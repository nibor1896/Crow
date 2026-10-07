r"""#346: LTX prompt enhance A/B/C -- nine clips through Crow's own animate path.

runs/340-enhance-ab/PREREG.md, committed before the first clip, fixes the arms, the
stills, the seeds, the order, the blind protocol and the decision rule. This file
carries them out and checks that it carries out exactly those.

  python tools/enhance_ab.py --selftest   no GPU, no server, no download: the arms,
                                          the stills, the PREREG (alias --dry-run)
  python tools/enhance_ab.py --go         the nine clips (Media Stack booted, e2b on
                                          disk), then the blind sheet and the sealed key
  python tools/enhance_ab.py --unblind    after robin's answers: the seal, the tally,
                                          the decision rule

THE ARMS ARE FILES AND A DELTA. arm-A.json is cli/workflows/ltx25_i2v_api.json
unchanged; arm-B.json and arm-C.json are derive_arms() of it, frozen when the PREREG
was written. The selftest holds the files against the delta and against the
template and node source in the installed ComfyUI, so none of them drifts quietly.

CROW'S OWN PATH. Each clip is one crow_core.tool_animate_image call: the language
model steps aside, ComfyUI starts fresh, the clip renders, ComfyUI ends and the
model comes back. For that one call crow_core.VIDEO_WORKFLOW names the arm's file;
tool_animate_image reads the name at call time, so nothing in cli/ changes.

Exit: 0 done / every check holds, 1 a check failed, 2 setup (wrong point, missing file).
"""

import argparse
import contextlib
import copy
import hashlib
import html
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "cli"))
import crow_core  # noqa: E402
import crow_platform  # noqa: E402

RUN = os.path.join(REPO, "runs", "340-enhance-ab")
PREREG = os.path.join(RUN, "PREREG.md")
RESULTS = os.path.join(RUN, "results.jsonl")
RATING = os.path.join(RUN, "rating")
KEY = os.path.join(RUN, "rating-key.json")
SEAL = os.path.join(RUN, "rating-key.sha256")
ANSWERS = os.path.join(RUN, "rating-answers.json")
DEFAULT_WORKFLOW = crow_core.VIDEO_WORKFLOW
ARMS = ("A", "B", "C")

# --------------------------------------------------------------- the stills
# The three stills of 2026-10-03 (#346, Proposed fix 1). Motion text and seed are
# what reached LTX in robin's runs, read from the `prompt` tag ComfyUI's SaveVideo
# wrote into each clip (nodes 398:376 and 398:339). sha256 is the still's bytes,
# equal to the copy those runs uploaded into ComfyUI's input folder.
STILLS = {
    "S1": {
        "name": "the key crow",
        "path": "~/images/20261003-123648-a-still-from-a-high-budget-3d-animated.png",
        "sha256": "1de92cb1fd06dfb1ead957371ab94bed619f614055f730dcb36436e3a8b24be9",
        "seed": 746329003, "seconds": 5,
        "motion": (
            "The black crow tilts its head curiously to one side, looks at the brass key, "
            "hops one small step forward, bends down and picks up the key in its beak, then "
            "lifts its head and holds the key proudly. The desk, the window, the plant and the "
            "room stay completely still. The camera holds still. No new objects, no cuts. "
            "Sound: two soft taps of the crow's feet hopping on the wooden desk, a light "
            "metallic clink as the key is picked up, one short cheerful caw, a quiet calm room, "
            "no static, no hiss, no music, no speech."),
    },
    "S2": {
        "name": "2B with the crow landing",
        "path": "~/Desktop/ct/images/20261003-114913-high-quality-anime-key-visual-cinematic.png",
        "sha256": "334d96657c576d851ee3594323eb3b2fd35300cb6a38dd141a07c76dbcfb8341",
        "seed": 497572401, "seconds": 5,
        "motion": (
            "2B slowly raises her left arm out to the side at shoulder height with the gloved "
            "hand open and the back of the hand up. The black crow flies in from the right, "
            "beats its wings a few times as it slows down, and lands on her raised left hand "
            "and wrist, gripping it, then folds its wings and settles. Her right hand keeps "
            "holding the katana pointing down. Her blindfold and headband stay in place, her "
            "hair only moves slightly. The background stays completely still: the city, the sun "
            "and the sky do not move. The camera holds still. No new objects, no cuts. Sound: "
            "the heavy flapping of the crow's wings coming closer, one short caw from the crow, "
            "a soft creak of the leather glove as the crow lands, a faint quiet wind, otherwise "
            "quiet, no static, no hiss, no music, no speech."),
    },
    "S3": {
        "name": "2B with the sign",
        "path": "~/Desktop/ct/images/20261002-084445-ultra-high-resolution-wide-16-9 - Kopie.png",
        "sha256": "347949c4344c4da5ebe88e1d5321e7caebb6f27dd252d1f46778311d5449aa5f",
        "seed": 912134647, "seconds": 5,
        "motion": (
            "2B keeps sitting on the mossy concrete block with her chin resting on her left "
            "hand, unchanged. Only the toe of her right black boot taps up and down slowly a "
            "few times, as if she is waiting. The black crow standing in the grass on the right "
            "bends its head and preens the feathers under its right wing with its beak. The "
            "sign, the grass, the clouds and the sky stay completely still. The camera holds "
            "still. No new objects, no cuts. Sound: a soft breeze in the grass, the quiet "
            "rustle of the crow's feathers, a faint tap of the boot, no music, no speech."),
    },
}

# Arms alternated per still as a 3x3 Latin square: every arm once per still and
# once in each position within a still.
ORDER = (("S1", "A"), ("S1", "B"), ("S1", "C"),
         ("S2", "B"), ("S2", "C"), ("S2", "A"),
         ("S3", "C"), ("S3", "A"), ("S3", "B"))

# ------------------------------------------------------------------ the arms
# The template's enhancer in API form: subgraph nodes 393 (CLIPLoader) and 380
# (TextGenerateLTX2Prompt) of video_ltx2_5_i2v.json (comfyui_workflow_templates_json
# 0.1.96, shipped with ComfyUI v0.38.0 portable). Input names: TextGenerate's schema
# in comfy_extras/nodes_textgen.py @ v0.38.0 (TextGenerateLTX2Prompt reuses it);
# a DynamicCombo's children travel as "<combo>.<child>" (comfy_api/latest/_io.py
# finalize_prefix). `mtp` is not set: the template predates that input, so the
# node's default "auto" applies, as it does when the template is queued.
E2B = "gemma4_e2b_it_int8_convrot.safetensors"
E2B_BYTES = 5199997904
E2B_SHA256 = "efeca0fcad2f863e5ed0a75e3af952b72bc963604c1dda6d20aee87a32b17566"
E2B_URL = ("https://huggingface.co/Comfy-Org/gemma-4/resolve/"
           "63d0f7c476756b88910170c1df75e2384ea1af31/text_encoders/" + E2B)
ENHANCER = {
    "398:393": {"class_type": "CLIPLoader",
                "inputs": {"clip_name": E2B, "type": "ltxv", "device": "default"},
                "_meta": {"title": "Load CLIP"}},
    "398:380": {"class_type": "TextGenerateLTX2Prompt",
                "inputs": {"prompt": ["398:376", 0], "max_length": 600, "sampling_mode": "on",
                           "sampling_mode.temperature": 0.7, "sampling_mode.top_k": 64,
                           "sampling_mode.top_p": 0.95, "sampling_mode.min_p": 0.05,
                           "sampling_mode.repetition_penalty": 1.15, "sampling_mode.seed": 0,
                           "sampling_mode.presence_penalty": 0, "thinking": False,
                           "use_default_template": True,
                           "clip": ["398:393", 0], "image": ["398:350", 0]},
                "_meta": {"title": "Generate LTX2 Prompt"}},
}
# The order the frontend stores node 380's widgets in (template widgets_values);
# ComfyUI's own blueprint "Image to Video (LTX-2.5).json" names them in this order.
WIDGET_ORDER = ("prompt", "max_length", "sampling_mode", "sampling_mode.temperature",
                "sampling_mode.top_k", "sampling_mode.top_p", "sampling_mode.min_p",
                "sampling_mode.repetition_penalty", "sampling_mode.seed",
                "sampling_mode.presence_penalty", "thinking", "use_default_template")
# Arm C: the ticket's 1280x720 into the subgraph's Width/Height (398:372/398:360),
# which then no longer read the ResolutionSelector (403) video_workflow() sets.
C_SIZE = (1280, 720)

# Where each link the arms touch must come from. The Phase 0 bypass wired the
# switch's on_true to the e2b CLIPLoader -- a CLIP where a STRING belongs.
_RAW = "PrimitiveStringMultiline"
WIRING = {
    "A": {("398:382", "on_false"): _RAW, ("398:382", "on_true"): _RAW,
          ("398:364", "text"): "ComfySwitchNode"},
    "B": {("398:382", "on_false"): _RAW, ("398:382", "on_true"): "TextGenerateLTX2Prompt",
          ("398:364", "text"): "ComfySwitchNode", ("398:380", "prompt"): _RAW,
          ("398:380", "clip"): "CLIPLoader", ("398:380", "image"): "LTXVPreprocess"},
}
WIRING["C"] = WIRING["B"]


def arm_path(arm: str) -> str:
    return os.path.join(RUN, "arm-%s.json" % arm)


def derive_arms(base: dict) -> dict:
    """{arm: API prompt}: A is `base`, B adds the enhancer and turns it on, C is B at C_SIZE."""
    b = copy.deepcopy(base)
    b.update(copy.deepcopy(ENHANCER))
    b["398:383"]["inputs"]["value"] = True
    b["398:382"]["inputs"]["on_true"] = ["398:380", 0]
    c = copy.deepcopy(b)
    c["398:372"]["inputs"]["value"], c["398:360"]["inputs"]["value"] = C_SIZE
    return {"A": copy.deepcopy(base), "B": b, "C": c}


def json_sha256(obj) -> str:
    """sha256 of the canonical JSON: the same on an LF and a CRLF checkout."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def _load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ checks
def check_graph(wf: dict, arm: str) -> "list[str]":
    """Every link resolves, crow_core's node ids exist, the arm's wiring holds."""
    bad = []
    for nid, node in wf.items():
        if not isinstance(node, dict) or not node.get("class_type") \
                or not isinstance(node.get("inputs"), dict):
            bad.append("%s: node %s has no class_type or inputs" % (arm, nid))
            continue
        for name, value in node["inputs"].items():
            if not isinstance(value, list):
                continue
            if len(value) != 2 or not isinstance(value[0], str) \
                    or not isinstance(value[1], int) or value[1] < 0:
                bad.append("%s: %s.%s is a malformed link %r" % (arm, nid, name, value))
            elif value[0] not in wf:
                bad.append("%s: %s.%s links to node %s, which is not in the graph"
                           % (arm, nid, name, value[0]))
    for nid in (crow_core._VN_IMAGE, crow_core._VN_PROMPT, crow_core._VN_SECONDS,
                crow_core._VN_SEED, crow_core._VN_SIZE, crow_core._VN_SAVE):
        if nid not in wf:
            bad.append("%s: node %s, which crow_core.video_workflow sets, is missing" % (arm, nid))
    if bad:
        return bad
    for (nid, name), want in WIRING[arm].items():
        link = wf.get(nid, {}).get("inputs", {}).get(name)
        got = wf[link[0]]["class_type"] if isinstance(link, list) else None
        if got != want:
            bad.append("%s: %s.%s comes from %s, not from a %s" % (arm, nid, name, got, want))
    enhance = wf.get("398:383", {}).get("inputs", {}).get("value")
    if enhance is not (arm != "A"):
        bad.append("%s: Enable Prompt Enhance (398:383) is %r" % (arm, enhance))
    size = (wf["398:372"]["inputs"].get("value"), wf["398:360"]["inputs"].get("value"))
    want_size = C_SIZE if arm == "C" else (["403", 0], ["403", 1])
    if size != want_size:
        bad.append("%s: Width/Height (398:372/398:360) are %r, not %r" % (arm, size, want_size))
    if arm == "A" and ("398:380" in wf or "398:393" in wf):
        bad.append("A: carries an enhancer node")
    if arm != "A" and wf["398:393"]["inputs"].get("clip_name") != E2B:
        bad.append("%s: the enhancer's CLIPLoader does not load %s" % (arm, E2B))
    return bad


def textgen_inputs(source: str) -> "set[str]":
    """The input names TextGenerate declares in comfy_extras/nodes_textgen.py."""
    m = re.search(r"class TextGenerate\(io\.ComfyNode\):(.*?)\nclass ", source, re.S)
    return set(re.findall(r'io\.\w+\.Input\(\s*"([^"]+)"', m.group(1) if m else ""))


def check_textgen_source(source: str) -> "list[str]":
    """The arms' TextGenerateLTX2Prompt inputs against the node's own source."""
    bad = []
    if 'node_id="TextGenerateLTX2Prompt"' not in source:
        bad.append("nodes_textgen.py: no node TextGenerateLTX2Prompt")
    if "inputs=parent_schema.inputs" not in source:
        bad.append("nodes_textgen.py: TextGenerateLTX2Prompt no longer takes TextGenerate's inputs")
    names = textgen_inputs(source)
    for key in ENHANCER["398:380"]["inputs"]:
        if key.split(".", 1)[-1] not in names:
            bad.append("nodes_textgen.py: TextGenerate has no input %r" % key)
    return bad


def check_template(template: dict, blueprint: "dict | None") -> "list[str]":
    """ENHANCER against the template's own nodes 380/393, value by value."""
    nodes = {}
    for sg in template.get("definitions", {}).get("subgraphs", []):
        nodes.update({n["id"]: n for n in sg.get("nodes", [])})
    bad = []
    if 380 not in nodes or 393 not in nodes:
        return ["template: no subgraph nodes 380 and 393"]
    got = dict(zip(WIDGET_ORDER, nodes[380].get("widgets_values") or []))
    got.pop("prompt", None)
    want = {k: v for k, v in ENHANCER["398:380"]["inputs"].items() if not isinstance(v, list)}
    if got != want:
        bad.append("template: node 380 has %r, the arms %r" % (got, want))
    loader = ENHANCER["398:393"]["inputs"]
    if nodes[393].get("widgets_values") != [loader["clip_name"], loader["type"], loader["device"]]:
        bad.append("template: node 393 has %r" % nodes[393].get("widgets_values"))
    if blueprint is not None:
        found = None
        for sg in blueprint.get("definitions", {}).get("subgraphs", []):
            for n in sg.get("nodes", []):
                if n.get("type") == "TextGenerateLTX2Prompt":
                    found = tuple((i.get("widget") or {}).get("name") for i in n.get("inputs", [])
                                  if i.get("widget"))
        if found != WIDGET_ORDER:
            bad.append("blueprint: TextGenerateLTX2Prompt's widgets are %r" % (found,))
    return bad


def check_prereg(text: str, arms: dict) -> "list[str]":
    """Everything the run uses is written in the committed PREREG, verbatim."""
    bad = []
    for sid, s in STILLS.items():
        for what in ("sha256", "seed", "motion"):
            if str(s[what]) not in text:
                bad.append("PREREG: %s's %s is not in it" % (sid, what))
    for arm, wf in arms.items():
        if json_sha256(wf) not in text:
            bad.append("PREREG: arm %s's sha256 %s is not in it" % (arm, json_sha256(wf)))
    order = " ".join("%s-%s" % pair for pair in ORDER)
    if order not in text:
        bad.append("PREREG: the run order %r is not in it" % order)
    return bad


def check_calls(arms: dict) -> "list[str]":
    """video_workflow() on each arm sets this call's fields and leaves the arm's wiring."""
    bad = []
    for arm, wf in arms.items():
        sent = crow_core.video_workflow(wf, "x.png", "m", 5, "1080p", 1, False)
        bad += check_graph(sent, arm)
        if sent[crow_core._VN_PROMPT]["inputs"]["value"] != "m":
            bad.append("%s: video_workflow did not set the motion text" % arm)
    return bad


def selftest(comfy_dir: "str | None") -> "list[tuple[str, list[str]]]":
    """[(check, problems)], one entry per check; [] problems means it holds."""
    out = []
    base = _load(DEFAULT_WORKFLOW)
    derived = derive_arms(base)
    files, missing = {}, []
    for arm in ARMS:
        try:
            files[arm] = _load(arm_path(arm))
        except (OSError, ValueError) as exc:
            missing.append("%s: %s" % (arm_path(arm), exc))
    out.append(("arm files read", missing))
    if missing:
        return out
    out.append(("arm files equal derive_arms(%s)" % os.path.relpath(DEFAULT_WORKFLOW, REPO),
                ["arm %s differs from the delta" % a for a in ARMS if files[a] != derived[a]]))
    out.append(("graphs: links resolve, node ids exist, wiring per arm",
                [p for a in ARMS for p in check_graph(files[a], a)]))
    out.append(("crow_core.video_workflow keeps each arm", check_calls(files)))
    try:
        with open(PREREG, encoding="utf-8") as fh:
            out.append(("PREREG names stills, seeds, texts, arm sha256, order",
                        check_prereg(fh.read(), files)))
    except OSError as exc:
        out.append(("PREREG read", [str(exc)]))
    if comfy_dir:
        src = os.path.join(comfy_dir, "ComfyUI", "comfy_extras", "nodes_textgen.py")
        tpl = os.path.join(comfy_dir, "python_embeded", "Lib", "site-packages",
                           "comfyui_workflow_templates_json", "templates", "video_ltx2_5_i2v.json")
        bp = os.path.join(comfy_dir, "ComfyUI", "blueprints", "Image to Video (LTX-2.5).json")
        if os.path.isfile(src):
            with open(src, encoding="utf-8") as fh:
                out.append(("enhancer inputs against %s" % src, check_textgen_source(fh.read())))
        if os.path.isfile(tpl):
            out.append(("enhancer values against %s" % tpl,
                        check_template(_load(tpl), _load(bp) if os.path.isfile(bp) else None)))
    stills = []
    for sid, s in STILLS.items():
        path = os.path.expanduser(s["path"])
        if not os.path.isfile(path):
            stills.append("%s: %s is not there" % (sid, path))
        elif file_sha256(path) != s["sha256"]:
            stills.append("%s: %s has other bytes than the PREREG names" % (sid, path))
    out.append(("stills on disk, sha256 as in the PREREG", stills))
    return out


# --------------------------------------------------------------- the clips
def text_encoder_dirs(comfy_dir: str) -> "list[str]":
    """Where ComfyUI looks for text encoders: extra_model_paths.yaml (CrowSetup's
    one-entry form, #340), then its own models folder."""
    dirs = [os.path.join(comfy_dir, "ComfyUI", "models", "text_encoders")]
    try:
        with open(os.path.join(comfy_dir, "ComfyUI", "extra_model_paths.yaml"),
                  encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return dirs
    base = re.search(r"^\s*base_path:\s*['\"]?(.+?)['\"]?\s*$", text, re.M)
    sub = re.search(r"^\s*text_encoders:\s*['\"]?(.+?)['\"]?\s*$", text, re.M)
    if base and sub:
        dirs.insert(0, os.path.join(base.group(1), sub.group(1)))
    return dirs


def preflight(core, hash_e2b: bool = True) -> "list[str]":
    """What must hold before the first clip; [] when the run may start."""
    bad = []
    doc, servers = core._media_servers()
    if servers is None:
        bad.append("no Media Stack running: boot the point media-stack from Crow's start "
                   "window first (the running point is %s)" % ((doc or {}).get("point")))
    else:
        dirs = text_encoder_dirs(servers["video"].get("cwd") or "")
        e2b = next((os.path.join(d, E2B) for d in dirs if os.path.isfile(os.path.join(d, E2B))), None)
        if e2b is None:
            bad.append("%s is not downloaded: %s (%s bytes) into %s"
                       % (E2B, E2B_URL, "{:,}".format(E2B_BYTES), dirs[0]))
        elif os.path.getsize(e2b) != E2B_BYTES:
            bad.append("%s has %d bytes, not %d" % (e2b, os.path.getsize(e2b), E2B_BYTES))
        elif hash_e2b and file_sha256(e2b) != E2B_SHA256:
            bad.append("%s has other bytes than %s" % (e2b, E2B_SHA256))
    for tool in ("ffmpeg", "ffprobe", "nvidia-smi"):
        if not shutil.which(tool):
            bad.append("%s is not on PATH" % tool)
    if os.path.exists(RESULTS):
        bad.append("%s exists: the series runs once; move that run aside first" % RESULTS)
    return bad


@contextlib.contextmanager
def arm_workflow(core, path: str):
    """For one call: crow_core.VIDEO_WORKFLOW names the arm's file, and what the
    call sent and got back is recorded. Everything is put back, also on a raise."""
    seen = {}
    saved = (core.VIDEO_WORKFLOW, core._video_request, core._run_video_job)
    ask, job = saved[1], saved[2]

    def request(path_, body=None, **kw):
        raw = ask(path_, body, **kw)
        if path_ == "/prompt" and body is not None:
            seen["sent"] = body.get("prompt")
        elif path_.startswith("/history/"):
            seen["history"] = raw
        return raw

    def run_job(wf, base):
        out = job(wf, base)
        seen["render_s"] = round(out[2], 1)
        return out

    core.VIDEO_WORKFLOW, core._video_request, core._run_video_job = path, request, run_job
    try:
        yield seen
    finally:
        core.VIDEO_WORKFLOW, core._video_request, core._run_video_job = saved


def caption(raw) -> "str | None":
    """The text the switch handed the 12B (Preview as Text, 398:381) from /history."""
    try:
        history = json.loads(raw or b"{}")
    except ValueError:
        return None
    for entry in (history or {}).values():
        text = ((entry.get("outputs") or {}).get("398:381") or {}).get("text")
        if text:
            return str(text[0])
    return None


def peak_mib(csv_text: str) -> "int | None":
    values = [int(v) for v in re.findall(r"^\s*(\d+)\s*$", csv_text, re.M)]
    return max(values) if values else None


class Vram:
    """nvidia-smi every 500 ms for one call: the whole card, the language model's
    share before it steps aside included."""

    def __init__(self, csv_path: str):
        self.csv_path, self.peak = csv_path, None

    def __enter__(self):
        self.fh = open(self.csv_path, "w")
        self.proc = subprocess.Popen(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
             "-lms", "500"], stdout=self.fh, stderr=subprocess.DEVNULL,
            **crow_platform.no_console_kwargs())
        return self

    def __exit__(self, *exc):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.fh.close()
        with open(self.csv_path, encoding="utf-8", errors="replace") as fh:
            self.peak = peak_mib(fh.read())
        return False


def probe(path: str) -> dict:
    """Width, height and frame count read back from the clip."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=width,height,nb_read_packets", "-of", "json",
                          path], capture_output=True, text=True, timeout=120)
    s = (json.loads(out.stdout or "{}").get("streams") or [{}])[0]
    frames = s.get("nb_read_packets")
    return {"width": s.get("width"), "height": s.get("height"),
            "frames": int(frames) if frames else None}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_clip(core, index: int, sid: str, arm: str, vram=Vram, readback=probe) -> dict:
    """One clip through tool_animate_image; the row results.jsonl gets."""
    s = STILLS[sid]
    tag = "%s-%s" % (sid, arm)
    row = {"index": index, "clip": tag, "still": sid, "arm": arm, "seed": s["seed"],
           "seconds": s["seconds"], "workflow": "arm-%s.json" % arm, "started": _now()}
    core.take_announced_videos()
    began = time.monotonic()
    with arm_workflow(core, arm_path(arm)) as seen, \
            vram(os.path.join(RUN, "vram-%s.csv" % tag)) as card:
        said = core.tool_animate_image(image=os.path.join(RUN, "inputs", sid + ".png"),
                                       motion=s["motion"], seconds=s["seconds"],
                                       resolution="1080p", seed=s["seed"])
    row.update(ended=_now(), call_s=round(time.monotonic() - began, 1),
               render_s=seen.get("render_s"), peak_vram_mib=card.peak, result=said,
               caption=caption(seen.get("history")))
    row["status"] = ("ok" if said.startswith("saved ") else
                     "stopped" if said.startswith(core.STOPPED) else "error")
    if seen.get("sent") is not None:
        with open(os.path.join(RUN, "workflow-api-%s.json" % tag), "w", encoding="utf-8") as fh:
            json.dump(seen["sent"], fh, indent=1)
        row["sent_sha256"] = json_sha256(seen["sent"])
    clips = core.take_announced_videos()
    if row["status"] == "ok" and clips:
        row["output"] = os.path.relpath(clips[-1]["path"], RUN).replace(os.sep, "/")
        row.update(readback(clips[-1]["path"]))
    return row


# ------------------------------------------------------------ blind rating
QUESTIONS = (("action", "(a) The requested action happened"),
             ("identity", "(b) Every object the text names keeps its identity"),
             ("camera", "(c) The camera does what the text says"))


def seal(rows: list, rng=None, strip=None) -> str:
    """Shuffle the ok clips under neutral names, write the key BEFORE the sheet,
    return the key's sha256 (the seal robin's answers are opened against)."""
    rng = rng or random.SystemRandom()
    strip = strip or _strip_metadata
    ok = [r for r in rows if r["status"] == "ok"]
    rng.shuffle(ok)
    os.makedirs(RATING, exist_ok=True)
    key = {"written": _now(), "prereg": "runs/340-enhance-ab/PREREG.md", "clips": {}}
    for i, r in enumerate(ok, 1):
        name = "clip-%02d" % i
        strip(os.path.join(RUN, r["output"]), os.path.join(RATING, name + ".mp4"))
        shutil.copyfile(os.path.join(RUN, "inputs", r["still"] + ".png"),
                        os.path.join(RATING, "still-%02d.png" % i))
        key["clips"][name] = {"clip": r["clip"], "still": r["still"], "arm": r["arm"],
                              "seed": r["seed"], "output": r["output"]}
    raw = json.dumps(key, indent=1).encode("utf-8")
    with open(KEY, "wb") as fh:
        fh.write(raw)
    sealed = hashlib.sha256(raw).hexdigest()
    with open(SEAL, "w", encoding="utf-8") as fh:
        fh.write("%s  rating-key.json\n" % sealed)
    cards = "\n".join(_card(i, STILLS[r["still"]]["motion"]) for i, r in enumerate(ok, 1))
    with open(os.path.join(RATING, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(_SHEET.replace("{n}", str(len(ok))).replace("{cards}", cards))
    return sealed


def _strip_metadata(src: str, dst: str) -> None:
    """A stream copy without the container tags: SaveVideo's `prompt` tag names the arm."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-map", "0", "-map_metadata", "-1",
                    "-c", "copy", dst], check=True, capture_output=True, timeout=120)


def _card(i: int, motion: str) -> str:
    qs = "".join(
        '<fieldset><legend>%s</legend><label><input type="radio" name="%s-%02d" value="yes"> yes'
        '</label><label><input type="radio" name="%s-%02d" value="no"> no</label></fieldset>'
        % (html.escape(text), key, i, key, i) for key, text in QUESTIONS)
    return ('<section class="card" data-clip="clip-%02d"><h2>clip-%02d</h2>'
            '<p class="motion">%s</p><div class="pair"><img src="still-%02d.png" alt="input still">'
            '<video src="clip-%02d.mp4" controls loop playsinline></video></div>%s'
            '<input class="note" name="note-%02d" placeholder="note (optional)"></section>'
            % (i, i, html.escape(motion), i, i, qs, i))


_SHEET = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Clip rating</title><style>
:root{--bg:#fff;--fg:#111;--mut:#666;--line:#ddd}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#eee;--mut:#999;--line:#333}}
body{background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif;margin:0 auto;max-width:1400px;padding:16px}
.card{border-top:1px solid var(--line);padding:12px 0} h2{margin:0 0 8px;font-size:16px}
.motion{color:var(--mut)} .pair{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.pair img,.pair video{width:100%;background:#000} @media (max-width:700px){.pair{grid-template-columns:1fr}}
fieldset{border:0;padding:4px 0;margin:0} legend{color:var(--mut)} label{margin-right:16px}
.note{width:100%;font:inherit;margin-top:4px} button{font:inherit;padding:8px 14px;margin:16px 0}
textarea{width:100%;height:140px}
</style></head><body>
<h1>#346 prompt enhance, blind clip rating</h1>
<p>{n} clips in random order. Left the input still, right the clip, above it the motion text it was given.
Three answers per clip; save the copied answers as runs/340-enhance-ab/rating-answers.json.</p>
{cards}
<button id="go">Copy answers</button><textarea id="out" readonly></textarea>
<script>
document.getElementById('go').onclick=()=>{const r={};document.querySelectorAll('.card').forEach((c,i)=>{
const num=String(i+1).padStart(2,'0');const v=k=>(document.querySelector(`input[name="${k}-${num}"]:checked`)||{}).value||null;
r[c.dataset.clip]={action:v('action'),identity:v('identity'),camera:v('camera'),
note:(document.querySelector(`input[name="note-${num}"]`)||{}).value||''}});
const t=JSON.stringify(r,null,1);document.getElementById('out').value=t;try{navigator.clipboard.writeText(t)}catch(e){}};
</script></body></html>
"""


def tally(key: dict, answers: dict, rows: list) -> dict:
    """Yes votes per arm and question, summed over the stills. A clip that did not
    render counts as no on all three (PREREG); an unanswered clip is an error."""
    t = {arm: {"action": 0, "identity": 0, "camera": 0, "failed": 0} for arm in ARMS}
    for r in rows:
        if r["status"] != "ok":
            t[r["arm"]]["failed"] += 1
    for name, k in key["clips"].items():
        given = answers.get(name) or {}
        for q, _text in QUESTIONS:
            if given.get(q) not in ("yes", "no"):
                raise ValueError("%s has no yes/no answer for %s" % (name, q))
            t[k["arm"]][q] += given[q] == "yes"
    return t


def decide(t: dict) -> dict:
    """The ticket's rule: B or C wins if it gets more yes votes than A on (a) and (b)
    summed over the three stills, without losing on (c) -- read as in the PREREG."""
    ab = {arm: t[arm]["action"] + t[arm]["identity"] for arm in ARMS}
    return {arm: ab[arm] > ab["A"] and t[arm]["camera"] >= t["A"]["camera"] for arm in ("B", "C")}


def unblind() -> int:
    with open(KEY, "rb") as fh:
        raw = fh.read()
    with open(SEAL, encoding="utf-8") as fh:
        sealed = fh.read().split()[0]
    if hashlib.sha256(raw).hexdigest() != sealed:
        print("rating-key.json does not match its seal %s -- not opened" % sealed)
        return 1
    with open(RESULTS, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    t = tally(json.loads(raw), _load(ANSWERS), rows)
    won = decide(t)
    with open(os.path.join(RUN, "tally.json"), "w", encoding="utf-8") as fh:
        json.dump({"seal": sealed, "tally": t, "wins": won}, fh, indent=1)
    print("seal %s holds" % sealed)
    for arm in ARMS:
        x = t[arm]
        print("%s: (a) %d  (b) %d  (c) %d  of %d stills, %d not rendered%s"
              % (arm, x["action"], x["identity"], x["camera"], len(STILLS), x["failed"],
                 "" if arm == "A" else ("  -> wins" if won[arm] else "  -> does not win")))
    return 0


# -------------------------------------------------------------------- main
def go(comfy_dir: "str | None") -> int:
    failed = [(name, p) for name, p in selftest(comfy_dir) if p]
    for name, problems in failed:
        print("FAIL %s: %s" % (name, "; ".join(problems)))
    if failed:
        return 1
    bad = preflight(crow_core)
    if bad:
        print("not started:\n  " + "\n  ".join(bad))
        return 2
    os.makedirs(os.path.join(RUN, "inputs"), exist_ok=True)
    for sid, s in STILLS.items():
        shutil.copyfile(os.path.expanduser(s["path"]), os.path.join(RUN, "inputs", sid + ".png"))
    crow_core.set_root(RUN)
    crow_core.INTERRUPT.clear()
    stop = threading.Event()

    def on_ctrl_c(*_):
        stop.set()
        crow_core.INTERRUPT.set()

    before = signal.signal(signal.SIGINT, on_ctrl_c)
    rows = []
    try:
        for index, (sid, arm) in enumerate(ORDER, 1):
            if stop.is_set():
                break
            row = run_clip(crow_core, index, sid, arm)
            rows.append(row)
            with open(RESULTS, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print("%d/%d %s %s call %.1f s render %s s peak %s MiB %sx%s"
                  % (index, len(ORDER), row["clip"], row["status"], row["call_s"],
                     row.get("render_s"), row.get("peak_vram_mib"), row.get("width"),
                     row.get("height")))
    finally:
        signal.signal(signal.SIGINT, before)
    if stop.is_set():
        print("stopped after %d of %d clips; no sheet, no key" % (len(rows), len(ORDER)))
        return 1
    sealed = seal(rows)
    print("blind sheet: %s\nkey sealed: rating-key.json sha256 %s -- post it on #346 "
          "before robin rates" % (os.path.join(RATING, "index.html"), sealed))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/enhance_ab.py", description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest", "--dry-run", action="store_true",
                      help="check arms, stills and PREREG; no GPU, no server")
    mode.add_argument("--go", action="store_true", help="render the nine clips, then seal")
    mode.add_argument("--unblind", action="store_true", help="open the key against the seal")
    ap.add_argument("--comfy", default=os.path.join(crow_platform.install_dir(), "comfyui"),
                    help="the ComfyUI portable folder whose template and node source the "
                         "selftest reads (default: the installed one)")
    args = ap.parse_args(argv)
    if args.unblind:
        return unblind()
    if args.go:
        return go(args.comfy)
    results = selftest(args.comfy)
    for name, problems in results:
        print(("ok   %s" % name) if not problems else
              "FAIL %s:\n       %s" % (name, "\n       ".join(problems)))
    failed = sum(1 for _n, p in results if p)
    print("selftest: %d checks, %s" % (len(results),
                                       "all hold" if not failed else "%d failed" % failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
