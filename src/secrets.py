from __future__ import annotations
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from google.cloud import secretmanager


_CANDIDATE_KEY_NAMES = (
    "billing_dev_sa.json",
)


def _default_credentials_path() -> Optional[Path]:
    secrets_dir = Path(__file__).resolve().parents[1] / "secrets"
    if not secrets_dir.exists():
        return None

    for name in _CANDIDATE_KEY_NAMES:
        candidate = secrets_dir / name
        if candidate.is_file():
            return candidate

    for candidate in sorted(secrets_dir.glob("*.json")):
        if candidate.is_file():
            return candidate
    return None


def _ensure_service_account() -> None:
    candidate = _default_credentials_path()
    if not candidate:
        return
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(candidate)
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        try:
            with candidate.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and data.get("project_id"):
                os.environ.setdefault("GOOGLE_CLOUD_PROJECT", data["project_id"])
        except Exception:
            pass


_ensure_service_account()

@lru_cache(maxsize=1)
def _sm_client() -> secretmanager.SecretManagerServiceClient:
    return secretmanager.SecretManagerServiceClient()

@lru_cache(maxsize=256)
def _sm_get(resource: str) -> str:
    """Retrieve a secret value from Google Cloud Secret Manager."""
    resp = _sm_client().access_secret_version(name=resource)
    return resp.payload.data.decode("utf-8")

def get_secret(name: str, default: Optional[str] = None) -> str:
    """
    Resolution order:
      1) NAME (env/.env)
      2) NAME_RESOURCE (Secret Manager resource path)
      3) else raise RuntimeError
    """
    if (v := os.getenv(name)) is not None:
        return v
    if (r := os.getenv(f"{name}_RESOURCE")):
        return _sm_get(r)
    if default is not None:
        return default
    raise RuntimeError(f"Missing {name} (or {name}_RESOURCE)")

# -------------------------------------------------------------------------

_PROJECT_SECRETS = [
    "STRIPE_SECRET_KEY",
    "STRIPE_PRICE_ID_STARTER",
    "STRIPE_PRICE_ID_MEDIUM",
    "STRIPE_PRICE_ID_PRO",
    "STRIPE_WEBHOOK_SECRET",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "INSTANCE_CONNECTION_NAME",
    "DB_NAME",
    "DB_USER",
    "DB_PASS",
    "CREDITS_PER_CENT",
    "ENV",
    "SESSION_SECRET",
]

def import_project_secrets() -> dict[str, str]:
    """
    Load all project secrets into os.environ and return them as a dict.
    Fails if any secret is missing (neither NAME nor NAME_RESOURCE set).
    """
    for key in _PROJECT_SECRETS:
        val = get_secret(key)
        os.environ[key] = val
