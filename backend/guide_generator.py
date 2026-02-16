"""
업종별 체험단 가이드 자동 생성 엔진

업종별 템플릿 기반으로 리뷰 구조, 사진 체크리스트,
키워드 배치 규칙, 금지어/대체표현, SEO 가이드를 포함한
가이드를 생성합니다.
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
            "완성된 안경 착용컷 (전면/측면)",
            "가격표 또는 할인 안내",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 계기로 방문했는지 자연스럽게 서술 (시력 변화, 안경 교체 등)", "word_count": "300~400자"},
            {"section": "핵심 경험", "guide": "검안 과정, 렌즈 안내, 안경테 선택 경험을 구체적으로 작성", "word_count": "500~600자"},
            {"section": "정보 정리", "guide": "가격대, 렌즈 종류, 소요 시간, 주차 정보 등을 깔끔하게 정리", "word_count": "400~500자"},
            {"section": "총평", "guide": "전체 만족도, 어떤 사람에게 소개하고 싶은지 명시", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역안경원", "#안경맞춤", "#검안", "#안경원후기", "#안경테"],
        "min_photos": 6,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["시술", "치료", "처방", "의료기기", "보험", "건강보험",
                           "가장", "최고", "최상", "100%", "완벽", "보장"],
        "alternative_words": {
            "시술": "피팅/조정",
            "치료": "관리/케어",
            "처방": "도수 측정",
            "의료기기": "시력 보정 기구",
            "가장": "특히/무엇보다",
            "최고": "인상적인",
            "보험": "지원 제도",
        },
        "forbidden_reason": "안경은 의료기기법 적용 품목으로, 의료행위 암시 표현 및 최상급 표현이 금지됩니다.",
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
            {"section": "방문 동기", "guide": "어떤 목적으로 방문했는지 (데이트, 작업, 모임 등)", "word_count": "300~400자"},
            {"section": "공간 소개", "guide": "외관, 내부 인테리어, 좌석 배치, 분위기 묘사", "word_count": "400~500자"},
            {"section": "메뉴 후기", "guide": "주문한 메뉴 맛 평가, 비주얼, 가격 대비 만족도", "word_count": "500~600자"},
            {"section": "종합 정보", "guide": "위치, 영업시간, 주차, 콘센트/와이파이, 누구와 가면 좋은지", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역카페", "#카페추천", "#분위기좋은카페", "#디저트카페", "#신상카페"],
        "min_photos": 7,
        "min_chars": 2000,
        "max_chars": 2500,
        "forbidden_words": ["가장", "최고", "강추", "꼭 가보세요"],
        "alternative_words": {
            "가장": "특히/무엇보다",
            "최고": "인상적인/눈에 띄는",
            "강추": "만족스러웠어요",
            "꼭 가보세요": "한번 방문해보셔도 좋을 것 같아요",
        },
        "forbidden_reason": "과도한 광고성/최상급 표현은 네이버 노출 제한 사유가 될 수 있습니다.",
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
            {"section": "방문 동기", "guide": "어떤 시술을 받으려 했는지, 고민 사항", "word_count": "300~400자"},
            {"section": "핵심 경험", "guide": "상담 내용, 시술 과정, 디자이너가 안내한 스타일 등 상세히", "word_count": "500~600자"},
            {"section": "정보 정리", "guide": "시술 가격, 소요 시간, 예약 방법, 주차 여부", "word_count": "400~500자"},
            {"section": "총평", "guide": "어떤 머리 고민이 있는 사람에게 소개하고 싶은지", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역미용실", "#헤어컬러", "#펌후기", "#미용실후기", "#헤어디자이너"],
        "min_photos": 6,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["가장", "최고", "강추"],
        "alternative_words": {
            "가장": "특히/무엇보다",
            "최고": "인상적인",
            "강추": "만족스러웠어요",
        },
        "forbidden_reason": "과도한 최상급 표현은 광고성 글로 분류될 수 있습니다.",
    },
    "음식점": {
        "photo_checklist": [
            "매장 외관 (간판 포함)",
            "매장 내부 인테리어",
            "대표 메뉴 클로즈업 (45도 각도, 자연광)",
            "사이드 메뉴 / 반찬",
            "전체 상차림 테이블 컷",
            "음식 단면/디테일 (고기 단면, 면 식감 등)",
            "메뉴판 또는 가격표",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 계기로 방문했는지 (소개, 검색, 재방문 등)", "word_count": "300~400자"},
            {"section": "매장 분위기", "guide": "외관, 내부 인테리어, 좌석 구성, 청결도", "word_count": "400~500자"},
            {"section": "메뉴 후기", "guide": "주문 메뉴, 맛 묘사, 양, 플레이팅을 솔직하게", "word_count": "600~800자"},
            {"section": "종합 정보", "guide": "가격 대비 만족도, 위치, 영업시간, 주차, 웨이팅 여부", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역맛집", "#맛집추천", "#점심추천", "#회식장소", "#맛집리뷰"],
        "min_photos": 8,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["가장", "최고", "강추", "꼭 가보세요"],
        "alternative_words": {
            "가장": "특히/무엇보다",
            "최고": "인상적인/눈에 띄는",
            "강추": "만족스러웠어요",
            "꼭 가보세요": "한번 방문해보셔도 좋을 것 같아요",
            "맛있는(과용)": "풍미가 좋은/감칠맛 나는/식감이 좋은",
        },
        "forbidden_reason": "과도한 광고성/최상급 표현은 네이버 노출 제한 사유가 될 수 있습니다.",
    },
    "병원": {
        "photo_checklist": [
            "병원 외관 (간판 포함)",
            "접수/대기실 전경",
            "진료실 또는 상담실",
            "진료 장비/시설",
            "진료 후 안내 장면",
            "주차장 또는 접근성 정보",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 증상/목적으로 방문했는지 (검진, 상담 등)", "word_count": "300~400자"},
            {"section": "병원 분위기", "guide": "접수 과정, 대기실, 청결도, 직원 응대", "word_count": "400~500자"},
            {"section": "진료 경험", "guide": "의료진 설명의 친절도, 대기 시간, 시설 (개인 경험으로 한정)", "word_count": "500~600자"},
            {"section": "종합 정보", "guide": "위치, 진료 시간, 주차, 예약 방법 (객관적 정보만)", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역병원", "#병원후기", "#건강검진", "#진료후기", "#의원후기"],
        "min_photos": 5,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["치료 효과 보장", "가격 할인", "이벤트", "타 병원 비교",
                           "의사 실력 평가", "부작용 없다", "100% 만족",
                           "가장", "최고", "완벽", "확실히"],
        "alternative_words": {
            "치료 효과 보장": "개인적인 경험입니다",
            "가격 할인": "직접 문의 안내",
            "의사 실력 평가": "친절하게 설명해주셨어요",
            "100% 만족": "개인적으로 만족스러웠습니다",
            "가장": "특히",
            "최고": "인상적인",
            "확실히": "분명히",
        },
        "forbidden_reason": "의료법에 따라 치료 효과 보장, 비교 광고, 과장 광고가 엄격히 금지됩니다.",
        "disclaimer": "이 글은 개인적인 경험을 바탕으로 작성되었으며, 의학적 효과는 개인마다 다를 수 있습니다.",
    },
    "치과": {
        "photo_checklist": [
            "치과 외관 (간판 포함)",
            "접수/대기실 전경",
            "진료실 또는 상담실",
            "진료 장비/시설",
            "진료 후 안내/설명 장면",
            "주차장 또는 접근성 정보",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 치과 고민으로 방문했는지 (검진, 스케일링, 교정 상담 등)", "word_count": "300~400자"},
            {"section": "병원 분위기", "guide": "접수, 대기실 청결도, 직원 응대, 긴장 완화 여부", "word_count": "400~500자"},
            {"section": "진료 경험", "guide": "의료진 설명, 시술 과정, 통증 정도 (개인 경험으로 한정)", "word_count": "500~600자"},
            {"section": "종합 정보", "guide": "위치, 진료 시간, 주차, 예약 방법, 비용 범위 (직접 문의 안내)", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역치과", "#치과후기", "#스케일링", "#임플란트후기", "#치과추천"],
        "min_photos": 5,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["치료 효과 보장", "가격 할인", "이벤트", "타 치과 비교",
                           "실력 평가", "부작용 없다", "100% 만족", "안 아파요",
                           "가장", "최고", "완벽"],
        "alternative_words": {
            "치료 효과 보장": "개인적인 경험입니다",
            "가격 할인": "직접 문의 안내",
            "실력 평가": "친절하게 설명해주셨어요",
            "안 아파요": "개인적으로 통증이 적었습니다",
            "가장": "특히",
            "최고": "인상적인",
        },
        "forbidden_reason": "의료법에 따라 치료 효과 보장, 비교 광고, 과장 광고가 엄격히 금지됩니다.",
        "disclaimer": "이 글은 개인적인 경험을 바탕으로 작성되었으며, 의학적 효과는 개인마다 다를 수 있습니다.",
    },
    "헬스장": {
        "photo_checklist": [
            "헬스장 외관",
            "운동 기구/시설 전경",
            "PT 트레이닝 장면",
            "락커룸/샤워실",
            "운동 전후 비교 (선택)",
            "가격표 또는 프로그램 안내",
        ],
        "review_structure": [
            {"section": "등록 동기", "guide": "어떤 운동 목표로 등록했는지 (다이어트, 근력, 재활 등)", "word_count": "300~400자"},
            {"section": "시설 소개", "guide": "운동기구, 공간, 탈의실, 청결도 등 상세히", "word_count": "400~500자"},
            {"section": "프로그램/PT", "guide": "PT 과정, 트레이너 응대, 프로그램 구성, 실제 운동 경험", "word_count": "500~600자"},
            {"section": "종합 정보", "guide": "가격(월/3개월/PT), 위치, 운영시간, 주차, 샤워실 여부", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역헬스장", "#PT추천", "#헬스장후기", "#운동", "#다이어트"],
        "min_photos": 6,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["다이어트 효과 보장", "몇 kg 감량", "체형 비하"],
        "alternative_words": {
            "다이어트 효과 보장": "꾸준히 하면 변화를 느낄 수 있을 것 같아요",
            "몇 kg 감량": "구체적 수치 대신 '눈에 띄는 변화'",
            "체형 비하": "긍정적 표현으로 대체",
        },
        "forbidden_reason": "구체적 감량 수치나 효과 보장은 허위/과장 광고에 해당할 수 있습니다.",
    },
    "학원": {
        "photo_checklist": [
            "학원 외관 (간판 포함)",
            "접수/로비 전경",
            "교실/강의실 내부",
            "교재 또는 커리큘럼 자료",
            "자습실/편의시설",
            "수강 안내 또는 가격표",
        ],
        "review_structure": [
            {"section": "등록 동기", "guide": "어떤 학습 목표로 등록했는지, 학원 선택 이유", "word_count": "300~400자"},
            {"section": "시설/환경", "guide": "교실, 자습실, 편의시설, 학습 분위기", "word_count": "400~500자"},
            {"section": "수업 경험", "guide": "커리큘럼, 교재, 강사 스타일, 관리 시스템", "word_count": "500~600자"},
            {"section": "종합 정보", "guide": "수강료 범위, 위치, 상담 방법, 어떤 학생에게 적합한지", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역학원", "#학원추천", "#학원후기", "#수업후기", "#공부"],
        "min_photos": 6,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["성적 향상 보장", "합격률", "1등", "학생 얼굴 노출"],
        "alternative_words": {
            "성적 향상 보장": "체계적인 커리큘럼이 인상적이었어요",
            "합격률": "직접 상담 시 확인 가능",
            "1등": "수업 집중도가 높았어요",
        },
        "forbidden_reason": "구체적 성적 수치나 합격률 보장은 과장 광고에 해당하며, 학생 초상권에 주의해야 합니다.",
    },
    "숙박": {
        "photo_checklist": [
            "숙소 외관 전경",
            "로비 또는 접수 공간",
            "객실 전체 전경",
            "침대/침구 클로즈업",
            "욕실/어메니티",
            "뷰/발코니 (해당 시)",
            "부대시설 (수영장, BBQ 등)",
            "조식 또는 간식 (해당 시)",
        ],
        "review_structure": [
            {"section": "방문 배경", "guide": "여행 목적, 예약 경위, 숙소 선택 이유", "word_count": "300~400자"},
            {"section": "객실 소개", "guide": "방 크기, 침구, 어메니티, 뷰, 청결도", "word_count": "500~600자"},
            {"section": "부대시설", "guide": "수영장, BBQ, 조식, 공용공간, 주차 등", "word_count": "400~500자"},
            {"section": "종합 정보", "guide": "가격대, 예약 방법, 체크인/아웃, 방음, 직원 응대", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역숙소", "#지역펜션", "#숙소추천", "#여행숙소", "#숙박후기"],
        "min_photos": 8,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["가장", "최고", "강추"],
        "alternative_words": {
            "가장": "특히/무엇보다",
            "최고": "인상적인",
            "강추": "만족스러웠어요",
        },
        "forbidden_reason": "최상급 표현은 과장 광고로 분류될 수 있습니다.",
    },
    "자동차": {
        "photo_checklist": [
            "정비소/세차장 외관",
            "접수/대기 공간",
            "작업 과정 (정비/세차)",
            "사용 장비/제품",
            "작업 완료 결과물",
            "가격표 또는 안내문",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 서비스가 필요했는지 (정비, 세차, 타이어 등)", "word_count": "300~400자"},
            {"section": "서비스 과정", "guide": "접수, 상담, 작업 과정, 소요 시간 등 상세히", "word_count": "500~600자"},
            {"section": "결과 만족도", "guide": "작업 결과, 품질, 가격 대비 만족도", "word_count": "400~500자"},
            {"section": "종합 정보", "guide": "위치, 영업시간, 가격대, 예약 방법, 주차", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역카센터", "#자동차정비", "#세차추천", "#타이어교체", "#정비후기"],
        "min_photos": 6,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["가장", "최고"],
        "alternative_words": {
            "가장": "특히",
            "최고": "인상적인",
        },
        "forbidden_reason": "최상급 표현은 과장 광고로 분류될 수 있습니다.",
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
        {"section": "방문 동기", "guide": "어떤 계기로 방문하게 되었는지 자연스럽게 서술", "word_count": "300~400자"},
        {"section": "핵심 경험", "guide": "서비스/상품의 핵심 경험을 구체적으로 작성", "word_count": "500~600자"},
        {"section": "정보 정리", "guide": "위치, 영업시간, 가격, 주차 등 실용 정보 정리", "word_count": "400~500자"},
        {"section": "총평", "guide": "어떤 사람/상황에 소개하고 싶은지 명시", "word_count": "300~400자"},
    ],
    "hashtag_examples": ["#지역매장", "#추천", "#후기", "#방문후기", "#체험"],
    "min_photos": 6,
    "min_chars": 2000,
    "max_chars": 3000,
    "forbidden_words": ["가장", "최고", "강추"],
    "alternative_words": {
        "가장": "특히/무엇보다",
        "최고": "인상적인",
        "강추": "만족스러웠어요",
    },
    "forbidden_reason": "최상급/과도한 광고성 표현은 노출 제한 사유가 될 수 있습니다.",
}


def _match_template(category: str) -> tuple[str, Dict[str, Any]]:
    """카테고리 텍스트를 분석하여 가장 적합한 템플릿 선택.
    반환: (template_key, template_dict)
    """
    cat_lower = category.strip().lower()

    # 치과는 병원과 별도 템플릿 (의료법은 같지만 세부 가이드 상이)
    keyword_map = {
        "치과": ["치과", "임플란트", "교정", "스케일링"],
        "안경원": ["안경", "렌즈", "안과", "안경원", "광학"],
        "카페": ["카페", "커피", "디저트", "베이커리", "빵집", "브런치"],
        "미용실": ["미용", "헤어", "네일", "뷰티", "살롱", "펌", "컬러", "피부관리"],
        "음식점": ["맛집", "음식", "식당", "레스토랑", "파스타", "피자", "치킨",
                  "고기", "삼겹살", "횟집", "초밥", "라멘", "국밥", "찌개",
                  "한식", "중식", "일식", "양식", "분식"],
        "병원": ["병원", "의원", "클리닉", "진료", "건강검진", "한의원", "피부과", "정형외과"],
        "헬스장": ["헬스", "피트니스", "필라테스", "요가", "pt", "크로스핏", "운동"],
        "학원": ["학원", "과외", "입시", "공부방", "어학원"],
        "숙박": ["숙박", "호텔", "펜션", "리조트", "게스트하우스", "모텔", "글램핑"],
        "자동차": ["자동차", "정비", "세차", "카센터", "타이어", "수리"],
    }

    for template_key, keywords in keyword_map.items():
        for kw in keywords:
            if kw in cat_lower:
                return template_key, TEMPLATES[template_key]

    return "default", DEFAULT_TEMPLATE


def generate_guide(
    region: str,
    category: str,
    store_name: str = "",
    address: str = "",
    main_keyword_override: str | None = None,
    sub_keywords: list[str] | None = None,
) -> Dict[str, Any]:
    """
    체험단 가이드 자동 생성

    Args:
        main_keyword_override: 노출 데이터 기반 메인 키워드 (있으면 우선 사용)
        sub_keywords: 노출 데이터 기반 서브 키워드 리스트

    Returns:
        {
            "store_name": str,
            "main_keyword": str,
            "title_rule": str,
            "body_rule": str,
            "review_structure": [...],
            "photo_checklist": [...],
            "keyword_placement": {...},
            "hashtag_examples": [...],
            "forbidden_words": [...],
            "alternative_words": {...},
            "seo_guide": {...},
            "full_guide_text": str,
        }
    """
    template_key, template = _match_template(category)

    # 메인 키워드: 노출 데이터 우선, 폴백으로 category 기반
    if main_keyword_override:
        main_keyword = main_keyword_override
    elif category:
        main_keyword = f"{region} {category}".strip()
    else:
        main_keyword = region

    store_label = store_name or main_keyword or region

    # 서브 키워드: 노출 데이터 우선, 폴백으로 category 기반
    if sub_keywords and len(sub_keywords) >= 2:
        sub_kw1 = sub_keywords[0]
        sub_kw2 = sub_keywords[1]
    elif sub_keywords and len(sub_keywords) == 1:
        sub_kw1 = sub_keywords[0]
        sub_kw2 = f"{main_keyword} 후기" if main_keyword != region else f"{region} 후기"
    elif category:
        sub_kw1 = f"{region} {category} 후기"
        sub_kw2 = f"{region} {category} 가격"
    else:
        sub_kw1 = f"{main_keyword} 후기" if main_keyword != region else f"{region} 후기"
        sub_kw2 = f"{main_keyword} 추천" if main_keyword != region else f"{region} 추천"

    # 키워드 배치 규칙
    keyword_placement = {
        "title": f"제목 앞 15자 이내에 '{main_keyword}' 배치",
        "body_intro": f"본문 초반 200자 이내에 '{main_keyword}' 1회 자연 삽입",
        "body_middle": "본문 중간부에 서브 키워드 (추천/후기/가격 등) 1~2회 배치",
        "hashtag": "마지막에 관련 해시태그 5~7개 배치",
    }

    # 해시태그: 지역명으로 치환 (공백 제거)
    region_nospace = region.replace(" ", "")
    hashtags = [tag.replace("지역", region_nospace) for tag in template["hashtag_examples"]]

    min_photos = template.get("min_photos", 6)
    min_chars = template.get("min_chars", 2000)
    max_chars = template.get("max_chars", 3000)
    forbidden = template.get("forbidden_words", [])
    alternatives = template.get("alternative_words", {})
    forbidden_reason = template.get("forbidden_reason", "")
    disclaimer = template.get("disclaimer", "")

    seo_guide = {
        "min_chars": min_chars,
        "max_chars": max_chars,
        "min_photos": min_photos,
        "subtitles": "3~4개 (소제목 활용)",
        "paragraph_length": "2~3문장 후 줄바꿈",
        "keyword_density": f"메인 키워드 5~6회, 서브 키워드 각 2~3회",
        "subtitle_keyword_rule": "전체 소제목 중 1개에만 키워드 포함",
        "max_word_frequency": "동일 단어 20회 초과 금지",
    }

    # ========================
    # 전체 가이드 텍스트 생성
    # ========================
    lines = []
    lines.append(f"[{store_label} 체험단 리뷰 가이드]")
    lines.append("")

    # --- 제목 ---
    lines.append("--- 제목 작성 규칙 ---")
    lines.append(f"- 제목 앞 15자 이내에 메인 키워드 '{main_keyword}' 포함")
    lines.append(f"- 예시: \"{main_keyword} 솔직 후기, {store_label} 방문 체험\"")
    lines.append("")

    # --- 본문 구조 ---
    lines.append(f"--- 본문 구조 ({len(template['review_structure'])}단락) ---")
    for i, section in enumerate(template["review_structure"], 1):
        wc = section.get("word_count", "")
        wc_hint = f" ({wc})" if wc else ""
        lines.append(f"{i}. [{section['section']}]{wc_hint}")
        lines.append(f"   {section['guide']}")
    lines.append("")

    # --- 키워드 배치 전략 ---
    lines.append("--- 키워드 배치 전략 ---")
    lines.append(f"  메인 키워드: '{main_keyword}'")
    lines.append(f"    - 본문 내 5~6회 (서론1, 본론2, 전환1, 결론1, 자연배치1)")
    lines.append(f"  서브 키워드1: '{sub_kw1}'")
    lines.append(f"    - 본문 내 2~3회 (본론1, 결론1)")
    lines.append(f"  서브 키워드2: '{sub_kw2}'")
    lines.append(f"    - 본문 내 2~3회 (본론1, 정보정리1)")
    lines.append(f"  소제목: 전체 3~4개 중 1개에만 키워드 포함")
    lines.append(f"  단어 빈도: 동일 단어 20회 초과 금지")
    lines.append(f"  해시태그: {' '.join(hashtags)}")
    lines.append("")

    # --- 사진 ---
    lines.append(f"--- 사진 체크리스트 (최소 {min_photos}장) ---")
    for i, photo in enumerate(template["photo_checklist"], 1):
        lines.append(f"  {i}. {photo}")
    lines.append("")

    # --- 금지어/대체표현 ---
    if forbidden:
        lines.append("--- 금지어 및 대체 표현 ---")
        if forbidden_reason:
            lines.append(f"  ({forbidden_reason})")
        for fw in forbidden:
            alt = alternatives.get(fw, "사용 금지")
            lines.append(f"  X {fw} -> O {alt}")
        lines.append("")

    # --- SEO 작성 가이드 ---
    lines.append("--- SEO 작성 가이드 ---")
    lines.append(f"- 글자 수: {min_chars:,}자 이상 {max_chars:,}자 이하")
    lines.append(f"- 이미지: 최소 {min_photos}장")
    lines.append("- 소제목: 3~4개 (H2/H3 활용)")
    lines.append("- 문단: 2~3문장 후 줄바꿈 (가독성)")
    lines.append("- 표/리스트: 1~2개 삽입 권장 (정보 정리)")
    lines.append("- 네이버 지도 링크 삽입 필수 (위치 정보 + SEO)")
    lines.append("- 메인 키워드를 본문에서 가장 많이 사용하도록 구성")
    lines.append("")

    # --- 공정위 표시의무 ---
    lines.append("--- 필수 광고 표기 (공정거래위원회 규정) ---")
    lines.append("- [필수] 본문 최상단(첫 문단)에 다음 문구 삽입:")
    lines.append(f'  "본 포스팅은 {store_label}에서 서비스를 제공받아 작성한 솔직한 후기입니다."')
    lines.append("- 제목에 [체험단] 또는 [협찬] 표기 권장")
    lines.append("- 해시태그에 #체험단 또는 #협찬 반드시 포함")
    lines.append("- 표시 위치: 스크롤 없이 바로 보이는 위치 (모바일 기준 첫 화면)")

    # 의료 업종 면책 문구
    if disclaimer:
        lines.append(f"- 면책 문구 추가: \"{disclaimer}\"")
    lines.append("")

    # --- 주의사항 ---
    lines.append("--- 주의사항 ---")
    lines.append("- 과도한 광고성 표현 지양 (솔직한 톤 유지)")
    lines.append("- 장점뿐 아니라 아쉬운 점도 자연스럽게 포함 (신뢰도 향상)")

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
        "forbidden_words": forbidden,
        "alternative_words": alternatives,
        "seo_guide": seo_guide,
        "full_guide_text": full_text,
    }
