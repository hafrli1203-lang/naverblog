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
router.get('/kakao', (req, res, next) => {
  passport.authenticate('kakao', (err) => {
    if (err) {
      console.error('[Auth] 카카오 인증 시작 실패:', err.message);
      return res.redirect(`${FRONTEND_URL}/?login=fail&provider=kakao&error=${encodeURIComponent(err.message)}`);
    }
  })(req, res, next);
});
router.get('/kakao/callback', (req, res, next) => {
  passport.authenticate('kakao', (err, user) => {
    if (err || !user) {
      console.error('[Auth] 카카오 콜백 실패:', err?.message || 'user 없음');
      return res.redirect(`${FRONTEND_URL}/?login=fail&provider=kakao`);
    }
    req.logIn(user, (loginErr) => {
      if (loginErr) {
        console.error('[Auth] 카카오 세션 저장 실패:', loginErr.message);
        return res.redirect(`${FRONTEND_URL}/?login=fail&provider=kakao`);
      }
      trackEvent(user._id, 'login', { provider: 'kakao' });
      if (user.createdAt && (Date.now() - user.createdAt.getTime()) < 5000) onNewUser();
      res.redirect(`${FRONTEND_URL}/?login=success`);
    });
  })(req, res, next);
});

// ═══ 네이버 ═══
router.get('/naver', (req, res, next) => {
  passport.authenticate('naver', (err) => {
    if (err) {
      console.error('[Auth] 네이버 인증 시작 실패:', err.message);
      return res.redirect(`${FRONTEND_URL}/?login=fail&provider=naver&error=${encodeURIComponent(err.message)}`);
    }
  })(req, res, next);
});
router.get('/naver/callback', (req, res, next) => {
  passport.authenticate('naver', (err, user) => {
    if (err || !user) {
      console.error('[Auth] 네이버 콜백 실패:', err?.message || 'user 없음');
      return res.redirect(`${FRONTEND_URL}/?login=fail&provider=naver`);
    }
    req.logIn(user, (loginErr) => {
      if (loginErr) {
        console.error('[Auth] 네이버 세션 저장 실패:', loginErr.message);
        return res.redirect(`${FRONTEND_URL}/?login=fail&provider=naver`);
      }
      trackEvent(user._id, 'login', { provider: 'naver' });
      if (user.createdAt && (Date.now() - user.createdAt.getTime()) < 5000) onNewUser();
      res.redirect(`${FRONTEND_URL}/?login=success`);
    });
  })(req, res, next);
});

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
