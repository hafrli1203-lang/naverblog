// routes/admin.js
const router = require('express').Router();
const Ad     = require('../models/Ad');
const User   = require('../models/User');
const { PageView, SearchLog, DailyStats, Event } = require('../models/Analytics');

// ── 관리자 확인 ──
function requireAdmin(req, res, next) {
  const ADMIN_EMAILS = (process.env.ADMIN_EMAIL || '').split(',').map(e => e.trim());
  if (!req.isAuthenticated()) return res.status(401).json({ error: '로그인 필요' });
  if (req.user.role !== 'admin' && !ADMIN_EMAILS.includes(req.user.email)) {
    return res.status(403).json({ error: '관리자 권한 필요' });
  }
  next();
}


// ╔══════════════════════════════════════════════════════════════╗
// ║  사이트 이용 현황 — 관리자 대시보드                            ║
// ╚══════════════════════════════════════════════════════════════╝

// ═══ 오늘 실시간 요약 ═══
router.get('/analytics/today', requireAdmin, async (req, res) => {
  const today     = new Date().toISOString().slice(0, 10);
  const todayStart = new Date(today + 'T00:00:00Z');

  const [dailyStat, todaySearches, todayEvents, onlineRecent] = await Promise.all([
    DailyStats.findOne({ date: today }),
    SearchLog.countDocuments({ createdAt: { $gte: todayStart } }),
    Event.countDocuments({ createdAt: { $gte: todayStart } }),
    // 최근 5분 내 활동 = "현재 접속 중" 추정
    PageView.distinct('sessionId', {
      createdAt: { $gte: new Date(Date.now() - 5 * 60 * 1000) }
    }),
  ]);

  res.json({
    date: today,
    pageViews:      dailyStat?.pageViews || 0,
    searches:       todaySearches,
    events:         todayEvents,
    estimatedOnline: onlineRecent.length,
    hourlyViews:    dailyStat?.hourlyViews || new Array(24).fill(0),
  });
});

// ═══ 기간별 통계 (차트용) ═══
router.get('/analytics/range', requireAdmin, async (req, res) => {
  const { days = 30 } = req.query;
  const since = new Date();
  since.setDate(since.getDate() - parseInt(days));
  const sinceStr = since.toISOString().slice(0, 10);

  const stats = await DailyStats.find({ date: { $gte: sinceStr } }).sort({ date: 1 });

  res.json({
    days: parseInt(days),
    data: stats.map(s => ({
      date:           s.date,
      pageViews:      s.pageViews,
      uniqueVisitors: s.uniqueVisitors,
      searches:       s.searches,
      newUsers:       s.newUsers,
      activeUsers:    s.activeUsers,
    })),
    totals: {
      pageViews:  stats.reduce((s, d) => s + d.pageViews, 0),
      searches:   stats.reduce((s, d) => s + d.searches, 0),
      newUsers:   stats.reduce((s, d) => s + d.newUsers, 0),
    }
  });
});

// ═══ 인기 검색 지역/업종 ═══
router.get('/analytics/popular', requireAdmin, async (req, res) => {
  const { days = 7 } = req.query;
  const since = new Date();
  since.setDate(since.getDate() - parseInt(days));

  const [topRegions, topTopics] = await Promise.all([
    SearchLog.aggregate([
      { $match: { createdAt: { $gte: since }, region: { $ne: null } } },
      { $group: { _id: '$region', count: { $sum: 1 } } },
      { $sort: { count: -1 } },
      { $limit: 10 },
    ]),
    SearchLog.aggregate([
      { $match: { createdAt: { $gte: since }, topic: { $ne: null } } },
      { $group: { _id: '$topic', count: { $sum: 1 } } },
      { $sort: { count: -1 } },
      { $limit: 10 },
    ]),
  ]);

  res.json({
    topRegions: topRegions.map(r => ({ name: r._id, count: r.count })),
    topTopics:  topTopics.map(t => ({ name: t._id, count: t.count })),
  });
});

// ═══ 최근 검색 실시간 피드 ═══
router.get('/analytics/searches', requireAdmin, async (req, res) => {
  const searches = await SearchLog.find()
    .sort({ createdAt: -1 })
    .limit(50)
    .populate('userId', 'displayName email');

  res.json(searches.map(s => ({
    region:    s.region,
    topic:     s.topic,
    keyword:   s.keyword,
    storeName: s.storeName,
    user:      s.userId?.displayName || '비회원',
    time:      s.createdAt,
  })));
});

// ═══ 최근 이벤트 피드 ═══
router.get('/analytics/events', requireAdmin, async (req, res) => {
  const events = await Event.find()
    .sort({ createdAt: -1 })
    .limit(50)
    .populate('userId', 'displayName email');

  res.json(events.map(e => ({
    event: e.event,
    data:  e.data,
    user:  e.userId?.displayName || '비회원',
    time:  e.createdAt,
  })));
});

// ═══ 유저 통계 ═══
router.get('/analytics/users', requireAdmin, async (req, res) => {
  const total     = await User.countDocuments();
  const today     = new Date().toISOString().slice(0, 10);
  const todayStart = new Date(today + 'T00:00:00Z');
  const newToday  = await User.countDocuments({ createdAt: { $gte: todayStart } });

  // 최근 7일 가입자 수
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);
  const newThisWeek = await User.countDocuments({ createdAt: { $gte: weekAgo } });

  // 로그인 방식별
  const byProvider = await User.aggregate([
    { $group: { _id: '$provider', count: { $sum: 1 } } },
    { $sort: { count: -1 } },
  ]);

  // 최근 가입자 목록
  const recentUsers = await User.find()
    .sort({ createdAt: -1 })
    .limit(20)
    .select('displayName email provider plan createdAt lastLoginAt');

  res.json({
    total,
    newToday,
    newThisWeek,
    byProvider: byProvider.map(p => ({ provider: p._id, count: p.count })),
    recentUsers,
  });
});

// ═══ 페이지별 조회수 ═══
router.get('/analytics/pages', requireAdmin, async (req, res) => {
  const { days = 7 } = req.query;
  const since = new Date();
  since.setDate(since.getDate() - parseInt(days));

  const pages = await PageView.aggregate([
    { $match: { createdAt: { $gte: since } } },
    { $group: { _id: '$section', count: { $sum: 1 } } },
    { $sort: { count: -1 } },
  ]);

  res.json(pages.map(p => ({ section: p._id, views: p.count })));
});


// ╔══════════════════════════════════════════════════════════════╗
// ║  광고 관리 CRUD                                              ║
// ╚══════════════════════════════════════════════════════════════╝

// ── 광고 전체 통계 ──
router.get('/ads/stats', requireAdmin, async (req, res) => {
  const now = new Date();
  const activeAds = await Ad.find({
    isActive: true, startDate: { $lte: now }, endDate: { $gte: now },
  });

  const totalImpressions = activeAds.reduce((s, a) => s + a.stats.impressions, 0);
  const totalClicks      = activeAds.reduce((s, a) => s + a.stats.clicks, 0);
  const monthlyRevenue   = activeAds.reduce((s, a) => s + (a.billing.amount || 0), 0);

  res.json({
    activeCount: activeAds.length,
    totalImpressions,
    totalClicks,
    avgCtr: totalImpressions > 0 ? ((totalClicks / totalImpressions) * 100).toFixed(2) : '0.00',
    monthlyRevenue,
  });
});

// ── CRUD ──
router.get('/ads',         requireAdmin, async (req, res) => {
  res.json(await Ad.find().sort({ priority: -1, createdAt: -1 }));
});
router.post('/ads',        requireAdmin, async (req, res) => {
  res.json(await Ad.create(req.body));
});
router.put('/ads/:id',     requireAdmin, async (req, res) => {
  res.json(await Ad.findByIdAndUpdate(req.params.id, { ...req.body, updatedAt: new Date() }, { new: true }));
});
router.delete('/ads/:id',  requireAdmin, async (req, res) => {
  await Ad.findByIdAndDelete(req.params.id);
  res.json({ ok: true });
});

// ── 개별 광고 리포트 ──
router.get('/ads/:id/report', requireAdmin, async (req, res) => {
  const ad = await Ad.findById(req.params.id);
  if (!ad) return res.status(404).json({ error: '없음' });
  const ctr = ad.stats.impressions > 0
    ? ((ad.stats.clicks / ad.stats.impressions) * 100).toFixed(2) : '0.00';
  res.json({
    advertiser:  ad.advertiser.company,
    title:       ad.title,
    period:      ad.startDate?.toISOString().slice(0,10) + ' ~ ' + ad.endDate?.toISOString().slice(0,10),
    targeting:   ad.targeting,
    impressions: ad.stats.impressions,
    clicks:      ad.stats.clicks,
    ctr:         ctr + '%',
    billing:     ad.billing,
    dailyStats:  ad.stats.daily.slice(-30),
  });
});

module.exports = router;
