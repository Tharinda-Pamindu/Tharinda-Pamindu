"""Build the animated profile panels in assets/.

    python scripts/build_profile.py            # refresh GitHub stats, then build
    python scripts/build_profile.py --offline  # build from scripts/profile-data.json

Needs Pillow and fontTools (pip install pillow fonttools). Fonts (Space Grotesk and
JetBrains Mono, SIL OFL) and brand icons (Simple Icons, CC0) are vendored in
scripts/vendor, subset per panel and embedded so each SVG renders on GitHub exactly
as designed. Output is deterministic, so the CI job only commits real changes.
"""
import base64
import datetime as dt
import hashlib
import io
import json
import math
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "scripts" / "vendor"
OUT = ROOT / "assets"
DATA = ROOT / "scripts" / "profile-data.json"
USER = "Tharinda-Pamindu"

# ── palette ──────────────────────────────────────────────────────────────────
WHITE, MUTED, DIM, LINE, CARD = "#f2f4f8", "#8a93a6", "#5d6577", "#272e42", "#1a1f2e"
ORANGE, AMBER, BLUE, GREEN, RED, PURPLE = "#ff7a1a", "#ffb52e", "#4ea8ff", "#2fd48a", "#ff5a4e", "#c77dff"

FONTS = {  # css class -> (file, weight, fallback stack)
    "sg": ("space-grotesk-latin-700-normal.woff", 700, "'Segoe UI',Helvetica,Arial,sans-serif"),
    "sgm": ("space-grotesk-latin-500-normal.woff", 500, "'Segoe UI',Helvetica,Arial,sans-serif"),
    "jb": ("jetbrains-mono-latin-400-normal.woff", 400, "ui-monospace,Menlo,Consolas,monospace"),
    "jbb": ("jetbrains-mono-latin-700-normal.woff", 700, "ui-monospace,Menlo,Consolas,monospace"),
}
TT = {k: TTFont(VENDOR / "fonts" / f, recalcTimestamp=False) for k, (f, _, _) in FONTS.items()}
ICONS = json.loads((VENDOR / "icons.json").read_text(encoding="utf-8"))["icons"]
PHOTO = Image.open(ROOT / "photo.png").convert("RGB")
USED = {k: set() for k in FONTS}


# ── data ─────────────────────────────────────────────────────────────────────
def github(path):
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-readme-builder"})
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def load_stats(offline):
    if not offline:
        try:
            user = github(f"users/{USER}")
            repos, page = [], 1
            while True:
                batch = github(f"users/{USER}/repos?per_page=100&page={page}")
                repos += batch
                if len(batch) < 100:
                    break
                page += 1
            langs = {}
            for r in repos:
                if not r["fork"] and r["language"]:
                    langs[r["language"]] = langs.get(r["language"], 0) + 1
            stats = {
                "public_repos": user["public_repos"],
                "followers": user["followers"],
                "since": int(user["created_at"][:4]),
                "stars": sum(r["stargazers_count"] for r in repos if not r["fork"]),
                "languages": sorted(langs.items(), key=lambda kv: (-kv[1], kv[0])),
                "synced": dt.date.today().strftime("%b %Y").upper(),
            }
            DATA.write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
            return stats
        except Exception as exc:  # network or rate limit: fall back to the last snapshot
            print(f"GitHub API unavailable ({exc}); using {DATA.name}")
    return json.loads(DATA.read_text(encoding="utf-8"))


# ── primitives ───────────────────────────────────────────────────────────────
def measure(s, cls, size, ls=0.0):
    f = TT[cls]
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(c), cmap[ord("?")])][0] for c in s) / upm * size + ls * len(s)


def fit(s, cls, width, start):
    size = start
    while measure(s, cls, size) > width:
        size -= 0.5
    return size


def text(x, y, s, cls="jb", size=14, fill=WHITE, ls=0, anchor="start", klass="", style="", attrs=""):
    USED[cls].update(s)
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    l = f' letter-spacing="{ls}"' if ls else ""
    st = f' style="{style}"' if style else ""
    classes = f"{cls} {klass}".strip()
    return f'<text class="{classes}" x="{x:g}" y="{y:g}" font-size="{size:g}" fill="{fill}"{l}{a}{st}{attrs}>{escape(s)}</text>'


def spans(x, y, parts, cls="jb", size=14, attrs=""):
    """One <text> with differently coloured runs: parts = [(string, colour), ...]."""
    USED[cls].update("".join(p for p, _ in parts))
    body = "".join(f'<tspan fill="{c}">{escape(p)}</tspan>' for p, c in parts)
    return f'<text class="{cls}" x="{x:g}" y="{y:g}" font-size="{size:g}" xml:space="preserve"{attrs}>{body}</text>'


def delay(s):
    return f"animation-delay:{s:.2f}s"


def rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


def on_dark(hex_color):
    """Brand colours that vanish on a dark panel are lifted toward white."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if lum >= 0.32:
        return f"#{h.lower()}"
    k = 0.62 if lum < 0.12 else 0.45
    return "#" + "".join(f"{round(c + (255 - c) * k):02x}" for c in (r, g, b))


def brand(slug, cx, cy, size, color=None):
    s = size / 24
    return f'<path transform="translate({cx - size / 2:g} {cy - size / 2:g}) scale({s:g})" d="{ICONS[slug]["path"]}" fill="{color or on_dark(ICONS[slug]["hex"])}"/>'


LINE_ICONS = {
    "layers": '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="m3 13 9 5 9-5"/><path d="m3 17.5 9 5 9-5"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "code": '<path d="m8 7-5 5 5 5"/><path d="m16 7 5 5-5 5"/><path d="m14 4-4 16"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "arrow": '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    "java": '<path d="M5 10h11v4a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5Z"/><path d="M16 11h1.5a2.5 2.5 0 0 1 0 5H15.5"/><path d="M3.5 21.5h14"/>'
            '<path class="steam" d="M8.5 2.5c-1.2 1.3 1.2 2.4 0 4"/><path class="steam" style="animation-delay:.6s" d="M12 2.5c-1.2 1.3 1.2 2.4 0 4"/>',
}


def line_icon(name, cx, cy, size, color, width=1.8):
    s = size / 24
    return (f'<g transform="translate({cx - size / 2:g} {cy - size / 2:g}) scale({s:g})" fill="none" stroke="{color}" '
            f'stroke-width="{width / s:g}" stroke-linecap="round" stroke-linejoin="round">{LINE_ICONS[name]}</g>')


def shuriken(cx, cy, scale, color, klass="spin", width=2, fill="none"):
    return (f'<g transform="translate({cx:g} {cy:g}) scale({scale:g})"><g class="{klass}">'
            f'<path d="M0-24 7-7 24 0 7 7 0 24-7 7-24 0-7-7Z" fill="{fill}" stroke="{color}" stroke-width="{width / scale:g}" stroke-linejoin="round"/>'
            f'<circle r="5" fill="none" stroke="{color}" stroke-width="{width / scale:g}"/></g></g>')


def label(x, y, s, color, anchor="start"):
    return text(x, y, s, "jbb", 12, color, 2.1, anchor)


def backdrop(region, size, panel_h, glow=None):
    """Panel background (plus an optional orange glow) as the area under `region` would show it."""
    x, y, w, h = region
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    top, bottom = (0x17, 0x1B, 0x28), (0x11, 0x14, 0x1D)
    for row in range(size[1]):
        t = (y + row * h / size[1]) / panel_h
        draw.line([(0, row), (size[0], row)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    if glow:
        gx, gy, gr, alpha = glow
        k = size[0] / w
        d = round(gr * 2 * k)
        mask = ImageChops.invert(Image.radial_gradient("L").resize((d, d))).point(lambda v: round(v * alpha))
        img.paste(Image.new("RGB", (d, d), (0xFF, 0x7A, 0x1A)), (round((gx - gr - x) * k), round((gy - gr - y) * k)), mask)
    return img


def photo(box, size, quality=82, under=None):
    """Crop the portrait; with `under`, its black backdrop is lifted to that image (a baked 'lighten')."""
    img = PHOTO.crop(box).resize(size, Image.LANCZOS)
    if under is not None:
        img = ImageChops.lighter(img, under)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def embers(points, color):
    return "".join(f'<circle class="ember" cx="{x}" cy="{y}" r="{r}" fill="{color}" opacity="0" style="{delay(d)};animation-duration:{t}s"/>'
                   for x, y, r, d, t in points)


# ── panel shell ──────────────────────────────────────────────────────────────
BASE_CSS = """
.fu{animation:fadeUp .7s cubic-bezier(.2,.8,.2,1) both}
.fi{animation:fadeIn .9s ease both}
.fl{animation:fadeL .7s cubic-bezier(.2,.8,.2,1) both}
.spin{transform-box:fill-box;transform-origin:center;animation:spin 28s linear infinite}
.spinr{transform-box:fill-box;transform-origin:center;animation:spin 40s linear infinite reverse}
.ember{animation:rise 6s ease-in infinite}
.blink{animation:bl 1.05s steps(1) infinite}
.pulse{animation:pulse 2.4s ease-in-out infinite}
.steam{animation:steam 2.4s ease-in-out infinite}
@keyframes steam{0%,100%{opacity:.25}50%{opacity:1}}
@keyframes fadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes fadeL{from{opacity:0;transform:translateX(-14px)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes rise{0%{opacity:0;transform:translateY(0)}20%{opacity:.85}100%{opacity:0;transform:translateY(-150px)}}
@keyframes bl{50%{opacity:0}}
@keyframes pulse{50%{opacity:.35}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def font_css():
    out = []
    for cls, (fname, weight, fallback) in FONTS.items():
        family = f"T{cls}"
        if USED[cls]:
            f = TTFont(VENDOR / "fonts" / fname, recalcTimestamp=False)
            opts = subset.Options()
            opts.flavor = "woff"
            opts.name_IDs = [1, 2]
            sub = subset.Subsetter(opts)
            sub.populate(text="".join(sorted(USED[cls])) + " ")
            sub.subset(f)
            buf = io.BytesIO()
            f.save(buf)
            data = base64.b64encode(buf.getvalue()).decode()
            out.append(f"@font-face{{font-family:'{family}';src:url(data:font/woff;base64,{data}) format('woff');font-weight:{weight}}}")
        out.append(f".{cls}{{font-family:'{family}',{fallback};font-weight:{weight}}}")
    return "\n".join(out)


def panel(name, w, h, title, desc, body, defs="", css="", edge=(ORANGE, BLUE)):
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">
<title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>
<defs><style>
{font_css()}
{BASE_CSS}{css}
</style>
<linearGradient id="pbg" x2="0" y2="1"><stop stop-color="#171b28"/><stop offset="1" stop-color="#11141d"/></linearGradient>
<linearGradient id="pedge" x2="1" y2="1"><stop stop-color="{edge[0]}" stop-opacity=".6"/><stop offset=".5" stop-color="{LINE}"/><stop offset="1" stop-color="{edge[1]}" stop-opacity=".5"/></linearGradient>
<pattern id="pdots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r=".9" fill="#fff" fill-opacity=".05"/></pattern>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="18"/></filter>
{defs}</defs>
<rect width="{w}" height="{h}" rx="24" fill="url(#pbg)"/><rect width="{w}" height="{h}" rx="24" fill="url(#pdots)"/>
{body}
<rect x=".75" y=".75" width="{w - 1.5}" height="{h - 1.5}" rx="23.25" fill="none" stroke="url(#pedge)" stroke-width="1.5"/>
</svg>
"""
    (OUT / name).write_text(svg, encoding="utf-8", newline="\n")
    for k in USED:
        USED[k].clear()
    print(f"  {name:<16} {len(svg.encode()) / 1024:7.1f} KB")


# ── 1 · hero ─────────────────────────────────────────────────────────────────
def build_hero(st):
    prompt = [("tharinda@rajarata", GREEN), (":~$ ", MUTED), ("summon", WHITE), (" --profile", ORANGE)]
    full = "".join(p for p, _ in prompt)
    widths = [measure(full[:i], "jb", 15) for i in range(len(full) + 1)]
    pad = 6  # frames of silence before typing starts
    vals = ";".join(f"{v:.1f}" for v in [0] * pad + widths)
    cur = ";".join(f"{52 + v + 3:.1f}" for v in [0] * pad + widths)
    dur = (pad + len(widths)) * 0.045

    spiral = " ".join(f"{'M' if i == 0 else 'L'}{250 + (8 + 11 * t) * math.cos(t):.1f} {330 + (8 + 11 * t) * math.sin(t):.1f}"
                      for i, t in enumerate(x / 10 for x in range(0, 173)))

    name = "Tharinda Pamindu"
    nsize = fit(name, "sg", 590, 66)
    roles = ["Full-Stack Developer", "Java Developer", "AI/ML Developer", "Competitive Programmer"]
    pills = [[("Rajarata University of Sri Lanka", ORANGE), ("3rd-year undergrad", BLUE)],
             [("Mihinthale, Sri Lanka", GREEN), (f"{st['public_repos']} repos · since {st['since']}", AMBER)]]

    b = f'<g class="spin" style="animation-duration:90s"><path d="{spiral}" fill="none" stroke="{ORANGE}" stroke-opacity=".07" stroke-width="22" stroke-linecap="round"/></g>'
    b += '<circle cx="230" cy="160" r="220" fill="url(#heat)"/>'
    # photo
    b += '<circle cx="950" cy="300" r="300" fill="url(#aura)"/>'
    img = photo((654, 0, 3146, 2160), (900, 780), under=backdrop((650, 20, 600, 520), (900, 780), 560))
    b += (f'<g class="fi" style="{delay(.25)};animation-duration:1.4s"><g mask="url(#pm)">'
          f'<image x="650" y="20" width="600" height="520" href="{img}" preserveAspectRatio="xMidYMid slice"/></g></g>')
    for x, y, dx, dy in [(728, 53, 1, 0), (1195, 53, -1, 0), (728, 473, 1, 0), (1195, 473, -1, 0)]:
        b += f'<path d="M{x} {y}h{12 * dx}" stroke="{ORANGE}" stroke-width="2" class="fi" style="{delay(1.2)}"/>'
    b += shuriken(1180, 96, .62, BLUE, "spin", 1.6)
    b += embers([(760, 520, 1.6, 0, 6), (840, 530, 1.2, 1.4, 7), (1010, 520, 1.8, 2.6, 6.5), (1120, 530, 1.3, .8, 7.5),
                 (930, 525, 1.1, 3.6, 6), (1190, 520, 1.5, 4.4, 7), (700, 520, 1.2, 5.1, 6.8)], AMBER)
    # terminal prompt with typing
    b += f'<clipPath id="typed"><rect x="50" y="44" height="28" width="{widths[-1]:.1f}"><animate attributeName="width" values="{vals}" dur="{dur:.2f}s" calcMode="discrete" fill="freeze"/></rect></clipPath>'
    b += f'<g clip-path="url(#typed)">{spans(52, 63, prompt, "jb", 15)}</g>'
    b += f'<rect class="blink" x="{52 + widths[-1] + 3:.1f}" y="50" width="8" height="16" rx="1" fill="{GREEN}"><animate attributeName="x" values="{cur}" dur="{dur:.2f}s" calcMode="discrete" fill="freeze"/></rect>'
    # greeting and name
    b += text(52, 142, "Hi, I’m", "sgm", 26, WHITE, klass="fu", style=delay(.8))
    b += f'<g class="fu" style="{delay(1)}">'
    b += text(50, 222, name, "sg", nsize, ORANGE, style="filter:url(#nameglow);opacity:.75")
    b += text(50, 222, name, "sg", nsize, "url(#nameg)") + "</g>"
    b += f'<rect class="draw" x="52" y="244" width="118" height="4" rx="2" fill="url(#bar)" style="{delay(1.35)}"/>'
    # cycling roles
    b += f'<path d="M54 296l9 6-9 6Z" fill="{ORANGE}" class="fi" style="{delay(1.4)}"/>'
    for i, r in enumerate(roles):
        b += text(74, 309, r, "jb", 21, WHITE, klass="role", style=delay(1.4 + 3 * i), attrs='' if i == 0 else ' opacity="0"')
    # pills
    for row, items in enumerate(pills):
        x = 52
        for j, (s, c) in enumerate(items):
            w = measure(s, "jb", 13) + 44
            y = 350 + row * 46
            b += (f'<g class="fu" style="{delay(1.7 + row * .15 + j * .08)}"><rect x="{x}" y="{y}" width="{w:.1f}" height="34" rx="17" fill="{CARD}" stroke="{LINE}"/>'
                  f'<circle cx="{x + 18}" cy="{y + 17}" r="4" fill="{c}"/>' + text(x + 30, y + 22, s, "jb", 13, "#c9cfdb") + "</g>")
            x += w + 10
    b += text(52, 500, "BUILD · LEARN · IMPROVE · REPEAT", "jbb", 12, ORANGE, 2.4, klass="fi", style=delay(2.2))

    defs = f"""<linearGradient id="nameg" x2="1"><stop stop-color="#ffd36b"/><stop offset=".45" stop-color="{AMBER}"/><stop offset="1" stop-color="#ff5a1f"/></linearGradient>
<linearGradient id="bar" x2="1"><stop stop-color="{ORANGE}"/><stop offset="1" stop-color="{BLUE}"/></linearGradient>
<filter id="nameglow" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="9"/></filter>
<radialGradient id="aura"><stop stop-color="{ORANGE}" stop-opacity=".2"/><stop offset="1" stop-color="{ORANGE}" stop-opacity="0"/></radialGradient>
<radialGradient id="heat"><stop stop-color="{ORANGE}" stop-opacity=".09"/><stop offset="1" stop-color="{ORANGE}" stop-opacity="0"/></radialGradient>
<linearGradient id="pmx" x2="1"><stop stop-opacity="0"/><stop offset=".22" stop-color="#fff"/><stop offset=".84" stop-color="#fff"/><stop offset="1" stop-opacity="0"/></linearGradient>
<linearGradient id="pmy" x2="0" y2="1"><stop stop-opacity="0"/><stop offset=".06" stop-color="#fff"/><stop offset=".8" stop-color="#fff"/><stop offset="1" stop-opacity="0"/></linearGradient>
<mask id="pmb" maskUnits="userSpaceOnUse" x="650" y="20" width="600" height="520"><rect x="650" y="20" width="600" height="520" fill="url(#pmy)"/></mask>
<mask id="pm" maskUnits="userSpaceOnUse" x="650" y="20" width="600" height="520"><rect x="650" y="20" width="600" height="520" fill="url(#pmx)" mask="url(#pmb)"/></mask>"""
    css = """
.role{animation:role 12s ease-in-out infinite both}
@keyframes role{0%{opacity:0;transform:translateY(8px)}4%,21%{opacity:1;transform:none}25%,100%{opacity:0;transform:translateY(-8px)}}
.draw{transform-box:fill-box;transform-origin:0 50%;animation:draw .9s cubic-bezier(.2,.8,.2,1) both}
@keyframes draw{from{transform:scaleX(0)}to{transform:none}}"""
    panel("hero.svg", 1280, 560, "Hi, I’m Tharinda Pamindu — Full-Stack Developer",
          "Animated hero: Tharinda's portrait beside his name, a typed terminal prompt, cycling roles (full-stack, Java, AI/ML, competitive programming) and where he studies.",
          b, defs, css)


# ── 2 · ninja way ────────────────────────────────────────────────────────────
def build_way(st):
    K, T, S, M, A, P, C = PURPLE, BLUE, GREEN, AMBER, ORANGE, "#d6dae4", MUTED
    code = [
        [("public class ", K), ("Tharinda ", T), ("extends ", K), ("Developer", T), (" {", C)],
        [("    String ", T), ("base  ", P), ("= ", C), ('"Rajarata University"', S), (";", C)],
        [("    String", T), ("[] ", C), ("stack ", P), ("= {", C), ('"Java"', S), (", ", C), ('"React"', S), (", ", C), ('"Python"', S), ("};", C)],
        [("    String ", T), ("motto ", P), ("= ", C), ('"Stand your ground."', S), (";", C)],
        [],
        [("    @Override", A)],
        [("    public void ", K), ("everyDay", M), ("() {", C)],
        [("        while ", K), ("(", C), ("curious", P), (") {", C)],
        [("            learn", M), ("();", C)],
        [("            build", M), ("();", C)],
        [("            improve", M), ("();", C)],
        [("        }", C)],
        [("    }", C)],
        [("}", C)],
    ]
    b = f'<rect x="60" y="70" width="460" height="400" rx="20" fill="{ORANGE}" opacity=".10" filter="url(#soft)"/>'
    b += f'<g class="fi" style="{delay(.1)}"><rect x="32" y="36" width="520" height="448" rx="16" fill="#0e1119" stroke="{LINE}"/>'
    b += f'<path d="M48 36h488a16 16 0 0 1 16 16v24H32V52a16 16 0 0 1 16-16Z" fill="#141925"/>'
    b += "".join(f'<circle cx="{x}" cy="56" r="5.5" fill="{c}"/>' for x, c in [(56, "#ff5f57"), (74, "#febc2e"), (92, "#28c840")])
    b += f'<rect x="114" y="42" width="140" height="34" rx="7" fill="#0e1119"/>' + line_icon("java", 132, 59, 15, "#f89820", 1.7)
    b += text(146, 63, "Tharinda.java", "jb", 12, WHITE) + text(500, 63, "~/rajarata", "jb", 11, DIM, anchor="end")
    b += f'<path d="M32 448h520v20a16 16 0 0 1-16 16H48a16 16 0 0 1-16-16Z" fill="#141925"/>'
    b += f'<circle cx="54" cy="466" r="3.5" fill="{GREEN}"/>' + text(64, 470, "main", "jb", 11, MUTED)
    b += text(536, 470, "Java · UTF-8 · Ln 14, Col 2", "jb", 11, DIM, anchor="end") + "</g>"
    for i, row in enumerate(code):
        y = 104 + i * 24
        b += f'<g class="fl" style="{delay(.35 + i * .09)}">' + text(70, y, str(i + 1), "jb", 12, "#3b4357", anchor="end")
        if row:
            b += spans(88, y, row, "jb", 13.5)
        b += "</g>"
    end = 88 + measure("}", "jb", 13.5)
    b += f'<rect class="blink" x="{end + 3:.1f}" y="{104 + 13 * 24 - 13}" width="7.5" height="16" fill="{ORANGE}"/>'
    b += shuriken(532, 40, .8, AMBER, "spin", 1.8, "#11141d")

    x0 = 600
    b += f'<g class="fu" style="{delay(.15)}">' + label(x0, 68, "// MY NINJA WAY", ORANGE)
    b += text(x0, 113, "Learn it — then build it", "sg", 34, WHITE)
    b += text(x0, 147, "Third-year undergrad who enjoys building practical software.", "sgm", 16, MUTED) + "</g>"
    rows = [
        ("layers", ORANGE, "Full-stack apps, end to end", "React and Next.js front ends on Spring Boot and Node.js services"),
        ("eye", BLUE, "AI that can see", "Computer vision and CNN models with OpenCV, TensorFlow and Keras"),
        ("bolt", AMBER, "Problem solving as a habit", "Competitive programming in C++ and Java, one contest at a time"),
    ]
    for i, (ic, c, t, d) in enumerate(rows):
        y = 180 + i * 76
        b += (f'<g class="fu" style="{delay(.45 + i * .15)}"><rect x="{x0}" y="{y}" width="42" height="42" rx="10" fill="{rgba(c, .12)}" stroke="{rgba(c, .38)}"/>'
              + line_icon(ic, x0 + 21, y + 21, 20, c) + text(x0 + 58, y + 17, t, "sgm", 17, WHITE) + text(x0 + 58, y + 37, d, "jb", 12.5, MUTED) + "</g>")
    langs = len(st["languages"])
    b += (f'<g class="fu" style="{delay(1)}"><rect x="{x0}" y="410" width="640" height="74" rx="14" fill="{rgba(ORANGE, .06)}" stroke="{rgba(ORANGE, .28)}"/>'
          f'<rect x="{x0}" y="410" width="4" height="74" rx="2" fill="{ORANGE}"/>'
          + text(x0 + 24, 442, "“Stand your ground. Keep coding, keep growing.”", "sgm", 18, WHITE)
          + text(x0 + 24, 466, f"NINDO · {st['public_repos']} REPOS · {langs} LANGUAGES · SINCE {st['since']}", "jb", 11, DIM, 1.6)
          + shuriken(1208, 447, .55, ORANGE, "spin", 1.6) + "</g>")
    panel("ninja-way.svg", 1280, 520, "My ninja way",
          "A Java editor window showing Tharinda's daily loop (learn, build, improve) beside three things he builds: full-stack apps, computer-vision AI, and competitive-programming solutions.",
          b, edge=(ORANGE, RED))


# ── 3 · jutsu arsenal ────────────────────────────────────────────────────────
def build_stack(st):
    chips = [
        [("openjdk", "Java", "#f89820"), ("python", "Python", None), ("javascript", "JavaScript", None), ("typescript", "TypeScript", None), ("cplusplus", "C++", None)],
        [("react", "React", None), ("nextdotjs", "Next.js", None), ("redux", "Redux", None), ("springboot", "Spring Boot", None), ("nodedotjs", "Node.js", None)],
        [("mysql", "MySQL", None), ("postgresql", "PostgreSQL", None), ("mongodb", "MongoDB", None), ("flutter", "Flutter", None), ("opencv", "OpenCV", None)],
        [("tensorflow", "TensorFlow", None), ("docker", "Docker", None), ("git", "Git", None), ("githubactions", "Actions", None), ("postman", "Postman", None)],
    ]
    extra = ["C", "Dart", "PHP", "HTML", "CSS", "Sass", "Bootstrap", "Hibernate", ".NET", "Keras", "Android Studio", "Anaconda",
             "Maven", "npm", "Bitbucket", "GitHub", "IntelliJ IDEA", "VS Code", "Visual Studio", "PyCharm", "CLion", "Rider"]
    core = sum(len(r) for r in chips)
    cx, cy = 215, 262

    b = '<g class="beam"><path d="M232 262 L1256 64 L1256 470 Z" fill="url(#beamG)"/>'
    b += '<path d="M232 262 L1256 140 L1256 390 Z" fill="url(#beamG)" opacity=".55" filter="url(#soft)"/></g>'
    b += f'<circle cx="{cx}" cy="{cy}" r="150" fill="url(#core)" opacity=".35"/>'
    b += f'<g class="spin" style="animation-duration:50s"><circle cx="{cx}" cy="{cy}" r="122" fill="none" stroke="{LINE}" stroke-width="1.5" stroke-dasharray="3 9"/></g>'
    b += f'<g class="spinr"><circle cx="{cx}" cy="{cy}" r="94" fill="none" stroke="{AMBER}" stroke-opacity=".35" stroke-dasharray="40 16"/></g>'
    orbit = [("#f89820", 0), ("#3776ab", 72), ("#f7df1e", 144), ("#61dafb", 216), (GREEN, 288)]
    b += (f'<g class="spin" style="animation-duration:16s">' + f'<circle cx="{cx}" cy="{cy}" r="94" fill="none"/>'
          + "".join(f'<circle cx="{cx + 94 * math.cos(math.radians(a)):.1f}" cy="{cy + 94 * math.sin(math.radians(a)):.1f}" r="5" fill="{c}" filter="url(#glow)"/>' for c, a in orbit) + "</g>")
    b += f'<circle cx="{cx}" cy="{cy}" r="64" fill="none" stroke="{ORANGE}" stroke-opacity=".45"/>'
    b += f'<circle cx="{cx}" cy="{cy}" r="56" fill="url(#core)" class="pulse"/>'
    b += shuriken(cx, cy, 1.25, "#fff6d8", "spin", 2.2, rgba(AMBER, .25))
    b += embers([(640, 300, 1.6, 0, 7), (820, 220, 1.2, 1.6, 7), (980, 330, 1.5, 3.1, 7), (720, 160, 1.1, 2.2, 7),
                 (1100, 260, 1.3, 4.4, 7), (560, 380, 1.4, 5.2, 7)], AMBER)
    b += text(cx, 452, "CHAKRA CORE", "jbb", 11, DIM, 2.4, "middle")

    b += f'<g class="fu" style="{delay(.15)}">' + label(462, 56, "// JUTSU ARSENAL", AMBER)
    b += text(1256, 56, f"{core} CORE · {core + len(extra)}+ IN THE SCROLL", "jb", 11, DIM, 2, "end")
    b += text(462, 99, "Tools I build with", "sg", 30, WHITE) + "</g>"
    for r, row in enumerate(chips):
        for c, (slug, name, color) in enumerate(row):
            x, y = 462 + c * 161, 128 + r * 66
            col = color or on_dark(ICONS[slug]["hex"])
            b += (f'<g class="chip" style="{delay(.35 + c * .12 + r * .06)}"><rect x="{x}" y="{y}" width="151" height="50" rx="10" fill="{rgba(col, .09)}" stroke="{rgba(col, .42)}"/>'
                  + (line_icon("java", x + 28, y + 25, 22, col, 1.8) if slug == "openjdk" else brand(slug, x + 28, y + 25, 22, col)) + text(x + 50, y + 30, name, "jb", 14, WHITE) + "</g>")
    # wrap the extras under the grid
    lines, cur, lead = [], "", "Also in the scroll  "
    for i, e in enumerate(extra):
        nxt = (cur + " · " if cur else "") + e
        if measure((lead if not lines else "") + nxt, "jb", 12) > 790:
            lines.append(cur)
            cur = e
        else:
            cur = nxt
    lines.append(cur)
    for i, ln in enumerate(lines):
        y = 420 + i * 24
        parts = ([(lead, AMBER)] if i == 0 else []) + [(ln, MUTED)]
        b += f'<g class="fu" style="{delay(1.2 + i * .1)}">' + spans(462, y, parts, "jb", 12) + "</g>"
    defs = f"""<linearGradient id="beamG" x2="1"><stop stop-color="#ffe9b0" stop-opacity=".6"/><stop offset=".2" stop-color="{AMBER}" stop-opacity=".2"/><stop offset="1" stop-color="{AMBER}" stop-opacity=".02"/></linearGradient>
<radialGradient id="core"><stop stop-color="#fff6d8" stop-opacity=".95"/><stop offset=".35" stop-color="{AMBER}" stop-opacity=".5"/><stop offset="1" stop-color="{AMBER}" stop-opacity="0"/></radialGradient>"""
    css = """
.chip{animation:pop .55s cubic-bezier(.2,.8,.3,1.25) both}
@keyframes pop{0%{opacity:0;transform:translateX(-18px) scale(.86)}70%{opacity:1;transform:translateX(2px) scale(1.03)}100%{opacity:1;transform:none}}
.chip{transform-box:fill-box;transform-origin:center}
.beam{animation:flick 4.5s ease-in-out infinite}
@keyframes flick{0%,100%{opacity:.55}18%{opacity:.8}30%{opacity:.45}52%{opacity:.85}70%{opacity:.6}}"""
    names = ", ".join(n for row in chips for _, n, _ in row)
    panel("jutsu-stack.svg", 1280, 500, "Jutsu arsenal — Tharinda's tech stack",
          f"A glowing chakra core casts a beam that reveals {core} technology chips: {names}; plus {', '.join(extra)}.",
          b, defs, css, edge=(AMBER, ORANGE))


# ── 4 · registration card + mission dashboard ────────────────────────────────
def build_id(st):
    b = f'<g class="drop"><g class="sway">'
    b += f'<rect x="186" y="-10" width="28" height="124" fill="url(#strap)"/>'
    b += text(0, 0, "RAJARATA · SHINOBI · TP · RAJARATA · SHINOBI", "jbb", 9, "#fff", 2, attrs=' opacity=".55" transform="translate(196 6) rotate(90)"')
    b += f'<rect x="178" y="100" width="44" height="22" rx="5" fill="url(#metal)"/><rect x="194" y="120" width="12" height="10" fill="#9aa3b5"/>'
    b += '<circle cx="200" cy="138" r="10" fill="none" stroke="#c3cad8" stroke-width="4"/>'
    b += '<rect x="58" y="164" width="300" height="440" rx="16" fill="#000" opacity=".45" filter="url(#soft)"/>'
    b += f'<rect x="46" y="150" width="308" height="440" rx="16" fill="url(#card)" stroke="url(#cardedge)" stroke-width="1.6"/>'
    b += f'<g clip-path="url(#cardclip)"><path d="M46 150h308v40H46Z" fill="{rgba(ORANGE, .1)}"/><rect class="foil" x="-180" y="120" width="120" height="520" fill="url(#foilg)" transform="rotate(18 200 370)"/></g>'
    b += f'<circle cx="70" cy="170" r="7" fill="none" stroke="{ORANGE}" stroke-width="2"/><path d="M70 170m-3 0a3 3 0 1 1 3 3" fill="none" stroke="{ORANGE}" stroke-width="1.6"/>'
    b += text(86, 174, "NINJA REGISTRATION", "jbb", 11, ORANGE, 2) + text(336, 174, "No. 0224", "jb", 10, MUTED, anchor="end")
    face = photo((1462, 80, 2337, 1130), (280, 336), 85)
    b += f'<clipPath id="faceclip"><rect x="130" y="206" width="140" height="168" rx="12"/></clipPath>'
    b += f'<image x="130" y="206" width="140" height="168" href="{face}" clip-path="url(#faceclip)" preserveAspectRatio="xMidYMid slice"/>'
    b += f'<rect x="130" y="206" width="140" height="168" rx="12" fill="none" stroke="{ORANGE}" stroke-width="2"/>'
    b += shuriken(90, 250, .5, AMBER, "spin", 1.5)
    b += (f'<g transform="rotate(-12 306 258)"><circle cx="306" cy="258" r="25" fill="none" stroke="{RED}" stroke-width="2" opacity=".85"/>'
          + text(306, 251, "YEAR", "jbb", 9, RED, 1.5, "middle") + text(306, 272, "3", "sg", 19, RED, anchor="middle") + "</g>")
    b += text(200, 410, "Tharinda Pamindu", "sg", fit("Tharinda Pamindu", "sg", 260, 25), WHITE, anchor="middle")
    b += text(200, 434, "FULL-STACK SHINOBI", "jbb", 11, ORANGE, 2, "middle")
    b += f'<path d="M70 450h260" stroke="{LINE}"/>'
    fields = [("VILLAGE", "Mihinthale, LK", 70, 468), ("BASE", "Rajarata Univ.", 210, 468),
              ("SQUAD", "CodeGenFam", 70, 504), ("SINCE", str(st["since"]), 210, 504)]
    for k, v, x, y in fields:
        b += text(x, y, k, "jb", 9, DIM, 1.5) + text(x, y + 16, v, "sgm", 13, WHITE)
    bits = "".join(f"{byte:08b}" for byte in hashlib.sha256(USER.encode()).digest())
    x = 70
    for i in range(0, 120, 2):
        w = 1 + int(bits[i]) + int(bits[i + 1])
        if x + w > 300:
            break
        b += f'<rect x="{x}" y="536" width="{w}" height="18" fill="#c3cad8" opacity=".8"/>'
        x += w + 1.6
    b += f'<circle cx="74" cy="571" r="3.5" fill="{GREEN}" class="pulse"/>' + text(84, 575, "ACTIVE DUTY", "jbb", 10, GREEN, 1.5)
    b += text(336, 575, f"@{USER}", "jb", 10, MUTED, anchor="end")
    b += "</g></g>"

    x0 = 420
    pill = f"SYNCED · {st['synced']}"
    pw = measure(pill, "jbb", 11, 1.5) + 40
    b += f'<g class="fu" style="{delay(.2)}">' + label(x0, 50, "// MISSION DASHBOARD", ORANGE) + text(x0, 92, "Stats from the field", "sg", 30, WHITE)
    b += (f'<rect x="{1240 - pw:.1f}" y="54" width="{pw:.1f}" height="26" rx="13" fill="{rgba(GREEN, .1)}" stroke="{rgba(GREEN, .45)}"/>'
          f'<circle cx="{1240 - pw + 16:.1f}" cy="67" r="3.5" fill="{GREEN}" class="pulse"/>' + text(1240 - pw + 26, 71, pill, "jbb", 11, GREEN, 1.5) + "</g>")
    tiles = [("folder", ORANGE, str(st["public_repos"]), "PUBLIC REPOS"), ("code", AMBER, str(len(st["languages"])), "LANGUAGES"),
             ("user", BLUE, str(st["followers"]), "FOLLOWERS"), ("calendar", GREEN, str(st["since"]), "ON GITHUB SINCE")]
    for i, (ic, c, n, k) in enumerate(tiles):
        x = x0 + i * 208
        b += (f'<g class="fu" style="{delay(.35 + i * .1)}"><rect x="{x}" y="134" width="194" height="94" rx="14" fill="{CARD}" stroke="{LINE}"/>'
              f'<rect x="{x + 18}" y="150" width="22" height="3" rx="1.5" fill="{c}"/>' + line_icon(ic, x + 166, 162, 20, c)
              + text(x + 18, 196, n, "sg", 32, WHITE) + text(x + 18, 215, k, "jb", 10, DIM, 1.8) + "</g>")
    top = st["languages"][:6]
    peak = top[0][1] if top else 1
    b += f'<g class="fu" style="{delay(.75)}"><rect x="{x0}" y="248" width="456" height="300" rx="14" fill="{CARD}" stroke="{LINE}"/>'
    b += text(x0 + 22, 280, "TOP LANGUAGES · REPOS", "jb", 11, MUTED, 2) + "</g>"
    for i, (lang, n) in enumerate(top):
        y = 318 + i * 34
        w = max(12, 206 * n / peak)
        b += (f'<g class="fu" style="{delay(.85 + i * .07)}">' + text(x0 + 22, y + 4, lang, "jb", 12.5, "#c9cfdb")
              + f'<rect x="600" y="{y - 6}" width="206" height="11" rx="5.5" fill="#232a3b"/>'
              + f'<rect class="grow" x="600" y="{y - 6}" width="{w:.1f}" height="11" rx="5.5" fill="url(#barg)" style="{delay(1 + i * .1)}"/>'
              + text(818, y + 4, str(n), "jbb", 12, WHITE) + "</g>")
    b += text(x0 + 22, 528, "primary language of each original repository", "jb", 10, DIM, klass="fi", style=delay(1.6))
    natures = [(ORANGE, "TAIJUTSU", "Java · Spring Boot · React"), (BLUE, "GENJUTSU", "Computer vision & CNNs"),
               (AMBER, "NINJUTSU", "C++ · competitive programming")]
    b += f'<g class="fu" style="{delay(.9)}"><rect x="896" y="248" width="344" height="300" rx="14" fill="{CARD}" stroke="{LINE}"/>'
    b += text(918, 280, "CHAKRA NATURE", "jb", 11, MUTED, 2)
    for i, (c, k, v) in enumerate(natures):
        y = 326 + i * 64
        b += f'<circle cx="922" cy="{y - 4}" r="4" fill="{c}"/>' + text(934, y, k, "jbb", 10, c, 1.6) + text(918, y + 24, v, "sgm", 15, WHITE)
    b += text(918, 528, "always training", "jb", 10, DIM) + "</g>"

    defs = f"""<linearGradient id="strap" x2="1"><stop stop-color="#b8242c"/><stop offset=".5" stop-color="#e2383f"/><stop offset="1" stop-color="#a31f27"/></linearGradient>
<linearGradient id="metal" x2="0" y2="1"><stop stop-color="#e3e7ef"/><stop offset="1" stop-color="#8b94a6"/></linearGradient>
<linearGradient id="card" x2=".4" y2="1"><stop stop-color="#20263a"/><stop offset=".6" stop-color="#161b28"/><stop offset="1" stop-color="#2a1b16"/></linearGradient>
<linearGradient id="cardedge" x2="1" y2="1"><stop stop-color="{ORANGE}"/><stop offset=".5" stop-color="#3a3140"/><stop offset="1" stop-color="{RED}"/></linearGradient>
<linearGradient id="foilg" x2="1"><stop stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#ffd9a8" stop-opacity=".14"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<linearGradient id="barg" x2="1"><stop stop-color="{AMBER}"/><stop offset="1" stop-color="{ORANGE}"/></linearGradient>
<clipPath id="cardclip"><rect x="46" y="150" width="308" height="440" rx="16"/></clipPath>"""
    css = """
.drop{animation:drop 1.1s cubic-bezier(.2,.9,.3,1.15) both}
@keyframes drop{from{transform:translateY(-90px);opacity:0}to{transform:none;opacity:1}}
.sway{transform-box:view-box;transform-origin:200px 0;animation:sway 6s ease-in-out 1.1s infinite}
@keyframes sway{0%,100%{transform:rotate(0)}25%{transform:rotate(1.4deg)}75%{transform:rotate(-1.4deg)}}
.foil{animation:foil 6s ease-in-out 1.4s infinite}
@keyframes foil{0%{transform:rotate(18deg) translateX(0)}60%,100%{transform:rotate(18deg) translateX(560px)}}
.foil{transform-box:view-box;transform-origin:200px 370px}
.grow{transform-box:fill-box;transform-origin:0 50%;animation:grow 1s cubic-bezier(.2,.8,.2,1) both}
@keyframes grow{from{transform:scaleX(0)}to{transform:none}}"""
    langs = ", ".join(f"{l} {n}" for l, n in top)
    panel("ninja-id.svg", 1280, 620, "Ninja registration card and mission dashboard",
          f"A swinging ID badge with Tharinda's photo (third year, Rajarata University) beside a dashboard: {st['public_repos']} public repos, "
          f"{len(st['languages'])} languages, {st['followers']} followers, on GitHub since {st['since']}. Top languages by repo: {langs}.",
          b, defs, css)


# ── 5 · join the squad ───────────────────────────────────────────────────────
def build_connect(st):
    art = photo((14, 0, 3826, 2160), (960, 544), 80)
    b = '<clipPath id="art"><rect x="32" y="64" width="600" height="340" rx="16"/></clipPath>'
    b += f'<g clip-path="url(#art)" class="fi" style="{delay(.1)}"><rect x="32" y="64" width="600" height="340" fill="#0b0d13"/>'
    b += '<circle cx="330" cy="150" r="200" fill="url(#sun)"/>'
    b += f'<image x="32" y="64" width="600" height="340" href="{art}" preserveAspectRatio="xMidYMid slice" style="mix-blend-mode:lighten"/>'
    b += '<rect x="32" y="64" width="600" height="340" fill="url(#vig)"/>'
    b += embers([(90, 404, 1.6, 0, 6), (180, 404, 1.2, 1.8, 7), (470, 404, 1.5, .9, 6.5), (560, 404, 1.3, 3.2, 7), (250, 404, 1.1, 4.2, 6)], ORANGE)
    b += "</g>"
    b += (f'<g transform="translate(130 222)"><g class="spin" style="animation-duration:18s" filter="url(#glow)" fill="none" stroke="#61dafb" stroke-width="2.4">'
          + "".join(f'<ellipse rx="52" ry="19" transform="rotate({a})"/>' for a in (0, 60, 120)) + '<circle r="7" fill="#61dafb" stroke="none"/></g></g>')
    b += f'<g class="float"><g filter="url(#glow)">' + line_icon("java", 528, 222, 84, "#f89820", 2.6) + "</g></g>"
    b += f'<rect x="32" y="64" width="600" height="340" rx="16" fill="none" stroke="{LINE}"/>'

    x0 = 680
    b += f'<g class="fu" style="{delay(.15)}">' + label(x0, 84, "// JOIN THE SQUAD", RED)
    b += text(x0, 126, "Let’s build something meaningful", "sg", fit("Let’s build something meaningful", "sg", 556, 30), WHITE) + "</g>"
    cards = [("github", "GitHub", USER, "#e8ebf2"), ("linkedin", "LinkedIn", "tharinda-wickramasinghe", None),
             ("instagram", "Instagram", "@thari_yaa__", None), ("blogger", "CodeGenFam", "codegenfam.blogspot.com", None),
             ("orcid", "ORCID", "0009-0008-7298-4498", None), ("buymeacoffee", "Buy Me a Coffee", "tharindapamindu", None)]
    for i, (slug, name, handle, color) in enumerate(cards):
        x, y = x0 + (i % 2) * 286, 152 + (i // 2) * 82
        c = color or on_dark(ICONS[slug]["hex"])
        b += (f'<g class="fu" style="{delay(.35 + i * .08)}"><rect x="{x}" y="{y}" width="272" height="70" rx="14" fill="{CARD}" stroke="{LINE}"/>'
              f'<rect x="{x + 14}" y="{y + 13}" width="44" height="44" rx="10" fill="{rgba(c, .14)}"/>' + brand(slug, x + 36, y + 35, 22, c)
              + text(x + 72, y + 31, name, "sgm", 16, WHITE) + text(x + 72, y + 51, handle, "jb", 11, MUTED)
              + f'<g class="nudge" style="{delay(i * .2)}">' + line_icon("arrow", x + 248, y + 35, 16, c, 2) + "</g></g>")
    b += (f'<g class="fi" style="{delay(1.1)}"><path d="M{x0 + 5} 427l5 5-5 5-5-5Z" fill="{ORANGE}"/>'
          + text(x0 + 18, 436, "Open to internships, collaborations and new chances to grow", "jb", 12, MUTED) + "</g>")
    defs = f"""<radialGradient id="sun"><stop stop-color="{RED}" stop-opacity=".55"/><stop offset=".6" stop-color="{ORANGE}" stop-opacity=".12"/><stop offset="1" stop-color="{ORANGE}" stop-opacity="0"/></radialGradient>
<linearGradient id="vig" x2="0" y2="1"><stop offset=".55" stop-color="#0b0d13" stop-opacity="0"/><stop offset="1" stop-color="#0b0d13" stop-opacity=".85"/></linearGradient>"""
    css = """
.float{animation:flt 5s ease-in-out infinite}
@keyframes flt{50%{transform:translateY(-8px)}}
.nudge{animation:nudge 2.6s ease-in-out infinite}
@keyframes nudge{0%,70%,100%{transform:none}85%{transform:translateX(4px)}}"""
    panel("connect.svg", 1280, 470, "Let’s connect with Tharinda Pamindu",
          "Tharinda's portrait between a glowing React atom and a Java cup, beside cards for GitHub, LinkedIn, Instagram, the CodeGenFam blog, ORCID and Buy Me a Coffee.",
          b, defs, css, edge=(RED, ORANGE))


# ── small spinning divider ───────────────────────────────────────────────────
def build_divider():
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="-60 -60 120 120" width="120" height="120" role="img" aria-label="Spinning shuriken divider">
<defs><linearGradient id="s" x2="1" y2="1"><stop stop-color="{AMBER}"/><stop offset="1" stop-color="{ORANGE}"/></linearGradient>
<style>.s{{animation:spin 2.4s linear infinite;transform-origin:0 0}}.t{{animation:spin 2.4s linear infinite;transform-origin:0 0;opacity:.25}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}</style></defs>
<circle r="46" fill="none" stroke="{ORANGE}" stroke-opacity=".25" stroke-dasharray="4 10"/>
<g class="s"><path d="M0-40 10-10 40 0 10 10 0 40-10 10-40 0-10-10Z" fill="url(#s)"/><circle r="7" fill="#11141d"/></g>
</svg>
"""
    (OUT / "shuriken.svg").write_text(svg, encoding="utf-8", newline="\n")
    print(f"  {'shuriken.svg':<16} {len(svg) / 1024:7.1f} KB")


if __name__ == "__main__":
    stats = load_stats("--offline" in sys.argv)
    OUT.mkdir(exist_ok=True)
    print("Building panels:")
    build_hero(stats)
    build_way(stats)
    build_stack(stats)
    build_id(stats)
    build_connect(stats)
    build_divider()
