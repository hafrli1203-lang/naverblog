from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class StoreProfile:
    region_text: str
    category_text: str = ""
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


def build_exposure_keywords(profile: StoreProfile) -> list[str]:
    """
    10개: 캐시 7개 + 홀드아웃 3개
    seed 쿼리와 겹치는 7개는 캐시 히트, 홀드아웃 3개는 확인편향 방지용 추가 검증
    홀드아웃은 업종별로 실제 검색패턴에 맞게 동적 생성
    지역만 모드: seed와 동일 7개 캐시 + 지역 홀드아웃 3개
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()

    if not c:
        # 지역만 모드: seed와 동일 7개 캐시 + 지역 홀드아웃 3개
        cached = [
            f"{r} 맛집",
            f"{r} 맛집 추천",
            f"{r} 카페",
            f"{r} 카페 추천",
            f"{r} 핫플",
            f"{r} 가볼만한곳",
            f"{r} 블로그",
        ]
        holdout = [
            f"{r} 맛집 후기",
            f"{r} 데이트",
            f"{r} 일상",
        ]
        return dedupe_keep_order(cached + holdout)[:10]

    # 캐시 히트 키워드 7개 (seed와 동일)
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
    후보수집용(7개): 핵심 업종 특화 쿼리만
    상호명/주소 토큰 쿼리 제거 (자기참조 방지, 신규 블로거 수집)
    지역만 모드: 인기 카테고리 키워드로 광범위 수집
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()

    if not c:
        # 지역만 모드: 인기 카테고리 키워드로 광범위 수집
        return dedupe_keep_order([
            f"{r} 맛집",
            f"{r} 맛집 추천",
            f"{r} 카페",
            f"{r} 카페 추천",
            f"{r} 핫플",
            f"{r} 가볼만한곳",
            f"{r} 블로그",
        ])[:7]

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


def build_region_power_queries(profile: StoreProfile) -> list[str]:
    """지역 랭킹 파워 블로거 탐색용 3개 쿼리.
    해당 업종과 다른 인기 카테고리에서 상위노출되는 블로거 = 높은 블로그 지수.
    예: 안경원 검색 시 → "강남 맛집 추천", "강남 카페 추천", "강남 핫플"
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()

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
    A/B 키워드 세트 생성 (중복 0개 보장)

    A세트 (상위노출용 5개): "지역+업종+추천/후기/가격/인기/리뷰" 패턴
    B세트 (플레이스/유입용 5개): "지역+업종+예약/주차/위치/영업시간/가격표" 패턴
    지역만 모드: 인기 키워드 기반 A/B
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()

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
