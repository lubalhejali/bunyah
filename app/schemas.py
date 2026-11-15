"""Shapes of the data the API accepts. Anything that doesn't match is rejected with a clear message.
Unknown fields are refused (extra="forbid"), so nobody can set fields such as status or verification by hand."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class In(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _check_url(v: str) -> str:
    if v and not (v.startswith("https://") or v.startswith("http://")):
        raise ValueError("must start with https:// or http://")
    return v


Money = Field(ge=100, le=1_000_000_000)          # 1 SAR .. 10,000,000 SAR, in halalas
WorkMode = Literal["remote", "onsite", "hybrid"]


# ---------- auth ----------
class RegisterIn(In):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(min_length=2, max_length=120)
    role: Literal["organization", "engineer"]
    org_name: str = Field(default="", max_length=160)
    locale: Literal["ar", "en"] = "ar"
    accept_terms: bool

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Please accept the prototype terms to continue")
        return v


class LoginIn(In):
    # Plain text (not EmailStr): the fictional demo accounts use the reserved ".test" domain.
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class DemoLoginIn(In):
    key: str = Field(min_length=2, max_length=40)


class PasswordChangeIn(In):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class AcceptInviteIn(In):
    token: str = Field(min_length=20, max_length=100)
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)


class AccountUpdate(In):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    locale: Literal["ar", "en"] | None = None


# ---------- organization ----------
class OrgUpdate(In):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    name_ar: str | None = Field(default=None, max_length=160)
    org_type: Literal["engineering_consultancy", "engineering_firm", "contractor", "developer", "government",
                      "other"] | None = None
    cr_number: str | None = Field(default=None, max_length=40)
    license_info: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=300)
    contact_email: EmailStr | Literal[""] | None = None
    contact_phone: str | None = Field(default=None, max_length=40)
    representative_name: str | None = Field(default=None, max_length=120)
    representative_title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    website: str | None = Field(default=None, max_length=255)

    @field_validator("website")
    @classmethod
    def _url(cls, v):
        return _check_url(v) if v else v


OrgRoleLit = Literal["owner", "project_manager", "technical_reviewer", "finance", "viewer"]


class InviteIn(In):
    email: EmailStr
    name: str = Field(default="", max_length=120)
    org_role: OrgRoleLit


class MemberUpdate(In):
    org_role: OrgRoleLit | None = None
    is_active: bool | None = None


class VerificationSubmitIn(In):
    note: str = Field(default="", max_length=2000)


# ---------- engineer ----------
class EngineerUpdate(In):
    title: str | None = Field(default=None, max_length=160)
    discipline_id: int | None = None
    specializations: str | None = Field(default=None, max_length=500)
    years_experience: int | None = Field(default=None, ge=0, le=60)
    education: str | None = Field(default=None, max_length=3000)
    qualifications: str | None = Field(default=None, max_length=3000)
    certifications: str | None = Field(default=None, max_length=3000)
    registration_body: str | None = Field(default=None, max_length=160)
    registration_number: str | None = Field(default=None, max_length=80)
    software_skills: str | None = Field(default=None, max_length=500)
    languages: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=80)
    availability: Literal["available", "partial", "unavailable"] | None = None
    work_preference: WorkMode | None = None
    rate_min_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    rate_max_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    bio: str | None = Field(default=None, max_length=5000)


# ---------- Model A ----------
class ProjectIn(In):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20, max_length=10000)
    discipline_id: int | None = None
    scope: str = Field(default="", max_length=10000)
    deliverables_text: str = Field(default="", max_length=5000)
    requirements: str = Field(default="", max_length=10000)
    qualifications: str = Field(default="", max_length=5000)
    work_mode: WorkMode
    location: str = Field(default="", max_length=160)
    budget_min_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    max_budget_cents: int = Money
    duration_days: int | None = Field(default=None, ge=1, le=1000)
    proposal_deadline: date | None = None
    deadline: date


class ProjectUpdate(In):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    description: str | None = Field(default=None, min_length=20, max_length=10000)
    discipline_id: int | None = None
    scope: str | None = Field(default=None, max_length=10000)
    deliverables_text: str | None = Field(default=None, max_length=5000)
    requirements: str | None = Field(default=None, max_length=10000)
    qualifications: str | None = Field(default=None, max_length=5000)
    work_mode: WorkMode | None = None
    location: str | None = Field(default=None, max_length=160)
    budget_min_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    max_budget_cents: int | None = Field(default=None, ge=100, le=1_000_000_000)
    duration_days: int | None = Field(default=None, ge=1, le=1000)
    proposal_deadline: date | None = None
    deadline: date | None = None


class ProjectStep(In):
    to: Literal["applications_closed", "under_evaluation", "published", "cancelled"]


class ProposalIn(In):
    price_cents: int = Money
    delivery_date: date
    duration_days: int | None = Field(default=None, ge=1, le=1000)
    message: str = Field(min_length=20, max_length=5000)
    technical_approach: str = Field(min_length=20, max_length=10000)


class ProposalDecision(In):
    decision: Literal["shortlist", "reject", "clarify"]
    note: str = Field(default="", max_length=3000)


class TextIn(In):
    body: str = Field(min_length=1, max_length=5000)


class NoteIn(In):
    note: str = Field(default="", max_length=5000)


class MilestoneIn(In):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=3000)
    amount_cents: int = Field(ge=0, le=1_000_000_000)   # no minimum milestone value
    due_date: date | None = None


class TaskIn(In):
    title: str = Field(min_length=2, max_length=200)
    status: Literal["todo", "in_progress", "done"] = "todo"
    milestone_id: int | None = None
    assignee_id: int | None = None
    due_date: date | None = None


class DeliverableIn(In):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=3000)
    milestone_id: int | None = None


class VersionReview(In):
    decision: Literal["approved", "revision_requested"]
    comment: str = Field(default="", max_length=5000)


class CommentIn(In):
    body: str = Field(min_length=1, max_length=5000)
    kind: Literal["comment", "technical_review"] = "comment"


# ---------- Model B ----------
class RequestIn(In):
    title: str = Field(min_length=5, max_length=200)
    discipline_id: int | None = None
    specialization: str = Field(default="", max_length=200)
    qualifications: str = Field(default="", max_length=5000)
    min_experience_years: int = Field(default=0, ge=0, le=50)
    duration_working_days: int = Field(ge=1, le=260)
    hours_per_day: int = Field(default=8, ge=1, le=12)
    daily_rate_cents: int = Money
    work_mode: WorkMode
    location: str = Field(default="", max_length=160)
    start_date: date
    responsibilities: str = Field(min_length=20, max_length=10000)
    outputs: str = Field(default="", max_length=5000)


class RequestUpdate(In):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    discipline_id: int | None = None
    specialization: str | None = Field(default=None, max_length=200)
    qualifications: str | None = Field(default=None, max_length=5000)
    min_experience_years: int | None = Field(default=None, ge=0, le=50)
    duration_working_days: int | None = Field(default=None, ge=1, le=260)
    hours_per_day: int | None = Field(default=None, ge=1, le=12)
    daily_rate_cents: int | None = Field(default=None, ge=100, le=1_000_000_000)
    work_mode: WorkMode | None = None
    location: str | None = Field(default=None, max_length=160)
    start_date: date | None = None
    responsibilities: str | None = Field(default=None, min_length=20, max_length=10000)
    outputs: str | None = Field(default=None, max_length=5000)


class RequestStep(In):
    to: Literal["applications_open", "under_evaluation", "cancelled"]


class ApplicationIn(In):
    cover_letter: str = Field(min_length=20, max_length=5000)
    proposed_daily_rate_cents: int = Money
    available_from: date


class ApplicationDecision(In):
    decision: Literal["shortlist", "reject", "select"]
    note: str = Field(default="", max_length=3000)


class ContractUpdate(In):
    start_date: date | None = None
    working_days: int | None = Field(default=None, ge=1, le=260)
    daily_rate_cents: int | None = Field(default=None, ge=100, le=1_000_000_000)
    hours_per_day: int | None = Field(default=None, ge=1, le=12)
    terms: str | None = Field(default=None, min_length=20, max_length=20000)


class SignIn(In):
    full_name: str = Field(min_length=2, max_length=120)
    confirm: bool

    @field_validator("confirm")
    @classmethod
    def _c(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Please confirm that you agree to the contract")
        return v


class TimeEntryIn(In):
    work_date: date
    day_fraction: float = Field(default=1.0)
    hours: float = Field(default=8.0, ge=0.5, le=16)
    description: str = Field(min_length=5, max_length=2000)


class PeriodReview(In):
    decision: Literal["approve", "revision"]
    comment: str = Field(default="", max_length=3000)


class FinishIn(In):
    outcome: Literal["completed", "terminated"]
    reason: str = Field(default="", max_length=3000)


# ---------- shared ----------
class StartConversationIn(In):
    user_id: int | None = None      # engineer to contact (organization side)
    org_id: int | None = None       # organization to contact (engineer side)


class DisputeIn(In):
    subject_type: Literal["project", "contract"]
    subject_id: int
    reason_code: Literal["quality", "delay", "scope", "payment", "conduct", "time_records", "other"]
    description: str = Field(min_length=20, max_length=5000)


class DisputeDecisionIn(In):
    outcome: Literal["release_to_engineer", "refund_to_organization", "partial_settlement", "resume_work",
                     "no_financial_action"]
    reasoning: str = Field(min_length=20, max_length=10000)
    resume_status: str = Field(min_length=3, max_length=40)


class AppealIn(In):
    reason: str = Field(min_length=20, max_length=5000)


class RatingIn(In):
    rating: int = Field(ge=1, le=5)
    text: str = Field(default="", max_length=3000)


# ---------- admin ----------
class VerificationDecision(In):
    decision: Literal["approve", "reject", "needs_info"]
    note: str = Field(default="", max_length=3000)


class RequestReviewIn(In):
    decision: Literal["start", "publish", "return"]
    note: str = Field(default="", max_length=3000)


class UserAdminUpdate(In):
    is_active: bool


class FeeRuleIn(In):
    model: Literal["A", "B"]
    payer: Literal["organization", "engineer", "both"]
    fee_type: Literal["percent", "fixed"]
    org_value: int = Field(default=0, ge=0, le=100_000_000)       # basis points or halalas
    engineer_value: int = Field(default=0, ge=0, le=100_000_000)
    note: str = Field(default="", max_length=300)


class SettingIn(In):
    value: bool | int | float


class DisciplineIn(In):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    name_en: str = Field(min_length=2, max_length=120)
    name_ar: str = Field(min_length=2, max_length=120)
    is_active: bool = True
    sort_order: int = Field(default=100, ge=0, le=1000)


class DisciplineUpdate(In):
    name_en: str | None = Field(default=None, min_length=2, max_length=120)
    name_ar: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)


class HolidayIn(In):
    day: date
    name_en: str = Field(min_length=2, max_length=120)
    name_ar: str = Field(min_length=2, max_length=120)
    is_confirmed: bool = False


class AnnouncementIn(In):
    audience: Literal["all", "organization", "engineer"]
    text: str = Field(min_length=5, max_length=280)


class ChecksIn(In):
    as_of: date | None = None


class EscalationResolveIn(In):
    note: str = Field(min_length=5, max_length=3000)


class RefundIn(In):
    reason: str = Field(min_length=10, max_length=500)


class PortfolioIn(In):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=3000)
    link: str = Field(default="", max_length=500)

    @field_validator("link")
    @classmethod
    def _url(cls, v):
        return _check_url(v) if v else v


class Page(BaseModel):
    data: list
    total: int
    page: int
    per_page: int
