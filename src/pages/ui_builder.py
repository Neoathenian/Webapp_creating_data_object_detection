from pathlib import Path

import gradio as gr
from src.pages.header import render_header

from src.components.Uploader_Display import Uploader_Display


_ASSETS_DIR = Path(__file__).parent / "ui_builder_assets"


def _read_asset(name: str) -> str:
    return (_ASSETS_DIR / name).read_text(encoding="utf-8")


STYLES_HTML = _read_asset("styles.html")
SIDEBAR_HTML = _read_asset("sidebar.html")
CENTER_HTML = _read_asset("center.html")
INSPECTOR_HTML = _read_asset("inspector.html")
BUILDER_JS = _read_asset("builder.js")


def make_builder_app() -> gr.Blocks:
    with gr.Blocks() as app:
        hdr = gr.HTML()

        # Layout + theming
        gr.HTML(value=STYLES_HTML)

        # Root marker so CSS computes viewport sizes correctly
        gr.HTML("<div id='builder-root'></div>")

        # Fixed left sidebar
        gr.HTML(value=SIDEBAR_HTML)

        # Center surface
        gr.HTML(value=CENTER_HTML)

        # Slide-in inspector on the right
        gr.HTML(value=INSPECTOR_HTML)

        # Mount Uploader_Display into the slot using Gradio layout
        with gr.Column(visible=False) as _hidden_mount:
            uploader = Uploader_Display(elem_id="new-api-upload", accept="image/*", height=280, with_border="solid")

        # Attach behavior
        app.load(
            None,
            js=BUILDER_JS,
            outputs=[],
        )

        # Inject header at end to ensure styles loaded
        def _header(request: gr.Request):
            return render_header(path="/app", request=request)
        app.load(_header, outputs=[hdr])

    return app
