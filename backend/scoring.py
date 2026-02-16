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
    # v7.1 신규
    neighbor_count: int = 0,
    blog_years: float = 0.0,
    estimated_tier: str = "unknown",
    image_ratio: float = 0.0,
    video_ratio: float = 0.0,
    rss_originality_v7: float = 0.0,
    rss_diversity_smoothed: float = 0.0,
    rss_posts: Optional[List[Any]] = None,
    popularity_cross_score: float = 0.0,
    base_score_val: float = 0.0,
    game_defense: float = 0.0,
    quality_floor: float = 0.0,
    tfidf_sim: float = 0.0,
    topic_focus: float = 0.0,
    topic_continuity: float = 0.0,
    queries_hit_ratio: float = 0.0,
) -> tuple:
    """
    블로그 단독/매장연계 분석 전용 점수 — v7.1 Base Score 구조.

    Returns:
        (result_dict)
        result_dict: golden_score_v71() 호환 구조
    """
    # 블로그 분석에서는 ranks가 없으므로 exposure 기반으로 근사
    # 검색 노출 데이터로 가상 ranks 구성
    virtual_ranks: List[int] = []
    if exposed_keywords > 0:
        eff_str = weighted_strength if weighted_strength > 0 else float(strength_sum)
        avg_str = eff_str / max(1, exposed_keywords)
        for _ in range(exposed_keywords):
            if avg_str >= 4:
                virtual_ranks.append(3)
            elif avg_str >= 2.5:
                virtual_ranks.append(8)
            elif avg_str >= 1.5:
                virtual_ranks.append(15)
            else:
                virtual_ranks.append(25)

    result = golden_score_v71(
        queries_hit_count=exposed_keywords,
        total_query_count=max(1, total_keywords),
        ranks=virtual_ranks if virtual_ranks else None,
        popularity_cross_score=popularity_cross_score,
        broad_query_hits=0,
        region_power_hits=0,
        estimated_tier=estimated_tier,
        neighbor_count=neighbor_count,
        blog_years=blog_years,
        interval_avg=interval_avg,
        richness_avg_len=richness_avg_len,
        rss_originality_v7=rss_originality_v7 if rss_originality_v7 > 0 else originality_raw,
        rss_diversity_smoothed=rss_diversity_smoothed if rss_diversity_smoothed > 0 else diversity_entropy,
        image_ratio=image_ratio,
        video_ratio=video_ratio,
        days_since_last_post=days_since_last_post,
        rss_posts=rss_posts,
        base_score_val=base_score_val,
        sponsor_signal_rate=sponsor_signal_rate,
        game_defense=game_defense,
        quality_floor=quality_floor,
        has_category=has_category and store_profile_present,
        keyword_match_ratio=keyword_match_ratio,
        exposure_ratio=exposed_keywords / max(1, total_keywords),
        queries_hit_ratio=queries_hit_ratio,
        topic_focus=topic_focus,
        topic_continuity=topic_continuity,
        tfidf_sim=tfidf_sim,
        cat_strength=strength_sum,
        cat_exposed=exposed_keywords,
        total_keywords=total_keywords,
        weighted_strength=weighted_strength,
    )

    # 하위 호환: (total_score, breakdown_dict) 형태 유지
    total = result["base_score"]
    breakdown = result["base_breakdown"]

    return total, breakdown, result


# ===========================
# GoldenScore v7.1 함수 (3모드 분석 + 2단계 점수 체계)
# ===========================

def compute_exposure_power(
    queries_hit_count: int,
    total_query_count: int,
    ranks: List[int],
    popularity_cross_score: float = 0.0,
    broad_query_hits: int = 0,
    region_power_hits: int = 0,
) -> float:
    """ExposurePower v7.1 (0~30): 4개 하위 항목.

    1. SERP 등장 빈도 (0~12)
    2. 순위 분포 (0~10)
    3. 인기순 교차검증 (0~5)
    4. 노출 다양성 (0~3)
    """
    # 1. SERP 등장 빈도 (0~12)
    if total_query_count > 0:
        ratio = queries_hit_count / total_query_count
    else:
        ratio = 0.0
    serp_freq = min(12.0, ratio * 12.0)

    # 2. 순위 분포 (0~10)
    if ranks:
        avg_rank = sum(ranks) / len(ranks)
        rank_score = max(0.0, 10.0 * (1 - min(avg_rank, 30) / 30))
        # top5/top10 카운트 보너스
        top5 = sum(1 for r in ranks if r <= 5)
        top10 = sum(1 for r in ranks if r <= 10)
        if top5 >= 3:
            rank_score = min(10.0, rank_score + 2.0)
        elif top10 >= 3:
            rank_score = min(10.0, rank_score + 1.0)
    else:
        rank_score = 0.0

    # 3. 인기순 교차검증 (0~5)
    pop_score = popularity_cross_score * 5.0

    # 4. 노출 다양성 (0~3): seed/popularity/broad/region_power 교차 등장
    diversity_count = 0
    if queries_hit_count > 0:
        diversity_count += 1  # seed
    if popularity_cross_score > 0:
        diversity_count += 1  # popularity
    if broad_query_hits > 0:
        diversity_count += 1  # broad
    if region_power_hits > 0:
        diversity_count += 1  # region_power
    diversity_score = min(3.0, diversity_count * 0.75)

    total = serp_freq + rank_score + pop_score + diversity_score
    return round(min(30.0, max(0.0, total)), 1)


def compute_blog_authority_v71(
    estimated_tier: str,
    neighbor_count: int,
    blog_years: float,
    interval_avg: Optional[float],
) -> float:
    """BlogAuthority v7.1 (0~22): 4개 하위 항목.

    1. 블로그 등급 추정 (0~10)
    2. 이웃 수 기반 영향력 (0~5)
    3. 블로그 운영 기간 (0~4)
    4. 포스팅 꾸준함 (0~3)
    """
    # 1. 블로그 등급 추정 (0~10)
    tier_map = {"power": 10.0, "premium": 8.0, "gold": 6.0, "silver": 4.0, "normal": 2.0, "unknown": 1.0}
    tier_score = tier_map.get(estimated_tier, 1.0)

    # 2. 이웃 수 기반 영향력 (0~5)
    if neighbor_count >= 5000:
        neighbor_score = 5.0
    elif neighbor_count >= 2000:
        neighbor_score = 4.0
    elif neighbor_count >= 1000:
        neighbor_score = 3.0
    elif neighbor_count >= 500:
        neighbor_score = 2.0
    elif neighbor_count >= 100:
        neighbor_score = 1.0
    else:
        neighbor_score = 0.0

    # 3. 블로그 운영 기간 (0~4)
    if blog_years >= 5:
        years_score = 4.0
    elif blog_years >= 3:
        years_score = 3.0
    elif blog_years >= 2:
        years_score = 2.0
    elif blog_years >= 1:
        years_score = 1.0
    else:
        years_score = 0.0

    # 4. 포스팅 꾸준함 (0~3)
    if interval_avg is None:
        posting_score = 0.0
    elif interval_avg <= 2:
        posting_score = 3.0
    elif interval_avg <= 5:
        posting_score = 2.0
    elif interval_avg <= 10:
        posting_score = 1.0
    else:
        posting_score = 0.0

    total = tier_score + neighbor_score + years_score + posting_score
    return round(min(22.0, max(0.0, total)), 1)


def compute_rss_quality_v71(
    richness_avg_len: float,
    rss_originality_v7: float,
    rss_diversity_smoothed: float,
    image_ratio: float,
    video_ratio: float,
) -> float:
    """RSSQuality v7.1 (0~18): 4개 하위 항목.

    1. 글 길이/충실도 (0~5)
    2. Originality (0~4)
    3. Diversity (0~5)
    4. 미디어 활용도 (0~4)
    """
    # 1. 글 길이/충실도 (0~5)
    if richness_avg_len >= 3000:
        richness = 5.0
    elif richness_avg_len >= 2000:
        richness = 4.0
    elif richness_avg_len >= 1000:
        richness = 3.0
    elif richness_avg_len >= 500:
        richness = 2.0
    elif richness_avg_len >= 200:
        richness = 1.0
    else:
        richness = 0.0

    # 2. Originality (0~4): SimHash 기반 (0~8 → 0~4 스케일)
    orig = min(4.0, rss_originality_v7 / 8.0 * 4.0)

    # 3. Diversity (0~5): Bayesian smoothed (0~1 → 0~5)
    div = min(5.0, rss_diversity_smoothed * 5.0)

    # 4. 미디어 활용도 (0~4)
    media = 0.0
    if image_ratio >= 0.8:
        media += 3.0
    elif image_ratio >= 0.5:
        media += 2.0
    elif image_ratio >= 0.2:
        media += 1.0
    if video_ratio >= 0.1:
        media += 1.0
    media = min(4.0, media)

    total = richness + orig + div + media
    return round(min(18.0, max(0.0, total)), 1)


def compute_freshness_v71(
    days_since_last_post: Optional[int],
    rss_posts: Optional[List[Any]] = None,
) -> float:
    """Freshness v7.1 (0~12): 3개 하위 항목.

    1. 최신 글 발행일 (0~6)
    2. 최근 30일 발행 빈도 (0~4)
    3. 발행 연속성 (0~2): 최근 3개월 매월 1건 이상
    """
    # 1. 최신 글 발행일 (0~6)
    if days_since_last_post is None:
        recent = 0.0
    elif days_since_last_post <= 3:
        recent = 6.0
    elif days_since_last_post <= 7:
        recent = 5.0
    elif days_since_last_post <= 14:
        recent = 4.0
    elif days_since_last_post <= 30:
        recent = 3.0
    elif days_since_last_post <= 60:
        recent = 1.0
    else:
        recent = 0.0

    # 2. 최근 30일 발행 빈도 (0~4)
    freq = 0.0
    if rss_posts:
        now = datetime.now()
        recent_30d = 0
        for p in rss_posts:
            pub = None
            pub_str = getattr(p, "pub_date", None)
            if pub_str:
                for fmt in (
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d",
                ):
                    try:
                        pub = datetime.strptime(pub_str.strip(), fmt).replace(tzinfo=None)
                        break
                    except (ValueError, TypeError):
                        continue
            if pub and (now - pub).days <= 30:
                recent_30d += 1
        if recent_30d >= 10:
            freq = 4.0
        elif recent_30d >= 6:
            freq = 3.0
        elif recent_30d >= 3:
            freq = 2.0
        elif recent_30d >= 1:
            freq = 1.0

    # 3. 발행 연속성 (0~2): 최근 3개월 매월 1건 이상
    continuity = 0.0
    if rss_posts:
        now = datetime.now()
        months_with_post = set()
        for p in rss_posts:
            pub = None
            pub_str = getattr(p, "pub_date", None)
            if pub_str:
                for fmt in (
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d",
                ):
                    try:
                        pub = datetime.strptime(pub_str.strip(), fmt).replace(tzinfo=None)
                        break
                    except (ValueError, TypeError):
                        continue
            if pub and (now - pub).days <= 90:
                months_with_post.add((pub.year, pub.month))
        if len(months_with_post) >= 3:
            continuity = 2.0
        elif len(months_with_post) >= 2:
            continuity = 1.0

    return round(min(12.0, recent + freq + continuity), 1)


def compute_top_exposure_proxy_v71(
    popularity_cross_score: float,
    neighbor_count: int,
    base_score_val: float,
    ranks: Optional[List[int]] = None,
) -> float:
    """TopExposureProxy v7.1 (0~10): 3개 하위 항목.

    1. 인기순 교차검색 등장 (0~5)
    2. 이웃수×base_score 복합 (0~3)
    3. 관련도순 상위 노출 빈도 (0~2)
    """
    # 1. 인기순 교차검색 등장 (0~5)
    pop = popularity_cross_score * 5.0

    # 2. 이웃수×base_score 복합 (0~3)
    # 이웃 500+이면서 base 40+ → 상위 블로그 지수 추정
    composite = 0.0
    if neighbor_count >= 2000 and base_score_val >= 50:
        composite = 3.0
    elif neighbor_count >= 1000 and base_score_val >= 40:
        composite = 2.0
    elif neighbor_count >= 500 and base_score_val >= 30:
        composite = 1.0

    # 3. 관련도순 상위 노출 빈도 (0~2)
    top3 = 0.0
    if ranks:
        top3_count = sum(1 for r in ranks if r <= 3)
        if top3_count >= 3:
            top3 = 2.0
        elif top3_count >= 1:
            top3 = 1.0

    return round(min(10.0, pop + composite + top3), 1)


def compute_sponsor_fit_v71(
    sponsor_signal_rate: float,
    rss_posts: Optional[List[Any]] = None,
    richness_avg_len: float = 0.0,
) -> float:
    """SponsorFit v7.1 (0~8): 3개 하위 항목.

    1. 체험단/협찬 경험 (0~3)
    2. 글 퀄리티×체험단 조합 (0~3)
    3. 내돈내산 vs 협찬 비율 (0~2)
    """
    from backend.blog_analyzer import _SPONSORED_TITLE_SIGNALS

    # 1. 체험단/협찬 경험 (0~3)
    sponsor_count = 0
    if rss_posts:
        for p in rss_posts:
            title = getattr(p, "title", "") or ""
            if any(sig in title for sig in _SPONSORED_TITLE_SIGNALS):
                sponsor_count += 1
    if sponsor_count >= 5:
        exp_score = 3.0
    elif sponsor_count >= 3:
        exp_score = 2.0
    elif sponsor_count >= 1:
        exp_score = 1.0
    else:
        exp_score = 0.0

    # 2. 글 퀄리티×체험단 조합 (0~3)
    combo = 0.0
    if sponsor_count >= 1 and richness_avg_len >= 1000:
        combo = 3.0
    elif sponsor_count >= 1 and richness_avg_len >= 500:
        combo = 2.0
    elif sponsor_count >= 1:
        combo = 1.0

    # 3. 내돈내산 vs 협찬 비율 (0~2): 균형이 가장 좋음
    if 0.10 <= sponsor_signal_rate <= 0.30:
        balance = 2.0
    elif 0.05 <= sponsor_signal_rate < 0.10 or 0.30 < sponsor_signal_rate <= 0.45:
        balance = 1.0
    else:
        balance = 0.0

    return round(min(8.0, exp_score + combo + balance), 1)


def compute_category_fit_bonus(
    keyword_match_ratio: float,
    exposure_ratio: float,
    queries_hit_ratio: float,
    topic_focus: float,
    topic_continuity: float,
    tfidf_sim: float,
) -> float:
    """CategoryFit Bonus v7.1 (0~15, 모드C 전용).

    6-Signal 가중평균 × 15.
    """
    fit = (
        keyword_match_ratio * 0.10
        + exposure_ratio * 0.15
        + queries_hit_ratio * 0.10
        + topic_focus * 0.20
        + topic_continuity * 0.15
        + tfidf_sim * 0.30
    )
    return round(min(15.0, max(0.0, fit * 15.0)), 1)


def compute_category_exposure_bonus(
    exposure_rate: float,
    strength_avg: float,
) -> float:
    """CategoryExposure Bonus v7.1 (0~10, 모드C 전용).

    exposure_rate × 0.4 + strength_avg × 0.6 → × 10.
    """
    raw = exposure_rate * 0.4 + min(1.0, strength_avg / 5.0) * 0.6
    return round(min(10.0, max(0.0, raw * 10.0)), 1)


def golden_score_v71(
    # ExposurePower 입력
    queries_hit_count: int = 0,
    total_query_count: int = 0,
    ranks: Optional[List[int]] = None,
    popularity_cross_score: float = 0.0,
    broad_query_hits: int = 0,
    region_power_hits: int = 0,
    # BlogAuthority 입력
    estimated_tier: str = "unknown",
    neighbor_count: int = 0,
    blog_years: float = 0.0,
    interval_avg: Optional[float] = None,
    # RSSQuality 입력
    richness_avg_len: float = 0.0,
    rss_originality_v7: float = 0.0,
    rss_diversity_smoothed: float = 0.0,
    image_ratio: float = 0.0,
    video_ratio: float = 0.0,
    # Freshness 입력
    days_since_last_post: Optional[int] = None,
    rss_posts: Optional[List[Any]] = None,
    # TopExposureProxy 입력
    base_score_val: float = 0.0,
    # SponsorFit 입력
    sponsor_signal_rate: float = 0.0,
    # GameDefense & QualityFloor (기존 v7.0 그대로)
    game_defense: float = 0.0,
    quality_floor: float = 0.0,
    # CategoryBonus 입력 (모드C 전용)
    has_category: bool = False,
    keyword_match_ratio: float = 0.0,
    exposure_ratio: float = 0.0,
    queries_hit_ratio: float = 0.0,
    topic_focus: float = 0.0,
    topic_continuity: float = 0.0,
    tfidf_sim: float = 0.0,
    cat_strength: int = 0,
    cat_exposed: int = 0,
    total_keywords: int = 0,
    weighted_strength: float = 0.0,
) -> dict:
    """
    GoldenScore v7.1 (Base 0~100 + Category Bonus 0~25)

    Base Score 8축:
    - ExposurePower (0~30)
    - BlogAuthority (0~22)
    - RSSQuality (0~18)
    - Freshness (0~12)
    - TopExposureProxy (0~10)
    - SponsorFit (0~8)
    - GameDefense (0 to -10)
    - QualityFloor (0 to +5)
    → Raw 합산 후 0~100 정규화 (max raw = 105)

    Category Bonus (모드C):
    - CategoryFit (0~15)
    - CategoryExposure (0~10)
    → 0~25

    Returns dict with base_score, category_bonus, final_score, breakdowns, mode, grade.
    """
    # Base Score 8축
    ep = compute_exposure_power(
        queries_hit_count, total_query_count, ranks or [],
        popularity_cross_score, broad_query_hits, region_power_hits,
    )
    ba = compute_blog_authority_v71(estimated_tier, neighbor_count, blog_years, interval_avg)
    rq = compute_rss_quality_v71(richness_avg_len, rss_originality_v7, rss_diversity_smoothed, image_ratio, video_ratio)
    fr = compute_freshness_v71(days_since_last_post, rss_posts)
    te = compute_top_exposure_proxy_v71(popularity_cross_score, neighbor_count, base_score_val, ranks)
    sf = compute_sponsor_fit_v71(sponsor_signal_rate, rss_posts, richness_avg_len)
    gd = max(-10.0, min(0.0, game_defense))
    qf = max(0.0, min(5.0, quality_floor))

    raw_base = ep + ba + rq + fr + te + sf + gd + qf
    # 정규화: max raw = 30+22+18+12+10+8+0+5 = 105 → 0~100
    base_score_val_v71 = round(max(0.0, min(100.0, raw_base / 105.0 * 100.0)), 1)

    base_breakdown = {
        "exposure_power": {"score": ep, "max": 30, "label": "검색 노출력"},
        "blog_authority": {"score": ba, "max": 22, "label": "블로그 권위"},
        "rss_quality": {"score": rq, "max": 18, "label": "RSS 품질"},
        "freshness": {"score": fr, "max": 12, "label": "최신성"},
        "top_exposure_proxy": {"score": te, "max": 10, "label": "상위노출 지수"},
        "sponsor_fit": {"score": sf, "max": 8, "label": "체험단 적합도"},
        "game_defense": {"score": gd, "max": 0, "label": "어뷰징 감점"},
        "quality_floor": {"score": qf, "max": 5, "label": "품질 보정"},
    }

    # Category Bonus (모드C)
    category_bonus = None
    bonus_breakdown = None
    analysis_mode = "region"

    if has_category:
        analysis_mode = "category"
        cf = compute_category_fit_bonus(
            keyword_match_ratio, exposure_ratio, queries_hit_ratio,
            topic_focus, topic_continuity, tfidf_sim,
        )

        # CategoryExposure: exposure_rate + strength_avg
        if total_keywords > 0:
            exp_rate = cat_exposed / max(1, total_keywords)
            eff_str = weighted_strength if weighted_strength > 0 else float(cat_strength)
            str_avg = eff_str / max(1, cat_exposed) if cat_exposed > 0 else 0.0
        else:
            exp_rate = 0.0
            str_avg = 0.0
        ce = compute_category_exposure_bonus(exp_rate, str_avg)

        category_bonus = round(cf + ce, 1)
        bonus_breakdown = {
            "category_fit": {"score": cf, "max": 15, "label": "업종 적합도"},
            "category_exposure": {"score": ce, "max": 10, "label": "업종 노출"},
        }

    # Final Score
    if category_bonus is not None:
        final_score = round(base_score_val_v71 + category_bonus, 1)
    else:
        final_score = base_score_val_v71

    grade = assign_grade_v71(base_score_val_v71)

    return {
        "base_score": base_score_val_v71,
        "category_bonus": category_bonus,
        "final_score": final_score,
        "base_breakdown": base_breakdown,
        "bonus_breakdown": bonus_breakdown,
        "analysis_mode": analysis_mode,
        "grade": grade,
        "grade_label": _grade_label_v71(grade),
    }


def assign_grade_v71(base_score_val: float) -> str:
    """v7.1 등급 판정 (항상 Base Score 기준)."""
    if base_score_val >= 80:
        return "S"
    elif base_score_val >= 65:
        return "A"
    elif base_score_val >= 50:
        return "B"
    elif base_score_val >= 35:
        return "C"
    else:
        return "D"


def _grade_label_v71(grade: str) -> str:
    labels = {"S": "최우수", "A": "우수", "B": "보통", "C": "미흡", "D": "부적합"}
    return labels.get(grade, "부적합")


def performance_score(strength_sum: int, exposed_keywords: int, total_keywords: int = 7) -> float:
    """
    Performance Score (0~100):
    - strength 기반 70%: (strength_sum / 35) * 70
    - 노출 키워드 커버리지 30%: (exposed_keywords / total_keywords) * 30
    """
    strength_part = min(1.0, strength_sum / 35.0) * 70.0
    coverage_part = min(1.0, exposed_keywords / max(1, total_keywords)) * 30.0
    return round(strength_part + coverage_part, 1)
