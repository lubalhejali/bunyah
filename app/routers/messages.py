"""Private chat between an organization (its members) and an engineer. The page checks for new messages
every few seconds. An engineer can start a chat only with an organization they sent a proposal or
application to; an organization can contact any engineer."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas as s
from app.database import get_db
from app.errors import bad_request, forbidden, not_found
from app.models import (
    Conversation,
    Message,
    Offer,
    Organization,
    OrgMember,
    Project,
    Role,
    ServiceApplication,
    ServiceRequest,
    User,
)
from app.security import current_user, org_context
from app.services import notify
from app.services.model_a import user_mini

router = APIRouter(prefix="/conversations", tags=["messages"])


def _my_org_id(db: Session, user: User) -> int | None:
    if user.role != Role.ORGANIZATION:
        return None
    return db.scalar(select(OrgMember.org_id).where(OrgMember.user_id == user.id, OrgMember.is_active.is_(True)))


def _mine_filter(db: Session, user: User):
    org_id = _my_org_id(db, user)
    if org_id:
        return Conversation.org_id == org_id
    return Conversation.freelancer_id == user.id


def _mine(db: Session, conv_id: int, user: User) -> Conversation:
    c = db.get(Conversation, conv_id)
    org_id = _my_org_id(db, user)
    if c is None or not (c.freelancer_id == user.id or (org_id and c.org_id == org_id)):
        raise not_found("Conversation", "المحادثة")
    return c


def _org_side(c: Conversation, user: User) -> bool:
    return user.id != c.freelancer_id


def unread_total(db: Session, user: User) -> int:
    org_id = _my_org_id(db, user)
    if org_id:
        cond = and_(Conversation.org_id == org_id, Message.id > Conversation.office_last_read_id,
                    Message.sender_id == Conversation.freelancer_id)
    else:
        cond = and_(Conversation.freelancer_id == user.id, Message.id > Conversation.freelancer_last_read_id,
                    Message.sender_id != user.id)
    return db.scalar(select(func.count(Message.id)).join(Conversation, Conversation.id == Message.conversation_id)
                     .where(cond)) or 0


def _conv_out(db: Session, c: Conversation, user: User) -> dict:
    org_side = _org_side(c, user)
    last_read = c.office_last_read_id if org_side else c.freelancer_last_read_id
    other_cond = (Message.sender_id == c.freelancer_id) if org_side else (Message.sender_id != c.freelancer_id)
    unread = db.scalar(select(func.count(Message.id)).where(Message.conversation_id == c.id, Message.id > last_read,
                                                            other_cond)) or 0
    last = db.scalar(select(Message.body).where(Message.conversation_id == c.id).order_by(Message.id.desc()).limit(1))
    org = c.org or (db.get(Organization, c.org_id) if c.org_id else None)
    other = ({"id": c.freelancer.id, "name": c.freelancer.name, "kind": "engineer"} if org_side else
             {"id": org.id if org else c.office_id, "name": org.name if org else c.office.name, "kind": "organization"})
    return {"id": c.id, "other": other, "last_message": (last or "")[:140], "last_message_at": c.last_message_at,
            "unread": unread}


@router.get("")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Conversation).where(_mine_filter(db, user))
                      .order_by(Conversation.last_message_at.desc()).limit(200)).all()
    return [_conv_out(db, c, user) for c in rows]


@router.post("")
def start_conversation(body: s.StartConversationIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ctx = org_context(db, user)
    if ctx:
        ctx.require("messages.send")
        eng = db.get(User, body.user_id) if body.user_id else None
        if eng is None or eng.role != Role.ENGINEER:
            raise not_found("Engineer", "المهندس")
        org_id, eng_id = ctx.org.id, eng.id
    elif user.role == Role.ENGINEER:
        org = db.get(Organization, body.org_id) if body.org_id else None
        if org is None:
            raise not_found("Organization", "الجهة")
        related = db.scalar(select(Offer.id).join(Project).where(Offer.freelancer_id == user.id,
                                                                 Project.org_id == org.id).limit(1)) or \
            db.scalar(select(ServiceApplication.id).join(ServiceRequest).where(
                ServiceApplication.engineer_id == user.id, ServiceRequest.org_id == org.id).limit(1))
        if not related:
            raise forbidden("You can message an organization after sending it a proposal or an application.",
                            "يمكنك مراسلة الجهة بعد إرسال عرض أو طلب تقديم إليها.")
        owner = db.scalar(select(OrgMember.user_id).where(OrgMember.org_id == org.id, OrgMember.org_role == "owner"))
        org_id, eng_id = org.id, user.id
    else:
        raise bad_request("Chats are between organizations and engineers.", "المحادثات بين الجهات والمهندسين فقط.")
    c = db.scalar(select(Conversation).where(Conversation.org_id == org_id, Conversation.freelancer_id == eng_id))
    if c is None:
        starter = user.id if ctx else owner
        c = Conversation(org_id=org_id, office_id=starter, freelancer_id=eng_id)
        db.add(c)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            c = db.scalar(select(Conversation).where(Conversation.org_id == org_id, Conversation.freelancer_id == eng_id))
    return _conv_out(db, c, user)


@router.get("/{conv_id}/messages")
def get_messages(conv_id: int, after_id: int = 0, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _mine(db, conv_id, user)
    stmt = select(Message).where(Message.conversation_id == c.id)
    if after_id:
        rows = db.scalars(stmt.where(Message.id > after_id).order_by(Message.id).limit(200)).all()
    else:
        rows = list(reversed(db.scalars(stmt.order_by(Message.id.desc()).limit(200)).all()))
    if rows:
        newest = rows[-1].id
        if _org_side(c, user) and newest > c.office_last_read_id:
            c.office_last_read_id = newest
            db.commit()
        elif not _org_side(c, user) and newest > c.freelancer_last_read_id:
            c.freelancer_last_read_id = newest
            db.commit()
    names = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_({m.sender_id for m in rows})))} if rows else {}
    return [{"id": m.id, "sender_id": m.sender_id, "sender_name": names.get(m.sender_id, ""),
             "mine": m.sender_id == user.id, "body": m.body, "created_at": m.created_at} for m in rows]


@router.post("/{conv_id}/messages", status_code=201)
def send_message(conv_id: int, body: s.TextIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _mine(db, conv_id, user)
    ctx = org_context(db, user)
    if ctx:
        ctx.require("messages.send")
    m = Message(conversation_id=c.id, sender_id=user.id, body=body.body)
    db.add(m)
    c.last_message_at = datetime.now(UTC)
    db.flush()
    if _org_side(c, user):
        c.office_last_read_id = m.id
        notify.notify(db, [c.freelancer_id], "new_message", c.org.name if c.org else user.name, f"/messages/{c.id}")
    else:
        c.freelancer_last_read_id = m.id
        notify.notify(db, notify.org_user_ids(db, c.org_id, ("owner", "project_manager", "technical_reviewer")),
                      "new_message", user.name, f"/messages/{c.id}")
    db.commit()
    return {"id": m.id, "sender_id": m.sender_id, "sender_name": user.name, "mine": True, "body": m.body,
            "created_at": m.created_at}


_ = (or_, user_mini)
