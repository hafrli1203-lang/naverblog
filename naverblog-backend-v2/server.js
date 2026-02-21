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

// ── 방문 추적 (모든 요청) ──
app.use(analytics.trackPageView);

// ── 라우트 ──
app.use('/auth',     require('./routes/auth'));
app.use('/user-api', require('./routes/api'));   // /api → /user-api (Python 백엔드 /api 충돌 방지)
app.use('/ads',      require('./routes/ads'));
app.use('/admin',    require('./routes/admin'));

// ── 헬스 체크 ──
app.get('/health', (req, res) => res.json({ status: 'ok' }));

// ── DB 연결 + 서버 시작 ──
mongoose.connect(process.env.MONGODB_URI)
  .then(() => {
    console.log('MongoDB 연결 완료');
    app.listen(process.env.PORT || 3000, () => {
      console.log('서버 시작:', process.env.PORT || 3000);
    });
  })
  .catch(err => console.error('MongoDB 연결 실패:', err));
