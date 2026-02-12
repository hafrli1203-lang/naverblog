# 네이버 블로그 체험단 모집 도구

네이버 블로그 검색 API를 활용하여 지역 기반 블로거를 분석하고, 체험단 모집 캠페인을 관리하는 풀스택 웹 애플리케이션.

## 프로젝트 구조

```
C:\naverblog/
├── CLAUDE.md                    # 이 파일 (프로젝트 문서)
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
    │   └── style.css            # 다크 테마 스타일
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

**`frontend/index.html`** — 3페이지 SPA 구조

- `#dashboard`: 검색 + 진행바 + 결과 카드 + 필터/정렬
- `#campaigns`: 캠페인 생성/목록/상세(블로거 관리)
- `#settings`: 검색설정, 점수 가중치 슬라이더, 데이터 관리

**`frontend/src/main.js`** — 클라이언트 로직

- SPA 라우팅: `hashchange` 이벤트 기반
- SSE 검색: `EventSource`로 실시간 진행 표시, 실패 시 POST 폴백
- 블로거 카드: 6항목 점수바, 뱃지(지역활동/노출우수), 상세모달(레이더차트)
- 캠페인: 생성/조회/블로거추가/상태변경/메모 (자동저장)
- 설정: localStorage 저장, 가중치 슬라이더, JSON 내보내기/초기화

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

## 외부 의존성

- **백엔드**: FastAPI, uvicorn, requests, python-dotenv, pydantic, beautifulsoup4
- **프론트엔드**: Chart.js 4.4.7 (CDN), Vite 5 (개발서버/빌드용, 선택)
- **API**: 네이버 검색 API (블로그) — `.env`에 클라이언트 ID/시크릿 필요

## 개발 시 주의사항

- `.env` 파일에 네이버 API 키가 반드시 있어야 함
- `campaigns.json`은 서버 실행 중 자동 생성됨 (커밋 불필요)
- CORS는 전체 허용 (`allow_origins=["*"]`) — 프로덕션에서는 제한 필요
- 프론트엔드는 `http://localhost:8001`을 하드코딩 — 서버 포트 변경 시 `main.js`의 `API_BASE` 수정
- 네이버 API 일일 호출 제한 있음 (25,000회/일) — 캐싱으로 실사용은 문제없음
