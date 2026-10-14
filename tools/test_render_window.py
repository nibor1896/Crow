"""render_window.py (#381): the page it builds, the fixture it replays, the browser run.

Everything up to BrowserTests needs no browser. BrowserTests renders the real
fixture through Chrome, Edge or Chromium (CROW_CHROME, or the usual places) and
is skipped where there is none.

Run from the repo root:  python -m unittest tools/test_render_window.py
"""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_window as R  # noqa: E402

sys.path.insert(0, str(R.REPO / "cli"))
import crow_core  # noqa: E402
import crow_gui   # noqa: E402

FIXTURE = HERE / "fixtures" / "goal-run-2026-09-16.json"
BROWSER = R.find_browser()


def kinds_the_page_handles() -> set:
    """Every `case "<k>":` of the page's `crow.on` switch."""
    page = crow_gui.PAGE
    start = page.index("  on(msg){")
    end = page.index("window.crow = crow;", start)
    return set(re.findall(r'case "(\w+)":', page[start:end]))


class ArgumentTests(unittest.TestCase):
    def test_size(self):
        self.assertEqual(R.parse_size("1440x960"), (1440, 960))
        self.assertEqual(R.parse_size(" 390X844 "), (390, 844))
        for bad in ("1440", "1440x", "axb", "1440x960x2", ""):
            with self.assertRaises(ValueError, msg=bad):
                R.parse_size(bad)

    def test_selectors_split_at_top_level_commas_only(self):
        self.assertEqual(R.split_selectors("#main, #bar ,#rail"), ["#main", "#bar", "#rail"])
        self.assertEqual(R.split_selectors("a:is(.x,.y),b"), ["a:is(.x,.y)", "b"])
        self.assertEqual(R.split_selectors("[data-k='1,2'],#z"), ["[data-k='1,2']", "#z"])
        self.assertEqual(R.split_selectors(""), [])
        self.assertEqual(R.split_selectors(" , ,"), [])

    def test_type_splits_at_the_first_equals_outside_brackets(self):
        self.assertEqual(R.split_type("#searchin=count"), ("#searchin", "count"))
        self.assertEqual(R.split_type("input[type=text]=a=b"), ("input[type=text]", "a=b"))
        self.assertEqual(R.split_type("#q= two words "), ("#q", " two words "))
        self.assertEqual(R.split_type("#q=/go"), ("#q", "/go"))
        for bad in ("no-equals", "=text", "", "[a=b]"):
            with self.assertRaises(ValueError, msg=bad):
                R.split_type(bad)

    def test_crow_chrome_wins_and_is_never_second_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "browser")
            Path(exe).write_text("x")
            self.assertEqual(R.find_browser({"CROW_CHROME": exe}, "linux"), exe)
            with self.assertRaises(SystemExit):
                R.find_browser({"CROW_CHROME": os.path.join(tmp, "missing")}, "linux",
                               which=lambda name: "/usr/bin/" + name)

    def test_windows_candidates_are_chrome_then_edge(self):
        env = {"PROGRAMFILES": "C:/PF", "PROGRAMFILES(X86)": "C:/PF86", "LOCALAPPDATA": "C:/LA"}
        names = [p.name for p in R.browser_candidates(env, "win32")]
        self.assertEqual(names, ["chrome.exe", "chrome.exe", "chrome.exe", "msedge.exe", "msedge.exe"])
        self.assertEqual(R.browser_candidates(env, "linux"), [])

    def test_linux_falls_back_to_path_in_order(self):
        seen = []

        def which(name):
            seen.append(name)
            return "/usr/bin/chromium" if name == "chromium" else None
        self.assertEqual(R.find_browser({}, "linux", which=which), "/usr/bin/chromium")
        self.assertEqual(seen, ["google-chrome", "google-chrome-stable", "chromium"])
        self.assertIsNone(R.find_browser({}, "linux", which=lambda name: None))

    def test_the_dumped_dom_is_unescaped_and_read(self):
        dom = '<body><pre id="__rects" hidden>{"rects": {"a&gt;b": null}, "errors": []}</pre></body>'
        self.assertEqual(R.read_result(dom), {"rects": {"a>b": None}, "errors": []})
        self.assertIsNone(R.read_result('<pre id="__rects" hidden></pre>'))
        self.assertIsNone(R.read_result("<body></body>"))

    def test_budget_grows_with_the_steps(self):
        self.assertEqual(R.virtual_budget(), R.VIRTUAL_BASE_MS)
        self.assertEqual(R.virtual_budget(["#a", "#b"], "#in"), R.VIRTUAL_BASE_MS + 3 * R.VIRTUAL_STEP_MS)
        self.assertEqual(R.virtual_budget(["#a"], "#in", [("#q", "x")], ["Enter", "Escape"]),
                         R.VIRTUAL_BASE_MS + 5 * R.VIRTUAL_STEP_MS)

    def test_main_refuses_without_a_browser_or_a_fixture(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch.object(R, "find_browser", return_value=None):
            self.assertEqual(R.main(["--fixture", str(FIXTURE)]), 2)
        self.assertIn("CROW_CHROME", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(R.main(["--fixture", str(HERE / "no-such.json")]), 2)
            self.assertEqual(R.main(["--fixture", str(FIXTURE), "--size", "wide"]), 2)
            self.assertEqual(R.main(["--fixture", str(FIXTURE), "--type", "no-equals"]), 2)


class FixtureTests(unittest.TestCase):
    """The fixture is held against the core, so it cannot drift from what the
    window is sent."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = R.load_fixture(FIXTURE)
        cls.messages = cls.fixture["messages"]

    def of(self, kind):
        return [m for m in self.messages if m["k"] == kind]

    def test_every_message_is_one_the_page_has_a_case_for(self):
        handled = kinds_the_page_handles()
        self.assertIn("cost", handled)
        used = {m["k"] for m in self.messages}
        self.assertEqual(used - handled, set())

    def test_the_turn_has_twelve_rounds_and_eleven_calls_in_order(self):
        self.assertEqual(len(self.of("start")), 12)
        self.assertEqual([m["name"] for m in self.of("tool")],
                         ["goal_set", "goal_step", "run_command", "run_command", "goal_step",
                          "goal_step", "delegate", "goal_step", "goal_step", "collect", "goal_step"])
        order = [m["k"] for m in self.messages]
        for i, kind in enumerate(order):
            if kind == "toolend":
                self.assertEqual(order[i - 1], "tool")
            if kind == "toolres":
                self.assertEqual(order[i - 1], "toolend")
        self.assertEqual(order[-1], "idle")
        self.assertEqual(order[order.index("cost") - 1], "format")

    def test_argument_summaries_are_the_cores(self):
        for m in self.of("tool"):
            self.assertEqual(m["args"], crow_core.format_tool_args(m["raw"]), m["name"])

    def test_the_answer_blocks_are_what_the_core_cuts(self):
        text = "".join(m["t"] for m in self.of("text"))
        self.assertEqual(self.of("format")[0]["blocks"], crow_core.markdown_blocks(text))

    def test_the_cost_line_is_turncost_line_of_the_stats(self):
        cost = self.of("cost")[0]
        s = cost["stats"]
        t = crow_core.TurnCost()
        t.rounds, t.decoded, t.prefilled = s["rounds"], s["decoded"], s["prefilled"]
        # record() rounds the seconds to 3 places and takes the rates from the
        # unrounded ones, so the line is rebuilt from the rates.
        t.decode_s = s["decoded"] / s["decode_rate"]
        t.prefill_s = s["prefilled"] / s["prefill_rate"]
        t.model_s, t.tool_s = s["model_s"], s["tool_s"]
        t.tool_calls, t.tool_errors, t.tool_declined = s["tool_calls"], s["tool_errors"], s["tool_declined"]
        t.cached, t.cached_of, t.finish = s["cached"], s["cached_of"], s["finish"]
        import time
        t.started = time.monotonic() - s["waited_s"]
        self.assertEqual(cost["line"], "[" + t.line() + "]")
        self.assertAlmostEqual(s["decode_s"], t.decode_s, places=3)
        self.assertAlmostEqual(s["prefill_s"], t.prefill_s, places=3)
        # the split the fixture marks as chosen: decode and prefill fit inside the model's time
        self.assertLessEqual(s["decode_s"] + s["prefill_s"], s["model_s"])
        self.assertAlmostEqual(s["model_s"] + s["tool_s"], s["waited_s"], places=3)
        self.assertEqual(s["tool_calls"], len(self.of("tool")))
        self.assertEqual(s["rounds"], len(self.of("start")))

    def test_the_cost_message_carries_what_the_page_reads_and_what_382_adds(self):
        cost = self.of("cost")[0]
        # `share` is a percentage: the page prints share.toFixed(0)
        self.assertEqual(cost["share"], 82.0)
        self.assertEqual((cost["tokens"], cost["n_ctx"]), (6100, 200000))
        self.assertTrue(cost["sub"].startswith("⑂ 1 subtask"))
        self.assertLessEqual(set(crow_core.TurnCost().record()) - {"seeds", "leg_seeds"}
                             - {"decode_rate", "prefill_rate", "cached", "cached_of", "finish"},
                             set(cost["stats"]))

    def test_the_goal_ends_complete(self):
        goal = self.of("goal")[-1]["goal"]
        self.assertEqual((goal["status"], goal["done"], goal["total"]), ("done", 3, 3))
        self.assertEqual(goal["delegated"], 65)
        self.assertEqual(self.of("subs")[-1]["items"][0]["res"], "42")


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = R.load_fixture(FIXTURE)

    def test_page_has_the_bridge_before_and_the_replay_after_the_pages_script(self):
        page = R.build_page(self.fixture, False, "dark", ["#go"], "#in", ["#main"])
        self.assertIn("window.pywebview = {api: new Proxy", page)
        self.assertIn("window.crow.on(m)", page)
        self.assertLess(page.index("window.pywebview = {api: new Proxy"), page.index("const crow = {"))
        self.assertGreater(page.index("window.crow.on(m)"), page.index("window.crowRemoteStart();"))
        self.assertIn("Count files, delegate 21*2, report results", page)    # the messages
        self.assertIn('["#go"]', page)
        self.assertIn('"#in"', page)
        self.assertIn('["#main"]', page)
        typed = R.build_page(self.fixture, False, "dark", types=[("#searchin", "/go")],
                             presses=["ArrowDown", "Enter"])
        self.assertIn('[["#searchin", "/go"]]', typed)
        self.assertIn('["ArrowDown", "Enter"]', typed)
        self.assertIn('data-theme="dark"', page)
        self.assertIn("if (false) {", page)
        self.assertIn("window.CROW_REMOTE = false;", page)

    def test_remote_page_stubs_the_network_the_phone_bridge_uses(self):
        page = R.build_page(self.fixture, True, "light", (), "", ())
        self.assertIn("window.CROW_REMOTE = true;", page)
        self.assertIn('data-theme="light"', page)
        self.assertIn("if (true) {", page)
        self.assertIn("window.EventSource = function", page)

    def test_the_theme_comes_from_the_temp_settings_not_the_real_ones(self):
        before = crow_gui.SETTINGS_FILE
        for theme in R.THEMES:
            self.assertIn('data-theme="%s"' % theme, R.build_page(self.fixture, False, theme))
        self.assertEqual(crow_gui.SETTINGS_FILE, before)

    def test_the_fixtures_panel_state_reaches_the_body(self):
        page = R.build_page(self.fixture, False, "dark")
        self.assertRegex(page, r'<body data-rail="open" data-code="open"')

    def test_a_message_cannot_close_the_script(self):
        fixture = {"messages": [{"k": "note", "t": "</script><b id='x'>"}], "api": {"a": "</script>"}}
        page = R.build_page(fixture, False, "dark")
        self.assertNotIn("</script><b id='x'>", page)
        self.assertIn("<\\/script>", page)

    def test_the_frame_holds_the_page_at_exactly_the_size(self):
        frame = R.build_frame((390, 844), "crow")
        self.assertIn("width:390px;height:844px", frame)
        self.assertIn('src="page.html"', frame)
        self.assertIn(crow_gui.THEME_BG["crow"], frame)

    def test_a_fixture_needs_messages_with_a_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            for doc in ('{}', '{"messages": [1]}', '{"messages": [{"t": "x"}]}', '[]'):
                bad.write_text(doc, encoding="utf-8")
                with self.assertRaises(ValueError, msg=doc):
                    R.load_fixture(bad)


@unittest.skipUnless(BROWSER, "no Chrome, Edge or Chromium (set CROW_CHROME)")
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = R.load_fixture(FIXTURE)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(R.remove_tree, cls.tmp.name)

    def render(self, name, size, remote=False, rects=("#bar", "#main", "#box"), fixture=None,
               clicks=(), focus="", types=(), presses=()):
        out = os.path.join(self.tmp.name, name + ".png")
        result = R.render(fixture or self.fixture, size, "dark", remote, clicks, focus,
                          list(rects), out, BROWSER, types, presses)
        return result, out

    def test_desktop_render_is_the_size_asked_for_and_repeats(self):
        first, out = self.render("desktop-1", (1440, 960))
        second, _ = self.render("desktop-2", (1440, 960))
        self.assertEqual(R.png_size(out), (1440, 960))
        self.assertEqual(first["errors"], [])
        self.assertEqual(json.dumps(first["rects"]), json.dumps(second["rects"]))
        bar = first["rects"]["#bar"]
        self.assertEqual((bar["x"], bar["y"], bar["w"]), (0, 0, 1440))
        main = first["rects"]["#main"]
        self.assertGreater(main["w"], 600)
        self.assertEqual(main["y"], bar["h"])
        # the replay drew the run: 12 rounds, 11 tool rows, the goal panel
        probe = self.render("probe", (1440, 960), rects=("#tclist", "#goalpanel", "#nothing-here"))[0]
        self.assertIsNone(probe["rects"]["#nothing-here"])
        self.assertGreater(probe["rects"]["#goalpanel"]["h"], 100)

    def test_phone_render_is_the_phone_size(self):
        result, out = self.render("phone", (390, 844), remote=True, rects=("#bar", "#box"))
        self.assertEqual(R.png_size(out), (390, 844))
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["rects"]["#bar"]["w"], 390)
        self.assertLessEqual(result["rects"]["#box"]["x"] + result["rects"]["#box"]["w"], 390)

    def test_clicks_and_focus_run_and_a_missed_selector_is_reported(self):
        # #384: the calls are the inspector's Tools tab, no longer a group to unfold.
        result, _ = self.render("clicks", (1440, 960), rects=("#toolcalls", "#in"),
                                clicks=["#itab-tools"], focus="#in")
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["rects"]["#toolcalls"]["h"], 100)     # the tab is shown
        missed, _ = self.render("missed", (1440, 960), clicks=["#no-such-button"], focus="#no-such")
        self.assertEqual(len(missed["errors"]), 2)
        self.assertIn("nothing matches #no-such-button", missed["errors"][0])

    def test_typing_and_keys_run_on_the_focused_field(self):
        """--type sets the value and sends `input`; --press sends keydown and
        keyup to whatever has the focus (#386's list under the search field)."""
        typed, _ = self.render("typed", (1440, 960), rects=("#searchpop", "#searchin"),
                               types=[("#searchin", "count")])
        self.assertEqual(typed["errors"], [])
        self.assertGreater(typed["rects"]["#searchpop"]["h"], 40)       # the list opened
        self.assertGreater(typed["rects"]["#searchin"]["w"], 100)       # the field is open
        shut, _ = self.render("pressed", (1440, 960), rects=("#searchpop", "#searchin"),
                              types=[("#searchin", "count")], presses=["Escape"])
        self.assertEqual(shut["errors"], [])
        self.assertEqual(shut["rects"]["#searchpop"]["h"], 0)           # Escape closed it
        self.assertEqual(shut["rects"]["#searchin"]["w"], 0)            # and the field folded
        missed, _ = self.render("type-missed", (1440, 960), types=[("#no-such-field", "x")])
        self.assertEqual(len(missed["errors"]), 1)
        self.assertIn("nothing matches #no-such-field", missed["errors"][0])

    def test_a_message_the_page_throws_on_is_reported(self):
        broken = {"messages": [{"k": "rail", "title": "t", "meta": "m", "unsaved": True,
                                "projects": [None]}]}
        result, _ = self.render("broken", (1440, 960), fixture=broken)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("message 0 (rail)", result["errors"][0])

    def test_the_command_prints_the_rects_as_one_json_line(self):
        out = os.path.join(self.tmp.name, "cli.png")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = R.main(["--fixture", str(FIXTURE), "--size", "1024x768", "--rects", "#bar,#main",
                           "--out", out])
        self.assertEqual(code, 0, stderr.getvalue())
        printed = json.loads(stdout.getvalue())
        self.assertEqual(list(printed), ["#bar", "#main"])
        self.assertEqual(printed["#bar"]["w"], 1024)
        self.assertEqual(R.png_size(out), (1024, 768))


if __name__ == "__main__":
    unittest.main()
