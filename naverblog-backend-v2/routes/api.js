// routes/api.js
const router = require('express').Router();
const User   = require('../models/User');
const { trackSearch, trackEvent } = require('../middleware/analytics');

function requireAuth(req, res, next) {
  if (!req.isAuthenticated()) return res.status(401).json({ error: '로그인이 필요합니다.' });
  next();
}

// ═══ 검색 히스토리 ═══
router.get('/history', requireAuth, async (req, res) => {
  const user = await User.findById(req.user._id).select('searchHistory');
  res.json(user.searchHistory.slice(-50).reverse());
});

router.post('/history', requireAuth, async (req, res) => {
  const { region, topic, storeName, keyword, resultCount } = req.body;
  await User.findByIdAndUpdate(req.user._id, {
    $push: { searchHistory: { $each: [{ region, topic, storeName, keyword }], $slice: -100 } }
  });
  // 검색 로그 (관리자 분석용)
  trackSearch(req.user._id, { region, topic, storeName, keyword, resultCount });
  res.json({ success: true });
});

// ═══ 저장한 블로거 ═══
router.get('/bloggers', requireAuth, async (req, res) => {
  const user = await User.findById(req.user._id).select('savedBloggers');
  res.json(user.savedBloggers);
});

router.post('/bloggers', requireAuth, async (req, res) => {
  const { blogId, blogName, score, grade } = req.body;
  await User.findByIdAndUpdate(req.user._id, {
    $push: { savedBloggers: { blogId, blogName, score, grade } }
  });
  trackEvent(req.user._id, 'blogger_save', { blogId });
  res.json({ success: true });
});

router.delete('/bloggers/:blogId', requireAuth, async (req, res) => {
  await User.findByIdAndUpdate(req.user._id, {
    $pull: { savedBloggers: { blogId: req.params.blogId } }
  });
  res.json({ success: true });
});

// ═══ 캠페인 ═══
router.get('/campaigns', requireAuth, async (req, res) => {
  const user = await User.findById(req.user._id).select('campaigns');
  res.json(user.campaigns);
});

router.post('/campaigns', requireAuth, async (req, res) => {
  const { name, region, category, memo } = req.body;
  const user = await User.findByIdAndUpdate(
    req.user._id,
    { $push: { campaigns: { name, region, category, memo, bloggers: [] } } },
    { new: true }
  );
  trackEvent(req.user._id, 'campaign_create', { name, region });
  res.json(user.campaigns[user.campaigns.length - 1]);
});

router.put('/campaigns/:id', requireAuth, async (req, res) => {
  const user = await User.findById(req.user._id);
  const campaign = user.campaigns.id(req.params.id);
  if (!campaign) return res.status(404).json({ error: '캠페인 없음' });
  Object.assign(campaign, req.body);
  await user.save();
  res.json(campaign);
});

router.delete('/campaigns/:id', requireAuth, async (req, res) => {
  await User.findByIdAndUpdate(req.user._id, { $pull: { campaigns: { _id: req.params.id } } });
  res.json({ success: true });
});

// ═══ 프로필 관리 ═══
router.get('/profile', requireAuth, async (req, res) => {
  const user = await User.findById(req.user._id).select(
    'displayName email profileImage provider userType businessType businessRegion blogUrl snsUrls desiredRate bio specialties phone plan role'
  );
  if (!user) return res.status(404).json({ error: '사용자를 찾을 수 없습니다.' });
  res.json(user);
});

router.put('/profile', requireAuth, async (req, res) => {
  const allowed = ['businessType', 'businessRegion', 'blogUrl', 'snsUrls', 'desiredRate', 'bio', 'specialties', 'phone', 'displayName'];
  const updates = {};
  for (const key of allowed) {
    if (req.body[key] !== undefined) updates[key] = req.body[key];
  }
  const user = await User.findByIdAndUpdate(req.user._id, { $set: updates }, { new: true }).select(
    'displayName email profileImage provider userType businessType businessRegion blogUrl snsUrls desiredRate bio specialties phone plan role'
  );
  trackEvent(req.user._id, 'profile_update', updates);
  res.json(user);
});

router.put('/profile/type', requireAuth, async (req, res) => {
  const { userType, businessType, businessRegion, blogUrl, desiredRate, bio, specialties } = req.body;
  if (!['owner', 'influencer'].includes(userType)) {
    return res.status(400).json({ error: '유효하지 않은 유형입니다. (owner/influencer)' });
  }
  const user = await User.findById(req.user._id);
  if (user.userType) {
    return res.status(400).json({ error: '이미 유형이 설정되어 있습니다.' });
  }
  const updates = { userType };
  if (userType === 'owner') {
    if (businessType) updates.businessType = businessType;
    if (businessRegion) updates.businessRegion = businessRegion;
  } else {
    if (blogUrl) updates.blogUrl = blogUrl;
    if (desiredRate) updates.desiredRate = desiredRate;
    if (bio) updates.bio = bio;
    if (specialties) updates.specialties = specialties;
  }
  const updated = await User.findByIdAndUpdate(req.user._id, { $set: updates }, { new: true }).select(
    'displayName email profileImage provider userType businessType businessRegion blogUrl snsUrls desiredRate bio specialties phone plan role'
  );
  trackEvent(req.user._id, 'user_type_set', { userType });
  res.json(updated);
});

// ═══ 플랜 업그레이드 (관리자 전용) ═══
router.put('/profile/plan', requireAuth, async (req, res) => {
  const user = await User.findById(req.user._id);
  if (user.role !== 'admin') {
    return res.status(403).json({ error: '관리자만 접근 가능합니다.' });
  }
  const { userId, plan } = req.body;
  if (!['free', 'pro'].includes(plan)) {
    return res.status(400).json({ error: '유효하지 않은 플랜입니다.' });
  }
  await User.findByIdAndUpdate(userId, { $set: { plan } });
  trackEvent(req.user._id, 'plan_change', { targetUser: userId, plan });
  res.json({ success: true });
});

module.exports = router;
