from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from fastapi import Depends, HTTPException, Request

from src.ledger_db_access import get_payment_db
from src.ledger_tables import UserBalance, CreditLedger
from src.ledger_tables import AppUser




def get_current_user_id(request: Request, db: Session = Depends(get_payment_db)) -> int:
    """This is to get the current user ID from the request (not the oauth, but db pk)."""
    sess = getattr(request, "session", {}) or {}
    user = sess.get("user") or {}
    sub = user.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="not_authenticated")

    u = db.execute(select(AppUser).where(AppUser.oauth_sub == sub)).scalar_one_or_none()
    if u:
        return int(u.id)

    # Create user if not exists
    u = AppUser(oauth_sub=sub)
    db.add(u)
    db.flush()
    return int(u.id)


ledger_router = APIRouter()


# ===================== PROD ENDPOINTS =====================

@ledger_router.get("/user/balance")
def get_user_balance(
    db: Session = Depends(get_payment_db),
    user_id: int = Depends(get_current_user_id),
):
    bal = db.execute(
        select(UserBalance.balance).where(UserBalance.user_id == user_id)
    ).scalar_one_or_none()
    return {"balance": int(bal or 0)}


@ledger_router.get("/user/ledger")
def get_user_ledger(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_payment_db),
    user_id: int = Depends(get_current_user_id),
):
    rows = db.execute(
        select(
            CreditLedger.id,
            CreditLedger.delta,
            CreditLedger.reason,
            CreditLedger.source_type,
            CreditLedger.source_id,
            CreditLedger.created_at,
        )
        .where(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.created_at.desc(), CreditLedger.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        dict(
            id=r.id,
            delta=int(r.delta),
            reason=r.reason,
            source_type=r.source_type,
            source_id=r.source_id,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]




# ===================== SPEND (UNCHANGED) =====================

@ledger_router.post("/credits/spend")
def spend_credits(
    cost: int = Body(embed=True, default=None),
    job_id: str = Body(embed=True, default=None),
    db: Session = Depends(get_payment_db),
    user_id: int = Depends(get_current_user_id),
):
    if cost is None or cost <= 0:
        raise HTTPException(status_code=400, detail="cost must be > 0")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id required")

    db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    updated = db.execute(
        update(UserBalance)
        .where(UserBalance.user_id == user_id)
        .where(UserBalance.balance >= cost)
        .values(balance=UserBalance.balance - cost)
        .execution_options(synchronize_session=False)
    ).rowcount

    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=402, detail="insufficient_credits")

    db.execute(
        pg_insert(CreditLedger)
        .values(
            user_id=user_id,
            delta=-cost,
            reason="spend",
            source_type="job",
            source_id=job_id,
        )
        .on_conflict_do_nothing(
            index_elements=[CreditLedger.source_type, CreditLedger.source_id]
        )
    )
    db.commit()

    bal = db.execute(
        select(UserBalance.balance).where(UserBalance.user_id == user_id)
    ).scalar_one()
    return {"balance": int(bal)}

