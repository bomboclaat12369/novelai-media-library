from pathlib import Path

src = Path('payload/userscript-2.7.1.patch01.txt')
out = Path('payload/userscript-2.7.2.patch01.txt')
text = src.read_text(encoding='utf-8')

text = text.replace('// NovelAI Media Library v2.7.1:', '// NovelAI Media Library v2.7.2:', 1)
text = text.replace('dataset.naiMediaV271', 'dataset.naiMediaV272')

# Keep the mirror tied to the currently-open Add Media modal. This prevents a
# canceled/closed import from leaking stale File objects into the next import.
needle = "  const fileKey = file => `${file?.name || ''}::${file?.size || 0}::${file?.lastModified || 0}`;\n"
if needle not in text:
    raise SystemExit('fileKey marker not found')
insert = needle + '''  function syncImportModalMirror() {
    const dropZone = modalRoot.querySelector('#fileDropZone');
    if (!dropZone) {
      importModalIdentity = null;
      return null;
    }
    if (dropZone !== importModalIdentity) {
      importModalIdentity = dropZone;
      mirroredFiles = [];
      importCancel = false;
    }
    return dropZone;
  }
'''
text = text.replace(needle, insert, 1)

old_change = '''  modalRoot.addEventListener('change', event => {
    if (event.target?.id === 'fileInput') mirrorAddFiles(event.target.files || []);
  }, true);
'''
new_change = '''  modalRoot.addEventListener('change', event => {
    if (event.target?.id !== 'fileInput') return;
    syncImportModalMirror();
    mirrorAddFiles(event.target.files || []);
  }, true);
'''
if old_change not in text:
    raise SystemExit('change mirror block not found')
text = text.replace(old_change, new_change, 1)

old_drop = '''  modalRoot.addEventListener('drop', event => {
    const path = event.composedPath?.() || [];
    if (!path.some(node => node?.id === 'fileDropZone')) return;
    event.preventDefault();
    mirrorAddFiles(event.dataTransfer?.files || []);
  }, true);
'''
new_drop = '''  modalRoot.addEventListener('drop', event => {
    const path = event.composedPath?.() || [];
    if (!path.some(node => node?.id === 'fileDropZone')) return;
    event.preventDefault();
    syncImportModalMirror();
    mirrorAddFiles(event.dataTransfer?.files || []);
  }, true);
'''
if old_drop not in text:
    raise SystemExit('drop mirror block not found')
text = text.replace(old_drop, new_drop, 1)

# Replace the multipart/FormData upload + GM polling workaround. Chrome/Tampermonkey
# can leave the multipart request pending after the companion has already saved the
# file. v2.7.2 sends the file as a raw request body and confirms completion through a
# normal page fetch, so the confirmation channel is independent of the GM upload.
start = text.index('  async function confirmImportedFile(')
end = text.index('  async function confirmImportedUrl(', start)
replacement = r'''  async function nativeLibrary(timeoutMs=12000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(`${API}/api/library?cb=${Date.now()}-${Math.random()}`, {
        method:'GET',
        cache:'no-store',
        signal:controller.signal,
      });
      if (!res.ok) throw new Error(`Library request failed (${res.status})`);
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async function confirmImportedFile(characterId, file, sha, beforeIds, categories, beforeItem, deadlineMs=120000) {
    const deadline = Date.now() + deadlineMs;
    await sleep(300);
    while (!importCancel && Date.now() < deadline) {
      try {
        let lib;
        try { lib = await nativeLibrary(8000); }
        catch (_) { lib = await gmRequest({path:'/api/library', timeout:8000}); }
        const item = (lib?.media || []).find(m => {
          if (m.character_id !== characterId) return false;
          if (sha) return m.sha256 === sha;
          return !beforeIds.has(m.id) && m.original_name === file.name;
        });
        if (item) {
          const duplicate = beforeIds.has(item.id);
          if (!duplicate) return {item, duplicate:false, confirmed:true};
          if (item.media_type === 'video') return {item, duplicate:true, confirmed:true};
          const required = Array.isArray(categories) ? categories : [];
          const beforeCats = Array.isArray(beforeItem?.categories) ? beforeItem.categories : [];
          const nowCats = Array.isArray(item.categories) ? item.categories : [];
          const noChangeNeeded = required.every(id => beforeCats.includes(id));
          const serverAppliedChange = required.every(id => nowCats.includes(id));
          if (noChangeNeeded || serverAppliedChange) return {item, duplicate:true, confirmed:true};
        }
      } catch (_) {}
      await sleep(450);
    }
    throw new Error(importCancel ? 'Import canceled' : 'The import could not be confirmed.');
  }

  async function uploadFileResilient(file, characterId, categories) {
    const before = library || await refreshLibrary();
    const beforeIds = new Set((before.media || []).map(m => m.id));
    const sha = await sha256File(file);
    const beforeItem = sha ? (before.media || []).find(m => m.character_id === characterId && m.sha256 === sha) || null : null;
    const query = new URLSearchParams({
      character_id: characterId,
      filename: file.name || 'upload',
      categories: JSON.stringify(Array.isArray(categories) ? categories : []),
    });

    let requestReject = null;
    const requestPromise = new Promise((resolve, reject) => {
      activeUploadHandle = GM_xmlhttpRequest({
        method:'POST',
        url:`${API}/api/import/raw?${query.toString()}`,
        data:file,
        timeout:300000,
        headers:{'Content-Type': file.type || 'application/octet-stream'},
        onload:res => {
          activeUploadHandle = null;
          if (res.status >= 200 && res.status < 300) {
            try { resolve(JSON.parse(res.responseText || '{}')); }
            catch (_) { resolve(null); }
          } else {
            let message = `Request failed (${res.status})`;
            try { message = JSON.parse(res.responseText || '{}').error || message; } catch (_) {}
            reject(new Error(message));
          }
        },
        onerror:()=>{ activeUploadHandle = null; reject(new Error(importCancel ? 'Import canceled' : 'Could not connect to the local NovelAI Media Library program.')); },
        ontimeout:()=>{ activeUploadHandle = null; reject(new Error(importCancel ? 'Import canceled' : 'The local media request timed out.')); },
      });
    }).catch(err => { requestReject = err; return null; });

    const confirmPromise = confirmImportedFile(characterId, file, sha, beforeIds, categories, beforeItem).catch(() => null);
    const first = await Promise.race([
      requestPromise.then(value => ({source:'request', value})),
      confirmPromise.then(value => ({source:'confirm', value})),
    ]);
    if (first.value?.item?.id) {
      if (first.source === 'confirm' && activeUploadHandle?.abort) {
        try { activeUploadHandle.abort(); } catch (_) {}
        activeUploadHandle = null;
      }
      return first.value;
    }
    const other = first.source === 'request' ? await confirmPromise : await requestPromise;
    if (other?.item?.id) return other;
    if (importCancel) throw new Error('Import canceled');
    throw requestReject || new Error('The file was not imported.');
  }

'''
text = text[:start] + replacement + text[end:]

# Let the top-right X remain usable while importing, and turn it into an abort as well
# as a close. The footer Cancel Import button also closes immediately instead of leaving
# a disabled modal behind while an aborted request settles.
old_disable = "    modalRoot.querySelectorAll('button,input,textarea').forEach(el => el.disabled = true);\n"
new_disable = "    modalRoot.querySelectorAll('button,input,textarea').forEach(el => { if (!el.matches('[data-close]')) el.disabled = true; });\n"
if old_disable not in text:
    raise SystemExit('import disable marker not found')
text = text.replace(old_disable, new_disable, 1)

run_marker = '  async function runOwnImport(reviewAfter) {\n'
if run_marker not in text:
    raise SystemExit('runOwnImport marker not found')
close_guard = '''  modalRoot.addEventListener('click', event => {
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
text = text.replace(run_marker, close_guard + run_marker, 1)

old_dropzone = "    const dropZone = modalRoot.querySelector('#fileDropZone');\n"
new_dropzone = "    const dropZone = syncImportModalMirror();\n"
if old_dropzone not in text:
    raise SystemExit('runOwnImport dropZone marker not found')
text = text.replace(old_dropzone, new_dropzone, 1)

old_cancel_tail = '''        activeUploadHandle = null;
        if (status) status.textContent = 'Canceling import…';
      });
'''
new_cancel_tail = '''        activeUploadHandle = null;
        if (status) status.textContent = 'Canceling import…';
        setTimeout(() => {
          if (modalRoot.querySelector('#fileDropZone')) modalRoot.innerHTML = '';
          refreshBtn?.click();
          schedulePseudoSync();
          scheduleMainFilter();
        }, 0);
      });
'''
if old_cancel_tail not in text:
    raise SystemExit('cancel handler marker not found')
text = text.replace(old_cancel_tail, new_cancel_tail, 1)

out.write_text(text, encoding='utf-8')
print(f'wrote {out}')
