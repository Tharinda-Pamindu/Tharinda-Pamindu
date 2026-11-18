"""Rebuild the self-contained README artwork with Python's standard library."""
from base64 import b64encode
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)
ORANGE, BLUE, GREEN, WHITE, MUTED = "#ff963b", "#67c8ff", "#68deb2", "#eef2fa", "#a1acc2"

def text(x, y, value, size=18, color=WHITE, weight=400, mono=False):
    family = "Consolas,monospace" if mono else "Segoe UI,Arial,sans-serif"
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" font-family="{family}">{escape(value)}</text>'

def rect(x, y, w, h, fill="#141d2e", stroke="#2b354b", radius=16):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>'

def label(x, y, value, color=ORANGE):
    return text(x, y, value, 14, color, 600, True)

def star(x, y, scale=1):
    return f'<g transform="translate({x} {y}) scale({scale})"><g class="spin"><path d="M0-24 8-8 24 0 8 8 0 24-8 8-24 0-8-8Z" fill="none" stroke="{ORANGE}" stroke-width="2"/><circle r="5" fill="none" stroke="{ORANGE}" stroke-width="2"/></g></g>'

def panel(name, height, title, desc, body, extra=""):
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1280" height="{height}" viewBox="0 0 1280 {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc>
<defs>
<linearGradient id="bg" x2="1" y2="1"><stop stop-color="#172032"/><stop offset="1" stop-color="#0c111d"/></linearGradient>
<linearGradient id="edge" x2="1" y2="1"><stop stop-color="#ff963b" stop-opacity=".65"/><stop offset=".5" stop-color="#29344b"/><stop offset="1" stop-color="#67c8ff" stop-opacity=".55"/></linearGradient>
<radialGradient id="aura"><stop stop-color="#ff963b" stop-opacity=".18"/><stop offset="1" stop-color="#ff963b" stop-opacity="0"/></radialGradient>
<pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse"><circle cx="13" cy="13" r="1" fill="#8291b0" opacity=".12"/></pattern>
<style>
.spin{{animation:spin 24s linear infinite;transform-box:fill-box;transform-origin:center}}
.float{{animation:float 7s ease-in-out infinite}}
.pulse{{animation:pulse 3s ease-in-out infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes float{{50%{{transform:translateY(-6px)}}}}
@keyframes pulse{{50%{{opacity:.35}}}}
@media(prefers-reduced-motion:reduce){{.spin,.float,.pulse{{animation:none}}}}
</style>{extra}</defs>
<rect x="1" y="1" width="1278" height="{height-2}" rx="24" fill="url(#bg)"/>
<rect x="1" y="1" width="1278" height="{height-2}" rx="24" fill="url(#dots)"/>
{body}
<rect x="1" y="1" width="1278" height="{height-2}" rx="24" fill="none" stroke="url(#edge)" stroke-width="1.5"/>
</svg>'''
    (OUT / name).write_text(svg, encoding="utf-8")

# Embed the existing portrait unchanged: SVG image documents cannot load sibling images.
portrait = "data:image/png;base64," + b64encode((ROOT / "photo.png").read_bytes()).decode()
hero = label(52, 59, "tharinda@dev:~$ summon --profile", GREEN)
hero += text(52, 125, "Hi, I'm", 28)
hero += text(48, 202, "Tharinda", 72, ORANGE, 750)
hero += text(48, 280, "Pamindu.", 72, WHITE, 750)
hero += '<rect x="52" y="308" width="112" height="4" rx="2" fill="#ff963b"/>'
hero += text(52, 354, "Full-Stack Developer  /  Java Developer", 24, WHITE, 600)
hero += text(52, 391, "AI/ML enthusiast. Always a student.", 21, MUTED)
hero += text(52, 446, "Rajarata University of Sri Lanka", 20, MUTED)
hero += label(52, 501, "BUILD. LEARN. IMPROVE. REPEAT.")
hero += '<circle cx="1000" cy="260" r="260" fill="url(#aura)"/>'
hero += rect(778, 34, 448, 490, "#101725")
hero += f'<image x="778" y="38" width="448" height="482" xlink:href="{portrait}" preserveAspectRatio="xMidYMid slice" clip-path="url(#portrait)"/>'
hero += '<path d="M798 90V56h34M1206 90V56h-34M798 468v34h34M1206 468v34h-34" fill="none" stroke="#ff963b" stroke-width="2"/>'
hero += star(1192, 468, .65) + label(807, 488, "STAND YOUR GROUND", WHITE)
panel("hero.svg", 560, "Tharinda Pamindu — Full-Stack and Java Developer", "Tharinda's own portrait, with his full-stack, Java and AI/ML interests and university.", hero, '<clipPath id="portrait"><rect x="780" y="36" width="444" height="486" rx="16"/></clipPath>')

about = label(52, 56, "01 / MY NINJA WAY") + text(52, 103, "Keep learning. Keep building.", 34, WHITE, 700)
about += text(52, 138, "Turning curiosity into useful software, one project at a time.", 20, MUTED)
about += '<g class="float">' + rect(52, 185, 400, 252)
about += '<circle cx="76" cy="211" r="5" fill="#ff7c78"/><circle cx="94" cy="211" r="5" fill="#ffca68"/><circle cx="112" cy="211" r="5" fill="#68deb2"/>'
about += label(78, 260, "class Developer {", BLUE)
about += label(96, 297, 'mindset = "keep growing";', WHITE)
about += label(96, 334, 'focus = "build with purpose";', WHITE)
about += label(96, 371, "learn(); build(); repeat();", ORANGE)
about += label(78, 407, "}", BLUE) + '</g>'
for i, (title, line, color) in enumerate([
    ("Full-stack development", "React interfaces, Java services, and connected data.", ORANGE),
    ("AI / ML exploration", "Learning through computer vision and practical projects.", BLUE),
    ("Problem solving", "Competitive programming and continuous improvement.", GREEN),
]):
    y = 198 + i * 88
    about += rect(500, y, 728, 74) + label(520, y+43, f"0{i+1}", color)
    about += text(568, y+28, title, 22, WHITE, 650) + text(568, y+55, line, 18, MUTED)
panel("ninja-way.svg", 476, "My ninja way — learn, build and improve", "Full-stack development, AI/ML exploration and competitive programming.", about)

stack = label(52, 55, "02 / JUTSU ARSENAL") + text(52, 103, "The tools behind the work.", 34, WHITE, 700)
groups = [
    ("LANGUAGES", ["Java", "JavaScript", "Python", "C / C++", "Dart", "PHP"], ORANGE),
    ("WEB & UI", ["React", "Next.js", "Redux", "HTML / CSS", "Sass", "Bootstrap"], BLUE),
    ("BACKEND & DATA", ["Spring", "Hibernate", "Node.js", ".NET", "MySQL", "PostgreSQL", "MongoDB"], GREEN),
    ("MOBILE & ML", ["Flutter", "Android Studio", "Anaconda", "OpenCV"], "#c29bff"),
    ("TOOLS & WORKFLOW", ["Git / GitHub", "Docker", "GitHub Actions", "Maven / npm", "Postman", "Bitbucket", "Markdown"], ORANGE),
]
for i, (title, values, color) in enumerate(groups):
    y = 140 + i * 80
    stack += label(52, y+28, title, color)
    x = 282
    for value in values:
        width = max(88, len(value)*10+28)
        stack += rect(x, y, width, 46, "#182235", "#344159", 12) + text(x+14, y+29, value, 17)
        x += width+10
stack += text(52, 563, "IDEs: VS Code, Visual Studio, IntelliJ IDEA, Eclipse, WebStorm, PyCharm, PHPStorm, CLion, Rider", 18, MUTED)
panel("jutsu-stack.svg", 598, "Jutsu arsenal — Tharinda's technology stack", "Languages, web frameworks, backend and database tools, mobile development, machine learning tools and IDEs from the original profile.", stack)

identity = label(466, 58, "03 / DEVELOPER REGISTRATION") + text(466, 104, "The person behind the commits.", 34, WHITE, 700)
identity += '<g class="float">' + rect(52, 46, 356, 354)
identity += '<path d="M194 0v56h70V0" fill="none" stroke="#ff963b" stroke-width="18"/>'
identity += rect(178, 64, 104, 12, "#73829d", "#73829d", 6)
identity += '<circle cx="230" cy="170" r="60" fill="#242d40" stroke="#ff963b"/>'
identity += text(186, 187, "TP", 48, ORANGE, 750) + text(89, 276, "THARINDA PAMINDU", 25, WHITE, 700)
identity += label(89, 310, "@Tharinda-Pamindu", MUTED) + label(89, 365, "SRI LANKA", GREEN) + '</g>'
for i, (title, l1, l2) in enumerate([
    ("EDUCATION", "Third-year undergraduate", "Rajarata University of Sri Lanka"),
    ("SPECIAL INTERESTS", "Full-stack development & Java", "AI/ML & competitive programming"),
    ("PERSONAL MOTTO", "Stand your ground.", "Keep growing. Keep improving."),
]):
    y = 145+i*88
    identity += label(466, y, title, [ORANGE, BLUE, GREEN][i])
    identity += text(466, y+29, l1, 23, WHITE, 600) + text(466, y+55, l2, 19, MUTED)
identity += star(1185, 355, 1.2)
panel("ninja-id.svg", 438, "Tharinda Pamindu's developer registration", "Third-year undergraduate at Rajarata University of Sri Lanka. Full-stack and Java developer, AI/ML and competitive programming enthusiast.", identity)

connect = label(52, 55, "04 / JOIN THE SQUAD") + text(52, 112, "Let's build something meaningful.", 42, WHITE, 700)
connect += text(52, 157, "Connect, exchange ideas, and keep learning together.", 23, MUTED)
connect += label(52, 214, "CODE  /  COLLABORATE  /  GROW", GREEN)
connect += '<g transform="translate(1120 132)"><circle r="75" fill="none" stroke="#344159"/><circle r="55" fill="none" stroke="#67c8ff" stroke-dasharray="5 10"/>' + star(0, 0, 1.4) + '</g>'
panel("connect.svg", 258, "Let's connect with Tharinda Pamindu", "Connect, exchange ideas, and keep learning together.", connect)
print("Built 5 profile SVGs in assets/")
