"""measure_negative_cfg.py (#339) without a GPU: the plan, the bodies, the blind sheet, the verdict.

The image server is StubSdServer (three routes on 127.0.0.1, port 0) and crow_core
is pointed at it only inside measure_negative_cfg.rehearse; no case starts a real
sd-server or reads a model.

Usage:  python tools/test_measure_negative_cfg.py      (unittest; exit 0 = green)
"""

import contextlib
import copy
import io
import json
import os
import random
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import measure_negative_cfg as M  # noqa: E402

# The ticket's pass criteria, copied from #339 *Expected result* (2026-10-06). The
# PREREG must carry them verbatim; a reworded threshold is a changed threshold.
TICKET_PASS_LINES = (
    "1. object absent in at least 8 of 10 pairs;",
    "2. 0 of 10 with frame-wide grain or clear degradation against the 1.0 arm;",
    "3. warm time at most 2.2× the 1.0 arm at the same size (today 155.2 s warm on "
    "Linux; the Windows 1.0 baseline is measured in the same run);",
    "4. 0 OOM lines, card peak below the card's capacity beside the 27B.",
    "The lowest passing value becomes `IMAGE_NEGATIVE_CFG`. No value passing means "
    "close as A.",
)


def slurp(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def ids(k):
    return [p.id for p in M.PAIRS[:k]]


class PlanTests(unittest.TestCase):
    def test_every_round_size_gives_every_pair_every_arm_once_and_alternates(self):
        for k in range(1, len(M.PAIRS) + 1):
            with self.subTest(pairs=k):
                jobs = M.plan(ids(k))
                bad, _ = M.validate_plan(jobs, ids(k), check_tool=False)
                self.assertEqual(bad, [])
                cfgs = [j["cfg"] for j in jobs]
                self.assertTrue(all(a != b for a, b in zip(cfgs, cfgs[1:])), cfgs)

    def test_two_pairs_would_repeat_an_arm_at_the_pass_boundary_without_the_shift(self):
        # (k - 1) % 3 == 1 is the case the shift exists for: k = 2, 5, 8, 11, 14.
        for k in (2, 5, 8, 11, 14):
            plain = [(pid, M.ARMS[(i + r) % 3]) for r in range(3)
                     for i, pid in enumerate(ids(k))]
            self.assertTrue(any(a[1] == b[1] for a, b in zip(plain, plain[1:])), k)
            got = M.schedule(ids(k))
            self.assertFalse(any(a[1] == b[1] for a, b in zip(got, got[1:])), k)

    def test_the_primary_round_keeps_a_pair_out_of_the_conditioning_cache(self):
        seqs = {}
        for j in M.plan(M.PRIMARY):
            seqs.setdefault(j["pair"], []).append(j["seq"])
        gaps = [b - a for s in seqs.values() for a, b in zip(s, s[1:])]
        self.assertGreater(min(gaps), M.CACHE_CAPACITY)

    def test_a_primary_round_inside_cache_reach_is_refused(self):
        tight = [(pid, cfg) for pid in M.PRIMARY for cfg in M.ARMS]   # pair by pair
        jobs = [{"seq": n, "pair": pid, "cfg": cfg, "body": M.arm_body(M.PAIR_BY_ID[pid], cfg)}
                for n, (pid, cfg) in enumerate(tight, 1)]
        bad, _ = M.validate_plan(jobs, M.PRIMARY, check_tool=False)
        self.assertTrue(any("conditioning cache" in b for b in bad), bad)

    def test_one_job_per_pair_and_arm_thirty_in_the_primary_round(self):
        jobs = M.plan(M.PRIMARY)
        self.assertEqual(len(jobs), 30)
        self.assertEqual(len({(j["pair"], j["cfg"]) for j in jobs}), 30)
        self.assertEqual(len({j["image"] for j in jobs}), 30)


class BodyTests(unittest.TestCase):
    def test_the_1_0_arm_is_the_body_generate_image_sends_today(self):
        for pair in M.PAIRS:
            with self.subTest(pair=pair.id):
                self.assertEqual(M.arm_body(pair, M.BASELINE), M.tool_body(pair))

    def test_the_1_0_arm_is_the_ticket_size_steps_and_sampler_without_a_negative(self):
        body = M.arm_body(M.PAIR_BY_ID["P01"], M.BASELINE)
        self.assertEqual((body["width"], body["height"]), (2752, 1536))
        self.assertEqual(body["sample_params"], {"sample_steps": 40, "sample_method": "euler",
                                                 "guidance": {"txt_cfg": 1.0}})
        self.assertNotIn("negative_prompt", body)
        self.assertEqual((body["prompt"], body["seed"]), ("a quiet harbour at dawn", 7))

    def test_a_guided_arm_adds_only_the_negative_prompt_and_its_txt_cfg(self):
        for pair in M.PAIRS:
            for cfg in M.GUIDED:
                body = M.arm_body(pair, cfg)
                self.assertEqual(body["negative_prompt"], pair.exclude)
                self.assertEqual(body["sample_params"]["guidance"], {"txt_cfg": cfg})
                rest = copy.deepcopy(body)
                del rest["negative_prompt"]
                rest["sample_params"]["guidance"]["txt_cfg"] = 1.0
                self.assertEqual(rest, M.arm_body(pair, M.BASELINE))

    def test_validation_catches_a_baseline_that_drifted_from_the_tool(self):
        jobs = M.plan(["P01"])
        for j in jobs:
            if j["cfg"] == M.BASELINE:
                j["body"]["sample_params"]["sample_steps"] = 30
        bad, _ = M.validate_plan(jobs, ["P01"])
        self.assertTrue(any("not the body tool_generate_image sends" in b for b in bad), bad)

    def test_validation_catches_a_negative_prompt_on_the_baseline(self):
        jobs = M.plan(["P01"])
        for j in jobs:
            if j["cfg"] == M.BASELINE:
                j["body"]["negative_prompt"] = "boats"
        bad, _ = M.validate_plan(jobs, ["P01"], check_tool=False)
        self.assertTrue(any("carries a negative_prompt" in b for b in bad), bad)

    def test_no_prompt_names_its_excluded_object_and_seeds_are_distinct(self):
        for pair in M.PAIRS:
            self.assertNotIn(pair.exclude.lower(), pair.prompt.lower(), pair.id)
        self.assertEqual(len({p.seed for p in M.PAIRS}), len(M.PAIRS))
        self.assertEqual(len({p.exclude for p in M.PAIRS}), len(M.PAIRS))
        self.assertNotIn(M.WARMUP_NEGATIVE, {p.exclude for p in M.PAIRS})

    def test_the_first_warm_up_is_crow_cores_own(self):
        src = slurp(os.path.join(M.REPO, "cli", "crow_core.py"))
        warm = src[src.index("def image_server_warm"):src.index("class SdProgress")]
        self.assertIn('"prompt": "a plain grey square", "width": 256, "height": 256', warm)
        self.assertIn('"sample_steps": 1, "sample_method": "euler"', warm)
        plain, guided = M.warmup_bodies()
        self.assertEqual((plain["prompt"], plain["width"], plain["seed"]),
                         ("a plain grey square", 256, 1))
        self.assertEqual(guided["negative_prompt"], M.WARMUP_NEGATIVE)


class PreregTests(unittest.TestCase):
    def setUp(self):
        with open(M.PREREG, encoding="utf-8") as fh:
            self.text = fh.read()

    def test_the_prereg_table_is_the_scripts_pairs(self):
        rows = re.findall(r"^\| (P\d\d|R\d\d) \| (\d+) \| (.+?) \| (.+?) \|$", self.text, re.M)
        self.assertEqual([(r[0], int(r[1]), r[2], r[3]) for r in rows],
                         [(p.id, p.seed, p.prompt, p.exclude) for p in M.PAIRS])

    def test_the_prereg_copies_the_tickets_criteria_verbatim(self):
        for line in TICKET_PASS_LINES:
            self.assertIn(line, self.text)

    def test_the_prereg_lists_the_primary_order_the_script_runs(self):
        listed = re.findall(r"^\| (\d+) \| (P\d\d) \| (\d)(?:\.0)? \|$", self.text, re.M)
        self.assertEqual([(int(s), p, float(c)) for s, p, c in listed],
                         [(j["seq"], j["pair"], j["cfg"]) for j in M.plan(M.PRIMARY)])


class PngTests(unittest.TestCase):
    def test_text_chunks_go_and_the_picture_stays(self):
        png = M.tiny_png("Negative prompt: boats, CFG scale: 6")
        out = M.strip_png_text(png)
        self.assertNotIn(b"tEXt", out)
        self.assertNotIn(b"CFG", out)
        self.assertEqual(out, M.tiny_png(""))

    def test_a_file_that_is_not_a_png_is_refused(self):
        with self.assertRaises(ValueError):
            M.strip_png_text(b"GIF89a....")
        with self.assertRaises(ValueError):
            M.strip_png_text(M.tiny_png("x")[:-6])


class LogTests(unittest.TestCase):
    def test_server_time_cache_hits_and_out_of_memory_lines(self):
        lines = [
            "[INFO   ] image.cpp:900 - generate_image 2752x1536",
            "[INFO   ] conditioning_cache.h:91 - conditioning cache hit",
            "[VERBOSE] ggml - ggml_cuda_host_malloc: failed to allocate 416.00 MiB of "
            "pinned memory: resource already mapped",
            "[ERROR  ] ggml - ggml_backend_cuda_buffer_type_alloc_buffer: allocating "
            "416.00 MiB on device 0: cudaMalloc failed: out of memory",
            "[VERBOSE] ggml - something failed to allocate quietly",
            "[INFO   ] image.cpp:1045 - generate_image completed in 361.25s",
        ]
        got = M.log_facts(lines)
        self.assertEqual(got["server_s"], 361.25)
        self.assertEqual(got["cache_hits"], 1)
        self.assertEqual(len(got["oom"]), 1)
        self.assertIn("cudaMalloc failed", got["oom"][0])
        self.assertEqual(len(got["pinned"]), 1)

    def test_a_clean_job_has_no_out_of_memory_line(self):
        got = M.log_facts(["[INFO   ] image.cpp:1045 - generate_image completed in 218.1s"])
        self.assertEqual((got["oom"], got["pinned"], got["cache_hits"]), ([], [], 0))


def good_facts():
    argv = ["C:/Crow/bin/sd-server.exe", "--diffusion-model", "C:/m/t.json", "--llm",
            "C:/m/e.json", "--vae", "C:/m/v.safetensors", "--backend", "te=cpu",
            "--diffusion-fa", "--max-vram", "7", "--vae-tiling", "--model-args",
            "qwen_image_2_1_prefix_cache_type=q8_0", "--listen-port", "8097", "-v", "--mmap"]
    line = ('"C:\\Crow\\bin\\sd-server.exe" --diffusion-model C:\\m\\t.json --llm C:\\m\\e.json '
            "--vae C:\\m\\v.safetensors --backend te=cpu --diffusion-fa --max-vram 7 "
            "--vae-tiling --model-args qwen_image_2_1_prefix_cache_type=q8_0 "
            "--listen-port 8097 -v --mmap")
    return {"active_point": {"point": "image-stack", "mode": None, "base_url":
                             "http://127.0.0.1:8099/v1"},
            "servers": [{"pid": "1", "kind": "crow-nest",
                         "line": "C:\\Crow\\bin\\serve.exe --port 8099"},
                        {"pid": "2", "kind": "image", "line": line}],
            "llm_model_path": "C:\\Crow\\models\\Qwen3.8-27B-CNQ4.5\\Qwen3.8-27B-CNQ4.5.cnq",
            "llm_health": {"status": "ok"}, "sd_expected_argv": argv,
            "sd_log": "C:\\Crow\\runs\\sd-server-8097.log", "sd_log_exists": True,
            "gpu": {"name": "RTX 5090", "total_mib": 32607, "used_mib": 31000},
            "prereg_sha256": "x" * 64, "git_dirty": False}


class PreflightTests(unittest.TestCase):
    def test_the_image_stack_as_crow_boot_starts_it_passes(self):
        self.assertEqual(M.check_preflight(good_facts()), [])

    def test_each_wrong_state_is_named(self):
        cases = {
            "operating point": lambda f: f["active_point"].update(point="27b"),
            "video mode": lambda f: f["active_point"].update(mode="video"),
            "crow-nest serve": lambda f: f["servers"].append(
                {"pid": "3", "kind": "llama-server", "line": "llama-server --port 8083"}),
            "ComfyUI": lambda f: f["servers"].append({"pid": "4", "kind": "video", "line": "x"}),
            "not the 27B": lambda f: f.update(llm_model_path="C:\\m\\Flash-Next.cnq"),
            "/health": lambda f: f.update(llm_health={"error": "refused"}),
            "nvidia-smi": lambda f: f.update(gpu=None),
            "missing": lambda f: f.update(prereg_sha256=None),
            "modified": lambda f: f.update(git_dirty=True),
            "--sd-log": lambda f: f.update(sd_log_exists=False),
        }
        for needle, breaks in cases.items():
            with self.subTest(needle=needle):
                facts = good_facts()
                breaks(facts)
                bad = M.check_preflight(facts)
                self.assertTrue(any(needle in b for b in bad), bad)

    def test_an_sd_server_with_another_argv_is_refused(self):
        for old, new, needle in (("--max-vram 7", "--max-vram 9", "--max-vram 7"),
                                 (" --mmap", "", "missing ['--mmap']"),
                                 (" -v", " -v --conditioning-cache-size 0",
                                  "extra ['--conditioning-cache-size']")):
            with self.subTest(change=new):
                facts = good_facts()
                facts["servers"][1]["line"] = facts["servers"][1]["line"].replace(old, new)
                bad = M.check_preflight(facts)
                self.assertTrue(any(needle in b for b in bad), bad)


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_the_server_gets_the_warm_ups_then_exactly_the_planned_bodies(self):
        status, out, stub = M.rehearse(self.tmp.name)
        self.assertEqual(status, "complete")
        self.assertEqual(stub.bodies,
                         M.warmup_bodies() + [j["body"] for j in M.plan(M.PRIMARY)])
        rows = M.read_rows(out)
        self.assertEqual([r["kind"] for r in rows], ["warmup"] * 2 + ["job"] * 30)
        for r in rows[2:]:
            self.assertEqual(r["status"], "ok")
            self.assertEqual(r["server_s"], 0.01)
            self.assertEqual(r["peak_mib"], 30000)
            self.assertTrue(os.path.isfile(os.path.join(out, r["image"])))

    def test_the_sheet_hides_the_arm_and_the_key_is_sealed_once(self):
        _status, out, _stub = M.rehearse(self.tmp.name)
        digest = M.seal(out)
        sheet = os.path.join(out, M.SHEET)
        pngs = sorted(n for n in os.listdir(sheet) if n.endswith(".png"))
        self.assertEqual(len(pngs), 30)
        self.assertTrue(all(re.match(r"^S\d\d-[ABC]\.png$", n) for n in pngs), pngs)
        for name in pngs:
            with open(os.path.join(sheet, name), "rb") as fh:
                data = fh.read()
            self.assertNotIn(b"tEXt", data)
            self.assertNotIn(b"CFG", data)
        form = M.read_json(os.path.join(sheet, "answers.json"))
        self.assertEqual(sorted(k for k in form if not k.startswith("_")),
                         ["S%02d" % n for n in range(1, 11)])
        self.assertNotIn("cfg", json.dumps(form).lower().replace("txt_cfg", ""))
        page = slurp(os.path.join(sheet, "index.html"))
        self.assertNotIn("cfg", page.lower())
        with open(os.path.join(out, M.KEY_NAME), "rb") as fh:
            self.assertEqual(M.sha256_bytes(fh.read()), digest)
        self.assertIn(digest, slurp(os.path.join(out, M.KEY_SHA_NAME)))
        with self.assertRaises(RuntimeError):
            M.seal(out)

    def test_the_shuffle_varies_between_seals(self):
        orders = set()
        for seed in range(4):
            tmp = os.path.join(self.tmp.name, str(seed))
            os.makedirs(tmp)
            _s, out, _stub = M.rehearse(tmp)
            M.seal(out, rng=random.Random(seed))
            key = M.read_json(os.path.join(out, M.KEY_NAME))
            orders.add(tuple((s, e["pair"], e["A"]["cfg"]) for s, e in sorted(key["slots"].items())))
        self.assertGreater(len(orders), 1)

    def test_scoring_checks_the_seal_and_wants_every_answer(self):
        _s, out, _stub = M.rehearse(self.tmp.name)
        digest = M.seal(out)
        with self.assertRaises(RuntimeError):          # nothing answered yet
            M.load_round(out)
        M.answer_all(out, absent={(p, c) for p in M.PRIMARY for c in M.GUIDED})
        self.assertEqual(M.evaluate([M.load_round(out, digest)])["image_negative_cfg"], 3.0)
        with self.assertRaises(RuntimeError):
            M.load_round(out, "0" * 64)                # not the published sha256
        key = os.path.join(out, M.KEY_NAME)
        with open(key, "rb") as fh:
            raw = fh.read()
        with open(key, "wb") as fh:
            fh.write(raw.replace(b'"cfg": 3.0', b'"cfg": 9.0', 1))
        with self.assertRaises(RuntimeError):
            M.load_round(out)

    def test_three_failed_jobs_in_a_row_stop_the_series_and_are_recorded(self):
        status, out, _stub = M.rehearse(self.tmp.name, fail={5, 6, 7})   # POST 5 = job 3
        self.assertEqual(status, "stopped")
        jobs = [r for r in M.read_rows(out) if r["kind"] == "job"]
        self.assertEqual([r["status"] for r in jobs], ["ok", "ok", "error", "error", "error"])
        self.assertEqual([len(r["oom_lines"]) for r in jobs], [0, 0, 1, 1, 1])
        self.assertIsNone(jobs[2]["image"])

    def test_resume_runs_only_what_has_no_row(self):
        calls = {"n": 0}
        real = M.core._run_image_job

        def stop_after_six(body, base, refine=False):
            calls["n"] += 1
            if calls["n"] > 8:                          # 2 warm-ups + 6 jobs
                raise KeyboardInterrupt
            return real(body, base)

        with self.assertRaises(KeyboardInterrupt):
            M.rehearse(self.tmp.name, submit=stop_after_six)
        status, out, stub = M.rehearse(self.tmp.name, resume=True)
        self.assertEqual(status, "complete")
        self.assertEqual(stub.bodies, M.warmup_bodies()
                         + [j["body"] for j in M.plan(M.PRIMARY)][6:])
        jobs = [r for r in M.read_rows(out) if r["kind"] == "job"]
        self.assertEqual(sorted((r["pair"], r["cfg"]) for r in jobs),
                         sorted((j["pair"], j["cfg"]) for j in M.plan(M.PRIMARY)))

    def test_a_second_run_into_the_same_round_needs_resume(self):
        M.rehearse(self.tmp.name)
        with self.assertRaises(RuntimeError):
            M.rehearse(self.tmp.name)

    def test_a_log_that_is_not_the_servers_stops_the_run_after_the_warm_ups(self):
        other = os.path.join(self.tmp.name, "other.log")
        with open(other, "w", encoding="utf-8"):
            pass
        status, out, stub = M.rehearse(self.tmp.name, sd_log=other)
        self.assertEqual(status, "stopped")
        self.assertEqual(len(stub.bodies), 2)


def record(pair, cfg, visible=True, degraded=False, wall=200.0, peak=31000, oom=0,
           status="ok", has_image=True):
    return {"pair": pair, "cfg": cfg, "has_image": has_image, "object_visible": visible,
            "degraded": degraded, "status": status, "wall_s": wall, "peak_mib": peak,
            "oom": oom, "cache_hits": 0}


def round_of(pairs, tweak=None, capacity=32607, name="round-1"):
    recs = {}
    for pid in pairs:
        recs[(pid, 1.0)] = record(pid, 1.0, visible=True, wall=200.0)
        recs[(pid, 3.0)] = record(pid, 3.0, visible=False, wall=330.0)
        recs[(pid, 6.0)] = record(pid, 6.0, visible=False, wall=340.0)
    for (pid, cfg), change in (tweak or {}).items():
        recs[(pid, cfg)].update(change)
    return {"dir": name, "pairs": list(pairs), "records": recs, "capacity_mib": capacity,
            "sha256": "s"}


class EvaluateTests(unittest.TestCase):
    def test_both_pass_and_the_lowest_value_is_chosen(self):
        got = M.evaluate([round_of(M.PRIMARY)])
        self.assertTrue(got["arms"]["3"]["pass"] and got["arms"]["6"]["pass"])
        self.assertEqual(got["image_negative_cfg"], 3.0)
        self.assertEqual(got["arms"]["3"]["time_ratio"], 1.65)

    def test_eight_absent_passes_seven_fails(self):
        seen = {("P0%d" % n, 3.0): {"object_visible": True} for n in (1, 2)}
        self.assertTrue(M.evaluate([round_of(M.PRIMARY, seen)])["arms"]["3"]["c1_absent"])
        seen[("P03", 3.0)] = {"object_visible": True}
        got = M.evaluate([round_of(M.PRIMARY, seen)])
        self.assertFalse(got["arms"]["3"]["c1_absent"])
        self.assertEqual(got["image_negative_cfg"], 6.0)

    def test_one_degraded_picture_or_a_missing_one_fails_criterion_2(self):
        for change in ({"degraded": True}, {"has_image": False, "status": "error",
                                            "object_visible": None}):
            got = M.evaluate([round_of(M.PRIMARY, {("P05", 6.0): change})])
            self.assertFalse(got["arms"]["6"]["c2_no_degradation"], change)
            self.assertEqual(got["image_negative_cfg"], 3.0)

    def test_the_time_ratio_is_inclusive_at_2_2(self):
        at = {(p, 6.0): {"wall_s": 440.0} for p in M.PRIMARY}
        self.assertTrue(M.evaluate([round_of(M.PRIMARY, at)])["arms"]["6"]["c3_time"])
        over = {(p, 6.0): {"wall_s": 442.0} for p in M.PRIMARY}
        self.assertFalse(M.evaluate([round_of(M.PRIMARY, over)])["arms"]["6"]["c3_time"])

    def test_an_oom_line_or_a_peak_at_capacity_fails_criterion_4(self):
        for change in ({"oom": 1}, {"peak_mib": 32607}, {"peak_mib": None}):
            got = M.evaluate([round_of(M.PRIMARY, {("P09", 3.0): change})])
            self.assertFalse(got["arms"]["3"]["c4_memory"], change)

    def test_no_value_passing_closes_as_option_a(self):
        slow = {(p, c): {"wall_s": 500.0} for p in M.PRIMARY for c in M.GUIDED}
        got = M.evaluate([round_of(M.PRIMARY, slow)])
        self.assertIsNone(got["image_negative_cfg"])
        self.assertIn("option A", got["verdict"])

    def test_a_pair_without_its_object_at_1_0_is_replaced_by_the_next_reserves(self):
        tweak = {("P02", 1.0): {"object_visible": False}, ("P07", 1.0): {"object_visible": False}}
        got = M.evaluate([round_of(M.PRIMARY, tweak)])
        self.assertFalse(got["complete"])
        self.assertEqual(got["invalid_pairs"], ["P02", "P07"])
        self.assertEqual(got["next_reserves"], ["R01", "R02"])
        self.assertIsNone(got["image_negative_cfg"])
        both = M.evaluate([round_of(M.PRIMARY, tweak), round_of(["R01", "R02"], name="round-2")])
        self.assertTrue(both["complete"])
        self.assertEqual(both["counted_pairs"], [p for p in M.PRIMARY if p not in ("P02", "P07")]
                         + ["R01", "R02"])
        self.assertEqual(both["timing_round"], "round-1")
        self.assertEqual(both["image_negative_cfg"], 3.0)

    def test_running_out_of_reserves_asks_for_an_addendum(self):
        tweak = {(p, 1.0): {"object_visible": False} for p in M.PRIMARY[:6]}
        got = M.evaluate([round_of(M.PRIMARY, tweak)])
        self.assertIn("addendum", got["verdict"])

    def test_a_pair_in_two_rounds_is_refused(self):
        with self.assertRaises(RuntimeError):
            M.evaluate([round_of(M.PRIMARY), round_of(["P01"], name="round-2")])

    def test_without_the_primary_round_no_time_and_no_pass(self):
        got = M.evaluate([round_of(list(M.PRIMARY[:5]) + list(M.RESERVES))])
        self.assertIsNone(got["arms"]["3"]["time_ratio"])
        self.assertIsNone(got["image_negative_cfg"])


class CliTests(unittest.TestCase):
    def test_dry_run_is_valid_and_touches_no_server(self):
        with mock.patch.object(M.core, "_run_image_job",
                               side_effect=AssertionError("a request was sent")), \
                contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertEqual(M.main(["--dry-run"]), 0)
        self.assertIn("plan: valid", said.getvalue())

    def test_round_one_is_always_the_primary_ten(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(M.main(["run", "--pairs", "P01,P02"]), 2)


if __name__ == "__main__":
    unittest.main()
