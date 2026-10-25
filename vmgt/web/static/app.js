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
  [/^#\/p\/(\d+)(?:\/(\w+))?$/, pageProject],
  [/^#\/uzduotys$/, pageMyActions],
  [/^#\/apkrova$/, pageCapacity],
  [/^#\/m\/(\d+)$/, pageMeeting],
  [/^#\/m\/(naujas)\/(\d+)$/, pageMeetingEdit],
  [/^#\/m\/(\d+)\/keisti$/, pageMeetingEdit],
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
    ["#/", "Projektai", "view"], ["#/uzduotys", "Užduotys", null], ["#/apkrova", "Apkrova", "view"], ["#/cechas", "Cechas", "view"], ["#/planas", "Planas", "plan"],
    ["#/t", "Terminalas", "execute"], ["#/ncr", "Neatitiktys", "ncr_report"],
    ["#/komponentai", "Komponentai", "view"],
    ["#/analitika", "Analitika", "view"], ["#/duomenys", "Duomenys", "tasks"], ["#/admin", "Administravimas", "admin"],
  ].filter(x => !x[2] || can(x[2]));
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
    <thead><tr><th>Sveikata</th><th>Projektas</th><th>Užsakovas</th><th>Vadovas</th><th>Terminas</th><th>Būsena</th><th>Vykdomi etapai</th><th>Užduotys</th><th>Neatitiktys</th></tr></thead>
    <tbody>${list.map(p => {
      const late = p.due_date && p.due_date < today() && p.status !== "baigtas";
      const pct = p.tasks_total ? Math.round(100 * p.tasks_done / p.tasks_total) : 0;
      const hd = p.health, dn = { schedule: "Terminai", execution: "Užduotys ir gamyba", components: "Komponentai", quality: "Kokybė" };
      return `<tr class="click" data-id="${p.id}">
        <td>${healthBadge(hd)}<div class="dims">${Object.entries(hd.dims).map(([k, v]) => dot(v, dn[k])).join("")}</div></td>
        <td><b class="mono">${esc(p.code)}</b><br>${esc(p.name)}</td><td>${esc(p.customer)}</td><td>${esc(p.manager_name || "—")}</td>
        <td class="num ${late ? "s-late" : ""}">${esc(p.due_date || "—")}${late ? " ⚠" : ""}</td>
        <td>${pill(p.status, p.status_label)} <span class="muted">P${p.priority}</span></td>
        <td>${esc(p.active_phases.join(", ") || "—")}</td>
        <td><div class="prog" title="${p.tasks_done} iš ${p.tasks_total}"><i style="width:${pct}%"></i></div><span class="muted num">${p.tasks_done}/${p.tasks_total}</span></td>
        <td>${p.ncr_open ? pill("atvira", p.ncr_open + " atv.") : "—"}</td></tr>`;
    }).join("") || `<tr><td colspan="9" class="muted">Projektų nėra.</td></tr>`}</tbody></table></div>
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
async function pageProject(pid, tab) {
  tab = tab || "sveikata";
  const [p, users, centres, h] = await Promise.all([GET(`/api/projects/${pid}`), GET("/api/users"), GET("/api/centres?all=1"), GET(`/api/projects/${pid}/health`)]);
  const active = users.filter(u => u.active);
  const ed = can("projects"), edt = can("tasks");
  const asmName = id => { const a = p.assemblies.find(x => x.id === id); return a ? `${a.code} ${a.name}` : "Visas projektas"; };
  const tabs = [["sveikata", "Sveikata"], ["planas", "Planas"], ["uzduotys", "Užduotys"], ["susitikimai", "Susitikimai"],
    ["gamyba", "Gamyba"], ["komponentai", "Komponentai"], ["neatitiktys", "Neatitiktys"]];
  const extra = {};
  if (tab === "uzduotys") extra.actions = await GET(`/api/actions?project_id=${pid}`);
  if (tab === "susitikimai") extra.meetings = await GET(`/api/meetings?project_id=${pid}`);
  if (tab === "planas") extra.depts = await GET("/api/departments");
  const deptOpts = sel => opt((extra.depts || []).map(d => ({ id: d.id, name: d.name })), sel, "pagal etapą");
  if (tab === "sveikata") extra.soon = (await GET(`/api/actions?project_id=${pid}&status=open`)).filter(x => x.due_date && x.due_date <= addDays(today(), 7));

  const body = {
    sveikata: () => healthView(h, p, extra.soon),
    planas: () => `${ed ? `<form id="pedit" class="inline card">
      <label>Būsena<select name="status" id="pe-status">${opt(S.meta.project_statuses, p.status)}</select></label>
      <label>Vadovas<select name="manager_id" id="pe-man">${opt(active, p.manager_id, "—")}</select></label>
      <label>Terminas<input type="date" name="due_date" value="${esc(p.due_date || "")}" id="pe-due"></label>
      <label>Prioritetas<input type="number" min="1" max="5" name="priority" value="${p.priority}" id="pe-prio" style="width:70px"></label>
      <button class="ghost">Įrašyti</button></form>` : ""}
  <div class="card"><div class="row between"><h2>Etapų planas</h2><span class="muted">${p.phases_done} iš ${p.phases_total} baigta</span></div>
    ${gantt(p.phases, asmName)}</div>
  <div class="card"><h2>Etapai ir atsakingieji</h2>
    <p class="muted">Planuojamos valandos naudojamos resursų apkrovai. Gamybos etapui nurodykite barą – jo valandos skaičiuojamos, kol mazgui nėra cecho operacijų (tada naudojamos jų normos).</p>
    <div class="tbl"><table><thead><tr><th>Mazgas</th><th>Etapas</th><th>Atsakingas</th><th>Planas</th><th>Val.</th><th>Departamentas</th><th>Faktas</th><th>Būsena</th></tr></thead>
    <tbody>${p.phases.map(ph => `<tr>
      <td>${esc(asmName(ph.assembly_id))}</td><td>${esc(ph.kind_label)}</td>
      <td>${ed ? `<select data-ph="${ph.id}" data-f="owner_id" id="ph-o-${ph.id}">${opt(active, ph.owner_id, "—")}</select>` : esc(ph.owner_name || "—")}</td>
      <td class="num">${ed ? `<input type="date" data-ph="${ph.id}" data-f="plan_start" value="${esc(ph.plan_start || "")}" id="ph-s-${ph.id}"> – <input type="date" data-ph="${ph.id}" data-f="plan_end" value="${esc(ph.plan_end || "")}" id="ph-e-${ph.id}">` : `${esc(ph.plan_start || "—")} – ${esc(ph.plan_end || "—")}`}</td>
      <td>${ed ? `<input type="number" min="0" step="1" data-ph="${ph.id}" data-f="hours" value="${ph.hours ?? ""}" style="width:80px" id="ph-h-${ph.id}">` : (ph.hours ?? "—")}</td>
      <td>${ed ? `<select data-ph="${ph.id}" data-f="department_id" id="ph-d-${ph.id}">${deptOpts(ph.department_id)}</select>` : esc(ph.department_name || "pagal etapą")}</td>
      <td class="num muted">${ph.actual_start ? dt(ph.actual_start) : "—"} – ${ph.actual_end ? dt(ph.actual_end) : ""}</td>
      <td>${pill(ph.status, ph.status)} ${ed ? phaseBtns(ph) : ""}</td></tr>`).join("") || `<tr><td colspan="8" class="muted">Etapų dar nėra.</td></tr>`}</tbody></table></div>
    ${ed ? `<form id="newph" class="inline">
      <label>Mazgas<select name="assembly_id" id="nph-a">${opt(p.assemblies.map(a => ({ id: a.id, name: `${a.code} ${a.name}` })), "", "Visas projektas")}</select></label>
      <label>Etapas<select name="kind" id="nph-k">${opt(S.meta.phase_kinds)}</select></label>
      <label>Atsakingas<select name="owner_id" id="nph-o">${opt(active, "", "—")}</select></label>
      <label>Pradžia<input type="date" name="plan_start" id="nph-s"></label><label>Pabaiga<input type="date" name="plan_end" id="nph-e"></label>
      <label>Valandos<input type="number" min="0" name="hours" style="width:90px" id="nph-h"></label>
      <label>Departamentas<select name="department_id" id="nph-d">${deptOpts("")}</select></label>
      <button class="ghost">Pridėti etapą</button></form>` : ""}</div>`,
    uzduotys: () => `<div class="card">${actionForm(p, active)}</div><div id="board"></div>`,
    susitikimai: () => `<div class="row between"><h2>Susitikimų protokolai</h2>${can("meetings") ? `<a class="btn" href="#/m/naujas/${p.id}">+ Naujas protokolas</a>` : ""}</div>
      ${simple(extra.meetings, ["Data", "Susitikimas", "Pirmininkas", "Veiksmai", "Būsena"], m => [
        `<span class="num">${esc(m.held_at.replace("T", " ").slice(0, 16))}</span>`, `<a href="#/m/${m.id}">${esc(m.title)}</a>`, esc(m.chair_name || "—"),
        `${m.actions_closed} iš ${m.actions_total} uždaryta`, pill(m.status === "patvirtintas" ? "baigta" : "laukia", m.status_label)])}`,
    gamyba: () => `<div class="card"><h2>Mazgai ir maršrutai</h2>
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
        <label>Centras<select name="centre_id" required id="nt-c-${a.id}">${byArea(centres).map(g => `<optgroup label="${esc(g.name)}">${g.items.map(c => `<option value="${c.id}">${esc(c.code)} ${esc(c.name)}</option>`).join("")}</optgroup>`).join("")}</select></label>
        <label>Operacija<input name="name" required id="nt-n-${a.id}"></label>
        <label>Kiekis<input name="qty_plan" type="number" min="1" value="${a.qty}" style="width:70px" id="nt-k-${a.id}"></label>
        <label>Norma min/vnt<input name="norm_min" type="number" step="0.1" style="width:90px" id="nt-m-${a.id}"></label>
        <label>Brėžinys<input name="drawing_no" style="width:110px" id="nt-d-${a.id}"></label><label>Rev.<input name="drawing_rev" style="width:50px" id="nt-r-${a.id}"></label>
        <button class="ghost">Pridėti operaciją</button></form>` : ""}</div>`;
    }).join("") || `<p class="muted">Mazgų dar nėra.</p>`}
    ${ed ? `<form id="newa" class="inline"><label>Mazgo kodas<input name="code" required id="na-code"></label><label>Pavadinimas<input name="name" required id="na-name"></label>
      <label>Kiekis<input name="qty" type="number" min="1" value="1" style="width:70px" id="na-qty"></label>
      <label>Laukia mazgų<input name="requires" placeholder="100,200" style="width:110px" id="na-req"></label><button class="ghost">Pridėti mazgą</button></form>` : ""}
  </div>`,
    komponentai: () => `<div class="card"><div class="row between"><h2>Komponentai</h2><a href="#/komponentai/${p.id}">Valdyti pirkimus →</a></div>
    ${compSummaryLine(p.components_summary)}
    ${p.components.length ? compTable(p.components, { compact: true }) : `<p class="muted">Pirkimo eilučių dar nėra.</p>`}</div>`,
    neatitiktys: () => `<div class="card"><h2>Neatitiktys</h2>${ncrTable(p.ncr, false)}</div>`,
  };

  app().innerHTML = `
  <div class="row between"><div><a href="#/">← Krepšelis</a><h1><span class="mono">${esc(p.code)}</span> ${esc(p.name)}</h1>
    <p class="muted">${esc(p.customer)} · terminas ${esc(p.due_date || "—")} · vadovas ${esc(p.manager_name || "—")}</p></div>
    <div class="row">${healthBadge(h)} ${pill(p.status, p.status_label)}</div></div>
  <nav class="tabs">${tabs.map(([k, l]) => `<a href="#/p/${p.id}/${k}" class="${k === tab ? "on" : ""}">${l}${
    k === "uzduotys" && h.dimensions[1].metrics.actions_overdue ? ` <span class="cnt bad">${h.dimensions[1].metrics.actions_overdue}</span>` :
    k === "neatitiktys" && p.ncr_open ? ` <span class="cnt bad">${p.ncr_open}</span>` : ""}</a>`).join("")}</nav>
  ${(body[tab] || body.sveikata)()}`;

  const reload = () => pageProject(pid, tab);
  if (tab === "uzduotys") { renderBoard($("#board"), extra.actions, { onChange: reload }); wireActionForm(p, reload); }
  if (tab === "sveikata") $$("[data-act]").forEach(el => el.onclick = () => actionModal(+el.dataset.act, reload));
  const pe = $("#pedit");
  if (pe) pe.onsubmit = async e => {
    e.preventDefault(); const d = formData(pe);
    d.manager_id = d.manager_id ? +d.manager_id : null; d.priority = +d.priority; d.due_date = d.due_date || null;
    await act(() => PUT(`/api/projects/${pid}`, d), "Įrašyta"); reload();
  };
  $$("[data-ph][data-f]").forEach(el => el.onchange = async () => {
    const v = el.value || null;
    const f = el.dataset.f;
    await act(() => PUT(`/api/phases/${el.dataset.ph}`, { [f]: ["owner_id", "department_id", "hours"].includes(f) ? (v ? +v : null) : v }), "Įrašyta");
    reload();
  });
  $$("[data-phs]").forEach(b => b.onclick = async () => { await act(() => POST(`/api/phases/${b.dataset.id}/status`, { status: b.dataset.phs })); reload(); });
  const nph = $("#newph");
  if (nph) nph.onsubmit = async e => {
    e.preventDefault(); const d = formData(nph);
    d.assembly_id = d.assembly_id ? +d.assembly_id : null; d.owner_id = d.owner_id ? +d.owner_id : null;
    d.plan_start = d.plan_start || null; d.plan_end = d.plan_end || null;
    d.hours = d.hours ? +d.hours : null; d.department_id = d.department_id ? +d.department_id : null;
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
  if (tab === "sveikata") S.timers.push(setInterval(() => { if ($("#modal").hidden && location.hash.startsWith(`#/p/${pid}`)) reload(); }, 30000));
}

const addDays = (d, n) => { const x = new Date(d + "T00:00:00Z"); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
const LEVEL_CLS = { green: "h-green", yellow: "h-yellow", red: "h-red" };
const healthBadge = h => `<span class="hbadge ${LEVEL_CLS[h.level]}" title="Sveikatos balas ${h.score}/100">● ${esc(h.level_label)} · ${h.score}</span>`;
const dot = (lvl, title) => `<i class="hdot ${LEVEL_CLS[lvl]}" title="${esc(title || "")}"></i>`;

function healthView(h, p, soon) {
  const m = k => h.dimensions.find(d => d.key === k).metrics;
  const sch = m("schedule"), ex = m("execution"), co = m("components"), q = m("quality");
  const pct = v => v == null ? "—" : `${Math.round(100 * v)}%`;
  const keyfig = {
    schedule: `Prognozė <b class="nw">${esc(sch.forecast_end || "—")}</b> · terminas <b class="nw">${esc(sch.due_date || "—")}</b><br>Etapų baigta ${sch.phases_done}/${sch.phases}${sch.slip_days ? ` · atsilikimas ${sch.slip_days} d.` : ""}`,
    execution: `Užduočių atvirų ${ex.actions_open}, vėluoja <b>${ex.actions_overdue}</b>, laukia ${ex.actions_waiting}<br>Gamyba: atlikta <b>${pct(ex.progress_actual)}</b>, planas ~${pct(ex.progress_expected)}${ex.norm_ratio ? ` · faktas/norma ${ex.norm_ratio}` : ""}`,
    components: `Gauta <b>${co.received_pct}%</b> iš ${co.lines} eil.<br>Vėluoja ${co.late}, rizika ${co.risk}, neužsakyta ${co.not_ordered}`,
    quality: `Atvirų neatitikčių <b>${q.ncr_open}</b><br>Brokas ${q.scrap} vnt.${q.scrap ? ` (${(100 * q.scrap_share).toFixed(1)}%)` : ""}`,
  };
  return `<div class="hsum ${LEVEL_CLS[h.level]}">
      <div><div class="muted">Projekto sveikata</div><div class="hbig">${esc(h.level_label)}</div><div class="muted">balas ${h.score}/100 · atnaujinta ${new Date(h.updated).toLocaleTimeString("lt-LT")}</div></div>
      <p>Bendras lygis – blogiausia sritis, kad viena kritiška problema nepasislėptų už gerų. Balas – svertinis vidurkis: terminai 35 %, užduotys ir gamyba 25 %, komponentai 25 %, kokybė 15 %.</p></div>
    <div class="hgrid">${h.dimensions.map(d => `<div class="hcard ${LEVEL_CLS[d.level]}">
      <div class="row between"><h3>${esc(d.label)}</h3><span class="hbadge ${LEVEL_CLS[d.level]}">${esc(d.level_label)}</span></div>
      <div class="hhead">${esc(d.headline)}</div>
      <div class="hfig">${keyfig[d.key]}</div>
      ${d.reasons.length ? `<ul class="hreasons">${d.reasons.map(r => `<li>${dot(r.level)}${esc(r.text)}</li>`).join("")}</ul>` : `<p class="muted">Nukrypimų nėra.</p>`}
    </div>`).join("")}</div>
    <div class="card"><h2>Artimiausių 7 dienų užduotys</h2>${soon.length ? soon.map(x => `<div class="soon" data-act="${x.id}">
      ${pill(actCls(x), x.status_label)} <b>${esc(x.title)}</b> <span class="muted">· ${esc(x.owner_name || "nepriskirta")} · iki ${esc(x.due_date)}</span>${x.overdue ? ' <span class="s-late">vėluoja</span>' : ""}</div>`).join("") : `<p class="muted">Nėra.</p>`}</div>`;
}

// ---------- projekto komandos užduotys ----------
const actCls = x => ({ nauja: "laukia", vykdoma: "gali", laukia: "pristabdyta", perziura: "vykdomas", atlikta: "baigta", atsaukta: "tuscia" }[x.status] || x.status);
const PRIO = { 1: "▲ aukštas", 2: "", 3: "▽ žemas" };

function renderBoard(el, list, o = {}) {
  let showCancelled = false;
  const draw = () => {
    const cols = S.meta.action_statuses.filter(s => showCancelled || s.key !== "atsaukta");
    el.innerHTML = `<div class="row between"><span class="muted">${list.filter(x => ["nauja", "vykdoma", "laukia", "perziura"].includes(x.status)).length} atvirų · ${list.filter(x => x.overdue).length} vėluoja</span>
      <label class="row" style="display:flex"><input type="checkbox" id="b-cx" ${showCancelled ? "checked" : ""}> rodyti atšauktas</label></div>
      <div class="board">${cols.map(c => {
        const items = list.filter(x => x.status === c.key);
        return `<div class="col"><div class="colh">${esc(c.label)} <span class="muted">${items.length}</span></div>${items.map(x => `
          <div class="acard ${x.overdue ? "late" : ""}" data-act="${x.id}" tabindex="0">
            <b>${esc(x.title)}</b>
            ${o.global ? `<div class="muted mono">${esc(x.project_code)}</div>` : ""}
            <div class="muted">${esc(x.owner_name || "nepriskirta")}${x.due_date ? ` · iki <span class="nw ${x.overdue ? "s-late" : ""}">${esc(x.due_date)}</span>` : ""}</div>
            ${x.status === "laukia" && x.wait_reason ? `<div class="warn">⏸ ${esc(x.wait_reason)}</div>` : ""}
            <div class="row" style="gap:6px">${PRIO[x.priority] ? `<span class="prio p${x.priority}">${PRIO[x.priority]}</span>` : ""}${x.meeting_id ? `<span class="muted">📋 susitikimas</span>` : ""}</div>
          </div>`).join("") || `<div class="muted empty">—</div>`}</div>`;
      }).join("")}</div>`;
    $("#b-cx", el).onchange = e => { showCancelled = e.target.checked; draw(); };
    $$("[data-act]", el).forEach(c => { c.onclick = () => actionModal(+c.dataset.act, o.onChange); c.onkeydown = e => e.key === "Enter" && c.onclick(); });
  };
  draw();
}

function actionForm(p, users) {
  if (!can("actions")) return `<p class="muted">Naujas užduotis kuria projekto vadovas ir komanda.</p>`;
  return `<form id="newact" class="inline"><label style="flex:1 1 260px">Nauja užduotis<input name="title" required placeholder="Ką reikia padaryti" id="na-title"></label>
    <label>Atsakingas<select name="owner_id" id="na-owner">${opt(users, S.me.id, "—")}</select></label>
    <label>Terminas<input type="date" name="due_date" id="na-due"></label>
    <label>Prioritetas<select name="priority" id="na-prio">${opt(S.meta.priorities, 2)}</select></label>
    <label>Mazgas<select name="assembly_id" id="na-asm">${opt(p.assemblies.map(a => ({ id: a.id, name: `${a.code} ${a.name}` })), "", "—")}</select></label>
    <button>Sukurti</button></form>`;
}
function wireActionForm(p, after) {
  const f = $("#newact"); if (!f) return;
  f.onsubmit = async e => {
    e.preventDefault(); const d = formData(f);
    d.project_id = p.id; d.owner_id = d.owner_id ? +d.owner_id : null; d.priority = +d.priority; d.assembly_id = d.assembly_id ? +d.assembly_id : null; d.due_date = d.due_date || null;
    await act(() => POST("/api/actions", d), "Užduotis sukurta"); after();
  };
}

async function actionModal(id, after) {
  const [x, users] = await Promise.all([GET(`/api/actions/${id}`), can("view") ? GET("/api/users") : []]);
  const ed = x.can_edit, full = can("actions");
  modal(`<div class="row between"><span class="muted mono">${esc(x.project_code)}${x.assembly_code ? " · " + esc(x.assembly_code) : ""}</span>${pill(actCls(x), x.status_label)}</div>
    ${full ? `<input id="ax-title" value="${esc(x.title)}" style="font-size:17px;font-weight:600">` : `<h2>${esc(x.title)}</h2>`}
    ${x.meeting_id ? `<div class="muted">Kilo iš susitikimo: <a href="#/m/${x.meeting_id}">${esc(x.meeting_title)}</a></div>` : ""}
    <div class="grid2" style="gap:10px">
      <label>Atsakingas${full ? `<select id="ax-owner">${opt(users.filter(u => u.active), x.owner_id, "—")}</select>` : `<b>${esc(x.owner_name || "—")}</b>`}</label>
      <label>Terminas${full ? `<input type="date" id="ax-due" value="${esc(x.due_date || "")}">` : `<b class="${x.overdue ? "s-late" : ""}">${esc(x.due_date || "—")}</b>`}</label>
      <label>Prioritetas${full ? `<select id="ax-prio">${opt(S.meta.priorities, x.priority)}</select>` : `<b>${esc((S.meta.priorities.find(p => p.key === x.priority) || {}).label)}</b>`}</label>
    </div>
    <label>Aprašymas${full ? `<textarea id="ax-desc">${esc(x.description)}</textarea>` : `<div>${esc(x.description || "—")}</div>`}</label>
    ${full ? `<div><button class="ghost" id="ax-save">Įrašyti pakeitimus</button></div>` : ""}
    ${x.status === "laukia" ? `<div class="warn">⏸ Laukia: ${esc(x.wait_reason)}</div>` : ""}
    ${ed && x.next.length ? `<div class="card" style="gap:8px"><b>Keisti statusą</b>
      <input id="ax-reason" placeholder="Priežastis (būtina laukiant ar atšaukiant)">
      <div class="row">${x.next.map(n => `<button class="${n.key === "atsaukta" ? "ghost" : ""}" data-st="${n.key}">→ ${esc(n.label)}</button>`).join("")}</div></div>` : ""}
    <div><b>Istorija</b><div class="hist">${x.history.map(hh => `<div><span class="muted num">${dt(hh.at)}</span> ${esc(hh.user_name || "")}:
      ${hh.kind === "status" ? (hh.from_status ? `${esc(hh.from_label)} → <b>${esc(hh.to_label)}</b>` : `<b>${esc(hh.to_label)}</b>`) + (hh.text ? ` – ${esc(hh.text)}` : "")
        : hh.kind === "edit" ? `<span class="muted">pakeista: ${esc(hh.text)}</span>` : `💬 ${esc(hh.text)}`}</div>`).join("")}</div></div>
    <div class="row"><input id="ax-com" placeholder="Komentaras" style="flex:1"><button class="ghost" id="ax-cbtn">Komentuoti</button></div>
    <div><button class="ghost" id="ax-x">Uždaryti</button></div>`, () => {
    const done = () => { closeModal(); after && after(); };
    $("#ax-x").onclick = done;
    $$("[data-st]").forEach(b => b.onclick = async () => {
      await act(() => POST(`/api/actions/${id}/status`, { status: b.dataset.st, reason: $("#ax-reason").value }), "Statusas pakeistas");
      actionModal(id, after);
    });
    $("#ax-cbtn").onclick = async () => { await act(() => POST(`/api/actions/${id}/comment`, { text: $("#ax-com").value })); actionModal(id, after); };
    const sv = $("#ax-save");
    if (sv) sv.onclick = async () => {
      await act(() => PUT(`/api/actions/${id}`, { title: $("#ax-title").value, owner_id: $("#ax-owner").value ? +$("#ax-owner").value : null,
        due_date: $("#ax-due").value || null, priority: +$("#ax-prio").value, description: $("#ax-desc").value }), "Įrašyta");
      actionModal(id, after);
    };
  });
}

async function pageMyActions() {
  const mine = (sessionStorage.getItem("pf.mine") ?? "1") === "1" || !can("view");
  const list = await GET(`/api/actions?${mine ? "owner=me&" : ""}status=`);
  app().innerHTML = `<div class="row between"><h1>${mine ? "Mano užduotys" : "Visos projektų užduotys"}</h1>
    ${can("view") ? `<div class="chips"><button class="${mine ? "" : "ghost"}" data-mine="1">Mano</button><button class="${mine ? "ghost" : ""}" data-mine="0">Visų projektų</button></div>` : ""}</div>
    <div id="board"></div>`;
  renderBoard($("#board"), list, { global: true, onChange: pageMyActions });
  $$("[data-mine]").forEach(b => b.onclick = () => { sessionStorage.setItem("pf.mine", b.dataset.mine); pageMyActions(); });
}

// ---------- susitikimų protokolai ----------
async function pageMeeting(id) {
  const m = await GET(`/api/meetings/${id}`);
  const draft = m.status === "juodrastis";
  app().innerHTML = `<div class="row between noprint"><a href="#/p/${m.project_id}/susitikimai">← ${esc(m.project_code)} susitikimai</a>
    <div class="row">${draft && can("meetings") ? `<a class="btn ghost" href="#/m/${m.id}/keisti">Redaguoti</a><button id="m-appr">Patvirtinti protokolą</button>` : ""}
      <button class="ghost" id="m-copy">Kopijuoti tekstą</button><button class="ghost" id="m-print">Spausdinti</button></div></div>
  <article class="card mom">
    <div class="row between"><div><div class="muted mono">${esc(m.project_code)} ${esc(m.project_name)}</div><h1>${esc(m.title)}</h1></div>${pill(draft ? "laukia" : "baigta", m.status_label)}</div>
    <div class="momgrid"><div><span class="muted">Data</span><b>${esc(m.held_at.replace("T", " ").slice(0, 16))}</b></div>
      <div><span class="muted">Vieta</span><b>${esc(m.location || "—")}</b></div>
      <div><span class="muted">Pirmininkas</span><b>${esc(m.chair_name || "—")}</b></div>
      <div><span class="muted">Dalyviai</span><b>${esc([...m.attendee_names, ...(m.guests ? [m.guests] : [])].join(", ") || "—")}</b></div></div>
    ${m.review.length ? `<section><h2>Ankstesnių susitikimų veiksmai</h2>${actTable(m.review, true)}</section>` : ""}
    ${m.agenda ? `<section><h2>Darbotvarkė</h2><pre class="txt">${esc(m.agenda)}</pre></section>` : ""}
    ${m.notes ? `<section><h2>Aptarta</h2><pre class="txt">${esc(m.notes)}</pre></section>` : ""}
    <section><h2>Sprendimai</h2>${m.decision_list.length ? `<ol>${m.decision_list.map(d => `<li>${esc(d)}</li>`).join("")}</ol>` : `<p class="muted">Sprendimų neužrašyta.</p>`}</section>
    <section><h2>Veiksmai</h2>${m.actions.length ? actTable(m.actions) : `<p class="muted">Veiksmų nėra.</p>`}</section>
    ${m.approved_at ? `<p class="muted">Patvirtino ${esc(m.approved_name)} ${dt(m.approved_at)}</p>` : ""}
  </article>`;
  $$("[data-act]").forEach(el => el.onclick = () => actionModal(+el.dataset.act, () => pageMeeting(id)));
  const ap = $("#m-appr"); if (ap) ap.onclick = async () => { await act(() => POST(`/api/meetings/${id}/approve`), "Protokolas patvirtintas"); pageMeeting(id); };
  $("#m-print").onclick = () => window.print();
  $("#m-copy").onclick = async () => {
    try { await navigator.clipboard.writeText(m.text); toast("Nukopijuota"); }
    catch { modal(`<h2>Protokolo tekstas</h2><textarea style="min-height:300px">${esc(m.text)}</textarea><button class="ghost" onclick="closeModal()">Uždaryti</button>`); }
  };
}
function actTable(list, withMeeting) {
  return `<div class="tbl"><table><thead><tr><th>Veiksmas</th><th>Atsakingas</th><th>Terminas</th>${withMeeting ? "<th>Iš susitikimo</th>" : ""}<th>Būsena</th></tr></thead><tbody>
    ${list.map(x => `<tr class="click" data-act="${x.id}"><td>${esc(x.title)}</td><td>${esc(x.owner_name || "—")}</td>
      <td class="num ${x.overdue ? "s-late" : ""}">${esc(x.due_date || "—")}${x.overdue ? " ⚠" : ""}</td>
      ${withMeeting ? `<td class="muted">${esc((x.meeting_at || "").slice(0, 10))} ${esc(x.meeting_title || "")}</td>` : ""}
      <td>${pill(actCls(x), x.status_label)}${x.status === "laukia" ? `<div class="warn">${esc(x.wait_reason)}</div>` : ""}</td></tr>`).join("")}</tbody></table></div>`;
}

async function pageMeetingEdit(a, b) {
  // #/m/naujas/<projektas> arba #/m/<id>/keisti
  const isNew = a === "naujas";
  const m = isNew ? { project_id: +b, title: "", held_at: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16),
    location: "", chair_id: S.me.id, attendees: [S.me.id], guests: "", agenda: "", notes: "", decisions: "", actions: [] } : await GET(`/api/meetings/${a}`);
  const [users, p, open] = await Promise.all([GET("/api/users"), GET(`/api/projects/${m.project_id}`), GET(`/api/actions?project_id=${m.project_id}&status=open`)]);
  const active = users.filter(u => u.active);
  const review = open.filter(x => x.meeting_id && x.meeting_id !== m.id);
  app().innerHTML = `<a href="#/p/${p.id}/susitikimai">← ${esc(p.code)} susitikimai</a>
  <h1>${isNew ? "Naujas susitikimo protokolas" : "Redaguoti protokolą"}</h1>
  <form id="mf" class="card" style="gap:12px">
    <div class="grid2" style="gap:10px">
      <label>Pavadinimas<input name="title" required value="${esc(m.title)}" placeholder="Savaitinis projekto susitikimas" id="mf-title"></label>
      <label>Data ir laikas<input type="datetime-local" name="held_at" required value="${esc((m.held_at || "").slice(0, 16))}" id="mf-at"></label>
      <label>Vieta<input name="location" value="${esc(m.location)}" id="mf-loc"></label>
      <label>Pirmininkas<select name="chair_id" id="mf-chair">${opt(active, m.chair_id, "—")}</select></label>
    </div>
    <fieldset><legend>Dalyviai</legend><div class="checks">${active.map(u => `<label class="chk"><input type="checkbox" name="att" value="${u.id}" ${m.attendees.includes(u.id) ? "checked" : ""} id="mf-u-${u.id}"> ${esc(u.name)} <span class="muted">${esc(u.role_label)}</span></label>`).join("")}</div>
      <label>Kiti dalyviai (užsakovas, tiekėjai)<input name="guests" value="${esc(m.guests)}" id="mf-guests"></label></fieldset>
    ${review.length ? `<fieldset><legend>Ankstesnių susitikimų veiksmai – peržiūrėkite susitikimo pradžioje</legend>${actTable(review, true)}</fieldset>` : ""}
    <label>Darbotvarkė<textarea name="agenda" id="mf-agenda">${esc(m.agenda)}</textarea></label>
    <label>Aptarta<textarea name="notes" style="min-height:110px" id="mf-notes">${esc(m.notes)}</textarea></label>
    <label>Sprendimai (po vieną eilutėje)<textarea name="decisions" id="mf-dec">${esc(m.decisions)}</textarea></label>
    <fieldset><legend>Veiksmai – kiekvienas taps projekto užduotimi</legend>
      ${m.actions.length ? `<div class="muted">Jau užregistruoti: ${m.actions.map(x => esc(x.title)).join("; ")}</div>` : ""}
      <div id="rows"></div><button type="button" class="ghost" id="addrow">+ Veiksmas</button></fieldset>
    <div class="row"><button>${isNew ? "Sukurti protokolą" : "Įrašyti"}</button><a class="btn ghost" href="#/p/${p.id}/susitikimai">Atšaukti</a></div>
  </form>`;
  let n = 0;
  const addRow = () => {
    const i = n++;
    const d = document.createElement("div");
    d.className = "inline actrow";
    d.innerHTML = `<label style="flex:1 1 240px">Veiksmas<input data-r="title" id="ar-t-${i}"></label>
      <label>Atsakingas<select data-r="owner_id" id="ar-o-${i}">${opt(active, "", "—")}</select></label>
      <label>Terminas<input type="date" data-r="due_date" id="ar-d-${i}"></label>
      <label>Prioritetas<select data-r="priority" id="ar-p-${i}">${opt(S.meta.priorities, 2)}</select></label>`;
    $("#rows").appendChild(d);
  };
  addRow(); addRow();
  $("#addrow").onclick = addRow;
  $$("[data-act]").forEach(el => el.onclick = () => actionModal(+el.dataset.act, () => {}));
  $("#mf").onsubmit = async e => {
    e.preventDefault();
    const d = formData(e.target);
    delete d.att;
    d.project_id = p.id;
    d.chair_id = d.chair_id ? +d.chair_id : null;
    d.attendees = $$("input[name=att]:checked").map(x => +x.value);
    d.new_actions = $$(".actrow").map(r => ({
      title: $("[data-r=title]", r).value, owner_id: $("[data-r=owner_id]", r).value ? +$("[data-r=owner_id]", r).value : null,
      due_date: $("[data-r=due_date]", r).value || null, priority: +$("[data-r=priority]", r).value,
    })).filter(x => x.title.trim());
    const r = await act(() => isNew ? POST("/api/meetings", d) : PUT(`/api/meetings/${m.id}`, d), "Protokolas įrašytas");
    location.hash = `#/m/${isNew ? r.id : m.id}`;
  };
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

// ---------- resursų apkrova ----------
const PROJ_COLORS = ["#2e6db4", "#c0762a", "#4f8a3c", "#8a6bbf", "#2f8f9d", "#a5542f", "#6b7d2f", "#b04a7a"];
const utilCls = u => u == null ? "u0" : u > 1 ? "u4" : u > 0.85 ? "u3" : u > 0.6 ? "u2" : u > 0 ? "u1" : "u0";

async function pageCapacity() {
  let st = { weeks: 12, basket: true, open: null };
  try { st = { ...st, ...JSON.parse(sessionStorage.getItem("pf.cap") || "{}") }; } catch {}
  const save = () => { try { sessionStorage.setItem("pf.cap", JSON.stringify(st)); } catch {} };
  const draw = async () => {
    const r = await GET(`/api/capacity?weeks=${st.weeks}&basket=${st.basket ? 1 : 0}`);
    const colorOf = {}; let ci = 0;
    r.departments.forEach(d => d.cells.forEach(c => c.projects.forEach(p => { if (!(p.code in colorOf)) colorOf[p.code] = PROJ_COLORS[ci++ % PROJ_COLORS.length]; })));
    const now = r.shortages.filter(s => !s.basket_only), withBasket = r.shortages.filter(s => s.basket_only);
    const worst = [...r.shortages].sort((a, b) => b.shortage - a.shortage)[0];
    const groups = [["office", "Biuro skyriai"], ["production", "Gamybos barai"]];
    const wk = w => r.weeks.find(x => x.start === w)?.label || w;
    app().innerHTML = `<div class="row between"><h1>Resursų apkrova</h1>
      <form id="capf" class="inline"><label>Laikotarpis<select id="cap-w">${[8, 12, 26].map(n => `<option value="${n}" ${n === st.weeks ? "selected" : ""}>${n} sav.</option>`).join("")}</select></label>
        <label class="row" style="display:flex"><input type="checkbox" id="cap-b" ${st.basket ? "checked" : ""}> įtraukti krepšelio projektus</label></form></div>
    <div class="tiles">
      <div class="tile"><span class="muted">Vykdomi projektai</span><b>${r.projects_active}</b></div>
      <div class="tile"><span class="muted">Krepšelyje (nepradėti)</span><b>${r.projects_basket}</b></div>
      <div class="tile"><span class="muted">Trūksta jau dabar</span><b class="${now.length ? "s-late" : ""}">${now.length}</b><span class="muted">savaičių departamentuose</span></div>
      <div class="tile"><span class="muted">Trūktų priėmus krepšelį</span><b class="${withBasket.length ? "warn" : ""}">${withBasket.length}</b><span class="muted">savaičių departamentuose</span></div>
      <div class="tile"><span class="muted">Didžiausias trūkumas</span><b>${worst ? `${worst.shortage} val.` : "—"}</b><span class="muted">${worst ? `${esc(worst.code)} · ${wk(worst.week)}` : ""}</span></div>
    </div>
    <div class="card"><div class="row between"><h2>Departamentų apkrova savaitėmis</h2>
      <div class="legend"><span><i class="cl u1"></i>iki 60 %</span><span><i class="cl u2"></i>60–85 %</span><span><i class="cl u3"></i>85–100 %</span><span><i class="cl u4"></i>trūksta (&gt;100 %)</span></div></div>
      <p class="muted">Langelyje – apkrova procentais nuo pajėgumo${st.basket ? ", po ja – kiek valandų sudaro krepšelio projektai" : ""}. Spauskite eilutę – matysite, kurie projektai apkrauna.</p>
      <div class="tbl"><table class="heat"><thead><tr><th>Departamentas</th><th>Pajėgumas / sav.</th>${r.weeks.map(w => `<th class="wk" title="${w.start}">${w.label}<br><span class="muted">${w.start.slice(5)}</span></th>`).join("")}<th>Laisva, val.</th></tr></thead>
      <tbody>${groups.map(([k, label]) => {
        const ds = r.departments.filter(d => d.kind === k);
        return ds.length ? `<tr class="grp"><td colspan="${r.weeks.length + 3}">${label}</td></tr>` + ds.map(d => `
        <tr class="click ${st.open === d.code ? "sel" : ""}" data-dep="${esc(d.code)}"><td><b>${esc(d.name)}</b><br><span class="muted">${d.headcount} žm. × ${d.hours_per_week} h × ${Math.round(100 * d.availability)} %</span></td>
          <td class="num">${d.capacity_week} h</td>
          ${d.cells.map(c => {
            const tot = c.committed + (st.basket ? c.basket : 0);
            const tip = `${wk(c.week)}: poreikis ${Math.round(tot)} h iš ${c.capacity} h` + (c.projects.length ? "\n" + c.projects.map(p => `${p.code}${p.basket ? " (krepšelis)" : ""}: ${p.hours} h`).join("\n") : "") + (c.shortage ? `\nTrūksta ${c.shortage} h` : "");
            return `<td class="hc ${utilCls(tot ? c.util : 0)}" title="${esc(tip)}">${tot ? `${Math.round(100 * c.util)}%` : ""}${st.basket && c.basket ? `<small>+${Math.round(c.basket)} kr.</small>` : ""}</td>`;
          }).join("")}
          <td class="num">${Math.round(d.free_hours)}</td></tr>
        ${st.open === d.code ? `<tr class="detail"><td colspan="${r.weeks.length + 3}">${depChart(d, r, colorOf)}</td></tr>` : ""}`).join("") : "";
      }).join("")}</tbody></table></div></div>
    <div class="grid2">
      <div class="card"><h2>Kur trūksta resurso</h2>${r.shortages.length ? simple(r.shortages, ["Savaitė", "Departamentas", "Poreikis", "Pajėgumas", "Trūksta", "≈ žmonių", "Daugiausia apkrauna"], s => [
        wk(s.week), esc(s.department) + (s.basket_only ? ' <span class="warn">tik priėmus krepšelį</span>' : ""), `${s.demand} h`, `${s.capacity} h`,
        `<b class="s-late">${s.shortage} h</b>`, s.people ?? "—", s.projects.map(p => `${esc(p.code)} ${p.hours} h`).join(", ")]) : `<p class="muted">Per pasirinktą laikotarpį resurso užtenka visur.</p>`}</div>
      <div class="card"><h2>Ar galima prisiimti krepšelio projektus</h2>
        <p class="muted">Tikrinama kiekviena savaitė: vykdomi projektai + šis projektas turi tilpti į pajėgumą.</p>
        ${r.basket_fit.length ? r.basket_fit.map(f => `<div class="fit">
          <div class="row between"><b>${esc(f.code)} ${esc(f.name)}</b>${f.fits === null ? '<span class="muted">nėra valandų</span>' : f.fits ? pill("baigta", "telpa") : pill("atvira", "netelpa")}</div>
          ${f.needs.filter(n => !n.ok).map(n => `<div class="lock">${esc(n.name)}: trūktų ${n.over} h (blogiausia ${wk(n.worst_week)})</div>`).join("")}
          <div class="muted">Poreikis: ${f.needs.map(n => `${esc(n.code)} ${n.hours} h`).join(", ") || "—"}</div></div>`).join("") : `<p class="muted">Krepšelyje projektų nėra.</p>`}</div>
    </div>
    ${r.unassigned.length ? `<div class="card"><h2>Ko trūksta tiksliam skaičiavimui</h2>${simple(r.unassigned, ["Projektas", "Kas", "Trūksta"], u => [
      `<a href="#/p/${u.project_id}/planas">${esc(u.project)}</a>`, esc(u.what), esc(u.why)])}</div>` : ""}
    ${r.notes.length ? `<div class="card"><h2>Prielaidos</h2><ul>${r.notes.map(n => `<li class="muted">${esc(n)}</li>`).join("")}</ul></div>` : ""}
    ${can("projects") ? `<div class="card"><h2>Departamentų pajėgumas</h2><p class="muted">Pajėgumas per savaitę = žmonės × valandos × prieinamumas (dalis laiko projektams, be atostogų, ligų ir kitų darbų).</p><div id="deps"></div></div>` : ""}`;
    $("#cap-w").onchange = e => { st.weeks = +e.target.value; save(); draw(); };
    $("#cap-b").onchange = e => { st.basket = e.target.checked; save(); draw(); };
    $$("tr[data-dep]").forEach(tr => tr.onclick = () => { st.open = st.open === tr.dataset.dep ? null : tr.dataset.dep; save(); draw(); });
    if (can("projects")) {
      const deps = await GET("/api/departments");
      $("#deps").innerHTML = `<div class="tbl"><table><thead><tr><th>Departamentas</th><th>Žmonės</th><th>Val. / sav.</th><th>Prieinamumas, %</th><th>Pajėgumas</th><th>Etapai</th></tr></thead><tbody>
        ${deps.map(d => `<tr><td>${esc(d.name)} <span class="muted mono">${esc(d.code)}</span></td>
          <td><input type="number" min="0" step="0.5" value="${d.headcount}" data-dp="${d.id}" data-f="headcount" style="width:70px" id="dp-h-${d.id}"></td>
          <td><input type="number" min="0" value="${d.hours_per_week}" data-dp="${d.id}" data-f="hours_per_week" style="width:70px" id="dp-w-${d.id}"></td>
          <td><input type="number" min="0" max="100" value="${Math.round(100 * d.availability)}" data-dp="${d.id}" data-f="availability" style="width:70px" id="dp-a-${d.id}"></td>
          <td class="num">${d.capacity_week} h</td><td class="muted">${d.kind === "production" ? "cecho operacijos, gamybos etapai" : esc(d.phase_kind_list.join(", "))}</td></tr>`).join("")}</tbody></table></div>`;
      $$("[data-dp]").forEach(el => el.onchange = async () => {
        const v = +el.value; await act(() => PUT(`/api/departments/${el.dataset.dp}`, { [el.dataset.f]: el.dataset.f === "availability" ? v / 100 : v }), "Įrašyta"); draw();
      });
    }
  };
  await draw();
}

function depChart(d, r, colorOf) {
  // stulpelinė diagrama: savaitės poreikis pagal projektus + pajėgumo linija
  const W = Math.max(560, r.weeks.length * 56), H = 220, pad = { l: 44, r: 10, t: 14, b: 40 };
  const bw = (W - pad.l - pad.r) / r.weeks.length;
  const max = Math.max(d.capacity_week * 1.15, ...d.cells.map(c => c.committed + c.basket)) || 1;
  const y = v => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => Math.round(max * f));
  let bars = "";
  d.cells.forEach((c, i) => {
    let acc = 0;
    c.projects.forEach(p => {
      if (p.basket && !r.include_basket) return;
      const y1 = y(acc + p.hours), y0 = y(acc);
      bars += `<rect x="${pad.l + i * bw + 6}" y="${y1}" width="${bw - 12}" height="${Math.max(0, y0 - y1)}" fill="${colorOf[p.code]}" ${p.basket ? 'fill-opacity="0.45" stroke="' + colorOf[p.code] + '" stroke-dasharray="3 2"' : ""}><title>${esc(p.code)}${p.basket ? " (krepšelis)" : ""}: ${p.hours} h</title></rect>`;
      acc += p.hours;
    });
  });
  const projs = [...new Map(d.cells.flatMap(c => c.projects).map(p => [p.code, p])).values()];
  return `<div class="chartwrap"><svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:${Math.min(W, 560)}px" class="chart" role="img" aria-label="${esc(d.name)} apkrova">
    ${ticks.map(t => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(t)}" y2="${y(t)}" class="grid"/><text x="${pad.l - 6}" y="${y(t) + 4}" text-anchor="end" class="ax">${t}</text>`).join("")}
    ${bars}
    <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(d.capacity_week)}" y2="${y(d.capacity_week)}" class="capline"/>
    <text x="${W - pad.r}" y="${y(d.capacity_week) - 5}" text-anchor="end" class="caplbl">pajėgumas ${d.capacity_week} h</text>
    ${r.weeks.map((w, i) => `<text x="${pad.l + i * bw + bw / 2}" y="${H - pad.b + 16}" text-anchor="middle" class="ax">${w.label}</text>`).join("")}
  </svg></div>
  <div class="legend">${projs.map(p => `<span><i style="background:${colorOf[p.code]};${p.basket ? "opacity:.5" : ""}"></i>${esc(p.code)}${p.basket ? " (krepšelis)" : ""}</span>`).join("")}</div>`;
}

route();
