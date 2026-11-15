/* Administrator console. Every sensitive action here is recorded in the audit log by the server. */
"use strict";

B.views.admin = async function (params, q) {
  if (!S.me.is_admin) throw new ApiErr(403, "FORBIDDEN", L("Administrators only.", "للإدارة فقط."));
  const tab = q.get("tab") || "overview";
  const items = [["overview", L("Overview", "نظرة عامة")], ["verifications", L("Verification", "التوثيق")], ["requests", L("Request review", "مراجعة الطلبات")],
    ["users", L("Users", "المستخدمون")], ["projects", L("Projects", "المشاريع")], ["contracts", L("Contracts & applications", "العقود والطلبات")],
    ["disputes", L("Disputes", "النزاعات")], ["escalations", L("Escalations", "التصعيد")], ["finance", L("Finance (demo)", "المالية (تجريبي)")],
    ["fees", L("Platform fees", "رسوم المنصة")], ["settings", L("Settings", "الإعدادات")], ["disciplines", L("Disciplines", "التخصصات")],
    ["calendar", L("Holidays", "العطل")], ["notify", L("Announcements", "الإعلانات")], ["audit", L("Audit log", "سجل التدقيق")]];
  const views = { overview: admOverview, verifications: admVerifications, requests: admRequests, users: admUsers, projects: admProjects, contracts: admContracts,
    disputes: () => B.views.disputes(), escalations: admEscalations, finance: admFinance, fees: admFees, settings: admSettings, disciplines: admDisciplines,
    calendar: admCalendar, notify: admNotify, audit: admAudit };
  const body = await (views[tab] || admOverview)(q);
  return h("div", {}, pageHead(L("BUNYAH administration", "إدارة بُنية"), L("Platform operations – prototype", "تشغيل المنصة – نموذج تجريبي")), tabs(items, tab, "/admin"), body);
};

const countMap = (obj) => Object.entries(obj || {}).map(([k, v]) => h("li", { class: "row between" }, badge(k), h("strong", { class: "num" }, v)));

async function admOverview() {
  const o = await api("/admin/overview");
  const f = o.simulated_finance;
  return h("div", { class: "stack" },
    h("div", { class: "grid grid-4" },
      stat(L("Verification requests waiting", "طلبات توثيق بانتظار البت"), o.verifications_pending), stat(L("Service requests to review", "طلبات خدمة للمراجعة"), o.requests_waiting_review),
      stat(L("Active disputes", "نزاعات نشطة"), o.disputes_active, o.disputes_overdue ? L(`${o.disputes_overdue} past target date`, `${o.disputes_overdue} تجاوزت الموعد`) : null),
      stat(L("Open escalations", "تصعيدات مفتوحة"), o.escalations_open),
      stat(L("Proposals (Model A)", "العروض (النموذج أ)"), o.proposals_total), stat(L("Applications (Model B)", "طلبات التقديم (النموذج ب)"), o.applications_total),
      stat(L("Contracts (Model B)", "العقود (النموذج ب)"), o.contracts_total), stat(L("Average engineer rating", "متوسط تقييم المهندسين"), o.average_engineer_rating ? o.average_engineer_rating.toFixed(2) : "—")),
    card(null, h("div", { class: "row between" }, h("h2", { style: "margin:0" }, L("Simulated financial activity", "النشاط المالي التجريبي")), demoTag()),
      h("div", { class: "grid grid-4", style: "margin-top:.75rem" }, stat(L("Paid volume", "حجم المدفوع"), money(f.paid_volume_cents)), stat(L("Platform fees", "رسوم المنصة"), money(f.platform_fees_cents)),
        stat(L("Unpaid invoices", "فواتير غير مدفوعة"), f.invoices_unpaid), stat(L("Payouts pending", "تحويلات معلقة"), f.payouts_pending))),
    h("div", { class: "grid grid-3", style: "align-items:start" },
      card(L("Projects by status", "المشاريع حسب الحالة"), h("ul", { class: "list" }, countMap(o.projects_by_status))),
      card(L("Service requests by status", "طلبات الخدمة حسب الحالة"), h("ul", { class: "list" }, countMap(o.requests_by_status))),
      card(L("Accounts", "الحسابات"), h("ul", { class: "list" }, Object.entries(o.users_by_role).map(([k, v]) => h("li", { class: "row between" }, { organization: L("Organization users", "مستخدمو الجهات"), engineer: L("Engineers", "المهندسون"), admin: L("Administrators", "المدراء") }[k] || k, h("strong", {}, v)))),
        h("h3", { class: "section-title" }, L("Organizations", "الجهات")), h("ul", { class: "list" }, countMap(o.organizations_by_verification)),
        h("h3", { class: "section-title" }, L("Engineers", "المهندسون")), h("ul", { class: "list" }, countMap(o.engineers_by_verification)))),
    card(L("Activity by discipline", "النشاط حسب التخصص"), table([{ label: L("Discipline", "التخصص"), render: r => r.discipline ? nm(r.discipline) : L("Not set", "غير محدد") },
      { label: L("Projects", "المشاريع"), num: true, render: r => r.projects }, { label: L("Service requests", "طلبات الخدمة"), num: true, render: r => r.requests }], o.by_discipline)),
    card(L("Scheduled checks", "الفحوصات المجدولة"), h("p", { class: "muted small" }, L("Reminders, review-window escalations, closing expired proposal windows and near-expiry contracts. They run automatically; you can run them now. In demo mode you can simulate a later date to see escalations happen.",
      "التذكيرات وتصعيد مهل المراجعة وإغلاق مهل العروض المنتهية والعقود القريبة من الانتهاء. تعمل تلقائيًا، ويمكنك تشغيلها الآن. في الوضع التجريبي يمكنك محاكاة تاريخ لاحق لرؤية التصعيد.")),
      onSubmit(h("form", { class: "row", style: "align-items:flex-end" }, field(L("As of date (demo only, optional)", "بتاريخ (تجريبي، اختياري)"), inp("as_of", { type: "date", "data-type": "nullable" })), h("button", { class: "btn", type: "submit" }, L("Run checks now", "تشغيل الفحوصات الآن"))),
        async (d) => { const r = await api("/admin/checks/run", { method: "POST", body: d }); toast(L(`Done: ${r.reminders} reminders, ${r.escalations} escalations, ${r.closed_proposal_windows} proposal windows closed, ${r.near_expiry} contracts near expiry.`, `تم: ${r.reminders} تذكيرات، ${r.escalations} تصعيدات، ${r.closed_proposal_windows} مهل عروض مغلقة، ${r.near_expiry} عقود قرب الانتهاء.`)); B.render(); })));
}

async function admVerifications(q) {
  const status = q.get("status") ?? "pending";
  const list = await api("/admin/verifications?status=" + status);
  const filter = sel("st", [["pending", statusLabel("pending")], ["verified", statusLabel("verified")], ["rejected", statusLabel("rejected")], ["needs_info", statusLabel("needs_info")], ["", L("All", "الكل")]], status, { "aria-label": L("Filter", "تصفية"), onchange: e => go("/admin?tab=verifications&status=" + e.target.value) });
  const open = q.get("id") ? await api("/admin/verifications/" + q.get("id")) : null;
  return h("div", { class: "stack" }, h("div", { class: "row" }, h("label", {}, L("Show", "عرض")), filter),
    card(null, table([{ label: L("Applicant", "مقدم الطلب"), render: v => h("a", { href: `#/admin?tab=verifications&status=${status}&id=${v.id}` }, v.subject.name) },
      { label: L("Type", "النوع"), render: v => v.subject_type === "organization" ? L("Organization", "جهة") : L("Engineer", "مهندس") },
      { label: L("Submitted", "تاريخ الإرسال"), render: v => fmtDate(v.created_at) }, { label: L("Status", "الحالة"), render: v => badge(v.status) }], list, { empty: L("No verification requests here.", "لا توجد طلبات توثيق.") })),
    open ? verificationReview(open) : null);
}

function verificationReview(v) {
  const s = v.subject;
  const details = v.subject_type === "organization"
    ? kv([[L("Name", "الاسم"), s.name], [L("Type", "النوع"), s.org_type], [L("CR number", "السجل التجاري"), s.cr_number], [L("Licence", "الترخيص"), s.license_info], [L("City", "المدينة"), s.city],
      [L("Address", "العنوان"), s.address], [L("Representative", "الممثل"), [s.representative_name, s.representative_title ? " – " + s.representative_title : ""]], [L("Contact", "التواصل"), [s.contact_email, " ", s.contact_phone]]])
    : kv([[L("Name", "الاسم"), s.name], [L("E-mail", "البريد"), s.email], [L("Title", "المسمى"), s.title], [L("Discipline", "التخصص"), s.discipline ? nm(s.discipline) : "—"],
      [L("Experience", "الخبرة"), s.years_experience], [L("Registration", "التسجيل"), [s.registration_body, " · ", s.registration_number || "—"]], [L("Education", "التعليم"), s.education], [L("Qualifications", "المؤهلات"), s.qualifications]]);
  const decide = (decision, label, cls, needNote) => action(label, (note) => api(`/admin/verifications/${v.id}/decision`, { method: "POST", body: { decision, note: note || "" } }), {
    cls, prompt: { message: label + "?", input: "textarea", inputLabel: needNote ? L("Reason (sent to the applicant)", "السبب (يُرسل لمقدم الطلب)") : L("Note (optional)", "ملاحظة (اختياري)"), required: needNote, minLength: needNote ? 5 : 0, okLabel: label }, done: L("Decision saved.", "تم حفظ القرار.") });
  return card(L("Review verification request", "مراجعة طلب التوثيق"), details,
    v.applicant_note ? h("p", { class: "small" }, h("strong", {}, L("Applicant note: ", "ملاحظة مقدم الطلب: ")), v.applicant_note) : null,
    h("h3", { class: "section-title" }, L("Private documents", "المستندات الخاصة")), h("ul", {}, v.documents.map(f => h("li", {}, fileLink(f)))),
    v.status === "pending" ? h("div", { class: "btn-row" }, decide("approve", L("Approve", "اعتماد"), "btn", false), decide("needs_info", L("Ask for more information", "طلب معلومات إضافية"), "btn secondary", true), decide("reject", L("Reject", "رفض"), "btn danger", true))
      : h("p", {}, badge(v.status), " ", v.reviewer_note));
}

async function admRequests(q) {
  const list = await api("/admin/service-requests?status=" + (q.get("status") || "review"));
  const review = (r, decision, label, cls, needNote) => action(label, (note) => api(`/admin/service-requests/${r.id}/review`, { method: "POST", body: { decision, note: note || "" } }), {
    cls, prompt: { message: `${label}: ${r.title}`, input: "textarea", inputLabel: needNote ? L("What should the organization change?", "ما الذي يجب أن تعدله الجهة؟") : L("Note (optional)", "ملاحظة (اختياري)"), required: needNote, okLabel: label } });
  return h("div", { class: "stack" }, notice("info", L("Model B requests are reviewed before publication because short-term engagements may raise employment-like and duration questions (pending legal review D2/D6).",
    "تُراجع طلبات النموذج ب قبل النشر لأن الارتباطات قصيرة المدة قد تثير مسائل شبيهة بالتوظيف والمدة (بانتظار المراجعة القانونية D2/D6).")),
    card(null, table([{ label: L("Request", "الطلب"), render: r => [h("a", { href: "#/services/" + r.id }, r.title), h("div", { class: "muted small" }, nm(r.organization))] },
      { label: L("Duration", "المدة"), render: r => L(`${r.duration_working_days} working days`, `${r.duration_working_days} يوم عمل`) }, { label: L("Daily rate", "السعر اليومي"), num: true, render: r => money(r.daily_rate_cents) },
      { label: L("Status", "الحالة"), render: r => badge(r.status) },
      { label: "", render: r => h("div", { class: "btn-row" }, r.status === "submitted" ? action(L("Start review", "بدء المراجعة"), () => api(`/admin/service-requests/${r.id}/review`, { method: "POST", body: { decision: "start", note: "" } }), { cls: "btn secondary small" }) : null,
        review(r, "publish", L("Approve & publish", "الموافقة والنشر"), "btn small", false), review(r, "return", L("Return for changes", "إعادة للتعديل"), "btn secondary small", true)) }], list, { empty: L("No requests waiting for review.", "لا توجد طلبات بانتظار المراجعة.") })));
}

async function admUsers(q) {
  const res = await api("/admin/users?" + new URLSearchParams(strip({ q: q.get("q"), role: q.get("role") })));
  const form = h("form", { class: "filters card flat" }, field(L("Search", "بحث"), inp("q", { type: "search", value: q.get("q") || "" })),
    field(L("Account type", "نوع الحساب"), sel("role", [["", L("All", "الكل")], ["organization", L("Organization", "جهة")], ["engineer", L("Engineer", "مهندس")], ["admin", L("Administrator", "مدير")]], q.get("role"))), h("div"), h("div"),
    h("button", { class: "btn", type: "submit" }, L("Search", "بحث")));
  form.addEventListener("submit", (ev) => { ev.preventDefault(); go("/admin?" + new URLSearchParams(strip({ tab: "users", ...readForm(form) }))); });
  return h("div", { class: "stack" }, form, card(null, table([
    { label: L("Name", "الاسم"), render: u => [u.name, u.is_admin ? h("span", { class: "muted small" }, L(" (admin)", " (مدير)")) : null, h("div", { class: "muted small ltr" }, u.email)] },
    { label: L("Type", "النوع"), render: u => ({ organization: L("Organization", "جهة"), engineer: L("Engineer", "مهندس"), admin: L("Administrator", "مدير") }[u.role] || u.role) },
    { label: L("Organization / role", "الجهة / الدور"), render: u => u.organization ? [u.organization, " · ", orgRole(u.org_role)] : "—" },
    { label: L("Verification", "التوثيق"), render: u => u.verification_status ? badge(u.verification_status) : "—" },
    { label: L("Last login", "آخر دخول"), render: u => fmtTime(u.last_login_at) },
    { label: L("Status", "الحالة"), render: u => badge(u.is_active ? "active" : "closed", u.is_active ? L("Active", "نشط") : L("Suspended", "موقوف")) },
    { label: "", render: u => u.id === S.me.id ? "" : action(u.is_active ? L("Suspend", "إيقاف") : L("Reactivate", "تفعيل"), () => api(`/admin/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } }), { cls: u.is_active ? "btn danger small" : "btn secondary small", confirm: u.is_active ? L(`Suspend ${u.name}? They are logged out immediately.`, `إيقاف ${u.name}؟ سيتم تسجيل خروجه فورًا.`) : null }) }], res.data)));
}

async function admProjects(q) {
  const list = await api("/admin/projects?" + new URLSearchParams(strip({ status: q.get("status") })));
  return card(L("All projects (Model A)", "جميع المشاريع (النموذج أ)"), table([{ label: L("Project", "المشروع"), render: p => [h("a", { href: "#/projects/" + p.id }, p.title), h("div", { class: "muted small" }, nm(p.organization))] },
    { label: L("Engineer", "المهندس"), render: p => p.engineer ? p.engineer.name : "—" }, { label: L("Budget", "الميزانية"), num: true, render: p => money(p.max_budget_cents) },
    { label: L("Proposals", "العروض"), num: true, render: p => p.proposal_count }, { label: L("Status", "الحالة"), render: p => [badge(p.status), p.review_escalated ? h("div", {}, badge("cancelled", L("Escalated", "تم التصعيد"))) : null] }], list));
}

async function admContracts() {
  const [cs, apps, props] = await Promise.all([api("/admin/contracts"), api("/admin/applications"), api("/admin/proposals")]);
  return h("div", { class: "stack" },
    card(L("Contracts (Model B)", "العقود (النموذج ب)"), table([{ label: L("Request", "الطلب"), render: c => [h("a", { href: "#/services/" + c.request_id }, c.title), h("div", { class: "muted small" }, c.organization)] },
      { label: L("Engineer", "المهندس"), render: c => c.engineer.name }, { label: L("Period", "المدة"), render: c => [fmtDate(c.start_date), " – ", fmtDate(c.end_date)] },
      { label: L("Daily rate", "السعر اليومي"), num: true, render: c => money(c.daily_rate_cents) }, { label: L("Billing", "الفوترة"), render: c => L(`${c.periods_approved} approved · ${c.periods_submitted} waiting`, `${c.periods_approved} معتمدة · ${c.periods_submitted} بانتظار`) },
      { label: L("Status", "الحالة"), render: c => badge(c.status) }], cs)),
    card(L("Applications (Model B)", "طلبات التقديم (النموذج ب)"), table([{ label: L("Request", "الطلب"), render: a => a.request_title }, { label: L("Engineer", "المهندس"), render: a => a.engineer.name },
      { label: L("Daily rate", "السعر اليومي"), num: true, render: a => money(a.proposed_daily_rate_cents) }, { label: L("Status", "الحالة"), render: a => badge(a.status) }, { label: L("Date", "التاريخ"), render: a => fmtDate(a.created_at) }], apps)),
    card(L("Proposals (Model A)", "العروض (النموذج أ)"), table([{ label: L("Project", "المشروع"), render: o => o.project_title }, { label: L("Engineer", "المهندس"), render: o => o.engineer.name },
      { label: L("Price", "السعر"), num: true, render: o => money(o.price_cents) }, { label: L("Status", "الحالة"), render: o => badge(o.status) }, { label: L("Date", "التاريخ"), render: o => fmtDate(o.created_at) }], props)));
}

async function admEscalations() {
  const list = await api("/admin/escalations");
  return h("div", { class: "stack" }, notice("info", L("An escalation opens when an organization does not review deliverables or a billing period within the review window. Nothing is approved automatically: follow up with the parties, then record what was done.",
    "يُفتح التصعيد عندما لا تراجع الجهة التسليمات أو فترة الفوترة ضمن المهلة. لا يتم أي اعتماد تلقائي: تابع مع الأطراف ثم سجّل ما تم.")),
    card(null, table([{ label: L("Item", "العنصر"), render: e => h("a", { href: "#" + e.link }, e.title) }, { label: L("Type", "النوع"), render: e => e.kind === "deliverable_review" ? L("Deliverable review (Model A)", "مراجعة تسليم (النموذج أ)") : L("Billing period review (Model B)", "مراجعة فترة فوترة (النموذج ب)") },
      { label: L("Details", "التفاصيل"), render: e => e.note }, { label: L("Opened", "تاريخ الفتح"), render: e => fmtTime(e.created_at) },
      { label: "", render: e => action(L("Mark followed up", "تسجيل المتابعة"), (note) => api(`/admin/escalations/${e.id}/resolve`, { method: "POST", body: { note } }), { cls: "btn secondary small", prompt: { message: L("What follow-up was done?", "ما المتابعة التي تمت؟"), input: "textarea", inputLabel: L("Follow-up note", "ملاحظة المتابعة"), required: true, minLength: 5, okLabel: L("Save", "حفظ") } }) }], list, { empty: L("No open escalations.", "لا توجد تصعيدات مفتوحة.") })));
}

async function admFinance() {
  const f = await api("/admin/finance");
  return h("div", { class: "stack" }, notice("warning", L("All records are simulated. Refunds can be recorded only for paid invoices and, if there is a dispute, only after a decision has been recorded.", "جميع السجلات تجريبية. يمكن تسجيل الاسترداد للفواتير المدفوعة فقط، وفي حال وجود نزاع بعد تسجيل القرار فقط.")),
    card(null, h("div", { class: "row between" }, h("h2", { style: "margin:0" }, L("Payout records", "سجلات التحويل")), demoTag()), table([
      { label: L("Reference", "المرجع"), render: t => h("span", { class: "ltr" }, t.ref) }, { label: L("Engineer", "المهندس"), render: t => t.engineer_name }, { label: L("Organization", "الجهة"), render: t => t.org_name },
      { label: L("Net to engineer", "صافي المهندس"), num: true, render: t => money(t.engineer_net_cents) }, { label: L("Status", "الحالة"), render: t => badge(t.status === "completed" ? "done" : t.status) },
      { label: "", render: t => t.status === "pending" ? action(L("Mark simulated payout sent", "تأكيد التحويل التجريبي"), () => api(`/admin/payouts/${t.id}/mark-sent`, { method: "POST" }), { cls: "btn small", confirm: L(`Record that the simulated payout ${t.ref} was sent? No real money moves.`, `تسجيل إرسال التحويل التجريبي ${t.ref}؟ لا تتم حركة مالية حقيقية.`) }) : "" }], f.transactions.filter(t => t.kind === "payout"))),
    card(null, h("div", { class: "row between" }, h("h2", { style: "margin:0" }, L("Invoices", "الفواتير")), demoTag()), table([
      { label: L("Invoice", "الفاتورة"), render: i => [h("span", { class: "ltr" }, i.number), h("div", { class: "muted small" }, i.description)] }, { label: L("Organization", "الجهة"), render: i => i.org_name },
      { label: L("Total", "الإجمالي"), num: true, render: i => money(i.total_cents) }, { label: L("Fees", "الرسوم"), num: true, render: i => money(i.org_fee_cents + i.engineer_fee_cents) }, { label: L("Status", "الحالة"), render: i => badge(i.status) },
      { label: "", render: i => i.status === "paid" ? action(L("Record simulated refund", "تسجيل استرداد تجريبي"), (reason) => api(`/admin/invoices/${i.id}/refund`, { method: "POST", body: { reason } }), { cls: "btn danger small", prompt: { message: L(`Refund ${i.number} (simulated)?`, `استرداد ${i.number} (تجريبي)؟`), input: "textarea", inputLabel: L("Reason", "السبب"), required: true, minLength: 10, okLabel: L("Record refund", "تسجيل الاسترداد") } }) : "" }], f.invoices)));
}

async function admFees() {
  const rules = await api("/admin/fee-rules");
  const box = errorBox();
  const valueHint = L("Percent: write 2.5 for 2.5%. Fixed: amount in SAR per invoice.", "النسبة: اكتب 2.5 تعني 2.5%. الثابت: مبلغ بالريال لكل فاتورة.");
  const form = onSubmit(h("form", { class: "card" }, h("h2", {}, L("New fee rule", "قاعدة رسوم جديدة")), box,
    notice("warning", L("Fee levels are a commercial decision pending approval (Blueprint D3). Values here are demo placeholders. A new rule replaces the active rule for that model; earlier invoices keep the fee they were issued with.",
      "مستويات الرسوم قرار تجاري بانتظار الاعتماد (القرار D3). القيم هنا تجريبية. القاعدة الجديدة تحل محل القاعدة المفعلة لهذا النموذج، وتحتفظ الفواتير السابقة برسومها.")),
    h("div", { class: "form-grid" },
      field(L("Service model", "نموذج الخدمة"), sel("model", [["A", L("Model A – projects", "النموذج أ – المشاريع")], ["B", L("Model B – short-term services", "النموذج ب – الخدمات قصيرة المدة")]], "A")),
      field(L("Who pays", "من يدفع"), sel("payer", [["organization", L("Organization", "الجهة")], ["engineer", L("Engineer", "المهندس")], ["both", L("Both parties", "الطرفان")]], "both")),
      field(L("Fee type", "نوع الرسوم"), sel("fee_type", [["percent", L("Percentage", "نسبة مئوية")], ["fixed", L("Fixed amount", "مبلغ ثابت")]], "percent")),
      field(L("Organization's fee", "رسوم الجهة"), inp("org_value", { inputmode: "decimal", value: "0" }), { hint: valueHint }),
      field(L("Engineer's fee", "رسوم المهندس"), inp("engineer_value", { inputmode: "decimal", value: "0" })),
      field(L("Note", "ملاحظة"), inp("note"))),
    h("button", { class: "btn", type: "submit" }, L("Save and activate", "حفظ وتفعيل"))),
  async (d) => {
    const conv = (v) => Math.round(parseFloat(String(v || "0").replace(",", ".")) * 100) || 0; // percent -> basis points; SAR -> halalas
    await api("/admin/fee-rules", { method: "POST", body: { ...d, org_value: conv(d.org_value), engineer_value: conv(d.engineer_value) } });
    toast(L("Fee rule saved and activated.", "تم حفظ قاعدة الرسوم وتفعيلها.")); B.render();
  });
  const fmt = (r, v) => r.fee_type === "percent" ? (v / 100) + "%" : money(v, { plain: true });
  return h("div", { class: "stack" }, card(L("Fee rules", "قواعد الرسوم"), table([{ label: L("Model", "النموذج"), render: r => r.model }, { label: L("Who pays", "من يدفع"), render: r => ({ organization: L("Organization", "الجهة"), engineer: L("Engineer", "المهندس"), both: L("Both", "الطرفان") }[r.payer]) },
    { label: L("Organization", "الجهة"), render: r => fmt(r, r.org_value) }, { label: L("Engineer", "المهندس"), render: r => fmt(r, r.engineer_value) },
    { label: L("Status", "الحالة"), render: r => badge(r.is_active ? "active" : "closed", r.is_active ? L("Active", "مفعلة") : L("Replaced", "مستبدلة")) }, { label: L("Note", "ملاحظة"), render: r => r.note }, { label: L("Created", "أنشئت"), render: r => fmtDate(r.created_at) }], rules)), form);
}

async function admSettings() {
  const list = await api("/admin/settings");
  return h("div", { class: "stack" }, notice("warning", L("Values marked 'pending review' are prototype assumptions – they are not legally or financially approved.", "القيم المعلَّمة «بانتظار المراجعة» افتراضات تجريبية وليست معتمدة قانونيًا أو ماليًا.")),
    card(null, table([{ label: L("Setting", "الإعداد"), render: s => [L(s.label_en, s.label_ar), s.pending_review ? h("div", {}, badge("pending", L("Pending review: ", "بانتظار المراجعة: ") + s.pending_review)) : null] },
      { label: L("Default", "الافتراضي"), render: s => String(s.default) },
      { label: L("Value", "القيمة"), render: s => {
        const input = s.kind === "bool" ? h("input", { type: "checkbox", checked: s.value, "aria-label": L(s.label_en, s.label_ar) }) : h("input", { type: "number", value: s.value, min: s.min, max: s.max, step: s.kind === "float" ? "0.1" : "1", style: "max-width:120px", "aria-label": L(s.label_en, s.label_ar) });
        const save = h("button", { class: "btn small secondary", type: "button", onclick: async () => {
          const value = s.kind === "bool" ? input.checked : (s.kind === "int" ? parseInt(input.value, 10) : parseFloat(input.value));
          try { await api(`/admin/settings/${s.key}`, { method: "PUT", body: { value } }); toast(L("Setting saved (recorded in the audit log).", "تم حفظ الإعداد (مسجل في سجل التدقيق).")); } catch (err) { toast(err.message, true); }
        } }, L("Save", "حفظ"));
        return h("div", { class: "row" }, input, save);
      } }], list)));
}

async function admDisciplines() {
  const list = await api("/admin/disciplines");
  const box = errorBox();
  return h("div", { class: "stack" }, card(L("Engineering disciplines", "التخصصات الهندسية"), table([{ label: L("Code", "الرمز"), render: d => h("span", { class: "ltr" }, d.code) }, { label: "English", render: d => d.name_en }, { label: "العربية", render: d => d.name_ar },
    { label: L("Status", "الحالة"), render: d => badge(d.is_active ? "active" : "closed", d.is_active ? L("Active", "مفعّل") : L("Hidden", "مخفي")) },
    { label: "", render: d => action(d.is_active ? L("Hide", "إخفاء") : L("Show", "إظهار"), () => api(`/admin/disciplines/${d.id}`, { method: "PATCH", body: { is_active: !d.is_active } }), { cls: "btn secondary small" }) }], list)),
    onSubmit(h("form", { class: "card" }, h("h2", {}, L("Add a discipline", "إضافة تخصص")), box, h("div", { class: "form-grid" },
      field(L("Code (latin, e.g. fire_safety)", "الرمز (لاتيني، مثل fire_safety)"), inp("code", { dir: "ltr", pattern: "[a-z0-9_]+" }), { required: true }),
      field(L("Sort order", "الترتيب"), inp("sort_order", { type: "number", value: 100, "data-type": "int" })),
      field("English", inp("name_en"), { required: true }), field("العربية", inp("name_ar"), { required: true })),
      h("button", { class: "btn", type: "submit" }, L("Add", "إضافة"))),
    async (d) => { await api("/admin/disciplines", { method: "POST", body: d }); DISCIPLINES = null; toast(L("Discipline added.", "تمت إضافة التخصص.")); B.render(); }));
}

async function admCalendar() {
  const list = await api("/admin/holidays");
  const box = errorBox();
  return h("div", { class: "stack" }, notice("info", L("Working days are Sunday to Thursday. Holidays below are excluded from review windows, contract lengths and billing periods. Islamic holiday dates are estimates until confirmed.",
    "أيام العمل من الأحد إلى الخميس. تُستثنى العطل أدناه من مهل المراجعة ومدد العقود وفترات الفوترة. تواريخ الأعياد تقديرية حتى تأكيدها.")),
    card(L("Public holidays", "العطل الرسمية"), table([{ label: L("Date", "التاريخ"), render: x => fmtDate(x.day) }, { label: "English", render: x => x.name_en }, { label: "العربية", render: x => x.name_ar },
      { label: L("Confirmed", "مؤكد"), render: x => x.is_confirmed ? badge("verified", L("Confirmed", "مؤكد")) : badge("pending", L("Estimate", "تقديري")) },
      { label: "", render: x => action(L("Remove", "حذف"), () => api(`/admin/holidays/${x.id}`, { method: "DELETE" }), { cls: "btn ghost small", confirm: L("Remove this holiday? Future working-day calculations will change.", "حذف هذه العطلة؟ ستتغير حسابات أيام العمل المستقبلية.") }) }], list)),
    onSubmit(h("form", { class: "card" }, h("h2", {}, L("Add a holiday", "إضافة عطلة")), box, h("div", { class: "form-grid" },
      field(L("Date", "التاريخ"), inp("day", { type: "date" }), { required: true }), field("English", inp("name_en"), { required: true }), field("العربية", inp("name_ar"), { required: true }),
      h("label", { class: "check" }, h("input", { type: "checkbox", name: "is_confirmed" }), L("Date is officially confirmed", "التاريخ مؤكد رسميًا"))),
      h("button", { class: "btn", type: "submit" }, L("Add holiday", "إضافة العطلة"))),
    async (d) => { await api("/admin/holidays", { method: "POST", body: d }); toast(L("Holiday added.", "تمت إضافة العطلة.")); B.render(); }));
}

async function admNotify() {
  const box = errorBox();
  return onSubmit(h("form", { class: "card", style: "max-width:640px" }, h("h2", {}, L("Send an announcement", "إرسال إعلان")), box,
    h("p", { class: "muted small" }, L("Appears in the notifications of the selected users (in-app only; e-mail is not configured).", "يظهر في إشعارات المستخدمين المحددين (داخل المنصة فقط؛ البريد غير مفعّل).")),
    field(L("Audience", "الجمهور"), sel("audience", [["all", L("Everyone", "الجميع")], ["organization", L("Organization users", "مستخدمو الجهات")], ["engineer", L("Engineers", "المهندسون")]], "all")),
    field(L("Message", "الرسالة"), txt("text", { rows: 3, maxlength: 280 }), { required: true }),
    h("button", { class: "btn", type: "submit" }, L("Send", "إرسال"))),
  async (d) => { const r = await api("/admin/announcements", { method: "POST", body: d }); toast(L(`Sent to ${r.recipients} users.`, `أُرسل إلى ${r.recipients} مستخدم.`)); B.render(); });
}

async function admAudit(q) {
  const page = parseInt(q.get("page") || "1", 10);
  const res = await api("/admin/audit-logs?" + new URLSearchParams(strip({ action: q.get("action"), page })));
  const form = h("form", { class: "row card flat", style: "align-items:flex-end;margin-bottom:1rem" }, field(L("Filter by action (e.g. verification, finance, dispute)", "تصفية حسب الإجراء (مثل verification أو finance أو dispute)"), inp("action", { value: q.get("action") || "", dir: "ltr" })), h("button", { class: "btn", type: "submit" }, L("Filter", "تصفية")));
  form.addEventListener("submit", (ev) => { ev.preventDefault(); go("/admin?" + new URLSearchParams(strip({ tab: "audit", action: readForm(form).action }))); });
  const pages = Math.max(1, Math.ceil(res.total / res.per_page));
  return h("div", {}, form, card(null, table([{ label: L("When", "الوقت"), render: r => fmtTime(r.created_at) }, { label: L("Who", "من"), render: r => r.actor ? r.actor.name : L("System", "النظام") },
    { label: L("Action", "الإجراء"), render: r => h("span", { class: "ltr" }, r.action) }, { label: L("Item", "العنصر"), render: r => r.entity_type ? `${r.entity_type} #${r.entity_id ?? ""}` : "—" },
    { label: L("Details", "التفاصيل"), render: r => h("span", { class: "small ltr", style: "white-space:normal" }, Object.entries(r.details || {}).map(([k, v]) => `${k}: ${v}`).join(" · ")) }], res.data),
    h("div", { class: "row between", style: "margin-top:.75rem" }, h("span", { class: "muted small" }, L(`Page ${page} of ${pages} · ${res.total} entries`, `صفحة ${page} من ${pages} · ${res.total} سجل`)),
      h("div", { class: "btn-row" }, page > 1 ? linkBtn(`/admin?tab=audit&page=${page - 1}`, L("Previous", "السابق"), "btn secondary small") : null, page < pages ? linkBtn(`/admin?tab=audit&page=${page + 1}`, L("Next", "التالي"), "btn secondary small") : null))));
}
