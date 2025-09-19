# ---- Resolve & inject ALL secrets BEFORE importing modules that read env ----
from src.secrets import get_secret

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
import gradio as gr
import os

from src.login_logic import register_oauth_provider
from src.pages.ui_login import make_login_page
from src.pages.ui_protected import make_protected_app
from src.pages.ui_profile import make_profile_app
from src.pages.ui_payment import make_payment_page
from src.ledger_router import ledger_router
from src.payment_router import payment_router
from src.mount_gradio_app import mount_gradio_app
from src.api_builder_router import router as api_builder_router
from src.api_key_handling import (
    builder_router as api_key_router,
    external_router as external_api_router,
)
from src.pages.ui_builder import make_builder_app

# --- lifespan manages DB connector/engine safely (no globals)
from src.ledger_db_access import init_payment_db_state, shutdown_payment_db_state

async def lifespan(app: FastAPI):
    app.state.db = init_payment_db_state()
    try:
        yield
    finally:
        shutdown_payment_db_state(app.state.db)

app = FastAPI(lifespan=lifespan)



@app.get("/_routes")
def _routes():
    return [getattr(r, "path", str(r)) for r in app.router.routes]

# OAuth client config (now guaranteed in env; also available via get_secret)
GOOGLE_CLIENT_ID     = get_secret("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = get_secret("GOOGLE_CLIENT_SECRET")

register_oauth_provider(
    name="google",
    icon="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    client_kwargs={"scope": "openid email profile"},
)

# --- Credits ledger routes
app.include_router(ledger_router)

# --- Payment router (deals with stripe) (must be public in middleware)
app.include_router(payment_router)

# --- API Builder routes
app.include_router(api_builder_router)
app.include_router(api_key_router)
app.include_router(external_api_router)

# --- Static for API images (ensure directory exists first)
os.makedirs("secrets/api_builder/images", exist_ok=True)
app.mount(
    "/static/api_images",
    StaticFiles(directory="secrets/api_builder/images", check_dir=False),
    name="api_images",
)

# --- Simple pages
protected_app = make_builder_app()  # Replace protected area with the builder UI
profile_app   = make_profile_app()
buy_page      = make_payment_page()
login_page    = make_login_page()

# Optional: session secret via secret manager (fallback default set in bootstrap)
session_secret = get_secret("SESSION_SECRET", default="dev-session-secret")
mount_gradio_app(app, protected_app, "/app", secret_key=session_secret)
mount_gradio_app(app, profile_app,   "/profile", secret_key=session_secret)
mount_gradio_app(app, buy_page,      "/buy", secret_key=session_secret)
gr.mount_gradio_app(app, login_page, "/")
