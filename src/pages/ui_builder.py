from pathlib import Path
import json

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


def _config_script(config: dict) -> str:
    return f"<script>window.__BUILDER_CONFIG__ = {json.dumps(config)};</script>"


def make_builder_app() -> gr.Blocks:
    config = {
        "apiPrefix": "/builder",
        "pagePath": "/templates",
        "sidebarTitle": "Templates",
        "newButtonText": "+ New template",
        "titlePlaceholder": "Template name",
        "uploadPrompt": "Upload an image to start a new template",
        "emptyHint": "Select a template from the left or create a new one.",
        "deleteLabel": "template",
        "showIntegration": True,
        "enableCollectorControls": False,
        "enableCropBboxes": False,
        "autoGenerateOnCreate": False,
    }
    with gr.Blocks(title="Pattern2json") as app:
        hdr = gr.HTML()

        # Layout + theming
        gr.HTML(value=STYLES_HTML)
        gr.HTML(value=_config_script(config))

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
            return render_header(path="/templates", request=request)
        app.load(_header, outputs=[hdr])

    return app


def make_data_collector_app() -> gr.Blocks:
    config = {
        "apiPrefix": "/data-collector",
        "pagePath": "/data-collector",
        "sidebarTitle": "Bboxes",
        "newButtonText": "+ Add files",
        "titlePlaceholder": "Sample name",
        "uploadPrompt": "Add images for the selected template",
        "emptyHint": "Choose a template, then add images to evaluate.",
        "deleteLabel": "image",
        "showIntegration": False,
        "enableCollectorControls": True,
        "enableCropBboxes": True,
        "autoGenerateOnCreate": False,
    }
    with gr.Blocks(title="Pattern2json Data collector") as app:
        hdr = gr.HTML()

        gr.HTML(value=STYLES_HTML)
        gr.HTML(value=_config_script(config))
        gr.HTML("<div id='builder-root'></div>")
        gr.HTML(value=SIDEBAR_HTML)
        gr.HTML(value=CENTER_HTML)
        gr.HTML(value=INSPECTOR_HTML)

        with gr.Column(visible=False) as _hidden_mount:
            uploader = Uploader_Display(elem_id="new-api-upload", accept="image/*", height=280, with_border="solid")

        app.load(
            None,
            js=BUILDER_JS,
            outputs=[],
        )

        def _header(request: gr.Request):
            return render_header(path="/data-collector", request=request)
        app.load(_header, outputs=[hdr])

    return app


def make_evaluation_overlap_app() -> gr.Blocks:
    config = {
        "apiPrefix": "/evaluation-overlap",
        "pagePath": "/evaluation-overlap",
        "sidebarTitle": "Evaluation overlap",
        "newButtonText": "+ Add files",
        "titlePlaceholder": "Sample name",
        "uploadPrompt": "Add images for the selected template",
        "emptyHint": "Choose a template, then add images to evaluate.",
        "deleteLabel": "image",
        "showIntegration": False,
        "enableCollectorControls": True,
        "enableCropBboxes": False,
        "autoGenerateOnCreate": False,
    }
    with gr.Blocks(title="Pattern2json Evaluation Overlap") as app:
        hdr = gr.HTML()

        gr.HTML(value=STYLES_HTML)
        gr.HTML(value=_config_script(config))
        gr.HTML("<div id='builder-root'></div>")
        gr.HTML(value=SIDEBAR_HTML)
        gr.HTML(value=CENTER_HTML)
        gr.HTML(value=INSPECTOR_HTML)

        with gr.Column(visible=False) as _hidden_mount:
            uploader = Uploader_Display(elem_id="new-api-upload", accept="image/*", height=280, with_border="solid")

        app.load(
            None,
            js=BUILDER_JS,
            outputs=[],
        )

        def _header(request: gr.Request):
            return render_header(path="/evaluation-overlap", request=request)
        app.load(_header, outputs=[hdr])

    return app
