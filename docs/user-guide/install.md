[← README](../../README.md) · [Docs index](../README.md)

# Install

One command per operating system. Neither installer asks for a password, and neither downloads
the model — that is a separate line, printed at the end of the run.

| | |
|---|---|
| Windows | `install.ps1` — five steps, no elevation, everything under `%LOCALAPPDATA%\Crow` |
| Linux | `install.sh` — five steps, no root, everything under `${XDG_DATA_HOME:-~/.local/share}/crow` |
| The model | `hf download`, separately, 73.45 GiB + 0.9 GiB for the projector |

---

## Requirements

| | |
|---|---|
| **GPU** | NVIDIA. The default operating point (crow-nest) needs Blackwell `sm_120` with 32 GB and 64 GB RAM. 16 GB is the installer's floor for the llama.cpp lines, unmeasured |
| **System RAM** | 32 GB for the 27B. **64 GB for Flash-Next** — `-ncmoe 30` keeps the experts of 30 of 48 layers in system RAM |
| **Disk** | ~2 GB for Crow, **73.45 GiB for the model** (3 shards) plus 0.9 GiB for the projector. The 27B is 16.35 GiB plus 0.9 |
| **OS** | Windows x64 · Linux x86_64 (Arch/Omarchy is what it was ported on and measured on) |
| **Python** | 3.9+ (`str.removesuffix` in the core). The terminal client uses the standard library only |
| **WebView2** | Window only, Windows. Ships with Windows 11 and with Edge |
| **WebKitGTK** | Window only, Linux. `webkit2gtk-4.1` + `python-gobject` from the distribution — neither installer asks for root |
| **wl-clipboard** | Linux only, and only for pasting an image into the window. `xclip` under X11 |
| **pywebview** | Window only, ~2 MB. Installed by `install.ps1` and by `install.sh` |
| **Node** | Optional, never required, installed by neither script. Used by MCP servers started with `npx` or `node`, and by the syntax check `write_file`/`append_file`/`edit_file` run over `.js`/`.mjs`/`.cjs` files and inline HTML scripts (`node --check`, 5 s, first error only, #251). Without node the check is skipped and the write result has no syntax line — the write itself is unaffected, on both systems. Both preflights report it as a warning |
| **esbuild** | Optional, for `build_bundle` (#212) and so for the [voxel kit](voxel-kit.md). Never downloaded: Crow uses one already on the machine — `$CROW_ESBUILD`, the `bundler` setting (#274), a project's `node_modules`, `PATH`, then the deno and npx caches. Without one, `build_bundle` says so and writes nothing |
| **bubblewrap** | Linux only, optional. The in-window browser panel's web process runs sandboxed only when `bwrap` exists (#226). The preflight warns without it |
| **Tailscale** | Optional, for the phone over HTTPS from anywhere (#249). Installed by neither script: `install.sh --tailscale` / `install.ps1 -Tailscale` print the missing steps. [download](https://tailscale.com/download) · [iPhone](https://apps.apple.com/app/tailscale/id1470499037) · [Android](https://play.google.com/store/apps/details?id=com.tailscale.ipn) · [Linux](https://tailscale.com/kb/1031/install-linux) · [Windows](https://tailscale.com/kb/1022/install-windows) · [setup](remote-tailscale.md) |
| **systemd-run** | Linux only, optional. With a reachable user manager, `render_page`'s browser (6 GiB) and `run_command`'s shell (8 GiB) run in a memory-bounded scope of their own (#213, #218); without it they are bounded by their clocks only. The preflight warns without it |

Every check that can reject the machine runs **before** the 506 MB download starts. Finding out
afterwards that the card is too small is the most expensive possible failure.

---

## Windows

```powershell
irm https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1 | iex
```

Preflight, download, extract, per-file sha256 against the release manifest, then the start lines
with paths resolved.

| does | does not |
|---|---|
| everything under `%LOCALAPPDATA%\Crow` | elevate — there is no administrator prompt |
| verifies every file against the release manifest | write to Program Files, the registry or `PATH` |
| installs **both** clients, the window and the terminal one | download the model, or start anything |

| flag | |
|---|---|
| `-InstallTo DIR` | install root, default `%LOCALAPPDATA%\Crow` |
| `-SourceUrl <url\|zip>` | take the package from somewhere other than the GitHub release |
| `-NoPause` | do not wait for ENTER at the end. The wait exists so the last screen can be read |
| `-Selftest` | run the checks against synthetic inputs, including the ones that must fail. Downloads nothing |
| `-PathTracer` | also switch on the `voxel-diorama` skill: path-traced voxel scenes with `kits\pathtracer` (shipped in every package). Verifies the bundle against `kit.json`, reports the esbuild `build_bundle` would use. On a current install it does only that — see [Voxel kit](voxel-kit.md) |
| `-Tailscale` | print what is still missing for the phone over HTTPS (`winget install --id Tailscale.Tailscale -e`, log in, Enable HTTPS, the `tailscale serve` line for an elevated shell, the phone app) and exit. Installs, downloads and elevates nothing — run it after the install: `&([scriptblock]::Create((irm https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1))) -Tailscale` |

There is no Start-menu entry: the last step prints the two start lines instead.

---

## Linux

```bash
curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh | bash
```

From a checkout it is the same script and the same five steps:

```bash
bash install.sh --models ~/Projects/models/qwen3.8-flash-next
```

Preflight, the files, a per-file sha256 manifest it re-reads on the next run, a
`--system-site-packages` venv with pywebview in it, `$CROW_HOME/bin/crow`, the `.desktop` entry,
the hicolor icons and the Hyprland rule. **It is idempotent and it removes nothing it did not
install** — the only files it deletes are the ones the previous manifest listed and the new
payload no longer ships, so `bin/`, `cuda/`, `src/`, `build/`, `venv/` and a model tree beside
them survive every re-run.

The GTK and WebKit bindings come from the distribution, so the installer **prints** the line
instead of running it — a script piped from the internet does not get a root password:

```bash
sudo pacman -S --needed python-gobject gtk3 webkit2gtk-4.1 wl-clipboard
```

The optional helpers — `node`, `bwrap`, `systemd-run` — are checked in the preflight and only
warned about; none of them stops the install.

| flag | |
|---|---|
| `--models DIR` | where the GGUFs live. Makes `$CROW_HOME/models` a link to it |
| `--voice` | also `faster-whisper` and `sounddevice` for the composer's microphone |
| `--tailscale` | also print what is still missing for the phone over HTTPS: the install line (`sudo pacman -S tailscale` on Arch, else kb/1031's script), `systemctl enable --now tailscaled`, `tailscale up`, Enable HTTPS, the `tailscale serve` line, the phone app. Reads `tailscale status --json` only; never runs sudo |
| `--pathtracer` | also switch on the `voxel-diorama` skill: path-traced voxel scenes with `kits/pathtracer` (shipped in every install). Verifies the bundle against `kit.json`, reports the esbuild `build_bundle` would use — see [Voxel kit](voxel-kit.md) |
| `--build-engine` | build `llama-server` now instead of printing the line (~20 minutes) |
| `--no-desktop` | no `.desktop` entry, no icons, no Hyprland rule |
| `--no-engine` | do not look for the engine at all |
| `--to DIR` | install root, same as `CROW_HOME=DIR` |
| `--selftest` | drive the script's own checks, including the ones that must fail. Installs nothing |

The engine is **built** rather than downloaded — the Windows package ships an `.exe` and there is
no Linux release asset. Full page: [Linux](linux.md).

---

## The model

**crow-nest, the default operating point.** The engine is its own repository and the container
one 104.7 GB file:

```bash
git clone https://github.com/nibor1896/crow-nest && cd crow-nest
hf download nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M Qwen3.8-Flash-Next-CNQ4.5-M.cnq --local-dir converter
cd engine && cargo build --release --bin serve && cd ..
```

Start it with `cd ~/Projects/crow-nest && tools/serve-linux.sh --port 8099` (Windows: `engine\target\release\serve.exe --port 8099`)
and point the window at it with `--base-url http://127.0.0.1:8099/v1`. Everything else:
[crow-nest](https://github.com/nibor1896/crow-nest) and [operating points](../operating-points.md#crow-nest--the-rust-engine).

Flash-Next GGUF on llama.cpp, the second operating point. Windows:

```powershell
hf download unsloth/Qwen3.8-Flash-Next-GGUF --include "*UD-Q2_K_XL*" --local-dir $env:LOCALAPPDATA\Crow\models\qwen-next-gguf
hf download unsloth/Qwen3.8-Flash-Next-GGUF mmproj-F16.gguf --local-dir $env:LOCALAPPDATA\Crow\models\qwen-next-gguf
```

Linux:

```bash
hf download unsloth/Qwen3.8-Flash-Next-GGUF --include "*UD-Q2_K_XL*" --local-dir ~/Projects/models/qwen3.8-flash-next
hf download unsloth/Qwen3.8-Flash-Next-GGUF mmproj-F16.gguf --local-dir ~/Projects/models/qwen3.8-flash-next
```

Three shards of 73.45 GiB total, plus 904,004,000 B for the projector.

The 27B, the third operating point (Windows paths shown):

```powershell
hf download unsloth/Qwen3.8-27B-GGUF --include "*UD-Q4_K_XL*" --local-dir $env:LOCALAPPDATA\Crow\models\qwen38-gguf
hf download unsloth/Qwen3.8-27B-GGUF mmproj-F16.gguf --local-dir $env:LOCALAPPDATA\Crow\models\qwen38-gguf
```

One file of 17,559,178,144 B and one of 927,607,488 B.

> **The second line of each pair is the vision projector, and the glob of the first does not catch
> it** — it sits in the repository ROOT, above the quant folder. Without it the server starts as a
> text model and `read_image` refuses with a sentence. `hf` prints `✓ Downloaded` even when it
> could not reach the repository, so check the byte counts.

**Where the tree goes.** On Windows the core looks in `<install>\models`. On Linux
`<install>/models` is a **link** to the tree, written by `install.sh --models DIR`; `$CROW_MODELS`
overrides it for one shell. A checkout is its own `<install>`, so give it the same link:

```bash
ln -s ~/Projects/models/qwen3.8-flash-next ~/Projects/crow/models
```

The tree may be flat or nested — the core tries the manifest's path under the models root and then
the file's basename directly under it.

---

## Updating

`Help → Settings → About` in the window: the version, the release check, and the button that
installs it. A restart is needed afterwards. The button runs the same installer as a fresh
install does — PowerShell with `install.ps1 -NoPause` on Windows, `bash install.sh` on Linux —
so re-running the command at the top of this page by hand is the same update.

---

## Where things live

Nothing is installed outside the user's own directories on either platform.

| what | Windows | Linux |
|---|---|---|
| install root | `%LOCALAPPDATA%\Crow` | `${XDG_DATA_HOME:-~/.local/share}/crow` |
| `settings.json`, `secrets.json`, `roots.json`, `USER.md`, `skills/`, `mcp.json`, `providers.json`, `approvals.json` | `%LOCALAPPDATA%\Crow\` | `~/.config/crow/` |
| `index.db` (session search) | `%LOCALAPPDATA%\Crow\` | `~/.local/share/crow/` |
| `session/`, `booted.json`, `git_events.json` | `%LOCALAPPDATA%\Crow\` | `~/.local/state/crow/` |
| server boot logs | `<cwd>\runs\` | `~/.local/state/crow/log/` |
| Crow's own log, `crow.log` (rotated, 1 MiB × 4) | `%LOCALAPPDATA%\Crow\log\` | `~/.local/state/crow/log/` |
| models | `<install>\models` | `<install>/models`, a link to the tree |
| engine binary | `<install>\bin\llama-server.exe` | `<install>/bin/`, then `PATH`, then `~/.local/share/crow/bin` |
| fonts | `%LOCALAPPDATA%\Microsoft\Windows\Fonts` + winreg | `~/.local/share/fonts/crow/` + `fc-cache` |
| launcher | — (the installer prints the start line) | `$CROW_HOME/bin/crow`, symlinked into `~/.local/bin` if that is on `$PATH` |
| desktop entry, icons | — | `~/.local/share/applications/crow.desktop`, `~/.local/share/icons/hicolor/<N>x<N>/apps/crow.png` |
| Hyprland rule | — | `~/.config/hypr/crow.lua` or `crow.conf`, and only if you add the line yourself |

Per-project state — `MEMORY.md`, `goal.json`, `root.json` — lives in `.crow/` inside the folder
the chat is bound to, not in any of the paths above.

**There is no uninstaller.** Removing Crow is removing those paths. The model tree is not one of
them: on Linux `<install>/models` is a link, so deleting the install root leaves the GGUFs where
they are.

---

## Next

| | |
|---|---|
| [Window](window.md) | the client, panel by panel |
| [Operating points](../operating-points.md) | the four measured lines, and the by-hand server commands |
| [Linux](linux.md) | paths, the engine build, the window on Wayland, troubleshooting |
| [Remote models](remote-models.md) | keys, sign-ins, dialects |
| [Phone over Tailscale](remote-tailscale.md) | the phone from anywhere over HTTPS; `--tailscale` / `-Tailscale` print the steps |
