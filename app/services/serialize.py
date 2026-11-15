"""Turns accounts and profiles into JSON. Each function lists exactly which fields are shared, so private data
(e-mail, phone, registration numbers, verification documents) is never sent by accident."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    EngineerProfile,
    Organization,
    OrgMember,
    PortfolioItem,
    Project,
    ProjectStatus,
    Rating,
    Role,
    ServiceContract,
    User,
    Verification,
)
from app.services.model_a import discipline_out


def engineer_rating(db: Session, user_id: int) -> tuple[float | None, int]:
    avg, count = db.execute(select(func.avg(Rating.rating), func.count(Rating.id)).where(
        Rating.engineer_id == user_id, Rating.reviewer_side == "organization")).one()
    return (round(float(avg), 2) if avg is not None else None), int(count)


def org_rating(db: Session, org_id: int) -> tuple[float | None, int]:
    avg, count = db.execute(select(func.avg(Rating.rating), func.count(Rating.id)).where(
        Rating.org_id == org_id, Rating.reviewer_side == "engineer")).one()
    return (round(float(avg), 2) if avg is not None else None), int(count)


def org_public(db: Session, o: Organization) -> dict:
    avg, count = org_rating(db, o.id)
    return {"id": o.id, "name": o.name, "name_ar": o.name_ar, "org_type": o.org_type, "city": o.city,
            "description": o.description, "website": o.website, "logo_file_id": o.logo_file_id,
            "verification_status": o.verification_status, "verified": o.verification_status == Verification.VERIFIED,
            "average_rating": avg, "rating_count": count, "created_at": o.created_at,
            "projects_posted": db.scalar(select(func.count(Project.id)).where(
                Project.org_id == o.id, Project.status != ProjectStatus.DRAFT)) or 0}


def org_private(db: Session, o: Organization) -> dict:
    """For the organization's own members and administrators."""
    return org_public(db, o) | {
        "cr_number": o.cr_number, "license_info": o.license_info, "address": o.address,
        "contact_email": o.contact_email, "contact_phone": o.contact_phone,
        "representative_name": o.representative_name, "representative_title": o.representative_title}


def engineer_public(db: Session, u: User) -> dict:
    p = u.engineer_profile or EngineerProfile(user_id=u.id)
    avg, count = engineer_rating(db, u.id)
    done = (db.scalar(select(func.count(Project.id)).where(Project.freelancer_id == u.id,
                                                          Project.status == ProjectStatus.COMPLETED)) or 0) + \
           (db.scalar(select(func.count(ServiceContract.id)).where(ServiceContract.engineer_id == u.id,
                                                                    ServiceContract.ended_at.is_not(None))) or 0)
    portfolio = db.scalars(select(PortfolioItem).where(PortfolioItem.user_id == u.id)
                           .order_by(PortfolioItem.id.desc())).all()
    reviews = db.scalars(select(Rating).where(Rating.engineer_id == u.id, Rating.reviewer_side == "organization")
                         .order_by(Rating.id.desc()).limit(20)).all()
    return {"id": u.id, "name": u.name, "title": p.title or u.headline, "discipline": discipline_out(p.discipline),
            "specializations": p.specializations, "years_experience": p.years_experience or 0,
            "education": p.education, "qualifications": p.qualifications, "certifications": p.certifications,
            "registration_body": p.registration_body, "has_registration": bool(p.registration_number),
            "software_skills": p.software_skills or u.skills, "languages": p.languages, "city": p.city or u.location,
            "availability": p.availability or "available", "work_preference": p.work_preference or "hybrid",
            "rate_min_cents": p.rate_min_cents, "rate_max_cents": p.rate_max_cents, "bio": p.bio or u.bio,
            "has_cv": bool(p.cv_file_id), "cv_file_id": p.cv_file_id,
            "verification_status": p.verification_status or Verification.UNVERIFIED,
            "verified": p.verification_status == Verification.VERIFIED,
            "average_rating": avg, "rating_count": count, "completed_engagements": done,
            "portfolio": [{"id": i.id, "title": i.title, "description": i.description, "link": i.link,
                           "image_file_id": i.image_file_id} for i in portfolio],
            "reviews": [{"id": r.id, "rating": r.rating, "text": r.text, "created_at": r.created_at,
                         "org_name": db.get(Organization, r.org_id).name} for r in reviews],
            "member_since": u.created_at}


def engineer_private(db: Session, u: User) -> dict:
    p = u.engineer_profile or EngineerProfile(user_id=u.id)
    return engineer_public(db, u) | {"registration_number": p.registration_number, "phone": u.phone}


def me_out(db: Session, u: User) -> dict:
    from app.config import get_settings
    from app.security import is_admin, permissions_for
    s = get_settings()
    out = {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role, "locale": u.locale,
           "is_admin": is_admin(u), "currency": s.currency, "demo_mode": s.demo_mode,
           "created_at": u.created_at, "organization": None, "org_role": None, "permissions": []}
    if u.role == Role.ORGANIZATION:
        m = db.scalar(select(OrgMember).where(OrgMember.user_id == u.id, OrgMember.is_active.is_(True)))
        if m:
            out["organization"] = org_private(db, db.get(Organization, m.org_id))
            out["org_role"], out["permissions"] = m.org_role, permissions_for(m.org_role)
    if u.role == Role.ENGINEER:
        p = u.engineer_profile
        out["verification_status"] = p.verification_status if p else Verification.UNVERIFIED
    return out
