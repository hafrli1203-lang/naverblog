# 네이버 블로그 체험단 모집 도구 v2.0

네이버 블로그 검색 API를 활용하여 지역 기반 블로거를 분석하고, 체험단 모집 캠페인을 관리하는 풀스택 웹 애플리케이션.
**v2.0**: SQLite DB 기반 블로거 선별 시스템, GoldenScore 4축 통합 랭킹, A/B 키워드 추천, 업종별 가이드 자동 생성(10개 템플릿), 블로그 개별 분석(BlogScore 5축 + 협찬글 상위노출 예측 + 콘텐츠 품질 검사).

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
│   ├── models.py                # 데이터 클래스 (BlogPostItem, CandidateBlogger, BlogScoreResult, QualityMetrics 등)
│   ├── keywords.py              # 키워드 생성 (검색/노출/A/B 세트)
│   ├── scoring.py               # 스코어링 (base_score + GoldenScore v2.2 4축 통합)
│   ├── analyzer.py              # 4단계 분석 파이프라인 (병렬 API 호출)
│   ├── blog_analyzer.py         # 블로그 개별 분석 엔진 (RSS + BlogScore 5축 + 협찬글 노출 감지 + 품질 검사)
│   ├── reporting.py             # Top20/Pool40 리포팅 + 태그 생성
│   ├── naver_client.py          # 네이버 검색 API 클라이언트
│   ├── naver_api.py             # 레거시 분석 엔진 (참조용)
│   ├── guide_generator.py       # 업종별 체험단 가이드 자동 생성
│   ├── maintenance.py           # 데이터 보관 정책 (180일)
│   ├── sse.py                   # SSE 유틸리티
│   ├── test_scenarios.py        # DB/로직 테스트 (84 TC)
│   ├── requirements.txt         # Python 의존성
│   └── .env                     # 네이버 API 키
└── frontend/
    ├── index.html               # SPA 메인 HTML (Top20/Pool40 + 키워드 + 가이드 + 메시지 템플릿 + 블로그 분석)
    ├── src/
    │   ├── main.js              # 클라이언트 로직 (카드/리스트 뷰, A/B 키워드, 가이드, 쪽지/메일, 템플릿, 블로그 분석)
    │   └── style.css            # HiveQ 스타일 + 리스트 뷰 + 키워드/가이드/쪽지/메일/템플릿/블로그 분석
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

- `GET /api/search/stream`: **SSE 스트리밍 검색** (메인) — `region` 필수, `category` 선택 (빈값 허용 = 지역만 검색)
  - 이벤트: `progress` (단계/진행률), `result` (Top20/Pool40 + 메타)
- `POST /api/search`: 동기 검색 (폴백용) — 동일 파라미터
- 캠페인 CRUD: `POST/GET/PUT/DELETE /api/campaigns`
- 매장 관리: `GET/DELETE /api/stores`
- `GET /api/stores/{id}/top`: Top20/Pool40 데이터
- `GET /api/stores/{id}/keywords`: A/B 키워드 추천
- `GET /api/stores/{id}/guide`: 체험단 가이드 자동 생성
- `GET /api/stores/{id}/message-template`: 체험단 모집 쪽지 템플릿
- `GET /api/blog-analysis/stream`: **SSE 블로그 개별 분석** (BlogScore 5축)
  - 이벤트: `progress` (RSS/콘텐츠/노출/품질/스코어링), `result` (BlogScoreResult)
- `POST /api/blog-analysis`: 동기 블로그 분석 (폴백용)

**`backend/blog_analyzer.py`** — 블로그 개별 분석 엔진 (RSS + BlogScore 5축 + 협찬글 노출 감지 + 품질 검사)

- `extract_blogger_id()`: URL/ID 파싱 (blogId= 쿼리 파라미터 우선, blog.naver.com/{id} 경로, 순수 ID)
- `fetch_rss()`: `https://rss.blog.naver.com/{id}.xml` → `RSSPost` 리스트 (API 쿼터 미사용)
- `extract_search_keywords_from_posts()`: 포스트 제목에서 2글자+ 한글 키워드 + 바이그램 자동 추출
- `analyze_activity()`: 활동 지표 (0~15점) — 최근활동(5)/포스팅빈도(5)/일관성(2.5)/포스트수량(2.5) + 활동 트렌드
- `analyze_content()`: 콘텐츠 성향 (0~20점) — 주제다양성(8)/콘텐츠충실도(6)/카테고리적합도(6) + food_bias/sponsor_rate
- `analyze_exposure()`: 검색 노출력 (0~40점) — 노출강도합계(20)/키워드커버리지(10)/**협찬글노출보너스(10)** (ThreadPoolExecutor 병렬 검색)
  - `_has_sponsored_signal()`: 포스트 제목에서 `_SPONSORED_TITLE_SIGNALS` 매칭 (체험단/협찬/제공/초대/서포터즈 등)
  - `sponsored_rank_count`: 협찬 시그널 있는 노출 포스트 수
  - `sponsored_page1_count`: 그 중 1페이지(10위 이내) — **핵심: 협찬 글이 상위노출되는 블로거 우대**
- `analyze_suitability()`: 체험단 적합도 (0~10점) — 협찬수용성(5, 10~30% sweet spot)/업종적합도(5)
- `analyze_quality()`: 콘텐츠 품질 (0~15점, HGI 차용) — 독창성(5, `difflib.SequenceMatcher`)/규정준수(5, 금지어+공정위표시)/충실도(5, description 길이)
  - `_SPONSORED_TITLE_SIGNALS`: 10개 협찬 감지 키워드 (체험단/협찬/제공/초대/서포터즈/원고료/제공받/광고/소정의/무료체험)
  - `_FORBIDDEN_WORDS`: 12개 금지어 (최고/최저/100%/완치/보장/무조건/확실/1등/가장/완벽/기적/특효)
  - `_DISCLOSURE_PATTERNS`: 8개 공정위 표시 패턴 (제공받아/소정의 원고료/업체로부터 등)
- `compute_grade()`: S(85+)/A(70+)/B(50+)/C(30+)/D(<30) 등급 판정
- `generate_insights()`: 강점/약점/추천문 자동 생성 — 품질/협찬글 노출 관련 인사이트 포함
- `analyze_blog()`: 전체 오케스트레이션 (ID추출 → RSS → 콘텐츠 → 노출 → **품질** → 적합도 → 등급 → 인사이트, SSE 5단계)
- **독립 분석**: 포스트 제목에서 키워드 자동 추출 (5~7개)
- **매장 연계 분석**: `build_exposure_keywords()` 활용 (10개, 캐시 7 + 홀드아웃 3)
- **RSS 비활성 대응**: 노출력만 부분 계산 + "RSS 비활성" 안내

**`backend/analyzer.py`** — 4단계 분석 파이프라인 (병렬 API 호출)

- `BloggerAnalyzer.analyze()`: 후보수집 → 지역 랭커 수집 → 확장 수집 → 노출검증 → DB저장
  - 1단계: 카테고리 특화 seed 쿼리 (7개, **병렬 실행**)
  - 2단계: 지역 랭킹 파워 블로거 수집 (3개, **병렬 실행**) — 인기 카테고리 상위 10위
  - 3단계: 카테고리 무관 확장 쿼리 (5개, **병렬 실행**)
  - 4단계: 노출 검증 (10개 키워드: 캐시 7개 + 홀드아웃 3개, **병렬 실행**)
- `collect_region_power_candidates()`: 지역 인기 카테고리 검색에서 상위 10위 블로거만 수집 (블로그 지수 높은 사람)
- `detect_self_blog()`: 자체블로그/경쟁사 감지 (멀티시그널 점수 >= 4 → "self") + 브랜드 블로그 패턴 감지
- `FRANCHISE_NAMES`: ~50개 주요 프랜차이즈/체인 (안경/카페/음식/미용/헬스/학원/기타)
- `STORE_SUFFIXES`: 매장 접미사 패턴 (점/원/실/관/샵/스토어/몰/센터/클리닉/의원)
- `exposure_mapping()`: `(rank, post_link, post_title)` 튜플 반환 — 포스트 URL/제목 캡처
- `_search_batch()`: `ThreadPoolExecutor(max_workers=5)`로 복수 쿼리 병렬 실행, 캐시 히트 쿼리 스킵

**`backend/scoring.py`** — 점수 체계

- `base_score()`: 0~80점 (최근활동/SERP순위/지역정합/쿼리적합/활동빈도/place_fit/broad_bonus - food_penalty - sponsor_penalty)
- `golden_score()`: 0~100점 = (BlogPower(25) + Exposure(35) + CategoryFit(25) + Recruitability(15)) × ExposureConfidence — **메인 랭킹 함수**
- `keyword_weight_for_suffix()`: 핵심 키워드 1.5x, 추천 1.3x, 후기 1.2x, 가격 1.1x, 기타 1.0x
- `performance_score()`: 레거시 (하위 호환용)
- `is_food_category()`: 업종 카테고리 음식 여부 판별
- `calc_food_bias()`, `calc_sponsor_signal()`: 편향률 계산

**`backend/reporting.py`** — Top20/Pool40 리포팅

- `get_top20_and_pool40()`: GoldenScore 내림차순 Top20 + 동적 쿼터 Pool40
  - 음식 업종: 맛집 블로거 80% 허용, 비맛집 최소 10%
  - 비음식 업종: 맛집 블로거 30% 제한, 비맛집 최소 50% 우선
- 자체블로그/경쟁사 분리: `detect_self_blog()` → `competition` 리스트로 분리 (Top20/Pool40에서 제외)
- `weighted_strength`: `keyword_weight_for_suffix()` 적용한 가중 노출 강도
- `ExposurePotential` 태그: 매우높음/높음/보통/낮음 (상위노출 가능성 예측)
- 각 블로거에 `exposure_details` 배열 포함: `[{keyword, rank, strength_points, is_page1, post_link, post_title}]`
- 태그 자동 부여: 맛집편향, 협찬성향, 노출안정

**`backend/keywords.py`** — 키워드 생성 (카테고리 동의어 + 홀드아웃)

- `CATEGORY_SYNONYMS` + `resolve_category_key()`: ~40개 동의어 → 정규 카테고리 키 매핑
- `CATEGORY_HOLDOUT_MAP`: 업종별 홀드아웃 키워드 3개 (seed와 비중복 검증용)
- `CATEGORY_BROAD_MAP`: 업종별 확장 쿼리 5개 (카테고리 인접 키워드)
- `build_seed_queries()`: 후보 수집용 7개 (추천/후기/인기/가격/리뷰/방문후기) — 상호명/주소 토큰 쿼리 제거. **지역만 모드**: 카테고리 빈값 시 인기 카테고리 키워드(맛집/카페/핫플 등)로 광범위 수집
- `build_region_power_queries()`: 지역 랭킹 파워 블로거 탐색용 3개 — 자기 업종과 다른 인기 카테고리 (REGION_POWER_MAP)
- `build_exposure_keywords()`: 노출 검증용 10개 (캐시 7개 + 홀드아웃 3개 — 확인편향 방지). **지역만 모드**: 지역 인기 키워드 7개 + 홀드아웃 3개(맛집 후기/데이트/일상)
- `build_broad_queries()`: 확장 후보 수집용 5개 (동의어 해소 후 업종별 매핑)
- `build_keyword_ab_sets()`: A세트 (상위노출용 5개: 추천/후기/가격/인기/리뷰) + B세트 (범용 유입용 5개: 방문후기/가성비/예약/신상/전문). **지역만 모드**: 인기 키워드 기반 A/B

**`backend/guide_generator.py`** — 업종별 가이드 자동 생성 (10개 템플릿)

- 업종별 템플릿 10종: 안경원, 카페, 미용실, 음식점, 병원, 치과, 헬스장, 학원, 숙박, 자동차 + 기본값
- 리뷰 구조: 방문동기/핵심경험/정보정리/추천대상 + `word_count` 가이드 (200~800자)
- 사진 체크리스트, 키워드 배치 규칙, 해시태그 예시
- `forbidden_words` / `alternative_words`: 업종별 사용 금지 표현 + 대체어 (법규 준수)
- `seo_guide`: min_chars, max_chars, min_photos, keyword_density, subtitle_rule
- 병원/치과 전용 `disclaimer`: 의료법 면책 문구
- 공정위 필수 광고 표기 문구 + `#체험단`/`#협찬` 해시태그 안내 포함
- SEO: 네이버 지도 삽입 필수, 메인 키워드 반복 사용 규칙

**`backend/db.py`** — SQLite 데이터베이스

- 5개 테이블: stores, campaigns, bloggers, exposures, blog_analyses
- exposures 테이블: `post_link TEXT`, `post_title TEXT` 컬럼 포함 (마이그레이션 자동)
- blog_analyses 테이블: 블로그 개별 분석 이력 저장 (blogger_id, blog_url, analysis_mode, store_id, blog_score, grade, result_json)
- `insert_exposure_fact()`: `INSERT ... ON CONFLICT DO UPDATE` (재분석 시 포스트 링크 갱신)
- `insert_blog_analysis()`: 분석 결과 JSON 저장
- 7개 인덱스 (WAL 모드, FK 활성화)
- 일별 유니크 팩트 저장 (UNIQUE INDEX on exposures)

**`backend/naver_client.py`** — 네이버 검색 API 클라이언트 (재시도/백오프)

- `search_blog()`: 네이버 블로그 검색 API 호출 + 자동 재시도
- 재시도 대상: HTTP 429, 500, 502, 503, 504 + Timeout + ConnectionError
- 지수 백오프: max_retries=3, base_delay=1.0 (1s → 2s → 4s)
- 401/403 (인증 오류)는 즉시 raise (재시도 불가)

**`backend/main.py`** — 하위 호환 래퍼 (`main:app` → `backend.app:app`)

### 프론트엔드 (Vanilla JS SPA)

**`frontend/index.html`** — 사이드바 + 메인 콘텐츠 2단 레이아웃

- **레이아웃**: `<aside class="sidebar">` + `<div class="main-content">` 2단 구조
- `#dashboard`: 검색 카드 (지역 필수 + 네이버 주제 드롭다운 선택 + 키워드 선택 + 매장명 선택) + 블로그 개별 분석 카드 + A/B 키워드 섹션 + 가이드 섹션 + 메시지 템플릿 섹션 + Top20/Pool40 결과
- `#campaigns`: 캠페인 생성/목록/상세 (Top20/Pool40 블로거)
- `#settings`: 데이터 관리 (내보내기/초기화)

**`frontend/src/main.js`** — 클라이언트 로직

- SSE 검색: `EventSource`로 실시간 진행 → Top20/Pool40 렌더링
- **기본 뷰: 리스트** — `#순위 | 블로거ID | Golden Score | 배지 | 상세 | 블로그 | 쪽지 | 메일`
- **카드 뷰** (토글 전환): Golden Score 바 + 배지만 표시 (세부 점수 없음)
- **상세 모달**: 상세 보기 클릭 시에만 전체 점수 + 키워드별 노출 현황 + 포스트 링크 표시
- **뷰 토글**: 리스트(기본) ↔ 카드 전환 (Top20/Pool40 독립)
- **쪽지/메일**: 카드·리스트·모달에 쪽지(`note.naver.com`)/메일(`mail.naver.com` + 이메일 클립보드 복사) 버튼
- **A/B 키워드**: `/api/stores/{id}/keywords` → 칩 형태로 표시
- **가이드**: `/api/stores/{id}/guide` → 프리포맷 텍스트 + 복사 버튼
- **메시지 템플릿**: `/api/stores/{id}/message-template` → 체험단 모집 쪽지 템플릿 + 복사 버튼
- 캠페인: 생성/조회/삭제, 상세에서 Top20/Pool40 표시
- **블로그 개별 분석**: SSE 핸들러 + BlogScore 결과 렌더링 (등급 원형 배지, 5축 바, 강점/약점, 탭별 상세 + 품질 탭 + 협찬글 배지)
- **매장 셀렉터**: 분석 시 연계 매장 선택 드롭다운 (독립/매장연계 모드)

**`frontend/src/style.css`** — HiveQ 스타일 디자인 시스템

- **색상 팔레트**: `--primary: #0057FF` 블루 계열, `--bg-color: #f5f6fa` 라이트 배경
- **새 컴포넌트**: 리스트 뷰, 뷰 토글, 키워드 칩, 가이드 섹션, Golden Score 바, 메시지 템플릿 섹션
- **쪽지/메일 버튼**: `.msg-btn` (그린), `.mail-btn` (오렌지), `.modal-action-btn`
- **노출 상세**: `.card-exposure-details`, `.exposure-detail-row`, `.post-link`
- **토스트 알림**: `.copy-toast` (이메일 복사 알림)
- **새 배지**: `.badge-recommend`, `.badge-food`, `.badge-sponsor`, `.badge-stable`
- **블로그 분석**: `.ba-header-card`, `.ba-grade-box`, `.ba-grade` (원형 등급 배지), `.ba-bar-row`/`.ba-bar-fill` (5축 바), `.ba-insights-grid`, `.ba-recommendation`, `.ba-tabs`/`.ba-tab-content` (탭 상세: 활동/콘텐츠/노출/품질)
- **반응형**: 768px 이하에서 사이드바 숨김, 키워드 그리드 1열, 블로그 분석 레이아웃 세로 전환

## 점수 체계

### Base Score (0~80점, 후보 수집 단계)

| 항목 | 최대 | 측정 기준 |
|------|------|-----------|
| 최근활동 | 15점 | 최신 게시물 날짜 (60일 기준) |
| 평균 SERP 순위 | 15점 | 검색 결과 평균 순위 (30위 기준) |
| 지역정합 | 15점 | 지역/주소 포함 비율 |
| 쿼리적합 | 10점 | 등장한 쿼리 수 비율 |
| 활동빈도 | 10점 | 게시물 수 기반 |
| place_fit | 10점 | 주소 토큰 등장 비율 |
| broad_bonus | +5점 | 확장 쿼리 출현 횟수 (블로그 지수 프록시) |
| region_power_bonus | +5점 | 지역 인기 카테고리 상위노출 횟수 (블로그 지수 프록시) |
| food_bias 페널티 | -10점 | 맛집 편향 75%↑:-10, 60%↑:-6, 50%↑:-3 |
| sponsor 페널티 | -15점 | 협찬 비율 60%↑:-15, 45%↑:-8, 30%↑:-3 |

### Strength Points (노출 검증 단계)

| 순위 | 포인트 |
|------|--------|
| 1~3위 | 5점 |
| 4~10위 | 3점 |
| 11~20위 | 2점 |
| 21~30위 | 1점 |

### Keyword Weight (키워드 가중치)

| 접미사 패턴 | 가중치 | 설명 |
|-------------|--------|------|
| 잘하는곳, 비교, 근처 | 1.5x | 핵심 전환 키워드 |
| 추천 | 1.3x | 추천 의도 |
| 후기, 방문후기, 리뷰 | 1.2x | 리뷰 의도 |
| 가격, 가격대 | 1.1x | 가격 비교 의도 |
| 기타 | 1.0x | 기본 가중치 |

### GoldenScore v2.2 (0~100점, 최종 순위) — 메인 랭킹

```
GoldenScore = (BlogPower(25) + Exposure(35) + CategoryFit(25) + Recruitability(15)) × ExposureConfidence
```

| 축 | 최대 | 계산 방식 |
|----|------|-----------|
| BlogPower | 25점 | (base_score / 80) * 25 |
| Exposure | 35점 | 노출 강도 min(1, str/(kw×3))×20 + 커버리지 min(1, exp/(kw×0.5))×15 |
| CategoryFit | 25점 | 음식: food_bias 긍정 (>85% 약한 페널티) / 비음식: food_bias 역비례 |
| Recruitability | 15점 | sponsor 10~30% sweet spot (15점), 60%↑ 패널티 (2점) |

**ExposureConfidence (노출 신뢰 계수):**

| 노출 비율 | confidence | 설명 |
|-----------|-----------|------|
| >= 30% | 1.0 | 충분한 노출 검증 |
| 0% < ratio < 30% | 0.6~1.0 | 부분 페널티 (선형 보간) |
| 0% | 0.4 | 노출 미검증 (60% 감점) |

### Performance Score (레거시, 하위 호환)

```
Performance Score = (strength_sum / 35) * 70 + (exposed_keywords / 10) * 30
```

### Top20/Pool40 태그

- **맛집편향**: food_bias_rate >= 60%
- **협찬성향**: sponsor_signal_rate >= 40%
- **노출안정**: 10개 키워드 중 5개 이상 노출
- **미노출**: exposed_keywords_30d == 0 (검색 노출 미검증, Top20 진입 불가)

### BlogScore (0~100점, 블로그 개별 분석) — v2 5축

```
BlogScore = Activity(15) + Content(20) + Exposure(40) + Suitability(10) + Quality(15)
```

| 축 | 최대 | 계산 방식 |
|----|------|-----------|
| Activity | 15점 | 최근활동(5) + 포스팅빈도(5) + 일관성(2.5) + 포스트수량(2.5) |
| Content | 20점 | 주제다양성(8) + 콘텐츠충실도(6) + 카테고리적합도(6) |
| Exposure | 40점 | 노출강도합계(20) + 키워드커버리지(10) + **협찬글노출보너스(10)** |
| Suitability | 10점 | 협찬수용성(5) + 업종적합도(5) |
| Quality | 15점 | 독창성(5) + 규정준수(5) + 충실도(5) |

**핵심 변경 (v1→v2)**: Exposure 축에 협찬글 상위노출 감지 추가. 검색 결과 포스트 제목에서 협찬/체험단 시그널을 감지하여, **협찬 글을 써도 상위노출되는 블로거**를 우대.
- `sponsored_rank_count`: 노출 포스트 중 협찬 시그널 있는 수
- `sponsored_page1_count`: 그 중 1페이지(10위 이내) — 보너스 = `10 * min(1.0, page1/2 + rank*0.15)`
- Quality 축(HGI 차용): `difflib.SequenceMatcher` 유사도, 금지어 검출, 공정위 표시 확인

### BlogScore 등급

| 점수 | 등급 | 라벨 | 색상 |
|------|------|------|------|
| 85~100 | S | 최우수 | Gold (#FFD700) |
| 70~84 | A | 우수 | Green (--success) |
| 50~69 | B | 보통 | Blue (--primary) |
| 30~49 | C | 미흡 | Orange (--warning) |
| 0~29 | D | 부적합 | Red (--danger) |

### ExposurePotential (상위노출 가능성 예측)

| 등급 | 조건 |
|------|------|
| 매우높음 | 노출 키워드 >= 5개 |
| 높음 | 노출 >= 3개 + best rank <= 10위 |
| 보통 | 노출 >= 1개 + best rank <= 20위 |
| 낮음 | 그 외 |

## 핵심 설계 결정

- **4단계 파이프라인**: seed 후보수집(7) → region_power 지역랭커(3) → broad 확장수집(5) → 노출검증(10: 캐시 7 + 홀드아웃 3) — 총 API 18회
- **홀드아웃 검증**: 노출 키워드 10개 중 3개는 seed와 비중복 (확인편향 방지)
- **API 호출 병렬화**: `ThreadPoolExecutor(max_workers=5)`로 Phase별 쿼리 병렬 실행 (~6.5s → ~2.0s). 캐시에 있는 쿼리는 스킵하고 미캐시 쿼리만 병렬 호출
- **API 재시도/백오프**: 429/5xx → 최대 3회 재시도 (1s → 2s → 4s 지수 백오프)
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
- 테스트 시나리오 34 TC (이후 57 TC로 확장)

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
| Exposure (10 queries, 7 cached) | ~0.4s | ~0.4s (변동 없음) |
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

### 11. 노출검증/후보수집 키워드 전면 교체 + 가이드 SEO 강화 (2026-02-14)

**커밋:** `dcb64a8` — fix: 노출검증/후보수집 키워드를 실제 검색 패턴으로 전면 교체

**수정 파일:** `backend/keywords.py`, `backend/guide_generator.py` (2개)

**노출검증 키워드 교체 (`build_exposure_keywords`):**
- 제거: `전문`, `모임`, `주차`, `협찬` (비현실적 검색어로 노출 검증 무의미)
- 추가: `인기`, `가격`, `리뷰`, `방문후기` (실제 유저 검색 패턴)
- seed 쿼리와 100% 겹침 → 캐시 히트율 86% → 100% (추가 API 호출 0회)

**후보수집 키워드 교체 (`build_seed_queries`):**
- 제거: `모임`, `주차`, `협찬` (업종 편향 키워드)
- 추가: `가격`, `리뷰`, `전문` (범용 검색 패턴)

**B세트 범용화 (`build_keyword_ab_sets`):**
- 제거: `메뉴`, `주차`, `모임` (안경원에서 "메뉴"는 무의미 등 업종 편향)
- 추가: `신상`, `전문`, `가격대`, `솔직후기` (모든 업종 적용 가능)

**가이드 SEO 강화 (`guide_generator.py`):**
- "네이버 지도 링크 삽입 필수 (위치 정보 제공 + SEO 효과)" 추가
- "메인 키워드를 본문에서 가장 많이 사용하도록 구성" 규칙 추가

### 12. 쪽지/메일 버튼 + 키워드별 포스트 링크 + 메시지 템플릿 (2026-02-14)

**커밋:** `b9336de` — feat: 쪽지/메일 버튼 + 키워드별 포스트 링크 + 메시지 템플릿

**수정 파일:** `backend/db.py`, `backend/analyzer.py`, `backend/reporting.py`, `backend/app.py`, `frontend/index.html`, `frontend/src/main.js`, `frontend/src/style.css` (7개)

**DB 스키마 확장 (`db.py`):**
- `exposures` 테이블에 `post_link TEXT`, `post_title TEXT` 컬럼 추가
- `init_db()`에 `ALTER TABLE` 마이그레이션 (기존 DB 호환)
- `insert_exposure_fact()`: `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO UPDATE` (재분석 시 포스트 링크 갱신)

**포스트 링크 캡처 (`analyzer.py`):**
- `exposure_mapping()` 반환 타입: `Dict[str, Dict[str, int]]` → `Dict[str, Dict[str, tuple]]`
- 각 항목: `rank` → `(rank, post_link, post_title)` 튜플
- `save_to_db()`: 튜플 언패킹 → `insert_exposure_fact()`에 `post_link`, `post_title` 전달

**노출 상세 데이터 (`reporting.py`):**
- 각 블로거에 `exposure_details` 배열 추가: `[{keyword, rank, strength_points, is_page1, post_link, post_title}]`
- `is_exposed=1`인 항목만 포함, `rank ASC` 정렬

**메시지 템플릿 API (`app.py`):**
- `GET /api/stores/{store_id}/message-template`: 매장 정보 기반 체험단 모집 쪽지 템플릿 반환
- 매장명, 지역, 업종, 체험 내용, 리뷰 조건 포함

**프론트엔드 (`index.html`, `main.js`, `style.css`):**
- 카드 뷰: 쪽지/메일 버튼 + 키워드별 노출 상세 (순위 + 포스트 링크)
- 리스트 뷰: 쪽지/메일 링크 추가
- 상세 모달: 키워드별 노출 현황 테이블 + 쪽지/메일 보내기 버튼
- 메시지 템플릿 섹션: 프리포맷 텍스트 + 복사 버튼
- 쪽지: `https://note.naver.com` (네이버 쪽지 서비스, 로그인 필요)
- 메일: `https://mail.naver.com` + 블로거 이메일 클립보드 자동 복사 + 토스트 알림
- 새 스타일: `.msg-btn`, `.mail-btn`, `.card-exposure-details`, `.message-template-*`, `.copy-toast`

### 13. 기본 뷰를 리스트로 변경 + 카드/리스트 간소화 (2026-02-14)

**커밋:** `ebb2608` — fix: 기본 뷰를 리스트로 변경 + 카드/리스트 뷰 간소화

**수정 파일:** `frontend/index.html`, `frontend/src/main.js`, `frontend/src/style.css` (3개)

**변경 내용:**
- 기본 뷰: 카드 → **리스트**로 변경 (`viewModes` 기본값 + HTML 토글 active 상태)
- 카드 뷰 간소화: Performance Score 바 + 배지만 표시 (세부 점수/노출 상세/report 라인 제거)
- 리스트 뷰 간소화: `#순위 | 블로거ID | P점수 | 배지 | 상세 | 블로그 | 쪽지 | 메일`
- 리스트 뷰에 상세 보기 버튼(`.detail-btn-sm`) 추가 — 클릭 시 모달에서 전체 점수 표시
- 상세 모달에서만 전체 점수 + 키워드별 노출 현황 + 포스트 링크 표시

### 14. 황금 로직 v2.0: GoldenScore 4축 통합 + 홀드아웃 검증 + 동적 쿼터 (2026-02-15)

**수정 파일:** `backend/scoring.py`, `backend/keywords.py`, `backend/analyzer.py`, `backend/reporting.py`, `backend/db.py`, `backend/models.py`, `backend/app.py`, `frontend/src/main.js` (8개)

**GoldenScore 4축 통합 (`scoring.py`):**
- `golden_score()` 신규: BlogPower(30) + Exposure(30) + CategoryFit(25) + Recruitability(15)
- `keyword_weight_for_suffix()`: 핵심 키워드 가중치 (1.0~1.5x)
- `base_score()` 확장: 0~75 → 0~80 (broad_bonus +5, sponsor_penalty -15 추가)
- `is_food_category()`: 음식 업종 판별 헬퍼

**카테고리 동의어 + 홀드아웃 키워드 (`keywords.py`):**
- `CATEGORY_SYNONYMS` (~40개): 다양한 업종명 → 정규 카테고리 키 매핑
- `resolve_category_key()`: 동의어 해소 함수
- `CATEGORY_HOLDOUT_MAP`: 업종별 홀드아웃 키워드 3개 (확인편향 방지)
- `CATEGORY_BROAD_MAP` 확장: 업종별 인접 카테고리 쿼리
- `build_exposure_keywords()`: 7개 → 10개 (캐시 7 + 홀드아웃 3)

**분석 파이프라인 개선 (`analyzer.py`):**
- `canonical_blogger_id_from_item()`: blogId 쿼리 파라미터 최우선 + 시스템 경로 필터링
- 포스트 중복 제거: `existing_links = {p.link for p in b.posts}`
- `detect_self_blog()`: 멀티시그널 점수 (>= 4 = self) + 프랜차이즈 경쟁사 감지
- 노출 검증 가드: 7 → 10으로 업데이트

**GoldenScore 기반 랭킹 + 동적 쿼터 (`reporting.py`):**
- GoldenScore 내림차순 Top20 + 동적 Pool40 쿼터
- `weighted_strength`: keyword_weight 적용 가중 노출 강도
- `ExposurePotential` 태그: 매우높음/높음/보통/낮음
- 자체블로그/경쟁사 → `competition` 리스트로 분리

**DB 스키마 (`db.py`):**
- `bloggers` 테이블에 `base_score REAL` 컬럼 마이그레이션
- `upsert_blogger()`에 `base_score` 파라미터 추가

**프론트엔드 (`main.js`):**
- `golden_score || performance_score` 하위 호환 참조
- "Golden Score X/100" 라벨 + 바 색상 유지

**API 호출량:**
| 구간 | 기존 | 변경 후 |
|------|------|---------|
| Seed | 10회 | 10회 |
| Broad | 5회 | 5회 |
| Exposure | 0회 (캐시) | **3회** (홀드아웃) |
| **합계** | **15회** | **18회** (+20%) |

### 15. 네이버 API 재시도/백오프 + 가이드 10개 템플릿 업그레이드 (2026-02-15)

**수정 파일:** `backend/naver_client.py`, `backend/guide_generator.py` (2개)

**API 재시도/백오프 (`naver_client.py`):**
- `_RETRYABLE_STATUS = {429, 500, 502, 503, 504}`
- max_retries=3, 지수 백오프 (1s → 2s → 4s)
- Timeout/ConnectionError도 재시도
- 401/403 인증 오류는 즉시 raise

**가이드 10개 업종 템플릿 (`guide_generator.py`):**
- 기존 4종 → 10종 확장: +병원, +치과, +헬스장, +학원, +숙박, +자동차
- 각 템플릿에 `forbidden_words`/`alternative_words` 추가 (법규 준수)
- `seo_guide` 추가: min_chars, max_chars, min_photos, keyword_density, subtitle_rule
- 병원/치과: `disclaimer` 의료법 면책 문구
- `review_structure`에 `word_count` 가이드 (200~800자)
- `_match_template()`: CATEGORY_SYNONYMS 활용 통합 매칭
- "PT" 대소문자 버그 수정 (keyword_map에서 `"PT"` → `"pt"`)

### 16. 시스템 전체 검증 + 테스트 57 TC 완성 (2026-02-15)

**수정 파일:** `backend/test_scenarios.py` (1개)

**테스트 추가 (TC-53~TC-57):**
- TC-53: 신규 템플릿 매칭 (치과/학원/숙박/자동차)
- TC-54: forbidden_words 가이드 포함 확인
- TC-55: seo_guide 필드 존재 확인
- TC-56: 병원/치과 medical disclaimer
- TC-57: review_structure word_count

**시스템 검증 (80개 항목 PASS):**
- 37개 카테고리 입력 → 템플릿 매칭 정확도 100%
- 11개 업종 가이드 출력 품질 (7개 필수 섹션 포함)
- 키워드 시스템 (중복/동의어/홀드아웃 분리)
- 스코어링 경계값/방향성/범위
- 블로거 ID 추출 (8개 URL 패턴)
- 자체블로그 감지 (self/competitor/normal)
- DB + 리포팅 파이프라인 무결성
- 비음식 업종 Pool 쿼터 검증

### 17. 블로그 개별 분석 기능 (BlogScore 4축) (2026-02-15)

**커밋:** `30b570c` — feat: 블로그 개별 분석 기능 (BlogScore 4축 + RSS 파싱 + SSE 스트리밍)

**신규 파일:** `backend/blog_analyzer.py` (1개)
**수정 파일:** `backend/models.py`, `backend/db.py`, `backend/app.py`, `frontend/index.html`, `frontend/src/main.js`, `frontend/src/style.css`, `backend/test_scenarios.py` (7개)

**블로그 개별 분석 엔진 (`blog_analyzer.py`):**
- RSS 피드 파싱 (`rss.blog.naver.com/{id}.xml`) → 포스트 수집 (API 쿼터 미사용)
- BlogScore 4축 계산: Activity(30) + Content(25) + Exposure(30) + Suitability(15)
- 등급 판정: S(85+)/A(70+)/B(50+)/C(30+)/D(<30) + 강점/약점/추천문 자동 생성
- 독립 분석: 포스트 제목에서 키워드 자동 추출 (바이그램 포함)
- 매장 연계 분석: `build_exposure_keywords()` 활용 (캐시 7 + 홀드아웃 3)
- RSS 비활성 대응: 노출력만 부분 계산 + 안내 표시

**데이터 모델 (`models.py`):**
- 6개 데이터클래스 추가: `RSSPost`, `ActivityMetrics`, `ContentMetrics`, `ExposureMetrics`, `SuitabilityMetrics`, `BlogScoreResult`

**DB 스키마 (`db.py`):**
- `blog_analyses` 테이블 추가 (분석 이력 저장: blogger_id, analysis_mode, blog_score, grade, result_json)
- `insert_blog_analysis()` 함수 + `idx_blog_analyses_blogger` 인덱스

**API 엔드포인트 (`app.py`):**
- `GET /api/blog-analysis/stream?blog_url={url}&store_id={id}`: SSE 스트리밍 (4단계 progress → result)
- `POST /api/blog-analysis`: 동기 폴백
- `BlogAnalysisRequest` Pydantic 모델

**프론트엔드 (`index.html`, `main.js`, `style.css`):**
- 블로그 분석 카드: URL 입력 + 매장 셀렉터 드롭다운
- BlogScore 결과: 등급 원형 배지 + 4축 프로그레스 바 + 강점/약점 그리드 + 추천문
- 탭별 상세: 활동 상세 / 콘텐츠 분석 / 노출 현황
- SSE 핸들러 + 동기 폴백 + 매장 셀렉터 로딩

**테스트 (`test_scenarios.py`):**
- TC-58~TC-65: 블로거 ID 추출, 활동 분석, 콘텐츠 분석, 적합도, 등급 경계값, 인사이트 생성, DB 저장, 키워드 추출
- 전체 65 TC PASS

**API 호출량:**
| 모드 | RSS | 검색 API | 합계 |
|------|-----|----------|------|
| 독립 분석 | 1회 | 5~7회 | 6~8회 |
| 매장 연계 | 1회 | 10회 | 11회 |

### 18. BlogScore v2: 5축 체계 + 협찬글 상위노출 예측 + 콘텐츠 품질 검사 (2026-02-15)

**수정 파일:** `backend/models.py`, `backend/blog_analyzer.py`, `frontend/index.html`, `frontend/src/main.js`, `backend/test_scenarios.py` (5개)

**점수 체계 변경 (4축 → 5축):**

| 축 | v1 (Before) | v2 (After) | 변경 |
|----|-------------|------------|------|
| Activity | 30점 | 15점 | 축소 |
| Content | 25점 | 20점 | 축소 |
| Exposure | 30점 | 40점 | 확대 + 협찬글 노출 감지 |
| Suitability | 15점 | 10점 | 축소 |
| Quality | - | 15점 | **신규** (HGI 차용) |

**핵심 신규 기능 — 협찬글 상위노출 감지 (`blog_analyzer.py`):**
- `_SPONSORED_TITLE_SIGNALS`: 10개 협찬 감지 키워드 (체험단/협찬/제공/초대/서포터즈/원고료/제공받/광고/소정의/무료체험)
- `_has_sponsored_signal()`: 포스트 제목에서 시그널 매칭 → exposure detail에 `is_sponsored: bool`
- `sponsored_rank_count` / `sponsored_page1_count` → 협찬글 노출 보너스 (0~10점)
- 의미: **협찬 글을 써도 1페이지에 올라가는 블로거** 우대

**콘텐츠 품질 분석 — `analyze_quality()` (0~15점, HGI 차용):**
- 독창성 (0~5): `difflib.SequenceMatcher`로 포스트 설명 간 평균 유사도 → 낮을수록 높은 점수
- 규정준수 (0~5): 금지어 비율 낮음(3점) + 공정위 표시 패턴 있음(2점)
- 충실도 (0~5): description 평균 길이 기반 (길수록 높은 점수)
- `_FORBIDDEN_WORDS`: 12개 (최고/최저/100%/완치/보장/무조건/확실/1등/가장/완벽/기적/특효)
- `_DISCLOSURE_PATTERNS`: 8개 (제공받아/소정의 원고료/업체로부터/협찬을 받아/무료로 제공/체험단/#협찬/#광고)

**활동 지표 축소 (`analyze_activity()`: 30→15점):**
- 최근활동: 10→5, 포스팅빈도: 10→5, 일관성: 5→2.5, 포스트수량: 5→2.5

**콘텐츠 성향 축소 (`analyze_content()`: 25→20점):**
- 주제다양성: 10→8, 콘텐츠충실도: 8→6, 카테고리적합도: 7→6

**검색 노출력 확대 (`analyze_exposure()`: 30→40점):**
- 기존 노출강도(20) + 키워드커버리지(10) 유지
- 신규 협찬글 노출 보너스(0~10): `10 * min(1.0, sponsored_page1_count/2 + sponsored_rank_count*0.15)`

**체험단 적합도 축소 (`analyze_suitability()`: 15→10점):**
- 협찬수용성: 8→5 (sweet spot 동일 비율), 업종적합도: 7→5 (동일 로직 축소)

**인사이트 강화 (`generate_insights()`):**
- 품질 관련: "콘텐츠 독창성 높음" / "포스트 간 유사도 높음 (복붙 의심)" / "공정위 표시 준수" / "금지어 사용 발견"
- 협찬 노출: "협찬글 상위노출 확인 (N건 1페이지)" / "협찬글 노출 N건"

**SSE 스트리밍 5단계:**
- RSS 수집 → 콘텐츠 분석 → 노출 검색 → **품질 검사** → 점수 계산

**데이터 모델 (`models.py`):**
- `QualityMetrics` 신규: originality/compliance/richness/score
- `ExposureMetrics`: `sponsored_rank_count`, `sponsored_page1_count` 필드 추가, score 0~40
- `BlogScoreResult`: `quality: QualityMetrics` 필드 추가

**프론트엔드 (`index.html`, `main.js`):**
- 5축 바 (콘텐츠품질 바 추가)
- 품질 검사 탭 (독창성/규정준수/충실도/품질점수)
- 노출 아이템에 협찬글 배지 (`<span class="badge-sponsor">협찬글</span>`)
- 노출 상세에 `협찬글 노출 N건` / `협찬글 1페이지 N건` 추가

**테스트 (`test_scenarios.py`: 65→69 TC):**
- TC-59/60/61/63: 기존 점수 범위 수정 (30→15, 25→20, 15→10, quality 파라미터 추가)
- TC-66: `analyze_quality()` 점수 범위 0~15
- TC-67: 협찬 시그널 감지 (`_has_sponsored_signal()` 정확도)
- TC-68: 금지어 검사 (compliance 감점 확인)
- TC-69: 5축 합산 0~100 범위 확인

### 19. GoldenScore 노출력 우선 랭킹 보완 (2026-02-15)

**수정 파일:** `backend/scoring.py`, `backend/reporting.py`, `frontend/src/style.css`, `frontend/src/main.js`, `backend/test_scenarios.py` (5개)

**GoldenScore 가중치 재조정 (`scoring.py`):**
- BlogPower: 30→20, Exposure: 30→40 (strength_part 20→25, coverage_part 10→15)
- 노출 신뢰 계수 (exposure_confidence) 추가:
  - ratio >= 0.3 → confidence = 1.0 (충분한 노출)
  - 0 < ratio < 0.3 → confidence = 0.6~1.0 (부분 페널티)
  - ratio == 0 → confidence = 0.4 (60% 감점)
- `최종 GoldenScore = raw_score × confidence`

**Top20 노출 최소 요건 (`reporting.py`):**
- Top20 gate: `exposed_keywords_30d >= 1` 필수 (0-노출 블로거는 Pool40으로만)
- "미노출" 태그: `exposed_keywords_30d == 0`인 블로거에 자동 부여
- 2차 정렬: `golden_score DESC, strength_sum DESC` (동점 시 노출 강도 우선)

**프론트엔드:**
- `.badge-unexposed` 스타일 추가 (빨간 배경)
- 카드/리스트 뷰에서 "미노출" 배지 렌더링

**테스트 (`test_scenarios.py`: 69→73 TC):**
- TC-36 수정: confidence 적용 후 0~100 범위 유지 + 0-노출 하향 확인
- TC-48 수정: 새 가중치(BP=20, Exp=40) 기준 주석 업데이트
- TC-70: 노출 0점 confidence=0.4 패널티 확인
- TC-71: 노출 충분(>=3) confidence=1.0 확인
- TC-72: Top20 gate — 0-노출 블로거 Top20 진입 불가
- TC-73: 미노출 태그 자동 부여

### 20. GoldenScore v2.2 캘리브레이션: 현실적 벤치마크 적용 (2026-02-15)

**수정 파일:** `backend/scoring.py`, `backend/reporting.py`, `backend/test_scenarios.py` (3개)

**문제**: 실제 노출 1위 블로거(키워드 3개, strength 11)가 52.9점으로 나오는 등 전체 점수가 40~55점대에 집중되어 분별력 부족.

**근본 원인**: 노출 강도 분모 `keywords×5`(전 키워드 1~3위 가정)가 비현실적, 커버리지 100% 기준도 과도.

**GoldenScore 공식 재캘리브레이션 (`scoring.py`):**
- BlogPower: 20→25 (`(base_score/80)*25`, base_score 차별화 회복)
- Exposure: 40→35 (내부 캘리브레이션 대폭 개선)
  - 강도: 분모 `×5`→`×3` (현실적 avg rank 4~10 기준), 최대 20점
  - 커버리지: 분모 `keywords`→`keywords×0.5` (50% 노출 = 만점), 최대 15점
- CategoryFit: 음식 업종에서 food_bias > 85% 시 약한 페널티 추가 (100%: ×0.925)
- Confidence/Recruitability: 변경 없음

**목표 점수 분포:**
| 블로거 유형 | Before (v2.1) | After (v2.2) |
|-------------|---------------|--------------|
| 우수 (base60, str25, 6kw) | ~55 | 70~85 |
| 보통 (base50, str11, 3kw) | ~53 | 55~75 |
| 미노출 (base50, 0kw) | ~22 | <25 |

**메타 라벨 (`reporting.py`):** `"GoldenScore v2.2 (BP25+Exp35+CatFit25+Recruit15 × ExposureConfidence)"`

**테스트 (`test_scenarios.py`: 73→74 TC):**
- TC-48: 주석 `BP=20, Exp=40` → `BP=25, Exp=35` 업데이트
- TC-74: 캘리브레이션 분포 검증 (우수≥70, 보통 55~75, 미노출<25)

### 21. 블로거 후보 수집 재설계: 랭킹 파워 기반 모집 (2026-02-15)

**수정 파일:** `backend/keywords.py`, `backend/analyzer.py`, `backend/models.py`, `backend/scoring.py`, `backend/test_scenarios.py` (5개)

**문제**: 기존 시스템이 "이미 해당 업종 글을 쓴 사람"만 찾고, "상위노출 시킬 수 있는 블로그 지수 높은 사람"을 놓침.
- seed 10개 쿼리가 전부 `{지역} {업종} {접미사}` 패턴 → 업종 터널 비전
- 상호명 자기참조 쿼리로 기존 리뷰어만 수집
- 경쟁사 브랜드 블로그 감지 부족

**쿼리 체계 재설계 (`keywords.py`):**
- `build_seed_queries()`: 10→7개 (핵심 업종 쿼리만, 상호명/주소 토큰 쿼리 제거)
- `build_region_power_queries()` 신규: 3개 (지역 인기 카테고리에서 랭킹 파워 블로거 탐색)
  - `REGION_POWER_MAP`: 업종별 다른 인기 카테고리 매핑 (안경→맛집/카페/핫플 등)
  - 자기 카테고리와 비중복 보장

**분석 파이프라인 확장 (`analyzer.py`):**
- 3단계→4단계: seed(7) → **region_power(3)** → broad(5) → exposure(10)
- `collect_region_power_candidates()`: 상위 10위 이내만 수집 (높은 블로그 지수)
- `FRANCHISE_NAMES`: 14→50개 확장 (안경/카페/음식/미용/헬스/학원/기타)
- `STORE_SUFFIXES` + 브랜드 블로그 패턴 감지: `"{업종}+{매장접미사}"` → competitor
  - "글라스박스안경 강남점" → competitor (업종 + 매장 접미사)
  - "안경에미친남자" → normal (매장 접미사 없음 → 진짜 리뷰어)

**데이터 모델 (`models.py`):**
- `CandidateBlogger.region_power_hits`: 지역 랭킹 파워 쿼리 출현 횟수

**스코어링 (`scoring.py`):**
- `region_power_bonus` (0~5): `region_power_hits >= 2 → 5점, >= 1 → 3점`
- base_score 최대값 80 유지 (자연적 cap)

**API 호출 수:** seed(10→7) + region_power(+3) = **동일 25회** (증가 없음)

**테스트 (`test_scenarios.py`: 74→80 TC):**
- TC-75: `build_region_power_queries()` 카테고리별 3개 쿼리, 자기 카테고리 비중복
- TC-76: `build_seed_queries()` 7개만 생성, 상호명 미포함
- TC-77: 브랜드 블로그 패턴 감지 ("XX안경 강남점" → competitor)
- TC-78: 일반 블로거 오탐 방지 ("안경에미친남자" → normal)
- TC-79: `FRANCHISE_NAMES` 50개+ 확인
- TC-80: 파이프라인 쿼리 수 seed(7)+rp(3)+broad(5)=15

### 22. 검색 폼 재설계: 네이버 주제 드롭다운 + 지역만 검색 모드 (2026-02-15)

**수정 파일:** `frontend/index.html`, `frontend/src/main.js`, `frontend/src/style.css`, `backend/app.py`, `backend/keywords.py`, `backend/analyzer.py`, `backend/test_scenarios.py`, `CLAUDE.md` (8개)

**검색 폼 UI 변경 (`index.html`):**
- `<input id="category-input">` → `<select id="topic-select">` (네이버 블로그 공식 주제 34개, 4그룹 `<optgroup>`)
- `<input id="address-input">` → `<input id="keyword-input">` (자유 키워드 입력)
- 필드 구성: 지역(필수) + 주제 드롭다운(선택) + 매장명(선택) + 키워드(선택)
- 검색 힌트: "지역은 필수입니다. 주제/키워드 미입력 시 지역 전체 블로거를 검색합니다."

**네이버 블로그 주제 목록 (4그룹 34개):**

| 그룹 | 주제 |
|------|------|
| 엔터테인먼트·예술 | 문학·책, 영화, 미술·디자인, 공연·전시, 음악, 드라마, 스타·연예인, 만화·애니, 방송 |
| 생활·노하우·쇼핑 | 일상·생각, 육아·결혼, 반려동물, 좋은글·이미지, 패션·미용, 인테리어·DIY, 요리·레시피, 상품리뷰, 원예·재배 |
| 취미·여가·여행 | 게임, 스포츠, 사진, 자동차, 취미, 국내여행, 세계여행, 맛집 |
| 지식·동향 | IT·컴퓨터, 사회·정치, 건강·의학, 비즈니스·경제, 어학·외국어, 교육·학문 |

**폼 제출 로직 변경 (`main.js`):**
- `category` 파생: 키워드 > 주제 > 빈값 (우선순위)
- `region`만 필수, `category`는 선택 (빈값 허용)
- `address_text` 파라미터 제거

**API 파라미터 변경 (`app.py`):**
- `/api/search/stream`, `/api/search`: `category` 기본값 `""` (선택)
- 유효성: `region`만 필수 (`if not region` → 400)

**지역만 검색 모드 (`keywords.py`, 핵심):**
- `StoreProfile.category_text` 기본값 `""` 으로 변경
- `build_seed_queries()`: 빈 카테고리 → `{r} 맛집`, `{r} 카페`, `{r} 핫플` 등 인기 키워드 7개
- `build_exposure_keywords()`: 빈 카테고리 → 인기 키워드 7캐시 + 홀드아웃 3개(맛집 후기/데이트/일상)
- `build_keyword_ab_sets()`: 빈 카테고리 → 인기 키워드 기반 A/B 세트

**빈 카테고리 처리 (`analyzer.py`):**
- `detect_self_blog()`: 빈 문자열 가드 (`if cat_lower and cat_lower in name_lower`) — 빈 카테고리가 모든 문자열에 매칭되는 문제 방지

**드롭다운 스타일 (`style.css`):**
- `.input-group select` 스타일: 기존 input과 동일한 높이/보더/폰트 + 커스텀 화살표
- `optgroup` 라벨 스타일 (볼드, 보조 텍스트 색상)

**테스트 (`test_scenarios.py`: 80→84 TC):**
- TC-81: `build_seed_queries()` 빈 카테고리 → 7개, 이중 공백 없음
- TC-82: `build_exposure_keywords()` 빈 카테고리 → 10개, 이중 공백 없음
- TC-83: `build_keyword_ab_sets()` 빈 카테고리 → A/B 세트 정상
- TC-84: `detect_self_blog()` 빈 카테고리 → 오탐 없음

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
