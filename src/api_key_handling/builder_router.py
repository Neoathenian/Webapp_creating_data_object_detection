from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api_key_handling.utils import (
    API_KEY_HEADER,
    compute_storage_uid,
    generate_api_key,
    hash_api_key,
)
from src.ledger_db_access import get_payment_db
from src.ledger_tables import UserApiKey
from src.ledger_router import get_current_user_id
from src.login_logic import get_user


router = APIRouter(prefix="/builder", tags=["api-key"])


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _require_user(request: Request) -> dict:
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


@router.get("/api-key")
def api_key_status(
    request: Request,
    db: Session = Depends(get_payment_db),
    user_id: int = Depends(get_current_user_id),
):
    _require_user(request)
    record = db.get(UserApiKey, user_id)
    if not record:
        return {
            "has_key": False,
            "key_prefix": None,
            "created_at": None,
            "last_used_at": None,
            "header": API_KEY_HEADER,
            "endpoint_template": "/external/apis/{api_id}",
        }

    return {
        "has_key": True,
        "key_prefix": record.key_prefix,
        "created_at": _iso(record.created_at),
        "last_used_at": _iso(record.last_used_at),
        "header": API_KEY_HEADER,
        "endpoint_template": "/external/apis/{api_id}",
    }


@router.post("/api-key")
def rotate_api_key(
    request: Request,
    db: Session = Depends(get_payment_db),
    user_id: int = Depends(get_current_user_id),
):
    user = _require_user(request)
    storage_uid = compute_storage_uid(user)

    record = db.get(UserApiKey, user_id)

    for _ in range(8):
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        conflict = db.execute(
            select(UserApiKey).where(UserApiKey.key_hash == key_hash)
        ).scalar_one_or_none()
        if conflict and conflict.user_id != user_id:
            continue

        prefix = raw_key[:8]
        now = datetime.utcnow()

        if record is None:
            record = UserApiKey(
                user_id=user_id,
                key_hash=key_hash,
                key_prefix=prefix,
                storage_uid=storage_uid,
                created_at=now,
            )
            db.add(record)
        else:
            record.key_hash = key_hash
            record.key_prefix = prefix
            record.storage_uid = storage_uid
            record.created_at = now
            record.last_used_at = None

        db.commit()
        return {
            "api_key": raw_key,
            "key_prefix": record.key_prefix,
            "created_at": _iso(record.created_at),
            "header": API_KEY_HEADER,
        }

    raise HTTPException(status_code=500, detail="Failed to generate a unique API key")


@router.delete("/api-key")
def delete_api_key(
    request: Request,
    db: Session = Depends(get_payment_db),
    user_id: int = Depends(get_current_user_id),
):
    _require_user(request)
    record = db.get(UserApiKey, user_id)
    if not record:
        return {"ok": True}

    db.delete(record)
    db.commit()
    return {"ok": True}
