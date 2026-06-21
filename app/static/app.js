const state = { view: "review", items: [], selected: null, settings: null, lastResult: null };

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

function mediaUrl(ref) {
  if (!ref) return "";
  if (typeof ref === "string") return ref;
  return ref.thumbnail_ref || ref.original_image_ref || "";
}

function counts() {
  return {
    all: state.items.length,
    draft: state.items.filter((x) => x.review_status === "draft").length,
    approved: state.items.filter((x) => x.review_status === "approved").length,
    rejected: state.items.filter((x) => x.review_status === "rejected").length,
    scheduled: state.items.filter((x) => x.schedule_status === "scheduled").length,
  };
}

async function load() {
  const [items, settings] = await Promise.all([api("/api/items"), api("/api/settings/status")]);
  state.items = items.items;
  state.settings = settings;
}

function shell(content, side = "") {
  const nav = ["review:审核", "sync:同步", "schedule:排期", "settings:设置"].map((item) => {
    const [view, label] = item.split(":");
    return `<button class="${state.view === view ? "active" : ""}" onclick="go('${view}')">${label}</button>`;
  }).join("");
  return `
    <aside class="nav"><div class="mark">CF</div>${nav}<button class="run" onclick="go('sync')">运行批次</button></aside>
    <main class="main ${side ? "" : "no-rail"}"><section class="stage">${content}</section><aside class="rail">${side}</aside></main>
    <nav class="tabbar">${nav}</nav>
  `;
}

function statBar() {
  const c = counts();
  return `<div class="stats">
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

function itemCard(item, compact = false) {
  const copy = (item.edited_copy || item.generated_copy || item.text || "").slice(0, compact ? 90 : 280);
  const scheduled = item.scheduled_at ? formatSlot(item.scheduled_at) : "";
  return `<article class="${compact ? "mini-card" : "feed-item"}" draggable="${item.review_status === "approved"}" ondragstart="dragItem(event, ${item.id})">
    ${compact ? "" : `<div class="avatar">${h(item.source[0]?.toUpperCase() || "C")}</div>`}
    <div>
      <div class="item-head">
        <span class="item-title">${h(item.title || "Untitled")}</span>
        <span class="muted">· ${h(item.source)}</span>
        <span class="pill ${item.review_status}">${item.review_status}</span>
        <span class="pill">${item.generation_status}</span>
        ${item.schedule_status === "scheduled" ? `<span class="pill approved">${h(scheduled)}</span>` : ""}
      </div>
      <p class="copy">${h(copy)}</p>
      ${compact ? "" : mediaGrid(item)}
      <div class="actions">
        <button class="primary" onclick="openItem(${item.id})">编辑文案</button>
        <button onclick="quickReview(${item.id}, 'approved')">批准</button>
        <button onclick="quickReview(${item.id}, 'rejected')" class="danger">拒绝</button>
        <span class="muted">图片引用 ${item.media_urls.length}</span>
      </div>
    </div>
  </article>`;
}

function reviewView() {
  const side = `<div class="panel"><h2>队列概览</h2>${Object.entries(counts()).map(([k,v]) => `<div class="kv"><span>${k}</span><strong>${v}</strong></div>`).join("")}</div>
    <div class="panel soft"><h2>运行规则</h2><p class="muted">先看 health.generated_at，变了才拉 export。入库按 source_id / url / hash 去重。</p></div>`;
  const items = state.items.map((item) => itemCard(item)).join("") || `<p class="panel">暂无文案。去同步页运行一个批次。</p>`;
  return shell(`<div class="topbar"><h1>内容审核工作台</h1><p class="muted">最新快照进来后，只处理新增。审核通过后可以拖到排期时间线。</p>${statBar()}</div>${items}`, side);
}

function editorView() {
  const item = state.selected || state.items[0];
  if (!item) return reviewView();
  return shell(`<div class="topbar"><button class="small-btn" onclick="go('review')">返回审核池</button></div>
    <div class="editor">
      <section class="source-pane"><h1>${h(item.title)}</h1><p class="muted">${h(item.source)} · ${h(item.published_at)} · <a href="${h(item.url)}" target="_blank">原文链接</a></p><h2>原文</h2><pre>${h(item.text)}</pre><h2>图片引用</h2>${mediaGrid(item)}</section>
      <section class="edit-pane"><h2>生成文案</h2><textarea id="copy">${h(item.edited_copy || item.generated_copy)}</textarea><div class="form-grid"><button class="wide-btn" onclick="saveReview(${item.id}, 'draft')">保存草稿</button><button class="wide-btn" onclick="saveReview(${item.id}, 'approved')">批准</button><button class="small-btn danger" onclick="saveReview(${item.id}, 'rejected')">拒绝</button><button class="small-btn" onclick="go('schedule')">去排期</button></div><p class="muted">生成状态：${h(item.generation_status)} ${h(item.generation_error || "")}</p></section>
    </div>`);
}

function syncView() {
  const r = state.lastResult;
  const runs = state.settings?.runs || [];
  return shell(`<div class="topbar"><h1>同步控制台</h1><p class="muted">先预览这一轮会处理多少条，再决定是否生成。</p></div>
    <div class="sync-grid">
      <section class="panel span-8"><h2>批次参数</h2><div class="form-grid"><label>limit<input id="limit" type="number" value="${state.settings?.export_limit || 10}"></label><label>since<input id="since" type="date"></label><label>until<input id="until" type="date"></label><label>sources<input value="${(state.settings?.sources || []).join(",")}" disabled></label></div><div class="actions"><button class="primary" onclick="previewSync()">预览本轮</button><button onclick="runSync()">运行生成</button></div></section>
      <section class="panel span-4"><h2>密钥状态</h2><div class="kv"><span>export token</span><strong>${state.settings?.has_export_token ? "ok" : "missing"}</strong></div><div class="kv"><span>DeepSeek</span><strong>${state.settings?.has_deepseek_key ? "ok" : "fake/local"}</strong></div></section>
      <section class="panel span-6"><h2>本轮结果</h2>${r ? resultBlock(r) : `<p class="muted">还没有运行。先点预览。</p>`}</section>
      <section class="panel span-6"><h2>运行记录</h2>${runs.map((run) => `<div class="run-row"><strong>${run.kind}</strong> ${run.created_at}<br><span class="muted">fetched ${run.fetched}, inserted ${run.inserted}, generated ${run.generated}, skipped ${run.skipped}</span></div>`).join("")}</section>
    </div>`);
}

function resultBlock(r) {
  return `<div class="stats">${["fetched","inserted","duplicates","filtered","generated"].map((k) => `<span class="chip">${k} <strong>${r[k]}</strong></span>`).join("")}<span class="chip">skipped <strong>${r.skipped}</strong></span></div>${r.errors?.length ? `<pre>${r.errors.join("\\n")}</pre>` : ""}`;
}

function scheduleView() {
  const approved = state.items.filter((x) => x.review_status === "approved" && x.schedule_status !== "scheduled");
  const slots = nextSlots();
  return shell(`<div class="topbar"><h1>拖拽排期时间线</h1><p class="muted">把 approved 文案拖到时间槽。这里只保存排期，不自动发布。</p>${statBar()}</div>
    <div class="timeline"><aside class="approved-pool"><h2>可排期</h2>${approved.map((x) => itemCard(x, true)).join("") || `<p class="muted">没有未排期 approved 文案。</p>`}</aside><section class="slot-grid">${slots.map(slotView).join("")}</section></div>`);
}

function slotView(slot) {
  const items = state.items.filter((x) => x.scheduled_at === slot);
  const parts = formatSlotParts(slot);
  return `<div class="slot" ondragover="allowDrop(event)" ondragleave="event.currentTarget.classList.remove('dragover')" ondrop="dropItem(event, '${slot}')"><time>${parts.time}</time><em>${parts.day}</em>${items.map((x) => itemCard(x, true) + `<button class="small-btn" onclick="unschedule(${x.id})">移出排期</button>`).join("")}</div>`;
}

function settingsView() {
  return shell(`<div class="topbar"><h1>部署与设置</h1><p class="muted">一屏看清楚本地工作台能不能上公网。</p></div><div class="sync-grid">
    <section class="panel span-6"><h2>运行状态</h2><div class="kv"><span>SQLite</span><strong>${state.settings?.db_path}</strong></div><div class="kv"><span>来源</span><strong>${(state.settings?.sources || []).join(",")}</strong></div><div class="kv"><span>Export token</span><strong>${state.settings?.has_export_token ? "ok" : "missing"}</strong></div><div class="kv"><span>DeepSeek</span><strong>${state.settings?.has_deepseek_key ? "ok" : "fake/local"}</strong></div></section>
    <section class="panel span-6"><h2>部署命令</h2><pre>python3 -m app.web --host 0.0.0.0 --port 8000\n*/30 * * * * python3 scripts/sync_once.py</pre></section>
  </div>`);
}

function nextSlots() {
  const base = new Date();
  const hours = [9, 12, 15, 18, 21];
  const slots = [];
  for (let d = 0; d < 3; d++) {
    for (const h of hours) {
      const date = new Date(base);
      date.setDate(base.getDate() + d);
      date.setHours(h, 0, 0, 0);
      slots.push(date.toISOString().slice(0, 16));
    }
  }
  return slots;
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
function openItem(id) { state.selected = state.items.find((x) => x.id === id); state.view = "editor"; render(); }
async function saveReview(id, status) {
  const text = $("#copy")?.value ?? state.items.find((x) => x.id === id)?.edited_copy ?? "";
  await api(`/api/items/${id}/review`, { edited_copy: text, status });
  await go("review");
}
async function quickReview(id, status) {
  const item = state.items.find((x) => x.id === id);
  await api(`/api/items/${id}/review`, { edited_copy: item.edited_copy || item.generated_copy, status });
  await refresh();
}
function syncPayload() { return { limit: Number($("#limit")?.value || 10), since: $("#since")?.value || "", until: $("#until")?.value || "" }; }
async function previewSync() { state.lastResult = (await api("/api/sync/preview", syncPayload())).result; await refresh(); state.view = "sync"; render(); }
async function runSync() { state.lastResult = (await api("/api/sync/run", syncPayload())).result; await refresh(); state.view = "sync"; render(); }
function dragItem(event, id) { event.dataTransfer.setData("text/plain", String(id)); }
function allowDrop(event) { event.preventDefault(); event.currentTarget.classList.add("dragover"); }
async function dropItem(event, scheduled_at) {
  event.preventDefault();
  event.currentTarget.classList.remove("dragover");
  await api(`/api/items/${event.dataTransfer.getData("text/plain")}/schedule`, { scheduled_at });
  await refresh();
}
async function unschedule(id) { await api(`/api/items/${id}/unschedule`, {}); await refresh(); }

refresh().catch((err) => { $("#app").innerHTML = `<main class="panel"><h1>加载失败</h1><pre>${err}</pre></main>`; });
