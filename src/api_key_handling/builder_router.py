from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api_key_handling.utils import (
    API_KEY_HEADER,
    compute_storage_uid,
    generate_api_key,
    hash_api_key,
)
from src.ledger_db_access import get_payment_db
from src.ledger_router import get_current_user_id
from src.ledger_tables import UserApiKey
from src.login_logic import get_user


router = APIRouter(prefix="/builder", tags=["api-key"])


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _require_user(request: Request) -> dict:
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def _serialize_record(record: UserApiKey) -> dict:
    return {
        "id": record.id,
        "key_prefix": record.key_prefix,
        "label": record.label or "",
        "created_at": _iso(record.created_at),
        "last_used_at": _iso(record.last_used_at),
    }


class CreateApiKeyRequest(BaseModel):
    label: Optional[str] = Field(default=None, description="Optional description shown next to the key")


@router.get("/api-key")
def list_api_keys(
    request: Request,
    db: Session = Depends(get_payment_db),
    user_id: int = Depends(get_current_user_id),
):
    _require_user(request)

    records = (
        db.execute(
            select(UserApiKey)
            .where(UserApiKey.user_id == user_id)
            .order_by(UserApiKey.created_at.desc(), UserApiKey.id.desc())
        )
        .scalars()
        .all()
    )

    return {
        "header": API_KEY_HEADER,
        "endpoint_template": "/external/apis/{api_id}",
        "keys": [_serialize_record(rec) for rec in records],
    }


@router.post("/api-key")
def create_api_key(
    request: Request,
    payload: CreateApiKeyRequest = Body(default=CreateApiKeyRequest()),
    db: Session = Depends(get_payment_db),
    user_id: int = Depends(get_current_user_id),
):
    user = _require_user(request)
    storage_uid = compute_storage_uid(user)

    label = (payload.label or "").strip()
    if len(label) > 512:
        label = label[:512]

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

        record = UserApiKey(
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=prefix,
            label=label,
            storage_uid=storage_uid,
            created_at=now,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {
            "api_key": raw_key,
            "header": API_KEY_HEADER,
            "key": _serialize_record(record),
        }

    raise HTTPException(status_code=500, detail="Failed to generate a unique API key")


@router.delete("/api-key/{key_id}")
def delete_api_key(
    request: Request,
    key_id: int,
    db: Session = Depends(get_payment_db),
    user_id: int = Depends(get_current_user_id),
):
    _require_user(request)
    record = db.get(UserApiKey, key_id)
    if not record:
        return {"ok": True}
    if record.user_id != user_id:
        raise HTTPException(status_code=404, detail="API key not found")

    db.delete(record)
    db.commit()
    return {"ok": True}
