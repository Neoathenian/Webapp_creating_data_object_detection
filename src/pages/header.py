from __future__ import annotations
import html
from typing import Any, Optional
from starlette.requests import Request as StarletteRequest
from src.login_logic import get_user
from src.css.utils import load_css

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
    css_block = f"<style>\n{css}\n</style>"

    if user:
        name  = html.escape(user.get("name") or user.get("email") or "Signed in")
        email = html.escape(user.get("email") or "")
        photo = (user.get("picture") or "").strip()
        initial = html.escape((user.get("name") or user.get("email") or "?")[0].upper())

        avatar = (
            f'<img class="avatar-img" src="{html.escape(photo)}" alt="{name}" />'
            if photo else f'<div class="avatar-circle">{initial}</div>'
        )

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
    <a href="/logout" role="menuitem" class="menu-link">Logout</a>
  </div>
</details>""".strip()

        # Order: [credits][profile] — both in the SAME flex row, touching.
        right = f'<nav class="nav nav-tight">{_credits_iframe()}{account_html}</nav>'
    else:
        #This is literally the svg code for the google button
        google_btn = """
            <a href="/auth/google" class="google-btn-pill" aria-label="Sign in with Google">
            <div class="google-icon-wrapper">
                <svg class="google-icon" viewBox="0 0 48 48" width="20" height="20">
                <path fill="#FFC107" d="M43.6 20.5h-1.9V20H24v8h11.3c-1.6 4.6-6 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.7 1.1 7.8 3l5.7-5.7C33 6.1 28.8 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.7-.4-3.5z"/>
                <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.2 16.4 18.7 13 24 13c3 0 5.7 1.1 7.8 3l5.7-5.7C33 6.1 28.8 4 24 4 16.3 4 9.6 8.5 6.3 14.7z"/>
                <path fill="#4CAF50" d="M24 44c5.9 0 10.9-2.3 14.6-6.1l-6.9-5.7c-2 1.4-4.5 2.3-7.7 2.3-5.3 0-9.7-3.4-11.3-8l-6.7 5.2C9.4 39.4 16.2 44 24 44z"/>
                <path fill="#1976D2" d="M43.6 20.5H24v8h11.3c-.7 1.9-2.1 3.7-4 4.9l.1-.1 6.9 5.7c-.5.5 8.7-6.3 8.7-18 0-1.3-.1-2.7-.4-3.5z"/>
                </svg>
            </div>
            <span class="btn-text">Sign in with Google</span>
            </a>
            """.strip()
        right = f'<nav class="nav">{google_btn}</nav>'

    # Left-side: site logo (always) and optional Protected link (when logged in)
    logo_html = (
        '<a href="/" class="site-logo" aria-label="Home">'
        '<svg viewBox="0 0 24 24" class="logo-svg" aria-hidden="true">'
        '  <rect x="3" y="2" width="18" height="20" rx="3" ry="3" opacity=".25" />'
        '  <rect x="6" y="5" width="12" height="4" rx="1" />'
        '</svg>'
        '</a>'
    )

    left_link = '<a href="/app/" class="hdr-link">Builder</a>' if user else ''

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
