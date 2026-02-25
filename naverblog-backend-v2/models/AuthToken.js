// models/AuthToken.js — OAuth 인증 토큰 (onetime: 팝업→메인 교환용, persistent: 장기 인증용)
const mongoose = require('mongoose');

const authTokenSchema = new mongoose.Schema({
  token:     { type: String, required: true, unique: true, index: true },
  userId:    { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  provider:  { type: String, required: true },
  used:      { type: Boolean, default: false },
  tokenType: { type: String, enum: ['onetime', 'persistent'], default: 'onetime' },
  createdAt: { type: Date, default: Date.now },
});

// TTL 인덱스: onetime → 60초, persistent → 7일 (MongoDB TTL은 스키마 레벨에서 하나만 설정 가능)
// persistent 토큰은 expireAt 필드로 관리
authTokenSchema.index({ createdAt: 1 }, { expireAfterSeconds: 7 * 24 * 60 * 60 }); // 최대 7일 후 자동 삭제

module.exports = mongoose.model('AuthToken', authTokenSchema);
