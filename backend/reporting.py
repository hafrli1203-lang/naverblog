from __future__ import annotations
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from backend.scoring import performance_score


def get_top20_and_pool40(conn: sqlite3.Connection, store_id: int, days: int = 30) -> Dict[str, Any]:
    """Top20 강한 추천 + Pool40 운영 풀"""

    # 해당 store의 총 키워드 수 조회
    kw_row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT keyword) AS total_keywords
        FROM exposures
        WHERE store_id = ?
          AND checked_at >= datetime('now', '-{days} days')
        """,
        (store_id,),
    ).fetchone()
    total_keywords = kw_row["total_keywords"] if kw_row else 0

    # 블로거 집계 (넓게 뽑기)
    rows = conn.execute(
        f"""
        WITH recent AS (
          SELECT *
          FROM exposures
          WHERE store_id = ?
            AND checked_at >= datetime('now', '-{days} days')
        ),
        agg AS (
          SELECT
            blogger_id,
            SUM(strength_points) AS strength_sum,
            COUNT(DISTINCT CASE WHEN is_page1=1 THEN keyword END) AS page1_keywords_30d,
            COUNT(DISTINCT CASE WHEN is_exposed=1 THEN keyword END) AS exposed_keywords_30d,
            MIN(CASE WHEN rank IS NOT NULL THEN rank ELSE 999 END) AS best_rank
          FROM recent
          GROUP BY blogger_id
        )
        SELECT
          a.*,
          b.blog_url,
          b.food_bias_rate,
          b.sponsor_signal_rate
        FROM agg a
        JOIN bloggers b ON b.blogger_id = a.blogger_id
        ORDER BY a.strength_sum DESC, a.page1_keywords_30d DESC, a.exposed_keywords_30d DESC, a.best_rank ASC
        LIMIT 200;
        """,
        (store_id,),
    ).fetchall()

    # Performance Score 계산 + best_rank_keyword 조회
    all_bloggers: List[Dict[str, Any]] = []
    for r in rows:
        best_rank = r["best_rank"]
        best_kw = None
        if best_rank and best_rank != 999:
            row2 = conn.execute(
                f"""
                SELECT keyword
                FROM exposures
                WHERE store_id=? AND blogger_id=?
                  AND checked_at >= datetime('now', '-{days} days')
                  AND rank = ?
                ORDER BY checked_at DESC
                LIMIT 1
                """,
                (store_id, r["blogger_id"], best_rank),
            ).fetchone()
            best_kw = row2["keyword"] if row2 else None

        # 키워드별 노출 상세 조회
        exp_rows = conn.execute(
            f"""
            SELECT keyword, rank, strength_points, is_page1, is_exposed,
                   post_link, post_title
            FROM exposures
            WHERE store_id=? AND blogger_id=?
              AND checked_at >= datetime('now', '-{days} days')
              AND is_exposed=1
            ORDER BY rank ASC
            """,
            (store_id, r["blogger_id"]),
        ).fetchall()
        exposure_details = [
            {
                "keyword": er["keyword"],
                "rank": er["rank"],
                "strength_points": er["strength_points"],
                "is_page1": bool(er["is_page1"]),
                "post_link": er["post_link"],
                "post_title": er["post_title"],
            }
            for er in exp_rows
        ]

        perf = performance_score(
            strength_sum=r["strength_sum"],
            exposed_keywords=r["exposed_keywords_30d"],
            total_keywords=max(1, total_keywords),
        )

        line1 = f"{total_keywords}개 중 1페이지 노출: {r['page1_keywords_30d']}개"
        if best_rank == 999:
            line2 = "최고 순위: -"
        else:
            line2 = f"최고 순위: {best_rank}위 (키워드: {best_kw or '-'})"

        # 태그 생성
        tags = []
        fb = r["food_bias_rate"] or 0.0
        sr = r["sponsor_signal_rate"] or 0.0
        if fb >= 0.60:
            tags.append("맛집편향")
        if sr >= 0.40:
            tags.append("협찬성향")
        # 노출 안정성: 7개 키워드 중 4개 이상 노출
        if r["exposed_keywords_30d"] >= 4:
            tags.append("노출안정")

        all_bloggers.append(
            {
                "blogger_id": r["blogger_id"],
                "blog_url": r["blog_url"],
                "strength_sum": r["strength_sum"],
                "performance_score": perf,
                "page1_keywords_30d": r["page1_keywords_30d"],
                "exposed_keywords_30d": r["exposed_keywords_30d"],
                "best_rank": None if best_rank == 999 else best_rank,
                "best_rank_keyword": best_kw,
                "food_bias_rate": r["food_bias_rate"],
                "sponsor_signal_rate": r["sponsor_signal_rate"],
                "report_line1": line1,
                "report_line2": line2,
                "tags": tags,
                "exposure_details": exposure_details,
            }
        )

    # Performance Score 내림차순 정렬
    all_bloggers.sort(key=lambda x: x["performance_score"], reverse=True)

    # Top20: Performance Score 상위 20명
    top20 = all_bloggers[:20]
    top20_ids = {r["blogger_id"] for r in top20}

    # Pool40: Top20 제외 후 쿼터 적용
    remaining = [r for r in all_bloggers if r["blogger_id"] not in top20_ids]

    target = 40
    food_cap = int(target * 0.60)  # 24
    nonfood_min = int(target * 0.30)  # 12

    selected: List[Dict[str, Any]] = []
    food_count = 0
    nonfood_count = 0

    # 1-pass: 비맛집 최소 확보
    for r in remaining:
        fb = r["food_bias_rate"] or 0.0
        is_food = fb >= 0.60
        if not is_food and nonfood_count < nonfood_min:
            selected.append(r)
            nonfood_count += 1
        if len(selected) >= target:
            break

    # 2-pass: cap 지키며 채움
    if len(selected) < target:
        selected_ids = {x["blogger_id"] for x in selected}
        for r in remaining:
            if r["blogger_id"] in selected_ids:
                continue
            fb = r["food_bias_rate"] or 0.0
            is_food = fb >= 0.60
            if is_food:
                if food_count >= food_cap:
                    continue
                selected.append(r)
                food_count += 1
            else:
                selected.append(r)
                nonfood_count += 1
            if len(selected) >= target:
                break

    pool40 = selected[:target]

    return {
        "top20": top20,
        "pool40": pool40,
        "meta": {"days": days, "total_keywords": total_keywords},
    }


# 하위 호환: 기존 테스트에서 사용하는 함수명
def get_top10_and_top50(conn: sqlite3.Connection, store_id: int, days: int = 30) -> Dict[str, Any]:
    result = get_top20_and_pool40(conn, store_id, days)
    all_bloggers = result["top20"] + result["pool40"]
    # 하위 호환: strength_sum 내림차순으로 정렬
    all_bloggers.sort(key=lambda x: (x["strength_sum"], x["page1_keywords_30d"]), reverse=True)
    top10 = all_bloggers[:10]
    top10_ids = {r["blogger_id"] for r in top10}
    top50 = [r for r in all_bloggers if r["blogger_id"] not in top10_ids][:50]
    return {
        "top10": top10,
        "top50": top50,
        "meta": result["meta"],
    }
