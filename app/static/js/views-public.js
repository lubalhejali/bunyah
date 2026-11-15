/* Public pages: landing, log in (with demo accounts), sign up, accept invitation. */
"use strict";

B.views.home = async function () {
  if (S.me) { go(S.me.is_admin && S.me.role === "admin" ? "/admin" : "/dashboard"); return null; }
  const model = (title, sub, steps) => h("section", { class: "card model-card" }, h("div", { class: "eyebrow" }, sub), h("h2", {}, title),
    h("ol", {}, steps.map(s => h("li", {}, s))));
  return h("div", { class: "stack" },
    h("section", { class: "hero" },
      h("div", { class: "eyebrow", style: "color:#B4B8A9" }, L("Saudi engineering services platform", "منصة سعودية للخدمات الهندسية")),
      h("h1", {}, L("Qualified engineering professionals for organizations that build.", "كفاءات هندسية مؤهلة للجهات التي تبني.")),
      h("p", {}, L("BUNYAH connects organizations and engineering companies with verified independent engineers – for defined projects or short-term engineering services – with clear workflows, versioned deliverables and accountable reviews.",
        "تربط بُنية الجهات والشركات الهندسية بمهندسين مستقلين موثّقين، لمشاريع محددة أو لخدمات هندسية قصيرة المدة، عبر مسارات عمل واضحة وتسليمات بنسخ موثقة ومراجعات مسؤولة.")),
      h("div", { class: "btn-row" }, linkBtn("/register", L("Create an account", "إنشاء حساب")), linkBtn("/login", L("Log in", "تسجيل الدخول"), "btn secondary"))),
    notice("warning", h("strong", {}, L("Prototype for review. ", "نموذج تجريبي للمراجعة. ")),
      L("All people and companies are fictional, payments are simulated, and legal, tax and data-hosting questions are pending professional review.",
        "جميع الأشخاص والجهات وهمية، والمدفوعات تجريبية، والمسائل القانونية والضريبية واستضافة البيانات بانتظار المراجعة المهنية.")),
    h("div", { class: "grid grid-2" },
      model(L("Engineering projects", "المشاريع الهندسية"), L("Model A – project-based", "النموذج أ – على أساس المشروع"), [
        L("The organization publishes a project with scope, deliverables and budget.", "تنشر الجهة مشروعًا بنطاقه وتسليماته وميزانيته."),
        L("Engineers send technical and financial proposals.", "يقدّم المهندسون عروضًا فنية ومالية."),
        L("The organization compares, shortlists and selects.", "تقارن الجهة العروض وتختصرها وتختار."),
        L("Work happens in a project workspace with optional milestones (up to 6).", "يتم العمل في مساحة مشروع بمراحل اختيارية (حتى 6)."),
        L("Every deliverable is versioned and reviewed: V1 → review → V2 → final approval.", "لكل تسليم نسخ ومراجعة: V1 ← مراجعة ← V2 ← اعتماد نهائي.")]),
      model(L("Short-term engineering services", "الخدمات الهندسية قصيرة المدة"), L("Model B – daily rate", "النموذج ب – بالسعر اليومي"), [
        L("The organization requests an engineer for a defined period.", "تطلب الجهة مهندسًا لمدة محددة."),
        L("BUNYAH reviews the request before it is published.", "تراجع بُنية الطلب قبل نشره."),
        L("Engineers apply; the organization compares and selects.", "يتقدّم المهندسون؛ وتقارن الجهة وتختار."),
        L("A contract is prepared and signed by both parties.", "يُعد عقد ويوقّعه الطرفان."),
        L("Daily work records are approved in billing periods of 20 working days.", "تُعتمد سجلات العمل اليومية في فترات فوترة من 20 يوم عمل.")])),
    h("div", { class: "grid grid-3" },
      card(L("Verified participants", "مشاركون موثّقون"), h("p", { class: "muted" }, L("Organizations and engineers are verified by the BUNYAH team. Verification documents stay private.", "يتم توثيق الجهات والمهندسين من فريق بُنية، وتبقى مستندات التوثيق سرية."))),
      card(L("No automatic approvals", "لا اعتماد تلقائي"), h("p", { class: "muted" }, L("If a review window passes, the work stays pending and is escalated – never approved silently.", "إذا انتهت مهلة المراجعة يبقى العمل معلقًا ويتم تصعيده، ولا يُعتمد تلقائيًا أبدًا."))),
      card(L("Reasoned dispute decisions", "قرارات نزاع مسبّبة"), h("p", { class: "muted" }, L("Disputes follow a documented process with evidence, responses, a reasoned decision and an appeal.", "تسير النزاعات وفق إجراء موثق يشمل الأدلة والردود وقرارًا مسببًا وإمكانية الاستئناف.")))));
};

B.views.login = async function (params, q) {
  if (S.me) { go(q.get("next") || "/dashboard"); return null; }
  const box = errorBox();
  const form = onSubmit(h("form", { class: "card", style: "max-width:460px" },
    h("h1", {}, L("Log in", "تسجيل الدخول")), box,
    field(L("E-mail", "البريد الإلكتروني"), inp("email", { type: "email", autocomplete: "username", dir: "ltr" }), { required: true }),
    field(L("Password", "كلمة المرور"), inp("password", { type: "password", autocomplete: "current-password", dir: "ltr" }), { required: true }),
    h("button", { class: "btn", type: "submit" }, L("Log in", "تسجيل الدخول")),
    h("p", { class: "muted small", style: "margin-top:1rem" }, L("No account yet? ", "ليس لديك حساب؟ "), h("a", { href: "#/register" }, L("Create one", "أنشئ حسابًا")))),
  async (d) => { S.me = await api("/auth/login", { method: "POST", body: d }); afterLogin(q.get("next")); });
  const wrap = h("div", { class: "grid grid-2", style: "align-items:start" }, form);
  if (true) {
    try {
      const demos = await api("/auth/demo-accounts");
      if (demos.length) {
        const groups = { organization: L("Organization", "الجهة"), engineer: L("Engineer", "المهندس"), admin: L("Administrator", "الإدارة") };
        wrap.append(h("section", { class: "card" },
          h("div", { class: "row between" }, h("h2", {}, L("Demo accounts", "الحسابات التجريبية")), demoTag(L("FICTIONAL", "وهمية"))),
          h("p", { class: "muted small" }, L("One click logs you in as a fictional person. Use these to test every scenario. The shared demo password is in DEMO_ACCOUNTS.md.",
            "بنقرة واحدة تدخل بحساب شخص وهمي لاختبار جميع السيناريوهات. كلمة المرور المشتركة موجودة في ملف DEMO_ACCOUNTS.md.")),
          Object.entries(groups).map(([g, label]) => {
            const list = demos.filter(d => d.group === g);
            return list.length ? h("div", {}, h("h3", { class: "section-title" }, label), h("div", { class: "demo-grid" }, list.map(d =>
              h("button", { class: "btn secondary small", type: "button", onclick: async (ev) => {
                ev.currentTarget.disabled = true;
                try { S.me = await api("/auth/demo-login", { method: "POST", body: { key: d.key } }); afterLogin(q.get("next")); }
                catch (err) { toast(err.message, true); ev.currentTarget.disabled = false; }
              } }, L(d.label_en, d.label_ar))))) : null;
          })));
      }
    } catch { /* demo mode off */ }
  }
  return wrap;
};

function afterLogin(next) {
  if (S.me.locale && S.me.locale !== S.lang) { S.lang = S.me.locale; savePref("bunyah.lang", S.lang); applyLang(); }
  B.renderChrome();
  go(next && next.startsWith("/") ? next : (S.me.role === "admin" ? "/admin" : "/dashboard"));
}

B.views.register = async function () {
  if (S.me) { go("/dashboard"); return null; }
  const box = errorBox();
  const orgField = field(L("Organization name", "اسم الجهة"), inp("org_name", { autocomplete: "organization" }), { required: true });
  const roleSel = sel("role", [["organization", L("An organization or engineering company", "جهة أو شركة هندسية")], ["engineer", L("An independent engineer", "مهندس مستقل")]], "organization");
  roleSel.addEventListener("change", () => { orgField.classList.toggle("hidden", roleSel.value !== "organization"); orgField.querySelector("input").required = roleSel.value === "organization"; });
  const form = onSubmit(h("form", { class: "card", style: "max-width:560px" },
    h("h1", {}, L("Create your account", "إنشاء حساب")),
    h("p", { class: "muted" }, L("After signing up, complete your profile and submit verification. The BUNYAH team reviews every account.", "بعد التسجيل أكمل ملفك وأرسل طلب التوثيق. يراجع فريق بُنية كل حساب.")),
    box,
    field(L("I am", "أنا"), roleSel, { required: true }),
    orgField,
    field(L("Your full name", "اسمك الكامل"), inp("name", { autocomplete: "name" }), { required: true }),
    field(L("E-mail", "البريد الإلكتروني"), inp("email", { type: "email", autocomplete: "email", dir: "ltr" }), { required: true }),
    field(L("Password", "كلمة المرور"), inp("password", { type: "password", autocomplete: "new-password", minlength: 10, dir: "ltr" }), { required: true, hint: L("At least 10 characters.", "10 أحرف على الأقل.") }),
    h("input", { type: "hidden", name: "locale", value: S.lang }),
    h("label", { class: "check" }, h("input", { type: "checkbox", name: "accept_terms", required: true }),
      h("span", {}, L("I understand this is a prototype with fictional data and simulated payments, and I won't enter real personal or financial data.",
        "أدرك أن هذا نموذج تجريبي ببيانات وهمية ومدفوعات تجريبية، ولن أُدخل بيانات شخصية أو مالية حقيقية."))),
    h("div", { style: "margin-top:1rem" }, h("button", { class: "btn", type: "submit" }, L("Create account", "إنشاء الحساب")))),
  async (d) => { S.me = await api("/auth/register", { method: "POST", body: d }); toast(L("Account created.", "تم إنشاء الحساب.")); afterLogin(d.role === "engineer" ? "/profile" : "/organization"); });
  return form;
};

B.views.invite = async function ([token]) {
  const inv = await api("/auth/invitations/" + encodeURIComponent(token));
  const box = errorBox();
  return onSubmit(h("form", { class: "card", style: "max-width:520px" },
    h("h1", {}, L("Join your team on BUNYAH", "انضم إلى فريقك في بُنية")),
    kv([[L("Organization", "الجهة"), inv.organization], [L("Role", "الدور"), orgRole(inv.org_role)], [L("E-mail", "البريد الإلكتروني"), h("span", { class: "ltr" }, inv.email)]]),
    h("hr", { class: "rule" }), box,
    field(L("Your full name", "اسمك الكامل"), inp("name", { value: inv.name }), { required: true }),
    field(L("Choose a password", "اختر كلمة مرور"), inp("password", { type: "password", minlength: 10, autocomplete: "new-password", dir: "ltr" }), { required: true, hint: L("At least 10 characters.", "10 أحرف على الأقل.") }),
    h("input", { type: "hidden", name: "token", value: token }),
    h("button", { class: "btn", type: "submit" }, L("Join the team", "الانضمام للفريق"))),
  async (d) => { S.me = await api("/auth/invitations/accept", { method: "POST", body: d }); afterLogin("/dashboard"); });
};
