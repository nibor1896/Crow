[← README](../../README.md) · [Docs index](../README.md)

# Settings

**Settings** at the foot of the window's chat rail (#382).

| pane | |
|---|---|
| **Dashboard** | the first page (#406): the activity grid of the last 12 months, the tokens of the last 30 days, the streak, the active days and the tokens per model, as on the first start of the day, plus the switch "Show the dashboard on the first start of each day". See [Dashboard](#dashboard-406) |
| **Appearance** | theme: dark, light, crow |
| **Skills** | one row per skill, name and description, a switch. Off takes it out of the prompt; the file stays. Switching re-pins the open chat and says what the prefill costs |
| **Server** | connection state, the base URL as its title, and the tool-call switch |
| **MCPs** | one row per server, folded; per tool a switch and its class. Add with a command line, `ask again`, `remove`. See [MCP servers](../user-guide/mcp.md) |
| **Model** | provider and model, two folds. Picking a provider empties the chat. See [Remote models](../user-guide/remote-models.md) |
| **OpenRouter** | the broker on its own page, and the page routes no turn: the operation switch parks or runs delegation, the three delegate favourites and the model pick configure it. Turns stay local until a provider is picked on the Model page |
| **Subscriptions** | one tile, Claude (#390): the Claude Code version, whether `claude auth status` says you are signed in and with what, and the variables that would refuse a turn. You sign in with `claude auth login` in a terminal (copy button) and press `ask again`; Crow opens no browser and keeps no token. No OpenAI tile for now. See [Remote models](../user-guide/remote-models.md#claude-subscription) |
| **API Keys** | one key per provider. Stored in `provider_keys.json`, shown as a mask afterwards |
| **About** | version, the release check, and the button that installs it. A restart is needed afterwards |

Chat rail: right-click a chat to rename, move to a project, archive or delete; right-click the empty
space for a new chat or a new project. A project **is** a working directory. A chat belongs to one
when its `crow_root` points there, and nothing else records it.

---

## #145/#148/#154 — budgets, favourites, digest

| key | default | what |
|---|---|---|
| `turn_token_budget` | `0` (off) | decoded tokens one window turn may spend; spent forces the answer, same protocol as the round budget |
| `subtask_max_tokens` | `0` (= `REMOTE_MAX_TOKENS`, which is the output cap `MAX_TOKENS`: 16384 unless `CROW_MAX_TOKENS` sets it; 8192 before 6301e0e, 2026-09-20) | output cap per delegated subtask; nonsense clamps to the default, never to unlimited |
| `rollover_digest_tokens` | `400` | cap for the model's own digest in the rollover note, asked on the still-warm prefix before the cut; the leg sends at least 2000 (#205), and an answer cut off at the cap is marked as cut (#210); `0` switches it off (#154) |
| `context_clear_at` | unset (= `0.65` on the local server, off on a remote provider) | share of the window at which tool results older than the last 5 rounds are replaced by a one-line stub, in batches that free at least 10 % of the window; originals go to `session/cleared/`, one line per batch to `log/crow.log` (#262's log); `0` switches it off (#263) |
| `context_clear_inputs` | unset (= on with the local server, off on a remote provider) | in the same batch as `context_clear_at`, the bodies the model wrote itself become a one-line stub too: `write_file` and `append_file` `content`, `edit_file` `old` and `new`, older than the last 5 rounds, 600 chars or more; the argument names stay, the last 5 rounds stay whole, the originals go to the same `session/cleared/` file (`"calls"`), and the batch's `crow.log` line names both counts; a file whose body was cleared must be read again before the next write; read every turn, no restart; `0` switches it off, `1` switches it on for a remote provider too; with `context_clear_at` off there is no batch (#359) |
| `bundler` | unset | path to the esbuild `build_bundle` uses before its own search (project `node_modules`, `PATH`, deno/npx caches); read every turn, no restart; it still has to answer `--version`. The way to name one the search skips on purpose, e.g. another program's `node_modules`. The terminal's twin is `--bundler PATH` (#274) |
| `syntax_checks` | unset (= built-in: `node --check` for `.js .mjs .cjs` and inline HTML scripts) | extension → argv run after `write_file`, `append_file` and `edit_file`; `{path}` is the file (appended when absent), exit 0 is ok. `{".py": ["python3", "-m", "py_compile", "{path}"]}` adds Python; `{".html": []}` switches a built-in off. Malformed rows are dropped one by one (#269) |
| `remote_enabled` | `false` | the phone mirror (`/remote`) starts with the window; set by `/remote on` and the phone icon, cleared by `/remote off` (#249) |
| `remote_port` | `8765` | the mirror's fixed port — fixed so a paired phone keeps its origin across restarts; values outside 1024–65535 fall back to the default (#249). `install.sh --tailscale` / `install.ps1 -Tailscale` read it for the printed `tailscale serve … http://127.0.0.1:<remote_port>` line |
| `remote_host` | unset (= the first LAN address `crow_platform` ranks) | the LAN address picked in the QR dialog; never `0.0.0.0` (#249) |
| `remote_https` | `false` | the QR dialog shows the Tailscale HTTPS address (`https://<pc>.<tailnet>.ts.net/`) instead of the LAN one; the LAN address listens either way. Set by the dialog's network switch. See [Phone over Tailscale](../user-guide/remote-tailscale.md) (#249 stage 5) |

## #294 — goal step budget

| key | default | what |
|---|---|---|
| `goal_step_minutes` | `60` | active wall clock one goal step may run before the goal pauses and asks (the clock stops while paused; a typed line gives the step a new budget). `CROW_GOAL_STEP_MINUTES` overrides it; `0` switches it off |
| `goal_no_progress_turns` | `10` | nudges on a step with a frozen checklist and no item newly passed before the goal pauses and asks. `CROW_GOAL_NO_PROGRESS_TURNS` overrides it; `0` switches it off |

Both are read every turn, like the budgets above. See [goals](../user-guide/goals-and-subagents.md#a-failure-has-a-class-and-a-ladder-and-the-end-of-every-ladder-is-a-pause-294).

The delegate favourites live in `providers.json` (`delegate_favorites`), not here — set them
from the OpenRouter page of the settings sheet. So does the judge's pin (#266):
`"judge": {"provider": "openrouter", "model": "<a vision model>"}`, or `{"provider": "local"}`.

---

## Dashboard (#406)

The first page of the sheet, and the view the window opens on at the first start of each day. See
[Window](../user-guide/window.md). A day starts at 04:00, so a turn at 01:30 belongs to the day before.

| key | default | what |
|---|---|---|
| `dashboard_daily` | `true` | show the dashboard on the first start of each day. The Dashboard page's switch writes it; `false` starts the window as before |
| `dashboard_seen` | unset | `"YYYY-MM-DD"`, the last day the dashboard was shown. Written when it is shown. It comes up at start when `dashboard_daily` is on and this is not today's day, so setting it to yesterday brings it back at the next start |

Both live in `settings.json` (`%LOCALAPPDATA%\Crow\` on Windows, `~/.config/crow/` on Linux) and are read at start.

### The ledger, `usage.jsonl`

| | |
|---|---|
| path | `%LOCALAPPDATA%\Crow\usage.jsonl` on Windows, `~/.local/state/crow/usage.jsonl` on Linux (`$XDG_STATE_HOME/crow/`), beside `session/` |
| written | one line per finished turn, appended when the turn ends, for local, OpenRouter and Claude (subscription) turns alike. A line that cannot be written is skipped and the turn does not notice |
| one file | for all chats, so archiving, moving or deleting a chat does not change the history |
| read | the dashboard reads the whole file; a damaged line is skipped and costs that one record |
| from when | this build on. Older chats are not backfilled: their saved `timings` carry no date and no model per turn |
| local | recorded on this machine only; nothing is sent anywhere |
| size | estimated at about 250 bytes a turn, 5 MB for 20,000 turns; not measured |

A line is one JSON object (shortened):

```json
{"v": 1, "ts": "2026-10-18T09:12:44+02:00", "day": "2026-10-18", "model": "Qwen3.8-27B", "input": 182340, "output": 1611, "rounds": 6}
```

| field | |
|---|---|
| `v` | `1`, the line format |
| `ts` | when the turn ended: local time with its UTC offset |
| `day` | the usage day, `YYYY-MM-DD`: the local date, with the day starting at 04:00. The grid and the streak count by it |
| `model` | the model name the turn was served by; the dashboard's per-model table groups by it |
| `input` | tokens the model read, summed over the turn's rounds: per round the prompt tokens plus the cached ones |
| `output` | tokens the model wrote |
| the turn's figures | those the chat file's `timings` keep (`clean_timings`): `rounds`, `decoded`, `prefilled`, `tool_calls`, `tool_errors`, `tool_declined`, `cached`, `cached_of`, `decode_s`, `prefill_s`, `model_s`, `tool_s`, `waited_s`, `decode_rate`, `prefill_rate`, `finish`, `seeds`, `leg_seeds`. A figure the turn did not have is absent |

The dashboard's tokens are `input` + `output`.

---

## The secret store (#193)

A key in an environment variable is inherited by every child process and printed by every tool
that dumps `Env:`. Measured 2026-09-10: a measurement runner in another repository printed its
shell environment into a log, and `CROW_TAVILY_KEY` went into the log with it. So the value
lives in a file instead.

| | |
|---|---|
| path | `%LOCALAPPDATA%\Crow\secrets.json` on Windows, `~/.config/crow/secrets.json` on Linux — beside `approvals.json` and the rest of what you configured |
| shape | a flat `{"NAME": "value"}` object, read as `utf-8-sig` so a BOM from Notepad or PowerShell 5.1 does not make it unreadable |
| order | the store first, the environment second. An entry that is present but **empty** counts as not set |
| the environment still works | and says so once, on a console, naming the file to move the value into. Every installation that exists today has the variable and no file |
| what is in it today | `CROW_TAVILY_KEY`, the general web index for `web_search`, and `remote_devices` (#249): the paired phones as `{id, name, created, last_seen, token_sha256}`, only the hash of each cookie. `CROW_SEARXNG_URL` is a URL, not a secret, and stays an environment variable |
| writing it | `powershell -ExecutionPolicy Bypass -File tools\migrate-secrets.ps1 -Names CROW_TAVILY_KEY` — it writes the file, sets the ACL and takes the variable out of the user scope |
| writing it on Linux | by hand: `{"CROW_TAVILY_KEY": "..."}` in `~/.config/crow/secrets.json` (`$XDG_CONFIG_HOME/crow/` when that is set). The migration script is Windows-only |
| what the texts say (#194) | `web_search`'s upgrade hint, its refusal and the SearXNG hint name this file by its resolved path first and the environment as the fallback; a refused Tavily key says whether it came from the store or the environment |
| moving it | `CROW_SECRETS_FILE`; the only caller that needs it is a test |

A broken store is reported by **path** and never by content: a parser error that quoted the line
it choked on would print the key it was written to hide. Provider keys and logins are a different
pair of files — see [Remote models](../user-guide/remote-models.md).
