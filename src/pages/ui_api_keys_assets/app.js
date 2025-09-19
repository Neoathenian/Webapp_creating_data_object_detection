// Standalone API key management logic reused from the builder integration panel.

async () => {
  const state = {
    apiKeyMeta: null,
  };

  const keyStatus = document.getElementById('api-key-status');
  const keySecretWrap = document.getElementById('api-key-secret-wrap');
  const keySecretInp = document.getElementById('api-key-secret');
  const copyKeyBtn = document.getElementById('btn-copy-key');
  const btnGenerateKey = document.getElementById('btn-generate-key');
  const btnDeleteKey = document.getElementById('btn-delete-key');
  const keyHint = document.getElementById('api-key-hint');
  const keyHeaderLabel = document.getElementById('api-key-header');
  const endpointTemplateLabel = document.getElementById('api-endpoint-template');

  if (copyKeyBtn) copyKeyBtn.disabled = true;
  if (btnDeleteKey) btnDeleteKey.disabled = true;

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

  function updateApiKeySection(meta, { showSecret = false, secretValue = '' } = {}) {
    state.apiKeyMeta = meta || null;

    const headerName = meta && meta.header ? meta.header : 'X-API-Key';
    if (keyHeaderLabel) keyHeaderLabel.textContent = headerName;
    updateEndpointTemplate(meta);

    if (keySecretWrap) {
      if (showSecret && secretValue) {
        keySecretInp.value = secretValue;
        keySecretWrap.classList.remove('hidden');
        if (copyKeyBtn) copyKeyBtn.disabled = false;
        if (keyHint) keyHint.textContent = 'Copy this key now; it will not be shown again.';
      } else {
        keySecretInp.value = '';
        keySecretWrap.classList.add('hidden');
        if (copyKeyBtn) copyKeyBtn.disabled = true;
        if (keyHint) keyHint.textContent = 'Generate a key to authenticate requests. Keys are shown only once—store it securely.';
      }
    }

    if (!keyStatus) return;

    if (!meta || !meta.has_key) {
      keyStatus.textContent = 'No API key yet.';
      if (btnDeleteKey) btnDeleteKey.disabled = true;
      if (btnGenerateKey) btnGenerateKey.textContent = 'Generate key';
      return;
    }

    const parts = [];
    const prefix = meta.key_prefix ? `${meta.key_prefix}…` : 'Active key';
    parts.push(prefix);
    if (meta.created_at) parts.push(`created ${formatDateString(meta.created_at)}`);
    if (meta.last_used_at) parts.push(`last used ${formatDateString(meta.last_used_at)}`);
    keyStatus.textContent = parts.join(' • ');

    if (btnDeleteKey) btnDeleteKey.disabled = false;
    if (btnGenerateKey) btnGenerateKey.textContent = 'Regenerate key';
    if (keyHint && !showSecret) {
      keyHint.textContent = 'Regenerating deletes the previous key immediately. Update any integrations before rotating again.';
    }
  }

  async function refreshApiKeyStatus({ silent = false } = {}) {
    if (keyStatus && !silent) keyStatus.textContent = 'Loading…';
    try {
      const res = await fetch('/builder/api-key', {
        credentials: 'include',
      });
      if (res.status === 401) {
        if (!silent && keyStatus) keyStatus.textContent = 'Sign in to manage API keys.';
        state.apiKeyMeta = null;
        if (btnDeleteKey) btnDeleteKey.disabled = true;
        if (copyKeyBtn) copyKeyBtn.disabled = true;
        if (keySecretWrap) {
          keySecretInp.value = '';
          keySecretWrap.classList.add('hidden');
        }
        return;
      }
      if (!res.ok) throw new Error('status');
      const meta = await res.json();
      updateApiKeySection(meta);
    } catch {
      if (!silent && keyStatus) keyStatus.textContent = 'Failed to load API key';
      if (btnDeleteKey) btnDeleteKey.disabled = true;
      if (copyKeyBtn) copyKeyBtn.disabled = true;
      if (keySecretWrap) {
        keySecretInp.value = '';
        keySecretWrap.classList.add('hidden');
      }
      state.apiKeyMeta = null;
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
      if (state.apiKeyMeta && state.apiKeyMeta.has_key) {
        const confirmed = window.confirm('Generate a new key? Existing integrations using the old key will stop working.');
        if (!confirmed) return;
      }
      btnGenerateKey.disabled = true;
      if (keyStatus) keyStatus.textContent = 'Generating key…';
      try {
        const res = await fetch('/builder/api-key', {
          method: 'POST',
          credentials: 'include',
        });
        if (res.status === 401) {
          if (keyStatus) keyStatus.textContent = 'Sign in to generate keys.';
          state.apiKeyMeta = null;
          if (copyKeyBtn) copyKeyBtn.disabled = true;
          return;
        }
        if (!res.ok) throw new Error('rotate');
        const data = await res.json();
        const meta = {
          has_key: true,
          key_prefix: data.key_prefix || '',
          created_at: data.created_at || null,
          last_used_at: null,
          header: data.header || (state.apiKeyMeta ? state.apiKeyMeta.header : 'X-API-Key'),
          endpoint_template: state.apiKeyMeta ? state.apiKeyMeta.endpoint_template : '/external/apis/{api_id}',
        };
        updateApiKeySection(meta, { showSecret: !!data.api_key, secretValue: data.api_key || '' });
      } catch {
        if (keyStatus) keyStatus.textContent = 'Failed to generate key';
      } finally {
        btnGenerateKey.disabled = false;
      }
    };
  }

  if (btnDeleteKey) {
    btnDeleteKey.onclick = async () => {
      if (btnDeleteKey.disabled || !(state.apiKeyMeta && state.apiKeyMeta.has_key)) return;
      const confirmed = window.confirm('Delete the current API key? Any requests using it will be rejected.');
      if (!confirmed) return;
      btnDeleteKey.disabled = true;
      if (keyStatus) keyStatus.textContent = 'Deleting key…';
      try {
        const res = await fetch('/builder/api-key', {
          method: 'DELETE',
          credentials: 'include',
        });
        if (res.status === 401) {
          if (keyStatus) keyStatus.textContent = 'Sign in to delete keys.';
          if (state.apiKeyMeta && state.apiKeyMeta.has_key) btnDeleteKey.disabled = false;
          return;
        }
        if (!res.ok) throw new Error('delete');
        await refreshApiKeyStatus({ silent: true });
      } catch {
        if (keyStatus) keyStatus.textContent = 'Failed to delete key';
        if (state.apiKeyMeta && state.apiKeyMeta.has_key) btnDeleteKey.disabled = false;
        return;
      }
      if (keyHint) keyHint.textContent = 'Generate a key to authenticate requests. Keys are shown only once—store it securely.';
      if (copyKeyBtn) copyKeyBtn.disabled = true;
    };
  }

  await refreshApiKeyStatus();
}
