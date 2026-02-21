// routes/auth.js — SNS 로그인만 (카카오/네이버/구글)
const router   = require('express').Router();
const passport = require('passport');
const { DailyStats } = require('../models/Analytics');
const { trackEvent } = require('../middleware/analytics');

// 프론트엔드 URL (Python 서버가 서빙)
const FRONTEND_URL = process.env.FRONTEND_URL || 'https://xn--6j1b00mxunnyck8p.com';

// ═══ 현재 로그인 상태 ═══
router.get('/me', (req, res) => {
  if (!req.isAuthenticated()) return res.json({ loggedIn: false });
  res.json({
    loggedIn: true,
    user: {
      id:           req.user._id,
      displayName:  req.user.displayName,
      email:        req.user.email,
      profileImage: req.user.profileImage,
      provider:     req.user.provider,
      plan:         req.user.plan,
      role:         req.user.role,
    }
  });
});

// 신규 가입 시 일별 통계 업데이트 헬퍼
async function onNewUser() {
  const today = new Date().toISOString().slice(0, 10);
  DailyStats.findOneAndUpdate(
    { date: today },
    { $inc: { newUsers: 1 }, $setOnInsert: { date: today } },
    { upsert: true }
  ).catch(() => {});
}

// ═══ 카카오 ═══
router.get('/kakao', passport.authenticate('kakao'));
router.get('/kakao/callback',
  passport.authenticate('kakao', { failureRedirect: `${FRONTEND_URL}/?login=fail` }),
  (req, res) => {
    trackEvent(req.user._id, 'login', { provider: 'kakao' });
    if (req.user.createdAt && (Date.now() - req.user.createdAt.getTime()) < 5000) onNewUser();
    res.redirect(`${FRONTEND_URL}/?login=success`);
  }
);

// ═══ 네이버 ═══
router.get('/naver', passport.authenticate('naver'));
router.get('/naver/callback',
  passport.authenticate('naver', { failureRedirect: `${FRONTEND_URL}/?login=fail` }),
  (req, res) => {
    trackEvent(req.user._id, 'login', { provider: 'naver' });
    if (req.user.createdAt && (Date.now() - req.user.createdAt.getTime()) < 5000) onNewUser();
    res.redirect(`${FRONTEND_URL}/?login=success`);
  }
);

// ═══ 구글 ═══
router.get('/google', passport.authenticate('google', { scope: ['email', 'profile'] }));
router.get('/google/callback',
  passport.authenticate('google', { failureRedirect: `${FRONTEND_URL}/?login=fail` }),
  (req, res) => {
    trackEvent(req.user._id, 'login', { provider: 'google' });
    if (req.user.createdAt && (Date.now() - req.user.createdAt.getTime()) < 5000) onNewUser();
    res.redirect(`${FRONTEND_URL}/?login=success`);
  }
);

// ═══ 로그아웃 ═══
router.post('/logout', (req, res) => {
  req.logout((err) => {
    if (err) return res.status(500).json({ error: '로그아웃 실패' });
    res.json({ success: true });
  });
});

module.exports = router;
