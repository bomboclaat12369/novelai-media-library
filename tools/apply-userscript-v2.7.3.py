from pathlib import Path

src = Path('payload/userscript-2.7.2.patch01.txt')
out = Path('payload/userscript-2.7.3.patch01.txt')
text = src.read_text(encoding='utf-8')
text = text.replace('// NovelAI Media Library v2.7.2:', '// NovelAI Media Library v2.7.3:', 1)
text = text.replace('dataset.naiMediaV272', 'dataset.naiMediaV273')

bad = "  function syncImportModalMirror() {\n    const dropZone = syncImportModalMirror();\n"
good = "  function syncImportModalMirror() {\n    const dropZone = modalRoot.querySelector('#fileDropZone');\n"
if bad not in text:
    raise SystemExit('recursive mirror bug marker not found')
text = text.replace(bad, good, 1)

old = "  async function runOwnImport(reviewAfter) {\n    if (importBusy) return;\n    const dropZone = modalRoot.querySelector('#fileDropZone');\n"
new = "  async function runOwnImport(reviewAfter) {\n    if (importBusy) return;\n    const dropZone = syncImportModalMirror();\n"
if old not in text:
    raise SystemExit('runOwnImport marker not found')
text = text.replace(old, new, 1)

out.write_text(text, encoding='utf-8')
print(f'wrote {out}')
