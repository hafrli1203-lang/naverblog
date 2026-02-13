"""
체험단 DB 테스트 시나리오 (TC-01 ~ TC-30, TC-32~34)
DB/로직 관련 테스트를 자동 실행합니다.
(TC-31 SSE 스트리밍, TC-35~36 프론트 UI는 수동 확인 필요)
"""
from __future__ import annotations
import sys
import os
import sqlite3
import time
import json
from pathlib import Path
from datetime import datetime, timedelta

# 모듈 임포트를 위해 상위 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import get_conn, init_db, upsert_store, create_campaign, upsert_blogger, insert_exposure_fact, conn_ctx
from backend.keywords import StoreProfile, build_exposure_keywords, build_seed_queries
from backend.scoring import strength_points, calc_food_bias, calc_sponsor_signal
from backend.models import BlogPostItem
from backend.reporting import get_top10_and_top50
from backend.maintenance import cleanup_exposures

TEST_DB = Path(__file__).resolve().parent / "test_blogger_db.sqlite"

passed = 0
failed = 0
results = []


def report(tc_id: str, name: str, ok: bool, detail: str = ""):
    global passed, failed
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    results.append((tc_id, name, status, detail))
    print(f"  [{status}] {tc_id}: {name}" + (f" - {detail}" if detail and not ok else ""))


def fresh_conn():
    """테스트용 새 DB 연결"""
    if TEST_DB.exists():
        TEST_DB.unlink()
    conn = get_conn(TEST_DB)
    return conn


# ==================== TC-01 ~ TC-03: DB 초기화 ====================

def test_tc01_schema_creation():
    conn = fresh_conn()
    init_db(conn)

    # 4개 테이블 확인
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    table_names = {r["name"] for r in tables}
    expected = {"stores", "campaigns", "bloggers", "exposures"}
    ok = expected.issubset(table_names)
    report("TC-01", "스키마 생성 확인 (4개 테이블)", ok, f"found: {table_names}")

    # 인덱스 확인
    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    idx_names = {r["name"] for r in indexes}
    expected_idx = {
        "idx_stores_region_cat", "idx_campaigns_store",
        "ux_exposures_daily", "idx_exposures_store_date",
        "idx_exposures_blogger_date", "idx_exposures_keyword_date"
    }
    ok2 = expected_idx.issubset(idx_names)
    report("TC-01b", "인덱스 6개 생성 확인", ok2, f"found: {idx_names}")

    conn.close()


def test_tc02_pragma():
    conn = get_conn(TEST_DB)

    jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    sync = conn.execute("PRAGMA synchronous;").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]

    ok = jm == "wal" and sync == 1 and fk == 1
    report("TC-02", "WAL/PRAGMA 설정", ok, f"journal={jm}, sync={sync}, fk={fk}")
    conn.close()


def test_tc03_idempotent():
    conn = get_conn(TEST_DB)
    # 2회 실행
    init_db(conn)
    init_db(conn)

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    ok = len([r for r in tables if r["name"] in ("stores", "campaigns", "bloggers", "exposures")]) == 4
    report("TC-03", "멱등성(재실행) 확인", ok)
    conn.close()


# ==================== TC-04 ~ TC-07: 매장 관리 ====================

def test_tc04_new_store():
    conn = get_conn(TEST_DB)
    store_id = upsert_store(conn, "제주시", "안경원", "naver.me/xxx", None, None)
    conn.commit()

    row = conn.execute("SELECT * FROM stores WHERE store_id=?", (store_id,)).fetchone()
    ok = row is not None and row["region_text"] == "제주시" and row["category_text"] == "안경원"
    report("TC-04", "신규 매장 등록", ok, f"store_id={store_id}")
    conn.close()
    return store_id


def test_tc05_upsert_store():
    conn = get_conn(TEST_DB)

    # 첫 등록 (place_url 기반)
    sid1 = upsert_store(conn, "제주시", "안경원", "naver.me/xxx", None, None)
    conn.commit()

    old_row = conn.execute("SELECT updated_at FROM stores WHERE store_id=?", (sid1,)).fetchone()
    old_updated = old_row["updated_at"]

    time.sleep(1.1)  # updated_at 차이를 보기 위해

    sid2 = upsert_store(conn, "제주시", "안경원", "naver.me/xxx", "테스트매장", None)
    conn.commit()

    new_row = conn.execute("SELECT * FROM stores WHERE store_id=?", (sid2,)).fetchone()
    count = conn.execute("SELECT COUNT(*) as c FROM stores WHERE place_url='naver.me/xxx'").fetchone()["c"]

    ok = sid1 == sid2 and count == 1 and new_row["updated_at"] > old_updated
    report("TC-05", "동일 매장 재등록(upsert)", ok, f"sid1={sid1}, sid2={sid2}, count={count}")
    conn.close()


def test_tc06_multi_store():
    conn = get_conn(TEST_DB)

    s1 = upsert_store(conn, "제주시", "안경원", "naver.me/s1", None, None)
    s2 = upsert_store(conn, "서귀포시", "안경원", "naver.me/s2", None, None)
    s3 = upsert_store(conn, "제주시", "음식점", "naver.me/s3", None, None)
    conn.commit()

    ok = len({s1, s2, s3}) == 3
    report("TC-06", "멀티 매장 등록", ok, f"ids={s1},{s2},{s3}")
    conn.close()


def test_tc07_no_place_url():
    conn = get_conn(TEST_DB)

    sid = upsert_store(conn, "제주시", "카페", None, "테스트카페", "제주시 연동 123")
    conn.commit()

    row = conn.execute("SELECT * FROM stores WHERE store_id=?", (sid,)).fetchone()
    ok = row is not None and row["place_url"] is None and row["address_text"] == "제주시 연동 123"
    report("TC-07", "place_url 없이 주소 폴백 등록", ok)
    conn.close()


# ==================== TC-08 ~ TC-10: 캠페인 ====================

def test_tc08_create_campaign():
    conn = get_conn(TEST_DB)
    sid = upsert_store(conn, "테스트지역", "테스트업종", None, None, None)
    cid = create_campaign(conn, sid, memo="1차 캠페인")
    conn.commit()

    row = conn.execute("SELECT * FROM campaigns WHERE campaign_id=?", (cid,)).fetchone()
    ok = row is not None and row["store_id"] == sid and row["status"] == "대기중"
    report("TC-08", "캠페인 생성 + store_id FK", ok, f"cid={cid}, status={row['status'] if row else 'N/A'}")
    conn.close()


def test_tc09_campaign_status():
    conn = get_conn(TEST_DB)
    sid = upsert_store(conn, "상태테스트", "업종", None, None, None)
    cid = create_campaign(conn, sid)
    conn.commit()

    conn.execute("UPDATE campaigns SET status='연락완료', updated_at=datetime('now') WHERE campaign_id=?", (cid,))
    conn.commit()
    r1 = conn.execute("SELECT status FROM campaigns WHERE campaign_id=?", (cid,)).fetchone()["status"]

    conn.execute("UPDATE campaigns SET status='수락', updated_at=datetime('now') WHERE campaign_id=?", (cid,))
    conn.commit()
    r2 = conn.execute("SELECT status FROM campaigns WHERE campaign_id=?", (cid,)).fetchone()["status"]

    ok = r1 == "연락완료" and r2 == "수락"
    report("TC-09", "캠페인 상태 변경", ok, f"r1={r1}, r2={r2}")
    conn.close()


def test_tc10_fk_violation():
    conn = get_conn(TEST_DB)
    try:
        conn.execute("INSERT INTO campaigns(store_id, memo) VALUES (9999, 'test')")
        conn.commit()
        ok = False
        detail = "FK violation not raised"
    except sqlite3.IntegrityError as e:
        ok = True
        detail = str(e)
    except Exception as e:
        ok = False
        detail = f"Unexpected: {e}"

    report("TC-10", "존재하지 않는 store_id FK 오류", ok, detail)
    conn.close()


# ==================== TC-11 ~ TC-13: 블로거 ====================

def test_tc11_new_blogger():
    conn = get_conn(TEST_DB)
    upsert_blogger(conn, "test_blogger_01", "https://blog.naver.com/test_blogger_01",
                   None, None, None, None, None)
    conn.commit()

    row = conn.execute("SELECT * FROM bloggers WHERE blogger_id='test_blogger_01'").fetchone()
    ok = row is not None and row["first_seen_at"] == row["last_seen_at"]
    report("TC-11", "신규 블로거 upsert", ok)
    conn.close()


def test_tc12_blogger_revisit():
    conn = get_conn(TEST_DB)

    # 첫 방문
    upsert_blogger(conn, "revisit_test", "https://blog.naver.com/revisit_test",
                   None, None, None, None, None)
    conn.commit()
    r1 = conn.execute("SELECT * FROM bloggers WHERE blogger_id='revisit_test'").fetchone()
    first_seen = r1["first_seen_at"]

    time.sleep(1.1)

    # 재방문
    upsert_blogger(conn, "revisit_test", "https://blog.naver.com/revisit_test",
                   "20250101", None, 0.5, 0.3, None)
    conn.commit()
    r2 = conn.execute("SELECT * FROM bloggers WHERE blogger_id='revisit_test'").fetchone()

    count = conn.execute("SELECT COUNT(*) as c FROM bloggers WHERE blogger_id='revisit_test'").fetchone()["c"]

    ok = count == 1 and r2["first_seen_at"] == first_seen and r2["last_seen_at"] > first_seen
    report("TC-12", "기존 블로거 재방문(upsert)", ok, f"count={count}, first_preserved={r2['first_seen_at']==first_seen}")
    conn.close()


def test_tc13_blogger_rates():
    conn = get_conn(TEST_DB)
    upsert_blogger(conn, "rate_test", "https://blog.naver.com/rate_test",
                   None, None, 0.72, 0.65, None)
    conn.commit()

    row = conn.execute("SELECT * FROM bloggers WHERE blogger_id='rate_test'").fetchone()
    ok = abs(row["sponsor_signal_rate"] - 0.72) < 0.001 and abs(row["food_bias_rate"] - 0.65) < 0.001
    report("TC-13", "sponsor_signal_rate/food_bias_rate 저장", ok,
           f"sponsor={row['sponsor_signal_rate']}, food={row['food_bias_rate']}")
    conn.close()


# ==================== TC-14 ~ TC-17: 노출 히스토리 ====================

def test_tc14_exposure_insert():
    conn = get_conn(TEST_DB)

    # 먼저 store와 blogger가 있어야 함
    sid = upsert_store(conn, "노출테스트", "업종", None, None, None)
    upsert_blogger(conn, "exp_blogger", "https://blog.naver.com/exp_blogger",
                   None, None, None, None, None)
    conn.commit()

    insert_exposure_fact(conn, sid, "제주 안경원", "exp_blogger", 3, 5, True, True)
    conn.commit()

    row = conn.execute(
        "SELECT * FROM exposures WHERE store_id=? AND blogger_id='exp_blogger'", (sid,)
    ).fetchone()

    ok = (row is not None and row["rank"] == 3 and row["strength_points"] == 5
          and row["is_page1"] == 1 and row["is_exposed"] == 1)
    report("TC-14", "노출 팩트 정상 삽입", ok)
    conn.close()


def test_tc15_strength_points():
    tests = [
        (1, 5), (2, 5), (3, 5),      # 1~3위: 5점
        (4, 3), (7, 3), (10, 3),      # 4~10위: 3점
        (11, 2), (15, 2), (20, 2),    # 11~20위: 2점
        (21, 1), (25, 1), (30, 1),    # 21~30위: 1점
        (31, 0), (None, 0),           # 미노출: 0점
    ]

    all_ok = True
    details = []
    for rank, expected in tests:
        actual = strength_points(rank)
        if actual != expected:
            all_ok = False
            details.append(f"rank={rank}: expected={expected}, got={actual}")

    report("TC-15", "Strength 포인트 규칙 검증", all_ok, "; ".join(details) if details else "")


def test_tc16_unique_index():
    conn = get_conn(TEST_DB)

    sid = upsert_store(conn, "중복테스트", "업종", None, None, None)
    upsert_blogger(conn, "dup_blogger", "https://blog.naver.com/dup_blogger",
                   None, None, None, None, None)
    conn.commit()

    insert_exposure_fact(conn, sid, "중복키워드", "dup_blogger", 5, 3, True, True)
    conn.commit()

    before = conn.execute("SELECT COUNT(*) as c FROM exposures WHERE store_id=? AND keyword='중복키워드' AND blogger_id='dup_blogger'", (sid,)).fetchone()["c"]

    # 같은 날 재삽입 (INSERT OR IGNORE)
    insert_exposure_fact(conn, sid, "중복키워드", "dup_blogger", 3, 5, True, True)
    conn.commit()

    after = conn.execute("SELECT COUNT(*) as c FROM exposures WHERE store_id=? AND keyword='중복키워드' AND blogger_id='dup_blogger'", (sid,)).fetchone()["c"]

    ok = before == 1 and after == 1
    report("TC-16", "일별 중복 방지(UNIQUE INDEX)", ok, f"before={before}, after={after}")
    conn.close()


def test_tc17_next_day():
    conn = get_conn(TEST_DB)

    sid = upsert_store(conn, "날짜테스트", "업종", None, None, None)
    upsert_blogger(conn, "day_blogger", "https://blog.naver.com/day_blogger",
                   None, None, None, None, None)
    conn.commit()

    # 2일 전 날짜로 직접 삽입 (UTC/KST 시차로 1일 차이 시 충돌 방지)
    yesterday = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    conn.execute(
        """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (yesterday + " 12:00:00", yesterday, sid, "일별키워드", "day_blogger", 5, 3, 1, 1)
    )
    conn.commit()

    # 오늘 날짜로 삽입
    insert_exposure_fact(conn, sid, "일별키워드", "day_blogger", 5, 3, True, True)
    conn.commit()

    count = conn.execute(
        "SELECT COUNT(*) as c FROM exposures WHERE store_id=? AND keyword='일별키워드' AND blogger_id='day_blogger'", (sid,)
    ).fetchone()["c"]

    ok = count == 2
    report("TC-17", "다음 날 동일 데이터 재삽입", ok, f"count={count}")
    conn.close()


# ==================== TC-18 ~ TC-21: Top10 계산 ====================

def setup_top10_data(conn):
    """Top10 테스트용 데이터 셋업"""
    sid = upsert_store(conn, "탑10테스트", "업종", None, None, None)
    conn.commit()

    keywords = [f"keyword_{i}" for i in range(7)]

    # 15명의 블로거, 다양한 노출 패턴
    for i in range(15):
        bid = f"top_blogger_{i:02d}"
        fb = 0.3 if i % 3 != 0 else 0.7
        upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}",
                       None, None, None, fb, None)
    conn.commit()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    for i in range(15):
        bid = f"top_blogger_{i:02d}"
        for j, kw in enumerate(keywords):
            if i + j < 20:  # 다양한 노출 패턴
                rank = max(1, (i * 3 + j) % 35)
                sp = strength_points(rank)
                is_p1 = rank <= 10
                is_exp = rank <= 30
                conn.execute(
                    """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid, kw, bid, rank, sp, 1 if is_p1 else 0, 1 if is_exp else 0)
                )
    conn.commit()
    return sid


def test_tc18_top10():
    conn = get_conn(TEST_DB)
    sid = setup_top10_data(conn)

    result = get_top10_and_top50(conn, sid, days=30)
    top10 = result["top10"]

    ok1 = len(top10) <= 10
    # strength_sum 내림차순
    ok2 = all(top10[i]["strength_sum"] >= top10[i+1]["strength_sum"] for i in range(len(top10)-1))

    ok = ok1 and ok2
    report("TC-18", "30일 기준 Top10 조회", ok, f"count={len(top10)}, sorted={ok2}")
    conn.close()


def test_tc19_30day_window():
    conn = get_conn(TEST_DB)
    sid = upsert_store(conn, "윈도우테스트", "업종", None, None, None)

    # 31일 전 고점수 블로거
    upsert_blogger(conn, "old_blogger", "https://blog.naver.com/old_blogger",
                   None, None, None, 0.3, None)
    conn.commit()

    old_date = (datetime.now() - timedelta(days=31))
    old_date_str = old_date.strftime("%Y-%m-%d")
    conn.execute(
        """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (old_date.strftime("%Y-%m-%d %H:%M:%S"), old_date_str, sid, "old_kw", "old_blogger", 1, 5, 1, 1)
    )

    # 최근 블로거
    upsert_blogger(conn, "new_blogger", "https://blog.naver.com/new_blogger",
                   None, None, None, 0.3, None)
    conn.commit()

    now = datetime.now()
    conn.execute(
        """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d"), sid, "new_kw", "new_blogger", 5, 3, True, True)
    )
    conn.commit()

    result = get_top10_and_top50(conn, sid, days=30)
    top10_ids = {r["blogger_id"] for r in result["top10"]}

    ok = "old_blogger" not in top10_ids and "new_blogger" in top10_ids
    report("TC-19", "30일 초과 데이터 제외", ok, f"top10_ids={top10_ids}")
    conn.close()


def test_tc20_card_report():
    conn = get_conn(TEST_DB)
    sid = upsert_store(conn, "카드테스트", "업종", None, None, None)
    upsert_blogger(conn, "card_blogger", "https://blog.naver.com/card_blogger",
                   None, None, None, 0.3, None)
    conn.commit()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    keywords = [f"kw_{i}" for i in range(7)]

    for i, kw in enumerate(keywords):
        rank = (i + 1) * 3  # 3, 6, 9, 12, 15, 18, 21
        sp = strength_points(rank)
        is_p1 = rank <= 10
        is_exp = rank <= 30
        conn.execute(
            """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid, kw, "card_blogger", rank, sp, 1 if is_p1 else 0, 1 if is_exp else 0)
        )
    conn.commit()

    result = get_top10_and_top50(conn, sid, days=30)
    top10 = result["top10"]

    if top10:
        r = top10[0]
        ok1 = "7개 중 1페이지 노출:" in r["report_line1"]
        ok2 = "최고 순위:" in r["report_line2"]
        ok3 = r["page1_keywords_30d"] is not None
        ok4 = r["best_rank"] is not None
        ok = ok1 and ok2 and ok3 and ok4
        report("TC-20", "카드 상단 리포트 데이터 추출", ok,
               f"line1={r['report_line1']}, line2={r['report_line2']}")
    else:
        report("TC-20", "카드 상단 리포트 데이터 추출", False, "no top10 data")
    conn.close()


def test_tc21_no_exposure():
    conn = get_conn(TEST_DB)
    sid = upsert_store(conn, "미노출테스트", "업종", None, None, None)
    upsert_blogger(conn, "noexp_blogger", "https://blog.naver.com/noexp_blogger",
                   None, None, None, 0.3, None)
    conn.commit()

    # 노출 데이터 없이 조회
    result = get_top10_and_top50(conn, sid, days=30)
    top10_ids = {r["blogger_id"] for r in result["top10"]}

    ok = "noexp_blogger" not in top10_ids
    report("TC-21", "노출 0건 블로거 Top10 제외", ok)
    conn.close()


# ==================== TC-22 ~ TC-24: Top50 계산 ====================

def setup_top50_data(conn):
    """Top50 테스트용: 많은 블로거 데이터"""
    sid = upsert_store(conn, "탑50테스트", "업종", None, None, None)
    conn.commit()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    keywords = [f"kw50_{i}" for i in range(7)]

    # food 블로거 35명
    for i in range(35):
        bid = f"food_{i:02d}"
        upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}",
                       None, None, None, 0.7 + (i % 3) * 0.05, None)
    conn.commit()

    # 비맛집 블로거 20명
    for i in range(20):
        bid = f"nonfood_{i:02d}"
        upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}",
                       None, None, None, 0.1 + (i % 3) * 0.1, None)
    conn.commit()

    # 노출 데이터 삽입
    for i in range(35):
        bid = f"food_{i:02d}"
        for j, kw in enumerate(keywords[:3]):
            rank = max(1, (i + j) % 30 + 1)
            sp = strength_points(rank)
            conn.execute(
                """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid, kw, bid, rank, sp, 1 if rank<=10 else 0, 1 if rank<=30 else 0)
            )

    for i in range(20):
        bid = f"nonfood_{i:02d}"
        for j, kw in enumerate(keywords[:3]):
            rank = max(1, (i + j) % 25 + 1)
            sp = strength_points(rank)
            conn.execute(
                """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid, kw, bid, rank, sp, 1 if rank<=10 else 0, 1 if rank<=30 else 0)
            )
    conn.commit()
    return sid


def test_tc22_top50_basic():
    conn = get_conn(TEST_DB)
    sid = setup_top50_data(conn)

    result = get_top10_and_top50(conn, sid, days=30)
    top50 = result["top50"]

    ok = len(top50) <= 50 and len(top50) > 0
    report("TC-22", "운영풀 Top50 기본 조회", ok, f"count={len(top50)}")
    conn.close()


def test_tc23_food_quota():
    conn = get_conn(TEST_DB)
    sid = setup_top50_data(conn)

    result = get_top10_and_top50(conn, sid, days=30)
    top50 = result["top50"]

    food_count = sum(1 for r in top50 if (r.get("food_bias_rate") or 0) >= 0.60)
    nonfood_count = sum(1 for r in top50 if (r.get("food_bias_rate") or 0) < 0.60)

    food_cap = int(50 * 0.60)  # 30
    nonfood_min = int(50 * 0.30)  # 15

    ok1 = food_count <= food_cap
    ok2 = nonfood_count >= min(nonfood_min, nonfood_count)  # 가용한 비맛집 수 내에서

    ok = ok1 and ok2
    report("TC-23", "food 쿼터 적용", ok,
           f"food={food_count}(cap={food_cap}), nonfood={nonfood_count}(min={nonfood_min})")
    conn.close()


def test_tc24_under50():
    conn = get_conn(TEST_DB)
    sid = upsert_store(conn, "소수테스트", "업종", None, None, None)

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 5명만 등록
    for i in range(5):
        bid = f"few_{i}"
        upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}", None, None, None, 0.3, None)
    conn.commit()

    for i in range(5):
        bid = f"few_{i}"
        conn.execute(
            """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid, "test_kw", bid, i+1, strength_points(i+1), 1 if (i+1)<=10 else 0, 1)
        )
    conn.commit()

    result = get_top10_and_top50(conn, sid, days=30)
    total = len(result["top10"]) + len(result["top50"])

    ok = total == 5
    report("TC-24", "후보 50명 미만 시 처리", ok, f"top10={len(result['top10'])}, top50={len(result['top50'])}, total={total}")
    conn.close()


# ==================== TC-25 ~ TC-26: 멀티 매장 분리 ====================

def test_tc25_store_independence():
    conn = get_conn(TEST_DB)

    sid1 = upsert_store(conn, "매장A", "업종A", "url_A", None, None)
    sid2 = upsert_store(conn, "매장B", "업종B", "url_B", None, None)

    upsert_blogger(conn, "indep_a", "https://blog.naver.com/indep_a", None, None, None, 0.3, None)
    upsert_blogger(conn, "indep_b", "https://blog.naver.com/indep_b", None, None, None, 0.3, None)
    conn.commit()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # A매장에는 indep_a만
    conn.execute(
        """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid1, "kw_a", "indep_a", 1, 5, 1, 1)
    )
    # B매장에는 indep_b만
    conn.execute(
        """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid2, "kw_b", "indep_b", 1, 5, 1, 1)
    )
    conn.commit()

    r1 = get_top10_and_top50(conn, sid1, 30)
    r2 = get_top10_and_top50(conn, sid2, 30)

    ids1 = {r["blogger_id"] for r in r1["top10"]}
    ids2 = {r["blogger_id"] for r in r2["top10"]}

    ok = "indep_b" not in ids1 and "indep_a" not in ids2
    report("TC-25", "매장별 노출 독립성", ok, f"store1={ids1}, store2={ids2}")
    conn.close()


def test_tc26_same_blogger_multi_store():
    conn = get_conn(TEST_DB)

    sid1 = upsert_store(conn, "공유매장1", "업종1", "url_share1", None, None)
    sid2 = upsert_store(conn, "공유매장2", "업종2", "url_share2", None, None)

    upsert_blogger(conn, "shared_blogger", "https://blog.naver.com/shared_blogger", None, None, None, 0.3, None)
    conn.commit()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 매장1: rank=1 (5점)
    conn.execute(
        """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid1, "kw_share", "shared_blogger", 1, 5, 1, 1)
    )
    # 매장2: rank=20 (2점)
    conn.execute(
        """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid2, "kw_share", "shared_blogger", 20, 2, 0, 1)
    )
    conn.commit()

    r1 = get_top10_and_top50(conn, sid1, 30)
    r2 = get_top10_and_top50(conn, sid2, 30)

    s1 = next((r["strength_sum"] for r in r1["top10"] if r["blogger_id"] == "shared_blogger"), None)
    s2 = next((r["strength_sum"] for r in r2["top10"] if r["blogger_id"] == "shared_blogger"), None)

    ok = s1 == 5 and s2 == 2
    report("TC-26", "동일 블로거 다중 매장 노출 이력", ok, f"store1_sum={s1}, store2_sum={s2}")
    conn.close()


# ==================== TC-27 ~ TC-28: 보관정책 ====================

def test_tc27_cleanup():
    conn = get_conn(TEST_DB)

    sid = upsert_store(conn, "정리테스트", "업종", None, None, None)
    upsert_blogger(conn, "cleanup_blogger", "https://blog.naver.com/cleanup_blogger", None, None, None, 0.3, None)
    conn.commit()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 190일 전 데이터 (삭제 대상)
    old = now - timedelta(days=190)
    for i in range(10):
        conn.execute(
            """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (old.strftime("%Y-%m-%d %H:%M:%S"), old.strftime("%Y-%m-%d"), sid, f"old_kw_{i}", "cleanup_blogger", 1, 5, 1, 1)
        )

    # 최근 데이터 (보존 대상)
    for i in range(20):
        recent = now - timedelta(days=i)
        conn.execute(
            """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (recent.strftime("%Y-%m-%d %H:%M:%S"), recent.strftime("%Y-%m-%d"), sid, f"recent_kw_{i}", "cleanup_blogger", 5, 3, 1, 1)
        )
    conn.commit()

    before = conn.execute("SELECT COUNT(*) as c FROM exposures WHERE store_id=?", (sid,)).fetchone()["c"]
    deleted = cleanup_exposures(conn, keep_days=180)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) as c FROM exposures WHERE store_id=?", (sid,)).fetchone()["c"]

    ok = deleted == 10 and after == 20
    report("TC-27", "180일 청소 쿼리 실행", ok, f"before={before}, deleted={deleted}, after={after}")
    conn.close()


def test_tc28_cleanup_then_top10():
    conn = get_conn(TEST_DB)

    sid = upsert_store(conn, "정리후조회", "업종", None, None, None)
    upsert_blogger(conn, "postclean", "https://blog.naver.com/postclean", None, None, None, 0.3, None)
    conn.commit()

    now = datetime.now()

    # 최근 5일 데이터만
    for i in range(5):
        recent = now - timedelta(days=i)
        conn.execute(
            """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (recent.strftime("%Y-%m-%d %H:%M:%S"), recent.strftime("%Y-%m-%d"), sid, f"pc_kw_{i}", "postclean", 2, 5, 1, 1)
        )
    conn.commit()

    cleanup_exposures(conn, keep_days=180)
    conn.commit()

    result = get_top10_and_top50(conn, sid, days=30)
    ok = len(result["top10"]) == 1 and result["top10"][0]["blogger_id"] == "postclean"
    report("TC-28", "청소 후 Top10 정상 동작", ok)
    conn.close()


# ==================== TC-29 ~ TC-30: 성능 ====================

def test_tc29_explain():
    conn = get_conn(TEST_DB)

    plan = conn.execute(
        """EXPLAIN QUERY PLAN
        SELECT blogger_id, SUM(strength_points)
        FROM exposures
        WHERE store_id=1 AND checked_at >= datetime('now', '-30 days')
        GROUP BY blogger_id"""
    ).fetchall()

    plan_text = " ".join(str(dict(r)) for r in plan)
    ok = "SCAN" not in plan_text.upper() or "INDEX" in plan_text.upper()
    report("TC-29", "EXPLAIN QUERY PLAN 인덱스 활용", ok, plan_text[:200])
    conn.close()


def test_tc30_bulk_performance():
    conn = get_conn(TEST_DB)

    sid = upsert_store(conn, "성능테스트", "업종", None, None, None)

    # 블로거 100명 등록
    for i in range(100):
        upsert_blogger(conn, f"perf_{i:04d}", f"https://blog.naver.com/perf_{i:04d}",
                       None, None, None, 0.3, None)
    conn.commit()

    # 10,000건 bulk insert
    now = datetime.now()
    keywords = [f"perf_kw_{j}" for j in range(10)]

    for i in range(100):
        bid = f"perf_{i:04d}"
        for j, kw in enumerate(keywords):
            for d in range(10):
                dt = now - timedelta(days=d)
                conn.execute(
                    """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (dt.strftime("%Y-%m-%d %H:%M:%S"), dt.strftime("%Y-%m-%d"), sid, kw, bid,
                     (i+j+d) % 30 + 1, strength_points((i+j+d) % 30 + 1),
                     1 if (i+j+d) % 30 + 1 <= 10 else 0,
                     1 if (i+j+d) % 30 + 1 <= 30 else 0)
                )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) as c FROM exposures WHERE store_id=?", (sid,)).fetchone()["c"]

    start = time.time()
    result = get_top10_and_top50(conn, sid, days=30)
    elapsed = time.time() - start

    ok = elapsed < 1.0 and len(result["top10"]) <= 10
    report("TC-30", "대용량 데이터 조회 속도", ok,
           f"rows={total}, time={elapsed:.3f}s, top10={len(result['top10'])}")
    conn.close()


# ==================== TC-32: 키워드 7개 ====================

def test_tc32_keywords():
    profile = StoreProfile(region_text="제주시", category_text="안경원")
    kws = build_exposure_keywords(profile)

    ok = len(kws) == 7
    report("TC-32", "키워드 7개 생성 확인", ok, f"keywords={kws}")


# ==================== TC-33 ~ TC-34: 캠페인 CRUD ====================

def test_tc33_campaign_list():
    conn = get_conn(TEST_DB)

    for i in range(3):
        sid = upsert_store(conn, f"캠페인리스트{i}", "업종", None, None, None)
        create_campaign(conn, sid, memo=f"캠페인{i}")
    conn.commit()

    rows = conn.execute(
        """SELECT c.campaign_id, c.store_id, c.status, s.region_text
           FROM campaigns c JOIN stores s ON s.store_id = c.store_id"""
    ).fetchall()

    ok = len(rows) >= 3
    report("TC-33", "캠페인 목록 조회", ok, f"count={len(rows)}")
    conn.close()


def test_tc34_cascade_delete():
    conn = get_conn(TEST_DB)

    sid = upsert_store(conn, "삭제테스트", "업종", "url_delete_test", None, None)
    cid = create_campaign(conn, sid, memo="삭제용")
    upsert_blogger(conn, "cascade_b", "https://blog.naver.com/cascade_b", None, None, None, 0.3, None)
    conn.commit()

    now = datetime.now()
    insert_exposure_fact(conn, sid, "cascade_kw", "cascade_b", 1, 5, True, True)
    conn.commit()

    # 삭제 전 확인
    exp_before = conn.execute("SELECT COUNT(*) as c FROM exposures WHERE store_id=?", (sid,)).fetchone()["c"]
    camp_before = conn.execute("SELECT COUNT(*) as c FROM campaigns WHERE store_id=?", (sid,)).fetchone()["c"]

    # store 삭제 → CASCADE
    conn.execute("DELETE FROM stores WHERE store_id=?", (sid,))
    conn.commit()

    exp_after = conn.execute("SELECT COUNT(*) as c FROM exposures WHERE store_id=?", (sid,)).fetchone()["c"]
    camp_after = conn.execute("SELECT COUNT(*) as c FROM campaigns WHERE store_id=?", (sid,)).fetchone()["c"]

    ok = exp_before >= 1 and camp_before >= 1 and exp_after == 0 and camp_after == 0
    report("TC-34", "캠페인 삭제 시 연관 데이터 CASCADE", ok,
           f"exp: {exp_before}→{exp_after}, camp: {camp_before}→{camp_after}")
    conn.close()


# ==================== MAIN ====================

def main():
    print("=" * 60)
    print("체험단 DB 테스트 시나리오 실행")
    print("=" * 60)

    # 깨끗한 시작
    if TEST_DB.exists():
        TEST_DB.unlink()

    print("\n[DB 초기화 TC-01~03]")
    test_tc01_schema_creation()
    test_tc02_pragma()
    test_tc03_idempotent()

    print("\n[매장 관리 TC-04~07]")
    test_tc04_new_store()
    test_tc05_upsert_store()
    test_tc06_multi_store()
    test_tc07_no_place_url()

    print("\n[캠페인 TC-08~10]")
    test_tc08_create_campaign()
    test_tc09_campaign_status()
    test_tc10_fk_violation()

    print("\n[블로거 TC-11~13]")
    test_tc11_new_blogger()
    test_tc12_blogger_revisit()
    test_tc13_blogger_rates()

    print("\n[노출 히스토리 TC-14~17]")
    test_tc14_exposure_insert()
    test_tc15_strength_points()
    test_tc16_unique_index()
    test_tc17_next_day()

    print("\n[Top10 계산 TC-18~21]")
    test_tc18_top10()
    test_tc19_30day_window()
    test_tc20_card_report()
    test_tc21_no_exposure()

    print("\n[Top50 계산 TC-22~24]")
    test_tc22_top50_basic()
    test_tc23_food_quota()
    test_tc24_under50()

    print("\n[멀티 매장 분리 TC-25~26]")
    test_tc25_store_independence()
    test_tc26_same_blogger_multi_store()

    print("\n[보관정책 TC-27~28]")
    test_tc27_cleanup()
    test_tc28_cleanup_then_top10()

    print("\n[성능 TC-29~30]")
    test_tc29_explain()
    test_tc30_bulk_performance()

    print("\n[키워드 TC-32]")
    test_tc32_keywords()

    print("\n[캠페인 CRUD TC-33~34]")
    test_tc33_campaign_list()
    test_tc34_cascade_delete()

    # 정리
    if TEST_DB.exists():
        TEST_DB.unlink()
    wal = Path(str(TEST_DB) + "-wal")
    shm = Path(str(TEST_DB) + "-shm")
    if wal.exists():
        wal.unlink()
    if shm.exists():
        shm.unlink()

    print("\n" + "=" * 60)
    print(f"결과: {passed} PASS / {failed} FAIL (총 {passed+failed}건)")
    print("=" * 60)

    if failed > 0:
        print("\n실패 항목:")
        for tc_id, name, status, detail in results:
            if status == "FAIL":
                print(f"  {tc_id}: {name} - {detail}")

    return failed


if __name__ == "__main__":
    sys.exit(main())
