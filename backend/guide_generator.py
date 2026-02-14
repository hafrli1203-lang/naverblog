"""
업종별 체험단 가이드 자동 생성 엔진

업종별 템플릿 기반으로 리뷰 구조, 사진 체크리스트,
키워드 배치 규칙을 포함한 가이드를 생성합니다.
"""
from __future__ import annotations
from typing import Dict, List, Any


# ========================
# 업종별 템플릿 정의
# ========================

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "안경원": {
        "photo_checklist": [
            "매장 외관 (간판 포함)",
            "검안/시력 측정 장비",
            "상담 장면 (렌즈 선택)",
            "안경 피팅/조정 과정",
            "완성된 안경 착용컷",
            "가격표 또는 할인 안내",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 계기로 방문했는지 자연스럽게 서술 (시력 변화, 안경 교체 등)"},
            {"section": "핵심 경험", "guide": "검안 과정, 렌즈 추천, 안경테 선택 경험을 구체적으로 작성"},
            {"section": "정보 정리", "guide": "가격대, 렌즈 종류, 소요 시간, 주차 정보 등을 깔끔하게 정리"},
            {"section": "추천 대상", "guide": "어떤 사람에게 추천하는지 명시 (학생, 직장인, 난시 등)"},
        ],
        "hashtag_examples": ["#지역안경원", "#안경추천", "#안경맞춤", "#검안", "#안경원추천"],
    },
    "카페": {
        "photo_checklist": [
            "매장 외관 전경",
            "인테리어 / 좌석 배치",
            "시그니처 메뉴 클로즈업",
            "디저트 / 사이드 메뉴",
            "음료 들고 찍은 분위기 컷",
            "메뉴판 또는 가격표",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 목적으로 방문했는지 (데이트, 작업, 모임 등)"},
            {"section": "핵심 경험", "guide": "주문한 메뉴 맛 평가, 인테리어 분위기, 서비스 경험"},
            {"section": "정보 정리", "guide": "위치, 영업시간, 주차, 가격대, 콘센트/와이파이 여부"},
            {"section": "추천 대상", "guide": "누구와 가면 좋을지, 어떤 상황에 추천하는지"},
        ],
        "hashtag_examples": ["#지역카페", "#카페추천", "#분위기좋은카페", "#디저트카페", "#신상카페"],
    },
    "미용실": {
        "photo_checklist": [
            "매장 외관",
            "시술 전 상담 모습",
            "시술 과정 (커트/컬러/펌)",
            "시술 후 비포&애프터",
            "스타일링 완성 셀카",
            "가격표 또는 이벤트 안내",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 시술을 받으려 했는지, 고민 사항"},
            {"section": "핵심 경험", "guide": "상담 내용, 시술 과정, 디자이너 추천 스타일 등 상세히"},
            {"section": "정보 정리", "guide": "시술 가격, 소요 시간, 예약 방법, 주차 여부"},
            {"section": "추천 대상", "guide": "어떤 머리 고민이 있는 사람에게 좋은지"},
        ],
        "hashtag_examples": ["#지역미용실", "#헤어컬러", "#펌추천", "#미용실추천", "#헤어디자이너"],
    },
    "음식점": {
        "photo_checklist": [
            "매장 외관 (간판 포함)",
            "매장 내부 인테리어",
            "대표 메뉴 클로즈업",
            "사이드 메뉴 / 반찬",
            "먹는 장면 또는 숟가락 컷",
            "메뉴판 또는 가격표",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 계기로 방문했는지 (소개, 검색, 재방문 등)"},
            {"section": "핵심 경험", "guide": "주문 메뉴, 맛 평가, 양, 서비스 경험을 솔직하게"},
            {"section": "정보 정리", "guide": "위치, 영업시간, 주차, 가격대, 웨이팅 여부"},
            {"section": "추천 대상", "guide": "어떤 모임/상황에 좋은지 (가족, 회식, 데이트 등)"},
        ],
        "hashtag_examples": ["#지역맛집", "#맛집추천", "#점심추천", "#회식장소", "#맛집리뷰"],
    },
}

# 기본 템플릿
DEFAULT_TEMPLATE: Dict[str, Any] = {
    "photo_checklist": [
        "매장 외관 (간판 포함)",
        "매장 내부 전경",
        "핵심 서비스/상품 사진",
        "이용 과정 또는 체험 장면",
        "마무리/완성 사진",
        "가격표 또는 안내문",
    ],
    "review_structure": [
        {"section": "방문 동기", "guide": "어떤 계기로 방문하게 되었는지 자연스럽게 서술"},
        {"section": "핵심 경험", "guide": "서비스/상품의 핵심 경험을 구체적으로 작성"},
        {"section": "정보 정리", "guide": "위치, 영업시간, 가격, 주차 등 실용 정보 정리"},
        {"section": "추천 대상", "guide": "어떤 사람/상황에 추천하는지 명시"},
    ],
    "hashtag_examples": ["#지역매장", "#추천", "#후기", "#방문후기", "#체험"],
}


def _match_template(category: str) -> Dict[str, Any]:
    """카테고리 텍스트를 분석하여 가장 적합한 템플릿 선택"""
    cat_lower = category.strip().lower()

    keyword_map = {
        "안경원": ["안경", "렌즈", "안과", "안경원"],
        "카페": ["카페", "커피", "디저트", "베이커리", "빵집"],
        "미용실": ["미용", "헤어", "네일", "뷰티", "살롱", "펌", "컬러"],
        "음식점": ["맛집", "음식", "식당", "레스토랑", "파스타", "피자", "치킨",
                  "고기", "삼겹살", "횟집", "초밥", "라멘", "국밥", "찌개",
                  "한식", "중식", "일식", "양식", "분식"],
    }

    for template_key, keywords in keyword_map.items():
        for kw in keywords:
            if kw in cat_lower:
                return TEMPLATES[template_key]

    return DEFAULT_TEMPLATE


def generate_guide(
    region: str,
    category: str,
    store_name: str = "",
    address: str = "",
) -> Dict[str, Any]:
    """
    체험단 가이드 자동 생성

    Returns:
        {
            "title_rule": str,
            "body_rule": str,
            "review_structure": [...],
            "photo_checklist": [...],
            "keyword_placement": {...},
            "hashtag_examples": [...],
            "full_guide_text": str,
        }
    """
    template = _match_template(category)

    main_keyword = f"{region} {category}".strip()
    store_label = store_name or f"{region} {category}"

    # 키워드 배치 규칙
    keyword_placement = {
        "title": f"제목 앞 15자 이내에 '{main_keyword}' 배치",
        "body_intro": f"본문 초반 200자 이내에 '{main_keyword}' 1회 자연 삽입",
        "body_middle": "본문 중간부에 서브 키워드 (추천/후기/가격 등) 1~2회 배치",
        "hashtag": "마지막에 관련 해시태그 5~7개 배치",
    }

    # 해시태그: 지역명으로 치환
    hashtags = [tag.replace("지역", region) for tag in template["hashtag_examples"]]

    # 전체 가이드 텍스트 생성
    lines = []
    lines.append(f"[{store_label} 체험단 리뷰 가이드]")
    lines.append("")
    lines.append(f"--- 제목 작성 규칙 ---")
    lines.append(f"- 제목 앞 15자 이내에 메인 키워드 '{main_keyword}' 포함")
    lines.append(f"- 예시: \"{main_keyword} 솔직 후기, {store_label} 방문 체험\"")
    lines.append("")
    lines.append(f"--- 본문 구조 (4단락) ---")
    for i, section in enumerate(template["review_structure"], 1):
        lines.append(f"{i}. [{section['section']}]")
        lines.append(f"   {section['guide']}")
    lines.append("")
    lines.append(f"--- 키워드 배치 ---")
    lines.append(f"- 본문 초반 200자 이내: '{main_keyword}' 1회 자연 삽입")
    lines.append(f"- 본문 중간: 서브 키워드 (추천/후기/가격 등) 1~2회")
    lines.append(f"- 해시태그: {' '.join(hashtags)}")
    lines.append("")
    lines.append(f"--- 사진 체크리스트 ({len(template['photo_checklist'])}장) ---")
    for i, photo in enumerate(template["photo_checklist"], 1):
        lines.append(f"  {i}. {photo}")
    lines.append("")
    lines.append("--- 필수 광고 표기 (공정거래위원회 규정) ---")
    lines.append("- 본문 상단 또는 하단에 다음 문구 필수 삽입:")
    lines.append('  "업체로부터 제품/서비스를 제공받아 작성한 솔직한 리뷰입니다."')
    lines.append("- 해시태그에 #체험단 또는 #협찬 반드시 포함")
    lines.append("")
    lines.append("--- 주의사항 ---")
    lines.append("- 과도한 광고성 표현 지양 (솔직한 톤 유지)")
    lines.append("- 장점뿐 아니라 아쉬운 점도 자연스럽게 포함 (신뢰도 향상)")
    lines.append("- 사진 최소 6장 이상 권장")
    lines.append("- 본문 1,000자 이상 2,500자 이하 권장")
    lines.append("- 네이버 지도 링크 삽입 필수 (위치 정보 제공 + SEO 효과)")
    lines.append("- 메인 키워드를 본문에서 가장 많이 사용하도록 구성")

    full_text = "\n".join(lines)

    return {
        "store_name": store_label,
        "main_keyword": main_keyword,
        "title_rule": keyword_placement["title"],
        "body_rule": keyword_placement["body_intro"],
        "review_structure": template["review_structure"],
        "photo_checklist": template["photo_checklist"],
        "keyword_placement": keyword_placement,
        "hashtag_examples": hashtags,
        "full_guide_text": full_text,
    }
