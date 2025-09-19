from __future__ import annotations

from datetime import datetime
from typing import Callable, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api_key_handling.utils import API_KEY_HEADER, hash_api_key
from src.gcs_storage import find_doc_by_id, find_doc_by_name
from src.ledger_db_access import get_payment_db
from src.ledger_tables import UserApiKey


default_tags = ["external"]
router = APIRouter(prefix="/external", tags=default_tags)

Resolver = Callable[[str], tuple[dict, str] | None]


def _resolve_api_key(
    x_api_key: str = Header(default=None, alias=API_KEY_HEADER, convert_underscores=False),
    db: Session = Depends(get_payment_db),
) -> Tuple[UserApiKey, Session]:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    key_hash = hash_api_key(x_api_key)
    record = db.execute(
        select(UserApiKey).where(UserApiKey.key_hash == key_hash)
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return record, db


def _load_doc(record: UserApiKey, db: Session, loader: Resolver):
    found = loader(record.storage_uid)
    if not found:
        raise HTTPException(status_code=404, detail="API not found")

    doc, _ = found

    # Track last usage; ignore failures
    try:
        record.last_used_at = datetime.utcnow()
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return doc


@router.get("/apis/{api_id}")
def fetch_api_definition(
    api_id: str,
    binding: Tuple[UserApiKey, Session] = Depends(_resolve_api_key),
):
    record, db = binding

    def _by_id(uid: str):
        return find_doc_by_id(uid, api_id)

    return _load_doc(record, db, _by_id)


@router.get("/apis/by-name/{api_name}")
def fetch_api_by_name(
    api_name: str,
    binding: Tuple[UserApiKey, Session] = Depends(_resolve_api_key),
):
    record, db = binding

    def _by_name(uid: str):
        return find_doc_by_name(uid, api_name)

    return _load_doc(record, db, _by_name)
