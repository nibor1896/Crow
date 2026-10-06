# PREREG — #346: LTX prompt enhance A/B/C for animate_image

Written 2026-10-06 between 20:00 and 20:30 +0200 on branch `t-346-prep` (from `main` 5d0991e), before the e2b
text encoder was downloaded and before any clip of this series exists; the time of the commit that adds this
file is authoritative.
Ticket: https://github.com/nibor1896/Crow/issues/346 (*Proposed fix* 1-3, *Expected result*). Refs #340.
Runner: `tools/enhance_ab.py`, same commit. Changes to this file only as a dated addendum at the end, written
before the result it judges.

## Question

Does LTX-2.5's prompt enhancer (and/or the template's lower resolution) fix the instruction following of
`animate_image`? Answered by the decision rule below, fixed before the first clip.

## Read from the template before writing this (corrects the ticket's premise, not its plan)

Read 2026-10-06 from `comfyui_workflow_templates_json` 0.1.96, `templates/video_ltx2_5_i2v.json`
(sha256 `4dc46671feee1da4a3369b24284cc8a9ca3eae9266eeb0da072aca8a55b7a866`), in ComfyUI v0.38.0 portable (`6b747c0`):

1. **The template ships with prompt enhance OFF.** Subgraph node 383's own widget reads `true`, but its `value`
   input is linked to the subgraph input `value_1` (link 766), and the top-level node 398 sets `value_1` to `false`
   (`widgets_values[1]`). The template's own note: "prompt_enhance *(Optional, off by default)*". Phase 0's PREREG
   (4be3203) recorded the same. What differs in Crow: the switch's `on_true` (398:382) points at the raw prompt
   instead of node 380, so enhance cannot be switched on. Crow's default equals the template's default.
2. **The template's size comes from the ResolutionSelector, not from 1280x720.** Nodes 372/360 show 1280/720, but
   their inputs are linked to node 403 (16:9, 0.9 MP, multiple 32), which the template's own table gives as 1280x736.
3. **What renders (read from source, not measured).** `EmptyLTXVLatentVideo` (`comfy_extras/nodes_lt.py:83`) floors
   `height // 32`; stage 1 runs at half size (398:353/398:355, `a/2`), the x2 latent upscaler doubles it.
   720 → 360 → 11 latent rows → 704 px; 736 → 368 → 11 → 704 px. The ticket's 1280x720 and the template's 0.9 MP
   therefore both render **1280x704** frames. Crow's 1920x1088 renders 1920x1088 (Phase 0, measured). The series
   reads every clip's size back with ffprobe.

Arm B therefore tests the template's *optional* enhancer path. The arms and the decision rule stand as the ticket
wrote them.

## Arms (verbatim from the ticket)

> - A = Crow's workflow as is
> - B = prompt enhance on (switch `398:382` → `TextGenerateLTX2Prompt` with the e2b CLIP, template settings)
> - C = B plus 1280x720

| Arm | File | sha256 of the canonical JSON | Delta |
|---|---|---|---|
| A | `arm-A.json` | `5cda669f5a705083fab04206e70aee5f396b54b98a1d8b9ab225e2d50226eedf` | byte copy of `cli/workflows/ltx25_i2v_api.json` at 5d0991e |
| B | `arm-B.json` | `51e22dd8c067fffd1803c4a5a56974b8f6d24f19f7de3ab9505f4e9c669ffc67` | A + nodes `398:393` and `398:380` (below); `398:383` value `true`; `398:382` `on_true` → `["398:380", 0]` |
| C | `arm-C.json` | `b86942b65c03b95fd8abb4f8c32f5fdd5e5afe37feb54d9f7b9844145a02631e` | B + `398:372` value `1280`, `398:360` value `720` (no longer linked to 403) |

Canonical JSON = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, UTF-8; a CRLF
checkout changes the file bytes, not this hash.

The enhancer, as the template has it (subgraph nodes 393 and 380):

- `398:393` `CLIPLoader`: `clip_name` `gemma4_e2b_it_int8_convrot.safetensors`, `type` `ltxv`, `device` `default`.
- `398:380` `TextGenerateLTX2Prompt`: `max_length` 600, `sampling_mode` `on` with `temperature` 0.7, `top_k` 64,
  `top_p` 0.95, `min_p` 0.05, `repetition_penalty` 1.15, `seed` 0, `presence_penalty` 0; `thinking` false,
  `use_default_template` true; `mtp` not set (the template predates that input, so the node's default `auto`
  applies); `clip` ← 398:393, `image` ← 398:350 (`LTXVPreprocess`, template link 757), `prompt` ← 398:376.
- Sources: the values are the template's node 380 `widgets_values`; their names, in that order, are those of
  ComfyUI's own blueprint `blueprints/Image to Video (LTX-2.5).json`; the input names are checked against
  `comfy_extras/nodes_textgen.py` @ v0.38.0 (local copy equal to GitHub tag `v0.38.0` modulo CRLF, LF sha256
  `ce41b40babe829cf8773aee3c3e43079f91205db921f6d964685e5fb0e5d7f54`); a DynamicCombo child travels as
  `sampling_mode.<child>` (`comfy_api/latest/_io.py`, `finalize_prefix`). With Gemma 4 and an image the node writes
  with `LTX24_I2V_SYSTEM_PROMPT` (`nodes_textgen.py:194`, `:243-246`).

Everything else is identical to A; `crow_core.video_workflow` sets image, motion, seconds, seed, node 403 and the
save prefix per call, in every arm. `python tools/enhance_ab.py --selftest` holds the three files against this
delta, against the template and the blueprint, and against the node source.

## Stills, seeds, motion texts

Per still one fixed seed and one fixed motion text: exactly what reached LTX in robin's runs of 2026-10-03, read
from the `prompt` tag ComfyUI's SaveVideo wrote into each clip (398:376 motion, 398:339 seed). Each still's bytes
equal the copy those runs uploaded into ComfyUI's input folder. All three are 2752x1536 PNG (16:9); 5 s each.

| Still | sha256 | Bytes | File (under `~`) | Source clip | Seed |
|---|---|---|---|---|---|
| S1 the key crow | `1de92cb1fd06dfb1ead957371ab94bed619f614055f730dcb36436e3a8b24be9` | 7,379,547 | `images/20261003-123648-a-still-from-a-high-budget-3d-animated.png` | `videos/20261003-123833-the-black-crow-tilts-its-head-curiously.mp4` | 746329003 |
| S2 2B with the crow landing | `334d96657c576d851ee3594323eb3b2fd35300cb6a38dd141a07c76dbcfb8341` | 9,761,794 | `Desktop/ct/images/20261003-114913-high-quality-anime-key-visual-cinematic.png` | `Desktop/ct/videos/20261003-115119-2b-slowly-raises-her-left-arm-out-to-the.mp4` | 497572401 |
| S3 2B with the sign | `347949c4344c4da5ebe88e1d5321e7caebb6f27dd252d1f46778311d5449aa5f` | 11,056,279 | `Desktop/ct/images/20261002-084445-ultra-high-resolution-wide-16-9 - Kopie.png` (byte-equal to Phase 0 still E) | `Desktop/ct/videos/20261003-121512-2b-keeps-sitting-on-the-mossy-concrete.mp4` | 912134647 |

S3's seed, by rule: two runs carry this exact text, 12:15:12 (seed 912134647) and 12:17:52 (seed 1939543149), both
after the verbatim fix 6e46dd1 (12:12:49). The earlier one is taken, by that rule alone. The three runs before
(12:03-12:06) carried 9B rewrites and are not used.

Motion texts, verbatim, one line each:

- **S1:** The black crow tilts its head curiously to one side, looks at the brass key, hops one small step forward, bends down and picks up the key in its beak, then lifts its head and holds the key proudly. The desk, the window, the plant and the room stay completely still. The camera holds still. No new objects, no cuts. Sound: two soft taps of the crow's feet hopping on the wooden desk, a light metallic clink as the key is picked up, one short cheerful caw, a quiet calm room, no static, no hiss, no music, no speech.
- **S2:** 2B slowly raises her left arm out to the side at shoulder height with the gloved hand open and the back of the hand up. The black crow flies in from the right, beats its wings a few times as it slows down, and lands on her raised left hand and wrist, gripping it, then folds its wings and settles. Her right hand keeps holding the katana pointing down. Her blindfold and headband stay in place, her hair only moves slightly. The background stays completely still: the city, the sun and the sky do not move. The camera holds still. No new objects, no cuts. Sound: the heavy flapping of the crow's wings coming closer, one short caw from the crow, a soft creak of the leather glove as the crow lands, a faint quiet wind, otherwise quiet, no static, no hiss, no music, no speech.
- **S3:** 2B keeps sitting on the mossy concrete block with her chin resting on her left hand, unchanged. Only the toe of her right black boot taps up and down slowly a few times, as if she is waiting. The black crow standing in the grass on the right bends its head and preens the feathers under its right wing with its beak. The sign, the grass, the clouds and the sky stay completely still. The camera holds still. No new objects, no cuts. Sound: a soft breeze in the grass, the quiet rustle of the crow's feathers, a faint tap of the boot, no music, no speech.

## Procedure

- Machine: RTX 5090 (32,607 MiB), 63.4 GiB host RAM, Windows 11, as in Phase 0. ComfyUI v0.38.0 portable as
  CrowSetup installed it (`%LOCALAPPDATA%\Crow\comfyui`), models through its `extra_model_paths.yaml`
  (`%LOCALAPPDATA%\Crow\models\ltx-2.5`).
- Before the first clip: the Media Stack is booted from Crow's start window (point `media-stack`, the 9B up);
  Crow's window is idle (no turn) or closed; nothing else uses the GPU; the e2b file is on disk (*What the Go
  needs*). The runner refuses to start otherwise, and also when the selftest fails or `results.jsonl` exists.
- **Every clip is one `crow_core.tool_animate_image` call** (image, motion, seconds 5, resolution `1080p`, seed),
  with `crow_core.VIDEO_WORKFLOW` naming the arm's file for that call (`tools/enhance_ab.py`, `run_clip`). Inside the
  call `use_mode` ends the 9B and any sd-server, starts ComfyUI, renders, ends ComfyUI and brings the 9B back:
  Crow's own path. For arm C the tool's result line still says 1920x1088 (it computes the size from its
  `resolution` argument); the size that counts is the one read back from the clip.
- **"`POST /free` before every clip"** (ticket) is read as: every clip starts in a freshly started ComfyUI process
  with no model in VRAM. That is what `/free` asks for, and stronger: the process that held the previous clip's
  models is gone. Models load from the OS file cache or disk, as in Crow's use. One engine at a time is what
  `use_mode` guarantees.
- **Run order**, a 3x3 Latin square (arms alternated per still; every arm once per still and once in each
  position): `S1-A S1-B S1-C S2-B S2-C S2-A S3-C S3-A S3-B`.
- A failure (ComfyUI error, out of memory, a crashed server, the tool's 30-minute limit) is a result row, not a
  reason to stop: no re-run, the series continues. A clip that did not render counts as **no** on (a), (b) and (c)
  for its arm.
- Ctrl+C stops the series: the running clip is interrupted and the 9B comes back. A stopped series gets no sheet
  and no key; running it again is a dated addendum.

## Recorded per clip (`results.jsonl`, git-ignored, beside this file)

Still, arm, seed, order index, start and end; `call_s`, the wall clock of the whole call including both mode
switches; `render_s`, `POST /prompt` until the job is done (`crow_core._run_video_job`); `peak_vram_mib`, the whole
card during the call (nvidia-smi every 500 ms, `vram-<clip>.csv`); the API prompt as sent
(`workflow-api-<clip>.json`, canonical sha256 in the row); `caption`, the text the switch handed the 12B encoder
(Preview as Text, 398:381, from `/history`) — for B and C the enhanced caption; the output file and its width,
height and frame count read back with ffprobe; the tool's result line.

## Blind protocol

- After the ninth clip the runner shuffles the rendered clips (`random.SystemRandom`), copies each to
  `rating/clip-NN.mp4` with the container tags stripped (SaveVideo's `prompt` tag names the arm; stream copy, no
  re-encode) and its still to `rating/still-NN.png`, writes `rating-key.json` (name → clip, still, arm, seed, file)
  **before** the sheet, and prints the key's sha256, also written to `rating-key.sha256`. That sha256 is posted on
  #346 before robin opens the sheet: the seal.
- robin rates `rating/index.html`: per clip the still, the motion text and the clip; three yes/no questions and an
  optional note. The page copies the answers as JSON; they are saved as `rating-answers.json`.
- Said now, a limit: arm C is not fully blind. Its 1280x704 frames are softer than 1920x1088, and a player shows the
  size. The sheet shows every clip at the same display width.
- Unblinding: `python tools/enhance_ab.py --unblind` opens the key only if its sha256 equals the seal, refuses on
  any unanswered question, prints the tally and writes `tally.json`.

## Metric and decision rule (verbatim from the ticket, *Proposed fix* 2-3)

> 2. **Metric:** robin's blind rating per clip.
>    - (a) the requested action happened, yes/no
>    - (b) a named object keeps its identity, yes/no
>    - (c) the camera does what the text says, yes/no
>
>    Also recorded: wall clock per clip, peak VRAM, and B's enhanced caption (from ComfyUI history).
> 3. **Decision rules, fixed here:**
>    - **B or C wins** if it gets more yes votes than A on (a) **and** (b) summed over the three stills, without losing on (c).
>    - **Then the change in Crow:** download the e2b file in CrowSetup (`stack.json` entry, original source `Comfy-Org/gemma-4`), set the switch in `cli/workflows/ltx25_i2v_api.json`, and decide the resolution.
>    - **If B wins, check the verbatim rule too:** the user's text would then be rewritten by e2b. The enhancer's system prompt asks it to keep every element the user stated (`:194`). Whether it keeps a "Sound: …" sentence must be read off B's captions.

## How the questions and the rule are read (fixed now, not after the result)

- **(a)** is yes only if every action the motion text asks for happens (S1: tilts the head, hops a step, picks the
  key up in the beak, lifts the head holding it; S2: 2B raises her left arm, the crow flies in from the right, lands
  on her raised left hand and wrist, folds its wings; S3: the toe of her right boot taps, the crow preens under its
  right wing while 2B stays seated, chin on her left hand).
- **(b)** is yes only if every object the text names stays the same object for the whole clip: it does not turn
  into another object, split, duplicate, vanish or change hands (S1: the crow, the brass key, the desk, the window,
  the plant; S2: 2B, the crow, the katana in her right hand, her blindfold and headband; S3: 2B, her boot, the crow,
  the sign).
- **(c)** is yes only if the camera does what the text says. All three texts say "The camera holds still": no pan,
  tilt, zoom or push.
- **The rule.** Per arm X: `ab(X)` = yes votes on (a) plus yes votes on (b), summed over S1-S3 (0-6);
  `cam(X)` = yes votes on (c) (0-3). B or C wins if `ab(X) > ab(A)` and `cam(X) >= cam(A)`. Equal `ab` is no win.
  The other reading, "more yes than A on (a) alone and also on (b) alone", is not used: with n = 3 per arm, A at
  3/3 on either question would make a win impossible whatever the other question shows.
- **Both B and C win:** enhance goes on; the resolution is robin's decision, as the ticket leaves it ("decide the
  resolution"), with both tallies and C's measured times in front of him. **Only C wins:** the same, with the
  resolution question explicitly open. **Neither wins:** the ticket's "If no": a documented LTX-2.5 limit in
  `docs/operating-points.md` with the three failure kinds and the n.
- **The verbatim check**, reported and not gated: for every B and C clip, does the caption keep every element of the
  motion text, in particular its "Sound: …" sentence and "The camera holds still"? Read from `caption` in
  `results.jsonl`.
- **Limits, said now:** n = 1 clip per still and arm, one seed per still, one machine, one day. The result decides
  this ticket; it is not a rate.

## What the Go needs

1. **The download (robin's go):** `gemma4_e2b_it_int8_convrot.safetensors`
   - Source: `Comfy-Org/gemma-4`, the template's own model link. This int8-convrot file is Comfy-Org's ComfyUI
     packaging of `google/gemma-4-E2B-it` and is published only there. Pinned to revision
     `63d0f7c476756b88910170c1df75e2384ea1af31`:
     https://huggingface.co/Comfy-Org/gemma-4/resolve/63d0f7c476756b88910170c1df75e2384ea1af31/text_encoders/gemma4_e2b_it_int8_convrot.safetensors
   - 5,199,997,904 B (4.84 GiB), LFS sha256 `efeca0fcad2f863e5ed0a75e3af952b72bc963604c1dda6d20aee87a32b17566`;
     the repo is not gated (Hugging Face API `gated: false`, read 2026-10-06).
   - Licence: Apache-2.0. `Comfy-Org/gemma-4` card: `license: apache-2.0`; `google/gemma-4-E2B-it` card:
     `license: apache-2.0`, its `license_link` https://ai.google.dev/gemma/docs/gemma_4_license is titled
     "Apache License 2.0" (read 2026-10-06).
   - Destination: `%LOCALAPPDATA%\Crow\models\ltx-2.5\text_encoders\` (the `text_encoders` entry of CrowSetup's
     `extra_model_paths.yaml`). The runner checks size and sha256 before the first clip.
   - PowerShell:
     `curl.exe -L --fail -o "$env:LOCALAPPDATA\Crow\models\ltx-2.5\text_encoders\gemma4_e2b_it_int8_convrot.safetensors" "https://huggingface.co/Comfy-Org/gemma-4/resolve/63d0f7c476756b88910170c1df75e2384ea1af31/text_encoders/gemma4_e2b_it_int8_convrot.safetensors"`
   - This series adds nothing to `manifests/stack.json` or CrowSetup; that is the "then" of the decision rule.
2. **Boot the Media Stack** from Crow's start window (point `media-stack`).
3. **Run, from the repository root:** `python tools/enhance_ab.py --go`
4. **GPU time, estimated, not measured for B and C:**
   - Measured on Crow's path 2026-10-03 (n=1, a clip like arm A): ComfyUI up ≈16 s, render 73.3 s, the 9B back
     ≈8 s, so ≈100 s per clip.
   - B and C add the enhancer. The template's own note says it "adds ~1-2 min of generation time" (read, not
     measured), plus the e2b file's first read from disk.
   - C renders 1280x704, 43 % of the pixels of 1920x1088, so its sampling is shorter (not measured).
   - About 25 min for the nine clips (20-30 min), plus ≈1 min for hashing the e2b file before the first clip.
   - VRAM: Phase 0's 5 s clips at 1920x1088 without the enhancer peaked at 31,951-32,021 MiB of 32,607. Whether B
     fits without running out of memory is not measured; if it does not, that is a result row.
5. **robin rates** the nine clips blind, three yes/no questions each, after the seal is posted on #346.

## Out of scope

Any change to `cli/workflows/ltx25_i2v_api.json`, `manifests/stack.json`, CrowSetup or `cli/crow_core.py`: only
after the decision rule says so (the ticket's "Then"). Higher rungs (1440p, 4K) and a camera-control LoRA (ticket).
