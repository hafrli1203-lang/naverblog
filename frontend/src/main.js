const API_BASE = "http://localhost:8001";

const getElement = (id) => document.getElementById(id);

// === SPA 라우팅 ===
const navLinks = document.querySelectorAll(".nav-link");
const pages = document.querySelectorAll(".page");

function navigateTo(page) {
  pages.forEach((p) => p.classList.remove("active"));
  navLinks.forEach((l) => l.classList.remove("active"));

  const target = getElement(`page-${page}`);
  if (target) target.classList.add("active");
  const link = document.querySelector(`.nav-link[data-page="${page}"]`);
  if (link) link.classList.add("active");

  if (page === "campaigns") loadCampaigns();
}

function handleRouting() {
  const hash = window.location.hash.replace("#", "") || "dashboard";
  navigateTo(hash);
}

window.addEventListener("hashchange", handleRouting);
window.addEventListener("DOMContentLoaded", handleRouting);

// === 대시보드 요소 ===
const searchBtn = getElement("search-btn");
const regionInput = getElement("region-input");
const categoryInput = getElement("category-input");
const storeNameInput = getElement("store-name-input");
const addressInput = getElement("address-input");
const resultsArea = getElement("results-area");
const loadingState = document.querySelector(".loading-state");
const progressArea = getElement("progress-area");
const progressStage = getElement("progress-stage");
const progressText = getElement("progress-text");
const progressBarFill = getElement("progress-bar-fill");
const metaArea = getElement("meta-area");
const top10Section = getElement("top10-section");
const top50Section = getElement("top50-section");
const top10List = getElement("top10-list");
const top50List = getElement("top50-list");

// 모달 요소
const detailModal = getElement("detail-modal");
const modalCloseBtn = getElement("modal-close-btn");
const modalBloggerName = getElement("modal-blogger-name");
const modalBlogLink = getElement("modal-blog-link");
const modalScoreDetails = getElement("modal-score-details");

const STAGE_LABELS = {
  search: "키워드 검색",
  broad_search: "확장 후보 수집",
  scoring: "점수 계산",
  exposure: "노출 분석",
  finalize: "결과 정리",
  done: "완료",
  waiting: "처리 중",
};

// === 검색 (SSE) ===
searchBtn.addEventListener("click", () => {
  const region = regionInput.value.trim();
  const category = categoryInput.value.trim();
  const storeName = storeNameInput.value.trim();
  const addressText = addressInput.value.trim();

  if (!region && !category && !storeName && !addressText) {
    alert("지역, 카테고리, 매장명, 주소 중 하나 이상 입력해주세요.");
    return;
  }

  resultsArea.classList.remove("hidden");
  loadingState.classList.remove("hidden");
  top10Section.classList.add("hidden");
  top50Section.classList.add("hidden");
  metaArea.classList.add("hidden");
  top10List.innerHTML = "";
  top50List.innerHTML = "";
  progressArea.classList.remove("hidden");
  progressBarFill.style.width = "0%";
  progressStage.textContent = "";
  progressText.textContent = "검색 시작 중...";
  searchBtn.disabled = true;

  const params = new URLSearchParams();
  if (region) params.set("region", region);
  if (category) params.set("category", category);
  if (storeName) params.set("store_name", storeName);
  if (addressText) params.set("address", addressText);

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

    renderResults(result);

    loadingState.classList.add("hidden");
    progressArea.classList.add("hidden");
    searchBtn.disabled = false;
    eventSource.close();
  });

  eventSource.addEventListener("error", () => {
    eventSource.close();
    progressArea.classList.add("hidden");
    fallbackSearch(region, category, storeName, addressText);
  });
});

async function fallbackSearch(region, category, storeName, addressText) {
  try {
    const body = {};
    if (region) body.region = region;
    if (category) body.category = category;
    if (storeName) body.store_name = storeName;
    if (addressText) body.address = addressText;

    const response = await fetch(`${API_BASE}/api/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) throw new Error("API 요청 실패");

    const result = await response.json();
    renderResults(result);
  } catch (error) {
    console.error(error);
    alert("블로거 데이터를 가져오지 못했습니다. 백엔드 서버가 실행 중인지 확인하세요.");
  } finally {
    loadingState.classList.add("hidden");
    searchBtn.disabled = false;
  }
}

// === 결과 렌더링 ===
let allBloggers = []; // 현재 검색 결과 전체

function renderResults(result) {
  // 백엔드가 배열을 직접 반환하는 경우 처리
  const bloggers = Array.isArray(result) ? result : (result.bloggers || []);
  allBloggers = bloggers;

  if (bloggers.length === 0) {
    top10Section.classList.remove("hidden");
    top10List.innerHTML = '<p class="empty-text">검색 결과가 없습니다.</p>';
    return;
  }

  // 상위 10명 = Top10, 나머지 = Top50
  const top10 = bloggers.slice(0, 10);
  const top50 = bloggers.slice(10);

  // 메타 정보
  metaArea.classList.remove("hidden");
  getElement("meta-store").textContent = `총 ${bloggers.length}명 분석 완료`;
  getElement("meta-calls").textContent = "";
  getElement("meta-keywords").textContent = "";

  // Top10
  if (top10.length > 0) {
    top10Section.classList.remove("hidden");
    top10List.innerHTML = top10.map((b, idx) => renderBloggerCard(b, idx + 1, true)).join("");
    attachCardEvents(top10List, top10);
  }

  // Top50
  if (top50.length > 0) {
    top50Section.classList.remove("hidden");
    top50List.innerHTML = top50.map((b, idx) => renderBloggerCard(b, idx + 11, false)).join("");
    attachCardEvents(top50List, top50);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderBloggerCard(blogger, rank, isTop10) {
  const blogUrl = blogger.blog_url || `https://blog.naver.com/${blogger.id}`;
  const totalScore = blogger.total_score || 0;
  const sb = blogger.score_breakdown || {};
  const details = blogger.exposure_details || [];

  // 노출 이력 계산
  const exposedCount = details.filter(d => d.rank > 0).length;
  const totalChecked = details.length;
  const top10Count = details.filter(d => d.rank > 0 && d.rank <= 10).length;

  // 점수 항목
  const scores = [
    { label: "활동빈도", value: sb.activity_frequency || 0, max: 15, color: "#10b981", desc: "게시물 작성 간격" },
    { label: "키워드관련", value: sb.keyword_relevance || 0, max: 15, color: "#6366f1", desc: "검색 키워드 매칭" },
    { label: "블로그지수", value: sb.blog_index || 0, max: 15, color: "#8b5cf6", desc: "평균 검색 순위 (낮을수록 높음)" },
    { label: "지역콘텐츠", value: sb.local_content || 0, max: 15, color: "#f59e0b", desc: "지역명 포함 비율" },
    { label: "최근활동", value: sb.recent_activity || 0, max: 15, color: "#ec4899", desc: "최신 게시물 날짜" },
    { label: "상위노출", value: sb.exposure_score || 0, max: 25, color: "#ef4444", desc: "키워드별 실제 노출 순위" },
  ];

  // 배지
  const badges = [];
  if ((sb.local_content || 0) >= 12) badges.push('<span class="exposure-badge">지역활동</span>');
  if (exposedCount >= 3) badges.push('<span class="food-badge">노출우수</span>');

  // 최근 게시물
  const recentPost = (blogger.recent_posts && blogger.recent_posts.length > 0)
    ? blogger.recent_posts[0] : null;

  // 노출 키워드 요약 (상위노출된 것만)
  const exposedKeywords = details
    .filter(d => d.rank > 0)
    .map(d => `<span class="exposed-kw">${escapeHtml(d.keyword)} <em>${d.rank}위</em></span>`)
    .join("");

  const scoreBars = scores.map(s => `
    <div class="score-bar-row" title="${s.desc}">
      <span class="score-bar-label">${s.label}</span>
      <div class="score-bar-track">
        <div class="score-bar-fill" style="width:${(s.value / s.max) * 100}%; background:${s.color}"></div>
      </div>
      <span class="score-bar-value">${s.value}/${s.max}</span>
    </div>`).join("");

  return `
  <div class="blogger-card ${isTop10 ? 'top10-card' : ''}">
    <div class="blogger-header">
      <div class="blogger-rank">#${rank}</div>
      <div>
        <a href="${escapeHtml(blogUrl)}" target="_blank" rel="noopener" class="blogger-name">${escapeHtml(blogger.name || blogger.id)}</a>
        ${badges.join("")}
      </div>
      <div class="score-badge">${totalScore}점</div>
    </div>

    <div class="card-report">
      <div class="report-line1">상위노출 ${exposedCount}/${totalChecked}개 키워드 | 1~10위 노출: ${top10Count}개</div>
      <div class="report-line2">게시물 ${blogger.post_count || 0}개 | 최근: ${escapeHtml(blogger.last_post_date || "-")}</div>
      ${recentPost ? `<div class="report-line3"><a href="${escapeHtml(recentPost.link)}" target="_blank" rel="noopener" class="post-link">${escapeHtml(recentPost.title)}</a></div>` : ""}
    </div>

    ${exposedKeywords ? `<div class="exposed-keywords">${exposedKeywords}</div>` : ""}

    <div class="score-bars">
      ${scoreBars}
    </div>

    <div class="card-actions">
      <button class="detail-btn" data-id="${escapeHtml(blogger.id)}">상세 보기</button>
    </div>
  </div>`;
}

function getStrengthColor(s) {
  if (s >= 25) return "#10b981";
  if (s >= 15) return "#6366f1";
  if (s >= 8) return "#f59e0b";
  return "#ef4444";
}

function attachCardEvents(container, bloggers) {
  container.querySelectorAll(".detail-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const blogger = bloggers.find((b) => b.id === btn.dataset.id);
      if (blogger) openDetailModal(blogger);
    });
  });
}

// === 상세 모달 ===
function openDetailModal(blogger) {
  const blogUrl = blogger.blog_url || `https://blog.naver.com/${blogger.id}`;
  modalBloggerName.textContent = blogger.name || blogger.id;
  modalBlogLink.textContent = blogUrl;
  modalBlogLink.href = blogUrl;

  const sb = blogger.score_breakdown || {};

  // 노출 상세 정보
  const exposureRows = (blogger.exposure_details || []).map(d =>
    `<div class="modal-score-item"><span>${escapeHtml(d.keyword)}</span><strong>${d.rank > 0 ? d.rank + '위 (+' + d.points + '점)' : '미노출'}</strong></div>`
  ).join("");

  // 최근 게시물 목록
  const postRows = (blogger.recent_posts || []).map(p =>
    `<div class="modal-score-item"><span><a href="${escapeHtml(p.link)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a></span><strong>${escapeHtml(p.date)}</strong></div>`
  ).join("");

  modalScoreDetails.innerHTML = `
    <div class="modal-score-item"><span>총점</span><strong>${blogger.total_score || 0}/100</strong></div>
    <div class="modal-score-item"><span>활동 빈도</span><strong>${sb.activity_frequency || 0}/15</strong></div>
    <div class="modal-score-item"><span>키워드 관련성</span><strong>${sb.keyword_relevance || 0}/15</strong></div>
    <div class="modal-score-item"><span>블로그 지수</span><strong>${sb.blog_index || 0}/15</strong></div>
    <div class="modal-score-item"><span>지역 콘텐츠</span><strong>${sb.local_content || 0}/15</strong></div>
    <div class="modal-score-item"><span>최근 활동</span><strong>${sb.recent_activity || 0}/15</strong></div>
    <div class="modal-score-item"><span>노출 점수</span><strong>${sb.exposure_score || 0}/25</strong></div>
    <hr/>
    ${exposureRows ? `<h4 style="margin:8px 0 4px;color:#a5b4fc;">노출 분석 상세</h4>${exposureRows}<hr/>` : ""}
    ${postRows ? `<h4 style="margin:8px 0 4px;color:#a5b4fc;">최근 게시물</h4>${postRows}` : ""}
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
    createCampaignBtn.classList.add("hidden");
    campaignForm.classList.add("hidden");
    campaignDetail.classList.remove("hidden");
    campaignDetail.dataset.id = campaignId;

    getElement("campaign-detail-name").textContent = campaign.name;
    getElement("campaign-detail-status").textContent = campaign.status;
    getElement("campaign-detail-status").className = `status-badge status-${campaign.status === '진행중' ? 'active' : campaign.status === '완료' ? 'done' : 'paused'}`;
    getElement("campaign-detail-info").textContent = `${campaign.region} / ${campaign.category} | 생성: ${campaign.created_at}`;
    getElement("campaign-detail-memo").textContent = campaign.memo || "";

    // Top10 렌더링
    const top10El = getElement("campaign-top10");
    if (campaign.top10 && campaign.top10.length > 0) {
      top10El.innerHTML = campaign.top10.map((b, i) => renderBloggerCard(b, i + 1, true)).join("");
      attachCardEvents(top10El, campaign.top10);
    } else {
      top10El.innerHTML = '<p class="empty-text">아직 분석 데이터가 없습니다. 대시보드에서 분석을 실행하세요.</p>';
    }

    // Top50 렌더링
    const top50El = getElement("campaign-top50");
    if (campaign.top50 && campaign.top50.length > 0) {
      top50El.innerHTML = campaign.top50.map((b, i) => renderBloggerCard(b, i + 1, false)).join("");
      attachCardEvents(top50El, campaign.top50);
    } else {
      top50El.innerHTML = '<p class="empty-text">운영 풀 데이터가 없습니다.</p>';
    }
  } catch (err) {
    alert("캠페인 상세 정보를 불러올 수 없습니다.");
  }
}

backToCampaigns.addEventListener("click", () => {
  campaignDetail.classList.add("hidden");
  campaignListEl.classList.remove("hidden");
  createCampaignBtn.classList.remove("hidden");
  loadCampaigns();
});

// === 설정 페이지 ===

// 데이터 내보내기
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

// 데이터 초기화
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
