[← README](../../README.md) · [Docs index](../README.md)

# Overview

What used to stand on the front page: how to start Crow, the window part by part, the feature
list, the tools, and the licences. Install: [install guide](install.md).

## Start

Two terminals: the engine first, then the window.

**Default: crow-nest** (from the crow-nest repo root)

```bash
cd ~/Projects/crow-nest && tools/serve-linux.sh --port 8099
crow --base-url http://127.0.0.1:8099/v1
```

```powershell
engine\target\release\serve.exe --port 8099
python $env:LOCALAPPDATA\Crow\cli\crow_gui.py --base-url http://127.0.0.1:8099/v1
```

**Second: llama.cpp, Linux**

```bash
python3 ~/.local/share/crow/tools/start-server.py flash-next-q2-k-xl
```

```bash
crow
```

**Second: llama.cpp, Windows**

```powershell
python $env:LOCALAPPDATA\Crow\cli\crow.py --serve flash-next-q2-k-xl
```

```powershell
python $env:LOCALAPPDATA\Crow\cli\crow_gui.py
```

The window is the client. On the llama.cpp lines it reads the port off the running server, and
the model menu can switch and reboot it from there. The by-hand `llama-server` lines, flag for flag, live in
[operating points](../operating-points.md).

## How to use Crow

Screenshots: [window](window.md) · [goals and subagents](goals-and-subagents.md) · [remote models](remote-models.md).

| | |
|---|---|
| **Chats sidebar** | chats grouped by project, archive at the foot, fold state remembered. A delegated subtask hangs under its chat as a `⑂` row. → [window](window.md) |
| **Composer** | type, or `/tools` for what the model can call. Seventeen slash commands, the same words in both surfaces. → [window](window.md) |
| **Context meter** | `6.1k / 200k` at the left of the composer. Past 0.9 of the window the conversation rolls over: the leg is archived whole and the new one opens with a digest. → [window](window.md) |
| **Model chip** | `Qwen3.8-Flash-Next · high (default)` — the model that is up and this chat's reasoning level, in one chip. Click it to switch models or providers. → [reasoning levels](../reference/reasoning-levels.md) · [remote models](remote-models.md) |
| **Approvals** | the mode chip, coloured by level: `manual` white, `allowedit` green, `auto` gold, `yolo` the alarm red. `auto` asks nothing, `allowedit` asks before executing, `manual` before writing and executing; `yolo` asks for nothing **and means it** -- outside paths and `git_commit` included. `git_push` asks at **every** level. → [tools](../reference/tools.md) |
| **Working directory** | the chip beside the approvals one — `crow` in the shot, `no folder` when there is none. Pick a folder there, or right-click the rail and make a project: a project **is** a working directory. It is the boundary every writer is held to, the repository the git panel reads, and where this chat's memory and goal live. → [memory](memory.md) · [settings](../reference/settings.md) |
| **Dropping files** | drop a file and its path lands in the composer for the model to `read_file`; drop an image and it becomes a chip that rides the next line. → [window](window.md) |
| **Trace** | one line per round, folded. Open it to see what the model actually did. **Thought** is its own fold, labelled with the share of the turn it took. → [window](window.md) |
| **CODE panel** | on the right: every tool call with its `arguments` and its `result`, and under them the source `write_file` and `edit_file` produced, by path, with a `copy` per block. → [window](window.md) |
| **Goal panel** | the plan the model wrote for itself: `3/3` steps, wall clock, tokens, delegated tokens. It outlives a rollover and a restart, and `done` has to hold up: `/goal title \| step \| check: <command>` makes a command the acceptance test. → [goals and subagents](goals-and-subagents.md) |
| **Subagents** | `delegate` hands a task to a second model and returns at once; the turn keeps streaming. `collect` fetches the results. Each one is a card in the pinned **Subtasks** card beside goal and git. Never on this machine's slot. → [goals and subagents](goals-and-subagents.md) |
| **Browser panel** | the globe in the title bar. Tabs, an address bar, per-tab history — a real web view, not an iframe, so claude.ai and github.com load. On Linux it lives inside Crow's window with its own profile, a memory kill and a sandbox; links in answers open there. → [browser](browser.md) |
| **Voice** | the microphone beside the arrow. Recorded and transcribed locally; nothing reaches the disk. → [window](window.md) |
| **Themes** | dark, light and crow. `Help → Settings → Appearance`. → [settings](../reference/settings.md) |
| **Images** | paste a screenshot (Ctrl+V) or `/image <path>`. They ride the next line, stay in the transcript and survive a restart; the model opens one itself with `read_image`. → [tools](../reference/tools.md) |

## Features

| | |
|---|---|
| [**Tools**](../reference/tools.md) | 28 built in, plus every MCP server you add |
| [**Memory**](memory.md) | two plain-text stores, per project and per person; the model writes its own notes, the background review asks first |
| [**Skills**](skills.md) | procedures the model keeps and rewrites; name and description in the prompt, body on request |
| [**Voxel kit**](voxel-kit.md) | path-traced voxel dioramas (three-gpu-pathtracer, vendored) as one offline page; opt-in with `--pathtracer` / `-PathTracer` |
| [**Goals**](goals-and-subagents.md) | a plan in the pinned head, the state in a file — it survives a rollover and a restart |
| [**Subagents**](goals-and-subagents.md) | `delegate` / `subtasks` / `collect`, up to 16 at once, on a remote spot |
| [**Browser panel**](browser.md) | tabs and an address bar in the window, and `render_page` for the model |
| [**Vision**](../reference/tools.md) | `read_image` — the model looks at a screenshot, a render or a diagram |
| [**Session search**](session-search.md) | SQLite FTS5 over every archived conversation; the real messages, not a summary |
| [**MCP**](mcp.md) | stdio and [Streamable HTTP](mcp-http.md), with OAuth, elicitation and per-tool classes |
| [**Remote models**](remote-models.md) | OpenRouter, Anthropic, OpenAI — key or sign-in. The default is always this machine |
| [**Phone**](remote.md) | `/remote`: the window on a paired phone — LAN, or HTTPS from anywhere [via Tailscale](remote-tailscale.md), phone 🎤 included. Tailscale: [download](https://tailscale.com/download) · [iPhone](https://apps.apple.com/app/tailscale/id1470499037) · [Android](https://play.google.com/store/apps/details?id=com.tailscale.ipn) · setup steps: `install.sh --tailscale` / `install.ps1 -Tailscale` |
| [**Voice**](window.md) | dictation into the composer, `faster-whisper` locally, nothing written to disk |
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

## Licence

MIT. See [LICENSE](../../LICENSE).

Default model: [Qwen3.8-Flash-Next as CNQ4.5-M](https://huggingface.co/nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M),
converted from the original safetensors by [crow-nest](https://github.com/nibor1896/crow-nest)
(engine code Apache-2.0), licensed qwen-community-1.0 — read it before redistributing. The GGUF of
the second operating point is quantised by [Unsloth](https://huggingface.co/unsloth) and runs on
[llama.cpp](https://github.com/ggml-org/llama.cpp); the third,
[Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B), is Apache-2.0. Crow does not ship the weights.
