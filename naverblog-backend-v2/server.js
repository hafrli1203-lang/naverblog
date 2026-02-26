// server.js
require('dotenv').config();
const express    = require('express');
const mongoose   = require('mongoose');
const session    = require('express-session');
const MongoStore = require('connect-mongo');
const helmet     = require('helmet');
const cors       = require('cors');
const passport   = require('./config/passport');
const analytics  = require('./middleware/analytics');

const app = express();
app.set('trust proxy', 1);  // Python 리버스 프록시 뒤에서 동작

// ── 미들웨어 ──
app.use(helmet({ contentSecurityPolicy: false }));
app.use(cors({
  origin: [
    'https://xn--6j1b00mxunnyck8p.com',
    'https://naverblog.onrender.com',
    'http://localhost:5173',
    'http://localhost:8001',
  ],
  credentials: true,
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ── 세션 (MongoDB에 저장) ──
app.use(session({
  secret: process.env.SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  rolling: true,  // 매 응답마다 Set-Cookie 재전송 (프록시 환경 쿠키 유실 복구)
  store: MongoStore.create({ mongoUrl: process.env.MONGODB_URI }),
  cookie: {
    maxAge: 7 * 24 * 60 * 60 * 1000, // 7일
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax', // 같은 도메인 (Python 프록시 경유)
  },
}));

// ── Passport ──
app.use(passport.initialize());
app.use(passport.session());

// ── Authorization: Bearer 토큰 인증 (쿠키 의존 제거) ──
// 세션 인증이 안 된 경우, persistent 토큰으로 req.user 설정
const AuthToken = require('./models/AuthToken');
const User      = require('./models/User');
app.use(async (req, res, next) => {
  // 세션 인증이 이미 되어있으면 스킵
  if (req.isAuthenticated()) return next();
  const authHeader = req.headers.authorization || '';
  if (!authHeader.startsWith('Bearer ')) return next();
  const token = authHeader.slice(7);
  if (!token || !/^[0-9a-f]{64}$/.test(token)) return next();
  try {
    const authToken = await AuthToken.findOne({ token, tokenType: 'persistent' });
    if (!authToken) return next();
    const user = await User.findById(authToken.userId);
    if (!user) return next();
    req.user = user; // req.isAuthenticated()가 true 반환하도록 설정
  } catch (e) {
    // 토큰 검증 실패해도 요청은 계속 진행 (로그인 불필요 API도 있으므로)
  }
  next();
});

// ── 방문 추적 (모든 요청) ──
app.use(analytics.trackPageView);

// ── 라우트 ──
app.use('/auth',     require('./routes/auth'));
app.use('/user-api', require('./routes/api'));   // /api → /user-api (Python 백엔드 /api 충돌 방지)
app.use('/ads',      require('./routes/ads'));
app.use('/admin',    require('./routes/admin'));

// ── 헬스 체크 ──
app.get('/health', (req, res) => res.json({ status: 'ok' }));

// ── 인증 상태 진단 (디버그용) ──
app.get('/auth/status', (req, res) => {
  res.json({
    providers: {
      kakao:  !!process.env.KAKAO_CLIENT_ID,
      naver:  !!process.env.NAVER_LOGIN_CLIENT_ID,
      google: !!process.env.GOOGLE_CLIENT_ID,
    },
    secrets: {
      kakao:  process.env.KAKAO_CLIENT_SECRET ? 'set' : 'empty',
      naver:  process.env.NAVER_LOGIN_CLIENT_SECRET ? 'set' : 'empty',
      google: process.env.GOOGLE_CLIENT_SECRET ? 'set' : 'empty',
    },
    mongodb: mongoose.connection.readyState === 1 ? 'connected' : 'disconnected',
    session: !!process.env.SESSION_SECRET,
    frontendUrl: process.env.FRONTEND_URL || '(not set)',
    callbackUrls: {
      kakao:  process.env.KAKAO_CALLBACK_URL || '(not set)',
      naver:  process.env.NAVER_LOGIN_CALLBACK_URL || '(not set)',
      google: process.env.GOOGLE_CALLBACK_URL || '(not set)',
    },
    uptime: Math.floor(process.uptime()) + 's',
  });
});

// ── 환경변수 검증 ──
const _requiredEnvVars = ['MONGODB_URI', 'SESSION_SECRET'];
for (const key of _requiredEnvVars) {
  if (!process.env[key]) console.error(`[WARN] 필수 환경변수 ${key} 미설정!`);
}
const _oauthProviders = [
  ['KAKAO_CLIENT_ID', 'KAKAO_CALLBACK_URL', '카카오'],
  ['NAVER_LOGIN_CLIENT_ID', 'NAVER_LOGIN_CALLBACK_URL', '네이버'],
  ['GOOGLE_CLIENT_ID', 'GOOGLE_CALLBACK_URL', '구글'],
];
for (const [idKey, cbKey, name] of _oauthProviders) {
  if (process.env[idKey]) {
    console.log(`[Auth] ${name} OAuth 활성화 (callback: ${process.env[cbKey] || 'NOT SET'})`);
    if (!process.env[cbKey]) console.error(`[WARN] ${name} CALLBACK_URL 미설정!`);
  } else {
    console.warn(`[Auth] ${name} OAuth 비활성화 (${idKey} 미설정)`);
  }
}

// ── Express catch-all 에러 핸들러 (Passport 내부 에러 → ?login=fail 리다이렉트) ──
const FRONTEND_URL = process.env.FRONTEND_URL || 'https://xn--6j1b00mxunnyck8p.com';
app.use((err, req, res, next) => {
  console.error('[Express Error]', req.method, req.originalUrl, err.message);
  if (req.originalUrl.startsWith('/auth/')) {
    return res.redirect(`${FRONTEND_URL}/?login=fail&provider=unknown&error=${encodeURIComponent(err.message)}`);
  }
  res.status(500).json({ error: 'Internal Server Error' });
});

// ── DB 연결 + 서버 시작 ──
mongoose.connect(process.env.MONGODB_URI)
  .then(async () => {
    console.log('MongoDB 연결 완료');
    // 인덱스 마이그레이션: 깨진/변경된 인덱스 자동 정리
    try {
      await AuthToken.syncIndexes();
      console.log('[DB] AuthToken 인덱스 동기화 완료');
    } catch (e) {
      console.warn('[DB] AuthToken 인덱스 동기화 실패 (무시):', e.message);
    }
    try {
      await User.syncIndexes();
      console.log('[DB] User 인덱스 동기화 완료 (email_1_provider_1 제거됨)');
    } catch (e) {
      console.warn('[DB] User 인덱스 동기화 실패 (무시):', e.message);
    }
    app.listen(process.env.PORT || 3000, () => {
      console.log('서버 시작:', process.env.PORT || 3000);
    });
  })
  .catch(err => console.error('MongoDB 연결 실패:', err));
