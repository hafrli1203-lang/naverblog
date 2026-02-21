// routes/ads.js
const router = require('express').Router();
const Ad     = require('../models/Ad');
const { inferBusinessType } = require('../config/businessTypeMap');

// ═══ 광고 매칭 — 방문자 업종에 맞는 광고 조회 ═══
router.get('/match', async (req, res) => {
  try {
    const { topic, region, keyword, placement } = req.query;
    const now = new Date();
    const visitorTypes = inferBusinessType(topic, keyword);

    const query = {
      isActive:  true,
      startDate: { $lte: now },
      endDate:   { $gte: now },
    };
    if (placement) query.placement = placement;

    // 방문자 업종에 맞거나 "all"(전업종)인 광고
    query.$or = [
      { 'targeting.businessTypes': { $in: visitorTypes } },
      { 'targeting.businessTypes': 'all' },
    ];

    // 지역 필터 (빈 배열 = 전국)
    if (region) {
      query.$and = [{
        $or: [
          { 'targeting.regions': { $size: 0 } },
          { 'targeting.regions': { $exists: false } },
          { 'targeting.regions': { $in: [region] } },
        ]
      }];
    }

    const ads = await Ad.find(query)
      .sort({ priority: -1, createdAt: -1 })
      .limit(2)
      .select('title description imageUrl linkUrl ctaText type placement');

    res.json(ads);
  } catch (err) {
    res.status(500).json({ error: '광고 조회 실패' });
  }
});

// ═══ 노출 기록 ═══
router.post('/impression/:adId', async (req, res) => {
  try {
    const today = new Date().toISOString().slice(0, 10);
    const adId  = req.params.adId;
    await Ad.findByIdAndUpdate(adId, { $inc: { 'stats.impressions': 1 } });
    const r = await Ad.updateOne(
      { _id: adId, 'stats.daily.date': today },
      { $inc: { 'stats.daily.$.impressions': 1 } }
    );
    if (r.modifiedCount === 0) {
      await Ad.updateOne({ _id: adId },
        { $push: { 'stats.daily': { date: today, impressions: 1, clicks: 0 } } });
    }
    res.json({ ok: true });
  } catch (err) { res.status(500).json({ error: '기록 실패' }); }
});

// ═══ 클릭 기록 ═══
router.post('/click/:adId', async (req, res) => {
  try {
    const today = new Date().toISOString().slice(0, 10);
    const adId  = req.params.adId;
    const ad = await Ad.findByIdAndUpdate(adId, { $inc: { 'stats.clicks': 1 } }, { new: true });
    const r = await Ad.updateOne(
      { _id: adId, 'stats.daily.date': today },
      { $inc: { 'stats.daily.$.clicks': 1 } }
    );
    if (r.modifiedCount === 0) {
      await Ad.updateOne({ _id: adId },
        { $push: { 'stats.daily': { date: today, impressions: 0, clicks: 1 } } });
    }
    res.json({ redirectUrl: ad?.linkUrl || '' });
  } catch (err) { res.status(500).json({ error: '기록 실패' }); }
});

module.exports = router;
