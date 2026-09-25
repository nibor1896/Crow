[← README](../../README.md) · [Docs index](../README.md)

# Linux

Same window, same core, same manifest. Ported and run on Arch (Omarchy), Hyprland 0.56.2 on
Wayland, RTX 5090, driver 610.57, Python 3.14. Nothing on this page needs root.

| | |
|---|---|
| Install | `bash install.sh` — five steps, a per-file sha256 manifest, idempotent |
| Window | WebKitGTK 4.1 through PyGObject, where Windows has WebView2 |
| Engine | built here, not downloaded: there is no Linux release asset |
| Clipboard | `wl-clipboard`; `xclip` is the X11 fallback |
| Models | `<install>/models`, a link the installer points at your tree; `$CROW_MODELS` overrides it |
| Source of truth | [`cli/crow_platform.py`](../../cli/crow_platform.py) — the one module that knows which OS this is |

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh | bash
```

or, from a checkout, the same script:

```bash
bash install.sh --models ~/Projects/models/qwen3.8-flash-next
```

| flag | |
|---|---|
| `--models DIR` | where the GGUFs live. Makes `$CROW_HOME/models` a link to it |
| `--voice` | also `faster-whisper` and `sounddevice` for the composer's microphone |
| `--tailscale` | also print what is still missing for the phone over HTTPS — see [Phone over Tailscale](#phone-over-tailscale) |
| `--pathtracer` | also switch on the `voxel-diorama` skill — see [Voxel kit](voxel-kit.md) |
| `--build-engine` | build `llama-server` now instead of printing the line (~20 minutes) |
| `--no-desktop` | no `.desktop` entry, no icons, no Hyprland rule |
| `--no-engine` | do not look for the engine at all |
| `--to DIR` | install root, same as `CROW_HOME=DIR` |
| `--selftest` | drive the script's own checks, including the ones that must fail. Installs nothing |

It needs PyGObject from the distribution, because pip cannot build it here without the GObject
headers — so the installer **prints** the line and never runs it:

```bash
sudo pacman -S --needed python-gobject gtk3 webkit2gtk-4.1 wl-clipboard
```

`node`, `bwrap` and `systemd-run` are optional and only warned about — see
[Optional helpers](#optional-helpers).

The venv it creates is a `--system-site-packages` one, and that is the whole trick: pywebview
comes from pip, PyGObject and the typelibs come from pacman, and both have to be visible to one
interpreter. `pywebview[gtk]` is never installed — the extra pulls a PyGObject wheel that
shadows the distribution's build, which is the one with the typelibs beside it.

**Idempotent, and it removes nothing it did not install.** `$CROW_HOME/manifest.sha256` is
written at the end of every run and read at the start of the next, so a second run reports what
moved underneath it and replaces exactly that. The only files it deletes are the ones the
previous manifest listed and the new payload no longer ships — so `bin/`, `cuda/`, `src/`,
`build/`, `venv/` and a model tree beside them survive every re-run.

---

## Where things go

Every XDG variable is honoured when it is set and absolute. A relative value is treated as
unset, which is what the specification asks for.

| what | Linux | Windows, unchanged |
|---|---|---|
| install root | `${XDG_DATA_HOME:-~/.local/share}/crow` | `%LOCALAPPDATA%\Crow` |
| `secrets.json`, `settings.json`, `roots.json`, `USER.md`, `skills/`, `mcp.json`, `providers.json`, `approvals.json` | `~/.config/crow/` | `%LOCALAPPDATA%\Crow\` |
| `index.db` (session search) | `~/.local/share/crow/` | `%LOCALAPPDATA%\Crow\` |
| `session/`, `booted.json`, `git_events.json` | `~/.local/state/crow/` | `%LOCALAPPDATA%\Crow\` |
| `llama-server` boot logs | `~/.local/state/crow/log/` | `<cwd>\runs\` |
| Crow's own log, `crow.log` (rotated, 1 MiB × 4) | `~/.local/state/crow/log/` | `%LOCALAPPDATA%\Crow\log\` |
| models | `<install>/models`, a link to the tree; `$CROW_MODELS` overrides it | `<install>\models` |
| `llama-server` binary | `<install>/bin/`, then `PATH`, then `~/.local/share/crow/bin` | `<install>\bin\llama-server.exe` |
| fonts | `~/.local/share/fonts/crow/` + `fc-cache` | `%LOCALAPPDATA%\Microsoft\Windows\Fonts` + winreg |
| launcher | `$CROW_HOME/bin/crow`, symlinked into `~/.local/bin` if that is on `$PATH` | none — `install.ps1` prints the start line and writes nothing to the Start menu, the registry or `PATH` |
| desktop entry | `~/.local/share/applications/crow.desktop` | — |
| icons | `~/.local/share/icons/hicolor/<N>x<N>/apps/crow.png`, N = 16…512 | the packaged `.ico` |

---

## Models

```bash
hf download unsloth/Qwen3.8-Flash-Next-GGUF --include "*UD-Q2_K_XL*" --local-dir ~/Projects/models/qwen3.8-flash-next
hf download unsloth/Qwen3.8-Flash-Next-GGUF mmproj-F16.gguf --local-dir ~/Projects/models/qwen3.8-flash-next
```

The second line is the vision projector: it sits in the repository root, above the quant folder,
so the glob of the first walks past it. Without it the server boots the same model as a
text-only one and `read_image` refuses with a sentence. `hf` prints a tick even when it reached
nothing — check the byte counts (73.45 GiB over three shards, 904,004,000 B for the projector).

**`<install>/models` is a link to your model tree; change it with `install.sh --models DIR`, or
point `CROW_MODELS` at another tree for one shell.** The link is the whole mechanism, and it is a
link rather than a variable because a variable reaches exactly one process. `--models DIR` used to
write `export CROW_MODELS="DIR"` into `$CROW_HOME/env` and only `$CROW_HOME/bin/crow` sourced that
file, so the window found the tree and nothing else did — `python3 ~/.local/share/crow/tools/start-server.py
flash-next-q2-k-xl` answered `model 'flash-next-q2-k-xl' is not on disk`. `<install>/models` is what
`crow_platform.models_dir()` resolves to with nothing set, so a link there is read by the window,
the terminal client and `tools/start-server.py` alike, with no environment at all. `$CROW_HOME/env`
is no longer written, and a run removes the one an earlier run left — unless you edited it, in which
case it is kept and named, and nothing reads it any more.

**A checkout is its own `<install>`.** `crow_core.INSTALL_ROOT` is the parent of the `cli/` that is
running, so `python cli/crow_gui.py` from a clone resolves `<clone>/models` and never looks in
`~/.local/share/crow`. Give the clone the same link — the installer prints this line when it ran
from one:

```bash
ln -s ~/Projects/models/qwen3.8-flash-next ~/Projects/crow/models
```

The installer never replaces a real `<install>/models` directory that has files in it: it warns and
prints the two lines that would move it aside.

The tree may be flat or nested: the core tries the manifest's path under the models root and
then the file's basename directly under it, so both
`<root>/qwen-next-gguf/UD-Q2_K_XL/…-00001-of-00003.gguf` and `<root>/…-00001-of-00003.gguf`
resolve.

---

## Engine

```bash
bash tools/build-llama-server.sh
```

There is no Linux release asset — the Windows package ships `llama-server.exe` — so the engine
is built from source, from the same three commits the operating point was measured at: llama.cpp
pin `6c84c7d5d` (PR #27742, `qwen4exp`), plus PR #27880 and PR #28040. It unpacks CUDA 13.3 and
cmake/ninja under `$CROW_HOME`, compiles for `sm_120`, and does not accept the result until
`ldd` resolves `libcudart`, `libcublas` and `libcublasLt` to that same prefix — mixing a
compiler of one CUDA major with another's runtime produces failures that look like a warmup
abort (upstream #28403, #25060).

| | |
|---|---|
| `JOBS=8` | gentler on the machine |
| `CLEAN=1` | throw the build directory away first |
| `LLAMA_PIN=<sha>` | move the pin; clear `LLAMA_PRS` with it |

`$CROW_HOME/cuda` must stay where it is: the binary reaches its CUDA libraries through a
`DT_RPATH` into that directory. Deleting it breaks the binary.

---

## Start

**Default: crow-nest**, from the crow-nest repo root (build and container download:
[install guide](install.md#the-model)):

```bash
cd ~/Projects/crow-nest && tools/serve-linux.sh --port 8099
crow --base-url http://127.0.0.1:8099/v1
```

`serve-linux.sh` looks for the CUDA 13.3 runtime in `~/.local/share/crow/cuda/lib`; `CUDA_LIB`
names another directory.

**Second: llama.cpp.** The server first, in its own terminal -- it loads for about a minute and prints
`listening on http://127.0.0.1:8083` when it is up:

```bash
python3 ~/.local/share/crow/tools/start-server.py flash-next-q2-k-xl
```

Then the window, in a second terminal:

```bash
crow
```

The window reads the port off the running server; the model menu can switch and reboot it from
there.

**The server runs in a scope of its own, and the experts are file-backed.** Both starts
wrap `llama-server` in `systemd-run --user --scope --slice=session.slice -p MemorySwapMax=0
-p MemoryHigh=<RAM − 10 GiB> -p MemoryMax=<RAM − 8 GiB>` when `systemd-run` is on the PATH
and the user manager is reachable, and the Linux line loads with `--load-mode mmap` where
Windows uses `none`. Measured 2026-09-16 on
Omarchy without it: systemd-oomd (kill policy on `app.slice`, 50 % pressure for 20 s, over
`vm.swappiness=150` and zram) killed the terminal's whole scope four times while the model
loaded -- the server and every process that terminal had spawned, log ending at
`loading model`. A fifth kill at 18:16 came with the scope alone: the ~48 GiB of experts were still anonymous
memory, still swapped into zram, and the desktop was still what got squeezed. So: mmap makes
the experts page-cache pages the kernel can drop and re-read from NVMe without swapping
anything; `MemorySwapMax=0` keeps the server's remaining anonymous memory out of zram; the
size bounds make the kernel reclaim the server's own cache before the desktop's. Decode under
mmap, measured the same evening in the window: 41.8 tok/s, above the 36.7 of `none`. `CROW_SERVER_MEMORY_HIGH=48G`
moves the bound, `CROW_SERVER_SCOPE=0` runs the bare process.

**Images: 1,024 tokens each, encoded on the CPU.** The Linux line carries `--image-min-tokens
1024` and `--no-mmproj-offload`. Below 1,024 tokens the model does not see a pasted screenshot;
with the projector on the GPU the encoder has no VRAM left at `-ncmoe 31` and the server
segfaults. On the CPU an image costs a few seconds of prefill and is read correctly. Both
measured 2026-09-16; the reasons in [operating points](../operating-points.md#flash-next-on-linux--the-line-that-differs-measured).

The page, the tools, the memory and the browser pane are the ones [`window.md`](window.md)
describes. What Wayland makes different:

**It has to be told to float.** A Wayland client may not place, size or raise its own toplevel —
`gtk_window_move()` is a documented no-op, `set_keep_above()` does nothing, and a window created
at 500×250 came up tiled at 1261×688. Tiled is fine -- the window takes its tile, fills the
workspace and goes fullscreen like any Omarchy window (accepted live, 2026-09-16). The float
rule is optional: Crow is frameless and its layout has a hard minimum of 1,130 px (520 rail +
560 chat + 50 column chrome), so tiled at a third of a screen the composer is the first thing to
go, and floating is the answer for that. The drag and resize grips only matter when floating.
The rule ships in both Hyprland dialects, because Hyprland picks its parser from the config it
finds:

| your config | what `install.sh` copies | the line to add, by hand |
|---|---|---|
| `~/.config/hypr/hyprland.lua` | `~/.config/hypr/crow.lua` | `require("hypr.crow")` |
| `~/.config/hypr/hyprland.conf` | `~/.config/hypr/crow.conf` | `source = ~/.config/hypr/crow.conf` |

Then `hyprctl reload`. The installer does not edit your config: a script that writes into
`hyprland.lua` has to parse it, and getting that wrong costs somebody their session on the next
reload.

**The title bar and the grips hand the gesture over.** `pywebview-drag-region` and
`window.move(x, y)` move nothing here, so a mousedown on the bar calls
`Gtk.Window.begin_move_drag` and one on any of the eight edge grips calls `begin_resize_drag`,
on the GTK main thread. The compositor runs the drag; Crow never computes a rectangle.

**The browser pane is inside the window (#201).** It is a second WebKitWebView in Crow's own
GtkWindow, placed on the panel through a `GtkOverlay`, not a toplevel. No window rule is involved.
Before #201 it was a separate toplevel with the `crow` app id. The float, center and
`size 1180 800` rules then made it a second 1180×800 window centred over Crow.
`CROW_PANE_WINDOW=1` brings that window back for comparison.

**The app id is `crow`.** `GLib.set_prgname("crow")` runs before the window opens, which is what
`xdg_toplevel.set_app_id` falls back to. Without it `hyprctl clients -j` reports the class as
`crow_gui.py`, the desktop entry matches nothing and the icon is generic. Under the X11 escape
hatch the same window is `Crow` — GTK capitalises `res_class` — so every rule matches
`^([Cc]row)$`.

---

## Clipboard

Pasting an image into the composer reads `wl-paste`, and `xclip` under X11. Without either, that
one gesture stops working; everything else is unaffected. It is in the pacman line above.

---

## Voice

```bash
bash install.sh --voice
```

`faster-whisper` and `sounddevice` into the same venv. The dictation model (`faster-whisper-small`,
~486 MB) is fetched by the window on the first click on the microphone, not by the installer.
`sounddevice` needs PortAudio from the distribution (`sudo pacman -S --needed portaudio`).

---

## Phone over Tailscale

```bash
bash install.sh --tailscale
curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh | bash -s -- --tailscale
```

Reads `tailscale status --json` and `tailscale serve status --json` (no sudo) and prints only the
steps still missing, in this order. It never runs them.

| state | printed |
|---|---|
| no `tailscale` | Arch/Omarchy and Arch-likes: `sudo pacman -S tailscale`; Debian/Ubuntu/Fedora/other: `curl -fsSL https://tailscale.com/install.sh \| sh` ([kb/1031](https://tailscale.com/kb/1031/install-linux)) |
| not running / not logged in | `sudo systemctl enable --now tailscaled`, `sudo tailscale up` |
| HTTPS off | [admin console → DNS](https://login.tailscale.com/admin/dns) → Enable HTTPS |
| no serve | `sudo tailscale serve --bg --https=443 http://127.0.0.1:<remote_port>` (8765 unless `remote_port` is set) |
| no phone in the tailnet | [iPhone](https://apps.apple.com/app/tailscale/id1470499037) · [Android](https://play.google.com/store/apps/details?id=com.tailscale.ipn) |
| ready | `https://<pc>.<tailnet>.ts.net/` |

Full setup and troubleshooting: [Phone over Tailscale](remote-tailscale.md).

---

## The tools get a ceiling of their own (#213, #218)

The server is not the only process that gets a scope. When `systemd-run` is on the PATH and the
user manager answers, two tools start their children in a transient user scope as well:

| | `render_page`'s browser (#213) | `run_command`'s shell (#218) |
|---|---|---|
| bounds | `MemoryHigh=5G`, `MemoryMax=6G`, `MemorySwapMax=0` | `MemoryHigh=7G`, `MemoryMax=8G`, `MemorySwapMax=0`, `OOMPolicy=kill` |
| move the bound | `CROW_RENDER_MEMORY_MAX=<size>` (`none` keeps only the swap cap) | `CROW_COMMAND_MEMORY_MAX=<size>` (`none` keeps only the swap cap) |
| switch off | `CROW_RENDER_SCOPE=0` | `CROW_COMMAND_SCOPE=0` |
| GPU only (#293) | default: the GPU when at least 512 MiB of VRAM are free; below that a local crow-nest serve is asked to lend the shortfall for the capture (#297, crow-nest#117), otherwise an ENVIRONMENT error and no image; `CROW_RENDER_GL=angle` skips that gate (`swiftshader` is refused); `CROW_RENDER_ANGLE=vulkan\|default` pins the ANGLE backend (default: vulkan, then default) | — |

Why: on 2026-09-21 a software-WebGL render of a 2 MB three.js page grew its headless Chromium to
54 GiB, froze the desktop, and the kernel's OOM killer shot the engine instead; on 2026-09-22 the
model started the same kind of browser 20 times through `run_command`. Why 8G for a command,
measured 2026-09-22 as each scope's own `memory.peak`: the diorama's three.js esbuild bundle
106 MiB, `npm ls --all` 46 MiB, node importing three 21 MiB, `test_crow_core` 109 MiB. With
`OOMPolicy=kill` a command at the ceiling dies whole, and the result says it was the ceiling; a
timeout or capture-cap kill takes the whole process group and the scope. systemd-run's own
`${VAR}`/`$$` expansion is switched off (`--expand-environment=no`, systemd 254 or newer).

Without `systemd-run` both run as before, bounded by their clocks and capture caps only;
`install.sh` warns about it in the preflight. The 8G ceiling does not scale with the machine's
RAM. Windows has no such scope (no Job Object yet).

---

## Optional helpers

None of these is installed by `install.sh`, and none is required. The preflight names each one
that is missing as a warning.

| | used for | without it |
|---|---|---|
| `node` | MCP servers started with `npx`/`node`; `node --check` over what `write_file`/`append_file`/`edit_file` wrote to a `.js`/`.mjs`/`.cjs` file or into an HTML page's inline scripts (#251) | MCP servers that need it cannot start; writes carry no syntax line, and the write itself is unaffected |
| an `esbuild` | `build_bundle` (#212): `$CROW_ESBUILD`, the `bundler` setting (#274), a project's `node_modules`, `PATH`, the deno (`~/.cache/deno`) and npx caches — never downloaded | `build_bundle` answers "no bundler found" with every place it looked, and writes nothing |
| `bwrap` | the in-window browser panel's web process runs sandboxed (#226); `CROW_PANE_SANDBOX=0` turns it off | the panel runs without a sandbox |
| `systemd-run` | the scopes above, and the server's own | no memory ceiling for render, command or server |

The syntax check parses without running (`node --check`), within one 5 s deadline per write,
skips files over 8 MiB and scripts past the 16th, and reports the first error only (line, message,
a 160-character window with a caret). Replayed on 2026-09-23: 20 of 98 JS/HTML writes of that
day's session would have carried their error.

---

## Troubleshooting

| symptom | what it is | what to do |
|---|---|---|
| The server and the whole terminal vanish during the load, `journalctl --user` says `systemd-oomd killed N process(es)` | oomd killed the terminal's scope under memory pressure (see "The server runs in a scope of its own") | update to 2.2.1 or newer; check the start line shows `systemd-run`; if `systemd-run` is missing, install it or set `CROW_SERVER_SCOPE=0` and accept the risk |
| The process dies before anything appears, `Gdk-Message: Error 71 (Protocol error) dispatching to Wayland display` | WebKitGTK's DMA-BUF renderer turns on Wayland explicit sync and then commits a buffer without an acquire point; Hyprland answers with a protocol error and a protocol error kills the connection | Already handled: `cli/crow_gui.py` sets `__NV_DISABLE_EXPLICIT_SYNC=1` **at import**, before `webview` is loaded. If you start the module some other way, export it yourself |
| The window opens and stays blank | the same renderer, one layer down | `WEBKIT_DISABLE_DMABUF_RENDERER=1 crow` — it drops the accelerated path, which is why it is not the default |
| Anything that wants real window coordinates, or a window kept above the rest | Wayland does not offer either | `CROW_GDK_BACKEND=x11 crow` — it sets `GDK_BACKEND`, and under XWayland those work again. The app id becomes `Crow`; the shipped rule matches both spellings |
| The window is tiled at a narrow width and the composer is cut off | the float rule is not loaded (it is optional) | add the line from the table above and `hyprctl reload` |
| `crow: this window needs pywebview` | the venv is not the one the launcher points at | `bash install.sh` again — it reuses the venv and repairs the launcher |
| `no llama-server to run. Tried: …` | the engine has not been built | `bash tools/build-llama-server.sh` |
| `model 'flash-next-q2-k-xl' is not on disk. Tried: …` | `<install>/models` points at the wrong tree, or the download is not finished | the message names every path it tried; `ls -l ~/.local/share/crow/models` says where the link goes, and `install.sh --models DIR` re-points it |
| A generic icon, or a window the launcher cannot name | the icon cache, or a `.desktop` entry from before the app id existed | `gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor`, then log out and in |
| `desktop-file-validate` hints about two main categories | `Categories=Development;Utility;` — the entry may appear in two menus | nothing. It is a hint, not an error |

---

## What was not verified

The pointer-driven drag and resize themselves: the bridge, the edge table and the GTK call are
covered by the suite, but synthesising a real button press against the compositor needs
privileges this machine does not have. The gestures were reasoned through and are unmeasured.
