import json
import os
import sys
import uuid
import asyncio
from datetime import datetime

# Windows cp949 콘솔에서 이모지 유니코드 출력 에러 방지
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(errors='replace')
    except Exception:
        pass
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
from naver_api import NaverBlogAnalyzer
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="네이버 블로그 체험단 모집 도구 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CAMPAIGNS_FILE = os.path.join(os.path.dirname(__file__), "campaigns.json")


# === 데이터 모델 ===

class SearchRequest(BaseModel):
    region: Optional[str] = ""
    category: Optional[str] = ""
    store_name: Optional[str] = ""
    address: Optional[str] = ""
    target_count: Optional[int] = 50


class RecentPost(BaseModel):
    title: str
    link: str
    date: str


class ScoreBreakdown(BaseModel):
    activity_frequency: int = 0
    keyword_relevance: int = 0
    blog_index: int = 0
    local_content: int = 0
    recent_activity: int = 0
    exposure_score: int = 0


class ExposureDetail(BaseModel):
    keyword: str
    rank: int
    points: int
    source: Optional[str] = "search"


class BloggerProfile(BaseModel):
    id: str
    name: str
    blog_url: str
    total_score: int
    score_breakdown: ScoreBreakdown
    recent_posts: List[RecentPost]
    post_count: int
    last_post_date: Optional[str] = None
    keywords: List[int]
    exposure_details: List[ExposureDetail] = []


class CampaignCreate(BaseModel):
    name: str
    region: str
    category: str
    memo: Optional[str] = ""


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    memo: Optional[str] = None
    status: Optional[str] = None
    bloggers: Optional[List[Dict]] = None


class CampaignBloggerAdd(BaseModel):
    blogger_id: str
    blogger_name: str
    blog_url: str
    total_score: int
    status: Optional[str] = "대기중"
    memo: Optional[str] = ""


# === 캠페인 파일 관리 ===

def load_campaigns() -> List[Dict]:
    if os.path.exists(CAMPAIGNS_FILE):
        with open(CAMPAIGNS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_campaigns(campaigns: List[Dict]):
    with open(CAMPAIGNS_FILE, "w", encoding="utf-8") as f:
        json.dump(campaigns, f, ensure_ascii=False, indent=2)


# === API 엔드포인트 ===

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.post("/api/search", response_model=List[BloggerProfile])
def search_bloggers(request: SearchRequest):
    region = (request.region or "").strip()
    category = (request.category or "").strip()
    store_name = (request.store_name or "").strip()
    address = (request.address or "").strip()

    print(f"검색 요청: 지역={region}, 카테고리={category}, 매장명={store_name}, 주소={address}, 목표={request.target_count}")

    if not any([region, category, store_name, address]):
        raise HTTPException(status_code=400, detail="지역, 카테고리, 매장명, 주소 중 하나 이상 입력해주세요.")

    analyzer = NaverBlogAnalyzer(
        region=region or None,
        category=category or None,
        store_name=store_name or None,
        address=address or None,
    )
    results = analyzer.analyze_bloggers(target_count=request.target_count)

    bloggers = []
    for r in results:
        bloggers.append(BloggerProfile(
            id=r["id"],
            name=r["name"],
            blog_url=r["blog_url"],
            total_score=r["total_score"],
            score_breakdown=ScoreBreakdown(**r["score_breakdown"]),
            recent_posts=[RecentPost(**p) for p in r["recent_posts"]],
            post_count=r["post_count"],
            last_post_date=r.get("last_post_date"),
            keywords=r["keywords"],
            exposure_details=[ExposureDetail(**d) for d in r.get("exposure_details", [])],
        ))

    return bloggers


@app.get("/api/search/stream")
async def search_bloggers_stream(
    region: str = Query(""),
    category: str = Query(""),
    store_name: str = Query(""),
    address: str = Query(""),
    target_count: int = Query(50),
):
    """SSE 스트리밍 검색 엔드포인트."""
    region = region.strip()
    category = category.strip()
    store_name = store_name.strip()
    address = address.strip()

    if not any([region, category, store_name, address]):
        raise HTTPException(status_code=400, detail="지역, 카테고리, 매장명, 주소 중 하나 이상 입력해주세요.")

    async def event_generator():
        progress_queue = asyncio.Queue()

        def progress_callback(data):
            progress_queue.put_nowait(data)

        async def run_analysis():
            analyzer = NaverBlogAnalyzer(region, category, progress_callback=progress_callback)
            return analyzer.analyze_bloggers(target_count=target_count)

        task = asyncio.get_event_loop().run_in_executor(None, lambda: _run_sync_analysis(region, category, store_name, address, target_count, progress_queue))

        while True:
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                yield f"event: progress\ndata: {json.dumps(progress, ensure_ascii=False)}\n\n"
                if progress.get("stage") == "done":
                    break
            except asyncio.TimeoutError:
                if task.done():
                    break
                yield f"event: progress\ndata: {json.dumps({'stage': 'waiting', 'current': 0, 'total': 0, 'message': '처리 중...'}, ensure_ascii=False)}\n\n"

        results = await task

        bloggers = []
        for r in results:
            bloggers.append({
                "id": r["id"],
                "name": r["name"],
                "blog_url": r["blog_url"],
                "total_score": r["total_score"],
                "score_breakdown": r["score_breakdown"],
                "recent_posts": r["recent_posts"],
                "post_count": r["post_count"],
                "last_post_date": r.get("last_post_date"),
                "keywords": r["keywords"],
                "exposure_details": r.get("exposure_details", []),
            })

        yield f"event: result\ndata: {json.dumps(bloggers, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _run_sync_analysis(region, category, store_name, address, target_count, queue):
    """동기 분석을 별도 스레드에서 실행."""
    def progress_callback(data):
        queue.put_nowait(data)

    analyzer = NaverBlogAnalyzer(
        region=region or None,
        category=category or None,
        store_name=store_name or None,
        address=address or None,
        progress_callback=progress_callback,
    )
    return analyzer.analyze_bloggers(target_count=target_count)


# === 캠페인 CRUD ===

@app.post("/api/campaigns")
def create_campaign(data: CampaignCreate):
    campaigns = load_campaigns()
    campaign = {
        "id": str(uuid.uuid4())[:8],
        "name": data.name,
        "region": data.region,
        "category": data.category,
        "memo": data.memo or "",
        "status": "진행중",
        "bloggers": [],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    campaigns.append(campaign)
    save_campaigns(campaigns)
    return campaign


@app.get("/api/campaigns")
def list_campaigns():
    return load_campaigns()


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: str):
    campaigns = load_campaigns()
    for c in campaigns:
        if c["id"] == campaign_id:
            return c
    raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")


@app.put("/api/campaigns/{campaign_id}")
def update_campaign(campaign_id: str, data: CampaignUpdate):
    campaigns = load_campaigns()
    for c in campaigns:
        if c["id"] == campaign_id:
            if data.name is not None:
                c["name"] = data.name
            if data.memo is not None:
                c["memo"] = data.memo
            if data.status is not None:
                c["status"] = data.status
            if data.bloggers is not None:
                c["bloggers"] = data.bloggers
            c["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_campaigns(campaigns)
            return c
    raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")


@app.post("/api/campaigns/{campaign_id}/bloggers")
def add_blogger_to_campaign(campaign_id: str, data: CampaignBloggerAdd):
    campaigns = load_campaigns()
    for c in campaigns:
        if c["id"] == campaign_id:
            # 중복 체크
            for b in c["bloggers"]:
                if b["blogger_id"] == data.blogger_id:
                    raise HTTPException(status_code=400, detail="이미 추가된 블로거입니다.")
            blogger_entry = {
                "blogger_id": data.blogger_id,
                "blogger_name": data.blogger_name,
                "blog_url": data.blog_url,
                "total_score": data.total_score,
                "status": data.status or "대기중",
                "memo": data.memo or "",
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            c["bloggers"].append(blogger_entry)
            c["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_campaigns(campaigns)
            return c
    raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")


@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str):
    campaigns = load_campaigns()
    new_campaigns = [c for c in campaigns if c["id"] != campaign_id]
    if len(new_campaigns) == len(campaigns):
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")
    save_campaigns(new_campaigns)
    return {"message": "캠페인이 삭제되었습니다."}


# Static file 서빙 (API 라우트 뒤에 마운트)
app.mount("/src", StaticFiles(directory=os.path.join(FRONTEND_DIR, "src")), name="static-src")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
