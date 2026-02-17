"""
업종별 체험단 가이드 자동 생성 엔진

업종별 템플릿 기반으로 리뷰 구조, 사진 체크리스트,
키워드 배치 규칙, 금지어/대체표현, SEO 가이드를 포함한
가이드를 생성합니다.

v2.0: 3계층 키워드 추천, 섹션별 글 구조 가이드, 동적 해시태그,
      상세 SEO 가이드, 공정위 표시의무, 모바일 최적화 체크리스트,
      14개 업종 + default 지원
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional


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
    # === 4개 신규 업종 ===
    "네일샵": {
        "photo_checklist": [
            "매장 외관",
            "네일 시술 전 손/발 상태",
            "시술 과정 (디자인 선택/시술)",
            "완성된 네일 클로즈업 (여러 각도)",
            "네일 컬러/디자인 샘플",
            "가격표 또는 메뉴판",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 네일을 받고 싶었는지, 디자인 레퍼런스", "word_count": "300~400자"},
            {"section": "시술 경험", "guide": "상담, 디자인 추천, 시술 과정, 꼼꼼함 정도 상세히", "word_count": "500~600자"},
            {"section": "완성도 평가", "guide": "마감 퀄리티, 지속력, 가격 대비 만족도", "word_count": "400~500자"},
            {"section": "종합 정보", "guide": "위치, 예약 방법, 가격대, 소요 시간, 주차 여부", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역네일", "#네일아트", "#네일샵추천", "#젤네일", "#네일후기"],
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
    "피부과": {
        "photo_checklist": [
            "병원 외관 (간판 포함)",
            "접수/대기실 전경",
            "상담실 또는 시술실",
            "시술 장비/시설",
            "시술 전후 비교 (허가 시, 개인 경험)",
            "주차장 또는 접근성 정보",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 피부 고민으로 방문했는지 (여드름, 미백, 탄력 등)", "word_count": "300~400자"},
            {"section": "상담 경험", "guide": "의료진 상담 내용, 시술 추천 과정, 설명 친절도", "word_count": "400~500자"},
            {"section": "시술 경험", "guide": "시술 과정, 통증 정도, 다운타임, 관리 안내 (개인 경험으로 한정)", "word_count": "500~600자"},
            {"section": "종합 정보", "guide": "위치, 진료 시간, 주차, 예약 방법, 비용 범위 (직접 문의 안내)", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역피부과", "#피부과후기", "#피부관리", "#피부시술", "#피부과추천"],
        "min_photos": 5,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["치료 효과 보장", "가격 할인", "이벤트", "타 병원 비교",
                           "부작용 없다", "100% 만족", "확실한 효과",
                           "가장", "최고", "완벽"],
        "alternative_words": {
            "치료 효과 보장": "개인적인 경험입니다",
            "가격 할인": "직접 문의 안내",
            "확실한 효과": "개인적으로 만족스러웠어요",
            "가장": "특히",
            "최고": "인상적인",
        },
        "forbidden_reason": "의료법에 따라 치료 효과 보장, 비교 광고, 과장 광고가 엄격히 금지됩니다.",
        "disclaimer": "이 글은 개인적인 경험을 바탕으로 작성되었으며, 의학적 효과는 개인마다 다를 수 있습니다.",
    },
    "인테리어": {
        "photo_checklist": [
            "시공 전 현장 사진",
            "시공 과정 (중간 단계)",
            "완성된 공간 전체 전경",
            "디테일 컷 (마감, 소재, 조명)",
            "가구/소품 배치 후 사진",
            "시공 업체 명함 또는 안내문",
        ],
        "review_structure": [
            {"section": "의뢰 동기", "guide": "어떤 공간을 어떻게 바꾸고 싶었는지, 업체 선택 이유", "word_count": "300~400자"},
            {"section": "상담/시공 과정", "guide": "견적, 디자인 상담, 시공 기간, 소통 방식 상세히", "word_count": "500~600자"},
            {"section": "완성도 평가", "guide": "마감 퀄리티, 디자인 만족도, 가격 대비 만족도", "word_count": "400~500자"},
            {"section": "종합 정보", "guide": "위치, 시공 범위, 예산 범위, A/S 정책", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역인테리어", "#인테리어후기", "#리모델링", "#집꾸미기", "#시공후기"],
        "min_photos": 8,
        "min_chars": 2000,
        "max_chars": 3000,
        "forbidden_words": ["가장", "최고", "강추", "최저가"],
        "alternative_words": {
            "가장": "특히/무엇보다",
            "최고": "인상적인",
            "강추": "만족스러웠어요",
            "최저가": "합리적인 가격",
        },
        "forbidden_reason": "최상급/최저가 표현은 과장 광고로 분류될 수 있습니다.",
    },
    "꽃집": {
        "photo_checklist": [
            "매장 외관 전경",
            "매장 내부 (꽃 진열 모습)",
            "주문한 꽃다발/화분 클로즈업",
            "포장/래핑 디테일",
            "꽃을 든 분위기 컷",
            "가격표 또는 메뉴판",
        ],
        "review_structure": [
            {"section": "방문 동기", "guide": "어떤 목적으로 꽃을 구매했는지 (선물, 인테리어, 이벤트 등)", "word_count": "300~400자"},
            {"section": "매장 분위기", "guide": "꽃 종류 다양성, 진열 상태, 매장 청결도, 향기", "word_count": "400~500자"},
            {"section": "상품 후기", "guide": "주문한 꽃다발/화분의 퀄리티, 가격, 신선도", "word_count": "500~600자"},
            {"section": "종합 정보", "guide": "위치, 영업시간, 가격대, 배달 가능 여부, 주차", "word_count": "300~400자"},
        ],
        "hashtag_examples": ["#지역꽃집", "#꽃다발", "#꽃집추천", "#플라워샵", "#꽃선물"],
        "min_photos": 6,
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


# ========================
# 3계층 키워드 추천 데이터
# ========================

INDUSTRY_KEYWORDS: Dict[str, Dict[str, Any]] = {
    "안경원": {
        "main_suffixes": ["추천", "후기", "가격", "잘하는곳"],
        "sub_keywords": ["검안", "안경테", "렌즈", "시력검사", "도수측정", "누진렌즈", "블루라이트"],
        "longtail": ["안경 맞추기 전 알아야 할 것", "안경테 얼굴형별 추천", "렌즈 종류 비교"],
        "negative": ["시술", "치료", "처방", "의료기기"],
        "hashtag_base": ["안경원", "안경맞춤", "검안", "안경원후기", "안경테", "렌즈추천"],
    },
    "카페": {
        "main_suffixes": ["추천", "후기", "데이트", "분위기"],
        "sub_keywords": ["디저트", "브런치", "커피", "케이크", "베이커리", "라떼", "아메리카노"],
        "longtail": ["데이트하기 좋은 카페", "작업하기 좋은 카페", "디저트 맛집 카페"],
        "negative": ["가장", "최고", "강추"],
        "hashtag_base": ["카페추천", "분위기좋은카페", "디저트카페", "신상카페", "카페투어"],
    },
    "미용실": {
        "main_suffixes": ["추천", "후기", "잘하는곳", "가격"],
        "sub_keywords": ["커트", "펌", "염색", "헤어컬러", "볼륨매직", "다운펌", "클리닉"],
        "longtail": ["펌 잘하는 미용실", "남자 커트 잘하는 곳", "염색 색상 추천"],
        "negative": ["가장", "최고", "강추"],
        "hashtag_base": ["미용실추천", "헤어컬러", "펌후기", "미용실후기", "헤어디자이너"],
    },
    "음식점": {
        "main_suffixes": ["추천", "후기", "맛집", "가격"],
        "sub_keywords": ["점심", "저녁", "회식", "데이트", "가성비", "코스요리", "런치메뉴"],
        "longtail": ["데이트 맛집 추천", "회식 장소 추천", "가성비 좋은 맛집"],
        "negative": ["가장", "최고", "강추", "꼭 가보세요"],
        "hashtag_base": ["맛집추천", "맛집후기", "점심추천", "회식장소", "맛집리뷰"],
    },
    "병원": {
        "main_suffixes": ["추천", "후기", "잘하는곳", "진료"],
        "sub_keywords": ["건강검진", "진료", "상담", "예약", "야간진료", "주말진료"],
        "longtail": ["건강검진 잘하는 병원", "야간 진료 가능한 병원", "내과 추천"],
        "negative": ["치료 효과 보장", "최고", "완벽", "확실히"],
        "hashtag_base": ["병원추천", "병원후기", "건강검진", "진료후기", "의원후기"],
    },
    "치과": {
        "main_suffixes": ["추천", "후기", "잘하는곳", "가격"],
        "sub_keywords": ["스케일링", "임플란트", "교정", "미백", "충치치료", "사랑니"],
        "longtail": ["임플란트 잘하는 치과", "치아교정 비용 비교", "스케일링 후기"],
        "negative": ["치료 효과 보장", "최고", "안 아파요"],
        "hashtag_base": ["치과추천", "치과후기", "스케일링", "임플란트후기", "치아교정"],
    },
    "헬스장": {
        "main_suffixes": ["추천", "후기", "가격", "PT"],
        "sub_keywords": ["PT", "필라테스", "요가", "크로스핏", "다이어트", "운동", "트레이너"],
        "longtail": ["PT 잘하는 헬스장", "여성 전용 헬스장", "1:1 PT 추천"],
        "negative": ["다이어트 효과 보장", "몇 kg 감량"],
        "hashtag_base": ["헬스장추천", "PT추천", "헬스장후기", "운동", "다이어트"],
    },
    "학원": {
        "main_suffixes": ["추천", "후기", "가격", "비교"],
        "sub_keywords": ["커리큘럼", "강사", "수업", "시간표", "입시", "자습실"],
        "longtail": ["수학 학원 추천", "영어 학원 비교", "입시 학원 후기"],
        "negative": ["성적 향상 보장", "합격률", "1등"],
        "hashtag_base": ["학원추천", "학원후기", "수업후기", "공부", "교육"],
    },
    "숙박": {
        "main_suffixes": ["추천", "후기", "예약", "가격"],
        "sub_keywords": ["호텔", "펜션", "리조트", "조식", "수영장", "뷰", "객실"],
        "longtail": ["가성비 좋은 숙소", "오션뷰 호텔 추천", "커플 펜션 추천"],
        "negative": ["가장", "최고", "강추"],
        "hashtag_base": ["숙소추천", "호텔후기", "펜션추천", "여행숙소", "숙박후기"],
    },
    "자동차": {
        "main_suffixes": ["추천", "후기", "가격", "잘하는곳"],
        "sub_keywords": ["정비", "세차", "타이어", "엔진오일", "수리", "광택", "코팅"],
        "longtail": ["세차 잘하는 곳", "타이어 교체 가격", "엔진오일 교체 주기"],
        "negative": ["가장", "최고"],
        "hashtag_base": ["카센터", "자동차정비", "세차추천", "타이어교체", "정비후기"],
    },
    "네일샵": {
        "main_suffixes": ["추천", "후기", "가격", "잘하는곳"],
        "sub_keywords": ["젤네일", "네일아트", "손톱케어", "발톱케어", "매니큐어", "패디큐어"],
        "longtail": ["네일아트 잘하는 곳", "젤네일 디자인 추천", "웨딩 네일 추천"],
        "negative": ["가장", "최고", "강추"],
        "hashtag_base": ["네일추천", "네일아트", "젤네일", "네일후기", "네일샵추천"],
    },
    "피부과": {
        "main_suffixes": ["추천", "후기", "가격", "잘하는곳"],
        "sub_keywords": ["레이저", "필링", "보톡스", "필러", "여드름", "기미", "피부관리"],
        "longtail": ["여드름 잘 보는 피부과", "기미 레이저 후기", "피부과 시술 추천"],
        "negative": ["치료 효과 보장", "최고", "완벽"],
        "hashtag_base": ["피부과추천", "피부과후기", "피부관리", "피부시술", "레이저시술"],
    },
    "인테리어": {
        "main_suffixes": ["추천", "후기", "업체", "비용"],
        "sub_keywords": ["리모델링", "시공", "견적", "마감", "셀프인테리어", "욕실", "주방"],
        "longtail": ["아파트 인테리어 비용", "욕실 리모델링 후기", "원룸 인테리어 추천"],
        "negative": ["가장", "최고", "최저가"],
        "hashtag_base": ["인테리어추천", "인테리어후기", "리모델링", "집꾸미기", "시공후기"],
    },
    "꽃집": {
        "main_suffixes": ["추천", "후기", "가격", "배달"],
        "sub_keywords": ["꽃다발", "화분", "화환", "드라이플라워", "꽃바구니", "플라워레슨"],
        "longtail": ["생일 꽃다발 추천", "개업 화환 가격", "플라워 레슨 후기"],
        "negative": ["가장", "최고", "강추"],
        "hashtag_base": ["꽃집추천", "꽃다발", "플라워샵", "꽃선물", "꽃배달"],
    },
    "default": {
        "main_suffixes": ["추천", "후기", "가격", "리뷰"],
        "sub_keywords": ["방문", "체험", "서비스", "이용"],
        "longtail": ["솔직 후기", "방문 체험", "가격 비교"],
        "negative": ["가장", "최고", "강추"],
        "hashtag_base": ["추천", "후기", "방문후기", "체험", "리뷰"],
    },
}


# ========================
# 업종별 상세 금지어 (forbidden/replacement/reason 구조)
# ========================

FORBIDDEN_WORDS_DETAILED: Dict[str, List[Dict[str, str]]] = {
    "_common": [
        {"forbidden": "가장", "replacement": "특히/무엇보다", "reason": "최상급 표현은 과장 광고로 분류될 수 있습니다"},
        {"forbidden": "최고", "replacement": "인상적인/눈에 띄는", "reason": "최상급 표현은 과장 광고로 분류될 수 있습니다"},
        {"forbidden": "강추", "replacement": "만족스러웠어요", "reason": "과도한 추천 표현은 광고성 글로 분류됩니다"},
        {"forbidden": "100%", "replacement": "대부분/많은 경우", "reason": "절대적 수치 표현은 허위 광고에 해당할 수 있습니다"},
        {"forbidden": "완벽", "replacement": "만족스러운/훌륭한", "reason": "과장 표현은 신뢰도를 낮춥니다"},
        {"forbidden": "꼭 가보세요", "replacement": "한번 방문해보셔도 좋을 것 같아요", "reason": "강요적 표현은 광고성 글로 분류됩니다"},
    ],
    "병원": [
        {"forbidden": "치료 효과 보장", "replacement": "개인적인 경험입니다", "reason": "의료법 위반 (효과 보장 금지)"},
        {"forbidden": "부작용 없다", "replacement": "개인적으로 불편함이 적었어요", "reason": "의료법 위반 (부작용 부정 금지)"},
        {"forbidden": "타 병원 비교", "replacement": "개인적인 선택 이유 서술", "reason": "의료법 위반 (비교 광고 금지)"},
        {"forbidden": "의사 실력 평가", "replacement": "친절하게 설명해주셨어요", "reason": "의료인 평가는 주관적이며 분쟁 소지"},
    ],
    "치과": [
        {"forbidden": "치료 효과 보장", "replacement": "개인적인 경험입니다", "reason": "의료법 위반 (효과 보장 금지)"},
        {"forbidden": "안 아파요", "replacement": "개인적으로 통증이 적었습니다", "reason": "통증 부정은 오해를 유발할 수 있습니다"},
        {"forbidden": "타 치과 비교", "replacement": "개인적인 선택 이유 서술", "reason": "의료법 위반 (비교 광고 금지)"},
    ],
    "피부과": [
        {"forbidden": "치료 효과 보장", "replacement": "개인적인 경험입니다", "reason": "의료법 위반 (효과 보장 금지)"},
        {"forbidden": "확실한 효과", "replacement": "개인적으로 만족스러웠어요", "reason": "효과 보장 표현은 의료법 위반"},
        {"forbidden": "부작용 없다", "replacement": "개인적으로 불편함이 적었어요", "reason": "의료법 위반 (부작용 부정 금지)"},
    ],
    "헬스장": [
        {"forbidden": "다이어트 효과 보장", "replacement": "꾸준히 하면 변화를 느낄 수 있을 것 같아요", "reason": "구체적 효과 보장은 허위 광고"},
        {"forbidden": "몇 kg 감량", "replacement": "눈에 띄는 변화", "reason": "구체적 수치는 개인차가 크므로 허위 광고 우려"},
    ],
    "학원": [
        {"forbidden": "성적 향상 보장", "replacement": "체계적인 커리큘럼이 인상적이었어요", "reason": "성적 보장은 과장 광고"},
        {"forbidden": "합격률", "replacement": "직접 상담 시 확인 가능", "reason": "합격률 표기는 검증 어려움"},
        {"forbidden": "학생 얼굴 노출", "replacement": "초상권 보호 필요", "reason": "초상권/개인정보 보호 의무"},
    ],
    "안경원": [
        {"forbidden": "시술", "replacement": "피팅/조정", "reason": "안경은 의료행위가 아닌 기구 피팅입니다"},
        {"forbidden": "처방", "replacement": "도수 측정", "reason": "의료행위 암시 표현 금지 (의료기기법)"},
        {"forbidden": "의료기기", "replacement": "시력 보정 기구", "reason": "법적 정의와 일상 표현 구분"},
    ],
}


# ========================
# 섹션별 글 구조 템플릿
# ========================

STRUCTURE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "음식점": {
        "sections": [
            {"heading": "방문 동기", "desc": "어떤 계기로 방문했는지 자연스럽게 서술", "img_min": 1},
            {"heading": "매장 분위기", "desc": "외관, 내부 인테리어, 청결도를 사진과 함께", "img_min": 2},
            {"heading": "메뉴 후기", "desc": "주문한 메뉴별 맛, 양, 가격을 상세히", "img_min": 3},
            {"heading": "종합 정보", "desc": "위치, 영업시간, 주차, 가격 정리", "img_min": 1},
        ],
        "tips": ["음식 사진은 45도 각도 + 자연광이 가장 좋습니다", "메뉴 1개당 최소 1장의 클로즈업 사진"],
        "word_count": {"min": 2000, "max": 3000},
    },
    "카페": {
        "sections": [
            {"heading": "방문 동기", "desc": "어떤 목적으로 방문했는지 (데이트, 작업 등)", "img_min": 1},
            {"heading": "공간 소개", "desc": "외관, 인테리어, 좌석 배치, 분위기", "img_min": 2},
            {"heading": "메뉴 후기", "desc": "주문한 메뉴 맛, 비주얼, 가성비", "img_min": 2},
            {"heading": "종합 정보", "desc": "위치, 주차, 와이파이, 콘센트 등", "img_min": 1},
        ],
        "tips": ["음료 + 디저트 조합샷이 인기 있습니다", "감성적인 분위기 컷 1장 필수"],
        "word_count": {"min": 2000, "max": 2500},
    },
    "미용실": {
        "sections": [
            {"heading": "방문 동기", "desc": "어떤 시술을 받으려 했는지, 고민 사항", "img_min": 1},
            {"heading": "시술 과정", "desc": "상담, 시술, 디자이너 안내 등 상세히", "img_min": 2},
            {"heading": "비포&애프터", "desc": "시술 전후 비교 사진과 후기", "img_min": 2},
            {"heading": "종합 정보", "desc": "가격, 소요시간, 예약 방법 등", "img_min": 1},
        ],
        "tips": ["비포&애프터는 같은 조명/각도에서 촬영", "헤어 디테일 컷 (앞/옆/뒤)"],
        "word_count": {"min": 2000, "max": 3000},
    },
    "병원": {
        "sections": [
            {"heading": "방문 동기", "desc": "증상/목적 서술 (개인 경험으로 한정)", "img_min": 1},
            {"heading": "병원 분위기", "desc": "접수, 대기실, 청결도, 직원 응대", "img_min": 2},
            {"heading": "진료 경험", "desc": "의료진 설명, 대기 시간, 시설 (개인 경험)", "img_min": 1},
            {"heading": "종합 정보", "desc": "위치, 시간, 주차, 예약 (객관적 정보)", "img_min": 1},
        ],
        "tips": ["진료실 촬영은 반드시 허가 후", "의료진 얼굴 노출 주의"],
        "word_count": {"min": 2000, "max": 3000},
    },
    "네일샵": {
        "sections": [
            {"heading": "방문 동기", "desc": "원하는 네일 디자인, 레퍼런스 설명", "img_min": 1},
            {"heading": "시술 경험", "desc": "상담, 디자인 추천, 시술 과정, 꼼꼼함", "img_min": 2},
            {"heading": "완성도 평가", "desc": "마감 퀄리티, 지속력, 만족도", "img_min": 2},
            {"heading": "종합 정보", "desc": "위치, 예약, 가격, 소요 시간", "img_min": 1},
        ],
        "tips": ["완성된 네일은 자연광에서 여러 각도로 촬영", "시술 전 손 상태도 함께 촬영"],
        "word_count": {"min": 2000, "max": 3000},
    },
    "인테리어": {
        "sections": [
            {"heading": "의뢰 동기", "desc": "공간 변화 목적, 업체 선택 이유", "img_min": 1},
            {"heading": "시공 과정", "desc": "견적, 디자인 상담, 시공 기간, 소통", "img_min": 3},
            {"heading": "완성도 평가", "desc": "마감 퀄리티, 디자인 만족도", "img_min": 3},
            {"heading": "종합 정보", "desc": "예산 범위, A/S, 추천 대상", "img_min": 1},
        ],
        "tips": ["시공 전/중/후 같은 각도에서 비교샷 촬영", "디테일 마감(코너, 타일 등) 클로즈업"],
        "word_count": {"min": 2000, "max": 3000},
    },
    "꽃집": {
        "sections": [
            {"heading": "방문 동기", "desc": "꽃 구매 목적 (선물, 인테리어 등)", "img_min": 1},
            {"heading": "매장 분위기", "desc": "꽃 종류, 진열, 향기, 청결도", "img_min": 2},
            {"heading": "상품 후기", "desc": "꽃다발/화분 퀄리티, 포장, 가격", "img_min": 2},
            {"heading": "종합 정보", "desc": "위치, 영업시간, 배달, 가격대", "img_min": 1},
        ],
        "tips": ["자연광에서 꽃 색감이 가장 잘 나옵니다", "포장 디테일과 전체 사이즈감을 함께 촬영"],
        "word_count": {"min": 2000, "max": 3000},
    },
}


# ========================
# 공정위 표시의무 구조화
# ========================

COMPLIANCE_GUIDE: Dict[str, Any] = {
    "placement": {
        "primary": "본문 최상단 (첫 문단, 스크롤 없이 보이는 위치)",
        "secondary": "제목에 [체험단] 또는 [협찬] 표기 권장",
    },
    "required_text": "본 포스팅은 {store}에서 서비스를 제공받아 작성한 솔직한 후기입니다.",
    "hashtag_required": ["#체험단", "#협찬"],
    "rules": [
        "광고임을 명확하게 표시 (모바일 기준 첫 화면에 노출)",
        "경제적 대가 사실을 숨기거나 축소하지 않기",
        "장점뿐 아니라 아쉬운 점도 자연스럽게 포함 (신뢰도 향상)",
        "추천인 코드/링크 포함 시 이해관계 명시",
    ],
    "medical_disclaimer": "이 글은 개인적인 경험을 바탕으로 작성되었으며, 의학적 효과는 개인마다 다를 수 있습니다.",
}


# ========================
# 상세 SEO 가이드 (6분야)
# ========================

SEO_GUIDE_DETAILED: Dict[str, List[str]] = {
    "title": [
        "제목 앞 15자 이내에 메인 키워드 배치",
        "제목 길이: 20~40자 (너무 길면 잘림)",
        "특수문자 최소화 (네이버 검색 노출에 불리)",
        "숫자 포함 시 클릭률 상승 (예: 'TOP 5', '3가지')",
    ],
    "body_keyword": [
        "메인 키워드: 본문 내 5~6회 자연 배치",
        "서브 키워드: 각 2~3회 자연 배치",
        "키워드 밀도: 전체 글자 수의 1~2% 이내",
        "동일 단어 20회 초과 금지 (키워드 스터핑)",
        "소제목 3~4개 중 1개에만 키워드 포함",
    ],
    "structure": [
        "소제목(H2/H3): 3~4개 활용",
        "문단: 2~3문장 후 줄바꿈 (가독성)",
        "표/리스트: 1~2개 삽입 권장 (정보 정리용)",
        "인용구: 핵심 문구 강조 시 활용",
    ],
    "image": [
        "이미지 ALT 텍스트에 키워드 포함",
        "이미지당 설명 텍스트 2~3줄 배치",
        "첫 이미지는 본문 시작 전 또는 직후에 배치",
        "네이버 지도 링크 삽입 필수 (위치 정보 + SEO)",
    ],
    "mobile": [
        "모바일 가독성: 한 줄에 15~20자 이내",
        "이미지 비율: 가로형(16:9 또는 4:3) 권장",
        "광고 표시: 모바일 첫 화면에 노출되어야 함",
        "스크롤 깊이: 핵심 정보를 상단에 배치",
    ],
    "video": [
        "동영상 포함 시 체류 시간 증가 (SEO 효과)",
        "15~30초 짧은 클립 권장",
        "동영상 설명에 키워드 포함",
    ],
}


# ========================
# 카테고리 정규화
# ========================

_CATEGORY_NORMALIZE_MAP: Dict[str, str] = {
    "안경": "안경원", "렌즈": "안경원", "안과": "안경원", "광학": "안경원",
    "커피": "카페", "디저트": "카페", "베이커리": "카페", "빵집": "카페", "브런치": "카페",
    "미용": "미용실", "헤어": "미용실", "뷰티": "미용실", "살롱": "미용실", "펌": "미용실", "컬러": "미용실",
    "맛집": "음식점", "음식": "음식점", "식당": "음식점", "레스토랑": "음식점",
    "의원": "병원", "클리닉": "병원", "한의원": "병원", "정형외과": "병원",
    "임플란트": "치과", "교정": "치과", "스케일링": "치과",
    "헬스": "헬스장", "피트니스": "헬스장", "필라테스": "헬스장", "요가": "헬스장", "pt": "헬스장",
    "과외": "학원", "입시": "학원", "어학원": "학원",
    "호텔": "숙박", "펜션": "숙박", "리조트": "숙박", "게스트하우스": "숙박", "모텔": "숙박", "글램핑": "숙박",
    "정비": "자동차", "세차": "자동차", "카센터": "자동차", "타이어": "자동차",
    "네일": "네일샵", "네일아트": "네일샵", "젤네일": "네일샵",
    "피부관리": "피부과", "에스테틱": "피부과", "피부시술": "피부과",
    "리모델링": "인테리어", "시공": "인테리어",
    "플라워샵": "꽃집", "꽃가게": "꽃집", "플라워": "꽃집", "화원": "꽃집",
}


def normalize_category(category: str) -> str:
    """카테고리 텍스트를 정규화된 업종명으로 변환.
    직접 매칭 → 부분 매칭 → 동의어 매칭 → 원본 반환
    """
    cat = category.strip()
    cat_lower = cat.lower()

    # 직접 매칭 (TEMPLATES 키)
    all_keys = set(TEMPLATES.keys()) | {"default"}
    if cat in all_keys:
        return cat

    # 부분 매칭
    for key in TEMPLATES:
        if key in cat_lower:
            return key

    # 동의어 매칭
    for synonym, canonical in _CATEGORY_NORMALIZE_MAP.items():
        if synonym in cat_lower:
            return canonical

    return cat


def _match_template(category: str) -> tuple[str, Dict[str, Any]]:
    """카테고리 텍스트를 분석하여 가장 적합한 템플릿 선택.
    반환: (template_key, template_dict)
    """
    cat_lower = category.strip().lower()

    keyword_map = {
        "치과": ["치과", "임플란트", "교정", "스케일링"],
        "피부과": ["피부과", "피부시술", "에스테틱", "피부관리"],
        "안경원": ["안경", "렌즈", "안과", "안경원", "광학"],
        "카페": ["카페", "커피", "디저트", "베이커리", "빵집", "브런치"],
        "네일샵": ["네일", "네일아트", "젤네일", "매니큐어", "패디큐어"],
        "미용실": ["미용", "헤어", "뷰티", "살롱", "펌", "컬러"],
        "음식점": ["맛집", "음식", "식당", "레스토랑", "파스타", "피자", "치킨",
                  "고기", "삼겹살", "횟집", "초밥", "라멘", "국밥", "찌개",
                  "한식", "중식", "일식", "양식", "분식"],
        "병원": ["병원", "의원", "클리닉", "진료", "건강검진", "한의원", "정형외과"],
        "헬스장": ["헬스", "피트니스", "필라테스", "요가", "pt", "크로스핏", "운동"],
        "학원": ["학원", "과외", "입시", "공부방", "어학원"],
        "숙박": ["숙박", "호텔", "펜션", "리조트", "게스트하우스", "모텔", "글램핑"],
        "자동차": ["자동차", "정비", "세차", "카센터", "타이어", "수리"],
        "인테리어": ["인테리어", "리모델링", "시공"],
        "꽃집": ["꽃집", "플라워", "화원", "꽃가게", "플라워샵"],
    }

    for template_key, keywords in keyword_map.items():
        for kw in keywords:
            if kw in cat_lower:
                return template_key, TEMPLATES[template_key]

    return "default", DEFAULT_TEMPLATE


# ========================
# 3계층 키워드 추천 생성
# ========================

def generate_keyword_recommendation(
    region: str,
    category: str,
    sub_category: str = "",
) -> Dict[str, Any]:
    """3계층 키워드 추천 생성.

    Returns:
        {
            "main_keywords": [...],     # 메인 키워드 (지역+업종+접미사)
            "sub_keywords": [...],      # 서브 키워드 (세부 서비스/특성)
            "longtail_keywords": [...], # 롱테일 키워드 (구체적 검색 의도)
            "negative_keywords": [...], # 사용 금지 키워드
            "placement_strategy": {...},# 배치 전략
            "density_guide": {...},     # 키워드 밀도 가이드
        }
    """
    normalized = normalize_category(category)
    kw_data = INDUSTRY_KEYWORDS.get(normalized, INDUSTRY_KEYWORDS["default"])

    r = region.strip()
    cat_label = sub_category.strip() if sub_category else (category.strip() or normalized)

    # 메인 키워드: 지역+업종+접미사 (카테고리와 접미사 중복 방지)
    cat_lower = cat_label.lower().replace(" ", "")
    main_keywords = [
        f"{r} {cat_label} {s}" for s in kw_data["main_suffixes"]
        if s.lower().replace(" ", "") != cat_lower
    ]
    if cat_label != r:
        main_keywords.insert(0, f"{r} {cat_label}")

    # 서브 키워드: 세부 서비스/특성
    sub_keywords = kw_data["sub_keywords"]

    # 롱테일: 구체적 검색 의도 (지역 접두)
    longtail_keywords = [f"{r} {lt}" for lt in kw_data["longtail"]]

    return {
        "main_keywords": main_keywords,
        "sub_keywords": sub_keywords,
        "longtail_keywords": longtail_keywords,
        "negative_keywords": kw_data["negative"],
        "placement_strategy": {
            "title": f"제목 앞 15자 이내에 메인 키워드 배치",
            "intro": "본문 초반 200자 이내에 메인 키워드 1회",
            "body": "서브 키워드를 본론 각 섹션에 1~2회 자연 배치",
            "closing": "결론에 메인 키워드 1회 + 롱테일 1회",
            "hashtag": "해시태그에 메인+서브 키워드 혼합 배치",
        },
        "density_guide": {
            "main": "본문 내 5~6회 (전체의 약 1~2%)",
            "sub": "각 2~3회",
            "max_single_word": "동일 단어 20회 초과 금지",
            "subtitle_rule": "전체 소제목 중 1개에만 키워드 포함",
        },
    }


# ========================
# 동적 해시태그 생성
# ========================

def generate_hashtags(
    region: str,
    category: str,
    store_name: str = "",
) -> List[str]:
    """동적 해시태그 생성 (지역+매장+업종+일반, 최대 15개)."""
    normalized = normalize_category(category)
    kw_data = INDUSTRY_KEYWORDS.get(normalized, INDUSTRY_KEYWORDS["default"])

    r_nospace = region.replace(" ", "")
    tags: list[str] = []

    # 지역 태그
    tags.append(f"#{r_nospace}")

    # 매장명 태그
    if store_name:
        tags.append(f"#{store_name.replace(' ', '')}")

    # 업종 기본 태그 (지역 접두)
    for base in kw_data["hashtag_base"]:
        tag = f"#{r_nospace}{base}" if not base.startswith(r_nospace) else f"#{base}"
        if tag not in tags:
            tags.append(tag)

    # 일반 태그
    general = ["#체험단", "#협찬", "#솔직후기", "#블로그리뷰"]
    for g in general:
        if g not in tags:
            tags.append(g)

    return tags[:15]


# ========================
# 상세 금지어 조회
# ========================

def get_forbidden_words_detailed(category: str) -> List[Dict[str, str]]:
    """업종별 + 공통 금지어 병합 반환."""
    normalized = normalize_category(category)
    common = list(FORBIDDEN_WORDS_DETAILED.get("_common", []))
    industry = list(FORBIDDEN_WORDS_DETAILED.get(normalized, []))
    return industry + common


# ========================
# 섹션별 구조 가이드 조회
# ========================

def get_structure_template(
    category: str,
    region: str = "",
    store_name: str = "",
    sub_category: str = "",
) -> Optional[Dict[str, Any]]:
    """섹션별 글 구조 가이드 반환. 없으면 None."""
    normalized = normalize_category(category)
    tmpl = STRUCTURE_TEMPLATES.get(normalized)
    if not tmpl:
        return None
    return tmpl


# ========================
# 지원 업종 목록
# ========================

def get_supported_categories() -> List[Dict[str, str]]:
    """지원 업종 목록 반환."""
    categories = []
    for key in TEMPLATES:
        categories.append({"key": key, "label": key})
    categories.append({"key": "default", "label": "기타 (기본 템플릿)"})
    return categories


# ========================
# 메인 가이드 생성
# ========================

def generate_guide(
    region: str,
    category: str,
    store_name: str = "",
    address: str = "",
    main_keyword_override: str | None = None,
    sub_keywords: list[str] | None = None,
    sub_category: str = "",
) -> Dict[str, Any]:
    """
    체험단 가이드 자동 생성

    Args:
        main_keyword_override: 노출 데이터 기반 메인 키워드 (있으면 우선 사용)
        sub_keywords: 노출 데이터 기반 서브 키워드 리스트
        sub_category: 세부 업종 (선택, 예: "젤네일", "임플란트")

    Returns:
        기존 필드 + keywords_3tier, structure_sections, forbidden_detailed,
        hashtags, compliance, seo_detailed, checklist
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
    template_hashtags = [tag.replace("지역", region_nospace) for tag in template["hashtag_examples"]]

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

    # === 확장 데이터 생성 ===
    effective_category = category or template_key
    keywords_3tier = generate_keyword_recommendation(region, effective_category, sub_category)
    dynamic_hashtags = generate_hashtags(region, effective_category, store_name)
    forbidden_detailed = get_forbidden_words_detailed(effective_category)
    structure_sections = get_structure_template(effective_category, region, store_name, sub_category)
    compliance = dict(COMPLIANCE_GUIDE)
    compliance["required_text"] = COMPLIANCE_GUIDE["required_text"].format(store=store_label)
    seo_detailed = dict(SEO_GUIDE_DETAILED)

    # 체크리스트
    checklist = [
        f"메인 키워드 '{main_keyword}'가 제목 앞 15자 이내에 배치되어 있나요?",
        f"본문 초반 200자 이내에 메인 키워드가 1회 포함되어 있나요?",
        f"사진이 최소 {min_photos}장 이상 포함되어 있나요?",
        f"글자 수가 {min_chars:,}자 이상인가요?",
        "공정위 광고 표시가 본문 최상단에 있나요?",
        "해시태그에 #체험단 또는 #협찬이 포함되어 있나요?",
        "소제목을 3~4개 사용했나요?",
        "네이버 지도 링크를 삽입했나요?",
        "금지어를 사용하지 않았나요?",
        "장점뿐 아니라 아쉬운 점도 포함했나요?",
        "모바일에서 첫 화면에 광고 표시가 보이나요?",
    ]

    # ========================
    # 전체 가이드 텍스트 생성 (9섹션)
    # ========================
    lines = []
    lines.append(f"[{store_label} 체험단 리뷰 가이드]")
    lines.append("")

    # 1. 제목 작성 규칙
    lines.append("--- 1. 제목 작성 규칙 ---")
    lines.append(f"- 제목 앞 15자 이내에 메인 키워드 '{main_keyword}' 포함")
    lines.append(f"- 제목 길이: 20~40자 (너무 길면 잘림)")
    lines.append(f"- 예시: \"{main_keyword} 솔직 후기, {store_label} 방문 체험\"")
    lines.append("")

    # 2. 키워드 배치 전략
    lines.append("--- 2. 키워드 배치 전략 ---")
    lines.append(f"  [메인] '{main_keyword}' — 본문 내 5~6회")
    lines.append(f"    서론1, 본론2, 전환1, 결론1, 자연배치1")
    lines.append(f"  [서브1] '{sub_kw1}' — 본문 내 2~3회")
    lines.append(f"  [서브2] '{sub_kw2}' — 본문 내 2~3회")
    if keywords_3tier["longtail_keywords"]:
        lines.append(f"  [롱테일] {keywords_3tier['longtail_keywords'][0]} — 결론부 1회")
    lines.append(f"  소제목: 전체 3~4개 중 1개에만 키워드 포함")
    lines.append(f"  단어 빈도: 동일 단어 20회 초과 금지")
    lines.append("")

    # 3. 본문 구조
    if structure_sections:
        sections = structure_sections["sections"]
        lines.append(f"--- 3. 글 구조 ({len(sections)}섹션) ---")
        for i, sec in enumerate(sections, 1):
            lines.append(f"  {i}. [{sec['heading']}] (사진 {sec['img_min']}장+)")
            lines.append(f"     {sec['desc']}")
        if structure_sections.get("tips"):
            lines.append(f"  TIP: {' / '.join(structure_sections['tips'])}")
    else:
        lines.append(f"--- 3. 본문 구조 ({len(template['review_structure'])}단락) ---")
        for i, section in enumerate(template["review_structure"], 1):
            wc = section.get("word_count", "")
            wc_hint = f" ({wc})" if wc else ""
            lines.append(f"  {i}. [{section['section']}]{wc_hint}")
            lines.append(f"     {section['guide']}")
    lines.append("")

    # 4. 사진 체크리스트
    lines.append(f"--- 4. 사진 체크리스트 (최소 {min_photos}장) ---")
    for i, photo in enumerate(template["photo_checklist"], 1):
        lines.append(f"  {i}. {photo}")
    lines.append("")

    # 5. 금지어 및 대체 표현
    if forbidden_detailed:
        lines.append("--- 5. 금지어 및 대체 표현 ---")
        if forbidden_reason:
            lines.append(f"  ({forbidden_reason})")
        for item in forbidden_detailed:
            lines.append(f"  X {item['forbidden']} -> O {item['replacement']}")
            if item.get("reason"):
                lines.append(f"    ({item['reason']})")
    elif forbidden:
        lines.append("--- 5. 금지어 및 대체 표현 ---")
        if forbidden_reason:
            lines.append(f"  ({forbidden_reason})")
        for fw in forbidden:
            alt = alternatives.get(fw, "사용 금지")
            lines.append(f"  X {fw} -> O {alt}")
    lines.append("")

    # 6. 필수 광고 표기 (공정위)
    lines.append("--- 6. 필수 광고 표기 (공정거래위원회 규정) ---")
    lines.append(f"- [필수] 본문 최상단(첫 문단)에 다음 문구 삽입:")
    lines.append(f'  "{compliance["required_text"]}"')
    lines.append("- 제목에 [체험단] 또는 [협찬] 표기 권장")
    lines.append("- 해시태그에 #체험단 또는 #협찬 반드시 포함")
    lines.append("- 표시 위치: 스크롤 없이 바로 보이는 위치 (모바일 기준 첫 화면)")
    for rule in compliance.get("rules", [])[2:]:  # 처음 2개는 이미 위에서 언급
        lines.append(f"- {rule}")
    if disclaimer:
        lines.append(f"- 면책 문구 추가: \"{disclaimer}\"")
    lines.append("")

    # 7. 해시태그
    lines.append("--- 7. 해시태그 ---")
    lines.append(f"  {' '.join(dynamic_hashtags)}")
    lines.append("")

    # 8. SEO + 모바일 가이드
    lines.append("--- 8. SEO + 모바일 가이드 ---")
    lines.append(f"- 글자 수: {min_chars:,}자 이상 {max_chars:,}자 이하")
    lines.append(f"- 이미지: 최소 {min_photos}장")
    lines.append("- 소제목: 3~4개 (H2/H3 활용)")
    lines.append("- 문단: 2~3문장 후 줄바꿈 (가독성)")
    lines.append("- 표/리스트: 1~2개 삽입 권장 (정보 정리)")
    lines.append("- 네이버 지도 링크 삽입 필수 (위치 정보 + SEO)")
    lines.append("- 메인 키워드를 본문에서 가장 많이 사용하도록 구성")
    lines.append("- 모바일 가독성: 한 줄에 15~20자, 가로형 이미지 권장")
    lines.append("- 동영상 포함 시 체류 시간 증가 (15~30초 클립 권장)")
    lines.append("")

    # 9. 체크리스트
    lines.append("--- 9. 발행 전 체크리스트 ---")
    for i, item in enumerate(checklist, 1):
        lines.append(f"  [ ] {item}")
    lines.append("")

    # --- 주의사항 ---
    lines.append("--- 주의사항 ---")
    lines.append("- 과도한 광고성 표현 지양 (솔직한 톤 유지)")
    lines.append("- 장점뿐 아니라 아쉬운 점도 자연스럽게 포함 (신뢰도 향상)")

    full_text = "\n".join(lines)

    return {
        # 기존 필드 (하위 호환)
        "store_name": store_label,
        "main_keyword": main_keyword,
        "title_rule": keyword_placement["title"],
        "body_rule": keyword_placement["body_intro"],
        "review_structure": template["review_structure"],
        "photo_checklist": template["photo_checklist"],
        "keyword_placement": keyword_placement,
        "hashtag_examples": template_hashtags,
        "forbidden_words": forbidden,
        "alternative_words": alternatives,
        "seo_guide": seo_guide,
        "full_guide_text": full_text,
        # 확장 필드 (프론트엔드 친화 키로 변환)
        "keywords_3tier": {
            "main": keywords_3tier.get("main_keywords", []),
            "sub": keywords_3tier.get("sub_keywords", []),
            "longtail": keywords_3tier.get("longtail_keywords", []),
            "negative": keywords_3tier.get("negative_keywords", []),
            "placement": keywords_3tier.get("placement_strategy", {}),
            "density": keywords_3tier.get("density_guide", {}),
        } if keywords_3tier else None,
        "structure_sections": structure_sections.get("sections", []) if isinstance(structure_sections, dict) else structure_sections,
        "forbidden_detailed": forbidden_detailed,
        "hashtags": dynamic_hashtags,
        "compliance": compliance,
        "seo_detailed": seo_detailed,
        "checklist": checklist,
    }
