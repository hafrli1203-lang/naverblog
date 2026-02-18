# 네이버 블로그 체험단 모집 도구 v2.0

네이버 블로그 검색 API를 활용하여 지역 기반 블로거를 분석하고, 체험단 모집 캠페인을 관리하는 풀스택 웹 애플리케이션.
**v2.0**: SQLite DB 기반 블로거 선별 시스템, GoldenScore v7.2 2단계 랭킹 (Base 6축 100 + Category Bonus 33, BlogPower + 프로필 크롤링 + EP Inference), A/B 키워드 추천, 업종별 가이드 자동 생성(14개 템플릿 + 3계층 키워드 + 리치 뷰), 블로그 개별 분석(GoldenScore v7.2 + 전수 역검색 + 협찬글 상위노출 예측 + 콘텐츠 품질 검사).

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
│   ├── models.py                # 데이터 클래스 (BlogPostItem, CandidateBlogger + v7.2 BlogPower 필드, BlogScoreResult, QualityMetrics 등)
│   ├── keywords.py              # 키워드 생성 (검색/노출/A/B 세트)
│   ├── scoring.py               # 스코어링 (base_score + GoldenScore v7.2 2단계: Base 6축 + Category Bonus 3축)
│   ├── analyzer.py              # 6단계 분석 파이프라인 (병렬 API 호출)
│   ├── blog_analyzer.py         # 블로그 개별 분석 엔진 (RSS + GoldenScore v7.2 + 전수 역검색 + 품질 검사)
│   ├── reporting.py             # Top20/Pool40 리포팅 + 태그 생성
│   ├── naver_client.py          # 네이버 검색 API 클라이언트
│   ├── naver_api.py             # 레거시 분석 엔진 (참조용)
│   ├── guide_generator.py       # 업종별 체험단 가이드 자동 생성
│   ├── maintenance.py           # 데이터 보관 정책 (180일)
│   ├── sse.py                   # SSE 유틸리티
│   ├── test_scenarios.py        # DB/로직 테스트 (158 TC)
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
- `GET /api/stores/{id}/guide`: 체험단 가이드 자동 생성 (14개 업종 + 3계층 키워드 + 구조화 데이터)
  - `sub_category` 쿼리 파라미터 (선택): 세부 업종 지정
  - 반환: 기존 필드(하위 호환) + `keywords_3tier`, `structure_sections`, `forbidden_detailed`, `hashtags`, `compliance`, `seo_detailed`, `checklist`
- `GET /api/guide/keywords/{category}?region=...&sub=...`: 3계층 키워드 추천 (매장 없이 독립 사용)
- `GET /api/guide/categories`: 지원 업종 목록 (14개 + default)
- `GET /api/stores/{id}/message-template`: 체험단 모집 쪽지 템플릿
- `GET /api/blog-analysis/stream`: **SSE 블로그 개별 분석** (GoldenScore v7.2)
  - 이벤트: `progress` (RSS/콘텐츠/노출/품질/스코어링), `result` (BlogScoreResult)
- `POST /api/blog-analysis`: 동기 블로그 분석 (폴백용)

**`backend/blog_analyzer.py`** — 블로그 개별 분석 엔진 (RSS + GoldenScore v7.2 + 전수 역검색 + 품질 검사)

- `extract_blogger_id()`: URL/ID 파싱 (blogId= 쿼리 파라미터 우선, blog.naver.com/{id} 경로, 순수 ID)
- `fetch_rss()`: `https://rss.blog.naver.com/{id}.xml` → `RSSPost` 리스트 (API 쿼터 미사용, 이미지/영상 카운트 포함)
- `_count_media_in_html()`: RSS description HTML에서 `<img>`, `<iframe>`, `<video>` 태그 카운트 (HTML 스트리핑 전)
- `fetch_blog_profile()`: **블로그 프로필 확장 수집 (v7.2 BlogPower용)** — 5개 소스: PostTitleListAsync.naver(최근글/addDate 상대·절대 파싱), 모바일 프로필 m.blog.naver.com(`postCount`/`totalVisitorCount`/`subscriberCount`), PostTitleListAsync 마지막 페이지(블로그 개설일 추정), 데스크톱 폴백(이웃수), RSS 폴백(개설일)
- `compute_image_video_ratio()`: RSS 포스트에서 이미지/영상 포함 비율 계산 (0~1)
- `compute_estimated_tier()`: 블로그 등급 추정 (power/premium/gold/silver/normal) — 이웃수+운영기간+빈도+포스트수 가중합산
- `compute_tfidf_topic_similarity()`: TF-IDF 기반 토픽 유사도 (0~1) — 순수 Python (한글 2-gram, 코사인 유사도)
- `extract_search_keywords_from_posts()`: 포스트 제목에서 2글자+ 한글 키워드 + 바이그램 자동 추출 (레거시, 폴백용)
- `extract_full_reverse_keywords()`: **전수 역검색용 키워드 추출 (v7.2)** — 3단계: 빈도 단일 키워드 15개 + 상위 빈도 2-gram 조합 + 인접 바이그램 = 15~25개
- `analyze_activity()`: 활동 지표 (0~15점) — 최근활동(5)/포스팅빈도(5)/일관성(2.5)/포스트수량(2.5) + 활동 트렌드
- `analyze_content()`: 콘텐츠 성향 (0~20점) — 주제다양성(8)/콘텐츠충실도(6)/카테고리적합도(6) + food_bias/sponsor_rate
- `analyze_exposure()`: 검색 노출력 (0~40점) — 노출강도합계(25)/키워드커버리지(15) (ThreadPoolExecutor 병렬 검색)
- `analyze_suitability()`: 체험단 적합도 (0~10점) — 협찬수용성(5, 10~30% sweet spot)/업종적합도(5)
- `analyze_quality()`: 콘텐츠 품질 (0~15점, HGI 차용) — 독창성(5)/규정준수(5)/충실도(5)
  - `_SPONSORED_TITLE_SIGNALS`: 10개 협찬 감지 키워드 (체험단/협찬/제공/초대/서포터즈/원고료/제공받/광고/소정의/무료체험)
  - `_FORBIDDEN_WORDS`: 12개 금지어 (최고/최저/100%/완치/보장/무조건/확실/1등/가장/완벽/기적/특효)
  - `_DISCLOSURE_PATTERNS`: 8개 공정위 표시 패턴 (제공받아/소정의 원고료/업체로부터 등)
- `compute_grade()`: S(85+)/A(70+)/B(50+)/C(30+)/D(<30) 등급 판정 (BlogScore 전용)
- `generate_insights()`: 강점/약점/추천문 자동 생성 — 품질/협찬글 노출 관련 인사이트 포함
- `analyze_blog()`: 전체 오케스트레이션 (ID추출 → RSS → **프로필** → 콘텐츠 → **전수 역검색 노출** → 품질 → v7.2 스코어링 → 인사이트, SSE 5단계)
- **독립 분석 (전수 역검색)**: 포스트 15건 제목에서 15~25개 키워드 추출 → 네이버 전수 역검색 (v7.2)
  - 3단계 전략: 빈도 기반 단일 키워드(15) + 상위 빈도 2-gram(C(6,2)) + 인접 바이그램(빈도2+)
  - 기존 7개 → 15~25개 키워드로 확장 → 히트율 50%+ 달성
  - 포스트 부족(5개 미만) 시 기존 빈도 기반 7개 폴백
- **매장 연계 분석**: `build_exposure_keywords()` 활용 (10개, 캐시 7 + 홀드아웃 3) + TF-IDF 토픽 유사도
- **RSS 비활성 대응**: 노출력만 부분 계산 + "RSS 비활성" 안내

**`backend/analyzer.py`** — 6단계 분석 파이프라인 (병렬 API 호출)

- `BloggerAnalyzer.analyze()`: 후보수집 → 인기순교차 → 지역 랭커 수집 → 확장 수집 → 기본+체급스코어 → 노출검증 → DB저장
  - 1단계: 카테고리 특화 seed 쿼리 (7개, **병렬 실행**, display=20 — 21~30위 미수집)
  - 1.5단계: 인기순 교차검색 (3개, sort=date, **병렬 실행**) — DIA 프록시 (+3 API)
  - 2단계: 지역 랭킹 파워 블로거 수집 (3개, **병렬 실행**) — 인기 카테고리 상위 10위
  - 3단계: 카테고리 무관 확장 쿼리 (5개, **병렬 실행**)
  - 4단계: 기본 스코어 + 체급 스코어 (v7.2 메트릭: RSS + **프로필 병렬 수집** + 미디어 비율 + 등급 추정)
  - 5단계: 노출 검증 (10개 키워드: 캐시 7개 + 홀드아웃 3개, **병렬 실행**)
  - 6단계: DB 저장
- `_parallel_fetch_profiles()`: 블로그 프로필 병렬 수집 (`ThreadPoolExecutor(max_workers=10)`) — PostTitleListAsync + 모바일 프로필 + 이웃 수 + 개설일 (v7.2 BlogPower용)
- `collect_region_power_candidates()`: 지역 인기 카테고리 검색에서 상위 10위 블로거만 수집 (블로그 지수 높은 사람)
- `detect_self_blog()`: 자체블로그/경쟁사 감지 (멀티시그널 점수 >= 4 → "self") + 브랜드 블로그 패턴 감지
- `FRANCHISE_NAMES`: ~50개 주요 프랜차이즈/체인 (안경/카페/음식/미용/헬스/학원/기타)
- `STORE_SUFFIXES`: 매장 접미사 패턴 (점/원/실/관/샵/스토어/몰/센터/클리닉/의원)
- `exposure_mapping()`: `(rank, post_link, post_title)` 튜플 반환 — 포스트 URL/제목 캡처
- `_search_batch()`: `ThreadPoolExecutor(max_workers=5)`로 복수 쿼리 병렬 실행, 캐시 히트 쿼리 스킵

**`backend/scoring.py`** — 점수 체계

- `base_score()`: 0~80점 (최근활동/SERP순위/지역정합/쿼리적합/활동빈도/place_fit/broad_bonus/seed_page1_bonus - food_penalty - sponsor_penalty)
  - `seed_page1_bonus` (0~8): seed 수집 단계에서 1페이지(10위 이내) 진입 횟수 기반 (5+→8, 3+→5, 1+→2)
- `golden_score_v72()`: **메인 랭킹 함수 (v7.2)** — 2단계: Base Score 6축(0~100) + Category Bonus 3축(0~33)
  - `compute_blog_power()`: **BlogPower (0~25, 신설)** — 포스트수(7)+방문자(7)+영향력(5, max(구독자,랭킹))+운영지속성(6)
  - `apply_ep_inference()`: **EP Inference** — BlogPower 높으면 EP 하한선 보장 (BP≥22→EP≥16, BP≥18→EP≥10, BP≥14→EP≥6, BP≥8→EP≥3)
  - `compute_exposure_power_v72()`: ExposurePower (0~18, 22→18 축소) — SERP빈도(6)+순위분포(6)+노출규모(6)+다양성+인기순(4) + 분모 분리(seed/reverse) + EP Inference
  - `compute_content_authority_v72()`: ContentAuthority (0~16, 22→16 축소) — 구조성숙도+정보밀도+주제전문성+장기패턴+성장추이
    - `_compute_structure_maturity()`: 구조 성숙도 (소제목/단락/리스트 패턴)
    - `_compute_info_density_consistency()`: 정보 밀도 + 일관성 (글자수 변동계수)
    - `_compute_topic_expertise_accumulation()`: 주제 깊이 축적 (깊이있는주제수+주제화비율)
    - `_compute_long_term_pattern()`: 장기 패턴 (포스팅 주기 안정성)
    - `_compute_content_growth_trend()`: 콘텐츠 성장 추이 (최근 글 길이 증가)
  - `compute_rss_quality_v72()`: RSSQuality (0~14, 22→14 축소) — 글길이(7, 이미지보정: +avg_img×300)+Originality(6)+Diversity(5)+미디어활용(4)
  - `compute_freshness_v72()`: Freshness (0~10, 18→10 축소) — 최신글(8)+30일빈도(5)+연속성(2)+간격안정성(3)
  - `compute_search_presence_v72()`: SearchPresence (0~17, 16→17 확대) — 검색친화제목(6)+노출수명(5)+키워드커버리지(5)
    - `_compute_search_friendly_titles()`: 검색 친화적 제목 비율
    - `_compute_post_date_spread()`: 포스팅 노출 수명 분포
    - `_compute_keyword_coverage_v72()`: 고유 키워드 커버리지
  - `compute_sponsor_bonus_v72()`: SponsorBonus (0~8, Category Bonus) — 체험단경험(3)+퀄리티×체험단(3)+내돈내산비율(2)
  - `compute_category_fit_bonus()`: CategoryFit Bonus (0~15, 업종 있을 때만) — 6-signal 가중평균 (TF-IDF 포함)
  - `compute_category_exposure_bonus()`: CategoryExposure Bonus (0~10, 업종 있을 때만) — 노출률+강도평균
  - `assign_grade_v72()`: S+(90+)/S(80+)/A(70+)/B+(60+)/B(50+)/C(40+)/D(30+)/F(<30) 등급 판정
- `golden_score_v71()`: 레거시 (v7.1, 하위 호환) — 2단계: Base(0~100) + Bonus(0~25)
- `golden_score_v7()`: 0~100점 9축 통합 — 레거시 (v7.0, 하위 호환)
- `golden_score()`: 0~100점 — 레거시 (v3.0, 하위 호환)
- `blog_analysis_score()`: 블로그 개별 분석 전용 점수 — v7.2 `golden_score_v72()` 위임 (3-tuple 반환)
- `keyword_weight_for_suffix()`: 핵심 키워드 1.5x, 추천 1.3x, 후기 1.2x, 가격 1.1x, 기타 1.0x
- `performance_score()`: 레거시 (하위 호환용)
- `is_food_category()`: 업종 카테고리 음식 여부 판별
- `calc_food_bias()`, `calc_sponsor_signal()`: 편향률 계산

**`backend/reporting.py`** — Top20/Pool40 리포팅

- `get_top20_and_pool40()`: GoldenScore v7.2 내림차순 Top20 + 동적 쿼터 Pool40
  - **Top20 gate**: `page1_keywords_30d >= 1` (1페이지 노출 최소 1개 필수)
  - **Pool40 gate**: `exposed_keywords_30d >= 1` (30위권 노출 최소 1개 필수, 완전 미노출 제외)
  - 정렬: `final_score DESC → base_score_v71 DESC → strength_sum DESC`
  - 각 블로거에 `base_score_v71`(하위 호환 키), `category_bonus`, `final_score`, `base_breakdown`, `bonus_breakdown`, `analysis_mode`, `grade`, `grade_label` 포함
  - 음식 업종: 맛집 블로거 80% 허용, 비맛집 최소 10%
  - 비음식 업종: 맛집 블로거 30% 제한, 비맛집 최소 50% 우선
- 자체블로그/경쟁사 분리: `detect_self_blog()` → `competition` 리스트로 분리 (Top20/Pool40에서 제외)
- `weighted_strength`: `keyword_weight_for_suffix()` 적용한 가중 노출 강도
- `ExposurePotential` 태그: 매우높음/높음/보통/낮음 (상위노출 가능성 예측)
- 각 블로거에 `exposure_details` 배열 포함: `[{keyword, rank, strength_points, is_page1, post_link, post_title}]`
- 태그 자동 부여: 맛집편향, 협찬성향, 노출안정, 미노출

**`backend/keywords.py`** — 키워드 생성 (카테고리 동의어 + 홀드아웃 + 주제 모드)

- **3가지 검색 모드**: 키워드 모드(업종 키워드 입력) / 주제 모드(네이버 블로그 주제 드롭다운) / 지역만 모드(둘 다 없음)
- `TOPIC_SEED_MAP`: 32개 네이버 블로그 주제 → 7개 실제 검색 쿼리 매핑 (주제명을 리터럴로 쓰지 않음)
- `TOPIC_FOOD_SET`: 음식 관련 주제 (맛집, 요리·레시피) — GoldenScore CategoryFit에서 음식 업종 취급
- `TOPIC_TEMPLATE_HINT`: 주제 → 가이드 템플릿 매칭 힌트 (맛집→음식, 건강·의학→병원 등)
- `is_topic_mode()`: 주제 모드 판별 헬퍼 (keyword 없이 topic만 있는 경우)
- `CATEGORY_SYNONYMS` + `resolve_category_key()`: ~50개 동의어 → 정규 카테고리 키 매핑 (네일샵/피부과/인테리어/꽃집 포함)
- `CATEGORY_HOLDOUT_MAP`: 업종별 홀드아웃 키워드 3개 (seed와 비중복 검증용)
- `CATEGORY_BROAD_MAP`: 업종별 확장 쿼리 5개 (카테고리 인접 키워드)
- `build_seed_queries()`: 후보 수집용 7개. **키워드 모드**: 추천/후기/인기/가격/리뷰/방문후기. **주제 모드**: TOPIC_SEED_MAP 기반 실제 검색 쿼리. **지역만 모드**: 맛집×3(맛집/추천/후기) + 카페×2 + 핫플 + 블로그
- `build_region_power_queries()`: 지역 랭킹 파워 블로거 탐색용 3개 — 자기 업종과 다른 인기 카테고리 (REGION_POWER_MAP). **지역만 모드**: seed와 비중복 쿼리 (`_REGION_ONLY_POWER_TEMPLATES`: 가볼만한곳/데이트코스/나들이)
- `_REGION_ONLY_POWER_TEMPLATES`: 지역만 모드 전용 region power 쿼리 (seed와 비중복 보장, REGION_POWER_MAP에 빈 문자열 키 넣으면 모든 카테고리에 매칭되므로 별도 상수)
- `build_exposure_keywords()`: 노출 검증용 10개 (캐시 7개 + 홀드아웃 3개). **주제 모드**: TOPIC_SEED_MAP 캐시 + 범용 홀드아웃(추천/후기/블로그). **지역만 모드**: 맛집×3 + 카페×2 + 핫플 + 블로그 (캐시 7) + 가볼만한곳/데이트/나들이 (홀드아웃 3)
- `build_broad_queries()`: 확장 후보 수집용 5개 (동의어 해소 후 업종별 매핑)
- `build_keyword_ab_sets()`: A세트 5개 + B세트 5개. **주제 모드**: TOPIC_SEED_MAP 기반 A/B. **지역만 모드**: 인기 키워드 기반 A/B

**`backend/guide_generator.py`** — 업종별 가이드 자동 생성 (14개 템플릿 + 3계층 키워드 추천 + 리치 가이드)

- 업종별 템플릿 14종: 안경원, 카페, 미용실, 음식점, 병원, 치과, 헬스장, 학원, 숙박, 자동차, **네일샵, 피부과, 인테리어, 꽃집** + 기본값
- `main_keyword_override` / `sub_keywords`: 노출 데이터 기반 실제 키워드로 가이드 생성 (주제명 리터럴 방지)
- 리뷰 구조: 방문동기/핵심경험/정보정리/추천대상 + `word_count` 가이드 (200~800자)
- 사진 체크리스트, 키워드 배치 규칙, 해시태그 예시
- `forbidden_words` / `alternative_words`: 업종별 사용 금지 표현 + 대체어 (법규 준수)
- `seo_guide`: min_chars, max_chars, min_photos, keyword_density, subtitle_rule
- 병원/치과 전용 `disclaimer`: 의료법 면책 문구
- 공정위 필수 광고 표기 문구 + `#체험단`/`#협찬` 해시태그 안내 포함
- SEO: 네이버 지도 삽입 필수, 메인 키워드 반복 사용 규칙
- **`INDUSTRY_KEYWORDS`**: 14개 업종 + default — main_suffixes, sub_keywords, longtail, negative, hashtag_base
- **`FORBIDDEN_WORDS_DETAILED`**: 업종별 상세 금지어 (forbidden/replacement/reason 구조) + `_common` 공통
- **`STRUCTURE_TEMPLATES`**: 7개 업종 섹션별 글 구조 (heading/desc/img_min + tips + word_count)
- **`COMPLIANCE_GUIDE`**: 공정위 표시의무 구조화 데이터
- **`SEO_GUIDE_DETAILED`**: 6분야 상세 SEO 가이드 (제목/본문키워드/글구조/이미지/모바일/동영상)
- `generate_keyword_recommendation(region, category, sub_category)` → 3계층 키워드 + 배치전략 + 밀도가이드
- `generate_hashtags(region, category, store_name)` → 동적 해시태그 (지역+매장+업종+일반, 최대 15개)
- `get_forbidden_words_detailed(category)` → 업종별 + 공통 금지어 병합
- `get_structure_template(category, region, store_name, sub_category)` → 섹션별 구조 가이드
- `normalize_category(category)` → 카테고리 정규화
- `get_supported_categories()` → 지원 업종 목록 반환
- `generate_guide()`: `sub_category` 파라미터 + 9섹션 `full_guide_text` + 7개 구조화 데이터 반환

**`backend/db.py`** — SQLite 데이터베이스

- 5개 테이블: stores, campaigns, bloggers, exposures, blog_analyses
- stores 테이블: `topic TEXT` 컬럼 포함 (네이버 블로그 주제 드롭다운 선택값 저장, 마이그레이션 자동)
- exposures 테이블: `post_link TEXT`, `post_title TEXT` 컬럼 포함 (마이그레이션 자동)
- blog_analyses 테이블: 블로그 개별 분석 이력 저장 (blogger_id, blog_url, analysis_mode, store_id, blog_score, grade, result_json)
- `insert_exposure_fact()`: `INSERT ... ON CONFLICT DO UPDATE` (재분석 시 포스트 링크 갱신)
- `insert_blog_analysis()`: 분석 결과 JSON 저장
- v7.1+ 마이그레이션: bloggers 테이블에 `neighbor_count`, `blog_years`, `estimated_tier`, `image_ratio`, `video_ratio`, `exposure_power` 컬럼
- v7.2 마이그레이션: `content_authority`, `search_presence`, `avg_image_count`, `total_posts`, `total_visitors`, `total_subscribers`, `ranking_percentile`, `blog_power` 컬럼 (8개)
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
- **상세 모달**: 상세 보기 클릭 시 v7.2 Base Score 6축 바 + Category Bonus 3축 바 + 키워드별 노출 현황 + 포스트 링크 표시
- **뷰 토글**: 리스트(기본) ↔ 카드 전환 (Top20/Pool40 독립)
- **쪽지/메일**: 카드·리스트·모달에 쪽지(`note.naver.com`)/메일(`mail.naver.com` + 이메일 클립보드 복사) 버튼
- **A/B 키워드**: `/api/stores/{id}/keywords` → 칩 형태로 표시
- **가이드**: `/api/stores/{id}/guide` → **리치 뷰** (3계층 키워드 칩, 글 구조 카드, 금지어 테이블, 해시태그 복사, 체크리스트) + **텍스트 뷰** 토글 + 복사 버튼
- **메시지 템플릿**: `/api/stores/{id}/message-template` → 체험단 모집 쪽지 템플릿 + 복사 버튼
- 캠페인: 생성/조회/삭제, 상세에서 Top20/Pool40 표시
- **블로그 개별 분석**: SSE 핸들러 + GoldenScore v7.2 결과 렌더링 (등급 원형 배지, Base 6축 바 + Category Bonus 3축 바, 강점/약점, 탭별 상세 + 품질 탭 + 전수 역검색 결과)
- **매장 셀렉터**: 분석 시 연계 매장 선택 드롭다운 (독립/매장연계 모드)

**`frontend/src/style.css`** — HiveQ 스타일 디자인 시스템

- **색상 팔레트**: `--primary: #0057FF` 블루 계열, `--bg-color: #f5f6fa` 라이트 배경
- **새 컴포넌트**: 리스트 뷰, 뷰 토글, 키워드 칩, 가이드 섹션, Golden Score 바, 메시지 템플릿 섹션
- **가이드 리치 뷰**: `.guide-rich-view`, `.guide-keyword-tier` (main/sub/longtail 칩), `.guide-structure-card`, `.guide-forbidden-table`, `.guide-hashtag-area`, `.guide-checklist`, `.guide-view-toggle`
- **쪽지/메일 버튼**: `.msg-btn` (그린), `.mail-btn` (오렌지), `.modal-action-btn`
- **노출 상세**: `.card-exposure-details`, `.exposure-detail-row`, `.post-link`
- **토스트 알림**: `.copy-toast` (이메일 복사 알림)
- **새 배지**: `.badge-recommend`, `.badge-food`, `.badge-sponsor`, `.badge-stable`
- **블로그 분석**: `.ba-header-card`, `.ba-grade-box`, `.ba-grade` (원형 등급 배지), `.ba-bar-row`/`.ba-bar-fill` (6축 바 + 보너스 바), `.ba-insights-grid`, `.ba-recommendation`, `.ba-tabs`/`.ba-tab-content` (탭 상세: 활동/콘텐츠/노출/품질)
- **모달 v7.2 바**: `.modal-bar-row`, `.modal-bar-track`, `.modal-bar-fill`, `.modal-bar-label`, `.modal-bar-value`, `.modal-section-header` (Base Score 6축 + Category Bonus 3축 바)
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
| **seed_page1_bonus** | **+8점** | **seed 수집 시 1페이지(10위) 진입 횟수 (5+→8, 3+→5, 1+→2)** |
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

### GoldenScore v7.2 (Base 0~100 + Category Bonus 0~33, 최종 순위) — 메인 랭킹

```
GoldenScore v7.2 = Base Score (0~100) + Category Bonus (0~33)

Base Score = EP + CA + RQ + FR + SP + BP + GD + QF → max(0, min(100, sum))
  6축 합계: 18 + 16 + 14 + 10 + 17 + 25 = 100
Category Bonus = CategoryFit(15) + CategoryExposure(10) + SponsorBonus(8) → 0~33 (업종 있을 때만)
```

**Base Score 6축 (합계 100):**

| 축 | 최대 | 계산 방식 |
|----|------|-----------|
| ExposurePower | 18점 | SERP빈도(6)+순위분포(6)+노출규모(6)+다양성+인기순(4), 분모 분리(seed/reverse) + **EP Inference** |
| ContentAuthority | 16점 | 구조성숙도+정보밀도+주제깊이(deep/medium주제수)+장기패턴+성장추이 |
| RSSQuality | 14점 | 글길이(7, 이미지보정)+Originality(6, SimHash)+Diversity(5, Bayesian)+미디어활용(4) |
| Freshness | 10점 | 최신글(8)+30일빈도(5)+연속성(2)+간격안정성(3) |
| SearchPresence | 17점 | 검색친화제목(6)+노출수명(5)+키워드커버리지(5) |
| **BlogPower** | **25점** | **포스트수(7)+방문자(7)+영향력(5, max(구독자,랭킹))+운영지속성(6)** |
| GameDefense | -10점 | Thin content(-4)+키워드스터핑(-3)+템플릿남용(-3) |
| QualityFloor | +5점 | base≥60+RSS실패=+3, base≥50+저노출+seed상위=+2 |

**Category Bonus 3축 (업종 있을 때만 가산):**

| 축 | 최대 | 계산 방식 |
|----|------|-----------|
| CategoryFit | 15점 | 6-signal 가중평균: kw_match(0.10)+exposure_ratio(0.15)+qh_ratio(0.10)+topic_focus(0.20)+topic_continuity(0.15)+**tfidf_sim(0.30)** |
| CategoryExposure | 10점 | exposure_rate(0.4)+strength_avg(0.6) |
| SponsorBonus | 8점 | 체험단경험(3)+퀄리티×체험단(3)+내돈내산비율(2) |

**v7.2 등급 판정 (항상 Base Score 기준, 7단계):**

| Base Score | 등급 | 라벨 |
|------------|------|------|
| 90+ | S+ | 탁월 |
| 80~89 | S | 우수 |
| 70~79 | A | 양호 |
| 60~69 | B+ | 보통이상 |
| 50~59 | B | 보통 |
| 40~49 | C | 미흡 |
| 30~39 | D | 부족 |
| 0~29 | F | 매우부족 |

**v7.1→v7.2 핵심 변경:**
- **BlogPower(0~25) 신설**: 프로필 크롤링 기반 블로그 규모 평가 — 포스트수(7)+방문자(7)+영향력(5)+운영지속성(6)
  - 프로필 크롤링 5개 소스: PostTitleListAsync(최신글), m.blog.naver.com(통계), PostTitleListAsync 마지막 페이지(개설일 추정), 데스크톱 폴백(이웃), RSS 폴백(개설일)
- **EP Inference**: BlogPower가 높으면 ExposurePower에 하한선 보장 (큰 블로그가 검색 샘플에서 우연히 안 잡힌 경우 보정)
- 5축 → **6축 재배분**: EP(22→18) + CA(22→16) + RQ(22→14) + FR(18→10) + SP(16→17) + **BP(25, 신설)** = 100
- BlogAuthority(22) → **ContentAuthority(16)**: 조작 가능한 외형 지표(이웃수/운영기간) → 포스팅 실력 기반 평가 (구조성숙도/정보밀도/주제전문성/장기패턴/성장추이)
- TopExposureProxy(10) → **SearchPresence(17)**: 인기순교차/이웃수 중복 제거 → 검색 친화성 평가 (제목 최적화/노출 수명/키워드 커버리지)
- SponsorFit(8) → **SponsorBonus(8)**: Base Score에서 Category Bonus로 이동 (단독 분석 시 제외)
- ExposurePower: 30 → 18 축소 + **분모 분리(seed/reverse)** + **노출규모 신설** + 전수 역검색 강화 + **EP Inference**
- RSSQuality: 18 → 14 (글길이 5→7 + **이미지 보정: adjusted_len = text + avg_img×300**, Originality 4→6)
- ContentAuthority 주제깊이: top1_ratio(집중도) → **deep/medium 주제 수(다주제 깊이)**
- 등급 체계: 5단계(S/A/B/C/D) → **7단계(S+/S/A/B+/B/C/D/F)**, 라벨: S+→탁월, S→우수, A→양호, B+→보통이상
- Freshness: 12 → 10 (최신글+빈도+연속성+간격안정성)
- Category Bonus: 25 → 33 확대 (SponsorBonus 8점 이동)
- GameDefense/QualityFloor: **0일 때 숨김** (적용 시에만 표시)
- DB: `total_posts`, `total_visitors`, `total_subscribers`, `ranking_percentile`, `blog_power` 컬럼 마이그레이션

### GoldenScore v7.1 (Base 0~100 + Category Bonus 0~25, 레거시, 하위 호환)

```
GoldenScore v7.1 = Base Score (0~100) + Category Bonus (0~25)
Base Score = normalize(EP + BA + RQ + FR + TE + SF + GD + QF, max_raw=105) → 0~100
Category Bonus = CategoryFit(15) + CategoryExposure(10) → 0~25 (업종 있을 때만)
```

### GoldenScore v7.0 (0~100점, 레거시, 하위 호환)

```
GoldenScore v7.0 = BlogAuthority(22) + CategoryExposure(18) + TopExposureProxy(12) + CategoryFit(15)
                 + Freshness(10) + RSSQuality(13) + SponsorFit(5) + GameDefense(-10) + QualityFloor(+5)
```

**GameDefense 3-signal:**
- Thin content (-4): 평균 글 길이 < 500자 + 포스팅 간격 < 0.5일
- 키워드 스터핑 (-3): 제목 내 동일 단어 3회+ 반복 비율 ≥ 30%
- 템플릿 남용 (-3): SimHash near-duplicate rate ≥ 50%

### GoldenScore v3.0 (레거시, 하위 호환)

```
GoldenScore v3.0 = (BlogPower(15) + Exposure(30) + Page1Authority(15) + CategoryFit(20) + Recruitability(10)) × Page1Confidence
```

### Performance Score (레거시, 하위 호환)

```
Performance Score = (strength_sum / 35) * 70 + (exposed_keywords / 10) * 30
```

### Top20/Pool40 진입 조건 + 태그

**진입 조건 (v7.2):**
- **Top20**: `page1_keywords_30d >= 1` (1페이지 노출 최소 1개 필수)
- **Pool40**: `exposed_keywords_30d >= 1` (30위권 노출 최소 1개 필수)
- **완전 미노출** (exposed=0): Top20/Pool40 모두 제외

**태그 (v7.2, 고권위/저권위 레거시 태그 제거됨):**
- **맛집편향**: food_bias_rate >= 60%
- **협찬성향**: sponsor_signal_rate >= 40%
- **노출안정**: 고유 노출 포스트(unique_exposed_posts) >= 5개
- **미노출**: exposed_keywords_30d == 0 (결과에서 제외)

### BlogScore (0~100점, 블로그 개별 분석) — v2 5축

```
BlogScore = Activity(15) + Content(20) + Exposure(40) + Suitability(10) + Quality(15)
```

| 축 | 최대 | 계산 방식 |
|----|------|-----------|
| Activity | 15점 | 최근활동(5) + 포스팅빈도(5) + 일관성(2.5) + 포스트수량(2.5) |
| Content | 20점 | 주제다양성(8) + 콘텐츠충실도(6) + 카테고리적합도(6) |
| Exposure | 40점 | 노출강도합계(25) + 키워드커버리지(15) |
| Suitability | 10점 | 협찬수용성(5) + 업종적합도(5) |
| Quality | 15점 | 독창성(5) + 규정준수(5) + 충실도(5) |

- Quality 축(HGI 차용): SimHash 기반 근사 중복 검출, 금지어 검출, 공정위 표시 확인

### BlogScore 등급

| 점수 | 등급 | 라벨 | 색상 |
|------|------|------|------|
| 85~100 | S | 최우수 | Gold (#FFD700) |
| 70~84 | A | 우수 | Green (--success) |
| 50~69 | B | 보통 | Blue (--primary) |
| 30~49 | C | 미흡 | Orange (--warning) |
| 0~29 | D | 부적합 | Red (--danger) |

### ExposurePotential (상위노출 가능성 예측, 고유 포스트 기반)

| 등급 | 조건 |
|------|------|
| 매우높음 | 고유 노출 포스트 >= 5개 |
| 높음 | 고유 노출 >= 3개 + 1페이지 노출 포스트 >= 1개 |
| 보통 | 고유 노출 >= 1개 + 최고순위 <= 20위 |
| 낮음 | 그 외 |

## 핵심 설계 결정

- **6단계 파이프라인**: seed 후보수집(7) → **인기순교차(3)** → region_power 지역랭커(3) → broad 확장수집(5) → 기본+체급스코어 → 노출검증(10: 캐시 7 + 홀드아웃 3) — 총 API 21회
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
- `<input id="category-input">` → `<select id="topic-select">` (네이버 블로그 공식 주제 32개, 4그룹 `<optgroup>`)
- `<input id="address-input">` → `<input id="keyword-input">` (자유 키워드 입력)
- 필드 구성: 지역(필수) + 주제 드롭다운(선택) + 매장명(선택) + 키워드(선택)
- 검색 힌트: "지역은 필수입니다. 주제/키워드 미입력 시 지역 전체 블로거를 검색합니다."

**네이버 블로그 주제 목록 (4그룹 32개):**

| 그룹 | 주제 |
|------|------|
| 엔터테인먼트·예술 | 문학·책, 영화, 미술·디자인, 공연·전시, 음악, 드라마, 스타·연예인, 만화·애니, 방송 |
| 생활·노하우·쇼핑 | 일상·생각, 육아·결혼, 반려동물, 좋은글·이미지, 패션·미용, 인테리어·DIY, 요리·레시피, 상품리뷰, 원예·재배 |
| 취미·여가·여행 | 게임, 스포츠, 사진, 자동차, 취미, 국내여행, 세계여행, 맛집 |
| 지식·동향 | IT·컴퓨터, 사회·정치, 건강·의학, 비즈니스·경제, 어학·외국어, 교육·학문 |

**폼 제출 로직 변경 (`main.js`):**
- `topic`과 `keyword`를 별도 파라미터로 전송 (→ #23에서 분리)
- `region`만 필수, `category`는 선택 (빈값 허용)
- `address_text` 파라미터 제거

**API 파라미터 변경 (`app.py`):**
- `/api/search/stream`, `/api/search`: `topic`/`keyword` 별도 수신, `category` 기본값 `""` (선택)
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

### 23. 주제 모드 신뢰도 개선: TOPIC_SEED_MAP + 데이터 기반 키워드/가이드 (2026-02-15)

**수정 파일:** `backend/keywords.py`, `backend/app.py`, `backend/guide_generator.py`, `backend/db.py`, `frontend/src/main.js`, `backend/test_scenarios.py`, `CLAUDE.md` (7개)

**문제**: #22에서 추가한 주제 드롭다운이 주제명을 리터럴로 검색 키워드에 넣는 문제.
- "비즈니스·경제" 선택 → "제주시 비즈니스·경제 추천" (비현실적 검색어)
- A/B 키워드가 정적 템플릿 (실제 노출 데이터 미반영)
- 가이드/메시지 템플릿이 주제명을 키워드로 사용

**주제→실제 검색 쿼리 변환 (`keywords.py`, 핵심):**
- `TOPIC_SEED_MAP`: 32개 네이버 블로그 주제 각각에 대해 7개 실제 검색 쿼리 매핑
  - 예: "비즈니스·경제" → `["{r} 창업", "{r} 재테크", "{r} 부동산", "{r} 투자", ...]`
  - 예: "패션·미용" → `["{r} 미용실", "{r} 네일", "{r} 패션", "{r} 뷰티", ...]`
- `TOPIC_FOOD_SET`: 음식 관련 주제 (맛집, 요리·레시피) — CategoryFit 음식 업종 취급
- `TOPIC_TEMPLATE_HINT`: 주제 → 가이드 템플릿 매칭 (맛집→음식, 건강·의학→병원)
- `is_topic_mode()`: 주제 모드 판별 (keyword 없이 topic만)
- `build_seed_queries()` / `build_exposure_keywords()` / `build_keyword_ab_sets()`: 3모드 분기 (키워드/주제/지역만)

**프론트엔드 topic/keyword 분리 (`main.js`):**
- 기존: `category = keyword || topic || ""` (하나로 합침)
- 변경: `topic`과 `keyword`를 별도 파라미터로 전송

**데이터 기반 A/B 키워드 + 가이드 (`app.py`):**
- `/api/stores/{id}/keywords`: 정적 템플릿 → exposures 테이블에서 실제 노출 데이터 조회 (strength, page1_count, blogger_count)
- `/api/stores/{id}/guide`: 노출 데이터 상위 3개 키워드로 가이드 생성 (`main_keyword_override` + `sub_keywords`)
- `/api/stores/{id}/message-template`: 노출 데이터 기반 추천 키워드 포함

**가이드 키워드 오버라이드 (`guide_generator.py`):**
- `generate_guide()`: `main_keyword_override`/`sub_keywords` 파라미터 추가 — 노출 데이터 기반 실제 키워드 우선 사용

**DB topic 컬럼 (`db.py`):**
- stores 테이블에 `topic TEXT` 컬럼 마이그레이션 추가
- `upsert_store()`: `topic` 파라미터 지원

**테스트 (`test_scenarios.py`: 84→89 TC):**
- TC-85: `build_seed_queries()` 주제 모드 → TOPIC_SEED_MAP 기반, 리터럴 주제명 미포함
- TC-86: `build_exposure_keywords()` 주제 모드 → 10개, 캐시 7 + 홀드아웃 3
- TC-87: `build_keyword_ab_sets()` 주제 모드 → A/B 세트, 리터럴 미포함
- TC-88: `is_topic_mode()` 헬퍼 정확도 (5가지 시나리오)
- TC-89: `TOPIC_SEED_MAP` 32개 주제 전체 커버리지 + 쿼리 템플릿 검증

### 24. GoldenScore v3.0: 상위노출 블로거 정확 선별 + 키워드 디버그 로깅 (2026-02-15)

**수정 파일:** `backend/scoring.py`, `backend/reporting.py`, `backend/analyzer.py`, `backend/app.py`, `backend/test_scenarios.py` (5개)

**문제**: pepechan3 (22~23위, 1페이지 0개) 블로거가 45.7점으로 상위 랭킹 진입.
- CategoryFit 25점이 노출 능력과 무관 (food_bias=0이면 무조건 만점)
- ExposureConfidence 0.867: 20% 노출(2/10)에 13% 감점만 → 차별화 불가
- Top20 gate: `exposed >= 1` (30위권 1개면 진입) → page1 요구 없음

**GoldenScore v3.0 — 5축 통합 + Page1Authority (`scoring.py`):**
- **Page1Authority 신설 (0~15점)**: 1페이지 노출 비율 = 블로그 지수 핵심 프록시
  - 50%+ → 15점, 30%+ → 12점, 20%+ → 8점, 10%+ → 4점, 0% → 0점
- 축 가중치 재배분: BlogPower 25→15, Exposure 35→30, **+Page1Auth 15**, CategoryFit 25→20, Recruitability 15→10
- **Page1Confidence**: page1 기반 신뢰 계수 (기존 exposure ratio 기반에서 전환)
  - page1>=30% → 1.0, >=10% → 0.8, exposed>=30% → 0.55, exposed>0 → 0.35, 0 → 0.2
- `base_score`에 `seed_page1_bonus` 추가 (0~8점): seed 수집 시 1페이지 진입 횟수

**pepechan3 점수 변화:**
```
v2.2: BP15 + Exp7.3 + CatFit25 + Recruit8 = 55.3 × 0.867 = 45.7
v3.0: BP9 + Exp5.5 + P1Auth0 + CatFit14 + Recruit5 = 33.5 × 0.35 = 11.7
```

**Top20/Pool40 진입 강화 (`reporting.py`):**
- Top20 gate: `exposed >= 1` → `page1_keywords >= 1` (1페이지 필수)
- Pool40 gate: 완전 미노출(exposed=0) 제외
- 정렬: `golden_score DESC → page1_keywords DESC → strength_sum DESC`
- 메타 라벨: `"GoldenScore v3.0 (BP15+Exp30+P1Auth15+CatFit20+Recruit10 × Page1Confidence)"`

**후보 수집 품질 개선 (`analyzer.py`):**
- seed 수집 `display=30` → `display=20` (21~30위 후보 미수집 → 저품질 블로거 제외)
- 노출 검증은 `display=30` 유지

**키워드 디버그 로깅 (`app.py`):**
- `_sync_analyze` 시작 시 검색 파라미터 로깅 (`region`, `category_text`, `topic`, `store_name`)

**테스트 (`test_scenarios.py`: 89→94 TC):**
- TC-36/45/48/70/71/72/73/74: v3.0 파라미터/동작에 맞게 수정
- TC-90: Page1Authority 축 검증 (page1=5 vs page1=0 gap>=20점)
- TC-91: v3.0 Confidence (page1=0, exposed=2 → 0.35x → <20점)
- TC-92: Top20 gate: page1=0 → Pool40만 가능
- TC-93: seed 수집 display=20 소스 확인
- TC-94: 상위노출자 vs 하위노출자 점수 차이 >= 40점

**예상 점수 분포:**
| 블로거 유형 | v2.2 | v3.0 | 변화 |
|------------|------|------|------|
| 최우수 (page1=7, str=30) | ~78 | 85~95 | ↑↑ |
| 우수 (page1=3, str=15) | ~65 | 55~70 | → |
| pepechan3류 (page1=0, str=2) | 45.7 | ~12 | ↓↓↓ |
| 미노출 (page1=0, str=0) | ~22 | ~8 | ↓↓ |

### 25. 지역만 검색 모드 블로거 수집 강화 (2026-02-16)

**수정 파일:** `backend/keywords.py`, `backend/test_scenarios.py` (2개)

**문제**: "노형동"만 검색하면 맛집 상위노출 블로거가 누락되지만, "노형동" + "맛집" 키워드 검색 시 정상 표시됨.

**근본 원인 (3가지):**
1. Seed 쿼리 깊이 부족: 맛집 키워드가 7개 중 2개뿐 (29%) → 얕은 커버리지
2. Region power 쿼리 중복: 빈 카테고리에서 `_default` 사용 → seed와 동일 3개 → API 3회 낭비
3. 노출검증 키워드 희석: 맛집 키워드 10개 중 2개 → 맛집 1위 블로거도 2/10 노출 → 낮은 GoldenScore

**Seed 쿼리 재설계 (`build_seed_queries()` 지역만 모드):**
- Before: `[맛집, 맛집 추천, 카페, 카페 추천, 핫플, 가볼만한곳, 블로그]`
- After: `[맛집, 맛집 추천, 맛집 후기, 카페, 카페 추천, 핫플, 블로그]`
- 변경점: +맛집 후기(깊이 2→3), -가볼만한곳(rp로 이동), 블로그 유지
- 순수 지역명 `{r}` 제외: 고유 기여 6명뿐 vs "블로그" 20명 커버 → 블로그 유지가 효율적

**Region power 중복 해소 (`build_region_power_queries()`):**
- `_REGION_ONLY_POWER_TEMPLATES` 신규: `[가볼만한곳, 데이트 코스, 나들이]` — seed와 완전 비중복
- 기존: `_default`(맛집추천/카페추천/핫플) = seed와 100% 중복 → API 3회 낭비 + 신규 0명
- REGION_POWER_MAP에 빈 문자열 키를 넣으면 `resolve_category_key()`에서 모든 카테고리에 매칭되므로 별도 상수로 분리

**Exposure 키워드 재설계 (`build_exposure_keywords()` 지역만 모드):**
- Before 캐시: `[맛집, 맛집 추천, 카페, 카페 추천, 핫플, 가볼만한곳, 블로그]` + 홀드아웃: `[맛집 후기, 데이트, 일상]`
- After 캐시: `[맛집, 맛집 추천, 맛집 후기, 카페, 카페 추천, 핫플, 블로그]` + 홀드아웃: `[가볼만한곳, 데이트, 나들이]`
- 맛집 2/10 → 3/10 (+50%), 일상 제거 (검증 부적합), 나들이 추가

**테스트 (`test_scenarios.py`: 94→102 TC):**
- TC-75 수정: 빈 카테고리 region power ≠ seed 비중복 검증 추가
- TC-81 수정: 맛집 3개 + 블로그 포함 확인
- TC-82 수정: 맛집 3개 + 블로그 포함 확인
- TC-101: 지역만 모드 region power와 seed 간 중복 0개 검증
- TC-102: 맛집 후기 + 블로그 포함, 가볼만한곳 rp 이동 확인

**실측 효과 (노형동 검색, API 검증):**
| 항목 | 수정 전 | 수정 후 | 변화 |
|------|---------|---------|------|
| Seed 후보 풀 | 118명 | 115명 | -3명 |
| RP 신규 블로거 | 0명 (seed 중복) | 28명 | **+28명** |
| 총 후보 풀 | 118명 | 143명 | **+25명** |
| 맛집 블로거 | 39명 | 54명 | **+15명** |
| 블로그 쿼리 커버 | 20/20명 | 20/20명 | 유지 |
| 가볼만한곳 11-20위 손실 | - | 9명 | 트레이드오프 |

### 26. GoldenScore v7.0: 9축 통합 + SimHash + GameDefense + Phase 1.5 (2026-02-16)

**수정 파일:** `backend/scoring.py`, `backend/models.py`, `backend/db.py`, `backend/analyzer.py`, `backend/reporting.py`, `backend/blog_analyzer.py`, `backend/app.py`, `frontend/src/main.js`, `backend/test_scenarios.py` (9개)

**문제**: v5.0(5축)의 한계 — difflib 기반 독창성(정확도 낮음), 카테고리 적합도 3-signal만, 스팸/어뷰징 감점 부재, 데이터 부족 보정 없음.

**점수 체계 변경 (5축 → 9축):**

| 축 | v5.0 | v7.0 | 변경 내용 |
|----|------|------|-----------|
| BlogAuthority | 30 | 22 | 배점 축소 |
| CategoryExposure | 25 | 18 | 배점 축소 |
| TopExposureProxy | - | 12 | **신규**: Phase 1.5 인기순 교차검색 DIA 추정 |
| CategoryFit | 15 | 15 | 3-signal → 5-signal (topic_focus, topic_continuity 추가) |
| Freshness | 10 | 10 | base_score 프록시 → 실제 시간 기반 |
| RSSQuality | 20 | 13 | difflib → SimHash + Bayesian diversity |
| SponsorFit | - | 5 | **신규**: 협찬률 적합도 |
| GameDefense | - | -10 | **신규**: Thin/키워드스터핑/템플릿 감점 |
| QualityFloor | - | +5 | **신규**: 데이터 부족 보정 보너스 |

**신규 함수 (`scoring.py`, 11개):**
- `compute_simhash(text)`: 64비트 SimHash 핑거프린트 (한국어 3-gram, hashlib.md5)
- `hamming_distance(h1, h2)`: SimHash 간 해밍 거리 (0~64)
- `compute_near_duplicate_rate(rss_posts)`: SimHash 기반 근사 중복률 (해밍≤3)
- `compute_originality_v7(rss_posts)`: SimHash 독창성 (0~8)
- `compute_diversity_smoothed(rss_posts)`: Bayesian smoothed 엔트로피 (Dirichlet prior)
- `compute_topic_focus(rss_posts, match_keywords)`: RSS 키워드 집중도 (0~1)
- `compute_topic_continuity(rss_posts, match_keywords)`: 최근 10개 연속성 (0~1)
- `compute_game_defense(rss_posts, rss_data)`: 3-signal 감점 (0 to -10)
- `compute_quality_floor(base_score, rss_success, exposure, seed_p1)`: 보정 (0 to +5)
- `_sponsor_fit(rate)`: 협찬률 적합도 (0~5)
- `_freshness_time_based(days)`: 시간 기반 Freshness (0~10)
- `golden_score_v7(...)`: 9축 통합 함수

**CandidateBlogger 8개 필드 추가 (`models.py`):**
- `popularity_cross_score`, `topic_focus`, `topic_continuity`, `game_defense`, `quality_floor`, `days_since_last_post`, `rss_originality_v7`, `rss_diversity_smoothed`

**DB 마이그레이션 + upsert 확장 (`db.py`):**
- 8개 컬럼 ALTER TABLE 마이그레이션 (DEFAULT 0/NULL)
- `upsert_blogger()` 18→26 파라미터

**Phase 1.5 인기순 교차검색 (`analyzer.py`):**
- `_search_batch()`/`_search_cached()`: `sort` 파라미터 추가, 캐시 키에 sort 포함
- `collect_popularity_cross()`: seed 3개를 sort=date로 재검색 → sim∩date 교차 = DIA
- `compute_tier_scores()` 확장: v7 메트릭 7개 계산
- `save_to_db()` 확장: 8개 신규 필드 전달
- `analyze()` 5단계→6단계 (Phase 1.5 추가, API 18→21회)

**v7 호출 전환 (`reporting.py`):**
- `golden_score_v5()` → `golden_score_v7()` 호출
- SQL SELECT에 8개 신규 컬럼 추가
- 메타 라벨: `"GoldenScore v7.0 (Auth22+CatExp18+TopExp12+CatFit15+Fresh10+RSSQual13+SpFit5+GameDef-10+QualFloor+5)"`

**SimHash 독창성 (`blog_analyzer.py`):**
- `difflib.SequenceMatcher` → SimHash 기반 근사 중복 검출로 교체

**버전 라벨 (`main.js`, `app.py`):**
- `GS v5.0` → `GS v7.0`, `Golden Score v5.0` → `Golden Score v7.0`
- `분석 완료 (GoldenScore v5.0)` → `분석 완료 (GoldenScore v7.0)`

**테스트 (`test_scenarios.py`: 129→145 TC):**
- TC-130~145: 16개 신규 (SimHash, GameDefense, QualityFloor, TopicFocus, TopicContinuity, Diversity, Originality, SponsorFit, Freshness, golden_score_v7 범위/분별력)
- TC-114 수정: v5.0 → v7.0 메타 라벨 확인
- `_FakeRSSPost` 헬퍼 클래스 추가

**설계 결정:**
- 새 pip 의존성 없음 (SimHash/Bayesian 순수 Python)
- Phase 1.5는 기존 NaverBlogSearchClient `sort="date"` 활용 (+3 API)
- v5/v4/v3 레거시 함수 삭제 없음 (하위 호환)
- DB 하위 호환: 모든 신규 컬럼 DEFAULT 0/NULL

**검증 결과:**

| 항목 | 결과 |
|------|------|
| 테스트 | 145/145 PASS |
| DB 마이그레이션 | 8/8 컬럼 OK |
| 고권위+노출 | 85.0점 (목표 80+) |
| 저권위+미노출 | 5.9점 (목표 <20) |
| 분별력 | 79.1점 차이 |
| GameDefense | -10.0점 영향 |
| QualityFloor | +5.0점 영향 |
| SponsorFit | 4.6점 차이 (sweet>excess) |

### 27. GoldenScore v7.1: 2단계 점수 체계 + 블로그 프로필 수집 + 프론트엔드 반영 (2026-02-16)

**수정 파일:** `backend/scoring.py`, `backend/models.py`, `backend/db.py`, `backend/analyzer.py`, `backend/reporting.py`, `backend/blog_analyzer.py`, `backend/app.py`, `backend/test_scenarios.py`, `frontend/src/main.js`, `frontend/src/style.css` (10개)

**문제**: v7.0(9축 단일 점수)의 한계 — 업종 유무에 따른 점수 공정성 문제, 블로그 권위를 CrossCat만으로 추정 (이웃 수/운영 기간 미반영), SponsorFit 5점으로 체험단 경험 차별화 부족, 미디어 활용도 미반영.

**점수 체계 변경 (단일 → 2단계):**

| 구분 | v7.0 | v7.1 | 변경 내용 |
|------|------|------|-----------|
| 구조 | 9축 단일 (0~100) | Base(0~100) + Bonus(0~25) | 업종 무관 Base + 업종 특화 Bonus 분리 |
| ExposurePower | - | 30 | **신규**: SERP빈도+순위분포+인기순교차+노출다양성 |
| BlogAuthority | 22 (CrossCat) | 22 (등급+이웃+기간) | CrossCat → 프로필 기반 (이웃 수, 운영 기간, 등급 추정) |
| RSSQuality | 13 | 18 | +미디어 활용도 (이미지/영상 비율) |
| Freshness | 10 | 12 | +30일빈도+3개월연속성 |
| TopExposureProxy | 12 | 10 | 이웃×base 복합 추가 |
| SponsorFit | 5 | 8 | 체험단경험+퀄리티×체험단+내돈내산비율 |
| CategoryFit | 15 (Base에 포함) | 15 (Bonus 분리) | 5→6-signal (TF-IDF 추가), **Base에서 Bonus로 이동** |
| CategoryExposure | 18 (Base에 포함) | 10 (Bonus 분리) | **Base에서 Bonus로 이동** |
| GameDefense | -10 | -10 | 변경 없음 |
| QualityFloor | +5 | +5 | 변경 없음 |

**신규 데이터 수집 (`blog_analyzer.py`, 4개 함수):**
- `fetch_blog_profile()`: blog.naver.com/{id} HTML에서 `buddyCnt` 파싱 → 이웃 수 + RSS 최오래된 포스트 → 개설일 추정
- `compute_image_video_ratio()`: RSS `<img>`, `<iframe>`, `<video>` 태그 카운트 → 이미지/영상 포함 비율
- `compute_estimated_tier()`: 이웃수+운영기간+빈도+포스트수 가중합산 → power/premium/gold/silver/normal
- `compute_tfidf_topic_similarity()`: 순수 Python TF-IDF (한글 2-gram, 코사인 유사도) → 토픽 유사도 (0~1)

**신규 v7.1 함수 (`scoring.py`, 10개):**
- `compute_exposure_power()`: ExposurePower (0~30)
- `compute_blog_authority_v71()`: BlogAuthority (0~22)
- `compute_rss_quality_v71()`: RSSQuality (0~18)
- `compute_freshness_v71()`: Freshness (0~12)
- `compute_top_exposure_proxy_v71()`: TopExposureProxy (0~10)
- `compute_sponsor_fit_v71()`: SponsorFit (0~8)
- `compute_category_fit_bonus()`: CategoryFit Bonus (0~15)
- `compute_category_exposure_bonus()`: CategoryExposure Bonus (0~10)
- `golden_score_v71()`: 2단계 통합 함수 (dict 반환)
- `assign_grade_v71()`: S(80+)/A(65+)/B(50+)/C(35+)/D(<35)

**CandidateBlogger 6개 필드 추가 (`models.py`):**
- `neighbor_count`, `blog_years`, `estimated_tier`, `image_ratio`, `video_ratio`, `exposure_power`
- `RSSPost`: `image_count`, `video_count` 필드 추가

**DB 마이그레이션 (`db.py`):**
- 6개 컬럼 ALTER TABLE 마이그레이션 (neighbor_count, blog_years, estimated_tier, image_ratio, video_ratio, exposure_power)
- `upsert_blogger()` 26→32 파라미터

**파이프라인 확장 (`analyzer.py`):**
- `_parallel_fetch_profiles()`: `ThreadPoolExecutor(max_workers=10)` 프로필 병렬 수집
- `compute_tier_scores()`: 4단계→프로필 수집 추가, v7.1 메트릭 (미디어 비율, 등급 추정) 계산

**v7.1 호출 전환 (`reporting.py`):**
- `golden_score_v7()` → `golden_score_v71()` 호출
- 결과에 `base_score_v71`, `category_bonus`, `final_score`, `base_breakdown`, `bonus_breakdown`, `analysis_mode` 포함
- 정렬: `final_score DESC → base_score_v71 DESC → strength_sum DESC`
- 메타 라벨: `"GoldenScore v7.1 (Base100+Bonus25)"`

**블로그 개별 분석 v7.1 전환 (`blog_analyzer.py`):**
- `analyze_blog()`: 프로필 수집 + v7.1 메트릭 계산 + `blog_analysis_score()` 3-tuple 반환
- 결과에 `base_score`, `category_bonus`, `final_score`, `base_breakdown`, `bonus_breakdown` 포함

**프론트엔드 (`main.js`, `style.css`):**
- 카드 뷰: "GS v7.0" → "GS v7.1" 라벨
- 상세 모달: v7.1 Base Score 8축 프로그레스 바 + Category Bonus 2축 바 렌더링
  - 감점 항목(GameDefense) 빨간 바 별도 렌더링
  - 업종 보너스 섹션 (bonus_breakdown 존재 시만 표시)
  - 분석 모드 표시 (지역/업종)
- 블로그 분석: base_breakdown 8축 동적 바 + bonus 섹션 + Base Score + Category Bonus 표시
- 새 CSS: `.modal-bar-row`, `.modal-bar-track`, `.modal-bar-fill`, `.modal-section-header` 등

**테스트 (`test_scenarios.py`: 145 TC 유지):**
- TC-114: v7.0 → v7.1 메타 라벨 확인
- TC-127: `blog_analysis_score()` 3-tuple 반환 + v7.1 base_breakdown 8축 구조
- TC-128: 매장 연계 모드 → category 모드 + bonus_breakdown 존재 확인
- TC-129: 최상 지표 시 높은 점수 도달 확인

**설계 결정:**
- 새 pip 의존성 없음 (TF-IDF/프로필 파싱 순수 Python)
- 프로필 HTML 파싱: `buddyCnt` + "이웃 N" 패턴 2중 매칭
- 프로필 수집 max_workers=10 (블로그 HTML은 네이버 API 아님 → rate limit 별도)
- v7.0/v5/v4/v3 레거시 함수 삭제 없음 (하위 호환)
- DB 하위 호환: 모든 신규 컬럼 DEFAULT 0/NULL

### 28. GoldenScore v7.2: 포스팅 실력 기반 개편 + 전수 역검색 (2026-02-17)

**커밋:** `b6194c8`, `025aa4c`, `55ae63d`, `c475f8b`

**수정 파일:** `backend/scoring.py`, `backend/models.py`, `backend/db.py`, `backend/analyzer.py`, `backend/reporting.py`, `backend/blog_analyzer.py`, `backend/app.py`, `backend/test_scenarios.py`, `frontend/src/main.js` (9개)

**문제 (v7.1 진단, wnstjd878 단독 분석):**
- 네이버 최적블로그인데 C등급(41.7/100) 판정
- BlogAuthority(22점)가 이웃수/운영기간 등 조작 가능한 외형 지표에 의존
- SponsorFit(8점)이 단독 분석에 포함 (목적 불일치)
- ExposurePower(30점)가 단독 모드에서 데이터 2~3건으로 구조적 불리
- TopExposureProxy(10점)와 ExposurePower 데이터 중복 (인기순교차 이중 가산)
- GameDefense(0), QualityFloor(0) 표시 방식 — 0점이 나쁘게 보임

**점수 체계 변경 (8축 → 5축 + 3축 Bonus):**

| 축 | v7.1 | v7.2 | 변경 |
|----|------|------|------|
| ExposurePower | 30 (Base) | 22 (Base) | 축소 + 전수 역검색 강화 |
| BlogAuthority | 22 (Base) | → ContentAuthority 22 (Base) | 외형 → 포스팅 실력 기반 |
| RSSQuality | 18 (Base) | 22 (Base) | 상향 (글길이 7, Originality 6) |
| Freshness | 12 (Base) | 18 (Base) | 상향 (+간격안정성) |
| TopExposureProxy | 10 (Base) | → SearchPresence 16 (Base) | 중복 제거 → 검색 친화성 |
| SponsorFit | 8 (Base) | → SponsorBonus 8 (Bonus) | Base → Bonus 이동 |
| CategoryFit | 15 (Bonus) | 15 (Bonus) | 변경 없음 |
| CategoryExposure | 10 (Bonus) | 10 (Bonus) | 변경 없음 |
| GameDefense | -10 (Base) | -10 (Base) | 0일 때 숨김 |
| QualityFloor | +5 (Base) | +5 (Base) | 0일 때 숨김 |
| **Max Bonus** | **25** | **33** | SponsorBonus 이동으로 확대 |

**ContentAuthority v7.2 (0~22) — BlogAuthority 대체 (`scoring.py`, 5개 헬퍼):**
- `_compute_structure_maturity()`: 구조 성숙도 — 소제목(#)/단락/리스트 패턴 비율
- `_compute_info_density_consistency()`: 정보 밀도 — 평균 글자수 + 변동계수(일관성)
- `_compute_topic_expertise_accumulation()`: 주제 전문성 — 반복 키워드 비율 (전문가 패턴)
- `_compute_long_term_pattern()`: 장기 패턴 — 포스팅 주기 안정성
- `_compute_content_growth_trend()`: 성장 추이 — 최근 글 길이 vs 과거 글 길이 비교
- 5개 헬퍼 합산 → 22점 정규화

**SearchPresence v7.2 (0~16) — TopExposureProxy 대체 (`scoring.py`, 3개 헬퍼):**
- `_compute_search_friendly_titles()`: 검색 친화 제목 비율 (0~6) — 길이 10~50자, 키워드 2+개, 특수문자 3개 미만
- `_compute_post_date_spread()`: 포스팅 노출 수명 (0~5) — 최근/중기/장기 분포
- `_compute_keyword_coverage_v72()`: 키워드 커버리지 (0~5) — 고유 키워드 수

**전수 역검색 (blog_analyzer.py, 독립 분석 모드):**
- `extract_full_reverse_keywords()`: 3단계 키워드 추출
  - 1단계: 전체 포스트에서 빈도 2+ 단일 키워드 (최대 15개)
  - 2단계: 상위 6개 빈도 단어끼리 2-gram 조합 (C(6,2) = 최대 15개)
  - 3단계: 인접 바이그램 중 빈도 2+ (실제 제목 문맥 보존)
  - 총 15~25개 검색 가능 키워드 → 네이버 역검색
- 기존 7개 빈도 기반 → 15~25개 전수 역검색으로 확장
- 포스트 부족(5개 미만) 시 기존 방식 폴백

**SponsorBonus v7.2 (0~8) — Category Bonus로 이동:**
- 체험단경험(3): 10~40% sweet spot
- 퀄리티×체험단(3): 협찬 경험 + 글 충실도 조합
- 내돈내산 비율(2): 자연 리뷰 비율

**테스트 (`test_scenarios.py`: 145→158 TC):**
- TC-146: ContentAuthority v7.2 범위 + 포스팅 실력 > 빈 포스트
- TC-147: SearchPresence v7.2 범위 0~16
- TC-148: RSSQuality v7.2 범위 0~22
- TC-149: Freshness v7.2 범위 0~18
- TC-150: SponsorBonus v7.2 범위 0~8 + sweet>excess
- TC-151: golden_score_v72 범위 + 분별력
- TC-152: GameDefense/QualityFloor 0일 때 숨김
- TC-153: Category Bonus 최대 33 + SponsorBonus 포함
- TC-154: SponsorBonus 단독분석 시 미포함 (0점)
- TC-155: assign_grade_v72 등급 판정
- TC-156: v7.2 Base 정규화 검증 + analysis_mode
- TC-157: ContentAuthority 포스팅 실력 정규화
- TC-158: ExposurePower v7.2 범위 0~22

**wnstjd878 검증 결과:**

| 항목 | v7.1 | v7.2 (전수 역검색) |
|------|------|-------------------|
| 등급 | C (41.7) | **A (71.9)** |
| 검색 키워드 | 7개 | **24개** |
| 노출 키워드 | 2개 | **12개** |
| 1페이지 | 불명 | **11개** |
| EP | 13.2/30 | **16.5/22** |

**설계 결정:**
- 새 pip 의존성 없음 (ContentAuthority/SearchPresence 순수 Python)
- 전수 역검색: 2어절 문장조각 → 빈도 기반 단일 키워드 + 상위 빈도 2-gram 조합 (검색 가능성 보장)
- SponsorFit → Category Bonus 이동: 단독 분석에서 체험단 적합도 배제 (목적 분리)
- v7.1/v7.0 레거시 함수 삭제 없음 (하위 호환)
- DB 하위 호환: 기존 컬럼 변경 없음

### 29. GoldenScore v7.2 개편안 4대 미해결 이슈 수정 (2026-02-17)

**수정 파일:** `backend/scoring.py`, `backend/models.py`, `backend/db.py`, `backend/analyzer.py`, `backend/reporting.py`, `backend/blog_analyzer.py`, `backend/test_scenarios.py`, `frontend/src/main.js` (8개)

**4대 수정 항목:**

1. **EP 분모 분리 + 노출규모 신설 (`scoring.py`)**:
   - Sub-signal 재배분: SERP빈도(8→6) + 순위분포(8→6) + **노출규모(0→6, 신설)** + 다양성+인기순(2+4→4)
   - `reverse_appeared`, `reverse_total` 파라미터 추가: seed_rate / reverse_rate 별도 계산, `max(seed_rate, reverse_rate)` 채택
   - 노출규모: `top20_count = sum(1 for r in ranks if r <= 20)` 기반 절대 노출 수 반영

2. **ContentAuthority 주제깊이 로직 변경 (`scoring.py`)**:
   - `_compute_topic_expertise_accumulation()`: top1_ratio(집중도) → deep_topics(5+포스트) + medium_topics(3+) + themed_ratio
   - 다양한 주제에서 깊이 있는 포스팅을 하는 블로거 우대

3. **RSSQuality 이미지 보정 (`scoring.py`)**:
   - `avg_image_count` 파라미터 추가: `adjusted_len = richness_avg_len + (avg_image_count * 300)`
   - 이미지 위주 블로그의 짧은 텍스트 페널티 해소
   - `avg_image_count` 파이프라인 연결: models → DB → analyzer → reporting → golden_score_v72

4. **7단계 등급 체계 (`scoring.py`, `main.js`)**:
   - 5단계(S/A/B/C/D) → 7단계(S+/S/A/B+/B/C/D/F)
   - UI: 점수→등급 순서 변경, GRADE_COLORS에 S+/B+/F 추가
   - 태그 생성: S+/S/A → 고권위, D/F → 저권위

**데이터 파이프라인 확장:**
- `CandidateBlogger.avg_image_count` 필드 추가 (`models.py`)
- `bloggers` 테이블 `avg_image_count` 컬럼 마이그레이션 (`db.py`)
- RSS에서 `avg_image_count` 계산 (`analyzer.py`, `blog_analyzer.py`)
- `golden_score_v72()` + `blog_analysis_score()`: `reverse_appeared`, `reverse_total`, `avg_image_count` 파라미터 연결

**테스트:** 158/158 PASS (TC-155 7단계 등급 경계값 업데이트)

### 30. GoldenScore v7.2 BlogPower 6축 체계 — 프로필 크롤링 + EP Inference (2026-02-17)

**커밋:** `9738ee2` — feat: GoldenScore v7.2 BlogPower 6축 체계 — 프로필 크롤링 + EP Inference

**수정 파일:** `backend/scoring.py`, `backend/blog_analyzer.py`, `backend/models.py`, `backend/db.py`, `backend/analyzer.py`, `backend/reporting.py` (6개)

**문제 (v7.2 5축 진단):**
- 블로그 규모(총 포스트 수, 총 방문자 수, 구독자 수)를 평가하는 축이 없음
- ContentAuthority가 외형 지표 제거 후 포스팅 실력만 평가 → 블로그 자체의 파워/인지도 미반영
- ExposurePower가 검색 샘플링에 의존 → 큰 블로그가 우연히 안 잡히면 저평가

**점수 체계 변경 (5축 → 6축):**

| 축 | v7.2 Before | v7.2 After | 변경 |
|----|-------------|------------|------|
| ExposurePower | 22 | 18 | 축소 + EP Inference |
| ContentAuthority | 22 | 16 | 축소 (비례 스케일링) |
| RSSQuality | 22 | 14 | 축소 (비례 스케일링) |
| Freshness | 18 | 10 | 축소 (비례 스케일링) |
| SearchPresence | 16 | 17 | 미세 확대 |
| **BlogPower** | **-** | **25** | **신설** |
| **합계** | **100** | **100** | 유지 |

**BlogPower (0~25) — 4 sub-signal (`scoring.py`):**

| Sub-signal | 최대 | 계산 방식 |
|------------|------|-----------|
| 포스트 수 | 7점 | 30→1, 100→2, 300→3, 500→4, 1000→5, 2000→6, 3000+→7 |
| 방문자 수 | 7점 | 10K→1, 50K→2, 100K→3, 300K→4, 500K→5, 1M→6, 3M+→7 |
| 영향력 | 5점 | max(구독자 단계, 랭킹 백분위 단계) |
| 운영 지속성 | 6점 | blog_age_years × 활동 여부(최근 30일 포스팅) |

**EP Inference (`scoring.py`):**
- BlogPower ≥ 22 → EP 하한 16
- BlogPower ≥ 18 → EP 하한 10
- BlogPower ≥ 14 → EP 하한 6
- BlogPower ≥ 8 → EP 하한 3
- 의미: 큰 블로그인데 검색 샘플에서 우연히 안 잡힌 경우 보정

**프로필 크롤링 확장 (`blog_analyzer.py`):**
- `fetch_blog_profile()` 전면 재작성 (v7.2 BlogPower용):
  1. PostTitleListAsync.naver: `addDate` 파싱 (상대 날짜 "3시간 전"/"5일 전" + 절대 날짜 "2026. 2. 14." 모두 처리)
  2. 모바일 프로필 (m.blog.naver.com): `postCount`>`countPost`(폴백), `totalVisitorCount`, `subscriberCount`>`buddyCount`(폴백), `blogDirectoryOpenDate`
  3. PostTitleListAsync 마지막 페이지: `ceil(total_posts/5)` → 가장 오래된 `addDate` → 블로그 개설일 추정 (blog_age_years)
  4. 데스크톱 블로그 폴백: `buddyCnt` (이웃 수)
  5. RSS 폴백: 최오래된 포스트 날짜 → 블로그 개설일 추정
- 반환 dict: `total_posts`, `total_visitors`, `total_subscribers`, `blog_age_years`, `last_post_days_ago`, `ranking_percentile`

**데이터 파이프라인 (`models.py` → `db.py` → `analyzer.py` → `reporting.py`):**
- `CandidateBlogger`: 5개 필드 추가 — `total_posts`, `total_visitors`, `total_subscribers`, `ranking_percentile`, `blog_power`
- DB 마이그레이션: 5개 컬럼 `ALTER TABLE` (DEFAULT 0/100)
- `upsert_blogger()`: 5개 파라미터 추가
- `compute_tier_scores()`: 프로필에서 BlogPower 입력 데이터 추출 + `compute_blog_power()` 호출
- `get_top20_and_pool40()`: SQL SELECT + `golden_score_v72()` 호출에 BlogPower 필드 전달

**등급 라벨 변경:**
- S+ → '탁월' (was '최상위'), S → '우수' (was '탁월'), A → '양호' (was '우수'), B+ → '보통이상' (was '양호')

**테스트:** 158/158 PASS

### 31. 프로필 크롤링 수정 + 등급 중복 표시 제거 + 블로그 개설일 추정 (2026-02-17)

**커밋:** `5ecaf48` — fix: 프로필 크롤링 수정 + 등급 중복 표시 제거 + 블로그 개설일 추정

**수정 파일:** `backend/blog_analyzer.py`, `backend/reporting.py`, `backend/test_scenarios.py`, `frontend/src/main.js` (4개)

**프로필 크롤링 수정 (`blog_analyzer.py`):**
- 네이버 API 필드명 변경 대응: `countPost`→`postCount`, `buddyCount`→`subscriberCount` (우선 패턴 + 폴백)
- `addDate` 파싱 강화: 상대 날짜("3시간 전"→0일, "5일 전"→5일) + 절대 날짜("2026. 2. 14.") 모두 처리
- 블로그 개설일 추정: `total_posts`에서 마지막 페이지(`ceil(posts/5)`) 계산 → PostTitleListAsync에서 가장 오래된 `addDate` 파싱
- 결과: BlogPower 0~7점 → 20~25점으로 정상화 (goingleee: posts=1174, visitors=912K, subs=1236, age=12.1년)

**등급 중복 표시 제거 (`reporting.py`, `main.js`):**
- 문제: "61.5 B+ C" 처럼 v7.2 grade("B+")와 레거시 tier_grade("C")가 동시 표시
- 수정: 카드/리스트/모달에서 tier_grade 배지 완전 제거, v7.2 grade만 표시
- 고권위/저권위 레거시 태그 생성 코드 제거 (reporting.py)
- 모달: "블로그 권위 tier_grade" → "등급 v7.2_grade grade_label"

**테스트 (`test_scenarios.py`):**
- TC-114: 고권위/저권위 태그가 존재하지 **않음**을 검증 + v7.2 grade/grade_label 필드 존재 확인

**실측 결과 (제주시 맛집):**
| 블로거 | BlogPower | EP | CA | SP | FS | 등급 |
|--------|-----------|----|----|----|----|------|
| piil | 25.0 | 16.0 | 10.7 | 14.9 | 91.7 | A |
| jinju1469 | 22.0 | 16.0 | 11.8 | 14.9 | 90.3 | A |
| birdkiss78 | 25.0 | 16.0 | 10.0 | 14.9 | 88.9 | S |
| goingleee | 20.0 | 10.0 | 11.8 | 17.0 | 85.8 | A |

### 32. 리뷰 가이드 & 키워드 추천 엔진 통합 (2026-02-17)

**수정 파일:** `backend/guide_generator.py`, `backend/keywords.py`, `backend/app.py`, `frontend/index.html`, `frontend/src/main.js`, `frontend/src/style.css` (6개)

**guide_generator.py — 핵심 엔진 확장 (556→1230줄):**
- 신규 업종 4개 추가: **네일샵, 피부과, 인테리어, 꽃집** (기존 10 → 14개 템플릿)
- `INDUSTRY_KEYWORDS`: 14개 업종 + default (main_suffixes, sub_keywords, longtail, negative, hashtag_base)
- `FORBIDDEN_WORDS_DETAILED`: 업종별 상세 금지어 (forbidden/replacement/reason) + `_common` 공통
- `STRUCTURE_TEMPLATES`: 7개 업종 섹션별 글 구조 (heading/desc/img_min + tips + word_count)
- `COMPLIANCE_GUIDE`: 공정위 표시의무 구조화 데이터
- `SEO_GUIDE_DETAILED`: 6분야 상세 SEO 가이드
- 신규 함수 6개: `normalize_category()`, `generate_keyword_recommendation()`, `generate_hashtags()`, `get_forbidden_words_detailed()`, `get_structure_template()`, `get_supported_categories()`
- `generate_guide()` 확장: `sub_category` 파라미터 + 9섹션 `full_guide_text` + 7개 구조화 데이터 반환
  - 반환 추가: `keywords_3tier`, `structure_sections`, `forbidden_detailed`, `hashtags`, `compliance`, `seo_detailed`, `checklist`
  - 기존 반환 필드 하위 호환 유지

**keywords.py — 동의어 확장:**
- `CATEGORY_SYNONYMS`: 4개 신규 업종 매핑 (네일→네일샵, 피부과→피부과, 인테리어→인테리어, 꽃집→꽃집)
  - 기존 `"네일"→"미용"` → `"네일"→"네일샵"`, `"피부과"→"병원"` → `"피부과"→"피부과"` 분리
- `CATEGORY_HOLDOUT_MAP`, `CATEGORY_BROAD_MAP`, `REGION_POWER_MAP`: 4개 신규 업종 항목 추가

**app.py — API 확장:**
- `GET /api/stores/{id}/guide`: `sub_category` 쿼리 파라미터 추가
- `GET /api/guide/keywords/{category}?region=...&sub=...`: 3계층 키워드 독립 API (신규)
- `GET /api/guide/categories`: 지원 업종 목록 API (신규)

**프론트엔드 — 리치 가이드 뷰:**
- `index.html`: `#guide-area` 확장 — 리치 뷰 컨테이너 (키워드 칩, 글 구조 카드, 금지어 테이블, 해시태그, 체크리스트) + 리치/텍스트 뷰 토글
- `main.js`: `loadGuide()` 재작성 — 구조화 데이터 있으면 리치 뷰 렌더링, `_renderGuideRichView()` + `_fillKeywordTier()` 헬퍼 추가
- `style.css`: 리치 가이드 뷰 스타일 추가 — `.guide-rich-view`, `.guide-keyword-tier` (3계층 칩), `.guide-structure-card`, `.guide-forbidden-table`, `.guide-hashtag-area`, `.guide-checklist`, `.guide-view-toggle`

**검증:** 176/176 PASS (7개 검증 그룹: categories, keywords 14업종, 매장가이드 기존+확장, 동의어 12가지, 9섹션 포맷, SYNONYMS 정합성, HOLDOUT/BROAD/POWER_MAP)

### 33. GoldenScore v7.2.1 신뢰도 패치 — RQ/SP 보정 + Blogdex 통합 (2026-02-17)

**수정 파일:** `backend/scoring.py`, `backend/blog_analyzer.py`, `backend/test_scenarios.py` (3개)

**문제:** 블로그 파워가 낮은 소규모 블로그가 RSS 품질/검색 존재감 점수를 과대 받아 신뢰도 저하.
- BP < 10인 블로그가 텍스트 품질만으로 RQ 만점 획득 (시장 미검증)
- BP < 10인 블로그가 제목 SEO만으로 SP 고점 획득 (실제 검색 노출과 괴리)

**v7.2.1 패치 3건:**

1. **RssQuality 블로그 규모 보정 (`scoring.py`):**
   - `golden_score_v72()` 내 RQ 계산 후 scaleFactor 적용
   - BP ≥ 10 (최적 블로그): 보정 없음 → 점수 하락 없음
   - BP < 10 & 방문자 < 50K: scaleFactor 적용
     - 방문자 ≥ 30K → 0.9, ≥ 10K → 0.85, < 10K → 0.75
   - 의미: 블로그 규모가 작으면 "시장 미검증 품질"로 RQ 할인

2. **SearchPresence BP 기반 상한선 (`scoring.py`):**
   - `golden_score_v72()` 내 SP 계산 후 cap 적용
   - BP ≥ 10: 상한 17 (보정 없음)
   - BP 5~9: 상한 12
   - BP < 5: 상한 9
   - 의미: 소규모 블로그가 제목 SEO만으로 높은 존재감 점수 방지

3. **Blogdex 통합 (`blog_analyzer.py`):**
   - `fetch_blogdex_data(blogger_id)` 신규: blogdex.space 스크래핑
   - 등급 파싱: 최적4+~일반 (16단계)
   - 주제/전체 랭킹 백분위 (`ranking_percentile`)
   - 기본 통계 폴백: total_posts, total_visitors, total_subscribers, blog_age_years
   - `fetch_blog_profile()` 6번째 데이터 소스로 통합 (네이버 못 가져온 데이터 보충)

**테스트 (158→162 TC):**
- TC-159: RQ scaleFactor 검증 (높은 BP → 보정 없음, 낮은 BP → 20%+ 할인)
- TC-160: SP cap 검증 (BP<5 → cap 9, 높은 BP → cap 없음)
- TC-161: BP≥10일 때 RQ/SP 보정 미적용 확인
- TC-162: fetch_blogdex_data() 존재 + 안전 반환 (외부 서비스 불가 시에도 에러 없음)

**검증:** 162/162 PASS

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
