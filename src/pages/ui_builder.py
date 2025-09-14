import gradio as gr
from src.pages.header import render_header

from src.components.Uploader_Display import Uploader_Display


def make_builder_app() -> gr.Blocks:
    with gr.Blocks() as app:
        hdr = gr.HTML()

        # Layout + theming
        gr.HTML(
            value="""
            <style>
              :root { --top: 56px; --side: 280px; --insp: 320px; }

              #builder-root { position: relative; width: 100vw; min-height: calc(100vh - var(--top)); }

              /* Left sidebar */
              #sidebar {
                position: fixed; top: var(--top); left: 0; height: calc(100vh - var(--top)); width: var(--side);
                background: #fff; border-right: 1px solid #e5e7eb; box-shadow: 0 2px 10px rgba(0,0,0,.04);
                padding: 12px; overflow: hidden; display:flex; flex-direction:column; gap:8px;
              }
              #sidebar h3 { margin: 4px 0 4px 2px; font-size: 14px; color:#111; }
              .sidebar-list { list-style: none; padding: 0; margin: 0; overflow: auto; border-radius: 8px; }
              .sidebar-item { display: grid; grid-template-columns: 28px 1fr; gap: 8px; align-items: center; padding: 8px; cursor: pointer; border-radius:8px; }
              .sidebar-item:hover { background: #f7f7f8; }
              .sidebar-item.active { background: #eff6ff; outline: 1px solid #c7ddff; }
              .sidebar-item .thumb { width: 28px; height: 28px; background: #fafafa; border: 1px solid #eee; border-radius: 6px; overflow: hidden; }
              .sidebar-item .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }

              /* Center area fixed to viewport so content starts at top without extra scroll */
              #center {
                position: fixed; top: var(--top); left: var(--side); right: 0; bottom: 0;
                padding: 12px 24px; overflow: auto; display:flex; flex-direction: column;
              }
              #center.inspector-open { right: var(--insp); }
              .toolbar { display:flex; align-items:center; gap: 10px; margin: 8px 0 12px; flex-wrap: wrap; }
              .mode-btn { padding: 6px 10px; border: 1px solid #d0d7de; border-radius: 8px; background:#fff; cursor:pointer; }
              .mode-btn.active { background: #eff6ff; border-color:#93c5fd; }
              .mode-btn.icon { display:inline-flex; align-items:center; justify-content:center; width:36px; height:36px; padding:0; }
              .mode-btn.icon svg { width:18px; height:18px; stroke:#374151; fill:none; stroke-width:2; }
              .mode-btn.active.icon svg { stroke:#1d4ed8; }
              .api-title { flex: 1; min-width: 220px; padding:8px; border:1px solid #d1d5db; border-radius:8px; }
              .zoom-wrap { display:flex; align-items:center; gap:6px; }
              .zoom-range { width: 180px; }
              .save-btn { padding: 6px 12px; border-radius: 8px; border:1px solid #10b981; background:#10b981; color:#fff; cursor:pointer; }
              .save-btn[disabled] { opacity:.5; cursor:not-allowed; }

              .workspace { position: relative; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; flex: 1 1 auto; display:block; overflow: hidden; min-height: 0; }
              #workspace.mode-select { cursor: default; }
              #workspace.mode-draw, #overlay.mode-draw { cursor: crosshair; }
              .workspace.grabbing { cursor: grabbing; }
              .stage { position: absolute; left: 0; top: 0; transform-origin: top left; user-select: none; }
              .stage img { display:block; max-width: none; }
              /* overlay must receive pointer events for drawing */
              .overlay { position: absolute; left: 0; top: 0; pointer-events: auto; }
              .rect { position: absolute; border: 2px solid #2563eb; background: rgba(37,99,235,0.05); box-sizing: border-box; pointer-events: auto; border-radius: 2px; }
              .rect.selected { border-color: #ef4444; background: rgba(239,68,68,0.06); }
              .hint { color:#6b7280; text-align:center; padding: 20px; }

              /* Right inspector */
              #inspector { position: fixed; top: var(--top); right: 0; height: calc(100vh - var(--top)); width: var(--insp);
                background:#fff; border-left: 1px solid #e5e7eb; box-shadow: 0 2px 10px rgba(0,0,0,.05);
                padding: 12px 14px; transform: translateX(100%); opacity: .0; transition: transform .18s ease, opacity .18s ease; overflow:auto; }
              #inspector.open { transform: translateX(0); opacity: 1; }
              #inspector h3 { margin: 4px 0 8px; font-size: 14px; }
              .inspector .row { display:flex; flex-direction:column; gap: 6px; margin: 8px 0; }
              .inspector label { font-size: 12px; color: #374151; }
              .inspector input[type="text"], .inspector input[type="number"] {
                padding:8px; border:1px solid #d1d5db; border-radius:8px; width: 100%; box-sizing: border-box;
              }
              .inspector input[type="checkbox"] { -webkit-appearance:none; appearance:none; margin:0; width:18px; height:18px; border:2px solid #2563eb; border-radius:4px; background:#fff; display:inline-grid; place-content:center; cursor:pointer; }
              .inspector input[type="checkbox"]::after { content:""; width:6px; height:10px; border-right:3px solid #fff; border-bottom:3px solid #fff; transform: rotate(45deg) scale(0); transition: transform .12s ease; }
              .inspector input[type="checkbox"]:checked { background:#2563eb; }
              .inspector input[type="checkbox"]:checked::after { transform: rotate(45deg) scale(1); }
              .inspector .danger { background:#fee2e2; color:#991b1b; border:1px solid #fecaca; padding:8px 10px; border-radius:8px; cursor:pointer; }

              .create-area { display:none; }
              .create-actions { display:flex; gap:8px; margin-top:8px; }
              .btn { padding: 8px 12px; border: 1px solid #d0d7de; border-radius: 8px; background:#fff; cursor:pointer; }
              .btn.primary { background:#2563eb; border-color:#2563eb; color: #fff; }
            </style>
            """
        )

        # Root marker so CSS computes viewport sizes correctly
        gr.HTML("<div id='builder-root'></div>")

        # Fixed left sidebar
        gr.HTML(
            value="""
            <div id='sidebar'>
              <h3>APIs</h3>
              <div style='display:flex; gap:8px;'>
                <button id='btn-new-api' class='btn primary'>+ New API</button>
              </div>
              <ul id='api-list' class='sidebar-list'></ul>
            </div>
            """
        )

        # Center surface
        gr.HTML(
            value="""
            <div id='center'>
              <div class='toolbar'>
                <input id='api-title' class='api-title' type='text' placeholder='API name' />
                <button id='mode-select' class='mode-btn icon active' data-mode='select' title='Select' aria-label='Select'>
                  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M3 3l7 14 2-6 6-2-15-6z"></path>
                  </svg>
                </button>
                <button id='mode-draw' class='mode-btn icon' data-mode='draw' title='Draw' aria-label='Draw'>
                  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 20h9"></path>
                    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"></path>
                  </svg>
                </button>
                <span class='zoom-wrap'>Zoom <input id='zoom-range' class='zoom-range' type='range' min='20' max='300' value='100' /> <span id='zoom-label'>100%</span></span>
                <button id='btn-save' class='save-btn' disabled>Save</button>
              </div>
              <div class='create-area' id='create-area'>
                <div style='margin-bottom:6px;color:#374151;'>Upload an image to start a new API</div>
                <div id='new-api-uploader-slot'></div>
                <div class='create-actions'>
                  <button id='btn-create-from-upload' class='btn primary'>Create API</button>
                  <button id='btn-cancel-create' class='btn'>Cancel</button>
                </div>
              </div>
                <div class='workspace mode-select' id='workspace'>
                  <div class='hint' id='workspace-hint'>Select an API from the left or create a new one.</div>
                  <div class='stage' id='stage' style='display:none;'>
                    <img id='workspace-img' src='' alt='document' />
                    <div class='overlay' id='overlay'></div>
                  </div>
                </div>
            </div>
            """
        )

        # Slide-in inspector on the right
        gr.HTML(
            value="""
            <div class='inspector' id='inspector'>
              <h3>Inspector</h3>
              <div id='selection-panel' style='display:none;'>
                <div class='row'>
                  <label for='rect-name'>Name</label>
                  <input id='rect-name' type='text' placeholder='Enter name' />
                </div>
                <div class='row' style='flex-direction:row; align-items:center; gap:8px;'>
                  <input id='rect-extract' type='checkbox' checked />
                  <label for='rect-extract'>Extract text</label>
                </div>
                <div class='row' style='display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px;'>
                  <div>
                    <label for='rect-x'>X (px)</label>
                    <input id='rect-x' type='number' min='0' step='1' />
                  </div>
                  <div>
                    <label for='rect-y'>Y (px)</label>
                    <input id='rect-y' type='number' min='0' step='1' />
                  </div>
                  <div>
                    <label for='rect-w'>W (px)</label>
                    <input id='rect-w' type='number' min='1' step='1' />
                  </div>
                  <div>
                    <label for='rect-h'>H (px)</label>
                    <input id='rect-h' type='number' min='1' step='1' />
                  </div>
                </div>
                <div class='row'>
                  <button id='btn-delete-rect' class='danger'>Delete rectangle</button>
                </div>
              </div>
            </div>
            """
        )

        # Mount Uploader_Display into the slot using Gradio layout
        with gr.Column(visible=False) as _hidden_mount:
            uploader = Uploader_Display(elem_id="new-api-upload", accept="image/*", height=280, with_border="solid")

        # Attach behavior
        app.load(
            None,
            js="""
            async () => {
              // State
              const state = {
                apis: [],
                selected: null, // api id
                rects: [],
                mode: 'select',
                zoom: 1,
                img: { naturalW: 0, naturalH: 0 },
                dirty: false,
              };

              // Elements
              const listEl = document.getElementById('api-list');
              const btnNew = document.getElementById('btn-new-api');
              const createArea = document.getElementById('create-area');
              const slot = document.getElementById('new-api-uploader-slot');
              const hiddenMount = document.getElementById('new-api-upload');
              const hint = document.getElementById('workspace-hint');
              const stage = document.getElementById('stage');
              const img = document.getElementById('workspace-img');
              const overlay = document.getElementById('overlay');
              const titleInp = document.getElementById('api-title');
              const zoomRange = document.getElementById('zoom-range');
              const zoomLabel = document.getElementById('zoom-label');
              const modeSelect = document.getElementById('mode-select');
              const modeDraw = document.getElementById('mode-draw');
              const selPanel = document.getElementById('selection-panel');
              const rectName = document.getElementById('rect-name');
              const rectExtract = document.getElementById('rect-extract');
              const rectX = document.getElementById('rect-x');
              const rectY = document.getElementById('rect-y');
              const rectW = document.getElementById('rect-w');
              const rectH = document.getElementById('rect-h');
              const btnDelRect = document.getElementById('btn-delete-rect');
              const btnCreateFromUpload = document.getElementById('btn-create-from-upload');
              const btnCancelCreate = document.getElementById('btn-cancel-create');
              const inspector = document.getElementById('inspector');
              const center = document.getElementById('center');
              const btnSave = document.getElementById('btn-save');

              function markDirty(d=true){ state.dirty=!!d; btnSave.disabled = !state.dirty || !state.selected; }

              async function doSave(){
                if (!state.selected) return true;
                try{
                  await fetch(`/builder/apis/${state.selected}`,{ method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ name: titleInp.value || 'Untitled API', rects: state.rects }) });
                  markDirty(false); await refreshList(); return true;
                }catch{ return false; }
              }

              window.addEventListener('beforeunload', (e)=>{ if(state.dirty){ e.preventDefault(); e.returnValue=''; return ''; } });

              // Move uploader into slot once
              if (hiddenMount && slot && !slot.hasChildNodes()) {
                slot.appendChild(hiddenMount);
              }

              function apiImageInput() {
                return document.getElementById('file-new-api-upload-up');
              }

  function setMode(m) {
    state.mode = m;
    modeSelect.classList.toggle('active', m === 'select');
    modeDraw.classList.toggle('active', m === 'draw');
    const ws = document.getElementById('workspace');
    const ov = document.getElementById('overlay');
    if (ws) { ws.classList.toggle('mode-select', m === 'select'); ws.classList.toggle('mode-draw', m === 'draw'); }
    if (ov) { ov.classList.toggle('mode-draw', m === 'draw'); }
  }

              function setInspectorOpen(open) {
                inspector.classList.toggle('open', !!open);
                center.classList.toggle('inspector-open', !!open);
              }

              function percentClamp(v) { return Math.max(0, Math.min(1, v)); }

              function renderList() {
                listEl.innerHTML = '';
                for (const it of state.apis) {
                  const li = document.createElement('li');
                  li.className = 'sidebar-item' + (it.id === state.selected ? ' active' : '');
                  li.dataset.id = it.id;
                  const thumb = document.createElement('div'); thumb.className = 'thumb';
                  const img = document.createElement('img'); img.src = it.image_url; thumb.appendChild(img);
                  const label = document.createElement('div'); label.textContent = it.name || 'Untitled';
                  li.appendChild(thumb); li.appendChild(label);
                  li.onclick = async () => {
                    if (state.dirty) {
                      if (confirm('You have unsaved changes. Save before switching?')) { const ok = await doSave(); if (!ok) return; }
                      else { markDirty(false); }
                    }
                    await loadApi(it.id);
                  };
                  listEl.appendChild(li);
                }
              }

              async function refreshList(selectId = null) {
                try {
                  const r = await fetch('/builder/apis');
                  const j = await r.json();
                  state.apis = Array.isArray(j) ? j : [];
                } catch { state.apis = []; }
                if (selectId) state.selected = selectId; else if (state.selected && !state.apis.find(a => a.id === state.selected)) state.selected = null;
                renderList();
              }

              function clearSelection() {
                selPanel.style.display = 'none';
                rectName.value = '';
                rectExtract.checked = true;
                for (const el of overlay.querySelectorAll('.rect')) el.classList.remove('selected');
                overlay.dataset.selected = '';
                setInspectorOpen(false);
              }

              function selectRect(id) {
                for (const el of overlay.querySelectorAll('.rect')) el.classList.toggle('selected', el.dataset.id === id);
                overlay.dataset.selected = id || '';
                const r = state.rects.find(x => x.id === id);
                if (r) {
                  selPanel.style.display = 'block';
                  rectName.value = r.name || '';
                  rectExtract.checked = !!r.extract_text;
                  setInspectorOpen(true);
                  rectX.value = Math.round(r.x * state.img.naturalW);
                  rectY.value = Math.round(r.y * state.img.naturalH);
                  rectW.value = Math.round(r.w * state.img.naturalW);
                  rectH.value = Math.round(r.h * state.img.naturalH);
                } else {
                  clearSelection();
                }
              }

              function layoutOverlay() {
                overlay.style.left = '0px';
                overlay.style.top = '0px';
                overlay.style.width = (state.img.naturalW) + 'px';
                overlay.style.height = (state.img.naturalH) + 'px';
              }

              function applyTransform(){
                const st = document.getElementById('stage');
                st.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
              }

              function centerStage() {
                const wrap = document.getElementById('workspace');
                const w = wrap.clientWidth, h = wrap.clientHeight;
                const sw = state.img.naturalW * state.zoom;
                const sh = state.img.naturalH * state.zoom;
                state.panX = Math.floor((w - sw) / 2);
                state.panY = Math.floor((h - sh) / 2);
                applyTransform();
              }

              function renderRects() {
                overlay.innerHTML = '';
                layoutOverlay();
                for (const r of state.rects) {
                  const el = document.createElement('div');
                  el.className = 'rect' + (overlay.dataset.selected === r.id ? ' selected' : '');
                  el.dataset.id = r.id;
                  el.style.left = (r.x * state.img.naturalW) + 'px';
                  el.style.top  = (r.y * state.img.naturalH) + 'px';
                  el.style.width  = (r.w * state.img.naturalW) + 'px';
                  el.style.height = (r.h * state.img.naturalH) + 'px';
                  el.onclick = (ev) => { ev.stopPropagation(); setMode('select'); selectRect(r.id); };
                  // Add resize handles if selected
                  if (overlay.dataset.selected === r.id) {
                    const cursors = { nw:'nwse-resize', n:'ns-resize', ne:'nesw-resize', e:'ew-resize', se:'nwse-resize', s:'ns-resize', sw:'nesw-resize', w:'ew-resize' };
                    const positions = ['nw','n','ne','e','se','s','sw','w'];
                    for (const pos of positions) {
                      const h = document.createElement('div');
                      h.className = 'handle'; h.dataset.pos = pos; h.style.position='absolute'; h.style.width='10px'; h.style.height='10px'; h.style.background='#2563eb'; h.style.border='2px solid #fff'; h.style.borderRadius='2px'; h.style.boxSizing='border-box'; h.style.cursor=cursors[pos];
                      const W = (r.w * state.img.naturalW), H = (r.h * state.img.naturalH);
                      const off = -5;
                      const map = {
                        nw: {left: off, top: off},
                        n:  {left: W/2-5, top: off},
                        ne: {left: W-5, top: off},
                        e:  {left: W-5, top: H/2-5},
                        se: {left: W-5, top: H-5},
                        s:  {left: W/2-5, top: H-5},
                        sw: {left: off, top: H-5},
                        w:  {left: off, top: H/2-5},
                      };
                      const p = map[pos]; h.style.left = p.left+'px'; h.style.top=p.top+'px';
                      el.appendChild(h);
                    }
                  }
                  overlay.appendChild(el);
                }
              }

              btnSave.onclick = async () => { await doSave(); };

              async function loadApi(id) {
                try {
                  const r = await fetch(`/builder/apis/${id}`);
                  if (!r.ok) throw new Error('fetch');
                  const doc = await r.json();
                  state.selected = id;
                  state.rects = Array.isArray(doc.rects) ? doc.rects : [];
                  titleInp.value = doc.name || 'Untitled API';
                  hint.style.display = 'none';
                  stage.style.display = 'block';
                  img.src = doc.image_url;
                  // Wait image load to set sizes
                  await new Promise((res) => { if (img.complete) res(); else img.onload = res; });
                  state.img.naturalW = img.naturalWidth; state.img.naturalH = img.naturalHeight;
                  // Reset zoom to fit container
                  try {
                    const wrap = document.getElementById('workspace');
                    const pad = 24;
                    const fit = Math.min( (wrap.clientWidth - pad) / state.img.naturalW, (wrap.clientHeight - pad) / state.img.naturalH ) || 1;
                    const pct = Math.max(0.2, Math.min(3, fit));
                    state.zoom = pct; zoomRange.value = String(Math.round(pct * 100)); zoomLabel.textContent = `${Math.round(pct*100)}%`;
                  } catch {}
                  centerStage();
                  renderRects();
                  selectRect('');
                  markDirty(false);
                } catch {
                  console.warn('Failed to load API');
                }
                renderList();
              }

              // Toolbar
              modeSelect.onclick = () => setMode('select');
              modeDraw.onclick = () => setMode('draw');
              setMode('select');

              zoomRange.oninput = () => {
                const v = Math.max(20, Math.min(300, +zoomRange.value || 100));
                zoomLabel.textContent = `${v}%`;
                state.zoom = v / 100;
                applyTransform();
                renderRects();
              };

              // Title changes mark dirty; save is explicit via button
              titleInp.oninput = () => { if (state.selected) markDirty(true); };

              // Drawing & Panning
              let drawing = null; // {startX,startY,el}
              let panning = null; // {sx,sy,px,py}
              let moving = null; // {id, startX, startY, rx, ry, rw, rh}
              let resizing = null; // {id, pos, startX, startY, rx, ry, rw, rh}

              const workspace = document.getElementById('workspace');
              workspace.addEventListener('mousedown', (ev) => {
                if (state.mode !== 'select') return;
                // ignore rectangle body and resize handles
                const isRect = ev.target && ev.target.closest && ev.target.closest('.rect');
                const isHandle = ev.target && ev.target.closest && ev.target.closest('.handle');
                if (isRect || isHandle) return;
                panning = { sx: ev.clientX, sy: ev.clientY, px: state.panX, py: state.panY };
                workspace.classList.add('grabbing');
                ev.preventDefault();
              });
              window.addEventListener('mousemove', (ev) => {
                if (!panning) return;
                state.panX = panning.px + (ev.clientX - panning.sx);
                state.panY = panning.py + (ev.clientY - panning.sy);
                applyTransform();
              });
              window.addEventListener('mouseup', () => {
                if (panning) { panning = null; workspace.classList.remove('grabbing'); }
              });
              overlay.addEventListener('mousedown', (ev) => {
                const box = img.getBoundingClientRect();
                const px = ev.clientX - box.left; const py = ev.clientY - box.top;
                const gx = percentClamp(px / (state.img.naturalW * state.zoom));
                const gy = percentClamp(py / (state.img.naturalH * state.zoom));
                // Resize handle?
                const h = ev.target.closest ? ev.target.closest('.handle') : null;
                const rectEl = ev.target.classList && ev.target.classList.contains('rect') ? ev.target : (h ? h.parentElement : null);
                if (state.mode === 'select' && h && rectEl) {
                  const id = rectEl.dataset.id; const r = state.rects.find(x=>x.id===id); if(!r) return;
                  resizing = { id, pos: h.dataset.pos, startX: gx, startY: gy, rx: r.x, ry: r.y, rw: r.w, rh: r.h };
                  ev.preventDefault(); ev.stopPropagation(); return;
                }
                if (state.mode === 'select' && rectEl) {
                  const id = rectEl.dataset.id; const r = state.rects.find(x=>x.id===id); if(!r) return;
                  selectRect(id);
                  moving = { id, startX: gx, startY: gy, rx: r.x, ry: r.y, rw: r.w, rh: r.h };
                  ev.preventDefault(); ev.stopPropagation(); return;
                }
                if (state.mode !== 'draw') return;
                const el = document.createElement('div'); el.className = 'rect selected'; overlay.appendChild(el);
                drawing = { startX: gx, startY: gy, el };
                overlay.dataset.selected = '';
                for (const r of overlay.querySelectorAll('.rect')) r.classList.remove('selected');
                ev.preventDefault(); ev.stopPropagation();
              });
              window.addEventListener('mousemove', (ev) => {
                const box = img.getBoundingClientRect();
                const px = ev.clientX - box.left; const py = ev.clientY - box.top;
                const gx = percentClamp(px / (state.img.naturalW * state.zoom));
                const gy = percentClamp(py / (state.img.naturalH * state.zoom));
                if (drawing) {
                  const x = Math.min(drawing.startX, gx), y = Math.min(drawing.startY, gy);
                  const w = Math.abs(gx - drawing.startX), h = Math.abs(gy - drawing.startY);
                  drawing.el.style.left = (x * state.img.naturalW) + 'px';
                  drawing.el.style.top  = (y * state.img.naturalH) + 'px';
                  drawing.el.style.width  = (w * state.img.naturalW) + 'px';
                  drawing.el.style.height = (h * state.img.naturalH) + 'px';
                  return;
                }
                if (moving) {
                  const r = state.rects.find(x=>x.id===moving.id); if(!r) return;
                  let dx = gx - moving.startX, dy = gy - moving.startY;
                  r.x = percentClamp(moving.rx + dx); r.y = percentClamp(moving.ry + dy);
                  // clamp so rect stays inside
                  r.x = Math.min(r.x, 1 - r.w); r.y = Math.min(r.y, 1 - r.h);
                  renderRects();
                  // update inspector fields
                  rectX.value = Math.round(r.x * state.img.naturalW);
                  rectY.value = Math.round(r.y * state.img.naturalH);
                  return;
                }
                if (resizing) {
                  const r = state.rects.find(x=>x.id===resizing.id); if(!r) return;
                  let x = resizing.rx, y = resizing.ry, w = resizing.rw, h = resizing.rh;
                  const pos = resizing.pos;
                  const min = 0.002;
                  if (pos.includes('e')) { w = Math.max(min, Math.min(1 - x, resizing.rw + (gx - resizing.startX))); }
                  if (pos.includes('s')) { h = Math.max(min, Math.min(1 - y, resizing.rh + (gy - resizing.startY))); }
                  if (pos.includes('w')) { const nx = Math.max(0, Math.min(resizing.rx + (gx - resizing.startX), resizing.rx + resizing.rw - min)); w = resizing.rx + resizing.rw - nx; x = nx; }
                  if (pos.includes('n')) { const ny = Math.max(0, Math.min(resizing.ry + (gy - resizing.startY), resizing.ry + resizing.rh - min)); h = resizing.ry + resizing.rh - ny; y = ny; }
                  r.x = x; r.y = y; r.w = w; r.h = h;
                  renderRects();
                  rectX.value = Math.round(r.x * state.img.naturalW);
                  rectY.value = Math.round(r.y * state.img.naturalH);
                  rectW.value = Math.round(r.w * state.img.naturalW);
                  rectH.value = Math.round(r.h * state.img.naturalH);
                  return;
                }
              });
              window.addEventListener('mouseup', (ev) => {
                if (drawing) {
                  const box = img.getBoundingClientRect();
                  const px = ev.clientX - box.left; const py = ev.clientY - box.top;
                  const x2 = percentClamp(px / (state.img.naturalW * state.zoom));
                  const y2 = percentClamp(py / (state.img.naturalH * state.zoom));
                  const x = Math.min(drawing.startX, x2), y = Math.min(drawing.startY, y2);
                  const w = Math.abs(x2 - drawing.startX), h = Math.abs(y2 - drawing.startY);
                  if (w > 0.002 && h > 0.002) {
                    const id = 'r-' + Math.random().toString(36).slice(2, 9);
                    const rect = { id, name: '', x, y, w, h, extract_text: true };
                    state.rects.push(rect);
                    selectRect(id);
                    markDirty(true);
                  } else {
                    try { drawing.el.remove(); } catch {}
                  }
                  drawing = null; renderRects(); return;
                }
                if (moving) { moving = null; markDirty(true); return; }
                if (resizing) { resizing = null; markDirty(true); return; }
              });

              overlay.addEventListener('click', (ev) => {
                if (state.mode === 'draw') return; // drawing handles its own
                if (ev.target === overlay) selectRect('');
              });

              rectName.oninput = () => {
                const id = overlay.dataset.selected || '';
                const r = state.rects.find(x => x.id === id);
                if (!r) return; r.name = rectName.value || ''; markDirty(true);
              };
              rectExtract.onchange = () => {
                const id = overlay.dataset.selected || '';
                const r = state.rects.find(x => x.id === id);
                if (!r) return; r.extract_text = !!rectExtract.checked; markDirty(true);
              };
              function clamp(v, lo, hi){ return Math.max(lo, Math.min(hi, v)); }
              function applyRectEdits(){
                const id = overlay.dataset.selected || '';
                const r = state.rects.find(x => x.id === id);
                if (!r) return;
                const W = state.img.naturalW, H = state.img.naturalH;
                let x = +rectX.value || 0, y = +rectY.value || 0, w = +rectW.value || 1, h = +rectH.value || 1;
                x = clamp(x, 0, W-1); y = clamp(y, 0, H-1);
                w = clamp(w, 1, W - x); h = clamp(h, 1, H - y);
                r.x = x / W; r.y = y / H; r.w = w / W; r.h = h / H;
                rectX.value = Math.round(x); rectY.value = Math.round(y); rectW.value = Math.round(w); rectH.value = Math.round(h);
                renderRects(); markDirty(true);
              }
              rectX.onchange = rectY.onchange = rectW.onchange = rectH.onchange = applyRectEdits;
              btnDelRect.onclick = () => {
                const id = overlay.dataset.selected || '';
                if (!id) return;
                state.rects = state.rects.filter(x => x.id !== id);
                selectRect(''); renderRects(); markDirty(true);
              };

              // New API flow
              function showCreate() {
                createArea.style.display = 'block';
                hint.style.display = 'none';
                stage.style.display = 'none';
              }
              function hideCreate() {
                createArea.style.display = 'none';
                if (!state.selected) hint.style.display = 'block';
              }
              btnNew.onclick = async () => {
                if (state.dirty) {
                  if (confirm('You have unsaved changes. Save before creating a new API?')) { const ok = await doSave(); if (!ok) return; }
                  else { markDirty(false); }
                }
                showCreate();
              };
              btnCancelCreate.onclick = () => { hideCreate(); };
              btnCreateFromUpload.onclick = async () => {
                const inp = apiImageInput();
                if (!inp || !inp.files || !inp.files[0]) { alert('Please choose an image'); return; }
                const fd = new FormData(); fd.append('image', inp.files[0]); fd.append('name', titleInp.value || 'Untitled API');
                try {
                  const r = await fetch('/builder/apis', { method: 'POST', body: fd });
                  if (!r.ok) throw new Error('upload');
                  const doc = await r.json();
                  hideCreate();
                  await refreshList(doc.id);
                  await loadApi(doc.id);
                  setMode('draw');
                } catch (e) { alert('Failed to create API'); }
              };

              // Auto-create when a file is picked (no need to press Create)
              (function hookAutoCreate(){
                try {
                  const el = document.getElementById('file-new-api-upload-up');
                  if (!el || el._boundAutoCreate) return;
                  el.addEventListener('change', () => { if (el.files && el.files[0]) btnCreateFromUpload.click(); });
                  el._boundAutoCreate = true;
                } catch {}
              })();

              // Init
              await refreshList();
              clearSelection();
            }
            """,
            outputs=[],
        )

        # Inject header at end to ensure styles loaded
        def _header(request: gr.Request):
            return render_header(path="/app", request=request)
        app.load(_header, outputs=[hdr])

    return app
