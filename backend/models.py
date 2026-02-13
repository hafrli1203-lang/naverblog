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
