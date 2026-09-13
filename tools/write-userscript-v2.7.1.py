from pathlib import Path

src = Path('payload/userscript-2.7.0.patch01.txt')
out = Path('payload/userscript-2.7.1.patch01.txt')
text = src.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, found {count}')
    text = text.replace(old, new, 1)

replace_once(
    '// NovelAI Media Library v2.7.0: Review queue, queue filmstrip/sets, video favorites, resilient imports',
    '// NovelAI Media Library v2.7.1: Review queue, queue filmstrip/sets, video favorites, resilient imports',
    'header',
)
replace_once("document.documentElement.dataset.naiMediaV270 === '1'", "document.documentElement.dataset.naiMediaV271 === '1'", 'guard check')
replace_once("document.documentElement.dataset.naiMediaV270 = '1'", "document.documentElement.dataset.naiMediaV271 = '1'", 'guard set')
replace_once(
    'async function confirmImportedUrl(characterId, url, beforeIds, deadlineMs=120000) {',
    'async function confirmImportedUrl(characterId, url, beforeIds, categories, beforeItem, deadlineMs=120000) {',
    'URL confirmer signature',
)

old = '''  async function uploadUrlResilient(url, characterId, categories) {\n    const before = library || await refreshLibrary();\n    const beforeIds = new Set((before.media || []).map(m => m.id));\n    const req = gmRequest({\n      method:'POST', path:'/api/import/url', timeout:300000,\n      headers:{'Content-Type':'application/json'},\n      data:JSON.stringify({character_id:characterId, categories, url}),\n    }).then(value => ({source:'request', value})).catch(() => ({source:'request', value:null}));\n    const confirm = confirmImportedUrl(characterId, url, beforeIds).then(value => ({source:'confirm', value}));\n    const first = await Promise.race([req, confirm]);\n    if (first.value?.item?.id) return first.value;\n    const second = first.source === 'request' ? await confirm : await req;\n    if (second.value?.item?.id) return second.value;\n    throw new Error('The URL import could not be confirmed.');\n  }'''
new = '''  async function uploadUrlResilient(url, characterId, categories) {\n    const before = library || await refreshLibrary();\n    const beforeIds = new Set((before.media || []).map(m => m.id));\n    const beforeItem = (before.media || []).find(m =>\n      m.character_id === characterId && m.source?.kind === 'url' && m.source?.url === url\n    ) || null;\n    let requestReject = null;\n    const requestPromise = new Promise((resolve, reject) => {\n      activeUploadHandle = GM_xmlhttpRequest({\n        method:'POST', url:`${API}/api/import/url`, timeout:300000,\n        headers:{Origin:'https://novelai.net','Content-Type':'application/json'},\n        data:JSON.stringify({character_id:characterId, categories, url}),\n        onload:res => {\n          activeUploadHandle = null;\n          if (res.status >= 200 && res.status < 300) {\n            try { resolve(JSON.parse(res.responseText || '{}')); } catch (_) { resolve(null); }\n          } else {\n            let message = `Request failed (${res.status})`;\n            try { message = JSON.parse(res.responseText || '{}').error || message; } catch (_) {}\n            reject(new Error(message));\n          }\n        },\n        onerror:()=>{ activeUploadHandle = null; reject(new Error(importCancel ? 'Import canceled' : 'Could not connect to the local NovelAI Media Library program.')); },\n        ontimeout:()=>{ activeUploadHandle = null; reject(new Error(importCancel ? 'Import canceled' : 'The local media request timed out.')); },\n      });\n    }).catch(err => { requestReject = err; return null; });\n    const confirmPromise = confirmImportedUrl(characterId, url, beforeIds, categories, beforeItem).catch(() => null);\n    while (!importCancel) {\n      const winner = await Promise.race([\n        requestPromise.then(value => ({source:'request', value})),\n        confirmPromise.then(value => ({source:'confirm', value})),\n      ]);\n      if (winner.value?.item?.id) {\n        if (winner.source === 'confirm' && activeUploadHandle?.abort) {\n          try { activeUploadHandle.abort(); } catch (_) {}\n          activeUploadHandle = null;\n        }\n        return winner.value;\n      }\n      const other = winner.source === 'request' ? await confirmPromise : await requestPromise;\n      if (other?.item?.id) return other;\n      break;\n    }\n    if (importCancel) throw new Error('Import canceled');\n    throw requestReject || new Error('The URL import could not be confirmed.');\n  }'''
replace_once(old, new, 'URL resilient importer')

out.write_text(text, encoding='utf-8')
print(f'Wrote {out} ({len(text.encode("utf-8"))} bytes)')
