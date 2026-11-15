/* Organization profile & team, engineer profile, verification, account settings, public profiles, engineer search. */
"use strict";

let DISCIPLINES = null;
async function disciplines() { if (!DISCIPLINES) DISCIPLINES = await api("/disciplines"); return DISCIPLINES; }
function disciplineOptions(list, withEmpty = true) {
  return [...(withEmpty ? [["", L("— Choose —", "— اختر —")]] : []), ...list.map(d => [d.id, nm(d)])];
}
const ORG_TYPES = { engineering_consultancy: ["Engineering consultancy", "مكتب استشارات هندسية"], engineering_firm: ["Engineering firm", "شركة هندسية"],
  contractor: ["Contractor", "مقاول"], developer: ["Developer", "مطور عقاري"], government: ["Government entity", "جهة حكومية"], other: ["Other", "أخرى"] };

function verificationPanel(status, path, history, { canSubmit, extraHint }) {
  const msgs = {
    unverified: L("Not verified yet. Complete the profile and submit your documents.", "لم يتم التوثيق بعد. أكمل الملف وأرسل المستندات."),
    pending: L("Your documents are with the BUNYAH team. You'll get a notification when they decide.", "مستنداتك لدى فريق بُنية، وسيصلك إشعار عند البت."),
    needs_info: L("The BUNYAH team needs more information – see their note below and submit again.", "يحتاج فريق بُنية معلومات إضافية – راجع الملاحظة أدناه وأعد الإرسال."),
    verified: L("Verified. Changing your legal or registration details will require a new check.", "تم التوثيق. تغيير البيانات القانونية أو بيانات التسجيل يتطلب تحققًا جديدًا."),
    rejected: L("Verification was not approved – see the reason below. You can submit again.", "لم تتم الموافقة على التوثيق – راجع السبب أدناه. يمكنك إعادة الإرسال."),
  };
  const box = errorBox();
  const files = h("input", { type: "file", name: "documents", multiple: true, required: true, accept: ".pdf,.jpg,.jpeg,.png" });
  const form = h("form", { class: "stack-sm" }, box,
    field(L("Verification documents", "مستندات التوثيق"), files, { hint: L("PDF, JPG or PNG – up to 5 files. Only the BUNYAH team can open them; they are never public.", "PDF أو JPG أو PNG – حتى 5 ملفات. لا يطّلع عليها إلا فريق بُنية ولا تُنشر أبدًا.") + (extraHint ? " " + extraHint : "") }),
    field(L("Note for the reviewer (optional)", "ملاحظة للمراجع (اختياري)"), txt("note", { rows: 2 })),
    h("button", { class: "btn", type: "submit" }, L("Submit for verification", "إرسال للتوثيق")));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault(); box.classList.add("hidden");
    try { await api(path, { method: "POST", form: new FormData(form) }); toast(L("Submitted for verification.", "تم الإرسال للتوثيق.")); B.render(); }
    catch (err) { showError(box, err); }
  });
  return h("div", { class: "stack" },
    card(L("Verification status", "حالة التوثيق"), h("p", {}, badge(status)), h("p", { class: "muted" }, msgs[status] || ""),
      canSubmit && ["unverified", "needs_info", "rejected"].includes(status) ? form : null,
      !canSubmit && status !== "verified" ? h("p", { class: "muted small" }, L("Only the organization owner can submit verification.", "مالك الجهة فقط يمكنه إرسال طلب التوثيق.")) : null),
    history.length ? card(L("Verification history", "سجل التوثيق"), table([
      { label: L("Submitted", "تاريخ الإرسال"), render: v => fmtDate(v.created_at) },
      { label: L("Status", "الحالة"), render: v => badge(v.status) },
      { label: L("Reviewer note", "ملاحظة المراجع"), render: v => v.reviewer_note || "—" },
      { label: L("Documents", "المستندات"), render: v => v.documents.map(f => h("div", {}, fileLink(f))) },
    ], history)) : null);
}

/* ---------- organization ---------- */
B.views.organization = async function (params, q) {
  const tab = q.get("tab") || "profile";
  const org = await api("/organizations/me");
  const canEdit = org.my_role === "owner";
  const head = pageHead(L(org.name, org.name_ar || org.name), L("Organization profile and team", "ملف الجهة والفريق"), badge(org.verification_status));
  const t = tabs([["profile", L("Profile", "الملف")], ["team", L("Team & roles", "الفريق والأدوار")], ["verification", L("Verification", "التوثيق")]], tab, "/organization");
  let body;
  if (tab === "team") body = await orgTeam();
  else if (tab === "verification") body = verificationPanel(org.verification_status, "/organizations/me/verification", await api("/verification/mine"), { canSubmit: canEdit });
  else {
    const box = errorBox();
    const f = (name, label, opts = {}) => field(label, (opts.area ? txt : inp)(name, { value: org[name] || "", disabled: !canEdit, ...(opts.attrs || {}) }), opts);
    body = onSubmit(h("form", { class: "card" }, box,
      !canEdit ? notice("info", L("Only the owner can edit the organization profile.", "مالك الجهة فقط يمكنه تعديل الملف.")) : null,
      h("fieldset", {}, h("legend", {}, L("Identity", "الهوية")), h("div", { class: "form-grid" },
        f("name", L("Organization name (English)", "اسم الجهة (بالإنجليزية)"), { required: true }), f("name_ar", L("Organization name (Arabic)", "اسم الجهة (بالعربية)")),
        field(L("Organization type", "نوع الجهة"), sel("org_type", Object.entries(ORG_TYPES).map(([k, v]) => [k, L(...v)]), org.org_type, { disabled: !canEdit })),
        f("cr_number", L("Commercial registration (CR) number", "رقم السجل التجاري"), { hint: L("Use a fictional value in this prototype.", "استخدم قيمة وهمية في هذا النموذج.") }),
        f("license_info", L("Licence / classification details", "بيانات الترخيص أو التصنيف"), { full: true }))),
      h("fieldset", {}, h("legend", {}, L("Location & contact (private)", "الموقع والتواصل (خاص)")), h("div", { class: "form-grid" },
        f("city", L("City", "المدينة")), f("address", L("Address", "العنوان")),
        f("contact_email", L("Contact e-mail", "بريد التواصل"), { attrs: { type: "email", dir: "ltr" } }), f("contact_phone", L("Contact phone", "هاتف التواصل"), { attrs: { dir: "ltr" } }),
        f("representative_name", L("Authorized representative", "الممثل المفوض")), f("representative_title", L("Representative's title", "منصب الممثل")))),
      h("fieldset", {}, h("legend", {}, L("Public description", "الوصف العام")),
        f("description", L("About the organization", "نبذة عن الجهة"), { area: true }), f("website", L("Website", "الموقع الإلكتروني"), { attrs: { dir: "ltr", placeholder: "https://" } })),
      canEdit ? h("button", { class: "btn", type: "submit" }, L("Save profile", "حفظ الملف")) : null),
    async (d) => { await api("/organizations/me", { method: "PATCH", body: d }); toast(L("Profile saved.", "تم حفظ الملف.")); B.render(); });
    if (canEdit) body = h("div", { class: "stack" }, body, card(L("Logo", "الشعار"),
      org.logo_file_id ? h("img", { src: `${API}/files/${org.logo_file_id}?inline=true`, alt: L("Current logo", "الشعار الحالي"), style: "max-height:72px" }) : h("p", { class: "muted" }, L("No logo yet.", "لا يوجد شعار.")),
      uploadForm("/organizations/me/logo", { label: L("Logo image", "صورة الشعار"), accept: ".png,.jpg,.jpeg" })));
  }
  return h("div", {}, head, t, body);
};

async function orgTeam() {
  const t = await api("/organizations/me/members");
  const rows = table([
    { label: L("Name", "الاسم"), render: m => [m.name, m.is_me ? h("span", { class: "muted small" }, L(" (you)", " (أنت)")) : null] },
    t.can_manage ? { label: L("E-mail", "البريد"), render: m => h("span", { class: "ltr" }, m.email) } : null,
    { label: L("Role", "الدور"), render: m => t.can_manage && !m.is_me ? sel("r", Object.keys(ORG_ROLES).map(k => [k, orgRole(k)]), m.org_role, { "aria-label": L("Role", "الدور"), onchange: async (e) => {
      try { await api(`/organizations/me/members/${m.id}`, { method: "PATCH", body: { org_role: e.target.value } }); toast(L("Role updated.", "تم تحديث الدور.")); }
      catch (err) { toast(err.message, true); B.render(); } } }) : orgRole(m.org_role) },
    { label: L("Status", "الحالة"), render: m => badge(m.is_active ? "active" : "closed", m.is_active ? L("Active", "نشط") : L("Deactivated", "موقوف")) },
    t.can_manage ? { label: "", render: m => m.is_me ? "" : action(m.is_active ? L("Deactivate", "إيقاف") : L("Reactivate", "تفعيل"), () => api(`/organizations/me/members/${m.id}`, { method: "PATCH", body: { is_active: !m.is_active } }), { cls: "btn secondary small", confirm: m.is_active ? L(`Deactivate ${m.name}? They will lose access immediately.`, `إيقاف ${m.name}؟ سيفقد الوصول فورًا.`) : null }) } : null,
  ].filter(Boolean), t.members);
  const perms = h("details", { class: "card flat" }, h("summary", {}, L("What each role can do", "صلاحيات كل دور")),
    h("ul", {}, [["owner", L("Everything, including team, organization profile, signing contracts and recording payments.", "كل الصلاحيات، بما فيها الفريق والملف وتوقيع العقود وتسجيل المدفوعات.")],
      ["project_manager", L("Publish and manage projects and requests, evaluate and select, approve milestones and billing periods.", "نشر وإدارة المشاريع والطلبات، التقييم والاختيار، اعتماد المراحل وفترات الفوترة.")],
      ["technical_reviewer", L("Review deliverables (approve versions or request revisions) and add technical reviews.", "مراجعة التسليمات (اعتماد النسخ أو طلب تعديل) وإضافة المراجعات الفنية.")],
      ["finance", L("View financial records and record simulated payments.", "عرض السجلات المالية وتسجيل المدفوعات التجريبية.")],
      ["viewer", L("Read-only access.", "اطلاع فقط.")]].map(([r, d]) => h("li", {}, h("strong", {}, orgRole(r) + ": "), d))));
  let inviteCard = null;
  if (t.can_manage) {
    const box = errorBox(); const result = h("div");
    inviteCard = card(L("Invite a team member", "دعوة عضو للفريق"),
      onSubmit(h("form", { class: "form-grid" }, h("div", { class: "full" }, box),
        field(L("E-mail", "البريد الإلكتروني"), inp("email", { type: "email", dir: "ltr" }), { required: true }),
        field(L("Name", "الاسم"), inp("name")),
        field(L("Role", "الدور"), sel("org_role", Object.keys(ORG_ROLES).filter(k => k !== "owner").map(k => [k, orgRole(k)]).concat([["owner", orgRole("owner")]]), "project_manager")),
        h("div", { class: "full" }, h("button", { class: "btn", type: "submit" }, L("Create invitation link", "إنشاء رابط الدعوة")))),
      async (d) => {
        const r = await api("/organizations/me/invitations", { method: "POST", body: d });
        result.replaceChildren(notice("success", h("p", {}, L("Invitation created. E-mail sending is not set up in the prototype, so copy this one-time link and share it with your colleague (valid 7 days):", "تم إنشاء الدعوة. إرسال البريد غير مفعّل في النموذج، فانسخ هذا الرابط لمرة واحدة وشاركه مع زميلك (صالح 7 أيام):")),
          h("input", { type: "text", readonly: true, value: r.link, dir: "ltr", onfocus: e => e.target.select(), "aria-label": L("Invitation link", "رابط الدعوة") })));
      }), result,
      t.invitations.length ? h("div", {}, h("h3", { class: "section-title" }, L("Open invitations", "دعوات مفتوحة")), table([
        { label: L("E-mail", "البريد"), render: i => h("span", { class: "ltr" }, i.email) }, { label: L("Role", "الدور"), render: i => orgRole(i.org_role) },
        { label: L("Expires", "تنتهي"), render: i => fmtDate(i.expires_at) },
        { label: "", render: i => action(L("Revoke", "إلغاء"), () => api(`/organizations/me/invitations/${i.id}`, { method: "DELETE" }), { cls: "btn secondary small" }) }], t.invitations)) : null);
  }
  return h("div", { class: "stack" }, card(L("Team members", "أعضاء الفريق"), rows), inviteCard, perms);
}

/* ---------- engineer profile ---------- */
B.views.profile = async function (params, q) {
  const tab = q.get("tab") || "profile";
  const [p, disc] = await Promise.all([api("/engineers/me"), disciplines()]);
  const head = pageHead(p.name, L("Your professional profile – this is what organizations see.", "ملفك المهني – هذا ما تراه الجهات."), badge(p.verification_status), linkBtn("/engineers/" + p.id, L("View public profile", "عرض الملف العام"), "btn secondary"));
  const t = tabs([["profile", L("Profile", "الملف")], ["documents", L("CV & portfolio", "السيرة والمعرض")], ["verification", L("Verification", "التوثيق")]], tab, "/profile");
  let body;
  if (tab === "verification") body = verificationPanel(p.verification_status, "/engineers/me/verification", await api("/verification/mine"), { canSubmit: true, extraHint: L("For example: degree, professional registration, ID (fictional in this prototype).", "مثل: المؤهل، التسجيل المهني، الهوية (وهمية في هذا النموذج).") });
  else if (tab === "documents") {
    body = h("div", { class: "grid grid-2", style: "align-items:start" },
      card(L("CV", "السيرة الذاتية"), p.has_cv ? h("p", {}, fileLink({ id: p.cv_file_id, filename: "CV" }, L("Download current CV", "تنزيل السيرة الحالية"))) : h("p", { class: "muted" }, L("No CV uploaded.", "لم يتم رفع سيرة ذاتية.")),
        h("p", { class: "muted small" }, L("Organizations can open your CV only after you send them a proposal or an application.", "لا تطّلع الجهات على سيرتك إلا بعد أن ترسل لها عرضًا أو طلب تقديم.")),
        uploadForm("/engineers/me/cv", { label: L("CV (PDF or DOCX)", "السيرة (PDF أو DOCX)"), accept: ".pdf,.docx" })),
      card(L("Portfolio", "معرض الأعمال"),
        p.portfolio.length ? h("ul", { class: "list" }, p.portfolio.map(i => h("li", {}, h("div", { class: "row between" }, h("strong", {}, i.title),
          action(L("Remove", "إزالة"), () => api(`/engineers/me/portfolio/${i.id}`, { method: "DELETE" }), { cls: "btn ghost small", confirm: L(`Remove "${i.title}" from your portfolio?`, `إزالة «${i.title}» من المعرض؟`) })),
          i.description ? h("p", { class: "muted small" }, i.description) : null, i.image_file_id ? fileLink({ id: i.image_file_id, filename: "file" }, L("Attachment", "المرفق")) : null))) : h("p", { class: "muted" }, L("No portfolio items yet.", "لا توجد أعمال بعد.")),
        h("h3", { class: "section-title" }, L("Add an item", "إضافة عمل")),
        uploadForm("/engineers/me/portfolio", { optional: true, label: L("Supporting file (optional)", "ملف داعم (اختياري)"), button: L("Add to portfolio", "إضافة للمعرض"), extra: [
          field(L("Title", "العنوان"), inp("title"), { required: true }), field(L("Description", "الوصف"), txt("description", { rows: 2 })),
          field(L("Link (optional)", "رابط (اختياري)"), inp("link", { dir: "ltr", placeholder: "https://" }))] })));
  } else {
    const box = errorBox();
    const f = (name, label, opts = {}) => field(label, (opts.area ? txt : inp)(name, { value: p[name] ?? "", ...(opts.attrs || {}) }), opts);
    body = onSubmit(h("form", { class: "card" }, box,
      h("fieldset", {}, h("legend", {}, L("Professional summary", "الملخص المهني")), h("div", { class: "form-grid" },
        f("title", L("Professional title", "المسمى المهني"), { required: true }),
        field(L("Engineering discipline", "التخصص الهندسي"), sel("discipline_id", disciplineOptions(disc), p.discipline?.id, { "data-type": "int" }), { required: true }),
        f("specializations", L("Specializations", "التخصصات الدقيقة"), { full: true }),
        f("years_experience", L("Years of experience", "سنوات الخبرة"), { attrs: { type: "number", min: 0, max: 60, "data-type": "int" } }),
        f("city", L("City", "المدينة")),
        f("bio", L("Professional biography", "نبذة مهنية"), { area: true, full: true }))),
      h("fieldset", {}, h("legend", {}, L("Qualifications", "المؤهلات")), h("div", { class: "form-grid" },
        f("education", L("Education", "التعليم"), { area: true }), f("qualifications", L("Professional qualifications", "المؤهلات المهنية"), { area: true }),
        f("certifications", L("Certifications", "الشهادات"), { area: true }), f("software_skills", L("Software skills", "البرامج"), { area: true }),
        f("registration_body", L("Professional registration body", "جهة التسجيل المهني")),
        f("registration_number", L("Registration number (private)", "رقم التسجيل (خاص)"), { hint: L("Shown only to BUNYAH administrators.", "يظهر لإدارة بُنية فقط."), attrs: { dir: "ltr" } }),
        f("languages", L("Languages", "اللغات")))),
      h("fieldset", {}, h("legend", {}, L("Availability & preferences", "التوفر والتفضيلات")), h("div", { class: "form-grid" },
        field(L("Availability", "التوفر"), sel("availability", [["available", L("Available", "متاح")], ["partial", L("Partly available", "متاح جزئيًا")], ["unavailable", L("Not available", "غير متاح")]], p.availability)),
        field(L("Work preference", "تفضيل العمل"), sel("work_preference", Object.keys(WORK_MODES).map(k => [k, workMode(k)]), p.work_preference)),
        field(L("Expected daily rate – from (SAR)", "الأجر اليومي المتوقع – من (ريال)"), moneyInput("rate_min_cents", p.rate_min_cents)),
        field(L("Expected daily rate – to (SAR)", "الأجر اليومي المتوقع – إلى (ريال)"), moneyInput("rate_max_cents", p.rate_max_cents)))),
      h("button", { class: "btn", type: "submit" }, L("Save profile", "حفظ الملف"))),
    async (d) => { await api("/engineers/me", { method: "PATCH", body: d }); toast(L("Profile saved.", "تم حفظ الملف.")); B.render(); });
  }
  return h("div", {}, head, t, body);
};

/* ---------- account ---------- */
B.views.account = async function () {
  const me = S.me;
  const box1 = errorBox(), box2 = errorBox();
  const hij = h("input", { type: "checkbox", checked: S.hijri, onchange: (e) => { S.hijri = e.target.checked; savePref("bunyah.hijri", S.hijri ? "1" : "0"); toast(L("Saved.", "تم الحفظ.")); } });
  return h("div", {}, pageHead(L("Account settings", "إعدادات الحساب"), h("span", { class: "ltr" }, me.email)),
    h("div", { class: "grid grid-2", style: "align-items:start" },
      onSubmit(h("form", { class: "card" }, h("h2", {}, L("Personal details", "البيانات الشخصية")), box1,
        field(L("Full name", "الاسم الكامل"), inp("name", { value: me.name }), { required: true, hint: L("Used when you sign contracts.", "يُستخدم عند توقيع العقود.") }),
        field(L("Phone (private)", "الهاتف (خاص)"), inp("phone", { value: me.phone, dir: "ltr" }), { hint: L("Never shown publicly.", "لا يظهر للعامة أبدًا.") }),
        field(L("Language", "اللغة"), sel("locale", [["ar", "العربية"], ["en", "English"]], me.locale)),
        h("button", { class: "btn", type: "submit" }, L("Save", "حفظ"))),
      async (d) => { S.me = await api("/auth/me", { method: "PATCH", body: d }); if (d.locale !== S.lang) setLang(d.locale); else { toast(L("Saved.", "تم الحفظ.")); B.renderChrome(); } }),
      h("div", { class: "stack" },
        card(L("Dates", "التواريخ"), h("label", { class: "check" }, hij, h("span", {}, L("Also show Hijri (Umm al-Qura) dates next to Gregorian dates", "إظهار التاريخ الهجري (أم القرى) بجانب الميلادي")))),
        onSubmit(h("form", { class: "card" }, h("h2", {}, L("Change password", "تغيير كلمة المرور")), box2,
          field(L("Current password", "كلمة المرور الحالية"), inp("current_password", { type: "password", autocomplete: "current-password", dir: "ltr" }), { required: true }),
          field(L("New password", "كلمة المرور الجديدة"), inp("new_password", { type: "password", autocomplete: "new-password", minlength: 10, dir: "ltr" }), { required: true, hint: L("At least 10 characters.", "10 أحرف على الأقل.") }),
          h("button", { class: "btn", type: "submit" }, L("Change password", "تغيير كلمة المرور"))),
        async (d, fd) => { await api("/auth/password", { method: "POST", body: d }); toast(L("Password changed.", "تم تغيير كلمة المرور.")); B.render(); void fd; }))));
};

/* ---------- public profiles & search ---------- */
B.views.engineer = async function ([id]) {
  const e = await api("/engineers/" + id);
  const contact = S.me.organization && S.me.permissions.includes("messages.send") ? action(L("Send a message", "إرسال رسالة"), async () => { const c = await api("/conversations", { method: "POST", body: { user_id: e.id } }); go("/messages/" + c.id); }, { cls: "btn secondary" }) : null;
  return h("div", {}, pageHead(e.name, [e.title, e.discipline ? " · " + nm(e.discipline) : ""].join(""), e.verified ? badge("verified") : badge("unverified"), contact),
    h("div", { class: "layout-side" },
      h("div", { class: "stack" },
        card(L("About", "نبذة"), h("p", { class: "prewrap" }, e.bio || "—"), kv([
          [L("Specializations", "التخصصات الدقيقة"), e.specializations], [L("Experience", "الخبرة"), L(`${e.years_experience} years`, `${e.years_experience} سنة`)],
          [L("Education", "التعليم"), e.education], [L("Qualifications", "المؤهلات"), e.qualifications], [L("Certifications", "الشهادات"), e.certifications],
          [L("Professional registration", "التسجيل المهني"), e.has_registration ? (e.registration_body || L("Provided", "متوفر")) + L(" (number visible to BUNYAH only)", " (الرقم لدى بُنية فقط)") : "—"],
          [L("Software", "البرامج"), e.software_skills], [L("Languages", "اللغات"), e.languages]])),
        card(L("Portfolio", "معرض الأعمال"), e.portfolio.length ? h("ul", { class: "list" }, e.portfolio.map(i => h("li", {}, h("strong", {}, i.title), h("p", { class: "muted small" }, i.description), safeUrl(i.link) ? h("a", { href: i.link, target: "_blank", rel: "noopener noreferrer nofollow" }, i.link) : null))) : h("p", { class: "muted" }, L("No portfolio items.", "لا توجد أعمال."))),
        card(L("Ratings from organizations", "تقييمات الجهات"), e.reviews.length ? h("ul", { class: "list" }, e.reviews.map(r => h("li", {}, stars(r.rating), " ", h("strong", {}, r.org_name), h("p", { class: "small" }, r.text), h("span", { class: "muted small" }, fmtDate(r.created_at))))) : h("p", { class: "muted" }, L("No ratings yet.", "لا توجد تقييمات بعد.")))),
      card(L("Summary", "ملخص"), kv([[L("City", "المدينة"), e.city], [L("Availability", "التوفر"), { available: L("Available", "متاح"), partial: L("Partly available", "متاح جزئيًا"), unavailable: L("Not available", "غير متاح") }[e.availability]], [L("Prefers", "يفضّل"), workMode(e.work_preference)],
        [L("Daily rate", "الأجر اليومي"), e.rate_min_cents ? [money(e.rate_min_cents), " – ", money(e.rate_max_cents)] : "—"],
        [L("Rating", "التقييم"), e.average_rating ? [stars(e.average_rating), ` (${e.rating_count})`] : "—"], [L("Completed engagements", "أعمال منجزة"), e.completed_engagements],
        [L("CV", "السيرة"), e.has_cv ? L("Available to organizations it applied to", "متاحة للجهات التي تقدّم إليها") : "—"]]))));
};

B.views.org = async function ([id]) {
  const o = await api("/organizations/" + id);
  return h("div", {}, pageHead(L(o.name, o.name_ar || o.name), [ORG_TYPES[o.org_type] ? L(...ORG_TYPES[o.org_type]) : "", o.city ? " · " + o.city : ""].join(""), o.verified ? badge("verified") : badge(o.verification_status)),
    card(null, h("p", { class: "prewrap" }, o.description || "—"), kv([[L("Projects published", "المشاريع المنشورة"), o.projects_posted],
      [L("Rating from engineers", "تقييم المهندسين"), o.average_rating ? [stars(o.average_rating), ` (${o.rating_count})`] : "—"],
      [L("Website", "الموقع"), safeUrl(o.website) ? h("a", { href: o.website, target: "_blank", rel: "noopener noreferrer nofollow", dir: "ltr" }, o.website) : "—"]])));
};

B.views.engineers = async function (params, q) {
  const disc = await disciplines();
  const res = await api("/engineers?" + new URLSearchParams(strip({ q: q.get("q"), discipline_id: q.get("discipline_id"), city: q.get("city"), availability: q.get("availability"), verified_only: q.get("verified_only") })));
  const form = h("form", { class: "filters card flat" },
    field(L("Search", "بحث"), inp("q", { type: "search", value: q.get("q") || "", placeholder: L("Name, title, skill…", "الاسم، المسمى، المهارة…") })),
    field(L("Discipline", "التخصص"), sel("discipline_id", [["", L("All", "الكل")], ...disc.map(d => [d.id, nm(d)])], q.get("discipline_id"))),
    field(L("City", "المدينة"), inp("city", { value: q.get("city") || "" })),
    field(L("Availability", "التوفر"), sel("availability", [["", L("Any", "الكل")], ["available", L("Available", "متاح")], ["partial", L("Partly", "جزئيًا")]], q.get("availability"))),
    h("div", { class: "field" }, h("label", { class: "check" }, h("input", { type: "checkbox", name: "verified_only", checked: q.get("verified_only") === "true" }), L("Verified only", "الموثّقون فقط")),
      h("button", { class: "btn", type: "submit" }, L("Search", "بحث"))));
  form.addEventListener("submit", (ev) => { ev.preventDefault(); const d = readForm(form); go("/engineers?" + new URLSearchParams(strip({ ...d, verified_only: d.verified_only ? "true" : "" }))); });
  return h("div", {}, pageHead(L("Find engineers", "البحث عن مهندسين"), L(`${res.total} engineers`, `${res.total} مهندس`)), form,
    res.data.length ? h("div", { class: "grid grid-3" }, res.data.map(e => h("a", { class: "item-card", href: "#/engineers/" + e.id },
      h("div", { class: "row between" }, h("h3", {}, e.name), e.verified ? badge("verified") : null),
      h("p", { class: "muted small", style: "margin:0" }, e.title, e.discipline ? " · " + nm(e.discipline) : ""),
      h("div", { class: "meta", style: "margin-top:.5rem" }, h("span", {}, e.city || "—"), h("span", {}, L(`${e.years_experience} yrs`, `${e.years_experience} سنة`)),
        e.average_rating ? h("span", {}, stars(e.average_rating)) : null, e.rate_min_cents ? h("span", {}, money(e.rate_min_cents), "+ ", L("/day", "/يوم")) : null))))
      : empty(L("No engineers match these filters", "لا يوجد مهندسون مطابقون"), L("Try removing a filter.", "جرّب إزالة أحد عوامل التصفية.")));
};
