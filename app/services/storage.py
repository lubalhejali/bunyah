"""Where file contents are kept. The rest of the app only calls save() and load(), so a cloud object store
(for example Amazon S3 or Cloudflare R2) can be added later as one more backend without changing anything else.

- database: bytes stored in the database row (default). Survives Render restarts and is backed up with the DB.
- local:    bytes stored in a folder (LOCAL_STORAGE_DIR). Fine on your computer; NOT persistent on Render
            unless a paid persistent disk is attached.
"""
import uuid
from pathlib import Path

from app.config import get_settings
from app.models import StoredFile


def save(f: StoredFile, data: bytes) -> None:
    backend = get_settings().storage_backend
    f.storage_backend = backend
    if backend == "local":
        root = Path(get_settings().local_storage_dir)
        root.mkdir(parents=True, exist_ok=True)
        key = uuid.uuid4().hex                # random name: never derived from the user's filename
        (root / key).write_bytes(data)
        f.storage_key, f.data = key, None
    else:
        f.storage_key, f.data = "", data


def load(f: StoredFile) -> bytes:
    if f.storage_backend == "local":
        key = f.storage_key
        if not key or not key.isalnum():
            raise FileNotFoundError(key)
        return (Path(get_settings().local_storage_dir) / key).read_bytes()
    return f.data or b""
