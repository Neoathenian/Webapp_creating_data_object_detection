import os
from typing import Any, Optional

from starlette.requests import Request
from starlette.requests import Request as StarletteRequest
from starlette.responses import RedirectResponse


_TRUE_VALUES = {"1", "true", "yes", "on"}
_LOCAL_AUTH_MODES = {"local", "none", "disabled", "noauth", "no-auth"}


def local_auth_enabled() -> bool:
    mode = os.getenv("AUTH_MODE", "local").strip().lower()
    disable_auth = os.getenv("DISABLE_AUTH", "").strip().lower()
    return mode in _LOCAL_AUTH_MODES or disable_auth in _TRUE_VALUES


def local_user() -> dict:
    email = os.getenv("LOCAL_USER_EMAIL", "object-detection-local@localhost").strip()
    name = os.getenv("LOCAL_USER_NAME", "Object Detection Builder").strip()
    sub = os.getenv("LOCAL_USER_SUB", email or "object-detection-local").strip()
    return {
        "sub": sub or "object-detection-local",
        "email": email or "object-detection-local@localhost",
        "name": name or "Object Detection Builder",
        "picture": "",
    }


def _session_user(request: Any) -> Optional[dict]:
    if not request:
        return None
    if hasattr(request, "request") and hasattr(request.request, "session"):
        user = request.request.session.get("user")
        return user if isinstance(user, dict) else None
    if isinstance(request, StarletteRequest):
        user = request.session.get("user")
        return user if isinstance(user, dict) else None
    return None


def _ensure_signup_bonus(request: Request, sub: str) -> None:
    session_factory = getattr(getattr(request.app.state, "db", None), "SessionLocal", None)
    if not sub or not session_factory:
        return

    from src.ledger_router import ensure_user_signup_bonus

    db = session_factory()
    try:
        ensure_user_signup_bonus(sub, db)
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def add_login_routes(app, app_route: str = "/templates"):
    @app.get("/logout")
    async def logout(request: Request):
        request.session.pop("user", None)
        if local_auth_enabled():
            return RedirectResponse(f"{app_route}/")
        return RedirectResponse("/")

    @app.get("/login/local")
    async def local_login(request: Request):
        if not local_auth_enabled():
            return RedirectResponse("/")

        user = local_user()
        request.session["user"] = user
        _ensure_signup_bonus(request, user["sub"])
        return RedirectResponse(f"{app_route}/")

    @app.get(app_route)
    async def _redir_to_slash():
        return RedirectResponse(f"{app_route}/")


def get_user(request: Any) -> Optional[dict]:
    try:
        user = _session_user(request)
        if user:
            return user
    except Exception:
        pass
    if local_auth_enabled():
        return local_user()
    return None
