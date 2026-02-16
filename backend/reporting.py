from __future__ import annotations
import json
import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from backend.scoring import performance_score, golden_score, golden_score_v4, golden_score_v5, golden_score_v7, is_food_category, keyword_weight_for_suffix, compute_authority_grade
from backend.analyzer import detect_self_blog
from backend.blog_analyzer import compute_grade
from backend.models import CandidateBlogger, BlogPostItem


def get_top20_and_pool40(conn: sqlite3.Connection, store_id: int, days: int = 30, category_text: str = "") -> Dict[str, Any]:
    """Top20 강한 추천 + Pool40 운영 풀 (GoldenScore 기반)"""

    # 지역만 모드(빈 카테고리): food_cat=None → CategoryFit 중립 + Pool40 쿼터 중립
    food_cat = None if not category_text.strip() else is_food_category(category_text)

    # has_category 판별 (topic도 확인)
    store_topic_row = conn.execute(
        "SELECT topic FROM stores WHERE store_id=?", (store_id,)
    ).fetchone()
    store_topic = (store_topic_row["topic"] or "") if store_topic_row else ""
    has_category = bool(category_text.strip() or store_topic.strip())

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
            COUNT(DISTINCT CASE WHEN is_exposed=1 AND post_link IS NOT NULL AND post_link != '' THEN post_link END) AS unique_exposed_posts,
            COUNT(DISTINCT CASE WHEN is_page1=1 AND post_link IS NOT NULL AND post_link != '' THEN post_link END) AS unique_page1_posts,
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
          b.posts_sample_json,
          b.tier_score,
          b.tier_grade,
          b.region_power_hits,
          b.broad_query_hits,
          b.rss_interval_avg,
          b.rss_originality,
          b.rss_diversity,
          b.rss_richness,
          b.keyword_match_ratio,
          b.queries_hit_ratio,
          b.popularity_cross_score,
          b.topic_focus,
          b.topic_continuity,
          b.game_defense,
          b.quality_floor,
          b.days_since_last_post,
          b.rss_originality_v7,
          b.rss_diversity_smoothed
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
        SELECT blogger_id, keyword, MIN(rank) AS rank,
               MAX(strength_points) AS strength_points,
               MAX(is_page1) AS is_page1,
               post_link, post_title
        FROM exposures
        WHERE store_id = ? AND blogger_id IN ({placeholders})
          AND checked_at >= datetime('now', ?)
          AND is_exposed = 1
        GROUP BY blogger_id, keyword, post_link
        ORDER BY MIN(rank) ASC
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
        ts = r["tier_score"] or 0.0
        tg = r["tier_grade"] or "D"
        rp_hits = r["region_power_hits"] or 0
        bq_hits = r["broad_query_hits"] or 0
        rss_ia = r["rss_interval_avg"]
        rss_orig = r["rss_originality"] or 0.0
        rss_div = r["rss_diversity"] or 0.0
        rss_rich = r["rss_richness"] or 0.0
        kw_match = r["keyword_match_ratio"] or 0.0
        q_hit = r["queries_hit_ratio"] or 0.0
        # v7.0 신규 필드
        pop_cross = r["popularity_cross_score"] or 0.0
        tf = r["topic_focus"] or 0.0
        tc = r["topic_continuity"] or 0.0
        gd = r["game_defense"] or 0.0
        qfl = r["quality_floor"] or 0.0
        dslp = r["days_since_last_post"]
        rss_orig_v7 = r["rss_originality_v7"] or 0.0
        rss_div_sm = r["rss_diversity_smoothed"] or 0.0

        # 키워드 가중치 적용: 핵심 키워드(추천/후기/가격) 노출에 더 높은 점수
        weighted_strength = sum(
            ed["strength_points"] * keyword_weight_for_suffix(ed["keyword"])
            for ed in exposure_details
        )

        perf = golden_score_v7(
            region_power_hits=rp_hits,
            broad_query_hits=bq_hits,
            interval_avg=rss_ia,
            originality_raw=rss_orig,
            diversity_entropy=rss_div,
            richness_avg_len=rss_rich,
            sponsor_signal_rate=sr,
            cat_strength=r["strength_sum"],
            cat_exposed=r["exposed_keywords_30d"],
            total_keywords=max(1, total_keywords),
            base_score_val=bs,
            weighted_strength=weighted_strength,
            keyword_match_ratio=kw_match,
            queries_hit_ratio=q_hit,
            has_category=has_category,
            popularity_cross_score=pop_cross,
            page1_keywords=r["page1_keywords_30d"],
            topic_focus=tf,
            topic_continuity=tc,
            days_since_last_post=dslp,
            rss_originality_v7=rss_orig_v7,
            rss_diversity_smoothed=rss_div_sm,
            game_defense=gd,
            quality_floor=qfl,
        )

        line1 = f"권위 {tg} ({ts:.0f}점) | {total_keywords}개 중 노출: {r['exposed_keywords_30d']}개"
        if best_rank == 999:
            line2 = "최고 순위: -"
        else:
            line2 = f"최고 순위: {best_rank}위 (키워드: {best_kw or '-'})"

        # 태그 생성
        tags = []
        if tg in ("S", "A"):
            tags.append("고권위")
        if tg == "D":
            tags.append("저권위")
        if fb >= 0.60:
            tags.append("맛집편향")
        if sr >= 0.40:
            tags.append("협찬성향")
        # 고유 포스트 수 (post_link 없는 레거시 데이터는 키워드 기준 폴백)
        unique_exp = r["unique_exposed_posts"]
        unique_p1 = r["unique_page1_posts"]
        effective_unique_exp = unique_exp if unique_exp > 0 else r["exposed_keywords_30d"]
        effective_unique_p1 = unique_p1 if unique_p1 > 0 else r["page1_keywords_30d"]
        # 노출 안정성: 고유 포스트 5개 이상 노출
        if effective_unique_exp >= 5:
            tags.append("노출안정")
        # 미노출: 검색 노출이 전혀 확인되지 않은 블로거
        if r["exposed_keywords_30d"] == 0:
            tags.append("미노출")

        # ExposurePotential: 고유 포스트 기반 상위노출 가능성 예측
        effective_best = best_rank if best_rank and best_rank != 999 else 999
        if effective_unique_exp >= 5:
            exposure_potential = "매우높음"
        elif effective_unique_exp >= 3 and effective_unique_p1 >= 1:
            exposure_potential = "높음"
        elif effective_unique_exp >= 1 and effective_best <= 20:
            exposure_potential = "보통"
        else:
            exposure_potential = "낮음"

        _grade, _grade_label = compute_grade(perf)
        blogger_entry = {
            "blogger_id": r["blogger_id"],
            "blog_url": r["blog_url"],
            "strength_sum": r["strength_sum"],
            "golden_score": perf,
            "grade": _grade,
            "grade_label": _grade_label,
            "performance_score": perf,  # 하위 호환
            "base_score": bs,
            "tier_score": ts,
            "tier_grade": tg,
            "page1_keywords_30d": r["page1_keywords_30d"],
            "exposed_keywords_30d": r["exposed_keywords_30d"],
            "unique_exposed_posts": unique_exp,
            "unique_page1_posts": unique_p1,
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

    # GoldenScore 내림차순 정렬 (동점 시 tier → strength 내림차순)
    all_bloggers.sort(key=lambda x: (x["golden_score"], x["tier_score"], x["strength_sum"]), reverse=True)

    # Top20: authority_grade in (S,A,B,C) AND exposed >= 1
    tier_qualified = [b for b in all_bloggers if b["tier_grade"] in ("S", "A", "B", "C") and b["exposed_keywords_30d"] >= 1]
    tier_unqualified = [b for b in all_bloggers if not (b["tier_grade"] in ("S", "A", "B", "C") and b["exposed_keywords_30d"] >= 1)]
    top20 = tier_qualified[:20]
    top20_ids = {r["blogger_id"] for r in top20}

    # Pool40: tier_score >= 5 AND cat_exposed >= 1
    remaining_qualified = [r for r in tier_qualified if r["blogger_id"] not in top20_ids]
    pool_eligible = [r for r in tier_unqualified if r["tier_score"] >= 5 and r["exposed_keywords_30d"] >= 1]
    remaining = remaining_qualified + pool_eligible

    target = 40
    if food_cat is None:
        # 지역만 모드: 업종 미지정 → 쿼터 제한 없이 GoldenScore 순 채움
        food_cap = target   # 제한 없음
        nonfood_min = 0     # 우선 확보 없음
    elif food_cat:
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
            "scoring_model": "GoldenScore v7.0 (Auth22+CatExp18+TopExp12+CatFit15+Fresh10+RSSQual13+SpFit5+GameDef-10+QualFloor+5)",
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
