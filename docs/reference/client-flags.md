[← README](../../README.md) · [Docs index](../README.md)

## Client flags

| flag | default | |
|---|---|---|
| `--base-url` | `http://127.0.0.1:8083/v1` | Flash-Next's port, the default since 2.0.0. The 27B listens on `:8082`, 0731 on `:8081` |
| `--reasoning-effort`, `--reasoning-budget N` | no flag in the window | per chat via `/reasoning` and `/budget`: [reasoning levels](reasoning-levels.md) |
| `--rollover-digest-tokens N`, `--context-clear-at SHARE` | no flag in the window | the settings `rollover_digest_tokens` and `context_clear_at`: [settings](settings.md#145148154--budgets-favourites-digest) |
| `--turn-token-budget N`, `--subtask-max-tokens N`, `--bundler PATH` | no flag in the window | the settings `turn_token_budget`, `subtask_max_tokens` and `bundler`: [settings](settings.md#145148154--budgets-favourites-digest) |
| `-m`, `--model NAME` | `crow` | the model name in the request body, sent with `--base-url` and `--api-key` (`provider_endpoint`) |
| `--api-key KEY` | `local-no-provider` | the key sent with `--base-url` and `--model` |
| `--mode` | `auto` | `manual` asks before writing and executing, `allowedit` before executing, `yolo` asks for nothing and means it -- outside paths and git commit included; `git_push` still asks, and the level never outlives the process |
| `--no-review` | off | stop the model saving memories and skills after a turn |
| `--no-memory-approval` | off | let the review write to memory without asking. **The gate is on by default** |
| `--no-session` | off | do not resume the last session, do not save this one |
| `--tools` | on | run tool calls |
| `--no-tools` | off | show tool calls instead of running them |
| `--root DIR` | unset | the folder tool writes are confined to; states it and creates it (`.crow/root.json`). In the window it also binds the restored chat and becomes the folder the next start opens, as a pick in the chip does (#303, [window](../user-guide/window.md)) |
| `--language NAME` | `$CROW_LANGUAGE`, else unset | pin the language of the model's replies, e.g. `--language English`. Unset keeps the rule "reply in the language the user wrote in", which the FIRST message decides: a chat opened with "Hey" was answered in German and stayed German through an English task (2026-09-19, both engines). It replaces that sentence in the system prompt, so a session resumed under another language pays one full prefill |
| temperature / top_p / min_p | `1.0` / `0.95` / `0.01` | the floor, written once in `cli/crow_core.py`. The manifest's shared block and the served model's entry override it: the two Qwen3.8-Flash-Next points send `min_p` 0.0, `top_k` 20, `presence_penalty` 0.0 ([thinking and sampling](../operating-points.md#thinking-and-sampling-per-point)) |
| output cap | `16384` | `max_tokens` on every request, local and remote (`MAX_TOKENS`). No flag: `CROW_MAX_TOKENS` sets it once per process. It also sets how large a file one `write_file` carries ([tools](tools.md#write_file-and-append_file-244-251-252-254)) |
| goal step budget | `60` min, `10` nudges | the window's goal engine. No flag: `CROW_GOAL_STEP_MINUTES` and `CROW_GOAL_NO_PROGRESS_TURNS` override the `goal_step_minutes` / `goal_no_progress_turns` settings; `0` switches one off ([settings](settings.md#294--goal-step-budget), #294) |
| window rendering (Windows) | WebView2 without the GPU | no flag: the window and the operating-point window set `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--disable-gpu --disable-gpu-compositing` before they open, so the page does not share the card with the local engine (GLM-5.3-Flash: 7.6-7.9 tok/s decode without, 14.17 with, 2026-10-11, #368). A value already in the environment is kept. `render_page`'s own browser does not get it; it keeps its own GPU flags ([tools](tools.md)). Linux is unchanged |

The retry cap needs no flag: the fourth identical failing call to an uncached tool is refused
before it runs, always.
