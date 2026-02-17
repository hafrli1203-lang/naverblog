from __future__ import annotations
import concurrent.futures
import json
import re
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from backend.db import insert_exposure_fact, upsert_blogger
from backend.keywords import StoreProfile, build_exposure_keywords, build_seed_queries, build_broad_queries, build_region_power_queries, TOPIC_SEED_MAP, is_topic_mode
from backend.models import BlogPostItem, CandidateBlogger
from backend.naver_client import NaverBlogSearchClient
from backend.scoring import (
    calc_food_bias, calc_sponsor_signal, base_score, strength_points, compute_authority_grade,
    compute_originality_v7, compute_diversity_smoothed, compute_topic_focus, compute_topic_continuity,
    compute_game_defense, compute_quality_floor,
    compute_content_authority_v72, compute_search_presence_v72,
)
from backend.blog_analyzer import (
    fetch_rss, analyze_activity, analyze_quality, analyze_content,
    fetch_blog_profile, compute_image_video_ratio, compute_estimated_tier,
    compute_tfidf_topic_similarity,
)


ProgressCb = Callable[[dict], None]

FRANCHISE_NAMES = [
    # 안경
    "다비치", "으뜸50", "룩옵티컬", "안경매니아", "글라스박스", "안경나라",
    # 카페
    "이디야", "스타벅스", "투썸", "메가커피", "컴포즈", "빽다방", "할리스", "탐앤탐스", "폴바셋", "블루보틀",
    # 음식
    "아웃백", "빕스", "놀부", "본죽", "맘스터치", "버거킹", "맥도날드", "롯데리아",
    "교촌", "BBQ", "BHC", "네네", "굽네", "도미노", "파파존스", "피자헛",
    "한솥", "홍콩반점", "새마을식당",
    # 미용
    "이철헤어", "준오헤어", "박승철", "리안헤어", "데뷰헤어",
    # 헬스
    "애니타임피트니스", "스포애니", "짐박스",
    # 학원
    "대성마이맥", "메가스터디", "YBM",
    # 기타
    "올리브영", "다이소", "무신사", "ABC마트",
]

STORE_SUFFIXES = ["점", "원", "실", "관", "샵", "스토어", "몰", "센터", "클리닉", "의원"]


def detect_self_blog(blogger: CandidateBlogger, store_name: str, category_text: str) -> str:
    """반환: 'self' | 'competitor' | 'normal'"""
    score = 0
    name_lower = (blogger.posts[0].bloggername or "").lower() if blogger.posts else ""
    bid = blogger.blogger_id.lower()
    sname = store_name.lower().replace(" ", "") if store_name else ""

    # 시그널 1: 블로거 이름에 매장명 포함
    if sname and sname in name_lower.replace(" ", ""):
        score += 3
    # 시그널 2: blogger_id에 매장명 토큰
    if sname and any(t in bid for t in sname.split() if len(t) >= 2):
        score += 2
    # 시그널 3: 블로거 이름에 업종 키워드 (빈 카테고리 가드)
    cat_lower = category_text.lower()
    if cat_lower and cat_lower in name_lower:
        score += 2

    if score >= 4:
        return "self"

    # 경쟁사(프랜차이즈) 체크
    for fn in FRANCHISE_NAMES:
        if fn in name_lower or fn.lower().replace(" ", "") in bid:
            return "competitor"

    # 브랜드 블로그 패턴: "{업종}+{매장접미사}" → 경쟁사 매장 블로그
    # 예: "다비치안경 역삼점", "글라스박스안경 강남점"
    # "안경에미친남자" → 매장 접미사 없음 → normal (진짜 리뷰어 가능)
    if cat_lower and cat_lower in name_lower:
        name_no_space = name_lower.replace(" ", "")
        for suffix in STORE_SUFFIXES:
            if name_no_space.endswith(suffix) or f"{suffix}" in name_no_space:
                # 접미사 위치가 카테고리 뒤에 있는지 확인
                cat_pos = name_no_space.find(cat_lower)
                suffix_pos = name_no_space.find(suffix)
                if cat_pos >= 0 and suffix_pos > cat_pos:
                    return "competitor"

    return "normal"


_SYSTEM_PATHS = frozenset({
    "postview", "postlist", "bloglist", "prologue",
    "postview.naver", "postlist.naver",
    "postview.nhn", "postlist.nhn",
})


def canonical_blogger_id_from_item(item: BlogPostItem) -> Optional[str]:
    urls = [item.bloggerlink, item.link]
    for u in urls:
        if not u:
            continue
        # 1순위: blogId 쿼리 파라미터 (PostView.naver?blogId=abc 대응)
        m = re.search(r"(?:blogId|blogid)=([A-Za-z0-9._-]+)", u)
        if m:
            return m.group(1).lower()
        # 2순위: blog.naver.com/{id} 경로 기반
        m = re.search(r"(?:m\.)?blog\.naver\.com/([A-Za-z0-9._-]+)", u)
        if m:
            bid = m.group(1).lower()
            if bid not in _SYSTEM_PATHS:
                return bid
    return None


def blog_url_from_id(blogger_id: str) -> str:
    return f"https://blog.naver.com/{blogger_id}"


def _build_match_keywords(category_text: str, topic: str) -> list[str]:
    """검색 키워드/주제에서 포스트 매칭용 키워드 리스트 추출.

    - 키워드 모드: category_text에서 핵심 단어 추출
    - 주제 모드: TOPIC_SEED_MAP[topic]에서 {r} 제거한 순수 키워드
    - 지역만 모드: 빈 리스트
    """
    cat = (category_text or "").strip()
    top = (topic or "").strip()

    if cat:
        # 키워드 모드: category_text 자체 + 2글자 이상 한글 토큰 분리
        keywords = [cat]
        import re as _re
        tokens = _re.findall(r"[가-힣]{2,}", cat)
        for t in tokens:
            if t != cat and t not in keywords:
                keywords.append(t)
        return keywords

    if top and top in TOPIC_SEED_MAP:
        # 주제 모드: TOPIC_SEED_MAP에서 {r} 제거한 순수 키워드
        keywords = []
        for tmpl in TOPIC_SEED_MAP[top]:
            kw = tmpl.replace("{r}", "").strip()
            if kw and kw not in keywords:
                keywords.append(kw)
        return keywords

    # 지역만 모드
    return []


class BloggerAnalyzer:
    def __init__(
        self,
        client: NaverBlogSearchClient,
        profile: StoreProfile,
        store_id: int,
        progress_cb: Optional[ProgressCb] = None,
        cache: Optional[Dict[str, List[BlogPostItem]]] = None,
    ) -> None:
        self.client = client
        self.profile = profile
        self.store_id = store_id
        self.progress_cb = progress_cb or (lambda _: None)
        self.cache = cache if cache is not None else {}

        # 호출 가드(검증용)
        self.exposure_api_calls = 0
        self.seed_api_calls = 0

    def _emit(self, stage: str, current: int, total: int, message: str) -> None:
        self.progress_cb({"stage": stage, "current": current, "total": total, "message": message})

    def _search_cached(self, query: str, display: int = 30, sort: str = "sim") -> List[BlogPostItem]:
        key = f"blog::{query}::display={display}::sort={sort}"
        if key in self.cache:
            return self.cache[key]
        items = self.client.search_blog(query=query, display=display, sort=sort)
        self.cache[key] = items
        return items

    def _search_batch(self, queries: List[str], display: int = 30, sort: str = "sim") -> Dict[str, List[BlogPostItem]]:
        """
        여러 쿼리를 ThreadPoolExecutor로 병렬 실행.
        캐시에 있는 쿼리는 API 호출 스킵.
        """
        results: Dict[str, List[BlogPostItem]] = {}
        uncached: List[str] = []

        for q in queries:
            key = f"blog::{q}::display={display}::sort={sort}"
            if key in self.cache:
                results[q] = self.cache[key]
            else:
                uncached.append(q)

        if uncached:
            def _fetch(query: str) -> tuple[str, List[BlogPostItem]]:
                items = self.client.search_blog(query=query, display=display, sort=sort)
                return query, items

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                futures = {pool.submit(_fetch, q): q for q in uncached}
                for fut in concurrent.futures.as_completed(futures):
                    q_key = futures[fut]
                    try:
                        query, items = fut.result()
                    except Exception:
                        query, items = q_key, []
                    key = f"blog::{query}::display={display}::sort={sort}"
                    self.cache[key] = items
                    results[query] = items

        return results

    def collect_candidates(self) -> Dict[str, CandidateBlogger]:
        queries = build_seed_queries(self.profile)
        bloggers: Dict[str, CandidateBlogger] = {}

        region = self.profile.region_text.strip()
        addr_tokens = self.profile.address_tokens()

        self._emit("search", 1, 2, f"키워드 후보 수집 중 ({len(queries)}개 키워드)...")
        batch_results = self._search_batch(queries, display=20)
        self.seed_api_calls += len(queries)

        for q in queries:
            items = batch_results.get(q, [])
            for rank0, it in enumerate(items):
                bid = canonical_blogger_id_from_item(it)
                if not bid:
                    continue
                if bid not in bloggers:
                    bloggers[bid] = CandidateBlogger(
                        blogger_id=bid,
                        blog_url=blog_url_from_id(bid),
                        ranks=[],
                        queries_hit=set(),
                        posts=[],
                        local_hits=0,
                    )
                b = bloggers[bid]
                b.ranks.append(rank0 + 1)
                b.queries_hit.add(q)

                # 중복 포스트 제거: link 기준
                existing_links = {p.link for p in b.posts}
                if it.link not in existing_links:
                    b.posts.append(it)
                    text = f"{it.title} {it.description}"
                    if region in text or any(t in text for t in addr_tokens):
                        b.local_hits += 1

        self._emit("search", 2, 2, "키워드 후보 수집 완료")
        return bloggers

    def collect_region_power_candidates(self, existing: Dict[str, CandidateBlogger]) -> Dict[str, CandidateBlogger]:
        """지역 랭킹 파워 블로거 수집.
        인기 카테고리 검색에서 상위 10위 이내 블로거만 수집 (높은 블로그 지수).
        """
        queries = build_region_power_queries(self.profile)
        bloggers = dict(existing)

        region = self.profile.region_text.strip()
        addr_tokens = self.profile.address_tokens()

        self._emit("region_power", 1, 2, f"지역 랭킹 파워 블로거 수집 중 ({len(queries)}개 키워드)...")
        batch_results = self._search_batch(queries, display=30)
        self.seed_api_calls += len(queries)

        for q in queries:
            items = batch_results.get(q, [])
            # 상위 10위 이내만 수집 (높은 블로그 지수)
            for rank0, it in enumerate(items[:10]):
                bid = canonical_blogger_id_from_item(it)
                if not bid:
                    continue
                if bid not in bloggers:
                    bloggers[bid] = CandidateBlogger(
                        blogger_id=bid,
                        blog_url=blog_url_from_id(bid),
                        ranks=[],
                        queries_hit=set(),
                        posts=[],
                        local_hits=0,
                    )
                b = bloggers[bid]
                b.ranks.append(rank0 + 1)
                b.queries_hit.add(q)

                # 중복 포스트 제거: link 기준
                existing_links = {p.link for p in b.posts}
                if it.link not in existing_links:
                    b.posts.append(it)
                    text = f"{it.title} {it.description}"
                    if region in text or any(t in text for t in addr_tokens):
                        b.local_hits += 1

        # region_power 쿼리 출현 횟수 계산
        rp_set = set(queries)
        for b in bloggers.values():
            b.region_power_hits = len(b.queries_hit & rp_set)

        self._emit("region_power", 2, 2, "지역 랭킹 파워 블로거 수집 완료")
        return bloggers

    def collect_popularity_cross(self, bloggers: Dict[str, CandidateBlogger]) -> None:
        """Phase 1.5: seed 3개 쿼리를 sort=date로 재검색 → sim∩date = 높은 DIA."""
        seed_queries = build_seed_queries(self.profile)
        cross_queries = seed_queries[:3]

        self._emit("popularity_cross", 1, 2, f"인기순 교차검색 중 ({len(cross_queries)}개 키워드)...")
        date_results = self._search_batch(cross_queries, display=20, sort="date")
        self.seed_api_calls += len(cross_queries)

        # sim 결과에서 이미 수집된 블로거 ID 목록
        for b in bloggers.values():
            cross_count = 0
            for q in cross_queries:
                date_items = date_results.get(q, [])
                date_ids = set()
                for it in date_items:
                    bid = canonical_blogger_id_from_item(it)
                    if bid:
                        date_ids.add(bid)
                if b.blogger_id in date_ids:
                    cross_count += 1
            b.popularity_cross_score = cross_count / max(1, len(cross_queries))

        self._emit("popularity_cross", 2, 2, "인기순 교차검색 완료")

    def collect_broad_candidates(self, existing: Dict[str, CandidateBlogger]) -> Dict[str, CandidateBlogger]:
        """
        카테고리 무관 지역 기반 확장 쿼리로 상위노출 가능 블로거를 추가 수집.
        기존 후보와 합쳐서 반환. 상위 10위 이내만 수집(블로그 지수 높은 사람).
        """
        queries = build_broad_queries(self.profile)
        bloggers = dict(existing)

        region = self.profile.region_text.strip()
        addr_tokens = self.profile.address_tokens()

        self._emit("broad_search", 1, 2, f"확장 후보 수집 중 ({len(queries)}개 키워드)...")
        batch_results = self._search_batch(queries, display=30)
        self.seed_api_calls += len(queries)

        for q in queries:
            items = batch_results.get(q, [])
            # 상위 15위 이내만 수집 (블로그 지수 높은 사람만)
            for rank0, it in enumerate(items[:15]):
                bid = canonical_blogger_id_from_item(it)
                if not bid:
                    continue
                if bid not in bloggers:
                    bloggers[bid] = CandidateBlogger(
                        blogger_id=bid,
                        blog_url=blog_url_from_id(bid),
                        ranks=[],
                        queries_hit=set(),
                        posts=[],
                        local_hits=0,
                    )
                b = bloggers[bid]
                b.ranks.append(rank0 + 1)
                b.queries_hit.add(q)

                # 중복 포스트 제거: link 기준
                existing_links = {p.link for p in b.posts}
                if it.link not in existing_links:
                    b.posts.append(it)
                    text = f"{it.title} {it.description}"
                    if region in text or any(t in text for t in addr_tokens):
                        b.local_hits += 1

        # broad 쿼리 출현 횟수 계산 (블로그 지수 프록시)
        broad_set = set(queries)
        for b in bloggers.values():
            b.broad_query_hits = len(b.queries_hit & broad_set)

        self._emit("broad_search", 2, 2, "확장 후보 수집 완료")
        return bloggers

    def compute_base_scores(self, bloggers: Dict[str, CandidateBlogger]) -> List[CandidateBlogger]:
        region = self.profile.region_text.strip()
        addr_tokens = self.profile.address_tokens()
        seed_queries = build_seed_queries(self.profile)
        queries_total = len(seed_queries)

        # 키워드 매칭용 키워드 리스트 (CategoryFit 3-signal)
        match_keywords = _build_match_keywords(
            self.profile.category_text,
            getattr(self.profile, 'topic', None) or "",
        )

        out: List[CandidateBlogger] = []
        for b in bloggers.values():
            b.food_bias_rate = calc_food_bias(b.posts)
            b.sponsor_signal_rate = calc_sponsor_signal(b.posts)
            b.base_score = base_score(b, region_text=region, address_tokens=addr_tokens, queries_total=queries_total)

            # keyword_match_ratio: 포스트 제목에 매칭 키워드 포함 비율
            if match_keywords and b.posts:
                match_count = 0
                for p in b.posts:
                    title_lower = p.title.lower()
                    if any(kw.lower() in title_lower for kw in match_keywords):
                        match_count += 1
                b.keyword_match_ratio = match_count / len(b.posts)
            else:
                b.keyword_match_ratio = 0.0

            # queries_hit_ratio: seed 쿼리 출현 비율
            b.queries_hit_ratio = len(b.queries_hit) / max(1, queries_total)

            out.append(b)

        out.sort(key=lambda x: x.base_score, reverse=True)
        return out

    def _parallel_fetch_rss(self, blogger_ids: List[str]) -> Dict[str, list]:
        """RSS 피드 병렬 fetch (max_workers=10, API 쿼터 미사용)."""
        rss_map: Dict[str, list] = {}

        def _fetch_one(bid: str):
            posts = fetch_rss(bid, timeout=8.0)
            return bid, posts

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_fetch_one, bid): bid for bid in blogger_ids}
            for fut in concurrent.futures.as_completed(futures):
                bid_key = futures[fut]
                try:
                    bid, posts = fut.result()
                    rss_map[bid] = posts
                except Exception:
                    rss_map[bid_key] = []

        return rss_map

    def _parallel_fetch_profiles(self, blogger_ids: List[str], rss_map: Dict[str, list]) -> Dict[str, Dict]:
        """블로그 프로필 병렬 fetch (이웃 수 등)."""
        profile_map: Dict[str, Dict] = {}

        def _fetch_one(bid: str):
            return bid, fetch_blog_profile(bid, rss_map.get(bid, []), timeout=6.0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_fetch_one, bid): bid for bid in blogger_ids}
            for fut in concurrent.futures.as_completed(futures):
                bid_key = futures[fut]
                try:
                    bid, profile = fut.result()
                    profile_map[bid] = profile
                except Exception:
                    profile_map[bid_key] = {"neighbor_count": 0, "blog_start_date": None}

        return profile_map

    def compute_tier_scores(self, bloggers: List[CandidateBlogger]) -> List[CandidateBlogger]:
        """RSS 기반 블로그 권위 분석.

        상위 80명만 RSS 분석 (base_score 순, 나머지는 tier=0).
        v7.1: 프로필 수집(이웃 수), 미디어 비율, estimated_tier, exposure_power 추가.
        """
        self._emit("tier_analysis", 1, 4, "블로그 권위 분석 중 (RSS 수집)...")

        # 상위 80명만 RSS 분석
        top_candidates = bloggers[:80]
        top_ids = [b.blogger_id for b in top_candidates]

        self._emit("tier_analysis", 2, 4, f"RSS 피드 병렬 수집 중 ({len(top_ids)}명)...")
        rss_map = self._parallel_fetch_rss(top_ids)

        # v7.1: 프로필 병렬 수집 (이웃 수 + 개설일)
        self._emit("tier_analysis", 3, 4, f"블로그 프로필 수집 중 ({len(top_ids)}명)...")
        profile_map = self._parallel_fetch_profiles(top_ids, rss_map)

        from backend.scoring import (
            _posting_intensity, _originality_steep, compute_authority_grade,
            compute_exposure_power,
        )

        # 매칭 키워드 리스트 (v7 topic_focus/topic_continuity 용)
        match_keywords = _build_match_keywords(
            self.profile.category_text,
            getattr(self.profile, 'topic', None) or "",
        )

        now = datetime.now()

        for b in bloggers:
            posts = rss_map.get(b.blogger_id, [])
            profile = profile_map.get(b.blogger_id, {"neighbor_count": 0, "blog_start_date": None})
            rss_success = len(posts) > 0

            # v7.1: 프로필 데이터 설정
            b.neighbor_count = profile.get("neighbor_count", 0)
            blog_start = profile.get("blog_start_date")
            if blog_start:
                b.blog_years = round((now - blog_start).days / 365.25, 1)
            else:
                b.blog_years = 0.0

            if posts:
                act = analyze_activity(posts)
                qual = analyze_quality(posts)
                cnt = analyze_content(posts)

                # 개별 RSS 메트릭 저장
                b.rss_interval_avg = act.avg_interval_days
                b.rss_originality = qual.originality  # 0~8
                b.rss_diversity = cnt.topic_diversity  # 0~1
                b.rss_richness = cnt.avg_description_length

                # v7.0 메트릭
                b.days_since_last_post = act.days_since_last_post
                b.rss_originality_v7 = compute_originality_v7(posts)
                b.rss_diversity_smoothed = compute_diversity_smoothed(posts)
                b.topic_focus = compute_topic_focus(posts, match_keywords)
                b.topic_continuity = compute_topic_continuity(posts, match_keywords)
                b.game_defense = compute_game_defense(
                    posts, {"interval_avg": act.avg_interval_days}
                )

                # v7.1: 미디어 비율
                b.image_ratio, b.video_ratio = compute_image_video_ratio(posts)
                # v7.2: 평균 이미지 수 (RSSQuality 이미지 보정용)
                b.avg_image_count = round(
                    sum(getattr(p, 'image_count', 0) for p in posts) / max(1, len(posts)), 1
                ) if posts else 0.0

                # v7.1: estimated_tier
                b.estimated_tier = compute_estimated_tier(
                    b.neighbor_count, b.blog_years,
                    act.avg_interval_days, act.total_posts,
                )

                # v7.2: ContentAuthority + SearchPresence
                b.content_authority = compute_content_authority_v72(posts)
                b.search_presence = compute_search_presence_v72(posts)
            else:
                b.rss_interval_avg = None
                b.rss_originality = 0.0
                b.rss_diversity = 0.0
                b.rss_richness = 0.0
                b.days_since_last_post = None
                b.rss_originality_v7 = 0.0
                b.rss_diversity_smoothed = 0.0
                b.topic_focus = 0.0
                b.topic_continuity = 0.0
                b.game_defense = 0.0
                b.image_ratio = 0.0
                b.video_ratio = 0.0
                b.estimated_tier = "unknown"
                b.content_authority = 0.0
                b.search_presence = 0.0
                b.avg_image_count = 0.0

            # QualityFloor
            page1_count = sum(1 for r in b.ranks if r <= 10)
            b.quality_floor = compute_quality_floor(
                b.base_score, rss_success, 0, page1_count
            )

            # v7.1: ExposurePower
            b.exposure_power = compute_exposure_power(
                queries_hit_count=len(b.queries_hit),
                total_query_count=len(build_seed_queries(self.profile)),
                ranks=b.ranks,
                popularity_cross_score=b.popularity_cross_score,
                broad_query_hits=b.broad_query_hits,
                region_power_hits=b.region_power_hits,
            )

            # BlogAuthority (0~30) = CrossCatAuthority(15) + PostingIntensity(10) + Originality(5)
            rp = getattr(b, 'region_power_hits', 0)
            broad = getattr(b, 'broad_query_hits', 0)

            if rp >= 3:
                cross_rp = 10.0
            elif rp >= 2:
                cross_rp = 7.0
            elif rp >= 1:
                cross_rp = 4.0
            else:
                cross_rp = 0.0

            if broad >= 3:
                cross_broad = 5.0
            elif broad >= 2:
                cross_broad = 3.0
            elif broad >= 1:
                cross_broad = 1.5
            else:
                cross_broad = 0.0

            cross_cat = min(15.0, cross_rp + cross_broad)
            posting = _posting_intensity(b.rss_interval_avg)
            orig = _originality_steep(b.rss_originality)

            b.tier_score = min(30.0, cross_cat + posting + orig)
            b.tier_grade = compute_authority_grade(b.tier_score)

        self._emit("tier_analysis", 4, 4, "블로그 권위 분석 완료")
        return bloggers

    def exposure_mapping(self, keywords: List[str]) -> Dict[str, Dict[str, tuple]]:
        """
        키워드당 1회 호출 → 결과에서 blogger_id별 best rank + post info 맵핑
        반환: {keyword: {blogger_id: (rank, post_link, post_title), ...}, ...}
        """
        mapping: Dict[str, Dict[str, tuple]] = {}

        self._emit("exposure", 1, 2, f"노출 검증 중 ({len(keywords)}개 키워드)...")
        batch_results = self._search_batch(keywords, display=30)
        self.exposure_api_calls += len(keywords)

        for kw in keywords:
            items = batch_results.get(kw, [])
            mp: Dict[str, tuple] = {}
            for rank0, it in enumerate(items):
                bid = canonical_blogger_id_from_item(it)
                if not bid:
                    continue
                r = rank0 + 1
                if bid not in mp or r < mp[bid][0]:
                    mp[bid] = (r, it.link, it.title)
            mapping[kw] = mp

        self._emit("exposure", 2, 2, "노출 검증 완료")
        return mapping

    def save_to_db(
        self,
        conn,
        bloggers: List[CandidateBlogger],
        exposure_keywords: List[str],
        exposure_map: Dict[str, Dict[str, tuple]],
    ) -> None:
        """
        bloggers upsert + exposures 팩트 누적 저장(일별 유니크)
        exposure_map 값은 (rank, post_link, post_title) 튜플
        """
        for b in bloggers:
            # 샘플은 최근 15개 정도만 저장
            sample = [
                {"title": p.title, "postdate": p.postdate, "link": p.link, "bloggername": p.bloggername}
                for p in b.posts[:15]
            ]
            upsert_blogger(
                conn,
                blogger_id=b.blogger_id,
                blog_url=b.blog_url,
                last_post_date=b.posts[0].postdate if b.posts else None,
                activity_interval_days=None,
                sponsor_signal_rate=b.sponsor_signal_rate,
                food_bias_rate=b.food_bias_rate,
                posts_sample_json=json.dumps(sample, ensure_ascii=False),
                base_score=b.base_score,
                tier_score=b.tier_score,
                tier_grade=b.tier_grade,
                region_power_hits=getattr(b, 'region_power_hits', 0),
                broad_query_hits=getattr(b, 'broad_query_hits', 0),
                rss_interval_avg=getattr(b, 'rss_interval_avg', None),
                rss_originality=getattr(b, 'rss_originality', None),
                rss_diversity=getattr(b, 'rss_diversity', None),
                rss_richness=getattr(b, 'rss_richness', None),
                keyword_match_ratio=getattr(b, 'keyword_match_ratio', 0.0),
                queries_hit_ratio=getattr(b, 'queries_hit_ratio', 0.0),
                # v7.0 신규
                popularity_cross_score=getattr(b, 'popularity_cross_score', 0.0),
                topic_focus=getattr(b, 'topic_focus', 0.0),
                topic_continuity=getattr(b, 'topic_continuity', 0.0),
                game_defense=getattr(b, 'game_defense', 0.0),
                quality_floor=getattr(b, 'quality_floor', 0.0),
                days_since_last_post=getattr(b, 'days_since_last_post', None),
                rss_originality_v7=getattr(b, 'rss_originality_v7', 0.0),
                rss_diversity_smoothed=getattr(b, 'rss_diversity_smoothed', 0.0),
                # v7.1 신규
                neighbor_count=getattr(b, 'neighbor_count', 0),
                blog_years=getattr(b, 'blog_years', 0.0),
                estimated_tier=getattr(b, 'estimated_tier', 'unknown'),
                image_ratio=getattr(b, 'image_ratio', 0.0),
                video_ratio=getattr(b, 'video_ratio', 0.0),
                exposure_power=getattr(b, 'exposure_power', 0.0),
                # v7.2 신규
                content_authority=getattr(b, 'content_authority', 0.0),
                search_presence=getattr(b, 'search_presence', 0.0),
                avg_image_count=getattr(b, 'avg_image_count', 0.0),
            )

        # exposures 저장(팩트)
        for kw in exposure_keywords:
            mp = exposure_map.get(kw, {})
            for b in bloggers:
                entry = mp.get(b.blogger_id)
                if entry is not None:
                    rank, post_link, post_title = entry
                else:
                    rank, post_link, post_title = None, None, None
                sp = strength_points(rank)
                is_page1 = (rank is not None and rank <= 10)
                is_exposed = (rank is not None and rank <= 30)
                insert_exposure_fact(
                    conn,
                    store_id=self.store_id,
                    keyword=kw,
                    blogger_id=b.blogger_id,
                    rank=rank,
                    strength_points=sp,
                    is_page1=is_page1,
                    is_exposed=is_exposed,
                    post_link=post_link,
                    post_title=post_title,
                )

    def analyze(self, conn, top_n: int = 50) -> Tuple[int, int, List[str]]:
        """
        전체 실행:
        Phase 1:   seed(7) → collect_candidates
        Phase 1.5: popularity_cross(3) → collect_popularity_cross [v7.0 신규, +3 API]
        Phase 2:   region_power(3)
        Phase 3:   broad(5)
        Phase 4:   base_scores + tier_scores (v7 메트릭 포함)
        Phase 5:   exposure(10)
        Phase 6:   save_to_db
        반환: (seed_calls, exposure_calls, exposure_keywords)
        """
        # Phase 1: 카테고리 특화 후보 수집
        bloggers_dict = self.collect_candidates()

        # Phase 1.5: 인기순 교차검색 (DIA 추정, v7.0)
        self.collect_popularity_cross(bloggers_dict)

        # Phase 2: 지역 랭킹 파워 블로거 수집 (인기 카테고리 상위노출자)
        bloggers_dict = self.collect_region_power_candidates(bloggers_dict)

        # Phase 3: 카테고리 무관 확장 후보 수집 (블로그 지수 높은 사람)
        bloggers_dict = self.collect_broad_candidates(bloggers_dict)

        ranked = self.compute_base_scores(bloggers_dict)

        # Phase 4: RSS 기반 순수체급 분석 (API 호출 없음, v7 메트릭 포함)
        ranked = self.compute_tier_scores(ranked)

        # Phase 5: 노출 검증
        exposure_keywords = build_exposure_keywords(self.profile)
        exposure_map = self.exposure_mapping(exposure_keywords)

        # Phase 6: DB 저장
        store_subset = ranked[: min(len(ranked), 150)]
        self.save_to_db(conn, store_subset, exposure_keywords, exposure_map)

        # 호출 가드: 노출검증은 반드시 10회
        if len(exposure_keywords) != 10:
            raise RuntimeError(f"Exposure keywords count must be 10, got {len(exposure_keywords)}")
        if self.exposure_api_calls != 10:
            raise RuntimeError(f"Exposure API calls must be 10, got {self.exposure_api_calls}")

        return self.seed_api_calls, self.exposure_api_calls, exposure_keywords
