from pathlib import Path

p = Path('runtime-src/companion-runtime.pyw')
s = p.read_text(encoding='utf-8')
old = '''                im.thumbnail((420, 420), Image.Resampling.LANCZOS)\n                if im.mode not in ("RGB", "RGBA"):\n                    im = im.convert("RGBA" if "transparency" in im.info else "RGB")\n                im.save(out, "WEBP", quality=82, method=5)\n'''
new = '''                # Thumbnails are only 420px. High-effort LANCZOS + WebP method 5 can\n                # take many seconds on large phone/AI images and used to block imports.\n                # Use the fast thumbnail path; the untouched original is never changed.\n                im.thumbnail((420, 420), Image.Resampling.BILINEAR)\n                if im.mode not in ("RGB", "RGBA"):\n                    im = im.convert("RGBA" if "transparency" in im.info else "RGB")\n                im.save(out, "WEBP", quality=82, method=1)\n'''
if old not in s:
    raise SystemExit('thumbnail block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('optimized thumbnail generation')
