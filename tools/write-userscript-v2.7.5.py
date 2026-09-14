from pathlib import Path

src = Path('payload/userscript-2.7.4.patch01.txt')
dst = Path('payload/userscript-2.7.5.patch01.txt')
text = src.read_text(encoding='utf-8')
text = text.replace('// NovelAI Media Library v2.7.3: Review queue, queue filmstrip/sets, video favorites, resilient imports', '// NovelAI Media Library v2.7.5: import startup deadlock fix + legacy/raw completion compatibility', 1)

old = '''  async function refreshLibrary() {
    library = await gmRequest({path:'/api/library'});
    if (!Array.isArray(library?.sets)) library.sets = [];
    return library;
  }
'''
new = '''  async function refreshLibrary() {
    // Prefer the browser's normal fetch path and put a hard timeout on both paths.
    // A stalled library refresh must never block an import from starting.
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 5000);
      try {
        const res = await fetch(`${API}/api/library?cb=${Date.now()}-${Math.random()}`, {
          method:'GET', cache:'no-store', signal:controller.signal,
        });
        if (!res.ok) throw new Error(`Library request failed (${res.status})`);
        library = await res.json();
      } finally { clearTimeout(timer); }
    } catch (_) {
      library = await gmRequest({path:'/api/library', timeout:7000});
    }
    if (!Array.isArray(library?.sets)) library.sets = [];
    return library;
  }
'''
if old not in text:
    raise SystemExit('refreshLibrary block not found')
text = text.replace(old, new, 1)

old = '''    let requestError = null;
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
'''
new = '''    let requestError = null;
    let requestResult = null;
    activeUploadHandle = GM_xmlhttpRequest({
      method:'POST',
      url:`${API}/api/import/raw?${query.toString()}`,
      data:file,
      timeout:300000,
      headers:{'Content-Type': file.type || 'application/octet-stream'},
      onload:res => {
        if (res.status >= 200 && res.status < 300) {
          // Runtime 2.7.2 returns 202 + token and completes through /status.
          // Runtime 2.7.1 and older raw endpoints can return the finished item directly.
          // Accept both so a companion update lag cannot leave the modal spinning forever.
          try {
            const parsed = JSON.parse(res.responseText || '{}');
            if (parsed?.item?.id) requestResult = parsed;
          } catch (_) {}
        } else {
          let message = `Request failed (${res.status})`;
          try { message = JSON.parse(res.responseText || '{}').error || message; } catch (_) {}
          requestError = new Error(message);
        }
      },
      onerror:()=>{ requestError = new Error(importCancel ? 'Import canceled' : 'Could not connect to the local NovelAI Media Library program.'); },
      ontimeout:()=>{ requestError = new Error(importCancel ? 'Import canceled' : 'The local media request timed out.'); },
      onabort:()=>{},
    });
'''
if old not in text:
    raise SystemExit('upload request block not found')
text = text.replace(old, new, 1)

old = '''    while (!importCancel && Date.now() < deadline) {
      const status = await importJobStatus274(token);
'''
new = '''    while (!importCancel && Date.now() < deadline) {
      if (requestResult?.item?.id) {
        activeUploadHandle = null;
        return {item:requestResult.item, duplicate:!!requestResult.duplicate, confirmed:true};
      }
      const status = await importJobStatus274(token);
'''
if old not in text:
    raise SystemExit('upload polling block not found')
text = text.replace(old, new, 1)

old = '''    try {
      await refreshLibrary();
      for (let i = 0; i < jobs.length; i++) {
'''
new = '''    if (status) {
      status.classList.remove('bad');
      status.textContent = `Starting import of ${jobs.length} item${jobs.length === 1 ? '' : 's'}…`;
    }

    try {
      // Do not refresh the entire library here. In 2.7.4 this request could stall
      // before the upload even started, producing the exact blank-status screen.
      for (let i = 0; i < jobs.length; i++) {
'''
if old not in text:
    raise SystemExit('runOwnImport pre-refresh block not found')
text = text.replace(old, new, 1)

old = '''          if (result?.item?.id && !importedIds.includes(result.item.id)) importedIds.push(result.item.id);
          await refreshLibrary();
'''
new = '''          if (result?.item?.id) {
            if (!importedIds.includes(result.item.id)) importedIds.push(result.item.id);
            if (library && Array.isArray(library.media)) {
              const existingIndex = library.media.findIndex(m => m.id === result.item.id);
              if (existingIndex >= 0) library.media[existingIndex] = result.item;
              else library.media.push(result.item);
            }
          }
'''
if old not in text:
    raise SystemExit('per-item refresh block not found')
text = text.replace(old, new, 1)

old = '''      if (bar) bar.style.width = '100%';
      await refreshLibrary();

      if (importCancel) {
'''
new = '''      if (bar) bar.style.width = '100%';

      if (importCancel) {
'''
if old not in text:
    raise SystemExit('post-import refresh block not found')
text = text.replace(old, new, 1)

old = '''  async function openReviewQueue(ids, mode='import') {
    await refreshLibrary();
    const queue = [...new Set(ids)].filter(id => mediaById(id));
'''
new = '''  async function openReviewQueue(ids, mode='import') {
    // Imported items are merged into the in-memory library immediately, so Rapid Review
    // can open without waiting on another /api/library round trip.
    if (mode !== 'import') {
      try { await refreshLibrary(); } catch (_) {}
    }
    const queue = [...new Set(ids)].filter(id => mediaById(id));
'''
if old not in text:
    raise SystemExit('openReviewQueue block not found')
text = text.replace(old, new, 1)

dst.write_text(text, encoding='utf-8')
print(f'wrote {dst}')
