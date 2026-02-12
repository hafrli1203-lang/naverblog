import os
import re
import sys
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable
from dotenv import load_dotenv

# Windows cp949 콘솔에서 이모지 등 유니코드 출력 에러 방지
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
SEARCH_API_URL = "https://openapi.naver.com/v1/search/blog.json"


class NaverBlogAnalyzer:
    def __init__(
        self,
        region: Optional[str] = None,
        category: Optional[str] = None,
        store_name: Optional[str] = None,
        address: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ):
        self.region = region or ""
        self.category = category or ""
        self.store_name = store_name or ""
        self.address = address or ""
        # 입력된 필드들을 리스트로 관리
        self._input_values = [v for v in [self.region, self.category, self.store_name, self.address] if v]
        self.headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        }
        self.progress_callback = progress_callback
        self._search_cache: Dict[str, Dict] = {}

    def _emit_progress(self, stage: str, current: int, total: int, message: str):
        if self.progress_callback:
            self.progress_callback({
                "stage": stage,
                "current": current,
                "total": total,
                "message": message,
            })

    def generate_keywords(self) -> List[str]:
        """입력된 필드 조합으로 키워드 목록 생성 (접미사 없음)."""
        seen = set()
        keywords = []

        def add(kw: str):
            kw = kw.strip()
            if kw and kw not in seen:
                seen.add(kw)
                keywords.append(kw)

        values = self._input_values  # 입력된 값들

        # 1) 각 입력값 단독 키워드
        for v in values:
            add(v)

        # 2) 2개씩 조합
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                add(f"{values[i]} {values[j]}")

        # 3) 3개 이상이면 전체 조합
        if len(values) >= 3:
            add(" ".join(values))

        # 4) 매장명+주소 특수 조합 (별도로)
        if self.store_name and self.address:
            add(f"{self.store_name} {self.address}")
        if self.store_name and self.region:
            add(f"{self.store_name} {self.region}")

        return keywords if keywords else []

    def search_blog(self, query: str, display: int = 30, start: int = 1, sort: str = "sim") -> Dict:
        """네이버 블로그 검색 API 호출 (캐싱 지원)."""
        cache_key = f"{query}|{display}|{start}|{sort}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        params = {
            "query": query,
            "display": display,
            "start": start,
            "sort": sort,
        }
        try:
            resp = requests.get(SEARCH_API_URL, headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            self._search_cache[cache_key] = result
            return result
        except requests.RequestException as e:
            print(f"[ERROR] 검색 API 호출 실패 ({query}): {e}")
            return {"items": [], "total": 0}

    def extract_blogger_id(self, link: str, bloggerlink: str) -> str:
        """블로거 고유 ID 추출."""
        if bloggerlink:
            match = re.search(r"blog\.naver\.com/([^/?]+)", bloggerlink)
            if match:
                return match.group(1)
        match = re.search(r"blog\.naver\.com/([^/?]+)", link)
        if match:
            return match.group(1)
        return bloggerlink or link

    def clean_html(self, text: str) -> str:
        """HTML 태그 제거."""
        return re.sub(r"<[^>]+>", "", text).strip()

    def _mine_relevant_keywords(self, posts: List[Dict], existing_keywords: List[str]) -> List[str]:
        """블로거 게시물 제목에서 관련 키워드를 마이닝하여 복합 검색 키워드 생성."""
        # 제목에서 2~8글자 한글 명사 추출
        noun_counts: Dict[str, int] = {}
        for post in posts:
            title = post.get("title", "")
            # 한글 2~8글자 단어 추출 (조사/접미사 등 짧은 것 제외)
            words = re.findall(r"[가-힣]{2,8}", title)
            for word in words:
                noun_counts[word] = noun_counts.get(word, 0) + 1

        # 복합 키워드 생성
        existing_set = {kw.lower().strip() for kw in existing_keywords}
        prefix = ""
        if self.region:
            prefix = self.region
        elif self.category:
            prefix = self.category
        elif self._input_values:
            prefix = self._input_values[0]

        if not prefix:
            return []

        # prefix 자체와 동일한 명사는 제외
        skip_words = {v.lower() for v in self._input_values}

        candidates: Dict[str, int] = {}
        for noun, count in noun_counts.items():
            if noun.lower() in skip_words:
                continue
            composite = f"{prefix} {noun}"
            if composite.lower() not in existing_set:
                candidates[composite] = count

        # 빈도순 상위 5개 반환
        sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        return [kw for kw, _ in sorted_candidates[:5]]

    def _check_exposure_rank(self, blogger_id: str, keywords: List[str]) -> List[Dict]:
        """키워드별로 검색하여 해당 블로거의 노출 순위와 점수를 반환."""
        results = []
        for keyword in keywords:
            data = self.search_blog(keyword, display=30)
            items = data.get("items", [])
            found_rank = None
            for rank, item in enumerate(items):
                bloggerlink = item.get("bloggerlink", "")
                link = item.get("link", "")
                item_blogger_id = self.extract_blogger_id(link, bloggerlink)
                if item_blogger_id == blogger_id:
                    found_rank = rank + 1
                    break

            if found_rank is not None:
                if 1 <= found_rank <= 10:
                    points = 3
                elif 11 <= found_rank <= 20:
                    points = 2
                else:
                    points = 1
                results.append({
                    "keyword": keyword,
                    "rank": found_rank,
                    "points": points,
                    "source": "mined",
                })
        return results

    def analyze_bloggers(self, target_count: int = 50) -> List[Dict]:
        """2단계 파이프라인: 1차 키워드 검색 + 스코어링 → 검색 키워드 기반 노출 점수 계산."""
        keywords = self.generate_keywords()
        blogger_data: Dict[str, Dict] = {}
        total_keywords = len(keywords)

        # === 1단계: 기존 키워드 검색 + 기본 스코어링 ===
        for kw_idx, keyword in enumerate(keywords):
            self._emit_progress("search", kw_idx + 1, total_keywords,
                                f"키워드 검색 중: {keyword}")
            print(f"[*] 키워드 검색 중: {keyword}")
            result = self.search_blog(keyword, display=30)
            items = result.get("items", [])

            for rank, item in enumerate(items):
                bloggerlink = item.get("bloggerlink", "")
                link = item.get("link", "")
                blogger_id = self.extract_blogger_id(link, bloggerlink)

                if not blogger_id:
                    continue

                title = self.clean_html(item.get("title", ""))
                description = self.clean_html(item.get("description", ""))
                postdate_str = item.get("postdate", "")
                bloggername = item.get("bloggername", "")

                postdate = None
                if postdate_str:
                    try:
                        postdate = datetime.strptime(postdate_str, "%Y%m%d")
                    except ValueError:
                        pass

                if blogger_id not in blogger_data:
                    blogger_data[blogger_id] = {
                        "id": blogger_id,
                        "name": bloggername,
                        "blog_url": f"https://blog.naver.com/{blogger_id}",
                        "posts": [],
                        "keyword_hits": set(),
                        "ranks": [],
                        "keyword_ranks": {},  # {kw_idx: rank} 키워드별 순위
                        "region_posts": 0,
                        "total_posts_checked": 0,
                    }

                entry = blogger_data[blogger_id]
                entry["keyword_hits"].add(kw_idx)
                entry["ranks"].append(rank + 1)
                # 키워드별 최고 순위 저장 (같은 키워드에 여러 글이면 최상위)
                current_rank = rank + 1
                if kw_idx not in entry["keyword_ranks"] or current_rank < entry["keyword_ranks"][kw_idx]:
                    entry["keyword_ranks"][kw_idx] = current_rank
                entry["total_posts_checked"] += 1

                combined_text = f"{title} {description}".lower()
                if self.region and self.region.lower() in combined_text:
                    entry["region_posts"] += 1

                entry["posts"].append({
                    "title": title,
                    "link": link,
                    "date": postdate,
                    "description": description[:100],
                })

        # 1차 점수 계산 (exposure 제외 5항목, 75점 만점)
        self._emit_progress("scoring", 0, 1, "1차 점수 계산 중...")
        preliminary_bloggers = []
        for blogger_id, data in blogger_data.items():
            scores = self._calculate_base_scores(data, total_keywords)
            base_total = sum(scores.values())

            sorted_posts = sorted(
                [p for p in data["posts"] if p["date"]],
                key=lambda x: x["date"],
                reverse=True,
            )
            last_post_date = None
            if sorted_posts:
                last_post_date = sorted_posts[0]["date"].strftime("%Y-%m-%d")

            recent_posts = []
            for p in sorted_posts[:5]:
                recent_posts.append({
                    "title": p["title"],
                    "link": p["link"],
                    "date": p["date"].strftime("%Y-%m-%d") if p["date"] else "",
                })

            preliminary_bloggers.append({
                "id": data["id"],
                "name": data["name"],
                "blog_url": data["blog_url"],
                "base_total": base_total,
                "score_breakdown": scores,
                "recent_posts": recent_posts,
                "post_count": data["total_posts_checked"],
                "last_post_date": last_post_date,
                "keywords": list(data["keyword_hits"]),
                "keyword_ranks": data["keyword_ranks"],
                "posts_raw": data["posts"],
            })

        # 1차 점수 기준 정렬
        preliminary_bloggers.sort(key=lambda x: x["base_total"], reverse=True)

        # 지역 입력 시: 지역 포함 키워드에 한 번도 매칭되지 않은 블로거 제외
        if self.region:
            region_keyword_indices = {
                idx for idx, kw in enumerate(keywords)
                if self.region.lower() in kw.lower()
            }
            if region_keyword_indices:
                before_count = len(preliminary_bloggers)
                preliminary_bloggers = [
                    b for b in preliminary_bloggers
                    if set(b["keyword_ranks"].keys()) & region_keyword_indices
                ]
                filtered_count = before_count - len(preliminary_bloggers)
                if filtered_count > 0:
                    print(f"[*] 지역 무관 블로거 {filtered_count}명 제외됨")

        # === 2단계: 딥 노출 분석 (상위 20명) + 기본 노출 점수 (나머지) ===
        deep_scan_count = min(20, len(preliminary_bloggers))
        self._emit_progress("exposure", 0, deep_scan_count, "상위 블로거 딥 노출 분석 시작...")

        for idx, blogger in enumerate(preliminary_bloggers):
            keyword_ranks = blogger["keyword_ranks"]  # {kw_idx: rank}

            # 1단계 키워드 기본 노출 포인트 계산
            base_points = 0
            exposure_details = []
            for kw_idx, rank in keyword_ranks.items():
                points = 0
                if 1 <= rank <= 10:
                    points = 3
                elif 11 <= rank <= 20:
                    points = 2
                elif 21 <= rank <= 30:
                    points = 1
                base_points += points
                exposure_details.append({
                    "keyword": keywords[kw_idx],
                    "rank": rank,
                    "points": points,
                    "source": "search",
                })

            if idx < deep_scan_count:
                # 상위 20명: 딥 스캔 — 게시물 제목에서 키워드 마이닝 후 추가 노출 체크
                self._emit_progress("exposure", idx + 1, deep_scan_count,
                                    f"딥 노출 분석 중: {blogger['name']} ({idx + 1}/{deep_scan_count})")
                print(f"[*] 딥 노출 분석: {blogger['id']} ({idx + 1}/{deep_scan_count})")

                mined_keywords = self._mine_relevant_keywords(blogger["posts_raw"], keywords)
                mined_results = self._check_exposure_rank(blogger["id"], mined_keywords)

                mined_points = sum(r["points"] for r in mined_results)
                exposure_details.extend(mined_results)

                total_points = base_points + mined_points
                total_keyword_count = total_keywords + len(mined_keywords)
                max_raw = total_keyword_count * 3 if total_keyword_count > 0 else 1
                normalized_score = min(25, int((total_points / max_raw) * 25))
            else:
                # 나머지: 1단계 데이터만으로 계산 (기존과 동일)
                max_raw = total_keywords * 3 if total_keywords > 0 else 1
                normalized_score = min(25, int((base_points / max_raw) * 25))

            blogger["score_breakdown"]["exposure_score"] = normalized_score
            blogger["exposure_details"] = exposure_details

        self._emit_progress("exposure", deep_scan_count, deep_scan_count, "딥 노출 분석 완료")

        # 최종 점수 계산 및 정렬
        scored_bloggers = []
        for blogger in preliminary_bloggers:
            total_score = sum(blogger["score_breakdown"].values())
            scored_bloggers.append({
                "id": blogger["id"],
                "name": blogger["name"],
                "blog_url": blogger["blog_url"],
                "total_score": total_score,
                "score_breakdown": blogger["score_breakdown"],
                "recent_posts": blogger["recent_posts"],
                "post_count": blogger["post_count"],
                "last_post_date": blogger["last_post_date"],
                "keywords": blogger["keywords"],
                "exposure_details": blogger.get("exposure_details", []),
            })

        scored_bloggers.sort(key=lambda x: x["total_score"], reverse=True)
        self._emit_progress("done", 1, 1, "분석 완료!")
        return scored_bloggers[:target_count]

    def _calculate_base_scores(self, data: Dict, total_keywords: int) -> Dict[str, int]:
        """6가지 평가 기준 중 기본 5항목 점수 계산 (각 15점 만점)."""
        scores = {}

        # 1. 활동 빈도 (0-15)
        dated_posts = sorted(
            [p for p in data["posts"] if p["date"]],
            key=lambda x: x["date"],
        )
        if len(dated_posts) >= 2:
            intervals = []
            for i in range(1, len(dated_posts)):
                delta = (dated_posts[i]["date"] - dated_posts[i - 1]["date"]).days
                intervals.append(delta)
            avg_interval = sum(intervals) / len(intervals)
            scores["activity_frequency"] = max(0, min(15, int(15 - (avg_interval / 30) * 15)))
        elif len(dated_posts) == 1:
            scores["activity_frequency"] = 7
        else:
            scores["activity_frequency"] = 0

        # 2. 키워드 관련성 (0-15)
        hit_ratio = len(data["keyword_hits"]) / max(total_keywords, 1)
        scores["keyword_relevance"] = min(15, int(hit_ratio * 15))

        # 3. 블로그 지수 (0-15)
        if data["ranks"]:
            avg_rank = sum(data["ranks"]) / len(data["ranks"])
            scores["blog_index"] = max(0, min(15, int(15 - (avg_rank / 30) * 15)))
        else:
            scores["blog_index"] = 0

        # 4. 지역 콘텐츠 비율 (0-15)
        if data["total_posts_checked"] > 0:
            if self.region:
                # 지역이 입력된 경우: 지역명 매칭만 사용 (카테고리 폴백 없음)
                region_ratio = data["region_posts"] / data["total_posts_checked"]
                scores["local_content"] = min(15, int(region_ratio * 15))
            elif data["region_posts"] > 0:
                region_ratio = data["region_posts"] / data["total_posts_checked"]
                scores["local_content"] = min(15, int(region_ratio * 15))
            else:
                # 지역 입력 없는 경우에만 다른 입력값으로 폴백
                local_hits = 0
                for p in data["posts"]:
                    combined = f"{p.get('title', '')} {p.get('description', '')}".lower()
                    if any(v.lower() in combined for v in self._input_values):
                        local_hits += 1
                local_ratio = local_hits / data["total_posts_checked"]
                scores["local_content"] = min(15, int(local_ratio * 15))
        else:
            scores["local_content"] = 0

        # 5. 최근 활동 (0-15)
        if dated_posts:
            latest = dated_posts[-1]["date"]
            days_ago = (datetime.now() - latest).days
            scores["recent_activity"] = max(0, min(15, int(15 - (days_ago / 60) * 15)))
        else:
            scores["recent_activity"] = 0

        return scores
