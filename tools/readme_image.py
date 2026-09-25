#!/usr/bin/env python3
"""The README's front image, both themes: docs/images/readme/crow-dark.svg (the window's crow
theme, for GitHub dark) and crow-light.svg (the light theme, for GitHub light). README.md shows
the one that matches the viewer through <picture> and prefers-color-scheme.

Every figure in it is copied from docs/ (operating points, features, tools). The version pill
reads cli/crow.py's VERSION, so a release re-runs this and commits the two files.
Fonts: GitHub's own stacks, nothing embedded. Usage:  python3 tools/readme_image.py"""
import os, pathlib, re, subprocess, sys
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "cli"
OUT = ROOT / "docs" / "images" / "readme"

C = dict(page="#0b0e17", panel="#0e1220", raised="#131829", line="#1c2438", text="#e8eef8",
         soft="#cfdaea", faint="#9fb0c9", dim="#6d7b95", ok="#4ec98f", gold="#e5c04b",
         sub="#39c6d8", mark="#7eb0f8", bevel="#2c5bac", bad="#f0655a", skip="#b392f0",
         term="#080b13")
VARIANT = os.environ.get("VARIANT")  # dark = crow theme, light = GitHub light
if VARIANT is None:  # one call writes both files: this module draws into globals, so each theme is its own run
    for v in ("dark", "light"):
        subprocess.run([sys.executable, __file__], env={**os.environ, "VARIANT": v}, check=True)
    sys.exit(0)
C = dict(page="#ffffff", panel="#ffffff", raised="#f0f1f3", line="#e4e4e7", text="#0f1114",
         soft="#3f4550", faint="#6b7280", dim="#6b7280", ok="#12855a", gold="#8a6400",
         sub="#0e7a8a", mark="#2c5bac", bevel="#2c5bac", bad="#c0362b", skip="#6f42c1",
         term="#f6f8fa") if VARIANT == "light" else C
UI = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"  # GitHub's own stack
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"  # GitHub's code stack
W, X0, X1 = 880, 40, 840
o = []


def t(x, y, s, size=13, fill=C["faint"], font=UI, weight=400, anchor="start", ls=0):
    o.append(f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" '
             f'fill="{fill}" text-anchor="{anchor}" letter-spacing="{ls}">{s}</text>')


def card(x, y, w, h, fill=C["panel"], stroke=C["line"], r=10):
    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}"/>')


def section(y, title, acc, sub=""):
    o.append(f'<rect x="{X0}" y="{y}" width="4" height="22" rx="2" fill="{C[acc]}"/>')
    t(56, y + 17, title, 20, C["text"], weight=600)
    lx = 76 + len(title) * 9.2
    if sub:
        t(lx, y + 16, sub, 12.5, C["dim"])
        lx += len(sub) * 6.0 + 16
    o.append(f'<line x1="{lx:.0f}" y1="{y+11}" x2="{X1}" y2="{y+11}" stroke="{C["line"]}"/>')
    return y + 40


def pill(x, y, label, col, font=MONO, size=12.5, fill="none"):
    w = 22 + len(label) * 7.6
    o.append(f'<rect x="{x}" y="{y}" width="{w:.0f}" height="26" rx="13" fill="{fill}" stroke="{col}"/>')
    t(x + w / 2, y + 17.5, escape(label), size, col, font, anchor="middle")
    return x + w + 10


def mark():
    g = re.search(r"<g .*?</g>", (CLI / ("mark-on-light.svg" if VARIANT == "light" else "mark-on-dark.svg")).read_text(), re.S).group(0)
    return g.replace("#64faf2", C["mark"]).replace("#04837d", C["mark"])


# ---------------------------------------------------------------- hero
y = 32
card(X0, y, 800, 300, r=14)
o.append(f'<g transform="translate(70 62) scale(0.235)">{mark()}</g>')
t(340, 150, "CROW", 64, C["text"], weight=300, ls=22)
t(344, 182, "AI AGENT", 13, C["faint"], ls=5)
o.append(f'<text x="342" y="226" font-family="{UI}" font-size="20" fill="{C["soft"]}">An agent, not a chat box.'
         f'<tspan fill="{C["mark"]}">▍<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" '
         f'dur="1.1s" repeatCount="indefinite"/></tspan></text>')
x = 342
VERSION = re.search(r'^VERSION = "([^"]+)"', (CLI / "crow.py").read_text(), re.M).group(1)
for label, acc in (("v" + VERSION, "mark"), ("MIT", "faint"), ("Windows · Linux · CUDA", "sub")):
    x = pill(x, 258, label, C[acc])

# ---------------------------------------------------------------- intro text
y = 364
for i, line in enumerate((
        "A local model at 200k context with 28 tools and MCP, persistent memory, its own skills,",
        "a browser panel, eyes, and subagents it can send out while it keeps working.",
        "Runs on this machine, or on a provider you choose.")):
    t(W / 2, y + i * 24, line, 15.5, C["soft"], anchor="middle")

# ---------------------------------------------------------------- stats
y = 452
STATS = [("200k", "context, one slot"), ("45.1", "tok/s decode"), ("771", "tok/s prefill, 16k prompt"),
         ("512 / 10", "MoE experts, active"), ("28", "tools built in"), ("16", "subagents at once")]
for i, (v, l) in enumerate(STATS):
    sx, sy = X0 + (i % 3) * 270, y + (i // 3) * 86
    card(sx, sy, 260, 76, C["raised"], C["raised"])
    t(sx + 18, sy + 36, v, 26, C["text"], MONO, 600)
    t(sx + 18, sy + 59, l, 12.5, C["faint"])
t(W / 2, y + 190, "Decode and prefill: crow-nest v0.3.0, CNQ4.5-M NVFP4, one RTX 5090, Windows, 2026-09-13/14. Conditions: docs/operating-points.md",
  11, C["dim"], anchor="middle")

# ---------------------------------------------------------------- features
y = section(686, "Features", "ok")
FEATURES = [
 ("Memory", "two plain-text stores, per project and per person", "ok"),
 ("Skills", "procedures the model keeps and rewrites", "gold"),
 ("Goals", "a plan in the pinned head, it survives a restart", "sub"),
 ("Subagents", "delegate, subtasks, collect: up to 16 at once", "ok"),
 ("Browser panel", "tabs and an address bar, render_page for the model", "gold"),
 ("Vision", "read_image: a screenshot, a render, a diagram", "sub"),
 ("Session search", "SQLite FTS5 over every archived conversation", "ok"),
 ("MCP", "stdio and Streamable HTTP, OAuth, per-tool classes", "gold"),
 ("Remote models", "OpenRouter, Anthropic, OpenAI. Default: this machine", "sub"),
 ("Phone", "the window on a paired phone, LAN or Tailscale", "ok"),
 ("Voice", "dictation via faster-whisper, nothing written to disk", "gold"),
 ("Secrets", "a file with an ACL, not an inherited env variable", "sub"),
]
for i, (ti, d, acc) in enumerate(FEATURES):
    fx, fy = X0 + (i % 2) * 405, y + (i // 2) * 80
    card(fx, fy, 395, 70)
    o.append(f'<circle cx="{fx+22}" cy="{fy+26}" r="4" fill="{C[acc]}"/>')
    t(fx + 36, fy + 31, ti, 16, C["text"], weight=600)
    t(fx + 36, fy + 53, escape(d), 12.5, C["faint"])
y += 6 * 80 + 20

# ---------------------------------------------------------------- approvals
y = section(y, "It asks before it writes, and before it runs.", "gold")
card(X0, y, 800, 160)
MODES = [("manual", C["text"], "asks before writing|and before executing"),
         ("allowedit", C["ok"], "asks before executing"),
         ("auto", C["gold"], "asks nothing"),
         ("yolo", C["bad"], "asks for nothing,|and means it")]
for i, (m, col, d) in enumerate(MODES):
    mx = X0 + 24 + i * 194
    pill(mx, y + 26, m, col)
    for k, part in enumerate(d.split("|")):
        t(mx, y + 74 + k * 18, part, 12.5, C["faint"])
t(X0 + 24, y + 128, "git_push asks at every level. A path outside the working directory asks first.", 13, C["soft"])
y += 200

# ---------------------------------------------------------------- tools
y = section(y, "Tools", "sub", "28 built in, every MCP tool joins the same list")
TOOLS = [
 ("Files", "read_file · write_file · append_file · edit_file"),
 ("", "list_dir · find_files · search_text"),
 ("Shell", "run_command · build_bundle"),
 ("Git", "git_status · git_diff · git_log · git_commit · git_push · github_connect"),
 ("Web", "web_search · fetch_url"),
 ("Browser", "render_page"),
 ("Vision", "read_image · judge"),
 ("Memory", "memory · skill · session_search"),
 ("Goals", "goal_set · goal_step"),
 ("Subagents", "delegate · subtasks · collect"),
]
card(X0, y, 800, 24 + len(TOOLS) * 34)
for i, (g, names) in enumerate(TOOLS):
    ry = y + 20 + i * 34
    if i and g:
        o.append(f'<line x1="{X0+20}" y1="{ry-12}" x2="{X1-20}" y2="{ry-12}" stroke="{C["line"]}" stroke-dasharray="2 4"/>')
    t(X0 + 24, ry + 10, g, 13.5, C["text"], weight=600)
    t(X0 + 140, ry + 10, escape(names), 13, C["sub"], MONO)
y += 24 + len(TOOLS) * 34 + 40

# ---------------------------------------------------------------- operating points
y = section(y, "Operating points", "mark")
OPS = [("Default, Windows", "CNQ4.5-M NVFP4 container", "45.1", "crow-nest"),
       ("Default, Linux", "CNQ4.5-M NVFP4 container", "36.8*", "crow-nest"),
       ("Second, Windows", "Qwen3.8-Flash-Next UD-Q2_K_XL", "41.76", "llama.cpp"),
       ("Second, Linux", "Qwen3.8-Flash-Next UD-Q2_K_XL", "41.8", "llama.cpp"),
       ("Third", "Qwen3.8-27B UD-Q4_K_XL", "123.05", "llama.cpp")]
card(X0, y, 800, 40 + len(OPS) * 44 + 44)
for hx, h in ((64, "line"), (250, "model"), (590, "decode tok/s"), (720, "engine")):
    t(hx, y + 26, h, 11.5, C["dim"], ls=1)
for i, (a, m, d, e) in enumerate(OPS):
    ry = y + 40 + i * 44
    o.append(f'<line x1="{X0+20}" y1="{ry}" x2="{X1-20}" y2="{ry}" stroke="{C["line"]}"/>')
    t(64, ry + 28, a, 14, C["text"], weight=600 if i < 2 else 400)
    t(250, ry + 28, m, 13, C["soft"], MONO)
    t(590, ry + 28, d, 15, C["mark"] if i < 2 else C["soft"], MONO, 600)
    t(720, ry + 28, e, 13, C["faint"])
t(X0 + 24, y + 40 + len(OPS) * 44 + 26, "* at 16k context. crow-nest: Windows 2026-09-13/14, Linux 2026-09-17. llama.cpp: Windows 2026-09-01 (#182), Linux 2026-09-16.", 11.5, C["dim"])
y += 40 + len(OPS) * 44 + 40 + 30

# ---------------------------------------------------------------- install pointer
y = section(y, "Install", "ok")
card(X0, y, 800, 118, C["term"], C["bevel"], 12)
t(X0 + 24, y + 38, "One line, Windows or Linux. Copy it right below this picture.", 16, C["text"], weight=600)
t(X0 + 24, y + 66, "Preflight, download, a per-file sha256 against the release manifest. No root, no elevation.", 13, C["faint"])
t(X0 + 24, y + 90, "The default engine and its 104.7 GB container come from crow-nest; the steps are printed.", 13, C["faint"])
t(X1 - 30, y + 66, "↓", 40, C["ok"], anchor="end")
y += 158

H = y - 20


svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
       f'aria-label="Crow: an agent, not a chat box. Features, tools, operating points.">'
       '' + "".join(o) + "</svg>\n")
(OUT / ("crow-" + VARIANT + ".svg")).write_text(svg)
