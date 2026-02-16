from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# .env 로드
load_dotenv(Path(__file__).parent / ".env")

from backend.db import conn_ctx, init_db, upsert_store, create_campaign, insert_blog_analysis
from backend.keywords import StoreProfile, build_exposure_keywords, build_keyword_ab_sets, TOPIC_FOOD_SET, TOPIC_TEMPLATE_HINT
from backend.naver_client import get_env_client
from backend.analyzer import BloggerAnalyzer
from backend.maintenance import cleanup_exposures
from backend.reporting import get_top20_and_pool40
from backend.guide_generator import generate_guide
from backend.blog_analyzer import analyze_blog, extract_blogger_id


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
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    with conn_ctx() as conn:
        init_db(conn)


# ============================
# SSE 스트리밍 분석 (GET - EventSource 호환)
# ============================
@app.get("/api/search/stream")
async def search_stream(
    region: str = Query(...),
    category: str = Query(""),
    topic: str = Query(""),
    keyword: str = Query(""),
    place_url: Optional[str] = Query(None),
    store_name: Optional[str] = Query(None),
    address_text: Optional[str] = Query(None),
    memo: Optional[str] = Query(None),
):
    """프론트엔드 EventSource 호환 GET SSE 엔드포인트"""
    region = (region or "").strip()
    # keyword > legacy category > "" (하위 호환)
    effective_category = (keyword or category or "").strip()
    topic_val = (topic or "").strip()
    if not region:
        raise HTTPException(status_code=400, detail="지역을 입력해주세요.")

    queue: asyncio.Queue[dict] = asyncio.Queue()

    def progress_cb(msg: dict):
        queue.put_nowait(msg)

    task = asyncio.get_event_loop().run_in_executor(
        None, _sync_analyze, region, effective_category, topic_val, place_url, store_name, address_text, memo, progress_cb
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


def _sync_analyze(region_text, category_text, topic_val, place_url, store_name, address_text, memo, progress_cb):
    import logging
    logger = logging.getLogger("naverblog.search")
    logger.info(
        "[검색 파라미터] region=%r, category_text=%r, topic=%r, store_name=%r",
        region_text, category_text, topic_val, store_name,
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

        client = get_env_client()
        analyzer = BloggerAnalyzer(client=client, profile=profile, store_id=store_id, progress_cb=progress_cb)
        seed_calls, exposure_calls, keywords = analyzer.analyze(conn, top_n=50)

        cleanup_exposures(conn, keep_days=180)

        result = get_top20_and_pool40(conn, store_id=store_id, days=30,
                                       category_text=effective_cat_for_food)

        progress_cb({"stage": "done", "current": 1, "total": 1, "message": "분석 완료 (GoldenScore v7.1)"})

        # result["meta"]와 병합 (result의 meta가 덮어쓰지 않도록)
        merged_meta = {
            "store_id": store_id,
            "campaign_id": campaign_id,
            "seed_calls": seed_calls,
            "exposure_calls": exposure_calls,
            "exposure_keywords": keywords,
        }
        merged_meta.update(result.pop("meta", {}))

        return {
            "meta": merged_meta,
            **result,
        }


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
):
    region = (region or "").strip()
    effective_category = (keyword or category or "").strip()
    topic_val = (topic or "").strip()
    if not region:
        raise HTTPException(400, "지역을 입력해주세요.")

    result = _sync_analyze(region, effective_category, topic_val, place_url, store_name, address_text, None, lambda _: None)
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
def get_store_guide(store_id: int):
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
        sub_keywords = None
        if top_kw_rows:
            main_keyword_override = top_kw_rows[0]["keyword"]
            if len(top_kw_rows) > 1:
                sub_keywords = [r["keyword"] for r in top_kw_rows[1:3]]

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
            sub_keywords=sub_keywords,
        )
        return guide


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
    blog_url: str = Query(...),
    store_id: Optional[int] = Query(None),
):
    """블로그 개별 분석 — SSE 스트리밍"""
    blog_url_val = (blog_url or "").strip()
    if not blog_url_val:
        raise HTTPException(400, "블로그 URL 또는 ID를 입력해주세요.")

    bid = extract_blogger_id(blog_url_val)
    if not bid:
        raise HTTPException(400, "유효하지 않은 블로그 URL/ID입니다.")

    queue: asyncio.Queue[dict] = asyncio.Queue()

    def progress_cb(msg: dict):
        queue.put_nowait(msg)

    task = asyncio.get_event_loop().run_in_executor(
        None, _sync_blog_analysis, blog_url_val, store_id, progress_cb
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


def _sync_blog_analysis(blog_url_val: str, store_id: Optional[int], progress_cb):
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

    progress_cb({"stage": "done", "current": 1, "total": 1, "message": "분석 완료"})
    return result


class BlogAnalysisRequest(BaseModel):
    blog_url: str
    store_id: Optional[int] = None


@app.post("/api/blog-analysis")
def blog_analysis_sync(data: BlogAnalysisRequest):
    """블로그 개별 분석 — 동기 폴백"""
    result = _sync_blog_analysis(data.blog_url.strip(), data.store_id, lambda _: None)
    return result


# ============================
# 프론트엔드 정적 파일 서빙
# ============================
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/src", StaticFiles(directory=FRONTEND_DIR / "src"), name="static-src")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("backend.app:app", host="0.0.0.0", port=port, reload=True)
