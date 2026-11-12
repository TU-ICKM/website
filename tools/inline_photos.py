"""Puts the placeholder photos into the pages as data URIs and deletes every photos/ folder, so that the photos
are encrypted together with the pages by protect.mjs and never lie readable on GitHub Pages (DECISIONS Nr. 70).

Run on the assembled gh-pages copy, before protect.mjs:
    python -I tools/inline_photos.py <folder>
Exits with an error if a photo is missing. Afterwards no photos/ folder and no reference to one is left."""
import base64
import re
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
SRC = re.compile(r'src="([^"]*?photos/[^"/]+\.(?:jpe?g|png|webp))"')
TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
pages = inlined = 0
missing = []
for page in root.rglob("*.html"):
    html = page.read_text(encoding="utf-8")
    if "photos/" not in html:
        continue

    def repl(m):
        global inlined
        f = (page.parent / m.group(1)).resolve()
        if not f.is_file():
            missing.append(f"{page.relative_to(root)}: {m.group(1)}")
            return m.group(0)
        inlined += 1
        data = base64.b64encode(f.read_bytes()).decode("ascii")
        return f'src="data:{TYPES[f.suffix.lower()]};base64,{data}"'

    new = SRC.sub(repl, html)
    if new != html:
        page.write_text(new, encoding="utf-8")
        pages += 1
if missing:
    sys.exit("missing photos:\n" + "\n".join(missing))
folders = [d for d in root.rglob("photos") if d.is_dir()]
for d in folders:
    shutil.rmtree(d)
left = [p for p in root.rglob("*.html") if SRC.search(p.read_text(encoding="utf-8"))]
if left or any(root.rglob("photos")):
    sys.exit(f"photos still referenced or present: {left[:3]}")
print(f"{inlined} photos put into {pages} pages, {len(folders)} photos/ folders removed")
