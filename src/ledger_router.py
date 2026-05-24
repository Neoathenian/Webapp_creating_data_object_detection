from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from fastapi import Depends, HTTPException, Request

from src.ledger_db_access import get_payment_db
from src.ledger_tables import UserBalance, CreditLedger
from src.ledger_tables import AppUser
from src.secrets import get_secret
from src.login_logic import get_user


DEFAULT_SIGNUP_CREDITS = int(get_secret("SIGNUP_CREDITS", default="0") or 0)


def ensure_user_signup_bonus(sub: str, db: Session) -> int:
    """Ensure a user exists and has received the signup bonus; return their PK."""
    needs_commit = False

    u = db.execute(select(AppUser).where(AppUser.oauth_sub == sub)).scalar_one_or_none()
    if not u:
        u = AppUser(oauth_sub=sub)
        db.add(u)
        db.flush()
        needs_commit = True

    if DEFAULT_SIGNUP_CREDITS > 0:
        bonus_source_id = f"user:{u.id}"
        has_balance = db.execute(
            select(UserBalance.user_id).where(UserBalance.user_id == u.id)
        ).scalar_one_or_none()
        has_bonus_entry = db.execute(
            select(CreditLedger.id)
            .where(CreditLedger.source_type == "signup_bonus")
            .where(CreditLedger.source_id == bonus_source_id)
        ).scalar_one_or_none()

        if not has_balance:
            db.add(UserBalance(user_id=u.id, balance=DEFAULT_SIGNUP_CREDITS))
            needs_commit = True
        if not has_bonus_entry:
            db.add(
                CreditLedger(
                    user_id=u.id,
                    delta=DEFAULT_SIGNUP_CREDITS,
                    reason="signup_bonus",
                    source_type="signup_bonus",
                    source_id=bonus_source_id,
                )
            )
            needs_commit = True

    if needs_commit:
        db.commit()

    return int(u.id)


def get_current_user_id(request: Request, db: Session = Depends(get_payment_db)) -> int:
    """This is to get the current user ID from the request (not the oauth, but db pk)."""
    user = get_user(request) or {}
    sub = user.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="not_authenticated")

    return ensure_user_signup_bonus(sub, db)


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
