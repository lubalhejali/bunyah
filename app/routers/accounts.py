"""Organization profiles and teams, engineer profiles, engineering disciplines and verification requests."""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import schemas as s
from app.config import get_settings
from app.database import get_db
from app.errors import bad_request, conflict, not_found
from app.models import (
    Discipline,
    EngineerProfile,
    Organization,
    OrgInvitation,
    OrgMember,
    OrgRole,
    PortfolioItem,
    Role,
    StoredFile,
    User,
    Verification,
    VerificationRequest,
)
from app.security import OrgContext, current_user, require_engineer, require_org
from app.services import audit, notify
from app.services import files as filesvc
from app.services.model_a import discipline_out
from app.services.serialize import engineer_private, engineer_public, org_private, org_public

router = APIRouter(tags=["accounts"])


# ---------- disciplines ----------
@router.get("/disciplines")
def disciplines(db: Session = Depends(get_db)):
    rows = db.scalars(select(Discipline).where(Discipline.is_active.is_(True))
                      .order_by(Discipline.sort_order, Discipline.name_en)).all()
    return [discipline_out(d) for d in rows]


# ---------- organizations ----------
@router.get("/organizations/me")
def my_org(db: Session = Depends(get_db), ctx: OrgContext = Depends(require_org)):
    return org_private(db, ctx.org) | {"my_role": ctx.member.org_role}


@router.patch("/organizations/me")
def update_org(body: s.OrgUpdate, db: Session = Depends(get_db), ctx: OrgContext = Depends(require_org)):
    ctx.require("org.edit")
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    legal = {"name", "cr_number", "license_info"} & changes.keys()
    for k, v in changes.items():
        setattr(ctx.org, k, v)
    if legal and ctx.org.verification_status == Verification.VERIFIED:
        # Changing legal identity details needs a new check by the BUNYAH team.
        ctx.org.verification_status = Verification.UNVERIFIED
        audit.record(db, ctx.user, "organization.verification_reset", "organization", ctx.org.id,
                     fields=",".join(sorted(legal)))
    db.commit()
    return org_private(db, ctx.org) | {"my_role": ctx.member.org_role}


@router.post("/organizations/me/logo")
def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db), ctx: OrgContext = Depends(require_org)):
    ctx.require("org.edit")
    f = filesvc.store(db, file, ctx.user, kind="logo", context_type="logo", context_id=ctx.org.id, images_only=True)
    ctx.org.logo_file_id = f.id
    db.commit()
    return {"logo_file_id": f.id}


@router.get("/organizations/{org_id}")
def org_profile(org_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    o = db.get(Organization, org_id)
    if o is None:
        raise not_found("Organization", "الجهة")
    return org_public(db, o)


@router.get("/organizations/me/members")
def members(db: Session = Depends(get_db), ctx: OrgContext = Depends(require_org)):
    rows = db.scalars(select(OrgMember).where(OrgMember.org_id == ctx.org.id).order_by(OrgMember.id)).all()
    invites = db.scalars(select(OrgInvitation).where(
        OrgInvitation.org_id == ctx.org.id, OrgInvitation.accepted_at.is_(None), OrgInvitation.revoked_at.is_(None),
        OrgInvitation.expires_at > datetime.now(UTC))).all() if ctx.can("team.manage") else []
    return {
        "members": [{"id": m.id, "user_id": m.user_id, "name": m.user.name,
                     "email": m.user.email if ctx.can("team.manage") else None,
                     "org_role": m.org_role, "is_active": m.is_active, "is_me": m.user_id == ctx.user.id}
                    for m in rows],
        "invitations": [{"id": i.id, "email": i.email, "name": i.name, "org_role": i.org_role,
                         "expires_at": i.expires_at} for i in invites],
        "can_manage": ctx.can("team.manage"),
    }


@router.post("/organizations/me/invitations", status_code=201)
def invite(body: s.InviteIn, db: Session = Depends(get_db), ctx: OrgContext = Depends(require_org)):
    """Creates a one-time invitation link (shown once). E-mail sending is not configured in the prototype."""
    ctx.require("team.manage")
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
        raise conflict("That e-mail already has a BUNYAH account. Each account can belong to one organization.",
                       "هذا البريد مسجل مسبقًا. يمكن لكل حساب الانتماء لجهة واحدة فقط.")
    token = secrets.token_urlsafe(32)
    inv = OrgInvitation(org_id=ctx.org.id, email=body.email.lower(), name=body.name, org_role=body.org_role,
                        token_hash=hashlib.sha256(token.encode()).hexdigest(), invited_by=ctx.user.id,
                        expires_at=datetime.now(UTC) + timedelta(days=7))
    db.add(inv)
    audit.record(db, ctx.user, "team.invited", "organization", ctx.org.id, email=body.email, role=body.org_role)
    db.commit()
    return {"id": inv.id, "link": f"{get_settings().public_base_url.rstrip('/')}/#/invite/{token}",
            "expires_at": inv.expires_at}


@router.delete("/organizations/me/invitations/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, db: Session = Depends(get_db), ctx: OrgContext = Depends(require_org)):
    ctx.require("team.manage")
    inv = db.get(OrgInvitation, invite_id)
    if inv is None or inv.org_id != ctx.org.id:
        raise not_found("Invitation", "الدعوة")
    inv.revoked_at = datetime.now(UTC)
    audit.record(db, ctx.user, "team.invitation_revoked", "organization", ctx.org.id, email=inv.email)
    db.commit()
    return Response(status_code=204)


@router.patch("/organizations/me/members/{member_id}")
def update_member(member_id: int, body: s.MemberUpdate, db: Session = Depends(get_db),
                  ctx: OrgContext = Depends(require_org)):
    ctx.require("team.manage")
    m = db.get(OrgMember, member_id)
    if m is None or m.org_id != ctx.org.id:
        raise not_found("Team member", "عضو الفريق")
    changes = body.model_dump(exclude_unset=True)
    owners = db.scalar(select(func.count(OrgMember.id)).where(
        OrgMember.org_id == ctx.org.id, OrgMember.org_role == OrgRole.OWNER, OrgMember.is_active.is_(True)))
    losing_owner = m.org_role == OrgRole.OWNER and m.is_active and (
        changes.get("org_role", OrgRole.OWNER) != OrgRole.OWNER or changes.get("is_active") is False)
    if losing_owner and owners <= 1:
        raise conflict("An organization needs at least one active owner.", "يجب أن يكون للجهة مالك نشط واحد على الأقل.")
    old = (m.org_role, m.is_active)
    for k, v in changes.items():
        if v is not None:
            setattr(m, k, v)
    audit.record(db, ctx.user, "team.member_changed", "org_member", m.id, before=str(old),
                 after=str((m.org_role, m.is_active)))
    db.commit()
    return {"id": m.id, "org_role": m.org_role, "is_active": m.is_active}


# ---------- verification ----------
def _submit_verification(db: Session, user: User, subject_type: str, subject_id: int, note: str,
                         documents: list[UploadFile]) -> VerificationRequest:
    if not documents or not any(d.filename for d in documents):
        raise bad_request("Attach at least one verification document.", "أرفق مستند توثيق واحدًا على الأقل.",
                          "DOCUMENT_REQUIRED")
    if len(documents) > 5:
        raise bad_request("Attach at most 5 documents.", "يمكن إرفاق 5 مستندات كحد أقصى.")
    if db.scalar(select(VerificationRequest.id).where(VerificationRequest.subject_type == subject_type,
                                                      VerificationRequest.subject_id == subject_id,
                                                      VerificationRequest.status == Verification.PENDING)):
        raise conflict("A verification request is already waiting for review.", "يوجد طلب توثيق قيد المراجعة.")
    vr = VerificationRequest(subject_type=subject_type, subject_id=subject_id, submitted_by=user.id,
                             applicant_note=note)
    db.add(vr)
    db.flush()
    for d in documents:
        if d.filename:
            filesvc.store(db, d, user, kind="verification", context_type="verification", context_id=vr.id)
    audit.record(db, user, "verification.submitted", subject_type, subject_id, request_id=vr.id)
    return vr


@router.post("/organizations/me/verification", status_code=201)
def org_verification(note: str = Form(default="", max_length=2000), documents: list[UploadFile] = File(...),
                     db: Session = Depends(get_db), ctx: OrgContext = Depends(require_org)):
    ctx.require("org.edit")
    o = ctx.org
    missing = [f for f in ("cr_number", "city", "representative_name") if not getattr(o, f)]
    if missing:
        raise bad_request("Complete the commercial registration number, city and authorized representative first.",
                          "أكمل رقم السجل التجاري والمدينة والممثل المفوض أولاً.", "PROFILE_INCOMPLETE")
    vr = _submit_verification(db, ctx.user, "organization", o.id, note, documents)
    o.verification_status = Verification.PENDING
    notify.notify(db, notify.admin_user_ids(db), "verification_submitted", o.name, "/admin/verifications")
    db.commit()
    return {"id": vr.id, "status": vr.status}


@router.post("/engineers/me/verification", status_code=201)
def eng_verification(note: str = Form(default="", max_length=2000), documents: list[UploadFile] = File(...),
                     db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    p = _profile(db, eng)
    if not (p.title and p.discipline_id and p.years_experience is not None):
        raise bad_request("Complete your professional title and discipline first.",
                          "أكمل المسمى المهني والتخصص أولاً.", "PROFILE_INCOMPLETE")
    vr = _submit_verification(db, eng, "engineer", eng.id, note, documents)
    p.verification_status = Verification.PENDING
    notify.notify(db, notify.admin_user_ids(db), "verification_submitted", eng.name, "/admin/verifications")
    db.commit()
    return {"id": vr.id, "status": vr.status}


@router.get("/verification/mine")
def my_verifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role == Role.ORGANIZATION:
        m = db.scalar(select(OrgMember).where(OrgMember.user_id == user.id))
        cond = (VerificationRequest.subject_type == "organization") & (VerificationRequest.subject_id == (m.org_id if m else -1))
    else:
        cond = (VerificationRequest.subject_type == "engineer") & (VerificationRequest.subject_id == user.id)
    rows = db.scalars(select(VerificationRequest).where(cond).order_by(VerificationRequest.id.desc())).all()
    return [{"id": v.id, "status": v.status, "applicant_note": v.applicant_note, "reviewer_note": v.reviewer_note,
             "created_at": v.created_at, "reviewed_at": v.reviewed_at,
             "documents": [filesvc.file_out(f) for f in db.scalars(select(StoredFile).where(
                 StoredFile.context_type == "verification", StoredFile.context_id == v.id)).all()]} for v in rows]


# ---------- engineers ----------
def _profile(db: Session, u: User) -> EngineerProfile:
    p = u.engineer_profile
    if p is None:
        p = EngineerProfile(user_id=u.id)
        db.add(p)
        db.flush()
    return p


@router.get("/engineers")
def search_engineers(q: str = "", discipline_id: int | None = None, city: str = "", availability: str = "",
                     verified_only: bool = False, page: int = 1, per_page: int = 20,
                     db: Session = Depends(get_db), _: User = Depends(current_user)):
    per_page, page = max(1, min(per_page, 50)), max(page, 1)
    stmt = select(User).join(EngineerProfile, EngineerProfile.user_id == User.id).where(
        User.role == Role.ENGINEER, User.is_active.is_(True))
    if q:
        like = f"%{q.strip()[:80]}%"
        stmt = stmt.where(or_(User.name.ilike(like), EngineerProfile.title.ilike(like),
                              EngineerProfile.specializations.ilike(like),
                              EngineerProfile.software_skills.ilike(like)))
    if discipline_id:
        stmt = stmt.where(EngineerProfile.discipline_id == discipline_id)
    if city:
        stmt = stmt.where(EngineerProfile.city.ilike(f"%{city.strip()[:80]}%"))
    if availability in ("available", "partial", "unavailable"):
        stmt = stmt.where(EngineerProfile.availability == availability)
    if verified_only:
        stmt = stmt.where(EngineerProfile.verification_status == Verification.VERIFIED)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    data = []
    for u in rows:
        e = engineer_public(db, u)
        data.append({k: e[k] for k in ("id", "name", "title", "discipline", "specializations", "years_experience",
                                       "city", "availability", "work_preference", "verified", "average_rating",
                                       "rating_count", "rate_min_cents", "rate_max_cents")})
    return {"data": data, "total": total, "page": page, "per_page": per_page}


@router.get("/engineers/me")
def my_engineer_profile(db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    _profile(db, eng)
    return engineer_private(db, eng)


@router.patch("/engineers/me")
def update_engineer(body: s.EngineerUpdate, db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    p = _profile(db, eng)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("discipline_id") and db.get(Discipline, changes["discipline_id"]) is None:
        raise bad_request("Unknown discipline.", "تخصص غير معروف.")
    rmin = changes.get("rate_min_cents", p.rate_min_cents)
    rmax = changes.get("rate_max_cents", p.rate_max_cents)
    if rmin and rmax and rmin > rmax:
        raise bad_request("The minimum rate is higher than the maximum.", "الحد الأدنى للأجر أعلى من الحد الأقصى.")
    for k, v in changes.items():
        setattr(p, k, v)
    if {"registration_number", "registration_body"} & changes.keys() and p.verification_status == Verification.VERIFIED:
        p.verification_status = Verification.UNVERIFIED
        audit.record(db, eng, "engineer.verification_reset", "engineer", eng.id)
    p.updated_at = datetime.now(UTC)
    db.commit()
    return engineer_private(db, eng)


@router.post("/engineers/me/cv")
def upload_cv(file: UploadFile = File(...), db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    p = _profile(db, eng)
    if (file.filename or "").rsplit(".", 1)[-1].lower() not in ("pdf", "docx"):
        raise bad_request("Upload your CV as PDF or DOCX.", "ارفع السيرة الذاتية بصيغة PDF أو DOCX.", "FILE_TYPE")
    f = filesvc.store(db, file, eng, kind="cv", context_type="cv", context_id=eng.id)
    p.cv_file_id = f.id
    db.commit()
    return {"cv_file_id": f.id}


@router.post("/engineers/me/portfolio", status_code=201)
def add_portfolio(title: str = Form(min_length=2, max_length=160), description: str = Form(default="", max_length=3000),
                  link: str = Form(default="", max_length=500), file: UploadFile | None = File(default=None),
                  db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    body = s.PortfolioIn(title=title, description=description, link=link)
    item = PortfolioItem(user_id=eng.id, **body.model_dump())
    if file is not None and file.filename:
        f = filesvc.store(db, file, eng, kind="portfolio", context_type="portfolio", context_id=eng.id)
        item.image_file_id = f.id
    db.add(item)
    db.commit()
    return {"id": item.id}


@router.delete("/engineers/me/portfolio/{item_id}", status_code=204)
def delete_portfolio(item_id: int, db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    item = db.get(PortfolioItem, item_id)
    if item is None or item.user_id != eng.id:
        raise not_found("Portfolio item", "عنصر المعرض")
    if item.image_file_id:
        f = db.get(StoredFile, item.image_file_id)
        if f:
            f.is_archived = True  # file kept (archived), not destroyed
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@router.get("/engineers/{user_id}")
def engineer_profile(user_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    u = db.get(User, user_id)
    if u is None or u.role != Role.ENGINEER or not u.is_active:
        raise not_found("Engineer", "المهندس")
    return engineer_public(db, u)
