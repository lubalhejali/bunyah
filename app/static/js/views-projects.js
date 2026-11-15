/* Model A – engineering projects: marketplace, project form, proposals, and the project workspace. */
"use strict";

const FLOW_A = ["draft", "published", "applications_closed", "under_evaluation", "shortlisted", "proposal_accepted", "in_progress",
  "submitted", "revision_requested", "resubmitted", "approved", "completed"];
const can = (perm) => !!(S.me && S.me.permissions && S.me.permissions.includes(perm));
const isOrg = () => S.me && S.me.role === "organization";
const isEng = () => S.me && S.me.role === "engineer";

function projectCard(p) {
  return h("a", { class: "item-card", href: "#/projects/" + p.id },
    h("div", { class: "row between" }, h("span", { class: "eyebrow" }, L("Project", "مشروع"), p.discipline ? " · " + nm(p.discipline) : ""), badge(p.status)),
    h("h3", {}, p.title),
    h("p", { class: "muted small", style: "margin:.2rem 0 .5rem" }, p.organization ? nm(p.organization) : "", p.organization?.verified ? " ✓" : ""),
    h("div", { class: "meta" },
      h("span", {}, L("Budget ", "الميزانية "), p.budget_min_cents ? [money(p.budget_min_cents), " – "] : "", money(p.max_budget_cents)),
      h("span", {}, workMode(p.work_mode), p.location ? " · " + p.location : ""),
      p.proposal_deadline ? h("span", {}, L("Proposals until ", "العروض حتى "), fmtDate(p.proposal_deadline)) : null,
      h("span", {}, L(`${p.proposal_count} proposals`, `${p.proposal_count} عروض`)),
      p.my_proposal_status ? badge(p.my_proposal_status, L("My proposal: ", "عرضي: ") + statusLabel(p.my_proposal_status)) : null));
}

B.views.projects = async function (params, q) {
  const disc = await disciplines();
  const scope = isOrg() ? "mine" : (q.get("tab") || q.get("scope") || "marketplace");
  const res = await api("/projects?" + new URLSearchParams(strip({ scope, q: q.get("q"), discipline_id: q.get("discipline_id"), work_mode: q.get("work_mode"), status: q.get("status") })));
  const filters = h("form", { class: "filters card flat" },
    field(L("Search", "بحث"), inp("q", { type: "search", value: q.get("q") || "", placeholder: L("Title, scope, city…", "العنوان، النطاق، المدينة…") })),
    field(L("Discipline", "التخصص"), sel("discipline_id", [["", L("All", "الكل")], ...disc.map(d => [d.id, nm(d)])], q.get("discipline_id"))),
    field(L("Work arrangement", "طريقة العمل"), sel("work_mode", [["", L("Any", "الكل")], ...Object.keys(WORK_MODES).map(k => [k, workMode(k)])], q.get("work_mode"))),
    scope === "mine" ? field(L("Status", "الحالة"), sel("status", [["", L("All", "الكل")], ...FLOW_A.concat(["cancelled", "disputed"]).map(s => [s, statusLabel(s)])], q.get("status"))) : h("div"),
    h("button", { class: "btn", type: "submit" }, L("Apply", "تطبيق")));
  filters.addEventListener("submit", (ev) => { ev.preventDefault(); go("/projects?" + new URLSearchParams(strip({ ...readForm(filters), tab: isEng() ? scope : "" }))); });
  const title = isOrg() ? L("Projects", "المشاريع") : (scope === "mine" ? L("My projects & proposals", "مشاريعي وعروضي") : L("Find engineering projects", "البحث عن مشاريع هندسية"));
  const actions = isOrg() && can("work.manage") ? [linkBtn("/projects/new", L("New project", "مشروع جديد"))] : [];
  return h("div", {},
    pageHead(title, L("Model A – project-based engineering services", "النموذج أ – خدمات هندسية على أساس المشروع"), ...actions),
    isEng() ? tabs([["marketplace", L("Marketplace", "السوق")], ["mine", L("My projects & proposals", "مشاريعي وعروضي")]], scope, "/projects") : null,
    filters,
    res.data.length ? h("div", { class: "grid grid-2" }, res.data.map(projectCard))
      : empty(L("No projects found", "لا توجد مشاريع"), isOrg() ? L("Create your first project to receive proposals from verified engineers.", "أنشئ مشروعك الأول لتستقبل عروض المهندسين الموثّقين.") : L("Try other filters or check again later.", "جرّب عوامل تصفية أخرى أو عُد لاحقًا."),
        isOrg() && can("work.manage") ? linkBtn("/projects/new", L("New project", "مشروع جديد")) : null));
};
B.views.projectForm = async function ([id]) {
  const disc = await disciplines();
  const p = id ? await api("/projects/" + id) : {};
  const box = errorBox();
  const f = (name, label, opts = {}) => field(label, (opts.area ? txt : inp)(name, { value: p[name] ?? "", ...(opts.attrs || {}) }), opts);
  return h("div", {}, pageHead(id ? L("Edit project", "تعديل المشروع") : L("New engineering project", "مشروع هندسي جديد"), L("The project is saved as a draft. Publish it when it is ready.", "يُحفظ المشروع كمسودة، ثم انشره عندما يكون جاهزًا.")),
    onSubmit(h("form", { class: "card" }, box,
      h("fieldset", {}, h("legend", {}, L("The project", "المشروع")), h("div", { class: "form-grid" },
        f("title", L("Project title", "عنوان المشروع"), { required: true, full: true, attrs: { minlength: 5 } }),
        field(L("Engineering discipline", "التخصص الهندسي"), sel("discipline_id", disciplineOptions(disc), p.discipline?.id, { "data-type": "int" }), { required: true }),
        field(L("Work arrangement", "طريقة العمل"), sel("work_mode", Object.keys(WORK_MODES).map(k => [k, workMode(k)]), p.work_mode || "hybrid"), { required: true }),
        f("location", L("Location (city / site)", "الموقع (المدينة / الموقع)"), { hint: L("Required for on-site or hybrid work.", "مطلوب للعمل الميداني أو المختلط.") }),
        f("description", L("Description", "الوصف"), { area: true, full: true, required: true, attrs: { minlength: 20 } }),
        f("scope", L("Scope of work", "نطاق العمل"), { area: true, full: true }),
        f("deliverables_text", L("Required deliverables", "التسليمات المطلوبة"), { area: true, full: true, hint: L("For example: design report (PDF), drawings (DWG), model (RVT).", "مثل: تقرير تصميم (PDF)، مخططات (DWG)، نموذج (RVT).") }),
        f("requirements", L("Technical requirements", "المتطلبات الفنية"), { area: true }),
        f("qualifications", L("Required qualifications", "المؤهلات المطلوبة"), { area: true }))),
      h("fieldset", {}, h("legend", {}, L("Budget & timing", "الميزانية والتوقيت")), h("div", { class: "form-grid" },
        field(L("Budget from (SAR, optional)", "الميزانية من (ريال، اختياري)"), moneyInput("budget_min_cents", p.budget_min_cents)),
        field(L("Budget up to (SAR)", "الميزانية حتى (ريال)"), moneyInput("max_budget_cents", p.max_budget_cents), { required: true }),
        f("duration_days", L("Expected duration (days)", "المدة المتوقعة (أيام)"), { attrs: { type: "number", min: 1, "data-type": "int" } }),
        f("proposal_deadline", L("Proposal submission deadline", "آخر موعد لتقديم العروض"), { attrs: { type: "date", min: todayISO(), "data-type": "nullable" } }),
        f("deadline", L("Target completion date", "تاريخ الإنجاز المستهدف"), { required: true, attrs: { type: "date", min: todayISO() } }))),
      h("div", { class: "btn-row" }, h("button", { class: "btn", type: "submit" }, id ? L("Save changes", "حفظ التغييرات") : L("Save as draft", "حفظ كمسودة")), linkBtn(id ? "/projects/" + id : "/projects", L("Cancel", "إلغاء"), "btn secondary"))),
    async (d) => {
      const r = id ? await api("/projects/" + id, { method: "PATCH", body: d }) : await api("/projects", { method: "POST", body: d });
      toast(L("Saved.", "تم الحفظ.")); go("/projects/" + r.id);
    }));
};

/* ---------------- project detail ---------------- */
B.views.project = async function ([id], q) {
  const p = await api("/projects/" + id);
  const role = p.my_role;
  const participant = ["org", "hired", "admin"].includes(role);
  const tab = q.get("tab") || "overview";
  const base = "/projects/" + id;
  const items = [["overview", L("Overview", "نظرة عامة")]];
  if (role === "org" || role === "admin" || role === "bidder" || role === "hired" || (role === "viewer" && isEng() && p.status === "published"))
    items.push(["proposals", role === "org" || role === "admin" ? L("Proposals", "العروض") : L("My proposal", "عرضي"), role === "org" ? p.proposal_count : null]);
  if (participant && p.accepted_proposal_id) items.push(["agreement", L("Agreement", "الاتفاقية")]);
  if (participant && !["draft", "published", "applications_closed", "under_evaluation", "shortlisted"].includes(p.status)) {
    items.push(["milestones", L("Milestones", "المراحل")], ["deliverables", L("Deliverables", "التسليمات")], ["tasks", L("Tasks", "المهام")]);
  }
  if (participant) items.push(["files", L("Files", "الملفات")], ["discussion", L("Discussion", "النقاش")], ["activity", L("Activity", "السجل")]);
  if (participant && p.accepted_proposal_id && (role !== "org" || can("finance.view") || can("work.manage"))) items.push(["finance", L("Finance", "المالية")]);
  const head = h("div", {},
    h("div", { class: "eyebrow" }, L("Model A · Project", "النموذج أ · مشروع"), p.is_demo ? " · " : "", p.is_demo ? demoTag(L("DEMO DATA", "بيانات تجريبية")) : null),
    pageHead(p.title, [p.organization ? nm(p.organization) : "", p.discipline ? " · " + nm(p.discipline) : ""].join(""), badge(p.status), p.is_delayed ? badge("cancelled", L("Delayed", "متأخر")) : null),
    !["cancelled", "disputed"].includes(p.status) ? stepper(FLOW_A, p.status) : null);
  let body;
  const views = { overview: projOverview, proposals: projProposals, agreement: projAgreement, milestones: projMilestones, deliverables: projDeliverables,
    tasks: projTasks, files: projFiles, discussion: projDiscussion, activity: projActivity, finance: projFinance };
  body = await (views[tab] || projOverview)(p);
  return h("div", {}, head, tabs(items, tab, base), body);
};

function projActions(p) {
  const out = [];
  const post = (path, body) => api(`/projects/${p.id}${path}`, { method: "POST", body: body ?? {} });
  const step = (to, label, opts) => action(label, () => post("/transitions", { to }), opts);
  if (p.my_role === "org") {
    const m = can("work.manage");
    if (m && ["draft", "published"].includes(p.status)) out.push(linkBtn(`/projects/${p.id}/edit`, L("Edit details", "تعديل التفاصيل"), "btn secondary"));
    if (m && p.status === "draft") out.push(action(L("Publish project", "نشر المشروع"), () => post("/publish"), { done: L("Published.", "تم النشر.") }));
    if (m && p.status === "published") out.push(step("applications_closed", L("Close proposals", "إغلاق استقبال العروض"), { cls: "btn secondary", confirm: L("Stop accepting new proposals? You can reopen later.", "إيقاف استقبال العروض الجديدة؟ يمكنك إعادة الفتح لاحقًا.") }));
    if (m && p.status === "applications_closed") out.push(step("under_evaluation", L("Start evaluation", "بدء التقييم")), step("published", L("Reopen for proposals", "إعادة فتح العروض"), { cls: "btn secondary" }));
    if (m && p.status === "proposal_accepted") {
      if (p.agreement_engineer_at) out.push(action(L("Confirm agreement & start work", "تأكيد الاتفاقية وبدء العمل"), () => post("/start"), { confirm: L("Confirm the agreement and start the work? Other open proposals will be closed.", "تأكيد الاتفاقية وبدء العمل؟ سيتم إغلاق العروض المفتوحة الأخرى."), done: L("Work started.", "بدأ العمل.") }));
      out.push(action(L("Withdraw selection", "التراجع عن الاختيار"), () => post("/unselect"), { cls: "btn secondary", confirm: L("Withdraw the selection and continue evaluating?", "التراجع عن الاختيار ومتابعة التقييم؟") }));
    }
    if (can("work.review") && ["submitted", "resubmitted"].includes(p.status)) {
      out.push(action(L("Request revision", "طلب تعديل"), (note) => post("/request-revision", { note }), { cls: "btn secondary", prompt: { message: L("What needs to change? The engineer will see this note.", "ما المطلوب تعديله؟ سيرى المهندس هذه الملاحظة."), input: "textarea", inputLabel: L("Revision note", "ملاحظة التعديل"), required: true, okLabel: L("Send revision request", "إرسال طلب التعديل") } }));
      if (m) out.push(action(L("Approve final delivery", "اعتماد التسليم النهائي"), () => post("/approve"), { confirm: L("Approve the final delivery? Simulated invoices for unpaid milestones and the final balance will be issued.", "اعتماد التسليم النهائي؟ ستصدر فواتير تجريبية للمراحل غير المدفوعة والرصيد النهائي."), done: L("Final delivery approved.", "تم اعتماد التسليم النهائي.") }));
    }
    if (m && p.status === "approved") out.push(action(L("Close project as completed", "إغلاق المشروع كمكتمل"), () => post("/complete"), { confirm: L("Close the project? All simulated invoices must be paid first.", "إغلاق المشروع؟ يجب دفع جميع الفواتير التجريبية أولاً.") }));
    if (m && ["draft", "published", "applications_closed", "under_evaluation", "shortlisted", "proposal_accepted"].includes(p.status))
      out.push(step("cancelled", L("Cancel project", "إلغاء المشروع"), { cls: "btn danger", confirm: L("Cancel this project? Engineers with open proposals will be told it was not awarded. This can't be undone.", "إلغاء هذا المشروع؟ سيُبلَّغ أصحاب العروض بعدم الترسية. لا يمكن التراجع.") }));
  }
  if (p.my_role === "hired") {
    if (p.status === "proposal_accepted" && !p.agreement_engineer_at) out.push(linkBtn(`/projects/${p.id}?tab=agreement`, L("Review & accept the agreement", "مراجعة الاتفاقية والموافقة")));
    if (["in_progress", "revision_requested"].includes(p.status)) out.push(action(p.status === "in_progress" ? L("Submit work for review", "تقديم العمل للمراجعة") : L("Resubmit for review", "إعادة التقديم للمراجعة"), (note) => post("/submit", { note }), { prompt: { message: L("Submit all deliverables for the organization's review? Add an optional note.", "تقديم جميع التسليمات لمراجعة الجهة؟ أضف ملاحظة اختيارية."), input: "textarea", inputLabel: L("Note (optional)", "ملاحظة (اختياري)"), okLabel: L("Submit for review", "تقديم للمراجعة") }, done: L("Submitted for review.", "تم التقديم للمراجعة.") }));
  }
  const canDispute = (p.my_role === "org" && can("dispute.raise")) || p.my_role === "hired";
  if (canDispute && ["in_progress", "submitted", "revision_requested", "resubmitted", "approved"].includes(p.status)) out.push(linkBtn(`/disputes/new?type=project&id=${p.id}`, L("Raise a dispute", "فتح نزاع"), "btn secondary"));
  if (p.status === "disputed" && p.dispute_id) out.push(linkBtn(`/disputes/${p.dispute_id}`, L("Open the dispute", "فتح ملف النزاع")));
  if (p.status === "completed" && ((p.my_role === "org" && can("work.manage")) || p.my_role === "hired") && !p.rated_by_me) out.push(rateButton(`/projects/${p.id}/ratings`, p.my_role === "org" ? L("Rate the engineer", "قيّم المهندس") : L("Rate the organization", "قيّم الجهة")));
  if (isEng() && p.my_role !== "hired" && p.organization && (p.my_role === "bidder")) out.push(action(L("Message the organization", "مراسلة الجهة"), async () => { const c = await api("/conversations", { method: "POST", body: { org_id: p.organization.id } }); go("/messages/" + c.id); }, { cls: "btn secondary" }));
  return out;
}

function rateButton(path, label) {
  return h("button", { class: "btn", type: "button", onclick: async () => {
    const box = errorBox();
    const form = h("form", { method: "dialog" }, h("h2", {}, label), box,
      field(L("Rating", "التقييم"), sel("rating", [5, 4, 3, 2, 1].map(n => [n, "★".repeat(n) + ` (${n})`]), 5, { "data-type": "int" })),
      field(L("Comment (optional)", "تعليق (اختياري)"), txt("text", { rows: 3 })),
      h("div", { class: "row end" }, h("button", { class: "btn secondary", type: "button", onclick: () => dlg.close() }, L("Go back", "رجوع")), h("button", { class: "btn", type: "submit" }, L("Submit rating", "إرسال التقييم"))));
    const dlg = h("dialog", {}, form);
    form.addEventListener("submit", async (ev) => { ev.preventDefault(); try { await api(path, { method: "POST", body: readForm(form) }); dlg.close(); dlg.remove(); toast(L("Thank you – rating saved.", "شكرًا – تم حفظ التقييم.")); B.render(); } catch (err) { showError(box, err); } });
    document.body.append(dlg); dlg.showModal();
  } }, label);
}

async function projOverview(p) {
  const acts = projActions(p);
  const notes = [];
  if (p.my_role === "org" && p.status === "draft") notes.push(notice("info", L("This project is a draft and visible only to your organization. Publish it to receive proposals.", "هذا المشروع مسودة ولا تراه إلا جهتك. انشره لتستقبل العروض.")));
  if (p.my_role === "org" && S.me.organization?.verification_status !== "verified" && p.status === "draft") notes.push(notice("warning", L("Your organization must be verified before publishing. ", "يجب توثيق جهتك قبل النشر. "), h("a", { href: "#/organization?tab=verification" }, L("Go to verification", "الانتقال إلى التوثيق"))));
  if (p.status === "proposal_accepted") notes.push(notice("info", p.agreement_engineer_at ? L("The engineer accepted the agreement. The organization can now confirm and start the work.", "وافق المهندس على الاتفاقية. يمكن للجهة الآن التأكيد وبدء العمل.") : L("Waiting for the selected engineer to accept the agreement.", "بانتظار موافقة المهندس المختار على الاتفاقية.")));
  if (["submitted", "resubmitted"].includes(p.status) && p.review_due_date) notes.push(notice(p.review_escalated ? "danger" : "warning",
    p.review_escalated ? L("The review window has passed. Nothing was approved automatically – the BUNYAH team has been asked to follow up.", "انتهت مهلة المراجعة. لم يتم أي اعتماد تلقائي – تم تصعيد الأمر لفريق بُنية للمتابعة.")
      : [L("Review window: please decide by ", "مهلة المراجعة: يرجى البت قبل "), fmtDate(p.review_due_date), L(". After that the item is escalated (never auto-approved).", ". بعد ذلك يتم التصعيد (دون اعتماد تلقائي).")]));
  if (p.status === "disputed") notes.push(notice("danger", L("A dispute is open. Approvals and simulated payments are paused until an administrator records a decision.", "يوجد نزاع مفتوح. توقفت الاعتمادات والمدفوعات التجريبية حتى تسجّل الإدارة قرارًا.")));
  return h("div", { class: "layout-side" },
    h("div", { class: "stack" }, ...notes,
      card(L("Project details", "تفاصيل المشروع"), h("p", { class: "prewrap" }, p.description),
        kv([[L("Scope of work", "نطاق العمل"), h("span", { class: "prewrap" }, p.scope || "—")], [L("Required deliverables", "التسليمات المطلوبة"), h("span", { class: "prewrap" }, p.deliverables_text || "—")],
          [L("Technical requirements", "المتطلبات الفنية"), h("span", { class: "prewrap" }, p.requirements || "—")], [L("Required qualifications", "المؤهلات المطلوبة"), h("span", { class: "prewrap" }, p.qualifications || "—")]]))),
    h("div", { class: "stack" },
      acts.length ? card(L("Next steps", "الخطوات التالية"), h("div", { class: "stack-sm" }, acts.map(a => h("div", {}, a)))) : null,
      card(L("Summary", "ملخص"), kv([
        [L("Organization", "الجهة"), p.organization ? h("a", { href: "#/org/" + p.organization.id }, nm(p.organization)) : "—"],
        [L("Budget", "الميزانية"), [p.budget_min_cents ? [money(p.budget_min_cents), " – "] : "", money(p.max_budget_cents)]],
        p.agreed_price_cents ? [L("Agreed price", "السعر المتفق عليه"), money(p.agreed_price_cents)] : null,
        [L("Work arrangement", "طريقة العمل"), workMode(p.work_mode) + (p.location ? " · " + p.location : "")],
        [L("Expected duration", "المدة المتوقعة"), p.duration_days ? L(`${p.duration_days} days`, `${p.duration_days} يومًا`) : "—"],
        [L("Proposals until", "العروض حتى"), fmtDate(p.proposal_deadline)], [L("Target completion", "الإنجاز المستهدف"), fmtDate(p.deadline)],
        p.engineer ? [L("Engineer", "المهندس"), h("a", { href: "#/engineers/" + p.engineer.id }, p.engineer.name)] : null,
        p.my_org_role ? [L("Your role", "دورك"), orgRole(p.my_org_role)] : null]))));
}

/* ---------- proposals ---------- */
async function projProposals(p) {
  const list = await api(`/projects/${p.id}/proposals`);
  if (p.my_role === "org" || p.my_role === "admin") return orgProposals(p, list);
  const mine = list[0];
  return h("div", { class: "grid grid-2", style: "align-items:start" }, mine ? proposalDetail(p, mine) : null,
    (!mine || ["submitted", "clarification_requested", "withdrawn"].includes(mine.status)) && p.status === "published" ? proposalForm(p, mine) : (!mine ? notice("info", L("This project is not accepting proposals.", "هذا المشروع لا يستقبل العروض.")) : null));
}

function proposalForm(p, mine) {
  const box = errorBox();
  const blocked = S.me.verification_status !== "verified";
  return onSubmit(h("form", { class: "card" }, h("h2", {}, mine ? L("Update your proposal", "تحديث عرضك") : L("Submit a proposal", "تقديم عرض")), box,
    blocked ? notice("warning", L("Your profile must be verified before you can send proposals. ", "يجب توثيق ملفك قبل تقديم العروض. "), h("a", { href: "#/profile?tab=verification" }, L("Go to verification", "الانتقال إلى التوثيق"))) : null,
    h("div", { class: "form-grid" },
      field(L("Price (SAR)", "السعر (ريال)"), moneyInput("price_cents", mine?.price_cents), { required: true, hint: [L("Maximum budget: ", "الحد الأقصى للميزانية: "), money(p.max_budget_cents, { plain: true })].join("") }),
      field(L("Expected duration (days)", "المدة المتوقعة (أيام)"), inp("duration_days", { type: "number", min: 1, value: mine?.duration_days ?? "", "data-type": "int" })),
      field(L("Delivery date", "تاريخ التسليم"), inp("delivery_date", { type: "date", min: todayISO(), max: p.deadline, value: mine?.delivery_date || "" }), { required: true }),
      field(L("Summary / cover letter", "الملخص / خطاب التقديم"), txt("message", { value: mine?.summary || "", minlength: 20 }), { required: true, full: true }),
      field(L("Technical approach & methodology", "المنهجية والأسلوب الفني"), txt("technical_approach", { value: mine?.technical_approach || "", minlength: 20, rows: 6 }), { required: true, full: true })),
    h("button", { class: "btn", type: "submit", disabled: blocked }, mine ? L("Update proposal", "تحديث العرض") : L("Submit proposal", "تقديم العرض"))),
  async (d) => { await api(`/projects/${p.id}/proposals`, { method: "POST", body: d }); toast(L("Proposal sent.", "تم إرسال العرض.")); B.render(); });
}

function proposalDetail(p, o) {
  const open = ["submitted", "shortlisted", "clarification_requested"].includes(o.status);
  return card(L("Your proposal", "عرضك"),
    h("p", {}, badge(o.status)),
    kv([[L("Price", "السعر"), money(o.price_cents)], [L("Delivery", "التسليم"), fmtDate(o.delivery_date)], [L("Duration", "المدة"), o.duration_days ? L(`${o.duration_days} days`, `${o.duration_days} يومًا`) : "—"],
      [L("Summary", "الملخص"), h("span", { class: "prewrap" }, o.summary)], [L("Approach", "المنهجية"), h("span", { class: "prewrap" }, o.technical_approach)],
      o.decision_note ? [L("Organization's note", "ملاحظة الجهة"), o.decision_note] : null]),
    h("h3", { class: "section-title" }, L("Attachments", "المرفقات")),
    o.attachments.length ? h("ul", {}, o.attachments.map(f => h("li", {}, fileLink(f), " ", h("span", { class: "muted small" }, sizeLabel(f.size))))) : h("p", { class: "muted small" }, L("No attachments.", "لا توجد مرفقات.")),
    open ? uploadForm(`/proposals/${o.id}/attachments`, { label: L("Add a portfolio document or reference", "إضافة مستند من أعمالك أو مرجع"), button: L("Attach", "إرفاق") }) : null,
    clarifications(o, true),
    open ? h("div", { style: "margin-top:1rem" }, action(L("Withdraw proposal", "سحب العرض"), () => api(`/proposals/${o.id}/withdraw`, { method: "POST" }), { cls: "btn danger small", confirm: L("Withdraw your proposal? You can send a new one while the project is published.", "سحب عرضك؟ يمكنك تقديم عرض جديد ما دام المشروع منشورًا.") })) : null);
}

function clarifications(o, asEngineer) {
  const items = o.clarifications || [];
  const box = errorBox();
  const reply = asEngineer && ["submitted", "shortlisted", "clarification_requested"].includes(o.status) && items.length
    ? onSubmit(h("form", { class: "stack-sm" }, box, field(L("Your answer", "إجابتك"), txt("body", { rows: 2 }), { required: true }), h("button", { class: "btn small", type: "submit" }, L("Send answer", "إرسال الإجابة"))),
      async (d) => { await api(`/proposals/${o.id}/clarifications`, { method: "POST", body: d }); toast(L("Answer sent.", "تم إرسال الإجابة.")); B.render(); }) : null;
  return h("div", {}, h("h3", { class: "section-title" }, L("Clarifications", "الاستيضاحات")),
    items.length ? h("ul", { class: "list" }, items.map(c => h("li", {}, h("strong", {}, c.author.name), " · ", h("span", { class: "muted small" }, fmtTime(c.created_at)), h("p", { class: "prewrap", style: "margin:0" }, c.body)))) : h("p", { class: "muted small" }, L("No questions yet.", "لا توجد استفسارات.")),
    reply);
}

function orgProposals(p, list) {
  if (!list.length) return empty(L("No proposals yet", "لا توجد عروض بعد"), p.status === "draft" ? L("Publish the project to receive proposals.", "انشر المشروع لتستقبل العروض.") : L("Verified engineers will see your project in the marketplace.", "سيرى المهندسون الموثّقون مشروعك في السوق."));
  const evaluating = ["published", "applications_closed", "under_evaluation", "shortlisted"].includes(p.status);
  const canSelect = ["under_evaluation", "shortlisted"].includes(p.status) && can("work.manage");
  const openOnes = list.filter(o => ["submitted", "shortlisted", "clarification_requested", "accepted"].includes(o.status));
  const compare = openOnes.length > 1 ? h("div", { class: "card flat" }, h("h2", {}, L("Side-by-side comparison", "مقارنة جنبًا إلى جنب")),
    h("div", { class: "table-wrap" }, h("table", { class: "data compare" }, h("thead", {}, h("tr", {}, h("th", {}, ""), openOnes.map(o => h("th", { scope: "col" }, o.engineer.name)))),
      h("tbody", {}, [
        [L("Status", "الحالة"), o => badge(o.status)], [L("Price", "السعر"), o => money(o.price_cents)], [L("Duration", "المدة"), o => o.duration_days ? L(`${o.duration_days} days`, `${o.duration_days} يومًا`) : "—"],
        [L("Delivery", "التسليم"), o => fmtDate(o.delivery_date)], [L("Experience", "الخبرة"), o => L(`${o.engineer.years_experience} years`, `${o.engineer.years_experience} سنة`)],
        [L("Verified", "موثّق"), o => o.engineer.verified ? badge("verified") : badge("unverified")], [L("Rating", "التقييم"), o => o.engineer.average_rating ? stars(o.engineer.average_rating) : "—"],
        [L("Approach", "المنهجية"), o => h("span", { class: "small" }, o.technical_approach.slice(0, 220) + (o.technical_approach.length > 220 ? "…" : ""))],
      ].map(([label, fn]) => h("tr", {}, h("th", { scope: "row" }, label), openOnes.map(o => h("td", {}, fn(o))))))))) : null;
  const rows = list.map(o => {
    const open = ["submitted", "shortlisted", "clarification_requested"].includes(o.status);
    const btns = [];
    if (open && evaluating && can("work.manage")) {
      if (o.status !== "shortlisted" && p.status !== "published") btns.push(action(L("Shortlist", "إضافة للقائمة المختصرة"), () => api(`/proposals/${o.id}/decision`, { method: "POST", body: { decision: "shortlist" } }), { cls: "btn secondary small" }));
      btns.push(action(L("Ask a question", "طلب توضيح"), (note) => api(`/proposals/${o.id}/decision`, { method: "POST", body: { decision: "clarify", note } }), { cls: "btn secondary small", prompt: { message: L(`Your question to ${o.engineer.name}`, `استفسارك إلى ${o.engineer.name}`), input: "textarea", inputLabel: L("Question", "الاستفسار"), required: true, okLabel: L("Send question", "إرسال الاستفسار") } }));
      btns.push(action(L("Decline", "رفض"), (note) => api(`/proposals/${o.id}/decision`, { method: "POST", body: { decision: "reject", note } }), { cls: "btn ghost small", prompt: { message: L(`Decline the proposal from ${o.engineer.name}?`, `رفض عرض ${o.engineer.name}؟`), input: "textarea", inputLabel: L("Reason (optional, shared with the engineer)", "السبب (اختياري، يُرسل للمهندس)"), okLabel: L("Decline proposal", "رفض العرض") } }));
    }
    if (open && canSelect) btns.push(action(L("Select this engineer", "اختيار هذا المهندس"), () => api(`/proposals/${o.id}/accept`, { method: "POST" }), { cls: "btn small", confirm: L(`Select ${o.engineer.name} for ${money(o.price_cents, { plain: true })}? They will be asked to accept the agreement.`, `اختيار ${o.engineer.name} بمبلغ ${money(o.price_cents, { plain: true })}؟ سيُطلب منه الموافقة على الاتفاقية.`), done: L("Engineer selected.", "تم اختيار المهندس.") }));
    if (can("messages.send")) btns.push(action(L("Message", "مراسلة"), async () => { const c = await api("/conversations", { method: "POST", body: { user_id: o.engineer.id } }); go("/messages/" + c.id); }, { cls: "btn ghost small" }));
    return h("details", { class: "card flat", open: list.length === 1 ? true : null },
      h("summary", { class: "row between", style: "cursor:pointer;list-style:none" },
        h("span", {}, h("strong", {}, o.engineer.name), " ", o.engineer.verified ? badge("verified") : null, h("span", { class: "muted small" }, " · " + (o.engineer.title || ""))),
        h("span", { class: "row" }, money(o.price_cents), badge(o.status))),
      h("div", { style: "margin-top:.75rem" },
        kv([[L("Delivery", "التسليم"), fmtDate(o.delivery_date)], [L("Summary", "الملخص"), h("span", { class: "prewrap" }, o.summary)], [L("Technical approach", "المنهجية"), h("span", { class: "prewrap" }, o.technical_approach)],
          [L("Engineer profile", "ملف المهندس"), h("a", { href: "#/engineers/" + o.engineer.id }, L("View profile", "عرض الملف"))],
          [L("Attachments", "المرفقات"), o.attachments.length ? o.attachments.map(f => h("div", {}, fileLink(f))) : "—"]]),
        clarifications(o, false), h("div", { class: "btn-row", style: "margin-top:.75rem" }, btns)));
  });
  return h("div", { class: "stack" },
    p.status === "published" ? notice("info", L("Close proposal submissions to start shortlisting and selecting. You can already ask questions or decline.", "أغلق استقبال العروض لبدء إعداد القائمة المختصرة والاختيار. يمكنك الآن طرح الأسئلة أو الرفض.")) : null,
    compare, ...rows);
}

/* ---------- agreement ---------- */
async function projAgreement(p) {
  const a = await api(`/projects/${p.id}/agreement`);
  const accept = p.my_role === "hired" && p.status === "proposal_accepted" && !a.engineer_accepted_at
    ? action(L("I accept this agreement", "أوافق على هذه الاتفاقية"), () => api(`/projects/${p.id}/agreement/accept`, { method: "POST" }), { confirm: L("Accept the agreement summary? The organization will then confirm and start the work.", "الموافقة على ملخص الاتفاقية؟ ستقوم الجهة بعدها بالتأكيد وبدء العمل."), done: L("Agreement accepted.", "تمت الموافقة على الاتفاقية.") }) : null;
  return card(L("Project agreement (summary)", "اتفاقية المشروع (ملخص)"),
    notice("warning", L(a.notice_en, a.notice_ar)),
    kv([[L("Organization", "الجهة"), a.organization], [L("Engineer", "المهندس"), a.engineer], [L("Agreed price", "السعر المتفق عليه"), money(a.price_cents)],
      [L("Delivery date", "تاريخ التسليم"), fmtDate(a.delivery_date)], [L("Scope", "النطاق"), h("span", { class: "prewrap" }, a.scope)],
      [L("Deliverables", "التسليمات"), h("span", { class: "prewrap" }, a.deliverables || "—")],
      [L("Milestones", "المراحل"), a.milestones.length ? h("ol", { style: "margin:0;padding-inline-start:1.2rem" }, a.milestones.map(m => h("li", {}, m.title, " – ", money(m.amount_cents)))) : L("No milestones (single final payment).", "بدون مراحل (دفعة نهائية واحدة).")],
      [L("Payment basis", "أساس الدفع"), L(a.payment_basis_en, a.payment_basis_ar)],
      [L("Engineer accepted", "موافقة المهندس"), a.engineer_accepted_at ? fmtTime(a.engineer_accepted_at) : L("Not yet", "لم تتم بعد")],
      [L("Organization confirmed", "تأكيد الجهة"), a.org_confirmed_at ? fmtTime(a.org_confirmed_at) : L("Not yet", "لم يتم بعد")]]),
    accept ? h("div", { style: "margin-top:1rem" }, accept) : null);
}

/* ---------- milestones ---------- */
async function projMilestones(p) {
  const ms = await api(`/projects/${p.id}/milestones`);
  const manage = p.my_role === "org" && can("work.manage");
  const editable = ["proposal_accepted", "in_progress", "revision_requested"].includes(p.status);
  const total = ms.reduce((s, m) => s + m.amount_cents, 0);
  const box = errorBox();
  const addForm = manage && editable && ms.length < 6 ? onSubmit(h("form", { class: "card" }, h("h2", {}, L("Add a milestone", "إضافة مرحلة")), box,
    h("div", { class: "form-grid" }, field(L("Title", "العنوان"), inp("title"), { required: true }), field(L("Amount (SAR)", "المبلغ (ريال)"), moneyInput("amount_cents", null, { placeholder: "0" }), { required: true, hint: L("Any amount – there is no minimum.", "أي مبلغ – لا يوجد حد أدنى.") }),
      field(L("Due date", "تاريخ الاستحقاق"), inp("due_date", { type: "date", "data-type": "nullable" })), field(L("Description", "الوصف"), txt("description", { rows: 2 }))),
    h("button", { class: "btn", type: "submit" }, L("Add milestone", "إضافة المرحلة"))),
  async (d) => { d.amount_cents = d.amount_cents ?? 0; await api(`/projects/${p.id}/milestones`, { method: "POST", body: d }); toast(L("Milestone added.", "تمت إضافة المرحلة.")); B.render(); }) : null;
  return h("div", { class: "stack" },
    notice("info", L(`Milestones are optional (up to 6). ${ms.length} of 6 used. Each approved milestone issues a simulated invoice; anything not covered by milestones is invoiced as the final payment.`,
      `المراحل اختيارية (حتى 6). المستخدم ${ms.length} من 6. كل مرحلة معتمدة تُصدر فاتورة تجريبية، وما لا تغطيه المراحل يُفوتر كدفعة نهائية.`)),
    card(L("Payment schedule", "جدول الدفعات"), h("div", { class: "grid grid-3" }, stat(L("Agreed price", "السعر المتفق عليه"), money(p.agreed_price_cents)), stat(L("In milestones", "في المراحل"), money(total)), stat(L("Final payment", "الدفعة النهائية"), money(Math.max((p.agreed_price_cents || 0) - total, 0))))),
    card(null, table([
      { label: "#", render: m => m.seq }, { label: L("Milestone", "المرحلة"), render: m => [h("strong", {}, m.title), m.description ? h("div", { class: "muted small" }, m.description) : null] },
      { label: L("Amount", "المبلغ"), num: true, render: m => money(m.amount_cents) }, { label: L("Due", "الاستحقاق"), render: m => fmtDate(m.due_date) },
      { label: L("Status", "الحالة"), render: m => badge(m.status) },
      { label: "", render: m => h("div", { class: "btn-row" },
        manage && m.status !== "approved" && ["in_progress", "submitted", "revision_requested", "resubmitted", "approved"].includes(p.status) ? action(L("Approve milestone", "اعتماد المرحلة"), () => api(`/milestones/${m.id}/approve`, { method: "POST" }), { cls: "btn small", confirm: L(`Approve "${m.title}"? All its deliverables must already be approved; a simulated invoice will be issued.`, `اعتماد «${m.title}»؟ يجب أن تكون كل تسليماتها معتمدة، وستصدر فاتورة تجريبية.`), done: L("Milestone approved.", "تم اعتماد المرحلة.") }) : null,
        manage && editable && m.status === "planned" ? action(L("Remove", "حذف"), () => api(`/milestones/${m.id}`, { method: "DELETE" }), { cls: "btn ghost small", confirm: L(`Remove "${m.title}"?`, `حذف «${m.title}»؟`) }) : null) },
    ], ms, { empty: L("No milestones – the whole price is paid once at final approval.", "لا توجد مراحل – يُدفع كامل السعر عند الاعتماد النهائي.") })),
    addForm);
}

/* ---------- deliverables (versioned) ---------- */
async function projDeliverables(p) {
  const [ds, ms] = await Promise.all([api(`/projects/${p.id}/deliverables`), api(`/projects/${p.id}/milestones`)]);
  const reviewer = p.my_role === "org" && can("work.review");
  const hired = p.my_role === "hired";
  const msName = id => (ms.find(m => m.id === id) || {}).title;
  const cards = ds.map(d => {
    const latest = d.versions[d.versions.length - 1];
    const canUpload = hired && ["in_progress", "revision_requested"].includes(p.status) && d.status !== "approved";
    const canReview = reviewer && latest && latest.review_status === "under_review" && ["in_progress", "submitted", "resubmitted"].includes(p.status);
    return h("section", { class: "card" },
      h("div", { class: "card-head" }, h("div", {}, h("h3", { style: "margin:0" }, d.title), d.milestone_id ? h("div", { class: "muted small" }, L("Milestone: ", "المرحلة: "), msName(d.milestone_id)) : null), badge(d.status)),
      d.description ? h("p", { class: "muted small" }, d.description) : null,
      d.versions.length ? h("div", {}, [...d.versions].reverse().map(v => h("div", { class: "version" + (v === latest ? " latest" : "") },
        h("div", { class: "row between" }, h("span", {}, h("span", { class: "vno" }, "V" + v.version_no), " ", fileLink(v.file), " ", h("span", { class: "muted small" }, sizeLabel(v.file.size))), badge(v.review_status)),
        h("div", { class: "meta" }, h("span", {}, L("Uploaded by ", "رفعها "), v.uploaded_by.name), h("span", {}, fmtTime(v.created_at)), v.reviewed_by ? h("span", {}, L("Reviewed by ", "راجعها "), v.reviewed_by.name, " · ", fmtTime(v.reviewed_at)) : null),
        v.note ? h("p", { class: "small", style: "margin:.3rem 0 0" }, L("Engineer's note: ", "ملاحظة المهندس: "), h("bdi", {}, v.note)) : null,
        v.review_comment ? h("p", { class: "small", style: "margin:.3rem 0 0" }, h("strong", {}, L("Review comment: ", "تعليق المراجعة: ")), h("bdi", {}, v.review_comment)) : null,
        v === latest && canReview ? h("div", { class: "btn-row", style: "margin-top:.5rem" },
          action(L("Approve this version", "اعتماد هذه النسخة"), () => api(`/deliverable-versions/${v.id}/review`, { method: "POST", body: { decision: "approved", comment: "" } }), { cls: "btn small", done: L("Version approved.", "تم اعتماد النسخة.") }),
          action(L("Request revision", "طلب تعديل"), (comment) => api(`/deliverable-versions/${v.id}/review`, { method: "POST", body: { decision: "revision_requested", comment } }), { cls: "btn secondary small", prompt: { message: L(`What should change in V${v.version_no}?`, `ما المطلوب تعديله في V${v.version_no}؟`), input: "textarea", inputLabel: L("Review comment", "تعليق المراجعة"), required: true, okLabel: L("Request revision", "طلب تعديل") } })) : null)))
        : h("p", { class: "muted" }, L("No version uploaded yet.", "لم يتم رفع أي نسخة بعد.")),
      canUpload ? h("details", { style: "margin-top:.75rem", open: d.status === "revision_requested" || !d.versions.length ? true : null }, h("summary", {}, L(`Upload V${(latest?.version_no || 0) + 1}`, `رفع النسخة V${(latest?.version_no || 0) + 1}`)),
        uploadForm(`/deliverables/${d.id}/versions`, { label: L("Deliverable file", "ملف التسليم"), button: L("Upload new version", "رفع نسخة جديدة"), extra: [field(L("What changed (optional)", "ما الذي تغيّر (اختياري)"), txt("note", { rows: 2 }))] })) : null);
  });
  const box = errorBox();
  const addForm = ((p.my_role === "org" && can("work.manage")) || hired) && ["proposal_accepted", "in_progress", "revision_requested"].includes(p.status)
    ? onSubmit(h("form", { class: "card" }, h("h2", {}, L("Define a deliverable", "تعريف تسليم")), box,
      h("div", { class: "form-grid" }, field(L("Title", "العنوان"), inp("title"), { required: true }),
        field(L("Milestone (optional)", "المرحلة (اختياري)"), sel("milestone_id", [["", L("None", "بدون")], ...ms.map(m => [m.id, `${m.seq}. ${m.title}`])], "", { "data-type": "int" })),
        field(L("Description", "الوصف"), txt("description", { rows: 2 }), { full: true })),
      h("button", { class: "btn", type: "submit" }, L("Add deliverable", "إضافة التسليم"))),
    async (d) => { await api(`/projects/${p.id}/deliverables`, { method: "POST", body: d }); toast(L("Deliverable added.", "تمت إضافة التسليم.")); B.render(); }) : null;
  return h("div", { class: "stack" },
    notice("info", L("Versions are never overwritten: each correction is a new version (V1 → review → V2 → final approval) and every version keeps its file, uploader, date and review comment.",
      "لا يتم استبدال النسخ أبدًا: كل تعديل نسخة جديدة (V1 ← مراجعة ← V2 ← اعتماد نهائي)، وتحتفظ كل نسخة بملفها ورافعها وتاريخها وتعليق مراجعتها.")),
    ...(cards.length ? cards : [empty(L("No deliverables yet", "لا توجد تسليمات بعد"), L("Define the expected deliverables so the engineer can upload versions.", "عرّف التسليمات المتوقعة ليتمكن المهندس من رفع النسخ."))]), addForm);
}

/* ---------- tasks ---------- */
async function projTasks(p) {
  const [ts, ms] = await Promise.all([api(`/projects/${p.id}/tasks`), api(`/projects/${p.id}/milestones`)]);
  const editable = (p.my_role === "hired" || (p.my_role === "org" && can("work.manage"))) && ["proposal_accepted", "in_progress", "submitted", "revision_requested", "resubmitted", "approved"].includes(p.status);
  const box = errorBox();
  return h("div", { class: "stack" }, card(L("Tasks", "المهام"), table([
    { label: L("Task", "المهمة"), render: t => t.title }, { label: L("Milestone", "المرحلة"), render: t => (ms.find(m => m.id === t.milestone_id) || {}).title || "—" },
    { label: L("Assigned to", "مسندة إلى"), render: t => t.assignee ? t.assignee.name : "—" }, { label: L("Due", "الاستحقاق"), render: t => fmtDate(t.due_date) },
    { label: L("Status", "الحالة"), render: t => editable ? sel("s", [["todo", statusLabel("todo")], ["in_progress", statusLabel("in_progress")], ["done", statusLabel("done")]], t.status, { "aria-label": L("Status", "الحالة"), onchange: async (e) => {
      try { await api(`/tasks/${t.id}`, { method: "PATCH", body: { title: t.title, status: e.target.value, milestone_id: t.milestone_id, assignee_id: t.assignee?.id ?? null, due_date: t.due_date } }); toast(L("Task updated.", "تم تحديث المهمة.")); } catch (err) { toast(err.message, true); } } }) : badge(t.status) },
  ], ts, { empty: L("No tasks yet.", "لا توجد مهام بعد.") })),
  editable ? onSubmit(h("form", { class: "card" }, h("h2", {}, L("Add a task", "إضافة مهمة")), box, h("div", { class: "form-grid" },
    field(L("Task", "المهمة"), inp("title"), { required: true }), field(L("Milestone", "المرحلة"), sel("milestone_id", [["", L("None", "بدون")], ...ms.map(m => [m.id, m.title])], "", { "data-type": "int" })),
    field(L("Due date", "تاريخ الاستحقاق"), inp("due_date", { type: "date", "data-type": "nullable" })),
    field(L("Assign to the engineer", "إسناد للمهندس"), sel("assignee_id", [["", L("Unassigned", "غير مسندة")], ...(p.engineer ? [[p.engineer.id, p.engineer.name]] : [])], "", { "data-type": "int" }))),
    h("button", { class: "btn", type: "submit" }, L("Add task", "إضافة المهمة"))),
  async (d) => { await api(`/projects/${p.id}/tasks`, { method: "POST", body: d }); toast(L("Task added.", "تمت إضافة المهمة.")); B.render(); }) : null);
}

/* ---------- files, discussion, activity ---------- */
async function projFiles(p) {
  const files = await api(`/projects/${p.id}/files`);
  const canBrief = p.my_role === "org" && can("work.manage");
  const canWork = p.my_role === "org" || p.my_role === "hired";
  const kindSel = sel("kind", [...(canBrief ? [["brief", L("Brief / reference (visible to bidders while published)", "مرجع / كراسة (يراها مقدمو العروض أثناء النشر)")]] : []), ["working", L("Working file (participants only)", "ملف عمل (للمشاركين فقط)")]], canBrief ? "brief" : "working");
  return h("div", { class: "stack" }, card(L("Project files", "ملفات المشروع"),
    h("p", { class: "muted small" }, L("Deliverable versions are on the Deliverables tab. Files here can be archived by their uploader; nothing is permanently deleted.", "نسخ التسليمات موجودة في تبويب التسليمات. يمكن لرافع الملف أرشفته هنا، ولا يُحذف شيء نهائيًا.")),
    table([{ label: L("File", "الملف"), render: f => fileLink(f) }, { label: L("Type", "النوع"), render: f => f.kind === "brief" ? L("Brief", "مرجع") : L("Working", "عمل") },
      { label: L("Uploaded by", "رفعه"), render: f => f.owner.name }, { label: L("Date", "التاريخ"), render: f => fmtTime(f.created_at) }, { label: L("Size", "الحجم"), num: true, render: f => sizeLabel(f.size) },
      { label: "", render: f => f.owner.id === S.me.id && !["completed", "cancelled"].includes(p.status) ? action(L("Archive", "أرشفة"), () => api(`/files/${f.id}`, { method: "DELETE" }), { cls: "btn ghost small", confirm: L(`Archive ${f.filename}? It will be hidden from this list but kept on record.`, `أرشفة ${f.filename}؟ سيُخفى من القائمة لكنه يبقى محفوظًا.`) }) : "" }], files, { empty: L("No files yet.", "لا توجد ملفات بعد.") })),
  canWork && !["completed", "cancelled"].includes(p.status) ? card(L("Upload a file", "رفع ملف"), uploadForm(`/projects/${p.id}/files`, { extra: [field(L("Type", "النوع"), kindSel), field(L("Note (optional)", "ملاحظة (اختياري)"), inp("note"))] })) : null);
}

async function projDiscussion(p) {
  const cs = await api(`/projects/${p.id}/comments`);
  const box = errorBox();
  const reviewer = p.my_role === "org" && can("work.review");
  const canPost = p.my_role === "hired" || (p.my_role === "org" && can("messages.send"));
  return h("div", { class: "stack" }, card(L("Discussion & technical reviews", "النقاش والمراجعات الفنية"),
    cs.length ? h("ul", { class: "list" }, cs.map(c => h("li", {}, h("div", { class: "row" }, h("strong", {}, c.author.name), c.kind === "technical_review" ? badge("under_review", L("Technical review", "مراجعة فنية")) : null, h("span", { class: "muted small" }, fmtTime(c.created_at))),
      h("p", { class: "prewrap", dir: "auto", style: "margin:.25rem 0 0" }, c.body)))) : h("p", { class: "muted" }, L("No comments yet.", "لا توجد تعليقات بعد.")),
    canPost && p.status !== "cancelled" ? onSubmit(h("form", { class: "stack-sm", style: "margin-top:1rem" }, box, field(L("Write a comment", "اكتب تعليقًا"), txt("body", { rows: 3 }), { required: true }),
      reviewer ? field(L("Type", "النوع"), sel("kind", [["comment", L("Comment", "تعليق")], ["technical_review", L("Technical review", "مراجعة فنية")]], "comment")) : null,
      h("button", { class: "btn", type: "submit" }, L("Post", "نشر"))),
    async (d) => { await api(`/projects/${p.id}/comments`, { method: "POST", body: d }); B.render(); }) : null));
}

async function activity(path) {
  const ev = await api(path);
  return card(L("Activity history", "سجل النشاط"), ev.length ? h("ol", { class: "timeline" }, [...ev].reverse().map(e => h("li", {}, fmtTime(e.created_at), L(e.text, e.text_ar || e.text)))) : h("p", { class: "muted" }, L("No activity yet.", "لا يوجد نشاط بعد.")));
}
const projActivity = (p) => activity(`/projects/${p.id}/events`);

/* ---------- finance ---------- */
function invoiceTable(invs, { pay, title } = {}) {
  return table([
    { label: L("Invoice", "الفاتورة"), render: i => [h("span", { class: "ltr" }, i.number), h("div", { class: "muted small" }, i.description || i.title || "")] },
    { label: L("Amount", "المبلغ"), num: true, render: i => money(i.subtotal_cents) },
    { label: L("Org. fee", "رسوم الجهة"), num: true, render: i => money(i.org_fee_cents) },
    { label: L("VAT", "الضريبة"), num: true, render: i => i.vat_percent ? [money(i.vat_cents), ` (${i.vat_percent}%)`] : L("Not applied*", "غير مطبقة*") },
    { label: L("Total for organization", "الإجمالي على الجهة"), num: true, render: i => h("strong", {}, money(i.total_cents)) },
    { label: L("Engineer receives", "صافي المهندس"), num: true, render: i => money(i.engineer_net_cents) },
    { label: L("Status", "الحالة"), render: i => badge(i.status) },
    pay ? { label: "", render: i => i.status === "issued" && can("finance.pay") ? action(L("Record simulated payment", "تسجيل دفعة تجريبية"), () => api(`/invoices/${i.id}/pay`, { method: "POST" }), { cls: "btn small", confirm: L(`Record a SIMULATED payment of ${money(i.total_cents, { plain: true })}? No real money moves.`, `تسجيل دفعة تجريبية بمبلغ ${money(i.total_cents, { plain: true })}؟ لا تتم أي حركة مالية حقيقية.`), done: L("Simulated payment recorded.", "تم تسجيل الدفعة التجريبية.") }) : "" } : null,
  ].filter(Boolean), invs, { empty: title || L("No invoices yet. Invoices are issued when a milestone or the final delivery is approved.", "لا توجد فواتير بعد. تصدر الفواتير عند اعتماد مرحلة أو التسليم النهائي.") });
}
function txTable(txs) {
  const kinds = { payment: L("Payment", "دفعة"), payout: L("Payout to engineer", "تحويل للمهندس"), refund: L("Refund", "استرداد") };
  return table([{ label: L("Reference", "المرجع"), render: t => h("span", { class: "ltr" }, t.ref) }, { label: L("Type", "النوع"), render: t => kinds[t.kind] || t.kind },
    { label: L("Gross", "الإجمالي"), num: true, render: t => money(t.gross_cents) }, { label: L("Engineer net", "صافي المهندس"), num: true, render: t => money(t.engineer_net_cents) },
    { label: L("Status", "الحالة"), render: t => badge(t.status === "completed" ? "done" : t.status, t.status === "completed" ? L("Completed (demo)", "منفذة (تجريبي)") : null) }, { label: L("Date", "التاريخ"), render: t => fmtTime(t.created_at) }], txs, { empty: L("No transactions yet.", "لا توجد عمليات بعد.") });
}
function feeNote(rule) {
  if (!rule || !rule.rule_id) return L("No platform fee rule is active.", "لا توجد قاعدة رسوم مفعلة.");
  const v = (x) => rule.fee_type === "percent" ? (x / 100) + "%" : money(x, { plain: true });
  const payer = { organization: L("organization", "الجهة"), engineer: L("engineer", "المهندس"), both: L("both parties", "الطرفان") }[rule.payer];
  return L(`Platform fee (configurable by administrators; demo values): paid by ${payer} – organization ${v(rule.org_value)}, engineer ${v(rule.engineer_value)}.`,
    `رسوم المنصة (قابلة للتعديل من الإدارة؛ قيم تجريبية): يدفعها ${payer} – الجهة ${v(rule.org_value)}، المهندس ${v(rule.engineer_value)}.`);
}
async function projFinance(p) {
  const f = await api(`/projects/${p.id}/finance`);
  return h("div", { class: "stack" },
    notice("warning", h("strong", {}, L("Simulated finance. ", "مالية تجريبية. ")), L("No real payment is processed, no card details are collected and BUNYAH does not hold any funds. Payment custody, provider and tax treatment are pending professional review.",
      "لا تتم معالجة أي دفع حقيقي ولا تُجمع بيانات بطاقات ولا تحتفظ بُنية بأي أموال. حفظ الأموال ومزود الدفع والمعاملة الضريبية بانتظار المراجعة المهنية.")),
    h("div", { class: "grid grid-4" }, stat(L("Agreed price", "السعر المتفق عليه"), money(f.agreed_price_cents)), stat(L("Invoiced", "المفوتر"), money(f.invoiced_cents)),
      stat(L("Paid (demo)", "المدفوع (تجريبي)"), money(f.paid_cents)), stat(L("Outstanding", "المستحق"), money(f.outstanding_cents))),
    card(null, h("div", { class: "row between" }, h("h2", { style: "margin:0" }, L("Invoices", "الفواتير")), demoTag()), h("p", { class: "muted small" }, feeNote(f.fee_rule)), invoiceTable(f.invoices, { pay: p.my_role === "org" }),
      h("p", { class: "muted small" }, L("* VAT is set to 0% until the tax treatment is confirmed by an accountant (admin setting).", "* ضريبة القيمة المضافة 0% حتى يؤكد المحاسب المعاملة الضريبية (إعداد إداري)."))),
    card(null, h("div", { class: "row between" }, h("h2", { style: "margin:0" }, L("Transaction history", "سجل العمليات")), demoTag()), txTable(f.transactions)));
}

Object.assign(B, { projectCard, invoiceTable, txTable, feeNote, activity, rateButton, can, isOrg, isEng });
