[← README](../README.md)

# Documentation

The [README](../README.md) is the front page: one image, the install lines, and links here.
Everything else is in this folder.

## User guide

| | |
|---|---|
| [Overview](user-guide/overview.md) | start, the window part by part, features, tools, licences: what the front page used to carry |
| [Install](user-guide/install.md) | requirements, both installers, the model download, updating, where everything lands; optional `--voice`, `--tailscale` / `-Tailscale`, `--pathtracer` / `-PathTracer` |
| [Window](user-guide/window.md) | the client, panel by panel: pinned cards, selection and links, layout |
| [Linux](user-guide/linux.md) | install, the paths table, the engine build, memory scopes for server, render and command, optional helpers, the window on Wayland, troubleshooting |
| [Memory](user-guide/memory.md) | what is written, by whom, and the gate |
| [Skills](user-guide/skills.md) | using and writing one |
| [Voxel kit](user-guide/voxel-kit.md) | path-traced voxel dioramas as one offline page: the vendored three-gpu-pathtracer, the voxel API, live/photo modes and animation, props and coverage, `check_diorama.py`, the measured rules, `--pathtracer` / `-PathTracer` |
| [Goals and subagents](user-guide/goals-and-subagents.md) | the plan a model writes for itself, what `done` has to prove, and the tasks it hands out |
| [Browser panel](user-guide/browser.md) | the in-window panel on Linux, tabs, the address bar, `render_page`, what is unverified on Windows |
| [Session search](user-guide/session-search.md) | the index over every archived conversation |
| [MCP servers](user-guide/mcp.md) | stdio, elicitation, commands |
| [MCP over HTTP](user-guide/mcp-http.md) | headers, OAuth, sessions |
| [Remote models](user-guide/remote-models.md) | subscriptions, keys, dialects, routing |
| [Phone (remote)](user-guide/remote.md) | `/remote`, pairing, the two addresses, the phone microphone |
| [Phone over Tailscale](user-guide/remote-tailscale.md) | HTTPS from anywhere: `install.sh --tailscale` / `install.ps1 -Tailscale`, [download](https://tailscale.com/download), [iPhone](https://apps.apple.com/app/tailscale/id1470499037), [Android](https://play.google.com/store/apps/details?id=com.tailscale.ipn), admin console, the one `tailscale serve` line, checks, undo |

## Reference

| | |
|---|---|
| [Tools](reference/tools.md) | the twenty-eight built in, plus MCP |
| [Server flags](reference/server-flags.md) | what the inference server is started with, and why each flag is there |
| [Client flags](reference/client-flags.md) | what `crow` and the window take |
| [Reasoning levels](reference/reasoning-levels.md) | `low`, `medium`, `high`, and the thinking budget |
| [Settings](reference/settings.md) | the settings sheet, `settings.json`, and the secret store |
| [mcp.json](reference/mcp-json.md) | every key, both transports |

## Operating points and measurements

| | |
|---|---|
| [Operating points](operating-points.md) | the four measured lines, the engine patches, and the by-hand server commands |
| [Measurements](measurements/README.md) | every number with the conditions it was taken under |
| [Acceptance: #207](acceptance/issue-207.md) | the live acceptance protocol of the bounded search and capture |
| [Flash-Next placement](measurements/flash-next-placement.md) | the `-ncmoe` / `-ub` sweep, 27 runs |
| [MCP cost](measurements/mcp-cost.md) | what tool declarations cost per request |

Raw rows that belong to the pages above: [`flash-next-placement-runs.csv`](measurements/flash-next-placement-runs.csv)
· [`qwen4exp-depth-407.csv`](measurements/qwen4exp-depth-407.csv).

## Developer guide

| | |
|---|---|
| [Architecture](developer-guide/architecture.md) | the four modules and the core/surface split |
| [Testing](developer-guide/testing.md) | the suites, the checkers, the manifests |
| [Repo](developer-guide/repo.md) | layout |
| [Not built](developer-guide/not-built.md) | decided against, and why |

## Plans

| | |
|---|---|
| [Crow on Linux](plans/linux-implementation-plan.md) | the plan the 2.2.0 port was built from, with its deviations recorded |

## Archive

Kept for the measurements in them. None is current, and no checker holds them to the manifest.

| | |
|---|---|
| [README v2.7.0](archive/README-v2.7.0.md) | the last text front page, before the image README |
| [README v0.5.1, Qwen-first](archive/README-v0.5.1-qwen.md) | the page as it stood when Qwen3.8-27B was the operating point |
| [README v0.5.1, the one before it](archive/README-v0.5.1-deepseek.md) | the DeepSeek-0731 page |
