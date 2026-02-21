// middleware/analytics.js
const { PageView, DailyStats, Event } = require('../models/Analytics');

// 섹션 분류
function classifySection(path) {
  if (path.includes('/api/search') || path.includes('dashboard'))  return 'search';
  if (path.includes('blog-analysis') || path.includes('/api/analyze')) return 'analysis';
  if (path.includes('campaign'))  return 'campaign';
  if (path.includes('goldenscore') || path.includes('guide'))      return 'guide';
  if (path.includes('/auth'))     return 'auth';
  if (path.includes('/admin'))    return 'admin';
  return 'other';
}

// 오늘 날짜 문자열
function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

// ── 페이지뷰 추적 미들웨어 ──
async function trackPageView(req, res, next) {
  // 정적 파일, 광고, 파비콘 제외
  if (
    req.path.match(/\.(js|css|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf)$/) ||
    req.path.startsWith('/ads/impression') ||
    req.path.startsWith('/ads/click')
  ) {
    return next();
  }

  try {
    const section = classifySection(req.path);
    const today = todayStr();
    const hour = new Date().getHours();

    // 세션 ID (비로그인 추적용)
    const sessionId = req.sessionID || req.ip;

    // 페이지뷰 기록 (비동기, 응답 블로킹 안 함)
    PageView.create({
      path:      req.path,
      section,
      userId:    req.user?._id || null,
      sessionId,
      ip:        req.ip,
      userAgent: req.headers['user-agent']?.substring(0, 200),
      referer:   req.headers['referer']?.substring(0, 300),
    }).catch(() => {}); // 실패해도 서비스에 영향 없음

    // 일별 통계 업데이트
    DailyStats.findOneAndUpdate(
      { date: today },
      {
        $inc: {
          pageViews: 1,
          [`hourlyViews.${hour}`]: 1,
        },
        $setOnInsert: { date: today },
      },
      { upsert: true, new: true }
    ).catch(() => {});

  } catch (e) {
    // 추적 실패가 서비스를 방해하면 안 됨
  }

  next();
}

// ── 이벤트 기록 함수 (라우트에서 호출) ──
async function trackEvent(userId, event, data = {}) {
  try {
    await Event.create({ userId, event, data });
  } catch (e) {}
}

// ── 검색 로그 기록 함수 ──
async function trackSearch(userId, searchData) {
  const { SearchLog } = require('../models/Analytics');
  try {
    await SearchLog.create({
      userId,
      region:      searchData.region,
      topic:       searchData.topic,
      storeName:   searchData.storeName,
      keyword:     searchData.keyword,
      resultCount: searchData.resultCount,
    });

    // 일별 통계에 검색 수 +1
    const today = todayStr();
    await DailyStats.findOneAndUpdate(
      { date: today },
      { $inc: { searches: 1 }, $setOnInsert: { date: today } },
      { upsert: true }
    );
  } catch (e) {}
}

module.exports = { trackPageView, trackEvent, trackSearch };
