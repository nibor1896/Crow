"""cli/crow_boot_gui.py: the operating-point window (#196).

The controller is tested without a window: its view() is every word and
button the page draws. Underneath runs the real crow_boot.Boot with
test_crow_boot's fakes (Popen, the probe, the clock, the scan), so what is
checked here is the window's state over the menu's own logic. Starts run
synchronously (`run=` calls the worker in place); a probe hook looks at the
view while a start is under way.
"""

from __future__ import annotations

import copy
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import crow_boot  # noqa: E402
import crow_boot_gui  # noqa: E402
import crow_core  # noqa: E402
import crow_platform  # noqa: E402
from test_crow_boot import (LLAMA_27B, NOTHING, OK_HEALTH, STACK, BootCase,  # noqa: E402
                            FakeLlama, FakePopen)

SERVE_LINE = ("7001", r"C:\x\bin\serve.exe --port 8099")


def run_now(fn, *args):
    fn(*args)


# #340: the Media Stack runs on Windows only, so the rows a platform shows differ.
MEDIA = any(p["id"] == "media-stack" and crow_boot.runs_here(p) for p in STACK["points"])


def group(view, label):
    """The picker's entries under one group heading (#396)."""
    return next((g["items"] for g in view["picker"]["groups"] if g["label"] == label), [])


class GuiCase(BootCase):
    def controller(self, **kw):
        boot = self.boot(**kw)
        return crow_boot_gui.Controller(boot, clock=self.clock, run=run_now)

    def running_27b(self):
        crow_core.write_active_point("27b", "http://127.0.0.1:8099/v1", {"serve": 5151, "image": None})


class TheWindowShowsTheStacksGuiLineTests(GuiCase):
    def test_the_entries_carry_menu_gui_and_the_terminal_keeps_menu_line(self):
        ctl = self.controller()
        ctl.refresh()
        shown = {r["id"]: r["detail"] for r in group(ctl.view(), "Operating points")}
        # #340: a point for another platform is not offered here (runs_here).
        self.assertEqual(shown, {p["id"]: p["menu"]["gui"] for p in STACK["points"]
                                 if crow_boot.runs_here(p)})
        self.assertEqual(shown["27b"], "128k context. Great speed, coding and vision.")
        menu = {r[2]: r[3] for r in ctl.boot.entries()}
        self.assertEqual(menu["Qwen3.8-27B"], next(p["menu"]["line"] for p in STACK["points"]
                                                   if p["id"] == "27b"))

    def test_without_a_gui_line_the_menu_line_is_shown(self):
        self.assertEqual(crow_boot_gui.gui_line({"line": "plain"}), "plain")
        self.assertEqual(crow_boot_gui.gui_line({"line": "plain", "gui": "Window."}), "Window.")

    def test_the_refusal_names_a_point_without_its_family(self):
        self.assertEqual(crow_boot_gui.short_title("Qwen3.8-Flash-Next"), "Flash-Next")
        self.assertEqual(crow_boot_gui.short_title("Image Stack"), "Image Stack")


class State1NothingRunsTests(GuiCase):
    def test_one_picker_with_three_groups_and_a_greyed_open_button(self):
        # #396: one field instead of a row and a Start button per point.
        ctl = self.controller(llama=FakeLlama([LLAMA_27B]))
        ctl.refresh()
        v = ctl.view()
        self.assertEqual(v["phase"], crow_boot_gui.IDLE)
        self.assertEqual(v["say"], "Which model should Crow fly with?")
        self.assertIsNone(v["fill"])
        self.assertNotIn("rows", v)
        self.assertNotIn("optional", v)
        p = v["picker"]
        self.assertEqual([g["label"] for g in p["groups"]],
                         ["Operating points", "Optional (llama.cpp)"])
        self.assertEqual([r["title"] for r in group(v, "Operating points")],
                         ["Qwen3.8-Flash-Next", "Qwen3.8-27B", "GLM-5.3-Flash", "Image Stack"]
                         + ["Media Stack"] * MEDIA)
        self.assertEqual([(r["title"], r["detail"]) for r in group(v, "Optional (llama.cpp)")],
                         [("Qwen3.8-27B-UD-Q4_K_XL (optional)", "llama.cpp, port 8082")])
        self.assertEqual((p["selected"], p["detail"], p["enabled"]),
                         ("flash-next", "200k context. Great for coding and vision.", True))
        self.assertEqual(p["start"], {"label": "Start", "act": "start", "enabled": True})
        self.assertEqual(v["bar"]["text"], "Start a model, then open the Crow window.")
        self.assertEqual(v["bar"]["button"]["label"], "Open Crow window")
        self.assertFalse(v["bar"]["button"]["enabled"])


class State2StartingTests(GuiCase):
    def test_the_crow_fills_against_the_usual_time_then_lands(self):
        self.layout("27b")
        seen = []
        probes = iter([NOTHING] * 70 + [OK_HEALTH])

        def get(url, timeout):
            seen.append(ctl.view())
            return next(probes)
        ctl = self.controller(get=get)
        ctl.start("27b")
        at7 = next(v for v in seen if v["say"] == "Flying to the nest. 7 s")
        self.assertEqual(at7["phase"], crow_boot_gui.STARTING)
        usual = crow_boot_gui.USUAL_START_S["27b"]
        self.assertTrue(int(100 * 7 / usual) <= at7["fill"] <= int(100 * 8 / usual), at7["fill"])
        p = at7["picker"]
        self.assertEqual((p["selected"], p["detail"], p["enabled"], p["start"]["enabled"]),
                         ("27b", "Loading the model. Usually ready in under 20 s.", False, False))
        self.assertEqual(at7["bar"]["text"], "You can close this window. The model keeps loading.")
        self.assertEqual(at7["bar"]["button"]["label"], "Cancel")
        self.assertTrue(all(v["fill"] <= crow_boot_gui.FILL_CAP for v in seen),
                        "the crow is never full before the server answers")
        self.assertEqual(seen[-1]["fill"], crow_boot_gui.FILL_CAP)
        done = ctl.view()
        self.assertEqual(done["phase"], crow_boot_gui.LANDED)
        self.assertIsNone(done["fill"], "full on readiness")

    def test_cancel_stops_what_was_started_and_writes_no_contract(self):
        self.layout("27b")
        probes = []

        def get(url, timeout):
            probes.append(url)
            if len(probes) == 3:
                ctl.cancel()
            return NOTHING
        popen = FakePopen()
        ctl = self.controller(get=get, popen=popen)
        ctl.start("27b")
        self.assertEqual(self.terminated, [popen.procs[0]])
        self.assertIsNone(self.contract())
        v = ctl.view()
        self.assertEqual(v["phase"], crow_boot_gui.IDLE)
        self.assertIsNone(v["note"], "a cancel is not a failure")

    def test_the_image_stack_says_when_it_fetches_the_paint_brushes(self):
        self.layout("image-stack")
        seen = []

        def get(url, timeout):
            seen.append(ctl.view())
            return OK_HEALTH if url.endswith("/health") else (200, b"{}")
        ctl = self.controller(get=get)
        ctl.start("image-stack")
        self.assertEqual(seen[0]["picker"]["detail"], "Loading the model. Usually ready in under 20 s.")
        self.assertEqual(seen[-1]["picker"]["detail"], "Fetching the paint brushes (Qwen-Image).")

    def test_a_failed_start_says_why_and_offers_every_point_again(self):
        self.layout("27b")
        ctl = self.controller(popen=FakePopen(exit_code=1, log_lines=["CUDA error"]))
        ctl.start("27b")
        v = ctl.view()
        self.assertEqual(v["phase"], crow_boot_gui.IDLE)
        self.assertIn("did not land: serve exited with code 1", v["note"]["title"])
        self.assertIn("serve-8099.log", v["note"]["detail"])
        self.assertTrue(v["picker"]["enabled"] and v["picker"]["start"]["enabled"])


class State3LandedTests(GuiCase):
    def test_the_running_point_sits_on_top_with_stop_and_open_is_live(self):
        self.running_27b()
        ctl = self.controller()
        ctl.refresh()
        v = ctl.view()
        self.assertEqual(v["say"], "Landed.")
        self.assertEqual(v["running"], {"title": "Qwen3.8-27B", "stop": True,
                                        "detail": "Running on port 8099. 128k context, vision on."})
        # #396: the picker below the card, on what runs; Start is for another entry.
        p = v["picker"]
        self.assertEqual((p["selected"], p["enabled"], p["start"]["enabled"]), ("27b", True, False))
        self.assertEqual(v["bar"]["text"], "The Crow window opens on Qwen3.8-27B.")
        self.assertTrue(v["bar"]["button"]["enabled"])

    def test_a_point_found_by_the_scan_shows_landed_when_the_window_opens(self):
        ctl = self.controller(scan=lambda: [SERVE_LINE],
                              point_for=lambda url, timeout=3.0: "flash-next")
        ctl.refresh()
        v = ctl.view()
        self.assertEqual(v["phase"], crow_boot_gui.LANDED)
        self.assertEqual(v["running"]["title"], "Qwen3.8-Flash-Next")
        self.assertEqual(v["running"]["detail"], "Running on port 8099. 200k context, vision on.")

    def test_open_crow_window_starts_crow_gui_on_the_running_point(self):
        self.running_27b()
        popen = FakePopen()
        ctl = self.controller(popen=popen)
        ctl.refresh()
        ctl.open_crow()
        argv, _kw = popen.calls[0]
        self.assertTrue(argv[1].endswith("crow_gui.py"))
        self.assertEqual(argv[2:], ["--base-url", "http://127.0.0.1:8099/v1"])
        self.assertEqual(ctl.view()["bar"]["text"], "The Crow window is opening on Qwen3.8-27B.")

    def test_stop_ends_the_point_and_the_window_goes_back_to_the_choice(self):
        self.running_27b()
        killed = []
        ctl = self.controller(scan=lambda: [] if killed else [SERVE_LINE], kill=killed.append,
                              alive=lambda pid: str(pid) not in killed)
        ctl.refresh()
        ctl.stop()
        self.assertEqual(killed, ["7001"])
        self.assertIsNone(self.contract())
        v = ctl.view()
        self.assertEqual(v["phase"], crow_boot_gui.IDLE)
        self.assertIsNone(v["running"])

    def test_a_llama_server_is_shown_as_its_line(self):
        scan = lambda: [("6001", "llama-server.exe -m D:/m/Qwen3.8-27B-UD-Q4_K_XL.gguf --port 8082")]  # noqa: E731
        ctl = self.controller(scan=scan, llama=FakeLlama([LLAMA_27B]))
        ctl.refresh()
        v = ctl.view()
        self.assertEqual(v["running"]["title"], "Qwen3.8-27B-UD-Q4_K_XL (optional)")
        self.assertEqual(v["running"]["detail"], "Running on port 8082. llama.cpp.")
        self.assertEqual(len(group(v, "Operating points")), 4 + MEDIA,
                         "every baseline point is offered (and refused)")
        self.assertEqual(v["picker"]["selected"], "qwen35-q4-k-xl")


class TheWindowOnLinuxTests(GuiCase):
    """#341: the window starts a point on Linux, behind the user scope."""

    def test_start_27b_lands_scoped_and_the_row_reads_the_linux_plan(self):
        scope = ["systemd-run", "--user", "--scope", "--"]
        with mock.patch.object(crow_boot, "PLATFORM_KEY", "linux"), \
                mock.patch.object(crow_boot.crow_platform, "server_scope_prefix", lambda: list(scope)):
            self.layout("27b")
            popen = FakePopen()
            ctl = self.controller(popen=popen, get=lambda url, timeout: OK_HEALTH)
            ctl.start("27b")
            ctl.refresh()
            v = ctl.view()
        self.assertEqual(v["phase"], crow_boot_gui.LANDED, self.out.getvalue())
        self.assertEqual(v["running"]["detail"], "Running on port 8099. 128k context, vision on.")
        (argv, kw), = popen.calls
        self.assertEqual(argv[:len(scope)], scope)
        self.assertEqual(argv[len(scope)], os.path.join(self.install, "bin", "serve"))
        self.assertTrue(kw["env"]["LD_LIBRARY_PATH"].startswith(os.path.join(self.install, "bin")))


class State4OneModelAtATimeTests(GuiCase):
    def test_a_second_start_is_refused_with_a_pointer_to_stop(self):
        self.running_27b()
        popen = FakePopen()
        ctl = self.controller(popen=popen)
        ctl.refresh()
        ctl.start("flash-next")
        v = ctl.view()
        self.assertEqual(popen.calls, [], "nothing starts beside a running point")
        self.assertEqual(v["say"], "One model at a time.")
        self.assertEqual(v["warn"], {"title": "Flash-Next needs the card for itself.",
                                     "detail": "Stop Qwen3.8-27B first, then start Flash-Next."})
        self.assertEqual(v["running"]["title"], "Qwen3.8-27B")
        self.assertEqual(v["picker"]["selected"], "flash-next")
        self.assertTrue(v["bar"]["button"]["enabled"])

    def test_boots_own_refusal_lands_in_the_same_state(self):
        # Something started between the window's look and Boot's own check.
        self.layout("27b")
        looks = []

        def scan():
            looks.append(1)
            return [] if len(looks) == 1 else [SERVE_LINE]
        ctl = self.controller(scan=scan, point_for=lambda url, timeout=3.0: "image-stack")
        ctl.start("27b")
        v = ctl.view()
        self.assertEqual(v["phase"], crow_boot_gui.REFUSED)
        self.assertEqual(v["warn"]["detail"], "Stop Image Stack first, then start 27B.")


class ThePageTests(unittest.TestCase):
    def test_the_crow_is_inlined_and_the_page_draws_the_view(self):
        with open(crow_boot_gui.PAGE_FILE, encoding="utf-8") as fh:
            raw = fh.read()
        self.assertIn(crow_boot_gui.LOGO_LINE, raw)
        page = crow_boot_gui.page()
        self.assertNotIn(crow_boot_gui.LOGO_LINE, page)
        self.assertIn("var LOGO = 'data:image/svg+xml;base64,", page)
        self.assertIn("CROW", page)
        self.assertIn("Operating points", page)
        self.assertIn("pywebview-drag-region", page)

    def test_no_emoji_or_dash_in_what_the_window_says(self):
        with open(crow_boot_gui.PAGE_FILE, encoding="utf-8") as fh:
            raw = fh.read()
        with open(crow_boot_gui.__file__, encoding="utf-8") as fh:
            src = fh.read()
        for text in (raw, src):
            # ASCII only: no emoji, no em or en dash, in the page or its wording
            self.assertEqual([c for c in text if ord(c) > 127], [])


class FakeShell32:
    def __init__(self):
        self.ids = []

    def SetCurrentProcessExplicitAppUserModelID(self, app_id):  # noqa: N802 - the Win32 name
        self.ids.append(app_id)


class TheCrowOnTheTaskbarTests(unittest.TestCase):
    def test_the_window_has_its_own_id_not_the_chat_windows(self):
        shell = FakeShell32()
        self.assertTrue(crow_boot_gui.taskbar_identity(shell32=shell))
        self.assertEqual(shell.ids, ["Crow.OperatingPoints"])
        with open(os.path.join(str(HERE), "crow_gui.py"), encoding="utf-8") as fh:
            self.assertIn('AppUserModelID("Crow.Window")', fh.read(),
                          "the chat window's id, which this one must not share")

    def test_the_icon_is_crow_guis(self):
        import crow_gui
        with mock.patch.object(crow_boot_gui.crow_platform, "IS_WINDOWS", False):
            self.assertEqual(crow_boot_gui.start_kwargs(crow_gui),
                             {"gui": "gtk", "icon": crow_gui.icon_png(256) or None})
            self.assertTrue(crow_gui.icon_png(256).endswith(os.path.join("icons", "crow-256.png")))
            self.assertFalse(crow_boot_gui.dress_window(crow_gui))
        with mock.patch.object(crow_boot_gui.crow_platform, "IS_WINDOWS", True):
            self.assertEqual(crow_boot_gui.start_kwargs(crow_gui), {})
        self.assertTrue(os.path.isfile(crow_gui.ICON_FILE))

    def test_dress_window_asks_shell_buttons_until_the_window_has_a_caption(self):
        answers = iter([False, False, True])
        asked = []
        gui = mock.Mock(shell_buttons=lambda title: asked.append(title) or next(answers))
        clock = iter(x * 0.2 for x in range(100))
        with mock.patch.object(crow_boot_gui.crow_platform, "IS_WINDOWS", True):
            done = crow_boot_gui.dress_window(gui, sleep=lambda s: None, clock=lambda: next(clock))
        self.assertTrue(done)
        self.assertEqual(asked, ["Crow", "Crow", "Crow"])


class FakeWindow:
    def __init__(self):
        self.calls = []

    def hide(self):
        self.calls.append("hide")

    def destroy(self):
        self.calls.append("destroy")


class ClosingTests(unittest.TestCase):
    def test_closing_while_a_point_starts_hides_until_it_has_landed(self):
        ctl = crow_boot_gui.Controller(crow_boot.Boot(STACK, "i", "m", llama=FakeLlama()))
        api = crow_boot_gui.Api(ctl)
        api._window = FakeWindow()
        ctl.busy = True
        api.close()
        self.assertEqual(api._window.calls, ["hide"])
        ctl.busy = False
        for _ in range(40):
            if "destroy" in api._window.calls:
                break
            crow_boot_gui.time.sleep(0.05)
        self.assertEqual(api._window.calls, ["hide", "destroy"])

    def test_closing_an_idle_window_closes_it(self):
        ctl = crow_boot_gui.Controller(crow_boot.Boot(STACK, "i", "m", llama=FakeLlama()))
        api = crow_boot_gui.Api(ctl)
        api._window = FakeWindow()
        api.close()
        self.assertEqual(api._window.calls, ["destroy"])

    def test_the_bridge_exposes_only_its_calls(self):
        api = crow_boot_gui.Api(crow_boot_gui.Controller(
            crow_boot.Boot(STACK, "i", "m", llama=FakeLlama())))
        public = sorted(n for n in vars(api) if not n.startswith("_"))
        self.assertEqual(public, [], "pywebview would expose these to the page")


class TheWindowStartsNoConsoleTests(unittest.TestCase):
    """robin's live test 2026-10-01: under pythonw every helper the window
    polls (the process scan every 5 s, taskkill on Stop, nvidia-smi) opened its
    own console window in the foreground. Each helper must ask for none."""

    def test_the_process_scan_asks_windows_for_no_console(self):
        import crow_platform
        import subprocess
        seen = {}

        def run(argv, **kw):
            seen.update(kw)
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(crow_platform, "IS_WINDOWS", True), \
                mock.patch.object(crow_platform.subprocess, "run", run):
            crow_platform._run_query(["powershell", "-Command", "x"])
        flags = seen.get("creationflags", 0)
        self.assertTrue(flags & 0x08000000, "the scan runs without CREATE_NO_WINDOW")

    def test_every_helper_crow_platform_runs_passes_the_no_console_keywords(self):
        import ast
        import crow_platform
        tree = ast.parse(Path(crow_platform.__file__).read_text(encoding="utf-8"))
        bare = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run" and getattr(node.func.value, "id", "") == "subprocess"):
                kws = {k.arg for k in node.keywords}
                if None not in kws and "creationflags" not in kws:
                    bare.append(node.lineno)
        self.assertEqual(bare, [], "subprocess.run without **no_console_kwargs() at these lines")



class AComfyUIAloneHasItsCardTests(GuiCase):
    """#340: a ComfyUI left without its language model is shown and stoppable."""

    def test_the_card_names_the_video_server(self):
        line = (r'"C:\x\comfyui\python_embeded\python.exe" -s C:\x\comfyui\ComfyUI\main.py'
                r' --port 8188')
        ctl = self.controller(scan=lambda: [("9191", line)])
        ctl.refresh()
        running = ctl.view()["running"]
        self.assertEqual(running["title"], "Video server (ComfyUI)")
        self.assertIn("pid 9191", running["detail"])


class APointForOnePlatformIsOfferedThereOnlyTests(GuiCase):
    """#340: the window offers what the terminal menu offers (crow_boot.runs_here):
    the Media Stack runs on Windows only."""

    def titles(self):
        ctl = self.controller()
        ctl.refresh()
        return [r["title"] for r in group(ctl.view(), "Operating points")]

    def test_linux_does_not_offer_the_media_stack(self):
        with mock.patch.object(crow_boot, "PLATFORM_KEY", "linux"):
            self.assertNotIn("Media Stack", self.titles())

    def test_windows_offers_it(self):
        with mock.patch.object(crow_boot, "PLATFORM_KEY", "windows"):
            self.assertIn("Media Stack", self.titles())


# ---------------------------------------------------------- the picker (#396) ---

# The no-vision variant #397 adds to stack.json, shaped as its interface says:
# Flash-Next and the 27B one `text` variant each, the other points none.
VARIANT_GUI = {"flash-next": "200k context. Great for coding.",
               "27b": "128k context. Great speed and coding."}


def variant_stack():
    doc = copy.deepcopy(STACK)
    for p in doc["points"]:
        if p["id"] in VARIANT_GUI:
            p["variants"] = [{"key": "text", "vision": False,
                              "menu": {"line": "text only", "gui": VARIANT_GUI[p["id"]]},
                              "env": {}, "env_unset": ["CROW_VIT_MMPROJ"]}]
    return doc


class ThePickerTests(GuiCase):
    """#396: one select-only combobox, a Vision switch and one Start."""

    def controller(self, **kw):
        ctl = super().controller(**kw)
        ctl.boot.stack = variant_stack()
        return ctl

    def test_select_changes_the_line_under_the_field(self):
        ctl = self.controller()
        ctl.refresh()
        ctl.select("27b")
        p = ctl.view()["picker"]
        self.assertEqual((p["selected"], p["detail"]),
                         ("27b", "128k context. Great speed, coding and vision."))
        ctl.select("glm53-flash")
        self.assertEqual(ctl.view()["picker"]["detail"],
                         "200k context. The big MoE, experts streamed from NVMe.")
        ctl.select("no-such-entry")
        self.assertEqual(ctl.view()["picker"]["selected"], "glm53-flash", "an unknown id is not taken")

    def test_the_vision_switch_shows_only_for_a_point_with_a_no_vision_variant(self):
        ctl = self.controller()
        ctl.refresh()
        shown = {}
        for entry in ("flash-next", "27b", "glm53-flash", "image-stack"):
            ctl.select(entry)
            shown[entry] = ctl.view()["picker"]["vision"]["shown"]
        self.assertEqual(shown, {"flash-next": True, "27b": True, "glm53-flash": False,
                                 "image-stack": False})

    def test_vision_off_shows_the_variants_line(self):
        ctl = self.controller()
        ctl.refresh()
        ctl.set_vision(False)
        p = ctl.view()["picker"]
        self.assertEqual((p["vision"], p["detail"]),
                         ({"shown": True, "on": False}, "200k context. Great for coding."))

    def test_start_with_vision_off_starts_the_text_variant(self):
        calls = []
        ctl = self.controller()
        ctl.boot.start = lambda point_id, **kw: calls.append((point_id, kw)) or crow_boot.EXIT_OK
        ctl.refresh()
        api = crow_boot_gui.Api(ctl)
        api.set_vision(False)
        api.start()                           # the page's Start: the picker's entry
        ctl.set_vision(True)
        ctl.start()
        ctl.select("glm53-flash")
        ctl.set_vision(False)
        ctl.start()
        # `variant=` only when one is chosen, so today's Boot.start takes the call too
        self.assertEqual(calls, [("flash-next", {"variant": "text"}), ("flash-next", {}),
                                 ("glm53-flash", {})])

    def test_starting_disables_the_picker(self):
        self.layout("27b")
        seen = []

        def get(url, timeout):
            if not seen:
                ctl.select("glm53-flash")     # the field is disabled: no new choice
                ctl.set_vision(False)
            seen.append(ctl.view())
            return OK_HEALTH
        ctl = self.controller(get=get)
        ctl.select("27b")
        ctl.start()
        v = seen[0]
        p = v["picker"]
        self.assertEqual(v["phase"], crow_boot_gui.STARTING)
        self.assertEqual((p["enabled"], p["selected"], p["start"]["enabled"], p["vision"]["on"]),
                         (False, "27b", False, True))
        self.assertEqual(p["detail"], "Loading the model. Usually ready in under 20 s.")
        self.assertEqual(ctl.view()["picker"]["selected"], "27b")

    def test_landed_with_another_selection_gives_the_refusal_on_start(self):
        self.running_27b()
        popen = FakePopen()
        ctl = self.controller(popen=popen)
        ctl.refresh()
        p = ctl.view()["picker"]
        self.assertEqual((p["selected"], p["start"]["enabled"]), ("27b", False),
                         "what runs is the default, and it is not started twice")
        ctl.select("flash-next")
        ctl.start()
        v = ctl.view()
        self.assertEqual(popen.calls, [], "nothing starts beside a running point")
        self.assertEqual(v["phase"], crow_boot_gui.REFUSED)
        self.assertEqual(v["warn"], {"title": "Flash-Next needs the card for itself.",
                                     "detail": "Stop Qwen3.8-27B first, then start Flash-Next."})
        ctl.select("glm53-flash")
        v = ctl.view()
        self.assertEqual((v["phase"], v["warn"]), (crow_boot_gui.LANDED, None),
                         "a new choice clears the refusal that named the old one")

    def test_a_selection_the_stack_no_longer_offers_falls_back_to_the_first_entry(self):
        ctl = self.controller()
        ctl.refresh()
        ctl.select("27b")
        ctl.boot.stack = {"points": [p for p in ctl.boot.stack["points"] if p["id"] != "27b"]}
        self.assertEqual(ctl.view()["picker"]["selected"], "flash-next")

    def test_the_running_card_says_vision_off_for_the_text_variant(self):
        ctl = self.controller()
        running = {"kind": crow_platform.KIND_CROW_NEST, "point": "27b",
                   "base_url": "http://127.0.0.1:8099/v1"}
        self.assertEqual(ctl.running_card(dict(running, variant="text"))["detail"],
                         "Running on port 8099. 128k context, vision off.")
        self.assertEqual(ctl.running_card(dict(running, variant=None))["detail"],
                         "Running on port 8099. 128k context, vision on.")


class ThePickerPageTests(unittest.TestCase):
    """#396: the page draws the picker as the APG select-only combobox."""

    def test_the_page_has_the_combobox_roles_keys_and_the_switch(self):
        with open(crow_boot_gui.PAGE_FILE, encoding="utf-8") as fh:
            raw = fh.read()
        for marker in ('role="combobox"', 'role="listbox"', 'role="option"', 'role="group"',
                       "aria-activedescendant", "aria-expanded", "aria-controls",
                       'type="checkbox" role="switch"', "'PageDown'", "'Escape'", "e.altKey",
                       "typeAhead", "act('select'", "act('set_vision'"):
            self.assertIn(marker, raw)
        self.assertNotIn("v.rows", raw)

    def test_no_function_of_the_page_is_declared_twice(self):
        # The later declaration replaces the first in the whole script: a list
        # helper named mark() once drew "undefined" where the crow sits.
        with open(crow_boot_gui.PAGE_FILE, encoding="utf-8") as fh:
            names = re.findall(r"\bfunction\s+(\w+)\s*\(", fh.read())
        self.assertEqual(sorted(n for n in set(names) if names.count(n) > 1), [])


if __name__ == "__main__":
    unittest.main()
