"""Build the ICKM website from plain text files.

Usage:
    python build.py

Needs Python 3.11 or newer and nothing else (only the standard library).

Reads:
    site.toml               site settings
    data/conferences.toml   one entry per conference year (single source for all conference pages and the maps)
    data/ne_110m_land.geojson  land outlines for the world map (Natural Earth, public domain)
    content/*.md            page texts in a small subset of Markdown
    templates/base.html     page layout
    static/                 files copied as they are (style sheet, script, logo, background videos)

Writes (next to this file, or in build_dir from an optional local.toml):
    _site/              the full website
    _site_transition/   the one-page transition site
    _publish/           a copy of whichever of the two site.toml names in "publish"
"""

import html
import json
import math
import re
import shutil
import sys
import time
import tomllib
from datetime import date
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

FORMATS = {"onsite": "In person", "virtual": "Virtual", "hybrid": "Hybrid"}

NAV = [
    ("about/", "Who we are"),
    ("people/", "People"),
    ("conferences/", "Conferences"),
    ("publications/", "Publications"),
    ("history/", "History"),
    ("community/", "Community"),
    ("contact/", "Contact"),
]

# Footer columns of the full site. The transition site only shows LEGAL.
FOOTER_GROUPS = [
    ("ICKM", [("about/", "Who we are"), ("people/", "People"), ("about/partners/", "Partners"), ("history/", "History")]),
    ("Conferences", [("conferences/", "All conferences"), ("next/", "Next conference"), ("publications/", "Publications")]),
    ("Get in touch", [("community/", "Community"), ("contact/", "Contact")]),
]
LEGAL = [("imprint/", "Imprint"), ("privacy/", "Privacy")]

# Host countries by continent, for the numbers on "Who we are". A new country needs a line here.
CONTINENTS = {
    "Singapore": "Asia", "Hong Kong": "Asia", "Japan": "Asia", "Türkiye": "Asia", "Jordan": "Asia",
    "USA": "North America", "Canada": "North America",
    "United Kingdom": "Europe", "Austria": "Europe", "Germany": "Europe", "Portugal": "Europe",
    "South Africa": "Africa", "Brazil": "South America", "Chile": "South America",
}

ICON_SUN = ('<svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4.2"/>'
            '<path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></svg>')
ICON_MOON = ('<svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
             '<path d="M20 14.6A8.3 8.3 0 0 1 9.4 4a8.3 8.3 0 1 0 10.6 10.6z"/></svg>')
ICON_MENU = ('<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
             '<path class="i-bars" d="M4 7h16M4 12h16M4 17h16"/><path class="i-close" d="M6 6l12 12M18 6L6 18"/></svg>')

# Files that only the full site needs. The transition site stays small (no video, no script).
FULL_ONLY = ("media/", "site.js")

# Logo and background videos are switched on in site.toml (logo = true, videos = true) once their use is cleared.
# Until then they can live in assets-local/ (not in git) and be switched on in local.toml for viewing on this computer.
ASSETS_LOCAL = ROOT / "assets-local"
FEATURES = {"logo": False, "videos": False, "photos": False}

# Placeholder photos live only in photos-local/ (not in git, with their list photos.toml) and show only with
# photos = true in local.toml. The public build never has them. For the online preview they are put into the
# pages before encryption (tools/inline_photos.py), so they never lie readable on GitHub Pages.
PHOTOS_LOCAL = ROOT / "photos-local"


def load_photos():
    path = PHOTOS_LOCAL / "photos.toml"
    if not FEATURES["photos"] or not path.exists():
        return []
    return tomllib.loads(path.read_text(encoding="utf-8")).get("photo", [])
LOGO_FILES = ("logo.svg", "logo-dark.svg", "favicon.svg")


# ---------------------------------------------------------------- links

def rel(from_dir, to_path):
    """Relative link from the page in from_dir (like "conferences/2017/") to a site path (like "about/")."""
    depth = len([p for p in from_dir.split("/") if p])
    link = "../" * depth + to_path
    return link or "./"


def resolve(url, from_dir):
    """Turn site paths written as "/about/" into relative links. Leave other links alone."""
    if url.startswith("/") and not url.startswith("//"):
        return rel(from_dir, url.lstrip("/"))
    return url


# ---------------------------------------------------------------- markdown subset

INLINE_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def inline(text, from_dir):
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*]+)\*(?![*\w])", r"<em>\1</em>", text)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2))
        href = html.escape(resolve(url, from_dir), quote=True)
        return f'<a href="{href}">{label}</a>'

    return INLINE_LINK.sub(link, text)


def markdown(text, from_dir):
    """Convert the Markdown subset used in content/*.md.

    Supported: # headings, paragraphs, "- " lists, "1. " lists, [links](url), **bold**, *italic*, `code`,
    and "> " notes. A note that starts with "Placeholder:" is shown as a placeholder box.
    """
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l.rstrip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        first = lines[0]
        if first.startswith("#"):
            level = min(len(first) - len(first.lstrip("#")), 4)
            out.append(f"<h{level}>{inline(first.lstrip('#').strip(), from_dir)}</h{level}>")
            rest = "\n".join(lines[1:])
            if rest:
                out.append(markdown(rest, from_dir))
        elif all(l.startswith("- ") for l in lines):
            items = "".join(f"<li>{inline(l[2:].strip(), from_dir)}</li>" for l in lines)
            out.append(f"<ul>{items}</ul>")
        elif all(re.match(r"\d+\.\s", l) for l in lines):
            items = "".join(f"<li>{inline(re.sub(r'^\d+\.\s', '', l), from_dir)}</li>" for l in lines)
            out.append(f"<ol>{items}</ol>")
        elif all(l.startswith(">") for l in lines):
            body = " ".join(l.lstrip(">").strip() for l in lines)
            css = "placeholder" if body.lower().startswith("placeholder:") else "note"
            out.append(f'<div class="{css}"><p>{inline(body, from_dir)}</p></div>')
        else:
            # A line that ends with a backslash keeps its line break (for postal addresses).
            parts = []
            for i, l in enumerate(lines):
                text = l.strip()
                last = i == len(lines) - 1
                if text.endswith("\\") and not last:
                    parts.append(inline(text[:-1].rstrip(), from_dir) + "<br>")
                else:
                    parts.append(inline(text, from_dir) + ("" if last else " "))
            out.append(f"<p>{''.join(parts)}</p>")
    return "\n".join(out)


def markdown_cards(text, from_dir):
    """Like markdown(), but every "## " section becomes a card in a grid. Text before the first "## " stays as it is."""
    parts = re.split(r"(?m)^## ", text.strip())
    out = markdown(parts[0], from_dir) if parts[0].strip() else ""
    cards = []
    for section in parts[1:]:
        heading, _, body = section.partition("\n")
        cards.append(f'<section class="info-card reveal"><h2>{inline(heading.strip(), from_dir)}</h2>'
                     f'{markdown(body, from_dir)}</section>')
    if cards:
        out += '<div class="card-grid">' + "".join(cards) + "</div>"
    return out


def minify_css(css):
    """Smaller style sheet for the published site: no comments, no extra spaces. The file in static/ stays readable."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,>])\s*", r"\1", css)
    css = re.sub(r":\s+", ":", css)
    return css.replace(";}", "}").strip() + "\n"


def read_content(name):
    """Return (title, rest): the first "# " heading and the text below it."""
    path = ROOT / "content" / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    m = re.match(r"#\s+(.+)\n?", text)
    if not m:
        return name.title(), text
    return m.group(1).strip(), text[m.end():]


def first_paragraph(text):
    """Split off the first plain paragraph (used as the lead line under a page title)."""
    blocks = re.split(r"\n\s*\n", text.strip(), maxsplit=1)
    head = blocks[0] if blocks else ""
    if head and not head.lstrip().startswith(("#", ">", "- ")) and not re.match(r"\d+\.\s", head):
        return " ".join(l.strip() for l in head.splitlines()), (blocks[1] if len(blocks) > 1 else "")
    return "", text


# ---------------------------------------------------------------- conference helpers

def fmt_dates(c):
    start, end = c.get("start"), c.get("end")
    if not isinstance(start, date):
        return ""
    if not isinstance(end, date) or end == start:
        return f"{MONTHS[start.month - 1]} {start.day}, {start.year}"
    if start.year != end.year:
        return (f"{MONTHS[start.month - 1]} {start.day}, {start.year} to "
                f"{MONTHS[end.month - 1]} {end.day}, {end.year}")
    if start.month != end.month:
        return f"{MONTHS[start.month - 1]} {start.day} to {MONTHS[end.month - 1]} {end.day}, {start.year}"
    return f"{MONTHS[start.month - 1]} {start.day}–{end.day}, {start.year}"


def fmt_place(c):
    parts = [c.get("city", ""), c.get("region", ""), c.get("country", "")]
    return ", ".join(p for p in parts if p)


def short_place(c):
    return c.get("city") or c.get("region") or c.get("country") or ""


def esc(text):
    return html.escape(str(text), quote=True)


def ext_link(url, label=None):
    return f'<a href="{esc(url)}">{esc(label or url)}</a>'


def proceedings_html(c):
    p = c.get("proceedings")
    if not p:
        return ""
    label = p.get("title") or "Proceedings"
    if p.get("publisher"):
        label += f" ({p['publisher']})"
    if p.get("url"):
        return ext_link(p["url"], label)
    return esc(label)


def upcoming(conferences):
    return [c for c in conferences if c.get("status") in ("announced", "planned")]


def kind(c):
    """CSS class for the state of a conference year."""
    status = c.get("status")
    if status == "cancelled":
        return "cancelled"
    if status in ("announced", "planned"):
        return "next"
    return "virtual" if c.get("format") == "virtual" else "held"


# ---------------------------------------------------------------- world map (Equal Earth projection)

_A1, _A2, _A3, _A4 = 1.340264, -0.081106, 0.000893, 0.003796
_M = math.sqrt(3) / 2
MAP_W = 1000
MAP_TOP, MAP_BOTTOM = 84, -57   # latitudes shown (Antarctica left out)


def _equal_earth(lat, lon):
    p, l = math.radians(lat), math.radians(lon)
    t = math.asin(_M * math.sin(p))
    t2 = t * t
    t6 = t2 ** 3
    x = l * math.cos(t) / (_M * (_A1 + 3 * _A2 * t2 + t6 * (7 * _A3 + 9 * _A4 * t2)))
    y = t * (_A1 + _A2 * t2 + t6 * (_A3 + _A4 * t2))
    return x, y


_XMAX = _equal_earth(0, 180)[0]
_SCALE = MAP_W / (2 * _XMAX)
_YTOP = _equal_earth(MAP_TOP, 0)[1]


def map_xy(lat, lon):
    x, y = _equal_earth(lat, lon)
    return (x + _XMAX) * _SCALE, (_YTOP - y) * _SCALE


MAP_H = round(map_xy(MAP_BOTTOM, 0)[1])


def world_svg(land="#0f2552", dots="#3d6aa8"):
    """Dotted world map from Natural Earth 1:110m land (public domain). Coarse on purpose: about 12 KB."""
    data = json.loads((ROOT / "data" / "ne_110m_land.geojson").read_text(encoding="utf-8"))
    parts = []
    for feature in data["features"]:
        g = feature["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            ring = poly[0]
            if max(p[1] for p in ring) < -55:
                continue
            pts = [map_xy(lat, lon) for lon, lat in ring]
            area = 0.5 * abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts))))
            if area < 8:
                continue
            kept = [pts[0]]
            for q in pts[1:]:
                if math.dist(q, kept[-1]) >= 2.5:
                    kept.append(q)
            if len(kept) < 3:
                continue
            r = [(round(x), round(y)) for x, y in kept]
            parts.append(f"M{r[0][0]} {r[0][1]}" + "".join(
                f"l{r[i][0] - r[i - 1][0]} {r[i][1] - r[i - 1][1]}" for i in range(1, len(r))) + "z")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {MAP_W} {MAP_H}">'
            '<defs><pattern id="d" width="6" height="6" patternUnits="userSpaceOnUse">'
            f'<circle cx="3" cy="3" r="1.45" fill="{dots}"/></pattern>'
            f'<path id="l" d="{"".join(parts)}"/></defs>'
            f'<use href="#l" fill="{land}"/><use href="#l" fill="url(#d)"/></svg>\n')


def arc_d(p, q):
    """A curved line from p to q that always bends north."""
    (x1, y1), (x2, y2) = p, q
    dist = math.hypot(x2 - x1, y2 - y1)
    nx, ny = -(y2 - y1) / dist, (x2 - x1) / dist
    if ny > 0:
        nx, ny = -nx, -ny
    k = 0.22 * dist
    cx, cy = (x1 + x2) / 2 + nx * k, (y1 + y2) / 2 + ny * k
    return f"M{x1:.0f} {y1:.0f}Q{cx:.0f} {cy:.0f} {x2:.0f} {y2:.0f}"


def map_html(from_dir, layers, themed=False):
    """The map picture plus a drawing layer on top. Purely decorative: every fact is also in the text.
    themed=True: light map in light mode, dark map in dark mode (only the visible one loads)."""
    if themed:
        pics = (f'<img class="only-dark" src="{rel(from_dir, "world.svg")}" width="{MAP_W}" height="{MAP_H}" alt="" loading="lazy">'
                f'<img class="only-light" src="{rel(from_dir, "world-light.svg")}" width="{MAP_W}" height="{MAP_H}" alt="" loading="lazy">')
    else:
        pics = f'<img src="{rel(from_dir, "world.svg")}" width="{MAP_W}" height="{MAP_H}" alt="">'
    return (f'<div class="map" style="aspect-ratio:{MAP_W}/{MAP_H}">{pics}'
            f'<svg viewBox="0 0 {MAP_W} {MAP_H}" aria-hidden="true" focusable="false">{layers}</svg></div>')


def city_mark(c, extra=""):
    x, y = map_xy(*c["geo"])
    cls = "city" + (" virtual" if c.get("format") == "virtual" else "") + extra
    return (f'<g class="{cls}" data-y="{c["year"]}"><circle class="halo" cx="{x:.0f}" cy="{y:.0f}" r="14"/>'
            f'<circle class="pt" cx="{x:.0f}" cy="{y:.0f}" r="5"/></g>')


def journey_map(conferences, from_dir):
    placed = [c for c in sorted(conferences, key=lambda c: c["year"]) if c.get("status") == "held" and c.get("geo")]
    arcs = []
    for a, b in zip(placed, placed[1:]):
        p, q = map_xy(*a["geo"]), map_xy(*b["geo"])
        if math.dist(p, q) > 1:
            arcs.append(f'<path class="arc" data-y="{b["year"]}" pathLength="1" d="{arc_d(p, q)}"/>')
    cities = "".join(city_mark(c) for c in placed)
    return map_html(from_dir, f'<g class="arcs">{"".join(arcs)}</g>{cities}', themed=True)


# ---------------------------------------------------------------- page assembly

class Site:
    def __init__(self, out_dir, settings, transition=False):
        self.out = out_dir
        self.settings = settings
        self.transition = transition
        self.template = Template((ROOT / "templates" / "base.html").read_text(encoding="utf-8"))
        self.pages = []

    def nav_html(self, from_dir):
        if self.transition:
            return ""
        items = []
        for path, label in NAV:
            current = ' aria-current="page"' if from_dir.startswith(path) else ""
            items.append(f'<li><a href="{rel(from_dir, path)}"{current}>{label}</a></li>')
        return '<nav class="main-nav" id="main-nav" aria-label="Main"><ul>' + "".join(items) + "</ul></nav>"

    def tools_html(self):
        """Light and dark switch (always) and the menu button for small screens (full site only).
        Both only appear when the small script in the page head runs."""
        tools = (f'<button class="theme-toggle" type="button" aria-label="Light or dark mode" '
                 f'title="Light or dark mode">{ICON_SUN}{ICON_MOON}</button>')
        if not self.transition:
            tools += (f'<button class="menu-toggle" type="button" aria-expanded="false" aria-controls="main-nav" '
                      f'aria-label="Menu">{ICON_MENU}</button>')
        return tools

    def footer_html(self, from_dir, link):
        cols = ""
        if not self.transition:
            for heading, links in FOOTER_GROUPS:
                items = "".join(f'<li><a href="{rel(from_dir, p)}">{label}</a></li>' for p, label in links)
                cols += f'<div class="foot-col"><p class="foot-head">{heading}</p><ul>{items}</ul></div>'
        legal = " · ".join(f'<a href="{rel(from_dir, p)}">{label}</a>' for p, label in LEGAL)
        return ('<div class="foot-grid">'
                '<p class="foot-brand">'
                + (f'<img class="only-light" src="{link("logo.svg")}" width="56" height="56" alt="" loading="lazy">'
                   f'<img class="only-dark" src="{link("logo-dark.svg")}" width="56" height="56" alt="" loading="lazy">'
                   if FEATURES["logo"] else '<span class="brand-mark" aria-hidden="true">ICKM</span>')
                + f'<span><strong>{esc(self.settings.get("brand", "ICKM"))}</strong><br>{esc(self.settings["title"])}</span></p>'
                + (f'<nav class="foot-cols" aria-label="Footer">{cols}</nav>' if cols else "") + '</div>'
                f'<p class="foot-note"><span>ICKM · International Conference on Knowledge Management · since 2004</span>'
                f'<span>{legal}</span></p>')

    def write(self, out_dir_rel, title, body, description="", absolute_base=None, head_extra="",
              body_class="", script=False):
        """Write one page to <out>/<out_dir_rel>/index.html (or 404.html when out_dir_rel is "404")."""
        if out_dir_rel == "404":
            target = self.out / "404.html"
            from_dir = ""
        else:
            target = self.out / out_dir_rel / "index.html"
            from_dir = out_dir_rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if absolute_base is not None:
            # The 404 page is served at any address, so it uses absolute links from the base path.
            def link(p):
                return absolute_base + p
        else:
            def link(p):
                return rel(from_dir, p)

        site_title = self.settings["title"]
        page_title = site_title if title == site_title else f"{title} · {site_title}"
        robots = '<meta name="robots" content="noindex, nofollow">' if self.settings.get("noindex") else ""
        nav = self.nav_html(from_dir)
        footer = self.footer_html(from_dir, link)
        if absolute_base is not None:
            nav = re.sub(r'href="(?:\.\./)*([^"]*)"', lambda m: f'href="{absolute_base}{m.group(1)}"', nav)
            footer = re.sub(r'href="(?:\.\./)*([^"]*)"', lambda m: f'href="{absolute_base}{m.group(1)}"', footer)
            body = re.sub(r'href="(?:\.\./)*([^":]*)"', lambda m: f'href="{absolute_base}{m.group(1)}"', body)

        page = self.template.substitute(
            page_title=esc(page_title),
            description=esc(description or self.settings.get("description", "")),
            robots=robots + head_extra,
            css=link("style.css"),
            favicon=link("favicon.svg" if FEATURES["logo"] else "favicon-text.svg"),
            script=f'<script src="{link("site.js")}" defer></script>' if (script or not self.transition) else "",
            body_class=body_class,
            tools=self.tools_html(),
            home=link(""),
            brand=self.brand_html(link),
            nav=nav,
            content=body,
            footer=footer,
        )
        target.write_text(page, encoding="utf-8")
        if out_dir_rel != "404":
            self.pages.append(out_dir_rel)

    def brand_html(self, link):
        """Logo and the full name. With the logo switched on, the header shows the original navy and amber logo
        in light mode and the light version in dark mode (only the visible one loads). Without it, "ICKM" as text."""
        title = self.settings["title"]
        first, _, rest = title.partition(" on ")
        name = f"{esc(first)}<br>on {esc(rest)}" if rest else esc(title)
        brand = esc(self.settings.get("brand", "ICKM"))
        if not FEATURES["logo"]:
            return f'<span class="brand-mark">{brand}</span><span class="brand-name">{name}</span>'
        return (f'<img class="brand-logo only-light" src="{link("logo.svg")}" width="56" height="56" alt="{brand}" loading="lazy">'
                f'<img class="brand-logo only-dark" src="{link("logo-dark.svg")}" width="56" height="56" alt="{brand}" loading="lazy">'
                f'<span class="brand-name">{name}</span>')

    def content_page(self, name, out_dir_rel, cards=False):
        title, text = read_content(name)
        lead, rest = first_paragraph(text)
        body = page_head(title, inline(lead, out_dir_rel) if lead else "")
        if cards:
            body += f'<div class="wrap page-body">{markdown_cards(rest, out_dir_rel)}</div>'
        else:
            body += f'<div class="wrap prose page-body">{markdown(rest, out_dir_rel)}</div>'
        self.write(out_dir_rel, title, body)

    def copy_static(self):
        for f in (ROOT / "static").rglob("*"):
            if not f.is_file():
                continue
            name = f.relative_to(ROOT / "static").as_posix()
            if self.transition and name.startswith(FULL_ONLY):
                continue
            dest = self.out / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if f.suffix == ".css":
                dest.write_text(minify_css(f.read_text(encoding="utf-8")), encoding="utf-8")
            else:
                shutil.copy2(f, dest)
        if ASSETS_LOCAL.is_dir():
            for f in ASSETS_LOCAL.rglob("*"):
                name = f.relative_to(ASSETS_LOCAL).as_posix()
                if not f.is_file() or (self.transition and name.startswith(FULL_ONLY)):
                    continue
                if (name in LOGO_FILES and not FEATURES["logo"]) or (name.startswith("media/") and not FEATURES["videos"]):
                    continue
                dest = self.out / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
        if not self.transition:
            for p in load_photos():
                dest = self.out / "photos" / p["file"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(PHOTOS_LOCAL / p["file"], dest)

    def write_robots_and_sitemap(self):
        (self.out / ".nojekyll").write_text("", encoding="utf-8")
        base = self.settings.get("base_url", "").rstrip("/")
        if self.settings.get("noindex") or not base:
            (self.out / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
            return
        urls = "".join(f"<url><loc>{esc(base + '/' + p)}</loc></url>" for p in self.pages)
        (self.out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n', encoding="utf-8")
        (self.out / "robots.txt").write_text(
            f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")


# ---------------------------------------------------------------- shared page parts

def page_head(title, lead="", eyebrow="", media="", aside="", extra_class=""):
    """Dark band at the top of every page with the page title."""
    cls = "top page-head" + (" with-media video-top" if media else "") + (f" {extra_class}" if extra_class else "")
    text = (f'<p class="eyebrow">{eyebrow}</p>' if eyebrow else "") + f"<h1>{esc(title)}</h1>"
    if lead:
        text += f'<p class="lead">{lead}</p>'
    grid = "ph-grid has-aside" if aside else "ph-grid"
    return (f'<section class="{cls}">{media}'
            f'<div class="wrap {grid}"><div class="ph-text">{text}</div>{aside}</div></section>')


def photo_figure(p, from_dir, cls=""):
    """One placeholder photo with caption and a visible "Placeholder photo" label."""
    src = rel(from_dir, f"photos/{p['file']}")
    classes = " ".join(x for x in ("photo reveal", p.get("layout", ""), cls) if x)
    return (f'<figure class="{classes}"><img src="{src}" alt="{esc(p.get("alt", ""))}" width="{p["width"]}" '
            f'height="{p["height"]}" loading="lazy" decoding="async">'
            f'<figcaption>{esc(p.get("caption", ""))}</figcaption>'
            '<span class="ph-badge">Placeholder photo</span></figure>')


def photos_for(place, year=None):
    return [p for p in load_photos() if place in p.get("places", []) and (year is None or p.get("year") == year)]


def photo_band(from_dir):
    """Home page: photos from past conferences (only with photos = true)."""
    photos = photos_for("home")
    if not photos:
        return ""
    return ('<section class="band moments" aria-labelledby="moments-title"><div class="wrap">'
            '<div class="section-head reveal"><p class="eyebrow">Moments</p>'
            '<h2 id="moments-title">Moments from ICKM</h2></div>'
            '<div class="mosaic">' + "".join(photo_figure(p, from_dir) for p in photos) + "</div></div></section>")


def video_bg(from_dir, name):
    """Background video. The script loads it shortly before it is visible. Without the script, with reduced
    motion or with data saving on, only the still image shows. Nothing while videos are switched off."""
    if not FEATURES["videos"]:
        return ""
    return (f'<div class="top-media" aria-hidden="true">'
            f'<video data-src="{rel(from_dir, f"media/{name}.mp4")}" poster="{rel(from_dir, f"media/{name}.webp")}" '
            'muted loop playsinline preload="none"></video></div>')


# ---------------------------------------------------------------- conference pages

def year_page_body(c, from_dir, prev_c=None, next_c=None):
    year = c["year"]
    status = c.get("status")
    rows = []

    def row(label, value):
        if value:
            rows.append(f"<dt>{label}</dt><dd>{value}</dd>")

    pager = ['<nav class="pager" aria-label="Other years">']
    pager.append(f'<a rel="prev" href="{rel(from_dir, f"conferences/{prev_c["year"]}/")}">← ICKM {prev_c["year"]}</a>'
                 if prev_c else "<span></span>")
    pager.append(f'<a href="{rel(from_dir, "conferences/")}">All conferences</a>')
    pager.append(f'<a rel="next" href="{rel(from_dir, f"conferences/{next_c["year"]}/")}">ICKM {next_c["year"]} →</a>'
                 if next_c else "<span></span>")
    pager.append("</nav>")
    pager = "".join(pager)

    if status in ("announced", "planned"):
        lead = esc(c["theme"]) if c.get("theme") else "Details coming soon."
        eyebrow = esc(fmt_place(c)) if c.get("city") or c.get("country") else "Next conference"
        body = page_head(f"ICKM {year}", lead, eyebrow=eyebrow, extra_class="is-next")
        inner = f"<p>{esc(c['notes'])}</p>" if c.get("notes") else ""
        return body + f'<div class="wrap page-body">{inner}{next_sections(c, from_dir)}{pager}</div>'

    if status == "cancelled":
        body = page_head(f"ICKM {year}", "This conference was cancelled.", eyebrow="Conference")
        inner = f"<p>{esc(c['notes'])}</p>" if c.get("notes") else ""
        return body + f'<div class="wrap prose page-body">{inner}{pager}</div>'

    row("Location", esc(fmt_place(c)))
    row("Venue", esc(c.get("venue", "")))
    row("Dates", esc(fmt_dates(c)))
    row("Format", esc(FORMATS.get(c.get("format", ""), "")))
    row("Hosts", esc(", ".join(c.get("hosts", []))))
    row("Partners", esc(", ".join(c.get("partners", []))))
    row("Joint event", esc(c.get("joint", "")))
    row("Proceedings", proceedings_html(c))
    if c.get("website"):
        row("Conference website", ext_link(c["website"]))
    if c.get("website_archive"):
        row("Archived website", ext_link(c["website_archive"], "Copy in the Internet Archive"))

    aside = ""
    if c.get("geo"):
        aside = f'<div class="ph-map">{map_html(from_dir, city_mark(c, " pin"), themed=True)}</div>'
    body = page_head(f"ICKM {year}", esc(c.get("theme", "")), eyebrow=esc(fmt_place(c)) or "Conference", aside=aside)
    inner = '<dl class="facts">' + "".join(rows) + "</dl>"
    if c.get("notes"):
        inner += f"<p>{esc(c['notes'])}</p>"
    photos = photos_for("year", year)
    if photos:
        inner += '<div class="year-photos">' + "".join(photo_figure(p, from_dir) for p in photos) + "</div>"
    return body + f'<div class="wrap prose page-body">{inner}{pager}</div>'


def next_sections(c, from_dir):
    """The usual parts of a conference website for the coming year. Each shows "To be announced" until the
    conference file has it (fields cfp, deadlines, submission, registration, venue, programme)."""
    tba = '<p class="tba">To be announced</p>'

    def link_or_tba(key, label):
        return f'<p><a class="more" href="{esc(c[key])}">{label}</a></p>' if c.get(key) else tba

    dates = ""
    if c.get("deadlines"):
        rows = "".join(f"<li><span>{esc(d.get('label', ''))}</span><span>{esc(fmt_dates({'start': d.get('date')}))}</span></li>"
                       for d in c["deadlines"])
        dates = f'<ul class="deadlines">{rows}</ul>'
    when = esc(fmt_dates(c))
    where = esc(", ".join(p for p in (c.get("venue", ""), fmt_place(c)) if p))
    cards = [
        ("Call for papers", link_or_tba("cfp", "Read the call for papers")),
        ("Important dates", dates or (f"<p>{when}</p>" if when else tba)),
        ("Submission", link_or_tba("submission", "Submit a paper")),
        ("Registration", link_or_tba("registration", "Register")),
        ("Venue and travel", f"<p>{where}</p>" if where else tba),
        ("Programme", link_or_tba("programme", "See the programme")),
    ]
    html_cards = "".join(f'<section class="info-card reveal"><h2>{title}</h2>{content}</section>' for title, content in cards)
    html_cards += ('<section class="info-card info-card-dark on-dark reveal"><h2>Questions</h2>'
                   '<p>Write to <a href="mailto:office@ickm.net">office@ickm.net</a>.</p></section>')
    return f'<div class="card-grid">{html_cards}</div>'


def people_body(from_dir):
    """Cards per group from data/people.toml (data/people.local.toml wins if present, not in git).
    Without a name, the card shows the role and "Name follows"."""
    path = ROOT / "data" / "people.local.toml"
    if not path.exists():
        path = ROOT / "data" / "people.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out = []
    for g in data.get("group", []):
        cards = []
        for person in g.get("person", []):
            name = person.get("name", "")
            initials = "".join(w[0] for w in name.replace("Dr. ", "").split()[:2]).upper() if name else ""
            sub = ", ".join(x for x in (person.get("affiliation", ""), person.get("country", "")) if x)
            name_html = esc(name) if name else '<span class="tba">Name follows</span>'
            if name and person.get("url"):
                name_html = f'<a href="{esc(person["url"])}">{esc(name)}</a>'
            cards.append(f'<li class="person reveal{"" if name else " open"}"><span class="avatar" aria-hidden="true">'
                         f'{esc(initials)}</span><span class="p-role">{esc(person.get("role", ""))}</span>'
                         f'<span class="p-name">{name_html}</span>'
                         + (f'<span class="p-sub">{esc(sub)}</span>' if sub else "") + "</li>")
        intro = f'<p class="section-lead">{esc(g["intro"])}</p>' if g.get("intro") else ""
        out.append(f'<section class="people-group"><h2>{esc(g["title"])}</h2>{intro}'
                   f'<ul class="people">{"".join(cards)}</ul></section>')
    return "".join(out)


def partners_body(conferences, from_dir):
    """Joint events, partners and hosts, year by year, taken from the conference file."""
    items = []
    for c in sorted(conferences, key=lambda c: c["year"]):
        if c.get("status") != "held":
            continue
        lines = []
        if c.get("joint"):
            lines.append(f'<p class="vt-theme">{esc(c["joint"])}</p>')
        if c.get("hosts"):
            lines.append(f'<p class="vt-theme">Host: {esc(", ".join(c["hosts"]))}</p>')
        if c.get("partners"):
            lines.append(f'<p class="vt-theme">Partners: {esc(", ".join(c["partners"]))}</p>')
        if not lines:
            continue
        link = f'<a href="{rel(from_dir, f"conferences/{c["year"]}/")}">{c["year"]}</a>'
        items.append(f'<li class="vt held reveal"><span class="vt-year">{link}</span><span class="vt-dot"></span>'
                     f'<div><p class="vt-place">{esc(fmt_place(c))}</p>{"".join(lines)}</div></li>')
    return '<ol class="vtimeline">' + "".join(items) + "</ol>"


def about_body(conferences):
    """Who we are: text from content/about.md, numbers from the conference file and links to the other pages."""
    title, text = read_content("about")
    lead, rest = first_paragraph(text)
    d = "about/"
    held = [c for c in conferences if c.get("status") == "held"]
    first = min(held, key=lambda c: c["year"])
    continents = {CONTINENTS.get(c.get("country") or c.get("city", "")) for c in held} - {None}
    volumes = sum(1 for c in held if c.get("proceedings", {}).get("url"))
    stats = [(str(first["year"]), f"First conference, in {esc(short_place(first))}"),
             (str(len(continents)), "Continents with host cities"),
             (str(volumes), "Proceedings volumes linked on this site")]
    stat_html = "".join(f'<li class="reveal"><span class="stat-n">{n}</span><span class="stat-l">{l}</span></li>'
                        for n, l in stats)
    links = [("people/", "People", "Who runs ICKM and its conferences."),
             ("history/", "History", "Every conference since 2004, year by year."),
             ("publications/", "Publications", "Proceedings of past conferences."),
             ("about/partners/", "Partners", "Joint conferences and partner organisations."),
             ("conferences/", "Conferences", "One page for every year."),
             ("community/", "Community", "Ways to take part between the conferences.")]
    link_html = "".join(f'<a class="link-card reveal" href="{rel(d, p)}"><span class="lc-title">{t}</span>'
                        f'<span class="lc-text">{x}</span></a>' for p, t, x in links)
    banner = "".join(photo_figure(p, d, "banner") for p in photos_for("about")[:1])
    return (page_head(title, inline(lead, d), eyebrow="About ICKM")
            + f'<div class="wrap page-body"><ul class="stats">{stat_html}</ul>{banner}'
            + f'<div class="prose">{markdown(rest, d)}</div>'
            + f'<h2 class="grid-title">Find out more</h2><div class="link-grid">{link_html}</div></div>')


# Filter above the conference cards. Hidden until the script runs; cards move to their new place smoothly.
FILTERS = ('<div class="filters" hidden role="group" aria-label="Show conferences">'
           '<button type="button" data-filter="all" aria-pressed="true">All</button>'
           '<button type="button" data-filter="2000s" aria-pressed="false">2004 to 2009</button>'
           '<button type="button" data-filter="2010s" aria-pressed="false">2010 to 2019</button>'
           '<button type="button" data-filter="2020s" aria-pressed="false">2020 onwards</button>'
           '<button type="button" data-filter="proc" aria-pressed="false">Proceedings online</button>'
           '<p class="filter-count" aria-live="polite"></p></div>')


def conference_cards(conferences, from_dir):
    cards = []
    for c in sorted(conferences, key=lambda c: c["year"], reverse=True):
        year = c["year"]
        k = kind(c)
        tags = []
        if k == "next" and not c.get("theme"):
            place, theme = "Details coming soon", ""
            tags.append("Next")
        elif k == "cancelled":
            place, theme = "Cancelled", c.get("notes", "")
        else:
            place, theme = fmt_place(c), c.get("theme", "")
            if k == "virtual":
                tags.append("Virtual")
            if c.get("joint"):
                tags.append("Joint event")
            if c.get("proceedings", {}).get("url"):
                tags.append("Proceedings")
        tag_html = "".join(f'<span class="tag">{t}</span>' for t in tags)
        cards.append(
            f'<li class="conf-card {k} reveal" data-era="{"2000s" if year < 2010 else "2010s" if year < 2020 else "2020s"}" '
            f'data-proc="{1 if c.get("proceedings", {}).get("url") else 0}"><a href="{rel(from_dir, f"conferences/{year}/")}">'
            f'<span class="cy">{year}</span><span class="cp">{esc(place)}</span>'
            + (f'<span class="ct">{esc(theme)}</span>' if theme else "")
            + (f'<span class="tags">{tag_html}</span>' if tag_html else "")
            + "</a></li>")
    return '<ul class="conf-grid" aria-label="All ICKM conferences, newest first">' + "".join(cards) + "</ul>"


def shelf(conferences, from_dir):
    """Publications as a bookshelf: one spine per conference year. Decorative, the list below has the same links."""
    books = []
    held = [c for c in sorted(conferences, key=lambda c: c["year"]) if c.get("status") == "held"]
    for i, c in enumerate(held):
        p = c.get("proceedings") or {}
        publisher = p.get("publisher", "")
        cls = {"World Scientific": "ws", "UNT Digital Library": "unt"}.get(publisher, "other" if p.get("url") else "none")
        label = publisher if p.get("url") else "Link to follow"
        inner = f'<span class="b-year">{c["year"]}</span><span class="b-pub">{esc(label)}</span>'
        tag = f'<a href="{esc(p["url"])}" tabindex="-1">{inner}</a>' if p.get("url") else f"<span>{inner}</span>"
        books.append(f'<li class="book {cls}" style="--i:{i};--h:{12 + (c["year"] * 7) % 5}rem">{tag}</li>')
    return f'<ul class="shelf" aria-hidden="true">{"".join(books)}</ul>'


def publications_body(conferences, from_dir):
    items = []
    for c in sorted(conferences, key=lambda c: c["year"]):
        if c.get("status") != "held":
            continue
        p = proceedings_html(c)
        link = f'<a href="{rel(from_dir, f"conferences/{c["year"]}/")}">ICKM {c["year"]}</a>'
        items.append(f"<li><span class=\"pub-year\">{link}</span><span>{p if p else 'Link to follow'}</span></li>")
    return '<ul class="pub-list">' + "".join(items) + "</ul>"


def timeline_body(conferences, from_dir):
    """Vertical timeline on the History page. The line fills while scrolling."""
    items = []
    for c in sorted(conferences, key=lambda c: c["year"]):
        year = c["year"]
        k = kind(c)
        link = f'<a href="{rel(from_dir, f"conferences/{year}/")}">{year}</a>'
        if k == "cancelled":
            place, theme = "Cancelled", c.get("notes", "")
        elif k == "next" and not c.get("theme"):
            place, theme = "Details coming soon", ""
        else:
            place = fmt_place(c) + (" (virtual)" if k == "virtual" else "")
            theme = c.get("theme", "")
        items.append(f'<li class="vt {k} reveal"><span class="vt-year">{link}</span><span class="vt-dot"></span>'
                     f'<div><p class="vt-place">{esc(place)}</p>'
                     + (f'<p class="vt-theme">{esc(theme)}</p>' if theme else "") + "</div></li>")
    return ('<div class="vt-wrap"><span class="vt-head" aria-hidden="true"></span>'
            '<ol class="vtimeline beam">' + "".join(items) + "</ol></div>")


def next_conference(conferences):
    nxt = upcoming(conferences)
    return min(nxt, key=lambda c: c["year"]) if nxt else None


def latest_conference(conferences):
    held = [c for c in conferences if c.get("status") == "held"]
    return max(held, key=lambda c: c["year"]) if held else None


def next_block_plain(conferences):
    c = next_conference(conferences)
    if not c:
        return ""
    return (f'<section class="card" aria-labelledby="next"><h2 id="next">Next conference</h2>'
            f"<p><strong>ICKM {c['year']}</strong>: details coming soon.</p></section>")


def latest_block(conferences, from_dir, link_year_page=True):
    c = latest_conference(conferences)
    if not c:
        return ""
    title = f"ICKM {c['year']}"
    if link_year_page:
        title = f'<a href="{rel(from_dir, f"conferences/{c["year"]}/")}">{title}</a>'
    parts = [f"<strong>{title}</strong>", esc(fmt_place(c)), esc(fmt_dates(c))]
    text = ", ".join(p for p in parts if p)
    extra = ""
    if c.get("joint"):
        extra += f"<p>{esc(c['joint'])}</p>"
    if c.get("website"):
        extra += f"<p>Conference website: {ext_link(c['website'])}</p>"
    return (f'<section class="card" aria-labelledby="latest"><h2 id="latest">Latest conference</h2>'
            f"<p>{text}</p>{extra}</section>")


# ---------------------------------------------------------------- home page scenes

def home_hero(settings, conferences, lead):
    first_year = min(c["year"] for c in conferences if c.get("status") == "held")
    title = settings["title"]
    first, _, rest = title.partition(" on ")
    # Each word in its own span, so the title can rise word by word (no effect with reduced motion).
    words = first.split() + (["on"] + rest.split() if rest else [])
    spans = [f'<span class="w" style="--i:{i}">{esc(w)}</span>' for i, w in enumerate(words)]
    n_first = len(first.split())
    h1 = " ".join(spans[:n_first]) + (f' <span class="h1-sub">{" ".join(spans[n_first:])}</span>' if rest else "")
    return ('<section class="top hero video-top">' + video_bg("", "hero-network")
            + '<div class="wrap hero-inner">'
            f'<p class="eyebrow shimmer">Since {first_year}</p><h1>{h1}</h1>'
            f'<p class="hero-lead">{lead}</p>'
            '<p class="actions">'
            f'<a class="btn btn-primary magnetic" href="{rel("", "conferences/")}">All conferences</a>'
            f'<a class="btn btn-ghost magnetic" href="#journey">Around the world</a></p></div>'
            '<a class="scroll-cue" href="#glance"><span class="sr">Scroll down</span></a></section>')


def glance(conferences):
    """"At a glance": tiles with numbers, a ranked bar chart and the host cities, all from the conference file."""
    held = sorted((c for c in conferences if c.get("status") == "held"), key=lambda c: c["year"])
    if not held:
        return ""
    first, last = held[0], held[-1]
    span = last["year"] - first["year"]

    # Host conferences by continent, largest first (ranked bars, one colour)
    counts = {}
    for c in held:
        cont = CONTINENTS.get(c.get("country") or c.get("city", ""))
        if cont:
            counts[cont] = counts.get(cont, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top = ranked[0][1] if ranked else 1
    bars = "".join(
        f'<li title="{esc(name)}: {n} conference{"s" if n != 1 else ""}"><span class="rb-name">{esc(name)}</span>'
        f'<span class="rb-track"><span class="rb-fill" style="--v:{n / top:.3f};--i:{i}"></span></span>'
        f'<span class="rb-val">{n}</span></li>'
        for i, (name, n) in enumerate(ranked))

    # Proceedings linked on this site, by publisher
    pubs = {}
    for c in held:
        pr = c.get("proceedings") or {}
        if pr.get("url"):
            pubs.setdefault(pr.get("publisher", "Other"), []).append(c["year"])
    volumes = sum(len(v) for v in pubs.values())
    pub_text = " · ".join(f"{esc(k)} ({v[0]}" + (f" to {v[-1]})" if len(v) > 1 else ")") for k, v in pubs.items())

    joint = sum(1 for c in held if c.get("joint"))
    cities = "".join(f"<li>{esc(short_place(c))} <b>{c['year']}</b></li>" for c in held)
    nxt = next_conference(conferences)
    next_tile = ""
    if nxt:
        detail = "Details coming soon." if not nxt.get("theme") else esc(fmt_place(nxt))
        next_tile = (f'<a class="tile t-next" href="{rel("", f"conferences/{nxt["year"]}/")}">'
                     f'<span class="tile-k">Next conference</span><span class="tile-n tile-n-sm">ICKM {nxt["year"]}</span>'
                     f'<span class="tile-l">{detail}</span></a>')
    return ('<section class="band glance" id="glance" aria-labelledby="glance-title"><div class="wrap">'
            '<div class="section-head reveal"><p class="eyebrow">ICKM</p><h2 id="glance-title">At a glance</h2></div>'
            '<div class="bento" data-inview>'
            f'<div class="tile t-years"><span class="tile-k">Since {first["year"]}</span>'
            f'<span class="tile-n" data-count="{span}">{span}</span>'
            f'<span class="tile-l">years from {esc(short_place(first))} {first["year"]} to {esc(short_place(last))} {last["year"]}</span></div>'
            f'<div class="tile t-conti"><span class="tile-k">Host conferences by continent</span>'
            f'<ul class="rbars">{bars}</ul></div>'
            f'<a class="tile t-procs" href="{rel("", "publications/")}"><span class="tile-k">Proceedings</span>'
            f'<span class="tile-n" data-count="{volumes}">{volumes}</span>'
            f'<span class="tile-l">volumes linked on this site</span><span class="tile-s">{pub_text}</span></a>'
            f'<a class="tile t-joint" href="{rel("", "about/partners/")}"><span class="tile-k">Partners</span>'
            f'<span class="tile-n" data-count="{joint}">{joint}</span>'
            f'<span class="tile-l">conferences held together with other conferences</span></a>'
            f'<div class="tile t-cities"><span class="tile-k">Host cities</span>'
            f'<div class="marquee"><ul class="mq-track">{cities}</ul><ul class="mq-track" aria-hidden="true">{cities}</ul></div></div>'
            f'{next_tile}</div></div></section>')


def home_intro(rest):
    if not rest.strip():
        return ""
    return ('<section class="band intro"><div class="wrap narrow reveal">'
            '<p class="eyebrow">About ICKM</p>' + markdown(rest, "")
            + f'<p><a class="more" href="{rel("", "about/")}">About ICKM</a></p></div></section>')


def year_strip(conferences):
    """Scene 2: one dot per year, the line draws itself while scrolling."""
    items = []
    ordered = sorted(conferences, key=lambda c: c["year"])
    for i, c in enumerate(ordered):
        k = kind(c)
        label = {"cancelled": "Cancelled", "next": "Next"}.get(k) or short_place(c)
        if k == "virtual":
            label += " (virtual)"
        if k == "cancelled":
            tip_text = c.get("notes", "Cancelled")
        elif k == "next" and not c.get("theme"):
            tip_text = "Details coming soon."
        else:
            tip_text = c.get("theme", "")
        side = " tip-l" if i < 3 else " tip-r" if i >= len(ordered) - 3 else ""
        tip = (f'<span class="tip{side}" aria-hidden="true"><b>{c["year"]} · {esc(fmt_place(c) or label)}</b>'
               + (f'<span>{esc(tip_text)}</span>' if tip_text else "") + "</span>")
        items.append(f'<li class="{k}" style="--i:{i}"><a href="{rel("", f"conferences/{c["year"]}/")}" '
                     f'aria-label="{c["year"]}, {esc(label)}"><span class="dot"></span>'
                     f'<span class="y">{c["year"]}</span><span class="c" aria-hidden="true">{esc(label)}</span>{tip}</a></li>')
    n = len(items)
    return ('<section class="band band-soft" aria-labelledby="since-title" id="since"><div class="wrap">'
            '<div class="section-head reveal"><p class="eyebrow">Timeline</p>'
            '<h2 id="since-title">Every year since 2004</h2>'
            '<p class="section-lead">One dot for each year. Select a year to open its page.</p></div>'
            f'<div class="years-scroll"><ol class="years" style="--n:{n}">{"".join(items)}</ol></div>'
            '<ul class="legend" aria-label="Legend">'
            '<li><span class="key held"></span>Held</li><li><span class="key virtual"></span>Virtual</li>'
            '<li><span class="key cancelled"></span>Cancelled</li><li><span class="key next"></span>Next</li>'
            '</ul></div></section>')


def journey(conferences):
    """Scene 3: the map stays in place while the text steps scroll past. Each step lights up its cities."""
    confs = sorted(conferences, key=lambda c: c["year"])
    done = [c for c in confs if c.get("status") in ("held", "cancelled")]
    first, last = done[0]["year"], done[-1]["year"]
    steps = ['<div class="step" data-upto="0" data-years=""><div class="step-card">'
             '<p class="eyebrow">Around the world</p><h2 id="journey-title">Where ICKM has met</h2>'
             f'<p>Each light on the map is a host city. Scroll on to follow the conferences from {first} '
             f'to {last}.</p></div></div>']
    for start in range(first, last + 1, 5):
        chunk = [c for c in done if start <= c["year"] < start + 5]
        if not chunk:
            continue
        end = chunk[-1]["year"]
        countries = []
        for c in chunk:
            name = c.get("country") or c.get("city")
            if c.get("status") == "held" and name and name not in countries:
                countries.append(name)
        stops = []
        for c in chunk:
            if c.get("status") == "cancelled":
                text = f'<span class="muted">{esc(c["country"]) + ", cancelled" if c.get("country") else "Cancelled"}</span>'
            else:
                text = esc(short_place(c)) + (' <span class="muted">(virtual)</span>' if c.get("format") == "virtual" else "")
            stops.append(f'<li><a href="{rel("", f"conferences/{c["year"]}/")}"><b>{c["year"]}</b> {text}</a></li>')
        years = " ".join(str(c["year"]) for c in chunk)
        steps.append(f'<div class="step" data-upto="{end}" data-years="{years}"><div class="step-card">'
                     f'<p class="eyebrow">{start} to {end}</p><h3>{" · ".join(esc(n) for n in countries)}</h3>'
                     f'<ul class="stops">{"".join(stops)}</ul></div></div>')
    nxt = next_conference(conferences)
    if nxt:
        steps.append(f'<div class="step" data-upto="9999" data-years=""><div class="step-card">'
                     f'<p class="eyebrow">Next</p><h3>ICKM {nxt["year"]}</h3><p>Details coming soon.</p>'
                     f'<p><a class="more" href="{rel("", "history/")}">The full history</a></p></div></div>')
    return ('<section class="journey" id="journey" aria-labelledby="journey-title">'
            '<div class="journey-inner">'
            f'<div class="journey-map">{journey_map(conferences, "")}</div>'
            f'<div class="journey-steps">{"".join(steps)}</div></div></section>')


def latest_band(conferences):
    c = latest_conference(conferences)
    if not c:
        return ""
    meta = " · ".join(p for p in (esc(fmt_place(c)), esc(fmt_dates(c))) if p)
    right = f'<p class="theme">{esc(c["theme"])}</p>' if c.get("theme") else ""
    if c.get("joint"):
        right += f"<p>{esc(c['joint'])}</p>"
    links = [f'<a class="btn btn-line" href="{rel("", f"conferences/{c["year"]}/")}">ICKM {c["year"]}</a>']
    if c.get("website"):
        links.append(f'<a class="btn btn-quiet" href="{esc(c["website"])}">Conference website</a>')
    right += f'<p class="actions">{"".join(links)}</p>'
    return ('<section class="band latest" aria-labelledby="latest"><div class="wrap latest-grid reveal">'
            f'<div><p class="eyebrow">Latest conference</p><h2 id="latest">ICKM {c["year"]}</h2>'
            f'<p class="meta">{meta}</p></div><div>{right}</div></div></section>')


def next_band(conferences):
    c = next_conference(conferences)
    if not c:
        return ""
    if c.get("theme"):
        detail = " · ".join(p for p in (esc(fmt_place(c)), esc(fmt_dates(c))) if p) or "Details coming soon."
    else:
        detail = "Details coming soon."
    return ('<section class="next-band" aria-labelledby="next" data-inview>'
            '<div class="lamp" aria-hidden="true"><span class="lamp-l"></span><span class="lamp-r"></span>'
            '<span class="lamp-bar"></span></div>'
            '<div class="wrap reveal"><p class="eyebrow">Next conference</p>'
            f'<h2 id="next">ICKM {c["year"]}</h2><p class="lead">{detail}</p>'
            f'<p class="actions"><a class="btn btn-ghost magnetic" href="{rel("", f"conferences/{c["year"]}/")}">'
            f'ICKM {c["year"]}</a></p></div></section>')


# ---------------------------------------------------------------- builds

def build_full(settings, conferences, out_root):
    out = out_root / "_site"
    reset(out)
    s = Site(out, settings)
    s.copy_static()
    (out / "world.svg").write_text(world_svg(), encoding="utf-8")
    (out / "world-light.svg").write_text(world_svg(land="#d9e2ef", dots="#8aa2c6"), encoding="utf-8")

    title, text = read_content("home")
    lead, rest = first_paragraph(text)
    body = (home_hero(settings, conferences, inline(lead, "")) + glance(conferences) + year_strip(conferences)
            + journey(conferences) + photo_band("")
            + home_intro(rest) + latest_band(conferences) + next_band(conferences))
    s.write("", settings["title"], body, body_class="home", script=True)

    s.write("about/", "Who we are", about_body(conferences))
    title, text = read_content("partners")
    lead, rest = first_paragraph(text)
    s.write("about/partners/", title, page_head(title, inline(lead, "about/partners/"), eyebrow="About ICKM")
            + f'<div class="wrap prose page-body">{markdown(rest, "about/partners/")}'
            + partners_body(conferences, "about/partners/") + "</div>")
    title, text = read_content("people")
    lead, rest = first_paragraph(text)
    s.write("people/", title, page_head(title, inline(lead, "people/"), eyebrow="About ICKM")
            + f'<div class="wrap page-body"><div class="prose">{markdown(rest, "people/")}</div>'
            + people_body("people/") + "</div>")
    for name in ("community", "contact"):
        s.content_page(name, f"{name}/", cards=True)
    for name in ("imprint", "privacy"):
        s.content_page(name, f"{name}/")

    title, text = read_content("conferences")
    lead, rest = first_paragraph(text)
    body = (page_head(title, inline(lead, "conferences/"), eyebrow="Since 2004")
            + f'<div class="wrap page-body">{markdown(rest, "conferences/")}'
            + FILTERS + conference_cards(conferences, "conferences/") + "</div>")
    s.write("conferences/", title, body)

    ordered = sorted(conferences, key=lambda c: c["year"])
    for i, c in enumerate(ordered):
        d = f"conferences/{c['year']}/"
        prev_c = ordered[i - 1] if i > 0 else None
        next_c = ordered[i + 1] if i + 1 < len(ordered) else None
        s.write(d, f"ICKM {c['year']}", year_page_body(c, d, prev_c, next_c),
                description=f"ICKM {c['year']}: {c.get('theme', '')}".strip(": "))

    title, text = read_content("history")
    lead, rest = first_paragraph(text)
    body = (page_head(title, inline(lead, "history/") if lead else "", eyebrow="Since 2004",
                      media=video_bg("history/", "history-stream"))
            + f'<div class="wrap prose page-body">{markdown(rest, "history/")}'
            + timeline_body(conferences, "history/") + "</div>")
    s.write("history/", title, body, script=True)

    title, text = read_content("publications")
    lead, rest = first_paragraph(text)
    body = (page_head(title, inline(lead, "publications/"), eyebrow="Proceedings")
            + f'<div class="wrap page-body">{shelf(conferences, "publications/")}'
            + f'<div class="prose">{markdown(rest, "publications/")}'
            + publications_body(conferences, "publications/") + "</div></div>")
    s.write("publications/", title, body)

    # /next/ always points to the next conference (fixed address for flyers and slides).
    nxt = upcoming(conferences)
    target_year = min(c["year"] for c in nxt) if nxt else max(c["year"] for c in conferences)
    target = rel("next/", f"conferences/{target_year}/")
    redirect = (page_head("Next ICKM", "This address always leads to the next ICKM.")
                + f'<div class="wrap prose page-body"><p><a href="{target}">Continue to ICKM {target_year}</a>.</p></div>')
    s.write("next/", f"ICKM {target_year}", redirect,
            head_extra=f'<meta http-equiv="refresh" content="0; url={target}">')

    title, text = read_content("404")
    s.write("404", title, page_head(title) + f'<div class="wrap prose page-body">{markdown(text, "")}</div>',
            absolute_base=settings.get("full_path", settings.get("base_path", "/")))
    s.write_robots_and_sitemap()
    return out


def build_transition(settings, conferences, out_root):
    out = out_root / "_site_transition"
    reset(out)
    s = Site(out, settings, transition=True)
    s.copy_static()
    title, text = read_content("transition")
    lead, rest = first_paragraph(text)
    netmark = (ROOT / "templates" / "netmark.svg").read_text(encoding="utf-8")
    head = (f'<section class="top page-head transition-head"><div class="wrap">{netmark}'
            f'<p class="eyebrow">Since 2004</p><h1>{esc(title)}</h1>'
            f'<p class="lead">{inline(lead, "")}</p></div></section>')
    title2, contact = read_content("transition-contact")
    cards = (markdown(rest, "") + next_block_plain(conferences)
             + latest_block(conferences, "", link_year_page=False)
             + f'<section class="card" aria-labelledby="contact"><h2 id="contact">{esc(title2)}</h2>'
             + markdown(contact, "") + "</section>")
    body = head + f'<div class="wrap prose page-body">{cards}</div>'
    s.write("", settings["title"], body, body_class="transition")
    for name in ("imprint", "privacy"):
        s.content_page(name, f"{name}/")
    title, text = read_content("404-transition")
    s.write("404", title, page_head(title) + f'<div class="wrap prose page-body">{markdown(text, "")}</div>',
            absolute_base=settings.get("base_path", "/"))
    s.write_robots_and_sitemap()
    return out


def reset(out):
    # Retry a few times: sync tools (Dropbox, OneDrive) briefly lock files and folders.
    for attempt in range(20):
        try:
            if out.exists():
                shutil.rmtree(out)
            out.mkdir(parents=True)
            return
        except PermissionError:
            time.sleep(0.5)
    sys.exit(f"Could not clear {out}. Close programs that use it and run the build again.")


def output_root():
    """Where the built sites go. Default: next to this file.

    A file local.toml (not in git) can set build_dir, for example to keep the output out of a synced folder.
    """
    local = ROOT / "local.toml"
    if local.exists():
        build_dir = tomllib.loads(local.read_text(encoding="utf-8")).get("build_dir")
        if build_dir:
            return Path(build_dir).expanduser()
    return ROOT


def main():
    settings = tomllib.loads((ROOT / "site.toml").read_text(encoding="utf-8"))
    local = ROOT / "local.toml"
    if local.exists():
        for key, value in tomllib.loads(local.read_text(encoding="utf-8")).items():
            if key in FEATURES:
                settings[key] = value
    for key in FEATURES:
        FEATURES[key] = bool(settings.get(key, False))
    data = tomllib.loads((ROOT / "data" / "conferences.toml").read_text(encoding="utf-8"))
    conferences = data["conference"]
    years = [c["year"] for c in conferences]
    if len(years) != len(set(years)):
        sys.exit("conferences.toml: a year appears twice")

    out_root = output_root()
    full = build_full(settings, conferences, out_root)
    transition = build_transition(settings, conferences, out_root)

    publish = out_root / "_publish"
    reset(publish)
    source = transition if settings.get("publish") == "transition" else full
    shutil.copytree(source, publish, dirs_exist_ok=True)

    print(f"Built {full.name}/, {transition.name}/ and _publish/ (= {source.name}/) in {out_root}")


if __name__ == "__main__":
    main()
