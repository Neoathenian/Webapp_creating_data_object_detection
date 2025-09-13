import os
os.environ["SQLALCHEMY_WARN_20"] = "1"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.ledger_tables import Base
from src.ledger_router import ledger_router

engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base.metadata.create_all(engine)

app = FastAPI()
app.include_router(ledger_router)

from src import ledger_db_get_current_user_id as deps_mod
def _get_payment_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
deps_mod.get_payment_db = _get_payment_db
deps_mod.get_current_user_id = lambda *_, **__: 1

client = TestClient(app)

def setup_user(db):
    db.execute(text("INSERT INTO app_user(id, oauth_sub) VALUES (1, 'sub1')"))
    db.execute(text("INSERT INTO user_balance(user_id, balance) VALUES (1, 100)"))
    db.commit()

def test_spend_idempotency():
    with SessionLocal() as db: setup_user(db)
    r1 = client.post("/credits/spend", json={"cost": 60, "job_id": "job-xyz"})
    assert r1.status_code == 200
    r2 = client.post("/credits/spend", json={"cost": 60, "job_id": "job-xyz"})
    assert r2.status_code == 200
    assert r2.json().get("idempotent") is True
    with SessionLocal() as db:
        bal = db.execute(text("SELECT balance FROM user_balance WHERE user_id=1")).scalar()
        assert bal == 40
        n = db.execute(text(
            "SELECT COUNT(*) FROM credit_ledger WHERE source_type='job' AND source_id='job-xyz'"
        )).scalar()
        assert n == 1

def test_no_negative_balance():
    with SessionLocal() as db:
        db.execute(text("DELETE FROM credit_ledger"))
        db.execute(text("UPDATE user_balance SET balance=50 WHERE user_id=1"))
        db.commit()
    r = client.post("/credits/spend", json={"cost": 60, "job_id": "job-2"})
    assert r.status_code == 402
