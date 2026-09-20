# ---- Resolve & inject ALL secrets BEFORE importing modules that read env ----
from src.secrets import get_secret

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from pathlib import Path


def _install_proxy_headers(app: FastAPI) -> None:
    """Attach a proxy-aware middleware even on stripped Starlette builds."""

    try:
        from starlette.middleware.proxy_headers import ProxyHeadersMiddleware as _Proxy

        app.add_middleware(_Proxy)
        return
    except ImportError:
        pass

    try:
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware as _Proxy  # type: ignore

        app.add_middleware(_Proxy, trusted_hosts="*")
        return
    except ImportError:
        pass

    from starlette.middleware.base import BaseHTTPMiddleware

    class _Proxy(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            forwarded_proto = request.headers.get("x-forwarded-proto")
            if forwarded_proto:
                request.scope["scheme"] = forwarded_proto.split(",")[0].strip()

            forwarded_host = request.headers.get("x-forwarded-host")
            forwarded_port = request.headers.get("x-forwarded-port")
            server = request.scope.get("server", (None, None))

            host = forwarded_host.split(",")[0].strip() if forwarded_host else server[0]
            port = (
                int(forwarded_port.split(",")[0])
                if forwarded_port and forwarded_port.split(",")[0].isdigit()
                else server[1]
            )
            if host or port:
                request.scope["server"] = (host, port)

            return await call_next(request)

    app.add_middleware(_Proxy)
import gradio as gr
import os

from src.pages.ui_login import make_login_page
from src.pages.ui_protected import make_protected_app
from src.pages.ui_profile import make_profile_app
from src.pages.ui_payment import make_payment_page
from src.pages.ui_api_keys import make_api_keys_app
from src.ledger_router import ledger_router
from src.payment_router import payment_router
from src.mount_gradio_app import mount_gradio_app
from src.api_builder_router import router as api_builder_router
from src.data_collector_router import router as data_collector_router
from src.evaluation_overlap_router import router as evaluation_overlap_router
from src.api_key_handling import (
    builder_router as api_key_router,
    external_router as external_api_router,
)
from src.pages.ui_builder import make_builder_app, make_data_collector_app, make_evaluation_overlap_app

# --- lifespan manages DB connector/engine safely (no globals)
from src.ledger_db_access import init_payment_db_state, shutdown_payment_db_state

async def lifespan(app: FastAPI):
    app.state.db = init_payment_db_state()
    try:
        yield
    finally:
        shutdown_payment_db_state(app.state.db)

app = FastAPI(lifespan=lifespan)
_install_proxy_headers(app)



@app.get("/_routes")
def _routes():
    return [getattr(r, "path", str(r)) for r in app.router.routes]

# --- Credits ledger routes
app.include_router(ledger_router)

# --- Payment router (deals with stripe) (must be public in middleware)
app.include_router(payment_router)

# --- API Builder routes
app.include_router(api_builder_router)
app.include_router(data_collector_router)
app.include_router(evaluation_overlap_router)
app.include_router(api_key_router)
app.include_router(external_api_router)

# --- Static assets
os.makedirs("images", exist_ok=True)
os.makedirs("secrets/api_builder/images", exist_ok=True)
LOGO_FILE = Path("images") / "Logo.png"
app.mount(
    "/images",
    StaticFiles(directory="images", check_dir=False),
    name="images",
)
app.mount(
    "/static/api_images",
    StaticFiles(directory="secrets/api_builder/images", check_dir=False),
    name="api_images",
)


@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    if LOGO_FILE.exists():
        return FileResponse(LOGO_FILE)
    raise HTTPException(status_code=404)

# --- Simple pages
protected_app = make_builder_app()  # Replace protected area with the builder UI
data_collector_app = make_data_collector_app()
evaluation_overlap_app = make_evaluation_overlap_app()
profile_app   = make_profile_app()
api_keys_page = make_api_keys_app()
buy_page      = make_payment_page()
login_page    = make_login_page()

# Optional: session secret via secret manager (fallback default set in bootstrap)
session_secret = get_secret("SESSION_SECRET", default="dev-session-secret")
mount_gradio_app(app, protected_app, "/templates", secret_key=session_secret)
mount_gradio_app(app, data_collector_app, "/data-collector", secret_key=session_secret)
mount_gradio_app(app, evaluation_overlap_app, "/evaluation-overlap", secret_key=session_secret)
mount_gradio_app(app, profile_app,   "/profile", secret_key=session_secret)
mount_gradio_app(app, api_keys_page, "/api-keys", secret_key=session_secret)
mount_gradio_app(app, buy_page,      "/buy", secret_key=session_secret)


@app.get("/app")
@app.get("/app/")
def _legacy_app_redirect():
    return RedirectResponse(url="/templates/")


gr.mount_gradio_app(app, login_page, "/")
