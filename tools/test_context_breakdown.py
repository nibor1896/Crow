"""context_breakdown.py (#359) without a tokenizer, a template or a model.

Every count here runs on an injected counter (whitespace words), so the suite
needs neither `tokenizers` nor a crow-nest checkout; the replay runs
crow_core's own batch, as the tool does. The one case that renders a template
uses a five-line template written to a temp dir and skips where jinja2 is not
installed.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import context_breakdown as B  # noqa: E402

try:
    import jinja2  # noqa: F401
except ImportError:
    jinja2 = None


def words(text):
    """The injected counter: one token per whitespace-separated word."""
    return text.split()


def body(tag, n):
    """`n` words of one kind, so a body's count is known exactly."""
    return " ".join([tag] * n)


def session(rounds=8, size=300, result_size=0):
    """system, user, then `rounds` write rounds: write_file, edit_file and
    append_file in turn, every body `size` words, each result 3 words plus
    `result_size` more."""
    messages = [{"role": "system", "content": body("sys", 10)},
                {"role": "user", "content": body("ask", 4)}]
    for r in range(rounds):
        kind = ("write_file", "edit_file", "append_file")[r % 3]
        if kind == "edit_file":
            args = {"path": "f%d.js" % r, "old": body("old", size), "new": body("new", size)}
        else:
            args = {"path": "f%d.js" % r, "content": body("con", size)}
        messages.append({"role": "assistant", "content": "doing %d" % r,
                         "reasoning_content": body("think", 5),
                         "tool_calls": [{"id": "c0", "type": "function",
                                         "function": {"name": kind,
                                                      "arguments": json.dumps(args)}}]})
        messages.append({"role": "tool", "tool_call_id": "c0",
                         "content": "wrote f%d.js ok " % r + body("res", result_size)})
    return messages


class TheTokenizerFollowsTheRecordedModelTests(unittest.TestCase):

    def test_glm_and_qwen_by_name_and_nothing_for_an_empty_model(self):
        with mock.patch.dict(os.environ, {"CROW_NEST": os.path.join("x", "nest")}):
            glm = B.default_tokenizer("GLM-5.3-Flash-MUL1K3.cnq")
            qwen = B.default_tokenizer("Qwen3.8-Flash-Next-CNQ4.5-M.cnq")
            self.assertEqual(glm, os.path.join("x", "nest", "models", "GLM-5.3-Flash-original",
                                               "tokenizer.json"))
            self.assertEqual(qwen, os.path.join("x", "nest", "models",
                                                "Qwen3.8-Flash-Next-original", "tokenizer.json"))
            for unknown in ("", None, "crow"):
                self.assertIsNone(B.default_tokenizer(unknown), unknown)


class TheBreakdownTests(unittest.TestCase):

    def test_the_cut_is_the_rule_of_clearable_results(self):
        messages = session(8)
        # assistant messages at 2, 4, ..., 16; the last five start at 8
        self.assertEqual(B.keep_cut(messages, 5), 8)
        self.assertEqual(B.keep_cut(messages, 0), 16, "keep 0 is read as 1")
        self.assertEqual(B.keep_cut(session(5), 5), 0, "nothing behind five rounds")

    def test_raw_categories_add_up_to_the_total(self):
        messages = session(8, size=300, result_size=20)
        report = B.breakdown(messages, words, B.raw_render, keep=5)
        rows = {r["category"]: r for r in report["rows"]}
        self.assertEqual(rows["head"]["tokens"], 10)
        self.assertEqual(rows["user"]["tokens"], 4)
        self.assertEqual(rows["reasoning"]["tokens"], 8 * 5)
        self.assertEqual(rows["assistant text"]["tokens"], 8 * 2)
        # write_file rounds 0, 3, 6: a path word and 300 body words each
        self.assertEqual(rows["args write_file"]["tokens"], 3 * 301)
        self.assertEqual(rows["args edit_file"]["tokens"], 3 * 601)
        self.assertEqual(rows["args append_file"]["tokens"], 2 * 301)
        # behind the cut (message 8): rounds 0, 1, 2
        self.assertEqual(rows["args write_file"]["behind"], 301)
        self.assertEqual(rows["args edit_file"]["behind"], 601)
        self.assertEqual(rows["args append_file"]["behind"], 301)
        self.assertEqual(rows["results edit_file"]["tokens"], 3 * 23)
        self.assertEqual(rows["results edit_file"]["behind"], 23)
        self.assertEqual(report["markup"], 0, "raw words leave no markup")
        self.assertEqual(sum(r["tokens"] for r in report["rows"]), report["total"])
        self.assertEqual(report["cut"], 8)


class TheReplayTests(unittest.TestCase):

    def test_one_batch_per_arm_and_the_bodies_on_top(self):
        messages = session(10, size=300, result_size=400)
        rep = B.replay(messages, words, B.raw_render, keep=5)
        only, both = rep["arms"]["results"], rep["arms"]["results+calls"]
        self.assertEqual((rep["cut"], rep["end"]), (12, len(messages)))
        self.assertEqual((only["results"], only["call_bodies"]), (5, 0))
        # rounds 0..4: write, edit (old, new), append, write, edit (old, new)
        self.assertEqual((both["results"], both["call_bodies"]), (5, 7))
        self.assertEqual(only["reprefill_events"], 1)
        self.assertEqual(both["reprefill_events"], 1)
        self.assertGreater(only["freed"], 0)
        self.assertGreater(both["freed"] - only["freed"], 6 * 250,
                           "seven 300-word bodies, each down to a stub")
        self.assertEqual(rep["bodies_on_top"], both["freed"] - only["freed"])
        # the first write (message 2) changes before the first result (3)
        self.assertEqual(only["first_changed_message"], 3)
        self.assertEqual(both["first_changed_message"], 2)
        for arm in (only, both):
            self.assertTrue(0 < arm["reprefill_tokens"] <= arm["tokens_after"], arm)
        self.assertTrue(rep["render_stable"])

    def test_the_batch_at_an_earlier_message_sees_that_conversation(self):
        messages = session(12, size=300)
        rep = B.replay(messages, words, B.raw_render, at=6, keep=5)
        # the keep window starts at 6, so the batch fires before message 16
        self.assertEqual((rep["cut"], rep["end"]), (6, 16))
        # behind 6: round 0 (write_file) and round 1 (edit_file, old and new)
        self.assertEqual(rep["arms"]["results+calls"]["call_bodies"], 3)

    def test_a_cut_inside_the_keep_window_is_refused(self):
        messages = session(8)
        with self.assertRaises(ValueError):
            B.replay(messages, words, B.raw_render, at=12, keep=5)

    def test_the_stubs_name_the_real_originals_dir_and_are_counted(self):
        """The replay writes its originals to a temp dir, but counts the stubs
        as the live batch writes them: naming <SESSION_DIR>/cleared."""
        core = B.import_core()
        messages = session(10, size=300, result_size=400)
        rep = B.replay(messages, words, B.raw_render, keep=5)
        both = rep["arms"]["results+calls"]
        self.assertEqual(both["stub_tokens"]["n"], both["call_bodies"])
        self.assertGreater(both["stub_tokens"]["mean"], 0)
        self.assertLessEqual(both["stub_tokens"]["min"], both["stub_tokens"]["max"])
        real = os.path.join(core.SESSION_DIR, "cleared", B.STAMP + ".json")
        self.assertEqual(rep["originals_named"], B.shown(real))
        self.assertTrue(rep["render_stable"])


class TheWalkTests(unittest.TestCase):
    """--walk: the session's history under the live rule, round by round, so
    the batches are the ones crow_core would fire, not one forced batch."""

    def test_both_arms_fire_under_the_live_rule_and_say_where(self):
        messages = session(20, size=300, result_size=400)
        total = len(words(B.raw_render(messages)))
        rep = B.walk(messages, words, B.raw_render, keep=5, n_ctx=int(total / 0.8))
        for name in ("results", "results+calls"):
            arm = rep["arms"][name]
            self.assertGreaterEqual(arm["reprefill_events"], 1, name)
            self.assertEqual(arm["reprefill_events"], len(arm["batches"]))
            for b in arm["batches"]:
                self.assertGreaterEqual(b["context_tokens"], 0.65 * rep["n_ctx"], b)
                self.assertGreater(b["freed"], 0, b)
                self.assertGreater(b["reprefill_tokens"], 0, b)
        self.assertEqual(rep["arms"]["results"]["batches"][0]["call_bodies"], 0)
        self.assertGreater(rep["arms"]["results+calls"]["batches"][0]["call_bodies"], 0)
        self.assertEqual((rep["at"], rep["at_least"]), (0.65, 0.10))
        self.assertIn("events_equal", rep)

    def test_a_batch_only_the_bodies_pay_for_is_an_extra_event(self):
        """Short results never pass the at_least test alone; with the bodies
        in, the same history fires. The forced replay cannot show this."""
        messages = session(20, size=300, result_size=0)
        total = len(words(B.raw_render(messages)))
        rep = B.walk(messages, words, B.raw_render, keep=5, n_ctx=int(total / 0.8))
        self.assertEqual(rep["arms"]["results"]["reprefill_events"], 0)
        self.assertGreaterEqual(rep["arms"]["results+calls"]["reprefill_events"], 1)
        self.assertFalse(rep["events_equal"])

    def test_the_walk_stops_where_the_window_would_roll(self):
        messages = session(20, size=300, result_size=0)
        total = len(words(B.raw_render(messages)))
        rep = B.walk(messages, words, B.raw_render, keep=5, n_ctx=int(total / 2),
                     arms=(("results", False),))
        arm = rep["arms"]["results"]
        self.assertIsNotNone(arm["rolled_at"])
        self.assertLess(arm["rolled_at"], len(messages))


class TheCommandLineTests(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ctx-breakdown-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _run(self, *argv):
        path = os.path.join(self.dir, "s.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"model": "", "context_tokens": 123, "messages": session(10)}, fh)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = B.main([path, "--raw", *argv], encode=words)
        return code, out.getvalue()

    def test_home_is_hidden_whichever_separator_the_path_came_with(self):
        """A tokenizer passed as C:/Users/... is still under the profile."""
        with mock.patch.object(B, "HOME", self.dir):
            for path in (os.path.join(self.dir, "m", "t.json"),
                         self.dir.replace("\\", "/") + "/m/t.json"):
                self.assertEqual(B.shown(path), "<home>" + os.sep + os.path.join("m", "t.json"))

    def test_json_for_the_breakdown_and_the_replay(self):
        code, text = self._run("--json")
        self.assertEqual(code, 0)
        doc = json.loads(text)
        self.assertEqual(doc["mode"], "raw values")
        self.assertEqual(doc["recorded_context_tokens"], 123)
        self.assertIn("args write_file", [r["category"] for r in doc["breakdown"]["rows"]])
        code, text = self._run("--json", "--replay")
        self.assertEqual(code, 0)
        doc = json.loads(text)
        self.assertEqual(doc["replay"]["arms"]["results+calls"]["reprefill_events"], 1)

    def test_a_table_by_default_and_home_written_as_a_placeholder(self):
        with mock.patch.object(B, "HOME", self.dir):
            code, text = self._run()
        self.assertEqual(code, 0)
        self.assertIn("| category |", text)
        self.assertIn("<home>", text)
        self.assertNotIn(self.dir, text)

    def test_no_model_and_no_tokenizer_is_a_setup_error(self):
        path = os.path.join(self.dir, "s.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"model": "", "messages": session(2)}, fh)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(B.main([path]), 2)
        self.assertIn("--tokenizer", err.getvalue())


@unittest.skipIf(jinja2 is None, "jinja2 is not installed")
class TheTemplateRenderTests(unittest.TestCase):

    def test_arguments_reach_the_template_as_an_object(self):
        """crow-nest serve parses `arguments` before the render; so does this."""
        tmp = tempfile.mkdtemp(prefix="ctx-template-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "chat_template.jinja")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{% for m in messages %}{% for c in m.tool_calls or [] %}"
                     "{% for k, v in c.function.arguments.items() %}"
                     "<{{ k }}>{{ v if v is string else v | tojson }}"
                     "{% endfor %}{% endfor %}{% endfor %}")
        render = B.template_renderer(path)
        messages = [{"role": "assistant", "content": "", "tool_calls": [
            {"id": "c0", "function": {"name": "write_file",
                                      "arguments": '{"path": "a.js", "n": 2}'}},
            {"id": "c1", "function": {"name": "write_file", "arguments": '{"path": "b'}}]}]
        self.assertEqual(render(messages), '<path>a.js<n>2<_raw>{"path": "b')


if __name__ == "__main__":
    unittest.main()
