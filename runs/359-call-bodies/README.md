# #359: call bodies in the #263 batch, offline replay

## Session

| field | value |
|---|---|
| file | `<home>\dev\crow-nest\decode_out\meas-245\session-0915.json` |
| sha256 | `6ee99879f3982c78e5a5e9118ef50e57834d89201d6393bec15c76fc0f46a834` |
| origin | byte copy of `rollover-20260915-092436.json` (crow-nest meas-245 `PREREG.md:100`), robin's Windows work session of 2026-09-15 |
| messages | 274: 1 system, 14 user, 133 assistant, 126 tool |
| model | not recorded in the file |
| recorded `context_tokens` | 180,263 |
| keep window | last 5 assistant messages, from message 264 |
| bodies behind the keep window, >= 600 chars | 13: `write_file` `content` 11, `edit_file` `old` 1, `new` 1; 26,874 chars, 679 to 6,418 each; 1 of the 13 was a refused write |

Not replayed:

- `chat-20261006-165103.json` (the ticket's session): gone from disk.
- `%LOCALAPPDATA%\Crow\session\session.json`: 5 messages, no tool calls.
- `%LOCALAPPDATA%\Crow\session\cleared\*.json`: originals of earlier batches, not conversations.

## Command

```
python tools/context_breakdown.py <session> --tokenizer <crow-nest>\models\GLM-5.3-Flash-original\tokenizer.json --replay --json
python tools/context_breakdown.py <session> --tokenizer <crow-nest>\models\Qwen3.8-Flash-Next-original\tokenizer.json --replay --json
```

| condition | value |
|---|---|
| date | 2026-10-14 |
| machine | Windows 11, Python 3.13.3, tokenizers 0.22.2, jinja2 3.1.6 |
| Crow | branch `ctx-359` on main `07fd73c` |
| mode | rendered template: the model's `chat_template.jinja`, no tools block (the file stores none) |
| renderer check | crow-nest `engine/tests/fixtures/GLM-5.3-Flash/tokenizer-goldens.json`: 16 of 16 renders and ids identical |
| batch | crow_core `clear_old_results`, keep 5, `at_least` 0, forced at message 264 on messages [0, 274) |
| runs | 2 per tokenizer, identical output |

## Result

| metric | GLM-5.3-Flash | Qwen3.8-Flash-Next |
|---|---|---|
| rendered tokens before | 157,224 | 173,668 |
| freed, results only (#263) | 38,722 | 43,979 |
| freed, results + call bodies (#359) | 45,207 | 50,905 |
| call bodies on top | 6,485 | 6,926 |
| first changed message, both arms | 3 | 3 |
| re-prefill tokens, results only | 116,613 | 127,707 |
| re-prefill tokens, results + call bodies | 110,128 | 120,781 |
| re-prefill events, both arms | 1 | 1 |
| render stable (only stubbed values moved) | yes | yes |

crow_core's own estimate for the same batch, both tokenizers:

| arm | typical | low |
|---|---|---|
| results only | 44,526 | 27,885 |
| results + call bodies | 53,400 | 33,008 |

## Against #359 expected result 1

| gate | measured | verdict |
|---|---|---|
| bodies free >= 8,000 tokens on top of results only | 6,485 (GLM), 6,926 (Flash-Next), n = 1 session | not met on this session |
| re-prefill events +0 | 1 and 1 per tokenizer | met |

- The 8,000 gate was set on `chat-20261006-165103.json` (measured potential 11,294); that session is gone.
- Recorded 180,263 against rendered 173,668 (Flash-Next): the 6,595 gap is not attributed; the tools block is one candidate, not measured.

## Files

- `session-0915-glm-5.3-flash.json`
- `session-0915-qwen3.8-flash-next.json`
