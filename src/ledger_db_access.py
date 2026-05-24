from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Generator, Optional

from fastapi import HTTPException, Request
from google.cloud.sql.connector import Connector, IPTypes
from sqlalchemy import create_engine
from google.oauth2 import service_account



def _load_sql_credentials():
    """Return service account credentials for Cloud SQL connector if configured."""
    path = os.getenv("CLOUD_SQL_CREDENTIALS")
    if not path:
        return None
    try:
        return service_account.Credentials.from_service_account_file(path)
    except Exception:
        return None


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
    direct_url = os.getenv("LEDGER_DATABASE_URL")
    local_mode = os.getenv("API_STORAGE_MODE", "").strip().lower() == "local"
    skip_db = os.getenv("DISABLE_PAYMENT_DB", "").strip().lower() in ("1", "true", "yes", "on")

    if (local_mode or skip_db) and not direct_url:
        return SimpleNamespace(connector=None, engine=None, SessionLocal=None, disabled=True)

    connector: Optional[Connector] = None
    if direct_url:
        engine: Engine = create_engine(direct_url, future=True)
    else:
        creds = _load_sql_credentials()
        connector = Connector(credentials=creds) if creds is not None else Connector()  # uses explicit creds when provided
        engine = create_engine(
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
        if getattr(state, "engine", None):
            state.engine.dispose()
    except Exception:
        pass
    try:
        if getattr(state, "connector", None):
            state.connector.close()
    except Exception:
        pass


def get_payment_db(request: Request) -> Generator[Session, None, None]:
    """
    FastAPI dependency. Pull Session factory from app.state (no globals).
    """
    SessionLocal = request.app.state.db.SessionLocal
    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="Payment ledger is disabled in local mode")
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass
