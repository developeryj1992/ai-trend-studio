"use strict";

const state = {
  data: null,
  activeTab: "trends",
  selectedSessionId: null,
  selectedSearchPlatform: "douyin",
  trendQuery: "",
  platformFilter: "all",
  includeUnrelated: false,
  refreshing: false,
};

const platformLabels = {
  douyin: "抖音",
  xiaohongshu: "小红书",
  bilibili: "B站",
  weibo: "微博",
  zhihu: "知乎",
  other: "其他",
};

const eventLabels = {
  speech: "发言",
  caption: "字幕",
  comment: "评论",
  system: "系统",
  insight: "结论",
};

const pageMeta = {
  trends: ["AI 热榜", "公开平台数据，自动过滤 AI 相关内容"],
  videos: ["视频提炼", "导入正文、字幕或评论后生成重点"],
  live: ["直播记录", "单人/多人直播内容实时采集与归纳"],
  settings: ["设置", "过滤规则与模型配置"],
};

function el(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderIcons() {
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
}

let toastTimer = null;
function toast(message, isError = false) {
  const node = el("toast");
  node.textContent = message;
  node.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.className = "toast"; }, 3400);
}

async function api(path, options = {}) {
  const config = {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
  };
  if (options.body !== undefined) config.body = JSON.stringify(options.body);
  const response = await fetch(path, config);
  let payload = null;
  try { payload = await response.json(); } catch (_) { payload = null; }
  if (!response.ok || (payload && payload.error && payload.error !== "not_found")) {
    throw new Error(payload?.error ? `${payload.error}` : `HTTP ${response.status}`);
  }
  return payload;
}

function formatNumber(value) {
  const num = Number(value || 0);
  if (!num) return "-";
  if (num >= 100000000) return `${(num / 100000000).toFixed(1)} 亿`;
  if (num >= 10000) return `${(num / 10000).toFixed(1)} 万`;
  return num.toLocaleString("zh-CN");
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function heatLabel(platform, kind) {
  if (platform === "bilibili" && kind === "video") return "播放";
  return "热度";
}

function setState(next) {
  Object.assign(state, next);
  renderAll();
}

function renderAll() {
  if (!state.data) return;
  renderSourceStatus();
  renderTrends();
  renderImports();
  renderSessions();
  renderSettings();
  renderPageMeta();
  renderIcons();
}

function renderPageMeta() {
  const [title, description] = pageMeta[state.activeTab];
  el("pageTitle").textContent = title;
  const trends = state.data.trends || {};
  const sources = (trends.sources || []).filter(source => source.ok).length;
  el("pageMeta").textContent = state.activeTab === "trends"
    ? `${description} · ${formatTime(trends.updated_at)} · ${sources}/${(trends.sources || []).length} 个源可用`
    : description;
}

function renderSourceStatus() {
  const sources = state.data.trends?.sources || [];
  const automatic = ["douyin", "bilibili", "weibo", "zhihu"];
  let html = automatic.map((id) => {
    const source = sources.find(row => row.id === id);
    const label = platformLabels[id];
    if (!source) {
      return `<div class="source-chip"><span class="source-dot"></span><span><strong>${label}</strong><small>待验证</small></span></div>`;
    }
    const detail = source.ok
      ? `AI 命中 ${source.kept ?? 0} / ${source.count ?? 0}`
      : `${source.error || "抓取失败"}`;
    return `<div class="source-chip ${source.ok ? "ok" : "error"}"><span class="source-dot"></span><span><strong>${label}</strong><small>${escapeHtml(detail)}</small></span></div>`;
  }).join("");
  html += `<div class="source-chip"><span class="source-dot"></span><span><strong>小红书</strong><small>手动导入</small></span></div>`;
  el("sourceStatus").innerHTML = html;
}

function trendMatches(row) {
  if (state.platformFilter !== "all" && row.platform !== state.platformFilter) return false;
  if (!state.trendQuery) return true;
  const haystack = `${row.title} ${row.description || ""} ${row.author || ""} ${(row.matched_keywords || []).join(" ")}`.toLowerCase();
  return haystack.includes(state.trendQuery.toLowerCase());
}

function renderTrends() {
  const rows = (state.data.trends?.items || []).filter(trendMatches);
  const list = el("trendList");
  if (!rows.length) {
    list.innerHTML = `<div class="card empty-message">没有匹配内容，可刷新或调整筛选条件</div>`;
    return;
  }
  list.innerHTML = rows.map((row) => {
    const platform = platformLabels[row.platform] || row.platform;
    const tags = [
      `<span class="tag platform">${platform}</span>`,
      `<span class="tag">${row.kind === "video" ? "视频" : row.kind === "hot_question" ? "问题" : "热词"}</span>`,
      ...(row.matched_keywords || []).slice(0, 4).map(word => `<span class="tag ai">${escapeHtml(word)}</span>`),
    ].join("");
    const title = row.url
      ? `<a href="${escapeHtml(row.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(row.title)}</a>`
      : escapeHtml(row.title);
    const sourceButton = row.kind === "video"
      ? `<button class="btn small import-from-trend" data-id="${row.id}" type="button"><i data-lucide="plus"></i>提炼</button>`
      : `<a class="btn small" href="${escapeHtml(row.url)}" target="_blank" rel="noopener noreferrer"><i data-lucide="external-link"></i>查看</a>`;
    return `<article class="card trend-card">
      <div class="rank">${Number(row.rank || 0)}</div>
      <div class="trend-main">
        <h3 class="trend-title">${title}</h3>
        ${row.description ? `<p class="trend-desc">${escapeHtml(row.description)}</p>` : ""}
        <div class="tags">${tags}</div>
      </div>
      <div class="trend-side">
        <div class="heat">${formatNumber(row.heat)}<small>${heatLabel(row.platform, row.kind)}</small></div>
        ${sourceButton}
      </div>
    </article>`;
  }).join("");
}

function summaryList(summary, field, limit = 5) {
  const values = summary?.[field] || [];
  if (!values.length) return `<ul class="summary-lines empty"></ul>`;
  return `<ul class="summary-lines">${values.slice(0, limit).map(value => `<li>${escapeHtml(value)}</li>`).join("")}</ul>`;
}

function renderImports() {
  const rows = state.data.imports || [];
  const list = el("importList");
  if (!rows.length) {
    list.innerHTML = `<div class="card empty-message">暂无提炼结果</div>`;
    return;
  }
  list.innerHTML = rows.map(row => `<article class="card import-card">
    <h4>${row.url ? `<a href="${escapeHtml(row.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(row.title || "未命名内容")}</a>` : escapeHtml(row.title || "未命名内容")}</h4>
    <div class="meta-row"><span>${platformLabels[row.platform] || row.platform} · ${escapeHtml(row.author || "未知作者")}</span><span>${formatTime(row.created_at)}</span></div>
    ${row.summary ? `<strong>${escapeHtml(row.summary.headline || "")}</strong>${summaryList(row.summary, "key_points")}` : ""}
  </article>`).join("");
}

function renderSessions() {
  const rows = state.data.sessions || [];
  const list = el("sessionList");
  if (!rows.length) {
    list.innerHTML = `<div class="card empty-message">暂无直播会话</div>`;
    el("sessionDetail").innerHTML = `<div class="empty-state"><i data-lucide="radio"></i><p>选择或新建直播会话</p></div>`;
    el("sessionDetail").classList.add("empty");
    return;
  }
  if (!state.selectedSessionId || !rows.some(row => row.id === state.selectedSessionId)) {
    state.selectedSessionId = rows[0].id;
  }
  list.innerHTML = rows.map(row => `<button class="card session-card ${row.id === state.selectedSessionId ? "active" : ""}" data-id="${row.id}" type="button">
    <h4>${escapeHtml(row.title)}</h4>
    <div class="meta-row">
      <span>${platformLabels[row.platform] || row.platform} · ${row.mode === "multi" ? "多人连线" : "单人授课"}</span>
      <span>${row.status === "live" ? "记录中" : formatTime(row.ended_at || row.created_at)}</span>
    </div>
  </button>`).join("");
  renderSessionDetail(rows.find(row => row.id === state.selectedSessionId));
}

function summaryBlocks(summary) {
  if (!summary) return "";
  return `<div class="summary-grid">
    ${summary.headline ? `<div class="summary-block"><h4>核心结论</h4><p class="summary-headline">${escapeHtml(summary.headline)}</p></div>` : ""}
    ${summary.key_points?.length ? `<div class="summary-block"><h4>重点</h4><ul>${summary.key_points.map(value => `<li>${escapeHtml(value)}</li>`).join("")}</ul></div>` : ""}
    ${summary.action_items?.length ? `<div class="summary-block"><h4>可执行项</h4><ul>${summary.action_items.map(value => `<li>${escapeHtml(value)}</li>`).join("")}</ul></div>` : ""}
    ${summary.risks?.length ? `<div class="summary-block"><h4>风险与限制</h4><ul>${summary.risks.map(value => `<li>${escapeHtml(value)}</li>`).join("")}</ul></div>` : ""}
  </div>`;
}

function renderSessionDetail(session) {
  const detail = el("sessionDetail");
  if (!session) {
    detail.innerHTML = `<div class="empty-state"><i data-lucide="radio"></i><p>选择或新建直播会话</p></div>`;
    detail.classList.add("empty");
    return;
  }
  detail.classList.remove("empty");
  const events = session.events || [];
  const speakerOptions = (session.speakers || []).map(speaker => `<option value="${escapeHtml(speaker)}">${escapeHtml(speaker)}</option>`).join("");
  const eventRows = events.length ? events.map(event => `<div class="event-row">
    <span class="event-time">${new Date(event.ts).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</span>
    <span class="event-speaker">${escapeHtml(event.speaker)}</span>
    <span class="event-kind">${eventLabels[event.kind] || event.kind}</span>
    <span class="event-content">${escapeHtml(event.content)}</span>
  </div>`).join("") : `<div class="empty-message">暂无记录</div>`;
  detail.innerHTML = `<article class="card session-detail-card">
    <div class="session-header">
      <div>
        <h3>${session.url ? `<a href="${escapeHtml(session.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(session.title)}</a>` : escapeHtml(session.title)}</h3>
        <div class="tags" style="margin-top:8px">
          <span class="tag platform">${platformLabels[session.platform] || session.platform}</span>
          <span class="tag">${session.mode === "multi" ? "多人连线" : "单人授课"}</span>
          <span class="tag ${session.status === "live" ? "ai" : ""}">${session.status === "live" ? "记录中" : "已完成"}</span>
          <span class="tag">${session.stats?.events || 0} 条</span>
        </div>
      </div>
      ${session.status === "live" ? `<button class="btn danger" id="finishSession" type="button"><i data-lucide="square"></i>完成并归纳</button>` : ""}
    </div>

    ${session.status === "live" ? `<form class="event-form" id="eventForm">
      <input id="eventSpeaker" list="speakerList" value="${escapeHtml(session.speakers?.[0] || "")}" placeholder="发言人" aria-label="发言人">
      <datalist id="speakerList">${speakerOptions}</datalist>
      <select id="eventKind" aria-label="类型">
        <option value="speech">发言</option>
        <option value="caption">字幕</option>
        <option value="comment">评论</option>
        <option value="insight">结论</option>
        <option value="system">系统</option>
      </select>
      <input id="eventContent" placeholder="输入或粘贴当前内容" aria-label="内容">
      <button class="btn primary" type="submit"><i data-lucide="plus"></i>记录</button>
    </form>
    <form id="captionUploadForm" style="display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;margin:-7px 0 14px">
      <input id="captionFile" type="file" accept=".srt,.vtt,.txt">
      <button class="btn" type="submit"><i data-lucide="upload"></i>导入</button>
    </form>` : ""}

    <div class="event-stream" id="eventStream">${eventRows}</div>
    ${session.summary ? `<section class="summary-card card"><h3>直播纪要</h3>${summaryBlocks(session.summary)}</section>` : ""}
  </article>`;
  const stream = el("eventStream");
  if (stream) stream.scrollTop = stream.scrollHeight;
  const finishButton = el("finishSession");
  if (finishButton) finishButton.addEventListener("click", finishSession);
  const eventForm = el("eventForm");
  if (eventForm) eventForm.addEventListener("submit", addEvent);
  const captionForm = el("captionUploadForm");
  if (captionForm) captionForm.addEventListener("submit", uploadCaption);
}

function renderSettings() {
  const settings = state.data.settings || {};
  el("settingsKeywords").value = (settings.keywords || []).join("\n");
  el("llmBaseUrl").value = settings.llm?.base_url || "";
  el("llmModel").value = settings.llm?.model || "";
  el("llmApiKey").value = settings.llm?.api_key || "";
  el("llmTimeout").value = settings.llm?.timeout || 30;
}

async function loadState() {
  const payload = await api("/api/state");
  state.data = payload;
  renderAll();
  return payload;
}

async function refreshTrends(showToast = true) {
  if (state.refreshing) return;
  state.refreshing = true;
  el("refreshButton").disabled = true;
  el("refreshButton").innerHTML = `<i data-lucide="loader-2"></i>刷新中`;
  renderIcons();
  try {
    const payload = await api("/api/refresh", {
      method: "POST",
      body: { include_unrelated: state.includeUnrelated },
    });
    state.data.trends = payload.trends;
    state.data.last_refresh = payload.trends.updated_at;
    if (showToast) {
      const failed = payload.trends.sources.filter(source => !source.ok).map(source => source.label);
      toast(failed.length ? `已刷新，${failed.join("、")}抓取失败` : `已刷新 ${payload.trends.items.length} 条 AI 内容`);
    }
  } catch (error) {
    if (showToast) toast(`刷新失败：${error.message}`, true);
  } finally {
    state.refreshing = false;
    el("refreshButton").disabled = false;
    el("refreshButton").innerHTML = `<i data-lucide="refresh-cw"></i>刷新热榜`;
    renderAll();
  }
}

async function saveImport(event) {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  button.innerHTML = `<i data-lucide="loader-2"></i>提炼中`;
  renderIcons();
  try {
    const payload = await api("/api/imports", {
      method: "POST",
      body: {
        platform: el("importPlatform").value,
        kind: el("importKind").value,
        title: el("importTitle").value,
        url: el("importUrl").value,
        author: el("importAuthor").value,
        raw_text: el("importText").value,
      },
    });
    state.data.imports.unshift(payload.import);
    el("importText").value = "";
    el("subtitleFile").value = "";
    toast("内容已提炼");
    renderAll();
  } catch (error) {
    toast(`提炼失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    button.innerHTML = `<i data-lucide="sparkles"></i>提炼并保存`;
    renderIcons();
  }
}

async function createSession(event) {
  event.preventDefault();
  const payload = await api("/api/live/sessions", {
    method: "POST",
    body: {
      title: el("liveTitle").value,
      platform: el("livePlatform").value,
      url: el("liveUrl").value,
      mode: el("liveMode").value,
      speakers: el("liveSpeakers").value.split(/\r?\n/).map(value => value.trim()).filter(Boolean),
    },
  });
  state.data.sessions.unshift(payload.session);
  state.selectedSessionId = payload.session.id;
  el("liveTitle").value = "";
  el("liveUrl").value = "";
  el("liveSpeakers").value = "";
  toast("直播记录已开始");
  renderAll();
}

async function addEvent(event) {
  event.preventDefault();
  const content = el("eventContent").value.trim();
  if (!content) return;
  try {
    const payload = await api(`/api/live/sessions/${state.selectedSessionId}/events`, {
      method: "POST",
      body: {
        speaker: el("eventSpeaker").value.trim(),
        kind: el("eventKind").value,
        content,
      },
    });
    const index = state.data.sessions.findIndex(row => row.id === state.selectedSessionId);
    state.data.sessions[index] = payload.session;
    el("eventContent").value = "";
    renderAll();
  } catch (error) {
    toast(`记录失败：${error.message}`, true);
  }
}

async function uploadCaption(event) {
  event.preventDefault();
  const file = el("captionFile").files?.[0];
  if (!file) return;
  const text = (await file.text()).trim();
  if (!text) return;
  try {
    const payload = await api(`/api/live/sessions/${state.selectedSessionId}/events`, {
      method: "POST",
      body: {
        speaker: el("eventSpeaker").value.trim() || "字幕",
        kind: "caption",
        content: text,
      },
    });
    const index = state.data.sessions.findIndex(row => row.id === state.selectedSessionId);
    state.data.sessions[index] = payload.session;
    el("captionFile").value = "";
    toast("字幕或文稿已导入");
    renderAll();
  } catch (error) {
    toast(`导入失败：${error.message}`, true);
  }
}

async function finishSession() {
  try {
    const payload = await api(`/api/live/sessions/${state.selectedSessionId}/finish`, { method: "POST", body: {} });
    const index = state.data.sessions.findIndex(row => row.id === state.selectedSessionId);
    state.data.sessions[index] = payload.session;
    toast("直播纪要已生成");
    renderAll();
  } catch (error) {
    toast(`生成失败：${error.message}`, true);
  }
}

async function saveSettings(event) {
  event.preventDefault();
  try {
    const payload = await api("/api/settings", {
      method: "POST",
      body: {
        settings: {
          keywords: el("settingsKeywords").value.split(/\r?\n/).map(value => value.trim()).filter(Boolean),
          llm: {
            base_url: el("llmBaseUrl").value,
            model: el("llmModel").value,
            api_key: el("llmApiKey").value,
            timeout: Number(el("llmTimeout").value || 30),
          },
        },
      },
    });
    state.data = payload.state;
    toast("设置已保存");
    renderAll();
  } catch (error) {
    toast(`保存失败：${error.message}`, true);
  }
}

const searchUrls = {
  douyin: keyword => `https://www.douyin.com/search/${encodeURIComponent(keyword)}?publish_time=0&sort_type=0&source=normal`,
  xiaohongshu: keyword => `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(keyword)}`,
  bilibili: keyword => `https://search.bilibili.com/all?keyword=${encodeURIComponent(keyword)}&order=click`,
};

function switchTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".nav-item").forEach(button => button.classList.toggle("active", button.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.toggle("active", panel.id === tab));
  renderPageMeta();
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach(button => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  el("refreshButton").addEventListener("click", () => refreshTrends());
  el("trendSearch").addEventListener("input", event => setState({ trendQuery: event.target.value.trim() }));
  el("platformFilter").addEventListener("change", event => setState({ platformFilter: event.target.value }));
  el("includeUnrelated").addEventListener("change", async event => {
    setState({ includeUnrelated: event.target.checked });
    await refreshTrends();
  });
  el("importForm").addEventListener("submit", saveImport);
  el("subtitleFile").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    el("importText").value = await file.text();
    toast("文件内容已载入");
  });
  el("liveForm").addEventListener("submit", createSession);
  el("settingsForm").addEventListener("submit", saveSettings);
  el("sessionList").addEventListener("click", event => {
    const button = event.target.closest(".session-card");
    if (!button) return;
    setState({ selectedSessionId: button.dataset.id });
  });
  el("trendList").addEventListener("click", event => {
    const button = event.target.closest(".import-from-trend");
    if (!button) return;
    const row = state.data.trends.items.find(item => item.id === button.dataset.id);
    if (!row) return;
    el("importPlatform").value = row.platform;
    el("importKind").value = "video";
    el("importTitle").value = row.title;
    el("importUrl").value = row.url || "";
    el("importAuthor").value = row.author || "";
    el("importText").value = `${row.description || ""}\n来源：${row.url || ""}\n热度：${row.heat || ""}`;
    switchTab("videos");
    toast("已带入视频信息，请补充口播或字幕");
  });
  document.querySelectorAll(".search-links button").forEach(button => {
    button.addEventListener("click", () => {
      state.selectedSearchPlatform = button.dataset.search;
      document.querySelectorAll(".search-links button").forEach(node => node.classList.toggle("active", node === button));
    });
  });
  el("openSearch").addEventListener("click", () => {
    const keyword = el("searchKeyword").value.trim() || "AI";
    window.open(searchUrls[state.selectedSearchPlatform](keyword), "_blank", "noopener,noreferrer");
  });
}

async function init() {
  bindEvents();
  document.querySelector(".search-links button")?.classList.add("active");
  renderIcons();
  try {
    const data = await loadState();
    if (!data.trends?.items?.length && !data.trends?.sources?.length) {
      await refreshTrends(false);
    }
  } catch (error) {
    toast(`加载失败：${error.message}`, true);
  }
  setInterval(() => refreshTrends(false), 10 * 60 * 1000);
}

init();
