"""enhance_ab.py (#346) without a GPU, a server or a download.

The arms are checked as committed; everything that writes (a clip row, the blind
sheet, the key, the tally) writes into a temp dir with a fake crow_core standing in
for ComfyUI. The one case that reads the installed ComfyUI skips where there is none.
"""

import copy
import hashlib
import json
import os
import random
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import enhance_ab as E  # noqa: E402

# nodes_textgen.py @ v0.38.0 abridged to the lines the check reads: TextGenerate's
# inputs (:4-49) and TextGenerateLTX2Prompt taking them over (:224-235).
TEXTGEN = '''from comfy_api.latest import ComfyExtension, io
class TextGenerate(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        sampling_options = [
            io.DynamicCombo.Option(key="on", inputs=[
                io.Float.Input("temperature", default=0.7),
                io.Int.Input("top_k", default=64),
                io.Float.Input("top_p", default=0.95),
                io.Float.Input("min_p", default=0.05),
                io.Float.Input("repetition_penalty", default=1.05),
                io.Int.Input("seed", default=0),
                io.Float.Input("presence_penalty", optional=True, default=0.0),
            ]),
            io.DynamicCombo.Option(key="off", inputs=[]),
        ]
        return io.Schema(node_id="TextGenerate", inputs=[
            io.Clip.Input("clip"),
            io.String.Input("prompt", multiline=True, default=""),
            io.Image.Input("image", optional=True),
            io.Int.Input("max_length", default=512),
            io.DynamicCombo.Input("sampling_mode", options=sampling_options),
            io.Boolean.Input("thinking", optional=True, default=False),
            io.Boolean.Input("use_default_template", optional=True, default=True),
        ])
class TextGenerateLTX2Prompt(TextGenerate):
    @classmethod
    def define_schema(cls):
        parent_schema = super().define_schema()
        return io.Schema(
            node_id="TextGenerateLTX2Prompt",
            inputs=parent_schema.inputs,
        )
'''


def template(values=None, loader=None):
    """video_ltx2_5_i2v.json reduced to its subgraph nodes 380 and 393."""
    return {"definitions": {"subgraphs": [{"nodes": [
        {"id": 380, "type": "TextGenerateLTX2Prompt",
         "widgets_values": values or ["", 600, "on", 0.7, 64, 0.95, 0.05, 1.15, 0, 0, False, True]},
        {"id": 393, "type": "CLIPLoader",
         "widgets_values": loader or ["gemma4_e2b_it_int8_convrot.safetensors", "ltxv", "default"]},
    ]}]}}


def blueprint(names=E.WIDGET_ORDER):
    inputs = [{"name": "clip", "link": 1}] + [{"name": n, "widget": {"name": n}} for n in names]
    return {"definitions": {"subgraphs": [{"nodes": [
        {"id": 406, "type": "TextGenerateLTX2Prompt", "inputs": inputs}]}]}}


def arms():
    return {arm: E._load(E.arm_path(arm)) for arm in E.ARMS}


class TheArmsTests(unittest.TestCase):
    def test_the_files_are_the_delta_of_todays_workflow(self):
        base = E._load(E.DEFAULT_WORKFLOW)
        files = arms()
        self.assertEqual(files, E.derive_arms(base))
        self.assertEqual(files["A"], base, "arm A is today's workflow unchanged")

    def test_derive_leaves_its_input_alone(self):
        base = E._load(E.DEFAULT_WORKFLOW)
        before = copy.deepcopy(base)
        E.derive_arms(base)
        self.assertEqual(base, before)

    def test_every_arm_holds(self):
        for arm, wf in arms().items():
            self.assertEqual(E.check_graph(wf, arm), [], arm)

    def test_b_turns_the_enhancer_on_and_c_only_changes_the_size(self):
        a, b, c = (arms()[x] for x in E.ARMS)
        self.assertEqual(set(b) - set(a), {"398:380", "398:393"})
        self.assertEqual([n for n in a if a[n] != b[n]], ["398:383", "398:382"])
        self.assertEqual([n for n in b if b[n] != c[n]], ["398:372", "398:360"])
        self.assertEqual(b["398:382"]["inputs"]["on_true"], ["398:380", 0])
        self.assertEqual((c["398:372"]["inputs"]["value"], c["398:360"]["inputs"]["value"]), (1280, 720))

    def test_a_dangling_link_is_named(self):
        b = arms()["B"]
        b["398:380"]["inputs"]["clip"] = ["398:999", 0]
        self.assertIn("398:380.clip links to node 398:999, which is not in the graph",
                      " ".join(E.check_graph(b, "B")))

    def test_the_phase_0_miswire_is_caught(self):
        b = arms()["B"]
        b["398:382"]["inputs"]["on_true"] = ["398:393", 0]
        self.assertIn("398:382.on_true comes from CLIPLoader, not from a TextGenerateLTX2Prompt",
                      " ".join(E.check_graph(b, "B")))

    def test_the_flag_and_the_size_belong_to_the_arm(self):
        a, c = arms()["A"], arms()["C"]
        a["398:383"]["inputs"]["value"] = True
        self.assertIn("Enable Prompt Enhance (398:383) is True", " ".join(E.check_graph(a, "A")))
        c["398:372"]["inputs"]["value"] = ["403", 0]
        self.assertIn("Width/Height", " ".join(E.check_graph(c, "C")))

    def test_a_missing_tool_node_is_named(self):
        a = arms()["A"]
        del a["403"]
        self.assertIn("node 403, which crow_core.video_workflow sets, is missing",
                      " ".join(E.check_graph(a, "A")))

    def test_the_tool_keeps_each_arm_and_c_ignores_the_selector(self):
        files = arms()
        self.assertEqual(E.check_calls(files), [])
        sent = E.crow_core.video_workflow(files["C"], "x.png", "m", 5, "1080p", 7, False)
        self.assertEqual(sent["403"]["inputs"]["megapixels"], 2.0)
        self.assertFalse(any(v in (["403", 0], ["403", 1])
                             for n in sent.values() for v in n["inputs"].values()))


class TheSourceTests(unittest.TestCase):
    def test_the_inputs_are_the_nodes_own(self):
        self.assertEqual(E.check_textgen_source(TEXTGEN), [])
        self.assertIn("presence_penalty", E.textgen_inputs(TEXTGEN))

    def test_an_input_the_node_lacks_is_named(self):
        src = TEXTGEN.replace('io.Int.Input("max_length", default=512),\n', "")
        self.assertEqual(E.check_textgen_source(src),
                         ["nodes_textgen.py: TextGenerate has no input 'max_length'"])

    def test_a_node_that_no_longer_reuses_the_parent_is_named(self):
        src = TEXTGEN.replace("inputs=parent_schema.inputs", "inputs=[]")
        self.assertIn("no longer takes TextGenerate's inputs", " ".join(E.check_textgen_source(src)))

    def test_the_values_are_the_templates(self):
        self.assertEqual(E.check_template(template(), blueprint()), [])

    def test_a_value_off_the_template_is_named(self):
        values = ["", 600, "on", 0.7, 64, 0.95, 0.05, 1.05, 0, 0, False, True]
        self.assertIn("template: node 380 has", " ".join(E.check_template(template(values), None)))
        self.assertIn("template: node 393 has",
                      " ".join(E.check_template(template(loader=["x", "ltxv", "default"]), None)))

    def test_a_blueprint_in_another_order_is_named(self):
        names = list(E.WIDGET_ORDER)
        names[3], names[4] = names[4], names[3]
        self.assertIn("blueprint:", " ".join(E.check_template(template(), blueprint(names))))

    def test_against_the_installed_comfyui(self):
        comfy = os.path.join(E.crow_platform.install_dir(), "comfyui")
        src = os.path.join(comfy, "ComfyUI", "comfy_extras", "nodes_textgen.py")
        if not os.path.isfile(src):
            self.skipTest("no ComfyUI installed at %s" % comfy)
        checks = dict(E.selftest(comfy))
        found = {k: v for k, v in checks.items() if k.startswith("enhancer ")}
        self.assertTrue(found)
        self.assertEqual(found, {k: [] for k in found})


class ThePreregTests(unittest.TestCase):
    def setUp(self):
        with open(E.PREREG, encoding="utf-8") as fh:
            self.text = fh.read()

    def test_the_committed_prereg_names_everything_the_run_uses(self):
        self.assertEqual(E.check_prereg(self.text, arms()), [])

    def test_a_changed_text_seed_or_arm_is_caught(self):
        text = self.text.replace("brass key, hops", "brass key, jumps")
        self.assertEqual(E.check_prereg(text, arms()), ["PREREG: S1's motion is not in it"])
        changed = arms()
        changed["B"]["398:380"]["inputs"]["max_length"] = 512
        self.assertIn("arm B's sha256", " ".join(E.check_prereg(self.text, changed)))
        self.assertIn("S2's seed", " ".join(E.check_prereg(self.text.replace("497572401", "1"), arms())))

    def test_the_order_is_a_latin_square(self):
        self.assertEqual(len(E.ORDER), 9)
        for sid in E.STILLS:
            self.assertEqual(sorted(a for s, a in E.ORDER if s == sid), list(E.ARMS))
        for pos in range(3):
            self.assertEqual(sorted(E.ORDER[3 * k + pos][1] for k in range(3)), list(E.ARMS))


class FakeCore:
    """crow_core as tool_animate_image uses it: the request and the job are module
    attributes the tool looks up at call time."""

    STOPPED = "stopped by the user"

    def __init__(self, run, answer="ok"):
        self.VIDEO_WORKFLOW = "default.json"
        self.answer, self.run, self.calls, self.announced = answer, run, [], []

        def request(path, body=None, **kw):
            if path.startswith("/history/"):
                return json.dumps({"j1": {"outputs": {"398:381": {"text": ["an enhanced caption"]}}}}).encode()
            return b'{"prompt_id": "j1"}'

        self._video_request = request
        self._run_video_job = lambda wf, base: (b"mp4", "clip.mp4", 12.34, None)

    def tool_animate_image(self, image, motion, seconds, resolution, seed):
        self.calls.append({"workflow": self.VIDEO_WORKFLOW, "image": image, "motion": motion,
                           "seconds": seconds, "resolution": resolution, "seed": seed})
        if self.answer == "raise":
            raise RuntimeError("boom")
        self._video_request("/prompt", {"prompt": {"sent": self.VIDEO_WORKFLOW}})
        self._run_video_job({}, {})
        self._video_request("/history/j1")
        if self.answer != "ok":
            return "error: the clip ran out of GPU memory: Allocation on device"
        out = os.path.join(self.run, "videos", "x.mp4")
        self.announced.append({"path": out})
        return "saved videos/x.mp4 (%s) -- 1920x1088, 121 frames" % out

    def take_announced_videos(self):
        out, self.announced = self.announced, []
        return out


class FakeVram:
    def __init__(self, path):
        self.peak = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.peak = 31999
        return False


class InATempRun(unittest.TestCase):
    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="crow-346-")
        self.addCleanup(shutil.rmtree, self.run, True)
        for name, value in (("RUN", self.run), ("RESULTS", os.path.join(self.run, "results.jsonl")),
                            ("RATING", os.path.join(self.run, "rating")),
                            ("KEY", os.path.join(self.run, "rating-key.json")),
                            ("SEAL", os.path.join(self.run, "rating-key.sha256")),
                            ("ANSWERS", os.path.join(self.run, "rating-answers.json"))):
            patcher = mock.patch.object(E, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)


class AClipTests(InATempRun):
    def clip(self, core, sid="S2", arm="B"):
        return E.run_clip(core, 4, sid, arm, vram=FakeVram,
                          readback=lambda p: {"width": 1920, "height": 1088, "frames": 121})

    def test_the_tool_renders_the_arms_file_and_gets_its_own_back(self):
        core = FakeCore(self.run)
        row = self.clip(core)
        self.assertEqual(core.calls, [{"workflow": os.path.join(self.run, "arm-B.json"),
                                       "image": os.path.join(self.run, "inputs", "S2.png"),
                                       "motion": E.STILLS["S2"]["motion"], "seconds": 5,
                                       "resolution": "1080p", "seed": 497572401}])
        self.assertEqual(core.VIDEO_WORKFLOW, "default.json")
        self.assertEqual((row["status"], row["clip"], row["render_s"], row["caption"]),
                         ("ok", "S2-B", 12.3, "an enhanced caption"))
        self.assertEqual((row["output"], row["width"], row["frames"], row["peak_vram_mib"]),
                         ("videos/x.mp4", 1920, 121, 31999))
        sent = E._load(os.path.join(self.run, "workflow-api-S2-B.json"))
        self.assertEqual(row["sent_sha256"], E.json_sha256(sent))

    def test_a_raise_puts_everything_back(self):
        core = FakeCore(self.run, answer="raise")
        before = (core.VIDEO_WORKFLOW, core._video_request, core._run_video_job)
        with self.assertRaises(RuntimeError):
            self.clip(core)
        self.assertEqual((core.VIDEO_WORKFLOW, core._video_request, core._run_video_job), before)

    def test_a_failed_clip_is_a_row_without_a_file(self):
        row = self.clip(FakeCore(self.run, answer="oom"))
        self.assertEqual(row["status"], "error")
        self.assertNotIn("output", row)
        self.assertIn("out of GPU memory", row["result"])


def rows_for(run, statuses=None):
    """Nine result rows in ORDER, each ok clip with a file behind it."""
    os.makedirs(os.path.join(run, "videos"), exist_ok=True)
    os.makedirs(os.path.join(run, "inputs"), exist_ok=True)
    for sid in E.STILLS:
        with open(os.path.join(run, "inputs", sid + ".png"), "wb") as fh:
            fh.write(sid.encode())
    rows = []
    for i, (sid, arm) in enumerate(E.ORDER, 1):
        status = (statuses or {}).get((sid, arm), "ok")
        row = {"clip": "%s-%s" % (sid, arm), "still": sid, "arm": arm,
               "seed": E.STILLS[sid]["seed"], "status": status}
        if status == "ok":
            row["output"] = "videos/%s-%s.mp4" % (sid, arm)
            with open(os.path.join(run, row["output"]), "wb") as fh:
                fh.write(row["clip"].encode())
        rows.append(row)
    return rows


class TheBlindSheetTests(InATempRun):
    def test_the_key_is_sealed_and_the_sheet_names_no_arm(self):
        rows = rows_for(self.run)
        sealed = E.seal(rows, rng=random.Random(1), strip=shutil.copyfile)
        with open(E.KEY, "rb") as fh:
            raw = fh.read()
        self.assertEqual(sealed, hashlib.sha256(raw).hexdigest())
        with open(E.SEAL, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "%s  rating-key.json\n" % sealed)
        key = json.loads(raw)["clips"]
        self.assertEqual(sorted(k["clip"] for k in key.values()), sorted(r["clip"] for r in rows))
        for name, k in key.items():
            with open(os.path.join(E.RATING, name + ".mp4"), "rb") as fh:
                self.assertEqual(fh.read(), k["clip"].encode(), "the clip behind the name")
        with open(os.path.join(E.RATING, "index.html"), encoding="utf-8") as fh:
            sheet = fh.read()
        self.assertEqual(sheet.count('class="card"'), 9)
        for r in rows:
            self.assertNotIn(r["clip"], sheet)
            self.assertNotIn("arm-" + r["arm"], sheet)
        self.assertNotEqual([k["clip"] for k in key.values()], [r["clip"] for r in rows],
                            "shuffled, not in render order")

    def test_a_clip_that_did_not_render_is_not_on_the_sheet(self):
        rows = rows_for(self.run, {("S3", "C"): "error"})
        E.seal(rows, rng=random.Random(2), strip=shutil.copyfile)
        key = E._load(E.KEY)["clips"]
        self.assertEqual(len(key), 8)
        self.assertNotIn("S3-C", [k["clip"] for k in key.values()])


def answers_for(key, votes):
    """votes: {(still, arm): "yyn"} for (a) action, (b) identity, (c) camera."""
    yn = {"y": "yes", "n": "no"}
    return {name: dict(zip(("action", "identity", "camera"),
                           (yn[v] for v in votes.get((k["still"], k["arm"]), "nnn"))))
            for name, k in key["clips"].items()}


class TheRuleTests(InATempRun):
    def setUp(self):
        super().setUp()
        self.rows = rows_for(self.run)
        E.seal(self.rows, rng=random.Random(3), strip=shutil.copyfile)
        self.key = E._load(E.KEY)

    def rule(self, votes, rows=None):
        return E.decide(E.tally(self.key, answers_for(self.key, votes), rows or self.rows))

    def test_more_yes_on_a_and_b_without_losing_the_camera_wins(self):
        votes = {("S1", "A"): "nyy", ("S2", "A"): "yyy", ("S3", "A"): "yny",
                 ("S1", "B"): "yyy", ("S2", "B"): "yyy", ("S3", "B"): "yny",
                 ("S1", "C"): "yyn", ("S2", "C"): "yyy", ("S3", "C"): "yyy"}
        # ab: A 4, B 5, C 6; cam: A 3, B 3, C 2
        self.assertEqual(self.rule(votes), {"B": True, "C": False})

    def test_a_tie_is_no_win(self):
        votes = {("S1", "A"): "yyy", ("S1", "B"): "yyy", ("S1", "C"): "yny"}
        self.assertEqual(self.rule(votes), {"B": False, "C": False})

    def test_a_clip_that_did_not_render_counts_as_no(self):
        rows = rows_for(self.run, {("S1", "B"): "error"})
        votes = {("S1", "A"): "yyy", ("S1", "B"): "yyy", ("S2", "B"): "ynn"}
        t = E.tally(self.key, answers_for(self.key, votes), rows)
        self.assertEqual(t["B"]["failed"], 1)

    def test_an_unanswered_question_is_an_error(self):
        answers = answers_for(self.key, {})
        answers["clip-04"]["camera"] = None
        with self.assertRaises(ValueError):
            E.tally(self.key, answers, self.rows)

    def test_unblind_opens_only_a_key_that_matches_its_seal(self):
        with open(E.RESULTS, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in self.rows))
        with open(E.ANSWERS, "w", encoding="utf-8") as fh:
            json.dump(answers_for(self.key, {("S1", "B"): "yyy"}), fh)
        with mock.patch("builtins.print"):
            self.assertEqual(E.unblind(), 0)
        self.assertEqual(E._load(os.path.join(self.run, "tally.json"))["wins"], {"B": True, "C": False})
        with open(E.KEY, "ab") as fh:
            fh.write(b" ")
        with mock.patch("builtins.print") as said:
            self.assertEqual(E.unblind(), 1)
        self.assertIn("does not match its seal", said.call_args[0][0])


class ThePreflightTests(InATempRun):
    def core(self, comfy):
        core = FakeCore(self.run)
        core._media_servers = lambda: ({"point": "media-stack"}, {"video": {"cwd": comfy}})
        return core

    def comfy(self):
        comfy = os.path.join(self.run, "comfyui")
        models = os.path.join(self.run, "models", "ltx-2.5")
        os.makedirs(os.path.join(comfy, "ComfyUI"))
        os.makedirs(os.path.join(models, "text_encoders"))
        with open(os.path.join(comfy, "ComfyUI", "extra_model_paths.yaml"), "w", encoding="utf-8") as fh:
            fh.write("crow:\n    base_path: '%s'\n    text_encoders: text_encoders\n    vae: vae\n" % models)
        return comfy, os.path.join(models, "text_encoders")

    def test_no_media_stack_no_start(self):
        core = FakeCore(self.run)
        core._media_servers = lambda: ({"point": "flash-next"}, None)
        with mock.patch.object(E.shutil, "which", return_value="x"):
            self.assertEqual(E.preflight(core), ["no Media Stack running: boot the point media-stack "
                                                 "from Crow's start window first (the running point "
                                                 "is flash-next)"])

    def test_a_missing_encoder_names_its_source_and_its_folder(self):
        comfy, encoders = self.comfy()
        self.assertEqual(E.text_encoder_dirs(comfy)[0], encoders)
        with mock.patch.object(E.shutil, "which", return_value="x"):
            bad = E.preflight(self.core(comfy))
        self.assertEqual(len(bad), 1)
        self.assertIn(E.E2B_URL, bad[0])
        self.assertIn(encoders, bad[0])

    def test_a_short_file_and_an_earlier_run_refuse(self):
        comfy, encoders = self.comfy()
        with open(os.path.join(encoders, E.E2B), "wb") as fh:
            fh.write(b"partial")
        with open(E.RESULTS, "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        with mock.patch.object(E.shutil, "which", return_value=None):
            bad = E.preflight(self.core(comfy))
        self.assertIn("has 7 bytes, not 5199997904", bad[0])
        self.assertEqual(sum("is not on PATH" in b for b in bad), 3)
        self.assertIn("the series runs once", bad[-1])


class TheSmallPartsTests(unittest.TestCase):
    def test_the_caption_comes_from_preview_as_text(self):
        raw = json.dumps({"j": {"outputs": {"75": {}, "398:381": {"text": ["cap"]}}}}).encode()
        self.assertEqual(E.caption(raw), "cap")
        self.assertIsNone(E.caption(b"not json"))
        self.assertIsNone(E.caption(None))

    def test_the_vram_peak_skips_what_is_not_a_number(self):
        self.assertEqual(E.peak_mib("1726\n\n31967\n[N/A]\n31000\n"), 31967)
        self.assertIsNone(E.peak_mib(""))

    def test_the_canonical_hash_ignores_layout(self):
        self.assertEqual(E.json_sha256(json.loads('{"b": 1, "a": [1, 2]}')),
                         E.json_sha256(json.loads('{\r\n "a": [1,2],\r\n "b": 1\r\n}')))


if __name__ == "__main__":
    unittest.main()
