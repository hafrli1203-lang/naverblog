// models/Analytics.js
const mongoose = require('mongoose');

// ── 페이지뷰 (개별 요청 기록) ──
const pageViewSchema = new mongoose.Schema({
  path:      String,               // "/dashboard", "/blog-analysis"
  section:   String,               // "search", "analysis", "campaign", "guide"
  userId:    { type: mongoose.Schema.Types.ObjectId, ref: 'User', default: null },
  sessionId: String,               // 비로그인 사용자도 추적
  ip:        String,
  userAgent: String,
  referer:   String,
  createdAt: { type: Date, default: Date.now, expires: 90 * 86400 }, // 90일 후 자동 삭제
});
pageViewSchema.index({ createdAt: -1 });
pageViewSchema.index({ section: 1, createdAt: -1 });

// ── 검색 로그 ──
const searchLogSchema = new mongoose.Schema({
  userId:    { type: mongoose.Schema.Types.ObjectId, ref: 'User', default: null },
  region:    String,
  topic:     String,
  storeName: String,
  keyword:   String,
  resultCount: Number,             // 검색 결과 수
  createdAt: { type: Date, default: Date.now, expires: 90 * 86400 },
});
searchLogSchema.index({ createdAt: -1 });
searchLogSchema.index({ region: 1 });
searchLogSchema.index({ topic: 1 });

// ── 일별 요약 통계 ──
const dailyStatsSchema = new mongoose.Schema({
  date:            { type: String, unique: true },  // "2026-02-21"
  pageViews:       { type: Number, default: 0 },
  uniqueVisitors:  { type: Number, default: 0 },
  searches:        { type: Number, default: 0 },
  blogAnalyses:    { type: Number, default: 0 },
  newUsers:        { type: Number, default: 0 },
  activeUsers:     { type: Number, default: 0 },    // 로그인한 유저 수

  // 인기 지역/업종
  topRegions:  [{ name: String, count: Number }],
  topTopics:   [{ name: String, count: Number }],

  // 시간대별 방문 (0~23시)
  hourlyViews: { type: [Number], default: () => new Array(24).fill(0) },
});

// ── 이벤트 (특정 행동 추적) ──
const eventSchema = new mongoose.Schema({
  userId:    { type: mongoose.Schema.Types.ObjectId, ref: 'User', default: null },
  event:     String,    // "blogger_save", "campaign_create", "report_view", "guide_view"
  data:      mongoose.Schema.Types.Mixed,  // 추가 데이터
  createdAt: { type: Date, default: Date.now, expires: 90 * 86400 },
});
eventSchema.index({ event: 1, createdAt: -1 });

module.exports = {
  PageView:   mongoose.model('PageView', pageViewSchema),
  SearchLog:  mongoose.model('SearchLog', searchLogSchema),
  DailyStats: mongoose.model('DailyStats', dailyStatsSchema),
  Event:      mongoose.model('Event', eventSchema),
};
