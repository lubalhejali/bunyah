"""Reference data (always) and FICTIONAL demo data (only when DEMO_MODE=true).

All demo people, organizations, projects and documents are invented. E-mails use the reserved ".test" domain,
so they can never reach a real inbox. Demo password for every demo account: see DEMO_PASSWORD below
(also listed in DEMO_ACCOUNTS.md). The login page offers one-click demo logins, so typing it is optional.

Run by hand:  python -m app.seed
"""
import hashlib
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BillingPeriod,
    Comment,
    Deliverable,
    DeliverableVersion,
    Discipline,
    Dispute,
    DisputeEntry,
    EngineerProfile,
    FeeRule,
    Holiday,
    Milestone,
    Offer,
    Organization,
    OrgMember,
    PortfolioItem,
    Project,
    ProjectEvent,
    ProposalClarification,
    Rating,
    ServiceApplication,
    ServiceContract,
    ServiceRequest,
    StoredFile,
    Task,
    TimeEntry,
    User,
    VerificationRequest,
)
from app.security import hash_password
from app.services import finance
from app.services.calendar import WorkCalendar, today as biz_today

DEMO_PASSWORD = "Bunyah-Demo-2026"  # fictional demo accounts only – never use for real accounts

DEMO_ACCOUNTS = {
    "admin": {"email": "admin@bunyah.test", "name": "Platform Administrator", "group": "admin",
              "label_en": "Administrator", "label_ar": "مدير المنصة"},
    "org_owner": {"email": "rawabi.owner@bunyah.test", "name": "Abdullah Al-Rashid", "group": "organization",
                  "label_en": "Organization – Owner", "label_ar": "جهة – المالك"},
    "org_pm": {"email": "rawabi.pm@bunyah.test", "name": "Hind Al-Otaibi", "group": "organization",
               "label_en": "Organization – Project Manager", "label_ar": "جهة – مدير المشاريع"},
    "org_reviewer": {"email": "rawabi.reviewer@bunyah.test", "name": "Khalid Al-Zahrani", "group": "organization",
                     "label_en": "Organization – Technical Reviewer", "label_ar": "جهة – المراجع الفني"},
    "org_finance": {"email": "rawabi.finance@bunyah.test", "name": "Mona Al-Shehri", "group": "organization",
                    "label_en": "Organization – Finance", "label_ar": "جهة – المالية"},
    "org_viewer": {"email": "rawabi.viewer@bunyah.test", "name": "Yousef Al-Dossary", "group": "organization",
                   "label_en": "Organization – Viewer", "label_ar": "جهة – مشاهد"},
    "org2_owner": {"email": "najd.owner@bunyah.test", "name": "Sultan Al-Anazi", "group": "organization",
                   "label_en": "Organization awaiting verification", "label_ar": "جهة بانتظار التوثيق"},
    "eng_structural": {"email": "faisal.eng@bunyah.test", "name": "Faisal Al-Harbi", "group": "engineer",
                       "label_en": "Engineer – Structural (verified)", "label_ar": "مهندس – إنشائي (موثق)"},
    "eng_mep": {"email": "reem.eng@bunyah.test", "name": "Reem Al-Ghamdi", "group": "engineer",
                "label_en": "Engineer – MEP (verified)", "label_ar": "مهندسة – كهروميكانيك (موثقة)"},
    "eng_bim": {"email": "majed.eng@bunyah.test", "name": "Majed Al-Mutairi", "group": "engineer",
                "label_en": "Engineer – BIM (verified)", "label_ar": "مهندس – نمذجة معلومات البناء (موثق)"},
    "eng_pending": {"email": "lama.eng@bunyah.test", "name": "Lama Al-Subaie", "group": "engineer",
                    "label_en": "Engineer awaiting verification", "label_ar": "مهندسة بانتظار التوثيق"},
}

DISCIPLINES = [
    ("architecture", "Architectural Engineering", "الهندسة المعمارية"),
    ("interior", "Interior Architecture", "العمارة الداخلية"),
    ("structural", "Structural Engineering", "الهندسة الإنشائية"),
    ("mep", "MEP Engineering", "الهندسة الكهروميكانيكية"),
    ("bim", "BIM", "نمذجة معلومات البناء"),
    ("technical_office", "Technical Office", "المكتب الفني"),
    ("project_coordination", "Project Coordination", "تنسيق المشاريع"),
    ("consulting", "Engineering Consulting", "الاستشارات الهندسية"),
    ("civil", "Civil Engineering", "الهندسة المدنية"),
    ("geotechnical", "Geotechnical Engineering", "الهندسة الجيوتقنية"),
]

# Islamic holiday dates follow moon sighting: these are ESTIMATES until an administrator confirms them.
HOLIDAYS = [
    (date(2026, 2, 22), "Founding Day", "يوم التأسيس", True),
    (date(2026, 9, 23), "Saudi National Day", "اليوم الوطني", True),
    (date(2027, 2, 22), "Founding Day", "يوم التأسيس", True),
    (date(2027, 3, 10), "Eid al-Fitr (estimate)", "عيد الفطر (تقديري)", False),
    (date(2027, 3, 11), "Eid al-Fitr (estimate)", "عيد الفطر (تقديري)", False),
    (date(2027, 3, 14), "Eid al-Fitr (estimate)", "عيد الفطر (تقديري)", False),
    (date(2027, 5, 16), "Eid al-Adha (estimate)", "عيد الأضحى (تقديري)", False),
    (date(2027, 5, 17), "Eid al-Adha (estimate)", "عيد الأضحى (تقديري)", False),
    (date(2027, 5, 18), "Eid al-Adha (estimate)", "عيد الأضحى (تقديري)", False),
    (date(2027, 9, 23), "Saudi National Day", "اليوم الوطني", True),
]

DEMO_PDF = b"%PDF-1.4\n% BUNYAH fictional demo document. Not a real drawing.\n%%EOF\n"


def ensure_reference_data(db: Session) -> None:
    for i, (code, en, ar) in enumerate(DISCIPLINES):
        if not db.scalar(select(Discipline.id).where(Discipline.code == code)):
            db.add(Discipline(code=code, name_en=en, name_ar=ar, sort_order=(i + 1) * 10))
    if not db.scalar(select(Holiday.id).limit(1)):
        for d, en, ar, ok in HOLIDAYS:
            db.add(Holiday(day=d, name_en=en, name_ar=ar, is_confirmed=ok))
    db.commit()


# ---------------------------------------------------------------------------------------------- helpers
def _now() -> datetime:
    return datetime.now(UTC)


def _user(db: Session, key: str, role: str, **extra) -> User:
    acc = DEMO_ACCOUNTS[key]
    u = User(email=acc["email"], name=acc["name"], role=role, password_hash=hash_password(DEMO_PASSWORD),
             locale="ar", phone="+966 5X XXX XXXX (demo)", **extra)
    db.add(u)
    db.flush()
    return u


def _file(db: Session, owner: User, name: str, ctx: str, ctx_id: int | None, project_id: int | None = None,
          kind: str = "deliverable") -> StoredFile:
    data = DEMO_PDF + name.encode()
    f = StoredFile(owner_id=owner.id, project_id=project_id, context_type=ctx, context_id=ctx_id, kind=kind,
                   filename=name, content_type="application/octet-stream", size=len(data),
                   sha256=hashlib.sha256(data).hexdigest(), storage_backend="database", data=data)
    db.add(f)
    db.flush()
    return f


def _ev(db: Session, actor: User | None, en: str, ar: str, project: Project | None = None,
        request: ServiceRequest | None = None, when: datetime | None = None) -> None:
    db.add(ProjectEvent(project_id=project.id if project else None, request_id=request.id if request else None,
                        actor_id=actor.id if actor else None, text=en, text_ar=ar, created_at=when or _now()))


def _disc(db: Session, code: str) -> int:
    return db.scalar(select(Discipline.id).where(Discipline.code == code))


# ---------------------------------------------------------------------------------------------- demo data
def seed_demo(db: Session) -> bool:
    """Creates the demo world once. Returns False if it already exists."""
    if db.scalar(select(User.id).where(User.email == DEMO_ACCOUNTS["admin"]["email"])):
        return False
    ensure_reference_data(db)
    cal = WorkCalendar.load(db)
    today = biz_today()

    # --- fee rules (DEMO placeholders: the real fee model is Blueprint decision D3) ---
    if not db.scalar(select(FeeRule.id).limit(1)):
        db.add(FeeRule(model="A", payer="both", fee_type="percent", org_value=250, engineer_value=500,
                       note="DEMO placeholder – not an approved commercial decision (D3)"))
        db.add(FeeRule(model="B", payer="organization", fee_type="percent", org_value=800, engineer_value=0,
                       note="DEMO placeholder – not an approved commercial decision (D3)"))

    # --- accounts ---
    admin = _user(db, "admin", "admin")
    rawabi = Organization(name="Al-Rawabi Engineering Consultants (Demo)", name_ar="الروابي للاستشارات الهندسية (تجريبي)",
                          org_type="engineering_consultancy", cr_number="1010000000 (demo)",
                          license_info="Engineering consultancy licence – demo value", city="Riyadh",
                          address="King Fahd Road, Riyadh (fictional)", contact_email="contact@rawabi.bunyah.test",
                          contact_phone="+966 11 XXX XXXX (demo)", representative_name="Abdullah Al-Rashid",
                          representative_title="Managing Director",
                          description="Fictional multidisciplinary consultancy used to demonstrate BUNYAH.",
                          verification_status="verified", is_demo=True)
    najd = Organization(name="Najd Development Company (Demo)", name_ar="شركة نجد للتطوير (تجريبي)",
                        org_type="developer", cr_number="1010999999 (demo)", city="Riyadh",
                        representative_name="Sultan Al-Anazi", representative_title="Projects Director",
                        description="Fictional developer waiting for verification.", verification_status="pending",
                        is_demo=True)
    db.add_all([rawabi, najd])
    db.flush()
    members = {}
    for key, role in [("org_owner", "owner"), ("org_pm", "project_manager"), ("org_reviewer", "technical_reviewer"),
                      ("org_finance", "finance"), ("org_viewer", "viewer")]:
        u = _user(db, key, "organization")
        db.add(OrgMember(org_id=rawabi.id, user_id=u.id, org_role=role))
        members[role] = u
    owner, pm, reviewer = members["owner"], members["project_manager"], members["technical_reviewer"]
    najd_owner = _user(db, "org2_owner", "organization")
    db.add(OrgMember(org_id=najd.id, user_id=najd_owner.id, org_role="owner"))

    def engineer(key, title, disc, years, spec, sw, city, rmin, rmax, status="verified"):
        u = _user(db, key, "engineer")
        db.add(EngineerProfile(user_id=u.id, title=title, discipline_id=_disc(db, disc), years_experience=years,
                               specializations=spec, software_skills=sw, languages="Arabic, English", city=city,
                               education="B.Sc. Engineering (fictional university)",
                               qualifications="Professional engineer (demo data)",
                               certifications="PMP (demo)" if years > 8 else "",
                               registration_body="Saudi engineering professional body (demo)",
                               registration_number="DEMO-" + key.upper(), availability="available",
                               work_preference="hybrid", rate_min_cents=rmin, rate_max_cents=rmax,
                               bio=f"Fictional {title.lower()} profile created for the BUNYAH prototype.",
                               verification_status=status, is_demo=True))
        db.flush()
        return u

    faisal = engineer("eng_structural", "Senior Structural Engineer", "structural", 12,
                      "Reinforced concrete, steel structures, seismic design", "ETABS, SAFE, Revit, AutoCAD",
                      "Riyadh", 150000, 220000)
    reem = engineer("eng_mep", "MEP Design Engineer", "mep", 8, "HVAC, plumbing, fire fighting",
                    "Revit MEP, AutoCAD, HAP", "Jeddah", 120000, 180000)
    majed = engineer("eng_bim", "BIM Coordinator", "bim", 6, "Clash detection, 4D planning, model audits",
                     "Revit, Navisworks, Dynamo", "Riyadh", 100000, 150000)
    lama = engineer("eng_pending", "Architect", "architecture", 4, "Residential and interior design",
                    "Revit, SketchUp, Enscape", "Dammam", 80000, 120000, status="pending")
    db.add(PortfolioItem(user_id=faisal.id, title="Commercial tower structural design (fictional)",
                         description="Demo portfolio item: 22-storey RC frame, ETABS model and drawings."))
    db.add(PortfolioItem(user_id=majed.id, title="Hospital BIM coordination (fictional)",
                         description="Demo portfolio item: federated model, weekly clash reports."))

    # verification requests waiting for the administrator
    for subj_type, subj_id, by, note in [("organization", najd.id, najd_owner, "CR and licence attached (demo)."),
                                         ("engineer", lama.id, lama, "Degree and registration attached (demo).")]:
        vr = VerificationRequest(subject_type=subj_type, subject_id=subj_id, submitted_by=by.id, applicant_note=note)
        db.add(vr)
        db.flush()
        _file(db, by, f"verification-document-{subj_type}-demo.pdf", "verification", vr.id, kind="verification")

    def project(title, disc, status, **kw):
        p = Project(org_id=rawabi.id, office_id=pm.id, title=title, discipline_id=_disc(db, disc), status=status,
                    is_demo=True, published_at=_now() if status != "draft" else None, **kw)
        db.add(p)
        db.flush()
        _ev(db, pm, "Project created as a draft.", "تم إنشاء المشروع كمسودة.", p)
        if status != "draft":
            _ev(db, pm, "Project published.", "تم نشر المشروع.", p)
        return p

    base = dict(work_mode="hybrid", location="Riyadh", duration_days=60)

    # P1: published, proposals waiting for evaluation (Scenario A)
    p1 = project("Structural design – 4-storey office building, Riyadh", "structural", "published",
                 description="Full structural design for a 4-storey office building with one basement (fictional).",
                 scope="Concept to IFC structural design, calculations, drawings and BOQ input.",
                 deliverables_text="Design basis report; ETABS model; structural drawings (DWG); calculation report.",
                 requirements="Saudi Building Code (SBC 301/304), ETABS, coordinated with architecture.",
                 qualifications="8+ years in RC buildings; professional registration.",
                 budget_min_cents=4_000_000, max_budget_cents=6_500_000,
                 proposal_deadline=today + timedelta(days=10), deadline=today + timedelta(days=90), **base)
    for eng, price, approach in [(faisal, 5_800_000, "Phased approach: design basis, preliminary model, "
                                                     "coordination workshops, final IFC package."),
                                 (majed, 4_900_000, "Model-based workflow with Revit and ETABS links and "
                                                    "weekly coordination.")]:
        db.add(Offer(project_id=p1.id, freelancer_id=eng.id, price_cents=price, delivery_date=today + timedelta(days=75),
                     duration_days=60, message=f"{eng.name}: proposal for the structural design (demo text).",
                     technical_approach=approach, status="submitted"))

    # P2: published, no proposal from Faisal yet (Scenario B)
    project("MEP peer review – residential compound, Jeddah", "mep", "published",
            description="Independent peer review of MEP design drawings for a 40-villa compound (fictional).",
            scope="Review HVAC, plumbing and fire-fighting drawings; issue comment sheets.",
            deliverables_text="Review comment sheets (XLSX); summary report (PDF).",
            requirements="SBC 501/701, NFPA references.", qualifications="MEP design experience 5+ years.",
            budget_min_cents=1_500_000, max_budget_cents=3_000_000,
            proposal_deadline=today + timedelta(days=14), deadline=today + timedelta(days=60),
            work_mode="remote", location="", duration_days=30)
    p3 = project("Structural assessment of an existing warehouse, Dammam", "structural", "published",
                 description="Condition assessment and strengthening recommendations for a steel warehouse.",
                 scope="Site visit, assessment report, strengthening concept drawings.",
                 deliverables_text="Assessment report (PDF); concept drawings (DWG).",
                 requirements="Steel design, site inspection.", qualifications="Structural engineer.",
                 budget_min_cents=1_000_000, max_budget_cents=2_500_000,
                 proposal_deadline=today + timedelta(days=12), deadline=today + timedelta(days=50),
                 work_mode="onsite", location="Dammam", duration_days=25)
    _ = p3

    # P4: in progress, milestones + versioned deliverables (Scenario A/B workspace)
    p4 = project("Structural design – school extension, Riyadh", "structural", "in_progress",
                 description="Structural design of a 2-storey classroom extension (fictional).",
                 scope="Design and drawings for the new wing; connection to the existing building.",
                 deliverables_text="Design basis; calculation report; drawings.", requirements="SBC 301/304.",
                 qualifications="School projects experience.", budget_min_cents=2_000_000, max_budget_cents=4_000_000,
                 proposal_deadline=today - timedelta(days=20), deadline=today + timedelta(days=45), **base)
    o4 = Offer(project_id=p4.id, freelancer_id=faisal.id, price_cents=3_600_000, delivery_date=today + timedelta(days=40),
               duration_days=45, message="Proposal for the school extension (demo).",
               technical_approach="Three stages aligned with the architectural programme.", status="accepted")
    db.add(o4)
    db.flush()
    p4.freelancer_id, p4.accepted_offer_id = faisal.id, o4.id
    p4.agreement_engineer_at = p4.agreement_org_at = _now() - timedelta(days=15)
    m1 = Milestone(project_id=p4.id, seq=1, title="Design basis & preliminary model", amount_cents=900_000,
                   due_date=today - timedelta(days=5), status="approved", approved_at=_now() - timedelta(days=4))
    m2 = Milestone(project_id=p4.id, seq=2, title="Calculation report", amount_cents=1_200_000,
                   due_date=today + timedelta(days=15), status="in_progress")
    m3 = Milestone(project_id=p4.id, seq=3, title="IFC drawings", amount_cents=1_000_000,
                   due_date=today + timedelta(days=35), status="planned")
    db.add_all([m1, m2, m3])
    db.flush()
    d1 = Deliverable(project_id=p4.id, milestone_id=m1.id, title="Design basis report", status="approved",
                     created_by=pm.id)
    d2 = Deliverable(project_id=p4.id, milestone_id=m2.id, title="Structural calculation report",
                     status="under_review", created_by=pm.id)
    d3 = Deliverable(project_id=p4.id, milestone_id=m3.id, title="Structural drawings (DWG)", status="awaiting_upload",
                     created_by=pm.id)
    db.add_all([d1, d2, d3])
    db.flush()
    f = _file(db, faisal, "design-basis-v1.pdf", "deliverable", d1.id, p4.id)
    db.add(DeliverableVersion(deliverable_id=d1.id, version_no=1, file_id=f.id, uploaded_by=faisal.id,
                              note="First issue.", review_status="approved", review_comment="Approved.",
                              reviewed_by=reviewer.id, reviewed_at=_now() - timedelta(days=4)))
    f = _file(db, faisal, "calculation-report-v1.pdf", "deliverable", d2.id, p4.id)
    db.add(DeliverableVersion(deliverable_id=d2.id, version_no=1, file_id=f.id, uploaded_by=faisal.id,
                              note="First issue.", review_status="revision_requested",
                              review_comment="Add the lateral load combinations and the foundation check.",
                              reviewed_by=reviewer.id, reviewed_at=_now() - timedelta(days=2)))
    f = _file(db, faisal, "calculation-report-v2.pdf", "deliverable", d2.id, p4.id)
    db.add(DeliverableVersion(deliverable_id=d2.id, version_no=2, file_id=f.id, uploaded_by=faisal.id,
                              note="Updated with lateral combinations and foundation check.",
                              review_status="under_review"))
    db.add_all([Task(project_id=p4.id, milestone_id=m2.id, title="Coordinate column grid with architect",
                     status="done", assignee_id=faisal.id, created_by=pm.id),
                Task(project_id=p4.id, milestone_id=m3.id, title="Prepare drawing list", status="in_progress",
                     assignee_id=faisal.id, created_by=faisal.id),
                Task(project_id=p4.id, title="Review calculation report V2", status="todo", assignee_id=reviewer.id,
                     created_by=pm.id)])
    db.add(Comment(project_id=p4.id, author_id=reviewer.id, kind="technical_review",
                   body="[Structural calculation report V1] Add the lateral load combinations and the foundation check."))
    for en, ar in [("Proposal from Faisal Al-Harbi accepted.", "تم قبول عرض فيصل الحربي."),
                   ("Agreement confirmed by the organization. Work started.", "أكدت الجهة الاتفاقية. بدأ العمل."),
                   ("Milestone approved: Design basis & preliminary model", "تم اعتماد المرحلة: أساس التصميم والنموذج الأولي"),
                   ("Structural calculation report: version V2 uploaded.", "تقرير الحسابات الإنشائية: تم رفع النسخة V2.")]:
        _ev(db, pm, en, ar, p4)
    db.flush()
    inv = finance.issue_invoice(db, model="A", org_id=rawabi.id, engineer_id=faisal.id, amount_cents=m1.amount_cents,
                                description=f"{p4.title} – milestone 1: {m1.title}", project_id=p4.id,
                                milestone_id=m1.id)
    finance.record_payment(db, members["finance"], inv)

    # P5: submitted for review 7 working days ago -> the startup check escalates it (no auto-approval)
    p5 = project("MEP design – clinic fit-out, Jeddah", "mep", "submitted",
                 description="MEP design for a 600 m² outpatient clinic fit-out (fictional).",
                 scope="HVAC, plumbing, fire fighting and electrical design.",
                 deliverables_text="MEP drawings; design report.", requirements="SBC 501/601/701.",
                 qualifications="Healthcare MEP experience.", budget_min_cents=1_500_000, max_budget_cents=2_500_000,
                 proposal_deadline=today - timedelta(days=40), deadline=today + timedelta(days=10),
                 work_mode="remote", location="", duration_days=40)
    o5 = Offer(project_id=p5.id, freelancer_id=reem.id, price_cents=2_200_000, delivery_date=today + timedelta(days=5),
               message="Proposal for the clinic MEP design (demo).", technical_approach="Standard healthcare workflow.",
               status="accepted")
    db.add(o5)
    db.flush()
    p5.freelancer_id, p5.accepted_offer_id = reem.id, o5.id
    p5.agreement_engineer_at = p5.agreement_org_at = _now() - timedelta(days=30)
    submitted_on = today
    for _i in range(7):
        submitted_on -= timedelta(days=1)
        while not cal.is_working_day(submitted_on):
            submitted_on -= timedelta(days=1)
    p5.submitted_at = datetime.combine(submitted_on, datetime.min.time(), UTC)
    p5.review_due_date = cal.add_working_days(submitted_on, 5)
    p5.review_reminders_sent = 2
    d5 = Deliverable(project_id=p5.id, title="MEP drawing set", status="under_review", created_by=pm.id)
    db.add(d5)
    db.flush()
    f = _file(db, reem, "mep-drawings-v1.zip.pdf", "deliverable", d5.id, p5.id)
    db.add(DeliverableVersion(deliverable_id=d5.id, version_no=1, file_id=f.id, uploaded_by=reem.id,
                              note="Complete set for review.", review_status="under_review",
                              created_at=p5.submitted_at))
    _ev(db, reem, "Work submitted for review.", "تم تقديم العمل للمراجعة.", p5, when=p5.submitted_at)

    # P6: completed with ratings (history)
    p6 = project("Villa structural drawings, Riyadh", "structural", "completed",
                 description="Structural drawings for a private villa (fictional).", scope="Design and drawings.",
                 deliverables_text="Drawings.", budget_min_cents=500_000, max_budget_cents=1_000_000,
                 proposal_deadline=today - timedelta(days=90), deadline=today - timedelta(days=30), **base)
    o6 = Offer(project_id=p6.id, freelancer_id=faisal.id, price_cents=800_000, delivery_date=today - timedelta(days=35),
               message="Villa proposal (demo).", technical_approach="Standard workflow.", status="accepted")
    db.add(o6)
    db.flush()
    p6.freelancer_id, p6.accepted_offer_id = faisal.id, o6.id
    p6.completed_at = p6.approved_at = _now() - timedelta(days=30)
    d6 = Deliverable(project_id=p6.id, title="Villa structural drawings", status="approved", created_by=pm.id)
    db.add(d6)
    db.flush()
    f = _file(db, faisal, "villa-structural-v1.pdf", "deliverable", d6.id, p6.id)
    db.add(DeliverableVersion(deliverable_id=d6.id, version_no=1, file_id=f.id, uploaded_by=faisal.id,
                              review_status="approved", reviewed_by=reviewer.id, reviewed_at=_now() - timedelta(days=31)))
    inv = finance.issue_invoice(db, model="A", org_id=rawabi.id, engineer_id=faisal.id, amount_cents=800_000,
                                description=f"{p6.title} – final payment", project_id=p6.id)
    _, payout = finance.record_payment(db, members["finance"], inv)
    finance.mark_payout_sent(db, admin, payout)
    db.add(Rating(subject_key=f"project:{p6.id}:organization", subject_type="project", project_id=p6.id,
                  reviewer_id=owner.id, reviewer_side="organization", org_id=rawabi.id, engineer_id=faisal.id,
                  rating=5, text="Clear drawings and on-time delivery (demo review)."))
    db.add(Rating(subject_key=f"project:{p6.id}:engineer", subject_type="project", project_id=p6.id,
                  reviewer_id=faisal.id, reviewer_side="engineer", org_id=rawabi.id, engineer_id=faisal.id,
                  rating=5, text="Well-organized client, quick feedback (demo review)."))

    # P7: draft
    project("Interior design – head office reception (draft)", "interior", "draft",
            description="Interior design concept and drawings for a 300 m² reception area (fictional).",
            scope="Concept, materials board, detailed drawings.", deliverables_text="Concept PDF; drawings.",
            budget_min_cents=800_000, max_budget_cents=1_500_000, proposal_deadline=today + timedelta(days=20),
            deadline=today + timedelta(days=60), work_mode="hybrid", location="Riyadh", duration_days=30)

    # P8: disputed project
    p8 = project("Fire-fighting system design – warehouse, Riyadh", "mep", "disputed",
                 description="Fire-fighting design for a logistics warehouse (fictional).", scope="Design and drawings.",
                 deliverables_text="Drawings; hydraulic calculations.", budget_min_cents=1_000_000,
                 max_budget_cents=2_000_000, proposal_deadline=today - timedelta(days=50),
                 deadline=today + timedelta(days=5), **base)
    o8 = Offer(project_id=p8.id, freelancer_id=reem.id, price_cents=1_700_000, delivery_date=today,
               message="Fire-fighting proposal (demo).", technical_approach="NFPA 13 based design.", status="accepted")
    db.add(o8)
    db.flush()
    p8.freelancer_id, p8.accepted_offer_id, p8.status_before_dispute = reem.id, o8.id, "revision_requested"
    p8.agreement_engineer_at = p8.agreement_org_at = _now() - timedelta(days=40)
    dsp = Dispute(subject_type="project", project_id=p8.id, raised_by=reem.id, raised_by_side="engineer",
                  reason_code="scope", description="The organization asks for a sprinkler redesign of an area that "
                  "was outside the agreed scope (demo dispute).", target_resolution_date=cal.add_working_days(today, 8))
    db.add(dsp)
    db.flush()
    db.add(DisputeEntry(dispute_id=dsp.id, author_id=reem.id, author_side="engineer", kind="statement",
                        body=dsp.description))
    db.add(DisputeEntry(dispute_id=dsp.id, author_id=pm.id, author_side="organization", kind="response",
                        body="The mezzanine area was listed in the brief appendix; we consider it in scope (demo)."))
    dsp.status = "under_review"
    _file(db, reem, "scope-appendix-evidence-demo.pdf", "dispute", dsp.id, kind="evidence")
    _ev(db, reem, "Dispute opened. Work, approvals and payments are paused.",
        "تم فتح نزاع. توقف العمل والاعتمادات والمدفوعات مؤقتًا.", p8)

    # ------------------------------------------------------------------ Model B
    def request(title, disc, status, days, rate, **kw):
        r = ServiceRequest(org_id=rawabi.id, created_by=pm.id, title=title, discipline_id=_disc(db, disc),
                           status=status, duration_working_days=days, daily_rate_cents=rate, is_demo=True,
                           published_at=_now() if status not in ("draft", "submitted") else None, **kw)
        db.add(r)
        db.flush()
        _ev(db, pm, "Service request created as a draft.", "تم إنشاء طلب الخدمة كمسودة.", request=r)
        return r

    common = dict(hours_per_day=8, work_mode="onsite", location="Riyadh", min_experience_years=5,
                  qualifications="Bachelor's degree in engineering; professional registration.",
                  responsibilities="Support the project team with day-to-day engineering tasks (fictional).",
                  outputs="Daily work log; weekly summary; reviewed documents.")
    r1 = request("BIM Specialist – hospital project (60 working days)", "bim", "applications_open", 60, 130_000,
                 specialization="Revit / Navisworks coordination", start_date=today + timedelta(days=14), **common)
    for eng, rate, letter in [(majed, 125_000, "Six years of BIM coordination on healthcare projects (demo)."),
                              (reem, 135_000, "MEP background with strong Revit coordination skills (demo).")]:
        db.add(ServiceApplication(request_id=r1.id, engineer_id=eng.id, cover_letter=letter,
                                  proposed_daily_rate_cents=rate, available_from=today + timedelta(days=14)))
    _ev(db, admin, "Approved and published by BUNYAH.", "تمت الموافقة والنشر من بُنية.", request=r1)
    _ev(db, pm, "Applications opened.", "تم فتح التقديم.", request=r1)

    # R2: active contract, started 25 working days ago (period 1 submitted, period 2 in progress)
    start = today
    for _i in range(25):
        start -= timedelta(days=1)
        while not cal.is_working_day(start):
            start -= timedelta(days=1)
    r2 = request("Site Structural Engineer – tower podium (90 working days)", "structural", "active", 90, 160_000,
                 specialization="Site supervision support and shop-drawing review", start_date=start, **common)
    ap2 = ServiceApplication(request_id=r2.id, engineer_id=faisal.id, cover_letter="Available for site support (demo).",
                             proposed_daily_rate_cents=160_000, available_from=start, status="selected")
    db.add(ap2)
    db.flush()
    r2.selected_application_id = ap2.id
    c2 = ServiceContract(request_id=r2.id, org_id=rawabi.id, engineer_id=faisal.id, application_id=ap2.id,
                         start_date=start, working_days=90, end_date=cal.nth_working_day(start, 90),
                         daily_rate_cents=160_000, hours_per_day=8, period_length_days=20,
                         terms="PROTOTYPE CONTRACT TEMPLATE – NOT LEGALLY REVIEWED (demo).",
                         org_signed_by=owner.id, org_signature_name=owner.name,
                         org_signed_at=_now() - timedelta(days=40), engineer_signature_name=faisal.name,
                         engineer_signed_at=_now() - timedelta(days=39))
    db.add(c2)
    db.flush()
    periods = []
    for i, (s_, e_, n) in enumerate(cal.split_periods(start, 90, 20), start=1):
        bp = BillingPeriod(contract_id=c2.id, seq=i, start_date=s_, end_date=e_, working_days=n)
        db.add(bp)
        periods.append(bp)
    db.flush()
    d, worked = start, 0
    while d < today and worked < 24:
        if cal.is_working_day(d):
            bp = next(p for p in periods if p.start_date <= d <= p.end_date)
            db.add(TimeEntry(contract_id=c2.id, period_id=bp.id, work_date=d, day_fraction=1.0 if worked % 9 else 0.5,
                             hours=8 if worked % 9 else 4,
                             description="Site inspection and shop-drawing review (demo entry)."))
            worked += 1
        d += timedelta(days=1)
    periods[0].status, periods[0].submitted_at = "submitted", _now() - timedelta(days=2)
    periods[0].review_due_date = cal.add_working_days(today - timedelta(days=2), 5)
    for en, ar in [("Contract signed by the organization.", "وقّعت الجهة العقد."),
                   ("Both parties signed. Contract is active.", "وقّع الطرفان. العقد ساري."),
                   ("Billing period 1 submitted for approval.", "تم تقديم فترة الفوترة 1 للاعتماد.")]:
        _ev(db, owner, en, ar, request=r2)

    # R3: waiting for administrator review; R4: draft
    request("MEP Engineer – technical office support (40 working days)", "mep", "submitted", 40, 120_000,
            specialization="Submittal and RFI review", start_date=today + timedelta(days=21), **common)
    request("Project Coordinator – fit-out programme (draft)", "project_coordination", "draft", 30, 100_000,
            specialization="Programme tracking", start_date=today + timedelta(days=30), **common)

    db.add(ProposalClarification(offer_id=db.scalar(select(Offer.id).where(Offer.project_id == p1.id,
                                                                           Offer.freelancer_id == majed.id)),
                                 author_id=pm.id, body="Can you confirm the number of coordination workshops? (demo)"))
    db.commit()
    return True


if __name__ == "__main__":
    from app.database import SessionLocal, init_db
    init_db()
    s = SessionLocal()
    ensure_reference_data(s)
    print("Demo data created." if seed_demo(s) else "Demo data already exists – nothing changed.")
