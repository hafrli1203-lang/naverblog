/*
  ════════════════════════════════════════════════════════════════
  프론트엔드 통합 코드 — 기존 index.html에 삽입
  
  포함 기능:
  1. 로그인 모달 (카카오/네이버/구글 SNS만)
  2. 유저 상태 관리 (로그인/비로그인 UI 전환)
  3. 광고 슬롯 렌더링 + 노출/클릭 추적
  4. 관리자 대시보드 (이용 현황 + 광고 관리)
  
  삽입 위치: </body> 바로 위
  ════════════════════════════════════════════════════════════════
*/


// ╔══════════════════════════════════════════════════════════════╗
// ║  PART 1: 로그인 모달 HTML — SNS 전용                         ║
// ╚══════════════════════════════════════════════════════════════╝

const LOGIN_MODAL_HTML = `

<!-- ═══════════════════ 로그인 모달 ═══════════════════ -->
<div id="loginModal" class="login-modal" style="display:none">
  <div class="login-overlay" onclick="closeLoginModal()"></div>
  <div class="login-box">
    <button class="login-close" onclick="closeLoginModal()">&times;</button>
    
    <div class="login-header">
      <svg viewBox="0 0 24 24" fill="none" width="32" height="32" style="margin-bottom:8px">
        <rect width="24" height="24" rx="6" fill="#2DB400"/>
        <path d="M6 12.5l4 4 8-8.5" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <h2>체험단모집</h2>
      <p>3초만에 시작하세요</p>
    </div>

    <!-- SNS 로그인 버튼 -->
    <div class="social-buttons">
      <a href="/auth/kakao" class="social-btn kakao-btn">
        <svg width="18" height="18" viewBox="0 0 18 18"><path d="M9 1C4.53 1 .9 3.81.9 7.27c0 2.23 1.49 4.18 3.74 5.28l-.95 3.5c-.08.3.25.54.5.37l3.71-2.47c.36.05.73.08 1.1.08 4.47 0 8.1-2.81 8.1-6.27S13.47 1 9 1z" fill="#000"/></svg>
        카카오로 시작하기
      </a>
      <a href="/auth/naver" class="social-btn naver-btn">
        <svg width="18" height="18" viewBox="0 0 18 18"><rect width="18" height="18" rx="2" fill="#03C75A"/><path d="M11.88 9.36L6.12 2.7H3.6v12.6h2.52V8.64L11.88 15.3H14.4V2.7h-2.52v6.66z" fill="#fff"/></svg>
        네이버로 시작하기
      </a>
      <a href="/auth/google" class="social-btn google-btn">
        <svg width="18" height="18" viewBox="0 0 18 18"><path d="M17.64 9.2c0-.63-.06-1.25-.16-1.84H9v3.48h4.84c-.21 1.1-.86 2.03-1.83 2.65v2.2h2.96c1.73-1.6 2.73-3.95 2.73-6.49z" fill="#4285F4"/><path d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.91-2.26c-.81.54-1.85.86-3.05.86-2.34 0-4.33-1.58-5.04-3.71H.96v2.33C2.44 15.98 5.48 18 9 18z" fill="#34A853"/><path d="M3.96 10.71c-.18-.54-.28-1.12-.28-1.71s.1-1.17.28-1.71V4.96H.96C.35 6.18 0 7.55 0 9s.35 2.82.96 4.04l3-2.33z" fill="#FBBC05"/><path d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0 5.48 0 2.44 2.02.96 4.96l3 2.33c.71-2.13 2.7-3.71 5.04-3.71z" fill="#EA4335"/></svg>
        구글로 시작하기
      </a>
    </div>

    <p class="login-footer">로그인하면 검색 기록과 캠페인이 자동 저장됩니다</p>
  </div>
</div>
`;


// ╔══════════════════════════════════════════════════════════════╗
// ║  PART 2: 광고 슬롯 HTML                                     ║
// ╚══════════════════════════════════════════════════════════════╝

const AD_SLOTS_HTML = `
<!-- Top 20 바로 위 -->
<div id="adSlot_search_top" class="ad-slot" style="display:none"></div>
<!-- Top 20 ↔ Pool 40 사이 -->
<div id="adSlot_search_middle" class="ad-slot" style="display:none"></div>
<!-- Pool 40 아래 -->
<div id="adSlot_search_bottom" class="ad-slot" style="display:none"></div>
<!-- 사이드바 -->
<div id="adSlot_sidebar" class="ad-slot" style="display:none"></div>
<!-- 블로그 분석 리포트 아래 -->
<div id="adSlot_report_bottom" class="ad-slot" style="display:none"></div>
<!-- 모바일 하단 고정 -->
<div id="adSlot_mobile_sticky" class="ad-slot ad-mobile-sticky" style="display:none"></div>
`;


// ╔══════════════════════════════════════════════════════════════╗
// ║  PART 3: 관리자 대시보드 HTML                                 ║
// ╚══════════════════════════════════════════════════════════════╝

const ADMIN_DASHBOARD_HTML = `
<div id="adminDashboard" class="section-panel" style="display:none">

  <div style="display:flex; align-items:center; gap:12px; margin-bottom:24px">
    <h2 style="font-size:1.3rem; font-weight:700; margin:0">📊 관리자 대시보드</h2>
    <button onclick="refreshAdminDashboard()" class="admin-refresh-btn">새로고침</button>
  </div>

  <div class="admin-tabs">
    <button class="admin-tab active" onclick="switchAdminTab('overview')">이용 현황</button>
    <button class="admin-tab" onclick="switchAdminTab('users')">회원 관리</button>
    <button class="admin-tab" onclick="switchAdminTab('searches')">검색 분석</button>
    <button class="admin-tab" onclick="switchAdminTab('ads')">광고 관리</button>
    <button class="admin-tab" onclick="switchAdminTab('live')">실시간</button>
  </div>

  <!-- 이용 현황 -->
  <div id="adminTab_overview" class="admin-tab-content">
    <div class="admin-stats-grid">
      <div class="admin-stat-card">
        <div class="admin-stat-label">오늘 페이지뷰</div>
        <div class="admin-stat-value" id="stat_pageViews">-</div>
      </div>
      <div class="admin-stat-card">
        <div class="admin-stat-label">오늘 검색</div>
        <div class="admin-stat-value" id="stat_searches">-</div>
      </div>
      <div class="admin-stat-card">
        <div class="admin-stat-label">현재 접속</div>
        <div class="admin-stat-value" id="stat_online">-</div>
        <div class="admin-stat-sub">최근 5분</div>
      </div>
      <div class="admin-stat-card">
        <div class="admin-stat-label">전체 회원</div>
        <div class="admin-stat-value" id="stat_totalUsers">-</div>
      </div>
      <div class="admin-stat-card">
        <div class="admin-stat-label">오늘 신규</div>
        <div class="admin-stat-value" id="stat_newToday">-</div>
      </div>
      <div class="admin-stat-card">
        <div class="admin-stat-label">광고 수익 (월)</div>
        <div class="admin-stat-value" id="stat_adRevenue">-</div>
      </div>
    </div>
    <div class="admin-section">
      <h3>시간대별 방문 (오늘)</h3>
      <div id="hourlyChart" class="hourly-chart"></div>
    </div>
    <div class="admin-section">
      <h3>최근 30일 추이</h3>
      <div id="rangeChart" class="range-chart"></div>
    </div>
  </div>

  <!-- 회원 관리 -->
  <div id="adminTab_users" class="admin-tab-content" style="display:none">
    <div class="admin-section">
      <h3>로그인 방식별</h3>
      <div id="providerStats"></div>
    </div>
    <div class="admin-section">
      <h3>최근 가입 회원</h3>
      <div id="recentUsersList"></div>
    </div>
  </div>

  <!-- 검색 분석 -->
  <div id="adminTab_searches" class="admin-tab-content" style="display:none">
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px">
      <div class="admin-section">
        <h3>인기 검색 지역 (7일)</h3>
        <div id="topRegions"></div>
      </div>
      <div class="admin-section">
        <h3>인기 검색 업종 (7일)</h3>
        <div id="topTopics"></div>
      </div>
    </div>
  </div>

  <!-- 광고 관리 -->
  <div id="adminTab_ads" class="admin-tab-content" style="display:none">
    <div class="admin-stats-grid" id="adStats" style="margin-bottom:16px"></div>
    <button class="admin-btn-primary" onclick="openAdForm()" style="margin-bottom:16px">+ 새 광고 등록</button>
    <div id="adsList"></div>
  </div>

  <!-- 실시간 -->
  <div id="adminTab_live" class="admin-tab-content" style="display:none">
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px">
      <div class="admin-section">
        <h3>실시간 검색</h3>
        <div id="liveSearches" class="live-feed"></div>
      </div>
      <div class="admin-section">
        <h3>실시간 이벤트</h3>
        <div id="liveEvents" class="live-feed"></div>
      </div>
    </div>
  </div>
</div>

<!-- 광고 등록 모달 -->
<div id="adFormModal" class="login-modal" style="display:none">
  <div class="login-overlay" onclick="closeAdForm()"></div>
  <div class="login-box" style="max-width:560px; max-height:85vh; overflow-y:auto">
    <button class="login-close" onclick="closeAdForm()">&times;</button>
    <h3 id="adFormTitle" style="margin-bottom:16px">새 광고 등록</h3>
    <div class="ad-form-section">
      <label>광고주 회사</label>
      <input id="af_company" class="login-input" placeholder="예: 스마트POS">
      <label>담당자 / 연락처</label>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px">
        <input id="af_name" class="login-input" placeholder="담당자명">
        <input id="af_phone" class="login-input" placeholder="010-0000-0000">
      </div>
    </div>
    <div class="ad-form-section">
      <label>광고 제목</label>
      <input id="af_title" class="login-input" placeholder="예: 매출이 오르는 POS, 첫 달 무료">
      <label>설명</label>
      <input id="af_desc" class="login-input" placeholder="자영업자 전용 올인원 POS 시스템">
      <label>배너 이미지 URL</label>
      <input id="af_image" class="login-input" placeholder="https://...">
      <label>클릭 시 이동 URL</label>
      <input id="af_link" class="login-input" placeholder="https://광고주사이트.com">
      <label>버튼 텍스트</label>
      <input id="af_cta" class="login-input" placeholder="자세히 보기" value="자세히 보기">
    </div>
    <div class="ad-form-section">
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px">
        <div>
          <label>유형</label>
          <select id="af_type" class="login-input">
            <option value="native_card">네이티브 카드</option>
            <option value="banner_horizontal">가로 배너</option>
            <option value="banner_sidebar">사이드바 배너</option>
            <option value="text_link">텍스트 링크</option>
          </select>
        </div>
        <div>
          <label>위치</label>
          <select id="af_placement" class="login-input">
            <option value="search_top">검색 상단</option>
            <option value="search_middle">Top20↔Pool40 사이</option>
            <option value="sidebar">사이드바</option>
            <option value="report_bottom">리포트 하단</option>
          </select>
        </div>
      </div>
    </div>
    <div class="ad-form-section">
      <label>타겟 업종 (쉼표 구분, "all"=전업종)</label>
      <input id="af_bizTypes" class="login-input" placeholder="음식점,카페 또는 all">
      <label>타겟 지역 (쉼표 구분, 비워두면 전국)</label>
      <input id="af_regions" class="login-input" placeholder="김해,부산">
    </div>
    <div class="ad-form-section">
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px">
        <div><label>시작일</label><input type="date" id="af_start" class="login-input"></div>
        <div><label>종료일</label><input type="date" id="af_end" class="login-input"></div>
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; margin-top:6px">
        <div>
          <label>과금</label>
          <select id="af_billingModel" class="login-input">
            <option value="monthly">월정액</option>
            <option value="weekly">주정액</option>
          </select>
        </div>
        <div><label>금액 (원)</label><input type="number" id="af_amount" class="login-input" placeholder="100000"></div>
        <div><label>우선순위</label><input type="number" id="af_priority" class="login-input" value="0" min="0"></div>
      </div>
    </div>
    <div style="display:flex; gap:8px; margin-top:16px">
      <button class="login-submit" style="background:#888" onclick="closeAdForm()">취소</button>
      <button class="login-submit" onclick="saveAd()">저장</button>
    </div>
  </div>
</div>
`;


// ╔══════════════════════════════════════════════════════════════╗
// ║  PART 4: CSS                                                ║
// ╚══════════════════════════════════════════════════════════════╝

const ALL_STYLES = `
<style>
/* ═══ 로그인 모달 ═══ */
.login-modal { position:fixed; inset:0; z-index:9999; display:flex; align-items:center; justify-content:center; }
.login-overlay { position:absolute; inset:0; background:rgba(0,0,0,0.5); backdrop-filter:blur(4px); }
.login-box { position:relative; width:380px; max-width:92vw; background:#fff; border-radius:16px; padding:32px; box-shadow:0 20px 60px rgba(0,0,0,0.2); }
.login-close { position:absolute; top:12px; right:16px; background:none; border:none; font-size:1.5rem; color:#999; cursor:pointer; }
.login-header { text-align:center; margin-bottom:24px; }
.login-header h2 { font-size:1.25rem; font-weight:700; margin:0 0 4px; }
.login-header p { font-size:0.85rem; color:#888; margin:0; }
.login-footer { text-align:center; font-size:.75rem; color:#aaa; margin-top:16px; }

.social-buttons { display:flex; flex-direction:column; gap:10px; }
.social-btn { display:flex; align-items:center; justify-content:center; gap:10px; padding:12px; border-radius:10px; font-size:0.9rem; font-weight:600; text-decoration:none; transition:all .15s; }
.social-btn:hover { opacity:.88; transform:translateY(-1px); box-shadow:0 4px 12px rgba(0,0,0,.1); }
.kakao-btn { background:#FEE500; color:#000; }
.naver-btn { background:#03C75A; color:#fff; }
.google-btn { background:#fff; color:#333; border:1px solid #ddd; }

.login-input { width:100%; padding:10px 12px; margin-bottom:6px; border:1px solid #e0e0e0; border-radius:8px; font-size:.88rem; outline:none; font-family:inherit; box-sizing:border-box; }
.login-input:focus { border-color:#2DB400; }
.login-submit { width:100%; padding:11px; margin-top:4px; background:#1a1a1a; color:#fff; border:none; border-radius:8px; font-size:.9rem; font-weight:600; cursor:pointer; font-family:inherit; }
.login-submit:hover { background:#333; }

/* ═══ 광고 슬롯 ═══ */
.ad-slot { margin:16px 0; }
.ad-native { background:#f8faff; border:1px solid #e3ecf7; border-radius:12px; padding:14px 18px; display:flex; align-items:center; gap:14px; cursor:pointer; transition:all .15s; position:relative; }
.ad-native:hover { background:#f0f5ff; border-color:#c5d6ee; }
.ad-native-img { width:52px; height:52px; border-radius:10px; object-fit:cover; flex-shrink:0; }
.ad-native-body { flex:1; min-width:0; }
.ad-native-badge { display:inline-block; background:#e8f0fe; color:#4a7fc1; font-size:.62rem; font-weight:700; padding:2px 7px; border-radius:6px; margin-bottom:3px; }
.ad-native-title { font-size:.92rem; font-weight:600; color:#1a1a1a; margin-bottom:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ad-native-desc { font-size:.8rem; color:#666; line-height:1.3; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.ad-native-cta { flex-shrink:0; background:#2E75B6; color:#fff; border:none; padding:7px 14px; border-radius:8px; font-size:.8rem; font-weight:600; cursor:pointer; }
.ad-native-cta:hover { background:#245d94; }
.ad-banner { position:relative; border-radius:10px; overflow:hidden; background:#f8f9fa; border:1px solid #eee; }
.ad-banner a { display:block; }
.ad-banner img { width:100%; height:auto; display:block; }
.ad-banner:hover { box-shadow:0 2px 12px rgba(0,0,0,.08); }
.ad-badge { position:absolute; top:5px; left:7px; background:rgba(0,0,0,.4); color:#fff; font-size:.58rem; font-weight:700; padding:2px 6px; border-radius:3px; letter-spacing:.7px; }
.ad-textlink { display:flex; align-items:center; gap:8px; padding:9px 14px; background:#fafafa; border-radius:7px; font-size:.83rem; color:#555; cursor:pointer; position:relative; }
.ad-textlink:hover { background:#f0f0f0; }
.ad-textlink .ad-badge { position:static; background:none; color:#999; padding:0; font-size:.62rem; }
.ad-textlink a { color:#2E75B6; text-decoration:none; font-weight:500; }
#adSlot_sidebar .ad-native { background:#222; border-color:#333; flex-direction:column; text-align:center; gap:8px; padding:12px; }
#adSlot_sidebar .ad-native:hover { background:#2a2a2a; }
#adSlot_sidebar .ad-native-badge { background:#333; color:#8cb4e0; }
#adSlot_sidebar .ad-native-title { color:#eee; font-size:.84rem; white-space:normal; }
#adSlot_sidebar .ad-native-desc { color:#999; font-size:.76rem; }
#adSlot_sidebar .ad-native-cta { width:100%; padding:7px; font-size:.76rem; }
.ad-mobile-sticky { display:none !important; }
@media(max-width:768px) {
  .ad-mobile-sticky { display:block !important; position:fixed; bottom:0; left:0; right:0; z-index:999; margin:0; background:#fff; border-top:1px solid #eee; padding:6px 10px; box-shadow:0 -2px 10px rgba(0,0,0,.06); }
}

/* ═══ 관리자 ═══ */
.admin-tabs { display:flex; gap:4px; margin-bottom:20px; flex-wrap:wrap; }
.admin-tab { padding:8px 16px; border:1px solid #e0e0e0; border-radius:8px; background:#fff; font-size:.82rem; cursor:pointer; font-family:inherit; transition:all .15s; }
.admin-tab:hover { background:#f5f5f5; }
.admin-tab.active { background:#1a1a1a; color:#fff; border-color:#1a1a1a; }
.admin-stats-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px,1fr)); gap:12px; margin-bottom:20px; }
.admin-stat-card { background:#f8f9fa; border:1px solid #eee; border-radius:10px; padding:14px 16px; }
.admin-stat-label { font-size:.75rem; color:#888; margin-bottom:4px; }
.admin-stat-value { font-size:1.4rem; font-weight:700; color:#1a1a1a; }
.admin-stat-sub { font-size:.68rem; color:#aaa; margin-top:2px; }
.admin-section { background:#f8f9fa; border:1px solid #eee; border-radius:10px; padding:16px; margin-bottom:16px; }
.admin-section h3 { font-size:.9rem; font-weight:600; margin:0 0 12px; }
.admin-refresh-btn { padding:5px 12px; border:1px solid #ddd; border-radius:6px; background:#fff; font-size:.75rem; cursor:pointer; font-family:inherit; }
.admin-btn-primary { padding:8px 16px; background:#2DB400; color:#fff; border:none; border-radius:8px; font-size:.85rem; font-weight:600; cursor:pointer; font-family:inherit; }
.hourly-chart { display:flex; align-items:flex-end; gap:3px; height:80px; }
.hourly-bar { flex:1; background:#2DB400; border-radius:2px 2px 0 0; min-height:2px; transition:height .3s; position:relative; }
.hourly-bar:hover::after { content:attr(data-label); position:absolute; bottom:calc(100%+4px); left:50%; transform:translateX(-50%); background:#333; color:#fff; font-size:.65rem; padding:2px 6px; border-radius:4px; white-space:nowrap; }
.live-feed { max-height:400px; overflow-y:auto; }
.live-item { padding:8px 0; border-bottom:1px solid #f0f0f0; font-size:.82rem; }
.live-time { color:#999; font-size:.72rem; }
.live-user { color:#2E75B6; font-weight:500; }
.ad-list-item { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border:1px solid #eee; border-radius:10px; margin-bottom:8px; gap:12px; }
.ad-list-item.inactive { opacity:.5; }
.ad-list-title { font-weight:600; font-size:.88rem; }
.ad-list-meta { font-size:.75rem; color:#888; margin-top:2px; }
.ad-list-stats { font-size:.78rem; color:#666; display:flex; gap:10px; }
.ad-list-actions { display:flex; gap:4px; margin-top:6px; }
.ad-list-actions button { padding:4px 10px; border:1px solid #ddd; border-radius:5px; background:#fff; font-size:.72rem; cursor:pointer; font-family:inherit; }
.ad-form-section { margin-bottom:14px; }
.ad-form-section label { display:block; font-size:.78rem; color:#666; margin-bottom:3px; font-weight:500; }
</style>
`;


// ╔══════════════════════════════════════════════════════════════╗
// ║  PART 5: JavaScript                                         ║
// ╚══════════════════════════════════════════════════════════════╝

const ALL_JS = `
<script>
// ═══════════════════════════════════════════════════════
// 1. 로그인 (SNS만)
// ═══════════════════════════════════════════════════════

let currentUser = null;

function openLoginModal()  { document.getElementById('loginModal').style.display = 'flex'; }
function closeLoginModal() { document.getElementById('loginModal').style.display = 'none'; }

async function checkAuth() {
  try {
    const res = await fetch('/auth/me', { credentials: 'include' });
    const data = await res.json();
    if (data.loggedIn) { currentUser = data.user; onLoggedIn(); }
    else { onLoggedOut(); }
  } catch (e) { onLoggedOut(); }
}

function onLoggedIn() {
  const userEl = document.querySelector('.user-btn');
  if (userEl) {
    const initial = currentUser.profileImage
      ? '<img src="' + currentUser.profileImage + '" class="user-avatar-img">'
      : '<div class="user-avatar">' + currentUser.displayName[0] + '</div>';
    userEl.innerHTML = initial +
      '<div class="user-info">' +
        '<div class="user-name">' + currentUser.displayName + '</div>' +
        '<div class="user-plan">' + currentUser.provider + ' · ' +
          '<a href="#" onclick="doLogout(); return false" style="color:#999;font-size:.75rem">로그아웃</a></div>' +
      '</div>';
  }
  if (currentUser.role === 'admin' || currentUser.email === (window.__ADMIN_EMAIL || '')) {
    showAdminMenu();
  }
  if (location.search.includes('login=success')) history.replaceState(null, '', '/');
  loadUserData();
}

function onLoggedOut() {
  currentUser = null;
  const userEl = document.querySelector('.user-btn');
  if (userEl) {
    userEl.innerHTML =
      '<div class="user-avatar" style="background:#666;cursor:pointer" onclick="openLoginModal()">?</div>' +
      '<div class="user-info">' +
        '<div class="user-name" style="cursor:pointer" onclick="openLoginModal()">로그인</div>' +
        '<div class="user-plan">SNS로 3초만에 시작하세요</div>' +
      '</div>';
  }
}

async function doLogout() {
  await fetch('/auth/logout', { method: 'POST', credentials: 'include' });
  currentUser = null;
  onLoggedOut();
}

async function loadUserData() {
  if (!currentUser) return;
  try {
    const [historyRes, bloggersRes, campaignsRes] = await Promise.all([
      fetch('/api/history',   { credentials: 'include' }),
      fetch('/api/bloggers',  { credentials: 'include' }),
      fetch('/api/campaigns', { credentials: 'include' }),
    ]);
    // 기존 UI 렌더링 함수 호출
    // renderSearchHistory(await historyRes.json());
    // renderSavedBloggers(await bloggersRes.json());
    // renderCampaigns(await campaignsRes.json());
  } catch (e) {}
}


// ═══════════════════════════════════════════════════════
// 2. 광고
// ═══════════════════════════════════════════════════════

async function loadAds(topic, region, keyword) {
  const placements = ['search_top', 'search_middle', 'sidebar'];
  for (const placement of placements) {
    try {
      const params = new URLSearchParams({ placement });
      if (topic)   params.set('topic', topic);
      if (region)  params.set('region', region);
      if (keyword) params.set('keyword', keyword);
      const res = await fetch('/ads/match?' + params.toString());
      const ads = await res.json();
      const container = document.getElementById('adSlot_' + placement);
      if (!container) continue;
      if (ads.length > 0) { renderAd(ads[0], container); container.style.display = 'block'; }
      else { container.style.display = 'none'; }
    } catch (e) {}
  }
}

function renderAd(ad, container) {
  const id = ad._id;
  if (ad.type === 'banner_horizontal' || ad.type === 'banner_sidebar') {
    container.innerHTML = '<div class="ad-banner" data-ad-id="' + id + '"><a href="#" onclick="onAdClick(\\'' + id + '\\'); return false"><img src="' + ad.imageUrl + '" alt="' + ad.title + '"></a><span class="ad-badge">AD</span></div>';
  } else if (ad.type === 'native_card') {
    container.innerHTML = '<div class="ad-native" data-ad-id="' + id + '" onclick="onAdClick(\\'' + id + '\\')">' +
      (ad.imageUrl ? '<img src="' + ad.imageUrl + '" class="ad-native-img">' : '') +
      '<div class="ad-native-body"><div class="ad-native-badge">추천 서비스</div><div class="ad-native-title">' + ad.title + '</div><div class="ad-native-desc">' + (ad.description||'') + '</div></div>' +
      '<button class="ad-native-cta">' + (ad.ctaText||'자세히 보기') + '</button></div>';
  } else if (ad.type === 'text_link') {
    container.innerHTML = '<div class="ad-textlink" data-ad-id="' + id + '"><span class="ad-badge">AD</span><a href="#" onclick="onAdClick(\\'' + id + '\\'); return false">' + ad.title + '</a></div>';
  }
  trackImpression(id, container);
}

function trackImpression(adId, container) {
  const el = container.querySelector('[data-ad-id]');
  if (!el) return;
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { fetch('/ads/impression/' + adId, { method: 'POST' }); obs.unobserve(el); } });
  }, { threshold: 0.5 });
  obs.observe(el);
}

async function onAdClick(adId) {
  try {
    const res = await fetch('/ads/click/' + adId, { method: 'POST' });
    const data = await res.json();
    if (data.redirectUrl) window.open(data.redirectUrl, '_blank');
  } catch (e) {}
}


// ═══════════════════════════════════════════════════════
// 3. 관리자
// ═══════════════════════════════════════════════════════

function showAdminMenu() {
  const nav = document.querySelector('.nav-items') || document.querySelector('.sidebar nav');
  if (nav && !document.getElementById('navAdmin')) {
    const item = document.createElement('a');
    item.id = 'navAdmin';
    item.href = '#admin';
    item.className = 'nav-item';
    item.innerHTML = '<span>📊</span> <span>관리자</span>';
    item.onclick = (e) => { e.preventDefault(); showSection('adminDashboard'); refreshAdminDashboard(); };
    nav.appendChild(item);
  }
}

function switchAdminTab(tab) {
  document.querySelectorAll('.admin-tab-content').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.admin-tab').forEach(el => el.classList.remove('active'));
  document.getElementById('adminTab_' + tab).style.display = 'block';
  event.target.classList.add('active');
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
      fetch('/admin/analytics/today',      { credentials:'include' }),
      fetch('/admin/analytics/range?days=30', { credentials:'include' }),
      fetch('/admin/ads/stats',             { credentials:'include' }),
      fetch('/admin/analytics/users',       { credentials:'include' }),
    ]);
    const today=await todayRes.json(), range=await rangeRes.json(), ads=await adRes.json(), users=await userRes.json();
    document.getElementById('stat_pageViews').textContent = today.pageViews.toLocaleString();
    document.getElementById('stat_searches').textContent = today.searches.toLocaleString();
    document.getElementById('stat_online').textContent = today.estimatedOnline;
    document.getElementById('stat_totalUsers').textContent = users.total.toLocaleString();
    document.getElementById('stat_newToday').textContent = users.newToday;
    document.getElementById('stat_adRevenue').textContent = ads.monthlyRevenue.toLocaleString() + '원';
    const maxH = Math.max(...today.hourlyViews, 1);
    document.getElementById('hourlyChart').innerHTML = today.hourlyViews.map((v,i) =>
      '<div class="hourly-bar" style="height:' + (v/maxH*100) + '%" data-label="' + i + '시 ' + v + '뷰"></div>'
    ).join('');
    document.getElementById('rangeChart').innerHTML = '<table style="width:100%;font-size:.78rem"><tr><th style="text-align:left">날짜</th><th>PV</th><th>검색</th><th>신규</th></tr>' +
      range.data.slice(-10).map(d => '<tr><td>'+d.date.slice(5)+'</td><td style="text-align:right">'+d.pageViews+'</td><td style="text-align:right">'+d.searches+'</td><td style="text-align:right">'+d.newUsers+'</td></tr>').join('') +
      '</table><div style="font-size:.72rem;color:#999;margin-top:6px">30일 합계: PV '+range.totals.pageViews.toLocaleString()+' / 검색 '+range.totals.searches.toLocaleString()+' / 신규 '+range.totals.newUsers+'</div>';
  } catch(e) { console.error('대시보드 로드 실패:', e); }
}

async function loadUsersTab() {
  try {
    const data = await (await fetch('/admin/analytics/users', { credentials:'include' })).json();
    document.getElementById('providerStats').innerHTML = data.byProvider.map(p =>
      '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f0f0"><span>'+p.provider+'</span><strong>'+p.count+'명</strong></div>'
    ).join('');
    document.getElementById('recentUsersList').innerHTML = '<table style="width:100%;font-size:.8rem"><tr><th>이름</th><th>이메일</th><th>방식</th><th>가입일</th><th>최근접속</th></tr>' +
      data.recentUsers.map(u => '<tr><td>'+u.displayName+'</td><td>'+(u.email||'-')+'</td><td>'+u.provider+'</td><td>'+new Date(u.createdAt).toLocaleDateString()+'</td><td>'+new Date(u.lastLoginAt).toLocaleDateString()+'</td></tr>').join('') + '</table>';
  } catch(e) {}
}

async function loadSearchesTab() {
  try {
    const data = await (await fetch('/admin/analytics/popular?days=7', { credentials:'include' })).json();
    document.getElementById('topRegions').innerHTML = data.topRegions.map((r,i) =>
      '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f0f0"><span>'+(i+1)+'. '+r.name+'</span><strong>'+r.count+'회</strong></div>'
    ).join('') || '<div style="color:#999">데이터 없음</div>';
    document.getElementById('topTopics').innerHTML = data.topTopics.map((t,i) =>
      '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f0f0"><span>'+(i+1)+'. '+t.name+'</span><strong>'+t.count+'회</strong></div>'
    ).join('') || '<div style="color:#999">데이터 없음</div>';
  } catch(e) {}
}

async function loadAdsTab() {
  try {
    const [stats, ads] = await Promise.all([
      (await fetch('/admin/ads/stats', { credentials:'include' })).json(),
      (await fetch('/admin/ads',       { credentials:'include' })).json(),
    ]);
    document.getElementById('adStats').innerHTML =
      '<div class="admin-stat-card"><div class="admin-stat-label">운영 중</div><div class="admin-stat-value">'+stats.activeCount+'</div></div>' +
      '<div class="admin-stat-card"><div class="admin-stat-label">총 노출</div><div class="admin-stat-value">'+stats.totalImpressions.toLocaleString()+'</div></div>' +
      '<div class="admin-stat-card"><div class="admin-stat-label">총 클릭</div><div class="admin-stat-value">'+stats.totalClicks.toLocaleString()+'</div></div>' +
      '<div class="admin-stat-card"><div class="admin-stat-label">평균 CTR</div><div class="admin-stat-value">'+stats.avgCtr+'%</div></div>';
    document.getElementById('adsList').innerHTML = ads.map(ad => {
      const ctr = ad.stats.impressions > 0 ? ((ad.stats.clicks/ad.stats.impressions)*100).toFixed(1) : '0.0';
      return '<div class="ad-list-item '+(ad.isActive?'':'inactive')+'"><div><div class="ad-list-title">'+ad.title+'</div><div class="ad-list-meta">'+(ad.advertiser?.company||'')+' · '+ad.placement+' · '+ad.targeting?.businessTypes?.join(',')+'</div></div><div style="text-align:right"><div class="ad-list-stats"><span>노출 '+ad.stats.impressions.toLocaleString()+'</span><span>클릭 '+ad.stats.clicks.toLocaleString()+'</span><span>CTR '+ctr+'%</span></div><div class="ad-list-actions"><button onclick="toggleAd(\\''+ad._id+'\\','+!ad.isActive+')">'+(ad.isActive?'중지':'활성')+'</button></div></div></div>';
    }).join('') || '<div style="color:#999">등록된 광고 없음</div>';
  } catch(e) {}
}

async function loadLiveTab() {
  try {
    const [searches, events] = await Promise.all([
      (await fetch('/admin/analytics/searches', { credentials:'include' })).json(),
      (await fetch('/admin/analytics/events',   { credentials:'include' })).json(),
    ]);
    document.getElementById('liveSearches').innerHTML = searches.slice(0,30).map(s =>
      '<div class="live-item"><span class="live-user">'+s.user+'</span> '+[s.region,s.topic,s.keyword].filter(Boolean).join(' · ')+' <span class="live-time">'+new Date(s.time).toLocaleTimeString()+'</span></div>'
    ).join('') || '<div style="color:#999">검색 기록 없음</div>';
    const labels = { login:'🔑 로그인', register:'📝 가입', blogger_save:'⭐ 블로거 저장', campaign_create:'📋 캠페인 생성' };
    document.getElementById('liveEvents').innerHTML = events.slice(0,30).map(e =>
      '<div class="live-item">'+(labels[e.event]||e.event)+' <span class="live-user">'+e.user+'</span> <span class="live-time">'+new Date(e.time).toLocaleTimeString()+'</span></div>'
    ).join('') || '<div style="color:#999">이벤트 없음</div>';
  } catch(e) {}
}

let editingAdId = null;
function openAdForm() { editingAdId=null; document.getElementById('adFormModal').style.display='flex'; }
function closeAdForm() { document.getElementById('adFormModal').style.display='none'; }

async function saveAd() {
  const body = {
    advertiser: { company:document.getElementById('af_company').value, name:document.getElementById('af_name').value, phone:document.getElementById('af_phone').value },
    title:document.getElementById('af_title').value, description:document.getElementById('af_desc').value,
    imageUrl:document.getElementById('af_image').value, linkUrl:document.getElementById('af_link').value,
    ctaText:document.getElementById('af_cta').value, type:document.getElementById('af_type').value,
    placement:document.getElementById('af_placement').value,
    targeting: { businessTypes:document.getElementById('af_bizTypes').value.split(',').map(s=>s.trim()).filter(Boolean), regions:document.getElementById('af_regions').value.split(',').map(s=>s.trim()).filter(Boolean) },
    startDate:document.getElementById('af_start').value, endDate:document.getElementById('af_end').value,
    billing: { model:document.getElementById('af_billingModel').value, amount:parseInt(document.getElementById('af_amount').value)||0 },
    priority:parseInt(document.getElementById('af_priority').value)||0,
  };
  await fetch(editingAdId?'/admin/ads/'+editingAdId:'/admin/ads', { method:editingAdId?'PUT':'POST', headers:{'Content-Type':'application/json'}, credentials:'include', body:JSON.stringify(body) });
  closeAdForm(); loadAdsTab();
}

async function toggleAd(id, active) {
  await fetch('/admin/ads/'+id, { method:'PUT', headers:{'Content-Type':'application/json'}, credentials:'include', body:JSON.stringify({isActive:active}) });
  loadAdsTab();
}

// ═══ 앱 시작 ═══
checkAuth();
</script>
`;
