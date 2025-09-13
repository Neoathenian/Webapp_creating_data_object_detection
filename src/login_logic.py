from typing import List, Dict, Any,Optional
from authlib.integrations.starlette_client import OAuth

from starlette.requests import Request
from starlette.responses import RedirectResponse

from starlette.requests import Request as StarletteRequest

oauth = OAuth()
login_providers: List[Dict[str, Any]] = []


def register_oauth_provider(*args, **kwargs):
    login_providers.append(kwargs)
    return oauth.register(*args, **kwargs)


def add_login_routes(app, app_route: str = "/app"):
    @app.get("/logout")
    async def logout(request: Request):
        request.session.pop("user", None)
        return RedirectResponse("/")

    @app.get(app_route)
    async def _redir_to_slash():
        return RedirectResponse(f"{app_route}/")

    for p in login_providers:
        name = p["name"]
        start_route_name = f"auth_start_{name}"
        cb_route_name    = f"auth_callback_{name}"

        @app.get(f"/auth/{name}", name=start_route_name)
        async def auth_start(request: Request, _name=name, _cb=cb_route_name):
            client = oauth.create_client(_name)
            redirect_uri = request.url_for(_cb)
            return await client.authorize_redirect(request, redirect_uri)

        @app.get(f"/auth/{name}/callback", name=cb_route_name)
        async def auth_callback(request: Request, _name=name, _app_route=app_route):
            client = oauth.create_client(_name)
            token = await client.authorize_access_token(request)
            userinfo = token.get("userinfo") or await client.parse_id_token(request, token)
            request.session["user"] = dict(userinfo)
            return RedirectResponse(f"{_app_route}/")
        

def get_user(request: Any) -> Optional[dict]:
    try:
        if hasattr(request, "request") and hasattr(request.request, "session"):
            return request.request.session.get("user")
        if isinstance(request, StarletteRequest):
            return request.session.get("user")
    except Exception:
        pass
    return None

