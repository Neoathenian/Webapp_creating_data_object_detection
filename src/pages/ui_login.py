import gradio as gr
from src.pages.header import render_header

def _header_root(request: gr.Request):
    # Use keyword args so order can't be swapped by Gradio
    return render_header(path="/", request=request)

def make_login_page() -> gr.Blocks:
    with gr.Blocks(title="Pattern2json") as login_page:
        hdr = gr.HTML()
        gr.Markdown("## Pattern2json\nCreate and manage object-detection API definitions.")
        gr.HTML('<p><a href="/login/local">Open builder</a></p>')

        login_page.load(_header_root, outputs=[hdr])

    return login_page
