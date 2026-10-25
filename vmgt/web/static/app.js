/* VMGT naršyklės dalis: vienas failas, be surinkimo įrankio.
   Maršrutai – #/… ; duomenys – /api/… ; taisyklės gyvena serveryje,
   čia tik rodoma, ką jis leidžia, ir parodomas jo atsakymas. */
"use strict";

const S = { me: null, meta: null, timers: [] };
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const app = () => $("#app");

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const can = p => S.me && S.me.perms.includes(p);

async function api(method, url, body, isForm) {
  const opt = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) opt.body = body;
    else { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  }
  const r = await fetch(url, opt);
  if (r.status === 401 && !url.endsWith("/login")) { S.me = null; location.hash = "#/login"; throw new Error("Prisijunkite"); }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.detail) || `Klaida ${r.status}`);
  return data;
}
const GET = u => api("GET", u);
const POST = (u, b) => api("POST", u, b ?? {});
const PUT = (u, b) => api("PUT", u, b);

function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg; t.className = err ? "err" : ""; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), err ? 6000 : 2500);
}
async function act(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(okMsg); return r; }
  catch (e) { toast(e.message, true); throw e; }
}

function modal(html, onMount) {
  const m = $("#modal");
  m.innerHTML = `<div class="box">${html}</div>`; m.hidden = false;
  m.onclick = e => { if (e.target === m) closeModal(); };
  onMount && onMount(m.firstElementChild);
}
function closeModal() { $("#modal").hidden = true; $("#modal").innerHTML = ""; }

// ---------- formatai ----------
function dur(s) {
  s = Math.max(0, Math.round(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
}
function hm(s) {
  s = Math.round(s || 0);
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return h ? `${h} val. ${m} min.` : `${m} min.`;
}
function dt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("lt-LT", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
const today = () => new Date().toISOString().slice(0, 10);
const since = iso => (Date.now() - new Date(iso).getTime()) / 1000;
const pill = (cls, text) => `<span class="pill s-${esc(cls)}">${esc(text)}</span>`;
const opt = (list, sel, empty) =>
  (empty !== undefined ? `<option value="">${esc(empty)}</option>` : "") +
  list.map(x => `<option value="${esc(x.key ?? x.id)}" ${String(x.key ?? x.id) === String(sel ?? "") ? "selected" : ""}>${esc(x.label ?? x.name)}</option>`).join("");
function formData(form) {
  const o = {};
  for (const [k, v] of new FormData(form).entries()) o[k] = v;
  return o;
}

// ---------- maršrutizatorius ----------
const ROUTES = [
  [/^#\/login$/, pageLogin],
  [/^#\/?$/, pageHome],
  [/^#\/p\/(\d+)$/, pageProject],
  [/^#\/cechas$/, pageFloor],
  [/^#\/planas(?:\/([\w-]+))?$/, pagePlan],
  [/^#\/t(?:\/([\w-]+))?$/, pageTerminal],
  [/^#\/ncr$/, pageNcr],
  [/^#\/analitika$/, pageAnalytics],
  [/^#\/komponentai(?:\/(\d+))?$/, pageComponents],
  [/^#\/duomenys$/, pageData],
  [/^#\/admin$/, pageAdmin],
];

async function route() {
  S.timers.forEach(clearInterval); S.timers = [];
  closeModal();
  document.body.classList.remove("term");
  const h = location.hash || "#/";
  if (!S.me && h !== "#/login") {
    try { const r = await GET("/api/me"); S.me = r.user; S.meta = r; }
    catch { location.hash = "#/login"; return; }
  }
  renderNav();
  for (const [re, fn] of ROUTES) {
    const m = h.match(re);
    if (m) { try { await fn(...m.slice(1)); } catch (e) { app().innerHTML = `<p class="pad lock">${esc(e.message)}</p>`; } return; }
  }
  app().innerHTML = `<p class="pad">Puslapis nerastas. <a href="#/">Į pradžią</a></p>`;
}
window.addEventListener("hashchange", route);

function renderNav() {
  const top = $("#top");
  if (!S.me) { top.hidden = true; return; }
  top.hidden = false;
  const items = [
    ["#/", "Projektai", "view"], ["#/cechas", "Cechas", "view"], ["#/planas", "Planas", "plan"],
    ["#/t", "Terminalas", "execute"], ["#/ncr", "Neatitiktys", "ncr_report"],
    ["#/komponentai", "Komponentai", "view"],
    ["#/analitika", "Analitika", "view"], ["#/duomenys", "Duomenys", "tasks"], ["#/admin", "Administravimas", "admin"],
  ].filter(x => can(x[2]));
  const h = location.hash || "#/";
  $("#nav").innerHTML = items.map(([href, label]) => {
    const on = href === "#/" ? (h === "#/" || h.startsWith("#/p/")) : h.startsWith(href);
    return `<a href="${href}" class="${on ? "on" : ""}">${label}</a>`;
  }).join("");
  $("#who").textContent = `${S.me.name} · ${S.me.role_label}`;
}
$("#logout").onclick = async () => { await POST("/api/logout").catch(() => {}); S.me = null; location.hash = "#/login"; route(); };

// ---------- prisijungimas ----------
async function pageLogin() {
  $("#top").hidden = true;
  app().innerHTML = `
  <div class="login card">
    <h1>VMGT</h1>
    <p class="muted">Projektų stebėsena ir gamybos valdymas</p>
    <div class="row"><button id="tab-pw">Vardas ir slaptažodis</button><button id="tab-pin" class="ghost">PIN (terminalas)</button></div>
    <form id="f-pw" class="card" style="border:0;padding:0">
      <label>Prisijungimo vardas<input name="login" autocomplete="username" required id="lg-login"></label>
      <label>Slaptažodis<input name="password" type="password" autocomplete="current-password" required id="lg-pass"></label>
      <button>Prisijungti</button>
    </form>
    <div id="f-pin" hidden>
      <div class="pindots" id="pindots"></div>
      <div class="pinpad">${[1,2,3,4,5,6,7,8,9].map(n => `<button class="ghost" data-n="${n}">${n}</button>`).join("")}
        <button class="ghost" data-n="C">⌫</button><button class="ghost" data-n="0">0</button><button data-n="OK">OK</button></div>
    </div>
  </div>`;
  const done = r => { S.me = null; location.hash = r.perms.includes("view") ? "#/" : "#/t"; };
  $("#f-pw").onsubmit = async e => { e.preventDefault(); done(await act(() => POST("/api/login", formData(e.target)))); };
  let pin = "";
  const show = () => ($("#pindots").textContent = "•".repeat(pin.length));
  $("#tab-pw").onclick = () => { $("#f-pw").hidden = false; $("#f-pin").hidden = true; $("#tab-pw").className = ""; $("#tab-pin").className = "ghost"; };
  $("#tab-pin").onclick = () => { $("#f-pw").hidden = true; $("#f-pin").hidden = false; $("#tab-pin").className = ""; $("#tab-pw").className = "ghost"; };
  $$(".pinpad button").forEach(b => b.onclick = async () => {
    const n = b.dataset.n;
    if (n === "C") pin = pin.slice(0, -1);
    else if (n === "OK") { try { done(await act(() => POST("/api/login", { pin }))); } finally { pin = ""; } }
    else if (pin.length < 8) pin += n;
    show();
  });
}

function pageHome() {
  if (!can("view")) { location.hash = "#/t"; return; }
  return pageProjects();
}

// ---------- projektų krepšelis ----------
async function pageProjects() {
  const all = sessionStorage.getItem("pf.all") === "1";
  const [list, users] = await Promise.all([GET(`/api/projects?all=${all ? 1 : 0}`), GET("/api/users")]);
  const managers = users.filter(u => ["vadovas", "admin"].includes(u.role) && u.active);
  app().innerHTML = `
  <div class="row between"><h1>Projektų krepšelis</h1>
    <label class="row" style="display:flex"><input type="checkbox" id="all" ${all ? "checked" : ""}> rodyti baigtus</label></div>
  <div class="tbl"><table>
    <thead><tr><th>Projektas</th><th>Užsakovas</th><th>Vadovas</th><th>Terminas</th><th>Būsena</th><th>Vykdomi etapai</th><th>Užduotys</th><th>Neatitiktys</th></tr></thead>
    <tbody>${list.map(p => {
      const late = p.due_date && p.due_date < today() && p.status !== "baigtas";
      const pct = p.tasks_total ? Math.round(100 * p.tasks_done / p.tasks_total) : 0;
      return `<tr class="click" data-id="${p.id}">
        <td><b class="mono">${esc(p.code)}</b><br>${esc(p.name)}</td><td>${esc(p.customer)}</td><td>${esc(p.manager_name || "—")}</td>
        <td class="num ${late ? "s-late" : ""}">${esc(p.due_date || "—")}${late ? " ⚠" : ""}</td>
        <td>${pill(p.status, p.status_label)} <span class="muted">P${p.priority}</span></td>
        <td>${esc(p.active_phases.join(", ") || "—")}</td>
        <td><div class="prog" title="${p.tasks_done} iš ${p.tasks_total}"><i style="width:${pct}%"></i></div><span class="muted num">${p.tasks_done}/${p.tasks_total}</span></td>
        <td>${p.ncr_open ? pill("atvira", p.ncr_open + " atv.") : "—"}</td></tr>`;
    }).join("") || `<tr><td colspan="8" class="muted">Projektų nėra.</td></tr>`}</tbody></table></div>
  ${can("projects") ? `<div class="card"><h2>Naujas projektas</h2>
    <form id="newp" class="inline">
      <label>Kodas<input name="code" required placeholder="P-24140" id="np-code"></label>
      <label>Pavadinimas<input name="name" required id="np-name"></label>
      <label>Užsakovas<input name="customer" id="np-cust"></label>
      <label>Terminas<input name="due_date" type="date" id="np-due"></label>
      <label>Prioritetas<select name="priority" id="np-prio">${[1,2,3,4,5].map(n => `<option ${n === 3 ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label>Vadovas<select name="manager_id" id="np-man">${opt(managers, "", "—")}</select></label>
      <button>Įtraukti į krepšelį</button></form></div>` : ""}`;
  $("#all").onchange = e => { sessionStorage.setItem("pf.all", e.target.checked ? "1" : "0"); route(); };
  $$("tr.click").forEach(tr => tr.onclick = () => (location.hash = `#/p/${tr.dataset.id}`));
  const f = $("#newp");
  if (f) f.onsubmit = async e => {
    e.preventDefault();
    const d = formData(f); d.priority = +d.priority; d.manager_id = d.manager_id ? +d.manager_id : null;
    const r = await act(() => POST("/api/projects", d), "Projektas įtrauktas");
    location.hash = `#/p/${r.id}`;
  };
}

// ---------- projekto puslapis ----------
async function pageProject(pid) {
  const [p, users, centres] = await Promise.all([GET(`/api/projects/${pid}`), GET("/api/users"), GET("/api/centres?all=1")]);
  const active = users.filter(u => u.active);
  const ed = can("projects"), edt = can("tasks");
  const asmName = id => { const a = p.assemblies.find(x => x.id === id); return a ? `${a.code} ${a.name}` : "Visas projektas"; };
  app().innerHTML = `
  <div class="row between"><div><a href="#/">← Krepšelis</a><h1><span class="mono">${esc(p.code)}</span> ${esc(p.name)}</h1>
    <p class="muted">${esc(p.customer)} · terminas ${esc(p.due_date || "—")} · vadovas ${esc(p.manager_name || "—")}</p></div>
    <div>${pill(p.status, p.status_label)}</div></div>
  ${ed ? `<form id="pedit" class="inline card">
      <label>Būsena<select name="status" id="pe-status">${opt(S.meta.project_statuses, p.status)}</select></label>
      <label>Vadovas<select name="manager_id" id="pe-man">${opt(active, p.manager_id, "—")}</select></label>
      <label>Terminas<input type="date" name="due_date" value="${esc(p.due_date || "")}" id="pe-due"></label>
      <label>Prioritetas<input type="number" min="1" max="5" name="priority" value="${p.priority}" id="pe-prio" style="width:70px"></label>
      <button class="ghost">Įrašyti</button></form>` : ""}
  <div class="card"><div class="row between"><h2>Etapų planas</h2><span class="muted">${p.phases_done} iš ${p.phases_total} baigta</span></div>
    ${gantt(p.phases, asmName)}</div>
  <div class="card"><h2>Etapai ir atsakingieji</h2>
    <div class="tbl"><table><thead><tr><th>Mazgas</th><th>Etapas</th><th>Atsakingas</th><th>Planas</th><th>Faktas</th><th>Būsena</th></tr></thead>
    <tbody>${p.phases.map(ph => `<tr>
      <td>${esc(asmName(ph.assembly_id))}</td><td>${esc(ph.kind_label)}</td>
      <td>${ed ? `<select data-ph="${ph.id}" data-f="owner_id" id="ph-o-${ph.id}">${opt(active, ph.owner_id, "—")}</select>` : esc(ph.owner_name || "—")}</td>
      <td class="num">${ed ? `<input type="date" data-ph="${ph.id}" data-f="plan_start" value="${esc(ph.plan_start || "")}" id="ph-s-${ph.id}"> – <input type="date" data-ph="${ph.id}" data-f="plan_end" value="${esc(ph.plan_end || "")}" id="ph-e-${ph.id}">` : `${esc(ph.plan_start || "—")} – ${esc(ph.plan_end || "—")}`}</td>
      <td class="num muted">${ph.actual_start ? dt(ph.actual_start) : "—"} – ${ph.actual_end ? dt(ph.actual_end) : ""}</td>
      <td>${pill(ph.status, ph.status)} ${ed ? phaseBtns(ph) : ""}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">Etapų dar nėra.</td></tr>`}</tbody></table></div>
    ${ed ? `<form id="newph" class="inline">
      <label>Mazgas<select name="assembly_id" id="nph-a">${opt(p.assemblies.map(a => ({ id: a.id, name: `${a.code} ${a.name}` })), "", "Visas projektas")}</select></label>
      <label>Etapas<select name="kind" id="nph-k">${opt(S.meta.phase_kinds)}</select></label>
      <label>Atsakingas<select name="owner_id" id="nph-o">${opt(active, "", "—")}</select></label>
      <label>Pradžia<input type="date" name="plan_start" id="nph-s"></label><label>Pabaiga<input type="date" name="plan_end" id="nph-e"></label>
      <button class="ghost">Pridėti etapą</button></form>` : ""}</div>
  <div class="card"><h2>Mazgai ir maršrutai</h2>
    ${p.assemblies.map(a => {
      const ts = p.tasks.filter(t => t.assembly_id === a.id);
      return `<div><h3><span class="mono">${esc(a.code)}</span> ${esc(a.name)} <span class="muted">× ${a.qty}${a.requires ? ` · laukia mazgų ${esc(a.requires)}` : ""}</span></h3>
      <div class="tbl"><table><thead><tr><th>Seka</th><th>Centras</th><th>Operacija</th><th>Kiekis</th><th>Norma</th><th>Brėžinys</th><th>Būsena</th><th></th></tr></thead><tbody>
      ${ts.map(t => `<tr><td class="num">${t.seq}</td><td class="mono">${esc(t.centre_code)}</td><td>${esc(t.name)}</td>
        <td class="num">${t.qty_good}/${t.qty_plan}${t.qty_scrap ? ` <span class="s-late">brokas ${t.qty_scrap}</span>` : ""}</td>
        <td class="num">${t.norm_min ? t.norm_min + " min/vnt" : "—"}</td>
        <td>${t.drawing_no ? `<a href="/api/drawings/${encodeURIComponent(t.drawing_no)}/file?rev=${encodeURIComponent(t.drawing_rev)}" target="_blank">${esc(t.drawing_no)} ${esc(t.drawing_rev)}</a>` : "—"}</td>
        <td>${pill(t.status, t.status)}${t.approved ? "" : ' <span class="muted">nepatvirtinta</span>'}</td>
        <td>${edt && t.status === "laukia" && !t.qty_good ? `<button class="small ghost" data-del="${t.id}">Šalinti</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="8" class="muted">Operacijų nėra.</td></tr>`}
      </tbody></table></div>
      ${edt ? `<form class="inline newt" data-a="${a.id}" style="margin-top:8px">
        <label>Seka<input name="seq" type="number" style="width:70px" placeholder="auto" id="nt-q-${a.id}"></label>
        <label>Centras<select name="centre_id" required id="nt-c-${a.id}">${opt(centres.map(c => ({ id: c.id, name: `${c.code} ${c.name}` })))}</select></label>
        <label>Operacija<input name="name" required id="nt-n-${a.id}"></label>
        <label>Kiekis<input name="qty_plan" type="number" min="1" value="${a.qty}" style="width:70px" id="nt-k-${a.id}"></label>
        <label>Norma min/vnt<input name="norm_min" type="number" step="0.1" style="width:90px" id="nt-m-${a.id}"></label>
        <label>Brėžinys<input name="drawing_no" style="width:110px" id="nt-d-${a.id}"></label><label>Rev.<input name="drawing_rev" style="width:50px" id="nt-r-${a.id}"></label>
        <button class="ghost">Pridėti operaciją</button></form>` : ""}</div>`;
    }).join("") || `<p class="muted">Mazgų dar nėra.</p>`}
    ${ed ? `<form id="newa" class="inline"><label>Mazgo kodas<input name="code" required id="na-code"></label><label>Pavadinimas<input name="name" required id="na-name"></label>
      <label>Kiekis<input name="qty" type="number" min="1" value="1" style="width:70px" id="na-qty"></label>
      <label>Laukia mazgų<input name="requires" placeholder="100,200" style="width:110px" id="na-req"></label><button class="ghost">Pridėti mazgą</button></form>` : ""}
  </div>
  <div class="card"><div class="row between"><h2>Komponentai</h2><a href="#/komponentai/${p.id}">Visi projekto pirkimai →</a></div>
    ${compSummaryLine(p.components_summary)}
    ${p.components.length ? compTable(p.components, { compact: true }) : `<p class="muted">Pirkimo eilučių dar nėra.</p>`}</div>
  <div class="card"><h2>Neatitiktys</h2>${ncrTable(p.ncr, false)}</div>`;

  const reload = () => pageProject(pid);
  const pe = $("#pedit");
  if (pe) pe.onsubmit = async e => {
    e.preventDefault(); const d = formData(pe);
    d.manager_id = d.manager_id ? +d.manager_id : null; d.priority = +d.priority; d.due_date = d.due_date || null;
    await act(() => PUT(`/api/projects/${pid}`, d), "Įrašyta"); reload();
  };
  $$("[data-ph][data-f]").forEach(el => el.onchange = async () => {
    const v = el.value || null;
    await act(() => PUT(`/api/phases/${el.dataset.ph}`, { [el.dataset.f]: el.dataset.f === "owner_id" ? (v ? +v : null) : v }), "Įrašyta");
    reload();
  });
  $$("[data-phs]").forEach(b => b.onclick = async () => { await act(() => POST(`/api/phases/${b.dataset.id}/status`, { status: b.dataset.phs })); reload(); });
  const nph = $("#newph");
  if (nph) nph.onsubmit = async e => {
    e.preventDefault(); const d = formData(nph);
    d.assembly_id = d.assembly_id ? +d.assembly_id : null; d.owner_id = d.owner_id ? +d.owner_id : null;
    d.plan_start = d.plan_start || null; d.plan_end = d.plan_end || null;
    await act(() => POST(`/api/projects/${pid}/phases`, d), "Etapas pridėtas"); reload();
  };
  const na = $("#newa");
  if (na) na.onsubmit = async e => { e.preventDefault(); await act(() => POST(`/api/projects/${pid}/assemblies`, formData(na)), "Mazgas pridėtas"); reload(); };
  $$("form.newt").forEach(f => f.onsubmit = async e => {
    e.preventDefault(); const d = formData(f);
    d.project_id = +pid; d.assembly_id = +f.dataset.a; d.centre_id = +d.centre_id;
    d.seq = d.seq ? +d.seq : null; d.qty_plan = +d.qty_plan || 1; d.norm_min = +d.norm_min || 0;
    await act(() => POST("/api/tasks", d), "Operacija pridėta"); reload();
  });
  $$("[data-del]").forEach(b => b.onclick = async () => { await act(() => api("DELETE", `/api/tasks/${b.dataset.del}`), "Pašalinta"); reload(); });
}

function phaseBtns(ph) {
  const b = (st, label) => `<button class="small ghost" data-phs="${st}" data-id="${ph.id}">${label}</button>`;
  if (ph.status === "planuota") return b("vykdoma", "Pradėti");
  if (ph.status === "vykdoma") return b("baigta", "Baigti");
  return b("vykdoma", "Atidaryti");
}

function gantt(phases, asmName) {
  const ds = phases.flatMap(p => [p.plan_start, p.plan_end, p.actual_start && p.actual_start.slice(0, 10), p.actual_end && p.actual_end.slice(0, 10)]).filter(Boolean);
  if (!ds.length) return `<p class="muted">Etapams nenurodytos datos.</p>`;
  ds.push(today());
  const t0 = new Date(ds.reduce((a, b) => a < b ? a : b)).getTime();
  const t1 = new Date(ds.reduce((a, b) => a > b ? a : b)).getTime() + 86400000;
  const pos = d => `${(100 * (new Date(d).getTime() - t0) / (t1 - t0)).toFixed(2)}%`;
  const width = (a, b) => `${Math.max(0.6, 100 * (new Date(b).getTime() - new Date(a).getTime()) / (t1 - t0)).toFixed(2)}%`;
  const weeks = [];
  for (let t = t0; t < t1; t += 7 * 86400000) weeks.push(new Date(t).toISOString().slice(5, 10));
  const lanes = phases.map(ph => {
    const col = `var(--p-${ph.kind})`;
    const plan = ph.plan_start && ph.plan_end ? `<div class="bar" style="left:${pos(ph.plan_start)};width:${width(ph.plan_start, ph.plan_end + "T23:59:59")};background:${col}" title="Planas ${ph.plan_start} – ${ph.plan_end}"></div>` : "";
    const actEnd = ph.actual_end || (ph.actual_start ? new Date().toISOString() : null);
    const act = ph.actual_start ? `<div class="act" style="left:${pos(ph.actual_start)};width:${width(ph.actual_start, actEnd)};background:${col}" title="Faktas"></div>` : "";
    return `<div class="lab" title="${esc(asmName(ph.assembly_id))} · ${esc(ph.kind_label)}">${esc(asmName(ph.assembly_id))} · ${esc(ph.kind_label)}</div>
      <div class="lane">${plan}${act}<div class="today" style="left:${pos(today())}"></div></div>`;
  }).join("");
  const legend = S.meta.phase_kinds.map(k => `<span><i style="background:var(--p-${k.key})"></i>${esc(k.label)}</span>`).join("");
  return `<div class="gantt"><div></div><div class="axis">${weeks.map((w, i) => `<span style="left:${(100 * i * 7 * 86400000 / (t1 - t0)).toFixed(2)}%">${w}</span>`).join("")}</div>${lanes}</div>
    <div class="legend">${legend}<span>Plona juosta – planas, stora – faktas, raudona linija – šiandien</span></div>`;
}

// ---------- gamybos barai ----------
// Centrai grupuojami pagal barą tokia tvarka, kokią grąžina serveris
// (barų eilė, centrų eilė bare); centras be baro – grupėje „Be baro“.
function byArea(list, get = x => x) {
  const groups = [];
  for (const x of list) {
    const c = get(x), k = c.area_code || "";
    let g = groups.find(g => g.code === k);
    if (!g) groups.push(g = { code: k, name: c.area_name || "Be baro", items: [] });
    g.items.push(x);
  }
  return groups;
}
function centreOptions(centres, sel) {
  return byArea(centres).map(g => `<optgroup label="${esc(g.name)}">${g.items.map(c =>
    `<option value="${esc(c.code)}" ${c.code === sel ? "selected" : ""}>${esc(c.code)} ${esc(c.name)}</option>`).join("")}</optgroup>`).join("");
}

// ---------- cechas ----------
async function pageFloor() {
  const draw = async () => {
    const r = await GET("/api/floor");
    const label = { dirba: "Dirba", pristabdyta: "Pristabdyta", gali: "Gali pradėti", laukia: "Laukia", tuscia: "Eilėje nėra" };
    let sel = ""; try { sel = localStorage.getItem("pf.area") || ""; } catch {}
    const groups = byArea(r.centres, s => s.centre);
    if (sel && !groups.some(g => g.code === sel)) sel = "";
    const masters = Object.fromEntries(r.areas.map(a => [a.code, a.master_name]));
    const count = (items, st) => items.filter(s => s.state === st).length;
    const card = s => {
      const t = s.task, n = s.next;
      const link = can("execute") ? `#/t/${s.centre.code}` : can("plan") ? `#/planas/${s.centre.code}` : "#/cechas";
      return `<a class="wc ${s.state}" href="${link}">
        <div class="row between"><b class="mono">${esc(s.centre.code)}</b>${pill(s.state, label[s.state])}</div>
        <div class="muted">${esc(s.centre.name)}</div>
        ${t ? `<div><b>${esc(t.project_code)} · ${esc(t.assembly_code)}</b><br>${esc(t.name)}</div>
          <div class="t" data-since="${s.state === "dirba" ? esc(s.since || "") : ""}" data-base="${s.work_s || 0}">${dur((s.work_s || 0) + (s.state === "dirba" && s.since ? since(s.since) : 0))}</div>
          <div class="muted">${esc(s.who || "")}${s.pause ? ` · ${esc(s.pause)}` : ""}</div>`
        : n ? `<div>Kitas: <b>${esc(n.project_code)} · ${esc(n.assembly_code)}</b> ${esc(n.name)}</div>${s.lock ? `<div class="lock">🔒 ${esc(s.lock)}</div>` : ""}` : ""}
        <div class="muted">Eilėje: ${s.queue}</div></a>`;
    };
    app().innerHTML = `<div class="row between"><h1>Cecho būsena</h1><span class="muted">atnaujinama kas 10 s</span></div>
    <div class="chips"><button class="${sel ? "ghost" : ""}" data-area="">Visi barai</button>${groups.map(g =>
      `<button class="${sel === g.code ? "" : "ghost"}" data-area="${esc(g.code)}">${esc(g.name)}</button>`).join("")}</div>
    ${groups.filter(g => !sel || g.code === sel).map(g => `<section class="area">
      <div class="row between area-h"><h2>${esc(g.name)}</h2>
        <div class="row">${masters[g.code] ? `<span class="muted">Meistras: ${esc(masters[g.code])}</span>` : ""}
          ${pill("dirba", `dirba ${count(g.items, "dirba")}`)} ${count(g.items, "pristabdyta") ? pill("pristabdyta", `pristabdyta ${count(g.items, "pristabdyta")}`) : ""}
          ${pill("gali", `gali pradėti ${count(g.items, "gali")}`)} <span class="muted">${g.items.length} centr.</span></div></div>
      <div class="floor">${g.items.map(card).join("")}</div></section>`).join("")}`;
    $$("[data-area]").forEach(b => b.onclick = () => { try { localStorage.setItem("pf.area", b.dataset.area); } catch {} draw(); });
  };
  await draw();
  S.timers.push(setInterval(draw, 10000));
  S.timers.push(setInterval(() => $$("[data-since]").forEach(el => el.dataset.since && (el.textContent = dur(+el.dataset.base + since(el.dataset.since)))), 1000));
}

// ---------- planas ----------
async function pagePlan(code) {
  const centres = await GET("/api/centres");
  code = code || localStorage.getItem("pf.plan") || (centres[0] && centres[0].code);
  if (!code) { app().innerHTML = `<p class="pad">Darbo centrų nėra.</p>`; return; }
  localStorage.setItem("pf.plan", code);
  const r = await GET(`/api/plan/${code}`);
  const unapproved = r.tasks.filter(t => !t.approved).length;
  app().innerHTML = `<div class="row between"><h1>Darbo centrų eilės</h1>
    <select id="pc">${centreOptions(centres, code)}</select></div>
  <div class="card"><div class="row between"><h2>${esc(r.centre.code)} ${esc(r.centre.name)}</h2>
    <button id="appr" ${unapproved ? "" : "disabled"}>Patvirtinti eilę${unapproved ? ` (${unapproved} naujos)` : ""}</button></div>
    <p class="muted">Terminalas rodo tik patvirtintas užduotis. ${r.centre.strict_order ? "Šiame centre griežta eilė: pradėti galima tik pirmą." : "Operatorius gali rinktis iš eilės."}</p>
    <div class="tbl"><table><thead><tr><th>#</th><th>Projektas · mazgas</th><th>Operacija</th><th>Kiekis</th><th>Terminas</th><th>Būsena</th><th>Kliūtis</th><th></th></tr></thead>
    <tbody>${r.tasks.map((t, i) => `<tr class="${t.approved ? "" : "dim"}">
      <td class="num">${i + 1}</td><td><b class="mono">${esc(t.project_code)}</b> · ${esc(t.assembly_code)} ${esc(t.assembly_name)}</td>
      <td>${esc(t.name)}</td><td class="num">${t.qty_good}/${t.qty_plan}</td><td class="num">${esc(t.due_date || "—")} <span class="muted">P${t.priority}</span></td>
      <td>${pill(t.status, t.status)} ${t.approved ? "" : '<span class="muted">nepatvirtinta</span>'}</td>
      <td class="lock">${esc(t.lock || "")}${t.components_missing ? `<div class="warn">⚠ negauti komponentai: ${t.components_missing} eil.</div>` : ""}</td>
      <td class="row" style="flex-wrap:nowrap"><button class="small ghost" data-mv="top" data-id="${t.id}" title="Į pradžią">⤒</button>
        <button class="small ghost" data-mv="up" data-id="${t.id}">▲</button><button class="small ghost" data-mv="down" data-id="${t.id}">▼</button></td></tr>`).join("")
      || `<tr><td colspan="8" class="muted">Eilėje užduočių nėra.</td></tr>`}</tbody></table></div></div>`;
  $("#pc").onchange = e => (location.hash = `#/planas/${e.target.value}`);
  $("#appr").onclick = async () => { await act(() => POST(`/api/plan/${code}/approve`), "Eilė patvirtinta"); pagePlan(code); };
  $$("[data-mv]").forEach(b => b.onclick = async () => { await act(() => POST(`/api/tasks/${b.dataset.id}/move`, { where: b.dataset.mv })); pagePlan(code); });
}

// ---------- terminalas ----------
async function pageTerminal(code) {
  document.body.classList.add("term");
  const centres = await GET("/api/centres");
  if (!code) {
    const saved = localStorage.getItem("pf.term");
    if (saved && centres.some(c => c.code === saved)) { location.hash = `#/t/${saved}`; return; }
    app().innerHTML = `<div class="tm"><h1>Pasirinkite darbo centrą</h1>${byArea(centres).map(g => `<h2>${esc(g.name)}</h2>
      <div class="floor">${g.items.map(c => `<a class="wc gali" href="#/t/${c.code}"><b class="mono">${esc(c.code)}</b><span>${esc(c.name)}</span></a>`).join("")}</div>`).join("")}</div>`;
    return;
  }
  localStorage.setItem("pf.term", code);
  let data;
  const draw = async () => {
    data = await GET(`/api/terminal/${code}`);
    const run = data.running;
    const first = data.queue.findIndex(t => !t.lock);
    app().innerHTML = `<div class="tm">
      <div class="row between"><h1><span class="mono">${esc(data.centre.code)}</span> ${esc(data.centre.name)}</h1>
        <div class="row"><span class="muted">${esc(S.me.name)}</span>${centres.length > 1 ? `<button class="ghost" id="chg">Kitas centras</button>` : ""}</div></div>
      ${run ? runCard(run) : `<div class="card"><h2>Šiuo metu niekas nevykdoma</h2><p class="muted">${first >= 0 ? "Pradėkite pažymėtą užduotį eilėje." : data.queue.length ? "Visos eilės užduotys šiuo metu užrakintos – priežastys nurodytos prie kiekvienos." : "Patvirtintoje eilėje užduočių nėra."}</p></div>`}
      <div class="card"><h2>Eilė</h2>${data.queue.map((t, i) => `
        <div class="q ${!run && i === first ? "next" : ""}">
          <div><b>${esc(t.project_code)} · ${esc(t.assembly_code)} ${esc(t.assembly_name)}</b><br>${esc(t.name)} · ${t.qty_plan - t.qty_good} vnt.${t.qty_good ? ` (padaryta ${t.qty_good})` : ""}
            ${t.drawing_no ? ` · <a href="/api/drawings/${encodeURIComponent(t.drawing_no)}/file?rev=${encodeURIComponent(t.drawing_current || t.drawing_rev)}" target="_blank">brėžinys ${esc(t.drawing_no)}</a>` : ""}
            ${t.lock ? `<div class="lock">🔒 ${esc(t.lock)}</div>` : ""}
            ${t.components_missing ? `<div class="warn">⚠ Negauti pirktiniai komponentai: ${t.components_missing} eil.</div>` : ""}</div>
          <div>${t.lock && t.lock.includes("revizija") && can("ack_rev") ? `<button class="b-pause" data-ack="${t.id}">Patvirtinti reviziją</button>` : ""}
            ${!run && !t.lock ? `<button class="b-ok" data-start="${t.id}">▶ Start</button>` : ""}</div>
        </div>`).join("") || `<p class="muted">Tuščia.</p>`}
        ${data.unapproved ? `<p class="muted">Dar ${data.unapproved} užduotys laukia planuotojo patvirtinimo.</p>` : ""}</div>
      ${data.done_today.length ? `<div class="card"><h2>Atlikta šiandien</h2>${data.done_today.map(t => `<div class="muted">✓ ${esc(t.project_code)} · ${esc(t.assembly_code)} ${esc(t.name)} – ${t.qty_good} vnt.${t.qty_scrap ? `, brokas ${t.qty_scrap}` : ""}</div>`).join("")}</div>` : ""}
    </div>`;
    const chg = $("#chg"); if (chg) chg.onclick = () => { localStorage.removeItem("pf.term"); location.hash = "#/t"; };
    $$("[data-start]").forEach(b => b.onclick = async () => { await act(() => POST(`/api/terminal/${b.dataset.start}/start`), "Pradėta"); draw(); });
    $$("[data-ack]").forEach(b => b.onclick = async () => { await act(() => POST(`/api/tasks/${b.dataset.ack}/ack_revision`), "Revizija patvirtinta"); draw(); });
    if (run) wireRun(run, draw);
  };
  await draw();
  S.timers.push(setInterval(() => { if ($("#modal").hidden) draw(); }, 15000));
  S.timers.push(setInterval(() => {
    const el = $("#timer"); if (el && data && data.running && data.running.since && !data.running.pause)
      el.textContent = dur(data.running.work_s + since(data.running.since));
    const pz = $("#ptimer"); if (pz && data && data.running && data.running.pause) pz.textContent = dur(since(data.running.pause.start));
  }, 1000));
}

function runCard(t) {
  const paused = !!t.pause;
  const revOk = !t.drawing_current || t.drawing_current === t.drawing_rev;
  return `<div class="card now ${paused ? "paused" : ""}">
    <div class="muted">${paused ? "PRISTABDYTA" : "DABAR VYKDOMA"} · projektas ${esc(t.project_code)} ${esc(t.project_name)}</div>
    <h2 style="font-size:22px">${esc(t.assembly_code)} ${esc(t.assembly_name)} · ${esc(t.name)}</h2>
    <div class="timer" id="timer">${dur(t.work_s + (paused ? 0 : since(t.since)))}</div>
    ${t.components_missing ? `<div class="warn">⚠ Šiam mazgui dar negauti pirktiniai komponentai: ${t.components_missing} eil.</div>` : ""}
    ${paused ? `<div style="color:var(--pause)">⏸ ${esc(t.pause.reason_label)}${t.pause.note ? ` – ${esc(t.pause.note)}` : ""} · <span id="ptimer">${dur(since(t.pause.start))}</span></div>` : ""}
    <div class="row muted">Planuota ${t.qty_plan} vnt. · padaryta ${t.qty_good}${t.qty_scrap ? ` · brokas ${t.qty_scrap}` : ""}${t.norm_min ? ` · norma ${t.norm_min} min/vnt` : ""}
      ${t.drawing_no ? ` · brėžinys ${esc(t.drawing_no)} <span class="${revOk ? "rev-ok" : "rev-bad"}">rev. ${esc(t.drawing_rev)} ${revOk ? "✓" : `(galioja ${esc(t.drawing_current)})`}</span>` : ""}</div>
    <div class="big">
      ${paused ? `<button class="b-ok" id="b-resume">▶ Tęsti</button>` : `<button class="b-pause" id="b-pause">⏸ Pauzė</button>`}
      <button class="b-stop" id="b-stop">■ ${paused ? "Baigti" : "Stop"}</button>
      <button class="b-ncr" id="b-ncr">⚠ Neatitiktis</button>
      ${t.drawing_no ? `<a class="btn b-doc" style="font-size:20px;padding:18px 10px;text-align:center;border:0;color:#fff" target="_blank" href="/api/drawings/${encodeURIComponent(t.drawing_no)}/file?rev=${encodeURIComponent(t.drawing_rev)}">📄 Brėžinys</a>` : ""}
    </div></div>`;
}

function wireRun(t, redraw) {
  const p = $("#b-pause");
  if (p) p.onclick = () => {
    let reason = null;
    modal(`<h2>Pauzės priežastis</h2><div class="grid-reasons">${S.meta.pause_reasons.map(r => `<button data-r="${r.key}">${esc(r.label)}</button>`).join("")}</div>
      <label>Pastaba<input id="pz-note" placeholder="būtina, jei „Kita“"></label>
      <div class="row"><button id="pz-ok" disabled>Pristabdyti</button><button class="ghost" id="pz-x">Atšaukti</button></div>`, box => {
      $$("[data-r]", box).forEach(b => b.onclick = () => { reason = b.dataset.r; $$("[data-r]", box).forEach(x => x.classList.toggle("sel", x === b)); $("#pz-ok").disabled = false; });
      $("#pz-x").onclick = closeModal;
      $("#pz-ok").onclick = async () => { await act(() => POST(`/api/terminal/${t.id}/pause`, { reason, note: $("#pz-note").value })); closeModal(); redraw(); };
    });
  };
  const rs = $("#b-resume");
  if (rs) rs.onclick = async () => { await act(() => POST(`/api/terminal/${t.id}/resume`)); redraw(); };
  $("#b-stop").onclick = () => {
    const left = Math.max(0, t.qty_plan - t.qty_good - t.qty_scrap);
    modal(`<h2>Baigti darbą</h2><p class="muted">${esc(t.name)} · liko ${left} iš ${t.qty_plan} vnt.</p>
      <div class="qty"><label>Gera<input id="st-good" type="number" min="0" value="${left}"></label><label>Brokas<input id="st-scrap" type="number" min="0" value="0"></label></div>
      <label class="row" style="display:flex"><input type="checkbox" id="st-fin"> užduotis baigta, nors ne visas kiekis</label>
      <p class="muted" id="st-hint"></p>
      <div class="row"><button id="st-ok">Įrašyti</button><button class="ghost" id="st-x">Atšaukti</button></div>`, () => {
      const hint = () => {
        const g = +$("#st-good").value || 0, s = +$("#st-scrap").value || 0;
        $("#st-hint").textContent = $("#st-fin").checked || g + s >= left ? "Užduotis bus baigta." : `Dalinis atlikimas: ${left - g - s} vnt. liks eilėje.`;
      };
      ["#st-good", "#st-scrap", "#st-fin"].forEach(s => $(s).oninput = hint); hint();
      $("#st-x").onclick = closeModal;
      $("#st-ok").onclick = async () => {
        const body = { good: +$("#st-good").value || 0, scrap: +$("#st-scrap").value || 0 };
        if ($("#st-fin").checked) body.finish = true;
        const r = await act(() => POST(`/api/terminal/${t.id}/stop`, body), "Įrašyta");
        closeModal();
        if (r.suggest_ncr) ncrModal({ task_id: t.id, qty: body.scrap, title: "Užregistruokite broką kaip neatitiktį" }, redraw);
        else redraw();
      };
    });
  };
  $("#b-ncr").onclick = () => ncrModal({ task_id: t.id }, redraw);
}

function ncrModal(pre, after, projects) {
  modal(`<h2>${esc(pre.title || "Nauja neatitiktis")}</h2>
    ${projects ? `<label>Projektas<select id="nc-p">${opt(projects.map(p => ({ id: p.id, name: `${p.code} ${p.name}` })))}</select></label>` : ""}
    <label>Kategorija<select id="nc-cat">${opt(S.meta.ncr_categories, "", "— pasirinkite —")}</select></label>
    <label>Kiekis<input id="nc-qty" type="number" min="0" value="${pre.qty || 0}"></label>
    <label>Kas negerai<textarea id="nc-desc"></textarea></label>
    <div class="row"><button id="nc-ok">Registruoti</button><button class="ghost" id="nc-x">Atšaukti</button></div>`, () => {
    $("#nc-x").onclick = () => { closeModal(); after && after(); };
    $("#nc-ok").onclick = async () => {
      const body = { task_id: pre.task_id || null, category: $("#nc-cat").value, qty: +$("#nc-qty").value || 0, description: $("#nc-desc").value };
      if (projects) body.project_id = +$("#nc-p").value;
      await act(() => POST("/api/ncr", body), "Neatitiktis užregistruota");
      closeModal(); after && after();
    };
  });
}

// ---------- neatitiktys ----------
function ncrTable(list, manage, users) {
  if (!list.length) return `<p class="muted">Neatitikčių nėra.</p>`;
  return `<div class="tbl"><table><thead><tr><th>Nr.</th><th>Data</th><th>Projektas · mazgas</th><th>Operacija</th><th>Kategorija</th><th>Aprašymas</th><th>Būsena</th>${manage ? "<th></th>" : ""}</tr></thead>
    <tbody>${list.map(n => `<tr><td class="num">${n.id}</td><td class="num">${dt(n.reported_at)}<br><span class="muted">${esc(n.reporter || "")}</span></td>
      <td><span class="mono">${esc(n.project_code)}</span> ${esc(n.assembly_code || "")}</td><td>${esc(n.centre_code || "")} ${esc(n.task_name || "")}</td>
      <td>${esc(n.category_label)}${n.qty ? ` · ${n.qty} vnt.` : ""}</td><td>${esc(n.description)}${n.resolution ? `<br><span class="muted">Sprendimas: ${esc(n.resolution)}</span>` : ""}</td>
      <td>${pill(n.status, n.status_label)}${n.assignee ? `<br><span class="muted">${esc(n.assignee)}</span>` : ""}</td>
      ${manage ? `<td>${n.status !== "uzdaryta" ? `<select data-asg="${n.id}" id="asg-${n.id}">${opt(users, n.assignee_id, "Priskirti…")}</select> <button class="small ghost" data-close="${n.id}">Uždaryti</button>` : ""}</td>` : ""}</tr>`).join("")}</tbody></table></div>`;
}

async function pageNcr() {
  const st = sessionStorage.getItem("pf.ncr") || "open";
  const [list, users, projects] = await Promise.all([GET(`/api/ncr?status=${st === "all" ? "" : st}`), GET("/api/users").catch(() => []), can("view") ? GET("/api/projects") : []]);
  const manage = can("ncr_manage");
  app().innerHTML = `<div class="row between"><h1>Neatitiktys</h1>
    <div class="row"><select id="nst"><option value="open" ${st === "open" ? "selected" : ""}>Neuždarytos</option><option value="all" ${st === "all" ? "selected" : ""}>Visos</option></select>
    ${projects.length ? `<button id="nnew">Nauja neatitiktis</button>` : ""}</div></div>
    ${ncrTable(list, manage, users.filter(u => u.active))}`;
  $("#nst").onchange = e => { sessionStorage.setItem("pf.ncr", e.target.value); pageNcr(); };
  const nn = $("#nnew"); if (nn) nn.onclick = () => ncrModal({}, pageNcr, projects);
  $$("[data-asg]").forEach(s => s.onchange = async () => { if (!s.value) return; await act(() => POST(`/api/ncr/${s.dataset.asg}/assign`, { assignee_id: +s.value }), "Priskirta"); pageNcr(); });
  $$("[data-close]").forEach(b => b.onclick = () => modal(`<h2>Uždaryti neatitiktį #${b.dataset.close}</h2><label>Sprendimas<textarea id="res"></textarea></label>
    <div class="row"><button id="c-ok">Uždaryti</button><button class="ghost" id="c-x">Atšaukti</button></div>`, () => {
    $("#c-x").onclick = closeModal;
    $("#c-ok").onclick = async () => { await act(() => POST(`/api/ncr/${b.dataset.close}/close`, { resolution: $("#res").value }), "Uždaryta"); closeModal(); pageNcr(); };
  }));
}

// ---------- analitika ----------
async function pageAnalytics() {
  const f = sessionStorage.getItem("pf.af") || "", t = sessionStorage.getItem("pf.at") || "";
  const r = await GET(`/api/analytics?date_from=${f}&date_to=${t}`);
  const maxW = Math.max(1, ...r.centres.map(c => c.work_s + c.pause_s));
  app().innerHTML = `<div class="row between"><h1>Analitika</h1>
    <form id="af" class="inline"><label>Nuo<input type="date" name="f" value="${esc(f)}" id="af-f"></label><label>Iki<input type="date" name="t" value="${esc(t)}" id="af-t"></label>
    <button class="ghost">Rodyti</button><button class="ghost" type="button" id="af-all">Visas laikas</button></form></div>
  <div class="tiles">
    <div class="tile"><span class="muted">Darbo laikas</span><b>${hm(r.totals.work_s)}</b></div>
    <div class="tile"><span class="muted">Neplanuotos pauzės</span><b>${hm(r.totals.pause_s)}</b></div>
    <div class="tile"><span class="muted">Užbaigta užduočių</span><b>${r.totals.tasks_done}</b></div>
    <div class="tile"><span class="muted">Brokas, vnt.</span><b>${r.totals.scrap}</b></div></div>
  <div class="card"><h2>Gamybos barai</h2>${simple(r.areas, ["Baras", "Darbo laikas", "Prastovos", "Užbaigta užduočių", "Brokas"], a =>
      [esc(a.name), hm(a.work_s), `${hm(a.pause_s)} <span class="muted">${Math.round(100 * a.pause_share)}%</span>`, a.tasks_done, a.scrap || "—"])}</div>
  <div class="card"><h2>Darbo centrai</h2><div class="tbl"><table><thead><tr><th>Centras</th><th>Darbas / prastovos</th><th>Darbo laikas</th><th>Prastovos</th><th>Užduotys</th><th>Faktas / norma</th><th>Brokas</th></tr></thead>
    <tbody>${r.centres.map(c => `<tr><td><b class="mono">${esc(c.code)}</b> ${esc(c.name)}<br><span class="muted">${esc(c.area_name || "Be baro")}</span></td>
      <td><div class="hbar" style="width:${Math.max(8, 100 * (c.work_s + c.pause_s) / maxW)}%"><i class="w" style="flex:${c.work_s}"></i><i class="p" style="flex:${c.pause_s}"></i></div></td>
      <td class="num">${hm(c.work_s)}</td><td class="num">${hm(c.pause_s)} <span class="muted">${Math.round(100 * c.pause_share)}%</span></td>
      <td class="num">${c.tasks_done}</td><td class="num ${c.norm_ratio > 1.15 ? "s-late" : ""}">${c.norm_ratio ? c.norm_ratio.toFixed(2) : "—"}</td>
      <td class="num">${c.scrap ? `${c.scrap} (${Math.round(100 * c.scrap_share)}%)` : "—"}</td></tr>`).join("") || `<tr><td colspan="7" class="muted">Duomenų nėra.</td></tr>`}</tbody></table></div>
    <p class="muted">Faktas / norma > 1 – darbas užtruko ilgiau nei normuota. Prastovose planuotos pauzės (pertrauka, pamainos pabaiga) neįskaičiuotos.</p></div>
  <div class="grid2">
    <div class="card"><h2>Pauzės pagal priežastį</h2>${simple(r.pauses, ["Priežastis", "Kartai", "Trukmė"], p => [esc(p.label) + (p.planned ? ' <span class="muted">(planuota)</span>' : ""), p.count, hm(p.seconds)])}</div>
    <div class="card"><h2>Laukimas prieš operaciją</h2>${simple(r.waits, ["Centras", "Kartai", "Mediana", "Iš viso"], w => [`<span class="mono">${esc(w.code)}</span> ${esc(w.name)}`, w.count, hm(w.median_s), hm(w.total_s)])}
      <p class="muted">Laikas nuo ankstesnės maršruto operacijos pabaigos iki šios pradžios.</p></div>
    <div class="card"><h2>Etapai: planas ir faktas</h2>${simple(r.phases, ["Etapas", "Baigta", "Vėlavo", "Vid. planas, d.", "Vid. faktas, d."], p => [esc(p.label), p.count, p.late, p.avg_plan_d, p.avg_fact_d])}</div>
    <div class="card"><h2>Tiekėjų patikimumas</h2>${simple(r.suppliers, ["Tiekėjas", "Eilučių", "Gauta", "Gauta vėliau", "Vid. vėlavimas, d.", "Dabar vėluoja"], x => [esc(x.supplier), x.lines, x.received, x.late, x.avg_delay_d || "—", x.open_late ? `<span class="s-late">${x.open_late}</span>` : 0])}
      <p class="muted">Gauta vėliau – gavimo data vėlesnė už tiekėjo patvirtintą.</p></div>
    <div class="card"><h2>Neatitiktys pagal kategoriją</h2>${simple(r.ncr, ["Kategorija", "Kiekis"], n => [esc((S.meta.ncr_categories.find(c => c.key === n.category) || {}).label || n.category), n.n])}</div>
  </div>
  <div class="card"><h2>Labiausiai normą viršijusios užduotys</h2>${simple(r.worst_tasks, ["Centras", "Užduotis", "Norma", "Faktas", "Santykis"], w => [`<span class="mono">${esc(w.centre)}</span>`, esc(w.name), hm(w.norm_s), hm(w.fact_s), w.ratio ? w.ratio.toFixed(2) : "—"])}</div>`;
  $("#af").onsubmit = e => { e.preventDefault(); const d = formData(e.target); sessionStorage.setItem("pf.af", d.f); sessionStorage.setItem("pf.at", d.t); pageAnalytics(); };
  $("#af-all").onclick = () => { sessionStorage.removeItem("pf.af"); sessionStorage.removeItem("pf.at"); pageAnalytics(); };
}
function simple(list, heads, fn) {
  if (!list.length) return `<p class="muted">Duomenų nėra.</p>`;
  return `<div class="tbl"><table><thead><tr>${heads.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${list.map(x => `<tr>${fn(x).map(v => `<td>${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

// ---------- duomenys: brėžiniai ir importas ----------
async function pageData() {
  const list = await GET("/api/drawings");
  app().innerHTML = `<h1>Duomenys</h1>
  <div class="card"><h2>Maršrutų importas iš CSV</h2>
    <p class="muted">Viena eilutė – viena mazgo operacija. Projektai ir mazgai sukuriami, jei jų nėra. Pirmiausia patikrinkite – įrašoma tik be klaidų.
      <a href="/api/import/template">Atsisiųsti šabloną</a></p>
    <form id="imp" class="inline"><input type="file" name="file" accept=".csv,text/csv" required id="imp-file">
      <button class="ghost" name="dry" value="1">Patikrinti</button><button name="dry" value="0">Importuoti</button></form>
    <div id="imp-res"></div></div>
  ${can("docs") ? `<div class="card"><h2>Įkelti brėžinį</h2>
    <form id="dup" class="inline"><label>Numeris<input name="number" required id="du-no"></label><label>Revizija<input name="revision" required style="width:70px" id="du-rev"></label>
      <label>Pavadinimas<input name="title" id="du-title"></label><input type="file" name="file" accept="application/pdf" required id="du-file"><button>Įkelti</button></form>
    <p class="muted">Įkėlus naują reviziją, užduotys su senesne terminale užrakinamos, kol meistras patvirtina.</p></div>` : ""}
  <div class="card"><h2>Brėžiniai</h2>${simple(list, ["Numeris", "Revizija", "Pavadinimas", "Įkelta", "Galioja"], d => [
    `<a href="/api/drawings/${encodeURIComponent(d.number)}/file?rev=${encodeURIComponent(d.revision)}" target="_blank" class="mono">${esc(d.number)}</a>`,
    esc(d.revision), esc(d.title), `${dt(d.uploaded_at)} <span class="muted">${esc(d.uploader || "")}</span>`, d.current ? pill("baigta", "galioja") : '<span class="muted">sena</span>'])}</div>`;
  let dry = 1;
  $$("#imp button").forEach(b => b.onclick = () => (dry = +b.value));
  $("#imp").onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(e.target); fd.set("dry_run", String(dry));
    const r = await act(() => api("POST", "/api/import", fd, true));
    $("#imp-res").innerHTML = r.errors.length
      ? `<p class="lock">Rasta klaidų: ${r.errors.length}. Niekas neįrašyta.</p><ul>${r.errors.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`
      : dry ? `<p>Klaidų nėra: ${r.rows} eilučių. Galima importuoti.</p>`
      : `<p>Importuota: ${r.tasks_new} operacijų, nauji projektai ${r.projects_new}, nauji mazgai ${r.assemblies_new}.</p>`;
  };
  const du = $("#dup");
  if (du) du.onsubmit = async e => { e.preventDefault(); await act(() => api("POST", "/api/drawings", new FormData(du), true), "Brėžinys įkeltas"); pageData(); };
}

// ---------- administravimas ----------
async function pageAdmin() {
  const [users, centres, areas] = await Promise.all([GET("/api/users"), GET("/api/centres?all=1"), GET("/api/areas")]);
  const masters = users.filter(u => u.active && ["meistras", "admin", "vadovas"].includes(u.role));
  const areaOpts = sel => opt(areas.map(a => ({ id: a.id, name: a.name })), sel, "Be baro");
  app().innerHTML = `<h1>Administravimas</h1>
  <div class="card"><h2>Vartotojai</h2><div class="tbl"><table><thead><tr><th>Vardas</th><th>Prisijungimas</th><th>Rolė</th><th>Darbo centrai</th><th>PIN</th><th>Aktyvus</th><th></th></tr></thead>
    <tbody>${users.map(u => `<tr class="${u.active ? "" : "dim"}"><td>${esc(u.name)}</td><td class="mono">${esc(u.login)}</td>
      <td><select data-u="${u.id}" data-f="role" id="u-r-${u.id}">${opt(S.meta.roles, u.role)}</select></td>
      <td><input data-u="${u.id}" data-f="centres" value="${esc(u.centres.join(","))}" placeholder="visi" title="Centrų (SV-01) arba barų (SVB) kodai per kablelį" style="width:140px" id="u-c-${u.id}"></td>
      <td>${u.has_pin ? "yra" : "—"}</td><td><input type="checkbox" data-u="${u.id}" data-f="active" ${u.active ? "checked" : ""} id="u-a-${u.id}"></td>
      <td><button class="small ghost" data-pw="${u.id}">Slaptažodis / PIN</button></td></tr>`).join("")}</tbody></table></div>
    <form id="nu" class="inline"><label>Vardas<input name="name" required id="nu-name"></label><label>Prisijungimas<input name="login" required id="nu-login"></label>
      <label>Rolė<select name="role" id="nu-role">${opt(S.meta.roles, "operatorius")}</select></label><label>Slaptažodis<input name="password" type="password" required id="nu-pw"></label>
      <label>PIN<input name="pin" inputmode="numeric" style="width:80px" id="nu-pin"></label><label>Centrai ar barai<input name="centres" placeholder="SVB arba SV-01,SV-02" id="nu-c"></label>
      <button class="ghost">Pridėti vartotoją</button></form></div>
  <div class="card"><h2>Gamybos barai</h2>
    <p class="muted">Baro kodą galima priskirti vartotojui vietoje atskirų centrų – tada jis mato visus to baro centrus, ir naujus taip pat.</p>
    <div class="tbl"><table><thead><tr><th>Kodas</th><th>Pavadinimas</th><th>Meistras</th><th>Centrų</th><th>Aktyvus</th></tr></thead>
    <tbody>${areas.map(a => `<tr class="${a.active ? "" : "dim"}"><td class="mono">${esc(a.code)}</td>
      <td><input data-ar="${a.id}" data-f="name" value="${esc(a.name)}" style="width:280px" id="ar-n-${a.id}"></td>
      <td><select data-ar="${a.id}" data-f="master_id" id="ar-m-${a.id}">${opt(masters, a.master_id, "—")}</select></td>
      <td class="num">${a.centres}</td><td><input type="checkbox" data-ar="${a.id}" data-f="active" ${a.active ? "checked" : ""} id="ar-a-${a.id}"></td></tr>`).join("")
      || `<tr><td colspan="5" class="muted">Barų dar nėra.</td></tr>`}</tbody></table></div>
    <form id="na" class="inline"><label>Kodas<input name="code" required style="width:90px" id="nar-code"></label><label>Pavadinimas<input name="name" required id="nar-name"></label>
      <label>Meistras<select name="master_id" id="nar-m">${opt(masters, "", "—")}</select></label><button class="ghost">Pridėti barą</button></form></div>
  <div class="card"><h2>Darbo centrai</h2><div class="tbl"><table><thead><tr><th>Kodas</th><th>Pavadinimas</th><th>Baras</th><th>Rūšis</th><th>Rankinis</th><th>Griežta eilė</th><th>Aktyvus</th></tr></thead>
    <tbody>${centres.map(c => `<tr class="${c.active ? "" : "dim"}"><td class="mono">${esc(c.code)}</td><td>${esc(c.name)}</td>
      <td><select data-c="${c.id}" data-f="area_id" id="c-ar-${c.id}">${areaOpts(c.area_id)}</select></td>
      <td><select data-c="${c.id}" data-f="kind" id="c-k-${c.id}">${opt(S.meta.centre_kinds, c.kind)}</select></td>
      ${["manual", "strict_order", "active"].map(f => `<td><input type="checkbox" data-c="${c.id}" data-f="${f}" ${c[f] ? "checked" : ""} id="c-${f}-${c.id}"></td>`).join("")}</tr>`).join("")}</tbody></table></div>
    <form id="nc" class="inline"><label>Kodas<input name="code" required style="width:100px" id="nc-code"></label><label>Pavadinimas<input name="name" required id="nc-name"></label>
      <label>Baras<select name="area_id" id="nc-area">${areaOpts("")}</select></label>
      <label>Rūšis<select name="kind" id="nc-kind">${opt(S.meta.centre_kinds)}</select></label><button class="ghost">Pridėti centrą</button></form></div>`;
  const splitC = v => v.split(",").map(x => x.trim()).filter(Boolean);
  $$("[data-u]").forEach(el => el.onchange = async () => {
    const f = el.dataset.f;
    const v = f === "active" ? el.checked : f === "centres" ? splitC(el.value) : el.value;
    try { await act(() => PUT(`/api/users/${el.dataset.u}`, { [f]: v }), "Įrašyta"); } finally { pageAdmin(); }
  });
  $$("[data-c]").forEach(el => el.onchange = async () => {
    const f = el.dataset.f;
    await act(() => PUT(`/api/centres/${el.dataset.c}`, { [f]: el.type === "checkbox" ? (el.checked ? 1 : 0) : f === "area_id" ? (el.value ? +el.value : null) : el.value }), "Įrašyta"); pageAdmin();
  });
  $$("[data-pw]").forEach(b => b.onclick = () => modal(`<h2>Slaptažodis ir PIN</h2>
    <label>Naujas slaptažodis<input id="m-pw" type="password"></label><label>Naujas PIN (tuščias – nekeisti, „-“ – pašalinti)<input id="m-pin" inputmode="numeric"></label>
    <div class="row"><button id="m-ok">Įrašyti</button><button class="ghost" id="m-x">Atšaukti</button></div>`, () => {
    $("#m-x").onclick = closeModal;
    $("#m-ok").onclick = async () => {
      const body = {}; const pw = $("#m-pw").value, pin = $("#m-pin").value;
      if (pw) body.password = pw; if (pin) body.pin = pin === "-" ? "" : pin;
      await act(() => PUT(`/api/users/${b.dataset.pw}`, body), "Įrašyta"); closeModal(); pageAdmin();
    };
  }));
  $("#nu").onsubmit = async e => { e.preventDefault(); const d = formData(e.target); d.centres = splitC(d.centres || ""); await act(() => POST("/api/users", d), "Vartotojas sukurtas"); pageAdmin(); };
  $("#nc").onsubmit = async e => { e.preventDefault(); const d = formData(e.target); d.area_id = d.area_id ? +d.area_id : null; await act(() => POST("/api/centres", d), "Centras sukurtas"); pageAdmin(); };
  $$("[data-ar]").forEach(el => el.onchange = async () => {
    const f = el.dataset.f;
    const v = f === "active" ? (el.checked ? 1 : 0) : f === "master_id" ? (el.value ? +el.value : null) : el.value;
    try { await act(() => PUT(`/api/areas/${el.dataset.ar}`, { [f]: v }), "Įrašyta"); } finally { pageAdmin(); }
  });
  $("#na").onsubmit = async e => { e.preventDefault(); const d = formData(e.target); d.master_id = d.master_id ? +d.master_id : null; await act(() => POST("/api/areas", d), "Baras sukurtas"); pageAdmin(); };
}

// ---------- komponentų pirkimai ----------
const compStatusCls = st => ({ reikia: "atvira", uzsakyta: "laukia", patvirtinta: "gali", dalinai: "pristabdyta", gauta: "baigta", atsaukta: "tuscia" }[st] || st);
const fmtQ = q => (Math.round(q * 1000) / 1000).toLocaleString("lt-LT");

function compSummaryLine(sm) {
  if (!sm.total) return "";
  return `<div class="row"><span>Gauta <b>${sm.received_pct}%</b> (${sm.by_status.gauta} iš ${sm.total})</span>
    ${sm.late ? pill("late", `vėluoja ${sm.late}`) : ""} ${sm.risk ? pill("pristabdyta", `rizika ${sm.risk}`) : ""}
    ${sm.by_status.reikia ? pill("atvira", `neužsakyta ${sm.by_status.reikia}`) : ""}</div>`;
}

function compFlags(c) {
  return [c.late ? `<div class="s-late">⚠ vėluoja: žadėta ${esc(c.promised_date)}</div>` : "",
    c.overdue_need ? `<div class="s-late">⚠ reikėjo iki ${esc(c.need_date)}</div>` : "",
    c.risk && !c.late ? `<div class="warn">⚠ ${c.promised_date && c.need_date && c.promised_date > c.need_date ? "atvyks vėliau nei reikia" : "reikia greitai, data nepatvirtinta"}</div>` : ""].join("");
}

function compTable(rows, o = {}) {
  const act = c => {
    if (o.compact) return "";
    const open = !["gauta", "atsaukta"].includes(c.status);
    return `<td class="row" style="flex-wrap:nowrap">${open && can("receive") ? `<button class="small" data-recv="${c.id}">Gauti</button>` : ""}
      ${can("purchase") ? `<button class="small ghost" data-edit="${c.id}">Keisti</button>` : ""}</td>`;
  };
  return `<div class="tbl"><table><thead><tr>${o.compact ? "" : "<th>Projektas</th>"}<th>Mazgas</th><th>Komponentas</th><th>Gauta</th><th>Tiekėjas</th><th>Užsakymas</th>
    <th>Patvirtinta</th><th>Reikia iki</th><th>Būsena</th>${o.compact ? "" : "<th></th>"}</tr></thead><tbody>
    ${rows.map(c => {
      const pct = c.qty ? Math.min(100, Math.round(100 * c.qty_received / c.qty)) : 0;
      return `<tr class="${c.status === "atsaukta" ? "dim" : ""}">
      ${o.compact ? "" : `<td><a href="#/p/${c.project_id}" class="mono">${esc(c.project_code)}</a></td>`}
      <td>${esc(c.assembly_code || "projektui")}</td>
      <td><b>${esc(c.name)}</b><br><span class="muted mono">${esc(c.item_no)}</span> <span class="muted">${esc(c.spec)}</span></td>
      <td class="num"><div class="prog"><i style="width:${pct}%"></i></div>${fmtQ(c.qty_received)} / ${fmtQ(c.qty)} ${esc(c.unit)}${c.received_date ? `<br><span class="muted">${esc(c.received_date)}</span>` : ""}</td>
      <td>${esc(c.supplier || "—")}</td>
      <td class="num">${c.po_no ? `<span class="mono">${esc(c.po_no)}${c.po_line ? "/" + esc(c.po_line) : ""}</span><br><span class="muted">${esc(c.ordered_date || "")}</span>` : "—"}</td>
      <td class="num">${esc(c.promised_date || "—")}</td><td class="num">${esc(c.need_date || "—")}</td>
      <td>${pill(compStatusCls(c.status), c.status_label)}${compFlags(c)}</td>${act(c)}</tr>`;
    }).join("") || `<tr><td colspan="10" class="muted">Eilučių nėra.</td></tr>`}</tbody></table></div>`;
}

async function pageComponents(projectId) {
  const key = "pf.comp";
  let f = {}; try { f = JSON.parse(sessionStorage.getItem(key) || "{}"); } catch { f = {}; }
  if (projectId) f.project_id = projectId;
  const projects = await GET("/api/projects?all=1");
  const draw = async () => {
    const q = new URLSearchParams();
    if (f.project_id) q.set("project_id", f.project_id);
    if (f.status) q.set("status", f.status);
    if (f.supplier) q.set("supplier", f.supplier);
    if (f.problems) q.set("problems", "1");
    const [r, rec] = await Promise.all([GET(`/api/components?${q}`), GET(`/api/components/receipts?limit=12${f.project_id ? `&project_id=${f.project_id}` : ""}`)]);
    const sm = r.summary, b = sm.by_status;
    const waiting = b.uzsakyta + b.patvirtinta + b.dalinai;
    app().innerHTML = `<div class="row between"><h1>Komponentų pirkimai</h1>
      <span class="muted">atnaujinta ${new Date(r.now).toLocaleTimeString("lt-LT")} · kas 30 s</span></div>
    <p class="muted">Šaltinis kol kas – įvedimas ranka ir importas iš ERP eksporto. Prijungus D365, eilutės ir gavimai ateis automatiškai.</p>
    <div class="tiles">
      <div class="tile"><span class="muted">Eilučių</span><b>${sm.total}</b></div>
      <div class="tile"><span class="muted">Neužsakyta</span><b class="${b.reikia ? "s-late" : ""}">${b.reikia}</b></div>
      <div class="tile"><span class="muted">Laukiama</span><b>${waiting}</b></div>
      <div class="tile"><span class="muted">Vėluoja</span><b class="${sm.late ? "s-late" : ""}">${sm.late}</b></div>
      <div class="tile"><span class="muted">Rizika terminui</span><b class="${sm.risk ? "warn" : ""}">${sm.risk}</b></div>
      <div class="tile"><span class="muted">Gauta</span><b>${sm.received_pct}%</b></div></div>
    <form id="cf" class="inline card">
      <label>Projektas<select name="project_id" id="cf-p">${opt(projects.map(p => ({ id: p.id, name: `${p.code} ${p.name}` })), f.project_id, "Visi")}</select></label>
      <label>Būsena<select name="status" id="cf-s"><option value="">Visos</option><option value="open" ${f.status === "open" ? "selected" : ""}>Dar negautos</option>${opt(r.statuses, f.status)}</select></label>
      <label>Tiekėjas<select name="supplier" id="cf-t">${opt(r.suppliers.map(x => ({ key: x, label: x })), f.supplier, "Visi")}</select></label>
      <label class="row" style="display:flex"><input type="checkbox" name="problems" id="cf-pr" ${f.problems ? "checked" : ""}> tik vėluojančios ir rizikingos</label>
      ${can("purchase") ? `<button type="button" id="cnew">+ Nauja eilutė</button>` : ""}</form>
    ${compTable(r.rows)}
    <div class="grid2">
      <div class="card"><h2>Paskutiniai gavimai</h2>${rec.length ? rec.map(x => `<div><b>${fmtQ(x.qty)} ${esc(x.unit)}</b> ${esc(x.name)}
        <span class="muted">· ${esc(x.project_code)} ${esc(x.assembly_code || "")} · ${dt(x.at)} · ${esc(x.user_name || x.source)}${x.qty_received < x.qty_total ? ` · iš viso ${fmtQ(x.qty_received)}/${fmtQ(x.qty_total)}` : ""}</span></div>`).join("") : `<p class="muted">Gavimų dar nėra.</p>`}</div>
      ${can("purchase") ? `<div class="card"><h2>Importas iš ERP eksporto (CSV)</h2>
        <p class="muted">Eilutė atpažįstama pagal užsakymo nr. ir eilutę: rasta atnaujinama, padidėjęs gautas kiekis užregistruojamas kaip gavimas. <a href="/api/components/template">Šablonas</a></p>
        <form id="cimp" class="inline"><input type="file" name="file" accept=".csv,text/csv" required id="cimp-f">
          <button class="ghost" value="1">Patikrinti</button><button value="0">Importuoti</button></form><div id="cimp-res"></div></div>` : ""}
    </div>`;
    $$("#cf select, #cf input[type=checkbox]").forEach(el => el.onchange = () => {
      const d = formData($("#cf")); f = { project_id: d.project_id || "", status: d.status || "", supplier: d.supplier || "", problems: !!d.problems };
      sessionStorage.setItem(key, JSON.stringify(f));
      if (projectId && String(f.project_id) !== String(projectId)) { location.hash = "#/komponentai"; return; }
      draw();
    });
    const cn = $("#cnew"); if (cn) cn.onclick = () => compForm(null, projects, draw, f.project_id);
    $$("[data-edit]").forEach(b2 => b2.onclick = () => compForm(r.rows.find(c => c.id === +b2.dataset.edit), projects, draw));
    $$("[data-recv]").forEach(b2 => b2.onclick = () => recvForm(r.rows.find(c => c.id === +b2.dataset.recv), draw));
    const ci = $("#cimp");
    if (ci) {
      let dry = 1; $$("#cimp button").forEach(x => x.onclick = () => (dry = +x.value));
      ci.onsubmit = async e => {
        e.preventDefault(); const fd = new FormData(ci); fd.set("dry_run", String(dry));
        const res = await act(() => api("POST", "/api/components/import", fd, true));
        const box = res.errors.length ? `<p class="lock">Rasta klaidų: ${res.errors.length}. Niekas neįrašyta.</p><ul>${res.errors.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`
          : dry ? `<p>Klaidų nėra: ${res.rows} eilučių. Galima importuoti.</p>`
          : `<p>Importuota: naujų ${res.created}, atnaujinta ${res.updated}, gavimų ${res.receipts}.</p>`;
        if (!dry && !res.errors.length) await draw();
        $("#cimp-res").innerHTML = box;
      };
    }
  };
  await draw();
  S.timers.push(setInterval(() => { if ($("#modal").hidden && !document.activeElement?.closest("form")) draw(); }, 30000));
}

function recvForm(c, after) {
  const left = c.qty - c.qty_received;
  modal(`<h2>Gauti: ${esc(c.name)}</h2>
    <p class="muted">${esc(c.project_code)} ${esc(c.assembly_code || "")} · ${esc(c.supplier)} · užsakymas ${esc(c.po_no || "—")} · gauta ${fmtQ(c.qty_received)} iš ${fmtQ(c.qty)} ${esc(c.unit)}</p>
    <label>Gautas kiekis, ${esc(c.unit)}<input id="rv-q" type="number" min="0" step="any" value="${left}"></label>
    <label>Pastaba<input id="rv-n" placeholder="pvz. važtaraštis, pažeista pakuotė"></label>
    <div class="row"><button id="rv-ok">Užregistruoti gavimą</button><button class="ghost" id="rv-x">Atšaukti</button></div>`, () => {
    $("#rv-x").onclick = closeModal;
    $("#rv-ok").onclick = async () => {
      await act(() => POST(`/api/components/${c.id}/receive`, { qty: +$("#rv-q").value, note: $("#rv-n").value }), "Gavimas užregistruotas");
      closeModal(); after();
    };
  });
}

function compForm(c, projects, after, defProject) {
  const v = c || { project_id: defProject ? +defProject : (projects[0] || {}).id, unit: "vnt", qty: 1 };
  const fld = (name, label, extra = "") => `<label>${label}<input name="${name}" value="${esc(v[name] ?? "")}" ${extra} id="cm-${name}"></label>`;
  modal(`<h2>${c ? "Keisti pirkimo eilutę" : "Nauja pirkimo eilutė"}</h2>
    <form id="cm" class="grid2" style="gap:10px">
      <label>Projektas<select name="project_id" id="cm-project_id">${opt(projects.map(p => ({ id: p.id, name: `${p.code} ${p.name}` })), v.project_id)}</select></label>
      <label>Mazgas<select name="assembly_id" id="cm-assembly_id"><option value="">Visam projektui</option></select></label>
      ${fld("name", "Pavadinimas", "required")}${fld("item_no", "Prekės kodas")}${fld("spec", "Specifikacija")}
      ${fld("qty", "Kiekis", 'type="number" step="any" min="0"')}${fld("unit", "Vnt.")}${fld("supplier", "Tiekėjas")}
      ${fld("po_no", "Užsakymo nr.")}${fld("po_line", "Eilutė")}
      ${fld("ordered_date", "Užsakyta", 'type="date"')}${fld("promised_date", "Tiekėjo patvirtinta data", 'type="date"')}
      ${fld("need_date", "Reikia iki", 'type="date"')}${fld("location", "Sandėlio vieta")}
      <label style="grid-column:1/-1">Pastaba<input name="note" value="${esc(v.note || "")}" id="cm-note"></label>
    </form>
    <div class="row between"><div class="row"><button id="cm-ok">Įrašyti</button><button class="ghost" id="cm-x">Atšaukti</button></div>
      ${c && c.qty_received === 0 ? `<button class="ghost" id="cm-cancel">${c.cancelled ? "Grąžinti eilutę" : "Atšaukti eilutę"}</button>` : ""}</div>`, async () => {
    const loadAsm = async pid => {
      const p = pid ? await GET(`/api/projects/${pid}`) : { assemblies: [] };
      $("#cm-assembly_id").innerHTML = `<option value="">Visam projektui</option>` + p.assemblies.map(a => `<option value="${a.id}" ${a.id === v.assembly_id ? "selected" : ""}>${esc(a.code)} ${esc(a.name)}</option>`).join("");
    };
    await loadAsm(v.project_id);
    $("#cm-project_id").onchange = e => { v.assembly_id = null; loadAsm(e.target.value); };
    $("#cm-x").onclick = closeModal;
    const cc = $("#cm-cancel");
    if (cc) cc.onclick = async () => { await act(() => POST(`/api/components/${c.id}/cancel`, { on: !c.cancelled }), "Įrašyta"); closeModal(); after(); };
    $("#cm-ok").onclick = async () => {
      const d = formData($("#cm"));
      d.project_id = +d.project_id; d.assembly_id = d.assembly_id ? +d.assembly_id : null; d.qty = +d.qty;
      await act(() => c ? PUT(`/api/components/${c.id}`, d) : POST("/api/components", d), "Įrašyta");
      closeModal(); after();
    };
  });
}

route();
