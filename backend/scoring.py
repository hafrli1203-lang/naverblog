from __future__ import annotations
import re
from datetime import datetime
from typing import Optional

from backend.models import CandidateBlogger, BlogPostItem


FOOD_WORDS = ["맛집", "메뉴", "웨이팅", "내돈내산", "재방문", "런치", "디너", "추천", "솔직후기", "후기"]
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
    base 0~75:
    - 최근활동 0~15
    - 평균SERP순위 0~15
    - 지역정합 0~15
    - 쿼리적합 0~10
    - 활동빈도 0~10 (간단화)
    - place_fit 0~10 (address token 노출)
    - food_bias_penalty 0~-10
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

    s = recent + serp + local + qrel + freq + place_fit + penalty
    return max(0.0, min(75.0, s))


def performance_score(strength_sum: int, exposed_keywords: int, total_keywords: int = 7) -> float:
    """
    Performance Score (0~100):
    - strength 기반 70%: (strength_sum / 35) * 70
    - 노출 키워드 커버리지 30%: (exposed_keywords / total_keywords) * 30
    """
    strength_part = min(1.0, strength_sum / 35.0) * 70.0
    coverage_part = min(1.0, exposed_keywords / max(1, total_keywords)) * 30.0
    return round(strength_part + coverage_part, 1)
