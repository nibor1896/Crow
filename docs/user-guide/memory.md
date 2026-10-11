[← README](../../README.md) · [Docs index](../README.md)

# Memory

Two files. Plain text, `§` on its own line between entries, editable by hand.

| path | limit | holds |
|---|---|---|
| `<working directory>/.crow/MEMORY.md` | 4,000 chars | this project: layout, conventions, commands, traps |
| `USER.md` — `%LOCALAPPDATA%\Crow\` on Windows, `~/.config/crow/` on Linux | 1,500 chars | who you are, how you want to be worked with |

| | |
|---|---|
| Limits come from | `MAX_TOOL_BYTES`. 16,000 B is ~4,000 tokens, so 4 chars buy 1 token |
| 4,000 chars is | a quarter of one tool read. Bigger than that and `read_file` is cheaper |
| Head cost | measured 2026-09-24 in a goal chat: the whole head 5,731 chars, the two store blocks ~3.9k of it (~1k tokens) |
| Empty stores cost | nothing. No entries, no block, the prefix unchanged |

## Rules

| | |
|---|---|
| Never trimmed for you | a write over the limit fails and returns the entries and both numbers |
| No `read` action | the content is already in the prompt |
| Exact duplicates | answered with success and one entry |
| Injection and invisible Unicode | refused before the entry is written |
| Contradicts the machine (#270) | refused with the fact: "no GPU" / "CPU-only" while nvidia-smi names a card (a note that names the card passes, e.g. "render_page refuses while the model server holds the RTX 5090"), and "a tool changes bytes" (every write is byte-exact, #252) |
| No working directory bound | `memory` is refused with a reason; `user` still works |

## The head is pinned

The rendered block is written into the chat file on first open and replayed **verbatim** from then
on. `prefix_fingerprint` hashes the system prompt, llama-server reuses a prompt by common token
prefix, and the KV cache lives on disk, so a head re-read at every start would go stale against
every saved cache. Binding a different folder re-pins and says what the prefill costs first.

## Order: the same in every chat first, the folder's last (#364)

| part of the system prompt | differs between chats? |
|---|---|
| base prompt (`--system`, `--language`) | no, per start |
| machine line | no, per machine |
| `USER PROFILE` | no, `USER.md` is global |
| `SKILLS` | no, global |
| working area | **yes**, per folder |
| project `MEMORY` (or the "no working directory bound" line) | **yes**, per folder |
| active goal | **yes**, per folder, always last |

A server reuses a prompt by its longest common token prefix, so a new chat in another folder reuses
everything above the working area. Measured offline on two stored chats in two folders (2026-10-11):
GLM-5.3-Flash 6,052 → 6,357 shared tokens, Qwen3.8-Flash-Next 6,548 → 6,873. Existing chats keep
their pinned head; the first new pin after the update is cold once.

## The machine line (#270)

The head opens with one line of static machine facts — OS, CPU, RAM, GPU name and total
VRAM, probed once per process (`crow_platform.machine_facts`) — and the rule that a tool's limit is not the
machine's. Never free memory or anything that moves: the head follows the fixed base prompt, so an unchanged head keeps the cached prefix. Existing chats keep their pinned
head; a new chat, a folder change or a rollover pins the new one.

## Who writes it

| | |
|---|---|
| In a turn | the model's own `memory` call writes at once, at every approval level -- no question |
| The review | `memory` and `skill` writes, gated (below) |
| Review trigger | `MEMORY_REVIEW_AT` = **0.20 / 0.50 / 0.75** of the context window |
| Each mark fires | once. The mark is written to the chat file and travels with it |
| A turn crossing several marks | fires once, at the highest |
| Off with | `--no-review` |
| Before it writes | **it asks.** The proposed entries wait on a chip in the composer; nothing reaches the file until you press it |
| Nobody answers | they expire after **300 s** and are dropped. Nothing is ever written by a timer |
| Ask nothing, write always | `--no-memory-approval` |
| When it saves | a `Memory updated` line: per entry when the review writes unasked, one per `save to memory` click when gated |

## The gate

The review never writes on its own. What it wants to keep is staged and shown behind the composer,
and it stays there until you answer.

<div align="center">
<img src="../images/memory-consolidation.png" alt="Memory Consolidation: the staged writes behind the composer, +2 gained and -0 lost" width="900">
</div>

| | |
|---|---|
| Collapsed | the title, lines **gained** in green and **lost** in red. A `replace` is one entry and both |
| First click | a preview of every proposed entry (160 chars), and the two answers |
| Second click | the full text: a `replace` shows `− old entry` above `+ new entry` (it keeps the old entry's place in the file), an `add` is marked "appended at the end" |
| `save to memory` | writes through the same `memory` tool the model uses. The cap, the duplicate check and the injection scan all still answer, and what did not land is said: `Memory: not saved -- already in memory / over the 4,000-char limit / expired` (#285) |
| `discard` | nothing is written |
| No answer | the entries expire after 300 s and are dropped. **Nothing is ever written by a timer** |
| New chat | the questions go with it |
| Typing while it runs | the line is **queued**, not dropped. The composer says `queued -- the memory review is finishing` and the turn starts by itself |
| Off | `--no-memory-approval`, and then the review writes unasked as it did before 1.0.0 |

It keeps breathing while it waits, because a question is still true until it is answered. The line
that reports a **finished** write glows once and settles: same colour, different grammar.

---
