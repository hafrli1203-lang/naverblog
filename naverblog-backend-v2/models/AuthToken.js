// models/AuthToken.js — 일회성 OAuth 토큰 (팝업→메인 페이지 인증 전달)
const mongoose = require('mongoose');

const authTokenSchema = new mongoose.Schema({
  token:     { type: String, required: true, unique: true, index: true },
  userId:    { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  provider:  { type: String, required: true },
  used:      { type: Boolean, default: false },
  createdAt: { type: Date, default: Date.now, expires: 60 }, // TTL 60초 자동 삭제
});

module.exports = mongoose.model('AuthToken', authTokenSchema);
