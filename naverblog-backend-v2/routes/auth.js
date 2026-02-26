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

// ═══ 일회성 인증 토큰 생성 (OAuth 콜백 → 메인 페이지 전달용) ═══
async function generateAuthToken(userId, provider) {
  try {
    const token = crypto.randomBytes(32).toString('hex'); // 256비트
    await AuthToken.create({ token, userId, provider, tokenType: 'onetime' });
    console.log('[Auth] Onetime token generated for', provider, '— userId:', userId);
    return token;
  } catch (e) {
    console.error('[Auth] Token 생성 실패:', e.message);
    return null;
  }
}

// ═══ 영속 인증 토큰 생성 (localStorage + Authorization 헤더용, 7일 유효) ═══
async function generatePersistentToken(userId, provider) {
  try {
    const token = crypto.randomBytes(32).toString('hex');
    await AuthToken.create({ token, userId, provider, tokenType: 'persistent' });
    console.log('[Auth] Persistent token generated for', provider, '— userId:', userId);
    return token;
  } catch (e) {
    console.error('[Auth] Persistent token 생성 실패:', e.message);
    return null;
  }
}

// ═══ 사용자 정보 직렬화 헬퍼 ═══
function serializeUser(user) {
  return {
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
  };
}

// ═══ 현재 로그인 상태 ═══
router.get('/me', (req, res) => {
  // req.user는 세션 또는 Authorization 헤더 미들웨어에서 설정됨
  if (!req.user) return res.json({ loggedIn: false });
  res.json({ loggedIn: true, user: serializeUser(req.user) });
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
        return res.redirect(`${FRONTEND_URL}/?login=fail&provider=kakao&error=${encodeURIComponent('session_save_failed: ' + loginErr.message)}`);
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
        return res.redirect(`${FRONTEND_URL}/?login=fail&provider=naver&error=${encodeURIComponent('session_save_failed: ' + loginErr.message)}`);
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
        return res.redirect(`${FRONTEND_URL}/?login=fail&provider=google&error=${encodeURIComponent('session_save_failed: ' + loginErr.message)}`);
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

// ═══ 토큰 교환 → persistent 토큰 발급 (쿠키 완전 불필요) ═══
router.post('/token-exchange', async (req, res) => {
  try {
    const { token } = req.body || {};
    // 토큰 형식 검증 (64자 hex = 32바이트)
    if (!token || typeof token !== 'string' || !/^[0-9a-f]{64}$/.test(token)) {
      return res.status(400).json({ error: 'invalid token format' });
    }
    // 원자적 1회 사용: onetime + used=false인 것만 찾아서 used=true로 변경
    const authToken = await AuthToken.findOneAndUpdate(
      { token, tokenType: 'onetime', used: false },
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
    // onetime 토큰 즉시 삭제
    AuthToken.deleteOne({ _id: authToken._id }).catch(() => {});
    // persistent 토큰 생성 (7일 유효, localStorage + Authorization 헤더용)
    const persistentToken = await generatePersistentToken(user._id, authToken.provider);
    console.log('[Auth] token-exchange 성공 — user:', user._id, user.displayName,
      '| provider:', authToken.provider, '| persistent:', !!persistentToken);
    res.json({
      success: true,
      user: serializeUser(user),
      authToken: persistentToken || null,
    });
  } catch (e) {
    console.error('[Auth] token-exchange 에러:', e);
    res.status(500).json({ error: 'internal error' });
  }
});

// ═══ 로그아웃 ═══
router.post('/logout', async (req, res) => {
  // Authorization 헤더에서 persistent 토큰 추출 → 삭제
  const authHeader = req.headers.authorization || '';
  if (authHeader.startsWith('Bearer ')) {
    const token = authHeader.slice(7);
    try {
      await AuthToken.deleteOne({ token, tokenType: 'persistent' });
      console.log('[Auth] Persistent token 삭제 (로그아웃)');
    } catch (e) {
      console.warn('[Auth] Persistent token 삭제 실패:', e.message);
    }
  }
  // 세션도 파기 (하위 호환)
  req.logout((err) => {
    if (err) return res.status(500).json({ error: '로그아웃 실패' });
    res.json({ success: true });
  });
});

module.exports = router;
