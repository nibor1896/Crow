# #359: call bodies in the #263 batch, offline replay

## Session

| field | value |
|---|---|
| file | `<home>\dev\crow-nest\decode_out\meas-245\session-0915.json` |
| sha256 | `6ee99879f3982c78e5a5e9118ef50e57834d89201d6393bec15c76fc0f46a834` |
| origin | byte copy of `rollover-20260915-092436.json` (crow-nest meas-245 `PREREG.md:100`), robin's Windows work session of 2026-09-15 |
| messages | 274: 1 system, 14 user, 133 assistant, 126 tool |
| model | not recorded in the file |
| recorded `context_tokens` | 180,263 (0.90 of 200,000, the window the walk assumes; the file records no n_ctx) |
| keep window | last 5 assistant messages, from message 264 |
| bodies behind the keep window, >= 600 chars | 13 in 12 calls: `write_file` `content` 11, `edit_file` `old` 1, `new` 1; 26,874 chars, 679 to 6,418 each; 1 of the 13 was a refused write (its stub says the call failed) |

Not replayed:

- `chat-20261006-165103.json` (the ticket's session): gone from disk.
- `%LOCALAPPDATA%\Crow\session\session.json`: 5 messages, no tool calls.
- `%LOCALAPPDATA%\Crow\session\cleared\*.json`: originals of earlier batches, not conversations.

## Commands

```
python tools/context_breakdown.py <session> --tokenizer <crow-nest>\models\GLM-5.3-Flash-original\tokenizer.json --replay --walk [--json]
python tools/context_breakdown.py <session> --tokenizer <crow-nest>\models\Qwen3.8-Flash-Next-original\tokenizer.json --replay --walk [--json]
python tools/context_breakdown.py <session> --tokenizer <crow-nest>\models\Qwen3.8-Flash-Next-original\tokenizer.json --walk --offset 6595
```

| condition | value |
|---|---|
| date | 2026-10-14 |
| machine | Windows 11, Python 3.13.3, tokenizers 0.22.2, jinja2 3.1.6 |
| Crow | branch `ctx-359` on main `07fd73c`, fix round 1 (stub shortened, refused writes named) |
| mode | rendered template: the model's `chat_template.jinja`, no tools block (the file stores none) |
| renderer check | crow-nest `engine/tests/fixtures/GLM-5.3-Flash/tokenizer-goldens.json`: 16 of 16 renders and ids identical |
| stubs | counted as a live batch on this machine writes them: naming `<home>\AppData\Local\Crow\session\cleared\<stamp>.json` |
| replay | crow_core `clear_old_results`, keep 5, `at_least` 0, forced at message 264 on messages [0, 274) |
| walk | every point before an assistant message, window count = rendered conversation through the last assistant message (+ `--offset`), crow_core's own rule: 0.65 of n_ctx 200,000, `at_least` 0.10, keep 5, rollover at 0.9 |
| runs | replay and walk: 2 per tokenizer, identical JSON; walk with offset: 1 |

## Replay: one batch forced at the keep window

| metric | GLM-5.3-Flash | Qwen3.8-Flash-Next |
|---|---|---|
| rendered tokens before | 157,224 | 173,668 |
| freed, results only (#263) | 38,908 | 44,196 |
| freed, results + call bodies (#359) | 45,727 | 51,487 |
| call bodies on top | 6,819 | 7,291 |
| call body stub, tokens (n = 13) | mean 84.1, 80 to 87 | mean 100.3, 96 to 103 |
| first changed message, both arms | 3 | 3 |
| re-prefill tokens, results only | 116,427 | 127,490 |
| re-prefill tokens, results + call bodies | 109,608 | 120,199 |
| re-prefill events, both arms | 1 (by construction) | 1 (by construction) |
| render stable (only stubbed values moved) | yes | yes |

crow_core's own estimate for the same batch, both tokenizers:

| arm | typical | low |
|---|---|---|
| results only | 44,526 | 27,885 |
| results + call bodies | 53,608 | 33,314 |

## Walk: the history under the live rule

| metric | GLM-5.3-Flash | Qwen3.8-Flash-Next | Qwen3.8-Flash-Next, count + 6,595 |
|---|---|---|---|
| batches, results only | 1, at message 216 | 1, at message 182 | 1, at message 176 |
| batches, results + call bodies | 1, at message 216 | 1, at message 182 | 1, at message 176 |
| window count at the batch | 130,777 | 132,708 | 134,855 |
| call bodies in the batch | 7 | 5 | 4 |
| freed, results only | 38,275 | 43,094 | 43,094 |
| freed, results + call bodies | 42,873 | 45,969 | 45,814 |
| re-prefill tokens, results only | 90,636 | 87,662 | 83,216 |
| re-prefill tokens, results + call bodies | 86,038 | 84,787 | 80,496 |
| first changed message, both arms | 3 | 3 | 3 |
| rollover reached | no, no | no, no | no, no |
| tokens at the end, results only / + bodies | 118,949 / 114,351 | 130,574 / 127,699 | 137,169 / 134,449 |

- 6,595 = recorded 180,263 minus rendered 173,668 (Flash-Next); not attributed, the tools block is one candidate, not measured.

## Against #359 expected result 1

| gate | measured | verdict |
|---|---|---|
| bodies free >= 8,000 tokens on top of results only | replay: 6,819 (GLM), 7,291 (Flash-Next); n = 1 session | not met on this session |
| re-prefill events +0 | walk under the live rule: 1 and 1 in all 3 walks | met on this session |

- The 8,000 gate was set on `chat-20261006-165103.json` (measured potential 11,294); that session is gone.
- Under the live rule the batch fires earlier than the forced replay (message 216 or 182, not 264), so fewer bodies are behind the keep window: 7 or 5 of 13.

## Files

| file | content |
|---|---|
| `session-0915-glm-5.3-flash.json`, `.txt` | breakdown, replay, walk |
| `session-0915-qwen3.8-flash-next.json`, `.txt` | breakdown, replay, walk |
| `session-0915-qwen3.8-flash-next-offset-6595.txt` | breakdown, walk with count + 6,595 |
