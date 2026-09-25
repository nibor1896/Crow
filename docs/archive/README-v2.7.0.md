[← README](../../README.md) · [Docs index](../README.md)

<!-- ARCHIVED 2026-09-25. This is README.md as it stood at v2.7.0, the last text front page
     before the image README. Its current content lives in user-guide/overview.md,
     user-guide/install.md and operating-points.md. Do not edit. -->

<div align="center">

<img src="../images/window-goal-2026-09-16.png" alt="The Crow window running a goal: the trace with a delegated subagent, the goal panel at 3/3, and the tool calls in the code panel" width="900">

<h1>CROW</h1>

<h3>An agent, not a chat box.</h3>

<p>A local model at 200k context with 28 tools and MCP, persistent memory, its own skills,<br>a browser panel, eyes, and subagents it can send out while it keeps working.<br>Runs on this machine, or on a provider you choose.</p>

<p>
<a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square&logo=opensourceinitiative&logoColor=white&labelColor=000000" alt="License"></a>
<a href="../../cli/crow.py"><img src="https://img.shields.io/badge/version-2.7.0-brightgreen?style=flat-square&logo=semver&logoColor=white&labelColor=000000" alt="Version"></a>
<a href="../user-guide/install.md"><img src="https://img.shields.io/badge/platform-Windows%20x64%20%C2%B7%20Linux%20x86__64%20%C2%B7%20CUDA-555555?style=flat-square&logo=nvidia&logoColor=76b900&labelColor=000000" alt="Platform"></a>
<a href="https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF"><img src="https://img.shields.io/badge/model-Qwen3.8--Flash--Next-orange?style=flat-square&logo=huggingface&logoColor=ffd21e&labelColor=000000" alt="Model"></a>
<a href="https://github.com/ggml-org/llama.cpp"><img src="https://img.shields.io/badge/engine-llama.cpp-555555?style=flat-square&logo=cplusplus&logoColor=00599c&labelColor=000000" alt="llama.cpp"></a>
<a href="https://github.com/nibor1896/crow-nest"><img src="https://img.shields.io/badge/engine-crow--nest%20(Rust)-555555?style=flat-square&logo=rust&logoColor=ffffff&labelColor=000000" alt="crow-nest"></a>
<a href="../reference/tools.md"><img src="https://img.shields.io/badge/vision-read__image-9b59d0?style=flat-square&logo=image&logoColor=white&labelColor=000000" alt="Vision"></a>
<a href="../user-guide/browser.md"><img src="https://img.shields.io/badge/browser-built--in-9b59d0?style=flat-square&logo=googlechrome&logoColor=white&labelColor=000000" alt="Browser"></a>
<a href="../user-guide/memory.md"><img src="https://img.shields.io/badge/memory-persistent-555555?style=flat-square&logo=sqlite&logoColor=003b57&labelColor=000000" alt="Memory"></a>
</p>

<table>
<tr>
<td align="center"><b>MoE</b><br><sub>512 experts, 10 active</sub></td>
<td align="center"><b>200k</b><br><sub>context, one slot</sub></td>
<td align="center"><b>73.45 GiB</b><br><sub>model on disk</sub></td>
<td align="center"><b>30,984 MiB</b><br><sub>VRAM in use</sub></td>
<td align="center"><b>41.76</b><br><sub>tok/s decode</sub></td>
<td align="center"><b>727.65</b><br><sub>tok/s prefill</sub></td>
<td align="center"><b>yes</b><br><sub>vision</sub></td>
</tr>
</table>

<sub>Decode and prefill: 2026-09-01 (#182), driver 616.56, one 33,494-token cold turn per boot, three rounds interleaved against the previous placement (539.98&nbsp;/&nbsp;35.74); decode range 40.34–42.76. VRAM settled after load. Conditions in full, and the Linux line: <a href="../operating-points.md">operating points</a>.</sub>

</div>

---

## Install

**Windows**

```powershell
irm https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1 | iex
```

Preflight, download, per-file sha256 against the release manifest, then the start lines with
paths resolved. No elevation, nothing in Program Files, the registry or `PATH`.

**Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh | bash
```

Five steps, a per-file sha256 manifest it re-reads on the next run, idempotent. No root — the GTK
and WebKit bindings come from your distribution, so the installer prints that line instead of
running it.

**Optional components**

| component | Windows | Linux |
|---|---|---|
| dictation (faster-whisper) | always installed | `curl -fsSL …/install.sh \| bash -s -- --voice` |
| phone over HTTPS ([Tailscale](https://tailscale.com/download)) — prints only the missing steps, never runs sudo | `&([scriptblock]::Create((irm …/install.ps1))) -Tailscale` | `curl -fsSL …/install.sh \| bash -s -- --tailscale` |
| [voxel kit](../user-guide/voxel-kit.md): path-traced voxel dioramas in one offline page — switches the `voxel-diorama` skill on | `&([scriptblock]::Create((irm …/install.ps1))) -PathTracer` | `curl -fsSL …/install.sh \| bash -s -- --pathtracer` |

**Neither one downloads the model.** That is a separate command:

```powershell
hf download unsloth/Qwen3.8-Flash-Next-GGUF --include "*UD-Q2_K_XL*" --local-dir $env:LOCALAPPDATA\Crow\models\qwen-next-gguf
hf download unsloth/Qwen3.8-Flash-Next-GGUF mmproj-F16.gguf --local-dir $env:LOCALAPPDATA\Crow\models\qwen-next-gguf
```

```bash
hf download unsloth/Qwen3.8-Flash-Next-GGUF --include "*UD-Q2_K_XL*" --local-dir ~/Projects/models/qwen3.8-flash-next
hf download unsloth/Qwen3.8-Flash-Next-GGUF mmproj-F16.gguf --local-dir ~/Projects/models/qwen3.8-flash-next
```

Three shards, 73.45 GiB, plus 904,004,000 B for the vision projector. **The second line of each
pair is that projector and the glob of the first walks past it** — it sits in the repository root,
above the quant folder. Without it the server starts as a text model and `read_image` refuses.

Requirements, both operating systems, updating, and where everything lands:
**[Install guide](../user-guide/install.md)**.

## Start

Two terminals: the server first (it loads for about a minute), then the window.

**Linux**

```bash
python3 ~/.local/share/crow/tools/start-server.py flash-next-q2-k-xl
```

```bash
crow
```

**Windows**

```powershell
python $env:LOCALAPPDATA\Crow\cli\crow.py --serve flash-next-q2-k-xl
```

```powershell
python $env:LOCALAPPDATA\Crow\cli\crow_gui.py
```

The window is the client. It reads the port off the running server, and the model menu can
switch and reboot it from there. The by-hand `llama-server` lines, flag for flag, live in
[operating points](../operating-points.md).

## How to use Crow

Everything below is in the screenshot at the top of this page.

| | |
|---|---|
| **Chats sidebar** | chats grouped by project, archive at the foot, fold state remembered. A delegated subtask hangs under its chat as a `⑂` row. → [window](../user-guide/window.md) |
| **Composer** | type, or `/tools` for what the model can call. Seventeen slash commands, the same words in both surfaces. → [window](../user-guide/window.md) |
| **Context meter** | `6.1k / 200k` at the left of the composer. Past 0.9 of the window the conversation rolls over: the leg is archived whole and the new one opens with a digest. → [window](../user-guide/window.md) |
| **Model chip** | `Qwen3.8-Flash-Next · high (default)` — the model that is up and this chat's reasoning level, in one chip. Click it to switch models or providers. → [reasoning levels](../reference/reasoning-levels.md) · [remote models](../user-guide/remote-models.md) |
| **Approvals** | the mode chip, coloured by level: `manual` white, `allowedit` green, `auto` gold, `yolo` the alarm red. `auto` asks nothing, `allowedit` asks before executing, `manual` before writing and executing; `yolo` asks for nothing **and means it** -- outside paths and `git_commit` included. `git_push` asks at **every** level. → [tools](../reference/tools.md) |
| **Working directory** | the chip beside the approvals one — `crow` in the shot, `no folder` when there is none. Pick a folder there, or right-click the rail and make a project: a project **is** a working directory. It is the boundary every writer is held to, the repository the git panel reads, and where this chat's memory and goal live. → [memory](../user-guide/memory.md) · [settings](../reference/settings.md) |
| **Dropping files** | drop a file and its path lands in the composer for the model to `read_file`; drop an image and it becomes a chip that rides the next line. → [window](../user-guide/window.md) |
| **Trace** | one line per round, folded. Open it to see what the model actually did. **Thought** is its own fold, labelled with the share of the turn it took. → [window](../user-guide/window.md) |
| **CODE panel** | on the right: every tool call with its `arguments` and its `result`, and under them the source `write_file` and `edit_file` produced, by path, with a `copy` per block. → [window](../user-guide/window.md) |
| **Goal panel** | the plan the model wrote for itself: `3/3` steps, wall clock, tokens, delegated tokens. It outlives a rollover and a restart, and `done` has to hold up: `/goal title \| step \| check: <command>` makes a command the acceptance test. → [goals and subagents](../user-guide/goals-and-subagents.md) |
| **Subagents** | `delegate` hands a task to a second model and returns at once; the turn keeps streaming. `collect` fetches the results. Each one is a card in the pinned **Subtasks** card beside goal and git. Never on this machine's slot. → [goals and subagents](../user-guide/goals-and-subagents.md) |
| **Browser panel** | the globe in the title bar. Tabs, an address bar, per-tab history — a real web view, not an iframe, so claude.ai and github.com load. On Linux it lives inside Crow's window with its own profile, a memory kill and a sandbox; links in answers open there. → [browser](../user-guide/browser.md) |
| **Voice** | the microphone beside the arrow. Recorded and transcribed locally; nothing reaches the disk. → [window](../user-guide/window.md) |
| **Themes** | dark, light and crow. `Help → Settings → Appearance`. → [settings](../reference/settings.md) |
| **Images** | paste a screenshot (Ctrl+V) or `/image <path>`. They ride the next line, stay in the transcript and survive a restart; the model opens one itself with `read_image`. → [tools](../reference/tools.md) |

<div align="center">
<img src="../images/CrowToolCallsAndTraceInChat.png" alt="A web_search turn: the Trace, the folded Thought, the answer, and two tool calls in the panel" width="820">
<br><br>
<img src="../images/CrowModelLocal.png" alt="Settings, Model page: this machine, OpenRouter, Anthropic and OpenAI as providers" width="820">
</div>

## Features

| | |
|---|---|
| [**Tools**](../reference/tools.md) | 28 built in, plus every MCP server you add |
| [**Memory**](../user-guide/memory.md) | two plain-text stores, per project and per person; the model writes its own notes, the background review asks first |
| [**Skills**](../user-guide/skills.md) | procedures the model keeps and rewrites; name and description in the prompt, body on request |
| [**Voxel kit**](../user-guide/voxel-kit.md) | path-traced voxel dioramas (three-gpu-pathtracer, vendored) as one offline page; opt-in with `--pathtracer` / `-PathTracer` |
| [**Goals**](../user-guide/goals-and-subagents.md) | a plan in the pinned head, the state in a file — it survives a rollover and a restart |
| [**Subagents**](../user-guide/goals-and-subagents.md) | `delegate` / `subtasks` / `collect`, up to 16 at once, on a remote spot |
| [**Browser panel**](../user-guide/browser.md) | tabs and an address bar in the window, and `render_page` for the model |
| [**Vision**](../reference/tools.md) | `read_image` — the model looks at a screenshot, a render or a diagram |
| [**Session search**](../user-guide/session-search.md) | SQLite FTS5 over every archived conversation; the real messages, not a summary |
| [**MCP**](../user-guide/mcp.md) | stdio and [Streamable HTTP](../user-guide/mcp-http.md), with OAuth, elicitation and per-tool classes |
| [**Remote models**](../user-guide/remote-models.md) | OpenRouter, Anthropic, OpenAI — key or sign-in. The default is always this machine |
| [**Phone**](../user-guide/remote.md) | `/remote`: the window on a paired phone — LAN, or HTTPS from anywhere [via Tailscale](../user-guide/remote-tailscale.md), phone 🎤 included. Tailscale: [download](https://tailscale.com/download) · [iPhone](https://apps.apple.com/app/tailscale/id1470499037) · [Android](https://play.google.com/store/apps/details?id=com.tailscale.ipn) · setup steps: `install.sh --tailscale` / `install.ps1 -Tailscale` |
| [**Voice**](../user-guide/window.md) | dictation into the composer, `faster-whisper` locally, nothing written to disk |
| [**Secrets**](../reference/settings.md) | a file with an ACL instead of an environment variable every child process inherits |

## Tools

28 built in. `/tools` lists them in either surface; the full reference is
[docs/reference/tools.md](../reference/tools.md).

| group | |
|---|---|
| **Files** | `read_file` a file or a line range · `write_file` a whole file (an existing file must have been read in this conversation and be unchanged since) · `append_file` only for a file above `write_file`'s size limit · `edit_file` one exact occurrence · `list_dir` · `find_files` by glob · `search_text` by regex. A write says its byte count and sha256 as read back, and a `.js` or HTML write carries `node --check`'s first error when node is installed |
| **Shell** | `run_command` — named shell, timeout, and a path outside the working directory asks first; on Linux in a memory-bounded scope of its own (8 GiB) · `build_bundle` — a page and its ES modules as one offline file, with the esbuild already on the machine |
| **Git** | `git_status` · `git_diff` · `git_log` · `git_commit` (stages exactly the paths given) · `git_push` · `github_connect` over the OAuth device flow |
| **Web** | `web_search` — answer from what you read, a list of links is not an answer · `fetch_url` one page as readable text · a host nobody named in the chat is refused |
| **Browser** | `render_page` opens a page in a browser Crow owns and brings back a screenshot plus the console |
| **Vision** | `read_image` — check your own work when a step says it has to look right · `judge` — a separate model that never saw the conversation checks the capture against the step's frozen checklist, yes/no/unknown (#266, #295) |
| **Memory** | `memory` add, replace, remove · `skill` read, save, remove · `session_search` over every past chat, archives and rollover segments included |
| **Goals** | `goal_set` writes the plan · `goal_step` moves one step, and costs no prefill. A `done` whose note says it is not done is refused, and a `check:` you set must pass before the goal closes. A failing step is never skipped by the engine: it reflects, retries in a fresh context, splits, then pauses and asks you; only `/goal skip <n>` skips |
| **Subagents** | `delegate` hands a task out · `subtasks` where they stand · `collect` waits and returns |

Every MCP tool joins the same list as `mcp_<server>_<tool>`, with its own class.

## Operating points

| | model | decode | port | engine |
|---|---|---|---|---|
| **Default, Windows** | `Qwen3.8-Flash-Next-UD-Q2_K_XL` | **41.76 tok/s** | 8083 | llama.cpp, local build |
| **Default, Linux** | `Qwen3.8-Flash-Next-UD-Q2_K_XL` | **41.8 tok/s** | 8083 | llama.cpp, built here |
| Second | `Qwen3.8-27B-UD-Q4_K_XL` | 123.05 / 133.18 tok/s | 8082 | llama.cpp, packaged |
| Third (Rust) | `CNQ4.5-M` NVFP4 container | **45.1 tok/s** (Windows) · 36.8 tok/s at 16k context (Linux) | 8099 | crow-nest `v0.3.0`, Windows and Linux |

Placements, conditions, the engine patches and the by-hand server lines:
**[operating points](../operating-points.md)**. Source of truth:
[`manifests/operating-point.json`](../../manifests/operating-point.json), held against every written
copy by [`tools/check_operating_point.py`](../../tools/check_operating_point.py).

## Documentation

Everything is under [`docs/`](../README.md).

| | |
|---|---|
| **User guide** | [Install](../user-guide/install.md) · [Window](../user-guide/window.md) · [Linux](../user-guide/linux.md) · [Memory](../user-guide/memory.md) · [Skills](../user-guide/skills.md) · [Voxel kit](../user-guide/voxel-kit.md) · [Goals and subagents](../user-guide/goals-and-subagents.md) · [Browser](../user-guide/browser.md) · [Session search](../user-guide/session-search.md) · [MCP servers](../user-guide/mcp.md) · [MCP over HTTP](../user-guide/mcp-http.md) · [Remote models](../user-guide/remote-models.md) · [Phone](../user-guide/remote.md) · [Phone over Tailscale](../user-guide/remote-tailscale.md) |
| **Reference** | [Tools](../reference/tools.md) · [Server flags](../reference/server-flags.md) · [Client flags](../reference/client-flags.md) · [Reasoning levels](../reference/reasoning-levels.md) · [Settings](../reference/settings.md) · [mcp.json](../reference/mcp-json.md) |
| **Operating points** | [The four lines](../operating-points.md) · [Measurements](../measurements/README.md) · [Placement sweep](../measurements/flash-next-placement.md) · [MCP cost](../measurements/mcp-cost.md) |
| **Developer guide** | [Architecture](../developer-guide/architecture.md) · [Testing](../developer-guide/testing.md) · [Repo](../developer-guide/repo.md) · [Not built](../developer-guide/not-built.md) |
| **Plans** | [Crow on Linux](../plans/linux-implementation-plan.md) |
| **Earlier READMEs** | [v0.5.1, Qwen-first](../archive/README-v0.5.1-qwen.md) · [v0.5.1, the one before it](../archive/README-v0.5.1-deepseek.md) |

## Licence

MIT. See [LICENSE](../../LICENSE).

Model: [Qwen](https://huggingface.co/Qwen/Qwen3.8-27B) (Apache-2.0). Quantisation by
[Unsloth](https://huggingface.co/unsloth). Engine:
[llama.cpp](https://github.com/ggml-org/llama.cpp). The optional third model,
Qwen3.8-Flash-Next, is licensed qwen-community-1.0 — read it before redistributing;
Crow does not ship the weights.

<div align="center">
<a href="https://ko-fi.com/nibor1896"><img src="https://img.shields.io/badge/support%20this%20on-ko--fi-ff5e5b?style=for-the-badge" alt="Ko-fi"></a>
</div>
