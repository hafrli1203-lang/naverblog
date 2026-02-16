const API_BASE = window.location.origin;

const getElement = (id) => document.getElementById(id);

// 이메일 주소 클립보드 복사 후 네이버 메일 열기
function copyEmailAndOpen(e) {
  const email = e.currentTarget.dataset.email;
  if (email) {
    navigator.clipboard.writeText(email).then(() => {
      showToast(`${email} 복사됨 — 네이버 메일에서 수신자에 붙여넣기 하세요`);
    }).catch(() => {
      // Fallback
      const ta = document.createElement("textarea");
      ta.value = email;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      showToast(`${email} 복사됨 — 네이버 메일에서 수신자에 붙여넣기 하세요`);
    });
  }
}

// 토스트 알림
function showToast(msg) {
  let toast = document.getElementById("copy-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "copy-toast";
    toast.className = "copy-toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => { toast.classList.remove("show"); }, 3000);
}

// === 블로그 개별 분석 ===
const blogAnalysisBtn = getElement("blog-analysis-btn");
const blogUrlInput = getElement("blog-url-input");
const blogStoreSelect = getElement("blog-store-select");
const blogProgressArea = getElement("blog-progress-area");
const blogProgressStage = getElement("blog-progress-stage");
const blogProgressText = getElement("blog-progress-text");
const blogProgressBarFill = getElement("blog-progress-bar-fill");
const blogAnalysisResult = getElement("blog-analysis-result");

const BA_STAGE_LABELS = {
  rss: "RSS 수집",
  content: "콘텐츠 분석",
  exposure: "노출 검색",
  quality: "품질 검사",
  scoring: "점수 계산",
  done: "완료",
  waiting: "분석 중",
};

const GRADE_COLORS = {
  S: "#FFD700",
  A: "#02CB00",
  B: "#0057FF",
  C: "#F97C00",
  D: "#EB1000",
};

// 매장 목록 로드 (셀렉트 박스용)
async function loadStoresForSelect() {
  try {
    const resp = await fetch(`${API_BASE}/api/stores`);
    if (!resp.ok) return;
    const stores = await resp.json();
    blogStoreSelect.innerHTML = '<option value="">독립 분석 (매장 연계 없음)</option>';
    stores.forEach((s) => {
      const name = s.store_name || `${s.region_text} ${s.category_text}`;
      blogStoreSelect.innerHTML += `<option value="${s.store_id}">${escapeHtml(name)} (${escapeHtml(s.region_text)}/${escapeHtml(s.category_text)})</option>`;
    });
  } catch (err) {
    // 무시
  }
}

blogAnalysisBtn.addEventListener("click", () => {
  const blogUrl = blogUrlInput.value.trim();
  if (!blogUrl) {
    alert("블로그 URL 또는 아이디를 입력하세요.");
    return;
  }

  const storeId = blogStoreSelect.value || "";
  blogAnalysisResult.classList.add("hidden");
  blogProgressArea.classList.remove("hidden");
  blogProgressBarFill.style.width = "0%";
  blogProgressStage.textContent = "";
  blogProgressText.textContent = "분석 시작 중...";
  blogAnalysisBtn.disabled = true;

  const params = new URLSearchParams();
  params.set("blog_url", blogUrl);
  if (storeId) params.set("store_id", storeId);

  const eventSource = new EventSource(`${API_BASE}/api/blog-analysis/stream?${params}`);

  eventSource.addEventListener("progress", (e) => {
    const data = JSON.parse(e.data);
    const stage = BA_STAGE_LABELS[data.stage] || data.stage;
    blogProgressStage.textContent = stage;
    blogProgressText.textContent = data.message;
    if (data.total > 0) {
      const pct = Math.round((data.current / data.total) * 100);
      blogProgressBarFill.style.width = `${pct}%`;
    }
  });

  eventSource.addEventListener("result", (e) => {
    const result = JSON.parse(e.data);
    eventSource.close();
    blogProgressArea.classList.add("hidden");
    blogAnalysisBtn.disabled = false;

    if (result.error) {
      alert("분석 오류: " + result.error);
      return;
    }

    renderBlogAnalysis(result);
    // 매장 목록 갱신
    loadStoresForSelect();
  });

  eventSource.addEventListener("error", () => {
    eventSource.close();
    blogProgressArea.classList.add("hidden");
    blogAnalysisBtn.disabled = false;
    // 동기 폴백
    fallbackBlogAnalysis(blogUrl, storeId);
  });
});

async function fallbackBlogAnalysis(blogUrl, storeId) {
  try {
    blogAnalysisBtn.disabled = true;
    const body = { blog_url: blogUrl };
    if (storeId) body.store_id = parseInt(storeId);

    const resp = await fetch(`${API_BASE}/api/blog-analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!resp.ok) throw new Error("API 요청 실패");
    const result = await resp.json();
    renderBlogAnalysis(result);
  } catch (err) {
    alert("블로그 분석에 실패했습니다. 서버 상태를 확인하세요.");
  } finally {
    blogAnalysisBtn.disabled = false;
  }
}

function renderBlogAnalysis(result) {
  blogAnalysisResult.classList.remove("hidden");

  const score = result.blog_score;
  const gradeColor = GRADE_COLORS[score.grade] || "#999";

  // 헤더
  getElement("ba-blogger-id").textContent = result.blogger_id;
  const blogLink = getElement("ba-blog-link");
  blogLink.textContent = result.blog_url;
  blogLink.href = result.blog_url;

  const modeBadge = getElement("ba-mode-badge");
  if (result.analysis_mode === "store_linked") {
    modeBadge.textContent = "매장 연계";
    modeBadge.className = "ba-mode-badge ba-mode-linked";
  } else {
    modeBadge.textContent = "독립 분석";
    modeBadge.className = "ba-mode-badge ba-mode-standalone";
  }

  // RSS 비활성 안내
  const rssWarning = getElement("ba-rss-warning");
  if (!result.rss_available) {
    rssWarning.classList.remove("hidden");
  } else {
    rssWarning.classList.add("hidden");
  }

  // 등급
  const gradeEl = getElement("ba-grade");
  gradeEl.textContent = score.grade;
  gradeEl.style.background = gradeColor;
  getElement("ba-grade-label").textContent = score.grade_label;
  getElement("ba-total-score").textContent = `${score.total}/100`;

  // 5축 바
  const bd = score.breakdown;
  _setBar("ba-bar-activity", "ba-bar-activity-val", bd.activity.score, bd.activity.max);
  _setBar("ba-bar-content", "ba-bar-content-val", bd.content.score, bd.content.max);
  _setBar("ba-bar-exposure", "ba-bar-exposure-val", bd.exposure.score, bd.exposure.max);
  _setBar("ba-bar-suitability", "ba-bar-suitability-val", bd.suitability.score, bd.suitability.max);
  if (bd.quality) {
    _setBar("ba-bar-quality", "ba-bar-quality-val", bd.quality.score, bd.quality.max);
  }

  // 강점/약점
  const strengthsList = getElement("ba-strengths-list");
  const weaknessesList = getElement("ba-weaknesses-list");
  const insights = result.insights;

  strengthsList.innerHTML = insights.strengths.length > 0
    ? insights.strengths.map((s) => `<li>${escapeHtml(s)}</li>`).join("")
    : "<li>-</li>";
  weaknessesList.innerHTML = insights.weaknesses.length > 0
    ? insights.weaknesses.map((w) => `<li>${escapeHtml(w)}</li>`).join("")
    : "<li>-</li>";
  getElement("ba-recommendation").textContent = insights.recommendation;

  // 활동 상세
  const act = result.activity;
  getElement("ba-activity-details").innerHTML = `
    <div class="ba-detail-item"><span>분석 포스트 (RSS)</span><strong>${act.total_posts}개</strong></div>
    <div class="ba-detail-item"><span>마지막 포스팅</span><strong>${act.days_since_last_post !== null ? act.days_since_last_post + '일 전' : '-'}</strong></div>
    <div class="ba-detail-item"><span>평균 포스팅 간격</span><strong>${act.avg_interval_days !== null ? act.avg_interval_days + '일' : '-'}</strong></div>
    <div class="ba-detail-item"><span>활동 등급</span><strong>${escapeHtml(act.posting_trend)}</strong></div>
  `;

  // 콘텐츠 분석
  const cnt = result.content;
  let topicsHtml = cnt.dominant_topics.length > 0
    ? cnt.dominant_topics.map((t) => `<span class="keyword-chip keyword-chip-a">${escapeHtml(t)}</span>`).join("")
    : "<span>-</span>";

  let postsHtml = "";
  if (cnt.recent_posts && cnt.recent_posts.length > 0) {
    postsHtml = `<div class="ba-recent-posts"><h4>최근 포스트</h4><ul>${cnt.recent_posts.map((p) =>
      `<li><a href="${escapeHtml(p.link)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a> <span class="post-date">${escapeHtml(p.date)}</span></li>`
    ).join("")}</ul></div>`;
  }

  getElement("ba-content-details").innerHTML = `
    <div class="ba-detail-grid">
      <div class="ba-detail-item"><span>맛집 편향률</span><strong>${(cnt.food_bias_rate * 100).toFixed(1)}%</strong></div>
      <div class="ba-detail-item"><span>협찬 비율</span><strong>${(cnt.sponsor_signal_rate * 100).toFixed(1)}%</strong></div>
      <div class="ba-detail-item"><span>주제 다양성</span><strong>${(cnt.topic_diversity * 100).toFixed(0)}%</strong></div>
    </div>
    <div class="ba-topics"><h4>주요 키워드</h4><div class="keyword-list">${topicsHtml}</div></div>
    ${postsHtml}
  `;

  // 노출 현황
  const exp = result.exposure;
  let exposureListHtml = "";
  if (exp.details && exp.details.length > 0) {
    exposureListHtml = exp.details.map((ed) => {
      const rankClass = ed.rank <= 10 ? "rank-high" : ed.rank <= 20 ? "rank-mid" : "rank-none";
      const postHtml = ed.post_link
        ? `<a href="${escapeHtml(ed.post_link)}" target="_blank" rel="noopener" class="post-link">포스트 보기</a>`
        : "";
      return `<div class="exposure-item ${rankClass}">
        <span class="exposure-keyword">${escapeHtml(ed.keyword)}</span>
        <span class="exposure-rank">${ed.rank}위 (+${ed.strength}pt)</span>
        ${postHtml}
      </div>`;
    }).join("");
  } else {
    exposureListHtml = '<p class="empty-text">검색 노출 데이터가 없습니다.</p>';
  }

  getElement("ba-exposure-details").innerHTML = `
    <div class="ba-detail-grid">
      <div class="ba-detail-item"><span>검색 키워드</span><strong>${exp.keywords_checked}개</strong></div>
      <div class="ba-detail-item"><span>노출 키워드</span><strong>${exp.keywords_exposed}개</strong></div>
      <div class="ba-detail-item"><span>1페이지 노출</span><strong>${exp.page1_count}개</strong></div>
      <div class="ba-detail-item"><span>노출 강도 합</span><strong>${exp.strength_sum}pt</strong></div>
    </div>
    <div class="ba-exposure-list">${exposureListHtml}</div>
  `;

  // 품질 검사
  const qual = result.quality || {};
  getElement("ba-quality-details").innerHTML = `
    <div class="ba-detail-grid">
      <div class="ba-detail-item"><span>독창성</span><strong>${qual.originality ?? '-'}/8</strong></div>
      <div class="ba-detail-item"><span>충실도</span><strong>${qual.richness ?? '-'}/7</strong></div>
      <div class="ba-detail-item"><span>품질 점수</span><strong>${qual.score ?? '-'}/15</strong></div>
    </div>
  `;

  // 결과 영역으로 스크롤
  blogAnalysisResult.scrollIntoView({ behavior: "smooth", block: "start" });
}

function _setBar(barId, valId, score, max) {
  const pct = Math.round((score / max) * 100);
  const barEl = getElement(barId);
  const valEl = getElement(valId);
  barEl.style.width = `${pct}%`;
  barEl.style.background = pct >= 70 ? "#02CB00" : pct >= 40 ? "#0057FF" : pct >= 20 ? "#F97C00" : "#EB1000";
  valEl.textContent = `${score}/${max}`;
}

// 탭 전환
document.addEventListener("click", (e) => {
  if (!e.target.classList.contains("ba-tab")) return;
  const tabId = e.target.dataset.tab;

  // 탭 버튼 active 전환
  document.querySelectorAll(".ba-tab").forEach((t) => t.classList.remove("active"));
  e.target.classList.add("active");

  // 탭 콘텐츠 전환
  document.querySelectorAll(".ba-tab-content").forEach((c) => c.classList.remove("active"));
  const tabContent = getElement(tabId);
  if (tabContent) tabContent.classList.add("active");
});

// === SPA 라우팅 ===
const navLinks = document.querySelectorAll(".nav-item");
const pages = document.querySelectorAll(".page");

const PAGE_TITLES = {
  dashboard: "대시보드",
  campaigns: "캠페인",
  settings: "설정",
};

function navigateTo(page) {
  pages.forEach((p) => p.classList.remove("active"));
  navLinks.forEach((l) => l.classList.remove("active"));

  const target = getElement(`page-${page}`);
  if (target) target.classList.add("active");
  const link = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (link) link.classList.add("active");

  const pageTitle = document.querySelector(".page-title");
  if (pageTitle) pageTitle.textContent = PAGE_TITLES[page] || page;

  if (page === "campaigns") loadCampaigns();
}

function handleRouting() {
  const hash = window.location.hash.replace("#", "") || "dashboard";
  navigateTo(hash);
}

window.addEventListener("hashchange", handleRouting);
window.addEventListener("DOMContentLoaded", () => {
  handleRouting();
  loadStoresForSelect();
});

// === 대시보드 요소 ===
const searchBtn = getElement("search-btn");
const regionInput = getElement("region-input");
const topicSelect = getElement("topic-select");
const storeNameInput = getElement("store-name-input");
const keywordInput = getElement("keyword-input");
const resultsArea = getElement("results-area");
const loadingState = document.querySelector(".loading-state");
const progressArea = getElement("progress-area");
const progressStage = getElement("progress-stage");
const progressText = getElement("progress-text");
const progressBarFill = getElement("progress-bar-fill");
const metaArea = getElement("meta-area");
const top20Section = getElement("top20-section");
const pool40Section = getElement("pool40-section");
const top20List = getElement("top20-list");
const pool40List = getElement("pool40-list");
const keywordsArea = getElement("keywords-area");
const guideArea = getElement("guide-area");
const messageTemplateArea = getElement("message-template-area");

// 모달 요소
const detailModal = getElement("detail-modal");
const modalCloseBtn = getElement("modal-close-btn");
const modalBloggerName = getElement("modal-blogger-name");
const modalBlogLink = getElement("modal-blog-link");
const modalScoreDetails = getElement("modal-score-details");

const STAGE_LABELS = {
  search: "키워드 검색",
  broad_search: "확장 후보 수집",
  region_power: "지역 랭킹 파워 수집",
  tier_analysis: "순수체급 분석 중",
  scoring: "점수 계산",
  exposure: "노출 분석",
  finalize: "결과 정리",
  done: "완료",
  waiting: "처리 중",
};

// 현재 뷰 모드 상태
let viewModes = { top20: "list", pool40: "list" };

// 마지막 검색 결과 캐시 (store_id 포함)
let lastResult = null;

// === 검색 (SSE) ===
searchBtn.addEventListener("click", () => {
  const region = regionInput.value.trim();
  const topic = topicSelect.value;
  const keyword = keywordInput.value.trim();
  const storeName = storeNameInput.value.trim();

  if (!region) {
    alert("지역은 필수 입력입니다.");
    return;
  }

  resultsArea.classList.remove("hidden");
  loadingState.classList.remove("hidden");
  top20Section.classList.add("hidden");
  pool40Section.classList.add("hidden");
  metaArea.classList.add("hidden");
  keywordsArea.classList.add("hidden");
  guideArea.classList.add("hidden");
  messageTemplateArea.classList.add("hidden");
  top20List.innerHTML = "";
  pool40List.innerHTML = "";
  progressArea.classList.remove("hidden");
  progressBarFill.style.width = "0%";
  progressStage.textContent = "";
  progressText.textContent = "검색 시작 중...";
  searchBtn.disabled = true;

  const params = new URLSearchParams();
  params.set("region", region);
  if (topic) params.set("topic", topic);
  if (keyword) params.set("keyword", keyword);
  if (storeName) params.set("store_name", storeName);

  const eventSource = new EventSource(`${API_BASE}/api/search/stream?${params}`);

  eventSource.addEventListener("progress", (e) => {
    const data = JSON.parse(e.data);
    const stage = STAGE_LABELS[data.stage] || data.stage;
    progressStage.textContent = stage;
    progressText.textContent = data.message;

    if (data.total > 0) {
      const pct = Math.round((data.current / data.total) * 100);
      progressBarFill.style.width = `${pct}%`;
    }
  });

  eventSource.addEventListener("result", (e) => {
    const result = JSON.parse(e.data);

    if (result.error) {
      alert("분석 오류: " + result.error);
      loadingState.classList.add("hidden");
      progressArea.classList.add("hidden");
      searchBtn.disabled = false;
      eventSource.close();
      return;
    }

    lastResult = result;
    renderResults(result);

    // A/B 키워드 + 가이드 + 메시지 템플릿 로드
    if (result.meta && result.meta.store_id) {
      loadKeywords(result.meta.store_id);
      loadGuide(result.meta.store_id);
      loadMessageTemplate(result.meta.store_id);
    }

    loadingState.classList.add("hidden");
    progressArea.classList.add("hidden");
    searchBtn.disabled = false;
    eventSource.close();
  });

  eventSource.addEventListener("error", () => {
    eventSource.close();
    progressArea.classList.add("hidden");
    fallbackSearch(region, topic, keyword, storeName);
  });
});

async function fallbackSearch(region, topic, keyword, storeName) {
  try {
    const params = new URLSearchParams();
    params.set("region", region);
    if (topic) params.set("topic", topic);
    if (keyword) params.set("keyword", keyword);
    if (storeName) params.set("store_name", storeName);

    const response = await fetch(`${API_BASE}/api/search?${params}`, {
      method: "POST",
    });

    if (!response.ok) throw new Error("API 요청 실패");

    const result = await response.json();
    lastResult = result;
    renderResults(result);

    if (result.meta && result.meta.store_id) {
      loadKeywords(result.meta.store_id);
      loadGuide(result.meta.store_id);
      loadMessageTemplate(result.meta.store_id);
    }
  } catch (error) {
    console.error(error);
    alert("블로거 데이터를 가져오지 못했습니다. 백엔드 서버가 실행 중인지 확인하세요.");
  } finally {
    loadingState.classList.add("hidden");
    searchBtn.disabled = false;
  }
}

// === A/B 키워드 로드 ===
async function loadKeywords(storeId) {
  try {
    const resp = await fetch(`${API_BASE}/api/stores/${storeId}/keywords`);
    if (!resp.ok) return;
    const data = await resp.json();

    getElement("keyword-set-a-label").textContent = `A세트: ${data.set_a_label}`;
    getElement("keyword-set-b-label").textContent = `B세트: ${data.set_b_label}`;

    getElement("keyword-set-a").innerHTML = data.set_a
      .map((kw) => `<span class="keyword-chip keyword-chip-a">${escapeHtml(kw)}</span>`)
      .join("");
    getElement("keyword-set-b").innerHTML = data.set_b
      .map((kw) => `<span class="keyword-chip keyword-chip-b">${escapeHtml(kw)}</span>`)
      .join("");

    keywordsArea.classList.remove("hidden");
  } catch (err) {
    console.error("키워드 로드 실패:", err);
  }
}

// === 가이드 로드 ===
async function loadGuide(storeId) {
  try {
    const resp = await fetch(`${API_BASE}/api/stores/${storeId}/guide`);
    if (!resp.ok) return;
    const data = await resp.json();

    getElement("guide-text").textContent = data.full_guide_text;
    guideArea.classList.remove("hidden");

    // 복사 버튼
    getElement("copy-guide-btn").onclick = async () => {
      try {
        await navigator.clipboard.writeText(data.full_guide_text);
        const btn = getElement("copy-guide-btn");
        btn.textContent = "복사됨!";
        setTimeout(() => { btn.textContent = "가이드 복사"; }, 2000);
      } catch {
        // Fallback
        const ta = document.createElement("textarea");
        ta.value = data.full_guide_text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        const btn = getElement("copy-guide-btn");
        btn.textContent = "복사됨!";
        setTimeout(() => { btn.textContent = "가이드 복사"; }, 2000);
      }
    };
  } catch (err) {
    console.error("가이드 로드 실패:", err);
  }
}

// === 메시지 템플릿 로드 ===
async function loadMessageTemplate(storeId) {
  try {
    const resp = await fetch(`${API_BASE}/api/stores/${storeId}/message-template`);
    if (!resp.ok) return;
    const data = await resp.json();

    getElement("message-template-text").textContent = data.template;
    messageTemplateArea.classList.remove("hidden");

    getElement("copy-template-btn").onclick = async () => {
      try {
        await navigator.clipboard.writeText(data.template);
        const btn = getElement("copy-template-btn");
        btn.textContent = "복사됨!";
        setTimeout(() => { btn.textContent = "템플릿 복사"; }, 2000);
      } catch {
        const ta = document.createElement("textarea");
        ta.value = data.template;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        const btn = getElement("copy-template-btn");
        btn.textContent = "복사됨!";
        setTimeout(() => { btn.textContent = "템플릿 복사"; }, 2000);
      }
    };
  } catch (err) {
    console.error("메시지 템플릿 로드 실패:", err);
  }
}

// === 결과 렌더링 ===
function renderResults(result) {
  const top20 = result.top20 || [];
  const pool40 = result.pool40 || [];
  const meta = result.meta || {};

  if (top20.length === 0 && pool40.length === 0) {
    top20Section.classList.remove("hidden");
    top20List.innerHTML = '<p class="empty-text">검색 결과가 없습니다.</p>';
    return;
  }

  // 메타 정보
  metaArea.classList.remove("hidden");
  getElement("meta-store").textContent = `총 ${top20.length + pool40.length}명 분석 완료`;
  getElement("meta-calls").textContent = meta.seed_calls ? `API 호출: ${meta.seed_calls + (meta.exposure_calls || 0)}회` : "";
  getElement("meta-keywords").textContent = meta.total_keywords ? `검색 키워드: ${meta.total_keywords}개` : "";

  // Top20
  if (top20.length > 0) {
    top20Section.classList.remove("hidden");
    renderBloggerList(top20List, top20, true, "top20");
  }

  // Pool40
  if (pool40.length > 0) {
    pool40Section.classList.remove("hidden");
    renderBloggerList(pool40List, pool40, false, "pool40");
  }
}

function renderBloggerList(container, bloggers, isTop, sectionKey) {
  const mode = viewModes[sectionKey] || "list";
  if (mode === "card") {
    container.className = "grid-layout";
    container.innerHTML = bloggers.map((b, idx) => renderBloggerCard(b, idx + 1, isTop)).join("");
  } else {
    container.className = "list-layout";
    container.innerHTML = bloggers.map((b, idx) => renderBloggerListRow(b, idx + 1, isTop)).join("");
  }
  attachCardEvents(container, bloggers);
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderBloggerCard(blogger, rank, isTop) {
  const blogUrl = blogger.blog_url || `https://blog.naver.com/${blogger.blogger_id}`;
  const perfScore = blogger.golden_score || blogger.performance_score || 0;
  const grade = blogger.grade || "";
  const gradeColor = GRADE_COLORS[grade] || "#999";
  const tags = blogger.tags || [];
  const tierGrade = blogger.tier_grade || "D";
  const tierColor = GRADE_COLORS[tierGrade] || "#999";

  // 배지
  const badges = [];
  badges.push(`<span class="tier-badge" style="background:${tierColor}">${tierGrade}</span>`);
  if (isTop) badges.push('<span class="badge-recommend">강한 추천</span>');
  tags.forEach((tag) => {
    if (tag === "맛집편향") badges.push('<span class="badge-food">맛집편향</span>');
    else if (tag === "협찬성향") badges.push('<span class="badge-sponsor">협찬성향</span>');
    else if (tag === "노출안정") badges.push('<span class="badge-stable">노출안정</span>');
    else if (tag === "미노출") badges.push('<span class="badge-unexposed">미노출</span>');
    else if (tag === "고체급") badges.push('<span class="badge-stable">고체급</span>');
    else if (tag === "저체급") badges.push('<span class="badge-unexposed">저체급</span>');
  });

  // Performance Score 바
  const perfPct = Math.min(100, perfScore);
  const perfColor = perfScore >= 70 ? "#02CB00" : perfScore >= 40 ? "#0057FF" : perfScore >= 20 ? "#F97C00" : "#EB1000";

  // 쪽지/메일 URL
  const msgUrl = `https://note.naver.com`;
  const naverMailUrl = `https://mail.naver.com`;
  const bloggerEmail = `${blogger.blogger_id}@naver.com`;

  return `
  <div class="blogger-card ${isTop ? 'top20-card' : ''}">
    <div class="blogger-header">
      <div class="blogger-rank">#${rank}</div>
      <div>
        <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener" class="blogger-name">${escapeHtml(blogger.blogger_id)}</a>
        ${badges.join("")}
      </div>
      <div class="score-badge" style="color:${gradeColor}">${grade} ${perfScore}</div>
    </div>

    <div class="perf-bar-container">
      <div class="perf-bar-track">
        <div class="perf-bar-fill" style="width:${perfPct}%; background:${perfColor}"></div>
      </div>
      <span class="perf-bar-label">GS v4.0 ${perfScore}/100</span>
    </div>

    <div class="card-actions">
      <button class="detail-btn" data-id="${escapeHtml(blogger.blogger_id)}">상세 보기</button>
      <a href="${escapeHtml(msgUrl)}" target="_blank" rel="noopener" class="msg-btn">쪽지</a>
      <a href="${escapeHtml(naverMailUrl)}" target="_blank" rel="noopener" class="mail-btn" data-email="${escapeHtml(bloggerEmail)}" onclick="copyEmailAndOpen(event)">메일</a>
    </div>
  </div>`;
}

function renderBloggerListRow(blogger, rank, isTop) {
  const blogUrl = blogger.blog_url || `https://blog.naver.com/${blogger.blogger_id}`;
  const perf = blogger.golden_score || blogger.performance_score || 0;
  const grade = blogger.grade || "";
  const gradeColor = GRADE_COLORS[grade] || "#999";
  const tags = blogger.tags || [];
  const msgUrl = `https://note.naver.com`;
  const naverMailUrl = `https://mail.naver.com`;
  const bloggerEmail = `${blogger.blogger_id}@naver.com`;
  const tierGrade = blogger.tier_grade || "D";
  const tierColor = GRADE_COLORS[tierGrade] || "#999";

  // 배지
  const badges = [];
  badges.push(`<span class="tier-badge" style="background:${tierColor}">${tierGrade}</span>`);
  if (isTop) badges.push('<span class="badge-recommend">강한 추천</span>');
  tags.forEach((tag) => {
    if (tag === "맛집편향") badges.push('<span class="badge-food">맛집편향</span>');
    else if (tag === "협찬성향") badges.push('<span class="badge-sponsor">협찬성향</span>');
    else if (tag === "노출안정") badges.push('<span class="badge-stable">노출안정</span>');
    else if (tag === "미노출") badges.push('<span class="badge-unexposed">미노출</span>');
    else if (tag === "고체급") badges.push('<span class="badge-stable">고체급</span>');
    else if (tag === "저체급") badges.push('<span class="badge-unexposed">저체급</span>');
  });

  return `
  <div class="list-row">
    <span class="list-rank">#${rank}</span>
    <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener" class="list-id">${escapeHtml(blogger.blogger_id)}</a>
    <span class="list-perf" style="color:${gradeColor}">${grade} ${perf}</span>
    <span class="list-badges">${badges.join("")}</span>
    <button class="detail-btn-sm list-detail-btn" data-id="${escapeHtml(blogger.blogger_id)}">상세</button>
    <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener" class="list-url">블로그</a>
    <a href="${escapeHtml(msgUrl)}" target="_blank" rel="noopener" class="list-url list-msg">쪽지</a>
    <a href="${escapeHtml(naverMailUrl)}" target="_blank" rel="noopener" class="list-url list-mail" data-email="${escapeHtml(bloggerEmail)}" onclick="copyEmailAndOpen(event)">메일</a>
  </div>`;
}

function attachCardEvents(container, bloggers) {
  container.querySelectorAll(".detail-btn, .list-detail-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const blogger = bloggers.find((b) => b.blogger_id === btn.dataset.id);
      if (blogger) openDetailModal(blogger);
    });
  });
}

// === 뷰 토글 ===
document.addEventListener("click", (e) => {
  if (!e.target.classList.contains("view-btn")) return;
  const view = e.target.dataset.view;
  const target = e.target.dataset.target;

  // 버튼 active 상태 업데이트
  e.target.closest(".view-toggle").querySelectorAll(".view-btn").forEach((b) => b.classList.remove("active"));
  e.target.classList.add("active");

  viewModes[target] = view;

  // 재렌더링
  if (lastResult) {
    if (target === "top20" && lastResult.top20) {
      renderBloggerList(top20List, lastResult.top20, true, "top20");
    } else if (target === "pool40" && lastResult.pool40) {
      renderBloggerList(pool40List, lastResult.pool40, false, "pool40");
    }
  }
});

// === 상세 모달 ===
function openDetailModal(blogger) {
  const blogUrl = blogger.blog_url || `https://blog.naver.com/${blogger.blogger_id}`;
  modalBloggerName.textContent = blogger.blogger_id;
  modalBlogLink.textContent = blogUrl;
  modalBlogLink.href = blogUrl;

  const perf = blogger.golden_score || blogger.performance_score || 0;
  const tags = (blogger.tags || []).join(", ") || "없음";
  const exposureDetails = blogger.exposure_details || [];

  const tierGrade = blogger.tier_grade || "D";
  const tierScore = blogger.tier_score != null ? blogger.tier_score.toFixed(1) : "0.0";
  const tierBadgeColor = GRADE_COLORS[tierGrade] || "#999";

  modalScoreDetails.innerHTML = `
    <div class="modal-score-item"><span>Golden Score v4.0</span><strong>${perf}/100</strong></div>
    <div class="modal-score-item"><span>순수체급</span><strong><span class="tier-badge" style="background:${tierBadgeColor}">${tierGrade}</span> ${tierScore}/40</strong></div>
    <hr/>
    <div class="modal-score-item"><span>Strength Sum</span><strong>${blogger.strength_sum || 0}</strong></div>
    <div class="modal-score-item"><span>1페이지 노출 키워드</span><strong>${blogger.page1_keywords_30d || 0}개</strong></div>
    <div class="modal-score-item"><span>노출 키워드</span><strong>${blogger.exposed_keywords_30d || 0}개</strong></div>
    <div class="modal-score-item"><span>최고 순위</span><strong>${blogger.best_rank ? blogger.best_rank + '위' : '-'}</strong></div>
    <div class="modal-score-item"><span>최고 순위 키워드</span><strong>${escapeHtml(blogger.best_rank_keyword || '-')}</strong></div>
    <hr/>
    <div class="modal-score-item"><span>맛집 편향률</span><strong>${((blogger.food_bias_rate || 0) * 100).toFixed(1)}%</strong></div>
    <div class="modal-score-item"><span>협찬 신호율</span><strong>${((blogger.sponsor_signal_rate || 0) * 100).toFixed(1)}%</strong></div>
    <div class="modal-score-item"><span>태그</span><strong>${escapeHtml(tags)}</strong></div>
  `;

  // 키워드별 노출 현황
  const modalExposure = getElement("modal-exposure-details");
  if (exposureDetails.length > 0) {
    modalExposure.innerHTML = `
      <h3>키워드별 노출 현황</h3>
      ${exposureDetails.map((ed) => {
        const rankClass = ed.rank <= 10 ? "rank-high" : ed.rank <= 20 ? "rank-mid" : "rank-none";
        const postHtml = ed.post_link
          ? `<a href="${escapeHtml(ed.post_link)}" target="_blank" rel="noopener" class="post-link">포스트 보기</a>`
          : "";
        return `<div class="exposure-item ${rankClass}">
          <span class="exposure-keyword">${escapeHtml(ed.keyword)}</span>
          <span class="exposure-rank">${ed.rank}위 (+${ed.strength_points}pt)</span>
          ${postHtml}
        </div>`;
      }).join("")}
    `;
  } else {
    modalExposure.innerHTML = "";
  }

  // 쪽지/메일 버튼
  const msgUrl = `https://note.naver.com`;
  const naverMailUrl = `https://mail.naver.com`;
  const bloggerEmail = `${blogger.blogger_id}@naver.com`;
  const modalActions = getElement("modal-actions-row");
  modalActions.innerHTML = `
    <a href="${escapeHtml(msgUrl)}" target="_blank" rel="noopener" class="modal-action-btn modal-msg-btn">쪽지 보내기</a>
    <a href="${escapeHtml(naverMailUrl)}" target="_blank" rel="noopener" class="modal-action-btn modal-mail-btn" data-email="${escapeHtml(bloggerEmail)}" onclick="copyEmailAndOpen(event)">메일 보내기</a>
  `;

  detailModal.classList.remove("hidden");
}

modalCloseBtn.addEventListener("click", () => {
  detailModal.classList.add("hidden");
});

detailModal.addEventListener("click", (e) => {
  if (e.target === detailModal) {
    detailModal.classList.add("hidden");
  }
});

// === 캠페인 페이지 ===
const createCampaignBtn = getElement("create-campaign-btn");
const campaignActionsEl = createCampaignBtn.parentElement;
const campaignForm = getElement("campaign-form");
const saveCampaignBtn = getElement("save-campaign-btn");
const cancelCampaignBtn = getElement("cancel-campaign-btn");
const campaignListEl = getElement("campaign-list");
const campaignDetail = getElement("campaign-detail");
const backToCampaigns = getElement("back-to-campaigns");

createCampaignBtn.addEventListener("click", () => {
  campaignForm.classList.toggle("hidden");
});

cancelCampaignBtn.addEventListener("click", () => {
  campaignForm.classList.add("hidden");
});

saveCampaignBtn.addEventListener("click", async () => {
  const name = getElement("campaign-name").value.trim();
  const region = getElement("campaign-region").value.trim();
  const category = getElement("campaign-category").value.trim();
  const memo = getElement("campaign-memo").value.trim();

  if (!name || !region || !category) {
    alert("이름, 지역, 카테고리를 모두 입력하세요.");
    return;
  }

  try {
    const resp = await fetch(`${API_BASE}/api/campaigns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, region, category, memo }),
    });

    if (resp.ok) {
      campaignForm.classList.add("hidden");
      getElement("campaign-name").value = "";
      getElement("campaign-region").value = "";
      getElement("campaign-category").value = "";
      getElement("campaign-memo").value = "";
      loadCampaigns();
    }
  } catch (err) {
    alert("캠페인 생성 실패");
  }
});

async function loadCampaigns() {
  try {
    const resp = await fetch(`${API_BASE}/api/campaigns`);
    const campaigns = await resp.json();

    if (campaigns.length === 0) {
      campaignListEl.innerHTML = '<p class="empty-text">아직 캠페인이 없습니다. 새 캠페인을 만들어보세요.</p>';
    } else {
      campaignListEl.innerHTML = campaigns
        .map(
          (c) => `
          <div class="campaign-card" data-id="${escapeHtml(c.id)}">
            <div class="campaign-card-header">
              <h3>${escapeHtml(c.name)}</h3>
              <span class="status-badge status-${c.status === '진행중' ? 'active' : c.status === '완료' ? 'done' : 'paused'}">${escapeHtml(c.status)}</span>
            </div>
            <p class="campaign-card-meta">${escapeHtml(c.region)} / ${escapeHtml(c.category)}</p>
            <p class="campaign-card-stats">${escapeHtml(c.created_at)}</p>
            <div class="campaign-card-actions">
              <button class="detail-btn campaign-view-btn" data-id="${escapeHtml(c.id)}">상세보기</button>
              <button class="danger-btn-sm campaign-delete-btn" data-id="${escapeHtml(c.id)}">삭제</button>
            </div>
          </div>`
        )
        .join("");

      campaignListEl.querySelectorAll(".campaign-view-btn").forEach((btn) => {
        btn.addEventListener("click", () => openCampaignDetail(btn.dataset.id));
      });

      campaignListEl.querySelectorAll(".campaign-delete-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          if (confirm("이 캠페인을 삭제하시겠습니까?")) {
            await fetch(`${API_BASE}/api/campaigns/${btn.dataset.id}`, { method: "DELETE" });
            loadCampaigns();
          }
        });
      });
    }
  } catch (err) {
    campaignListEl.innerHTML = '<p class="empty-text">캠페인 목록을 불러올 수 없습니다.</p>';
  }
}

async function openCampaignDetail(campaignId) {
  try {
    const resp = await fetch(`${API_BASE}/api/campaigns/${campaignId}`);
    const campaign = await resp.json();

    campaignListEl.classList.add("hidden");
    campaignActionsEl.classList.add("hidden");
    campaignForm.classList.add("hidden");
    campaignDetail.classList.remove("hidden");
    campaignDetail.dataset.id = campaignId;

    getElement("campaign-detail-name").textContent = campaign.name;
    getElement("campaign-detail-status").textContent = campaign.status;
    getElement("campaign-detail-status").className = `status-badge status-${campaign.status === '진행중' ? 'active' : campaign.status === '완료' ? 'done' : 'paused'}`;
    getElement("campaign-detail-info").textContent = `${campaign.region} / ${campaign.category} | 생성: ${campaign.created_at}`;
    getElement("campaign-detail-memo").textContent = campaign.memo || "";

    // Top20 렌더링
    const top20El = getElement("campaign-top20");
    if (campaign.top20 && campaign.top20.length > 0) {
      top20El.className = "grid-layout";
      top20El.innerHTML = campaign.top20.map((b, i) => renderBloggerCard(b, i + 1, true)).join("");
      attachCardEvents(top20El, campaign.top20);
    } else {
      top20El.innerHTML = '<p class="empty-text">아직 분석 데이터가 없습니다. 대시보드에서 분석을 실행하세요.</p>';
    }

    // Pool40 렌더링
    const pool40El = getElement("campaign-pool40");
    if (campaign.pool40 && campaign.pool40.length > 0) {
      pool40El.className = "grid-layout";
      pool40El.innerHTML = campaign.pool40.map((b, i) => renderBloggerCard(b, i + 1, false)).join("");
      attachCardEvents(pool40El, campaign.pool40);
    } else {
      pool40El.innerHTML = '<p class="empty-text">운영 풀 데이터가 없습니다.</p>';
    }
  } catch (err) {
    alert("캠페인 상세 정보를 불러올 수 없습니다.");
  }
}

backToCampaigns.addEventListener("click", () => {
  campaignDetail.classList.add("hidden");
  campaignListEl.classList.remove("hidden");
  campaignActionsEl.classList.remove("hidden");
  loadCampaigns();
});

// === 설정 페이지 ===

getElement("export-data-btn").addEventListener("click", async () => {
  try {
    const resp = await fetch(`${API_BASE}/api/campaigns`);
    const data = await resp.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `campaigns_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("데이터 내보내기 실패");
  }
});

getElement("reset-data-btn").addEventListener("click", async () => {
  if (confirm("모든 캠페인 데이터를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")) {
    try {
      const resp = await fetch(`${API_BASE}/api/campaigns`);
      const campaigns = await resp.json();
      for (const c of campaigns) {
        await fetch(`${API_BASE}/api/campaigns/${c.id}`, { method: "DELETE" });
      }
      alert("모든 캠페인이 삭제되었습니다.");
    } catch (err) {
      alert("초기화 실패");
    }
  }
});
