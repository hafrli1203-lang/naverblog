# 네이버 블로그 체험단 모집 도구

네이버 블로그 검색 API를 활용하여 지역 기반 블로거를 분석하고, 체험단 모집 캠페인을 관리하는 풀스택 웹 애플리케이션.

- **배포 URL**: https://체험단모집.com (= `https://xn--6j1b00mxunnyck8p.com`)
- **Render URL**: https://naverblog.onrender.com
- **GitHub**: https://github.com/hafrli1203-lang/naverblog
- **DNS/CDN**: Cloudflare (무료 플랜) — DDoS 방어, CDN 캐싱, SSL

## 프로젝트 구조

```
C:\naverblog/
├── CLAUDE.md                    # 이 파일 (프로젝트 문서)
├── render.yaml                  # Render 배포 설정
├── backend/
│   ├── main.py                  # FastAPI 서버 (포트 8001)
│   ├── naver_api.py             # 네이버 API 연동 + 블로거 분석 엔진
│   ├── campaigns.json           # 캠페인 데이터 저장소 (자동 생성)
│   ├── requirements.txt         # Python 의존성
│   └── .env                     # 네이버 API 키 (NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)
└── frontend/
    ├── index.html               # SPA 메인 HTML (3페이지 구조)
    ├── src/
    │   ├── main.js              # 클라이언트 로직 (라우팅, SSE, CRUD, 차트)
    │   └── style.css            # HiveQ 스타일 라이트 테마 (사이드바 레이아웃)
    ├── package.json             # Vite 개발서버 설정
    └── package-lock.json
```

## 실행 방법

```bash
# 백엔드
cd backend
pip install -r requirements.txt
python main.py                    # http://localhost:8001

# 프론트엔드
브라우저에서 frontend/index.html 직접 열기
# 또는 Vite 개발서버:
cd frontend && npm install && npm run dev
```

## 아키텍처

### 백엔드 (Python FastAPI)

**`backend/naver_api.py`** — 핵심 분석 엔진

- `NaverBlogAnalyzer` 클래스
  - `__init__(region, category, store_name, address, progress_callback)`: 입력 필드/SSE 콜백 설정
  - `generate_keywords()`: 입력 필드 조합으로 검색 키워드 생성
  - `search_blog(query, display, start, sort)`: 네이버 블로그 검색 API 호출 (결과 캐싱)
  - `extract_blogger_id(link, bloggerlink)`: URL에서 블로거 고유 ID 추출
  - `analyze_bloggers(target_count)`: **2단계 파이프라인** 메인 함수
    - 1단계: 키워드 검색 → 블로거별 집계 + 키워드별 순위 수집 → 5항목 기본 점수
    - 필터링: 지역 입력 시, 지역 포함 키워드에 한 번도 매칭되지 않은 블로거 제외
    - 2단계: 1단계에서 수집한 키워드별 순위로 노출 점수 계산 (추가 API 호출 없음)
  - `_calculate_base_scores(data, total_keywords)`: 5가지 기본 점수 (각 15점)

**`backend/main.py`** — API 서버

- `POST /api/search`: 동기 검색 (폴백용)
- `GET /api/search/stream`: **SSE 스트리밍 검색** (메인)
  - 이벤트: `progress` (단계/진행률), `result` (최종 블로거 목록)
- 캠페인 CRUD:
  - `POST /api/campaigns`: 캠페인 생성
  - `GET /api/campaigns`: 전체 목록
  - `GET /api/campaigns/{id}`: 상세
  - `PUT /api/campaigns/{id}`: 수정 (이름/메모/상태/블로거목록)
  - `POST /api/campaigns/{id}/bloggers`: 블로거 추가
  - `DELETE /api/campaigns/{id}`: 삭제
- 데이터 저장: `campaigns.json` 파일 (JSON)

### 프론트엔드 (Vanilla JS SPA)

**`frontend/index.html`** — 사이드바 + 메인 콘텐츠 2단 레이아웃

- **레이아웃**: `<aside class="sidebar">` + `<div class="main-content">` 2단 구조
  - 사이드바: 로고 + SVG 아이콘 네비게이션 (대시보드/캠페인/설정)
  - 메인: 탑바 (동적 페이지 타이틀) + 콘텐츠 영역
- `#dashboard`: 검색 카드 (2x2 그리드 입력) + 진행바 + 결과 카드
- `#campaigns`: 캠페인 생성/목록/상세 (블로거 관리)
- `#settings`: 데이터 관리 (내보내기/초기화)

**`frontend/src/main.js`** — 클라이언트 로직

- SPA 라우팅: `hashchange` 이벤트 기반, `.nav-item` 셀렉터
- 동적 페이지 타이틀: `PAGE_TITLES` 맵으로 탑바 `<h1 class="page-title">` 업데이트
- SSE 검색: `EventSource`로 실시간 진행 표시, 실패 시 POST 폴백
- 블로거 카드: 6항목 점수바, 뱃지(지역활동/노출우수), 상세모달(레이더차트)
- 캠페인: 생성/조회/블로거추가/상태변경/메모 (자동저장)
- 캠페인 상세 진입 시 `campaignActionsEl` (버튼 부모 div) 숨김/표시 처리

**`frontend/src/style.css`** — HiveQ 스타일 디자인 시스템

- **색상 팔레트**: `--primary: #0057FF` 블루 계열, `--bg-color: #f5f6fa` 라이트 배경
- **사이드바**: 고정 좌측 240px, 흰색 배경, active 시 `--primary-light` 배경 + 파란색 텍스트
- **카드**: `border-radius: 8px`, `box-shadow: 0 2px 12px rgba(0,0,0,0.06)`
- **반응형**: 768px 이하에서 사이드바 숨김

## 점수 체계 (100점 만점, 6항목)

| 항목 | 최대 | 측정 기준 |
|------|------|-----------|
| `activity_frequency` | 15점 | 게시물 날짜 간격 평균 (짧을수록 높음) |
| `keyword_relevance` | 15점 | 7개 검색 키워드 중 등장 비율 |
| `blog_index` | 15점 | 평균 검색 순위 (낮을수록 높음) |
| `local_content` | 15점 | 지역명 포함 게시물 비율 (지역 입력 시 지역명만 매칭, 폴백 없음) |
| `recent_activity` | 15점 | 최신 게시물 날짜 (최근일수록 높음) |
| `exposure_score` | **25점** | 실제 검색 키워드별 노출 순위 (1~10위:3점, 11~20위:2점, 21~30위:1점, 25점 정규화) |

## 핵심 설계 결정

- **2단계 파이프라인**: 전체 블로거 기본 스코어링 → 1단계 검색 데이터 재활용으로 노출 점수 계산 (추가 API 호출 없음)
- **검색 캐싱**: 동일 키워드 결과를 딕셔너리에 캐싱 (중복 API 호출 방지)
- **블로그 URL**: API의 불안정한 `bloggerlink` 대신 `https://blog.naver.com/{id}` 직접 구성
- **SSE 스트리밍**: 분석이 수십 초 걸리므로 실시간 진행 표시 (별도 스레드 + asyncio Queue)
- **캠페인 저장**: 서버 JSON 파일 (`campaigns.json`) — DB 없이 영속성 확보
- **설정 저장**: 클라이언트 localStorage — 서버 부담 없음
- **UI 디자인**: HiveQ HR Dashboard 참고 — 좌측 사이드바 + 우측 메인 콘텐츠 2단 구조, 클린 미니멀 SaaS 스타일

## UI/UX 디자인 (HiveQ 스타일)

### 색상 팔레트
```css
:root {
  --bg-color: #f5f6fa;        /* 페이지 배경 */
  --card-bg: #ffffff;          /* 카드 배경 */
  --sidebar-bg: #ffffff;       /* 사이드바 배경 */
  --primary: #0057FF;          /* 메인 블루 */
  --primary-hover: #003ECB;    /* 호버 블루 */
  --primary-light: #f0f4ff;    /* 연한 블루 (active 배경) */
  --text-main: #191919;        /* 본문 텍스트 */
  --text-secondary: #595959;   /* 보조 텍스트 */
  --text-muted: #a4a4a4;       /* 흐린 텍스트 */
  --border: #e8e8e8;           /* 보더 */
  --success: #02CB00;          /* 성공 */
  --warning: #F97C00;          /* 경고 */
  --danger: #EB1000;           /* 위험 */
  --shadow: 0 2px 12px rgba(0, 0, 0, 0.06);  /* 카드 그림자 */
}
```

### 레이아웃 구조
```
┌──────────┬────────────────────────────┐
│          │  탑바 (페이지 타이틀)         │
│ 사이드바  │────────────────────────────│
│ (240px)  │                            │
│          │  콘텐츠 영역                 │
│ - 대시보드│  (검색 카드, 결과 카드 등)    │
│ - 캠페인  │                            │
│ - 설정    │                            │
└──────────┴────────────────────────────┘
```

### 디자인 참고
- **참고**: [HiveQ HR Dashboard (Dribbble)](https://dribbble.com/shots/27052023-HiveQ-HR-Project-Management-Admin-Dashboard)
- **톤**: 클린 미니멀, 엔터프라이즈 SaaS 대시보드

## 변경 이력

### HiveQ 스타일 UI/UX 리디자인 (2025-02)

**커밋 기록:**
1. `d38013d` — HiveQ 스타일 UI/UX 리디자인 (사이드바 레이아웃 + 블루 테마)
2. `f0d2689` — 설정 페이지 중복 타이틀 제거
3. `84836a6` — 캠페인 페이지 중복 타이틀 제거
4. `e11fc3d` — 이전 indigo 색상 잔존 제거 + 캠페인 상세 레이아웃 수정

**주요 변경 내용:**
- **레이아웃**: 상단 nav → 좌측 고정 사이드바 (240px) + 우측 메인 콘텐츠 2단 구조
- **색상**: `#6366f1` indigo → `#0057FF` 블루 계열로 전면 변경
- **카드 스타일**: 가벼운 그림자 + 8px border-radius + 흰색 배경
- **검색 폼**: hero 중앙 정렬 → 카드 기반 2x2 그리드 폼
- **JS 셀렉터**: `.nav-link` → `.nav-item`, `PAGE_TITLES` 맵 + 동적 탑바 타이틀 추가
- **버그 수정**: 설정/캠페인 페이지 중복 타이틀, JS 내 `#6366f1`/`#4f46e5` 잔존 색상, 캠페인 상세 진입 시 빈 page-actions div 마진 문제

### Cloudflare + 커스텀 도메인 적용 (2025-02)

**커밋 기록:**
1. `a3c5fd4` — Cloudflare + 커스텀 도메인(체험단모집.com) 적용

**작업 내용:**
- **도메인 구매**: 가비아에서 `체험단모집.com` (퓨니코드: `xn--6j1b00mxunnyck8p.com`)
- **Cloudflare 설정**: 무료 플랜, 네임서버 변경 (가비아 → Cloudflare)
- **DNS 레코드**: 기존 A 레코드(216.24.57.1) 삭제 → CNAME(`@`, `www`) → `naverblog.onrender.com` (Proxied)
- **SSL/TLS**: Full (strict) 설정
- **Bot Fight Mode**: ON
- **CORS 보안**: `allow_origins=["*"]` → 허용 도메인만 명시
- **보호 효과**: DDoS 방어, CDN 캐싱, 봇 차단, SSL 암호화

## 인프라 / 배포

### 배포 구조
```
사용자 → Cloudflare (DDoS 방어 + CDN + SSL)
       → Render (naverblog.onrender.com)
       → FastAPI 서버 (gunicorn + uvicorn)
```

### 도메인
- **도메인**: 체험단모집.com (한글 도메인)
- **퓨니코드**: `xn--6j1b00mxunnyck8p.com`
- **등록업체**: 가비아 (gabia.com)

### Cloudflare 설정 (무료 플랜)
- **네임서버**: `carl.ns.cloudflare.com`, `kate.ns.cloudflare.com` (가비아에서 변경)
- **DNS 레코드**:
  | 유형 | 이름 | 대상 | 프록시 |
  |------|------|------|--------|
  | CNAME | `@` (루트) | `naverblog.onrender.com` | Proxied (주황색 구름) |
  | CNAME | `www` | `naverblog.onrender.com` | Proxied (주황색 구름) |
- **SSL/TLS**: Full (strict)
- **Bot Fight Mode**: ON
- **Under Attack Mode**: OFF (공격 시에만 활성화)

### Render 설정
- **서비스 타입**: Web Service (Python)
- **빌드 커맨드**: `pip install -r backend/requirements.txt`
- **시작 커맨드**: `cd backend && gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`
- **환경변수**: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `PYTHONIOENCODING=utf-8`

### 보안
- **CORS**: 허용 도메인만 명시 (`체험단모집.com`, `naverblog.onrender.com`, `localhost`)
- **Cloudflare DDoS 방어**: 자동 활성화
- **CDN 캐싱**: 정적 파일 엣지 서버 캐싱
- **봇 차단**: Bot Fight Mode로 악성 봇 자동 차단

## 외부 의존성

- **백엔드**: FastAPI, uvicorn, gunicorn, requests, python-dotenv, pydantic, beautifulsoup4
- **프론트엔드**: Chart.js 4.4.7 (CDN), Vite 5 (개발서버/빌드용, 선택)
- **API**: 네이버 검색 API (블로그) — `.env`에 클라이언트 ID/시크릿 필요
- **인프라**: Render (호스팅), Cloudflare (DNS/CDN/DDoS), 가비아 (도메인)

## 개발 시 주의사항

- `.env` 파일에 네이버 API 키가 반드시 있어야 함
- `campaigns.json`은 서버 실행 중 자동 생성됨 (커밋 불필요)
- CORS는 배포 도메인 + localhost만 허용 (체험단모집.com, naverblog.onrender.com, localhost)
- `API_BASE`는 `window.location.origin`으로 동적 설정 — 로컬/배포 환경 자동 대응
- 네이버 API 일일 호출 제한 있음 (25,000회/일) — 캐싱으로 실사용은 문제없음
