from __future__ import annotations
import concurrent.futures
import json
import re
from typing import Callable, Dict, List, Optional, Tuple

from backend.db import insert_exposure_fact, upsert_blogger
from backend.keywords import StoreProfile, build_exposure_keywords, build_seed_queries, build_broad_queries
from backend.models import BlogPostItem, CandidateBlogger
from backend.naver_client import NaverBlogSearchClient
from backend.scoring import calc_food_bias, calc_sponsor_signal, base_score, strength_points


ProgressCb = Callable[[dict], None]


def canonical_blogger_id_from_item(item: BlogPostItem) -> Optional[str]:
    # 우선 bloggerlink에서 추출
    urls = [item.bloggerlink, item.link]
    for u in urls:
        if not u:
            continue
        # 예: https://blog.naver.com/{id}/...
        m = re.search(r"blog\.naver\.com/([A-Za-z0-9._-]+)", u)
        if m:
            return m.group(1).lower()
        # 예: https://m.blog.naver.com/{id}/...
        m = re.search(r"m\.blog\.naver\.com/([A-Za-z0-9._-]+)", u)
        if m:
            return m.group(1).lower()
        # 예: blogId=xxx
        m = re.search(r"(?:blogId|blogid)=([A-Za-z0-9._-]+)", u)
        if m:
            return m.group(1).lower()
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
                    query, items = fut.result()
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
                b.posts.append(it)

                text = f"{it.title} {it.description}"
                if region in text or any(t in text for t in addr_tokens):
                    b.local_hits += 1

        self._emit("search", 2, 2, "키워드 후보 수집 완료")
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
                b.posts.append(it)

                text = f"{it.title} {it.description}"
                if region in text or any(t in text for t in addr_tokens):
                    b.local_hits += 1

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

    def exposure_mapping(self, keywords: List[str]) -> Dict[str, Dict[str, int]]:
        """
        키워드당 1회 호출 → 결과에서 blogger_id별 best rank 맵핑
        """
        mapping: Dict[str, Dict[str, int]] = {}

        self._emit("exposure", 1, 2, f"노출 검증 중 ({len(keywords)}개 키워드)...")
        batch_results = self._search_batch(keywords, display=30)
        self.exposure_api_calls += len(keywords)

        for kw in keywords:
            items = batch_results.get(kw, [])
            mp: Dict[str, int] = {}
            for rank0, it in enumerate(items):
                bid = canonical_blogger_id_from_item(it)
                if not bid:
                    continue
                r = rank0 + 1
                if bid not in mp or r < mp[bid]:
                    mp[bid] = r
            mapping[kw] = mp

        self._emit("exposure", 2, 2, "노출 검증 완료")
        return mapping

    def save_to_db(
        self,
        conn,
        bloggers: List[CandidateBlogger],
        exposure_keywords: List[str],
        exposure_map: Dict[str, Dict[str, int]],
    ) -> None:
        """
        bloggers upsert + exposures 팩트 누적 저장(일별 유니크)
        """
        for b in bloggers:
            # 샘플은 최근 15개 정도만 저장
            sample = [
                {"title": p.title, "postdate": p.postdate, "link": p.link}
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
            )

        # exposures 저장(팩트)
        for kw in exposure_keywords:
            mp = exposure_map.get(kw, {})
            for b in bloggers:
                rank = mp.get(b.blogger_id)
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
                )

    def analyze(self, conn, top_n: int = 50) -> Tuple[int, int, List[str]]:
        """
        전체 실행:
        - 후보 수집
        - base 점수
        - 노출 검증(7키워드)
        - DB 저장(프로필 + 팩트)
        반환: (seed_calls, exposure_calls, exposure_keywords)
        """
        # 1단계: 카테고리 특화 후보 수집
        bloggers_dict = self.collect_candidates()

        # 2단계: 카테고리 무관 확장 후보 수집 (블로그 지수 높은 사람)
        bloggers_dict = self.collect_broad_candidates(bloggers_dict)

        ranked = self.compute_base_scores(bloggers_dict)

        exposure_keywords = build_exposure_keywords(self.profile)
        exposure_map = self.exposure_mapping(exposure_keywords)

        store_subset = ranked[: min(len(ranked), 150)]
        self.save_to_db(conn, store_subset, exposure_keywords, exposure_map)

        # 호출 가드: 노출검증은 반드시 7회
        if len(exposure_keywords) != 7:
            raise RuntimeError(f"Exposure keywords count must be 7, got {len(exposure_keywords)}")
        if self.exposure_api_calls != 7:
            raise RuntimeError(f"Exposure API calls must be 7, got {self.exposure_api_calls}")

        return self.seed_api_calls, self.exposure_api_calls, exposure_keywords
