/* BUNYAH front end – shared helpers. Every screen is a "view" function chosen by the address after the # sign.
   Safety rule used everywhere: text is inserted with textContent (via h()), never as HTML.
   Language: Arabic (RTL) is the default, English (LTR) is a complete alternative. L(en, ar) picks the right text. */
"use strict";

const API = "/api/v1";
const B = window.B = { state: { me: null, lang: "ar", hijri: false, timers: [], counts: { notifications: 0, messages: 0 } }, views: {} };
const S = B.state;

/* ---------------- language ---------------- */
function loadPrefs() {
  try {
    S.lang = localStorage.getItem("bunyah.lang") || "ar";
    S.hijri = localStorage.getItem("bunyah.hijri") === "1";
  } catch { /* storage may be blocked; defaults apply */ }
}
function savePref(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } }
function L(en, ar) { return S.lang === "ar" ? (ar ?? en) : en; }
function applyLang() {
  const html = document.documentElement;
  html.lang = S.lang; html.dir = S.lang === "ar" ? "rtl" : "ltr";
  document.getElementById("skip-link").textContent = L("Skip to content", "تخطي إلى المحتوى");
  document.querySelector(".menu-label").textContent = L("Menu", "القائمة");
  document.getElementById("brand-link").setAttribute("aria-label", L("BUNYAH home", "الصفحة الرئيسية لبُنية"));
  document.getElementById("nav").setAttribute("aria-label", L("Main", "القائمة الرئيسية"));
}
function setLang(lang) {
  S.lang = lang; savePref("bunyah.lang", lang); applyLang();
  if (S.me && S.me.locale !== lang) api("/auth/me", { method: "PATCH", body: { locale: lang } }).catch(() => {});
  B.render();
}

/* ---------------- DOM ---------------- */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v;
    else if (k === "value") el.value = v;
    else if (k === "checked") el.checked = !!v;
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, String(v));
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const $main = () => document.getElementById("main");

/* ---------------- API ---------------- */
class ApiErr extends Error {
  constructor(status, code, message, details) { super(message); this.status = status; this.code = code; this.details = details || []; }
}
async function api(path, { method = "GET", body, form } = {}) {
  const opts = { method, credentials: "same-origin", headers: { "X-Requested-With": "fetch" } };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(API + path, opts); }
  catch { throw new ApiErr(0, "NETWORK", L("Can't reach the server. Check your connection and try again.", "تعذر الاتصال بالخادم. تحقق من الاتصال وحاول مرة أخرى.")); }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = (data && data.error) || {};
    if (res.status === 401 && !["/auth/login", "/auth/me", "/auth/password"].includes(path)) {
      S.me = null; B.renderChrome(); go("/login?next=" + encodeURIComponent(currentPath()));
    }
    const msg = (S.lang === "ar" && e.message_ar) ? e.message_ar : (e.message || L("Something went wrong. Please try again.", "حدث خطأ. حاول مرة أخرى."));
    throw new ApiErr(res.status, e.code || "ERROR", msg, e.details);
  }
  return data;
}

/* ---------------- formatting ---------------- */
const LOCALE = () => S.lang === "ar" ? "ar-SA-u-nu-latn-ca-gregory" : "en-GB";
function money(cents, { plain } = {}) {
  if (cents === null || cents === undefined) return "—";
  const v = cents / 100;
  const txt = new Intl.NumberFormat(S.lang === "ar" ? "ar-SA-u-nu-latn" : "en-US", { style: "currency", currency: (S.me && S.me.currency) || "SAR", maximumFractionDigits: v % 1 ? 2 : 0 }).format(v);
  return plain ? txt : h("span", { class: "money" }, txt);
}
function parseMoney(str) {
  const n = Number(String(str ?? "").replace(/[٠-٩]/g, d => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace(/[^\d.]/g, ""));
  return Number.isFinite(n) && String(str).trim() !== "" ? Math.round(n * 100) : null;
}
function toDate(d) { return d.length === 10 ? new Date(d + "T00:00:00") : new Date(d); }
function fmtDate(d) {
  if (!d) return "—";
  const dt = toDate(d);
  const g = dt.toLocaleDateString(LOCALE(), { year: "numeric", month: "short", day: "numeric" });
  if (!S.hijri) return h("time", { datetime: d }, g);
  const hj = dt.toLocaleDateString(S.lang === "ar" ? "ar-SA-u-ca-islamic-umalqura-nu-latn" : "en-u-ca-islamic-umalqura", { year: "numeric", month: "short", day: "numeric" });
  return h("time", { datetime: d, title: hj }, g, h("span", { class: "muted small" }, " · " + hj));
}
function fmtTime(d) { return d ? h("time", { datetime: d }, new Date(d).toLocaleString(LOCALE(), { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })) : "—"; }
function todayISO() { const t = new Date(); t.setMinutes(t.getMinutes() - t.getTimezoneOffset()); return t.toISOString().slice(0, 10); }
function addDaysISO(n) { const t = new Date(); t.setDate(t.getDate() + n); t.setMinutes(t.getMinutes() - t.getTimezoneOffset()); return t.toISOString().slice(0, 10); }
function sizeLabel(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB"; }
function nm(o) { if (!o) return "—"; return S.lang === "ar" && o.name_ar ? o.name_ar : (o.name_en || o.name || "—"); }
function stars(r) { const n = Math.round(r || 0); return h("span", { class: "stars", "aria-label": L(`${r} out of 5`, `${r} من 5`) }, "★".repeat(n) + "☆".repeat(5 - n)); }
function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : null; }

/* ---------------- statuses (word + icon + colour) ---------------- */
const ST = {
  draft: ["Draft", "مسودة", "neutral"], published: ["Published", "منشور", "info"],
  applications_closed: ["Proposals closed", "أُغلق استقبال العروض", "neutral"], under_evaluation: ["Under evaluation", "قيد التقييم", "info"],
  shortlisted: ["Shortlisted", "قائمة مختصرة", "info"], proposal_accepted: ["Proposal accepted", "تم قبول العرض", "success"],
  in_progress: ["In progress", "قيد التنفيذ", "info"], submitted: ["Submitted", "مقدَّم", "warning"],
  revision_requested: ["Revision requested", "مطلوب تعديل", "warning"], resubmitted: ["Resubmitted", "أعيد تقديمه", "warning"],
  approved: ["Approved", "معتمد", "success"], completed: ["Completed", "مكتمل", "success"], cancelled: ["Cancelled", "ملغى", "danger"],
  disputed: ["Disputed", "متنازع عليه", "danger"], pending_review: ["Pending BUNYAH review", "قيد مراجعة بُنية", "warning"],
  applications_open: ["Applications open", "التقديم مفتوح", "info"], selected: ["Selected", "تم الاختيار", "success"],
  contract_preparation: ["Contract preparation", "إعداد العقد", "info"], awaiting_signatures: ["Awaiting signatures", "بانتظار التوقيع", "warning"],
  active: ["Active", "ساري", "success"], near_expiry: ["Near expiry", "قرب الانتهاء", "warning"], terminated: ["Terminated", "أُنهي مبكرًا", "danger"],
  clarification_requested: ["Clarification requested", "مطلوب توضيح", "warning"], accepted: ["Accepted", "مقبول", "success"],
  rejected: ["Not selected", "لم يتم الاختيار", "neutral"], withdrawn: ["Withdrawn", "مسحوب", "neutral"],
  awaiting_upload: ["Awaiting upload", "بانتظار الرفع", "neutral"], under_review: ["Under review", "قيد المراجعة", "warning"],
  superseded: ["Superseded", "استُبدلت", "neutral"], planned: ["Planned", "مخطط", "neutral"], open: ["Open", "مفتوح", "info"],
  issued: ["Issued", "صادرة", "warning"], paid: ["Paid (demo)", "مدفوعة (تجريبي)", "success"], refunded: ["Refunded (demo)", "مستردة (تجريبي)", "danger"],
  void: ["Void", "ملغاة", "neutral"], pending: ["Pending", "معلّق", "warning"], decided: ["Decision recorded", "صدر القرار", "info"],
  appealed: ["Appealed", "مستأنف", "warning"], closed: ["Closed", "مغلق", "neutral"], verified: ["Verified", "موثّق", "success"],
  unverified: ["Not verified", "غير موثّق", "neutral"], needs_info: ["More info needed", "مطلوب معلومات إضافية", "warning"],
  todo: ["To do", "للتنفيذ", "neutral"], done: ["Done", "منجز", "success"], recorded: ["Recorded", "مسجّل", "neutral"],
  period_submitted: ["Billing period waiting", "فترة فوترة بانتظار الاعتماد", "warning"], resolved: ["Resolved", "تمت المعالجة", "success"],
};
const TONE_ICON = { success: "✓", warning: "◷", danger: "!", info: "●", neutral: "○" };
function statusLabel(s) { const x = ST[s]; return x ? L(x[0], x[1]) : String(s || "—").replace(/_/g, " "); }
function badge(s, override) {
  const tone = (ST[s] && ST[s][2]) || "neutral";
  return h("span", { class: "badge tone-" + tone }, h("span", { class: "ic", "aria-hidden": "true" }, TONE_ICON[tone]), override || statusLabel(s));
}
function demoTag(text) { return h("span", { class: "demo-tag", title: L("Simulated – no real money moves", "تجريبي – لا تتم أي حركة مالية حقيقية") }, text || L("DEMO / SIMULATED", "تجريبي / محاكاة")); }
const ORG_ROLES = { owner: ["Owner", "المالك"], project_manager: ["Project Manager", "مدير المشاريع"], technical_reviewer: ["Technical Reviewer", "المراجع الفني"], finance: ["Finance", "المالية"], viewer: ["Viewer", "مشاهد"] };
const orgRole = r => r ? L(...ORG_ROLES[r]) : "—";
const WORK_MODES = { remote: ["Remote", "عن بُعد"], onsite: ["On-site", "في الموقع"], hybrid: ["Hybrid", "مختلط"] };
const workMode = m => WORK_MODES[m] ? L(...WORK_MODES[m]) : (m || "—");

/* ---------------- feedback ---------------- */
function toast(msg, isError) {
  const t = h("div", { class: "toast" + (isError ? " error" : ""), role: isError ? "alert" : null }, msg);
  document.getElementById("toasts").append(t);
  setTimeout(() => t.remove(), isError ? 7000 : 3500);
}
function errorBox() { return h("div", { class: "form-error hidden", role: "alert" }); }
function showError(box, err) { box.textContent = err.message || String(err); box.classList.remove("hidden"); box.scrollIntoView({ block: "nearest" }); }

/** Dialog asking for confirmation, optionally with a text input. Resolves {ok, value}. */
function ask(message, okLabel, { danger, input, inputLabel, required, minLength = 0, value = "" } = {}) {
  return new Promise((resolve) => {
    let field = null;
    if (input) field = h(input === "textarea" ? "textarea" : "input", { id: "dlg-input", type: input === "textarea" ? null : input, value, rows: 4 });
    const err = h("div", { class: "field-error hidden", role: "alert" });
    const ok = h("button", { class: danger ? "btn danger" : "btn", type: "button" }, okLabel);
    const back = h("button", { class: "btn secondary", type: "button" }, L("Go back", "رجوع"));
    const dlg = h("dialog", { "aria-labelledby": "dlg-msg" },
      h("p", { id: "dlg-msg", style: "margin-bottom:1rem;font-weight:600" }, message),
      field ? h("div", { class: "field" }, h("label", { for: "dlg-input" }, inputLabel || ""), field, err) : null,
      h("div", { class: "row end" }, back, ok));
    const finish = (r) => { dlg.close(); dlg.remove(); resolve(r); };
    ok.addEventListener("click", () => {
      const v = field ? field.value.trim() : "";
      if (field && required && v.length < Math.max(1, minLength)) {
        err.textContent = minLength > 1 ? L(`Please write at least ${minLength} characters.`, `يرجى كتابة ${minLength} حرفًا على الأقل.`) : L("This field is required.", "هذا الحقل مطلوب.");
        err.classList.remove("hidden"); field.setAttribute("aria-invalid", "true"); field.focus(); return;
      }
      finish({ ok: true, value: v });
    });
    back.addEventListener("click", () => finish({ ok: false }));
    dlg.addEventListener("cancel", (e) => { e.preventDefault(); finish({ ok: false }); });
    document.body.append(dlg); dlg.showModal(); (field || back).focus();
  });
}

/** A button that runs an action (optionally after a confirmation), shows the result and redraws the page. */
function action(label, fn, { confirm, cls = "btn", done, prompt } = {}) {
  return h("button", {
    class: cls, type: "button", onclick: async (ev) => {
      const btn = ev.currentTarget;
      let value;
      if (confirm || prompt) {
        const r = await ask(confirm || prompt.message, prompt?.okLabel || label, { danger: cls.includes("danger"), ...(prompt || {}) });
        if (!r.ok) return;
        value = r.value;
      }
      btn.disabled = true; btn.setAttribute("aria-busy", "true");
      try { await fn(value); if (done) toast(done); await B.render(); }
      catch (err) { toast(err.message, true); btn.disabled = false; btn.removeAttribute("aria-busy"); }
    },
  }, label);
}

/* ---------------- forms ---------------- */
let _fid = 0;
function field(labelText, input, { hint, required, full } = {}) {
  const id = input.id || ("f" + (++_fid)); input.id = id;
  if (required) input.required = true;
  const hintEl = hint ? h("div", { class: "hint", id: id + "-hint" }, hint) : null;
  if (hintEl) input.setAttribute("aria-describedby", id + "-hint");
  return h("div", { class: "field" + (full ? " full" : "") }, h("label", { for: id, class: required ? "req" : null }, labelText), input, hintEl);
}
function inp(name, attrs = {}) { return h("input", { name, type: "text", ...attrs }); }
function txt(name, attrs = {}) { return h("textarea", { name, rows: 4, ...attrs }, attrs.value || ""); }
function sel(name, options, value, attrs = {}) {
  return h("select", { name, ...attrs }, options.map(([v, label]) => h("option", { value: v, selected: String(v) === String(value ?? "") ? true : null }, label)));
}
function moneyInput(name, cents, attrs = {}) {
  return inp(name, { inputmode: "decimal", "data-type": "money", value: cents ? String(cents / 100) : "", placeholder: L("Amount in SAR", "المبلغ بالريال"), ...attrs });
}
/** Reads a form into an object. data-type="money" -> halalas, "int"/"float" -> numbers, empty optional -> null. */
function readForm(form) {
  const out = {};
  for (const el of form.elements) {
    if (!el.name || el.disabled || el.type === "file") continue;
    if (el.type === "checkbox") { out[el.name] = el.checked; continue; }
    const v = el.value.trim(), t = el.dataset.type;
    if (t === "money") out[el.name] = v === "" ? null : parseMoney(v);
    else if (t === "int") out[el.name] = v === "" ? null : parseInt(v, 10);
    else if (t === "float") out[el.name] = v === "" ? null : parseFloat(v);
    else if (t === "nullable") out[el.name] = v === "" ? null : v;
    else out[el.name] = v;
  }
  return out;
}
function onSubmit(form, handler) {
  const box = form.querySelector(".form-error");
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    if (box) box.classList.add("hidden");
    form.querySelectorAll("[aria-invalid]").forEach(e => e.removeAttribute("aria-invalid"));
    if (btn) { btn.disabled = true; btn.setAttribute("aria-busy", "true"); }
    try { await handler(readForm(form), new FormData(form)); }
    catch (err) {
      (err.details || []).forEach(d => { const el = form.querySelector(`[name="${CSS.escape(d.field)}"]`); if (el) el.setAttribute("aria-invalid", "true"); });
      if (box) showError(box, err); else toast(err.message, true);
    }
    finally { if (btn) { btn.disabled = false; btn.removeAttribute("aria-busy"); } }
  });
  return form;
}
function strip(obj) { const o = {}; for (const [k, v] of Object.entries(obj)) if (v !== null && v !== "") o[k] = v; return o; }

/* ---------------- building blocks ---------------- */
function table(columns, rows, { empty: emptyText } = {}) {
  if (!rows.length) return h("p", { class: "muted" }, emptyText || L("Nothing here yet.", "لا توجد بيانات بعد."));
  const t = h("table", { class: "data stack" },
    h("thead", {}, h("tr", {}, columns.map(c => h("th", { scope: "col", class: c.num ? "num" : null }, c.label)))),
    h("tbody", {}, rows.map(r => h("tr", {}, columns.map(c => h("td", { "data-label": c.label, class: c.num ? "num" : null }, c.render(r)))))));
  return h("div", { class: "table-wrap" }, t);
}
function tabs(items, active, base) {
  return h("nav", { class: "tabs", "aria-label": L("Sections", "الأقسام") }, items.filter(Boolean).map(([key, label, count]) =>
    h("a", { href: "#" + base + (base.includes("?") ? "&" : "?") + "tab=" + key, "aria-current": key === active ? "page" : null }, label, count ? h("span", { class: "pill", style: "margin-inline-start:.35rem;background:var(--surface-2)" }, count) : null)));
}
function stat(label, value, hint) { return h("div", { class: "stat" }, h("div", { class: "label" }, label), h("div", { class: "value" }, value), hint ? h("div", { class: "hint" }, hint) : null); }
function empty(title, text, cta) { return h("div", { class: "empty" }, h("h3", {}, title), text ? h("p", {}, text) : null, cta || null); }
function card(title, ...kids) { return h("section", { class: "card" }, title ? h("h2", {}, title) : null, ...kids); }
function cardHead(title, ...actions) { return h("div", { class: "card-head" }, h("h2", {}, title), h("div", { class: "btn-row" }, ...actions)); }
function kv(pairs) { return h("dl", { class: "kv" }, pairs.filter(Boolean).flatMap(([k, v]) => [h("dt", {}, k), h("dd", { dir: typeof v === "string" ? "auto" : null }, v ?? "—")])); }
function pageHead(title, sub, ...actions) {
  return h("div", { class: "page-head" }, h("div", {}, h("h1", {}, title), sub ? h("p", { class: "sub" }, sub) : null), actions.length ? h("div", { class: "btn-row" }, ...actions) : null);
}
function linkBtn(href, label, cls = "btn") { return h("a", { class: cls, href: "#" + href }, label); }
function notice(kind, ...kids) { return h("div", { class: "notice " + kind, role: kind === "danger" ? "alert" : null }, ...kids); }
function stepper(flow, current) {
  const idx = flow.indexOf(current);
  return h("ol", { class: "stepper", "aria-label": L("Workflow progress", "مراحل سير العمل") }, flow.map((s, i) =>
    h("li", { class: i < idx ? "done" : (i === idx ? "current" : null), "aria-current": i === idx ? "step" : null }, statusLabel(s))));
}
function fileLink(f, label) {
  return h("a", { href: `${API}/files/${f.id}`, download: f.filename }, label || f.filename);
}
/** Small upload form. extra: extra form fields (inputs). onDone receives the response. */
function uploadForm(path, { label, extra = [], accept, onDone, button, multiple, fieldName = "file", optional } = {}) {
  const box = errorBox();
  const fileInput = h("input", { type: "file", name: fieldName, required: !optional, accept: accept || ".pdf,.dwg,.dxf,.rvt,.rfa,.docx,.xlsx,.jpg,.jpeg,.png,.zip,.ifc,.pptx", multiple: multiple || null });
  const form = h("form", { class: "stack-sm" }, box, field(label || L("File", "الملف"), fileInput, { hint: L("PDF, DWG, DXF, RVT, RFA, DOCX, XLSX, JPG, PNG or ZIP – up to 25 MB.", "PDF أو DWG أو DXF أو RVT أو RFA أو DOCX أو XLSX أو JPG أو PNG أو ZIP – حتى 25 ميجابايت.") }), ...extra,
    h("button", { class: "btn", type: "submit" }, button || L("Upload", "رفع")));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    box.classList.add("hidden");
    const btn = form.querySelector("button[type=submit]"); btn.disabled = true;
    try { const r = await api(path, { method: "POST", form: new FormData(form) }); toast(L("Uploaded.", "تم الرفع.")); if (onDone) await onDone(r); else await B.render(); }
    catch (err) { showError(box, err); }
    finally { btn.disabled = false; }
  });
  return form;
}

/* ---------------- router ---------------- */
function currentPath() { return location.hash.replace(/^#/, "") || "/"; }
function go(path) { if (currentPath() === path) B.render(); else location.hash = "#" + path; }
function query() { return new URLSearchParams((currentPath().split("?")[1]) || ""); }
function every(ms, fn) { S.timers.push(setInterval(fn, ms)); }

Object.assign(B, { L, h, api, ApiErr, money, parseMoney, fmtDate, fmtTime, todayISO, addDaysISO, sizeLabel, nm, stars, safeUrl,
  badge, statusLabel, demoTag, orgRole, workMode, ORG_ROLES, WORK_MODES, toast, errorBox, showError, ask, action, field, inp, txt, sel,
  moneyInput, readForm, onSubmit, strip, table, tabs, stat, empty, card, cardHead, kv, pageHead, linkBtn, notice, stepper, fileLink,
  uploadForm, currentPath, go, query, every, loadPrefs, applyLang, setLang, $main });
