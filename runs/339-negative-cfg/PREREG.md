# PREREG — #339: negative prompt at txt_cfg 1.0 / 3.0 / 6.0, judged blind

Written 2026-10-06T20:05+0200, before any guided picture exists on this stack: Crow has never sent
`txt_cfg > 1` (#339 *Evidence*), and nothing below has been run. Ticket:
https://github.com/nibor1896/Crow/issues/339 (body *Expected result*). Runner:
`tools/measure_negative_cfg.py`, committed with this file; its tests: `tools/test_measure_negative_cfg.py`.
Checked against `5d0991e` (main): `_image_sample_params` is now `cli/crow_core.py:13909-13913`,
`tool_generate_image` `:13942-13977`, the warm-up literal `:12788-12792`; the behaviour the ticket cites
is unchanged. Changes to this file are allowed only as a dated addendum at the end, written before the
result they judge.

## Acceptance criteria (verbatim from the ticket, *Expected result*)

Thresholds fixed here, before any guided result exists. Amendments only as dated, visible edits written before the result they judge.

Measurement (same `sd-server` 2f88688 binary and argv as `docs/reference/tools.md:202`, one run at a time, arms alternated, 2752×1536, 40 steps, euler, 3 `txt_cfg` values {1.0, 3.0, 6.0}, the 27B resident as in production, Windows RTX 5090):
- 10 prompt/seed pairs, each naming one object to exclude. A pair counts only if the `txt_cfg` 1.0 arm (no negative effect possible) shows that object; pairs that do not are replaced.
- Per guided arm record: object absent (yes/no, robin judges, n = 10), frame-wide grain or visible degradation (robin judges, n = 10), wall time warm, card peak MiB, any OOM line in `sd-server-8097.log`.

Pass for a `txt_cfg` value, all required:
1. object absent in at least 8 of 10 pairs;
2. 0 of 10 with frame-wide grain or clear degradation against the 1.0 arm;
3. warm time at most 2.2× the 1.0 arm at the same size (today 155.2 s warm on Linux; the Windows 1.0 baseline is measured in the same run);
4. 0 OOM lines, card peak below the card's capacity beside the 27B.

The lowest passing value becomes `IMAGE_NEGATIVE_CFG`. No value passing means close as A.

## The arms (fixed now)

- **1.0** = the body `tool_generate_image` sends today, byte for byte, and no `negative_prompt`:
  `{"prompt", "width": 2752, "height": 1536, "seed", "sample_params": {"sample_steps": 40, "sample_method": "euler", "guidance": {"txt_cfg": 1.0}}}`.
  The runner refuses to start if its 1.0 body differs from what `tool_generate_image` builds at the
  checked-out commit (`validate_plan`, caught with the request patched out, no server).
  Why no `negative_prompt` here: option B sends none when none is given, and at `txt_cfg` 1.0 sd-server
  never encodes one (`src/pipeline/request.cpp:304`, read at 2f88688, not run).
- **3.0** and **6.0** = the same body plus `"negative_prompt": "<the pair's object>"` and that `txt_cfg`:
  exactly option B's request. Nothing else differs (`validate_plan` checks it).
- Every job goes through `crow_core._run_image_job` (POST `/sdcpp/v1/img_gen`, poll `/sdcpp/v1/jobs/{id}`
  every 0.5 s), the tool's own path. `crow_core` is not changed for this measurement.

## How the criteria are read (fixed now, not after the result)

- **Pair validity.** A pair is valid when robin, judging blind, answers *object visible: yes* for its
  1.0 picture. The 10 **counted** pairs are the first 10 valid ones in the order P01…P10, R01…R05.
  An invalid pair is reported with all three of its pictures and replaced by the next unmeasured
  reserve, in order, in a further round (`run --round N --pairs R01,…`). If the reserves run out
  before 10 pairs are valid, the result is *incomplete* and nothing passes; a new pair needs a dated
  addendum before it runs.
- **Criterion 1** (absent ≥ 8 of 10): over the 10 counted pairs, a guided picture counts as absent when
  robin answers *object visible: no*. A guided job without a picture counts as not absent.
- **Criterion 2** (0 of 10 degraded): over the 10 counted pairs, a guided picture fails when robin marks
  it *degraded* (frame-wide grain or clear degradation, judged against the other two pictures of its
  row, see *Blind judging*), and a guided job without a picture fails. A 1.0 picture marked degraded is
  reported as a finding; it does not excuse a guided one.
- **Criterion 3** (time ≤ 2.2×): ratio = median wall time of the arm's 10 jobs / median wall time of
  the 1.0 arm's 10 jobs, both from **round 1** (the 10 primary pairs, valid or not: time does not
  depend on what robin sees), completed jobs only; pass when ratio ≤ 2.2. Wall time = from the POST of
  the job to the poll that sees `completed` (`_run_image_job`'s own clock, resolution 0.5 s). Every
  counted job is warm: two warm-ups run first (below). The server's own `generate_image completed in`
  time is recorded beside it. Replacement rounds do not enter criterion 3 (too few jobs to keep a pair
  out of the conditioning cache, see *Order*).
- **Criterion 4** (memory): over every job of the arm in every round, 0 OOM lines **and** a card peak
  strictly below the card's `memory.total`. An OOM line is what `crow_core._image_oom_cause` treats as
  one: a line in the sd-server log since the job's start holding `cudaMalloc failed: out of memory` or
  `failed to allocate`, unless a level other than `ERROR` stands before it. A `ggml_cuda_host_malloc:
  failed ... pinned memory` line at VERBOSE is recorded apart and reported, not gated. Card peak =
  the highest `nvidia-smi --query-gpu=memory.used` sample (whole card, every 500 ms) between the job's
  POST and its end; no sample at all fails the criterion (not measured is not a pass).
- **Failures.** A job that fails (OOM, error, 20 min without a result) is a result row and is never run
  again. The series continues; 3 failed jobs in a row end it (reported as incomplete). If the server
  stops answering, `crow_core.image_server_start` brings one up (the tool's path), the restart is a row,
  and the two warm-ups run again before the next job.

## Runtime and settings

- Machine as in #320: Windows 11, RTX 5090 (32,607 MiB), 63 GB host without a pagefile. The runner
  records GPU name, `memory.total`, `memory.used` before the first job, driver, git HEAD, Crow version,
  both servers' command lines, the sd-server binary's sha256 and this file's sha256 in `run.json`.
- **The Image Stack as Crow starts it**: crow-nest `serve` with the 27B (`Qwen3.8-27B-CNQ4.5.cnq`) on
  8099 and sd-server 2f88688 on 8097 with `crow_core.image_server_command` + Windows `--mmap`
  (= `docs/reference/tools.md:202`). The runner refuses unless: the active point is `image-stack` and not
  in video mode; exactly one crow-nest serve runs and `/props` names the 27B and `/health` is ok; no
  llama-server and no ComfyUI run; at most one sd-server runs and its flags and non-path values equal
  `image_server_command`; nvidia-smi answers; tracked files are unmodified (the committed script and
  this file are what runs).
- **Warm-ups, not counted:** `crow_core.image_server_warm`'s own job (256×256, 1 step, `txt_cfg` 1.0,
  "a plain grey square", seed 1), then the same with `txt_cfg` 6.0 and `negative_prompt` "watermark", so
  the first guided job pays no first-use cost. If the sd-server log does not record them
  (`generate_image completed in`), the log is not the running server's and the run stops before the
  first counted job.
- One engine at a time; no other GPU work and no image or video tool use during the series. The Crow
  window may be open with no turn running.

## Pairs (each prompt implies its object without naming it)

P01 is the ticket's own live-check pair. R01–R05 are reserves, used only to replace invalid pairs, in
this order.

| Pair | Seed | Prompt | Excluded object (`negative_prompt`) |
|---|---|---|---|
| P01 | 7 | a quiet harbour at dawn | boats |
| P02 | 3390002 | a busy city street at night in the rain, neon signs reflected on the wet asphalt | cars |
| P03 | 3390003 | an airport apron at sunset, seen through the terminal window | airplanes |
| P04 | 3390004 | a coral reef aquarium in a dark room, lit from above | fish |
| P05 | 3390005 | a children's birthday party in a sunny garden | balloons |
| P06 | 3390006 | an old town square in Europe on a summer afternoon | people |
| P07 | 3390007 | a tropical beach with turquoise water and white sand | palm trees |
| P08 | 3390008 | a railway station platform in the morning | trains |
| P09 | 3390009 | a medieval castle on a green hill under a blue sky | flags |
| P10 | 3390010 | a still life of a fruit bowl on a wooden kitchen table | bananas |
| R01 | 3390101 | a shop front on a high street, photographed straight on | text |
| R02 | 3390102 | a cozy reading corner with an armchair by a window | books |
| R03 | 3390103 | a ski slope on a bright winter day | skiers |
| R04 | 3390104 | a garden table set for afternoon tea | teacups |
| R05 | 3390105 | a kitchen counter with fresh vegetables ready for cooking | tomatoes |

## Order (alternating)

Three passes over the pairs of a round; pair *i* (0-based) in pass *r* gets `ARMS[(i + r·s) mod 3]`,
`ARMS = (1.0, 3.0, 6.0)`, `s = 1`, or `s = 2` when `(k − 1) mod 3 = 1` for *k* pairs (otherwise one arm
would repeat across a pass boundary). So every pair gets every arm once, no two neighbouring jobs share
an arm, every pass carries all three arms (drift over the ~3 h spreads over all arms), and a pair's
three jobs are *k* jobs apart. That last point is for sd-server's conditioning cache: 2f88688 keeps the
last 4 conditionings, LRU, keyed by the prompt text (`src/conditioning/conditioning_cache.h`,
default capacity 4, `include/stable-diffusion.h:252`; the production argv does not change it). Ten
pairs apart, no counted job of round 1 can read its prompt from the cache; each job records the log's
`conditioning cache hit` lines as a check (expected 0 in round 1).

Round 1, the order the runner executes (`python tools/measure_negative_cfg.py plan` prints it with
each body's sha256):

| Seq | Pair | txt_cfg |
|---|---|---|
| 1 | P01 | 1.0 |
| 2 | P02 | 3.0 |
| 3 | P03 | 6.0 |
| 4 | P04 | 1.0 |
| 5 | P05 | 3.0 |
| 6 | P06 | 6.0 |
| 7 | P07 | 1.0 |
| 8 | P08 | 3.0 |
| 9 | P09 | 6.0 |
| 10 | P10 | 1.0 |
| 11 | P01 | 3.0 |
| 12 | P02 | 6.0 |
| 13 | P03 | 1.0 |
| 14 | P04 | 3.0 |
| 15 | P05 | 6.0 |
| 16 | P06 | 1.0 |
| 17 | P07 | 3.0 |
| 18 | P08 | 6.0 |
| 19 | P09 | 1.0 |
| 20 | P10 | 3.0 |
| 21 | P01 | 6.0 |
| 22 | P02 | 1.0 |
| 23 | P03 | 3.0 |
| 24 | P04 | 6.0 |
| 25 | P05 | 1.0 |
| 26 | P06 | 3.0 |
| 27 | P07 | 6.0 |
| 28 | P08 | 1.0 |
| 29 | P09 | 3.0 |
| 30 | P10 | 6.0 |

## Output layout

```
runs/339-negative-cfg/
  PREREG.md                 this file (committed, forced past the runs/ ignore rule)
  round-1/                  git-ignored, like every run
    run.json                the plan with every body, the preflight facts, thresholds, start time
    results.jsonl           one row per warm-up, restart and job: seq, pair, txt_cfg, seed, prompt,
                            negative_prompt, body sha256, start/end, wall_s, server_s, status, error,
                            peak_mib, oom_lines, pinned_lines, cache_hits, image path, sha256, bytes
    vram.csv                every nvidia-smi sample (unix time, monotonic time, MiB used)
    images/P01-cfg1.png …   the pictures as the server returned them (labelled: robin does not open these)
    sheet/index.html        what robin judges: S01-A.png … S10-C.png, answers.json
    sealed-key.json         slot/letter → pair, txt_cfg, raw file, both sha256
    sealed-key.sha256       the key's sha256, written at sealing
  round-2/ …                replacement rounds, same layout
  score.json                the verdict (score)
```

## Blind judging protocol

1. When the last job of a round has a row, the runner seals it: the pairs go to slots S01… in a shuffled
   order and each slot's three pictures to A/B/C in a shuffled order (`random.SystemRandom`, no seed
   anyone could replay). The sheet holds copies **without PNG text chunks**: sd-server writes the
   generation parameters, negative prompt and CFG among them, into every PNG it returns
   (`examples/server/async_jobs.cpp:206`, `embed_image_metadata` defaults to true). The key goes to
   `sealed-key.json`, its sha256 to `sealed-key.sha256` and to the console.
2. The lead posts that sha256 on #339 **before** robin sees the sheet.
3. robin opens only `sheet/index.html` (one row per slot, its question, the three pictures, each
   clickable at full size) and answers two questions per picture: *Do you see any \<object\> anywhere in
   the picture?* and *frame-wide grain or clear degradation, compared with the other two pictures of the
   row?* — yes/no each. The answers go into `sheet/answers.json` (robin, or the lead typing in exactly
   what robin dictates). robin does not open `images/`, `results.jsonl`, `run.json` or the key before
   every answer is in.
4. Only then `python tools/measure_negative_cfg.py score runs/339-negative-cfg/round-1 [round-2 …]
   --expect-sha256 <posted sha256> …`: it checks the key against `sealed-key.sha256` and the posted
   value, refuses blank answers, unblinds and prints the four criteria per `txt_cfg` and the verdict.
5. Limits of the blind: the effect itself is visible (a row's picture with the object is likely the
   1.0 one), and a failed job shows as a missing picture. What stays hidden is which guided picture is
   3.0 and which is 6.0, and which slot is which pair.

## Duration and resources (estimate, not a measurement)

30 jobs: about 2.6–3.3 h of GPU time. 1.0 job 218.3 s warm on Windows (#320, mean of 218.1 and 218.5);
a guided job 1.66× of it if the second pass costs the 40 steps at 3.57 s/it again (Linux, #308; not
measured on Windows), 2.2× at the ticket's limit. Plus ~1 min of warm-ups. A replacement pair adds
~16–20 min. VRAM: the whole card; the 1.0 arm peaked at 31,861 MiB of 32,607 beside the 27B on Windows
(#320). The guided arms are not measured: sd.cpp keeps a separate prefix cache per condition, 1.0625 GiB
each at `q8_0` for a 4096-token prefix (`docs/qwen_image_2.1.md`), which is what criterion 4 decides.

## Not measured here

`edit_image` with a negative prompt; `img_cfg` and `distilled_guidance`; Linux; sizes other than
2752×1536; values other than 3.0 and 6.0; more than one seed per prompt; more than one day.
