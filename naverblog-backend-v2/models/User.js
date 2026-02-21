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
userSchema.index({ provider: 1, providerId: 1 }, { unique: true, sparse: true });
userSchema.index({ email: 1, provider: 1 }, { unique: true, sparse: true });

module.exports = mongoose.model('User', userSchema);
