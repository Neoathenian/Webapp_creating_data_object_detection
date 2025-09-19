from __future__ import annotations

import hashlib
import secrets
from typing import Any, Mapping

API_KEY_HEADER = "X-API-Key"


def generate_api_key() -> str:
    """Return a new random API key string suitable for display."""
    # token_urlsafe(32) yields ~43 characters of entropy (>250 bits)
    return secrets.token_urlsafe(32)


def hash_api_key(raw: str) -> str:
    """Hash an API key for storage/lookup."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_storage_uid(user: Mapping[str, Any]) -> str:
    """Derive the storage UID used for this app's GCS layout."""
    if not user:
        return "anon"
    candidate = (user.get("email") or user.get("sub") or user.get("name") or "anon").strip()
    return candidate or "anon"
