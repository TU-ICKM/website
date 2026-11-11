# ICKM website

Source of the website of the International Conference on Knowledge Management (ICKM), planned for ickm.net.
The site is static: plain HTML pages, no database, no login and nothing on a server that needs updates.

## Where things are

| What | File |
|---|---|
| All conferences (one block per year) | `data/conferences.toml` |
| Page texts | `content/*.md` |
| Site settings (title, indexing, which build is published) | `site.toml` |
| Layout and style | `templates/base.html`, `static/style.css` |
| Small script (background videos, map journey) | `static/site.js` |
| Logo and background videos (switched off for now) | `logo` and `videos` in `site.toml` |
| Land outlines for the world map (Natural Earth, public domain) | `data/ne_110m_land.geojson` |
| Build script | `build.py` |
| Publishing to GitHub Pages | branch `gh-pages` for now. Automatic build: `tools/pages-workflow.yml` (inactive copy, see below) |

## Common changes

- **New conference year or new details:** edit `data/conferences.toml`. Copy one block, change the values. The
  conference list, the year page, the home page (timeline and map) and Publications update themselves. For the map,
  add `geo = [latitude, longitude]` of the city.
- **Change a text:** edit the file in `content/`. Headings start with `#`, list items with `- `, links look like
  `[text](https://example.org)`. A note that starts with `> Placeholder:` is shown as a box marked "Text follows".
- On GitHub, both can be done in the browser: open the file, click the pencil, save with "Commit changes".
  Once the automatic build is switched on (below), GitHub rebuilds and publishes the site within a few minutes.

## Publishing

For now the built site is published from the branch `gh-pages` (GitHub Pages: "Deploy from a branch").
Run `python build.py`, then copy the content of `_publish/` into the branch `gh-pages` and push it.
`.nojekyll` in the output tells GitHub to serve the files as they are.

To let GitHub build the site itself after every change, create `.github/workflows/pages.yml` on github.com with the
content of `tools/pages-workflow.yml`, then set Settings > Pages > Source to "GitHub Actions".

## Build and view on your own computer

Needs Python 3.12 or newer, nothing else.

```
python build.py
python -m http.server 8000 --bind 127.0.0.1 --directory _site
```

Then open http://localhost:8000 in a browser. The one-page transition site is in `_site_transition`.

## Logo and videos

The logo and the background videos are switched off in `site.toml` until their use is cleared. The site then shows
"ICKM" as text in the header and the still backgrounds without video. To switch them on: put `logo.svg`,
`logo-dark.svg`, `favicon.svg` and the folder `media/` into `static/`, then set `logo = true` and `videos = true`.

For viewing on one computer only, the files can also live in `assets-local/` and be switched on in `local.toml`
(both not in git).

## Rules

- No tracking, no cookies, no fonts or scripts from other servers. Only our own small script.
- No forms on the site. Submission and registration run on the systems of each conference host.
- Place and dates of a coming conference appear only once they are public.
