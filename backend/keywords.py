from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class StoreProfile:
    region_text: str
    category_text: str = ""
    topic: Optional[str] = None
    place_url: Optional[str] = None
    store_name: Optional[str] = None
    address_text: Optional[str] = None

    # 주소 텍스트에서 토큰을 간단히 뽑아 쓰기(과적합 방지: 최대 2개)
    def address_tokens(self) -> list[str]:
        if not self.address_text:
            return []
        raw = self.address_text.replace(",", " ").replace("  ", " ")
        tokens = [t.strip() for t in raw.split() if t.strip()]
        # 너무 긴 토큰/숫자만 토큰 제거
        cleaned = []
        for t in tokens:
            if t.isdigit():
                continue
            if len(t) > 20:
                continue
            cleaned.append(t)
        # 앞쪽 2개만 사용(안정)
        return cleaned[:2]


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        x2 = " ".join(x.split())  # normalize spaces
        if not x2:
            continue
        if x2 in seen:
            continue
        seen.add(x2)
        out.append(x2)
    return out


# ========================
# 네이버 블로그 주제 → 실제 검색 쿼리 매핑
# 주제는 블로거의 글쓰기 분야이므로, 해당 분야에서 활동하는 블로거를 찾을 수 있는
# 실제 네이버 검색 키워드로 변환합니다.
# ========================
TOPIC_SEED_MAP: Dict[str, List[str]] = {
    # 엔터테인먼트·예술
    "문학·책": ["{r} 북카페", "{r} 서점 추천", "{r} 독서모임", "{r} 책방", "{r} 도서관", "{r} 독서", "{r} 북카페 추천"],
    "영화": ["{r} 영화관", "{r} 영화 추천", "{r} 영화 후기", "{r} CGV", "{r} 메가박스", "{r} 영화 리뷰", "{r} 시네마"],
    "미술·디자인": ["{r} 전시회", "{r} 미술관", "{r} 갤러리", "{r} 전시 후기", "{r} 아트", "{r} 미술", "{r} 갤러리 추천"],
    "공연·전시": ["{r} 공연", "{r} 전시회", "{r} 뮤지컬", "{r} 콘서트", "{r} 연극", "{r} 전시 후기", "{r} 공연 후기"],
    "음악": ["{r} 공연", "{r} 콘서트", "{r} 음악", "{r} 라이브", "{r} 공연장", "{r} 음악 카페", "{r} 버스킹"],
    "드라마": ["{r} 촬영지", "{r} 드라마 촬영지", "{r} 로케이션", "{r} 핫플", "{r} 가볼만한곳", "{r} 카페", "{r} 핫플레이스"],
    "스타·연예인": ["{r} 핫플", "{r} 맛집", "{r} 카페", "{r} 핫플레이스", "{r} 트렌드", "{r} 인스타", "{r} SNS 맛집"],
    "만화·애니": ["{r} 만화카페", "{r} 보드게임", "{r} 오락실", "{r} 방탈출", "{r} 게임방", "{r} 피규어샵", "{r} 취미"],
    "방송": ["{r} 핫플", "{r} 맛집", "{r} 카페", "{r} 촬영지", "{r} 트렌드", "{r} 방송 맛집", "{r} 핫플레이스"],

    # 생활·노하우·쇼핑
    "일상·생각": ["{r} 일상", "{r} 블로그", "{r} 가볼만한곳", "{r} 핫플", "{r} 나들이", "{r} 산책", "{r} 일상 기록"],
    "육아·결혼": ["{r} 키즈카페", "{r} 아이랑", "{r} 웨딩", "{r} 스튜디오", "{r} 육아", "{r} 아기 맛집", "{r} 키즈"],
    "반려동물": ["{r} 애견카페", "{r} 동물병원", "{r} 펫카페", "{r} 강아지 산책", "{r} 반려동물", "{r} 애견", "{r} 고양이카페"],
    "좋은글·이미지": ["{r} 일상", "{r} 블로그", "{r} 감성", "{r} 사진", "{r} 풍경", "{r} 힐링", "{r} 감성 카페"],
    "패션·미용": ["{r} 미용실", "{r} 네일", "{r} 패션", "{r} 뷰티", "{r} 헤어", "{r} 미용실 추천", "{r} 네일 추천"],
    "인테리어·DIY": ["{r} 인테리어", "{r} 가구", "{r} 소품샵", "{r} 인테리어 업체", "{r} 리모델링", "{r} 홈 인테리어", "{r} 가구 추천"],
    "요리·레시피": ["{r} 맛집", "{r} 맛집 추천", "{r} 카페", "{r} 베이커리", "{r} 요리", "{r} 쿠킹클래스", "{r} 레시피"],
    "상품리뷰": ["{r} 추천", "{r} 후기", "{r} 리뷰", "{r} 쇼핑", "{r} 제품 리뷰", "{r} 사용 후기", "{r} 가성비"],
    "원예·재배": ["{r} 꽃집", "{r} 플라워", "{r} 화원", "{r} 정원", "{r} 식물", "{r} 가드닝", "{r} 플라워카페"],

    # 취미·여가·여행
    "게임": ["{r} PC방", "{r} 보드게임", "{r} 방탈출", "{r} VR", "{r} 오락실", "{r} 게임방", "{r} 보드게임카페"],
    "스포츠": ["{r} 헬스장", "{r} 필라테스", "{r} 요가", "{r} 운동", "{r} 수영장", "{r} 클라이밍", "{r} PT"],
    "사진": ["{r} 사진", "{r} 출사", "{r} 스튜디오", "{r} 풍경", "{r} 포토존", "{r} 사진 명소", "{r} 사진관"],
    "자동차": ["{r} 카센터", "{r} 세차", "{r} 자동차 정비", "{r} 드라이브", "{r} 주유소", "{r} 타이어", "{r} 자동차"],
    "취미": ["{r} 원데이클래스", "{r} 공방", "{r} 취미", "{r} 체험", "{r} 핸드메이드", "{r} 클래스", "{r} 워크샵"],
    "국내여행": ["{r} 여행", "{r} 가볼만한곳", "{r} 관광", "{r} 숙소", "{r} 핫플", "{r} 여행코스", "{r} 관광명소"],
    "세계여행": ["{r} 여행", "{r} 가볼만한곳", "{r} 관광", "{r} 핫플", "{r} 맛집", "{r} 여행 후기", "{r} 관광지"],
    "맛집": ["{r} 맛집", "{r} 맛집 추천", "{r} 맛집 후기", "{r} 카페", "{r} 점심 추천", "{r} 데이트 맛집", "{r} 가성비 맛집"],

    # 지식·동향
    "IT·컴퓨터": ["{r} IT", "{r} 코워킹스페이스", "{r} 스타트업", "{r} 개발", "{r} IT 학원", "{r} 코워킹", "{r} 스터디카페"],
    "사회·정치": ["{r} 지역 소식", "{r} 동네 소식", "{r} 지역 행사", "{r} 축제", "{r} 커뮤니티", "{r} 지역 이슈", "{r} 뉴스"],
    "건강·의학": ["{r} 병원", "{r} 한의원", "{r} 약국", "{r} 건강검진", "{r} 클리닉", "{r} 병원 추천", "{r} 의원"],
    "비즈니스·경제": ["{r} 창업", "{r} 재테크", "{r} 부동산", "{r} 투자", "{r} 사무실", "{r} 코워킹스페이스", "{r} 상가"],
    "어학·외국어": ["{r} 어학원", "{r} 영어학원", "{r} 외국어", "{r} 학원 추천", "{r} 영어", "{r} 일본어", "{r} 중국어"],
    "교육·학문": ["{r} 학원", "{r} 학원 추천", "{r} 과외", "{r} 입시", "{r} 교육", "{r} 도서관", "{r} 스터디카페"],
}

# 음식 관련 주제 (GoldenScore CategoryFit에서 음식 업종으로 취급)
TOPIC_FOOD_SET = {"맛집", "요리·레시피"}

# 주제 → 가이드 템플릿 매칭 힌트
# (guide_generator.py의 _match_template에서 사용)
TOPIC_TEMPLATE_HINT: Dict[str, str] = {
    "맛집": "음식",
    "요리·레시피": "음식",
    "건강·의학": "병원",
    "스포츠": "헬스",
    "자동차": "자동차",
    "교육·학문": "학원",
    "어학·외국어": "학원",
    "패션·미용": "미용",
    "국내여행": "숙박",
    "세계여행": "숙박",
}


def is_topic_mode(profile: StoreProfile) -> bool:
    """주제 모드인지 확인: keyword 없이 topic만 있는 경우"""
    c = (profile.category_text or "").strip()
    t = (profile.topic or "").strip()
    return not c and bool(t) and t in TOPIC_SEED_MAP


# 카테고리 동의어 매핑: 다양한 입력 표현 → 표준 카테고리 키
# "커피전문점" → "카페", "삼겹살집" → "음식" 등 변형 입력 대응
CATEGORY_SYNONYMS = {
    "커피": "카페", "디저트": "카페", "베이커리": "카페", "빵집": "카페", "브런치": "카페",
    "맛집": "음식", "식당": "음식", "레스토랑": "음식", "치킨": "음식", "피자": "음식",
    "고기": "음식", "삼겹살": "음식", "횟집": "음식", "초밥": "음식", "라멘": "음식",
    "국밥": "음식", "찌개": "음식", "한식": "음식", "중식": "음식", "일식": "음식",
    "양식": "음식", "분식": "음식",
    "헤어": "미용", "네일": "미용", "뷰티": "미용", "살롱": "미용", "펌": "미용",
    "렌즈": "안경", "안과": "안경",
    "피트니스": "헬스", "필라테스": "헬스", "요가": "헬스", "크로스핏": "헬스",
    "의원": "병원", "클리닉": "병원", "피부과": "병원", "정형외과": "병원", "한의원": "병원",
    "임플란트": "치과", "교정": "치과",
    "호텔": "숙박", "펜션": "숙박", "리조트": "숙박", "게스트하우스": "숙박", "모텔": "숙박",
    "과외": "학원", "입시": "학원",
    "정비": "자동차", "세차": "자동차", "카센터": "자동차",
}


def resolve_category_key(category_text: str, category_map: dict) -> str | None:
    """카테고리 텍스트를 category_map의 키로 리졸브.
    1순위: 직접 substring 매칭 (기존 로직)
    2순위: 동의어 매핑을 통한 매칭
    """
    c_lower = category_text.strip().lower()

    # 1순위: 직접 매칭
    for key in category_map:
        if key in c_lower:
            return key

    # 2순위: 동의어 → 표준 키 변환 후 매칭
    for synonym, canonical in CATEGORY_SYNONYMS.items():
        if synonym in c_lower and canonical in category_map:
            return canonical

    return None


CATEGORY_HOLDOUT_MAP = {
    "안경": ["{r} 안경 맞추기", "{r} 렌즈 잘하는곳", "{r} 안경테 추천"],
    "카페": ["{r} 카페 분위기", "{r} 커피 맛집", "{r} 카페 데이트"],
    "미용": ["{r} 헤어 잘하는곳", "{r} 펌 잘하는곳", "{r} 미용실 가격"],
    "음식": ["{r} 맛집 솔직후기", "{r} 밥집 추천", "{r} 먹거리 추천"],
    "병원": ["{r} 병원 잘하는곳", "{r} 진료 후기", "{r} 의원 비교"],
    "헬스": ["{r} 헬스장 비교", "{r} PT 후기", "{r} 운동 추천"],
    "치과": ["{r} 치과 잘하는곳", "{r} 임플란트 후기", "{r} 치과 비교"],
}

DEFAULT_HOLDOUT_TEMPLATES = ["{r} {c} 잘하는곳", "{r} {c} 비교", "{r} 근처 {c}"]

# 주제 모드 전용 홀드아웃: seed 쿼리와 비중복인 검증용 키워드
TOPIC_HOLDOUT_TEMPLATES = ["{r} 추천", "{r} 후기", "{r} 블로그"]


def build_exposure_keywords(profile: StoreProfile) -> list[str]:
    """
    10개: 캐시 7개 + 홀드아웃 3개
    seed 쿼리와 겹치는 7개는 캐시 히트, 홀드아웃 3개는 확인편향 방지용 추가 검증
    - 키워드 모드: 업종별 홀드아웃
    - 주제 모드: TOPIC_SEED_MAP 기반 캐시 + 범용 홀드아웃
    - 지역만 모드: seed와 동일 7개 캐시 + 지역 홀드아웃 3개
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()
    t = (profile.topic or "").strip()

    # 주제 모드: TOPIC_SEED_MAP 기반
    if not c and t and t in TOPIC_SEED_MAP:
        templates = TOPIC_SEED_MAP[t]
        cached = [tmpl.format(r=r) for tmpl in templates][:7]
        holdout = [tmpl.format(r=r) for tmpl in TOPIC_HOLDOUT_TEMPLATES]
        return dedupe_keep_order(cached + holdout)[:10]

    if not c:
        # 지역만 모드: seed와 동일 7개 캐시 + 지역 홀드아웃 3개
        cached = [
            f"{r} 맛집",
            f"{r} 맛집 추천",
            f"{r} 맛집 후기",
            f"{r} 카페",
            f"{r} 카페 추천",
            f"{r} 핫플",
            f"{r} 블로그",
        ]
        holdout = [
            f"{r} 가볼만한곳",
            f"{r} 데이트",
            f"{r} 나들이",
        ]
        return dedupe_keep_order(cached + holdout)[:10]

    # 키워드 모드: 캐시 히트 키워드 7개 (seed와 동일)
    cached = [
        f"{r} {c}",
        f"{r} {c} 추천",
        f"{r} {c} 후기",
        f"{r} {c} 인기",
        f"{r} {c} 가격",
        f"{r} {c} 리뷰",
        f"{r} {c} 방문후기",
    ]

    # 업종별 홀드아웃 키워드 3개 (검증 정확도 향상)
    matched_key = resolve_category_key(c, CATEGORY_HOLDOUT_MAP)
    holdout_templates = CATEGORY_HOLDOUT_MAP.get(matched_key) if matched_key else None

    if holdout_templates is not None:
        holdout = [tmpl.format(r=r) for tmpl in holdout_templates]
    else:
        holdout = [tmpl.format(r=r, c=c) for tmpl in DEFAULT_HOLDOUT_TEMPLATES]

    return dedupe_keep_order(cached + holdout)[:10]


def build_seed_queries(profile: StoreProfile) -> list[str]:
    """
    후보수집용(7개):
    - 키워드 모드: 핵심 업종 특화 쿼리
    - 주제 모드: TOPIC_SEED_MAP에서 해당 주제의 실제 검색 쿼리 사용
    - 지역만 모드: 인기 카테고리 키워드로 광범위 수집
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()
    t = (profile.topic or "").strip()

    # 키워드 모드: 업종 특화 쿼리
    if c:
        q = [
            f"{r} {c}",
            f"{r} {c} 추천",
            f"{r} {c} 후기",
            f"{r} {c} 인기",
            f"{r} {c} 가격",
            f"{r} {c} 리뷰",
            f"{r} {c} 방문후기",
        ]
        return dedupe_keep_order(q)[:7]

    # 주제 모드: TOPIC_SEED_MAP에서 실제 검색 쿼리 변환
    if t and t in TOPIC_SEED_MAP:
        templates = TOPIC_SEED_MAP[t]
        return dedupe_keep_order([tmpl.format(r=r) for tmpl in templates])[:7]

    # 지역만 모드: 맛집 깊이 강화 + 인기 카테고리 + 블로그
    return dedupe_keep_order([
        f"{r} 맛집",
        f"{r} 맛집 추천",
        f"{r} 맛집 후기",
        f"{r} 카페",
        f"{r} 카페 추천",
        f"{r} 핫플",
        f"{r} 블로그",
    ])[:7]


# 지역 랭킹 파워 블로거 탐색용 쿼리 맵
# 자기 카테고리와 다른 인기 카테고리에서 상위노출되는 블로거 = 높은 블로그 지수
REGION_POWER_MAP = {
    "음식": ["{r} 카페 추천", "{r} 핫플", "{r} 데이트 코스"],
    "카페": ["{r} 맛집 추천", "{r} 핫플", "{r} 데이트 코스"],
    "미용": ["{r} 맛집 추천", "{r} 카페 추천", "{r} 핫플"],
    "안경": ["{r} 맛집 추천", "{r} 카페 추천", "{r} 핫플"],
    "헬스": ["{r} 맛집 추천", "{r} 카페 추천", "{r} 핫플"],
    "병원": ["{r} 맛집 추천", "{r} 카페 추천", "{r} 핫플"],
    "치과": ["{r} 맛집 추천", "{r} 카페 추천", "{r} 핫플"],
    "학원": ["{r} 맛집 추천", "{r} 카페 추천", "{r} 핫플"],
    "숙박": ["{r} 맛집 추천", "{r} 카페 추천", "{r} 핫플"],
    "자동차": ["{r} 맛집 추천", "{r} 카페 추천", "{r} 핫플"],
    "_default": ["{r} 맛집 추천", "{r} 카페 추천", "{r} 핫플"],
}

# 지역만 모드 전용: seed와 비중복 쿼리 (REGION_POWER_MAP에 넣으면 빈 문자열이 모든 키워드에 매칭됨)
_REGION_ONLY_POWER_TEMPLATES = ["{r} 가볼만한곳", "{r} 데이트 코스", "{r} 나들이"]


def build_region_power_queries(profile: StoreProfile) -> list[str]:
    """지역 랭킹 파워 블로거 탐색용 3개 쿼리.
    해당 업종과 다른 인기 카테고리에서 상위노출되는 블로거 = 높은 블로그 지수.
    예: 안경원 검색 시 → "강남 맛집 추천", "강남 카페 추천", "강남 핫플"
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()

    # 빈 카테고리: seed와 비중복 쿼리 사용
    if not c:
        return dedupe_keep_order([tmpl.format(r=r) for tmpl in _REGION_ONLY_POWER_TEMPLATES])[:3]

    matched_key = resolve_category_key(c, REGION_POWER_MAP)
    templates = REGION_POWER_MAP.get(matched_key) if matched_key else None

    if templates is None:
        templates = REGION_POWER_MAP["_default"]

    q = [tmpl.format(r=r) for tmpl in templates]
    return dedupe_keep_order(q)[:3]


CATEGORY_BROAD_MAP = {
    "안경": ["{r} 콘택트렌즈 추천", "{r} 시력교정", "{r} 눈건강", "{r} 렌즈 가격", "{r} 안과 추천"],
    "카페": ["{r} 디저트 맛집", "{r} 브런치 추천", "{r} 분위기좋은카페", "{r} 베이커리", "{r} 작업하기좋은곳"],
    "미용": ["{r} 헤어샵 추천", "{r} 펌 추천", "{r} 염색 잘하는곳", "{r} 네일아트", "{r} 뷰티샵"],
    "음식": ["{r} 맛집 추천", "{r} 점심 추천", "{r} 회식장소", "{r} 데이트 맛집", "{r} 가성비 맛집"],
    "병원": ["{r} 병원 추천", "{r} 건강검진", "{r} 의원 후기", "{r} 진료 잘하는곳", "{r} 클리닉"],
    "헬스": ["{r} 헬스장 추천", "{r} PT 추천", "{r} 필라테스", "{r} 요가", "{r} 운동"],
    "학원": ["{r} 학원 추천", "{r} 과외 추천", "{r} 영어학원", "{r} 수학학원", "{r} 입시"],
    "숙박": ["{r} 호텔 추천", "{r} 펜션 추천", "{r} 숙소 후기", "{r} 게스트하우스", "{r} 리조트"],
    "자동차": ["{r} 자동차 정비", "{r} 세차 추천", "{r} 카센터", "{r} 타이어 교체", "{r} 수리"],
    "치과": ["{r} 치과 추천", "{r} 임플란트 가격", "{r} 교정 후기", "{r} 치아미백", "{r} 스케일링"],
}

DEFAULT_BROAD = ["{r} 추천", "{r} 후기", "{r} 가볼만한곳", "{r} 인기", "{r} 가성비"]


def build_broad_queries(profile: StoreProfile) -> list[str]:
    """
    확장 풀용: 카테고리 인접 키워드 기반 (최대 5개)
    업종별 관련 키워드로 실질적 상위노출 블로거 포착
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip().lower()

    matched_key = resolve_category_key(c, CATEGORY_BROAD_MAP)
    selected = CATEGORY_BROAD_MAP.get(matched_key) if matched_key else None

    if selected is None:
        selected = DEFAULT_BROAD

    q = [tmpl.format(r=r) for tmpl in selected]
    return dedupe_keep_order(q)[:5]


def build_keyword_ab_sets(profile: StoreProfile) -> Dict[str, List[str]]:
    """
    A/B 키워드 세트 생성 — 폴백용 (정적 템플릿)
    실제 노출 데이터가 있으면 app.py에서 데이터 기반 A/B로 대체됨

    A세트 (상위노출용 5개): "지역+업종+추천/후기/가격/인기/리뷰" 패턴
    B세트 (플레이스/유입용 5개): "지역+업종+방문후기/가성비/예약/신상/전문" 패턴
    지역만/주제 모드: 인기 키워드 기반 A/B
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()
    t = (profile.topic or "").strip()

    # 주제 모드: TOPIC_SEED_MAP 기반 A/B
    if not c and t and t in TOPIC_SEED_MAP:
        templates = TOPIC_SEED_MAP[t]
        all_queries = [tmpl.format(r=r) for tmpl in templates]
        set_a = dedupe_keep_order(all_queries[:5])
        remaining = [q for q in all_queries[5:] if q not in set(set_a)]
        # 범용 확장 키워드로 B세트 채우기
        extra_b = [f"{r} 추천", f"{r} 후기", f"{r} 블로그", f"{r} 가볼만한곳", f"{r} 핫플"]
        set_b = dedupe_keep_order(remaining + extra_b)[:5]
        return {
            "set_a": set_a,
            "set_b": set_b,
            "set_a_label": "상위노출용 (블로그 노출 최적화)",
            "set_b_label": "범용 유입용 (네이버 유입)",
        }

    if not c:
        # 지역만 모드: 인기 키워드 기반 A/B
        set_a = dedupe_keep_order([
            f"{r} 맛집 추천",
            f"{r} 카페 추천",
            f"{r} 맛집 후기",
            f"{r} 핫플",
            f"{r} 가볼만한곳",
        ])[:5]
        set_b = dedupe_keep_order([
            f"{r} 데이트 코스",
            f"{r} 일상",
            f"{r} 블로그",
            f"{r} 나들이",
            f"{r} 여행",
        ])[:5]
        return {
            "set_a": set_a,
            "set_b": set_b,
            "set_a_label": "상위노출용 (블로그 노출 최적화)",
            "set_b_label": "범용 유입용 (네이버 유입)",
        }

    # 키워드 모드
    set_a = dedupe_keep_order([
        f"{r} {c} 추천",
        f"{r} {c} 후기",
        f"{r} {c} 가격",
        f"{r} {c} 인기",
        f"{r} {c} 리뷰",
    ])[:5]

    # B세트: A와 중복되지 않도록 (범용 검색 패턴만 사용)
    a_set = set(set_a)
    candidates_b = [
        f"{r} {c} 방문후기",
        f"{r} {c} 가성비",
        f"{r} {c} 예약",
        f"{r} {c} 신상",
        f"{r} {c} 전문",
        f"{r} {c} 가격대",
        f"{r} {c} 솔직후기",
    ]
    set_b = []
    for kw in candidates_b:
        kw_norm = " ".join(kw.split())
        if kw_norm not in a_set and kw_norm not in set_b:
            set_b.append(kw_norm)
        if len(set_b) >= 5:
            break

    return {
        "set_a": set_a,
        "set_b": set_b,
        "set_a_label": "상위노출용 (블로그 노출 최적화)",
        "set_b_label": "플레이스/유입용 (네이버 플레이스 유입)",
    }
