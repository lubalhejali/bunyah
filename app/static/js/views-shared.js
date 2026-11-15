/* Dashboards, finance, disputes, messages, notifications. */
"use strict";

B.views.dashboard = async function () {
  if (S.me.role === "admin") { go("/admin"); return null; }
  const d = await api("/dashboard");
  if (d.role === "organization") {
    const st = d.stats;
    const verifyNote = d.organization.verification_status !== "verified" ? notice("warning", h("strong", {}, L("Verification needed. ", "التوثيق مطلوب. ")),
      L("Complete your organization profile and submit verification before publishing projects or requests. Current status: ", "أكمل ملف الجهة وأرسل طلب التوثيق قبل نشر المشاريع أو الطلبات. الحالة الحالية: "), badge(d.organization.verification_status), " ",
      h("a", { href: "#/organization?tab=verification" }, L("Go to verification", "الانتقال إلى التوثيق"))) : null;
    return h("div", {},
      pageHead(L(`Welcome, ${S.me.name}`, `مرحبًا، ${S.me.name}`), [d.organization.name, " · ", orgRole(d.org_role)].join(""),
        ...(can("work.manage") ? [linkBtn("/projects/new", L("New project", "مشروع جديد")), linkBtn("/services/new", L("New service request", "طلب خدمة جديد"), "btn secondary")] : [])),
      verifyNote,
      h("div", { class: "grid grid-4" },
        stat(L("Projects in evaluation", "مشاريع قيد التقييم"), st.projects_open), stat(L("Active projects", "مشاريع نشطة"), st.projects_active),
        stat(L("Active contracts", "عقود سارية"), st.requests_active), stat(L("New proposals", "عروض جديدة"), st.proposals_new),
        stat(L("Reviews waiting for you", "مراجعات بانتظارك"), st.reviews_waiting), stat(L("Unpaid invoices (demo)", "فواتير غير مدفوعة (تجريبي)"), st.invoices_unpaid),
        stat(L("Completed projects", "مشاريع مكتملة"), st.projects_completed)),
      h("div", { class: "grid grid-2", style: "margin-top:1rem;align-items:start" },
        card(L("Needs your attention", "يحتاج إلى انتباهك"), d.attention.length ? h("ul", { class: "list" }, d.attention.map(a => h("li", {},
          h("a", { href: a.model === "B" ? `#/services/${a.id}?tab=time` : `#/projects/${a.id}?tab=deliverables` }, a.title),
          h("div", { class: "row small", style: "margin-top:.2rem" }, badge(a.status), a.period_seq ? h("span", { class: "muted" }, L(`Period ${a.period_seq}`, `الفترة ${a.period_seq}`)) : null,
            a.review_due_date ? h("span", { class: "muted" }, L("Decide by ", "البت قبل "), fmtDate(a.review_due_date)) : null, a.escalated ? badge("cancelled", L("Escalated", "تم التصعيد")) : null))))
          : h("p", { class: "muted" }, L("Nothing waiting for review. ", "لا يوجد ما ينتظر المراجعة. "))),
        card(L("Recent projects", "أحدث المشاريع"), d.projects.length ? h("ul", { class: "list" }, d.projects.slice(0, 6).map(p => h("li", { class: "row between" }, h("a", { href: "#/projects/" + p.id }, p.title), badge(p.status))))
          : empty(L("No projects yet", "لا توجد مشاريع"), L("Publish a project to start receiving proposals.", "انشر مشروعًا لتبدأ باستقبال العروض."))),
        card(L("Short-term service requests", "طلبات الخدمات قصيرة المدة"), d.requests.length ? h("ul", { class: "list" }, d.requests.slice(0, 6).map(r => h("li", { class: "row between" }, h("a", { href: "#/services/" + r.id }, r.title), badge(r.status))))
          : empty(L("No requests yet", "لا توجد طلبات"), L("Request an engineer for a defined number of working days.", "اطلب مهندسًا لعدد محدد من أيام العمل.")))));
  }
  const st = d.stats;
  const verifyNote = d.verification_status !== "verified" ? notice("warning", h("strong", {}, L("Verification needed. ", "التوثيق مطلوب. ")),
    L("Complete your professional profile and submit verification to send proposals and applications. Status: ", "أكمل ملفك المهني وأرسل طلب التوثيق لتقديم العروض والطلبات. الحالة: "), badge(d.verification_status), " ",
    h("a", { href: "#/profile?tab=verification" }, L("Go to verification", "الانتقال إلى التوثيق"))) : null;
  return h("div", {},
    pageHead(L(`Welcome, ${S.me.name}`, `مرحبًا، ${S.me.name}`), L("Your engineering work on BUNYAH", "أعمالك الهندسية على بُنية"), linkBtn("/projects", L("Find projects", "ابحث عن مشاريع")), linkBtn("/services", L("Short-term services", "خدمات قصيرة المدة"), "btn secondary")),
    verifyNote,
    h("div", { class: "grid grid-4" }, stat(L("Open proposals", "عروض مفتوحة"), st.proposals_open), stat(L("Open applications", "طلبات مفتوحة"), st.applications_open),
      stat(L("Active projects", "مشاريع نشطة"), st.projects_active), stat(L("Active contracts", "عقود سارية"), st.contracts_active),
      stat(L("Payouts pending (demo)", "تحويلات معلقة (تجريبي)"), money(st.payouts_pending_cents)), stat(L("Payouts sent (demo)", "تحويلات منفذة (تجريبي)"), money(st.payouts_sent_cents))),
    h("div", { class: "grid grid-2", style: "margin-top:1rem;align-items:start" },
      card(L("My projects", "مشاريعي"), d.projects.length ? h("ul", { class: "list" }, d.projects.map(p => h("li", { class: "row between" }, h("a", { href: "#/projects/" + p.id }, p.title), badge(p.status)))) : h("p", { class: "muted" }, L("No accepted projects yet.", "لا توجد مشاريع مقبولة بعد."))),
      card(L("My contracts", "عقودي"), d.contracts.length ? h("ul", { class: "list" }, d.contracts.map(r => h("li", { class: "row between" }, h("a", { href: "#/services/" + r.id }, r.title), badge(r.status)))) : h("p", { class: "muted" }, L("No contracts yet.", "لا توجد عقود بعد."))),
      card(L("My proposals", "عروضي"), table([{ label: L("Project", "المشروع"), render: o => h("a", { href: `#/projects/${o.project_id}?tab=proposals` }, o.project_title) },
        { label: L("Price", "السعر"), num: true, render: o => money(o.price_cents) }, { label: L("Status", "الحالة"), render: o => badge(o.status) }], d.proposals, { empty: L("You haven't sent proposals yet.", "لم ترسل عروضًا بعد.") })),
      card(L("My applications", "طلباتي"), table([{ label: L("Request", "الطلب"), render: a => h("a", { href: `#/services/${a.request_id}?tab=applications` }, a.request_title) },
        { label: L("Daily rate", "السعر اليومي"), num: true, render: a => money(a.proposed_daily_rate_cents) }, { label: L("Status", "الحالة"), render: a => badge(a.status) }], d.applications, { empty: L("You haven't applied yet.", "لم تتقدم بعد.") }))));
};

/* ---------- finance ---------- */
B.views.finance = async function () {
  const f = await api("/finance");
  const t = f.totals;
  const eng = S.me.role === "engineer";
  return h("div", {},
    pageHead(L("Financial records", "السجلات المالية"), eng ? L("Payment records and payouts for your work", "سجلات المدفوعات والتحويلات لأعمالك") : L("Invoices and payments for your organization", "فواتير ومدفوعات جهتك"), demoTag()),
    notice("warning", h("strong", {}, L("Everything on this page is simulated. ", "كل ما في هذه الصفحة تجريبي. ")), L("No card details are collected, no real payment is processed and BUNYAH does not hold customer funds. The payment model, provider and tax treatment are pending legal and accounting review (Blueprint D1).",
      "لا تُجمع بيانات بطاقات ولا تتم معالجة أي دفع حقيقي ولا تحتفظ بُنية بأموال العملاء. نموذج الدفع والمزوّد والمعاملة الضريبية بانتظار المراجعة القانونية والمحاسبية (القرار D1).")),
    h("div", { class: "grid grid-4" },
      eng ? stat(L("Payouts pending", "تحويلات معلقة"), money(t.payouts_pending_cents)) : stat(L("Outstanding", "مستحق"), money(t.outstanding_cents)),
      eng ? stat(L("Payouts sent", "تحويلات منفذة"), money(t.payouts_sent_cents)) : stat(L("Paid", "مدفوع"), money(t.paid_cents)),
      stat(L("Invoiced (total)", "إجمالي الفواتير"), money(t.invoiced_cents)), stat(L("Refunded", "مسترد"), money(t.refunded_cents))),
    card(null, h("div", { class: "row between" }, h("h2", { style: "margin:0" }, L("Invoices", "الفواتير")), demoTag()), invoiceTable(f.invoices, { pay: !eng })),
    h("div", { style: "height:1rem" }),
    card(null, h("div", { class: "row between" }, h("h2", { style: "margin:0" }, eng ? L("Payment & payout records", "سجلات الدفعات والتحويلات") : L("Transaction history", "سجل العمليات")), demoTag()), txTable(f.transactions)));
};

/* ---------- disputes ---------- */
const REASONS = { quality: ["Quality of work", "جودة العمل"], delay: ["Delay", "التأخير"], scope: ["Scope disagreement", "خلاف على النطاق"], payment: ["Payment", "الدفع"],
  conduct: ["Professional conduct", "السلوك المهني"], time_records: ["Time records", "سجلات الوقت"], other: ["Other", "أخرى"] };
const OUTCOMES = { release_to_engineer: ["Release to engineer", "صرف للمهندس"], refund_to_organization: ["Refund to organization", "استرداد للجهة"], partial_settlement: ["Partial settlement", "تسوية جزئية"],
  resume_work: ["Resume work", "استئناف العمل"], no_financial_action: ["No financial action", "دون إجراء مالي"] };

B.views.disputes = async function () {
  const list = await api("/disputes");
  return h("div", {}, pageHead(L("Disputes", "النزاعات"), L("Target time for an administrative decision: 10 working days.", "المدة المستهدفة لقرار الإدارة: 10 أيام عمل.")),
    card(null, table([
      { label: "#", render: d => h("a", { href: "#/disputes/" + d.id }, "#" + d.id) },
      { label: L("Subject", "الموضوع"), render: d => [d.subject_title, h("div", { class: "muted small" }, d.subject_type === "project" ? L("Project (Model A)", "مشروع (النموذج أ)") : L("Contract (Model B)", "عقد (النموذج ب)"))] },
      { label: L("Reason", "السبب"), render: d => L(...REASONS[d.reason_code]) }, { label: L("Opened by", "فتحه"), render: d => d.raised_by.name },
      { label: L("Status", "الحالة"), render: d => [badge(d.status), d.overdue ? h("div", {}, badge("cancelled", L("Past target date", "تجاوز الموعد المستهدف"))) : null] },
      { label: L("Target date", "الموعد المستهدف"), render: d => fmtDate(d.target_resolution_date) }], list, { empty: L("No disputes.", "لا توجد نزاعات.") })));
};

B.views.disputeNew = async function (params, q) {
  const type = q.get("type"), id = q.get("id");
  const subject = type === "project" ? await api("/projects/" + id) : await api("/service-requests/" + id);
  const box = errorBox();
  return h("div", {}, pageHead(L("Raise a dispute", "فتح نزاع"), subject.title),
    notice("warning", L("Opening a dispute pauses approvals and simulated payments for this work until a BUNYAH administrator records a reasoned decision. Both parties can add statements and evidence. Either party may appeal the decision.",
      "فتح النزاع يوقف الاعتمادات والمدفوعات التجريبية لهذا العمل حتى تسجّل إدارة بُنية قرارًا مسببًا. يمكن للطرفين إضافة الإفادات والأدلة، ولكل منهما استئناف القرار.")),
    onSubmit(h("form", { class: "card", style: "max-width:720px" }, box,
      field(L("Reason", "السبب"), sel("reason_code", Object.entries(REASONS).map(([k, v]) => [k, L(...v)]), "quality"), { required: true }),
      field(L("Describe the issue", "صف المشكلة"), txt("description", { rows: 6, minlength: 20 }), { required: true, hint: L("Facts, dates and what outcome you are asking for. You can add evidence files on the next page.", "الوقائع والتواريخ والنتيجة التي تطلبها. يمكنك إرفاق الأدلة في الصفحة التالية.") }),
      h("input", { type: "hidden", name: "subject_type", value: type }), h("input", { type: "hidden", name: "subject_id", value: id, "data-type": "int" }),
      h("div", { class: "btn-row" }, h("button", { class: "btn danger", type: "submit" }, L("Open dispute", "فتح النزاع")), linkBtn(type === "project" ? "/projects/" + id : "/services/" + id, L("Cancel", "إلغاء"), "btn secondary"))),
    async (d) => { const r = await api("/disputes", { method: "POST", body: d }); toast(L("Dispute opened.", "تم فتح النزاع.")); go("/disputes/" + r.id); }));
};

B.views.dispute = async function ([id]) {
  const d = await api("/disputes/" + id);
  const admin = d.my_side === "admin";
  const party = ["organization", "engineer"].includes(d.my_side);
  const kinds = { statement: L("Statement", "إفادة"), response: L("Response", "رد"), admin_note: L("Administrator note", "ملاحظة الإدارة"), decision: L("Decision", "القرار"), appeal: L("Appeal", "استئناف") };
  const sides = { organization: L("Organization", "الجهة"), engineer: L("Engineer", "المهندس"), admin: L("BUNYAH administrator", "إدارة بُنية") };
  const box = errorBox();
  const entryForm = d.status !== "closed" ? onSubmit(h("form", { class: "card" }, h("h2", {}, admin ? L("Add an administrator note", "إضافة ملاحظة إدارية") : L("Add a statement or response", "إضافة إفادة أو رد")), box,
    field(L("Text", "النص"), txt("body", { rows: 4 }), { required: true }), h("button", { class: "btn", type: "submit" }, L("Add", "إضافة"))),
  async (x) => { await api(`/disputes/${d.id}/entries`, { method: "POST", body: x }); toast(L("Added.", "تمت الإضافة.")); B.render(); }) : null;
  const dbox = errorBox();
  const decisionForm = admin && ["open", "under_review", "appealed"].includes(d.status) ? onSubmit(h("form", { class: "card" },
    h("h2", {}, d.status === "appealed" ? L("Record the final decision (after appeal)", "تسجيل القرار النهائي (بعد الاستئناف)") : L("Record a reasoned decision", "تسجيل قرار مسبب")), dbox,
    notice("info", L("Recording a decision does not move any money. Simulated releases or refunds are recorded separately on the finance page, only after a decision.", "تسجيل القرار لا يحرك أي أموال. يُسجل الصرف أو الاسترداد التجريبي بشكل منفصل في صفحة المالية بعد القرار فقط.")),
    field(L("Outcome", "النتيجة"), sel("outcome", d.outcomes.map(o => [o, L(...OUTCOMES[o])]), "resume_work"), { required: true }),
    field(L("Status the work returns to when the dispute is closed", "الحالة التي يعود إليها العمل عند إغلاق النزاع"), sel("resume_status", d.resume_options.map(s => [s, statusLabel(s)]), d.resume_options[0]), { required: true }),
    field(L("Reasons for the decision", "أسباب القرار"), txt("reasoning", { rows: 6, minlength: 20 }), { required: true, hint: L("Shared with both parties. At least 20 characters.", "تُشارك مع الطرفين. 20 حرفًا على الأقل.") }),
    h("button", { class: "btn", type: "submit" }, L("Record decision", "تسجيل القرار"))),
  async (x) => { await api(`/admin/disputes/${d.id}/decision`, { method: "POST", body: x }); toast(L("Decision recorded.", "تم تسجيل القرار.")); B.render(); }) : null;
  const adminActs = admin ? h("div", { class: "btn-row" },
    d.status === "open" ? action(L("Start review", "بدء المراجعة"), () => api(`/admin/disputes/${d.id}/start-review`, { method: "POST" }), { cls: "btn secondary" }) : null,
    d.status === "decided" ? action(L("Close dispute", "إغلاق النزاع"), (note) => api(`/admin/disputes/${d.id}/close`, { method: "POST", body: { note } }), { prompt: { message: L("Close the dispute and apply the decided status? If the appeal window is still open, record why.", "إغلاق النزاع وتطبيق الحالة المقررة؟ إذا كانت مهلة الاستئناف مفتوحة فاذكر السبب."), input: "textarea", inputLabel: L("Closing note", "ملاحظة الإغلاق"), okLabel: L("Close dispute", "إغلاق النزاع") } }) : null) : null;
  const appealBtn = party && d.status === "decided" ? action(L("Appeal the decision", "استئناف القرار"), (reason) => api(`/disputes/${d.id}/appeal`, { method: "POST", body: { reason } }), { cls: "btn secondary", prompt: { message: L("Why should the decision be reviewed again?", "لماذا يجب إعادة النظر في القرار؟"), input: "textarea", inputLabel: L("Appeal reason", "سبب الاستئناف"), required: true, minLength: 20, okLabel: L("Submit appeal", "تقديم الاستئناف") } }) : null;
  return h("div", {},
    pageHead(L(`Dispute #${d.id}`, `النزاع #${d.id}`), d.subject_title, badge(d.status), d.overdue ? badge("cancelled", L("Past target date", "تجاوز الموعد المستهدف")) : null),
    h("div", { class: "layout-side" },
      h("div", { class: "stack" },
        card(L("Case history", "سجل القضية"), h("ol", { class: "timeline" }, d.entries.map(e => h("li", {}, fmtTime(e.created_at),
          h("strong", {}, kinds[e.kind], " · ", sides[e.author_side], " (", e.author.name, ")"), h("p", { class: "prewrap", style: "margin:.2rem 0 0" }, e.body))))),
        d.decision_text ? card(L("Decision", "القرار"), h("p", {}, badge("decided", L(...(OUTCOMES[d.decision_outcome] || ["", ""])))), h("p", { class: "prewrap" }, d.decision_text),
          d.appeal_deadline ? h("p", { class: "muted small" }, L("Appeal possible until ", "يمكن الاستئناف حتى "), fmtDate(d.appeal_deadline)) : null) : null,
        d.final_decision_text ? card(L("Final decision after appeal", "القرار النهائي بعد الاستئناف"), h("p", { class: "prewrap" }, d.final_decision_text)) : null,
        decisionForm, entryForm),
      h("div", { class: "stack" },
        card(L("Summary", "ملخص"), kv([[L("Subject", "الموضوع"), h("a", { href: d.subject_type === "project" ? `#/projects/${d.subject_id}` : `#/services/${d.subject_id}` }, d.subject_title)],
          [L("Reason", "السبب"), L(...REASONS[d.reason_code])], [L("Opened by", "فتحه"), sides[d.raised_by_side]], [L("Opened", "تاريخ الفتح"), fmtDate(d.created_at)],
          [L("Target decision date", "الموعد المستهدف للقرار"), fmtDate(d.target_resolution_date)], [L("You are", "صفتك"), sides[d.my_side]]]),
          adminActs, appealBtn ? h("div", { style: "margin-top:.75rem" }, appealBtn) : null),
        card(L("Evidence", "الأدلة"), d.evidence.length ? h("ul", {}, d.evidence.map(f => h("li", {}, fileLink(f), " ", h("span", { class: "muted small" }, sizeLabel(f.size))))) : h("p", { class: "muted small" }, L("No evidence files.", "لا توجد ملفات أدلة.")),
          d.status !== "closed" ? uploadForm(`/disputes/${d.id}/evidence`, { label: L("Evidence file", "ملف الدليل"), button: L("Attach evidence", "إرفاق دليل") }) : null))));
};

/* ---------- messages ---------- */
B.views.messages = async function ([convId]) {
  const convs = await api("/conversations");
  const listEl = h("nav", { class: "card chat-list", style: "padding:0", "aria-label": L("Conversations", "المحادثات") },
    convs.length ? convs.map(c => h("a", { href: "#/messages/" + c.id, "aria-current": String(c.id) === convId ? "page" : null },
      h("div", { class: "row between" }, h("strong", {}, c.other.name), c.unread ? h("span", { class: "pill", style: "background:var(--ink);color:var(--paper)" }, c.unread) : null),
      h("div", { class: "muted small" }, c.last_message || L("No messages yet", "لا توجد رسائل")))) : h("p", { class: "muted", style: "padding:1rem" }, L("No conversations yet. Start one from an engineer's profile, a proposal or an application.", "لا توجد محادثات. ابدأ واحدة من ملف مهندس أو عرض أو طلب تقديم.")));
  if (!convId) return h("div", {}, pageHead(L("Messages", "الرسائل")), h("div", { class: "chat" }, listEl, h("div", { class: "card" }, empty(L("Choose a conversation", "اختر محادثة"), ""))));
  const conv = convs.find(c => String(c.id) === convId);
  if (!conv) throw new ApiErr(404, "NOT_FOUND", L("Conversation not found.", "المحادثة غير موجودة."));
  const msgs = await api(`/conversations/${convId}/messages`);
  let last = msgs.length ? msgs[msgs.length - 1].id : 0;
  const box = h("div", { class: "chat-msgs", "aria-live": "polite" });
  const add = (m) => box.append(h("div", { class: "msg" + (m.mine ? " mine" : "") }, h("div", { class: "small", style: "font-weight:600" }, m.sender_name), h("div", { class: "prewrap" }, m.body), fmtTime(m.created_at)));
  msgs.forEach(add);
  const canSend = S.me.role === "engineer" || can("messages.send");
  const err = errorBox();
  const form = canSend ? onSubmit(h("form", { class: "row", style: "margin-top:.75rem;align-items:flex-end" }, err,
    h("div", { style: "flex:1" }, h("label", { for: "msg-body", class: "hidden" }, L("Message", "الرسالة")), txt("body", { id: "msg-body", rows: 2, placeholder: L("Write a message…", "اكتب رسالة…") })),
    h("button", { class: "btn", type: "submit" }, L("Send", "إرسال"))),
  async (d, fd) => { const m = await api(`/conversations/${convId}/messages`, { method: "POST", body: { body: d.body } }); add(m); last = m.id; form.reset(); box.scrollTop = box.scrollHeight; void fd; }) : notice("info", L("Your role can read but not send messages.", "يمكن لدورك القراءة دون الإرسال."));
  every(5000, async () => { try { const n = await api(`/conversations/${convId}/messages?after_id=${last}`); n.forEach(m => { if (m.id > last) { add(m); last = m.id; } }); if (n.length) box.scrollTop = box.scrollHeight; } catch { /* ignore */ } });
  setTimeout(() => { box.scrollTop = box.scrollHeight; }, 0);
  return h("div", {}, pageHead(L("Messages", "الرسائل")), h("div", { class: "chat" }, listEl, h("section", { class: "card" }, h("h2", {}, conv.other.name), box, form)));
};

/* ---------- notifications ---------- */
B.views.notifications = async function () {
  const list = await api("/notifications");
  return h("div", {}, pageHead(L("Notifications", "الإشعارات"), L("E-mail delivery is not set up in the prototype – notifications appear here only.", "إرسال البريد غير مفعّل في النموذج – تظهر الإشعارات هنا فقط."),
    list.some(n => !n.read) ? action(L("Mark all as read", "تحديد الكل كمقروء"), () => api("/notifications/read-all", { method: "POST" }), { cls: "btn secondary" }) : null),
    list.length ? h("ul", { class: "list card" }, list.map(n => h("li", { class: "row between" },
      h("div", {}, h("a", { href: "#" + (n.link || "/notifications"), style: n.read ? "" : "font-weight:600", onclick: () => { if (!n.read) api(`/notifications/${n.id}/read`, { method: "POST" }).catch(() => {}); } }, L(n.title_en, n.title_ar)),
        h("div", { class: "muted small" }, fmtTime(n.created_at))), n.read ? null : badge("open", L("New", "جديد")))))
      : empty(L("You're all caught up", "لا توجد إشعارات جديدة"), L("Notifications about proposals, reviews, contracts and payments will appear here.", "ستظهر هنا إشعارات العروض والمراجعات والعقود والمدفوعات.")));
};
