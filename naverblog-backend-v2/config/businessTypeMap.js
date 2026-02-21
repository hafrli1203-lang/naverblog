// config/businessTypeMap.js

// 사용자가 검색한 "주제"로부터 방문자 업종을 추론
// → 해당 업종 사장님에게 맞는 B2B 광고를 매칭

const BUSINESS_TYPE_MAP = {
  '맛집':         ['음식점', '맛집'],
  '요리·레시피':   ['음식점', '맛집'],
  '카페':         ['카페'],
  '패션·미용':    ['뷰티', '미용실', '네일'],
  '건강·의학':    ['병원', '의원', '약국', '안경원'],
  '국내여행':     ['숙박', '펜션', '호텔'],
  '세계여행':     ['여행사'],
  '교육·학문':    ['학원', '교육'],
  '상품리뷰':     ['쇼핑몰', '소매'],
  '인테리어·DIY': ['인테리어', '시공'],
  '반려동물':     ['동물병원', '펫샵'],
  '자동차':       ['정비소', '세차장'],
  '스포츠':       ['체육관', '스포츠시설'],
  '사진':         ['스튜디오'],
};

function inferBusinessType(searchTopic, searchKeyword) {
  if (searchTopic && BUSINESS_TYPE_MAP[searchTopic]) {
    return BUSINESS_TYPE_MAP[searchTopic];
  }
  if (searchKeyword) {
    const kw = searchKeyword.toLowerCase();
    if (kw.includes('맛집') || kw.includes('음식') || kw.includes('식당')) return ['음식점', '맛집'];
    if (kw.includes('카페') || kw.includes('커피')) return ['카페'];
    if (kw.includes('미용') || kw.includes('네일') || kw.includes('피부')) return ['뷰티'];
    if (kw.includes('안경') || kw.includes('렌즈')) return ['안경원'];
    if (kw.includes('병원') || kw.includes('의원') || kw.includes('치과')) return ['병원', '의원'];
    if (kw.includes('학원')) return ['학원', '교육'];
    if (kw.includes('호텔') || kw.includes('펜션')) return ['숙박'];
  }
  return ['all'];
}

module.exports = { BUSINESS_TYPE_MAP, inferBusinessType };
