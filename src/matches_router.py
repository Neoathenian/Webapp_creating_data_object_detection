from pathlib import Path
from importlib.util import find_spec
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, FileResponse
from pydantic import BaseModel, Field, StrictInt

from src.login_logic import get_user
from src.pages.header import render_header, FAVICON_SCRIPT
from src import matches_storage as store

ASSETS = Path(__file__).parent / 'pages' / 'ui_matches_assets'


def require_user(request: Request):
    if not get_user(request):
        raise HTTPException(401, 'Unauthorized')
    if os.getenv('API_STORAGE_MODE', 'local') != 'local':
        raise HTTPException(400, 'Matches datasets are available in local storage mode.')


router = APIRouter(prefix='/matches', tags=['matches'], dependencies=[Depends(require_user)])


class Pair(BaseModel):
    template_id: StrictInt
    scene_id: StrictInt


class SaveMatches(BaseModel):
    revision: int = Field(ge=0)
    fingerprints: dict[str, str]
    pairs: list[Pair] = Field(max_length=10000)


def checked(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except store.ConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, 'OCR dataset or its image is missing.') from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
def page(request: Request):
    return ((ASSETS / 'index.html').read_text()
            .replace('<!-- BUILDER STYLES -->', (ASSETS.parent / 'ui_builder_assets/styles.html').read_text())
            .replace('<!-- HEADER -->', render_header('/matches', request).replace(FAVICON_SCRIPT, '')))


@router.get('/assets/{name}')
def asset(name: str):
    if name in ('SourceSansPro-Regular.woff2', 'SourceSansPro-Bold.woff2'):
        gradio_root = Path(find_spec('gradio').origin).parent
        return FileResponse(gradio_root / 'templates/frontend/static/fonts/Source Sans Pro' / name)
    if name not in ('matches.js', 'matches.css'):
        raise HTTPException(404)
    return FileResponse(ASSETS / name)


@router.get('/api/catalog')
def catalog():
    return checked(store.catalog)


@router.get('/api/pair/{template}/{sample}')
def pair(template: str, sample: str):
    return checked(store.load_pair, template, sample)


@router.put('/api/pair/{template}/{sample}')
def save(template: str, sample: str, payload: SaveMatches):
    return checked(store.save_pair, template, sample, [p.model_dump() for p in payload.pairs],
                   payload.revision, payload.fingerprints)


@router.get('/api/image/{template}/{sample}/{side}')
def image(template: str, sample: str, side: str):
    if side not in ('template', 'scene'):
        raise HTTPException(404)
    checked(store.folder, template, sample)
    path = checked(store.template_folder, template) if side == 'template' else checked(store.folder, template, sample)
    data = checked(store.ocr_data, path)
    raw = checked(store.coordinate_image, path, data, template=side == 'template')
    return Response(raw, media_type='image/png', headers={'Cache-Control': 'no-cache'})
