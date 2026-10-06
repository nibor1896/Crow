# Changelog

Released history. Every number carries the conditions it was taken under, or says it is unmeasured.
The reasoning is in the commit and on the issue.

## Unreleased

## 3.2.8 — 2026-10-06

**The README no longer offers a Linux download that does not exist; Crow behaves exactly as v3.2.7.** CrowSetup still installs engine v0.9.5. Windows assets only, as for v3.2.x.

### Fixed

- **No Linux one-window download in the README** (`ce61afe`, 2026-10-06). The "Linux, one window" command fetched `releases/latest/download/CrowSetup-linux-x64`, which answers 404 since v3.2.0: the releases carry Windows assets only. The block is gone and Linux keeps `install.sh`. `docs/user-guide/install.md` and the README image say that `CrowSetup-linux-x64` is built on Linux ([Build it (Linux)](docs/user-guide/install.md#build-it-linux)) and run with `--package-source` on the two packages built beside it.
- **The README image's alt text counts 31 tools**, as the image and `crow_core.BUILTIN_TOOLS` do; it said 30 (2026-10-06).
- **Version 3.2.8** in `cli/crow_core.py`, `install.ps1` and `manifests/operating-point.json`; README image regenerated.

### Added

- **Measurement harnesses for #339 and #346, prepared before any GPU run** (`31bcbe6`, `039ea02`, 2026-10-06). No user-visible change, and none of it ships in the package. #339: `tools/measure_negative_cfg.py` and `runs/339-negative-cfg/PREREG.md` for a negative prompt and `txt_cfg` above 1.0 in `generate_image`. #346: `tools/enhance_ab.py`, `runs/340-enhance-ab/PREREG.md` and three arm workflows for LTX prompt enhance in `animate_image`. The GPU runs and the blind judging wait for the owner's go.

## 3.2.7 — 2026-10-06

**v3.2.6 made Flash-Next half as fast in Crow; CrowSetup now installs engine v0.9.5, which undoes it.** Windows assets only, as for v3.2.x.

### Fixed

- **Flash-Next is back to full speed** (2026-10-06). Engine v0.9.4, which CrowSetup v3.2.6 installed, set `CROW_STAGE_PAR=1` by default and halved Flash-Next on Crow's requests on Windows: decode 20.4–24.1 tok/s and cold prefill 256–297 tok/s at 7.5–9.3k context, against 39.0–41.1 tok/s and 554 tok/s that morning. With the flag off, the same engine read 39.3–41.4 tok/s. CrowSetup installs engine v0.9.5, which no longer sets it. The "+6.7 %" in v3.2.6 came from a greedy test without streaming and tools and did not hold in Crow.
- **README image and `docs/operating-points.md`** show the decode of a live Crow session (≈40 tok/s at 8k) instead of that test figure.
- **Version 3.2.7** in `cli/crow_core.py`, `install.ps1` and `manifests/operating-point.json`.

## 3.2.6 — 2026-10-06

**Flash-Next decodes 6.7 % faster on Windows: CrowSetup installs engine v0.9.4.** The phone over Tailscale is set up and checked on Windows. Windows assets only, as for v3.2.x.

### Changed

- **CrowSetup installs engine v0.9.4** (crow-nest, 2026-10-06): `serve` stages cold experts on a side stream by default (`CROW_STAGE_PAR`). Measured on Windows (Flash-Next, 31,827-token prompt, greedy, 1,024 tokens, 6 runs per arm): 43.08 -> 45.97 tok/s decode, the same answer text in all runs.
- **Flash-Next's reasoning budget stays 1024, now measured** (#245, 2026-10-06): `flash-next-cnq45-m._reasoning_budget_status` holds the series. 36 rounds per arm on robin's 2026-09-15 session: no-call 0 / 0, corrupt 0 / 0, median 26.5 s per round at 1024 against 34.7 s at 2048 (1.31x). Owner decision: 1024 stays, 2048 is slower and fixes nothing.
- **Operating-point figures for Windows after the PLE fix** in `docs/operating-points.md` and the README image: 46.0 tok/s at 32k with engine 0.9.4, 39.3–48.1 tok/s from 100k to 175k with 0.9.3, cold prefill 775.6–788.5 tok/s (2026-10-06).
- **Version 3.2.6** in `cli/crow_core.py`, `install.ps1` and `manifests/operating-point.json`; README image regenerated.

### Measured

- **The phone over Tailscale works on Windows** (#249, 2026-10-06): Tailscale 1.102.4 on robin's Windows PC `zephirot` in the tailnet `tail77dcd2.ts.net`, `tailscale serve --bg --https=443 http://127.0.0.1:8765`; Crow's `tailscale_state` reads `ready`; robin opened the mirror on the iPhone and reported it working. No code change: the guide in `docs/user-guide/remote-tailscale.md` held as written.

### Known limitations

- **No Linux assets**, as for v3.2.5.

## 3.2.5 — 2026-10-06

**CrowSetup stops instead of starting over when it cannot read its state file, installing on Windows accepts Microsoft's terms for the Visual C++ runtime, and the engine no longer refuses a start over a reused PID.** CrowSetup installs engine v0.9.3. Windows assets only, as for v3.2.x.

### Changed

- **Installing Crow on Windows accepts Microsoft's terms for the Visual C++ runtime it carries** (2026-10-06). The package has shipped five unmodified Microsoft DLLs in `bin\` since v2.0.0 (`msvcp140`, `msvcp140_codecvt_ids`, `vcomp140`, `vcruntime140`, `vcruntime140_1`). The Visual Studio 2026 licence (last updated October 1, 2025, "Distribution Requirements") lets them be redistributed only if end users agree to terms that protect them at least as much; until now `NOTICE` only said so. CrowSetup's selection page now names the Microsoft Visual C++ v14 Redistributable and Runtime license terms under Crow, every licence name with a URL opens it in the browser (`open_licence`, only URLs from `stack.json`), and a line above Install says that Install accepts the terms named on the page. `--headless` and `install.ps1` print the terms before anything is written. `manifests/stack.json` gains the licence `msvc-v14-runtime` and `package_licenses` (Windows only); `tools/check_stack.py` checks them (new check "package licences", 6 tests). `NOTICE` and `docs/user-guide/install.md` say the same.

- **CrowSetup installs engine v0.9.3** (crow-nest, 2026-10-06): the engine lock is an OS file lock that Windows releases with the process, so a `serve` stopped with `taskkill /F` no longer blocks the next start once its PID is reused (robin's Flash-Next start at 11:40 exited with code 101, "another engine (pid 29192)", while no engine ran); `CROW_RAM_MARGIN_GB` defaults to 1 GiB.
- **Version 3.2.5** in `cli/crow_core.py`, `install.ps1` and `manifests/operating-point.json`; README image regenerated.

### Fixed

- **CrowSetup no longer starts over silently when it cannot read its state file** (#338, 2026-10-06). Up to v3.2.4 an I/O error on `setup\state.json` became an empty state without a message, and a failed save was dropped: on 2026-10-01 two window runs against a valid prepared `state.json` fetched the 27B projector again (927,607,488 B, already verified) and demanded convert inputs the done convert step had deleted. Now a `state.json` that exists but cannot be read stops the run with its path and the OS error; a corrupt one is still set aside as `state.json.bad`. A failed save keeps the run going and shows one warning, "Progress is not being saved to <path>: <error>"; the window shows it as a "Progress file" row and asks to keep the window open. Both lines are appended with a UTC timestamp to `setup\setup.log`. Why the 2026-10-01 runs could not use the file is still not found; the log is the evidence the next such run leaves.

### Known limitations

- **No Linux assets**, as for v3.2.4: a Linux package needs a build on Linux. The `#[cfg(unix)]` paths of CrowSetup's `nvidia` step are still not compiled.
- **Not checked live: the "Progress is not being saved" warning** (#338), which only appears once Install has started downloads; covered by `failed_save_warns_once_and_still_lands`.

## 3.2.4 — 2026-10-06

**Crow ships no NVIDIA file; the installers fetch NVIDIA's CUDA libraries from NVIDIA's own wheels.** The Windows package no longer carries `cublas64_13.dll` and `cublasLt64_13.dll` (≈516 MB unpacked), the Linux package no longer carries `cuda/lib/`, and the CUDA-EULA redistribution question is gone with them.

### Changed

- **CrowSetup downloads the CUDA libraries from PyPI** (`78de323`, `956ff4c`, 2026-10-06). `manifests/stack.json` gains `nvidia_files`: `nvidia-cuda-nvrtc` 13.3.33, `nvidia-cublas` 13.6.0.2 and, on Linux, `nvidia-cuda-runtime` 13.3.29, each pinned by URL on files.pythonhosted.org, bytes and sha256. A wheel is fetched when a selected point runs one of its servers: `serve` needs NVRTC, `llama-server` and `sd-server` need cuBLAS. A new `nvidia` step extracts only the named members into the paths the packages used (`bin/`; Linux `cuda/lib/`), checks each against the wheel's `RECORD` and the pinned sha256, refuses member paths that leave the wheel or targets outside the install root, writes NVIDIA's licence text to `licenses/NVIDIA-CUDA-EULA.txt`, and deletes the wheel. Every pinned member sha256 equals the DLL that shipped up to v3.2.3. The install page shows the NVIDIA CUDA EULA as a licence the user accepts. Older packages that still contain the files install unchanged. `tools/check_stack.py` validates the new section (127 tests).
- **`install.ps1` fetches cuBLAS the same way** (`e2a128a`): the pinned Windows `nvidia-cublas` wheel, verified before anything under the install folder is touched. `install.sh` needs nothing: it builds from source against NVIDIA's redist archives.
- **`pack-release.ps1` / `.sh` / `repack-release.py` stage no NVIDIA library** (`a059909`). The import-closure check accepts exactly `cublas64_13.dll` and `cublasLt64_13.dll` as provided at install time and still refuses any other missing DLL; staging an NVIDIA file refuses. `NOTICE` and `docs/user-guide/install.md` say where the libraries come from, with the `pip download` line for a manual install.

- **CrowSetup installs engine v0.9.2**, the crow-nest package without NVRTC (3.5 MB instead of 48.9 MB).
- **Version 3.2.4** in `cli/crow_core.py`, `install.ps1` and `manifests/operating-point.json`; README image regenerated.

### Measured

- **A real CrowSetup run fetched the wheels** (2026-10-06, headless, `--points 27b,media-stack`, over the live install with the four NVIDIA DLLs removed from `bin\` first): `nvidia-cuda-nvrtc` 13.3.33 (3 files written: both DLLs and the EULA) and `nvidia-cublas` 13.6.0.2 (2 written, 1 already in place) came from files.pythonhosted.org, both wheels were deleted after extraction, `licenses\NVIDIA-CUDA-EULA.txt` (59,262 B) landed, the check passed ("Landed. Crow is ready."), and all four DLLs are byte-identical to the ones removed.
- **Older release assets are deleted** (owner decision 2026-10-06): every earlier `crow-*-win-x64.zip` and the v3.1.0 Linux package carried NVIDIA libraries.

### Known limitations

- **The `#[cfg(unix)]` paths of the new installer step are not compiled** (2026-10-06): the Linux target check stops at `zstd-sys` and `ring` for want of a cross-gcc. They need a build on Linux.
- **No Linux assets.** The v3.1.0 Linux package carried `cuda/lib/` and is withdrawn with the other old packages (owner decision 2026-10-06); a Linux package needs a build on Linux. Windows assets only, as for v3.2.x.

## 3.2.3 — 2026-10-05

**Flash-Next boots on Windows again with crow-nest v0.9.1, and Crow's Flash-Next figures name the run they come from.** CrowSetup installs engine v0.9.1, which no longer takes `whisper-small`'s config for Flash-Next's, no longer runs a tool call the model only wrote inside its reasoning, and names the page file a Flash-Next boot needs on Windows. Windows assets only, as for v3.2.x.

### Fixed

- **CrowSetup installs crow-nest v0.9.1** (2026-10-05). Since the Media Stack put `models\whisper-small\config.json` beside the other models (2026-10-01), every Flash-Next boot on v0.8.0 ended with exit 101: the engine took the lone config under `models\` as the container's own and its metadata gate refused it. v0.9.1 fixes that, stops executing a `<tool_call>` written inside a think block, and refuses a cold tier past the Windows commit limit by name before it allocates it (crow-nest CHANGELOG v0.9.1).
- **Context clearing counts an image the way crow-nest resizes it** (`768c299`, 2026-10-05). On the `flash-next` and `27b` points every picture costs the engine 1,024 to 1,280 visual tokens (crow-nest `vit.rs` `smart_resize`, factor 32, 1024..1280 tokens), while Crow counted one token per 32×32 px, so an 800×450 render was booked at 350 instead of 1,032. `_image_tokens` now follows the engine's rule when the served model is a crow-nest container; every other server keeps the 32×32 grid, and an unreadable image still counts 0. Six tests pin the engine's own grids.

### Changed

- **Flash-Next figures name their run and the PLE fix** (`6be0e03`, 2026-10-05). The README, its generated image and `docs/operating-points.md` headline the newest measurement after crow-nest's PLE fix of 2026-09-23 (`85a48e7`): 35.8 tok/s decode at 122k context (Linux, 2026-09-24, hot set `crow0924`, runs 35.6 / 35.8 / 35.8). The 45.1 tok/s Windows figure (2026-09-13) and the Linux 36.8 / 42.5 figures are kept only as "before the PLE fix". "Greedy ids bit-identical" now says it means run to run. The prefill default names its runs (771.3 = mean of three crow-nest runs; llama.cpp 922.7 from its raw records), the quality line reads 2/5/3 against llama.cpp's 2/6/2, and "accepted live at 41.8" is corrected to the recorded 42.70 and 41.48 (#182). `manifests/stack.json` cites crow-nest `geo.rs:233` for the context floor, and `manifests/operating-point.json` names the b10687 abort log that exists in crow-lab.

### Measured

- **Windows charges VRAM and pinned memory 1:1 against commit** (2026-10-05, robin's machine, RTX 5090, 63.38 GiB RAM, no page file): 20 × 1 GiB `cuMemAlloc` took 20 GiB of commit, 41 × 1 GiB pinned host blocks took 41 GiB. A Flash-Next boot needs about 95 GiB of commit, so on a 64 GB machine it needs a page file of about 40 GiB; the other operating points fit without one.

### Known limitations

- **Flash-Next on Windows needs a page file** of about 40 GiB on a 64 GB machine (see Measured). Without one, engine v0.9.1 refuses the boot by name instead of running out mid-load. The Windows boot with a page file is not yet verified live.
- **Windows has no Flash-Next speed measured since the PLE fix**; the headline figure is Linux.

## 3.2.2 — 2026-10-03

**CrowSetup carries its licence notices.** From v3.0.0 to v3.2.1 `CrowSetup.exe` shipped without the notices of the Rust crates compiled into it and of Microsoft's WebView2 loader it links statically. This release adds them, inside the exe (`CrowSetup --licenses`) and as `installer/THIRD-PARTY-NOTICES.txt`; installing works exactly as in v3.2.1. Windows assets only, as for v3.2.x.

### Fixed

- **CrowSetup carries its third-party notices** (#350, 2026-10-03). The installer binary compiles in Rust crates under MIT, Apache-2.0, BSD, ISC, Zlib, Unicode-3.0, CDLA-Permissive-2.0 and bzip2-1.0.6 terms, and on Windows Microsoft's WebView2 loader (linked statically from Microsoft.Web.WebView2 1.0.3800.47), but shipped without their notices. `installer/THIRD-PARTY-NOTICES.txt` now lists every crate of the Windows and Linux release builds (209 together: 145 on Windows, 190 on Linux) with each licence text the crate ships (the Apache-2.0 terms once per wording plus each crate's own copyright lines, 5,457 lines), and `CrowSetup --licenses` prints it from inside the exe. `tools/installer_notices.py` generates the file from `installer/Cargo.lock` and holds it there in CI; the five crates without a licence file of their own (webview2-com, -sys, -macros, dlopen2, dlopen2_derive) and Microsoft's texts are vendored byte for byte under `installer/licenses/` with source and sha256. The check also evaluates each crate's SPDX expression against the texts it ships ("A AND B" needs both). It found one MPL-2.0 crate in the Linux build, option-ext 0.2.0 (via wry → dirs → dirs-sys); as MPL-2.0 §3.2(a) asks, the notices name its unmodified source on crates.io with the sha256 from `Cargo.lock`. `NOTICE` names the installer, the embedded Python package and get-pip.py.

- **`NOTICE` names the Microsoft C++ runtime in the Windows package** (2026-10-03). Since v2.0.0 (`a7dd737`) `bin\` carries `msvcp140.dll`, `msvcp140_codecvt_ids.dll`, `vcomp140.dll`, `vcruntime140.dll` and `vcruntime140_1.dll`, because the llama.cpp and stable-diffusion.cpp binaries import them; `NOTICE` never mentioned them. All five are byte-identical to Visual Studio Community 2026's `VC\Redist\MSVC\14.51.36231\x64` files and stay under Microsoft's terms. The stable-diffusion.cpp entry now also names `sd-cli.exe`, which ships beside `sd-server.exe`.

## 3.2.1 — 2026-10-03

**The Media Stack installs to the end.** v3.2.0's `CrowSetup.exe` stopped every Media Stack install at its last check, after all files and the video runtime were in place.

### Fixed

- **CrowSetup no longer asks for the ComfyUI archive it deleted** (#348, 2026-10-03). The runtime step unpacks `ComfyUI_windows_portable_nvidia.7z` and deletes it, but the check still required it, so the install ended with "media-stack is not complete: missing: …ComfyUI_windows_portable_nvidia.7z" and Retry failed the same way. The boot menu's plan now names the archives a runtime consumes, and the check asks for the unpacked ComfyUI program instead. Found by the v3.2.0 deployment check (released `CrowSetup.exe --headless` on robin's machine); the regression tests are red without the fix.

## 3.2.0 — 2026-10-03

**Crow makes short videos.** The new Media Stack operating point (Windows) puts Qwen3.5-9B, Qwen-Image 2.1 and LTX-2.5 on one card, and `animate_image` turns a still into an MP4 with sound that plays in the window. CrowSetup installs it from the original sources, with the user's own Hugging Face token for the gated LTX weights, and unpacks ComfyUI as the video runtime. The first live run on robin's RTX 5090 (2026-10-03, n=1) rendered a 5 s clip in 73.3 s and brought the language model back 8 s after ComfyUI ended. This release ships Windows assets only; on Linux, v3.1.0 stays the install.

### Added

- **The Media Stack operating point: pictures and short videos on one card** (#340, Windows). Qwen3.5-9B Q8_0 with its projector on llama-server; Qwen-Image 2.1 on sd-server, warmed when Crow's window opens (#300); LTX-2.5 (distilled, int8) on ComfyUI v0.38.0, started on the first clip. Pictures and videos never share the card. #340 Phase 0 (RTX 5090) measured VRAM at up to 32,049 of 32,607 MiB during a clip, and host RAM at up to 50,868 MiB machine-wide during a 20 s clip. CrowSetup therefore asks for 64 GB RAM for this point. Every file comes from its original source, and nothing foreign is mirrored. The LTX weights come from `Lightricks/LTX-2.5`, which is gated: CrowSetup sends the user's own Hugging Face token, either from the field on its selection screen, from `HF_TOKEN`, or from the Hugging Face CLI login. The 9B's context of 65,536 and its 15 s usual start are not measured yet.
- **`animate_image` turns a still into a clip** (#340). It takes one continuous motion plus the camera, 1 to 20 s at 24 fps, 1080p (1920x1088) or 1440p (2560x1408), and saves an MP4 in `<working root>/videos/`. When ffmpeg is on the PATH, three stills of the clip go back to the model. While the clip renders, the language model steps aside: `use_mode` stops sd-server and the engine, starts ComfyUI, and afterwards ends ComfyUI and starts the engine again from the boot's plan. The engine comes back after an error, a stop or the 30-minute timeout as well. #340 Phase 0 measured a 5 s clip at 1080p with a median of 65.6 s, 10 s with 146.2 s, and 20 s with 349 to 361 s. The clip carries LTX-2.5's own sound (AAC, 48 kHz stereo); the motion text describes it in words. A motion text the user wrote goes to the video model verbatim: on 2026-10-03 the 9B's rewrites had dropped a user's sound sentence (the clip came back with loud noise) and named "the human's foot at the bottom left corner" (a giant foot was painted in), while the verbatim text was followed.
- **The clip plays in the window** (#340). A saved clip replaces its progress tile with a player, and the caption shows the size the stream reports. On Windows and on a phone, the clip goes to the page as bytes, the same way pictures do. Phase 0's 5 s clips were 1.6 to 2.6 MB. Before the player gets the file, it must lie in the working area or an approved path and start with MP4 or WebM bytes. The clip comes back after a restart, and **Show in folder** opens the folder with the file selected.
- **CrowSetup unpacks ComfyUI's own release archive** (#340). The archive is a solid LZMA2 + BCJ2 7z, read with sevenz-rust2 on one thread. On `ComfyUI_windows_portable_nvidia.7z` v0.38.0 (1,994,326,521 B, 58,293 files, 4,384,588,275 B) that took 806 MB of RAM and 40.9 s, against 10.2 GB on the default 24 threads. The archive is deleted after unpacking. `ComfyUI/extra_model_paths.yaml` points ComfyUI at the LTX files under the models root.
- **The operating-point window and CrowSetup list the Media Stack** (#340). It shows on Windows only (`platforms` in `manifests/stack.json`); CrowSetup's selection page has the Hugging Face token field, its `--points` takes `media-stack`, and its preflight asks for 64 GB RAM and 100 GB free disk.

### Changed

- **Projectors and tokenizers download from their original repos** (#340). Six files that came from a mirror are fetched from the repos that publish them; their sha256 is unchanged. Only robin's own CNQ quants and their companion files live in his repos.
- **`NOTICE` names sd-server's components, the NVIDIA Linux libraries and the ComfyUI template** (#340). The notices for these parts were missing from the v3.1.0 assets.
- **The 2.1.0, 2.8.4 and 2.8.5 Windows assets no longer carry local logs** (#196, 2026-10-01). Each was replaced on its release by a repack of its own tag with that tag's packer and the rebuilt `bin\` (llama.cpp `1c3c967`, sd.cpp `2f88688`; the published `bin\` of all three was byte-identical to 2.8.5's). The repacks hold exactly the files of the originals minus the 10 `cli/runs/*.log` each: 2.1.0 531,611,346 B (33 files), 2.8.4 643,541,823 B (59), 2.8.5 643,542,202 B (59).

### Known limitations

- **The Media Stack runs on Windows only.** ComfyUI publishes its portable runtime for Windows only; a Linux runtime is not started.
- **Prompt following of LTX-2.5 in Crow is weaker than it should be** (#346). On 2026-10-03 a small brass key turned into two rings while the crow picked it up, and the camera panned although the text said it holds still. Crow sends LTX the raw text where Lightricks' ComfyUI template first enhances it with Gemma 4 e2b, and renders 1920x1088 where the template renders 1280x720. Neither is measured yet.
- **The 1080p video is 1920x1088, not 1920x1080.** It is the size ComfyUI's `ResolutionSelector` picks in the workflow (`comfy_extras/nodes_resolution.py`, v0.38.0).
- **The 9B's context of 65,536, its start, its VRAM beside sd-server and ComfyUI's boot time rest on one run** (2026-10-03): ComfyUI answered 16 s after the card was free, 9B + sd-server peaked at 21,864 of 32,579 MiB. `docs/operating-points.md` keeps them under "Not measured".

## 3.1.0 — 2026-10-02

**Linux gets the one-window installer and the operating points.** `CrowSetup-linux-x64` is attached to this release; it installs Crow's Linux package (with `sd-server` and its CUDA libraries) and the crow-nest v0.9.0 Linux engine, and writes the "Crow Operating Points" launcher. The operating-point window starts 27B and the Image Stack on Linux. Windows assets are unchanged: `CrowSetup.exe` and the Windows package stay on v3.0.0.

### Added

- **`CrowSetup-linux-x64` installs Crow, the crow-nest engine and the chosen operating points on Linux** (#342, 2026-10-02). It is the same installer as `CrowSetup.exe`, built from the same crate: a GTK/WebKitGTK window, the same resumable, verified downloads, `--headless`, `--source` and `--package-source`. The window runs on X11 and Wayland, NVIDIA included (it sets `__NV_DISABLE_EXPLICIT_SYNC=1` unless you set it, as the Crow window does); before that fix it never mapped under Wayland, and on Hyprland + NVIDIA 610.57.04 WebKitGTK died at the first frame ("Missing acquire timeline").
  - **Layout:** the root is `${XDG_DATA_HOME:-~/.local/share}/crow`. `bin/` holds `serve`, `libnvrtc.so`, `libnvrtc-builtins.so.13.3` (crow-nest #133) and `sd-server`, `cuda/lib/` holds cudart, cublas and cublasLt, and Python is a venv from the system `python3` (3.10 or newer). It writes desktop entries "Crow Operating Points" and "Crow" (`$XDG_DATA_HOME/applications`).
  - **Local models:** `--source` hard-links models that are on the same file system, and the disk check counts them as free.
  - **Packages:** `crow-<v>-linux-x64.tar.gz` is packed by `tools/pack-release.sh`, which uses the privacy gate of `pack-release.ps1` plus `/home/<anyone>/`. The archive is read back through the gate member by member. The bare user name passes only in the public-namespace contexts (URLs, repo ids, the repo constant, the README link text, the copyright line); robin confirmed this on 2026-10-02. `installer/build.sh` builds and gates the installer: 4,640,496 B, 0 refused hits.
  - **sd-server for shipping:** `SD_RELEASE=1 tools/build-sd-server.sh` builds it with RPATH `$ORIGIN/../cuda/lib`, `-ffile-prefix-map` and GGML_NATIVE off with AVX2/FMA/F16C (x86-64-v3). The privacy scan finds 0 hits, against 236 for the 2026-09-27 local build.
  - **Measured on the Linux box, 2026-10-02:**
    - Install: a headless install of 27B + Image Stack from local packages and the manifest-layout models took 22 s. 52.9 GB were planned and hard-linked; the disk lost about 1.3 GB (packages and venv).
    - Boot from the installed root: Image Stack "Landed" after 9 s. NVRTC came from `bin/` and cudart/cublasLt from `cuda/lib/`, with no CUDA toolkit on any path.
    - Image: one `generate_image` at 2048×2048 took 161.3 s on the first request. The 2.8.0 reference with the native build is 155 s warm and 175 s cold at 2752×1536.
    - Stop took 0.6 s, and both ports were free afterwards.
- **Operating points start on Linux** (#341, 2026-10-02). `manifests/stack.json` names `bin/serve` and `bin/sd-server` for Linux and a `lib_path` (`<install>/bin`, `<install>/cuda/lib`) that goes in front of `LD_LIBRARY_PATH`. The boot menu and the operating-point window start both servers in the same memory-bounded user scope as the llama.cpp lines. `tools/check_stack.py` checks both platforms. Measured on the Linux box (RTX 5090), from a scratch install root with the crow-nest Linux pack (crow-nest #133) and the models in the manifest layout: the 27B landed in 11 s (`/props` `model_path` ends with the container, vision on), and the Image Stack in 9 s with sd-server ready on :8097. Stop took 0.3 s, and afterwards both ports were free and VRAM was back to 697 MiB.

### Fixed

- **The release gate no longer finds the host name inside binary data** (#345, 2026-10-02). A host-name hit now needs a separator, NUL or line end on both sides; three hits for the four-letter host name inside the v3.0.0 Windows DLLs (compressed CUDA data, a base64 run) had refused the v3.1.0 Windows repack. The public-namespace contexts the Linux packer allows now apply to `repack-release.py` too. Tests red without the fix, green with it.
- **The Linux release packer no longer refuses its own archive** (#342, 2026-10-02). The readback gate scanned the tar as one blob, so the per-file allowlist did not apply and the public namespace was counted 20 times. Each member is now scanned under its own path. Its selftest is red without the fix ("an allowed context reads back clean") and green with it, 25 checks.
- **`tools/check_stack.py` no longer takes the Hugging Face owner for the user name** (#343, 2026-10-02). On a machine whose login equals the repo namespace (robin's Linux box: `nibor1896`), the check failed 17 times on `/files[i]/repo` and `tools/test_check_stack.py` was red twice against an unchanged manifest. The namespace of a bare repo id is now exempt, while the repo name part and every other field are still checked. Result: 7 of 7, and the suite has 53 tests OK under the real login.
- **Stop no longer waits 30 s on Linux for a server it already ended** (#341, 2026-10-02). A killed child that nobody waited for stayed a zombie and still answered signal 0, so Stop timed out with "still there". `process_exists` now treats a zombie as gone.

## 3.0.0 — 2026-10-01

**`CrowSetup.exe` installs Crow, the crow-nest engine and the operating points in one window, and the window is Crow's only client.** The installer is attached to this release; it downloads Crow's package and the crow-nest v0.8.0 engine from their releases, resumes after a stop, and writes the shortcut to the new operating-point window. The terminal client and `crow --serve` are removed: start Crow with `python <install>/cli/crow_gui.py`; installs of 2.8.5 and older update through the usual one-liner. Major version because a command line that used to work no longer exists.

### Added

- **`CrowSetup.exe` installs Crow, the crow-nest engine and the chosen operating points** (#196, 2026-10-01). One Rust exe whose window (WebView2) uses Crow's own look: the crow fills as the progress, "Flying to the nest", "Landed. Crow is ready.".
  - **Selection:** Crow and the engine are required; Flash-Next, 27B and Image Stack are chosen per row; a point the machine cannot run (no RTX 50 card, under 64 GB RAM for Flash-Next, not enough disk) stays visible with its reason.
  - **Downloads resume:** each file goes to `.part` with `setup\state.json` (fsync every 64 MiB), Range + If-Range, unbounded retries with a stall timeout, sha256 before the rename, a fallback to IPv4 after resets. Closing with X and starting again shows "Welcome back" and continues. Measured 2026-10-01: a 927,607,488 B file from Hugging Face killed at 30.4 % resumed from byte 268,447,949 and verified; Pause resumed at the exact byte; a `--source` install killed at 6.0 GB continued from the last checkpoint.
  - **Configuration** comes from `manifests/stack.json` and the boot menu; nothing is written to the user environment. Models always go to `<install>\models`; the shortcut passes `--models`. The Image Stack's `text_encoder_sdcli/` is derived on the machine and the upstream `text_encoder/` deleted.
  - **Python:** a found Python 3.10+ is used, else the bundled embeddable 3.13.16.
  - **Flags:** `--headless`, `--selftest`, `--source <dir>`, `--package-source <dir>`, `--install-root <dir>`, `--shortcut-dir <dir>`, `--no-shortcuts`. `installer/build.ps1` builds it remapped, with a static C runtime, and refuses on the privacy gate (18,488,320 B on 2026-10-01).
- **The operating-point window** (#196, 2026-10-01). `python cli\crow_boot.py --gui`, and the shortcut the installer writes: the three crow-nest points and the optional llama.cpp lines with Start, the crow filling while a point starts, "Landed." with the running point and Stop on top, "One model at a time." when a second start is refused, and "Open Crow window" for the chat. The terminal menu stays (`--terminal` writes its shortcut). Measured 2026-10-01: the 27B landed in 15.3 s through the window; Stop took 4.4 s with every port free afterwards.

- **A boot menu starts an operating point, then Crow** (#196, 2026-10-01). It is started with `python cli\crow_boot.py`, or from a shortcut via `--create-shortcut <folder>`, which uses Windows Terminal when present.
  - **Entries:** Start Crow, the three crow-nest points (Flash-Next, 27B, Image Stack, the baseline), and below them under "Optional (llama.cpp)" Crow's llama.cpp lines, dimmed. Only lines whose files are on disk are shown. The last entries are Stop and Quit.
  - **Starting a point:** an animated "flying to the nest" line replaces the server log. "Landed" shows for 5 s, then the menu comes back.
  - **Context:** the 27B point runs at 128k (`CROW_CONTEXT=131072`), the Image Stack at the dense default 65,536 so Qwen-Image fits beside it. Measured on Windows (RTX 5090, BF16 KV, F16 projector), 2026-10-01: 200,000 is refused at boot, needing 13.03 GiB of states against 12.17 GiB free. At 131,072 the boot took 12 s, `/props` showed `n_ctx` 131072 with vision, and the card had 28,342 of 32,607 MiB in use (1,252 idle). 200k waits for an 8-bit KV cache in crow-nest.
  - **One point at a time, in both directions.** A second start names what runs and how to stop it.
  - **Configuration:** everything comes from `manifests/stack.json`, which now ships in the package. The menu writes `active-point.json` for the window.
  - **Measured on Windows, 2026-10-01**, from a hardlinked install layout and the engine pack of crow-nest #131: the 27B ready in 9-13 s, the Image Stack in 10 s (sd-server started after serve), the 27B GGUF line in 9-12 s. A second start was refused (exit 3). After Stop, every port was free.
  - Stop waits on the process handle: a 13 GB llama-server was gone from the scan after 0.08 s but from `tasklist` only after 1.61 s.
  - Flags `--status`, `--start <point>`, `--stop` and `--start-crow` work without the menu. `docs/user-guide/boot.md` documents it.

- **`manifests/stack.json` describes the three installable operating points** (#196, 2026-10-01). Flash-Next + vision, 27B + vision and 27B + Qwen-Image 2.1. Each point lists every file with repo, pinned revision, bytes and sha256, plus serve's env and argv, ports, the readiness probe and the identity (`/props` `model_path`). Disk per point: 105,644,572,827 B, 18,784,665,622 B and 69,434,804,127 B. The projectors, the tokenizer and the crow0924 hot set are marked `mirror-pending`: they move into our CNQ repos on Hugging Face, upload on robin's word. Qwen-Image stays upstream. `tools/check_stack.py` validates it (5 of 5 offline, 31 of 31 `--online` against HF on 2026-10-01), and a test pins its sd-server line to `crow_core.image_server_command`. This is the data the installer and the boot script will read.
- **`tools/te_rename.py` derives `text_encoder_sdcli/` from upstream Qwen-Image** (#196, 2026-10-01). It rewrites only the tensor names (`model.language_model.*`, `model.visual.*`, `lm_head.*` → `text_encoders.llm.*`). The payload is copied byte for byte, each shard is atomic and the run is resumable. Checked against the four upstream shard headers read by HTTP range: 750 tensors, 0 mismatches, and headers and index byte-identical to the copy the image stack was measured with.

### Changed

- **The window finds crow-nest by itself** (#196, 2026-10-01). Without `--base-url` it now also tries `127.0.0.1:8099` (`/health` = ok) after any llama-server. Crow sees `serve.exe` and `sd-server.exe` as servers. Starting a second operating point is refused, naming the running serve. `tools/start-server.py` lists a running serve as `crow-nest <point> on port 8099`.
- **The image server starts only on the Image Stack** (#196, 2026-10-01). `%LOCALAPPDATA%\Crow\active-point.json` (written by the coming boot script) names the running point. On `flash-next` or `27b` the window no longer warms sd-server, and the image tools say that image generation needs the Image Stack. Beside Flash-Next, serve leaves 73-185 MiB of VRAM, so a warm-up there would not fit; that it fails is not measured. Without the file, or when its serve pid is dead, nothing changes.
- **No owner name and no machine paths in what ships** (#196, 2026-10-01). Model prompts and texts say "the user". `operating-point.json` no longer carries a models root or a lab binary path. Models come from `$CROW_MODELS`, else `<install>/models`, and a line's own build from `CROW_LLAMA_SERVER_<KEY>`, else `<install>/bin`. A test fails on any owner name or profile path in the shipped files: 389 hits before, 0 after.

### Fixed

- **Release packages no longer carry local logs or builder paths** (#196, 2026-10-01). `crow-2.8.5-win-x64.zip` (643,483,909 B) shipped 10 `cli/runs/llama-server-808x*.log` files with local model paths; 2.8.4 and 2.1.0 have the same, per the audit. Both packers now ship only a declared set and exclude `runs/`, `*.log`, `.env*`, `secrets.json` and session files. Before writing anything they scan every packed file (UTF-8 and UTF-16LE) for the builder's profile path, user name and host name, and refuse on any hit, with no override. On the 2.8.5 tree the scan catches the logs and 10 binaries (`ggml-cuda.dll`, `llama.dll`, `sd-server.exe` and others) that embed build paths. `pack-release.ps1` has no personal `-BuildDir` default any more (`$env:CROW_BUILD_DIR`). Selftests: `pack-release.ps1` 52 OK, `test_repack_release` 18 OK.

### Known limitations

- **The published 2.1.0 and 2.8.4 Windows assets still contain the local logs.** The 2.8.5 asset was replaced on 2026-10-01 by a repack of the `v2.8.5` tag with its own packer and the rebuilt `bin\` (643,542,202 B, 59 files, no `runs/` logs).
  - The gate refuses the binaries those packages were built from.
  - `bin\` was rebuilt on 2026-10-01 from a path without a user name, at the same commits and CMake options: llama.cpp `1c3c967` with its working-tree diff, sd.cpp `2f88688`. Builder paths went from up to 258 per file to 0, sizes changed by less than 0.03 %.
  - The gate passes that rebuild. It allows only three upstream word sites, each by file, exact context and measured maximum: "round-robin" twice in `llama-server-impl.dll`, and 29 tokenizer-vocabulary entries ("Robin", "Robinson") in each of `sd-cli.exe` and `sd-server.exe`. Paths are never allowed.

### Removed

- **The terminal client and `crow --serve` are gone** (#187, 2026-10-01). `cli/crow.py` and its suite `cli/test_crow.py` are deleted; the window is the only client: `python <install>/cli/crow_gui.py`, against crow-nest with `--base-url http://127.0.0.1:8099/v1`. `--serve <model>` has no replacement: the window boots a llama.cpp operating point from its model menu, and crow-nest's `serve` starts from the crow-nest repository. The version literal now lives in `cli/crow_core.py`; the installers read it there and fall back to `cli/crow.py` only for installs older than this change, so those still update. `tools/run_server_block.py` (E14 block), which drove the terminal client, moved to `tools/archive/2026-10/`. The suites are now `test_crow_core`, `test_crow_gui` and `test_crow_remote`; dropping `test_crow` is a deliberate coverage reduction: 3,143 tests before, 2,945 after (Windows, 2026-10-01, same 7 known Windows-only failures both times); 332 of the 480 `test_crow` tests that guarded `crow_core` functions were moved into `test_crow_core`, and the tests of code that lost its last caller went with that code.

## 2.8.5 — 2026-09-30

**The phone remote answers a refused request instead of resetting the connection.** A test of it went red on
CI windows-latest for the v2.8.4 tag; the cause was the server, not the test, and it is fixed here.

### Fixed

- **The phone remote answers a refused request instead of resetting the connection** (#334, 2026-09-30). A refusal (400, 401, 403, 415, 421, 501) closed the socket while the request body was still unread; when the body arrived after the close, TCP sent a reset that also swallowed the answer (CI windows-latest on the v2.8.4 tag: WinError 10053). The server now reads an unread body of up to 1 MiB (2 s limit) before it answers. Reproduced with the body sent 0.1 s after the headers: 20 of 20 resets before, clean 400/401/421 after.

## 2.8.4 — 2026-09-30

**Crow keeps working when its thinking is cut after a tool result.** When the 1024 reasoning cap ended a
think block, the sentence Crow injected told the model to write the final answer, so a working agent could
announce its next step and stop. After a tool result the sentence now tells it to act; after your own message
it still tells it to answer. Both halves were measured on the 27B under Windows on 2026-09-30; the switch
between them waits for robin's next long run.

### Fixed

- **Crow no longer announces the next step and stops when its thinking is cut after a tool result** (#245, 2026-09-30). When the 1024 reasoning cap closes the think block, Crow injects a sentence; after a tool result it is now "…I will now act on it." instead of "…I will now write the final answer for the user.", which the model took literally ("Ich starte das jetzt." and no call). Measured on the 27B under Windows, same seeds and cut points: 4 of 49 cut rounds without a call before, 0 of 49 after. After your own message the old sentence stays: the new one turned 12 of 31 cut text requests into a tool call (mostly `write_file`), the old one 2. The switch on the last message is read from those two measurements, not measured on its own; watch for it in the next long run. `docs/reference/reasoning-levels.md` has the table.

### Changed

- **The 27B's 1024 reasoning cap is measured now, and it stays** (#245, 2026-09-30). `qwen38-27b-cnq` carries `_reasoning_budget_status`: 1024 against 2048 on crow-nest's `serve.exe` under Windows (RTX 5090), replaying robin's Windows session of 2026-09-15 at the two turns where 1024 closed the think block in a screening pass (K=10, 19,172 prompt tokens; K=45, 41,254), 8 seeds + greedy per arm and point, criteria fixed first (crow-nest `decode_out/meas-245/PREREG.md`). 1024: 1 of 18 rounds without a tool call, 0 corrupt, median 20.9 s per round; 2048: 0 of 18, 0 corrupt, 36.35 s. 2048 fails the pre-set wall-clock limit (1.74x against 1.5x), so nothing on the wire changes. Not decided by it: Flash-Next's 1024.

### Known limitations

- **The sentence switch is not measured on its own** (#245). It is read from two measurements that each held one sentence fixed: on tool turns (4 of 49 cut rounds without a call with the answer sentence, 0 of 49 with the act sentence) and on turns that need no tool (12 of 31 cut text requests became tool calls with the act sentence, 2 with the answer sentence). robin's next long goal run is the live check.
- **Flash-Next's 1024 cap is still unmeasured against another value** (#245); both measurements above ran on the 27B only.

## 2.8.3 — 2026-09-30

**Windows closes cleanly and the browser panel behaves.** Closing the window can no longer leave an empty
`session.json`, and Crow ends after the X even when the browser panel was used. On Windows the panel keeps
logins across a restart, stays above Crow only, follows the page in its tab and address, and a panel restored
open starts with a tab. The image server runs in its own empty folder, so a window started from the home
folder makes pictures again. Every fix was checked live by robin on Windows on 2026-09-30.

### Added

- **Windows: the browser panel leaves a trace in `crow.log`** (#327, 2026-09-30): `[pane] browser pane:` lines for created, go, show, hide and loaded, and a malformed WebView2 message becomes one `malformed web message from <origin>` line instead of a traceback on the terminal. The trace showed that the panel loaded its page on every restart; the blank was the missing tab (above). The traceback came from Sony's sign-in page posting to `window.chrome.webview`.

### Changed

- **Docs carry the Windows image timing** (#320, `6677383`): the README image and `docs/reference/tools.md` state the Windows measurement (218-235 s beside the 27B serve, 2026-09-28). No code change.

### Fixed

- **The image server runs in its own empty folder, and a refusing server says so** (#324, 2026-09-28). A window started from the home folder on Windows never posted an image job: sd-server walks its working directory on every `GET /sdcpp/v1/capabilities` (`--lora-model-dir` defaults to `.`), the walk threw on Docker's socket file, the probe got HTTP 500, and the card showed "loading" until stop (238 s).
  - sd-server now starts in `<state>/image-server`, a folder Crow creates and keeps empty. Same machine, started from an empty folder: capabilities 200 in 29 ms. The argv is unchanged on both systems.
  - A 5xx on capabilities ends the start at once with `the image server answered HTTP 500 on /sdcpp/v1/capabilities` and the server's exception text, instead of waiting 180 s.
  - A relative `CROW_IMAGE_MODEL_DIR` is resolved against the folder Crow was started in.
  - robin's live check (2026-09-30, Windows, window started from `C:\Users\robin`, beside the 27B serve): the tile read `sampling 1/40` after 21 s, the picture came in 314.7 s (2752×1536). n = 1.
- **Closing the window can no longer empty the saved chat** (#325, 2026-09-30). On Windows the exit watchdog ended Crow while the close was still writing `session.json`, and the file was left at 0 bytes (2026-09-28 16:22); the next start opened an empty chat and said nothing.
  - `session.json` is written to `session.json.tmp` and then moved over the old file, so an end at any moment (watchdog, Ctrl+C) leaves the previous file whole. The same for the rewrite that withdraws the KV half on load.
  - The exit watchdog waits while any session save is running, up to 30 s, and logs `exit: waited N s for the session save`.
  - The window says `saving the chat and the cache...` from the X until it is gone.
  - An empty or unreadable `session.json` is moved aside to `session.json.unreadable` and the start says so once, instead of an empty chat without a word.
  - robin's live check (2026-09-30, Windows): closing works and the note showed; after both closes with the panel used the process ended without Ctrl+C, `session.json` was valid (`kv: true`) and the chat came back. A close cut mid-write was not exercised live (unit test).
- **Crow ends after the X on Windows when the browser panel was used** (#328, 2026-09-30). The panel's second window outlived the main one, pywebview only ends its loop when the last window is gone, and the exit watchdog is armed after that loop: the process stayed until Ctrl+C (3 of 3 closes after using the panel, > 60 s). `close()` now destroys the panel window before the main one and arms the watchdog itself after the save. robin's live check (2026-09-30): 2 of 2 closes after using the panel ended without Ctrl+C.
- **Windows: the browser panel keeps logins across a restart** (#326, 2026-09-30). pywebview starts in private mode by default, for every window; Crow now starts it with `private_mode=False` and its own storage in `%LOCALAPPDATA%\Crow\webview`. Crow's page keeps its one `localStorage` key (`crow.theme`). robin's live check (2026-09-30): logged in, restarted, still logged in.
- **Windows: the browser panel stays above Crow only** (#329, 2026-09-30). It was created `on_top`, which is TopMost over every application (seen over Discord with Crow behind it); it is now owned by Crow's window instead, so it goes behind other apps with Crow and minimises with it. robin's live check (2026-09-30): another app brought to the front covers the panel.
- **Windows: the panel's tab and address follow the page** (#330, 2026-09-30). A link or redirect inside the page left the tab and the address on the first URL; each load now reports its URL the way Linux does. robin's live check (2026-09-30): the tab names the new site. `pushState` and `#hash` changes fire no load on Windows and are still not followed.
- **A browser panel restored open has a tab** (#327, 2026-09-30). The panel came back open after a restart with no tab ("no tab open -- press + for one"), and Enter in its address bar did nothing until `+` was pressed. The start now gives an open, empty panel its first tab, as unfolding it always did, and Enter without a tab opens one with that address. robin's live check (2026-09-30): a tab at once after the restart, an address loads without `+`.

## 2.8.2 — 2026-09-28

**Pictures on Windows beside the 27B.** `generate_image` failed on every call on Windows while crow-nest's 27B served; sd-server now maps its weights there, and a failed image names its out-of-memory line. The Windows package is attached to the release again, so the Windows one-line installer finds it. Linux behaviour is unchanged.

### Fixed

- **The Windows package is on the release again** (2026-09-28). `install.ps1` downloads `crow-<version>-win-x64.zip` from the release of the newest tag; v2.8.0 and v2.8.1 carried no asset, so the Windows one-liner had nothing to fetch. 2.8.2 ships `crow-2.8.2-win-x64.zip` with `sd-server.exe` and `sd-cli.exe` (pin `2f88688`, built with the Ninja recipe of #318).
- **Windows: the image server starts with `--mmap`, and an out-of-memory end is named** (#320, 2026-09-28). On Windows every `generate_image` beside crow-nest's 27B serve died in `cudaMalloc failed: out of memory` with VRAM free, and the tool answered only `generate_image returned no results`.
  - Cause, measured on robin's machine: the Windows commit limit, not the card. Under WDDM every CUDA allocation also counts against commit (no pagefile, limit 64,901 MB); serve holds 26.7 GB, sd-server without `--mmap` needs ~37 GB (CPU text encoder copy 14.4 GB + pinned DiT staging 14 GB). A VRAM loan from serve did not help (10 GB VRAM free, same failure).
  - Windows: `image_server_command` appends `--mmap` from `crow_platform.image_server_platform_args()`. Measured beside the default 27B serve: the image completed in 237.7 s, commit 51,149 of 64,901 MB. The Linux argv is unchanged.
  - Both systems: a failed job whose log since its start holds `cudaMalloc failed: out of memory`, an ERROR `failed to allocate` line or a pinned-memory refusal answers with that log line (`the image server ran out of GPU memory: <line>`); on Windows it adds that the commit limit may be the cause.
  - Acceptance, same machine, 2026-09-28: 3 of 3 images beside the running 27B serve (235.1 s, 218.1 s, 218.5 s), 0 out-of-memory lines, card peak 31,861 of 32,607 MiB. The GUI path on Windows is robin's live check.

### Changed

- **Windows image-server recipe builds with Ninja** (#318, 2026-09-28). `docs/user-guide/install.md`: `cmake -G "Ninja Multi-Config"` in a `vcvars64` shell; the Visual Studio generator stopped at `No CUDA toolset found` (VS 18, CUDA 13.3). Measured: 398 of 398 build steps, `sd-cli.exe --version` reads `master-920-2f88688, commit 2f88688`.
- **The node parse tests no longer depend on the runner's first node start** (#319, 2026-09-28). The tests that assert `node --check`'s verdict run with a 60 s clock; the product keeps 5 s. Before: 7 red CI jobs in 55 runs (2026-09-20 to 09-27). Tests only.
- **Docs name the image model's licence** (2026-09-27). README, `docs/user-guide/linux.md` and `docs/reference/tools.md` link [`Qwen/Qwen-Image-2.1`](https://huggingface.co/Qwen/Qwen-Image-2.1) and say that it is under the Qwen Research License: research and evaluation only, commercial use needs a licence from Qwen. No code change.

## 2.8.1 — 2026-09-27

**A calmer chat box.** The window's composer no longer wears the banner blue while nobody types in it;
only the focused box glows. A one-change patch on top of 2.8.0.

### Changed

- **The idle chat box has no coloured frame** (`9de5f41`, robin, 2026-09-27). At rest the composer's frame was the banner blue with a faint blue ring, so a box nobody was typing in looked selected. It is now the neutral line colour of the other frames, without a ring; the focused box keeps its accent border and glow unchanged. Desktop window only; the phone mirror already drew no ring.

## 2.8.0 — 2026-09-27

**Crow makes and edits images, and the 27B on crow-nest sees them.** `generate_image` and `edit_image` run
Qwen-Image 2.1 on a resident sd-server beside crow-nest's dense 27B on one 32 GB card: 2752×1536 in about
2.6 min, an edit in two stages (1 MP edit, full-size redraw) because a 4 MP edit comes out grainy (#300, #308).
In the chat an animated square in the theme's colours becomes the picture; a lightbox opens it with folder,
download and info (#311), on the phone mirror too. `install.sh --build-image-server` builds sd-server (#314).
Images dropped from the file manager reach the model on Linux (#312), the window's X ends the process (#313),
Stop interrupts a running command (#310), and a command over its memory ceiling dies instead of crawling (#309).
20 commits since v2.7.0.

### Added

- **Crow makes and edits images** (#300 phase 3, #308, #311, 2026-09-27). Two tools on a resident `sd-server` (stable-diffusion.cpp 2f88688, Qwen-Image 2.1, BF16 DiT streamed, `--max-vram 7`, text encoder on the CPU), started on first use or warmed at window start, stopped with Crow:
  - `generate_image(prompt, aspect_ratio)`: the model card's sizes (16:9 = 2752×1536). Measured beside crow-nest's 27B (8.15 GiB free): 155 s warm, 175 s cold, card peak 31,338 MiB, the 27B's output unchanged.
  - `edit_image(images, instruction, description)`: two stages in one call, because a 4 MP edit comes out grainy (measured E1/E2). Stage 1 edits at ~1 MP, the reference pipeline's size; stage 2 redraws the result at full size (img2img without references, strength 0.25). Measured 105.7 s + 55.3 s for 2752×1536, clean; chosen by robin from a side-by-side (`crow-nest/decode_out/p3-img/compare-img2img.png`).
  - Images land in `<working root>/images/`; the model sees its own result (vision).
  - **In the chat:** a square in the image's aspect ratio with a flow animation in the active theme's colours (static under reduced motion) and the phase line (loading, encoding, sampling i/40 · ETA, decoding, stage 1/2 · 2/2) stands where the image will be; the finished picture replaces it in place. Error: a red tile with the reason. After a restart an unfinished job shows "interrupted".
  - **Lightbox:** a click on the picture opens it large; top right: Show in folder, Download (Save as…; on the phone a real download), Copy image, Copy path, Open in viewer, Move to trash (two clicks, never a plain delete), "i" with name, W×H, size in MB and bytes, format, created, path, tool, seed; Esc closes. The phone mirror shows previews, the lightbox and the info.
  - robin's live check (2026-09-27): generate 162.2 s / 163.6 s, a two-stage edit 109.4 s + 60.3 s, the tile, the swap, the lightbox and the phone as described. Not measured: Windows.
- **`install.sh --build-image-server`** (#314, 2026-09-27): builds `sd-server` and `sd-cli` (stable-diffusion.cpp 2f88688 with its four submodule pins, CUDA, sm_120) into `bin/` with `tools/build-sd-server.sh`, reusing the llama-server builder's CUDA toolkit; no web UI. Measured on the RTX 5090 box: 3 min 10 s (8 jobs), a rerun 1.4 s with nothing to do, `ldd` resolving CUDA from `<install>/cuda/lib`. An older `sd-cli` is kept as `sd-cli-<commit>`. Windows: `tools/pack-release.ps1 -SdBuildDir` puts `sd-server.exe` and its DLLs into the release zip, recipe in `docs/user-guide/install.md`; not run yet (needs Windows).

- **Crow knows crow-nest's dense Qwen3.8-27B container** (#300, 2026-09-27). New `models.entries.qwen38-27b-cnq` for `Qwen3.8-27B-CNQ4.5.cnq`, the container crow-nest's `serve` opens on port 8099 (not booted from Crow, like `flash-next-cnq45-m`). `model_key_for` pairs it with what the running serve reports (checked live: key `qwen38-27b-cnq`), so a request to it carries the 27B card's rows (thinking 1.0 / 0.95 / 20 / 0.0 / 0.0, non-thinking 0.7 / 0.80 / 20 / 0.0 / 1.5), thinking fixed at `high` (= the template's xhigh) and the 1024 reasoning cap, the same policy as the crow-nest Flash-Next point. Reasoning levels measured on the running 27B serve (#74 method): none / low / medium / high accepted, max / minimal / off / High / empty refused with 400; identical to Flash-Next's, since the 27B's chat template and tokenizer files are byte-identical to Flash-Next's. `docs/operating-points.md` has its row. Not measured: answer quality in Crow on this point.

### Changed

- **The README is a generated image** (#307, 2026-09-25; `4664c3a`, `f1c941d`): one picture per GitHub theme and a one-column variant for phones (`docs/images/readme/`, drawn by `tools/readme_image.py`), then the install lines, the docs links, the licence and Ko-fi; the old text front page lives in `docs/archive/README-v2.7.0.md`. For 2.8.0 the picture shows the image tools and takes the tool count from `crow_core.BUILTIN_TOOLS` (30, was drawn as 28) (`0c08fb1`).
- **`install.ps1` sees a running `sd-server.exe`** holding `bin\` during an update, as it did llama-server (#314). Not run: no PowerShell on the Linux release machine.

### Fixed

- **An image dropped into the window on Linux is lost** (#312, 2026-09-27). The drop took the file's path from pywebview's GTK drag handler; robin's drops from the file manager reached no chip and no request. Measured on the retest (`crow.log` 09:38:03, 09:38:47): WebKitGTK handed the page the drop with **zero** File objects, so neither the path nor the bytes existed. The page now takes a picture's bytes when the drop carries files (`FileReader` → `stage_image_data` → written like a paste → staged under its own name, also on the phone mirror), and otherwise reads the file manager's URIs where GTK has them: the second retest (`crow.log` 10:00:46) showed the page types `text/uri-list` and `text/html` with zero files and an EMPTY uri text, and pywebview reads the GTK drag data with `get_text()` (None for a uri-list), so Crow connects the WebKit widget's `drag-data-received` itself, keeps `Gtk.SelectionData.get_uris()`, and `on_drop` turns them into paths for the normal drop route (`drag_uri_path`; the page-side `dropUriPaths` stays for backends that expose the text). Every drop leaves `[drop]` lines in `crow.log` (types, file count, uri length). Harness: an 11,528,977-byte PNG dropped synthetically into WebKitGTK arrives byte-identical. Tests red without the fix; a real file-manager drop is robin's live check.
- **The process stays alive after the window's X** (#313, 2026-09-27). robin's closed window left the process running (pid 34193, SIGINT ignored), and from a terminal Ctrl+C was always needed. Cause, measured with the new exit watchdog's stacks on robin's next close (`crow.log` 09:39:45): the main thread in `threading._shutdown`, joining pywebview's JS-bridge thread `Thread-14 (_call)`, which waited in `evaluate_js` for WebKit's reply to an answer still in flight when the window went. pywebview runs bridge calls in non-daemon threads and waits on GTK with no timeout (`webview/util.py:335`, `platforms/gtk.py:693-695`). Crow now makes those threads daemon threads (`daemon_bridge_threads`) before the window opens. A harness with one answer in flight at the close hung 2 of 2 without it (killed after 15 s) and ended 2 of 2 in 1-2 s with it. The exit watchdog stays as the backstop: 5 s after the window loop returns, a process still alive logs its threads and stacks, stops the MCP servers and exits.

- **Stop interrupts a running `run_command`** (#310, 2026-09-27). Before, Stop set a flag that nothing read while a tool ran: a `sleep 110` poll ran to its end, every remaining call of the round still ran, and one more chat request went to serve before it was dropped (engine.log 2026-09-27 00:27:39, 535 tokens prefilled for nothing). Now Stop ends the running command within ~2 s: SIGTERM to its process group and its scope, up to 2 s for a cleanup, then the existing SIGKILL sweep; on Windows `taskkill /T /F` on the tree, for the clock and the cap too. The model reads `error: stopped by the user after <N>s -- the command and everything it started in this call were ended: <command>` plus the output so far, booked like a declined call, not a failure. The round's later calls do not run (`error: stopped by the user -- not run`), and no further request goes to the server. Jobs an earlier call put in the background (`nohup … &`) survive, as documented. `build_bundle` and the syntax check stop the same way. Not verified: the GUI click end to end and Windows.
- **A command over its memory ceiling dies at the ceiling instead of crawling, and a background job's kill or thrash is said** (#309, 2026-09-27).
  - `run_command`'s scope drops `MemoryHigh=7G`: the default is `MemoryMax=8G`, `MemorySwapMax=0`, `OOMPolicy=kill`, the shape `CROW_COMMAND_MEMORY_MAX` already had. memory.high throttles and never kills, and with no swap the anonymous part cannot be reclaimed.
  - Before, measured 2026-09-27 on aios (62 GiB, crow-nest serve holding the 27B): a Qwen-Image 2.1 load started with `nohup sd-cli … &` sat at 7.40 GiB of the 7G throttle for 10 min 47 s, in D state, `memory.pressure` full avg60 = 88.13, loading at ~11–22 MB/s instead of ~5 GB/s, and never reached the 8G kill. The same argv under a 40G ceiling loaded all 397 tensors in 2.58 s.
  - Same mechanism at 1/40 scale (2026-09-27, systemd 261, 300 MB anonymous hog, no swap): `MemoryHigh=150M` + `MemoryMax=200M` was still throttled when `timeout 20` ended it (21.8 s); `MemoryMax=200M` alone killed it in 42 ms.
  - A job a command leaves in the background is recorded while its scope still holds a process. Every later tool result starts with a `note:` (after the first line of an `error:` result) when that job was killed at its ceiling (the kernel's `oom_kill` count for `session.slice` rose while its scope vanished) or when its scope's `memory.pressure` reads `full avg60` ≥ 50 %. Before, the model polled the starving job 7 times and read "RUNNING".
  - #218's protection stays: 8G still stops the 54 GiB software-WebGL runaway a seventh of the way, with no swap. Windows is unchanged (no command scope there).
  - Not measured: the 8G ceiling kill of a 12 GiB foreground hog through `run_command` (the ≤ 15 s threshold), and the live sd-cli case with the note (needs the GPU and serve's slot). A job that really needs more than 8G still needs `CROW_COMMAND_MEMORY_MAX` at GUI launch.

## 2.7.0 — 2026-09-25

**Goal runs stop skipping silently, render_page renders on the GPU only, and voxel dioramas get a path-tracing
kit.** A failed goal step climbs a classified ladder and then pauses and asks robin; the judge answers a frozen
yes/no/unknown checklist on clock-stepped frames; a skip is never stored as done (#294–#296). render_page drops the
SwiftShader fallback, captures up to 4 frames at controlled page time with pixel prechecks, borrows VRAM from an
idle crow-nest serve around the capture, and lets path-traced kit pages converge for up to 120 s (#293, #297,
#302). The voxel kit vendors three-gpu-pathtracer with a skill, a scaffold, animation, a photo mode, a props
registry and a diorama checker, opt-in with `install.sh --pathtracer` / `install.ps1 -PathTracer` (#298, #299,
#304). Also: `read_file` refuses binary files and names `read_image` (#301), `--root` survives the restored chat
(#303), and scrollbars show only while used (#305).

Everything on local `main` since 2.6.0 (21d7505): 24 commits, 12 tickets (#293–#299, #301–#305), 2026-09-25.
Most numbers come from the 2026-09-24/25 diorama and lighthouse goal runs. #300 (image generation beside a live
session) is not in this release. Tickets are released pending robin's live check.

### Added

- **Voxel kit: path-traced voxel dioramas as one offline page** (#298, 2026-09-25).
  - `kits/pathtracer/` ships in every install. It holds three 0.186.1 + three-mesh-bvh 0.9.15 + three-gpu-pathtracer 0.0.24 as one esbuild-minified ES module (958,266 bytes; sha256, npm integrity and licence hashes in `kit.json`; the MIT texts beside it; a NOTICE entry). Next to it: `voxel-kit.js`, a scaffold, and the skill `voxel-diorama`.
  - The kit provides a voxel grid; culled-face meshing with one `MeshStandardMaterial` per palette colour; a telephoto near-isometric camera with slight depth of field; a dome, a ground plane and a soft key light; lamps with the spot light below a solid shade; emission capped at 1; a despeckle pass; context-loss recovery; and `window.__SCENE__` / `__PT__` probes.
  - `build_bundle` resolves `crow-voxel-kit` and `crow-pathtracer` to the installed kit, so the library never passes through the model.
  - `install.sh --pathtracer` / `install.ps1 -PathTracer` verify the bundle, switch the skill on and name the esbuild. A kit skill is seeded once, switched off, through a `skills/.seeded` ledger: 0 prompt tokens until someone switches it on.
  - Measured on 2026-09-25, headless Chromium 152, ANGLE/Vulkan, RTX 5090, 1024×1024: the scaffold room (26,627 voxels, 46,168 triangles) ran at 13.0 samples/s at 10 s and 14.3 at 40 s, and lost and restored the context once. The rules come from the pt-proof runs: vertex colours rendered black in 1 of 3 starts, and a spot inside a hollow shade gave 30.6 dB where one below a solid shade gave 38.6 dB (PSNR 60 s vs 180 s).
  - Before: the 2026-09-24/25 goal run hand-wrote a WebGL2 ray tracer for ~16 h (#293–#295).
  - The model's use of the kit in a live goal run is not measured.

- **Voxel kit v2: animated live preview, photo mode, orbit, props registry, diorama checker** (#299, 2026-09-25).
  - The page opens in LIVE mode (since 9e4daa4 this flat preview is `?mode=raster`; see Changed): a rasterised three.js preview of the same scene and materials, with real lights, soft shadow maps (`PCFShadowMap` + `shadow.radius`; `PCFSoftShadowMap` is gone in three r182+) and the scene's `d.animate((t, dt, scene) => …)` every frame. PHOTO mode pauses at t and path-traces as before (despeckle, context-loss restore). Switch with key P or a small Foto/Live button that shows only under the pointer. `?mode=photo&t=<s>` opens the photo directly, `?mode=live` the preview, `&ui=0` hides the button. Drag orbits, wheel or pinch zooms; in photo mode a camera change restarts the accumulation.
  - New API: `d.part(name, grid, {pivot})` returns a movable `THREE.Group` built from its own grid; `d.addSpot({...})`; `addLamp` / `addAreaLight` / `addSpot` return a light rig the callback can rotate (a lighthouse beam). Time comes only from the page clock, so render_page's 4 frames (#293) differ and repeat byte-identically.
  - Against empty scenes: `g.prop(name, build)` records the name, voxels and bbox of each prop. `window.__SCENE__` and the console line `[crow-scene] {json}` report `props`, `propKinds`, `coverage` (terrain columns with a prop above their top cell, divided by all terrain columns), `parts`, `animated`, `mode` and `errors`. The skill sets the targets: ≥ 40 props of ≥ 12 kinds, ≥ 60,000 voxels, coverage ≥ 0.5.
  - `kits/pathtracer/check_diorama.py <index.html>` is a goal `check:` command. It renders through Crow's own `render_page` and prints PASS/FAIL for gpu, probe, samples, props, kinds, voxels, coverage, motion (all 6 frame pairs > 0.5 % changed), repeat, photo precheck and errors; it exits 0 only when all pass.
  - Measured on 2026-09-25, scaffold with its pinwheel part, headless Chromium, ANGLE/Vulkan, RTX 5090, 1024×1024: live 60 fps; photo 289 samples at 20 s (14.5 samples/s); live frame pairs changed 0.69–1.26 %; a second capture was byte-identical; 0 page errors. The scaffold fails the density targets by design (6 props, 26,751 voxels, coverage 0.118). A model-built dense scene is not measured yet.
- **render_page captures frames at controlled page time** (#293, 2026-09-25). `frames` (1–4) and `frame_ms`
  (16–5000, default 500): with more than one frame the page's clock is frozen from its first script
  (`Date`, `performance.now`, timers, `requestAnimationFrame`, a seeded `Math.random`), and each capture follows
  exactly `frame_ms` of page time. Also written: a 2×2 contact sheet at half size, `render-<stamp>-sheet.png`.
  No-GPU smoke on Chromium 152 (canvas 2D, `--disable-gpu`, 640×400, 4 frames × 250 ms): 1.6 s per call, 4
  pairwise different frames, a second call byte-identical (sha256). Not measured on the GPU; that is robin's live
  check.
- **A structured render record** (#293). Every capture and every ENVIRONMENT error carries one line,
  `render: {render_mode, renderer, frames, contact_sheet, precheck}`, and `crow_core.last_render()` returns the
  same dict. `precheck` holds `uniform`, `distinct_colours`, `one_colour_pct`, `dark_pct` and `clipped_pct` (last
  frame), plus `max_frame_diff` and `identical_frames` (all frame pairs; a pixel counts as changed when a channel
  moves by more than 25, and the frames count as moving from 0.5 % changed).
- **render_page borrows VRAM from an idle crow-nest serve** (#297, crow-nest#117, 2026-09-25). Below the VRAM bound,
  when this turn's endpoint is local (loopback), render_page asks serve for the shortfall + 256 MiB
  (`POST /v1/crow/vram/lend`, TTL = the render's own ceiling + 30 s, at most 600 s), reads the free VRAM again, and
  renders on the GPU if it now clears the bound. The loan goes back (`POST /v1/crow/vram/return`, a 503 retried 3×)
  in a `finally` after the browser is closed or killed, on a capture, an error, a timeout or an exception, and before
  the result reaches the model, so `judge` only ever asks after the return. Still short after the loan: the
  ENVIRONMENT error says lending was tried and how much was lent. llama.cpp or an older serve (404), lending off
  (501), a loan already out (409), no answer (then the idempotent return is sent anyway), or a remote endpoint: the
  ENVIRONMENT error as before. Each loan and return is a `render:` line in `crow.log` with MiB and milliseconds.
  Before: under serve, 0.07–0.5 GiB free (#271, #293, crow-nest#117) and every capture refused. Tested against a
  fake serve only; not measured live.

- **Frozen per-step checklist for the judge, with yes/no/unknown, frames, a precheck and reference images**
  (#295, 2026-09-25). Each visual step gets a checklist when it starts. It comes from `accept:` lines
  (`accept: 5: <item>` binds to step 5), or the model writes it once with `goal_step(n, "running", checklist=[…])`,
  or the first `judge` call writes it. A second write is refused, and a replan keeps it. The judge answers each item
  yes/no/unknown with one line of evidence. `done` needs every must-item "yes" (`optional:` items do not gate).
  "unknown" twice on one step pauses the goal. When the render recorded clock-stepped `frames` or a
  `contact_sheet`, the judge sees them. A capture that is software-rendered on a GPU step, uniform, black, under 16
  colours, or frozen on a step that needs motion never reaches the judge model: it is an environment failure.
  `reference: <image> -- <criterion>` in `/goal` sends robin's reference image for a pairwise item. These items are
  advisory until calibrated. Before, on 2026-09-25, 8 judge calls on steps 5–8 used criteria the model wrote at
  judge time, each scored 1–10 on one software frame. Not measured live.
- **Step budget and no-progress timer** (#294). A goal step gets 60 min of active wall clock (`goal_step_minutes`,
  `CROW_GOAL_STEP_MINUTES`). A step with a checklist pauses after 10 nudges with no item newly passed
  (`goal_no_progress_turns`, `CROW_GOAL_NO_PROGRESS_TURNS`). The clock stops while the goal is paused. On
  2026-09-24/25 step 5 carried 8 idle night hours (43,130 s). Not measured live.

### Changed

- **Voxel kit: live mode path-traces the island; a person's page fills the window** (#299 follow-up, 9e4daa4,
  2026-09-25). LIVE (the default) now path-traces the static island, which keeps converging while the camera rests,
  and rasterises only the animated parts (`d.part`) on top, depth-tested against the island. `?mode=raster` (alias
  `preview`) keeps #299's flat raster preview, and `check_diorama.py` takes its motion and repeat captures there,
  because the accumulating path tracer would make a still scene "move". A page opened by a person (`ui` not 0)
  fills the window at `devicePixelRatio` (cap 2) and follows resizes; `ui=0` (Crow's captures, the checker) keeps
  the fixed `width` × `height` at pixel ratio 1. Before: robin opened the flat raster preview after a 6/6 run and it
  looked nothing like the photos, and the fixed 1024×1024 canvas at pixel ratio 1 looked pixelated on his scaled
  1440p screen. Node tests for the mode parser and the checker only; the live mode is not measured on the GPU.
- **Scrollbars show only while their strip is scrolled or pointed at** (#305, 2026-09-25). Every scroll container in
  the window and the phone mirror — the chat, the per-turn stats line (`[24 rounds | … tok/s | prefill …]`), code
  blocks, tables, the Code/Tool-Calls, git, goal and Subtasks panels, the rail, settings, menus — now draws a
  transparent thumb at rest. It appears on any scroll (wheel, keyboard, touch, drag) and goes 0.8 s after the last
  scroll event; a held pointer keeps it; a mouse pointer over the strip shows it (`@media (hover:hover)`, so not on
  a phone). Only the colour changes: bar widths, the 10 px chat gutter and the column do not move. Before: the thumb
  was drawn permanently on every strip. Source and node-run tests only; not yet seen in WebKitGTK, WebView2 or on
  iOS (robin's live check).
- **render_page renders on the GPU only** (#293, 2026-09-25). The SwiftShader fallback is gone. Below the VRAM
  bound (512 MiB, or 1,536 MiB with the panel open), or when the browser's own `UNMASKED_RENDERER_WEBGL` is
  software (SwiftShader, llvmpipe, lavapipe) or not the NVIDIA card, the result is `error: ENVIRONMENT -- ...`
  naming the free VRAM or the renderer string, and no image comes back. The renderer is read before the page
  loads and again after the last capture. Before: in the 2026-09-24/25 diorama run, 35 of the 42 surviving
  results were `software (swiftshader)` captures taken at 51–317 MiB free. ANGLE runs on Vulkan first, with one
  retry on `--use-gl=angle` (`CROW_RENDER_ANGLE` pins one). `CROW_RENDER_GL=swiftshader` is now a refusal. Chromium
  152 still hands WebGL to SwiftShader under `--disable-gpu`, even without `--enable-unsafe-swiftshader` (measured,
  the smoke above); the renderer check is what caught it. On Windows the renderer cannot be read (no DevTools pipe),
  so it says `unverified`, and `frames` > 1 is refused there.

- **render_page lets path-traced kit pages wait up to 120 s** (#302, 2026-09-25). A local page that carries the
  voxel kit's `[crow-pt]` marker gets a `wait_ms` ceiling of 120,000; every other page keeps 20,000 (#213). The
  pathtracer skill asks for 60,000–120,000 on night or dark scenes and says never to shrink the scene to fit a short
  capture. Before: the 2026-09-25 lighthouse goal run capped every photo at 20 s, which held ~295 samples (291.5,
  295.5, 298), stayed grainy, and paused step 2 with an offer to shrink the scene. At the measured ~15 samples/s at
  1024² (RTX 5090), 90 s holds ~1,350 samples. Not measured live.

- **A failed goal step is never skipped by the engine; it climbs a ladder and then pauses and asks** (#294,
  2026-09-25, replaces #289's skip). Each failure has a class. *Environment* (render_mode unavailable, software on a
  GPU step, blank or identical frames, no judge answered): two retries 15 s apart, then pause. *Capability* (a valid
  capture the judge does not pass): a written reflection, then attempt 3 in a fresh context, then a split into 2–3
  sub-steps (`goal_step(n, "split", substeps=[…])`, reported with `sub`), then pause. The 25-turn and 60-turn caps
  and the budget pause too. On every pause the model writes robin a report: what it found, why it cannot go on,
  2–3 proposals, and whether he has more input. The report is shown in the window and on the phone. Only a typed
  line resumes. Before: the 2026-09-24/25 diorama run ended "complete with 4 skipped", with steps 5–8 skipped on
  software-GL captures and nobody asked. After: 0 skips without `/goal skip` in the unit replay. Not measured live.

### Fixed

- **A skip stored as `done`, and skipped drawn in the running step's amber** (#296). A `done` step whose note starts
  with "skipped" loads as `skipped`, which repairs the 2026-09-24 hand edit of step 4 (counted 5/9, now 4/9). The
  model can no longer set a user-skipped step `done` or `running`; `/goal redo <n>` reopens it. In the goal bar
  (window and phone), skipped has its own colour (`--skip`, violet), a dashed ring with a skip glyph and the word
  "skipped". Running keeps amber with a dot. A paused step shows a red pause glyph, and the head reads
  "Paused · step N".
- **`read_file` refuses images and other binary files, and names `read_image`** (#301, 2026-09-25). A file whose
  first 8,000 bytes hold a NUL, or that starts with a PNG/JPEG/GIF/WebP/BMP/PDF signature, is detected by its
  content, not its extension. It gets one line instead of bytes decoded as text: `error: …/island.png is a PNG image
  (543x768, 502,797 bytes) -- read_file returns text only; use read_image to see it`. A PDF names `pdftotext`, other
  binaries `file`/`xxd`. Before: the 2026-09-25 lighthouse run got 16,056 characters (~5,946 tokens) of mojibake for
  `reference/island.png`, blamed `read_image` and saved "read_image returns raw bytes" into `.crow/MEMORY.md`.
  UTF-8 text reads as before, including a multi-byte character at the 8,000-byte edge. `read_image` on a missing
  `-crop.png` whose frame exists now says a crop is written only under 50 % coverage and names the frame. Before: a
  bare `no such image`, twice in the same run. Not measured live.
- **A window started with `--root` keeps that folder when it restores the last chat** (#303, 2026-09-25).
  `crow --root DIR` now binds DIR for the restored chat and saves DIR as the folder the next start opens (`active` in
  `roots.json`), the same as a pick in the chip. Before: on 2026-09-25 15:19, `--root …/lighthouse-test` restored the
  chat "Voxel" (no folder of its own) into `diorama-test`, the last folder picked in the chip (09:45). The goal bar
  disappeared, and the next line ran in the wrong folder. A restored chat that recorded another folder is moved to DIR:
  the model gets #224's notice, and the memory head is rebuilt only if it named the other folder. Without `--root`,
  nothing changes. The terminal already let `--root` win. Covered by 4 window tests, 2 of them red without the fix;
  not verified live.
- **`check_diorama.py` borrows VRAM from serve like a Crow turn does** (#304, 2026-09-25). The checker runs as its
  own process, outside any Crow turn, so #297's lending had no endpoint and never asked serve. It now names the local
  serve before the first capture: `--serve` (default `http://127.0.0.1:8099/v1`, env `CROW_SERVE_URL`, `none` = never
  borrow). Before: on 2026-09-25 ~15:35 the lighthouse goal's `check.sh` failed all 10 checks with the ENVIRONMENT
  error at 280 MiB free while serve held the card, and `crow.log` had no `render:` line for it; render_page inside the
  same turn had borrowed 582 MiB twice minutes earlier. Covered by 3 tests, red without the fix; not verified live.

### Known limitations

- **Agent-built dioramas stay far below the references, and robin did not accept them.** The voxel kit renders
  reference-grade stills: proven with a hand-built scene (2026-09-25, RTX 5090). In the 2026-09-25
  lighthouse goal run the agent-built diorama stayed far below robin's reference images: crude props, a flat
  pond, and a lighthouse beam that read as a windmill. robin did not accept the result.
- **The diorama gates do not measure visual quality against references.** `check_diorama.py` and the judge's
  checklist measure the GPU, sample counts, prop counts and kinds, voxels, coverage, motion, repeatability, a
  near-uniform/near-black precheck and page errors. A page can pass every gate and still look nothing like the
  reference; `reference:` items are advisory until calibrated, and `--reference` only prints luma/saturation.
- **Live checks pending for every ticket in this release** (#293–#299, #301–#305): unit tests, node runs, a fake
  serve and GPU smokes of the scaffold only. The lend (#297, #304) was tested against a fake serve; the path-traced
  live mode (9e4daa4) and the 120 s wait (#302) were not run on the GPU for this release.
- **Windows**: render_page cannot read the renderer there (no DevTools pipe), says `unverified` and refuses
  `frames` > 1 (#293). `install.ps1 -PathTracer`, `install.ps1 -Selftest` and `tools/pack-release.ps1` were not run
  for this release (no PowerShell on the Linux release machine).
- `check_gui_prereqs` (not in CI) reports 2 of 3 prerequisites: point (ii), 26 glyph problems over the 2 shipped
  Google Sans Code faces, unchanged since 2.6.0.
- Not in this release: #300 (image generation beside a live session: decision open). Still open from 2.5.0: the
  Windows installer bundle (#196); `sampling_no_thinking`'s presence_penalty 1.5 (#246).

## 2.6.0 — 2026-09-24

**The phone becomes a second view of the session, and goal runs get a fresh-eyes judge.** A paired phone mirrors
the open session on the home LAN and, through Tailscale serve, over HTTPS from anywhere, with its own microphone
(#249 stages 1 and 5, #290). Goal mode gains a judge that scores captures in a fresh request, an evidence gate for
visual steps, a render-loop breaker, retry-then-skip for failed steps and `/goal skip` (#265–#268, #277, #286,
#289). Long runs keep more of the window: old tool results are cleared below the rollover, and Crow's own status
lines move to `crow.log` (#262, #263). The file tools share one syntax-check table and keep line endings (#269,
#276, #283); `render_page`, `build_bundle`, memory, `session_search` and delegate each close a failure seen in the
2026-09-23/24 diorama goal runs (#270–#275, #278, #279, #284, #285, #287, #288).

Everything on local `main` since 2.5.0 (origin/main 0c3e392): 87 commits, 2026-09-23 to 2026-09-24. Most
measurements are against robin's 2026-09-23 diorama goal run and its 2026-09-24 follow-ups. Tickets stay open until
robin's live check unless the ticket says otherwise.

### Added

- **Phone mirror on the home LAN** (#249 stage 1). `/remote on` (or the phone icon left of code/git/browser in the
  title bar) starts `cli/crow_remote.py`, a standard-library HTTP server on one LAN address and a fixed port
  (`remote_port`, default 8765; `0.0.0.0` is refused). The Remote dialog shows a QR code with a single-use 120 s
  pairing code; a new device waits up to 60 s for **Allow** on the desktop, otherwise it is denied. A paired phone
  keeps an HttpOnly, SameSite=Strict cookie for 400 days, of which only the sha256 is stored (devices in
  `secrets.json`); 5 failed pairings lock pairing for 10 minutes, and revoking a device ends its stream at once.
  Host (421), Origin (403) and cookie (401) guards on every request. The phone gets the session over SSE (a
  per-device replay ring of 5,000 events, snapshot otherwise, 15 s heartbeat, text coalesced to ≤ 4 updates/s) and
  calls an allowlist of 58 proxied page methods; each client has its own view, so a phone never moves the desktop
  and the other way round. The phone layer (below 700 px): a one-row composer, rail/code/git/browser as drawers, a
  44 px goal bar, pinned approvals, image upload (20 MiB), its own home-screen icon and title, and an auto-hiding
  header in the iOS home-screen app. `/remote on|off|status|devices|forget <name>`; settings `remote_enabled`,
  `remote_port`, `remote_host`. The QR encoder (byte mode, level M, versions 1–6) matches segno module for module
  on 20 URLs.
- **Phone mirror over HTTPS via Tailscale** (#249 stage 5). With a tailnet up, Crow additionally listens on
  `127.0.0.1:<remote_port>` for `tailscale serve --bg --https=443`, where only the machine's `ts.net` Host and
  Origin pass (a bare `127.0.0.1` Host stays 421) and the cookie is `Secure`. Crow never runs a Tailscale command
  that changes anything: it reads `tailscale status --json` and `tailscale serve status --json` without sudo into
  six states (missing, down, https-off, serve-missing, funnel, ready), and the Remote dialog offers
  **HTTPS · `<name>`** with one status line per state and the one-time serve command to copy (setting
  `remote_https`). Never plain HTTP on `0.0.0.0` or the 100.x address; with Funnel on for the name there is no
  loopback listener at all. Setup guide: `docs/user-guide/remote-tailscale.md`.
- **Tailscale as an opt-in installer component** (#249). `install.sh --tailscale` / `install.ps1 -Tailscale` read
  what is already done (read-only `tailscale status --json` / `tailscale serve status --json`, through the same
  state table as the Remote dialog) and print only the missing steps: the install command for the distribution
  (`sudo pacman -S tailscale` on Arch/Omarchy and Arch-likes, the official `curl -fsSL
  https://tailscale.com/install.sh | sh` elsewhere, `winget install --id Tailscale.Tailscale -e` on Windows),
  `sudo systemctl enable --now tailscaled`, `tailscale up`, **Enable HTTPS** in the admin console,
  `tailscale serve --bg --https=443 http://127.0.0.1:<remote_port>` (in an elevated shell on Windows) and the phone
  app when no iOS/Android device is in the tailnet yet. On Linux the section follows the install; on Windows
  `-Tailscale` prints it and exits without downloading anything. Neither installer runs sudo or elevates.
  `install.sh --selftest` drives every state against a fake `tailscale` on PATH (39 checks); `install.ps1
  -Selftest` does the same through a fake seam.
- **Phone microphone with a live transcript** (#290). On the HTTPS address the phone records with MediaRecorder
  and uploads the clip with the same guards; the window transcribes it with `crow_voice` (same model and settings
  as the desktop's dictation) and puts the words into that phone's input, never sent. Every 1.5 s the recording so
  far is transcribed as a greyed partial; recording stops after 2 s of silence once speech was heard; the button
  shows listening / writing / loading the speech model. One transcription per phone at a time, only the newest
  partial waits, finals first. One `crow.log` line per final dictation. Measured 2026-09-24 (faster-whisper small
  int8, CPU): 5 s clip 1.25–1.4 s, 10 s 1.4 s, 15 s 1.5 s; model load from cache 0.85 s. Plain HTTP keeps the
  keyboard-dictation hint.
- **Fresh-eyes judge for visual work** (#266, #286). The `judge` tool sends images and a rubric to a vision model
  in a fresh request with no history and stores the score in goal.json; without a pin it uses the local model. The
  rubric leads with the step's own text ("delivers: <step>"); the goal's `accept:` lines, PLAN.md, the caller's
  criteria or a default rubric only add to it (#286: step 3 "G-buffer and voxel volume" had passed on step 2's
  camera criteria). The verdict records its rubric source. Live on the 2026-09-23 "9+" final frame: 4 vision models
  scored it at most 2.
- **Evidence gate for visual steps** (#267). `goal_step done` on a visual step needs a capture from this goal and
  a judge minimum of at least `judge_threshold` (default 8; `--judge-threshold`, settings `judge_threshold`).
- **Render-loop breaker** (#268, #277). Three captures of one page that come back the same get a bisect nudge; six
  force a rollover that carries what was tried. A capture with a luma mean ≤ 4/255 counts as stuck, and captures
  are counted in every turn, including turns cut by a same-failure nudge or a mid-turn rollover (#277: on
  2026-09-24, 9 near-black captures of one page, luma mean 1–2/255, got 0 nudges; the replay nudges at session
  message 13 and forces the roll at 155). A black streak gets a concrete bisect (one pass in isolation; `getError`,
  `checkFramebufferStatus`, `readPixels`).
- **Failed goal steps are retried once, then skipped; `/goal skip`** (#289). The first `failed` sends the step back
  with the failure note and asks for a different approach; the second marks it `skipped` and the goal moves on. A
  goal whose steps are all done or skipped ends `partial` ("complete with N skipped"), never `done`.
  `/goal skip <n> [reason]` works in the window, on the phone and in the terminal. The goal bar shows skipped steps
  and follows goal.json every round, before every turn and on `/goal`, so a hand edit shows at once.
- **render_page metrics and an enlarged crop** (#265). Coverage, colours and luma per render; a small scene gets an
  enlarged content crop for `read_image`. 2026-09-23: the scene filled 7–22 % of 62 renders.
- **Context editing below the rollover** (#263). At 0.65 of the window, tool results older than the last 5 rounds
  become a one-line stub, in batches that free at least 10 %; the originals go to `session/cleared/`.
  `context_clear_at` in settings, `--context-clear-at`. Replay: rollovers 55 and 88 rounds later.
- **crow.log** (#262). Crow's own status lines go to `~/.local/state/crow/log/crow.log` with local time and offset,
  rotated, instead of into the chat: goal brake, same-failure streak, degenerate round, cache, budget, context
  clearing (#263), the rollover line and #98's boundary alarm, chat-open and `/goal` setup notes, the "no folder"
  note, a browser-panel crash (#279) and rejected memory writes (#285). The roll card, the `/goal` status answer
  and the #226 memory-ceiling stop stay in the chat.
- **One syntax-check table for all file tools** (#269). `edit_file` parses what it left (node for JS/HTML) and says
  whether this edit broke the file or it was broken before; settings `syntax_checks` maps an extension to a command
  for `write_file`, `append_file` and `edit_file`. Replay of 2026-09-23: 0 of 66 JS/HTML edits broke a file —
  parity, not a measured failure.
- **Machine facts in the prompt head, and memory may not contradict them** (#270). The head names OS, CPU, RAM, GPU
  and total VRAM (probed once per process) and says a tool's limit is not the machine's; `memory` refuses a
  no-GPU/CPU-only note that does not name the real card, and a "tool changes bytes" note. 2026-09-24: the diorama
  run had saved "Machine has NO GPU" on an RTX 5090.
- **render_page says why it rendered in software** (#271): the card's free VRAM against the bound, that the model
  server holds it, and that the machine has the GPU. 2026-09-23: 49 of 49 captures fell back.

### Changed

- **Version 2.6.0.**
- **Hosts nobody named are refused** (#288). `render_page` and `fetch_url` refuse a remote host that appears nowhere
  in the conversation (the user's words, a tool result, the goal, PLAN.md) before any socket or browser opens, with
  a next step; loopback always passes, a subdomain of a named host counts, and it is on in every mode, yolo
  included. Across a rollover a Crow-written line carries the newest 60 hosts.
- **The memory gate answers every approved write** (#285). A refusal, a duplicate or an expired entry comes back as
  "Memory: not saved -- <reason>" in the window and the terminal, and goes to `crow.log`. The Memory Consolidation
  tile has three states (collapsed, previews, full text) and shows a replace as "- old" above "+ new".
- **session_search covers rollover segments and chats put aside** (#287). 0 of 6 rollover segments on disk were
  searchable, because #261 took them out of the rail the index read. A segment hit is labelled
  "<chat title> (before the cut, <date>)", every hit prints its path, and a search in the first turn of a new chat
  no longer drops the chat just put aside.
- **A line typed during a turn is queued, never a stop** (#264, #282). In goal mode it goes before the goal nudge.
  A line opening with `/` that is not a Crow command (a path) is queued too; the button reads `↑ Queue` while the
  box holds a line; a Crow command waits in the box; an IME-confirming Enter is not a submit. **Stop pauses goal
  mode** (#282): Stop used to end one turn while the engine started the next at once; now the engine pauses with
  a note until the next line you send.
- **edit_file answers a missed `old` with the closest text** (#276): line numbers, what differs, whitespace-only
  named; a uniform indentation drift with one unambiguous window is applied and said. 16 of 147 edits missed on
  2026-09-23/24; replayed, 3 now land and 11 of the other 12 get the region.
- **Chat bubbles stand on the composer's edges** (#280): your bubble right-aligned on the input box's right border,
  Crow's text on its left border (the `●` column is gone). Headless Chromium 2026-09-24, 32 layouts: 716–780 px
  (user) and 40 px (Crow) off before, 0.0 px after.
- **The Subtasks card closes like the goal card** (#281): an `×` in the same place hides the card and its 306 px
  column reserve; nothing is cancelled, and a new subtask or a jump brings it back.
- **Rollover archives leave the chat rail** (#261) for the archive drawer; a Crow note is never a chat title.
- **goal_set carries the whole step record** (#260): notes, seconds and tokens of a re-declared step survive.
- **Comments on `presence_penalty`** (nibor1896/crow-nest#111) no longer say crow-nest reads an absent field as 1.5
  (it is 0 since crow-nest #91). No behaviour change: Crow sends 0.0 explicitly.

### Fixed

- **edit_file rewrote a whole CRLF file as LF** (#283). A one-line edit of a 40-line CRLF file left 0 CRLF
  (measured 2026-09-24 at 57ed521). The file is now read raw and only the matched span is replaced, in the ending
  it had: 40/0 stays 40/0, a 20/20 mixed file stays 20/20.
- **The browser panel crashed in the NVIDIA driver next to GPU renders, and a folded panel still loaded pages**
  (#279). 2026-09-24: the panel's WebKitWebProcess segfaulted in `libnvidia-eglcore` 5–10 s after each of two GPU
  `render_page` captures (~560 MiB free), and after six crashes the window stopped repainting. render_page's GPU
  bound is now 1,536 MiB while the panel is open or holds a page (512 MiB otherwise); a folded or hidden panel
  unloads its page and loads nothing; after a crash the dead view is hidden and the window redrawn, and a watched
  page is reloaded once; during a local-model turn the panel renders without hardware acceleration.
- **The visual gate refused the planning step** (#267). "Think and plan: … verify findings, write PLAN.md" counted
  as visual because of "verify"; the step's leading phrase decides now, and the refusal names the planning
  exemption.
- **An identical `render_page` after an edit replayed the old capture** (#273). `render_page` joins
  `run_command`/`build_bundle` in `NEVER_CACHED`.
- **`render_page` dropped a local page's `?query` / `#fragment`** (#272): `index.html?view=albedo` came back
  "no such page" (2026-09-24, session.json msg 36/37), and the model stored "file:// rejects a ?query" in memory.
  The file is checked without the suffix, which goes back onto a percent-encoded `file://` URL (RFC 8089 for drive
  letters and UNC).
- **build_bundle missed deno's esbuild and gave advice the model could not follow** (#274). It now looks in
  `~/.cache/deno`, takes `bundler` in settings.json or `--bundler PATH`, and its error names the settings file and
  the `node_modules/.bin/esbuild` link and says an `export` does not reach Crow. Measured 2026-09-24: finds
  esbuild 0.25.5 in `~/.cache/deno/dl/` (was: none).
- **The round that spent the tool budget was decoded and thrown away** (#278): 6 of 6 budget turns on 2026-09-24
  decoded one more round (298–4,290 tokens, 11,240 / 271 s in total). A budget turn is now 24 tool rounds + the
  answer (25 requests, was 26).
- **`goal_step running` on the running step restarted its clock** (#275): step 2's 73.5 min and its tokens vanished
  from goal.json on 2026-09-24. A repeated `running` keeps `started` and stores its note.
- **The goal brake judged a turn by its last message** (#258) and cut 157 + 52 messages of real work on 2026-09-23
  (cold prefills of 106k). A turn that ran tools is never "empty".
- **A forced answer after the tool budget could be reasoning-only** (#259) and the window showed nothing; the
  reasoning is surfaced now.
- **A subtask stopped while its attempt fails closed "failed"** (#242) and memoed the spot dead; it closes
  "interrupted" now.
- **A retired free model's 404 counted as transient** (#284). "unavailable for free" matched the retry pattern, so
  every subtask of the 2026-09-24 diorama wave spent 1 of 3 attempts on a spot that can never answer; it is a spot
  refusal now (memoed, next spot).
- **Phone mirror fixes found on robin's iPhone** (#249): pairing no longer holds a request open (Chrome for iOS gave
  up after ~6 s; `POST /pair` answers 202 and the page polls `/pair/wait`), a paired phone ignores a stale pairing
  code, a phone page load no longer re-recorded every note (1 "no folder" note became 32), and Safari's toolbar
  tint and scrolling stay as loaded after a drawer closes.

### Known limitations

- **The phone on real devices** (#249, #290): pairing, the mirror, the HTTPS address and the microphone were used
  live on robin's iPhone (iOS 27, Safari and Chrome); the auto-hiding home-screen header and the drawer fixes were
  checked in Chromium emulation only. Android is unverified. `/remote` is window-only; the terminal answers
  "stage 2".
- **Tailscale on Windows is unverified** (#249 stage 5): the dialog, the serve command without `sudo` and
  `install.ps1 -Tailscale` were not run on a Windows machine, and `install.ps1 -Selftest` was not run for this
  release (no PowerShell on the Linux release machine).
- **#279** is covered by unit tests only (red without the fix); not yet checked live.
- **#288** counts a tool result's hosts by URL only: a host that appears there as a bare name, and nowhere else,
  is refused.
- **#269/#251 need node on PATH** for JS/HTML; neither installer installs node.
- `check_gui_prereqs` (not in CI) reports 2 of 3 prerequisites: point (ii) fails on 13 glyphs missing from
  Google Sans Code (both shipped faces, 26 problems) — the 12 of 2.5.0 (0c3e392) plus U+1F3A4 🎤, new with the phone
  microphone (#290, 4d753af; `cli/crow_core.py:18037`, `cli/crow_gui.py:8740`). Measured 2026-09-24 at 0a0304b.
- Still open from 2.5.0: the Windows installer bundle (#196); `sampling_no_thinking`'s presence_penalty 1.5 (#246).

## 2.5.0 — 2026-09-23

Everything on `release-2026-09-23` since origin/main (6301e0e, 2026-09-20): 65 commits,
2026-09-21 to 2026-09-23. Most measurements are against the 2026-09-22 diorama session (655 messages after a
rollover at 17:12 CEST, 474 before) and the three 2026-09-23 diorama session files. Suites on the branch head
(0311d0d, runtime venv, Linux): test_crow_core OK (skipped=2), test_crow 451 OK (skipped=3), test_crow_gui 756 OK
(skipped=2), ruff clean.

Ticket state on 2026-09-23 (nibor1896/crow): **closed** -- #194, #201, #207, #208, #211, #213, #214, #215, #219,
#220, #221, #222, #225, #226-#239, #243, #244. **Still open, awaiting robin's live check or review** -- #195, #202,
#209, #210, #212, #216, #217, #218, #223, #224, #240, #241, #248 (windows-latest CI needs a push), #250, #251,
#252, #253, #254, #255, #256. #207 is the only one with a written live acceptance
(`docs/acceptance/issue-207.md`, attempt 2, 2026-09-21); for the rest acceptance is robin's GUI replay.

### Added

- **Subtask cards live in a pinned panel beside goal and git** (#255, `4be49fc`, `0311d0d`). `subCard` appended
  every delegate card into the chat (`#flow`, d994265), so the tiles scrolled away with the transcript. They now
  live in `#subpanel`, a third card in the `#panels` column between goal and git: header
  `N running · M finished`, running cards on top, finished/failed/interrupted ones in a collapsed
  `finished · N` fold; a jump opens the fold and scrolls only the panel; a chat switch drops foreign cards and
  hides the panel. The #233 reserve at >= 1100 px of chat width applies to it too. Measured 2026-09-23, headless
  Chromium, 1180x800, 40 turns, one `subs` event: `#flow.scrollHeight` +185 px -> 0 px; card movement when the
  chat scrolls 5027 px: -5027 px -> 0 px.
- **Goal mode: an acceptance check the user writes** (#250, `d46690f`). `/goal title | step | step | check:
  <command>` (or a `check:` line): the `done` that would close the goal runs the command through `run_command`
  (120 s clock, capture cap, #218 memory scope, cwd = working area); a non-zero exit refuses the `done` with the
  output and the goal stays open. The check is stored in `SESSION_DIR/goal-checks.json`, not in goal.json (the
  working area is writable by the model, and a command there would run unasked at `allowedit`). A model replan
  keeps it, `/goal off` drops it; the head names it.
- **write_file/append_file parse what they wrote** (#251, `bbb5260`). `.js/.mjs/.cjs` through
  `node --check <file>`; `.html/.htm` inline classic and module scripts (no `src`, no data-block type) through
  stdin, padded so the line number is the page's. One 5 s deadline through `_bounded_run`, files over 8 MiB
  and scripts past the 16th skipped, the first error only (line, message, a 160-char window with the caret).
  The write always stands; an append that does not parse yet says the file may still be in pieces. Replayed
  2026-09-23 over every JS/HTML write in the three session files: 58 writes -> 14 FAILED (5 .js + 9 .html),
  where before 0 said anything (the ticket's count over all 98 JS/HTML writes: 20 did not pass `node --check`).
- **render_page names the real API member and the argument count** (#253, `94f3bb8`). After the capture one
  `Runtime.evaluate` over the DevTools pipe (3 s) dumps the page's interface prototypes with each member's
  `length`. `X.name is not a function` gets the nearest real member (1-2 edits), the interface that has it and
  the page's own probe line; `WebGL: INVALID_*: fn` gets the source line's top-level argument count against the
  live `fn.length`. At most 6 `hint:` lines, every console line scanned. Replay of the 47 real render_page
  results of 2026-09-23 (Chromium 152.0.7977.82, SwiftShader arm): 18 carry a failing name or WebGL error;
  hints 0/18 -> 17/18 with live names (the 18th is a real shader failure), 10/18 in the fallback without them.
- **The browser panel lives inside Crow's window on Linux** (#201, #226, #227, #230, `5399a82`, `0b66dee`). A
  second WebKitWebView in Crow's own GTK window replaces the separate `crow-browser` window that Hyprland placed on
  its own. It has its own lasting profile under `<state>/crow/browser`, a 2048 MB memory kill checked every
  second (WebKit's default kill threshold is 0 = never; the chat says so), a bwrap sandbox when bwrap is present
  and no pywebview bridge. In-page navigation updates the bar, tab and Back; `_blank` and `window.open` stay in the
  panel; an answer link opens as a panel tab (Ctrl/middle click and the GitHub device code go to the system
  browser); renders reuse one tab; a new blank tab empties the address bar. Measured: Chromium tabs opened per
  link held ~73 MB each and were never closed (271 -> 1012 MB PSS over 10 loads); the panel stays flat at
  ~370 MB. Verified under broadwayd in a 3G scope: 17/17 end-to-end checks; a 400 MB test limit killed the page
  with the note after 4.1 s. Fallback: the old window (`CROW_PANE_WINDOW=1`). Windows keeps the old pane (#247).
- **Text selects and copies; links and paths are marked** (#228, #229, `a7a5248`, `e49509a`). WebKitGTK 2.52.6
  ignores unprefixed `user-select`, and pywebview's `text_select=False` injected
  `body{-webkit-user-select:none}`: nothing could be selected. One policy block in both spellings (content text,
  controls none); a right-click menu (Copy, Copy path, Copy path:line, Show in file manager, Open link) with APG
  keyboard support; Ctrl+C also copies through `Api.copy`. http(s) URLs and POSIX/Windows paths (with
  `:line:col`) are linkified in answers, inline code and tool results; a bare URL is one piece, and `_` inside a
  word or URL is no longer emphasis (CommonMark 0.31.2 6.2).
- **`build_bundle` tool** (#212, `0e22c51`, `b4ecf57`, `c7de871`). Bundles a page's ES modules, or one module,
  into a single self-contained offline HTML/IIFE with the esbuild already on the machine: `CROW_ESBUILD`, project
  `node_modules`, PATH, then the deno/npx caches. No network. Import maps become aliases, shaders import as text
  (bytes are never re-typed, the #91 escape hatch), images and models as data URLs. Bounded by one 120 s build
  clock, the #207 capture cap and write_file's fence. Its description tells the model that a file:// page cannot
  load ES modules and that a library is never flattened by hand. Measured on a scratch copy of the diorama app
  graph (2026-09-22): 957,410 B page, 0 errors, 0 warnings, 0.07 s. A `.js` entry built to `.html` names the
  module's exports nobody calls; a `.js` out without `global_name` names the exports nothing can reach.
- **The head names the working area on every request** (#222, `3ccecdf`). `prompt_head` opens with
  `Working area: <root>` and one sentence on how relative paths and a cwd-less `run_command` resolve there. It is
  byte-identical and at the same offset on both sides of the rollover cut. The 2026-09-22 K=2 head (6,738 tokens)
  had no working directory, and the model invented one (crow-nest#91).
- **A moved working area is said once** (#224, `c1033bd`): `[Working area is now X (was Y).]` opens the next user
  message (no sent byte moves). A->B->A withdraws it, reset drops it; `clear_root` re-pins the head too.
- **The #202 brake names the wall** (#202, `6b9f54b`). Each failed tool result of the running goal step is
  sorted into a class -- dead service (same HTTP 401/402/403 per tool and host), refusal loop, phantom path
  (ENOENT on a path first named by the failing call), render/command timeout, same exception signature -- and at
  three in one step the next nudge carries the class, the count and the way around instead of the step text;
  the flow shows a note. Replayed on the 2026-09-22 session: web_search 401 named at the first nudge after [29],
  phantom paths at [296], edit_file refusals at [348], render timeouts at [522] -- before the 12000/20000
  escalation.
- **Rollover carries its last good tool calls** (#214, `94e0c33`). Behind the rollover note the fresh context
  opens with the last 3 answered, successful, correctly shaped tool rounds (verbatim calls, results clipped to
  2000 chars and marked `[carried across the cut]`, images replaced by a sentence, 3000-token budget, an edit
  preferred). At the 2026-09-22 17:12 cut: 2 run_command rounds and an edit_file with `path, old, new`, ~1,250
  tokens. A regression test holds the tool list, sampling, thinking fields and `max_tokens` identical across the
  seam, and the digest request identical to the turn's.
- **The rollover seam carries the working state, and the window keeps what it knew** (#210, #211, `f692838`).
  The seam head carries the goal's step statuses; `goal_set` carries done-marks onto matching steps and names
  the first open one, so a post-cut replan no longer zeroes a 9/15 goal; the seam re-asserts mode, model, context
  and panel to the page, the chat band draws an archive card at the cut (live and on replay), and a level picked
  mid-goal queues for the between-turn gap instead of being refused. The digest leg retries a tool-call answer
  once on the same warm prefix (measured 2026-09-22: `finish=tool_calls`, 482 tokens, one half sentence rode
  across the cut) and fails loud under 200 chars.

### Changed

- **The installers name node, bwrap and systemd-run as optional helpers** (`1505865`). install.sh gains three
  warn-only preflight rows: node (MCP servers via npx, #251's `node --check`, #212's esbuild from the npx cache),
  bwrap (the #226 panel sandbox) and systemd-run (the #213/#218 memory ceiling). install.ps1's Node row no longer
  says every built-in tool runs without it. Nothing blocks the install. `install.sh --selftest` 26/26 (2026-09-23);
  install.ps1 reviewed statically only (no PowerShell on the Linux machine).
- **Thinking fixed on for Qwen3.8-Flash-Next, sent explicitly** (#225, `297a05b`, robin 2026-09-22). Both entries
  carry `reasoning_fixed: "high"` (llama: same bytes as the absent key, #160; serve: the template's xhigh). The
  turn, the digest leg, the turn after the cut and the review all send it; a stored chat level is ignored, a
  contradicting `--reasoning-effort` is refused with the reason, and the window shows no level for these points.
  **crow-nest changes from thinking OFF (2,962 of 2,962 requests on 2026-09-22) to xhigh with the 1024 cap.** The
  budget stays 1024 until measured (#245). `sampling_no_thinking` holds the card's non-thinking row
  (0.7/0.8/20/0.0/1.5) for a later flip (#246).
- **min_p on both Flash-Next arms: 0.01 for one day, then 0.0 again** (`e7d10a7` 2026-09-21, corrected by #225
  `297a05b` 2026-09-22). e7d10a7 moved both arms from 0.0 to 0.01 on the claim that 0.01 is the model card's
  operating point, after crow-nest #83 made the device sampler honour the field. Re-reading the card for #225:
  its Best Practices say min_p 0.0 in both rows, so both arms send 0.0 again. Both arms always moved together
  (one-sampler rule; `check_operating_point` 10/10).
- **write_file carries a whole file up to a stated limit; append_file only above it** (#254, `27f71b9`,
  `9a59872`). The descriptions of 6301e0e said "one append per section" and never what "large" is; the
  2026-09-23 diorama run (cap 16384) built 1-5 KB files from a head plus up to 10 appends: 61 write_file (median
  940 B), 50 append_file (median 319 B), 0 cut off. `whole_write_bytes()` keeps half the cap for reasoning (max
  1,042 tokens measured in a write round) and divides the rest by 0.75 tokens/byte (densest measured call >= 1 KB:
  0.735 with the model's own tokenizer): **10 KB at 16384, 5 KB at 8192**. Both descriptions state the number and
  the cap, written once at import (`CROW_MAX_TOKENS` moves it). An append that leaves a file at or under the
  limit says so once per path; #203's `TRUNCATED_CALL` names append_file and the part size.
- **A write result counts bytes and says it is byte-exact** (#252, `907f941`). `wrote N bytes` was `len(content)`
  -- characters; 32 of 112 writes on 2026-09-23 held non-ASCII text (`"ä—"`: 2 -> 5 bytes). The result reads the
  file back and adds `(sha256 <12 hex>, file N bytes). Byte-exact: ...`; a read-back that does not match is said as
  a WARNING. With #251 and #254 the append line reads e.g. `(+3 bytes, file now 5 bytes)` plus the receipt.
- **The composer and the chat column stand on the window's centre** (#256, `3287dc1`, `0311d0d`). #233 reserved
  the 306 px card width on the right only, so with a goal, git or subtask card and >= 1100 px of chat width both
  sat 158 px left of centre (5 px left without a card: the scrollbar gutter). The reserve is now symmetric, and
  `#flow`'s left padding carries the gutter width. Measured 2026-09-23, headless Chromium 1234, rail/code/git
  open/shut x 1180/1440/1920/2560 x 900 (32 combos): composer centre - window centre -158.0 / -5.0 px -> 0.0 px in
  all 32; column right edge >= 20 px clear of the cards in all 10 card combos. Cost: the column narrows with a
  card while the chat is under 1612 px (at 1116 px: 780 -> 464 px).
- **`run_command` is bounded like the render** (#218, `f813557`, `a56a2f0`). On Linux the shell runs in its own
  user scope (`MemoryMax=8G`, no swap, `OOMPolicy=kill`; `CROW_COMMAND_MEMORY_MAX`, `CROW_COMMAND_SCOPE=0`); a
  ceiling kill says so, and a timeout or capture-cap kill takes the whole process group and the scope. A headless
  browser in the command gets a note pointing to render_page. systemd-run's `${VAR}`/`$$` expansion is switched
  off (`--expand-environment=no`, systemd >= 254) -- it had emptied them. The tool description says what the
  scope does.
- **render_page's `wait_ms` is real time** (#213 follow-up, `d84cf9a`). On Linux the page runs `wait_ms` of real
  time over `--remote-debugging-pipe` and is captured when that time is up, even if it never finishes loading; one
  ceiling (15 s load + wait_ms + 10 s frame), `wait_ms` at most 20000. The old virtual-time path needed 32.7 s on
  the diorama page at every budget while its deadline was `wait/1000 + 8` -- raising wait_ms could never help.
  Now 5.6 s (software) / 5.8 s (GPU) at wait_ms 4000. A failed capture names the rasterer.
- **Every local request sends its own seed** (#217, `b0f2514`, `c9ff31f`): turn rounds, the rollover digest and
  the memory pass (crow-nest defaulted to seed 0, the seed that reproduced the 2026-09-22 corruption byte for
  byte). Seeds are recorded as `seeds`/`leg_seeds` in the turn bill.
- The thinking budget is looked up by the model the server reports, not the request's `"crow"` label (#220,
  `140a4f9`): the manifest's `reasoning_budget` now reaches local turns, reviews and digests from window and
  terminal. The terminal's rollover digest uses the turn's `--api-key` and `--model` (#214).
- `run_command`, `build_bundle` and the esbuild `--version` probe run through one bounded runner (#212/#207,
  `8e96b1f`); a grandchild holding the pipe no longer holds `build_bundle` past its clock (1 s deadline: 8.01 s ->
  1.25 s).

### Fixed

- **search_text no longer reads a 105 GB model container as text** (#207, `a045caf`, live-accepted 2026-09-21,
  `260cc87`). Live 2026-09-21: a pattern with no hits walked the CNQ container byte by byte and the turn hung
  mid-pair (spinner forever, only killing the app ended it). The walk now has the three bounds of a production
  grep: a NUL in the first 4 KiB means binary, files over 2 MiB are never opened (the result counts them), and
  past 30 s `search_text`/`find_files` return what they have with a note. `target` and `.cache` join one prune
  list both tools share. `run_tool` names unknown argument keys (`pattern_2`, `regex` rode in on the live call)
  instead of swallowing them.
- **run_command's capture is bounded while it is read** (#207 second incident, `d22f3a2`). Live 2026-09-21 a
  round-6 tool printed at pipe speed; Crow's python grew until 13.6 GiB were swapped and the kernel OOM killer
  shot serve (46.8 GiB pinned). The cap now lives in the reader threads, 32 MiB per stream, and kills the child
  with a result the model can act on; `read_image` refuses oversized files before reading.
- **The render browser has its own ceiling, reaper and blank verdict** (#208, #213, `3dbc015`). The 54 GiB
  software-WebGL runaway of 2026-09-21 ran in no cgroup of its own, and the kernel killed the server. The browser
  now starts in a scope in `session.slice` with `MemoryMax=6G`/`MemoryHigh=5G`/`MemorySwapMax=0` (verified on the
  cgroup: memory.max 6442450944, swap 0); a ceiling kill is returned as the reason. A timeout waits for the
  process it killed (wedged `while(true)` page: 9.2 s total, nothing left behind). A >= 99.9 % one-colour capture
  warns first ("treat it as no-signal"; reproduced blank: share 1.0 at 4714 B). The GPU is used (`--use-gl=angle`)
  at >= 512 MiB free VRAM per nvidia-smi, SwiftShader otherwise; the result names the rasterer. Pins:
  `CROW_RENDER_MEMORY_MAX`, `CROW_RENDER_SCOPE`, `CROW_RENDER_GL`.
- render_page: a capture that is almost but not entirely one colour (one line of text on white measured
  99.96 %) says "almost one colour" instead of "no-signal"; GCM login noise and DevTools pipe messages no
  longer crowd out the page's console lines (#213 follow-up).
- **Goal mode refuses a `done` whose own note says it is not done** (#250, `d46690f`). A note like "in spirit",
  "with deviation", "cannot be created", "unreachable" is refused, and so is a `done` without a note on a step
  last reported failed. Replayed on the 10 real `done` calls of 2026-09-23: 10/10 accepted before, 6 refused
  after; the 4 with positive notes pass.
- **windows-latest CI** (#248, `a90b962`). Two YoloTurnTests used `cat /etc/os-release` as the outside command,
  which Windows by design does not read as a path; they failed on windows-latest in every run since 2026-09-19
  (run 35438718703). The fixture is now a file beside the working area, `type` on Windows and `cat` elsewhere;
  a new case asserts it is outside on the running platform. Linux green; Windows not run (needs the push).
- **A reloaded window no longer restores the session twice and closes** (#209, `5753377`). #204's recovery
  reload fired `pywebviewready` again, and `ready()` re-ran start-up: `_probe` restored session.json into the
  running chat (`RuntimeError: restore() is for a fresh conversation`), posted the saved KV into `/slots/0`
  mid-chat and re-bound the roots. A second page load now only redraws the live chat. `_probe` restores only into
  a fresh conversation, and a streamed token with no open round opens one. 7 new tests, which failed on 3d26875
  with the live errors. Not run live in WebKit.
- **Secrets are named where they live** (#194, #195, `bdbe280`, `036925e`). Search hints and the Tavily 401/403
  refusal name the store by its real per-platform path first (the refusal also says which source the refused
  key came from) and the environment as fallback. MCP `${VAR}` credentials are read through `secret()`, store
  before environment; `_mcp_missing` no longer refuses a server whose token is only in the store. 13 new tests.
- **Goal-mode nudges mandate nothing** (#240, `9110044`). Nudges are user-role messages carrying the model's
  own plan text, so their paths counted as user-named. A `/goal` plan the user typed still counts (`by` in
  goal.json).
- **A reopened chat draws only the typed line** (#241, `3f83e86`). #224's rebind notice no longer shows in the
  user's bubble, and an image-only turn's notice no longer marks both folders as user-named.
- **The null device is not an outside path** (#243, `944a8e1`). `2>/dev/null` (and `\\.\NUL`) stopped at
  `auto`. 202 of 775 distinct stored commands contain it.
- **write_file refuses lookalike directories once and control characters always** (#244, `c4b642b`). A
  missing directory that looks like an existing sibling (`w` beside `work`) is refused once with "did you mean".
  Repeating the identical call creates it. Every created directory is reported. Measured in stored writes: 6 of
  111 paths carried a control character (`pipeline.py\n`).
- **A finished code block keeps its copy button** (#239, `3d26875`). `codeFinish` emptied the whole head row
  (`.cwh`) to write the path, taking #156's copy button with it; the path now goes into the name slot `.cwn`.
- **Drags and window resizes follow the pointer in long chats** (#236, #237, #238, `8362087`). Measured on a
  200-turn chat (12,968 nodes), WebKitGTK 2.52.6: rail drag 38.8 -> 3.6 ms per step, code grip 40.5 -> 3.5 ms,
  window resize 16.9 -> 4.0 ms, 0 px view drift after a mid-chat drag (was 2,079 px: WebKitGTK has no scroll
  anchoring); Chromium 152: rail drag 42 -> 16.4 ms per step, long tasks 7 -> 0. The rail widths are set on the
  elements that read them, not on `<html>` (#236); turns use `content-visibility:auto` only during a gesture and
  the view is restored afterwards (#237); per-event bridge work is gone on GTK (76 -> 0 bridge calls per drag)
  and coalesced on Windows (#238).
- **Nothing overhangs or clips** (#231-#235, `65b741c`). Composer buttons stay inside the box (477 -> 0 audit
  findings); long paths, URLs and compounds wrap in the column (1950 -> 0); menus open above the goal/git cards
  and the cards no longer cover the composer or, from 1100 px of chat width, the column; a squeezed code panel
  (< 150 px) hides instead of clipping; the settings sheet stays under the 34 px title bar; alignment, scrollbar
  corners, tab strip and focus rings. Audited over 185 Chromium and 12 WebKitGTK renders before and after.
- Integration re-audit of the GUI wave (`93aba43`, `5d59ebe`, `dffdeb6`): a drag no longer moves turns 6 px
  (margins under `content-visibility`); browser tabs shrink before they scroll (the active tab was hidden); the
  menu focus ring keeps its 5 px radius; `brPlace` keeps calling the bridge under `NATIVEDRAG`, because #201's
  in-window panel is placed by it on GTK (one call per real change).
- **The rollover note is data, not the user's words** (#223, `b405de1`). It is framed as a record written by Crow
  and the model; only the user's carried lines and the typed line count as user-named paths. The Qwen3.8
  template allows no other role for it (a late system message raises, and so does a turn with no user query).
- **An invented `cwd` never runs** (#221, `4791598`). `run_command` refuses a cwd that is not an existing
  directory before anything runs and before the approval card. The refusal names the working area and the near
  miss found on disk (edit distance 1-2, unique best match, case-insensitive on Windows):
  `'nibor11896' is 'nibor1896' here`. read_file, list_dir and the outside-root write refusal carry the same hint;
  `~` in cwd is expanded. A bare filesystem root in prose (`4120 / package`) no longer counts as a user-named
  path. That `/` in the 2026-09-22 rollover note had disarmed #144 and `_outside_root` for the whole session.
  Measured over all stored sessions: 5 of 18 cwd calls named a home that does not exist, and each cost a `pwd`
  round after a bare Errno 2.
- **Tool arguments under another harness's names are taken and said** (#215, `d3b5585`). `edit_file` accepts
  `old_string`/`old_str`, `new_string`/`new_str` and `file_path`; `read_file`/`write_file`/`append_file`
  accept `file_path` (write_file also `file_text`); `search_text`/`find_files` accept `path` as `root`;
  `memory` accepts `new_text` as `content`. The result opens with `[took old_string as old, ...]`; two names
  with different values are an error. After the 2026-09-22 rollover, 22 of 22 edit_file calls had failed on
  Claude Code's names, 15 of them first told to read the file.
- A call with an unknown key and a missing required one runs nothing and returns the tool's argument list,
  before the tool's own checks (#214, `95c2f0f`). `edit_file` checks `old`/`new` before the read-first rule,
  and a missing `new` is an error instead of silently deleting `old` (`new=""` still deletes) (#215).
- **Read-before-write is the file's state, not the turn** (#215, `fbc05e7`). A read counts across turns and
  goal-mode nudges while the file keeps the mtime and size it was read with; refusals say "never read in this
  conversation" or "it changed on disk since you read it". Crow's own writes keep the file counted. The state
  empties at a rollover (mid-turn included -- it did not before), a new chat, a model switch or a resume.
- `search_text` given a file as root searches that file instead of answering "no match" (#215).
- The terminal's between-turn rollover keeps the chat's memory, skills and goal (#214).
- **Rollover digest cut off at its token cap** no longer passes as complete (#210, `b9e54b0`): the unfinished
  last line is dropped and the note says `[digest cut off at the N-token cap ...]`; the digest prompt names a
  500-word budget (unmeasured). Measured 2026-09-22 17:12: 2000 tokens, finish length, 6,795 chars ending
  mid-bullet.
- **Delegation: a gated fallback spot is skipped** (#216, `f25f27a`). HTTP 403 (e.g. a model OpenRouter serves
  only to agentic harnesses), "no endpoints found" and 402 on a paid favourite mark the spot dead and try the
  next; up to six such refusals don't count against the three transient retries. 401, 402 on a free model and
  schema errors stop the chain at once. A failed delegate names every spot it tried and why, saved in
  `subtasks-registry.json` and the transcript. A mid-stream error chunk from a remote endpoint reports its
  code instead of "the model answered nothing".
- **Degenerate rounds stay out of the history** (#217, `b0f2514`, `c9ff31f`). A round that is bare tool-call
  markup, or a stub that visibly stopped (ends on a colon, a dangling word, comma or dash), is not stored; it is
  asked again once on the same prefix with a fresh seed. A stub on the retry is kept; markup twice ends the turn
  with one red line. Short answers ("Ja", "Erledigt", "42") are never touched. Replayed over 27 session files:
  8 markup + 79 stub rounds flagged, 0 false positives. A call cut by the model's own stop gets `UNCLOSED_CALL`
  naming the parameter instead of blaming the output limit; crow-nest's `finish: abort` and
  `crow_malformed_calls` are read.
- `check_shared_core` is green again (82/82): `tool_append_file` was never declared since 2026-09-20 (#219,
  `d528a5b`).

### Known limitations

- **#251 needs node on PATH.** `syntax_check` looks node up with `shutil.which("node")`; without it (the default
  on a Windows or Linux machine with no Node.js) it returns nothing: no line in the result, no warning, the
  write stands. Neither installer installs node. The 7 #251 tests are skipped when node is absent.
  Windows (`node.exe`, `_bounded_run`'s Windows path without a process group) is unverified. Whether the model
  acts on a FAILED line live is unmeasured.
- #250: the not-done phrases are a fixed list; live behaviour in a goal run is unverified (robin: add a
  `check:` to the next diorama `/goal`).
- #253: without the DevTools pipe (Windows) or without an answer only the page's own probe lines and the
  argument count are claimed (10/18 in the replay instead of 17/18).
- #254: whether the model now writes whole files up to the limit is unmeasured; the limit is fixed per process.
- #255/#256 were measured in headless Chromium only; WebKitGTK 2.52 is unmeasured (#256 assumes WebKitGTK
  reserves the 10 px scrollbar gutter like Chromium). Below 1100 px of chat width goal, git and subtask cards
  still float over the column (#233, needs a design decision). No real delegate run against the panel yet.
- **Windows is unverified** for #201/#226 (old pane window, `on_top`), #238 grip coalescing, #228 copy/context
  menu and #229 `explorer /select` (#247); #248's CI fix waits for a push.
- render_page on Windows keeps the command-line capture under the virtual clock (now with the fixed ceiling);
  it cannot capture on the deadline. A page with a blocked main thread now costs 25 s (was 9.2 s).
- `wait_ms` changed meaning from virtual to real time: light pages cost about `wait_ms` of real time.
- The render GPU arm has not been run against a loaded card; no Windows Job Object for the render (#213).
- run_command on Windows has no scope and no process group (no Job Object yet); the 8G ceiling does not scale
  with the machine's RAM.
- The #202 class counting runs between turns; one turn can still spend its tool rounds on one wall.
- The #220 budget now caps every default turn on the llama arm (absent level = high there). The 1024 budget
  binds at the operating point (8 of 9 rounds at K=26 in MEAS-0923, #245); budget and closing sentence are
  unmeasured with thinking on.
- `sampling_no_thinking` carries presence_penalty 1.5, undecided (#246); decide before a point is flipped to
  `none`.
- #217's live escape rate (does a fresh-seed retry avoid the bad round?) is unmeasured.
- A subtask stopped while its spot is failing ends `failed` and memos the spot dead instead of `interrupted`
  (#242, found by reading, not observed live).
- Not in this release: `/remote` phone mirror (#249), the Windows installer bundle (#196).

## 2.4.0 — 2026-09-19

### Added

- **`yolo` release level** (de69502). A fourth position on the mode dial that releases every
  question the other levels can ask: all tool classes run unasked, the outside-path question
  (#144) is silenced, and `git_commit` runs without asking. Two limits are part of the design:
  - `git_push` asks at **every** level, `yolo` included. The check sits before the level table
    in `stops_for`, the single predicate the turn gate reads.
  - `yolo` is session-only. `write_root_mode` stores `auto` while `yolo` is active and
    `read_root_mode` answers unset for a hand-edited `yolo`, so the level cannot survive a
    restart from disk.
  - Activation is deliberate on both surfaces. The terminal asks once per activation and accepts
    only a typed `y`; EOF or any other answer keeps the current level. `--mode yolo` starts
    without asking, because an explicit flag is the decision. The window arms the row on the
    first click ("runs everything unasked -- click again to accept"), disarms after four seconds,
    and plays a one-shot pixel burst on the mode chip once the level is actually adopted
    (delta-timed animation on a 3px grid, honours `prefers-reduced-motion`).
  - An outside command that runs unasked is still reported -- `run_command ran unasked for
    <paths>, outside the working area (yolo)` -- and the window draws its escape alarm as before.

- **`--language NAME` flag** (41d629f, terminal and window). Pins the reply language by replacing
  the sentence "Always reply in the same language the user wrote in." in the default system
  prompt with "Always reply in NAME, whatever language the user writes in." Default is
  `$CROW_LANGUAGE`, else unset; unset changes no byte. A custom `--system` prompt gets the pin
  appended; `--no-system` stays without a system prompt. A session resumed under a different
  language pays one full prefill, because the system prompt is byte 0 of the prefix.

- **Model menu row for engine-booted models** (98b2273). A model that is running but not
  bootable by the client -- the CNQ container served by crow-nest -- now gets its own row in the
  window's model menu, so its reasoning levels have somewhere to hang.

- **Reasoning ladder for the CNQ container** (f2a093a). The menu shows the container's four
  measured steps -- `none`, `low`, `medium`, `high`; `high` maps to `xhigh`, the highest step of
  the original template. On this engine, off is none: a level that means no thinking sends no
  thinking. Unknown level names are answered with a named 400 instead of silence. Engine side:
  crow-nest commit 92a28dc.

### Fixed

- **Hidden `presence_penalty` default** (c00906b). When the client sent no `presence_penalty`,
  crow-nest's serve applied 1.5 across the whole answer while llama.cpp computed with 0, and the
  engine-reported model name matched no manifest entry, so the model ran without its manifest
  sampling row. Crow now sends `presence_penalty` (default 0) on every request, and the
  operating-point manifest carries an entry for the CNQ container under the name the engine
  reports. Measured context (quality probe of 2026-09-18: 12 prompts, 3 seeds, thinking off):
  16.40 vs 8.21 non-words per 1,000 words of long German prose, crow-nest against llama.cpp --
  the measurement that started this change.

### Known issues

- None known for this release. Not yet measured: output quality of long unattended `yolo` runs.

## 2.3.0 — 2026-09-18

Goal mode gained guards for failure shapes observed in live sessions: a brake on the empty loop, a cap
on a single step, a shorter nudge, and a client that never again iterates a string into a plan.
Every request now carries its own output cap, local included. Minor rather than patch for that
reason -- no flag, no path and no measured number of 2.2.1 moves.

### A declared array that arrives as a string is parsed once, or refused

Seen live 2026-09-18, 11:15: `goal_set` was called with `steps` as a JSON **string**, the string
was walked character by character, and the panel read **0/852** -- 852 steps of one character
each. The plan was the model's own JSON, packed once too often, and nothing in the client looked
at what it had actually been handed before iterating it.

`run_tool` now unpacks a declared container before the tool sees it. `coerce_declared_containers`
reads the tool's own schema and, for every property declared `array` or `object` whose value
arrived as a string, parses that string **once** -- not repeatedly, and not into whatever comes
out: the result has to be of the declared kind, or the model gets a tool error naming the key, the
shape that was wanted, and the position at which the JSON breaks. The repair is never silent; a
note goes in front of the result, in the same bracket form `run_tool_cached` already uses for a
repeated call.

`goal_steps_from` holds the same line inside `goal_set`, which is also called directly. It parses a
string once, maps an object step to its `item` / `title` / `text` / `step` key, and refuses more
than twenty single-character items outright -- belt beside braces: a plan of 852 steps of length
one is an iterated string however it arrives.

Not measured: whether the model writes fewer such strings. This is a guard at the seam, not a
change to the prompt, and the one session is the only instance on record (6761bc1).

### The brake on the empty loop, and a cap on one step (#202)

Measured in the stored session of 2026-09-18: **thirty-five** answers of a single character (`I`),
one after the other, at **130,939 tokens** of context, each of them answering the same 330-byte
nudge. The 60-turn cap of #165 was the only thing in the way, and it counts the whole goal, so a
plan hanging on one step of six did not reach it. The day before, at 178,779 tokens, the same shape
ran forty minutes: 105 identical nudges and 300 turns on step 4 of 5 (#202).

Three things now stand between a plan and the night.

**The brake.** `goal_answer_mark` fingerprints an answer by its text *and* its tool calls with
their arguments -- `read_file` on twenty files is work, `read_file` twenty times on the same file
is a circle. Three identical answers, or three empty ones, are a loop; empty means at most two
characters **and** no tool call, because the two cases seen live were `I` and `3` and a rule that
knows only the empty string would have caught neither. On the third, those engine turns are **cut
out of the history** -- counted at Crow's own nudges, so a turn leaves with its answer and its tool
results, and nothing before the first of them is touched -- and **one** recovery line goes out in
their place, naming the step that is still open. An empty answer to that line stops the goal with a
line a user can read: how many times, at what context size, how many of how many steps are done.
There is no second recovery line. Cutting is the repair and stopping is not: an empty answer left
standing in the history is not a record of a mistake, it is an example, and the next turn reads it
as one.

**A cap on one step: 25 turns**, beside the 60 the whole goal has. The counter belongs to the step
and restarts whenever the step changes, so a plan that moves never sees it. A step that has taken
25 turns is cut wrong or cannot be done, and both are questions for the user rather than for another
turn: the goal pauses, `/goal` shows where it stands, and a typed line carries on.

**A short nudge from the second turn of a step.** The full block is 330 bytes of instruction, and
byte for byte in front of every turn it is itself the pattern the model continues -- at the
twentieth repetition it says nothing the first did not. When the last turn ran on Crow's nudge and
called a tool, the next one gets `[Goal mode, step N still open. Continue.]`. The first turn of a
step keeps the whole block, because that is where the step is named.

What this does not answer, and what keeps #202 open: the sampling row. Crow sends the model card's
thinking-mode row (temperature 1.0 / top_p 0.95) while the engine renders this model with
`enable_thinking false`, whose card row is a different one. Not measured: whether the brake would
have caught the 2026-09-17 session. Its nine echo answers ran 65 to 76 tokens, so they were neither
byte-identical nor empty, and the stored session has not been replayed against this code
(2b4964f).

### One output cap on every request, and a URL the model shortened

**`MAX_TOKENS = 8192` travels on every request, the local one included.** Until 2026-09-18 the
local body carried no `max_tokens` at all, on the reasoning that a cap would cut long answers the
local server is happy to finish and that no measurement had asked for one. A measurement asked. A
body without the field does not run uncapped -- it inherits the **server's** default, and that
default is not this client's to choose. crow-nest's was 1024, and a live turn paid for it: a
`write_file` carrying a whole SVG hit `finish length` after 1,024 generated tokens, **before** the
model had written its `path` argument, so the call arrived without one and the file was never
written ("The file path was missing"). crow-nest raised its own default to 8192 the same day
(8bad310), which is the right value and still not a thing a client may depend on. Away from home
the field was already load-bearing: OpenRouter answered `HTTP 402 -- you requested up to 65536
tokens, but can only afford 313` on 2026-08-23, because a provider reserves the model's maximum
output and prices the request against it.

8192 is the one value every Claude model accepts, which is what makes it one number instead of
per-model knowledge this client does not have. The subtask budget (`subtask_max_tokens`) and the
digest budgets still win where they are set. What the cap costs is named rather than hidden: an
answer longer than it is marked `CUT OFF at the token budget`, so a truncated answer no longer
looks like a finished one -- the half the 1024 incident was missing.

**`fetch_url` and `render_page` answer a broken address before the socket.** Live the same day the
model wrote `https://collectionapi.metm...org/v1/objects/343580` -- it abbreviated the hostname the
way prose does -- and got back `did not answer within 20s ('idna' codec can't encode character
'\x2e' in position 19: label empty)`. That sentence is a lie the error path told: nothing was ever
sent, the address could not be assembled. The model read the first half of it, concluded the
network was slow, and retried the same broken URL four times. The complaint now comes back before
the socket and names the thing the model can fix: an abbreviated host, a URL that names no host, a
space or a control character in the host, a port that is not a port, an address the idna codec
refuses. A trailing dot is a root and not a hole, and an IPv6 literal is never asked the codec at
all. Not measured: whether the model corrects itself on the named error -- the guard removes the
false cause, not the retry (2cedd44).

### The crow-nest line: the decode attention table is the default

Crow's third operating point runs on crow-nest, and the engine moved on 2026-09-18 in two ways that
are Crow's business. Both landed in crow-nest `v0.3.1`, tagged 2026-09-18 after this entry was
written; [`docs/operating-points.md`](docs/operating-points.md) records them as measured on the
engine's `main`, which is what they were at the time.

**`CROW_ATTN_LUT` is the default** (crow-nest #61, 61g, decided 2026-09-18): the split
decode attention kernel reads its e4m3 KV bytes out of a shared table. Bit-identical by
construction and measured so -- generated ids `56305eee11d6`, unchanged. `decode run`, fresh
process per run, W + 3N: **23.52 ms per decode token = 42.5 tok/s**, against the
`CROW_ATTN_LUT=0` fallback run's 25.20 ms = 39.68. The `serve` figure of record, taken as an arm
mean in one drift chain (`c3-sdsd-61g`, RTX 5090 / Arch Linux, four counted runs):
**53.32 tok/s mean, within-arm spread 1.0038**, beside that chain's adjacent `decode run` arm at
42.56 tok/s and spread 1.0010. Measured on Linux only; Windows has not been rerun at this default.

**Every image but the first of a process was read as the previous one** (crow-nest #73, `bc9cd9b`,
found and fixed 2026-09-18). The vision tower launched asynchronously and the blocking copy that
reads its result ran on the legacy null stream, which does not order against it, so the copy took
whatever the one shared scratch buffer still held: the previous image's embeddings -- complete,
plausible and one request stale -- and those rows were then cached under the **new** image's hash.
It reads as a fixed colour permutation and is really a shift by one request. **This is Crow's
`read_image` and every clipboard paste** against a crow-nest server. The first image of a process
was always correct, which is why nothing here caught it. No Crow code changes; the engine has to be
the one on `main` or newer.

Crow's own two issues stand where they stand. **#201 is open**: on Hyprland the browser tab opens as
its own window outside the Crow window instead of inside the browser area. **#202 is open** as
well -- the brake and the two caps above are two of its three points, and the sampling row is the
third.

### Known limitations

**Web search still needs a key.** Unchanged; listed again because it surfaced once more on 2026-09-18:
with neither `CROW_TAVILY_KEY` nor `CROW_SEARXNG_URL` set, `web_search` answers out of the keyless
sources, which cover code, packages and reference and **not** the open web -- the tool says so in
its own first line. Tavily is free and takes no credit card; `CROW_SEARXNG_URL` points at an
instance somebody already runs. The URL guard above does not touch this: a tool with no general
index cannot be given one by an address check.

**Suites.** 1,995 cases, 0 failures: `test_crow_core` + `test_crow` + `test_crow_gui`.
`check_shared_core` 79 of 79, `check_operating_point` 9 of 9, ruff clean.

## 2.2.1 — 2026-09-16

### Linux: `--load-mode mmap` decodes at 41.8 tok/s, and the window can see

Measured in the window against the running server, the evening after 2.2.0: **41.78 / 41.85
tok/s decode** (124- and 445-token answers, the second with an image), **428 tok/s prefill** on a
3,964-token cold first turn -- above the 36.7 of `--load-mode none`, because with the experts
file-backed nothing sits in zram any more. The load itself takes 8 s; the first turn pays the
page-ins.

Vision needed two flags, both now in the Linux line. `--image-min-tokens 1024`: at the model's
own minimum a 1097×380 paste became ~350 image tokens and the model answered that no image had
arrived (llama.cpp warns at load that Qwen-VL needs 1,024). `--no-mmproj-offload`: with 1,024
tokens and the projector on the GPU the server died with `SIGSEGV` in `ggml_gallocr_alloc_graph`
under `clip_encode` (core dump 18:43:27) -- ~1.3 GiB of VRAM is all the card has left at
`-ncmoe 31`. On the CPU the same paste was read line for line, 155 tok/s prefill on the image
turn. `server_command` spells the false as `--no-mmproj-offload`; the checker reads the word.
Windows keeps its line; neither flag is measured there.


### The server gets a scope of its own, because oomd took the terminal with it

Measured 2026-09-16 on Omarchy, four times between 17:42 and 17:56: `llama-server` started
from a terminal, loaded for a minute, and systemd-oomd killed the terminal's whole scope --
34, 60, 56, 34 processes, the server and every shell and agent that terminal had spawned. The
server's log ends at `loading model`. The mechanism: `ManagedOOMMemoryPressure=kill` on
`app.slice` (50 % for 20 s), `vm.swappiness=150` over zram, and `--load-mode none` holding
~48 GiB of experts in anonymous memory while the page cache holds the same bytes; on 62 GiB
the desktop goes to zram, pressure crosses the limit, and oomd kills the largest cgroup under
`app.slice`.

`crow_platform.server_scope_prefix()` wraps the boot -- the window's and
`tools/start-server.py`'s alike -- in `systemd-run --user --scope --slice=session.slice
-p MemoryHigh=<RAM − 8 GiB>` when `systemd-run` is on the PATH and the user manager's socket
is there. Out of `app.slice`, a kill can never take a terminal; bounded, the kernel reclaims
the server's own clean cache before anything else. Verified: a user scope accepts both
properties and `memory.high` lands in the cgroup. A fifth kill at 18:16 came with the scope and
`MemoryHigh` alone: the experts were still anonymous memory in zram and the desktop still
what got squeezed. So the Linux line now loads with `--load-mode mmap` (the experts become
page cache the kernel drops and re-reads instead of swapping), the scope adds
`MemorySwapMax=0` (the server's anonymous memory may not go to zram) and `MemoryMax`. Decode
under mmap is not yet measured against the 36.7 tok/s of `none`. `CROW_SERVER_MEMORY_HIGH`
moves the bound, `CROW_SERVER_SCOPE=0` runs the bare process. Empty on Windows, byte-identical
there.

The README's Start section names both commands per OS -- the server, then the window -- instead
of claiming the window boots the server on its own.

## 2.2.0 — 2026-09-16

Crow runs on Linux. Not a port of the page to a second toolkit: the same `cli/crow_gui.py`, the
same core, the same manifest and the same operating point, with one module between them and the
operating system. Windows does not move — every value it had is byte-identical, and the three
production bugs this port surfaced were Windows bugs.

### One platform seam, and the core stops knowing its OS

`cli/crow_platform.py` is the one module that answers "where" and "how" per platform: XDG
directories, install and models roots, the server binary name and search order, `/proc`-based
server discovery without `psutil`, spawn flags, kill by process group, the shell, the browser
candidates, the font store, the updater argv. Standard library only, one-way — it never imports
the core. `cli/crow_core.py` calls it at 45 sites and no longer mentions `sys.platform` or
`os.name`.

| | Windows, unchanged | Linux |
|---|---|---|
| install root | `%LOCALAPPDATA%\Crow` | `${XDG_DATA_HOME:-~/.local/share}/crow` |
| settings, secrets, skills, MCP | `%LOCALAPPDATA%\Crow\` | `~/.config/crow/` |
| sessions, `booted.json` | `%LOCALAPPDATA%\Crow\` | `~/.local/state/crow/` |
| server boot logs | `<cwd>\runs\` | `~/.local/state/crow/log/` |
| models | `<install>\models` | `<install>/models`, a link to the tree; `$CROW_MODELS` overrides it |

**Three Windows assumptions were production bugs and are fixed.** The `run_command` path
boundary (#144) knew only `C:\`, UNC and `%VAR%` shapes and released nothing on POSIX;
`render_page` looked for a browser before validating its argument and built `file:////tmp`; the
font install refused off Windows.

### The window on Wayland

Verified live on Hyprland 0.56.2: the window maps floating as class `crow`, streams a turn,
discovers a running server's `--port`, pastes a clipboard image, opens the browser pane. What
Wayland and WebKitGTK refused, and what answers it:

| | |
|---|---|
| the process died before the surface mapped, `Gdk Error 71` | WebKitGTK's DMA-BUF renderer against NVIDIA explicit sync. `__NV_DISABLE_EXPLICIT_SYNC=1` is set at import, before `webview` is loaded; `CROW_GDK_BACKEND=x11` is the escape hatch |
| `create_window(html=…)` yielded `about:blank`, `file://` never loaded | the window is created with a placeholder and the page arrives through `load_html` with a file base |
| `pywebview-drag-region` and `window.move` are no-ops | `Api.begin_move` and `Api.begin_resize(edge)` hand `begin_move_drag` / `begin_resize_drag` to the compositor from the title bar and eight edge grips, on the GTK main thread |
| a `hidden=True` window can never be shown on GTK | the browser pane clears the flag before `show()` and is a floating toplevel of its own — under Wayland it cannot be glued to the main window |
| no Win32 clipboard | `wl-paste` / `wl-copy`, `xclip` as the X11 fallback |
| the launcher and the float rule had nothing to key on | `GLib.set_prgname("crow")` before the window opens, so the app id is `crow`. PNG icons 16…512, `cli/crow.desktop`, and the rule in both Hyprland dialects — Lua for Omarchy, `.conf` for ini setups |

### The Linux placement: `-ncmoe 31 -t 24`, measured

The same card, one gigabyte less of it: the Wayland desktop holds ~1,083 MiB before the server
starts, and the Windows line was measured with 1,059 MiB left. At `-ncmoe 30` the model loaded
and died on its first request (`cublasCreate`: the resource allocation failed). At 31 the card
settles at 31,081–31,213 MiB after load, 31,334 peak in a turn. llama.cpp's Linux thread default
chose 4 of the Ultra 9 285K's 24 cores; two 200-token turns per arm, temperature 0, thinking off:

| threads | decode tok/s |
|---|---|
| default (4) | 26.41 / 25.57 |
| `-t 8` | 34.39 / 31.32 |
| **`-t 24`** | **36.72 / 36.22** |
| `-t 8 -tb 24` | 33.73 / 34.59 |

The two flags live as the line's `linux` object in `manifests/operating-point.json`, merged over
the line by `server_command` on Linux only; `check_operating_point.py` holds the Linux copies to
the merged line and the Windows copies to the line. Not measured: a cold 33k-token turn, the
16–20 thread range, and how much of the gap to Windows (41.76) is the extra CPU layer.

### `install.sh`, and an engine that is built rather than downloaded

`bash install.sh`, or `curl -fsSL …/install.sh | bash`. install.ps1's contract translated: the
same five steps in the same order, the same per-file sha256 verification, the same refusal to
elevate and to download the model. Preflight (Python, PyGObject, `wl-clipboard`, VRAM, RAM,
disk) runs before anything is fetched. It writes `$CROW_HOME/manifest.sha256` and reads it on
the next run, so a re-run reports what moved underneath it — and the only files it removes are
the ones the previous manifest listed and the new payload no longer ships, so `bin/`, `cuda/`,
`src/`, `build/`, `venv/` and a model tree beside them survive. `--selftest` drives 25 checks,
including the ones that must fail.

**The model root is a link, because a variable reached one entry point.** `--models DIR` wrote
`export CROW_MODELS="DIR"` into `$CROW_HOME/env`, and the generated `$CROW_HOME/bin/crow` was the
only thing that sourced it — so the window found the tree and nothing else did: `python3
~/.local/share/crow/tools/start-server.py flash-next-q2-k-xl` answered `model 'flash-next-q2-k-xl'
is not on disk`. It is now `$CROW_HOME/models`, a symlink to the tree, which is exactly where
`crow_platform.models_dir()` looks with nothing set — the fallback its own docstring describes,
written down on disk instead of into one process's environment, and read by the window, the
terminal client and `tools/start-server.py` alike. A checkout is its own `<install>`
(`crow_core.INSTALL_ROOT` is the parent of `cli/`), so it takes the same link and the last step of
the installer prints that line rather than writing into somebody's git tree. `$CROW_MODELS` is what
that docstring always called it: the
override, for one shell. `$CROW_HOME/env` is no longer written and a run removes the one an earlier
run left, byte for byte or not at all — an env file with a line of the user's own in it is kept and
named. A real `<install>/models` directory with files in it is never replaced: the installer warns
and prints the two lines that would move it aside. The model tree is not payload and never was, so
the link is not in `manifest.sha256` and a re-run does not report it as drift.

`tools/build-llama-server.sh` builds the CUDA engine, because the Windows release asset is an
`.exe` and there is no Linux one: llama.cpp pin `6c84c7d5d` (PR #27742, `qwen4exp`) plus PR
#27880 and PR #28040 — the three commits the operating point was measured at — CUDA 13.3 from
NVIDIA's redistributable components, `sm_120`, no root, everything under `$CROW_HOME`. The
result is not accepted until `ldd` resolves `libcudart` / `libcublas` / `libcublasLt` to that
same prefix: compiling against one CUDA major and linking another's runtime produces failures
that read like a warmup abort (upstream #28403, #25060).

### The drift checker read a quote as part of a path

`tools/check_operating_point.py` captured `--slot-save-path "…\Crow\session"` with its closing
quote and compared `session"` against the manifest's `session`, so the README's Qwen line — which
is correct, and which a human copies and runs — had been red since it was written, and the
installer's own printed lines were laid out around the parser instead of around the reader. A
quote is the shell's punctuation, not part of the value, and is now stripped the way the
PowerShell line-continuation backtick already was. **8 of 8 sources agree** where it was 7; 9 of 9 with the Linux entry.

### Also

| | |
|---|---|
| `pyproject.toml` | hatchling, version read out of `cli/crow.py` so there is no second literal; `pywebview>=6.2`, extras `voice` and `dev`; ruff configured for `E9`/`F63`/`F7`/`F82` only — syntax and undefined names, nothing about style |
| `justfile` | `check`, `test`, `lint`, `run`, `serve`, `engine`, `install` |
| `.github/workflows/ci.yml` | ubuntu-latest and windows-latest: ruff, the suites, `check_shared_core`, `check_operating_point`, and `install.sh --selftest` on Linux |
| [`docs/user-guide/linux.md`](docs/user-guide/linux.md) | install, the paths table, the window on Hyprland, models, engine, troubleshooting |
| README | a **Linux** section with its own table, the install line, the model and engine lines, and the by-hand server line in bash — held to `manifests/operating-point.json` by the same checker as the PowerShell one |

**Suites.** 1,947 cases, 0 failures: `test_crow_core` + `test_crow` 1,313 (25 of them failed on
Linux before the seam), `test_crow_gui` 634. `check_shared_core` 79 of 79. `check_operating_point`
9 of 9. `install.sh --selftest` 25 of 25.

**Not verified:** the pointer-driven drag and resize themselves — the bridge, the edge table and
the GTK call are covered by the suite, but synthesising a real button press against the
compositor needs privileges the target machine does not have.

## 2.1.0 — 2026-09-01

Flash-Next gets the placement it should have had, the engine gets its last two patches, and the
question of whether the engine has more to give is closed with a number. Minor: `DEFAULT_BASE_URL`
and every client-facing flag are unchanged; the server command line moved.

### `-ncmoe 30 -b/-ub 2048`: +16.8 % decode, +34.8 % prefill, −24.4 % wall clock per turn (#182)

The ubatch buffer held VRAM that expert layers can carry. At `-ub 4096` only 8 of 48 expert layers
fit on the card; at 2048 it is 18, and every layer that moves takes 10 × 1.7883 MiB = 17.9 MiB
per token off the RAM bus and puts it on VRAM at ~20× the bandwidth.

| | `-ncmoe 40 -ub 4096` | **`-ncmoe 30 -ub 2048`** | |
|---|---|---|---|
| decode | 35.74 (35.13–36.11) | **41.76 (40.34–42.76)** | +16.8 %, no overlap |
| prefill | 539.98 | **727.65** | +34.8 % |
| wall clock per turn | 67.9 s | **51.3 s** | −24.4 % |

Conditions: 2026-09-01, three interleaved runs per arm, one boot per run, one 33,494-token cold
turn, 200 tokens out. Fenced from both sides in both dimensions: `-ncmoe 32` → 59.6 s, `28` →
97.5 s, `-ub 1536` → 55.5 s, `3072` → 98.8 s. **Wall clock is the measure, not decode:**
`-ncmoe 24 -ub 1024` has the highest decode ever seen here (46.59) and is 2.5× slower per turn,
because prefill collapses to 208 and an agent prefills every round. Accepted live at 41.8 tok/s.

Two notes were replaced rather than left standing. `-ub 2048` had been recorded as "wins
nothing" (measured at `-ncmoe 40`, where VRAM was not the limit) and `-ncmoe 32` as "dies 2/2"
(measured at `-ub 4096`, where it is). Each was true under its own conditions and each blocked
the other. **A lever declared dead has to name which state of the other lever it was measured
against.**

VRAM at this line, settled after load: **30,984 MiB of 32,607, 1,059 MiB left**, no load peak
above that (3 MiB over 57 samples). Not measured: whether an image prefill fits in that gigabyte.

### The engine binary: two patches on the pin, and one of them was wrongly blamed (#159)

**PR #27992 was closed by its own author** on 2026-09-01 — never merged, "better fix in #28040".
The operating point had carried it as a local patch since 1.7.0. **PR #28040** replaces it: the
same O(log n) `get_prev_tokens` lookup, 62 lines smaller, ported by hand (9 of 10 hunks).
Measured at parity, four boots interleaved, six depths, one variable: fixed term +0.6 % against
1.335 ms of spread inside one arm. The closed PR's unit test, ported across implementations:
9,480 lookups, 0 failures, and a deliberate off-by-one turns 3,416 of them red.

**PR #27880 runs on the pin.** Since 1.7.0 the docs said `b10687` dies during CUDA warmup
*because of* #27880 "reduce number of graph splits". That was an A/B across a full day of
mainline, and it was wrong: #27880 isolated on the pin (zero hunks by hand — no commit between
the pin and the PR's parent touches its two files) boots, survives the warmup and serves, in four
of four boots. It hoists the PLE embedding out of the per-layer loop into the token embedding's
graph split: **62 graph splits per decoded token instead of 64**. What kills `b10687` on this
card is not attributed; the pin does not move.

| pin + #28040 + #27880 vs pin + #28040 | |
|---|---|
| fixed term (one clean pair) | 23.072 ms vs 24.061 — **−0.99 ms, −4.1 %** |
| spread inside one arm | 1.354 ms |
| decode at 30k depth | 40.96 vs 40.78 tok/s |
| ten-task gate | **10/10 and 10/10**, control 10/10 and 10/10; token counts per task identical across all four cells; wall clock 119.7 / 116.0 s vs 121.4 / 119.3 s |

Free and not worse. Whether it is 1 ms better is below what two rounds resolve. The "~52 tok/s
if the splits halve" arithmetic of the day rested on a halving that does not happen at
`-ncmoe 30`: 60 of the 64 splits are the CPU expert layers, and #27880 removes the other two.

### The fixed term is synchronization, and nothing inside the engine moves it (#159, #186)

`ms/token = 24.06 + 0.0706 per 1,000 tokens of context` (r² 0.93). Profiled with VTune,
2026-09-01: **67.1 % of CPU cycles** per token are kernel, NT sync primitives and the OpenMP
runtime; **27.8 %** are `ggml-cpu`; the barrier spin alone is 63.1 % of CPU time. The DRAM bus
runs at 28.157 GB/s of 84 — 33.5 %, never the limit. Handoffs per decoded token are `4 + 2 × ncmoe`
exactly (r² 1.0000 over seven placements).

Every lever inside llama.cpp is dead by a direct measurement:

| lever | result |
|---|---|
| RAM bandwidth | 33.5 % busy, 0.0 % of the time saturated |
| expert cache (`--moe-stream`) | 1.16–1.89× slower per agent turn on every task; prefill decides |
| thread count | saturates: `ms/token = 21.66 + 65.59 / threads` (r² 0.99) |
| `OMP_WAIT_POLICY` | `ACTIVE` is the default and the optimum; `PASSIVE` costs 16.3 % |
| `-ncmoe` below 30 | spills into WDDM |
| the barrier implementation (`GGML_OPENMP=OFF`) | ggml's own threadpool: **+4 to +6 ms per token** at 30k–140k, plus a 42–70 ms first-request warm-up; `--poll 100` worse still |
| split count at fixed placement (#27880) | −2 of 64, ~1 ms at the resolution floor |

The ceiling for a perfect implementation on this hardware is 86 tok/s, bound by GPU work at
sm 46 %. **It is a bound, not a target, and there is no path to it inside this engine.** An own
*server* buys nothing: `tools/server` is 21,528 of the ~294,000 lines Crow depends on — 7 % — and
none of the four things that blocked the project on 2026-09-01 lived in it (#186). Whether an own
*engine* follows is #188, open, with its goals still to be set.

### Fixes

| | |
|---|---|
| #184 | `run_command` names its shell. It runs `cmd.exe` and said only "run a shell command"; on a PowerShell machine the model guessed PowerShell, failed, and fell back — one wasted call in every turn that lists a directory |
| #185 | the GUI suite booted a real Flash-Next server once per model-menu key — 50 s and 30,984 MiB each, three orphaned servers over three runs, two of which took a live session down. The plumbing is mocked; 94.6 s → 22.3 s. Five unclosed handles in test code closed in the same pass |
| #182 | `tools/test_check_operating_point.py` had been red since #140: the fixture never received `--mmproj`. Green again |

### Not built

- **No own inference engine in this release.** The decision is open on #188; the server alone
  is 7 % of the dependency and was never in the way.
- **No pin move to `b10687`.** It still aborts here, and the cause is now *unattributed* rather
  than wrongly attributed.
- **No `--tensor-read-lazy off` probe** of the `b10687` abort. The PLE table is 26.8 GiB and would
  go resident next to the CPU experts; the question is moot on the pin.
- **No further rounds on #27880.** Two rounds resolve 1.35 ms; the effect is at most that.

## 2.0.0 — 2026-08-31

Flash-Next becomes the default operating point, the model gets eyes, and the window gets a
browser. Major, because `DEFAULT_BASE_URL` moves from 8082 to 8083: a client started with
nothing and told nothing now looks for a different server.

### The default operating point is Qwen3.8-Flash-Next (#140, #159)

`DEFAULT_BASE_URL` is `http://127.0.0.1:8083/v1`. Qwen3.8-27B stays shipped, measured and
bootable as the second operating point on 8082; DeepSeek 0731 stays where it was.

| | Flash-Next `UD-Q2_K_XL` | 27B `UD-Q4_K_XL` |
|---|---|---|
| on disk | 73.45 GiB, 3 shards | 16.35 GiB, one file |
| VRAM | 27,707 MiB | 26,140 MiB |
| decode | 32.44 tok/s (31.06–33.20) | 123.05 / 133.18 tok/s |
| prefill | 970.44 tok/s (941.07–985.32) | 2,262.96 tok/s |
| engine | local pin `6c84c7d5d` + PR #27992 | packaged `b10269` |
| licence | `qwen-community-1.0` | Apache-2.0 |

Flash-Next conditions: 2026-08-30, driver 616.56, one 31,979-token cold turn per boot, three
rounds interleaved against a same-session control (964.92 / 29.05). **Not measured:** decode at
a full 200k window.

**The engine is a local build.** `qwen4exp` exists in llama.cpp only from PR #27742 and the
packaged `b10269` cannot load it. On the bare pin without #27992 the numbers are 959.81 / 28.60
over ten boots.

### `read_image`: the model can look at a picture (#170)

Vision ran in one direction. A person could hand an image in — `/image`, a drop, Ctrl+V — and
everything the model produced itself was invisible to it. Seen live 2026-08-30: it began
decoding PNG bytes in node to get pixel statistics instead of an answer.

| | |
|---|---|
| class | `reading` |
| wire | the tool message's content becomes `[{text}, {image_url}]` — the block a pasted image travels as. `server-common.cpp` converts `image_url` parts **regardless of the message's role**, so the next round sees it the way `/image` shows one |
| boundary | `_rooted`, like every other reader (#177) |
| no projector | `refuse_images` is asked **before** the block is attached: a picture sent to a blind server is an HTTP 500 that costs the whole turn |

Flash-Next gets its projector: `mmproj-F16.gguf`, 904,004,000 B, from the ROOT of
`unsloth/Qwen3.8-Flash-Next-GGUF` — a download filtered to the quant folder misses it.

Accepted live: asked about a Hugging Face card, the model named the `huggingface.co` watermark
and the browser hover box, both of which exist only in the pixels. **Not measured:** the
projector's VRAM cost on a line already at the card edge under `-ncmoe 40`.

### A browser panel, and it is not an iframe (#175)

The model used to build a browser out of shell commands. Measured during one stall in the
2026-08-30 voxel run: **19 chrome processes, the oldest two hours old, one with 7,511 s of CPU**,
llama-server idle, the window silent. Three stalls in that run, each needing a person to kill
processes by hand.

A globe in the title bar opens a panel built like the code panel — tabs, an address bar, per-tab
history. Behind it is a **second frameless WebView2** laid over the panel rectangle, not an
iframe: `X-Frame-Options: DENY` and `frame-ancestors 'none'` refuse embedding, and that is
claude.ai, github.com and google.com. A window is top-level, so neither header applies. Measured
2026-08-31: in an iframe only example.com loaded; in the pane all of them do.

`render_page(path)` gives the model the same thing, supervised:

| case | wall clock | result |
|---|---|---|
| page settling at 300 ms, `wait_ms=1500` | 0.5 s | screenshot shows the settled text |
| page settling at 3 s, `wait_ms=6000` | 0.5 s | not killed |
| endless `fetch`, `wait_ms=1200` | 9.3 s | ends itself, names the timeout, no screenshot |

It owns its child: `proc.kill()` on its own handle, never a name and never a process list — the
#158 lesson, paid once when a sweep took down a running test server. Its own
`--user-data-dir` per run, because without one Chrome hands the job to a running instance and
returns exit 0 with nothing. stdout and stderr go to files, because `communicate()` hangs on
Windows after a kill when a grandchild holds the pipe.

The result opens as a tab showing the **screenshot**, not the live page: the page can have
changed since the model looked.

### The git panel moved into the chat (#173)

Out of the side column, under the goal panel, as one flex column — a goal that starts or ends
moves it with no JavaScript, because a hidden goal panel takes no space. The pair gets 70 % of
the chat height where the goal alone had 60 %.

### Notes and cards stay where they happened (#173)

Every mark carries `at`, the number of messages that stood before it, stamped at one place in
`Api.push`; `_replay` threads them back in rather than appending them. The rollover note, which
marks where the context was cut, no longer claims the cut was just now.

The approval card was left behind by `fold()`: the `Trace` element is created at the flow's end
*at that moment* and every later round is pulled into it, so a card hanging off the flow ended up
below everything. It now hangs off the round that asked.

### A turn's bill outlives the cut (#171)

`timings` beside the messages, one record per turn, numbers only — `clean_timings` keeps the
rendered line out, because a sentence is the one thing that cannot be evaluated afterwards. A run
that rolled over can be read turn by turn from the archives.

### Thinking is capped per request (#176)

`reasoning_budget` 1024 for `flash-next-q2-k-xl`, from the manifest. It is a **brake, not a
saving**: measured at a single prompt it turned one 7,870-token block and 352.0 s into 116.3 s,
and in goal mode it does nothing at all, because nobody there writes a long block — ten blocks of
181 down to 14. Four interleaved goal runs at 128 came out *slower* (73.8 s against 65.4 s) and
thought *more*. 1024 never fires in goal mode (largest block over four runs: 324) and catches the
runaway block in ordinary chat. **Do not lower it** — that experiment has been run.

Three levers against the thinking share were tested and all three are dead: the reasoning level
(`none` is the most expensive of four — 3.6× time, 1.8× tokens), the verification sentence in the
nudge (2.3 tokens on 10,500 — 0.02 %, against a spread of s = 2,315), and the cap above.

### Fixes

| | |
|---|---|
| #177 | relative paths resolved against the launcher, not the bound folder. `_ROOT` was a fence and never a ground: four goal runs did "read a file only in this folder" outside that folder, and every checker was green |
| #178 | an approval for a path out of the user profile was written down as if the user had named it |
| #179 | a user-named path with a space in it was refused, and its truncated prefix released a different folder |
| #172 | a tool call that never returns now shows its own clock |
| #168 | a step worked on again no longer keeps its green tick |
| #169 | tokens per step were counted once per turn while steps were ticked several times inside one |
| #174 | the goal header's total did not survive a rollover |
| #161–#165 | goal mode: the store, the panel, the engine, concurrent operation |

### Not built

- **No lower thinking cap than 1024.** Four runs show 128 costs.
- **No `min_p` change** against the occasional Chinese token at 2-bit. It leaves the model card's
  sampling, against which every #140 measurement was taken.
- **No sweep by process name**, anywhere.

## 1.7.0 — 2026-08-30

The third model gets a faster engine, and two checker suites that had been red
for weeks can go red again on purpose.

### Flash-Next decodes 11.7 % faster: the pin carries PR #27992 (#159)

qwen4exp's PLE n-gram embedding called `get_prev_tokens()` on every graph build,
and at the pin that walked **every used cell** of the KV cache testing up to
`LLAMA_MAX_SEQ = 256` sequence bits — once per decoded token, on the critical
path. PR #27992 indexes `(seq, pos)` cells instead.

The engine measured its own cost before any throughput number was read. Under
the PR's `verify` mode at 31,979 tokens of depth: **scan 4450.6 µs against index
14.8 µs, 0 mismatches over 250 calls.**

Measured on the shipped binary, three rounds interleaved against a same-session
control, one 31,979-token cold turn per boot:

| | control | pin + #27992 |
|---|---|---|
| prefill | 964.92 (936.31–981.07) | 970.44 (941.07–985.32) |
| decode | 29.05 (28.49–29.84) | **32.44 (31.06–33.20)** |

**+11.7 % decode with no overlap between the ranges; prefill flat at +0.6 %** —
the change is decode-side, as claimed. Per-token saving 3.59 ms.

**The gain is proportional to context depth**, because the scan is `O(n_kv)`:
about 3 % at the ten-task gate's few-hundred-token depth, +11.7 % at 31,979
tokens, larger and unmeasured at the 200k window. Correctness twice: the PR's own
unit test (9,480 lookups, 0 failures) and the live mismatch count above. The
ten-task gate is 10/10 twice with token counts **byte-identical** to the control —
an engine-only change cannot move what the model writes, and that is measured
rather than assumed.

**It is a draft PR** whose author notes it charges every other architecture a
little for qwen4exp's benefit. If it is rejected upstream, drop the patch: the
binary key falls back to the bare pin, which measured 959.81 / 28.60 over ten
boots.

**Interleaved on purpose.** This machine drifted −5.0 % prefill and −5.5 % decode
within one day — larger than the effect and enough to flip its sign. Three times
on 2026-08-30 a control from another session would have produced the wrong
verdict. No arm is compared against a control from another session.

### Two checker suites had been red for weeks, and hid the next regression

`test_check_operating_point.py` went red on 2026-08-21 and stayed red through
**ten releases**. `test_check_shared_core.py` failed 18 of its 19 cases. Both
checkers were green on the real repository the whole time — what was broken was
the half that proves they can go red at all.

The damage is not hypothetical. The comment above `QWEN_LINE` says in as many
words: *"It moves again when a third model key lands, and somebody should have to
look."* The third model key landed with #140 and nobody looked, **because the
suite was already red**. Three regressions had accumulated behind the first one.

Repaired: the fixtures now carry the vision switch, the third model's line, a
helper entry, and the blank lines every real document has between two command
lines. Two real defects in the checkers came out with them:

- **A file the caller names and that is not there is an error, not a miss.**
  Making the document rule "at least one live page prints this key correctly" was
  right, but it also swallowed `--extra`: a mistyped path passed silently as long
  as some other page carried the line.
- **`command_regions` clamps backward now, for the same reason it clamps
  forward.** A region stops at the next anchor so it cannot merge two command
  lines; nothing stopped it reaching back into the previous one, and since the
  two-line lookback for the env prelude landed, two commands one blank line apart
  were enough for the second to read the first one's `--port`. A correct document
  reported as drifted.

### Also

- `manifests/operating-point.json` records the reasoning levels this model
  actually accepts as unmeasured no longer: `max`, `minimal` and an explicit
  `off` return HTTP 500, and `UNSET` renders byte-identically to `high` (#160)
- the MTP head is not absent from Flash-Next — the checkpoint carries it and
  mainline's converter opts out; a small Qwen3.8 GGUF now exists too. Speculation
  stays dead for a better reason: verifying N drafted tokens reads the *union* of
  the experts they select, 19.8 of 512 at N=2 against 10 for a single token
- suites 427 / 732 / 528; checkers `check_operating_point` 8/8,
  `check_shared_core` 75/75, and their suites 17/17 and 19/19

## 1.6.2 — 2026-08-30

Three roots closed in one night: the silent server deaths, the empty rollover
digest, and the fork the third model needed.

### The silent server deaths were a console signal (#158)

The class that had been blamed on the driver JIT, the compute cache and the PR
build since 2026-08-28. WER LocalDumps were armed and the next death left **no
dump**; the boot log ended on a completed turn (`release ... n_tokens = 169987`)
with no error line; Crow reported exit code 1 (0x00000001), an ordinary return
value rather than an NTSTATUS; and neither `stop_servers` nor `proc.kill()` had
run. No crash, no fault, no killer — the process ended itself, in order.

The only `exit(1)` reachable at runtime in llama.cpp's server sits in its
`signal_handler`. `start_server` spawned the server with no `creationflags`, so
it inherited the console **and the process group** of the window — and Windows
delivers `CTRL_C_EVENT` to every process in a group. Every Ctrl+C in the terminal
the window was started from reached the server too.

`CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` now. Neither stop path is
affected: `taskkill /PID` and `TerminateProcess` reach a process in its own
group unchanged.

### The rollover digest was thinking instead of answering (#157)

Measured against the running 27B, one variable per arm, `max_tokens 400`: with
the chat default `high` the reasoning ate the entire budget — 400/400 tokens,
**0 characters of content** — which is why a roll produced a note with no digest
block. The model thinks at every level, so no lower step heals it.
`chat_template_kwargs: {"enable_thinking": false}` lands the answer complete in
87 of 400 tokens. Templates that do not know the kwarg drop it silently, and the
Anthropic dialect never carries it. The digest leg only; the level a turn runs
at is untouched.

### Qwen3.8-Flash-Next no longer needs a fork (#140)

PR #27742 merged into mainline llama.cpp on 2026-08-29. Ten boots on the merge
commit `6c84c7d5d`, one 31,979-token turn each on a cold cache: **10/10 clean,
prefill 959.81 tok/s mean, decode 28.60, VRAM 27,988 MiB** — inside the spreads
of the lab build on both figures.

**The commit is pinned, not the tag.** `b10687`, a day younger, aborts during
warmup with `ggml_cuda_compute_forward: MUL_MAT failed`. The only `qwen4exp`
change between them is #27880 "reduce number of graph splits", which hoists the
PLE embedding into one shared split and then multiplies it by per-layer weights
— and under `-ncmoe` those weights are on the CPU. The pin moves when that is
fixed upstream, not when a newer tag appears.

### Also

- `run_command` gives its child no keyboard (stdin `DEVNULL`): a PowerShell
  confirmation on the console once stalled a turn for 8m55s with nothing on
  screen to say why
- README counted 15 tools; there are 21 since the git group

## 1.6.1 — 2026-08-29

### No child process may wait for a keystroke

Found live within the hour of 1.6.0. The model ran `Invoke-WebRequest` without
`-UseBasicParsing`; PowerShell 5.1 raises a confirmation for that and raises it **on
the console**, not through the pipes `run_command` reads. The child had inherited the
window's terminal as stdin and waited for a keypress nobody knew about — the turn
stood still for 8m55s with nothing on screen to say why, and only the cost line's
`waited` field showed it afterwards.

stdin is `DEVNULL` now. Any such prompt reads EOF, the call ends at once, and what
the program says comes back as an ordinary tool result the model can read and work
around. In this program questions go through the approval card, nowhere else.

## 1.6.0 — 2026-08-29

Git is a tool group of its own, the account connects over the device flow, and the
window grew a git panel beside the code panel. Suites 427 / 731 / 528, checkers
8/8 and 75/75.

### Git as six tools, not as shell lines (#156)

`git_status` `git_diff` `git_log` `git_commit` `git_push` `github_connect`. All five
git calls run a **fixed argument list without a shell** — a branch or a path that
looks like an option stays data, and a commit message beginning with `--` cannot be
read as one. They operate on the repository the WORKING DIRECTORY is bound to, never
on the process's cwd.

`git_commit` stages exactly the paths it is given: no `-a`, no `.`. `git_push` uses
git's own credentials on this machine — a token on a git command line would be
readable in every process list for the length of the call.

**`git_commit` and `git_push` ask at EVERY release level, `auto` included**, and no
`always` can silence them: both are outside the level table (`ALWAYS_ASKS`) and have
no approval scope, so neither a switched level nor a remembered answer releases them.
Two independent locks, neither of which is a setting.

### GitHub over the device flow

`github_connect` returns the eight-character code immediately and polls in the
background — the browser leg takes minutes, and a tool call may not hold the turn for
that. The token is stored owner-only beside the provider keys and never handed to a
surface; what a surface shows is the login. The client id is not a secret (the device
flow has none), so it may be shipped or typed on the key page. One app covers every
repository the account can reach.

### The git panel (#156)

Under the code panel, same shape and same folds, toggled by the octocat in the title
bar — the only way to close it, as it is for the code panel. Both open share the
height; one closed leaves the other the whole column. Changes with per-file `+`/`−`,
the branch and its upstream, a Commit group that lists the files it would take by
name, and a History that marks `◉` commit, `⑃` merge, `⇧` push, `⑂` fork, `◈` connect.
Commits and merges come from `git log`, pushes and connects from Crow's own record —
nothing is invented.

The account button in the panel head **only connects**. It was a toggle for one
evening, and that evening it read a stale label and disconnected an account somebody
was trying to connect; `Disconnect` now lives on the key page, on a button whose text
is the action.

### `copy` sits on the block, not on the panel

The panel head's `copy` took the visible text of everything in it — calls and source
in one blob — so whoever wanted one code block got all of them. Every block carries
its own now, and `Program code` became a fold with a count like the calls above it.
`clear all` stays alone in the head: it means everything, which is its job.

## 1.5.2 — 2026-08-29

5 commits. The rollover note carries the model's own digest of the leg, a pasted
screenshot becomes a vision chip, and two phantom classes died: `\x` escapes read
as UNC paths, and suite sandboxes that leaked state across runs.

### The note digests the leg before the cut (#154)

One question to the same spot BEFORE `conversation.reset()`, while the full prefix
is still warm in the server's cache -- state, decisions taken, open steps ride the
note as marked, unverified model text next to the user's verbatim lines (#147).
`tools` stay in the body: without them the template renders differently and the
warm prefix breaks. A failed or slow digest is "" and the roll proceeds unchanged.
`rollover_digest_tokens` (settings.json) / `--rollover-digest-tokens`, default
400, `0` switches it off.

### A pasted screenshot is a chip

Ctrl+V wrote the image to `pastes\` and attached the PATH as text -- the route
predates #142. A pasted image now takes the drop route: chip, vision, transcript.

### `\\name` without a share is not a UNC path

A Select-String pattern containing the escape `n\xe4chste` was read as UNC path
`\\xe4chste`, and the approval card asked always-for a phantom. Both path
scanners now require `\\host\share` and a word-start lookbehind -- the same one
that killed the phantom `P:` drive.

### Suite sandboxes leak no state across runs (#155)

Fixed `%TEMP%` names made one run's leftovers the next run's "empty"
configuration (an HTTP 401 in the image case, a `d1` corpse in the delegate
case) -- and `test_crow.py` never had the isolation block at all: it ran on the
REAL installation and wrote suite data into the live subtask registry.
Per-process `mkdtemp` + `atexit` everywhere; acceptance is each suite green
twice back to back with no manual cleanup between runs.

## 1.5.1 — 2026-08-29

2 commits. Bugfix release: the window's rollover, live-tested on a session stuck at
200.2k of 200,192 — it rolled and continued.

### The second rollover fires (#152)

Three defects behind one symptom. The window persisted the core's per-turn `rolled`
guard across turns — after the first rollover every later one was refused; the refusal
was a base-class no-op, so turns just ended wordlessly; and a session already past the
threshold failed its FIRST request at the server (HTTP 400 exceed_context_size) before
the end-of-round check could ever roll. Fixed: the flag is fresh per turn, a refused
roll is a red line with its reason, and the window rolls BEFORE the turn like the
terminal — the archive is a complete conversation, the typed line opens the new context
as carry, staged images stay put.

### A rollover archive is not titled by the note (#153)

An archive carries no title of its own and was titled by its first user line — which IS
the previous rollover note, so the rail read as the same session twice. The title now
skips note lines and takes the next real user line; on disk nothing was ever duplicated
(archive and continuation verified distinct, pointer intact).

## 1.5.0 — 2026-08-29

2 commits. The harness wave: approvals that persist and cover every path of a command,
opt-in budgets, delegate favourites with health-aware fallback, a rollover that carries
the user's own words, one nudge for a silent close, one retry for a broken stream — and
a window that reboots its own dead server. Qwen3.8-27B stays the default operating point.

### Approvals ask once and stick (#144)

`run_command` on paths outside the working directory asks at every release level — one
card, every outside path named, and an approval covers ALL outside paths of the command.
`always` lands in `%LOCALAPPDATA%\Crow\approvals.json` and survives the restart. An
obfuscated path does not ask: the gate is a question, not a sandbox.

### Budgets, retry cap, incident memory (#145)

`turn_token_budget` and `subtask_max_tokens` — settings.json keys and terminal flags,
both opt-in; a spent budget forces the answer with the round-budget protocol. The fourth
identical failing tool call is refused before it runs. Refusals and caps reach the memory
review as incidents.

### Favourites and fallback (#146, #148)

Three delegate favourites over the whole catalogue, tried in order before the free
default — a paid favourite is the user's explicit pick on their own key, and what nobody
chose never falls onto a bill. A spot that failed this session is skipped, the card says
`fell back from`, and the dead upstream's 404 class is retryable.

### Rollover carries the user's words (#147)

The note that crosses the cut now carries the user's own lines verbatim, and the context
readout resets the moment the roll happens instead of rounds later at turn end.

### /verify (#149)

The conversation's writes go to the checker spot with review instructions; `collect`
returns the verdict. User-triggered on purpose — a maker that may skip its own checker
will.

### One nudge, one retry (#150, #151)

A reasoning-only close gets ONE nudge for visible text; a second silence becomes an
incident. A mid-turn stream reset (the 10054 class) is retried ONCE on the intact
prefix — never for hard errors, never twice.

### Self-healing

A server the window itself booted is remembered in `booted.json`, across window
restarts; dies it mid-session, the turn reboots it — `booting it again (n/3)`, three per
turn, then honestly red with the boot's own exit code. HTTP 503 `Loading model` is
waited out once per turn. Every boot writes `runs\llama-server-<port>.{out,err}.log`.

### Window

OpenRouter on its own settings page, and the page routes no turn — the default is always
the machine; turns leave it only through the Model page. Subtasks persist per chat
(`session\subtasks-registry.json`) and a deleted chat takes them along. The stream pulls
only who IS at the end (80 px). The running card's amber bar sits exactly like the
finished one's.

## 1.4.0 — 2026-08-28

7 commits. Crow delegates: subtasks fan out to remote spots while the local slot keeps
running, from the model's tools and from the user's own `/delegate` — also mid-turn. A
third operating point runs a 125B by hybrid offload, measured to its ceiling. Images ride
the message on both surfaces, and the composer's width has a floor.

### Delegation (#143)

Parallelism is bought at a provider, not from the card. Three tools — `delegate`,
`subtasks`, `collect` — and the same pair as slash commands on both surfaces; the local
slot is refused as a target, hard. Cards in the flow, `⑂` children under the root chat,
a subtask is never opened as a chat. Stop cancels the subtasks with the turn.

| | |
|---|---|
| live acceptance | two subtasks delegated and collected beside a running turn, 0 € on the free pool |
| the free pool | shared and empty at US primetime (`upstream_provider_shared_pool`): a spot is pinned only after answering twice in a row AND carrying a real delegation |
| remote accounting | remote endpoints send `usage`, not llama timings — `usage_tokens` counts them |
| the last defect | the page's Stop gate ate slash lines mid-turn: `/delegate` killed the running turn it was meant to run beside. Found in the first live minute, fixed same day — only the delegation pair passes the gate, the stop gesture is unchanged |

### A third operating point: Qwen3.8-Flash-Next by hybrid offload (#140)

73.45 GiB against 32 GiB of card: experts of the first 40 of 48 layers in system RAM.
`-c 200000 -b 4096 -ub 4096 -ncmoe 40 --fit off --load-mode none -ctk q8_0 -ctv q8_0`
on the PR #27742 engine — a server line may now name its own `binary`.

| conditions: 31,979-token cold turns, 10-boot series, driver 616.56 | |
|---|---|
| prefill | **964.8 tok/s** mean (949.99–981.03) |
| decode | **28.61 tok/s** mean (27.01–29.37); window practice at 7–17k depth: 32–33 |
| VRAM / RAM | 28.4 GiB (4.2 free) / ~46.6 of 63.38 GiB |
| boots | 10 of 10 |

`--load-mode none` is the finding: mmap at the RAM ceiling reads the NVMe into every
token — identical lines spread 19–31 tok/s until the experts sit in anonymous memory.
The decode ceiling is measured, not guessed: MTP head absent from the GGUF, ngram nets
−2 %, a 27B drafter halves decode at 0.775 acceptance, threads optimal at auto-24. The
newer PR head is 3–6 % faster and fails warmup 11 of 19 — build 439 ships the line.
Full tables: [measurements](docs/measurements/README.md), raw rows on #140.

### Vision, second half (#142)

The vision switch is one manifest field (`mmproj`), its copies enforced by the checker,
and an image rides the message the same way on both surfaces: chips above the input,
transcript and restart survive, a server without `--mmproj` refuses with a sentence
before anything is sent.

### The composer has a floor

`#main` never falls under 560 px, the window under 1130×520 — no combination of rail,
panel and window can push the mask below the reference. A dragged panel width is still
a decision and is never overridden.

## 1.3.0 — 2026-08-26

4 commits. A dropped MCP connection is retried instead of reported as a dead server,
the code panel stops showing JSON envelopes, and a line typed while the memory
review runs is queued rather than dropped.

### A dropped connection is not a dead server

Measured 2026-08-24, five `initialize` posts three seconds apart per server:
`huggingface.co` answered **3 of 5** while six other servers answered 5 of 5. Two
runs with different `User-Agent` values produced the same pattern, so the drop
belongs to the far end. Live afterwards: **5 of 5**, three rounds needing a repeat;
context7 5 of 5 with no repeat at all.

| | |
|---|---|
| Retried | `initialize`, `tools/list`, `notifications/*` — up to 3 attempts, 0.25 s apart. One attempt reaches 60 %, two 84 %, three 94 % |
| Sent once | **`tools/call`**, and anything not named above. Nothing on the wire says whether a call it got no answer to ran, MCP has no idempotency key, and a repeat of a write is a second write |
| Never retried | connection refused, and any timeout. Nothing listens on a refused port; a server that spent the whole budget once will spend it again |
| Documented in | [MCP over HTTP](docs/user-guide/mcp-http.md) |

The ticket proposed retrying a `tools/call` that failed *before* anything was sent.
That line is not buildable: `urllib` wraps everything up to **and including** the
send in `URLError`, so connect and send are indistinguishable from outside.

### The code panel

It showed the JSON envelope of every call — `{"query":"C++ reference"}` beside
`{"command":"where node npx"}` — and the source a turn wrote was one of them,
told apart by nothing.

| | |
|---|---|
| Tool calls | one fold for the group and one **per call**. Open a call for its `arguments` and, under them, its `result` — 4,000 characters, the remainder counted |
| A failed call | marked on its head, not only inside it |
| Program code | its own section, from `write_file` and `edit_file` only. The head is the **path**, the body the content |
| `read_file` | deliberately absent. Crow reads far more than it changes |
| `clear all` | empties both halves and survives a restart |
| Start width | half the space beside the rail. A dragged width is a decision and is never overridden |

`tool_result(name, result)` is new on the seam, beside `tool_finished` rather than
widening it. The whole result travels; how much fits on a screen is the screen's
decision — the window shows 4,000 characters, the terminal shows nothing and says
so in a docstring.

### A line typed during the memory review

| | |
|---|---|
| Was | drawn into the transcript by the page, then dropped by `send`. The same question stood there twice and only the second ran |
| Cause | `idle` is pushed **before** the review since 1.0.0, and the review runs on the same worker. The window said free while `send` said busy |
| Now | queued. The composer says `queued -- the memory review is finishing` and the turn starts by itself |

### The composer

The send arrow stood beside the frame rather than in it. A flex child carries
`min-width:auto` and does not shrink below its content, and every child of that
row also carried `white-space:nowrap` — so none gave way and the overflow fell on
the last element. What gives way now is ordered: the hint, then the model chip,
then the context figure. The buttons never do.

### Suite

**1501**, up from 1463: `test_crow` 418, `test_crow_core` 618, `test_crow_gui` 465.
`check_shared_core` 64/64, `check_operating_point` 6/6.

## 1.2.1 — 2026-08-24

5 commits. A tool filter that does not lock out tomorrow's tools, a level menu that
stopped growing with the table, two CSS comments that had voided the rules behind
them, and the documentation split out of a 966-line README.

### MCP tools

| | |
|---|---|
| Adding a server | writes **no** filter at all. It used to write every offered tool name into `tools.include`, which was a photograph of that minute — the 74th tool a server grew afterwards matched nothing and was unreachable, with no error anywhere |
| Clearing a tick | writes `tools.exclude`. It names the refusal and leaves the rest of the server open, including what it has not offered yet |
| An `include` listing every offered name | is dropped on the next refresh. A positive list that admits everything is not a filter. A hand-written glob is never touched |
| Unchanged | `include` still wins over `exclude`, both still take globs, and `classes` stays empty — a tool that arrives on its own arrives in the strictest class and is asked for at `manual` and `allowedit` |

### The level menu

`mode_description()` now lives in the core and both surfaces read it. It names the
built-in tools and **counts** the rest:

```
asks before edit_file, run_command, write_file and 93 MCP tools
```

It was built by joining every name that asks — written separately in the terminal
and in the window, both the same wrong way. That reads well for twelve built-ins
and became ninety lines with one MCP server attached. Cloudflare's API server
reports around 3,300 tools, so there is no size at which listing starts working
again.

### A server that stopped answering

| | |
|---|---|
| The window | now says `start llama-server first, then retry.` under the error. The terminal had said it since #114; the window never did, so `[WinError 10061]` read as a permission refusal |
| Where it lives | `failure_line()` in the core, by exception **type**. A failed boot and an HTTP 400 do not get it |
| Default endpoint | `:8082`, Qwen's port. It was `:8081` — 0731's, and the only one until a second model arrived. A client started with nothing running named a port that had not been served in weeks |

### The memory row

Two comments in the `#122` block were closed one `*/` too early, so the prose
behind them was parsed as a selector — and CSS discards the rule that follows one
it cannot read. `.memnote` went, then `.memicon`. The row arrived grey, flat and
without its mark. A checker now walks the stylesheet's comments and fails on a
`*/` outside one.

### Documentation

`README.md` went from 966 lines to 247 — requirements, install, start, operating
point, screenshots. Everything else moved to [`docs/`](docs/): 19 pages under
`reference/`, `user-guide/`, `measurements/` and `developer-guide/`, the last two
of which describe the four modules and the five checkers for the first time.

`check_operating_point` reads `README.md` as raw text, so the nine flags under
*Operating point* stayed where they are — noted in `docs/developer-guide/testing.md`
so the next move does not trip over it.

### Suite

1408 cases, up from 1390. `check_shared_core` 64 of 64 — three new entries, because
the level sentence had been written twice and the manifest could not see it.

## 1.2.0 — 2026-08-23

3 commits. A rail you can drag, air around the chat, the voice drawn as a line, and a
suite that no longer writes into a real installation.

### The window

| | |
|---|---|
| Rail | dragged by a five-pixel handle, clamped to 180..520 in the page AND in Python, kept in `settings.json` |
| Chat | ten pixels of air on each side. The stable scrollbar gutter was there, but a gutter is not a distance |
| Composer | 900 again, the edge of its own text column. It was 675 for one evening |
| Voice | while dictating, a line of pill bars mirrored around the middle, inside the input row |
| Placeholder | gone while recording, or the resting dots read as marks in the sentence |

### How the level is read

| | |
|---|---|
| Source | the block PortAudio hands over anyway. No second stream, nothing new that can refuse to open |
| Peak, not RMS | an average over 20 ms flattens exactly the syllables a meter is there to show |
| Scale | a running peak that decays three percent per frame, with a noise floor, reset at every start |
| Why | the first scale was fixed and wrong by an order of magnitude: float32 speech sits at 0.05 to 0.3, and `level*22` is four pixels. The band stayed flat while the transcription came back clean |

### The suite stopped standing on the live installation

Two cases wrote into a running client: an invented API key into
`mcp_tokens.json`, a `rail_width` into `settings.json`. The head of both test
files already redirected four paths, which is what made it look solved.

| | |
|---|---|
| The fix | a case that walks every path constant of both modules and refuses any that resolves into the real `%LOCALAPPDATA%\Crow` |
| What it found | eight more beyond the two: the search index, roots, the session directory and file, skills, USER.md, the paste directory |
| Now | all ten point at a directory whose parent does not exist, the state the readers treat as "nothing configured" |

| suite | |
|---|---|
| 1360 | `test_crow` 418, `test_crow_core` 566, `test_crow_gui` 376 |
| checkers | `check_shared_core` 60/60, `check_operating_point` 6/6, `install.ps1 -Selftest` 85 |

## 1.1.0 — 2026-08-23

6 commits. Formatted answers, an update button, and a routing filter that is asked per model.

### The core cuts the answer, the window draws it

| | |
|---|---|
| In | headings, bullet and numbered lists, tables, paragraphs; bold, italic, inline code, links |
| Out | nested lists, block quotes, reference links. They stay the characters they are, as all of it did |
| Where | `crow_core.markdown_blocks`. The page builds elements out of `textContent` and no markup comes off the wire |
| When | at the end of a run of prose, at a fence and at the end of the turn. Half of `**bold` is not bold yet |
| Line breaks | a single newline inside a paragraph is still a line break, which is what this client always did |
| Links | `http` and `https` only, checked in the core and again in the window, and opened outside it |
| Emphasis | CommonMark 0.31.2's flanking rule, so `2 * 3 * 4` stays arithmetic |

### Update from the About pane

| | |
|---|---|
| Check | the latest release, asked when the pane opens |
| Run | install.ps1 fetched to a file, started as `-File ... -NoPause` |
| Not `iex` | it cannot take parameters, and without `-NoPause` the installer waits for ENTER behind a window that has no console |
| Progress | the installer's own lines |
| Failure | exit code and last line, and no promise of a restart |
| Restart | required. Python keeps the modules it started with |
| Current version | the button is offered anyway; install.ps1 answers "nothing to do" and exits before it downloads |

### Local fields stay local

| measured 2026-08-23, openrouter.ai, no key needed | |
|---|---|
| models | 422 |
| accept `tools` | 337 |
| accept `tools`, `temperature`, `top_p`, `max_tokens` | 250 |
| accept those and `min_p` | 72 |

| | |
|---|---|
| Dropped from a remote body | `min_p`, `timings_per_token`, `chat_template_kwargs` |
| Kept at home | all three. `min_p` 0.01 is measured against llama-server, which is the only endpoint that acts on it |
| `provider.require_parameters` | sent where the catalogue says the model takes everything the body holds, nowhere else |
| Live | `nvidia/nemotron-3.5-lightning:free`, a turn with `web_search`, 2 rounds, 1 tool call, 2.5 s of tool time |

### Also

| | |
|---|---|
| Taskbar icon | the raven filled 66 % of the width of its canvas at every size, now 90 to 93 % |
| `REMOTE_ENDPOINT_NOTE` | said "nothing is kept warm between turns", which `session_id` had made untrue |
| README | 27 em dashes replaced by punctuation, and the routing section rewritten |

| suite | |
|---|---|
| 1344 | `test_crow` 418, `test_crow_core` 566, `test_crow_gui` 360 |
| checkers | `check_shared_core` 60/60, `check_operating_point` 6/6, `install.ps1 -Selftest` 85 |

## 1.0.1 — 2026-08-23

15 commits. MCP servers, remote providers, and a gate in front of the only writer that runs unasked.

### MCP servers (#128, closed with ten children)

| | |
|---|---|
| Transports | stdio, and Streamable HTTP per spec 2025-06-18 |
| Auth | OAuth 2.1 — discovery, DCR, PKCE, `resource`, refresh |
| Tool schema | fetched **once** when the server is added, then read from disk. `TOOLS` cannot move because a server is slow or down |
| Per tool | a switch and a class: reading / writing / executing |
| Class source | pre-filled from `annotations`, decided by the user, stored in Crow's config. The spec calls annotations untrusted |
| Naming | `mcp_<server>_<tool>` |
| Config | `%LOCALAPPDATA%\Crow\mcp.json`; `tools.include` / `tools.exclude`, `enabled`, `timeout`, `connect_timeout` |
| Not built | `sampling`, live `notifications/tools/list_changed`, `elicitation`, standing `GET` stream, `Last-Event-ID` resume, curated catalogue |

Driven against `mcp.context7.com`, `mcp.deepwiki.com`, `docs.mcp.cloudflare.com` and
`mcp.higgsfield.ai` (73 tools, 143,739 chars, full Clerk OAuth leg).

| measured 2026-08-22 | |
|---|---|
| `Python-urllib/3.13` at `docs.mcp.cloudflare.com` | `HTTP 403`, error 1010, `browser_signature` |
| same client, `User-Agent: Crow/<version>` | `200` |
| `bearer <token>` at `mcp.higgsfield.ai` | `401` |
| `Bearer <token>`, same token | `200` |

| measured 2026-08-23, local Qwen3.8-27B, one `context7` call | |
|---|---|
| Prompt cache | `cached 3,687/3,968` — 92.9 % held with a foreign schema in `TOOLS` |
| Wall time | 7.5 s: model 5.1 s, tools 2.4 s |

### Remote models

| provider | endpoint | credential |
|---|---|---|
| This machine | `--base-url` | none |
| OpenRouter | `https://openrouter.ai/api/v1` | `sk-or-...` |
| Anthropic | `https://api.anthropic.com/v1` | `sk-ant-...` or a sign-in |
| OpenAI | `https://api.openai.com/v1` | `sk-...` or a sign-in |

| | |
|---|---|
| Second transport | `anthropic_messages` — system hoisted, `input_schema`, `tool_use` blocks, results batched per turn, stream translated back into the chunk shape the reply loop already reads. One loop, two dialects |
| One resolution point | `provider_endpoint()`. `stream_reply` **and** the background review read it |
| Subscriptions | `claude setup-token`, `CLAUDE_CODE_OAUTH_TOKEN`, and a borrowed `~/.claude/.credentials.json` read at request time, never written, never refreshed |
| Context bar | `/props` measured locally, `context_length` declared remotely, no bar when nobody says |
| Sticky routing | `session_id`, sha256 of the chat path, on both senders. OpenRouter only |
| Not built | price display, default context window, `codex_responses`, foreign `client_id`, `provider.require_parameters` |

| measured 2026-08-23 | |
|---|---|
| `openrouter.ai/api/v1/models` | 421 models, 18 with `:free` |
| `api.anthropic.com/v1/models`, setup token | `200`, 10 models |
| `api.anthropic.com/v1/messages`, borrowed session | `429`, no limit named, account window at 7 % |
| `api.openai.com/v1/models`, Codex token | `403` |
| `chat/completions` without `max_tokens` | `HTTP 402 — you requested up to 65536 tokens, but can only afford 313` |
| `chat/completions` with `provider.require_parameters` | `HTTP 404 — No endpoints found that can handle the requested parameters` |

`require_parameters` was reverted the same day. The flag turns "ignore an unknown parameter" into
"exclude the provider", and Crow's body carries `timings_per_token` and `chat_template_kwargs`,
which no remote upstream supports.

### Memory gate

| | |
|---|---|
| Default | **on**. The background review asks before it writes |
| Off | `--no-memory-approval` |
| Reason | the review is the only writer that runs with nobody at the keyboard |

### Fixes

| | |
|---|---|
| `run_command` | non-JSON on stdout is kept and reported separately from stderr — `npx ctx7 setup` is an installer, not a server, and was being dropped |
| Tool calls | leave the reading column; a dismissed row stays dismissed |
| Foreign strings | tool descriptions carrying tabs and newlines are condensed before they are cut to a fixed column |
| Preflight | reports `node`, refuses nobody over it |

### Numbers

| | |
|---|---|
| Suite | 1,298 — `test_crow` 418, `test_crow_core` 533, `test_crow_gui` 347 |
| `check_shared_core` | 60 / 60 |
| `check_operating_point` | 6 / 6 |
| `install.ps1 -Selftest` | 85 |

## 1.0.0 — 2026-08-21

A one rather than a minor. The client gained a memory, its own procedures, a search across every
past conversation, and a window rebuilt from the status bar up — and it stopped speaking two
languages. Nothing here is a refinement of 0.5.1; a user opening this build meets a different
program.

**Crow remembers, and the head does not move while a chat lives (#119).** Two stores, plain text,
editable by hand: `<root>\.crow\MEMORY.md` at 4,000 characters beside `root.json`, and
`%LOCALAPPDATA%\Crow\USER.md` at 1,500 for the profile. Both are anchored to `MAX_TOOL_BYTES` at
four characters per token — memory has to stay cheaper than letting the model read the file, and
when it stops being cheaper the answer is not a bigger cap.

The rendered block is **pinned into the chat's own JSON** under `memory` and replayed word for word
on open, whatever the files say by then. llama-server reuses a prompt by common token prefix and
Crow holds its KV cache on disk; a head that moves mid-session throws that cache away. The price is
named rather than hidden: a chat left open for weeks learns nothing new, and new memory takes effect
from the next chat.

**An empty store costs byte 0 nothing.** No frame, no 0% line, nothing in the prompt until an entry
exists. A chat with no working directory bound says so instead of showing an empty frame — an empty
frame reads as "nothing learned", which is the more dangerous of the two.

Writes never truncate. Over the cap, the write **fails** and the error carries both numbers and the
current entries; from 80% the head tells the model to consolidate. A store that silently drops
something on overflow eventually drops the wrong thing and nobody learns when.

**The review runs three times per window, behind the turn (#119).** `MEMORY_REVIEW_AT` is
`(0.20, 0.50, 0.75)` of the context — shares, not turn counts, because one turn here can cost 20k
tokens; measured live, fourteen rounds stood at 25.2k of 200k. Each mark fires once and travels with
the chat. It sits **behind the visible end of the turn**, never inside it: it ran inside `run_turn`
for one afternoon and was caught live — the answer stood complete, the cost line never came, and the
composer still said `Stop`. `--no-review` switches it off entirely.

Every saved entry is announced the moment it is written, and that line **cannot be switched off**.
Without an approval gate it is the only thing a person sees of a system writing into its own prompt.

**Crow keeps its own procedures.** Skills live globally at
`%LOCALAPPDATA%\Crow\skills\<name>\SKILL.md`, plain text with front matter. Memory is what is
**true**; a skill is what is **to do** — and the two invert: memory puts its whole content in the
prompt and has no `read` action, a skill puts only name and description there and has one. The cap
sits on the **list**, not the entry: the failure case is twenty valid skills, not one long one, and
the list says how many did not fit rather than truncating in silence. `enabled` lives in the file,
so the toggle in the settings sheet and editing by hand are the same act. One skill ships:
`skill-creator`, seeded once if the directory is missing.

**Every past conversation is searchable.** `session_search` runs an FTS5 index at
`%LOCALAPPDATA%\Crow\index.db` over the live session and the archive. The index is **derived and
disposable** — delete it and the next search rebuilds it with the same hits; truth stays in the chat
JSON. Every query word is quoted as a phrase, so `--slot-save-path` is a search and not a syntax
error. Where FTS5 is missing the tool stays **declared** and says it cannot work: dropping it from
the schema would make `TOOLS`, and therefore every stored cache, depend on how someone's Python was
compiled.

**The window was rebuilt.** The status bar is gone and the chat lies on the panel; the rules between
regions went with it. A settings sheet with six tabs — Appearance, Skills, Server, MCPs, Other
providers, About. Three themes. A rounded top-left corner, a taskbar icon, and a wireframe bird over
an empty chat. The rail groups chats by working directory, so a project is a root folder rather than
a list someone maintains. A new chat is **rootless** and gains its memory the moment it is moved into
a project — and the cost of that prefill is announced before it is paid.

**The window speaks one language, and it is English.** Fourteen German strings were still in it.
There is no locale switch and no translation layer: `locale`, `gettext` and `getdefaultlocale`
appear zero times in all three modules. A language nobody can set is the only language, and half a
translation is worse than either whole one.

**The thinking level belongs to the chat (#117).** The menu draws renderings rather than names, is
capped, carries its contrast with the level, and no longer names a step it does not offer. The
thinking share reported is the turn's, not the last round's.

**Bringing a server up is its own job.** A client must not guess a port. Starting the server is a
separate tool with a separate responsibility, and the client finds what is already running.

**The README is Qwen's.** Rewritten against the shipped operating point with no DeepSeek in it; the
previous one is archived whole under `docs/README-v0.5.1-qwen.md` with its image paths repaired —
an archive whose pictures resolve to nothing is not an archive.

**Measured, and not measured.** The operating point is unchanged from 0.5.1 and was not
re-measured: `Qwen3.8-27B-UD-Q4_K_XL.gguf` at `-c 200000` on one slot. `TOOLS` grew from 9 tools and
4,273 characters to 12 and 6,209, so **every session on disk resumes cold exactly once** after this
update — unavoidable, and stated here rather than sprung on the first turn. Suites at release,
on Python 3.13.3: `cli/test_crow.py` 415/415, `cli/test_crow_core.py` 248/248,
`cli/test_crow_gui.py` 262/262, `check_shared_core` 60/60, `check_operating_point` 6/6,
`install.ps1 -Selftest` 80/80. What the background
review costs on a single slot is **unmeasured** and closed that way (#122): how long it holds the
slot, whether the next user turn queues behind it, and whether the prefix hit on the next turn is the
full history are all without a number. The reasoning came from `get_common_prefix` in
`tools/server/server-context.cpp`, which is a reading of the source and not a run.

## 0.5.1 — 2026-08-15

Written down after the fact: this release was cut and tagged without an entry here, and a changelog
that skips a shipped version is worse than one that admits the gap late.

**The stamp writes what it knows and never erases out of silence.** `_stamp` carried an
`else: data.pop("crow_title", None)`: a stamp arriving without a name deleted a title that was
already there. A write path that removes on absence turns every caller that does not know a field
into a caller that destroys it.

**A suite that answers differently in a console is not a gate (#102).** The three suites returned
662 of 671 in an interactive PowerShell console and 671 of 671 through a pipe, minutes apart, with
no line of code between the runs. `crow_core._TTY` is decided once at import from
`sys.stdout.isatty()`, and nine cases were comparing bare strings against escape sequences. The
colour gate itself was right and is unchanged — a redirected transcript has to stay greppable. What
was wrong is that the cases **inherited** that decision from whoever ran them instead of pinning it.

Pinning alone would have made "switch the colour off everywhere" pass and ship a grey client
invisibly, so the opposite direction became a case of its own: a terminal must **get** the
sequences, a pipe must get none. With `_c()` forced to return `""`, that one case goes red and the
other 671 stay green — which is the measurement worth keeping.

Suites on Python 3.13.3, run both ways with `isatty` forced: 672 of 672 as a console, 672 of 672
through a pipe. `check_shared_core` 51/51, `check_gui_prereqs` 3/3, `check_operating_point` 4/4.
No live run, and none was due: `cli/crow_core.py` and `cli/crow.py` were byte-identical to their
previous state.

## 0.5.0 — 2026-08-15

A minor rather than a patch, because the client refuses less and remembers more, and both are
things a user notices in the first minute.

**The working area stopped arguing with you (#98).** Until now a path outside the chosen root was
refused no matter who chose it — including a path you had just typed into the prompt. The ticket
that opened on this recorded the model reaching the path through the shell as a *bypass*; it was
obedience against a rule that could not tell an instruction from an invention. `write_file` and
`edit_file` now refuse only what **Crow itself** picked. A location you name — the file, or a
directory above it, anywhere in the conversation — is written, at every release level.

A location counts as named when it carries a separator: `C:\…`, `D:/…`, `\\share\…`. "put it on the
desktop" names no path, and deriving a directory from a noun is how a release rule starts releasing
places nobody named. The refusal says what lifts it.

`run_command` is still unbounded, as decided on #92. What is left of that gap is narrow — a path you
never named, reached through the shell — and a shell call that runs in a turn where the boundary
already refused a write is now marked on screen in `auto`'s colour, naming the refused path. Since
only unnamed paths are refused, the marker fires only when Crow went somewhere on its own.

**The window remembers where you were working (#92).** The folder had to be picked again after every
single start: `adopt_root` carried fifteen lines of comment describing a restore, and the line under
them bound nothing. `roots.json` gained `active` beside `recent` — `recent` is the picker's menu and
is written by both clients, so it cannot decide where the window opens. Choosing **no folder** is
itself remembered. If the folder is gone at start, Crow says so and runs without one.

The terminal is unchanged: `--root`, else where you stand. The two clients divide on expectation —
a terminal user means the directory they just typed, a window user means the project they left open,
and a window's cwd comes from a shortcut and means nothing.

**Each chat carries its own working directory (#101).** Switching chats moves the boundary with
them, so two chats can work in two projects. A chat that never chose starts from the template. The
release level stays with the **folder**: two chats in one folder share it, or the same directory
would carry different rights depending on which conversation was open.

**A chat named before its first turn keeps its name (#100).** `save_session` refuses to write an
empty conversation — deliberately, that refusal is what stops a `/reset` chat returning on the next
start — so a name given before typing had nowhere to live and died with the window. A named empty
chat is a slot you reserved: it survives closing, survives switching away, and opens again. An
unnamed empty chat is a stray click and still leaves nothing behind.

**Measured, and not measured.** Every change above was run live in the window at the shipped
operating point before it was accepted. Suites at release: `cli/test_crow.py` 398/398,
`cli/test_crow_core.py` 152/152, `cli/test_crow_gui.py` 120/120, `check_shared_core` 51/51,
`check_gui_prereqs` 3/3, `check_operating_point` 4/4 — on Python 3.13.3, the interpreter carrying
pywebview. Throughput and quality are untouched by this release and were not re-measured; the
operating point is the one 0.4.1 shipped.

## 0.4.1 — 2026-08-14

Shipped because the 0.4.0 package predates the fix below: the tag sits on `1a50f6d`, the fix
landed as `8adee6a`. Whoever installed 0.4.0 got a reopened chat without its tool rows.

**This package also carries a change to `llama.dll` that is not in the Crow repository at all.**
The host-RAM tier's eviction policy went from FIFO to CLOCK (second chance) in the patched
llama.cpp tree the package is built from. Measured the same evening, one paired arm, same prompt:
L2 hit rate **18.23 % → 20.97 %**, load stall per remap 0.905 → 0.851 ms, decode 17.57 → 18.26
tok/s, lock wait unchanged at 0.24 us per operation.

**That is one pair, and the operating point is a median of three.** The throughput delta sits inside
the 1.09x spread the manifest records for repeating one configuration, so it proves nothing on its
own; the hit rate is the figure that moved. It ships because it costs one byte per entry and no lock
time, and because holding it back would mean rebuilding the DLL to ship less than what was tested.
The reasoning and the raw numbers are in the vault note on CLOCK beating FIFO at the L2 tier by 2.7 points at a cost of one byte.

**A reopened chat kept its thoughts and lost every tool row (#99).** `_replay` read `content` and
`reasoning_content` and never `tool_calls`, so an assistant turn that only called a tool was skipped
whole — a restored chat showed two thoughts with nothing between them and an answer referring to a
file it never visibly wrote. The rows now draw through `Turn.tool_started`, the same renderer the
live path uses.

**`format_tool_args` moved into the core.** `cli/crow_gui.py` reached for
`crow_core.format_tool_args` behind a `hasattr` guard that had been False since the split, so the
window always took the raw-JSON fallback while the terminal showed values. An expression written to
make two surfaces agree is what kept them apart; `check_shared_core` could not see it because the
name was not declared. 47 of 47 now.

## 0.4.0 — 2026-08-14

**Web research: `web_search` and `fetch_url`, and nothing to configure (#96).** The model searches,
reads what it found, and continues the task. Six official keyless APIs are queried in parallel —
PyPI, crates.io, HuggingFace, Stack Overflow, GitHub, Wikipedia, plus DuckDuckGo's *documented*
instant-answer endpoint. No key, no account, no service. `CROW_TAVILY_KEY` or `CROW_SEARXNG_URL`
switch to a general index for whoever wants one.

**The obvious implementation does not work, and fails silently.** Measured 2026-08-14:
`duckduckgo.com/html/?q=` — the endpoint every model writes for this, Crow's own local model
included — answers **HTTP 202 with zero `result__a` matches** to both `Mozilla/5.0` and
`Crow/0.3.3`. 202 is a success status, `urlopen` does not raise, so a tool built on it reports
`no results` forever with nothing in any log. `lite.duckduckgo.com` still answers **200 with 10
results** to a browser user-agent and **202 to Crow's own**, one URL and one second apart: the only
working scrape requires misrepresenting the client. Six public SearXNG instances were probed the
same day (searx.be, search.inetol.net, priv.au, searxng.site, search.bus-hit.me, baresearch.org);
none served `format=json`.

**Three defects the live run found and the unit tests could not.** Three results came to **16,056
bytes** because one repository description was 15 KB — `_clip` then cut the tail, so the model paid
full prefill for one project's marketing and never saw results two and three; every snippet is now
capped at 240 bytes. Concatenating the sources put GitHub first unconditionally, so "requests
library current version" answered with a stranger's library-management project while PyPI's exact
`requests 2.34.2` sat further down; the merge is now round-robin in authority order. And the package
lookup fired on any identifier-looking word, so "llama.cpp moe stream flag" led with `pypi Moe
2.5.0`, a music library manager — a coincidental name match in the top slot is worse than noise
because it looks authoritative.

**HuggingFace carries the weight, not just the name.** `Qwen/Qwen3.5-27B` reports 2,734,049
downloads against 1,028 likes; `Qwen/Qwen3.8-27B` reports **2 downloads against 8,457 likes**, which
is the signature of a release published hours earlier. The same string from an official org path and
from a 0-download re-upload is not the same evidence, so the counts are printed. Its search takes the
model name and not the sentence: "Qwen3.5-27B model" returned nothing until the gate words were
stripped from the query they let through.

**Cost, measured through `/apply-template` and `/tokenize` on 2026-08-14.** The same five-token
message that sent 953 tokens with seven tools now sends **1,269**, of which **1,222 (96.3 %)** are
the nine declarations. The two web tools cost **313 tokens of prefix in every request**.

`network` is a fourth class in `TOOL_CLASS` and asks at **no** release level, `manual` included: the
search happens because a task was given, and giving the task is the release. `fetch_url` takes http
and https only — `file:` and `data:` would make it a disk read around #92's boundary rather than
through it. Extraction runs before the 16 KB clip, because clipping first keeps the markup and drops
the answer. 152 in `cli/test_crow_core.py`, 13 breakages each count-checked to a single site.

**The window's live tok/s counts the pauses, and that is now written down (#97).** Observed
2026-08-14: **9.5 tok/s** on screen beside a server logging **17.99–19.29 t/s** for the same turn.
The denominator runs from `reply_started`, so it contains the wait for the first token, every tool
call and the prefill of every tool result — and the web tools widened the gap, because a search is
exactly that kind of pause.

It reads like the defect `crow_core.TurnCost` fixed on 2026-08-11 ("printed 1.49 tok/s for a turn the
server had just measured at 14.77 and 16.46"). It was changed to sum only the gaps between deltas,
and changed straight back: **what the user waits through is wall clock.** A decode rate that ignores
the pauses answers a question the server already answers, and the server's own figure is the line
that lands underneath at the end of the turn — two figures, two meanings, both on screen.

The reason it looks like a bug is the reason it now has a guard.
`TheLiveRateIsWallClockOnPurposeTests` fails if the pauses ever stop counting, with the well-meant
repair as its negative control: summing only the inter-delta gaps lands back at the decode rate, and
a case that goes green there means the decision was reverted without anyone deciding to. 98 in
`cli/test_crow_gui.py`.

## 0.3.3 — 2026-08-14

**A working directory the model may not write outside of (#92).** `write_file` and `edit_file` took
any path; at `auto` — the default — nothing stood between the model and the disk. A release level
(#88) asks an attentive user at round 14 of 24; a boundary refuses without asking, which is the half
that protects the turn nobody was watching. The refusal names the root, so a user can see what the
boundary thought it was instead of guessing.

**The root is the nearest ancestor holding `.crow/root.json` — not `.crow/` itself.** That directory
is a by-product: `SPILL_DIR` creates it wherever crow runs. Measured on 2026-08-14,
`C:\Users\robin\.crow` already existed, dated 2026-08-08, from a single session started in the home
directory — treating it as the marker would have made the entire user profile a root and the
boundary decoration. A directory becomes a root when someone picks it, never by accident.

**Writes only, and both halves are recorded decisions.** `read_file` stays unbounded: a read boundary
blinds the model to its own installation, which is a real use, and a read destroys nothing.
`run_command` is not covered either — a `cwd` inside the root says nothing about what the command
does, `cd /d C:\ && del …` being one shell line — so it stands on #88's `executing` class instead. At
`auto` that gap is real, and it is named here rather than left to be discovered.

Three traps, all measured that day on Python 3.13.3: `os.path.ALLOW_MISSING` is in the 3.13
documentation and does not exist in this release; `commonpath` and `relpath` raise `ValueError`
across drive letters instead of answering "no"; and `"C:\root2\x".startswith("C:\root")` is `True`,
so a bare prefix check lets a sibling directory through.

The window has a folder picker with a recently-used list; the terminal has `--root`, which states a
root **and** creates it. The window does not walk up from its cwd — a shortcut decides that
directory, so a stray marker under it would outrank what the user picked.

**What this does not do: the choice does not survive closing the client.** A persistence path through
the session file was built and removed again — it never worked in the running window, and half of it
would read as "the boundary holds" when it does not. Nothing in the window has exercised the refusal
in a live turn either.

Held against thirteen deliberate breakages. The two that matter are complementary: with the boundary
switched off 9 cases go red, with it refusing everything 3 go red — the negative halves. Neither
"always refuse" nor "never refuse" passes both.

**`/reset` now survives closing the client, on both surfaces.** It never had. `save_session` refuses
a conversation with nothing in it — right for the case it guards, a client started and closed without
a word, since an empty file is worse than none — but the guard cannot tell that from *the user just
emptied it on purpose*. So a `/reset` followed by an exit wrote nothing, the file from before the
reset stayed, and the next start restored the conversation that had just been dropped.

Found in the window on 2026-08-14 and confirmed against the live file: `session.json` still
held three messages, timestamped **before** the reset — the last turn's write, not the reset's.

The fix is not a change to the guard, which would delete archives on the same reasoning.
`forget_session()` in the core removes the file, and both `/reset` paths call it. `--no-session`
leaves it alone: a client that does not own that file has no business deleting it.

**And in the window it lets go of the chat it came from.** Removing `session.json` fixed the live
case and left the other half: a conversation opened out of the rail keeps `_current_path`, and
closing archives the open conversation *there* — where the same guard refused it, so the file kept
its old messages and the next start found them again. **Detached, not deleted:** `/reset` drops the
context, it is not *throw my saved chat away*, and the chat stays in the rail with everything in it.
Both halves are cases, and neither "stay bound" nor "delete the file" passes both.

**The window runs every slash command now (#94).** It handled `/tools`; the other six travelled to
the server as ordinary questions and came back as an answer about the word — `/reset`, `/context`,
`/thoughts`, `/mode`, `/exit`, `/quit`.

| typed | does |
|---|---|
| `/reset` | drops the context and the standing approvals. **The chat stays where it is** |
| `/context` | messages, tokens, and the rollover point the bar never names |
| `/mode`, `/mode <name>` | reports the release level, or switches it through `set_mode` |
| `/thoughts` | folds every reasoning block open, or closed again |
| `/exit`, `/quit` | closes the window |
| `/help`, `/tools` | the window's own list, and the tool schema |

**The first attempt answered them with a sentence naming the control that does the same job, and
that was wrong twice over.** *"/reset: that is the new button, top left of the chat rail"* — the
button is on the **right**, because `margin-left:auto` puts it there; and `new` **archives the
conversation into the rail and opens an empty one**, which is not what `/reset` does in the terminal
at all. A user who followed that instruction would file away a chat they meant to keep.

**A pointer is prose about pixels, and prose about pixels cannot be tested.** The case written to
catch a lying pointer only asserted that `id="new"` appears somewhere in the page, so it could never
have caught either error — green, and worthless, in the exact shape its own docstring warned about.
Running the command has neither failure mode: no prose to be wrong about, and no mapping to get
wrong. A case now forbids the words *button*, *top left*, *beside*, *dropdown* and *click* from every
answer the window gives.

**What is shared is the list, not the answer.** `crow_core.SLASH_COMMANDS` holds the names both
surfaces must cover; `crow.py` keeps the prose of `HELP` and is pinned against it. A command added to
one and not the other is a red test rather than a command the window has never heard of.

**A message that merely starts with a slash still reaches the model** — `/usr/bin/env is what?` is a
question, not a command.

Two more found in the window after that, both older than this change: **`/help` and `/tools` arrived
as one run-on paragraph**, because `.note` had no `white-space` and their columns were collapsed —
true of `/tools` since the day it was answered here; and **`/mode <name>` answered twice**, because
`set_mode` pushes its own note and the command returned a second one. An empty answer now means
*handled, and already said*, which is a third thing next to a note and a `None`.

24 cases in `cli/test_crow_gui.py` (74) and one in `cli/test_crow.py` (340). The one that matters
counts the files in the session directory before and after `/reset`: if it writes one, it has become
`new` again.

**Two defects came with it, both older than the change and both found in the window rather than by
the suite.** The Api pushed a `user` echo before its answer — but `go()` already draws that line
before it calls in, so the typed command appeared **twice**. And `go()` painted the composer "Stop"
with a read-timeout hint on the way in, which a turn normally takes back; a command answered in
Python starts no turn, so the window **sat on "Stop" with nothing running behind it**. Both were true
of `/tools` before this change and became true of all seven with it.

**`send` now answers the question the page was guessing at.** Every `pywebview.api.*` call resolves a
promise once the Python side returns — so `send` returns whether a **turn** started, and `go()` locks
synchronously but paints from the answer:

```js
this.user(text); this.running=true;
pywebview.api.send(text).then(started => started ? this.busy() : this.idle(),
                              () => this.idle());
```

One mechanism instead of two: no "Stop" flicker on a slash command, no correcting message pushed
after the fact, and a rejected call unlocks as well. The lock stays synchronous because the round
trip is a real window for a second click; only the **button** waits.

**Every one of the 57 cases passed through both defects.** They drive the Api with no page on the
other side — one half of a seam measuring itself, and every assertion was about what this half
pushed. Four cases pin the seam now, including the two lines of `go()` the Python half depends on, so
the next change to the page's side turns a test red instead of shipping.

**The tool cache was keyed on less than its inputs (#93).** `run_tool_cached` answered a repeated
call from the first one, on the stated grounds that *"re-running would produce the identical
failure"*. True for five of the seven tools and false for two, measured 2026-08-14 in the first real
agent run: a `write_file` refused for want of a read was replayed **after the read that lifted it**,
three times, until the model gave up and reached for `edit_file`; and a `run_command` after an
`edit_file` on the same file replayed the output from before the edit, until the model appended
`2>&1` to change the key rather than the command. 4 of that turn's 12 calls were replays of a state
that had already moved, and 2 of its 13 rounds existed only to get around them.

The fix is not to recognise refusal text — a cache keyed on less than its inputs is wrong whatever
the text says. The inputs now go into the key: `run_command` is never cached, `write_file` and
`edit_file` carry whether that path has been read this turn, and everything else is keyed as before.
That last part is what keeps the loop the cache was built for closed — it happened on `read_file`
for a path that does not exist, and a path does not start existing because it was asked for twice.

**A declined tool call is no longer counted as a failure (#95).** `DECLINED` begins with `error: ` on
purpose, because that prefix is what makes the model treat a refusal as recoverable rather than
terminal. The cost line decided what to call a malfunction with the same prefix, so a user's own
decision arrived as `1 failed` — seen in the run above, where the one "failure" was the
read-before-write rule holding. Counted and named separately now (`1 declined`). The prefix is
unchanged, and the screen still prints a declined call: only the count was split.

17 new cases (`cli/test_crow.py` 339, `cli/test_crow_core.py` 118), and they bracket the behaviour
rather than confirm it — held against four deliberate breakages, each red in a different place:

| breakage | red |
|---|---|
| the key ignores state again | 5 |
| the cache is removed altogether | 9, incl. the four cases that predate this change |
| a decline counts as a failure again | 3 |
| `DECLINED` loses its `error: ` prefix | 2 |

Neither "always cache" nor "never cache" passes both halves, which is the point: the second breakage
is the cheap fix that looks like success.

One test-harness defect fell out of it: `ToolLayerCase._install` **deleted** the entry it replaced
instead of restoring it, so a double installed over a shipped tool name removed that tool from
`TOOL_IMPL` for the rest of the process. Harmless until a case needed a double under a real name;
then an unrelated case went red with no visible connection to what broke it.

**`/mode` is in the header.** 0.3.2 shipped three release levels and advertised none of them: the
block beside the wordmark listed `/help`, `/tools` and `/exit`, so the only way to find `/mode` was
to already know it existed and type `/help`. A level nobody can find is the same as no level. It now
reads `/mode manual, allowedit or auto` — the modes on the line, because the header is where the
user learns what the prompt will do.

The column is budgeted against the wordmark's **five rows**: four commands plus a blank plus the
repository URL is six slots, the commands still land on the mark, and the URL moves down onto the
bevel row. A **fifth** command pushes the URL onto the version line — which is the one thing
`header_lines`' centring exists to prevent, and **no test noticed**:
`test_the_version_line_carries_no_command` iterates commands only, and the URL is the last entry, so
it is the one that falls off first. Now pinned by
`test_the_version_line_carries_nothing_from_the_column`, with
`test_a_fifth_command_pushes_the_url_onto_the_version` as its negative control — an assertion never
seen red cannot be told apart from one that cannot go red. 329 in `cli/test_crow.py`.

## 0.3.2 — 2026-08-14

**The CLI's tool-call marker is a glyph the shipped font actually has.** It was U+2692 `⚒`, and
neither shipped face covers it — Windows drew it from a substitute face, which is the exact fallback
`cli/crow.py` keeps its spinner away from braille to avoid. Found by E9 on 2026-08-13, declared in
`KNOWN_UNCOVERED` rather than swallowed, fixed here. It is now **U+25CF `●`** — the same marker the
window already draws for a tool call, so both surfaces mark a call the same way. Two call sites,
`cli/crow.py:935` and `:963`; nothing else used it.

The declaration was not deleted alongside the edit: `check_gui_prereqs.py` went red at it first
("U+2692 is declared in KNOWN_UNCOVERED and no surface writes it any more — drop the declaration"),
which is the half of point (ii) that makes the other half worth reading. `KNOWN_UNCOVERED` is now
empty.

**Release levels for tool calls (#88).** The seven tools ran unasked in both clients. They now run
under a level, and the level is visible in both surfaces.

| class | tools | manual | allowedit | auto |
|---|---|---|---|---|
| reading | `read_file`, `list_dir`, `find_files`, `search_text` | runs | runs | runs |
| writing | `write_file`, `edit_file` | **asks** | runs | runs |
| executing | `run_command` | **asks** | **asks** | runs |

- **Reading never asks, at any level.** A level that asks before `list_dir` is one nobody keeps
  switched on.
- **`auto` is the default**, because it is what every release up to 0.3.1 did. Making `manual` the
  default would change the behaviour of every existing session in a commit that adds a choice.
- **A declined call is a tool RESULT, not an abort** — `error: declined by the user`, and the turn
  continues. An assistant turn whose `tool_calls` have no `tool` message behind them is a broken
  prefix for every later turn, so this is a fourth trigger for the rule `run_turn` already keeps
  three times over, not a fourth implementation of it.
- **The terminal:** `/mode` reports the level, `/mode manual|allowedit|auto` switches it, `--mode` is
  the start value. The prompt prints the tool and its arguments, and offers "always for this
  directory / this program".
- **The window:** a dropdown beside `send`, coloured by level — manual white, allowedit green, auto
  yellow. A held-back call becomes a card in the transcript with three buttons; the card stays
  afterwards with the answer on it.
- **Standing approvals are per session and never written to disk.** Their scope is one directory for
  writes and one program for commands, so `git status` and `git log` share a key while `git` and `rm`
  do not. Dropped by `/reset`, by the window's new-chat button and by any level change — but **not**
  by a rollover, which resets the conversation while the user carries on with the same work.
- **The slash commands left `repl()`** into `run_slash()`. `test_repl_is_one_job_again` caps the loop
  at 220 lines so the five-job block the 0.3.0 split took apart cannot grow back; `/mode` pushed it
  to 227. Moved rather than rewritten. The command-coverage test now reads both functions — it was
  looking for the command names in `repl()`'s source alone and would have gone red at a refactor that
  changed no behaviour.

15 new cases in `cli/test_crow_core.py` (111 total), including the two #88 asks for by name — a
`write_file` refused under `manual`, a `run_command` refused under `allowedit` while the write in the
same turn runs — and the memory's negative half: a second directory and a second program must ask
again. Held against three deliberate breakages: a `needs_approval` that never asks goes red in 8
cases, a refusal that aborts the turn in 2, a memory with no scope in 1.

**Not in this change:** a working-directory boundary. #88 says why — a level asks a human, a boundary
refuses without asking, and mixing them into one ticket is how neither gets built.

**Both checkers that still measured tkinter now measure the window.** Neither was in the release
gate, so neither blocked anything — which is exactly why they could sit green and wrong.

- **`tools/measure_gui_stream.py` runs again.** Its point 1 measured Tk queue saturation against
  `TICK_MS` and `DRAIN_PER_TICK`, constants the webview does not carry, so it raised
  `SETUP ERROR: crow_gui.py does not carry TICK_MS` — and because that error returned from `main`,
  it took the two points **below** it down with it. Twenty lines of dead apparatus made 633 lines of
  live measurement unreachable, including the read-timeout probe that decides `READ_TIMEOUT_S`.
  Point 1 removed (99 lines, 3 functions); its result is kept in the docstring because
  `cli/crow_gui.py` quotes it. Points (2) and (3) keep their numbers — they refer to each other by
  number in their own output.
  **`READ_TIMEOUT_S = 600` now stands on a run rather than a note:** `3 of 3 numbers hold`, and the
  check is two-sided (`469.51 < bound < 1800`), so the previous 20 s would have gone red here.
- **`tools/check_gui_prereqs.py` point (iii) checks the window runtime**, not Tk 8.6.15. Both halves,
  because they fail separately: pywebview importable (6.2.1, read from package metadata — the module
  carries no `__version__`) **and** a WebView2 runtime in the registry (151.0.4129.78). All three
  views are read, because on this machine only `HKLM\WOW6432Node` answers; the GUID and the keys are
  `install.ps1:334-338`'s rather than a second set. **No floor is claimed for WebView2** — none has
  been measured, and an invented number is worse than none. `--min-webview2` exists for the negative
  control. Points (i) and (ii) are untouched — (ii) is what found the uncovered U+2692 marker fixed
  above, and its declaration list is empty again.
- **`tools/test_check_gui_prereqs.py` case 4 follows it** — it drove `--min-tk 99.0` and went green
  off the old point. Now `--min-webview2 999.0`: `2 of 3`, exit 1, with (i) and (ii) still green.
  8 of 8.

## 0.3.1 — 2026-08-14

**The window shipped in 0.3.0 was usable for one turn at a time.** Driving it for an afternoon found
four defects, three of which only appear once a turn is allowed to run longer than a single round.
Two of them were listed in 0.3.0's own *Known* section and are closed here.

### Changed

- **Tool calls now RUN in the window**, as they always have in the terminal. 0.3.0 shipped them as
  shown-only behind a chip, on the argument that behind a window nobody sees `run_command` start a
  shell. Driven live, that argument cut the other way: a user who asks for a file gets a tool call
  and no answer at all, every turn, with nothing on screen saying why. `--no-tools` is the new flag
  for the old behaviour, and the chip still names the mode in both states.
  **This does not add permission levels.** #88 (`/mode manual, allowedit, auto`) binds intent to
  permission, and it binds both clients or neither. `run_command` starts a shell in either one.

### Fixed

- **`READ_TIMEOUT_S` was 20 s** — listed as known in 0.3.0 and reached within minutes of tools being
  switched on. It is a **per-read** bound, so it only ever expires on a wait with no bytes in it: a
  prefill. A live turn died at `prefill 2,222 @ 51.21 tok/s`, about 43 s of silence, losing 12 rounds
  and 13 tool calls to `stream broke: timed out`. Now 600 s, which is what `README.md` and
  `tools/measure_gui_stream.py:106` had already been saying and what its own probe at `:636` requires
  (`> 469.51`, the worst prefill on record).
- **Maximising on a second monitor moved the window to the primary one.** `SPI_GETWORKAREA` returns
  the primary monitor's work area and nothing else; the window was being sent to coordinates that
  only exist over there. Now `MonitorFromWindow` + `GetMonitorInfoW`, which answer for the monitor
  the window is actually on. Verified by driving the real functions against a window placed on each
  of three screens, including one at scale 1.5, with the old path as the negative control.
- **The chat column hugged the left edge.** `max-width` without auto margins pins a column to the
  left and leaves the rest of a wide window empty. Text and composer now share one centred 900 px
  measure.
- **The download check named the wrong file count.** `README.md` told the reader to expect "four
  files totalling ~97 GiB" — that is `UD-IQ3_XXS`, replaced on 2026-08-12. `UD-IQ2_XXS` is three
  shards and 84.62 GiB (90,860,736,928 B). The line exists because `hf` prints `Downloaded` and
  returns the local directory when it could not reach the repository; the one check meant to catch a
  silent failure was producing one.
- **The architecture diagram's VRAM caption ran off both edges** — one 184-character line in a
  1132-wide box, and SVG does not wrap.

### Also

- **`README.md` is half its length**: 9,128 words to 4,686. Every measured figure, command block,
  table and citation stayed; the prose around them went.

### Known, and not fixed here

- **One aborted read in 50 outlived its grace** (`race_runs 50`, `race_leaked 1`, one run) —
  unchanged from 0.3.0.
- **Slash commands other than `/tools` do not exist in the window**; they go to the model as text.
- **`tools/measure_gui_stream.py` is red** and measures the tkinter build that 0.3.0 removed
  (`SETUP ERROR: crow_gui.py does not carry TICK_MS`). It owns the read-timeout probe, so the 600 s
  above clears a recorded floor rather than a re-run one.
- **`tools/check_gui_prereqs.py` still checks Tk 8.6.15** and reports 3 of 3 green. It is not in the
  release gate — that list names `check_shared_core.py` and `check_operating_point.py` — so it blocks
  nothing, but it is a checker that cannot go red for the toolkit this package actually ships.

### Measured

`cli/test_crow.py` 327/327 · `cli/test_crow_core.py` 96/96 · `cli/test_crow_gui.py` 47/47 ·
`check_shared_core` 44/44 · `check_operating_point` 4/4.

The operating point is unchanged from 0.2.0. Nothing in this release was measured against a live
server beyond the turns that produced the two defects above; the window itself was accepted by
driving it, not by a probe.

## 0.3.0 — 2026-08-13

**Crow gets a second client: a window, over the same core.** `cli/crow_gui.py` is a pywebview window
on the same conversation, the same session file and the same server as `cli/crow.py`. Neither wraps
the other, neither is needed to use the other, and both ship in the same package.

### New

- **The window.** Streaming with a live counter, foldable thought blocks, code blocks with a copy
  button, a chat list with rename / archive / delete, `/tools`, and a chip that says whether tools
  run or are only shown. Tools are **shown** by default — #55 and #88 are open, and a window that
  ran shell commands without saying so would answer that question silently.
- **`cli/crow_core.py`** now carries what both clients share: conversation, request body, SSE read,
  tool loop, cost line, where a thought block begins. `cli/crow.py` went from 2,942 to 1,701 lines.
- **The installer installs `pywebview`** into the interpreter it found. A failed pip does not fail
  the install — the terminal client is complete without it, and the exact command to finish the
  window by hand is printed with that interpreter's real path.
- **The preflight asks for the WebView2 runtime instead of Tk**, before the download, out of the
  registry — all three views, because on the development machine only the 32-bit one answers.

### Fixed

- **The chat list lost chats.** A chat was given its file when it was *restored* rather than when it
  was *left*, so every launch wrote another copy and deleting them brought one straight back. A chat
  with no file of its own was written into `session.json` when the user switched away — a file
  nothing lists and the next turn overwrites. A renamed chat lost its name because `save_session`
  writes six keys and the file whole.
- **A warm session was never saved.** The warm-cache flag was passed as the fourth argument of
  `save_session`, which is `path`; the call then died inside `os.path.dirname` and was swallowed.
- **Every cost line reported no thinking share** — it travelled as a message the page has no case for.
- **The taskbar button did nothing.** A frameless window is created without `WS_MINIMIZEBOX`, that
  bit is ignored without `WS_SYSMENU`, and the shell reads the style once, when it registers the button.

### Known, and not fixed here

- **One aborted read in 50 outlived its grace** (`race_runs 50`, `race_leaked 1`, one run). The
  normal path holds: the next question was answered 8.04 s after the abort, under the 30 s threshold.
- **`READ_TIMEOUT_S` is 20 s in the window**, while the worst prefill measured on a resumed 21k
  session is 469.51 s — a resumed session whose cache does not hold can be cut off mid-prefill.
- **Slash commands other than `/tools` do not exist in the window**; they go to the model as text.
- **`timings` arrives on almost every chunk**: 12 of 14 at `predicted_n 13`, one run.

### Measured

`cli/test_crow.py` 327/327 · `cli/test_crow_core.py` 96/96 · `cli/test_crow_gui.py` 47/47 ·
`tools/test_run_server_block.py` 24/24 · `check_shared_core` 44/44 · `check_operating_point` 4/4 ·
`install.ps1 -Selftest` 74 checks.

The operating point is unchanged from 0.2.0. E14 ran the window against it: 7 of 7 capabilities
held; two checks that live only in the page — folding a thought block, typing during a turn — are
reported as **not measured** rather than green.

## 0.2.0 — 2026-08-12

**The operating point moves to `UD-IQ2_XXS`.** Same verdicts on the gate, cheaper misses, and
3 GB more of the card left over. The binary is the one 0.1.0 shipped; what changed is which file
it opens.

### What was measured, #89

Three graded runs of the ten-task gate per rung, own server per run, one variable changed:

| | UD-IQ3_XXS | UD-IQ2_XXS |
|---|---:|---:|
| gate, three runs | 10/10 · 10/10 · 10/10 | 10/10 · **9/10** · 10/10 |
| decode, median | 18.63 tok/s | **19.53** |
| prefill, 1,884-token prompt | 118.26 tok/s | **133.10** |
| ms per miss | 0.7097 | **0.6470** |
| hit rate | 80.24 % | 80.13 % |
| VRAM after load | 31,074 MiB | **27,994 MiB** |

**The one 9/10 is the extractor, not the model.** `two-sum` in run 2 answered completely and
correctly and put `from bisect import bisect_right` above the function; the extractor takes only a
definition in column 0, so the call died on a `NameError`. Replayed against the extracted file to
confirm. `merge-intervals` — the task that failed 3 of 3 byte-identically on `UD-Q2_K_XL` in #28 —
is correct 3 of 3 here.

**The mechanism is bytes per miss, not cache slots.** The hit rate moved 0.11 points across a
13.38 % smaller slab. That is what a saturated cache looks like: 0731 covers 95 % of its selections
in 9.0 % of the experts, and 58 slots is 22.7 % resident.

### The file

84.62 GiB across three shards — 90,860,736,928 B. Routed experts 78.11 GiB of that, 92.3 %.
Resident tensors 6,378.40 MiB on CUDA0 plus 284.06 MiB of host buffers = 6.51 GiB. A slot costs
327,614,463 B per expert across 43 layers, so 58 slots is 18,121.38 MiB — the server's own line.

### Unmeasured on this rung, and marked wherever it appears

The slot ladder (56/58/60/62/64) and the host-tier pairing that produces the **1.63x** were taken
on `UD-IQ3_XXS` and are **not** repeated here. They describe a mechanism that did not change and
carry numbers that did. 58 slots is carried over unchanged for the reason it was chosen — the cache
is already past saturation, so the 4.6 GB the smaller slab frees would buy nothing.

Also unmeasured: the vendor KLD gap (0.30789 → 0.48487, top-1 81.93 % → 76.60 %) against anything
but ten algorithmic tasks. #46 puts the gate's own resolution at two tasks, so what is established
is the **absence of a detectable loss**, not the absence of a loss.

## 0.1.1 — 2026-08-11

**The operating point asked for more VRAM than the card has.** `--moe-stream-cache` goes from
**64s to 58s**. Nothing else about the product changed; the binary is the same one 0.1.0 shipped.

### What was wrong

A slot costs 360.69 MiB, so 64 slots need 32,062 MiB of a 32,607 MiB card and leave **545 MiB** for
everything the display does. This machine's desktop was read at **342, 543, 622 and 978 MiB within
one day**. Above the gap Windows moves the difference into host memory without printing anything,
and the affected request runs at half rate.

That is why it looked like a lottery rather than a fault: it depends on what is on the screen when a
request runs, so it hit some turns and not others, and never the short runs of the measurement
harness.

**No counter in the server can see it.** The halved request executed the same 195 graphs, took
comparable misses, and had the **lowest** load stall of its run — 7,807 ms against 7,872 / 8,651 /
9,041. Identical work, double the wall clock, and nothing in the streaming path to charge it to.

### Measured, 2026-08-11

Cold prefill of 1,374 tokens (3 runs) and decode of 200 tokens (8 runs), fresh server per run,
`runs/2026-08-11/`:

| cache | prefill | decode | VRAM used | free |
|---|---:|---:|---:|---:|
| 64 (0.1.0) | 15.28, spread **8.69x** | unusable | 32,014 | 545 |
| 62 | 114.92 | **7.07 among 15s** | 31,899 | 708 |
| 60 | 113.53 | 17.40 | 31,285 | 1,322 |
| **58 (0.1.1)** | **112.69** | **17.32** | **30,548** | **2,059** |
| 56 | 110.30 | 17.00 | 29,842 | 2,765 |

Throughput rises with the cache right up to the edge, so the fastest value is not the shippable one.
62 wins on paper and still halved one request in four. 58 costs 0.7 % of prefill and 0.5 % of decode
against 60 and triples the margin over the highest desktop reading.

**Driven by hand through the client**, the same cold 1,094-token prompt prefills at **60.44 tok/s**
against 15.09 at 64 slots, and four consecutive rounds of one turn decode at 14.97 / 14.97 / 17.00 /
14.61 — the halving is gone. The harness figures above use a repeated word list, which routes to
fewer distinct experts than real text; both are measured, only the second is what a user waits for.

### Also ruled out, so it is not tried again

`-ub` in both directions (8 → 74.73 … 512 → 98.76 … 2048 → 13.42, and 2048 falls off the same cliff
with the same fingerprint), a larger host tier, cache capacity (`slot wait` is 0.00 ms over 0 waits
in every block of a 13-round run), cold misses, context length, and server uptime.

### Not measured

- **The graded gate has not been run at 58 slots.** The 19.81 tok/s on record is 62's. The 17.32 here
  is a probe of eight requests, not the gate, and `README.md` says so.
- 58 is derived from **this** card's 32,607 MiB and a desktop that peaks near 1 GiB. A smaller card
  or a busier display needs a different value, and the failure is silent. Open as
  [#87](https://github.com/nibor1896/Crow/issues/87).
- Whether the two-hour decode collapse of [#71](https://github.com/nibor1896/Crow/issues/71) is the
  same mechanism at a larger scale. Nothing measured for this release ran that long.

## 0.1.0 — 2026-08-10

The model switch: DeepSeek-V4-Flash (preview) is replaced by **DeepSeek-V4-Flash-0731**,
and the release keeps the one promise it made — not slower than 0.0.6.

### The promise, measured

Same driver, same six graded tasks, fresh server per arm, both arms with the shipped
chat template. Raw runs `runs/2026-08-10/0731-pairs`, fingerprinted in
`manifests/runs-2026-08-10.json`.

| | 0.0.6 (preview, 2026-08-09) | 0.1.0 (0731, 2026-08-10) |
|---|---|---|
| decode, tier, median of 3 pairs | 14.73 tok/s | **19.13 tok/s** (+29.9 %) |
| decode, no tier, median | 10.54 | 12.84 |
| stall per miss, tier arms | 0.745 ms | 0.717–0.741 ms |

Even the worst 0731 tier arm (16.17) beats the old median. Within-arm spread 1.19x
against the baseline's 1.09x — the band is indicative, the direction clears the noise.

### Changed

- **New wordmark, and the commands moved beside it.** The banner is drawn in full blocks
  with a box-drawing shadow instead of the shaded bevel. Both ranges are covered by the
  bundled Google Sans Code — measured 2026-08-10 from its cmap: U+2500–257F is 128 of 128
  and U+2580–259F is 32 of 32, against Cascadia Mono at the same counts as a control. A
  glyph outside them falls back to another face and the columns stop lining up, which is
  why the covered range is a test and not a comment. `/help`, `/tools` and `/exit` now sit
  to the right of the mark, one per line, the name in the same yellow a slash command turns
  while it is typed. The column is computed from the widest banner row, so it follows the
  mark instead of being written down beside it.
- **Model: `unsloth/DeepSeek-V4-Flash-0731-GGUF`, UD-IQ3_XXS, 97.1 GiB.** Identical
  architecture (43 layers, 256 experts, top-6). 378,208,256 B per expert — 288 MiB more
  than the preview at 64 slots, inside the measured 599 MiB of headroom (311 MiB left).
  Measured twice: HTTP range requests over the tensor table before downloading, and the
  finished files. Ready-made quantisation on purpose: third-party conversions that do not
  preserve the native MXFP4 experts deviate from the official weights, and the abandoned
  in-house conversion path additionally cost 66 CPU-minutes and 52 GB of RAM for a dry run.
- **The chat template ships as a file** (`templates/0731-chat-template.jinja`) and the
  printed server line carries `--chat-template-file`. 0731 publishes no Jinja template; the
  one embedded in the GGUF fails the model's own golden vector 4 — an action turn opens a
  think block it never closes. The shipped template renders **all four golden vectors
  byte-identically** (jinja2), and the Crow-shaped conversation renders byte-identically
  under the server's own minja too; vectors with roles Crow never sends fail in llama.cpp's
  message canonicalisation before any template runs, which is recorded as the boundary.
- **Sampling follows the model it ships:** `temperature 1.0` (was 0.6 — the preview
  family's value), `top_p 0.95` and `min_p 0.01` sent explicitly for the first time —
  omitting them meant inheriting server defaults nobody chose. The card-vs-
  `generation_config.json` disagreement on `top_p` is recorded next to the value.
  `--reasoning-effort low|high|max` rides in `chat_template_kwargs`, only when set;
  low against max provably changes the rendered prompt at the effort marker.
- **An update removes what the package dropped**, and the first dropped file is the unit
  suite (73,792 B of developer equipment that shipped since 0.0.1). Removal is decided by
  the PREVIOUS package's manifest, never by a directory listing — the exception-list
  design before it deleted a user's own backup folder on its first real run, restored only
  because the deleted folder was itself a copy.
- **The operating point has one source**, `manifests/operating-point.json`:
  version, model, server flags, sampling, and the measured baselines. `README.md`,
  `install.ps1` and the vault page are held against it as raw text by
  `tools/check_operating_point.py`; model paths and sampling defaults are read from it by
  the measurement tools.

### Measured for the first time

- **A diagnostic flag, not the documented line, produced the 1 tok/s.** Decode from the
  README line on a fresh server: **16.05 tok/s** over **one** answer of 108 tokens. That is
  *below* the weakest measured arm (16.17 / 19.13 / 19.25), by 0.7 %, and it is a single
  observation with no run written under `runs/` — it settles the direction, not the number,
  and nothing here is claimed against it. The same line with `-lv 5` writing to an
  interactive console: **0.98 / 1.01 / 1.13 tok/s** over three runs — a factor of 14 to 16.
  The debug
  log is ~40 lines per token; between two consecutive lines the gap is **2.05 ms** into a
  redirected file and **20.3 ms** onto a console, and every CUDA graph launch pays it,
  prefill and decode alike. The card sat at 2895 MHz and 155 W of 575 throughout, which is
  what a GPU waiting on its host looks like. The six gate runs redirect their log to a file
  (`measure-24-gate.ps1`); a hand-started server does not, and nothing said so.
- **Cold against warm prefill on the same server:** 953 tokens at **12.79 tok/s** with the
  expert cache empty, 984 at **62.68 tok/s** once it is not. Within the cold run itself the
  rate climbs from 9.93 tok/s over the first 437 tokens to 17.1 over the remaining 512. The
  filled-context figures below are the warm case and do not describe a first start.
- **What a fresh turn actually sends:** 953 tokens, of which 5 are the message and 39 the
  system prompt. The other **909 — 95.4 %** are the seven tool declarations, measured
  through the server's own `/apply-template` and `/tokenize`. They are unchanged since
  0.0.1 and ride on every request by design: the model's template drops a replayed
  `reasoning_content` when `tools` is empty.
- **Prefill at filled context** (server-counted denominators, fresh server):
  96.13 tok/s at 1,374 tokens · 85.32 at 10,824 · 83.80 at 43,224 · **76.54 at 172,824**.
  The old "8–50 tok/s" came from 86–103-token prompts and does not describe filled
  context — large batches amortise expert fetches. **Measured on the PREVIEW model**, in
  the before-side run that had to happen before the weights left the disk
  (`runs/2026-08-10/before-0731/prefill/`, temperature 0.6, no `--chat-template-file`).
  0731 has not re-run it. The series was published under the 0731 heading until
  2026-08-10 and the attribution is corrected here rather than quietly dropped.
- **VRAM at 200k on one slot:** 31,899 MiB after load, 31,997 under a filled context, of
  32,607. The two previously documented values (31,838 / 32,008) were taken at different
  phases of the same thing; neither said which.
- Preview quality before side, taken before the model left the disk: two gates, all ten
  probe-suite tasks exactly once, temperature pinned 0.6, 8 of 8 graded correct
  (`runs/2026-08-10/before-0731`).

### Not measured, said out loud

- Quality of 0731 beyond the six graded pair tasks and the probe bundle — no like-for-like
  quality comparison against the preview exists by design: the preview is
  replaced, not competed with.
- The host-RAM peak (33.73 GiB) and hit-rate figures in the README are preview-series
  measurements; 0731 has not re-run them. Marked as such where they appear.
- What `min_p 0.01` against 0.05 changes in output quality — the value is the
  quantiser's recommendation, not an in-house measurement.

## 0.0.6 — 2026-08-10

### Added

- **The window rolls over instead of hitting the wall.** The server's limit is not a slope: a
  request that arrives at or past `n_ctx` is refused outright and the turn is lost with it. At 90 %
  of the window (`--rollover-at`, `0` switches it off) Crow writes the conversation to
  `rollover-<stamp>.json` and `rollover-<stamp>.md`, empties it, and opens the next one with a note
  naming the transcript, its line count, and the paths the work had reached. `--resume FILE` picks
  an archive back up.

  Two properties came from watching it fail, driven live on 2026-08-10. The check also runs **inside
  the tool loop**, because one round was measured adding 5,253 tokens and a full-budget turn grew a
  single turn by 28,900 — more than the 20,000 that 0.9 leaves between the threshold and the wall.
  And the archive is written **without** the KV cache: the server's slot file has one fixed name, so
  saving it would put the archive's cache over the live one.

  The note points at the `.md` because the JSON is unreachable: `json.dump` writes one line, a real
  archive measured 104,618 bytes on it, and `read_file` caps at 16 KB. Pointed at the JSON, the
  model guessed a directory that does not exist, scanned a user profile twice, and spent **402 s
  across seven tool rounds** before it read anything.

- **`/tools`.** The seven tools were only ever visible in a request nobody reads. The listing is
  derived from `TOOLS` rather than written beside it. The header carries it, and the repository URL.

- **A slash command turns yellow as it is typed.** `input()` cannot do this — the console stays in
  cooked mode and hands nothing over until Enter — so the line is read one key at a time. Piped
  input and any platform without `msvcrt` or `termios` fall back to `input()`. Known cost: the
  console's own line editing goes with it. Backspace, Ctrl+C and Ctrl+D are handled; arrow keys and
  history are not.

- **`--max-tool-rounds`.** The limit that decides how long a turn runs was a constant with no flag,
  and the message it printed sent the reader looking for a knob that did not exist.

### Fixed

- **A spent tool budget ended in a bracket.** Driven live with `--max-tool-rounds 0`: the model
  produced 102 tokens, `thinking 100%`, and the user was shown nothing at all. One more round now
  goes out — tools still declared, or the template drops the replayed reasoning and the cache breaks
  (#60, 242.3 s against 1.6 s) — carrying a turn that says the budget is spent and asks for what was
  found, what was missed, and what comes next.

  Its first live run reported reading a line it had never read and described one that is blank, so
  the request names the case: if you ran nothing, say you ran nothing. Measured after the change on
  the same question: *"Ich habe nichts gelesen."*

- **Calls that will never run are no longer appended.** An assistant turn whose `tool_calls` have no
  `tool` message behind them is a broken prefix for every later turn, and the old bare `break` left
  one behind every time a budget ran out.

- **`cache warm` was a promise nobody checked.** Measured 2026-08-10: a start printed
  `resumed: 36 messages, cache warm` and the next turn came back `cached 0/21004` after **469.51 s**
  of prefill. A 200 from `action=restore` says the file was read, not that the slot holds the prefix
  about to be sent. The save now records the server's `n_saved`, the restore compares `n_restored`,
  and the first turn settles it: a warm claim followed by `cached 0` says so in one line. A server
  that reports neither figure is still believed — silence is not a contradiction.

- **An update can run while the server is up.** Windows locks a running binary, and the moment the
  client says a new version exists is the moment `llama-server` is up in the other terminal. The
  files in `bin\` are renamed to `.old` first — renaming a running executable is permitted, deleting
  it is not, both measured. What cannot be moved is named and the install stops there. The `.old`
  files that stay are reported as staying, not counted as removed.

  Driven end to end on 2026-08-10, **0.0.4 → 0.0.6 with the server serving throughout**: 17 files
  renamed, 26 extracted, 25 of 25 hashes matched, **2 `.old` removed and 15 reported as still held**
  — and 15 were still on disk afterwards, held by the process that was named. The version this
  replaces would have printed "17 stale .old files removed", which is false for 15 of them. The
  running server kept answering; the new binary took over on its next start.

### Tests

- `install.ps1 -Selftest`: 51 checks, up from 42, nine of them reaching the new code — two against a
  real lock rather than a simulation. The first version of that fix sat below the selftest's exit
  and reported 42 of 42 green without executing a line of itself.
- `cli/test_crow.py`: 201, up from 122.
- `tools/probe-rollover.py`: new. Drives the real CLI through a fake OpenAI endpoint at `n_ctx=100`
  — 35 checks in about a second, no model loaded.

### Not done

- Nobody has watched the 15 `.old` files leave. They are swept on the next install that finds them
  unheld, and `Move-LockedAside` clears a stale one before it renames over the same name — both
  covered by the selftest against real locked files, neither seen on a live machine after the server
  finally stopped.

## 0.0.5 — 2026-08-09

### Added

- **Crow acts.** The client executes the model's tool calls, hands the results back and asks
  again, up to 24 rounds: `read_file`, `write_file`, `edit_file`, `list_dir`, `find_files`,
  `search_text`, `run_command`. Until now a reply could only be printed and copied out by hand.

  Three properties carry a reason rather than a preference. `read_file` takes a line range and
  caps at 16 KB, because prefill is the cost that matters — a 100 KB file is ~25,000 tokens, and at
  the 8–50 tok/s prefill measures depending on cache state that is between eight and fifty minutes
  before the model has read a word of it. `write_file` and `edit_file`
  refuse a file this session has not read, because a model that writes what it has not read
  overwrites whatever it does not know about. And the system prompt deliberately carries no
  working directory: it is byte 0 of the prefix, so a session saved in one folder would be
  worthless resumed from another.

  Driven live on 2026-08-09 — `list_dir` → two `read_file` calls → a correct answer, five turns
  at 11.79–16.72 tok/s with the prompt cache holding (`cached 4140/4722` by the last turn).

- **`--moe-stream-l2 <GiB>`: an optional host-RAM tier below the VRAM slots.** A miss that finds
  its expert in page-locked host memory uploads at 47,357 MB/s instead of fetching it off the
  drive at 10,593 — **56.7 µs against 401.5 µs per work item, 7.08x.**

  Measured end to end, paired on identical tasks, 32 GiB tier: **15.89 / 14.73 / 14.53 tok/s with
  against 10.81 / 10.54 / 10.09 without — 1.40–1.47x**, and the cost of a miss falls from
  1.28-1.35 ms to 0.73-0.75, a factor of 1.79. Within-arm spread was 1.09x and 1.07x, narrower than the difference.

  **The arrangement is half the result, and two of them measured nothing.** Repeating the same
  ten gate tasks per run gave 7.65 and 15.77 tok/s at *identical* configuration, because the
  second run meets the cache the first warmed — with 32 GiB of experts held, that shared state is
  the subject. Giving each arm different tasks removed the carry-over and replaced it with arms
  solving differently hard problems. What works is both at once: same tasks within a pair, fresh
  tasks across pairs, each arm on its own server.

  **It costs 32 GiB of page-locked memory** — process peak goes from 1.28 GiB to 33.73 GiB, and
  that memory is unavailable to the rest of the machine until the server exits. The flag defaults
  to off; the installer puts it into the command it prints above 60 GB of detected RAM, because 32 GiB on a ~64 GB host
  is the only ratio that has been run.

  **Unmeasured:** any other tier size, and whether the factor survives a full 200k window. Every
  paired run stayed under 6k of context.

- **`--slot-save-path` is in the printed command, and the installer creates the directory.** The
  server refuses to start against a path that is not an existing directory, so the line it
  printed could fail on a fresh install. Without the flag a restart re-prefills the whole history.
  The 22 ms restore is measured; the ~35 minutes for 23,400 tokens is extrapolated from a run that
  was aborted at 10 %.

### Fixed

- **A cache race that no throughput number could show.** The tier's first version handed out a
  resident slot and released its lock; another worker took the same slot as an eviction victim
  and read a different expert into it mid-upload. The model emitted 8,191 characters of
  `<<<<<<<<` instead of an answer — at 31–35 tok/s, a fast run by every counter that existed.
  A slot is now pinned while it is read, and a filled one is published only after its bytes have
  left for the GPU.

- **A failed session restore repeated forever.** Point the server at a different
  `--slot-save-path` than the one a session was written to and the client asked for a KV state
  that was not there, on every start, printing two server errors each time. The claim is now
  withdrawn when it is disproved. The first failure still prints — the client cannot know whether
  the file exists, because the path belongs to the server.

- **The tool call line showed half its JSON.** A raw cut at 80 characters lands mid-string often
  enough to be the normal case, and `read_file({"path":"…","start_line":1,"` reads as a malformed
  call rather than a shortened one. Values are shown now, paths cut from the front.

- **The tier's allocation line was invisible.** At the default verbosity `llama-server` prints no
  INFO from `llama.dll` at all, so a user who passed the flag saw no confirmation anywhere. It is
  printed at WARN — a deliberate misuse of the level, because what it reports is that GiB-scale
  memory has been page-locked away from the rest of the machine.

### Changed

- **`probe-suite.py` defaults to temperature 0.6, matching the CLI.** At 0, under the model's own
  chat template, greedy decoding never leaves the reasoning block: sixteen answers in a row came
  back `finish_reason=length` with an empty content field. `--temperature 0` remains available for
  reproducing the older series and is now a deliberate act.

- **`measure-24-gate.ps1` gained `-Only` and `-Warm`.** Repeating a task measures the cache, not
  the configuration; a warm-up pass on tasks the graded pass does not use keeps the first graded
  task from paying for the cold model, cold slots and empty tier at once.

## 0.0.4 — 2026-08-08

### Fixed

- **There was no way to update.** `install.ps1` refused any non-empty target with
  `pass -Force to overwrite` and exit 1 — and the documented one-liner is
  `irm … | iex`, which cannot be given parameters at all. The advice it printed
  could not be followed by the person reading it. Moving from one version to the
  next meant deleting `%LOCALAPPDATA%\Crow` by hand, and nothing said so.

  The installer now reads the version out of the `cli\crow.py` it finds in the
  target — the same pattern `pack-release.ps1` stamps it with, so the two cannot
  disagree about where the number lives — and decides from it. An older install
  updates. The same version does nothing and exits **0**, not 1. A newer install
  is not overwritten, and a directory that does not identify itself as a Crow
  install is not touched; both refuse and print the `[scriptblock]::Create`
  invocation that *can* carry `-Force`, because naming a switch the user's command
  cannot pass is not a route.

  Driven end to end over the real 0.0.1 and 0.0.2 packages, not only in the
  selftest: install, update, same-version, downgrade-refused, stranger's-directory
  refused. The refusals left the target untouched.

- **Nothing told anyone a new version existed.** The client asks the release API
  on start and prints the version together with the command that installs it. The
  request is fired before the banner is drawn, so it overlaps work that happens
  anyway, and it is given at most 1.5 s of the start. Every failure — no network,
  rate limit, an answer we do not recognise — is silence rather than an error
  between the user and their prompt. `--no-update-check` switches it off.

  **This cannot reach installations that predate it.** 0.0.3 and earlier have no
  check in them and will never announce 0.0.4; that generation has to be updated
  by hand, once.

### Added

- **`crow --version`.** The number existed only inside the start banner.
- **The installer resolves the newest release itself** when no `-Version` is
  given, so the same one-liner installs the current version without anyone editing
  a default. The hard-coded number stays as the offline answer.
- **`Updating` in the README**, which said nothing about it before.

### Tests

Client suite 91 → 108. Installer selftest 24 → 37. The new cases include the ones
that must refuse: an equal version, a newer install, an unparseable version string.
A comparison that read garbage as `0.0.0` would announce an update to every user on
every start, which is worse than no notice at all.

### Not done

Nothing is deleted on update. The 95.9 GiB model lives under the install directory,
so a "clean" install would throw it away and re-download it over the user's
connection. Files a newer package no longer ships are therefore left behind.

## 0.0.3 — 2026-08-08

### Fixed

- **The server command the installer prints was missing `--port 8081`.** `llama-server`
  defaults to 8080 and the client defaults to 8081, so following the instructions
  exactly produced a server the client could not find — and on Windows 8080 is
  frequently already held by something else, which is how it surfaced: a bind
  failure rather than a silent mismatch. The operating-point page in the project's
  notes carried the flag all along; the shipped command had dropped it.

- **The installer verified nothing, and the word was on the screen anyway.** Step 3
  was called *Verifying*: it printed the archive's SHA256 and compared it with
  nothing, and the `MANIFEST.json` in the package — a hash per file — was never
  read.

  The assumption underneath was that a damaged archive would fail to extract.
  Measured 2026-08-08: it does not. A single flipped byte inside the compressed
  stream, at three different offsets, and `Expand-Archive` extracted all three
  **without an error** and wrote the wrong bytes to disk. TLS covers the wire;
  nothing covered the file. A damaged install would have surfaced later as a DLL
  that will not load and been diagnosed as anything but a bad download.

  Verification now happens after extraction, against the manifest, file by file.
  A mismatch names the file, says the install is damaged, and exits 1 instead of
  printing the next steps. Both directions are driven end to end in the suite:
  an honest package passes, a package whose manifest disagrees with its contents
  fails.

## 0.0.2 — 2026-08-08

The first release existed for about an hour before it was installed, and both
defects it shipped were found by running it rather than by reading it.

### Fixed

- **A finished install reported exit code 255.** `& nvidia-smi … | Select-Object -First 1`
  ends the pipeline after one line, PowerShell kills the process, and
  `$LASTEXITCODE` lands on `-1`. Nothing later touched it, so the installer
  handed that back after doing everything right. Any caller checking an exit
  code read a success as a failure.
- **The install closed the user's shell.** The fix for the above put an explicit
  `exit 0` at the end. In a script file `exit` leaves the script; in a string run
  through `iex` — which is how this is installed — it leaves the **host shell**.
  The window vanished the instant the install finished, before the three
  commands it had just printed could be read.
- **The command the installer prints was missing `--jinja`.** Without it
  `llama-server` uses its own built-in template instead of the model's, the
  client's replayed reasoning is dropped, and the prompt cache breaks on every
  turn: 138.8–242.3 s of re-prefill against 1.6–2.2 s. Following the installer
  gave the slow path while following the README gave the fast one.

### Added

- **The run ends on ENTER.** A console opened for the install closes with it, and
  the model to fetch and the two commands to run appear nowhere else on screen.
  `-NoPause` for a script driving the install; skipped when the host has no
  console, because a wait nobody can satisfy is a hang.
- **`-SourceUrl`** takes an http(s) URL or a local `.zip`. An installer whose only
  source is a release can never be tried before that release is published — the
  first person to run it would be the first person to test it.
- **The last screen names the model properly**: what it is, who quantised it,
  where it lives, and the one trap measured on 2026-08-07 — `hf` reports success
  even when it reached nothing.

### Changed — the client

- **An assistant turn now carries its reasoning back into the history.** The
  chat template renders a kept turn as `<think>…</think>`, so omitting the field
  left an empty think block and the prefix diverged exactly where the thoughts
  began. Everything behind that point was re-read, however short the thoughts
  were: 48 tokens of reasoning cost 2,018 tokens of prefill. Measured across
  three task sets — dropping it re-reads 0.909–0.986 of the previous turn's
  output, replaying it re-reads 0.008–0.016. Live: turns 2 and 3 prefilled 18 and
  19 tokens where they had cost about 4,256 before. ([#60](https://github.com/nibor1896/Crow/issues/60))
- **Every request carries a one-entry `tools` array**, for the prompt cache
  rather than for the tool. This template keeps a past turn's thoughts only while
  tools are present; with none, both variants render byte for byte the same.
  A returned tool call is reported, not executed — that is
  [#58](https://github.com/nibor1896/Crow/issues/58).
- **The context bar asks the server** instead of adding `prompt_n` and
  `predicted_n`, which was wrong three times over and ran the bar *backwards*
  while the conversation grew. It reads `usage.total_tokens` now.
  ([#60](https://github.com/nibor1896/Crow/issues/60))
- **The timing line carries `cached N/M`** — how much of the prompt the server
  did not have to read again, per turn, reported rather than inferred.

### Tests

Client suite 75 → 91. Installer selftest 13 → 20, including the two cases that
cover the shell it used to close. `tools/probe-prefix-cache.py` and its suite are
new: they are the measurement behind the reasoning decision, not a description of
it.

## 0.0.1 — 2026-08-08

First package: the patched `llama-server` with the expert-streaming path, every
runtime library it needs, and the Python client. 26 files, 506.4 MB,
self-contained — the packer refuses to write an archive whose binaries import
something the archive does not carry.

Superseded within the day by 0.0.2. It installs, and then reports a failure and
closes the window.
