const state = {
  view: "review",
  items: [],
  selected: null,
  settings: null,
  publishQueue: [],
  lastResult: null,
  workDate: todayKey(),
  sourceFilter: "all",
  syncPhase: "",
  syncError: "",
};
let syncTimer = 0;

const $ = (sel) => document.querySelector(sel);
function h(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}
const api = (path, body) => fetch(path, {
  method: body ? "POST" : "GET",
  headers: body ? { "Content-Type": "application/json" } : {},
  body: body ? JSON.stringify(body) : undefined,
}).then((r) => r.ok ? r.json() : Promise.reject(r));

function dateKey(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}
function todayKey() { return dateKey(0); }
function yesterdayKey() { return dateKey(-1); }

function mediaUrl(ref) {
  if (!ref) return "";
  if (typeof ref === "string") return ref;
  return ref.thumbnail_ref || ref.original_image_ref || "";
}

function selectedMedia(item) {
  return item.selected_media_url || mediaUrl(item.media_urls?.[0]);
}

function sourceKind(item) {
  return item.source.includes("xueqiu") ? "xueqiu" : item.source.includes("reddit") ? "reddit" : item.source;
}

function sourceLabel(value) {
  return value.includes("xueqiu") ? "雪球" : value.includes("reddit") ? "Reddit" : value;
}

function visibleItems() {
  return state.sourceFilter === "all" ? state.items : state.items.filter((item) => sourceKind(item) === state.sourceFilter);
}

function counts(items = visibleItems()) {
  return {
    all: items.length,
    draft: items.filter((x) => x.review_status === "draft").length,
    approved: items.filter((x) => x.review_status === "approved").length,
    rejected: items.filter((x) => x.review_status === "rejected").length,
    scheduled: items.filter((x) => x.schedule_status === "scheduled").length,
    confirmed: items.filter((x) => x.publish_status === "confirmed").length,
  };
}

function canMove(item) {
  return item.review_status === "approved" && ["none", "failed"].includes(item.publish_status || "none");
}

function syncBusy() {
  return ["fetch", "write"].includes(state.syncPhase);
}

async function load() {
  const itemPath = `/api/items?work_date=${encodeURIComponent(state.workDate)}`;
  const [items, settings, queue] = await Promise.all([api(itemPath), api("/api/settings/status"), api("/api/publish/queue")]);
  if (state.workDate === todayKey() && !items.items.length) {
    const all = await api("/api/items?work_date=");
    state.workDate = "";
    state.items = all.items;
  } else {
    state.items = items.items;
  }
  state.settings = settings;
  state.publishQueue = queue.tasks;
}

function shell(content, side = "") {
  const topNav = ["review:内容审核", "schedule:发布排期", "sync:同步中心"].map((item) => {
    const [view, label] = item.split(":");
    return `<button class="${state.view === view ? "active" : ""}" onclick="go('${view}')">${label}</button>`;
  }).join("");
  const nav = ["review:审核工作台", "schedule:发布排期", "sync:同步中心"].map((item) => {
    const [view, label] = item.split(":");
    return `<button class="${state.view === view ? "active" : ""}" onclick="go('${view}')"><span>${label}</span></button>`;
  }).join("");
  return `
    <aside class="nav"><div class="brand"><div class="mark">CF</div><strong>Copy Factory</strong></div>${nav}<div class="nav-card"><strong>数据同步正常</strong><p>每 30 分钟自动同步</p><button onclick="manualSync()" ${syncBusy() ? "disabled" : ""}>${syncBusy() ? "同步中" : "立即同步"}</button></div></aside>
    <main class="workspace"><header class="appbar"><nav>${topNav}</nav><div class="search">搜索内容、来源或标签...</div><div class="user-dot">J</div></header><div class="main ${side ? "" : "no-rail"}"><section class="stage">${content}</section><aside class="rail">${side}</aside></div></main>
    <nav class="tabbar">${nav}</nav>
  `;
}

function statBar() {
  const c = counts();
  const dayLabel = state.workDate || "全部";
  return `<div class="date-tabs">
    <button class="${state.workDate === todayKey() ? "active" : ""}" onclick="setWorkDate('${todayKey()}')">今日</button>
    <button class="${state.workDate === yesterdayKey() ? "active" : ""}" onclick="setWorkDate('${yesterdayKey()}')">昨日</button>
    <button class="${state.workDate === "" ? "active" : ""}" onclick="setWorkDate('')">全部</button>
    <input type="date" value="${h(state.workDate)}" onchange="setWorkDate(this.value)">
    <span class="muted">当前：${h(dayLabel)}</span>
  </div><div class="source-tabs">
    ${["all:全部来源", "xueqiu:雪球", "reddit:Reddit"].map((item) => {
      const [value, label] = item.split(":");
      return `<button class="${state.sourceFilter === value ? "active" : ""}" onclick="setSourceFilter('${value}')">${label}</button>`;
    }).join("")}
  </div><div class="stats">
    <span class="chip">全部 <strong>${c.all}</strong></span>
    <span class="chip">待审 <strong>${c.draft}</strong></span>
    <span class="chip">通过 <strong>${c.approved}</strong></span>
    <span class="chip">排期 <strong>${c.scheduled}</strong></span>
    <span class="chip">拒绝 <strong>${c.rejected}</strong></span>
  </div>`;
}

function mediaGrid(item) {
  if (!item.media_urls.length) return `<div class="media-grid"><div class="media-tile"><span>无图片</span></div></div>`;
  return `<div class="media-grid">${item.media_urls.slice(0, 4).map((ref, i) => {
    const url = mediaUrl(ref);
    return `<a class="media-tile" href="${h(url)}" target="_blank"><img src="${h(url)}" alt="图片 ${i + 1}"><span>图片 ${i + 1}</span></a>`;
  }).join("")}</div>`;
}

function itemCard(item, compact = false, context = "") {
  const copy = (item.edited_copy || item.generated_copy || item.text || "").slice(0, compact ? 90 : 280);
  const scheduled = item.scheduled_at ? formatSlot(item.scheduled_at) : "";
  const label = sourceLabel(sourceKind(item));
  const observed = item.observed_at ? `抓取 ${item.observed_at.slice(0, 16).replace("T", " ")}` : "";
  const published = item.published_at ? `原文 ${item.published_at.slice(0, 16).replace("T", " ")}` : "";
  const timeLine = [observed, published].filter(Boolean).join(" · ");
  return `<article class="${compact ? "mini-card" : "feed-item"}" draggable="${canMove(item)}" ondragstart="dragItem(event, ${item.id})">
    ${compact ? "" : `<div class="avatar ${sourceKind(item)}">${h(label[0]?.toUpperCase() || "C")}</div>`}
    <div class="item-body">
      <div class="item-head">
        <span class="source-line">${h(label)} ${timeLine ? "· " + h(timeLine) : ""}</span>
        <span class="item-title">${h(item.title || "Untitled")}</span>
        <span class="pill ${item.review_status}">${item.review_status}</span>
        <span class="pill">${item.generation_status}</span>
        ${item.schedule_status === "scheduled" ? `<span class="pill approved">${h(scheduled)}</span>` : ""}
        ${item.publish_status && item.publish_status !== "none" ? `<span class="pill publish">${h(item.publish_status)}</span>` : ""}
      </div>
      ${selectedMedia(item) ? `<img class="selected-media ${compact ? "compact" : ""}" src="${h(selectedMedia(item))}" alt="选中配图">` : ""}
      <p class="copy">${h(copy)}</p>
      ${compact ? "" : mediaGrid(item)}
      ${compact && context === "pool" ? `<div class="actions"><button onclick="quickSchedule(${item.id})">排到下一槽</button></div>` : compact ? "" : `<div class="actions">
        <button class="primary" onclick="openItem(${item.id})">编辑文案</button>
        <button onclick="quickReview(${item.id}, 'approved')">批准</button>
        <button onclick="quickReview(${item.id}, 'rejected')" class="danger">拒绝</button>
        <span class="muted">图片引用 ${item.media_urls.length}</span>
      </div>`}
    </div>
  </article>`;
}

function reviewView() {
  const c = counts();
  const side = `<div class="panel"><h2>队列概览</h2><div class="queue-total"><strong>${c.all}</strong><span>全部内容</span></div>${Object.entries(c).filter(([k]) => k !== "all").map(([k,v]) => `<div class="kv"><span>${k}</span><strong>${v}</strong></div>`).join("")}</div>
    <div class="panel soft"><h2>同步健康</h2><div class="kv"><span>状态</span><strong class="ok">正常</strong></div><p class="muted">最新 feed 按 generated_at 判断，只处理新增快照。</p></div>
    <div class="panel"><h2>快捷操作</h2><button class="rail-action" onclick="go('sync')">刷新列表</button><button class="rail-action" onclick="go('schedule')">打开排期</button></div>`;
  const items = visibleItems().map((item) => itemCard(item)).join("") || `<p class="panel">暂无文案。换个日期或来源看看。</p>`;
  return shell(`<div class="topbar"><p class="eyebrow">Copy Factory</p><h1>内容审核工作台</h1><p class="muted">每天同步进来的内容按日期分开；昨天没选上的会保留在昨天或全部里。</p>${statBar()}</div><div class="feed-list">${items}</div>`, side);
}

function editorView() {
  const item = state.selected || state.items[0];
  if (!item) return reviewView();
  const mediaChoices = item.media_urls.length ? `<div class="media-choice">${item.media_urls.map((ref, i) => {
    const url = mediaUrl(ref);
    const checked = selectedMedia(item) === url ? "checked" : "";
    return `<label><input type="radio" name="selected-media" value="${h(url)}" ${checked}><img src="${h(url)}" alt="候选配图 ${i + 1}"><span>图片 ${i + 1}</span></label>`;
  }).join("")}</div>` : `<p class="muted">这条来源没有图片。</p>`;
  return shell(`<div class="topbar editor-title"><button class="small-btn" onclick="go('review')">返回列表</button><h1>编辑文案</h1><span class="pill ${item.review_status}">${item.review_status}</span></div>
    <div class="editor">
      <section class="source-pane"><h1>${h(item.title)}</h1><p class="muted">${h(item.source)} · 抓取 ${h(item.observed_at || "")} · 原文 ${h(item.published_at)} · <a href="${h(item.url)}" target="_blank">原文链接</a></p><h2>原文</h2><pre>${h(item.text)}</pre><h2>图片引用</h2>${mediaGrid(item)}</section>
      <section class="edit-pane"><h2>生成文案</h2><textarea id="copy">${h(item.edited_copy || item.generated_copy)}</textarea><h2>选择配图</h2>${mediaChoices}<div class="form-grid"><button class="wide-btn" onclick="saveReview(${item.id}, 'draft')">保存草稿</button><button class="wide-btn" onclick="saveReview(${item.id}, 'approved')">批准</button><button class="small-btn danger" onclick="saveReview(${item.id}, 'rejected')">拒绝</button><button class="small-btn" onclick="go('schedule')">去排期</button></div><p class="muted">生成状态：${h(item.generation_status)} ${h(item.generation_error || "")}</p></section>
      <section class="preview-pane"><h2>预览</h2><div class="post-preview"><div class="preview-avatar">CF</div><strong>Copy Factory</strong><p>${h(item.edited_copy || item.generated_copy)}</p>${selectedMedia(item) ? `<img src="${h(selectedMedia(item))}" alt="预览配图">` : ""}</div><label>发布时间<input value="${h(formatSlot(item.scheduled_at || nextSlots()[0]))}" disabled></label></section>
    </div>`);
}

function syncView() {
  const r = state.lastResult;
  const runs = state.settings?.runs || [];
  const last = runs[0];
  return shell(`<div class="topbar"><h1>同步中心</h1><p class="muted">自动同步每 30 分钟跑一次；需要马上拉新内容时点立即同步。</p></div>
    <div class="sync-grid">
      <section class="panel span-6"><h2>当前状态</h2>${syncStatusBlock()}<div class="kv"><span>频率</span><strong>每 30 分钟</strong></div><div class="kv"><span>来源</span><strong>${(state.settings?.sources || []).map(sourceLabel).join(" / ")}</strong></div><button class="wide-btn" onclick="manualSync()" ${syncBusy() ? "disabled" : ""}>${syncBusy() ? "同步中" : "立即同步"}</button></section>
      <section class="panel span-6"><h2>${r ? "本轮结果" : "最近同步"}</h2>${r ? resultBlock(r) : last ? runBlock(last) : `<p class="muted">还没有同步记录。</p>`}</section>
    </div>`);
}

function syncStatusBlock() {
  const sources = (state.settings?.sources || []).map(sourceLabel).join(" / ") || "内容源";
  const text = {
    fetch: ["拉取中", `正在从 ${sources} 拉取新内容`],
    write: ["改写中", "正在生成审核工作台里的文案"],
    done: ["已完成", "审核工作台已刷新"],
    error: ["失败", state.syncError || "同步失败，请稍后重试"],
  }[state.syncPhase] || ["正常", "自动同步中"];
  return `<div class="sync-status ${state.syncPhase || "idle"}"><strong>${text[0]}</strong><span>${h(text[1])}</span></div>${syncFlow()}`;
}

function syncFlow() {
  const steps = ["拉取", "改写", "入池"];
  const index = { fetch: 0, write: 1, done: 3, error: -1 }[state.syncPhase] ?? -1;
  return `<div class="sync-flow ${state.syncPhase || "idle"} ${syncBusy() ? "running" : ""}"><div class="sync-bar"><span></span></div>${steps.map((step, i) => `<span class="${i < index ? "done" : i === index ? "active" : ""}">${step}</span>`).join("")}</div>`;
}

function resultBlock(r) {
  return `<div class="stats">${["fetched","inserted","duplicates","filtered","generated"].map((k) => `<span class="chip">${k} <strong>${r[k]}</strong></span>`).join("")}<span class="chip">skipped <strong>${r.skipped}</strong></span></div>${r.errors?.length ? `<pre>${r.errors.join("\\n")}</pre>` : ""}`;
}

function runBlock(run) {
  return `<div class="run-row"><strong>${run.kind}</strong> ${run.created_at}<br><span class="muted">拉取 ${run.fetched}，新增 ${run.inserted}，生成 ${run.generated}${run.skipped ? "，没有新快照" : ""}</span></div>`;
}

function scheduleView() {
  const approved = visibleItems().filter((x) => x.review_status === "approved" && x.schedule_status !== "scheduled");
  const slots = scheduleSlots();
  return shell(`<div class="topbar schedule-top"><div><p class="eyebrow">Publish desk</p><h1>发布排期</h1><p class="muted">按小时排布未来 48 小时的内容，把通过的文案拖到合适时间。</p>${statBar()}</div></div>
    <div class="timeline schedule-planner"><aside class="approved-pool"><div class="pool-head"><h2>待排内容</h2><span>${approved.length}</span></div>${approved.map((x) => itemCard(x, true, "pool")).join("") || `<p class="empty-note">没有未排期 approved 文案。</p>`}</aside><section class="schedule-board"><div class="confirm-bar"><div><strong>${scheduledReady()} 条可确认</strong><p class="muted">队列 ${state.publishQueue.length} 条，已确认 ${state.publishQueue.filter((x) => x.status === "confirmed").length} 条。</p></div><button class="primary" onclick="confirmPublishPlan()">确认发布计划</button></div><div class="slot-grid">${slotGroups(slots).map(dayView).join("")}</div></section></div>`);
}

function scheduledReady() {
  return state.items.filter((x) => x.review_status === "approved" && x.schedule_status === "scheduled" && ["none", "failed"].includes(x.publish_status)).length;
}

function slotView(slot) {
  const items = visibleItems().filter((x) => x.scheduled_at === slot);
  const parts = formatSlotParts(slot);
  return `<div class="slot" ondragover="allowDrop(event)" ondragleave="event.currentTarget.classList.remove('dragover')" ondrop="dropItem(event, '${slot}')"><time>${parts.time}</time><div class="slot-drop">${items.map((x) => itemCard(x, true) + (canMove(x) ? `<button class="small-btn unschedule-btn" onclick="unschedule(${x.id})">移出</button>` : "")).join("") || `<span>空档</span>`}</div></div>`;
}

function slotGroups(slots) {
  const groups = [];
  for (const slot of slots) {
    const day = formatSlotParts(slot).day;
    const last = groups[groups.length - 1];
    if (last?.day === day) last.slots.push(slot);
    else groups.push({ day, slots: [slot] });
  }
  return groups;
}

function dayView(group) {
  return `<section class="day-column"><header>${h(group.day)}<span>${group.slots.length} 档</span></header>${group.slots.map(slotView).join("")}</section>`;
}

function settingsView() {
  return shell(`<div class="topbar"><h1>部署与设置</h1><p class="muted">一屏看清楚本地工作台能不能上公网。</p></div><div class="sync-grid">
    <section class="panel span-6"><h2>运行状态</h2><div class="kv"><span>SQLite</span><strong>${state.settings?.db_path}</strong></div><div class="kv"><span>来源</span><strong>${(state.settings?.sources || []).join(",")}</strong></div><div class="kv"><span>Export token</span><strong>${state.settings?.has_export_token ? "ok" : "missing"}</strong></div><div class="kv"><span>DeepSeek</span><strong>${state.settings?.has_deepseek_key ? "ok" : "fake/local"}</strong></div></section>
    <section class="panel span-6"><h2>部署命令</h2><pre>python3 -m app.web --host 0.0.0.0 --port 8000\n*/30 * * * * python3 scripts/sync_once.py</pre></section>
  </div>`);
}

function nextSlots() {
  const base = new Date();
  if (base.getMinutes() || base.getSeconds() || base.getMilliseconds()) base.setHours(base.getHours() + 1);
  base.setMinutes(0, 0, 0);
  const slots = [];
  for (let i = 0; i < 48; i++) {
    const date = new Date(base);
    date.setHours(base.getHours() + i);
    slots.push(date.toISOString());
  }
  return slots;
}

function scheduleSlots() {
  return [...new Set([
    ...visibleItems().filter((x) => x.scheduled_at).map((x) => x.scheduled_at),
    ...nextSlots(),
  ])].sort((a, b) => new Date(a) - new Date(b));
}

function formatSlotParts(value) {
  const date = new Date(value);
  return {
    day: date.toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "short" }),
    time: date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }),
  };
}

function formatSlot(value) {
  const p = formatSlotParts(value);
  return `${p.day} ${p.time}`;
}

async function refresh() { await load(); render(); }
function render() {
  const views = { review: reviewView, editor: editorView, sync: syncView, schedule: scheduleView, settings: settingsView };
  $("#app").innerHTML = views[state.view]();
}
async function go(view) { state.view = view; await refresh(); }
async function setWorkDate(value) { state.workDate = value; await refresh(); }
async function setSourceFilter(value) { state.sourceFilter = value; render(); }
function openItem(id) { state.selected = state.items.find((x) => x.id === id); state.view = "editor"; render(); }
async function saveReview(id, status) {
  const text = $("#copy")?.value ?? state.items.find((x) => x.id === id)?.edited_copy ?? "";
  const selected = document.querySelector("input[name='selected-media']:checked")?.value ?? state.items.find((x) => x.id === id)?.selected_media_url ?? "";
  await api(`/api/items/${id}/review`, { edited_copy: text, status, selected_media_url: selected });
  await go("review");
}
async function quickReview(id, status) {
  const item = state.items.find((x) => x.id === id);
  await api(`/api/items/${id}/review`, { edited_copy: item.edited_copy || item.generated_copy, status, selected_media_url: selectedMedia(item) });
  await refresh();
}
function syncPayload() { return { limit: Number($("#limit")?.value || state.settings?.export_limit || 10), since: $("#since")?.value || "", until: $("#until")?.value || "" }; }
async function previewSync() { state.lastResult = (await api("/api/sync/preview", syncPayload())).result; await refresh(); state.view = "sync"; render(); }
async function runSync() {
  if (syncBusy()) return;
  state.view = "sync";
  state.syncPhase = "fetch";
  state.syncError = "";
  state.lastResult = null;
  render();
  clearTimeout(syncTimer);
  syncTimer = setTimeout(() => {
    if (state.syncPhase === "fetch") {
      state.syncPhase = "write";
      render();
    }
  }, 1200);
  try {
    state.lastResult = (await api("/api/sync/run", syncPayload())).result;
    clearTimeout(syncTimer);
    state.syncPhase = "done";
    await load();
    state.view = "sync";
    render();
  } catch (err) {
    clearTimeout(syncTimer);
    state.syncPhase = "error";
    state.syncError = err?.status ? `请求失败 ${err.status}` : String(err);
    render();
  }
}
async function manualSync() { state.view = "sync"; await runSync(); }
function dragItem(event, id) { event.dataTransfer.setData("text/plain", String(id)); }
function allowDrop(event) { event.preventDefault(); event.currentTarget.classList.add("dragover"); }
async function dropItem(event, scheduled_at) {
  event.preventDefault();
  event.currentTarget.classList.remove("dragover");
  await api(`/api/items/${event.dataTransfer.getData("text/plain")}/schedule`, { scheduled_at });
  await refresh();
}
async function unschedule(id) { await api(`/api/items/${id}/unschedule`, {}); await refresh(); }
async function quickSchedule(id) { await api(`/api/items/${id}/schedule`, { scheduled_at: nextSlots()[0] }); await refresh(); }
async function confirmPublishPlan() {
  const result = await api("/api/publish/confirm_plan", {});
  state.publishQueue = result.tasks;
  await refresh();
  state.view = "schedule";
  render();
}

refresh().catch((err) => { $("#app").innerHTML = `<main class="panel"><h1>加载失败</h1><pre>${err}</pre></main>`; });
