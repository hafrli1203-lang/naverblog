from __future__ import annotations
import json
import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from backend.scoring import performance_score, golden_score, is_food_category, keyword_weight_for_suffix
from backend.analyzer import detect_self_blog
from backend.models import CandidateBlogger, BlogPostItem


def get_top20_and_pool40(conn: sqlite3.Connection, store_id: int, days: int = 30, category_text: str = "") -> Dict[str, Any]:
    """Top20 강한 추천 + Pool40 운영 풀 (GoldenScore 기반)"""

    food_cat = is_food_category(category_text)

    # days를 정수로 강제 (SQL injection 방지)
    days = int(days)
    days_expr = f"-{days} days"

    # 해당 store의 총 키워드 수 조회
    kw_row = conn.execute(
        """
        SELECT COUNT(DISTINCT keyword) AS total_keywords
        FROM exposures
        WHERE store_id = ?
          AND checked_at >= datetime('now', ?)
        """,
        (store_id, days_expr),
    ).fetchone()
    total_keywords = kw_row["total_keywords"] if kw_row else 0

    # 매장 정보 조회 (자체블로그 감지용)
    store_row = conn.execute(
        "SELECT store_name, category_text FROM stores WHERE store_id=?",
        (store_id,),
    ).fetchone()
    store_name = store_row["store_name"] if store_row else ""
    store_cat = store_row["category_text"] if store_row else category_text

    # 블로거 집계 (넓게 뽑기)
    rows = conn.execute(
        """
        WITH recent AS (
          SELECT *
          FROM exposures
          WHERE store_id = ?
            AND checked_at >= datetime('now', ?)
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
          b.sponsor_signal_rate,
          b.base_score,
          b.posts_sample_json
        FROM agg a
        JOIN bloggers b ON b.blogger_id = a.blogger_id
        ORDER BY a.strength_sum DESC, a.page1_keywords_30d DESC, a.exposed_keywords_30d DESC, a.best_rank ASC
        LIMIT 200;
        """,
        (store_id, days_expr),
    ).fetchall()

    if not rows:
        result = {
            "top20": [],
            "pool40": [],
            "meta": {"days": days, "total_keywords": total_keywords},
        }
        return result

    # 배치 쿼리: 전체 블로거의 best_rank_keyword + exposure_details를 한 번에 조회
    blogger_ids = [r["blogger_id"] for r in rows]
    placeholders = ",".join("?" for _ in blogger_ids)

    # best_rank_keyword 배치: 블로거별 best rank에 해당하는 키워드
    best_rank_map: Dict[str, str] = {}
    best_kw_rows = conn.execute(
        f"""
        SELECT blogger_id, keyword, rank
        FROM exposures
        WHERE store_id = ? AND blogger_id IN ({placeholders})
          AND checked_at >= datetime('now', ?)
          AND rank IS NOT NULL
        ORDER BY rank ASC, checked_at DESC
        """,
        (store_id, *blogger_ids, days_expr),
    ).fetchall()
    for bkr in best_kw_rows:
        bid = bkr["blogger_id"]
        if bid not in best_rank_map:
            best_rank_map[bid] = bkr["keyword"]

    # exposure_details 배치: 블로거별 노출 상세
    exp_detail_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    exp_detail_rows = conn.execute(
        f"""
        SELECT blogger_id, keyword, rank, strength_points, is_page1, is_exposed,
               post_link, post_title
        FROM exposures
        WHERE store_id = ? AND blogger_id IN ({placeholders})
          AND checked_at >= datetime('now', ?)
          AND is_exposed = 1
        ORDER BY rank ASC
        """,
        (store_id, *blogger_ids, days_expr),
    ).fetchall()
    for er in exp_detail_rows:
        exp_detail_map[er["blogger_id"]].append({
            "keyword": er["keyword"],
            "rank": er["rank"],
            "strength_points": er["strength_points"],
            "is_page1": bool(er["is_page1"]),
            "post_link": er["post_link"],
            "post_title": er["post_title"],
        })

    # GoldenScore 계산
    all_bloggers: List[Dict[str, Any]] = []
    competition: List[Dict[str, Any]] = []

    for r in rows:
        best_rank = r["best_rank"]
        best_kw = best_rank_map.get(r["blogger_id"]) if best_rank and best_rank != 999 else None
        exposure_details = exp_detail_map.get(r["blogger_id"], [])

        fb = r["food_bias_rate"] or 0.0
        sr = r["sponsor_signal_rate"] or 0.0
        bs = r["base_score"] or 0.0

        # 키워드 가중치 적용: 핵심 키워드(추천/후기/가격) 노출에 더 높은 점수
        weighted_strength = sum(
            ed["strength_points"] * keyword_weight_for_suffix(ed["keyword"])
            for ed in exposure_details
        )

        perf = golden_score(
            base_score_val=bs,
            strength_sum=r["strength_sum"],
            exposed_keywords=r["exposed_keywords_30d"],
            total_keywords=max(1, total_keywords),
            food_bias_rate=fb,
            sponsor_signal_rate=sr,
            is_food_cat=food_cat,
            weighted_strength=weighted_strength,
        )

        line1 = f"{total_keywords}개 중 1페이지 노출: {r['page1_keywords_30d']}개"
        if best_rank == 999:
            line2 = "최고 순위: -"
        else:
            line2 = f"최고 순위: {best_rank}위 (키워드: {best_kw or '-'})"

        # 태그 생성
        tags = []
        if fb >= 0.60:
            tags.append("맛집편향")
        if sr >= 0.40:
            tags.append("협찬성향")
        # 노출 안정성: 10개 키워드 중 5개 이상 노출
        if r["exposed_keywords_30d"] >= 5:
            tags.append("노출안정")

        # ExposurePotential: 상위노출 가능성 예측
        exposed_cnt = r["exposed_keywords_30d"]
        effective_best = best_rank if best_rank and best_rank != 999 else 999
        if exposed_cnt >= 5:
            exposure_potential = "매우높음"
        elif exposed_cnt >= 3 and effective_best <= 10:
            exposure_potential = "높음"
        elif exposed_cnt >= 1 and effective_best <= 20:
            exposure_potential = "보통"
        else:
            exposure_potential = "낮음"

        blogger_entry = {
            "blogger_id": r["blogger_id"],
            "blog_url": r["blog_url"],
            "strength_sum": r["strength_sum"],
            "golden_score": perf,
            "performance_score": perf,  # 하위 호환
            "base_score": bs,
            "page1_keywords_30d": r["page1_keywords_30d"],
            "exposed_keywords_30d": r["exposed_keywords_30d"],
            "best_rank": None if best_rank == 999 else best_rank,
            "best_rank_keyword": best_kw,
            "food_bias_rate": fb,
            "sponsor_signal_rate": sr,
            "report_line1": line1,
            "report_line2": line2,
            "tags": tags,
            "exposure_details": exposure_details,
            "exposure_potential": exposure_potential,
        }

        # 자체블로그/경쟁사 감지
        bloggername = ""
        try:
            sample = json.loads(r["posts_sample_json"] or "[]")
            if sample:
                bloggername = sample[0].get("bloggername", "")
        except Exception:
            pass

        dummy = CandidateBlogger(
            blogger_id=r["blogger_id"],
            blog_url=r["blog_url"],
            ranks=[], queries_hit=set(), posts=[
                BlogPostItem(title="", description="", link="", bloggername=bloggername)
            ] if bloggername else [],
        )
        blog_type = detect_self_blog(dummy, store_name or "", store_cat)

        if blog_type in ("self", "competitor"):
            blogger_entry["blog_type"] = blog_type
            competition.append(blogger_entry)
        else:
            all_bloggers.append(blogger_entry)

    # GoldenScore 내림차순 정렬
    all_bloggers.sort(key=lambda x: x["golden_score"], reverse=True)

    # Top20: GoldenScore 상위 20명
    top20 = all_bloggers[:20]
    top20_ids = {r["blogger_id"] for r in top20}

    # Pool40: Top20 제외 후 동적 쿼터 적용
    # 업종 특성에 따라 맛집/비맛집 블로거 비율을 동적으로 조절
    remaining = [r for r in all_bloggers if r["blogger_id"] not in top20_ids]

    target = 40
    if food_cat:
        # 음식 업종: 맛집 블로거 80% 허용, 비맛집 최소 10% 확보
        food_cap = int(target * 0.80)   # 32명
        nonfood_min = int(target * 0.10) # 4명
    else:
        # 비음식 업종: 맛집 블로거 30% 제한, 비맛집 최소 50% 우선 확보
        food_cap = int(target * 0.30)    # 12명
        nonfood_min = int(target * 0.50) # 20명

    selected: List[Dict[str, Any]] = []
    food_count = 0
    nonfood_count = 0

    # 1-pass: 비맛집 블로거 최소 수량(nonfood_min)을 우선 확보
    # GoldenScore 정렬 순서를 유지하면서 비맛집만 선별
    for r in remaining:
        fb = r["food_bias_rate"] or 0.0
        is_food = fb >= 0.60
        if not is_food and nonfood_count < nonfood_min:
            selected.append(r)
            nonfood_count += 1
        if nonfood_count >= nonfood_min:
            break

    # 2-pass: 나머지 슬롯을 food_cap 제한을 지키면서 GoldenScore 순으로 채움
    # 1-pass에서 이미 선택된 블로거는 스킵
    if len(selected) < target:
        selected_ids = {x["blogger_id"] for x in selected}
        for r in remaining:
            if r["blogger_id"] in selected_ids:
                continue
            fb = r["food_bias_rate"] or 0.0
            is_food = fb >= 0.60
            if is_food:
                if food_count >= food_cap:
                    continue  # 맛집 상한 초과 → 스킵
                selected.append(r)
                food_count += 1
            else:
                selected.append(r)
                nonfood_count += 1
            if len(selected) >= target:
                break

    pool40 = selected[:target]

    result = {
        "top20": top20,
        "pool40": pool40,
        "meta": {
            "days": days,
            "total_keywords": total_keywords,
            "kpi_definition": "네이버 블로그탭 1~30위 기준 (1페이지=1~10위)",
            "scoring_model": "GoldenScore v2.0 (BlogPower+Exposure+CategoryFit+Recruitability)",
        },
    }

    if competition:
        result["competition"] = competition

    return result


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
