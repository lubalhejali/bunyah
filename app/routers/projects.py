"""Model A endpoints: projects, proposals, agreement, milestones, tasks, deliverables (versioned), files,
comments, activity and the simulated financial summary."""
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import schemas as s
from app.database import get_db
from app.errors import bad_request, conflict, forbidden, not_found
from app.models import (
    Comment,
    Deliverable,
    DeliverableVersion,
    Milestone,
    Offer,
    OfferStatus,
    Project,
    ProjectEvent,
    ProjectStatus as P,
    Role,
    StoredFile,
    Task,
    User,
)
from app.security import OrgContext, current_user, require_engineer, require_org
from app.services import finance
from app.services import files as filesvc
from app.services import model_a as A
from app.services.model_a import user_mini

router = APIRouter(tags=["Model A – projects"])


def _out(db: Session, a: A.Access) -> dict:
    return A.project_out(db, a.p, a)


# ---------- projects ----------
@router.get("/projects")
def list_projects(scope: Literal["marketplace", "mine"] = "marketplace", q: str = "", discipline_id: int | None = None,
                  work_mode: Literal["remote", "onsite", "hybrid", ""] = "", status: str = "",
                  budget_max: int | None = None, page: int = 1, per_page: int = 20,
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    """scope=marketplace: published projects. scope=mine: my organization's projects, or the projects I work on
    or sent proposals to (engineers)."""
    per_page, page = max(1, min(per_page, 50)), max(page, 1)
    stmt = select(Project)
    if scope == "marketplace":
        stmt = stmt.where(Project.status == P.PUBLISHED)
    elif user.role == Role.ORGANIZATION:
        from app.security import org_context
        ctx = org_context(db, user)
        stmt = stmt.where(Project.org_id == (ctx.org.id if ctx else -1))
    else:
        proposed = select(Offer.project_id).where(Offer.freelancer_id == user.id)
        stmt = stmt.where(or_(Project.freelancer_id == user.id, Project.id.in_(proposed)))
    if status and scope == "mine":
        stmt = stmt.where(Project.status == status)
    if q:
        like = f"%{q.strip()[:80]}%"
        stmt = stmt.where(or_(Project.title.ilike(like), Project.description.ilike(like),
                              Project.location.ilike(like), Project.scope.ilike(like)))
    if discipline_id:
        stmt = stmt.where(Project.discipline_id == discipline_id)
    if work_mode:
        stmt = stmt.where(Project.work_mode == work_mode)
    if budget_max:
        stmt = stmt.where(Project.max_budget_cents <= budget_max)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Project.created_at.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    data = []
    for p in rows:
        a = A.Access(db, p, user)
        data.append(A.project_out(db, p, brief=True) | {"my_role": a.role,
                                                         "my_proposal_status": a.offer.status if a.offer else None})
    return {"data": data, "total": total, "page": page, "per_page": per_page}


@router.post("/projects", status_code=201)
def create_project(body: s.ProjectIn, db: Session = Depends(get_db), ctx: OrgContext = Depends(require_org)):
    p = A.create_project(db, ctx, body.model_dump())
    db.commit()
    return A.project_out(db, p, A.Access(db, p, ctx.user))


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _out(db, A.get_access(db, project_id, user))


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: s.ProjectUpdate, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    A.update_project(db, a, body.model_dump(exclude_unset=True))
    db.commit()
    return _out(db, a)


@router.post("/projects/{project_id}/publish")
def publish(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    A.publish(db, a)
    db.commit()
    return _out(db, a)


@router.post("/projects/{project_id}/transitions")
def transition(project_id: int, body: s.ProjectStep, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    A.simple_move(db, a, body.to)
    db.commit()
    return _out(db, a)


@router.get("/projects/{project_id}/events")
def events(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    if not a.participant:
        raise forbidden()
    rows = db.scalars(select(ProjectEvent).where(ProjectEvent.project_id == project_id).order_by(ProjectEvent.id)).all()
    return [{"id": e.id, "text": e.text, "text_ar": e.text_ar, "created_at": e.created_at} for e in rows]


# ---------- proposals ----------
@router.get("/projects/{project_id}/proposals")
def project_proposals(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    if a.org or a.admin:
        rows = db.scalars(select(Offer).where(Offer.project_id == project_id, Offer.status != OfferStatus.WITHDRAWN)
                          .order_by(Offer.price_cents)).all()
    elif a.offer or a.hired:
        rows = db.scalars(select(Offer).where(Offer.project_id == project_id, Offer.freelancer_id == user.id)).all()
    else:
        return []
    return [A.proposal_out(db, o) for o in rows]


@router.post("/projects/{project_id}/proposals", status_code=201)
def submit_proposal(project_id: int, body: s.ProposalIn, db: Session = Depends(get_db),
                    eng: User = Depends(require_engineer)):
    """Creates the proposal, or updates it while it is still open."""
    a = A.get_access(db, project_id, eng)
    o = A.submit_proposal(db, a, eng, body.model_dump())
    db.commit()
    return A.proposal_out(db, o)


@router.get("/proposals/mine")
def my_proposals(db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    rows = db.scalars(select(Offer).where(Offer.freelancer_id == eng.id).order_by(Offer.id.desc()).limit(200)).all()
    return [A.proposal_out(db, o, full=False) | {"project_status": o.project.status} for o in rows]


def _proposal(db: Session, proposal_id: int, user: User) -> tuple[Offer, A.Access]:
    o = db.get(Offer, proposal_id)
    if o is None:
        raise not_found("Proposal", "العرض")
    a = A.get_access(db, o.project_id, user)
    if not (a.org or a.admin or o.freelancer_id == user.id):
        raise not_found("Proposal", "العرض")
    return o, a


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o, _ = _proposal(db, proposal_id, user)
    return A.proposal_out(db, o)


@router.post("/proposals/{proposal_id}/withdraw")
def withdraw(proposal_id: int, db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    o, _ = _proposal(db, proposal_id, eng)
    A.withdraw_proposal(db, o, eng)
    db.commit()
    return A.proposal_out(db, o)


@router.post("/proposals/{proposal_id}/decision")
def decide(proposal_id: int, body: s.ProposalDecision, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    o, a = _proposal(db, proposal_id, user)
    A.decide_proposal(db, a, o, body.decision, body.note)
    db.commit()
    return A.proposal_out(db, o)


@router.post("/proposals/{proposal_id}/clarifications", status_code=201)
def answer(proposal_id: int, body: s.TextIn, db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    o, _ = _proposal(db, proposal_id, eng)
    A.answer_clarification(db, o, eng, body.body)
    db.commit()
    return A.proposal_out(db, o)


@router.post("/proposals/{proposal_id}/attachments", status_code=201)
def attach(proposal_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
           eng: User = Depends(require_engineer)):
    o, _ = _proposal(db, proposal_id, eng)
    if o.freelancer_id != eng.id or o.status not in OfferStatus.OPEN:
        raise conflict("Attachments can be added only to your open proposal.", "يمكن إرفاق الملفات بعرضك المفتوح فقط.")
    if db.scalar(select(func.count(StoredFile.id)).where(StoredFile.context_type == "proposal",
                                                       StoredFile.context_id == o.id)) >= 5:
        raise bad_request("A proposal can have at most 5 attachments.", "الحد الأقصى 5 مرفقات للعرض.")
    f = filesvc.store(db, file, eng, kind="proposal", context_type="proposal", context_id=o.id,
                      project_id=o.project_id)
    db.commit()
    return filesvc.file_out(f)


@router.post("/proposals/{proposal_id}/accept")
def accept(proposal_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o, a = _proposal(db, proposal_id, user)
    A.accept_proposal(db, a, o)
    db.commit()
    return _out(db, a)


@router.post("/projects/{project_id}/unselect")
def unselect(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    A.unselect(db, a)
    db.commit()
    return _out(db, a)


# ---------- agreement ----------
@router.get("/projects/{project_id}/agreement")
def agreement(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    if not a.participant or not a.p.accepted_offer_id:
        raise not_found("Agreement", "الاتفاقية")
    return A.agreement_text(db, a.p)


@router.post("/projects/{project_id}/agreement/accept")
def accept_agreement(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    A.engineer_accept_agreement(db, a)
    db.commit()
    return _out(db, a)


@router.post("/projects/{project_id}/start")
def start(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    A.start_work(db, a)
    db.commit()
    return _out(db, a)


# ---------- milestones ----------
def _participant(db: Session, project_id: int, user: User) -> A.Access:
    a = A.get_access(db, project_id, user)
    if not a.participant:
        raise forbidden("Only the organization and the selected engineer can see the workspace.",
                        "مساحة العمل متاحة للجهة والمهندس المختار فقط.")
    return a


def _milestones(db: Session, project_id: int) -> list[dict]:
    rows = db.scalars(select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.seq)).all()
    return [{"id": m.id, "seq": m.seq, "title": m.title, "description": m.description, "amount_cents": m.amount_cents,
             "due_date": m.due_date, "status": m.status, "approved_at": m.approved_at} for m in rows]


@router.get("/projects/{project_id}/milestones")
def milestones(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _participant(db, project_id, user)
    return _milestones(db, project_id)


@router.post("/projects/{project_id}/milestones", status_code=201)
def add_milestone(project_id: int, body: s.MilestoneIn, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    a = _participant(db, project_id, user)
    A.save_milestone(db, a, body.model_dump())
    db.commit()
    return _milestones(db, project_id)


def _milestone(db: Session, milestone_id: int, user: User) -> tuple[Milestone, A.Access]:
    m = db.get(Milestone, milestone_id)
    if m is None:
        raise not_found("Milestone", "المرحلة")
    return m, _participant(db, m.project_id, user)


@router.patch("/milestones/{milestone_id}")
def edit_milestone(milestone_id: int, body: s.MilestoneIn, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    m, a = _milestone(db, milestone_id, user)
    A.save_milestone(db, a, body.model_dump(), m)
    db.commit()
    return _milestones(db, a.p.id)


@router.delete("/milestones/{milestone_id}", status_code=204)
def remove_milestone(milestone_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m, a = _milestone(db, milestone_id, user)
    A.delete_milestone(db, a, m)
    db.commit()
    return Response(status_code=204)


@router.post("/milestones/{milestone_id}/approve")
def approve_milestone(milestone_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m, a = _milestone(db, milestone_id, user)
    inv = A.approve_milestone(db, a, m)
    db.commit()
    return {"milestones": _milestones(db, a.p.id), "invoice": finance.invoice_out(inv) if inv else None}


# ---------- tasks ----------
def _tasks(db: Session, project_id: int) -> list[dict]:
    rows = db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.id)).all()
    return [{"id": t.id, "title": t.title, "status": t.status, "milestone_id": t.milestone_id,
             "assignee": user_mini(db.get(User, t.assignee_id)) if t.assignee_id else None, "due_date": t.due_date,
             "created_at": t.created_at} for t in rows]


@router.get("/projects/{project_id}/tasks")
def tasks(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _participant(db, project_id, user)
    return _tasks(db, project_id)


@router.post("/projects/{project_id}/tasks", status_code=201)
def add_task(project_id: int, body: s.TaskIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _participant(db, project_id, user)
    A.save_task(db, a, body.model_dump())
    db.commit()
    return _tasks(db, project_id)


@router.patch("/tasks/{task_id}")
def edit_task(task_id: int, body: s.TaskIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(Task, task_id)
    if t is None:
        raise not_found("Task", "المهمة")
    a = _participant(db, t.project_id, user)
    A.save_task(db, a, body.model_dump(), t)
    db.commit()
    return _tasks(db, t.project_id)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(Task, task_id)
    if t is None:
        raise not_found("Task", "المهمة")
    a = _participant(db, t.project_id, user)
    if not ((a.org and a.org.can("work.manage")) or t.created_by == user.id):
        raise forbidden()
    db.delete(t)
    db.commit()
    return Response(status_code=204)


# ---------- deliverables & versions ----------
@router.get("/projects/{project_id}/deliverables")
def deliverables(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _participant(db, project_id, user)
    rows = db.scalars(select(Deliverable).where(Deliverable.project_id == project_id).order_by(Deliverable.id)).all()
    return [A.deliverable_out(db, d) for d in rows]


@router.post("/projects/{project_id}/deliverables", status_code=201)
def add_deliverable(project_id: int, body: s.DeliverableIn, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    a = _participant(db, project_id, user)
    d = A.add_deliverable(db, a, body.title, body.description, body.milestone_id)
    db.commit()
    return A.deliverable_out(db, d)


@router.post("/deliverables/{deliverable_id}/versions", status_code=201)
def upload_version(deliverable_id: int, file: UploadFile = File(...), note: str = Form(default="", max_length=3000),
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = db.get(Deliverable, deliverable_id)
    if d is None:
        raise not_found("Deliverable", "التسليم")
    a = _participant(db, d.project_id, user)
    a.need_hired()
    f = filesvc.store(db, file, user, kind="deliverable", context_type="deliverable", context_id=d.id,
                      project_id=d.project_id)
    A.add_version(db, a, d, f.id, note)
    db.commit()
    db.refresh(d)
    return A.deliverable_out(db, d)


@router.post("/deliverable-versions/{version_id}/review")
def review_version(version_id: int, body: s.VersionReview, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    v = db.get(DeliverableVersion, version_id)
    if v is None:
        raise not_found("Version", "النسخة")
    a = _participant(db, v.deliverable.project_id, user)
    A.review_version(db, a, v, body.decision, body.comment)
    db.commit()
    return A.deliverable_out(db, v.deliverable)


# ---------- project-level review steps ----------
@router.post("/projects/{project_id}/submit")
def submit(project_id: int, body: s.NoteIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _participant(db, project_id, user)
    A.submit_for_review(db, a, body.note)
    db.commit()
    return _out(db, a)


@router.post("/projects/{project_id}/request-revision")
def request_revision(project_id: int, body: s.NoteIn, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    a = _participant(db, project_id, user)
    A.request_project_revision(db, a, body.note)
    db.commit()
    return _out(db, a)


@router.post("/projects/{project_id}/approve")
def approve(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _participant(db, project_id, user)
    A.approve_final(db, a)
    db.commit()
    return _out(db, a)


@router.post("/projects/{project_id}/complete")
def complete(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _participant(db, project_id, user)
    A.complete(db, a)
    db.commit()
    return _out(db, a)


# ---------- files (brief / reference / working files) ----------
@router.get("/projects/{project_id}/files")
def list_files(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    stmt = select(StoredFile).where(StoredFile.project_id == project_id, StoredFile.context_type == "project",
                                    StoredFile.is_archived.is_(False))
    if not a.participant:
        stmt = stmt.where(StoredFile.kind == "brief")
    return [filesvc.file_out(f) | {"owner": user_mini(f.owner)} for f in db.scalars(stmt.order_by(StoredFile.id.desc()))]


@router.post("/projects/{project_id}/files", status_code=201)
def upload_file(project_id: int, file: UploadFile = File(...), kind: Literal["brief", "working"] = Form(...),
                note: str = Form(default="", max_length=500), db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    if kind == "brief":
        a.need("work.manage")
    elif not (a.org or a.hired):
        raise forbidden()
    if a.p.status in (P.COMPLETED, P.CANCELLED):
        raise conflict("This project is closed.", "هذا المشروع مغلق.")
    f = filesvc.store(db, file, user, kind=kind, context_type="project", context_id=project_id,
                      project_id=project_id, note=note)
    A.event(db, user, f"File uploaded: {f.filename}", f"تم رفع ملف: {f.filename}", project_id=project_id)
    db.commit()
    return filesvc.file_out(f)


@router.get("/files/{file_id}")
def download(file_id: int, inline: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    f = db.get(StoredFile, file_id)
    if f is None or not filesvc.can_download(db, user, f):
        raise not_found("File", "الملف")
    return filesvc.file_response(f, inline)


@router.delete("/files/{file_id}", status_code=204)
def archive_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Archives (hides) a brief or working file uploaded by you. Nothing is destroyed. Deliverable versions,
    verification documents and dispute evidence can't be removed."""
    f = db.get(StoredFile, file_id)
    if f is None or f.owner_id != user.id or f.context_type != "project":
        raise not_found("File", "الملف")
    p = db.get(Project, f.project_id)
    if p.status in (P.COMPLETED, P.CANCELLED):
        raise conflict("Files can't be removed from a closed project.", "لا يمكن إزالة ملفات من مشروع مغلق.")
    f.is_archived = True
    A.event(db, user, f"File archived: {f.filename}", f"تمت أرشفة ملف: {f.filename}", project_id=p.id)
    db.commit()
    return Response(status_code=204)


# ---------- comments & technical reviews ----------
@router.get("/projects/{project_id}/comments")
def comments(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _participant(db, project_id, user)
    rows = db.scalars(select(Comment).where(Comment.project_id == project_id).order_by(Comment.id)).all()
    return [{"id": c.id, "body": c.body, "kind": c.kind, "file_id": c.file_id, "author": user_mini(c.author),
             "created_at": c.created_at} for c in rows]


@router.post("/projects/{project_id}/comments", status_code=201)
def add_comment(project_id: int, body: s.CommentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _participant(db, project_id, user)
    if a.org and not a.org.can("messages.send"):
        raise forbidden()
    if body.kind == "technical_review" and not (a.org and a.org.can("work.review")):
        raise forbidden("Only reviewers of the organization can add technical reviews.",
                        "مراجعو الجهة فقط يمكنهم إضافة مراجعات فنية.")
    if a.p.status == P.CANCELLED:
        raise conflict("This project was cancelled.", "تم إلغاء هذا المشروع.")
    c = Comment(project_id=project_id, author_id=user.id, body=body.body, kind=body.kind)
    db.add(c)
    db.commit()
    return {"id": c.id}


# ---------- finance ----------
@router.get("/projects/{project_id}/finance")
def project_finance(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _participant(db, project_id, user)
    if a.org and not a.org.can("finance.view") and not a.org.can("work.manage"):
        raise forbidden()
    return finance.project_summary(db, a.p, A.agreed_price(db, a.p))
