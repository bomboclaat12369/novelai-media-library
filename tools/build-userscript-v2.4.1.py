from pathlib import Path

src_path = Path('payload/userscript-2.4.0.patch01.txt')
out_path = Path('payload/userscript-2.4.1.patch01.txt')
src = src_path.read_text(encoding='utf-8')

src = src.replace('// NovelAI Media Library v2.4.0: permanent non-destructive top/bottom image cropping', '// NovelAI Media Library v2.4.1: on-disk crop persistence + split selector restore', 1)
src = src.replace("document.documentElement.dataset.naiMediaV240 === '1'", "document.documentElement.dataset.naiMediaV241 === '1'", 1)
src = src.replace("document.documentElement.dataset.naiMediaV240 = '1'", "document.documentElement.dataset.naiMediaV241 = '1'", 1)

needle = '''  const crops = new Map();
  const cropUrls = new Map();
  let editor = null;
'''
replacement = '''  const crops = new Map();
  const cropUrls = new Map();
  let editor = null;
  let serverCropReady = false;
'''
if needle not in src:
    raise SystemExit('state insertion point not found')
src = src.replace(needle, replacement, 1)

needle = '''  function uiState() {
'''
helpers = r'''  function apiJson({method='GET', path, data=null}) {
    return new Promise((resolve, reject) => GM_xmlhttpRequest({
      method,
      url:`${API}${path}`,
      data:data == null ? null : JSON.stringify(data),
      headers:{Origin:'https://novelai.net', ...(data == null ? {} : {'Content-Type':'application/json'})},
      timeout:120000,
      onload:r=>{
        let parsed=null;
        try { parsed = r.responseText ? JSON.parse(r.responseText) : null; } catch (_) {}
        if (r.status >= 200 && r.status < 300) resolve(parsed);
        else reject(new Error(parsed?.error || `Request failed (${r.status})`));
      },
      onerror:()=>reject(new Error('Could not connect to the local NovelAI Media Library program.')),
      ontimeout:()=>reject(new Error('The local media request timed out.')),
    }));
  }

  async function syncCropsFromServer() {
    try {
      const health = await apiJson({path:'/api/health'});
      if (Number(health?.version || 0) < 4) return false;
      const lib = await apiJson({path:'/api/library'});
      const localBefore = new Map(crops);
      const next = new Map();
      for (const m of (lib?.media || [])) {
        if (m?.media_type !== 'image' || !m?.id) continue;
        let remote = normalize({top:m.crop_top, bottom:m.crop_bottom});
        const local = normalize(localBefore.get(m.id));
        // v2.4.0 stored crops only in browser storage. Migrate those once when
        // the v4 companion becomes available, but keep library.json authoritative afterward.
        if (!remote.top && !remote.bottom && (local.top || local.bottom)) {
          try {
            const updated = await apiJson({method:'POST', path:`/api/media/${encodeURIComponent(m.id)}/crop`, data:local});
            remote = normalize({top:updated?.crop_top, bottom:updated?.crop_bottom});
          } catch (_) {}
        }
        if (remote.top || remote.bottom) next.set(m.id, remote);
      }
      crops.clear();
      for (const [id,c] of next) crops.set(id,c);
      persist(); // browser copy is now only a cache/fallback; library.json is source of truth.
      serverCropReady = true;
      applyStages(true);
      refreshButton();
      return true;
    } catch (_) {
      return false;
    }
  }

  function syncSplitSlotButtons() {
    const split = stages.classList.contains('split');
    root.querySelectorAll('.naiSlotSelectBtnV239').forEach(button => {
      button.style.display = split ? 'inline-flex' : 'none';
    });
  }

  // Persisted split mode is restored by the base script without clicking Split.
  // Watch only the stages class, so the Slot 1/Slot 2 buttons are correct immediately after refresh.
  new MutationObserver(syncSplitSlotButtons).observe(stages, {attributes:true, attributeFilter:['class']});
  [0,40,120,300,700].forEach(ms => setTimeout(syncSplitSlotButtons, ms));

'''
if needle not in src:
    raise SystemExit('helper insertion point not found')
src = src.replace(needle, helpers + needle, 1)

needle = '''    wrap.querySelector('.naiCropSave').onclick=()=>{
      const c=normalize({top:editor.top,bottom:editor.bottom});
      if (!c.top&&!c.bottom) crops.delete(id); else crops.set(id,c);
      persist(); revoke(id); done(); applyStages(true); refreshButton();
    };
'''
replacement = '''    const saveBtn=wrap.querySelector('.naiCropSave');
    saveBtn.onclick=async()=>{
      const c=normalize({top:editor.top,bottom:editor.bottom});
      saveBtn.disabled=true;
      try {
        if (!serverCropReady) await syncCropsFromServer();
        if (!serverCropReady) throw new Error('The companion crop-storage update is still installing. Wait about a minute, then refresh NovelAI and try again.');
        const updated=await apiJson({method:'POST',path:`/api/media/${encodeURIComponent(id)}/crop`,data:c});
        const saved=normalize({top:updated?.crop_top,bottom:updated?.crop_bottom});
        if (!saved.top&&!saved.bottom) crops.delete(id); else crops.set(id,saved);
        persist(); revoke(id); done(); applyStages(true); refreshButton();
      } catch(e) {
        alert(e?.message || 'Could not save this crop.');
        saveBtn.disabled=false;
      }
    };
'''
if needle not in src:
    raise SystemExit('save handler insertion point not found')
src = src.replace(needle, replacement, 1)

needle = '''  schedule(); refreshButton();
})();
'''
replacement = '''  syncSplitSlotButtons();
  syncCropsFromServer();
  schedule(); refreshButton();
})();
'''
if needle not in src:
    raise SystemExit('initialization insertion point not found')
src = src.replace(needle, replacement, 1)

out_path.write_text(src, encoding='utf-8')
print(f'Wrote {out_path}')
