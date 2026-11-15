"""Checking uploads, storing them, deciding who may download them, and sending them back safely."""
import hashlib
import re
import unicodedata
from urllib.parse import quote

from fastapi import Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError, bad_request
from app.models import (
    Dispute,
    Offer,
    OrgMember,
    Project,
    ServiceApplication,
    ServiceRequest,
    StoredFile,
    User,
    VerificationRequest,
)
from app.services import storage

IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}

# Engineering and office formats accepted on BUNYAH. Anything else is refused.
ALLOWED_EXTENSIONS = set(IMAGE_TYPES) | {
    "pdf", "dwg", "dxf", "rvt", "rfa", "docx", "xlsx", "zip",
    # also common in engineering work:
    "ifc", "nwd", "nwc", "pptx", "csv", "txt",
}

# File signatures ("magic numbers"): the first bytes must match the extension, so a renamed program is refused.
_SIGNATURES = {
    "pdf": [b"%PDF"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"], "jpeg": [b"\xff\xd8\xff"],
    "zip": [b"PK\x03\x04", b"PK\x05\x06"], "docx": [b"PK\x03\x04"], "xlsx": [b"PK\x03\x04"], "pptx": [b"PK\x03\x04"],
    "dwg": [b"AC10", b"AC1."], "rvt": [b"\xd0\xcf\x11\xe0"], "rfa": [b"\xd0\xcf\x11\xe0"],
}


def _safe_name(name: str | None) -> str:
    name = unicodedata.normalize("NFKC", name or "file")
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f\"<>|:*?]", "", name).strip(" .")
    return (name or "file")[:200]


def _signature_ok(ext: str, data: bytes) -> bool:
    sigs = _SIGNATURES.get(ext)
    if not sigs:
        return True  # text-like formats (dxf, csv, txt, ifc) have no fixed signature
    if ext == "dwg":
        return data[:4] == b"AC10" or (data[:3] == b"AC1" and data[3:6].isdigit())
    return any(data.startswith(s) for s in sigs)


def read_upload(upload: UploadFile, images_only: bool = False) -> tuple[str, str, bytes]:
    """Returns (filename, content_type, bytes) or raises a friendly error."""
    filename = _safe_name(upload.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = set(IMAGE_TYPES) if images_only else ALLOWED_EXTENSIONS
    if ext not in allowed:
        kinds = "PNG or JPG" if images_only else "PDF, DWG, DXF, RVT, RFA, DOCX, XLSX, JPG, PNG or ZIP"
        raise bad_request(f"Please upload a {kinds} file. '.{ext or '?'}' files aren't accepted.",
                          f"يرجى رفع ملف بصيغة {kinds}. الصيغة '.{ext or '?'}' غير مقبولة.", "FILE_TYPE")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        mb = get_settings().max_upload_mb
        raise ApiError(413, "FILE_TOO_LARGE", f"Files can be at most {mb} MB.", f"الحد الأقصى لحجم الملف {mb} ميجابايت.")
    if not data:
        raise bad_request("That file is empty.", "الملف فارغ.", "FILE_EMPTY")
    if not _signature_ok(ext, data):
        raise bad_request(f"That file doesn't look like a real .{ext} file.",
                          f"محتوى الملف لا يطابق صيغة .{ext}.", "FILE_TYPE")
    if ext in IMAGE_TYPES:
        return filename, IMAGE_TYPES[ext], data
    return filename, "application/octet-stream", data  # we decide the type; never trust the browser


def store(db: Session, upload: UploadFile, owner: User, *, kind: str, context_type: str, context_id: int | None,
          project_id: int | None = None, note: str = "", images_only: bool = False) -> StoredFile:
    name, ctype, data = read_upload(upload, images_only=images_only)
    f = StoredFile(owner_id=owner.id, project_id=project_id, context_type=context_type, context_id=context_id,
                   kind=kind, filename=name, content_type=ctype, size=len(data),
                   sha256=hashlib.sha256(data).hexdigest(), note=note.strip()[:500])
    storage.save(f, data)
    db.add(f)
    db.flush()
    return f


def _is_org_member(db: Session, user: User, org_id: int | None) -> bool:
    if org_id is None:
        return False
    return db.scalar(select(OrgMember.id).where(OrgMember.user_id == user.id, OrgMember.org_id == org_id,
                                                OrgMember.is_active.is_(True))) is not None


def can_download(db: Session, user: User, f: StoredFile) -> bool:
    """Private by default. Verification documents and dispute evidence are never public."""
    from app.security import is_admin

    if is_admin(user) or f.owner_id == user.id:
        return True
    ct = f.context_type
    if ct in ("portfolio", "logo"):
        return True  # shown on profiles to signed-in users
    if ct in ("project", "deliverable"):
        p = db.get(Project, f.project_id) if f.project_id else None
        if p is None:
            return False
        if _is_org_member(db, user, p.org_id) or p.freelancer_id == user.id:
            return True
        return ct == "project" and f.kind == "brief" and p.status == "published"
    if ct == "proposal":
        o = db.get(Offer, f.context_id) if f.context_id else None
        return bool(o and (o.freelancer_id == user.id or _is_org_member(db, user, o.project.org_id)))
    if ct == "verification":
        v = db.get(VerificationRequest, f.context_id) if f.context_id else None
        if v is None:
            return False
        return (v.subject_type == "engineer" and v.subject_id == user.id) or \
               (v.subject_type == "organization" and _is_org_member(db, user, v.subject_id))
    if ct == "dispute":
        d = db.get(Dispute, f.context_id) if f.context_id else None
        if d is None:
            return False
        from app.services.disputes import is_party
        return is_party(db, user, d)
    if ct == "cv":
        # Organizations may read a CV only when that engineer applied or sent a proposal to them.
        eng_id = f.owner_id
        org_ids = [m for m in db.scalars(select(OrgMember.org_id).where(OrgMember.user_id == user.id)).all()]
        if not org_ids:
            return False
        proposed = db.scalar(select(Offer.id).join(Project, Project.id == Offer.project_id)
                             .where(Offer.freelancer_id == eng_id, Project.org_id.in_(org_ids)).limit(1))
        applied = db.scalar(select(ServiceApplication.id)
                            .join(ServiceRequest, ServiceRequest.id == ServiceApplication.request_id)
                            .where(ServiceApplication.engineer_id == eng_id, ServiceRequest.org_id.in_(org_ids))
                            .limit(1))
        return bool(proposed or applied)
    return False


def file_response(f: StoredFile, inline: bool) -> Response:
    is_image = f.content_type in IMAGE_TYPES.values()
    disposition = "inline" if (inline and is_image) else "attachment"
    ascii_name = f.filename.encode("ascii", "ignore").decode() or "file"
    return Response(
        content=storage.load(f),
        media_type=f.content_type if is_image else "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(f.filename)}',
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


def file_out(f: StoredFile) -> dict:
    return {"id": f.id, "filename": f.filename, "size": f.size, "kind": f.kind, "content_type": f.content_type,
            "note": f.note, "created_at": f.created_at, "owner_id": f.owner_id, "sha256": f.sha256[:12],
            "is_image": f.content_type in IMAGE_TYPES.values()}
