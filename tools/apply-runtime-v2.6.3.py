from pathlib import Path

p = Path('runtime-src/companion-runtime.pyw')
s = p.read_text(encoding='utf-8')


def one(old: str, new: str, label: str) -> None:
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    s = s.replace(old, new, 1)

one('API_VERSION = 7', 'API_VERSION = 8', 'api version')

old = '''                if "cropped_rel" not in m:\n                    m["cropped_rel"] = None\n                    changed = True\n                if m.get("media_type") == "video":\n'''
new = '''                if "cropped_rel" not in m:\n                    m["cropped_rel"] = None\n                    changed = True\n\n                # display_rel is the single file normal viewing should use. The\n                # untouched import remains stored_rel and is reserved for crop\n                # editing/reset. Existing libraries migrate automatically.\n                stored_rel = m.get("stored_rel")\n                desired_display = stored_rel\n                if m.get("media_type") == "image":\n                    try:\n                        crop_top = float(m.get("crop_top") or 0.0)\n                    except Exception:\n                        crop_top = 0.0\n                    try:\n                        crop_bottom = float(m.get("crop_bottom") or 0.0)\n                    except Exception:\n                        crop_bottom = 0.0\n                    crop_rel = m.get("cropped_rel")\n                    if (crop_top > 0.0 or crop_bottom > 0.0) and crop_rel:\n                        try:\n                            crop_path = (self.root / str(crop_rel)).resolve()\n                            root_path = self.root.resolve()\n                            if (root_path in crop_path.parents or crop_path == root_path) and crop_path.exists():\n                                desired_display = crop_rel\n                        except Exception:\n                            pass\n                if m.get("display_rel") != desired_display:\n                    m["display_rel"] = desired_display\n                    changed = True\n\n                if m.get("media_type") == "video":\n'''
one(old, new, 'load display_rel migration')

old = '''                "stored_rel": destination.relative_to(self.root).as_posix(),\n                "thumb_rel": thumb_rel,\n'''
new = '''                "stored_rel": destination.relative_to(self.root).as_posix(),\n                "display_rel": destination.relative_to(self.root).as_posix(),\n                "thumb_rel": thumb_rel,\n'''
one(old, new, 'new media display_rel')

old = '''        m["cropped_rel"] = None\n\n    def _make_cropped_derivative'''
new = '''        m["cropped_rel"] = None\n        m["display_rel"] = m.get("stored_rel")\n\n    def _make_cropped_derivative'''
one(old, new, 'reset display_rel')

old = '''        m["cropped_rel"] = out.relative_to(self.root).as_posix()\n        return out\n'''
new = '''        m["cropped_rel"] = out.relative_to(self.root).as_posix()\n        m["display_rel"] = m["cropped_rel"]\n        return out\n'''
one(old, new, 'cropped derivative becomes display')

old = '''            old_top = m.get("crop_top", 0.0)\n            old_bottom = m.get("crop_bottom", 0.0)\n            old_rel = m.get("cropped_rel")\n'''
new = '''            old_top = m.get("crop_top", 0.0)\n            old_bottom = m.get("crop_bottom", 0.0)\n            old_rel = m.get("cropped_rel")\n            old_display_rel = m.get("display_rel")\n'''
one(old, new, 'save old display_rel')

old = '''                m["crop_top"] = old_top\n                m["crop_bottom"] = old_bottom\n                m["cropped_rel"] = old_rel\n                raise\n'''
new = '''                m["crop_top"] = old_top\n                m["crop_bottom"] = old_bottom\n                m["cropped_rel"] = old_rel\n                m["display_rel"] = old_display_rel\n                raise\n'''
one(old, new, 'restore display_rel on crop failure')

old = '''            # /source is always the exact untouched imported file. Videos also always\n            # use their original file. Normal image display, however, must prefer the\n            # persistent cropped derivative whenever crop metadata is present.\n            if source or m.get("media_type") != "image":\n                rel = m.get("stored_rel")\n                using_crop = False\n            else:\n                try:\n                    top = float(m.get("crop_top") or 0.0)\n                except Exception:\n                    top = 0.0\n                try:\n                    bottom = float(m.get("crop_bottom") or 0.0)\n                except Exception:\n                    bottom = 0.0\n                has_crop = top > 0.0 or bottom > 0.0\n                using_crop = False\n                if has_crop:\n                    rel = m.get("cropped_rel")\n                    candidate = (self.root / str(rel or "")).resolve() if rel else None\n                    if not rel or candidate is None or not candidate.exists():\n                        self._make_cropped_derivative(m)\n                        self.save()\n                        rel = m.get("cropped_rel")\n                    if not rel:\n                        raise FileNotFoundError("Cropped media file is missing")\n                    using_crop = True\n                else:\n                    rel = m.get("stored_rel")\n\n            path = (self.root / str(rel or "")).resolve()\n'''
new = '''            # /source always means the untouched imported file. Normal viewing has\n            # exactly one source of truth: display_rel. Saving a crop changes\n            # display_rel to the persistent cropped PNG; resetting changes it back to\n            # stored_rel. The crop metadata below is only a self-healing guard for old\n            # libraries or a manually deleted derivative.\n            if source or m.get("media_type") != "image":\n                rel = m.get("stored_rel")\n                using_crop = False\n            else:\n                rel = m.get("display_rel") or m.get("stored_rel")\n                try:\n                    top = float(m.get("crop_top") or 0.0)\n                except Exception:\n                    top = 0.0\n                try:\n                    bottom = float(m.get("crop_bottom") or 0.0)\n                except Exception:\n                    bottom = 0.0\n                has_crop = top > 0.0 or bottom > 0.0\n                using_crop = False\n                if has_crop:\n                    crop_rel = m.get("cropped_rel")\n                    crop_path = (self.root / str(crop_rel or "")).resolve() if crop_rel else None\n                    if not crop_rel or crop_path is None or not crop_path.exists():\n                        self._make_cropped_derivative(m)\n                        self.save()\n                        crop_rel = m.get("cropped_rel")\n                    if not crop_rel:\n                        raise FileNotFoundError("Cropped media file is missing")\n                    if m.get("display_rel") != crop_rel:\n                        m["display_rel"] = crop_rel\n                        self.save()\n                    rel = crop_rel\n                    using_crop = True\n                else:\n                    original_rel = m.get("stored_rel")\n                    if m.get("display_rel") != original_rel:\n                        m["display_rel"] = original_rel\n                        self.save()\n                    rel = original_rel\n\n            path = (self.root / str(rel or "")).resolve()\n'''
one(old, new, 'display_rel media path')

p.write_text(s, encoding='utf-8')
print('Applied runtime v2.6.3 display-file architecture')
