[← README](../../README.md) · [Docs index](../README.md)

# Window

<div align="center">
<img src="../images/window.png" alt="Crow window: chat rail, the wireframe over an empty chat, and the composer" width="920">
</div>

<div align="center">
<img src="../images/CrowToolCallsAndTraceInChat.png" alt="A web_search turn: the Trace, the folded Thought, the answer, and two tool calls in the panel" width="920">
</div>

| | |
|---|---|
| Composer | model and reasoning level as one chip, context readout, working directory, release level, dictation |
| Cost line | rounds, tokens, decode, prefill, cache hits, tool calls, wall clock |
| Thought blocks | folded, one per re-entry, each labelled with the turn's thinking share |
| Answers | headings, lists, tables, bold, italic, inline code and links, drawn when the turn ends |
| Links and paths | http(s) URLs and file paths (POSIX and Windows, with `:line` or `:line:col`) are marked in answers, inline code and tool results. A click on a link opens it in the browser panel. `_` inside a word or a URL is no longer emphasis (CommonMark 6.2) (#229) |
| Selecting and copying | content text selects and copies; controls do not. WebKitGTK 2.52 ignores the unprefixed `user-select`, and pywebview's `text_select=False` had injected `body{-webkit-user-select:none}`, so on Linux nothing could be selected before #228. Ctrl+C copies the selection (also through Python's clipboard path); on a focused link or path with nothing selected it copies the target |
| Right-click on content | a menu built from what is under the pointer: `Copy` (a selection), `Open in Crow's browser` / `Open in system browser` / `Copy link` (a link), `Copy path`, `Copy path:line[:col]`, `Show in file manager`, and for an `.html`/`.htm`/`.svg` path `Open in Crow's browser` (a path). Never "open with the default program". Up/Down/Home/End move, Escape closes (#228, #229). The rail keeps its own menu |
| Rail | chats grouped by project, archive, fold state remembered |
| Phone | the phone icon in the title bar, or `/remote`: the window mirrored to a paired phone, on the LAN or over HTTPS via Tailscale (#249, #290) — see [Phone](remote.md) |
| Code panel | on the right, mirrored from the rail: dragged between 260 and 720, folded from the title bar, width and state remembered. Starts at half the space beside the rail until somebody drags it once |
| Tool calls | top of the panel, one fold for the group and one per call. Open a call for its `arguments` and, under them, its `result` — 4,000 characters, the remainder counted. A failed call is marked on its head |
| Program code | under the calls, from `write_file` and `edit_file` only. Its own fold with a count, like the calls above it. The head of each block is the **path**, the body the content — no JSON envelope. Readable while it is being written; the envelope is replaced once the arguments are whole |
| `copy` per block | in the head of every code block, beside the path — it copies **that** block. The panel head has no `copy`: one button for calls and source together copied both to whoever wanted one of them (#156) |
| Chat column | chat and composer are one column: your messages stand on the right, their bubble's right edge on the input box's right border; Crow's answers, thoughts and notes start on the box's left border, with no mark column in front (#280). Column and box are computed from the same CSS variables (`--colw` 900 px, `--colpad`, `--sbw`, `--reserve`), so they cannot drift apart with or without the pinned cards. Measured 2026-09-24, headless Chromium, rail open/shut × 1180/1440/1920/2560 × 900 × no card/git/goal/subtasks (32): short bubble right edge 716–780 px left of the box's right edge and answer text 40 px right of its left edge before, 0.0 px in all 32 after. The rounds inside an opened Trace keep their indent. WebKitGTK not measured |
| Pinned cards | the goal, **Subtasks** and git cards stand in one column at the top right of the chat, in that order, and do not scroll with the transcript (#164, #255). Each is hidden while it has nothing to show. From 1,100 px of chat width, while any of them stands, the chat column and the composer reserve the card width (306 px) on **both** sides, so the text never runs under a card and column and composer stay on the window's centre (#233, #256). Measured 2026-09-23, headless Chromium, 32 combinations of rail/code/git and 1180/1440/1920/2560 × 900: composer centre minus window centre −158.0 px with a card and −5.0 px without it before #256, 0.0 in all 32 after. The column only narrows where 960 + 2 × 316 px does not fit (chat area under about 1,612 px). Below 1,100 px the cards float over the column as before (#233 open for that range). WebKitGTK not measured |
| Git panel | one of the pinned cards, under the goal and subtask cards — one flex column, so a card that appears or goes moves the others without a line of JavaScript. Toggled by the octocat in the title bar, still the only way to close it (#156, #173) |
| Goal panel | the first pinned card: title, `done/total`, wall clock, tokens, delegated tokens, one row per step. It survives a rollover and a restart — see [goals and subagents](goals-and-subagents.md) (#161–#165). Goal mode stops itself and writes a note into the flow when a step has taken 25 turns, when the whole goal has taken 60, or when three identical or empty answers say the model is looping — the looping turns leave the history and one recovery line goes out in their place (#202); how many messages left is written to `crow.log`, not the flow (see *Crow log*). A `done` whose own note says it is not done is refused, and a user's `check:` command must pass before the goal closes (#250) |
| Browser panel | a globe in the title bar, beside code and git. Tabs, an address bar, per-tab history. Not an iframe. On Linux it is a second WebKitWebView inside the window (#201). On Windows it is a second frameless WebView2 over the panel rect. Folded, it holds no page, and a render does not unfold it; during a turn on the local model it renders without the GPU (#279). See [browser](browser.md) (#175) |
| `clear all` | empties both halves and stays empty across a restart. The group's own `clear` takes the calls only |
| Code blocks | language, line count and `copy`. Fifteen lines or more can be folded away. A finished `write_file`/`edit_file` block keeps its `copy` button when its path is written into the head (#239) |
| Images | drop `.png .jpg .jpeg .gif .webp .bmp` into the window, paste a screenshot (Ctrl+V), or `/image <path>`: a chip per image above the input, `×` removes one. They ride the next line, appear in the transcript, and are still there after a restart. Needs a server started with `--mmproj` — one without it refuses with a sentence before anything is sent. The bytes travel unresized; the server caps an image at 4,096 tokens (`--image-max-tokens`). Any other dropped file keeps the old behaviour: its path lands in the input for the model to `read_file`. The model opens one itself with [`read_image`](../reference/tools.md) (#170) |
| Delegation | a subtask is a card in the pinned **Subtasks** card beside the goal and git cards — spot, state, token count. The head reads `N running · M finished`; running cards on top, finished ones in a folded `finished · N` group. The card is never a block of the scrolling chat (0 px in the flow), a chat switch drops the other chat's cards, and a jump opens the fold and scrolls only the card (#255). Each subtask is also a child row under its root chat in the rail, marked `⑂`. Clicking either jumps to the card; a subtask is never opened as a chat. The `×` in the card's head (same place and style as the goal card's) hides the card for this chat — running subtasks keep running, their rail rows and the `⑂` chip stay — and the column reserve lets go with it; the card comes back when a new subtask starts in that chat or a chip-menu/rail row jumps to a card. The closed mark is kept in the registry, so it survives a restart (#281). Measured 2026-09-24, headless Chromium, 1920×900, git shut, no goal: `#flow`/`#composer` reserve 306 px → 0 px after `×`, composer centre on the window centre (0.0 px) both ways. Cards keep breathing outside a turn, and Stop cancels the subtasks with the turn |
| `/delegate` mid-turn | the delegation pair (`/delegate`, `/subtasks`) passes the Stop gate: typed while a turn runs, the card starts beside it, the turn keeps streaming, and the composer stays on Stop. The Stop button and Escape stop the turn (#143 E3) |
| Typing mid-turn | a plain line + Enter while a turn runs — goal mode included — is **queued**, not a stop: the turn keeps going, the hint reads `queued -- it goes in when this turn ends`, and at the turn's end the line is drawn and runs next, ahead of goal mode's own nudge; it resets the goal's turn caps like any typed line. Two lines queued go in as one message. **No typed line is a stop**: a line that opens with `/` but is not a Crow command (a path) is queued too; while the box holds a line the button reads `↑ Queue` and a click queues it; a Crow command other than the delegation pair (`/model`, `/goal`, `/reset` …) waits in the box until the turn ends and the hint says so. Stop is an empty Enter, the button with an empty box, or Escape (with anything in the box). An Enter that confirms an input-method composition is not a submit (#264, #165) |
| Stop in goal mode | Stop ends the turn **and pauses the goal**: no next turn starts, and the chat says `goal mode paused: you pressed Stop. Step N is open -- the next line you send resumes it.` The next line you send runs and the goal continues after it; a line queued before the Stop runs first (#282) |
| `/verify` | the conversation's own writes go to the checker spot with review instructions; the verdict comes back as a subtask card (#149) |
| OpenRouter page | its own pane in Settings, and it routes no turn: the switch parks or runs the broker — delegation, catalogue, favourites — while the machine keeps answering. The default is always the machine; turns leave it only through the Model page |
| Delegate favourites | on the OpenRouter page: three dropdowns over the whole catalogue, tried in your order before the free default — a paid favourite is your explicit pick on your own key, and what nobody chose never falls forward onto a bill. A spot that failed this session is skipped (#146, #148) |
| Budgets | `turn_token_budget` and `subtask_max_tokens` in settings.json, both opt-in (#145); a spent token budget ends the turn with the same protocol as the round budget |
| Self-healing | dies the server the window itself booted (`booted.json`, kept across restarts — `%LOCALAPPDATA%\Crow\` on Windows, `~/.local/state/crow/` on Linux), the turn reboots it — `booting it again (n/3)`, three per turn, then honestly red with the boot's own exit code. A server still loading (HTTP 503) is waited out once per turn |
| Crow log | Crow's own status lines about its machinery are written to `crow.log`, not into the chat (#262): the goal brake's `goal mode: N messages of an empty loop dropped from the history`, the same-failure line `goal mode, step N: the same failure keeps coming back -- …`, a discarded or kept degenerate round (#217), `the restored cache did not hold`, `the page in the browser panel stopped (…)` (#279), the chat-open and goal-setup bookkeeping (`working directory: …`, `mode yolo -- …`, `archived: …`, `no working directory -- writes are unbounded`, the working-area and goal cost notes, the `/goal` setup echo `goal: <title> -- N steps …`), the rollover's `rolled over at N tokens -> …` line, the working-area boundary alarm `! the working area was refused for …` with its explanation (#98), and — in the terminal — `tool budget spent after N rounds`. One line each, local time with its UTC offset and a kind: `2026-09-23T21:04:18+0200 [goal] goal mode: 52 messages …`. `~/.local/state/crow/log/crow.log` on Linux, `%LOCALAPPDATA%\Crow\log\crow.log` on Windows; rotated at 1 MiB, three old files kept (`crow.log.1`..`.3`). A reopened chat from an earlier build no longer draws these lines either. What stays in the chat: the rollover card, `goal mode stopped: …` / `goal mode paused: …`, the server reboot and load-wait lines, every other alarm, the `/goal` status answer (`goal: <title> -- 3/9, …`), `Memory updated`, `carried across the cut: …`, and every answer to something you typed or clicked. None of the moved lines was ever sent to the model; the nudges the model reads are unchanged |
| Boot logs | every boot Crow starts writes `llama-server-<port>.out.log` / `.err.log`, rewritten per boot — under `<cwd>\runs\` on Windows, `~/.local/state/crow/log/` on Linux. A silent death leaves its exit code and stderr there |
| Persistent subtasks | cards and `⑂` rows come back after a window restart (`session/subtasks-registry.json`): `running` becomes `interrupted`, numbering continues, deleting a chat deletes its subtasks |
| Scroll | the stream pulls to the end only for who IS at the end (80 px); scrolled up, nothing yanks you back — your own message does |
| Scrollbars | shown only while a strip scrolls (wheel, keys, touch, drag; gone 0.8 s after the last movement, kept while the pointer is held) or while the mouse pointer is over it — the chat, the stats line under an answer, code blocks, tables, the side panels, the rail, menus. At rest nothing is drawn, and nothing moves when a bar appears: the space stays reserved. The phone mirror uses the same page without the hover part; iOS draws its own indicator while you swipe (#305). The browser tabs strip and the phone's image and settings-category strips scroll without any bar |
| Layout at the minimum size | the composer's buttons stay inside the input box, long paths, URLs and compounds wrap inside the column instead of widening it, menus open above the pinned cards, a squeezed code or browser panel hides instead of showing a clipped sliver, and the settings sheet stays under the title bar (#231–#235). Audited 2026-09-23 (headless Chromium 1234 and WebKitGTK 2.52, 1130×520 to 2560×1440): composer spill and cut 477 → 0 findings, long-word overflow 1,950 → 0; re-audited on the integrated tree over 185 Chromium and 12 WebKitGTK renders. Accepted by robin in the live run of 2026-09-23 |
| Long chats | the rail and panel drags and the window resize follow the pointer. Measured 2026-09-23 on a 200-turn chat (12,968 nodes), WebKitGTK 2.52.6: rail drag 38.8 → 3.6 ms per step, window resize 16.9 → 4.0 ms, and 0 px of view drift after a mid-chat drag (was 2,079 px; WebKitGTK has no scroll anchoring) (#236–#238). On Windows the bridge calls are coalesced instead of dropped; not measured there |
| Working area moved | when the chat's folder changes, the model is told once, before your next line: `[Working area is now X (was Y).]` (#224). The notice rides that request only; a reopened chat draws your typed line alone in the bubble, not the notice (#241) |
| Start with `--root` | `crow --root DIR` binds DIR for the window and for the chat it restores, and makes DIR the folder the next start without `--root` opens (`active` in `roots.json`), the same as picking it in the chip. Before #303 the restored chat fell back to the last folder picked in the chip. A chat that recorded another folder is moved to DIR: the model is told once (#224), and its memory head is rebuilt only if it named the other folder. Without `--root` a restored chat keeps its own folder, or else the last picked one (#101). Covered by tests; not yet run live |
| Reload | a reload of the page (the recovery after a dead WebKitWebProcess, #204) redraws the live chat and runs start-up only once: it no longer restores session.json into a running chat and closes the window (#209). Covered by tests; not run live in WebKit |
| Tool-result clearing | before the window has to roll, old tool output is let go (#263). At 0.65 of the window (default on the local server, off for a remote provider), every tool result older than the last 5 rounds becomes one line: `[cleared at N of M tokens to keep the window: read_file 'path' -- chars, ~tokens. The file is on disk: read it again if you need it. Original: …/session/cleared/<stamp>.json]` (the path is quoted in backticks in the real line). Your lines, the model's answers, its reasoning and its tool calls stay exactly as they were, and so do the head (memory, goal) and the last 5 rounds. A batch runs only when it frees at least a tenth of the window, because every batch makes the server re-read the conversation from the first cleared result on (on the diorama replay: 64k–95k tokens per batch). Goal state, memory, skill and subtask results are never cleared. Nothing appears in the chat; each batch writes one line to `~/.local/state/crow/log/crow.log` (`[context] context-clear: …`, #262's log). `context_clear_at` in settings.json sets the share, `0` switches it off. The rollover below stays as the last resort — replayed on the 2026-09-23 run, each rollover came 55 and 88 rounds later, and neither recorded context would have reached it on its own |
| Rollover | past 0.9 of the window the next line rolls BEFORE the turn — the archive is a complete conversation, your line opens the new context as carry. Mid-turn the roll happens at a round boundary, once per turn; a refused second roll is a red line, and the readout resets the moment a roll happens (#152). The note carries the model's own digest of the leg — asked on the still-warm prefix, marked as unverified model text, capped by `rollover_digest_tokens` with a floor of 2000 tokens (`0` off, #154/#205). The leg speaks the turn's own reasoning fields so it lands on the warm cache, and thinking that leaks into the answer is washed out afterwards (#205 replaced #157's thinking-off switch, which re-rendered the prefix cold). An answer that is a tool call is asked once more; one that still is not text, or is under 200 characters, becomes the line `[digest failed: ...]` (#210). An answer the cap cut off loses its unfinished last line and ends with `[digest cut off at the N-token cap ...]` (#210). The head after the cut carries the goal's step marks once — `[done]`/`[running]`/`[open]` and the next step (#210). Behind the note come the last 3 tool rounds from before the cut, verbatim: answered, successful and correctly named calls only, results clipped to 2000 chars and marked `[carried across the cut]`, images replaced by a sentence, 3000 tokens at most, an `edit_file`/`write_file` preferred. Your line comes after them. A reopened chat draws them as a note line `carried across the cut: <tools>` under the card, not as new tool rows (#214) |

---

## Dictation

The microphone sits between the release level and the arrow. While it records, the composer is a
live waveform:

<div align="center">
<img src="../images/CrowVoiceInput.png" alt="The composer recording: a waveform across the input, the microphone lit" width="900">
</div>

| | |
|---|---|
| Why Python and not the page | the window is handed to WebView2 as HTML rather than served, so it is not a secure context — `getUserMedia` is behind that same gate, and WebView2 has no recogniser of its own |
| Model | `faster-whisper-small`, ~486 MB, multilingual. `install.ps1` fetches it on Windows; on Linux the window fetches it on the first click |
| Audio | 16 kHz mono asked of the device directly, no resampler behind it |
| Disk | nothing. `sounddevice` fills an array and `faster-whisper` takes it directly — there is no WAV in between |
| Optional | both imports are, like pywebview itself. Missing ones are **named** in the sentence the button answers with |
| Linux | `bash install.sh --voice`, plus PortAudio from the distribution — see [Linux](linux.md) |

It never submits by itself: the text lands in the input and you press the arrow.

The phone has its own 🎤 on the HTTPS address, transcribed by the same model on this PC — see [Phone](remote.md#phone-microphone-290) (#290).

---

## Git panel (#156)

The octocat in the title bar opens it, and closes it again — there is no cross in
the panel, for the reason the code panel has none: a control inside the thing it
folds away leaves no way back.

| group | what it shows |
|---|---|
| Changes | branch against its upstream, every changed file with its status letter and `+`/`−`, the totals in the head. Untracked files are listed and counted separately — they are never swept into a commit |
| `⎇ <branch>` | the current branch, ahead/behind in the head, every local branch in the body |
| `⊸ Commit` | the tracked, changed files **by name**, a message field, and the button. It stages exactly those paths — no `-a`, no `.` |
| History | `◉` commit · `⑃` merge · `⇧` push · `⑂` fork · `◈` connect. Commits and merges come out of `git log`; pushes and connects out of Crow's own record (`git_events.json`, beside the sessions) — nothing is invented, a fork appears the day one happens |

The repository is the one the **working directory** is bound to, never the process's
cwd. No folder bound, or the folder is not a repository: the panel says so and shows
nothing else.

### Connecting GitHub

Settings → API Keys → GitHub. The client id belongs to an OAuth app **with device
flow enabled** and is not a secret — the device flow has none, which is why it may
be shipped or typed in plain. `Connect` puts a code in the chat; enter it at
github.com/login/device and the token is stored owner-only beside the provider keys
(`provider_keys.json`). One app covers every repository the account can reach.

`Disconnect` sits on that same page, and only there: the account button in the
panel head **only connects**. As a toggle it once read a stale label and
disconnected the account somebody was trying to connect.

**Pushing uses git's own credentials**, not that token — a token on a git command
line would be readable in the process list for the length of the call.

---
