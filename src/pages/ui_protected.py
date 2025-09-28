import gradio as gr
from src.pages.header import render_header
from src.login_logic import get_user

def _header_app(request: gr.Request):
    return render_header(path="/app", request=request)

def _show_user(request: gr.Request):
    return gr.update(value=get_user(request))

def make_protected_app() -> gr.Blocks:
    with gr.Blocks(title="Pattern2json") as protected_app:
        hdr = gr.HTML()
        gr.Markdown("### Protected area (/app)")

        with gr.Row():
            balance_box = gr.Textbox(label="Credits", interactive=False)

        protected_app.load(
            None,
            js="""
            async () => {
              try {
                const r = await fetch('/user/balance');
                if (!r.ok) return '—';
                const j = await r.json();
                return String(j.balance ?? 0);
              } catch { return '—'; }
            }
            """,
            outputs=[balance_box],
        )
        
        gr.HTML('<a href="/profile/" style="text-decoration:none;padding:.5em 1em;border:1px solid #ddd;border-radius:8px;">Go to Profile</a>')

        btn_show = gr.Button("Get current user")
        databox = gr.Textbox(interactive=False)
        btn_show.click(_show_user, outputs=[databox])

        protected_app.load(_header_app, outputs=[hdr])

    return protected_app
