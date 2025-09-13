# src/mount_gradio_app.py
from starlette.requests import Request
from starlette.responses import RedirectResponse
import gradio as gr
from starlette.middleware.sessions import SessionMiddleware

from src.login_logic import add_login_routes
from src.secrets import get_secret

GRADIO_PUBLIC_PREFIXES = (
    "/gradio_api", "/file", "/assets", "/static", "/config",
    "/proxy", "/localfiles", "/theme.css", "/favicon.ico",
    "/robots.txt", "/logo.png",
)

# Public non-auth endpoints
PUBLIC_EXTRA = (
    "/payments/create-checkout-session",
    "/checkout/success",
    "/checkout/cancel",
    "/webhooks/stripe",
)

def add_middleware_redirect(app, app_route: str):
    """
    Protect everything under `app_route` EXCEPT Gradio internals there.
    Root-level Gradio internals and PUBLIC_EXTRA are always allowed.
    """
    ALLOWED_MOUNT_PREFIXES = tuple(
        f"{app_route}{p}" for p in (
            "/gradio_api", "/file", "/assets", "/static", "/config",
            "/proxy", "/localfiles", "/theme.css", "/api/predict", "/reset"
        )
    )

    @app.middleware("http")
    async def check_authentication(request: Request, call_next):
        path = request.url.path

        # If user is already authenticated and hits root, send to app
        if path == "/" and request.session.get("user"):
            # Always send authenticated users to the main protected app
            return RedirectResponse(url="/app/")

        # Always allow public root and auth/public entry points
        if (
            path == "/" or
            path.startswith("/auth") or
            path.startswith("/login") or
            any(path.startswith(p) for p in GRADIO_PUBLIC_PREFIXES) or
            any(path.startswith(p) for p in ALLOWED_MOUNT_PREFIXES) or
            any(path.startswith(p) for p in PUBLIC_EXTRA)
        ):
            return await call_next(request)

        # Require session for protected mount pages
        if path.startswith(app_route):
            if not request.session.get("user"):
                return RedirectResponse(url="/")
            return await call_next(request)

        # Non-matching paths: pass through
        return await call_next(request)

def mount_gradio_app(*args, secret_key: str | None = None, **kwargs):
    app = args[0]
    path = args[2]

    add_middleware_redirect(app, path)
    add_login_routes(app, path)

    # session secret via get_secret (env locally, Secret Manager on GCP)
    secret = secret_key or get_secret("SESSION_SECRET", default="dev-session-secret")
    app.add_middleware(SessionMiddleware, secret_key=secret)

    return gr.mount_gradio_app(*args, **kwargs)
