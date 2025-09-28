import gradio as gr
from src.pages.header import render_header

def _header_root(request: gr.Request):
    # Use keyword args so order can't be swapped by Gradio
    return render_header(path="/", request=request)

def make_login_page() -> gr.Blocks:
    with gr.Blocks(title="Pattern2json") as login_page:
        hdr = gr.HTML()
        gr.Markdown("## Welcome\nThis is the public homepage. Please sign in to continue.")
        gr.Markdown("- Public info\n- Marketing copy\n- Whatever you want here")

        login_page.load(_header_root, outputs=[hdr])

    return login_page
