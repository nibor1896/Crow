[← README](../../README.md) · [Docs index](../README.md)

# Boot menu

Starts one operating point, then Crow. The crow-nest points and, on Windows, the Media Stack are the baseline; everything they need (binary, env, argv, port, readiness, menu text) comes from `manifests/stack.json`. Crow's llama.cpp lines are optional and listed below them. The boot menu has two faces over the same steps: the operating-point window (what the shortcut and the installer's **Open boot menu** open) and the terminal menu. It runs on Windows and Linux; what differs on Linux is under [Linux](#linux).

## Operating-point window

```
python cli\crow_boot.py --gui
```

Header **CROW · Operating points**. The shortcut runs it with `pythonw.exe`, so no console opens. On Windows it has its own taskbar button with the crow (AppUserModelID `Crow.OperatingPoints`), apart from Crow's chat window. Each point's line is `menu.gui` from `manifests/stack.json`; the terminal menu shows `menu.line`.

Everything to start is in one field (#396), in three groups: **Operating points** (this platform's; the Media Stack on Windows only), **Optional (llama.cpp)** (the installed lines), **Claude**. The chosen entry's line is under the field, with one **Start**. A point with a no-vision variant in `stack.json` also has a **Vision** switch: off starts that variant, and the line under the field is the variant's. The field starts on what runs, else on the first entry.

| Key on the field | |
|---|---|
| Down, Enter, Space | open the list on the chosen entry (Up and Home on the first, End on the last) |
| Up, Down, Home, End, PageUp, PageDown | move in the open list (PageUp and PageDown by 10) |
| Enter, Space, Tab, Alt+Up | take the entry and close |
| Escape | close without a change |
| a letter or a name | jump to the entry it starts |

| State | What it shows |
|---|---|
| Nothing runs | "Which model should Crow fly with?": the field, its line and **Start**. **Open Crow window** is greyed |
| Starting | "Flying to the nest. N s": the crow fills against the point's usual start time (the 27B and the Image Stack about 15 s, Flash-Next about 80 s, measured; GLM-5.3-Flash 60 s and the Media Stack 15 s, not measured) and is full when the server answers. The field shows the starting point and is disabled. **Cancel** stops what was started. Closing the window hides it; the start finishes and the contract file is written |
| Landed | the running point on top, blue, with its port, context and vision (`vision off` for a no-vision variant), and **Stop**; the field below it, on the running point. **Open Crow window** opens Crow's window on it (like **Start Crow** in the terminal menu) |
| A second start | **Start** on another point while one runs: "One model at a time.", the point needs the card for itself; stop the running one first |

A point that already runs when the window opens (started from the terminal, or by an earlier window) is shown as landed at once. A failed start shows its reason and the server log's path. If the window cannot open at all, the reason goes to `runs\crow-boot-gui.log`.

**Claude (subscription)** (#398) opens Crow on your Claude plan through Claude Code, without a local model, whether or not a point runs. Its state is asked in the background when the window opens (`claude --version`, `claude auth status`):

| The entry says | When | Button |
|---|---|---|
| Checking Claude Code... | until Claude Code has answered | none |
| Claude (subscription) refuses this turn: `<variable>` is set ... | `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_USE_BEDROCK` or `CLAUDE_CODE_USE_VERTEX` is set ([remote models](remote-models.md#claude-subscription)) | none |
| Claude Code is not installed: npm install -g @anthropic-ai/claude-code | `claude` is not on `PATH` | none |
| Sign in once with your Claude subscription. Claude Code opens Anthropic's sign-in in a terminal. | not signed in | **Sign in** |
| Claude Code bills an API key, not your subscription (or: runs on a cloud platform) | signed in, but not with the subscription | none |
| Your Claude plan through Claude Code. No local model needed. | signed in with the subscription | **Start** |

| | |
|---|---|
| Sign in | opens a terminal running the unmodified `claude auth login`: Windows Terminal when it is installed, else a console of its own; on Linux `$TERMINAL`, `x-terminal-emulator`, `gnome-terminal`, `konsole` or `xterm`, the first one found. You sign in there, in Anthropic's own flow; Crow reads nothing of it. The window asks `claude auth status` again every 3 s for up to 10 minutes, and the entry turns to **Start** once you are signed in |
| Start | sets Claude (subscription) as the active provider in `providers.json` and opens Crow's window. The bar says "The Crow window is opening on Claude (subscription)." The window's local model is the running server, else `http://127.0.0.1:8099/v1`, so a point started later from here answers when you switch back (`Settings → Model` → This machine, or `/model`). Turns stay on Claude until then |

## Terminal menu

```
python cli\crow_boot.py
```

```
  🐦  C R O W  boot menu
  ----------------------------------------------------
  ⚪ No operating point is running.

   1  🚀 Start Crow                             open the window on the running point
   2  🚀 Start Crow with Claude (subscription)  open the window on your Claude plan, no local model needed
   3  🧠 Qwen3.8-Flash-Next                     200k context — great for coding & vision
   4  🧠 Qwen3.8-Flash-Next · text only         200k context — text only, the vision tower's VRAM goes to experts
   5  ⚡ Qwen3.8-27B                            128k context — great speed, awesome for coding & vision
   6  ⚡ Qwen3.8-27B · text only                128k context — text only, without the vision tower
   7  🐋 GLM-5.3-Flash                          200k context — the big MoE, experts streamed from NVMe
   8  🎨 Image Stack                            27B + Ming-Image 0.1 Design — create AWESOME pictures
   9  🎬 Media Stack                            9B + Ming-Image 0.1 Design + LTX-2.5 — pictures and short videos

  Optional (llama.cpp)
  10  🦙 Qwen3.8-27B (optional)                 llama.cpp, port 8082
  11  🦙 Qwen3.8-Flash-Next (optional)          llama.cpp, port 8083

  12  🛑 Stop the running point
   0  👋 Quit
```

| Menu entry | What it does |
|---|---|
| Start Crow | opens the window with `--base-url` of what runs: a baseline point, or a llama-server (its port), and says which. Only when no model server runs it says so and starts nothing |
| Start Crow with Claude (subscription) | opens the window on your Claude plan through Claude Code, no local model needed, whether or not a point runs (#398): sets Claude (subscription) as the active provider and passes `--base-url` of what runs, else `http://127.0.0.1:8099/v1`. Claude Code is asked when you choose the line. Not signed in, it names `claude auth login` to run in a terminal and opens nothing; with a guard variable set, without Claude Code, or signed in with an API key or a cloud platform it says so and starts nothing ([operating-point window](#operating-point-window)) |
| Qwen3.8-Flash-Next | starts crow-nest's `serve` with the Flash-Next container (200k context) |
| Qwen3.8-Flash-Next · text only | the same point without the vision tower (#397): `CROW_VIT=0`, no `CROW_VIT_MMPROJ`, so the projector's and the image reserve's VRAM stay with the expert hot set (at most N 160). No images: `/props` says vision false, and Crow answers a pasted image with its no-vision sentence. **Not measured** |
| Qwen3.8-27B | starts `serve` with the 27B container at 131,072 context (`CROW_CONTEXT`; 200k waits for an 8-bit KV cache in crow-nest) |
| Qwen3.8-27B · text only | the 27B without the vision tower, at the base's 131,072 context (#397: `CROW_VIT=0`, no `CROW_VIT_MMPROJ`, no `CROW_CONTEXT` of its own). The ~1 GiB of VRAM the tower frees is not used by the dense model. **Not measured** |
| GLM-5.3-Flash | starts `serve` with the GLM-5.3-Flash container (200k context) and crow-nest's `arm4.env` operating set plus the three prefill-reuse switches `CROW_GLM_SMALL_PROMPT`, `CROW_GLM_ANSWER_REUSE`, `CROW_GLM_PREFIX_ANCHOR` (#365, 2026-10-12; needs crow-nest v0.12.0 or later, pinned v0.13.2) |
| Image Stack | starts the 27B at 65,536 context (room for the image model beside it: measured with Qwen-Image 2.1, **not measured** with Ming-Image), then `sd-server` with Ming-Image 0.1 Design once `serve` is ready. `edit_image` is not available on Ming-Image ([tools](../reference/tools.md#generate_image-and-edit_image-300-308-311)) |
| Media Stack | Windows only. Starts `llama-server` with Qwen3.5-9B Q8_0 and its projector on 8099 at 65,536 context. Crow's window warms `sd-server` when it opens; ComfyUI (LTX-2.5) starts on the first `animate_image`; for a clip the language model leaves the card and comes back afterwards ([operating points](../operating-points.md#media-stack--pictures-and-short-videos-windows)) |
| *(optional)* lines | a llama.cpp line from `manifests/operating-point.json` (ports 8081/8082/8083), started like Crow's own `start_server`: ready when `/props` answers, 600 s. Drawn dimmed; plain consoles show only the tag |
| Stop the running point | ends every model server the process scan sees (`serve`, `sd-server`, `llama-server`, ComfyUI), waits until each is torn down, removes the contract file |
| Quit | leaves the menu. A running point keeps running |
| *(engine update)* | not in this menu: the window's `Settings → About` (Settings at the foot of the rail) shows crow-nest's newest release and installs it into `bin\`, and refuses while a `serve` from there runs, so stop the point here first (#367, [install](install.md#updating)) |

| | |
|---|---|
| While starting | an animated line instead of the server log. Timeouts: Flash-Next and GLM-5.3-Flash 600 s, the 27B and the Media Stack's 9B 300 s, `sd-server` 300 s more, a llama.cpp line 600 s |
| Landed | shows for 5 s, then the menu comes back by itself |
| Failure or timeout | what was started is stopped, the last 10 log lines are shown |
| One point at a time | in both directions: a llama-server blocks a baseline start and a baseline point blocks an optional one. The message names what runs and how to stop it: the menu entry, `--stop`, or `taskkill /PID <pid> /F` |
| Which optional lines show | only those whose llama-server binary and GGUF are on disk (`%CROW_MODELS%` or `<install>\models`, `CROW_LLAMA_SERVER_<KEY>`); the others are left out |
| Contract file | `%LOCALAPPDATA%\Crow\active-point.json` (`point`, `base_url`, `started_at`, `pids`; `variant` only for a variant start, e.g. `"text"`), for the baseline points only. The window reads it. A point found by the process scan instead counts as its text-only variant when `/props` says `modalities.vision` false |
| Logs | `runs\serve-8099.log`, `runs\sd-server-8097.log`, `runs\llama-server-<port>.out.log` / `.err.log` under the folder the menu was started from (the shortcut starts it in the install folder). The previous run is kept as `.prev.log` |
| Without a modern console | plain ASCII, no colours, no animation. `NO_COLOR` drops only the colours |

## Flags

| Flag | |
|---|---|
| *(none)* | the menu |
| `--status` | what runs. Exit 0, or 1 when nothing runs |
| `--start <point>` | `flash-next`, `27b`, `image-stack`, or an optional line's key (`qwen35-q4-k-xl`, `flash-next-q2-k-xl`, `operating-point`). No animation when the output is not a terminal |
| `--variant <key>` | with `--start`: one of the point's variants from `stack.json`, today `text` for `flash-next` and `27b` (#397, not measured): `--start flash-next --variant text`. A key the point does not have is exit 2 |
| `--stop` | stop the running point |
| `--start-crow` | open the window on the running point |
| `--start-claude` | open the window on the Claude subscription, as the menu's Start Crow with Claude (subscription). Exit 1 when Claude Code is not ready, with the reason (signed out: `claude auth login`) |
| `--gui` | the operating-point window instead of the terminal menu |
| `--create-shortcut <folder>` | write `<folder>\Crow.lnk` (Windows) to the operating-point window |
| `--terminal` | with `--create-shortcut`: the shortcut opens the terminal menu instead |
| `--install-root <dir>` | the install root `${INSTALL}` (default `%LOCALAPPDATA%\Crow`) |
| `--models <dir>` | the models root `${MODELS}` (default `%CROW_MODELS%`, else `<install>\models`); also handed to the optional lines as `CROW_MODELS` |
| `--stack <file>` | another `stack.json` |

Exit codes: 0 done, 1 failed, 2 setup error (missing file, unknown point or variant), 3 refused because a point already runs.

## Linux

```bash
python3 cli/crow_boot.py --gui --models ~/Projects/models/crow-stack
```

| | Linux (#341) |
|---|---|
| Binaries | `<install>/bin/serve`, `<install>/bin/sd-server` (`binary.linux` in `stack.json`) |
| Libraries | `<install>/bin` (NVRTC beside `serve`) and `<install>/cuda/lib` (CUDA runtime and cuBLAS for `sd-server`, downloaded from NVIDIA's wheels by CrowSetup: [Install](install.md#nvidia-libraries)) go in front of `LD_LIBRARY_PATH` (`lib_path.linux` in `stack.json`) |
| Memory scope | `serve` and `sd-server` start in `systemd-run --user --scope` with the bounds the llama.cpp lines get ([Linux](linux.md#start)); `CROW_SERVER_SCOPE=0` starts the bare process |
| Install root | `~/.local/share/crow` (`$XDG_DATA_HOME/crow`) |
| Contract file | `~/.config/crow/active-point.json` |
| Logs | `~/.local/state/crow/log/serve-8099.log`, `sd-server-8097.log` |
| Stop by hand | `kill <pid>` |
| Window | GTK. `--create-shortcut` is Windows only |

## Shortcut

```
python cli\crow_boot.py --create-shortcut "%USERPROFILE%\Desktop"
```

| | |
|---|---|
| Target | `pythonw.exe` beside this Python running `crow_boot.py --gui` (the operating-point window, no console); this Python itself when there is no `pythonw.exe`. `--install-root`, `--models` and `--stack` are carried along |
| With `--terminal` | the terminal menu: Windows Terminal (`wt.exe`) running this Python with `crow_boot.py`; plain `python.exe` when Windows Terminal is not installed |
| Working folder | the install root |
| Icon | `cli\crow.ico` |
| Other folders | any folder works: the Start menu is `%APPDATA%\Microsoft\Windows\Start Menu\Programs` |
