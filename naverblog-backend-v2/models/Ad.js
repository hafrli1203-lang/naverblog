// models/Ad.js
const mongoose = require('mongoose');

const adSchema = new mongoose.Schema({
  // ── 광고주 ──
  advertiser: {
    company: String,    // "스마트POS" / "렌즈도매몰"
    name:    String,    // 담당자
    phone:   String,
    email:   String,
    memo:    String,
  },

  // ── 콘텐츠 ──
  title:       String,
  description: String,
  imageUrl:    String,
  linkUrl:     String,
  ctaText:     { type: String, default: '자세히 보기' },

  // ── 유형 ──
  type: {
    type: String,
    enum: ['banner_horizontal', 'banner_sidebar', 'native_card', 'text_link'],
    default: 'native_card',
  },

  // ── 위치 ──
  placement: {
    type: String,
    enum: ['search_top', 'search_middle', 'search_bottom', 'sidebar', 'report_bottom', 'mobile_sticky'],
    default: 'search_top',
  },

  // ── 타겟: 방문자(자영업자) 업종 ──
  targeting: {
    businessTypes: [String],  // ["음식점","맛집"] or ["all"]
    regions:       [String],  // ["김해","부산"] or [] (전국)
  },

  // ── 기간 ──
  startDate: { type: Date, required: true },
  endDate:   { type: Date, required: true },
  isActive:  { type: Boolean, default: true },

  // ── 과금 ──
  billing: {
    model:  { type: String, enum: ['monthly', 'weekly', 'cpc', 'free_trial'], default: 'monthly' },
    amount: Number,
    notes:  String,
  },

  // ── 통계 ──
  stats: {
    impressions: { type: Number, default: 0 },
    clicks:      { type: Number, default: 0 },
    daily: [{
      date:        String,
      impressions: { type: Number, default: 0 },
      clicks:      { type: Number, default: 0 },
    }],
  },

  priority:  { type: Number, default: 0 },
  createdAt: { type: Date, default: Date.now },
});

adSchema.index({ isActive: 1, startDate: 1, endDate: 1 });
adSchema.index({ 'targeting.businessTypes': 1 });

module.exports = mongoose.model('Ad', adSchema);
