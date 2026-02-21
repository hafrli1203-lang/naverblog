// config/passport.js — SNS 로그인만 (카카오/네이버/구글)
const passport       = require('passport');
const KakaoStrategy  = require('passport-kakao').Strategy;
const NaverStrategy  = require('passport-naver-v2').Strategy;
const GoogleStrategy = require('passport-google-oauth20').Strategy;
const User           = require('../models/User');

passport.serializeUser((user, done) => done(null, user.id));
passport.deserializeUser(async (id, done) => {
  try { done(null, await User.findById(id)); }
  catch (err) { done(err, null); }
});

// ═══ 카카오 ═══
if (process.env.KAKAO_CLIENT_ID) {
  passport.use(new KakaoStrategy({
    clientID: process.env.KAKAO_CLIENT_ID,
    callbackURL: process.env.KAKAO_CALLBACK_URL,
  }, async (accessToken, refreshToken, profile, done) => {
    try {
      let user = await User.findOne({ provider: 'kakao', providerId: String(profile.id) });
      if (!user) {
        user = await User.create({
          provider: 'kakao',
          providerId: String(profile.id),
          displayName: profile.displayName || profile._json?.properties?.nickname || '카카오회원',
          email: profile._json?.kakao_account?.email || null,
          profileImage: profile._json?.properties?.profile_image || '',
        });
      } else {
        user.lastLoginAt = new Date();
        await user.save();
      }
      done(null, user);
    } catch (err) { done(err); }
  }));
}

// ═══ 네이버 ═══
if (process.env.NAVER_LOGIN_CLIENT_ID) {
  passport.use(new NaverStrategy({
    clientID: process.env.NAVER_LOGIN_CLIENT_ID,
    clientSecret: process.env.NAVER_LOGIN_CLIENT_SECRET,
    callbackURL: process.env.NAVER_LOGIN_CALLBACK_URL,
  }, async (accessToken, refreshToken, profile, done) => {
    try {
      let user = await User.findOne({ provider: 'naver', providerId: String(profile.id) });
      if (!user) {
        user = await User.create({
          provider: 'naver',
          providerId: String(profile.id),
          displayName: profile.displayName || profile._json?.name || '네이버회원',
          email: profile._json?.email || null,
          profileImage: profile._json?.profile_image || '',
        });
      } else {
        user.lastLoginAt = new Date();
        await user.save();
      }
      done(null, user);
    } catch (err) { done(err); }
  }));
}

// ═══ 구글 ═══
if (process.env.GOOGLE_CLIENT_ID) {
  passport.use(new GoogleStrategy({
    clientID: process.env.GOOGLE_CLIENT_ID,
    clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    callbackURL: process.env.GOOGLE_CALLBACK_URL,
  }, async (accessToken, refreshToken, profile, done) => {
    try {
      let user = await User.findOne({ provider: 'google', providerId: String(profile.id) });
      if (!user) {
        user = await User.create({
          provider: 'google',
          providerId: String(profile.id),
          displayName: profile.displayName || '구글회원',
          email: profile.emails?.[0]?.value || null,
          profileImage: profile.photos?.[0]?.value || '',
        });
      } else {
        user.lastLoginAt = new Date();
        await user.save();
      }
      done(null, user);
    } catch (err) { done(err); }
  }));
}

module.exports = passport;
