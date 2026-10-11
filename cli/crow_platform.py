#!/usr/bin/env python3
r"""The one place in Crow that knows which operating system this is.

WHY A MODULE AND NOT TWENTY `if sys.platform == "win32"`. The port to Linux
touched paths, process discovery, spawning, killing, the shell, the browser and
the font store -- seven facts about an OS, each of which was written down where
it happened to be needed. Seven scattered branches are seven places to forget.
This file is the seam: every OS-dependent fact is answered here, the core asks
and does not branch, and a reader who wants to know what changes between the two
platforms reads ONE file.

WHY THE NAME IS `crow_platform` AND NOT `platform`. `python cli/crow_gui.py`
puts cli/ on sys.path[0], so a file called cli/platform.py would shadow the standard
library's `platform` module for every client that starts from this directory --
the same trap crow_core.py's own docstring records for cli/json.py.

STANDARD LIBRARY ONLY, like the core: the core's stdlib-only invariant runs
through here, and `/proc` plus `shutil.which` answer everything
`psutil` would have.

THE LAYOUT, and Windows does not move:

    what                       Windows (unchanged)          Linux
    ------------------------------------------------------------------------
    install root               %LOCALAPPDATA%\Crow          ~/.local/share/crow
    secrets.json, settings,    %LOCALAPPDATA%\Crow\...      ~/.config/crow/...
      roots.json, USER.md,
      skills/, mcp.json,
      providers.json,
      approvals.json
    index.db (session search)  %LOCALAPPDATA%\Crow\...      ~/.local/share/crow/...
    session/, booted.json,     %LOCALAPPDATA%\Crow\...      ~/.local/state/crow/...
      git_events.json
    llama-server boot logs     <cwd>\runs\                  ~/.local/state/crow/log/
    crow.log (Crow's own)      %LOCALAPPDATA%\Crow\log\     ~/.local/state/crow/log/
    models                     <install>\models             $CROW_MODELS, else
                                                            <install>/models
    llama-server binary        <install>\bin\               <install>/bin/, then
      llama-server.exe                                      PATH, then
                                                            ~/.local/share/crow/bin
    fonts                      %LOCALAPPDATA%\Microsoft\    ~/.local/share/fonts/
                                 Windows\Fonts + winreg       crow/ + fc-cache

Every XDG variable is honoured when it is set and absolute, which is what the
specification asks for; an empty or relative value is treated as unset, because
a relative "base directory" resolves against whatever directory the window was
started from -- exactly the class of bug #177 closed for the working area.

WHAT IS DELIBERATELY NOT HERE: anything that decides product behaviour. This
module answers "where" and "how", never "whether". A refusal, a wording or a
release level is the core's, and a platform file that started answering those
would be a second core.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

# The directory name, and it differs by platform on purpose: `Crow` is what
# install.ps1 has always created under %LOCALAPPDATA%, and a lower-case name
# is what every other XDG directory beside it is spelled like.
APP_DIR_WINDOWS = "Crow"
APP_DIR_XDG = "crow"


def _home() -> str:
    return os.path.expanduser("~")


def _windows_base() -> str:
    """`%LOCALAPPDATA%\\Crow` -- install.ps1's own `$InstallTo` default.

    The fallback fires only where LOCALAPPDATA is unset, which on Windows means
    a stripped service environment rather than a user session.
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        _home(), "AppData", "Local")
    return os.path.join(base, APP_DIR_WINDOWS)


def _xdg_base(variable: str, default_tail: tuple[str, ...]) -> str:
    """`$<variable>`, or the specification's default below ~.

    A value that is not an ABSOLUTE path is ignored, as the specification says:
    "If an implementation encounters a relative path it should consider it
    invalid". The alternative is a base directory that moves with the cwd.
    """
    raw = os.environ.get(variable) or ""
    if raw and os.path.isabs(raw):
        return raw
    return os.path.join(_home(), *default_tail)


def _xdg(variable: str, default_tail: tuple[str, ...]) -> str:
    """`$<variable>/crow` -- Crow's own directory under one XDG base."""
    return os.path.join(_xdg_base(variable, default_tail), APP_DIR_XDG)


def data_dir() -> str:
    """User data that would hurt to lose: the search index, the install itself."""
    return _windows_base() if IS_WINDOWS else _xdg("XDG_DATA_HOME", (".local", "share"))


def config_dir() -> str:
    """What the user configured: secrets, settings, roots, skills, MCP, providers."""
    return _windows_base() if IS_WINDOWS else _xdg("XDG_CONFIG_HOME", (".config",))


def state_dir() -> str:
    """State that outlives a run and nobody backs up: sessions, logs, boots."""
    return _windows_base() if IS_WINDOWS else _xdg("XDG_STATE_HOME", (".local", "state"))


def webview_start_kwargs() -> dict:
    """#326: what `webview.start` gets on Windows so a login survives a restart.

    pywebview defaults `private_mode=True` (nothing kept between sessions) and
    keeps its profile in `%APPDATA%/pywebview`, shared with other pywebview apps.
    Both are process-wide, so this holds for Crow's page and the browser panel
    alike. Crow's own folder under `state_dir()`. Linux has its own WebKit
    profile for the panel (#226) and needs none of this: empty there.
    """
    if not IS_WINDOWS:
        return {}
    return {"private_mode": False,
            "storage_path": os.path.join(state_dir(), "webview")}


# #368. THE WINDOW RENDERS WITHOUT THE GPU. The WebView2 loader reads this
# variable when it creates an environment and APPENDS it to the arguments
# pywebview passes (learn.microsoft.com, CreateCoreWebView2EnvironmentWithOptions).
WEBVIEW2_ARGS_ENV = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"
WEBVIEW2_NO_GPU = "--disable-gpu --disable-gpu-compositing"


def webview_without_gpu(environ=None) -> None:
    """#368: before `import webview`, in every process that opens a window.

    The window renders without the GPU so WebView2 does not time-slice the
    card with the local engine's CUDA kernels (GLM-5.3-Flash in the window:
    14.17 tok/s with the flag, 7.6-8.3 without, 2026-10-11). An explicit
    value in the environment is kept. Linux (WebKitGTK) is untouched."""
    environ = os.environ if environ is None else environ
    if IS_WINDOWS:
        environ.setdefault(WEBVIEW2_ARGS_ENV, WEBVIEW2_NO_GPU)


def browser_env(environ=None) -> dict:
    """#368: the environment for render_page's own headless browser.

    The window's WebView2 switch is not the render's: the render picks its GPU
    or SwiftShader flags itself (#213/#293, `render_gpu_flags`), so the
    variable the window set for its WebView2 is dropped here."""
    env = dict(os.environ if environ is None else environ)
    for key in [k for k in env if k.upper() == WEBVIEW2_ARGS_ENV]:
        del env[key]
    return env


def cache_dir() -> str:
    """Throwaway: anything here may be deleted between two starts."""
    return _windows_base() if IS_WINDOWS else _xdg("XDG_CACHE_HOME", (".cache",))


def user_cache_base() -> str:
    """The XDG cache BASE (`$XDG_CACHE_HOME`, else ~/.cache), without Crow's name.

    For the caches OTHER programs keep there -- deno's is `<base>/deno`. #274:
    build_bundle joined `cache_dir()` with "deno" and looked in ~/.cache/crow/deno,
    where no deno ever wrote, and missed the esbuild in ~/.cache/deno.
    POSIX only; Windows callers use %LOCALAPPDATA% directly.
    """
    return _xdg_base("XDG_CACHE_HOME", (".cache",))


def install_dir() -> str:
    """Where the installer puts an installation -- its default, not a guess.

    Windows: `%LOCALAPPDATA%\\Crow`, install.ps1's `$InstallTo` default and the
    path its own documentation names. Linux: install.sh's default is the XDG
    data directory, so the install root IS data_dir(). Nothing is written
    outside the user's own tree on either platform, so no elevation and no sudo
    is involved anywhere in this path.
    """
    return _windows_base() if IS_WINDOWS else data_dir()


def log_dir() -> str:
    """Where a server boot writes its .out.log and .err.log.

    WINDOWS KEEPS `runs\\` UNDER THE CURRENT DIRECTORY, which is the owner's Ansage
    vom 2026-08-28: the traces of a Crow boot lie beside the ones the B5 runs
    already write, not under a random name in %TEMP% that nobody finds after a
    crash. On Linux the window is started from a desktop entry and the current
    directory is then the user's home or `/` -- a `runs/` folder appearing there
    is litter, and the XDG answer for "logs" is the state directory.
    """
    if IS_WINDOWS:
        return os.path.join(os.getcwd(), "runs")
    return os.path.join(state_dir(), "log")


def models_dir(install: str | None = None) -> str:
    """The root every `models.entries.path` in the manifest resolves under.

    `$CROW_MODELS` FIRST, because a model tree is the one part of an install
    that a user moves: 80-110 GiB do not belong beside the program, and on this
    machine they live under ~/Projects/models while the install is in
    ~/.local/share/crow. There is no copy of it in a settings file, because a
    path that two places can set is a path nobody can find.

    Absent the variable this is `<install>/models`, which is exactly what
    model_candidates has always used -- and on Linux that is where install.sh
    puts a SYMLINK to the chosen tree, so every entry point (the window,
    tools/start-server.py, a terminal) finds the model with no variable set.
    The variable is the override for one shell; the link is the install.
    """
    raw = (os.environ.get("CROW_MODELS") or "").strip()
    if raw:
        # expanduser so `CROW_MODELS=~/Projects/models` works from a shell
        # profile that did not expand it; a symlinked tree is followed by the
        # filesystem and needs nothing here.
        return os.path.expanduser(raw)
    return os.path.join(install or install_dir(), "models")


# ------------------------------------------------------------- the server ---

def server_binary_name() -> str:
    return "llama-server.exe" if IS_WINDOWS else "llama-server"


def server_search_dirs(install: str | None = None) -> list[str]:
    """Where a llama-server may sit, in order, WITHOUT looking at PATH.

    `<install>/bin` first, and PATH after it (see find_server_binary): a package
    that ships its own binary must not be overtaken by whatever happens to be on
    a developer's PATH -- that is how a measurement ends up describing a build
    nobody shipped.

    On Linux the XDG install's own bin/ is searched EVEN WHEN `install` points
    somewhere else, because that is where install.sh and the llama.cpp build
    both land the binary while Crow itself is usually run from a checkout.
    """
    out = [os.path.join(install or install_dir(), "bin")]
    if not IS_WINDOWS:
        packaged = os.path.join(data_dir(), "bin")
        if packaged not in out:
            out.append(packaged)
    return out


def find_server_binary(install: str | None = None) -> tuple[str | None, list[str]]:
    """The llama-server this build would run, and everywhere it looked.

    The list is RETURNED rather than reduced to the first hit, for the reason
    model_candidates gives: a failure that says only "not found" cannot tell a
    wrong table from a missing download.
    """
    name = server_binary_name()
    tried: list[str] = []
    for directory in server_search_dirs(install):
        candidate = os.path.join(directory, name)
        tried.append(candidate)
        if os.path.isfile(candidate):
            return candidate, tried
    tried.append("PATH")
    found = shutil.which("llama-server") or shutil.which("llama-server.exe")
    return found, tried


def binary_is_for_this_os(path: str) -> bool:
    """Could this spelling of a path name a program on THIS platform?

    #140 lets a server line name its own binary, and the flash-next line names
    `bin\\llama-server.exe`. On Windows a missing
    binary at that path is ITS OWN error -- falling back would boot a build that
    cannot load the architecture. On Linux the same string is not a statement
    about this machine at all: it is a Windows path, it can never exist here,
    and the honest reading is "this line was written on the other platform", not
    "the binary is missing". So the caller falls back to the search above.

    The question is asked of the SPELLING, not of the disk: a drive letter or a
    backslash is Windows, a leading `/` is POSIX.
    """
    text = (path or "").strip()
    if not text:
        return False
    drive = len(text) > 1 and text[1] == ":" and text[0].isalpha()
    windows_shaped = drive or text.startswith("\\\\") or "\\" in text
    if IS_WINDOWS:
        # A POSIX-absolute path is not a Windows path -- but a bare relative
        # name is fine on both, so only the leading slash disqualifies it.
        return not (text.startswith("/") and not drive)
    return not windows_shaped


# The Windows process list, and it is a PowerShell query because there is no
# /proc: Get-CimInstance is the documented way to a command line, and tasklist
# does not print one. Moved here from crow_core.py with its behaviour intact.
# #196 C3: it also asks for crow-nest's `serve.exe` and the image server
# `sd-server.exe`, which hold the card just as firmly as a llama-server does.
# #340: ComfyUI is a python.exe, so it is asked for by the main.py on its line.
_PROCESS_QUERY = ("Get-CimInstance Win32_Process -Filter \"Name like 'llama-server%'"
                  " or Name = 'serve.exe' or Name like 'sd-server%'"
                  " or (Name like 'python%' and CommandLine like '%ComfyUI%main.py%')\""
                  " | ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")

# #196 C3: the three kinds of server the scan reports, named by executable.
KIND_LLAMA = "llama-server"
KIND_CROW_NEST = "crow-nest"     # serve.exe, both crow-nest operating points
KIND_IMAGE = "image"             # sd-server.exe
KIND_VIDEO = "video"             # #340: ComfyUI, a python running ComfyUI/main.py
# The port each listens on when its command line names none: serve.rs
# DEFAULT_PORT 8099; sd.cpp examples/server/runtime.h listen_port 1234;
# ComfyUI comfy/cli_args.py --port 8188.
# llama-server's own default is not assumed -- discovery has always read --port.
_DEFAULT_PORTS = {KIND_CROW_NEST: 8099, KIND_IMAGE: 1234, KIND_VIDEO: 8188}
_PORT_FLAGS = {KIND_LLAMA: "--port", KIND_CROW_NEST: "--port",
               KIND_IMAGE: "--listen-port", KIND_VIDEO: "--port"}
# ComfyUI's entry point as a whole word of the line: `ComfyUI\main.py` from the
# portable folder, `/opt/.../ComfyUI/main.py` on Linux. A python running some
# other main.py is not a server.
_COMFYUI_MAIN = re.compile(r'(?:^|[\s"\\/])ComfyUI[\\/]main\.py(?:["\s]|$)')


def _is_comfyui(command_line: str) -> bool:
    """#340: a python interpreter whose line runs ComfyUI's main.py."""
    return (_executable_name(command_line).lower().startswith("python")
            and _COMFYUI_MAIN.search(command_line or "") is not None)


def _kind_of_name(name: str) -> "str | None":
    """The kind for an executable's base name, or None for anything else.

    `serve` is matched EXACTLY: the name is generic, and only crow-nest's
    binary carries it bare. The other two keep the prefix match the Windows
    query has always used (`llama-server%`).
    """
    name = name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if name.startswith("llama-server"):
        return KIND_LLAMA
    if name == "serve":
        return KIND_CROW_NEST
    if name.startswith("sd-server"):
        return KIND_IMAGE
    return None


_EXE_WITH_SPACES = re.compile(r'\s*"?([^"]*?\.exe)(?=["\s]|$)', re.IGNORECASE)


def _base_name(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _executable_name(command_line: str) -> str:
    """The base name of the program a command line starts.

    A quoted first token is the program; otherwise the first word is, unless
    it names no server and the line holds an unquoted Windows path with a
    space (`C:\\Program Files\\...\\serve.exe`) -- then that path up to `.exe`.
    """
    text = (command_line or "").strip()
    if text.startswith('"'):
        return _base_name(text[1:].split('"', 1)[0])
    exe = (text.split(None, 1) or [""])[0]
    if _kind_of_name(_base_name(exe)) is None:
        hit = _EXE_WITH_SPACES.match(text)
        if hit:
            exe = hit.group(1)
    return _base_name(exe)


def server_kind(command_line: str) -> "str | None":
    """#196 C3: which server a scanned command line is -- KIND_LLAMA,
    KIND_CROW_NEST, KIND_IMAGE -- or None.

    Read off the EXECUTABLE, so notepad with serve.log open is not a server.
    A line that merely mentions llama-server still counts as one: that is what
    the listing reader has always accepted, and it is kept unchanged.
    """
    kind = _kind_of_name(_executable_name(command_line))
    if kind is None and "llama-server" in (command_line or ""):
        return KIND_LLAMA
    if kind is None and _is_comfyui(command_line):
        return KIND_VIDEO
    return kind


def server_port(command_line: str) -> "int | None":
    """The port a scanned server listens on, where it can be derived: its own
    flag, else its kind's default (none for llama-server)."""
    kind = server_kind(command_line)
    if kind is None:
        return None
    hit = re.search(r"(?:^|\s)%s[\s=]+(\d+)" % re.escape(_PORT_FLAGS[kind]),
                    command_line)
    return int(hit.group(1)) if hit else _DEFAULT_PORTS.get(kind)

# The POSIX fallback, used only where /proc cannot be read (a container with it
# unmounted, a BSD). `ps` is a subprocess; /proc is four file reads and no fork.
_PS_ARGV = ["ps", "-eo", "pid=,args="]


def _quote(arg: str) -> str:
    """Put an argument back the way a command line would have carried it.

    /proc splits the arguments for us, and the core's `-m` reader expects the
    shape a command LINE has -- so a path with a space goes back in quotes
    rather than being handed over as two tokens.
    """
    return '"%s"' % arg if (" " in arg or "\t" in arg) else arg


def _proc_servers(proc_root: str = "/proc") -> "list[tuple[str, str]] | None":
    """Every server in /proc (llama-server, crow-nest's serve, sd-server), or
    None when /proc cannot be read.

    None IS NOT AN EMPTY LIST HERE. "No /proc" and "no server" are different
    answers and the caller does different things with them: the first falls back
    to `ps`, the second refuses to start a second server. Collapsing them would
    make an unreadable /proc look like a free card.
    """
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return None
    mine = str(os.getpid())
    out: list[tuple[str, str]] = []
    for pid in entries:
        if not pid.isdigit() or pid == mine:
            continue
        try:
            with open(os.path.join(proc_root, pid, "cmdline"), "rb") as fh:
                raw = fh.read()
        except OSError:
            continue                      # the process ended, or is not ours
        if not raw:
            continue                      # a kernel thread has no command line
        args = [a.decode("utf-8", "replace")
                for a in raw.split(b"\0") if a]
        if not args:
            continue
        # THE NAME IS READ OFF argv[0] AND NOT OFF THE WHOLE LINE, which is the
        # same narrowing the Windows query gets from `Name like 'llama-server%'`:
        # a text editor with llama-server.log open is not a server, and a
        # measurement script that mentions one is not one either.
        line = " ".join(_quote(a) for a in args)
        if _kind_of_name(os.path.basename(args[0])) is None and not _is_comfyui(line):
            continue
        out.append((pid, line))
    return out


def _run_query(argv: list[str]) -> str:
    # stdin=DEVNULL, AND IT IS NOT TIDINESS. Without it the child inherits this
    # process's stdin, and `powershell -Command` READS it: measured 2026-08-21,
    # a picker that asked which model to start got EOF instead of the answer,
    # because listing the processes had already swallowed it.
    done = subprocess.run(argv, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL,
                          encoding="utf-8", errors="replace", timeout=60, **no_console_kwargs())
    return done.stdout if done.returncode == 0 else ""


def _parse_process_table(text: str) -> list[tuple[str, str]]:
    """`<pid>\\t<command line>` (or `<pid> <command line>`) into pairs."""
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        pid, _, rest = line.partition("\t")
        if not rest:
            pid, _, rest = line.partition(" ")
        if server_kind(rest) is None:
            continue
        out.append((pid.strip(), rest.strip()))
    return out


def find_servers(query=None, proc_root: str = "/proc") -> list[tuple[str, str]]:
    """Every model server on this machine, as (pid, command line): each
    llama-server, crow-nest's serve and the image server sd-server (#196 C3).
    `server_kind` and `server_port` read a line's kind and port.

    An unreadable process list comes back EMPTY rather than raising: the caller
    runs this on the path that starts a server, and refusing to boot because a
    query failed would trade a rare risk for a certain one.

    `query` is the injection point for a test and for `running_servers`: any
    callable returning the text a process listing prints.
    """
    if query is None:
        if not IS_WINDOWS:
            found = _proc_servers(proc_root)
            if found is not None:
                return found
            argv = _PS_ARGV
        else:
            argv = ["powershell", "-NoProfile", "-NonInteractive",
                    "-Command", _PROCESS_QUERY]

        def query():
            return _run_query(argv)
    try:
        return _parse_process_table(query())
    except Exception:
        return []


# ---------------------------------------------------- spawning and killing ---

def no_console_kwargs() -> dict:
    """The subprocess.run keywords for a short helper (a query, taskkill).

    The owner's live test 2026-10-01: the operating-point window runs under
    pythonw, which has no console, so every console program it started (the
    process scan every 5 s, taskkill on Stop, nvidia-smi) opened a console
    window of its own in the foreground. CREATE_NO_WINDOW starts it without one.
    Linux: nothing to do.
    """
    if IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def spawn_kwargs(detached: bool = True) -> dict:
    r"""The Popen keywords that keep a server out of the console that bore it.

    #158, AND IT WAS THE ROOT OF THE SILENT DEATHS. Without these a llama-server
    inherits the console AND the process group of the window, and a Ctrl+C in
    the terminal the window was started from -- an aborted `Get-Content -Wait`,
    a finished measurement run -- hits the server too. It then shuts down
    cleanly with exit code 1, no error line, no dump: the "silent exit-1 class"
    that was blamed on the driver, the compute cache and the PR build in turn.

    Windows: CREATE_NEW_PROCESS_GROUP takes it out of the signal group,
    CREATE_NO_WINDOW out of the console (the second half is for CTRL_CLOSE_EVENT,
    which a closing console sends to everyone attached).

    Linux: `start_new_session=True` is setsid(), which is both halves at once --
    a new session has its own process group, so SIGINT from the terminal does
    not reach it, and it has no controlling terminal to be hung up by.
    """
    if not detached:
        return {}
    if IS_WINDOWS:
        return {"creationflags": (subprocess.CREATE_NEW_PROCESS_GROUP
                                  | getattr(subprocess, "CREATE_NO_WINDOW", 0))}
    return {"start_new_session": True}


_SCOPE_HEADROOM_GIB = 8


def _mem_total_bytes(meminfo: str = "/proc/meminfo") -> int:
    try:
        with open(meminfo, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def server_memory_bounds(mem_total: int | None = None) -> dict:
    """The memory properties the server's scope gets, as systemd sizes.

    MemorySwapMax=0 always: the server's anonymous memory may not be swapped
    or compressed into zram -- under vm.swappiness=150 that is exactly what the
    kernel did with the experts, and a server whose weights sit in zram is the
    freeze the desktop felt. Without swap the kernel reclaims the server's clean
    page cache instead, and if the anonymous part truly does not fit, the kernel
    ends the server alone inside its scope, not the desktop.

    MemoryHigh = RAM minus 10 GiB, MemoryMax = RAM minus 8 GiB: at 62 GiB that is
    52 and 54, above the ~48 GiB the measured line keeps on the CPU under
    --load-mode none and well above the few GiB it keeps under mmap, and it
    leaves the desktop 8 GiB before the server is throttled. Below 16 GiB of
    RAM there is no bound to give. $CROW_SERVER_MEMORY_HIGH moves MemoryHigh
    (any systemd size); `none` drops both size bounds, the swap cap stays.
    """
    out = {"MemorySwapMax": "0"}
    raw = (os.environ.get("CROW_SERVER_MEMORY_HIGH") or "").strip()
    if raw.lower() in ("0", "none", "off"):
        return out
    total = mem_total if mem_total is not None else _mem_total_bytes()
    gib = total // (1024 ** 3)
    if gib >= 16:
        out["MemoryHigh"] = "%dG" % (gib - _SCOPE_HEADROOM_GIB - 2)
        out["MemoryMax"] = "%dG" % (gib - _SCOPE_HEADROOM_GIB)
    if raw:
        out["MemoryHigh"] = raw
    return out


def user_manager_reachable(runtime_dir: str | None = None) -> bool:
    """Can `systemd-run --user` reach the user's service manager from here?

    A FILE CHECK, NOT A PROBE PROCESS. `systemd-run --user` talks to the user
    manager over $XDG_RUNTIME_DIR/systemd/private; when that socket is there
    the call goes through, when it is not (a container, an SSH session without
    a session, a CI runner) it fails at once. Reading the socket's presence
    answers the same question without starting anything -- which matters
    because the boot is exercised in the suites with a Popen that is a fake.
    """
    base = runtime_dir if runtime_dir is not None else os.environ.get("XDG_RUNTIME_DIR", "")
    if not base:
        return False
    try:
        import stat
        return stat.S_ISSOCK(os.stat(os.path.join(base, "systemd", "private")).st_mode)
    except OSError:
        return False


_RENDER_MEMORY_DEFAULT = "6G"


def render_memory_bounds() -> dict:
    """The memory properties the render browser's scope gets, as systemd sizes.

    #213. The 2026-09-21 incident: a software-WebGL render of the 2 MB three.js
    page grew its headless chromium to 54 GiB, the desktop froze, and the
    kernel's OOM killer shot the ENGINE -- the browser sat in no cgroup of its
    own, so "largest process" was answered with somebody else's server.
    MemoryMax=6G kills that runaway one ninth of the way up while leaving a
    healthy software render of the same page ten times its usual size to
    finish; MemoryHigh one below it makes the kernel reclaim first. The swap
    cap carries the server's reason unchanged: on this machine's zram the
    browser's anonymous memory is the freeze, and without the cap it goes
    exactly there. $CROW_RENDER_MEMORY_MAX moves the kill bound (any systemd
    size); `none` drops the size bounds and keeps the swap cap.
    """
    out = {"MemorySwapMax": "0"}
    raw = (os.environ.get("CROW_RENDER_MEMORY_MAX") or "").strip()
    if raw.lower() in ("0", "none", "off"):
        return out
    if raw:
        out["MemoryMax"] = raw
        return out
    out["MemoryHigh"] = "5G"
    out["MemoryMax"] = _RENDER_MEMORY_DEFAULT
    return out


def server_scope_prefix() -> list[str]:
    """What to put in front of llama-server's argv so it runs in its own scope.

    MEASURED 2026-09-16 ON OMARCHY, four times between 17:42 and 17:56: the
    server was started from a terminal, loaded for a minute, and systemd-oomd
    killed the TERMINAL'S WHOLE SCOPE -- 34, 60, 56, 34 processes, the server
    and every shell and agent that terminal had spawned. Nothing in the
    server's log; it ends at `loading model`. The mechanism: Omarchy runs
    systemd-oomd with `ManagedOOMMemoryPressure=kill` on app.slice (limit 50 %
    for 20 s), vm.swappiness is 150 over a zram swap, and `--load-mode none`
    reads ~48 GiB of experts into anonymous memory while the same bytes sit in
    the page cache -- on 62 GiB that transient pushes the desktop into zram,
    app.slice's pressure crosses the limit, and oomd kills the largest cgroup
    under app.slice: the terminal the server sits in.

    THREE THINGS, ONE PREFIX. `--slice=session.slice` takes the server out of
    app.slice, the one cgroup oomd watches here, so a kill can never take a
    terminal with it. `-p MemorySwapMax=0` forbids the server's anonymous
    memory the zram, which is where its weights went. `-p MemoryHigh=` and
    `MemoryMax=` bound the server's OWN cgroup, so when it crosses the bound
    the kernel reclaims the server's clean page cache instead of squeezing the
    desktop -- and the placement's load_mode is mmap on Linux (manifest), so
    the experts ARE that cache. The fifth kill, 18:16, came with session.slice
    and MemoryHigh alone: the desktop was still what got squeezed. Verified
    on this machine that a user scope accepts both properties and that
    memory.high lands in the cgroup (53,687,091,200 for `50G`). Whether the
    load then stays out of swap is NOT yet measured -- the four kills above
    were the last runs.

    Empty on Windows, empty when systemd-run is not on PATH or the user manager
    is not reachable (user_manager_reachable): then the server starts as
    before, unbounded. `CROW_SERVER_SCOPE=0` switches the prefix off for a
    measurement that wants the bare process. The Popen pid becomes
    systemd-run's; the server is its child in the same session and process
    group, which is what kill_pid and terminate_tree address, and
    `systemd-run --scope` exits with the server's own exit code.
    """
    if IS_WINDOWS or (os.environ.get("CROW_SERVER_SCOPE") or "").strip().lower() in ("0", "off", "none"):
        return []
    return _user_scope_prefix(server_memory_bounds())


def image_server_platform_args() -> list[str]:
    """What this platform appends to sd-server's argv (#320).

    WINDOWS: `--mmap`. Under WDDM every CUDA allocation also counts against
    the system commit limit (the owner's machine: no pagefile, 64,901 MB). serve
    holds 26.7 GB of it, and sd-server without --mmap needs ~37 GB more (the
    CPU text encoder's copy 14.4 GB + pinned DiT staging 14 GB), so every job
    died in `cudaMalloc failed: out of memory` with VRAM free; a VRAM loan
    from serve did not help (10 GB free, same failure). mmap-backed weights
    are file-backed pages, not commit-charged. Measured 2026-09-28 beside the
    default 27B serve: the image completed in 237.7 s, commit 51,149 of
    64,901 MB. ELSEWHERE nothing: the Linux argv is the one measured beside
    the 27B (8.15 GiB free) and stays as it is.
    """
    return ["--mmap"] if IS_WINDOWS else []


def oom_hint() -> str:
    """What this platform adds to an image job's out-of-memory sentence (#320).

    WINDOWS: under WDDM every CUDA allocation also counts against the system
    commit limit, so a `cudaMalloc failed: out of memory` can come with VRAM
    free (the owner's machine, 2026-09-28: 10 GB free, commit exhausted).
    ELSEWHERE nothing: the card is what runs out.
    """
    if not IS_WINDOWS:
        return ""
    return (" -- on Windows the system memory commit limit (RAM plus pagefile) "
            "may be the cause: every CUDA allocation also counts against it "
            "(#320)")


_SYSTEMD_VERSIONS: dict = {}


def _systemd_version(run: str) -> int:
    """The major version `systemd-run --version` reports (0 if unreadable), once per binary."""
    if run not in _SYSTEMD_VERSIONS:
        try:
            first = subprocess.run([run, "--version"], capture_output=True, text=True,
                                   timeout=5, stdin=subprocess.DEVNULL, **no_console_kwargs()).stdout.split()
            _SYSTEMD_VERSIONS[run] = int(first[1]) if first[:1] == ["systemd"] else 0
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            _SYSTEMD_VERSIONS[run] = 0
    return _SYSTEMD_VERSIONS[run]


def _user_scope_prefix(properties: dict, unit: str | None = None,
                       literal: bool = False) -> list[str]:
    """The shared builder: a user scope in session.slice with these properties.

    The callers differ only in their bounds and their switch -- the shape
    (user manager, --scope so the Popen pid stays the waitable one, the slice
    oomd does not watch, --quiet, `--` before the payload) is what #158 and the
    2026-09-16 oomd kills paid for, and it belongs in one place like every
    other OS fact in this file. Verified here (2026-09-22): the scoped process
    lands in session.slice/run-*.scope with memory.max/memory.high/
    memory.swap.max exactly as given. `unit` names the scope (`--unit=`) for a
    caller that has to ask it afterwards how it ended (scope_result) or stop
    what is left in it (kill_scope); without it systemd picks run-*.scope.

    `literal` is for a payload that carries a model's shell text. systemd-run
    EXPANDS ITS COMMAND LINE: measured 2026-09-22 on systemd 261, `bash -c
    'X=secret; echo "[$X]" "[${X}]"'` printed `[secret] []` with "Referenced
    but unset environment variable" on stderr, and `$$` arrived as `$`.
    `--expand-environment=no` turns that off; it exists from systemd 254 on,
    and before 254 a scope did no expansion (systemd NEWS 254/258: off by
    default for --scope until 258 flipped it on), so older ones get nothing.
    The render's and the server's argv hold no `${`, and stay as they were.
    """
    run = shutil.which("systemd-run")
    if not run or not user_manager_reachable():
        return []
    prefix = [run, "--user", "--scope", "--slice=session.slice", "--quiet"]
    if unit:
        prefix.append("--unit=" + unit)
    if literal and _systemd_version(run) >= 254:
        prefix.append("--expand-environment=no")
    for name, value in properties.items():
        prefix += ["-p", "%s=%s" % (name, value)]
    return prefix + ["--"]


def render_scope_prefix() -> list[str]:
    """What to put in front of the render browser's argv (#213).

    The 2026-09-21 runaway (54 GiB software-WebGL render, frozen desktop, the
    kernel shooting the ENGINE instead) ended in no cgroup of the browser's
    own; this prefix gives it one, sized by render_memory_bounds, so the next
    runaway dies alone inside it. Empty on Windows and everywhere systemd-run
    cannot reach the user manager -- then the browser runs as before, bounded
    only by the wall-clock kill. `CROW_RENDER_SCOPE=0` switches it off for a
    measurement that wants the bare process.

    THE UNIT STARTS IN $HOME, NOT IN THE CALLER'S CWD -- measured 2026-09-22:
    a systemd-run probe launched from ~ resolved its relative path against ~
    and died of ENOENT without one retry line. render_page's argv carries only
    absolute paths (the found browser, mkdtemp's profile, the rooted target),
    which is what makes this prefix safe to prepend there.
    """
    if IS_WINDOWS or (os.environ.get("CROW_RENDER_SCOPE") or "").strip().lower() in ("0", "off", "none"):
        return []
    return _user_scope_prefix(render_memory_bounds())


_COMMAND_MEMORY_DEFAULT = "8G"


def command_memory_bounds() -> dict:
    """The memory properties run_command's shell scope gets, as systemd sizes.

    #218. 2026-09-22 evening: after render_page kept timing out, the model ran
    the SAME software-WebGL headless chromium (--enable-unsafe-swiftshader
    --no-sandbox) 20 times through run_command -- the one tool with no memory
    bound, so the runaway #213 had just fenced in was one shell away. The
    bound goes on the shell, not on a binary: the model reaches any binary
    through it.

    WHY 8G. Measured 2026-09-22 as each scope's own memory.peak: the
    diorama's three.js esbuild bundle 106 MiB, `npm ls --all` 46 MiB, node
    importing three 21 MiB, gcc 9 MiB, Crow's own test_crow 60 MiB and
    test_crow_core 109 MiB. 8G is ~75x the largest of those and above a node
    build at V8's own heap ceiling (~4 GiB); it stops the 54 GiB runaway at a
    seventh of the way. The swap cap is render_memory_bounds' reason
    unchanged (on zram the anonymous memory IS the freeze).
    $CROW_COMMAND_MEMORY_MAX moves the kill bound (any systemd size); `none`
    drops the size bounds, keeps the swap cap.

    #309: NO MemoryHigh BELOW THE CEILING -- the default has the override's
    shape. memory.high throttles and never kills (cgroup-v2.rst: "Going over
    the high limit never invokes the OOM killer"), and with no swap the
    anonymous part cannot be reclaimed. Measured 2026-09-27: a Qwen-Image
    sd-cli load sat at 7.40 GiB of MemoryHigh=7G for 10 min 47 s, D state,
    memory.pressure full avg60=88.13, loading at ~11 MB/s instead of
    ~5 GB/s, and never reached the 8G kill its error message is built for.
    Without the throttle an over-budget command dies at memory.max and is
    named as a ceiling kill; the measured legitimate peaks (<= 109 MiB) never
    lived between 7G and 8G.
    """
    out = {"MemorySwapMax": "0"}
    raw = (os.environ.get("CROW_COMMAND_MEMORY_MAX") or "").strip()
    if raw.lower() in ("0", "none", "off"):
        return out
    out["MemoryMax"] = raw or _COMMAND_MEMORY_DEFAULT
    return out


def command_scope_prefix(unit: str) -> list[str]:
    """What to put in front of run_command's shell argv (#218): its own scope.

    Sized by command_memory_bounds, named `unit` so the caller can ask how it
    ended (scope_result) and sweep it after a kill (kill_scope). OOMPolicy=kill
    sets memory.oom.group: at the ceiling the kernel kills EVERY process in
    the scope at once. Measured 2026-09-22 (200 MB hog against MemoryMax=100M,
    `hog; echo after`): with the default OOMPolicy=stop the shell went on and
    printed "after rc=137" before systemd's stop reached it; with kill the
    shell died with the hog (-9) and printed nothing more -- a command either
    ran or was killed whole, never half.

    The scope inherits the caller's cwd: measured 2026-09-22, `pwd` under the
    prefix from a scratch directory printed that directory -- `--scope` execs
    the payload in systemd-run's own process. Empty on Windows, empty where
    systemd-run cannot reach the user manager (then the shell runs as before,
    bounded by the clock and the capture cap only), and with
    `CROW_COMMAND_SCOPE=0`.
    """
    if IS_WINDOWS or (os.environ.get("CROW_COMMAND_SCOPE") or "").strip().lower() in ("0", "off", "none"):
        return []
    # CollectMode: a scope the ceiling killed is unloaded, not kept "failed".
    # CI 2026-09-23 (systemd 255): the unit sat in deactivating past
    # scope_result's settle and turned failed afterwards, a row in
    # `systemctl --user --failed` nobody resets. The kill is still named:
    # session_oom_kills is the witness that does not depend on the unit.
    return _user_scope_prefix(dict(command_memory_bounds(), OOMPolicy="kill",
                                   CollectMode="inactive-or-failed"), unit,
                              literal=True)


def _systemctl_user(*args: str) -> str:
    """`systemctl --user <args>` stdout, "" on any failure. Short and bounded."""
    ctl = shutil.which("systemctl")
    if not ctl:
        return ""
    try:
        return subprocess.run([ctl, "--user", *args], capture_output=True, text=True,
                              timeout=5, stdin=subprocess.DEVNULL, **no_console_kwargs()).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def scope_result(unit: str, settle: float = 2.0) -> str:
    """How the named scope ended: systemd's Result= ("oom-kill", "success", ...).

    A FACT FROM THE UNIT, NOT A GUESS FROM THE EXIT CODE. -9 is also what a
    `kill -9 $$` gives, and a reason the model acts on has to be the real one.
    Measured 2026-09-22, 8 of 8: the first query right after the shell's -9
    already read `failed oom-kill`; `settle` covers a unit still marked
    active/deactivating. 2 s and not 0.5: on CI (systemd 255, 2026-09-23) the
    journal logged "Failed with result 'oom-kill'" for a scope this query had
    already given up on. It is paid only after a -9, and only while systemd
    still calls the unit active. A failed unit stays loaded until reset-failed -- it is
    reset here, so the kill leaves no row in `systemctl --user --failed`.
    """
    import time
    deadline = time.monotonic() + settle
    while True:
        fields = _systemctl_user("show", unit + ".scope", "-p", "ActiveState",
                                 "-p", "Result", "--value").split()
        state, result = (fields + ["", ""])[:2]
        if state == "failed":
            _systemctl_user("reset-failed", unit + ".scope")
            return result
        if state not in ("active", "deactivating", "reloading") or time.monotonic() >= deadline:
            return result
        time.sleep(0.05)


_SLICE_CGROUP: "list[str]" = []
_CGROUP_ROOT = "/sys/fs/cgroup"


def session_oom_kills() -> "int | None":
    """The kernel's oom_kill count for session.slice, or None where unreadable.

    #218, CI 2026-09-23. scope_result asks systemd for Result=oom-kill, and on
    systemd 255 (ubuntu-latest) that answer loses a race: OOMPolicy=kill
    empties the scope at once, the cgroup-empty event is handled before the
    OOM event, the scope goes dead with Result=success and is collected -- the
    ceiling kill came back as a bare "[exit -9]". systemd 261 here always read
    `failed oom-kill` (8 of 8, 2026-09-22). The kernel's count does not race:
    memory.events is hierarchical (cgroup-v2.rst: "all fields in this file are
    hierarchical"), so a kill in any scope under session.slice raises the
    slice's oom_kill. The caller reads it before and after its own scope ran.
    """
    if IS_WINDOWS:
        return None
    # CACHED ONLY ONCE KNOWN. Before the first scope lands in session.slice
    # the slice is not loaded and ControlGroup reads "" -- measured on CI
    # 2026-09-23, where caching that "" left the count None for good.
    if not _SLICE_CGROUP:
        path = _systemctl_user(
            "show", "session.slice", "-p", "ControlGroup", "--value").strip()
        if not path.startswith("/"):
            return None
        _SLICE_CGROUP.append(path)
    path = _SLICE_CGROUP[0]
    try:
        with open(_CGROUP_ROOT + path + "/memory.events", encoding="ascii") as fh:
            for line in fh:
                key, _, value = line.partition(" ")
                if key == "oom_kill":
                    return int(value)
    except (OSError, ValueError):
        return None
    return None


def scope_memory_state(unit: str) -> "dict | None":
    """A live crow-cmd scope's memory, or None when it holds no process (#309).

    For a job that outlived its run_command call: the call's scope keeps it,
    under the call's ceiling, and nothing else looks at it again. Read from
    the cgroup files under session.slice (the path session_oom_kills
    resolves): `procs` (how many), `current` and `max` (bytes; max None for
    "max"), `full_avg60` (memory.pressure, the % of the last 60 s in which
    every task of the scope was stalled on memory -- the PSI signal
    systemd-oomd acts on). None on Windows, where the slice is unknown, and
    once the scope is empty or collected: a scope with no process is over.
    """
    if IS_WINDOWS:
        return None
    if not _SLICE_CGROUP:
        session_oom_kills()             # resolves and caches the slice path
    if not _SLICE_CGROUP:
        return None
    base = "%s%s/%s.scope/" % (_CGROUP_ROOT, _SLICE_CGROUP[0], unit)

    def read(name: str) -> str:
        try:
            with open(base + name, encoding="ascii") as fh:
                return fh.read()
        except (OSError, ValueError):
            return ""
    procs = read("cgroup.procs").split()
    if not procs:
        return None
    state: dict = {"procs": len(procs), "current": None, "max": None, "full_avg60": None}
    for key, name in (("current", "memory.current"), ("max", "memory.max")):
        raw = read(name).strip()
        state[key] = int(raw) if raw.isdigit() else None
    for line in read("memory.pressure").splitlines():
        kind, _, fields = line.partition(" ")
        if kind == "full":
            for field in fields.split():
                name, _, value = field.partition("=")
                if name == "avg60":
                    try:
                        state["full_avg60"] = float(value)
                    except ValueError:
                        pass
    return state


def kill_scope(unit: str, sig: str = "SIGKILL") -> None:
    """SIGKILL whatever is still in the named scope -- the sweep after a kill.

    The process-group kill reaches everything the shell started EXCEPT a
    descendant that left the group (setsid, a daemonizer). The scope's cgroup
    it cannot leave. The unit is the one this caller named, never a pattern
    (#158). `sig` is SIGTERM for #310's graceful first step on Stop."""
    _systemctl_user("kill", "--signal=" + sig, unit + ".scope")


def devtools_pipe() -> "tuple[list[str], tuple[int, int], int, int] | None":
    """The two pipes of `--remote-debugging-pipe`, or None where they cannot be had (#213).

    Chromium reads DevTools commands from fd 3 and writes answers to fd 4 --
    the transport puppeteer's and playwright's `pipe` launch use. Returns
    (argv prefix, fds for Popen's pass_fds, our write end, our read end);
    the caller closes the pass_fds pair after Popen and its own pair when
    the render is over.

    A TRAMPOLINE PROCESS AND NOT preexec_fn: the GUI calls render_page from a
    worker thread, and preexec_fn is documented unsafe with threads. The
    child ends are lifted to fds >= 10 first, because moving fd 3 onto 3 and
    then closing the original closes what was just placed -- measured
    2026-09-22: a fresh os.pipe() hands out fd 3, and the browser then logged
    "Remote debugging pipe file descriptors are not open". The prefix goes
    AFTER the scope prefix: the trampoline execs the browser in place, so the
    pid the scope holds is the browser.

    None on Windows: there the pipe needs handle inheritance through
    --remote-debugging-io-pipes, which nobody has measured here; the caller
    keeps the command-line screenshot path.
    """
    if IS_WINDOWS:
        return None
    import fcntl

    def lifted(fd: int) -> int:
        high = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10)
        os.close(fd)
        return high

    child_in, ours_out = os.pipe()
    ours_in, child_out = os.pipe()
    child_in, ours_out, ours_in, child_out = (
        lifted(child_in), lifted(ours_out), lifted(ours_in), lifted(child_out))
    # THE TRAMPOLINE IS PYTHON, NOT sh. It was `sh -c 'exec "$@" 3<&10 ...'`
    # until CI on ubuntu-latest (2026-09-23) read b"" where the echo child
    # should have answered: /bin/sh there is dash, and dash takes only
    # single-digit fds in a redirection ("Bad fd number") -- so on every
    # Debian/Ubuntu machine the browser never started and every render was
    # "closed its devtools pipe". Arch's sh is bash, which is why it passed
    # here. The interpreter running Crow is always at hand; it moves the two
    # ends onto 3 and 4, closes the originals and execs in place, so the pid
    # the scope holds is still the browser's.
    hop = ("import os,sys;a,b=int(sys.argv[1]),int(sys.argv[2]);"
           "os.dup2(a,3);os.dup2(b,4);os.close(a);os.close(b);"
           "os.execvp(sys.argv[3],sys.argv[3:])")
    prefix = [sys.executable, "-I", "-S", "-c", hop,
              str(child_in), str(child_out)]
    return prefix, (child_in, child_out), ours_out, ours_in


def kill_pid(pid) -> bool:
    """Ask the process with this pid to end. True when the ask went out.

    Windows: `taskkill /PID <pid> /F`, which reaches a process in its own group
    unchanged -- it is not a signal.

    Linux: the GROUP, not the pid, because spawn_kwargs put the server in a
    session of its own and llama-server's own children would otherwise outlive
    it. SIGTERM first: llama.cpp's signal handler shuts down cleanly, and a
    server killed mid-write leaves a slot file nobody can load.
    """
    try:
        number = int(pid)
    except (TypeError, ValueError):
        return False
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(number), "/F"],
                       capture_output=True, stdin=subprocess.DEVNULL,
                       timeout=30, **no_console_kwargs())
        return True
    import signal
    try:
        os.killpg(os.getpgid(number), signal.SIGTERM)
    except ProcessLookupError:
        return False                       # it was already gone
    except (OSError, PermissionError):
        try:
            os.kill(number, signal.SIGTERM)
        except OSError:
            return False
    return True


def pid_alive(pid) -> bool:
    """#196 C3: True while a process with this pid exists.

    Windows: OpenProcess + GetExitCodeProcess (STILL_ACTIVE), no subprocess;
    access denied means it exists. POSIX: signal 0. A pid the OS has since
    reused for another program also reads as alive -- this answers "exists",
    not "is still the same program".
    """
    try:
        number = int(pid)
    except (TypeError, ValueError):
        return False
    if number <= 0:
        return False
    if IS_WINDOWS:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                         wintypes.DWORD)
        handle = kernel32.OpenProcess(0x1000, False, number)  # QUERY_LIMITED
        if not handle:
            return ctypes.get_last_error() == 5               # ACCESS_DENIED
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259                          # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(number, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def kill_tree(pid) -> bool:
    """#310, Windows only: `taskkill /PID <pid> /T /F` -- the process AND the
    children it started. `proc.kill()` on cmd.exe left those running. True
    when taskkill ran and said so; False elsewhere or on any failure, and the
    caller falls back to its handle. Not measured on Windows (#247)."""
    if not IS_WINDOWS:
        return False
    try:
        done = subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                              capture_output=True, stdin=subprocess.DEVNULL,
                              timeout=30, **no_console_kwargs())
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def terminate_tree(proc, grace: float = 5.0) -> None:
    """End a child this process started, and whatever it started in turn.

    THE HANDLE, NEVER A NAME. #158 was paid once: a measurement script swept
    "every llama-server" and took the owner's running test server with it. What dies
    here is the process this caller spawned.

    Windows: killing the handle is the whole story (TerminateProcess). Linux:
    SIGTERM to the session's group, then SIGKILL to whatever is still there
    after `grace` -- a browser leaves grandchildren, and a killed leader does
    not take them along.
    """
    if proc is None:
        return
    try:
        proc.kill()
    except Exception:
        pass
    if IS_WINDOWS:
        return
    import signal
    import time
    try:
        group = os.getpgid(proc.pid)
    except (OSError, AttributeError):
        return
    if group == os.getpgrp():
        return                             # not detached: killing it is enough
    # DER ANFUEHRER WIRD ABGEHOLT, BEVOR DIE GRUPPE GEZAEHLT WIRD. `proc.kill()`
    # oben hinterlaesst eine Leiche, bis jemand auf sie wartet -- und eine
    # Leiche ist weiterhin Mitglied der Gruppe: `killpg(group, 0)` unten gelingt
    # auf ihr. Ohne dieses Warten lief die Schleife DESHALB immer die vollen
    # `grace` Sekunden und eskalierte immer auf SIGKILL, auch wenn das SIGTERM
    # die Gruppe laengst geleert hatte (gemessen 2026-09-16: 5,01 s bei
    # grace=5,0, und tool_render_page zahlt das auf dem Zeitlimit-Weg).
    try:
        proc.wait(timeout=grace)
    except Exception:                      # noqa: BLE001 - die Schleife zaehlt
        pass
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 0.0)):
        try:
            os.killpg(group, sig)
        except (ProcessLookupError, OSError):
            return
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            try:
                os.killpg(group, 0)
            except (ProcessLookupError, OSError):
                return
            time.sleep(0.05)


# --------------------------------------------------------------- the shell ---


def shell_executable() -> "str | None":
    """The shell binary for `subprocess.run(..., shell=True)`, or None.

    None on Windows means COMSPEC, which is what shell=True has always used --
    handing it an explicit argv instead would change how a space or an ampersand
    in a path is quoted, and that is the one thing a shell call may not change.

    On Linux shell=True is `/bin/sh`, and `sh` is not what the model is told it
    is talking to: it writes bash (`[[`, `$'...'`, process substitution). So the
    shell is named, and only if it is really there.
    """
    if IS_WINDOWS:
        return None
    return shutil.which("bash")


def shell_argv(command: str) -> list[str]:
    """The same command as an explicit argv, for a caller that wants no shell=True."""
    if IS_WINDOWS:
        return [os.environ.get("COMSPEC") or "cmd.exe", "/c", command]
    return [shell_executable() or "/bin/sh", "-c", command]


# ------------------------------------------------------------- the browser ---

# #175. WHERE A BROWSER LIES, AND IT IS SEARCHED FOR RATHER THAN GUESSED.
# Windows: Chrome first, Edge as the fallback -- both are Chromium and take the
# same switches, but Edge is on every Windows, and a tool that presupposes an
# installation the user does not have is a tool that fails once and is never
# called again.
_BROWSERS_WINDOWS = (
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
)

# Linux has no fixed installation path worth guessing -- a browser may come from
# the distribution, from flatpak or from a tarball -- so the names are looked up
# on PATH. Chromium first for the same reason Chrome is first on Windows:
# `--headless=new --screenshot` is a Chromium switch set. Firefox is last and is
# NOT equivalent (its headless screenshot mode takes different flags); it stands
# here so that `find_browser` can say "there is a browser" on a machine that has
# only Firefox, and the render call then fails with the browser's own words.
_BROWSERS_LINUX = ("chromium", "chromium-browser", "google-chrome-stable",
                   "google-chrome", "brave", "brave-browser", "microsoft-edge",
                   "firefox")


def browser_candidates() -> tuple[str, ...]:
    """Every place a Chromium could be, in order. Nothing is started."""
    return _BROWSERS_WINDOWS if IS_WINDOWS else _BROWSERS_LINUX


def find_browser_path() -> "str | None":
    """The first browser on this machine, or None. Path only, nothing started."""
    for raw in browser_candidates():
        if IS_WINDOWS:
            path = os.path.expandvars(raw)
            if "%" not in path and os.path.isfile(path):
                return path
        else:
            found = shutil.which(raw)
            if found:
                return found
    return None


# #293. GPU ONLY. Until 2026-09-25 this gate chose SwiftShader below the
# bound, and a 16-hour diorama run (2026-09-24/25, 35 of 42 surviving results
# `software (swiftshader)` at 51-317 MiB free) was judged on 1-spp CPU noise.
# Below the bound render_page now returns an ENVIRONMENT error, never pixels.
#
# #213. GPU WHEN THE CARD IS FREE, SWIFTSHADER OTHERWISE. Measured here
# 2026-09-22, headless, one animated WebGL page, budgets 2000 vs 8000:
#
#   --disable-gpu --enable-unsafe-swiftshader --use-angle=swiftshader
#       renderer "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)),
#       SwiftShader driver)" -- software, as it has been since #175-Nachtrag;
#       both budgets drew (14260 != 14162 bytes).
#   --use-gl=angle (no --disable-gpu)
#       renderer "ANGLE (NVIDIA Corporation, NVIDIA GeForce RTX 5090/PCIe/
#       SSE2, OpenGL ES 3.2)" -- the card, and both budgets drew too
#       (13836 != 13261 bytes). Its own VRAM draw stayed inside ~150 MiB on
#       that page; the runaway memory class of software WebGL never started.
#
# The gate is FREE VRAM, not presence: the engine may hold the card, and a
# render that guesses itself onto a busy one trades a frozen desktop for a
# shot engine. 512 MiB free is comfortably above the measured draw of a
# headless render while being small enough to let the common card-free case
# through.
_GPU_HEADROOM_MIB = 512

# #279. CROW'S OWN BROWSER PANEL IS A SECOND GPU CLIENT. Measured
# 2026-09-24 (the owner's diorama run, serve up, ~560 MiB free at boot): the
# panel's WebKitWebProcess held 343 MiB of the card, and twice a GPU render
# 5-10 s earlier was followed by a SIGSEGV of that process inside
# libnvidia-eglcore (coredumpctl, 13:15:20 and 13:16:01 local). 512 MiB was
# set in #213 from ONE headless render with no second client in the picture.
# With the panel open (or holding a page) the bound is the render's measured
# ~150 MiB + the panel's measured 343 MiB, doubled for a WebGL page that grows
# and for the driver's own slack, rounded up to 1.5 GiB. The window says
# whether the panel counts (crow_core.render_panel_set, read per turn).
_GPU_HEADROOM_PANEL_MIB = 1536


def gpu_headroom_mib(panel: bool = False) -> int:
    """The free VRAM a GPU render needs: #213's bound, or #279's with the
    window's browser panel on the same card."""
    return _GPU_HEADROOM_PANEL_MIB if panel else _GPU_HEADROOM_MIB


def gpu_free_mib(query=None) -> "int | None":
    """Free VRAM in MiB on the first card, or None when there is no answer.

    nvidia-smi is the only reader -- the machine this was measured on answers
    with an NVIDIA card, and a generic probe would be a second opinion nobody
    asked for. A probe that cannot run or cannot be parsed is None, and None
    means SOFTWARE (swiftshader): the render may not guess itself onto a card
    whose state it could not read. `query` is the injection point for the
    suite, the same seam find_servers has.
    """
    if query is None:
        exe = shutil.which("nvidia-smi")
        if not exe:
            return None

        def query():
            try:
                done = subprocess.run(
                    [exe, "--query-gpu=memory.free",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, stdin=subprocess.DEVNULL,
                    timeout=10, **no_console_kwargs())
            except (OSError, subprocess.SubprocessError):
                return ""
            return done.stdout if done.returncode == 0 else ""

    try:
        first = (query() or "").strip().splitlines()[0]
        return int(round(float(first.strip().split(",")[0])))
    except (IndexError, ValueError):
        return None


# #270. WHAT THE MACHINE IS, as static facts for the prompt head.
# Measured 2026-09-23/24: with the model server holding the card (73 MiB free of
# 32,607), render_page rasterised 49 of 49 captures in software, and the model
# concluded twice -- in its memory ("Machine has NO GPU", 09:53) and in its
# answers -- that the MACHINE had no GPU. Nothing in its context said otherwise.
# STATIC ONLY: names and totals, never free memory, because the head is byte 0
# of the prefix and a number that moves would cost a full prefill per turn.
_MACHINE: "list[str]" = []


def gpu_card(query=None) -> "tuple[str, int] | None":
    """(name, total MiB) of the first NVIDIA card, or None without an answer."""
    if query is None:
        exe = shutil.which("nvidia-smi")
        if not exe:
            return None

        def query():
            try:
                done = subprocess.run(
                    [exe, "--query-gpu=name,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, stdin=subprocess.DEVNULL,
                    timeout=10, **no_console_kwargs())
            except (OSError, subprocess.SubprocessError):
                return ""
            return done.stdout if done.returncode == 0 else ""

    try:
        first = (query() or "").strip().splitlines()[0]
        name, total = [p.strip() for p in first.rsplit(",", 1)]
        return (name, int(round(float(total)))) if name else None
    except (IndexError, ValueError):
        return None


def _os_name() -> str:
    if IS_WINDOWS:
        import platform
        return "Windows %s" % platform.release()
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return "Linux (%s)" % line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return sys.platform


def _cpu_name() -> "str | None":
    if IS_WINDOWS:
        import platform
        return platform.processor() or None
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def _ram_gib() -> "int | None":
    if IS_WINDOWS:
        import ctypes

        class _Mem(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        mem = _Mem()
        mem.dwLength = ctypes.sizeof(_Mem)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                return int(round(mem.ullTotalPhys / 2 ** 30))
        except (AttributeError, OSError):
            return None
        return None
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(round(int(line.split()[1]) / 2 ** 20))
    except (OSError, ValueError, IndexError):
        pass
    return None


def machine_facts(card=None) -> str:
    """One line: OS, CPU, RAM, GPU. Probed once per process, then fixed.

    `card` is the suite's seam (a (name, MiB) tuple, or False for none).
    """
    if card is None and _MACHINE:
        return _MACHINE[0]
    if card is None:
        card = gpu_card()
    parts = [_os_name()]
    cpu = _cpu_name()
    if cpu:
        parts.append(cpu)
    ram = _ram_gib()
    if ram:
        parts.append("%d GiB RAM" % ram)
    parts.append("GPU %s (%s MiB VRAM)" % (card[0], "{:,}".format(card[1]))
                 if card else "no NVIDIA GPU found by nvidia-smi")
    line = ", ".join(parts)
    if not _MACHINE:
        _MACHINE.append(line)
    return line


def render_gl_reason(free_mib: "int | None" = None, panel: bool = False) -> str:
    """#271/#293: why render_gl_mode said "unavailable", in one clause."""
    forced = (os.environ.get("CROW_RENDER_GL") or "").strip().lower()
    if forced in _RENDER_GL_SOFTWARE:
        return ("CROW_RENDER_GL=%s asks for software rendering, which render_page "
                "no longer does -- it renders on the GPU only (#293)" % forced)
    if free_mib is None:
        free_mib = gpu_free_mib()
    if free_mib is None:
        return "nvidia-smi gave no free-VRAM reading"
    card = gpu_card()
    name = card[0] if card else "the GPU"
    need = gpu_headroom_mib(panel)
    # #279: the bound is named with its reason, so a refusal with 900 MiB
    # free does not read as a miscount.
    beside = (" next to Crow's own browser panel on the same card" if panel
              else "")
    return ("%s has %s MiB VRAM free, below the %s MiB a GPU render needs%s -- the "
            "model server holds it; the machine HAS this GPU and the user's browser "
            "renders on it, so this says nothing about the page or about GPU speed"
            % (name, "{:,}".format(free_mib), "{:,}".format(need), beside))


# The values of $CROW_RENDER_GL that used to pin the software arm (#213).
_RENDER_GL_SOFTWARE = ("swiftshader", "software", "cpu")


def render_gl_mode(free_mib: "int | None" = None, panel: bool = False) -> str:
    """"angle" when the card has headroom, else "unavailable" (#213, #293).

    `panel`: the window's browser panel is open or holds a page, so the render
    would be the card's second client next to it (#279).

    $CROW_RENDER_GL=angle|gpu skips the VRAM gate (the renderer check in
    render_page still applies). The old software values are "unavailable":
    render_page renders on the GPU only since #293, and a pin that asks for
    software gets the refusal that names it, never software pixels. An
    unreadable card is "unavailable" too -- the render may not guess itself
    onto a card whose state it could not read.
    """
    forced = (os.environ.get("CROW_RENDER_GL") or "").strip().lower()
    if forced in ("angle", "gpu"):
        return "angle"
    if forced in _RENDER_GL_SOFTWARE:
        return "unavailable"
    if free_mib is None:
        free_mib = gpu_free_mib()
    return "angle" if (free_mib is not None
                       and free_mib >= gpu_headroom_mib(panel)) else "unavailable"


# #293. THE ANGLE BACKENDS, IN ORDER. `vulkan` is the owner's decision of
# 2026-09-25 and the launcher line of the research brief (Chromium's
# "Using GPU hardware in headless Chrome",
# https://chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/gpu/using-gpu-hardware-in-headless-chrome.md;
# https://developer.chrome.com/blog/supercharge-web-ai-testing; three.js e2e,
# https://github.com/mrdoob/three.js/blob/dev/test/e2e/puppeteer.js L209-218).
# NOT MEASURED on this machine. `default` is the line measured here on
# 2026-09-22 (#213): `--use-gl=angle` alone, renderer "ANGLE (NVIDIA
# Corporation, NVIDIA GeForce RTX 5090/PCIe/SSE2, OpenGL ES 3.2)". When the
# renderer check rejects the first, render_page tries the next once.
#
# NEVER `--enable-unsafe-swiftshader` (the opt-in of the blink-dev intent,
# https://groups.google.com/a/chromium.org/g/blink-dev/c/yhFguWS_3pM). But
# its absence is NOT the guard: measured 2026-09-25, Chromium 152.0.7977.82
# with --disable-gpu and without the flag still handed WebGL a SwiftShader
# context ("Automatic fallback to software WebGL has been deprecated" in the
# console). The guard is the renderer string (render_renderer_verdict).
_RENDER_GPU_FLAGS = {
    "vulkan": ["--enable-gpu", "--use-gl=angle", "--use-angle=vulkan",
               "--enable-features=Vulkan", "--disable-vulkan-surface",
               "--ignore-gpu-blocklist"],
    "default": ["--use-gl=angle"],
}


def render_angle_backends() -> "list[str]":
    """The ANGLE backends render_page tries, in order (#293).

    $CROW_RENDER_ANGLE=vulkan|default pins one; anything else is both.
    """
    pinned = (os.environ.get("CROW_RENDER_ANGLE") or "").strip().lower()
    if pinned in _RENDER_GPU_FLAGS:
        return [pinned]
    return list(_RENDER_GPU_FLAGS)


def render_gpu_flags(backend: str) -> "list[str]":
    """Chromium's flags for one ANGLE backend (#293), a fresh list."""
    return list(_RENDER_GPU_FLAGS.get(backend, _RENDER_GPU_FLAGS["default"]))


# Renderer strings that are software, whatever the launch line asked for:
# SwiftShader (Chrome's own), Mesa's llvmpipe/lavapipe/softpipe, Windows'
# WARP ("Microsoft Basic Render Driver").
_SOFTWARE_RENDERER = re.compile(
    r"swiftshader|llvmpipe|lavapipe|softpipe|software|basic render", re.I)


def render_renderer_verdict(renderer: "str | None", why: str = "",
                            card: "tuple | None | bool" = None) -> "str | None":
    """#293. None when `renderer` (WEBGL_debug_renderer_info's
    UNMASKED_RENDERER_WEBGL) is the real GPU, else the reason it is not.

    A software string is refused by name. When nvidia-smi names an NVIDIA
    card, the string must say NVIDIA -- the owner's rule of 2026-09-25: the
    capture is taken on the card or not at all. `card` is the suite's seam
    (a (name, MiB) tuple, or False for none)."""
    if not renderer:
        return ("the browser created no WebGL context%s" % (" (%s)" % why if why else ""))
    if _SOFTWARE_RENDERER.search(renderer):
        return "WebGL runs on a software rasterer: %s" % renderer
    if card is None:
        card = gpu_card()
    if card and "nvidia" in str(card[0]).lower() and "nvidia" not in renderer.lower():
        return ("WebGL runs on %s, not on the %s" % (renderer, card[0]))
    return None


# --------------------------------------------------------------- the fonts ---

def font_store() -> str:
    """The per-user font directory this platform reads faces from.

    Per-user on both, and on purpose: the machine-wide store needs elevation on
    Windows and root here, and a chat client has no business asking for either.
    """
    if IS_WINDOWS:
        return os.path.join(os.environ.get("LOCALAPPDATA", ""),
                            "Microsoft", "Windows", "Fonts")
    # `$XDG_DATA_HOME/fonts` is the directory fontconfig scans per user; the
    # `crow/` below it is so that an uninstall can remove exactly what Crow put
    # there and nothing the user installed by hand.
    return os.path.join(_xdg_base("XDG_DATA_HOME", (".local", "share")),
                        "fonts", APP_DIR_XDG)


# ------------------------------------------------------------- the updater ---

def opener_command(path: str) -> "list[str] | None":
    """How this platform shows a file to the person, as data. Nothing runs here.

    #211. DIE KARTE AM SCHNITT braucht einen Weg, das Transkript zu zeigen:
    Windows hat `os.startfile` (kein argv -- None heisst hier "die eigene
    Tuere", der Aufrufer kennt sie), macOS `open`, alles andere `xdg-open`.
    Dasselbe Warum wie bei `updater_command`: die Plattformentscheidung
    gehoert in dieses Modul, nicht zwanzigmal in den Aufrufern.
    """
    if IS_WINDOWS:
        return None
    if sys.platform == "darwin":
        return ["open", path]
    return ["xdg-open", path]


def reveal_command(path: str, is_dir: bool) -> list[str]:
    """#229. How this platform shows a path IN ITS FOLDER, as data. Runs nothing.

    A FOLDER IS WHAT GETS OPENED, NEVER THE FILE. The path comes out of a
    model's text, and `xdg-open` / `os.startfile` on a `.desktop`, `.sh`, `.exe`
    or `.bat` can run it -- so the file manager is shown the folder (Windows and
    macOS select the file in it; freedesktop's `xdg-open` has no "select", so
    Linux opens the parent). A directory handler runs nothing it is pointed at.
    """
    if IS_WINDOWS:
        # `explorer /select,<path>` is ONE argument to explorer, comma and all.
        return ["explorer", path] if is_dir else ["explorer", "/select," + path]
    if sys.platform == "darwin":
        return ["open", path] if is_dir else ["open", "-R", path]
    return ["xdg-open", path if is_dir else os.path.dirname(path) or "/"]


def updater_command(script: str, install: str | None = None) -> list[str]:
    """How this platform runs the installer, as data. Nothing is executed here.

    WINDOWS: PowerShell, the installer as a FILE, and told not to wait. Two
    facts, each fatal on its own -- `irm <url> | iex` cannot take parameters
    (install.ps1 says so in its own comment), so the script is fetched to a file
    and run with `-File`; and the installer waits for ENTER at the end so the
    last screen can be read, which behind a window with no console is a wait
    that never ends. `-NoProfile` so a profile that prints or prompts cannot
    join in, `-ExecutionPolicy Bypass` because a downloaded file is exactly what
    the default policy refuses.

    LINUX: `bash install.sh`, no flags. install.sh's contract is
    `install.sh [--to DIR]` and its default target is install_dir(), so an
    update in place is the bare call; bash is named rather than relying on the
    executable bit, because a script fetched over HTTP arrives without one.
    """
    if IS_WINDOWS:
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", script, "-NoPause"]
    return ["bash", script]


# ------------------------------------------------------------ the LAN (#249) ---

# Interfaces that are never "the home network": container bridges, VPN
# tunnels, VM host-only nets. /remote binds ONE address, and binding one of
# these would either be unreachable from the phone or reachable from further
# away than the home Wi-Fi -- tailscale* is the second kind, and the ticket
# rules out access from outside the LAN.
_LAN_SKIP = ("lo", "docker", "veth", "br-", "tun", "tap", "tailscale", "vbox",
             "virbr", "wg", "zt", "vmnet", "lxc", "lxd", "podman", "cni", "flannel")


def _rfc1918(ip: str) -> bool:
    import ipaddress
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return any(addr in ipaddress.IPv4Network(n)
               for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def _parse_ip_json(text: str) -> list[tuple[str, str]]:
    """`ip -j -4 addr` output -> [(interface, IPv4)], every address, unfiltered."""
    import json
    try:
        links = json.loads(text or "[]")
    except ValueError:
        return []
    out = []
    for link in links if isinstance(links, list) else []:
        name = link.get("ifname") or ""
        for a in link.get("addr_info") or []:
            if a.get("family") == "inet" and a.get("local"):
                out.append((name, a["local"]))
    return out


def _ioctl_addresses() -> list[tuple[str, str]]:
    """The same list without iproute2: SIOCGIFADDR per interface, stdlib only.

    One address per interface (the primary), which is all a home machine has.
    """
    import fcntl
    import socket
    import struct
    out = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for _, name in socket.if_nameindex():
            try:
                raw = fcntl.ioctl(s.fileno(), 0x8915,            # SIOCGIFADDR
                                  struct.pack("256s", name.encode()[:15]))
            except OSError:
                continue                                         # no IPv4 on it
            out.append((name, socket.inet_ntoa(raw[20:24])))
    return out


def lan_addresses(query=None, sys_net: str = "/sys/class/net") -> list[tuple[str, str]]:
    """(interface, IPv4) pairs /remote may bind, best candidate first.

    WHERE, NOT WHETHER: this lists and orders, the caller picks (the dialog
    can switch). Loopback, link-local and the _LAN_SKIP families are dropped;
    what remains is ordered RFC1918 before anything else, then physical
    (/sys/class/net/<if>/device exists -- a real NIC or Wi-Fi card) before
    virtual, then by name, so a home machine's Wi-Fi or Ethernet address is
    first.

    LINUX asks iproute2 (`ip -j -4 addr`, present on every distribution this
    runs on) and falls back to an ioctl per interface. `query` replaces the
    `ip` call for the tests. WINDOWS is stage 3: a best effort through the
    host name's addresses, with no interface names.
    """
    if IS_WINDOWS:
        import socket
        try:
            found = [("", info[4][0]) for info in
                     socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
        except OSError:
            found = []
    else:
        try:
            text = query() if query else _run_query(["ip", "-j", "-4", "addr"])
        except Exception:                  # noqa: BLE001 - the fallback answers
            text = None
        found = _parse_ip_json(text) if text else []
        if not found and query is None:
            try:
                found = _ioctl_addresses()
            except Exception:              # noqa: BLE001 - no LAN is an answer, not a crash
                found = []
    seen, out = set(), []
    for name, ip in found:
        if (name, ip) in seen or ip.startswith("127.") or ip.startswith("169.254."):
            continue
        if name and name.startswith(_LAN_SKIP):
            continue
        seen.add((name, ip))
        out.append((name, ip))

    def physical(name: str) -> bool:
        return bool(name) and os.path.exists(os.path.join(sys_net, name, "device"))

    out.sort(key=lambda p: (not _rfc1918(p[1]), not physical(p[0]), p[0], p[1]))
    return out
