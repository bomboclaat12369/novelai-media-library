from pathlib import Path

src = Path('payload/userscript-2.7.3.patch01.txt')
dst = Path('payload/userscript-2.7.4.patch01.txt')
text = src.read_text(encoding='utf-8')

text = text.replace('v2.7.3: Review queue, queue filmstrip/sets, video favorites, resilient imports',
                    'v2.7.4: status-tracked imports, Review queue, queue filmstrip/sets, video favorites', 1)
text = text.replace('naiMediaV273', 'naiMediaV274')

# Strip the original Add Media button listeners by replacing the buttons whenever the
# base modal is created. This makes our import handler the sole owner of those clicks.
marker = '''  modalRoot.addEventListener('change', event => {
'''
hook = '''  function hookImportModal274() {
    const dropZone = modalRoot.querySelector('#fileDropZone');
    if (!dropZone) return;
    syncImportModalMirror();

    for (const id of ['importDirect', 'importReview']) {
      const oldButton = modalRoot.querySelector(`#${id}`);
      if (!oldButton || oldButton.dataset.naiOwnImport274 === '1') continue;
      const fresh = oldButton.cloneNode(true);
      fresh.dataset.naiOwnImport274 = '1';
      oldButton.replaceWith(fresh);
      fresh.addEventListener('click', event => {
        event.preventDefault();
        event.stopImmediatePropagation();
        runOwnImport(id === 'importReview').catch(err => {
          importBusy = false;
          activeUploadHandle = null;
          alert(err?.message || String(err));
        });
      });
    }
    modalRoot.querySelectorAll('[data-close]').forEach(el => { el.disabled = false; });
  }

  const importModalObserver274 = new MutationObserver(() => queueMicrotask(hookImportModal274));
  importModalObserver274.observe(modalRoot, {childList:true, subtree:true});
  queueMicrotask(hookImportModal274);

'''
if marker not in text:
    raise SystemExit('import change-listener marker not found')
text = text.replace(marker, hook + marker, 1)

# Replace local-file import with a token/status protocol. The POST response is no longer
# authoritative: completion comes from /api/import/status/<token>, so a stuck userscript
# upload response cannot strand the UI after the companion has already saved the file.
start_marker = '  async function uploadFileResilient(file, characterId, categories) {\n'
end_marker = '  async function confirmImportedUrl(characterId, url, beforeIds, categories, beforeItem, deadlineMs=120000) {\n'
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('uploadFileResilient markers not found')
replacement = '''  function importToken274() {
    try { return `nai_${crypto.randomUUID().replace(/-/g, '')}`; }
    catch (_) { return `nai_${Date.now()}_${Math.random().toString(36).slice(2)}`; }
  }

  async function importJobStatus274(token) {
    const path = `/api/import/status/${encodeURIComponent(token)}`;
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 3500);
      try {
        const res = await fetch(`${API}${path}?cb=${Date.now()}-${Math.random()}`, {
          method:'GET', cache:'no-store', signal:controller.signal,
        });
        if (res.ok) return await res.json();
      } finally { clearTimeout(timer); }
    } catch (_) {}
    try { return await gmRequest({path, timeout:5000}); }
    catch (_) { return null; }
  }

  async function uploadFileResilient(file, characterId, categories) {
    const token = importToken274();
    const query = new URLSearchParams({
      character_id: characterId,
      filename: file.name || 'upload',
      categories: JSON.stringify(Array.isArray(categories) ? categories : []),
      token,
    });

    let requestError = null;
    activeUploadHandle = GM_xmlhttpRequest({
      method:'POST',
      url:`${API}/api/import/raw?${query.toString()}`,
      data:file,
      timeout:300000,
      headers:{'Content-Type': file.type || 'application/octet-stream'},
      onload:res => {
        // The status endpoint is authoritative. Only remember HTTP failures here.
        if (!(res.status >= 200 && res.status < 300)) {
          let message = `Request failed (${res.status})`;
          try { message = JSON.parse(res.responseText || '{}').error || message; } catch (_) {}
          requestError = new Error(message);
        }
      },
      onerror:()=>{ requestError = new Error(importCancel ? 'Import canceled' : 'Could not connect to the local NovelAI Media Library program.'); },
      ontimeout:()=>{ requestError = new Error(importCancel ? 'Import canceled' : 'The local media request timed out.'); },
      onabort:()=>{},
    });

    const sizeMiB = Math.max(1, (file.size || 0) / (1024 * 1024));
    const maxWait = Math.min(15 * 60 * 1000, Math.max(120000, sizeMiB * 8000));
    const deadline = Date.now() + maxWait;
    let sawJob = false;

    while (!importCancel && Date.now() < deadline) {
      const status = await importJobStatus274(token);
      if (status?.state && status.state !== 'unknown') sawJob = true;
      if (status?.state === 'done' && status.item?.id) {
        try { activeUploadHandle?.abort?.(); } catch (_) {}
        activeUploadHandle = null;
        return {item:status.item, duplicate:!!status.duplicate, confirmed:true};
      }
      if (status?.state === 'error') {
        try { activeUploadHandle?.abort?.(); } catch (_) {}
        activeUploadHandle = null;
        throw new Error(status.error || 'The companion could not finish the import.');
      }
      // If the request failed before the companion ever created the job, surface that
      // rather than waiting the full timeout. Once the job exists, keep polling it.
      if (requestError && !sawJob) {
        await sleep(400);
        const retry = await importJobStatus274(token);
        if (!retry || retry.state === 'unknown') {
          try { activeUploadHandle?.abort?.(); } catch (_) {}
          activeUploadHandle = null;
          throw requestError;
        }
        sawJob = true;
        if (retry.state === 'done' && retry.item?.id) return {item:retry.item, duplicate:!!retry.duplicate, confirmed:true};
        if (retry.state === 'error') throw new Error(retry.error || 'The companion could not finish the import.');
      }
      await sleep(250);
    }

    try { activeUploadHandle?.abort?.(); } catch (_) {}
    activeUploadHandle = null;
    if (importCancel) throw new Error('Import canceled');
    throw requestError || new Error('Import timed out before the companion confirmed completion.');
  }

'''
text = text[:start] + replacement + text[end:]

old_close = '''  modalRoot.addEventListener('click', event => {
    if (event.target?.closest?.('#clearFiles')) {
      mirroredFiles = [];
      return;
    }
    if (!importBusy || !event.target?.closest?.('[data-close]')) return;
    importCancel = true;
    try { activeUploadHandle?.abort?.(); } catch (_) {}
    activeUploadHandle = null;
  }, true);
'''
new_close = '''  modalRoot.addEventListener('click', event => {
    if (event.target?.closest?.('#clearFiles')) {
      mirroredFiles = [];
      return;
    }
    if (!importBusy || !event.target?.closest?.('[data-close]')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    importCancel = true;
    importBusy = false;
    try { activeUploadHandle?.abort?.(); } catch (_) {}
    activeUploadHandle = null;
    mirroredFiles = [];
    modalRoot.innerHTML = '';
    refreshBtn?.click();
    schedulePseudoSync();
    scheduleMainFilter();
  }, true);
'''
if old_close not in text:
    raise SystemExit('busy modal close handler not found')
text = text.replace(old_close, new_close, 1)

old_disable = "    modalRoot.querySelectorAll('button,input,textarea').forEach(el => { if (!el.matches('[data-close]')) el.disabled = true; });\n"
new_disable = old_disable + "    modalRoot.querySelectorAll('[data-close]').forEach(el => { el.disabled = false; });\n"
if old_disable not in text:
    raise SystemExit('import disable marker not found')
text = text.replace(old_disable, new_disable, 1)

# Keep a capture-phase backup in case the modal is clicked before the observer microtask
# gets a chance to clone the buttons. importBusy prevents a duplicate start.
old_root = '''  root.addEventListener('click', event => {
    const button = event.target?.closest?.('#importReview,#importDirect');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    runOwnImport(button.id === 'importReview').catch(err => {
      importBusy = false;
      alert(err?.message || String(err));
    });
  }, true);
'''
new_root = '''  root.addEventListener('click', event => {
    const button = event.target?.closest?.('#importReview,#importDirect');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    runOwnImport(button.id === 'importReview').catch(err => {
      importBusy = false;
      activeUploadHandle = null;
      alert(err?.message || String(err));
    });
  }, true);
'''
if old_root not in text:
    raise SystemExit('root import capture handler not found')
text = text.replace(old_root, new_root, 1)

# Sanity checks: this build must own the Add Media buttons and use token status imports.
required = [
    'naiMediaV274',
    'hookImportModal274',
    '/api/import/status/',
    'token,',
    'dataset.naiOwnImport274',
]
for needle in required:
    if needle not in text:
        raise SystemExit(f'missing required v2.7.4 marker: {needle}')

# Ensure the old local-file completion race is no longer active.
local_start = text.find('  async function uploadFileResilient(file, characterId, categories) {')
local_end = text.find('  async function confirmImportedUrl', local_start)
local_block = text[local_start:local_end]
if 'confirmImportedFile(' in local_block or 'Promise.race' in local_block:
    raise SystemExit('old local-file completion race is still present')

dst.write_text(text, encoding='utf-8')
print(f'wrote {dst} ({len(text)} chars)')
