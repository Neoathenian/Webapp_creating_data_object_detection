import gradio as gr
from src.pages.header import render_header
from src.login_logic import get_user
from src.css.utils import load_css


def _header_profile(request: gr.Request):
    return render_header(path="/profile", request=request)


def _user_info(request: gr.Request):
    user = get_user(request) or {}
    name = user.get("name") or user.get("email") or "User"
    email = user.get("email") or ""
    photo = (user.get("picture") or "").strip()

    # Simple inline HTML for user info
    if photo:
        avatar_html = f'<img alt="{name}" src="{photo}" style="width:64px;height:64px;border-radius:50%;border:1px solid #e5e7eb;object-fit:cover;" />'
    else:
        initial = (name or "?")[0:1].upper()
        avatar_html = f'<div style="width:64px;height:64px;border-radius:50%;background:#e5e7eb;color:#374151;display:flex;align-items:center;justify-content:center;font-weight:700;">{initial}</div>'

    html = f"""
        <div class=\"profile-wrap\">
            <div class=\"profile-card\">
                <div class=\"user-row\">
                    <div class=\"avatar\">{avatar_html}</div>
                        <div class=\"meta\">
                            <div class=\"name\">{name}</div>
                            <div class=\"email\">{email}</div>
                            <div class=\"credits-inline\"><label>Credits</label><input id=\"credits-inline\" type=\"text\" value=\"\" readonly /></div>
                        </div>
                    </div>
                </div>
        </div>
    """
    return gr.update(value=html)


def make_profile_app() -> gr.Blocks:
    with gr.Blocks() as profile_app:
        hdr = gr.HTML()

        css = load_css("profile_page.css")
        gr.HTML(f"<style>\n{css}\n</style>")

        # Compact profile card with inline credits input
        with gr.Row(elem_id="profile-top-row"):
            with gr.Column(scale=1):
                user_html = gr.HTML(elem_id="profile-user")

        # History container
        history_html = gr.HTML("""
        <div class='profile-wrap'>
          <div class='history-card'>
            <div class='history-head'>
              <h4 class='history-title'>Credits History</h4>
              <p class='history-note'>Purchases and spends</p>
            </div>
            <div class='history-table-wrap'>
              <table class='history'>
                <thead>
                  <tr><th>Date</th><th>Change</th><th>Reason</th><th>Source</th></tr>
                </thead>
                <tbody id='hist-body'>
                </tbody>
              </table>
            </div>
            <div id='hist-more' class='hist-more'>Loading…</div>
          </div>
        </div>
        """)

        # Load balance, push to header, and initialize infinite scroll for ledger
        profile_app.load(
            None,
            js="""
            async () => {
              const esc = (v) => String(v ?? '').replaceAll('<','&lt;');
              const fmtDate = (s) => { try { return new Date(s).toLocaleString(); } catch { return String(s || ''); } };

              // Update balance and header pill
              try {
                const rb = await fetch('/user/balance');
                if (rb?.ok) {
                  const j = await rb.json();
                  const balance = Number.isFinite(+j.balance) ? String(j.balance) : '0';
                  try { const inp = document.getElementById('credits-inline'); if (inp) inp.value = balance; } catch {}
                  try { const ifr = document.querySelector('.credits-frame'); if (ifr && ifr.contentWindow) ifr.contentWindow.postMessage({ type: 'set-balance', balance: +balance }, '*'); } catch {}
                }
              } catch {}

              // Infinite scroll for history
              const state = { offset: 0, size: 30, loading: false, done: false };
              const tbody = document.getElementById('hist-body');
              const more  = document.getElementById('hist-more');
              if (tbody && more) {
                const append = (rows) => {
                  const frag = document.createDocumentFragment();
                  for (const r of rows) {
                    const d = +r.delta || 0; const cls = d >= 0 ? 'amt-pos' : 'amt-neg'; const sign = d > 0 ? '+' : '';
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td>${fmtDate(r.created_at)}</td><td class="${cls}">${sign}${d}</td><td>${esc(r.reason)}</td><td>${esc(r.source_type)}</td>`;
                    frag.appendChild(tr);
                  }
                  if (!rows.length && state.offset === 0) {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td colspan='4' style='color:#6b7280;padding:16px;'>No history yet</td>`;
                    frag.appendChild(tr);
                  }
                  tbody.appendChild(frag);
                };

                const loadMore = async () => {
                  if (state.loading || state.done) return;
                  state.loading = true; more.textContent = 'Loading…';
                  try {
                    const r = await fetch(`/user/ledger?limit=${state.size}&offset=${state.offset}`);
                    if (!r.ok) throw new Error('fetch');
                    const rows = await r.json();
                    append(Array.isArray(rows) ? rows : []);
                    const got = Array.isArray(rows) ? rows.length : 0;
                    state.offset += got;
                    if (got < state.size) { state.done = true; more.textContent = 'End of history'; }
                    else { more.textContent = 'Loading…'; }
                  } catch {
                    more.textContent = 'Failed to load';
                  } finally {
                    state.loading = false;
                  }
                };

                const io = new IntersectionObserver((entries) => {
                  for (const e of entries) { if (e.isIntersecting) loadMore(); }
                }, { root: null, rootMargin: '200px 0px', threshold: 0 });
                io.observe(more);
                // Kick off initial load
                loadMore();
              }

              // No component outputs to update
              return '';
            }
            """,
            outputs=[],
        )

        # Populate user info + header
        profile_app.load(_user_info, outputs=[user_html])
        profile_app.load(_header_profile, outputs=[hdr])

    return profile_app
