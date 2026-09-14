from pathlib import Path

src = Path('payload/userscript-2.7.6.patch01.txt')
dst = Path('payload/userscript-2.7.7.patch01.txt')
text = src.read_text(encoding='utf-8')
text = text.replace('// NovelAI Media Library v2.7.6: remove localhost fetch stalls + instant Rapid Review media load', '// NovelAI Media Library v2.7.7: restore proven multipart import path + timing diagnostics', 1)

start = text.index('  async function uploadFileResilient(file, characterId, categories) {')
end = text.index('\n  async function confirmImportedUrl(', start)
new_block = r'''  async function uploadFileResilient(file, characterId, categories) {
    // Restore the original proven-fast local import transport. The raw/status transport
    // introduced in 2.7.x added a second polling lifecycle and is no longer used for files.
    const form = new FormData();
    form.append('character_id', characterId);
    form.append('categories', JSON.stringify(Array.isArray(categories) ? categories : []));
    form.append('file', file, file.name || 'upload');
    const started = performance.now();
    return await new Promise((resolve, reject) => {
      activeUploadHandle = GM_xmlhttpRequest({
        method:'POST',
        url:`${API}/api/import/file`,
        data:form,
        timeout:300000,
        headers:{Origin:'https://novelai.net'},
        onload:res => {
          activeUploadHandle = null;
          const elapsed = Math.round(performance.now() - started);
          console.info(`[NovelAI Media timing] local import response: ${elapsed} ms`);
          if (res.status >= 200 && res.status < 300) {
            try { resolve(JSON.parse(res.responseText || '{}')); }
            catch (_) { resolve(null); }
            return;
          }
          let message = `Request failed (${res.status})`;
          try { message = JSON.parse(res.responseText || '{}').error || message; } catch (_) {}
          reject(new Error(message));
        },
        onerror:()=>{
          activeUploadHandle = null;
          reject(new Error(importCancel ? 'Import canceled' : 'Could not connect to the local NovelAI Media Library program.'));
        },
        ontimeout:()=>{
          activeUploadHandle = null;
          reject(new Error(importCancel ? 'Import canceled' : 'The local media request timed out.'));
        },
      });
    });
  }
'''
text = text[:start] + new_block + text[end:]

# Add visible timing around opening Rapid Review so a remaining delay identifies itself.
old = '''      if (reviewAfter && importedIds.length) {
        mirroredFiles = [];
        modalRoot.innerHTML = '';
        await openReviewQueue(importedIds, 'import');
'''
new = '''      if (reviewAfter && importedIds.length) {
        mirroredFiles = [];
        const reviewStarted = performance.now();
        modalRoot.innerHTML = '';
        await openReviewQueue(importedIds, 'import');
        console.info(`[NovelAI Media timing] Rapid Review opened: ${Math.round(performance.now() - reviewStarted)} ms`);
'''
if old not in text:
    raise SystemExit('review handoff block not found')
text = text.replace(old, new, 1)

old = '''        const img = document.createElement('img');
        img.alt = m.original_name || '';
        img.decoding = 'async';
        img.src = `${API}/api/media/${encodeURIComponent(m.id)}/original`;
        stage.innerHTML = '';
        stage.appendChild(img);
'''
new = '''        const img = document.createElement('img');
        img.alt = m.original_name || '';
        img.decoding = 'async';
        const imageStarted = performance.now();
        img.addEventListener('load', () => console.info(`[NovelAI Media timing] Rapid Review image loaded: ${Math.round(performance.now() - imageStarted)} ms`), {once:true});
        img.addEventListener('error', () => console.warn(`[NovelAI Media timing] Rapid Review image failed after ${Math.round(performance.now() - imageStarted)} ms`), {once:true});
        img.src = `${API}/api/media/${encodeURIComponent(m.id)}/original`;
        stage.innerHTML = '';
        stage.appendChild(img);
'''
if old not in text:
    raise SystemExit('rapid review image block not found')
text = text.replace(old, new, 1)

dst.write_text(text, encoding='utf-8')
print(f'wrote {dst}')
