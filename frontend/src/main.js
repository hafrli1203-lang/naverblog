const API_BASE = window.location.origin;
// Auth/Ads/Admin → Python 서버가 Node.js로 프록시 (같은 도메인, 쿠키 문제 없음)
const AUTH_BASE = window.location.origin;

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
  "S+": "#2B4C7E",
  S: "#3B7DD8",
  A: "#4A8B6F",
  "B+": "#8B8A3C",
  B: "#C2883D",
  C: "#C0392B",
  D: "#7B4040",
  F: "#5C2626",
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
  if (!requireLogin()) return;

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

  // v7.2: Base Score + Category Bonus 표시
  const baseScore71 = score.base_score != null ? score.base_score : score.total;
  const catBonus = score.category_bonus;
  const finalScore = score.final_score != null ? score.final_score : score.total;
  if (catBonus != null && catBonus > 0) {
    getElement("ba-total-score").textContent = `${finalScore} (Base ${baseScore71} + 업종 +${catBonus})`;
  } else {
    getElement("ba-total-score").textContent = `${baseScore71}/100`;
  }

  // v7.2: Base Score 바 (base_breakdown 우선, fallback: breakdown)
  const bd = score.base_breakdown || score.breakdown || {};
  const barsContainer = getElement("ba-bars-container");
  barsContainer.innerHTML = "";
  const barKeys = Object.keys(bd);
  barKeys.forEach((key, idx) => {
    const axis = bd[key];
    const barId = `ba-bar-dyn-${idx}`;
    const valId = `ba-bar-dyn-val-${idx}`;
    const label = axis.label || key;
    const isNeg = (axis.max || 0) <= 0;
    const row = document.createElement("div");
    row.className = "ba-bar-row";
    row.innerHTML = `
      <span class="ba-bar-label">${escapeHtml(label)}</span>
      <div class="ba-bar-track"><div id="${barId}" class="ba-bar-fill"></div></div>
      <span id="${valId}" class="ba-bar-value"></span>
    `;
    barsContainer.appendChild(row);
    if (isNeg) {
      // 감점 항목 (game_defense): 별도 렌더링
      const barEl = getElement(barId);
      const valEl = getElement(valId);
      const absPct = Math.min(100, Math.abs(axis.score) * 10);
      barEl.style.width = `${absPct}%`;
      barEl.style.background = "#EB1000";
      valEl.textContent = `${axis.score}`;
    } else {
      _setBar(barId, valId, axis.score, axis.max);
    }
  });

  // v7.2: Category Bonus 바 (bonus_breakdown)
  const bonusBd = score.bonus_breakdown;
  if (bonusBd) {
    const bonusHeader = document.createElement("div");
    bonusHeader.className = "ba-bar-row";
    bonusHeader.innerHTML = `<span class="ba-bar-label" style="font-weight:600;color:var(--accent)">업종 보너스 +${catBonus}</span><div class="ba-bar-track"></div><span class="ba-bar-value"></span>`;
    barsContainer.appendChild(bonusHeader);
    Object.keys(bonusBd).forEach((key, idx) => {
      const axis = bonusBd[key];
      const barId = `ba-bar-bonus-${idx}`;
      const valId = `ba-bar-bonus-val-${idx}`;
      const label = axis.label || key;
      const row = document.createElement("div");
      row.className = "ba-bar-row";
      row.innerHTML = `
        <span class="ba-bar-label">${escapeHtml(label)}</span>
        <div class="ba-bar-track"><div id="${barId}" class="ba-bar-fill"></div></div>
        <span id="${valId}" class="ba-bar-value"></span>
      `;
      barsContainer.appendChild(row);
      _setBar(barId, valId, axis.score, axis.max);
    });
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
  barEl.style.background = pct >= 70 ? "#3B7DD8" : pct >= 40 ? "#4A8B6F" : pct >= 20 ? "#C2883D" : "#C0392B";
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

// === GoldenScore FAQ 아코디언 ===
document.addEventListener("click", (e) => {
  const q = e.target.closest(".gs-faq-q");
  if (!q) return;
  const item = q.closest(".gs-faq-item");
  if (!item) return;
  // 다른 열린 항목 닫기
  document.querySelectorAll(".gs-faq-item.open").forEach((i) => {
    if (i !== item) i.classList.remove("open");
  });
  item.classList.toggle("open");
});

// === SPA 라우팅 ===
const navLinks = document.querySelectorAll(".sidebar-nav-item, .top-bar-link.nav-item");
const pages = document.querySelectorAll(".page");

const PAGE_TITLES = {
  dashboard: "체험단검색",
  "blog-analysis": "블로그분석",
  campaigns: "내 체험단",
  goldenscore: "이용가이드",
  admin: "관리자",
  settings: "설정",
};

function navigateTo(page) {
  pages.forEach((p) => p.classList.remove("active"));
  navLinks.forEach((l) => l.classList.remove("active"));

  const target = getElement(`page-${page}`);
  if (target) target.classList.add("active");

  // 사이드바 + 상단바 모두에서 active 적용
  document.querySelectorAll(`[data-page="${page}"]`).forEach((el) => el.classList.add("active"));

  // 상단바 타이틀 업데이트
  const titleEl = getElement("top-bar-title");
  if (titleEl) titleEl.textContent = PAGE_TITLES[page] || page;

  // 모바일 사이드바 닫기
  const sidebar = getElement("app-sidebar");
  if (sidebar) sidebar.classList.remove("open");

  if (page === "campaigns") { renderFavorites(); }
  if (page === "blog-analysis") { loadStoresForSelect(); loadCampaigns(); }
  if (page === "admin") { refreshAdminDashboard(); }
}

function handleRouting() {
  const hash = window.location.hash.replace("#", "") || "dashboard";
  navigateTo(hash);
}

window.addEventListener("hashchange", handleRouting);
window.addEventListener("DOMContentLoaded", () => {
  handleRouting();
  loadStoresForSelect();
  loadRecentSearches();
  initSearchHeroVisibility();
  updateFavCount();
  checkAuth();

  // 모바일 햄버거 메뉴 토글
  const mobileMenuBtn = getElement("mobile-menu-btn");
  if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener("click", () => {
      const sidebar = getElement("app-sidebar");
      if (sidebar) sidebar.classList.toggle("open");
    });
  }

  // 새 검색 버튼
  const newSearchBtn = getElement("new-search-btn");
  if (newSearchBtn) {
    newSearchBtn.addEventListener("click", () => {
      window.location.hash = "#dashboard";
      resetSearchView();
    });
  }
});

// === 히어로 검색 가시성 ===
function initSearchHeroVisibility() {
  // 검색 결과가 없으면 히어로 표시
  const hero = getElement("search-hero");
  const results = getElement("results-area");
  if (hero && results && results.classList.contains("hidden")) {
    hero.classList.remove("hidden");
  }
}

function resetSearchView() {
  const hero = getElement("search-hero");
  if (hero) hero.classList.remove("hidden");

  // 폼 필드 초기화
  const regionInput = getElement("region-input");
  const keywordInput = getElement("keyword-input");
  const topicSelect = getElement("topic-select");
  const storeNameInput = getElement("store-name-input");
  if (regionInput) regionInput.value = "";
  if (keywordInput) keywordInput.value = "";
  if (topicSelect) topicSelect.value = "";
  if (storeNameInput) storeNameInput.value = "";

  // 결과 영역 숨기기
  ["results-area", "progress-area", "meta-area", "keywords-area", "guide-area", "message-template-area"].forEach((id) => {
    const el = getElement(id);
    if (el) el.classList.add("hidden");
  });
}

// === 블로거 즐겨찾기 (내 체험단) ===
function getFavorites() {
  return JSON.parse(localStorage.getItem("favoriteBloggers") || "[]");
}

function saveFavorites(favs) {
  localStorage.setItem("favoriteBloggers", JSON.stringify(favs));
  updateFavCount();
}

function toggleFavorite(blogger) {
  let favs = getFavorites();
  const idx = favs.findIndex((f) => f.blogger_id === blogger.blogger_id);
  if (idx >= 0) {
    favs.splice(idx, 1);
  } else {
    favs.push({
      blogger_id: blogger.blogger_id,
      blog_url: blogger.blog_url || `https://blog.naver.com/${blogger.blogger_id}`,
      final_score: blogger.final_score || 0,
      grade: blogger.grade || "",
      tags: blogger.tags || [],
      added_at: new Date().toISOString(),
    });
  }
  saveFavorites(favs);
  return idx < 0; // true if added
}

function isFavorite(bloggerId) {
  return getFavorites().some((f) => f.blogger_id === bloggerId);
}

function updateFavCount() {
  const badge = getElement("fav-count-badge");
  const count = getFavorites().length;
  if (badge) {
    badge.textContent = count;
    badge.style.display = count > 0 ? "flex" : "none";
  }
}

function renderFavorites() {
  const container = getElement("favorites-list");
  if (!container) return;
  const favs = getFavorites();
  if (favs.length === 0) {
    container.innerHTML = '<p class="empty-text">저장한 블로거가 없습니다. 검색 결과에서 ★를 클릭하여 블로거를 저장하세요.</p>';
    return;
  }
  const GC = { "S+": "#2B4C7E", S: "#3B7DD8", A: "#4A8B6F", "B+": "#8B8A3C", B: "#C2883D", C: "#C0392B", D: "#7B4040", F: "#5C2626" };
  container.innerHTML = favs.map((f) => {
    const blogUrl = f.blog_url || `https://blog.naver.com/${f.blogger_id}`;
    const gradeColor = GC[f.grade] || "#595959";
    const score = f.final_score ? Math.round(f.final_score * 10) / 10 : "-";
    const addedDate = f.added_at ? new Date(f.added_at).toLocaleDateString("ko-KR") : "";
    return `
    <div class="fav-list-row">
      <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener" class="fav-list-id">${escapeHtml(f.blogger_id)}</a>
      <span class="fav-list-grade" style="color:${gradeColor}">${score} ${escapeHtml(f.grade || "")}</span>
      <div class="fav-list-tags">${(f.tags || []).map(t => `<span class="badge-food">${escapeHtml(t)}</span>`).join("")}</div>
      <span class="fav-list-date">${addedDate}</span>
      <div class="fav-list-actions">
        <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener">블로그</a>
        <a href="https://note.naver.com" target="_blank" rel="noopener">쪽지</a>
        <button class="fav-remove-btn" data-id="${escapeHtml(f.blogger_id)}">삭제</button>
      </div>
    </div>`;
  }).join("");

  container.querySelectorAll(".fav-remove-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      let favs = getFavorites();
      favs = favs.filter((f) => f.blogger_id !== btn.dataset.id);
      saveFavorites(favs);
      renderFavorites();
    });
  });
}

// === 최근 검색 (localStorage) ===
function saveRecentSearch(query) {
  let history = JSON.parse(localStorage.getItem("recentSearches") || "[]");
  history = history.filter((h) => h !== query);
  history.unshift(query);
  if (history.length > 10) history = history.slice(0, 10);
  localStorage.setItem("recentSearches", JSON.stringify(history));
  loadRecentSearches();
}

function loadRecentSearches() {
  const list = getElement("sidebar-recent-list");
  if (!list) return;
  const history = JSON.parse(localStorage.getItem("recentSearches") || "[]");
  if (history.length === 0) {
    list.innerHTML = '<span style="padding:4px 12px;font-size:0.8rem;color:#bbb;">검색 기록이 없습니다</span>';
    return;
  }
  list.innerHTML = history.map((q) =>
    `<a href="#" class="recent-search-item" data-query="${escapeHtml(q)}">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      ${escapeHtml(q)}
    </a>`
  ).join("");

  list.querySelectorAll(".recent-search-item").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      const query = el.dataset.query;
      const heroInput = getElement("hero-search-input");
      if (heroInput) heroInput.value = query;
      window.location.hash = "#dashboard";
      setTimeout(() => triggerHeroSearch(), 50);
    });
  });
}

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
  tier_analysis: "블로그 권위 분석",
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
  if (!requireLogin()) return;

  const region = regionInput.value.trim();
  const topic = topicSelect.value;
  const keyword = keywordInput.value.trim();
  const storeName = storeNameInput.value.trim();

  if (!region) {
    alert("지역은 필수 입력입니다.");
    return;
  }

  // 히어로 숨기기
  const hero = getElement("search-hero");
  if (hero) hero.classList.add("hidden");

  // 최근 검색 저장
  const queryStr = [region, keyword, storeName].filter(Boolean).join(" ");
  if (queryStr) saveRecentSearch(queryStr);

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

    const guideText = getElement("guide-text");
    const richView = getElement("guide-rich-view");
    const toggleBtn = getElement("guide-view-toggle");

    guideText.textContent = data.full_guide_text;
    guideArea.classList.remove("hidden");

    // 리치 뷰 데이터가 있으면 렌더링
    const hasRich = data.keywords_3tier || data.structure_sections || data.hashtags;
    if (hasRich) {
      _renderGuideRichView(data);
      // 기본: 리치 뷰 표시
      richView.classList.add("active");
      guideText.style.display = "none";
      toggleBtn.textContent = "텍스트 뷰";
      toggleBtn.classList.add("active");

      toggleBtn.onclick = () => {
        if (richView.classList.contains("active")) {
          richView.classList.remove("active");
          guideText.style.display = "";
          toggleBtn.textContent = "리치 뷰";
          toggleBtn.classList.remove("active");
        } else {
          richView.classList.add("active");
          guideText.style.display = "none";
          toggleBtn.textContent = "텍스트 뷰";
          toggleBtn.classList.add("active");
        }
      };
    } else {
      richView.classList.remove("active");
      guideText.style.display = "";
      toggleBtn.style.display = "none";
    }

    // 복사 버튼 (항상 full_guide_text 복사)
    getElement("copy-guide-btn").onclick = async () => {
      try {
        await navigator.clipboard.writeText(data.full_guide_text);
        const btn = getElement("copy-guide-btn");
        btn.textContent = "복사됨!";
        setTimeout(() => { btn.textContent = "가이드 복사"; }, 2000);
      } catch {
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

function _renderGuideRichView(data) {
  // 3계층 키워드
  const kwSection = getElement("guide-keywords-section");
  if (data.keywords_3tier) {
    const kw = data.keywords_3tier;
    _fillKeywordTier("guide-keywords-main", kw.main || []);
    _fillKeywordTier("guide-keywords-sub", kw.sub || []);
    _fillKeywordTier("guide-keywords-longtail", kw.longtail || []);
    kwSection.classList.remove("hidden");
  }

  // 글 구조
  const structSection = getElement("guide-structure-section");
  if (data.structure_sections && data.structure_sections.length) {
    const container = getElement("guide-structure-cards");
    container.innerHTML = data.structure_sections.map(s =>
      `<div class="guide-structure-card">
        <h5>${escapeHtml(s.heading)}</h5>
        <p>${escapeHtml(s.desc)}</p>
        ${s.img_min ? `<div class="img-hint">사진 최소 ${s.img_min}장</div>` : ""}
      </div>`
    ).join("");
    structSection.classList.remove("hidden");
  }

  // 금지어
  const forbidSection = getElement("guide-forbidden-section");
  if (data.forbidden_detailed && data.forbidden_detailed.length) {
    const tbody = getElement("guide-forbidden-table").querySelector("tbody");
    tbody.innerHTML = data.forbidden_detailed.map(f =>
      `<tr><td>${escapeHtml(f.forbidden)}</td><td>${escapeHtml(f.replacement)}</td><td>${escapeHtml(f.reason)}</td></tr>`
    ).join("");
    forbidSection.classList.remove("hidden");
  }

  // 해시태그
  const hashSection = getElement("guide-hashtag-section");
  if (data.hashtags && data.hashtags.length) {
    const area = getElement("guide-hashtag-area");
    area.innerHTML = data.hashtags.map(h =>
      `<span class="guide-hashtag-chip">${escapeHtml(h)}</span>`
    ).join("");
    hashSection.classList.remove("hidden");

    getElement("copy-hashtag-btn").onclick = async () => {
      const text = data.hashtags.join(" ");
      try {
        await navigator.clipboard.writeText(text);
        const btn = getElement("copy-hashtag-btn");
        btn.textContent = "복사됨!";
        setTimeout(() => { btn.textContent = "해시태그 복사"; }, 2000);
      } catch { /* ignore */ }
    };
  }

  // 체크리스트
  const checkSection = getElement("guide-checklist-section");
  if (data.checklist && data.checklist.length) {
    const container = getElement("guide-checklist");
    container.innerHTML = data.checklist.map((item, i) =>
      `<div class="guide-checklist-item" id="checklist-item-${i}">
        <input type="checkbox" id="check-${i}" onchange="this.parentElement.classList.toggle('checked')">
        <label for="check-${i}">${escapeHtml(item)}</label>
      </div>`
    ).join("");
    checkSection.classList.remove("hidden");
  }
}

function _fillKeywordTier(elId, keywords) {
  const el = getElement(elId);
  el.innerHTML = keywords.map(kw =>
    `<span class="guide-keyword-chip">${escapeHtml(kw)}</span>`
  ).join("");
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

  // 배지 (v7.2 grade 기준, tier_grade 제거)
  const badges = [];
  if (isTop) badges.push('<span class="badge-recommend">강한 추천</span>');
  tags.forEach((tag) => {
    if (tag === "맛집편향") badges.push('<span class="badge-food">맛집편향</span>');
    else if (tag === "협찬성향") badges.push('<span class="badge-sponsor">협찬성향</span>');
    else if (tag === "노출안정") badges.push('<span class="badge-stable">노출안정</span>');
    else if (tag === "미노출") badges.push('<span class="badge-unexposed">미노출</span>');
  });

  // Performance Score 바
  const perfPct = Math.min(100, perfScore);
  const perfColor = perfScore >= 70 ? "#3B7DD8" : perfScore >= 40 ? "#4A8B6F" : perfScore >= 20 ? "#C2883D" : "#C0392B";

  // 쪽지/메일 URL
  const msgUrl = `https://note.naver.com`;
  const naverMailUrl = `https://mail.naver.com`;
  const bloggerEmail = `${blogger.blogger_id}@naver.com`;

  const favActiveCard = isFavorite(blogger.blogger_id) ? "active" : "";

  return `
  <div class="blogger-card ${isTop ? 'top20-card' : ''}">
    <div class="blogger-header">
      <button class="fav-star-btn ${favActiveCard}" data-id="${escapeHtml(blogger.blogger_id)}" title="내 체험단에 저장">★</button>
      <div class="blogger-rank">${rank}</div>
      <div>
        <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener" class="blogger-name">${escapeHtml(blogger.blogger_id)}</a>
        ${badges.join("")}
      </div>
      <div class="score-badge" style="color:${gradeColor}">${perfScore} ${grade}</div>
    </div>

    <div class="perf-bar-container">
      <div class="perf-bar-track">
        <div class="perf-bar-fill" style="width:${perfPct}%; background:${perfColor}"></div>
      </div>
      <span class="perf-bar-label">GS v7.2 ${perfScore}/100</span>
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

  // 배지 (v7.2 grade 기준, tier_grade 제거)
  const badges = [];
  if (isTop) badges.push('<span class="badge-recommend">강한 추천</span>');
  tags.forEach((tag) => {
    if (tag === "맛집편향") badges.push('<span class="badge-food">맛집편향</span>');
    else if (tag === "협찬성향") badges.push('<span class="badge-sponsor">협찬성향</span>');
    else if (tag === "노출안정") badges.push('<span class="badge-stable">노출안정</span>');
    else if (tag === "미노출") badges.push('<span class="badge-unexposed">미노출</span>');
  });

  const favActive = isFavorite(blogger.blogger_id) ? "active" : "";

  return `
  <div class="list-row">
    <button class="fav-star-btn ${favActive}" data-id="${escapeHtml(blogger.blogger_id)}" title="내 체험단에 저장">★</button>
    <span class="list-rank">${rank}</span>
    <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener" class="list-id">${escapeHtml(blogger.blogger_id)}</a>
    <span class="list-perf" style="color:${gradeColor}">${perf} ${grade}</span>
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

  // 즐겨찾기 별 버튼
  container.querySelectorAll(".fav-star-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const blogger = bloggers.find((b) => b.blogger_id === btn.dataset.id);
      if (blogger) {
        const added = toggleFavorite(blogger);
        btn.classList.toggle("active", added);
      }
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

  const v72Grade = blogger.grade || "";
  const v72GradeLabel = blogger.grade_label || "";
  const v72GradeColor = GRADE_COLORS[v72Grade] || "#999";

  // v7.2 Base Breakdown 바
  const baseBd = blogger.base_breakdown || {};
  const baseBdKeys = Object.keys(baseBd);
  const baseBarsHtml = baseBdKeys.map((key) => {
    const axis = baseBd[key];
    const label = axis.label || key;
    const score = axis.score ?? 0;
    const max = axis.max ?? 1;
    const isNeg = max <= 0;
    const pct = isNeg ? 0 : Math.round((Math.abs(score) / (max || 1)) * 100);
    const barColor = isNeg ? "#C0392B" : (pct >= 70 ? "#3B7DD8" : pct >= 40 ? "#4A8B6F" : pct >= 20 ? "#C2883D" : "#C0392B");
    const displayVal = isNeg ? `${score}` : `${score}/${max}`;
    return `<div class="modal-bar-row">
      <span class="modal-bar-label">${escapeHtml(label)}</span>
      <div class="modal-bar-track"><div class="modal-bar-fill" style="width:${isNeg ? Math.min(100, Math.abs(score)*10) : pct}%;background:${barColor}"></div></div>
      <span class="modal-bar-value">${displayVal}</span>
    </div>`;
  }).join("");

  // v7.2 Category Bonus 바
  const bonusBd = blogger.bonus_breakdown || null;
  let bonusHtml = "";
  if (bonusBd) {
    const bonusBarsHtml = Object.keys(bonusBd).map((key) => {
      const axis = bonusBd[key];
      const label = axis.label || key;
      const score = axis.score ?? 0;
      const max = axis.max ?? 1;
      const pct = Math.round((score / (max || 1)) * 100);
      const barColor = pct >= 70 ? "#3B7DD8" : pct >= 40 ? "#4A8B6F" : pct >= 20 ? "#C2883D" : "#C0392B";
      return `<div class="modal-bar-row">
        <span class="modal-bar-label">${escapeHtml(label)}</span>
        <div class="modal-bar-track"><div class="modal-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
        <span class="modal-bar-value">${score}/${max}</span>
      </div>`;
    }).join("");
    bonusHtml = `
      <div class="modal-section-header">업종 보너스 <strong>+${blogger.category_bonus ?? 0}</strong></div>
      ${bonusBarsHtml}
    `;
  }

  const baseScore = blogger.base_score_v71 != null ? blogger.base_score_v71 : perf;
  const modeLabel = blogger.analysis_mode === "category" ? "업종 분석" : "지역 분석";

  modalScoreDetails.innerHTML = `
    <div class="modal-score-item"><span>Golden Score v7.2</span><strong>${perf}</strong></div>
    <div class="modal-score-item"><span>등급</span><strong><span class="tier-badge" style="background:${v72GradeColor}">${v72Grade}</span> ${escapeHtml(v72GradeLabel)}</strong></div>
    <div class="modal-score-item"><span>분석 모드</span><strong>${modeLabel}</strong></div>
    <hr/>
    <div class="modal-section-header">Base Score <strong>${baseScore}/100</strong></div>
    ${baseBarsHtml}
    ${bonusHtml}
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

  // 쪽지/메일/즐겨찾기 버튼
  const msgUrl = `https://note.naver.com`;
  const naverMailUrl = `https://mail.naver.com`;
  const bloggerEmail = `${blogger.blogger_id}@naver.com`;
  const modalFavActive = isFavorite(blogger.blogger_id) ? "active" : "";
  const modalActions = getElement("modal-actions-row");
  modalActions.innerHTML = `
    <button class="modal-action-btn modal-fav-btn ${modalFavActive}" id="modal-fav-toggle">★ ${isFavorite(blogger.blogger_id) ? "저장됨" : "저장하기"}</button>
    <a href="${escapeHtml(msgUrl)}" target="_blank" rel="noopener" class="modal-action-btn modal-msg-btn">쪽지 보내기</a>
    <a href="${escapeHtml(naverMailUrl)}" target="_blank" rel="noopener" class="modal-action-btn modal-mail-btn" data-email="${escapeHtml(bloggerEmail)}" onclick="copyEmailAndOpen(event)">메일 보내기</a>
  `;

  // 모달 즐겨찾기 토글
  const modalFavBtn = getElement("modal-fav-toggle");
  if (modalFavBtn) {
    modalFavBtn.addEventListener("click", () => {
      const added = toggleFavorite(blogger);
      modalFavBtn.classList.toggle("active", added);
      modalFavBtn.textContent = added ? "★ 저장됨" : "★ 저장하기";
      // 리스트/카드의 별 상태도 동기화
      document.querySelectorAll(`.fav-star-btn[data-id="${blogger.blogger_id}"]`).forEach((btn) => {
        btn.classList.toggle("active", added);
      });
    });
  }

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

// === 캠페인 섹션 (블로그 분석 페이지) ===
const createCampaignBtn = getElement("create-campaign-btn");
const campaignActionsEl = createCampaignBtn ? createCampaignBtn.parentElement : null;
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
    if (campaignActionsEl) campaignActionsEl.classList.add("hidden");
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
      top20El.innerHTML = '<p class="empty-text">아직 분석 데이터가 없습니다. 체험단검색에서 분석을 실행하세요.</p>';
    }

    // Pool40 렌더링
    const pool40El = getElement("campaign-pool40");
    if (campaign.pool40 && campaign.pool40.length > 0) {
      pool40El.className = "grid-layout";
      pool40El.innerHTML = campaign.pool40.map((b, i) => renderBloggerCard(b, i + 1, false)).join("");
      attachCardEvents(pool40El, campaign.pool40);
    } else {
      pool40El.innerHTML = '<p class="empty-text">추천체험단 데이터가 없습니다.</p>';
    }
  } catch (err) {
    alert("캠페인 상세 정보를 불러올 수 없습니다.");
  }
}

backToCampaigns.addEventListener("click", () => {
  campaignDetail.classList.add("hidden");
  campaignListEl.classList.remove("hidden");
  if (campaignActionsEl) campaignActionsEl.classList.remove("hidden");
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

// ═══════════════════════════════════════════════════════
// 로그인 / 인증 (SNS)
// ═══════════════════════════════════════════════════════

let currentUser = null;

// 로그인 필수 가드 — 로그인 안 되어 있으면 로그인 모달 표시
function requireLogin() {
  if (currentUser) return true;
  openLoginModal();
  return false;
}

function openLoginModal() {
  const m = getElement('loginModal');
  if (!m) return;
  // SNS 버튼 href를 AUTH_BASE로 동적 설정
  m.querySelectorAll('.social-btn[data-provider]').forEach(btn => {
    btn.href = `${AUTH_BASE}/auth/${btn.dataset.provider}`;
  });
  m.style.display = 'flex';
}
function closeLoginModal() { const m = getElement('loginModal'); if (m) m.style.display = 'none'; }

async function checkAuth() {
  try {
    const res = await fetch(`${AUTH_BASE}/auth/me`, { credentials: 'include' });
    const data = await res.json();
    if (data.loggedIn) { currentUser = data.user; onLoggedIn(); }
    else { onLoggedOut(); }
  } catch (e) { onLoggedOut(); }
}

const PROVIDER_LABELS = { kakao: '카카오', naver: '네이버', google: '구글' };

function onLoggedIn() {
  const userEl = getElement('sidebar-user-btn');
  if (!userEl) return;
  const avatar = currentUser.profileImage
    ? `<img src="${currentUser.profileImage}" class="user-avatar-img">`
    : `<div class="user-avatar">${escapeHtml(currentUser.displayName[0])}</div>`;
  const providerLabel = PROVIDER_LABELS[currentUser.provider] || currentUser.provider;
  userEl.onclick = null;
  userEl.style.cursor = 'default';
  userEl.innerHTML =
    `<div class="user-avatar-wrap"><span class="user-online-dot"></span>${avatar}</div>` +
    `<div class="user-info">` +
      `<div class="user-name">${escapeHtml(currentUser.displayName)}</div>` +
      `<div class="user-plan">${escapeHtml(providerLabel)} 로그인` +
        ` · <a href="#" onclick="doLogout(); return false" class="user-logout-link">로그아웃</a></div>` +
    `</div>`;
  if (currentUser.role === 'admin') {
    showAdminMenu();
  }
  if (location.search.includes('login=success')) history.replaceState(null, '', '/');
}

function onLoggedOut() {
  currentUser = null;
  const userEl = getElement('sidebar-user-btn');
  if (!userEl) return;
  userEl.onclick = openLoginModal;
  userEl.style.cursor = 'pointer';
  userEl.innerHTML =
    `<div class="user-avatar-wrap"><div class="user-avatar" style="background:#97a097">?</div></div>` +
    `<div class="user-info">` +
      `<div class="user-name">로그인하세요</div>` +
      `<div class="user-plan">SNS로 3초만에 시작</div>` +
    `</div>`;
}

async function doLogout() {
  await fetch(`${AUTH_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
  currentUser = null;
  onLoggedOut();
}

// ═══════════════════════════════════════════════════════
// 광고
// ═══════════════════════════════════════════════════════

async function loadAds(topic, region, keyword) {
  const placements = ['search_top', 'search_middle', 'sidebar'];
  for (const placement of placements) {
    try {
      const params = new URLSearchParams({ placement });
      if (topic)   params.set('topic', topic);
      if (region)  params.set('region', region);
      if (keyword) params.set('keyword', keyword);
      const res = await fetch(`${AUTH_BASE}/ads/match?${params.toString()}`);
      const ads = await res.json();
      const container = getElement('adSlot_' + placement);
      if (!container) continue;
      if (ads.length > 0) { renderAd(ads[0], container); container.style.display = 'block'; }
      else { container.style.display = 'none'; }
    } catch (e) { /* 광고 로드 실패 무시 */ }
  }
}

function renderAd(ad, container) {
  const id = ad._id;
  if (ad.type === 'banner_horizontal' || ad.type === 'banner_sidebar') {
    container.innerHTML = `<div class="ad-banner" data-ad-id="${id}"><a href="#" onclick="onAdClick('${id}'); return false"><img src="${escapeHtml(ad.imageUrl)}" alt="${escapeHtml(ad.title)}"></a><span class="ad-badge">AD</span></div>`;
  } else if (ad.type === 'native_card') {
    container.innerHTML = `<div class="ad-native" data-ad-id="${id}" onclick="onAdClick('${id}')">` +
      (ad.imageUrl ? `<img src="${escapeHtml(ad.imageUrl)}" class="ad-native-img">` : '') +
      `<div class="ad-native-body"><div class="ad-native-badge">추천 서비스</div><div class="ad-native-title">${escapeHtml(ad.title)}</div><div class="ad-native-desc">${escapeHtml(ad.description || '')}</div></div>` +
      `<button class="ad-native-cta">${escapeHtml(ad.ctaText || '자세히 보기')}</button></div>`;
  } else if (ad.type === 'text_link') {
    container.innerHTML = `<div class="ad-textlink" data-ad-id="${id}"><span class="ad-badge">AD</span><a href="#" onclick="onAdClick('${id}'); return false">${escapeHtml(ad.title)}</a></div>`;
  }
  trackImpression(id, container);
}

function trackImpression(adId, container) {
  const el = container.querySelector('[data-ad-id]');
  if (!el) return;
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        fetch(`${AUTH_BASE}/ads/impression/${adId}`, { method: 'POST' });
        obs.unobserve(el);
      }
    });
  }, { threshold: 0.5 });
  obs.observe(el);
}

async function onAdClick(adId) {
  try {
    const res = await fetch(`${AUTH_BASE}/ads/click/${adId}`, { method: 'POST' });
    const data = await res.json();
    if (data.redirectUrl) window.open(data.redirectUrl, '_blank');
  } catch (e) { /* 클릭 추적 실패 무시 */ }
}

// ═══════════════════════════════════════════════════════
// 관리자 대시보드
// ═══════════════════════════════════════════════════════

function showAdminMenu() {
  const nav = document.querySelector('.sidebar-nav');
  if (nav && !getElement('navAdmin')) {
    const item = document.createElement('a');
    item.id = 'navAdmin';
    item.href = '#admin';
    item.className = 'sidebar-nav-item';
    item.dataset.page = 'admin';
    item.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/></svg> 관리자`;
    nav.appendChild(item);
    item.addEventListener('click', (e) => {
      e.preventDefault();
      window.location.hash = '#admin';
    });
  }
}

function switchAdminTab(tab) {
  document.querySelectorAll('.admin-tab-content').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.admin-tab').forEach(el => el.classList.remove('active'));
  const tabEl = getElement('adminTab_' + tab);
  if (tabEl) tabEl.style.display = 'block';
  // active 버튼
  document.querySelectorAll('.admin-tab').forEach(el => {
    if (el.textContent.trim() === {overview:'이용 현황',users:'회원 관리',searches:'검색 분석',ads:'광고 관리',live:'실시간'}[tab]) {
      el.classList.add('active');
    }
  });
  if (tab === 'overview') loadOverview();
  if (tab === 'users')    loadUsersTab();
  if (tab === 'searches') loadSearchesTab();
  if (tab === 'ads')      loadAdsTab();
  if (tab === 'live')     loadLiveTab();
}

async function refreshAdminDashboard() { loadOverview(); }

async function loadOverview() {
  try {
    const [todayRes, rangeRes, adRes, userRes] = await Promise.all([
      fetch(`${AUTH_BASE}/admin/analytics/today`, { credentials:'include' }),
      fetch(`${AUTH_BASE}/admin/analytics/range?days=30`, { credentials:'include' }),
      fetch(`${AUTH_BASE}/admin/ads/stats`, { credentials:'include' }),
      fetch(`${AUTH_BASE}/admin/analytics/users`, { credentials:'include' }),
    ]);
    const today = await todayRes.json(), range = await rangeRes.json(), ads = await adRes.json(), users = await userRes.json();
    const el = (id) => getElement(id);
    if (el('stat_pageViews')) el('stat_pageViews').textContent = (today.pageViews || 0).toLocaleString();
    if (el('stat_searches'))  el('stat_searches').textContent = (today.searches || 0).toLocaleString();
    if (el('stat_online'))    el('stat_online').textContent = today.estimatedOnline || 0;
    if (el('stat_totalUsers'))el('stat_totalUsers').textContent = (users.total || 0).toLocaleString();
    if (el('stat_newToday'))  el('stat_newToday').textContent = users.newToday || 0;
    if (el('stat_adRevenue')) el('stat_adRevenue').textContent = (ads.monthlyRevenue || 0).toLocaleString() + '원';
    // 시간대별 차트
    if (today.hourlyViews && el('hourlyChart')) {
      const maxH = Math.max(...today.hourlyViews, 1);
      el('hourlyChart').innerHTML = today.hourlyViews.map((v,i) =>
        `<div class="hourly-bar" style="height:${(v/maxH)*100}%" data-label="${i}시 ${v}뷰"></div>`
      ).join('');
    }
    // 30일 추이
    if (range.data && el('rangeChart')) {
      el('rangeChart').innerHTML = `<table style="width:100%;font-size:.78rem"><tr><th style="text-align:left">날짜</th><th>PV</th><th>검색</th><th>신규</th></tr>` +
        range.data.slice(-10).map(d => `<tr><td>${d.date.slice(5)}</td><td style="text-align:right">${d.pageViews}</td><td style="text-align:right">${d.searches}</td><td style="text-align:right">${d.newUsers}</td></tr>`).join('') +
        `</table><div style="font-size:.72rem;color:#999;margin-top:6px">30일 합계: PV ${range.totals.pageViews.toLocaleString()} / 검색 ${range.totals.searches.toLocaleString()} / 신규 ${range.totals.newUsers}</div>`;
    }
  } catch(e) { console.error('대시보드 로드 실패:', e); }
}

async function loadUsersTab() {
  try {
    const data = await (await fetch(`${AUTH_BASE}/admin/analytics/users`, { credentials:'include' })).json();
    const ps = getElement('providerStats');
    if (ps) ps.innerHTML = (data.byProvider || []).map(p =>
      `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f0f0"><span>${escapeHtml(p.provider)}</span><strong>${p.count}명</strong></div>`
    ).join('');
    const rl = getElement('recentUsersList');
    if (rl) rl.innerHTML = `<table style="width:100%;font-size:.8rem"><tr><th>이름</th><th>이메일</th><th>방식</th><th>가입일</th></tr>` +
      (data.recentUsers || []).map(u => `<tr><td>${escapeHtml(u.displayName)}</td><td>${escapeHtml(u.email||'-')}</td><td>${escapeHtml(u.provider)}</td><td>${new Date(u.createdAt).toLocaleDateString()}</td></tr>`).join('') + '</table>';
  } catch(e) { /* ignore */ }
}

async function loadSearchesTab() {
  try {
    const data = await (await fetch(`${AUTH_BASE}/admin/analytics/popular?days=7`, { credentials:'include' })).json();
    const tr = getElement('topRegions');
    if (tr) tr.innerHTML = (data.topRegions || []).map((r,i) =>
      `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f0f0"><span>${i+1}. ${escapeHtml(r.name)}</span><strong>${r.count}회</strong></div>`
    ).join('') || '<div style="color:#999">데이터 없음</div>';
    const tt = getElement('topTopics');
    if (tt) tt.innerHTML = (data.topTopics || []).map((t,i) =>
      `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f0f0"><span>${i+1}. ${escapeHtml(t.name)}</span><strong>${t.count}회</strong></div>`
    ).join('') || '<div style="color:#999">데이터 없음</div>';
  } catch(e) { /* ignore */ }
}

async function loadAdsTab() {
  try {
    const [stats, ads] = await Promise.all([
      (await fetch(`${AUTH_BASE}/admin/ads/stats`, { credentials:'include' })).json(),
      (await fetch(`${AUTH_BASE}/admin/ads`, { credentials:'include' })).json(),
    ]);
    const as = getElement('adStats');
    if (as) as.innerHTML =
      `<div class="admin-stat-card"><div class="admin-stat-label">운영 중</div><div class="admin-stat-value">${stats.activeCount}</div></div>` +
      `<div class="admin-stat-card"><div class="admin-stat-label">총 노출</div><div class="admin-stat-value">${(stats.totalImpressions||0).toLocaleString()}</div></div>` +
      `<div class="admin-stat-card"><div class="admin-stat-label">총 클릭</div><div class="admin-stat-value">${(stats.totalClicks||0).toLocaleString()}</div></div>` +
      `<div class="admin-stat-card"><div class="admin-stat-label">평균 CTR</div><div class="admin-stat-value">${stats.avgCtr || 0}%</div></div>`;
    const al = getElement('adsList');
    if (al) al.innerHTML = ads.map(ad => {
      const ctr = ad.stats.impressions > 0 ? ((ad.stats.clicks/ad.stats.impressions)*100).toFixed(1) : '0.0';
      return `<div class="ad-list-item ${ad.isActive?'':'inactive'}"><div><div class="ad-list-title">${escapeHtml(ad.title)}</div><div class="ad-list-meta">${escapeHtml(ad.advertiser?.company||'')} · ${escapeHtml(ad.placement)} · ${escapeHtml((ad.targeting?.businessTypes||[]).join(','))}</div></div><div style="text-align:right"><div class="ad-list-stats"><span>노출 ${(ad.stats.impressions||0).toLocaleString()}</span><span>클릭 ${(ad.stats.clicks||0).toLocaleString()}</span><span>CTR ${ctr}%</span></div><div class="ad-list-actions"><button onclick="toggleAd('${ad._id}',${!ad.isActive})">${ad.isActive?'중지':'활성'}</button></div></div></div>`;
    }).join('') || '<div style="color:#999">등록된 광고 없음</div>';
  } catch(e) { /* ignore */ }
}

async function loadLiveTab() {
  try {
    const [searches, events] = await Promise.all([
      (await fetch(`${AUTH_BASE}/admin/analytics/searches`, { credentials:'include' })).json(),
      (await fetch(`${AUTH_BASE}/admin/analytics/events`, { credentials:'include' })).json(),
    ]);
    const ls = getElement('liveSearches');
    if (ls) ls.innerHTML = searches.slice(0,30).map(s =>
      `<div class="live-item"><span class="live-user">${escapeHtml(s.user||'')}</span> ${[s.region,s.topic,s.keyword].filter(Boolean).map(v=>escapeHtml(v)).join(' · ')} <span class="live-time">${new Date(s.time).toLocaleTimeString()}</span></div>`
    ).join('') || '<div style="color:#999">검색 기록 없음</div>';
    const labels = { login:'로그인', register:'가입', blogger_save:'블로거 저장', campaign_create:'캠페인 생성' };
    const le = getElement('liveEvents');
    if (le) le.innerHTML = events.slice(0,30).map(e =>
      `<div class="live-item">${labels[e.event]||e.event} <span class="live-user">${escapeHtml(e.user||'')}</span> <span class="live-time">${new Date(e.time).toLocaleTimeString()}</span></div>`
    ).join('') || '<div style="color:#999">이벤트 없음</div>';
  } catch(e) { /* ignore */ }
}

let editingAdId = null;
function openAdForm() { editingAdId=null; const m=getElement('adFormModal'); if(m) m.style.display='flex'; }
function closeAdForm() { const m=getElement('adFormModal'); if(m) m.style.display='none'; }

async function saveAd() {
  const body = {
    advertiser: { company: getElement('af_company').value, name: getElement('af_name').value, phone: getElement('af_phone').value },
    title: getElement('af_title').value,
    description: getElement('af_desc').value,
    imageUrl: getElement('af_image').value,
    linkUrl: getElement('af_link').value,
    ctaText: getElement('af_cta').value,
    type: getElement('af_type').value,
    placement: getElement('af_placement').value,
    targeting: {
      businessTypes: getElement('af_bizTypes').value.split(',').map(s=>s.trim()).filter(Boolean),
      regions: getElement('af_regions').value.split(',').map(s=>s.trim()).filter(Boolean),
    },
    startDate: getElement('af_start').value,
    endDate: getElement('af_end').value,
    billing: { model: getElement('af_billingModel').value, amount: parseInt(getElement('af_amount').value)||0 },
    priority: parseInt(getElement('af_priority').value)||0,
  };
  await fetch(editingAdId ? `${AUTH_BASE}/admin/ads/${editingAdId}` : `${AUTH_BASE}/admin/ads`, {
    method: editingAdId ? 'PUT' : 'POST',
    headers: {'Content-Type':'application/json'},
    credentials: 'include',
    body: JSON.stringify(body),
  });
  closeAdForm();
  loadAdsTab();
}

async function toggleAd(id, active) {
  await fetch(`${AUTH_BASE}/admin/ads/${id}`, {
    method: 'PUT',
    headers: {'Content-Type':'application/json'},
    credentials: 'include',
    body: JSON.stringify({isActive:active}),
  });
  loadAdsTab();
}
