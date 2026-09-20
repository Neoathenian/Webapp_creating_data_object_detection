(() => {
  'use strict';
  const $ = id => document.getElementById(id), ns = 'http://www.w3.org/2000/svg';
  const board = $('board');
  let catalog = [], data = null, pairs = [], selected = null, history = [], future = [];
  let proposals = [], dismissed = new Set();
  let savedState = '[]', busy = false, view = [0, 0, 1800, 900], layout = {}, drag = null;
  const color = i => `hsl(${(i * 137.508 + 165) % 360} 78% 42%)`;
  const dirty = () => JSON.stringify(pairs) !== savedState;
  const status = (message, error = false) => { $('status').textContent = message; $('status').classList.toggle('error', error); };
  const svg = (tag, attrs, parent = board) => { const el = document.createElementNS(ns, tag); for (const [k,v] of Object.entries(attrs)) el.setAttribute(k, v); parent.appendChild(el); return el; };
  const endpoint = () => `/matches/api/pair/${encodeURIComponent(data.template_name)}/${encodeURIComponent(data.sample_name)}`;
  const clone = value => JSON.parse(JSON.stringify(value));
  const EQUIVALENT = { o: '0', 0: '0', i: '1', l: '1', 1: '1' };
  const canonical = label => {
    const value = String(label ?? '').trim();
    if (value.length !== 1) return value;
    const lower = value.toLowerCase();
    return EQUIVALENT[lower] ?? value;
  };
  const sameLabel = (left, right) => {
    const a = canonical(left), b = canonical(right);
    return !!a && a === b;
  };
  async function api(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) { let message = `Request failed (${response.status})`; try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail); } catch {} throw new Error(message); }
    return response.json();
  }
  function controls() {
    $('save').disabled = !data || busy || !dirty();
    $('predict').disabled = !data || busy;
    $('accept-predictions').disabled = !data || busy || !availablePredictions().length;
    $('undo').disabled = busy || !history.length;
    $('redo').disabled = busy || !future.length;
    $('export').disabled = !data || busy;
    for (const id of ['template','sample','previous','next']) $(id).disabled = busy;
    $('save-state').textContent = busy ? 'Loading…' : !data ? 'No sample loaded' : dirty() ? 'Unsaved changes' : `Saved · revision ${data.revision}`;
    $('count').textContent = pairs.length;
    $('zoom-range').value = Math.round(180000 / view[2]);
    $('zoom-range').style.setProperty('--zoom-progress', `${(Number($('zoom-range').value) - 50) / 950 * 100}%`);
    $('zoom-label').textContent = `${Math.round(180000 / view[2])}%`;
    for (const button of $('sample-list').querySelectorAll('button')) {
      const active = button.dataset.sample === $('sample').value;
      button.classList.toggle('active', active);
      button.setAttribute('aria-current', active ? 'true' : 'false');
      button.disabled = busy;
    }
  }
  function populateSamples() {
    $('sample').replaceChildren();
    $('sample-list').replaceChildren();
    const group = catalog.find(t => t.name === $('template').value);
    for (const [index, item] of (group?.samples || []).entries()) {
      const option = new Option(`${item.reviewed ? '✓ ' : ''}${item.name}${item.matches ? ` · ${item.matches} matches` : ''}`, item.name);
      $('sample').add(option);
      const row = document.createElement('li');
      const button = document.createElement('button');
      button.className = 'sidebar-item'; button.dataset.sample = item.name;
      const thumb = document.createElement('span'); thumb.className = 'thumb';
      const image = document.createElement('img'); image.alt = ''; image.loading = 'lazy';
      image.src = `/matches/api/image/${encodeURIComponent(group.name)}/${encodeURIComponent(item.name)}/scene`;
      thumb.appendChild(image);
      const name = document.createElement('span'); name.className = 'sample-name';
      name.textContent = `(${index + 1}) ${item.name}`;
      if (item.reviewed) {
        const count = document.createElement('span'); count.className = 'sample-count';
        count.textContent = `✓ ${item.matches} matches`; name.appendChild(count);
      }
      button.append(thumb, name); row.appendChild(button); $('sample-list').appendChild(row);
      button.onclick = () => {
        if (item.name === $('sample').value || !acceptNavigation()) return;
        $('sample').value = item.name; load();
      };
    }
    $('dataset-info').textContent = group ? `${group.samples.length} OCR scenes · ${group.error_count} OCR error reports excluded` : 'No OCR datasets found in the matches folder.';
  }
  function acceptNavigation() {
    if (busy) return false;
    return !dirty() || window.confirm('Discard unsaved matches for this scene?');
  }
  function restoreSelects() { if (data) { $('template').value = data.template_name; populateSamples(); $('sample').value = data.sample_name; controls(); } }
  async function load() {
    const t = $('template').value, s = $('sample').value;
    data = null; pairs = []; proposals = []; dismissed = new Set(); savedState = '[]'; selected = null; history = []; future = []; board.replaceChildren(); renderList(); renderPredictions();
    if (!t || !s) { status('No OCR scenes available.'); controls(); return; }
    busy = true; controls(); status('Loading OCR points and images…');
    try {
      const result = await api(`/matches/api/pair/${encodeURIComponent(t)}/${encodeURIComponent(s)}`);
      const base = `/matches/api/image/${encodeURIComponent(t)}/${encodeURIComponent(s)}`;
      await Promise.all(['template','scene'].map(side => new Promise((resolve,reject) => { const image = new Image(); image.onload = resolve; image.onerror = () => reject(new Error(`Could not load ${side} image.`)); image.src = `${base}/${side}`; })));
      data = result; pairs = clone(result.pairs); savedState = JSON.stringify(pairs);
      proposals = result.predictions?.pairs || [];
      $('predictions-panel').open = proposals.length > 0;
      $('template-name').textContent = t; $('scene-name').textContent = s;
      for (const [index,side] of ['template','scene'].entries()) {
        const info = data[side], scale = Math.min(820/info.width, 780/info.height);
        layout[side] = {x:30 + index * 900 + (820-info.width*scale)/2, y:45+(780-info.height*scale)/2, scale};
      }
      view = [0,0,1800,900]; render();
    } catch (error) { status(error.message, true); }
    finally { busy = false; controls(); renderList(); renderPredictions(); }
  }
  const position = (side,p) => ({x: layout[side].x + p.x*layout[side].scale, y:layout[side].y + p.y*layout[side].scale});
  function availability() {
    const used = {template:new Set(pairs.map(p=>p.template_id)), scene:new Set(pairs.map(p=>p.scene_id))};
    const counts = {template:new Map(),scene:new Map()};
    for (const side of ['template','scene']) {
      for (const p of data[side].points) {
        const key = canonical(p.label);
        if (key && !used[side].has(p.id)) counts[side].set(key, (counts[side].get(key) || 0) + 1);
      }
    }
    return {used, counts};
  }
  function render() {
    if (!data) return;
    board.replaceChildren(); board.setAttribute('viewBox', view.join(' '));
    const base = `/matches/api/image/${encodeURIComponent(data.template_name)}/${encodeURIComponent(data.sample_name)}`;
    for (const side of ['template','scene']) { const l = layout[side]; svg('image',{href:`${base}/${side}`,x:l.x,y:l.y,width:data[side].width*l.scale,height:data[side].height*l.scale}); }
    const pointMap = {template:new Map(data.template.points.map(p=>[p.id,p])),scene:new Map(data.scene.points.map(p=>[p.id,p]))};
    pairs.forEach((pair,index) => { const a = position('template',pointMap.template.get(pair.template_id)), b = position('scene',pointMap.scene.get(pair.scene_id)); svg('path',{d:`M${a.x},${a.y} L885,${a.y} L915,${b.y} L${b.x},${b.y}`,stroke:color(index),class:'match-line',opacity:selected ? .2 : .75}); });
    for (const pair of availablePredictions()) {
      const a = position('template', pointMap.template.get(pair.template_id));
      const b = position('scene', pointMap.scene.get(pair.scene_id));
      svg('path', {d: `M${a.x},${a.y} L885,${a.y} L915,${b.y} L${b.x},${b.y}`, class: 'prediction-line'});
    }
    const {used,counts} = availability();
    // Maintain point sizes in screen pixels while zooming into dense OCR regions.
    const unit = Math.max(view[2]/Math.max(board.clientWidth,1),view[3]/Math.max(board.clientHeight,1));
    for (const side of ['template','scene']) {
      const opposite = side === 'template' ? 'scene' : 'template';
      for (const p of data[side].points) {
        const matched = used[side].has(p.id);
        const available = !!canonical(p.label) && !matched && !!counts[opposite].get(canonical(p.label));
        if (selected && selected.side !== side && (!available || !sameLabel(selected.label, p.label))) continue;
        const xy = position(side,p), active = selected?.side === side && selected.id === p.id;
        const g = svg('g',{transform:`translate(${xy.x} ${xy.y})`,class:available?'ocr-point':'unavailable','data-side':side,'data-id':p.id,'aria-label':`${side} ${p.label || 'unrecognized'} point ${p.id}${available ? '' : ', no available matches'}`});
        const title = svg('title',{},g); title.textContent = `${p.label || 'Unrecognized'} · point ${p.id} · ${matched?'already matched':available?`${counts[opposite].get(canonical(p.label))} candidates`:'no available match'}`;
        if (available) {
          g.setAttribute('role','button'); g.setAttribute('tabindex','0');
          svg('circle',{r:6*unit,class:'hit'},g);
          svg('circle',{r:(active?5:3)*unit,fill:active?'#ffb52b':'#f8fafc',stroke:active?'#9e5a00':'#193c55','stroke-width':unit,class:'marker'},g);
          g.addEventListener('click', event=>{event.stopPropagation(); choose(side,p);});
          g.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(side,p);}});
        } else {
          const matchIndex = pairs.findIndex(pair=>pair[`${side}_id`]===p.id);
          svg('path',{d:`M${-2.8*unit},${-2.8*unit} L${2.8*unit},${2.8*unit} M${-2.8*unit},${2.8*unit} L${2.8*unit},${-2.8*unit}`,stroke:matched?color(matchIndex):'#737c88','stroke-width':1.4*unit,'pointer-events':'none'},g);
        }
        if ($('labels').checked) { const text = svg('text',{x:5*unit,y:-5*unit,'font-size':10*unit,'stroke-width':2*unit},g); text.textContent=p.label || '?'; }
      }
    }
    renderList(); renderPredictions(); controls();
    if (selected) { const opposite=selected.side==='template'?'scene':'template'; status(`Selected “${selected.label}” on ${selected.side} · ${counts[opposite].get(canonical(selected.label))||0} candidates. Click its counterpart to confirm, or press Esc.`); }
    else status(`${pairs.length} confirmed matches. Select a character on either image to see its available counterparts.`);
  }
  function choose(side,p) {
    if(busy) return;
    if(selected && selected.side!==side) {
      if(!sameLabel(selected.label,p.label)) return;
      history.push(clone(pairs)); future=[];
      pairs.push(side==='scene'?{template_id:selected.id,scene_id:p.id}:{template_id:p.id,scene_id:selected.id}); selected=null;
    } else selected=selected?.side===side&&selected.id===p.id?null:{side,...p};
    render();
  }
  function renderList() {
    const list=$('match-list'); list.replaceChildren();
    if(!pairs.length){const p=document.createElement('p');p.className='empty';p.textContent='No confirmed matches yet.';list.appendChild(p);return;}
    pairs.forEach((pair,index)=>{
      const row=document.createElement('div');row.className='match-row';
      const swatch=document.createElement('span');swatch.className='swatch';swatch.style.background=color(index);
      const label=document.createElement('strong');label.textContent=data.template.points.find(p=>p.id===pair.template_id).label;
      const ids=document.createElement('span');ids.className='ids';ids.textContent=`#${pair.template_id} ↔ #${pair.scene_id}`;
      const remove=document.createElement('button');remove.textContent='×';remove.title='Remove match';remove.setAttribute('aria-label',`Remove match ${pair.template_id} to ${pair.scene_id}`);remove.disabled=busy;
      remove.onclick=()=>{history.push(clone(pairs));future=[];pairs.splice(index,1);selected=null;render();};
      row.append(swatch,label,ids,remove);list.appendChild(row);
    });
  }
  const predictionKey = pair => `${pair.template_id}:${pair.scene_id}`;
  function availablePredictions() {
    const usedTemplate = new Set(pairs.map(p => p.template_id));
    const usedScene = new Set(pairs.map(p => p.scene_id));
    return proposals.filter(p => !dismissed.has(predictionKey(p)) && !usedTemplate.has(p.template_id) && !usedScene.has(p.scene_id));
  }
  function acceptPredictions(items) {
    if (busy || !items.length) return;
    history.push(clone(pairs)); future = [];
    pairs.push(...items.map(p => ({template_id: p.template_id, scene_id: p.scene_id})));
    selected = null; render();
    status(`${items.length} prediction${items.length === 1 ? '' : 's'} accepted. Review and Save to keep these matches.`);
  }
  function renderPredictions() {
    const list = $('prediction-list'), available = availablePredictions();
    list.replaceChildren(); $('prediction-count').textContent = available.length;
    if (!available.length) {
      const text = document.createElement('p'); text.className = 'empty';
      text.textContent = proposals.length ? 'No unused predictions remain.' : 'Click Predict matches for suggestions.';
      list.appendChild(text); return;
    }
    for (const pair of available) {
      const row = document.createElement('div'); row.className = 'prediction-row';
      const label = document.createElement('span');
      const point = data.template.points.find(p => p.id === pair.template_id);
      label.textContent = `${point.label} #${pair.template_id} ↔ #${pair.scene_id}`;
      const accept = document.createElement('button'); accept.className = 'btn'; accept.textContent = 'Accept'; accept.disabled = busy;
      accept.onclick = () => acceptPredictions([pair]);
      const reject = document.createElement('button'); reject.className = 'btn'; reject.textContent = '×'; reject.title = 'Dismiss prediction'; reject.setAttribute('aria-label', `Dismiss prediction ${pair.template_id} to ${pair.scene_id}`); reject.disabled = busy;
      reject.onclick = () => { dismissed.add(predictionKey(pair)); render(); };
      row.append(label, accept, reject); list.appendChild(row);
    }
  }
  $('accept-predictions').onclick = () => acceptPredictions(availablePredictions());
  $('predict').onclick = async () => {
    if (!data || busy) return;
    busy = true; selected = null; controls(); renderList(); renderPredictions();
    $('save-state').textContent = 'Predicting…';
    status('Running object detection match predictions on the saved OCR points…');
    try {
      const result = await api(`/matches/api/predictions/${encodeURIComponent(data.template_name)}/${encodeURIComponent(data.sample_name)}`, {method: 'POST'});
      if (JSON.stringify(result.fingerprints) !== JSON.stringify(data.fingerprints)) throw new Error('Inputs changed. Reload this scene before using predictions.');
      proposals = result.pairs; dismissed = new Set(); $('predictions-panel').open = true;
      render();
      status(`${availablePredictions().length} predictions available. Accept individually or all at once.${result.skipped ? ` ${result.skipped} incompatible predictions were excluded.` : ''}`);
    } catch (error) { status(error.message, true); }
    finally { busy = false; controls(); renderList(); renderPredictions(); }
  };
  async function save() {
    if(!data||busy||!dirty()) return;
    busy=true;controls();renderList();$('save-state').textContent='Saving…';
    try { const saved=await api(endpoint(),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({pairs,revision:data.revision,fingerprints:data.fingerprints})}); data.revision=saved.revision;savedState=JSON.stringify(pairs);const item=catalog.find(t=>t.name===data.template_name).samples.find(s=>s.name===data.sample_name);item.matches=pairs.length;item.reviewed=true;populateSamples();$('sample').value=data.sample_name;status('Matches saved.'); }
    catch(error){status(error.message,true);}
    finally{busy=false;controls();renderList();renderPredictions();}
  }
  $('save').onclick=save;
  $('template').onchange=()=>{if(!acceptNavigation()){restoreSelects();return;}populateSamples();load();};
  $('sample').onchange=()=>{if(!acceptNavigation()){restoreSelects();return;}load();};
  function navigate(delta){const next=$('sample').selectedIndex+delta;if(next<0||next>=$('sample').options.length||!acceptNavigation())return;$('sample').selectedIndex=next;load();}
  $('previous').onclick=()=>navigate(-1);$('next').onclick=()=>navigate(1);
  $('undo').onclick=()=>{if(busy||!history.length)return;future.push(clone(pairs));pairs=history.pop();selected=null;render();};
  $('redo').onclick=()=>{if(busy||!future.length)return;history.push(clone(pairs));pairs=future.pop();selected=null;render();};
  $('deselect').onclick=()=>{selected=null;render();};$('labels').onchange=render;
  function zoom(factor,point){if(!data)return;const width=Math.max(180,Math.min(3600,view[2]*factor));factor=width/view[2];const p=point||{x:view[0]+view[2]/2,y:view[1]+view[3]/2};view=[p.x+(view[0]-p.x)*factor,p.y+(view[1]-p.y)*factor,width,view[3]*factor];render();}
  const localPoint=event=>new DOMPoint(event.clientX,event.clientY).matrixTransform(board.getScreenCTM().inverse());
  board.addEventListener('wheel',event=>{event.preventDefault();zoom(event.deltaY>0?1.13:1/1.13,localPoint(event));},{passive:false});
  board.addEventListener('pointerdown',event=>{if(event.target.closest('.ocr-point')||event.button!==0)return;drag={start:localPoint(event),view:[...view]};board.setPointerCapture(event.pointerId);board.classList.add('panning');});
  board.addEventListener('pointermove',event=>{if(!drag)return;const point=localPoint(event);view[0]+=drag.start.x-point.x;view[1]+=drag.start.y-point.y;board.setAttribute('viewBox',view.join(' '));});
  const stopDrag=()=>{if(!drag)return;drag=null;board.classList.remove('panning');render();};
  board.addEventListener('pointerup',stopDrag);board.addEventListener('pointercancel',stopDrag);
  $('zoom-range').oninput=()=>zoom((180000 / Number($('zoom-range').value)) / view[2]);$('fit').onclick=()=>{view=[0,0,1800,900];render();};
  $('export').onclick=()=>{const payload={schema_version:1,template_name:data.template_name,sample_name:data.sample_name,fingerprints:data.fingerprints,coordinate_spaces:{template:data.template.coordinate_space,scene:data.scene.coordinate_space},template_points:data.template.points,scene_points:data.scene.points,pairs};const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`${data.template_name}__${data.sample_name}__matches.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  window.addEventListener('beforeunload',event=>{if(dirty()){event.preventDefault();event.returnValue='';}});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){$('deselect').click();}if((event.ctrlKey||event.metaKey)&&event.key==='s'){event.preventDefault();save();}if((event.ctrlKey||event.metaKey)&&event.key==='z'&&!['INPUT','SELECT','TEXTAREA'].includes(event.target.tagName)){event.preventDefault();$(event.shiftKey?'redo':'undo').click();}});
  new ResizeObserver(()=>{if(data&&!drag)render();}).observe(board);
  const header = document.querySelector('.hdr-wrap');
  if (header) new ResizeObserver(() => {
    document.documentElement.style.setProperty('--top', `${Math.ceil(header.getBoundingClientRect().height)}px`);
  }).observe(header);
  api('/matches/api/catalog').then(result=>{catalog=result;for(const group of catalog)$('template').add(new Option(group.name,group.name));populateSamples();return load();}).catch(error=>status(error.message,true));
})();
