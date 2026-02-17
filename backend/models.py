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
    region_power_hits: int = 0  # 지역 랭킹 파워 쿼리 출현 횟수
    tier_score: float = 0.0  # BlogAuthority 점수 (0~30, v5.0)
    tier_grade: str = "D"  # AuthorityGrade (S/A/B/C/D)
    rss_interval_avg: Optional[float] = None  # RSS 포스팅 평균 간격(일)
    rss_originality: float = 0.0  # RSS 독창성 (0~8)
    rss_diversity: float = 0.0  # RSS 주제 다양성 (0~1)
    rss_richness: float = 0.0  # RSS 충실도 (description 평균 길이)
    keyword_match_ratio: float = 0.0  # 포스트 키워드 매칭률 (0~1)
    queries_hit_ratio: float = 0.0  # seed 쿼리 출현 비율 (0~1)
    # v7.0 신규
    popularity_cross_score: float = 0.0   # Phase 1.5 DIA proxy (0~1)
    topic_focus: float = 0.0              # RSS 키워드 집중도 (0~1)
    topic_continuity: float = 0.0         # 최근 포스트 키워드 연속성 (0~1)
    game_defense: float = 0.0             # GameDefense (0 to -10)
    quality_floor: float = 0.0            # QualityFloor (0 to +5)
    days_since_last_post: Optional[int] = None
    rss_originality_v7: float = 0.0       # SimHash 독창성 (0~8)
    rss_diversity_smoothed: float = 0.0   # Bayesian 다양성 (0~1)
    # v7.1 신규
    neighbor_count: int = 0               # 이웃 수
    blog_years: float = 0.0              # 운영 기간(년)
    estimated_tier: str = "unknown"       # power/premium/gold/silver/normal/unknown
    image_ratio: float = 0.0             # 이미지 포함 포스트 비율
    video_ratio: float = 0.0             # 영상 포함 포스트 비율
    exposure_power: float = 0.0          # ExposurePower v7.1 (0~30)
    # v7.2 신규
    content_authority: float = 0.0       # ContentAuthority v7.2 (0~16)
    search_presence: float = 0.0         # SearchPresence v7.2 (0~17)
    avg_image_count: float = 0.0         # RSS 포스트 평균 이미지 수
    # v7.2 BlogPower 신규
    total_posts: int = 0                 # 총 포스트 수 (프로필 크롤링)
    total_visitors: int = 0              # 총 방문자 수
    total_subscribers: int = 0           # 총 구독자/이웃 수
    ranking_percentile: float = 100.0    # 랭킹 백분위 (100=최하위)
    blog_power: float = 0.0             # BlogPower v7.2 (0~25)


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
    image_count: int = 0
    video_count: int = 0


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
    details: list[dict]  # [{keyword, rank, strength, post_link, post_title}]
    sponsored_rank_count: int = 0  # deprecated (항상 0)
    sponsored_page1_count: int = 0  # deprecated (항상 0)
    score: float = 0.0  # 0~40


@dataclass
class SuitabilityMetrics:
    sponsor_receptivity_score: float  # 0~5
    category_fit_score: float  # 0~5
    score: float  # 0~10


@dataclass
class QualityMetrics:
    originality: float  # 0~8 (포스트 간 유사도 역수)
    compliance: float  # deprecated (항상 0.0)
    richness: float  # 0~7 (description 길이 + 다양성)
    score: float  # 0~15


@dataclass
class BlogScoreResult:
    total: float
    grade: str  # S/A/B/C/D
    grade_label: str  # 최우수/우수/보통/미흡/부적합
    activity: ActivityMetrics
    content: ContentMetrics
    exposure: ExposureMetrics
    strengths: list[str]
    weaknesses: list[str]
    recommendation: str
    suitability: Optional[SuitabilityMetrics] = None
    quality: Optional[QualityMetrics] = None
