// routes/auth.js — SNS 로그인만 (카카오/네이버/구글) + 토큰 교환
const router   = require('express').Router();
const passport = require('passport');
const crypto   = require('crypto');
const { DailyStats } = require('../models/Analytics');
const { trackEvent } = require('../middleware/analytics');
const AuthToken = require('../models/AuthToken');
const User      = require('../models/User');

// 프론트엔드 URL (Python 서버가 서빙)
const FRONTEND_URL = process.env.FRONTEND_URL || 'https://xn--6j1b00mxunnyck8p.com';

// ═══ 일회성 인증 토큰 생성 ═══
async function generateAuthToken(userId, provider) {
  try {
    const token = crypto.randomBytes(32).toString('hex'); // 256비트
    await AuthToken.create({ token, userId, provider });
    console.log('[Auth] Token generated for', provider, '— userId:', userId);
    return token;
  } catch (e) {
    console.error('[Auth] Token 생성 실패:', e.message);
    return null; // 실패 시 쿠키 폴백 (토큰 없이 리다이렉트)
  }
}

// ═══ 현재 로그인 상태 ═══
router.get('/me', (req, res) => {
  if (!req.isAuthenticated()) return res.json({ loggedIn: false });
  res.json({
    loggedIn: true,
    user: {
      id:             req.user._id,
      displayName:    req.user.displayName,
      email:          req.user.email,
      profileImage:   req.user.profileImage,
      provider:       req.user.provider,
      plan:           req.user.plan,
      role:           req.user.role,
      userType:       req.user.userType || null,
      businessType:   req.user.businessType || null,
      businessRegion: req.user.businessRegion || null,
      blogUrl:        req.user.blogUrl || null,
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
  console.log('[Auth] 카카오 인증 시작 — sessionID:', req.sessionID);
  passport.authenticate('kakao', { failureRedirect: `${FRONTEND_URL}/?login=fail&provider=kakao` })(req, res, next);
});
router.get('/kakao/callback', (req, res, next) => {
  console.log('[Auth] 카카오 콜백 진입 — sessionID:', req.sessionID,
    '| cookie:', req.headers.cookie ? 'present' : 'absent',
    '| code:', !!req.query.code, '| error:', req.query.error || 'none',
    '| session_keys:', Object.keys(req.session || {}));
  passport.authenticate('kakao', (err, user, info) => {
    if (err || !user) {
      console.error('[Auth] 카카오 콜백 실패:', err?.message || 'user 없음', '| info:', JSON.stringify(info));
      const errMsg = err?.message || info?.message || 'unknown';
      return res.redirect(`${FRONTEND_URL}/?login=fail&provider=kakao&error=${encodeURIComponent(errMsg)}`);
    }
    req.logIn(user, { keepSessionInfo: true }, (loginErr) => {
      if (loginErr) {
        console.error('[Auth] 카카오 세션 저장 실패:', loginErr.message);
        return res.redirect(`${FRONTEND_URL}/?login=fail&provider=kakao`);
      }
      console.log('[Auth] 카카오 로그인 성공 — user:', user._id, user.displayName, '| sessionID:', req.sessionID);
      trackEvent(user._id, 'login', { provider: 'kakao' });
      if (user.createdAt && (Date.now() - user.createdAt.getTime()) < 5000) onNewUser();
      req.session.save(async (saveErr) => {
        if (saveErr) console.error('[Auth] 카카오 세션 save 실패:', saveErr.message);
        const token = await generateAuthToken(user._id, 'kakao');
        const tokenParam = token ? `&token=${token}` : '';
        res.redirect(`${FRONTEND_URL}/?login=success&provider=kakao${tokenParam}`);
      });
    });
  })(req, res, next);
});

// ═══ 네이버 ═══
router.get('/naver', (req, res, next) => {
  console.log('[Auth] 네이버 인증 시작 — sessionID:', req.sessionID);
  passport.authenticate('naver', { failureRedirect: `${FRONTEND_URL}/?login=fail&provider=naver` })(req, res, next);
});
router.get('/naver/callback', (req, res, next) => {
  console.log('[Auth] 네이버 콜백 진입 — sessionID:', req.sessionID,
    '| query.state:', req.query.state, '| session.state:', req.session?.oauth_state,
    '| code:', !!req.query.code, '| error:', req.query.error || 'none',
    '| error_description:', req.query.error_description || 'none');
  passport.authenticate('naver', (err, user, info) => {
    if (err || !user) {
      console.error('[Auth] 네이버 콜백 실패:', err?.message || 'user 없음', '| info:', JSON.stringify(info));
      const errMsg = err?.message || info?.message || 'unknown';
      return res.redirect(`${FRONTEND_URL}/?login=fail&provider=naver&error=${encodeURIComponent(errMsg)}`);
    }
    req.logIn(user, { keepSessionInfo: true }, (loginErr) => {
      if (loginErr) {
        console.error('[Auth] 네이버 세션 저장 실패:', loginErr.message);
        return res.redirect(`${FRONTEND_URL}/?login=fail&provider=naver`);
      }
      console.log('[Auth] 네이버 로그인 성공 — user:', user._id, user.displayName, '| sessionID:', req.sessionID);
      trackEvent(user._id, 'login', { provider: 'naver' });
      if (user.createdAt && (Date.now() - user.createdAt.getTime()) < 5000) onNewUser();
      req.session.save(async (saveErr) => {
        if (saveErr) console.error('[Auth] 네이버 세션 save 실패:', saveErr.message);
        const token = await generateAuthToken(user._id, 'naver');
        const tokenParam = token ? `&token=${token}` : '';
        res.redirect(`${FRONTEND_URL}/?login=success&provider=naver${tokenParam}`);
      });
    });
  })(req, res, next);
});

// ═══ 구글 ═══
router.get('/google', passport.authenticate('google', { scope: ['email', 'profile'] }));
router.get('/google/callback', (req, res, next) => {
  passport.authenticate('google', (err, user, info) => {
    if (err || !user) {
      console.error('[Auth] 구글 콜백 실패:', err?.message || 'user 없음', '| info:', JSON.stringify(info));
      const errMsg = err?.message || info?.message || 'unknown';
      return res.redirect(`${FRONTEND_URL}/?login=fail&provider=google&error=${encodeURIComponent(errMsg)}`);
    }
    req.logIn(user, { keepSessionInfo: true }, (loginErr) => {
      if (loginErr) {
        console.error('[Auth] 구글 세션 저장 실패:', loginErr.message);
        return res.redirect(`${FRONTEND_URL}/?login=fail&provider=google`);
      }
      console.log('[Auth] 구글 로그인 성공 — user:', user._id, user.displayName, '| sessionID:', req.sessionID);
      trackEvent(user._id, 'login', { provider: 'google' });
      if (user.createdAt && (Date.now() - user.createdAt.getTime()) < 5000) onNewUser();
      req.session.save(async (saveErr) => {
        if (saveErr) console.error('[Auth] 구글 세션 save 실패:', saveErr.message);
        const token = await generateAuthToken(user._id, 'google');
        const tokenParam = token ? `&token=${token}` : '';
        res.redirect(`${FRONTEND_URL}/?login=success&provider=google${tokenParam}`);
      });
    });
  })(req, res, next);
});

// ═══ 토큰 교환 → 세션 생성 ═══
router.post('/token-exchange', async (req, res) => {
  try {
    const { token } = req.body || {};
    // 토큰 형식 검증 (64자 hex = 32바이트)
    if (!token || typeof token !== 'string' || !/^[0-9a-f]{64}$/.test(token)) {
      return res.status(400).json({ error: 'invalid token format' });
    }
    // 원자적 1회 사용: used=false인 것만 찾아서 used=true로 변경
    const authToken = await AuthToken.findOneAndUpdate(
      { token, used: false },
      { $set: { used: true } },
      { new: true }
    );
    if (!authToken) {
      console.warn('[Auth] token-exchange 실패 — 토큰 없음/만료/사용됨');
      return res.status(401).json({ error: 'invalid or expired token' });
    }
    // 사용자 조회
    const user = await User.findById(authToken.userId);
    if (!user) {
      console.error('[Auth] token-exchange — 사용자 없음:', authToken.userId);
      return res.status(401).json({ error: 'user not found' });
    }
    // 세션 생성
    req.logIn(user, (loginErr) => {
      if (loginErr) {
        console.error('[Auth] token-exchange 세션 생성 실패:', loginErr.message);
        return res.status(500).json({ error: 'session creation failed' });
      }
      req.session.save(async (saveErr) => {
        if (saveErr) console.error('[Auth] token-exchange 세션 save 실패:', saveErr.message);
        // 토큰 즉시 삭제 (TTL 대기 불필요)
        AuthToken.deleteOne({ _id: authToken._id }).catch(() => {});
        console.log('[Auth] token-exchange 성공 — user:', user._id, user.displayName, '| provider:', authToken.provider);
        res.json({
          success: true,
          user: {
            id:             user._id,
            displayName:    user.displayName,
            email:          user.email,
            profileImage:   user.profileImage,
            provider:       user.provider,
            plan:           user.plan,
            role:           user.role,
            userType:       user.userType || null,
            businessType:   user.businessType || null,
            businessRegion: user.businessRegion || null,
            blogUrl:        user.blogUrl || null,
          }
        });
      });
    });
  } catch (e) {
    console.error('[Auth] token-exchange 에러:', e);
    res.status(500).json({ error: 'internal error' });
  }
});

// ═══ 로그아웃 ═══
router.post('/logout', (req, res) => {
  req.logout((err) => {
    if (err) return res.status(500).json({ error: '로그아웃 실패' });
    res.json({ success: true });
  });
});

module.exports = router;
