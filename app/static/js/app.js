/* Router, navigation and start-up. */
"use strict";

const ROUTES = [
  [/^\/$/, "home", false], [/^\/login$/, "login", false], [/^\/register$/, "register", false], [/^\/invite\/([\w-]+)$/, "invite", false],
  [/^\/dashboard$/, "dashboard", true],
  [/^\/projects$/, "projects", true], [/^\/projects\/new$/, "projectForm", true], [/^\/projects\/(\d+)\/edit$/, "projectForm", true], [/^\/projects\/(\d+)$/, "project", true],
  [/^\/services$/, "services", true], [/^\/services\/new$/, "serviceForm", true], [/^\/services\/(\d+)\/edit$/, "serviceForm", true], [/^\/services\/(\d+)$/, "service", true],
  [/^\/engineers$/, "engineers", true], [/^\/engineers\/(\d+)$/, "engineer", true], [/^\/org\/(\d+)$/, "org", true],
  [/^\/organization$/, "organization", true], [/^\/profile$/, "profile", true], [/^\/account$/, "account", true],
  [/^\/finance$/, "finance", true], [/^\/disputes$/, "disputes", true], [/^\/disputes\/new$/, "disputeNew", true], [/^\/disputes\/(\d+)$/, "dispute", true],
  [/^\/messages$/, "messages", true], [/^\/messages\/(\d+)$/, "messages", true], [/^\/notifications$/, "notifications", true],
  [/^\/admin$/, "admin", true], [/^\/admin\/requests$/, "admin", true], [/^\/admin\/verifications$/, "admin", true],
];

function navItems() {
  const me = S.me;
  if (!me) return [["/", L("Home", "الرئيسية")], ["/login", L("Log in", "تسجيل الدخول")], ["/register", L("Create account", "إنشاء حساب")]];
  if (me.role === "admin") return [["/admin", L("Administration", "الإدارة")], ["/admin?tab=verifications", L("Verification", "التوثيق")], ["/admin?tab=requests", L("Request review", "مراجعة الطلبات")],
    ["/admin?tab=disputes", L("Disputes", "النزاعات")], ["/admin?tab=finance", L("Finance (demo)", "المالية (تجريبي)")], ["/admin?tab=settings", L("Settings", "الإعدادات")]];
  const items = [["/dashboard", L("Dashboard", "لوحة التحكم")]];
  if (me.role === "organization") {
    items.push(["/projects", L("Projects", "المشاريع")], ["/services", L("Short-term services", "الخدمات قصيرة المدة")], ["/engineers", L("Engineers", "المهندسون")]);
    if (me.permissions.includes("finance.view")) items.push(["/finance", L("Finance", "المالية")]);
    items.push(["/disputes", L("Disputes", "النزاعات")], ["/messages", L("Messages", "الرسائل")], ["/organization", L("Organization", "الجهة")]);
  } else {
    items.push(["/projects", L("Projects", "المشاريع")], ["/services", L("Short-term services", "الخدمات قصيرة المدة")], ["/finance", L("Payments", "المدفوعات")],
      ["/disputes", L("Disputes", "النزاعات")], ["/messages", L("Messages", "الرسائل")], ["/profile", L("My profile", "ملفي")]);
  }
  if (me.is_admin) items.push(["/admin", L("Admin", "الإدارة")]);
  return items;
}

B.renderChrome = function () {
  applyLang();
  const path = currentPath();
  const nav = document.getElementById("nav");
  const items = navItems();
  const pathOnly = path.split("?")[0];
  const exact = items.find(([x]) => x === path);
  nav.replaceChildren(...items.map(([href, label]) => {
    const base = href.split("?")[0];
    const active = exact ? href === exact[0] : (!href.includes("?") && (pathOnly === base || (base !== "/" && pathOnly.startsWith(base + "/"))));
    const extra = href === "/messages" && S.counts.messages ? h("span", { class: "pill", style: "margin-inline-start:.3rem", "aria-label": L(`${S.counts.messages} unread`, `${S.counts.messages} غير مقروءة`) }, S.counts.messages) : null;
    return h("a", { href: "#" + href, class: active ? "active" : null, "aria-current": active ? "page" : null, onclick: () => nav.classList.remove("open") }, label, extra);
  }));
  const tools = document.getElementById("tools");
  const langBtn = h("button", { class: "tool-btn", type: "button", lang: S.lang === "ar" ? "en" : "ar", onclick: () => setLang(S.lang === "ar" ? "en" : "ar") }, S.lang === "ar" ? "English" : "العربية");
  const kids = [langBtn];
  if (S.me) {
    kids.unshift(h("a", { class: "tool-btn", href: "#/notifications", "aria-label": L(`Notifications, ${S.counts.notifications} unread`, `الإشعارات، ${S.counts.notifications} غير مقروءة`) },
      h("span", { "aria-hidden": "true" }, "🔔"), S.counts.notifications ? h("span", { class: "pill" }, S.counts.notifications) : null));
    kids.push(h("a", { class: "tool-btn", href: "#/account", title: L("Account settings", "إعدادات الحساب") }, S.me.name.split(" ")[0]),
      h("button", { class: "tool-btn", type: "button", onclick: async () => { try { await api("/auth/logout", { method: "POST" }); } catch { /* ignore */ } S.me = null; B.renderChrome(); go("/"); } }, L("Log out", "خروج")));
  }
  tools.replaceChildren(...kids);
  const banner = document.getElementById("demo-banner");
  banner.hidden = false;
  banner.textContent = L("PROTOTYPE – fictional data only · all payments are simulated · legal and financial terms pending review",
    "نموذج تجريبي – بيانات وهمية فقط · جميع المدفوعات تجريبية · الشروط القانونية والمالية بانتظار المراجعة");
  document.getElementById("footer").textContent = L("BUNYAH | بُنية – functional prototype for review. Not legally or regulatorily approved. Western numerals, Gregorian dates (Hijri optional in account settings).",
    "بُنية | BUNYAH – نموذج وظيفي للمراجعة، غير معتمد قانونيًا أو تنظيميًا. أرقام لاتينية وتواريخ ميلادية (الهجري اختياري من إعدادات الحساب).");
};

B.render = async function () {
  S.timers.forEach(clearInterval); S.timers = [];
  const full = currentPath();
  const [path, qs] = full.split("?");
  const q = new URLSearchParams(qs || "");
  B.renderChrome();
  const match = ROUTES.find(([re]) => re.test(path));
  const main = $main();
  if (!match) { main.replaceChildren(empty(L("Page not found", "الصفحة غير موجودة"), L("That address doesn't exist.", "هذا العنوان غير موجود."), linkBtn("/", L("Go home", "الرئيسية")))); return; }
  const [re, viewName, needsLogin] = match;
  if (needsLogin && !S.me) { go("/login?next=" + encodeURIComponent(full)); return; }
  const params = path.match(re).slice(1);
  if (!main.firstChild || main.dataset.path !== path) main.replaceChildren(h("p", { class: "loading" }, L("Loading…", "جارٍ التحميل…")));
  try {
    const node = await B.views[viewName](params, q);
    if (currentPath() === full && node) {
      const y = main.dataset.path === path ? window.scrollY : 0;
      main.replaceChildren(node); main.dataset.path = path;
      document.title = (node.querySelector("h1")?.textContent || "") + " – BUNYAH | بُنية";
      window.scrollTo(0, y);
    }
  } catch (err) {
    if (err.status === 401) return;
    console.error(err);
    main.replaceChildren(empty(err.status === 404 ? L("Not found", "غير موجود") : (err.status === 403 ? L("No access", "لا توجد صلاحية") : L("Couldn't load this page", "تعذر تحميل الصفحة")), err.message,
      linkBtn(S.me ? "/dashboard" : "/", L("Back to the start", "العودة للبداية"), "btn secondary")));
  }
};

async function refreshCounts() {
  if (!S.me) return;
  try {
    const c = await api("/notifications/unread-count");
    const changed = c.notifications !== S.counts.notifications || c.messages !== S.counts.messages;
    S.counts = c;
    if (changed) B.renderChrome();
  } catch { /* ignore */ }
}

(async function init() {
  loadPrefs(); applyLang();
  document.getElementById("menu-btn").addEventListener("click", (e) => {
    const nav = document.getElementById("nav"); const open = !nav.classList.contains("open");
    nav.classList.toggle("open", open); e.currentTarget.setAttribute("aria-expanded", String(open));
  });
  try { S.me = await api("/auth/me"); } catch { S.me = null; }
  let stored = null;
  try { stored = localStorage.getItem("bunyah.lang"); } catch { /* storage blocked */ }
  if (S.me && S.me.locale && !stored) { S.lang = S.me.locale; applyLang(); }
  window.addEventListener("hashchange", () => { B.render(); document.getElementById("main").focus({ preventScroll: true }); });
  await refreshCounts();
  setInterval(refreshCounts, 20000);
  B.render();
})();
