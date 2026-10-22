# Card title artwork

Selected title designs: Royal Ink (Captain) and Legacy Gold (Former #1).
The selected generated concepts were extracted with the image-generation edit tool
into transparent artwork, then encoded as 1200-pixel-wide WebP at quality 92 with
alpha preserved. These are static shared assets, not per-card generated graphics.

`release-standalone.json` maps title IDs to these files. `tools/build-standalone.py`
embeds them once in the offline standalone document. NovelAI has no dependency on
them. Keep the assets and release build together when changing their paths.
