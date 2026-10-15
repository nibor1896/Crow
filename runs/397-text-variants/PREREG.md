# PREREG — #397: text-only variants of Flash-Next and the 27B

Written 2026-10-15T19:02+0200 on branch `fix/397-text-variants` (from `main` 6c3fecc), before any run of
either variant: nothing below has been measured, no server was started for it. Ticket:
https://github.com/nibor1896/crow/issues/397 (body *Expected result*, measurement half). The variants
are `variants` key `text` on the points `flash-next` and `27b` in `manifests/stack.json`, started with
`python cli/crow_boot.py --start <point> --variant text` or the boot menu's own line. The time of the
commit that adds this file is authoritative. Changes to this file only as a dated addendum at the end,
written before the result it judges.

## Criteria (verbatim from the ticket, *Expected result*)

> **Measurement, criteria fixed here before any run.** It needs robin's go: the GPU runs one point at a time. It runs on the owner's Windows RTX 5090 machine with engine 0.13.2 installed, in the real Crow window (the speed-switch rule), with A = vision and B = text alternating A B A B A B A B A B:
>
> - n = 5 per arm, after one discarded warmup turn per boot.
> - The same prompt each turn: `tools/prompts/probe-f-coding.txt`.
> - Decode and prefill tok/s from serve's own timings.
> - 95 % t-interval of the difference.
>
> 1. **Flash-Next text:**
>    - **Boot:** the `[vit]` boot line says the tower is off, and the hot-set line gives N for each arm.
>    - **N** (hot set): B ≥ A + 3, or B = 160.
>    - **Decode:** B's mean is at least A's mean minus one SD of A (no regression). A gain is claimed only when the 95 % CI of B − A excludes 0.
>    - **Parity:** the first 256 greedy tokens are identical between A and B on `probe-a-chat.txt`, `probe-b-completion.txt` and `probe-f-coding.txt`.
> 2. **27B text:**
>    - **Boot at 200,000:** the boot passes without the planner's refusal and `/props` reports `n_ctx` 200000.
>    - **Long prompt:** a prompt of about 150,000 tokens is accepted and answered.
>    - **Decode** at short context is at least 0.97 × A's mean (A = the 128k vision point).
>    - **If the boot is refused at 200,000:** the result is recorded, the variant drops back to 131072, and robin decides whether a no-vision 27B is still worth a line.
> 3. **Images:** on either variant, a pasted image is refused with Crow's existing no-vision sentence (`refuse_images`, `/props` vision false).
>
> The numbers go to the Messbuch and to this ticket. `_status` in `stack.json` is replaced by the measured figures before the release ships the variants.

## The arms (fixed now)

- **A = vision** = the base point as the boot starts it at this commit: `--start flash-next`, `--start 27b`
  (131,072 context, `CROW_VIT_MMPROJ` set, no `CROW_VIT`).
- **B = text** = `--start <point> --variant text`: the base env without `CROW_VIT_MMPROJ`, plus `CROW_VIT=0`;
  the 27B also `CROW_CONTEXT=200000`. Nothing else differs (`cli/crow_boot.py` `plan_point`, held by
  `cli/test_crow_boot.py` `TheTextVariantsArePlannedFromTheirBaseTests`).
- Order per point: A B A B A B A B A B. Switching the arm needs a new boot; the first turn of every boot
  is discarded.

## Prompts (sha256 at this commit)

- `tools/prompts/probe-f-coding.txt` `c99b00d65a435d0058e7bd4629939da712ae80822c2ded5afd0a1938e5d3d0da` (timed turns, parity)
- `tools/prompts/probe-a-chat.txt` `32c92bc4ff708c7cc125c0ba53012b2ad0c2122cede636a06211509f7c22f44f` (parity)
- `tools/prompts/probe-b-completion.txt` `50e598b99f66652ac110bbe418cea426961b4300eea2ac77e88dfb7d9b0dcb4e` (parity)

## Open before the first run (each needs a dated addendum here before the run it concerns)

- The ticket names no file for the 27B's prompt of about 150,000 tokens; the repo has none
  (`tools/prompts/probe-d-long-france.txt` and `probe-e-long-japan.txt` are 8,294 and 8,293 bytes).

## Addenda

None yet.

## Amendment 2026-10-15 (before any run)

Written before any run of either variant; nothing below has been measured. The original text above is
unchanged.

**Criterion 2 is withdrawn** (27B text: boot at 200,000, a prompt of about 150,000 tokens, decode at
200k). The 27B stays at 131,072 by a standing owner decision. 200k was refused for VRAM on 2026-10-01
(`manifests/stack.json`, point `27b`, `engine._context`: 13.03 GiB of states needed against 12.17 GiB
free). The 8-bit KV gate that was to make 200k possible failed on 2026-10-07 (crow-nest #88). The owner
confirmed on 2026-10-15 that the 27B does not boot at 200k. The 27B text variant therefore stays at the
base point's 131,072 and only drops the vision tower; the ~1 GiB of VRAM that frees is not used by the
dense 27B. In *The arms*, the 27B's `CROW_CONTEXT=200000` no longer applies: B = text is the base env
without `CROW_VIT_MMPROJ`, plus `CROW_VIT=0`, nothing else. The open item about a prompt of about
150,000 tokens for the 27B falls away with the criterion.

**The 27B text variant is checked instead for** (A = the 128k vision base, B = `--start 27b --variant
text`, same machine state):

- **(a) Boot:** it boots at 131,072 and the `[vit]` boot line says the tower is off.
- **(b) VRAM:** the VRAM in use after boot is at least 0.8 GiB below the vision base's, same machine
  state, n = 3 alternating (A B A B A B).
- **(c) Decode:** decode tok/s at short context is at least 0.97 x the vision base's mean (n = 5
  alternating, as in criterion 1: the same prompt, `probe-f-coding.txt`, one discarded warmup turn per
  boot).
- **(d) Images:** a pasted image is refused with Crow's existing no-vision sentence (criterion 3 for
  the 27B, unchanged).

Criterion 1 (Flash-Next text) and criterion 3 stand as written.
