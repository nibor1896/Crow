#!/usr/bin/env python3
"""The README's front image, both themes and two widths: docs/images/readme/crow-dark.svg (the
window's crow theme, for GitHub dark), crow-light.svg (GitHub light), and crow-mobile-dark.svg /
crow-mobile-light.svg, one column and larger type for phones (880 px scaled to a phone's width left
5-6 px text, robin 2026-09-25). README.md picks one through <picture>: prefers-color-scheme for the
theme, max-width for the phone.

Every figure in it is copied from docs/ (operating points, features, tools, images). The version
pill reads crow_core.VERSION and the tool count is len(crow_core.BUILTIN_TOOLS), so a release
re-runs this and commits the four files. TOOLS below must name every built-in tool, or this stops.
Fonts: GitHub's own stacks, nothing embedded. Usage:  python3 tools/readme_image.py"""
import os, pathlib, re, subprocess, sys
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "cli"
OUT = ROOT / "docs" / "images" / "readme"
sys.path.insert(0, str(CLI))
import crow_core  # noqa: E402  (the version and the tool list; the import has no side effects)
BUILTIN = [tool["function"]["name"] for tool in crow_core.BUILTIN_TOOLS]
NTOOLS = str(len(BUILTIN))

C = dict(page="#0b0e17", panel="#0e1220", raised="#131829", line="#1c2438", text="#e8eef8",
         soft="#cfdaea", faint="#9fb0c9", dim="#6d7b95", ok="#4ec98f", gold="#e5c04b",
         sub="#39c6d8", mark="#7eb0f8", bevel="#2c5bac", bad="#f0655a", skip="#b392f0",
         term="#080b13")
VARIANT = os.environ.get("VARIANT")  # dark = crow theme, light = GitHub light
MOBILE = os.environ.get("LAYOUT") == "mobile"
if VARIANT is None:  # one call writes all four files: this module draws into globals, so each is its own run
    for layout in ("desktop", "mobile"):
        for v in ("dark", "light"):
            subprocess.run([sys.executable, __file__], env={**os.environ, "VARIANT": v, "LAYOUT": layout}, check=True)
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
    # rough 20 px semibold advance per glyph: narrow, wide, else; len * 9.2 ran into "Images"
    lx = 74 + sum(6.5 if c in "iljtfrI ,.'" else 15 if c.isupper() or c in "mw" else 12 for c in title)
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


STATS = [("200k", "context, one slot"), ("40", "tok/s decode in Crow, 8k, Windows"), ("780", "tok/s prefill, 100k–175k"),
         ("512 / 10", "MoE experts, active"), (NTOOLS, "tools built in"), ("16", "subagents at once")]

FEATURES = [
 ("Memory", "two plain-text stores, per project and per person", "ok"),
 ("Skills", "procedures the model keeps and rewrites", "gold"),
 ("Goals", "a plan in the pinned head, it survives a restart", "sub"),
 ("Subagents", "delegate, subtasks, collect: up to 16 at once", "ok"),
 ("Browser panel", "tabs and an address bar, render_page for the model", "gold"),
 ("Vision", "read_image, a drop, a paste; Flash-Next and the 27B", "sub"),
 ("Images", "Qwen-Image 2.1 pictures, LTX-2.5 clips, local", "ok"),
 ("Lightbox", "folder, download, size in MB; on the phone too", "gold"),
 ("Session search", "SQLite FTS5 over every archived conversation", "sub"),
 ("MCP", "stdio and Streamable HTTP, OAuth, per-tool classes", "ok"),
 ("Remote models", "OpenRouter, Anthropic, OpenAI. Default: this machine", "gold"),
 ("Phone", "the window on a paired phone, LAN or Tailscale", "sub"),
 ("Voice", "dictation via faster-whisper, nothing written to disk", "ok"),
 ("Secrets", "a file with an ACL, not an inherited env variable", "gold"),
]

MODES = [("manual", C["text"], "asks before writing|and before executing"),
         ("allowedit", C["ok"], "asks before executing"),
         ("auto", C["gold"], "asks nothing"),
         ("yolo", C["bad"], "asks for nothing,|and means it")]

TOOLS = [
 ("Files", "read_file · write_file · append_file · edit_file"),
 ("", "list_dir · find_files · search_text"),
 ("Shell", "run_command · build_bundle"),
 ("Git", "git_status · git_diff · git_log · git_commit · git_push · github_connect"),
 ("Web", "web_search · fetch_url"),
 ("Browser", "render_page"),
 ("Vision", "read_image · judge"),
 ("Images", "generate_image · edit_image · animate_image"),
 ("Memory", "memory · skill · session_search"),
 ("Goals", "goal_set · goal_step"),
 ("Subagents", "delegate · subtasks · collect"),
]

_listed = [n.strip() for _, names in TOOLS for n in names.split("·")]
if sorted(_listed) != sorted(BUILTIN):
    sys.exit(f"readme_image: TOOLS is out of date; missing {sorted(set(BUILTIN) - set(_listed))}, "
             f"extra {sorted(set(_listed) - set(BUILTIN))}")

# Measured on Linux 2026-09-27, the Windows row 2026-09-28 (docs/reference/tools.md, "generate_image and edit_image"): 40 steps.
IMAGES = [("generate_image, warm", "2752×1536", "155.2 s"),
          ("generate_image, cold", "2752×1536", "175.3 s"),
          ("edit_image, 2 stages", "1 MP edit + full-size redraw", "105.7 + 55.3 s"),
          ("generate_image, Windows", "2752×1536", "218.1 s"),
          ("animate_image, 5 s clip", "1920×1088, Media Stack", "65.6 s")]
IMAGES_SUB = "Qwen-Image 2.1 beside crow-nest's 27B"
IMAGES_TEXT = ("In the chat an animated square in the theme's colours stands where the picture will be, "
               "then turns into it.")
IMAGES_NOTE = ("RTX 5090; pictures beside the 27B, 40 steps, 2026-09-27/28; the clip: median of 5, 2026-10-02. "
               "Source: docs/")

OPS = [("Default, Windows", "CNQ4.5-M NVFP4 container", "40‡", "crow-nest"),
       ("Default, Linux", "CNQ4.5-M NVFP4 container", "35.8*", "crow-nest"),
       ("Second, Windows", "Qwen3.8-Flash-Next UD-Q2_K_XL", "41.76", "llama.cpp"),
       ("Second, Linux", "Qwen3.8-Flash-Next UD-Q2_K_XL", "41.8", "llama.cpp"),
       ("Third", "Qwen3.8-27B UD-Q4_K_XL", "123.05", "llama.cpp"),
       ("Media Stack, Windows", "Qwen3.5-9B Q8_0 + Qwen-Image + LTX-2.5", "—", "llama.cpp")]
STATS_NOTE = "crow-nest CNQ4.5-M, RTX 5090, Windows 2026-10-06, after the PLE fix: decode in a live Crow session, prefill cold. Source: docs/operating-points.md"
OPS_NOTE = "‡ live Crow session at 8k, 2026-10-06. * at 122k context, 2026-09-24. — not measured. Dates and sources: docs/operating-points.md"
INTRO_LINES = (
    f"A local model at 200k context with {NTOOLS} tools and MCP, persistent memory, its own skills,",
    "a browser panel, eyes, and subagents it can send out while it keeps working.",
    "It makes and edits images beside crow-nest's 27B, on one 32 GB card.",
    "Runs on this machine, or on a provider you choose.")
INSTALL_TEXT = "One line, Windows or Linux. Preflight, download, a per-file sha256 against the release manifest. No root, no elevation. One window, Windows or Linux: CrowSetup from the release installs Crow, the crow-nest engine and the operating points you pick."


def desktop():
    global W, X0, X1
    W, X0, X1 = 880, 40, 840
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
    VERSION = crow_core.VERSION
    for label, acc in (("v" + VERSION, "mark"), ("MIT", "faint"), ("Windows · Linux · CUDA", "sub")):
        x = pill(x, 258, label, C[acc])

    # ---------------------------------------------------------------- intro text
    y = 364
    for i, line in enumerate(INTRO_LINES):
        t(W / 2, y + i * 24, line, 15.5, C["soft"], anchor="middle")

    # ---------------------------------------------------------------- stats
    y = 364 + len(INTRO_LINES) * 24 + 16
    for i, (v, l) in enumerate(STATS):
        sx, sy = X0 + (i % 3) * 270, y + (i // 3) * 86
        card(sx, sy, 260, 76, C["raised"], C["raised"])
        t(sx + 18, sy + 36, v, 26, C["text"], MONO, 600)
        t(sx + 18, sy + 59, l, 12.5, C["faint"])
    t(W / 2, y + 190, STATS_NOTE,
      11, C["dim"], anchor="middle")

    # ---------------------------------------------------------------- features
    y = section(y + 234, "Features", "ok")
    for i, (ti, d, acc) in enumerate(FEATURES):
        fx, fy = X0 + (i % 2) * 405, y + (i // 2) * 80
        card(fx, fy, 395, 70)
        o.append(f'<circle cx="{fx+22}" cy="{fy+26}" r="4" fill="{C[acc]}"/>')
        t(fx + 36, fy + 31, ti, 16, C["text"], weight=600)
        t(fx + 36, fy + 53, escape(d), 12.5, C["faint"])
    y += (len(FEATURES) + 1) // 2 * 80 + 20

    # ---------------------------------------------------------------- approvals
    y = section(y, "It asks before it writes, and before it runs.", "gold")
    card(X0, y, 800, 160)
    for i, (m, col, d) in enumerate(MODES):
        mx = X0 + 24 + i * 194
        pill(mx, y + 26, m, col)
        for k, part in enumerate(d.split("|")):
            t(mx, y + 74 + k * 18, part, 12.5, C["faint"])
    t(X0 + 24, y + 128, "git_push asks at every level. A path outside the working directory asks first.", 13, C["soft"])
    y += 200

    # ---------------------------------------------------------------- tools
    y = section(y, "Tools", "sub", NTOOLS + " built in, every MCP tool joins the same list")
    card(X0, y, 800, 24 + len(TOOLS) * 34)
    for i, (g, names) in enumerate(TOOLS):
        ry = y + 20 + i * 34
        if i and g:
            o.append(f'<line x1="{X0+20}" y1="{ry-12}" x2="{X1-20}" y2="{ry-12}" stroke="{C["line"]}" stroke-dasharray="2 4"/>')
        t(X0 + 24, ry + 10, g, 13.5, C["text"], weight=600)
        t(X0 + 140, ry + 10, escape(names), 13, C["sub"], MONO)
    y += 24 + len(TOOLS) * 34 + 40

    # ---------------------------------------------------------------- images
    y = section(y, "Images", "gold", IMAGES_SUB)
    card(X0, y, 800, 40 + len(IMAGES) * 44 + 74)
    for hx, h in ((64, "tool"), (290, "size"), (590, "wall clock")):
        t(hx, y + 26, h, 11.5, C["dim"], ls=1)
    for i, (a, m, d) in enumerate(IMAGES):
        ry = y + 40 + i * 44
        o.append(f'<line x1="{X0+20}" y1="{ry}" x2="{X1-20}" y2="{ry}" stroke="{C["line"]}"/>')
        t(64, ry + 28, a, 14, C["text"], MONO)
        t(290, ry + 28, m, 13, C["soft"])
        t(590, ry + 28, d, 15, C["gold"], MONO, 600)
    ny = y + 40 + len(IMAGES) * 44
    o.append(f'<line x1="{X0+20}" y1="{ny}" x2="{X1-20}" y2="{ny}" stroke="{C["line"]}"/>')
    t(X0 + 24, ny + 28, escape(IMAGES_TEXT), 13, C["soft"])
    t(X0 + 24, ny + 54, escape(IMAGES_NOTE), 11.5, C["dim"])
    y += 40 + len(IMAGES) * 44 + 74 + 40

    # ---------------------------------------------------------------- operating points
    y = section(y, "Operating points", "mark")
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
    t(X0 + 24, y + 40 + len(OPS) * 44 + 26, OPS_NOTE, 11.5, C["dim"])
    y += 40 + len(OPS) * 44 + 40 + 30

    # ---------------------------------------------------------------- install pointer
    y = section(y, "Install", "ok")
    card(X0, y, 800, 118, C["term"], C["bevel"], 12)
    t(X0 + 24, y + 38, "One line, Windows or Linux. Copy it right below this picture.", 16, C["text"], weight=600)
    t(X0 + 24, y + 66, "Preflight, download, a per-file sha256 against the release manifest. No root, no elevation.", 13, C["faint"])
    t(X0 + 24, y + 90, "One window, Windows or Linux: CrowSetup installs Crow, the engine and the operating points.", 13, C["faint"])
    t(X1 - 30, y + 66, "↓", 40, C["ok"], anchor="end")
    y += 158

    return y


def wrap(text, n):
    """Greedy word wrap at n characters."""
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > n:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + ([cur] if cur else [])


def mobile():
    """One column at 440 px: shown about 360 px wide on a phone, so 14 px type lands near 11-12 px."""
    global W, X0, X1
    W, X0, X1 = 440, 10, 430
    CW = X1 - X0
    VERSION = crow_core.VERSION

    def msection(y, title, acc):
        o.append(f'<rect x="{X0}" y="{y}" width="4" height="22" rx="2" fill="{C[acc]}"/>')
        t(X0 + 14, y + 17, escape(title), 19, C["text"], weight=600)
        return y + 38

    # hero
    y = 10
    card(X0, y, CW, 360, r=14)
    o.append(f'<g transform="translate({W/2 - 90:.0f} {y + 6}) scale(0.176)">{mark()}</g>')
    t(W / 2, y + 222, "CROW", 50, C["text"], weight=300, anchor="middle", ls=16)
    t(W / 2, y + 250, "AI AGENT", 12.5, C["faint"], anchor="middle", ls=5)
    o.append(f'<text x="{W/2}" y="{y + 288}" text-anchor="middle" font-family="{UI}" font-size="19" fill="{C["soft"]}">'
             f'An agent, not a chat box.<tspan fill="{C["mark"]}">▍<animate attributeName="opacity" values="1;1;0;0" '
             f'keyTimes="0;.5;.5;1" dur="1.1s" repeatCount="indefinite"/></tspan></text>')
    pills = (("v" + VERSION, "mark"), ("MIT", "faint"), ("Windows · Linux · CUDA", "sub"))
    tot = sum(22 + len(l) * 7.6 for l, _ in pills) + 10 * (len(pills) - 1)
    x = W / 2 - tot / 2
    for label, acc in pills:
        x = pill(x, y + 310, label, C[acc])
    y += 360 + 26

    # intro
    intro = " ".join(INTRO_LINES)
    for i, line in enumerate(wrap(intro, 46)):
        t(W / 2, y + i * 23, line, 16, C["soft"], anchor="middle")
    y += len(wrap(intro, 46)) * 23 + 14

    # stats, 2 x 3
    for i, (v, l) in enumerate(STATS):
        sx, sy = X0 + (i % 2) * 214, y + (i // 2) * 84
        card(sx, sy, 206, 76, C["raised"], C["raised"])
        t(sx + 16, sy + 36, v, 25, C["text"], MONO, 600)
        t(sx + 16, sy + 59, l, 13.5, C["faint"])
    y += 3 * 84 + 8
    for i, line in enumerate(wrap(STATS_NOTE, 62)):
        t(W / 2, y + i * 16, line, 11.5, C["dim"], anchor="middle")
    y += len(wrap(STATS_NOTE, 62)) * 16 + 30

    # features, one column
    y = msection(y, "Features", "ok")
    for i, (ti, d, acc) in enumerate(FEATURES):
        fy = y + i * 74
        card(X0, fy, CW, 66)
        o.append(f'<circle cx="{X0+20}" cy="{fy+25}" r="4.5" fill="{C[acc]}"/>')
        t(X0 + 34, fy + 30, ti, 17, C["text"], weight=600)
        t(X0 + 34, fy + 52, escape(d), 14, C["faint"])
    y += len(FEATURES) * 74 + 26

    # approvals, 2 x 2
    y = msection(y, "It asks before it writes,", "gold")
    t(X0 + 14, y - 2, "and before it runs.", 19, C["text"], weight=600)
    y += 14
    card(X0, y, CW, 232)
    for i, (m, col, d) in enumerate(MODES):
        mx, my = X0 + 18 + (i % 2) * 206, y + 20 + (i // 2) * 90
        pill(mx, my, m, col)
        for k, part in enumerate(d.split("|")):
            t(mx, my + 48 + k * 19, part, 14, C["faint"])
    for k, line in enumerate(wrap("git_push asks at every level. A path outside the working directory asks first.", 50)):
        t(X0 + 18, y + 200 + k * 19, line, 14, C["soft"])
    y += 232 + 30

    # tools
    y = msection(y, "Tools", "sub")
    t(X0 + 80, y - 21, NTOOLS + " built in, plus every MCP tool", 13, C["dim"])
    rows = []
    for g, names in TOOLS:
        parts = [n.strip() for n in names.split("·")]
        cur = ""
        first = True
        for n in parts:
            cand = (cur + " · " + n) if cur else n
            if len(cand) > 38 and cur:
                rows.append((g if first else "", cur)); first = False; cur = n
            else:
                cur = cand
        rows.append((g if first else "", cur))
    # group label on its own line above the names
    lines = []
    for g, names in rows:
        if g:
            lines.append(("g", g))
        lines.append(("n", names))
    h = 16 + sum(28 if k == "g" else 24 for k, _ in lines) + 12
    card(X0, y, CW, h)
    ly = y + 16
    for k, v in lines:
        if k == "g":
            if ly > y + 20:
                o.append(f'<line x1="{X0+16}" y1="{ly-2}" x2="{X1-16}" y2="{ly-2}" stroke="{C["line"]}" stroke-dasharray="2 4"/>')
            t(X0 + 18, ly + 20, v, 15, C["text"], weight=600); ly += 28
        else:
            t(X0 + 18, ly + 17, escape(v), 14, C["sub"], MONO); ly += 24
    y += h + 30

    # images, two lines per row
    y = msection(y, "Images", "gold")
    t(X0 + 94, y - 21, escape(IMAGES_SUB), 13, C["dim"])
    text = wrap(IMAGES_TEXT, 50)
    note = wrap(IMAGES_NOTE, 60)
    ih = 14 + len(IMAGES) * 62 + 10 + len(text) * 19 + 10 + len(note) * 16 + 12
    card(X0, y, CW, ih)
    for i, (a, m, d) in enumerate(IMAGES):
        ry = y + 14 + i * 62
        if i:
            o.append(f'<line x1="{X0+16}" y1="{ry}" x2="{X1-16}" y2="{ry}" stroke="{C["line"]}"/>')
        t(X0 + 18, ry + 26, a, 14, C["text"], MONO)
        t(X1 - 18, ry + 26, d, 15.5, C["gold"], MONO, 600, anchor="end")
        t(X0 + 18, ry + 49, m, 13.5, C["soft"])
    ny = y + 14 + len(IMAGES) * 62
    o.append(f'<line x1="{X0+16}" y1="{ny}" x2="{X1-16}" y2="{ny}" stroke="{C["line"]}"/>')
    for k, line in enumerate(text):
        t(X0 + 18, ny + 24 + k * 19, escape(line), 14, C["soft"])
    ny += 10 + len(text) * 19 + 10
    for k, line in enumerate(note):
        t(X0 + 18, ny + 12 + k * 16, escape(line), 11.5, C["dim"])
    y += ih + 30

    # operating points, two lines per row
    y = msection(y, "Operating points", "mark")
    card(X0, y, CW, 20 + len(OPS) * 62 + 64)
    for i, (a, m, d, e) in enumerate(OPS):
        ry = y + 14 + i * 62
        if i:
            o.append(f'<line x1="{X0+16}" y1="{ry}" x2="{X1-16}" y2="{ry}" stroke="{C["line"]}"/>')
        t(X0 + 18, ry + 26, a, 15.5, C["text"], weight=600 if i < 2 else 400)
        t(X1 - 18, ry + 26, d + " tok/s", 15.5, C["mark"] if i < 2 else C["soft"], MONO, 600, anchor="end")
        t(X0 + 18, ry + 49, m, 13, C["soft"], MONO)
        t(X1 - 18, ry + 49, e, 13.5, C["faint"], anchor="end")
    ny = y + 20 + len(OPS) * 62 + 6
    for k, line in enumerate(wrap(OPS_NOTE, 60)):
        t(X0 + 18, ny + k * 16, line, 11.5, C["dim"])
    y += 20 + len(OPS) * 62 + 64 + 30

    # install pointer
    y = msection(y, "Install", "ok")
    body = wrap(INSTALL_TEXT, 50)
    ih = 58 + len(body) * 20 + 14
    card(X0, y, CW, ih, C["term"], C["bevel"], 12)
    t(X0 + 18, y + 34, "Copy it right below this picture.", 17, C["text"], weight=600)
    for k, line in enumerate(body):
        t(X0 + 18, y + 62 + k * 20, line, 14, C["faint"])
    t(X1 - 20, y + 36, "↓", 30, C["ok"], anchor="end")
    y += ih + 12
    return y


y = mobile() if MOBILE else desktop()
H = y - 20


svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
       f'aria-label="Crow: an agent, not a chat box. Features, tools, images, operating points.">'
       '' + "".join(o) + "</svg>\n")
(OUT / ("crow-" + ("mobile-" if MOBILE else "") + VARIANT + ".svg")).write_text(svg)
