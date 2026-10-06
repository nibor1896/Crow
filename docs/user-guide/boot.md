[← README](../../README.md) · [Docs index](../README.md)

# Boot menu

Starts one operating point, then Crow. The crow-nest points and, on Windows, the Media Stack are the baseline; everything they need (binary, env, argv, port, readiness, menu text) comes from `manifests/stack.json`. Crow's llama.cpp lines are optional and listed below them. The boot menu has two faces over the same steps: the operating-point window (what the shortcut and the installer's **Open boot menu** open) and the terminal menu. It runs on Windows and Linux; what differs on Linux is under [Linux](#linux).

## Operating-point window

```
python cli\crow_boot.py --gui
```

Header **CROW · Operating points**. The shortcut runs it with `pythonw.exe`, so no console opens. On Windows it has its own taskbar button with the crow (AppUserModelID `Crow.OperatingPoints`), apart from Crow's chat window. Each point's line is `menu.gui` from `manifests/stack.json`; the terminal menu shows `menu.line`.

| State | What it shows |
|---|---|
| Nothing runs | "Which model should Crow fly with?": the points of this platform with a Start button each (the Media Stack on Windows only), the optional llama.cpp lines dimmed below them. **Open Crow window** is greyed |
| Starting | "Flying to the nest. N s": the crow fills against the point's usual start time (the 27B and the Image Stack about 15 s, Flash-Next about 80 s, measured; the Media Stack 15 s, not measured) and is full when the server answers. The other points are disabled. **Cancel** stops what was started. Closing the window hides it; the start finishes and the contract file is written |
| Landed | the running point on top, blue, with its port, context and vision, and **Stop**. **Open Crow window** opens Crow's window on it (like **Start Crow** in the terminal menu) |
| A second start | "One model at a time.": the point needs the card for itself; stop the running one first |

A point that already runs when the window opens (started from the terminal, or by an earlier window) is shown as landed at once. A failed start shows its reason and the server log's path. If the window cannot open at all, the reason goes to `runs\crow-boot-gui.log`.

## Terminal menu

```
python cli\crow_boot.py
```

```
  🐦  C R O W  boot menu
  ----------------------------------------------------
  ⚪ No operating point is running.

   1  🚀 Start Crow                     open the window on the running point
   2  🧠 Qwen3.8-Flash-Next             200k context — great for coding & vision
   3  ⚡ Qwen3.8-27B                    128k context — great speed, awesome for coding & vision
   4  🎨 Image Stack                    27B + Qwen-Image 2.1 — create AWESOME pictures
   5  🎬 Media Stack                    9B + Qwen-Image 2.1 + LTX-2.5 — pictures and short videos

  Optional (llama.cpp)
   6  🦙 Qwen3.8-27B (optional)         llama.cpp, port 8082
   7  🦙 Qwen3.8-Flash-Next (optional)  llama.cpp, port 8083

   8  🛑 Stop the running point
   0  👋 Quit
```

| Menu entry | What it does |
|---|---|
| Start Crow | opens the window with `--base-url` of what runs: a baseline point, or a llama-server (its port), and says which. Only when no model server runs it says so and starts nothing |
| Qwen3.8-Flash-Next | starts crow-nest's `serve` with the Flash-Next container (200k context) |
| Qwen3.8-27B | starts `serve` with the 27B container at 131,072 context (`CROW_CONTEXT`; 200k waits for an 8-bit KV cache in crow-nest) |
| Image Stack | starts the 27B at 65,536 context (room for Qwen-Image beside it), then `sd-server` with Qwen-Image 2.1 once `serve` is ready |
| Media Stack | Windows only. Starts `llama-server` with Qwen3.5-9B Q8_0 and its projector on 8099 at 65,536 context. Crow's window warms `sd-server` when it opens; ComfyUI (LTX-2.5) starts on the first `animate_image`; for a clip the language model leaves the card and comes back afterwards ([operating points](../operating-points.md#media-stack--pictures-and-short-videos-windows)) |
| *(optional)* lines | a llama.cpp line from `manifests/operating-point.json` (ports 8081/8082/8083), started like Crow's own `start_server`: ready when `/props` answers, 600 s. Drawn dimmed; plain consoles show only the tag |
| Stop the running point | ends every model server the process scan sees (`serve`, `sd-server`, `llama-server`, ComfyUI), waits until each is torn down, removes the contract file |
| Quit | leaves the menu. A running point keeps running |

| | |
|---|---|
| While starting | an animated line instead of the server log. Timeouts: Flash-Next 600 s, the 27B and the Media Stack's 9B 300 s, `sd-server` 300 s more, a llama.cpp line 600 s |
| Landed | shows for 5 s, then the menu comes back by itself |
| Failure or timeout | what was started is stopped, the last 10 log lines are shown |
| One point at a time | in both directions: a llama-server blocks a baseline start and a baseline point blocks an optional one. The message names what runs and how to stop it: the menu entry, `--stop`, or `taskkill /PID <pid> /F` |
| Which optional lines show | only those whose llama-server binary and GGUF are on disk (`%CROW_MODELS%` or `<install>\models`, `CROW_LLAMA_SERVER_<KEY>`); the others are left out |
| Contract file | `%LOCALAPPDATA%\Crow\active-point.json` (`point`, `base_url`, `started_at`, `pids`), for the baseline points only. The window reads it |
| Logs | `runs\serve-8099.log`, `runs\sd-server-8097.log`, `runs\llama-server-<port>.out.log` / `.err.log` under the folder the menu was started from (the shortcut starts it in the install folder). The previous run is kept as `.prev.log` |
| Without a modern console | plain ASCII, no colours, no animation. `NO_COLOR` drops only the colours |

## Flags

| Flag | |
|---|---|
| *(none)* | the menu |
| `--status` | what runs. Exit 0, or 1 when nothing runs |
| `--start <point>` | `flash-next`, `27b`, `image-stack`, or an optional line's key (`qwen35-q4-k-xl`, `flash-next-q2-k-xl`, `operating-point`). No animation when the output is not a terminal |
| `--stop` | stop the running point |
| `--start-crow` | open the window on the running point |
| `--gui` | the operating-point window instead of the terminal menu |
| `--create-shortcut <folder>` | write `<folder>\Crow.lnk` (Windows) to the operating-point window |
| `--terminal` | with `--create-shortcut`: the shortcut opens the terminal menu instead |
| `--install-root <dir>` | the install root `${INSTALL}` (default `%LOCALAPPDATA%\Crow`) |
| `--models <dir>` | the models root `${MODELS}` (default `%CROW_MODELS%`, else `<install>\models`); also handed to the optional lines as `CROW_MODELS` |
| `--stack <file>` | another `stack.json` |

Exit codes: 0 done, 1 failed, 2 setup error (missing file, unknown point), 3 refused because a point already runs.

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
