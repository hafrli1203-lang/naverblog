from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
import uuid as _uuid

from fastapi import FastAPI, HTTPException, Query, Request, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
import uvicorn

# .env 로드
load_dotenv(Path(__file__).parent / ".env")

from backend.db import (
    conn_ctx, init_db, upsert_store, create_campaign, insert_blog_analysis,
    save_search_snapshot, get_latest_search_snapshot,
    get_latest_blog_analysis, cleanup_expired_cache,
    # PRD 신규
    upsert_influencer_profile, get_influencer_profile, get_influencer_by_blog_id,
    update_influencer_fields, list_influencer_profiles, count_influencer_profiles,
    create_match, list_matches, get_match, update_match_status,
    create_notification, list_notifications, mark_notification_read, count_unread_notifications,
    create_survey, list_surveys, get_pending_surveys, submit_survey_response, get_survey_responses,
    toggle_survey_active, get_influencer_email,
)
from backend.email_sender import send_notification_email
from backend.keywords import StoreProfile, build_exposure_keywords, build_keyword_ab_sets, TOPIC_FOOD_SET, TOPIC_TEMPLATE_HINT
from backend.naver_client import get_env_client
from backend.analyzer import BloggerAnalyzer
from backend.maintenance import cleanup_all
from backend.reporting import get_top20_and_pool40
from backend.guide_generator import generate_guide, generate_keyword_recommendation, get_supported_categories
from backend.blog_analyzer import analyze_blog, extract_blogger_id
from backend.admin_db import (
    init_admin_db, create_ad as db_create_ad, update_ad as db_update_ad,
    delete_ad as db_delete_ad, get_ad as db_get_ad, list_ads as db_list_ads,
    match_ads as db_match_ads, record_impression as db_record_impression,
    record_click as db_record_click, get_ad_stats as db_get_ad_stats,
    get_ad_report as db_get_ad_report, log_page_view, log_search,
    log_event, get_today_stats, get_hourly_stats, get_range_stats,
    get_popular_searches, get_recent_searches, get_recent_events,
    get_user_stats, refresh_daily_stats,
    list_zones as db_list_zones, update_zone as db_update_zone,
    get_zone_inventory as db_get_zone_inventory,
    create_booking as db_create_booking, update_booking_status as db_update_booking_status,
    list_bookings as db_list_bookings, delete_booking as db_delete_booking,
    get_daily_ad_stats as db_get_daily_ad_stats,
    get_zone_performance as db_get_zone_performance,
    get_ad_performance as db_get_ad_performance,
)
from backend.admin_auth import verify_password, create_token, require_admin

logger = logging.getLogger("naverblog")


# ── 일반 사용자 인증 Dependency ──
async def get_current_user(request: Request) -> dict:
    """세션 쿠키를 Node.js /auth/me에 전달하여 사용자 정보 반환."""
    cookie = request.headers.get("cookie", "")
    if not cookie:
        raise HTTPException(401, "로그인이 필요합니다")
    try:
        client = await _get_proxy_client()
        resp = await client.get("/auth/me", headers={"Cookie": cookie})
    except Exception:
        raise HTTPException(503, "인증 서버 연결 실패")
    if resp.status_code != 200:
        raise HTTPException(401, "인증 실패")
    data = resp.json()
    if not data.get("loggedIn"):
        raise HTTPException(401, "로그인이 필요합니다")
    return data["user"]  # {id, displayName, email, provider, plan, role}


async def get_optional_user(request: Request) -> Optional[dict]:
    """로그인 선택적 — 비로그인 시 None 반환."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None

# ── 간이 Rate Limiter (인메모리, 새 의존성 없음) ──
import time as _time
from collections import defaultdict

_rate_buckets: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 30        # 1분 최대 횟수
_RATE_WINDOW = 60.0     # 윈도우 (초)


def _check_rate(key: str) -> bool:
    """간이 rate limiter. True면 허용, False면 차단."""
    now = _time.time()
    bucket = _rate_buckets[key]
    _rate_buckets[key] = bucket = [t for t in bucket if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_LIMIT:
        return False
    bucket.append(now)
    return True

app = FastAPI(title="블로그 체험단 모집 도구 v2.0")

ALLOWED_ORIGINS = [
    "https://naverblog.onrender.com",
    "https://xn--6j1b00mxunnyck8p.com",
    "https://www.xn--6j1b00mxunnyck8p.com",
    "http://localhost:8001",
    "http://localhost:5173",
    "http://127.0.0.1:8001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.on_event("startup")
def on_startup():
    with conn_ctx() as conn:
        init_db(conn)
        init_admin_db(conn)
        # 서버 시작 시 만료 캐시 자동 정리
        try:
            cleaned = cleanup_expired_cache(conn)
            if any(v > 0 for v in cleaned.values()):
                logger.info("서버 시작 캐시 정리: %s", cleaned)
        except Exception as e:
            logger.debug("서버 시작 캐시 정리 실패: %s", e)


# ============================
# SSE 스트리밍 분석 (GET - EventSource 호환)
# ============================
@app.get("/api/search/stream")
async def search_stream(
    request: Request,
    region: str = Query(...),
    category: str = Query(""),
    topic: str = Query(""),
    keyword: str = Query(""),
    place_url: Optional[str] = Query(None),
    store_name: Optional[str] = Query(None),
    address_text: Optional[str] = Query(None),
    memo: Optional[str] = Query(None),
    force_refresh: bool = Query(False),
):
    """프론트엔드 EventSource 호환 GET SSE 엔드포인트"""
    region = (region or "").strip()
    # keyword > legacy category > "" (하위 호환)
    effective_category = (keyword or category or "").strip()
    topic_val = (topic or "").strip()
    if not region:
        raise HTTPException(status_code=400, detail="지역을 입력해주세요.")

    # 사용 제한 체크 (로그인 사용자만)
    user = await get_optional_user(request)
    if user:
        with conn_ctx() as conn:
            if not _check_usage_limit(conn, user, "search"):
                raise HTTPException(429, "일일 무료 검색 횟수를 초과했습니다. 프로 플랜으로 업그레이드해주세요.")
            _record_usage(conn, user, "search")

    queue: asyncio.Queue[dict] = asyncio.Queue()

    def progress_cb(msg: dict):
        queue.put_nowait(msg)

    task = asyncio.get_event_loop().run_in_executor(
        None, _sync_analyze, region, effective_category, topic_val, place_url, store_name, address_text, memo, progress_cb, force_refresh
    )

    async def event_gen():
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.5)
                yield f"event: progress\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("stage") == "done":
                    break
            except asyncio.TimeoutError:
                if task.done():
                    # 큐에 남은 것 모두 처리
                    while not queue.empty():
                        msg = queue.get_nowait()
                        yield f"event: progress\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                    break
                yield f"event: progress\ndata: {json.dumps({'stage': 'waiting', 'current': 0, 'total': 0, 'message': '처리 중...'}, ensure_ascii=False)}\n\n"

        try:
            result = await task
            yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"event: result\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sync_analyze(region_text, category_text, topic_val, place_url, store_name, address_text, memo, progress_cb, force_refresh=False):
    import logging
    _logger = logging.getLogger("naverblog.search")
    _logger.info(
        "[검색 파라미터] region=%r, category_text=%r, topic=%r, store_name=%r, force_refresh=%r",
        region_text, category_text, topic_val, store_name, force_refresh,
    )
    with conn_ctx() as conn:
        store_id = upsert_store(
            conn,
            region_text=region_text,
            category_text=category_text,
            place_url=place_url,
            store_name=store_name,
            address_text=address_text,
            topic=topic_val or None,
        )
        campaign_id = create_campaign(conn, store_id, memo=memo)

        # Layer 3: 스냅샷 캐시 확인 (force_refresh가 아닌 경우)
        if not force_refresh:
            try:
                snapshot = get_latest_search_snapshot(conn, store_id)
                if snapshot:
                    _logger.info("[캐시 히트] store_id=%d, cached_at=%s", store_id, snapshot["created_at"])
                    progress_cb({"stage": "done", "current": 1, "total": 1, "message": "캐시된 결과 사용"})
                    result = json.loads(snapshot["snapshot_json"])
                    result["meta"]["from_cache"] = True
                    result["meta"]["cached_at"] = snapshot["created_at"]
                    result["meta"]["campaign_id"] = campaign_id
                    return result
            except Exception as e:
                _logger.debug("스냅샷 캐시 조회 실패: %s", e)

        # 음식 업종 판별: 키워드 또는 주제 기반
        effective_cat_for_food = category_text
        if not category_text and topic_val and topic_val in TOPIC_FOOD_SET:
            effective_cat_for_food = "맛집"

        profile = StoreProfile(
            region_text=region_text,
            category_text=category_text,
            topic=topic_val or None,
            place_url=place_url,
            store_name=store_name,
            address_text=address_text,
        )

        client = get_env_client()  # → CachedNaverBlogSearchClient (Layer 2 자동 적용)
        analyzer = BloggerAnalyzer(client=client, profile=profile, store_id=store_id, progress_cb=progress_cb)
        seed_calls, exposure_calls, keywords = analyzer.analyze(conn, top_n=50)

        cleanup_all(conn, keep_days=180)

        result = get_top20_and_pool40(conn, store_id=store_id, days=30,
                                       category_text=effective_cat_for_food)

        progress_cb({"stage": "done", "current": 1, "total": 1, "message": "분석 완료 (GoldenScore v7.2)"})

        # result["meta"]와 병합 (result의 meta가 덮어쓰지 않도록)
        merged_meta = {
            "store_id": store_id,
            "campaign_id": campaign_id,
            "seed_calls": seed_calls,
            "exposure_calls": exposure_calls,
            "exposure_keywords": keywords,
            "from_cache": False,
        }
        # API 캐시 통계 추가 + 로깅
        cache_stats = getattr(client, "cache_stats", None)
        if cache_stats:
            merged_meta["cache_stats"] = cache_stats
            _logger.info(
                "캐시 통계: hits=%d, misses=%d, hit_rate=%.0f%%",
                cache_stats.get("hits", 0),
                cache_stats.get("misses", 0),
                cache_stats.get("hits", 0) / max(1, cache_stats.get("hits", 0) + cache_stats.get("misses", 0)) * 100,
            )
        merged_meta.update(result.pop("meta", {}))

        full_result = {
            "meta": merged_meta,
            **result,
        }

        # Layer 3: 스냅샷 저장
        try:
            total_api = seed_calls + exposure_calls
            save_search_snapshot(conn, store_id, json.dumps(full_result, ensure_ascii=False), total_api)
        except Exception as e:
            _logger.debug("스냅샷 저장 실패: %s", e)

        # 검색 로그 자동 기록
        try:
            from datetime import date as _date
            log_search(conn, "server", region_text, topic_val or None, category_text or None,
                        store_name or None, len(result.get("top20", [])))
            refresh_daily_stats(conn, _date.today().isoformat())
        except Exception as e:
            _logger.debug("검색 로그 기록 실패: %s", e)

        return full_result


# ============================
# 동기 분석 (폴백)
# ============================
@app.post("/api/search")
def search_sync(
    region: str = Query(...),
    category: str = Query(""),
    topic: str = Query(""),
    keyword: str = Query(""),
    place_url: Optional[str] = Query(None),
    store_name: Optional[str] = Query(None),
    address_text: Optional[str] = Query(None),
    force_refresh: bool = Query(False),
):
    region = (region or "").strip()
    effective_category = (keyword or category or "").strip()
    topic_val = (topic or "").strip()
    if not region:
        raise HTTPException(400, "지역을 입력해주세요.")

    result = _sync_analyze(region, effective_category, topic_val, place_url, store_name, address_text, None, lambda _: None, force_refresh)
    return result


# ============================
# 매장/캠페인 조회
# ============================
@app.get("/api/stores")
def list_stores():
    with conn_ctx() as conn:
        rows = conn.execute("SELECT * FROM stores ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]


@app.get("/api/stores/{store_id}/top")
def get_store_top(store_id: int, days: int = 30):
    with conn_ctx() as conn:
        row = conn.execute("SELECT category_text, topic FROM stores WHERE store_id=?", (store_id,)).fetchone()
        cat = row["category_text"] if row else ""
        topic_val = row["topic"] if row else ""
        # 주제 기반 음식 카테고리 판별
        if not cat and topic_val and topic_val in TOPIC_FOOD_SET:
            cat = "맛집"
        return get_top20_and_pool40(conn, store_id=store_id, days=days, category_text=cat)


@app.delete("/api/stores/{store_id}")
def delete_store(store_id: int):
    with conn_ctx() as conn:
        conn.execute("DELETE FROM stores WHERE store_id=?", (store_id,))
        return {"ok": True}


# ============================
# 캠페인 CRUD (DB 기반)
# ============================
class CampaignCreateRequest(BaseModel):
    name: str
    region: str
    category: str
    memo: Optional[str] = ""


class CampaignUpdateRequest(BaseModel):
    status: Optional[str] = None
    memo: Optional[str] = None


@app.post("/api/campaigns")
def create_campaign_api(data: CampaignCreateRequest):
    with conn_ctx() as conn:
        store_id = upsert_store(conn, data.region, data.category, None, data.name, None)
        cid = create_campaign(conn, store_id, memo=data.memo)
        return {
            "id": str(cid),
            "campaign_id": cid,
            "store_id": store_id,
            "name": data.name,
            "region": data.region,
            "category": data.category,
            "memo": data.memo,
            "status": "대기중",
        }


@app.get("/api/campaigns")
def list_campaigns():
    with conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT c.campaign_id, c.store_id, c.memo, c.status, c.created_at, c.updated_at,
                   s.store_name, s.region_text, s.category_text
            FROM campaigns c
            JOIN stores s ON s.store_id = c.store_id
            ORDER BY c.created_at DESC
            """
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["id"] = str(d["campaign_id"])
            d["name"] = d.get("store_name") or f"{d['region_text']} {d['category_text']}"
            d["region"] = d["region_text"]
            d["category"] = d["category_text"]
            result.append(d)
        return result


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: str):
    with conn_ctx() as conn:
        row = conn.execute(
            """
            SELECT c.*, s.store_name, s.region_text, s.category_text, s.place_url, s.address_text
            FROM campaigns c
            JOIN stores s ON s.store_id = c.store_id
            WHERE c.campaign_id = ?
            """,
            (int(campaign_id),),
        ).fetchone()
        if not row:
            raise HTTPException(404, "캠페인을 찾을 수 없습니다.")
        d = dict(row)
        d["id"] = str(d["campaign_id"])
        d["name"] = d.get("store_name") or f"{d['region_text']} {d['category_text']}"
        d["region"] = d["region_text"]
        d["category"] = d["category_text"]

        # Top20/Pool40 블로거 데이터 포함
        top = get_top20_and_pool40(conn, d["store_id"], days=30, category_text=d.get("category_text", ""))
        d["top20"] = top["top20"]
        d["pool40"] = top["pool40"]
        return d


@app.put("/api/campaigns/{campaign_id}")
def update_campaign(campaign_id: str, data: CampaignUpdateRequest):
    with conn_ctx() as conn:
        existing = conn.execute("SELECT campaign_id FROM campaigns WHERE campaign_id=?", (int(campaign_id),)).fetchone()
        if not existing:
            raise HTTPException(404, "캠페인을 찾을 수 없습니다.")
        if data.status:
            conn.execute("UPDATE campaigns SET status=?, updated_at=datetime('now') WHERE campaign_id=?", (data.status, int(campaign_id)))
        if data.memo is not None:
            conn.execute("UPDATE campaigns SET memo=?, updated_at=datetime('now') WHERE campaign_id=?", (data.memo, int(campaign_id)))
        return {"ok": True}


@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str):
    with conn_ctx() as conn:
        # 캠페인의 store_id도 함께 삭제(CASCADE로 exposures도 삭제됨)
        row = conn.execute("SELECT store_id FROM campaigns WHERE campaign_id=?", (int(campaign_id),)).fetchone()
        if row:
            conn.execute("DELETE FROM stores WHERE store_id=?", (row["store_id"],))
        return {"ok": True, "message": "캠페인이 삭제되었습니다."}


# ============================
# A/B 키워드 추천
# ============================
@app.get("/api/stores/{store_id}/keywords")
def get_store_keywords(store_id: int):
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT region_text, category_text, store_name, address_text, place_url, topic FROM stores WHERE store_id=?",
            (store_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "매장을 찾을 수 없습니다.")

        # 데이터 기반 A/B: 실제 노출 데이터에서 키워드 성과 분석
        exposure_rows = conn.execute(
            """
            SELECT keyword,
                   SUM(strength_points) as total_strength,
                   COUNT(DISTINCT blogger_id) as blogger_count,
                   SUM(CASE WHEN is_page1=1 THEN 1 ELSE 0 END) as page1_count
            FROM exposures
            WHERE store_id = ? AND is_exposed = 1
              AND checked_at >= datetime('now', '-30 days')
            GROUP BY keyword
            ORDER BY total_strength DESC, page1_count DESC
            """,
            (store_id,),
        ).fetchall()

        if exposure_rows and len(exposure_rows) >= 3:
            # 데이터 기반: 실제 노출 성과로 A/B 세트 구성
            all_keywords = [dict(r) for r in exposure_rows]

            # Set A: 노출 강도 상위 5개 (검증된 상위노출 키워드)
            set_a = [kw["keyword"] for kw in all_keywords[:5]]

            # Set B: 나머지 키워드 (확장 노출 가능성)
            set_b = [kw["keyword"] for kw in all_keywords[5:10]]

            # 노출 통계 포함
            set_a_stats = [
                f"{kw['keyword']} (강도:{kw['total_strength']}, 1페이지:{kw['page1_count']}건)"
                for kw in all_keywords[:5]
            ]
            set_b_stats = [
                f"{kw['keyword']} (강도:{kw['total_strength']}, 1페이지:{kw['page1_count']}건)"
                for kw in all_keywords[5:10]
            ]

            return {
                "set_a": set_a,
                "set_b": set_b,
                "set_a_label": "상위노출 키워드 (실제 노출 데이터 기반)",
                "set_b_label": "추가 노출 키워드 (확장 가능성)",
                "set_a_stats": set_a_stats,
                "set_b_stats": set_b_stats,
                "data_driven": True,
            }

        # 폴백: 정적 템플릿 기반
        profile = StoreProfile(
            region_text=row["region_text"],
            category_text=row["category_text"],
            topic=row["topic"],
            store_name=row["store_name"],
            address_text=row["address_text"],
            place_url=row["place_url"],
        )

        ab = build_keyword_ab_sets(profile)
        return ab


# ============================
# 가이드 자동 생성
# ============================
@app.get("/api/stores/{store_id}/guide")
def get_store_guide(store_id: int, sub_category: str = Query("", description="세부 업종 (선택)")):
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT region_text, category_text, store_name, address_text, topic FROM stores WHERE store_id=?",
            (store_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "매장을 찾을 수 없습니다.")

        # 노출 데이터에서 메인 키워드 추출
        top_kw_rows = conn.execute(
            """
            SELECT keyword, SUM(strength_points) as total_strength
            FROM exposures
            WHERE store_id = ? AND is_exposed = 1
              AND checked_at >= datetime('now', '-30 days')
            GROUP BY keyword
            ORDER BY total_strength DESC
            LIMIT 3
            """,
            (store_id,),
        ).fetchall()

        main_keyword_override = None
        sub_keywords_list = None
        if top_kw_rows:
            main_keyword_override = top_kw_rows[0]["keyword"]
            if len(top_kw_rows) > 1:
                sub_keywords_list = [r["keyword"] for r in top_kw_rows[1:3]]

        # 가이드 템플릿 매칭: 키워드 > 주제 힌트 > 기본
        template_category = row["category_text"] or ""
        topic_val = row["topic"] or ""
        if not template_category and topic_val:
            template_category = TOPIC_TEMPLATE_HINT.get(topic_val, topic_val)

        guide = generate_guide(
            region=row["region_text"],
            category=template_category,
            store_name=row["store_name"] or "",
            address=row["address_text"] or "",
            main_keyword_override=main_keyword_override,
            sub_keywords=sub_keywords_list,
            sub_category=sub_category,
        )
        return guide


# ============================
# 키워드 추천 (매장 없이 독립 사용)
# ============================
@app.get("/api/guide/keywords/{category}")
def get_guide_keywords(
    category: str,
    region: str = Query("", description="지역명"),
    sub: str = Query("", description="세부 업종"),
):
    """3계층 키워드 추천만 반환 (매장 연계 없이 독립 사용)"""
    result = generate_keyword_recommendation(
        region=region,
        category=category,
        sub_category=sub,
    )
    return result


@app.get("/api/guide/categories")
def get_guide_categories():
    """지원 업종 목록 반환"""
    return {"categories": get_supported_categories()}


# ============================
# 메시지 템플릿
# ============================
@app.get("/api/stores/{store_id}/message-template")
def get_message_template(store_id: int):
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT region_text, category_text, store_name, address_text, topic FROM stores WHERE store_id=?",
            (store_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "매장을 찾을 수 없습니다.")

        region = row["region_text"]
        category = row["category_text"] or ""
        topic_val = row["topic"] or ""
        store_name = row["store_name"] or f"{region} 매장"

        # 노출 데이터에서 추천 키워드 추출
        top_kw_rows = conn.execute(
            """
            SELECT keyword, SUM(strength_points) as total_strength
            FROM exposures
            WHERE store_id = ? AND is_exposed = 1
              AND checked_at >= datetime('now', '-30 days')
            GROUP BY keyword
            ORDER BY total_strength DESC
            LIMIT 3
            """,
            (store_id,),
        ).fetchall()
        top_keywords = [r["keyword"] for r in top_kw_rows] if top_kw_rows else []

        # 업종 설명: 키워드 > 주제 > 생략
        cat_desc = category or ""

        template = (
            f"안녕하세요, {store_name} 담당자입니다.\n\n"
            f"블로거님의 블로그를 관심 있게 보고 있었는데,\n"
            f"저희 매장 체험단에 참여해주실 의향이 있으신지 여쭤보려고 연락드렸습니다.\n\n"
            f"[매장 정보]\n"
            f"- 매장명: {store_name}\n"
            f"- 지역: {region}\n"
        )
        if cat_desc:
            template += f"- 업종: {cat_desc}\n"

        template += (
            f"\n[체험 내용]\n"
            f"- 제공: 메뉴/서비스 무료 체험\n"
            f"- 조건: 방문 후 솔직한 블로그 리뷰 1건 작성\n"
            f"- 기한: 방문일로부터 7일 이내 포스팅\n"
        )

        if top_keywords:
            template += f"\n[추천 키워드]\n"
            for kw in top_keywords[:3]:
                template += f"- {kw}\n"

        template += (
            f"\n관심이 있으시다면 편하게 답장 부탁드립니다.\n"
            f"일정 조율 후 방문 안내 드리겠습니다.\n\n"
            f"감사합니다.\n"
            f"{store_name} 드림"
        )

        return {
            "store_name": store_name,
            "region": region,
            "category": cat_desc,
            "template": template,
            "top_keywords": top_keywords,
        }


# ============================
# 블로그 개별 분석 (SSE)
# ============================
@app.get("/api/blog-analysis/stream")
async def blog_analysis_stream(
    request: Request,
    blog_url: str = Query(...),
    store_id: Optional[int] = Query(None),
    force_refresh: bool = Query(False),
):
    """블로그 개별 분석 — SSE 스트리밍"""
    blog_url_val = (blog_url or "").strip()
    if not blog_url_val:
        raise HTTPException(400, "블로그 URL 또는 ID를 입력해주세요.")

    bid = extract_blogger_id(blog_url_val)
    if not bid:
        raise HTTPException(400, "유효하지 않은 블로그 URL/ID입니다.")

    # 사용 제한 체크 (로그인 사용자만)
    user = await get_optional_user(request)
    if user:
        with conn_ctx() as conn:
            if not _check_usage_limit(conn, user, "blog_analysis"):
                raise HTTPException(429, "일일 무료 블로그 분석 횟수를 초과했습니다. 프로 플랜으로 업그레이드해주세요.")
            _record_usage(conn, user, "blog_analysis")

    queue: asyncio.Queue[dict] = asyncio.Queue()

    def progress_cb(msg: dict):
        queue.put_nowait(msg)

    task = asyncio.get_event_loop().run_in_executor(
        None, _sync_blog_analysis, blog_url_val, store_id, progress_cb, force_refresh
    )

    async def event_gen():
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.5)
                yield f"event: progress\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("stage") == "done":
                    break
            except asyncio.TimeoutError:
                if task.done():
                    while not queue.empty():
                        msg = queue.get_nowait()
                        yield f"event: progress\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                    break
                yield f"event: progress\ndata: {json.dumps({'stage': 'waiting', 'current': 0, 'total': 0, 'message': '분석 중...'}, ensure_ascii=False)}\n\n"

        try:
            result = await task
            yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"event: result\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sync_blog_analysis(blog_url_val: str, store_id: Optional[int], progress_cb, force_refresh: bool = False):
    bid = extract_blogger_id(blog_url_val)

    # 블로그 분석 캐시 확인 (force_refresh가 아닌 경우)
    if not force_refresh and bid:
        try:
            with conn_ctx() as conn:
                cached = get_latest_blog_analysis(conn, bid, store_id, ttl_hours=48)
                if cached:
                    progress_cb({"stage": "done", "current": 1, "total": 1, "message": "캐시된 분석 결과 사용"})
                    result = json.loads(cached["result_json"])
                    result["from_cache"] = True
                    result["cached_at"] = cached["created_at"]
                    return result
        except Exception:
            pass  # 캐시 실패 시 라이브 분석

    client = get_env_client()
    store_profile = None

    if store_id:
        with conn_ctx() as conn:
            row = conn.execute(
                "SELECT region_text, category_text, store_name, address_text, place_url, topic FROM stores WHERE store_id=?",
                (store_id,),
            ).fetchone()
            if row:
                store_profile = StoreProfile(
                    region_text=row["region_text"],
                    category_text=row["category_text"],
                    topic=row["topic"],
                    store_name=row["store_name"],
                    address_text=row["address_text"],
                    place_url=row["place_url"],
                )

    result = analyze_blog(
        blog_url_or_id=blog_url_val,
        client=client,
        store_profile=store_profile,
        progress_cb=progress_cb,
    )

    # DB에 분석 이력 저장
    with conn_ctx() as conn:
        insert_blog_analysis(
            conn,
            blogger_id=result["blogger_id"],
            blog_url=result["blog_url"],
            analysis_mode=result["analysis_mode"],
            store_id=store_id,
            blog_score=result["blog_score"]["total"],
            grade=result["blog_score"]["grade"],
            result_json=json.dumps(result, ensure_ascii=False),
        )

    result["from_cache"] = False
    # API 캐시 통계 추가
    cache_stats = getattr(client, "cache_stats", None)
    if cache_stats:
        result["cache_stats"] = cache_stats

    progress_cb({"stage": "done", "current": 1, "total": 1, "message": "분석 완료"})
    return result


class BlogAnalysisRequest(BaseModel):
    blog_url: str
    store_id: Optional[int] = None


@app.post("/api/blog-analysis")
def blog_analysis_sync(data: BlogAnalysisRequest):
    """블로그 개별 분석 — 동기 폴백"""
    result = _sync_blog_analysis(data.blog_url.strip(), data.store_id, lambda _: None, force_refresh=False)
    return result


# ============================
# 캐시 통계
# ============================
@app.get("/api/cache/stats")
def cache_stats():
    """활성 캐시 수 반환"""
    with conn_ctx() as conn:
        api_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM api_cache WHERE expires_at > datetime('now')"
        ).fetchone()["cnt"]
        snapshot_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM search_snapshots WHERE expires_at > datetime('now')"
        ).fetchone()["cnt"]
        analysis_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM blog_analyses WHERE created_at > datetime('now', '-48 hours')"
        ).fetchone()["cnt"]
        return {
            "api_cache_active": api_count,
            "snapshots_active": snapshot_count,
            "blog_analyses_recent": analysis_count,
        }


# ============================
# 인플루언서 프로필/마켓플레이스 (Stage 3)
# ============================

@app.post("/api/influencer/register")
async def influencer_register(request: Request, user: dict = Depends(get_current_user)):
    """블로그 URL 등록 + GoldenScore 분석 실행."""
    body = await request.json()
    blog_url_val = (body.get("blog_url") or "").strip()
    if not blog_url_val:
        raise HTTPException(400, "블로그 URL을 입력해주세요.")
    bid = extract_blogger_id(blog_url_val)
    if not bid:
        raise HTTPException(400, "유효하지 않은 블로그 URL입니다.")

    # 동기 분석 실행
    result = _sync_blog_analysis(blog_url_val, None, lambda _: None, force_refresh=True)

    # 분석 결과를 influencer_profiles에 저장
    bs = result.get("blog_score", {})
    base_bd = bs.get("base_breakdown", {})
    with conn_ctx() as conn:
        upsert_influencer_profile(
            conn,
            user_mongo_id=user["id"],
            blog_id=bid,
            blog_url=f"https://blog.naver.com/{bid}",
            golden_score=bs.get("total", 0),
            grade=bs.get("grade", "F"),
            grade_label=bs.get("grade_label", ""),
            base_score=bs.get("base_score", 0),
            bp_score=base_bd.get("BlogPower", 0),
            ep_score=base_bd.get("ExposurePower", 0),
            ca_score=base_bd.get("ContentAuthority", 0),
            rq_score=base_bd.get("RSSQuality", 0),
            fr_score=base_bd.get("Freshness", 0),
            sp_score=base_bd.get("SearchPresence", 0),
            total_posts=result.get("profile", {}).get("total_posts", 0),
            total_visitors=result.get("profile", {}).get("total_visitors", 0),
            total_subscribers=result.get("profile", {}).get("total_subscribers", 0),
            desired_rate=body.get("desired_rate", 0),
            bio=body.get("bio", ""),
            specialties=json.dumps(body.get("specialties", []), ensure_ascii=False),
            email=user.get("email", ""),
        )

    return {"ok": True, "blog_id": bid, "blog_score": bs, "result": result}


@app.get("/api/influencer/profile")
async def influencer_profile_get(user: dict = Depends(get_current_user)):
    """자신의 인플루언서 프로필 + GoldenScore 조회."""
    with conn_ctx() as conn:
        profile = get_influencer_profile(conn, user["id"])
    if not profile:
        return {"registered": False}
    profile["registered"] = True
    return profile


@app.put("/api/influencer/profile")
async def influencer_profile_update(request: Request, user: dict = Depends(get_current_user)):
    """희망 단가/자기소개/전문 업종 수정."""
    body = await request.json()
    fields = {}
    if "desired_rate" in body:
        fields["desired_rate"] = int(body["desired_rate"])
    if "bio" in body:
        fields["bio"] = str(body["bio"])
    if "specialties" in body:
        fields["specialties"] = json.dumps(body["specialties"], ensure_ascii=False) if isinstance(body["specialties"], list) else str(body["specialties"])
    if "is_public" in body:
        fields["is_public"] = 1 if body["is_public"] else 0
    with conn_ctx() as conn:
        update_influencer_fields(conn, user["id"], fields)
        profile = get_influencer_profile(conn, user["id"])
    return profile or {"ok": True}


@app.get("/api/influencer/marketplace")
async def influencer_marketplace(
    page: int = Query(1),
    limit: int = Query(20),
    min_score: float = Query(0),
    specialty: str = Query(""),
):
    """자영업자용 인플루언서 목록 (GoldenScore 순, 페이지네이션)."""
    offset = (max(1, page) - 1) * limit
    with conn_ctx() as conn:
        items = list_influencer_profiles(conn, offset=offset, limit=limit, min_score=min_score, specialty=specialty)
        total = count_influencer_profiles(conn, min_score=min_score, specialty=specialty)
    return {"items": items, "total": total, "page": page, "limit": limit}


@app.get("/api/influencer/marketplace/{blog_id}")
async def influencer_marketplace_detail(blog_id: str):
    """인플루언서 상세 프로필."""
    with conn_ctx() as conn:
        profile = get_influencer_by_blog_id(conn, blog_id)
    if not profile:
        raise HTTPException(404, "인플루언서를 찾을 수 없습니다.")
    return profile


# ============================
# 매칭 프로세스 (Stage 4)
# ============================

@app.post("/api/matches")
async def create_match_api(request: Request, user: dict = Depends(get_current_user)):
    """자영업자가 매칭 요청."""
    body = await request.json()
    inf_blog_id = body.get("influencer_blog_id", "")
    if not inf_blog_id:
        raise HTTPException(400, "인플루언서 블로그 ID가 필요합니다.")
    # 사용 제한 체크
    with conn_ctx() as conn:
        if not _check_usage_limit(conn, user, "match_request"):
            raise HTTPException(429, "일일 무료 매칭 요청 횟수를 초과했습니다. 프로 플랜으로 업그레이드해주세요.")
        _record_usage(conn, user, "match_request")
    # 인플루언서 user_id 조회
    with conn_ctx() as conn:
        inf_profile = get_influencer_by_blog_id(conn, inf_blog_id)
        if not inf_profile:
            raise HTTPException(404, "인플루언서를 찾을 수 없습니다.")
        mid = create_match(
            conn,
            owner_user_id=user["id"],
            owner_display_name=user.get("displayName", ""),
            influencer_user_id=inf_profile["user_mongo_id"],
            influencer_blog_id=inf_blog_id,
            store_id=body.get("store_id"),
            campaign_type=body.get("campaign_type", "experience"),
            message=body.get("message", ""),
            offered_rate=body.get("offered_rate", 0),
            owner_email=user.get("email", ""),
        )
        # 인플루언서에게 알림
        create_notification(
            conn,
            user_id=inf_profile["user_mongo_id"],
            ntype="match_request",
            title="새 체험단 매칭 요청",
            message=f"{user.get('displayName', '자영업자')}님이 매칭을 요청했습니다.",
            link=f"/matches/{mid}",
        )
        # 인플루언서에게 이메일 발송
        inf_email = get_influencer_email(conn, inf_profile["user_mongo_id"])
        if inf_email:
            send_notification_email(
                to_email=inf_email,
                recipient_name=inf_blog_id,
                title="새 체험단 매칭 요청",
                message=f"{user.get('displayName', '자영업자')}님이 체험단 매칭을 요청했습니다. 확인 후 수락 또는 거절해주세요.",
                link=f"/matches/{mid}",
            )
    return {"ok": True, "match_id": mid}


@app.get("/api/matches")
async def list_matches_api(
    role: str = Query("sent"),
    status: str = Query(""),
    user: dict = Depends(get_current_user),
):
    """매칭 목록 (발신: sent / 수신: received)."""
    with conn_ctx() as conn:
        items = list_matches(conn, user["id"], role=role, status=status)
    return items


@app.get("/api/matches/{match_id}")
async def get_match_api(match_id: int, user: dict = Depends(get_current_user)):
    """매칭 상세."""
    with conn_ctx() as conn:
        m = get_match(conn, match_id)
    if not m:
        raise HTTPException(404, "매칭을 찾을 수 없습니다.")
    if m["owner_user_id"] != user["id"] and m["influencer_user_id"] != user["id"]:
        raise HTTPException(403, "접근 권한이 없습니다.")
    return m


@app.put("/api/matches/{match_id}/respond")
async def respond_match_api(match_id: int, request: Request, user: dict = Depends(get_current_user)):
    """인플루언서 수락/거절."""
    body = await request.json()
    status_val = body.get("status", "")
    if status_val not in ("accepted", "declined"):
        raise HTTPException(400, "accepted 또는 declined만 가능합니다.")
    with conn_ctx() as conn:
        m = get_match(conn, match_id)
        if not m:
            raise HTTPException(404, "매칭을 찾을 수 없습니다.")
        if m["influencer_user_id"] != user["id"]:
            raise HTTPException(403, "인플루언서만 응답할 수 있습니다.")
        update_match_status(conn, match_id, status_val, body.get("decline_reason", ""))
        # 자영업자에게 알림
        msg = "수락되었습니다" if status_val == "accepted" else "거절되었습니다"
        create_notification(
            conn,
            user_id=m["owner_user_id"],
            ntype="match_response",
            title=f"매칭 요청이 {msg}",
            message=f"인플루언서가 매칭 요청을 {msg}.",
            link=f"/matches/{match_id}",
        )
        # 자영업자에게 이메일 발송
        owner_email = m.get("owner_email", "")
        if owner_email:
            send_notification_email(
                to_email=owner_email,
                recipient_name=m.get("owner_display_name", ""),
                title=f"매칭 요청이 {msg}",
                message=f"인플루언서({m['influencer_blog_id']})가 매칭 요청을 {msg}.",
                link=f"/matches/{match_id}",
            )
    return {"ok": True}


@app.put("/api/matches/{match_id}/complete")
async def complete_match_api(match_id: int, user: dict = Depends(get_current_user)):
    """완료 처리."""
    with conn_ctx() as conn:
        m = get_match(conn, match_id)
        if not m:
            raise HTTPException(404)
        if m["owner_user_id"] != user["id"]:
            raise HTTPException(403, "자영업자만 완료 처리할 수 있습니다.")
        update_match_status(conn, match_id, "completed")
    return {"ok": True}


@app.get("/api/matches/{match_id}/guide")
async def match_guide_api(match_id: int, user: dict = Depends(get_current_user)):
    """매칭 가이드라인 조회 (guide_generator 활용)."""
    with conn_ctx() as conn:
        m = get_match(conn, match_id)
        if not m:
            raise HTTPException(404)
        if m["owner_user_id"] != user["id"] and m["influencer_user_id"] != user["id"]:
            raise HTTPException(403)
        # store_id가 있으면 매장 정보로 가이드 생성
        if m.get("store_id"):
            row = conn.execute(
                "SELECT region_text, category_text, store_name, address_text FROM stores WHERE store_id=?",
                (m["store_id"],)
            ).fetchone()
            if row:
                guide = generate_guide(
                    region=row["region_text"],
                    category=row["category_text"],
                    store_name=row["store_name"] or "",
                    address=row["address_text"] or "",
                )
                return guide
    return {"guide": "매장 정보가 없어 기본 가이드를 제공합니다.", "sections": []}


# ============================
# 사용 제한 (Stage 5)
# ============================

FREE_LIMITS = {"search": 3, "blog_analysis": 5, "match_request": 3}  # 일별


def _check_usage_limit(conn, user: dict, action: str) -> bool:
    """free 사용자 일별 사용량 체크. True면 허용."""
    if user.get("plan") == "pro" or user.get("role") == "admin":
        return True
    limit = FREE_LIMITS.get(action, 999)
    today = date.today().isoformat()
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM user_events WHERE session_id=? AND event_type=? AND created_at >= ?",
        (user["id"], f"usage_{action}", today),
    ).fetchone()["cnt"]
    return count < limit


def _record_usage(conn, user: dict, action: str):
    """사용량 기록."""
    log_event(conn, user["id"], f"usage_{action}", json.dumps({"action": action}))


@app.get("/api/usage/check")
async def check_usage(action: str = Query(...), user: dict = Depends(get_optional_user)):
    """사용 제한 사전 체크. SSE 스트림 시작 전 프론트엔드에서 호출."""
    if not user:
        return {"allowed": True, "remaining": None}  # 비로그인 사용자 허용
    with conn_ctx() as conn:
        allowed = _check_usage_limit(conn, user, action)
        limit = FREE_LIMITS.get(action, 999)
        today = date.today().isoformat()
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM user_events WHERE session_id=? AND event_type=? AND created_at >= ?",
            (user["id"], f"usage_{action}", today),
        ).fetchone()["cnt"]
    return {"allowed": allowed, "remaining": max(0, limit - count), "limit": limit, "plan": user.get("plan", "free")}


# ============================
# 알림 시스템 (Stage 6)
# ============================

@app.get("/api/notifications")
async def notifications_list(user: dict = Depends(get_current_user)):
    with conn_ctx() as conn:
        items = list_notifications(conn, user["id"], limit=20)
    return items


@app.put("/api/notifications/{notif_id}/read")
async def notification_mark_read(notif_id: int, user: dict = Depends(get_current_user)):
    with conn_ctx() as conn:
        mark_notification_read(conn, notif_id)
    return {"ok": True}


@app.get("/api/notifications/unread-count")
async def notifications_unread_count(user: dict = Depends(get_current_user)):
    with conn_ctx() as conn:
        cnt = count_unread_notifications(conn, user["id"])
    return {"count": cnt}


# ============================
# 서베이 (Stage 7)
# ============================

@app.get("/api/surveys/pending")
async def surveys_pending(user: dict = Depends(get_current_user)):
    with conn_ctx() as conn:
        items = get_pending_surveys(conn, user["id"])
    return items


@app.post("/api/surveys/{survey_id}/respond")
async def survey_respond(survey_id: int, request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    answers = json.dumps(body.get("answers", {}), ensure_ascii=False)
    with conn_ctx() as conn:
        rid = submit_survey_response(conn, survey_id, user["id"], answers)
    return {"ok": True, "response_id": rid}


# ── 서베이 관리자 ──

@app.post("/admin/surveys")
async def admin_create_survey(request: Request, _=Depends(require_admin)):
    body = await request.json()
    with conn_ctx() as conn:
        sid = create_survey(
            conn,
            title=body.get("title", ""),
            questions=json.dumps(body.get("questions", []), ensure_ascii=False),
            target=body.get("target", "all"),
        )
    return {"ok": True, "survey_id": sid}


@app.get("/admin/surveys")
async def admin_list_surveys(_=Depends(require_admin)):
    with conn_ctx() as conn:
        return list_surveys(conn, active_only=False)


@app.get("/admin/surveys/{survey_id}/responses")
async def admin_survey_responses(survey_id: int, _=Depends(require_admin)):
    with conn_ctx() as conn:
        return get_survey_responses(conn, survey_id)


@app.put("/admin/surveys/{survey_id}/toggle")
async def admin_toggle_survey(survey_id: int, request: Request, _=Depends(require_admin)):
    body = await request.json()
    with conn_ctx() as conn:
        toggle_survey_active(conn, survey_id, bool(body.get("is_active", False)))
    return {"ok": True}


# ============================
# CSV 추출 (Stage 7, 관리자)
# ============================

def _rows_to_csv(rows: List[Dict], columns: List[str]) -> str:
    import csv
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for r in rows:
        writer.writerow([r.get(c, "") for c in columns])
    return buf.getvalue()


@app.get("/admin/export/stores")
async def admin_export_stores(_=Depends(require_admin)):
    with conn_ctx() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM stores ORDER BY store_id").fetchall()]
    csv_str = _rows_to_csv(rows, ["store_id", "store_name", "region_text", "category_text", "topic", "created_at"])
    return Response(content=csv_str, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=stores.csv"})


@app.get("/admin/export/bloggers")
async def admin_export_bloggers(_=Depends(require_admin)):
    with conn_ctx() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT blogger_id, blog_url, base_score, blog_power, total_posts, total_visitors, last_seen_at FROM bloggers ORDER BY base_score DESC LIMIT 1000"
        ).fetchall()]
    csv_str = _rows_to_csv(rows, ["blogger_id", "blog_url", "base_score", "blog_power", "total_posts", "total_visitors", "last_seen_at"])
    return Response(content=csv_str, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=bloggers.csv"})


@app.get("/admin/export/matches")
async def admin_export_matches(_=Depends(require_admin)):
    with conn_ctx() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM matches ORDER BY requested_at DESC").fetchall()]
    cols = ["match_id", "owner_user_id", "owner_display_name", "influencer_blog_id", "status", "offered_rate", "requested_at", "responded_at"]
    csv_str = _rows_to_csv(rows, cols)
    return Response(content=csv_str, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=matches.csv"})


@app.get("/admin/export/searches")
async def admin_export_searches(_=Depends(require_admin)):
    with conn_ctx() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM search_logs ORDER BY created_at DESC LIMIT 5000"
        ).fetchall()]
    cols = ["session_id", "region", "topic", "category", "store_name", "result_count", "created_at"]
    csv_str = _rows_to_csv(rows, cols)
    return Response(content=csv_str, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=searches.csv"})


@app.get("/admin/export/survey/{survey_id}")
async def admin_export_survey(survey_id: int, _=Depends(require_admin)):
    with conn_ctx() as conn:
        rows = get_survey_responses(conn, survey_id)
    csv_str = _rows_to_csv(rows, ["response_id", "survey_id", "user_mongo_id", "answers", "created_at"])
    return Response(content=csv_str, media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=survey_{survey_id}.csv"})


# ============================
# 프론트엔드 정적 파일 서빙
# ============================
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
def serve_index():
    return FileResponse(
        FRONTEND_DIR / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


app.mount("/src", StaticFiles(directory=FRONTEND_DIR / "src"), name="static-src")

# 광고 이미지 업로드 디렉터리
UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

_ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


@app.post("/admin/ads/upload")
async def admin_upload_ad_image(file: UploadFile = File(...), _=Depends(require_admin)):
    """광고 배너 이미지 업로드 → URL 반환."""
    ext = Path(file.filename or "img.png").suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"허용되지 않는 파일 형식입니다. ({', '.join(_ALLOWED_IMAGE_EXT)})")
    contents = await file.read()
    if len(contents) > _MAX_IMAGE_SIZE:
        raise HTTPException(400, "파일 크기가 5MB를 초과합니다.")
    unique_name = f"{_uuid.uuid4().hex[:12]}{ext}"
    save_path = UPLOADS_DIR / unique_name
    save_path.write_bytes(contents)
    return {"ok": True, "url": f"/uploads/{unique_name}", "filename": unique_name}


# ============================
# 리버스 프록시 → Node.js Auth 서버
# (같은 도메인에서 쿠키 유지를 위해)
# ============================
AUTH_SERVER = os.environ.get("AUTH_SERVER_URL", "https://naverblog-auth.onrender.com")
_proxy_logger = logging.getLogger("naverblog.proxy")

_proxy_client: httpx.AsyncClient | None = None

async def _get_proxy_client() -> httpx.AsyncClient:
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = httpx.AsyncClient(base_url=AUTH_SERVER, timeout=60.0, follow_redirects=False)
    return _proxy_client

async def _proxy(request: Request, path: str) -> Response:
    client = await _get_proxy_client()
    url = f"/{path}"
    # 요청 헤더 전달 (host/content-length/transfer-encoding 제외)
    _skip_req = {"host", "content-length", "transfer-encoding"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _skip_req}
    # 프록시 → Node.js 간 압축 비활성화 (인코딩 깨짐 방지)
    headers["accept-encoding"] = "identity"
    # X-Forwarded 헤더 설정
    client_host = request.headers.get("host", "")
    headers["x-forwarded-host"] = client_host
    headers["x-forwarded-proto"] = "https"
    if request.client:
        headers["x-forwarded-for"] = request.client.host
    body = await request.body()

    # Render 무료 플랜 콜드 스타트 대응: 첫 요청 실패 시 재시도
    max_retries = 2
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body if body else None,
                params=dict(request.query_params),
            )
            _proxy_logger.info(f"[Proxy] {request.method} /{path} → {resp.status_code} (attempt {attempt})")
            break
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            last_error = e
            if attempt < max_retries:
                wait = 5 * (attempt + 1)
                _proxy_logger.warning(f"[Proxy] /{path} 연결 실패 (attempt {attempt}), {wait}초 후 재시도: {e}")
                await asyncio.sleep(wait)
            else:
                _proxy_logger.error(f"[Proxy] /{path} 최종 실패 ({max_retries + 1}회 시도): {e}")
                return Response(
                    content=f'{{"error":"인증 서버 연결 실패. 잠시 후 다시 시도해주세요.","detail":"{type(e).__name__}"}}'.encode(),
                    status_code=503,
                    headers={"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"},
                )

    # 응답 헤더 구성 (Set-Cookie 복수 전달)
    _skip_resp = {"content-encoding", "content-length", "transfer-encoding", "set-cookie"}
    resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _skip_resp}
    response = Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
    response.headers["Cache-Control"] = "no-store"
    for k, v in resp.headers.multi_items():
        if k.lower() == "set-cookie":
            response.headers.append("set-cookie", v)
    return response


@app.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_auth(request: Request, path: str):
    return await _proxy(request, f"auth/{path}")


@app.api_route("/user-api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_user_api(request: Request, path: str):
    return await _proxy(request, f"user-api/{path}")


# ============================
# 관리자 인증
# ============================

class AdminLoginRequest(BaseModel):
    password: str


@app.post("/admin/login")
async def admin_login(data: AdminLoginRequest):
    if not verify_password(data.password):
        raise HTTPException(401, "비밀번호가 틀렸습니다")
    token = create_token()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
        path="/",
    )
    return response


@app.post("/admin/logout")
async def admin_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("admin_token", path="/")
    return response


# ============================
# 광고 관리 (require_admin)
# ============================

@app.get("/admin/ads")
async def admin_list_ads(_=Depends(require_admin)):
    with conn_ctx() as conn:
        return db_list_ads(conn)


@app.post("/admin/ads")
async def admin_create_ad(request: Request, _=Depends(require_admin)):
    body = await request.json()
    data = _normalize_ad_body(body)
    with conn_ctx() as conn:
        ad_id = db_create_ad(conn, data)
        return {"ok": True, "ad_id": ad_id}


@app.put("/admin/ads/{ad_id}")
async def admin_update_ad(ad_id: int, request: Request, _=Depends(require_admin)):
    body = await request.json()
    data = _normalize_ad_body(body)
    with conn_ctx() as conn:
        db_update_ad(conn, ad_id, data)
        return {"ok": True}


@app.delete("/admin/ads/{ad_id}")
async def admin_delete_ad(ad_id: int, _=Depends(require_admin)):
    with conn_ctx() as conn:
        db_delete_ad(conn, ad_id)
        return {"ok": True}


@app.get("/admin/ads/stats")
async def admin_ad_stats(_=Depends(require_admin)):
    with conn_ctx() as conn:
        return db_get_ad_stats(conn)


@app.get("/admin/ads/{ad_id}/report")
async def admin_ad_report(ad_id: int, _=Depends(require_admin)):
    with conn_ctx() as conn:
        return db_get_ad_report(conn, ad_id)


# ============================
# 영역 관리 (require_admin)
# ============================

@app.get("/admin/ads/zones")
async def admin_list_zones(_=Depends(require_admin)):
    with conn_ctx() as conn:
        zones = db_list_zones(conn)
        month = date.today().strftime("%Y-%m")
        inventory = db_get_zone_inventory(conn, month)
        inv_map = {i["zone_id"]: i for i in inventory}
        for z in zones:
            inv = inv_map.get(z["zone_id"], {})
            z["booked_count"] = inv.get("booked_count", 0)
            z["available"] = inv.get("available", z.get("max_slots", 0))
            z["inventory_status"] = inv.get("status", "신청가능")
        return zones


@app.put("/admin/ads/zones/{zone_id}")
async def admin_update_zone(zone_id: int, request: Request, _=Depends(require_admin)):
    body = await request.json()
    with conn_ctx() as conn:
        db_update_zone(conn, zone_id, body)
        return {"ok": True}


# ============================
# 예약 관리 (require_admin)
# ============================

@app.get("/admin/ads/bookings")
async def admin_list_bookings(
    month: str = Query(""),
    zone_id: Optional[int] = Query(None),
    status: str = Query(""),
    _=Depends(require_admin),
):
    with conn_ctx() as conn:
        return db_list_bookings(
            conn,
            month=month or None,
            zone_id=zone_id,
            status=status or None,
        )


@app.post("/admin/ads/bookings")
async def admin_create_booking(request: Request, _=Depends(require_admin)):
    body = await request.json()
    with conn_ctx() as conn:
        try:
            bid = db_create_booking(
                conn,
                ad_id=body["ad_id"],
                zone_id=body["zone_id"],
                booking_month=body["booking_month"],
                price=body.get("price", 0),
                memo=body.get("memo", ""),
            )
            return {"ok": True, "booking_id": bid}
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.put("/admin/ads/bookings/{booking_id}")
async def admin_update_booking(booking_id: int, request: Request, _=Depends(require_admin)):
    body = await request.json()
    with conn_ctx() as conn:
        db_update_booking_status(conn, booking_id, body["status"])
        return {"ok": True}


@app.delete("/admin/ads/bookings/{booking_id}")
async def admin_delete_booking(booking_id: int, _=Depends(require_admin)):
    with conn_ctx() as conn:
        db_delete_booking(conn, booking_id)
        return {"ok": True}


# ============================
# 인벤토리 (공개, 셀프서비스 준비)
# ============================

@app.get("/ads/zones/inventory")
async def ads_zone_inventory(month: str = Query("")):
    m = month or date.today().strftime("%Y-%m")
    with conn_ctx() as conn:
        return db_get_zone_inventory(conn, m)


# ============================
# 성과 대시보드 (require_admin)
# ============================

@app.get("/admin/ads/dashboard")
async def admin_ads_dashboard(month: str = Query(""), _=Depends(require_admin)):
    m = month or date.today().strftime("%Y-%m")
    y, mo = int(m[:4]), int(m[5:7])
    start_date = f"{m}-01"
    if mo == 12:
        end_date = f"{y+1}-01-01"
    else:
        end_date = f"{y}-{mo+1:02d}-01"
    with conn_ctx() as conn:
        stats = db_get_ad_stats(conn)
        daily = db_get_daily_ad_stats(conn, start_date, end_date)
        zones = db_get_zone_performance(conn, m)
        ads = db_get_ad_performance(conn, m)
        # booking revenue for month
        rev = conn.execute(
            "SELECT COALESCE(SUM(price),0) as rev FROM ad_bookings WHERE booking_month=? AND status IN ('approved','active')",
            (m,),
        ).fetchone()["rev"]
        return {
            "kpi": {
                "activeAds": stats["activeCount"],
                "totalImpressions": stats["totalImpressions"],
                "totalClicks": stats["totalClicks"],
                "avgCtr": stats["avgCtr"],
                "monthlyRevenue": rev,
            },
            "daily": daily,
            "zones": zones,
            "ads": ads,
        }


@app.get("/admin/ads/{ad_id}/daily")
async def admin_ad_daily(
    ad_id: int,
    start: str = Query(""),
    end: str = Query(""),
    _=Depends(require_admin),
):
    s = start or (date.today() - timedelta(days=30)).isoformat()
    e = end or date.today().isoformat()
    with conn_ctx() as conn:
        rows = conn.execute(
            "SELECT event_date as date, impressions, clicks FROM ad_events WHERE ad_id=? AND event_date BETWEEN ? AND ? ORDER BY event_date",
            (ad_id, s, e),
        ).fetchall()
        return [dict(r) for r in rows]


def _normalize_ad_body(body: dict) -> dict:
    """프론트엔드 JSON → DB 함수 입력 형태 정규화."""
    data = {}
    # advertiser 중첩 → 플랫
    adv = body.get("advertiser", {})
    if adv:
        data["company"] = adv.get("company", "")
        data["contact_name"] = adv.get("name", "")
        data["contact_phone"] = adv.get("phone", "")
    # 직접 필드
    for key in ("name", "title", "description", "cta_text", "placement", "start_date", "end_date", "priority"):
        if key in body:
            data[key] = body[key]
    # camelCase → snake_case
    if "imageUrl" in body:
        data["image_url"] = body["imageUrl"]
    if "linkUrl" in body:
        data["link_url"] = body["linkUrl"]
    if "ctaText" in body:
        data["cta_text"] = body["ctaText"]
    if "type" in body:
        data["ad_type"] = body["type"]
    if "startDate" in body:
        data["start_date"] = body["startDate"]
    if "endDate" in body:
        data["end_date"] = body["endDate"]
    if "isActive" in body:
        data["is_active"] = body["isActive"]
    # 빈 날짜 문자열 제거 (create_ad 기본값 폴백 작동)
    for dk in ("start_date", "end_date"):
        if dk in data and not data[dk]:
            del data[dk]
    # targeting 중첩 → 플랫
    tgt = body.get("targeting", {})
    if tgt:
        data["biz_types"] = tgt.get("businessTypes", ["all"])
        data["regions"] = tgt.get("regions", [])
    # billing 중첩 → 플랫
    billing = body.get("billing", {})
    if billing:
        data["billing_model"] = billing.get("model", "monthly")
        data["billing_amount"] = billing.get("amount", 0)
    return data


# ============================
# 광고 매칭 — 방문자용 (인증 불필요)
# ============================

@app.get("/ads/match")
async def ads_match(
    placement: str = Query("search_top"),
    topic: str = Query(""),
    region: str = Query(""),
    keyword: str = Query(""),
):
    biz_type = keyword or topic or "all"
    with conn_ctx() as conn:
        ads = db_match_ads(conn, placement, biz_type, region)
        return ads


@app.post("/ads/impression/{ad_id}")
async def ads_impression(ad_id: int, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate(f"imp:{client_ip}"):
        raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
    with conn_ctx() as conn:
        db_record_impression(conn, ad_id)
        return {"ok": True}


@app.post("/ads/click/{ad_id}")
async def ads_click(ad_id: int, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate(f"clk:{client_ip}"):
        raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
    with conn_ctx() as conn:
        result = db_record_click(conn, ad_id)
        return result


# ============================
# 분석 대시보드 (require_admin)
# ============================

@app.get("/admin/analytics/today")
async def admin_analytics_today(_=Depends(require_admin)):
    with conn_ctx() as conn:
        stats = get_today_stats(conn)
        stats["hourlyViews"] = get_hourly_stats(conn)
        return stats


@app.get("/admin/analytics/range")
async def admin_analytics_range(days: int = Query(7), _=Depends(require_admin)):
    with conn_ctx() as conn:
        return get_range_stats(conn, days)


@app.get("/admin/analytics/popular")
async def admin_analytics_popular(days: int = Query(7), _=Depends(require_admin)):
    with conn_ctx() as conn:
        return get_popular_searches(conn, days)


@app.get("/admin/analytics/searches")
async def admin_analytics_searches(_=Depends(require_admin)):
    with conn_ctx() as conn:
        return get_recent_searches(conn)


@app.get("/admin/analytics/events")
async def admin_analytics_events(_=Depends(require_admin)):
    with conn_ctx() as conn:
        return get_recent_events(conn)


@app.get("/admin/analytics/users")
async def admin_analytics_users(_=Depends(require_admin)):
    with conn_ctx() as conn:
        return get_user_stats(conn)


# ============================
# 분석 수집 — 방문자용 (인증 불필요)
# ============================

@app.post("/api/track/pageview")
async def track_pageview(request: Request):
    try:
        body = await request.json()
        with conn_ctx() as conn:
            log_page_view(
                conn,
                session_id=body.get("session_id", "unknown"),
                section=body.get("section", "dashboard"),
                referrer=body.get("referrer"),
                user_agent=request.headers.get("user-agent"),
            )
    except Exception:
        pass
    return {"ok": True}


@app.post("/api/track/event")
async def track_event(request: Request):
    try:
        body = await request.json()
        with conn_ctx() as conn:
            log_event(
                conn,
                session_id=body.get("session_id", "unknown"),
                event_type=body.get("event_type", "unknown"),
                event_data=body.get("event_data"),
            )
    except Exception:
        pass
    return {"ok": True}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("backend.app:app", host="0.0.0.0", port=port, reload=True)
