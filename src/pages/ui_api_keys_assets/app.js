// Standalone API key management logic shared with the builder integration panel.

async () => {
  const state = {
    apiKeys: [],
    apiKeyHeader: 'X-API-Key',
    endpointTemplate: '/external/apis/{api_id}',
  };

  const keyStatus = document.getElementById('api-key-status');
  const keyList = document.getElementById('api-key-list');
  const keySecretWrap = document.getElementById('api-key-secret-wrap');
  const keySecretInp = document.getElementById('api-key-secret');
  const copyKeyBtn = document.getElementById('btn-copy-key');
  const btnGenerateKey = document.getElementById('btn-generate-key');
  const keyHint = document.getElementById('api-key-hint');
  const keyHeaderLabel = document.getElementById('api-key-header');
  const endpointTemplateLabel = document.getElementById('api-endpoint-template');
  const labelInput = document.getElementById('api-key-label');

  if (copyKeyBtn) copyKeyBtn.disabled = true;
  if (btnGenerateKey) btnGenerateKey.disabled = false;

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatDateString(value) {
    if (!value) return '';
    try {
      const d = new Date(value);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleString();
      }
    } catch {}
    return String(value ?? '');
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
    const prev = btn.dataset.prevLabel || btn.textContent || 'Copy';
    btn.dataset.prevLabel = prev;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = btn.dataset.prevLabel || prev; }, 1500);
  }

  function updateEndpointTemplate(meta) {
    if (!endpointTemplateLabel) return;
    const tpl = meta && meta.endpoint_template ? meta.endpoint_template : '/external/apis/{api_id}';
    endpointTemplateLabel.textContent = tpl;
  }

  function renderSecret({ showSecret = false, secretValue = '' } = {}) {
    if (!keySecretWrap) return;
    if (showSecret && secretValue) {
      keySecretInp.value = secretValue;
      keySecretWrap.classList.remove('hidden');
      if (copyKeyBtn) copyKeyBtn.disabled = false;
      if (keyHint) keyHint.textContent = 'Copy this key now; it will not be shown again.';
    } else {
      keySecretInp.value = '';
      keySecretWrap.classList.add('hidden');
      if (copyKeyBtn) copyKeyBtn.disabled = true;
      if (keyHint) keyHint.textContent = 'Keys are shown only once—store them securely and describe how you use them.';
    }
  }

  function renderHeader(meta) {
    const headerName = (meta && meta.header) ? meta.header : 'X-API-Key';
    state.apiKeyHeader = headerName;
    if (keyHeaderLabel) keyHeaderLabel.textContent = headerName;
    const endpoint = meta && meta.endpoint_template ? meta.endpoint_template : '/external/apis/{api_id}';
    state.endpointTemplate = endpoint;
    updateEndpointTemplate({ endpoint_template: endpoint });
  }

  function renderKeys() {
    if (!keyList) return;
    keyList.innerHTML = '';

    if (!Array.isArray(state.apiKeys) || state.apiKeys.length === 0) {
      if (keyStatus) keyStatus.textContent = 'No API keys yet.';
      return;
    }

    if (keyStatus) keyStatus.textContent = `${state.apiKeys.length} active ${state.apiKeys.length === 1 ? 'key' : 'keys'}.`;

    state.apiKeys.forEach((key) => {
      const item = document.createElement('div');
      item.className = 'api-key-item';
      item.dataset.keyId = String(key.id);

      const prefixLabel = key.key_prefix ? `${key.key_prefix}…` : 'Key';
      const createdLabel = key.created_at ? `Created ${formatDateString(key.created_at)}` : '';
      const usedLabel = key.last_used_at ? `Last used ${formatDateString(key.last_used_at)}` : '';
      const metaPieces = [createdLabel, usedLabel].filter(Boolean);
      const description = key.label ? escapeHtml(key.label) : 'No description provided.';

      item.innerHTML = `
        <div class="api-key-item-details">
          <div class="api-key-prefix">${escapeHtml(prefixLabel)}</div>
          <div class="api-key-description">${description}</div>
          <div class="api-key-meta">${metaPieces.join(' • ')}</div>
        </div>
        <div class="api-key-item-actions">
          <button class="btn small danger" type="button" data-action="delete" data-key-id="${escapeHtml(key.id)}">Delete</button>
        </div>
      `;

      keyList.appendChild(item);
    });
  }

  async function refreshApiKeys({ silent = false } = {}) {
    if (keyStatus && !silent) keyStatus.textContent = 'Loading…';
    renderSecret({ showSecret: false });

    try {
      const res = await fetch('/builder/api-key', {
        credentials: 'include',
      });
      if (res.status === 401) {
        if (!silent && keyStatus) keyStatus.textContent = 'Sign in to manage API keys.';
        state.apiKeys = [];
        renderKeys();
        if (btnGenerateKey) btnGenerateKey.disabled = true;
        return;
      }
      if (!res.ok) throw new Error('status');
      const meta = await res.json();
      state.apiKeys = Array.isArray(meta.keys) ? meta.keys : [];
      renderHeader(meta);
      renderKeys();
      if (btnGenerateKey) btnGenerateKey.disabled = false;
    } catch {
      if (!silent && keyStatus) keyStatus.textContent = 'Failed to load API keys';
      state.apiKeys = [];
      renderKeys();
      if (btnGenerateKey) btnGenerateKey.disabled = false;
    }
  }

  if (copyKeyBtn) {
    copyKeyBtn.onclick = async () => {
      if (!keySecretInp || !keySecretInp.value) return;
      const ok = await copyToClipboard(keySecretInp.value);
      if (ok) flashButton(copyKeyBtn);
      else window.alert('Unable to copy key automatically. Please copy it manually.');
    };
  }

  if (btnGenerateKey) {
    btnGenerateKey.onclick = async () => {
      if (btnGenerateKey.disabled) return;
      btnGenerateKey.disabled = true;
      if (keyStatus) keyStatus.textContent = 'Generating key…';

      const body = {
        label: labelInput ? labelInput.value : '',
      };

      try {
        const res = await fetch('/builder/api-key', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        });
        if (res.status === 401) {
          if (keyStatus) keyStatus.textContent = 'Sign in to generate keys.';
          btnGenerateKey.disabled = false;
          return;
        }
        if (!res.ok) throw new Error('create');
        const data = await res.json();
        if (labelInput) labelInput.value = '';
        if (data && data.key) {
          state.apiKeys = [data.key, ...state.apiKeys];
          renderKeys();
          renderHeader({ header: data.header });
        } else {
          await refreshApiKeys({ silent: true });
        }
        renderSecret({ showSecret: !!data.api_key, secretValue: data.api_key || '' });
        if (keyStatus) keyStatus.textContent = 'Key created.';
      } catch {
        if (keyStatus) keyStatus.textContent = 'Failed to generate key';
      } finally {
        btnGenerateKey.disabled = false;
      }
    };
  }

  if (keyList) {
    keyList.addEventListener('click', async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const action = target.dataset.action;
      const keyId = target.dataset.keyId;
      if (action !== 'delete' || !keyId) return;

      const confirmed = window.confirm('Delete this API key? Any requests using it will stop working.');
      if (!confirmed) return;

      const btn = target;
      btn.disabled = true;
      const prevLabel = btn.textContent;
      btn.textContent = 'Deleting…';

      try {
        const res = await fetch(`/builder/api-key/${encodeURIComponent(keyId)}`, {
          method: 'DELETE',
          credentials: 'include',
        });
        if (res.status === 401) {
          window.alert('Sign in to delete API keys.');
          btn.disabled = false;
          btn.textContent = prevLabel;
          return;
        }
        if (res.status === 404) {
          window.alert('API key not found or already deleted.');
        }
        if (!res.ok) throw new Error('delete');
        state.apiKeys = state.apiKeys.filter((key) => String(key.id) !== String(keyId));
        renderKeys();
        if (keyStatus) keyStatus.textContent = 'Key removed.';
      } catch {
        window.alert('Failed to delete API key. Please try again.');
        btn.disabled = false;
        btn.textContent = prevLabel;
        return;
      }

      btn.disabled = false;
      btn.textContent = prevLabel;
    });
  }

  await refreshApiKeys();
}
