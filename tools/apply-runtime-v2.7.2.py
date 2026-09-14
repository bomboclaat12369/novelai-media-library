from pathlib import Path

p = Path('runtime-src/companion-runtime.pyw')
s = p.read_text(encoding='utf-8')
old = '''            with Image.open(original) as im:\n                if ImageOps is not None:\n                    im = ImageOps.exif_transpose(im)\n'''
new = '''            with Image.open(original) as im:\n                # JPEG can decode directly at a reduced resolution, avoiding a full-size\n                # decode for thumbnails of very large source images.\n                try:\n                    if str(getattr(im, "format", "")).upper() == "JPEG":\n                        im.draft("RGB", (840, 840))\n                except Exception:\n                    pass\n                if ImageOps is not None:\n                    im = ImageOps.exif_transpose(im)\n'''
if old not in s:
    raise SystemExit('Image.open block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('added JPEG draft thumbnail fast path')
