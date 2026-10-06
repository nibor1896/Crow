#!/usr/bin/env python3
"""#339: a negative prompt at txt_cfg 1 / 3 / 6, ten prompt/seed pairs, judged blind.

THE MEASUREMENT COMES BEFORE THE FEATURE (#339, *Proposed fix*: "nothing is built
before it"). This script is the measurement and nothing else. crow_core is
imported, never changed: the 1.0 arm is the body tool_generate_image sends today,
and each guided arm is that body plus `negative_prompt` and a higher `txt_cfg` --
the request option B would send. Both go through crow_core._run_image_job, the
tool's own submit-and-poll path, to the running sd-server.

The criteria, the pairs, the order, the output layout and the blind protocol are
fixed in runs/339-negative-cfg/PREREG.md, written before the first picture.

    python tools/measure_negative_cfg.py plan       (or --dry-run) the planned requests,
                                                    validated; no server, no GPU
    python tools/measure_negative_cfg.py selftest   (or --selftest) plan + a dress rehearsal
                                                    against a stub sd-server in this process
    python tools/measure_negative_cfg.py run        the Go: preflight, 2 warm-ups, 30 jobs,
                                                    then the blind sheet and the sealed key
    python tools/measure_negative_cfg.py run --round 2 --pairs R01,R02    replacements
    python tools/measure_negative_cfg.py seal DIR   the blind sheet (run does it at its end)
    python tools/measure_negative_cfg.py score DIR [DIR ...]   after robin's answers

Exit 0 = valid / green / complete. 2 = the plan is invalid, 3 = the preflight
refused, 4 = the series stopped early, 130 = interrupted (continue with --resume).
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import html
import json
import os
import random
import re
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zlib
from collections import namedtuple
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "cli"))

import crow_core as core  # noqa: E402
import crow_platform  # noqa: E402

TICKET = 339
RUN_ROOT = os.path.join(REPO, "runs", "339-negative-cfg")
PREREG = os.path.join(RUN_ROOT, "PREREG.md")

# The ticket's measurement: 2752x1536 (16:9), three txt_cfg values.
ASPECT = "16:9"
TICKET_SIZE = (2752, 1536)
ARMS = (1.0, 3.0, 6.0)
BASELINE = 1.0
GUIDED = (3.0, 6.0)

Pair = namedtuple("Pair", "id prompt exclude seed")

# P01 is the ticket's own live-check pair. Every prompt implies its object without
# naming it; R01-R05 replace invalid pairs, in this order (PREREG.md, *Pairs*).
PAIRS = (
    Pair("P01", "a quiet harbour at dawn", "boats", 7),
    Pair("P02", "a busy city street at night in the rain, neon signs reflected "
                "on the wet asphalt", "cars", 3390002),
    Pair("P03", "an airport apron at sunset, seen through the terminal window",
         "airplanes", 3390003),
    Pair("P04", "a coral reef aquarium in a dark room, lit from above", "fish",
         3390004),
    Pair("P05", "a children's birthday party in a sunny garden", "balloons",
         3390005),
    Pair("P06", "an old town square in Europe on a summer afternoon", "people",
         3390006),
    Pair("P07", "a tropical beach with turquoise water and white sand",
         "palm trees", 3390007),
    Pair("P08", "a railway station platform in the morning", "trains", 3390008),
    Pair("P09", "a medieval castle on a green hill under a blue sky", "flags",
         3390009),
    Pair("P10", "a still life of a fruit bowl on a wooden kitchen table",
         "bananas", 3390010),
    Pair("R01", "a shop front on a high street, photographed straight on",
         "text", 3390101),
    Pair("R02", "a cozy reading corner with an armchair by a window", "books",
         3390102),
    Pair("R03", "a ski slope on a bright winter day", "skiers", 3390103),
    Pair("R04", "a garden table set for afternoon tea", "teacups", 3390104),
    Pair("R05", "a kitchen counter with fresh vegetables ready for cooking",
         "tomatoes", 3390105),
)
PAIR_BY_ID = {p.id: p for p in PAIRS}
PRIMARY = tuple(p.id for p in PAIRS if p.id.startswith("P"))
RESERVES = tuple(p.id for p in PAIRS if p.id.startswith("R"))

# The ticket's thresholds (*Expected result*), as numbers. PREREG.md holds the text.
N_COUNTED = 10
ABSENT_MIN = 8
DEGRADED_MAX = 0
TIME_RATIO_MAX = 2.2
OOM_LINES_MAX = 0
THRESHOLDS = {"n": N_COUNTED, "absent_min": ABSENT_MIN, "degraded_max": DEGRADED_MAX,
              "time_ratio_max": TIME_RATIO_MAX, "oom_lines_max": OOM_LINES_MAX}

# sd.cpp 2f88688 keeps the last 4 conditionings (LRU, keyed by the prompt text,
# include/stable-diffusion.h:252, src/conditioning/conditioning_cache.h). A pair's
# second job must come at least CACHE_CAPACITY + 1 jobs after its first, or it
# reads its prompt from the cache and its time is not the time of a new call.
CACHE_CAPACITY = 4
MAX_FAILS_IN_A_ROW = 3

# The warm-up crow_core.image_server_warm sends (cli/crow_core.py:12788-12792),
# then the same with guidance, so the first guided job pays no first-use cost.
WARMUP_PROMPT = "a plain grey square"
WARMUP_NEGATIVE = "watermark"

# The image stack's language model (manifests/stack.json, image-stack identity).
LLM_MODEL_SUFFIX = "Qwen3.8-27B-CNQ4.5.cnq"

NVSMI_SAMPLE = ["nvidia-smi", "--query-gpu=memory.used",
                "--format=csv,noheader,nounits", "-lms", "500"]
NVSMI_INFO = ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version",
              "--format=csv,noheader,nounits"]

# For the duration estimate only. 218.3 s: the Windows warm 1.0 job, mean of
# 218.1 and 218.5 (#320, 2026-09-28). 1.66: that job plus a second pass for
# 40 steps at 3.57 s/it (Linux gen2.log, #308) -- not measured on Windows.
# 2.2: the ticket's limit.
BASE_S_WINDOWS = 218.3
GUIDED_FACTOR_GUESS = (1.66, 2.2)

KEY_NAME = "sealed-key.json"
KEY_SHA_NAME = "sealed-key.sha256"
SHEET = "sheet"
LETTERS = ("A", "B", "C")
QUESTION = "Do you see any %s anywhere in the picture?"
ANSWER_HOW = (
    "Two answers per picture, true or false. object_visible: you see the slot's "
    "object anywhere in the picture. degraded: frame-wide grain or clear "
    "degradation compared with the other pictures of its row. A picture that is "
    "null had no image (its job failed) and is not answered. Do not open "
    "../sealed-key.json, ../results.jsonl, ../run.json or ../images/ before every "
    "answer is in.")


# ------------------------------------------------------------------ helpers --

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cfg_label(cfg: float) -> str:
    return "cfg%g" % cfg


def read_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str, doc) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")


def read_rows(out: str) -> "list[dict]":
    path = os.path.join(out, "results.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def append_row(out: str, row: dict) -> None:
    with open(os.path.join(out, "results.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# ---------------------------------------------------------------- the plan --

def baseline_body(pair: Pair) -> dict:
    """The body tool_generate_image sends for (prompt, 16:9, seed) today
    (cli/crow_core.py tool_generate_image -> _run_image_job)."""
    width, height = core.IMAGE_SIZES[ASPECT]
    return {"prompt": pair.prompt, "width": width, "height": height,
            "seed": pair.seed, "sample_params": core._image_sample_params()}


def arm_body(pair: Pair, cfg: float) -> dict:
    """1.0: today's body, byte for byte. Guided: the same plus negative_prompt
    and txt_cfg -- option B's request (#339, *Proposed fix*)."""
    body = baseline_body(pair)
    if cfg == BASELINE:
        return body
    body["sample_params"]["guidance"]["txt_cfg"] = float(cfg)
    body["negative_prompt"] = pair.exclude
    return body


def tool_body(pair: Pair) -> dict:
    """The body tool_generate_image builds for this pair, caught before it is sent.

    _image_start (progress, server start) and _run_image_job (the request) are
    replaced for this one call, so nothing reaches a server."""
    seen = []

    def catch(body, base, refine=False):
        seen.append(copy.deepcopy(body))
        return None, 0.0, "error: caught by measure_negative_cfg"

    base = {"job": "img-plan", "kind": "generate", "stage": "", "width": 0, "height": 0}
    with mock.patch.object(core, "_image_start", lambda *a, **k: (base, None)), \
            mock.patch.object(core, "_run_image_job", catch):
        core.tool_generate_image(pair.prompt, aspect_ratio=ASPECT, seed=pair.seed)
    if len(seen) != 1:
        raise RuntimeError("tool_generate_image sent %d bodies, expected 1" % len(seen))
    return seen[0]


def schedule(pair_ids) -> "list[tuple[str, float]]":
    """Three passes over the pairs; pair i gets ARMS[(i + pass * shift) % 3].

    Every pair gets every arm once, neighbours never share an arm (shift 2 where
    shift 1 would repeat one across a pass boundary, k = 2, 5, 8, ...), each pass
    carries all three arms (drift spreads evenly), and a pair's jobs are k apart,
    out of reach of sd-server's conditioning cache for k >= 5."""
    ids = list(pair_ids)
    shift = 2 if (len(ids) - 1) % 3 == 1 else 1
    return [(pid, ARMS[(i + r * shift) % 3]) for r in range(3) for i, pid in enumerate(ids)]


def plan(pair_ids) -> "list[dict]":
    jobs = []
    for seq, (pid, cfg) in enumerate(schedule(pair_ids), 1):
        body = arm_body(PAIR_BY_ID[pid], cfg)
        jobs.append({"seq": seq, "pair": pid, "cfg": cfg, "body": body,
                     "body_sha256": sha256_bytes(canonical(body)),
                     "image": "images/%s-%s.png" % (pid, cfg_label(cfg))})
    return jobs


def validate_plan(jobs, pair_ids, check_tool: bool = True) -> "tuple[list[str], list[str]]":
    """(problems, notes). A problem forbids the run; a note is recorded with it."""
    ids = list(pair_ids)
    bad, notes = [], []
    if not ids:
        return ["no pairs"], notes
    unknown = [p for p in ids if p not in PAIR_BY_ID]
    if unknown:
        return ["unknown pairs: %s" % ", ".join(unknown)], notes
    if len(set(ids)) != len(ids):
        bad.append("a pair is listed twice: %s" % ", ".join(ids))
    if len(jobs) != 3 * len(ids):
        bad.append("%d jobs for %d pairs, expected %d" % (len(jobs), len(ids), 3 * len(ids)))
    for pid in ids:
        got = sorted(j["cfg"] for j in jobs if j["pair"] == pid)
        if got != sorted(ARMS):
            bad.append("%s gets txt_cfg %s, expected each of %s once" % (pid, got, list(ARMS)))
    for a, b in zip(jobs, jobs[1:]):
        if a["cfg"] == b["cfg"]:
            bad.append("jobs %d and %d are both txt_cfg %g (arms must alternate)"
                       % (a["seq"], b["seq"], a["cfg"]))
    for j in jobs:
        pair, body = PAIR_BY_ID[j["pair"]], j["body"]
        sp = body.get("sample_params") or {}
        if (body.get("width"), body.get("height")) != TICKET_SIZE:
            bad.append("job %d is %sx%s, the ticket measures %dx%d"
                       % ((j["seq"], body.get("width"), body.get("height")) + TICKET_SIZE))
        if sp.get("sample_steps") != 40 or sp.get("sample_method") != "euler":
            bad.append("job %d is not 40 euler steps: %s" % (j["seq"], sp))
        if (sp.get("guidance") or {}).get("txt_cfg") != j["cfg"]:
            bad.append("job %d sends txt_cfg %s, planned %g"
                       % (j["seq"], (sp.get("guidance") or {}).get("txt_cfg"), j["cfg"]))
        if pair.exclude.lower() in pair.prompt.lower():
            bad.append("%s's prompt names its excluded object %r" % (pair.id, pair.exclude))
        if j["cfg"] == BASELINE:
            if "negative_prompt" in body:
                bad.append("job %d (txt_cfg 1.0) carries a negative_prompt" % j["seq"])
            if check_tool and body != tool_body(pair):
                bad.append("job %d (%s, txt_cfg 1.0) is not the body tool_generate_image "
                           "sends today" % (j["seq"], pair.id))
        else:
            if body.get("negative_prompt") != pair.exclude:
                bad.append("job %d sends negative_prompt %r, planned %r"
                           % (j["seq"], body.get("negative_prompt"), pair.exclude))
            rest = copy.deepcopy(body)
            rest.pop("negative_prompt", None)
            rest.get("sample_params", {}).get("guidance", {})["txt_cfg"] = BASELINE
            if rest != baseline_body(pair):
                bad.append("job %d differs from the 1.0 body in more than txt_cfg and "
                           "negative_prompt" % j["seq"])
    seqs = {}
    for j in jobs:
        seqs.setdefault(j["pair"], []).append(j["seq"])
    gaps = [b - a for s in seqs.values() for a, b in zip(s, s[1:])]
    if gaps and min(gaps) <= CACHE_CAPACITY:
        if sorted(ids) == sorted(PRIMARY):
            bad.append("the primary round's pair jobs are only %d apart: sd-server's "
                       "conditioning cache would serve their prompts" % min(gaps))
        else:
            notes.append("a pair's jobs are only %d apart: sd-server's conditioning cache "
                         "(%d entries) may serve the prompt; these times are not used for "
                         "criterion 3 (PREREG.md)" % (min(gaps), CACHE_CAPACITY))
    return bad, notes


def estimate(n_pairs: int) -> str:
    lo, hi = (n_pairs * BASE_S_WINDOWS * (1 + 2 * f) / 3600.0 for f in GUIDED_FACTOR_GUESS)
    return ("%d jobs, about %.1f-%.1f h of GPU time (1.0 job %.1f s on Windows, #320; a "
            "guided job %.2fx-%.1fx of it, not measured) plus ~1 min of warm-ups"
            % (3 * n_pairs, lo, hi, BASE_S_WINDOWS, GUIDED_FACTOR_GUESS[0],
               GUIDED_FACTOR_GUESS[1]))


def warmup_bodies() -> "list[dict]":
    plain = {"prompt": WARMUP_PROMPT, "width": 256, "height": 256, "seed": 1,
             "sample_params": {"sample_steps": 1, "sample_method": "euler",
                               "guidance": {"txt_cfg": 1.0}}}
    guided = copy.deepcopy(plain)
    guided["sample_params"]["guidance"]["txt_cfg"] = GUIDED[-1]
    guided["negative_prompt"] = WARMUP_NEGATIVE
    return [plain, guided]


# --------------------------------------------------------------- the image --

_TEXT_CHUNKS = (b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"tIME")


def strip_png_text(data: bytes) -> bytes:
    """The PNG without its text, EXIF and time chunks; pixels untouched.

    sd-server embeds the generation parameters -- negative prompt and CFG among
    them -- in every PNG it returns (examples/server/async_jobs.cpp:206,
    embed_image_metadata defaults to true), so a sheet copy with them would carry
    its own label."""
    sig = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(sig):
        raise ValueError("not a PNG")
    out, i = [sig], len(sig)
    while i < len(data):
        if i + 8 > len(data):
            raise ValueError("truncated PNG chunk header at byte %d" % i)
        length = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        end = i + 12 + length
        if end > len(data):
            raise ValueError("truncated PNG chunk %r at byte %d" % (kind, i))
        if kind not in _TEXT_CHUNKS:
            out.append(data[i:end])
        i = end
        if kind == b"IEND":
            break
    return b"".join(out)


def tiny_png(text: str = "", shade: int = 128) -> bytes:
    """A 1x1 PNG, optionally with a tEXt `parameters` chunk -- the stub's picture."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    parts = [b"\x89PNG\r\n\x1a\n", chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))]
    if text:
        parts.append(chunk(b"tEXt", b"parameters\x00" + text.encode("latin-1", "replace")))
    parts += [chunk(b"IDAT", zlib.compress(bytes([0, shade, shade, shade]))),
              chunk(b"IEND", b"")]
    return b"".join(parts)


# ----------------------------------------------------------------- the log --

_COMPLETED = re.compile(r"generate_image completed in ([\d.]+)\s*s")


def log_facts(lines) -> dict:
    """What one job left in sd-server's log: its own time, conditioning-cache
    hits, and its out-of-memory lines -- crow_core's markers and level rule
    (_image_oom_cause): a `cudaMalloc failed: out of memory` or `failed to
    allocate` line counts unless a level other than ERROR stands before it; a
    pinned-host-memory refusal is listed apart."""
    server_s, hits, oom, pinned = None, 0, [], []
    for line in lines or []:
        hit = _COMPLETED.search(line)
        if hit:
            server_s = float(hit.group(1))
        if "conditioning cache hit" in line:
            hits += 1
        level = core._SD_LOG.match(line)
        if any(m in line for m in core._SD_OOM_MARKS) and not (
                level and level.group(1) != "ERROR"):
            oom.append(line)
        elif any(m in line for m in core._SD_PINNED_MARKS):
            pinned.append(line)
    return {"server_s": server_s, "cache_hits": hits, "oom": oom, "pinned": pinned}


def sd_log_candidates() -> "list[str]":
    """Where the running sd-server's log can be. crow_platform.log_dir() is
    `runs\\` under the CURRENT folder on Windows, so a stack the boot shortcut
    started (in the install root) logs there, not beside this checkout."""
    found = [core.image_server_log()]
    if crow_platform.IS_WINDOWS:
        found.append(os.path.join(crow_platform.install_dir(), "runs",
                                  os.path.basename(core.image_server_log())))
    return list(dict.fromkeys(found))


def default_sd_log() -> str:
    candidates = sd_log_candidates()
    existing = [p for p in candidates if os.path.isfile(p)]
    return max(existing, key=os.path.getmtime) if existing else candidates[0]


# ------------------------------------------------------------- the machine --

class VramSampler:
    """nvidia-smi every 500 ms, the whole card, into vram.csv; peak() per job."""

    def __init__(self, csv_path: str, argv=None):
        self.csv_path = csv_path
        self.argv = list(argv or NVSMI_SAMPLE)
        self.samples: "list[tuple[float, int]]" = []
        self._lock = threading.Lock()
        self.proc = None

    def start(self) -> None:
        fresh = not os.path.exists(self.csv_path)
        self._sink = open(self.csv_path, "a", encoding="utf-8")
        if fresh:
            self._sink.write("unix_s,monotonic_s,used_mib\n")
        self.proc = subprocess.Popen(self.argv, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self._read, name="vram", daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            try:
                used = int(line.strip().split(",")[0])
            except ValueError:
                continue
            now = time.monotonic()
            with self._lock:
                self.samples.append((now, used))
                self._sink.write("%.3f,%.3f,%d\n" % (time.time(), now, used))
                self._sink.flush()

    def peak(self, t0: float, t1: float) -> "int | None":
        with self._lock:
            seen = [used for t, used in self.samples if t0 <= t <= t1]
        return max(seen) if seen else None

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        with self._lock:
            if getattr(self, "_sink", None) is not None:
                self._sink.close()
                self._sink = None


class FixedSampler:
    """The dress rehearsal's sampler: one fixed reading."""

    def __init__(self, mib: "int | None" = 30000):
        self.mib = mib

    def start(self) -> None:
        pass

    def peak(self, t0: float, t1: float) -> "int | None":
        return self.mib

    def stop(self) -> None:
        pass


def gpu_info() -> "dict | None":
    try:
        out = subprocess.run(NVSMI_INFO, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    parts = [p.strip() for p in (out.strip().splitlines() or [""])[0].split(",")]
    if len(parts) < 4:
        return None
    try:
        return {"name": parts[0], "total_mib": int(parts[1]), "used_mib": int(parts[2]),
                "driver": parts[3]}
    except ValueError:
        return None


def http_json(url: str, timeout: float = 5.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except Exception as exc:               # noqa: BLE001 - the error is the answer
        return {"error": str(exc)}


def git_state() -> "tuple[str | None, bool | None]":
    try:
        head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=20).stdout.strip() or None
        dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain",
                                "--untracked-files=no"], capture_output=True, text=True,
                               timeout=20).stdout.strip()
        return head, bool(dirty)
    except (OSError, subprocess.SubprocessError):
        return None, None


def gather_facts(sd_log: str) -> dict:
    """Everything the preflight judges, and what run.json records about the machine."""
    facts = {"at": now_iso(), "platform": sys.platform, "python": sys.version.split()[0],
             "crow_version": core.VERSION}
    facts["git_head"], facts["git_dirty"] = git_state()
    doc = core.read_active_point()
    facts["active_point"] = None if doc is None else {
        k: doc.get(k) for k in ("point", "mode", "base_url")}
    facts["servers"] = [{"pid": str(pid), "kind": crow_platform.server_kind(line),
                         "line": line}
                        for pid, line in core.running_servers(include_image=True)]
    root = None
    if doc and doc.get("base_url"):
        root = re.sub(r"/v1/?$", "", str(doc["base_url"]).rstrip("/"))
    facts["llm_root"] = root
    facts["llm_health"] = http_json(root + "/health") if root else None
    props = http_json(root + "/props") if root else None
    facts["llm_model_path"] = props.get("model_path") if isinstance(props, dict) else None
    facts["sd_answers"] = core._image_server_answers()
    facts["sd_expected_argv"] = core.image_server_command(core._image_port())
    binary = core.image_server_binary()
    facts["sd_binary"] = binary
    facts["sd_binary_sha256"] = sha256_file(binary) if binary else None
    facts["sd_log"] = sd_log
    facts["sd_log_exists"] = os.path.isfile(sd_log)
    facts["gpu"] = gpu_info()
    facts["prereg_sha256"] = sha256_file(PREREG) if os.path.isfile(PREREG) else None
    return facts


def _is_path(value: str) -> bool:
    return "/" in value or "\\" in value


def argv_mismatch(line: str, expected) -> "list[str]":
    """Where a running sd-server's command line differs from the production argv
    (crow_core.image_server_command): its flag set, and every value that is not
    a path (paths are spelled per platform and per caller)."""
    want = {t for t in expected[1:] if t.startswith("-")}
    have = set(re.findall(r'(?:^|\s)"?(--?[A-Za-z][\w-]*)', line or ""))
    bad = []
    if want != have:
        bad.append("sd-server's flags differ from crow_core.image_server_command: "
                   "missing %s, extra %s" % (sorted(want - have), sorted(have - want)))
    toks = list(expected[1:])
    for flag, value in zip(toks, toks[1:]):
        if flag.startswith("-") and not value.startswith("-") and not _is_path(value):
            if not re.search(r'(?:^|\s)%s[\s=]+"?%s"?(?=\s|$)'
                             % (re.escape(flag), re.escape(value)), line or ""):
                bad.append("sd-server runs without `%s %s`" % (flag, value))
    return bad


def check_preflight(facts: dict) -> "list[str]":
    """Why the measurement may not start on this machine now, or []."""
    bad = []
    point = facts.get("active_point") or {}
    if point.get("point") != core.ACTIVE_POINT_IMAGE:
        bad.append("the running operating point is %r, not %r -- start the Image Stack "
                   "(boot menu, or python cli/crow_boot.py --start image-stack)"
                   % (point.get("point"), core.ACTIVE_POINT_IMAGE))
    elif point.get("mode") == "video":
        bad.append("the card is in video mode")
    servers = facts.get("servers") or []
    language = [s for s in servers
                if s.get("kind") in (crow_platform.KIND_CROW_NEST, crow_platform.KIND_LLAMA)]
    if len(language) != 1 or language[0].get("kind") != crow_platform.KIND_CROW_NEST:
        bad.append("expected exactly one crow-nest serve, found %s"
                   % ([s.get("kind") for s in language] or "none"))
    if any(s.get("kind") == crow_platform.KIND_VIDEO for s in servers):
        bad.append("ComfyUI is running")
    images = [s for s in servers if s.get("kind") == crow_platform.KIND_IMAGE]
    if len(images) > 1:
        bad.append("%d sd-servers are running" % len(images))
    for s in images:
        bad += argv_mismatch(s.get("line", ""), facts.get("sd_expected_argv") or [])
    if images and not facts.get("sd_log_exists"):
        bad.append("no sd-server log at %s -- pass --sd-log <the running server's log>"
                   % facts.get("sd_log"))
    if not str(facts.get("llm_model_path") or "").endswith(LLM_MODEL_SUFFIX):
        bad.append("the language model is %r, not the 27B (%s)"
                   % (facts.get("llm_model_path"), LLM_MODEL_SUFFIX))
    health = facts.get("llm_health")
    if not (isinstance(health, dict) and health.get("status") == "ok"):
        bad.append("the language model's /health is %r, not ok" % (health,))
    if not facts.get("gpu"):
        bad.append("nvidia-smi gave no reading")
    if not facts.get("prereg_sha256"):
        bad.append("%s is missing" % PREREG)
    if facts.get("git_dirty"):
        bad.append("tracked files are modified: the run uses the committed script and PREREG")
    return bad


# ----------------------------------------------------------------- the run --

def _one(body: dict, label: str, sd_log: str, sampler, submit) -> "tuple[bytes | None, dict]":
    try:
        offset = os.path.getsize(sd_log)
    except OSError:
        offset = 0
    base = {"job": "m339-" + label, "kind": "generate", "stage": "",
            "width": body["width"], "height": body["height"]}
    started = now_iso()
    t0 = time.monotonic()
    png, took, err = submit(body, base)
    t1 = time.monotonic()
    facts = log_facts(core._image_log_lines(sd_log, offset) or [])
    return png, {"started": started, "ended": now_iso(), "wall_s": round(took, 2),
                 "server_s": facts["server_s"], "status": "ok" if err is None else "error",
                 "error": err, "peak_mib": sampler.peak(t0, t1), "oom_lines": facts["oom"],
                 "pinned_lines": facts["pinned"], "cache_hits": facts["cache_hits"],
                 "body_sha256": sha256_bytes(canonical(body)), "sd_log": sd_log}


def run_series(jobs, out: str, *, header: dict, sd_log: str, sampler, submit=None,
               ensure=None, answers=None, resume: bool = False, say=print) -> str:
    """The jobs, in order, after two warm-ups. 'complete', or 'stopped' (why is said).

    A failed job is a result row, not a reason to stop, and is never run again;
    MAX_FAILS_IN_A_ROW failures in a row end the series. --resume skips every
    (pair, txt_cfg) that already has a row and warms the server up again first."""
    submit = submit or core._run_image_job
    ensure = ensure or core.image_server_start
    answers = answers or core._image_server_answers
    os.makedirs(os.path.join(out, "images"), exist_ok=True)
    if os.path.exists(os.path.join(out, KEY_NAME)):
        raise RuntimeError("%s is sealed already; nothing more runs into it" % out)
    done = set()
    if read_rows(out):
        if not resume:
            raise RuntimeError("%s already has results -- add --resume to continue it" % out)
        done = {(r["pair"], r["cfg"]) for r in read_rows(out) if r.get("kind") == "job"}
    head = os.path.join(out, "run.json")
    if os.path.exists(head):
        head = os.path.join(out, "resume-%s.json" % time.strftime("%Y%m%d-%H%M%S"))
    write_json(head, header)
    state = {"log": sd_log}

    def server_up(reason: str) -> "str | None":
        if answers():
            return None
        why = ensure()
        if core._IMAGE_PROC is not None:
            state["log"] = core._IMAGE_PROC[1]     # a server this process started
        append_row(out, {"kind": "restart", "at": now_iso(), "reason": reason,
                         "error": why, "sd_log": state["log"]})
        return why

    def warm() -> "str | None":
        rows = []
        for n, body in enumerate(warmup_bodies(), 1):
            _png, row = _one(body, "warm%d" % n, state["log"], sampler, submit)
            row.update(kind="warmup", txt_cfg=body["sample_params"]["guidance"]["txt_cfg"])
            append_row(out, row)
            rows.append(row)
            if row["status"] != "ok":
                return "warm-up %d failed: %s" % (n, row["error"])
        if all(r["server_s"] is None for r in rows):
            return ("the log at %s did not record the warm-ups -- it is not the running "
                    "server's log; pass --sd-log" % state["log"])
        return None

    sampler.start()
    try:
        why = server_up("no image server answered at the start") or warm()
        if why:
            say("stopped: %s" % why)
            return "stopped"
        fails = 0
        for job in jobs:
            if (job["pair"], job["cfg"]) in done:
                continue
            if not answers():
                why = server_up("the image server stopped answering before job %d"
                                % job["seq"]) or warm()
                if why:
                    say("stopped: %s" % why)
                    return "stopped"
            png, row = _one(job["body"], "%02d" % job["seq"], state["log"], sampler, submit)
            pair = PAIR_BY_ID[job["pair"]]
            row.update(kind="job", seq=job["seq"], pair=pair.id, cfg=job["cfg"],
                       seed=pair.seed, prompt=pair.prompt,
                       negative_prompt=job["body"].get("negative_prompt"),
                       image=None, image_sha256=None, bytes=None)
            if png is not None:
                with open(os.path.join(out, job["image"]), "xb") as fh:
                    fh.write(png)
                row.update(image=job["image"], image_sha256=sha256_bytes(png), bytes=len(png))
                fails = 0
            else:
                fails += 1
            append_row(out, row)
            say("[%2d/%d] %s %-7s %-5s %7.1f s  peak %s MiB  oom %d  cache hits %d"
                % (job["seq"], len(jobs), pair.id, cfg_label(job["cfg"]), row["status"],
                   row["wall_s"], row["peak_mib"], len(row["oom_lines"]), row["cache_hits"]))
            if fails >= MAX_FAILS_IN_A_ROW:
                say("stopped: %d failed jobs in a row" % fails)
                return "stopped"
        return "complete"
    finally:
        sampler.stop()


# ------------------------------------------------------------- the blinding --

def seal(out: str, rng=None) -> str:
    """The blind sheet and the sealed key. Returns the key's sha256.

    Pairs go to slots S01.. in a shuffled order, each slot's three arms to A/B/C
    in a shuffled order (random.SystemRandom: no seed anyone could replay).
    Sheet pictures are copies without PNG text chunks."""
    key_path = os.path.join(out, KEY_NAME)
    if os.path.exists(key_path):
        raise RuntimeError("%s exists: a round is sealed once" % key_path)
    run = read_json(os.path.join(out, "run.json"))
    planned = [(j["pair"], j["cfg"]) for j in run["plan"]]
    rows = {(r["pair"], r["cfg"]): r for r in read_rows(out) if r.get("kind") == "job"}
    missing = [p for p in planned if p not in rows]
    if missing:
        raise RuntimeError("not every planned job has a row yet: %s" % missing)
    rng = rng or random.SystemRandom()
    pairs = list(dict.fromkeys(pid for pid, _ in planned))
    rng.shuffle(pairs)
    sheet = os.path.join(out, SHEET)
    os.makedirs(sheet, exist_ok=True)
    key = {"ticket": TICKET, "sealed_at": now_iso(), "round": run.get("round"), "slots": {}}
    form = {"_how": ANSWER_HOW}
    for n, pid in enumerate(pairs, 1):
        slot, pair = "S%02d" % n, PAIR_BY_ID[pid]
        cfgs = list(ARMS)
        rng.shuffle(cfgs)
        entry = {"pair": pid, "object": pair.exclude}
        asked = {"object": pair.exclude, "question": QUESTION % pair.exclude}
        for letter, cfg in zip(LETTERS, cfgs):
            row = rows[(pid, cfg)]
            item = {"cfg": cfg, "raw": row.get("image"), "raw_sha256": row.get("image_sha256"),
                    "sheet": None, "sheet_sha256": None}
            asked[letter] = None
            if row.get("image"):
                with open(os.path.join(out, row["image"]), "rb") as fh:
                    data = strip_png_text(fh.read())
                name = "%s-%s.png" % (slot, letter)
                with open(os.path.join(sheet, name), "wb") as fh:
                    fh.write(data)
                item.update(sheet="%s/%s" % (SHEET, name), sheet_sha256=sha256_bytes(data))
                asked[letter] = {"object_visible": None, "degraded": None}
            entry[letter] = item
        key["slots"][slot] = entry
        form[slot] = asked
    write_json(os.path.join(sheet, "answers.json"), form)
    with open(os.path.join(sheet, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(sheet_html(form))
    raw = json.dumps(key, indent=1, sort_keys=True).encode("utf-8")
    with open(key_path, "wb") as fh:
        fh.write(raw)
    digest = sha256_bytes(raw)
    with open(os.path.join(out, KEY_SHA_NAME), "w", encoding="utf-8") as fh:
        fh.write("%s  %s\n" % (digest, KEY_NAME))
    return digest


def sheet_html(form: dict) -> str:
    rows = []
    for slot in sorted(k for k in form if not k.startswith("_")):
        cells = []
        for letter in LETTERS:
            if form[slot][letter] is None:
                cells.append('<figure><div class="none">no picture: the job failed</div>'
                             '<figcaption>%s</figcaption></figure>' % letter)
            else:
                src = "%s-%s.png" % (slot, letter)
                cells.append('<figure><a href="%s"><img src="%s" alt="%s %s"></a>'
                             '<figcaption>%s</figcaption></figure>'
                             % (src, src, slot, letter, letter))
        rows.append('<section><h2>%s &mdash; %s</h2><div class="row">%s</div></section>'
                    % (slot, html.escape(form[slot]["question"]), "".join(cells)))
    style = ("body{margin:0;padding:16px;background:#1e1e1e;color:#e6e6e6;"
             "font:15px/1.5 system-ui,sans-serif}"
             ".row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}"
             "@media (max-width:800px){.row{grid-template-columns:1fr}}"
             "figure{margin:0}img{width:100%;height:auto;display:block}"
             "figcaption{text-align:center;font-weight:600;padding:4px}"
             ".none{aspect-ratio:16/9;display:grid;place-items:center;"
             "border:1px dashed #777}h2{font-size:17px;margin:28px 0 8px}")
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>#339 blind sheet</title><style>" + style + "</style></head><body>"
            "<h1>#339 blind sheet</h1><p>" + html.escape(ANSWER_HOW) + "</p>"
            "<p>Click a picture for full size. Answers go into <code>answers.json</code> "
            "in this folder.</p>" + "".join(rows) + "</body></html>\n")


# ------------------------------------------------------------- the verdict --

def load_round(out: str, expect_sha256: "str | None" = None) -> dict:
    """One sealed round with robin's answers, the key checked before it is read."""
    with open(os.path.join(out, KEY_NAME), "rb") as fh:
        raw = fh.read()
    digest = sha256_bytes(raw)
    with open(os.path.join(out, KEY_SHA_NAME), encoding="utf-8") as fh:
        sealed = fh.read().split()[0]
    if digest != sealed:
        raise RuntimeError("%s changed after sealing: %s, sealed %s" % (KEY_NAME, digest, sealed))
    if expect_sha256 and digest != expect_sha256:
        raise RuntimeError("%s is %s, the published sha256 is %s" % (KEY_NAME, digest,
                                                                     expect_sha256))
    key = json.loads(raw.decode("utf-8"))
    form = read_json(os.path.join(out, SHEET, "answers.json"))
    run = read_json(os.path.join(out, "run.json"))
    rows = {(r["pair"], r["cfg"]): r for r in read_rows(out) if r.get("kind") == "job"}
    records, blank = {}, []
    for slot, entry in sorted(key["slots"].items()):
        for letter in LETTERS:
            item = entry[letter]
            given = (form.get(slot) or {}).get(letter)
            rec = {"pair": entry["pair"], "cfg": item["cfg"], "has_image": bool(item["sheet"]),
                   "object_visible": None, "degraded": None}
            if rec["has_image"]:
                if not (isinstance(given, dict) and isinstance(given.get("object_visible"), bool)
                        and isinstance(given.get("degraded"), bool)):
                    blank.append("%s-%s" % (slot, letter))
                else:
                    rec.update(object_visible=given["object_visible"],
                               degraded=given["degraded"])
            row = rows[(entry["pair"], item["cfg"])]
            rec.update(status=row["status"], wall_s=row["wall_s"], peak_mib=row["peak_mib"],
                       oom=len(row["oom_lines"]), cache_hits=row["cache_hits"])
            records[(entry["pair"], item["cfg"])] = rec
    if blank:
        raise RuntimeError("no answer yet for %s" % ", ".join(blank))
    return {"dir": out, "pairs": list(run["pairs"]), "records": records,
            "capacity_mib": ((run.get("facts") or {}).get("gpu") or {}).get("total_mib"),
            "sha256": digest}


def evaluate(rounds) -> dict:
    """The ticket's four criteria per guided txt_cfg, read as PREREG.md fixes them."""
    seen = {}
    for rnd in rounds:
        for k, rec in rnd["records"].items():
            if k in seen:
                raise RuntimeError("%s txt_cfg %g is in two rounds" % k)
            seen[k] = dict(rec, capacity_mib=rnd["capacity_mib"])
    measured = [p.id for p in PAIRS if all((p.id, c) in seen for c in ARMS)]
    valid = [pid for pid in measured if seen[(pid, BASELINE)]["has_image"]
             and seen[(pid, BASELINE)]["object_visible"] is True]
    counted = valid[:N_COUNTED]
    primary = [r for r in rounds if sorted(r["pairs"]) == sorted(PRIMARY)]
    timing = primary[0]["records"] if len(primary) == 1 else None

    def median_wall(cfg):
        if timing is None:
            return None
        vals = [r["wall_s"] for (_p, c), r in timing.items() if c == cfg and r["status"] == "ok"]
        return statistics.median(vals) if vals else None

    base = median_wall(BASELINE)
    arms = {}
    for cfg in ARMS:
        recs = [seen[(pid, cfg)] for pid in counted]
        every = [r for (_p, c), r in seen.items() if c == cfg]
        peaks = [r["peak_mib"] for r in every if r["peak_mib"] is not None]
        unsampled = sum(1 for r in every if r["peak_mib"] is None)
        caps = [r["capacity_mib"] for r in every if r["capacity_mib"]]
        med = median_wall(cfg)
        arm = {"n": len(recs),
               "object_absent": sum(1 for r in recs if r["has_image"]
                                    and r["object_visible"] is False),
               "degraded": sum(1 for r in recs if not r["has_image"] or r["degraded"]),
               "median_wall_s": med,
               "time_ratio": round(med / base, 3) if med is not None and base else None,
               "oom_lines": sum(r["oom"] for r in every),
               "peak_mib": max(peaks) if peaks else None,
               "capacity_mib": min(caps) if caps else None,
               "jobs_without_vram_sample": unsampled,
               "failed_jobs": sum(1 for r in every if r["status"] != "ok"),
               "cache_hits": sum(r["cache_hits"] for r in every)}
        if cfg != BASELINE:
            full = len(recs) == N_COUNTED
            arm["c1_absent"] = full and arm["object_absent"] >= ABSENT_MIN
            arm["c2_no_degradation"] = full and arm["degraded"] <= DEGRADED_MAX
            arm["c3_time"] = arm["time_ratio"] is not None and arm["time_ratio"] <= TIME_RATIO_MAX
            arm["c4_memory"] = (arm["oom_lines"] <= OOM_LINES_MAX and not unsampled
                                and arm["peak_mib"] is not None
                                and arm["capacity_mib"] is not None
                                and arm["peak_mib"] < arm["capacity_mib"])
            arm["pass"] = all(arm[k] for k in ("c1_absent", "c2_no_degradation", "c3_time",
                                               "c4_memory"))
        arms["%g" % cfg] = arm
    complete = len(counted) == N_COUNTED
    left = [r for r in RESERVES if r not in measured]
    passing = [c for c in GUIDED if complete and arms["%g" % c]["pass"]]
    if not complete and len(left) < N_COUNTED - len(counted):
        verdict = ("incomplete: %d of %d valid pairs and too few reserves left -- a new pair "
                   "needs a dated PREREG addendum before it runs" % (len(counted), N_COUNTED))
    elif not complete:
        verdict = ("incomplete: %d of %d valid pairs -- run the next reserves: %s"
                   % (len(counted), N_COUNTED, ",".join(left[:N_COUNTED - len(counted)])))
    elif passing:
        verdict = ("IMAGE_NEGATIVE_CFG = %g (the lowest passing txt_cfg): build option B"
                   % min(passing))
    else:
        verdict = "no txt_cfg passes: close #339 as option A with these numbers"
    return {"complete": complete, "counted_pairs": counted,
            "invalid_pairs": [p for p in measured if p not in valid],
            "next_reserves": [] if complete else left[:N_COUNTED - len(counted)],
            "timing_round": primary[0]["dir"] if timing is not None else None,
            "arms": arms, "image_negative_cfg": min(passing) if passing else None,
            "key_sha256": {r["dir"]: r["sha256"] for r in rounds}, "verdict": verdict}


# --------------------------------------------------------- dress rehearsal --

class StubSdServer:
    """sd-server's three routes for the dress rehearsal: no model, no GPU.

    Every POST appends the two log lines a real job leaves (start, completed);
    POST numbers in `fail` end as failed jobs with a cudaMalloc line instead."""

    def __init__(self, log_path: str, fail=()):
        self.log_path = log_path
        self.fail = set(fail)
        self.bodies: "list[dict]" = []
        self.jobs: "dict[str, dict]" = {}
        self._lock = threading.Lock()
        self.httpd = None

    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d" % self.httpd.server_port

    def _log(self, *lines: str) -> None:
        with open(self.log_path, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")

    def start(self) -> "StubSdServer":
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def _send(self, code: int, doc) -> None:
                data = json.dumps(doc).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/sdcpp/v1/capabilities":
                    return self._send(200, {})
                hit = re.match(r"^/sdcpp/v1/jobs/([\w-]+)$", self.path)
                if hit and hit.group(1) in stub.jobs:
                    return self._send(200, stub.jobs[hit.group(1)])
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                size = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
                if self.path != "/sdcpp/v1/img_gen":
                    return self._send(404, {"error": "not found"})
                with stub._lock:
                    stub.bodies.append(body)
                    n = len(stub.bodies)
                    job = "job-%d" % n
                    stub._log("[INFO   ] stub.cpp:1  - generate_image %dx%d"
                              % (body["width"], body["height"]))
                    if n in stub.fail:
                        stub._log("[ERROR  ] ggml - ggml_backend_cuda_buffer_type_alloc_buffer:"
                                  " allocating 416.00 MiB on device 0: cudaMalloc failed:"
                                  " out of memory")
                        stub.jobs[job] = {"status": "failed", "error": {
                            "message": "generate_image returned no results"}}
                    else:
                        stub._log("[INFO   ] stub.cpp:2  - generate_image completed in 0.01s")
                        guidance = body["sample_params"]["guidance"]["txt_cfg"]
                        png = tiny_png("Negative prompt: %s, CFG scale: %g"
                                       % (body.get("negative_prompt", ""), guidance),
                                       shade=int(guidance * 20) % 256)
                        stub.jobs[job] = {"status": "completed", "result": {"images": [
                            {"b64_json": base64.b64encode(png).decode("ascii")}]}}
                return self._send(202, {"id": job})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, name="stub-sd", daemon=True).start()
        return self

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()


def stub_header(pair_ids, jobs, sd_log: str, total_mib: int = 32607) -> dict:
    return {"ticket": TICKET, "round": 1 if sorted(pair_ids) == sorted(PRIMARY) else 2,
            "pairs": list(pair_ids), "plan": jobs, "notes": [], "thresholds": THRESHOLDS,
            "started": now_iso(), "stub": True,
            "facts": {"gpu": {"name": "stub", "total_mib": total_mib, "used_mib": 0,
                              "driver": "stub"}, "sd_log": sd_log}}


# The stub has no GPU to spend time on, so in the rehearsal a job reports the
# seconds of a modelled card instead of its few milliseconds (Windows' monotonic
# clock can make those 0.0). Only the rehearsal uses this.
REHEARSAL_SECONDS = {1.0: 200.0, 3.0: 330.0, 6.0: 340.0}


def modelled(submit):
    def run(body, base, refine=False):
        png, _took, err = submit(body, base)
        cfg = body["sample_params"]["guidance"]["txt_cfg"]
        return png, REHEARSAL_SECONDS.get(cfg, 1.0), err
    return run


def rehearse(tmp: str, pair_ids=PRIMARY, fail=(), peak_mib: "int | None" = 30000,
             say=lambda *_: None, submit=None, resume: bool = False,
             sd_log: "str | None" = None) -> "tuple[str, str, StubSdServer]":
    """run_series against StubSdServer, with crow_core pointed at it for the
    duration. Returns (status, out dir, stub). Never starts a real server."""
    log = os.path.join(tmp, "sd-server-stub.log")
    open(log, "a", encoding="utf-8").close()
    out = os.path.join(tmp, "round")
    stub = StubSdServer(log, fail).start()
    jobs = plan(pair_ids)
    try:
        with mock.patch.object(core, "IMAGE_SERVER_URL", stub.url), \
                mock.patch.object(core, "image_server_log", lambda: log), \
                mock.patch.object(core, "_IMAGE_PROC", None):
            status = run_series(jobs, out, header=stub_header(pair_ids, jobs, log),
                                sd_log=sd_log or log, sampler=FixedSampler(peak_mib),
                                submit=submit or modelled(core._run_image_job),
                                ensure=lambda: "error: the dress rehearsal starts no server",
                                resume=resume, say=say)
    finally:
        stub.stop()
    return status, out, stub


def answer_all(out: str, absent=None, degraded=None, visible_at_1=None) -> None:
    """Fill answers.json from the key, the way a judge with these results would:
    the object shows at 1.0 (unless the pair is in `visible_at_1` False), is gone
    in a guided picture whose (pair, cfg) is in `absent`, and (pair, cfg) in
    `degraded` is marked degraded. For tests and the selftest only."""
    absent = set(absent or ())
    degraded = set(degraded or ())
    hidden_at_1 = set(visible_at_1 or ())
    with open(os.path.join(out, KEY_NAME), encoding="utf-8") as fh:
        key = json.load(fh)
    form = read_json(os.path.join(out, SHEET, "answers.json"))
    for slot, entry in key["slots"].items():
        for letter in LETTERS:
            if form[slot][letter] is None:
                continue
            k = (entry["pair"], entry[letter]["cfg"])
            visible = (k[0] not in hidden_at_1) if k[1] == BASELINE else (k not in absent)
            form[slot][letter] = {"object_visible": visible, "degraded": k in degraded}
    write_json(os.path.join(out, SHEET, "answers.json"), form)


def selftest(say=print) -> int:
    checks = 0
    jobs = plan(PRIMARY)
    bad, notes = validate_plan(jobs, PRIMARY)
    assert not bad, bad
    checks += 1
    for k in range(1, len(PAIRS) + 1):
        ids = [p.id for p in PAIRS[:k]]
        assert not validate_plan(plan(ids), ids, check_tool=False)[0], k
    checks += 1
    png = tiny_png("CFG scale: 6")
    assert b"tEXt" in png and b"tEXt" not in strip_png_text(png)
    checks += 1
    with tempfile.TemporaryDirectory() as tmp:
        status, out, stub = rehearse(tmp)
        assert status == "complete", status
        assert stub.bodies == warmup_bodies() + [j["body"] for j in jobs], "bodies differ"
        checks += 1
        digest = seal(out, rng=random.Random(TICKET))
        names = sorted(os.listdir(os.path.join(out, SHEET)))
        assert len([n for n in names if n.endswith(".png")]) == 30, names
        for n in names:
            if n.endswith(".png"):
                with open(os.path.join(out, SHEET, n), "rb") as fh:
                    assert b"tEXt" not in fh.read(), n
        checks += 1
        answer_all(out, absent={(p, c) for p in PRIMARY for c in GUIDED})
        result = evaluate([load_round(out, digest)])
        assert result["image_negative_cfg"] == 3.0, result["verdict"]
        checks += 1
        with open(os.path.join(out, KEY_NAME), "ab") as fh:
            fh.write(b" ")
        try:
            load_round(out)
        except RuntimeError:
            checks += 1
        else:
            raise AssertionError("a changed key was read")
    say("selftest: %d checks OK (plan, rounds of 1-15 pairs, PNG strip, dress rehearsal "
        "against a stub sd-server, seal, score, tamper)" % checks)
    return 0


# -------------------------------------------------------------------- CLI --

def _measured_pairs() -> "list[str]":
    found = []
    if os.path.isdir(RUN_ROOT):
        for name in sorted(os.listdir(RUN_ROOT)):
            head = os.path.join(RUN_ROOT, name, "run.json")
            if os.path.isfile(head):
                found += read_json(head).get("pairs", [])
    return found


def cmd_plan(pair_ids, as_json: bool) -> int:
    jobs = plan(pair_ids)
    bad, notes = validate_plan(jobs, pair_ids)
    if as_json:
        print(json.dumps({"jobs": jobs, "problems": bad, "notes": notes}, indent=1))
    else:
        for j in jobs:
            print("%2d  %s  txt_cfg %-3g  seed %-8d  negative_prompt %-12s  sha256 %s"
                  % (j["seq"], j["pair"], j["cfg"], j["body"]["seed"],
                     json.dumps(j["body"].get("negative_prompt")), j["body_sha256"][:16]))
        shown = set()
        for j in jobs:
            if j["cfg"] not in shown:
                shown.add(j["cfg"])
                print("body, txt_cfg %g (%s): %s" % (j["cfg"], j["pair"],
                                                     json.dumps(j["body"], sort_keys=True)))
        print(estimate(len(pair_ids)))
        for note in notes:
            print("note: %s" % note)
        for problem in bad:
            print("PROBLEM: %s" % problem)
        print("plan: %s" % ("INVALID" if bad else "valid -- the 1.0 bodies equal what "
                            "tool_generate_image sends today"))
    return 2 if bad else 0


def cmd_run(a) -> int:
    if a.round == 1:
        pair_ids = list(PRIMARY) if not a.pairs else a.pairs.split(",")
    elif not a.pairs:
        print("--round %d needs --pairs (the next reserves, in order)" % a.round)
        return 2
    else:
        pair_ids = a.pairs.split(",")
    if a.round == 1 and sorted(pair_ids) != sorted(PRIMARY):
        print("round 1 is the ten primary pairs: %s" % ",".join(PRIMARY))
        return 2
    out = a.out or os.path.join(RUN_ROOT, "round-%d" % a.round)
    if a.round > 1 and not a.resume:
        before = _measured_pairs()
        left = [r for r in RESERVES if r not in before]
        if pair_ids != left[:len(pair_ids)]:
            print("replacements are the next unmeasured reserves in order: %s"
                  % ",".join(left[:len(pair_ids)]))
            return 2
    jobs = plan(pair_ids)
    bad, notes = validate_plan(jobs, pair_ids)
    if bad:
        for problem in bad:
            print("PROBLEM: %s" % problem)
        return 2
    sd_log = a.sd_log or default_sd_log()
    facts = gather_facts(sd_log)
    refused = check_preflight(facts)
    if refused:
        for why in refused:
            print("REFUSED: %s" % why)
        return 3
    print("preflight OK: %s, %s, %s MiB total, %s MiB used now; sd-server log %s"
          % (facts["active_point"]["point"], facts["gpu"]["name"], facts["gpu"]["total_mib"],
             facts["gpu"]["used_mib"], sd_log))
    print(estimate(len(pair_ids)))
    os.makedirs(out, exist_ok=True)
    header = {"ticket": TICKET, "round": a.round, "pairs": pair_ids, "plan": jobs,
              "notes": notes, "thresholds": THRESHOLDS, "started": now_iso(), "facts": facts}
    try:
        status = run_series(jobs, out, header=header, sd_log=sd_log,
                            sampler=VramSampler(os.path.join(out, "vram.csv")),
                            resume=a.resume)
    except KeyboardInterrupt:
        print("interrupted. The server finishes its current job in the background; "
              "continue with: python tools/measure_negative_cfg.py run --round %d%s --resume"
              % (a.round, "" if a.round == 1 else " --pairs " + ",".join(pair_ids)))
        return 130
    if status != "complete":
        return 4
    digest = seal(out)
    print("sealed: %s  %s" % (digest, os.path.join(out, KEY_NAME)))
    print("post this sha256 on #339 BEFORE robin opens %s"
          % os.path.join(out, SHEET, "index.html"))
    return 0


def cmd_score(dirs, expect) -> int:
    rounds = [load_round(d, expect[i] if i < len(expect) else None)
              for i, d in enumerate(dirs)]
    result = evaluate(rounds)
    path = os.path.join(os.path.dirname(os.path.abspath(dirs[0])), "score.json")
    write_json(path, result)
    print("pairs counted: %s" % ",".join(result["counted_pairs"]))
    print("pairs replaced (no object at 1.0): %s" % (",".join(result["invalid_pairs"]) or "none"))
    for cfg, arm in result["arms"].items():
        print("txt_cfg %-3s absent %2d/%d  degraded %d  median %s s  ratio %s  oom %d  "
              "peak %s/%s MiB  failed %d%s"
              % (cfg, arm["object_absent"], arm["n"], arm["degraded"], arm["median_wall_s"],
                 arm["time_ratio"], arm["oom_lines"], arm["peak_mib"], arm["capacity_mib"],
                 arm["failed_jobs"], "" if "pass" not in arm else "  -> %s (c1 %s c2 %s c3 %s "
                 "c4 %s)" % ("PASS" if arm["pass"] else "fail", arm["c1_absent"],
                             arm["c2_no_degradation"], arm["c3_time"], arm["c4_memory"])))
    print(result["verdict"])
    print("written: %s" % path)
    return 0 if result["complete"] else 4


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="the same as `plan`")
    ap.add_argument("--selftest", action="store_true", help="the same as `selftest`")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("plan", help="the planned requests, validated; no server")
    p.add_argument("--pairs", default=",".join(PRIMARY))
    p.add_argument("--json", action="store_true")
    sub.add_parser("selftest", help="plan + a dress rehearsal against a stub sd-server")
    r = sub.add_parser("run", help="the measurement (robin's Go)")
    r.add_argument("--round", type=int, default=1)
    r.add_argument("--pairs", help="comma-separated; round 1 is always the primary ten")
    r.add_argument("--out", help="default runs/339-negative-cfg/round-<n>")
    r.add_argument("--sd-log", help="the running sd-server's log (default: found)")
    r.add_argument("--resume", action="store_true")
    s = sub.add_parser("seal", help="the blind sheet and the sealed key for a finished round")
    s.add_argument("dir")
    c = sub.add_parser("score", help="the verdict, after robin's answers")
    c.add_argument("dirs", nargs="+")
    c.add_argument("--expect-sha256", action="append", default=[],
                   help="the sha256 posted on #339, one per DIR in order")
    a = ap.parse_args(argv)
    cmd = "plan" if a.dry_run else "selftest" if a.selftest else a.cmd
    if cmd == "plan":
        pairs = getattr(a, "pairs", None) or ",".join(PRIMARY)
        return cmd_plan(pairs.split(","), getattr(a, "json", False))
    if cmd == "selftest":
        return selftest()
    if cmd == "run":
        return cmd_run(a)
    if cmd == "seal":
        print("sealed: %s" % seal(a.dir))
        return 0
    if cmd == "score":
        return cmd_score(a.dirs, a.expect_sha256)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
