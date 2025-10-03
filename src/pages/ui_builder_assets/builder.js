// Client-side logic powering the interactive API builder workspace.

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
    loaded: false,
    deleting: false,
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
  const modeSplit = document.getElementById('mode-split');
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
  const sepsList = document.getElementById('seps-list');
  const btnInspectorClose = document.getElementById('inspector-close');
  const btnUndo = document.getElementById('btn-undo');
  const btnRedo = document.getElementById('btn-redo');
  const btnDelete = document.getElementById('btn-delete-api');
  if (btnDelete) btnDelete.disabled = true;
  const endpointInp = document.getElementById('api-endpoint');
  const copyEndpointBtn = document.getElementById('btn-copy-endpoint');
  const keyHeaderLabel = document.getElementById('api-key-header');
  const pythonToggle = document.getElementById('toggle-python-example');
  const pythonSample = document.getElementById('python-example-block');
  const copyPythonBtn = document.getElementById('btn-copy-python-example');
  const pythonCodeBlock = pythonSample ? pythonSample.querySelector('code') : null;
  const origin = (typeof window !== 'undefined' && window.location && window.location.origin) ? window.location.origin : '';

  function syncBaseAccess(doc) {
    if (!doc) return;
    doc._baseAccessUrl = doc.access_url || doc._baseAccessUrl || '';
  }

  function buildAccessPreview(baseUrl, name) {
    if (!baseUrl) return '';
    const trimmedName = (name || '').trim();
    const effectiveName = trimmedName || 'Untitled API';
    let core = baseUrl;
    let suffix = '';
    const hashIdx = core.indexOf('#');
    if (hashIdx >= 0) {
      suffix = core.slice(hashIdx);
      core = core.slice(0, hashIdx);
    }
    let query = '';
    const qIdx = core.indexOf('?');
    if (qIdx >= 0) {
      query = core.slice(qIdx);
      core = core.slice(0, qIdx);
    }
    const slashIdx = core.lastIndexOf('/');
    if (slashIdx < 0) {
      return `${effectiveName}${query}${suffix}`;
    }
    const prefix = core.slice(0, slashIdx + 1);
    return `${prefix}${effectiveName}${query}${suffix}`;
  }

  function markDirty(d=true){
    state.dirty = !!d;
    const cur = state.apis.find(a=>a.id===state.selected);
    const isPending = !!(cur && cur.pending);
    let cleared = false;
    if (!state.dirty && cur && cur._pendingName) {
      delete cur._pendingName;
      cleared = true;
      updateEndpoint(cur);
    }
    btnSave.disabled = !state.dirty || !state.selected || isPending;
    if (btnDelete) {
      const canDelete = !!(state.selected && !isPending && !state.deleting);
      btnDelete.disabled = !canDelete;
    }
    if (cleared) renderList();
  }

  function updateEndpoint(doc) {
    if (!endpointInp) return;
    if (doc && doc.access_url) {
      let href = doc.access_url;
      try {
        href = new URL(doc.access_url, origin || (typeof window !== 'undefined' ? window.location.href : '')).toString();
      } catch {}
      endpointInp.value = href;
      if (copyEndpointBtn) copyEndpointBtn.disabled = false;
    } else {
      endpointInp.value = 'Select an API to view its link';
      if (copyEndpointBtn) copyEndpointBtn.disabled = true;
    }
  }

  async function copyToClipboard(text) {
    if (!text) return false;
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {}
    try {
      const temp = document.createElement('textarea');
      temp.value = text;
      temp.style.position = 'fixed';
      temp.style.opacity = '0';
      document.body.appendChild(temp);
      temp.focus();
      temp.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(temp);
      return ok;
    } catch {
      return false;
    }
  }

  function flashButton(btn) {
    if (!btn) return;
    const hasIcon = !!btn.querySelector('svg');
    if (hasIcon) {
      const prevTitle = btn.dataset.prevTitle || btn.title || 'Copy';
      btn.dataset.prevTitle = prevTitle;
      btn.title = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.classList.remove('copied');
        btn.title = btn.dataset.prevTitle || prevTitle;
      }, 1500);
      return;
    }
    const prev = btn.dataset.prevLabel || btn.textContent || 'Copy';
    btn.dataset.prevLabel = prev;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = btn.dataset.prevLabel || prev; }, 1500);
  }
  if (keyHeaderLabel) keyHeaderLabel.textContent = 'API-KEY';

  // --- Simple history (rectangles only)
  const history = { undo: [], redo: [] };
  const cloneRects = () => JSON.parse(JSON.stringify(state.rects||[]));
  let keyNudgeActive = false;
  function pushHistory(){ history.undo.push(cloneRects()); history.redo.length = 0; }
  function applyRects(rects){ state.rects = JSON.parse(JSON.stringify(rects||[])); renderRects(); const cur = state.rects.find(x=>x.id===overlay.dataset.selected); try{ renderSepsInspector(cur); }catch{} markDirty(true); }
  function undo(){ if(!history.undo.length) return; history.redo.push(cloneRects()); const prev = history.undo.pop(); applyRects(prev); }
  function redo(){ if(!history.redo.length) return; history.undo.push(cloneRects()); const next = history.redo.pop(); applyRects(next); }

  async function deleteSelectedApi() {
    if (state.deleting || !state.selected) return;
    const doc = state.apis.find(a => a.id === state.selected);
    if (!doc || doc.pending) return;
    const hasName = (doc.name || '').trim();
    const displayName = hasName ? `"${hasName}"` : 'this API';
    const extra = state.dirty ? '\nUnsaved changes will be lost.' : '';
    const confirmMsg = `Delete ${displayName}? This action cannot be undone.${extra}`;
    if (!(typeof window !== 'undefined' && window.confirm && window.confirm(confirmMsg))) return;

    state.deleting = true;
    markDirty(state.dirty);
    try {
      const resp = await fetch(`/builder/apis/${doc.id}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error('delete');
      state.apis = state.apis.filter(a => a.id !== doc.id);
      state.selected = null;
      state.rects = [];
      state.img.naturalW = 0; state.img.naturalH = 0;
      history.undo = []; history.redo = [];
      clearSelection({ skipRender: true });
      renderRects();
      if (hint) hint.style.display = 'block';
      if (stage) stage.style.display = 'none';
      if (img) img.src = '';
      if (createArea) createArea.style.display = 'none';
      if (titleInp) titleInp.value = '';
      updateEndpoint(null);
      markDirty(false);
      renderList();
    } catch (err) {
      console.error(err);
      if (typeof window !== 'undefined' && window.alert) {
        window.alert('Failed to delete API. Please try again.');
      }
    } finally {
      state.deleting = false;
      markDirty(state.dirty);
    }
  }

  async function doSave(){
    if (!state.selected) return true;
    try{
      // Convert rects to pixel units before sending
      const W = state.img.naturalW, H = state.img.naturalH;
      const pixelRects = (state.rects || []).map(r => ({
        ...r,
        x: Math.round(r.x * W),
        y: Math.round(r.y * H),
        w: Math.round(r.w * W),
        h: Math.round(r.h * H),
        seps: Array.isArray(r.seps) ? r.seps.map(rel => Math.round(rel * r.h * H)) : [],
        extract_text: !!r.extract_text
      }));
      const r = await fetch(`/builder/apis/${state.selected}`,{
        method:'PUT', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ name: titleInp.value || 'Untitled API', rects: pixelRects })
      });
      if (!r.ok) throw new Error('save');
      const doc = await r.json();
      syncBaseAccess(doc);
      if (doc._pendingName) delete doc._pendingName;
      // Update local cache entry
      const i = state.apis.findIndex(a=>a.id===doc.id);
      if (i>=0) state.apis[i] = doc; else state.apis.unshift(doc);
      if (doc.id === state.selected) updateEndpoint(doc);
      renderList();
      markDirty(false);
      return true;
    }catch{ return false; }
  }

  window.addEventListener('beforeunload', (e)=>{ if(state.dirty){ e.preventDefault(); e.returnValue=''; return ''; } });

  if (btnInspectorClose) {
    btnInspectorClose.onclick = () => { clearSelection(); };
  }
  if (btnUndo) btnUndo.onclick = () => undo();
  if (btnRedo) btnRedo.onclick = () => redo();
  if (btnDelete) btnDelete.onclick = () => { deleteSelectedApi(); };
  window.addEventListener('keydown', (e) => {
    const z = (e.key === 'z' || e.key === 'Z');
    const y = (e.key === 'y' || e.key === 'Y');
    if ((e.ctrlKey || e.metaKey) && z) { e.preventDefault(); undo(); }
    else if ((e.ctrlKey || e.metaKey) && y) { e.preventDefault(); redo(); }
    else if (!e.ctrlKey && !e.metaKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      if (state.mode !== 'select' || !state.selected) return;
      const rectId = overlay.dataset.selected || '';
      if (!rectId) return;
      const active = document.activeElement;
      const tag = (active && active.tagName) ? active.tagName.toLowerCase() : '';
      const isEditing = !!(active && (active.isContentEditable || ['input','textarea','select'].includes(tag)));
      if (isEditing) return;
      const rect = state.rects.find(r => r.id === rectId);
      if (!rect) return;
      const step = e.shiftKey ? 10 : 1;
      let dx = 0, dy = 0;
      if (e.key === 'ArrowLeft') dx = -step;
      else if (e.key === 'ArrowRight') dx = step;
      else if (e.key === 'ArrowUp') dy = -step;
      else if (e.key === 'ArrowDown') dy = step;
      const canMove = nudgeSelectedRect(rect, dx, dy, { preview: true });
      if (!canMove) { e.preventDefault(); return; }
      if (!keyNudgeActive) {
        try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
        keyNudgeActive = true;
      }
      const moved = nudgeSelectedRect(rect, dx, dy);
      if (moved) {
        e.preventDefault();
        markDirty(true);
      }
    }
  });

  window.addEventListener('keyup', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      keyNudgeActive = false;
    }
  });

  if (copyEndpointBtn) {
    copyEndpointBtn.disabled = true;
    copyEndpointBtn.onclick = async () => {
      if (copyEndpointBtn.disabled) return;
      const ok = await copyToClipboard(endpointInp ? endpointInp.value : '');
      if (ok) flashButton(copyEndpointBtn);
      else window.alert('Unable to copy link automatically. Please copy it manually.');
    };
  }

  if (pythonToggle && pythonSample) {
    pythonToggle.addEventListener('click', () => {
      const hidden = pythonSample.classList.toggle('hidden');
      pythonToggle.setAttribute('aria-expanded', hidden ? 'false' : 'true');
    });
  }

  if (copyPythonBtn && pythonCodeBlock) {
    copyPythonBtn.addEventListener('click', async () => {
      const sample = pythonCodeBlock.textContent || '';
      if (!sample.trim()) return;
      const ok = await copyToClipboard(sample);
      if (!ok) {
        if (typeof window !== 'undefined' && window.alert) {
          window.alert('Unable to copy example automatically. Please copy it manually.');
        }
        return;
      }
      flashButton(copyPythonBtn);
    });
  }


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
    if (modeSplit) modeSplit.classList.toggle('active', m === 'split');
    const ws = document.getElementById('workspace');
    const ov = document.getElementById('overlay');
    if (ws) { ws.classList.toggle('mode-select', m === 'select'); ws.classList.toggle('mode-draw', m === 'draw'); ws.classList.toggle('mode-split', m === 'split'); }
    if (ov) { ov.classList.toggle('mode-draw', m === 'draw'); ov.classList.toggle('mode-split', m === 'split'); }
  }

  function setInspectorOpen(open) {
    inspector.classList.toggle('open', !!open);
    center.classList.toggle('inspector-open', !!open);
  }

  function percentClamp(v) { return Math.max(0, Math.min(1, v)); }

  function nudgeSelectedRect(rect, dx, dy, { preview = false } = {}) {
    if (!rect) return false;
    const W = state.img.naturalW;
    const H = state.img.naturalH;
    if (!W || !H) return false;
    const curX = Math.round(rect.x * W);
    const curY = Math.round(rect.y * H);
    const widthPx = Math.max(1, Math.round(rect.w * W));
    const heightPx = Math.max(1, Math.round(rect.h * H));
    const maxX = Math.max(0, W - widthPx);
    const maxY = Math.max(0, H - heightPx);
    const nextX = clamp(curX + dx, 0, maxX);
    const nextY = clamp(curY + dy, 0, maxY);
    if (nextX === curX && nextY === curY) return false;
    if (preview) return true;
    rect.x = nextX / W;
    rect.y = nextY / H;
    if (overlay.dataset.selected === rect.id) {
      if (rectX) rectX.value = String(nextX);
      if (rectY) rectY.value = String(nextY);
    }
    renderRects();
    return true;
  }

  function renderList() {
    listEl.innerHTML = '';
    for (const it of state.apis) {
      const li = document.createElement('li');
      li.className = 'sidebar-item' + (it.id === state.selected ? ' active' : '') + (it.pending ? ' pending' : '');
      li.dataset.id = it.id;
      const thumb = document.createElement('div'); thumb.className = 'thumb';
      const img = document.createElement('img'); img.src = it.image_url; thumb.appendChild(img);
      const labelText = (it._pendingName ?? it.name) || 'Untitled';
      const label = document.createElement('div'); label.textContent = labelText;
      li.appendChild(thumb); li.appendChild(label);
      li.onclick = async () => {
        if (it.pending) return; // ignore clicks while uploading
        if (state.dirty) {
          if (confirm('You have unsaved changes. Save before switching?')) { const ok = await doSave(); if (!ok) return; }
          else { markDirty(false); }
        }
        await loadApi(it.id);
      };
      listEl.appendChild(li);
    }
  }

  async function fetchAll() {
    try {
      const r = await fetch('/builder/apis');
      const j = await r.json();
      state.apis = Array.isArray(j) ? j : [];
      state.apis.forEach(syncBaseAccess);
      state.loaded = true;
    } catch { state.apis = []; state.loaded = true; }
    if (state.selected && !state.apis.find(a=>a.id===state.selected)) state.selected = null;
    renderList();
    if (state.selected) {
      const current = state.apis.find(a => a.id === state.selected);
      updateEndpoint(current);
    } else {
      updateEndpoint(null);
    }
  }

  function clearSelection({ skipRender = false } = {}) {
    selPanel.style.display = 'none';
    rectName.value = '';
    rectExtract.checked = true;
    for (const el of overlay.querySelectorAll('.rect')) el.classList.remove('selected');
    overlay.dataset.selected = '';
    keyNudgeActive = false;
    setInspectorOpen(false);
    if (!skipRender) renderRects();
  }

  function selectRect(id) {
    overlay.dataset.selected = id || '';
    keyNudgeActive = false;
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
      try { renderSepsInspector(r); } catch {}
    } else {
      clearSelection({ skipRender: true });
    }
    renderRects();
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
      el.onclick = (ev) => { ev.stopPropagation(); /* keep current mode */ selectRect(r.id); };
      // Render horizontal separators
      const seps = Array.isArray(r.seps) ? r.seps : [];
      for (let i=0;i<seps.length;i++){
        const yRel = Math.max(0, Math.min(1, +seps[i] || 0));
        const s = document.createElement('div'); s.className = 'sep-line'; s.dataset.idx = String(i);
        s.style.top = (yRel * (r.h * state.img.naturalH)) + 'px';
        el.appendChild(s);
      }
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

function renderSepsInspector(r){
  if (!sepsList) return;
  sepsList.innerHTML = '';
  if (!r) return;
  const H = state.img.naturalH;
  const seps = Array.isArray(r.seps) ? r.seps : [];
  seps.forEach((rel, idx) => {
    const row = document.createElement('div'); row.className = 'sep-item';
    const px = Math.round((rel||0)*(r.h*H));
    row.innerHTML = `
      <input type="number" class="sep-px" data-idx="${idx}" value="${px}" min="0" step="1" />
      <button class="sep-del" data-idx="${idx}" title="Remove">×</button>
    `;
    sepsList.appendChild(row);
  });
  sepsList.oninput = (ev) => {
    const cur = state.rects.find(x=>x.id===overlay.dataset.selected); if (!cur) return;
    const idx = +ev.target.getAttribute('data-idx'); if (Number.isNaN(idx)) return;
    if (!Array.isArray(cur.seps)) cur.seps = [];
    if (ev.target.classList.contains('sep-px')){
      const Ht = Math.max(1, cur.h*H);
      let v = Math.max(0, Math.min(Ht, +ev.target.value||0));
      cur.seps[idx] = v / Ht;
    }
    renderRects(); markDirty(true);
  };
  sepsList.onclick = (ev) => {
    if (!ev.target.classList.contains('sep-del')) return;
    const cur = state.rects.find(x=>x.id===overlay.dataset.selected); if (!cur) return;
    const idx = +ev.target.getAttribute('data-idx'); if (Number.isNaN(idx)) return;
    if (Array.isArray(cur.seps)) cur.seps.splice(idx,1);
    renderSepsInspector(cur); renderRects(); markDirty(true);
  };
}

  btnSave.onclick = async () => { await doSave(); };

  async function loadApi(id) {
    const doc = state.apis.find(a => a.id === id);
    if (!doc) { console.warn('API not found in cache'); return; }
    syncBaseAccess(doc);
    if (doc._pendingName) delete doc._pendingName;
    state.selected = id;
    // Wait image load to set sizes without altering user zoom
    hint.style.display = 'none';
    hideCreate();
    stage.style.display = 'block';
    img.src = doc.image_url;
    await new Promise((res) => { if (img.complete) res(); else img.onload = res; });
    state.img.naturalW = img.naturalWidth; state.img.naturalH = img.naturalHeight;
    // Convert pixel rects to normalized rects for display
    const W = state.img.naturalW, H = state.img.naturalH;
    state.rects = Array.isArray(doc.rects) ? doc.rects.map(r => ({
      ...r,
      x: r.x / W,
      y: r.y / H,
      w: r.w / W,
      h: r.h / H,
      seps: Array.isArray(r.seps) ? r.seps.map(s => (r.h ? s / r.h : 0) / H) : [],
      extract_text: r.extract_text !== false       // default TRUE ✅
      })) : [];
    titleInp.value = doc.name || 'Untitled API';
    updateEndpoint(doc);
    if (!state._hasInteracted) {
      try {
        const wrap = document.getElementById('workspace');
        const pad = 24;
        const fit = Math.min( (wrap.clientWidth - pad) / W, (wrap.clientHeight - pad) / H ) || 1;
        const pct = Math.max(0.2, Math.min(3, fit));
        state.zoom = pct; zoomRange.value = String(Math.round(pct * 100)); zoomLabel.textContent = `${Math.round(pct*100)}%`;
      } catch {}
    }
    centerStage();
    renderRects();
    selectRect('');
    markDirty(false);
    // Seed history so Undo works from first edit
    try { history.undo = []; history.redo = []; history.undo.push(cloneRects()); } catch {}
    renderList();
  }

  async function initFromCurrentImage({fit=true}={}){
    await new Promise((res) => { if (img.complete) res(); else img.onload = res; });
    state.img.naturalW = img.naturalWidth; state.img.naturalH = img.naturalHeight;
    if (fit) {
      try {
        const wrap = document.getElementById('workspace');
        const pad = 24;
        const fitZ = Math.min( (wrap.clientWidth - pad) / state.img.naturalW, (wrap.clientHeight - pad) / state.img.naturalH ) || 1;
        const pct = Math.max(0.2, Math.min(3, fitZ));
        state.zoom = pct; zoomRange.value = String(Math.round(pct * 100)); zoomLabel.textContent = `${Math.round(pct*100)}%`;
      } catch {}
    }
    centerStage();
    renderRects();
  }

  // Toolbar
  modeSelect.onclick = () => setMode('select');
  modeDraw.onclick = () => setMode('draw');
  if (modeSplit) modeSplit.onclick = () => setMode('split');
  setMode('draw');

  function updateZoomUI(){
    try {
      const v = Math.round(state.zoom * 100);
      zoomRange.value = String(v);
      zoomLabel.textContent = `${v}%`;
    } catch {}
  }

  function setZoom(newZoom, anchorX=null, anchorY=null){
    const minZ = 0.2, maxZ = 5;
    newZoom = Math.max(minZ, Math.min(maxZ, +newZoom || 1));
    const rect = workspace.getBoundingClientRect();
    const px = (anchorX == null ? rect.width/2 : anchorX);
    const py = (anchorY == null ? rect.height/2 : anchorY);
    // Keep the point under the cursor stable while zooming
    const ix = (px - state.panX) / (state.zoom || 1);
    const iy = (py - state.panY) / (state.zoom || 1);
    state.zoom = newZoom;
    state.panX = Math.floor(px - ix * state.zoom);
    state.panY = Math.floor(py - iy * state.zoom);
    applyTransform();
    updateZoomUI();
    renderRects();
  }

  zoomRange.oninput = () => {
    const v = Math.max(20, Math.min(300, +zoomRange.value || 100));
    setZoom(v/100);
  };

  // Title changes mark dirty; preview endpoint updates live
  titleInp.oninput = () => {
    if (!state.selected) return;
    markDirty(true);
    const doc = state.apis.find(a => a.id === state.selected);
    if (!doc) return;
    const previewName = (titleInp.value || '').trim() || 'Untitled API';
    doc._pendingName = previewName;
    syncBaseAccess(doc);
    const baseUrl = doc._baseAccessUrl || doc.access_url || '';
    if (baseUrl) {
      const previewUrl = buildAccessPreview(baseUrl, previewName);
      updateEndpoint({ access_url: previewUrl });
    } else {
      updateEndpoint(null);
    }
    renderList();
  };

  // Drawing & Panning
  let drawing = null; // {startX,startY,el}
  let panning = null; // {sx,sy,px,py}
  let moving = null; // {id, startX, startY, rx, ry, rw, rh}
  let resizing = null; // {id, pos, startX, startY, rx, ry, rw, rh}

  const workspace = document.getElementById('workspace');
  // Wheel / trackpad zoom (including pinch on many browsers)
  workspace.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    const rect = workspace.getBoundingClientRect();
    const px = ev.clientX - rect.left; const py = ev.clientY - rect.top;
    const factor = Math.exp(-(ev.deltaY || 0) * 0.001);
    setZoom(state.zoom * factor, px, py);
  }, { passive: false });

  // Safari pinch gesture fallback
  let _pinch = null;
  workspace.addEventListener('gesturestart', (ev) => { ev.preventDefault(); _pinch = { z: state.zoom }; }, { passive: false });
  workspace.addEventListener('gesturechange', (ev) => {
    ev.preventDefault();
    const rect = workspace.getBoundingClientRect();
    setZoom((_pinch?.z || state.zoom) * (ev.scale || 1), rect.width/2, rect.height/2);
  }, { passive: false });
  workspace.addEventListener('gestureend', () => { _pinch = null; }, { passive: true });
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
  // Double-click on a rectangle to start moving it (even in draw mode)
  overlay.addEventListener('dblclick', (ev) => {
    const rectEl = ev.target.closest && ev.target.closest('.rect'); if (!rectEl) return;
    const id = rectEl.dataset.id; const r = state.rects.find(x=>x.id===id); if(!r) return;
    const box = img.getBoundingClientRect();
    const px = ev.clientX - box.left; const py = ev.clientY - box.top;
    const gx = percentClamp(px / (state.img.naturalW * state.zoom));
    const gy = percentClamp(py / (state.img.naturalH * state.zoom));
    history.undo.push(cloneRects()); history.redo.length = 0;
    selectRect(id);
    moving = { id, startX: gx, startY: gy, rx: r.x, ry: r.y, rw: r.w, rh: r.h, changed: false };
    ev.preventDefault(); ev.stopPropagation();
  });
  overlay.addEventListener('mousedown', (ev) => {
    const box = img.getBoundingClientRect();
    const px = ev.clientX - box.left; const py = ev.clientY - box.top;
    const gx = percentClamp(px / (state.img.naturalW * state.zoom));
    const gy = percentClamp(py / (state.img.naturalH * state.zoom));
    // Resize handle?
    const h = ev.target.closest ? ev.target.closest('.handle') : null;
    const sep = ev.target.closest ? ev.target.closest('.sep-line') : null;
    const rectEl = ev.target.classList && ev.target.classList.contains('rect') ? ev.target : (h ? h.parentElement : (sep ? sep.parentElement : null));
    if (state.mode === 'split' && rectEl && !h) {
      try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
      const id = rectEl.dataset.id; const r = state.rects.find(x=>x.id===id); if(!r) return;
      // Ensure this rect is selected and inspector is open
      if ((overlay.dataset.selected || '') !== id) {
        selectRect(id);
      }
      const rel = Math.max(0, Math.min(1, (gy - r.y) / Math.max(0.0001, r.h)));
      if (!Array.isArray(r.seps)) r.seps = [];
      r.seps.push(rel); r.seps.sort((a,b)=>a-b);
      renderRects();
      try { renderSepsInspector(r); } catch {}
      markDirty(true);
      ev.preventDefault(); ev.stopPropagation(); return;
    }
    if (h && rectEl) {
      try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
      const id = rectEl.dataset.id; const r = state.rects.find(x=>x.id===id); if(!r) return;
      resizing = { id, pos: h.dataset.pos, startX: gx, startY: gy, rx: r.x, ry: r.y, rw: r.w, rh: r.h, changed: false };
      ev.preventDefault(); ev.stopPropagation(); return;
    }
    if (state.mode === 'select' && rectEl) {
      try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
      const id = rectEl.dataset.id; const r = state.rects.find(x=>x.id===id); if(!r) return;
      selectRect(id);
      moving = { id, startX: gx, startY: gy, rx: r.x, ry: r.y, rw: r.w, rh: r.h, changed: false };
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
      if (ev.buttons !== undefined && (ev.buttons & 1) === 0) {
        const moved = !!moving.changed;
        moving = null;
        if (moved) markDirty(true);
        return;
      }
      const r = state.rects.find(x=>x.id===moving.id);
      if(!r) { moving = null; return; }
      const prevX = r.x, prevY = r.y;
      const dx = gx - moving.startX, dy = gy - moving.startY;
      let nextX = percentClamp(moving.rx + dx);
      let nextY = percentClamp(moving.ry + dy);
      // clamp so rect stays inside
      nextX = Math.min(nextX, 1 - r.w);
      nextY = Math.min(nextY, 1 - r.h);
      if (!moving.changed && (Math.abs(nextX - prevX) > 0.0001 || Math.abs(nextY - prevY) > 0.0001)) {
        moving.changed = true;
      }
      r.x = nextX; r.y = nextY;
      renderRects();
      // update inspector fields
      rectX.value = Math.round(r.x * state.img.naturalW);
      rectY.value = Math.round(r.y * state.img.naturalH);
      return;
    }
    if (resizing) {
      if (ev.buttons !== undefined && (ev.buttons & 1) === 0) {
        const resized = !!resizing.changed;
        resizing = null;
        if (resized) markDirty(true);
        return;
      }
      const r = state.rects.find(x=>x.id===resizing.id);
      if(!r) { resizing = null; return; }
      const prevX = r.x, prevY = r.y, prevW = r.w, prevH = r.h;
      let x = resizing.rx, y = resizing.ry, w = resizing.rw, h = resizing.rh;
      const pos = resizing.pos;
      const min = 0.002;
      if (pos.includes('e')) { w = Math.max(min, Math.min(1 - x, resizing.rw + (gx - resizing.startX))); }
      if (pos.includes('s')) { h = Math.max(min, Math.min(1 - y, resizing.rh + (gy - resizing.startY))); }
      if (pos.includes('w')) { const nx = Math.max(0, Math.min(resizing.rx + (gx - resizing.startX), resizing.rx + resizing.rw - min)); w = resizing.rx + resizing.rw - nx; x = nx; }
      if (pos.includes('n')) { const ny = Math.max(0, Math.min(resizing.ry + (gy - resizing.startY), resizing.ry + resizing.rh - min)); h = resizing.ry + resizing.rh - ny; y = ny; }
      if (!resizing.changed) {
        if (Math.abs(x - prevX) > 0.0001 || Math.abs(y - prevY) > 0.0001 || Math.abs(w - prevW) > 0.0001 || Math.abs(h - prevH) > 0.0001) {
          resizing.changed = true;
        }
      }
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
        try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
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
    if (moving) {
      const moved = !!moving.changed;
      moving = null;
      if (moved) markDirty(true);
      return;
    }
    if (resizing) {
      const resized = !!resizing.changed;
      resizing = null;
      if (resized) markDirty(true);
      return;
    }
  });

  // Shift+click inside selected rectangle to add a separator line
  overlay.addEventListener('click', (ev) => {
    if (state.mode === 'draw') return; // drawing handles its own
    const rectEl = ev.target.closest && ev.target.closest('.rect');
    if (ev.shiftKey && rectEl) {
      const id = rectEl.dataset.id; const r = state.rects.find(x=>x.id===id); if(!r) return;
      const box = rectEl.getBoundingClientRect();
      const rel = Math.max(0, Math.min(1, (ev.clientY - box.top) / Math.max(1, box.height)));
      if (!Array.isArray(r.seps)) r.seps = [];
      r.seps.push(rel); r.seps.sort((a,b)=>a-b);
      renderRects(); try { renderSepsInspector(r); } catch {} markDirty(true); ev.preventDefault(); return;
    }
    if (ev.target === overlay) selectRect('');
  });

  rectName.oninput = () => {
    try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
    const id = overlay.dataset.selected || '';
    const r = state.rects.find(x => x.id === id);
    if (!r) return; r.name = rectName.value || ''; markDirty(true);
  };
  rectExtract.onchange = () => {
    try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
    const id = overlay.dataset.selected || '';
    const r = state.rects.find(x => x.id === id);
    if (!r) return; r.extract_text = !!rectExtract.checked; markDirty(true);
  };
  
  function clamp(v, lo, hi){ return Math.max(lo, Math.min(hi, v)); }
  function applyRectEdits(){
    try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
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
    try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
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
    const file = inp.files[0];
    // Show instant local preview to avoid waiting for upload
    try {
      const localURL = URL.createObjectURL(file);
      hint.style.display = 'none';
      createArea.style.display = 'none';
      stage.style.display = 'block';
      img.src = localURL;
    } catch {}

    // Prepare stage for editing immediately
    state.selected = null; state.rects = [];
    updateEndpoint(null);
    await initFromCurrentImage({fit:true});
    selectRect('');
    markDirty(false);

    // Optimistically add a placeholder entry to the left panel
    const tmpId = 'pending-' + Math.random().toString(36).slice(2,8);
    const placeholder = { id: tmpId, name: 'New API', image_url: img.src, rects: [] , pending: true };
    state.apis.unshift(placeholder); renderList();
    state.selected = tmpId;

    const fd = new FormData(); fd.append('image', file);
    try {
      const r = await fetch('/builder/apis', { method: 'POST', body: fd });
      if (!r.ok) throw new Error('upload');
      const doc = await r.json();
      syncBaseAccess(doc);
      // Replace placeholder with real doc
      const idx = state.apis.findIndex(a=>a.id===tmpId);
      if (idx>=0) state.apis.splice(idx,1,doc); else state.apis.unshift(doc);
      renderList();
      // Keep current stage (local preview) to avoid recalibration; swap to signed URL silently
      img.src = doc.image_url || img.src;
      state.selected = doc.id;
      titleInp.value = doc.name || titleInp.value || 'New API';
      updateEndpoint(doc);
      hideCreate();
      // If user has drawn rectangles meanwhile, persist immediately
      if (state.rects && state.rects.length) { await doSave(); }
      markDirty(false);
      setMode('draw');
    } catch (e) {
      alert('Failed to create API');
      // Remove placeholder on failure
      const idx = state.apis.findIndex(a=>a.id===tmpId);
      if (idx>=0) { state.apis.splice(idx,1); renderList(); }
    }
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
  await fetchAll();
  clearSelection();
}
