#!/usr/bin/env python3
"""Render the window's page headless, with content in it (#381).

Nothing in the repo drew the window before this. The layout numbers in
docs/user-guide/window.md came from one-off scripts that were never checked in,
and the redesign (#380) needs a render it can repeat, on the desktop page and on
the phone's.

    python tools/render_window.py --fixture tools/fixtures/goal-run-2026-09-16.json \\
        --size 1440x960 --theme dark [--remote] [--click SEL]... [--focus SEL] \\
        [--type SEL=TEXT]... [--press KEY]... \\
        [--rects "#main,#bar,..."] --out runs/render/goal.png

HOW. `crow_gui.stamped_page(remote)` is the page, the same chain the window and
the phone get. It is written to a temp .html with two scripts added:

  head   `window.pywebview.api`, a Proxy whose methods resolve with the
         fixture's answers or null, so the page runs without Python. With
         --remote the phone's own bridge replaces it, so `fetch` and
         `EventSource` are stubbed there instead.
  tail   after the page's script: the fixture's messages go through
         `window.crow.on(...)` one by one, the way Python pushes them, then the
         --click and --focus steps, then --type (focus SEL, set its value, an
         `input` event) and --press (a keydown and keyup of KEY, e.g. ArrowDown,
         Enter, Escape, on whatever has the focus), then the --rects are
         measured.

The page sits in an iframe of exactly the requested size inside a second file.
Chrome's headless window is not the viewport -- on Windows 1440x960 gives a
1424x865 viewport to a --dump-dom run and has a minimum width of 500, which a
390 px phone page cannot live with -- and the screenshot run overrides it after
the page has loaded. An iframe has its size from the first layout, so the
screenshot and the measurement see the same page. The frame hands the numbers
to its parent with postMessage, because --dump-dom does not serialise an iframe.

THEME AND PANELS are Python's: `current_theme()` and `code_open()` read
settings.json, so `crow_gui.SETTINGS_FILE` is pointed at a temp file that holds
--theme and the fixture's `settings`. The render never reads or writes the real
one, and two machines stamp the same page.

The browser runs with virtual time (`--virtual-time-budget`), so timers,
transitions and the replay finish in the same order every time and two runs
print the same rects. stdout is the rects as one line of JSON; the PNG path, the
time and any page error go to stderr. A message the page threw on, a --click or
--focus that matched nothing, or a --rects selector the browser refused exits 1.

CROW_CHROME names the browser; otherwise Chrome, then Edge on Windows, and
google-chrome, chromium, microsoft-edge on Linux.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
THEMES = ("dark", "light", "crow")
DEFAULT_SIZE = "1440x960"

# VIRTUAL, not wall-clock: the budget is how much page time passes before the
# shot, and the browser spends it as fast as the page lets it. The replay waits
# SETTLE_MS (and two frames) after the messages and after every --click and
# --focus, for the .16 s panel transitions; the budget covers that and more.
VIRTUAL_BASE_MS = 4000
VIRTUAL_STEP_MS = 1000
SETTLE_MS = 400
BROWSER_TIMEOUT_S = 90


# -- the browser ----------------------------------------------------------------

def browser_candidates(environ=None, platform=None) -> list:
    """Where Chrome or Edge usually is, best first."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    out = []
    if platform.startswith("win"):
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            if environ.get(var):
                out.append(Path(environ[var]) / "Google" / "Chrome" / "Application" / "chrome.exe")
        for var in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            if environ.get(var):
                out.append(Path(environ[var]) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    return out


def find_browser(environ=None, platform=None, which=shutil.which) -> "str | None":
    """The browser to run, or None. CROW_CHROME wins and is never second-guessed:
    a path that does not exist is an error, not a reason to pick another."""
    environ = os.environ if environ is None else environ
    named = environ.get("CROW_CHROME")
    if named:
        if os.path.isfile(named):
            return named
        raise SystemExit("CROW_CHROME is set to %r, which is not a file" % named)
    for path in browser_candidates(environ, platform):
        if path.is_file():
            return str(path)
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "microsoft-edge", "microsoft-edge-stable"):
        found = which(name)
        if found:
            return found
    return None


# -- the arguments --------------------------------------------------------------

def parse_size(text: str) -> tuple:
    match = re.fullmatch(r"(\d{2,5})x(\d{2,5})", text.strip().lower())
    if not match:
        raise ValueError("size must look like 1440x960, not %r" % text)
    return int(match.group(1)), int(match.group(2))


def split_selectors(text: str) -> list:
    """`"#a,#b:is(x,y),[k='1,2']"` -> three selectors. A comma inside (), [] or
    quotes belongs to the selector."""
    out, depth, quote, cur = [], 0, "", ""
    for ch in text:
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def split_type(text: str) -> tuple:
    """`"#searchin=count"` -> ("#searchin", "count"). The split is at the first
    `=` outside (), [] and quotes, so `input[type=text]=x` keeps its selector."""
    depth, quote = 0, ""
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "=" and depth == 0 and text[:i].strip():
            return text[:i].strip(), text[i + 1:]
    raise ValueError("--type wants SEL=TEXT, not %r" % text)


def load_fixture(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    messages = doc.get("messages") if isinstance(doc, dict) else None
    if not isinstance(messages, list) or not all(
            isinstance(m, dict) and isinstance(m.get("k"), str) for m in messages):
        raise ValueError("%s: a fixture is an object whose `messages` is a list of "
                         "objects that each carry a `k`" % path)
    return doc


# -- the page -------------------------------------------------------------------

def stamp_page(remote: bool, theme: str, settings: dict) -> str:
    """`stamped_page(remote)` with the theme and panel state this render asks for.

    SETTINGS_FILE IS REBOUND, not written: the page reads `current_theme()`,
    `rail_open()` and `code_open()` from it, and the real file is the user's."""
    sys.path.insert(0, str(REPO / "cli"))
    import crow_gui
    tmp = tempfile.mkdtemp(prefix="crow-render-settings-")
    keep = crow_gui.SETTINGS_FILE
    try:
        crow_gui.SETTINGS_FILE = os.path.join(tmp, "settings.json")
        with open(crow_gui.SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(dict(settings, theme=theme), fh)
        return crow_gui.stamped_page(remote)
    finally:
        crow_gui.SETTINGS_FILE = keep
        shutil.rmtree(tmp, ignore_errors=True)


def js_json(value) -> str:
    """JSON that is safe inside a <script>: ASCII only, and no `</`."""
    return json.dumps(value, ensure_ascii=True).replace("</", "<\\/")


# The bridge the page expects. Every method resolves; the fixture's `api` map
# answers the ones whose return value the page reads, the rest answer null.
BRIDGE_JS = r"""
(function(){
  const ANSWERS = __ANSWERS__;
  const has = Object.prototype.hasOwnProperty;
  const answer = name => has.call(ANSWERS, name) ? ANSWERS[name] : null;
  // Collected from here, before the page's own script, so one that throws while
  // loading is seen too. The replay adds its own and hands the list over.
  window.__renderErrors = [];
  const note = (what, e) => { const text = e && e.message ? e.message : String(e);
    if (!/^ResizeObserver loop/.test(text)) window.__renderErrors.push(what + ": " + text); };
  window.addEventListener("error", ev => note("page error", ev.error || ev.message));
  window.addEventListener("unhandledrejection", ev => note("page rejection", ev.reason));
  window.__renderNote = note;
  window.pywebview = {api: new Proxy({}, {get: (_, name) =>
    (typeof name !== "string" || name === "then") ? undefined
      : () => Promise.resolve(answer(name))})};
  if (__REMOTE__) {
    // The phone page swaps the bridge above for POST /api/<name>; the same
    // answers come back from there. No stream: the replay is the stream.
    window.fetch = function(url){
      const m = /\/api\/([^/?#]+)/.exec(String(url));
      return Promise.resolve(new Response(JSON.stringify(m ? answer(m[1]) : null),
        {status: 200, headers: {"Content-Type": "application/json"}})); };
    window.EventSource = function(){ this.readyState = 1; this.close = function(){}; };
  }
})();
"""

# After the page's own script: replay, steps, measurement.
REPLAY_JS = r"""
(function(){
  const MESSAGES = __MESSAGES__, CLICKS = __CLICKS__, FOCUS = __FOCUS__,
        TYPES = __TYPES__, PRESSES = __PRESSES__, RECTS = __RECTS__, SETTLE = __SETTLE__;
  const out = {rects: {}, errors: []};
  const say = window.__renderNote;
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const frames = () => Promise.race([wait(100),
    new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))]);
  const settle = async () => { await frames(); await wait(SETTLE); await frames(); };
  const pick = (what, sel) => { try { const el = document.querySelector(sel);
      if (!el) say(what, "nothing matches " + sel); return el; }
    catch (e) { say(what + " " + sel, e); return null; } };
  const round = v => Math.round(v * 100) / 100;
  (async () => {
    try {
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      // pywebview fires this after it has injected the bridge; the phone page
      // fires it itself from crowRemoteStart.
      if (!window.CROW_REMOTE) window.dispatchEvent(new Event("pywebviewready"));
      MESSAGES.forEach((m, i) => { try { window.crow.on(m); }
        catch (e) { say("message " + i + " (" + m.k + ")", e); } });
      await settle();
      for (const sel of CLICKS) { const el = pick("click", sel);
        if (el) { try { el.click(); } catch (e) { say("click " + sel, e); } }
        await settle(); }
      if (FOCUS) { const el = pick("focus", FOCUS);
        if (el) { window.focus(); el.focus(); } await settle(); }
      for (const [sel, text] of TYPES) { const el = pick("type", sel);
        if (el) { window.focus(); el.focus(); el.value = text;
          el.dispatchEvent(new Event("input", {bubbles: true})); }
        await settle(); }
      for (const key of PRESSES) { const el = document.activeElement || document.body;
        for (const type of ["keydown", "keyup"])
          el.dispatchEvent(new KeyboardEvent(type, {key: key, bubbles: true, cancelable: true}));
        await settle(); }
      for (const sel of RECTS) { out.rects[sel] = null;
        try { const el = document.querySelector(sel);
          if (el) { const b = el.getBoundingClientRect();
            out.rects[sel] = {x: round(b.x), y: round(b.y), w: round(b.width), h: round(b.height)}; } }
        catch (e) { say("rects " + sel, e); } }
    } catch (e) { say("render", e); }
    out.errors = window.__renderErrors;
    parent.postMessage(JSON.stringify(out), "*");
  })();
})();
"""

FRAME_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>render_window</title></head>
<body style="margin:0;overflow:hidden;background:__BG__">
<iframe src="page.html" style="display:block;border:0;width:__W__px;height:__H__px"></iframe>
<pre id="__rects" hidden></pre>
<script>
window.addEventListener("message", ev => {
  if (typeof ev.data === "string") document.getElementById("__rects").textContent = ev.data; });
</script>
</body></html>
"""


def build_page(fixture: dict, remote: bool, theme: str, clicks=(), focus="", rects=(),
               types=(), presses=()) -> str:
    """The stamped page with the bridge in its head and the replay at its end."""
    page = stamp_page(remote, theme, fixture.get("settings") or {})
    bridge = (BRIDGE_JS.replace("__ANSWERS__", js_json(fixture.get("api") or {}))
                       .replace("__REMOTE__", "true" if remote else "false"))
    replay = (REPLAY_JS.replace("__MESSAGES__", js_json(fixture["messages"]))
                       .replace("__CLICKS__", js_json(list(clicks)))
                       .replace("__FOCUS__", js_json(focus or ""))
                       .replace("__TYPES__", js_json([list(t) for t in types]))
                       .replace("__PRESSES__", js_json(list(presses)))
                       .replace("__RECTS__", js_json(list(rects)))
                       .replace("__SETTLE__", str(SETTLE_MS)))
    if "<head>" not in page or "</body>" not in page:
        raise RuntimeError("stamped_page no longer has a <head> and a </body> to hook into")
    page = page.replace("<head>", "<head><script>" + bridge + "</script>", 1)
    end = page.rindex("</body>")
    return page[:end] + "<script>" + replay + "</script>" + page[end:]


def build_frame(size: tuple, theme: str) -> str:
    sys.path.insert(0, str(REPO / "cli"))
    import crow_gui
    return (FRAME_HTML.replace("__BG__", crow_gui.THEME_BG.get(theme, "#181818"))
                      .replace("__W__", str(size[0])).replace("__H__", str(size[1])))


# -- the browser run ------------------------------------------------------------

def virtual_budget(clicks=(), focus: str = "", types=(), presses=()) -> int:
    return VIRTUAL_BASE_MS + VIRTUAL_STEP_MS * (len(clicks) + (1 if focus else 0)
                                                + len(types) + len(presses))


def browser_args(browser: str, profile: str, size: tuple, url: str, budget: int,
                 *extra: str) -> list:
    # REDUCED MOTION, so a capture shows the end state: under virtual time a
    # CSS transition stays at its start (measured 2026-10-14 on the #382 rail
    # fold: the shut render reported the open widths).
    args = [browser, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1",
            "--force-prefers-reduced-motion",
            "--window-size=%d,%d" % size, "--user-data-dir=" + profile,
            "--no-first-run", "--no-default-browser-check", "--disable-extensions",
            "--disable-background-networking", "--disable-sync",
            "--virtual-time-budget=%d" % budget]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")          # Chrome refuses to start as root without it
    return args + list(extra) + [url]


def run_browser(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=BROWSER_TIMEOUT_S)


def png_size(path: str) -> "tuple | None":
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def read_result(dom: str) -> "dict | None":
    """The measurement the frame wrote into <pre id="__rects"> of a dumped DOM."""
    match = re.search(r'<pre id="__rects"[^>]*>(.*?)</pre>', dom, re.S)
    if not match or not match.group(1).strip():
        return None
    return json.loads(html.unescape(match.group(1)))


def remove_tree(path: str) -> None:
    """Chrome's helper processes outlive the main one by a moment, and on Windows
    a directory one of them still holds cannot be removed. Try for two seconds."""
    for _ in range(10):
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return
        time.sleep(0.2)


def render(fixture: dict, size: tuple, theme: str, remote: bool, clicks, focus: str,
           rects, out: str, browser: str, types=(), presses=()) -> dict:
    """Write `out` and return {"rects": {...}, "errors": [...]}."""
    work = tempfile.mkdtemp(prefix="crow-render-")
    try:
        with open(os.path.join(work, "page.html"), "w", encoding="utf-8") as fh:
            fh.write(build_page(fixture, remote, theme, clicks, focus, rects, types, presses))
        with open(os.path.join(work, "frame.html"), "w", encoding="utf-8") as fh:
            fh.write(build_frame(size, theme))
        url = Path(work, "frame.html").as_uri()
        profile = os.path.join(work, "profile")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        budget = virtual_budget(clicks, focus, types, presses)
        shot = run_browser(browser_args(browser, profile, size, url, budget,
                                        "--screenshot=" + os.path.abspath(out)))
        if png_size(out) is None:
            raise RuntimeError("the browser wrote no screenshot: "
                               + shot.stderr.decode("utf-8", "replace")[-400:])
        dump = run_browser(browser_args(browser, profile, size, url, budget, "--dump-dom"))
        result = read_result(dump.stdout.decode("utf-8", "replace"))
        if result is None:
            raise RuntimeError("the page never reported (no <pre id=\"__rects\"> in the "
                               "dumped DOM); the replay did not finish inside %d virtual ms"
                               % budget)
        return result
    finally:
        remove_tree(work)


# -- the command ----------------------------------------------------------------

def default_out(fixture_path: str, size: tuple, theme: str, remote: bool) -> str:
    stem = Path(fixture_path).stem
    return str(REPO / "runs" / "render" / "%s-%dx%d-%s%s.png"
               % (stem, size[0], size[1], theme, "-remote" if remote else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Render the window's page headless with a fixture's messages in it (#381).")
    ap.add_argument("--fixture", required=True, help="JSON: {messages: [...], settings, api}")
    ap.add_argument("--size", default=DEFAULT_SIZE, help="viewport, WxH (default %(default)s)")
    ap.add_argument("--theme", choices=THEMES, default="dark")
    ap.add_argument("--remote", action="store_true", help="the phone's page, not the window's")
    ap.add_argument("--click", action="append", default=[], metavar="SEL",
                    help="click the first element matching SEL (repeatable, in order)")
    ap.add_argument("--focus", default="", metavar="SEL", help="focus the first element matching SEL")
    ap.add_argument("--type", action="append", default=[], metavar="SEL=TEXT", dest="types",
                    help="focus the first element matching SEL and type TEXT into it (repeatable, in order)")
    ap.add_argument("--press", action="append", default=[], metavar="KEY", dest="presses",
                    help="press KEY (ArrowDown, Enter, Escape, ...) on the focused element (repeatable, in order)")
    ap.add_argument("--rects", default="", metavar="SEL,SEL",
                    help="print getBoundingClientRect of each as JSON {sel: {x,y,w,h} | null}")
    ap.add_argument("--out", default="", metavar="PNG",
                    help="screenshot path (default runs/render/<fixture>-<size>-<theme>.png)")
    args = ap.parse_args(argv)

    try:
        size = parse_size(args.size)
        fixture = load_fixture(args.fixture)
        types = [split_type(t) for t in args.types]
    except (ValueError, OSError) as err:
        print("render_window: %s" % err, file=sys.stderr)
        return 2
    browser = find_browser()
    if not browser:
        print("render_window: no Chrome, Edge or Chromium found; set CROW_CHROME to one",
              file=sys.stderr)
        return 2
    out = args.out or default_out(args.fixture, size, args.theme, args.remote)

    started = time.monotonic()
    try:
        result = render(fixture, size, args.theme, args.remote, args.click, args.focus,
                        split_selectors(args.rects), out, browser, types, args.presses)
    except (RuntimeError, subprocess.TimeoutExpired) as err:
        print("render_window: %s" % err, file=sys.stderr)
        return 1
    took = time.monotonic() - started

    print(json.dumps(result["rects"]))
    shot = png_size(out)
    print("render_window: %s %s in %.1f s (%s)" % (
        out, "%dx%d" % shot if shot else "?", took, os.path.basename(browser)), file=sys.stderr)
    if shot and shot != size:
        print("render_window: the screenshot is %dx%d, not the %dx%d asked for"
              % (shot + size), file=sys.stderr)
    for error in result["errors"]:
        print("render_window: " + error, file=sys.stderr)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
