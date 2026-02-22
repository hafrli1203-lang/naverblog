// ═══ 팝업 콜백 감지 IIFE — OAuth 팝업에서 실행 시 부모에 결과 전달 후 닫힘 ═══
// window.opener는 cross-origin OAuth 리다이렉트 후 null이 되므로 localStorage 플래그로 팝업 감지
let _isPopupCallback = false;
(function() {
  const params = new URLSearchParams(window.location.search);
  const status = params.get('login');
  if (!status) return;
  // 팝업인지 확인: window.opener 또는 localStorage 플래그
  const isPopup = !!window.opener || localStorage.getItem('_auth_pending') === '1';
  if (!isPopup) return;
  localStorage.removeItem('_auth_pending');
  const provider = params.get('provider') || '';
  // 부모에 결과 전달 (1: postMessage, 2: localStorage 이벤트)
  if (window.opener) {
    try { window.opener.postMessage({ type: 'auth-callback', status, provider }, window.location.origin); } catch(e) {}
  }
  try { localStorage.setItem('_auth_result', JSON.stringify({ status, provider, ts: Date.now() })); } catch(e) {}
  _isPopupCallback = true;
  window.close();
  setTimeout(() => {
    document.body.innerHTML = status === 'success'
      ? '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:18px;color:#1B9C00">로그인 완료! 이 탭을 닫아주세요.</div>'
      : '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:18px;color:#c0392b">로그인 실패. 이 탭을 닫고 다시 시도해주세요.</div>';
  }, 300);
})();
if (_isPopupCallback) { throw new Error('popup-callback-halt'); }

const API_BASE = window.location.origin;
// Auth → Python 서버가 Node.js로 프록시 (같은 도메인, 쿠키 문제 없음)
const AUTH_BASE = window.location.origin;

const getElement = (id) => document.getElementById(id);

// ═══ 세션 ID (탭 단위) ═══
function getSessionId() {
  let sid = sessionStorage.getItem('_sid');
  if (!sid) { sid = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2); sessionStorage.setItem('_sid', sid); }
  return sid;
}

// ═══ 분석 트래킹 (fire-and-forget) ═══
function trackPageView(section) {
  try { navigator.sendBeacon(`${API_BASE}/api/track/pageview`, JSON.stringify({ session_id: getSessionId(), section: section || 'dashboard', referrer: document.referrer })); } catch(e) {}
}
function trackEvent(eventType, eventData) {
  try { navigator.sendBeacon(`${API_BASE}/api/track/event`, JSON.stringify({ session_id: getSessionId(), event_type: eventType, event_data: typeof eventData === 'string' ? eventData : JSON.stringify(eventData) })); } catch(e) {}
}

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
  "S+": "#0a6e00",
  S: "#1B9C00",
  A: "#3a8a4a",
  "B+": "#7a9a30",
  B: "#c49020",
  C: "#c0392b",
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
    // 블로그 분석 캐시 알림
    showBlogCacheNotice(result);
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
  barEl.style.background = pct >= 70 ? "#1B9C00" : pct >= 40 ? "#3a8a4a" : pct >= 20 ? "#c49020" : "#C0392B";
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

  // 내 체험단 / 설정은 로그인 필수
  if ((page === "campaigns" || page === "settings") && !requireLogin()) return;

  trackPageView(page);
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
  checkAuth();        // OAuth 인증 확인
  checkAdminAuth();   // 관리자 인증 확인

  // 페이지뷰 트래킹
  trackPageView('dashboard');

  // 팝업 로그인 결과 수신 (postMessage — window.opener 있을 때)
  window.addEventListener('message', (e) => {
    if (e.origin !== window.location.origin) return;
    if (!e.data || e.data.type !== 'auth-callback') return;
    const providerNames = { kakao: '카카오', naver: '네이버', google: '구글' };
    const name = providerNames[e.data.provider] || e.data.provider || 'SNS';
    if (e.data.status === 'success') {
      checkAuth();
    } else {
      showToast(`${name} 로그인에 실패했습니다. 잠시 후 다시 시도해주세요.`);
    }
    if (_loginPopup && !_loginPopup.closed) { try { _loginPopup.close(); } catch(ex) {} }
    _loginPopup = null;
  });

  // 팝업 로그인 결과 수신 (localStorage — cross-origin에서 window.opener null일 때 폴백)
  window.addEventListener('storage', (e) => {
    if (e.key !== '_auth_result' || !e.newValue) return;
    try {
      const result = JSON.parse(e.newValue);
      localStorage.removeItem('_auth_result');
      const providerNames = { kakao: '카카오', naver: '네이버', google: '구글' };
      const name = providerNames[result.provider] || result.provider || 'SNS';
      if (result.status === 'success') {
        checkAuth();
      } else {
        showToast(`${name} 로그인에 실패했습니다. 잠시 후 다시 시도해주세요.`);
      }
    } catch(ex) {}
    if (_loginPopup && !_loginPopup.closed) { try { _loginPopup.close(); } catch(ex) {} }
    _loginPopup = null;
  });

  // 로그인 실패 감지 (리다이렉트 폴백용)
  if (location.search.includes('login=fail')) {
    const params = new URLSearchParams(location.search);
    const provider = params.get('provider') || 'SNS';
    const providerNames = { kakao: '카카오', naver: '네이버', google: '구글' };
    const name = providerNames[provider] || provider;
    showToast(`${name} 로그인에 실패했습니다. 잠시 후 다시 시도해주세요.`);
    history.replaceState(null, '', location.pathname + location.hash);
  }

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
  if (!currentUser) { openLoginModal(); return false; }
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
  container.innerHTML = favs.map((f) => {
    const blogUrl = f.blog_url || `https://blog.naver.com/${f.blogger_id}`;
    const gradeColor = GRADE_COLORS[f.grade] || "#595959";
    const score = f.final_score ? Math.round(f.final_score * 10) / 10 : "-";
    const addedDate = f.added_at ? new Date(f.added_at).toLocaleDateString("ko-KR") : "";
    const email = `${f.blogger_id}@naver.com`;
    return `
    <div class="fav-list-row">
      <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener" class="fav-list-id">${escapeHtml(f.blogger_id)}</a>
      <span class="fav-list-grade" style="color:${gradeColor}">${score} ${escapeHtml(f.grade || "")}</span>
      <div class="fav-list-tags">${(f.tags || []).map(t => `<span class="badge-food">${escapeHtml(t)}</span>`).join("")}</div>
      <span class="fav-list-date">${addedDate}</span>
      <div class="fav-list-actions">
        <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener">블로그</a>
        <a href="https://note.naver.com" target="_blank" rel="noopener">쪽지</a>
        <a href="https://mail.naver.com" target="_blank" rel="noopener" class="fav-mail-btn" data-email="${escapeHtml(email)}" onclick="copyEmailAndOpen(event)">메일</a>
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
  if (!currentUser) return; // 로그인 필수
  let history = JSON.parse(localStorage.getItem("recentSearches") || "[]");
  history = history.filter((h) => h !== query);
  history.unshift(query);
  if (history.length > 10) history = history.slice(0, 10);
  localStorage.setItem("recentSearches", JSON.stringify(history));
  loadRecentSearches();
}

function loadRecentSearches() {
  const list = getElement("sidebar-recent-list");
  const historySection = getElement("sidebar-history");
  if (!list) return;
  // 로그인 안 되어 있으면 최근 검색 섹션 숨김
  if (!currentUser) {
    if (historySection) historySection.style.display = 'none';
    list.innerHTML = '';
    return;
  }
  if (historySection) historySection.style.display = '';
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

  // 캐시 알림 숨기기
  const cacheNotice = document.getElementById("cache-notice");
  if (cacheNotice) cacheNotice.classList.add("hidden");

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

    // 캐시 알림 표시
    showCacheNotice(result);

    // A/B 키워드 + 가이드 + 메시지 템플릿 로드
    if (result.meta && result.meta.store_id) {
      loadKeywords(result.meta.store_id);
      loadGuide(result.meta.store_id);
      loadMessageTemplate(result.meta.store_id);
    }

    // 광고 로드
    loadAds(topic, region, keyword);

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

// ============================
// 캐시 알림 표시
// ============================
function showCacheNotice(result) {
  const notice = document.getElementById("cache-notice");
  const noticeText = document.getElementById("cache-notice-text");
  if (!notice || !noticeText) return;

  if (result.meta?.from_cache) {
    const cachedAt = result.meta.cached_at || "";
    const timeAgo = cachedAt ? _formatTimeAgo(cachedAt) : "";
    noticeText.textContent = timeAgo
      ? `${timeAgo} 분석 결과를 사용 중입니다.`
      : "캐시된 결과를 사용 중입니다.";
    notice.classList.remove("hidden");
    setTimeout(() => notice.classList.add("hidden"), 10000);
  } else if (result.meta?.cache_stats?.hits > 0) {
    const hits = result.meta.cache_stats.hits;
    const misses = result.meta.cache_stats.misses;
    noticeText.textContent = `API 캐시: ${hits}건 재사용, ${misses}건 신규 호출`;
    notice.classList.remove("hidden");
    setTimeout(() => notice.classList.add("hidden"), 5000);
  } else {
    notice.classList.add("hidden");
  }
}

function showBlogCacheNotice(result) {
  const headerCard = document.querySelector(".ba-header-card");
  if (!headerCard) return;

  const existing = headerCard.querySelector(".ba-cache-notice");
  if (existing) existing.remove();

  if (result.from_cache) {
    const cachedAt = result.cached_at || "";
    const timeAgo = cachedAt ? _formatTimeAgo(cachedAt) : "";
    const div = document.createElement("div");
    div.className = "ba-cache-notice cache-notice";
    div.innerHTML = `<span>${timeAgo ? timeAgo + " 분석 결과를 사용 중입니다." : "캐시된 분석 결과입니다."}</span>`;
    headerCard.insertBefore(div, headerCard.firstChild);
    setTimeout(() => div.remove(), 10000);
  }
}

function _formatTimeAgo(isoStr) {
  try {
    // isoStr: "2026-02-22 12:30:00" (UTC)
    const d = new Date(isoStr.replace(" ", "T") + "Z");
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "방금 전";
    if (diffMin < 60) return `${diffMin}분 전`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}시간 전`;
    const diffDay = Math.floor(diffHour / 24);
    return `${diffDay}일 전`;
  } catch {
    return "";
  }
}

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

    // 광고 로드
    loadAds(topic, region, keyword);
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

  // 검색 완료 트래킹
  trackEvent('search_complete', { region: meta.region || '', top20: top20.length, pool40: pool40.length });

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
  const perfColor = perfScore >= 70 ? "#1B9C00" : perfScore >= 40 ? "#3a8a4a" : perfScore >= 20 ? "#c49020" : "#C0392B";

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
    const barColor = isNeg ? "#C0392B" : (pct >= 70 ? "#1B9C00" : pct >= 40 ? "#3a8a4a" : pct >= 20 ? "#c49020" : "#C0392B");
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
      const barColor = pct >= 70 ? "#1B9C00" : pct >= 40 ? "#3a8a4a" : pct >= 20 ? "#c49020" : "#C0392B";
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
// 로그인 / 인증 (SNS OAuth)
// ═══════════════════════════════════════════════════════

let currentUser = null;

// 로그인 필수 가드 — 로그인 안 되어 있으면 로그인 모달 표시
function requireLogin() {
  if (currentUser) return true;
  openLoginModal();
  return false;
}

let _loginPopup = null;

function openLoginModal() {
  const m = getElement('loginModal');
  if (!m) return;
  m.querySelectorAll('.social-btn[data-provider]').forEach(btn => {
    const provider = btn.dataset.provider;
    btn.href = `${AUTH_BASE}/auth/${provider}`;
    btn.onclick = (e) => {
      e.preventDefault();
      if (btn.classList.contains('loading')) return;
      btn.classList.add('loading');
      const origHTML = btn.innerHTML;
      btn.textContent = '서버 연결 중...';

      // 팝업 감지용 플래그 (cross-origin에서 window.opener가 null이 되므로)
      localStorage.setItem('_auth_pending', '1');
      // 팝업 차단 방지: 클릭 이벤트 내에서 즉시 window.open
      const popupFeatures = 'width=500,height=650,left=' + (screen.width/2 - 250) + ',top=' + (screen.height/2 - 325) + ',scrollbars=yes';
      const popup = window.open('about:blank', 'auth_popup', popupFeatures);

      if (!popup || popup.closed) {
        // 팝업 차단됨 → 리다이렉트 폴백
        console.warn('[Auth] 팝업 차단됨, 리다이렉트 폴백');
        fetch(`${AUTH_BASE}/auth/me`, { credentials: 'include' })
          .then(() => { window.location.href = `${AUTH_BASE}/auth/${provider}`; })
          .catch(() => {
            btn.textContent = '서버 시작 중...';
            return new Promise(r => setTimeout(r, 3000))
              .then(() => fetch(`${AUTH_BASE}/auth/me`, { credentials: 'include' }))
              .then(() => { window.location.href = `${AUTH_BASE}/auth/${provider}`; })
              .catch(() => {
                showToast('인증 서버가 시작 중입니다. 10초 후 다시 시도해주세요.');
                btn.classList.remove('loading');
                btn.innerHTML = origHTML;
              });
          });
        return;
      }

      _loginPopup = popup;
      popup.document.write('<html><head><title>로그인</title></head><body style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#595959"><div style="text-align:center"><div style="margin-bottom:12px;font-size:24px">⏳</div>서버 연결 중...</div></body></html>');

      // 서버 워밍업 후 OAuth URL로 이동
      fetch(`${AUTH_BASE}/auth/me`, { credentials: 'include' })
        .then(() => {
          popup.location.href = `${AUTH_BASE}/auth/${provider}`;
        })
        .catch(() => {
          try { popup.document.body.querySelector('div').textContent = '서버 시작 중...'; } catch(e) {}
          return new Promise(r => setTimeout(r, 3000))
            .then(() => fetch(`${AUTH_BASE}/auth/me`, { credentials: 'include' }))
            .then(() => {
              popup.location.href = `${AUTH_BASE}/auth/${provider}`;
            })
            .catch(() => {
              try {
                popup.document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#c0392b"><div style="text-align:center"><div style="margin-bottom:12px;font-size:24px">⚠️</div>서버 연결 실패<br><br><button onclick="window.close()" style="padding:8px 24px;border:1px solid #ccc;border-radius:6px;background:#fff;cursor:pointer">닫기</button></div></div>';
              } catch(e) { popup.close(); }
              showToast('인증 서버가 시작 중입니다. 10초 후 다시 시도해주세요.');
            });
        })
        .finally(() => {
          btn.classList.remove('loading');
          btn.innerHTML = origHTML;
        });

      closeLoginModal();
    };
  });
  m.style.display = 'flex';
}
function closeLoginModal() { const m = getElement('loginModal'); if (m) m.style.display = 'none'; }

async function checkAuth(retryCount = 0) {
  try {
    const res = await fetch(`${AUTH_BASE}/auth/me`, { credentials: 'include' });
    if (!res.ok) {
      if (retryCount < 2) {
        setTimeout(() => checkAuth(retryCount + 1), 3000);
        return;
      }
      onLoggedOut();
      return;
    }
    const data = await res.json();
    if (data.loggedIn) { currentUser = data.user; onLoggedIn(); }
    else {
      if (location.search.includes('login=success') && retryCount < 2) {
        setTimeout(() => checkAuth(retryCount + 1), 800);
      } else {
        onLoggedOut();
      }
    }
  } catch (e) {
    console.warn('[Auth] checkAuth 에러:', e);
    if (retryCount < 2) {
      setTimeout(() => checkAuth(retryCount + 1), 3000);
      return;
    }
    onLoggedOut();
  }
}

const PROVIDER_LABELS = { kakao: '카카오', naver: '네이버', google: '구글' };

function onLoggedIn() {
  const userEl = getElement('sidebar-user-btn');
  if (!userEl) return;
  const name = currentUser.displayName || currentUser.email || '사용자';
  const initial = name.charAt(0) || '?';
  const avatar = currentUser.profileImage
    ? `<img src="${currentUser.profileImage}" class="user-avatar-img" onerror="this.outerHTML='<div class=\\'user-avatar\\'>${escapeHtml(initial)}</div>'">`
    : `<div class="user-avatar">${escapeHtml(initial)}</div>`;
  const providerLabel = PROVIDER_LABELS[currentUser.provider] || currentUser.provider;
  userEl.removeAttribute('onclick');
  userEl.onclick = null;
  userEl.style.cursor = 'default';
  userEl.innerHTML =
    `<div class="user-avatar-wrap"><span class="user-online-dot"></span>${avatar}</div>` +
    `<div class="user-info">` +
      `<div class="user-name">${escapeHtml(name)}</div>` +
      `<div class="user-plan">${escapeHtml(providerLabel)} 로그인` +
        ` · <a href="#" class="user-logout-link" id="logout-link">로그아웃</a></div>` +
    `</div>`;
  const logoutLink = getElement('logout-link');
  if (logoutLink) {
    logoutLink.addEventListener('click', (e) => { e.preventDefault(); doLogout(); });
  }
  if (currentUser.role === 'admin') {
    showAdminMenu();
  }
  if (location.search.includes('login=success')) {
    history.replaceState(null, '', location.pathname + location.hash);
  }
  // 로그인 후 최근 검색 표시
  loadRecentSearches();
  updateFavCount();
}

function onLoggedOut() {
  currentUser = null;
  const userEl = getElement('sidebar-user-btn');
  if (!userEl) return;
  userEl.setAttribute('onclick', 'openLoginModal()');
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
  try {
    await fetch(`${AUTH_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
  } catch (e) {
    console.warn('[Auth] 로그아웃 요청 실패:', e);
  }
  currentUser = null;
  // localStorage 초기화 (검색기록, 즐겨찾기 등)
  localStorage.removeItem('recentSearches');
  localStorage.removeItem('favoriteBloggers');
  // UI 상태 초기화
  lastResult = null;
  if (resultsArea) resultsArea.classList.add('hidden');
  if (keywordsArea) keywordsArea.classList.add('hidden');
  if (guideArea) guideArea.classList.add('hidden');
  if (messageTemplateArea) messageTemplateArea.classList.add('hidden');
  if (top20Section) top20Section.classList.add('hidden');
  if (pool40Section) pool40Section.classList.add('hidden');
  if (metaArea) metaArea.classList.add('hidden');
  const hero = getElement('search-hero');
  if (hero) hero.classList.remove('hidden');
  onLoggedOut();
  loadRecentSearches(); // 최근검색 섹션 숨김
  updateFavCount();
  showToast('로그아웃 되었습니다');
  // 초기 화면으로 이동
  window.location.hash = '#dashboard';
  navigateTo('dashboard');
}

// ═══════════════════════════════════════════════════════
// 관리자 인증 (비밀번호 방식)
// ═══════════════════════════════════════════════════════

let _isAdmin = false;

function openAdminLogin() {
  const m = getElement('adminLoginModal');
  if (m) { m.style.display = 'flex'; const inp = getElement('adminPwInput'); if(inp) inp.focus(); }
}
function closeAdminLogin() {
  const m = getElement('adminLoginModal');
  if (m) m.style.display = 'none';
}

async function adminLogin() {
  const pw = getElement('adminPwInput')?.value;
  if (!pw) { showToast('비밀번호를 입력하세요'); return; }
  try {
    const res = await fetch(`${API_BASE}/admin/login`, {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({password: pw}),
    });
    if (res.ok) {
      _isAdmin = true;
      closeAdminLogin();
      showAdminMenu();
      showToast('관리자 로그인 성공');
      navigateTo('admin');
    } else {
      showToast('비밀번호가 틀렸습니다');
    }
  } catch(e) {
    showToast('서버 연결 실패');
  }
}

async function checkAdminAuth() {
  // 관리자 인증 확인 — ads/stats에 401이면 미인증
  try {
    const res = await fetch(`${API_BASE}/admin/ads/stats`, { credentials: 'include' });
    if (res.ok) { _isAdmin = true; showAdminMenu(); }
  } catch(e) { /* 미인증 */ }
}

// ═══════════════════════════════════════════════════════
// 광고
// ═══════════════════════════════════════════════════════

async function loadAds(topic, region, keyword) {
  const placements = ['search_top', 'search_middle', 'search_bottom'];
  for (const placement of placements) {
    try {
      const params = new URLSearchParams({ placement });
      if (topic)   params.set('topic', topic);
      if (region)  params.set('region', region);
      if (keyword) params.set('keyword', keyword);
      const res = await fetch(`${API_BASE}/ads/match?${params.toString()}`);
      const ads = await res.json();
      const container = getElement('adSlot_' + placement);
      if (!container) continue;
      if (ads.length > 0) { renderAd(ads[0], container); container.style.display = 'block'; }
      else { container.style.display = 'none'; }
    } catch (e) { /* 광고 로드 실패 무시 */ }
  }
}

function renderAd(ad, container) {
  const id = ad._id || ad.ad_id;
  const imgUrl = ad.imageUrl || ad.image_url || '';
  const ctaText = ad.ctaText || ad.cta_text || '자세히 보기';
  const adType = ad.type || ad.ad_type || 'native_card';
  if (adType === 'banner_horizontal' || adType === 'banner_sidebar') {
    container.innerHTML = `<div class="ad-banner" data-ad-id="${id}"><a href="#" onclick="onAdClick('${id}'); return false"><img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(ad.title)}"></a><span class="ad-badge">AD</span></div>`;
  } else if (adType === 'native_card') {
    container.innerHTML = `<div class="ad-native" data-ad-id="${id}" onclick="onAdClick('${id}')">` +
      (imgUrl ? `<img src="${escapeHtml(imgUrl)}" class="ad-native-img">` : '') +
      `<div class="ad-native-body"><div class="ad-native-badge">추천 서비스</div><div class="ad-native-title">${escapeHtml(ad.title)}</div><div class="ad-native-desc">${escapeHtml(ad.description || '')}</div></div>` +
      `<button class="ad-native-cta">${escapeHtml(ctaText)}</button></div>`;
  } else if (adType === 'text_link') {
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
        fetch(`${API_BASE}/ads/impression/${adId}`, { method: 'POST' });
        obs.unobserve(el);
      }
    });
  }, { threshold: 0.5 });
  obs.observe(el);
}

async function onAdClick(adId) {
  try {
    const res = await fetch(`${API_BASE}/ads/click/${adId}`, { method: 'POST' });
    const data = await res.json();
    if (data.redirectUrl) window.open(data.redirectUrl, '_blank');
  } catch (e) { /* 클릭 추적 실패 무시 */ }
}

// ═══════════════════════════════════════════════════════
// 관리자 대시보드
// ═══════════════════════════════════════════════════════

function showAdminMenu() {
  _isAdmin = true;
  // 설정 페이지 관리자 버튼 상태 업데이트
  const loginBtn = getElement('admin-login-btn');
  if (loginBtn) {
    loginBtn.textContent = '관리자 대시보드';
    loginBtn.onclick = () => navigateTo('admin');
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

async function refreshAdminDashboard() {
  if (!_isAdmin) {
    // 인증 확인 시도
    try {
      const res = await fetch(`${API_BASE}/admin/ads/stats`, { credentials: 'include' });
      if (res.status === 401) { openAdminLogin(); return; }
      if (res.ok) { _isAdmin = true; showAdminMenu(); }
    } catch(e) { openAdminLogin(); return; }
  }
  loadOverview();
}

async function loadOverview() {
  try {
    const [todayRes, rangeRes, adRes, userRes] = await Promise.all([
      fetch(`${API_BASE}/admin/analytics/today`, { credentials:'include' }),
      fetch(`${API_BASE}/admin/analytics/range?days=30`, { credentials:'include' }),
      fetch(`${API_BASE}/admin/ads/stats`, { credentials:'include' }),
      fetch(`${API_BASE}/admin/analytics/users`, { credentials:'include' }),
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
    const data = await (await fetch(`${API_BASE}/admin/analytics/users`, { credentials:'include' })).json();
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
    const data = await (await fetch(`${API_BASE}/admin/analytics/popular?days=7`, { credentials:'include' })).json();
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
    const [statsRes, adsRes] = await Promise.all([
      fetch(`${API_BASE}/admin/ads/stats`, { credentials:'include' }),
      fetch(`${API_BASE}/admin/ads`, { credentials:'include' }),
    ]);
    if (!statsRes.ok || !adsRes.ok) {
      console.warn('[Admin] 광고 로드 실패:', statsRes.status, adsRes.status);
      return;
    }
    const stats = await statsRes.json();
    const ads = await adsRes.json();
    const as = getElement('adStats');
    if (as) as.innerHTML =
      `<div class="admin-stat-card"><div class="admin-stat-label">운영 중</div><div class="admin-stat-value">${stats.activeCount || 0}</div></div>` +
      `<div class="admin-stat-card"><div class="admin-stat-label">총 노출</div><div class="admin-stat-value">${(stats.totalImpressions||0).toLocaleString()}</div></div>` +
      `<div class="admin-stat-card"><div class="admin-stat-label">총 클릭</div><div class="admin-stat-value">${(stats.totalClicks||0).toLocaleString()}</div></div>` +
      `<div class="admin-stat-card"><div class="admin-stat-label">평균 CTR</div><div class="admin-stat-value">${stats.avgCtr || 0}%</div></div>`;
    _adsCache = Array.isArray(ads) ? ads : []; // 미리보기/수정용 캐시
    const al = getElement('adsList');
    if (al) al.innerHTML = (Array.isArray(ads) ? ads : []).map(ad => {
      const adStats = ad.stats || {};
      const imp = adStats.impressions || 0;
      const clk = adStats.clicks || 0;
      const ctr = imp > 0 ? ((clk/imp)*100).toFixed(1) : '0.0';
      const adId = ad._id || ad.ad_id;
      const isActive = ad.isActive !== undefined ? ad.isActive : Boolean(ad.is_active);
      const company = ad.advertiser?.company || ad.company || '';
      const placementLabel = AD_PLACEMENT_LABELS[ad.placement] || ad.placement || '';
      const bizTypes = ad.targeting?.businessTypes || [];
      const imgUrl = ad.imageUrl || ad.image_url || '';
      return `<div class="ad-list-item ${isActive?'':'inactive'}">
        <div style="display:flex;gap:10px;align-items:center;flex:1;min-width:0">
          ${imgUrl ? `<img src="${escapeHtml(imgUrl)}" style="width:48px;height:48px;border-radius:6px;object-fit:cover;flex-shrink:0">` : ''}
          <div style="min-width:0">
            <div class="ad-list-title">${escapeHtml(ad.title)}</div>
            <div class="ad-list-meta">${escapeHtml(company)} · ${escapeHtml(placementLabel)} · ${escapeHtml(bizTypes.join(', ') || '전업종')}</div>
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div class="ad-list-stats">
            <span>노출 ${imp.toLocaleString()}</span>
            <span>클릭 ${clk.toLocaleString()}</span>
            <span>CTR ${ctr}%</span>
          </div>
          <div class="ad-list-actions">
            <button onclick="previewAd('${adId}')">미리보기</button>
            <button onclick="editAd('${adId}')">수정</button>
            <button onclick="toggleAd('${adId}',${!isActive})">${isActive?'중지':'활성'}</button>
            <button onclick="if(confirm('정말 삭제하시겠습니까?')) deleteAd('${adId}')" style="color:#c00">삭제</button>
          </div>
        </div>
      </div>`;
    }).join('') || '<div style="color:#999;padding:20px;text-align:center">등록된 광고가 없습니다</div>';
  } catch(e) {
    console.error('[Admin] 광고 탭 로드 에러:', e);
    const al = getElement('adsList');
    if (al) al.innerHTML = '<div style="color:#c00;padding:12px">광고 데이터를 불러오는데 실패했습니다.</div>';
  }
}

async function loadLiveTab() {
  try {
    const [searches, events] = await Promise.all([
      (await fetch(`${API_BASE}/admin/analytics/searches`, { credentials:'include' })).json(),
      (await fetch(`${API_BASE}/admin/analytics/events`, { credentials:'include' })).json(),
    ]);
    const ls = getElement('liveSearches');
    if (ls) ls.innerHTML = searches.slice(0,30).map(s =>
      `<div class="live-item"><span class="live-user">${escapeHtml(s.session_id?.slice(0,8)||'')}</span> ${[s.region,s.topic,s.keyword].filter(Boolean).map(v=>escapeHtml(v)).join(' · ')} <span class="live-time">${new Date(s.time).toLocaleTimeString()}</span></div>`
    ).join('') || '<div style="color:#999">검색 기록 없음</div>';
    const labels = { search_complete:'검색 완료', blog_analysis:'블로그 분석', guide_view:'가이드 조회', page_view:'페이지 뷰' };
    const le = getElement('liveEvents');
    if (le) le.innerHTML = events.slice(0,30).map(e =>
      `<div class="live-item">${labels[e.event]||e.event} <span class="live-user">${escapeHtml(e.session_id?.slice(0,8)||'')}</span> <span class="live-time">${new Date(e.time).toLocaleTimeString()}</span></div>`
    ).join('') || '<div style="color:#999">이벤트 없음</div>';
  } catch(e) { /* ignore */ }
}

let editingAdId = null;

// 위치별 권장 사이즈 맵
const AD_SIZE_MAP = {
  search_top: '728 x 90px',
  search_middle: '728 x 90px',
  sidebar: '300 x 250px',
  report_bottom: '728 x 90px',
  mobile_sticky: '320 x 50px',
};

function openAdForm() {
  editingAdId = null;
  const m = getElement('adFormModal');
  if (!m) return;
  const title = getElement('adFormTitle');
  if (title) title.textContent = '새 광고 등록';
  // 폼 초기화
  ['af_company','af_name','af_phone','af_title','af_desc','af_image','af_link','af_cta','af_bizTypes','af_regions','af_amount','af_priority'].forEach(id => {
    const el = getElement(id); if (el) el.value = '';
  });
  const cta = getElement('af_cta'); if (cta) cta.value = '자세히 보기';
  const priority = getElement('af_priority'); if (priority) priority.value = '0';
  // 이미지 프리뷰 초기화
  const preview = getElement('ad-image-preview');
  const placeholder = getElement('ad-image-placeholder');
  if (preview) { preview.innerHTML = ''; preview.style.display = 'none'; }
  if (placeholder) placeholder.style.display = '';
  _updateAdSizeHint();
  m.style.display = 'flex';
}
function closeAdForm() { const m=getElement('adFormModal'); if(m) m.style.display='none'; }

// 위치 선택 변경 시 사이즈 힌트 업데이트
function _updateAdSizeHint() {
  const placement = getElement('af_placement');
  const hint = getElement('ad-size-hint');
  if (placement && hint) {
    hint.textContent = '권장: ' + (AD_SIZE_MAP[placement.value] || '728 x 90px') + ' (최대 5MB)';
  }
}

// 이미지 파일 업로드 핸들러
(function initAdImageUpload() {
  document.addEventListener('DOMContentLoaded', () => {
    const fileInput = getElement('af_image_file');
    const placement = getElement('af_placement');
    if (placement) placement.addEventListener('change', _updateAdSizeHint);
    if (!fileInput) return;
    fileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) { alert('파일 크기가 5MB를 초과합니다.'); return; }
      const preview = getElement('ad-image-preview');
      const placeholder = getElement('ad-image-placeholder');
      // 로컬 미리보기
      const reader = new FileReader();
      reader.onload = (ev) => {
        if (preview) {
          preview.innerHTML = `<img src="${ev.target.result}" style="max-width:100%;max-height:160px;border-radius:6px">`;
          preview.style.display = 'block';
        }
        if (placeholder) placeholder.style.display = 'none';
      };
      reader.readAsDataURL(file);
      // 서버 업로드
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch(`${API_BASE}/admin/ads/upload`, { method: 'POST', credentials: 'include', body: formData });
        if (!res.ok) { const err = await res.json().catch(()=>({})); alert(err.detail || '업로드 실패'); return; }
        const data = await res.json();
        const imageInput = getElement('af_image');
        if (imageInput) imageInput.value = data.url;
      } catch (err) {
        alert('이미지 업로드 중 오류가 발생했습니다.');
      }
    });
  });
})();

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
  await fetch(editingAdId ? `${API_BASE}/admin/ads/${editingAdId}` : `${API_BASE}/admin/ads`, {
    method: editingAdId ? 'PUT' : 'POST',
    headers: {'Content-Type':'application/json'},
    credentials: 'include',
    body: JSON.stringify(body),
  });
  closeAdForm();
  loadAdsTab();
}

async function toggleAd(id, active) {
  try {
    await fetch(`${API_BASE}/admin/ads/${id}`, {
      method: 'PUT',
      headers: {'Content-Type':'application/json'},
      credentials: 'include',
      body: JSON.stringify({isActive:active}),
    });
    showToast(active ? '광고가 활성화되었습니다' : '광고가 중지되었습니다');
  } catch(e) { showToast('변경 실패'); }
  loadAdsTab();
}

async function deleteAd(id) {
  try {
    await fetch(`${API_BASE}/admin/ads/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    showToast('광고가 삭제되었습니다');
  } catch(e) { showToast('삭제 실패'); }
  loadAdsTab();
}

// 광고 미리보기
const AD_PLACEMENT_LABELS = {
  search_top: '검색 상단 (Top20 위)',
  search_middle: 'Top20 ↔ Pool40 사이',
  search_bottom: '검색 하단 (Pool40 아래)',
  report_bottom: '리포트 하단',
  sidebar: '사이드바',
  mobile_sticky: '모바일 하단 고정',
};

let _adsCache = [];

async function previewAd(adId) {
  let ad = _adsCache.find(a => String(a._id || a.ad_id) === String(adId));
  if (!ad) {
    try {
      const res = await fetch(`${API_BASE}/admin/ads`, { credentials: 'include' });
      if (res.ok) {
        _adsCache = await res.json();
        ad = _adsCache.find(a => String(a._id || a.ad_id) === String(adId));
      }
    } catch(e) { console.error('[Preview] fetch error:', e); }
  }
  if (!ad) { showToast('광고 데이터를 불러올 수 없습니다'); return; }

  const modal = getElement('adPreviewModal');
  const content = getElement('adPreviewContent');
  if (!modal || !content) return;

  const adObj = {
    _id: ad._id || ad.ad_id,
    title: ad.title || '',
    description: ad.description || '',
    imageUrl: ad.imageUrl || ad.image_url || '',
    ctaText: ad.ctaText || ad.cta_text || '자세히 보기',
    type: ad.type || ad.ad_type || 'native_card',
    placement: ad.placement || 'search_top',
  };

  const placementLabel = AD_PLACEMENT_LABELS[adObj.placement] || adObj.placement;
  const sizeHint = AD_SIZE_MAP[adObj.placement] || '728 x 90px';
  const company = ad.advertiser?.company || ad.company || '';
  const bizTypes = ad.targeting?.businessTypes || [];
  const regions = ad.targeting?.regions || [];
  const isActive = ad.isActive !== undefined ? ad.isActive : Boolean(ad.is_active);
  const startDate = ad.startDate || ad.start_date || '';
  const endDate = ad.endDate || ad.end_date || '';

  // 광고 정보 요약
  let infoHtml = `<div class="ad-preview-info">
    <div class="ad-preview-info-row"><span class="ad-preview-label">상태</span><span class="ad-preview-badge ${isActive ? 'active' : 'inactive'}">${isActive ? '운영 중' : '중지'}</span></div>
    <div class="ad-preview-info-row"><span class="ad-preview-label">위치</span><span>${escapeHtml(placementLabel)}</span></div>
    <div class="ad-preview-info-row"><span class="ad-preview-label">권장 사이즈</span><span>${sizeHint}</span></div>
    <div class="ad-preview-info-row"><span class="ad-preview-label">유형</span><span>${escapeHtml(adObj.type)}</span></div>
    ${company ? `<div class="ad-preview-info-row"><span class="ad-preview-label">광고주</span><span>${escapeHtml(company)}</span></div>` : ''}
    ${bizTypes.length ? `<div class="ad-preview-info-row"><span class="ad-preview-label">타겟 업종</span><span>${escapeHtml(bizTypes.join(', '))}</span></div>` : ''}
    ${regions.length ? `<div class="ad-preview-info-row"><span class="ad-preview-label">타겟 지역</span><span>${escapeHtml(regions.join(', '))}</span></div>` : ''}
    ${startDate ? `<div class="ad-preview-info-row"><span class="ad-preview-label">기간</span><span>${escapeHtml(startDate)} ~ ${escapeHtml(endDate)}</span></div>` : ''}
  </div>`;

  // 실제 렌더링 미리보기
  let previewHtml = '<div class="ad-preview-section"><div class="ad-preview-section-title">실제 표시 모습</div>';
  previewHtml += `<div class="ad-preview-frame" style="background:#f5f6fa; border-radius:10px; padding:16px;">`;

  // 배치 위치 시뮬레이션
  if (adObj.placement === 'search_top') {
    previewHtml += `<div class="ad-preview-context" style="margin-bottom:8px; color:#999; font-size:.75rem; border-bottom:1px dashed #ddd; padding-bottom:6px;">-- 검색 결과 영역 시작 --</div>`;
  }

  // 실제 광고 렌더링 (renderAd와 동일 로직)
  previewHtml += `<div class="ad-slot" style="display:block; margin:0;">`;
  if (adObj.type === 'banner_horizontal' || adObj.type === 'banner_sidebar') {
    previewHtml += `<div class="ad-banner"><img src="${escapeHtml(adObj.imageUrl)}" alt="${escapeHtml(adObj.title)}" style="width:100%;height:auto;display:block"><span class="ad-badge">AD</span></div>`;
  } else if (adObj.type === 'text_link') {
    previewHtml += `<div class="ad-textlink"><span class="ad-badge">AD</span><a href="#">${escapeHtml(adObj.title)}</a></div>`;
  } else {
    // native_card (기본)
    previewHtml += `<div class="ad-native" style="cursor:default">` +
      (adObj.imageUrl ? `<img src="${escapeHtml(adObj.imageUrl)}" class="ad-native-img">` : '') +
      `<div class="ad-native-body"><div class="ad-native-badge">추천 서비스</div><div class="ad-native-title">${escapeHtml(adObj.title)}</div><div class="ad-native-desc">${escapeHtml(adObj.description)}</div></div>` +
      `<button class="ad-native-cta" style="cursor:default">${escapeHtml(adObj.ctaText)}</button></div>`;
  }
  previewHtml += `</div>`;

  if (adObj.placement === 'search_top') {
    previewHtml += `<div class="ad-preview-context" style="margin-top:8px; color:#999; font-size:.75rem; border-top:1px dashed #ddd; padding-top:6px;">-- Top20 블로거 목록 --</div>`;
  } else if (adObj.placement === 'search_middle') {
    previewHtml += `<div class="ad-preview-context" style="margin-top:8px; color:#999; font-size:.75rem; border-top:1px dashed #ddd; padding-top:6px;">-- Pool40 블로거 목록 --</div>`;
  }

  previewHtml += `</div></div>`;

  content.innerHTML = infoHtml + previewHtml;
  modal.style.display = 'flex';
}

function closeAdPreview() {
  const m = getElement('adPreviewModal');
  if (m) m.style.display = 'none';
}

// 광고 수정
async function editAd(adId) {
  let ad = _adsCache.find(a => String(a._id || a.ad_id) === String(adId));
  if (!ad) {
    try {
      const res = await fetch(`${API_BASE}/admin/ads`, { credentials: 'include' });
      if (res.ok) {
        _adsCache = await res.json();
        ad = _adsCache.find(a => String(a._id || a.ad_id) === String(adId));
      }
    } catch(e) { console.error('[EditAd] fetch error:', e); }
  }
  if (!ad) { showToast('광고 데이터를 불러올 수 없습니다'); return; }

  editingAdId = adId;
  const m = getElement('adFormModal');
  if (!m) return;
  const title = getElement('adFormTitle');
  if (title) title.textContent = '광고 수정';

  // 폼 필드 채우기
  const v = (id, val) => { const el = getElement(id); if (el) el.value = val || ''; };
  v('af_company', ad.advertiser?.company || ad.company || '');
  v('af_name', ad.advertiser?.name || ad.contact_name || '');
  v('af_phone', ad.advertiser?.phone || ad.contact_phone || '');
  v('af_title', ad.title || '');
  v('af_desc', ad.description || '');
  v('af_image', ad.imageUrl || ad.image_url || '');
  v('af_link', ad.linkUrl || ad.link_url || '');
  v('af_cta', ad.ctaText || ad.cta_text || '자세히 보기');
  v('af_type', ad.type || ad.ad_type || 'native_card');
  v('af_placement', ad.placement || 'search_top');
  v('af_bizTypes', (ad.targeting?.businessTypes || []).join(', '));
  v('af_regions', (ad.targeting?.regions || []).join(', '));
  v('af_start', ad.startDate || ad.start_date || '');
  v('af_end', ad.endDate || ad.end_date || '');
  v('af_billingModel', ad.billing?.model || ad.billing_model || 'monthly');
  v('af_amount', ad.billing?.amount || ad.billing_amount || 0);
  v('af_priority', ad.priority || 0);

  // 이미지 미리보기
  const imgUrl = ad.imageUrl || ad.image_url || '';
  const preview = getElement('ad-image-preview');
  const placeholder = getElement('ad-image-placeholder');
  if (imgUrl && preview) {
    preview.innerHTML = `<img src="${imgUrl}" style="max-width:100%;max-height:160px;border-radius:6px">`;
    preview.style.display = 'block';
    if (placeholder) placeholder.style.display = 'none';
  } else {
    if (preview) { preview.innerHTML = ''; preview.style.display = 'none'; }
    if (placeholder) placeholder.style.display = '';
  }

  _updateAdSizeHint();
  m.style.display = 'flex';
}

// 관리자 로그아웃
async function adminLogout() {
  await fetch(`${API_BASE}/admin/logout`, { method:'POST', credentials:'include' });
  _isAdmin = false;
  // 설정 페이지 버튼 복원
  const loginBtn = getElement('admin-login-btn');
  if (loginBtn) {
    loginBtn.textContent = '관리자 로그인';
    loginBtn.onclick = () => openAdminLogin();
  }
  navigateTo('dashboard');
  showToast('관리자 로그아웃');
}
