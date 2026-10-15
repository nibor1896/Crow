#!/usr/bin/env python3
r"""The operating-point window: crow_boot.py's menu as a window (#196).

    python cli/crow_boot.py --gui        (what the shortcut runs, under pythonw.exe)
    python cli/crow_boot_gui.py          the same

THE DECISIONS, and why each is this way:

* A FACE, NOT A SECOND BOOT. Everything a point does -- the plan from
  manifests/stack.json, the one-at-a-time check, the spawn, the readiness wait,
  the contract file, Stop, Start Crow -- is crow_boot.Boot's, called as it is.
  The window adds two hooks Boot offers for it: `cancelled` (the Cancel button
  ends a start the way Ctrl+C ends it in the menu: what was started is stopped)
  and `on_stage` (which server is being waited for, so the Image Stack can say
  it is fetching the paint brushes). Boot's own text goes into a buffer; a
  failure shows its first line.
* THE CONTROLLER HOLDS THE STATE, THE PAGE ONLY DRAWS IT. `Controller.view()`
  is a plain dict with every word on the screen; cli/crow_boot_gui.html renders
  it and sends button presses back. So the four approved states (idle,
  starting, landed, a second start refused) are tested without a window. The
  selection and the vision switch are the controller's too; the page keeps
  only whether the list is open and which option the keys stand on.
* ONE PICKER, NOT A ROW PER POINT (#396): a select-only combobox (WAI-ARIA
  APG) with two groups -- the points of this platform, the installed
  llama.cpp lines -- the chosen entry's line under it, a Vision switch
  for a point with a no-vision variant (stack.json `variants`, #397), and one
  Start. It is drawn by the page, not a native <select>: WebView2 and
  WebKitGTK draw that popup each their own way and without the second line.
  The selection defaults to what runs, else the first entry.
* WHAT RUNS IS DETECTED ON OPEN AND EVERY REFRESH_S: Boot.detect (the contract
  file, the process scan with point_for_server, port 8099). A point started
  from the terminal or a window opened while one runs shows "Landed." at once.
* THE CROW FILLS AGAINST THE POINT'S USUAL START TIME (USUAL_START_S), capped
  at FILL_CAP until the server answers, then full.
* CLOSING WHILE A POINT STARTS hides the window and lets the start finish, so
  the contract file is still written: the bar says "You can close this window.
  The model keeps loading.", and that has to stay true.
* THE CROW ON THE TASKBAR: crow_gui's own icon code (`shell_buttons`, which
  hangs cli/crow.ico on the window; `icon_png` on Linux), under this window's
  own AppUserModelID, APP_ID, so it is not stacked with the chat window.
* THE PAGE GETS THE CROW INLINED (a data: URI): pywebview hands HTML to
  WebView2 and WebKitGTK without a base folder, so a relative file would not load.

pywebview is imported only when the window opens, so the controller and its
tests need nothing but the standard library and Crow's own modules.
"""

from __future__ import annotations

import base64
import io
import os
import re
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import crow_boot  # noqa: E402
import crow_core  # noqa: E402
import crow_platform  # noqa: E402

PAGE_FILE = os.path.join(HERE, "crow_boot_gui.html")
LOGO_FILE = os.path.join(HERE, "mark-on-dark.svg")
LOGO_LINE = "var LOGO = 'mark-on-dark.svg';"

# How long a point usually takes until it answers, for the crow's fill. Measured
# on the owner's RTX 5090 box: the 27B 9-13 s, the Image Stack 10 s and the 27B
# GGUF line 9-12 s from a hardlinked install layout (2026-10-01, CHANGELOG
# 3.0.0); Flash-Next's cold start ~83 s (2026-09-11, crow_boot.py BOOT_TIMEOUT_S).
# A line without a measurement fills against DEFAULT_USUAL_START_S, a guess.
# GLM-5.3-Flash (#365) is NOT MEASURED: it takes DEFAULT_USUAL_START_S.
# The Media Stack (#340) is NOT MEASURED yet: its 9B llama-server line takes the
# 27B GGUF line's figure, the nearest measured start.
USUAL_START_S = {"flash-next": 83.0, "27b": 15.0, "glm53-flash": 60.0, "image-stack": 15.0,
                 "media-stack": 15.0, "qwen35-q4-k-xl": 15.0}
DEFAULT_USUAL_START_S = 60.0
FILL_CAP = 95
REFRESH_S = 3.0
OPENED_S = 5.0

IDLE, STARTING, LANDED, REFUSED, STOPPING = "idle", "starting", "landed", "refused", "stopping"

# The picker's groups (#396).
POINTS_GROUP, OPTIONAL_GROUP = "Operating points", "Optional (llama.cpp)"

# THE TASKBAR IDENTITY. Without one a pythonw.exe window is Python's button
# with Python's icon (crow_gui.taskbar_identity says why). Its own id and not
# crow_gui's "Crow.Window": the chat window and this one are two windows the
# user switches between, and one id would stack them under one button.
APP_ID = "Crow.OperatingPoints"
TITLE = "Crow"
DRESS_S = 5.0


def gui_line(menu: dict) -> str:
    """A point's line in this window: stack.json's `menu.gui` (the approved
    window text, held by tools/check_stack.py), `menu.line` only without one.
    The terminal menu keeps `menu.line`."""
    return menu.get("gui") or menu.get("line") or ""


def short_title(title: str) -> str:
    """"Qwen3.8-Flash-Next" -> "Flash-Next": the family prefix off, for the refusal."""
    return re.sub(r"^Qwen[\d.]+-", "", title or "")


def usual_text(point_id: str) -> str:
    usual = USUAL_START_S.get(point_id)
    if usual is None:
        return "Loading the model."
    if usual <= 20:
        return "Loading the model. Usually ready in under 20 s."
    return "Loading the model. Usually ready in about %d s." % (round(usual / 10.0) * 10)


def _thread(fn, *args) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


class Controller:
    """The window's state over one crow_boot.Boot. Every outside effect is Boot's."""

    def __init__(self, boot: "crow_boot.Boot", clock=None, run=None):
        self.boot = boot
        self.clock = clock or time.monotonic
        self.run = run or _thread
        self._cancel = threading.Event()
        self._lock = threading.RLock()
        boot.out = io.StringIO()
        boot.style = crow_boot.Style()
        boot.cancelled = self._cancel.is_set
        boot.on_stage = self._stage
        self.phase = IDLE
        self.running = None
        self.starting = None
        self.refused = None
        self.note = None
        self.busy = False
        self.opened_at = None
        # #396: the picker's choice (None: what runs, else the first entry)
        # and the Vision switch, off = the point's no-vision variant.
        self.selected = None
        self.vision = True

    # -- what is on offer ---------------------------------------------------
    def points(self) -> list:
        """The baseline points that run here, then the installed optional lines.

        #340: a point for one platform (the Media Stack, Windows) is left out
        elsewhere, as in the terminal menu (crow_boot.runs_here).
        """
        out = []
        for p in self.boot.stack["points"]:
            if not crow_boot.runs_here(p):
                continue
            menu = p.get("menu") or {}
            out.append({"id": p.get("id"), "title": menu.get("title") or p.get("id"),
                        "detail": gui_line(menu), "optional": False})
        for line in self.boot.optional_lines():
            out.append({"id": line["key"], "title": "%s (optional)" % line["title"],
                        "detail": "llama.cpp, port %d" % line["port"], "optional": True,
                        "port": line["port"]})
        return out

    def _point(self, point_id):
        return next((p for p in self.points() if p["id"] == point_id), None)

    def _no_vision(self, point_id):
        """The point's no-vision variant from stack.json (#397), or None."""
        point = next((p for p in self.boot.stack["points"] if p.get("id") == point_id), None)
        return next((v for v in (point or {}).get("variants") or []
                     if v.get("vision") is False and v.get("key")), None)

    def _running_id(self, running) -> "str | None":
        """The entry that runs: a baseline point, or the llama.cpp line on its port."""
        if not running:
            return None
        if running.get("kind") == crow_platform.KIND_LLAMA:
            line = next((p for p in self.points() if p.get("port") == running.get("port")), None)
            return line["id"] if line else None
        return running.get("point")

    # -- the actions --------------------------------------------------------
    def refresh(self) -> None:
        """Ask Boot what runs. Not while a start or a stop is under way."""
        if self.busy:
            return
        running = self.boot.detect()
        with self._lock:
            if self.busy:
                return
            self.running = running
            if not running:
                self.phase, self.refused = IDLE, None
            elif self.phase != REFUSED:
                self.phase = LANDED

    def select(self, entry_id: str) -> None:
        """The picker's choice (#396). Not while a start or a stop is under way.

        A refusal names the entry it refused, so a new choice clears it.
        """
        if entry_id not in [e["id"] for e in self.entries()]:
            return
        with self._lock:
            if self.busy:
                return
            self.selected = entry_id
            if self.phase == REFUSED:
                self.phase, self.refused = LANDED if self.running else IDLE, None

    def set_vision(self, on) -> None:
        with self._lock:
            if not self.busy:
                self.vision = bool(on)

    def start(self, point_id: "str | None" = None) -> None:
        """Start a point, or without one the picker's entry (#396).

        Vision off starts the point's no-vision variant where it has one.
        """
        if point_id is None:
            point_id = self._chosen(self.entries(), self.running)
        with self._lock:
            if self.busy or self._point(point_id) is None:
                return
            self.busy = True
            self.selected = point_id
            variant = None if self.vision else (self._no_vision(point_id) or {}).get("key")
        running = self.boot.detect()
        with self._lock:
            if running:
                self.busy = False
                self.running, self.phase, self.refused = running, REFUSED, point_id
                return
            self._cancel.clear()
            self.note, self.refused = None, None
            self.phase = STARTING
            self.starting = {"id": point_id, "variant": variant, "began": self.clock(),
                             "stage": None}
        self.run(self._start, point_id, variant)

    def _stage(self, stage: str) -> None:
        with self._lock:
            if self.starting is not None:
                self.starting["stage"] = stage

    def _start(self, point_id: str, variant: "str | None" = None) -> None:
        self.boot.out = io.StringIO()
        try:
            # `variant=` only when one is chosen: a Boot before #397 has no such keyword
            code = (self.boot.start(point_id, variant=variant) if variant
                    else self.boot.start(point_id))
        except Exception as exc:              # noqa: BLE001 - the window says it
            code = crow_boot.EXIT_FAILED
            self.boot.say("x %s could not be started: %s" % (point_id, exc))
        said = self.boot.out.getvalue()
        running = self.boot.detect() if code in (crow_boot.EXIT_OK, crow_boot.EXIT_REFUSED) else None
        with self._lock:
            self.starting = None
            self.busy = False
            if code == crow_boot.EXIT_OK:
                self.running, self.phase = running or self.running, LANDED if running else IDLE
            elif code == crow_boot.EXIT_REFUSED:
                self.running, self.phase, self.refused = running, REFUSED if running else IDLE, point_id
            elif self._cancel.is_set():
                self.phase = IDLE
            else:
                self.phase, self.note = IDLE, self._failure(said)

    @staticmethod
    def _failure(said: str) -> dict:
        """Boot's failure in two lines: what happened, and where to read more."""
        rows = [r.strip() for r in said.splitlines() if r.strip()]
        head = next((r for r in rows if r.startswith(("x ", "! "))), rows[-1] if rows else "")
        head = re.sub(r"^[x!]\s+", "", head)
        logs = [r[len("Last lines of "):].rstrip(":") for r in rows if r.startswith("Last lines of ")]
        detail = ("The server log: %s" % logs[0]) if logs else ""
        if not logs and rows and rows[-1] != head and not rows[-1].startswith(("x ", "! ")):
            detail = rows[-1]
        return {"title": head, "detail": detail}

    def cancel(self) -> None:
        if self.phase == STARTING:
            self._cancel.set()

    def stop(self) -> None:
        with self._lock:
            if self.busy:
                return
            self.busy, self.phase, self.note = True, STOPPING, None
        self.run(self._stop)

    def _stop(self) -> None:
        self.boot.out = io.StringIO()
        try:
            code = self.boot.stop()
        except Exception as exc:              # noqa: BLE001
            code = crow_boot.EXIT_FAILED
            self.boot.say("x Stop failed: %s" % exc)
        said = self.boot.out.getvalue()
        running = self.boot.detect()
        with self._lock:
            self.busy = False
            self.running, self.refused = running, None
            self.phase = LANDED if running else IDLE
            if code != crow_boot.EXIT_OK:
                self.note = self._failure(said)

    def open_crow(self) -> None:
        """Start Crow, Boot's way: the window on what runs."""
        self.boot.out = io.StringIO()
        code = self.boot.start_crow()
        with self._lock:
            if code == crow_boot.EXIT_OK:
                self.opened_at, self.note = self.clock(), None
            else:
                self.note = self._failure(self.boot.out.getvalue())

    # -- what the page draws ------------------------------------------------
    def running_card(self, running: dict, stop: bool = True) -> dict:
        """The running point: its title and its port, context and vision line."""
        kind = running.get("kind")
        pids = running.get("pids") or {}
        if kind == crow_platform.KIND_IMAGE:
            return {"title": "Image server (sd-server)",
                    "detail": "Running without its language model, pid %s." % pids.get("image"),
                    "stop": stop}
        if kind == crow_platform.KIND_VIDEO:
            return {"title": "Video server (ComfyUI)",
                    "detail": "Running without its language model, pid %s." % pids.get("video"),
                    "stop": stop}
        m = re.search(r":(\d+)(?:/|$)", running.get("base_url") or "")
        port = int(m.group(1)) if m else (running.get("port") or crow_core.CROW_NEST_PORT)
        if kind == crow_platform.KIND_LLAMA:
            line = next((p for p in self.points() if p.get("port") == port), None)
            model = os.path.basename(running.get("model") or "") or "llama.cpp"
            return {"title": line["title"] if line else model,
                    "detail": "Running on port %s. llama.cpp." % port, "stop": stop}
        point = running.get("point")
        if not point:
            return {"title": "crow-nest",
                    "detail": "Running on port %s. Not identified yet, it may still be loading." % port,
                    "stop": stop}
        bits = []
        try:
            plan = crow_boot.plan_point(self.boot.stack, point, self.boot.install, self.boot.models)
        except crow_boot.SetupError:
            plan = None
        # #396: a variant runs ("text", #397's detect says so): vision off, and
        # its env and menu line over the point's own.
        off = bool(running.get("variant"))
        variant = self._no_vision(point) if off else None
        if plan:
            env = dict(plan["serve"]["env"])
            env.update((variant or {}).get("env") or {})
            for key in (variant or {}).get("env_unset") or []:
                env.pop(key, None)
            ctx = env.get("CROW_CONTEXT")
            if ctx and str(ctx).isdigit():
                bits.append("%dk context" % (int(ctx) // 1024))
            else:
                m = re.search(r"(\d+)k context", ((variant or {}).get("menu") or {}).get("line")
                              or plan["line"])
                if m:
                    bits.append("%sk context" % m.group(1))
            if off:
                bits.append("vision off")
            elif env.get("CROW_VIT_MMPROJ"):
                bits.append("vision on")
            if plan["image"]:
                bits.append("Qwen-Image on port %d" % plan["image"]["port"])
        detail = "Running on port %s." % port
        if bits:
            rest = ", ".join(bits)
            detail += " %s%s." % (rest[0].upper(), rest[1:])
        return {"title": self.boot.titles.get(point, point), "detail": detail, "stop": stop}

    def entries(self) -> list:
        """Everything the picker offers, in its order (#396): the points, then
        the installed llama.cpp lines."""
        return self.points()

    def _chosen(self, entries: list, running) -> "str | None":
        """The selection. None, or one the stack no longer offers, is what
        runs, else the first entry."""
        ids = [e["id"] for e in entries]
        for want in (self.selected, self._running_id(running)):
            if want in ids:
                return want
        return ids[0] if ids else None

    def _picker(self, entries: list, chosen, enabled: bool = True, detail=None,
                start: bool = True) -> dict:
        """The picker with `chosen` selected (#396).

        `detail` replaces the chosen entry's line (a start under way says how
        long it usually takes); `start` False greys Start (the entry runs). The
        Vision switch is shown for a point with a no-vision variant, and the
        line under the field is that variant's while it is off.
        """
        def item(e):
            return {"id": e["id"], "title": e["title"], "detail": e["detail"]}
        groups = [(POINTS_GROUP, [item(e) for e in entries if not e["optional"]]),
                  (OPTIONAL_GROUP, [item(e) for e in entries if e["optional"]])]
        with self._lock:
            vision = self.vision
        me = next((e for e in entries if e["id"] == chosen), None)
        variant = self._no_vision(chosen)
        line = me["detail"] if me else ""
        if variant and not vision:
            line = gui_line(variant.get("menu") or {}) or line
        button = {"label": "Start", "act": "start", "enabled": enabled and start}
        return {"groups": [{"label": label, "items": items} for label, items in groups if items],
                "selected": chosen, "detail": line if detail is None else detail,
                "vision": {"shown": variant is not None, "on": vision},
                "enabled": enabled, "start": button}

    def view(self) -> dict:
        with self._lock:
            phase, running, starting = self.phase, self.running, dict(self.starting or {})
            refused, note = self.refused, self.note
            opened = self.opened_at is not None and self.clock() - self.opened_at < OPENED_S
        entries = self.entries()
        view = {"phase": phase, "fill": None, "running": None, "warn": None, "note": note,
                "picker": None, "bar": None}
        open_btn = {"label": "Open Crow window", "act": "open_crow", "kind": "btn", "enabled": False}

        if phase == STARTING:
            began = starting.get("began", self.clock())
            elapsed = max(0.0, self.clock() - began)
            usual = USUAL_START_S.get(starting.get("id"), DEFAULT_USUAL_START_S)
            view["fill"] = int(min(FILL_CAP, 100.0 * elapsed / usual))
            view["say"] = "Flying to the nest. %d s" % int(elapsed)
            detail = usual_text(starting.get("id"))
            if starting.get("stage") == "sd-server":
                detail = "Fetching the paint brushes (Qwen-Image)."
            view["picker"] = self._picker(entries, starting.get("id"), enabled=False, detail=detail)
            view["bar"] = {"text": "You can close this window. The model keeps loading.",
                           "button": {"label": "Cancel", "act": "cancel", "kind": "chip", "enabled": True}}
            return view

        chosen = self._chosen(entries, running)
        if phase in (LANDED, REFUSED, STOPPING) and running:
            card = self.running_card(running, stop=phase != STOPPING)
            view["running"] = card
            can_open = running.get("kind") in (crow_platform.KIND_CROW_NEST, crow_platform.KIND_LLAMA) \
                and bool(running.get("base_url")) and phase != STOPPING
            if phase == STOPPING:
                text = "Stopping %s." % card["title"]
            elif not can_open:
                text = "Start a model, then open the Crow window."
            elif opened:
                text = "The Crow window is opening on %s." % card["title"]
            else:
                text = "The Crow window opens on %s." % card["title"]
            view["bar"] = {"text": text, "button": dict(open_btn, enabled=can_open)}
            if phase == REFUSED:
                view["say"] = "One model at a time."
                want = next((e for e in entries if e["id"] == refused), None)
                name = short_title(want["title"]) if want else refused
                view["warn"] = {"title": "%s needs the card for itself." % name,
                                "detail": "Stop %s first, then start %s." % (card["title"], name)}
            else:
                view["say"] = "Stopping." if phase == STOPPING else "Landed."
            view["picker"] = self._picker(entries, chosen, enabled=phase != STOPPING,
                                          start=chosen != self._running_id(running))
            return view

        view["say"] = "Which model should Crow fly with?"
        view["picker"] = self._picker(entries, chosen)
        view["bar"] = {"text": "Start a model, then open the Crow window.", "button": open_btn}
        return view


# ------------------------------------------------------------------ window ---

def page() -> str:
    """The page with the crow inlined as a data: URI."""
    with open(PAGE_FILE, encoding="utf-8") as fh:
        html = fh.read()
    try:
        with open(LOGO_FILE, "rb") as fh:
            logo = "data:image/svg+xml;base64," + base64.b64encode(fh.read()).decode("ascii")
    except OSError:
        logo = ""
    return html.replace(LOGO_LINE, "var LOGO = '%s';" % logo)


class Api:
    """What the page may call. Everything else is private: pywebview exposes
    every public attribute, nested objects included."""

    def __init__(self, controller: Controller):
        self._ctl = controller
        self._window = None
        self._closing = False
        self._maximised = False

    def view(self) -> dict:
        return self._ctl.view()

    def start(self, point_id=None) -> None:
        self._ctl.start(None if point_id is None else str(point_id))

    def select(self, entry_id) -> None:
        self._ctl.select(str(entry_id))

    def set_vision(self, on) -> None:
        self._ctl.set_vision(bool(on))

    def cancel(self) -> None:
        self._ctl.cancel()

    def stop(self) -> None:
        self._ctl.stop()

    def open_crow(self) -> None:
        self._ctl.open_crow()

    def minimise(self) -> None:
        self._window.minimize()

    def maximise(self) -> None:
        if self._maximised:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximised = not self._maximised

    def close(self) -> None:
        """Gone at once; while a point starts, hidden until it has landed."""
        if self._closing:
            return
        self._closing = True
        if not self._ctl.busy:
            self._window.destroy()
            return
        self._window.hide()

        def finish():
            while self._ctl.busy:
                time.sleep(0.25)
            self._window.destroy()
        _thread(finish)

    def _watch(self) -> None:
        while not self._closing:
            time.sleep(REFRESH_S)
            try:
                self._ctl.refresh()
            except Exception:                 # noqa: BLE001 - the next turn tries again
                pass


def _log_failure(boot) -> None:
    """pythonw.exe has no console: a window that cannot open leaves a note."""
    try:
        with open(os.path.join(boot.log_dir(), "crow-boot-gui.log"), "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
    except OSError:
        pass


def taskbar_identity(shell32=None) -> bool:
    """APP_ID for this process, before the window exists (the shell reads it
    when it registers the button). Windows only; a test hands in `shell32`."""
    if shell32 is None:
        if not crow_platform.IS_WINDOWS:
            return False
        try:
            import ctypes
            shell32 = ctypes.windll.shell32
        except Exception:                     # noqa: BLE001 - cosmetic, never fatal
            return False
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        return True
    except Exception:                         # noqa: BLE001
        return False


def start_kwargs(gui) -> dict:
    """What `webview.start` gets. Linux: GTK and the crow PNG (crow_gui.icon_png;
    pywebview's `icon=` is GTK/Qt only). Windows: nothing, the icon goes on the
    window itself (`dress_window`)."""
    if crow_platform.IS_WINDOWS:
        return {}
    return {"gui": "gtk", "icon": gui.icon_png(256) or None}


def dress_window(gui, sleep=time.sleep, clock=time.monotonic) -> bool:
    """crow_gui.shell_buttons on this window: crow.ico on the caption and the
    taskbar, and the minimise style a frameless window lacks. Retried, because
    at first the window has no caption to be found by (crow_gui does the same)."""
    if not crow_platform.IS_WINDOWS:
        return False
    deadline = clock() + DRESS_S
    while clock() < deadline:
        if gui.shell_buttons(TITLE):
            return True
        sleep(0.2)
    return False


def open_window(boot: "crow_boot.Boot") -> int:
    """`crow_boot.py --gui`: the window over this Boot, until it is closed.

    The crow on the taskbar and the caption is crow_gui's own code (icon files,
    `shell_buttons`), imported here and not copied; only the id is this window's.
    """
    try:
        crow_platform.webview_without_gpu()   # #368: open while the model decodes
        import webview
        import crow_gui
        ctl = Controller(boot)
        ctl.refresh()
        api = Api(ctl)
        taskbar_identity()
        window = webview.create_window(
            TITLE, html=page(), js_api=api, width=620, height=660, min_size=(520, 560),
            frameless=True, easy_drag=False, background_color="#181818")
        api._window = window
        _thread(api._watch)
        webview.start(dress_window, (crow_gui,), **start_kwargs(crow_gui))
    except Exception:                         # noqa: BLE001 - said in the log
        _log_failure(boot)
        return crow_boot.EXIT_FAILED
    return crow_boot.EXIT_OK


def main(argv=None) -> int:
    return crow_boot.main(["--gui"] + list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
