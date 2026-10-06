[← README](../../README.md) · [Docs index](../README.md)

# Install

One command per operating system. Neither installer asks for a password, and neither downloads
the model — that is a separate line, printed at the end of the run.

| | |
|---|---|
| Windows | `install.ps1` — five steps, no elevation, everything under `%LOCALAPPDATA%\Crow` |
| Windows, one window | `CrowSetup.exe` from the [latest release](https://github.com/nibor1896/Crow/releases/latest): Crow, the crow-nest engine and the operating points you pick, with resume. See [CrowSetup.exe](#crowsetupexe-windows) |
| Linux | `install.sh` — five steps, no root, everything under `${XDG_DATA_HOME:-~/.local/share}/crow` |
| Linux, one window | `CrowSetup-linux-x64` from the [latest release](https://github.com/nibor1896/Crow/releases/latest): the same installer as `CrowSetup.exe`, for Linux. See [CrowSetup (Linux)](#crowsetup-linux) |
| The model | `hf download`, separately, 73.45 GiB + 0.9 GiB for the projector |

---

## Requirements

| | |
|---|---|
| **GPU** | NVIDIA. The default operating point (crow-nest) needs Blackwell `sm_120` with 32 GB and 64 GB RAM. 16 GB is the installer's floor for the llama.cpp lines, unmeasured |
| **System RAM** | 32 GB for the 27B. **64 GB for Flash-Next** — `-ncmoe 30` keeps the experts of 30 of 48 layers in system RAM |
| **Disk** | ~2 GB for Crow, **73.45 GiB for the model** (3 shards) plus 0.9 GiB for the projector. The 27B is 16.35 GiB plus 0.9 |
| **OS** | Windows x64 · Linux x86_64 (Arch/Omarchy is what it was ported on and measured on) |
| **Python** | 3.9+ (`str.removesuffix` in the core). |
| **WebView2** | Window only, Windows. Ships with Windows 11 and with Edge |
| **WebKitGTK** | Window only, Linux. `webkit2gtk-4.1` + `python-gobject` from the distribution — neither installer asks for root |
| **wl-clipboard** | Linux only, and only for pasting an image into the window. `xclip` under X11 |
| **pywebview** | Window only, ~2 MB. Installed by `install.ps1` and by `install.sh` |
| **Node** | Optional, never required, installed by neither script. Used by MCP servers started with `npx` or `node`, and by the syntax check `write_file`/`append_file`/`edit_file` run over `.js`/`.mjs`/`.cjs` files and inline HTML scripts (`node --check`, 5 s, first error only, #251). Without node the check is skipped and the write result has no syntax line — the write itself is unaffected, on both systems. Both preflights report it as a warning |
| **esbuild** | Optional, for `build_bundle` (#212) and so for the [voxel kit](voxel-kit.md). Never downloaded: Crow uses one already on the machine — `$CROW_ESBUILD`, the `bundler` setting (#274), a project's `node_modules`, `PATH`, then the deno and npx caches. Without one, `build_bundle` says so and writes nothing |
| **bubblewrap** | Linux only, optional. The in-window browser panel's web process runs sandboxed only when `bwrap` exists (#226). The preflight warns without it |
| **Tailscale** | Optional, for the phone over HTTPS from anywhere (#249). Installed by neither script: `install.sh --tailscale` / `install.ps1 -Tailscale` print the missing steps. [download](https://tailscale.com/download) · [iPhone](https://apps.apple.com/app/tailscale/id1470499037) · [Android](https://play.google.com/store/apps/details?id=com.tailscale.ipn) · [Linux](https://tailscale.com/kb/1031/install-linux) · [Windows](https://tailscale.com/kb/1022/install-windows) · [setup](remote-tailscale.md) |
| **systemd-run** | Linux only, optional. With a reachable user manager, `render_page`'s browser (6 GiB) and `run_command`'s shell (8 GiB) run in a memory-bounded scope of their own (#213, #218); without it they are bounded by their clocks only. The preflight warns without it |

### NVIDIA libraries

The packages carry no NVIDIA file. `CrowSetup` downloads cuBLAS/cuBLASLt (and on Linux the CUDA
runtime, plus NVRTC for the engine) from NVIDIA's own PyPI wheels at install time and puts them at
`<install>\bin\` (Windows) and `<install>/cuda/lib/` (Linux), under NVIDIA's licence, which you
accept there (see [NOTICE](../../NOTICE)). Without CrowSetup (the zip or tarball unpacked by
hand, or `install.ps1`/`install.sh` alone) fetch the same wheels and copy the named files:

```
pip download nvidia-cublas==13.6.0.2 nvidia-cuda-runtime==13.3.29 nvidia-cuda-nvrtc==13.3.33 --no-deps --only-binary=:all:
```

| file | wheel | goes to |
|---|---|---|
| `cublas64_13.dll`, `cublasLt64_13.dll` | `nvidia-cublas` 13.6.0.2 | `<install>\bin\` |
| `libcublas.so.13`, `libcublasLt.so.13` | `nvidia-cublas` 13.6.0.2 | `<install>/cuda/lib/` |
| `libcudart.so.13` | `nvidia-cuda-runtime` 13.3.29 | `<install>/cuda/lib/` |
| the NVRTC library | `nvidia-cuda-nvrtc` 13.3.33 | beside the engine's `serve` (`<install>/bin/` on Linux) |

A wheel is a zip file: open it and copy the files out.

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
| installs the window | download the model, or start anything |

| flag | |
|---|---|
| `-InstallTo DIR` | install root, default `%LOCALAPPDATA%\Crow` |
| `-SourceUrl <url\|zip>` | take the package from somewhere other than the GitHub release |
| `-NoPause` | do not wait for ENTER at the end. The wait exists so the last screen can be read |
| `-Selftest` | run the checks against synthetic inputs, including the ones that must fail. Downloads nothing |
| `-PathTracer` | also switch on the `voxel-diorama` skill: path-traced voxel scenes with `kits\pathtracer` (shipped in every package). Verifies the bundle against `kit.json`, reports the esbuild `build_bundle` would use. On a current install it does only that — see [Voxel kit](voxel-kit.md) |
| `-Tailscale` | print what is still missing for the phone over HTTPS (`winget install --id Tailscale.Tailscale -e`, log in, Enable HTTPS, the `tailscale serve` line for an elevated shell, the phone app) and exit. Installs, downloads and elevates nothing — run it after the install: `&([scriptblock]::Create((irm https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1))) -Tailscale` |

There is no Start-menu entry: the last step prints the two start lines instead.

### Image server (Windows)

`generate_image` and `edit_image` need `sd-server.exe` in `<install>\bin`. The package carries
it only when it was packed with `-SdBuildDir`; without it the pack prints
`image server: none` and both tools answer `the image server is not installed`. Build it on
Windows from the Linux builder's pin, with the same CUDA 13 toolkit as `llama-server.exe`; both
import `cublas64_13.dll`/`cublasLt64_13.dll`, which the package does not carry
([NVIDIA libraries](#nvidia-libraries)):

```powershell
git clone https://github.com/leejet/stable-diffusion.cpp sd.cpp; cd sd.cpp
git checkout master-920-2f88688      # 2f886889e6e8b78738d6b87f7191f6018557c551
git submodule update --init ggml thirdparty/libwebp thirdparty/libwebm
# in a shell that has run VS's vcvars64.bat (the "x64 Native Tools" prompt), same as llama.cpp
cmake -S . -B build -G "Ninja Multi-Config" -DSD_CUDA=ON -DSD_SERVER_BUILD_FRONTEND=OFF -DCMAKE_CUDA_ARCHITECTURES=120
cmake --build build --config Release --target sd-server sd-cli
.\tools\pack-release.ps1 -BuildDir <llama.cpp>\build\bin\Release -SdBuildDir <sd.cpp>\build\bin\Release
```

The generator is not optional. Without `-G`, CMake picks the Visual Studio generator, and that
one needs CUDA's MSBuild integration: without it configure stops at `No CUDA toolset found`
(measured with VS 18 and CUDA 13.3). Ninja calls `nvcc` directly, as the `llama-server.exe`
build does; `Ninja Multi-Config` still writes to `build\bin\Release`.

| | |
|---|---|
| measured | 2026-09-27, VS 18 Community, CUDA 13.3.73, RTX 5090 (`sm_120`) |
| build | 398 of 398 steps; `sd-cli.exe` 91.2 MB, `sd-server.exe` 91.4 MB |
| check | `sd-cli.exe --version` reads `master-920-2f88688, commit 2f88688`, run from the packed `bin\` with only `System32` on `PATH` |
| pack | 7 runtime libraries added, `msvcp140_codecvt_ids.dll` new with the image server; completeness OK |
| beside the 27B | Windows commit limit under WDDM: sd-server starts with `--mmap` on Windows (#320); 3 of 3 images beside the crow-nest 27B serve, 218 to 235 s, card peak 31,861 MiB (2026-09-28) |
| not yet run | the image tools from the Crow window on Windows |

`pack-release.ps1` takes only `sd-server.exe` and `sd-cli.exe` from that directory and resolves
their DLLs with `dumpbin` exactly as it does for `llama-server.exe`; a DLL already staged is not
copied twice. The two cuBLAS DLLs are the exception: the completeness check accepts exactly those
two names as provided at install time from NVIDIA and packs neither. `sd-server.exe` links
ggml-cuda statically and imports `cublasLt64_13.dll` directly. Upstream's `win-cuda12` zip is not used: it brings a second CUDA runtime (563 MB) and
its `sm_120` support is unverified (#314).

---

## CrowSetup.exe (Windows)

One window that installs Crow, the crow-nest engine and the operating points you pick, and
resumes where it stopped. `install.ps1` above stays the way to install Crow alone.

| installs | |
|---|---|
| Crow | the release package, always |
| NVIDIA libraries | `cublas64_13.dll` and `cublasLt64_13.dll` from NVIDIA's `nvidia-cublas` wheel into `<install>\bin\` ([NVIDIA libraries](#nvidia-libraries)) |
| crow-nest engine | the engine zip from the crow-nest release, always. Every model runs on it |
| operating points | any of Flash-Next (200k), 27B (128k), Image Stack, and on Windows the Media Stack (pictures and short videos). The optional llama.cpp section downloads nothing |
| Media Stack | its LTX-2.5 weights come from `Lightricks/LTX-2.5`, a gated Hugging Face repo: accept the licence there, then paste a read token into the field on the selection page (or set `HF_TOKEN`, or log in with the Hugging Face CLI). The token goes only to `https://huggingface.co` and is never logged. ComfyUI's own portable 7z is unpacked to `<install>\comfyui`. Needs 64 GB RAM and 100 GB free disk |
| Python | only when no Python 3.10+ is found (`py` launcher, `PATH`): the embeddable 3.13, pip, and `pywebview` (required), `faster-whisper`, `sounddevice` (voice, a missing one only warns) |

| | |
|---|---|
| resume | closing the window or a crash keeps the `.part` files and `%LOCALAPPDATA%\Crow\setup\state.json`. The next start re-hashes the partial file and continues by `Range`; at most the last 64 MB is fetched again |
| verify | a file is renamed into place only after its sha256 matches. A mismatch refetches that one file, once |
| retries | a download that gets no bytes for 30 s counts as stalled and is retried with 1 to 30 s backoff, without limit. `401`, `403` and `404` stop with a Retry button |
| order | the Crow package, the engine, small files, then the large containers. A file two points share is fetched once |
| blocked points | a point this machine cannot run stays visible with its reason in one line |
| configuration | `stack.json` and the [boot menu](boot.md) are the configuration. No environment variable is written |
| landed | shown only after every selected point resolves like `crow_boot.py` resolves it: files present with the right size and sha256, `serve.exe` and `sd-server.exe` start, and the boot menu plans the point |
| shortcuts | created through `crow_boot.py --create-shortcut`: the folder you chose and the Start menu |
| update | the version is compared, `models\` and user data are left alone, a locked file is renamed to `.old` |
| not done | no administrator prompt, no registry, no Apps & Features entry |

Install root: `%LOCALAPPDATA%\Crow`, models in `<install>\models` (the same layout as
[Where things live](#where-things-live)).

| flag | |
|---|---|
| `--headless` | no window: the installer without WebView2 (Windows 11 ships it, so this is the fallback) |
| `--source <dir>` | take the files from a local folder instead of Hugging Face and GitHub |
| `--install-root <dir>` | install root, default `%LOCALAPPDATA%\Crow` |
| `--package-source <dir>` | Crow's package and the engine package from `<dir>\<asset>`, checked against the embedded size and sha256; every other file from its URL (or `--source`) |
| `--points <ids>` | with `--headless`: the points to install (`flash-next`, `27b`, `image-stack`, `media-stack`) |
| `--shortcut-dir <dir>` | the shortcut goes into `<dir>` only, not the Desktop or the Start menu |
| `--no-shortcuts` | no shortcut at all |
| `--selftest` | run the checks, open no window, use no network. Exit code 0 is green |
| `--licenses` | print the third-party notices of everything compiled into the installer (the Rust crates and, on Windows, Microsoft's WebView2 loader) |

### Build it

```powershell
powershell -NoProfile -File installer\build.ps1 -CrowZip <crow-X-win-x64.zip> -EngineZip <crow-nest-engine-X-win-x64.zip>
powershell -NoProfile -File installer\build.ps1 -Selftest
```

| step | |
|---|---|
| vendor | the Python 3.13.16 embeddable zip and `get-pip.py` into `installer\vendor\`, each against a sha256 pinned in the script. The pip is the pypa/get-pip commit with pip 26.2.1, so the sha cannot move under a pin |
| `packages.json` | asset, bytes, sha256, version and release URL of the two zips; the exe embeds it |
| notices | `installer\THIRD-PARTY-NOTICES.txt`, generated from `installer\Cargo.lock` by `tools\installer_notices.py`; the exe embeds it and prints it with `--licenses` |
| build | `cargo build --release -p crowsetup --features bundle`, paths remapped, C runtime linked static |
| check | `crowsetup.exe --selftest` must exit 0 |
| privacy gate | `tools\repack-release.py` scans the exe for the builder's profile path, user name and host name, as UTF-8 and UTF-16. A hit refuses the build and nothing is copied |
| output | `installer\dist\CrowSetup.exe`, with its size and sha256 printed |

Needs Rust (edition 2024), Python 3 for the gate, and the network on the first run. `-Selftest`
needs neither the network nor `cargo`. CI builds without the `bundle` feature and runs
`cargo test` and `crowsetup --selftest` in `installer\`.

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
| `--build-image-server` | build `sd-server` + `sd-cli` for `generate_image`/`edit_image` (~3 minutes with the engine's CUDA toolkit) — see [Linux](linux.md#image-server) |
| `--no-desktop` | no `.desktop` entry, no icons, no Hyprland rule |
| `--no-engine` | do not look for the engine at all |
| `--to DIR` | install root, same as `CROW_HOME=DIR` |
| `--selftest` | drive the script's own checks, including the ones that must fail. Installs nothing |

The engine is **built** rather than downloaded — the Windows package ships an `.exe` and there is
no Linux release asset. Full page: [Linux](linux.md).

---

## CrowSetup (Linux)

`CrowSetup-linux-x64` is `CrowSetup.exe` built for Linux: the same window, the same points, the
same resume, verify and retry rules as [CrowSetup.exe](#crowsetupexe-windows).

```bash
chmod +x CrowSetup-linux-x64 && ./CrowSetup-linux-x64
./CrowSetup-linux-x64 --headless --points 27b,image-stack
```

| needs | |
|---|---|
| system | `webkit2gtk-4.1` and `gtk3` (the window and the binary link them), glibc 2.34+ (the engine) |
| Python | `python3` 3.10+ with `venv`, and `python-gobject` for the Crow window |
| display | X11 or Wayland. The window sets `__NV_DISABLE_EXPLICIT_SYNC=1` unless you set it, as the Crow window does: without it WebKitGTK dies on NVIDIA under Wayland |

```bash
sudo pacman -S --needed gtk3 webkit2gtk-4.1 python python-gobject
```

| installs | |
|---|---|
| Crow | `crow-<v>-linux-x64.tar.gz`: Crow and `bin/sd-server`, no NVIDIA file |
| NVIDIA libraries | `libcudart.so.13`, `libcublas.so.13`, `libcublasLt.so.13` into `cuda/lib/`, from NVIDIA's PyPI wheels ([NVIDIA libraries](#nvidia-libraries)) |
| crow-nest engine | `crow-nest-engine-<v>-linux-x64.tar.gz` into `bin/`: `serve` and the files its `MANIFEST.json` lists. Refused when the system glibc is older than the pack's `glibc_min` |
| Python | `<install>/venv` from the system `python3` with `--system-site-packages`, then `pywebview` (required), `faster-whisper`, `sounddevice` (voice, a missing one only warns) — as `install.sh` |
| shortcuts | desktop entries: "Crow Operating Points" (`crow-operating-points.desktop`) and "Crow" (`crow.desktop`) in `${XDG_DATA_HOME:-~/.local/share}/applications`; the folder you chose gets "Crow Operating Points" |

| | Windows | Linux |
|---|---|---|
| install root | `%LOCALAPPDATA%\Crow` | `${XDG_DATA_HOME:-~/.local/share}/crow` |
| models | `<install>\models` | `<install>/models` |
| setup state | `<install>\setup\state.json` | `<install>/setup/state.json` |
| a running binary on update | renamed to `.old` | replaced by rename, the running process keeps its file |
| `--source` on the same file system | copied | hard-linked after its sha256 matched; the source is never written |

| flag | |
|---|---|
| `--source <dir>` | as on Windows, plus: a file not at `<dir>/<repo>/<path>` is taken from `<dir>/<path under models/>` (a models tree). A folder that holds `qwen-image-2.1/text_encoder_sdcli/` complete is linked in and the convert step is skipped |
| `--package-source <dir>` | the two `.tar.gz` packages from `<dir>/<asset>` |
| all others | as [CrowSetup.exe](#crowsetupexe-windows) |

A local test install that downloads no model, from a models tree on the same file system:

```bash
./CrowSetup-linux-x64 --headless --points 27b,image-stack \
    --install-root ~/crow-test/crow --source ~/models/crow-stack \
    --package-source ~/crow-test/packs --no-shortcuts
```

### Build it (Linux)

```bash
bash tools/pack-release.sh --sd-server <sd-server>
bash installer/build.sh --crow-pack dist/crow-<v>-linux-x64.tar.gz --engine-pack crow-nest-engine-<v>-linux-x64.tar.gz
bash tools/pack-release.sh --selftest
bash installer/build.sh --selftest
```

| `tools/pack-release.sh` | |
|---|---|
| stage | the payload as `tools/repack-release.py` stages it, `bin/sd-server`; no NVIDIA file, nothing under `cuda/` |
| completeness | every `NEEDED` (`readelf -d`) is packed, a system library (glibc, libstdc++, libgcc, libgomp, the driver's `libcuda.so.1`) or one of the three named NVIDIA libraries CrowSetup downloads (`libcudart.so.13`, `libcublas.so.13`, `libcublasLt.so.13`). Any other missing library refuses |
| shipped set | `tools/repack-release.py` rules; `runs/`, `*.log` and the other excludes never ship |
| privacy gate | `$HOME`, `/home/<anyone>/`, the user name (bare too), the host name, `--private-pattern`, UTF-8 and UTF-16LE. The user name passes only where it is the project's public namespace (`github.com/<name>/`, `"repo": "<name>/`, the copyright line). A hit writes nothing |
| archive | regular files only, no owner in the headers, `MANIFEST.json` with forward slashes, read back against its manifest and gated again |

| `installer/build.sh` | |
|---|---|
| `packages-linux-x64.json` | asset, bytes, sha256, version and release URL of the two tarballs; the binary embeds it. No Python is embedded |
| build | `cargo build --release -p crowsetup --features bundle`, `$HOME`, `CARGO_HOME` and the repo remapped |
| check | `crowsetup --selftest` must exit 0 |
| privacy gate | `tools/pack-release.sh --gate` over the binary. A hit refuses the build and nothing is copied |
| output | `installer/dist/CrowSetup-linux-x64`, with its size and sha256 printed |

Needs Rust, the GTK 3 and WebKitGTK 4.1 development files, Python 3 and `readelf`.

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
