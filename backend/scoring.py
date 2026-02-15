from __future__ import annotations
import re
from datetime import datetime
from typing import Optional

from backend.models import CandidateBlogger, BlogPostItem


FOOD_WORDS = ["맛집", "메뉴", "웨이팅", "내돈내산", "재방문", "런치", "디너", "맛있", "먹방", "식당"]
SPONSOR_WORDS = ["협찬", "제공", "지원", "초대", "체험단", "서포터즈", "기자단", "광고"]


def parse_date_any(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    # YYYYMMDD
    if re.fullmatch(r"\d{8}", s):
        try:
            return datetime.strptime(s, "%Y%m%d")
        except Exception:
            return None
    # ISO-ish
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt)
        except Exception:
            pass
    return None


def calc_food_bias(posts: list[BlogPostItem]) -> float:
    if not posts:
        return 0.0
    hits = 0
    for p in posts:
        text = f"{p.title} {p.description}"
        if any(w in text for w in FOOD_WORDS):
            hits += 1
    return hits / max(1, len(posts))


def calc_sponsor_signal(posts: list[BlogPostItem]) -> float:
    if not posts:
        return 0.0
    hits = 0
    for p in posts:
        text = f"{p.title} {p.description}"
        if any(w in text for w in SPONSOR_WORDS):
            hits += 1
    return hits / max(1, len(posts))


KEYWORD_SUFFIX_WEIGHTS = {
    "추천": 1.3,
    "후기": 1.2,
    "가격": 1.1,
}


def keyword_weight_for_suffix(keyword: str) -> float:
    """
    키워드 검색의도 기반 가중치.
    핵심 대표 키워드(지역+업종만) = 1.5x
    추천 = 1.3x, 후기 = 1.2x, 가격 = 1.1x
    기타 = 1.0x
    """
    parts = keyword.strip().split()
    if len(parts) <= 2:
        return 1.5  # "지역 업종" = 메인 키워드
    suffix = parts[-1]
    return KEYWORD_SUFFIX_WEIGHTS.get(suffix, 1.0)


def strength_points(rank: Optional[int]) -> int:
    if rank is None:
        return 0
    if 1 <= rank <= 3:
        return 5
    if 4 <= rank <= 10:
        return 3
    if 11 <= rank <= 20:
        return 2
    if 21 <= rank <= 30:
        return 1
    return 0


def base_score(
    blogger: CandidateBlogger,
    region_text: str,
    address_tokens: list[str],
    queries_total: int,
) -> float:
    """
    base 0~80:
    - 최근활동 0~15
    - 평균SERP순위 0~15
    - 지역정합 0~15
    - 쿼리적합 0~10
    - 활동빈도 0~10 (간단화)
    - place_fit 0~10 (address token 노출)
    - broad_bonus 0~5 (블로그 지수 프록시: broad 쿼리 출현 횟수)
    - food_bias_penalty 0~-10
    - sponsor_penalty 0~-15
    """
    posts = blogger.posts
    now = datetime.now()

    # 최근활동
    dates = [parse_date_any(p.postdate) for p in posts]
    dates = [d for d in dates if d]
    latest = max(dates) if dates else None
    if latest:
        days = (now - latest).days
        recent = max(0.0, 15.0 * (1 - min(days, 60) / 60))
    else:
        recent = 0.0

    # 평균 SERP 순위(낮을수록 좋음)
    if blogger.ranks:
        avg_rank = sum(blogger.ranks) / len(blogger.ranks)
        serp = max(0.0, 15.0 * (1 - min(avg_rank, 30) / 30))
    else:
        serp = 0.0

    # 지역정합: region or address token 포함 비율
    local_hits = blogger.local_hits
    total_posts = max(1, len(posts))
    local_ratio = local_hits / max(1, total_posts)
    local = min(15.0, local_ratio * 30.0)

    # 쿼리 적합(등장한 쿼리 수)
    q_hit = len(blogger.queries_hit)
    qrel = min(10.0, (q_hit / max(1, queries_total)) * 10.0)

    # 활동빈도(간단): 최근 게시물 수가 많을수록 점수
    freq = min(10.0, len(posts) / 20.0 * 10.0)

    # place_fit: address token이 제목/설명에 자연스럽게 나오면 가산(최대 10)
    place_cnt = 0
    for p in posts:
        text = f"{p.title} {p.description}"
        if any(t in text for t in address_tokens):
            place_cnt += 1
    place_fit = min(10.0, (place_cnt / max(1, len(posts))) * 20.0)

    # 편향 페널티
    fb = blogger.food_bias_rate
    penalty = 0.0
    if fb >= 0.75:
        penalty = -10.0
    elif fb >= 0.60:
        penalty = -6.0
    elif fb >= 0.50:
        penalty = -3.0

    # 협찬 페널티
    sponsor = blogger.sponsor_signal_rate
    if sponsor >= 0.60:
        penalty_sponsor = -15.0
    elif sponsor >= 0.40:
        penalty_sponsor = -8.0
    elif sponsor >= 0.25:
        penalty_sponsor = -3.0
    else:
        penalty_sponsor = 0.0

    # broad 키워드 출현 보너스 (블로그 지수 프록시)
    broad_hits = getattr(blogger, 'broad_query_hits', 0)
    if broad_hits >= 3:
        broad_bonus = 5.0
    elif broad_hits >= 1:
        broad_bonus = 2.0
    else:
        broad_bonus = 0.0

    s = recent + serp + local + qrel + freq + place_fit + broad_bonus + penalty + penalty_sponsor
    return max(0.0, min(80.0, s))


FOOD_CATEGORY_KEYWORDS = [
    "맛집", "음식", "식당", "레스토랑", "카페", "커피", "디저트",
    "베이커리", "빵집", "치킨", "피자", "고기", "삼겹살", "횟집",
    "초밥", "라멘", "국밥", "찌개", "한식", "중식", "일식", "양식", "분식",
]


def is_food_category(category_text: str) -> bool:
    cat = category_text.strip().lower()
    return any(kw in cat for kw in FOOD_CATEGORY_KEYWORDS)


def golden_score(
    base_score_val: float,
    strength_sum: int,
    exposed_keywords: int,
    total_keywords: int,
    food_bias_rate: float,
    sponsor_signal_rate: float,
    is_food_cat: bool,
    weighted_strength: float = 0.0,
) -> float:
    """
    GoldenScore (0~100) = 4축 통합
    1. BlogPower (0~30): 정규화된 base_score (broad_bonus 포함)
    2. Exposure (0~30): 가중 노출 강도 + 커버리지
    3. CategoryFit (0~25): 업종 적합도
    4. Recruitability (0~15): 섭외 가능성/효과
    """
    # 1. BlogPower (base_score 0~80 → 0~30)
    blog_power = (base_score_val / 80.0) * 30.0

    # 2. Exposure (가중 strength 우선 사용)
    effective_strength = weighted_strength if weighted_strength > 0 else float(strength_sum)
    max_strength = total_keywords * 5
    strength_part = min(1.0, effective_strength / max(1, max_strength)) * 20.0
    coverage_part = min(1.0, exposed_keywords / max(1, total_keywords)) * 10.0
    exposure = strength_part + coverage_part

    # 3. CategoryFit
    if is_food_cat:
        category_fit = (0.3 + food_bias_rate * 0.7) * 25.0
    else:
        category_fit = max(0.0, (1.0 - food_bias_rate * 1.5)) * 25.0

    # 4. Recruitability (sweet spot: 10~30% sponsor rate)
    if sponsor_signal_rate >= 0.60:
        recruit = 2.0
    elif sponsor_signal_rate >= 0.45:
        recruit = 5.0
    elif sponsor_signal_rate >= 0.30:
        recruit = 10.0
    elif sponsor_signal_rate >= 0.15:
        recruit = 15.0
    elif sponsor_signal_rate >= 0.05:
        recruit = 12.0
    else:
        recruit = 8.0

    return round(blog_power + exposure + category_fit + recruit, 1)


def performance_score(strength_sum: int, exposed_keywords: int, total_keywords: int = 7) -> float:
    """
    Performance Score (0~100):
    - strength 기반 70%: (strength_sum / 35) * 70
    - 노출 키워드 커버리지 30%: (exposed_keywords / total_keywords) * 30
    """
    strength_part = min(1.0, strength_sum / 35.0) * 70.0
    coverage_part = min(1.0, exposed_keywords / max(1, total_keywords)) * 30.0
    return round(strength_part + coverage_part, 1)
