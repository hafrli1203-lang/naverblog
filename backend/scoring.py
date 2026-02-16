from __future__ import annotations
import hashlib
import math
import re
from collections import Counter
from datetime import datetime
from typing import Any, List, Optional

from backend.models import CandidateBlogger, BlogPostItem


FOOD_WORDS = ["맛집", "메뉴", "웨이팅", "내돈내산", "재방문", "런치", "디너", "맛있", "먹방", "식당"]
SPONSOR_WORDS = ["협찬", "제공", "초대", "체험단", "서포터즈", "기자단"]


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

    # region_power 보너스 (0~5): 지역 인기 카테고리에서 상위노출 = 높은 블로그 지수
    region_power = getattr(blogger, 'region_power_hits', 0)
    if region_power >= 2:
        region_power_bonus = 5.0
    elif region_power >= 1:
        region_power_bonus = 3.0
    else:
        region_power_bonus = 0.0

    # seed 수집 단계 1페이지 진입 보너스 (블로그 지수 프록시)
    page1_ranks = sum(1 for r in blogger.ranks if r <= 10)
    if page1_ranks >= 5:
        seed_page1_bonus = 8.0
    elif page1_ranks >= 3:
        seed_page1_bonus = 5.0
    elif page1_ranks >= 1:
        seed_page1_bonus = 2.0
    else:
        seed_page1_bonus = 0.0

    s = recent + serp + local + qrel + freq + place_fit + broad_bonus + region_power_bonus + seed_page1_bonus + penalty + penalty_sponsor
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
    is_food_cat: Optional[bool] = None,
    weighted_strength: float = 0.0,
    page1_keywords: int = 0,
    unique_exposed_posts: int = 0,
    unique_page1_posts: int = 0,
    keyword_match_ratio: float = 0.0,
    queries_hit_ratio: float = 0.0,
    has_category: bool = False,
) -> float:
    """
    GoldenScore v3.0 (0~100) = 5축 통합 × 노출 신뢰 계수
    1. BlogPower (0~15): 정규화된 base_score
    2. Exposure (0~30): 가중 노출 강도 + 커버리지 × post_diversity_factor
    3. Page1Authority (0~15): 1페이지 노출 빈도 = 블로그 지수 핵심 프록시
    4. CategoryFit (0~20): 업종 적합도
    5. Recruitability (0~10): 섭외 가능성/효과

    exposure_confidence (page1 기반):
    - page1_ratio >= 0.3 → 1.0 (3+ page1)
    - page1_ratio >= 0.1 → 0.8 (1-2 page1)
    - exposure_ratio >= 0.3 → 0.55 (노출은 있지만 page1 없음)
    - exposure_ratio > 0 → 0.35 (하위권 노출만)
    - else → 0.2 (미노출)

    post_diversity_factor:
    - 고유 포스트 수 / 노출 키워드 수 → 다양한 포스트일수록 높은 점수
    - 5키워드 5포스트 = 1.0 (이상적), 5키워드 1포스트 = 0.52 (감점)
    """
    # 1. BlogPower (base_score 0~80 → 0~15)
    blog_power = (base_score_val / 80.0) * 15.0

    # 2. Exposure (가중 strength 우선 사용, 현실적 분모 적용)
    effective_strength = weighted_strength if weighted_strength > 0 else float(strength_sum)
    max_strength = total_keywords * 3
    strength_part = min(1.0, effective_strength / max(1, max_strength)) * 18.0
    coverage_part = min(1.0, exposed_keywords / max(1, total_keywords * 0.5)) * 12.0

    # post_diversity_factor: 고유 포스트 / 노출 키워드 수
    # 5키워드 5포스트 = 1.0 (이상적), 5키워드 1포스트 = 0.52 (감점)
    if exposed_keywords > 0 and unique_exposed_posts > 0:
        diversity_ratio = unique_exposed_posts / exposed_keywords
        diversity_factor = 0.4 + 0.6 * diversity_ratio  # 최소 0.4 ~ 최대 1.0
    else:
        diversity_factor = 1.0  # unique_exposed_posts 정보 없으면 패널티 없음

    exposure = (strength_part + coverage_part) * diversity_factor

    # 3. Page1Authority (1페이지 노출 빈도 = 블로그 지수 핵심 프록시)
    # unique_page1_posts 가용 시 고유 포스트 기준 사용
    effective_page1 = unique_page1_posts if unique_page1_posts > 0 else page1_keywords
    page1_ratio = effective_page1 / max(1, total_keywords)
    if page1_ratio >= 0.5:
        page1_authority = 15.0
    elif page1_ratio >= 0.3:
        page1_authority = 12.0
    elif page1_ratio >= 0.2:
        page1_authority = 8.0
    elif page1_ratio >= 0.1:
        page1_authority = 4.0
    else:
        page1_authority = 0.0

    # 4. CategoryFit (키워드 기반 추가 보너스, 0~20)
    if not has_category:
        category_fit = 0.0  # 카테고리 없음: 순수 블로그 지수만 비교
    else:
        exposure_ratio = exposed_keywords / max(1, total_keywords)
        fit = keyword_match_ratio * 0.4 + exposure_ratio * 0.3 + queries_hit_ratio * 0.3
        category_fit = fit * 20.0

    # 5. Recruitability (sweet spot: 10~30% sponsor rate)
    if sponsor_signal_rate >= 0.60:
        recruit = 1.5
    elif sponsor_signal_rate >= 0.45:
        recruit = 3.0
    elif sponsor_signal_rate >= 0.30:
        recruit = 7.0
    elif sponsor_signal_rate >= 0.15:
        recruit = 10.0
    elif sponsor_signal_rate >= 0.05:
        recruit = 8.0
    else:
        recruit = 5.0

    raw_score = blog_power + exposure + page1_authority + category_fit + recruit

    # 노출 신뢰 계수 (page1 기반 exposure_confidence)
    # unique 포스트 가용 시 고유 포스트 기준 사용
    effective_page1_for_conf = unique_page1_posts if unique_page1_posts > 0 else page1_keywords
    effective_exposed_for_conf = unique_exposed_posts if unique_exposed_posts > 0 else exposed_keywords
    effective_page1_ratio = effective_page1_for_conf / max(1, total_keywords)
    effective_exposure_ratio = effective_exposed_for_conf / max(1, total_keywords)
    if effective_page1_ratio >= 0.3:
        confidence = 1.0
    elif effective_page1_ratio >= 0.1:
        confidence = 0.8
    elif effective_exposure_ratio >= 0.3:
        confidence = 0.55
    elif effective_exposure_ratio > 0:
        confidence = 0.35
    else:
        confidence = 0.2

    return round(raw_score * confidence, 1)


def compute_tier_grade(tier_score: float) -> str:
    """TierScore → TierGrade 변환."""
    if tier_score >= 35:
        return "S"
    elif tier_score >= 28:
        return "A"
    elif tier_score >= 20:
        return "B"
    elif tier_score >= 12:
        return "C"
    else:
        return "D"


# ===========================
# GoldenScore v5.0 헬퍼 함수
# ===========================

def _posting_intensity(interval_avg: Optional[float]) -> float:
    """포스팅 강도 (0~10): 가파른 단계형."""
    if interval_avg is None:
        return 0.0
    if interval_avg < 0.3:
        return 10.0
    elif interval_avg < 1.0:
        return 8.0
    elif interval_avg < 2.0:
        return 6.0
    elif interval_avg < 3.0:
        return 4.0
    elif interval_avg < 7.0:
        return 2.0
    else:
        return 0.0


def _originality_steep(originality_raw: float) -> float:
    """독창성 (0~5): 가파른 단계형 (originality_raw 0~8)."""
    if originality_raw >= 7.0:
        return 5.0
    elif originality_raw >= 6.5:
        return 4.0
    elif originality_raw >= 6.0:
        return 3.0
    elif originality_raw >= 5.5:
        return 2.0
    elif originality_raw >= 5.0:
        return 1.0
    else:
        return 0.0


def _diversity_steep(entropy: float) -> float:
    """주제 다양성 (0~10): 가파른 단계형 (entropy 0~1)."""
    if entropy >= 0.97:
        return 10.0
    elif entropy >= 0.95:
        return 8.0
    elif entropy >= 0.92:
        return 6.0
    elif entropy >= 0.88:
        return 4.0
    elif entropy >= 0.85:
        return 2.0
    else:
        return 0.0


def _richness_score(avg_desc_len: float) -> float:
    """충실도 (0~5): description 평균 길이."""
    if avg_desc_len >= 300:
        return 5.0
    elif avg_desc_len >= 200:
        return 4.0
    elif avg_desc_len >= 100:
        return 2.5
    else:
        return 1.0


def _sponsor_balance(sponsor_rate: float) -> float:
    """협찬 균형 (0~5)."""
    if 0.10 <= sponsor_rate <= 0.30:
        return 5.0
    elif (0.05 <= sponsor_rate < 0.10) or (0.30 < sponsor_rate <= 0.45):
        return 3.0
    elif sponsor_rate < 0.05:
        return 2.5
    elif 0.45 < sponsor_rate <= 0.60:
        return 1.5
    else:
        return 0.5


def compute_authority_grade(authority_score: float) -> str:
    """BlogAuthority (0~30) → AuthorityGrade 변환."""
    if authority_score >= 25:
        return "S"
    elif authority_score >= 20:
        return "A"
    elif authority_score >= 14:
        return "B"
    elif authority_score >= 8:
        return "C"
    else:
        return "D"


def golden_score_v5(
    region_power_hits: int,
    broad_query_hits: int,
    interval_avg: Optional[float],
    originality_raw: float,
    diversity_entropy: float,
    richness_avg_len: float,
    sponsor_signal_rate: float,
    cat_strength: int,
    cat_exposed: int,
    total_keywords: int,
    food_bias_rate: float = 0.0,
    is_food_cat: Optional[bool] = None,
    base_score_val: float = 0.0,
    weighted_strength: float = 0.0,
    keyword_match_ratio: float = 0.0,
    queries_hit_ratio: float = 0.0,
    has_category: bool = False,
) -> float:
    """
    GoldenScore v5.0 (0~100) = BlogAuthority(30) + CategoryExposure(25)
    + CategoryFit(15) + Freshness(10) + RSSQuality(20)
    """
    # 1. BlogAuthority (0~30)
    # CrossCatAuthority (0~15)
    if region_power_hits >= 3:
        cross_rp = 10.0
    elif region_power_hits >= 2:
        cross_rp = 7.0
    elif region_power_hits >= 1:
        cross_rp = 4.0
    else:
        cross_rp = 0.0

    if broad_query_hits >= 3:
        cross_broad = 5.0
    elif broad_query_hits >= 2:
        cross_broad = 3.0
    elif broad_query_hits >= 1:
        cross_broad = 1.5
    else:
        cross_broad = 0.0

    cross_cat_authority = min(15.0, cross_rp + cross_broad)
    posting_intensity = _posting_intensity(interval_avg)
    originality = _originality_steep(originality_raw)
    blog_authority = min(30.0, cross_cat_authority + posting_intensity + originality)

    # 2. CategoryExposure (0~25)
    effective_strength = weighted_strength if weighted_strength > 0 else float(cat_strength)
    max_strength = total_keywords * 3
    strength_part = min(1.0, effective_strength / max(1, max_strength)) * 15.0
    coverage_part = min(1.0, cat_exposed / max(1, total_keywords * 0.5)) * 10.0
    cat_exposure = strength_part + coverage_part

    # 3. CategoryFit (키워드 기반 추가 보너스, 0~15)
    if not has_category:
        category_fit = 0.0  # 카테고리 없음: 순수 블로그 지수만 비교
    else:
        exposure_ratio = cat_exposed / max(1, total_keywords)
        fit = keyword_match_ratio * 0.4 + exposure_ratio * 0.3 + queries_hit_ratio * 0.3
        category_fit = fit * 15.0

    # 4. Freshness (0~10)
    freshness = (base_score_val / 80.0) * 10.0

    # 5. RSSQuality (0~20)
    diversity = _diversity_steep(diversity_entropy)
    richness = _richness_score(richness_avg_len)
    sponsor_bal = _sponsor_balance(sponsor_signal_rate)
    rss_quality = diversity + richness + sponsor_bal

    raw_score = blog_authority + cat_exposure + category_fit + freshness + rss_quality
    return round(min(100.0, max(0.0, raw_score)), 1)


# ===========================
# GoldenScore v7.0 함수
# ===========================

def compute_simhash(text: str) -> int:
    """64비트 SimHash 핑거프린트 (한국어 3-gram 기반)."""
    if not text:
        return 0
    # 3-gram 추출
    tokens = [text[i:i+3] for i in range(max(1, len(text) - 2))]
    v = [0] * 64
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8", errors="replace")).hexdigest(), 16)
        for i in range(64):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(h1: int, h2: int) -> int:
    """두 SimHash 간 해밍 거리 (0~64)."""
    x = h1 ^ h2
    return bin(x).count("1")


def compute_near_duplicate_rate(rss_posts: List[Any]) -> float:
    """SimHash 기반 근사 중복률 (0~1). 해밍 거리 ≤ 3이면 근사 중복."""
    if len(rss_posts) < 2:
        return 0.0
    descriptions = [getattr(p, "description", "") or "" for p in rss_posts]
    hashes = [compute_simhash(d) for d in descriptions[:20]]
    total_pairs = 0
    dup_pairs = 0
    for i in range(len(hashes)):
        for j in range(i + 1, min(i + 5, len(hashes))):
            total_pairs += 1
            if hamming_distance(hashes[i], hashes[j]) <= 3:
                dup_pairs += 1
    if total_pairs == 0:
        return 0.0
    return dup_pairs / total_pairs


def compute_originality_v7(rss_posts: List[Any]) -> float:
    """SimHash 기반 독창성 (0~8). 중복률이 낮을수록 높은 점수."""
    dup_rate = compute_near_duplicate_rate(rss_posts)
    return round(8.0 * (1.0 - min(1.0, dup_rate)), 1)


def compute_diversity_smoothed(rss_posts: List[Any]) -> float:
    """Bayesian smoothed 엔트로피 (Dirichlet prior, 0~1)."""
    if not rss_posts:
        return 0.0

    words: List[str] = []
    for p in rss_posts:
        title = getattr(p, "title", "") or ""
        tokens = re.findall(r"[가-힣]{2,}", title)
        words.extend(tokens)

    if not words:
        return 0.0

    counter = Counter(words)
    vocab_size = len(counter)
    if vocab_size <= 1:
        return 0.0

    total = sum(counter.values())
    alpha = 1.0  # Dirichlet prior (symmetric)
    adjusted_total = total + alpha * vocab_size

    entropy = 0.0
    for count in counter.values():
        p = (count + alpha) / adjusted_total
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(vocab_size + alpha * vocab_size / adjusted_total * vocab_size)
    if max_entropy <= 0:
        max_entropy = math.log2(vocab_size)

    if max_entropy <= 0:
        return 0.0
    return round(min(1.0, entropy / max_entropy), 3)


def compute_topic_focus(rss_posts: List[Any], match_keywords: List[str]) -> float:
    """RSS 키워드 집중도 (0~1). 포스트 제목에 매칭 키워드 포함 비율."""
    if not rss_posts or not match_keywords:
        return 0.0
    match_count = 0
    for p in rss_posts:
        title = (getattr(p, "title", "") or "").lower()
        if any(kw.lower() in title for kw in match_keywords):
            match_count += 1
    return round(match_count / len(rss_posts), 3)


def compute_topic_continuity(rss_posts: List[Any], match_keywords: List[str]) -> float:
    """최근 10개 포스트 키워드 연속성 (0~1)."""
    if not rss_posts or not match_keywords:
        return 0.0
    recent = rss_posts[:10]
    match_count = 0
    for p in recent:
        title = (getattr(p, "title", "") or "").lower()
        if any(kw.lower() in title for kw in match_keywords):
            match_count += 1
    return round(match_count / len(recent), 3)


def compute_game_defense(rss_posts: List[Any], rss_data: dict = None) -> float:
    """GameDefense (0 to -10): Thin content/키워드스터핑/템플릿 남용 감점."""
    if not rss_posts:
        return 0.0

    penalty = 0.0

    # 1. Thin content (-4): 평균 description 길이 < 500 + 포스팅 간격 < 0.5일
    descriptions = [getattr(p, "description", "") or "" for p in rss_posts]
    avg_len = sum(len(d) for d in descriptions) / max(1, len(descriptions))
    interval = (rss_data or {}).get("interval_avg")
    if avg_len < 500 and interval is not None and interval < 0.5:
        penalty -= 4.0

    # 2. 키워드 스터핑 (-3): 제목 내 동일 단어 3회+ 반복 비율 ≥ 30%
    stuffing_count = 0
    for p in rss_posts:
        title = getattr(p, "title", "") or ""
        words = re.findall(r"[가-힣]{2,}", title)
        if words:
            counter = Counter(words)
            most_common_count = counter.most_common(1)[0][1]
            if most_common_count >= 3:
                stuffing_count += 1
    if len(rss_posts) > 0 and stuffing_count / len(rss_posts) >= 0.30:
        penalty -= 3.0

    # 3. 템플릿 남용 (-3): SimHash near-duplicate rate ≥ 50%
    dup_rate = compute_near_duplicate_rate(rss_posts)
    if dup_rate >= 0.50:
        penalty -= 3.0

    return max(-10.0, penalty)


def compute_quality_floor(
    base_score_val: float,
    rss_success: bool,
    exposure_count: int,
    seed_page1_count: int,
) -> float:
    """QualityFloor (0 to +5): 데이터 부족 보정 보너스."""
    bonus = 0.0
    # base≥60 + RSS 실패: +3
    if base_score_val >= 60 and not rss_success:
        bonus += 3.0
    # base≥50 + 노출≤2 + seed_page1≥2: +2
    if base_score_val >= 50 and exposure_count <= 2 and seed_page1_count >= 2:
        bonus += 2.0
    return min(5.0, bonus)


def _sponsor_fit(rate: float) -> float:
    """SponsorFit (0~5): 협찬률 적합도 (sweet spot 10-30%)."""
    if 0.10 <= rate <= 0.30:
        return 5.0
    elif (0.05 <= rate < 0.10) or (0.30 < rate <= 0.45):
        return 3.0
    elif rate < 0.05:
        return 2.5
    elif 0.45 < rate <= 0.60:
        return 1.5
    else:
        return 0.5


def _freshness_time_based(days: Optional[int]) -> float:
    """시간 기반 Freshness (0~10): days_since_last_post."""
    if days is None:
        return 0.0
    if days <= 3:
        return 10.0
    elif days <= 7:
        return 8.0
    elif days <= 14:
        return 6.0
    elif days <= 30:
        return 4.0
    elif days <= 60:
        return 2.0
    else:
        return 0.0


def golden_score_v7(
    region_power_hits: int,
    broad_query_hits: int,
    interval_avg: Optional[float],
    originality_raw: float,
    diversity_entropy: float,
    richness_avg_len: float,
    sponsor_signal_rate: float,
    cat_strength: int,
    cat_exposed: int,
    total_keywords: int,
    food_bias_rate: float = 0.0,
    is_food_cat: Optional[bool] = None,
    base_score_val: float = 0.0,
    weighted_strength: float = 0.0,
    keyword_match_ratio: float = 0.0,
    queries_hit_ratio: float = 0.0,
    has_category: bool = False,
    popularity_cross_score: float = 0.0,
    page1_keywords: int = 0,
    topic_focus: float = 0.0,
    topic_continuity: float = 0.0,
    days_since_last_post: Optional[int] = None,
    rss_originality_v7: float = 0.0,
    rss_diversity_smoothed: float = 0.0,
    game_defense: float = 0.0,
    quality_floor: float = 0.0,
) -> float:
    """
    GoldenScore v7.0 (0~100) = 9축 통합
    BlogAuthority(22) + CategoryExposure(18) + TopExposureProxy(12) + CategoryFit(15)
    + Freshness(10) + RSSQuality(13) + SponsorFit(5) + GameDefense(-10) + QualityFloor(+5)
    """
    # 1. BlogAuthority (0~22): CrossCat(0~12) + PostingIntensity(0~6) + Originality(0~4)
    if region_power_hits >= 3:
        cross_rp = 8.0
    elif region_power_hits >= 2:
        cross_rp = 5.5
    elif region_power_hits >= 1:
        cross_rp = 3.0
    else:
        cross_rp = 0.0

    if broad_query_hits >= 3:
        cross_broad = 4.0
    elif broad_query_hits >= 2:
        cross_broad = 2.5
    elif broad_query_hits >= 1:
        cross_broad = 1.0
    else:
        cross_broad = 0.0

    cross_cat = min(12.0, cross_rp + cross_broad)
    posting_i = _posting_intensity(interval_avg)
    posting_part = posting_i * 0.6  # 0~6
    orig_part = _originality_steep(originality_raw) * 0.8  # 0~4
    blog_authority = min(22.0, cross_cat + posting_part + orig_part)

    # 2. CategoryExposure (0~18): Strength(0~11) + Coverage(0~7)
    effective_strength = weighted_strength if weighted_strength > 0 else float(cat_strength)
    max_strength = total_keywords * 3
    strength_part = min(1.0, effective_strength / max(1, max_strength)) * 11.0
    coverage_part = min(1.0, cat_exposed / max(1, total_keywords * 0.5)) * 7.0
    cat_exposure = strength_part + coverage_part

    # 3. TopExposureProxy (0~12): popularity_cross(0~8) + page1_ratio(0~4)
    pop_cross = popularity_cross_score * 8.0  # 0~8
    page1_ratio = page1_keywords / max(1, total_keywords)
    if page1_ratio >= 0.3:
        page1_part = 4.0
    elif page1_ratio >= 0.2:
        page1_part = 3.0
    elif page1_ratio >= 0.1:
        page1_part = 2.0
    elif page1_ratio > 0:
        page1_part = 1.0
    else:
        page1_part = 0.0
    top_exp_proxy = min(12.0, pop_cross + page1_part)

    # 4. CategoryFit (0~15): 5-signal 가중평균 × 15
    if not has_category:
        category_fit = 0.0
    else:
        exposure_ratio = cat_exposed / max(1, total_keywords)
        qh_ratio = queries_hit_ratio
        # 5-signal: kw_match(0.20) + exposure_ratio(0.20) + qh_ratio(0.15) + topic_focus(0.25) + topic_continuity(0.20)
        fit = (keyword_match_ratio * 0.20
               + exposure_ratio * 0.20
               + qh_ratio * 0.15
               + topic_focus * 0.25
               + topic_continuity * 0.20)
        category_fit = fit * 15.0

    # 5. Freshness (0~10): 시간 기반
    freshness = _freshness_time_based(days_since_last_post)

    # 6. RSSQuality (0~13): Diversity(0~6) + Richness(0~4) + Originality bonus(0~3)
    div_score = rss_diversity_smoothed * 6.0  # 0~6
    if richness_avg_len >= 300:
        rich_score = 4.0
    elif richness_avg_len >= 200:
        rich_score = 3.0
    elif richness_avg_len >= 100:
        rich_score = 2.0
    else:
        rich_score = 1.0
    orig_bonus = min(3.0, rss_originality_v7 / 8.0 * 3.0)  # 0~3
    rss_quality = min(13.0, div_score + rich_score + orig_bonus)

    # 7. SponsorFit (0~5)
    sponsor_fit = _sponsor_fit(sponsor_signal_rate)

    # 8. GameDefense (0 to -10)
    gd = max(-10.0, min(0.0, game_defense))

    # 9. QualityFloor (0 to +5)
    qf = max(0.0, min(5.0, quality_floor))

    raw = blog_authority + cat_exposure + top_exp_proxy + category_fit + freshness + rss_quality + sponsor_fit + gd + qf
    return round(max(0.0, min(100.0, raw)), 1)


def golden_score_v4(
    tier_score: float,
    cat_strength: int,
    cat_exposed: int,
    total_keywords: int,
    food_bias_rate: float = 0.0,
    is_food_cat: Optional[bool] = None,
    base_score_val: float = 0.0,
    weighted_strength: float = 0.0,
    keyword_match_ratio: float = 0.0,
    queries_hit_ratio: float = 0.0,
    has_category: bool = False,
) -> float:
    """
    GoldenScore v4.0 (0~100) = TierScore(40) + CategoryExposure(35) + CategoryFit(15) + Freshness(10)

    - TierScore: RSS 기반 순수체급 (이미 계산되어 전달됨, 0~40)
    - CategoryExposure: 업종 키워드 노출 강도 + 커버리지 (0~35)
    - CategoryFit: 업종 적합도 (0~15)
    - Freshness: 최근활동/SERP 순위/빈도 반영 (0~10)
    - Recruitability 제거 (태그만 유지)
    """
    # 1. TierScore (0~40, 이미 계산됨)
    tier = min(40.0, max(0.0, tier_score))

    # 2. CategoryExposure (0~35): strength(20) + coverage(15)
    effective_strength = weighted_strength if weighted_strength > 0 else float(cat_strength)
    max_strength = total_keywords * 3
    strength_part = min(1.0, effective_strength / max(1, max_strength)) * 20.0
    coverage_part = min(1.0, cat_exposed / max(1, total_keywords * 0.5)) * 15.0
    cat_exposure = strength_part + coverage_part

    # 3. CategoryFit (키워드 기반 추가 보너스, 0~15)
    if not has_category:
        category_fit = 0.0  # 카테고리 없음: 순수 블로그 지수만 비교
    else:
        exposure_ratio = cat_exposed / max(1, total_keywords)
        fit = keyword_match_ratio * 0.4 + exposure_ratio * 0.3 + queries_hit_ratio * 0.3
        category_fit = fit * 15.0

    # 4. Freshness (0~10): base_score 기반
    freshness = (base_score_val / 80.0) * 10.0

    raw_score = tier + cat_exposure + category_fit + freshness
    return round(min(100.0, max(0.0, raw_score)), 1)


# ===========================
# 블로그 단독 분석 전용 스코어링
# ===========================

def _recent_activity_score(days_since: Optional[int]) -> float:
    """최근 활동 점수 (0~15): 30일 기준 step curve."""
    if days_since is None:
        return 0.0
    if days_since <= 3:
        return 15.0
    elif days_since <= 7:
        return 12.0
    elif days_since <= 14:
        return 9.0
    elif days_since <= 30:
        return 6.0
    elif days_since <= 60:
        return 3.0
    else:
        return 0.0


def _richness_expanded(avg_len: float) -> float:
    """콘텐츠 충실도 확장 (0~12): description 평균 길이."""
    if avg_len >= 400:
        return 12.0
    elif avg_len >= 300:
        return 10.0
    elif avg_len >= 200:
        return 7.0
    elif avg_len >= 100:
        return 4.0
    else:
        return 1.0


def _post_volume_score(total_posts: int) -> float:
    """포스트 수량 점수 (0~8)."""
    if total_posts >= 40:
        return 8.0
    elif total_posts >= 25:
        return 6.0
    elif total_posts >= 15:
        return 4.0
    elif total_posts >= 5:
        return 2.0
    else:
        return 0.0


def _richness_store(avg_len: float) -> float:
    """RSS 품질 충실도 (0~8): 매장 연계용."""
    if avg_len >= 400:
        return 8.0
    elif avg_len >= 300:
        return 7.0
    elif avg_len >= 200:
        return 5.0
    elif avg_len >= 100:
        return 3.0
    else:
        return 1.0


def _sponsor_balance_store(rate: float) -> float:
    """협찬 균형 확장 (0~7): 매장 연계용."""
    if 0.10 <= rate <= 0.30:
        return 7.0
    elif (0.05 <= rate < 0.10) or (0.30 < rate <= 0.45):
        return 4.5
    elif rate < 0.05:
        return 3.5
    elif 0.45 < rate <= 0.60:
        return 2.0
    else:
        return 1.0


def blog_analysis_score(
    *,
    interval_avg: Optional[float],
    originality_raw: float,
    diversity_entropy: float,
    richness_avg_len: float,
    sponsor_signal_rate: float,
    strength_sum: int,
    exposed_keywords: int,
    total_keywords: int,
    food_bias_rate: float,
    weighted_strength: float = 0.0,
    days_since_last_post: Optional[int] = None,
    total_posts: int = 0,
    store_profile_present: bool = False,
    is_food_cat: Optional[bool] = None,
    keyword_match_ratio: float = 0.0,
    has_category: bool = False,
) -> tuple:
    """
    블로그 단독/매장연계 분석 전용 점수 (0~100).
    golden_score_v5()와 분리 — 파이프라인 전용 데이터(region_power, broad 등) 불필요.

    Returns:
        (total_score, breakdown_dict)
        breakdown_dict: {key: {"score": float, "max": int, "label": str}}
    """
    eff_strength = weighted_strength if weighted_strength > 0 else float(strength_sum)
    max_str = max(1, total_keywords) * 3
    str_part = min(1.0, eff_strength / max(1, max_str))
    cov_part = min(1.0, exposed_keywords / max(1, max(1, total_keywords) * 0.5))

    posting_i = _posting_intensity(interval_avg)
    orig_s = _originality_steep(originality_raw)
    recent = _recent_activity_score(days_since_last_post)

    if not store_profile_present:
        # === 단독 분석 모드 ===
        # 포스팅 활동 (0~25): PostingIntensity(15) + Originality(10)
        posting_activity = posting_i * 1.5 + orig_s * 2.0

        # 검색 노출 (0~25): Strength(15) + Coverage(10)
        search_exposure = str_part * 15.0 + cov_part * 10.0

        # 콘텐츠 다양성 (0~15): Diversity(10) + SponsorBalance(5)
        diversity = _diversity_steep(diversity_entropy)
        sponsor_bal = _sponsor_balance(sponsor_signal_rate)
        content_diversity = diversity + sponsor_bal

        # 콘텐츠 충실도 (0~20): Richness(12) + PostVolume(8)
        richness = _richness_expanded(richness_avg_len)
        volume = _post_volume_score(total_posts)
        content_richness = richness + volume

        total = posting_activity + search_exposure + recent + content_diversity + content_richness
        total = round(min(100.0, max(0.0, total)), 1)

        breakdown = {
            "posting_activity": {"score": round(posting_activity, 1), "max": 25, "label": "포스팅 활동"},
            "search_exposure": {"score": round(search_exposure, 1), "max": 25, "label": "검색 노출"},
            "recent_activity": {"score": round(recent, 1), "max": 15, "label": "최근 활동"},
            "content_diversity": {"score": round(content_diversity, 1), "max": 15, "label": "콘텐츠 다양성"},
            "content_richness": {"score": round(content_richness, 1), "max": 20, "label": "콘텐츠 충실도"},
        }
    else:
        # === 매장 연계 분석 모드 ===
        # 포스팅 활동 (0~20): PostingIntensity(12) + Originality(8)
        posting_activity = posting_i * 1.2 + orig_s * 1.6

        # 업종 노출 (0~25): Strength(15) + Coverage(10)
        category_exposure = str_part * 15.0 + cov_part * 10.0

        # 업종 적합도 (0~15): 키워드 기반 추가 보너스 (2-signal, seed 없음)
        if not has_category:
            category_fit = 0.0
        else:
            exposure_ratio = exposed_keywords / max(1, total_keywords)
            fit = keyword_match_ratio * 0.6 + exposure_ratio * 0.4
            category_fit = fit * 15.0

        # RSS 품질 (0~25): Diversity(10) + Richness(8) + SponsorBalance(7)
        diversity = _diversity_steep(diversity_entropy)
        richness = _richness_store(richness_avg_len)
        sponsor_bal = _sponsor_balance_store(sponsor_signal_rate)
        rss_quality = diversity + richness + sponsor_bal

        total = posting_activity + category_exposure + category_fit + recent + rss_quality
        total = round(min(100.0, max(0.0, total)), 1)

        breakdown = {
            "posting_activity": {"score": round(posting_activity, 1), "max": 20, "label": "포스팅 활동"},
            "category_exposure": {"score": round(category_exposure, 1), "max": 25, "label": "업종 노출"},
            "category_fit": {"score": round(category_fit, 1), "max": 15, "label": "업종 적합도"},
            "recent_activity": {"score": round(recent, 1), "max": 15, "label": "최근 활동"},
            "rss_quality": {"score": round(rss_quality, 1), "max": 25, "label": "RSS 품질"},
        }

    return total, breakdown


def performance_score(strength_sum: int, exposed_keywords: int, total_keywords: int = 7) -> float:
    """
    Performance Score (0~100):
    - strength 기반 70%: (strength_sum / 35) * 70
    - 노출 키워드 커버리지 30%: (exposed_keywords / total_keywords) * 30
    """
    strength_part = min(1.0, strength_sum / 35.0) * 70.0
    coverage_part = min(1.0, exposed_keywords / max(1, total_keywords)) * 30.0
    return round(strength_part + coverage_part, 1)
