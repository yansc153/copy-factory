const state = { view: "review", items: [], selected: null, settings: null, publishQueue: [], lastResult: null, workDate: todayKey() };

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

function counts() {
  return {
    all: state.items.length,
    draft: state.items.filter((x) => x.review_status === "draft").length,
    approved: state.items.filter((x) => x.review_status === "approved").length,
    rejected: state.items.filter((x) => x.review_status === "rejected").length,
    scheduled: state.items.filter((x) => x.schedule_status === "scheduled").length,
    confirmed: state.items.filter((x) => x.publish_status === "confirmed").length,
  };
}

function canMove(item) {
  return item.review_status === "approved" && ["none", "failed"].includes(item.publish_status || "none");
}

async function load() {
  const itemPath = `/api/items?work_date=${encodeURIComponent(state.workDate)}`;
  const [items, settings, queue] = await Promise.all([api(itemPath), api("/api/settings/status"), api("/api/publish/queue")]);
  state.items = items.items;
  state.settings = settings;
  state.publishQueue = queue.tasks;
}

function shell(content, side = "") {
  const nav = ["review:审核", "sync:同步", "schedule:排期", "settings:设置"].map((item) => {
    const [view, label] = item.split(":");
    return `<button class="${state.view === view ? "active" : ""}" onclick="go('${view}')"><span>${label}</span></button>`;
  }).join("");
  return `
    <aside class="nav"><div class="mark">CF</div><p class="nav-note">Morning desk</p>${nav}<button class="run" onclick="go('sync')">运行批次</button></aside>
    <main class="main ${side ? "" : "no-rail"}"><section class="stage">${content}</section><aside class="rail">${side}</aside></main>
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
  const sourceLabel = item.source.includes("xueqiu") ? "雪球" : item.source;
  return `<article class="${compact ? "mini-card" : "feed-item"}" draggable="${canMove(item)}" ondragstart="dragItem(event, ${item.id})">
    ${compact ? "" : `<div class="avatar">${h(sourceLabel[0]?.toUpperCase() || "C")}</div>`}
    <div class="item-body">
      <div class="item-head">
        <span class="item-title">${h(item.title || "Untitled")}</span>
        <span class="muted">· ${h(sourceLabel)}</span>
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
  const side = `<div class="panel"><h2>队列概览</h2>${Object.entries(counts()).map(([k,v]) => `<div class="kv"><span>${k}</span><strong>${v}</strong></div>`).join("")}</div>
    <div class="panel soft"><h2>运行规则</h2><p class="muted">先看 health.generated_at，变了才拉 export。入库按 source_id / url / hash 去重。</p></div>`;
  const items = state.items.map((item) => itemCard(item)).join("") || `<p class="panel">暂无文案。去同步页运行一个批次。</p>`;
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
  return shell(`<div class="topbar"><button class="small-btn" onclick="go('review')">返回审核池</button></div>
    <div class="editor">
      <section class="source-pane"><h1>${h(item.title)}</h1><p class="muted">${h(item.source)} · ${h(item.published_at)} · <a href="${h(item.url)}" target="_blank">原文链接</a></p><h2>原文</h2><pre>${h(item.text)}</pre><h2>图片引用</h2>${mediaGrid(item)}</section>
      <section class="edit-pane"><h2>生成文案</h2><textarea id="copy">${h(item.edited_copy || item.generated_copy)}</textarea><h2>选择配图</h2>${mediaChoices}<div class="form-grid"><button class="wide-btn" onclick="saveReview(${item.id}, 'draft')">保存草稿</button><button class="wide-btn" onclick="saveReview(${item.id}, 'approved')">批准</button><button class="small-btn danger" onclick="saveReview(${item.id}, 'rejected')">拒绝</button><button class="small-btn" onclick="go('schedule')">去排期</button></div><p class="muted">生成状态：${h(item.generation_status)} ${h(item.generation_error || "")}</p></section>
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
  return shell(`<div class="topbar"><p class="eyebrow">Publish desk</p><h1>拖拽排期时间线</h1><p class="muted">把 approved 文案拖到时间槽，再确认发布计划；确认后 server 队列等待 Mac mini 到点领取。</p>${statBar()}</div>
    <div class="timeline"><aside class="approved-pool"><h2>可排期</h2>${approved.map((x) => itemCard(x, true, "pool")).join("") || `<p class="muted">没有未排期 approved 文案。</p>`}</aside><section><div class="confirm-bar"><div><strong>${scheduledReady()} 条可确认</strong><p class="muted">当前队列 ${state.publishQueue.length} 条，confirmed ${state.publishQueue.filter((x) => x.status === "confirmed").length} 条。</p></div><button class="primary" onclick="confirmPublishPlan()">确认发布计划</button></div><div class="slot-grid">${slots.map(slotView).join("")}</div></section></div>`);
}

function scheduledReady() {
  return state.items.filter((x) => x.review_status === "approved" && x.schedule_status === "scheduled" && ["none", "failed"].includes(x.publish_status)).length;
}

function slotView(slot) {
  const items = state.items.filter((x) => x.scheduled_at === slot);
  const parts = formatSlotParts(slot);
  return `<div class="slot" ondragover="allowDrop(event)" ondragleave="event.currentTarget.classList.remove('dragover')" ondrop="dropItem(event, '${slot}')"><time>${parts.time}</time><em>${parts.day}</em>${items.map((x) => itemCard(x, true) + (canMove(x) ? `<button class="small-btn" onclick="unschedule(${x.id})">移出排期</button>` : "")).join("")}</div>`;
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
      slots.push(date.toISOString());
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
async function setWorkDate(value) { state.workDate = value; await refresh(); }
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
async function quickSchedule(id) { await api(`/api/items/${id}/schedule`, { scheduled_at: nextSlots()[0] }); await refresh(); }
async function confirmPublishPlan() {
  const result = await api("/api/publish/confirm_plan", {});
  state.publishQueue = result.tasks;
  await refresh();
  state.view = "schedule";
  render();
}

refresh().catch((err) => { $("#app").innerHTML = `<main class="panel"><h1>加载失败</h1><pre>${err}</pre></main>`; });
