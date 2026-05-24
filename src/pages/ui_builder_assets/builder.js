// Client-side logic powering the interactive API builder workspace.

async () => {
  const path = (typeof window !== 'undefined' && window.location && window.location.pathname) ? window.location.pathname : '';
  const inferredCollector = path.replace(/\/+$/, '').endsWith('/data-collector') || path.includes('/data-collector/');
  const defaultConfig = inferredCollector ? {
    apiPrefix: '/data-collector',
    pagePath: '/data-collector',
    sidebarTitle: 'Data collector',
    newButtonText: '+ Add files',
    titlePlaceholder: 'Sample name',
    uploadPrompt: 'Add images for the selected template',
    emptyHint: 'Choose a template, then add images to evaluate.',
    deleteLabel: 'image',
    showIntegration: false,
    enableCollectorControls: true,
    autoGenerateOnCreate: false,
  } : {
    apiPrefix: '/builder',
    pagePath: '/app',
    sidebarTitle: 'APIs',
    newButtonText: '+ New API',
    titlePlaceholder: 'API name',
    uploadPrompt: 'Upload an image to start a new API',
    emptyHint: 'Select an API from the left or create a new one.',
    deleteLabel: 'API',
    showIntegration: true,
    enableCollectorControls: false,
    autoGenerateOnCreate: false,
  };
  const injectedConfig = (typeof window !== 'undefined' && window.__BUILDER_CONFIG__) || {};
  const config = { ...defaultConfig, ...injectedConfig };
  const apiPrefix = String(config.apiPrefix || '/builder').replace(/\/+$/, '');
  const apiUrl = (path) => `${apiPrefix}${path.startsWith('/') ? path : `/${path}`}`;
  const deleteLabel = config.deleteLabel || 'API';

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
    evaluating: false,
    templates: [],
    selectedTemplate: null,
  };

  // Elements
  const listEl = document.getElementById('api-list');
  const btnNew = document.getElementById('btn-new-api');
  const sidebarTitle = document.querySelector('#sidebar h3');
  const createArea = document.getElementById('create-area');
  const createPrompt = document.getElementById('create-prompt');
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
  const rectNameSelect = document.getElementById('rect-name-select');
  const rectExtract = document.getElementById('rect-extract');
  const rectReference = document.getElementById('rect-reference');
  const rectNoise = document.getElementById('rect-noise');
  const rectX = document.getElementById('rect-x');
  const rectY = document.getElementById('rect-y');
  const rectW = document.getElementById('rect-w');
  const rectH = document.getElementById('rect-h');
  const rectTheta = document.getElementById('rect-theta');
  const btnDelRect = document.getElementById('btn-delete-rect');
  const inspector = document.getElementById('inspector');
  const center = document.getElementById('center');
  const btnSave = document.getElementById('btn-save');
  const sepsList = document.getElementById('seps-list');
  const btnInspectorClose = document.getElementById('inspector-close');
  const btnUndo = document.getElementById('btn-undo');
  const btnRedo = document.getElementById('btn-redo');
  const btnDelete = document.getElementById('btn-delete-api');
  const btnPrevImage = document.getElementById('btn-prev-image');
  const btnNextImage = document.getElementById('btn-next-image');
  const btnGenerateRects = document.getElementById('btn-generate-rects');
  const btnEvaluateAll = document.getElementById('btn-evaluate-all');
  const evaluateAllPopup = document.getElementById('evaluate-all-popup');
  const evaluateAllBackdrop = document.getElementById('evaluate-all-backdrop');
  const evaluateAllMode = document.getElementById('evaluate-all-mode');
  const btnEvaluateAllStart = document.getElementById('btn-evaluate-all-start');
  const btnEvaluateAllCancel = document.getElementById('btn-evaluate-all-cancel');
  const btnClearRects = document.getElementById('btn-clear-rects');
  const collectorStatus = document.getElementById('collector-status');
  const collectorTemplatePicker = document.getElementById('collector-template-picker');
  const collectorTemplateButton = document.getElementById('collector-template-button');
  const collectorTemplateMenu = document.getElementById('collector-template-menu');
  const collectorTemplateThumb = document.getElementById('collector-template-thumb');
  const collectorTemplateLabel = document.getElementById('collector-template-label');
  const collectorTemplateSelect = document.getElementById('collector-template-select');
  const integrationPanel = document.getElementById('integration-panel');
  if (btnDelete) btnDelete.disabled = true;
  const endpointInp = document.getElementById('api-endpoint');
  const copyEndpointBtn = document.getElementById('btn-copy-endpoint');
  const keyHeaderLabel = document.getElementById('api-key-header');
  const pythonToggle = document.getElementById('toggle-python-example');
  const pythonSample = document.getElementById('python-example-block');
  const copyPythonBtn = document.getElementById('btn-copy-python-example');
  const pythonCodeBlock = pythonSample ? pythonSample.querySelector('code') : null;
  const origin = (typeof window !== 'undefined' && window.location && window.location.origin) ? window.location.origin : '';

  document.body.classList.toggle('collector-enabled', !!config.enableCollectorControls);
  if (sidebarTitle && config.sidebarTitle) sidebarTitle.textContent = config.sidebarTitle;
  if (btnNew && config.newButtonText) btnNew.textContent = config.newButtonText;
  if (titleInp && config.titlePlaceholder) titleInp.placeholder = config.titlePlaceholder;
  if (createPrompt && config.uploadPrompt) createPrompt.textContent = config.uploadPrompt;
  if (hint && config.emptyHint) hint.textContent = config.emptyHint;
  if (integrationPanel && config.showIntegration === false) integrationPanel.classList.add('hidden');
  if (rectName && rectNameSelect) {
    if (config.enableCollectorControls) {
      rectName.style.display = 'none';
      rectNameSelect.style.display = '';
    } else {
      rectName.style.display = '';
      rectNameSelect.style.display = 'none';
    }
  }

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
    setCollectorActionState();
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
    const displayName = hasName ? `"${hasName}"` : `this ${deleteLabel}`;
    const extra = state.dirty ? '\nUnsaved changes will be lost.' : '';
    const confirmMsg = `Delete ${displayName}? This action cannot be undone.${extra}`;
    if (!(typeof window !== 'undefined' && window.confirm && window.confirm(confirmMsg))) return;

    state.deleting = true;
    markDirty(state.dirty);
    try {
      const resp = await fetch(apiUrl(`/apis/${doc.id}`), { method: 'DELETE' });
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
        window.alert(`Failed to delete ${deleteLabel}. Please try again.`);
      }
    } finally {
      state.deleting = false;
      markDirty(state.dirty);
    }
  }

  function setCollectorStatus(text, isError=false) {
    if (!collectorStatus) return;
    collectorStatus.textContent = text || '';
    collectorStatus.style.color = isError ? '#b91c1c' : '#4b5563';
  }

  function selectedTemplateId() {
    if (!config.enableCollectorControls) return '';
    return String((collectorTemplateSelect && collectorTemplateSelect.value) || state.selectedTemplate || '').trim();
  }

  function selectedTemplateName() {
    const id = selectedTemplateId();
    const template = state.templates.find((item) => String(item.id) === id);
    return template ? (template.name || 'Template') : '';
  }

  function selectedTemplateDoc() {
    const id = selectedTemplateId();
    return state.templates.find((item) => String(item.id) === id) || null;
  }

  function templateRectangleNamePool() {
    const template = selectedTemplateDoc();
    if (!template || typeof template !== 'object') return [];
    const source = [
      ...(Array.isArray(template.extract_text) ? template.extract_text : []),
      ...(Array.isArray(template.references) ? template.references : []),
      ...(Array.isArray(template.noise) ? template.noise : []),
      ...(Array.isArray(template.rects) ? template.rects : []),
    ];
    const seen = new Set();
    const names = [];
    for (const rect of source) {
      if (!rect || typeof rect !== 'object') continue;
      const name = String(rect.name || '').trim();
      if (!name || seen.has(name)) continue;
      seen.add(name);
      names.push(name);
    }
    return names;
  }

  function refreshRectNameControl(selectedRectId = '') {
    if (!rectNameSelect || !rectName) return;
    if (!config.enableCollectorControls) {
      rectName.style.display = '';
      rectNameSelect.style.display = 'none';
      return;
    }

    rectName.style.display = 'none';
    rectNameSelect.style.display = '';

    const selectedRect = (state.rects || []).find((item) => item && item.id === selectedRectId) || null;
    const currentName = String((selectedRect && selectedRect.name) || '').trim();
    const assignedNames = new Set();
    for (const rect of state.rects || []) {
      if (!rect || rect.id === selectedRectId) continue;
      const name = String(rect.name || '').trim();
      if (name) assignedNames.add(name);
    }

    const values = [];
    if (currentName) values.push(currentName);
    for (const name of templateRectangleNamePool()) {
      if (assignedNames.has(name)) continue;
      if (!values.includes(name)) values.push(name);
    }

    rectNameSelect.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Select name';
    rectNameSelect.appendChild(placeholder);
    for (const name of values) {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      rectNameSelect.appendChild(option);
    }
    rectNameSelect.value = currentName;
  }

  function currentRectNameInputValue() {
    if (config.enableCollectorControls && rectNameSelect) {
      return String(rectNameSelect.value || '').trim();
    }
    return String((rectName && rectName.value) || '').trim();
  }

  function setCollectorActionState() {
    if (!config.enableCollectorControls) return;
    const hasTemplate = !!selectedTemplateId();
    const navigable = (state.apis || []).filter((item) => item && !item.pending && item.id);
    const currentIndex = navigable.findIndex((item) => item.id === state.selected);
    if (btnNew) btnNew.disabled = !hasTemplate;
    if (btnGenerateRects) btnGenerateRects.disabled = !hasTemplate || !state.selected || state.evaluating || String(state.selected).startsWith('pending-');
    if (btnEvaluateAll) btnEvaluateAll.disabled = !hasTemplate || state.evaluating || !state.apis.some((item) => item && !item.pending && item.id);
    if (btnPrevImage) btnPrevImage.disabled = state.evaluating || currentIndex <= 0;
    if (btnNextImage) btnNextImage.disabled = state.evaluating || currentIndex < 0 || currentIndex >= navigable.length - 1;
    if (collectorTemplateButton) collectorTemplateButton.disabled = !state.templates.length;
  }

  async function navigateSelectedImage(step) {
    if (!config.enableCollectorControls) return;
    const direction = Number(step) < 0 ? -1 : 1;
    const navigable = (state.apis || []).filter((item) => item && !item.pending && item.id);
    if (!navigable.length) return;
    const currentIndex = navigable.findIndex((item) => item.id === state.selected);
    if (currentIndex < 0) return;
    const targetIndex = currentIndex + direction;
    if (targetIndex < 0 || targetIndex >= navigable.length) return;

    if (state.dirty) {
      if (confirm('You have unsaved changes. Save before switching?')) {
        const ok = await doSave();
        if (!ok) return;
      } else {
        markDirty(false);
      }
    }

    await loadApi(navigable[targetIndex].id);
  }

  function upsertApiDocs(docs) {
    for (const doc of docs || []) {
      if (!doc || !doc.id) continue;
      syncBaseAccess(doc);
      const idx = state.apis.findIndex((item) => item.id === doc.id);
      if (idx >= 0) state.apis.splice(idx, 1, doc);
      else state.apis.unshift(doc);
    }
    sortApisForList();
  }

  function stableListString(value) {
    return String(value || '').trim().toLocaleLowerCase();
  }

  function sortApisForList() {
    if (!Array.isArray(state.apis) || state.apis.length < 2) return;
    if (!config.enableCollectorControls) return;
    state.apis.sort((a, b) => {
      const aPending = !!(a && a.pending);
      const bPending = !!(b && b.pending);
      if (aPending !== bPending) return aPending ? -1 : 1;

      const aName = stableListString((a && (a._pendingName || a.name || a.original_filename)));
      const bName = stableListString((b && (b._pendingName || b.name || b.original_filename)));
      const byName = aName.localeCompare(bName);
      if (byName !== 0) return byName;

      const aCreated = stableListString(a && a.created_at);
      const bCreated = stableListString(b && b.created_at);
      const byCreated = aCreated.localeCompare(bCreated);
      if (byCreated !== 0) return byCreated;

      return stableListString(a && a.id).localeCompare(stableListString(b && b.id));
    });
  }

  function extractApiDocs(payload) {
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.items)) return payload.items;
    if (payload && payload.id) return [payload];
    return [];
  }

  function closeTemplateMenu() {
    if (collectorTemplateMenu) collectorTemplateMenu.classList.add('hidden');
    if (collectorTemplateButton) collectorTemplateButton.setAttribute('aria-expanded', 'false');
  }

  function updateTemplateButton() {
    if (!collectorTemplateButton) return;
    const template = selectedTemplateDoc();
    if (collectorTemplateLabel) collectorTemplateLabel.textContent = template ? `Template: ${template.name || 'Untitled template'}` : 'Template';
    if (collectorTemplateThumb) {
      if (template && template.image_url) {
        collectorTemplateThumb.src = template.image_url;
        collectorTemplateThumb.style.display = 'block';
      } else {
        collectorTemplateThumb.removeAttribute('src');
        collectorTemplateThumb.style.display = 'none';
      }
    }
  }

  async function switchCollectorTemplate(nextTemplateId) {
    const nextId = String(nextTemplateId || '').trim();
    if (!nextId || nextId === state.selectedTemplate) {
      closeTemplateMenu();
      return;
    }
    if (state.dirty) {
      if (confirm('You have unsaved changes. Save before switching templates?')) {
        const ok = await doSave();
        if (!ok) {
          if (collectorTemplateSelect) collectorTemplateSelect.value = state.selectedTemplate || '';
          closeTemplateMenu();
          return;
        }
      } else {
        markDirty(false);
      }
    }
    state.selectedTemplate = nextId;
    if (collectorTemplateSelect) collectorTemplateSelect.value = state.selectedTemplate;
    if (collectorTemplateMenu) {
      for (const item of collectorTemplateMenu.querySelectorAll('.template-menu-item')) {
        item.classList.toggle('active', item.dataset.templateId === state.selectedTemplate);
      }
    }
    try { window.localStorage.setItem('data-collector-template-id', state.selectedTemplate); } catch {}
    state.selected = null;
    state.rects = [];
    state.img.naturalW = 0;
    state.img.naturalH = 0;
    clearSelection({ skipRender: true });
    renderRects();
    if (stage) stage.style.display = 'none';
    if (img) img.removeAttribute('src');
    if (hint) hint.style.display = 'block';
    if (titleInp) titleInp.value = '';
    updateEndpoint(null);
    setCollectorStatus('');
    updateTemplateButton();
    closeTemplateMenu();
    await fetchAll();
    setCollectorActionState();
  }

  function renderTemplateSelect() {
    if (!collectorTemplateSelect) return;
    collectorTemplateSelect.innerHTML = '';
    if (collectorTemplateMenu) collectorTemplateMenu.innerHTML = '';
    if (!state.templates.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No templates';
      collectorTemplateSelect.appendChild(option);
      collectorTemplateSelect.disabled = true;
      state.selectedTemplate = null;
      if (collectorTemplateLabel) collectorTemplateLabel.textContent = 'No templates';
      if (collectorTemplateThumb) {
        collectorTemplateThumb.removeAttribute('src');
        collectorTemplateThumb.style.display = 'none';
      }
      setCollectorStatus('Create a Builder template first.', true);
      setCollectorActionState();
      return;
    }

    collectorTemplateSelect.disabled = false;
    for (const template of state.templates) {
      const option = document.createElement('option');
      option.value = String(template.id || '');
      option.textContent = template.name || 'Untitled template';
      collectorTemplateSelect.appendChild(option);

      if (collectorTemplateMenu) {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'template-menu-item';
        item.dataset.templateId = String(template.id || '');
        const thumb = document.createElement('span');
        thumb.className = 'template-thumb';
        const thumbImg = document.createElement('img');
        thumbImg.alt = '';
        if (template.image_url) thumbImg.src = template.image_url;
        thumb.appendChild(thumbImg);
        const title = document.createElement('span');
        title.className = 'template-menu-title';
        title.textContent = template.name || 'Untitled template';
        item.appendChild(thumb);
        item.appendChild(title);
        item.onclick = () => { switchCollectorTemplate(template.id); };
        collectorTemplateMenu.appendChild(item);
      }
    }
    const remembered = (() => {
      try { return window.localStorage.getItem('data-collector-template-id') || ''; } catch { return ''; }
    })();
    const current = state.templates.find((item) => String(item.id) === String(state.selectedTemplate));
    const stored = state.templates.find((item) => String(item.id) === remembered);
    const selected = current || stored || state.templates[0];
    state.selectedTemplate = String(selected.id || '');
    collectorTemplateSelect.value = state.selectedTemplate;
    if (collectorTemplateMenu) {
      for (const item of collectorTemplateMenu.querySelectorAll('.template-menu-item')) {
        item.classList.toggle('active', item.dataset.templateId === state.selectedTemplate);
      }
    }
    updateTemplateButton();
    setCollectorStatus('');
    setCollectorActionState();
    refreshRectNameControl(overlay.dataset.selected || '');
  }

  async function fetchTemplates() {
    if (!config.enableCollectorControls) return;
    try {
      const resp = await fetch(apiUrl('/templates'));
      if (!resp.ok) throw new Error('templates');
      const payload = await resp.json();
      state.templates = Array.isArray(payload) ? payload : [];
    } catch (err) {
      console.error(err);
      state.templates = [];
      setCollectorStatus('Failed to load templates', true);
    }
    renderTemplateSelect();
  }

  function listApisUrl() {
    if (!config.enableCollectorControls) return apiUrl('/apis');
    const templateId = selectedTemplateId();
    if (!templateId) return '';
    return `${apiUrl('/apis')}?template_id=${encodeURIComponent(templateId)}`;
  }

  async function evaluateCurrentItem({ silent=false } = {}) {
    if (!config.enableCollectorControls) return;
    if (!state.selected || String(state.selected).startsWith('pending-')) {
      if (!silent) alert('Select or upload an image first.');
      return;
    }
    if (!silent && state.dirty && !confirm('Evaluate will replace unsaved rectangle edits. Continue?')) return;
    state.evaluating = true;
    setCollectorActionState();
    setCollectorStatus('Evaluating...');
    try {
      const resp = await fetch(apiUrl(`/apis/${state.selected}/evaluate`), { method: 'POST' });
      if (!resp.ok) {
        let detail = '';
        try {
          const payload = await resp.json();
          detail = payload && payload.detail ? String(payload.detail) : '';
        } catch {}
        throw new Error(detail || 'evaluate');
      }
      const doc = await resp.json();
      upsertApiDocs([doc]);
      await loadApi(doc.id);
      const evaluation = doc.evaluation || {};
      const score = Number(evaluation.confidence_score);
      const suffix = Number.isFinite(score) ? ` (${Math.round(score * 100)}%)` : '';
      const message = evaluation.success === false
        ? (evaluation.message || `Evaluation did not find ${selectedTemplateName() || 'the template'}`)
        : `Evaluated${suffix}`;
      setCollectorStatus(message, evaluation.success === false);
    } catch (err) {
      console.error(err);
      setCollectorStatus('Evaluation failed', true);
      if (!silent) alert(`Failed to evaluate image${err && err.message && err.message !== 'evaluate' ? `: ${err.message}` : '.'}`);
    } finally {
      state.evaluating = false;
      setCollectorActionState();
    }
  }

  async function evaluateAllItems() {
    if (!config.enableCollectorControls) return;
    const mode = String((evaluateAllMode && evaluateAllMode.value) || 'all').toLowerCase();
    const hasAnyRectangles = (item) => {
      if (!item) return false;
      const extract = Array.isArray(item.extract_text) ? item.extract_text : [];
      const references = Array.isArray(item.references) ? item.references : [];
      const noise = Array.isArray(item.noise) ? item.noise : [];
      const rects = Array.isArray(item.rects) ? item.rects : [];
      return !!(extract.length || references.length || noise.length || rects.length);
    };
    const shouldEvaluateItem = (item) => {
      if (!item || item.pending || !item.id) return false;
      if (mode === 'empty') return !hasAnyRectangles(item);
      return true;
    };
    const items = (state.apis || []).filter(shouldEvaluateItem);
    if (!items.length) {
      setCollectorStatus(mode === 'empty' ? 'No empty images to evaluate' : 'No images to evaluate', true);
      return;
    }
    if (state.dirty) {
      const shouldSave = confirm('You have unsaved rectangle edits. Save before evaluating all?');
      if (shouldSave) {
        const ok = await doSave();
        if (!ok) {
          setCollectorStatus('Save failed. Evaluation cancelled.', true);
          return;
        }
      } else {
        markDirty(false);
      }
    }

    const total = items.length;
    const previousSelected = state.selected;
    let completed = 0;
    let failed = 0;

    state.evaluating = true;
    setCollectorActionState();
    try {
      for (let i = 0; i < total; i += 1) {
        const item = items[i];
        const label = (item && (item.name || item._pendingName)) || `item ${i + 1}`;
        setCollectorStatus(`Evaluating ${i + 1}/${total}: ${label}...`);
        try {
          const resp = await fetch(apiUrl(`/apis/${item.id}/evaluate`), { method: 'POST' });
          if (!resp.ok) throw new Error('evaluate');
          const doc = await resp.json();
          upsertApiDocs([doc]);
          completed += 1;
        } catch (err) {
          console.error(err);
          failed += 1;
        }
      }

      renderList();
      const selectedStillExists = previousSelected && state.apis.find((item) => item.id === previousSelected);
      if (selectedStillExists) {
        await loadApi(previousSelected);
      } else if (state.apis.length) {
        await loadApi(state.apis[0].id);
      }

      const modeLabel = mode === 'empty' ? 'empty images' : 'images';
      const msg = failed
        ? `Evaluated ${completed}/${total} ${modeLabel} (${failed} failed)`
        : `Evaluated ${completed}/${total} ${modeLabel}`;
      setCollectorStatus(msg, failed > 0);
    } finally {
      state.evaluating = false;
      setCollectorActionState();
    }
  }

  function openEvaluateAllPopup() {
    if (!evaluateAllPopup) return;
    evaluateAllPopup.classList.remove('hidden');
  }

  function closeEvaluateAllPopup() {
    if (!evaluateAllPopup) return;
    evaluateAllPopup.classList.add('hidden');
  }

  function clearAllRectangles() {
    if (!config.enableCollectorControls) return;
    if (!state.rects.length) {
      setCollectorStatus('No rectangles to clear');
      return;
    }
    try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
    state.rects = [];
    clearSelection({ skipRender: true });
    renderRects();
    markDirty(true);
    setCollectorStatus('Rectangles cleared');
  }

  async function doSave(){
    if (!state.selected) return true;
    try{
      // Convert rects to pixel units before sending
      const W = state.img.naturalW, H = state.img.naturalH;
      const rectLookup = new Map();
      const buildPixelRect = (r) => {
        const px = {
          id: r.id,
          name: r.name || '',
          x: Math.round(r.x * W),
          y: Math.round(r.y * H),
          w: Math.round(r.w * W),
          h: Math.round(r.h * H),
          'θ': rectThetaDeg(r),
          seps: Array.isArray(r.seps) ? r.seps.map(rel => Math.round(rel * Math.max(r.h * H, 1))) : [],
        };
        rectLookup.set(px.id, px);
        return px;
      };
      const extractText = [];
      const references = [];
      const noise = [];
      for (const rect of state.rects || []) {
        const px = buildPixelRect(rect);
        const hasExtract = !!rect.extract_text;
        const hasReference = !!rect.reference;
        const hasNoise = !!rect.noise;
        if (hasExtract) extractText.push({ ...px });
        if (hasReference) references.push({ ...px });
        if (hasNoise) noise.push({ ...px });
        if (!hasExtract && !hasReference && !hasNoise) {
          noise.push({ ...px });
        }
      }
      const r = await fetch(apiUrl(`/apis/${state.selected}`),{
        method:'PUT', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          name: titleInp.value || 'Untitled API',
          extract_text: extractText,
          references,
          noise
        })
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
  if (btnPrevImage) btnPrevImage.onclick = async () => { await navigateSelectedImage(-1); };
  if (btnNextImage) btnNextImage.onclick = async () => { await navigateSelectedImage(1); };
  if (btnGenerateRects) btnGenerateRects.onclick = () => { evaluateCurrentItem(); };
  if (btnEvaluateAll) btnEvaluateAll.onclick = () => { openEvaluateAllPopup(); };
  if (btnEvaluateAllCancel) btnEvaluateAllCancel.onclick = () => { closeEvaluateAllPopup(); };
  if (evaluateAllBackdrop) evaluateAllBackdrop.onclick = () => { closeEvaluateAllPopup(); };
  if (btnEvaluateAllStart) btnEvaluateAllStart.onclick = async () => {
    closeEvaluateAllPopup();
    await evaluateAllItems();
  };
  if (btnClearRects) btnClearRects.onclick = () => { clearAllRectangles(); };
  if (collectorTemplateButton) {
    collectorTemplateButton.onclick = (ev) => {
      ev.stopPropagation();
      if (!collectorTemplateMenu || !state.templates.length) return;
      const isHidden = collectorTemplateMenu.classList.toggle('hidden');
      collectorTemplateButton.setAttribute('aria-expanded', isHidden ? 'false' : 'true');
    };
  }
  if (collectorTemplateSelect) {
    collectorTemplateSelect.onchange = async () => { await switchCollectorTemplate(collectorTemplateSelect.value); };
  }
  document.addEventListener('click', (ev) => {
    if (!collectorTemplatePicker || !collectorTemplateMenu) return;
    if (!collectorTemplatePicker.contains(ev.target)) closeTemplateMenu();
  });
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
    if (e.key === 'Escape' && evaluateAllPopup && !evaluateAllPopup.classList.contains('hidden')) {
      closeEvaluateAllPopup();
      return;
    }
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

  function rectThetaDeg(rect) {
    const raw = rect ? (rect['θ'] ?? rect.theta ?? 0) : 0;
    const num = Number(raw);
    return Number.isFinite(num) ? num : 0;
  }

  function rectAabbPx(rect) {
    const W = Math.max(1, state.img.naturalW || 1);
    const H = Math.max(1, state.img.naturalH || 1);
    const wPx = rect.w * W;
    const hPx = rect.h * H;
    const theta = rectThetaDeg(rect) * Math.PI / 180;
    const cosA = Math.abs(Math.cos(theta));
    const sinA = Math.abs(Math.sin(theta));
    const aabbW = (wPx * cosA) + (hPx * sinA);
    const aabbH = (wPx * sinA) + (hPx * cosA);
    return { aabbW, aabbH, wPx, hPx, W, H };
  }

  function rectAnchorBoundsNormalized(rect) {
    const { aabbW, aabbH, wPx, hPx, W, H } = rectAabbPx(rect);
    const minX = (aabbW - wPx) / (2 * W);
    const maxX = (W - ((aabbW + wPx) / 2)) / W;
    const minY = (aabbH - hPx) / (2 * H);
    const maxY = (H - ((aabbH + hPx) / 2)) / H;
    return { minX, maxX, minY, maxY };
  }

  function rectVisualPx(rect) {
    const { aabbW, aabbH, wPx, hPx, W, H } = rectAabbPx(rect);
    const xPx = rect.x * W;
    const yPx = rect.y * H;
    return {
      x: xPx + ((wPx - aabbW) / 2),
      y: yPx + ((hPx - aabbH) / 2),
      w: aabbW,
      h: aabbH,
      anchorW: wPx,
      anchorH: hPx,
    };
  }

  // Track overlapping rectangle hit-testing so repeated clicks can cycle targets.
  const HIT_CYCLE_PRECISION = 1000;
  const hitCycle = { key: '', idx: 0 };

  function resetHitCycle() {
    hitCycle.key = '';
    hitCycle.idx = 0;
  }

  function hitTestRectsAt(gx, gy) {
    const rects = Array.isArray(state.rects) ? state.rects : [];
    const hits = [];
    rects.forEach((rect, idx) => {
      if (!rect) return;
      const cx = rect.x + rect.w / 2;
      const cy = rect.y + rect.h / 2;
      const theta = rectThetaDeg(rect) * Math.PI / 180;
      const cos = Math.cos(theta);
      const sin = Math.sin(theta);
      const dx = gx - cx;
      const dy = gy - cy;
      const localX = dx * cos + dy * sin;
      const localY = -dx * sin + dy * cos;
      const withinX = Math.abs(localX) <= rect.w / 2;
      const withinY = Math.abs(localY) <= rect.h / 2;
      if (withinX && withinY) {
        const area = Math.max(0, rect.w * rect.h);
        hits.push({ rect, idx, area });
      }
    });
    hits.sort((a, b) => {
      if (a.area !== b.area) return a.area - b.area;
      return a.idx - b.idx;
    });
    return hits;
  }

  function buildHitKey(hits, gx, gy) {
    const ids = hits.map(h => h.rect.id || '').join('|');
    const posX = Math.round(gx * HIT_CYCLE_PRECISION);
    const posY = Math.round(gy * HIT_CYCLE_PRECISION);
    return `${ids}@${posX},${posY}`;
  }

  function pickRectFromHits(hits, gx, gy, { advance = true, remember = true } = {}) {
    if (!hits.length) {
      if (remember) resetHitCycle();
      return null;
    }
    if (!remember) return hits[0].rect;
    const key = buildHitKey(hits, gx, gy);
    if (hitCycle.key !== key) {
      hitCycle.key = key;
      hitCycle.idx = 0;
    } else if (advance) {
      hitCycle.idx = (hitCycle.idx + 1) % hits.length;
    }
    const current = hits[hitCycle.idx % hits.length];
    return current ? current.rect : hits[0].rect;
  }

  function nudgeSelectedRect(rect, dx, dy, { preview = false } = {}) {
    if (!rect) return false;
    const W = state.img.naturalW;
    const H = state.img.naturalH;
    if (!W || !H) return false;
    const vis = rectVisualPx(rect);
    const curX = Math.round(vis.x);
    const curY = Math.round(vis.y);
    const widthPx = Math.max(1, Math.round(vis.w));
    const heightPx = Math.max(1, Math.round(vis.h));
    const maxX = Math.max(0, W - widthPx);
    const maxY = Math.max(0, H - heightPx);
    const nextX = clamp(curX + dx, 0, maxX);
    const nextY = clamp(curY + dy, 0, maxY);
    const shiftX = nextX - curX;
    const shiftY = nextY - curY;
    if (shiftX === 0 && shiftY === 0) return false;
    if (preview) return true;
    rect.x = (rect.x * W + shiftX) / W;
    rect.y = (rect.y * H + shiftY) / H;
    if (overlay.dataset.selected === rect.id) {
      const nextVis = rectVisualPx(rect);
      if (rectX) rectX.value = String(Math.round(nextVis.x));
      if (rectY) rectY.value = String(Math.round(nextVis.y));
    }
    renderRects();
    return true;
  }

  function renderList() {
    sortApisForList();
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
      const url = listApisUrl();
      if (!url) {
        state.apis = [];
        state.loaded = true;
        renderList();
        updateEndpoint(null);
        return;
      }
      const r = await fetch(url);
      const j = await r.json();
      state.apis = Array.isArray(j) ? j : [];
      state.apis.forEach(syncBaseAccess);
      sortApisForList();
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
    setCollectorActionState();
    if (config.enableCollectorControls && !state.selected && !state.apis.length && selectedTemplateId()) {
      if (titleInp) titleInp.value = '';
      showCreate();
    }
  }

  function clearSelection({ skipRender = false } = {}) {
    selPanel.style.display = 'none';
    rectName.value = '';
    if (rectNameSelect) rectNameSelect.value = '';
    rectExtract.checked = true;
    if (rectReference) rectReference.checked = false;
    if (rectNoise) rectNoise.checked = false;
    for (const el of overlay.querySelectorAll('.rect')) el.classList.remove('selected');
    overlay.dataset.selected = '';
    keyNudgeActive = false;
    refreshRectNameControl('');
    setInspectorOpen(false);
    if (!skipRender) renderRects();
  }

  function selectRect(id) {
    overlay.dataset.selected = id || '';
    keyNudgeActive = false;
    refreshRectNameControl(id || '');
    const r = state.rects.find(x => x.id === id);
    if (r) {
      selPanel.style.display = 'block';
      rectName.value = r.name || '';
      if (rectNameSelect) rectNameSelect.value = r.name || '';
      rectExtract.checked = !!r.extract_text;
      if (rectReference) rectReference.checked = !!r.reference;
      if (rectNoise) rectNoise.checked = !!r.noise;
      setInspectorOpen(true);
      const vis = rectVisualPx(r);
      rectX.value = Math.round(vis.x);
      rectY.value = Math.round(vis.y);
      rectW.value = Math.round(r.w * state.img.naturalW);
      rectH.value = Math.round(r.h * state.img.naturalH);
      if (rectTheta) rectTheta.value = String(rectThetaDeg(r));
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
      const classes = ['rect'];
      if (overlay.dataset.selected === r.id) classes.push('selected');
      if (r.extract_text !== false) classes.push('rect-info');
      if (r.reference) classes.push('rect-reference');
      if (r.noise) classes.push('rect-noise');
      el.className = classes.join(' ');
      el.dataset.id = r.id;
      el.style.left = (r.x * state.img.naturalW) + 'px';
      el.style.top  = (r.y * state.img.naturalH) + 'px';
      el.style.width  = (r.w * state.img.naturalW) + 'px';
      el.style.height = (r.h * state.img.naturalH) + 'px';
      el.style.transformOrigin = '50% 50%';
      el.style.transform = `rotate(${rectThetaDeg(r)}deg)`;
      el.onclick = (ev) => {
        ev.stopPropagation();
        if (state.mode === 'select') return;
        if (!state.img.naturalW || !state.img.naturalH) {
          selectRect(r.id);
          return;
        }
        const box = img.getBoundingClientRect();
        const px = ev.clientX - box.left;
        const py = ev.clientY - box.top;
        const gx = percentClamp(px / Math.max(1, state.img.naturalW * state.zoom));
        const gy = percentClamp(py / Math.max(1, state.img.naturalH * state.zoom));
        const hits = hitTestRectsAt(gx, gy);
        const picked = pickRectFromHits(hits, gx, gy);
        const target = picked || r;
        selectRect(target.id);
      };
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
    const toArray = (value) => (Array.isArray(value) ? value : []);
    const extractList = toArray(doc.extract_text);
    const referenceList = toArray(doc.references);
    const noiseList = toArray(doc.noise);
    const fallbackRects = Array.isArray(doc.rects) ? doc.rects : [];

    if (!extractList.length && fallbackRects.length) {
      for (const r of fallbackRects) {
        if (r && r.extract_text !== false) extractList.push(r);
      }
    }

    let anonCounter = 0;
    const rectMap = new Map();
    const getNumber = (value, fallback = 0) => {
      const num = Number(value);
      return Number.isFinite(num) ? num : fallback;
    };
    const addRect = (raw, flags = {}) => {
      if (!raw || typeof raw !== 'object') return;
      let id = String(raw.id ?? raw._id ?? '').trim();
      if (!id) {
        id = `r-${(anonCounter++).toString(36).padStart(5, '0')}`;
      }
      const xPx = getNumber(raw.x, getNumber(raw.left, 0));
      const yPx = getNumber(raw.y, getNumber(raw.top, 0));
      const wPx = Math.max(1, getNumber(raw.w, getNumber(raw.width, 0)));
      const hPx = Math.max(1, getNumber(raw.h, getNumber(raw.height, 0)));
      const prev = rectMap.get(id);
      const base = prev || {
        id,
        name: '',
        x: W ? xPx / W : 0,
        y: H ? yPx / H : 0,
        w: W ? wPx / W : 0,
        h: H ? hPx / H : 0,
        'θ': 0,
        seps: [],
        extract_text: false,
        reference: false,
        noise: false,
      };
      base.name = (raw.name ?? base.name ?? '') || '';
      base.x = W ? xPx / Math.max(W, 1) : base.x;
      base.y = H ? yPx / Math.max(H, 1) : base.y;
      base.w = W ? wPx / Math.max(W, 1) : base.w;
      base.h = H ? hPx / Math.max(H, 1) : base.h;
      if (W > 0 && H > 0) {
        const minW = 1 / Math.max(W, 1);
        const minH = 1 / Math.max(H, 1);
        base.w = Math.max(minW, Math.min(1, base.w));
        base.h = Math.max(minH, Math.min(1, base.h));
        base.x = Math.max(0, Math.min(Math.max(0, 1 - base.w), base.x));
        base.y = Math.max(0, Math.min(Math.max(0, 1 - base.h), base.y));
      }
      base['θ'] = getNumber(raw['θ'], getNumber(raw.theta, getNumber(base['θ'], 0)));
      if (Array.isArray(raw.seps) && raw.seps.length) {
        const rectHeight = Math.max(hPx, 1);
        base.seps = raw.seps.map((s) => {
          const abs = getNumber(s, 0);
          const frac = rectHeight ? abs / rectHeight : 0;
          return Math.max(0, Math.min(1, frac));
        });
      }
      if (flags.extract_text) base.extract_text = true;
      if (flags.reference) base.reference = true;
      if (flags.noise) base.noise = true;
      rectMap.set(id, base);
    };

    fallbackRects.forEach((r) => addRect(r, { extract_text: r && r.extract_text !== false }));
    extractList.forEach((r) => addRect(r, { extract_text: true }));
    referenceList.forEach((r) => addRect(r, { reference: true }));
    noiseList.forEach((r) => addRect(r, { noise: true }));

    state.rects = Array.from(rectMap.values());
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
    const box = img.getBoundingClientRect();
    const px = ev.clientX - box.left;
    const py = ev.clientY - box.top;
    const denomX = Math.max(1, state.img.naturalW * state.zoom);
    const denomY = Math.max(1, state.img.naturalH * state.zoom);
    const gx = percentClamp(px / denomX);
    const gy = percentClamp(py / denomY);
    const hits = hitTestRectsAt(gx, gy);
    const picked = pickRectFromHits(hits, gx, gy, { advance: false });
    const fallbackEl = ev.target.closest && ev.target.closest('.rect');
    const fallback = fallbackEl ? state.rects.find(x => x.id === fallbackEl.dataset.id) : null;
    const r = picked || fallback;
    if (!r) return;
    const id = r.id;
    history.undo.push(cloneRects()); history.redo.length = 0;
    selectRect(id);
    moving = { id, startX: gx, startY: gy, rx: r.x, ry: r.y, rw: r.w, rh: r.h, changed: false };
    ev.preventDefault(); ev.stopPropagation();
  });
  overlay.addEventListener('mousedown', (ev) => {
    const box = img.getBoundingClientRect();
    const px = ev.clientX - box.left;
    const py = ev.clientY - box.top;
    const denomX = Math.max(1, state.img.naturalW * state.zoom);
    const denomY = Math.max(1, state.img.naturalH * state.zoom);
    const gx = percentClamp(px / denomX);
    const gy = percentClamp(py / denomY);
    const hits = hitTestRectsAt(gx, gy);
    const h = ev.target.closest ? ev.target.closest('.handle') : null;
    const sep = ev.target.closest ? ev.target.closest('.sep-line') : null;
    let rectEl = ev.target.classList && ev.target.classList.contains('rect')
      ? ev.target
      : (h ? h.parentElement : (sep ? sep.parentElement : null));
    let rectData = rectEl ? state.rects.find(x => x.id === rectEl.dataset.id) : null;
    if (!h && !sep) {
      if (state.mode === 'select' || state.mode === 'split') {
        const picked = pickRectFromHits(hits, gx, gy);
        if (picked) {
          rectData = picked;
          const el = overlay.querySelector(`.rect[data-id="${picked.id}"]`);
          if (el) rectEl = el;
        } else {
          rectData = null;
          rectEl = null;
        }
      } else if (!hits.length) {
        resetHitCycle();
      }
    } else if (!hits.length) {
      resetHitCycle();
    }
    if (state.mode === 'split' && rectData && !h) {
      try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
      const r = rectData;
      const id = r.id;
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
    if (h && rectData) {
      try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
      const r = rectData;
      const id = r.id;
      resizing = { id, pos: h.dataset.pos, startX: gx, startY: gy, rx: r.x, ry: r.y, rw: r.w, rh: r.h, changed: false };
      ev.preventDefault(); ev.stopPropagation(); return;
    }
    if (state.mode === 'select' && rectData) {
      try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
      const r = rectData;
      const id = r.id;
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
      let nextX = moving.rx + dx;
      let nextY = moving.ry + dy;
      if (!moving.changed && (Math.abs(nextX - prevX) > 0.0001 || Math.abs(nextY - prevY) > 0.0001)) {
        moving.changed = true;
      }
      r.x = nextX; r.y = nextY;
      const { minX, maxX, minY, maxY } = rectAnchorBoundsNormalized(r);
      if (maxX < minX) nextX = minX;
      else nextX = clamp(nextX, minX, maxX);
      if (maxY < minY) nextY = minY;
      else nextY = clamp(nextY, minY, maxY);
      r.x = nextX; r.y = nextY;
      renderRects();
      // update inspector fields
      const vis = rectVisualPx(r);
      rectX.value = Math.round(vis.x);
      rectY.value = Math.round(vis.y);
      if (rectTheta) rectTheta.value = String(rectThetaDeg(r));
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
      const { minX, maxX, minY, maxY } = rectAnchorBoundsNormalized(r);
      if (maxX < minX) r.x = minX;
      else r.x = clamp(r.x, minX, maxX);
      if (maxY < minY) r.y = minY;
      else r.y = clamp(r.y, minY, maxY);
      renderRects();
      const vis = rectVisualPx(r);
      rectX.value = Math.round(vis.x);
      rectY.value = Math.round(vis.y);
      rectW.value = Math.round(r.w * state.img.naturalW);
      rectH.value = Math.round(r.h * state.img.naturalH);
      if (rectTheta) rectTheta.value = String(rectThetaDeg(r));
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
        const rect = { id, name: '', x, y, w, h, extract_text: true, reference: false, noise: false, 'θ': 0 };
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
    if (ev.shiftKey) {
      if (!state.img.naturalW || !state.img.naturalH) return;
      const box = img.getBoundingClientRect();
      const px = ev.clientX - box.left;
      const py = ev.clientY - box.top;
      const denomX = Math.max(1, state.img.naturalW * state.zoom);
      const denomY = Math.max(1, state.img.naturalH * state.zoom);
      const gx = percentClamp(px / denomX);
      const gy = percentClamp(py / denomY);
      const hits = hitTestRectsAt(gx, gy);
      const picked = pickRectFromHits(hits, gx, gy, { advance: false });
      const fallback = rectEl ? state.rects.find(x => x.id === rectEl.dataset.id) : null;
      const r = picked || fallback;
      if (!r) return;
      const rel = Math.max(0, Math.min(1, (gy - r.y) / Math.max(0.0001, r.h)));
      if (!Array.isArray(r.seps)) r.seps = [];
      r.seps.push(rel); r.seps.sort((a,b)=>a-b);
      renderRects(); try { renderSepsInspector(r); } catch {} markDirty(true); ev.preventDefault(); return;
    }
    if (ev.target === overlay) { resetHitCycle(); selectRect(''); }
  });

  function applyRectNameEdit() {
    try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
    const id = overlay.dataset.selected || '';
    const r = state.rects.find(x => x.id === id);
    if (!r) return;
    r.name = currentRectNameInputValue();
    refreshRectNameControl(id);
    markDirty(true);
  }
  if (rectName) rectName.oninput = applyRectNameEdit;
  if (rectNameSelect) rectNameSelect.onchange = applyRectNameEdit;
  rectExtract.onchange = () => {
    try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
    const id = overlay.dataset.selected || '';
    const r = state.rects.find(x => x.id === id);
    if (!r) return; r.extract_text = !!rectExtract.checked; renderRects(); markDirty(true);
  };
  if (rectReference) {
    rectReference.onchange = () => {
      try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
      const id = overlay.dataset.selected || '';
      const r = state.rects.find(x => x.id === id);
      if (!r) return; r.reference = !!rectReference.checked; renderRects(); markDirty(true);
    };
  }
  if (rectNoise) {
    rectNoise.onchange = () => {
      try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
      const id = overlay.dataset.selected || '';
      const r = state.rects.find(x => x.id === id);
      if (!r) return; r.noise = !!rectNoise.checked; renderRects(); markDirty(true);
    };
  }
  
  function clamp(v, lo, hi){ return Math.max(lo, Math.min(hi, v)); }
  function applyRectEdits(){
    try { history.undo.push(cloneRects()); history.redo.length = 0; } catch {}
    const id = overlay.dataset.selected || '';
    const r = state.rects.find(x => x.id === id);
    if (!r) return;
    const W = state.img.naturalW, H = state.img.naturalH;
    let x = +rectX.value || 0, y = +rectY.value || 0, w = +rectW.value || 1, h = +rectH.value || 1;
    const thetaInput = rectTheta ? Number(rectTheta.value) : 0;
    const theta = Number.isFinite(thetaInput) ? thetaInput : 0;
    w = clamp(w, 1, W);
    h = clamp(h, 1, H);
    const thetaRad = theta * Math.PI / 180;
    const aabbW = Math.abs(w * Math.cos(thetaRad)) + Math.abs(h * Math.sin(thetaRad));
    const aabbH = Math.abs(w * Math.sin(thetaRad)) + Math.abs(h * Math.cos(thetaRad));
    x = clamp(x, 0, Math.max(0, W - aabbW));
    y = clamp(y, 0, Math.max(0, H - aabbH));
    const anchorX = x + ((aabbW - w) / 2);
    const anchorY = y + ((aabbH - h) / 2);
    r.x = anchorX / W;
    r.y = anchorY / H;
    r.w = w / W;
    r.h = h / H;
    r['θ'] = theta;
    const vis = rectVisualPx(r);
    rectX.value = Math.round(vis.x);
    rectY.value = Math.round(vis.y);
    rectW.value = Math.round(w);
    rectH.value = Math.round(h);
    if (rectTheta) rectTheta.value = String(theta);
    renderRects(); markDirty(true);
  }
  rectX.onchange = rectY.onchange = rectW.onchange = rectH.onchange = applyRectEdits;
  if (rectTheta) rectTheta.onchange = applyRectEdits;
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
  function bindUploaderInput() {
    const el = apiImageInput();
    if (!el) return null;
    if (config.enableCollectorControls) el.multiple = true;
    if (!el._boundAutoCreate) {
      el.addEventListener('change', () => { if (el.files && el.files[0]) createFromUpload(); });
      el._boundAutoCreate = true;
    }
    return el;
  }
  function openCollectorFilePicker() {
    const el = bindUploaderInput();
    if (el) {
      try {
        el.click();
        return true;
      } catch {}
    }
    showCreate();
    setCollectorStatus('Upload control is still loading. Click the drop area or try again.', true);
    return false;
  }
  btnNew.onclick = async () => {
    if (config.enableCollectorControls && !selectedTemplateId()) {
      alert('Choose a template before adding files.');
      return;
    }
    if (state.dirty) {
      if (confirm(`You have unsaved changes. Save before creating a new ${deleteLabel}?`)) { const ok = await doSave(); if (!ok) return; }
      else { markDirty(false); }
    }
    if (config.enableCollectorControls) {
      openCollectorFilePicker();
      return;
    }
    clearSelection({ skipRender: true });
    state.selected = null;
    state.rects = [];
    renderRects();
    renderList();
    if (stage) stage.style.display = 'none';
    if (img) img.removeAttribute('src');
    state.img.naturalW = 0;
    state.img.naturalH = 0;
    if (hint) hint.style.display = 'none';
    if (titleInp) titleInp.value = '';
    updateEndpoint(null);
    markDirty(false);
    showCreate();
  };
  const createFromUpload = async () => {
    const inp = apiImageInput();
    const files = inp && inp.files ? Array.from(inp.files) : [];
    if (!files.length) { alert('Please choose an image'); return; }
    const templateId = selectedTemplateId();
    if (config.enableCollectorControls && !templateId) {
      alert('Choose a template before adding files.');
      return;
    }
    const file = files[0];
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
    const placeholderName = config.enableCollectorControls
      ? (files.length === 1 ? (file.name || 'New image') : `${files.length} files`)
      : 'New API';
    const placeholder = { id: tmpId, name: placeholderName, image_url: img.src, rects: [] , pending: true };
    state.apis.unshift(placeholder); renderList();
    state.selected = tmpId;
    setCollectorActionState();

    const fd = new FormData();
    let uploadUrl = apiUrl('/apis');
    if (config.enableCollectorControls) {
      files.forEach((item) => fd.append('images', item));
      uploadUrl = `${uploadUrl}?template_id=${encodeURIComponent(templateId)}`;
    } else {
      fd.append('image', file);
    }
    try {
      const r = await fetch(uploadUrl, { method: 'POST', body: fd });
      if (!r.ok) throw new Error('upload');
      const payload = await r.json();
      const docs = extractApiDocs(payload);
      if (!docs.length) throw new Error('upload');
      // Replace placeholder with returned docs
      const idx = state.apis.findIndex(a=>a.id===tmpId);
      if (idx>=0) state.apis.splice(idx,1);
      upsertApiDocs(docs);
      renderList();
      const doc = docs.find((item) => !item.duplicate) || docs[0];
      hideCreate();
      await loadApi(doc.id);
      setMode('draw');
      if (config.enableCollectorControls) {
        const createdCount = Array.isArray(payload.created) ? payload.created.length : docs.filter((item) => !item.duplicate).length;
        const duplicateCount = Array.isArray(payload.duplicates) ? payload.duplicates.length : docs.filter((item) => item.duplicate).length;
        if (createdCount && duplicateCount) {
          setCollectorStatus(`Added ${createdCount}; ${duplicateCount} already existed`);
        } else if (duplicateCount) {
          setCollectorStatus(duplicateCount === 1 ? 'File already exists for this template' : `${duplicateCount} files already exist for this template`);
        } else {
          setCollectorStatus(createdCount === 1 ? 'Added 1 file' : `Added ${createdCount} files`);
        }
      }
    } catch (e) {
      alert(`Failed to create ${deleteLabel}`);
      // Remove placeholder on failure
      const idx = state.apis.findIndex(a=>a.id===tmpId);
      if (idx>=0) { state.apis.splice(idx,1); renderList(); }
    } finally {
      try { inp.value = ''; } catch {}
      setCollectorActionState();
    }
  };

  // Auto-create when a file is picked (no need to press Create)
  (function hookAutoCreate(){
    let attempts = 0;
    const tryBind = () => {
      attempts += 1;
      if (bindUploaderInput()) return;
      if (attempts < 30) setTimeout(tryBind, 150);
    };
    tryBind();
  })();

  // Init
  if (config.enableCollectorControls) {
    await fetchTemplates();
  }
  await fetchAll();
  clearSelection();
  setCollectorActionState();
}
