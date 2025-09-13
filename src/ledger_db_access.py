from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Generator

from fastapi import Request
from google.cloud.sql.connector import Connector, IPTypes
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session



def _connect_factory(connector: Connector):
    def _connect():
        instance_connection_name = os.getenv("INSTANCE_CONNECTION_NAME")
        if not instance_connection_name:
            raise RuntimeError("INSTANCE_CONNECTION_NAME is required (project:region:instance)")

        db_name = os.getenv("DB_NAME", "postgres")
        db_user = os.getenv("DB_USER", "")
        db_pass = os.getenv("DB_PASS", "")
        iam_auth = os.getenv("DB_IAM_AUTH", "false").strip().lower() in ("1", "true", "yes", "on")
        ip_type = IPTypes.PRIVATE if os.getenv("DB_PRIVATE_IP", "").strip().lower() in ("1", "true", "yes", "on") else IPTypes.PUBLIC

        return connector.connect(
            instance_connection_name,
            driver="pg8000",
            user=db_user,
            password=None if iam_auth else db_pass,
            db=db_name,
            ip_type=ip_type,
            enable_iam_auth=iam_auth,
        )
    return _connect


def init_payment_db_state() -> SimpleNamespace:
    connector = Connector()  # uses ADC / GOOGLE_APPLICATION_CREDENTIALS
    engine: Engine = create_engine(
        "postgresql+pg8000://",           # URL is ignored; creator provides real conn
        creator=_connect_factory(connector),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    return SimpleNamespace(connector=connector, engine=engine, SessionLocal=SessionLocal)


def shutdown_payment_db_state(state: SimpleNamespace) -> None:
    try:
        state.engine.dispose()
    except Exception:
        pass
    try:
        state.connector.close()
    except Exception:
        pass


def get_payment_db(request: Request) -> Generator[Session, None, None]:
    """
    FastAPI dependency. Pull Session factory from app.state (no globals).
    """
    SessionLocal = request.app.state.db.SessionLocal
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass
