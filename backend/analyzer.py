from __future__ import annotations
import concurrent.futures
import json
import re
from typing import Callable, Dict, List, Optional, Tuple

from backend.db import insert_exposure_fact, upsert_blogger
from backend.keywords import StoreProfile, build_exposure_keywords, build_seed_queries, build_broad_queries, build_region_power_queries
from backend.models import BlogPostItem, CandidateBlogger
from backend.naver_client import NaverBlogSearchClient
from backend.scoring import calc_food_bias, calc_sponsor_signal, base_score, strength_points


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

    def _search_cached(self, query: str, display: int = 30) -> List[BlogPostItem]:
        key = f"blog::{query}::display={display}"
        if key in self.cache:
            return self.cache[key]
        items = self.client.search_blog(query=query, display=display)
        self.cache[key] = items
        return items

    def _search_batch(self, queries: List[str], display: int = 30) -> Dict[str, List[BlogPostItem]]:
        """
        여러 쿼리를 ThreadPoolExecutor로 병렬 실행.
        캐시에 있는 쿼리는 API 호출 스킵.
        """
        results: Dict[str, List[BlogPostItem]] = {}
        uncached: List[str] = []

        for q in queries:
            key = f"blog::{q}::display={display}"
            if key in self.cache:
                results[q] = self.cache[key]
            else:
                uncached.append(q)

        if uncached:
            def _fetch(query: str) -> tuple[str, List[BlogPostItem]]:
                items = self.client.search_blog(query=query, display=display)
                return query, items

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                futures = {pool.submit(_fetch, q): q for q in uncached}
                for fut in concurrent.futures.as_completed(futures):
                    q_key = futures[fut]
                    try:
                        query, items = fut.result()
                    except Exception:
                        query, items = q_key, []
                    key = f"blog::{query}::display={display}"
                    self.cache[key] = items
                    results[query] = items

        return results

    def collect_candidates(self) -> Dict[str, CandidateBlogger]:
        queries = build_seed_queries(self.profile)
        bloggers: Dict[str, CandidateBlogger] = {}

        region = self.profile.region_text.strip()
        addr_tokens = self.profile.address_tokens()

        self._emit("search", 1, 2, f"키워드 후보 수집 중 ({len(queries)}개 키워드)...")
        batch_results = self._search_batch(queries, display=30)
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
        queries_total = len(build_seed_queries(self.profile))

        out: List[CandidateBlogger] = []
        for b in bloggers.values():
            b.food_bias_rate = calc_food_bias(b.posts)
            b.sponsor_signal_rate = calc_sponsor_signal(b.posts)
            b.base_score = base_score(b, region_text=region, address_tokens=addr_tokens, queries_total=queries_total)
            out.append(b)

        out.sort(key=lambda x: x.base_score, reverse=True)
        return out

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
        - 후보 수집 (seed 7개 + region_power 3개 + broad 5개)
        - base 점수
        - 노출 검증 (10키워드: 캐시 7개 + 홀드아웃 3개)
        - DB 저장(프로필 + 팩트)
        반환: (seed_calls, exposure_calls, exposure_keywords)
        """
        # 1단계: 카테고리 특화 후보 수집
        bloggers_dict = self.collect_candidates()

        # 2단계: 지역 랭킹 파워 블로거 수집 (인기 카테고리 상위노출자)
        bloggers_dict = self.collect_region_power_candidates(bloggers_dict)

        # 3단계: 카테고리 무관 확장 후보 수집 (블로그 지수 높은 사람)
        bloggers_dict = self.collect_broad_candidates(bloggers_dict)

        ranked = self.compute_base_scores(bloggers_dict)

        exposure_keywords = build_exposure_keywords(self.profile)
        exposure_map = self.exposure_mapping(exposure_keywords)

        store_subset = ranked[: min(len(ranked), 150)]
        self.save_to_db(conn, store_subset, exposure_keywords, exposure_map)

        # 호출 가드: 노출검증은 반드시 10회
        if len(exposure_keywords) != 10:
            raise RuntimeError(f"Exposure keywords count must be 10, got {len(exposure_keywords)}")
        if self.exposure_api_calls != 10:
            raise RuntimeError(f"Exposure API calls must be 10, got {self.exposure_api_calls}")

        return self.seed_api_calls, self.exposure_api_calls, exposure_keywords
