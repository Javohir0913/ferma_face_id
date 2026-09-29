"use strict";
// Galereyadan yuklash imkoni atayin yo'q: <input type="file"> ishlatilmaydi,
// rasm faqat jonli kamera oqimidan (getUserMedia) olinadi.
const tg = window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData ? window.Telegram.WebApp : null;
const API = "/api/davomat";
const $app = document.getElementById("app");
let TOKEN = null, STATE = null, DIR = null, STREAM = null, PHOTO = null, LOC = null;
let LOC_RUN = 0, CHAT_POLL = null;

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]); }
async function api(path, opts = {}) {
  const headers = {};
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const r = await fetch(API + path, {method: opts.method || "GET", headers, body: opts.body, credentials: "same-origin"});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Xato ${r.status}`);
  return data;
}
function applyTheme() {
  if (!tg) return;
  const p = tg.themeParams || {}, root = document.documentElement;
  root.setAttribute("data-theme", tg.colorScheme === "dark" ? "dark" : "light");
  const map = {"--bg": p.secondary_bg_color, "--card": p.bg_color, "--text": p.text_color, "--muted": p.hint_color,
               "--accent": p.button_color, "--accent-text": p.button_text_color, "--line": p.section_separator_color};
  Object.entries(map).forEach(([k, v]) => { if (v) root.style.setProperty(k, v); });
}
function envInfo() {
  return `${tg ? "tg " + tg.platform + " v" + tg.version : "brauzer"} | ${navigator.userAgent}`;
}
function report(event, detail) {
  api("/client-log", {method: "POST", json: {event, detail: `${detail} | ${envInfo()}`}}).catch(() => {});
}
function fail(msg) { $app.innerHTML = `<div class="card"><div class="err">${esc(msg)}</div></div>`; }
function withTimeout(promise, ms, msg) {
  return Promise.race([promise, new Promise((_, rej) => setTimeout(() => rej(new Error(msg)), ms))]);
}

async function boot() {
  if (tg) {
    document.documentElement.classList.add("in-tg"); tg.ready(); tg.expand(); applyTheme();
    if (tg.BackButton) { tg.BackButton.onClick(goBack); tg.BackButton.show(); }
  }
  try {
    if (tg) TOKEN = (await api("/auth/webapp", {method: "POST", json: {init_data: tg.initData}})).token;
    STATE = await api("/checkin/state");
  } catch (e) {
    return fail(tg ? e.message : "Bu sahifa faqat Telegram bot ichida ochiladi.");
  }
  // Navbat: boshlanmagan ishni tugatib bo'lmaydi, boshlangan ishni qayta boshlab bo'lmaydi.
  DIR = STATE.can_out ? "out" : "in";
  const wanted = new URLSearchParams(location.search).get("dir");
  report("open", `dir=${wanted || "-"} holat=${DIR}`);
  if ((wanted === "in" || wanted === "out") && wanted !== DIR) return renderMismatch(wanted);
  render();
  startFlow();
}

// Ruxsatlar ketma-ket: avval kamera, keyin joylashuv. Android Telegram'da ikki ruxsat
// oynasi bir vaqtda chiqsa, biri yo'qolib, so'rov osilib qoladi.
async function startFlow() {
  await startCamera();
  getLocation();
}

// Noto'g'ri tugma bosilgan (masalan ish boshlangan-u, yana "boshladim"): kamera/joylashuvga
// tegmaymiz — avval aniq tushuntiramiz, foydalanuvchi tasdiqlagandan keyingina ochamiz.
function renderMismatch(wanted) {
  const t = STATE.last ? esc(STATE.last.ts.slice(11, 16)) : "";
  const started = wanted === "in";
  $app.innerHTML = `
    <button class="btn ghost" onclick="goBack()" style="margin-bottom:10px;min-height:36px;padding:6px 14px">‹ Orqaga</button>
    <div class="card" style="text-align:center;padding:28px 20px">
      <div style="font-size:44px;margin-bottom:6px">${started ? "⏳" : "ℹ️"}</div>
      <h2 style="margin:0 0 8px">${started ? "Ish allaqachon boshlangan" : "Ish hali boshlanmagan"}</h2>
      <p class="muted" style="margin:0 0 18px">${started
        ? `Siz bugun ${t} da «Ishni boshladim» ni belgilagansiz. Qayta boshlab bo'lmaydi.`
        : "Tugatish uchun avval «Ishni boshladim» ni belgilash kerak."}</p>
      <button class="btn big" id="go-right">${started ? "⏹ Ishni tugatishga o'tish" : "▶️ Ishni boshlashga o'tish"}</button>
      <button class="btn big ghost" style="margin-top:8px" onclick="goBack()">Bekor qilish</button>
    </div>`;
  document.getElementById("go-right").onclick = () => { render(); startFlow(); };
}

function render() {
  const last = STATE.last ? `Oxirgi belgi: ${STATE.last.direction === "in" ? "ishni boshlagan" : "ishni tugatgan"} — ${esc(STATE.last.ts.slice(0, 16))}` : "Hali belgi yo'q";
  const note = "";
  $app.innerHTML = `
    <button class="btn ghost" onclick="goBack()" style="margin-bottom:10px;min-height:36px;padding:6px 14px">‹ Orqaga</button>
    <div class="card hello"><div class="logo">F</div><div><strong style="font-size:16px">${esc(STATE.employee_name)}</strong><div class="muted" style="font-size:13px">${last}</div></div></div>
    ${note ? `<div class="ok-msg" style="background:var(--warn-bg);color:var(--warn)">${note}</div>` : ""}
    <div class="dir">
      <button class="btn ${DIR === "in" ? "sel" : "ghost"}" data-dir="in" ${STATE.can_in ? "" : "disabled"}>▶️ Ishni boshladim</button>
      <button class="btn ${DIR === "out" ? "sel" : "ghost"}" data-dir="out" ${STATE.can_out ? "" : "disabled"}>⏹ Ishni tugatdim</button>
    </div>
    <div class="cam" id="cam"><video id="video" autoplay playsinline muted></video></div>
    <button class="btn big" id="shot" disabled>📸 Suratga olish</button>
    <div class="card" style="margin-top:12px">
      <div class="step"><span class="dot" id="d-photo">1</span><span id="t-photo">Kamera ishga tushmoqda...</span></div>
      <div class="step"><span class="dot" id="d-loc">2</span><span id="t-loc">Joylashuv aniqlanmoqda...</span></div>
    </div>
    <div id="msg"></div>
    <button class="btn big" id="send" disabled>${DIR === "in" ? "▶️ Ishni boshlash" : "⏹ Ishni tugatish"}</button>`;
  document.getElementById("shot").onclick = () => PHOTO ? retake() : takePhoto();
  document.getElementById("send").onclick = send;
}

function setStep(id, ok, text) {
  const d = document.getElementById("d-" + id);
  if (!d) return;
  d.className = "dot " + (ok === true ? "ok" : ok === false ? "bad" : "");
  d.textContent = ok === true ? "✓" : ok === false ? "!" : (id === "photo" ? "1" : "2");
  document.getElementById("t-" + id).innerHTML = text;
  document.getElementById("send").disabled = !(PHOTO && LOC && LOC.ok);
}

// ------------------------------ kamera ------------------------------
function cameraHelp() {
  const pf = (tg && tg.platform) || (/iphone|ipad/i.test(navigator.userAgent) ? "ios" : /android/i.test(navigator.userAgent) ? "android" : "");
  if (pf === "ios") return "iPhone: <b>Sozlamalar → Telegram → Kamera</b> ni yoqing, keyin shu yerga qaytib «Kamerani qayta yoqish» ni bosing.";
  if (pf === "android") return "Android: <b>Sozlamalar → Ilovalar → Telegram → Ruxsatlar → Kamera → Ruxsat berish</b>, keyin shu yerga qaytib «Kamerani qayta yoqish» ni bosing.";
  return "Brauzer manzil qatoridagi 🔒 belgisini bosib, kameraga ruxsat bering va «Kamerani qayta yoqish» ni bosing.";
}

let CAM_BUSY = false, CAM_FAILS = 0;
function reloadPage() {
  stopCamera();
  const u = new URL(location.href);
  u.searchParams.set("dir", DIR || "in");
  u.searchParams.set("r", Date.now());   // WebView keshsiz qayta yuklasin
  location.replace(u.toString());
}
window.reloadPage = reloadPage;
async function startCamera() {
  if (CAM_BUSY || STREAM) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return setStep("photo", false, "Bu qurilmada kamera ochilmadi. Telegram'ni yangilang.");
  }
  CAM_BUSY = true;
  setStep("photo", null, `<span class="spin"></span> Kamera ishga tushmoqda...`);
  const gum = navigator.mediaDevices.getUserMedia({video: {facingMode: "user", width: {ideal: 960}, height: {ideal: 1280}}, audio: false});
  const attach = (st) => {
    STREAM = st;
    const v = document.getElementById("video");
    if (!v) { st.getTracks().forEach(t => t.stop()); STREAM = null; return; }
    v.srcObject = st;
    document.getElementById("shot").disabled = false;
    setStep("photo", null, "Yuzingiz ramkada ko'rinsin va «Suratga olish» ni bosing");
  };
  try {
    attach(await withTimeout(gum, 15000, "timeout"));
  } catch (e) {
    if (e && e.message === "timeout") {
      gum.then(st => { if (STREAM || PHOTO) st.getTracks().forEach(t => t.stop()); else attach(st); }).catch(() => {});
    }
    STREAM = null;
    CAM_FAILS++;
    report("camera", `${e && e.name}: ${e && e.message} (urinish ${CAM_FAILS})`);
    const why = e && e.message === "timeout" ? "Kamera javob bermadi (ruxsat oynasi yopilib qolgan bo'lishi mumkin)."
      : e && e.name === "NotAllowedError" ? "Kameraga ruxsat berilmadi."
      : e && e.name === "NotReadableError" ? "Kamera boshqa ilova tomonidan band. Uni yoping."
      : e && e.name === "NotFoundError" ? "Kamera topilmadi." : "Kamera ochilmadi.";
    setStep("photo", false, `${why}<div class="muted" style="font-size:12.5px;margin:4px 0 8px">${cameraHelp()}
        ${CAM_FAILS > 1 ? "<br><b>Ruxsat berganingizdan keyin ham ochilmasa — «Sahifani qayta yuklash» ni bosing.</b>" : ""}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn ghost" onclick="startCamera()">📷 Kamerani qayta yoqish</button>
        <button class="btn ghost" onclick="reloadPage()">🔄 Sahifani qayta yuklash</button></div>
      <div class="muted" style="font-size:11px;margin-top:6px">${esc((e && e.name) || "")} · ${esc(tg ? tg.platform + " " + tg.version : "brauzer")}</div>`);
  } finally { CAM_BUSY = false; }
}
window.startCamera = startCamera;

function stopCamera() { if (STREAM) STREAM.getTracks().forEach(t => t.stop()); STREAM = null; }
function goBack() {
  stopCamera(); stopChatPoll();
  location.href = "/davomat/";
}
window.goBack = goBack;

function takePhoto() {
  const v = document.getElementById("video");
  if (!v.videoWidth) return;
  const scale = Math.min(1, 960 / Math.max(v.videoWidth, v.videoHeight));
  const c = document.createElement("canvas");
  c.width = Math.round(v.videoWidth * scale); c.height = Math.round(v.videoHeight * scale);
  const ctx = c.getContext("2d");
  ctx.translate(c.width, 0); ctx.scale(-1, 1);
  ctx.drawImage(v, 0, 0, c.width, c.height);
  c.toBlob(b => {
    PHOTO = b;
    const img = document.createElement("img");
    img.src = URL.createObjectURL(b);
    const cam = document.getElementById("cam");
    cam.querySelector("video").hidden = true;
    cam.appendChild(img);
    cam.classList.add("taken");
    document.getElementById("shot").textContent = "🔄 Qayta olish";
    document.getElementById("shot").className = "btn ghost big";
    setStep("photo", true, "Surat olindi");
    if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");
  }, "image/jpeg", 0.85);
}

function retake() {
  PHOTO = null;
  const cam = document.getElementById("cam");
  cam.querySelectorAll("img").forEach(i => i.remove());
  cam.classList.remove("taken");
  cam.querySelector("video").hidden = false;
  document.getElementById("shot").textContent = "📸 Suratga olish";
  document.getElementById("shot").className = "btn big";
  setStep("photo", null, "Yuzingiz ramkada ko'rinsin va «Suratga olish» ni bosing");
}

// ------------------------------ joylashuv ------------------------------
// 1) Telegram LocationManager (Bot API 8.0+), 2) brauzer geolokatsiyasi,
// 3) bot chatida yuborilgan jonli joylashuv. Har bir bosqich vaqt bilan cheklangan.
function tgLocation() {
  return new Promise((resolve, reject) => {
    const lm = tg && tg.LocationManager;
    if (!lm || !tg.isVersionAtLeast || !tg.isVersionAtLeast("8.0")) return reject(new Error("Telegram joylashuv API'si yo'q"));
    const ask = () => {
      try {
        if (lm.isAccessRequested && !lm.isAccessGranted) return reject(new Error("denied"));
        // isLocationAvailable ilova ochilgandagi holatni eslab qoladi — GPS keyin yoqilsa ham
        // false bo'lib qolishi mumkin, shuning uchun unga qaramay to'g'ridan-to'g'ri so'raymiz.
        lm.getLocation(loc => loc ? resolve({lat: loc.latitude, lon: loc.longitude, accuracy: loc.horizontal_accuracy})
                                  : reject(new Error(lm.isAccessGranted ? "GPS o'chiq" : "denied")));
      } catch (e) { reject(e); }
    };
    try {
      if (lm.isInited) ask();          // init faqat bir marta — qayta chaqirilsa javob kelmaydi
      else lm.init(ask);
    } catch (e) { reject(e); }
  });
}

function browserLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Geolokatsiya yo'q"));
    navigator.geolocation.getCurrentPosition(
      p => resolve({lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy}),
      e => reject(new Error(e.code === 1 ? "denied" : "Joylashuv aniqlanmadi")),
      {enableHighAccuracy: true, timeout: 15000, maximumAge: 0});
  });
}

function acceptLocation(l, source) {
  const maxAcc = STATE.max_accuracy_m || 100;
  const acc = l.accuracy == null ? null : Math.round(l.accuracy);
  LOC = {lat: l.lat, lon: l.lon, accuracy: l.accuracy, source, ok: source === "chat" || (acc != null && acc <= maxAcc)};
  if (LOC.ok) {
    setStep("loc", true, source === "chat" ? `Joylashuv bot chatidan olindi${l.live ? " (jonli)" : ""}` : `Joylashuv aniqlandi (±${acc} m)`);
    stopChatPoll();
  } else {
    setStep("loc", false, `Aniqlik past (±${acc ?? "?"} m, kerak ≤ ${maxAcc} m). GPS'ni yoqing, ochiq joyga chiqing.
      <button class="btn ghost" onclick="getLocation()">Qayta</button>`);
  }
}

async function locationGranted() {
  const lm = tg && tg.LocationManager;
  if (lm && lm.isInited && lm.isAccessGranted) return true;
  try {
    if (navigator.permissions && navigator.permissions.query) {
      return (await navigator.permissions.query({name: "geolocation"})).state === "granted";
    }
  } catch {}
  return false;
}

// Bitta tez urinish (fonda qayta tekshirish uchun) — ekrandagi holatni o'zgartirmaydi.
// Ruxsat berilmagan bo'lsa hech narsa so'ramaydi: ruxsat oynasi faqat foydalanuvchi bosganda chiqadi.
let QUICK_BUSY = false;
async function quickTry() {
  if (QUICK_BUSY || (LOC && LOC.ok) || !(await locationGranted())) return;
  QUICK_BUSY = true;
  try {
    for (const [fn, ms] of [[tgLocation, 5000], [browserLocation, 8000]]) {
      try { const l = await withTimeout(fn(), ms, "timeout"); if (!(LOC && LOC.ok)) acceptLocation(l, "device"); return; } catch {}
    }
  } finally { QUICK_BUSY = false; }
}
let RETRY_TIMER = null;
function startAutoRetry() {
  if (RETRY_TIMER) return;
  RETRY_TIMER = setInterval(() => { if (LOC && LOC.ok) { clearInterval(RETRY_TIMER); RETRY_TIMER = null; } else quickTry(); }, 5000);
}
function onBackToApp() {
  if (!(LOC && LOC.ok)) quickTry();
  if (!STREAM && !PHOTO && CAM_FAILS && document.getElementById("video")) startCamera();
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) onBackToApp(); });
if (tg && tg.onEvent) { tg.onEvent("activated", onBackToApp); tg.onEvent("locationManagerUpdated", onBackToApp); }

async function getLocation() {
  const run = ++LOC_RUN;
  LOC = null;
  setStep("loc", null, `<span class="spin"></span> Joylashuv aniqlanmoqda...
    <div class="muted" style="font-size:12px;margin-top:4px">GPS o'chiq bo'lsa — yoqing, sahifa o'zi topadi.
    <a href="#" onclick="getLocation();return false">Qayta urinish</a></div>`);
  startAutoRetry();
  if (STATE.chat_location) return acceptLocation(STATE.chat_location, "chat");
  const errors = [];
  for (const [fn, ms, name] of [[tgLocation, 10000, "telegram"], [browserLocation, 12000, "brauzer"]]) {
    try {
      const l = await withTimeout(fn(), ms, `${name}: vaqt tugadi`);
      if (run !== LOC_RUN || (LOC && LOC.ok)) return;
      return acceptLocation(l, "device");
    } catch (e) {
      errors.push(`${name}: ${e.message}`);
      if (e.message === "denied" && tg && tg.LocationManager && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0")) {
        if (run !== LOC_RUN) return;
        setStep("loc", false, `Joylashuvga ruxsat berilmagan.
          <button class="btn ghost" onclick="Telegram.WebApp.LocationManager.openSettings()">Ruxsat berish</button>
          <button class="btn ghost" onclick="getLocation()">Qayta</button>`);
        return startChatPoll(errors);
      }
    }
  }
  if (run !== LOC_RUN || (LOC && LOC.ok)) return;
  showChatFallback(errors);
}
window.getLocation = getLocation;

function showChatFallback(errors) {
  report("location", errors.join(" · "));
  setStep("loc", false, `Telefon joylashuvni ilova ichida bermadi.<br>
    <b>Bot chatida:</b> 📎 → <b>Joylashuv</b> → <b>«Jonli joylashuvni ulashish»</b> ni bosing.
    Joylashuv kelishi bilan shu yerda avtomatik davom etadi.
    <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
      <button class="btn ghost" onclick="getLocation()">Qayta urinish</button>
      ${tg ? `<button class="btn ghost" onclick="Telegram.WebApp.close()">Chatga o'tish</button>` : ""}</div>
    <details style="margin-top:6px"><summary class="muted" style="font-size:12px">Texnik ma'lumot</summary>
      <div class="muted" style="font-size:12px">${esc(errors.join(" · "))} · ${tg ? esc(tg.platform + " " + tg.version) : "brauzer"}</div></details>`);
  startChatPoll(errors);
}

function startChatPoll() {
  stopChatPoll();
  CHAT_POLL = setInterval(async () => {
    try {
      const st = await api("/checkin/state");
      if (st.chat_location) { STATE.chat_location = st.chat_location; acceptLocation(st.chat_location, "chat"); }
    } catch {}
  }, 3000);
}
function stopChatPoll() { if (CHAT_POLL) clearInterval(CHAT_POLL); CHAT_POLL = null; }

// ------------------------------ yuborish ------------------------------
async function send() {
  if (!PHOTO || !LOC || !LOC.ok) return;
  const btn = document.getElementById("send");
  btn.disabled = true; btn.innerHTML = `<span class="spin"></span>`;
  const fd = new FormData();
  fd.append("direction", DIR);
  fd.append("loc_source", LOC.source === "chat" ? "chat" : "device");
  if (LOC.source !== "chat") { fd.append("lat", LOC.lat); fd.append("lon", LOC.lon); fd.append("accuracy", LOC.accuracy); }
  fd.append("photo", PHOTO, "photo.jpg");
  try {
    const r = await fetch(API + "/checkin", {method: "POST", body: fd, credentials: "same-origin",
      headers: TOKEN ? {"Authorization": "Bearer " + TOKEN} : {}});
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || `Xato ${r.status}`);
    if (STREAM) STREAM.getTracks().forEach(t => t.stop());
    stopChatPoll();
    if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
    const where = data.outside ? `<div class="err">📍 Ferma hududidan tashqarida (${(data.distance_m / 1000).toFixed(1)} km)</div>`
      : (data.distance_m != null ? `<div class="ok-msg">🏠 Ferma hududida</div>` : "");
    $app.innerHTML = `<div class="card" style="text-align:center">
      <div style="font-size:48px">✅</div>
      <h2>${DIR === "in" ? "Ish boshlandi" : "Ish tugatildi"}</h2>
      <p class="muted">${esc(data.ts.slice(0, 16))}</p>${where}
      <button class="btn big" id="close">Yopish</button></div>`;
    document.getElementById("close").onclick = () => tg ? tg.close() : history.back();
  } catch (e) {
    btn.disabled = false; btn.textContent = DIR === "in" ? "▶️ Ishni boshlash" : "⏹ Ishni tugatish";
    document.getElementById("msg").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

boot();
