"use strict";
const tg = window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData ? window.Telegram.WebApp : null;
const API = "/api/davomat";
const $app = document.getElementById("app");
let TOKEN = null, ME = null, CFG = null;

const STATUS_CLASS = {
  "yopildi": "st-yopildi", "jarayonda": "st-jarayonda", "to'liq emas": "st-tolik-emas",
  "tasdiqlanmagan": "st-tasdiqlanmagan", "qo'lda tuzatilgan": "st-qolda",
};
const OYLAR = ["Yanvar","Fevral","Mart","Aprel","May","Iyun","Iyul","Avgust","Sentabr","Oktabr","Noyabr","Dekabr"];

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]);
}
function todayTashkent() {
  return new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Tashkent", year: "numeric", month: "2-digit", day: "2-digit"}).format(new Date());
}
function addDays(iso, n) {
  const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10);
}
function niceDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${OYLAR[m - 1]}`;
}
function hm(ts) { return ts ? ts.slice(11, 16) : "—"; }
function hmRel(ts, workDate) {
  if (!ts) return "—";
  const t = ts.slice(11, 16);
  return ts.slice(0, 10) !== workDate ? `${t} <span class="muted">(${niceDate(ts)})</span>` : t;
}
function dur(sec) {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60);
  return `${Math.floor(m / 60)}s ${String(m % 60).padStart(2, "0")}m`;
}
const AV_COLORS = ["#15803d", "#0e7490", "#7c3aed", "#c2410c", "#be185d", "#1d4ed8", "#4d7c0f", "#a16207", "#0f766e", "#9333ea"];
function avatar(name, size) {
  const parts = String(name || "?").replace(/[^\p{L}\s]/gu, "").trim().split(/\s+/);
  const ini = ((parts[0] || "?")[0] + ((parts[1] || "")[0] || "")).toUpperCase();
  let h = 0; for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const sz = size ? `width:${size}px;height:${size}px;font-size:${Math.round(size / 2.9)}px;` : "";
  return `<div class="avatar" style="${sz}background:${AV_COLORS[h % AV_COLORS.length]}">${esc(ini)}</div>`;
}
const IC = {
  now: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  day: '<rect x="3" y="4" width="18" height="18" rx="3"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  period: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
  checkins: '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
  guards: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  my: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
  admin: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  profile: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="10" r="3"/><path d="M6.2 18.5a7 7 0 0 1 11.6 0"/>',
  more: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
  chev: '<path d="M9 18l6-6-6-6"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
};
function icon(name, size) { return `<svg class="i" viewBox="0 0 24 24" ${size ? `style="width:${size}px;height:${size}px"` : ""}>${IC[name] || ""}</svg>`; }
function tile(n, label, tone, href, ic) {
  const tag = href ? `a href="${href}"` : "div";
  return `<${tag} class="stat tone-${tone || "gray"}">${ic ? `<div class="ic">${icon(ic, 18)}</div>` : ""}<div class="n">${n}</div><div class="l">${label}</div></${href ? "a" : "div"}>`;
}
function status(s) { return `<span class="st ${STATUS_CLASS[s] || ""}">${esc(s)}</span>`; }
function chips(list) { return (list || []).map(f => `<span class="chip">${esc(f)}</span>`).join(""); }
function shiftLabel(t) { return {"kun": "", "kunduzgi": "☀️ kunduzgi", "tungi": "🌙 tungi", "noma'lum": "❓ smena noma'lum"}[t] ?? t; }
function qs(params) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, v); });
  const s = p.toString();
  return s ? "?" + s : "";
}
function isSuper() { return ME && ME.level === "superadmin"; }
function isAdmin() { return ME && (ME.level === "admin" || ME.level === "superadmin"); }
// Boshqalarning davomatini faqat admin ko'radi; qolganlar faqat o'zinikini.
function isViewer() { return isAdmin(); }
const LEVEL_NAMES = {superadmin: "👑 Super admin", admin: "🛠 Admin"};
function levelName(l) { return LEVEL_NAMES[l] || "xodim"; }
function canManage(level) { return isSuper() ? level !== "superadmin" : (!level || level === "viewer"); }
function homeTab() { return isViewer() ? "now" : (ME && ME.employee_no ? "my" : "profile"); }

let ROUTE_SEQ = 0;
const STALE = "__stale__";

async function api(path, opts = {}) {
  // Sahifa almashgan bo'lsa, eski so'rov javobi yangi sahifani bosib ketmasin.
  const seq = ROUTE_SEQ;
  const headers = Object.assign({}, opts.headers || {});
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const r = await fetch(API + path, {method: opts.method || "GET", headers, body: opts.body, credentials: "same-origin"});
  if (r.status === 401 && !opts.noAuthRedirect) { TOKEN = null; renderLogin(); throw new Error("Avtorizatsiya kerak"); }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.blob();
  if (seq !== ROUTE_SEQ) throw new Error(STALE);
  if (!r.ok) throw new Error((data && data.detail) ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : `Xato ${r.status}`);
  return data;
}

async function download(path, fileName) {
  try {
    if (tg && tg.downloadFile) {
      const {url} = await api("/download-link", {method: "POST", json: {path}});
      tg.downloadFile({url: location.origin + url, file_name: fileName});
      return;
    }
    const blob = await api(path);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = fileName; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  } catch (e) { alertMsg(e.message); }
}
function askConfirm(m) {
  return new Promise(res => (tg && tg.showConfirm) ? tg.showConfirm(m, ok => res(!!ok)) : res(window.confirm(m)));
}
function alertMsg(m) { if (m === STALE) return; if (tg && tg.showAlert) tg.showAlert(m); else alert(m); }

// ------------------------------ theme ------------------------------
function applyTheme() {
  if (!tg) return;
  const p = tg.themeParams || {};
  const root = document.documentElement;
  root.setAttribute("data-theme", tg.colorScheme === "dark" ? "dark" : "light");
  const map = {"--bg": p.secondary_bg_color, "--card": p.bg_color, "--text": p.text_color, "--muted": p.hint_color,
               "--accent": p.button_color, "--accent-text": p.button_text_color, "--line": p.section_separator_color};
  Object.entries(map).forEach(([k, v]) => { if (v) root.style.setProperty(k, v); });
}

// ------------------------------ auth ------------------------------
async function boot() {
  if (tg) { document.documentElement.classList.add("in-tg"); tg.ready(); tg.expand(); applyTheme(); tg.onEvent("themeChanged", applyTheme); }
  // Sozlamalar va Telegram avtorizatsiyasi bir vaqtda — sekin tarmoqda bitta kutish kam.
  const cfgP = api("/config", {noAuthRedirect: true}).catch(() => ({}));
  const authP = tg ? api("/auth/webapp", {method: "POST", json: {init_data: tg.initData}, noAuthRedirect: true}) : null;
  CFG = await cfgP;
  if (authP) {
    try { TOKEN = (await authP).token; }
    catch (e) { $app.innerHTML = `<div class="login"><div class="err">${esc(e.message)}</div></div>`; return; }
  }
  try { ME = await api("/me", {noAuthRedirect: true}); } catch { return renderLogin(); }
  afterLogin();
}

const NAV = [
  {id: "now", label: "Hozir", need: "admin"},
  {id: "day", label: "Kunlik", need: "admin"},
  {id: "period", label: "Davr", need: "admin"},
  {id: "checkins", label: "Check-in", need: "admin"},
  {id: "guards", label: "Qorovullar", need: "admin"},
  {id: "my", label: "Mening davomatim", short: "Davomatim", need: "employee"},
  {id: "admin", label: "Admin", need: "admin"},
  {id: "profile", label: "Profil"},
];
const TITLES = {now: "Hozir fermada", day: "Kunlik hisobot", period: "Davr hisoboti", checkins: "Tashqi check-in",
  guards: "Qorovul smenalari", my: "Mening davomatim", admin: "Boshqaruv", profile: "Profil", emp: "Xodim", more: "Menyu"};
function allowedNav() {
  return NAV.filter(n => !n.need || (n.need === "admin" && isAdmin()) || (n.need === "employee" && ME.employee_no));
}
function buildNav() {
  const items = allowedNav();
  document.getElementById("side-nav").innerHTML = items.map(n =>
    `${n.id === "admin" ? '<div class="sep"></div>' : ""}<a href="#/${n.id}" data-tab="${n.id}">${icon(n.id)}<span>${n.label}</span></a>`).join("");
  // Telefonda: 4 ta asosiy bo'lim + qolganlari "Menyu" da.
  const primary = items.length <= 5 ? items : items.slice(0, 4);
  const bottom = primary.map(n => `<a href="#/${n.id}" data-tab="${n.id}"><span class="pill">${icon(n.id)}</span>${n.short || n.label}</a>`);
  if (items.length > 5) bottom.push(`<a href="#/more" data-tab="more"><span class="pill">${icon("more")}</span>Menyu</a>`);
  document.getElementById("bottom-nav").innerHTML = bottom.join("");
  const nm = ME.employee_name || ME.name || "";
  document.getElementById("who").innerHTML = `<div class="who-text"><b>${esc(nm)}</b>${levelName(ME.level)}</div>${avatar(nm, 34)}`;
  document.getElementById("side-user").innerHTML = `${avatar(nm, 38)}<div style="min-width:0"><b>${esc(nm)}</b><span class="muted">${levelName(ME.level)}</span></div>`;
}
function setActive(tab) {
  const primary = new Set([...document.querySelectorAll("#bottom-nav a")].map(a => a.dataset.tab));
  document.querySelectorAll("#side-nav a, #bottom-nav a").forEach(a => {
    const t = a.dataset.tab;
    a.classList.toggle("active", t === tab || (t === "more" && !primary.has(tab) && tab !== "emp"));
  });
  document.getElementById("page-title").textContent = TITLES[tab] || "Ferma davomati";
}
async function pageMore() {
  const primary = new Set([...document.querySelectorAll("#bottom-nav a")].map(a => a.dataset.tab));
  const rest = allowedNav().filter(n => !primary.has(n.id));
  $app.innerHTML = `<div class="menu-list fade-in">` + rest.map(n =>
    `<a href="#/${n.id}"><span class="mi">${icon(n.id)}</span>${n.label}<span class="chev">${icon("chev")}</span></a>`).join("") + `</div>`;
}

function afterLogin() {
  if (!isViewer() && !ME.employee_no) {
    $app.innerHTML = `<div class="login card"><div class="err">Siz hali tizimga biriktirilmagansiz.<br>Telegram ID: ${esc(ME.uid)}</div>
      <p class="muted">Rahbar sizni biriktirgandan keyin kira olasiz.</p></div>`;
    return;
  }
  document.body.classList.remove("logged-out");
  buildNav();
  window.onhashchange = route;
  route();
}

function renderLogin() {
  document.body.classList.add("logged-out");
  let html = `<div class="login card"><div class="logo">F</div><h2 style="margin:0 0 4px">Ferma davomati</h2>
    <p class="muted" style="margin:0 0 18px">Tizimga kirish</p>
    <form id="pw-form" style="text-align:left">
      <div class="field"><label>Login</label><input id="pw-login" autocomplete="username" autocapitalize="none" required></div>
      <div class="field"><label>Parol</label><input id="pw-pass" type="password" autocomplete="current-password" required></div>
      <button class="btn big">Kirish</button>
    </form>
    <p class="muted" style="font-size:13px">Login va parol sizni biriktirishganda bot orqali yuborilgan.</p>`;
  if (CFG && CFG.bot_username) html += `<p class="muted">yoki</p><div id="tg-login"></div>`;
  if (CFG && CFG.dev_login) html += `<hr><p class="muted">Lokal test (DEV_LOGIN)</p>
    <div class="filters" style="justify-content:center"><input id="dev-uid" placeholder="Telegram ID" inputmode="numeric">
    <button class="btn" id="dev-go">Kirish</button></div>`;
  html += `<div id="login-err"></div></div>`;
  $app.innerHTML = html;
  document.getElementById("pw-form").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const r = await api("/auth/password", {method: "POST", noAuthRedirect: true, json: {
        login: document.getElementById("pw-login").value.trim(), password: document.getElementById("pw-pass").value}});
      TOKEN = r.token; ME = await api("/me"); afterLogin();
    } catch (e) { document.getElementById("login-err").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
  if (CFG && CFG.bot_username) {
    const s = document.createElement("script");
    s.src = "https://telegram.org/js/telegram-widget.js?22";
    s.async = true;
    s.setAttribute("data-telegram-login", CFG.bot_username);
    s.setAttribute("data-size", "large");
    s.setAttribute("data-request-access", "write");
    s.setAttribute("data-onauth", "onTelegramAuth(user)");
    document.getElementById("tg-login").appendChild(s);
  }
  const b = document.getElementById("dev-go");
  if (b) b.onclick = async () => {
    try { const r = await api("/auth/dev?uid=" + encodeURIComponent(document.getElementById("dev-uid").value), {noAuthRedirect: true});
      TOKEN = r.token; ME = await api("/me"); afterLogin();
    } catch (e) { document.getElementById("login-err").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
}
window.onTelegramAuth = async (user) => {
  try {
    const r = await api("/auth/widget", {method: "POST", json: user, noAuthRedirect: true});
    TOKEN = r.token; ME = await api("/me"); afterLogin();
  } catch (e) { document.getElementById("login-err").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
};

// ------------------------------ routing ------------------------------
function parseHash() {
  const h = location.hash.replace(/^#\/?/, "") || homeTab();
  const [path, q] = h.split("?");
  return {parts: path.split("/"), params: Object.fromEntries(new URLSearchParams(q || ""))};
}
function go(path, params) { location.hash = "#/" + path + qs(params || {}); }

async function route(silent) {
  // silent=true — orqa fonda yangilash: yuklanish ko'rinishi yo'q, sahifa joyida qoladi.
  silent = silent === true;
  ROUTE_SEQ++;
  const {parts, params} = parseHash();
  const tab = parts[0];
  setActive(tab);
  if (!silent) window.scrollTo(0, 0);
  if (tg) {
    if (parts[0] === "emp") { tg.BackButton.show(); tg.BackButton.onClick(() => history.back()); } else tg.BackButton.hide();
  }
  if (!silent) $app.innerHTML = `<div class="stats">${'<div class="skel" style="height:112px"></div>'.repeat(4)}</div>` +
    '<div class="skel" style="height:74px;margin-bottom:8px"></div>'.repeat(4);
  try {
    if (parts[0] === "profile") await pageProfile();
    else if (parts[0] === "more") await pageMore();
    else if (parts[0] === "my" && ME.employee_no) await pageEmployee(null, params);
    else if (!isViewer()) go(homeTab());
    else if (parts[0] === "now") await pageNow();
    else if (parts[0] === "day") await pageDay(params);
    else if (parts[0] === "emp") await pageEmployee(decodeURIComponent(parts[1] || ""), params);
    else if (parts[0] === "guards") await pageGuards(params);
    else if (parts[0] === "period") await pagePeriod(params);
    else if (parts[0] === "checkins") await pageCheckins(params);
    else if (parts[0] === "admin" && isAdmin()) await pageAdmin(parts[1] || "employees");
    else go(homeTab());
  } catch (e) {
    // Orqa fondagi yangilash xatosi sahifani buzmasin — eski ma'lumot ko'rinib turaveradi.
    if (!silent && e.message !== "Avtorizatsiya kerak" && e.message !== STALE) {
      // Xato bo'lsa ham foydalanuvchi qamalib qolmasin — sahifani standart sanalar bilan ochish tugmasi.
      $app.innerHTML = `<div class="err">${esc(e.message)}</div>
        <button class="btn ghost" id="reset-page">↺ Standart sanalar bilan ochish</button>`;
      document.getElementById("reset-page").onclick = () => { location.hash = location.hash.split("?")[0]; };
    }
  }
}

// Sana oralig'ini serverga yuborishdan oldin tekshirish: xato bo'lsa sahifa almashmaydi,
// sana maydonlari joyida qoladi va xabar ularning tagida chiqadi.
const MAX_RANGE_DAYS = 366;
function rangeGo(path, extra) {
  const from = document.getElementById("from").value, to = document.getElementById("to").value;
  let msg = "";
  if (!from || !to) msg = "Ikkala sanani tanlang.";
  else if (from > to) msg = "Boshlanish sanasi tugash sanasidan keyin bo'lishi mumkin emas.";
  else if ((new Date(to) - new Date(from)) / 86400000 >= MAX_RANGE_DAYS) msg = `Oraliq ${MAX_RANGE_DAYS} kundan (1 yil) oshmasin.`;
  let box = document.getElementById("range-err");
  if (!box) {
    box = document.createElement("div"); box.id = "range-err";
    document.getElementById("from").closest(".filters").after(box);
  }
  box.innerHTML = msg ? `<div class="err">${msg}</div>` : "";
  if (!msg) go(path, Object.assign({from, to}, extra || {}));
}

// ------------------------------ Hozir ------------------------------
let NOW_TIMER = null;
function ago(sec) {
  if (sec < 60) return "hozirgina";
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m} daq oldin`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h} soat ${m % 60} daq oldin` : `${Math.floor(h / 24)} kun oldin`;
}
const NOW_GROUPS = [
  ["inside", "Fermada", "st-yopildi", "Oxirgi belgi — kirish", "ok", "🟢"],
  ["outside_work", "Tashqarida ishlamoqda", "st-jarayonda", "Telegram orqali hududdan tashqarida ishni boshlagan", "open", "📍"],
  ["left", "Chiqib ketgan", "st-tolik-emas", "Bugun kelgan, oxirgi belgi — chiqish", "bad", "🔴"],
  ["absent", "Bugun kelmagan", "st-gray", "So'nggi 14 kunda kelgan, bugun belgi yo'q", "gray", "⚪"],
];
// Tanlangan filtr avtomatik yangilanishda ham saqlanib qoladi (null = hammasi).
let NOW_FILTER = null;
const NOW_ICONS = {inside: "check", outside_work: "checkins", left: "logout", absent: "clock"};

function nowGroupsHtml(d) {
  let html = "";
  for (const [k, title, cls, hint, , ic] of NOW_GROUPS) {
    if (NOW_FILTER && NOW_FILTER !== k) continue;
    const rows = d.groups[k];
    html += `<div class="section-title" id="g-${k}">${ic} ${title} <span class="muted">${rows.length} kishi · ${hint}</span></div><div class="list">`
      + (rows.length ? rows.map(r => `<div class="row" data-emp="${esc(r.employee_no)}">
          ${avatar(r.name)}
          <div class="main"><div class="name">${esc(r.name)}</div>
            <div class="sub">${esc(r.role_name)}${r.first_today ? " · keldi " + r.first_today.slice(11, 16) : ""}</div></div>
          <div class="right"><span class="st ${cls}">${r.last_direction === "in" ? "kirdi" : "chiqdi"} ${r.last_ts.slice(11, 16)} ${r.last_source === "telegram" ? "📱" : ""}</span>
            <span class="sub">${ago(r.since_sec)}</span></div>
        </div>`).join("") : `<div class="card empty" style="padding:14px">Hech kim yo'q</div>`) + `</div>`;
  }
  return html;
}

async function pageNow() {
  const d = await api("/now");
  const tiles = NOW_GROUPS.map(([k, t, , , tone]) =>
    `<button type="button" class="stat tone-${tone}${NOW_FILTER === k ? " selected" : ""}" data-filter="${k}" aria-pressed="${NOW_FILTER === k}">
      <div class="ic">${icon(NOW_ICONS[k], 18)}</div><div class="n">${d.counts[k]}</div><div class="l">${t}</div></button>`).join("");
  let html = `<div class="page-head"><div class="muted">${niceDate(d.now)}, ${d.now.slice(11, 16)} holatiga · har daqiqada yangilanadi</div>
      <button class="btn ghost" id="refresh">↻ Yangilash</button></div>
    <div class="stats">${tiles}</div>
    <div id="filter-bar"></div>
    <div id="now-groups">${nowGroupsHtml(d)}</div>
    <p class="muted" style="font-size:12px;margin-top:16px">Eslatma: kirish kamerasi ba'zan odamni qayd etmaydi —
    "chiqib ketgan" ro'yxatidagi odam qaytib kirgan, lekin kamerada ko'rinmagan bo'lishi mumkin.</p>`;
  $app.innerHTML = html;

  const bindRows = () => document.querySelectorAll(".row[data-emp]").forEach(el =>
    el.onclick = () => go("emp/" + encodeURIComponent(el.dataset.emp), {from: addDays(todayTashkent(), -6), to: todayTashkent()}));
  const paint = () => {
    document.querySelectorAll(".stat[data-filter]").forEach(b => {
      const on = b.dataset.filter === NOW_FILTER;
      b.classList.toggle("selected", on); b.setAttribute("aria-pressed", on);
    });
    const g = NOW_GROUPS.find(x => x[0] === NOW_FILTER);
    document.getElementById("filter-bar").innerHTML = g ? `<div class="filter-chip">Filtr: <b>${g[1]}</b>
      <button type="button" id="clear-filter" aria-label="Filtrni olib tashlash">✕</button></div>` : "";
    const c = document.getElementById("clear-filter");
    if (c) c.onclick = () => { NOW_FILTER = null; paint(); };
    document.getElementById("now-groups").innerHTML = nowGroupsHtml(d);
    bindRows();
  };
  // Bir marta bosish — filtr; yana bosish — olib tashlash; boshqasini bosish — o'shanga o'tish.
  document.querySelectorAll(".stat[data-filter]").forEach(b => b.onclick = () => {
    NOW_FILTER = NOW_FILTER === b.dataset.filter ? null : b.dataset.filter;
    paint();
  });
  paint();
  document.getElementById("refresh").onclick = () => route();
  clearTimeout(NOW_TIMER);
  const seq = ROUTE_SEQ;
  NOW_TIMER = setTimeout(async () => {
    if (seq !== ROUTE_SEQ || parseHash().parts[0] !== "now" || document.hidden) return;
    const y = window.scrollY;
    await route(true);
    window.scrollTo(0, y);
  }, 60000);
}

// ------------------------------ Kunlik ------------------------------
async function pageDay(p) {
  const date = p.date || todayTashkent();
  const d = await api("/day" + qs({date, role: p.role}));
  const s = d.summary.by_status;
  const roleOpts = `<option value="">Barcha rollar</option>` + Object.entries(d.roles)
    .map(([c, n]) => `<option value="${esc(c)}" ${p.role === c ? "selected" : ""}>${esc(n)}</option>`).join("");
  let html = `<div class="filters">
      <button class="btn ghost" id="prev">‹</button>
      <input type="date" id="date" value="${esc(date)}">
      <button class="btn ghost" id="next">›</button>
      <select id="role">${roleOpts}</select>
    </div>
    <div class="stats">
      ${tile(d.summary.people, "kishi", "accent", null, "users")}
      ${tile(s["yopildi"] || 0, "yopildi", "ok", null, "check")}
      ${tile(s["jarayonda"] || 0, "jarayonda", "open", null, "clock")}
      ${tile(s["to'liq emas"] || 0, "to'liq emas", "bad", null, "alert")}
    </div>`;
  if (!d.rows.length) html += `<div class="empty">${niceDate(date)} uchun ma'lumot yo'q</div>`;
  html += `<div class="list">` + d.rows.map(r => `
    <div class="row" data-emp="${esc(r.employee_no)}">
      ${avatar(r.name)}
      <div class="main"><div class="name">${esc(r.name)}</div>
        <div class="sub">${esc(r.role_name)} ${esc(shiftLabel(r.shift_type))} ${r.sources.includes("telegram") ? "· 📱" : ""}</div>
        <div class="times">${hmRel(r.kirish, r.work_date)} → ${hmRel(r.chiqish, r.work_date)}</div></div>
      <div class="right">${status(r.status)}<div class="hours">${dur(r.inside_sec)}<small>fermada</small></div>
        <div class="sub">ish ${dur(r.span_sec)}</div></div>
      ${(r.flags.length || r.merged_count) ? `<div class="flags">${chips(r.flags)}${r.merged_count ? `<span class="chip">${r.merged_count} dublikat</span>` : ""}</div>` : ""}
    </div>`).join("") + `</div>`;
  $app.innerHTML = html;
  const upd = (patch) => go("day", Object.assign({date, role: p.role}, patch));
  document.getElementById("date").onchange = e => upd({date: e.target.value});
  document.getElementById("prev").onclick = () => upd({date: addDays(date, -1)});
  document.getElementById("next").onclick = () => upd({date: addDays(date, 1)});
  document.getElementById("role").onchange = e => upd({role: e.target.value});
  document.querySelectorAll(".row[data-emp]").forEach(el =>
    el.onclick = () => go("emp/" + encodeURIComponent(el.dataset.emp), {from: addDays(date, -6), to: date}));
}

// ------------------------------ Xodim kartochkasi ------------------------------
function timelineHtml(tl) {
  let out = "", prev = null;
  for (const e of tl) {
    if (!e.merged && prev && prev.direction === "out" && e.direction === "in") {
      const gap = (new Date(e.ts.replace(" ", "T")) - new Date(prev.ts.replace(" ", "T"))) / 1000;
      out += `<li class="gap">tashqarida ${dur(gap)}</li>`;
    }
    const icon = e.source === "telegram" ? "📱" : "📷";
    const lbl = e.direction === "in" ? "Kirish" : "Chiqish";
    out += `<li class="${e.merged ? "merged" : e.direction}">${e.ts.slice(11, 19)} ${icon} ${lbl}${e.merged ? " — dublikat" : ""}${e.outside ? " 📍 hududdan tashqarida" : ""}</li>`;
    if (!e.merged) prev = e;
  }
  return `<ul class="timeline">${out}</ul>`;
}

async function pageEmployee(no, p) {
  const to = p.to || todayTashkent(), from = p.from || addDays(to, -6);
  const mine = no === null;
  const d = await api((mine ? "/my" : `/employee/${encodeURIComponent(no)}`) + qs({from, to}));
  const e = d.employee;
  let html = mine ? `<div class="grid2" style="margin-bottom:12px">
      <a class="btn big" href="/davomat/checkin?dir=in">▶️ Ishni boshladim</a>
      <a class="btn big ghost" href="/davomat/checkin?dir=out">⏹ Ishni tugatdim</a></div>` : "";
  html += `<div class="card" style="display:flex;gap:14px;align-items:center">
      ${avatar(e.name, 56)}
      <div style="min-width:0"><h2 style="margin:0;font-size:19px">${esc(e.name)}</h2>
      <div class="muted">${esc(e.role_name || "")} · ID ${esc(e.employee_no)}${e.aliases.length ? " · birlashtirilgan: " + e.aliases.map(esc).join(", ") : ""}</div></div></div>
      <div class="stats">
        ${tile(d.totals.days, "kun / smena", "accent", null, "day")}
        ${tile(dur(d.totals.span_sec), "ish soati", "open", null, "clock")}
        ${tile(dur(d.totals.inside_sec), "fermada", "ok", null, "check")}
        ${tile(d.totals.incomplete, "to'liq emas", "bad", null, "alert")}
      </div>
    <div class="filters"><input type="date" id="from" value="${from}"> — <input type="date" id="to" value="${to}"></div>`;
  if (!d.shifts.length) html += `<div class="empty">Bu davrda belgi yo'q</div>`;
  d.shifts.slice().reverse().forEach((s, i) => {
    const start = (s.timeline.find(t => !t.merged) || {}).ts;
    html += `<div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <strong style="font-size:16px">${niceDate(s.work_date)} <span class="muted" style="font-weight:500">${esc(shiftLabel(s.shift_type))}</span></strong>${status(s.status)}</div>
      <div class="grid2" style="margin-top:10px">
        <div><div class="muted" style="font-size:12px">Kirish → Chiqish</div><div class="hours" style="font-size:15px">${hmRel(s.kirish, s.work_date)} → ${hmRel(s.chiqish, s.work_date)}</div></div>
        <div style="text-align:right"><div class="muted" style="font-size:12px">Ish soati / Fermada</div><div class="hours" style="font-size:15px">${dur(s.span_sec)} / ${dur(s.inside_sec)}</div></div>
      </div>
      ${s.flags.length ? `<div class="flags" style="margin-top:6px">${chips(s.flags)}</div>` : ""}
      ${timelineHtml(s.timeline)}
      ${isAdmin() && s.shift_type === "noma'lum" && start ? `<div class="filters" style="margin-top:8px">
          <span class="muted">Smena turi:</span>
          <button class="btn ghost" data-resolve="kunduzgi" data-start="${esc(start)}">☀️ Kunduzgi</button>
          <button class="btn ghost" data-resolve="tungi" data-start="${esc(start)}">🌙 Tungi</button></div>` : ""}
      ${isAdmin() ? `<details style="margin-top:8px"><summary class="muted">✏️ Qo'lda tuzatish</summary>
          <div class="grid2" style="margin-top:8px">
            <div class="field"><label>Maydon</label><select id="cf-field-${i}"><option value="kirish">Kirish</option><option value="chiqish">Chiqish</option></select></div>
            <div class="field"><label>Vaqt</label><input type="datetime-local" id="cf-value-${i}" value="${(s.chiqish || s.kirish || s.work_date + " 08:00").slice(0, 16).replace(" ", "T")}"></div>
          </div>
          <div class="field"><label>Sabab (majburiy)</label><input id="cf-note-${i}" placeholder="masalan: kamera ishlamagan"></div>
          <button class="btn" data-correct="${i}" data-date="${esc(s.work_date)}">Saqlash</button>
        </details>` : ""}
    </div>`;
  });
  $app.innerHTML = html;
  const upd = () => rangeGo(mine ? "my" : "emp/" + encodeURIComponent(no));
  document.getElementById("from").onchange = upd;
  document.getElementById("to").onchange = upd;
  document.querySelectorAll("[data-resolve]").forEach(b => b.onclick = async () => {
    try { await api("/admin/resolutions", {method: "POST", json: {employee_no: e.employee_no, shift_start: b.dataset.start, shift_type: b.dataset.resolve}}); route(); }
    catch (err) { alertMsg(err.message); }
  });
  document.querySelectorAll("[data-correct]").forEach(b => b.onclick = async () => {
    const i = b.dataset.correct;
    try {
      await api("/admin/corrections", {method: "POST", json: {
        employee_no: e.employee_no, work_date: b.dataset.date,
        field: document.getElementById("cf-field-" + i).value,
        value: document.getElementById("cf-value-" + i).value.replace("T", " "),
        note: document.getElementById("cf-note-" + i).value}});
      route();
    } catch (err) { alertMsg(err.message); }
  });
}

// ------------------------------ Qorovullar ------------------------------
async function pageGuards(p) {
  const to = p.to || todayTashkent(), from = p.from || addDays(to, -6);
  const d = await api("/guards" + qs({from, to}));
  let html = `<div class="filters"><input type="date" id="from" value="${from}"> — <input type="date" id="to" value="${to}"></div>`;
  if (!d.guards_count) html += `<div class="err">Qorovul roli hech kimga biriktirilmagan (Admin → Xodimlar).</div>`;
  if (d.empty.length) html += `<div class="card"><strong>⚠️ Bo'sh qolgan smenalar (${d.empty.length})</strong><div class="flags" style="margin-top:6px">`
    + d.empty.map(x => `<span class="chip">${niceDate(x.date)} ${esc(shiftLabel(x.shift_type))}</span>`).join("") + `</div></div>`;
  html += `<div class="list">` + d.rows.slice().reverse().map(r => `
    <div class="row" data-emp="${esc(r.employee_no)}">
      ${avatar(r.name)}
      <div class="main"><div class="name">${esc(r.name)}</div><div class="sub">${niceDate(r.work_date)} · ${esc(shiftLabel(r.shift_type))}</div>
        <div class="times">${hmRel(r.kirish, r.work_date)} → ${hmRel(r.chiqish, r.work_date)}</div></div>
      <div class="right">${status(r.status)}<div class="hours">${dur(r.span_sec)}</div><div class="sub">fermada ${dur(r.inside_sec)}</div></div>
    </div>`).join("") + `</div>`;
  if (!d.rows.length) html += `<div class="empty">Qorovul smenalari yo'q</div>`;
  $app.innerHTML = html;
  const upd = () => rangeGo("guards");
  document.getElementById("from").onchange = upd;
  document.getElementById("to").onchange = upd;
  document.querySelectorAll(".row[data-emp]").forEach(el => el.onclick = () => go("emp/" + encodeURIComponent(el.dataset.emp), {from, to}));
}

// ------------------------------ Davr ------------------------------
async function pagePeriod(p) {
  const to = p.to || todayTashkent(), from = p.from || (to.slice(0, 8) + "01");
  const d = await api("/period" + qs({from, to, role: p.role}));
  const tot = d.rows.reduce((a, r) => (a.s += r.span_sec, a.i += r.inside_sec, a), {s: 0, i: 0});
  let html = `<div class="filters"><input type="date" id="from" value="${from}"> — <input type="date" id="to" value="${to}">
      <button class="btn" id="xlsx">⬇ Excel</button></div>
    <div class="stats">${tile(d.rows.length, "xodim", "accent", null, "users")}${tile(dur(tot.s), "jami ish soati", "open", null, "clock")}${tile(dur(tot.i), "jami fermada", "ok", null, "check")}</div>
    <div class="card scroll-x"><table class="t"><thead><tr><th>F.I.O.</th><th>Rol</th><th class="num">Kun</th>
      <th class="num">To'liq emas</th><th class="num">Ish soati</th><th class="num">Fermada</th></tr></thead><tbody>`
    + d.rows.map(r => `<tr data-emp="${esc(r.employee_no)}" style="cursor:pointer"><td>${esc(r.name)}</td><td>${esc(r.role_name)}</td>
      <td class="num">${r.days}</td><td class="num">${r.incomplete || ""}</td><td class="num">${dur(r.span_sec)}</td>
      <td class="num"><b>${dur(r.inside_sec)}</b></td></tr>`).join("")
    + `</tbody></table></div>`;
  $app.innerHTML = html;
  const upd = () => rangeGo("period", {role: p.role});
  document.getElementById("from").onchange = upd;
  document.getElementById("to").onchange = upd;
  document.getElementById("xlsx").onclick = () => download("/period.xlsx" + qs({from, to, role: p.role}), `davomat_${from}_${to}.xlsx`);
  document.querySelectorAll("tr[data-emp]").forEach(el => el.onclick = () => go("emp/" + encodeURIComponent(el.dataset.emp), {from, to}));
}

// ------------------------------ Check-in ------------------------------
async function loadPhoto(img) {
  try { const b = await api(`/checkins/${img.dataset.photo}/photo`); img.src = URL.createObjectURL(b); } catch { img.alt = "rasm yo'q"; }
}
async function pageCheckins(p) {
  const to = p.to || todayTashkent(), from = p.from || to;
  const d = await api("/checkins" + qs({from, to}));
  let html = `<div class="filters"><input type="date" id="from" value="${from}"> — <input type="date" id="to" value="${to}">
    <button class="btn" id="xlsx">⬇ Excel</button></div>`;
  if (!d.rows.length) html += `<div class="empty">Telegram orqali belgilash yo'q</div>`;
  html += `<div class="list">` + d.rows.map(r => `
    <div class="card" style="display:flex;gap:10px;align-items:flex-start">
      <img data-photo="${r.id}" alt="" style="width:72px;height:72px;object-fit:cover;border-radius:10px;background:var(--bg);flex:none">
      <div style="flex:1;min-width:0">
        <div class="brand"><strong>${esc(r.name)}</strong><span class="muted">${niceDate(r.ts)} ${r.ts.slice(11, 16)}</span></div>
        <div>${r.direction === "in" ? "▶️ Ishni boshladi" : "⏹ Ishni tugatdi"}</div>
        <div class="flags" style="margin-top:4px">
          ${r.outside ? `<span class="st st-tolik-emas">📍 hududdan tashqarida${r.distance_m != null ? " · " + (r.distance_m / 1000).toFixed(1) + " km" : ""}</span>`
                      : (r.distance_m != null ? `<span class="st st-yopildi">🏠 ferma hududida</span>` : `<span class="chip">hudud sozlanmagan</span>`)}
          <span class="chip">aniqlik ±${Math.round(r.accuracy || 0)} m</span>
          <a class="chip" href="https://maps.google.com/?q=${r.lat},${r.lon}" target="_blank" rel="noopener">xarita</a>
        </div></div></div>`).join("") + `</div>`;
  $app.innerHTML = html;
  document.querySelectorAll("img[data-photo]").forEach(loadPhoto);
  const upd = () => rangeGo("checkins");
  document.getElementById("from").onchange = upd;
  document.getElementById("to").onchange = upd;
  document.getElementById("xlsx").onclick = () => download("/checkins.xlsx" + qs({from, to}), `checkin_${from}_${to}.xlsx`);
}

// ------------------------------ Profil ------------------------------
async function pageProfile() {
  const c = await api("/auth/credentials");
  $app.innerHTML = `<div class="card">
      <strong>${esc(ME.employee_name || ME.name || "")}</strong>
      <div class="muted">Telegram ID: ${esc(ME.uid)} · ${levelName(ME.level)}</div></div>
    <div class="card"><strong>Web uchun login va parol</strong>
      ${c.login ? `<p class="muted">Joriy login: <b>${esc(c.login)}</b></p>
      <div class="field"><label>Joriy parol</label><input id="cur" type="password" autocomplete="current-password"></div>
      <div class="field"><label>Yangi login (ixtiyoriy)</label><input id="nl" autocapitalize="none" placeholder="${esc(c.login)}"></div>
      <div class="field"><label>Yangi parol (ixtiyoriy, kamida 8 belgi, harf va raqam)</label><input id="np" type="password" autocomplete="new-password"></div>
      <button class="btn" id="save">Saqlash</button><div id="pmsg" style="margin-top:10px"></div>`
      : `<p class="muted">Sizga hali login berilmagan.</p>`}</div>
    ${tg ? "" : `<button class="btn ghost" id="logout">Chiqish</button>`}`;
  const b = document.getElementById("save");
  if (b) b.onclick = async () => {
    try {
      const r = await api("/auth/change-credentials", {method: "POST", json: {current_password: document.getElementById("cur").value,
        new_login: document.getElementById("nl").value.trim() || null, new_password: document.getElementById("np").value || null}});
      document.getElementById("pmsg").innerHTML = `<div class="ok-msg">Saqlandi. Login: <b>${esc(r.login)}</b></div>`;
    } catch (e) { document.getElementById("pmsg").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
  const lo = document.getElementById("logout");
  if (lo) lo.onclick = async () => { await api("/auth/logout", {method: "POST"}); TOKEN = null; ME = null; location.hash = ""; renderLogin(); };
}

// ------------------------------ Admin ------------------------------
const ADMIN_TABS = [["employees", "Xodimlar"], ["requests", "So'rovlar"], ["users", "Foydalanuvchilar"],
                    ["roles", "Rollar"], ["settings", "Sozlamalar"], ["audit", "Audit"]];
const SETTING_LABELS = {
  farm_lat: "Ferma kengligi (lat)", farm_lon: "Ferma uzunligi (lon)", farm_radius_m: "Ferma radiusi (m)",
  max_accuracy_m: "Check-in: GPS aniqligi chegarasi (m)", guard_day_start: "Qorovul kunduzgi smena boshlanishi",
  guard_night_start: "Qorovul tungi smena boshlanishi", guard_grace_min: "Qorovul kelmasa ogohlantirish (daqiqa)",
  daily_summary_time: "Kunlik xulosa vaqti", remind_after_h: "Javob bo'lmasa eslatma (soat)",
  auto_resolve_after_h: "Javob bo'lmasa avtomatik tanlash (soat)",
  link_admin_id: "Yangi foydalanuvchi so'rovlari boradigan Telegram ID (1 kishi)",
};

async function pageAdmin(sub) {
  const tabs = ADMIN_TABS.filter(([k]) => isSuper() || !["roles", "settings", "users"].includes(k));
  if (!tabs.some(([k]) => k === sub)) sub = "employees";
  let html = `<div class="subtabs">` + tabs.map(([k, n]) => `<a href="#/admin/${k}" class="${k === sub ? "active" : ""}">${n}</a>`).join("") + `</div><div id="admin-body"></div>`;
  $app.innerHTML = html;
  const body = document.getElementById("admin-body");
  const fn = {employees: adminEmployees, requests: adminRequests, users: adminUsers, roles: adminRoles, settings: adminSettings, audit: adminAudit}[sub];
  if (fn) await fn(body);
}

async function adminEmployees(el) {
  const [list, roles] = await Promise.all([api("/admin/employees"), api("/admin/roles")]);
  const roleName = Object.fromEntries(roles.map(r => [r.code, r.name]));
  el.innerHTML = `<div class="filters"><input id="q" placeholder="Qidirish..."></div><div class="list" id="emps"></div>`;
  const draw = (q) => {
    document.getElementById("emps").innerHTML = list.filter(e => !q || e.full_name.toLowerCase().includes(q) || e.employee_no.includes(q)).map(e => `
      <details class="card"><summary><strong>${esc(e.full_name)}</strong> <span class="muted">· ${esc(e.employee_no)} · ${esc(roleName[e.role] || e.role)}${e.role_auto ? " (avto)" : ""}
        ${e.merged_into ? "· → " + esc(e.merged_into) : ""}${e.active ? "" : " · nofaol"}${e.telegram_user_id ? " · 📱" : ""}</span></summary>
        <div class="grid2" style="margin-top:10px">
          <div class="field"><label>Ish roli</label><select data-f="role"><option value="avto" ${e.role_auto ? "selected" : ""}>🤖 Avtomatik (tizim aniqlaydi)</option>${roles.map(r => `<option value="${esc(r.code)}" ${r.code === e.role && !e.role_auto ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select></div>
          <div class="field"><label>Qaysi sanadan</label><input type="date" data-f="valid_from" value="${todayTashkent()}"></div>
        </div>
        <button class="btn" data-act="role" data-no="${esc(e.employee_no)}">Rolni saqlash</button>
        <div class="muted" style="margin:8px 0">Rollar tarixi: ${e.roles.length ? e.roles.map(r => `${esc(roleName[r.role] || r.role)} (${r.from} → ${r.to || "hozir"})`).join("; ") : (e.role_auto ? "qo'lda berilmagan — smena naqshidan avtomatik qorovul deb aniqlandi" : "standart")}</div>
        <div class="grid2">
          <div class="field"><label>F.I.O.</label><input data-f="full_name" value="${esc(e.full_name)}"></div>
          <div class="field"><label>Telegram ID (check-in uchun)</label><input data-f="telegram_user_id" inputmode="numeric" value="${esc(e.telegram_user_id || "")}"></div>
          <div class="field"><label>Boshqa ID bilan birlashtirish (asosiy ID)</label><input data-f="merged_into" value="${esc(e.merged_into || "")}" placeholder="masalan 00000002"></div>
          <div class="field"><label>Holat</label><select data-f="active"><option value="1" ${e.active ? "selected" : ""}>Faol</option><option value="0" ${e.active ? "" : "selected"}>Nofaol</option></select></div>
        </div>
        <button class="btn" data-act="save" data-no="${esc(e.employee_no)}">Saqlash</button>
        ${e.telegram_user_id ? `<button class="btn ghost" data-act="reset" data-uid="${e.telegram_user_id}">🔑 Yangi parol yuborish</button>` : ""}
      </details>`).join("");
    document.querySelectorAll("#emps [data-act]").forEach(b => b.onclick = async () => {
      const card = b.closest("details"), f = n => card.querySelector(`[data-f="${n}"]`).value.trim();
      try {
        if (b.dataset.act === "reset") { await api(`/admin/users/${b.dataset.uid}/reset-password`, {method: "POST"}); alertMsg("Yuborildi"); return; }
        if (b.dataset.act === "role") await api(`/admin/employees/${encodeURIComponent(b.dataset.no)}/role`, {method: "POST", json: {role: f("role"), valid_from: f("valid_from")}});
        else await api(`/admin/employees/${encodeURIComponent(b.dataset.no)}`, {method: "POST", json: {
          full_name: f("full_name"), active: f("active") === "1",
          telegram_user_id: f("telegram_user_id") ? Number(f("telegram_user_id")) : null, clear_telegram: !f("telegram_user_id"),
          merged_into: f("merged_into") || null, clear_merge: !f("merged_into")}});
        alertMsg("Saqlandi"); route();
      } catch (err) { alertMsg(err.message); }
    });
  };
  draw("");
  document.getElementById("q").oninput = e => draw(e.target.value.toLowerCase());
}

async function adminRequests(el) {
  const [reqs, emps] = await Promise.all([api("/admin/link-requests"), api("/admin/employees")]);
  const opts = emps.filter(e => e.active && !e.merged_into).map(e => `<option value="${esc(e.employee_no)}">${esc(e.full_name)}</option>`).join("");
  el.innerHTML = reqs.length ? reqs.map(r => `<div class="card">
      <strong>${esc(r.full_name || "")}</strong> <span class="muted">${r.username ? "@" + esc(r.username) : ""} · ID ${r.telegram_user_id}</span>
      <div class="filters" style="margin-top:8px"><select data-uid="${r.telegram_user_id}">${opts}</select>
        <button class="btn" data-link="${r.telegram_user_id}">Biriktirish</button>
        <button class="btn ghost" data-reject="${r.telegram_user_id}">Rad etish</button></div></div>`).join("")
    : `<div class="empty">Yangi so'rov yo'q. Xodim botga /start yozsa, so'rov shu yerda chiqadi.</div>`;
  el.querySelectorAll("[data-link]").forEach(b => b.onclick = async () => {
    const no = el.querySelector(`select[data-uid="${b.dataset.link}"]`).value;
    try { await api(`/admin/employees/${encodeURIComponent(no)}`, {method: "POST", json: {telegram_user_id: Number(b.dataset.link)}}); route(); }
    catch (err) { alertMsg(err.message); }
  });
  el.querySelectorAll("[data-reject]").forEach(b => b.onclick = async () => {
    try { await api(`/admin/link-requests/${b.dataset.reject}/reject`, {method: "POST"}); route(); } catch (err) { alertMsg(err.message); }
  });
}

async function adminUsers(el) {
  const users = await api("/admin/users");
  el.innerHTML = `<div class="card"><strong>Admin berish</strong>
      <p class="muted" style="margin:4px 0 0">Admin barcha xodimlarning keldi-ketdisini ko'radi va tuzatadi. Admin bo'lmaganlar faqat o'zini ko'radi.</p>
      <div class="grid2" style="margin-top:8px">
        <div class="field"><label>Telegram ID</label><input id="u-id" inputmode="numeric"></div>
        <div class="field"><label>Ism</label><input id="u-name"></div>
        <input type="hidden" id="u-level" value="admin">
        <div class="field"><label>Istisno xabarlarini oladi</label><select id="u-resp"><option value="0">Yo'q</option><option value="1">Ha</option></select></div>
      </div><button class="btn" id="u-save">Saqlash</button>
      <p class="muted">Telegram ID ni bilish: foydalanuvchi botga /start yozadi — bot ID ni ko'rsatadi.<br>
      👑 Super admin bitta — u .env dagi SUPERADMIN_TELEGRAM_ID orqali belgilanadi.</p></div>
    <div class="card scroll-x"><table class="t"><thead><tr><th>Ism</th><th>ID</th><th>Login</th><th>Daraja</th><th>Xabarlar</th><th></th></tr></thead><tbody>`
    + users.map(u => `<tr><td>${esc(u.name)}</td><td>${u.telegram_user_id}</td><td>${esc(u.login || "—")}</td><td>${levelName(u.level)}</td><td>${u.is_responsible ? "✅" : ""}</td>
        <td style="white-space:nowrap">${canManage(u.level) ? `<button class="btn ghost" data-edit='${esc(JSON.stringify(u))}' title="Tahrirlash">✏️</button>` : ""}
          ${canManage(u.level) || u.telegram_user_id === ME.uid ? `<button class="btn ghost" data-reset="${u.telegram_user_id}" title="Yangi parol yuborish">🔑</button>` : ""}
          ${canManage(u.level) ? `<button class="btn danger" data-del="${u.telegram_user_id}" title="O'chirish">✕</button>` : ""}</td></tr>`).join("")
    + `</tbody></table></div>`;
  document.getElementById("u-save").onclick = async () => {
    try { await api("/admin/users", {method: "POST", json: {telegram_user_id: Number(document.getElementById("u-id").value),
      name: document.getElementById("u-name").value, level: document.getElementById("u-level").value,
      is_responsible: document.getElementById("u-resp").value === "1"}}); route(); } catch (err) { alertMsg(err.message); }
  };
  el.querySelectorAll("[data-edit]").forEach(b => b.onclick = () => {
    const u = JSON.parse(b.dataset.edit);
    document.getElementById("u-id").value = u.telegram_user_id; document.getElementById("u-name").value = u.name || "";
    document.getElementById("u-resp").value = u.is_responsible ? "1" : "0";
    window.scrollTo(0, 0);
  });
  el.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    try { await api(`/admin/users/${b.dataset.del}`, {method: "DELETE"}); route(); } catch (err) { alertMsg(err.message); }
  });
  el.querySelectorAll("[data-reset]").forEach(b => b.onclick = async () => {
    try { await api(`/admin/users/${b.dataset.reset}/reset-password`, {method: "POST"}); alertMsg("Yangi parol Telegram orqali yuborildi"); }
    catch (err) { alertMsg(err.message); }
  });
}

async function adminRoles(el) {
  const roles = await api("/admin/roles");
  el.innerHTML = `<p class="muted">day_boundary — kun chegarasi; debounce_sec — dublikat oynasi; max_shift_hours — smena maksimal davomiyligi;
      mode "shift" — qorovul smenasi; day_window/night_window — smena boshlanish soatlari [dan, gacha).</p>`
    + roles.map(r => `<div class="card"><div class="field"><label>Nomi (${esc(r.code)})</label><input data-name="${esc(r.code)}" value="${esc(r.name)}"></div>
      <div class="field"><label>Parametrlar (JSON)</label><textarea rows="4" data-params="${esc(r.code)}">${esc(JSON.stringify(r.params, null, 1))}</textarea></div>
      <button class="btn" data-save="${esc(r.code)}">Saqlash</button></div>`).join("");
  el.querySelectorAll("[data-save]").forEach(b => b.onclick = async () => {
    const c = b.dataset.save;
    try {
      const params = JSON.parse(el.querySelector(`[data-params="${c}"]`).value);
      await api(`/admin/roles/${encodeURIComponent(c)}`, {method: "PUT", json: {name: el.querySelector(`[data-name="${c}"]`).value, params}});
      alertMsg("Saqlandi");
    } catch (err) { alertMsg(err.message); }
  });
}

async function adminSettings(el) {
  const s = await api("/admin/settings");
  el.innerHTML = `<div class="card">` + Object.keys(SETTING_LABELS).map(k => `<div class="field"><label>${esc(SETTING_LABELS[k])}</label>
      <input data-k="${k}" value="${esc(s[k] ?? "")}"></div>`).join("")
    + `<button class="btn" id="s-save">Saqlash</button>
       <p class="muted">Ferma koordinatasini bilish: Google Maps'da fermani bosib turing — pastda "41.xxxx, 69.xxxx" chiqadi.</p></div>`;
  document.getElementById("s-save").onclick = async () => {
    const body = {};
    el.querySelectorAll("[data-k]").forEach(i => body[i.dataset.k] = i.value);
    try { await api("/admin/settings", {method: "PUT", json: body}); alertMsg("Saqlandi"); } catch (err) { alertMsg(err.message); }
  };
}

async function adminAudit(el) {
  const rows = await api("/admin/audit?limit=200");
  el.innerHTML = `<div class="card scroll-x"><table class="t"><thead><tr><th>Vaqt (UTC)</th><th>Kim</th><th>Amal</th><th>Obyekt</th><th>O'zgarish</th></tr></thead><tbody>`
    + rows.map(r => `<tr><td>${esc((r.created_at || "").slice(0, 16))}</td><td>${esc(r.actor_id ?? "tizim")}</td><td>${esc(r.action)}</td>
      <td>${esc(r.entity)} ${esc(r.entity_id || "")}</td><td class="muted" style="font-size:12px;max-width:340px;word-break:break-word">${esc(r.after || "")}</td></tr>`).join("")
    + `</tbody></table></div>`;
}

boot();
