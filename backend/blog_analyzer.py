"""
블로그 개별 분석 엔진

RSS 피드 + 네이버 검색 API로 특정 블로거를 종합 분석.
두 가지 모드:
  A) 독립 분석: 블로그 URL만 → 포스트 제목에서 키워드 추출 → 범용 평가
  B) 매장 연계: 블로그 URL + 매장 → 매장 키워드 기반 노출력 평가
"""
from __future__ import annotations

import concurrent.futures
import logging
import math
import re
import statistics
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
from xml.etree import ElementTree

import requests

from backend.keywords import StoreProfile, build_exposure_keywords
from backend.models import (
    ActivityMetrics,
    BlogScoreResult,
    ContentMetrics,
    ExposureMetrics,
    QualityMetrics,
    RSSPost,
    SuitabilityMetrics,
)
from backend.naver_client import NaverBlogSearchClient
from backend.scoring import (
    FOOD_WORDS,
    SPONSOR_WORDS,
    is_food_category,
    keyword_weight_for_suffix,
    strength_points,
    blog_analysis_score,
    compute_simhash,
    hamming_distance,
)

logger = logging.getLogger(__name__)

ProgressCb = Callable[[dict], None]

# RSS에서 무시할 공통 불용어
_STOPWORDS = frozenset({
    "나의", "오늘", "일상", "하루", "이번", "그리고", "그런데", "하지만",
    "정말", "진짜", "너무", "아주", "매우", "좀", "약간",
    "있는", "없는", "하는", "되는", "같은", "통한", "위한",
    "것이", "것을", "것은", "에서", "으로", "에게",
    "블로그", "포스팅", "리뷰", "후기", "이벤트",
})


_SPONSORED_TITLE_SIGNALS = frozenset({
    "체험단", "협찬", "제공", "초대", "서포터즈", "원고료",
    "제공받", "소정의", "무료체험",
})

_FORBIDDEN_WORDS = frozenset({
    "최고", "최저", "100%", "완치", "보장", "무조건", "확실",
    "1등", "가장", "완벽", "기적", "특효",
})

_DISCLOSURE_PATTERNS = [
    "제공받아", "소정의 원고료", "업체로부터", "협찬을 받아",
    "무료로 제공", "체험단", "#협찬", "#광고",
]


_SYSTEM_PATHS = frozenset({
    "postview", "postlist", "bloglist", "prologue",
    "postview.naver", "postlist.naver",
    "postview.nhn", "postlist.nhn",
})


def extract_blogger_id(url_or_id: str) -> Optional[str]:
    """블로그 URL 또는 ID에서 blogger_id 추출."""
    text = url_or_id.strip()
    if not text:
        return None
    # 이미 순수 ID인 경우
    if re.fullmatch(r"[A-Za-z0-9._-]+", text):
        return text.lower()
    # 1순위: blogId 쿼리 파라미터
    m = re.search(r"(?:blogId|blogid)=([A-Za-z0-9._-]+)", text)
    if m:
        return m.group(1).lower()
    # 2순위: blog.naver.com/{id} 패턴 (시스템 경로 제외)
    m = re.search(r"(?:m\.)?blog\.naver\.com/([A-Za-z0-9._-]+)", text)
    if m:
        bid = m.group(1).lower()
        if bid not in _SYSTEM_PATHS:
            return bid
    return None


def fetch_rss(blogger_id: str, timeout: float = 10.0) -> List[RSSPost]:
    """네이버 블로그 RSS 피드에서 포스트 목록 수집."""
    url = f"https://rss.blog.naver.com/{blogger_id}.xml"
    try:
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; BlogAnalyzer/1.0)"
        })
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("RSS fetch failed for %s: %s", blogger_id, e)
        return []

    try:
        root = ElementTree.fromstring(resp.content)
    except ElementTree.ParseError as e:
        logger.warning("RSS parse failed for %s: %s", blogger_id, e)
        return []

    posts: List[RSSPost] = []
    for item in root.iter("item"):
        title = _get_text(item, "title")
        link = _get_text(item, "link")
        pub_date = _get_text(item, "pubDate")
        desc = _get_text(item, "description")
        category = _get_text(item, "category")
        if title and link:
            # 이미지/영상 카운트 (HTML 스트리핑 전)
            img_cnt, vid_cnt = _count_media_in_html(desc) if desc else (0, 0)
            posts.append(RSSPost(
                title=_strip_html(title),
                link=link,
                pub_date=pub_date,
                description=_strip_html(desc) if desc else "",
                category=category,
                image_count=img_cnt,
                video_count=vid_cnt,
            ))
    return posts


def _get_text(elem, tag: str) -> Optional[str]:
    child = elem.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _count_media_in_html(raw_html: str) -> tuple:
    """HTML에서 이미지/영상 수 카운트 (태그 스트리핑 전에 호출)."""
    img_count = len(re.findall(r"<img\b", raw_html, re.IGNORECASE))
    video_count = len(re.findall(r"<(?:iframe|video)\b|youtube\.com|youtu\.be", raw_html, re.IGNORECASE))
    return img_count, video_count


def _strip_html(text: str) -> str:
    """간단한 HTML 태그 제거."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_rss_date(date_str: Optional[str]) -> Optional[datetime]:
    """RSS pubDate 파싱 (RFC 822 형식)."""
    if not date_str:
        return None
    # RFC 822: "Sun, 15 Feb 2026 09:00:00 +0900"
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=None)
        except (ValueError, TypeError):
            continue
    return None


# ===========================
# 프로필 / 미디어 / 등급 추정
# ===========================

def fetch_blog_profile(blogger_id: str, rss_posts: List[RSSPost] = None, timeout: float = 8.0) -> Dict[str, Any]:
    """네이버 블로그에서 이웃 수 + 블로그 개설일 추정.

    1순위: blog.naver.com/{id} HTML에서 buddyCnt 파싱
    2순위: RSS 최오래된 포스트 날짜로 개설일 추정
    실패 시 기본값 반환.
    """
    result: Dict[str, Any] = {"neighbor_count": 0, "blog_start_date": None}

    # 이웃 수: 블로그 메인 HTML에서 buddyCnt 추출
    try:
        url = f"https://blog.naver.com/{blogger_id}"
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code == 200:
            text = resp.text
            # buddyCnt 패턴: "buddyCnt":123 또는 buddyCnt = 123
            m = re.search(r'"?buddyCnt"?\s*[:=]\s*(\d+)', text)
            if m:
                result["neighbor_count"] = int(m.group(1))
            else:
                # 이웃 수 다른 패턴: "이웃 N" 텍스트
                m = re.search(r'이웃\s*(\d[\d,]*)', text)
                if m:
                    result["neighbor_count"] = int(m.group(1).replace(",", ""))
    except Exception as e:
        logger.debug("Blog profile fetch failed for %s: %s", blogger_id, e)

    # 블로그 개설일: RSS 최오래된 포스트 날짜
    if rss_posts:
        dates = [_parse_rss_date(p.pub_date) for p in rss_posts]
        dates = [d for d in dates if d]
        if dates:
            result["blog_start_date"] = min(dates)

    return result


def compute_image_video_ratio(posts: List[RSSPost]) -> Tuple[float, float]:
    """RSS 포스트에서 이미지/영상 포함 비율 계산."""
    if not posts:
        return 0.0, 0.0
    img_posts = sum(1 for p in posts if p.image_count > 0)
    vid_posts = sum(1 for p in posts if p.video_count > 0)
    n = len(posts)
    return round(img_posts / n, 3), round(vid_posts / n, 3)


def compute_estimated_tier(
    neighbor_count: int,
    blog_years: float,
    interval_avg: Optional[float],
    total_posts: int,
) -> str:
    """블로그 등급 추정: power/premium/gold/silver/normal.

    여러 조건의 가중 합산으로 판정.
    """
    score = 0

    # 이웃 수 기준
    if neighbor_count >= 5000:
        score += 4
    elif neighbor_count >= 2000:
        score += 3
    elif neighbor_count >= 1000:
        score += 2
    elif neighbor_count >= 500:
        score += 1

    # 운영 기간
    if blog_years >= 5:
        score += 3
    elif blog_years >= 3:
        score += 2
    elif blog_years >= 2:
        score += 1

    # 포스팅 빈도
    if interval_avg is not None and interval_avg <= 2:
        score += 2
    elif interval_avg is not None and interval_avg <= 5:
        score += 1

    # 포스트 수 (RSS에서 보통 20~30개만 나오므로 보수적)
    if total_posts >= 25:
        score += 1

    if score >= 8:
        return "power"
    elif score >= 6:
        return "premium"
    elif score >= 4:
        return "gold"
    elif score >= 2:
        return "silver"
    else:
        return "normal"


def compute_tfidf_topic_similarity(
    rss_posts: List[RSSPost],
    match_keywords: List[str],
    target_topic: str = "",
) -> float:
    """TF-IDF 기반 토픽 유사도 (0~1). 순수 Python 구현.

    RSS 포스트 제목에서 한글 2-gram 추출 → TF-IDF 벡터화 → target 키워드와 코사인 유사도.
    """
    if not rss_posts or (not match_keywords and not target_topic):
        return 0.0

    # 문서 = 각 포스트 제목
    docs = []
    for p in rss_posts:
        tokens = re.findall(r"[가-힣]{2,}", p.title)
        docs.append(tokens)

    if not docs:
        return 0.0

    # 타겟 토큰
    target_tokens = []
    for kw in match_keywords:
        target_tokens.extend(re.findall(r"[가-힣]{2,}", kw))
    if target_topic:
        target_tokens.extend(re.findall(r"[가-힣]{2,}", target_topic))

    if not target_tokens:
        return 0.0

    # 어휘 구축
    vocab: Dict[str, int] = {}
    for doc in docs:
        for w in doc:
            if w not in vocab:
                vocab[w] = len(vocab)
    for w in target_tokens:
        if w not in vocab:
            vocab[w] = len(vocab)

    vocab_size = len(vocab)
    if vocab_size == 0:
        return 0.0

    # DF 계산
    df = [0] * vocab_size
    for doc in docs:
        seen = set()
        for w in doc:
            idx = vocab[w]
            if idx not in seen:
                df[idx] += 1
                seen.add(idx)

    n_docs = len(docs)
    idf = [math.log((n_docs + 1) / (d + 1)) + 1 for d in df]

    # 문서 평균 TF-IDF 벡터
    avg_vec = [0.0] * vocab_size
    for doc in docs:
        tf_counter: Dict[int, int] = {}
        for w in doc:
            idx = vocab[w]
            tf_counter[idx] = tf_counter.get(idx, 0) + 1
        doc_len = max(1, len(doc))
        for idx, cnt in tf_counter.items():
            avg_vec[idx] += (cnt / doc_len) * idf[idx]
    for i in range(vocab_size):
        avg_vec[i] /= max(1, n_docs)

    # 타겟 TF-IDF 벡터
    target_vec = [0.0] * vocab_size
    target_counter: Dict[int, int] = {}
    for w in target_tokens:
        idx = vocab[w]
        target_counter[idx] = target_counter.get(idx, 0) + 1
    target_len = max(1, len(target_tokens))
    for idx, cnt in target_counter.items():
        target_vec[idx] = (cnt / target_len) * idf[idx]

    # 코사인 유사도
    dot = sum(a * b for a, b in zip(avg_vec, target_vec))
    mag_a = math.sqrt(sum(x * x for x in avg_vec))
    mag_b = math.sqrt(sum(x * x for x in target_vec))
    if mag_a == 0 or mag_b == 0:
        return 0.0

    return round(min(1.0, max(0.0, dot / (mag_a * mag_b))), 3)


# ===========================
# 분석 함수들
# ===========================

def analyze_activity(posts: List[RSSPost]) -> ActivityMetrics:
    """활동 지표 분석 (0~15점)."""
    now = datetime.now()
    total = len(posts)

    dates = [_parse_rss_date(p.pub_date) for p in posts]
    dates = sorted([d for d in dates if d], reverse=True)

    if not dates:
        return ActivityMetrics(
            total_posts=total,
            days_since_last_post=None,
            avg_interval_days=None,
            interval_std_days=None,
            posting_trend="비활성",
            score=0.0,
        )

    days_since = (now - dates[0]).days

    # 간격 계산
    intervals = []
    for i in range(len(dates) - 1):
        diff = (dates[i] - dates[i + 1]).days
        intervals.append(max(0, diff))

    avg_interval = statistics.mean(intervals) if intervals else 90.0
    std_interval = statistics.stdev(intervals) if len(intervals) >= 2 else avg_interval

    # 활동 등급
    if avg_interval <= 3:
        trend = "매우활발"
    elif avg_interval <= 7:
        trend = "활발"
    elif avg_interval <= 14:
        trend = "보통"
    else:
        trend = "비활성"

    # 점수 계산 (0~15)
    # 최근 활동 (0~5)
    recent_score = 5.0 * (1 - min(days_since, 90) / 90)

    # 포스팅 빈도 (0~5)
    freq_score = 5.0 * (1 - min(avg_interval, 14) / 14)

    # 일관성 (0~2.5)
    if std_interval <= 1:
        consistency = 2.5
    elif std_interval <= 3:
        consistency = 2.0
    elif std_interval <= 7:
        consistency = 1.5
    elif std_interval <= 14:
        consistency = 0.75
    else:
        consistency = 0.0

    # 포스트 수량 (0~2.5)
    volume = 2.5 * min(1.0, total / 30)

    score = max(0.0, min(15.0, recent_score + freq_score + consistency + volume))

    return ActivityMetrics(
        total_posts=total,
        days_since_last_post=days_since,
        avg_interval_days=round(avg_interval, 1),
        interval_std_days=round(std_interval, 1),
        posting_trend=trend,
        score=round(score, 1),
    )


def analyze_content(
    posts: List[RSSPost],
    is_food_cat: bool = False,
    store_category: Optional[str] = None,
) -> ContentMetrics:
    """콘텐츠 성향 분석 (0~20점)."""
    if not posts:
        return ContentMetrics(
            food_bias_rate=0.0,
            sponsor_signal_rate=0.0,
            topic_diversity=0.0,
            dominant_topics=[],
            avg_description_length=0.0,
            category_fit_score=0.0,
            score=0.0,
        )

    # food_bias, sponsor 계산
    food_hits = 0
    sponsor_hits = 0
    desc_lengths = []
    all_words: List[str] = []

    for p in posts:
        text = f"{p.title} {p.description or ''}"
        if any(w in text for w in FOOD_WORDS):
            food_hits += 1
        if any(w in text for w in SPONSOR_WORDS):
            sponsor_hits += 1
        desc_lengths.append(len(p.description or ""))

        # 제목에서 키워드 추출
        words = _extract_keywords_from_title(p.title)
        all_words.extend(words)

    n = max(1, len(posts))
    food_bias = food_hits / n
    sponsor_rate = sponsor_hits / n
    avg_desc_len = statistics.mean(desc_lengths) if desc_lengths else 0

    # 주제 다양성 (엔트로피 기반)
    word_counter = Counter(all_words)
    total_words = sum(word_counter.values())
    dominant_topics = [w for w, _ in word_counter.most_common(10)]

    if total_words > 0 and len(word_counter) > 1:
        entropy = -sum(
            (c / total_words) * math.log2(c / total_words)
            for c in word_counter.values()
            if c > 0
        )
        max_entropy = math.log2(len(word_counter))
        diversity = entropy / max_entropy if max_entropy > 0 else 0
    else:
        diversity = 0.0

    # 점수 계산

    # 주제 다양성 (0~8)
    diversity_score = diversity * 8.0

    # 콘텐츠 충실도 — description 길이 기반 (0~6)
    if avg_desc_len >= 200:
        richness = 6.0
    elif avg_desc_len >= 100:
        richness = 4.5
    elif avg_desc_len >= 50:
        richness = 3.0
    else:
        richness = 1.5

    # 카테고리 적합도 (0~6)
    if store_category:
        cat_lower = store_category.lower()
        cat_mentions = sum(1 for p in posts if cat_lower in p.title.lower())
        cat_fit = 6.0 * min(1.0, cat_mentions / max(1, len(posts)) * 3)
    else:
        # 독립 분석: 다양성 보너스
        cat_fit = min(6.0, diversity * 6.0)

    score = max(0.0, min(20.0, diversity_score + richness + cat_fit))

    return ContentMetrics(
        food_bias_rate=round(food_bias, 3),
        sponsor_signal_rate=round(sponsor_rate, 3),
        topic_diversity=round(diversity, 3),
        dominant_topics=dominant_topics,
        avg_description_length=round(avg_desc_len, 1),
        category_fit_score=round(cat_fit, 1),
        score=round(score, 1),
    )


def _extract_keywords_from_title(title: str) -> List[str]:
    """제목에서 2글자 이상의 한글 명사/키워드 추출 (불용어 제거)."""
    # 한글 2글자 이상 단어 추출
    words = re.findall(r"[가-힣]{2,}", title)
    return [w for w in words if w not in _STOPWORDS]


def extract_search_keywords_from_posts(posts: List[RSSPost], max_keywords: int = 7) -> List[str]:
    """포스트 제목에서 검색용 키워드 추출 (독립 분석 모드용)."""
    counter: Counter = Counter()
    for p in posts:
        words = _extract_keywords_from_title(p.title)
        # 2-gram 조합도 생성
        for w in words:
            counter[w] += 1
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            counter[bigram] += 1

    # 빈도 상위 키워드
    candidates = [kw for kw, count in counter.most_common(max_keywords * 3) if count >= 2]
    return candidates[:max_keywords]


def _has_sponsored_signal(title: str) -> bool:
    """포스트 제목에 협찬/체험단 시그널이 있는지 감지."""
    return any(sig in title for sig in _SPONSORED_TITLE_SIGNALS)


def analyze_exposure(
    blogger_id: str,
    keywords: List[str],
    client: NaverBlogSearchClient,
    progress_cb: Optional[ProgressCb] = None,
) -> ExposureMetrics:
    """검색 노출력 분석 (0~40점)."""
    if not keywords:
        return ExposureMetrics(
            keywords_checked=0, keywords_exposed=0, page1_count=0,
            strength_sum=0, weighted_strength=0.0, details=[],
            sponsored_rank_count=0, sponsored_page1_count=0, score=0.0,
        )

    emit = progress_cb or (lambda _: None)
    details: List[dict] = []

    # 병렬 검색
    def _search_kw(kw: str) -> Tuple[str, List]:
        items = client.search_blog(query=kw, display=30)
        return kw, items

    mapping: Dict[str, Optional[Tuple[int, str, str]]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_search_kw, kw): kw for kw in keywords}
        for fut in concurrent.futures.as_completed(futures):
            kw = futures[fut]
            try:
                keyword, items = fut.result()
                found = None
                for rank0, it in enumerate(items):
                    # blogger_id 매칭
                    item_url = it.bloggerlink or it.link or ""
                    if blogger_id in item_url.lower():
                        found = (rank0 + 1, it.link, it.title)
                        break
                    # blogId 쿼리 파라미터 체크
                    m = re.search(r"(?:blogId|blogid)=([A-Za-z0-9._-]+)", item_url)
                    if m and m.group(1).lower() == blogger_id:
                        found = (rank0 + 1, it.link, it.title)
                        break
                    # blog.naver.com/{id} 체크
                    m = re.search(r"blog\.naver\.com/([A-Za-z0-9._-]+)", item_url)
                    if m and m.group(1).lower() == blogger_id:
                        found = (rank0 + 1, it.link, it.title)
                        break
                mapping[keyword] = found
            except Exception:
                mapping[kw] = None

    total_strength = 0
    total_weighted = 0.0
    exposed_count = 0
    page1_count = 0

    for kw in keywords:
        found = mapping.get(kw)
        if found:
            rank, post_link, post_title = found
            sp = strength_points(rank)
            weight = keyword_weight_for_suffix(kw)
            total_strength += sp
            total_weighted += sp * weight
            exposed_count += 1
            clean_title = _strip_html(post_title) if post_title else ""
            if rank <= 10:
                page1_count += 1
            details.append({
                "keyword": kw,
                "rank": rank,
                "strength": sp,
                "is_page1": rank <= 10,
                "post_link": post_link,
                "post_title": clean_title,
            })

    # 점수 계산 (0~40): 노출 강도(25) + 키워드 커버리지(15)
    max_strength = len(keywords) * 3  # GoldenScore와 동일한 현실적 분모
    strength_score = min(1.0, total_weighted / max(1, max_strength)) * 25.0
    coverage_score = min(1.0, exposed_count / max(1, len(keywords))) * 15.0
    score = max(0.0, min(40.0, strength_score + coverage_score))

    return ExposureMetrics(
        keywords_checked=len(keywords),
        keywords_exposed=exposed_count,
        page1_count=page1_count,
        strength_sum=total_strength,
        weighted_strength=round(total_weighted, 1),
        details=sorted(details, key=lambda d: d["rank"]),
        sponsored_rank_count=0,
        sponsored_page1_count=0,
        score=round(score, 1),
    )


def analyze_suitability(
    food_bias: float,
    sponsor_rate: float,
    is_food_cat: bool,
    is_independent: bool = False,
) -> SuitabilityMetrics:
    """체험단 적합도 분석 (0~10점)."""
    # 협찬 수용성 (0~5)
    if 0.10 <= sponsor_rate <= 0.30:
        sponsor_recv = 5.0
    elif 0.05 <= sponsor_rate < 0.10:
        sponsor_recv = 3.75
    elif sponsor_rate < 0.05:
        sponsor_recv = 3.0
    elif 0.30 < sponsor_rate <= 0.45:
        sponsor_recv = 3.0
    elif 0.45 < sponsor_rate <= 0.60:
        sponsor_recv = 2.0
    else:
        sponsor_recv = 1.0

    # 업종 적합도 (0~5)
    if is_independent:
        cat_fit = 3.0  # 독립 분석(매장 미연계) → 중립
    elif is_food_cat:
        cat_fit = (0.3 + food_bias * 0.7) * 5.0
    else:
        cat_fit = max(0.0, (1.0 - food_bias * 1.5)) * 5.0

    score = max(0.0, min(10.0, sponsor_recv + cat_fit))

    return SuitabilityMetrics(
        sponsor_receptivity_score=round(sponsor_recv, 1),
        category_fit_score=round(cat_fit, 1),
        score=round(score, 1),
    )


def analyze_quality(posts: List[RSSPost]) -> QualityMetrics:
    """콘텐츠 품질 분석 (0~15점): 독창성(0~8) + 충실도(0~7).

    v7.0: difflib.SequenceMatcher → SimHash 기반 독창성.
    """
    if not posts:
        return QualityMetrics(originality=0.0, compliance=0.0, richness=0.0, score=0.0)

    descriptions = [p.description or "" for p in posts]

    # 독창성 (0~8): SimHash 기반 근사 중복 감지 → 낮을수록 높은 점수
    if len(descriptions) >= 2:
        sample = descriptions[:20]
        hashes = [compute_simhash(d) for d in sample]
        dup_pairs = 0
        total_pairs = 0
        for i in range(len(hashes)):
            for j in range(i + 1, min(i + 5, len(hashes))):
                total_pairs += 1
                if hamming_distance(hashes[i], hashes[j]) <= 3:
                    dup_pairs += 1
        dup_rate = dup_pairs / max(1, total_pairs)
        originality = 8.0 * (1.0 - min(1.0, dup_rate))
    else:
        originality = 4.0  # 단일 포스트는 중간값

    # compliance deprecated (항상 0.0)
    compliance = 0.0

    # 충실도 (0~7): description 평균 길이 기반
    avg_len = statistics.mean(len(d) for d in descriptions) if descriptions else 0
    if avg_len >= 200:
        richness = 7.0
    elif avg_len >= 100:
        richness = 5.0
    elif avg_len >= 50:
        richness = 3.0
    else:
        richness = 1.5

    score = max(0.0, min(15.0, originality + compliance + richness))

    return QualityMetrics(
        originality=round(originality, 1),
        compliance=0.0,
        richness=round(richness, 1),
        score=round(score, 1),
    )


def compute_grade(total: float) -> Tuple[str, str]:
    """점수 → 등급 + 라벨."""
    if total >= 85:
        return "S", "최우수"
    elif total >= 70:
        return "A", "우수"
    elif total >= 50:
        return "B", "보통"
    elif total >= 30:
        return "C", "미흡"
    else:
        return "D", "부적합"


def generate_insights(
    activity: ActivityMetrics,
    content: ContentMetrics,
    exposure: ExposureMetrics,
    quality: QualityMetrics,
    total: float,
) -> Tuple[List[str], List[str], str]:
    """강점/약점/추천문 자동 생성."""
    strengths: List[str] = []
    weaknesses: List[str] = []

    # 활동
    if activity.posting_trend in ("매우활발", "활발"):
        strengths.append(f"최근 활발한 포스팅 ({activity.posting_trend})")
    elif activity.posting_trend == "비활성":
        days = activity.days_since_last_post
        if days and days > 30:
            weaknesses.append(f"{days}일간 포스팅 없음")
        else:
            weaknesses.append("포스팅 빈도 낮음")

    if activity.avg_interval_days and activity.avg_interval_days <= 5:
        strengths.append(f"평균 {activity.avg_interval_days}일 간격 꾸준한 활동")

    # 콘텐츠
    if content.topic_diversity >= 0.7:
        strengths.append("다양한 주제 포스팅")
    elif content.topic_diversity < 0.3:
        weaknesses.append("주제 다양성 부족")

    if content.food_bias_rate >= 0.60:
        weaknesses.append(f"맛집 편향 높음 ({content.food_bias_rate*100:.0f}%)")
    elif content.food_bias_rate >= 0.40:
        weaknesses.append(f"맛집 편향 {content.food_bias_rate*100:.0f}%")

    # 노출
    if exposure.page1_count >= 3:
        strengths.append(f"1페이지 노출 {exposure.page1_count}개 키워드")
    elif exposure.keywords_exposed > 0:
        strengths.append(f"검색 노출 {exposure.keywords_exposed}개 키워드")
    elif exposure.keywords_checked > 0:
        weaknesses.append("검색 노출 없음")

    # 적합도
    sr = content.sponsor_signal_rate
    if 0.10 <= sr <= 0.30:
        strengths.append("체험단 경험 있음 (적정 수준)")
    elif sr > 0.60:
        weaknesses.append(f"협찬 비율 과다 ({sr*100:.0f}%+)")
    elif sr < 0.05:
        strengths.append("순수 콘텐츠 위주 (비협찬)")

    # 품질
    if quality.originality >= 6.0:
        strengths.append("콘텐츠 독창성 높음")
    elif quality.originality < 3.0:
        weaknesses.append("포스트 간 유사도 높음 (복붙 의심)")

    # 추천문
    if total >= 70:
        rec = "이 블로거는 체험단 모집에 적합합니다."
    elif total >= 50:
        rec = "이 블로거는 체험단 모집에 고려해볼 만합니다."
    elif total >= 30:
        rec = "이 블로거는 체험단 모집에 다소 부적합할 수 있습니다."
    else:
        rec = "이 블로거는 체험단 모집에 적합하지 않습니다."

    return strengths, weaknesses, rec


# ===========================
# 메인 분석 함수
# ===========================

def analyze_blog(
    blog_url_or_id: str,
    client: NaverBlogSearchClient,
    store_profile: Optional[StoreProfile] = None,
    progress_cb: Optional[ProgressCb] = None,
) -> Dict[str, Any]:
    """
    블로그 종합 분석 실행.

    Args:
        blog_url_or_id: 블로그 URL 또는 ID
        client: 네이버 검색 API 클라이언트
        store_profile: 매장 연계 시 프로필 (None이면 독립 분석)
        progress_cb: SSE 진행 콜백

    Returns:
        분석 결과 딕셔너리
    """
    emit = progress_cb or (lambda _: None)

    # 1. 블로거 ID 추출
    blogger_id = extract_blogger_id(blog_url_or_id)
    if not blogger_id:
        raise ValueError("유효하지 않은 블로그 URL/ID입니다.")

    blog_url = f"https://blog.naver.com/{blogger_id}"
    analysis_mode = "store_linked" if store_profile else "standalone"
    is_food_cat = is_food_category(store_profile.category_text) if store_profile else False

    # 2. RSS 피드 수집
    emit({"stage": "rss", "current": 1, "total": 5, "message": "RSS 피드 수집 중..."})
    posts = fetch_rss(blogger_id)
    rss_available = len(posts) > 0

    # 3. 콘텐츠 분석
    emit({"stage": "content", "current": 2, "total": 5, "message": "콘텐츠 분석 중..."})
    if rss_available:
        activity = analyze_activity(posts)
        content = analyze_content(
            posts,
            is_food_cat=is_food_cat,
            store_category=store_profile.category_text if store_profile else None,
        )
    else:
        activity = ActivityMetrics(
            total_posts=0, days_since_last_post=None,
            avg_interval_days=None, interval_std_days=None,
            posting_trend="알 수 없음", score=0.0,
        )
        content = ContentMetrics(
            food_bias_rate=0.0, sponsor_signal_rate=0.0,
            topic_diversity=0.0, dominant_topics=[],
            avg_description_length=0.0, category_fit_score=0.0, score=0.0,
        )

    # 4. 노출력 분석
    emit({"stage": "exposure", "current": 3, "total": 5, "message": "검색 노출력 확인 중..."})
    if store_profile:
        keywords = build_exposure_keywords(store_profile)
    elif rss_available:
        keywords = extract_search_keywords_from_posts(posts, max_keywords=7)
    else:
        keywords = []

    exposure = analyze_exposure(blogger_id, keywords, client, progress_cb)

    # 5. 품질 검사
    emit({"stage": "quality", "current": 4, "total": 5, "message": "콘텐츠 품질 검사 중..."})
    if rss_available:
        quality = analyze_quality(posts)
    else:
        quality = QualityMetrics(originality=0.0, compliance=0.0, richness=0.0, score=0.0)

    # 6. BlogAnalysisScore 계산
    emit({"stage": "scoring", "current": 5, "total": 5, "message": "BlogScore 계산 중..."})

    # 매장 연계: RSS 포스트에서 keyword_match_ratio 계산
    ba_keyword_match = 0.0
    ba_has_category = False
    if store_profile and rss_available:
        from backend.analyzer import _build_match_keywords
        match_kws = _build_match_keywords(
            store_profile.category_text,
            getattr(store_profile, 'topic', None) or "",
        )
        ba_has_category = bool(match_kws)
        if match_kws:
            match_count = sum(
                1 for p in posts
                if any(kw.lower() in p.title.lower() for kw in match_kws)
            )
            ba_keyword_match = match_count / max(1, len(posts))

    # v7.1: 프로필 + 미디어 + 등급 추정
    profile = fetch_blog_profile(blogger_id, posts if rss_available else [], timeout=6.0)
    neighbor_count = profile.get("neighbor_count", 0)
    blog_start = profile.get("blog_start_date")
    blog_years = 0.0
    if blog_start:
        blog_years = round((datetime.now() - blog_start).days / 365.25, 1)

    img_ratio, vid_ratio = compute_image_video_ratio(posts) if rss_available else (0.0, 0.0)
    est_tier = compute_estimated_tier(
        neighbor_count, blog_years,
        activity.avg_interval_days, activity.total_posts,
    ) if rss_available else "unknown"

    # v7.1: TF-IDF 토픽 유사도
    tfidf_sim = 0.0
    if rss_available and store_profile:
        from backend.analyzer import _build_match_keywords
        match_kws_tf = _build_match_keywords(
            store_profile.category_text,
            getattr(store_profile, 'topic', None) or "",
        )
        tfidf_sim = compute_tfidf_topic_similarity(posts, match_kws_tf)

    # v7.1: SimHash/Bayesian 메트릭
    from backend.scoring import (
        compute_originality_v7, compute_diversity_smoothed,
        compute_game_defense, compute_quality_floor,
        compute_topic_focus, compute_topic_continuity,
    )
    rss_orig_v7 = 0.0
    rss_div_sm = 0.0
    gd_val = 0.0
    qf_val = 0.0
    tf_val = 0.0
    tc_val = 0.0
    if rss_available:
        rss_orig_v7 = compute_originality_v7(posts)
        rss_div_sm = compute_diversity_smoothed(posts)
        gd_val = compute_game_defense(posts, {"interval_avg": activity.avg_interval_days})
        qf_val = compute_quality_floor(0.0, True, exposure.keywords_exposed, 0)
        if store_profile:
            from backend.analyzer import _build_match_keywords as _bmk
            mk = _bmk(store_profile.category_text, getattr(store_profile, 'topic', None) or "")
            tf_val = compute_topic_focus(posts, mk)
            tc_val = compute_topic_continuity(posts, mk)

    total, breakdown, v72_result = blog_analysis_score(
        interval_avg=activity.avg_interval_days,
        originality_raw=quality.originality,
        diversity_entropy=content.topic_diversity,
        richness_avg_len=content.avg_description_length,
        sponsor_signal_rate=content.sponsor_signal_rate,
        strength_sum=exposure.strength_sum,
        exposed_keywords=exposure.keywords_exposed,
        total_keywords=max(1, exposure.keywords_checked),
        food_bias_rate=content.food_bias_rate,
        weighted_strength=exposure.weighted_strength,
        days_since_last_post=activity.days_since_last_post,
        total_posts=activity.total_posts,
        store_profile_present=store_profile is not None,
        keyword_match_ratio=ba_keyword_match,
        has_category=ba_has_category,
        neighbor_count=neighbor_count,
        blog_years=blog_years,
        estimated_tier=est_tier,
        image_ratio=img_ratio,
        video_ratio=vid_ratio,
        rss_originality_v7=rss_orig_v7,
        rss_diversity_smoothed=rss_div_sm,
        rss_posts=posts if rss_available else None,
        game_defense=gd_val,
        quality_floor=qf_val,
        tfidf_sim=tfidf_sim,
        topic_focus=tf_val,
        topic_continuity=tc_val,
    )
    grade = v72_result["grade"]
    grade_label = v72_result["grade_label"]

    strengths, weaknesses, recommendation = generate_insights(
        activity, content, exposure, quality, total,
    )

    # 최근 포스트 (최대 10개)
    recent_posts = []
    for p in posts[:10]:
        dt = _parse_rss_date(p.pub_date)
        recent_posts.append({
            "title": p.title,
            "date": dt.strftime("%Y-%m-%d") if dt else "",
            "link": p.link,
            "category": p.category or "",
        })

    return {
        "blogger_id": blogger_id,
        "blog_url": blog_url,
        "analysis_mode": analysis_mode,
        "rss_available": rss_available,
        "blog_score": {
            "total": total,
            "grade": grade,
            "grade_label": grade_label,
            "breakdown": breakdown,
            # v7.2 확장
            "base_score": v72_result["base_score"],
            "category_bonus": v72_result["category_bonus"],
            "final_score": v72_result["final_score"],
            "base_breakdown": v72_result["base_breakdown"],
            "bonus_breakdown": v72_result["bonus_breakdown"],
        },
        "activity": {
            "total_posts": activity.total_posts,
            "days_since_last_post": activity.days_since_last_post,
            "avg_interval_days": activity.avg_interval_days,
            "posting_trend": activity.posting_trend,
        },
        "content": {
            "food_bias_rate": content.food_bias_rate,
            "sponsor_signal_rate": content.sponsor_signal_rate,
            "topic_diversity": content.topic_diversity,
            "dominant_topics": content.dominant_topics,
            "recent_posts": recent_posts,
        },
        "exposure": {
            "keywords_checked": exposure.keywords_checked,
            "keywords_exposed": exposure.keywords_exposed,
            "page1_count": exposure.page1_count,
            "strength_sum": exposure.strength_sum,
            "details": exposure.details,
        },
        "quality": {
            "originality": quality.originality,
            "compliance": quality.compliance,
            "richness": quality.richness,
            "score": quality.score,
        },
        "insights": {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendation": recommendation,
        },
    }
