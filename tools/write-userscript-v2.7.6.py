from pathlib import Path

src = Path('payload/userscript-2.7.5.patch01.txt')
dst = Path('payload/userscript-2.7.6.patch01.txt')
text = src.read_text(encoding='utf-8')

text = text.replace('// NovelAI Media Library v2.7.4: status-tracked imports, Review queue, queue filmstrip/sets, video favorites', '// NovelAI Media Library v2.7.6: remove localhost fetch stalls + instant Rapid Review media load', 1)

old = '''  async function refreshLibrary() {
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
new = '''  async function refreshLibrary() {
    // Use Tampermonkey's localhost-capable request path directly. Native page fetches from
    // https://novelai.net to http://127.0.0.1 can sit in private-network/mixed-content checks
    // for seconds before failing, which made otherwise local operations feel frozen.
    library = await gmRequest({path:'/api/library', timeout:15000});
    if (!Array.isArray(library?.sets)) library.sets = [];
    return library;
  }
'''
if old not in text:
    raise SystemExit('refreshLibrary v2.7.5 block not found')
text = text.replace(old, new, 1)

start = text.index('  async function importJobStatus274(token) {')
end = text.index('\n  async function uploadFileResilient', start)
old = text[start:end]
new = '''  async function importJobStatus274(token) {
    // Same rule as refreshLibrary: avoid native HTTPS-page -> HTTP-localhost fetches.
    // GM_xmlhttpRequest is already authorized for this companion and does not incur the
    // browser private-network delay before every status poll.
    try {
      return await gmRequest({path:`/api/import/status/${encodeURIComponent(token)}`, timeout:5000});
    } catch (_) {
      return null;
    }
  }
'''
text = text[:start] + new + text[end:]

old = '''  async function loadQueueThumb(id, img) {
    try {
      const blob = await gmRequest({path:`/api/media/${encodeURIComponent(id)}/thumb`, responseType:'blob'});
      const url = URL.createObjectURL(blob);
      if (reviewSession) reviewSession.urls.push(url);
      if (img.isConnected) img.src = url;
    } catch (_) {}
  }
'''
new = '''  async function loadQueueThumb(id, img) {
    if (!id || !img?.isConnected) return;
    // Let the browser stream/cache the local thumbnail directly instead of waiting for
    // Tampermonkey to download the entire Blob before anything can paint.
    img.src = `${API}/api/media/${encodeURIComponent(id)}/thumb`;
  }
'''
if old not in text:
    raise SystemExit('loadQueueThumb block not found')
text = text.replace(old, new, 1)

old = '''  async function renderReviewQueue() {
    if (!reviewSession) return;
    revokeSessionUrls();
    await refreshLibrary();
    const m = currentReviewMedia();
'''
new = '''  async function renderReviewQueue() {
    if (!reviewSession) return;
    revokeSessionUrls();
    // The queue already owns the exact imported/review media records. Refreshing the whole
    // library here added a full localhost round-trip before every image and every Back/Next.
    const m = currentReviewMedia();
'''
if old not in text:
    raise SystemExit('renderReviewQueue refresh block not found')
text = text.replace(old, new, 1)

old = '''      } else {
        const blob = await gmRequest({path:`/api/media/${encodeURIComponent(m.id)}/original`, responseType:'blob', timeout:300000});
        const url = URL.createObjectURL(blob); reviewSession.urls.push(url);
        const img = document.createElement('img'); img.alt = m.original_name || ''; img.src = url;
        stage.innerHTML = ''; stage.appendChild(img);
      }
'''
new = '''      } else {
        // Direct image source: Chrome can stream/decode immediately and use its normal cache.
        // The previous Blob path waited for the complete original to cross GM_xmlhttpRequest
        // before creating an <img>, which explains the extra 30+ second blank "Loading…".
        const img = document.createElement('img');
        img.alt = m.original_name || '';
        img.decoding = 'async';
        img.src = `${API}/api/media/${encodeURIComponent(m.id)}/original`;
        stage.innerHTML = '';
        stage.appendChild(img);
      }
'''
if old not in text:
    raise SystemExit('Rapid Review image blob block not found')
text = text.replace(old, new, 1)

dst.write_text(text, encoding='utf-8')
print(f'wrote {dst}')
