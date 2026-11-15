"""Database tables. Each class = one table. Money is always stored in halalas (1 SAR = 100), as whole numbers.

Layout
- Accounts: User, Organization, OrgMember, OrgInvitation, EngineerProfile, Discipline, VerificationRequest
- Model A (projects): Project, Offer (= proposal), ProposalClarification, Milestone, Task, Deliverable,
  DeliverableVersion, Comment, ProjectEvent
- Model B (short-term services): ServiceRequest, ServiceApplication, ServiceContract, BillingPeriod, TimeEntry
- Shared: StoredFile, Conversation, Message, Notification, Dispute, DisputeEntry, Escalation, Rating,
  FeeRule, SimTransaction, SimInvoice, PlatformSetting, Holiday, AuditLog
- Legacy EngConnect tables kept unchanged so no old data is lost: Payment, Withdrawal, Review, PortfolioItem
"""
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy import DateTime as _DateTime
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class DateTime(TypeDecorator):
    """Always hands back times marked as UTC (the local SQLite file forgets the time zone; PostgreSQL keeps it)."""

    impl = _DateTime(timezone=True)
    cache_ok = True

    def __init__(self, timezone: bool = True):
        super().__init__()

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


def _id() -> Mapped[int]:
    return mapped_column(primary_key=True)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow)


# =====================================================================================
# Accounts
# =====================================================================================
class Role:
    """Account types. (Old EngConnect values 'office' / 'freelancer' are migrated to these.)"""
    ORGANIZATION = "organization"
    ENGINEER = "engineer"
    ADMIN = "admin"
    ALL = (ORGANIZATION, ENGINEER, ADMIN)


class Verification:
    UNVERIFIED = "unverified"   # profile not submitted yet
    PENDING = "pending"         # waiting for an administrator
    NEEDS_INFO = "needs_info"   # administrator asked for more documents
    VERIFIED = "verified"
    REJECTED = "rejected"
    ALL = (UNVERIFIED, PENDING, NEEDS_INFO, VERIFIED, REJECTED)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = _id()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(40), default="")          # private, never shown publicly
    locale: Mapped[str] = mapped_column(String(5), default="ar")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Legacy EngConnect profile columns (still read for old accounts; new profiles use EngineerProfile).
    headline: Mapped[str] = mapped_column(String(160), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    website: Mapped[str] = mapped_column(String(255), default="")
    skills: Mapped[str] = mapped_column(String(500), default="")
    company_name: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = _created()

    portfolio: Mapped[list["PortfolioItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="PortfolioItem.id.desc()"
    )
    membership: Mapped["OrgMember | None"] = relationship(back_populates="user", uselist=False,
                                                          foreign_keys="OrgMember.user_id")
    engineer_profile: Mapped["EngineerProfile | None"] = relationship(back_populates="user", uselist=False)


class Discipline(Base):
    __tablename__ = "disciplines"

    id: Mapped[int] = _id()
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class OrgType:
    ALL = ("engineering_consultancy", "engineering_firm", "contractor", "developer", "government", "other")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = _id()
    name: Mapped[str] = mapped_column(String(160), index=True)
    name_ar: Mapped[str] = mapped_column(String(160), default="")
    org_type: Mapped[str] = mapped_column(String(40), default="engineering_consultancy")
    cr_number: Mapped[str] = mapped_column(String(40), default="")         # commercial registration
    license_info: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    contact_email: Mapped[str] = mapped_column(String(255), default="")    # private
    contact_phone: Mapped[str] = mapped_column(String(40), default="")     # private
    representative_name: Mapped[str] = mapped_column(String(120), default="")
    representative_title: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    website: Mapped[str] = mapped_column(String(255), default="")
    logo_file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default=Verification.UNVERIFIED, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()

    members: Mapped[list["OrgMember"]] = relationship(back_populates="org", cascade="all, delete-orphan")


class OrgRole:
    OWNER = "owner"
    PROJECT_MANAGER = "project_manager"
    TECHNICAL_REVIEWER = "technical_reviewer"
    FINANCE = "finance"
    VIEWER = "viewer"
    ALL = (OWNER, PROJECT_MANAGER, TECHNICAL_REVIEWER, FINANCE, VIEWER)


class OrgMember(Base):
    __tablename__ = "org_members"
    __table_args__ = (UniqueConstraint("user_id", name="uq_org_member_user"),)  # one organization per account

    id: Mapped[int] = _id()
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    org_role: Mapped[str] = mapped_column(String(30), default=OrgRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()

    org: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="membership", foreign_keys=[user_id])


class OrgInvitation(Base):
    __tablename__ = "org_invitations"

    id: Mapped[int] = _id()
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120), default="")
    org_role: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class EngineerProfile(Base):
    __tablename__ = "engineer_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    discipline_id: Mapped[int | None] = mapped_column(ForeignKey("disciplines.id"), nullable=True, index=True)
    specializations: Mapped[str] = mapped_column(String(500), default="")
    years_experience: Mapped[int] = mapped_column(Integer, default=0)
    education: Mapped[str] = mapped_column(Text, default="")
    qualifications: Mapped[str] = mapped_column(Text, default="")
    certifications: Mapped[str] = mapped_column(Text, default="")
    registration_body: Mapped[str] = mapped_column(String(160), default="")   # e.g. professional body name
    registration_number: Mapped[str] = mapped_column(String(80), default="")  # shown only to admins
    software_skills: Mapped[str] = mapped_column(String(500), default="")
    languages: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    availability: Mapped[str] = mapped_column(String(20), default="available")  # available|partial|unavailable
    work_preference: Mapped[str] = mapped_column(String(20), default="hybrid")  # remote|onsite|hybrid
    rate_min_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)  # expected daily rate range
    rate_max_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bio: Mapped[str] = mapped_column(Text, default="")
    cv_file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default=Verification.UNVERIFIED, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = _created()

    user: Mapped[User] = relationship(back_populates="engineer_profile")
    discipline: Mapped[Discipline | None] = relationship()


class VerificationRequest(Base):
    __tablename__ = "verification_requests"

    id: Mapped[int] = _id()
    subject_type: Mapped[str] = mapped_column(String(20), index=True)   # organization | engineer
    subject_id: Mapped[int] = mapped_column(Integer, index=True)        # organization id or user id
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default=Verification.PENDING, index=True)
    applicant_note: Mapped[str] = mapped_column(Text, default="")
    reviewer_note: Mapped[str] = mapped_column(Text, default="")
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


# =====================================================================================
# Files (versioned deliverables use DeliverableVersion -> StoredFile)
# =====================================================================================
class StoredFile(Base):
    """File metadata. The bytes live in the storage backend chosen in settings ('database' by default, which
    survives Render restarts; 'local' folder for development; object storage can be added later)."""

    __tablename__ = "files"

    id: Mapped[int] = _id()
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    # What the file belongs to; decides who may download it (see services/files.py: can_download).
    context_type: Mapped[str] = mapped_column(String(30), default="project", index=True)
    context_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    storage_backend: Mapped[str] = mapped_column(String(20), default="database")
    storage_key: Mapped[str] = mapped_column(String(300), default="")
    data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()

    owner: Mapped[User] = relationship()


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(500), default="")
    image_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    created_at: Mapped[datetime] = _created()

    user: Mapped[User] = relationship(back_populates="portfolio")


# =====================================================================================
# Model A - project-based services
# =====================================================================================
class ProjectStatus:
    DRAFT = "draft"
    PUBLISHED = "published"
    APPLICATIONS_CLOSED = "applications_closed"
    UNDER_EVALUATION = "under_evaluation"
    SHORTLISTED = "shortlisted"
    PROPOSAL_ACCEPTED = "proposal_accepted"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    REVISION = "revision_requested"
    RESUBMITTED = "resubmitted"
    APPROVED = "approved"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    ALL = (DRAFT, PUBLISHED, APPLICATIONS_CLOSED, UNDER_EVALUATION, SHORTLISTED, PROPOSAL_ACCEPTED, IN_PROGRESS,
           SUBMITTED, REVISION, RESUBMITTED, APPROVED, COMPLETED, CANCELLED, DISPUTED)
    EVALUATING = (PUBLISHED, APPLICATIONS_CLOSED, UNDER_EVALUATION, SHORTLISTED)
    WORKING = (IN_PROGRESS, SUBMITTED, REVISION, RESUBMITTED, APPROVED)
    ACTIVE = (PROPOSAL_ACCEPTED, IN_PROGRESS, SUBMITTED, REVISION, RESUBMITTED, APPROVED, DISPUTED)
    IN_REVIEW = (SUBMITTED, RESUBMITTED)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = _id()
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # the member who created it
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    discipline_id: Mapped[int | None] = mapped_column(ForeignKey("disciplines.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(Text, default="")
    deliverables_text: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[str] = mapped_column(Text, default="")       # technical requirements
    qualifications: Mapped[str] = mapped_column(Text, default="")     # required qualifications
    category: Mapped[str] = mapped_column(String(80), default="", index=True)  # legacy free-text category
    work_mode: Mapped[str] = mapped_column(String(10), index=True)    # remote | onsite | hybrid
    location: Mapped[str] = mapped_column(String(160), default="")
    budget_min_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_budget_cents: Mapped[int] = mapped_column(Integer)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)   # expected duration (calendar days)
    proposal_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)  # submission deadline
    deadline: Mapped[date] = mapped_column(Date)                                 # target completion date
    status: Mapped[str] = mapped_column(String(30), default=ProjectStatus.DRAFT, index=True)
    status_before_dispute: Mapped[str] = mapped_column(String(30), default="")
    freelancer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    accepted_offer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agreement_engineer_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agreement_org_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    review_escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped[Organization | None] = relationship()
    office: Mapped[User] = relationship(foreign_keys=[office_id])
    freelancer: Mapped[User | None] = relationship(foreign_keys=[freelancer_id])
    discipline: Mapped[Discipline | None] = relationship()
    offers: Mapped[list["Offer"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    @property
    def is_delayed(self) -> bool:
        if self.status in (ProjectStatus.PROPOSAL_ACCEPTED, ProjectStatus.IN_PROGRESS, ProjectStatus.REVISION):
            from app.services.calendar import today as biz_today  # local import: calendar imports models
            return biz_today() > self.deadline
        return False


class OfferStatus:
    """Proposal statuses (the table is still called 'offers' from EngConnect)."""
    SUBMITTED = "submitted"
    SHORTLISTED = "shortlisted"
    CLARIFICATION = "clarification_requested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    OPEN = (SUBMITTED, SHORTLISTED, CLARIFICATION)


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("project_id", "freelancer_id", name="uq_offer_project_freelancer"),)

    id: Mapped[int] = _id()
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    freelancer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    price_cents: Mapped[int] = mapped_column(Integer)
    delivery_date: Mapped[date] = mapped_column(Date)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text)                         # summary / cover letter
    technical_approach: Mapped[str] = mapped_column(Text, default="")  # methodology
    status: Mapped[str] = mapped_column(String(30), default=OfferStatus.SUBMITTED, index=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="offers")
    freelancer: Mapped[User] = relationship()


class ProposalClarification(Base):
    __tablename__ = "proposal_clarifications"

    id: Mapped[int] = _id()
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()

    author: Mapped[User] = relationship()


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = _id()
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned | in_progress | approved
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = _id()
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="todo")  # todo | in_progress | done
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created()


class Deliverable(Base):
    __tablename__ = "deliverables"

    id: Mapped[int] = _id()
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    # awaiting_upload | under_review | revision_requested | approved
    status: Mapped[str] = mapped_column(String(30), default="awaiting_upload")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created()

    versions: Mapped[list["DeliverableVersion"]] = relationship(
        back_populates="deliverable", order_by="DeliverableVersion.version_no")


class DeliverableVersion(Base):
    """One uploaded version. Versions are never overwritten: a correction is always a new version."""

    __tablename__ = "deliverable_versions"
    __table_args__ = (UniqueConstraint("deliverable_id", "version_no", name="uq_deliverable_version"),)

    id: Mapped[int] = _id()
    deliverable_id: Mapped[int] = mapped_column(ForeignKey("deliverables.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(30), default="under_review")
    review_comment: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()

    deliverable: Mapped[Deliverable] = relationship(back_populates="versions")
    file: Mapped[StoredFile] = relationship()
    uploader: Mapped[User] = relationship(foreign_keys=[uploaded_by])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])


class Comment(Base):
    """Comments and technical review notes inside a project workspace."""

    __tablename__ = "comments"

    id: Mapped[int] = _id()
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="comment")  # comment | technical_review
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()

    author: Mapped[User] = relationship()


class ProjectEvent(Base):
    """Activity timeline line for a project or a service request."""

    __tablename__ = "project_events"

    id: Mapped[int] = _id()
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("service_requests.id"), index=True, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    text: Mapped[str] = mapped_column(String(300))
    text_ar: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = _created()


# =====================================================================================
# Model B - short-term engineering service contracts
# =====================================================================================
class RequestStatus:
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    APPLICATIONS_OPEN = "applications_open"
    UNDER_EVALUATION = "under_evaluation"
    SELECTED = "selected"
    CONTRACT_PREPARATION = "contract_preparation"
    AWAITING_SIGNATURES = "awaiting_signatures"
    ACTIVE = "active"
    NEAR_EXPIRY = "near_expiry"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"   # withdrawn by the organization before a contract exists
    ALL = (DRAFT, SUBMITTED, PENDING_REVIEW, PUBLISHED, APPLICATIONS_OPEN, UNDER_EVALUATION, SELECTED,
           CONTRACT_PREPARATION, AWAITING_SIGNATURES, ACTIVE, NEAR_EXPIRY, COMPLETED, TERMINATED, DISPUTED, CANCELLED)
    RUNNING = (ACTIVE, NEAR_EXPIRY)


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id: Mapped[int] = _id()
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    discipline_id: Mapped[int | None] = mapped_column(ForeignKey("disciplines.id"), nullable=True, index=True)
    specialization: Mapped[str] = mapped_column(String(200), default="")
    qualifications: Mapped[str] = mapped_column(Text, default="")
    min_experience_years: Mapped[int] = mapped_column(Integer, default=0)
    duration_working_days: Mapped[int] = mapped_column(Integer)
    hours_per_day: Mapped[int] = mapped_column(Integer, default=8)
    daily_rate_cents: Mapped[int] = mapped_column(Integer)
    work_mode: Mapped[str] = mapped_column(String(10), default="onsite")
    location: Mapped[str] = mapped_column(String(160), default="")
    start_date: Mapped[date] = mapped_column(Date)
    responsibilities: Mapped[str] = mapped_column(Text, default="")
    outputs: Mapped[str] = mapped_column(Text, default="")   # required deliverables / work outputs
    status: Mapped[str] = mapped_column(String(30), default=RequestStatus.DRAFT, index=True)
    status_before_dispute: Mapped[str] = mapped_column(String(30), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    selected_application_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped[Organization] = relationship()
    discipline: Mapped[Discipline | None] = relationship()


class ServiceApplication(Base):
    __tablename__ = "service_applications"
    __table_args__ = (UniqueConstraint("request_id", "engineer_id", name="uq_application_request_engineer"),)

    id: Mapped[int] = _id()
    request_id: Mapped[int] = mapped_column(ForeignKey("service_requests.id"), index=True)
    engineer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    cover_letter: Mapped[str] = mapped_column(Text)
    proposed_daily_rate_cents: Mapped[int] = mapped_column(Integer)
    available_from: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="submitted")  # submitted|shortlisted|selected|rejected|withdrawn
    decision_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()

    request: Mapped[ServiceRequest] = relationship()
    engineer: Mapped[User] = relationship()


class ServiceContract(Base):
    __tablename__ = "service_contracts"

    id: Mapped[int] = _id()
    request_id: Mapped[int] = mapped_column(ForeignKey("service_requests.id"), unique=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    engineer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("service_applications.id"))
    start_date: Mapped[date] = mapped_column(Date)
    working_days: Mapped[int] = mapped_column(Integer)
    end_date: Mapped[date] = mapped_column(Date)
    daily_rate_cents: Mapped[int] = mapped_column(Integer)
    hours_per_day: Mapped[int] = mapped_column(Integer, default=8)
    period_length_days: Mapped[int] = mapped_column(Integer, default=20)
    terms: Mapped[str] = mapped_column(Text, default="")
    org_signed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    org_signature_name: Mapped[str] = mapped_column(String(120), default="")
    org_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engineer_signature_name: Mapped[str] = mapped_column(String(120), default="")
    engineer_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_reason: Mapped[str] = mapped_column(Text, default="")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()

    request: Mapped[ServiceRequest] = relationship()
    engineer: Mapped[User] = relationship(foreign_keys=[engineer_id])
    org: Mapped[Organization] = relationship()
    periods: Mapped[list["BillingPeriod"]] = relationship(order_by="BillingPeriod.seq")


class BillingPeriod(Base):
    __tablename__ = "billing_periods"
    __table_args__ = (UniqueConstraint("contract_id", "seq", name="uq_period_seq"),)

    id: Mapped[int] = _id()
    contract_id: Mapped[int] = mapped_column(ForeignKey("service_contracts.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    working_days: Mapped[int] = mapped_column(Integer)
    # open | submitted | revision_requested | approved | disputed
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    approved_days: Mapped[float] = mapped_column(default=0.0)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    review_comment: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    review_escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    contract: Mapped[ServiceContract] = relationship(back_populates="periods")


class TimeEntry(Base):
    __tablename__ = "time_entries"
    __table_args__ = (UniqueConstraint("contract_id", "work_date", name="uq_time_entry_day"),)

    id: Mapped[int] = _id()
    contract_id: Mapped[int] = mapped_column(ForeignKey("service_contracts.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("billing_periods.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date)
    day_fraction: Mapped[float] = mapped_column(default=1.0)  # 1 = full day, 0.5 = half day
    hours: Mapped[float] = mapped_column(default=8.0)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="recorded")  # recorded | approved | rejected
    created_at: Mapped[datetime] = _created()


# =====================================================================================
# Messaging and notifications
# =====================================================================================
class Conversation(Base):
    """A private chat between an organization (its members) and an engineer."""

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("office_id", "freelancer_id", name="uq_conversation_pair"),)

    id: Mapped[int] = _id()
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)       # org member who started it
    freelancer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)   # the engineer
    office_last_read_id: Mapped[int] = mapped_column(Integer, default=0)
    freelancer_last_read_id: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    office: Mapped[User] = relationship(foreign_keys=[office_id])
    freelancer: Mapped[User] = relationship(foreign_keys=[freelancer_id])
    org: Mapped[Organization | None] = relationship()


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = _id()
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title_en: Mapped[str] = mapped_column(String(300))
    title_ar: Mapped[str] = mapped_column(String(300))
    link: Mapped[str] = mapped_column(String(200), default="")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_status: Mapped[str] = mapped_column(String(20), default="not_configured")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# =====================================================================================
# Disputes, escalations and ratings
# =====================================================================================
class DisputeStatus:
    OPEN = "open"                  # waiting for the other party's response
    UNDER_REVIEW = "under_review"  # administrator is reviewing
    DECIDED = "decided"            # reasoned decision recorded; appeal window running
    APPEALED = "appealed"
    CLOSED = "closed"
    ACTIVE = (OPEN, UNDER_REVIEW, DECIDED, APPEALED)


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[int] = _id()
    subject_type: Mapped[str] = mapped_column(String(20))  # project | contract
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("service_requests.id"), nullable=True, index=True)
    raised_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    raised_by_side: Mapped[str] = mapped_column(String(20))  # organization | engineer
    reason_code: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=DisputeStatus.OPEN, index=True)
    target_resolution_date: Mapped[date] = mapped_column(Date)
    decision_outcome: Mapped[str] = mapped_column(String(40), default="")
    decision_text: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    appeal_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    appeal_reason: Mapped[str] = mapped_column(Text, default="")
    appealed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    final_decision_text: Mapped[str] = mapped_column(Text, default="")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()

    raiser: Mapped[User] = relationship(foreign_keys=[raised_by])


class DisputeEntry(Base):
    """Statements, responses, admin notes, decisions. Never edited or deleted (audit history)."""

    __tablename__ = "dispute_entries"

    id: Mapped[int] = _id()
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author_side: Mapped[str] = mapped_column(String(20))  # organization | engineer | admin
    kind: Mapped[str] = mapped_column(String(20))         # statement | response | admin_note | decision | appeal
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()

    author: Mapped[User] = relationship()


class Escalation(Base):
    """Opened when a review window passes without a decision. Nothing is approved automatically."""

    __tablename__ = "escalations"

    id: Mapped[int] = _id()
    kind: Mapped[str] = mapped_column(String(30))  # deliverable_review | period_review
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("billing_periods.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open | resolved
    note: Mapped[str] = mapped_column(Text, default="")
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class Rating(Base):
    """Two-way ratings after a project or contract finishes."""

    __tablename__ = "ratings"

    id: Mapped[int] = _id()
    subject_key: Mapped[str] = mapped_column(String(60), unique=True)  # e.g. "project:12:organization"
    subject_type: Mapped[str] = mapped_column(String(20))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("service_contracts.id"), nullable=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewer_side: Mapped[str] = mapped_column(String(20))  # organization | engineer
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    engineer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


# =====================================================================================
# Simulated finance (NO real money). Every row is marked simulated.
# =====================================================================================
class FeeRule(Base):
    __tablename__ = "fee_rules"

    id: Mapped[int] = _id()
    model: Mapped[str] = mapped_column(String(5))          # A | B
    payer: Mapped[str] = mapped_column(String(20))         # organization | engineer | both
    fee_type: Mapped[str] = mapped_column(String(10))      # percent | fixed
    org_value: Mapped[int] = mapped_column(Integer, default=0)       # basis points (500 = 5%) or halalas
    engineer_value: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = _created()


class SimTransaction(Base):
    __tablename__ = "sim_transactions"

    id: Mapped[int] = _id()
    ref: Mapped[str] = mapped_column(String(30), unique=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)   # payment | payout | refund
    model: Mapped[str] = mapped_column(String(5))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"), nullable=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("service_contracts.id"), nullable=True, index=True)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("billing_periods.id"), nullable=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("sim_invoices.id"), nullable=True, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    engineer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    gross_cents: Mapped[int] = mapped_column(Integer)
    org_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    engineer_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)  # pending | completed | cancelled
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    fee_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = _created()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SimInvoice(Base):
    __tablename__ = "sim_invoices"

    id: Mapped[int] = _id()
    number: Mapped[str] = mapped_column(String(30), unique=True)
    model: Mapped[str] = mapped_column(String(5))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"), nullable=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("service_contracts.id"), nullable=True, index=True)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("billing_periods.id"), nullable=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    engineer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    description: Mapped[str] = mapped_column(String(300))
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    org_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    engineer_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    vat_percent: Mapped[float] = mapped_column(default=0.0)
    vat_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="issued", index=True)  # issued | paid | refunded | void
    fee_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    issued_at: Mapped[datetime] = _created()
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# =====================================================================================
# Platform configuration and audit
# =====================================================================================
class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)   # stored as {"v": <value>}
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = _created()


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = _id()
    day: Mapped[date] = mapped_column(Date, unique=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)  # Islamic dates must be confirmed yearly


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = _id()
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    actor: Mapped[User | None] = relationship()


# =====================================================================================
# Legacy EngConnect tables - kept read-only so existing records are never lost.
# The old Stripe/escrow flow is switched off in BUNYAH (see docs/LEGACY.md).
# =====================================================================================
class PaymentStatus:
    PENDING = "pending"
    HELD = "held"
    RELEASED = "released"
    REFUNDED = "refunded"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = _id()
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    freelancer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.PENDING, index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_ref: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = _created()
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship()


class WithdrawalStatus:
    REQUESTED = "requested"
    PAID = "paid"
    REJECTED = "rejected"


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id: Mapped[int] = _id()
    freelancer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    payout_method: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default=WithdrawalStatus.REQUESTED, index=True)
    created_at: Mapped[datetime] = _created()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    freelancer: Mapped[User] = relationship()


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = _id()
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    freelancer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()
