from __future__ import annotations
import html
from typing import Any, Optional
from starlette.requests import Request as StarletteRequest
from src.login_logic import get_user, local_auth_enabled
from src.css.utils import load_css

LOGO_URL = "/images/Logo.png"
TEXT_LOGO_URL = "/images/Logo_text.png" 
FAVICON_SCRIPT = """
<script>
(function() {
  const url = new URL("__LOGO_URL__", window.location.origin).toString();

  const applyIcon = () => {
    const head = document.head || document.getElementsByTagName('head')[0];
    if (!head) return;

    const links = head.querySelectorAll('link[rel~="icon"], link[rel="shortcut icon"]');
    if (links.length) {
      links.forEach((link) => link.setAttribute('href', url));
    } else {
      const link = document.createElement('link');
      link.setAttribute('id', 'doc2json-favicon');
      link.setAttribute('rel', 'icon');
      link.setAttribute('type', 'image/png');
      link.setAttribute('href', url);
      head.appendChild(link);
    }
  };

  const applyTitle = () => {
    document.title = 'Pattern2json';
  };

  applyIcon();
  applyTitle();

  const observer = new MutationObserver(() => {
    applyIcon();
    applyTitle();
  });
  observer.observe(document.head || document.documentElement, { childList: true, subtree: true });
})();
</script>
""".strip().replace("__LOGO_URL__", LOGO_URL)

def _credits_iframe() -> str:
    # Auto-resize iframe width to its content; keep height fixed by CSS.
    return """
<iframe class="credits-frame" src="/header/credits?cb=1" title="Credits"
  style="visibility:hidden"
  onload="(function(ifr){
    try{
      const doc = ifr.contentDocument || ifr.contentWindow.document;
      if (doc && doc.body){
        // eliminate default margins inside the iframe
        doc.documentElement.style.margin = '0';
        doc.body.style.margin = '0';
        const w = Math.ceil((doc.documentElement.scrollWidth || doc.body.scrollWidth) || 0);
        if (w) ifr.style.width = w + 'px';
      }
    }catch(e){}
    ifr.style.visibility='visible';
  })(this)"></iframe>""".strip()

def _header_html(user: Optional[dict], path: str, request: Any) -> str:
    css = load_css("header.css")
    css_block = f"<style>\n{css}\n</style>\n{FAVICON_SCRIPT}"

    if user:
        name  = html.escape(user.get("name") or user.get("email") or "Signed in")
        email = html.escape(user.get("email") or "")
        photo = (user.get("picture") or "").strip()
        initial = html.escape((user.get("name") or user.get("email") or "?")[0].upper())

        avatar = (
            f'<img class="avatar-img" src="{html.escape(photo)}" alt="{name}" referrerpolicy="no-referrer" loading="lazy" />'
            if photo else f'<div class="avatar-circle">{initial}</div>'
        )

        logout_link = "" if local_auth_enabled() else '<a href="/logout" role="menuitem" class="menu-link">Logout</a>'

        account_html = f"""
<details class="account-menu">
  <summary class="account-btn" aria-label="{name}">
    {avatar}
  </summary>
  <div class="account-dropdown" role="menu">
    <div class="account-info">
      <div class="account-name">{name}</div>
      <div class="account-email">{email}</div>
    </div>
    <a href="/profile/" role="menuitem" class="menu-link">Profile</a>
    <a href="/api-keys/" role="menuitem" class="menu-link">API keys</a>
    {logout_link}
  </div>
</details>""".strip()

        # Order: [credits][profile] — both in the SAME flex row, touching.
        right = f'<nav class="nav nav-tight">{_credits_iframe()}{account_html}</nav>'
    else:
        action_btn = """
            <a href="/login/local" class="header-action-pill" aria-label="Open builder">
            <span class="btn-text">Open builder</span>
            </a>
            """.strip()
        right = f'<nav class="nav">{action_btn}</nav>'

    # Left-side: site logo (always) and optional Protected link (when logged in)
    logo_html = (
        '<a href="/" class="site-logo" aria-label="Home">'
        f'<img src="{LOGO_URL}" class="logo-img" alt="Doc2JSON" />'
        f'<img src="{TEXT_LOGO_URL}" class="logo-text-img" alt="Doc2JSON text" loading="lazy" />'
        '</a>'
    )

    if user:
        home_link = '<a href="/?home=1" class="hdr-link hdr-link--home">Home</a>'
        builder_link = '<a href="/templates/" class="hdr-link hdr-link--builder">templates</a>'
        collector_link = '<a href="/data-collector/" class="hdr-link hdr-link--builder">bboxes</a>'
        eval_link = '<a href="/evaluation-overlap/" class="hdr-link hdr-link--builder">Evaluation overlap</a>'
        left_link = f"{home_link}\n      {builder_link}\n      {collector_link}\n      {eval_link}\n      <a href='/matches/' class='hdr-link hdr-link--builder'>Matches</a>"
    else:
        left_link = ''

    #in the <div><strong></strong> we could put some cool text or maybe a logo
    return f"""{css_block}
<div class="hdr-wrap">
  <div class="hdr">
    <div class="hdr-left">{logo_html}<strong></strong>
      {left_link}
      <small class="muted" style="margin-left:.5rem"></small>
    </div>
    {right}
  </div>
</div>
<div class="hdr-spacer"></div>
"""

def render_header(path: str = "/", request: Any = None, *args, **kwargs) -> str:
    if "0" in kwargs and isinstance(kwargs["0"], str):
        path = kwargs["0"]
    if hasattr(path, "request") or isinstance(path, StarletteRequest):
        request, path = path, "/"
    user = get_user(request)
    return _header_html(user, path or "/", request)
