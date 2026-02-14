# 네이버 블로그 체험단 모집 도구 v2.0

네이버 블로그 검색 API를 활용하여 지역 기반 블로거를 분석하고, 체험단 모집 캠페인을 관리하는 풀스택 웹 애플리케이션.
**v2.0**: SQLite DB 기반 블로거 선별 시스템, Performance Score, A/B 키워드 추천, 가이드 자동 생성.

- **배포 URL**: https://체험단모집.com (= `https://xn--6j1b00mxunnyck8p.com`)
- **Render URL**: https://naverblog.onrender.com
- **GitHub**: https://github.com/hafrli1203-lang/naverblog
- **DNS/CDN**: Cloudflare (무료 플랜) — DDoS 방어, CDN 캐싱, SSL

## 프로젝트 구조

```
C:\naverblog/
├── CLAUDE.md                    # 이 파일 (프로젝트 문서)
├── .gitignore                   # Git 제외 파일
├── render.yaml                  # Render 배포 설정
├── backend/
│   ├── __init__.py              # 패키지 초기화
│   ├── main.py                  # 하위 호환 래퍼 (app.py로 위임)
│   ├── app.py                   # FastAPI 메인 서버 (DB 기반, 포트 8001)
│   ├── db.py                    # SQLite DB 스키마 + ORM 함수
│   ├── models.py                # 데이터 클래스 (BlogPostItem, CandidateBlogger 등)
│   ├── keywords.py              # 키워드 생성 (검색/노출/A/B 세트)
│   ├── scoring.py               # 스코어링 (base_score + performance_score)
│   ├── analyzer.py              # 3단계 분석 파이프라인 (병렬 API 호출)
│   ├── reporting.py             # Top20/Pool40 리포팅 + 태그 생성
│   ├── naver_client.py          # 네이버 검색 API 클라이언트
│   ├── naver_api.py             # 레거시 분석 엔진 (참조용)
│   ├── guide_generator.py       # 업종별 체험단 가이드 자동 생성
│   ├── maintenance.py           # 데이터 보관 정책 (180일)
│   ├── sse.py                   # SSE 유틸리티
│   ├── test_scenarios.py        # DB/로직 테스트 (34 TC)
│   ├── requirements.txt         # Python 의존성
│   └── .env                     # 네이버 API 키
└── frontend/
    ├── index.html               # SPA 메인 HTML (Top20/Pool40 + 키워드 + 가이드)
    ├── src/
    │   ├── main.js              # 클라이언트 로직 (카드/리스트 뷰, A/B 키워드, 가이드 복사)
    │   └── style.css            # HiveQ 스타일 + 리스트 뷰 + 키워드/가이드 섹션
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

### 백엔드 (Python FastAPI + SQLite)

**`backend/app.py`** — 메인 API 서버 (DB 기반)

- `GET /api/search/stream`: **SSE 스트리밍 검색** (메인)
  - 이벤트: `progress` (단계/진행률), `result` (Top20/Pool40 + 메타)
- `POST /api/search`: 동기 검색 (폴백용)
- 캠페인 CRUD: `POST/GET/PUT/DELETE /api/campaigns`
- 매장 관리: `GET/DELETE /api/stores`
- `GET /api/stores/{id}/top`: Top20/Pool40 데이터
- `GET /api/stores/{id}/keywords`: A/B 키워드 추천
- `GET /api/stores/{id}/guide`: 체험단 가이드 자동 생성

**`backend/analyzer.py`** — 3단계 분석 파이프라인 (병렬 API 호출)

- `BloggerAnalyzer.analyze()`: 후보수집 → base score → 노출검증 → DB저장
  - 1단계: 카테고리 특화 seed 쿼리 (10개, **병렬 실행**)
  - 2단계: 카테고리 무관 확장 쿼리 (5개, **병렬 실행**)
  - 3단계: 노출 검증 (7개 키워드, API 호출 7회 고정, **병렬 실행** — 대부분 캐시 히트)
- `_search_batch()`: `ThreadPoolExecutor(max_workers=5)`로 복수 쿼리 병렬 실행, 캐시 히트 쿼리 스킵

**`backend/scoring.py`** — 점수 체계

- `base_score()`: 0~75점 (최근활동/SERP순위/지역정합/쿼리적합/활동빈도/place_fit/편향페널티)
- `performance_score()`: 0~100점 = (strength/35)*70 + (exposed/7)*30
- `calc_food_bias()`, `calc_sponsor_signal()`: 편향률 계산

**`backend/reporting.py`** — Top20/Pool40 리포팅

- `get_top20_and_pool40()`: Performance Score 내림차순 Top20 + 맛집쿼터 Pool40
- 태그 자동 부여: 맛집편향, 협찬성향, 노출안정

**`backend/keywords.py`** — 키워드 생성

- `build_seed_queries()`: 후보 수집용 10개
- `build_exposure_keywords()`: 노출 검증용 7개
- `build_keyword_ab_sets()`: A세트 (상위노출용 5개: 추천/후기/가격/인기/리뷰) + B세트 (실검색 패턴 5개: 방문후기/가성비/예약/메뉴/주차)

**`backend/guide_generator.py`** — 가이드 자동 생성

- 업종별 템플릿: 안경원, 카페, 미용실, 음식점, 기본값
- 리뷰 구조: 방문동기/핵심경험/정보정리/추천대상
- 사진 체크리스트, 키워드 배치 규칙, 해시태그 예시
- 공정위 필수 광고 표기 문구 + `#체험단`/`#협찬` 해시태그 안내 포함

**`backend/db.py`** — SQLite 데이터베이스

- 4개 테이블: stores, campaigns, bloggers, exposures
- 6개 인덱스 (WAL 모드, FK 활성화)
- 일별 유니크 팩트 저장 (UNIQUE INDEX on exposures)

**`backend/main.py`** — 하위 호환 래퍼 (`main:app` → `backend.app:app`)

### 프론트엔드 (Vanilla JS SPA)

**`frontend/index.html`** — 사이드바 + 메인 콘텐츠 2단 레이아웃

- **레이아웃**: `<aside class="sidebar">` + `<div class="main-content">` 2단 구조
- `#dashboard`: 검색 카드 + A/B 키워드 섹션 + 가이드 섹션 + Top20/Pool40 결과
- `#campaigns`: 캠페인 생성/목록/상세 (Top20/Pool40 블로거)
- `#settings`: 데이터 관리 (내보내기/초기화)

**`frontend/src/main.js`** — 클라이언트 로직

- SSE 검색: `EventSource`로 실시간 진행 → Top20/Pool40 렌더링
- **카드 뷰**: Performance Score 바, 배지 (강한추천/맛집편향/협찬성향/노출안정)
- **리스트 뷰**: `blogger_id | perf=XX | 1p=X/7 | best=N(키워드) | URL`
- **뷰 토글**: 카드 ↔ 리스트 전환 (Top20/Pool40 독립)
- **A/B 키워드**: `/api/stores/{id}/keywords` → 칩 형태로 표시
- **가이드**: `/api/stores/{id}/guide` → 프리포맷 텍스트 + 복사 버튼
- 캠페인: 생성/조회/삭제, 상세에서 Top20/Pool40 표시

**`frontend/src/style.css`** — HiveQ 스타일 디자인 시스템

- **색상 팔레트**: `--primary: #0057FF` 블루 계열, `--bg-color: #f5f6fa` 라이트 배경
- **새 컴포넌트**: 리스트 뷰, 뷰 토글, 키워드 칩, 가이드 섹션, Performance 바
- **새 배지**: `.badge-recommend`, `.badge-food`, `.badge-sponsor`, `.badge-stable`
- **반응형**: 768px 이하에서 사이드바 숨김, 키워드 그리드 1열

## 점수 체계

### Base Score (0~75점, 후보 수집 단계)

| 항목 | 최대 | 측정 기준 |
|------|------|-----------|
| 최근활동 | 15점 | 최신 게시물 날짜 (60일 기준) |
| 평균 SERP 순위 | 15점 | 검색 결과 평균 순위 (30위 기준) |
| 지역정합 | 15점 | 지역/주소 포함 비율 |
| 쿼리적합 | 10점 | 등장한 쿼리 수 비율 |
| 활동빈도 | 10점 | 게시물 수 기반 |
| place_fit | 10점 | 주소 토큰 등장 비율 |
| food_bias 페널티 | -10점 | 맛집 편향 75%↑:-10, 60%↑:-6, 50%↑:-3 |

### Strength Points (노출 검증 단계)

| 순위 | 포인트 |
|------|--------|
| 1~3위 | 5점 |
| 4~10위 | 3점 |
| 11~20위 | 2점 |
| 21~30위 | 1점 |

### Performance Score (0~100점, 최종 순위)

```
Performance Score = (strength_sum / 35) * 70 + (exposed_keywords / 7) * 30
```

### Top20/Pool40 태그

- **맛집편향**: food_bias_rate >= 60%
- **협찬성향**: sponsor_signal_rate >= 40%
- **노출안정**: 7개 키워드 중 4개 이상 노출

## 핵심 설계 결정

- **2단계 파이프라인**: 전체 블로거 기본 스코어링 → 1단계 검색 데이터 재활용으로 노출 점수 계산 (추가 API 호출 없음)
- **API 호출 병렬화**: `ThreadPoolExecutor(max_workers=5)`로 Phase별 쿼리 병렬 실행 (~6.5s → ~1.6s, 약 4배 개선). 캐시에 있는 쿼리는 스킵하고 미캐시 쿼리만 병렬 호출. Phase 간 순서는 유지 (1+2 → 3 → 4 → 5)
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

## 변경 이력 (시간순)

### 1. 프로젝트 초기 생성 + 딥 스캔 분석 기능 (2026-02-13)

**커밋:** `7cdd876` — feat: 상위노출 딥 스캔 분석 기능 추가

**최초 커밋으로 전체 프로젝트 생성 (3,931줄):**
- FastAPI 백엔드 (`main.py`, `naver_api.py`) — 네이버 블로그 검색 API 연동
- Vanilla JS SPA 프론트엔드 (`index.html`, `main.js`, `style.css`)
- 2단계 분석 파이프라인: 키워드 검색 → 기본 스코어링 → 노출 점수 계산
- SSE 스트리밍 검색 (실시간 진행 표시)
- 캠페인 CRUD (JSON 파일 저장)
- **딥 스캔 분석**: 상위 20명 블로거에 대해 게시물 제목에서 키워드 마이닝 → 추가 노출 순위 체크
  - `_mine_relevant_keywords()`: 게시물 제목에서 복합 키워드 생성 (최대 5개)
  - `_check_exposure_rank()`: 마이닝 키워드별 노출 순위 체크
  - `exposure_details`에 `source` 필드 추가 (`search`/`mined` 구분)
- Windows cp949 콘솔 UnicodeEncodeError 방지

### 2. gitignore 정리 (2026-02-13)

**커밋:** `baa2c4b` — chore: 미사용 파일 gitignore에 추가

- 미사용 백엔드 모듈 13개 gitignore 등록 (`analyzer.py`, `db.py`, `models.py` 등)
- `campaigns.json`, `blogger_db.sqlite` 자동생성 파일 제외
- 스크린샷 (`*.png`), OS 파일 (`.DS_Store`, `Thumbs.db`) 제외

### 3. Render 클라우드 배포 설정 (2026-02-13)

**커밋:** `f266934` — feat: Render 클라우드 배포 설정

- FastAPI에서 프론트엔드 static file 직접 서빙 (`app.mount`, `FileResponse`)
- `API_BASE`를 `window.location.origin`으로 동적 설정 (로컬/배포 자동 대응)
- gunicorn 추가, `PORT` 환경변수 지원
- `render.yaml` 배포 설정 파일 추가

### 4. 다크 → 화이트 테마 전환 (2026-02-13)

**커밋:** `6a1fc17` — style: 다크 테마에서 화이트 톤으로 변경

- 다크 배경 → 밝은 `#f5f6fa` 배경으로 전면 전환
- CSS 변수 및 JS 내 하드코딩 색상 일괄 수정

### 5. HiveQ 스타일 UI/UX 리디자인 (2026-02-13)

**커밋 기록:**
1. `d38013d` — HiveQ 스타일 UI/UX 리디자인 (사이드바 레이아웃 + 블루 테마)
2. `f0d2689` — 설정 페이지 중복 타이틀 제거
3. `84836a6` — 캠페인 페이지 중복 타이틀 제거
4. `e11fc3d` — 이전 indigo 색상 잔존 제거 + 캠페인 상세 레이아웃 수정
5. `6550d67` — docs: HiveQ UI/UX 리디자인 작업 전체 문서화

**주요 변경 내용:**
- **레이아웃**: 상단 nav → 좌측 고정 사이드바 (240px) + 우측 메인 콘텐츠 2단 구조
- **색상**: `#6366f1` indigo → `#0057FF` 블루 계열로 전면 변경
- **카드 스타일**: 가벼운 그림자 + 8px border-radius + 흰색 배경
- **검색 폼**: hero 중앙 정렬 → 카드 기반 2x2 그리드 폼
- **JS 셀렉터**: `.nav-link` → `.nav-item`, `PAGE_TITLES` 맵 + 동적 탑바 타이틀 추가
- **버그 수정**: 설정/캠페인 페이지 중복 타이틀, JS 내 `#6366f1`/`#4f46e5` 잔존 색상, 캠페인 상세 진입 시 빈 page-actions div 마진 문제

### 6. Cloudflare + 커스텀 도메인 적용 (2026-02-13)

**커밋 기록:**
1. `a3c5fd4` — security: Cloudflare + 커스텀 도메인(체험단모집.com) 적용
2. `55e6702` — docs: Cloudflare 인프라 설정 및 보안 구성 전체 문서화

**작업 내용:**
- **도메인 구매**: 가비아에서 `체험단모집.com` (퓨니코드: `xn--6j1b00mxunnyck8p.com`)
- **Cloudflare 설정**: 무료 플랜, 네임서버 변경 (가비아 → Cloudflare)
- **DNS 레코드**: 기존 A 레코드(216.24.57.1) 삭제 → CNAME(`@`, `www`) → `naverblog.onrender.com` (Proxied)
- **SSL/TLS**: Full (strict) 설정
- **Bot Fight Mode**: ON
- **CORS 보안**: `allow_origins=["*"]` → 허용 도메인만 명시
- **보호 효과**: DDoS 방어, CDN 캐싱, 봇 차단, SSL 암호화

### 7. 블로거 선별 시스템 v2.0 전환 (2026-02-14)

**커밋:** `6d2064c` — feat: 블로거 선별 시스템 v2.0 전환 (SQLite DB + Performance Score)

- SQLite DB 기반 블로거/매장/캠페인/노출 데이터 관리 (4테이블, 6인덱스)
- Performance Score 도입 (0~100점 = strength 70% + exposure breadth 30%)
- 3단계 분석 파이프라인: seed(10) → broad(5) → exposure(7)
- Top20/Pool40 리포팅 + 태그 (맛집편향/협찬성향/노출안정)
- A/B 키워드 추천, 업종별 가이드 자동 생성
- 테스트 시나리오 34 TC

### 8. 검색 속도 최적화: API 호출 병렬화 (2026-02-14)

**커밋:** `2fb64cc` — perf: API 호출 병렬화로 검색 속도 ~4x 개선 (ThreadPoolExecutor)

**수정 파일:** `backend/analyzer.py` (1개)

**변경 내용:**
- `_search_batch()` 메서드 추가: `ThreadPoolExecutor(max_workers=5)`로 복수 쿼리 병렬 실행
  - 캐시에 있는 쿼리는 API 호출 스킵, 미캐시 쿼리만 병렬 호출
  - 스레드 안전: 각 쿼리가 고유 캐시 키를 가지므로 경합 없음
- `collect_candidates()`: 10개 seed 쿼리 순차 → 병렬 배치 실행
- `collect_broad_candidates()`: 5개 broad 쿼리 순차 → 병렬 배치 실행
- `exposure_mapping()`: 7개 exposure 쿼리 순차 → 병렬 배치 실행
- Progress 보고: 쿼리별 → Phase 단위 "시작/완료" emit으로 변경

**성능 개선:**
| Phase | Before | After (5 workers) |
|-------|--------|-------------------|
| Seed (10 queries) | ~4s | ~0.8s (2 rounds) |
| Broad (5 queries) | ~2s | ~0.4s (1 round) |
| Exposure (7 queries, 6 cached) | ~0.4s | ~0.4s (변동 없음) |
| **총 API 시간** | **~6.5s** | **~1.6s** (4x 개선) |

### 9. 검색 결과 meta 병합 버그 수정 (2026-02-14)

**커밋:** `8e61d7c` — fix: 검색 결과 meta 병합 오류 수정 (store_id 누락 → 키워드/가이드 미표시)

**수정 파일:** `backend/app.py` (1개)

**원인:**
- `_sync_analyze()`에서 `{"meta": {..., "store_id": store_id}, **result}` 형태로 반환
- `get_top20_and_pool40()`의 `result`에도 `"meta"` 키가 있어서 `**result` spread 시 덮어씀
- `store_id`, `campaign_id` 등이 사라져 프론트엔드에서 키워드/가이드 API 호출이 불가

**수정:**
- `result.pop("meta", {})`로 꺼낸 뒤 `merged_meta.update()`로 병합
- 모든 키(`store_id`, `campaign_id`, `seed_calls`, `days`, `total_keywords` 등)가 보존됨

### 10. 키워드 B세트 개선 + 가이드 광고표기 의무 추가 (2026-02-14)

**커밋:** `f63e35d` — fix: 키워드 B세트 비현실 키워드 교체 + 가이드 광고표기 의무 추가

**수정 파일:** `backend/keywords.py`, `backend/guide_generator.py` (2개)

**키워드 B세트 개선 (`keywords.py`):**
- 제거: `영업시간`, `가격표`, `전화번호` (실제 사용자가 검색하지 않는 인위적 조합)
- 추가: `방문후기`, `가성비`, `모임`, `신상` (실제 블로그 검색 패턴)
- 유지: `예약`, `메뉴`, `주차` (실질적 유입 키워드)

**가이드 광고표기 의무 추가 (`guide_generator.py`):**
- 공정거래위원회 규정에 따른 필수 문구 안내: "업체로부터 제품/서비스를 제공받아 작성한 솔직한 리뷰입니다."
- `#체험단` 또는 `#협찬` 해시태그 필수 포함 안내
- 장점뿐 아니라 아쉬운 점도 자연스럽게 포함하도록 유도 (신뢰도 향상)
- 본문 권장 글자수: 1,500자 이상 → 1,000~2,500자 범위로 조정 (SEO 최적 범위)

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
- API 병렬 호출 `max_workers=5` — 네이버 API rate limit 방지를 위한 보수적 설정, 무분별하게 올리지 말 것
