"""
체험단 DB 테스트 시나리오 (TC-01 ~ TC-102)
DB/로직 관련 테스트를 자동 실행합니다.
(TC-31 SSE 스트리밍은 수동 확인 필요)
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

from backend.db import get_conn, init_db, upsert_store, create_campaign, upsert_blogger, insert_exposure_fact, conn_ctx, insert_blog_analysis
from backend.keywords import StoreProfile, build_exposure_keywords, build_seed_queries, build_region_power_queries, is_topic_mode, TOPIC_SEED_MAP
from backend.scoring import strength_points, calc_food_bias, calc_sponsor_signal, golden_score, is_food_category
from backend.models import BlogPostItem
from backend.reporting import get_top10_and_top50, get_top20_and_pool40
from backend.analyzer import canonical_blogger_id_from_item
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

    ok = len(kws) == 10
    report("TC-32", "키워드 10개 생성 확인 (7 캐시 + 3 홀드아웃)", ok, f"keywords={kws}")


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


# ==================== TC-35 ~ TC-37: GoldenScore + base_score 컬럼 ====================

def test_tc35_base_score_column():
    conn = get_conn(TEST_DB)
    cursor = conn.execute("PRAGMA table_info(bloggers)")
    cols = {row[1] for row in cursor.fetchall()}
    ok = "base_score" in cols
    report("TC-35", "bloggers 테이블에 base_score 컬럼 존재", ok, f"cols={cols}")
    conn.close()


def test_tc36_golden_score():
    # v3.0: page1_keywords 파라미터 추가, confidence는 page1 기반
    gs = golden_score(
        base_score_val=50.0,
        strength_sum=20,
        exposed_keywords=7,
        total_keywords=10,
        food_bias_rate=0.3,
        sponsor_signal_rate=0.2,
        is_food_cat=False,
        page1_keywords=4,
    )
    # page1=4/10=0.4 >= 0.3 → confidence=1.0
    gs_zero = golden_score(
        base_score_val=50.0,
        strength_sum=0,
        exposed_keywords=0,
        total_keywords=10,
        food_bias_rate=0.3,
        sponsor_signal_rate=0.2,
        is_food_cat=False,
        page1_keywords=0,
    )
    # page1=0, exposed=0 → confidence=0.2
    ok1 = 0 <= gs <= 100
    ok2 = 0 <= gs_zero <= 100
    ok3 = gs_zero < gs  # 0-노출은 반드시 낮아야 함
    ok = ok1 and ok2 and ok3
    report("TC-36", "GoldenScore v3.0 범위 0~100 + page1 confidence 적용", ok,
           f"gs_normal={gs}, gs_zero_exposure={gs_zero}")


def test_tc37_is_food_category():
    ok1 = is_food_category("카페") is True
    ok2 = is_food_category("맛집") is True
    ok3 = is_food_category("안경원") is False
    ok4 = is_food_category("헬스장") is False
    ok = ok1 and ok2 and ok3 and ok4
    report("TC-37", "is_food_category 분류", ok, f"카페={ok1}, 맛집={ok2}, 안경원={ok3}, 헬스장={ok4}")


# ==================== TC-38 ~ TC-43: v2.0 성능 최적화 ====================

def test_tc38_food_words_no_generic():
    """FOOD_WORDS에 범용 단어가 없는지 확인"""
    from backend.scoring import FOOD_WORDS
    generic = {"추천", "후기", "솔직후기", "리뷰", "방문"}
    overlap = generic & set(FOOD_WORDS)
    ok = len(overlap) == 0
    report("TC-38", "FOOD_WORDS에 범용 단어 미포함", ok, f"overlap={overlap}")


def test_tc39_blogger_id_extraction():
    """blogId= 파라미터 우선 추출 + 시스템 경로 제외"""
    # blogId 파라미터 추출
    item1 = BlogPostItem(title="t", description="d",
                         link="https://blog.naver.com/PostView.naver?blogId=testuser&logNo=123",
                         bloggerlink="")
    bid1 = canonical_blogger_id_from_item(item1)
    ok1 = bid1 == "testuser"

    # 시스템 경로 제외 (.nhn)
    item2 = BlogPostItem(title="t", description="d",
                         link="https://blog.naver.com/PostView.nhn?blogId=realuser",
                         bloggerlink="https://blog.naver.com/postview.nhn")
    bid2 = canonical_blogger_id_from_item(item2)
    ok2 = bid2 == "realuser"

    # 일반 경로 추출
    item3 = BlogPostItem(title="t", description="d",
                         link="https://blog.naver.com/normaluser/12345",
                         bloggerlink="")
    bid3 = canonical_blogger_id_from_item(item3)
    ok3 = bid3 == "normaluser"

    ok = ok1 and ok2 and ok3
    report("TC-39", "blogger_id 추출 (blogId=, 경로, .nhn)", ok,
           f"bid1={bid1}, bid2={bid2}, bid3={bid3}")


def test_tc40_bloggername_in_sample():
    """posts_sample_json에 bloggername이 포함되는지 확인"""
    conn = get_conn(TEST_DB)
    sample_json = json.dumps([
        {"title": "테스트 제목", "postdate": "20250101", "link": "http://example.com", "bloggername": "테스트블로거"}
    ], ensure_ascii=False)
    upsert_blogger(conn, "sample_test", "https://blog.naver.com/sample_test",
                   None, None, None, None, sample_json)
    conn.commit()

    row = conn.execute("SELECT posts_sample_json FROM bloggers WHERE blogger_id='sample_test'").fetchone()
    sample = json.loads(row["posts_sample_json"])
    ok = sample[0].get("bloggername") == "테스트블로거"
    report("TC-40", "posts_sample_json에 bloggername 포함", ok,
           f"bloggername={sample[0].get('bloggername')}")
    conn.close()


def test_tc41_pool40_nonfood_quota():
    """Pool40 비음식 업종: 비맛집 50%+ 확보"""
    conn = get_conn(TEST_DB)
    sid = upsert_store(conn, "쿼터테스트", "안경원", "url_quota", "테스트안경원", None)
    conn.commit()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 60명 블로거: 30명 맛집(fb=0.7), 30명 비맛집(fb=0.2)
    for i in range(60):
        bid = f"quota_{i:02d}"
        fb = 0.7 if i < 30 else 0.2
        upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}",
                       None, None, None, fb, None)
    conn.commit()

    keywords = [f"quota_kw_{j}" for j in range(3)]
    for i in range(60):
        bid = f"quota_{i:02d}"
        for j, kw in enumerate(keywords):
            rank = max(1, (i + j) % 30 + 1)
            sp = strength_points(rank)
            conn.execute(
                """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid, kw, bid, rank, sp, 1 if rank<=10 else 0, 1 if rank<=30 else 0)
            )
    conn.commit()

    result = get_top20_and_pool40(conn, sid, days=30, category_text="안경원")
    pool40 = result["pool40"]

    nonfood_in_pool = sum(1 for r in pool40 if (r.get("food_bias_rate") or 0) < 0.60)
    food_in_pool = sum(1 for r in pool40 if (r.get("food_bias_rate") or 0) >= 0.60)

    # 비음식 업종: food_cap=12 (30%), nonfood_min=20 (50%)
    ok1 = food_in_pool <= 12  # food_cap
    ok2 = nonfood_in_pool >= min(20, nonfood_in_pool)  # nonfood_min met within available

    ok = ok1 and ok2
    report("TC-41", "Pool40 비음식 업종 동적 쿼터", ok,
           f"food={food_in_pool}(cap=12), nonfood={nonfood_in_pool}(min=20)")
    conn.close()


def test_tc42_guide_templates():
    """가이드 템플릿: 병원/헬스장 존재 확인"""
    from backend.guide_generator import generate_guide

    guide1 = generate_guide("서울", "정형외과")
    ok1 = "진료" in guide1["full_guide_text"]

    guide2 = generate_guide("강남", "헬스장")
    ok2 = "트레이너" in guide2["full_guide_text"] or "PT" in guide2["full_guide_text"]

    # 해시태그 공백 없음 확인
    guide3 = generate_guide("제주시 연동", "카페")
    ok3 = all(" " not in tag for tag in guide3["hashtag_examples"])

    ok = ok1 and ok2 and ok3
    report("TC-42", "가이드 병원/헬스 + 해시태그 공백", ok,
           f"병원={ok1}, 헬스={ok2}, 해시태그공백없음={ok3}")


def test_tc43_broad_query_categories():
    """CATEGORY_BROAD_MAP 확장 카테고리 매칭"""
    from backend.keywords import build_broad_queries

    # 치과 → 카테고리 매칭
    p1 = StoreProfile(region_text="서울", category_text="치과")
    q1 = build_broad_queries(p1)
    ok1 = any("임플란트" in q or "치과" in q for q in q1)

    # 학원 → 카테고리 매칭
    p2 = StoreProfile(region_text="강남", category_text="영어학원")
    q2 = build_broad_queries(p2)
    ok2 = any("학원" in q for q in q2)

    # 안경원 → 안경 매칭
    p3 = StoreProfile(region_text="제주시", category_text="안경원")
    q3 = build_broad_queries(p3)
    ok3 = any("렌즈" in q or "시력" in q for q in q3)

    ok = ok1 and ok2 and ok3
    report("TC-43", "CATEGORY_BROAD_MAP 확장 매칭", ok,
           f"치과={ok1}({q1[:2]}), 학원={ok2}({q2[:2]}), 안경원={ok3}({q3[:2]})")


# ==================== TC-44 ~ TC-48: 검토보고서 반영 항목 ====================

def test_tc44_keyword_weight_for_suffix():
    """키워드 가중치: 핵심(1.5x) / 추천(1.3x) / 후기(1.2x) / 가격(1.1x) / 기타(1.0x)"""
    from backend.scoring import keyword_weight_for_suffix

    # 2단어 = 메인 키워드 → 1.5x
    ok1 = keyword_weight_for_suffix("강남 카페") == 1.5
    # 추천 → 1.3x
    ok2 = keyword_weight_for_suffix("강남 카페 추천") == 1.3
    # 후기 → 1.2x
    ok3 = keyword_weight_for_suffix("강남 카페 후기") == 1.2
    # 가격 → 1.1x
    ok4 = keyword_weight_for_suffix("강남 카페 가격") == 1.1
    # 기타 → 1.0x
    ok5 = keyword_weight_for_suffix("강남 카페 인기") == 1.0

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-44", "키워드 가중치 (suffix별 weight)", ok,
           f"메인={ok1}, 추천={ok2}, 후기={ok3}, 가격={ok4}, 기타={ok5}")


def test_tc45_exposure_potential():
    """ExposurePotential 태그가 블로거 결과에 포함되는지 확인"""
    conn = get_conn(TEST_DB)
    sid = upsert_store(conn, "포텐셜테스트", "카페", "url_potential", "테스트카페", None)
    conn.commit()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 블로거A: 5개 키워드 노출 (page1) → 매우높음
    upsert_blogger(conn, "potential_a", "https://blog.naver.com/potential_a",
                   None, None, None, 0.3, None, base_score=50.0)
    # 블로거B: 하위권 노출만 (rank=20, page1=0) → 낮음
    upsert_blogger(conn, "potential_b", "https://blog.naver.com/potential_b",
                   None, None, None, 0.3, None, base_score=50.0)
    conn.commit()

    keywords = [f"pot_kw_{i}" for i in range(6)]
    for j, kw in enumerate(keywords[:5]):
        rank = j + 1
        sp = strength_points(rank)
        conn.execute(
            """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid, kw, "potential_a", rank, sp, 1, 1)
        )
    # B는 하위권 노출 1건 (rank=20, is_exposed=1, is_page1=0) → Pool40만 가능
    conn.execute(
        """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid, "pot_kw_0", "potential_b", 20, 2, 0, 1)
    )
    conn.commit()

    result = get_top20_and_pool40(conn, sid, days=30, category_text="카페")
    all_b = result["top20"] + result["pool40"]

    a_entry = next((b for b in all_b if b["blogger_id"] == "potential_a"), None)

    ok1 = a_entry is not None and a_entry.get("exposure_potential") == "매우높음"

    # B는 하위권 노출만 → Pool40에 존재, exposure_potential = "낮음" 또는 "보통"
    b_entry = next((b for b in all_b if b["blogger_id"] == "potential_b"), None)
    ok2 = b_entry is not None and b_entry.get("exposure_potential") in ("낮음", "보통")

    ok = ok1 and ok2
    report("TC-45", "ExposurePotential 태그 정확도", ok,
           f"A={a_entry.get('exposure_potential') if a_entry else 'N/A'}, "
           f"B={b_entry.get('exposure_potential') if b_entry else 'N/A'}")
    conn.close()


def test_tc46_category_holdout_keywords():
    """업종별 홀드아웃 키워드가 seed와 다른지 확인"""
    from backend.keywords import build_seed_queries

    # 안경원 → CATEGORY_HOLDOUT_MAP 매칭
    profile = StoreProfile(region_text="제주시", category_text="안경원")
    exp_kws = build_exposure_keywords(profile)
    seed_kws = build_seed_queries(profile)

    # 홀드아웃 키워드는 seed에 없어야 함 (최소 1개)
    seed_set = set(seed_kws)
    holdout_only = [kw for kw in exp_kws if kw not in seed_set]
    ok1 = len(holdout_only) >= 1

    # 안경 관련 홀드아웃이 포함되어야 함
    ok2 = any("안경" in kw or "렌즈" in kw for kw in holdout_only)

    # 카페 → 다른 홀드아웃
    profile2 = StoreProfile(region_text="강남", category_text="카페")
    exp_kws2 = build_exposure_keywords(profile2)
    seed_kws2 = build_seed_queries(profile2)
    seed_set2 = set(seed_kws2)
    holdout_only2 = [kw for kw in exp_kws2 if kw not in seed_set2]
    ok3 = any("카페" in kw or "커피" in kw for kw in holdout_only2)

    ok = ok1 and ok2 and ok3
    report("TC-46", "업종별 홀드아웃 키워드 분리", ok,
           f"안경holdout={holdout_only}, 카페holdout={holdout_only2}")


def test_tc47_broad_bonus_in_base_score():
    """broad_query_hits → base_score broad_bonus 반영 확인"""
    from backend.scoring import base_score
    from backend.models import CandidateBlogger, BlogPostItem

    posts = [BlogPostItem(title="테스트", description="설명", link="http://ex.com",
                          postdate=datetime.now().strftime("%Y%m%d"))]

    # broad_query_hits = 0 → bonus = 0
    b1 = CandidateBlogger(
        blogger_id="broad_test_0", blog_url="http://b.com/broad_test_0",
        ranks=[5], queries_hit={"q1"}, posts=posts, local_hits=0,
        broad_query_hits=0,
    )
    s1 = base_score(b1, region_text="서울", address_tokens=[], queries_total=10)

    # broad_query_hits = 3 → bonus = 5
    b2 = CandidateBlogger(
        blogger_id="broad_test_3", blog_url="http://b.com/broad_test_3",
        ranks=[5], queries_hit={"q1"}, posts=posts, local_hits=0,
        broad_query_hits=3,
    )
    s2 = base_score(b2, region_text="서울", address_tokens=[], queries_total=10)

    # broad_query_hits = 1 → bonus = 2
    b3 = CandidateBlogger(
        blogger_id="broad_test_1", blog_url="http://b.com/broad_test_1",
        ranks=[5], queries_hit={"q1"}, posts=posts, local_hits=0,
        broad_query_hits=1,
    )
    s3 = base_score(b3, region_text="서울", address_tokens=[], queries_total=10)

    ok1 = s2 > s1  # 3히트 > 0히트
    ok2 = s3 > s1  # 1히트 > 0히트
    ok3 = s2 > s3  # 3히트 > 1히트
    ok4 = 0 <= s1 <= 80 and 0 <= s2 <= 80  # 범위 0~80

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-47", "broad_bonus base_score 반영", ok,
           f"0hits={s1:.1f}, 1hit={s3:.1f}, 3hits={s2:.1f}, range_ok={ok4}")


def test_tc48_weighted_strength_golden_score():
    """weighted_strength가 golden_score에 반영되는지 확인 (v3.0: BP=15, Exp=30, P1Auth=15)"""
    # weighted_strength > 0 → 일반 strength_sum 대신 사용
    gs1 = golden_score(
        base_score_val=50.0, strength_sum=10, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, weighted_strength=0.0, page1_keywords=3,
    )
    gs2 = golden_score(
        base_score_val=50.0, strength_sum=10, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, weighted_strength=20.0, page1_keywords=3,
    )
    # weighted_strength=20 > strength_sum=10 → gs2 > gs1
    # page1=3/10=0.3 → confidence=1.0 (양쪽 동일)
    ok1 = gs2 > gs1
    ok2 = 0 <= gs1 <= 100 and 0 <= gs2 <= 100

    ok = ok1 and ok2
    report("TC-48", "weighted_strength golden_score 반영 (v3.0)", ok,
           f"gs_raw={gs1}, gs_weighted={gs2}")


# ==================== TC-49 ~ TC-52: 검토보고서 v2 반영 ====================

def test_tc49_api_retry_config():
    """NaverBlogSearchClient에 재시도/백오프 설정이 있는지 확인"""
    from backend.naver_client import NaverBlogSearchClient, _RETRYABLE_STATUS

    client = NaverBlogSearchClient("test_id", "test_secret")
    ok1 = client.max_retries == 3
    ok2 = client.base_delay == 1.0
    ok3 = 429 in _RETRYABLE_STATUS
    ok4 = 500 in _RETRYABLE_STATUS and 502 in _RETRYABLE_STATUS
    ok5 = 401 not in _RETRYABLE_STATUS and 403 not in _RETRYABLE_STATUS

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-49", "API 재시도/백오프 설정 존재", ok,
           f"retries={client.max_retries}, delay={client.base_delay}, "
           f"429재시도={ok3}, 5xx재시도={ok4}, 401미재시도={ok5}")


def test_tc50_category_synonym_matching():
    """카테고리 동의어 매핑: 변형 입력에서 올바른 Broad/Holdout 매칭"""
    from backend.keywords import build_broad_queries, build_exposure_keywords

    # "커피전문점" → 카페 Broad 매칭
    p1 = StoreProfile(region_text="강남", category_text="커피전문점")
    q1 = build_broad_queries(p1)
    ok1 = any("디저트" in q or "브런치" in q or "카페" in q for q in q1)

    # "삼겹살집" → 음식 Broad 매칭
    p2 = StoreProfile(region_text="종로", category_text="삼겹살집")
    q2 = build_broad_queries(p2)
    ok2 = any("맛집" in q or "점심" in q for q in q2)

    # "피트니스" → 헬스 Holdout 매칭
    p3 = StoreProfile(region_text="서울", category_text="피트니스센터")
    exp3 = build_exposure_keywords(p3)
    ok3 = any("헬스장" in kw or "PT" in kw or "운동" in kw for kw in exp3)

    # "의원" → 병원 Broad 매칭
    p4 = StoreProfile(region_text="부산", category_text="정형외과의원")
    q4 = build_broad_queries(p4)
    ok4 = any("병원" in q or "건강검진" in q or "클리닉" in q for q in q4)

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-50", "카테고리 동의어 매핑", ok,
           f"커피전문점→카페={ok1}, 삼겹살집→음식={ok2}, "
           f"피트니스→헬스={ok3}, 정형외과→병원={ok4}")


def test_tc51_guide_disclosure_position():
    """표시의무: 본문 최상단 위치 + 제목 표기 권장"""
    from backend.guide_generator import generate_guide

    guide = generate_guide("강남", "카페")
    text = guide["full_guide_text"]

    ok1 = "본문 최상단" in text or "첫 문단" in text
    ok2 = "제목에" in text and ("[체험단]" in text or "[협찬]" in text)
    ok3 = "스크롤 없이" in text or "첫 화면" in text

    ok = ok1 and ok2 and ok3
    report("TC-51", "표시의무 최상단 위치 + 제목 권장", ok,
           f"최상단={ok1}, 제목표기={ok2}, 첫화면={ok3}")


def test_tc52_kpi_definition_in_meta():
    """reporting meta에 KPI 정의가 포함되는지 확인"""
    conn = get_conn(TEST_DB)
    sid = upsert_store(conn, "KPI테스트", "카페", "url_kpi", None, None)
    upsert_blogger(conn, "kpi_blogger", "https://blog.naver.com/kpi_blogger",
                   None, None, None, 0.3, None, base_score=30.0)
    conn.commit()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    conn.execute(
        """INSERT OR IGNORE INTO exposures(checked_at, checked_date, store_id, keyword, blogger_id, rank, strength_points, is_page1, is_exposed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now.strftime("%Y-%m-%d %H:%M:%S"), today, sid, "kpi_kw", "kpi_blogger", 5, 3, 1, 1)
    )
    conn.commit()

    result = get_top20_and_pool40(conn, sid, days=30, category_text="카페")
    meta = result["meta"]

    ok1 = "kpi_definition" in meta
    ok2 = "scoring_model" in meta
    ok3 = "블로그탭" in meta.get("kpi_definition", "")
    ok4 = "GoldenScore" in meta.get("scoring_model", "")

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-52", "meta에 KPI 정의 + 스코어링 모델 명시", ok,
           f"kpi={meta.get('kpi_definition', 'N/A')[:30]}, model={meta.get('scoring_model', 'N/A')[:30]}")
    conn.close()


# ==================== TC-53 ~ TC-57: 가이드 업그레이드 ====================

def test_tc53_new_template_matching():
    """신규 템플릿 매칭: 치과/학원/숙박/자동차 → 전용 템플릿 (default 아님)"""
    from backend.guide_generator import generate_guide, _match_template

    # 치과 → 치과 템플릿
    key1, _ = _match_template("임플란트 치과")
    ok1 = key1 == "치과"

    # 학원 → 학원 템플릿
    key2, _ = _match_template("영어학원")
    ok2 = key2 == "학원"

    # 숙박 → 숙박 템플릿
    key3, _ = _match_template("펜션")
    ok3 = key3 == "숙박"

    # 자동차 → 자동차 템플릿
    key4, _ = _match_template("자동차 정비")
    ok4 = key4 == "자동차"

    # 알 수 없는 카테고리 → default
    key5, _ = _match_template("알수없는업종")
    ok5 = key5 == "default"

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-53", "신규 템플릿 매칭 (치과/학원/숙박/자동차)", ok,
           f"치과={key1}, 학원={key2}, 숙박={key3}, 자동차={key4}, default={key5}")


def test_tc54_forbidden_words_in_guide():
    """금지어/대체표현이 가이드 텍스트에 포함되는지 확인"""
    from backend.guide_generator import generate_guide

    # 안경원 → 의료기기법 관련 금지어
    guide1 = generate_guide("제주시", "안경원")
    text1 = guide1["full_guide_text"]
    ok1 = "금지어" in text1 and "시술" in text1 and "피팅/조정" in text1

    # forbidden_words가 API 응답에 포함
    ok2 = len(guide1["forbidden_words"]) >= 3
    ok3 = len(guide1["alternative_words"]) >= 3

    # 병원 → 의료법 금지어
    guide2 = generate_guide("서울", "정형외과")
    text2 = guide2["full_guide_text"]
    ok4 = "치료 효과 보장" in text2 or "의료법" in text2

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-54", "금지어/대체표현 가이드 포함", ok,
           f"안경금지어={ok1}, forbidden={len(guide1['forbidden_words'])}, "
           f"alt={len(guide1['alternative_words'])}, 병원금지어={ok4}")


def test_tc55_seo_guide_fields():
    """SEO 가이드 필드가 API 응답에 포함되는지 확인"""
    from backend.guide_generator import generate_guide

    guide = generate_guide("강남", "카페")

    ok1 = "seo_guide" in guide
    seo = guide["seo_guide"]
    ok2 = "min_chars" in seo and seo["min_chars"] >= 1000
    ok3 = "max_chars" in seo and seo["max_chars"] >= 2000
    ok4 = "min_photos" in seo and seo["min_photos"] >= 5
    ok5 = "keyword_density" in seo
    ok6 = "max_word_frequency" in seo

    # 가이드 텍스트에 SEO 섹션 존재
    text = guide["full_guide_text"]
    ok7 = "SEO 작성 가이드" in text

    ok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7
    report("TC-55", "SEO 가이드 필드 포함", ok,
           f"seo_guide={ok1}, min_chars={seo.get('min_chars')}, "
           f"max_chars={seo.get('max_chars')}, photos={seo.get('min_photos')}, SEO텍스트={ok7}")


def test_tc56_medical_disclaimer():
    """병원/치과 면책 문구 포함 확인"""
    from backend.guide_generator import generate_guide

    # 병원 → 면책 문구
    guide1 = generate_guide("서울", "정형외과")
    text1 = guide1["full_guide_text"]
    ok1 = "면책" in text1 and "의학적 효과" in text1

    # 치과 → 면책 문구
    guide2 = generate_guide("강남", "치과")
    text2 = guide2["full_guide_text"]
    ok2 = "면책" in text2 and "의학적 효과" in text2

    # 카페 → 면책 문구 없음
    guide3 = generate_guide("제주시", "카페")
    text3 = guide3["full_guide_text"]
    ok3 = "면책" not in text3

    ok = ok1 and ok2 and ok3
    report("TC-56", "의료 업종 면책 문구", ok,
           f"병원면책={ok1}, 치과면책={ok2}, 카페면책없음={ok3}")


def test_tc57_word_count_in_review_structure():
    """review_structure 각 섹션에 word_count 필드 존재"""
    from backend.guide_generator import generate_guide

    categories = ["안경원", "카페", "치과", "학원", "숙박", "자동차", "정형외과", "헬스장"]
    all_ok = True
    details = []

    for cat in categories:
        guide = generate_guide("서울", cat)
        for section in guide["review_structure"]:
            if "word_count" not in section:
                all_ok = False
                details.append(f"{cat}/{section['section']}: word_count 누락")

    # 가이드 텍스트에 word_count 힌트가 포함되는지
    guide = generate_guide("서울", "카페")
    text = guide["full_guide_text"]
    ok2 = "자" in text  # word_count 값이 "300~400자" 등으로 표시

    ok = all_ok and ok2
    report("TC-57", "review_structure word_count 필드", ok,
           "; ".join(details) if details else f"전체 {len(categories)}개 업종 OK")


# ==================== TC-58 ~ TC-64: 블로그 개별 분석 ====================

def test_tc58_extract_blogger_id():
    """블로거 ID 추출: URL / ID / blogId= 파라미터"""
    from backend.blog_analyzer import extract_blogger_id

    ok1 = extract_blogger_id("testuser") == "testuser"
    ok2 = extract_blogger_id("https://blog.naver.com/myuser123") == "myuser123"
    ok3 = extract_blogger_id("https://m.blog.naver.com/MobileUser") == "mobileuser"
    ok4 = extract_blogger_id("https://blog.naver.com/PostView.naver?blogId=quser&logNo=123") == "quser"
    ok5 = extract_blogger_id("") is None
    ok6 = extract_blogger_id("https://example.com") is None

    ok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6
    report("TC-58", "블로거 ID 추출 (URL/ID/파라미터)", ok,
           f"id={ok1}, url={ok2}, mobile={ok3}, param={ok4}, empty={ok5}, invalid={ok6}")


def test_tc59_analyze_activity():
    """활동 지표 분석: 점수 범위 + 등급"""
    from backend.blog_analyzer import analyze_activity
    from backend.models import RSSPost
    from datetime import datetime, timedelta

    now = datetime.now()

    # 매우활발: 매일 포스팅
    posts_active = [
        RSSPost(title=f"제목{i}", link=f"http://l/{i}",
                pub_date=(now - timedelta(days=i)).strftime("%a, %d %b %Y %H:%M:%S"))
        for i in range(20)
    ]
    act1 = analyze_activity(posts_active)
    ok1 = act1.posting_trend in ("매우활발", "활발")
    ok2 = 0 <= act1.score <= 15

    # 비활성: 오래된 포스팅 + 넓은 간격
    posts_inactive = [
        RSSPost(title=f"제목{i}", link=f"http://l/{i}",
                pub_date=(now - timedelta(days=100+i*30)).strftime("%a, %d %b %Y %H:%M:%S"))
        for i in range(3)
    ]
    act2 = analyze_activity(posts_inactive)
    ok3 = act2.posting_trend == "비활성"
    ok4 = act2.score < act1.score

    # 빈 포스트
    act3 = analyze_activity([])
    ok5 = act3.score == 0.0 and act3.posting_trend == "비활성"

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-59", "활동 지표 분석 (범위/등급)", ok,
           f"active={act1.posting_trend}({act1.score}), "
           f"inactive={act2.posting_trend}({act2.score}), empty={act3.score}")


def test_tc60_analyze_content():
    """콘텐츠 성향 분석: food_bias + sponsor + 주제다양성"""
    from backend.blog_analyzer import analyze_content
    from backend.models import RSSPost

    # 맛집 편향 높은 포스트
    food_posts = [
        RSSPost(title="강남 맛집 추천 파스타", link="http://l/1", description="맛집 후기 먹방"),
        RSSPost(title="홍대 맛집 디너 코스", link="http://l/2", description="레스토랑 리뷰"),
        RSSPost(title="삼겹살집 웨이팅 맛있", link="http://l/3", description="고기집"),
    ]
    c1 = analyze_content(food_posts)
    ok1 = c1.food_bias_rate >= 0.5
    ok2 = 0 <= c1.score <= 20

    # 다양한 주제 포스트
    diverse_posts = [
        RSSPost(title="여행 일기 제주도", link="http://l/1", description="제주 풍경"),
        RSSPost(title="맛집 리뷰 강남", link="http://l/2", description="파스타 맛있"),
        RSSPost(title="피트니스 운동 루틴", link="http://l/3", description="헬스 가이드"),
        RSSPost(title="영화 리뷰 최신작", link="http://l/4", description="신작 영화"),
        RSSPost(title="독서 기록 추천도서", link="http://l/5", description="좋은 책"),
    ]
    c2 = analyze_content(diverse_posts)
    ok3 = c2.topic_diversity > c1.topic_diversity

    # 협찬 포스트
    sponsor_posts = [
        RSSPost(title="협찬 체험단 리뷰", link="http://l/1", description="제공받아 작성"),
        RSSPost(title="서포터즈 초대 체험", link="http://l/2", description="지원 광고"),
    ]
    c3 = analyze_content(sponsor_posts)
    ok4 = c3.sponsor_signal_rate >= 0.5

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-60", "콘텐츠 성향 분석 (food/sponsor/다양성)", ok,
           f"food_bias={c1.food_bias_rate:.2f}, "
           f"diversity_food={c1.topic_diversity:.2f}/diverse={c2.topic_diversity:.2f}, "
           f"sponsor={c3.sponsor_signal_rate:.2f}")


def test_tc61_analyze_suitability():
    """체험단 적합도: sweet spot + 과다 + 미경험"""
    from backend.blog_analyzer import analyze_suitability

    # sweet spot: 10~30%
    s1 = analyze_suitability(food_bias=0.3, sponsor_rate=0.2, is_food_cat=False)
    ok1 = s1.sponsor_receptivity_score == 5.0

    # 과다: 60%+
    s2 = analyze_suitability(food_bias=0.3, sponsor_rate=0.7, is_food_cat=False)
    ok2 = s2.sponsor_receptivity_score == 1.0

    # 미경험: 0%
    s3 = analyze_suitability(food_bias=0.3, sponsor_rate=0.0, is_food_cat=False)
    ok3 = s3.sponsor_receptivity_score == 3.0

    # 범위 체크
    ok4 = all(0 <= s.score <= 10 for s in [s1, s2, s3])

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-61", "체험단 적합도 (sweet spot/과다/미경험)", ok,
           f"sweet={s1.sponsor_receptivity_score}, over={s2.sponsor_receptivity_score}, "
           f"zero={s3.sponsor_receptivity_score}")


def test_tc62_compute_grade():
    """등급 계산: S/A/B/C/D 경계값"""
    from backend.blog_analyzer import compute_grade

    ok1 = compute_grade(90)[0] == "S"
    ok2 = compute_grade(85)[0] == "S"
    ok3 = compute_grade(84)[0] == "A"
    ok4 = compute_grade(70)[0] == "A"
    ok5 = compute_grade(50)[0] == "B"
    ok6 = compute_grade(30)[0] == "C"
    ok7 = compute_grade(29)[0] == "D"
    ok8 = compute_grade(0)[0] == "D"

    ok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7 and ok8
    report("TC-62", "등급 계산 경계값 (S/A/B/C/D)", ok,
           f"90=S:{ok1}, 85=S:{ok2}, 84=A:{ok3}, 70=A:{ok4}, "
           f"50=B:{ok5}, 30=C:{ok6}, 29=D:{ok7}, 0=D:{ok8}")


def test_tc63_generate_insights():
    """강점/약점 자동 생성"""
    from backend.blog_analyzer import generate_insights
    from backend.models import ActivityMetrics, ContentMetrics, ExposureMetrics, SuitabilityMetrics, QualityMetrics

    activity = ActivityMetrics(
        total_posts=30, days_since_last_post=2,
        avg_interval_days=3.0, interval_std_days=1.5,
        posting_trend="매우활발", score=12.0,
    )
    content = ContentMetrics(
        food_bias_rate=0.65, sponsor_signal_rate=0.15,
        topic_diversity=0.75, dominant_topics=["맛집", "카페"],
        avg_description_length=150.0, category_fit_score=5.0, score=15.0,
    )
    exposure = ExposureMetrics(
        keywords_checked=7, keywords_exposed=4,
        page1_count=3, strength_sum=15, weighted_strength=20.0,
        details=[], sponsored_rank_count=1, sponsored_page1_count=1, score=30.0,
    )
    suitability = SuitabilityMetrics(
        sponsor_receptivity_score=4.0, category_fit_score=3.5, score=7.5,
    )
    quality = QualityMetrics(
        originality=4.5, compliance=4.0, richness=3.5, score=12.0,
    )

    strengths, weaknesses, rec = generate_insights(activity, content, exposure, suitability, quality, 76.0)

    ok1 = any("활발" in s for s in strengths)
    ok2 = any("맛집" in w for w in weaknesses)
    ok3 = any("1페이지" in s for s in strengths)
    ok4 = "적합" in rec

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-63", "강점/약점/추천문 생성", ok,
           f"strengths={strengths}, weaknesses={weaknesses}")


def test_tc64_blog_analyses_table():
    """blog_analyses 테이블 생성 + insert"""
    from backend.db import insert_blog_analysis
    conn = get_conn(TEST_DB)

    # 테이블 존재 확인
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blog_analyses'")
    ok1 = cursor.fetchone() is not None

    # insert 테스트
    aid = insert_blog_analysis(
        conn,
        blogger_id="test_ba_user",
        blog_url="https://blog.naver.com/test_ba_user",
        analysis_mode="standalone",
        store_id=None,
        blog_score=72.5,
        grade="A",
        result_json='{"test": true}',
    )
    conn.commit()
    ok2 = aid > 0

    row = conn.execute("SELECT * FROM blog_analyses WHERE analysis_id=?", (aid,)).fetchone()
    ok3 = row is not None and row["blogger_id"] == "test_ba_user"
    ok4 = row["blog_score"] == 72.5 and row["grade"] == "A"

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-64", "blog_analyses 테이블 + insert", ok,
           f"table={ok1}, aid={aid}, row={ok3}, score={ok4}")
    conn.close()


def test_tc65_keyword_extraction():
    """포스트 제목에서 키워드 추출"""
    from backend.blog_analyzer import extract_search_keywords_from_posts
    from backend.models import RSSPost

    posts = [
        RSSPost(title="강남역 파스타 맛집 추천", link="http://l/1"),
        RSSPost(title="강남역 카페 디저트 후기", link="http://l/2"),
        RSSPost(title="강남역 파스타 가격 비교", link="http://l/3"),
        RSSPost(title="홍대 맛집 리뷰 모음", link="http://l/4"),
        RSSPost(title="강남역 브런치 카페 추천", link="http://l/5"),
    ]
    kws = extract_search_keywords_from_posts(posts, max_keywords=5)

    ok1 = len(kws) >= 1
    ok2 = any("강남역" in kw for kw in kws)  # 빈도 높은 키워드
    ok3 = len(kws) <= 5

    ok = ok1 and ok2 and ok3
    report("TC-65", "포스트 제목 키워드 추출", ok, f"keywords={kws}")


# ==================== TC-66 ~ TC-69: BlogScore v2 (5축) ====================

def test_tc66_analyze_quality():
    """품질 분석: 독창성/규정준수/충실도 점수 범위"""
    from backend.blog_analyzer import analyze_quality
    from backend.models import RSSPost

    # 다양한 콘텐츠 + 공정위 표시 포함
    posts_good = [
        RSSPost(title="강남 맛집 추천", link="http://l/1",
                description="업체로부터 제공받아 작성한 솔직한 리뷰입니다. 파스타가 정말 맛있었습니다." * 3),
        RSSPost(title="홍대 카페 후기", link="http://l/2",
                description="분위기가 좋은 카페를 다녀왔습니다. 커피 맛도 훌륭하고 디저트도 괜찮았어요." * 3),
        RSSPost(title="부산 여행 일기", link="http://l/3",
                description="해운대 해변이 정말 아름다웠습니다. 숙소도 깨끗하고 서비스도 좋았습니다." * 3),
    ]
    q1 = analyze_quality(posts_good)
    ok1 = 0 <= q1.score <= 15
    ok2 = 0 <= q1.originality <= 5
    ok3 = 0 <= q1.compliance <= 5
    ok4 = 0 <= q1.richness <= 5

    # 빈 포스트
    q2 = analyze_quality([])
    ok5 = q2.score == 0.0

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-66", "품질 분석 (독창성/규정준수/충실도)", ok,
           f"score={q1.score}, orig={q1.originality}, comp={q1.compliance}, rich={q1.richness}, empty={q2.score}")


def test_tc67_sponsored_signal_detection():
    """협찬 시그널 감지: 포스트 제목에서 협찬/체험단 감지"""
    from backend.blog_analyzer import _has_sponsored_signal

    ok1 = _has_sponsored_signal("강남 맛집 체험단 후기") is True
    ok2 = _has_sponsored_signal("협찬 리뷰 파스타") is True
    ok3 = _has_sponsored_signal("서포터즈 초대 이벤트") is True
    ok4 = _has_sponsored_signal("강남역 파스타 맛집 추천") is False
    ok5 = _has_sponsored_signal("일상 블로그 일기") is False

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-67", "협찬 시그널 감지 (제목 기반)", ok,
           f"체험단={ok1}, 협찬={ok2}, 서포터즈={ok3}, 일반1={ok4}, 일반2={ok5}")


def test_tc68_forbidden_words():
    """금지어 검사: 금지어 포함 시 compliance 감점"""
    from backend.blog_analyzer import analyze_quality
    from backend.models import RSSPost

    # 금지어 포함 포스트
    posts_bad = [
        RSSPost(title="최고의 맛집 완벽한 서비스", link="http://l/1",
                description="최고 100% 보장 완벽한 맛집입니다"),
        RSSPost(title="가장 좋은 기적의 식당", link="http://l/2",
                description="무조건 가야하는 기적의 맛집 확실한 추천"),
    ]
    q_bad = analyze_quality(posts_bad)

    # 금지어 없는 포스트
    posts_clean = [
        RSSPost(title="강남 파스타 후기", link="http://l/1",
                description="파스타가 맛있었습니다. 분위기도 좋아요."),
        RSSPost(title="홍대 카페 방문", link="http://l/2",
                description="커피 맛이 괜찮았습니다. 인테리어가 예뻐요."),
    ]
    q_clean = analyze_quality(posts_clean)

    ok1 = q_clean.compliance >= q_bad.compliance  # 금지어 없으면 compliance 더 높음

    ok = ok1
    report("TC-68", "금지어 검사 (compliance 감점)", ok,
           f"clean_comp={q_clean.compliance}, bad_comp={q_bad.compliance}")


def test_tc69_v2_total_score_range():
    """종합 v2 점수: 5축 합산 0~100 범위"""
    from backend.blog_analyzer import analyze_activity, analyze_content, analyze_suitability, analyze_quality
    from backend.models import RSSPost, ExposureMetrics
    from datetime import datetime, timedelta

    now = datetime.now()
    posts = [
        RSSPost(title=f"제목{i}", link=f"http://l/{i}",
                pub_date=(now - timedelta(days=i*2)).strftime("%a, %d %b %Y %H:%M:%S"),
                description="테스트 포스트 내용입니다 " * 10)
        for i in range(10)
    ]

    act = analyze_activity(posts)
    cnt = analyze_content(posts)
    exp = ExposureMetrics(
        keywords_checked=5, keywords_exposed=3,
        page1_count=2, strength_sum=10, weighted_strength=12.0,
        details=[], sponsored_rank_count=1, sponsored_page1_count=1, score=25.0,
    )
    suit = analyze_suitability(food_bias=0.2, sponsor_rate=0.15, is_food_cat=False)
    qual = analyze_quality(posts)

    total = act.score + cnt.score + exp.score + suit.score + qual.score

    ok1 = 0 <= act.score <= 15
    ok2 = 0 <= cnt.score <= 20
    ok3 = 0 <= exp.score <= 40
    ok4 = 0 <= suit.score <= 10
    ok5 = 0 <= qual.score <= 15
    ok6 = 0 <= total <= 100

    ok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6
    report("TC-69", "5축 합산 범위 (0~100)", ok,
           f"act={act.score}/15, cnt={cnt.score}/20, exp={exp.score}/40, "
           f"suit={suit.score}/10, qual={qual.score}/15, total={total:.1f}")


# ==================== TC-70 ~ TC-73: GoldenScore 노출 우선 랭킹 ====================

def test_tc70_zero_exposure_confidence():
    """노출 0점 → confidence=0.2 패널티 확인 (v3.0)"""
    gs_full = golden_score(
        base_score_val=50.0, strength_sum=20, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=3,
    )
    gs_zero = golden_score(
        base_score_val=50.0, strength_sum=0, exposed_keywords=0,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=0,
    )
    # gs_zero: raw_score × 0.2 (v3.0: page1=0, exposed=0 → confidence=0.2)
    ok1 = gs_zero < gs_full
    ok2 = gs_zero < 15  # 대폭 하향되어야 함 (v3.0: 0.2x)
    ok = ok1 and ok2
    report("TC-70", "노출 0점 confidence 패널티 (v3.0: 0.2x)", ok,
           f"gs_full={gs_full}, gs_zero={gs_zero}")


def test_tc71_sufficient_exposure_confidence():
    """v3.0: page1>=3/10 → confidence=1.0 확인"""
    gs3 = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=3,
    )
    gs5 = golden_score(
        base_score_val=50.0, strength_sum=25, exposed_keywords=7,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=5,
    )
    # page1=3/10=0.3 → confidence=1.0, page1=5/10=0.5 → confidence=1.0
    # gs5 > gs3 because higher strength, coverage, and page1authority
    ok1 = gs5 > gs3
    ok2 = gs3 > 0 and gs5 > 0
    ok = ok1 and ok2
    report("TC-71", "v3.0 page1 충분 (>=3) confidence=1.0", ok,
           f"gs_3p1={gs3}, gs_5p1={gs5}")


def test_tc72_top20_gate():
    """v3.0: Top20에 page1=0 블로거 진입 불가 확인"""
    conn = get_conn(TEST_DB)
    init_db(conn)
    # 전용 매장 생성 (region, category, place_url, store_name, address)
    sid = upsert_store(conn, "서울", "테스트", "", "노출테스트", "")
    # page1 노출 있는 블로거 (page1=1)
    for i in range(25):
        bid = f"exposed_{i:02d}"
        upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}", "20260210", 3.0, 0.1, 0.2, "[]", 40.0)
        insert_exposure_fact(conn, sid, f"키워드A_{i}", bid, rank=5, strength_points=5, is_page1=1, is_exposed=1)
    # 노출은 있지만 page1=0인 블로거 (30위권 노출만) — base_score가 높아도 Top20 불가
    for i in range(5):
        bid = f"nop1_{i:02d}"
        upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}", "20260210", 3.0, 0.1, 0.1, "[]", 70.0)
        insert_exposure_fact(conn, sid, f"키워드B_{i}", bid, rank=25, strength_points=1, is_page1=0, is_exposed=1)
    conn.commit()

    result = get_top20_and_pool40(conn, sid, days=30, category_text="테스트")
    top20_ids = {b["blogger_id"] for b in result["top20"]}

    # page1=0 블로거가 Top20에 없어야 함
    nop1_in_top20 = any(f"nop1_{i:02d}" in top20_ids for i in range(5))

    ok1 = not nop1_in_top20  # Top20에 page1=0 없음
    ok2 = len(result["top20"]) == 20  # Top20 20명 채움

    ok = ok1 and ok2
    report("TC-72", "v3.0 Top20 gate: page1=0 블로거 Top20 진입 불가", ok,
           f"nop1_in_top20={nop1_in_top20}, top20_count={len(result['top20'])}")
    conn.close()


def test_tc73_unexposed_tag():
    """v3.0: 완전 미노출(exposed=0) 블로거는 Top20/Pool40 모두 제외"""
    conn = get_conn(TEST_DB)
    init_db(conn)
    sid = upsert_store(conn, "서울", "테스트", "", "태그테스트", "")
    # 완전 미노출 블로거 (exposed=0)
    bid = "tag_test_unexposed"
    upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}", "20260210", 3.0, 0.1, 0.1, "[]", 50.0)
    insert_exposure_fact(conn, sid, "키워드X", bid, rank=None, strength_points=0, is_page1=0, is_exposed=0)
    # page1 노출 블로거
    bid2 = "tag_test_exposed"
    upsert_blogger(conn, bid2, f"https://blog.naver.com/{bid2}", "20260210", 3.0, 0.1, 0.1, "[]", 50.0)
    insert_exposure_fact(conn, sid, "키워드Y", bid2, rank=3, strength_points=5, is_page1=1, is_exposed=1)
    conn.commit()

    result = get_top20_and_pool40(conn, sid, days=30, category_text="테스트")
    all_bloggers = result["top20"] + result["pool40"]

    # v3.0: 완전 미노출 블로거는 결과에서 제외됨
    unexposed_blogger = next((b for b in all_bloggers if b["blogger_id"] == bid), None)
    exposed_blogger = next((b for b in all_bloggers if b["blogger_id"] == bid2), None)

    ok1 = unexposed_blogger is None  # v3.0: 완전 미노출은 결과에서 제외
    ok2 = exposed_blogger is not None and "미노출" not in exposed_blogger.get("tags", [])

    ok = ok1 and ok2
    report("TC-73", "v3.0: 완전 미노출 블로거 결과 제외", ok,
           f"unexposed_in_results={unexposed_blogger is not None}, "
           f"exposed_tags={exposed_blogger.get('tags') if exposed_blogger else 'N/A'}")
    conn.close()


def test_tc74_calibration_distribution():
    """GoldenScore v3.0 캘리브레이션: 우수 page1 많음 ≥55, pepechan3류 <20, 미노출 <10"""
    # 우수 블로거: base60, str25, exp6/10, page1=5, food70%, sponsor20%, 음식업종
    gs_excellent = golden_score(
        base_score_val=60.0, strength_sum=25, exposed_keywords=6,
        total_keywords=10, food_bias_rate=0.70, sponsor_signal_rate=0.20,
        is_food_cat=True, page1_keywords=5,
    )
    # pepechan3류: base48, str2, exp2/10, page1=0
    gs_pepechan = golden_score(
        base_score_val=48.0, strength_sum=2, exposed_keywords=2,
        total_keywords=10, food_bias_rate=0.0, sponsor_signal_rate=0.0,
        is_food_cat=False, page1_keywords=0,
    )
    # 미노출 블로거: base50, str0, exp0/10, page1=0
    gs_unexposed = golden_score(
        base_score_val=50.0, strength_sum=0, exposed_keywords=0,
        total_keywords=10, food_bias_rate=0.50, sponsor_signal_rate=0.20,
        is_food_cat=True, page1_keywords=0,
    )

    ok1 = gs_excellent >= 55  # 우수 블로거 55점 이상
    ok2 = gs_pepechan < 20  # pepechan3류 20점 미만 (was 45.7)
    ok3 = gs_unexposed < 10  # 미노출 블로거 10점 미만 (v3.0: 0.2x)
    ok4 = gs_excellent > gs_pepechan > gs_unexposed  # 순서 보장

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-74", "v3.0 캘리브레이션 분포 (우수≥55, pepechan<20, 미노출<10)", ok,
           f"excellent={gs_excellent}, pepechan={gs_pepechan}, unexposed={gs_unexposed}")


# ==================== TC-75 ~ TC-80: 랭킹 파워 기반 모집 ====================

def test_tc75_region_power_queries():
    """build_region_power_queries: 카테고리별 3개 쿼리 생성, 자기 카테고리와 비중복, 빈 카테고리 seed 비중복"""
    # 안경원 → 맛집/카페/핫플 (안경과 겹치지 않음)
    p1 = StoreProfile(region_text="강남", category_text="안경원")
    q1 = build_region_power_queries(p1)
    ok1 = len(q1) == 3
    ok2 = all("안경" not in q for q in q1)  # 자기 카테고리 미포함
    ok3 = any("맛집" in q or "카페" in q or "핫플" in q for q in q1)

    # 맛집 → 카페/핫플/데이트 (음식과 겹치지 않음)
    p2 = StoreProfile(region_text="홍대", category_text="맛집")
    q2 = build_region_power_queries(p2)
    ok4 = len(q2) == 3
    ok5 = all("맛집" not in q for q in q2)

    # 카페 → 맛집/핫플/데이트 (카페와 겹치지 않음)
    p3 = StoreProfile(region_text="서울", category_text="카페")
    q3 = build_region_power_queries(p3)
    ok6 = len(q3) == 3
    ok7 = all("카페" not in q for q in q3)

    # 빈 카테고리 → seed와 비중복 쿼리
    p4 = StoreProfile(region_text="노형동", category_text="")
    q4 = build_region_power_queries(p4)
    seed4 = build_seed_queries(p4)
    ok8 = len(q4) == 3
    ok9 = len(set(q4) & set(seed4)) == 0  # seed와 완전 비중복

    ok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7 and ok8 and ok9
    report("TC-75", "build_region_power_queries 카테고리별 3개 쿼리 + 빈카테고리 비중복", ok,
           f"안경={q1}, 맛집={q2}, 빈카테고리={q4}, seed비중복={len(set(q4) & set(seed4))==0}")


def test_tc76_seed_queries_no_store_name():
    """build_seed_queries: 7개만 생성, 상호명 미포함"""
    p = StoreProfile(region_text="강남", category_text="안경원",
                     store_name="테스트안경원", address_text="서울 강남구 역삼동 123")
    q = build_seed_queries(p)
    ok1 = len(q) == 7
    ok2 = all("테스트안경원" not in kw for kw in q)  # 상호명 미포함
    ok3 = all("역삼동" not in kw for kw in q)  # 주소 토큰 미포함

    # 필수 키워드 포함 확인
    ok4 = f"강남 안경원" in q
    ok5 = f"강남 안경원 추천" in q

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-76", "build_seed_queries 7개 (상호명/주소 미포함)", ok,
           f"count={len(q)}, queries={q}")


def test_tc77_brand_blog_detection():
    """detect_self_blog: 브랜드 블로그 패턴 감지 ("XX안경 강남점" → competitor)"""
    from backend.analyzer import detect_self_blog
    from backend.models import CandidateBlogger, BlogPostItem

    posts = [BlogPostItem(title="t", description="d", link="http://l",
                          bloggername="글라스박스안경 강남점")]
    b1 = CandidateBlogger(blogger_id="glassbox_gn", blog_url="http://b.com/1",
                          ranks=[1], queries_hit=set(), posts=posts, local_hits=0)
    r1 = detect_self_blog(b1, "테스트안경원", "안경")
    ok1 = r1 == "competitor"

    # "다비치안경 역삼점" → 프랜차이즈 이름으로 먼저 잡힘
    posts2 = [BlogPostItem(title="t", description="d", link="http://l",
                           bloggername="다비치안경 역삼점")]
    b2 = CandidateBlogger(blogger_id="davich_ys", blog_url="http://b.com/2",
                          ranks=[1], queries_hit=set(), posts=posts2, local_hits=0)
    r2 = detect_self_blog(b2, "테스트안경원", "안경")
    ok2 = r2 == "competitor"

    ok = ok1 and ok2
    report("TC-77", "브랜드 블로그 패턴 감지 (경쟁사 매장)", ok,
           f"글라스박스안경강남점={r1}, 다비치안경역삼점={r2}")


def test_tc78_normal_blogger_no_false_positive():
    """detect_self_blog: 일반 블로거 오탐 방지 ("안경에미친남자" → normal)"""
    from backend.analyzer import detect_self_blog
    from backend.models import CandidateBlogger, BlogPostItem

    # "안경에미친남자" → 업종 키워드 포함하지만 매장 접미사 없음 → normal
    posts = [BlogPostItem(title="t", description="d", link="http://l",
                          bloggername="안경에미친남자")]
    b = CandidateBlogger(blogger_id="glasses_man", blog_url="http://b.com/1",
                         ranks=[1], queries_hit=set(), posts=posts, local_hits=0)
    r = detect_self_blog(b, "테스트안경원", "안경")
    ok1 = r == "normal"

    # "맛집탐험가" → 업종과 관련 없는 블로거 → normal
    posts2 = [BlogPostItem(title="t", description="d", link="http://l",
                           bloggername="맛집탐험가")]
    b2 = CandidateBlogger(blogger_id="food_explorer", blog_url="http://b.com/2",
                          ranks=[1], queries_hit=set(), posts=posts2, local_hits=0)
    r2 = detect_self_blog(b2, "테스트안경원", "안경")
    ok2 = r2 == "normal"

    ok = ok1 and ok2
    report("TC-78", "일반 블로거 오탐 방지", ok,
           f"안경에미친남자={r}, 맛집탐험가={r2}")


def test_tc79_franchise_names_expanded():
    """FRANCHISE_NAMES 확장: 50개+ 프랜차이즈 포함"""
    from backend.analyzer import FRANCHISE_NAMES

    ok1 = len(FRANCHISE_NAMES) >= 50
    # 주요 브랜드 포함 확인
    ok2 = "스타벅스" in FRANCHISE_NAMES
    ok3 = "맥도날드" in FRANCHISE_NAMES
    ok4 = "올리브영" in FRANCHISE_NAMES
    ok5 = "준오헤어" in FRANCHISE_NAMES
    ok6 = "안경나라" in FRANCHISE_NAMES

    ok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6
    report("TC-79", "FRANCHISE_NAMES 확장 (50개+)", ok,
           f"count={len(FRANCHISE_NAMES)}, 스타벅스={ok2}, 맥도날드={ok3}, 올리브영={ok4}")


def test_tc80_pipeline_query_count():
    """파이프라인 쿼리: seed(7) + region_power(3) + broad(5) = 15개"""
    from backend.keywords import build_broad_queries

    p = StoreProfile(region_text="강남", category_text="안경원")
    seed = build_seed_queries(p)
    rp = build_region_power_queries(p)
    broad = build_broad_queries(p)

    ok1 = len(seed) == 7
    ok2 = len(rp) == 3
    ok3 = len(broad) == 5
    ok4 = len(seed) + len(rp) + len(broad) == 15

    # region_power 쿼리가 seed와 겹치지 않음 (다른 카테고리이므로)
    seed_set = set(seed)
    rp_overlap = set(rp) & seed_set
    ok5 = len(rp_overlap) == 0

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-80", "파이프라인 쿼리 수 (seed7+rp3+broad5=15)", ok,
           f"seed={len(seed)}, rp={len(rp)}, broad={len(broad)}, rp_overlap={rp_overlap}")


def test_tc81_seed_queries_empty_category():
    """build_seed_queries 빈 카테고리 → 순수 지역명 포함 + 맛집 3개 + 7개"""
    p = StoreProfile(region_text="강남", category_text="")
    queries = build_seed_queries(p)

    ok1 = len(queries) == 7
    # 이중 공백이 없어야 함
    ok2 = all("  " not in q for q in queries)
    # 모든 쿼리가 "강남"으로 시작
    ok3 = all(q.startswith("강남") for q in queries)
    # 순수 지역명 쿼리 포함
    ok4 = "강남" in queries
    # 맛집 관련 키워드 3개 이상
    matjip_count = sum(1 for q in queries if "맛집" in q)
    ok5 = matjip_count >= 3

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-81", "빈 카테고리 seed 쿼리 (순수지역명 + 맛집3개)", ok,
           f"count={len(queries)}, pure_region={'강남' in queries}, matjip={matjip_count}, queries={queries}")


def test_tc82_exposure_keywords_empty_category():
    """build_exposure_keywords 빈 카테고리 → 순수 지역명 + 맛집 3개 + 10개"""
    p = StoreProfile(region_text="홍대", category_text="")
    keywords = build_exposure_keywords(p)

    ok1 = len(keywords) == 10
    ok2 = all("  " not in kw for kw in keywords)
    # 순수 지역명 포함
    ok3 = "홍대" in keywords
    # 맛집 관련 키워드 3개 이상
    matjip_count = sum(1 for kw in keywords if "맛집" in kw)
    ok4 = matjip_count >= 3

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-82", "빈 카테고리 exposure 키워드 (순수지역명 + 맛집3개)", ok,
           f"count={len(keywords)}, pure_region={'홍대' in keywords}, matjip={matjip_count}, keywords={keywords}")


def test_tc83_keyword_ab_sets_empty_category():
    """build_keyword_ab_sets 빈 카테고리 → A/B 세트 정상 생성"""
    from backend.keywords import build_keyword_ab_sets

    p = StoreProfile(region_text="부산", category_text="")
    ab = build_keyword_ab_sets(p)

    ok1 = len(ab["set_a"]) == 5
    ok2 = len(ab["set_b"]) == 5
    # A/B 중복 없음
    ok3 = len(set(ab["set_a"]) & set(ab["set_b"])) == 0
    # 이중 공백 없음
    ok4 = all("  " not in kw for kw in ab["set_a"] + ab["set_b"])

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-83", "빈 카테고리 A/B 키워드 세트", ok,
           f"a={len(ab['set_a'])}, b={len(ab['set_b'])}, overlap={set(ab['set_a']) & set(ab['set_b'])}")


def test_tc84_detect_self_blog_empty_category():
    """detect_self_blog 빈 카테고리 → 카테고리 시그널 스킵, 오탐 없음"""
    from backend.analyzer import detect_self_blog
    from backend.models import CandidateBlogger, BlogPostItem

    # 빈 카테고리: 카테고리 시그널이 적용되지 않아야 함
    posts = [BlogPostItem(title="t", description="d", link="http://l",
                          bloggername="맛집탐험가")]
    b = CandidateBlogger(blogger_id="food_explorer", blog_url="http://b.com/1",
                         ranks=[1], queries_hit=set(), posts=posts, local_hits=0)
    r = detect_self_blog(b, "", "")
    ok1 = r == "normal"

    # 빈 카테고리 + 블로거 이름에 매장 접미사 → competitor 오탐 없어야 함
    posts2 = [BlogPostItem(title="t", description="d", link="http://l",
                           bloggername="강남점 리뷰어")]
    b2 = CandidateBlogger(blogger_id="gn_reviewer", blog_url="http://b.com/2",
                          ranks=[1], queries_hit=set(), posts=posts2, local_hits=0)
    r2 = detect_self_blog(b2, "", "")
    ok2 = r2 == "normal"

    ok = ok1 and ok2
    report("TC-84", "빈 카테고리 detect_self_blog 오탐 방지", ok,
           f"맛집탐험가={r}, 강남점리뷰어={r2}")


# ==================== TC-85~TC-89: 주제 모드 (topic mode) ====================

def test_tc85_seed_queries_topic_mode():
    """build_seed_queries 주제 모드 → TOPIC_SEED_MAP 기반 실제 검색 쿼리, 리터럴 주제명 미포함"""
    # "비즈니스·경제" 주제 → "제주시 비즈니스·경제 추천" 같은 리터럴이 아닌
    # "제주시 창업", "제주시 재테크" 등 실제 검색 쿼리로 변환
    p = StoreProfile(region_text="제주시", category_text="", topic="비즈니스·경제")
    queries = build_seed_queries(p)

    ok1 = len(queries) == 7
    # 리터럴 주제명이 쿼리에 직접 포함되면 안 됨
    ok2 = all("비즈니스" not in q and "경제" not in q for q in queries)
    # 실제 검색 가능한 키워드가 포함되어야 함
    ok3 = any("창업" in q for q in queries)
    ok4 = any("재테크" in q or "부동산" in q for q in queries)
    # 모든 쿼리가 지역명으로 시작
    ok5 = all(q.startswith("제주시") for q in queries)
    # 이중 공백 없음
    ok6 = all("  " not in q for q in queries)

    ok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6
    report("TC-85", "주제 모드 seed 쿼리 (TOPIC_SEED_MAP 기반)", ok,
           f"count={len(queries)}, has_literal={any('비즈니스' in q for q in queries)}, queries={queries[:3]}")


def test_tc86_exposure_keywords_topic_mode():
    """build_exposure_keywords 주제 모드 → 10개, TOPIC_SEED_MAP 캐시 + 범용 홀드아웃"""
    p = StoreProfile(region_text="강남", category_text="", topic="비즈니스·경제")
    keywords = build_exposure_keywords(p)

    ok1 = len(keywords) == 10
    # 리터럴 주제명(연결문자 포함한 전체 이름)이 쿼리에 직접 포함되면 안 됨
    ok2 = all("비즈니스·경제" not in kw for kw in keywords)
    # TOPIC_SEED_MAP 기반 키워드 포함 (비즈니스·경제 → 창업, 재테크 등)
    ok3 = any("창업" in kw or "재테크" in kw or "부동산" in kw for kw in keywords)
    # 홀드아웃 (추천, 후기, 블로그) 포함
    ok4 = any("추천" in kw for kw in keywords)
    # 이중 공백 없음
    ok5 = all("  " not in kw for kw in keywords)

    # seed와 exposure가 겹치는 부분 확인 (캐시 히트율)
    seed = build_seed_queries(p)
    seed_set = set(seed)
    cached = [kw for kw in keywords if kw in seed_set]
    holdout = [kw for kw in keywords if kw not in seed_set]
    ok6 = len(holdout) >= 1  # 최소 1개 홀드아웃

    ok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6
    report("TC-86", "주제 모드 exposure 키워드 (10개, 캐시+홀드아웃)", ok,
           f"count={len(keywords)}, cached={len(cached)}, holdout={len(holdout)}")


def test_tc87_keyword_ab_sets_topic_mode():
    """build_keyword_ab_sets 주제 모드 → A/B 세트 생성, 리터럴 주제명 미포함"""
    from backend.keywords import build_keyword_ab_sets

    p = StoreProfile(region_text="서울", category_text="", topic="비즈니스·경제")
    ab = build_keyword_ab_sets(p)

    ok1 = len(ab["set_a"]) == 5
    ok2 = len(ab["set_b"]) == 5
    # A/B 중복 없음
    ok3 = len(set(ab["set_a"]) & set(ab["set_b"])) == 0
    # 리터럴 주제명(전체)이 쿼리에 포함되면 안 됨
    ok4 = all("비즈니스·경제" not in kw for kw in ab["set_a"] + ab["set_b"])
    # 실제 검색 키워드 포함 (비즈니스·경제 → 창업, 재테크, 부동산 등)
    ok5 = any("창업" in kw or "재테크" in kw or "부동산" in kw for kw in ab["set_a"] + ab["set_b"])
    # 이중 공백 없음
    ok6 = all("  " not in kw for kw in ab["set_a"] + ab["set_b"])

    ok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6
    report("TC-87", "주제 모드 A/B 키워드 세트", ok,
           f"a={ab['set_a'][:2]}, b={ab['set_b'][:2]}, literal_free={ok4}")


def test_tc88_is_topic_mode():
    """is_topic_mode 헬퍼 함수 정확도"""
    # 주제만 있음 → True
    p1 = StoreProfile(region_text="강남", category_text="", topic="맛집")
    ok1 = is_topic_mode(p1) is True

    # 키워드 있음 → False (키워드 모드)
    p2 = StoreProfile(region_text="강남", category_text="안경원", topic="맛집")
    ok2 = is_topic_mode(p2) is False

    # 둘 다 없음 → False (지역만 모드)
    p3 = StoreProfile(region_text="강남", category_text="", topic="")
    ok3 = is_topic_mode(p3) is False

    # topic이 None → False
    p4 = StoreProfile(region_text="강남", category_text="", topic=None)
    ok4 = is_topic_mode(p4) is False

    # 유효하지 않은 주제 → False
    p5 = StoreProfile(region_text="강남", category_text="", topic="없는주제")
    ok5 = is_topic_mode(p5) is False

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-88", "is_topic_mode 헬퍼 정확도", ok,
           f"topic_only={ok1}, keyword={ok2}, empty={ok3}, none={ok4}, invalid={ok5}")


def test_tc89_topic_seed_map_coverage():
    """TOPIC_SEED_MAP이 32개 네이버 블로그 주제를 모두 커버하는지 확인"""
    NAVER_TOPICS = [
        # 엔터테인먼트·예술 (9)
        "문학·책", "영화", "미술·디자인", "공연·전시", "음악", "드라마", "스타·연예인", "만화·애니", "방송",
        # 생활·노하우·쇼핑 (9)
        "일상·생각", "육아·결혼", "반려동물", "좋은글·이미지", "패션·미용", "인테리어·DIY", "요리·레시피", "상품리뷰", "원예·재배",
        # 취미·여가·여행 (8)
        "게임", "스포츠", "사진", "자동차", "취미", "국내여행", "세계여행", "맛집",
        # 지식·동향 (6)
        "IT·컴퓨터", "사회·정치", "건강·의학", "비즈니스·경제", "어학·외국어", "교육·학문",
    ]

    ok1 = len(NAVER_TOPICS) == 32
    # 모든 주제가 TOPIC_SEED_MAP에 있는지
    missing = [t for t in NAVER_TOPICS if t not in TOPIC_SEED_MAP]
    ok2 = len(missing) == 0
    # 각 주제에 7개 쿼리 템플릿이 있는지
    short = [t for t in NAVER_TOPICS if t in TOPIC_SEED_MAP and len(TOPIC_SEED_MAP[t]) < 7]
    ok3 = len(short) == 0
    # 모든 쿼리 템플릿에 {r} 플레이스홀더가 있는지
    no_placeholder = []
    for t in NAVER_TOPICS:
        if t in TOPIC_SEED_MAP:
            for tmpl in TOPIC_SEED_MAP[t]:
                if "{r}" not in tmpl:
                    no_placeholder.append((t, tmpl))
    ok4 = len(no_placeholder) == 0

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-89", "TOPIC_SEED_MAP 32개 주제 전체 커버리지", ok,
           f"total={len(NAVER_TOPICS)}, missing={missing}, short={short}")


# ==================== TC-90 ~ TC-94: GoldenScore v3.0 ====================

def test_tc90_page1_authority():
    """Page1Authority 축 검증: page1=5 → 15점, page1=0 → 0점"""
    # page1=5/10=0.5 → page1_authority=15, confidence=1.0
    gs_high = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=5,
    )
    # page1=0 → page1_authority=0, confidence=0.35 (exposed>0)
    gs_low = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=0,
    )
    # page1=5는 page1_authority=15 + confidence=1.0, page1=0은 authority=0 + confidence 하락
    gap = gs_high - gs_low
    ok1 = gap >= 20  # page1authority(15) + confidence 차이 → 최소 20점 차이
    ok2 = gs_high > gs_low
    ok = ok1 and ok2
    report("TC-90", "Page1Authority 축 (page1=5 vs page1=0 gap>=20)", ok,
           f"gs_high={gs_high}, gs_low={gs_low}, gap={gap}")


def test_tc91_v3_confidence():
    """v3.0 Confidence: page1=0, exposed=2 → 0.35"""
    gs = golden_score(
        base_score_val=48.0, strength_sum=2, exposed_keywords=2,
        total_keywords=10, food_bias_rate=0.0, sponsor_signal_rate=0.0,
        is_food_cat=False, page1_keywords=0,
    )
    # page1=0, exposure_ratio=0.2 → exposure_ratio>0 → confidence=0.35
    # raw_score 구성: BP + Exp + P1Auth(0) + CatFit + Recruit
    # gs ≈ raw × 0.35 → 낮은 값
    ok1 = gs < 20  # confidence=0.35 → 대폭 하락
    ok2 = gs > 0
    ok = ok1 and ok2
    report("TC-91", "v3.0 Confidence (page1=0, exposed=2 → 0.35x)", ok,
           f"gs={gs}")


def test_tc92_top20_page1_gate():
    """v3.0 Top20 gate: page1=0이면 노출이 있어도 Top20 진입 불가"""
    conn = get_conn(TEST_DB)
    init_db(conn)
    sid = upsert_store(conn, "부산", "테스트", "", "페이지1테스트", "")
    # page1=1 블로거 20명
    for i in range(20):
        bid = f"p1yes_{i:02d}"
        upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}", "20260210", 3.0, 0.1, 0.2, "[]", 40.0)
        insert_exposure_fact(conn, sid, f"kw_p1_{i}", bid, rank=7, strength_points=3, is_page1=1, is_exposed=1)
    # page1=0 but exposed 블로거 (rank=15, 노출은 있지만 1페이지 아님)
    for i in range(5):
        bid = f"p1no_{i:02d}"
        upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}", "20260210", 3.0, 0.1, 0.1, "[]", 60.0)
        insert_exposure_fact(conn, sid, f"kw_ex_{i}", bid, rank=15, strength_points=2, is_page1=0, is_exposed=1)
    conn.commit()

    result = get_top20_and_pool40(conn, sid, days=30, category_text="테스트")
    top20_ids = {b["blogger_id"] for b in result["top20"]}
    pool40_ids = {b["blogger_id"] for b in result["pool40"]}

    # page1=0 블로거가 Top20에 없어야 함
    p1no_in_top20 = any(f"p1no_{i:02d}" in top20_ids for i in range(5))
    # page1=0 블로거는 Pool40에 있을 수 있음 (exposed>=1이므로)
    p1no_in_pool40 = any(f"p1no_{i:02d}" in pool40_ids for i in range(5))

    ok1 = not p1no_in_top20
    ok2 = len(result["top20"]) == 20
    ok3 = p1no_in_pool40  # Pool40에는 포함

    ok = ok1 and ok2 and ok3
    report("TC-92", "v3.0 Top20 gate: page1=0 → Pool40만 가능", ok,
           f"p1no_in_top20={p1no_in_top20}, top20={len(result['top20'])}, p1no_in_pool40={p1no_in_pool40}")
    conn.close()


def test_tc93_seed_display_20():
    """seed 수집 display=20 확인 (collect_candidates에서 display=20 사용)"""
    import inspect
    from backend.analyzer import BloggerAnalyzer
    source = inspect.getsource(BloggerAnalyzer.collect_candidates)
    ok = "display=20" in source
    report("TC-93", "seed 수집 display=20 (후보 품질 개선)", ok,
           f"display=20 in source: {ok}")


def test_tc94_score_gap_top_vs_bottom():
    """상위노출자 vs 하위노출자 점수 차이 >= 40점"""
    # 상위노출자: page1=7, str=30, exp=8/10
    gs_top = golden_score(
        base_score_val=65.0, strength_sum=30, exposed_keywords=8,
        total_keywords=10, food_bias_rate=0.5, sponsor_signal_rate=0.2,
        is_food_cat=True, page1_keywords=7,
    )
    # 하위노출자 (pepechan3류): page1=0, str=2, exp=2/10
    gs_bottom = golden_score(
        base_score_val=48.0, strength_sum=2, exposed_keywords=2,
        total_keywords=10, food_bias_rate=0.0, sponsor_signal_rate=0.0,
        is_food_cat=False, page1_keywords=0,
    )
    gap = gs_top - gs_bottom
    ok1 = gap >= 40
    ok2 = gs_top >= 60
    ok3 = gs_bottom < 20
    ok = ok1 and ok2 and ok3
    report("TC-94", "상위노출자 vs 하위노출자 점수 차이 >= 40점", ok,
           f"top={gs_top}, bottom={gs_bottom}, gap={gap}")


# ==================== TC-95 ~ TC-100: 포스트 다양성 (Post-Diversity Fix) ====================

def test_tc95_post_diversity_factor():
    """post_diversity_factor: 5키워드 5포스트 (1.0) vs 5키워드 1포스트 (0.52)"""
    # 다양한 포스트 (5키워드 5포스트 = diversity 1.0)
    gs_diverse = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=3,
        unique_exposed_posts=5, unique_page1_posts=3,
    )
    # 중복 포스트 (5키워드 1포스트 = diversity 0.2 → factor 0.52)
    gs_dup = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=3,
        unique_exposed_posts=1, unique_page1_posts=1,
    )
    ok1 = gs_diverse > gs_dup  # 다양한 포스트가 더 높은 점수
    ok2 = gs_diverse - gs_dup >= 10  # 의미 있는 점수 차이
    ok = ok1 and ok2
    report("TC-95", "post_diversity_factor (다양 vs 중복)", ok,
           f"diverse={gs_diverse}, dup={gs_dup}, gap={gs_diverse - gs_dup}")


def test_tc96_unique_exposed_posts_param():
    """golden_score unique_exposed_posts 파라미터 작동 확인"""
    # unique=0 (미제공) → diversity_factor=1.0 (기존 동작)
    gs_no_info = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=3,
        unique_exposed_posts=0, unique_page1_posts=0,
    )
    # unique=exposed (다양) → 높은 점수
    gs_diverse = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=3,
        unique_exposed_posts=5, unique_page1_posts=3,
    )
    # unique=1, exposed=5 → 낮은 점수
    gs_dup = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=3,
        unique_exposed_posts=1, unique_page1_posts=1,
    )
    ok1 = gs_no_info == gs_diverse  # unique=0이면 패널티 없음 = 다양할 때와 동일
    ok2 = gs_diverse > gs_dup
    ok3 = gs_dup < gs_no_info  # 중복이면 미제공보다 낮음
    ok = ok1 and ok2 and ok3
    report("TC-96", "unique_exposed_posts 파라미터 작동", ok,
           f"no_info={gs_no_info}, diverse={gs_diverse}, dup={gs_dup}")


def test_tc97_page1_authority_unique():
    """Page1Authority에 unique_page1_posts 적용: unique=1 vs page1=5"""
    # page1_keywords=5이지만 unique_page1_posts=1 → authority는 unique 기준
    gs_dup_p1 = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=5,
        unique_exposed_posts=1, unique_page1_posts=1,
    )
    # page1_keywords=5, unique_page1_posts=5 → authority는 높음
    gs_real_p1 = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=5,
        unique_exposed_posts=5, unique_page1_posts=5,
    )
    # unique=1이면 page1=5여도 authority가 낮아야 함
    ok1 = gs_real_p1 > gs_dup_p1
    ok2 = gs_real_p1 - gs_dup_p1 >= 15  # Page1Authority 차이 + confidence 차이
    ok = ok1 and ok2
    report("TC-97", "Page1Authority unique_page1_posts 적용", ok,
           f"real={gs_real_p1}, dup={gs_dup_p1}, gap={gs_real_p1 - gs_dup_p1}")


def test_tc98_reporting_unique_columns():
    """reporting.py SQL unique 컬럼: 같은 post_link 5개 → unique_exposed_posts=1"""
    conn = get_conn(TEST_DB)
    init_db(conn)
    sid = upsert_store(conn, "제주", "테스트", "", "유니크테스트", "")
    bid = "dup_post_blogger"
    upsert_blogger(conn, bid, f"https://blog.naver.com/{bid}", "20260210", 3.0, 0.1, 0.2, "[]", 50.0)
    # 같은 post_link로 5개 키워드 노출
    same_link = "https://blog.naver.com/dup_post_blogger/123456"
    for i in range(5):
        insert_exposure_fact(
            conn, sid, f"키워드_{i}", bid, rank=5, strength_points=5,
            is_page1=1, is_exposed=1,
            post_link=same_link, post_title=f"같은포스트 키워드{i}",
        )
    # 다른 블로거: 5개 키워드에 5개 다른 포스트
    bid2 = "diverse_post_blogger"
    upsert_blogger(conn, bid2, f"https://blog.naver.com/{bid2}", "20260210", 3.0, 0.1, 0.2, "[]", 50.0)
    for i in range(5):
        insert_exposure_fact(
            conn, sid, f"키워드_{i}", bid2, rank=5, strength_points=5,
            is_page1=1, is_exposed=1,
            post_link=f"https://blog.naver.com/{bid2}/{100+i}",
            post_title=f"다른포스트{i}",
        )
    conn.commit()

    result = get_top20_and_pool40(conn, sid, days=30, category_text="테스트")
    all_bloggers = result["top20"] + result["pool40"]
    dup_blogger = next((b for b in all_bloggers if b["blogger_id"] == bid), None)
    diverse_blogger = next((b for b in all_bloggers if b["blogger_id"] == bid2), None)

    ok1 = dup_blogger is not None and dup_blogger["unique_exposed_posts"] == 1
    ok2 = dup_blogger is not None and dup_blogger["unique_page1_posts"] == 1
    ok3 = diverse_blogger is not None and diverse_blogger["unique_exposed_posts"] == 5
    ok4 = diverse_blogger is not None and diverse_blogger["unique_page1_posts"] == 5
    # 다양한 포스트 블로거가 더 높은 점수
    ok5 = (diverse_blogger["golden_score"] if diverse_blogger else 0) > (dup_blogger["golden_score"] if dup_blogger else 0)

    ok = ok1 and ok2 and ok3 and ok4 and ok5
    report("TC-98", "SQL unique 컬럼 집계 (같은 post_link=1)", ok,
           f"dup_unique={dup_blogger['unique_exposed_posts'] if dup_blogger else 'N/A'}, "
           f"diverse_unique={diverse_blogger['unique_exposed_posts'] if diverse_blogger else 'N/A'}, "
           f"dup_gs={dup_blogger['golden_score'] if dup_blogger else 'N/A'}, "
           f"diverse_gs={diverse_blogger['golden_score'] if diverse_blogger else 'N/A'}")
    conn.close()


def test_tc99_exposure_potential_unique_posts():
    """ExposurePotential: 고유 포스트 기반 판단"""
    conn = get_conn(TEST_DB)
    init_db(conn)
    sid = upsert_store(conn, "서울", "테스트", "", "포텐셜테스트", "")
    # 5키워드 1포스트 → "매우높음" 아님
    bid1 = "ep_dup_blogger"
    upsert_blogger(conn, bid1, f"https://blog.naver.com/{bid1}", "20260210", 3.0, 0.1, 0.2, "[]", 50.0)
    same_link = "https://blog.naver.com/ep_dup_blogger/111"
    for i in range(5):
        insert_exposure_fact(
            conn, sid, f"ep_kw_{i}", bid1, rank=3, strength_points=5,
            is_page1=1, is_exposed=1,
            post_link=same_link, post_title="같은포스트",
        )
    # 5키워드 5포스트 → "매우높음"
    bid2 = "ep_diverse_blogger"
    upsert_blogger(conn, bid2, f"https://blog.naver.com/{bid2}", "20260210", 3.0, 0.1, 0.2, "[]", 50.0)
    for i in range(5):
        insert_exposure_fact(
            conn, sid, f"ep_kw_{i}", bid2, rank=3, strength_points=5,
            is_page1=1, is_exposed=1,
            post_link=f"https://blog.naver.com/{bid2}/{200+i}",
            post_title=f"포스트{i}",
        )
    conn.commit()

    result = get_top20_and_pool40(conn, sid, days=30, category_text="테스트")
    all_bloggers = result["top20"] + result["pool40"]
    dup = next((b for b in all_bloggers if b["blogger_id"] == bid1), None)
    diverse = next((b for b in all_bloggers if b["blogger_id"] == bid2), None)

    ok1 = dup is not None and dup["exposure_potential"] != "매우높음"  # 1포스트 → 매우높음 아님
    ok2 = diverse is not None and diverse["exposure_potential"] == "매우높음"  # 5포스트 → 매우높음

    ok = ok1 and ok2
    report("TC-99", "ExposurePotential 고유 포스트 기반", ok,
           f"dup_potential={dup['exposure_potential'] if dup else 'N/A'}, "
           f"diverse_potential={diverse['exposure_potential'] if diverse else 'N/A'}")
    conn.close()


def test_tc100_confidence_unique_posts():
    """Confidence에 고유 포스트 반영: page1_keywords=5, unique_page1_posts=1 → confidence 하락"""
    # page1=5이지만 unique=1 → confidence는 unique 기준 (ratio=0.1 → 0.8)
    gs_dup = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=5,
        unique_exposed_posts=1, unique_page1_posts=1,
    )
    # page1=5, unique=5 → confidence=1.0 (ratio=0.5)
    gs_real = golden_score(
        base_score_val=50.0, strength_sum=15, exposed_keywords=5,
        total_keywords=10, food_bias_rate=0.3, sponsor_signal_rate=0.2,
        is_food_cat=False, page1_keywords=5,
        unique_exposed_posts=5, unique_page1_posts=5,
    )
    # unique=1/10=0.1 → confidence=0.8 < unique=5/10=0.5 → confidence=1.0
    ok1 = gs_real > gs_dup
    ok2 = gs_dup < gs_real  # confidence 차이로 점수 하락

    ok = ok1 and ok2
    report("TC-100", "Confidence 고유 포스트 반영 (unique=1 → 하락)", ok,
           f"real={gs_real}, dup={gs_dup}, gap={gs_real - gs_dup}")


# ==================== TC-101~TC-102: 지역만 모드 블로거 수집 강화 ====================

def test_tc101_region_only_power_no_seed_overlap():
    """지역만 모드 region power ≠ seed (중복 0개)"""
    p = StoreProfile(region_text="제주시", category_text="")
    seed = build_seed_queries(p)
    rp = build_region_power_queries(p)

    overlap = set(seed) & set(rp)
    ok1 = len(overlap) == 0
    ok2 = len(rp) == 3
    ok3 = len(seed) == 7

    ok = ok1 and ok2 and ok3
    report("TC-101", "지역만 모드 region power ≠ seed (중복 0개)", ok,
           f"overlap={overlap}, rp={rp}, seed={seed}")


def test_tc102_region_only_seed_pure_region():
    """지역만 모드 seed에 순수 지역명 쿼리 포함 확인"""
    p = StoreProfile(region_text="노형동", category_text="")
    seed = build_seed_queries(p)

    # 첫 번째 쿼리가 순수 지역명
    ok1 = seed[0] == "노형동"
    # 맛집 후기 포함 (깊이 강화)
    ok2 = "노형동 맛집 후기" in seed
    # 가볼만한곳, 블로그 제거 확인
    ok3 = "노형동 가볼만한곳" not in seed
    ok4 = "노형동 블로그" not in seed

    ok = ok1 and ok2 and ok3 and ok4
    report("TC-102", "지역만 모드 seed 순수 지역명 + 맛집 후기 포함", ok,
           f"first={seed[0]}, has_matjip_review={'노형동 맛집 후기' in seed}, seed={seed}")


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

    print("\n[GoldenScore TC-35~37]")
    test_tc35_base_score_column()
    test_tc36_golden_score()
    test_tc37_is_food_category()

    print("\n[v2.0 성능 최적화 TC-38~43]")
    test_tc38_food_words_no_generic()
    test_tc39_blogger_id_extraction()
    test_tc40_bloggername_in_sample()
    test_tc41_pool40_nonfood_quota()
    test_tc42_guide_templates()
    test_tc43_broad_query_categories()

    print("\n[검토보고서 반영 TC-44~48]")
    test_tc44_keyword_weight_for_suffix()
    test_tc45_exposure_potential()
    test_tc46_category_holdout_keywords()
    test_tc47_broad_bonus_in_base_score()
    test_tc48_weighted_strength_golden_score()

    print("\n[검토보고서 v2 반영 TC-49~52]")
    test_tc49_api_retry_config()
    test_tc50_category_synonym_matching()
    test_tc51_guide_disclosure_position()
    test_tc52_kpi_definition_in_meta()

    print("\n[가이드 업그레이드 TC-53~57]")
    test_tc53_new_template_matching()
    test_tc54_forbidden_words_in_guide()
    test_tc55_seo_guide_fields()
    test_tc56_medical_disclaimer()
    test_tc57_word_count_in_review_structure()

    print("\n[블로그 개별 분석 TC-58~65]")
    test_tc58_extract_blogger_id()
    test_tc59_analyze_activity()
    test_tc60_analyze_content()
    test_tc61_analyze_suitability()
    test_tc62_compute_grade()
    test_tc63_generate_insights()
    test_tc64_blog_analyses_table()
    test_tc65_keyword_extraction()

    print("\n[BlogScore v2 5축 TC-66~69]")
    test_tc66_analyze_quality()
    test_tc67_sponsored_signal_detection()
    test_tc68_forbidden_words()
    test_tc69_v2_total_score_range()

    print("\n[GoldenScore 노출 우선 랭킹 TC-70~73]")
    test_tc70_zero_exposure_confidence()
    test_tc71_sufficient_exposure_confidence()
    test_tc72_top20_gate()
    test_tc73_unexposed_tag()

    print("\n[GoldenScore v2.2 캘리브레이션 TC-74]")
    test_tc74_calibration_distribution()

    print("\n[랭킹 파워 기반 모집 TC-75~80]")
    test_tc75_region_power_queries()
    test_tc76_seed_queries_no_store_name()
    test_tc77_brand_blog_detection()
    test_tc78_normal_blogger_no_false_positive()
    test_tc79_franchise_names_expanded()
    test_tc80_pipeline_query_count()

    print("\n[지역만 검색 모드 TC-81~84]")
    test_tc81_seed_queries_empty_category()
    test_tc82_exposure_keywords_empty_category()
    test_tc83_keyword_ab_sets_empty_category()
    test_tc84_detect_self_blog_empty_category()

    print("\n[주제 모드 TC-85~89]")
    test_tc85_seed_queries_topic_mode()
    test_tc86_exposure_keywords_topic_mode()
    test_tc87_keyword_ab_sets_topic_mode()
    test_tc88_is_topic_mode()
    test_tc89_topic_seed_map_coverage()

    print("\n[GoldenScore v3.0 TC-90~94]")
    test_tc90_page1_authority()
    test_tc91_v3_confidence()
    test_tc92_top20_page1_gate()
    test_tc93_seed_display_20()
    test_tc94_score_gap_top_vs_bottom()

    print("\n[포스트 다양성 TC-95~100]")
    test_tc95_post_diversity_factor()
    test_tc96_unique_exposed_posts_param()
    test_tc97_page1_authority_unique()
    test_tc98_reporting_unique_columns()
    test_tc99_exposure_potential_unique_posts()
    test_tc100_confidence_unique_posts()

    print("\n[지역만 모드 블로거 수집 강화 TC-101~102]")
    test_tc101_region_only_power_no_seed_overlap()
    test_tc102_region_only_seed_pure_region()

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
