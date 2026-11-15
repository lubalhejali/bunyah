/* Model B – short-term engineering service contracts. Separate screens and rules from Model A. */
"use strict";

const FLOW_B = ["draft", "submitted", "pending_review", "published", "applications_open", "under_evaluation", "selected",
  "contract_preparation", "awaiting_signatures", "active", "near_expiry", "completed"];

function requestCard(r) {
  return h("a", { class: "item-card", href: "#/services/" + r.id },
    h("div", { class: "row between" }, h("span", { class: "eyebrow" }, L("Short-term service", "خدمة قصيرة المدة"), r.discipline ? " · " + nm(r.discipline) : ""), badge(r.status)),
    h("h3", {}, r.title),
    h("p", { class: "muted small", style: "margin:.2rem 0 .5rem" }, nm(r.organization), r.organization.verified ? " ✓" : ""),
    h("div", { class: "meta" }, h("span", {}, money(r.daily_rate_cents), L(" / day", " / يوم")),
      h("span", {}, L(`${r.duration_working_days} working days`, `${r.duration_working_days} يوم عمل`)), h("span", {}, workMode(r.work_mode), r.location ? " · " + r.location : ""),
      h("span", {}, L("Starts ", "يبدأ "), fmtDate(r.start_date)),
      r.my_application_status ? badge(r.my_application_status, L("My application: ", "طلبي: ") + statusLabel(r.my_application_status)) : null));
}

B.views.services = async function (params, q) {
  const disc = await disciplines();
  const scope = isOrg() ? "mine" : (q.get("tab") || "marketplace");
  const res = await api("/service-requests?" + new URLSearchParams(strip({ scope, q: q.get("q"), discipline_id: q.get("discipline_id"), work_mode: q.get("work_mode"), status: q.get("status") })));
  const filters = h("form", { class: "filters card flat" },
    field(L("Search", "بحث"), inp("q", { type: "search", value: q.get("q") || "" })),
    field(L("Discipline", "التخصص"), sel("discipline_id", [["", L("All", "الكل")], ...disc.map(d => [d.id, nm(d)])], q.get("discipline_id"))),
    field(L("Work arrangement", "طريقة العمل"), sel("work_mode", [["", L("Any", "الكل")], ...Object.keys(WORK_MODES).map(k => [k, workMode(k)])], q.get("work_mode"))),
    scope === "mine" ? field(L("Status", "الحالة"), sel("status", [["", L("All", "الكل")], ...FLOW_B.concat(["terminated", "disputed", "cancelled"]).map(s => [s, statusLabel(s)])], q.get("status"))) : h("div"),
    h("button", { class: "btn", type: "submit" }, L("Apply", "تطبيق")));
  filters.addEventListener("submit", (ev) => { ev.preventDefault(); go("/services?" + new URLSearchParams(strip({ ...readForm(filters), tab: isEng() ? scope : "" }))); });
  return h("div", {},
    pageHead(isOrg() ? L("Short-term service requests", "طلبات الخدمات قصيرة المدة") : L("Short-term engineering services", "خدمات هندسية قصيرة المدة"),
      L("Model B – daily-rate contracts for a defined number of working days", "النموذج ب – عقود بالسعر اليومي لعدد محدد من أيام العمل"),
      ...(isOrg() && can("work.manage") ? [linkBtn("/services/new", L("New service request", "طلب خدمة جديد"))] : [])),
    isEng() ? tabs([["marketplace", L("Open requests", "الطلبات المفتوحة")], ["mine", L("My applications & contracts", "طلباتي وعقودي")]], scope, "/services") : null,
    filters,
    res.data.length ? h("div", { class: "grid grid-2" }, res.data.map(requestCard))
      : empty(L("No service requests found", "لا توجد طلبات خدمة"), isOrg() ? L("Request a qualified engineer for a defined number of working days.", "اطلب مهندسًا مؤهلًا لعدد محدد من أيام العمل.") : L("Check again later or change the filters.", "عُد لاحقًا أو غيّر عوامل التصفية.")));
};

B.views.serviceForm = async function ([id]) {
  const disc = await disciplines();
  const r = id ? await api("/service-requests/" + id) : {};
  const box = errorBox();
  const f = (name, label, opts = {}) => field(label, (opts.area ? txt : inp)(name, { value: r[name] ?? opts.def ?? "", ...(opts.attrs || {}) }), opts);
  return h("div", {}, pageHead(id ? L("Edit service request", "تعديل طلب الخدمة") : L("New short-term service request", "طلب خدمة قصيرة المدة جديد"), L("Saved as a draft. Submitting sends it to the BUNYAH team for review before publication.", "يُحفظ كمسودة، والتقديم يرسله لفريق بُنية للمراجعة قبل النشر.")),
    notice("warning", L("The maximum contract length (currently 90 working days) is a prototype setting pending Saudi legal review. Use fictional data only.", "الحد الأقصى لمدة العقد (حاليًا 90 يوم عمل) إعداد تجريبي بانتظار المراجعة القانونية. استخدم بيانات وهمية فقط.")),
    onSubmit(h("form", { class: "card" }, box,
      h("fieldset", {}, h("legend", {}, L("Role required", "الدور المطلوب")), h("div", { class: "form-grid" },
        f("title", L("Title", "العنوان"), { required: true, full: true, attrs: { placeholder: L("e.g. BIM Specialist – hospital project", "مثال: أخصائي نمذجة – مشروع مستشفى") } }),
        field(L("Discipline", "التخصص"), sel("discipline_id", disciplineOptions(disc), r.discipline?.id, { "data-type": "int" }), { required: true }),
        f("specialization", L("Specialization", "التخصص الدقيق")),
        f("min_experience_years", L("Minimum experience (years)", "الحد الأدنى للخبرة (سنوات)"), { def: 0, attrs: { type: "number", min: 0, "data-type": "int" } }),
        f("qualifications", L("Qualifications", "المؤهلات"), { area: true }),
        f("responsibilities", L("Responsibilities", "المسؤوليات"), { area: true, required: true, full: true, attrs: { minlength: 20 } }),
        f("outputs", L("Required deliverables / work outputs", "المخرجات المطلوبة"), { area: true, full: true }))),
      h("fieldset", {}, h("legend", {}, L("Terms", "الشروط")), h("div", { class: "form-grid" },
        f("duration_working_days", L("Contract duration (working days)", "مدة العقد (أيام عمل)"), { required: true, attrs: { type: "number", min: 1, max: 260, "data-type": "int" }, hint: L("Sunday–Thursday, excluding public holidays.", "من الأحد إلى الخميس، باستثناء العطل الرسمية.") }),
        f("hours_per_day", L("Expected hours per day", "الساعات المتوقعة يوميًا"), { def: 8, attrs: { type: "number", min: 1, max: 12, "data-type": "int" } }),
        field(L("Daily rate (SAR)", "السعر اليومي (ريال)"), moneyInput("daily_rate_cents", r.daily_rate_cents), { required: true }),
        f("start_date", L("Start date", "تاريخ البدء"), { required: true, attrs: { type: "date", min: todayISO() } }),
        field(L("Work arrangement", "طريقة العمل"), sel("work_mode", Object.keys(WORK_MODES).map(k => [k, workMode(k)]), r.work_mode || "onsite")),
        f("location", L("Location", "الموقع"), { hint: L("Required for on-site or hybrid work.", "مطلوب للعمل الميداني أو المختلط.") }))),
      h("div", { class: "btn-row" }, h("button", { class: "btn", type: "submit" }, id ? L("Save changes", "حفظ التغييرات") : L("Save as draft", "حفظ كمسودة")), linkBtn(id ? "/services/" + id : "/services", L("Cancel", "إلغاء"), "btn secondary"))),
    async (d) => { const x = id ? await api("/service-requests/" + id, { method: "PATCH", body: d }) : await api("/service-requests", { method: "POST", body: d }); toast(L("Saved.", "تم الحفظ.")); go("/services/" + x.id); }));
};

B.views.service = async function ([id], q) {
  const r = await api("/service-requests/" + id);
  const tab = q.get("tab") || "overview";
  const role = r.my_role, inside = ["org", "contractor", "admin"].includes(role);
  const items = [["overview", L("Overview", "نظرة عامة")]];
  if (role === "org" || role === "admin") items.push(["applications", L("Applications", "طلبات التقديم"), r.application_count]);
  else if (isEng()) items.push(["applications", L("My application", "طلبي")]);
  if (r.contract && inside) items.push(["contract", L("Contract", "العقد")], ["time", L("Work log & billing", "سجل العمل والفوترة")], ["finance", L("Finance", "المالية")]);
  if (inside) items.push(["activity", L("Activity", "السجل")]);
  const views = { overview: svcOverview, applications: svcApplications, contract: svcContract, time: svcTime, finance: svcFinance, activity: (x) => activity(`/service-requests/${x.id}/events`) };
  const body = await (views[tab] || svcOverview)(r);
  return h("div", {},
    h("div", { class: "eyebrow" }, L("Model B · Short-term service", "النموذج ب · خدمة قصيرة المدة"), r.is_demo ? " · " : "", r.is_demo ? demoTag(L("DEMO DATA", "بيانات تجريبية")) : null),
    pageHead(r.title, [nm(r.organization), r.discipline ? " · " + nm(r.discipline) : ""].join(""), badge(r.status)),
    !["cancelled", "disputed", "terminated"].includes(r.status) ? stepper(FLOW_B, r.status) : null,
    tabs(items, tab, "/services/" + id), body);
};

function svcActions(r) {
  const out = [], post = (p, b) => api(`/service-requests/${r.id}${p}`, { method: "POST", body: b ?? {} });
  const step = (to, label, opts) => action(label, () => post("/transitions", { to }), opts);
  if (r.my_role === "org") {
    const m = can("work.manage");
    if (m && r.status === "draft") out.push(linkBtn(`/services/${r.id}/edit`, L("Edit details", "تعديل التفاصيل"), "btn secondary"),
      action(L("Submit for BUNYAH review", "تقديم لمراجعة بُنية"), () => post("/submit"), { confirm: L("Submit this request? The BUNYAH team reviews it before it is published.", "تقديم الطلب؟ يراجعه فريق بُنية قبل نشره."), done: L("Submitted for review.", "تم التقديم للمراجعة.") }));
    if (m && r.status === "published") out.push(step("applications_open", L("Open applications", "فتح التقديم")));
    if (m && r.status === "applications_open") out.push(step("under_evaluation", L("Close applications & evaluate", "إغلاق التقديم والتقييم"), { confirm: L("Stop accepting applications and start the evaluation?", "إيقاف استقبال الطلبات وبدء التقييم؟") }));
    if (m && r.status === "under_evaluation") out.push(linkBtn(`/services/${r.id}?tab=applications`, L("Compare & select a candidate", "قارن واختر مرشحًا")), step("applications_open", L("Reopen applications", "إعادة فتح التقديم"), { cls: "btn secondary" }));
    if (m && r.status === "selected") out.push(action(L("Prepare the contract", "إعداد العقد"), () => post("/contract"), { done: L("Contract draft created.", "تم إنشاء مسودة العقد.") }));
    if (m && ["selected", "contract_preparation"].includes(r.status)) out.push(action(L("Withdraw selection", "التراجع عن الاختيار"), () => post("/unselect"), { cls: "btn secondary", confirm: L("Withdraw the selection and return to evaluation?", "التراجع عن الاختيار والعودة للتقييم؟") }));
    if (m && r.status === "contract_preparation") out.push(linkBtn(`/services/${r.id}?tab=contract`, L("Review contract & send for signature", "مراجعة العقد وإرساله للتوقيع")));
    if (["awaiting_signatures"].includes(r.status)) out.push(linkBtn(`/services/${r.id}?tab=contract`, L("Go to signatures", "الانتقال إلى التوقيع")));
    if (m && ["active", "near_expiry"].includes(r.status)) out.push(
      action(L("Mark contract completed", "إنهاء العقد كمكتمل"), () => post("/finish", { outcome: "completed" }), { confirm: L("Complete the contract? All billing periods with recorded days must be approved.", "إكمال العقد؟ يجب اعتماد كل فترات الفوترة التي تحتوي أيامًا مسجلة.") }),
      action(L("End contract early", "إنهاء العقد مبكرًا"), (reason) => post("/finish", { outcome: "terminated", reason }), { cls: "btn danger", prompt: { message: L("End this contract early? This is recorded and can't be undone.", "إنهاء العقد مبكرًا؟ سيتم التسجيل ولا يمكن التراجع."), input: "textarea", inputLabel: L("Reason", "السبب"), required: true, minLength: 5, okLabel: L("End contract", "إنهاء العقد") } }));
    if (m && ["draft", "published", "applications_open", "under_evaluation", "selected", "contract_preparation", "awaiting_signatures"].includes(r.status) && r.status !== "submitted")
      out.push(step("cancelled", L("Cancel request", "إلغاء الطلب"), { cls: "btn danger", confirm: L("Cancel this request? Applicants will be informed. This can't be undone.", "إلغاء هذا الطلب؟ سيتم إبلاغ المتقدمين. لا يمكن التراجع.") }));
  }
  if (r.my_role === "contractor") {
    if (r.status === "awaiting_signatures" && !r.contract.engineer_signed_at) out.push(linkBtn(`/services/${r.id}?tab=contract`, L("Review & sign the contract", "مراجعة العقد وتوقيعه")));
    if (["active", "near_expiry"].includes(r.status)) out.push(linkBtn(`/services/${r.id}?tab=time`, L("Record work days", "تسجيل أيام العمل")),
      action(L("End contract early", "إنهاء العقد مبكرًا"), (reason) => post("/finish", { outcome: "terminated", reason }), { cls: "btn danger", prompt: { message: L("End this contract early? This is recorded and can't be undone.", "إنهاء العقد مبكرًا؟ سيتم التسجيل ولا يمكن التراجع."), input: "textarea", inputLabel: L("Reason", "السبب"), required: true, minLength: 5, okLabel: L("End contract", "إنهاء العقد") } }));
  }
  const canDispute = (r.my_role === "org" && can("dispute.raise")) || r.my_role === "contractor";
  if (canDispute && ["active", "near_expiry"].includes(r.status)) out.push(linkBtn(`/disputes/new?type=contract&id=${r.id}`, L("Raise a dispute", "فتح نزاع"), "btn secondary"));
  if (r.status === "disputed" && r.dispute_id) out.push(linkBtn(`/disputes/${r.dispute_id}`, L("Open the dispute", "فتح ملف النزاع")));
  if (["completed", "terminated"].includes(r.status) && r.contract && !r.rated_by_me && ((r.my_role === "org" && can("work.manage")) || r.my_role === "contractor"))
    out.push(rateButton(`/service-requests/${r.id}/ratings`, r.my_role === "org" ? L("Rate the engineer", "قيّم المهندس") : L("Rate the organization", "قيّم الجهة")));
  return out;
}

async function svcOverview(r) {
  const acts = svcActions(r);
  const notes = [];
  if (r.my_role === "org" && r.status === "draft" && r.review_note) notes.push(notice("warning", h("strong", {}, L("Returned by BUNYAH: ", "أعادته بُنية: ")), r.review_note));
  if (["submitted", "pending_review"].includes(r.status)) notes.push(notice("info", L("The BUNYAH team is reviewing this request before publication.", "يراجع فريق بُنية هذا الطلب قبل نشره.")));
  if (r.status === "near_expiry") notes.push(notice("warning", L("This contract ends soon. Make sure all billing periods are submitted and approved.", "ينتهي هذا العقد قريبًا. تأكد من تقديم واعتماد جميع فترات الفوترة.")));
  return h("div", { class: "layout-side" },
    h("div", { class: "stack" }, ...notes, card(L("Service details", "تفاصيل الخدمة"), kv([
      [L("Responsibilities", "المسؤوليات"), h("span", { class: "prewrap" }, r.responsibilities)], [L("Required outputs", "المخرجات المطلوبة"), h("span", { class: "prewrap" }, r.outputs || "—")],
      [L("Qualifications", "المؤهلات"), h("span", { class: "prewrap" }, r.qualifications || "—")], [L("Specialization", "التخصص الدقيق"), r.specialization || "—"],
      [L("Minimum experience", "الحد الأدنى للخبرة"), L(`${r.min_experience_years} years`, `${r.min_experience_years} سنوات`)]]))),
    h("div", { class: "stack" },
      acts.length ? card(L("Next steps", "الخطوات التالية"), h("div", { class: "stack-sm" }, acts.map(a => h("div", {}, a)))) : null,
      card(L("Terms", "الشروط"), kv([[L("Organization", "الجهة"), h("a", { href: "#/org/" + r.organization.id }, nm(r.organization))],
        [L("Daily rate", "السعر اليومي"), money(r.daily_rate_cents)], [L("Duration", "المدة"), L(`${r.duration_working_days} working days`, `${r.duration_working_days} يوم عمل`)],
        [L("Estimated value", "القيمة التقديرية"), money(r.estimated_total_cents)], [L("Hours per day", "الساعات اليومية"), r.hours_per_day],
        [L("Start date", "تاريخ البدء"), fmtDate(r.start_date)], [L("Work arrangement", "طريقة العمل"), workMode(r.work_mode) + (r.location ? " · " + r.location : "")],
        r.my_org_role ? [L("Your role", "دورك"), orgRole(r.my_org_role)] : null]))));
}

async function svcApplications(r) {
  const list = await api(`/service-requests/${r.id}/applications`);
  if (r.my_role !== "org" && r.my_role !== "admin") {
    const mine = list[0];
    const box = errorBox();
    const blocked = S.me.verification_status !== "verified";
    return h("div", { class: "grid grid-2", style: "align-items:start" },
      mine ? card(L("Your application", "طلبك"), h("p", {}, badge(mine.status)), kv([[L("Proposed daily rate", "السعر اليومي المقترح"), money(mine.proposed_daily_rate_cents)], [L("Available from", "متاح من"), fmtDate(mine.available_from)], [L("Cover letter", "خطاب التقديم"), h("span", { class: "prewrap" }, mine.cover_letter)], mine.decision_note ? [L("Organization's note", "ملاحظة الجهة"), mine.decision_note] : null]),
        ["submitted", "shortlisted"].includes(mine.status) ? h("div", { style: "margin-top:1rem" }, action(L("Withdraw application", "سحب الطلب"), () => api(`/applications/${mine.id}/withdraw`, { method: "POST" }), { cls: "btn danger small", confirm: L("Withdraw your application?", "سحب طلبك؟") })) : null) : null,
      (!mine || mine.status === "withdrawn") && r.status === "applications_open" ? onSubmit(h("form", { class: "card" }, h("h2", {}, L("Apply for this service", "التقديم على هذه الخدمة")), box,
        blocked ? notice("warning", L("Your profile must be verified before you can apply. ", "يجب توثيق ملفك قبل التقديم. "), h("a", { href: "#/profile?tab=verification" }, L("Go to verification", "الانتقال إلى التوثيق"))) : null,
        field(L("Proposed daily rate (SAR)", "السعر اليومي المقترح (ريال)"), moneyInput("proposed_daily_rate_cents", r.daily_rate_cents), { required: true }),
        field(L("Available from", "متاح من"), inp("available_from", { type: "date", min: todayISO(), value: r.start_date }), { required: true }),
        field(L("Cover letter", "خطاب التقديم"), txt("cover_letter", { minlength: 20, rows: 5 }), { required: true, hint: L("Explain your relevant experience. Your CV is shared with this organization when you apply.", "اشرح خبرتك ذات الصلة. تُشارك سيرتك مع هذه الجهة عند التقديم.") }),
        h("button", { class: "btn", type: "submit", disabled: blocked }, L("Send application", "إرسال الطلب"))),
      async (d) => { await api(`/service-requests/${r.id}/applications`, { method: "POST", body: d }); toast(L("Application sent.", "تم إرسال الطلب.")); B.render(); })
        : (!mine ? notice("info", L("This request is not accepting applications right now.", "هذا الطلب لا يستقبل طلبات حاليًا.")) : null));
  }
  if (!list.length) return empty(L("No applications yet", "لا توجد طلبات بعد"), r.status === "applications_open" ? L("Verified engineers can now apply.", "يمكن للمهندسين الموثّقين التقديم الآن.") : L("Open applications to receive candidates.", "افتح التقديم لاستقبال المرشحين."));
  const m = can("work.manage");
  const canSelect = m && r.status === "under_evaluation";
  return h("div", { class: "stack" },
    r.status === "applications_open" ? notice("info", L("Close applications to select a candidate. You can shortlist or decline already.", "أغلق التقديم لاختيار مرشح. يمكنك الآن إعداد القائمة المختصرة أو الرفض.")) : null,
    card(L("Compare candidates", "مقارنة المرشحين"), table([
      { label: L("Engineer", "المهندس"), render: a => [h("a", { href: "#/engineers/" + a.engineer.id }, a.engineer.name), " ", a.engineer.verified ? badge("verified") : null, h("div", { class: "muted small" }, a.engineer.title)] },
      { label: L("Experience", "الخبرة"), render: a => L(`${a.engineer.years_experience} yrs`, `${a.engineer.years_experience} سنة`) },
      { label: L("Daily rate", "السعر اليومي"), num: true, render: a => [money(a.proposed_daily_rate_cents), h("div", { class: "muted small" }, L("Total ", "الإجمالي "), money(a.proposed_daily_rate_cents * r.duration_working_days))] },
      { label: L("Available", "متاح من"), render: a => fmtDate(a.available_from) },
      { label: L("Rating", "التقييم"), render: a => a.engineer.average_rating ? stars(a.engineer.average_rating) : "—" },
      { label: L("CV", "السيرة"), render: a => a.engineer.has_cv ? fileLink({ id: a.engineer.cv_file_id, filename: "CV" }, L("Download", "تنزيل")) : "—" },
      { label: L("Status", "الحالة"), render: a => badge(a.status) },
      { label: "", render: a => h("div", { class: "btn-row" },
        h("details", {}, h("summary", { class: "small" }, L("Cover letter", "خطاب التقديم")), h("p", { class: "prewrap small" }, a.cover_letter)),
        m && ["submitted"].includes(a.status) ? action(L("Shortlist", "قائمة مختصرة"), () => api(`/applications/${a.id}/decision`, { method: "POST", body: { decision: "shortlist" } }), { cls: "btn secondary small" }) : null,
        canSelect && ["submitted", "shortlisted"].includes(a.status) ? action(L("Select", "اختيار"), () => api(`/applications/${a.id}/decision`, { method: "POST", body: { decision: "select" } }), { cls: "btn small", confirm: L(`Select ${a.engineer.name} at ${money(a.proposed_daily_rate_cents, { plain: true })} per day?`, `اختيار ${a.engineer.name} بسعر ${money(a.proposed_daily_rate_cents, { plain: true })} يوميًا؟`), done: L("Candidate selected.", "تم اختيار المرشح.") }) : null,
        m && ["submitted", "shortlisted"].includes(a.status) ? action(L("Decline", "رفض"), (note) => api(`/applications/${a.id}/decision`, { method: "POST", body: { decision: "reject", note } }), { cls: "btn ghost small", prompt: { message: L(`Decline ${a.engineer.name}?`, `رفض ${a.engineer.name}؟`), input: "textarea", inputLabel: L("Reason (optional)", "السبب (اختياري)"), okLabel: L("Decline", "رفض") } }) : null,
        can("messages.send") ? action(L("Message", "مراسلة"), async () => { const c = await api("/conversations", { method: "POST", body: { user_id: a.engineer.id } }); go("/messages/" + c.id); }, { cls: "btn ghost small" }) : null) },
    ], list)));
}

async function svcContract(r) {
  const c = r.contract;
  const org = r.my_role === "org";
  const box = errorBox();
  const editForm = org && can("work.manage") && r.status === "contract_preparation" ? onSubmit(h("form", { class: "card" }, h("h2", {}, L("Contract terms", "شروط العقد")), box, h("div", { class: "form-grid" },
    field(L("Start date", "تاريخ البدء"), inp("start_date", { type: "date", min: todayISO(), value: c.start_date }), { required: true }),
    field(L("Working days", "أيام العمل"), inp("working_days", { type: "number", min: 1, value: c.working_days, "data-type": "int" }), { required: true }),
    field(L("Daily rate (SAR)", "السعر اليومي (ريال)"), moneyInput("daily_rate_cents", c.daily_rate_cents), { required: true }),
    field(L("Hours per day", "الساعات اليومية"), inp("hours_per_day", { type: "number", min: 1, max: 12, value: c.hours_per_day, "data-type": "int" })),
    field(L("Contract text", "نص العقد"), txt("terms", { value: c.terms, rows: 8 }), { full: true })),
    h("div", { class: "btn-row" }, h("button", { class: "btn secondary", type: "submit" }, L("Save terms", "حفظ الشروط")),
      action(L("Send for signature", "إرسال للتوقيع"), () => api(`/service-requests/${r.id}/contract/send`, { method: "POST" }), { confirm: L("Send the contract to both parties for signature? Terms can't be changed after signing starts unless it is returned to preparation.", "إرسال العقد للطرفين للتوقيع؟ لا يمكن تعديل الشروط بعد بدء التوقيع إلا بإعادته لمرحلة الإعداد."), done: L("Sent for signature.", "تم الإرسال للتوقيع.") }))),
  async (d) => { await api(`/service-requests/${r.id}/contract`, { method: "PATCH", body: d }); toast(L("Terms saved. End date recalculated on the working-day calendar.", "تم الحفظ وإعادة حساب تاريخ الانتهاء وفق أيام العمل.")); B.render(); }) : null;
  const mySig = org ? c.org_signed_at : c.engineer_signed_at;
  const canSign = r.status === "awaiting_signatures" && !mySig && ((org && can("contract.sign")) || r.my_role === "contractor");
  const sbox = errorBox();
  const signForm = canSign ? onSubmit(h("form", { class: "card" }, h("h2", {}, L("Sign the contract", "توقيع العقد")), sbox,
    notice("warning", L("Simulated electronic signature for the prototype – not a legally valid e-signature.", "توقيع إلكتروني تجريبي للنموذج – ليس توقيعًا إلكترونيًا معتمدًا قانونيًا.")),
    field(L("Type your full name exactly as on your account", "اكتب اسمك الكامل كما في حسابك"), inp("full_name", { autocomplete: "name", placeholder: S.me.name }), { required: true, hint: S.me.name }),
    h("label", { class: "check" }, h("input", { type: "checkbox", name: "confirm", required: true }), L("I have read the contract terms and agree to them.", "قرأت شروط العقد وأوافق عليها.")),
    h("div", { style: "margin-top:.75rem" }, h("button", { class: "btn", type: "submit" }, L("Sign contract", "توقيع العقد")))),
  async (d) => { await api(`/service-requests/${r.id}/contract/sign`, { method: "POST", body: d }); toast(L("Signed.", "تم التوقيع.")); B.render(); }) : null;
  const returnBtn = org && can("work.manage") && r.status === "awaiting_signatures" ? action(L("Return to preparation", "إعادة لمرحلة الإعداد"), () => api(`/service-requests/${r.id}/contract/return`, { method: "POST" }), { cls: "btn secondary", confirm: L("Return the contract to preparation? Existing signatures will be cleared.", "إعادة العقد لمرحلة الإعداد؟ سيتم إلغاء التواقيع الحالية.") }) : null;
  return h("div", { class: "stack" }, notice("warning", L(c.legal_notice_en, c.legal_notice_ar)),
    h("div", { class: "layout-side" },
      h("div", { class: "stack" }, editForm || card(L("Contract text", "نص العقد"), h("p", { class: "prewrap small" }, c.terms)), signForm),
      h("div", { class: "stack" }, card(L("Contract summary", "ملخص العقد"), kv([
        [L("Engineer", "المهندس"), c.engineer.name], [L("Start", "البدء"), fmtDate(c.start_date)], [L("End", "الانتهاء"), fmtDate(c.end_date)],
        [L("Working days", "أيام العمل"), c.working_days], [L("Daily rate", "السعر اليومي"), money(c.daily_rate_cents)], [L("Contract value", "قيمة العقد"), money(c.contract_value_cents)],
        [L("Billing periods", "فترات الفوترة"), L(`Every ${c.period_length_days} working days; the last one covers the rest`, `كل ${c.period_length_days} يوم عمل؛ والأخيرة تغطي المتبقي`)],
        [L("Organization signature", "توقيع الجهة"), c.org_signed_at ? [c.org_signature_name, " · ", fmtTime(c.org_signed_at)] : L("Not signed", "لم يوقّع")],
        [L("Engineer signature", "توقيع المهندس"), c.engineer_signed_at ? [c.engineer_signature_name, " · ", fmtTime(c.engineer_signed_at)] : L("Not signed", "لم يوقّع")],
        c.ended_reason ? [L("Ended", "الإنهاء"), c.ended_reason] : null]), returnBtn ? h("div", { style: "margin-top:.75rem" }, returnBtn) : null))));
}

async function svcTime(r) {
  const c = r.contract;
  if (!c.periods.length) return empty(L("Billing periods start when the contract is active", "تبدأ فترات الفوترة عند سريان العقد"), L("Both parties must sign first.", "يجب أن يوقّع الطرفان أولاً."));
  const contractor = r.my_role === "contractor";
  const approver = r.my_role === "org" && can("billing.approve");
  const running = ["active", "near_expiry"].includes(r.status);
  const box = errorBox();
  const entryForm = contractor && running ? onSubmit(h("form", { class: "card" }, h("h2", {}, L("Record a work day", "تسجيل يوم عمل")), box, h("div", { class: "form-grid" },
    field(L("Date", "التاريخ"), inp("work_date", { type: "date", max: todayISO(), min: c.start_date, value: todayISO() }), { required: true, hint: L("Working days only (Sunday–Thursday, not holidays).", "أيام العمل فقط (الأحد–الخميس، عدا العطل).") }),
    field(L("Day", "اليوم"), sel("day_fraction", [["1", L("Full day", "يوم كامل")], ["0.5", L("Half day", "نصف يوم")]], "1", { "data-type": "float" })),
    field(L("Hours", "الساعات"), inp("hours", { type: "number", step: "0.5", min: 0.5, max: 16, value: c.hours_per_day, "data-type": "float" })),
    field(L("Work done", "العمل المنجز"), txt("description", { rows: 2, minlength: 5 }), { required: true, full: true })),
    h("button", { class: "btn", type: "submit" }, L("Save work day", "حفظ يوم العمل"))),
  async (d) => { await api(`/service-requests/${r.id}/time-entries`, { method: "POST", body: d }); toast(L("Work day recorded.", "تم تسجيل يوم العمل.")); B.render(); }) : null;
  const periodCards = c.periods.map(p => {
    const editable = contractor && running && ["open", "revision_requested"].includes(p.status);
    const acts = [];
    if (contractor && ["open", "revision_requested"].includes(p.status) && p.entries.length && (running || r.status === "terminated"))
      acts.push(action(L("Submit period for approval", "تقديم الفترة للاعتماد"), () => api(`/billing-periods/${p.id}/submit`, { method: "POST" }), { cls: "btn small", confirm: L(`Submit period ${p.seq} (${p.recorded_days} days)? You can't edit its entries while it is under review.`, `تقديم الفترة ${p.seq} (${p.recorded_days} يوم)؟ لا يمكنك تعديل سجلاتها أثناء المراجعة.`), done: L("Submitted.", "تم التقديم.") }));
    if (approver && p.status === "submitted") acts.push(
      action(L("Approve period", "اعتماد الفترة"), () => api(`/billing-periods/${p.id}/review`, { method: "POST", body: { decision: "approve", comment: "" } }), { cls: "btn small", confirm: L(`Approve ${p.recorded_days} days × ${money(c.daily_rate_cents, { plain: true })} = ${money(p.estimated_cents, { plain: true })}? A simulated invoice will be issued.`, `اعتماد ${p.recorded_days} يوم × ${money(c.daily_rate_cents, { plain: true })} = ${money(p.estimated_cents, { plain: true })}؟ ستصدر فاتورة تجريبية.`), done: L("Period approved.", "تم اعتماد الفترة.") }),
      action(L("Request changes", "طلب تعديل"), (comment) => api(`/billing-periods/${p.id}/review`, { method: "POST", body: { decision: "revision", comment } }), { cls: "btn secondary small", prompt: { message: L("What needs to change in these work records?", "ما المطلوب تعديله في سجلات العمل؟"), input: "textarea", inputLabel: L("Comment", "التعليق"), required: true, okLabel: L("Request changes", "طلب تعديل") } }));
    return h("section", { class: "card" },
      h("div", { class: "card-head" }, h("h3", { style: "margin:0" }, L(`Billing period ${p.seq}`, `فترة الفوترة ${p.seq}`), h("span", { class: "muted small" }, " · ", fmtDate(p.start_date), " – ", fmtDate(p.end_date))), badge(p.status)),
      h("div", { class: "meta" }, h("span", {}, L(`${p.working_days} working days`, `${p.working_days} يوم عمل`)), h("span", {}, L("Recorded: ", "المسجّل: "), p.recorded_days),
        h("span", {}, L("Estimated: ", "التقدير: "), money(p.estimated_cents)), p.status === "approved" ? h("span", {}, L("Approved: ", "المعتمد: "), p.approved_days, " → ", money(p.amount_cents)) : null,
        p.review_due_date && p.status === "submitted" ? h("span", {}, L("Review by ", "المراجعة قبل "), fmtDate(p.review_due_date)) : null),
      p.review_escalated ? notice("danger", L("Review window passed – escalated to the BUNYAH team. Not approved automatically.", "انتهت مهلة المراجعة – تم التصعيد لفريق بُنية دون اعتماد تلقائي.")) : null,
      p.review_comment && p.status === "revision_requested" ? notice("warning", h("strong", {}, L("Requested changes: ", "التعديلات المطلوبة: ")), p.review_comment) : null,
      p.entries.length ? table([{ label: L("Date", "التاريخ"), render: e => fmtDate(e.work_date) }, { label: L("Day", "اليوم"), render: e => e.day_fraction === 1 ? L("Full", "كامل") : L("Half", "نصف") },
        { label: L("Hours", "الساعات"), num: true, render: e => e.hours }, { label: L("Work done", "العمل المنجز"), render: e => e.description }, { label: L("Status", "الحالة"), render: e => badge(e.status) },
        editable ? { label: "", render: e => action(L("Delete", "حذف"), () => api(`/time-entries/${e.id}`, { method: "DELETE" }), { cls: "btn ghost small", confirm: L("Delete this work day?", "حذف يوم العمل هذا؟") }) } : null].filter(Boolean), p.entries)
        : h("p", { class: "muted small" }, L("No work days recorded in this period.", "لا توجد أيام مسجلة في هذه الفترة.")),
      acts.length ? h("div", { class: "btn-row", style: "margin-top:.75rem" }, acts) : null);
  });
  return h("div", { class: "stack" }, notice("info", L(`Fees = daily rate × approved working days. Periods of ${c.period_length_days} working days; the final period adapts to the remaining days. Approval is never automatic.`,
    `الأتعاب = السعر اليومي × أيام العمل المعتمدة. الفترات من ${c.period_length_days} يوم عمل والأخيرة تتكيف مع المتبقي. لا يوجد اعتماد تلقائي.`)), entryForm, ...periodCards);
}

async function svcFinance(r) {
  const f = await api(`/service-requests/${r.id}/finance`);
  return h("div", { class: "stack" },
    notice("warning", h("strong", {}, L("Simulated finance. ", "مالية تجريبية. ")), L("No real money moves. BUNYAH does not hold funds in this prototype.", "لا تتم أي حركة مالية حقيقية، ولا تحتفظ بُنية بأي أموال في هذا النموذج.")),
    h("div", { class: "grid grid-4" }, stat(L("Contract value", "قيمة العقد"), money(f.contract_value_cents)), stat(L("Approved days", "الأيام المعتمدة"), f.approved_days),
      stat(L("Paid (demo)", "المدفوع (تجريبي)"), money(f.paid_cents)), stat(L("Outstanding", "المستحق"), money(f.outstanding_cents))),
    card(null, h("div", { class: "row between" }, h("h2", { style: "margin:0" }, L("Period invoices", "فواتير الفترات")), demoTag()), h("p", { class: "muted small" }, feeNote(f.fee_rule)), invoiceTable(f.invoices, { pay: r.my_role === "org", title: L("No invoices yet. An invoice is issued when a billing period is approved.", "لا توجد فواتير بعد. تصدر الفاتورة عند اعتماد فترة فوترة.") })),
    card(null, h("div", { class: "row between" }, h("h2", { style: "margin:0" }, L("Transactions", "العمليات")), demoTag()), txTable(f.transactions)));
}
