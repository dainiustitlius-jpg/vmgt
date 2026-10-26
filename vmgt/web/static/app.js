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
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#modal").hidden) closeModal(); });

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
  [/^#\/projektai$/, pageProjects],
  [/^#\/p\/(\d+)(?:\/(\w+))?$/, pageProject],
  [/^#\/uzduotys$/, pageMyActions],
  [/^#\/mano(?:\/(\d{4}-\d{2}-\d{2}))?$/, pageMyWeek],
  [/^#\/apkrova$/, pageCapacity],
  [/^#\/m\/(\d+)$/, pageMeeting],
  [/^#\/m\/(naujas)\/(\d+)$/, pageMeetingEdit],
  [/^#\/m\/(\d+)\/keisti$/, pageMeetingEdit],
  [/^#\/cechas(?:\/(planas|korteles))?$/, pageFloor],
  [/^#\/planas\/kalendorius(?:\/(factory|area|centre)\/(\d+))?$/, pageCalendar],
  [/^#\/planas(?:\/([\w-]+))?$/, pagePlan],
  [/^#\/t(?:\/([\w-]+))?$/, pageTerminal],
  [/^#\/r\/(\d+)(?:\/d\/([^/]+))?$/, pageRoute],
  [/^#\/r\/(\d+)\/lapai$/, pageRouteCards],
  [/^#\/ncr$/, pageNcr],
  [/^#\/kokybe(?:\/(\w+))?$/, pageQuality],
  [/^#\/dosje\/(\d+)$/, pageDossier],
  [/^#\/analitika$/, pageAnalytics],
  [/^#\/komponentai(?:\/(\d+))?$/, pageComponents],
  [/^#\/duomenys$/, pageData],
  [/^#\/technologija$/, pageTechList],
  [/^#\/technologija\/(\d+)$/, pageTechEdit],
  [/^#\/admin(?:\/(vartotojai|roles|centrai|zurnalas)(?:\/(\d+))?)?$/, pageAdmin],
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
  // viršuje – moduliai, po jais – aktyvaus modulio skyriai
  const h = location.hash || "#/", cur = modOf(h);
  $("#nav").innerHTML = `<a href="#/" class="${h === "#/" ? "on" : ""}">Pradžia</a>` + MODS.filter(m => modSections(m).length).map(m =>
    `<a href="${modSections(m)[0][0]}" class="${cur === m ? "on" : ""}">${icon(m.key, "nico")}${m.label}</a>`).join("");
  const secs = cur ? modSections(cur) : [], on = cur && sectionOf(cur, h);
  $("#subnav").hidden = secs.length < 2;
  $("#subnav").innerHTML = secs.map(s => `<a href="${s[0]}" class="${s[0] === on ? "on" : ""}">${esc(s[1])}</a>`).join("");
  $("#who").innerHTML = `${esc(S.me.name)}<small>${esc(S.me.role_label)}</small>`;
  bellCount();
}
$("#logout").onclick = async () => { await POST("/api/logout").catch(() => {}); S.me = null; location.hash = "#/login"; route(); };

// ---------- prisijungimas ----------
// Prisijungimo lango iliustracija – robotinės rankos brėžinys: kontūrai
// brėžinio mėlyna, jungtys oranžinės, judesio zona ir matmuo – kaip CAD lape
const ARM_SVG = `<svg viewBox="0 0 360 250" fill="none" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="Robotinės rankos brėžinys">
  <g stroke="#6aa7e8" stroke-width="1.6">
    <path d="M20 220H340"/>
    <path d="M95 40A130 130 0 0 1 225 170" stroke-dasharray="4 5" opacity=".55"/>
    <path d="M95 150V232M85 170h20" stroke-dasharray="10 3 2 3" opacity=".5"/>
    <rect x="60" y="198" width="70" height="22" rx="2"/><rect x="76" y="180" width="38" height="18" rx="2"/>
    <rect x="-9" y="-68" width="18" height="136" rx="9" transform="translate(135 125) rotate(41.6)"/>
    <rect x="-61" y="-7.5" width="122" height="15" rx="7.5" transform="translate(225 92.5) rotate(14)"/>
    <path d="M275 112v14M264 126h22M266 126v15M284 126v15"/>
    <rect x="252" y="198" width="46" height="22" rx="1"/><path d="M252 209h46" opacity=".5"/>
    <path d="M95 238H275M95 233v10M275 233v10M95 238l7-3v6zM275 238l-7-3v6z"/>
  </g>
  <g stroke="#ff7a2e" stroke-width="2"><circle cx="95" cy="170" r="12"/><circle cx="175" cy="80" r="10"/><circle cx="275" cy="105" r="7"/></g>
  <g fill="#ff7a2e"><circle cx="95" cy="170" r="2.5"/><circle cx="175" cy="80" r="2.5"/><circle cx="275" cy="105" r="2"/></g>
  <g fill="#8d9aa8" font-family="Consolas, monospace" font-size="10"><text x="112" y="188">J1</text><text x="190" y="72">J2</text><text x="286" y="100">J3</text>
    <text x="168" y="232">R 1200</text><text x="236" y="56">±170°</text></g>
</svg>`;

async function pageLogin() {
  $("#top").hidden = true;
  app().innerHTML = `
  <div class="login card">
    <div class="hero">
      <div><span class="brand">${$("#top .brand svg").outerHTML}VMGT</span><p>Projektų stebėsena ir gamybos valdymas</p></div>
      ${ARM_SVG}
      <div class="tblock"><span>VIENETINĖ METALO GAMYBA</span><span>PJOVIMAS → SUVIRINIMAS → SURINKIMAS → TESTAVIMAS</span></div>
    </div>
    <div class="form">
      <h2>Prisijungimas</h2>
      <div class="row"><button id="tab-pw">Vardas ir slaptažodis</button><button id="tab-pin" class="ghost">PIN (terminalas)</button></div>
      <form id="f-pw" class="stack">
        <label>Prisijungimo vardas<input name="login" autocomplete="username" required id="lg-login"></label>
        <label>Slaptažodis<input name="password" type="password" autocomplete="current-password" required id="lg-pass"></label>
        <button>Prisijungti</button>
      </form>
      <div id="f-pin" hidden>
        <div class="pindots" id="pindots"></div>
        <div class="pinpad">${[1,2,3,4,5,6,7,8,9].map(n => `<button class="ghost" data-n="${n}">${n}</button>`).join("")}
          <button class="ghost" data-n="C">⌫</button><button class="ghost" data-n="0">0</button><button data-n="OK">OK</button></div>
      </div>
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

// ---------- moduliai: navigacija ir pradžios plytelės ----------
// Vartotojo sprendimas (2026-10-26): funkcijos sudėliotos į modulius, pradžia –
// modulių plytelės su tuo, kas laukia. Meniu rodo tik modulius, kuriuose
// žmogus turi bent vieną skyrių, o modulio skyriai – antroje juostoje.
const ICONS = {
  projektai: '<path d="M3 6h7l2 2h9v11H3z"/><path d="M7 13h6M7 16h9"/>',
  mano: '<rect x="4" y="4" width="16" height="17" rx="1"/><path d="M8 2v4M16 2v4M8 11l2 2 4-4M8 17h8"/>',
  planavimas: '<path d="M3 5h18M3 5v15h18V5"/><path d="M6 9h6M9 13h8M5 17h5"/>',
  gamyba: '<path d="M3 21h10M7 21v-4"/><circle cx="7" cy="15" r="2"/><path d="m8.5 13.5 5-5"/><circle cx="15" cy="7" r="2"/><path d="M17 7h3M20 4.5v5"/>',
  kokybe: '<path d="M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
  tiekimas: '<path d="M3 8 12 3l9 5v9l-9 5-9-5z"/><path d="m3 8 9 5 9-5M12 13v9"/>',
  analitika: '<path d="M4 20V10M10 20V4M16 20v-7M21 20H3"/>',
  admin: '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><path d="M17 11l2 2 3-4"/>',
};
const icon = (k, cls = "") => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[k] || ""}</svg>`;
const MODS = [
  { key: "projektai", label: "Projektai", desc: "Projektų portfelis ir krepšelis, sveikata, etapai, susitikimai",
    match: ["#/projektai", "#/p/", "#/m/"], sections: [["#/projektai", "Portfelis", "view"]] },
  { key: "mano", label: "Mano darbai", desc: "Asmeninis savaitės planas, man priskirtos užduotys, pranešimai",
    match: ["#/mano", "#/uzduotys"], sections: [["#/mano", "Savaitės planas", null], ["#/uzduotys", "Užduotys", null]] },
  { key: "planavimas", label: "Planavimas", desc: "Departamentų planas, centrų eilės, darbo kalendorius, apkrova",
    match: ["#/planas", "#/apkrova"], sections: [["#/planas", "Departamentų planas", "view"], ["#/planas/eiles", "Centrų eilės", "plan"],
      ["#/planas/kalendorius", "Darbo kalendorius", "view"], ["#/apkrova", "Apkrova", "view"]] },
  { key: "gamyba", label: "Gamyba", desc: "Cecho būsena ir planas, terminalai, technologija ir maršrutai",
    match: ["#/cechas", "#/t", "#/technologija", "#/duomenys", "#/r/"], sections: [["#/cechas", "Cechas", "view"], ["#/t", "Terminalas", "execute"],
      ["#/technologija", "Technologija", "tasks"], ["#/duomenys", "Duomenys ir importas", "tasks"]] },
  { key: "kokybe", label: "Kokybė", desc: "Kontrolės eilė, medžiagos, suvirinimas, neatitiktys, dosjė",
    match: ["#/kokybe", "#/ncr", "#/dosje"], sections: [["#/kokybe", "Kokybės kontrolė", "view"], ["#/ncr", "Neatitiktys", "ncr_report"]] },
  { key: "tiekimas", label: "Tiekimas", desc: "Pirktiniai komponentai: užsakymai, gavimai, vėlavimai",
    match: ["#/komponentai"], sections: [["#/komponentai", "Komponentai", "view"]] },
  { key: "analitika", label: "Analitika", desc: "Darbo laikas, prastovos, faktas prieš normą, tiekėjai",
    match: ["#/analitika"], sections: [["#/analitika", "Efektyvumas", "view"]] },
  { key: "admin", label: "Administravimas", desc: "Vartotojai, rolės ir teisės, barai ir centrai, žurnalas",
    match: ["#/admin"], sections: [["#/admin/vartotojai", "Vartotojai", "admin"], ["#/admin/roles", "Rolės ir teisės", "admin"],
      ["#/admin/centrai", "Barai ir centrai", "admin"], ["#/admin/zurnalas", "Teisių žurnalas", "admin"]] },
];
const modSections = m => m.sections.filter(s => !s[2] || can(s[2]));
const modOf = h => MODS.find(m => m.match.some(p => h === p || h.startsWith(p.endsWith("/") ? p : p + "/")));
// aktyvus skyrius – ilgiausias sutampantis; #/planas/<centras> – centrų eilės
function sectionOf(m, h) {
  if (m.key === "planavimas" && /^#\/planas\/(?!kalendorius)/.test(h)) return "#/planas/eiles";
  return m.sections.map(s => s[0]).filter(p => h === p || h.startsWith(p + "/")).sort((a, b) => b.length - a.length)[0];
}
// bare ribojamos teisės: meistrui – tik savo barų / centrų darbai
const SCOPED = new Set(["execute", "ack_rev", "plan", "calendar"]);
function canAt(perm, centre, area) {
  if (!can(perm)) return false;
  if (!SCOPED.has(perm) || (perm !== "execute" && S.me.scope === "all")) return true;
  const c = S.me.centres || [];
  return !c.length || c.includes(centre) || (!!area && c.includes(area));
}

async function pageHome() {
  if (!can("view") && can("execute")) { location.hash = "#/t"; return; }
  const draw = async () => {
    const r = await GET("/api/home");
    const byKey = Object.fromEntries(r.tiles.map(t => [t.key, t]));
    const hour = new Date().getHours();
    const hi = hour < 11 ? "Labas rytas" : hour < 18 ? "Laba diena" : "Labas vakaras";
    const tiles = MODS.filter(m => byKey[m.key] && modSections(m).length);
    app().innerHTML = `<div class="row between"><div><h1>${hi}, ${esc(S.me.name.split(" ")[0])}</h1>
        <p class="muted">${esc(S.me.role_label)}${S.me.centres.length ? ` · ${S.me.scope === "own" ? "jūsų barai" : "darbo vietos"}: <b class="mono">${esc(S.me.centres.join(", "))}</b>` : ""}</p></div>
        <span class="muted small">${new Date().toLocaleDateString("lt-LT", { weekday: "long", month: "long", day: "numeric" })}</span></div>
      <div class="mods">${tiles.map(m => {
        const t = byKey[m.key], secs = modSections(m);
        return `<section class="mod">
          <a class="mod-h" href="${secs[0][0]}">${icon(m.key, "mico")}<div><h2>${esc(m.label)}</h2><p class="muted small">${esc(m.desc)}</p></div></a>
          ${t.counters.length ? `<div class="mcnt">${t.counters.map(c => `<a class="mc ${c.sev}" href="${esc(c.href || secs[0][0])}"><b>${c.n}</b><span>${esc(c.label)}</span></a>`).join("")}</div>` : ""}
          ${t.note ? `<p class="muted small">${esc(t.note)}</p>` : ""}
          <div class="mlinks">${secs.map(s => `<a href="${s[0]}">${esc(s[1])} →</a>`).join("")}</div></section>`;
      }).join("")}</div>`;
    $$('.mc[href="#bell"]').forEach(a => a.onclick = e => { e.preventDefault(); $("#bell").click(); });
  };
  await draw();
  S.timers.push(setInterval(() => { if ($("#modal").hidden) draw(); }, 60000));
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
      <label title="EN 1090-2: nuo EXC2 – privalomas medžiagų atsekamumas ir WPS">Vykdymo klasė<select name="exc_class" id="pe-exc">${["", "EXC1", "EXC2", "EXC3", "EXC4"].map(x => `<option value="${x}" ${x === (p.exc_class || "") ? "selected" : ""}>${x || "—"}</option>`).join("")}</select></label>
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
    <p class="muted">Detalės kodas nusako srautą: tos pačios detalės operacijos – jos atšaka, be kodo – mazgo operacijos, kuriose detalės susilieja. Ceche užduotys matomos tik technologui išleidus maršrutą į gamybą.</p>
    ${p.assemblies.map(a => {
      const ts = p.tasks.filter(t => t.assembly_id === a.id);
      const rel = !!a.released_at;
      return `<div class="asm"><div class="row between"><h3><span class="mono">${esc(a.code)}</span> ${esc(a.name)} <span class="muted">× ${a.qty}${a.requires ? ` · laukia mazgų ${esc(a.requires)}` : ""}</span></h3>
        <div class="row">${rel ? pill("baigta", `išleista į gamybą ${dt(a.released_at)}`) : ts.length ? pill("laukia", "juodraštis – neišleista") : ""}
          ${edt ? `<a class="btn ghost small" href="#/technologija/${a.id}">Technologija ir failai →</a>` : ""}
          ${ts.length ? `<a class="btn ghost small" href="#/r/${a.id}">Srautas ir atsekamumas →</a>` : ""}</div></div>
      <div class="tbl"><table><thead><tr><th>Seka</th><th>Detalė</th><th>Centras</th><th>Operacija</th><th>Kiekis</th><th>Norma</th><th>Brėžinys</th><th>Būsena</th><th>Prognozė</th><th></th></tr></thead><tbody>
      ${ts.map(t => `<tr><td class="num">${t.seq}</td><td class="mono">${t.part_no ? esc(t.part_no) : '<span class="muted">mazgas</span>'}</td><td class="mono">${esc(t.centre_code)}</td><td>${esc(t.name)}</td>
        <td class="num">${t.qty_good}/${t.qty_plan}${t.qty_scrap ? ` <span class="s-late">brokas ${t.qty_scrap}</span>` : ""}</td>
        <td class="num">${t.norm_min ? t.norm_min + " min/vnt" : "—"}</td>
        <td>${t.drawing_no ? `<a href="/api/drawings/${encodeURIComponent(t.drawing_no)}/file?rev=${encodeURIComponent(t.drawing_rev)}" target="_blank">${esc(t.drawing_no)} ${esc(t.drawing_rev)}</a>` : "—"}</td>
        <td>${pill(t.status, t.status)}${t.approved ? "" : ' <span class="muted">nepatvirtinta</span>'}</td>
        <td>${t.status === "baigta" ? "" : fcCell(t.forecast)}</td>
        <td>${edt && !rel && t.status === "laukia" && !t.qty_good ? `<button class="small ghost" data-del="${t.id}">Šalinti</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="10" class="muted">Operacijų nėra.</td></tr>`}
      </tbody></table></div>
      ${edt && rel ? `<p class="muted">Maršrutas išleistas į gamybą ir užrakintas. Keisti – „Srautas ir atsekamumas“ → „Keisti maršrutą“.</p>` : ""}
      ${edt && !rel ? `<form class="inline newt" data-a="${a.id}" style="margin-top:8px">
        <label>Seka<input name="seq" type="number" style="width:70px" placeholder="auto" id="nt-q-${a.id}"></label>
        <label>Detalė<input name="part_no" style="width:110px" placeholder="tuščia – mazgas" id="nt-p-${a.id}"></label>
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
  <div class="row between"><div><a href="#/projektai">← Portfelis</a><h1><span class="mono">${esc(p.code)}</span> ${esc(p.name)}</h1>
    <p class="muted">${esc(p.customer)} · terminas ${esc(p.due_date || "—")} · vadovas ${esc(p.manager_name || "—")}</p></div>
    <div class="row">${p.exc_class ? `<span class="pill s-gali" title="EN 1090-2 vykdymo klasė">${esc(p.exc_class)}</span>` : ""} ${healthBadge(h)} ${pill(p.status, p.status_label)}
      <a class="btn ghost small" href="#/dosje/${p.id}">Kokybės dosjė</a></div></div>
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
            ${o.global ? `<div class="muted mono">${x.personal ? "asmeninė" : esc(x.project_code)}</div>` : ""}
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
  const ed = x.can_edit, full = x.personal ? ed : can("actions"), mine = x.owner_id === S.me.id;
  const projs = x.personal && can("view") ? await GET("/api/projects") : [];
  modal(`<div class="row between"><span class="muted mono">${x.personal ? "Asmeninė užduotis – matote tik jūs" : esc(x.project_code)}${x.assembly_code ? " · " + esc(x.assembly_code) : ""}</span>${pill(actCls(x), x.status_label)}</div>
    ${full ? `<input id="ax-title" value="${esc(x.title)}" style="font-size:17px;font-weight:600">` : `<h2>${esc(x.title)}</h2>`}
    ${x.meeting_id ? `<div class="muted">Kilo iš susitikimo: <a href="#/m/${x.meeting_id}">${esc(x.meeting_title)}</a></div>` : ""}
    <div class="grid2" style="gap:10px">
      ${x.personal && projs.length ? `<label>Susieti su projektu<select id="ax-proj">${opt(projs.map(p => ({ id: p.id, name: `${p.code} ${p.name}` })), "", "— asmeninė —")}</select></label>` : ""}
      <label>Atsakingas${full && !x.personal ? `<select id="ax-owner">${opt(users.filter(u => u.active), x.owner_id, "—")}</select>` : `<b>${esc(x.owner_name || "—")}</b>`}</label>
      ${mine ? `<label>Planuoju daryti<input type="date" id="ax-plan" value="${esc(x.plan_date || "")}"></label>
        <label>Įvertis, val.<input type="number" min="0" step="0.5" id="ax-est" value="${x.estimate_h ?? ""}"></label>` : ""}
      <label>Terminas${full ? `<input type="date" id="ax-due" value="${esc(x.due_date || "")}">` : `<b class="${x.overdue ? "s-late" : ""}">${esc(x.due_date || "—")}</b>`}</label>
      <label>Prioritetas${full ? `<select id="ax-prio">${opt(S.meta.priorities, x.priority)}</select>` : `<b>${esc((S.meta.priorities.find(p => p.key === x.priority) || {}).label)}</b>`}</label>
    </div>
    <label>Aprašymas${full ? `<textarea id="ax-desc">${esc(x.description)}</textarea>` : `<div>${esc(x.description || "—")}</div>`}</label>
    ${full || mine ? `<div><button class="ghost" id="ax-save">Įrašyti pakeitimus</button>${x.personal && projs.length ? ` <span class="muted">Susieta su projektu užduotis tampa matoma komandai ir ją galima priskirti kolegai.</span>` : ""}</div>` : ""}
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
      const body = {};
      if (full) Object.assign(body, { title: $("#ax-title").value, due_date: $("#ax-due").value || null, priority: +$("#ax-prio").value, description: $("#ax-desc").value });
      if ($("#ax-owner")) body.owner_id = $("#ax-owner").value ? +$("#ax-owner").value : null;
      if ($("#ax-proj") && $("#ax-proj").value) body.project_id = +$("#ax-proj").value;
      if (mine) { body.plan_date = $("#ax-plan").value || null; body.estimate_h = $("#ax-est").value === "" ? null : +$("#ax-est").value; }
      await act(() => PUT(`/api/actions/${id}`, body), "Įrašyta");
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

// ---------- asmeninis savaitės planas ----------
// Kiekvienas planuojasi savo darbus: asmenines užduotis ir jam priskirtas
// projektų. Tempiama į dieną (arba „Planuoti“ lange) – serveris saugo dieną.
async function pageMyWeek(start) {
  const [w, projs] = await Promise.all([GET(`/api/my/week${start ? `?start=${start}` : ""}`), can("view") ? GET("/api/projects") : []]);
  const shift = n => addDays(w.start, n);
  const fmtD = d => `${d.slice(8, 10)}.${d.slice(5, 7)}`;
  const card = x => `<div class="acard pcard ${x.overdue ? "late" : ""} ${x.status === "atlikta" ? "done" : ""}" draggable="${x.status !== "atlikta"}" data-act="${x.id}" tabindex="0">
      <div class="row" style="gap:6px;flex-wrap:nowrap;align-items:start">
        ${x.personal && x.status !== "atlikta" && x.next.some(n => n.key === "atlikta") ? `<input type="checkbox" class="pdone" data-done="${x.id}" title="Atlikta" aria-label="Pažymėti atlikta">` : x.status === "atlikta" ? "✓" : ""}
        <b>${esc(x.title)}</b></div>
      <div class="muted small"><span class="mono">${x.personal ? "asmeninė" : esc(x.project_code)}</span>${x.estimate_h ? ` · ${String(x.estimate_h).replace(".", ",")} val.` : ""}${x.due_date ? ` · iki <span class="nw ${x.overdue ? "s-late" : ""}">${esc(x.due_date)}</span>` : ""}</div>
      ${x.personal || x.status === "atlikta" ? "" : `<div>${pill(actCls(x), x.status_label)}</div>`}
      ${x.rolled_from ? `<div class="warn small">↻ perkelta iš ${fmtD(x.rolled_from)}</div>` : ""}
      ${x.late_plan ? `<div class="lock small">suplanuota po termino</div>` : ""}
      ${x.status === "laukia" && x.wait_reason ? `<div class="warn small">⏸ ${esc(x.wait_reason)}</div>` : ""}</div>`;
  // į praėjusią dieną planuoti negalima – ji nepriima ir neturi „+ Pridėti“
  const col = (key, head, items, extra = "", past = false) => `<div class="col pcol ${extra}" ${past ? "" : `data-drop="${key}"`}>${head}${items.map(card).join("") || `<div class="muted empty">—</div>`}
    ${past ? "" : `<button class="ghost small padd" data-add="${key}">+ Pridėti</button>`}</div>`;
  const days = w.days.filter(d => !d.weekend || d.items.length);
  app().innerHTML = `<div class="row between"><div><h1>Mano darbai</h1>
      <p class="muted">Asmeninės užduotys (matote tik jūs) ir jums priskirtos projektų užduotys. Tempkite į dieną, kurią planuojate daryti.</p></div>
    <div class="row"><button class="ghost" data-wk="${shift(-7)}">←</button><b class="nw">${fmtD(w.start)} – ${fmtD(w.end)}</b><button class="ghost" data-wk="${shift(7)}">→</button>
      <button class="ghost" data-wk="">Ši savaitė</button></div></div>
  <form id="qadd" class="inline card">
    <label style="flex:1 1 260px">Nauja užduotis sau<input name="title" required placeholder="Ką reikia padaryti" id="qa-title" autocomplete="off"></label>
    <label>Diena<select name="plan_date" id="qa-day">${opt([{ id: "", name: "Neplanuota" }, ...w.days.filter(d => !d.past).map(d => ({ id: d.date, name: `${d.label} ${fmtD(d.date)}` }))], w.days.some(d => d.date === w.work_day) ? w.work_day : "")}</select></label>
    <label>Įvertis, val.<input name="estimate_h" type="number" min="0" step="0.5" style="width:90px" id="qa-est"></label>
    ${projs.length && can("actions") ? `<label>Projektas<select name="project_id" id="qa-proj">${opt(projs.map(p => ({ id: p.id, name: `${p.code} ${p.name}` })), "", "— asmeninė —")}</select></label>` : ""}
    <button>Pridėti</button></form>
  <p class="muted">Atvirų: ${w.open} · dienos planas ${w.days[0].capacity} val. Neatlikta praėjusios dienos užduotis rodoma šiandien.</p>
  <div class="board week">
    ${col("", `<div class="colh">Neplanuota <span class="muted">${w.unplanned.length}</span></div>`, w.unplanned)}
    ${days.map(d => col(d.date, `<div class="colh">${esc(d.label)} <span class="muted">${fmtD(d.date)}</span></div>
      <div class="dbar ${d.over ? "over" : ""}" title="${d.hours} iš ${d.capacity} val."><i style="width:${Math.min(100, d.hours / d.capacity * 100)}%"></i></div>
      <div class="small ${d.over ? "s-late" : "muted"}">${String(d.hours).replace(".", ",")} / ${d.capacity} val.${d.over ? " – per daug" : ""}</div>`, d.items, `${d.today ? "today" : ""} ${d.past ? "past" : ""}`, d.past)).join("")}
    ${col(shift(7), `<div class="colh">Vėliau <span class="muted">${w.later.length}</span></div>`, w.later)}
  </div>`;
  const reload = () => pageMyWeek(start);
  $$("[data-wk]").forEach(b => b.onclick = () => (location.hash = b.dataset.wk ? `#/mano/${b.dataset.wk}` : "#/mano"));
  const f = $("#qadd");
  f.onsubmit = async e => {
    e.preventDefault(); const d = formData(f);
    const body = { title: d.title, plan_date: d.plan_date || null, estimate_h: d.estimate_h === "" ? null : +d.estimate_h };
    if (d.project_id) { body.project_id = +d.project_id; body.owner_id = S.me.id; }
    await act(() => POST("/api/actions", body), "Pridėta"); reload();
  };
  $$("[data-add]").forEach(b => b.onclick = () => { $("#qa-day").value = b.dataset.add; if ($("#qa-day").value !== b.dataset.add) $("#qa-day").value = ""; $("#qa-title").focus(); });
  $$("[data-done]").forEach(c => { c.onclick = e => e.stopPropagation(); c.onchange = async () => { await act(() => POST(`/api/actions/${c.dataset.done}/status`, { status: "atlikta" }), "Atlikta"); reload(); }; });
  $$(".pcard[data-act]").forEach(c => {
    c.onclick = () => actionModal(+c.dataset.act, reload);
    c.onkeydown = e => e.key === "Enter" && c.onclick();
    c.ondragstart = e => { e.dataTransfer.setData("text/plain", c.dataset.act); c.classList.add("drag"); };
    c.ondragend = () => c.classList.remove("drag");
  });
  $$("[data-drop]").forEach(z => {
    z.ondragover = e => { e.preventDefault(); z.classList.add("over"); };
    z.ondragleave = () => z.classList.remove("over");
    z.ondrop = async e => {
      e.preventDefault(); z.classList.remove("over");
      const id = e.dataTransfer.getData("text/plain");
      if (id) { await act(() => PUT(`/api/actions/${id}`, { plan_date: z.dataset.drop || null })); reload(); }
    };
  });
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
const floorTabs = on => `<nav class="tabs"><a href="#/cechas/planas" class="${on === "p" ? "on" : ""}">Cecho planas</a><a href="#/cechas/korteles" class="${on === "k" ? "on" : ""}">Kortelės</a></nav>`;

async function pageFloor(view) {
  if (!view) { try { view = localStorage.getItem("pf.floorView") || "planas"; } catch { view = "planas"; } }
  try { localStorage.setItem("pf.floorView", view); } catch {}
  if (view === "planas") return pageFloorPlan();
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
        ${s.calendar && !s.calendar.working ? `<div class="offc">⏾ ${esc(s.calendar.why)}${s.calendar.next ? ` · nuo ${dt(s.calendar.next)}` : ""}</div>` : ""}
        ${t ? `<div><b>${esc(t.project_code)} · ${esc(t.assembly_code)}</b><br>${esc(t.name)}</div>
          <div class="t" data-since="${s.state === "dirba" ? esc(s.since || "") : ""}" data-base="${s.work_s || 0}">${dur((s.work_s || 0) + (s.state === "dirba" && s.since ? since(s.since) : 0))}</div>
          <div class="muted">${esc(s.who || "")}${s.pause ? ` · ${esc(s.pause)}` : ""}</div>`
        : n ? `<div>Kitas: <b>${esc(n.project_code)} · ${esc(n.assembly_code)}</b> ${esc(n.name)}</div>${s.lock ? `<div class="lock">🔒 ${esc(s.lock)}</div>` : ""}` : ""}
        <div class="muted">Eilėje: ${s.queue}</div></a>`;
    };
    app().innerHTML = `<div class="row between"><h1>Cecho būsena</h1><span class="muted">atnaujinama kas 10 s</span></div>
    ${floorTabs("k")}
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

// ---------- cecho planas: barai ir centrai kaip ceche, su gyvomis būsenomis ----------
// Koordinatės – sąlyginiais metrais (SVG viewBox). Centro vieta – baro viduje.
const ST_LABEL = { dirba: "Dirba", pristabdyta: "Pristabdyta", gali: "Gali pradėti", laukia: "Laukia", tuscia: "Laisvas" };
const cut = (s, n) => (s = String(s ?? "")).length > n ? s.slice(0, Math.max(1, n - 1)) + "…" : s;

async function pageFloorPlan() {
  let pid = "", flows = true, edit = false, model = null, data = null;
  try { pid = localStorage.getItem("pf.fproj") || ""; flows = localStorage.getItem("pf.fflow") !== "0"; } catch {}
  const centreAbs = (a, c) => ({ x: a.box.x + c.box.x, y: a.box.y + c.box.y, w: c.box.w, h: c.box.h });

  const render = () => {
    const r = model, ov = data.project;
    const W = Math.max(r.size.w, 40) + (edit ? 30 : 2), H = Math.max(r.size.h, 20) + (edit ? 20 : 2);
    const byId = {};
    r.areas.forEach(a => a.centres.forEach(c => (byId[c.id] = { a, c })));
    const mid = id => { const o = byId[id]; if (!o) return null; const b = centreAbs(o.a, o.c); return [b.x + b.w / 2, b.y + b.h / 2]; };
    const arrow = (f, t, cls, label) => {
      const p1 = mid(f), p2 = mid(t); if (!p1 || !p2) return "";
      const mx = (p1[0] + p2[0]) / 2, my = (p1[1] + p2[1]) / 2, dx = p2[0] - p1[0], dy = p2[1] - p1[1], len = Math.hypot(dx, dy) || 1;
      const cx = mx - dy / len * Math.min(6, len / 4), cy = my + dx / len * Math.min(6, len / 4);   // lenkta, kad nesutaptų su priešinga
      return `<path class="${cls}" d="M${p1[0]},${p1[1]} Q${cx},${cy} ${p2[0]},${p2[1]}" marker-end="url(#${cls.includes("proj") ? "arP" : "arF"})"/>`
        + (label ? `<text class="flabel" x="${(mx + cx) / 2}" y="${(my + cy) / 2}">${esc(label)}</text>` : "");
    };
    const inProj = id => ov && ov.centres[id];
    const centre = (a, c) => {
      const b = c.box, t = c.task, pc = inProj(c.id), n = Math.floor(b.w * 1.45);
      const alert = c.alerts.length ? c.alerts.some(x => x.severity === "red") ? "red" : "yellow" : "";
      const timer = (c.state === "dirba" || c.state === "pristabdyta") && t;
      // ne darbo laikas (šventė, remontas, po pamainos) – blankus, nebent kas dirba
      const off = c.calendar && !c.calendar.working && !timer;
      return `<g class="fc st-${c.state} ${off ? "off" : ""} ${ov && !pc ? "dim" : ""} ${pc ? "inproj" : ""}" data-c="${c.id}" data-a="${a.id}" transform="translate(${b.x},${b.y})" tabindex="0" role="button" aria-label="${esc(c.code)} ${esc(ST_LABEL[c.state])}">
        <rect class="fcr" width="${b.w}" height="${b.h}" rx="0.4"/>
        <circle class="led" cx="${b.w - 0.9}" cy="0.9" r="0.45"/>
        <text class="fcode" x="0.6" y="1.5">${esc(cut(c.code, n - 2))}</text>
        <text class="fsub" x="0.6" y="2.7">${esc(cut(t ? `${t.project_code} · ${t.assembly_code}` : c.next ? `Kitas: ${c.next.project_code}` : c.name, n))}</text>
        ${t ? `<text class="fsub" x="0.6" y="3.8">${esc(cut(t.name, n))}</text>` : ""}
        ${timer ? `<text class="ftime" x="0.6" y="${b.h - 0.6}" data-since="${c.state === "dirba" ? esc(c.since || "") : ""}" data-base="${c.work_s || 0}">${dur((c.work_s || 0) + (c.state === "dirba" && c.since ? since(c.since) : 0))}</text>`
          : `<text class="fsub" x="0.6" y="${b.h - 0.6}">${off ? `⏾ ${esc({ svente: "šventė", nedarbo: "nedirba", remontas: "remontas", poilsio: "poilsis" }[c.calendar.kind] || "po pamainos")} · ` : ""}eilėje ${c.queue}</text>`}
        ${c.waiting ? `<g class="fwait" transform="translate(${b.w - 2.6},${b.h - 1.9})"><rect width="2.2" height="1.4" rx="0.3"/><text x="1.1" y="1.05">⧗${c.waiting}</text></g>` : ""}
        ${alert ? `<g class="falert ${alert}" transform="translate(-0.7,-0.7)"><circle r="0.85" cx="0.85" cy="0.85"/><text x="0.85" y="1.3">!</text></g>` : ""}
        ${pc ? `<text class="fproj" x="0.6" y="${b.h + 1.1}">✓${pc.done} ▶${pc.running} ○${pc.open}</text>` : ""}
        ${edit ? `<rect class="rz" data-rz="c" x="${b.w - 1}" y="${b.h - 1}" width="1" height="1"/>` : ""}
      </g>`;
    };
    $("#fplan").innerHTML = `<svg viewBox="-1 -1 ${W} ${H}" class="fsvg ${edit ? "editing" : ""}" id="fsvg">
      <defs><marker id="arF" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="arF"/></marker>
        <marker id="arP" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="arP"/></marker></defs>
      ${r.areas.map(a => `<g class="farea" data-area="${a.id}" transform="translate(${a.box.x},${a.box.y})">
        <rect class="far" width="${a.box.w}" height="${a.box.h}" rx="0.5"/>
        <text class="fname" x="0.8" y="2.2">${esc(cut(a.name, Math.floor((a.box.w - 7) * 1.15)))}</text>
        <text class="fcount" x="${a.box.w - 0.8}" y="2.2">${a.centres.filter(c => c.state === "dirba").length}/${a.centres.length} dirba</text>
        ${a.centres.map(c => centre(a, c)).join("")}
        ${edit ? `<rect class="rz" data-rz="a" x="${a.box.w - 1.4}" y="${a.box.h - 1.4}" width="1.4" height="1.4"/>` : ""}</g>`).join("")}
      ${!edit && flows ? data.flows.map(f => arrow(f.from_id, f.to_id, "fmove", `${f.qty}`)).join("") : ""}
      ${!edit && ov ? ov.edges.map(e => arrow(e.from_id, e.to_id, `proj ${e.done ? "done" : ""}`)).join("") : ""}
    </svg>`;
    if (edit) wireEdit(); else $$("#fsvg .fc").forEach(g => { g.onclick = () => centreModal(byId[g.dataset.c].c, byId[g.dataset.c].a); g.onkeydown = e => e.key === "Enter" && g.onclick(); });
  };

  const draw = async () => {
    data = await GET(`/api/floor/plan${pid ? `?project_id=${pid}` : ""}`);
    if (!edit) model = JSON.parse(JSON.stringify(data));
    const all = data.areas.flatMap(a => a.centres), n = st => all.filter(c => c.state === st).length;
    const alerts = all.filter(c => c.alerts.length).length;
    app().innerHTML = `<div class="row between"><h1>Cecho būsena</h1>
      <div class="row"><span class="muted small">atnaujinama kas 10 s</span><button class="ghost small" id="f-full" title="Visas ekranas – sieniniam ekranui">⛶ Visas ekranas</button></div></div>
    ${floorTabs("p")}
    <div class="row between ftools">
      <div class="row">${pill("dirba", `dirba ${n("dirba")}`)} ${pill("pristabdyta", `pristabdyta ${n("pristabdyta")}`)} ${pill("gali", `gali pradėti ${n("gali")}`)} ${pill("laukia", `laukia ${n("laukia")}`)}
        ${alerts ? `<span class="sev red">įspėjimų: ${alerts}</span>` : ""}</div>
      <div class="row">
        <label class="row" style="display:flex"><input type="checkbox" id="f-flow" ${flows ? "checked" : ""}> šiandienos detalių judėjimas</label>
        <select id="f-proj" aria-label="Projektas"><option value="">Visi projektai</option>${data.projects.map(p => `<option value="${p.id}" ${String(p.id) === pid ? "selected" : ""}>${esc(p.code)} ${esc(p.name)}</option>`).join("")}</select>
        ${can("admin") ? (edit ? `<button id="f-save">Išsaugoti išdėstymą</button><button class="ghost" id="f-cancel">Atšaukti</button><button class="ghost" id="f-reset">Automatinis</button>`
          : `<button class="ghost" id="f-edit">Redaguoti išdėstymą</button>`) : ""}</div></div>
    ${edit ? `<p class="warn">Redagavimas: tempkite barus (už pavadinimo ar tuščios vietos) ir centrus, kampo kvadratėliu keiskite dydį. Centras lieka savo baro viduje.</p>` : ""}
    <div class="card fwrap" id="fwrap"><div id="fplan"></div>
      <div class="flegend muted small"><span><i class="lg st-dirba"></i>dirba</span><span><i class="lg st-pristabdyta"></i>pristabdyta</span><span><i class="lg st-gali"></i>gali pradėti</span>
        <span><i class="lg st-laukia"></i>laukia (užrakinta)</span><span><i class="lg st-tuscia"></i>laisvas</span><span><i class="lg off"></i>ne darbo laikas</span><span>⧗ – atkeliavusios detalės laukia</span><span class="lgal">!</span> įspėjimas
        ${flows ? `<span>→ šiandien perduota (vnt.)</span>` : ""}${data.project ? `<span class="lgp">→ ${esc(data.project.code)} kelias (✓ atlikta ▶ vyksta ○ laukia)</span>` : ""}</div></div>`;
    $("#f-flow").onchange = e => { flows = e.target.checked; try { localStorage.setItem("pf.fflow", flows ? "1" : "0"); } catch {} draw(); };
    $("#f-proj").onchange = e => { pid = e.target.value; try { localStorage.setItem("pf.fproj", pid); } catch {} draw(); };
    $("#f-full").onclick = () => { const w = $("#fwrap"); document.fullscreenElement ? document.exitFullscreen() : w.requestFullscreen && w.requestFullscreen(); };
    const ed = $("#f-edit"); if (ed) ed.onclick = () => { edit = true; draw(); };
    const ca = $("#f-cancel"); if (ca) ca.onclick = () => { edit = false; draw(); };
    const rs = $("#f-reset"); if (rs) rs.onclick = async () => { await act(() => PUT("/api/floor/layout", { reset: true }), "Grąžintas automatinis išdėstymas"); edit = false; draw(); };
    const sv = $("#f-save"); if (sv) sv.onclick = async () => {
      await act(() => PUT("/api/floor/layout", { areas: model.areas.filter(a => a.id).map(a => ({ id: a.id, ...a.box })),
        centres: model.areas.flatMap(a => a.centres.map(c => ({ id: c.id, ...c.box }))) }), "Išdėstymas išsaugotas");
      edit = false; draw();
    };
    render();
  };

  // tempimas: SVG koordinatės iš pelės / piršto, žingsnis – 0,5 m
  const wireEdit = () => {
    const svg = $("#fsvg");
    const pt = ev => { const p = svg.createSVGPoint(); p.x = ev.clientX; p.y = ev.clientY; return p.matrixTransform(svg.getScreenCTM().inverse()); };
    const snap = v => Math.round(v * 2) / 2;
    svg.onpointerdown = ev => {
      const rz = ev.target.dataset.rz, cg = ev.target.closest(".fc"), ag = ev.target.closest(".farea");
      if (!ag) return;
      ev.preventDefault();
      const a = model.areas.find(x => String(x.id) === ag.dataset.area);
      const c = cg ? a.centres.find(x => String(x.id) === cg.dataset.c) : null;
      const target = c ? c.box : a.box, start = pt(ev), b0 = { ...target };
      // tempiant keičiamas tik tempiamas elementas: perpiešus visą SVG,
      // naršyklė prarastų tempimą po pirmo judesio
      const g = cg || ag, rect = g.querySelector(c ? ".fcr" : ".far"), handle = g.querySelector(`.rz[data-rz="${c ? "c" : "a"}"]`);
      svg.setPointerCapture(ev.pointerId);
      svg.onpointermove = m => {
        const p = pt(m), dx = p.x - start.x, dy = p.y - start.y;
        if (rz) { target.w = Math.max(c ? 3 : 6, snap(b0.w + dx)); target.h = Math.max(c ? 2.5 : 5, snap(b0.h + dy)); }
        else { target.x = Math.max(0, snap(b0.x + dx)); target.y = Math.max(0, snap(b0.y + dy)); }
        if (c) {                                         // centras – baro viduje
          target.w = Math.min(target.w, a.box.w); target.h = Math.min(target.h, a.box.h - 2);
          target.x = Math.min(target.x, a.box.w - target.w); target.y = Math.max(2.5, Math.min(target.y, a.box.h - target.h));
        }
        g.setAttribute("transform", `translate(${target.x},${target.y})`);
        rect.setAttribute("width", target.w); rect.setAttribute("height", target.h);
        if (handle) { const k = c ? 1 : 1.4; handle.setAttribute("x", target.w - k); handle.setAttribute("y", target.h - k); }
      };
      svg.onpointerup = () => {
        svg.onpointermove = svg.onpointerup = null;
        model.size.w = Math.max(...model.areas.map(x => x.box.x + x.box.w)); model.size.h = Math.max(...model.areas.map(x => x.box.y + x.box.h));
        render();
      };
    };
  };

  await draw();
  S.timers.push(setInterval(() => { if (!edit && $("#modal").hidden && location.hash.startsWith("#/cechas")) draw(); }, 10000));
  S.timers.push(setInterval(() => $$("#fsvg [data-since]").forEach(el => el.dataset.since && (el.textContent = dur(+el.dataset.base + since(el.dataset.since)))), 1000));
}

function centreModal(c, a) {
  const t = c.task;
  modal(`<div class="row between"><h2><span class="mono">${esc(c.code)}</span> ${esc(c.name)}</h2>${pill(c.state, ST_LABEL[c.state])}</div>
    <p class="muted">${esc(a.name)}${c.manual ? "" : " · staklės"}${c.needs_files ? " · reikia programos failo" : ""}</p>
    ${c.alerts.map(x => `<div class="${x.severity === "red" ? "lock" : "warn"}">⚠ ${esc(x.text)}</div>`).join("")}
    ${t ? `<div class="card"><b>${esc(t.project_code)} · ${esc(t.assembly_code)}</b> ${esc(t.name)}
      <div class="muted">${t.qty_good}/${t.qty_plan} vnt.${t.norm_min ? ` · norma ${t.norm_min} min/vnt` : ""}${c.who ? ` · ${esc(c.who)}` : ""}</div>
      <div class="timer-s mono">${dur((c.work_s || 0) + (c.state === "dirba" && c.since ? since(c.since) : 0))}</div>
      ${c.pause ? `<div class="warn">⏸ ${esc(c.pause)}</div>` : ""}</div>`
      : c.next ? `<p>Kitas eilėje: <b>${esc(c.next.project_code)} · ${esc(c.next.assembly_code)}</b> ${esc(c.next.name)}</p>${c.lock ? `<p class="lock">🔒 ${esc(c.lock)}</p>` : ""}` : `<p class="muted">Eilėje darbų nėra.</p>`}
    ${c.calendar && !c.calendar.working ? `<p class="offc">⏾ ${esc(c.calendar.why)}${c.calendar.next ? ` · darbas nuo ${dt(c.calendar.next)}` : ""}</p>` : ""}
    <p>Eilėje: <b>${c.queue}</b>${c.waiting ? ` · atkeliavusių detalių laukia: <b>${c.waiting}</b>` : ""}</p>
    <div class="row">${can("execute") ? `<a class="btn" href="#/t/${esc(c.code)}">Terminalas</a>` : ""}${can("plan") ? `<a class="btn ghost" href="#/planas/${esc(c.code)}">Centro eilė</a>` : ""}${can("view") ? `<a class="btn ghost" href="#/planas/kalendorius/centre/${c.id}">Kalendorius</a>` : ""}
      <button class="ghost" id="cm-x">Uždaryti</button></div>`, () => { $("#cm-x").onclick = closeModal; });
}

// ---------- planas ----------
// skyriai (planas, eilės, kalendorius, apkrova) – modulio juostoje viršuje
const planTabs = () => "";

async function pagePlan(code) {
  if (!code) return pagePlanner();
  const centres = await GET("/api/centres");
  if (code === "eiles") code = null;
  code = code || localStorage.getItem("pf.plan") || (centres[0] && centres[0].code);
  if (!code) { app().innerHTML = `<p class="pad">Darbo centrų nėra.</p>`; return; }
  localStorage.setItem("pf.plan", code);
  const r = await GET(`/api/plan/${code}`);
  const unapproved = r.tasks.filter(t => !t.approved).length;
  // meistras eilę tvarko tik savo baruose, kitų barų – tik mato
  const mine = canAt("plan", r.centre.code, r.centre.area_code);
  app().innerHTML = `<div class="row between"><h1>Planavimas</h1>
    <select id="pc">${centreOptions(centres, code)}</select></div>${planTabs("q")}
  <div class="card"><div class="row between"><h2>${esc(r.centre.code)} ${esc(r.centre.name)}</h2>
    ${mine ? `<button id="appr" ${unapproved ? "" : "disabled"}>Patvirtinti eilę${unapproved ? ` (${unapproved} naujos)` : ""}</button>` : `<span class="tag">ne jūsų baras – tik peržiūra</span>`}</div>
    <p class="muted">Terminalas rodo tik patvirtintas užduotis. ${r.centre.strict_order ? "Šiame centre griežta eilė: pradėti galima tik pirmą." : "Operatorius gali rinktis iš eilės."}
      Prognozė – pagal eilę, normas ir <a href="#/planas/kalendorius/centre/${r.centre.id}">centro darbo kalendorių</a>.</p>
    <div class="tbl"><table><thead><tr><th>#</th><th>Projektas · mazgas</th><th>Operacija</th><th>Kiekis</th><th>Terminas</th><th>Prognozė</th><th>Būsena</th><th>Kliūtis</th><th></th></tr></thead>
    <tbody>${r.tasks.map((t, i) => `<tr class="${t.approved ? "" : "dim"}">
      <td class="num">${i + 1}</td><td><b class="mono">${esc(t.project_code)}</b> · ${esc(t.assembly_code)} ${esc(t.assembly_name)}</td>
      <td>${esc(t.name)}${t.part_no ? ` <span class="muted mono">${esc(t.part_no)}</span>` : ""}<div class="muted small">→ ${t.next.map(d => d.task_id ? esc(d.centre_code) : esc(d.label)).join(", ")}</div></td>
      <td class="num">${t.qty_good}/${t.qty_plan}</td><td class="num">${esc(t.due_date || "—")} <span class="muted">P${t.priority}</span></td>
      <td>${fcCell(t.forecast)}</td>
      <td>${pill(t.status, t.status)} ${t.approved ? "" : '<span class="muted">nepatvirtinta</span>'}</td>
      <td class="lock">${esc(t.lock || "")}${t.components_missing ? `<div class="warn">⚠ negauti komponentai: ${t.components_missing} eil.</div>` : ""}</td>
      <td class="row" style="flex-wrap:nowrap">${mine ? `<button class="small ghost" data-mv="top" data-id="${t.id}" title="Į pradžią">⤒</button>
        <button class="small ghost" data-mv="up" data-id="${t.id}">▲</button><button class="small ghost" data-mv="down" data-id="${t.id}">▼</button>` : ""}</td></tr>`).join("")
      || `<tr><td colspan="9" class="muted">Eilėje užduočių nėra.</td></tr>`}</tbody></table></div></div>`;
  $("#pc").onchange = e => (location.hash = `#/planas/${e.target.value}`);
  const ap = $("#appr"); if (ap) ap.onclick = async () => { await act(() => POST(`/api/plan/${code}/approve`), "Eilė patvirtinta"); pagePlan(code); };
  $$("[data-mv]").forEach(b => b.onclick = async () => {
    const r = await act(() => POST(`/api/tasks/${b.dataset.id}/move`, { where: b.dataset.mv }));
    // perkėlimas eilėje signalizuoja projektams, kurių darbai pasislinko
    if (r.affected && r.affected.length) toast(`Pranešta: ${r.affected.map(a => a.code).join(", ")} – jų darbai eilėje pasislinko`);
    pagePlan(code);
  });
}

// ---------- darbo kalendorius: gamykla → baras → centras, metų vaizdas ----------
// Spustelėjus dieną (ar pele pažymėjus kelias) – išimtis: nedarbo diena,
// remontas, papildomas darbas, kitas laikas. Įrašius serveris parodo, kurių
// projektų operacijos dėl to pasislinko, ir jiems praneša.
const CAL_KIND = { darbo: "Darbo diena", poilsio: "Poilsio diena", svente: "Šventė", nedarbo: "Nedarbo diena",
  remontas: "Remontas / priežiūra", papildomas: "Papildomas darbas", kitas: "Kitas darbo laikas" };
const MONTHS = ["Sausis", "Vasaris", "Kovas", "Balandis", "Gegužė", "Birželis", "Liepa", "Rugpjūtis", "Rugsėjis", "Spalis", "Lapkritis", "Gruodis"];
const WD = ["Pr", "An", "Tr", "Kt", "Pn", "Št", "Sk"];
// savaitė glaustai: vienodos iš eilės dienos – viena dalis („Pr–Pn 07:00-15:30“)
const weekText = week => {
  const out = [];
  week.forEach((w, i) => { const l = out[out.length - 1]; if (l && l.w === w && l.b === i - 1) l.b = i; else out.push({ w, a: i, b: i }); });
  return out.filter(x => x.w).map(x => `${WD[x.a]}${x.b > x.a ? "–" + WD[x.b] : ""} ${x.w}`).join(" · ") || "be darbo dienų";
};
const calTip = x => `${x.date} ${WD[(new Date(x.date + "T00:00:00Z").getUTCDay() + 6) % 7]} · ${CAL_KIND[x.kind]}${x.note ? `: ${x.note}` : ""}\n${x.minutes ? `${x.hours} (${Math.round(x.minutes / 6) / 10} val.)` : "nedirbama"}${x.src && !x.own ? `\npaveldėta: ${x.src.startsWith("factory") ? "gamykla" : x.src.startsWith("area") ? "baras" : "centras"}` : ""}`;

async function pageCalendar(scope, id) {
  scope = scope || "factory"; id = +(id || 0);
  let year = S.calYear || +today().slice(0, 4);
  const [areas, centres] = await Promise.all([GET("/api/areas"), GET("/api/centres")]);
  const draw = async () => {
    const [r, pats] = await Promise.all([GET(`/api/calendar?scope=${scope}&id=${id}&year=${year}`), GET("/api/calendar/patterns")]);
    // meistras – tik savo barų ir jų centrų kalendorių; gamyklos – planuotojas, vadovas
    const edit = can("calendar") && (S.me.scope === "all" || (scope === "area" && canAt("calendar", "", (areas.find(a => a.id === id) || {}).code))
      || (scope === "centre" && (c => c && canAt("calendar", c.code, c.area_code))(centres.find(c => c.id === id))));
    const byDate = Object.fromEntries(r.days.map(x => [x.date, x]));
    const now = today();
    const month = m => {
      const first = new Date(Date.UTC(year, m, 1)), pad = (first.getUTCDay() + 6) % 7, n = new Date(Date.UTC(year, m + 1, 0)).getUTCDate();
      const cells = Array(pad).fill(`<span></span>`);
      for (let d = 1; d <= n; d++) {
        const iso = `${year}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`, x = byDate[iso];
        cells.push(`<button class="cday k-${x.kind} ${x.own ? "own" : x.src ? "inh" : ""} ${x.kind === "remontas" && x.minutes ? "part" : ""} ${iso === now ? "now" : ""}"
          data-d="${iso}" title="${esc(calTip(x))}" ${edit ? "" : "tabindex='-1'"}>${d}</button>`);
      }
      return `<div class="mcal"><b>${MONTHS[m]}</b><div class="mgrid">${WD.map(w => `<i>${w}</i>`).join("")}${cells.join("")}</div></div>`;
    };
    const srcLabel = { factory: "gamyklos", area: "baro", centre: "centro" }[r.pattern_src];
    app().innerHTML = `<div class="row between"><h1>Planavimas</h1>
      <div class="row"><select id="k-scope" aria-label="Kieno kalendorius"><option value="factory:0">Gamykla (visiems)</option>
        <optgroup label="Barai">${areas.map(a => `<option value="area:${a.id}" ${scope === "area" && a.id === id ? "selected" : ""}>${esc(a.code)} ${esc(a.name)}</option>`).join("")}</optgroup>
        ${byArea(centres).map(g => `<optgroup label="${esc(g.name)}">${g.items.map(c => `<option value="centre:${c.id}" ${scope === "centre" && c.id === id ? "selected" : ""}>${esc(c.code)} ${esc(c.name)}</option>`).join("")}</optgroup>`).join("")}</select>
        <button class="ghost small" id="k-prev" aria-label="Ankstesni metai">◀</button><b class="mono">${year}</b><button class="ghost small" id="k-next" aria-label="Kiti metai">▶</button></div></div>
    ${planTabs("k")}
    <div class="card"><div class="row between"><h2>${esc(r.name)}</h2><span class="muted">${year} m.: <b>${r.totals.work_days}</b> darbo d. · <b>${r.totals.hours}</b> val.</span></div>
      <div class="row calbar">
        <label>Pamainos ${edit ? `<select id="k-pat">${scope !== "factory" ? `<option value="">Paveldėti (${esc(r.own_pattern ? "" : r.pattern ? r.pattern.name : "—")})</option>` : ""}
          ${pats.map(p => `<option value="${p.id}" ${p.id === r.own_pattern ? "selected" : ""}>${esc(p.name)} · ${p.week_hours} val./sav.</option>`).join("")}</select>`
          : `<b>${esc(r.pattern ? r.pattern.name : "—")}</b>`}</label>
        <span class="muted small">${r.pattern ? `${r.pattern_src !== scope ? `paveldėta iš ${srcLabel} kalendoriaus · ` : ""}${esc(weekText(r.pattern.week))}` : ""}</span>
        ${edit && S.me.scope === "all" ? `<button class="ghost small" id="k-pats">Pamainų šablonai…</button>` : ""}</div>
      <div class="calleg muted small">${["darbo", "poilsio", "svente", "nedarbo", "remontas", "papildomas", "kitas"].map(k => `<span><i class="cday k-${k}"></i>${CAL_KIND[k]}</span>`).join("")}
        <span><i class="cday k-darbo own"></i>šio kalendoriaus išimtis</span><span><i class="cday k-nedarbo inh"></i>paveldėta</span></div>
      <p class="muted small">${edit ? "Spustelėkite dieną arba pele pažymėkite kelias – nurodysite nedarbo dieną, remontą, papildomą darbą ar kitą laiką. " : ""}Centras paveldi baro ir gamyklos kalendorių (šventės, uždarymai), baras – gamyklos.</p>
      <div class="yrcal" id="k-year">${MONTHS.map((_, m) => month(m)).join("")}</div></div>
    <div class="card"><h2>Išimtys ${year} m.</h2>
      <div class="tbl"><table><thead><tr><th>Kada</th><th>Kur</th><th>Rūšis</th><th>Laikas</th><th>Pastaba</th><th></th></tr></thead><tbody>
      ${r.exceptions.map(e => `<tr><td class="num">${e.from}${e.to !== e.from ? ` – ${e.to} <span class="muted">(${e.days} d.)</span>` : ""}</td>
        <td>${e.own ? esc(e.where) : `<a href="#/planas/kalendorius/${e.level[0]}/${e.level[1]}">${esc(e.where)}</a>`}</td>
        <td><i class="cday k-${e.kind}"></i> ${esc(e.label)}</td><td class="mono">${esc(e.hours || (e.kind === "remontas" ? "visa diena" : ""))}</td><td>${esc(e.note)}</td>
        <td>${edit && e.own ? `<button class="small ghost" data-rm="${e.from}|${e.to}">Pašalinti</button>` : e.own ? "" : '<span class="muted small">paveldėta</span>'}</td></tr>`).join("")
        || `<tr><td colspan="6" class="muted">Išimčių nėra – dirbama pagal pamainų šabloną, išskyrus šventes.</td></tr>`}</tbody></table></div>
      <details><summary class="muted">Valstybinės šventės (${r.holidays.length})</summary><ul class="small">${r.holidays.map(h => `<li><span class="mono">${h.date}</span> ${esc(h.name)}</li>`).join("")}</ul></details></div>`;
    $("#k-scope").value = `${scope}:${id}`;
    $("#k-scope").onchange = e => { const [s, i] = e.target.value.split(":"); location.hash = s === "factory" ? "#/planas/kalendorius" : `#/planas/kalendorius/${s}/${i}`; };
    $("#k-prev").onclick = () => { year--; S.calYear = year; draw(); };
    $("#k-next").onclick = () => { year++; S.calYear = year; draw(); };
    if (!edit) return;
    $("#k-pat").onchange = async e => calSaved(await act(() => PUT("/api/calendar/pattern", { scope, scope_id: id, pattern_id: e.target.value ? +e.target.value : null })), draw);
    const kp = $("#k-pats"); if (kp) kp.onclick = () => patternsModal(pats, draw);
    $$("[data-rm]").forEach(b => b.onclick = async () => {
      const [a, z] = b.dataset.rm.split("|");
      calSaved(await act(() => POST("/api/calendar/days", { scope, scope_id: id, from: a, to: z, kind: "iprasta" })), draw);
    });
    // pele – tempiant pažymimos kelios dienos; pirštu ar klaviatūra – viena (intervalą galima pakeisti lange)
    const grid = $("#k-year"); let sel = null, byMouse = 0;
    const mark = () => $$(".cday[data-d]", grid).forEach(c => c.classList.toggle("sel", !!sel && c.dataset.d >= sel[0] && c.dataset.d <= sel[1]));
    grid.onpointerdown = ev => {
      const c = ev.target.closest(".cday[data-d]"); if (!c || ev.pointerType !== "mouse" || ev.button) return;
      ev.preventDefault(); const a = c.dataset.d; sel = [a, a]; mark();
      grid.onpointerover = m => { const o = m.target.closest(".cday[data-d]"); if (o) { sel = [a, o.dataset.d].sort(); mark(); } };
      document.addEventListener("pointerup", () => {
        grid.onpointerover = null; const s = sel; sel = null; mark(); byMouse = Date.now(); dayModal(r, s[0], s[1], draw);
      }, { once: true });
    };
    grid.onclick = ev => {
      const c = ev.target.closest(".cday[data-d]");
      if (c && Date.now() - byMouse > 400) dayModal(r, c.dataset.d, c.dataset.d, draw);
    };
  };
  await draw();
}

function dayModal(r, a, z, after) {
  const x = r.days.find(d => d.date === a) || {};
  // poilsio dienai ar šventei dažniausiai žymimas papildomas darbas, darbo dienai – nedarbo
  const pre = a === z && x.own ? x.kind : x.minutes ? "nedarbo" : "papildomas";
  const def = r.pattern ? (r.pattern.week.find(Boolean) || "07:00-15:30") : "07:00-15:30";
  const kinds = [["iprasta", "Įprasta – pašalinti išimtį"], ...Object.entries(r.kinds)];
  modal(`<h2>${esc(r.name)}: dienos</h2>
    <p class="muted small">${esc(calTip(x).split("\n")[0])}</p>
    <div class="row"><label>Nuo<input type="date" id="cd-a" value="${a}"></label><label>Iki<input type="date" id="cd-b" value="${z}"></label></div>
    <div class="ckinds">${kinds.map(([k, l]) => `<label class="row" style="display:flex"><input type="radio" name="cd-k" value="${k}" ${k === pre ? "checked" : ""}><i class="cday k-${k === "iprasta" ? "darbo" : k}"></i>${esc(l)}</label>`).join("")}</div>
    <label id="cd-hl">Laikas<input id="cd-h" placeholder="pvz. 07:00-15:30" value="${esc(a === z && x.own && x.kind !== "nedarbo" ? x.hours : "")}" autocomplete="off"></label>
    <p class="muted small" id="cd-hint"></p>
    <label>Pastaba<input id="cd-n" value="${esc(a === z && x.own ? x.note : "")}" placeholder="pvz. lazerio servisas, kolektyvinės atostogos"></label>
    <label class="row" style="display:flex"><input type="checkbox" id="cd-w"> tik darbo dienoms (praleisti savaitgalius ir šventes)</label>
    <div class="row"><button id="cd-ok">Įrašyti</button><button class="ghost" id="cd-x">Atšaukti</button></div>`, box => {
    const k = () => $("input[name=cd-k]:checked", box).value;
    const upd = () => {
      const v = k();
      $("#cd-hl").hidden = v === "iprasta" || v === "nedarbo";
      $("#cd-hint").textContent = { remontas: "Tuščia – visa diena. Su laiku – centras nedirba tik tuo metu (pvz. 07:00-11:00).",
        papildomas: "Pridedama prie įprasto darbo laiko: šeštadienio pamaina ar viršvalandžiai (pvz. 15:30-19:30).",
        kitas: "Pakeičia dienos laiką, pvz. sutrumpinta diena ar darbas šventės dieną.", nedarbo: "Tą dieną nedirbama: gamyklos uždarymas, kolektyvinės atostogos.",
        iprasta: "Išimtis pašalinama – dirbama pagal pamainų šabloną (šventės lieka)." }[v];
      if ((v === "papildomas" || v === "kitas") && !$("#cd-h").value) $("#cd-h").value = v === "papildomas" ? "07:00-13:00" : def;
    };
    $$("input[name=cd-k]", box).forEach(i => i.onchange = upd); upd();
    $("#cd-x").onclick = closeModal;
    $("#cd-ok").onclick = async () => {
      const v = k();
      const res = await act(() => POST("/api/calendar/days", { scope: r.scope, scope_id: r.scope_id, from: $("#cd-a").value, to: $("#cd-b").value || $("#cd-a").value,
        kind: v, hours: v === "nedarbo" || v === "iprasta" ? "" : $("#cd-h").value, note: $("#cd-n").value, workdays_only: $("#cd-w").checked }));
      calSaved(res, after);
    };
  });
}

// po kalendoriaus pakeitimo – kas paveikta (operacijos vėliau, apkrova) ir kam pranešta
function calSaved(r, after) {
  closeModal(); after && after();
  if (!r) return;
  const n = r.affected.length;
  if (!n && !r.freed.length) { toast(`${r.summary}${r.days !== undefined ? ` · ${r.days} d.` : ""} – kitų darbų nepaveikė`); return; }
  modal(`<h2>Kalendorius pakeistas</h2><p><b>${esc(r.summary)}</b></p>
    ${n ? `<div><b>Paveikti projektai (${n})</b> <span class="muted small">– jų vadovams, atsakingiesiems ir planuotojams išsiųstas pranešimas</span>
      <div class="aff">${r.affected.map(a => `<div class="affrow ${a.severity}"><div><span class="sev ${a.severity}">${esc(SEV_LABEL[a.severity])}</span> <b class="mono">${esc(a.code)}</b> ${esc(a.name)}</div>
        <ul>${a.reasons.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`).join("")}</div></div>` : ""}
    ${r.freed.length ? `<div><b>Pagerėjo</b><ul class="muted small">${r.freed.map(f => `<li>${esc(f)}</li>`).join("")}</ul></div>` : ""}
    <div><button id="cs-x">Gerai</button></div>`, () => { $("#cs-x").onclick = closeModal; });
}

function patternsModal(pats, after) {
  const form = p => `<form id="pt-f" class="ptform"><input type="hidden" name="id" value="${p ? p.id : ""}">
    <label>Pavadinimas<input name="name" required value="${esc(p ? p.name : "")}"></label>
    ${WD.map((w, i) => `<label class="row" style="display:flex"><span class="mono" style="width:24px">${w}</span><input name="w${i}" value="${esc(p ? p.week[i] : i < 5 ? "07:00-11:00, 11:30-15:30" : "")}" placeholder="nedirbama" autocomplete="off"></label>`).join("")}
    <p class="muted small">Kelios dalys – per kablelį (pertrauka – tarpas tarp jų). Vietinis laikas. Naktinė pamaina – dviem dalimis: 22:00-24:00 ir kitą dieną 00:00-06:00.</p>
    <div class="row"><button>${p ? "Įrašyti" : "Sukurti"}</button><button type="button" class="ghost" id="pt-back">Atgal</button></div></form>`;
  const list = () => modal(`<h2>Pamainų šablonai</h2>
    <div class="tbl"><table><thead><tr><th>Šablonas</th><th>Val./sav.</th><th>Naudoja</th><th></th></tr></thead><tbody>
    ${pats.map(p => `<tr><td><b>${esc(p.name)}</b><div class="muted small">${esc(weekText(p.week))}</div></td>
      <td class="num">${p.week_hours}</td><td class="small">${p.factory ? "<b>gamykla</b> " : ""}${esc(p.used_by.join(", "))}</td>
      <td><button class="small ghost" data-pe="${p.id}">Keisti</button></td></tr>`).join("")}</tbody></table></div>
    <div class="row"><button id="pt-new">+ Naujas šablonas</button><button class="ghost" id="pt-x">Uždaryti</button></div>`, () => {
    $("#pt-x").onclick = closeModal;
    $("#pt-new").onclick = () => edit(null);
    $$("[data-pe]").forEach(b => b.onclick = () => edit(pats.find(p => p.id === +b.dataset.pe)));
  });
  const edit = p => modal(`<h2>${p ? `Šablonas „${esc(p.name)}“` : "Naujas pamainų šablonas"}</h2>
    ${p && (p.factory || p.used_by.length) ? `<p class="warn">Šabloną naudoja ${p.factory ? "gamykla" : ""}${p.factory && p.used_by.length ? ", " : ""}${esc(p.used_by.join(", "))} – pakeitimas paveiks jų prognozę ir apkrovą.</p>` : ""}
    ${form(p)}`, box => {
    $("#pt-back").onclick = list;
    $("#pt-f").onsubmit = async e => {
      e.preventDefault();
      const f = formData(e.target), body = { name: f.name, week: WD.map((_, i) => f[`w${i}`]) };
      const r = await act(() => p ? PUT(`/api/calendar/patterns/${p.id}`, body) : POST("/api/calendar/patterns", body));
      if (!r) return;
      if (p) calSaved(r, after); else { closeModal(); toast("Šablonas sukurtas – priskirkite jį gamyklai, barui ar centrui"); after(); }
    };
  });
  list();
}

// prognozė: kada operacija prasidės ir baigsis pagal eilę, normas ir kalendorių
function fcCell(f) {
  if (!f) return '<span class="muted">—</span>';
  if (f.no_time) return '<span class="lock">centras nedirba – laiko nėra</span>';
  return `<span class="fcst ${f.late ? "late" : ""}" title="${esc(`Pradžia ${dt(f.start)}, pabaiga ${dt(f.end)}${f.due ? `\nEtapo terminas ${f.due}` : ""}${f.wait ? `\nLaukia: ${f.wait}` : ""}${f.norm ? "" : "\nBe normos – trukmė nežinoma"}`)}">
    <span class="nw">${dt(f.start)} → <b>${dt(f.end)}</b></span>${f.late ? `<span class="s-late small"> · nespės iki ${esc(f.due)}</span>` : ""}
    ${f.wait ? `<div class="muted small">po ${esc(f.wait)}</div>` : ""}${f.pending ? `<div class="muted small">jei paleista dabar – ${esc(f.pending)}</div>` : ""}${f.loop ? `<div class="lock">eilė prieštarauja maršrutui</div>` : ""}${f.norm ? "" : `<div class="muted small">be normos</div>`}</span>`;
}

// ---------- pranešimai (varpelis) ----------
const SEV_LABEL = { red: "Kritiška", yellow: "Dėmesio", info: "Informacija", good: "Pagerėjo" };
const KIND_LABEL = { phase: "Etapo datos", priority: "Prioritetas", queue: "Centro eilė", activate: "Naujas projektas",
  shop_delay: "Vėlavimas ceche", component_delay: "Komponentai", calendar: "Darbo kalendorius" };
async function bellCount() {
  if (!S.me) return;
  try {
    const r = await GET("/api/notifications/count");
    const n = $("#bell-n"); n.hidden = !r.unread; n.textContent = r.unread > 99 ? "99+" : r.unread;
  } catch {}
}
// kas minutę – ne per S.timers, nes juos išvalo kiekvienas puslapio keitimas
setInterval(() => { if (S.me && !document.hidden) bellCount(); }, 60000);
$("#bell").onclick = async () => {
  const r = await GET("/api/notifications");
  bellCount();
  modal(`<div class="row between"><h2>Pranešimai</h2>${r.unread ? `<button class="ghost small" id="nt-all">Pažymėti visus perskaitytais</button>` : ""}</div>
    <p class="muted small">Plano pokyčiai, paveikę jūsų projektus: kitų projektų perkėlimai, vėlavimai ceche, komponentai, nauji projektai.</p>
    <div class="ntlist">${r.items.map(n => `<a class="nt ${n.read_at ? "" : "unread"}" href="${esc(n.link || "#/planas")}" data-nt="${n.id}">
      <i class="hdot ${LEVEL_CLS[n.severity === "red" ? "red" : n.severity === "yellow" ? "yellow" : "green"]}" title="${esc(SEV_LABEL[n.severity] || "")}"></i>
      <div><b>${esc(n.title)}</b><div class="muted small">${esc(KIND_LABEL[n.kind] || n.kind)} · ${dt(n.created)}</div>
      <div class="ntbody">${esc(n.body)}</div></div></a>`).join("") || `<p class="muted">Pranešimų nėra.</p>`}</div>
    <div><button class="ghost" id="nt-x">Uždaryti</button></div>`, box => {
    $("#nt-x").onclick = closeModal;
    const all = $("#nt-all"); if (all) all.onclick = async () => { await POST("/api/notifications/read", {}); closeModal(); bellCount(); };
    $$("[data-nt]", box).forEach(a => a.onclick = () => { POST("/api/notifications/read", { ids: [+a.dataset.nt] }).then(bellCount); closeModal(); });
  });
};

// ---------- planuotojo Gantt: visų departamentų darbai laike ----------
// Juostą galima tempti (perkelti) arba tempti dešinį kraštą (keisti pabaigą);
// prieš įrašant serveris parodo poveikį kitiems projektams.
const DAY = 864e5;
const isoAdd = (iso, n) => new Date(Date.parse(iso + "T00:00:00Z") + n * DAY).toISOString().slice(0, 10);
const dayDiff = (a, b) => Math.round((Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / DAY);

async function pagePlanner() {
  let weeks = 12, basket = true, focus = "";
  try { weeks = +(localStorage.getItem("pf.gw") || 12); basket = localStorage.getItem("pf.gb") !== "0"; } catch {}
  let dragging = false;
  const draw = async () => {
    const [r, ch] = await Promise.all([GET(`/api/planner?weeks=${weeks}&basket=${basket ? 1 : 0}`), GET("/api/planner/changes?limit=25")]);
    const total = weeks * 7, x = d => Math.max(0, Math.min(100, dayDiff(r.start, d) / total * 100));
    const color = Object.fromEntries(r.projects.map((p, i) => [p.id, PROJ_COLORS[i % PROJ_COLORS.length]]));
    const pcode = Object.fromEntries(r.projects.map(p => [p.id, p]));
    const lanes = bars => {           // persidengiančios juostos – į atskiras eilutes
      const out = [];
      [...bars].sort((a, b) => a.plan_start.localeCompare(b.plan_start)).forEach(b => {
        const l = out.find(l => l[l.length - 1].plan_end < b.plan_start); (l || (out[out.length] = [])).push(b);
      });
      return out;
    };
    const bar = b => {
      const p = pcode[b.project_id], s = Math.max(0, dayDiff(r.start, b.plan_start)), e = dayDiff(r.start, b.plan_end) + 1;
      if (e <= 0 || s >= total) return "";
      const dim = focus && +focus !== b.project_id ? "dim" : "";
      const tip = `${p.code} ${p.name}\n${b.assembly ? "Mazgas " + b.assembly + " · " : ""}${b.label} · ${b.plan_start} – ${b.plan_end}\n${b.status}${b.owner ? " · " + b.owner : ""}${b.share ? ` · ${b.share} val.` : ""}${b.late ? "\nVĖLUOJA" : ""}`;
      return `<div class="gb ${p.status === "krepselis" ? "basket" : ""} ${b.status === "baigta" ? "done" : ""} ${b.late || b.late_start ? "late" : ""} ${dim}"
        style="left:${x(b.plan_start)}%;width:${Math.max(0.6, (Math.min(e, total) - s) / total * 100)}%;--pc:${color[b.project_id]}"
        data-ph="${b.phase_id}" data-s="${b.plan_start}" data-e="${b.plan_end}" title="${esc(tip)}" tabindex="0">
        <span>${esc(p.code)}${b.assembly ? " " + esc(b.assembly) : ""} · ${esc(b.label)}</span>${b.status !== "baigta" ? '<i class="gh" title="Tempkite – keisti pabaigą"></i>' : ""}</div>`;
    };
    const today = x(r.today);
    app().innerHTML = `<div class="row between"><h1>Planavimas</h1>
      <div class="row"><label class="row" style="display:flex"><input type="checkbox" id="g-b" ${basket ? "checked" : ""}> krepšelio projektai</label>
        <select id="g-w" aria-label="Laikotarpis">${[8, 12, 16, 24].map(n => `<option value="${n}" ${n === weeks ? "selected" : ""}>${n} sav.</option>`).join("")}</select></div></div>
    ${planTabs("g")}
    <div class="card"><div class="row between"><h2>Projektai</h2><span class="muted small">Spustelėkite projektą – paryškinsite jo darbus. Prioritetą keiskite čia – parodomas poveikis kitiems.</span></div>
      <div class="plegend">${r.projects.map(p => `<div class="pl ${focus && +focus === p.id ? "on" : ""}" style="--pc:${color[p.id]}">
        <button class="ghost small" data-focus="${p.id}"><i></i><b class="mono">${esc(p.code)}</b> ${esc(p.name)}</button>
        ${can("plan") || can("projects") ? `<select data-prio="${p.id}" aria-label="Prioritetas ${esc(p.code)}">${[1, 2, 3, 4, 5].map(n => `<option value="${n}" ${n === p.priority ? "selected" : ""}>P${n}</option>`).join("")}</select>` : `<span class="muted">P${p.priority}</span>`}
        ${p.status === "krepselis" ? (can("projects") ? `<button class="small" data-act-p="${p.id}">Patvirtinti…</button>` : pill("krepselis", "krepšelis")) : ""}
        <span class="muted small nw">${p.due_date ? "iki " + esc(p.due_date) : ""}</span></div>`).join("")}</div></div>
    <div class="card gantt2"><div class="gwrap"><div class="gtable">
      <div class="ghead"><div class="glab"></div><div class="gtime">${r.weeks.map((w, i) => `<span style="left:${i / weeks * 100}%;width:${100 / weeks}%">${esc(w.label)}<small>${esc(w.start.slice(5))}</small></span>`).join("")}
        <i class="gtoday" style="left:${today}%"></i></div></div>
      ${r.departments.filter(d => d.bars.length || d.load.some(c => c.hours)).map(d => `<div class="grow">
        <div class="glab"><b>${esc(d.name)}</b><span class="muted small">${d.capacity_week} val./sav.</span></div>
        <div class="gtime">
          ${d.off.map(o => `<i class="goff k-${o.kind} ${o.off ? "" : "part"}" style="left:${x(o.d)}%;width:${100 / total}%" title="${esc(o.d + " · " + o.text)}"></i>`).join("")}
          <div class="gload">${d.load.map((c, i) => `<span class="${utilCls(c.util)}" style="left:${i / weeks * 100}%;width:${100 / weeks}%" title="${esc(r.weeks[i].label)}: ${c.hours} val. iš ${d.capacity_week}${c.shortage ? ` – trūksta ${c.shortage} val.` : ""}">${c.util ? Math.round(c.util * 100) + "%" : ""}</span>`).join("")}</div>
          ${lanes(d.bars).map(l => `<div class="glane">${l.map(bar).join("")}</div>`).join("")}
          <i class="gtoday" style="left:${today}%"></i></div></div>`).join("")}
    </div></div>
    <p class="muted small">Juostos – etapų planas departamentuose (gamybos baruose – pagal operacijas). Viršuje – savaitės apkrova. Raudonas kraštas – vėluoja, brūkšniuota – krepšelio projektas. Fone – <a href="#/planas/kalendorius">darbo kalendorius</a>: pilka – nedirbama, raudona – šventė ar uždaryta, žalia – papildomas darbas, ochra – remontas. Tempkite juostą arba jos dešinį kraštą; spustelėję – keisti datas.</p></div>
    <div class="card"><h2>Pokyčių signalai</h2>${changesList(ch)}</div>`;
    $("#g-b").onchange = e => { basket = e.target.checked; try { localStorage.setItem("pf.gb", basket ? "1" : "0"); } catch {} draw(); };
    $("#g-w").onchange = e => { weeks = +e.target.value; try { localStorage.setItem("pf.gw", weeks); } catch {} draw(); };
    $$("[data-focus]").forEach(b => b.onclick = () => { focus = focus === b.dataset.focus ? "" : b.dataset.focus; draw(); });
    $$("[data-prio]").forEach(sel => sel.onchange = () => impactModal({ kind: "priority", project_id: +sel.dataset.prio, priority: +sel.value }, draw, draw));
    $$("[data-act-p]").forEach(b => b.onclick = () => impactModal({ kind: "activate", project_id: +b.dataset.actP }, draw));
    $$(".gb[data-ph]").forEach(el => wireBar(el, r, total, () => (dragging = true), draw));
  };
  await draw();
  S.timers.push(setInterval(() => { if ($("#modal").hidden && !dragging && location.hash === "#/planas") draw(); }, 60000));
}

function wireBar(el, r, total, onDrag, redraw) {
  const s0 = el.dataset.s, e0 = el.dataset.e, id = +el.dataset.ph;
  const open = (s, e) => impactModal({ kind: "phase", phase_id: id, plan_start: s, plan_end: e }, redraw, redraw);
  const edit = () => modal(`<h2>Etapo datos</h2><p>${esc(el.title.split("\n").slice(0, 2).join(" · "))}</p>
    <div class="row"><label>Pradžia<input type="date" id="bp-s" value="${s0}"></label><label>Pabaiga<input type="date" id="bp-e" value="${e0}"></label></div>
    <div class="row"><button id="bp-ok">Peržiūrėti poveikį</button><button class="ghost" id="bp-x">Atšaukti</button></div>`, () => {
    $("#bp-x").onclick = closeModal;
    $("#bp-ok").onclick = () => open($("#bp-s").value, $("#bp-e").value);
  });
  el.onkeydown = e => { if (e.key === "Enter") edit(); };
  if (!(can("plan") || can("projects")) || el.classList.contains("done")) { el.onclick = edit; return; }
  el.onpointerdown = ev => {
    ev.preventDefault();
    const resize = ev.target.classList.contains("gh");
    const pxPerDay = el.parentElement.getBoundingClientRect().width / total;
    const startX = ev.clientX, left0 = parseFloat(el.style.left), w0 = parseFloat(el.style.width);
    let days = 0;
    el.setPointerCapture(ev.pointerId); el.classList.add("drag"); onDrag();
    el.onpointermove = m => {
      days = Math.round((m.clientX - startX) / pxPerDay);
      if (resize) el.style.width = Math.max(100 / total, w0 + days * 100 / total) + "%";
      else el.style.left = left0 + days * 100 / total + "%";
      el.querySelector("span").textContent = resize ? `pabaiga ${isoAdd(e0, days)}` : `${isoAdd(s0, days)} – ${isoAdd(e0, days)}`;
    };
    el.onpointerup = () => {
      el.onpointermove = el.onpointerup = null; el.classList.remove("drag");
      if (!days) return edit();                                   // paspaudimas, ne tempimas
      const s = resize ? s0 : isoAdd(s0, days), e = isoAdd(e0, days);
      if (resize && e < s0) return redraw();
      open(s, e);
    };
  };
}

function changesList(list) {
  return list.length ? `<div class="chg">${list.map(c => `<div class="chrow">
    <div class="muted small nw">${dt(c.at)}</div>
    <div><b>${esc(KIND_LABEL[c.kind] || c.kind)}</b> · ${esc(c.summary)}${c.user_name ? ` <span class="muted">– ${esc(c.user_name)}</span>` : ""}
      ${c.note ? `<div class="muted small">„${esc(c.note)}“</div>` : ""}
      ${(c.impact.affected || []).length ? `<div class="row" style="gap:4px;margin-top:3px">${c.impact.affected.map(a => `<span class="sev ${a.severity}" title="${esc(a.reasons.join("\n"))}">${esc(a.code || "")}</span>`).join("")}</div>` : `<div class="muted small">kitų projektų nepaveikė</div>`}</div></div>`).join("")}</div>`
    : `<p class="muted">Pokyčių dar nebuvo.</p>`;
}

// Poveikio peržiūra: ką pakeitimas padarys kitiems projektams – prieš įrašant
async function impactModal(change, after, onCancel) {
  let imp;
  try { imp = await POST("/api/planner/impact", change); } catch (e) { toast(e.message, true); onCancel && onCancel(); return; }
  const n = imp.affected.length;
  modal(`<h2>Pakeitimo poveikis</h2><p><b>${esc(imp.summary)}</b></p>
    ${imp.own.length ? `<div class="card warnbox">${imp.own.map(w => `<div class="warn">⚠ ${esc(w)}</div>`).join("")}</div>` : ""}
    ${n ? `<div><b>Paveikti projektai (${n})</b> <span class="muted small">– jų vadovams ir atsakingiesiems bus išsiųstas pranešimas</span>
      <div class="aff">${imp.affected.map(a => `<div class="affrow ${a.severity}"><div><span class="sev ${a.severity}">${esc(SEV_LABEL[a.severity])}</span> <b class="mono">${esc(a.code)}</b> ${esc(a.name)}</div>
        <ul>${a.reasons.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`).join("")}</div></div>`
      : `<p class="s-baigta">✓ Kitų projektų departamentai nepersikrauna, eilės nepasislenka.</p>`}
    ${imp.freed.length ? `<div><b>Atsilaisvina</b><ul class="muted small">${imp.freed.map(f => `<li>${esc(f)}</li>`).join("")}</ul></div>` : ""}
    <label>Pastaba (kodėl keičiama – matys paveiktieji)<input id="im-note" placeholder="pvz. užsakovas paprašė anksčiau"></label>
    <div class="row"><button id="im-ok">${n ? `Įrašyti ir pranešti (${n})` : "Įrašyti"}</button><button class="ghost" id="im-x">Atšaukti</button></div>`, () => {
    $("#im-x").onclick = () => { closeModal(); onCancel && onCancel(); };
    $("#im-ok").onclick = async () => {
      await act(() => POST("/api/planner/apply", { ...change, note: $("#im-note").value }), n ? `Įrašyta, pranešta ${n} projektams` : "Įrašyta");
      closeModal(); after && after();
    };
  });
}

// ---------- terminalas ----------
async function pageTerminal(code) {
  document.body.classList.add("term");
  // terminale – tik centrai, kuriuose žmogus gali dirbti
  const centres = (await GET("/api/centres")).filter(c => canAt("execute", c.code, c.area_code));
  if (!code) {
    const saved = localStorage.getItem("pf.term");
    if (saved && centres.some(c => c.code === saved)) { location.hash = `#/t/${saved}`; return; }
    app().innerHTML = `<div class="tm"><h1>Pasirinkite darbo centrą</h1>${byArea(centres).map(g => `<h2>${esc(g.name)}</h2>
      <div class="floor">${g.items.map(c => `<a class="wc gali" href="#/t/${c.code}"><b class="mono">${esc(c.code)}</b><span>${esc(c.name)}</span></a>`).join("")}</div>`).join("")}</div>`;
    return;
  }
  localStorage.setItem("pf.term", code);
  let data, scanFocus = false;   // skaitytuvas veikia kaip klaviatūra – fokusas išlieka po atnaujinimo
  const draw = async () => {
    data = await GET(`/api/terminal/${code}`);
    S.termCal = data.calendar; S.termArea = data.centre.area_code;
    const run = data.running;
    const first = data.queue.findIndex(t => !t.lock);
    app().innerHTML = `<div class="tm">
      <div class="row between"><h1><span class="mono">${esc(data.centre.code)}</span> ${esc(data.centre.name)}</h1>
        <div class="row"><input id="scan" class="scan" placeholder="▦ Skenuokite maršruto lapą" autocomplete="off" aria-label="Maršruto lapo QR">
          <span class="muted">${esc(S.me.name)}</span>${centres.length > 1 ? `<button class="ghost" id="chg">Kitas centras</button>` : ""}</div></div>
      ${data.calendar && !data.calendar.working ? `<div class="offc big-off">⏾ ${esc(data.calendar.why)}${data.calendar.next ? ` · darbo laikas nuo ${dt(data.calendar.next)}` : ""}</div>` : ""}
      ${run ? runCard(run) : `<div class="card"><h2>Šiuo metu niekas nevykdoma</h2><p class="muted">${first >= 0 ? "Pradėkite pažymėtą užduotį eilėje." : data.queue.length ? "Visos eilės užduotys šiuo metu užrakintos – priežastys nurodytos prie kiekvienos." : "Patvirtintoje eilėje užduočių nėra."}</p></div>`}
      <div class="card"><h2>Eilė</h2>${data.queue.map((t, i) => `
        <div class="q ${!run && i === first ? "next" : ""}" data-q="${t.id}">
          <div><b>${esc(t.project_code)} · ${esc(t.assembly_code)} ${esc(t.assembly_name)}</b><br>${esc(t.name)} · ${t.qty_plan - t.qty_good} vnt.${t.qty_good ? ` (padaryta ${t.qty_good})` : ""}
            ${t.drawing_no ? ` · <a href="/api/drawings/${encodeURIComponent(t.drawing_no)}/file?rev=${encodeURIComponent(t.drawing_current || t.drawing_rev)}" target="_blank">brėžinys ${esc(t.drawing_no)}</a>` : ""}
            ${flowLine(t)}${filesLine(t)}${t.wps ? `<div class="flow">WPS <b class="mono">${esc(t.wps.code)}</b> · procesas ${esc(t.wps.process)}</div>` : ""}
            ${t.held.length ? `<div class="warn">⧗ Padarytos detalės sulaikytos – laukia kokybės kontrolės: ${esc(t.held.join(", "))}</div>` : ""}
            ${t.lock ? `<div class="lock">🔒 ${esc(t.lock)}</div>` : ""}
            ${t.components_missing ? `<div class="warn">⚠ Negauti pirktiniai komponentai: ${t.components_missing} eil.</div>` : ""}</div>
          <div>${t.lock && t.lock.includes("revizija") && canAt("ack_rev", data.centre.code, data.centre.area_code) ? `<button class="b-pause" data-ack="${t.id}">Patvirtinti reviziją</button>` : ""}
            ${t.files_pending && canAt("ack_rev", data.centre.code, data.centre.area_code) ? `<button class="b-pause" data-ackf="${t.id}">Patvirtinti failą</button>` : ""}
            ${!run && !t.lock ? `<button class="b-ok" data-start="${t.id}">▶ Start</button>` : ""}</div>
        </div>`).join("") || `<p class="muted">Tuščia.</p>`}
        ${data.unapproved ? `<p class="muted">Dar ${data.unapproved} užduotys laukia planuotojo patvirtinimo.</p>` : ""}</div>
      ${data.done_today.length ? `<div class="card"><h2>Atlikta šiandien</h2>${data.done_today.map(t => `<div class="muted">✓ ${esc(t.project_code)} · ${esc(t.assembly_code)} ${esc(t.name)} – ${t.qty_good} vnt.${t.qty_scrap ? `, brokas ${t.qty_scrap}` : ""}</div>`).join("")}</div>` : ""}
    </div>`;
    const chg = $("#chg"); if (chg) chg.onclick = () => { localStorage.removeItem("pf.term"); location.hash = "#/t"; };
    const scan = $("#scan");
    if (scanFocus) scan.focus();
    scan.onfocus = () => (scanFocus = true); scan.onblur = () => (scanFocus = false);
    scan.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); onScan(scan.value.trim(), data); scan.value = ""; } };
    // ne darbo laikas – tik paklausiama: viršvalandžius ar skubų darbą leidžia meistras
    $$("[data-start]").forEach(b => b.onclick = async () => {
      const c = data.calendar;
      if (c && !c.working && !confirm(`Dabar ne darbo laikas: ${c.why}.\nAr tikrai pradėti darbą?`)) return;
      await act(() => POST(`/api/terminal/${b.dataset.start}/start`), "Pradėta"); draw();
    });
    $$("[data-ack]").forEach(b => b.onclick = async () => { await act(() => POST(`/api/tasks/${b.dataset.ack}/ack_revision`), "Revizija patvirtinta"); draw(); });
    $$("[data-ackf]").forEach(b => b.onclick = async () => { await act(() => POST(`/api/tasks/${b.dataset.ackf}/ack_files`), "Failas patvirtintas"); draw(); });
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
  return `<div class="card now ${paused ? "paused" : ""}" data-q="${t.id}">
    <div class="muted">${paused ? "PRISTABDYTA" : "DABAR VYKDOMA"} · projektas ${esc(t.project_code)} ${esc(t.project_name)}</div>
    <h2 style="font-size:22px">${esc(t.assembly_code)} ${esc(t.assembly_name)} · ${esc(t.name)}</h2>
    ${flowLine(t)}${filesLine(t)}
    ${termQuality(t)}
    ${t.files_pending ? `<div class="warn">⚠ Technologas atnaujino failą vykdant darbą – patikrinkite, ar staklėse nauja versija</div>` : ""}
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
  if (rs) rs.onclick = async () => {
    const c = S.termCal;
    if (c && !c.working && !confirm(`Dabar ne darbo laikas: ${c.why}.\nAr tikrai tęsti darbą?`)) return;
    await act(() => POST(`/api/terminal/${t.id}/resume`)); redraw();
  };
  $("#b-stop").onclick = () => {
    const left = Math.max(0, t.qty_plan - t.qty_good - t.qty_scrap);
    modal(`<h2>Baigti darbą</h2><p class="muted">${esc(t.name)} · liko ${left} iš ${t.qty_plan} vnt.</p>
      <div class="qty"><label>Gera<input id="st-good" type="number" min="0" value="${left}"></label><label>Brokas<input id="st-scrap" type="number" min="0" value="0"></label></div>
      <label class="row" style="display:flex"><input type="checkbox" id="st-fin"> užduotis baigta, nors ne visas kiekis</label>
      ${stopNeeds(t)}
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
        const then = () => r.suggest_ncr ? ncrModal({ task_id: t.id, qty: body.scrap, title: "Užregistruokite broką kaip neatitiktį" }, redraw) : redraw();
        if (r.held && r.held.length) heldModal(r, then);
        else if (r.moved > 0) moveModal(r, then); else then();
      };
    });
  };
  $("#b-ncr").onclick = () => ncrModal({ task_id: t.id }, redraw);
  wireTermQuality(t, redraw);
}

// ---------- technologo darbo aplinka ----------
const fsize = n => n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} kB`;
// kelias taip, kaip jį mato cecho kompiuteris (tinklo diskas), kad failą rastų ir staklėse
const sharePath = rel => { const base = S.meta.nc_share || ""; const sep = base.includes("\\") ? "\\" : "/"; return base.replace(/[\\/]+$/, "") + sep + rel.split("/").join(sep); };

function filesLine(t) {
  if (!t.files || !t.files.length) return "";
  return `<div class="files">${t.files.map(f => `<a class="fchip ${f.needs_ack ? "new" : ""}" href="/api/files/${f.id}" title="${esc(sharePath(f.path))}">📄 ${esc(f.name)} <small>v${f.version}</small></a>`).join("")}
    <div class="muted small path">${esc(sharePath(t.files[0].path.split("/").slice(0, -1).join("/")))}</div></div>`;
}

async function pageTechList() {
  let mine = false, hideDone = true;
  try { mine = localStorage.getItem("pf.techMine") === "1"; hideDone = localStorage.getItem("pf.techAll") !== "1"; } catch {}
  const all = await GET(`/api/tech/worklist${mine ? "?mine=1" : ""}`);
  const list = hideDone ? all.filter(a => a.state !== "isleista" || a.pending_ack) : all;
  const cnt = st => all.filter(a => a.state === st).length;
  app().innerHTML = `<div class="row between"><div><h1>Technologija</h1>
      <p class="muted">Mazgų maršrutai, programos ir DXF failai staklėms. Išleistas į gamybą maršrutas atsiranda ceche.</p></div>
    <div class="chips"><button class="${mine ? "ghost" : ""}" data-m="0">Visi</button><button class="${mine ? "" : "ghost"}" data-m="1">Mano (technologijos etapas)</button></div></div>
  <div class="tiles"><div class="tile">Nėra maršruto<b>${cnt("nera")}</b></div><div class="tile">Juodraščiai<b>${cnt("juodrastis")}</b></div>
    <div class="tile">Išleista<b>${cnt("isleista")}</b></div><div class="tile">Trūksta failų<b class="${all.some(a => a.no_file) ? "s-late" : ""}">${all.reduce((n, a) => n + a.no_file, 0)}</b></div></div>
  <label class="row" style="display:flex"><input type="checkbox" id="tl-all" ${hideDone ? "" : "checked"}> rodyti ir išleistus</label>
  <div class="tbl"><table><thead><tr><th>Projektas</th><th>Mazgas</th><th>Būsena</th><th>Operacijos</th><th>Ko trūksta</th><th>Failai</th><th>Technologija</th></tr></thead>
  <tbody>${list.map(a => `<tr class="click" data-go="${a.id}">
    <td><b class="mono">${esc(a.project_code)}</b><div class="muted small">${esc(a.project_name)}</div></td>
    <td><span class="mono">${esc(a.code)}</span> ${esc(a.name)} <span class="muted">× ${a.qty}</span></td>
    <td>${pill(a.state === "isleista" ? "baigta" : a.state === "juodrastis" ? "gali" : "laukia", a.state_label)}</td>
    <td class="num">${a.ops}${a.parts ? ` <span class="muted">(${a.parts} det.)</span>` : ""}</td>
    <td>${[a.no_file ? `<span class="s-late">be failo ${a.no_file}</span>` : "", a.no_norm ? `<span class="warn">be normos ${a.no_norm}</span>` : "",
      a.pending_ack ? `<span class="warn">laukia meistro ${a.pending_ack}</span>` : "", a.errors && !a.no_file ? `<span class="s-late">klaidų ${a.errors}</span>` : ""].filter(Boolean).join(" · ") || (a.ops ? "—" : '<span class="muted">sukurkite maršrutą</span>')}</td>
    <td class="num">${a.files}</td>
    <td>${a.tech_owner ? esc(a.tech_owner) : '<span class="muted">—</span>'}${a.tech_due ? `<div class="muted small nw">iki ${esc(a.tech_due)}</div>` : ""}</td></tr>`).join("")
    || `<tr><td colspan="7" class="muted">Nėra mazgų${mine ? ", kurių technologijos etapas priskirtas jums" : ""}.</td></tr>`}</tbody></table></div>`;
  $$("[data-m]").forEach(b => b.onclick = () => { try { localStorage.setItem("pf.techMine", b.dataset.m); } catch {} pageTechList(); });
  $("#tl-all").onchange = e => { try { localStorage.setItem("pf.techAll", e.target.checked ? "1" : "0"); } catch {} pageTechList(); };
  $$("[data-go]").forEach(r => r.onclick = () => (location.hash = `#/technologija/${r.dataset.go}`));
}

async function pageTechEdit(aid) {
  const [r, centres, qm] = await Promise.all([GET(`/api/route/${aid}`), GET("/api/centres?all=1"), GET("/api/quality/meta")]);
  const a = r.assembly, rel = r.released, lanes = [...r.branches, ...(r.main ? [r.main] : [])];
  const parts = r.branches.map(b => b.part);
  const centreSel = (sel, id) => `<select data-f="centre_id" ${id} style="max-width:190px">${byArea(centres).map(g => `<optgroup label="${esc(g.name)}">${g.items.map(c =>
    `<option value="${c.id}" ${c.id === sel ? "selected" : ""}>${esc(c.code)} ${esc(c.name)}${c.needs_files ? " ▣" : ""}</option>`).join("")}</optgroup>`).join("")}</select>`;
  const cid = code => (centres.find(c => c.code === code) || {}).id;
  const row = o => {
    const lock = rel ? "disabled" : "";
    return `<tr data-t="${o.id}" class="${o.status === "baigta" ? "dim" : ""}">
      <td><input type="number" data-f="seq" value="${o.seq}" style="width:64px" ${lock} aria-label="Seka"></td>
      <td>${rel ? (o.part_no ? `<span class="mono">${esc(o.part_no)}</span>` : '<span class="muted">mazgas</span>')
        : `<input data-f="part_no" value="${esc(o.part_no)}" style="width:100px" placeholder="mazgas" list="parts" aria-label="Detalė">`}</td>
      <td>${rel ? `<b class="mono">${esc(o.centre_code)}</b>` : centreSel(cid(o.centre_code), `aria-label="Centras"`)}</td>
      <td><input data-f="name" value="${esc(o.name)}" style="min-width:150px" aria-label="Operacija"></td>
      <td class="fcell" data-drop="${o.id}">
        ${(o.files || []).map(f => `<div class="frow"><a class="fchip ${f.needs_ack ? "new" : ""}" href="/api/files/${f.id}" title="${esc(sharePath(f.path))}">📄 ${esc(f.name)}</a>
          <button class="small ghost" data-hist="${o.id}" title="Versijų istorija">v${f.version}</button>${f.needs_ack ? '<span class="warn small">laukia meistro</span>' : ""}
          ${rel ? "" : `<button class="small ghost" data-rm="${f.id}" title="Pašalinti iš operacijos" aria-label="Pašalinti ${esc(f.name)}">✕</button>`}</div>`).join("")}
        ${o.needs_files && !(o.files || []).length ? `<div class="s-late small">▣ staklėms reikia failo</div>` : ""}
        ${o.status === "baigta" ? "" : `<label class="btn ghost small upl">+ Failas<input type="file" multiple hidden data-up="${o.id}"></label>`}</td>
      <td class="qcell">${qualityCell(o, rel, qm)}</td>
      <td><input type="number" min="1" data-f="qty_plan" value="${o.qty_plan}" style="width:64px" ${lock} aria-label="Kiekis"></td>
      <td><input type="number" min="0" step="0.1" data-f="norm_min" value="${o.norm_min || ""}" style="width:74px" aria-label="Norma, min/vnt"></td>
      <td class="nw"><input data-f="drawing_no" value="${esc(o.drawing_no)}" style="width:96px" aria-label="Brėžinys"> <input data-f="drawing_rev" value="${esc(o.drawing_rev)}" style="width:40px" aria-label="Revizija"></td>
      <td>${pill(o.status, o.status)}${rel || o.status !== "laukia" ? "" : ` <button class="small ghost" data-del="${o.id}" title="Šalinti operaciją" aria-label="Šalinti operaciją">✕</button>`}</td></tr>`;
  };
  const sources = rel ? [] : await GET("/api/tech/sources");
  app().innerHTML = `
  <div class="row between"><div><a href="#/technologija">← Technologija</a>
      <h1><span class="mono">${esc(a.code)}</span> ${esc(a.name)} <span class="muted">× ${a.qty}</span></h1>
      <p class="muted"><b class="mono">${esc(a.project_code)}</b> ${esc(a.project_name)} · failai: <span class="mono">${esc(sharePath(`${a.project_code}/${a.code}`))}</span></p></div>
    <div class="row">${rel ? pill("baigta", `išleista ${dt(a.released_at)}`) : pill("gali", "juodraštis")}
      <a class="btn ghost" href="#/r/${a.id}">Srautas →</a><a class="btn ghost" href="#/r/${a.id}/lapai">🖨 Maršruto lapai</a>
      ${can("release") && !rel ? `<button id="rel" ${r.check.errors.length ? "disabled" : ""}>Išleisti į gamybą</button>` : ""}
      ${can("release") && rel ? `<button class="ghost" id="unrel">Keisti maršrutą</button>` : ""}</div></div>
  ${rel ? `<p class="muted">Maršrutas išleistas: keisti galima pavadinimą, normą, brėžinį ir įkelti naują failo versiją (ceche ją patvirtins meistras). Seką, centrą, detalę, kiekį – tik „Keisti maršrutą“.</p>`
    : r.check.errors.length || r.check.warnings.length ? `<div class="card"><h2>Prieš išleidžiant</h2>${r.check.errors.map(e => `<div class="lock">✖ ${esc(e)}</div>`).join("")}${r.check.warnings.map(w => `<div class="warn">⚠ ${esc(w)}</div>`).join("")}</div>`
    : `<p class="s-baigta">✓ Maršrutas paruoštas išleisti.</p>`}
  <datalist id="parts">${parts.map(p => `<option value="${esc(p)}">`).join("")}</datalist>
  ${lanes.map(l => `<div class="card"><h2>${l.part ? `Detalė <span class="mono">${esc(l.part)}</span>` : `Mazgo operacijos <span class="muted">(čia detalės susilieja)</span>`}</h2>
    <div class="tbl"><table class="tedit"><thead><tr><th>Seka</th><th>Detalė</th><th>Centras</th><th>Operacija</th><th>Failai</th><th>Kokybė</th><th>Kiekis</th><th>Norma min/vnt</th><th>Brėžinys, rev.</th><th></th></tr></thead>
    <tbody>${l.ops.map(row).join("")}</tbody></table></div></div>`).join("") || `<div class="card"><h2>Maršrutas</h2><p class="muted">Operacijų dar nėra – pridėkite žemiau arba nukopijuokite iš panašaus mazgo.</p></div>`}
  ${rel ? "" : `<div class="card"><h2>Pridėti operaciją</h2>
    <form id="addop" class="inline">
      <label>Detalė<input name="part_no" list="parts" placeholder="tuščia – mazgas" style="width:120px" id="ao-part"></label>
      <label>Seka<input name="seq" type="number" placeholder="auto" style="width:70px" id="ao-seq"></label>
      <label>Centras${centreSel(null, 'name="centre_id" id="ao-centre"')}</label>
      <label>Operacija<input name="name" required id="ao-name"></label>
      <label>Kiekis<input name="qty_plan" type="number" min="1" value="${a.qty}" style="width:70px" id="ao-qty"></label>
      <label>Norma min/vnt<input name="norm_min" type="number" step="0.1" style="width:90px" id="ao-norm"></label>
      <label>Brėžinys<input name="drawing_no" style="width:110px" id="ao-drw"></label><label>Rev.<input name="drawing_rev" style="width:50px" id="ao-rev"></label>
      <button>Pridėti</button></form>
    <p class="muted small">▣ – staklės, kurioms reikia programos ar DXF failo. Failą galima ir nutempti ant operacijos eilutės.</p></div>
    ${sources.filter(x => x.id !== a.id).length ? `<div class="card"><h2>Kopijuoti maršrutą iš kito mazgo</h2>
      <form id="copy" class="inline"><label style="flex:1 1 300px">Mazgas<select name="from" id="cp-from">${opt(sources.filter(x => x.id !== a.id).map(x => ({ id: x.id, name: `${x.project_code} · ${x.code} ${x.name} (× ${x.qty}, ${x.ops} op.)` })))}</select></label>
        <label class="row" style="display:flex"><input type="checkbox" id="cp-files" checked> su failais</label><button class="ghost">Kopijuoti</button></form>
      <p class="muted small">Operacijos pridedamos prie esamų, kiekiai perskaičiuojami pagal mazgų kiekį.</p></div>` : ""}`}
  ${lanes.length ? `<div class="card"><h2>Srauto peržiūra</h2><div class="flowmap">
    ${r.branches.map(b => `<div class="flane"><div class="lane-h">Detalė <b class="mono">${esc(b.part)}</b></div><div class="ops">${laneOps(b.ops)}</div></div>`).join("")}
    ${r.main ? `${r.branches.length ? `<div class="join">⤵ ${r.branches.length > 1 ? `${r.branches.length} detalės susilieja` : "detalė keliauja"} į mazgą</div>` : ""}<div class="flane main"><div class="lane-h">Mazgas <b class="mono">${esc(a.code)}</b></div><div class="ops">${laneOps(r.main.ops)}<span class="arr">→</span><div class="op end">${r.main.next.map(destText).join("<br>")}</div></div></div>` : ""}
  </div></div>` : ""}`;

  const reload = () => pageTechEdit(aid);
  const upload = async (tid, files) => {
    for (const f of files) {
      const fd = new FormData(); fd.append("file", f);
      await act(() => api("POST", `/api/tasks/${tid}/files`, fd, true), `Įkelta: ${f.name}`).catch(() => {});
    }
    reload();
  };
  $$("tr[data-t] [data-f]").forEach(el => el.onchange = async () => {
    const f = el.dataset.f, num = ["seq", "qty_plan", "norm_min", "centre_id", "wps_id"].includes(f);
    await act(() => PUT(`/api/tasks/${el.closest("tr").dataset.t}`, { [f]: num ? +el.value || 0 : el.value.trim() }), "Įrašyta").catch(() => {});
    reload();
  });
  $$("[data-up]").forEach(i => i.onchange = () => upload(i.dataset.up, i.files));
  $$("[data-drop]").forEach(z => {
    z.ondragover = e => { e.preventDefault(); z.classList.add("over"); };
    z.ondragleave = () => z.classList.remove("over");
    z.ondrop = e => { e.preventDefault(); z.classList.remove("over"); if (e.dataTransfer.files.length) upload(z.dataset.drop, e.dataTransfer.files); };
  });
  $$("[data-rm]").forEach(b => b.onclick = async () => { await act(() => api("DELETE", `/api/files/${b.dataset.rm}`), "Pašalinta"); reload(); });
  $$("[data-chk-rm]").forEach(b => b.onclick = async () => { await act(() => api("DELETE", `/api/checks/${b.dataset.chkRm}`), "Patikra pašalinta"); reload(); });
  $$("[data-chk-add]").forEach(b => b.onclick = () => addCheckModal(+b.dataset.chkAdd, qm, reload));
  $$("[data-del]").forEach(b => b.onclick = async () => { await act(() => api("DELETE", `/api/tasks/${b.dataset.del}`), "Operacija pašalinta"); reload(); });
  $$("[data-hist]").forEach(b => b.onclick = async () => {
    const h = await GET(`/api/tasks/${b.dataset.hist}/files?history=1`);
    modal(`<h2>Failų versijos</h2>${simple(h, ["Failas", "Versija", "Dydis", "Įkėlė", "Būsena"], f => [
      `<a href="/api/files/${f.id}">${esc(f.name)}</a>${f.note ? `<div class="muted small">${esc(f.note)}</div>` : ""}`, `v${f.version}`, fsize(f.size),
      `${esc(f.uploaded_by_name || "—")}<div class="muted small">${dt(f.uploaded_at)}</div>`,
      f.current ? (f.needs_ack ? '<span class="warn">laukia meistro</span>' : pill("baigta", "galioja")) : '<span class="muted">senesnė</span>'])}
      <p class="muted small">Senesnės versijos lieka diske – matyti, pagal kurią programą dirbta.</p><button id="h-x">Uždaryti</button>`, () => { $("#h-x").onclick = closeModal; });
  });
  const add = $("#addop");
  if (add) add.onsubmit = async e => {
    e.preventDefault(); const d = formData(add);
    Object.assign(d, { project_id: a.project_id, assembly_id: a.id, centre_id: +d.centre_id, seq: d.seq ? +d.seq : null,
      qty_plan: +d.qty_plan || 1, norm_min: +d.norm_min || 0, part_no: d.part_no.trim() });
    await act(() => POST("/api/tasks", d), "Operacija pridėta"); reload();
  };
  const cp = $("#copy");
  if (cp) cp.onsubmit = async e => {
    e.preventDefault();
    const res = await act(() => POST(`/api/route/${aid}/copy`, { from_assembly: +$("#cp-from").value, files: $("#cp-files").checked }));
    toast(`Nukopijuota: ${res.ops} op., ${res.files} fail.`); reload();
  };
  const rb = $("#rel");
  if (rb) rb.onclick = async () => { await act(() => POST(`/api/route/${aid}/release`), "Maršrutas išleistas į gamybą"); reload(); };
  const un = $("#unrel");
  if (un) un.onclick = () => modal(`<h2>Keisti maršrutą</h2>
    <p class="muted">Pradėti darbai tęsiami, nepradėti užrakinami, kol maršrutą išleisite iš naujo.</p>
    <label>Kodėl keičiama<input id="ur-why"></label>
    <div class="row"><button id="ur-ok">Grąžinti keisti</button><button class="ghost" id="ur-x">Atšaukti</button></div>`, () => {
    $("#ur-x").onclick = closeModal;
    $("#ur-ok").onclick = async () => { await act(() => POST(`/api/route/${aid}/unrelease`, { reason: $("#ur-why").value }), "Grąžinta keisti"); closeModal(); reload(); };
  });
}

// ---------- technologinis srautas ----------
const routeUrl = (aid, part) => `${location.origin}${location.pathname}#/r/${aid}${part ? `/d/${encodeURIComponent(part)}` : ""}`;
const destText = d => d.task_id ? `<b class="mono">${esc(d.centre_code)}</b> ${esc(d.name)}${d.assembly ? ` <span class="muted">(mazgas ${esc(d.assembly)})</span>` : ""}` : esc(d.label);

// Iš kur detalės ateina ir kur keliaus – operatorius mato srautą prie kiekvienos užduoties
function flowLine(t) {
  const from = (t.from || []).map(f => `${f.part_no && f.part_no !== t.part_no ? `${esc(f.part_no)} iš ` : ""}<b class="mono">${esc(f.centre_code)}</b>${f.done ? " ✓" : f.qty_good ? ` (${f.qty_good} vnt.)` : " …"}`);
  return `<div class="flow">${t.part_no ? `Detalė <b class="mono">${esc(t.part_no)}</b> · ` : ""}${from.length ? `iš ← ${from.join(", ")} · ` : ""}${t.arrived ? `atkeliavo ${t.arrived} vnt. · ` : ""}toliau → ${(t.next || []).map(destText).join(", ")}</div>`;
}

// Po Stop: kur nunešti padarytas detales – didelėmis raidėmis, kad matytųsi iš toli
function moveModal(r, after) {
  modal(`<div class="move"><div class="muted">PERDUOKITE ${r.moved} VNT.</div>
    ${(r.next || []).map(d => `<div class="dest"><span class="arrow">→</span><div>${d.task_id
      ? `<div class="big-c mono">${esc(d.centre_code)}</div><div>${esc(d.centre_name)}${d.area_name ? ` · ${esc(d.area_name)}` : ""}</div>
         <div class="muted">${esc(d.name)}${d.assembly ? ` · mazgas ${esc(d.assembly)}` : ""}${d.joins > 1 ? ` · čia susilieja ${d.joins} detalės` : ""}</div>`
      : `<div class="big-c">${esc(d.label)}</div>`}</div></div>`).join("")}
    <button id="mv-ok" class="b-ok">Supratau</button></div>`, () => { $("#mv-ok").onclick = () => { closeModal(); after(); }; });
}

// Maršruto lapo QR: skaitytuvas „įrašo“ nuorodą ir Enter. Randama šio centro
// užduotis; jei detalė čia neateina – parodoma, kur ji turi būti.
async function onScan(text, data) {
  const m = text.match(/#\/r\/(\d+)(?:\/d\/([^/?#\s]+))?/);
  if (!m) { toast("Tai ne VMGT maršruto lapas", true); return; }
  const aid = +m[1], part = m[2] ? decodeURIComponent(m[2]) : "";
  const all = [data.running, ...data.queue].filter(Boolean);
  const hit = all.find(t => t.assembly_id === aid && (t.part_no || "") === part) || all.find(t => t.assembly_id === aid);
  if (hit) {
    const el = $(`[data-q="${hit.id}"]`) || $(".now");
    el.classList.add("hit"); el.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => el.classList.remove("hit"), 4000);
    toast(`Rasta: ${hit.assembly_code} · ${hit.name}`);
    return;
  }
  const r = await act(() => GET(`/api/route/${aid}`));
  const lane = part ? r.branches.find(b => b.part === part) : r.main;
  const here = lane ? lane.ops.filter(o => o.here) : [];
  const mine = lane && lane.ops.find(o => o.centre_code === data.centre.code);
  const what = part ? `Detalė ${esc(part)}` : "Mazgas";
  const title = !mine ? `${what} į ${esc(data.centre.code)} neateina`
    : mine.status === "baigta" ? `${what} čia jau apdirbta` : `${what} dar ne šio centro eilėje`;
  modal(`<h2>${title}</h2>
    ${mine && mine.status !== "baigta" ? `<p class="lock">${esc(mine.lock || (mine.approved ? "" : "Laukia planuotojo patvirtinimo"))}</p>` : ""}
    <p>${esc(r.assembly.project_code)} · ${esc(r.assembly.code)} ${esc(r.assembly.name)}</p>
    ${here.length ? `<p>Dabar: ${here.map(o => `<b class="mono">${esc(o.centre_code)}</b> – ${esc(o.here)}`).join(", ")}</p>` : lane && lane.done ? `<p>Atšaka baigta, toliau → ${lane.next.map(destText).join(", ")}</p>` : ""}
    ${lane ? `<p class="muted">Srautas: ${lane.ops.map(o => esc(o.centre_code)).join(" → ")}</p>` : ""}
    <button id="sc-x">Uždaryti</button>`, () => { $("#sc-x").onclick = closeModal; });
}

function opBox(o) {
  return `<div class="op st-${esc(o.status)}">
    <div class="row between"><b class="mono">${esc(o.centre_code)}</b><span class="num">${o.qty_good}/${o.qty_plan}${o.qty_scrap ? ` <span class="s-late">−${o.qty_scrap}</span>` : ""}</span></div>
    <div>${esc(o.name)}</div>
    <div class="muted small">${esc(o.area_name || "")}${o.seq ? ` · seka ${o.seq}` : ""}</div>
    ${o.here ? `<div class="here">📍 ${esc(o.here)}</div>` : ""}
    ${o.lock && o.here ? `<div class="lock small">🔒 ${esc(o.lock)}</div>` : ""}</div>`;
}
const laneOps = ops => ops.map(opBox).join(`<span class="arr" aria-hidden="true">→</span>`);

async function pageRoute(aid, part) {
  part = part ? decodeURIComponent(part) : "";
  const r = await GET(`/api/route/${aid}`);
  const a = r.assembly, edit = can("release");
  const lanes = r.branches.map(b => `<div class="flane ${part && b.part === part ? "sel" : ""}">
      <div class="lane-h">Detalė <b class="mono">${esc(b.part)}</b> ${b.done ? pill("baigta", "atšaka baigta") : ""}</div>
      <div class="ops">${laneOps(b.ops)}${r.main ? "" : `<span class="arr">→</span><div class="op end">${b.next.map(destText).join("<br>")}</div>`}</div></div>`).join("");
  app().innerHTML = `
  <div class="row between"><div>${can("view") ? `<a href="#/p/${a.project_id}/gamyba">← ${esc(a.project_code)} gamyba</a>` : ""}
      <h1><span class="mono">${esc(a.code)}</span> ${esc(a.name)} <span class="muted">× ${a.qty}</span></h1>
      <p class="muted">${esc(a.project_code)} ${esc(a.project_name)} · technologinis srautas ir atsekamumas</p></div>
    <div class="row">${r.released ? pill("baigta", `išleista ${dt(a.released_at)}${a.released_by_name ? ` · ${a.released_by_name}` : ""}`) : pill("laukia", "juodraštis – neišleista")}
      <a class="btn ghost" href="#/r/${a.id}/lapai">🖨 Maršruto lapai</a>
      ${edit && !r.released ? `<button id="rel" ${r.check.errors.length ? "disabled" : ""}>Išleisti į gamybą</button>` : ""}
      ${edit && r.released ? `<button class="ghost" id="unrel">Keisti maršrutą</button>` : ""}</div></div>
  ${!r.released && (r.check.errors.length || r.check.warnings.length) ? `<div class="card">
    <h2>Prieš išleidžiant</h2>${r.check.errors.map(e => `<div class="lock">✖ ${esc(e)}</div>`).join("")}${r.check.warnings.map(w => `<div class="warn">⚠ ${esc(w)}</div>`).join("")}
    <p class="muted">Klaidos draudžia išleisti, įspėjimai – ne. Operacijas keiskite projekto kortelėje „Gamyba“.</p></div>` : ""}
  ${!r.released ? `<p class="muted">Kol maršrutas neišleistas, planuotojas jo užduočių negali patvirtinti, o terminalas – pradėti.</p>` : ""}
  <div class="card"><h2>Srautas</h2>
    ${r.requires.length ? `<p>Į šį mazgą ateina: ${r.requires.map(x => `<a href="#/r/${x.id}" class="mono">${esc(x.code)}</a> ${esc(x.name)} ${x.done ? "✓" : "…"}`).join(", ")}</p>` : ""}
    <div class="flowmap">${lanes || ""}
      ${r.main ? `${r.branches.length ? `<div class="join">⤵ ${r.branches.length > 1 ? `${r.branches.length} detalės susilieja` : "detalė keliauja"} į mazgą</div>` : ""}
      <div class="flane main ${!part ? "sel" : ""}"><div class="lane-h">Mazgas <b class="mono">${esc(a.code)}</b> ${r.main.done ? pill("baigta", "baigtas") : ""}</div>
        <div class="ops">${laneOps(r.main.ops)}<span class="arr">→</span><div class="op end">${r.main.next.map(destText).join("<br>")}</div></div></div>` : ""}
      ${!r.main && !r.branches.length ? `<p class="muted">Operacijų dar nėra.</p>` : ""}</div></div>
  <div class="card"><h2>Perdavimai</h2>
    ${simple(r.transfers, ["Laikas", "Iš", "Kiekis", "Į", "Kas"], m => [
      `<span class="num">${dt(m.at)}</span>`, `<span class="mono">${esc(m.from_centre)}</span> ${esc(m.from_name)}${m.from_part ? ` <span class="muted">${esc(m.from_part)}</span>` : ""}`,
      `<span class="num">${m.qty}</span>`, esc(m.to_label) + (m.to_assembly && m.to_assembly !== a.code ? ` <span class="muted">(mazgas ${esc(m.to_assembly)})</span>` : ""), esc(m.user_name || "—")])}</div>`;
  const rel = $("#rel");
  if (rel) rel.onclick = async () => {
    const res = await act(() => POST(`/api/route/${aid}/release`), "Maršrutas išleistas į gamybą");
    if (res.warnings.length) toast(`Išleista su įspėjimais: ${res.warnings.length}`);
    pageRoute(aid, part);
  };
  const un = $("#unrel");
  if (un) un.onclick = () => modal(`<h2>Keisti maršrutą</h2>
    <p class="muted">Pradėti darbai tęsiami, nepradėti užrakinami, kol maršrutą išleisite iš naujo. Priežastis lieka žurnale.</p>
    <label>Kodėl keičiama<input id="ur-why" required></label>
    <div class="row"><button id="ur-ok">Grąžinti keisti</button><button class="ghost" id="ur-x">Atšaukti</button></div>`, () => {
    $("#ur-x").onclick = closeModal;
    $("#ur-ok").onclick = async () => { await act(() => POST(`/api/route/${aid}/unrelease`, { reason: $("#ur-why").value }), "Maršrutas grąžintas keisti"); closeModal(); pageRoute(aid, part); };
  });
  S.timers.push(setInterval(() => { if ($("#modal").hidden && location.hash.startsWith(`#/r/${aid}`) && !location.hash.endsWith("/lapai")) pageRoute(aid, part); }, 20000));
}

// Maršruto lapai: po vieną kiekvienai detalei ir mazgui. Lapas keliauja su
// detalėmis, jo QR terminale atidaro užduotį, telefone – šį srautą.
async function pageRouteCards(aid) {
  const r = await GET(`/api/route/${aid}`);
  const a = r.assembly;
  const sheet = (lane, part) => `<section class="rcard">
    <div class="rc-head"><div>
      <div class="muted">MARŠRUTO LAPAS${r.released ? "" : " · JUODRAŠTIS – NEIŠLEISTA Į GAMYBĄ"}</div>
      <h2>${part ? `Detalė <span class="mono">${esc(part)}</span>` : `Mazgas <span class="mono">${esc(a.code)}</span>`}</h2>
      <div><b class="mono">${esc(a.project_code)}</b> ${esc(a.project_name)}</div>
      <div>Mazgas <b class="mono">${esc(a.code)}</b> ${esc(a.name)} × ${a.qty}${lane.ops[0] && lane.ops[0].drawing_no ? ` · brėžinys ${esc(lane.ops[0].drawing_no)} ${esc(lane.ops[0].drawing_rev)}` : ""}</div>
      ${!part && r.branches.length ? `<div>Susilieja detalės: ${r.branches.map(b => `<span class="mono">${esc(b.part)}</span>`).join(", ")}</div>` : ""}</div>
      <img class="qr" alt="QR" src="/api/qr?data=${encodeURIComponent(routeUrl(a.id, part))}"></div>
    <table><thead><tr><th>Seka</th><th>Centras</th><th>Operacija</th><th>Kiekis</th><th>Norma</th><th>Failai</th><th>Atlikta: data, parašas</th></tr></thead>
    <tbody>${lane.ops.map(o => `<tr><td class="num">${o.seq}</td><td><b class="mono">${esc(o.centre_code)}</b><br><small>${esc(o.area_name || "")}</small></td>
      <td>${esc(o.name)}</td><td class="num">${o.qty_plan}</td><td class="num">${o.norm_min ? `${o.norm_min} min/vnt` : ""}</td>
      <td><small>${(o.files || []).map(f => `${esc(f.name)} v${f.version}`).join("<br>")}</small></td><td class="sign"></td></tr>`).join("")}</tbody></table>
    <p><b>Baigus → </b>${lane.next.map(d => d.task_id ? `${esc(d.centre_code)} ${esc(d.centre_name)} · ${esc(d.name)}${d.assembly ? ` (mazgas ${esc(d.assembly)})` : ""}` : esc(d.label)).join("; ")}</p>
  </section>`;
  app().innerHTML = `<div class="row between noprint"><div><a href="#/r/${a.id}">← Srautas</a><h1>Maršruto lapai · ${esc(a.code)} ${esc(a.name)}</h1>
      <p class="muted">${r.branches.length + (r.main ? 1 : 0)} lapai: kiekvienai detalei ir mazgui. Lapas keliauja kartu su detalėmis.</p></div>
    <button id="pr">🖨 Spausdinti</button></div>
    ${r.released ? "" : `<p class="warn noprint">Maršrutas dar neišleistas į gamybą – lapai pažymėti kaip juodraštis.</p>`}
    <div class="rcards">${r.branches.map(b => sheet(b, b.part)).join("")}${r.main ? sheet(r.main, "") : ""}</div>`;
  $("#pr").onclick = () => window.print();
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

// ---------- kokybė (EN 1090 / ISO 3834) ----------
const CHK_ICON = { laukia: "○", ok: "✓", nok: "✗", isimtis: "≈" };
const CHK_CLS = { laukia: "muted", ok: "s-baigta", nok: "s-late", isimtis: "warn" };
const perfLabel = p => p === "qc" ? "KK" : "op.";

function qualityCell(o, rel, qm) {
  const chk = (o.checks || []).map(c => `<div class="qchk"><span class="${CHK_CLS[c.status]}" title="${esc(c.status)}">${CHK_ICON[c.status]}</span>
    <span>${esc(c.name)}${c.tolerance ? ` <span class="muted small nw">${esc(c.tolerance)}</span>` : ""} <span class="tag ${c.performer}">${perfLabel(c.performer)}</span></span>
    ${!rel && c.status === "laukia" ? `<button class="small ghost" data-chk-rm="${c.id}" aria-label="Pašalinti patikrą ${esc(c.name)}">✕</button>` : "<span></span>"}</div>`).join("");
  const wps = o.centre_kind === "suvirinimas" ? `<label class="wpsl">WPS<select data-f="wps_id" aria-label="WPS">${opt(qm.wps.map(w => ({ id: w.id, name: `${w.code} (${w.process}, ${w.material_group})` })), o.wps_id, "—")}</select></label>` : "";
  const mats = (o.materials || []).map(m => `<div class="small muted">⬡ ${esc(m.heat_no)} ${esc(m.material)}</div>`).join("");
  return `${chk}${mats}${wps}${o.status !== "baigta" ? `<button class="small ghost" data-chk-add="${o.id}">+ Patikra</button>` : ""}`;
}

function addCheckModal(taskId, qm, after) {
  modal(`<h2>Nauja patikra</h2>
    <label>Iš šablono<select id="ck-t">${opt(qm.templates.map(t => ({ id: t.id, name: `${t.code} · ${t.name}${t.performer === "qc" ? " (KK)" : ""}` })), "", "— savo patikra —")}</select></label>
    <div id="ck-own" class="stack">
      <label>Pavadinimas<input id="ck-n" placeholder="pvz. Įstrižainių skirtumas"></label>
      <div class="row"><label>Tipas<select id="ck-k"><option value="check">OK / NOK</option><option value="measure">Matavimas</option></select></label>
        <label>Atlieka<select id="ck-p">${opt(qm.performers)}</select></label></div>
      <div class="row" id="ck-m" hidden><label>Vardinė<input id="ck-nom" type="number" step="any" style="width:90px"></label>
        <label>− tol.<input id="ck-lo" type="number" step="any" style="width:70px"></label><label>+ tol.<input id="ck-hi" type="number" step="any" style="width:70px"></label>
        <label>Vnt.<input id="ck-u" value="mm" style="width:60px"></label></div>
      <label>Instrukcija<textarea id="ck-i" placeholder="kaip tikrinti, kuo matuoti"></textarea></label></div>
    <div class="row"><button id="ck-ok">Pridėti</button><button class="ghost" id="ck-x">Atšaukti</button></div>`, () => {
    const sync = () => { $("#ck-own").hidden = !!$("#ck-t").value; $("#ck-m").hidden = $("#ck-k").value !== "measure"; };
    $("#ck-t").onchange = sync; $("#ck-k").onchange = sync; sync();
    $("#ck-x").onclick = closeModal;
    $("#ck-ok").onclick = async () => {
      const body = $("#ck-t").value ? { template_id: +$("#ck-t").value } : { name: $("#ck-n").value, kind: $("#ck-k").value, performer: $("#ck-p").value,
        nominal: $("#ck-nom").value, tol_minus: $("#ck-lo").value, tol_plus: $("#ck-hi").value, unit: $("#ck-u").value, instruction: $("#ck-i").value };
      await act(() => POST(`/api/tasks/${taskId}/checks`, body), "Patikra pridėta"); closeModal(); after();
    };
  });
}

// terminale: savikontrolė, kokybės inžinieriaus patikros, medžiagos lydinys
function termQuality(t) {
  const checks = t.checks || [];
  if (!checks.length && !t.needs_material && !(t.materials || []).length && !t.wps) return "";
  return `<div class="tq">
    ${t.wps ? `<div>WPS <b class="mono">${esc(t.wps.code)}</b> · procesas ${esc(t.wps.process)} · grupė ${esc(t.wps.material_group)}</div>` : ""}
    ${checks.map(c => `<div class="tqrow ${c.status}"><span class="tqi">${CHK_ICON[c.status]}</span>
      <div><b>${esc(c.name)}</b>${c.tolerance ? ` <span class="muted">${esc(c.tolerance)}</span>` : ""}${c.instruction ? `<div class="muted small">${esc(c.instruction)}</div>` : ""}
        ${c.status === "nok" ? `<div class="lock">NOK – užregistruota neatitiktis, pataisykite ir pakartokite</div>` : ""}</div>
      <div class="tqa">${c.performer === "qc" ? (c.status === "ok" || c.status === "isimtis" ? "" : `<span class="muted">laukia kokybės inžinieriaus</span>`)
        : c.status === "ok" || c.status === "isimtis" ? `<span class="muted">${c.value != null ? esc(String(c.value).replace(".", ",")) + " " + esc(c.unit) : "OK"}</span>`
        : c.kind === "measure" ? `<input type="text" inputmode="decimal" autocomplete="off" class="tqv" data-cv="${c.id}" placeholder="${esc(c.unit || "reikšmė")}" aria-label="${esc(c.name)}"><button class="b-ok" data-cm="${c.id}">Įrašyti</button>`
        : `<button class="b-ok" data-cok="${c.id}">OK</button><button class="b-stop" data-cnok="${c.id}">NOK</button>`}
        ${canAt("ack_rev", t.centre_code, S.termArea) && (c.status === "laukia" || c.status === "nok") ? `<button class="ghost small" data-cw="${c.id}">Išimtis</button>` : ""}</div></div>`).join("")}
    ${t.needs_material || (t.materials || []).length ? `<div class="tqrow ${(t.materials || []).length ? "ok" : "laukia"}"><span class="tqi">${(t.materials || []).length ? "✓" : "○"}</span>
      <div><b>Medžiaga (lydinys)</b>${t.needs_material ? ` <span class="muted">– ${esc(t.exc_class)}: privaloma prieš perduodant</span>` : ""}
        ${(t.materials || []).map(m => `<div class="muted">⬡ ${esc(m.heat_no)} · ${esc(m.material)} ${esc(m.product)}${m.cert_no ? ` · sert. ${esc(m.cert_no)}` : ""}</div>`).join("")}</div>
      <div class="tqa"><button class="b-doc" id="tq-lot">${(t.materials || []).length ? "+ Dar lydinys" : "Nurodyti lydinį"}</button></div></div>` : ""}
  </div>`;
}

function wireTermQuality(t, redraw) {
  const res = async (id, body, msg) => {
    const r = await act(() => POST(`/api/checks/${id}/result`, body));
    toast(r.ok ? (r.released ? `${msg} · perduota ${r.released} vnt.` : msg) : "NOK – užregistruota neatitiktis", !r.ok);
    redraw();
  };
  $$("[data-cok]").forEach(b => b.onclick = () => res(b.dataset.cok, { ok: true }, "Patikra OK"));
  $$("[data-cm]").forEach(b => b.onclick = () => res(b.dataset.cm, { value: $(`[data-cv="${b.dataset.cm}"]`).value }, "Įrašyta"));
  $$("[data-cnok]").forEach(b => b.onclick = () => modal(`<h2>NOK – kas negerai?</h2><label>Aprašymas<textarea id="nk-n"></textarea></label>
    <div class="row"><button class="b-stop" id="nk-ok">Įrašyti NOK</button><button class="ghost" id="nk-x">Atšaukti</button></div>`, () => {
    $("#nk-x").onclick = closeModal;
    $("#nk-ok").onclick = async () => { closeModal(); await res(b.dataset.cnok, { ok: false, note: $("#nk-n").value }, ""); };
  }));
  $$("[data-cw]").forEach(b => b.onclick = () => waiveModal(+b.dataset.cw, redraw));
  const lb = $("#tq-lot");
  if (lb) lb.onclick = async () => {
    const lots = await GET("/api/quality/lots?ok=1");
    modal(`<h2>Iš kurio lydinio pjauta?</h2>
      <input id="lt-q" placeholder="Ieškoti: lydinio nr., medžiaga, sertifikatas" autocomplete="off">
      <div class="ltlist" id="lt-l"></div><div><button class="ghost" id="lt-x">Atšaukti</button></div>`, () => {
      const list = q => $("#lt-l").innerHTML = lots.filter(l => !q || `${l.heat_no} ${l.material} ${l.product} ${l.cert_no}`.toLowerCase().includes(q.toLowerCase()))
        .slice(0, 40).map(l => `<button class="ghost lt" data-lot="${l.id}"><b class="mono">${esc(l.heat_no)}</b> ${esc(l.material)} · ${esc(l.product)}<span class="muted small">${esc(l.supplier)} · sert. ${esc(l.cert_no || "—")} ${esc(l.cert_type)}</span></button>`).join("")
        || `<p class="muted">Nerasta. Lydinį užregistruoja sandėlis ar kokybės skyrius („Kokybė → Medžiagos“).</p>`;
      list(""); $("#lt-q").oninput = e => list(e.target.value); $("#lt-q").focus();
      $("#lt-x").onclick = closeModal;
      $("#lt-l").onclick = async e => { const b = e.target.closest("[data-lot]"); if (!b) return;
        await act(() => POST(`/api/tasks/${t.id}/materials`, { lot_id: +b.dataset.lot }), "Lydinys įrašytas"); closeModal(); redraw(); };
    });
  };
}

function waiveModal(id, after) {
  modal(`<h2>Išimtis patikrai</h2><p class="muted">Patikra bus laikoma užbaigta be OK rezultato. Priežastis lieka kokybės įraše ir dosjė.</p>
    <label>Priežastis<textarea id="wv-r" placeholder="pvz. užsakovas raštu sutiko su nukrypimu"></textarea></label>
    <div class="row"><button id="wv-ok">Leisti išimtį</button><button class="ghost" id="wv-x">Atšaukti</button></div>`, () => {
    $("#wv-x").onclick = closeModal;
    $("#wv-ok").onclick = async () => { const r = await act(() => POST(`/api/checks/${id}/waive`, { reason: $("#wv-r").value }), "Išimtis įrašyta"); closeModal(); after(r); };
  });
}

// ko dar trūksta, kad detales būtų galima perduoti – rodoma Stop lange iš anksto
function stopNeeds(t) {
  const own = (t.checks || []).filter(c => c.performer === "operator" && (c.status === "laukia" || c.status === "nok"));
  const qc = (t.checks || []).filter(c => c.performer === "qc" && (c.status === "laukia" || c.status === "nok"));
  const mat = t.needs_material && !(t.materials || []).length;
  if (!own.length && !mat && !qc.length) return "";
  return `<div class="card warnbox" style="color:var(--fg)">${own.length || mat ? `<b>Prieš perduodant gerus vienetus:</b><ul>
    ${own.map(c => `<li>įveskite patikrą „${esc(c.name)}“</li>`).join("")}${mat ? `<li>nurodykite medžiagos lydinį</li>` : ""}</ul>` : ""}
    ${qc.length ? `<div class="muted">Po Stop detalės bus sulaikytos, kol kokybės inžinierius atliks: ${esc(qc.map(c => c.name).join(", "))}</div>` : ""}</div>`;
}

function heldModal(r, after) {
  modal(`<div class="move"><div class="muted">${r.qty_good} VNT. SULAIKYTA</div>
    <div class="dest" style="border-color:var(--pause)"><span class="arrow" style="color:var(--pause)">⧗</span><div><div class="big-c">Laukia kokybės kontrolės</div>
      <div class="muted">${esc(r.held.join(", "))} – detalių kol kas neneškite. Perdavimas bus įrašytas, kai kokybės inžinierius patvirtins.</div></div></div>
    <button id="mv-ok" class="b-ok">Supratau</button></div>`, () => { $("#mv-ok").onclick = () => { closeModal(); after(); }; });
}

async function ncr8d(id, after) {
  const [n, qm] = await Promise.all([GET(`/api/ncr/${id}`), GET("/api/quality/meta")]);
  const ed = can("ncr_manage") && n.status !== "uzdaryta";
  const field = (k, label, ph) => `<label>${label}${ed ? `<textarea id="d-${k}" placeholder="${esc(ph)}">${esc(n[k] || "")}</textarea>` : `<div>${esc(n[k] || "—")}</div>`}</label>`;
  modal(`<div class="row between"><h2>Neatitiktis NCR-${n.id}</h2>${pill(n.status, n.status_label)}</div>
    <p><b class="mono">${esc(n.project_code)}</b> ${esc(n.assembly_code || "")} · ${esc(n.centre_code || "")} ${esc(n.task_name || "")} · ${esc(n.category_label)}${n.qty ? ` · ${n.qty} vnt.` : ""}</p>
    <p><b>D2 Problema:</b> ${esc(n.description)} <span class="muted small">– ${esc(n.reporter || "")}, ${dt(n.reported_at)}</span></p>
    ${field("containment", "D3 Laikini veiksmai (izoliavimas)", "kas padaryta iškart: detalės atskirtos, pažymėtos…")}
    ${field("root_cause", "D4 Šakninė priežastis *", "kodėl įvyko (5 kodėl)")}
    ${field("corrective", "D5–D6 Korekciniai veiksmai", "kas pataisyta")}
    ${field("preventive", "D7 Kad nepasikartotų", "procedūros, instrukcijų, įrankių pakeitimai")}
    <label>Sprendimas dėl gaminio *${ed ? `<select id="d-disposition">${opt(qm.dispositions, n.disposition, "—")}</select>` : `<b>${esc(n.disposition_label || "—")}</b>`}</label>
    <div><b>Nuotraukos ir dokumentai</b><div class="row">${n.files.map(f => `<a class="fchip" href="/api/ncr_files/${f.id}" target="_blank">📷 ${esc(f.name)}</a>`).join("") || `<span class="muted">nėra</span>`}
      ${n.status !== "uzdaryta" ? `<label class="btn ghost small upl">+ Nuotrauka<input type="file" accept="image/*,application/pdf" capture="environment" hidden id="d-file"></label>` : ""}</div></div>
    ${ed ? `<label>D8 Sprendimas (uždarant)<textarea id="d-res">${esc(n.resolution || "")}</textarea></label>`
      : n.resolution ? `<p><b>D8 Sprendimas:</b> ${esc(n.resolution)}</p>` : ""}
    <div class="row">${ed ? `<button id="d-close">Uždaryti</button><button class="ghost" id="d-save">Įrašyti juodraštį</button>` : ""}<button class="ghost" id="d-x">Uždaryti langą</button></div>`, () => {
    const body = () => Object.fromEntries(["containment", "root_cause", "corrective", "preventive", "disposition"].map(k => [k, $(`#d-${k}`).value]));
    $("#d-x").onclick = () => { closeModal(); after && after(); };
    const f = $("#d-file");
    if (f) f.onchange = async () => { const fd = new FormData(); fd.append("file", f.files[0]); await act(() => api("POST", `/api/ncr/${id}/files`, fd, true), "Įkelta"); ncr8d(id, after); };
    const sv = $("#d-save"); if (sv) sv.onclick = async () => { await act(() => PUT(`/api/ncr/${id}`, body()), "Įrašyta"); ncr8d(id, after); };
    const cl = $("#d-close"); if (cl) cl.onclick = async () => { await act(() => POST(`/api/ncr/${id}/close`, { ...body(), resolution: $("#d-res").value }), "Neatitiktis uždaryta"); closeModal(); after && after(); };
  });
}

async function pageQuality(tab) {
  const tabs = [...(can("quality") ? [["kontrole", "Kontrolės eilė"]] : []), ["medziagos", "Medžiagos ir sertifikatai"], ["suvirinimas", "Suvirinimas: WPS ir kvalifikacijos"],
    ...(can("quality") || can("tasks") ? [["sablonai", "Patikrų šablonai"]] : []), ["dosje", "Dosjė"]];
  tab = tabs.some(t => t[0] === tab) ? tab : tabs[0][0];
  const head = `<div class="row between"><h1>Kokybė</h1><span class="muted small">EN 1090 / ISO 3834</span></div>
    <nav class="tabs">${tabs.map(([k, l]) => `<a href="#/kokybe/${k}" class="${k === tab ? "on" : ""}">${l}</a>`).join("")}</nav>`;
  const reload = () => pageQuality(tab);
  if (tab === "kontrole") {
    const q = await GET("/api/quality/queue");
    app().innerHTML = head + `<div class="card"><h2>Laukiančios kokybės patikros</h2>
      <p class="muted">Pirmiausia – tos, dėl kurių ceche sulaikytos detalės. OK – detalės iškart perduodamos kitai operacijai; NOK – užregistruojama neatitiktis.</p>
      ${q.length ? `<div class="tbl"><table><thead><tr><th>Projektas · mazgas</th><th>Operacija</th><th>Patikra</th><th>Būsena</th><th>Rezultatas</th></tr></thead><tbody>
      ${q.map(c => `<tr><td><b class="mono">${esc(c.project_code)}</b> ${esc(c.assembly_code)}${c.part_no ? ` <span class="muted">${esc(c.part_no)}</span>` : ""}</td>
        <td><span class="mono">${esc(c.centre_code)}</span> ${esc(c.task_name)}<div class="muted small">${c.qty_good}/${c.qty_plan} vnt.</div></td>
        <td><b>${esc(c.name)}</b>${c.tolerance ? `<div class="muted small">${esc(c.tolerance)}</div>` : ""}${c.instruction ? `<div class="muted small">${esc(c.instruction)}</div>` : ""}</td>
        <td>${c.holding ? `<span class="sev yellow">sulaikyta ${c.qty_good} vnt.</span>` : `<span class="muted">detalės dar gaminamos</span>`}${c.status === "nok" ? ` <span class="sev red">NOK</span>` : ""}</td>
        <td class="nw">${c.kind === "measure" ? `<input type="text" inputmode="decimal" autocomplete="off" style="width:90px" data-qv="${c.id}" placeholder="${esc(c.unit)}" aria-label="${esc(c.name)}"> <button class="small" data-qm="${c.id}">Įrašyti</button>`
          : `<button class="small" data-qok="${c.id}">OK</button> <button class="small ghost" data-qnok="${c.id}">NOK</button>`} <button class="small ghost" data-qw="${c.id}">Išimtis</button></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="s-baigta">✓ Laukiančių patikrų nėra.</p>`}</div>`;
    const res = async (id, body) => { const r = await act(() => POST(`/api/checks/${id}/result`, body)); toast(r.ok ? `OK${r.released ? ` – perduota ${r.released} vnt.` : ""}` : "NOK – užregistruota neatitiktis", !r.ok); reload(); };
    $$("[data-qok]").forEach(b => b.onclick = () => res(b.dataset.qok, { ok: true }));
    $$("[data-qm]").forEach(b => b.onclick = () => res(b.dataset.qm, { value: $(`[data-qv="${b.dataset.qm}"]`).value }));
    $$("[data-qnok]").forEach(b => b.onclick = () => modal(`<h2>NOK – kas negerai?</h2><label>Aprašymas<textarea id="qn"></textarea></label>
      <div class="row"><button id="qn-ok">Įrašyti NOK</button><button class="ghost" id="qn-x">Atšaukti</button></div>`, () => {
      $("#qn-x").onclick = closeModal; $("#qn-ok").onclick = async () => { closeModal(); await res(b.dataset.qnok, { ok: false, note: $("#qn").value }); }; }));
    $$("[data-qw]").forEach(b => b.onclick = () => waiveModal(+b.dataset.qw, reload));
    S.timers.push(setInterval(() => { if ($("#modal").hidden && location.hash.startsWith("#/kokybe")) reload(); }, 30000));
  } else if (tab === "medziagos") {
    const [lots, qm] = await Promise.all([GET("/api/quality/lots"), GET("/api/quality/meta")]);
    const canAdd = can("quality") || can("receive");
    app().innerHTML = head + `${canAdd ? `<form id="lt-new" class="card inline"><h2 style="flex-basis:100%">Gautas metalas</h2>
      <label>Lydinio nr. *<input name="heat_no" required style="width:120px" id="ln-h"></label><label>Medžiaga *<input name="material" required placeholder="S355J2+N" style="width:120px" id="ln-m"></label>
      <label>Gaminys<input name="product" placeholder="lakštas t10 3000×1500" id="ln-p"></label><label>Tiekėjas<input name="supplier" id="ln-s"></label>
      <label>Sertifikato nr.<input name="cert_no" style="width:110px" id="ln-c"></label><label>Tipas<select name="cert_type" id="ln-t">${qm.cert_types.map(x => `<option ${x === "3.1" ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label>Kiekis<input name="qty" type="number" step="any" style="width:80px" id="ln-q"></label><label>Vnt.<input name="unit" value="vnt" style="width:60px" id="ln-u"></label>
      <label>Sertifikatas (PDF)<input type="file" name="file" accept="application/pdf" id="ln-f"></label><button>Registruoti</button></form>` : ""}
      <div class="card"><div class="row between"><h2>Lydiniai</h2><input id="lt-s" placeholder="Ieškoti…" style="width:220px"></div>
      <div class="tbl"><table><thead><tr><th>Lydinys</th><th>Medžiaga</th><th>Tiekėjas</th><th>Sertifikatas</th><th>Gauta</th><th>Panaudota</th><th>Būsena</th></tr></thead>
      <tbody id="lt-b">${lots.map(l => `<tr data-s="${esc(`${l.heat_no} ${l.material} ${l.product} ${l.supplier} ${l.cert_no}`.toLowerCase())}"><td class="mono"><b>${esc(l.heat_no)}</b></td><td>${esc(l.material)}<div class="muted small">${esc(l.product)}</div></td>
        <td>${esc(l.supplier || "—")}</td><td>${l.cert_file ? `<a href="/api/quality/lots/${l.id}/cert" target="_blank">${esc(l.cert_no || "PDF")}</a>` : esc(l.cert_no || "—")} <span class="muted">${esc(l.cert_type)}</span></td>
        <td class="num">${dt(l.received_at)}<div class="muted small">${esc(l.received_by_name || "")}</div></td><td class="num">${l.used} op.</td>
        <td>${l.status === "tinkama" ? pill("baigta", "tinkama") : `${pill("atvira", "blokuota")}<div class="lock small">${esc(l.note)}</div>`}
          ${can("quality") ? `<button class="small ghost" data-lst="${l.id}" data-to="${l.status === "tinkama" ? "blokuota" : "tinkama"}">${l.status === "tinkama" ? "Blokuoti" : "Atblokuoti"}</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="7" class="muted">Lydinių dar nėra.</td></tr>`}</tbody></table></div></div>`;
    $("#lt-s").oninput = e => $$("#lt-b tr[data-s]").forEach(r => (r.hidden = !r.dataset.s.includes(e.target.value.toLowerCase())));
    const f = $("#lt-new"); if (f) f.onsubmit = async e => { e.preventDefault(); const fd = new FormData(f); if (!$("#ln-f").files.length) fd.delete("file");
      await act(() => api("POST", "/api/quality/lots", fd, true), "Lydinys užregistruotas"); reload(); };
    $$("[data-lst]").forEach(b => b.onclick = async () => {
      const note = b.dataset.to === "blokuota" ? prompt("Kodėl medžiaga blokuojama?") : "";
      if (b.dataset.to === "blokuota" && !note) return;
      await act(() => POST(`/api/quality/lots/${b.dataset.lst}/status`, { status: b.dataset.to, note }), "Įrašyta"); reload(); });
  } else if (tab === "suvirinimas") {
    const [wps, quals, users] = await Promise.all([GET("/api/quality/wps"), GET("/api/quality/qualifications"), GET("/api/users").catch(() => [])]);
    const qe = can("quality");
    app().innerHTML = head + `<div class="card"><h2>Suvirintojų kvalifikacijos</h2>
      <p class="muted">Terminalas neleidžia pradėti suvirinimo pagal WPS, jei prisijungęs suvirintojas neturi galiojančios kvalifikacijos tam procesui ir medžiagų grupei.</p>
      <div class="tbl"><table><thead><tr><th>Suvirintojas</th><th>Standartas</th><th>Procesas</th><th>Grupė</th><th>Sertifikatas</th><th>Galioja iki</th></tr></thead><tbody>
      ${quals.map(x => `<tr><td>${esc(x.user_name)}</td><td>${esc(x.standard)}</td><td class="mono">${esc(x.process)}</td><td class="mono">${esc(x.material_group)}</td>
        <td>${x.file ? `<a href="/api/quality/file?path=${encodeURIComponent(x.file)}" target="_blank">${esc(x.cert_no || "PDF")}</a>` : esc(x.cert_no || "—")}</td>
        <td class="num ${x.valid ? (x.expires_soon ? "warn" : "") : "s-late"}">${esc(x.valid_until)}${x.valid ? (x.expires_soon ? " · baigiasi" : "") : " · negalioja"}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">Kvalifikacijų dar nėra.</td></tr>`}</tbody></table></div>
      ${qe ? `<form id="ql-new" class="inline"><label>Suvirintojas<select name="user_id" id="qn-u">${opt(users.filter(u => u.active && u.perms.includes("execute")), "")}</select></label>
        <label>Procesas<input name="process" required placeholder="135" style="width:70px" id="qn-p"></label><label>Grupė<input name="material_group" required placeholder="1.1" style="width:70px" id="qn-g"></label>
        <label>Standartas<input name="standard" value="ISO 9606-1" style="width:110px" id="qn-s"></label><label>Sert. nr.<input name="cert_no" style="width:110px" id="qn-c"></label>
        <label>Galioja iki<input type="date" name="valid_until" required id="qn-v"></label><label>PDF<input type="file" name="file" accept="application/pdf" id="qn-f"></label><button class="ghost">Pridėti</button></form>` : ""}</div>
      <div class="card"><h2>Suvirinimo procedūros (WPS)</h2>
      <div class="tbl"><table><thead><tr><th>Kodas</th><th>Procesas</th><th>Medžiagų grupė</th><th>Aprašymas</th><th>Dokumentas</th></tr></thead><tbody>
      ${wps.map(w => `<tr><td class="mono"><b>${esc(w.code)}</b></td><td class="mono">${esc(w.process)}</td><td class="mono">${esc(w.material_group)}</td><td>${esc(w.description)}</td>
        <td>${w.file ? `<a href="/api/quality/file?path=${encodeURIComponent(w.file)}" target="_blank">PDF</a>` : "—"}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">WPS dar nėra.</td></tr>`}</tbody></table></div>
      ${qe ? `<form id="wp-new" class="inline"><label>Kodas<input name="code" required style="width:120px" id="wn-c"></label><label>Procesas<input name="process" required placeholder="135" style="width:70px" id="wn-p"></label>
        <label>Grupė<input name="material_group" required placeholder="1.1" style="width:70px" id="wn-g"></label><label>Aprašymas<input name="description" id="wn-d"></label>
        <label>PDF<input type="file" name="file" accept="application/pdf" id="wn-f"></label><button class="ghost">Pridėti WPS</button></form>` : ""}</div>`;
    const form = (id, url, msg) => { const f = $(id); if (f) f.onsubmit = async e => { e.preventDefault(); const fd = new FormData(f); if (!f.querySelector("[type=file]").files.length) fd.delete("file");
      await act(() => api("POST", url, fd, true), msg); reload(); }; };
    form("#ql-new", "/api/quality/qualifications", "Kvalifikacija pridėta"); form("#wp-new", "/api/quality/wps", "WPS pridėtas");
  } else if (tab === "sablonai") {
    const [list, qm] = await Promise.all([GET("/api/quality/templates?all=1"), GET("/api/quality/meta")]);
    app().innerHTML = head + `<div class="card"><h2>Patikrų šablonai</h2><p class="muted">Technologas juos priskiria operacijoms maršruto redaktoriuje („+ Patikra“).</p>
      <div class="tbl"><table><thead><tr><th>Kodas</th><th>Patikra</th><th>Tipas</th><th>Atlieka</th><th>Instrukcija</th></tr></thead><tbody>
      ${list.map(t => `<tr class="${t.active ? "" : "dim"}"><td class="mono">${esc(t.code)}</td><td><b>${esc(t.name)}</b></td>
        <td>${t.kind === "measure" ? `matavimas ${esc(String(t.nominal ?? "").replace(".", ","))} −${t.tol_minus ?? 0}/+${t.tol_plus ?? 0} ${esc(t.unit)}` : "OK / NOK"}</td>
        <td>${esc((qm.performers.find(p => p.key === t.performer) || {}).label || t.performer)}</td><td class="small">${esc(t.instruction)}</td></tr>`).join("")}</tbody></table></div>
      <form id="tp-new" class="inline"><label>Kodas<input name="code" required style="width:100px" id="tn-c"></label><label>Pavadinimas<input name="name" required id="tn-n"></label>
        <label>Tipas<select name="kind" id="tn-k"><option value="check">OK / NOK</option><option value="measure">Matavimas</option></select></label>
        <label>Vardinė<input name="nominal" type="number" step="any" style="width:80px" id="tn-v"></label><label>−tol.<input name="tol_minus" type="number" step="any" style="width:70px" id="tn-lo"></label>
        <label>+tol.<input name="tol_plus" type="number" step="any" style="width:70px" id="tn-hi"></label><label>Vnt.<input name="unit" style="width:60px" id="tn-u"></label>
        <label>Atlieka<select name="performer" id="tn-p">${opt(qm.performers)}</select></label><label>Instrukcija<input name="instruction" id="tn-i"></label><button class="ghost">Pridėti</button></form></div>`;
    $("#tp-new").onsubmit = async e => { e.preventDefault(); await act(() => POST("/api/quality/templates", formData(e.target)), "Šablonas pridėtas"); reload(); };
  } else {
    const ps = await GET("/api/projects?all=1");
    app().innerHTML = head + `<div class="card"><h2>Projekto kokybės dosjė</h2><p class="muted">Medžiagų atsekamumas, suvirinimo žurnalas, patikrų protokolas, neatitiktys – spausdinimui ar PDF, priedai – ZIP.</p>
      <div class="tbl"><table><thead><tr><th>Projektas</th><th>Klasė</th><th>Būsena</th><th></th></tr></thead><tbody>
      ${ps.map(p => `<tr><td><b class="mono">${esc(p.code)}</b> ${esc(p.name)}</td><td>${esc(p.exc_class || "—")}</td><td>${pill(p.status, p.status_label)}</td>
        <td><a class="btn ghost small" href="#/dosje/${p.id}">Atidaryti</a></td></tr>`).join("")}</tbody></table></div></div>`;
  }
}

async function pageDossier(pid) {
  const d = await GET(`/api/quality/dossier/${pid}`);
  const p = d.project, st = { laukia: "laukia", ok: "OK", nok: "NOK", isimtis: "išimtis" };
  app().innerHTML = `<div class="row between noprint"><a href="#/kokybe/dosje">← Kokybė</a>
    <div class="row"><a class="btn ghost" href="/api/quality/dossier/${pid}/zip">⬇ Priedai (ZIP)</a><button id="dp">🖨 Spausdinti / PDF</button></div></div>
  <section class="dossier">
    <div class="rc-head"><div><div class="muted">KOKYBĖS DOSJĖ · EN 1090 / ISO 3834</div><h1><span class="mono">${esc(p.code)}</span> ${esc(p.name)}</h1>
      <div>${esc(p.customer)} · vadovas ${esc(p.manager_name || "—")} · vykdymo klasė <b>${esc(p.exc_class || "nenurodyta")}</b></div>
      <div class="muted small">Sudaryta ${dt(d.generated)}</div></div>
      <div>${d.complete ? pill("baigta", "dosjė pilnas") : pill("atvira", `trūksta: ${d.gaps.length}`)}</div></div>
    ${d.gaps.length ? `<div class="card warnbox"><h2>Ko trūksta</h2><ul>${d.gaps.map(g => `<li>${esc(g)}</li>`).join("")}</ul></div>` : ""}
    <div class="card"><h2>1. Medžiagų atsekamumas</h2>${simple(d.materials, ["Mazgas · detalė", "Operacija", "Lydinys", "Medžiaga", "Sertifikatas"], m => [
      `${esc(m.assembly)}${m.part ? ` <span class="mono">${esc(m.part)}</span>` : ""}`, `<span class="mono">${esc(m.centre)}</span> ${esc(m.operation)}`, `<b class="mono">${esc(m.heat_no)}</b>`,
      `${esc(m.material)} <span class="muted">${esc(m.product)}</span>`, `${m.has_cert ? `<a href="/api/quality/lots/${m.lot_id}/cert" target="_blank">${esc(m.cert_no || "PDF")}</a>` : esc(m.cert_no || "—")} ${esc(m.cert_type)}`])}</div>
    <div class="card"><h2>2. Suvirinimo žurnalas</h2>${simple(d.welding, ["Mazgas", "Operacija", "WPS", "Suvirintojas", "Kvalifikacija", "Laikas"], w => [
      esc(w.assembly), `<span class="mono">${esc(w.centre)}</span> ${esc(w.operation)}`, `<span class="mono">${esc(w.wps || "—")}</span>`, esc(w.welder),
      w.qualification ? `${esc(w.qualification.cert_no || "")} ${esc(w.qualification.process)}/${esc(w.qualification.material_group)} <span class="${w.qualification.valid_until >= (w.end || "").slice(0, 10) ? "" : "s-late"}">iki ${esc(w.qualification.valid_until)}</span>` : `<span class="s-late">nėra</span>`,
      `<span class="num">${dt(w.start)} – ${dt(w.end)}</span>`])}</div>
    <div class="card"><h2>3. Patikrų protokolas</h2>${simple(d.inspections, ["Mazgas", "Operacija", "Patikra", "Rezultatas", "Kas, kada"], c => [
      `${esc(c.assembly)}${c.part ? ` <span class="mono">${esc(c.part)}</span>` : ""}`, `<span class="mono">${esc(c.centre)}</span> ${esc(c.operation)}`,
      `${esc(c.name)}${c.tolerance ? ` <span class="muted">${esc(c.tolerance)}</span>` : ""}`,
      `<span class="${CHK_CLS[c.status]}">${esc(st[c.status])}${c.value != null ? ` · ${esc(String(c.value).replace(".", ","))} ${esc(c.unit)}` : ""}</span>${c.waiver_reason ? `<div class="small">${esc(c.waiver_reason)}</div>` : ""}`,
      `${esc(c.done_by_name || "—")} <span class="muted">${dt(c.done_at)}</span>`])}</div>
    <div class="card"><h2>4. Neatitiktys</h2>${d.ncr.length ? d.ncr.map(n => `<div class="ncr8"><div class="row between"><b>NCR-${n.id} · ${esc(n.category_label)}</b>${pill(n.status, n.status_label)}</div>
      <div>${esc(n.description)} <span class="muted small">${dt(n.reported_at)}, ${esc(n.reporter || "")}</span></div>
      ${[["Laikini veiksmai", n.containment], ["Šakninė priežastis", n.root_cause], ["Korekciniai veiksmai", n.corrective], ["Kad nepasikartotų", n.preventive], ["Sprendimas dėl gaminio", n.disposition_label], ["Sprendimas", n.resolution !== n.corrective ? n.resolution : ""]]
        .filter(x => x[1]).map(([k, v]) => `<div class="small"><b>${k}:</b> ${esc(v)}</div>`).join("")}
      ${n.files.length ? `<div class="small muted">Priedai: ${n.files.map(f => esc(f.name)).join(", ")}</div>` : ""}</div>`).join("") : `<p class="muted">Neatitikčių nebuvo.</p>`}</div>
  </section>`;
  $("#dp").onclick = () => window.print();
}

// ---------- neatitiktys ----------
function ncrTable(list, manage, users) {
  if (!list.length) return `<p class="muted">Neatitikčių nėra.</p>`;
  return `<div class="tbl"><table><thead><tr><th>Nr.</th><th>Data</th><th>Projektas · mazgas</th><th>Operacija</th><th>Kategorija</th><th>Aprašymas</th><th>Būsena</th><th></th></tr></thead>
    <tbody>${list.map(n => `<tr><td class="num">${n.id}</td><td class="num">${dt(n.reported_at)}<br><span class="muted">${esc(n.reporter || "")}</span></td>
      <td><span class="mono">${esc(n.project_code)}</span> ${esc(n.assembly_code || "")}</td><td>${esc(n.centre_code || "")} ${esc(n.task_name || "")}</td>
      <td>${esc(n.category_label)}${n.qty ? ` · ${n.qty} vnt.` : ""}</td><td>${esc(n.description)}${n.resolution ? `<br><span class="muted">Sprendimas: ${esc(n.resolution)}</span>` : ""}</td>
      <td>${pill(n.status, n.status_label)}${n.assignee ? `<br><span class="muted">${esc(n.assignee)}</span>` : ""}</td>
      ${manage ? `<td class="nw">${n.status !== "uzdaryta" ? `<select data-asg="${n.id}" id="asg-${n.id}">${opt(users, n.assignee_id, "Priskirti…")}</select> ` : ""}<button class="small ghost" data-8d="${n.id}">${n.status !== "uzdaryta" ? "8D / uždaryti" : "8D"}</button></td>`
        : `<td><button class="small ghost" data-8d="${n.id}">Atidaryti</button></td>`}</tr>`).join("")}</tbody></table></div>`;
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
  $$("[data-8d]").forEach(b => b.onclick = () => ncr8d(+b.dataset["8d"], pageNcr));
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
// ---------- administravimas: vartotojai, rolės ir teisės, barai ir centrai, žurnalas ----------
// Vartotojo sprendimai (2026-10-26): rolės redaguojamos (matrica rolė × teisė),
// vartotojui – viena rolė ir prireikus individualios išimtys; meistro veiksmai
// ribojami jo barais; kiekvienas teisių pakeitimas – žurnale (auditui).
async function pageAdmin(tab, id) {
  tab = tab || "vartotojai";
  if (tab === "vartotojai" && id) return pageUserCard(+id);
  if (tab === "vartotojai") return pageUsers();
  if (tab === "roles") return pageRoles();
  if (tab === "zurnalas") return pageAccessLog();
  return pageCentresAdmin();
}

const SRC_LABEL = { "rolė": "pagal rolę", papildomai: "papildomai", "atimta": "atimta" };
// barai ir centrai kaip medis: pažymėtas baras – visi jo centrai (ir nauji)
function placesTree(areas, centres, sel, idp) {
  const groups = byArea(centres);
  return `<div class="utree">${groups.map(g => {
    const a = areas.find(x => x.code === g.code), on = g.code && sel.includes(g.code);
    return `<div class="ut-a"><label class="row" style="display:flex">${g.code ? `<input type="checkbox" data-pa="${esc(g.code)}" ${on ? "checked" : ""} id="${idp}-a-${esc(g.code)}">` : ""}
        <b>${esc(a ? a.name : g.name)}</b>${g.code ? ` <span class="muted mono small">${esc(g.code)}</span>` : ""}</label>
      <div class="ut-c">${g.items.map(c => `<label class="row" style="display:flex"><input type="checkbox" data-pc="${esc(c.code)}" data-area="${esc(g.code)}"
        ${on || sel.includes(c.code) ? "checked" : ""} ${on ? "disabled" : ""} id="${idp}-c-${esc(c.code)}"><span class="mono">${esc(c.code)}</span></label>`).join("")}</div></div>`;
  }).join("")}</div>`;
}
function readPlaces(box) {
  const out = $$("[data-pa]", box).filter(x => x.checked).map(x => x.dataset.pa);
  $$("[data-pc]", box).forEach(x => { if (x.checked && !out.includes(x.dataset.area)) out.push(x.dataset.pc); });
  return out;
}
function wirePlaces(box) {
  $$("[data-pa]", box).forEach(a => a.onchange = () => $$(`[data-pc][data-area="${a.dataset.pa}"]`, box).forEach(c => { c.checked = a.checked; c.disabled = a.checked; }));
}

async function pageUsers() {
  const [users, roles, areas, centres] = await Promise.all([GET("/api/users"), GET("/api/roles"), GET("/api/areas"), GET("/api/centres?all=1")]);
  let q = "", role = "", place = "";
  try { role = sessionStorage.getItem("pf.urole") || ""; } catch {}
  const draw = () => {
    const list = users.filter(u => (!q || (u.name + " " + u.login).toLowerCase().includes(q.toLowerCase()))
      && (!role || u.role === role) && (!place || u.centres.includes(place) || centres.some(c => c.code && u.centres.includes(c.code) && c.area_code === place)));
    $("#u-list").innerHTML = `<table><thead><tr><th>Vardas</th><th>Prisijungimas</th><th>Rolė</th><th>Barai / centrai</th><th>Išimtys</th><th>PIN</th><th>Būsena</th></tr></thead>
      <tbody>${list.map(u => `<tr class="click ${u.active ? "" : "dim"}" data-go="${u.id}" tabindex="0">
        <td><b>${esc(u.name)}</b></td><td class="mono">${esc(u.login)}</td>
        <td>${esc(u.role_label)}${u.scope === "own" ? ` <span class="tag" title="Eilės, kalendorius, patvirtinimai – tik savo baruose">savo barai</span>` : ""}</td>
        <td class="mono small">${esc(u.centres.join(", ")) || '<span class="muted">visi</span>'}</td>
        <td>${u.perm_add.length ? `<span class="tag plus" title="${esc(u.perm_add.join(", "))}">+${u.perm_add.length}</span>` : ""}${u.perm_remove.length ? ` <span class="tag minus" title="${esc(u.perm_remove.join(", "))}">−${u.perm_remove.length}</span>` : ""}</td>
        <td>${u.has_pin ? "✓" : '<span class="muted">—</span>'}</td><td>${u.active ? pill("baigta", "aktyvus") : pill("tuscia", "išjungtas")}</td></tr>`).join("")
        || `<tr><td colspan="7" class="muted">Nerasta.</td></tr>`}</tbody></table>`;
    $("#u-n").textContent = `${list.length} iš ${users.length}`;
    $$("[data-go]").forEach(tr => { tr.onclick = () => (location.hash = `#/admin/vartotojai/${tr.dataset.go}`); tr.onkeydown = e => e.key === "Enter" && tr.onclick(); });
  };
  app().innerHTML = `<div class="row between"><h1>Vartotojai</h1><button id="u-new">+ Naujas vartotojas</button></div>
    <div class="card"><div class="row">
      <input id="u-q" placeholder="Paieška: vardas ar prisijungimas" aria-label="Paieška" style="flex:1;min-width:180px">
      <select id="u-r" aria-label="Rolė"><option value="">Visos rolės</option>${roles.map(r => `<option value="${esc(r.code)}" ${r.code === role ? "selected" : ""}>${esc(r.name)} (${r.users})</option>`).join("")}</select>
      <select id="u-p" aria-label="Baras"><option value="">Visi barai</option>${areas.map(a => `<option value="${esc(a.code)}">${esc(a.code)} ${esc(a.name)}</option>`).join("")}</select>
      <span class="muted small" id="u-n"></span></div>
      <div class="tbl" id="u-list"></div></div>`;
  $("#u-q").oninput = e => { q = e.target.value; draw(); };
  $("#u-r").onchange = e => { role = e.target.value; try { sessionStorage.setItem("pf.urole", role); } catch {} draw(); };
  $("#u-p").onchange = e => { place = e.target.value; draw(); };
  $("#u-new").onclick = () => modal(`<h2>Naujas vartotojas</h2><form id="nu" class="stack">
    <div class="row"><label style="flex:1">Vardas, pavardė<input name="name" required id="nu-name"></label><label>Prisijungimo vardas<input name="login" required id="nu-login" autocomplete="off"></label></div>
    <label>Rolė<select name="role" id="nu-role">${roles.map(r => `<option value="${esc(r.code)}" ${r.code === "operatorius" ? "selected" : ""}>${esc(r.name)} – ${esc(r.description)}</option>`).join("")}</select></label>
    <div class="row"><label>Slaptažodis<input name="password" type="password" required id="nu-pw" autocomplete="new-password"></label><label>PIN terminalui<input name="pin" inputmode="numeric" style="width:110px" id="nu-pin" autocomplete="off"></label></div>
    <div><b class="small">Kur dirba</b> <span class="muted small">– nieko nepažymėjus: visi barai</span>${placesTree(areas, centres.filter(c => c.active), [], "nu")}</div>
    <div class="row"><button>Sukurti</button><button type="button" class="ghost" id="nu-x">Atšaukti</button></div></form>`, box => {
    wirePlaces(box); $("#nu-x").onclick = closeModal;
    $("#nu").onsubmit = async e => {
      e.preventDefault(); const d = formData(e.target); d.centres = readPlaces(box);
      const r = await act(() => POST("/api/users", d), "Vartotojas sukurtas");
      if (r) { closeModal(); location.hash = `#/admin/vartotojai/${r.id}`; }
    };
  });
  draw();
}

async function pageUserCard(uid) {
  const [u, roles, areas, centres] = await Promise.all([GET(`/api/users/${uid}`), GET("/api/roles"), GET("/api/areas"), GET("/api/centres?all=1")]);
  const st = { role: u.role, add: new Set(u.perm_add), rem: new Set(u.perm_remove) };
  const roleOf = c => roles.find(r => r.code === c) || { perms: [], scope: "all", name: c };
  const perms = () => S.meta.perm_modules;
  const rights = () => {
    const r = roleOf(st.role), has = p => st.role === "admin" || ((r.perms.includes(p) || st.add.has(p)) && !st.rem.has(p));
    const places = readPlaces($("#uc-places"));
    return perms().map(m => `<tr class="mxm"><th colspan="4">${icon(m.key, "mico-s")} ${esc(m.label)}</th></tr>${m.perms.map(p => {
      const inRole = st.role === "admin" || r.perms.includes(p.key), val = st.rem.has(p.key) ? "-" : st.add.has(p.key) ? "+" : "";
      const where = !has(p.key) ? "" : p.scoped && (p.key === "execute" || r.scope === "own") ? (places.length ? places.join(", ") : "visi barai") : p.scoped ? "visi barai" : "";
      return `<tr class="${has(p.key) ? "" : "dim"}"><td title="${esc(p.description)}">${esc(p.label)}<div class="muted small">${esc(p.description)}</div></td>
        <td class="ctr">${inRole ? "✓" : '<span class="muted">—</span>'}</td>
        <td><select data-ex="${p.key}" aria-label="Išimtis: ${esc(p.label)}" ${st.role === "admin" ? "disabled" : ""}>
          <option value="" ${val === "" ? "selected" : ""}>pagal rolę</option>
          ${inRole ? `<option value="-" ${val === "-" ? "selected" : ""}>− atimti</option>` : `<option value="+" ${val === "+" ? "selected" : ""}>+ suteikti</option>`}</select></td>
        <td>${has(p.key) ? `<b class="s-baigta">✓ gali</b>${where ? `<div class="muted small mono">${esc(where)}</div>` : ""}` : '<span class="muted">negali</span>'}</td></tr>`;
    }).join("")}`).join("");
  };
  app().innerHTML = `<div><a href="#/admin/vartotojai">← Vartotojai</a></div>
    <div class="row between"><div><h1>${esc(u.name)}</h1><p class="muted"><span class="mono">${esc(u.login)}</span> · ${u.active ? "aktyvus" : "išjungtas"}${u.last_login ? ` · paskutinį kartą prisijungė ${dt(u.last_login)}` : " · dar nesijungė"}</p></div>
      <div class="row"><button id="uc-save">Išsaugoti pakeitimus</button></div></div>
    <div class="ugrid">
      <div class="card"><h2>Rolė ir darbo vietos</h2>
        <label>Vardas, pavardė<input id="uc-name" value="${esc(u.name)}"></label>
        <label>Rolė<select id="uc-role">${roles.map(r => `<option value="${esc(r.code)}" ${r.code === u.role ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select></label>
        <p class="muted small" id="uc-rdesc"></p>
        <label class="row" style="display:flex"><input type="checkbox" id="uc-act" ${u.active ? "checked" : ""}> aktyvus (išjungus – iškart atjungiamas)</label>
        <div><b class="small">Kur dirba</b> <span class="muted small" id="uc-phint"></span><div id="uc-places">${placesTree(areas, centres.filter(c => c.active), u.centres, "uc")}</div></div>
        <div class="row"><button class="ghost small" id="uc-pw">Nustatyti slaptažodį</button><button class="ghost small" id="uc-pin">${u.has_pin ? "Keisti PIN" : "Nustatyti PIN"}</button>
          ${u.has_pin ? `<button class="ghost small" id="uc-nopin">Pašalinti PIN</button>` : ""}</div></div>
      <div class="card"><div class="row between"><h2>Ką mato ir gali</h2><span class="muted small">Išimtis – tik šiam žmogui, rolė nesikeičia</span></div>
        <div class="tbl"><table class="umx"><thead><tr><th>Teisė</th><th>Rolėje</th><th>Išimtis</th><th>Galioja</th></tr></thead><tbody id="uc-rights"></tbody></table></div></div>
    </div>
    <div class="card"><h2>Teisių pakeitimų istorija</h2>${logTable(u.log, false)}</div>`;
  const upd = () => {
    const r = roleOf(st.role);
    $("#uc-rdesc").textContent = (r.description || "") + (r.scope === "own" ? ". Rolė „savo barai“: eilės, kalendorius ir patvirtinimai galioja tik pažymėtuose baruose, kitur – tik matyti." : "");
    $("#uc-phint").textContent = r.scope === "own" ? "– čia galioja jo veiksmai (eilės, kalendorius, patvirtinimai) ir terminalas" : "– kuriuose terminaluose gali dirbti; nieko nepažymėjus – visi";
    $("#uc-rights").innerHTML = rights();
    $$("[data-ex]").forEach(s => s.onchange = () => {
      st.add.delete(s.dataset.ex); st.rem.delete(s.dataset.ex);
      if (s.value === "+") st.add.add(s.dataset.ex); if (s.value === "-") st.rem.add(s.dataset.ex);
      upd();
    });
  };
  wirePlaces($("#uc-places"));
  $("#uc-places").addEventListener("change", upd);
  $("#uc-role").onchange = e => {
    st.role = e.target.value;
    // išimtys lieka tik tos, kurios naujai rolei dar ką nors keičia
    const r = roleOf(st.role);
    [...st.add].forEach(p => r.perms.includes(p) && st.add.delete(p)); [...st.rem].forEach(p => !r.perms.includes(p) && st.rem.delete(p));
    upd();
  };
  upd();
  $("#uc-save").onclick = async () => {
    const body = { name: $("#uc-name").value.trim(), role: st.role, active: $("#uc-act").checked, centres: readPlaces($("#uc-places")),
      perm_add: [...st.add], perm_remove: [...st.rem] };
    if (await act(() => PUT(`/api/users/${uid}`, body), "Įrašyta")) pageUserCard(uid);
  };
  const secret = (title, field, input) => modal(`<h2>${title}</h2><label>${field === "pin" ? "PIN (4–8 skaitmenys)" : "Naujas slaptažodis"}<input id="sc-v" ${input}></label>
    <div class="row"><button id="sc-ok">Įrašyti</button><button class="ghost" id="sc-x">Atšaukti</button></div>`, () => {
    $("#sc-x").onclick = closeModal; $("#sc-v").focus();
    $("#sc-ok").onclick = async () => {
      const v = $("#sc-v").value; if (!v) return;
      if (field === "pin" && !/^\d{4,8}$/.test(v)) { toast("PIN – 4–8 skaitmenys", true); return; }
      if (await act(() => PUT(`/api/users/${uid}`, { [field]: v }), "Įrašyta")) { closeModal(); pageUserCard(uid); }
    };
  });
  $("#uc-pw").onclick = () => secret("Naujas slaptažodis", "password", 'type="password" autocomplete="new-password"');
  $("#uc-pin").onclick = () => secret("PIN terminalui", "pin", 'inputmode="numeric" autocomplete="off"');
  const np = $("#uc-nopin"); if (np) np.onclick = async () => { if (confirm("Pašalinti PIN? Prie terminalo jis nebegalės prisijungti PIN kodu.") && await act(() => PUT(`/api/users/${uid}`, { pin: "" }), "PIN pašalintas")) pageUserCard(uid); };
}

function logTable(list, withTarget = true) {
  return list.length ? `<div class="tbl"><table><thead><tr><th>Kada</th><th>Kas pakeitė</th>${withTarget ? "<th>Kam</th>" : ""}<th>Pakeitimas</th></tr></thead><tbody>
    ${list.map(l => `<tr><td class="num">${dt(l.at)}</td><td>${esc(l.by_name || "sistema")}</td>
      ${withTarget ? `<td>${l.target === "user" ? `<a href="#/admin/vartotojai/${esc(l.target_id)}">vartotojas</a>` : `<span class="tag">rolė</span> <span class="mono">${esc(l.target_id)}</span>`}</td>` : ""}
      <td>${esc(l.summary)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">Pakeitimų dar nebuvo.</p>`;
}

async function pageAccessLog() {
  let target = "";
  const draw = async () => {
    const list = await GET(`/api/access_log${target ? `?target=${target}` : ""}`);
    app().innerHTML = `<div class="row between"><h1>Teisių žurnalas</h1>
      <select id="al-t" aria-label="Kam"><option value="">Visi pakeitimai</option><option value="user" ${target === "user" ? "selected" : ""}>Vartotojai</option><option value="role" ${target === "role" ? "selected" : ""}>Rolės</option></select></div>
      <div class="card"><p class="muted small">Kas, kada ir kam keitė rolę, teises, darbo vietas, PIN ar slaptažodį (reikšmės nesaugomos). Įrašų ištrinti negalima – auditui (ISO 9001, ISO 3834).</p>${logTable(list)}</div>`;
    $("#al-t").onchange = e => { target = e.target.value; draw(); };
  };
  await draw();
}

async function pageRoles() {
  let roles = await GET("/api/roles");
  const pending = {};                // rolės kodas → {perms:Set, scope}
  const cur = r => pending[r.code] || { perms: new Set(r.perms), scope: r.scope };
  const changed = () => Object.keys(pending).filter(c => { const r = roles.find(x => x.code === c), p = pending[c];
    return p.scope !== r.scope || p.perms.size !== r.perms.length || r.perms.some(x => !p.perms.has(x)); });
  const draw = () => {
    const n = changed().length;
    app().innerHTML = `<div class="row between"><h1>Rolės ir teisės</h1><button id="r-new">+ Nauja rolė</button></div>
    <div class="card"><p class="muted small">Pažymėkite, ką kiekviena rolė gali. Pakeitimas galioja visiems tos rolės žmonėms nuo kito jų veiksmo.
      Atskiram žmogui teisę pridėti ar atimti galima jo kortelėje. <b>Savo barai</b> – eilės, kalendorius, meistro patvirtinimai ir terminalas galioja tik vartotojui priskirtuose baruose, kitur – tik matyti.</p>
      <div class="tbl mxwrap"><table class="mx"><thead><tr><th class="mxp">Teisė</th>${roles.map(r => `<th class="mxr">
        <button class="linkb" data-re="${esc(r.code)}" title="${esc(r.description)}">${esc(r.name)}</button>
        <div class="muted small">${r.users} žm.</div>
        <select data-sc="${esc(r.code)}" aria-label="${esc(r.name)}: kur galioja" ${r.locked ? "disabled" : ""}><option value="all" ${cur(r).scope === "all" ? "selected" : ""}>visi barai</option><option value="own" ${cur(r).scope === "own" ? "selected" : ""}>savo barai</option></select></th>`).join("")}</tr></thead>
      <tbody>${S.meta.perm_modules.map(m => `<tr class="mxm"><th colspan="${roles.length + 1}">${icon(m.key, "mico-s")} ${esc(m.label)}</th></tr>
        ${m.perms.map(p => `<tr><td class="mxp" title="${esc(p.description)}">${esc(p.label)}${p.scoped ? ' <span class="tag" title="Galioja tik savo baruose, jei rolei taip nurodyta">baras</span>' : ""}<div class="muted small">${esc(p.description)}</div></td>
          ${roles.map(r => { const on = cur(r).perms.has(p.key), dirty = pending[r.code] && on !== r.perms.includes(p.key);
            return `<td class="mxc ${dirty ? "dirty" : ""}"><input type="checkbox" data-r="${esc(r.code)}" data-p="${p.key}" ${on ? "checked" : ""} ${r.locked ? "disabled" : ""}
              aria-label="${esc(r.name)}: ${esc(p.label)}"></td>`; }).join("")}</tr>`).join("")}`).join("")}</tbody></table></div></div>
    <div class="savebar" ${n ? "" : "hidden"}><span>Pakeista rolių: <b>${n}</b></span><button id="r-save">Išsaugoti</button><button class="ghost" id="r-undo">Atšaukti</button></div>`;
    $$("[data-r]").forEach(c => c.onchange = () => {
      const r = roles.find(x => x.code === c.dataset.r), p = pending[r.code] = cur(r);
      c.checked ? p.perms.add(c.dataset.p) : p.perms.delete(c.dataset.p); draw();
    });
    $$("[data-sc]").forEach(s => s.onchange = () => { const r = roles.find(x => x.code === s.dataset.sc); (pending[r.code] = cur(r)).scope = s.value; draw(); });
    const sv = $("#r-save"); if (sv) sv.onclick = async () => {
      const list = changed();
      const sum = list.map(c => { const r = roles.find(x => x.code === c), p = pending[c];
        const plus = [...p.perms].filter(x => !r.perms.includes(x)), minus = r.perms.filter(x => !p.perms.has(x));
        return `<li><b>${esc(r.name)}</b> (${r.users} žm.): ${plus.length ? `+ ${esc(plus.join(", "))} ` : ""}${minus.length ? `− ${esc(minus.join(", "))} ` : ""}${p.scope !== r.scope ? (p.scope === "own" ? "· tik savo barai" : "· visi barai") : ""}</li>`; }).join("");
      modal(`<h2>Išsaugoti rolių pakeitimus?</h2><ul>${sum}</ul><p class="muted small">Įrašoma į teisių žurnalą.</p>
        <div class="row"><button id="rs-ok">Išsaugoti</button><button class="ghost" id="rs-x">Atšaukti</button></div>`, () => {
        $("#rs-x").onclick = closeModal;
        $("#rs-ok").onclick = async () => {
          for (const c of list) {
            const p = pending[c];
            if (!await act(() => PUT(`/api/roles/${c}`, { perms: [...p.perms], scope: p.scope }))) { closeModal(); return; }
            delete pending[c];
          }
          closeModal(); toast("Rolės išsaugotos"); roles = await GET("/api/roles"); draw();
        };
      });
    };
    const un = $("#r-undo"); if (un) un.onclick = () => { Object.keys(pending).forEach(k => delete pending[k]); draw(); };
    $("#r-new").onclick = () => modal(`<h2>Nauja rolė</h2><form id="rn" class="stack">
      <label>Pavadinimas<input name="name" required placeholder="pvz. Dažymo meistras" id="rn-name"></label>
      <label>Kodas <span class="muted small">(lotyniškai, nesikeičia)</span><input name="code" required pattern="[a-z][a-z0-9_]{1,23}" placeholder="meistras_dazymo" id="rn-code"></label>
      <label>Teises nukopijuoti iš<select name="copy_from" id="rn-copy"><option value="">— tik „Matyti“ —</option>${roles.map(r => `<option value="${esc(r.code)}">${esc(r.name)}</option>`).join("")}</select></label>
      <label>Aprašymas<input name="description" id="rn-d" placeholder="kam skirta"></label>
      <div class="row"><button>Sukurti</button><button type="button" class="ghost" id="rn-x">Atšaukti</button></div></form>`, () => {
      $("#rn-x").onclick = closeModal;
      $("#rn-name").oninput = e => { const c = $("#rn-code"); if (!c.dataset.touched) c.value = e.target.value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 24); };
      $("#rn-code").oninput = e => (e.target.dataset.touched = 1);
      $("#rn").onsubmit = async e => { e.preventDefault(); if (await act(() => POST("/api/roles", formData(e.target)), "Rolė sukurta")) { closeModal(); roles = await GET("/api/roles"); draw(); } };
    });
    $$("[data-re]").forEach(b => b.onclick = () => {
      const r = roles.find(x => x.code === b.dataset.re);
      modal(`<h2>Rolė „${esc(r.name)}“</h2><p class="muted small mono">${esc(r.code)} · ${r.users} aktyvūs vartotojai${r.system ? " · įprasta rolė" : ""}</p>
        <label>Pavadinimas<input id="re-n" value="${esc(r.name)}"></label><label>Aprašymas<input id="re-d" value="${esc(r.description)}"></label>
        <div class="row"><button id="re-ok">Įrašyti</button>${!r.system ? `<button class="ghost" id="re-del" ${r.users ? "disabled title='Rolę dar turi vartotojai'" : ""}>Pašalinti rolę</button>` : ""}
          <a class="btn ghost" href="#/admin/vartotojai" id="re-u">Vartotojai</a><button class="ghost" id="re-x">Uždaryti</button></div>`, () => {
        $("#re-x").onclick = closeModal;
        $("#re-u").onclick = () => { try { sessionStorage.setItem("pf.urole", r.code); } catch {} closeModal(); };
        $("#re-ok").onclick = async () => { if (await act(() => PUT(`/api/roles/${r.code}`, { name: $("#re-n").value, description: $("#re-d").value }), "Įrašyta")) { closeModal(); roles = await GET("/api/roles"); draw(); } };
        const d = $("#re-del"); if (d) d.onclick = async () => { if (confirm(`Pašalinti rolę „${r.name}“?`) && await act(() => api("DELETE", `/api/roles/${r.code}`), "Rolė pašalinta")) { closeModal(); roles = await GET("/api/roles"); draw(); } };
      });
    });
  };
  draw();
}

async function pageCentresAdmin() {
  const [users, centres, areas] = await Promise.all([GET("/api/users"), GET("/api/centres?all=1"), GET("/api/areas")]);
  const masters = users.filter(u => u.active && u.perms.includes("ack_rev"));
  const areaOpts = sel => opt(areas.map(a => ({ id: a.id, name: a.name })), sel, "Be baro");
  app().innerHTML = `<h1>Barai ir darbo centrai</h1>
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
  <div class="card"><h2>Darbo centrai</h2><div class="tbl"><table><thead><tr><th>Kodas</th><th>Pavadinimas</th><th>Baras</th><th>Rūšis</th><th>Rankinis</th><th>Griežta eilė</th><th>Aktyvus</th><th title="Technologas turi pridėti programą / DXF, kitaip maršruto išleisti negalima">Reikia failo</th></tr></thead>
    <tbody>${centres.map(c => `<tr class="${c.active ? "" : "dim"}"><td class="mono">${esc(c.code)}</td><td>${esc(c.name)}</td>
      <td><select data-c="${c.id}" data-f="area_id" id="c-ar-${c.id}">${areaOpts(c.area_id)}</select></td>
      <td><select data-c="${c.id}" data-f="kind" id="c-k-${c.id}">${opt(S.meta.centre_kinds, c.kind)}</select></td>
      ${["manual", "strict_order", "active", "needs_files"].map(f => `<td><input type="checkbox" data-c="${c.id}" data-f="${f}" ${c[f] ? "checked" : ""} id="c-${f}-${c.id}"></td>`).join("")}</tr>`).join("")}</tbody></table></div>
    <form id="nc" class="inline"><label>Kodas<input name="code" required style="width:100px" id="nc-code"></label><label>Pavadinimas<input name="name" required id="nc-name"></label>
      <label>Baras<select name="area_id" id="nc-area">${areaOpts("")}</select></label>
      <label>Rūšis<select name="kind" id="nc-kind">${opt(S.meta.centre_kinds)}</select></label><button class="ghost">Pridėti centrą</button></form></div>`;
  $$("[data-c]").forEach(el => el.onchange = async () => {
    const f = el.dataset.f;
    await act(() => PUT(`/api/centres/${el.dataset.c}`, { [f]: el.type === "checkbox" ? (el.checked ? 1 : 0) : f === "area_id" ? (el.value ? +el.value : null) : el.value }), "Įrašyta"); pageCentresAdmin();
  });
  $("#nc").onsubmit = async e => { e.preventDefault(); const d = formData(e.target); d.area_id = d.area_id ? +d.area_id : null; await act(() => POST("/api/centres", d), "Centras sukurtas"); pageCentresAdmin(); };
  $$("[data-ar]").forEach(el => el.onchange = async () => {
    const f = el.dataset.f;
    const v = f === "active" ? (el.checked ? 1 : 0) : f === "master_id" ? (el.value ? +el.value : null) : el.value;
    try { await act(() => PUT(`/api/areas/${el.dataset.ar}`, { [f]: v }), "Įrašyta"); } finally { pageCentresAdmin(); }
  });
  $("#na").onsubmit = async e => { e.preventDefault(); const d = formData(e.target); d.master_id = d.master_id ? +d.master_id : null; await act(() => POST("/api/areas", d), "Baras sukurtas"); pageCentresAdmin(); };
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
