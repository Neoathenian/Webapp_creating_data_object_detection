import gradio as gr
from src.pages.header import render_header


def _header_payment(request: gr.Request):
    return render_header(path="/buy", request=request)


def make_payment_page() -> gr.Blocks:
    with gr.Blocks() as payment_page:
        hdr = gr.HTML()

        # Minimal inline CSS for clear, clickable cards
        gr.HTML(
            """
            <style>
              .buy-wrap { max-width: 900px; margin: 0 auto; }
              .buy-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
              .buy-card { cursor: pointer; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 24px; box-shadow: 0 8px 18px rgba(0,0,0,.06); transition: transform .06s ease, box-shadow .12s ease; }
              .buy-card:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(0,0,0,.10); }
              .buy-title { font-family: system-ui; font-weight: 700; color: #111827; font-size: 22px; margin: 0 0 6px; }
              .buy-sub { font-family: system-ui; color: #4b5563; margin: 0 0 12px; }
              .buy-price { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 18px; color: #111827; margin: 0; }
              .buy-note { font-family: system-ui; color: #6b7280; font-size: 12px; margin-top: 8px; }
            </style>
            """
        )

        gr.Markdown("### Buy Credits")
        gr.HTML("<div class='buy-wrap'><p>Select a package to continue to payment.</p></div>")

        with gr.Row():
            gr.HTML(
                """
                <div class="buy-grid">
                  <div class="buy-card" id="pkg-5" role="button" tabindex="0" aria-label="Buy 50 credits for 5€">
                    <h3 class="buy-title">50 credits</h3>
                    <p class="buy-sub">Starter</p>
                    <p class="buy-price">5€</p>
                    <p class="buy-note">Redirects to Stripe checkout</p>
                  </div>
                  <div class="buy-card" id="pkg-20" role="button" tabindex="0" aria-label="Buy 500 credits for 20€">
                    <h3 class="buy-title">500 credits</h3>
                    <p class="buy-sub">Value</p>
                    <p class="buy-price">20€</p>
                    <p class="buy-note">Redirects to Stripe checkout</p>
                  </div>
                  <div class="buy-card" id="pkg-100" role="button" tabindex="0" aria-label="Buy 5000 credits for 100€">
                    <h3 class="buy-title">5000 credits</h3>
                    <p class="buy-sub">Pro</p>
                    <p class="buy-price">100€</p>
                    <p class="buy-note">Redirects to Stripe checkout</p>
                  </div>
                </div>
                """
            )

        # Attach JS click handlers to the cards -> create Stripe checkout and redirect
        payment_page.load(
            None,
            js="""
            async () => {
              const go = async (packageKey) => {
                try {
                  const r = await fetch('/payments/create-checkout-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ package: packageKey })
                  });
                  if (!r.ok) { alert('Stripe error: ' + (await r.text())); return; }
                  const { url } = await r.json();
                  window.location.href = url;
                } catch (e) { alert('Network error'); }
              };
              const byId = (id) => document.getElementById(id);
              const attach = (id, key) => {
                const el = byId(id); if (!el) return;
                const h = () => go(key);
                el.addEventListener('click', h);
                el.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); h(); } });
              };
              attach('pkg-5',   'starter');
              attach('pkg-20',  'value');
              attach('pkg-100', 'pro');
              return '';
            }
            """,
            outputs=[],
        )

        payment_page.load(_header_payment, outputs=[hdr])

    return payment_page
