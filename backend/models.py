from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BlogPostItem:
    title: str
    description: str
    link: str
    postdate: Optional[str] = None  # YYYYMMDD or ISO-ish
    bloggerlink: Optional[str] = None
    bloggername: Optional[str] = None


@dataclass
class CandidateBlogger:
    blogger_id: str
    blog_url: str
    ranks: list[int]
    queries_hit: set[str]
    posts: list[BlogPostItem]
    local_hits: int = 0

    # computed
    base_score: float = 0.0
    food_bias_rate: float = 0.0
    sponsor_signal_rate: float = 0.0
    broad_query_hits: int = 0  # broad 쿼리에서의 출현 횟수 (블로그 지수 프록시)


@dataclass
class ExposureDetail:
    keyword: str
    rank: Optional[int]
    strength_points: int
    is_page1: bool
    is_exposed: bool


@dataclass
class BloggerResult:
    blogger_id: str
    blog_url: str
    base_score: float
    exposure_score: float
    strength_sum: int
    page1_keywords_30d: int
    exposed_keywords_30d: int
    best_rank: Optional[int]
    best_rank_keyword: Optional[str]
    food_bias_rate: float
    sponsor_signal_rate: float

    # UI 리포트(카드 상단 고정)
    report_line1: str
    report_line2: str


# ===========================
# 블로그 개별 분석 데이터 클래스
# ===========================

@dataclass
class RSSPost:
    title: str
    link: str
    pub_date: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


@dataclass
class ActivityMetrics:
    total_posts: int
    days_since_last_post: Optional[int]
    avg_interval_days: Optional[float]
    interval_std_days: Optional[float]
    posting_trend: str  # 매우활발/활발/보통/비활성
    score: float  # 0~15


@dataclass
class ContentMetrics:
    food_bias_rate: float
    sponsor_signal_rate: float
    topic_diversity: float
    dominant_topics: list[str]
    avg_description_length: float
    category_fit_score: float  # 0~6
    score: float  # 0~20


@dataclass
class ExposureMetrics:
    keywords_checked: int
    keywords_exposed: int
    page1_count: int
    strength_sum: int
    weighted_strength: float
    details: list[dict]  # [{keyword, rank, strength, post_link, post_title, is_sponsored}]
    sponsored_rank_count: int = 0
    sponsored_page1_count: int = 0
    score: float = 0.0  # 0~40


@dataclass
class SuitabilityMetrics:
    sponsor_receptivity_score: float  # 0~5
    category_fit_score: float  # 0~5
    score: float  # 0~10


@dataclass
class QualityMetrics:
    originality: float  # 0~5 (포스트 간 유사도 역수)
    compliance: float  # 0~5 (금지어 없음 + 공정위 표시)
    richness: float  # 0~5 (description 길이 + 다양성)
    score: float  # 0~15


@dataclass
class BlogScoreResult:
    total: float
    grade: str  # S/A/B/C/D
    grade_label: str  # 최우수/우수/보통/미흡/부적합
    activity: ActivityMetrics
    content: ContentMetrics
    exposure: ExposureMetrics
    suitability: SuitabilityMetrics
    quality: QualityMetrics
    strengths: list[str]
    weaknesses: list[str]
    recommendation: str
