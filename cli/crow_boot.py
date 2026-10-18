#!/usr/bin/env python3
r"""The boot menu: start one of the three operating points, then open Crow.

#196 phase 1. One terminal menu that starts crow-nest's serve (and, for the
Image Stack, sd-server beside it), waits until it answers, writes the contract
file the window reads (`crow_core.write_active_point`) and opens the window
against it. Run it bare for the menu; the flags below do the same steps without
a menu, for a script or a test.

    python cli/crow_boot.py                       the menu
    python cli/crow_boot.py --status              what runs (exit 0), or nothing (exit 1)
    python cli/crow_boot.py --start 27b           start one point (flash-next, 27b, image-stack)
    python cli/crow_boot.py --start 27b --variant text
                                                  the same point without its vision tower (#397)
    python cli/crow_boot.py --stop                stop the running point
    python cli/crow_boot.py --start-crow          open the window against the running point
    python cli/crow_boot.py --start-claude        open the window on the Claude subscription (#398)
    python cli/crow_boot.py --gui                 the operating-point window (crow_boot_gui.py)
    python cli/crow_boot.py --create-shortcut DIR a Windows shortcut to that window in DIR
                                                  (add --terminal for one to this menu)
    python cli/crow_boot.py --plan 27b --json     what --start 27b would use, as JSON (the
                                                  installer's check step reads it)

Exit codes: 0 done, 1 failed (or, for --status, nothing runs), 2 setup error
(no stack.json, unknown point or variant, no engine binary), 3 refused because
another point already runs.

THE DECISIONS, and why each is this way:

* EVERYTHING ABOUT A POINT COMES FROM manifests/stack.json: binary, env, argv,
  cwd, dirs, port, readiness probe, identity, menu text, the image server's
  argv and its platform argv, and the window's `crow_env`. Nothing here names
  a model file. `${INSTALL}` is Crow's install root
  (`crow_platform.install_dir()`, `--install-root` overrides) and `${MODELS}`
  is `crow_platform.models_dir(install)` -- `$CROW_MODELS`, else
  `<install>/models` (`--models` overrides). A value that held a placeholder
  is a path and is normalised for the platform; any other value (`te=cpu`,
  `8099`) is passed as written. stack.json is looked up beside cli/ at
  `../manifests/stack.json` (`--stack` overrides).
* THE ENGINE ENV IS THE STACK'S, NOT THE SHELL'S: every key any point declares
  (its variants' included, #397) is dropped from the inherited environment
  before the chosen point's own are set, so a `CROW_HOTSETS` left over from
  Flash-Next cannot reach the 27B, nor a shell's `CROW_VIT=0` a base start.
* A VARIANT IS THE SAME POINT WITH ANOTHER ENV (#397): stack.json `variants`,
  today `text` on Flash-Next and the 27B (`CROW_VIT=0`, no `CROW_VIT_MMPROJ`;
  the 27B keeps its base's 131,072). `plan_point(..., variant=)` takes the base env minus the
  variant's `env_unset` plus its `env`, its menu line and gui text, and
  `identity.vision` from its `vision`; the title stays the base's. It installs
  nothing: the projector stays for the base point. The menu lists each variant
  on its own numbered line under its base, `--start <point> --variant <key>`
  starts one, the contract file carries `variant` (a base start writes none),
  and a scanned serve that says /props `modalities.vision` false is the
  point's variant with `vision: false` (`crow_core.server_vision`). A base
  start is what it was before variants existed.
* DETACHED: `crow_platform.spawn_kwargs(detached=True)` (Windows:
  CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW, #158 -- a Ctrl+C in this menu or
  closing its console does not reach the server), plus
  CREATE_BREAKAWAY_FROM_JOB so a terminal that kills its job on close does not
  take the server along; where the job forbids breakaway, the start is retried
  without it. stdin is DEVNULL, stdout and stderr go to
  `<log dir>/serve-<port>.log` and `sd-server-<port>.log`, with the previous
  run kept as `.prev.log` (`crow_core._keep_previous_log`). The log dir is
  `crow_platform.log_dir()` (Windows: `runs\` under the current folder -- the
  shortcut starts the menu in the install root; if that folder cannot be
  created, `<install>/runs`).
* LINUX (#341): serve and sd-server start behind
  `crow_platform.server_scope_prefix()` -- the user scope with the memory
  bounds the llama.cpp lines get; empty on Windows. `systemd-run --scope`
  execs the server, so the Popen pid IS the server's pid, the one the scan,
  Stop and `terminate_tree` address. Their LD_LIBRARY_PATH gets stack.json's
  `lib_path` for this platform in front (Linux: `<install>/bin` for the
  NVRTC beside serve, `<install>/cuda/lib` for sd-server's CUDA runtime);
  Windows has none and its env is left as it was.
* READINESS is the stack's probe: serve `GET /health` == `{"status": "ok"}`
  (it answers only once fully loaded), sd-server `GET /sdcpp/v1/capabilities`
  == 200; a 5xx from sd-server is final (#324), a 5xx from serve is waited
  out. Timeouts: Flash-Next 600 s (measured cold start ~83 s, 2026-09-11),
  the 27B and the Image Stack's serve 300 s (measured 10-20 s), sd-server
  300 s after serve is up. A process that exits early fails at once.
* THE IMAGE STACK STARTS sd-server ONLY AFTER serve IS READY, in
  `crow_core.image_server_workdir()` (an empty folder Crow owns, #324), with
  `crow_core._image_server_env()`. On failure, timeout or Ctrl+C, what this run
  started is ended by its handle (`crow_platform.terminate_tree`), the last 10
  log lines are shown, and no contract file is written.
* A POINT WITH A VIDEO SERVER (#340) starts only its engine here. Its
  contract file also carries `servers` -- the engine's argv, env, the keys to
  drop, lib_path, cwd, port and probe, and ComfyUI's argv, cwd (the runtime
  folder), port and probe -- plus `mode: "image"` and `pids.video`, so the
  window starts ComfyUI and restarts the engine exactly as planned here
  (`crow_core.use_mode`). The scan sees ComfyUI (`crow_platform.KIND_VIDEO`):
  it blocks a start like sd-server does, and Stop ends it.
* ONE POINT AT A TIME, checked before anything starts: the contract file
  (`crow_core.read_active_point`), then the process scan
  (`crow_core.running_servers(include_image=True)`; a serve is named by
  `crow_core.point_for_server`), then port 8099 itself in case the process list
  was unreadable. It holds in both directions: a llama-server blocks a
  baseline start and a baseline point blocks an optional one. The refusal
  names what runs and how to stop it: the menu entry, `--stop`, or the pid
  with `taskkill /PID <pid> /F` (`kill <pid>`).
* OPTIONAL llama.cpp LINES (the owner, 2026-10-01: the crow-nest points are
  the baseline). Crow's llama.cpp lines from manifests/operating-point.json
  (8081/8082/8083) are listed below the three points under "Optional
  (llama.cpp)", tagged "(optional)" and dimmed (the plain fallback keeps the
  tag). A line is listed only when `crow_core.server_command` resolves its
  binary and GGUF (`$CROW_MODELS`, `CROW_LLAMA_SERVER_<KEY>`); one that does
  not is left out, not shown as "not installed". Starting one uses
  crow_core.start_server's argv, env overlay, scope prefix, slot folder and
  `llama-server-<port>.out/.err.log`, with this menu's spawn, animation and
  wait (`/props` answers 200, 600 s). No contract file is written for it: its
  `point` is one of the three baseline ids. `--models` is handed on as
  `CROW_MODELS` so both kinds resolve under one root -- unless `CROW_MODELS` is
  already set: a lab root for these lines stays theirs (CrowSetup always passes
  `--models <install>/models` for the three points).
* STOP ends every model server the process scan sees (crow_core.stop_servers'
  set: serve, sd-server, llama-server), waits until each is torn down
  (`process_exists`: the process handle, not the exit code -- Windows tears
  a 13 GB server down for ~1.6 s after it has one) and no longer listed, up to
  30 s, and removes the contract file. A pid that only the contract file names is not
  killed (a pid outlives its process and may belong to another program by
  now); it is reported with the command.
* START CROW opens `crow_gui.py --base-url <the point's URL>` detached
  (pythonw.exe on Windows when it sits beside the interpreter), with the
  point's `crow_env` (the Image Stack's CROW_IMAGE_MODEL_DIR) in its
  environment; with a llama-server running, on `http://127.0.0.1:<its
  --port>/v1`, naming the server. Only when no model server with an address
  runs (nothing, or an sd-server alone) it says so and starts nothing.
* START CROW WITH CLAUDE (SUBSCRIPTION) (#398, `--start-claude`) needs no
  model server: Boot.start_claude, the same as the window's Claude entry. Its
  state is asked when it is chosen, never on a draw. Signed out it names
  `claude auth login` and opens nothing: a terminal that pops up from a
  terminal would be a second one for no reason.
* THE TERMINAL: stdout is forced to UTF-8; on Windows VT processing is
  switched on (SetConsoleMode, ENABLE_VIRTUAL_TERMINAL_PROCESSING). If that
  fails, or stdout is not a terminal, the output is plain: ASCII markers, no
  colour, no animation. NO_COLOR drops only the colour.
* ONE MENU, NOT TWO: Start Crow, Start Crow with Claude (subscription), the
  three points (each variant under its base), the optional lines, Stop, Quit. "Landed" shows
  for 5 seconds and returns to this menu by itself; errors and refusals wait
  for Enter so they can be read.
* THE SHORTCUT (`--create-shortcut DIR`, Windows): `DIR\Crow.lnk`, written by
  PowerShell's WScript.Shell with every value passed through the environment
  (no quoting). Target (#196, the operating-point window): `pythonw.exe` beside
  this interpreter (the interpreter itself when there is none) running this
  script with `--gui`, so no console opens. With `--terminal` it opens this
  menu instead: Windows Terminal (`wt.exe`) when it is on PATH, running the
  console interpreter with this script; else that interpreter itself. Either
  way `--install-root`, `--models` and `--stack` are carried along. Working
  folder: the install root. Icon: cli/crow.ico.
* THE WINDOW (`--gui`) is cli/crow_boot_gui.py: a face over this Boot, which
  it drives through `cancelled` (a Cancel button ends a start the way Ctrl+C
  does) and `on_stage` (which server is being waited for).

STANDARD LIBRARY ONLY, plus Crow's own crow_core and crow_platform.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import crow_core  # noqa: E402
import crow_platform  # noqa: E402

DEFAULT_STACK = os.path.normpath(os.path.join(HERE, os.pardir, "manifests", "stack.json"))
GUI_SCRIPT = os.path.join(HERE, "crow_gui.py")
ICON_FILE = os.path.join(HERE, "crow.ico")
PLATFORM_KEY = "windows" if crow_platform.IS_WINDOWS else "linux"

# glm53-flash (#365): its boot is not measured; it gets the Flash-Next allowance
# for the other container that streams experts from NVMe.
BOOT_TIMEOUT_S = {"flash-next": 600.0, "glm53-flash": 600.0}
DEFAULT_BOOT_TIMEOUT_S = 300.0
IMAGE_TIMEOUT_S = 300.0
LLAMA_TIMEOUT_S = 600.0             # crow_core.start_server's own wait_s
LANDED_S = 5
OPENED_S = 3
POLL_S = 1.0
FRAME_S = 0.12
STOP_WAIT_S = 30.0
LOG_TAIL_LINES = 10

EXIT_OK, EXIT_FAILED, EXIT_SETUP, EXIT_REFUSED = 0, 1, 2, 3

CREATE_BREAKAWAY_FROM_JOB = 0x01000000

# (fancy, plain): the plain half is what a console without VT gets.
ICONS = {
    "crow": ("\U0001F426", "*"),
    "nest": ("\U0001FAB9", "[nest]"),
    "landed": ("\U0001FABA", "[ok]"),
    "start": ("\U0001F680", ">"),
    "flash-next": ("\U0001F9E0", "-"),
    "27b": ("⚡", "-"),
    "glm53-flash": ("\U0001F40B", "-"),
    "image-stack": ("\U0001F3A8", "-"),
    "media-stack": ("\U0001F3AC", "-"),
    "optional": ("\U0001F999", "-"),
    "stop": ("\U0001F6D1", "x"),
    "quit": ("\U0001F44B", "q"),
    "on": ("\U0001F7E2", "[on]"),
    "off": ("⚪", "[off]"),
    "warn": ("⚠️ ", "!"),
    "fail": ("❌", "x"),
    "brush": ("\U0001F58C️ ", "~"),
}
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# #397: how a variant is named after its point's title; another key is shown as written.
VARIANT_TAGS = {"text": "text only"}


def kill_hint(pid) -> str:
    """The command that ends one process by hand on this platform."""
    return ("taskkill /PID %s /F" % pid) if crow_platform.IS_WINDOWS else ("kill %s" % pid)


def base_url_for(port: int) -> str:
    return "http://127.0.0.1:%d/v1" % int(port)


def point_title(title: str, variant: "str | None" = None) -> str:
    """A point's title with its variant's tag: "Qwen3.8-Flash-Next · text only".
    No variant: the title as it is."""
    if not variant:
        return title
    return "%s · %s" % (title, VARIANT_TAGS.get(variant, variant))


# ----------------------------------------------------------------- stack.json ---

class SetupError(Exception):
    """The stack or the install cannot be used as it is. Exit 2."""


def load_stack(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError as exc:
        raise SetupError("cannot read %s: %s" % (path, exc))
    except ValueError as exc:
        raise SetupError("%s is not valid JSON: %s" % (path, exc))
    if not isinstance(doc, dict) or not isinstance(doc.get("points"), list):
        raise SetupError("%s has no points list" % path)
    return doc


def resolve(value, install: str, models: str):
    """One stack value with ${INSTALL} and ${MODELS} filled in.

    A value that held a placeholder is a path: normalised for this platform.
    Anything else is passed as written.
    """
    text = str(value)
    if "${INSTALL}" not in text and "${MODELS}" not in text:
        return text
    text = text.replace("${MODELS}", models).replace("${INSTALL}", install)
    return os.path.normpath(text)


def _binary(spec: dict, point_id: str, what: str) -> str:
    binary = (spec.get("binary") or {}).get(PLATFORM_KEY)
    if not binary:
        raise SetupError("stack.json names no %s binary for %s on %s"
                         % (what, point_id, PLATFORM_KEY))
    return binary


def runs_here(point: dict) -> bool:
    """The point names this platform, or names none (= both, #340)."""
    return PLATFORM_KEY in (point.get("platforms") or ("windows", "linux"))


def plan_point(stack: dict, point_id: str, install: str, models: str,
               variant: "str | None" = None) -> dict:
    """Everything needed to start one point, placeholders resolved.

    `lib_path` is stack.json's top-level `lib_path` for this platform: the
    folders serve and sd-server get in front of LD_LIBRARY_PATH (#341). []
    where the stack names none (Windows).

    `variant` (#397) is one of the point's stack.json `variants` by its key:
    the base env minus its `env_unset`, plus its `env`; its menu line and gui
    text; `identity.vision` from its `vision`. The title stays the base's.
    `plan["variant"]` is the key, None for the base. A key the point does not
    have is a SetupError.
    """
    points = {p.get("id"): p for p in stack["points"]}
    point = points.get(point_id)
    if point is None:
        raise SetupError("unknown operating point %r (one of %s)"
                         % (point_id, ", ".join(p for p in points if p)))
    if not runs_here(point):
        raise SetupError("%s runs on %s only, not on %s"
                         % (point_id, ", ".join(point.get("platforms") or []), PLATFORM_KEY))
    chosen = None
    if variant is not None:
        known = [v for v in point.get("variants") or [] if isinstance(v, dict)]
        chosen = next((v for v in known if v.get("key") == variant), None)
        if chosen is None:
            raise SetupError("%s has no variant %r (%s)"
                             % (point_id, variant,
                                ", ".join(str(v.get("key")) for v in known) or "it has none"))

    def r(value):
        return resolve(value, install, models)

    engine = point.get("engine") or {}
    env = engine.get("env") or {}
    if chosen is not None:
        env = {k: v for k, v in env.items() if k not in (chosen.get("env_unset") or [])}
        env.update(chosen.get("env") or {})
    port = int(engine.get("port") or crow_core.CROW_NEST_PORT)
    serve = {
        "kind": engine.get("kind") or "serve",
        "argv": [r(_binary(engine, point_id, "engine"))]
                + [r(a) for a in engine.get("argv") or []],
        "env": {str(k): r(v) for k, v in env.items()},
        "cwd": r(engine.get("cwd") or "${INSTALL}"),
        "dirs": [r(d) for d in engine.get("dirs") or []],
        "port": port,
        "readiness": engine.get("readiness") or {"path": "/health", "status": 200},
    }
    image = None
    spec = point.get("image_server")
    if spec:
        image = {
            # #404: $CROW_IMAGE_WEIGHT_TYPE's `--type` tail, the one
            # crow_core.image_server_command appends (NOT MEASURED; [] unset).
            "argv": [r(_binary(spec, point_id, "image server"))]
                    + [r(a) for a in spec.get("argv") or []]
                    + [r(a) for a in (spec.get("argv_platform") or {}).get(PLATFORM_KEY) or []]
                    + crow_core.image_weight_type_args(),
            "port": int(spec.get("port") or 8097),
            "readiness": spec.get("readiness") or {"path": "/", "status": 200},
        }
    # #340: the video server is planned here but never started by the menu; Crow
    # starts it on first use. `runtime` is the unpacked folder its program lives in.
    video = None
    spec = point.get("video_server")
    if spec:
        video = {
            "argv": [r(_binary(spec, point_id, "video server"))]
                    + [r(a) for a in spec.get("argv") or []],
            "port": int(spec.get("port") or 8188),
            "readiness": spec.get("readiness") or {"path": "/system_stats", "status": 200},
            "runtime": r(((spec.get("runtime") or {}).get(PLATFORM_KEY) or {}).get("dir") or ""),
        }
    menu = point.get("menu") or {}
    words = menu if chosen is None else (chosen.get("menu") or {})
    identity = engine.get("identity") or {}
    if chosen is not None:
        identity = dict(identity, vision=bool(chosen.get("vision")))
    return {
        "id": point_id,
        "variant": variant,
        "title": menu.get("title") or point_id,
        "line": words.get("line") or "",
        "gui": words.get("gui") or "",
        "serve": serve,
        "image": image,
        "video": video,
        "crow_env": {str(k): r(v) for k, v in (point.get("crow_env") or {}).items()},
        "base_url": base_url_for(port),
        "identity": identity,
        "timeout": BOOT_TIMEOUT_S.get(point_id, DEFAULT_BOOT_TIMEOUT_S),
        "lib_path": [r(d) for d in (stack.get("lib_path") or {}).get(PLATFORM_KEY) or []],
    }


def with_lib_path(env: dict, lib_path) -> dict:
    """`env` with the plan's library folders in front of LD_LIBRARY_PATH (#341).

    The loader searches LD_LIBRARY_PATH before RUNPATH, and a library that
    dlopens further (libnvrtc -> libnvrtc-builtins) inherits it; libnvrtc has
    no RUNPATH and cudarc dlopens bare names. A folder already there moves to
    the front instead of being listed twice. No folders (Windows): `env` comes
    back as it was, no key added.
    """
    if not lib_path:
        return env
    have = [d for d in (env.get("LD_LIBRARY_PATH") or "").split(os.pathsep) if d]
    env["LD_LIBRARY_PATH"] = os.pathsep.join(list(lib_path) + [d for d in have if d not in lib_path])
    return env


def engine_env_keys(stack: dict) -> set:
    """Every env key any point's engine declares, its variants' included.

    #397: a variant's `env` keys are the stack's too, so a `CROW_VIT=0` left in
    the shell cannot boot a base point blind while its contract file says base.
    `env_unset` names base keys, which are here already.
    """
    keys = set()
    for point in stack["points"]:
        keys.update((point.get("engine") or {}).get("env") or {})
        for variant in point.get("variants") or []:
            if isinstance(variant, dict):
                keys.update(variant.get("env") or {})
                keys.update(variant.get("env_unset") or [])
    return keys


def missing_files(plan: dict, install: str, models: str) -> list:
    """Placeholder paths the point needs that are not on disk (dirs excluded).

    The video server is not among them: the menu never starts it, and a point
    whose video runtime is missing still boots (#340).
    """
    roots = tuple(os.path.normpath(p) for p in (install, models))
    dirs = set(plan["serve"]["dirs"])
    wanted = [plan["serve"]["argv"][0]] + list(plan["serve"]["env"].values())
    wanted += [a for a in plan["serve"]["argv"][1:] if a not in dirs]
    if plan["image"]:
        wanted += plan["image"]["argv"]
    out = []
    for path in wanted:
        if not os.path.normpath(path).startswith(roots) or path in dirs:
            continue
        if not os.path.exists(path) and path not in out:
            out.append(path)
    return out


def plan_json(stack: dict, point_id: str, install: str, models: str) -> dict:
    """`--plan <point> --json`: what the menu starts for a point, for CrowSetup's check.

    Built from plan_point and resolve, the menu's own resolution, so the
    installer checks exactly what a start would use. `env` is the point's own
    keys only (the inherited environment is not part of the plan). `files` are
    the point's stack.json files with dest resolved; `derived` names the files
    built on the machine (none since #400: Ming-Image's files are used as
    published; Qwen-Image 2.1 had text_encoder_sdcli/), with the input ids
    they consume and their outputs.
    """
    plan = plan_point(stack, point_id, install, models)
    point = next(p for p in stack["points"] if p.get("id") == point_id)

    def r(value):
        return resolve(value, install, models)

    def lookup(kind: str, ids) -> list:
        known = {e.get("id"): e for e in stack.get(kind) or []}
        out = []
        for ref in ids or []:
            if ref not in known:
                raise SetupError("%s lists %s %r, which stack.json does not define"
                                 % (point_id, {"files": "file"}.get(kind, "derived entry"), ref))
            out.append(known[ref])
        return out

    files = [{"id": f["id"], "dest": r(f["dest"]), "bytes": int(f["bytes"]),
              "sha256": f.get("sha256")} for f in lookup("files", point.get("files"))]
    derived = []
    for d in lookup("derived", point.get("derived")):
        dest = r(d["dest"])
        derived.append({
            "id": d["id"], "dest": dest, "inputs": list(d.get("inputs") or []),
            "outputs": [{"dest": os.path.normpath(os.path.join(dest, o["path"])),
                         "bytes": int(o["bytes"]), "sha256": o.get("sha256")}
                        for o in d.get("outputs") or []],
        })
    serve = plan["serve"]
    image = plan["image"]
    video = plan["video"]
    return {
        "point": plan["id"],
        "title": plan["title"],
        "install_root": install,
        "models_root": models,
        "base_url": plan["base_url"],
        "serve": {"kind": serve["kind"], "binary": serve["argv"][0], "argv": serve["argv"][1:],
                  "cwd": serve["cwd"],
                  "env": serve["env"], "dirs": serve["dirs"], "port": serve["port"],
                  "readiness": serve["readiness"]},
        "image": None if image is None else {
            "binary": image["argv"][0], "argv": image["argv"][1:], "port": image["port"],
            "readiness": image["readiness"]},
        "video": None if video is None else {
            "binary": video["argv"][0], "argv": video["argv"][1:], "port": video["port"],
            "readiness": video["readiness"], "runtime": video["runtime"]},
        "crow_env": plan["crow_env"],
        "files": files,
        "derived": derived,
        # #348: the archive the installer's runtime step unpacks and deletes,
        # by file id -- consumed like a derived job's inputs, so the check asks
        # for the unpacked program (video.binary) instead.
        "runtime_archives": [a for a in [((((point.get("video_server") or {}).get("runtime")
                                             or {}).get(PLATFORM_KEY)) or {}).get("file")] if a],
    }


# ------------------------------------------------------------- the terminal ---

def _enable_vt(stream) -> bool:
    """Switch on VT processing for this console. False when it cannot be had."""
    if not crow_platform.IS_WINDOWS:
        return True
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        handle = kernel32.GetStdHandle(-11)                 # STD_OUTPUT_HANDLE
        mode = wintypes.DWORD()
        if not handle or not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:                       # noqa: BLE001 - plain output is the answer
        return False


class Style:
    """How this terminal may be written to: icons, colour, an animated line."""

    def __init__(self, fancy: bool = False, colour: bool = False, animate: bool = False):
        self.fancy, self.colour, self.animate = fancy, colour, animate

    @classmethod
    def detect(cls, stream) -> "Style":
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                   # noqa: BLE001 - a wrapped stream keeps its own
            pass
        tty = bool(getattr(stream, "isatty", lambda: False)())
        vt = tty and _enable_vt(stream)
        return cls(fancy=vt, colour=vt and not os.environ.get("NO_COLOR"), animate=vt)

    def icon(self, key: str) -> str:
        fancy, plain = ICONS[key]
        return fancy if self.fancy else plain

    def paint(self, text: str, code: str) -> str:
        return "\x1b[%sm%s\x1b[0m" % (code, text) if self.colour else text

    def bold(self, text: str) -> str:
        return self.paint(text, "1")

    def dim(self, text: str) -> str:
        return self.paint(text, "2")


def flight_frame(i: int, fancy: bool, width: int = 16) -> str:
    """One frame of the in-line animation: the crow flying towards the nest."""
    if not fancy:
        return "|/-\\"[i % 4]
    pos = i % width
    track = "".join("\U0001F426" if n == pos else "·" for n in range(width))
    return track + " \U0001FAB9"


# ------------------------------------------------------------------ helpers ---

def http_get(url: str, timeout: float = 2.0):
    """(status, body) for one GET; (None, b"") when nothing answers."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:                   # noqa: BLE001
            body = b""
        exc.close()
        return exc.code, body
    except Exception:                       # noqa: BLE001 - not answering is the answer
        return None, b""


READY, WAIT, BROKEN = "ready", "wait", "broken"


def readiness_state(spec: dict, status, body: bytes, fatal_5xx: bool) -> str:
    if status is None:
        return WAIT
    if status == int(spec.get("status", 200)):
        want = spec.get("json")
        if not want:
            return READY
        try:
            doc = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            return WAIT
        if isinstance(doc, dict) and all(doc.get(k) == v for k, v in want.items()):
            return READY
        return WAIT
    if status >= 500 and fatal_5xx:
        return BROKEN
    return WAIT


def log_tail(path: str, lines: int = LOG_TAIL_LINES) -> list:
    """The last lines of a server log, progress redraws and colour removed."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 65536))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    rows = [_ANSI.sub("", r).rstrip() for r in re.split(r"[\r\n]+", text)]
    return [r for r in rows if r.strip()][-lines:]


def process_exists(pid) -> bool:
    """True until the process is really gone, teardown included.

    NOT crow_platform.pid_alive, WHICH ANSWERS "HAS NO EXIT CODE YET". Measured
    2026-10-01 on a 27B llama-server (13 GB) after taskkill /F: pid_alive and the
    Get-CimInstance scan said gone after 0.08 s, the process handle was signalled
    and tasklist dropped it only after 1.61 s -- the time Windows needed to tear
    down its memory. A next point started in between shares the card with it.
    Windows: a SYNCHRONIZE handle, signalled once the process object is done.
    Elsewhere: pid_alive, except that a ZOMBIE is gone (#341). The window and
    the menu are the parent of the serve they started, and nothing waits on
    it after Stop: measured 2026-10-02, a scoped child that was killed stays
    `Z` in /proc/<pid>/stat and answers signal 0, so pid_alive said "alive"
    and Stop waited its 30 s and reported it still there. A zombie holds no
    memory, card or port; only its exit status is left.
    """
    if not crow_platform.IS_WINDOWS:
        return crow_platform.pid_alive(pid) and not _is_zombie(pid)
    try:
        number = int(pid)
    except (TypeError, ValueError):
        return False
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    handle = kernel32.OpenProcess(0x00100000, False, number)          # SYNCHRONIZE
    if not handle:
        return ctypes.get_last_error() == 5                           # ACCESS_DENIED
    try:
        return kernel32.WaitForSingleObject(handle, 0) == 0x102       # WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def _is_zombie(pid, proc_root: str = "/proc") -> bool:
    """True when /proc says the process has exited and waits to be reaped."""
    try:
        with open(os.path.join(proc_root, str(int(pid)), "stat"), "rb") as fh:
            stat = fh.read().decode("utf-8", "replace")
    except (OSError, TypeError, ValueError):
        return False
    # the state follows the command name, which is in parentheses and may hold any byte
    rest = stat.rsplit(")", 1)[-1].split()
    return bool(rest) and rest[0] == "Z"


def _detached_kwargs(breakaway: bool) -> dict:
    kw = dict(crow_platform.spawn_kwargs(detached=True))
    if crow_platform.IS_WINDOWS and breakaway:
        kw["creationflags"] = kw.get("creationflags", 0) | CREATE_BREAKAWAY_FROM_JOB
    return kw


def _quote(arg: str) -> str:
    return '"%s"' % arg if (not arg or " " in arg or "\t" in arg) else arg


def quiet_python(exe: str) -> str:
    """pythonw.exe beside `exe` on Windows when it is there, else `exe`.

    The windows (Crow's and the operating-point window) need no console; the
    embeddable and the python.org interpreters both ship pythonw.exe.
    """
    if crow_platform.IS_WINDOWS:
        quiet = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(quiet):
            return quiet
    return exe


class LlamaLines:
    """Crow's optional llama.cpp operating points, as crow_core knows them.

    The lines are manifests/operating-point.json's `servers` (8081/8082/8083);
    every answer is crow_core's: `bootable_models`, `server_command` (the GGUF
    under `$CROW_MODELS` or `<install>/models`, the binary from
    `CROW_LLAMA_SERVER_<KEY>` or the line's own or `<install>/bin`),
    `server_port`, `model_label`, `server_env`. A test hands in its own.
    """

    def __init__(self, install: str):
        self.install = install

    def keys(self) -> tuple:
        return crow_core.bootable_models()

    def command(self, key: str) -> list:
        """The argv; raises crow_core.ServerBootError when it does not resolve."""
        return crow_core.server_command(key, None, self.install)

    def port(self, key: str):
        return crow_core.server_port(key)

    def label(self, key: str) -> str:
        return crow_core.model_label(key)

    def env(self, key: str) -> dict:
        return crow_core.server_env(key)

    def installed(self) -> list:
        """[{key, title, port, argv}] for every line whose files resolve on disk.

        A line that does not resolve is left out of the menu, not shown as
        "not installed": the three baseline points are the product, and a list
        of models nobody downloaded is noise.
        """
        out = []
        for key in self.keys():
            try:
                argv = self.command(key)
            except Exception:              # noqa: BLE001 - not on disk is "not listed"
                continue
            port = self.port(key)
            if not port:
                continue
            out.append({"key": key, "title": self.label(key) or key,
                        "port": int(port), "argv": argv})
        return out


# ---------------------------------------------------------------- the boot ---

class Boot:
    """The menu and its steps. Every outside effect is a parameter, for tests."""

    def __init__(self, stack: dict, install: str, models: str, out=None,
                 style: "Style | None" = None, popen=None, get=None,
                 sleep=None, clock=None, read=None, scan=None, active=None,
                 point_for=None, model_path=None, write_active=None,
                 terminate=None, kill=None, alive=None, log_dir=None,
                 forwarded_args=(), llama=None, cancelled=None, on_stage=None,
                 vision=None):
        self.stack, self.install, self.models = stack, install, models
        self.out = out or sys.stdout
        self.style = style or Style()
        self.popen = popen or subprocess.Popen
        self.get = get or http_get
        self.sleep = sleep or time.sleep
        self.clock = clock or time.monotonic
        self.read = read or input
        self.scan = scan or (lambda: crow_core.running_servers(include_image=True))
        self.active = active or crow_core.read_active_point
        self.point_for = point_for or crow_core.point_for_server
        self.model_path = model_path or crow_core.server_model_path
        self.vision = vision or crow_core.server_vision
        self.write_active = write_active or crow_core.write_active_point
        self.terminate = terminate or crow_platform.terminate_tree
        self.kill = kill or crow_platform.kill_pid
        self.alive = alive or process_exists
        self._log_dir = log_dir
        self._note = ""
        self.forwarded_args = list(forwarded_args)
        self.llama = llama or LlamaLines(install)
        # The window's two hooks (crow_boot_gui.py). `cancelled` is asked on
        # every turn of the wait: True ends the start like Ctrl+C does here.
        # `on_stage` hears which server the wait is for ("serve", "sd-server",
        # "llama-server"). The menu passes neither.
        self.cancelled = cancelled or (lambda: False)
        self.on_stage = on_stage or (lambda stage: None)
        self._llama_cache = None
        self.titles = {p.get("id"): (p.get("menu") or {}).get("title") or p.get("id")
                       for p in stack["points"]}
        self.variants = {p.get("id"): [v for v in p.get("variants") or [] if isinstance(v, dict)]
                         for p in stack["points"]}

    # -- output ------------------------------------------------------------
    def say(self, text: str = "") -> None:
        self.out.write(text + "\n")
        self.out.flush()

    def _line(self, text: str) -> None:
        """Redraw the current line in place (animated terminals only)."""
        self.out.write("\r\x1b[2K" + text)
        self.out.flush()

    def _end_line(self) -> None:
        if self.style.animate:
            self.out.write("\r\x1b[2K")
            self.out.flush()

    def countdown(self, seconds: int, what: str) -> None:
        """Wait `seconds`, showing it; returns by itself."""
        for left in range(int(seconds), 0, -1):
            text = "   %s in %d s..." % (what, left)
            if self.style.animate:
                self._line(self.style.dim(text))
            elif left == seconds:
                self.say(text)
            self.sleep(1)
        self._end_line()

    def pause(self) -> None:
        try:
            self.read(self.style.dim("   Press Enter to return to the menu. "))
        except (EOFError, KeyboardInterrupt):
            pass

    def optional_lines(self) -> list:
        """The installed llama.cpp lines, resolved once per run."""
        if self._llama_cache is None:
            self._llama_cache = self.llama.installed()
        return self._llama_cache

    def label(self, point_id: "str | None", variant: "str | None" = None) -> str:
        if not point_id:
            return "crow-nest (point not identified yet, it may still be loading)"
        return "%s (%s)" % (point_title(self.titles.get(point_id, point_id), variant), point_id)

    def log_dir(self) -> str:
        if self._log_dir:
            return self._log_dir
        folder = crow_platform.log_dir()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            folder = os.path.join(self.install, "runs")
        self._log_dir = folder
        return folder

    # -- what runs ---------------------------------------------------------
    def blind_variant(self, point_id: "str | None", url: str) -> "str | None":
        """#397: the variant a serve the scan found runs, or None for the base.

        Only a point with a variant of `vision: false` is asked, over /props
        `modalities.vision` (`self.vision`); false names that variant. True,
        or no answer, is the base point.
        """
        key = next((v.get("key") for v in self.variants.get(point_id) or []
                    if v.get("vision") is False), None)
        if key is None:
            return None
        return key if self.vision(url) is False else None

    def detect(self) -> "dict | None":
        """The running point (or other model server), or None.

        A crow-nest point carries `variant` (#397): the contract file's, or
        for a serve found by the scan or on the port, `blind_variant`.
        """
        doc = self.active()
        if doc:
            pids = doc.get("pids") or {}
            return {"kind": crow_platform.KIND_CROW_NEST, "point": doc.get("point"),
                    "variant": doc.get("variant"), "source": "active-point",
                    "pids": {"serve": pids.get("serve"), "image": pids.get("image"),
                             "video": pids.get("video")},
                    "base_url": doc.get("base_url") or base_url_for(crow_core.CROW_NEST_PORT),
                    "since": doc.get("started_at")}
        found = self.scan() or []
        by_kind = {}
        for pid, line in found:
            by_kind.setdefault(crow_platform.server_kind(line), []).append((pid, line))
        serves = by_kind.get(crow_platform.KIND_CROW_NEST, [])
        images = by_kind.get(crow_platform.KIND_IMAGE, [])
        llamas = by_kind.get(crow_platform.KIND_LLAMA, [])
        image_pid = images[0][0] if images else None
        if serves:
            pid, line = serves[0]
            port = crow_platform.server_port(line) or crow_core.CROW_NEST_PORT
            url = base_url_for(port)
            point = self.point_for(url)
            return {"kind": crow_platform.KIND_CROW_NEST, "point": point,
                    "variant": self.blind_variant(point, url),
                    "source": "scan", "pids": {"serve": pid, "image": image_pid},
                    "base_url": url}
        if llamas:
            pid, line = llamas[0]
            port = crow_platform.server_port(line)
            return {"kind": crow_platform.KIND_LLAMA, "point": None, "source": "scan",
                    "pids": {"serve": pid, "image": image_pid}, "port": port,
                    "base_url": base_url_for(port) if port else None,
                    "model": crow_core.served_model(line)}
        if images:
            return {"kind": crow_platform.KIND_IMAGE, "point": None, "source": "scan",
                    "pids": {"serve": None, "image": image_pid}}
        videos = by_kind.get(crow_platform.KIND_VIDEO, [])
        if videos:
            # #340: ComfyUI holds the card as firmly as any of them.
            return {"kind": crow_platform.KIND_VIDEO, "point": None, "source": "scan",
                    "pids": {"serve": None, "image": None, "video": videos[0][0]}}
        url = base_url_for(crow_core.CROW_NEST_PORT)
        point = self.point_for(url)
        if point:
            return {"kind": crow_platform.KIND_CROW_NEST, "point": point,
                    "variant": self.blind_variant(point, url),
                    "source": "port", "pids": {"serve": None, "image": None},
                    "base_url": url}
        return None

    def describe(self, running: dict) -> str:
        """One phrase naming what runs."""
        kind = running["kind"]
        pids = running.get("pids") or {}
        if kind == crow_platform.KIND_LLAMA:
            where = " on port %s" % running["port"] if running.get("port") else ""
            model = " (%s)" % os.path.basename(running["model"]) if running.get("model") else ""
            return "a llama.cpp server%s%s, pid %s" % (model, where, pids.get("serve"))
        if kind == crow_platform.KIND_IMAGE:
            return "an image server (sd-server) without its language model, pid %s" % pids.get("image")
        if kind == crow_platform.KIND_VIDEO:
            return "a video server (ComfyUI) without its language model, pid %s" % pids.get("video")
        bits = []
        if pids.get("serve"):
            bits.append("serve pid %s" % pids["serve"])
        if pids.get("image"):
            bits.append("sd-server pid %s" % pids["image"])
        if pids.get("video"):
            bits.append("ComfyUI pid %s" % pids["video"])
        return "%s%s" % (self.label(running.get("point"), running.get("variant")),
                         ", " + ", ".join(bits) if bits else "")

    def refusal(self, running: dict) -> str:
        """Why a second point is not started, and how to stop the first."""
        pids = running.get("pids") or {}
        lines = ["%s Another model server is already running: %s."
                 % (self.style.icon("warn"), self.describe(running)),
                 "   Only one operating point can run at a time."]
        lines.append('   To stop it: choose "Stop the running point" in this menu, or run')
        lines.append("     python %s --stop" % os.path.join("cli", "crow_boot.py"))
        hand = [kill_hint(p) for p in (pids.get("serve"), pids.get("image"), pids.get("video"))
                if p]
        if hand:
            lines.append("   or by hand: %s" % " and ".join(hand))
        return "\n".join(lines)

    # -- start -------------------------------------------------------------
    def _spawn(self, argv, **kw):
        try:
            return self.popen(argv, **kw, **_detached_kwargs(breakaway=True))
        except OSError as exc:
            if crow_platform.IS_WINDOWS and getattr(exc, "winerror", None) == 5:
                return self.popen(argv, **kw, **_detached_kwargs(breakaway=False))
            raise

    def _open_log(self, name: str):
        path = os.path.join(self.log_dir(), name)
        keep = getattr(crow_core, "_keep_previous_log", None)
        if keep is not None:
            keep(path)
        return path, open(path, "wb")

    def _wait(self, procs, port: int, readiness: dict, timeout: float,
              fatal_5xx: bool, message: str):
        """Poll until ready. None on success, else the reason."""
        url = "http://127.0.0.1:%d%s" % (port, readiness.get("path") or "/")
        start = self.clock()
        next_probe = start
        frame = 0
        self.on_stage(procs[-1][0])
        if not self.style.animate:
            self.say("   %s (waiting for %s)" % (message, url))
        while True:
            if self.cancelled():
                self._end_line()
                return "cancelled"
            now = self.clock()
            for name, proc in procs:
                code = proc.poll()
                if code is not None:
                    self._end_line()
                    return "%s exited with code %s before it answered" % (name, code)
            if now >= next_probe:
                status, body = self.get(url, 2.0)
                state = readiness_state(readiness, status, body, fatal_5xx)
                if state == READY:
                    self._end_line()
                    return None
                if state == BROKEN:
                    self._end_line()
                    return "%s answered HTTP %s on %s" % (procs[-1][0], status, url)
                next_probe = self.clock() + POLL_S
            elapsed = self.clock() - start
            if elapsed > timeout:
                self._end_line()
                return "%s did not answer within %.0f s" % (procs[-1][0], timeout)
            if self.style.animate:
                self._line("  %s  %s %s" % (flight_frame(frame, self.style.fancy),
                                            message, self.style.dim("%3.0f s" % elapsed)))
            frame += 1
            self.sleep(FRAME_S)

    def _fail(self, title: str, why: str, started, logs) -> int:
        """End what this run started, say why, show the logs' last lines."""
        for _name, proc in reversed(started):
            self.terminate(proc)
        self.say("%s %s did not land: %s." % (self.style.icon("fail"), title, why))
        if started:
            self.say("   What this run started was stopped.")
        for log in logs:
            tail = log_tail(log)
            if tail:
                self.say("   Last lines of %s:" % log)
                for row in tail:
                    self.say("     " + row)
        return EXIT_FAILED

    def start(self, point_id: str, interactive: bool = False,
              variant: "str | None" = None) -> int:
        """Start one point, or with `variant` one of its stack.json variants (#397).

        An optional llama.cpp line has no variants: with one named, its key is
        no point of the stack and the start is a setup error.
        """
        line = None
        if variant is None:
            line = next((o for o in self.optional_lines() if o["key"] == point_id), None)
        if line is not None:
            return self.start_llama(line, interactive)
        try:
            plan = plan_point(self.stack, point_id, self.install, self.models, variant)
        except SetupError as exc:
            self.say("%s %s" % (self.style.icon("fail"), exc))
            return EXIT_SETUP
        title = point_title(plan["title"], plan["variant"])
        running = self.detect()
        if running:
            self.say(self.refusal(running))
            return EXIT_REFUSED
        for folder in plan["serve"]["dirs"]:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as exc:
                self.say("%s cannot create %s: %s" % (self.style.icon("fail"), folder, exc))
                return EXIT_SETUP
        missing = missing_files(plan, self.install, self.models)
        if missing:
            self.say("%s %s is not installed completely. Missing:"
                     % (self.style.icon("fail"), title))
            for path in missing[:5]:
                self.say("     %s" % path)
            if len(missing) > 5:
                self.say("     ... and %d more" % (len(missing) - 5))
            return EXIT_SETUP

        self.say("%s Starting %s -- %s" % (self.style.icon("start"),
                                           self.style.bold(title), plan["line"]))
        env = {k: v for k, v in os.environ.items() if k not in engine_env_keys(self.stack)}
        env.update(plan["serve"]["env"])
        with_lib_path(env, plan["lib_path"])
        started = []
        logs = []
        began = self.clock()
        try:
            log, sink = self._open_log("serve-%d.log" % plan["serve"]["port"])
            logs.append(log)
            try:
                serve = self._spawn(crow_platform.server_scope_prefix() + plan["serve"]["argv"],
                                    cwd=plan["serve"]["cwd"],
                                    env=env, stdin=subprocess.DEVNULL,
                                    stdout=sink, stderr=subprocess.STDOUT)
            finally:
                sink.close()
            started.append(("serve", serve))
            why = self._wait([("serve", serve)], plan["serve"]["port"],
                             plan["serve"]["readiness"], plan["timeout"], False,
                             "Please wait while flying to the nest...")
            image = None
            if why is None and plan["image"]:
                work = crow_core.image_server_workdir()
                os.makedirs(work, exist_ok=True)
                log, sink = self._open_log("sd-server-%d.log" % plan["image"]["port"])
                logs.append(log)
                try:
                    image = self._spawn(crow_platform.server_scope_prefix() + plan["image"]["argv"],
                                        cwd=work,
                                        env=with_lib_path(crow_core._image_server_env(),
                                                          plan["lib_path"]),
                                        stdin=subprocess.DEVNULL,
                                        stdout=sink, stderr=subprocess.STDOUT)
                finally:
                    sink.close()
                started.append(("sd-server", image))
                why = self._wait([("serve", serve), ("sd-server", image)],
                                 plan["image"]["port"], plan["image"]["readiness"],
                                 IMAGE_TIMEOUT_S, True,
                                 "%s Fetching the paint brushes (%s)..."
                                 % (self.style.icon("brush"), crow_core.IMAGE_MODEL_SHORT))
        except KeyboardInterrupt:
            why = "cancelled"
        except OSError as exc:
            why = "could not be started: %s" % exc
        if why is not None:
            return self._fail(title, why, started, logs)

        seconds = self.clock() - began
        pids = {"serve": serve.pid, "image": image.pid if image is not None else None}
        extra = {}
        if plan["video"]:
            # #340: the window starts ComfyUI and restarts this engine itself
            # (crow_core.use_mode), from exactly what this plan resolved.
            pids["video"] = None
            extra = {"mode": "image", "servers": {
                "serve": {"argv": plan["serve"]["argv"], "env": plan["serve"]["env"],
                          "drop": sorted(engine_env_keys(self.stack)),
                          "lib_path": plan["lib_path"], "cwd": plan["serve"]["cwd"],
                          "port": plan["serve"]["port"],
                          "readiness": plan["serve"]["readiness"]},
                "video": {"argv": plan["video"]["argv"], "cwd": plan["video"]["runtime"],
                          "port": plan["video"]["port"],
                          "readiness": plan["video"]["readiness"]}}}
        if plan["variant"] is not None:
            extra["variant"] = plan["variant"]          # #397; a base start writes none
        try:
            where = self.write_active(plan["id"], plan["base_url"], pids, **extra)
        except (OSError, ValueError) as exc:
            where = None
            self.say("%s the contract file could not be written: %s" % (self.style.icon("warn"), exc))
        model = self.model_path(plan["base_url"]) or ""
        self.landed(plan, seconds, model, pids, where, interactive)
        return EXIT_OK

    def start_llama(self, line: dict, interactive: bool = False) -> int:
        """Start one optional llama.cpp line the way crow_core.start_server does.

        The argv, the env overlay, the scope prefix, the slot folder and the
        two logs (`llama-server-<port>.out.log` / `.err.log`) are
        crow_core.start_server's; the spawn, the animation and the wait are this menu's
        (detached like serve, ready when `/props` answers 200). NO CONTRACT FILE:
        its `point` is one of the three baseline ids, and the window keeps
        today's behaviour for a llama.cpp server.
        """
        title = "%s (optional)" % line["title"]
        running = self.detect()
        if running:
            self.say(self.refusal(running))
            return EXIT_REFUSED
        try:
            argv = self.llama.command(line["key"])
        except Exception as exc:          # noqa: BLE001 - ServerBootError names what is missing
            self.say("%s %s cannot start: %s" % (self.style.icon("fail"), title, exc))
            return EXIT_SETUP
        if "--slot-save-path" in argv:
            try:
                os.makedirs(argv[argv.index("--slot-save-path") + 1], exist_ok=True)
            except (OSError, IndexError):
                pass                      # the server refuses it in its own words
        port = line["port"]
        env = dict(os.environ)
        env.update(self.llama.env(line["key"]) or {})
        self.say("%s Starting %s -- llama.cpp on port %d"
                 % (self.style.icon("start"), self.style.bold(title), port))
        logs, started = [], []
        began = self.clock()
        try:
            out_log, out_sink = self._open_log("llama-server-%d.out.log" % port)
            err_log, err_sink = self._open_log("llama-server-%d.err.log" % port)
            logs += [err_log, out_log]
            try:
                proc = self._spawn(crow_platform.server_scope_prefix() + argv, env=env,
                                   stdin=subprocess.DEVNULL, stdout=out_sink, stderr=err_sink)
            finally:
                out_sink.close()
                err_sink.close()
            started.append(("llama-server", proc))
            why = self._wait([("llama-server", proc)], port, {"path": "/props", "status": 200},
                             LLAMA_TIMEOUT_S, False, "Please wait while flying to the nest...")
        except KeyboardInterrupt:
            why = "cancelled"
        except OSError as exc:
            why = "could not be started: %s" % exc
        if why is not None:
            return self._fail(title, why, started, logs[:1])
        url = base_url_for(port)
        plan = {"title": title, "base_url": url, "identity": {}, "process": "llama-server"}
        self.landed(plan, self.clock() - began, self.model_path(url) or "",
                    {"serve": proc.pid, "image": None}, None, interactive)
        return EXIT_OK

    def landed(self, plan, seconds, model, pids, where, interactive) -> None:
        self.say("%s %s %s is ready at %s after %.0f s."
                 % (self.style.icon("landed"), self.style.paint("Landed!", "1;32"),
                    point_title(plan["title"], plan.get("variant")), plan["base_url"], seconds))
        want = (plan.get("identity") or {}).get("endswith") or ""
        if model:
            self.say("   model: %s" % model)
            if want and not model.replace("\\", "/").lower().endswith(want.lower()):
                self.say("   %s expected a model ending in %s" % (self.style.icon("warn"), want))
        bits = ["%s pid %s" % (plan.get("process", "serve"), pids["serve"])]
        if pids.get("image"):
            bits.append("sd-server pid %s" % pids["image"])
        self.say("   %s" % ", ".join(bits))
        if where:
            self.say(self.style.dim("   contract file: %s" % where))
        if interactive:
            self.say('   Choose "Start Crow" to open the window.')
            self.countdown(LANDED_S, "Back to the menu")

    # -- stop --------------------------------------------------------------
    def stop(self) -> int:
        """End every model server, wait until they are gone, remove the file.

        crow_core.stop_servers' set -- serve, sd-server and llama-server -- and
        ONLY WHAT THE SCAN SEES. The contract file's pids name the point, but a
        pid outlives its process: after a crash Windows may hand it to any
        program, and killing it by the file alone would end that program.
        """
        doc = self.active() or {}
        point = doc.get("point")
        targets, llama_names = [], []
        for pid, line in self.scan() or []:
            kind = crow_platform.server_kind(line)
            if kind == crow_platform.KIND_LLAMA:
                targets.append(("llama", str(pid)))
                llama_names.append(os.path.basename(crow_core.served_model(line)) or "llama.cpp")
                continue
            role = {crow_platform.KIND_IMAGE: "image",
                    crow_platform.KIND_VIDEO: "video"}.get(kind, "serve")
            targets.append((role, str(pid)))
            if role == "serve" and not point:
                port = crow_platform.server_port(line) or crow_core.CROW_NEST_PORT
                point = self.point_for(base_url_for(port))
        seen = {p for _r, p in targets}
        strays = [str(p) for p in (doc.get("pids") or {}).values()
                  if p and str(p) not in seen and self.alive(p)]
        path = crow_core.active_point_path()
        if not targets:
            removed = self._remove(path)
            self.say("%s Nothing to stop: no operating point is running.%s"
                     % (self.style.icon("off"),
                        " (a stale contract file was removed)" if removed else ""))
            self._mention_strays(strays)
            return EXIT_OK
        if not point and llama_names:
            point_text = "the llama.cpp server (%s)" % ", ".join(llama_names)
        else:
            point_text = self.label(point, doc.get("variant")) if point else "the running point"
        for _role, pid in targets:
            self.kill(pid)
        began = self.clock()
        deadline = began + STOP_WAIT_S
        left = [p for _r, p in targets]
        while left and self.clock() < deadline:
            left = [p for p in left if self.alive(p)]
            if not left:
                # GONE IS "TORN DOWN AND NO LONGER LISTED", NOT "HAS AN EXIT
                # CODE": self.alive is process_exists (the handle, measured
                # 1.61 s after the exit code on a 13 GB llama-server), and the
                # scan is asked once more. The next point must not start beside
                # a process that still holds the card.
                listed = {str(pid) for pid, _line in self.scan() or []}
                left = [p for _r, p in targets if p in listed]
            if left:
                self.sleep(0.25)
        took = self.clock() - began
        self._remove(path)
        names = {"serve": "serve", "image": "sd-server", "llama": "llama-server",
                 "video": "ComfyUI"}
        done = ", ".join("%s pid %s" % (names[r], p) for r, p in targets)
        if left:
            self.say("%s Asked %s to stop (%s), but pid %s is still there. End it by hand: %s"
                     % (self.style.icon("warn"), point_text,
                        done, ", ".join(left), " and ".join(kill_hint(p) for p in left)))
            return EXIT_FAILED
        self.say("%s Stopped %s (%s) in %.0f s."
                 % (self.style.icon("stop"), point_text, done, took))
        self._mention_strays(strays)
        return EXIT_OK

    def _mention_strays(self, strays) -> None:
        for pid in strays:
            self.say("   pid %s from the contract file is alive but is not a model server "
                     "process the scan can see, so it was left alone. If it is one: %s"
                     % (pid, kill_hint(pid)))

    def _remove(self, path: str) -> bool:
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    # -- start crow --------------------------------------------------------
    def gui_command(self, base_url: str) -> list:
        return [quiet_python(sys.executable), GUI_SCRIPT, "--base-url", base_url]

    def no_point_hint(self, running: "dict | None") -> str:
        lines = ["%s No operating point is running." % self.style.icon("nest"),
                 "   Start one of the three operating points first:"]
        titles = [(p.get("menu") or {}).get("title") or p.get("id") for p in self.stack["points"]]
        width = max(len(t) for t in titles)
        for title, p in zip(titles, self.stack["points"]):
            lines.append("     - %s  %s" % (title.ljust(width), (p.get("menu") or {}).get("line") or ""))
        if self.optional_lines():
            lines.append("   or one of the optional llama.cpp lines in the menu.")
        if running:
            lines.append("   (Running now: %s.)" % self.describe(running))
        return "\n".join(lines)

    def start_crow(self) -> int:
        """Open the window on what runs: a baseline point, or a llama-server.

        The hint only when no model server with an address runs at all (an
        sd-server alone, or a llama-server whose port cannot be read, has none).
        """
        running = self.detect()
        if not running or not running.get("base_url") or running["kind"] not in (
                crow_platform.KIND_CROW_NEST, crow_platform.KIND_LLAMA):
            self.say(self.no_point_hint(running))
            return EXIT_FAILED
        url = running["base_url"]
        env = dict(os.environ)
        if running["kind"] == crow_platform.KIND_LLAMA:
            what = self.describe(running)
        else:
            what = self.label(running.get("point"), running.get("variant"))
        if running["kind"] == crow_platform.KIND_CROW_NEST and running.get("point"):
            try:
                plan = plan_point(self.stack, running["point"], self.install, self.models)
                env.update(plan["crow_env"])
            except SetupError:
                pass
        try:
            proc = self._spawn(self.gui_command(url), cwd=os.getcwd(), env=env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        except OSError as exc:
            self.say("%s The window could not be started: %s" % (self.style.icon("fail"), exc))
            return EXIT_FAILED
        self.say("%s Crow is opening (pid %s), connected to %s at %s."
                 % (self.style.icon("crow"), proc.pid, what, url))
        return EXIT_OK

    # -- start crow on the Claude subscription (#398) ------------------------
    def claude_state(self, again: bool = False) -> dict:
        """Whether Crow can open on the Claude subscription: {state, detail, action}.

        crow_core's own facts, the first that holds wins: `guarded` (a guard
        variable would move the bill, crow_core.claude_cli_env_conflicts),
        `missing` (no Claude Code on PATH), `signed_out`, `billed` (signed in,
        but not on the subscription), `ready`. `action` is what may be offered:
        "sign_in" when signed out, "start" when ready, else None.

        THE PROBE SPAWNS TWO PROCESSES (`claude --version`, `claude auth
        status`) the first time and is then kept; `again` asks anew. The window
        asks off its UI thread. A guard variable needs no probe: it refuses
        whatever the probe would say.
        """
        names = crow_core.claude_cli_env_conflicts()
        if names:
            return {"state": "guarded", "detail": crow_core.claude_cli_guard_line(names),
                    "action": None}
        probe = crow_core.claude_probe(again)
        if not probe.get("found"):
            return {"state": "missing", "detail": crow_core.CLAUDE_CLI_MISSING, "action": None}
        if not probe.get("logged_in"):
            return {"state": "signed_out",
                    "detail": "Sign in once with your Claude subscription. Claude Code "
                              "opens Anthropic's sign-in in a terminal.",
                    "action": "sign_in"}
        method = probe.get("method") or ""
        if method not in ("claude.ai", "oauth_token"):
            return {"state": "billed",
                    "detail": crow_core.CLAUDE_SUB_SAYS.get(method)
                    or "Claude Code is signed in, but not with your subscription (%s)"
                    % (method or "no method"),
                    "action": None}
        return {"state": "ready",
                "detail": "Your Claude plan through Claude Code. No local model needed.",
                "action": "start"}

    def claude_sign_in(self, which=shutil.which) -> int:
        """Open a terminal the user types into, running `claude auth login`.

        ANTHROPIC'S OWN FLOW, UNMODIFIED: its terms ("Authentication and
        credential use", code.claude.com/docs/en/legal-and-compliance, read
        2026-10-15) allow the user to sign in to the unmodified Claude Code and
        forbid Crow to offer, collect or intermediate that sign-in. So Crow
        starts a terminal and nothing else: no argument of its own to claude,
        none of its output read, and the outcome learnt only from the next
        `claude auth status`. The sign-in may ask for a pasted code, so it needs
        a real terminal, not a hidden child.

        Windows: Windows Terminal (`wt.exe`) when it is on PATH, as the
        shortcut does, else a console of its own (CREATE_NEW_CONSOLE). Either
        runs `cmd.exe /k`: cmd finds `claude.cmd` (npm) as well as
        `claude.exe`, and keeps the window open on "Login successful". Linux:
        $TERMINAL, x-terminal-emulator, gnome-terminal, konsole, xterm, the
        first one found. EXIT_FAILED names the command to run by hand.
        """
        login = crow_core.CLAUDE_CLI_LOGIN.split()
        kw = {}
        argv = None
        if crow_platform.IS_WINDOWS:
            shell = ["cmd.exe", "/k"] + login
            terminal = which("wt") or which("wt.exe")
            if terminal:
                argv = [terminal] + shell
            else:
                argv = shell
                kw["creationflags"] = 0x00000010            # CREATE_NEW_CONSOLE
        else:
            for name in (os.environ.get("TERMINAL"), "x-terminal-emulator",
                         "gnome-terminal", "konsole", "xterm"):
                path = which(name) if name else None
                if path:
                    # gnome-terminal takes the command after `--`; the others after -e
                    run = ["--"] if os.path.basename(path) == "gnome-terminal" else ["-e"]
                    argv = [path] + run + login
                    break
        by_hand = "   Run it in a terminal yourself: %s" % crow_core.CLAUDE_CLI_LOGIN
        if argv is None:
            self.say("%s No terminal was found to sign in to Claude Code." % self.style.icon("fail"))
            self.say(by_hand)
            return EXIT_FAILED
        try:
            proc = self.popen(argv, **kw)
        except OSError as exc:
            self.say("%s The terminal could not be opened: %s" % (self.style.icon("fail"), exc))
            self.say(by_hand)
            return EXIT_FAILED
        self.say("%s Claude Code's sign-in is open in a terminal (pid %s). Finish it there."
                 % (self.style.icon("crow"), proc.pid))
        return EXIT_OK

    def start_claude(self, again: bool = False) -> int:
        """Open the window on the Claude subscription; no local model needed.

        Only in `ready` (claude_state; `again` asks Claude Code anew, as the
        menu does, else the kept probe); in any other state it says that
        state's sentence and changes nothing. Signed out, the sentence is the
        command to run: neither the menu nor `--start-claude` opens a terminal
        by itself (the window's Sign in does, claude_sign_in). Then
        providers.json's `active` is `claude` (crow_core.provider_pick; the
        window reads it at start) and the window opens like Start Crow, with
        `--base-url` of the model server that runs, else crow-nest's port: a
        point booted later from here is the local endpoint when the user
        switches back (Settings -> Model or `/model`; turns stay on Claude
        until then).
        """
        state = self.claude_state(again)
        if state["state"] == "signed_out":
            self.say("%s Claude Code is not signed in. Sign in once with your Claude subscription:"
                     % self.style.icon("fail"))
            self.say("     %s" % crow_core.CLAUDE_CLI_LOGIN)
            self.say("   then start Crow with Claude again.")
            return EXIT_FAILED
        if state["state"] != "ready":
            self.say("%s %s" % (self.style.icon("fail"), state["detail"]))
            return EXIT_FAILED
        running = self.detect()
        env = dict(os.environ)
        if running and running.get("base_url") and running["kind"] in (
                crow_platform.KIND_CROW_NEST, crow_platform.KIND_LLAMA):
            url = running["base_url"]
            if running["kind"] == crow_platform.KIND_CROW_NEST and running.get("point"):
                try:
                    env.update(plan_point(self.stack, running["point"], self.install,
                                          self.models)["crow_env"])
                except SetupError:
                    pass
        else:
            url = base_url_for(crow_core.CROW_NEST_PORT)
        problem = crow_core.provider_pick(crow_core.CLAUDE_PROVIDER)
        if problem:
            self.say("%s %s" % (self.style.icon("fail"), problem))
            return EXIT_FAILED
        try:
            proc = self._spawn(self.gui_command(url), cwd=os.getcwd(), env=env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        except OSError as exc:
            self.say("%s The window could not be started: %s" % (self.style.icon("fail"), exc))
            return EXIT_FAILED
        self.say("%s Crow is opening (pid %s) on %s; the local model is looked for at %s."
                 % (self.style.icon("crow"), proc.pid,
                    crow_core.PROVIDERS[crow_core.CLAUDE_PROVIDER]["label"], url))
        return EXIT_OK

    # -- status ------------------------------------------------------------
    def status(self) -> int:
        running = self.detect()
        if not running:
            self.say("%s No operating point is running." % self.style.icon("off"))
            return EXIT_FAILED
        self.say("%s Running: %s" % (self.style.icon("on"), self.describe(running)))
        if running.get("base_url"):
            self.say("   base URL  %s" % running["base_url"])
            model = self.model_path(running["base_url"])
            if model:
                self.say("   model     %s" % model)
        if running.get("since"):
            self.say("   since     %s" % running["since"])
        self.say("   found by  %s" % running["source"])
        return EXIT_OK

    def status_line(self) -> str:
        running = self.detect()
        if not running:
            return "%s %s" % (self.style.icon("off"), self.style.dim("No operating point is running."))
        return "%s %s" % (self.style.icon("on"), self.style.paint(self.describe(running), "32"))

    # -- the menu ----------------------------------------------------------
    def entries(self) -> list:
        """(key, icon, title, line, action, optional) in menu order.

        Start Crow, then Start Crow with Claude (subscription) (#398; its state
        is asked when it is chosen, not on every draw: the probe spawns two
        processes). The three baseline points from stack.json next, each variant (#397)
        on its own numbered line right under its base (action ("variant",
        (point, key))); below them, under a heading row (key "", action None),
        the installed optional llama.cpp lines, each tagged "(optional)" and
        drawn dimmed.
        """
        rows = [("1", "start", "Start Crow", "open the window on the running point",
                 ("crow", None), False),
                ("2", "start", "Start Crow with Claude (subscription)",
                 "open the window on your Claude plan, no local model needed",
                 ("claude", None), False)]
        for p in self.stack["points"]:
            if not runs_here(p):
                continue
            menu = p.get("menu") or {}
            icon = p.get("id") if p.get("id") in ICONS else "start"
            title = menu.get("title") or p.get("id")
            rows.append((str(len(rows) + 1), icon, title,
                         menu.get("line") or "", ("point", p.get("id")), False))
            for v in self.variants.get(p.get("id")) or []:
                rows.append((str(len(rows) + 1), icon, point_title(title, v.get("key")),
                             (v.get("menu") or {}).get("line") or "",
                             ("variant", (p.get("id"), v.get("key"))), False))
        n = len(rows)
        optional = self.optional_lines()
        if optional:
            rows.append(("", None, "Optional (llama.cpp)", "", None, True))
        for line in optional:
            n += 1
            rows.append((str(n), "optional", "%s (optional)" % line["title"],
                         "llama.cpp, port %d" % line["port"], ("point", line["key"]), True))
        rows.append((str(n + 1), "stop", "Stop the running point", "", ("stop", None), False))
        rows.append(("0", "quit", "Quit", "", ("quit", None), False))
        return rows

    def draw(self) -> None:
        if self.style.animate:
            self.out.write("\x1b[2J\x1b[H")
        s = self.style
        self.say()
        self.say("  %s  %s" % (s.icon("crow"), s.bold("C R O W") + s.dim("  boot menu")))
        self.say("  " + s.dim("-" * 52))
        self.say("  " + self.status_line())
        self.say()
        rows = self.entries()
        width = max(len(r[2]) for r in rows if r[0])
        after_optional = False
        for key, icon, title, line, action, optional in rows:
            # #397: the variant rows reach 10 and up; a two-digit key takes one
            # of the three leading blanks, so the icons stay in one column.
            lead = " " * max(1, 4 - len(key))
            if action is None:                      # the "Optional (llama.cpp)" heading
                self.say()
                self.say("  " + s.dim(title))
            elif optional:
                self.say(("%s%s  %s %s" % (lead, s.dim(key), s.icon(icon),
                                           s.dim("%s  %s" % (title.ljust(width), line)))).rstrip())
            else:
                if after_optional:
                    self.say()
                self.say(("%s%s  %s %s  %s" % (lead, s.bold(key), s.icon(icon), title.ljust(width),
                                              s.dim(line))).rstrip())
            after_optional = optional
        self.say()
        if self._note:
            self.say("  " + s.paint(self._note, "33"))
            self._note = ""

    def menu(self) -> int:
        while True:
            self.draw()
            try:
                # lstrip the BOM: PowerShell prefixes one to text it pipes in.
                choice = self.read("  Choose: ").strip().lstrip("﻿").lower()
            except (EOFError, KeyboardInterrupt):
                self.say()
                return EXIT_OK
            action = next((r[4] for r in self.entries() if r[0] and r[0] == choice), None)
            if choice in ("q", "quit", "exit"):
                action = ("quit", None)
            if action is None:
                self._note = "Unknown choice %r -- type one of the numbers." % choice
                continue
            what, arg = action
            self.say()
            if what == "quit":
                self.say("  %s Bye." % self.style.icon("quit"))
                return EXIT_OK
            if what == "crow":
                if self.start_crow() == EXIT_OK:
                    self.countdown(OPENED_S, "Back to the menu")
                else:
                    self.pause()
            elif what == "claude":
                # asked anew: a sign-in in another terminal since the last ask counts
                if self.start_claude(again=True) == EXIT_OK:
                    self.countdown(OPENED_S, "Back to the menu")
                else:
                    self.pause()
            elif what == "point":
                if self.start(arg, interactive=True) != EXIT_OK:
                    self.pause()
            elif what == "variant":
                if self.start(arg[0], interactive=True, variant=arg[1]) != EXIT_OK:
                    self.pause()
            elif what == "stop":
                self.stop()
                self.pause()

    # -- the shortcut ------------------------------------------------------
    def shortcut_spec(self, folder: str, which=shutil.which, gui: bool = False) -> dict:
        """What `--create-shortcut` writes: this menu, or with `gui` the window.

        The window runs under pythonw.exe (no console) with `--gui`; the menu
        runs under the console interpreter, in Windows Terminal when there is one.
        """
        python = sys.executable
        if crow_platform.IS_WINDOWS and os.path.basename(python).lower() == "pythonw.exe":
            console = os.path.join(os.path.dirname(python), "python.exe")
            if os.path.isfile(console):
                python = console
        script = os.path.abspath(__file__)
        forwarded = [_quote(a) for a in self.forwarded_args]
        if gui:
            return {"path": os.path.join(os.path.abspath(folder), "Crow.lnk"),
                    "target": quiet_python(python),
                    "arguments": " ".join([_quote(script), "--gui"] + forwarded),
                    "workdir": self.install,
                    "icon": ICON_FILE if os.path.isfile(ICON_FILE) else "",
                    "description": "Crow: start a model, then open the Crow window"}
        tail = [_quote(python), _quote(script)] + forwarded
        terminal = which("wt") or which("wt.exe")
        if terminal:
            target = terminal
            args = " ".join(["--title", "Crow", "-d", _quote(self.install)] + tail)
        else:
            target = python
            args = " ".join(tail[1:])
        return {"path": os.path.join(os.path.abspath(folder), "Crow.lnk"),
                "target": target, "arguments": args, "workdir": self.install,
                "icon": ICON_FILE if os.path.isfile(ICON_FILE) else "",
                "description": "Crow boot menu: start an operating point, then Crow"}

    def create_shortcut(self, folder: str, run=subprocess.run, which=shutil.which,
                        terminal: bool = False) -> int:
        if not crow_platform.IS_WINDOWS:
            self.say("%s --create-shortcut writes a Windows .lnk; on this platform start "
                     "the menu with: python %s" % (self.style.icon("fail"), os.path.abspath(__file__)))
            return EXIT_SETUP
        # PowerShell hands "%USERPROFILE%\Desktop" over unexpanded; cmd and the
        # docs spell it that way, so the folder is expanded here, ~ as well
        folder = os.path.expanduser(os.path.expandvars(folder))
        if not os.path.isdir(folder):
            self.say("%s no such folder: %s" % (self.style.icon("fail"), folder))
            return EXIT_SETUP
        spec = self.shortcut_spec(folder, which, gui=not terminal)
        script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:CROW_LNK_PATH); "
                  "$s.TargetPath = $env:CROW_LNK_TARGET; $s.Arguments = $env:CROW_LNK_ARGS; "
                  "$s.WorkingDirectory = $env:CROW_LNK_DIR; $s.Description = $env:CROW_LNK_DESC; "
                  "if ($env:CROW_LNK_ICON) { $s.IconLocation = $env:CROW_LNK_ICON + ',0' }; "
                  "$s.Save()")
        env = dict(os.environ, CROW_LNK_PATH=spec["path"], CROW_LNK_TARGET=spec["target"],
                   CROW_LNK_ARGS=spec["arguments"], CROW_LNK_DIR=spec["workdir"],
                   CROW_LNK_DESC=spec["description"], CROW_LNK_ICON=spec["icon"])
        done = run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-Command", script], env=env, capture_output=True, text=True,
                   stdin=subprocess.DEVNULL, timeout=60)
        if done.returncode != 0 or not os.path.isfile(spec["path"]):
            self.say("%s the shortcut could not be written: %s"
                     % (self.style.icon("fail"), (done.stderr or done.stdout or "").strip()))
            return EXIT_FAILED
        self.say("%s Shortcut written: %s" % (self.style.icon("crow"), spec["path"]))
        self.say("   target: %s %s" % (spec["target"], spec["arguments"]))
        return EXIT_OK


# ------------------------------------------------------------------- main ---

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Crow's boot menu: start an operating point, then Crow.")
    ap.add_argument("--install-root", help="Crow's install root (default: the installer's)")
    ap.add_argument("--models", help="the models root of the three points (default: $CROW_MODELS, "
                                     "else <install>/models); the llama.cpp lines keep $CROW_MODELS when set")
    ap.add_argument("--stack", help="manifests/stack.json (default: beside cli/)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true", help="say what runs (exit 0) or not (exit 1)")
    group.add_argument("--start", metavar="POINT", help="start one operating point")
    group.add_argument("--stop", action="store_true", help="stop the running operating point")
    group.add_argument("--start-crow", action="store_true", help="open the window on the running point")
    group.add_argument("--start-claude", action="store_true",
                       help="open the window on your Claude subscription (Claude Code), no local model needed")
    group.add_argument("--gui", action="store_true", help="the operating-point window instead of this menu")
    group.add_argument("--create-shortcut", metavar="DIR",
                       help="write a Windows shortcut to the operating-point window")
    group.add_argument("--plan", metavar="POINT", help="print what --start POINT would use (needs --json)")
    ap.add_argument("--json", action="store_true", help="with --plan: the plan as JSON on stdout")
    ap.add_argument("--terminal", action="store_true",
                    help="with --create-shortcut: the shortcut opens this terminal menu instead")
    ap.add_argument("--variant", metavar="KEY",
                    help="with --start: one of the point's variants (text: without the vision tower)")
    args = ap.parse_args(argv)
    if bool(args.plan) != bool(args.json):
        ap.error("--plan and --json go together: --plan POINT --json")
    if args.terminal and not args.create_shortcut:
        ap.error("--terminal goes with --create-shortcut DIR")
    if args.variant and not args.start:
        ap.error("--variant goes with --start POINT")

    style = Style.detect(sys.stdout)
    install = os.path.abspath(args.install_root) if args.install_root else crow_platform.install_dir()
    models = os.path.abspath(args.models) if args.models else crow_platform.models_dir(install)
    if args.models:
        # The optional llama.cpp lines resolve through crow_platform.models_dir,
        # which reads CROW_MODELS: without one, --models serves them too; one the
        # user set (a lab root for those lines) stays theirs. CrowSetup always
        # passes --models <install>/models, so it never moves either (#196 P2-E2E).
        os.environ.setdefault("CROW_MODELS", models)
    forwarded = []
    for flag, value in (("--install-root", args.install_root and install),
                        ("--models", args.models and models),
                        ("--stack", args.stack and os.path.abspath(args.stack))):
        if value:
            forwarded += [flag, value]
    try:
        stack = load_stack(os.path.abspath(args.stack) if args.stack else DEFAULT_STACK)
    except SetupError as exc:
        print("%s %s" % (style.icon("fail"), exc), file=sys.stderr if args.plan else sys.stdout)
        return EXIT_SETUP
    if args.plan:
        # stdout carries the JSON and nothing else; a setup error goes to stderr
        try:
            doc = plan_json(stack, args.plan, install, models)
        except SetupError as exc:
            print("%s %s" % (style.icon("fail"), exc), file=sys.stderr)
            return EXIT_SETUP
        sys.stdout.write(json.dumps(doc, indent=2) + "\n")
        return EXIT_OK
    boot = Boot(stack, install, models, style=style, forwarded_args=forwarded)
    if args.status:
        return boot.status()
    if args.start:
        return boot.start(args.start, variant=args.variant)
    if args.stop:
        return boot.stop()
    if args.start_crow:
        return boot.start_crow()
    if args.start_claude:
        return boot.start_claude()
    if args.create_shortcut:
        return boot.create_shortcut(args.create_shortcut, terminal=args.terminal)
    if args.gui:
        import crow_boot_gui
        return crow_boot_gui.open_window(boot)
    return boot.menu()


if __name__ == "__main__":
    sys.exit(main())
