// models/User.js
const mongoose = require('mongoose');
const userSchema = new mongoose.Schema({
  // ── 기본 정보 ──
  email:        { type: String, sparse: true },
  displayName:  { type: String, required: true },
  profileImage: { type: String, default: '' },

  // ── 로그인 방식 (SNS만) ──
  provider:   { type: String, enum: ['kakao', 'naver', 'google'], required: true },
  providerId: { type: String, required: true },

  // ── 권한 ──
  role: { type: String, enum: ['user', 'admin'], default: 'user' },
  plan: { type: String, enum: ['free', 'pro'], default: 'free' },

  // ── 회원 유형 (자영업자/인플루언서) ──
  userType:       { type: String, enum: ['owner', 'influencer'], default: null },
  // 자영업자 전용
  businessType:   String,
  businessRegion: String,
  // 인플루언서 전용
  blogUrl:        String,
  snsUrls:        [String],
  desiredRate:    { type: Number, default: 0 },
  bio:            String,
  specialties:    [String],
  phone:          String,

  // ── 유저별 저장 데이터 ──
  savedBloggers: [{
    blogId:   String,
    blogName: String,
    score:    Number,
    grade:    String,
    savedAt:  { type: Date, default: Date.now },
  }],

  searchHistory: [{
    region:     String,
    topic:      String,
    storeName:  String,
    keyword:    String,
    searchedAt: { type: Date, default: Date.now },
  }],

  campaigns: [{
    name:      String,
    region:    String,
    category:  String,
    memo:      String,
    bloggers:  [{ blogId: String, blogName: String, score: Number, grade: String }],
    createdAt: { type: Date, default: Date.now },
  }],

  // ── 메타 ──
  createdAt:   { type: Date, default: Date.now },
  lastLoginAt: { type: Date, default: Date.now },
});

// 중복 방지 (같은 provider + providerId 조합)
userSchema.index({ provider: 1, providerId: 1 }, { unique: true });
// NOTE: {email, provider} 유니크 인덱스 제거 — email: null인 OAuth 사용자 다수 허용
// (기존 sparse:true는 null 값을 스킵하지 않아 E11000 중복 에러 발생)

module.exports = mongoose.model('User', userSchema);
