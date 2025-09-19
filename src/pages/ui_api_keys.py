from __future__ import annotations

from pathlib import Path

import gradio as gr

from src.css.utils import load_css
from src.pages.header import render_header


_ASSETS_DIR = Path(__file__).parent / "ui_api_keys_assets"


def _read_asset(name: str) -> str:
    path = _ASSETS_DIR / name
    return path.read_text(encoding="utf-8")


API_KEYS_JS = _read_asset("app.js")


def _header_api_keys(request: gr.Request):
    return render_header(path="/api-keys", request=request)


def make_api_keys_app() -> gr.Blocks:
    with gr.Blocks() as app:
        hdr = gr.HTML()

        css = load_css("api_keys.css")
        gr.HTML(f"<style>\n{css}\n</style>")

        gr.HTML(
            value="""
            <div class=\"api-keys-page\">
              <div class=\"api-keys-card\">
                <h1>API keys</h1>
                <p>Use these keys to authenticate requests made to your hosted APIs.</p>
                <div class=\"integration-section\">
                  <div class=\"integration-heading\">Endpoint &amp; header</div>
                  <div class=\"integration-note\">
                    Send requests to <code id=\"api-endpoint-template\">/external/apis/{api_id}</code>
                    with the <code id=\"api-key-header\">X-API-Key</code> header.
                  </div>
                </div>
                <div class=\"integration-section\">
                  <div class=\"integration-heading\">Current key</div>
                  <div id=\"api-key-status\" class=\"integration-status\">Loading…</div>
                  <div id=\"api-key-secret-wrap\" class=\"integration-secret hidden\">
                    <input id=\"api-key-secret\" class=\"integration-input highlight\" type=\"text\" readonly />
                    <button id=\"btn-copy-key\" class=\"btn small\" type=\"button\">Copy</button>
                  </div>
                  <div class=\"integration-actions\">
                    <button id=\"btn-generate-key\" class=\"btn primary small\" type=\"button\">Generate key</button>
                    <button id=\"btn-delete-key\" class=\"btn danger small\" type=\"button\">Delete key</button>
                  </div>
                  <div id=\"api-key-hint\" class=\"integration-note\">
                    Generate a key to authenticate requests. Keys are shown only once—store it securely.
                  </div>
                </div>
              </div>
            </div>
            """,
        )

        app.load(_header_api_keys, outputs=[hdr])
        app.load(None, js=API_KEYS_JS, outputs=[])

    return app
