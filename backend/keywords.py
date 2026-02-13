from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class StoreProfile:
    region_text: str
    category_text: str
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


def build_exposure_keywords(profile: StoreProfile) -> list[str]:
    """
    7개 고정: 카테고리 4 + 의도 3(체험단/협찬 1개 포함)
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()

    # 카테고리 4
    k = [
        f"{r} {c}",
        f"{r} {c} 추천",
        f"{r} {c} 후기",
        f"{r} {c} 전문",
    ]

    # 의도 3
    k += [
        f"{r} {c} 모임",
        f"{r} {c} 주차",
        f"{r} {c} 협찬",
    ]

    return dedupe_keep_order(k)[:7]


def build_seed_queries(profile: StoreProfile) -> list[str]:
    """
    후보수집용(최대 10개): 카테고리 특화 쿼리
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()
    tokens = profile.address_tokens()
    sname = (profile.store_name or "").strip()

    q = [
        f"{r} {c}",
        f"{r} {c} 추천",
        f"{r} {c} 후기",
        f"{r} {c} 인기",
        f"{r} {c} 방문후기",
        f"{r} {c} 신상",
        f"{r} {c} 가성비",
        f"{r} {c} 모임",
        f"{r} {c} 주차",
        f"{r} {c} 협찬",
    ]

    extra = []
    if tokens:
        extra.append(f"{tokens[0]} {c}")
        if len(tokens) > 1:
            extra.append(f"{tokens[1]} {c}")
    if sname and tokens:
        extra.append(f"{sname} {tokens[0]} 후기")

    q = dedupe_keep_order(q + extra)
    return q[:10]


def build_broad_queries(profile: StoreProfile) -> list[str]:
    """
    확장 풀용: 카테고리 무관, 지역 기반 상위노출 블로거 포착 (최대 5개)
    블로그 지수가 높아 어떤 키워드든 상위노출 가능한 사람을 찾는다.
    """
    r = profile.region_text.strip()

    q = [
        f"{r} 맛집 추천",
        f"{r} 가볼만한곳",
        f"{r} 블로그 체험단",
        f"{r} 데이트",
        f"{r} 핫플",
    ]

    return dedupe_keep_order(q)[:5]


def build_keyword_ab_sets(profile: StoreProfile) -> Dict[str, List[str]]:
    """
    A/B 키워드 세트 생성 (중복 0개 보장)

    A세트 (상위노출용 5개): "지역+업종+추천/후기/가격/인기/리뷰" 패턴
    B세트 (플레이스/유입용 5개): "지역+업종+예약/주차/위치/영업시간/가격표" 패턴
    """
    r = profile.region_text.strip()
    c = profile.category_text.strip()

    set_a = dedupe_keep_order([
        f"{r} {c} 추천",
        f"{r} {c} 후기",
        f"{r} {c} 가격",
        f"{r} {c} 인기",
        f"{r} {c} 리뷰",
    ])[:5]

    # B세트: A와 중복되지 않도록
    a_set = set(set_a)
    candidates_b = [
        f"{r} {c} 예약",
        f"{r} {c} 주차",
        f"{r} {c} 위치",
        f"{r} {c} 영업시간",
        f"{r} {c} 가격표",
        f"{r} {c} 메뉴",
        f"{r} {c} 전화번호",
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
