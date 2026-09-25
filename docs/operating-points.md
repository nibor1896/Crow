[← README](../README.md) · [Docs index](README.md)

# Operating points

An operating point is one model on one engine at one measured placement. Crow ships four of
them. The default is crow-nest, the Rust engine: it is started from its own repository and the
window connects with `--base-url http://127.0.0.1:8099/v1`. The window boots the llama.cpp lines
from its model menu — the lines below are what it builds, written out for a shell.

**Source of truth:** [`manifests/operating-point.json`](../manifests/operating-point.json).
Every line on this page is held against it by
[`tools/check_operating_point.py`](../tools/check_operating_point.py), which reads this file as
raw text. Editing a flag here without editing the manifest turns the checker red.

| | model | decode | port | engine |
|---|---|---|---|---|
| **Default, Windows** | `CNQ4.5-M` NVFP4 container | **45.1 tok/s** | 8099 | crow-nest (Rust) |
| **Default, Linux** | `CNQ4.5-M` NVFP4 container | **36.8 tok/s** at 16k context | 8099 | crow-nest (Rust) |
| Second, Windows | `Qwen3.8-Flash-Next-UD-Q2_K_XL` | 41.76 tok/s | 8083 | llama.cpp, local build |
| Second, Linux | `Qwen3.8-Flash-Next-UD-Q2_K_XL` | 41.8 tok/s | 8083 | llama.cpp, built here |
| Third | `Qwen3.8-27B-UD-Q4_K_XL` | 123.05 / 133.18 tok/s | 8082 | llama.cpp, packaged |

crow-nest figures: measured on `v0.3.0` ([crow-nest — the Rust engine](#crow-nest--the-rust-engine)).

`DEFAULT_BASE_URL` in the client is still `http://127.0.0.1:8083/v1`, so the crow-nest line is
reached with `--base-url http://127.0.0.1:8099/v1`.

A fourth server, DeepSeek-V4-Flash-0731 on `:8081`, is still set up by `install.ps1` and is
[at the end of this page](#deepseek-v4-flash-0731).

---

## Flash-Next on Windows — the second operating point, default from 2.0.0 to 2.7.0

| | |
|---|---|
| Model | `Qwen3.8-Flash-Next-UD-Q2_K_XL`, 3 shards, 73.45 GiB |
| Architecture | `qwen4exp` MoE: 48 layers, 512 experts per layer, 10 active, full attention every 4th |
| Quant | `UD-Q2_K_XL`, Unsloth |
| Context | `-c 200000`, one slot (`-np 1`) |
| Placement | `-ncmoe 30 --fit off --load-mode none`, `-b 2048 -ub 2048` |
| KV | `q8_0` / `q8_0` |
| Vision | `--mmproj mmproj-F16.gguf`, 904,004,000 B (#170) |
| Reasoning | fixed: `high` (the template's xhigh) on every request; the window offers no level. Accepted words `none` `low` `medium` `high`; `max`, `minimal` and an explicit `off` return HTTP 500 (#160). See [thinking and sampling](#thinking-and-sampling-per-point) |
| Thinking cap | `reasoning_budget` 1024 per request, from the manifest (#176). Looked up by the model the server reports, not by the wire label `"crow"` (#220, 2026-09-22): before that, no local turn, review or digest without `--model` carried it |
| GPU | RTX 5090, 32,607 MiB. **30,984 MiB in use**, 1,059 MiB left |
| Decode | **41.76 tok/s** (40.34–42.76) |
| Prefill | **727.65 tok/s** |
| Build | llama.cpp pin `6c84c7d5d` (PR #27742) + PR #28040 + PR #27880, local. 62 graph splits per decoded token |
| License | `qwen-community-1.0` — not Apache-2.0 |
| Port | 8083 |

Conditions: 2026-09-01, driver 616.56, one 33,494-token cold turn per boot, 200 tokens out,
three rounds interleaved against the previous placement `-ncmoe 40 -ub 4096` (539.98 / 35.74);
wall clock per turn 67.9 s → 51.3 s. Accepted live at 41.8 tok/s. Decode falls with context
depth: `ms/token = 24.06 + 0.0706 per 1,000 tokens` (r² 0.93), i.e. ~41 tok/s at 30k and ~28 at
175k. Not measured: decode at a full 200k window, and whether an image prefill fits in the
1,059 MiB left on the card.

**The engine is a local build.** The packaged `b10269` cannot load `qwen4exp` at all. The pin
carries two patches, both measured at parity or better on this line: PR #28040 (the PLE n-gram
lookup in O(log n) instead of a scan over every used KV cell) and PR #27880 (the PLE embedding
hoisted into the token embedding's graph split: 62 splits per decoded token instead of 64,
−0.99 ms on the fixed term in the one clean pair, inside the 1.35 ms spread of one arm).

**The engine has nothing more to give, and that is measured (#159, #186).** 67.1 % of CPU
cycles per token are synchronization at the 62 CPU↔GPU handoffs; the RAM bus runs at 33.5 %.
Every lever inside llama.cpp is dead by a direct measurement: bandwidth, expert cache, thread
count, `OMP_WAIT_POLICY`, `-ncmoe` below 30, and the barrier implementation itself
(`GGML_OPENMP=OFF` costs +4 to +6 ms per token).

### By hand

```powershell
& "$env:LOCALAPPDATA\Crow\bin\llama-server.exe" -m "$env:LOCALAPPDATA\Crow\models\qwen-next-gguf\UD-Q2_K_XL\Qwen3.8-Flash-Next-UD-Q2_K_XL-00001-of-00003.gguf" --port 8083 -c 200000 -b 2048 -ub 2048 -ctk q8_0 -ctv q8_0 -ncmoe 30 --fit off --load-mode none -np 1 --mmproj "$env:LOCALAPPDATA\Crow\models\qwen-next-gguf\mmproj-F16.gguf" --jinja
```

`--load-mode none` is what makes it reproducible: the expert weights are read once at boot
(about a minute) instead of being paged off the disk during the turn.

**This one needs a local engine.** `qwen4exp` exists in llama.cpp only from PR #27742; the
packaged `b10269` cannot load it. Build the pin `6c84c7d5d` and apply PR #28040 (one hunk by
hand) and PR #27880 (applies cleanly) for the line above. Do not build `b10687` or newer: it
aborts during CUDA warmup on this card, and the cause is not attributed.

Crow does this for you from the manifest, with the log and the process group it needs:

```powershell
python $env:LOCALAPPDATA\Crow\cli\crow.py --serve flash-next-q2-k-xl
```

---

## Flash-Next on Linux — the line that differs, measured

Same model, same manifest line, with the `linux` object merged over it. Measured 2026-09-16 on
Arch (Omarchy), Hyprland 0.56.2 on Wayland, RTX 5090, driver 610.57.

| | |
|---|---|
| Placement | `-ncmoe 31 -t 24 --load-mode mmap --image-min-tokens 1024 --no-mmproj-offload`, otherwise the Windows line |
| Why `--load-mode mmap` | `none` holds ~48 GiB of experts in anonymous memory beside the page cache's copy; on 62 GiB with `vm.swappiness=150` over zram that swapped the desktop and systemd-oomd killed the terminal, five times. Under mmap the experts are file-backed pages: dropped and re-read, never compressed. Measured after the switch: **41.78 / 41.85 tok/s decode, 428 tok/s prefill** on a 3,964-token first turn -- above the 36.7 of `none`, because nothing sits in zram any more |
| Why `--image-min-tokens 1024` | the model's own minimum turned a 1097×380 paste into ~350 tokens and the model said no image had arrived; llama.cpp warns at load that Qwen-VL needs 1,024 |
| Why `--no-mmproj-offload` | at 1,024 image tokens the projector on the GPU died with `SIGSEGV` in `ggml_gallocr_alloc_graph` under `clip_encode` (core dump 18:43:27): ~1.3 GiB of VRAM is all the card has left at `-ncmoe 31`. On the CPU the same paste was read line for line, 155 tok/s prefill on the image turn |
| Why `-ncmoe 31` | the Wayland desktop already holds about 1 GiB of the card, and the Windows placement died on its first request (`cublasCreate`, resource allocation failed). At 31 the card settles at 31,081–31,213 MiB after load, 31,334 peak in a turn |
| Why `-t 24` | llama.cpp's Linux default picked 4 threads on the 24-core Ultra 9 285K |
| Engine | built here: llama.cpp pin `6c84c7d5d` + PR #27880 + PR #28040, CUDA 13.3, `sm_120`. See [`tools/build-llama-server.sh`](../tools/build-llama-server.sh) |
| Port | 8083 |

Decode on two 200-token turns per arm, temperature 0, thinking off:

| threads | decode tok/s |
|---|---|
| default (4) | 26.41 / 25.57 |
| `-t 8` | 34.39 / 31.32 |
| **`-t 24`** | **36.72 / 36.22** |
| `-t 8 -tb 24` | 33.73 / 34.59 |

Those four rows were taken under `--load-mode none`; the line now runs `mmap` and decodes at
**41.78 / 41.85 tok/s** (124- and 445-token answers, the second with an image), prefill 428
tok/s on a 3,964-token cold first turn. The Windows line's 41.76 was a cold 33k-token turn at
`-ncmoe 30`; **the two are not the same measurement.** Not measured: a cold 33k-token turn here,
the 16–20 thread range under mmap, and decode after the page cache has been evicted by
something else.

### By hand

```bash
$HOME/.local/share/crow/bin/llama-server -m $CROW_MODELS/Qwen3.8-Flash-Next-UD-Q2_K_XL-00001-of-00003.gguf --port 8083 -c 200000 -b 2048 -ub 2048 -ctk q8_0 -ctv q8_0 -ncmoe 31 -t 24 --fit off --load-mode mmap --image-min-tokens 1024 --no-mmproj-offload -np 1 --mmproj $CROW_MODELS/mmproj-F16.gguf --jinja
```

`python3 ~/.local/share/crow/tools/start-server.py flash-next-q2-k-xl` builds that line from the
manifest instead of repeating it. `CROW_MODELS` points one shell at a model tree;
`<install>/models` is where the core looks with nothing set — see [Linux](user-guide/linux.md).

---

## Qwen3.8-27B — the third operating point

Still shipped, still measured, still bootable from the model menu. It is the faster one per
token and the smaller download, and it runs on the **packaged** engine.

| | |
|---|---|
| Model | `Qwen3.8-27B-UD-Q4_K_XL.gguf`, 17,559,178,144 B |
| Architecture | dense, no `expert_count`; hybrid attention + SSM, `full_attention_interval 4` |
| Quant | `UD-Q4_K_XL`, Unsloth, imatrix 1,251 chunks |
| Context | `-c 200000`, one slot (`-np 1`) |
| KV | `q8_0` / `q8_0`, 6,647.00 MiB measured against 6,645.8 predicted |
| Vision | `--mmproj mmproj-F16.gguf`, 927,607,488 B; +1,124 MiB VRAM, text prefill unchanged |
| Speculation | `--spec-type draft-mtp`, head ships in the GGUF |
| GPU | RTX 5090, 32,607 MiB. 26,140 MiB in use |
| Decode | 123.05 tok/s (11-round turn) · 133.18 (warm turn) |
| Prefill | 2,262.96 tok/s |
| Port | 8082 |
| Build | llama.cpp server `1c3c967` — the packaged engine runs it |
| License | Apache-2.0 |

### By hand

```powershell
& "$env:LOCALAPPDATA\Crow\bin\llama-server.exe" -m "$env:LOCALAPPDATA\Crow\models\qwen38-gguf\Qwen3.8-27B-UD-Q4_K_XL.gguf" --mmproj "$env:LOCALAPPDATA\Crow\models\qwen38-gguf\mmproj-F16.gguf" --port 8082 -c 200000 -ctk q8_0 -ctv q8_0 -ngl 99 -np 1 --jinja --slot-save-path "$env:LOCALAPPDATA\Crow\session" --spec-type draft-mtp
```

---

## crow-nest — the Rust engine

Crow runs on crow-nest, the Rust engine built for this project. Since v0.2.0 (2026-09-14) its
decode is faster than llama.cpp on the same machine, with identical greedy outputs; vision is
served from the container itself, no projector file. Since v0.3.0 (2026-09-17) the engine runs
on Linux too, inside the same memory-bounded scope Crow uses for llama-server.

The line below is **v0.3.0**, the engine these numbers were measured against. `v0.3.1` was
released later the same day, 2026-09-18 ([release](https://github.com/nibor1896/crow-nest/releases/tag/v0.3.1));
the three things on it that Crow has to know about are under
[the engine's `main`](#the-engines-main) at the end of this section, measured before the tag.

| | |
|---|---|
| Engine | crow-nest `v0.3.0` ([repo](https://github.com/nibor1896/crow-nest), [release](https://github.com/nibor1896/crow-nest/releases/tag/v0.3.0)), Windows and Linux, own HTTP server, OpenAI-compatible |
| Model | `CNQ4.5-M`, the project's own quant: one 104.7 GB NVFP4 container of `Qwen3.8-Flash-Next` ([package](https://huggingface.co/nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M)) |
| Context | 200,000, one slot |
| Vision | yes, from the container's own `vit` section (no `--mmproj`, nothing extra to download) |
| Decode | Windows: **45.1 tok/s** (22.18 ms/token) vs llama.cpp 44.9 on the same prompt, greedy ids bit-identical. Linux: 36.8 tok/s at 16k context (the ten-task form, the same figure the Windows record of that form shows) |
| Prefill | Windows: 771 tok/s default, **871 tok/s** with `CROW_PF_GEMM_B=1`, vs llama.cpp 922.5 (16k reference prompt). Linux: **968 tok/s** cold on the same 16k prompt, 740 tok/s on a cold 1024-token prompt, warm short turns 228 ms prefill / 247 ms to the first token |
| Quality | ten-task suite unchanged (2/5/3) against the llama.cpp operating point's reading |
| Port | 8099 |
| Thinking | fixed: `high`, which serve maps to the template's xhigh, capped at 1024 reasoning tokens. Until 2026-09-22 Crow sent no level and serve read that as thinking **off**. See [thinking and sampling](#thinking-and-sampling-per-point) |
| GPU | RTX 5090 class (Blackwell `sm_120` required), 62-64 GB host RAM class, CUDA driver + NVRTC 13.3 (Linux: the runtime libs on `LD_LIBRARY_PATH`, the container on a non-compressed path) |

Measured 2026-09-13/14 on one RTX 5090 (Windows), F49 pair-chain methodology; sources: crow-nest issues
#62 (decode) and #10 (prefill), release notes of v0.2.0. Linux numbers measured 2026-09-17 on the same
card under Arch Linux, driver 610.57.04, paired cold-state runs; sources: the crow-nest v0.3.0 release
notes and its CHANGELOG. Known on Linux: the engine's logits drift from the Windows references beyond
the 8-row parity form (NVRTC/driver JIT versions), ids identical on the short forms; long goal-mode
sessions at 170k+ context degenerate (crow-nest #67, #68).

Start on Windows (PowerShell, two windows; engine repo root):

```powershell
# engine (from the crow-nest repo root)
$env:CROW_PF_GEMM_B = "1"
engine/target_srv/release/serve.exe --port 8099 --slot-save-path decode_out/session

# Crow (the window; pick the engine above, http://127.0.0.1:8099/v1, in its model menu)
python cli/crow_gui.py
```

Start on Linux (two terminals; engine repo root):

```bash
# engine: the launcher puts serve in a memory-bounded systemd scope and sets LD_LIBRARY_PATH
tools/serve-linux.sh --port 8099 --slot-save-path decode_out/slots

# Crow
crow --base-url http://127.0.0.1:8099/v1
```

### The engine's `main`

Measured on the engine's `main` after v0.3.0, on the same card under Arch Linux, and recorded here
because each of them changes what a Crow user sees. All three are in crow-nest **v0.3.1**, tagged
2026-09-18 after this section was written.

**`CROW_ATTN_LUT` is the engine's default since 2026-09-18** (crow-nest `#61`, 61g): the split
decode attention kernel reads its e4m3 KV bytes out of a shared table. Bit-identical by
construction, and measured so — generated ids `56305eee11d6`, unchanged. `decode run`, one fresh
process per run, W + 3N: **23.52 ms per decode token = 42.5 tok/s**, against the one
`CROW_ATTN_LUT=0` fallback run at 25.20 ms = 39.68. The `serve` figure of record, an arm mean in
one drift chain (`c3-sdsd-61g`, four counted runs): **53.32 tok/s, within-arm spread 1.0038**,
beside that chain's adjacent `decode run` arm at 42.56 tok/s and spread 1.0010. `CROW_ATTN_LUT=0`
is the fallback of record. Linux only — Windows has not been rerun at this default, and the 45.1
tok/s in the table above is the v0.2.0 Windows reading, not this one.

**Every image but the first of a process was read as the previous image** (crow-nest `#73`,
`bc9cd9b`, found and fixed 2026-09-18). The vision tower launched asynchronously and the blocking
copy that reads its result ran on the legacy null stream, which does not order against it, so the
copy took whatever the one shared scratch buffer still held: the previous image's embeddings —
complete, plausible and one request stale — cached under the **new** image's hash. It reads as a
fixed colour permutation and is a shift by one request. This is what Crow's
[`read_image`](reference/tools.md) and every clipboard paste got against a crow-nest server. The
first image of a process was always correct, which is why it stayed invisible. No Crow code
changes; the engine has to be on `main` or newer.

**`serve`'s default `max_tokens` is 8192, not 1024** (`8bad310`, 2026-09-18). Crow sends
`max_tokens` on every request since 2.3.0 and no longer depends on this, but a 2.2.1 client against
an older engine can still lose a long tool call to `finish length`.

---

## Thinking and sampling, per point

Before 2026-09-22 Crow sent no `reasoning_effort` on a chat where nobody had picked a level, so
the engine decided. llama-server passed the empty key to Qwen3.8's template, which defaults to
xhigh. crow-nest's `serve` read the same empty key as thinking **off** (`serve.rs`; engine.log
2026-09-22: 2,962 requests `thinking off`). Both got the card's *thinking* sampling row. Now an
entry in `manifests/operating-point.json` can set `reasoning_fixed`. Crow then sends that word
on every request: turn, rollover digest, turn after the cut and review. A level stored in the
chat is ignored, and the window shows no level menu. To flip a point, change that one value
(`none` picks the entry's `sampling_no_thinking` row). To give the choice back to the chat,
delete it.

| Entry | Thinking sent | Sampling (temperature / top_p / top_k / min_p / presence) | Cap |
|---|---|---|---|
| `flash-next-q2-k-xl` | `high` | 1.0 / 0.95 / 20 / 0.0 / 0.0 | 1024 |
| `flash-next-cnq45-m` | `high` | 1.0 / 0.95 / 20 / 0.0 / 0.0 | 1024 |

The rows are the card's Best Practices
([Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next), re-read 2026-09-22):

- thinking: 1.0 / 0.95 / 20 / 0.0 / 0.0
- non-thinking: 0.7 / 0.80 / 20 / 0.0 / 1.5

`min_p` is 0.0 in **both** rows. From 2026-09-21 to 2026-09-22 both entries sent 0.01, because
a note wrongly claimed 0.01 was the card's value. The cap of 1024 stays until it is measured.
The card allows up to 262,144 reasoning tokens for agentic work, and this repo has no
measurement above 1024 with the cap on. Without a cap, 21 of 30 xhigh generations on crow-nest
ended at `max_tokens` 16384 with no answer text (#80). `tools/check_operating_point.py` checks
that this table matches the manifest.

Two questions about this table are open and unmeasured:

- **The 1024 budget binds** (#245). In a replay of the 2026-09-22 diorama session on crow-nest
  (branch `meas-0923`, 2026-09-22 22:51-23:08 UTC; thinking high = xhigh, budget 1024, min_p 0.0,
  presence 0.0, `max_tokens` 16384; 8 seeds + greedy per point) the budget force-closed the
  thinking block in 0 of 9 rounds at K=2 (6,774 prompt tokens), 8 of 9 at K=26 (24,446) and 1 of 9
  at K=69 (39,309). All 8 closed rounds at K=26 still made a tool call; the one closed round at
  K=69 (seed 2) was the only round of 27 that ended without one. No budget other than 1024 has
  been measured with thinking on at this point.
- **`presence_penalty` 1.5 in `sampling_no_thinking`** (#246). The unused non-thinking row is
  the card's and is what Crow would send the moment a point is flipped to `none`. crow-nest #91
  removed the same 1.5 from serve's absent-field default on the suspicion that it pushes digits
  off the answer; no measurement at 1.5 exists for tool-call corruption. Decide before flipping
  a point to `none`.

## DeepSeek-V4-Flash-0731

Not the operating point, and it has not been since 2.0.0. It is kept current because
`install.ps1` still sets this server up.

| | |
|---|---|
| Model | `DeepSeek-V4-Flash-0731`, `UD-IQ2_XXS` |
| Architecture | MoE, 304B total, 13.3B active |
| Experts | streamed off the SSD, not resident |
| Port | 8081 |
| Context | `-c 200000`, one slot (`-np 1`) |
| KV | f16 |
| Template | `manifests/0731-chat-template.jinja` — the GGUF's embedded one fails its own golden vector 4 |
| Source of truth | [`../manifests/operating-point.json`](../manifests/operating-point.json), key `operating-point` |

### Model

```powershell
hf download unsloth/DeepSeek-V4-Flash-0731-GGUF --include "*UD-IQ2_XXS*" --local-dir $env:LOCALAPPDATA\Crow\models\0731-gguf
```

### By hand

```powershell
$env:LOCALAPPDATA\Crow\bin\llama-server.exe `
  -m $env:LOCALAPPDATA\Crow\models\0731-gguf\UD-IQ2_XXS\DeepSeek-V4-Flash-0731-UD-IQ2_XXS-00001-of-00003.gguf `
  --port 8081 -c 200000 -ngl 99 -np 1 --jinja `
  --slot-save-path $env:LOCALAPPDATA\Crow\session `
  --chat-template-file $env:LOCALAPPDATA\Crow\manifests\0731-chat-template.jinja `
  --moe-stream --moe-stream-cache 58s --moe-stream-io-threads 8 --moe-stream-direct `
  --moe-stream-l2 32
```

### Flags this model needs and Qwen does not

| flag | value | why |
|---|---|---|
| `--moe-stream` | on | routes expert tensors through a slot cache. Qwen has no expert tensors |
| `--moe-stream-cache` | `58s` | 58 slots. Measured: 18.03 tok/s against 11.04 at the earlier value |
| `--moe-stream-io-threads` | `8` | |
| `--moe-stream-direct` | on | |
| `--moe-stream-l2` | `32` | computed by `install.ps1` from detected RAM; the manifest records this machine's value |
| `--chat-template-file` | path | the embedded template fails golden vector 4 |
| `--spec-type` | absent | its speculation path needs a separate draft model and costs 6.06 % |

### Reasoning levels

| rows offered | collapses |
|---|---|
| `low` (default), `max` | `off`, `low`, `high` all render the same prompt |

### Numbers

| | |
|---|---|
| decode, 1,653 tokens of context | 74.09 tok/s |
| decode, 35,984 tokens | 64.50 tok/s |
| expert cache at 58 slots vs the earlier value | 18.03 vs 11.04 tok/s |
| speculation | not used — 6.06 % cost, separate draft model |

### Not measured

| open | |
|---|---|
| this model under `--spec-type` | never run to completion |
| the host RAM tier's effect | flag present, contribution unseparated |

---

## How the Flash-Next pin got here (#140, #159)

73.45 GiB in 3 shards, `UD-Q2_K_XL`, arch `qwen4exp` — 48 layers, 512 experts per
layer, 10 active, a shared expert per layer. **No fork any more:** PR #27742
merged into mainline llama.cpp on 2026-08-29, and the line above runs that merge
commit, `6c84c7d5d`. The shipped binary still cannot load it -- that one is
`b10269` from 2026-08-06. License is `qwen-community-1.0`, not apache-2.0.

**The commit is pinned, not the tag -- and the reason changed on 2026-09-01.**
`b10687`, one day younger, aborts during warmup with
`ggml_cuda_compute_forward: MUL_MAT failed`. Until 2026-09-01 that was attributed
to #27880 "reduce number of graph splits", the only `qwen4exp` change between the
two commits. The attribution was an A/B across a full day of mainline, and it was
wrong: #27880 isolated on this pin boots, survives the full CUDA warmup and
serves (four boots, `crow-lab/runs/2026-09-01-probe-27880/`). What kills `b10687`
on this card is not attributed, so the pin stays where it is.

Ten boots on the bare merge commit, one 31,979-token turn each on a cold cache:
**10/10 clean, prefill 959.81 tok/s mean (945.67-995.29), decode 28.60
(27.31-29.74), VRAM 27,988 MiB, load 71.8 s** -- inside the spreads of build 439
on both figures. Raw rows:
`crow-lab/runs/2026-08-30-merge-qwen4exp/boot-series.csv`.

**The pin carries two patches.**

*PR #28040* -- qwen4exp's PLE n-gram embedding calls `get_prev_tokens()` on every
graph build, and at the bare pin that walks *every* used cell of the KV cache once
per decoded token, on the critical path. #28040 resolves it in O(log n) from the
sequence position index. It replaced the closed draft #27992 on 2026-09-01,
measured at parity: fixed term +0.6 % against 1.335 ms of spread inside one arm.
Ported by hand (9 of 10 hunks), +40 -94 against the pin. The closed PR's unit
test, ported across implementations, passes 9,480 lookups with 0 failures, and a
deliberate off-by-one turns 3,416 of them red.

*PR #27880* -- hoists the PLE embedding out of the per-layer loop into the token
embedding's graph split: **62 graph splits per decoded token instead of 64** (92
instead of 94 in prefill). Merged upstream 2026-08-28, applied to the pin with zero
hunks by hand. Measured 2026-09-01, four boots interleaved against the #28040-only
binary, six depths, 200 new tokens: **fixed term 23.072 ms against 24.061 in the
one clean pair (-0.99 ms, -4.1 %)**, against 1.354 ms of spread inside the arm --
free and not worse; whether it is 1 ms better is below what two rounds resolve.
Decode at 30k depth 40.96 against 40.78 tok/s. Raw rows:
`crow-lab/runs/2026-09-01-levers2-159/`.

**The last lever inside the engine is dead, by a direct switch.** The same tree
built with `GGML_OPENMP=OFF` -- ggml's own threadpool instead of `vcomp140.dll`,
verified by the missing `OPENMP` field in `system_info` -- costs +4 to +6 ms per
token at 30k-140k depth in both rounds and a 42-70 ms first-request warm-up;
`--poll 100` on top is worse. With `OMP_WAIT_POLICY=PASSIVE` at -16.3 % from the
same day, all three synchronizations available on this machine are measured and
the default is the fastest. The fixed term of 23-24 ms per token is where this
engine stays (#159, #186).

Ten-task gate against this line, 2026-09-01, same-session control interleaved:
10/10 in both passes on the new binary and 10/10 in both same-session control passes; completion-token counts per task identical across all four cells (518 226 304 483 632 496 354 252 384 1032); wall clock 119.7 / 116.0 s against 121.4 / 119.3 s for the control (−1.4 % / −2.8 %). Raw rows: `crow-lab/runs/2026-09-01-gate-27880/`.

*Interleaved on purpose.* This machine drifted -5.0 % prefill and -5.5 % decode
within one day -- larger than the effect and enough to flip its sign. On 2026-08-30
a control from another session would have produced the wrong verdict three times
over. No arm is compared against a control from another session.

The binary the 2026-09-01 series was measured on, for the record:

    C:\Users\robin\dev\crow-lab\wt-27880\build-27880\bin\Release\llama-server.exe `
      -m <models>\qwen-next-gguf\UD-Q2_K_XL\Qwen3.8-Flash-Next-UD-Q2_K_XL-00001-of-00003.gguf `
      --port 8083 -c 200000 -b 2048 -ub 2048 `
      -ctk q8_0 -ctv q8_0 -ncmoe 30 `
      --fit off --load-mode none -np 1 `
      --mmproj <models>\qwen-next-gguf\mmproj-F16.gguf `
      --jinja

No env prelude: `CUDA_CACHE_DISABLE=1` stood here for three hours on
2026-08-28 night and was measured WORSE -- without the driver cache every
fresh kernel shape hits the driver JIT, and this machine's JIT is what rolls
CUDA 303. The corrupt cache that killed boots that evening was set aside
(`ComputeCache.korrupt-2026-08-28`); a fresh cache boots and serves without
any flag. The manifest's `_env_history` carries the numbers.

### Numbers at the earlier placement (2026-08-28, build 439, driver 616.56, 10-boot series)

| | |
|---|---|
| prefill, 31,979 tokens cold | 964.8 tok/s mean of 10 (949.99–981.03) |
| decode | 28.61 tok/s mean of 10 (27.01–29.37) |
| VRAM after the turn | 28.4 GiB, 4.2 free |
| RAM | ~46.6 of 63.38 GiB |
| boots | 10/10 |

`--load-mode none` is the row that matters: mmap at the RAM ceiling reads the
NVMe into every token — identical lines spread 19–31 tok/s on page-cache luck
until the CPU experts sit in anonymous memory. Speculation buys nothing here:
the GGUF ships no MTP head, ngram nets −2 %, and a 27B drafter halves decode at
0.775 acceptance. Details: the three measurement comments on #140.

---

## Measurement conditions

One user, `-np 1`, identical prompt, the server restarted cold per arm, cross-checked against
the server's own `eval time` blocks. Arms are interleaved inside one session, never compared
against a control from another one — this machine drifted 5 % within a single day, which is
larger than most effects measured here.

Every number with its full conditions: [Measurements](measurements/README.md). The placement
sweep that produced `-ncmoe 30 -b/-ub 2048`:
[flash-next-placement.md](measurements/flash-next-placement.md), 27 runs.

---

## Related

| | |
|---|---|
| [Server flags](reference/server-flags.md) | what each flag above is for, with the measurement behind it |
| [Install](user-guide/install.md) | requirements, the installers, the model download |
| [Linux](user-guide/linux.md) | paths, the engine build, the window on Wayland |
| [Measurements](measurements/README.md) | every number with its conditions |
