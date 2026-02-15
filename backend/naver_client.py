from __future__ import annotations
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from backend.models import BlogPostItem

logger = logging.getLogger(__name__)

# 재시도 대상 HTTP 상태 코드
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class NaverBlogSearchClient:
    """
    네이버 검색 API(블로그) 호출 클라이언트
    429/5xx 에러 시 지수 백오프 재시도 (최대 3회)
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_delay = base_delay

    def search_blog(self, query: str, display: int = 30, start: int = 1, sort: str = "sim") -> List[BlogPostItem]:
        url = "https://openapi.naver.com/v1/search/blog.json"
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        params = {"query": query, "display": display, "start": start, "sort": sort}

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.get(url, headers=headers, params=params, timeout=self.timeout)

                if r.status_code in _RETRYABLE_STATUS and attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        "Naver API %d for query '%s' (attempt %d/%d), retrying in %.1fs",
                        r.status_code, query, attempt + 1, self.max_retries, delay,
                    )
                    time.sleep(delay)
                    continue

                r.raise_for_status()
                data = r.json()

                items: list[BlogPostItem] = []
                for it in data.get("items", []):
                    items.append(
                        BlogPostItem(
                            title=it.get("title", ""),
                            description=it.get("description", ""),
                            link=it.get("link", ""),
                            postdate=it.get("postdate"),
                            bloggerlink=it.get("bloggerlink"),
                            bloggername=it.get("bloggername"),
                        )
                    )
                return items

            except requests.exceptions.Timeout as e:
                last_exc = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        "Naver API timeout for query '%s' (attempt %d/%d), retrying in %.1fs",
                        query, attempt + 1, self.max_retries, delay,
                    )
                    time.sleep(delay)
                    continue
            except requests.exceptions.ConnectionError as e:
                last_exc = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        "Naver API connection error for query '%s' (attempt %d/%d), retrying in %.1fs",
                        query, attempt + 1, self.max_retries, delay,
                    )
                    time.sleep(delay)
                    continue
            except requests.exceptions.HTTPError:
                raise  # 4xx (401, 403 등)는 재시도하지 않음

        # 모든 재시도 소진
        if last_exc:
            raise last_exc
        return []


def get_env_client() -> NaverBlogSearchClient:
    cid = os.environ.get("NAVER_CLIENT_ID", "").strip()
    sec = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if not cid or not sec:
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET env vars are required")
    return NaverBlogSearchClient(cid, sec)
