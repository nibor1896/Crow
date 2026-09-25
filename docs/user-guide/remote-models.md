[← README](../../README.md) · [Docs index](../README.md)

# Remote models

`Settings → API Keys`, paste the key, then `Settings → Model`. The catalogue is fetched when the key
lands and on `ask again`. Nothing is asked of a provider while a window opens.

<div align="center">
<img src="../images/CrowAPI.png" alt="Settings, API Keys: one key per provider, shown as a mask once saved" width="900">
</div>

<div align="center">
<img src="../images/CrowModelLocal.png" alt="Settings, Model page: this machine, OpenRouter, Anthropic and OpenAI as providers" width="900">
</div>

A key is kept in its own file that no view reads back — what the box shows afterwards is a mask.

OpenRouter has its own page instead: switch, delegate favourites and model pick. **The page routes
no turn** — its switch runs the broker for delegation while the machine keeps answering, in
parallel. The default is always the machine; turns leave it only through the Model page.

When a delegate spot fails, the error decides the next step: a sick spot (429, 5xx, timeout) and a
spot that will not serve this client (403, "no endpoints found", 402 on a paid favourite) are
skipped for the next one; 401, 402 on a free spot and schema errors stop the chain at once. The
result names every spot tried and why (#216). Full table:
[goals and subagents](goals-and-subagents.md#subagents-143).

Three files, in `%LOCALAPPDATA%\Crow\` on Windows and `~/.config/crow/` on Linux:

| file | |
|---|---|
| `providers.json` | active provider, model per provider, catalogue, favourites, the broker switch |
| `provider_keys.json` | keys, `0600`, read by no view |
| `provider_tokens.json` | logins, `0600`, read by no view |

| provider | endpoint | credential |
|---|---|---|
| This machine | `--base-url`, default `http://127.0.0.1:8083/v1` since 2.0.0 | none |
| OpenRouter | `https://openrouter.ai/api/v1` | `sk-or-...` |
| Anthropic | `https://api.anthropic.com/v1` (Messages) | `sk-ant-...` or a sign-in |
| OpenAI | `https://api.openai.com/v1` | `sk-...` or a sign-in |

| | |
|---|---|
| Typed slug | field beside `ask for the list`, sent exactly as entered. Measured 2026-08-23: Anthropic's `/v1/models` answers a borrowed sign-in `401` |
| Variant suffix | `:free`, `:extended`, `:nitro`, `:floor` are part of the slug. `z-ai/glm-5.2` and `z-ai/glm-5.2:free` are two entries with two bills |

## Subscriptions

`Settings → Subscriptions`, one tile per provider. PKCE, `state`, refresh: the flow `/mcp` uses.
A sign-in outranks a pasted key; `sign out` drops the login and leaves the key.

Measured 2026-08-22, neither provider registers a client:

| | discovery | registration |
|---|---|---|
| `claude.ai`, `api.anthropic.com`, `console.anthropic.com` | 404 | none |
| `auth.openai.com` | `openid-configuration`, authorize + token | none |

Each needs a `client_id`. Until one is set the tile says so instead of opening a login that returns
`400`. Crow ships no other product's `client_id`.

```json
{"oauth": {"anthropic": {"client_id": "...", "authorize": "https://...", "token": "https://..."}}}
```

`issuer` replaces `authorize`/`token` where the provider publishes discovery. `auth.openai.com` does.

**Anthropic, documented way in:**

```bash
claude setup-token
```

Paste what it prints. `CLAUDE_CODE_OAUTH_TOKEN` in the environment is read under the same name.

**Borrowed sign-in, second choice.** Measured 2026-08-23: a borrowed Claude Code session token
authenticated at `/v1/messages` and returned `429` naming no limit, with the account's five-hour
window at 7 %.

| provider | store | read |
|---|---|---|
| Anthropic | `~/.claude/.credentials.json` | `claudeAiOauth.accessToken` |

| borrowed token | |
|---|---|
| Read | at the moment a request needs it |
| Never | copied, written, refreshed. The refresh token belongs to the program that owns the file |
| Expired | reported; open that program once and it refreshes itself |
| Grant | requests carry **that program's** grant, so nothing switches on by finding a file |
| Order | Crow's own sign-in, then borrowed, then pasted key |

**Not Codex.** `~/.codex/auth.json` holds a token; `GET https://api.openai.com/v1/models` answers it
`403`: authenticated, resource refused. It belongs to the ChatGPT backend; the platform API wants
an `sk-...` key. Two providers, not one.

## Two dialects

| transport | endpoint | who |
|---|---|---|
| `chat_completions` | `<base>/chat/completions` | the local server, OpenRouter, OpenAI |
| `anthropic_messages` | `<base>/messages` | Anthropic, key **and** sign-in |

The dialect belongs to the provider, not to the credential. Measured 2026-08-23, a Codex token got
`403` from the OpenAI-shaped endpoint.

What `anthropic_messages` translates, each mandatory:

| | |
|---|---|
| System prompt | moves to the top level |
| Tools | `input_schema` instead of `function` |
| Tool call | `tool_use` blocks with an object `input` |
| Tool results | every result answering one turn batched into **one** user message |
| `max_tokens` | required |
| `temperature`, `top_p`, `top_k` | removed on current models, not sent |
| Stream back | `text_delta` → content, `thinking_delta` → reasoning, `input_json_delta` → tool arguments. One loop, not two |

| credential | header |
|---|---|
| key | `x-api-key` |
| sign-in | `Authorization: Bearer` plus `anthropic-beta: oauth-2025-04-20` |

Never both.

## One answer's ceiling

`max_tokens` travels on a remote request and not on a local one. Measured 2026-08-23, without it
OpenRouter answered:

```
HTTP 402 -- you requested up to 65536 tokens, but can only afford 313
```

A provider reserves and prices the model's maximum output when the body names no cap. llama-server
reserves nothing and bills nobody, and a cap there would cut long answers it is happy to finish.

## Which upstream answers

OpenRouter is a broker: one slug is served by many upstream companies. One field is sent to it and
to nobody else.

| field | | |
|---|---|---|
| `session_id` | sticky routing key | all turns of one chat go to the same upstream |

| | |
|---|---|
| Value | sha256 of the chat's path, never the path. That path names a person and a directory layout |
| Length | 64 characters against a documented limit of 256 |
| Unsaved chat | sends none; an empty string would make every unsaved chat one session |
| Both senders | the visible turn and the background review carry the same key, or the review is a second session inside the first |

**`provider.require_parameters` is sent per model, never per provider.** Sent for everyone once,
measured 2026-08-23:

```
HTTP 404 -- No endpoints found that can handle the requested parameters
```

| | |
|---|---|
| Default | an upstream that does not know a parameter ignores it, `tools` included, and answers anyway |
| With the flag | ignoring becomes exclusion, so a model keeps the tools it was sent |
| Then | the body carried `timings_per_token`, `chat_template_kwargs` and `min_p`. Every candidate excluded |
| Now | those three stay at home, and the flag rides only where the catalogue says the model takes what is left |
| No claim, no flag | a model the catalogue does not describe is asked for nothing |

| measured 2026-08-23, openrouter.ai, no key needed | |
|---|---|
| models | 422 |
| accept `tools` | 337 |
| accept `tools`, `temperature`, `top_p`, `max_tokens` | 250 |
| accept those and `min_p` | 72 |

The 87 that fall out are the current reasoning models, `claude-opus-5` and `claude-sonnet-5` among
them, and what they are missing is `temperature` or `top_p`, which they refuse rather than lack.
They are asked for no filter and stay usable.

## No slot, no operating point

`SLOT_FILE`, `prefix_fingerprint`, `/props` and every "pays a full prefill" line are llama-server's.
Against a provider none of them exists, and the window says so once, where the endpoint is chosen:

| | local | remote |
|---|---|---|
| context window | `/props`, **measured** | the catalogue's `context_length`, **declared** |
| no window reported | bare token count, no bar | bare token count, no bar |
| KV save and restore | `/slots/0` | not attempted; the session file says `kv: false` |
| `/health`, `/props` | asked | not asked |
| reasoning levels | per `manifests/` | none offered |
| prompt cache | llama-server's, held by `prefix_fingerprint` | the upstream's. Crow marks nothing for caching; `session_id` keeps the turns of one chat on the same one |

No price display. Whoever brings a key knows their costs.

---
