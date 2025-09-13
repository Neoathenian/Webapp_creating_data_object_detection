from __future__ import annotations
import os
from functools import lru_cache
from google.cloud import secretmanager

@lru_cache(maxsize=1)
def _sm_client() -> secretmanager.SecretManagerServiceClient:
    return secretmanager.SecretManagerServiceClient()

@lru_cache(maxsize=256)
def _sm_get(resource: str) -> str:
    """Retrieve a secret value from Google Cloud Secret Manager."""
    resp = _sm_client().access_secret_version(name=resource)
    return resp.payload.data.decode("utf-8")

def get_secret(name: str,default="") -> str:
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
    if not default:
        return default
    raise RuntimeError(f"Missing {name} (or {name}_RESOURCE)")

# -------------------------------------------------------------------------

_PROJECT_SECRETS = [
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
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
