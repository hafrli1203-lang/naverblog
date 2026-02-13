from __future__ import annotations
import os
import time
import urllib.parse
from typing import Any, Dict, List, Optional

import requests

from backend.models import BlogPostItem


class NaverBlogSearchClient:
    """
    네이버 검색 API(블로그) 호출 클라이언트
    """

    def __init__(self, client_id: str, client_secret: str, timeout: float = 10.0) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    def search_blog(self, query: str, display: int = 30, start: int = 1, sort: str = "sim") -> List[BlogPostItem]:
        url = "https://openapi.naver.com/v1/search/blog.json"
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        params = {"query": query, "display": display, "start": start, "sort": sort}

        r = requests.get(url, headers=headers, params=params, timeout=self.timeout)
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
                )
            )
        return items


def get_env_client() -> NaverBlogSearchClient:
    cid = os.environ.get("NAVER_CLIENT_ID", "").strip()
    sec = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if not cid or not sec:
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET env vars are required")
    return NaverBlogSearchClient(cid, sec)
