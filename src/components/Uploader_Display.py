import gradio as gr
import base64
from io import BytesIO


def _svg_styles() -> str:
    return (
        "<style>"
        "/* Base icon button */"
        ".icon-btn{width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;"
        "border:1px solid #d0d0d0;background:#fff;color:#444;border-radius:6px;cursor:pointer;padding:0;line-height:0;transition:background .15s ease,border-color .15s ease,color .15s ease;}"
        ".icon-btn svg{width:16px;height:16px;stroke:currentColor;}"
        ".icon-btn:focus{outline:2px solid #93c5fd; outline-offset:2px;}"
        "/* Upload (+) */"
        ".icon-btn icon-btn--upload{background:#ffffff;border-color:#d0d0d0;color:#374151;}"
        ".icon-btn--upload:hover{background:#f2f2f2;}"
        "/* Zoom (fullscreen) */"
        ".icon-btn--zoom{background:#ffffff;border-color:#d0d0d0;color:#374151;}"
        ".icon-btn--zoom:hover{background:#f2f2f2;}"
        "/* Clear (X) */"
        ".icon-btn--clear{background:#ffffff;border-color:#e5b3b3;color:#b91c1c;}"
        ".icon-btn--clear:hover{background:#fdecec;border-color:#f3aaaa;color:#991b1b;}"
        "</style>"
    )


def PIL_image_to_data_url(img):
    """Convert a PIL Image to a PNG data URL. Returns None if not convertible."""
    if img is None:
        return None
    try:
        from PIL import Image  # type: ignore
        if isinstance(img, Image.Image):
            buf = BytesIO()
            img.save(buf, format="PNG")
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        pass
    return None

class Uploader:
    """
    Uploader-only component (akin to gr.File): renders a dropzone and exposes
    a data URL via `value`. Does not auto-preview.
    """

    def __init__(self, *,
                 elem_id: str | None = None,
                 accept: str = "image/*,.pdf",
                 height: int | str | None = 300,
                 width: int | str | None = None,
                 show_upload: bool = True,
                 border: str = "dashed"):
        self.accept = accept
        self.height = height
        self.width = width
        self.elem_id = elem_id or "uploader"
        self.show_upload = show_upload
        # border: 'dashed' | 'solid' | 'none'
        self.border = border if border in {"dashed", "solid", "none"} else "dashed"
        self._build()

    def _build(self):
        base_id = self.elem_id
        drop_id = f"drop-{base_id}"
        btn_id = f"btn-{base_id}"
        file_id = f"file-{base_id}"
        # Expose IDs for composition
        self.btn_id = btn_id
        self.file_input_id = file_id
        if isinstance(getattr(self, "width", None), int):
            _width_style = f"width:{self.width}px; "
        elif isinstance(getattr(self, "width", None), str) and self.width.strip():
            _width_style = f"width:{self.width}; "
        else:
            _width_style = ""
        if isinstance(getattr(self, "height", None), int):
            _height_style = f"height:{self.height}px; "
        elif isinstance(getattr(self, "height", None), str) and str(self.height).strip():
            _height_style = f"height:{self.height}; "
        else:
            _height_style = ""

        border_css = (
            "border: 2px dashed #bbb;" if self.border == "dashed"
            else ("border: 2px solid #bbb;" if self.border == "solid" else "border: none;")
        )
        drop_html = f"""
        <div id='{drop_id}'
             style='
                background:#fff; {border_css} border-radius: 8px; padding: 16px;
                display:flex; align-items:center; justify-content:center;
                {_height_style}{_width_style}text-align:center; color:#666; cursor:pointer;'
             onclick="document.getElementById('{file_id}').click();"
             ondragover="event.preventDefault(); this.style.borderColor='#888';"
             ondragleave="this.style.borderColor='#bbb';"
             ondrop="event.preventDefault(); this.style.borderColor='#bbb';
                     const f = event.dataTransfer.files && event.dataTransfer.files[0];
                      if (f) {{ const dt = new DataTransfer(); dt.items.add(f);
                               const inp = document.getElementById('{file_id}');
                               inp.files = dt.files; const btn = document.getElementById('{btn_id}'); if (btn) btn.click(); }}">
          <div>
            <div style='line-height:1; display:flex; justify-content:center;'>
              <svg viewBox='0 0 24 24' width='40' height='40' fill='none'
                   stroke='#6b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'
                   aria-hidden='true' focusable='false'>
                <path d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'></path>
                <polyline points='17 8 12 3 7 8'></polyline>
                <line x1='12' y1='3' x2='12' y2='15'></line>
              </svg>
            </div>
            <div style='margin-top:10px; color:#6b7280; font-size:18px;'>Drop File Here</div>
            <div style='margin:6px 0; color:#9ca3af; font-size:14px;'>- or -</div>
            <div style='color:#6b7280; font-size:16px;'>Click to Upload</div>
          </div>
        </div>
        <input type='file' id='{file_id}' accept='{self.accept}' style='display:none' onchange="const btn=document.getElementById('{btn_id}'); if(btn) btn.click();" />
        """
        with gr.Column(elem_classes=["file-container"], elem_id=self.elem_id) as container:
            gr.HTML(value=drop_html)
            self._upload_btn = gr.Button("Upload", elem_id=btn_id, visible=False)
            self.value = gr.Textbox(visible=False)
            self.container = container

        self._upload_btn.click(
            fn=lambda s: gr.update(value=s),
            inputs=[self.value],
            outputs=[self.value],
            js=self._js_reader(),
            queue=False,
        )

    def _js_reader(self) -> str:
        # Instant blob preview using Display wrapper; return Data URL for processing.
        return (
            "async () => {\n"
            f"  const inputId = 'file-{self.elem_id}';\n"
            "  const el = document.getElementById(inputId);\n"
            "  if (!el || !el.files || !el.files[0]) return '';\n"
            "  const f = el.files[0];\n"
            "  // Compute Display preview and its inner content id\n"
            "  const base = inputId.slice('file-'.length);\n"
            "  const root = base.endsWith('-up') ? base.slice(0, -3) : base;\n"
            "  const previewId = 'preview-' + root + '-disp';\n"
            "  const contentId = previewId + '-content';\n"
            "  try {\n"
            "    const url = URL.createObjectURL(f);\n"
            "    const prev = document.getElementById(previewId);\n"
            "    const content = document.getElementById(contentId);\n"
            "    if (prev && content) {\n"
            "      prev.style.display = 'block';\n"
            "      const isPdf = (f.type||'').includes('pdf');\n"
            "      const inner = isPdf ? `<embed src=\"${url}\" type=\"application/pdf\" style=\"width:100%;height:100%;border:0;\" />` : `<img src=\"${url}\" style=\"max-width:100%;max-height:100%;display:block;\"/>`;\n"
            "      content.innerHTML = inner;\n"
            "      setTimeout(() => { try { URL.revokeObjectURL(url); } catch(e){} }, 15000);\n"
            "    }\n"
            "  } catch (e) { /* ignore */ }\n"
            "  const r = new FileReader();\n"
            "  return await new Promise((res) => { r.onload = () => res(r.result); r.readAsDataURL(f); });\n"
            "}"
        )

    def upload(self, fn, *, inputs=None, outputs=None, **kwargs):
        inputs = list(inputs or [])
        # Default to updating our hidden value so handlers can just return gr.update(value=...)
        outputs = outputs or [self.value]
        # Normalize outputs so passing the wrapper instance works (e.g., outputs=[uploader])
        norm = []
        for o in outputs:
            if o is self:
                norm.append(self.value)
            elif isinstance(o, (Uploader, Display, Uploader_Display)):
                norm.append(o.value)
            else:
                norm.append(o)
        outputs = norm
        reader = self._js_reader()
        js_wrapper = (
            "async (...args) => {\n"
            "  const data = await (" + reader + ")();\n"
            "  const out = Array.from(args); out[0] = data; return out;\n"
            "}"
        )
        return self._upload_btn.click(
            fn=fn,
            inputs=[self.value] + inputs,
            outputs=outputs,
            js=js_wrapper,
            **kwargs,
        )


class Display:
    """
    Display-only component (akin to gr.Display): renders a preview from a data
    URL set via `.value` or via `update()`.
    """

    def __init__(self, *,
                 elem_id: str | None = None,
                 height: int | str | None = 300,
                 width: int | str | None = None,
                 show_close: bool = True,
                 show_fullscreen: bool = True,
                 border: str = "dashed",
                 with_border: str | None = None):
        self.height = height
        self.width = width
        self.elem_id = elem_id or "display"
        self.show_close = show_close
        self.show_fullscreen = show_fullscreen
        # border (legacy) or with_border (preferred)
        _choice = with_border if with_border is not None else border
        self.border = _choice if _choice in {"dashed", "solid", "none"} else "dashed"
        self.preview_elem_id = f"preview-{self.elem_id}"
        self._toolbar_html = ""
        self._build()

    def _build(self):
        with gr.Column(elem_classes=["file-container"], elem_id=self.elem_id) as container:
            self.container = container
            self.value = gr.Textbox(visible=False)
        self.preview = gr.HTML(visible=False, elem_id=self.preview_elem_id)
        # Hidden clear button for toolbar X
        self._clear_btn_id = f"clear-{self.elem_id}"
        self._clear_btn = gr.Button(visible=False, elem_id=self._clear_btn_id)
        self._clear_btn.click(
            fn=lambda: (gr.update(value="", visible=False), ""),
            inputs=None,
            outputs=[self.preview, self.value],
            queue=False,
        )
        self.value.change(
            fn=lambda s: self._handle_b64_to_html(s),
            inputs=[self.value],
            outputs=[self.preview, self.value],
            queue=False,
        )

    def _build_preview_box(self, inner_html: str) -> str:
        buttons = []
        if getattr(self, "_toolbar_html", ""):
            buttons.append(self._toolbar_html)
        if self.show_fullscreen:
            fs_paths = (
                "<path d='M3 9V3h6'></path><path d='M15 3h6v6'></path>"
                "<path d='M21 15v6h-6'></path><path d='M9 21H3v-6'></path>"
            )
            zoom_btn_id = f"zoom-btn-{self.elem_id}"
            buttons.append(
                f"<button id='{zoom_btn_id}' class='icon-btn icon-btn--zoom' title='Fullscreen' style=\"background:#fff;border:1px solid #d0d0d0;color:#444;border-radius:6px;\" onclick=\"(function(){{var p=document.getElementById('{self.preview_elem_id}'); var el=p && p.querySelector('img,embed'); if(el && el.requestFullscreen) el.requestFullscreen(); else if(p && p.requestFullscreen) p.requestFullscreen();}})()\">"
                f"<svg viewBox='0 0 24 24' fill='none' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{fs_paths}</svg>"
                f"</button>"
            )
        if self.show_close:
            x_path = "<path d='M6 6l12 12M6 18L18 6'></path>"
            clear_btn_id = f"clear-btn-{self.elem_id}"
            buttons.append(
                f"<button id='{clear_btn_id}' class='icon-btn icon-btn--clear' title='Clear' style=\"background:#fff;border:1px solid #e5b3b3;color:#b91c1c;border-radius:6px;\" onclick=\"(function(){{var b=document.getElementById('{self._clear_btn_id}'); if(b) b.click();}})()\">"
                f"<svg viewBox='0 0 24 24' fill='none' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{x_path}</svg>"
                f"</button>"
            )
        tray_html = (
            "<div style=\"position:absolute;top:8px;right:8px;display:flex;gap:6px;\">"
            + "".join(buttons)
            + "</div>"
        )
        if isinstance(getattr(self, "width", None), int):
            _width_style = f"width:{self.width}px; "
        elif isinstance(getattr(self, "width", None), str) and self.width.strip():
            _width_style = f"width:{self.width}; "
        else:
            _width_style = ""
        if isinstance(getattr(self, "height", None), int):
            _height_style = f"height:{self.height}px; "
        elif isinstance(getattr(self, "height", None), str) and str(self.height).strip():
            _height_style = f"height:{self.height}; "
        else:
            _height_style = ""
        border_css = (
            "border:2px dashed #bbb;" if self.border == "dashed"
            else ("border:2px solid #bbb;" if self.border == "solid" else "border:none;")
        )
        return (
            f"<div style=\"position:relative;background:#fff;{border_css}border-radius:8px;{_height_style}{_width_style}display:flex;align-items:center;justify-content:center;overflow:hidden;\">"
            f"{_svg_styles()}" + tray_html + f"<div id=\"{self.preview_elem_id}-content\" style=\"width:100%;height:100%;display:flex;align-items:center;justify-content:center;\">{inner_html}</div></div>"
        )

    def _handle_b64_to_html(self, b64):
        if not b64:
            return gr.update(value="", visible=False), ""
        # Accept data URL string or PIL.Image.Image; convert images when needed
        data_url = None
        if isinstance(b64, str):
            if b64.startswith("data:") and "," in b64:
                data_url = b64
            else:
                data_url = "data:image/png;base64," + b64
        else:
            conv = PIL_image_to_data_url(b64)
            if conv:
                data_url = conv
        if not data_url:
            return gr.update(value="", visible=False), ""
        inner = self._inner_for_data_url(data_url)
        return gr.update(value=self._build_preview_box(inner), visible=True), data_url

    def _inner_for_data_url(self, data_url: str) -> str:
        if data_url.startswith("data:application/pdf"):
            if isinstance(getattr(self, "height", None), int):
                _h = f"height:{self.height-8}px;"
            else:
                _h = "height:100%;"
            return f"<embed src=\"{data_url}\" type=\"application/pdf\" style=\"width:100%;{_h}border:0;\" />"
        if isinstance(getattr(self, "height", None), int):
            _max_h = f"max-height:{self.height-16}px;"
        else:
            _max_h = "max-height:100%;"
        return f"<img src=\"{data_url}\" style=\"max-width:100%;{_max_h}display:block;\"/>"

    def targets(self):
        return [self.preview, self.value]

    def update(self, *, data_url: str | None = None):
        if not data_url:
            return gr.update(), gr.update()
        inner = self._inner_for_data_url(data_url)
        return gr.update(value=self._build_preview_box(inner), visible=True), data_url

    def set_toolbar_html(self, html: str):
        self._toolbar_html = html or ""
        return self

    def set_reset_button_id(self, btn_id: str):
        """Route the toolbar X to a different hidden button id."""
        if btn_id:
            self._clear_btn_id = btn_id
        return self


class Uploader_Display:
    """Composite of Uploader + Display using composition instead of inheritance.

    Provides a single value and update surface and coordinates visibility.
    """

    def __init__(self, *,
                 elem_id: str | None = None,
                 accept: str = "image/*,.pdf",
                 height: int | str | None = 300,
                 width: int | str | None = None,
                 show_close: bool = True,
                 show_fullscreen: bool = True,
                 show_upload: bool = True,
                 border: str = "dashed",
                 with_border: str | None = None):
        self.elem_id = elem_id or "uploader_display"
        self.accept = accept
        self.height = height
        self.width = width
        self.show_close = show_close
        self.show_fullscreen = show_fullscreen
        self.show_upload = show_upload
        _choice = with_border if with_border is not None else border
        self.border = _choice if _choice in {"dashed", "solid", "none"} else "dashed"
        self._external_upload_attached = False

        with gr.Column(elem_classes=["file-container"], elem_id=self.elem_id) as container:

            # Children
            self.uploader = Uploader(
                elem_id=f"{self.elem_id}-up",
                accept=self.accept,
                height=self.height,
                width=self.width,
                show_upload=self.show_upload,
                border=self.border,
            )
            self.display = Display(
                elem_id=f"{self.elem_id}-disp",
                height=self.height,
                width=self.width,
                show_close=self.show_close,
                show_fullscreen=self.show_fullscreen,
                border=self.border,
            )
        # Unified value uses display.value
        self.value = self.display.value
        # Hidden processing value: always stores DataURL for server processing
        self.processing_value = gr.Textbox(visible=False)

        # Hidden reset button to restore uploader and clear preview
        self._reset_btn = gr.Button(visible=False, elem_id=f"reset-{self.elem_id}")
        self._reset_btn.click(
            fn=lambda: (gr.update(visible=True), gr.update(value="", visible=False), ""),
            inputs=None,
            outputs=[self.uploader.container, self.display.preview, self.value],
            queue=False,
            # We need to reset the uploaded image because if not we won´t be able to upload the same image if we hit the X button
            js=f"""
            () => {{
                const fileInput = document.getElementById('{self.uploader.file_input_id}');
                if (fileInput) {{
                    fileInput.value = ''; // Reset the file input
                }}
            }}
            """,
        )

        # Configure toolbar: order will be [custom html (+), fullscreen, X]. X should trigger reset
        toolbar_parts = []
        if self.show_upload:
            plus_svg = "<svg viewBox='0 0 24 24' fill='none' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M12 5v14M5 12h14'></path></svg>"
            upload_btn_id = f"upload-btn-{self.elem_id}"
            toolbar_parts.append(
                f"<button id='{upload_btn_id}' class='icon-btn icon-btn--upload' title='Upload' style=\"background:#fff;border:1px solid #d0d0d0;color:#444;border-radius:6px;\" onclick=\"(function(){{var el=document.getElementById('{self.uploader.file_input_id}'); if(el) el.click();}})()\">{plus_svg}</button>"
            )
        # Route Display's X to our reset button so it shows uploader again
        self.display.set_reset_button_id(f"reset-{self.elem_id}")
        self.display.set_toolbar_html("".join(toolbar_parts))

        # Default behavior: preview on upload and hide dropzone
        self.uploader.upload(
            self._default_on_upload,
            outputs=[self.uploader.container, self.display.preview, self.value],
            queue=False,
        )

        # When value changes programmatically (e.g., handler returns gr.update(value=...)),
        # hide the uploader when non-empty; show it again when cleared.
        self.value.change(
            fn=lambda s: gr.update(visible=(not bool(s))),
            inputs=[self.value],
            outputs=[self.uploader.container],
            queue=False,
        )

    def _default_on_upload(self, data_url: str):
        if self._external_upload_attached:
            return gr.update(), gr.update(), gr.update()
        prev, val = self.display.update(data_url=data_url)
        return gr.update(visible=False), prev, val

    def js_reader(self) -> str:
        return self.uploader._js_reader()

    def targets(self):
        return [self.uploader.container, self.display.preview, self.value]

    def update(self, *, data_url: str | None = None, visible: bool | None = None):
        if data_url:
            prev, val = self.display.update(data_url=data_url)
            return gr.update(visible=False), prev, val
        if visible is not None:
            return gr.update(visible=visible), gr.update(), gr.update()
        return gr.update(), gr.update(), gr.update()

    def upload(self, fn, *, inputs=None, outputs=None, **kwargs):
        self._external_upload_attached = True
        # Default to updating our unified value so user can return gr.update(value=...)
        outputs = outputs or [self.value]
        # Normalize: allow outputs to include wrapper instances
        norm = []
        for o in outputs:
            if o is self:
                norm.append(self.value)
            elif isinstance(o, (Uploader, Display, Uploader_Display)):
                norm.append(o.value)
            else:
                norm.append(o)
        outputs = norm

        # Wrap handler to convert PIL.Image returned inside gr.update(value=...) to data URL
        # Resolve tokens before calling user fn; convert PIL.Image to data URL on return

        def _resolve_token(x):
            # Pass tokens through; Display knows how to render them
            return x

        def _wrapped(*args, **kw):
            # First arg is the Data URL from JS
            data_url = args[0] if args else None
            out = fn(data_url, *list(args[1:]), **kw)

            def transform(x):
                try:
                    # If this is a gr.update-like dict with a PIL value, replace with data URL
                    if isinstance(x, dict) and "value" in x:
                        v = x["value"]
                        conv = PIL_image_to_data_url(v)
                        if conv:
                            return gr.update(value=conv)
                    # Or if raw PIL image is returned
                    conv = PIL_image_to_data_url(x)
                    if conv:
                        return conv
                except Exception:
                    return x
                return x

            # If caller returns fewer outputs than requested, append the data URL as needed
            if isinstance(out, (list, tuple)):
                transformed = [transform(x) for x in out]
                if len(transformed) < len(outputs) and data_url is not None:
                    transformed += [data_url] * (len(outputs) - len(transformed))
                return type(out)(transformed)
            t = transform(out)
            if len(outputs) > 1 and data_url is not None:
                extra = [data_url] * (len(outputs) - 1)
                return [t] + extra
            return t

        return self.uploader.upload(_wrapped, inputs=inputs, outputs=outputs, **kwargs)
