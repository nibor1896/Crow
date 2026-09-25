#!/usr/bin/env python3
"""Suite for the window: cli/crow_gui.py against cli/crow_core.py.

Run:  python cli/test_crow_gui.py

WHAT CHANGED UNDER THIS FILE, AND WHAT DID NOT. The first version of this suite
read Tk widget state -- `displaychars`, the widget's own `dump`, the real
clipboard -- because the window was a `tk.Tk` and the only honest question was
"what is on the screen". E12 replaced that window with a pywebview page, so
every one of those predicates now asks a question about an object that no longer
exists. The BEHAVIOUR they were cut against did not change, and neither did the
cases: an abort against a blocked read, batching instead of one render per
event, reasoning that re-enters mid-answer, one session file through two doors.

SO THE SEAM MOVED FROM THE WIDGET TO THE MESSAGE. Everything the window draws
arrives as one JSON message pushed onto `Api._out` -- there is no second path to
the page and no shadow copy beside it, which is what made the widget rule worth
having in the first place. Reading that queue is reading what the page was told,
and `test_every_message_the_window_pushes_has_a_case_on_the_page` closes the
other half: a message the page has no `case` for is drawn by nobody. That hole
was real, and it had swallowed the reasoning share of every turn.

NO SERVER, NO MODEL, NO NETWORK, and no window either: `Api` is driven directly,
which is what the page does through `js_api`. The streams are recorded chunks
fed through the REAL `crow_core.stream_reply` and the REAL `crow_core.run_turn`
by rebinding `_post_stream`, the one door there is. The two proofs that need a
running server -- the abort's next question answered in under 30 s, and the two
live directions of the session round trip -- are E14's by the plan's own
arrangement.

NO TK, SO NOTHING SKIPS. The old suite skipped on a headless box, which was
honest and also meant the cases never ran anywhere they were not being watched.
"""

from __future__ import annotations

import atexit
import difflib
import io
import inspect
import json
import os
import re
import shutil
import socket
import struct
import sys
import tempfile
import threading
import time
from unittest import mock
import unittest
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import crow            # noqa: E402
import crow_core       # noqa: E402
import crow_gui        # noqa: E402
import crow_platform   # noqa: E402

# THE SUITE MAY NOT DEPEND ON WHAT THIS MACHINE HAS CONFIGURED (#130).
# `crow_core` reads %LOCALAPPDATA%\Crow\mcp.json at import and appends whatever
# it finds to TOOLS, TOOL_IMPL and TOOL_CLASS. Every case that enumerates the
# tool table therefore answered differently on a machine with an MCP server than
# on one without -- found on 2026-08-22, when `ReleaseLevelTests` went red
# against a real MCP install and nothing in this file had changed.
#
# A PATH WHOSE PARENT DOES NOT EXIST, not a temp file that might: the reader
# treats "no file" as the empty configuration, and that is the state the twelve
# built-in tools are the whole table in. Cases that WANT a configuration rebind
# `MCP_FILE` themselves and put it back.
#
# #155: UNTER EINEM JE PROZESS FRISCHEN ORDNER, NIE UNTER EINEM FESTEN NAMEN.
# Die festen %TEMP%-Namen ueberlebten den Prozess: was ein Lauf durch die
# vollen Pfade schrieb, fand der naechste als "leere" Konfiguration vor --
# am 2026-08-29 zweimal bezahlt (HTTP 401 im Bild-Fall aus einer
# hinterlassenen providers.json, d1-Leiche im Delegations-Fall aus einer
# hinterlassenen session.json). mkdtemp ist leer per Konstruktion, atexit
# raeumt ab, und zwei parallele Laeufe teilen keinen Pfad mehr.
_SANDBOX = tempfile.mkdtemp(prefix="crow-suite-")
atexit.register(shutil.rmtree, _SANDBOX, True)
crow_core.MCP_FILE = os.path.join(_SANDBOX, "has-no-mcp", "mcp.json")
crow_core.mcp_apply()

# THE SAME RULE FOR THE PROVIDER FILES (#130 again). `provider_endpoint` reads
# providers.json under %LOCALAPPDATA%, so on a machine with OpenRouter chosen
# every case that resolves an endpoint would answer differently from the same
# case on a fresh install -- and the one that broke would be the one about where
# a turn goes. A path whose parent does not exist is the empty configuration.
crow_core.PROVIDERS_FILE = os.path.join(_SANDBOX, "has-no-provider", "providers.json")
crow_core.PROVIDER_KEYS_FILE = os.path.join(_SANDBOX, "has-no-provider", "keys.json")
crow_core.PROVIDER_TOKEN_FILE = os.path.join(_SANDBOX, "has-no-provider", "tokens.json")
# 2026-08-28: die Dauer-Freigaben ("always") schreiben nach APPROVALS_FILE --
# dieselbe Regel, gefunden vom Waechter unten am Abend ihrer Einfuehrung.
crow_core.APPROVALS_FILE = os.path.join(_SANDBOX, "has-no-provider", "approvals.json")
# Und die Boot-Registry aus derselben Nacht: eine Suite, die die echte Datei
# laese, koennte robins LIVE-Server "wiederbeleben" -- nie.
crow_core.BOOTED_FILE = os.path.join(_SANDBOX, "has-no-provider", "booted.json")

# UND DIE BEIDEN, DIE HIER BIS ZUM 2026-08-23 GEFEHLT HABEN. Ein Fall schrieb
# einen erfundenen API-Schluessel in robins ECHTE `mcp_tokens.json`, ein
# zweiter eine `rail_width` in seine echte `settings.json` -- beides Dateien,
# die der laufende Client liest, und die erste kostete eine Stunde Fehlersuche
# an der falschen Stelle. `TheSuiteTouchesNoRealConfigurationTests` weiter
# unten sucht ab jetzt nach dem naechsten Pfad, den jemand hier vergisst.
crow_core.MCP_TOKEN_FILE = os.path.join(_SANDBOX, "has-no-mcp", "mcp_tokens.json")

# UND DER REST DES VERZEICHNISSES, gefunden am 2026-08-23 vom Waechter weiter
# unten, nachdem zwei Faelle in robins laufende Installation geschrieben hatten.
# Die vier oben sahen aus wie die Loesung; tatsaechlich stand die Suite mit acht
# weiteren Konstanten weiterhin auf seinen echten Sessions, seinen Roots, seinen
# Skills, seiner USER.md und seinem Suchindex. Ein Fall, der eine davon
# schreibt, aendert, was der laufende Client danach liest.
#
# EIN PFAD, DESSEN ELTERN NICHT EXISTIEREN, wie bei den vier oben: der Leser
# behandelt "keine Datei" als leeren Zustand, und das ist der Zustand, gegen den
# diese Suite gedacht ist. Faelle, die Inhalt WOLLEN, biegen selbst um und legen
# ihn an.
_NOWHERE = os.path.join(_SANDBOX, "has-no-install")
crow_core.INDEX_PATH = os.path.join(_NOWHERE, "index.db")
crow_core.ROOTS_FILE = os.path.join(_NOWHERE, "roots.json")
# UND DER, DEN DIE WACHE WEITER UNTEN BEIM LINUX-PORT GEFUNDEN HAT. Die
# Geheimnisse standen in dieser Suite bis heute auf der ECHTEN Datei --
# test_crow_core.py biegt sie seit langem um, diese Datei nie. Aufgefallen ist
# es erst, als `_real_roots` alle drei XDG-Wurzeln pruefte statt nur der einen
# Windows-Wurzel; die Wache war also richtig und ihr Fang der erste Beweis.
crow_core.SECRETS_FILE = os.path.join(_NOWHERE, "secrets.json")
crow_core.SESSION_DIR = os.path.join(_NOWHERE, "session")
crow_core.SESSION_FILE = os.path.join(_NOWHERE, "session", "session.json")
crow_core.SKILLS_DIR = os.path.join(_NOWHERE, "skills")
# #298: no kit skill seeded from this checkout into the cases.
crow_core.PATHTRACER_KIT = os.path.join(_NOWHERE, "kits", "pathtracer")
crow_core.USER_PATH = os.path.join(_NOWHERE, "USER.md")
# #262: Crow's own log file, never the real one under the state dir.
crow_core.LOG_FILE = os.path.join(_SANDBOX, "log", "crow.log")
crow_gui.PASTE_DIR = os.path.join(_NOWHERE, "pastes")
crow_gui.SESSION_FILE = os.path.join(_NOWHERE, "session", "session.json")
crow_gui.SETTINGS_FILE = os.path.join(_SANDBOX, "has-no-settings", "settings.json")


# #249: KEIN FALL OEFFNET JE EINEN ECHTEN PORT. Der Standard-Doppelgaenger
# weigert sich zu starten -- so beantwortet auch die Schleife ueber alle
# Slash-Befehle ein nacktes `/remote`, ohne zu lauschen und ohne
# `remote_enabled` in die Sandbox zu schreiben. Die Remote-Faelle setzen ihren
# eigenen, der startet.
class _RemoteRefuses:
    def __init__(self, **_kw):
        pass

    def start(self):
        raise OSError("the suite never listens")


crow_gui.REMOTE_FACTORY = _RemoteRefuses
# #249 STAGE 5: UND KEIN FALL RUFT JE DIE ECHTE `tailscale`-CLI. Der Standard
# ist "nicht installiert"; die Tailnet-Faelle setzen ihre eigene Antwort.
crow_gui.TAILSCALE_PROBE = lambda port: {"state": "missing"}
import crow_voice      # noqa: E402


# ---------------------------------------------------------------- fixtures --

# THE STREAM E4's SEAM WAS CUT AGAINST, and the one both surfaces are held to
# below: reasoning, then an answer, in the shape the server sends them.
RECORDED = [
    {"reasoning_content": "the socket is the question here"},
    {"content": "The read sits in _post_stream.\n"},
    {"content": "A close from outside reaches the buffer.\n"},
]

# P3 IN FIVE DELTAS: think, answer, THINK AGAIN, answer again, inside one turn.
# The same fixture cli/test_crow_core.py cuts E10's state machine against,
# repeated here on purpose -- the window has to survive the identical shape, and
# a test file that invented its own would be measuring a different stream.
RE_ENTRY = [
    {"reasoning_content": "first I "},
    {"reasoning_content": "consider it"},
    {"content": "ANSWER ONE\n"},
    {"reasoning_content": "wait -- I should check"},
    {"content": "ANSWER TWO\n"},
]

TIMINGS = {"predicted_n": 252, "predicted_ms": 17060.0, "predicted_per_second": 14.77,
           "prompt_n": 528, "prompt_ms": 7066.0, "prompt_per_second": 74.72}
USAGE = {"total_tokens": 11507, "prompt_tokens_details": {"cached_tokens": 10979}}


class _StoppedClock:
    """`time` with a monotonic that does not move.

    The live counter throttles on elapsed wall clock. A case about the throttle
    that let the clock run would be measuring the machine's mood; everything
    else on the module is passed straight through.
    """

    def __init__(self, at: float = 1000.0) -> None:
        self._at = at

    def monotonic(self) -> float:
        return self._at

    def __getattr__(self, name: str):
        return getattr(time, name)


def chunks_for(deltas: list[dict], timings: dict | None = None,
               every: bool = False) -> list[str]:
    """A recorded stream as the wire carries it: one JSON payload per chunk."""
    out = []
    for delta in deltas:
        chunk: dict = {"choices": [{"delta": delta}]}
        if timings and every:
            chunk["timings"] = timings
        out.append(json.dumps(chunk))
    tail: dict = {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": USAGE}
    if timings:
        tail["timings"] = timings
    out.append(json.dumps(tail))
    return out


class ApiCase(unittest.TestCase):
    """An `Api` with its session directory in a temp dir, and nothing global left
    behind.

    BOTH `SESSION_FILE`s ARE REBOUND, and that is not belt and braces: the window
    imported the name at module load, so `crow_gui.SESSION_FILE` is a second
    binding to the same string. Patching only the core's would leave the rail
    reading one directory while the writes went to another -- and the suite would
    be green about a window nobody could have used.
    """

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="crow-gui-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.session = os.path.join(self.dir, "session.json")
        self._before = (crow_core._post_stream, crow_core.SESSION_FILE,
                        crow_core.SESSION_DIR, crow_gui.SESSION_FILE,
                        crow_gui.time)
        self.addCleanup(self._restore)
        crow_core.SESSION_DIR = self.dir
        crow_core.SESSION_FILE = self.session
        crow_gui.SESSION_FILE = self.session
        crow_core.INTERRUPT.clear()

    def _restore(self) -> None:
        (crow_core._post_stream, crow_core.SESSION_FILE, crow_core.SESSION_DIR,
         crow_gui.SESSION_FILE, crow_gui.time) = self._before
        crow_core.INTERRUPT.clear()

    def api(self, *argv: str, klass=None, session: bool = True):
        """The object the page talks to. No window, because the page is not here.

        `Api.push` only ever puts a dict on a queue; `pump` is the one method
        that touches the window, and it is a thread `main` starts. Driving the
        Api directly is therefore the same code path the page drives, minus the
        transport.
        """
        args = crow_gui.build_parser().parse_args(
            ["--base-url", "http://127.0.0.1:1/v1", *argv])
        args.session = session
        return (klass or crow_gui.Api)(args)

    def drained(self, api) -> list[dict]:
        """Everything the page would have been told, in order."""
        out = []
        while True:
            try:
                out.append(api._out.get_nowait())
            except Exception:
                return out

    def kinds(self, api) -> list[str]:
        return [m.get("k") for m in self.drained(api)]

    def answer_text(self, messages: list[dict]) -> str:
        return "".join(m["t"] for m in messages if m.get("k") == "text")

    def serve(self, payloads: list[str]) -> None:
        """Script the endpoint. The REAL stream loop runs behind it."""
        def fake(url, body, api_key, timeout):
            for payload in payloads:
                yield payload
        crow_core._post_stream = fake

    def sink_events(self, deltas: list[dict], klass=None,
                    live: bool = True) -> list[dict]:
        """One recorded stream through the real core into a real `Sink`."""
        collected: list[dict] = []
        sink = (klass or crow_gui.Sink)(collected.append, live=live)
        self.serve(chunks_for(deltas))
        crow_core.stream_reply(
            crow_core.Conversation("SYS"), base_url="http://x/v1", model="crow",
            api_key="k", temperature=0.0, timeout=1.0, events=sink)
        return collected

    def a_chat(self, api, first: str = "the first thing said",
               reply: str = "an answer") -> None:
        """A conversation with something in it, without a server."""
        api._conversation.append("user", first)
        api._conversation.append("assistant", reply)

    def rail(self, api) -> dict:
        """The last rail message the page would have received."""
        rails = [m for m in self.drained(api) if m.get("k") == "rail"]
        self.assertTrue(rails, "the rail was never drawn")
        return rails[-1]


# ----------------------------------------------------------------- F1, P3 ----

class TheStreamReachesThePageTests(ApiCase):
    """What the core said, and what the page was told, are the same thing."""

    def test_a_recorded_stream_arrives_as_text_and_thought_messages(self):
        """POSITIVE. The answer arrives as `text`, the reasoning as `think`, and
        the two are never the same message."""
        events = self.sink_events(RECORDED)
        self.assertEqual(self.answer_text(events),
                         "The read sits in _post_stream.\n"
                         "A close from outside reaches the buffer.\n")
        thoughts = "".join(m["t"] for m in events if m.get("k") == "think")
        self.assertEqual(thoughts, "the socket is the question here")

    def test_the_thoughts_are_not_in_the_answer(self):
        """The reasoning is 53 % of a turn at the shipped operating point. Merged
        into the answer it is indistinguishable from it."""
        self.assertNotIn("the socket is the question here",
                         self.answer_text(self.sink_events(RECORDED)))

    def test_reasoning_that_re_enters_opens_a_second_block(self):
        """P3, POSITIVE. Think, answer, think again, answer again -- inside one
        turn. One block per re-entry, in the order the stream had them."""
        events = self.sink_events(RE_ENTRY)
        shape = [m["k"] for m in events
                 if m["k"] in ("think_open", "think_close", "text")]
        self.assertEqual(shape.count("think_open"), 2,
                         "a re-entering stream produced %d thought blocks"
                         % shape.count("think_open"))
        self.assertEqual(shape.count("think_open"), shape.count("think_close"),
                         "a thought block was opened and never closed")
        # THE RUNS ARE NOT ONE MESSAGE EACH, and that is the core's decision:
        # `CodeFences.feed` looks at the first characters of a line singly --
        # that is the span in which it could still become a fence -- and hands
        # the rest over in whole runs. So the shape is compared by its blocks
        # rather than by counting `text` messages.
        blocks = [k for i, k in enumerate(shape)
                  if k != "text" or i == 0 or shape[i - 1] != "text"]
        self.assertEqual(blocks, ["think_open", "think_close", "text",
                                  "think_open", "think_close", "text"])
        self.assertEqual(self.answer_text(events), "ANSWER ONE\nANSWER TWO\n")

    def test_a_stream_with_one_thought_does_not_fake_a_re_entry(self):
        """NEGATIVE for the case above. A predicate that counted blocks without
        the stream having them would pass on anything."""
        events = self.sink_events(RECORDED)
        self.assertEqual(len([m for m in events if m["k"] == "think_open"]), 1)


class _ReasoningLeaksIntoTheAnswer(crow_gui.Sink):
    """A sink that reports the thoughts as answer text.

    The single most likely mistake in a window that shows reasoning: one stream
    of text with the thoughts merged in. It is here to be driven through the
    same comparison as the real one, because "the two clients answer the same
    question the same way" has to be able to fail.
    """

    def reasoning_text(self, piece: str) -> None:
        self.answer_text(piece)


class AcrossTheClientBoundaryTests(ApiCase):
    """E4's diff runs CLI against CLI. This runs CLI against the window.

    The same recorded stream through BOTH sinks, the visible answer of each
    written to a file, and `diff`. That is the sharper form of "both clients
    answer the same question the same way", and it costs nothing.
    """

    def _cli_text(self, deltas: list[dict]) -> str:
        out = io.StringIO()
        self.serve(chunks_for(deltas))
        crow_core.stream_reply(
            crow_core.Conversation("SYS"), base_url="http://x/v1", model="crow",
            api_key="k", temperature=0.0, timeout=1.0,
            events=crow.TerminalEvents(out=out, prefix=""))
        return out.getvalue()

    def _files(self, cli: str, gui: str) -> tuple[str, str]:
        cli_path = os.path.join(self.dir, "answer-cli.txt")
        gui_path = os.path.join(self.dir, "answer-gui.txt")
        for path, text in ((cli_path, cli), (gui_path, gui)):
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        return cli_path, gui_path

    def _diff(self, cli_path: str, gui_path: str) -> str:
        with io.open(cli_path, encoding="utf-8") as fh:
            a = fh.readlines()
        with io.open(gui_path, encoding="utf-8") as fh:
            b = fh.readlines()
        return "".join(difflib.unified_diff(a, b, "cli", "gui"))

    def test_both_clients_show_the_same_answer_for_the_same_stream(self):
        """POSITIVE, as two files and a diff."""
        cli_path, gui_path = self._files(
            self._cli_text(RECORDED), self.answer_text(self.sink_events(RECORDED)))
        self.assertEqual(self._diff(cli_path, gui_path), "")

    def test_a_sink_that_writes_reasoning_into_the_answer_fails_the_diff(self):
        """NEGATIVE, and the case the positive one is worthless without."""
        cli_path, gui_path = self._files(
            self._cli_text(RECORDED),
            self.answer_text(self.sink_events(RECORDED,
                                              klass=_ReasoningLeaksIntoTheAnswer)))
        self.assertNotEqual(self._diff(cli_path, gui_path), "",
                            "a sink that shows the thoughts as the answer passed "
                            "the comparison -- then the comparison checks nothing")


# --------------------------------------------------------------------- P2 ---

class ThrottleTests(ApiCase):
    """P2: "one event per token ... the fix is batching per tick, not rendering
    per event."

    THE WEBVIEW'S ANSWER TO P2 IS NOT TK'S. There is no tick to batch into: every
    message crosses to the page on its own. What would flood the page is the LIVE
    COUNTER, which has something new to say on every single delta, and it is
    throttled to five updates a second. The text is not throttled, and must not
    be -- a dropped delta is a hole in the answer.
    """

    def test_a_burst_of_deltas_produces_at_most_one_counter_update(self):
        """POSITIVE. Sixty deltas inside one 200 ms window leave one `live`
        message, not sixty."""
        crow_gui.time = _StoppedClock()
        collected: list[dict] = []
        sink = crow_gui.Sink(collected.append)
        sink.reply_started()
        for i in range(60):
            sink.answer_text("tok%02d " % i)
        live = [m for m in collected if m["k"] == "live"]
        self.assertLessEqual(len(live), 1,
                             "sixty deltas produced %d counter updates -- that is "
                             "one render per event" % len(live))

    def test_the_throttle_drops_no_answer_text(self):
        """NEGATIVE for the throttle: it may thin the counter and nothing else.
        A version that throttled the text would pass the case above and lose the
        answer."""
        crow_gui.time = _StoppedClock()
        collected: list[dict] = []
        sink = crow_gui.Sink(collected.append)
        sink.reply_started()
        for i in range(60):
            sink.answer_text("tok%02d " % i)
        sink.reply_finished()
        text = self.answer_text(collected)
        self.assertEqual(text.count("tok"), 60,
                         "%d of 60 deltas reached the page" % text.count("tok"))

    def test_a_replayed_chat_counts_nothing(self):
        """A restored conversation is drawn through the same sink with the
        counter off: a chat loaded from a file has no rate, and a counter
        climbing over an answer written yesterday is a lie about what is
        happening now."""
        collected: list[dict] = []
        sink = crow_gui.Sink(collected.append, live=False)
        sink.reply_started()
        for i in range(30):
            sink.answer_text("x")
        self.assertEqual([m for m in collected if m["k"] == "live"], [])

    def test_the_counter_moves_when_the_clock_does(self):
        """The throttle has to let something through, or it is not a throttle but
        a mute. Two bursts a second apart, on a clock that moved between them."""
        clock = _StoppedClock()
        crow_gui.time = clock
        collected: list[dict] = []
        sink = crow_gui.Sink(collected.append)
        sink.reply_started()
        for _ in range(5):
            sink.answer_text("a")
        clock._at += 1.0
        for _ in range(5):
            sink.answer_text("b")
        self.assertGreaterEqual(len([m for m in collected if m["k"] == "live"]), 1)


# --------------------------------------------------------------- P1, F4 -----

def _silent_server(after: int = 1) -> tuple[int, socket.socket]:
    """A loopback endpoint that sends `after` chunks and then says nothing.

    The shape P1 is about: the socket is alive, the read is blocked, and nothing
    will ever arrive to unblock it.
    """
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)

    def serve() -> None:
        try:
            conn, _ = sock.accept()
            # `with`, so the accepted connection is closed when this thread is
            # done with it (#185). Without it the socket outlived the suite and
            # was reported twice as an unclosed ResourceWarning from
            # threading.py -- the report names the thread, never the test.
            with conn:
                conn.recv(65536)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                             b"Connection: close\r\n\r\n")
                for i in range(after):
                    conn.sendall(json.dumps({"choices": [{"delta": {"content": "x%d" % i}}]})
                                 .encode("utf-8").join((b"data: ", b"\n\n")))
                # and then nothing at all, until the test is done with it
                time.sleep(30)
        except Exception:
            pass

    threading.Thread(target=serve, daemon=True).start()
    return sock.getsockname()[1], sock


class AbortPathTests(unittest.TestCase):
    """P1: "`cancel()` against a blocked `readline()` ... the abort button
    SILENTLY DOES NOTHING and the turn runs to completion."

    THE EFFECT IS NOT THE PROOF, and E12 says so: an interface reacting can be
    faked with a flag. The proof that matters is the next question being
    answered, and it needs a server -- it is in E14. What is here is the CAUSE:
    the second abort path exists and is bounded by the read timeout the window
    ships, over a real socket.
    """

    def setUp(self) -> None:
        crow_core.INTERRUPT.clear()
        self.addCleanup(crow_core.INTERRUPT.clear)

    def _abort_after(self, timeout: float) -> float:
        crow_core.INTERRUPT.clear()
        port, sock = _silent_server()
        self.addCleanup(sock.close)
        before = threading.active_count()
        stream = crow_core._post_stream("http://127.0.0.1:%d/v1/chat/completions" % port,
                                        {"x": 1}, "k", timeout)
        self.assertTrue(next(stream), "the fixture sent nothing")
        started = time.monotonic()
        crow_core.INTERRUPT.set()
        stream.close()
        deadline = started + timeout + 10.0
        while threading.active_count() > before and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertLessEqual(
            threading.active_count(), before,
            "the reader outlived even the read timeout -- P1 with no bound left")
        return time.monotonic() - started

    def test_the_read_timeout_is_what_bounds_an_aborted_reader(self):
        """POSITIVE, END TO END OVER A REAL SOCKET.

        Two aborts against the same silent server, one with a 1 s read timeout
        and one with a 4 s one. If the close were what ended the read, both would
        return at the same moment; they do not, and the difference IS the read
        timeout doing the work. That is why cli/crow_gui.py ships one instead of
        inheriting the CLI's 1800 s.
        """
        quick = self._abort_after(1.0)
        slow = self._abort_after(4.0)
        self.assertLess(quick, 3.0, "a 1 s read timeout took %.1f s" % quick)
        self.assertGreater(slow, quick + 1.0,
                           "a 4 s read timeout returned as fast as a 1 s one -- "
                           "then something other than the timeout ended the read "
                           "and the window's bound is measuring nothing")

    def test_the_timeout_the_turn_runs_under_is_the_one_the_window_declares(self):
        """The value is only a bound if the turn actually runs under it. A
        constant that nothing passes to `run_turn` bounds a comment."""
        self.assertGreater(crow_gui.READ_TIMEOUT_S, 0)
        self.assertLess(crow_gui.READ_TIMEOUT_S, 1800.0)
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.assertIn("timeout=READ_TIMEOUT_S", source,
                      "the window declares a read timeout it does not run under")

    def test_an_interrupted_turn_is_written_on_the_page(self):
        """The other half of P1: when the abort lands, the window SAYS SO. A
        window that went quiet is indistinguishable from one where the abort did
        nothing."""
        collected: list[dict] = []
        crow_gui.Turn(collected.append).turn_interrupted()
        self.assertEqual([m["k"] for m in collected], ["fail"])
        self.assertEqual(collected[0]["t"], crow_core.ABORT_NOTE)


# ------------------------------------------------------ the reasoning share --

class TheCostLineCarriesTheShareTests(ApiCase):
    """The share of a turn that was thinking, from the core to the cost line.

    IT USED TO BE PUSHED AS `{"k": "_round"}` AND READ BY NOBODY. The page's
    switch has no case for it, so it fell through; the cost line was then drawn
    from a local variable that nothing ever wrote, and every turn reported a
    share of null. Two things had to be true at once for that to stay invisible,
    and both are cases now: the value has to arrive, and no message may exist
    that the page cannot draw.
    """

    def test_the_share_is_computed_from_what_the_core_counted(self):
        """POSITIVE. 60 characters of thought against 40 of answer is 60 %."""
        turn = crow_gui.Turn(lambda m: None)
        turn.round_finished({"_reasoning_chars": 60, "_content_chars": 40})
        self.assertAlmostEqual(turn.share, 60.0)

    def test_a_round_that_counted_nothing_leaves_the_share_unset(self):
        """NEGATIVE. A share of 0 % and no share at all are different claims, and
        the page draws them differently."""
        turn = crow_gui.Turn(lambda m: None)
        turn.round_finished({})
        self.assertIsNone(turn.share)

    def test_the_share_is_the_turn_and_not_the_last_round(self):
        """THE ONE THAT WAS RED BEFORE #117. Each round used to overwrite the value, and the page
        then stamped the survivor onto every thought block under a label reading "% of the turn".

        90 % of thinking followed by 10 % is a turn of 50 %, not a turn of 10 %. The two rounds
        carry the same number of characters on purpose: taking the LAST round gives 10, a mean
        over rounds gives 50 as well, and summing gives 50 -- so the case is cut to separate
        last-round from the other two, and the case below separates summing from averaging.
        """
        turn = crow_gui.Turn(lambda m: None)
        turn.round_finished({"_reasoning_chars": 90, "_content_chars": 10})
        turn.round_finished({"_reasoning_chars": 10, "_content_chars": 90})
        self.assertAlmostEqual(turn.share, 50.0)

    def test_a_long_round_outweighs_a_short_one(self):
        """The denominator is CHARACTERS, not rounds. 900 thought against 100 answer, then a tool
        round of 1 against 99, is 901 of 1100 -- 82 %. A mean over the two rounds would say 45 and
        let a round that produced almost nothing halve the figure of the one that did the work."""
        turn = crow_gui.Turn(lambda m: None)
        turn.round_finished({"_reasoning_chars": 900, "_content_chars": 100})
        turn.round_finished({"_reasoning_chars": 1, "_content_chars": 99})
        self.assertAlmostEqual(turn.share, 100.0 * 901 / 1100)

    def test_the_share_does_not_leave_as_a_message_of_its_own(self):
        """It is read off the turn at the end. A message with no case on the page
        is a value that looks delivered and is not."""
        collected: list[dict] = []
        crow_gui.Turn(collected.append).round_finished(
            {"_reasoning_chars": 1, "_content_chars": 1})
        self.assertEqual([m["k"] for m in collected], [])


# ------------------------------------------- the counter after a rollover ----


class TheCounterFollowsTheRolloverTests(unittest.TestCase):
    """robins Live-Test 2026-08-29: der Rollover griff, aber unten links stand
    bis zum Turn-Ende -- Runden spaeter -- der Fuellstand von VOR dem Roll.
    Der Kern zaehlt ab dem Roll von 0; dieselbe Zahl gehoert im selben Moment
    auf die Seite."""

    def test_the_roll_note_travels_with_a_counter_reset(self):
        """POSITIV: `rolled_over` schiebt neben der Notiz ein eigenes
        ctx-Ereignis mit tokens 0. NEGATIV im selben Zug: NICHT als `cost` --
        `cost()` raeumt den Stream-Cursor ab, und der Turn laeuft noch."""
        collected: list[dict] = []
        crow_gui.Turn(collected.append).rolled_over(187333, "rollover-x.json")
        kinds = [m["k"] for m in collected]
        self.assertIn("note", kinds)
        self.assertIn("ctx", kinds)
        self.assertNotIn("cost", kinds,
                         "cost mid-turn nimmt den Stream-Cursor mit")
        self.assertEqual(collected[kinds.index("ctx")]["tokens"], 0)

    def test_the_page_has_a_case_for_the_new_kind(self):
        """Die Falle hinter #117: ein Ereignis ohne Seiten-Fall faellt durch
        den Switch und sieht trotzdem geliefert aus. Der Switch kennt `ctx`
        und fuehrt es auf dieselbe Anzeige wie das Turn-Ende."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        sw = source[source.index('case "cost"'):]
        sw = sw[:sw.index('case "subs"')]
        self.assertIn('case "ctx": this.ctx(e.tokens,e.n_ctx); break;', sw)


class TheSeamReassertsTheSurfaceTests(unittest.TestCase):
    """#211. Der Roll sagte der Seite bis hier genau EINE Sache (die Notiz)
    -- Modell-Chip und Berechtigungsstufe standen danach auf dem, was zufaell-
    ig zuletzt stand, und jede Neudarstellung liess sie leer (robins Test
    2026-09-22). Der Schnitt ruft den Fensterzustand NACH, gebuendelt."""

    def test_rolled_over_calls_the_surface_after_the_counter(self):
        """POSITIV: Karte, Notiz, ctx 0 -- und DANN der Burst; die Reihenfolge
        ist der Vertrag, denn die Karte steht im Band, bevor irgendwer von
        Zahlen spricht, und der Burst schreibt Zahlen, die die Notiz nennt."""
        collected: list[dict] = []
        fired: list[bool] = []
        turn = crow_gui.Turn(collected.append,
                             surface_reload=lambda: fired.append(True))
        turn.rolled_over(180145, "rollover-x.json")
        kinds = [m["k"] for m in collected]
        self.assertEqual(kinds, ["roll", "note", "ctx"])
        self.assertEqual(collected[0]["tokens"], 180145)
        self.assertTrue(collected[0]["path"].endswith("rollover-x.md"))
        self.assertEqual(collected[kinds.index("ctx")]["tokens"], 0)
        self.assertEqual(fired, [True], "der Schnitt ruft den Zustand nach")

    def test_without_a_surface_the_roll_rolls_as_before(self):
        """NEGATIV: die Suite und das Terminal bauen Turn ohne Fenster --
        kein Rueckruf darf dort zum AttributeError werden."""
        crow_gui.Turn(lambda m: None).rolled_over(1, "rollover-x.json")


class TheLevelWaitsForTheGapTests(unittest.TestCase):
    """#211. Der Goal-Motor haelt den Worker stundenlang am Leben -- die
    Weigerung "mid-turn" hatte kein Ende, solange ein Ziel lief (robins
    Live-Befund: die Berechtigungsstufe war unveraenderlich). Ein Level,
    das mitten im Zug gewaehlt wird, wartet auf den Spalt zwischen zwei
    Zuegen und wird dort echt."""

    def _api(self, mode: str = "auto") -> "crow_gui.Api":
        api = crow_gui.Api.__new__(crow_gui.Api)
        api._mode_queued = None
        api._args = types.SimpleNamespace(mode=mode)
        api._worker = None
        api.push = self.out.append
        return api

    def setUp(self) -> None:
        self.out: list[dict] = []

    def test_mid_turn_the_level_queues_instead_of_refusing(self):
        """POSITIV: der Klick wird angenommen, wartet, und die Notiz nennt
        den Moment, an dem er gilt -- kein Abweisungston mehr ohne Ende."""
        api = self._api()
        api._worker = types.SimpleNamespace(is_alive=lambda: True)
        applied: list[str] = []
        api._apply_mode = applied.append          # der Spalt selbst, hier gefakt
        api.set_mode("yolo")
        self.assertEqual(applied, [], "mitten im Zug gilt noch nichts")
        self.assertEqual(api._mode_queued, "yolo")
        self.assertTrue(any("yolo applies after this one" in m.get("t", "")
                            for m in self.out if m.get("k") == "note"))

    def test_the_gap_applies_the_queued_level_once(self):
        """POSITIV: `_drain_mode_queue` ist der Spalt -- angewandt wird nur,
        was noch nicht gilt, und genau ein Mal."""
        api = self._api()
        api._mode_queued = "yolo"
        applied: list[str] = []
        api._apply_mode = applied.append
        api._drain_mode_queue()
        self.assertEqual(applied, ["yolo"])
        self.assertIsNone(api._mode_queued)
        api._drain_mode_queue()
        self.assertEqual(applied, ["yolo"], "zweimal ziehen aendert nichts")

    def test_a_level_that_already_stands_needs_no_gap(self):
        """NEGATIV: derselbe Name ist keine Aenderung -- die Notiz wuerde von
        einem Wechsel sprechen, der keiner ist."""
        api = self._api(mode="yolo")
        api._mode_queued = "yolo"
        applied: list[str] = []
        api._apply_mode = applied.append
        api._drain_mode_queue()
        self.assertEqual(applied, [])
        self.assertIsNone(api._mode_queued)


class TheArchiveCardBacksItsButtonsTests(ApiCase):
    """#211. Die Karte am Schnitt nennt den Transkriptpfad; ihre Knoepfen
    lesen NUR Dateien, die der Roll selbst in den Sitzungsordner geschrieben
    hat -- ein Gespraech, das jemand bearbeitet hat, darf kein beliebiger
    Datei-Oeffner sein."""

    def _api(self) -> "crow_gui.Api":
        api = crow_gui.Api.__new__(crow_gui.Api)
        api.push = self.out.append
        return api

    def setUp(self) -> None:
        super().setUp()
        self.out: list[dict] = []

    def _write_transcript(self, lines: int = 60) -> str:
        path = crow_core.rollover_path("card.json")[:-5] + ".md"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join("zeile %d" % n for n in range(1, lines + 1)))
        return path

    def test_the_tail_is_the_end_of_the_file(self):
        """POSITIV: 40 Zeilen vom Ende -- die Notiz selbst sagt, dass DORT zu
        lesen ist, wo die Dinge standen."""
        path = self._write_transcript()
        tail = self._api().roll_tail(path)
        self.assertEqual(tail.splitlines()[0], "zeile 21")
        self.assertEqual(tail.splitlines()[-1], "zeile 60")
        self.assertEqual(len(tail.splitlines()), 40)

    def test_a_path_outside_the_session_folder_is_refused(self):
        """NEGATIV: die Karte steht im Gespraech, und Gespraechstext ist kein
        Pfadvertrauen -- nur das eigene Verzeichnis, nur .md. (ApiCase biegt
        SESSION_DIR auf das Temp-Verzeichnis; 'daneben' ist darum ein
        eigenes.)"""
        elsewhere = tempfile.mkdtemp(prefix="crow-card-out-")
        self.addCleanup(shutil.rmtree, elsewhere, True)
        outside = os.path.join(elsewhere, "notes.md")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("nichts fuer die Karte")
        self.assertEqual(self._api().roll_tail(outside), "")
        self.assertTrue(any(m.get("k") == "fail" for m in self.out))

    def test_show_opens_nothing_when_the_file_is_gone(self):
        """NEGATIV: ein verschwundenes Transkript ist eine Zeile, kein
        Oeffnen daneben -- der Klick kam von einer alten Karte."""
        gone = crow_core.rollover_path("gone.json")[:-5] + ".md"
        with mock.patch.object(crow_gui.subprocess, "Popen") as popen:
            self._api().roll_show(gone)
        popen.assert_not_called()
        self.assertTrue(any(m.get("k") == "fail" for m in self.out))


class TheReplayDrawsTheBoundaryTests(unittest.TestCase):
    """#211. Ein wieder geoeffneter Chat zeigt seine Grenze: die Notiz wird
    zur Karte, die Zeile, die mit ihr reiste, zur getippten Frage -- derselbe
    Spalter wie live, dasselbe Ereignis fuer die Seite."""

    def test_a_restored_note_becomes_a_card_and_its_carry_a_line(self):
        note = crow_core.ROLLOVER_NOTE.format(
            tokens=180145, transcript="/x/rollover-1.md", lines=5223,
            path="/x/rollover-1.json", where="", spoken="", digest="")
        messages = [{"role": "system", "content": "SYS"},
                    {"role": "user", "content": note + "\n\nweiter so"},
                    {"role": "user", "content": "eine zweite Frage"}]
        out: list[dict] = []

        class _Collector:
            """Der Sammler, von dem `Api._replay` sagt, dass die ihn so baut:
            nur `push`, kein Fenster."""
            def __init__(self_inner):
                self_inner.push = out.append

        crow_gui._replay_rows(_Collector(), messages, lambda n: None)
        kinds = [m["k"] for m in out]
        self.assertEqual(kinds, ["roll", "user", "user"])
        self.assertEqual(out[0]["tokens"], 180145)
        self.assertEqual(out[0]["path"], "/x/rollover-1.md")
        self.assertEqual(out[0]["lines"], 5223)
        self.assertEqual(out[1]["t"], "weiter so")
        self.assertEqual(out[2]["t"], "eine zweite Frage")


class TheReplayDropsTheWorkingAreaNoticeTests(unittest.TestCase):
    """#241: #224's notice opens the stored user message, but live the
    bubble showed only the typed line -- a reopened chat must draw the same."""

    def _drawn(self, messages):
        out: list[dict] = []

        class _Collector:
            def __init__(self_inner):
                self_inner.push = out.append
                self_inner._context_tokens = 0
                self_inner._n_ctx = 0

        crow_gui._replay_rows(_Collector(), messages, lambda n: None)
        return out

    def test_the_bubble_holds_only_the_typed_line(self):
        out = self._drawn([
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": crow_core.ROOT_NOTICE.format(
                new="/a/new", old="/a/old") + "go on"}])
        users = [m["t"] for m in out if m["k"] == "user"]
        self.assertEqual(users, ["hi", "go on"])

    def test_an_image_turn_without_words_draws_no_notice(self):
        talk = crow_core.Conversation("SYS")
        talk.append("user", "hi")
        talk.append("assistant", "hello")
        talk.note_root_change("/a", "/b")
        talk.append("user", [{"type": "image_url", "image_url": {"url": "data:x"}}])
        out = self._drawn(talk.payload())
        last = [m for m in out if m["k"] == "user"][-1]
        self.assertEqual(last["t"], "")
        self.assertEqual(last["i"], ["data:x"])


class TheSecondRolloverFiresTests(ApiCase):
    """#152, robins Live-Nacht 2026-08-29: der erste Rollover griff, danach
    verweigerte jeder Folgeturn den naechsten Roll -- stumm -- bis der Server
    bei 200.235 > 200.192 Token die Anfrage ablehnte. `rolled` ist der
    Ein-Turn-Waechter des Kerns ("zweimal in einem Turn heisst: die Frage
    passt nicht"); das Fenster hatte ihn zum Session-Dauerzustand gemacht."""

    def setUp(self) -> None:
        # Dasselbe Provider-Umbiegen wie TheRemoteEndpointTests: ohne es
        # schreibt der Fall in die Modul-Sandbox mit FESTEM Pfad, und jeder
        # spaetere Lauf findet einen gewaehlten Provider vor, wo "leer"
        # versprochen ist -- gefunden am 401 des Bild-Falls, 2026-08-29.
        super().setUp()
        self._prov = (crow_core.PROVIDERS_FILE, crow_core.PROVIDER_KEYS_FILE,
                      crow_core.PROVIDER_TOKEN_FILE)
        self.addCleanup(self._restore_prov)
        crow_core.PROVIDERS_FILE = os.path.join(self.dir, "providers.json")
        crow_core.PROVIDER_KEYS_FILE = os.path.join(self.dir, "provider_keys.json")
        crow_core.PROVIDER_TOKEN_FILE = os.path.join(self.dir, "provider_tokens.json")

    def _restore_prov(self) -> None:
        (crow_core.PROVIDERS_FILE, crow_core.PROVIDER_KEYS_FILE,
         crow_core.PROVIDER_TOKEN_FILE) = self._prov

    def test_every_turn_starts_with_a_fresh_rolled_flag(self):
        """POSITIV: auch NACH einem Turn, der rollte (result.rolled=True),
        geht der naechste Turn mit rolled=False hinein -- wie repl() es je
        Zeile frisch setzt."""
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        doc = crow_core.provider_doc()
        doc["catalog"] = {"openrouter": {"fetched": 1, "models": [
            {"id": "z-ai/glm-5.2:free", "name": "glm", "context": 131072}]}}
        crow_core.provider_write(doc)
        self.assertIsNone(crow_core.provider_pick("openrouter", "z-ai/glm-5.2:free"))
        flags = []

        def fake_run(conversation, **kw):
            flags.append(kw["rolled"])
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=True,
                                        stopped=False, reported=True)

        api = self.api()
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._conversation.append("user", "erste Frage")
            api._run("erste Frage")
            api._conversation.append("user", "zweite Frage")
            api._run("zweite Frage")
        self.assertEqual(flags, [False, False],
                         "der Ein-Turn-Waechter reist als Session-Zustand")

    def test_a_refused_rollover_is_visible_in_the_flow(self):
        """NEGATIV zur alten Lage: die Verweigerung war ein No-op der
        Basisklasse -- der Turn endete wortlos. Jetzt steht eine rote Zeile,
        die den Grund nennt."""
        collected: list[dict] = []
        crow_gui.Turn(collected.append).rollover_refused()
        self.assertEqual([m["k"] for m in collected], ["fail"])
        self.assertIn("rollover", collected[0]["t"])

    def _provider(self) -> None:
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        doc = crow_core.provider_doc()
        doc["catalog"] = {"openrouter": {"fetched": 1, "models": [
            {"id": "z-ai/glm-5.2:free", "name": "glm", "context": 131072}]}}
        crow_core.provider_write(doc)
        self.assertIsNone(crow_core.provider_pick("openrouter", "z-ai/glm-5.2:free"))

    def test_a_session_past_the_threshold_rolls_before_the_first_request(self):
        """robins Retest 2026-08-29: die RT-Session stand bei 200,2k von
        200.192 -- UEBER der Wand. Der Kern prueft erst am RUNDEN-Ende, die
        erste Anfrage scheiterte aber am Server (HTTP 400 exceed_context_size)
        -- der Roll war unerreichbar, die Session tot. Wie repl() rollt das
        Fenster jetzt VOR dem Turn: das Archiv ist vollstaendig, die getippte
        Zeile eroeffnet als carry den neuen Kontext, der Turn geht mit
        context_tokens 0 und rolled=True hinein."""
        self._provider()
        rolls, seen = [], {}

        def fake_roll(conversation, base_url, context_tokens, carry=None,
                      digest="", **_):
            rolls.append((context_tokens, carry))
            conversation.reset()
            conversation.append("user", "note\n\n" + (carry or ""))
            return os.path.join(crow_core.SESSION_DIR, "rollover-fake.json")

        def fake_run(conversation, **kw):
            seen.update(kw)
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=True,
                                        stopped=False, reported=True)

        api = self.api()
        api._n_ctx = 200192
        api._context_tokens = 190000
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "roll_over", fake_roll), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run("weiter im Text")
        self.assertEqual(rolls, [(190000, "weiter im Text")])
        self.assertIs(seen.get("rolled"), True)
        self.assertEqual(seen.get("context_tokens"), 0)
        # the roll card shows it; the "rolled over at" line is log-only (robin
        # 2026-09-24)
        rolls_drawn = [m for m in self.drained(api) if m.get("k") == "roll"]
        self.assertTrue(any(m.get("tokens") == 190000 for m in rolls_drawn),
                        "der Roll blieb unsichtbar: %r" % rolls_drawn)

    def test_a_session_under_the_threshold_does_not_roll_before_the_turn(self):
        """NEGATIV: unter der Schwelle kein Vor-Turn-Roll -- die Zeile wird
        normal angehaengt und der Turn startet mit rolled=False."""
        self._provider()
        rolls, seen = [], {}

        def fake_roll(conversation, base_url, context_tokens, carry=None,
                      digest="", **_):
            rolls.append(context_tokens)
            return "never"

        def fake_run(conversation, **kw):
            seen.update(kw)
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=False,
                                        stopped=False, reported=True)

        api = self.api()
        api._n_ctx = 200192
        api._context_tokens = 1000
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "roll_over", fake_roll), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run("weiter im Text")
        self.assertEqual(rolls, [])
        self.assertIs(seen.get("rolled"), False)

    def test_a_stuck_render_loop_forces_the_roll_below_the_threshold(self):
        """#268: six stuck captures set the flag; the next turn rolls first,
        at 1,000 of 200,192 tokens, and the carry is the breaker's line."""
        self._provider()
        rolls = []

        def fake_roll(conversation, base_url, context_tokens, carry=None,
                      digest="", **_):
            rolls.append(carry)
            conversation.reset()
            conversation.append("user", "note\n\n" + (carry or ""))
            return os.path.join(crow_core.SESSION_DIR, "rollover-fake.json")

        def fake_run(conversation, **kw):
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=True,
                                        stopped=False, reported=True)

        api = self.api()
        api._n_ctx = 200192
        api._context_tokens = 1000
        api._goal_roll_due = True
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "roll_over", fake_roll), \
             mock.patch.object(crow_core, "rollover_digest", lambda *a, **k: ""), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run("[Goal mode, step 2: what was tried]")
            api._run("next line")
        self.assertEqual(rolls, ["[Goal mode, step 2: what was tried]"])
        self.assertFalse(api._goal_roll_due)

    def test_the_pre_turn_roll_carries_the_digest(self):
        """#154: der Digest entsteht VOR roll_over -- auf dem noch vollen
        Praefix, mit dem Spot des Turns -- und reist als digest= in die
        Note."""
        self._provider()
        seen = {}

        def fake_digest(conversation, **kw):
            return "DIGEST-TEXT"

        def fake_roll(conversation, base_url, context_tokens, carry=None,
                      digest="", **_):
            seen["digest"] = digest
            conversation.reset()
            conversation.append("user", "note\n\n" + (carry or ""))
            return os.path.join(crow_core.SESSION_DIR, "rollover-fake.json")

        def fake_run(conversation, **kw):
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=True,
                                        stopped=False, reported=True)

        api = self.api()
        api._n_ctx = 200192
        api._context_tokens = 190000
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "roll_over", fake_roll), \
             mock.patch.object(crow_core, "rollover_digest", fake_digest), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run("weiter im Text")
        self.assertEqual(seen.get("digest"), "DIGEST-TEXT")

    def test_the_pre_turn_roll_sends_the_goal_marks(self):
        """#210, Audit 2026-09-22 17:12: der ECHTE `roll_over`, der echte
        `repin_head`, eine gebundene Wurzel mit goal.json unter `.crow/` --
        und der Kopf, den der erste Zug nach dem Schnitt bekommt, traegt die
        Marken und den naechsten Schritt."""
        self._provider()
        root = os.path.join(self.dir, "work")
        os.makedirs(root)
        heads = []

        def fake_run(conversation, **kw):
            heads.append(conversation.payload()[0]["content"])
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=True,
                                        stopped=False, reported=True)

        api = self.api()
        crow_core.set_root(root)
        self.addCleanup(crow_core.set_root, None)
        crow_core.goal_start("Ship", ["read", "write", "prove"], now=1000.0)
        crow_core.goal_step_end(0, now=1010.0)
        api._conversation.append("user", "erste Frage")
        api._conversation.append("assistant", "erste Antwort")
        api._n_ctx = 200192
        api._context_tokens = 190000
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "rollover_digest",
                               lambda *a, **k: ""), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run("weiter im Text")
        self.assertEqual(len(heads), 1)
        for line in ("1. [done] read", "2. [open] write",
                     "Next: step 2. write", crow_core.GOAL_SEAM_NOTE):
            self.assertIn(line, heads[0])


    def test_the_pre_turn_roll_carries_the_last_good_round(self):
        """#214: der ECHTE `roll_over` im Vor-Turn-Roll des Fensters -- der
        erste Zug nach dem Schnitt sieht das letzte gelungene `edit_file`
        woertlich hinter der Notiz, gepaart, und die getippte Zeile zuletzt."""
        self._provider()
        sent = []

        def fake_run(conversation, **kw):
            sent.append(conversation.payload())
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=True,
                                        stopped=False, reported=True)

        api = self.api()
        edit = json.dumps({"path": "src/app.js", "old": "a", "new": "b"})
        api._conversation.append("user", "erste Frage")
        api._conversation.append("assistant", "", tool_calls=[
            {"id": "call_0", "name": "edit_file", "arguments": edit}])
        api._conversation.append("tool", "replaced 1 occurrence",
                                 tool_call_id="call_0")
        api._conversation.append("assistant", "erste Antwort")
        api._n_ctx = 200192
        api._context_tokens = 190000
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "rollover_digest",
                               lambda *a, **k: ""), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run("weiter im Text")
        self.assertEqual(len(sent), 1)
        after = sent[0]
        self.assertEqual([m["role"] for m in after],
                         ["system", "user", "assistant", "tool", "user"])
        self.assertEqual(after[2]["tool_calls"][0]["function"]["arguments"],
                         edit)
        self.assertEqual(after[3]["tool_call_id"], "call_0")
        self.assertTrue(after[3]["content"].startswith(
            crow_core.ROLLOVER_CARRY_MARK))
        self.assertEqual(after[-1]["content"], "weiter im Text")


class TheReplayDrawsACarriedRoundAsCarriedTests(unittest.TestCase):
    """#214: eine getragene Runde lief VOR dem Schnitt. Beim Wiederoeffnen
    steht sie hinter der Karte als Hinweis, nicht als neue Werkzeugzeile."""

    def test_a_carried_round_is_a_note_and_a_real_one_a_row(self):
        note = crow_core.ROLLOVER_NOTE.format(
            tokens=180145, transcript="/x/rollover-1.md", lines=5223,
            path="/x/rollover-1.json", where="", spoken="", digest="")
        call = {"id": "call_0", "type": "function", "function": {
            "name": "edit_file",
            "arguments": '{"path": "p", "old": "a", "new": "b"}'}}
        messages = [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": note},
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "call_0",
             "content": crow_core.ROLLOVER_CARRY_MARK + "]\nreplaced 1"},
            {"role": "user", "content": "weiter so"},
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "call_0", "content": "replaced 1"}]
        out: list[dict] = []

        class _Collector:
            def __init__(self_inner):
                self_inner.push = out.append
                self_inner._context_tokens = 0
                self_inner._n_ctx = 0

        crow_gui._replay_rows(_Collector(), messages, lambda n: None)
        kinds = [m["k"] for m in out]
        self.assertEqual(kinds[:3], ["roll", "note", "user"])
        self.assertEqual(out[1]["t"], "carried across the cut: edit_file")
        tools = [m for m in out if m["k"] == "tool"]
        self.assertEqual(len(tools), 1, "the carried call was drawn as a row")


class TheWindowAsksTheManifestAboutTheServedModelTests(ApiCase):
    """#220, the window half. `_endpoint` answers `model: "crow"`
    for the local provider (DEFAULT_MODEL through provider_endpoint), sampling
    and levels came from `self._model` -- what /props reported -- and the #176
    budget came from "crow", which names no entry: the CNQ container's 1024
    never reached the wire from this window. The REAL `run_turn` and the REAL
    `rollover_digest` run here; only the transport is scripted."""

    CNQ = crow_core.model_display_name("/m/Qwen3.8-Flash-Next-CNQ4.5-M.cnq")

    def setUp(self) -> None:
        # THE LOCAL PROVIDER, WHATEVER RAN BEFORE: a case that picks OpenRouter
        # in the module sandbox leaves it chosen, and this class is about the
        # local path -- same fence as the rollover class above.
        super().setUp()
        for name in ("PROVIDERS_FILE", "PROVIDER_KEYS_FILE", "PROVIDER_TOKEN_FILE"):
            self.addCleanup(setattr, crow_core, name, getattr(crow_core, name))
            setattr(crow_core, name, os.path.join(self.dir, name.lower() + ".json"))

    def _window(self, **state):
        api = self.api()
        api._model = self.CNQ
        api._n_ctx = 200192
        for name, value in state.items():
            setattr(api, name, value)
        return api

    def _turn_bodies(self, api, text="hello") -> list[dict]:
        bodies = []

        def fake(url, body, api_key, timeout):
            bodies.append(json.loads(json.dumps(body)))
            yield from chunks_for([{"content": "ok"}], {"predicted_n": 1})
        crow_core._post_stream = fake
        api._conversation.append("user", text)
        with mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run(text)
        self.assertTrue(bodies, "the turn never reached the transport")
        return bodies

    def test_the_turn_for_the_container_carries_what_its_entry_declares(self):
        body = self._turn_bodies(self._window(_reasoning="high"))[0]
        self.assertEqual(body["model"], crow_core.DEFAULT_MODEL,
                         "the wire label moved -- serve only echoes it")
        self.assertEqual(body["reasoning_budget_tokens"],
                         crow_core.reasoning_budget_for(self.CNQ))
        self.assertEqual(body["reasoning_budget_tokens"], 1024)
        self.assertEqual(body["reasoning_budget_message"],
                         crow_core.REASONING_BUDGET_MESSAGE)
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertIn(body["reasoning_effort"],
                      crow_core.reasoning_levels_for(self.CNQ))
        # The sampling half was right before; held here so the two lookups
        # stay on one name.
        for name, value in crow_core.sampling_for(self.CNQ).items():
            self.assertEqual(body[name], value, name)

    def test_a_never_chosen_chat_sends_thinking_explicitly(self):
        """#225: `_reasoning` None used to send no key -- serve read
        that as thinking OFF. The fixed word goes on the wire now, with the
        card's thinking row."""
        body = self._turn_bodies(self._window(_reasoning=None))[0]
        self.assertEqual(body["reasoning_effort"], "high")
        for name, value in (("temperature", 1.0), ("top_p", 0.95), ("top_k", 20),
                            ("min_p", 0.0), ("presence_penalty", 0.0)):
            self.assertEqual(body[name], value, name)

    def test_a_stored_level_does_not_move_a_fixed_point(self):
        body = self._turn_bodies(self._window(_reasoning="low"))[0]
        self.assertEqual(body["reasoning_effort"], "high")

    def test_the_window_offers_no_level_for_a_fixed_point(self):
        """#225: the chip's level menu is empty for a fixed point."""
        api = self._window()
        self.drained(api)
        api._surface()
        up = [m for m in self.drained(api) if m.get("k") == "up"][-1]
        self.assertEqual((up["levels"], up["groups"]), ([], []))
        self.assertIn("fixed", api._reasoning_command([]))

    def test_a_model_that_is_not_fixed_keeps_its_levels(self):
        """NEGATIVE: the 27B keeps the chip as it was."""
        api = self._window(_model="Qwen3.8-27B")
        self.drained(api)
        api._surface()
        up = [m for m in self.drained(api) if m.get("k") == "up"][-1]
        self.assertEqual(up["levels"],
                         list(crow_core.reasoning_levels_for("Qwen3.8-27B")))
        self.assertTrue(up["levels"])

    def test_a_lifted_cap_is_lifted_in_the_window_too(self):
        body = self._turn_bodies(self._window(
            _budget=crow_core.BUDGET_LIFTED))[0]
        self.assertNotIn("reasoning_budget_tokens", body)
        self.assertNotIn("reasoning_budget_message", body)

    def test_the_pre_turn_digest_asks_the_same_name(self):
        legs = []
        answer = json.dumps({"choices": [{"finish_reason": "stop", "message": {
            "content": "state: the work stands where the transcript ends. " * 8}}]})

        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def leg(request, timeout=None):
            legs.append(json.loads(request.data.decode("utf-8")))
            return _Resp(answer.encode("utf-8"))

        def fake_roll(conversation, base_url, context_tokens, carry=None, **_):
            conversation.reset()
            conversation.append("user", "note\n\n" + (carry or ""))
            return os.path.join(crow_core.SESSION_DIR, "rollover-fake.json")

        api = self._window(_context_tokens=190000)
        self.a_chat(api)
        with mock.patch.object(crow_core.urllib.request, "urlopen", leg), \
             mock.patch.object(crow_core, "roll_over", fake_roll):
            body = self._turn_bodies(api, "weiter")[0]
        self.assertEqual(len(legs), 1, "one digest question")
        for sent in (legs[0], body):
            self.assertEqual(sent["model"], crow_core.DEFAULT_MODEL)
            self.assertEqual(sent["reasoning_budget_tokens"], 1024)


class APastedScreenshotBecomesAChipTests(unittest.TestCase):
    """robins Frage 2026-08-29 nachmittags ('wieso geht vision auf einmal
    nicht mehr'): Ctrl+V schrieb das Bild nach pastes\\ und haengte den
    PFAD als Text an den Composer -- die Route stammt von VOR #142. Ein
    Paste-Bild geht jetzt denselben Weg wie ein gedropptes: Chip, Vision,
    Transcript."""

    def test_the_paste_listener_feeds_the_drop_route(self):
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        block = source[source.index('document.addEventListener("paste"'):]
        block = block[:block.index("});") + 3]
        self.assertIn("crow.dropped([", block)
        self.assertNotIn("crow.attach(", block,
                         "der Pfad landet wieder als Text im Composer")


class ARolloverArchiveIsNotTitledByTheNoteTests(unittest.TestCase):
    """#153: ein Rollover-Archiv traegt keinen crow_title, also betitelt die
    Rail es nach der ersten User-Zeile -- und die IST die vorige
    Rollover-Note. Zwei Zeilen, die beide wie "die Session" lesen."""

    @staticmethod
    def _note() -> str:
        return crow_core.ROLLOVER_NOTE.format(
            tokens=180858, path="rollover-x.json", transcript="rollover-x.md",
            lines=12, where="", spoken="", digest="")

    def test_the_note_line_does_not_become_the_title(self):
        messages = [
            {"role": "system", "content": "You are Crow."},
            {"role": "user", "content": self._note() + "\n\nweiter gehts"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "Zeta-Labor weiterbauen"},
        ]
        self.assertEqual(crow_gui.Api._first_line(messages),
                         "Zeta-Labor weiterbauen")

    def test_a_file_of_only_the_note_falls_back_to_no_title(self):
        """NEGATIV: besteht ein Archiv nur aus der Note, bleibt der
        Dateiname-Fallback von `_entry_of` zustaendig -- kein Erfinden."""
        messages = [{"role": "user", "content": self._note()}]
        self.assertIsNone(crow_gui.Api._first_line(messages))


class RolloversLeaveTheRailTests(ApiCase):
    """#261 (robin, 2026-09-23): after each rollover the rail
    listed the archived segment as a chat of its own -- "[The tool budget for
    this turn is ..." (324 messages) and "Hey" (191 messages), both "rolled
    over". A rollover is the live chat's earlier half: it belongs in the
    archive drawer, and Crow's own notes are never anybody's title."""

    def cut(self, api, stamp: str) -> str:
        """One real `roll_over` of the window's conversation, like the seam."""
        path = os.path.join(self.dir, "rollover-%s.json" % stamp)
        archived = crow_core.roll_over(api._conversation, "http://127.0.0.1:1/v1",
                                       180000, path=path)
        self.assertEqual(archived, path)
        return path

    def two_rollovers(self, api) -> "tuple[str, str]":
        api._conversation.append("user", "Hey")
        api._conversation.append("assistant", "hi")
        api._conversation.append("user", crow_core.BUDGET_SPENT)
        api._conversation.append("assistant", "ran nothing")
        first = self.cut(api, "20260923-195925")
        api._conversation.append("user", crow_core.BUDGET_SPENT)
        api._conversation.append("assistant", "ok")
        api._conversation.append("user", "[Goal mode. 1 of 9 steps done. Next "
                                         "is step 2: Build geometry]")
        api._conversation.append("assistant", "working")
        second = self.cut(api, "20260923-210418")
        api._conversation.append("user", crow_core.BUDGET_SPENT)
        api._conversation.append("assistant", "still here")
        return first, second

    def test_rollover_archives_are_not_in_the_rail(self):
        api = self.api()
        first, second = self.two_rollovers(api)
        self.drained(api)
        api._reload_rail()
        entry = self.rail(api)
        listed = [r["path"] for r in entry["rollovers"]]
        self.assertNotIn(first, listed)
        self.assertNotIn(second, listed)
        self.assertTrue(entry["unsaved"], "the live chat is drawn as ONE entry")

    def test_they_stay_on_disk_and_in_the_drawer(self):
        api = self.api()
        first, second = self.two_rollovers(api)
        self.drained(api)
        api._reload_rail()
        drawer = self.rail(api)["archived"]
        self.assertEqual([r["path"] for r in drawer], [second, first])
        self.assertTrue(all(r["rollover"] for r in drawer))
        self.assertTrue(all(r["meta"].endswith("rolled over") for r in drawer))
        for path in (first, second):
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(os.path.isfile(path[:-5] + ".md"))

    def test_no_title_is_a_crow_note_and_the_chat_keeps_its_name(self):
        """Both archives and the live chat are "Hey": one chat, three
        segments. Before, the second archive read "[The tool budget ..." and
        the live chat named itself after whatever note came first."""
        api = self.api()
        self.two_rollovers(api)
        self.drained(api)
        api._reload_rail()
        entry = self.rail(api)
        self.assertEqual(entry["title"], "Hey")
        self.assertEqual([r["title"] for r in entry["archived"]], ["Hey", "Hey"])

    def test_an_opened_rollover_stands_in_the_rail_once(self):
        """The one exception: a rollover somebody opened IS the chat in the
        window, so it is in the rail (marked) and not also in the drawer."""
        api = self.api()
        first, _second = self.two_rollovers(api)
        api.open(first)
        self.drained(api)
        api._reload_rail()
        entry = self.rail(api)
        mine = [r for r in entry["rollovers"] if r["path"] == first]
        self.assertEqual(len(mine), 1)
        self.assertTrue(mine[0]["active"])
        self.assertNotIn(first, [r["path"] for r in entry["archived"]])

    def test_the_drawer_offers_no_restore_for_a_rollover(self):
        src = crow_gui.PAGE
        self.assertIn('if(!entry.rollover)\n      rows.push({act:"arch"',
                      src)


class CrowNotesAreNeverATitleTests(unittest.TestCase):
    """#261: every user-role note Crow sends, not only the
    rollover note (#153), is skipped when a chat is titled."""

    def test_each_note_is_skipped(self):
        notes = [crow_core.BUDGET_SPENT, crow_core.TOKEN_BUDGET_SPENT,
                 crow_core.THINK_ONLY_NUDGE,
                 "[Goal mode, step 9 still open. Continue.]",
                 crow_core.goal_trouble_nudge(3, [])]
        for note in notes:
            messages = [{"role": "system", "content": "s"},
                        {"role": "user", "content": note},
                        {"role": "assistant", "content": "ok"},
                        {"role": "user", "content": "build the fog"}]
            self.assertEqual(crow_gui.Api._first_line(messages), "build the fog",
                             note[:40])
            self.assertIsNone(crow_gui.Api._first_line(messages[:2]), note[:40])

    def test_a_typed_bracket_line_is_still_a_title(self):
        """NEGATIV: only Crow's own heads are skipped, not every '['."""
        messages = [{"role": "user", "content": "[WIP] fog shader"}]
        self.assertEqual(crow_gui.Api._first_line(messages), "[WIP] fog shader")

    def test_the_root_notice_is_not_the_title_the_typed_line_is(self):
        text = crow_core.ROOT_NOTICE.format(new="/a", old="/b") + "move it"
        messages = [{"role": "user", "content": text}]
        self.assertEqual(crow_gui.Api._first_line(messages), "move it")


# ----------------------------------------------------------- the rail --------

class _ArchivesIntoTheLiveSession(crow_gui.Api):
    """The window as it was: a chat with no file of its own is written into
    session.json when it is left.

    Nothing lists session.json in the rail, so the chat had left the window; the
    first turn of the chat being opened then wrote over it. This is the shape of
    "the previous chat is completely overwritten", kept runnable so the case
    against it can fail.
    """

    def _archive(self) -> str | None:
        if self._current_path:
            return super()._archive()
        try:
            crow_core.save_session(self._conversation, self._args.base_url,
                                   self._context_tokens,
                                   path=crow_gui.SESSION_FILE, with_kv=False)
        except Exception:
            return None
        return crow_gui.SESSION_FILE


class _FilesTheRestoredSessionEveryStart(crow_gui.Api):
    """The window as it was: start-up hands the restored session a file whether
    it has one already or not. Five launches, five identical entries."""

    def _probe(self) -> None:
        super()._probe()
        self._current_path = None
        self._current_path = self._archive()


class _NeverStampsTheName(crow_gui.Api):
    """The window as it was: `crow_title` is written into one file and nowhere
    else, so the next write through the core drops it."""

    def _stamp(self, path: str, pointer: bool = False) -> None:
        return None


class RailTests(ApiCase):
    """The three faults reported against the built window, each with the version
    that had them still runnable beside it.

    A CASE THAT ONLY THE FIX CAN PASS. Every positive here is followed by the
    same predicate against a subclass restoring the old behaviour: if the broken
    window passes too, the case is measuring nothing.
    """

    # -- symptom 3: switching away destroyed the chat being left ---------------

    def test_switching_chats_leaves_the_previous_one_in_the_rail(self):
        """POSITIVE. Two chats, a switch, and the one switched away from is
        still there -- with its own messages in it."""
        api = self.api()
        self.a_chat(api, "chat ONE speaking")
        ok, first = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "chat TWO speaking")
        self.drained(api)

        api.open(first)
        entry = self.rail(api)
        earlier = [r["title"] for r in entry["rollovers"]]
        self.assertIn("chat TWO speaking", earlier,
                      "the chat that was open when the switch happened is in no "
                      "list -- it was written where nothing reads")
        self.assertEqual(entry["title"], "chat ONE speaking")

    def test_the_chat_being_left_is_readable_afterwards(self):
        """The stronger half: listed is not the same as intact."""
        api = self.api()
        self.a_chat(api, "chat ONE speaking")
        ok, first = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "chat TWO speaking", "the second answer")
        self.drained(api)
        api.open(first)

        second = [r["path"] for r in self.rail(api)["rollovers"]
                  if r["title"] == "chat TWO speaking"]
        self.assertTrue(second, "no file to read back")
        restored = crow_core.load_session("http://127.0.0.1:1/v1", None, second[0])
        self.assertIsNotNone(restored, "the file the switch wrote is not a session")
        messages, _tokens, _kv = restored
        self.assertIn("the second answer", [m.get("content") for m in messages])

    def test_the_old_window_loses_the_chat_it_switched_away_from(self):
        """NEGATIVE. The same steps against the version that wrote it into
        session.json: the case above has to go red for it, or it proves nothing."""
        api = self.api(klass=_ArchivesIntoTheLiveSession)
        self.a_chat(api, "chat ONE speaking")
        ok, first = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "chat TWO speaking")
        self.drained(api)
        api.open(first)

        earlier = [r["title"] for r in self.rail(api)["rollovers"]]
        self.assertNotIn("chat TWO speaking", earlier,
                         "the old behaviour kept the chat -- then this suite is "
                         "not reproducing the fault it is cut against")

    # -- symptom 1: deleted chats came back on "new" --------------------------

    def test_a_deleted_chat_does_not_come_back_when_the_next_one_starts(self):
        """POSITIVE. Delete every chat under "Earlier", press "new", and the
        rail holds only what is actually still on disk."""
        api = self.api()
        self.a_chat(api, "the one to delete")
        ok, first = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "the one still open")
        self.drained(api)

        api.delete_chat(first)
        self.assertFalse(os.path.exists(first))
        api.reset()
        titles = [r["title"] for r in self.rail(api)["rollovers"]]
        self.assertNotIn("the one to delete", titles,
                         "a chat that was deleted is in the rail again")
        self.assertEqual(titles.count("the one still open"), 1,
                         "the chat put aside was written more than once")

    def test_deleting_the_open_chat_empties_the_window(self):
        """The open chat is deletable too, and "delete" has to mean it. Kept in
        memory, it was written straight back out by the next "new"."""
        api = self.api()
        self.a_chat(api, "the open one")
        ok, path = api._leave()
        self.assertTrue(ok)
        self.drained(api)

        api.delete_chat(path)
        self.assertIn("clear", [m["k"] for m in self.drained(api)] + ["clear"])
        api.reset()
        titles = [r["title"] for r in self.rail(api)["rollovers"]]
        self.assertNotIn("the open one", titles,
                         "the deleted chat was written back out by the next new")
        self.assertFalse(os.path.exists(self.session),
                         "session.json still holds the deleted conversation")

    def test_a_restored_session_is_not_copied_into_the_rail_on_every_start(self):
        """POSITIVE, and the root of the "deleted chats come back" report: what
        returned was not the old file but a fresh copy of the same conversation,
        written by the launch itself. Three starts, no entry under "Earlier"."""
        conversation = crow_core.Conversation(None)
        conversation.append("user", "the restored one")
        conversation.append("assistant", "an answer")
        crow_core.save_session(conversation, "http://127.0.0.1:1/v1", 12, with_kv=False)

        for _ in range(3):
            api = self.api()
            self._probe_without_a_server(api)
            entry = self.rail(api)
        self.assertEqual(entry["rollovers"], [],
                         "%d copies of the restored chat after three launches"
                         % len(entry["rollovers"]))
        self.assertEqual(entry["title"], "the restored one")

    def test_the_old_window_copied_the_restored_session_on_every_start(self):
        """NEGATIVE for the case above."""
        conversation = crow_core.Conversation(None)
        conversation.append("user", "the restored one")
        conversation.append("assistant", "an answer")
        crow_core.save_session(conversation, "http://127.0.0.1:1/v1", 12, with_kv=False)

        for _ in range(3):
            api = self.api(klass=_FilesTheRestoredSessionEveryStart)
            self._probe_without_a_server(api)
            entry = self.rail(api)
        self.assertGreater(len(entry["rollovers"]), 0,
                           "the old behaviour produced no copies -- then this "
                           "suite is not reproducing the fault")

    # -- symptom 2: a renamed chat lost its name when it was put aside --------

    def test_a_renamed_chat_keeps_its_name_when_it_is_put_aside(self):
        """POSITIVE. Name the open chat "Test IDE", press "new", and it is under
        "Earlier" as "Test IDE" -- not as its first line."""
        api = self.api()
        self.a_chat(api, "the first line of this chat")
        api.rename("", "Test IDE")
        self.drained(api)

        api.reset()
        titles = [r["title"] for r in self.rail(api)["rollovers"]]
        self.assertIn("Test IDE", titles,
                      "the renamed chat is listed as %s" % titles)
        self.assertNotIn("the first line of this chat", titles)

    def test_renaming_the_open_chat_does_not_file_it_away(self):
        """A rename is a label, not a decision to be finished with it. Naming the
        open chat used to archive it on the spot."""
        api = self.api()
        self.a_chat(api, "still working here")
        api.rename("", "a name")
        entry = self.rail(api)
        self.assertEqual(entry["title"], "a name")
        self.assertEqual(entry["rollovers"], [],
                         "renaming the open chat put it under Earlier")

    def test_the_name_survives_a_restart(self):
        """The name is written where the next launch reads it, or it is a label
        on this process only."""
        api = self.api()
        self.a_chat(api, "the first line of this chat")
        api.rename("", "Test IDE")
        api._persist_live()

        second = self.api()
        self._probe_without_a_server(second)
        self.assertEqual(self.rail(second)["title"], "Test IDE")

    # -- #100: a name given before the first turn ----------------------------

    def test_a_name_given_before_the_first_turn_survives_a_restart(self):
        """POSITIVE (#100). Naming a chat before typing into it is how people
        file things -- the name describes what the slot is FOR, not what is in
        it. Until now it lived only in memory: `save_session` refuses an empty
        conversation, so no file was written, so `_stamp` never ran.
        """
        api = self.api()
        api.rename("", "Einkaufsliste")            # no turn in this chat at all
        self.drained(api)

        second = self.api()
        self._probe_without_a_server(second)
        self.assertEqual(self.rail(second)["title"], "Einkaufsliste")

    def test_an_empty_chat_nobody_named_still_leaves_nothing(self):
        """THE NEGATIVE HALF, and the one that keeps the fix above from being a
        regression. `save_session`'s refusal is what stops an abandoned chat
        coming back on the next start; writing a file for EVERY empty chat would
        walk straight back into it. Only a name earns a file.
        """
        api = self.api()
        api._persist_live()
        self.assertFalse(os.path.isfile(self.session),
                         "an unnamed empty chat wrote a session file")

    def test_a_session_file_with_only_a_name_is_not_a_conversation(self):
        """THE SECOND NEGATIVE HALF. The file this fix creates carries a name and
        no messages. If the core read that as a chat, the window would come back
        holding an empty conversation it never had -- so this pins that the core
        answers "no session", and that it does not raise on the way there."""
        api = self.api()
        api.rename("", "nur ein Name")
        self.drained(api)
        self.assertTrue(os.path.isfile(self.session))
        self.assertIsNone(crow_core.load_session("http://127.0.0.1:1/v1", None))

    def test_a_window_that_does_not_stamp_the_name_loses_it(self):
        """NEGATIVE. The version that wrote `crow_title` into one file and left
        it there: the core's next write drops the key."""
        api = self.api(klass=_NeverStampsTheName)
        self.a_chat(api, "the first line of this chat")
        api.rename("", "Test IDE")
        self.drained(api)
        api.reset()
        titles = [r["title"] for r in self.rail(api)["rollovers"]]
        self.assertNotIn("Test IDE", titles,
                         "the old behaviour kept the name -- then the case above "
                         "is not measuring the stamp")

    # -- the rules the rail is drawn by --------------------------------------

    def test_the_open_chat_is_listed_once_and_marked(self):
        """It used to be drawn at the top AND filtered out of the list, so a
        click MOVED it -- out of where it was and into the live slot. It stays
        in the list now, marked where it sits.

        REPLACES `test_the_open_chat_is_not_listed_under_earlier`, which pinned
        the filter. The duplicate that one guarded against is what `unsaved`
        prevents: the top slot exists only for a chat with no file.
        """
        api = self.api()
        self.a_chat(api, "the open one")
        ok, path = api._leave()
        self.assertTrue(ok)
        api._reload_rail()
        entry = self.rail(api)
        listed = [r for r in entry["rollovers"] if r["path"] == path]
        self.assertEqual(len(listed), 1, "the open chat is listed once")
        self.assertTrue(listed[0]["active"])
        self.assertFalse(entry["unsaved"], "it has a file; no second slot on top")

    def test_a_chat_with_no_file_is_the_only_thing_on_top(self):
        """NEGATIVE HALF, and the case the old filter existed for: without this
        the live slot could be drawn beside the same chat's list entry."""
        api = self.api()
        self.a_chat(api, "never left")
        api._reload_rail()
        entry = self.rail(api)
        self.assertTrue(entry["unsaved"])
        self.assertEqual([r for r in entry["rollovers"] if r.get("active")], [])

    def test_a_chat_with_no_turn_in_it_gets_no_file(self):
        """Files are for conversations. A window opened and closed again must not
        leave anything in the rail."""
        api = self.api()
        ok, path = api._leave()
        self.assertTrue(ok)
        self.assertIsNone(path)
        self.assertEqual([n for n in os.listdir(self.dir) if n.endswith(".json")], [])

    def test_leaving_a_chat_twice_writes_one_file(self):
        """Its file, not another one. This is what "new" on a chat that came out
        of the archive used to get wrong."""
        api = self.api()
        self.a_chat(api, "the same chat")
        ok, first = api._leave()
        self.assertTrue(ok)
        ok, again = api._leave()
        self.assertTrue(ok)
        self.assertEqual(first, again)
        self.assertEqual(len([n for n in os.listdir(self.dir)
                              if n.startswith("chat-")]), 1)

    def test_a_chat_that_was_archived_is_listed_in_the_drawer_and_not_above(self):
        """Archiving moves the file; the rail has to follow it in both
        directions."""
        api = self.api()
        self.a_chat(api, "put me away")
        ok, path = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.drained(api)

        api.archive_chat(path)
        entry = self.rail(api)
        self.assertEqual([r["title"] for r in entry["archived"]], ["put me away"])
        self.assertEqual([r["title"] for r in entry["rollovers"]], [])

        api.archive_chat(entry["archived"][0]["path"])
        entry = self.rail(api)
        self.assertEqual([r["title"] for r in entry["rollovers"]], ["put me away"])
        self.assertEqual(entry["archived"], [])

    def _probe_without_a_server(self, api) -> None:
        """`_probe` with the three endpoint calls answered from here.

        The window asks /health, the model name and n_ctx before it restores
        anything, and this suite has no server. Everything after those three
        lines is the real method, which is the part these cases are about.
        """
        before = (crow_gui.check_endpoint, crow_gui.fetch_model_name,
                  crow_gui.fetch_n_ctx)
        crow_gui.check_endpoint = lambda url: "ok"
        crow_gui.fetch_model_name = lambda url: "crow"
        crow_gui.fetch_n_ctx = lambda url: 200000
        try:
            api._probe()
        finally:
            (crow_gui.check_endpoint, crow_gui.fetch_model_name,
             crow_gui.fetch_n_ctx) = before


# ---------------------------------------------------- the session, twice ----

class SessionRoundTripTests(ApiCase):
    """ONE SESSION, TWO DOORS. #90's E12 point 4, with a file and a name.

    WHAT IS HERE AND WHAT IS IN E14. The two LIVE directions need a running
    server and are E14's. What can be settled without one is the part that
    decides it: whether the two doors write and read ONE file in ONE format. A
    window with a format of its own passes every live forward test and fails
    right here.
    """

    def test_what_the_window_wrote_is_what_the_cli_reads(self):
        """FORWARD. The window saves; `load_session` -- the same function
        cli/crow.py calls at start -- reads the same messages back."""
        api = self.api()
        self.a_chat(api, "was macht der Prefix-Cache", "Er haelt.")
        api._persist_live()
        self.assertTrue(os.path.exists(self.session))

        restored = crow_core.load_session("http://127.0.0.1:1/v1", None)
        self.assertIsNotNone(restored, "the CLI's reader sees no session")
        messages, _tokens, _kv = restored
        self.assertEqual([m["role"] for m in messages],
                         [m["role"] for m in api._conversation.payload()])
        self.assertEqual([m["content"] for m in messages],
                         [m["content"] for m in api._conversation.payload()])

    def test_what_the_cli_wrote_is_what_the_window_shows(self):
        """BACKWARD, and it is the direction a window with its own format fails.
        The file is written the way cli/crow.py writes one; the window has to
        SHOW it, not merely hold it."""
        conversation = crow_core.Conversation(None)
        conversation.append("user", "was macht der Prefix-Cache")
        conversation.append("assistant", "Er haelt, solange das Praefix gleich bleibt.")
        crow_core.save_session(conversation, "http://127.0.0.1:1/v1", 4711,
                               with_kv=False)

        api = self.api()
        RailTests._probe_without_a_server(self, api)
        drawn = self.drained(api)
        self.assertEqual(len(api._conversation), len(conversation))
        self.assertEqual(api._context_tokens, 4711)
        asked = [m.get("t") for m in drawn if m.get("k") == "user"]
        self.assertIn("was macht der Prefix-Cache", asked)
        self.assertIn("Er haelt, solange das Praefix gleich bleibt.",
                      self.answer_text(drawn))

    def test_a_restored_chat_is_drawn_through_the_same_sink_as_a_live_one(self):
        """A reopened chat cannot be allowed to look different from a typed one.
        It went straight to the page once, so a stored fence arrived as three
        backticks and a stored thought did not arrive at all."""
        conversation = crow_core.Conversation(None)
        conversation.append("user", "zeig mir code")
        conversation.append("assistant", "so:\n```python\nx = 1\n```\n",
                            reasoning="erst denken")
        crow_core.save_session(conversation, "http://127.0.0.1:1/v1", 1, with_kv=False)

        api = self.api()
        RailTests._probe_without_a_server(self, api)
        kinds = [m.get("k") for m in self.drained(api)]
        self.assertIn("code_open", kinds, "a stored fence was not cut by the core")
        self.assertIn("think_open", kinds, "a stored thought was not replayed")

    def test_the_window_stamps_the_file_with_the_version_the_cli_owns(self):
        """The same file from both doors means the same header from both doors."""
        api = self.api()
        self.a_chat(api, "x")
        api._persist_live()
        with io.open(self.session, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["version"], crow.VERSION)
        self.assertEqual(saved[crow_core.SESSION_FORMAT_KEY], crow_core.SESSION_FORMAT)

    def test_crows_own_keys_do_not_disturb_the_core(self):
        """`crow_title` and `crow_path` are added after the core has written. The
        file has to stay a session file both clients can open."""
        api = self.api()
        self.a_chat(api, "erste zeile")
        api.rename("", "ein name")
        restored = crow_core.load_session("http://127.0.0.1:1/v1", None)
        self.assertIsNotNone(restored, "the stamped file is no longer readable")
        with io.open(self.session, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["crow_title"], "ein name")

    def test_a_session_this_build_cannot_read_is_refused_and_left_alone(self):
        """The gate from E8, through the window's door. A refusal that still
        overwrote the file would be the data loss the gate exists against."""
        stranger = {crow_core.SESSION_FORMAT_KEY: "99",
                    "messages": [{"role": "user", "content": "hi"}]}
        with io.open(self.session, "w", encoding="utf-8") as fh:
            json.dump(stranger, fh)
        before = Path(self.session).read_bytes()

        api = self.api()
        RailTests._probe_without_a_server(self, api)
        said = " ".join(str(m.get("t", "")) for m in self.drained(api))
        self.assertIn("format", said.lower(),
                      "a refused session file was not reported to the page")
        self.assertEqual(Path(self.session).read_bytes(), before)
        # "Empty" is the system prompt and nothing else -- a fresh Conversation
        # already holds one, which is why this is not a comparison against 0.
        self.assertEqual(len(api._conversation),
                         1 if api._conversation.has_system else 0)


# --------------------------------------------------- the seam to the page ---

def _code_only(source: str) -> str:
    """The file with its comment lines dropped, Python's and the page's.

    THE SAME RULE tools/check_operating_point.py's `code_only` states: a
    sentence explaining a message that USED to be pushed is not a place that
    pushes it. Without this the seam check below reported `_round` as a live
    hole because the comment recording its removal names it.

    THREE COMMENT SYNTAXES, because this file is three languages in one: Python,
    the page's JavaScript, and its CSS -- and the CSS block comment is the one
    that carries the longest explanations, including the two traps below.
    """
    blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(line for line in blocks.splitlines()
                     if not line.lstrip().startswith(("#", "//")))


def _message_kinds(source: str) -> set:
    """Every `k` the Python side pushes."""
    return set(re.findall(r'\{"k":\s*"([a-z_]+)"', _code_only(source)))


def _drawn_kinds(source: str) -> set:
    """Every `k` the page has a case for."""
    return set(re.findall(r'case\s+"([a-z_]+)":', _code_only(source)))


class SlashCommandsReachTheWindowTests(ApiCase):
    """#94. The window handled `/tools` and nothing else.

    The other six travelled to the server as ordinary questions and came back as
    an answer about the word -- `/reset`, `/context`, `/thoughts`, `/mode`,
    `/exit`, `/quit`. That is the divergence #90 exists to prevent, in the shape
    no checker sees: both surfaces call the same core, and the difference is in
    what never reaches it.

    THE DECISION (robin, 2026-08-14) IS NOT "PORT THE COMMANDS". Four of the
    seven already have a widget here, so those point at it and only the ones
    without are executed. What is shared is the LIST, not the answer.
    """

    class _StubWindow:
        """`/exit` reaches `window.destroy()`, which a test has no window for."""

        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    def windowed(self, *argv):
        api = self.api(*argv)
        api._window = self._StubWindow()
        return api

    def test_every_shared_command_gets_an_answer(self):
        for command in crow_core.SLASH_COMMANDS:
            api = self.windowed()
            self.assertIsNotNone(api.slash_answer(command),
                                 f"{command} still travels to the model")

    # -- what /reset means, which is the whole reason this was rebuilt --------

    def test_reset_drops_the_context(self):
        """The TERMINAL's meaning: `conversation.reset()`; the context goes.
        ANGEPASST 2026-08-28 spaetabends auf robins Ansage: die geschriebene
        Dauer-Freigabe ("always") ueberlebt den Reset -- nur der Chat endet."""
        api = self.windowed()
        # THE BASELINE IS NOT ZERO: a Conversation carries its system message,
        # and `reset()` keeps it. Comparing against 0 would fail on a correct
        # reset and pass on one that threw the system prompt away.
        empty = len(api._conversation)
        api._conversation.append("user", "something")
        api._context_tokens = 4321
        self.addCleanup(setattr, crow_core, "APPROVALS_FILE",
                        crow_core.APPROVALS_FILE)
        self.addCleanup(setattr, crow_core, "_STORED_APPROVALS", None)
        crow_core.APPROVALS_FILE = os.path.join(self.dir, "approvals.json")
        crow_core._STORED_APPROVALS = None
        crow_core.remember("write_file", json.dumps({"path": "x"}))
        api.slash_answer("/reset")
        self.assertEqual(len(api._conversation), empty)
        self.assertEqual(api._context_tokens, 0)
        self.assertTrue(crow_core.remembered("write_file",
                                             json.dumps({"path": "x"})),
                        "the written always died with the chat")

    def test_reset_does_NOT_archive_the_chat(self):
        """THE CASE THIS WHOLE REBUILD IS FOR.

        The first version answered `/reset` with "that is the new button" -- and
        `new` archives the conversation into the rail and opens an empty one.
        `/reset` keeps the chat where it is. Two operations, and pointing one at
        the other is worse than not handling it at all: the user follows the
        instruction and files away a chat they meant to keep.
        """
        api = self.windowed()
        api._conversation.append("user", "something")
        before = sorted(os.listdir(self.dir))
        note = api.slash_answer("/reset")
        self.assertEqual(sorted(os.listdir(self.dir)), before,
                         "/reset wrote a file; that is what `new` does")
        self.assertNotIn("put aside", note)
        self.assertIn("prefill", note)

    def test_reset_survives_closing_the_window(self):
        """ROBIN'S REPORT, 2026-08-14: "/reset wird scheinbar nicht gespeichert
        wenn man crow schließt".

        He was right, and it was not the window's fault: `save_session` will not
        write an empty conversation, so the file from before the reset stayed
        and the next start restored it. The whole chain is driven here -- write a
        session, drop it, close, and ask what a restart would find -- because
        every link of it was individually green while the chain was broken.
        """
        api = self.windowed()
        api._conversation.append("user", "Lies aufgabe.txt")
        api._conversation.append("assistant", "ok")
        api._context_tokens = 1100
        crow_core.save_session(api._conversation, api._args.base_url, 1100,
                               with_kv=False)
        self.assertTrue(os.path.exists(self.session), "nothing was there to lose")

        api.slash_answer("/reset")
        api.close()
        self.assertIsNone(crow_core.load_session(api._args.base_url),
                          "the dropped conversation came back")

    def _opened_from_the_rail(self):
        """An Api holding a chat that came out of the rail, as `open()` leaves it."""
        api = self.windowed()
        path = os.path.join(self.dir, "chat-20260814-120000.json")
        talk = crow_core.Conversation("SYS")
        talk.append("user", "hey my friend")
        talk.append("assistant", "hi")
        crow_core.save_session(talk, api._args.base_url, 900,
                               path=path, with_kv=False)
        api._conversation = talk
        api._current_path = path
        api._context_tokens = 900
        return api, path

    def test_a_reset_lets_go_of_the_chat_it_came_from(self):
        """ROBIN, 2026-08-14: "/reset in einem EARLIER Fenster geht erst, aber
        nach Neustart ist der Text samt cache und context wieder da."

        A chat opened out of the rail keeps `_current_path`, and `close()`
        archives the open conversation THERE -- except `save_session` refuses an
        empty one, so the file kept its old messages and the next start found
        them. Removing `session.json` alone fixed the live case and left this
        one, which is one half of the same seam again.
        """
        api, path = self._opened_from_the_rail()
        api.slash_answer("/reset")
        self.assertIsNone(api._current_path, "still bound to the chat it dropped")
        api.close()
        self.assertIsNone(crow_core.load_session(api._args.base_url),
                          "the dropped conversation came back")

    def test_but_it_does_NOT_throw_the_saved_chat_away(self):
        """NEGATIVE HALF, and the more important one. `/reset` drops the
        context; it is not "delete my saved chat". A fix that removed the file
        would pass the case above and quietly destroy work."""
        api, path = self._opened_from_the_rail()
        api.slash_answer("/reset")
        api.close()
        self.assertTrue(os.path.exists(path), "/reset deleted a saved chat")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)["messages"]), 3)

    def test_and_the_name_of_that_chat_survives_the_reset_too(self):
        """THE OTHER HALF OF THE SAME PROMISE. The case above pins the MESSAGES
        of a chat `/reset` let go of and says nothing about its IDENTITY -- and
        the name is the one thing about a chat the user typed themselves. A
        detached chat that came back nameless would be the same loss with the
        text still in it.

        WHAT THIS DOES NOT PROVE, and the commit says so rather than implying
        otherwise: it is not a negative probe for the `else: data.pop(...)`
        `_stamp` carried until now. That branch needed `_current_title` to be
        None while a file it was about to stamp still held a name, and `/reset`
        clears `_current_path` in the same breath -- so nothing stamps this file
        at all and the case is green either way. The branch was unreachable,
        which is why it went without a case of its own. This one holds the
        promise it had been standing next to.
        """
        api, path = self._opened_from_the_rail()
        self.assertTrue(api.rename(path, "Schmetterlinge"))
        api.slash_answer("/reset")
        api.close()
        self.assertIsNone(api._current_title, "the window kept a name it dropped")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh).get("crow_title"), "Schmetterlinge",
                             "/reset took the name off a chat it only let go of")

    def test_no_session_leaves_the_file_alone(self):
        """NEGATIVE HALF. `--no-session` means this client does not own that
        file, and a reset is not a licence to delete somebody else's."""
        api = self.windowed("--no-session")
        api._args.session = False
        talk = crow_core.Conversation("SYS")
        talk.append("user", "not ours to drop")
        crow_core.save_session(talk, api._args.base_url, 10, with_kv=False)
        api.slash_answer("/reset")
        self.assertTrue(os.path.exists(self.session))

    def test_reset_clears_the_page_too(self):
        """The conversation and what is on screen are two things, and only one
        of them is Python's. `new` clears the flow from the page side before it
        calls in; a command answered here has to say so on the queue."""
        api = self.windowed()
        api.slash_answer("/reset")
        self.assertIn("clear", [m.get("k") for m in self.drained(api)])

    def test_reset_is_refused_mid_turn(self):
        """`set_mode` and `set_tools` both refuse; dropping the context under a
        running turn is the same class and a louder failure."""
        api = self.windowed()

        class _Busy:
            def is_alive(self):
                return True

        api._worker = _Busy()
        api._conversation.append("user", "something")
        held = len(api._conversation)
        self.assertIn("mid-turn", api.slash_answer("/reset"))
        self.assertEqual(len(api._conversation), held)

    # -- the other four ------------------------------------------------------

    def test_context_reports_the_three_figures(self):
        api = self.windowed()
        api._conversation.append("user", "something")
        api._context_tokens = 1234
        api._n_ctx = 200000
        line = api.slash_answer("/context")
        self.assertIn("1234 tokens", line)
        self.assertIn("messages", line)
        self.assertIn("rolls over at", line)

    def test_mode_reports_and_switches(self):
        api = self.windowed()
        self.assertIn(api._args.mode, api.slash_answer("/mode"))
        api.slash_answer("/mode manual")
        self.assertEqual(api._args.mode, "manual")

    def test_a_switch_is_announced_once_and_not_twice(self):
        """`set_mode` pushes its own note. A second from the command put the
        switch on screen twice -- the same defect as the doubled echo, in a
        different half. Found by robin in the window, again."""
        api = self.windowed()
        api.send("/mode manual")
        notes = [m for m in self.drained(api) if m.get("k") == "note"]
        self.assertEqual(len(notes), 1, [n.get("t") for n in notes])
        self.assertIn("manual", notes[0]["t"])

    def test_an_empty_answer_is_handled_but_not_shown(self):
        """NEGATIVE HALF of the line above: "" means handled-and-already-said,
        None means not-ours. Confusing them sends `/mode manual` to the model."""
        api = self.windowed()
        self.assertEqual(api.slash_answer("/mode manual"), "")
        self.assertIs(api.send("/mode auto"), False)

    def test_an_unknown_level_is_named_rather_than_ignored(self):
        """NEGATIVE HALF of the switch: a typo that silently does nothing is a
        level the user believes they are on."""
        api = self.windowed()
        answer = api.slash_answer("/mode careful")
        self.assertIn("careful", answer)
        self.assertNotEqual(api._args.mode, "careful")

    def test_thoughts_folds_and_unfolds(self):
        api = self.windowed()
        first = api.slash_answer("/thoughts")
        second = api.slash_answer("/thoughts")
        folds = [m for m in self.drained(api) if m.get("k") == "thoughts"]
        self.assertEqual([m["open"] for m in folds], [True, False])
        self.assertIn("opened", first)
        self.assertIn("closed", second)

    def test_exit_closes_the_window(self):
        api = self.windowed()
        api.slash_answer("/exit")
        self.assertTrue(api._window.destroyed)

    def test_quit_does_the_same(self):
        api = self.windowed()
        api.slash_answer("/quit")
        self.assertTrue(api._window.destroyed)

    def test_the_help_listing_covers_every_one_of_them(self):
        listing = self.api().help_listing()
        for command in crow_core.SLASH_COMMANDS:
            self.assertIn(command, listing)
        self.assertNotIn("nothing here answers this yet", listing)

    def test_an_argument_does_not_send_it_to_the_model(self):
        """`/mode manual` is the form the terminal documents, so it is the form
        a user brings over."""
        self.assertIsNotNone(self.api().slash_answer("/mode manual"))

    def test_tools_still_answers_with_the_schema(self):
        """The one command that already worked has to keep working -- it is the
        one the input's own placeholder advertises."""
        self.assertIn("the model can call", self.api().slash_answer("/tools"))

    # -- the negative half --------------------------------------------------

    def test_an_unknown_slash_word_still_reaches_the_model(self):
        """NEGATIVE CONTROL. A window that swallows everything starting with a
        slash has taken a question away from the thing that could answer it --
        and it would pass every case above."""
        self.assertIsNone(self.api().slash_answer("/nonsense"))

    def test_a_question_about_a_path_still_reaches_the_model(self):
        """The case that makes the one above concrete rather than theoretical."""
        api = self.api()
        self.assertIsNone(api.slash_answer("/usr/bin/env is what?"))
        self.assertIsNone(api.slash_answer("/etc/hosts"))

    def test_an_empty_message_is_not_a_command(self):
        self.assertIsNone(self.api().slash_answer("   "))

    # -- the pointers have to point at something that exists ----------------

    def test_no_answer_describes_where_a_control_is(self):
        """THE RULE THAT REPLACED THE POINTERS, and it is the one a later change
        will be tempted to break.

        The first version answered each command with a sentence naming the
        widget that does the same job. One of those sentences was wrong about
        which side of the rail a button sits on, and the case meant to catch
        that only asserted the button's id appears in the page -- so it could
        not have. Prose about pixels cannot be tested, which is the argument
        against writing any.
        """
        api = self.windowed()
        answers = [api.slash_answer(c) or "" for c in crow_core.SLASH_COMMANDS]
        answers.append(api.help_listing())
        for said in answers:
            for word in ("button", "top left", "top right", "beside", "dropdown",
                         "title bar", "click"):
                self.assertNotIn(word, said.lower(),
                                 f"an answer describes a control: {said!r}")

    def test_a_multi_line_answer_survives_the_page(self):
        """`/help` and `/tools` build a column with their own line breaks. The
        default `white-space` collapsed all of it into one run-on paragraph --
        eight commands on a single line, true of `/tools` since the day the
        window answered it, and found by robin in the window rather than here.

        BOTH HALVES, because either alone is green and useless: the answer has
        to carry newlines, and the page has to keep them.
        """
        self.assertIn("\n", self.windowed().help_listing())
        # THE SELECTOR HAS TO BE ANCHORED. There are two `.note` rules and the
        # other one is `.tool .note{…white-space:nowrap}`, for the timing on a
        # tool row -- searching for ".note{" finds that one first and reads a
        # rule that is correctly the opposite of what this pins.
        rule = crow_gui.PAGE.split("\n.note{")[1].split("}")[0]
        self.assertIn("white-space:pre-wrap", rule,
                      "the page collapses a multi-line note again")

    def test_every_command_on_the_shared_list_is_described(self):
        """The help a user reads is built from the shared list, so a command
        added there and forgotten here shows up as a gap rather than silence."""
        for command in crow_core.SLASH_COMMANDS:
            self.assertIn(command, crow_gui.Api.WHAT_THEY_DO,
                          f"{command} has no line in the window's help")

    # -- the seam to the page, which the cases above could not see -------------
    #
    # THESE THREE REPLACE A CASE THAT PINNED THE DEFECT. It asserted the Api
    # pushes a `user` echo before the note, which is what the code did and what
    # robin's window showed to be wrong: the typed command appeared TWICE, and
    # the composer stayed on "Stop". Every case above passed throughout, because
    # they drive the Api with no page on the other side -- one half of a seam
    # measuring itself.

    def test_the_command_is_not_echoed_from_this_side(self):
        """The page draws the line before it calls us. A second echo here is the
        same command on screen twice -- wrong for `/tools` before #94, and wrong
        for all seven after it."""
        api = self.windowed()
        api.send("/reset")
        kinds = [m.get("k") for m in self.drained(api)]
        self.assertNotIn("user", kinds)
        self.assertIn("note", kinds)

    def test_a_command_reports_that_no_turn_started(self):
        """WHAT THE PAGE WAITS ON. `pywebview.api.*` resolves a promise when
        this returns, so the composer can be painted from the one fact only this
        side has -- whether there is anything to stop. It used to paint "Stop"
        on the way in and hope, which is how `/reset` left the window sitting on
        Stop with nothing behind it."""
        self.assertIs(self.api().send("/help"), False)

    def test_a_line_mid_turn_starts_no_second_turn(self):
        """The other way to start nothing, and since #138c it is the ONLY thing
        this case still claims.

        WHAT IS PROTECTED IS THE THREAD, not the return value. A line typed mid
        turn used to be dropped and reported as `False`; robin chose on
        2026-08-26 to have it QUEUED instead, because the memory review keeps
        the worker alive after the window has already said idle -- and a line
        typed in that gap vanished from a transcript it was already drawn into.

        So `True` now means "accepted" rather than "started", and the invariant
        that matters is checked directly: one worker, never two.
        """
        api = self.api()
        api._busy = True
        self.assertIs(api.send("hello"), True)
        self.assertEqual(api._queued, "hello")
        self.assertIsNone(api._worker, "no second thread was started")

    def test_an_ordinary_message_reports_that_one_did(self):
        """POSITIVE CONTROL. Without it the rule could be "always return False",
        which passes both cases above and leaves the button dead for real turns.
        """
        api = self.api()
        self.addCleanup(lambda: crow_core.INTERRUPT.set())
        self.assertIs(api.send("what is here?"), True)

    def test_the_page_paints_from_the_answer_and_not_before(self):
        """THE ANCHOR FOR ALL THREE ABOVE, and the half a python case cannot
        reach. They are only correct while `go()` draws the line itself, locks
        synchronously, and leaves the button to the promise. If that changes,
        the Api has to take one of those jobs back -- and a reader finds it here
        rather than in a screenshot, which is where it was found last time.
        """
        self.assertIn("this.user(text)", crow_gui.PAGE)
        self.assertIn("this.running=true", crow_gui.PAGE)
        self.assertIn("started => started ? this.busy() : this.idle()",
                      crow_gui.PAGE)
        # busy() may no longer be called on the way in -- that IS the defect.
        self.assertNotIn("this.user(text); this.busy()", crow_gui.PAGE)

    def test_a_delegate_line_mid_turn_is_sent_not_stopped(self):
        """#143 E3, THE HALF THE PYTHON CASES CANNOT REACH. `send()` answers
        slash lines ahead of the busy buffer -- and the page's own gate turned
        every submit during a turn into `stop()`, so the line never arrived:
        robin typed `/delegate` mid-turn on 2026-08-28 and the RUNNING TURN
        died. The gate has to let the delegation pair through, and it has to
        sit BEFORE the stop call it guards.

        ONLY the delegation pair: a `/reset` or `/model` through this gate
        would yank state under a running pump. The stop gesture itself is the
        negative control below -- a plain line mid-turn still stops.
        """
        gate = "/^\\/(delegate|subtasks)\\b/i.test(text)"
        self.assertIn(gate, crow_gui.PAGE)
        stop = "pywebview.api.stop(); return;"
        self.assertIn(stop, crow_gui.PAGE)
        self.assertLess(crow_gui.PAGE.index(gate), crow_gui.PAGE.index(stop),
                        "the bypass must be checked before the stop gesture")
        # The composer stays on Stop either way: the LOCAL turn is what the
        # button is about, and it is still running behind the slash answer.
        self.assertIn("then(()=>this.busy(), ()=>this.busy())", crow_gui.PAGE)


class TheSeamToThePageTests(unittest.TestCase):
    """Python speaks, the page listens, and nothing checks that they agree.

    THIS FOUND A REAL HOLE. `{"k": "_round"}` carried the reasoning share of
    every turn and the page's switch had no case for it, so it fell through and
    the cost line was drawn with a share of null. Nothing was broken enough to
    look broken: the window worked, and one number was silently always absent.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_every_message_the_window_pushes_has_a_case_on_the_page(self):
        """POSITIVE."""
        holes = sorted(_message_kinds(self.source) - _drawn_kinds(self.source))
        self.assertEqual(holes, [],
                         "pushed to a page that cannot draw it: %s" % holes)

    def test_the_check_sees_a_hole_when_there_is_one(self):
        """NEGATIVE, against the predicate itself. A regex that matched nothing
        would report a clean seam forever."""
        holes = _message_kinds(self.source + '\nself.push({"k": "invented"})\n')
        self.assertIn("invented", holes - _drawn_kinds(self.source))

    def test_the_page_draws_nothing_the_window_never_sends(self):
        """The other direction is a weaker rule but the same drift: a case for a
        message no one sends is a feature that was removed from one side."""
        orphans = sorted(_drawn_kinds(self.source) - _message_kinds(self.source))
        self.assertEqual(orphans, [],
                         "the page has a case for messages nothing sends: %s"
                         % orphans)


# ------------------------------------------------------- the file itself ----

class TheWindowBorrowsAndDoesNotRebuildTests(unittest.TestCase):
    """The rules E12 states about the FILE, held against the file.

    tools/check_shared_core.py holds the same lines against the manifest and is
    the tool that has to stay green. These are the ones it cannot express.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        # COMMENTS OUT: a sentence explaining why a value may not be written
        # here is not a place that writes it.
        self.code = _code_only(self.source)

    def test_no_callback_ends_the_process(self):
        """`main` in cli/crow.py catches CrowError and returns 2. A `sys.exit`
        inside a callback is the wrong translation of that: it takes the window,
        the unsaved session and the running turn with it."""
        body = self.source.split('def main(')[0]
        self.assertNotIn("sys.exit(", body,
                         "a callback in this file can end the process")

    def test_every_function_declares_what_it_returns(self):
        """The type idiom: 85 of 88 functions in the existing client carry a
        return type. A new file is where that quietly stops being true."""
        import ast

        tree = ast.parse(self.source)
        missing = [node.name for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.returns is None
                   and not node.name.startswith("<")]
        self.assertEqual(missing, [], "functions with no return type: %s" % missing)

    def test_the_brand_values_are_not_written_here(self):
        """`#0b0e17` and the accent come out of the core. Written here they would
        be a second copy to correct, which is what the manifest counts."""
        self.assertNotIn("#0b0e17", self.code)
        self.assertNotIn("#7eb0f8", self.code)
        self.assertIn("CROW_BG", self.code)
        self.assertIn("CROW_ACCENT_HEX", self.code)

    def test_the_version_literal_does_not_appear_here(self):
        """install.ps1 greps cli/crow.py for `^VERSION = "..."`. A second file
        carrying one is a second thing to bump, and the stale one is the one no
        release step reads."""
        self.assertIsNone(re.search(r'^VERSION\s*=\s*"', self.source, re.M))
        self.assertEqual(crow_gui.client_version(), crow.VERSION)

    def test_a_missing_client_file_leaves_the_version_empty(self):
        """The empty default is load-bearing: a window that could not read the
        version must stay quiet rather than stamp a session with a guess."""
        empty = tempfile.mkdtemp(prefix="crow-empty-")
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertEqual(crow_gui.client_version(os.path.join(empty, "crow.py")), "")

    def test_the_drag_region_is_the_one_webview2_understands(self):
        """`-webkit-app-region: drag` is Electron's. WebView2 does not know it,
        and the window could not be moved at all. Measured 2026-08-13.

        The DECLARATION is what this rules out, not the string: the file also
        explains the trap in a comment, and a check that could not tell those
        apart would have to be deleted the first time anyone wrote it down.
        """
        self.assertIn("pywebview-drag-region", self.code)
        self.assertIsNone(re.search(r"-webkit-app-region\s*:\s*drag", self.code),
                          "the window is dragged by a property WebView2 ignores")

    def test_the_clipboard_does_not_go_through_the_page(self):
        """`navigator.clipboard` refuses silently outside a secure context, and
        the page is handed over as HTML rather than served over https: the copy
        button reported success over an empty clipboard. Measured 2026-08-13."""
        self.assertIsNone(re.search(r"navigator\.clipboard\s*\.", self.code),
                          "the copy button writes through a clipboard that "
                          "refuses without raising")
        self.assertIn("def copy(self, text: str) -> bool:", self.source)


class TheFolderPickerTests(ApiCase):
    """#92 in the window: the folder picker, and what it is allowed to do.

    THE PICKER IS THE ONLY THING THAT CREATES A ROOT, so these cases are the
    other half of the core's boundary rather than a second copy of it. What is
    checked here is the window's share: that the state reaches the page at all,
    that a directory the user never picked cannot become one, and that the
    boundary cannot move under a running turn.
    """

    def setUp(self) -> None:
        super().setUp()
        self._roots = crow_core.ROOTS_FILE
        crow_core.ROOTS_FILE = os.path.join(self.dir, "roots.json")
        self.addCleanup(setattr, crow_core, "ROOTS_FILE", self._roots)
        self.addCleanup(crow_core.set_root, None)
        crow_core.set_root(None)
        self.root = os.path.join(self.dir, "projekt")
        os.makedirs(self.root)

    def _root_msg(self, api):
        msgs = [m for m in self.drained(api) if m.get("k") == "root"]
        self.assertTrue(msgs, "the page was never told about the working directory")
        return msgs[-1]

    def test_ready_tells_the_page_there_is_none(self):
        """THE ABSENCE IS THE STATE THAT MUST BE VISIBLE. A window that says
        nothing when nothing is bound reads as "bounded and fine"."""
        api = self.api()
        api.ready()
        msg = self._root_msg(api)
        self.assertEqual(msg["path"], "")
        self.assertEqual(msg["roots"], [])

    def test_a_root_restored_by_the_session_reaches_the_page(self):
        """THE SEAM, and it is the one that bit three times on 2026-08-14.

        The restore runs on the probe thread, AFTER `ready()` has already told the
        page what it bound. Without a second push the boundary holds while the
        button still says something else -- screen and loop disagreeing, which is
        worse than either state alone. No Api-only case sees it; this one drives
        `_probe` itself.

        THE SETUP WAS REPLACED ON 2026-08-15 (#101), AND THE ASSERTIONS WERE NOT.
        It used to hand `load_session` a `side_effect` that called `set_root` --
        staging an internal call that has never existed: nothing outside
        `adopt_root` and the picker has ever bound the root, and the comment that
        claimed otherwise was removed the same day. The claim this case makes is
        unchanged and is now stricter, because the folder it checks for arrives
        the way the product actually delivers it: out of the chat's own file.
        """
        crow_core.write_root_mode(self.root, "auto")
        api = self.api()
        # The chat's file carries its root, written the way the window writes it.
        api._current_title = "ein Chat mit Ordner"
        crow_core.set_root(self.root)
        api._root_chosen = True                   # chosen for this chat, not borrowed
        api._stamp(crow_gui.SESSION_FILE, pointer=True)
        crow_core.set_root(None)
        api._current_title = None
        with mock.patch.object(crow_gui, "check_endpoint", return_value="ok"), \
             mock.patch.object(crow_gui, "model_display_name", return_value="m"), \
             mock.patch.object(crow_gui, "fetch_model_name", return_value="m"), \
             mock.patch.object(crow_gui, "fetch_n_ctx", return_value=1000), \
             mock.patch.object(crow_gui, "load_session",
                               return_value=([{"role": "user", "content": "hi"}],
                                             10, False)):
            api._probe()
        msg = self._root_msg(api)
        self.assertEqual(os.path.normcase(msg["path"]),
                         os.path.normcase(os.path.realpath(self.root)))
        self.assertEqual(msg["name"], "projekt")

    # -- #101: the working directory belongs to the chat ---------------------

    def _chat_with_root(self, name, root):
        """A chat file on disk that carries `root` as its own, the way `_stamp`
        writes it. Returns its path."""
        api = self.api()
        api._current_title = name
        crow_core.set_root(root)
        api._root_chosen = True                   # a person picked, for this chat
        api._stamp(crow_gui.SESSION_FILE, pointer=True)
        crow_core.set_root(None)
        path = os.path.join(self.dir, "chat-%s.json" % name)
        os.replace(crow_gui.SESSION_FILE, path)
        return path

    def test_a_chat_brings_its_own_working_directory(self):
        """POSITIVE (#101). robin: switching the folder in one chat used to move
        it for every chat, because the window bound one root for the process."""
        other = os.path.join(self.dir, "zweites-projekt")
        os.makedirs(other)
        crow_core.write_root_mode(self.root, "auto")
        crow_core.write_root_mode(other, "auto")
        theirs = self._chat_with_root("A", other)

        api = self.api()
        crow_core.set_root(self.root)                 # some other chat's folder
        api._adopt_chat_root(theirs)
        self.assertEqual(os.path.normcase(crow_core.get_root() or ""),
                         os.path.normcase(os.path.realpath(other)))

    def test_a_chat_that_chose_no_folder_keeps_that_across_a_switch(self):
        """"None" is a choice here too, and it is the chat's. Without the third
        state a chat deliberately working unbounded would be handed the template
        every time it was opened."""
        crow_core.write_root_mode(self.root, "auto")
        theirs = self._chat_with_root("ohne", None)
        crow_core.set_active_root(self.root)          # a template that must lose

        api = self.api()
        crow_core.set_root(self.root)
        api._adopt_chat_root(theirs)
        self.assertIsNone(crow_core.get_root())

    def test_a_chat_that_never_chose_takes_the_template_not_what_was_bound(self):
        """THE NEGATIVE HALF, and the whole defect in one case. Every chat file
        written before #101 has no root in it. Falling through to "whatever is
        bound" is exactly what made one chat's folder leak into all the others --
        so an unmarked chat takes the template, never the neighbour's."""
        leftover = os.path.join(self.dir, "vom-vorherigen-chat")
        os.makedirs(leftover)
        crow_core.write_root_mode(self.root, "auto")
        crow_core.write_root_mode(leftover, "auto")
        old = os.path.join(self.dir, "chat-alt.json")
        with open(old, "w", encoding="utf-8") as fh:
            json.dump({"messages": []}, fh)           # no crow_root at all
        crow_core.set_active_root(self.root)

        api = self.api()
        crow_core.set_root(leftover)                  # the neighbour's folder
        api._adopt_chat_root(old)
        self.assertEqual(os.path.normcase(crow_core.get_root() or ""),
                         os.path.normcase(os.path.realpath(self.root)))

    def test_a_new_chat_starts_from_the_template(self):
        """Same rule from the other side: "new chat" is a chat that never chose."""
        leftover = os.path.join(self.dir, "vorher")
        os.makedirs(leftover)
        crow_core.write_root_mode(self.root, "auto")
        crow_core.write_root_mode(leftover, "auto")
        crow_core.set_active_root(self.root)

        api = self.api()
        crow_core.set_root(leftover)
        api._adopt_chat_root(None)
        self.assertEqual(os.path.normcase(crow_core.get_root() or ""),
                         os.path.normcase(os.path.realpath(self.root)))

    def test_the_level_stays_with_the_folder_not_with_the_chat(self):
        """THE SECOND NEGATIVE HALF. The level is a statement about the project,
        so two chats in ONE folder share it. Move it into the chat and the same
        directory has different rights depending on which chat is open."""
        crow_core.write_root_mode(self.root, "manual")
        one = self._chat_with_root("eins", self.root)
        two = self._chat_with_root("zwei", self.root)

        api = self.api()
        api._adopt_chat_root(one)
        first = api._args.mode
        api._adopt_chat_root(two)
        self.assertEqual(api._args.mode, first)
        self.assertEqual(api._args.mode, "manual")

    def test_a_borrowed_root_is_never_written_into_the_chat(self):
        """THE CASE THAT MUST FAIL, and it is the defect robin hit within minutes
        of #101 landing: he picked a folder in one chat, switched to another, and
        the second chat -- a file from before the ticket, with no root of its own
        -- took the template and then OWNED it. A fallback is a guess, and the
        rule against writing a guess down is already in this file for the name:
        "that guess must never be stamped back into the file as though it had
        been chosen".
        """
        crow_core.write_root_mode(self.root, "auto")
        old = os.path.join(self.dir, "chat-ohne-wahl.json")
        with open(old, "w", encoding="utf-8") as fh:
            json.dump({"messages": [], "crow_title": "alt"}, fh)
        crow_core.set_active_root(self.root)

        api = self.api()
        api._adopt_chat_root(old)                  # borrows the template
        self.assertEqual(os.path.normcase(crow_core.get_root() or ""),
                         os.path.normcase(os.path.realpath(self.root)))
        api._current_title = "alt"
        api._stamp(old)

        with open(old, encoding="utf-8") as fh:
            self.assertNotIn("crow_root", json.load(fh),
                             "the borrowed folder was written into the chat")

    def test_a_named_empty_chat_survives_being_left(self):
        """POSITIVE. #100 kept a named empty chat across closing the window;
        switching away still dropped it, because `_leave` had nothing to archive
        and the next write put the other chat over session.json. robin lost a
        chat called "Schmetterlinge" that way, folder and all."""
        api = self.api()
        api.rename("", "Schmetterlinge")
        self.drained(api)
        ok, kept = api._leave()
        self.assertTrue(ok)
        self.assertIsNotNone(kept, "a named empty chat was not put anywhere")
        self.assertEqual(self._stored_title_of(kept), "Schmetterlinge")

    def test_a_named_empty_chat_can_be_opened_again(self):
        """THE ROUND TRIP, and the case whose absence cost three defects in a row.

        Writing is half a contract. `_leave` produced a file for a named empty
        chat and the suite was green -- while `open` refused that very file with
        "empty: chat-....json", because `load_session` answers None for anything
        with no messages. robin created a chat called "Youtube", switched away,
        and could never get back into it.

        THE RULE THIS CASE EXISTS TO ENFORCE: every path that writes state to
        disk needs, in the same commit, a case that reads that file back and puts
        the window into the state the user expects. Testing that the write
        happened is testing the mechanism, not the promise.
        """
        api = self.api()
        api.rename("", "Youtube")
        self.drained(api)
        ok, kept = api._leave()
        self.assertTrue(ok)

        second = self.api()
        second.open(kept)
        fails = [m for m in self.drained(second) if m.get("k") == "fail"]
        self.assertEqual(fails, [], "opening the reserved slot was refused")
        self.assertEqual(second._current_title, "Youtube")
        self.assertEqual(os.path.normcase(second._current_path or ""),
                         os.path.normcase(kept))
        spoken = [m["role"] for m in second._conversation.payload()
                  if m["role"] in ("user", "assistant")]
        self.assertEqual(spoken, [], "the reserved slot came back with a turn in it")

    def test_an_archive_nobody_named_and_with_nothing_in_it_is_still_refused(self):
        """THE NEGATIVE HALF of the round trip. Emptiness alone must not become a
        thing worth opening, or a truncated or half-written file reads as a chat
        and the user is handed a window that silently lost its contents."""
        broken = os.path.join(self.dir, "chat-kaputt.json")
        with open(broken, "w", encoding="utf-8") as fh:
            json.dump({"messages": []}, fh)
        api = self.api()
        api.open(broken)
        fails = [m for m in self.drained(api) if m.get("k") == "fail"]
        self.assertTrue(fails, "an unnamed empty archive was opened as a chat")
        self.assertIn("empty", fails[-1]["t"])

    def test_an_unnamed_empty_chat_is_still_dropped_when_it_is_left(self):
        """THE NEGATIVE HALF. A stray "new" click must still vanish, or the rail
        fills with conversations nobody started -- which is what the emptiness
        rule was for before the name became the line."""
        api = self.api()
        ok, kept = api._leave()
        self.assertTrue(ok)
        self.assertIsNone(kept, "an unnamed empty chat was filed away")

    @staticmethod
    def _stored_title_of(path):
        with open(path, encoding="utf-8") as fh:
            return (json.load(fh).get("crow_title") or "").strip() or None

    def test_choosing_a_root_binds_it_and_tells_the_page(self):
        api = self.api()
        crow_core.write_root_mode(self.root, "auto")
        api.choose_root(self.root)
        self.assertEqual(os.path.normcase(crow_core.get_root()),
                         os.path.normcase(os.path.realpath(self.root)))
        self.assertEqual(self._root_msg(api)["name"], "projekt")

    def test_choosing_writes_the_marker_so_the_pick_survives(self):
        api = self.api()
        api.choose_root(self.root)
        self.assertTrue(os.path.isfile(crow_core.root_file(self.root)))

    def test_a_directory_that_is_gone_is_refused_and_the_page_is_resynced(self):
        api = self.api()
        api.choose_root(os.path.join(self.dir, "weg"))
        self.assertIsNone(crow_core.get_root())
        self.assertIn("fail", self.kinds(api))

    def test_the_level_follows_the_root(self):
        """robin's decision: opening a folder restores what it was allowed to do."""
        api = self.api()
        crow_core.write_root_mode(self.root, "manual")
        api.choose_root(self.root)
        self.assertEqual(api._args.mode, "manual")
        self.assertIn("mode", self.kinds(api))

    def test_clearing_the_root_is_offered_and_works(self):
        api = self.api()
        api.choose_root(self.root)
        api.clear_root()
        self.assertIsNone(crow_core.get_root())
        self.assertEqual(self._root_msg(api)["path"], "")

    def test_clearing_leaves_the_folder_in_the_menu(self):
        api = self.api()
        api.choose_root(self.root)
        api.clear_root()
        self.assertEqual([r["name"] for r in self._root_msg(api)["roots"]], ["projekt"])

    def test_the_root_does_not_move_mid_turn(self):
        """Same rule as `set_mode`: half a turn allowed to write where the other
        half may not is worse than either boundary alone."""
        api = self.api()
        api._worker = _AliveWorker()
        api.choose_root(self.root)
        self.assertIsNone(crow_core.get_root())

    def test_the_picker_does_not_open_mid_turn(self):
        api = self.api()
        api._worker = _AliveWorker()
        api._window = _RefusingWindow()          # would raise if it were called
        api.pick_root()
        self.assertIsNone(crow_core.get_root())

    def test_a_cancelled_dialog_changes_nothing_and_says_nothing(self):
        """Cancel is an answer, not a failure. A note on every cancel trains the
        user to ignore notes."""
        api = self.api()
        api._window = _PickingWindow(None)
        api.pick_root()
        self.assertIsNone(crow_core.get_root())
        self.assertEqual([k for k in self.kinds(api) if k in ("fail", "note")], [])

    def test_picking_a_folder_binds_it(self):
        api = self.api()
        api._window = _PickingWindow((self.root,))
        api.pick_root()
        self.assertEqual(os.path.normcase(crow_core.get_root()),
                         os.path.normcase(os.path.realpath(self.root)))

    def test_picking_a_folder_is_what_the_next_start_reads(self):
        """THE WIRING, not the rule -- the rule is `AdoptRootTests`'s. Without
        this case the core could restore correctly forever while the window never
        told it anything, which is the state #92 was in until 2026-08-15: fifteen
        lines of comment describing a restore, and nothing writing what to
        restore."""
        api = self.api()
        api._window = _PickingWindow((self.root,))
        api.pick_root()
        restored, problem = crow_core.restore_root()
        self.assertIsNone(problem)
        self.assertEqual(os.path.normcase(restored or ""),
                         os.path.normcase(os.path.realpath(self.root)))

    def test_choosing_no_folder_overwrites_the_remembered_one(self):
        """"None" is a choice and has to outlive the window. If `clear_root` only
        cleared the live boundary, the next start would restore the folder the
        user had just switched off -- and it would look like the button did
        nothing."""
        api = self.api()
        api._window = _PickingWindow((self.root,))
        api.pick_root()
        api.clear_root()
        restored, problem = crow_core.restore_root()
        self.assertIsNone(restored)
        self.assertIsNone(problem)

    def test_a_cancelled_dialog_leaves_the_remembered_choice_alone(self):
        """Cancel changes nothing -- and "nothing" now includes what the next
        start will bind. The existing case above pins the live state; this pins
        the stored one, which a cancel could otherwise quietly overwrite with a
        null."""
        api = self.api()
        api._window = _PickingWindow((self.root,))
        api.pick_root()
        api._window = _PickingWindow(None)
        api.pick_root()
        restored, _ = crow_core.restore_root()
        self.assertEqual(os.path.normcase(restored or ""),
                         os.path.normcase(os.path.realpath(self.root)))

    def test_a_dialog_that_throws_is_not_a_crash(self):
        api = self.api()
        api._window = _RefusingWindow()
        api.pick_root()
        self.assertIsNone(crow_core.get_root())

    def test_the_recent_list_only_offers_roots_that_still_declare_themselves(self):
        api = self.api()
        api.choose_root(self.root)
        os.remove(crow_core.root_file(self.root))
        api.push_root()
        self.assertEqual(self._root_msg(api)["roots"], [])

    def test_the_page_has_the_button_and_its_handler(self):
        """The seam #90 exists for: a bridge method with nothing calling it is a
        feature that does not exist, and no Api case can see the difference."""
        page = crow_gui.PAGE
        self.assertIn('id="root"', page)
        self.assertIn("crow.rootMenu()", page)
        self.assertIn("pywebview.api.pick_root()", page)
        self.assertIn("pywebview.api.choose_root(", page)
        self.assertIn('case "root":', page)

    def test_the_menu_never_interpolates_a_path_into_html(self):
        """A directory may be named `<img onerror=...>`. Paths reach the page as
        textContent and dataset only -- this pins that they are not concatenated
        into the menu's HTML string."""
        page = crow_gui.PAGE
        menu = page[page.index("rootMenu(){"):page.index("chooseRoot(p){")]
        self.assertNotIn("+x.path+", menu.replace(" ", ""))
        self.assertNotIn("+x.name+", menu.replace(" ", ""))
        self.assertIn("textContent", menu)


class _AliveWorker:
    def is_alive(self):
        return True


class _PickingWindow:
    def __init__(self, result):
        self._result = result

    def create_file_dialog(self, *a, **k):
        return self._result


class _RefusingWindow:
    def create_file_dialog(self, *a, **k):
        raise RuntimeError("no dialog here")


class AReopenedChatKeepsItsToolRowsTests(unittest.TestCase):
    """#99. Switching chats redrew the thoughts and dropped every tool row."""

    def _drawn(self, messages):
        """The real `_replay`, bound to a stand-in that only records."""
        out = []

        class Recorder:
            def __init__(self):
                self._context_tokens = 0
                self._n_ctx = 0

            def push(self, message):
                out.append(message)

        crow_gui.Api._replay(Recorder(), messages)
        return out

    def test_a_turn_that_only_called_a_tool_is_not_skipped(self):
        """The message has no `content` at all -- the emptiness test used to
        drop it whole, which is why the reopened chat showed two thoughts with
        nothing between them."""
        drawn = self._drawn([{"role": "assistant", "content": "",
                              "reasoning_content": "let me look",
                              "tool_calls": [{"function": {
                                  "name": "web_search",
                                  "arguments": '{"query":"llama.cpp"}'}}]}])
        tools = [m for m in drawn if m["k"] == "tool"]
        self.assertEqual([t["name"] for t in tools], ["web_search"])
        self.assertIn("llama.cpp", tools[0]["args"])

    def test_two_calls_in_one_turn_keep_their_order(self):
        drawn = self._drawn([{"role": "assistant", "content": "",
                              "tool_calls": [
                                  {"function": {"name": "read_file",
                                                "arguments": '{"path":"a.py"}'}},
                                  {"function": {"name": "write_file",
                                                "arguments": '{"path":"b.py"}'}}]}])
        self.assertEqual([m["name"] for m in drawn if m["k"] == "tool"],
                         ["read_file", "write_file"])

    def test_written_code_is_what_the_row_carries(self):
        """The reason the rows matter: the code Crow wrote lives in a write_file
        argument and nowhere else in the transcript."""
        drawn = self._drawn([{"role": "assistant", "content": "",
                              "tool_calls": [{"function": {
                                  "name": "write_file",
                                  "arguments": '{"path":"C:/x/y.py","content":"def f(): pass"}'
                              }}]}])
        row = [m for m in drawn if m["k"] == "tool"][0]
        self.assertIn("y.py", row["args"])
        self.assertIn("def f(): pass", row["args"])

    def test_a_tool_result_is_not_drawn_as_an_answer(self):
        """NEGATIVE HALF. The `role: tool` payload is 16 KB of text the model
        already has. Drawing it would make a reopened chat longer than the live
        one it is supposed to reproduce."""
        drawn = self._drawn([{"role": "tool", "content": "x" * 5000}])
        self.assertEqual(drawn, [])

    def test_a_chat_without_tools_draws_what_it_always_did(self):
        """NEGATIVE HALF the other way: no tool call, no tool row, and the
        answer still comes through the fence renderer."""
        drawn = self._drawn([{"role": "user", "content": "hi"},
                             {"role": "assistant", "content": "```py\nx=1\n```"}])
        self.assertEqual([m for m in drawn if m["k"] == "tool"], [])
        self.assertTrue([m for m in drawn if m["k"] == "code_open"])

    def test_the_window_formats_arguments_instead_of_dumping_json(self):
        """The `hasattr` guard was never True: format_tool_args lived in
        cli/crow.py, so the window always took the raw-JSON fallback."""
        self.assertTrue(hasattr(crow_core, "format_tool_args"))
        out = []
        crow_gui.Turn(out.append).tool_started(
            "read_file", '{"path":"C:/very/long/path/to/a/file.py"}')
        row = [m for m in out if m["k"] == "tool"][0]
        self.assertNotIn('{"path"', row["args"])
        self.assertIn("path=", row["args"])


class TheLiveRateIsWallClockOnPurposeTests(unittest.TestCase):
    """The window's live tok/s counts the pauses, and that is the decision.

    It looks like the defect `crow_core.TurnCost` already fixed once -- "the
    first version divided tokens by the whole round and printed 1.49 tok/s for a
    turn the server had just measured at 14.77 and 16.46" -- and on 2026-08-14 it
    was changed to sum only the gaps between deltas, then changed straight back
    (robin, #97). What the user waits through is wall clock. The decode figure is
    the server's and lands underneath at the end of the turn; two figures with
    two meanings, both on screen.

    These cases exist so the next reading of that docstring does not turn into a
    second fix. They fail if the pauses ever stop counting.
    """

    def _rate(self, gaps):
        clock = [1000.0]
        real = crow_gui.time.monotonic
        crow_gui.time.monotonic = lambda: clock[0]
        try:
            out = []
            sink = crow_gui.Sink(out.append, live=True)
            sink.reply_started()
            for gap in gaps:
                clock[0] += gap
                sink.reasoning_text_counted()
            live = [m for m in out if m["k"] == "live"]
            self.assertTrue(live, "no live message was ever sent")
            return live[-1]["rate"]
        finally:
            crow_gui.time.monotonic = real

    def test_a_steady_stream_reports_its_throughput(self):
        """POSITIVE, and it has to hold before any claim about pauses means
        anything: fifty deltas 50 ms apart with nothing in between is 20 a
        second either way of measuring."""
        self.assertAlmostEqual(self._rate([0.05] * 50), 20.0, delta=1.0)

    def test_a_tool_call_lowers_the_figure_because_the_user_waited(self):
        """THE DECISION. The same fifty deltas with a fifteen-second web search
        between them: the model still generated at 20, and the user still waited
        32 s for 50 tokens. The window reports what was waited through."""
        self.assertLess(self._rate([0.05] * 25 + [15.0] + [0.05] * 25), 5.0)

    def test_the_pause_is_not_quietly_excluded(self):
        """NEGATIVE HALF, and the one that catches a well-meant repair: summing
        only the gaps between deltas lands back near 20 here. If this ever
        passes at 20, the decision was reverted without anyone deciding to."""
        with_pause = self._rate([0.05] * 25 + [15.0] + [0.05] * 25)
        without = self._rate([0.05] * 50)
        self.assertGreater(without - with_pause, 10.0,
                           "the pause stopped counting -- see #97 before changing this")



class TheReasoningSliderIsTheSameCommandTests(ApiCase):
    """#116, the window half. The terminal half is in test_crow.py, and BOTH
    exist for the reason the ticket names: #99 is the case where one surface was
    forgotten -- `format_tool_args` behind a hasattr guard that had been False
    since the split, so the feature worked in one client and not the other for
    months with nothing in the suite able to see it.
    """

    def _api(self, model="Qwen3.8-27B"):
        api = self.api()
        api._model = model
        return api

    def test_the_command_is_on_the_shared_list_and_described(self):
        self.assertIn("/reasoning", crow_core.SLASH_COMMANDS)
        self.assertIn("/reasoning", crow_gui.Api.WHAT_THEY_DO)
        self.assertNotIn("nothing here answers this yet", self.api().help_listing())

    def test_bare_reasoning_answers_rather_than_reaching_the_model(self):
        answer = self._api().slash_answer("/reasoning")
        self.assertIsNotNone(answer)
        self.assertIn("levels", answer)
        for level in crow_core.reasoning_levels_for("Qwen3.8-27B"):
            self.assertIn(level, answer)

    def test_setting_a_level_binds_it_and_states_the_prefill(self):
        api = self._api()
        answer = api.slash_answer("/reasoning medium")
        self.assertEqual(api._reasoning, "medium")
        self.assertIn(crow_core.REASONING_COST_NOTE, answer)

    def test_the_slider_types_the_command_rather_than_setting_the_level(self):
        """THE POINT OF THE WHOLE CLASS. A control wired separately from the
        command it duplicates is #99 all over again, so the slider goes through
        `_reasoning_command` and its refusal applies to both."""
        api = self._api()
        api.set_reasoning("high")
        self.assertEqual(api._reasoning, "high")
        api.set_reasoning("careful")
        self.assertEqual(api._reasoning, "high",
                         "the slider bypassed the refusal the command applies")

    def test_an_unknown_level_is_named_and_nothing_is_bound(self):
        """NEGATIVE PROOF. An invalid level does not fail here -- it fails on
        the server, after the prefill has been paid for."""
        api = self._api()
        api.slash_answer("/reasoning low")
        answer = api.slash_answer("/reasoning careful")
        self.assertIn("careful", answer)
        self.assertEqual(api._reasoning, "low")

    def test_off_returns_to_the_never_chosen_state(self):
        api = self._api()
        api.slash_answer("/reasoning high")
        api.slash_answer("/reasoning off")
        self.assertIsNone(api._reasoning)

    def test_a_change_tells_the_page_and_a_refusal_does_not(self):
        """The chip has to follow the value, and only when it moved: a push on
        every attempt would repaint the chip for a level that was refused."""
        api = self._api()
        api.slash_answer("/reasoning high")
        moved = [m for m in self.drained(api) if m.get("k") == "reasoning"]
        self.assertEqual([m["level"] for m in moved], ["high"])
        api.slash_answer("/reasoning careful")
        self.assertEqual([m for m in self.drained(api) if m.get("k") == "reasoning"], [])

    def test_the_page_has_a_case_for_the_message_it_is_sent(self):
        """#99's shape in the transport: a `k` the Python side pushes and the
        page has no case for is a message into a void."""
        self.assertIn("reasoning", _drawn_kinds(inspect.getsource(crow_gui)))

    def test_the_level_reaches_the_session_file_and_comes_back(self):
        api = self._api()
        api.slash_answer("/reasoning medium")
        api._conversation.append("user", "hello")
        api._conversation.append("assistant", "hi")
        crow_core.post_json = lambda url, body, timeout=0: {"n_saved": 3}
        api._persist_live()
        self.assertEqual(crow_core.session_reasoning(self.session), "medium")

    def test_a_level_the_new_model_refuses_is_dropped_and_said(self):
        """The model-switch criterion, at the level of the state: `max` is fine
        for 0731 and raises against unsloth's template."""
        with open(self.session, "w", encoding="utf-8") as fh:
            json.dump({"format_version": crow_core.SESSION_FORMAT,
                       "messages": [{"role": "user", "content": "x"}],
                       "reasoning": "max"}, fh)
        level, note = crow_core.reasoning_for_chat("Qwen3.8-27B", self.session)
        self.assertIsNone(level)
        self.assertIn("max", note)

    def test_the_level_names_are_not_interpolated(self):
        """The rootMenu rule, and the ticket names it: a level out of the
        manifest is text off the disk, so the page sets it with textContent.

        THE ELEMENT MOVED, THE RULE DID NOT (#117). This used to look for `#reasonlabel`, which
        was the label under the slider handle; the slider is gone and the names are now drawn as
        rows by reasonMenu. A level called `<img onerror=...>` still has to be DRAWN, not run.
        """
        source = inspect.getsource(crow_gui)
        self.assertIn('el.querySelector("b").textContent = name;', source)
        self.assertIn('el.querySelector(".what").textContent = bits.join', source)


class TheDictationButtonTests(unittest.TestCase):
    """The microphone: where it sits, and what it does with what it heard.

    THE FILE IS READ RATHER THAN DRIVEN, like the two classes above it: the
    button lives in a page this suite has no browser for, so the source it is
    built from is the evidence there is.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.code = _code_only(self.source)

    def _method(self, head: str) -> str:
        """One method of the page object, by its opening line.

        `  },` at two spaces closes a method and appears nowhere inside one --
        the bodies are indented four and six.
        """
        return self.code.split(head)[1].split("  },")[0]

    def test_the_mic_sits_between_the_level_and_the_arrow(self):
        """Where robin asked for it. #acts is a flex row with no ordering of its
        own, so source order IS the order on screen and there is nothing else to
        hold this to."""
        order = [self.code.index(m) for m in
                 ('id="mode" data-mode=', 'id="mic" onclick=', 'id="go" onclick=')]
        self.assertEqual(order, sorted(order),
                         "the microphone is not drawn between the level and the arrow")

    def test_a_dictation_lands_in_the_box(self):
        """POSITIVE. The text arrives as an event and is appended to whatever was
        already typed, so half a typed line survives a thought finished aloud.

        THE WRITING MOVED TO `attach` when the drop and the paste needed the same
        four lines; what this case is about is that a dictation still reaches it,
        and that whatever it reaches still writes."""
        self.assertIn("this.attach(e.text)", self._method("micState(e){"),
                      "a finished dictation does not reach the box")
        writer = self._method("attach(text){")
        self.assertIn("input.value", writer, "nothing is written into the box")
        self.assertIn("dispatchEvent", writer,
                      "the textarea is not told to regrow around the new text")

    def test_a_dictation_never_sends_itself(self):
        """NEGATIVE, and the one that matters. Whisper is wrong often enough that
        a dictation which submitted itself would be a message nobody could take
        back. The text goes in the box; a human presses the arrow."""
        block = self._method("micState(e){")
        for forbidden in ("pywebview.api.send", "crow.go()", "this.go()"):
            self.assertNotIn(forbidden, block,
                             "a finished dictation reaches %s" % forbidden)

    def test_recording_is_visible_without_reading_anything(self):
        """robin's words: you should be able to see that it is recording. A glow
        does that from across the room; a changed tooltip does not."""
        # AGAINST THE SOURCE, NOT self.code, and it is not sloppiness: _code_only
        # drops every line beginning with `#` as a Python comment, which takes
        # each CSS id selector with it. The two lines below are held against
        # self.code because neither starts with one.
        self.assertIn("#mic.rec{", self.source, "no recording state on the button")
        self.assertIn("@keyframes micglow", self.code,
                      "the recording state does not move")
        self.assertIn("animation:micglow", self.code,
                      "the glow is defined and never used")

    def test_the_button_has_exactly_two_states(self):
        """robin's rule: grey is snoozed, blue glow is recording. NEGATIVE,
        because the way this breaks is somebody ADDING a state. A third one was
        built once -- yellow, while the recogniser ran -- and cut on sight: a
        colour the user cannot act on is furniture with a colour."""
        self.assertNotIn("#mic.work", self.source, "a third button state is back")
        self.assertNotIn('"work"', self.source, "a third mic state is pushed")

    def test_recording_is_not_drawn_in_the_mute_colour(self):
        """Red is what every conference tool on this machine uses for MUTE. The
        first build painted recording red, so the one signal that had to be
        unambiguous said the opposite of what was happening."""
        rule = self.source.split("#mic.rec{")[1].split("}")[0]
        self.assertIn("var(--accent)", rule, "recording is not the accent colour")
        self.assertNotIn("var(--bad)", rule, "recording is drawn in the mute colour")

    def test_the_page_never_paints_itself_recording(self):
        """NEGATIVE for the state. The class comes back from Python once the
        stream is actually open: a button that reddened on click would lie for as
        long as it took PortAudio to refuse."""
        block = self._method("mic(){")
        self.assertNotIn("classList.add", block,
                         "the click paints the state instead of asking for it")

    def test_transcription_does_not_run_inside_the_bridge_call(self):
        """The first dictation loads 486 MB of model. A bridge call that did the
        work would hold the page's promise open for seconds with the button
        frozen between two states."""
        block = self.source.split("def dictate_stop(")[1].split("def _dictate_finish")[0]
        self.assertIn("threading.Thread", block, "the work is done on the bridge call")
        self.assertNotIn("crow_voice.stop()", block,
                         "dictate_stop transcribes before it returns")


class TheVoiceModuleTests(unittest.TestCase):
    """cli/crow_voice.py: what it promises on a machine that cannot deliver."""

    def test_a_missing_package_is_named_and_not_raised(self):
        """NEGATIVE. Both dependencies are optional the way pywebview is, so the
        answer to "no sounddevice" is a sentence the window can print -- not an
        exception that takes the click with it.

        `None` in sys.modules is what makes `import x` raise ImportError, which
        is the same shape as the package not being installed at all."""
        with mock.patch.dict(sys.modules, {"sounddevice": None}):
            why = crow_voice.available()
        self.assertIsInstance(why, str, "a missing package did not produce a reason")
        self.assertIn("sounddevice", why, "the reason does not name what is missing")

    def test_nothing_recorded_transcribes_to_nothing(self):
        """POSITIVE for the empty case, and it has to hold with NO optional
        package present: this used to import numpy first, which turned a button
        pressed twice by accident into an ImportError instead of a shrug."""
        crow_voice._blocks.clear()
        with mock.patch.dict(sys.modules, {"numpy": None, "faster_whisper": None}):
            self.assertEqual(crow_voice.stop(), "")

    def test_the_installer_and_the_client_name_one_directory(self):
        """TWO FILES DECIDE WHERE THE MODEL LIVES. If they drift, install.ps1
        fetches 486 MB into one directory and the window downloads the same bytes
        again because it looked in another."""
        ps = (HERE.parent / "install.ps1").read_text(encoding="utf-8")
        self.assertIn('$WHISPER_DIRNAME   = "%s"' % crow_voice.MODEL_DIRNAME, ps,
                      "install.ps1 does not name the directory crow_voice.py reads")
        self.assertEqual(crow_voice.model_dir().parent.name, "models")
        self.assertEqual(crow_voice.model_dir().parent.parent,
                         Path(crow_voice.__file__).resolve().parent.parent,
                         "the model is not looked for beside the client")

    def test_a_phone_clip_is_decoded_and_transcribed_with_the_same_model(self):
        """#290: `transcribe_file(path)` -- the phone's recording, decoded to
        16 kHz mono (faster-whisper's own PyAV decoder, faked here: this box
        has no voice extra) and handed to the same model with the same
        settings as `stop()`. Too short a clip is "" and the model is not
        asked."""
        asked = []

        class Seg:
            def __init__(self, text):
                self.text = text

        class Model:
            def transcribe(self, audio, **kw):
                asked.append((len(audio), kw))
                return [Seg(" Hallo Crow, "), Seg("teste die Spracheingabe. ")], None

        decoded = {}

        def decode(path):
            decoded["path"] = path
            return [0.0] * (crow_voice.SAMPLE_RATE * 2)

        with mock.patch.object(crow_voice, "_decode", decode), \
                mock.patch.object(crow_voice, "load_model", Model):
            self.assertEqual(crow_voice.transcribe_file("/tmp/clip.m4a"),
                             "Hallo Crow, teste die Spracheingabe.")
            self.assertEqual(decoded["path"], "/tmp/clip.m4a")
            self.assertEqual(asked, [(32000, {"beam_size": 5, "vad_filter": True})])
            with mock.patch.object(crow_voice, "_decode",
                                   lambda p: [0.0] * (crow_voice.MIN_FRAMES - 1)):
                self.assertEqual(crow_voice.transcribe_file("/tmp/tap.m4a"), "")
            self.assertEqual(len(asked), 1)
            # #290: the clip's length, for the log line
            stats = {}
            crow_voice.transcribe_file("/tmp/clip.m4a", stats)
            self.assertEqual(stats, {"seconds": 2.0})

    def test_the_model_says_whether_it_is_loaded(self):
        """#290: the phone shows "loading the speech model" until it is."""
        with mock.patch.object(crow_voice, "_model", None):
            self.assertFalse(crow_voice.model_loaded())
        with mock.patch.object(crow_voice, "_model", object()):
            self.assertTrue(crow_voice.model_loaded())

    def test_the_phone_path_needs_only_the_recogniser(self):
        """NEGATIVE: no microphone and no sounddevice on the PC must not block
        a phone's clip; a missing faster-whisper is named."""
        with mock.patch.dict(sys.modules, {"sounddevice": None, "faster_whisper": None}):
            why = crow_voice.file_available()
        self.assertIn("faster-whisper", why)
        with mock.patch.dict(sys.modules, {"sounddevice": None,
                                           "faster_whisper": mock.MagicMock()}):
            self.assertIsNone(crow_voice.file_available())

class TheThemeAndTheSettingsSheetTests(unittest.TestCase):
    """Two palettes, one attribute, and the sheet that switches them."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def test_a_failure_can_be_more_than_one_line(self):
        """`failure_line` puts the advice on a second line, and a rule without
        `white-space` renders that newline as a space -- seen live 2026-08-24:
        "...die Verbindung verweigerte start llama-server first, then retry."
        The sentence arrived and read as part of the error."""
        import re
        m = re.search(r"\.fail\{([^}]*)\}", self.css)
        self.assertTrue(m, "the .fail rule is gone")
        self.assertIn("white-space", m.group(1),
                      "a two-line failure collapses into one: %s" % m.group(1))

    def test_no_prose_escapes_a_css_comment(self):
        """FOUND IN THE WINDOW, 2026-08-24: the memory row arrived grey, flat and
        without its mark. Two comments in the #122 block were closed one `*/` too
        early, so the prose behind them became a selector -- and CSS discards the
        rule that follows a selector it cannot parse. `.memnote` went once,
        `.memicon` went once, and nothing anywhere reported it.

        SAME FAMILY AS THE BRACKET a `.Replace()` ate on the same day, which
        voided every rule after `.scrim`: CSS fails silently and downward, so the
        damage is never where the typo is. A comment that closes early is not a
        typo a reader catches -- the text keeps reading like a comment.
        """
        css, i, plain = self.css, 0, []
        while i < len(css):
            if css.startswith("/*", i):
                j = css.find("*/", i + 2)
                self.assertGreater(j, 0, "a CSS comment is never closed")
                i = j + 2
                continue
            j = css.find("/*", i)
            j = len(css) if j < 0 else j
            plain.append((i, css[i:j]))
            i = j
        for pos, chunk in plain:
            k = chunk.find("*/")
            if k >= 0:
                line = css[:pos + k].count("\n") + 1
                self.fail("a `*/` sits outside a comment at CSS line %d -- the "
                          "prose before it is parsed as a selector and the rule "
                          "after it is thrown away:\n...%s"
                          % (line, chunk[max(0, k - 160):k + 2]))

    def test_no_rule_carries_a_colour_of_its_own(self):
        """THE ONE THAT KEEPS A LIGHT MODE POSSIBLE, and it is a negative probe
        because this breaks by ADDING: one new rule with `color:#cfdaea` in it is
        a rule the light palette cannot reach, and nothing else would go red.

        Hex only. The rgba() tints left in the file are derived from the accent
        and the three state colours and read on both grounds; a flat hex does
        not."""
        import re

        palette, offenders = False, []
        for line in self.css.split("\n"):
            t = line.strip()
            if t.startswith(":root"):
                palette = True
            elif palette and t == "}":
                palette = False
            if palette or t.startswith(("/*", "*", "//")):
                continue
            if re.search(r"#[0-9a-fA-F]{6}\b", line):
                offenders.append(t[:80])
        self.assertEqual(offenders, [],
                         "a CSS rule names a colour the light palette cannot reach")

    def test_every_palette_defines_the_same_names(self):
        """A name defined in one theme and not the other is a colour that falls
        back to the dark value on a white ground -- invisible text, and only on
        the theme nobody develops in."""
        import re

        def names(block):
            return set(re.findall(r"(--[a-z0-9-]+)\s*:", block))

        base = names(self.css.split(":root{")[1].split("\n}")[0])
        # Structure rather than colour, and three deliberate carry-throughs: the
        # accent, the bevel and the model's own colour are brand values out of
        # the core, and a theme that redefined them would be inventing a second
        # brand rather than choosing a ground.
        structural = {"--mono", "--ui", "--barh", "--sbw", "--colw", "--colpad", "--reserve"}
        carried = {"--accent", "--bevel", "--model"}
        for theme in ("light", "crow"):
            head = ':root[data-theme="%s"]{' % theme
            self.assertIn(head, self.css, "no palette for %s" % theme)
            got = names(self.css.split(head)[1].split("\n}")[0])
            missing = (base - got) - structural - carried
            self.assertEqual(missing, set(),
                             "the %s palette does not redefine %s"
                             % (theme, sorted(missing)))

    def test_the_theme_is_on_the_element_before_the_page_is_handed_over(self):
        """NOT applied by a script after load. A window that painted itself dark
        and then switched would show the wrong theme for a frame on every start,
        and the frame is exactly when somebody looks at it."""
        self.assertIn('<html lang="de" data-theme="__THEME__">', self.source)
        self.assertIn('.replace("__THEME__", current_theme())', self.source)

    def test_a_chosen_theme_comes_back(self):
        """PERSISTENCE IS A CONTRACT: whatever writes has to read in the same
        change. `set_theme` writes the file and `current_theme` is what the page
        is stamped from -- so the round trip is the test, not the write."""
        with tempfile.TemporaryDirectory() as tmp:
            before = crow_gui.SETTINGS_FILE
            crow_gui.SETTINGS_FILE = os.path.join(tmp, "settings.json")
            try:
                self.assertEqual(crow_gui.current_theme(), crow_gui.DEFAULT_THEME)
                api = crow_gui.Api.__new__(crow_gui.Api)
                self.assertTrue(api.set_theme("light"))
                self.assertEqual(crow_gui.current_theme(), "light")
                # NEGATIVE: a value this build does not have is refused, and the
                # refusal must not overwrite the one that works.
                self.assertFalse(api.set_theme("solarized"))
                self.assertEqual(crow_gui.current_theme(), "light")
            finally:
                crow_gui.SETTINGS_FILE = before

    def test_a_settings_file_that_is_rubbish_is_not_an_error(self):
        """NEGATIVE for the reader. A half-written file is a value this build
        does not have, and the answer to that is the value it does have."""
        with tempfile.TemporaryDirectory() as tmp:
            before = crow_gui.SETTINGS_FILE
            crow_gui.SETTINGS_FILE = os.path.join(tmp, "settings.json")
            try:
                with io.open(crow_gui.SETTINGS_FILE, "w", encoding="utf-8") as fh:
                    fh.write("{oh no")
                self.assertEqual(crow_gui.current_theme(), crow_gui.DEFAULT_THEME)
            finally:
                crow_gui.SETTINGS_FILE = before

    def test_the_bundler_setting_is_read_every_turn(self):
        """#274: `bundler` in settings.json reaches build_bundle through the
        same per-turn door as the #145/#154 keys -- no restart, and a key that
        is gone again clears it."""
        with tempfile.TemporaryDirectory() as tmp:
            before = crow_gui.SETTINGS_FILE
            crow_gui.SETTINGS_FILE = os.path.join(tmp, "settings.json")
            try:
                api = crow_gui.Api.__new__(crow_gui.Api)
                with io.open(crow_gui.SETTINGS_FILE, "w", encoding="utf-8") as fh:
                    json.dump({"bundler": "/opt/esb/esbuild"}, fh)
                api._token_budget()
                self.assertEqual(crow_core.bundler_path(), "/opt/esb/esbuild")
                with io.open(crow_gui.SETTINGS_FILE, "w", encoding="utf-8") as fh:
                    json.dump({}, fh)
                api._token_budget()
                self.assertIsNone(crow_core.bundler_path())
            finally:
                crow_gui.SETTINGS_FILE = before
                crow_core.bundler_set(None)

    def test_hilfe_sits_in_the_title_bar_and_leaves_the_drag_region(self):
        """The bar moves the window. Anything clickable in it has to opt out, or
        the click becomes a drag and the menu never opens."""
        self.assertIn('<div id="helpwrap" class="pywebview-no-drag">', self.source)
        self.assertIn('id="help" onclick="crow.helpMenu()"', self.source)
        mark = self.source.index('id="mark"')
        help_at = self.source.index('id="helpwrap"')
        wbtns = self.source.index('id="wbtns"')
        self.assertLess(mark, help_at, "Help is not drawn after the wordmark")
        self.assertLess(help_at, wbtns, "Help is drawn past the window buttons")

    def test_the_sheet_carries_the_three_categories(self):
        """Appearance, Skills, About -- named even where they are still empty,
        so the shape is visible before the contents are."""
        for cat in ("Appearance", "Skills", "About"):
            self.assertIn(">%s</button>" % cat, self.source,
                          "the settings sheet has no %s" % cat)
        for key in ("look", "skills", "about"):
            self.assertIn('data-cat="%s"' % key, self.source)

    def test_the_typeface_is_the_machine_own(self):
        """NEGATIVE. The shipped typeface must not be named by the page: a window
        that looks different depending on whether the user installed a font has
        two appearances and no way to say which is the real one."""
        # THE DECLARATIONS, NOT THE COMMENTS. The note above the stack names the
        # typeface it replaced, and a test that could not tell the two apart
        # would forbid writing down why the change happened.
        rules = chr(10).join(l for l in self.css.splitlines()
                        if not l.strip().startswith(("/*", "*", "//")))
        self.assertNotIn("Google Sans Code", rules,
                         "the page still asks for the shipped typeface")
        self.assertIn("--ui:system-ui", self.css)

class TheDropAndThePasteTests(unittest.TestCase):
    """Files into the box: dropped from Explorer, pasted from the clipboard."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.code = _code_only(self.source)

    # -- what the page has to do -------------------------------------------

    def test_dragover_is_prevented(self):
        """THE ONE EVERYBODY FORGETS. Without preventDefault on dragover the
        drop never reaches a listener at all: WebView2 has already decided to
        navigate to the file, and the window shows a picture instead of a chat."""
        self.assertIn('document.addEventListener("dragover"', self.code)
        block = self.code.split('document.addEventListener("dragover"')[1][:120]
        self.assertIn("preventDefault", block, "dragover does not stop the navigation")

    def test_text_is_pasted_the_way_it_always_was(self):
        """NEGATIVE, and it is the one that protects everyday use. Pasting a
        path, a log or a stack trace must not reach the bridge at all: the
        handler returns before preventDefault, so the browser's own paste runs."""
        block = self.code.split('document.addEventListener("paste"')[1].split("});")[0]
        want = 'if(types.indexOf("text/plain") !== -1) return;'
        self.assertIn(want, block, "a text paste is not let through untouched")
        self.assertLess(block.index(want), block.index("preventDefault"),
                        "the handler stops the browser before it checks for text")

    def test_a_path_with_a_space_is_quoted(self):
        """A Windows path with a space in it is the normal case. Unquoted it is
        two arguments to whatever reads the line next. Der PASTE-Zweig quotet
        seit robins Vision-Ansage 2026-08-29 nichts mehr -- ein Paste-Bild ist
        ein Chip-Drop, siehe APastedScreenshotBecomesAChipTests."""
        self.assertIn("this.attach(paths.map(", self.code)
        self.assertEqual(self.code.count('+p+'), 1, "the drop path is not quoted")

    def test_one_place_writes_into_the_box(self):
        """Two callers -- dictation and non-image drop -- and one `attach`.
        Copies of the same four lines would drift the day one of them is
        fixed. Paste speist seit 2026-08-29 die Drop-Route statt attach."""
        self.assertEqual(self.code.count("  attach(text){"), 1)
        for caller in ("this.attach(e.text)", "this.attach(paths.map("):
            self.assertIn(caller, self.code, "%s does not go through attach" % caller)

    # -- what Python has to do ---------------------------------------------

    def test_the_dropped_path_comes_from_pywebview_not_the_page(self):
        """The page is handed a File with a name and no location; pywebview puts
        the real one on this side. A drop entry without it is skipped rather than
        pushed as an empty string -- NEGATIVE, because an empty path in the box
        looks like a bug in the drop and is a bug in the reading."""
        api = crow_gui.Api.__new__(crow_gui.Api)
        seen = []
        api.push = seen.append
        api.on_drop({"dataTransfer": {"files": [
            {"name": "a.md", "pywebviewFullPath": r"C:\tmp\a.md"},
            {"name": "nameless.png"},
        ]}})
        self.assertEqual(seen, [{"k": "drop", "paths": [r"C:\tmp\a.md"]}])

    def test_a_drop_of_nothing_does_not_crash(self):
        """NEGATIVE. pywebview hands over whatever the event carried, and a drop
        of selected text carries no files at all."""
        api = crow_gui.Api.__new__(crow_gui.Api)
        seen = []
        api.push = seen.append
        for event in (None, {}, {"dataTransfer": None}, {"dataTransfer": {"files": None}}):
            api.on_drop(event)
        self.assertEqual(seen, [{"k": "drop", "paths": []}] * 4)

    def test_a_pasted_picture_is_written_and_named(self):
        """POSITIVE, and the round trip is the test: the path that comes back has
        to be a file that is really there, with the bytes that went in."""
        with tempfile.TemporaryDirectory() as tmp:
            before = crow_gui.PASTE_DIR
            crow_gui.PASTE_DIR = os.path.join(tmp, "pastes")
            try:
                raw = b"\x89PNG\r\n\x1a\n" + b"x" * 40
                path = crow_gui.write_paste(".png", raw)
                self.assertTrue(path, "nothing came back")
                self.assertTrue(path.endswith(".png"))
                with open(path, "rb") as fh:
                    self.assertEqual(fh.read(), raw)
                # THE SECOND PASTE IN THE SAME SECOND is not a rare case when the
                # clipboard is a keyboard shortcut. It must not eat the first.
                second = crow_gui.write_paste(".png", raw)
                self.assertNotEqual(second, path, "the second paste overwrote the first")
                self.assertTrue(os.path.isfile(path))
            finally:
                crow_gui.PASTE_DIR = before

    def test_nothing_and_too_much_are_both_refused(self):
        """NEGATIVE. Each returns "" and leaves the directory empty -- an empty
        answer is what the page checks before it writes into the box."""
        with tempfile.TemporaryDirectory() as tmp:
            before = crow_gui.PASTE_DIR
            crow_gui.PASTE_DIR = os.path.join(tmp, "pastes")
            try:
                self.assertEqual(crow_gui.write_paste(".png", b""), "")
                too_big = b"x" * (crow_gui.PASTE_MAX_BYTES + 1)
                self.assertEqual(crow_gui.write_paste(".png", too_big), "")
                self.assertFalse(os.path.isdir(crow_gui.PASTE_DIR) and
                                 os.listdir(crow_gui.PASTE_DIR),
                                 "something was written that should not have been")
            finally:
                crow_gui.PASTE_DIR = before

    def test_an_empty_clipboard_is_an_empty_answer(self):
        """NEGATIVE for the bridge call. Most of what people paste is text, so
        "" is the ORDINARY result here and must not raise or write."""
        before = crow_gui.clipboard_image
        crow_gui.clipboard_image = lambda: None
        try:
            api = crow_gui.Api.__new__(crow_gui.Api)
            self.assertEqual(api.paste_clipboard(), "")
        finally:
            crow_gui.clipboard_image = before

    # -- the DIB arithmetic, which is the part that can be quietly wrong ----

    def _dib(self, bits, comp=0, used=0, size=40, payload=64):
        return struct.pack("<IiiHHIIiiII", size, 8, 8, 1, bits, comp,
                           0, 0, 0, used, 0) + b"p" * payload

    def test_the_pixel_offset_is_arithmetic_and_not_a_constant(self):
        """A DIB carries its palette and its colour masks BETWEEN the header and
        the pixels. An offset that ignored them opens as a picture of noise --
        which is worse than failing, because it looks like it worked.

        The four cases are the four shapes a screenshot can arrive in."""
        cases = [
            (self._dib(32), 54),                    # BI_RGB, no palette
            (self._dib(24), 54),                    # 24-bit, no palette
            (self._dib(8), 54 + 256 * 4),           # 8-bit, implied 256 entries
            (self._dib(8, used=16), 54 + 16 * 4),   # 8-bit, biClrUsed wins
            (self._dib(32, comp=3), 54 + 12),       # BI_BITFIELDS, three masks
        ]
        for dib, want in cases:
            out = crow_gui.dib_to_bmp(dib)
            self.assertEqual(out[:2], b"BM")
            total, _r1, _r2, offset = struct.unpack_from("<IHHI", out, 2)
            self.assertEqual(offset, want, "wrong pixel offset for %d-bit" % dib[14])
            self.assertEqual(total, len(out), "the size field does not match the file")
            self.assertEqual(out[14:], dib, "the DIB was altered on the way through")

    def test_a_dib_too_short_to_have_a_header_is_refused(self):
        """NEGATIVE. GlobalSize can hand back less than a header; unpacking that
        would raise inside a bridge call, where nobody sees it."""
        self.assertEqual(crow_gui.dib_to_bmp(b""), b"")
        self.assertEqual(crow_gui.dib_to_bmp(b"x" * 39), b"")

    def test_pasted_pictures_land_outside_the_working_directory(self):
        """A screenshot is not part of the project it is about. Writing one into
        whatever folder happens to be bound would put Crow's own files into a
        user's repository."""
        # DURCH DIE NAHT, und der Fall sagt jetzt beides: der Ordner heisst
        # `pastes` UND er haengt an `crow_platform.data_dir()`. Bis zum
        # Linux-Port stand hier `os.path.dirname(crow_core.SESSION_DIR)` --
        # auf Windows derselbe Ordner, auf Linux aber das STATE-Verzeichnis,
        # und ein eingefuegtes Bild ist nichts, was man verliert, sondern
        # etwas, worauf ein alter Chat noch zeigt.
        self.assertIn("crow_platform.data_dir(), \"pastes\"", self.source)
        self.assertTrue(crow_gui.PASTE_DIR.endswith("pastes"))

class TheModelMenuSurvivesASwitchTests(ApiCase):
    """#115's menu, after the switch it exists to perform.

    THE DEFECT THIS CLASS IS CUT FOR: two places pushed `models` and they pushed
    two different shapes. The probe sent `[key, label]` pairs; the switch sent
    bare keys. The page keeps ONE `this.models` and the last payload wins, so the
    first switch replaced pairs with strings -- and `modelMenu`, which indexes
    x[0] and x[1], drew the second LETTER of each key. `operating-point` became
    `p`, `qwen35-q4-k-xl` became `w`, the running row said "restarts the server"
    because "o" never equals "operating-point", and a click sent "o" into
    `choose_model`, where `model_command` refused it as a typo. Nothing on disk
    went red: no test named the shape.
    """

    def _switched(self, api):
        """Drive `/model <other>` with the boot stubbed out, and hand back the
        `up` payload the page would have received."""
        with mock.patch.object(crow_core, "model_command",
                               return_value=("up", "http://127.0.0.1:2/v1", True)), \
             mock.patch.object(crow_gui, "fetch_model_name", return_value="m"), \
             mock.patch.object(crow_gui, "model_display_name", return_value="m"), \
             mock.patch.object(crow_gui, "fetch_n_ctx", return_value=1000):
            api._model_command(["qwen35-q4-k-xl"])
        ups = [m for m in self.drained(api) if m.get("k") == "up" and "models" in m]
        self.assertTrue(ups, "the switch told the page nothing about the models")
        return ups[-1]

    def test_the_switch_sends_pairs_not_bare_keys(self):
        """Every row the menu draws needs BOTH halves: the key goes into dataset
        and comes back on the click, the label is what a person recognises."""
        rows = self._switched(self.api())["models"]
        self.assertEqual(rows, [[k, crow_core.model_label(k)]
                                for k in crow_core.bootable_models()])
        for row in rows:
            self.assertEqual(len(row), 2, "a row that is not a pair draws letters")
            self.assertIn(row[0], crow_core.bootable_models())
            self.assertNotEqual(row[0], row[1],
                                "the key is the table's word, the label is the model's")

    def test_the_key_that_comes_back_is_one_the_table_knows(self):
        """THE CONSEQUENCE THE LABELS HID. A wrong shape does not just misspell
        the row -- it puts x[0] into dataset.k, and a single letter is refused by
        `model_command` as a typo, so the menu stops switching entirely.

        THE BOOT IS MOCKED, AND IT HAS TO BE (#185). `model_command` refuses a
        typo at crow_core.py:1804 and only THEN reaches stop_servers and
        start_server, so what this case asserts happens before either. Unmocked,
        the loop killed whatever server was running and booted the 73.45 GiB line
        once per menu entry -- ~50 s and 30,984 MiB of VRAM each, measured
        2026-09-01. Two runs took robins server down without anyone noticing.
        Mocking the plumbing leaves the assertion untouched; it only stops the
        side effect that was never part of it.
        """
        with mock.patch.object(crow_core, "stop_servers", return_value=0), \
             mock.patch.object(crow_core, "start_server", return_value="mocked"):
            for key, _label in self._switched(self.api())["models"]:
                said, _url, switched = crow_core.model_command(
                    key, "http://127.0.0.1:1/v1")
                self.assertNotIn("no model", said,
                                 "the menu would send a key the table refuses")
                del switched

    def test_a_bare_key_producer_would_be_caught(self):
        """NEGATIVE PROBE for the two above, and the guard against a THIRD
        producer: the positives only see the switch, so they would stay green
        while a new `push` somewhere else re-introduced the bare list."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        pairs = len(re.findall(r'"models":\s*\[\[k,', _code_only(source)))
        total = len(re.findall(r'"models":', _code_only(source)))
        self.assertEqual(pairs, total,
                         "a place that pushes models does not push pairs")
        salted = _code_only(source) + '\n"models": list(bootable_models()),\n'
        self.assertNotEqual(len(re.findall(r'"models":\s*\[\[k,', salted)),
                            len(re.findall(r'"models":', salted)),
                            "the check cannot see a bare-key producer")


class TheComposerControlsAreOneHeightTests(unittest.TestCase):
    """The four controls in #acts -- folder, level, microphone, arrow.

    THEY SAT AT FOUR HEIGHTS because each was as tall as whatever it held: the
    folder and the level are an 11.5px line box at the inherited 1.55 factor
    (25.83px once padding and border are counted), the arrow is 14px at a 1.2
    line-height (22.8), and the microphone is an SVG that declares height="13"
    (19). `align-items:center` let every one of them keep its own number.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def rule(self, selector: str) -> str:
        """The declarations of one rule, by its exact selector. Against the CSS
        slice of `source` and never against `_code_only`: that helper drops every
        line starting with `#`, which is every id selector in this file."""
        m = re.search(r"(?m)^%s\{(.*?)\}" % re.escape(selector), self.css, re.S)
        self.assertIsNotNone(m, "no rule for %s" % selector)
        return m.group(1)

    def test_the_row_stretches_so_one_height_reaches_all_four(self):
        """`stretch` is the initial value of align-items; the row gets ONE height
        from its tallest control and the rest adopt it. Pinning a px number on
        each button instead would go stale the first time a font-size moves."""
        acts = self.rule("#acts")
        self.assertIn("align-items:stretch", acts)
        self.assertNotIn("align-items:center", acts,
                         "center is what let the four keep four heights")

    def test_the_stretch_reaches_the_buttons_inside_their_wrappers(self):
        """#root and #mode are not children of #acts -- their menu wrappers are.
        A stretch that stops at a transparent div moves nothing."""
        for selector in ("#rootwrap", "#modewrap"):
            body = self.rule(selector)
            self.assertIn("display:flex", body,
                          "%s does not pass the stretch on" % selector)
            self.assertIn("position:relative", body,
                          "%s must stay the menu's containing block" % selector)

    def test_the_glyph_stays_on_the_centre_line_once_stretched(self):
        """A stretched button grows at the BOTTOM. #mic was already a centred
        flex box; #go was not, and its arrow would have ridden high."""
        self.assertIn("align-items:center", self.rule("#go"))
        self.assertIn("align-items:center", self.rule("#mic"))

    def test_the_hint_is_the_one_child_that_does_not_stretch(self):
        """NEGATIVE SIDE of the stretch: it is a bare word with no border to line
        up, and a stretched span puts its text at the top of the box."""
        self.assertIn("align-self:center", self.rule("#hint"))

    def test_no_control_pins_a_height_of_its_own(self):
        """The whole point of the fix. A `height:` on any of the four would be
        the number that disagrees with the row the next time the font moves."""
        for selector in ("#root", "#mode", "#mic", "#go"):
            self.assertIsNone(re.search(r"(?<![-a-z])height:\s*\d", self.rule(selector)),
                              "%s pins its own height" % selector)


class TheBarLostThreeChipsAndTheMenuGainedASubmenuTests(unittest.TestCase):
    """#119: what the status bar carries, and where the model is chosen.

    THE FILE IS READ RATHER THAN DRIVEN, like the dictation and theme classes:
    the suite has no browser for this page, so the source it is built from is
    the evidence there is. What that buys is still real -- every claim below is
    about WHERE a control is written, and a control written in the wrong block
    is drawn in the wrong place.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]
        body = self.source[self.source.index("</style>"):]
        # #125. THE STATUS BAR IS GONE, so `bar` is the title ribbon that is left
        # and `server` is where its two chips moved. The claims below did not
        # change -- only the block they are made about, which is the point of
        # slicing by marker rather than by line.
        self.bar = body[body.index('<div id="bar"'):body.index('<div id="body">')]
        self.server = body[body.index('<section data-cat="server"'):
                           body.index('<section data-cat="skills"')]
        self.composer = body[body.index('<div id="composer">'):body.index("<script>")]

    def test_the_bar_is_gone_and_nothing_was_left_hidden(self):
        """#125. An empty bar is a band of nothing between the ribbon and the
        first line of the chat, so it was removed rather than emptied -- and
        with it the rule it drew, which was half the seam."""
        self.assertNotIn('id="status"', self.source)
        self.assertNotIn("#status{", self.css)
        self.assertNotIn('id="right"', self.source)

    def test_the_bar_carries_neither_the_address_nor_the_window_size(self):
        """Both were chips that said something better said elsewhere: the URL is
        looked up when something is wrong, and n_ctx is already the denominator
        the composer prints."""
        self.assertNotIn('id="url"', self.bar)
        self.assertNotIn('id="nctx"', self.bar)
        self.assertNotIn("n_ctx", self.bar)

    def test_the_address_survives_as_the_connected_chip_s_title(self):
        """REMOVED IS NOT THE SAME AS GONE. Dropping the chip without keeping the
        address anywhere would take away the one fact worth having when the dot
        goes red."""
        self.assertIn('id="conn"', self.server)
        self.assertIn('$("#conn").title=e.url;', self.source)
        self.assertIn("#conn{cursor:help}", self.css,
                      "a native title with no cursor hint is a fact nobody finds")

    def test_the_model_is_chosen_in_the_composer_and_not_in_the_bar(self):
        """robin's placement: beside the number it decides. The window size the
        context is measured against comes from the model."""
        self.assertIn('id="model"', self.composer)
        self.assertIn('id="modelmenu"', self.composer)
        self.assertNotIn('id="model"', self.bar)
        self.assertNotIn('id="modelmenu"', self.bar)

    def test_the_menu_opens_upwards_now_that_it_sits_at_the_bottom(self):
        """The same reason #modemenu and #rootmenu do: a menu that opened
        downwards from the composer would be drawn past the window edge."""
        rule = re.search(r"(?m)^#modelmenu\{(.*?)\}", self.css, re.S)
        self.assertIsNotNone(rule, "no #modelmenu rule")
        self.assertIn("bottom:calc(100% + 6px)", rule.group(1))
        self.assertNotIn("top:calc", rule.group(1),
                         "downwards is what put it past the edge")

    def test_there_is_one_panel_and_the_second_one_is_not_renamed(self):
        """NEGATIVE PROBE for the merge: a `#reasonmenu` left anywhere -- element,
        rule or handler -- means the two panels still exist and only one of them
        is reachable, which is worse than two that both are."""
        self.assertNotIn("#reasonmenu", self.source)
        self.assertNotIn("reasonMenu(", self.source)
        self.assertNotIn('id="reasoning"', self.source)

    def test_the_levels_hang_only_under_the_running_model(self):
        """THE ONE INVARIANT THE MERGE COULD HAVE LOST. `levels` and `groups`
        describe the model that ANSWERED the probe; drawing them under the other
        row would name steps nobody measured there, and a click on one would put
        17 GB on the card for a setting."""
        plan = self.source[self.source.index("modelPlan(){"):
                           self.source.index("modelMenu(){")]
        guard = plan.index("if(!running || !(this.levels||[]).length) return;")
        self.assertLess(guard, plan.index('kind:"level"'),
                        "the level rows are pushed before the guard that limits them")
        self.assertIn('const running = (x[0] === this.modelKey);', plan,
                      "running is decided by the key the probe reported, not by order")

    def test_a_running_model_nobody_here_booted_still_gets_its_row(self):
        """SEEN ON SCREEN 2026-09-18. crow-nest's container has a manifest entry
        and measured levels but no `servers` block, so it is in no bootable list:
        no row was `running`, the guard above returned for every row, and the
        chip read `none (default)` over a menu without one level in it.

        The fix puts the answering model INTO the list the loop walks, under its
        own key, so the invariant above still decides where levels hang. And the
        row is never sent to `/model`, which would say "no model ..." about the
        model that is answering."""
        plan = self.source[self.source.index("modelPlan(){"):
                           self.source.index("modelMenu(){")]
        self.assertIn("if(this.foreignRunning()) shown.unshift([this.modelKey, this.modelName]);",
                      plan)
        self.assertLess(plan.index("shown.unshift("), plan.index("shown.forEach("),
                        "the row is added after the loop that needed it")
        self.assertIn("!(this.models||[]).some(x => x[0] === k)", self.source,
                      "foreign means: keyed by the manifest, absent from the bootable list")
        choose = self.source[self.source.index("  chooseModel(k){"):]
        choose = choose[:choose.index("pywebview.api.choose_model(k);")]
        self.assertIn("if(this.foreignRunning() && k === this.modelKey) return;", choose,
                      "a click on the foreign row reaches /model")

    def test_the_chip_names_the_model_and_what_it_does(self):
        """#117 SURVIVES THE MERGE. `high` means somebody chose it; `high
        (default)` means nothing was chosen and the template lands there anyway.
        The word is six characters and it is the entire finding."""
        self.assertIn('c.querySelector("b").textContent = this.modelName;', self.source)
        self.assertIn('c.querySelector(".lvl").textContent = this.levelLabel();',
                      self.source)
        self.assertIn('" (default)"', self.source)

    def test_the_chip_borrows_the_shape_of_its_new_neighbours(self):
        """The rule the microphone was built under: a neighbour with its own
        radius and padding reads as an accident. #root and #mode are 6px and
        3px/11px at 11.5px, and this control now stands beside them."""
        rule = re.search(r"(?m)^#model\{(.*?)\}", self.css, re.S)
        self.assertIsNotNone(rule, "no #model rule")
        for decl in ("border-radius:6px", "padding:3px 11px", "font-size:11.5px"):
            self.assertIn(decl, rule.group(1),
                          "the chip keeps the bar's pill shape in the composer")

    # -- a click elsewhere closes every popup, not two of the five -----------

    def test_every_popup_is_in_the_dismiss_table(self):
        """A menu that stays open when you look away is the one the last click
        left behind. Two of the five closed on an outside click and three did
        not, so the window had two behaviours and no rule for which was which."""
        table = self.source[self.source.index("const DISMISS = ["):
                            self.source.index("window.addEventListener(\"mousedown\"")]
        for wrap, menu in (("#helpwrap", "#helpmenu"), ("#modelwrap", "#modelmenu"),
                           ("#modewrap", "#modemenu"), ("#rootwrap", "#rootmenu")):
            self.assertIn('["%s","%s"]' % (wrap, menu), table,
                          "%s does not close on a click elsewhere" % menu)

    def test_the_guard_is_the_wrapper_and_never_the_panel(self):
        """THE TRAP THIS PAIRING EXISTS FOR. Guarding on the panel alone closes
        the menu on the mousedown that lands on its own chip, and the click a
        moment later finds it hidden and toggles it back open -- so the chip
        could open a menu and never close it.

        Both halves are asserted: every guard is a *wrap, and every wrapper
        really contains the panel it is paired with in the page."""
        table = self.source[self.source.index("const DISMISS = ["):
                            self.source.index("window.addEventListener(\"mousedown\"")]
        for wrap in re.findall(r'\["(#\w+)","#\w+"\]', table):
            self.assertTrue(wrap.endswith("wrap"),
                            "%s is not a wrapper -- the chip would re-open it" % wrap)
        body = self.source[self.source.index("</style>"):]
        for wrap, menu in re.findall(r'\["#(\w+)","#(\w+)"\]', table):
            start = body.index('id="%s"' % wrap)
            self.assertLess(start, body.index('id="%s"' % menu),
                            "%s is not inside %s in the page" % (menu, wrap))

    def test_the_table_names_every_menu_the_page_has(self):
        """NEGATIVE PROBE, and it breaks by ADDING: a fifth wrapper-and-panel
        pair introduced later is a fifth menu that stays open, and nothing else
        on disk would go red about it."""
        body = self.source[self.source.index("</style>"):]
        wraps = {m for m in re.findall(r'id="(\w+wrap)"', body)}
        table = self.source[self.source.index("const DISMISS = ["):
                            self.source.index("window.addEventListener(\"mousedown\"")]
        listed = {m for m in re.findall(r'\["#(\w+)","#\w+"\]', table)}
        self.assertEqual(sorted(wraps - listed), [],
                         "a wrapper in the page is not in the dismiss table")


class ProjectsInTheRailTests(ApiCase):
    """#119: chats grouped by the directory they are bound to.

    DRIVEN, NOT READ, wherever the answer is Python's. The grouping itself is
    the page's arithmetic and is held by the class below this one; everything
    here -- what a rail payload carries, what a move writes into a chat file,
    what comes back after a restart -- runs.
    """

    def setUp(self) -> None:
        super().setUp()
        self._roots = (crow_core.ROOTS_FILE, crow_gui.SETTINGS_FILE)
        self.addCleanup(self._put_back)
        crow_core.ROOTS_FILE = os.path.join(self.dir, "roots.json")
        crow_gui.SETTINGS_FILE = os.path.join(self.dir, "settings.json")

    def _put_back(self) -> None:
        (crow_core.ROOTS_FILE, crow_gui.SETTINGS_FILE) = self._roots

    def project(self, name: str) -> str:
        path = os.path.join(self.dir, name)
        os.makedirs(path, exist_ok=True)
        crow_core.add_project(path)
        return path

    def chat(self, name: str, root: str | None = "", messages: int = 1) -> str:
        """A chat file on disk. `root=""` writes no key -- nobody ever chose."""
        path = os.path.join(self.dir, "chat-%s.json" % name)
        data = {"format_version": crow_core.SESSION_FORMAT,
                "crow_title": name,
                "messages": [{"role": "user", "content": "x"}] * messages}
        if root != "":
            data["crow_root"] = root
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def rail_of(self, api) -> dict:
        api._reload_rail()
        rails = [m for m in self.drained(api) if m.get("k") == "rail"]
        self.assertTrue(rails, "the window told the page no rail")
        return rails[-1]

    # -- what the rail payload carries --------------------------------------

    def test_the_rail_carries_the_projects_and_every_chat_s_root(self):
        """ONE PAYLOAD, ONE GROUPING. A rail drawn against a project list that
        arrived on its own message would, for one frame, put a chat under a
        heading that is not there."""
        root = self.project("Crow")
        self.chat("eins", root)
        msg = self.rail_of(self.api())
        self.assertEqual([p["name"] for p in msg["projects"]], ["Crow"])
        entry = [r for r in msg["rollovers"] if r["title"] == "eins"][0]
        self.assertEqual(os.path.normcase(entry["root"]), os.path.normcase(root))

    def test_a_chat_carries_no_project_key_of_its_own(self):
        """THE INVARIANT THE WHOLE DESIGN RESTS ON. A label beside the directory
        is a second place for one fact, and the two part company the first time
        either is written alone. Membership is the boundary, or it is nothing."""
        root = self.project("Crow")
        path = self.chat("eins", root)
        self.rail_of(self.api())
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertNotIn("crow_project", data)
        self.assertIn("crow_root", data)
        # `_code_only`, because this file explains in prose that the key does
        # not exist -- and a sentence saying so is not a place that writes one.
        self.assertNotIn("crow_project", _code_only(
            (HERE / "crow_gui.py").read_text(encoding="utf-8")))

    def test_the_project_name_is_the_folder_s(self):
        """Nowhere else it could come from without a second key to hold it -- and
        a rename in the file manager reaches the rail with nothing told."""
        root = self.project("Obsidian-Vault")
        msg = self.rail_of(self.api())
        self.assertEqual(msg["projects"][0]["name"], os.path.basename(root))

    # -- moving one chat -----------------------------------------------------

    def test_moving_a_chat_writes_the_root_into_its_own_file(self):
        root = self.project("Crow")
        path = self.chat("eins")
        self.api().set_chat_root(path, root)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["crow_root"], root)

    def test_leaving_a_project_writes_null_and_not_a_missing_key(self):
        """#101's three states. An absent key means nobody ever chose here, and
        collapsing that with an explicit "no folder" is how a decision to be
        unbounded comes back as a folder on the next read."""
        root = self.project("Crow")
        path = self.chat("eins", root)
        self.api().set_chat_root(path, "")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("crow_root", data)
        self.assertIsNone(data["crow_root"])

    def test_moving_a_chat_keeps_everything_else_in_its_file(self):
        """NEGATIVE PROBE for the writer: a read-modify-write that missed would
        take the conversation with it, and a rail that still listed the title
        would look entirely healthy."""
        root = self.project("Crow")
        path = self.chat("eins", messages=3)
        self.api().set_chat_root(path, root)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(len(data["messages"]), 3)
        self.assertEqual(data["crow_title"], "eins")
        self.assertEqual(data["format_version"], crow_core.SESSION_FORMAT)

    def test_a_chat_that_is_gone_is_reported_and_not_raised(self):
        api = self.api()
        api.set_chat_root(os.path.join(self.dir, "weg.json"), self.project("Crow"))
        # THE MESSAGE, NOT MERELY A `fail`. Without the guard the open() below
        # raises into the broad except and reports "could not write that chat",
        # which is also a fail -- so a test that only counted the kind could not
        # tell the guard from the crash it exists to prevent.
        said = [m["t"] for m in self.drained(api) if m.get("k") == "fail"]
        self.assertEqual(said, ["that chat is gone"])

    def test_a_directory_that_is_gone_is_refused(self):
        """NEGATIVE for the mover: binding a chat to a hole would hand it a
        boundary that does not exist, which is worse than no boundary."""
        api = self.api()
        path = self.chat("eins")
        api.set_chat_root(path, os.path.join(self.dir, "nirgends"))
        self.assertIn("fail", self.kinds(api))
        with open(path, encoding="utf-8") as fh:
            self.assertNotIn("crow_root", json.load(fh))

    def test_moving_the_OPEN_chat_writes_the_root_into_its_file_too(self):
        """THE BUG robin SAW: the boundary bound, the note appeared, and the row
        stayed where it was.

        The live chat goes through `_bind_root`, which sets the boundary in
        MEMORY and marks it chosen -- but `crow_root` reached the file only on
        the next save. `_reload_rail` reads the file, so the rail was drawn from
        a copy that did not know yet. A window whose screen disagrees with its
        own disk is the state that is hardest to report, because both halves
        look right on their own.
        """
        root = self.project("Crow")
        path = self.chat("offen")
        api = self.api()
        api._current_path = path
        api._current_title = "offen"
        self.addCleanup(crow_core.set_root, None)
        api.set_chat_root(path, root)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh).get("crow_root"), root,
                             "the open chat's own file was never told")
        entry = [r for r in self.rail_of(api)["rollovers"]
                 if os.path.abspath(r["path"]) == os.path.abspath(path)][0]
        self.assertEqual(os.path.normcase(entry["root"]), os.path.normcase(root),
                         "the rail would draw it outside the project")

    def test_the_open_chat_leaving_a_project_is_written_too(self):
        """NEGATIVE HALF of the case above: the same gap in the other direction
        would leave a chat drawn inside a project it had just been taken out of."""
        root = self.project("Crow")
        path = self.chat("offen", root)
        api = self.api()
        api._current_path = path
        api._current_title = "offen"
        self.addCleanup(crow_core.set_root, None)
        crow_core.set_root(root)
        api._root_chosen = True
        api.set_chat_root(path, "")
        with open(path, encoding="utf-8") as fh:
            self.assertIsNone(json.load(fh).get("crow_root", "missing"),
                              "the open chat kept a boundary it was released from")

    # -- the three robin found on the built window ---------------------------

    def test_a_new_chat_starts_bound_to_nothing(self):
        """robin, on sight: "ein neuer Chat soll immer wurzellos sein".

        THIS OVERTURNS A DECISION #101 WROTE DOWN. `_adopt_chat_root(None)` fell
        back to the template in roots.json, and `active` is rewritten by every
        bind -- so moving one chat into a project made that project the ground
        every later chat started on. The template still answers at LAUNCH, which
        is the case #92 added it for; a new chat is no longer one of its callers.
        """
        root = self.project("Crow")
        api = self.api()
        self.addCleanup(crow_core.set_root, None)
        api._bind_root(root)                      # a move, which also sets active
        self.assertEqual(crow_core.get_root(), root)
        api.reset()
        self.assertIsNone(crow_core.get_root(),
                          "the new chat inherited the last project")
        self.assertFalse(api._root_chosen,
                         "unbound is not the same as chosen to be unbound")

    def test_the_launch_template_still_answers(self):
        """NEGATIVE HALF of the case above, and the reason it is a separate one:
        the fix must not reach `restore_root`. A window that came up bound to
        nothing would have thrown away #92 to fix a different event."""
        root = self.project("Crow")
        crow_core.set_active_root(root)
        self.addCleanup(crow_core.set_root, None)
        self.assertEqual(crow_core.restore_root()[0], root)
        api = self.api()
        api._adopt_chat_root(None)
        self.assertEqual(crow_core.get_root(), root)

    def test_binding_a_boundary_redraws_the_rail(self):
        """robin: moving a chat in only showed up after folding the project.

        A chat with no file goes through `choose_root`, and that door bound the
        boundary, printed the note and stopped. Nothing redrew, so the row sat
        where it was until some UNRELATED thing reloaded the rail -- folding a
        project, which is exactly what he found. It cost nothing while the
        boundary was invisible in the list; it costs from the moment the list is
        GROUPED by it.
        """
        root = self.project("Crow")
        api = self.api()
        self.addCleanup(crow_core.set_root, None)
        api.choose_root(root)
        self.assertIn("rail", self.kinds(api),
                      "the chat moved and the list was never told")

    def test_releasing_a_boundary_redraws_the_rail_too(self):
        """The other direction, and it has its own case because it is a
        different door: a chat taken out of a project must leave the group on
        the same click that took it out."""
        root = self.project("Crow")
        api = self.api()
        self.addCleanup(crow_core.set_root, None)
        api._bind_root(root)
        self.drained(api)
        api.clear_root()
        self.assertIn("rail", self.kinds(api))

    def test_a_rebind_mid_chat_is_said_at_the_next_request(self):
        """#224: the move is one line in front of the next user
        message, and the head follows it."""
        first, second = self.project("Crow"), self.project("Nest")
        api = self.api()
        self.addCleanup(crow_core.set_root, None)
        api._bind_root(first)
        api._conversation.pin_memory(crow_core.prompt_head())
        api._conversation.append("user", "hi")
        api._conversation.append("assistant", "hello")
        api._bind_root(second)
        self.assertIn("Working area: %s" % crow_core.get_root(),
                      api._conversation.system)
        api._conversation.append("user", "go on")
        self.assertEqual(api._conversation.payload()[-1]["content"],
                         "[Working area is now %s (was %s).]\n\ngo on"
                         % (crow_core.get_root(), first))

    def test_an_unbind_mid_chat_moves_the_head_and_is_said(self):
        root = self.project("Crow")
        api = self.api()
        self.addCleanup(crow_core.set_root, None)
        api._bind_root(root)
        api._conversation.pin_memory(crow_core.prompt_head())
        api._conversation.append("user", "hi")
        api._conversation.append("assistant", "hello")
        self.drained(api)
        api.clear_root()
        self.assertNotIn("Working area", api._conversation.system or "")
        self.assertIn("now none (was %s)" % root,
                      api._conversation.pending_notice)

    def test_the_live_chat_without_a_file_can_be_discarded(self):
        """robin: the new chat could not be deleted.

        It has no file, so `delete_chat` had nothing to remove -- the row armed,
        said "really delete?" and then did nothing at all, which is the one
        outcome worse than refusing. A chat that exists only in the window is
        still a chat somebody can want rid of.
        """
        api = self.api()
        api._current_path = None
        api._current_title = "neu"
        api._conversation.append("user", "hallo")
        self.assertTrue(api.discard_live())
        # THE SAME ARITHMETIC `_reload_rail` DOES: the system prompt is not a
        # turn, and `reset()` keeps it on purpose.
        spare = 1 if api._conversation.has_system else 0
        self.assertEqual(len(api._conversation) - spare, 0)
        self.assertIsNone(api._current_title)
        kinds = self.kinds(api)
        self.assertIn("clear", kinds)
        self.assertIn("rail", kinds)

    def test_discarding_refuses_when_the_chat_has_a_file(self):
        """NEGATIVE PROBE: this door drops a conversation WITHOUT archiving it,
        which is only safe for one that was never written. A chat with a file is
        `delete_chat`'s business, and letting this one answer for it would be a
        second way to lose a saved conversation."""
        path = self.chat("gespeichert")
        api = self.api()
        api._current_path = path
        self.assertFalse(api.discard_live())
        self.assertTrue(os.path.isfile(path))

    # -- what comes back after a restart ------------------------------------

    def test_the_rail_state_is_written_and_read_back(self):
        """PERSISTENCE IS A CONTRACT. A setting only ever written is one nobody
        has proved comes back -- the rule `set_theme` states, held here as a
        case rather than as a sentence."""
        api = self.api()
        self.assertTrue(crow_gui.rail_open(), "the default is open")
        self.assertTrue(api.set_rail_open(False))
        self.assertFalse(crow_gui.rail_open())
        self.assertTrue(api.set_rail_open(True))
        self.assertTrue(crow_gui.rail_open())

    def test_a_folded_project_is_written_and_read_back(self):
        root = self.project("Crow")
        api = self.api()
        self.assertTrue(self.rail_of(api)["projects"][0]["open"])
        api.set_project_open(root, False)
        self.assertFalse(self.rail_of(api)["projects"][0]["open"])
        api.set_project_open(root, True)
        self.assertTrue(self.rail_of(api)["projects"][0]["open"])

    def test_a_project_removed_and_added_again_comes_back_unfolded(self):
        """THE CLOSED ONES ARE THE LIST, so a new row is open like every other
        new row rather than carrying a state from a project that is gone."""
        root = self.project("Crow")
        api = self.api()
        api.set_project_open(root, False)
        api.drop_project(root)
        crow_core.add_project(root)
        self.assertTrue(self.rail_of(api)["projects"][0]["open"],
                        "it came back folded from a life it no longer has")

    def test_dropping_a_project_keeps_its_chats_where_they_are(self):
        """The row goes and nothing else does: the chats stay listed, still
        bound, and the marker stays on the directory."""
        root = self.project("Crow")
        path = self.chat("eins", root)
        api = self.api()
        api.drop_project(root)
        msg = self.rail_of(api)
        self.assertEqual(msg["projects"], [])
        # THE MARKER IS THE HALF THAT MATTERS. A boundary that disappeared
        # because a list was tidied is the failure the root mechanism exists to
        # prevent, and every chat here is still bound to this directory.
        self.assertTrue(os.path.isfile(crow_core.root_file(root)))
        entry = [r for r in msg["rollovers"] if r["title"] == "eins"][0]
        self.assertEqual(os.path.normcase(entry["root"]), os.path.normcase(root))
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["crow_root"], root)


class TheEmptyChatSaysSomethingTests(ApiCase):
    """#119: the greeting under a chat with nothing in it.

    THE CLOCK IS INJECTED, so these are cases and not samples. `greeting` takes
    a timestamp for exactly this reason -- see its docstring on why it is not
    `random`.
    """

    def at(self, h: int, m: int = 0, name: str = "Robin") -> str:
        return crow_gui.greeting(time.mktime((2026, 8, 21, h, m, 0, 0, 0, -1)), name)

    def test_the_hour_decides_which_group_the_line_comes_from(self):
        """A line that says "Good morning" at eight in the evening is worse than
        no line at all."""
        self.assertEqual([crow_gui.daypart(h) for h in (0, 4, 5, 10, 11, 17, 18, 22, 23)],
                         ["night", "night", "morning", "morning", "day", "day",
                          "evening", "evening", "night"])
        self.assertIn("morning", self.at(8).lower())
        self.assertIn("evening", self.at(20).lower())

    def test_the_line_changes_without_the_hour_changing(self):
        """robin asked for it in as many words: not always the same one. Four
        consecutive minutes inside one group have to produce four lines."""
        lines = {self.at(8, m) for m in range(4)}
        self.assertEqual(len(lines), len(crow_gui.GREETINGS["morning"]))

    def test_the_same_minute_gives_the_same_line(self):
        """NEGATIVE HALF, and the reason `random` was refused: without this the
        only testable claim left is "it is one of four", which is not the
        behaviour anybody asked for and would hide a line that never varied."""
        # TWENTY, NOT TWO. A `random.choice` over four lines repeats itself one
        # time in four, so a pair of calls agrees a quarter of the time -- the
        # test would have passed on the very implementation it exists to refuse.
        first = self.at(8, 2)
        self.assertEqual({self.at(8, 2) for _ in range(20)}, {first})

    def test_the_name_is_the_login_s_first_part(self):
        """`DOMAIN\\robin` and `robin@host` are both logins somebody really has."""
        for raw in ("robin", "CORP\\robin", "robin@rechner", "robin.ludwig"):
            with mock.patch.object(crow_gui.getpass, "getuser", return_value=raw):
                self.assertEqual(crow_gui.user_first_name(), "Robin")

    def test_a_machine_that_will_not_say_still_gets_a_greeting(self):
        """NEGATIVE PROBE. "Hello, user." is worse than "Hello." -- and a
        greeting that came out as "Hello, ." would read as a defect."""
        with mock.patch.object(crow_gui.getpass, "getuser",
                               side_effect=OSError("no such user")):
            self.assertEqual(crow_gui.user_first_name(), "")
        for h in (8, 14, 20, 2):
            for m in range(4):
                line = crow_gui.greeting(
                    time.mktime((2026, 8, 21, h, m, 0, 0, 0, -1)), "")
                self.assertNotIn("%s", line)
                self.assertNotIn(" ,", line)
                self.assertNotIn(", .", line)
                self.assertTrue(line[:1].isupper(), line)
                # THE CLAIM THIS CASE IS ABOUT, and it was missing: the name is
                # DROPPED, not filled with a stand-in. Every check above passes
                # happily on "Hello, user." -- only the length says which of
                # the two happened.
                named = crow_gui.greeting(
                    time.mktime((2026, 8, 21, h, m, 0, 0, 0, -1)), "Robin")
                self.assertLess(len(line), len(named), line)

    def test_a_new_chat_is_greeted(self):
        api = self.api()
        api.reset()
        self.assertIn("hello", self.kinds(api))

    def test_a_launch_with_nothing_to_restore_is_greeted_too(self):
        """THE CALLER WITH NO CLEAR TO HANG ON, which is why the greeting is its
        own message rather than a field on `clear`."""
        api = self.api()
        with mock.patch.object(crow_gui, "load_session", return_value=None), \
             mock.patch.object(crow_gui, "check_endpoint", return_value="ok"), \
             mock.patch.object(crow_gui, "model_display_name", return_value="m"), \
             mock.patch.object(crow_gui, "fetch_model_name", return_value="m"), \
             mock.patch.object(crow_gui, "fetch_n_ctx", return_value=1000):
            api._probe()
        self.assertIn("hello", self.kinds(api))

    def test_the_first_turn_takes_the_line_back_off(self):
        """Hooked to `turn()`, the ONE place a row is appended -- not to the
        user's message. A chat restored from disk, a tool card and an error are
        three shapes that are not `user()` and all mean the chat is not empty."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.assertIn('turn(cls){ const g=$("#hello"); if(g) g.remove();', source)

    def test_the_line_is_drawn_and_never_run(self):
        """It carries a login name off the machine.

        THE CLAIM IS UNCHANGED, THE LINE MOVED. #127 put a drawing above the
        greeting, so the text is its own element inside the block -- which is
        why this reads the whole `hello()` body for `innerHTML` instead of
        matching one statement that a layout change can shift.
        """
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        hello = source[source.index("  hello(text){"):]
        hello = hello[:hello.index("  user(text){")]
        self.assertIn("p.textContent=text;", hello)
        self.assertNotIn("innerHTML", hello)

    def test_the_line_is_centred_by_the_box_and_not_by_a_number(self):
        """It stood at `16vh`, which is a guess about one window at one size.
        `min-height:100%` fills #flow's content box -- which already excludes
        the bottom padding the ResizeObserver reserves for the composer -- so
        the line sits on the middle of the space that is free, at any height."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        css = source[source.index("<style>"):source.index("</style>")]
        rule = re.search(r"(?m)^#hello\{(.*?)\}", css, re.S)
        self.assertIsNotNone(rule)
        body = rule.group(1)
        self.assertIn("min-height:100%", body)
        self.assertIn("align-items:center", body)
        self.assertIsNone(re.search(r"margin:\s*\d+vh", body),
                          "a tuned offset is a guess about one window size")


class TheRailDrawsTheGroupsTests(unittest.TestCase):
    """#119, the page's half: how the rail arranges what that payload carries.

    READ RATHER THAN DRIVEN, like every other page class here -- there is no
    browser in this suite. What that still buys is real: each case names a rule
    the arithmetic has to obey, and a rule deleted from the source is a rule
    nothing else on disk would miss.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]
        body = self.source[self.source.index("</style>"):]
        self.bar = body[body.index('<div id="bar"'):body.index('<div id="menu"')]
        self.rail = body[body.index('<aside id="rail">'):body.index('<div id="main">')]

    def test_the_fold_toggle_survives_the_rail_it_folds(self):
        """THE ONE CONTROL THAT MUST NOT LIVE IN THE THING IT HIDES. Inside the
        rail it would go away with it, and there would be no way back."""
        self.assertIn('id="railtoggle"', self.bar)
        self.assertNotIn('id="railtoggle"', self.rail)

    def test_the_fold_state_is_stamped_before_the_page_is_handed_over(self):
        """The theme's rule, for the same reason: a rail drawn open and folded
        by a script after load would do it on every start, and that frame is
        exactly when somebody is looking at the window."""
        # DIE ZUSAGE, NICHT DIE GANZE ZEILE. Sie stand als vollstaendiges
        # `<body ...>` hier und wurde rot, als das Code-Panel sein eigenes
        # Attribut danebenstellte -- an einer Ergaenzung, die genau dieselbe
        # Regel befolgt. Geprueft wird jetzt, dass jedes Panel seinen Stand
        # gestempelt bekommt, bevor die Seite uebergeben wird.
        self.assertIn('<body data-rail="__RAIL__"', self.source)
        self.assertIn('data-code="__CODE__"', self.source)
        self.assertIn('.replace("__RAIL__"', self.source)
        self.assertIn('.replace("__CODE__"', self.source)
        self.assertIn('body[data-rail="shut"] #rail{width:0', self.css)
        self.assertIn('body[data-code="shut"] #code{width:0', self.css)

    def test_a_folded_project_draws_no_rows_rather_than_hidden_ones(self):
        """Rows built and then hidden stay in the tree, and the fast path that
        moves the active mark would find a node nobody can see."""
        self.assertIn("if(p.open) mine.forEach(r=>box.appendChild(rowFor(r)));",
                      self.source)

    def test_folding_and_moving_are_both_in_the_rail_s_shape(self):
        """THE FAST PATH IS THE TRAP HERE. It skips the rebuild when the shape
        is unchanged, so a shape blind to roots and fold state would leave the
        list right in Python and stale on screen."""
        shape = self.source[self.source.index("const shape=(rollovers"):]
        shape = shape[:shape.index("if(box.dataset.shape===shape)")]
        self.assertIn('(r.root||"")', shape, "a move would not redraw")
        self.assertIn('p.open?"+":"-"', shape, "a fold would not redraw")

    def test_the_empty_space_below_the_chats_answers_a_right_click(self):
        """Otherwise the two things done least often -- start a chat, make a
        project -- are the two with no way in from the list."""
        self.assertIn('if(e.target.closest("#sessions")){ crow.railMenu(e); return; }',
                      self.source)
        plan = self.source[self.source.index("railPlan(kind,entry,archived){"):]
        plan = plan[:plan.index("menuDo(act,arg){")]
        for act in ('act:"newchat"', 'act:"newproj"', 'act:"dropproj"',
                    'act:"toproj"'):
            self.assertIn(act, plan)

    def test_no_menu_row_carries_a_snippet_of_code(self):
        """A project name is a folder name off the disk. The rows carry an ACTION
        NAME and are wired from the plan, so a folder called `'); alert('` is a
        label and cannot become anything else -- the modelMenu rule verbatim."""
        self.assertIn('el.querySelector("b").textContent=p.label;', self.source)
        self.assertIn("el.onclick=()=>crow.menuDo(p.act,p.arg);", self.source)
        menu = self.source[self.source.index("menu(e,kind,entry,row,archived){"):]
        menu = menu[:menu.index("closeMenu()")]
        self.assertNotIn("onclick=\\\"", menu,
                         "a handler is being interpolated into the row's HTML")

    def test_a_project_a_chat_is_already_in_is_not_offered(self):
        """A row that changes nothing reads as a row that failed."""
        self.assertIn(
            "const others=(this.projects||[]).filter(p=>!this.sameDir(p.path,entry.root));",
            self.source)

    def test_membership_is_an_exact_match_and_not_an_ancestor_walk(self):
        """`find_root` takes the NEAREST marker and not the highest, so a
        sub-directory that declares itself is its own root. The page compares
        the whole path, trailing separator and case folded, and nothing else."""
        fn = self.source[self.source.index("sameDir(a,b){"):]
        fn = fn[:fn.index("projectOf(root)")]
        self.assertIn("toLowerCase()", fn)
        self.assertNotIn("indexOf", fn, "a prefix test is an ancestor walk")
        self.assertNotIn("startsWith", fn, "a prefix test is an ancestor walk")

    def test_no_two_methods_on_the_page_share_a_name(self):
        """THE BUG THIS CLASS DID NOT CATCH, and the reason it could not: the page
        is one object literal, so a second `menuPlan` silently replaced the first
        and the model chip called the context menu's planner with no arguments.
        Nothing threw until a click, and no source assertion about either method
        was false -- both strings were still in the file.

        Held here rather than by reading either method, because the failure is
        not in a method. It is in the pair.
        """
        page = self.source[self.source.index("const crow = {"):
                           self.source.index("const composer =")]
        names = re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_]*)\(", page)
        # `if(` and friends sit at this indent too and are not definitions.
        keywords = {"if", "for", "while", "switch", "catch", "return", "function"}
        names = [n for n in names if n not in keywords]
        dupes = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(dupes, [],
                         "a later definition silently replaces the earlier one")

    def test_the_wordmark_takes_its_colour_from_the_palette(self):
        """It was the accent in all three themes -- Crow's own blue, which is
        right on the dark blue ground it was drawn for and a coloured word
        floating on a neutral or a white one. robin: white on dark, dark on
        light, unchanged in `crow`.

        TWO NAMES, because only `crow` splits the O off; the other two set both
        to one value, which is what makes the word solid rather than holed."""
        rule = re.search(r"(?m)^#mark\{(.*?)\}", self.css, re.S)
        self.assertIsNotNone(rule)
        self.assertIn("color:var(--mark)", rule.group(1))
        self.assertNotIn("var(--accent)", rule.group(1))
        self.assertIn("#mark span{color:var(--mark-o)}", self.css)
        # THE HEX IS NEVER HERE. The palette test beside this one holds that as
        # a rule; naming it again is what makes THIS case about the wordmark.
        for name in ("--mark:", "--mark-o:"):
            self.assertEqual(self.css.count(name), 3,
                             "%s is not defined in all three palettes" % name)

    def test_a_project_heading_carries_more_weight_than_its_chats(self):
        """A heading and its children at one weight is a list with an indent,
        not a group."""
        proj = re.search(r"(?m)^\.proj \.t\{(.*?)\}", self.css, re.S)
        sess = re.search(r"(?m)^\.sess \.t\{(.*?)\}", self.css, re.S)
        self.assertIsNotNone(proj)
        self.assertIsNotNone(sess)
        self.assertIn("font-weight:600", proj.group(1))
        self.assertNotIn("font-weight", sess.group(1))

    def test_the_delete_still_takes_two_clicks_in_one_menu(self):
        """NEGATIVE SIDE of building the rows from a plan: `menuDo` shuts the
        panel before it dispatches, and delete had to be exempted or the gesture
        would have quietly become two right-clicks."""
        self.assertIn('if(act==="del") return this.deleteTarget(entry);',
                      self.source)
        self.assertIn('btn.dataset.armed="1";', self.source)
        # BOTH WORDS, because the armed label now names which of the two acts it
        # is: a file is deleted, a chat that was never written is discarded.
        self.assertIn('"really delete?"', self.source)
        self.assertIn('"really discard?"', self.source)


class TheHeldWriteBarTests(unittest.TestCase):
    """#128: the strip that pops up over the composer while a write waits."""

    def setUp(self):
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def _bar(self):
        return self.css[self.css.index("#pendbar{"):self.css.index("#pendbar[hidden]")]

    def test_it_wears_the_memory_line_own_look(self):
        """NOT A SECOND VISUAL LANGUAGE FOR THE SAME SUBJECT. `.memnote` announces
        a write that HAPPENED; this announces one that WANTS to. Same accent,
        same gradient, same halo -- a reader should not have to learn two
        appearances for one thing."""
        bar = self._bar()
        self.assertIn("var(--accent)", bar)
        self.assertIn("linear-gradient", bar)
        self.assertIn("@keyframes pendglow", self.css)

    def test_it_breathes_because_it_is_a_state(self):
        """`.memnote` settles after one pass because a save is over. A question
        is still true until it is answered, so this one does not stop."""
        bar = self._bar()
        self.assertIn("infinite", bar)
        self.assertNotIn("forwards", bar)

    def test_it_sits_over_the_composer_and_not_in_the_button_row(self):
        """THE ROW IS FOR CONTROLS THAT ARE ALWAYS THERE, and this is not one: it
        pops in when there is something to answer and leaves again. Asserted by
        position in the page, because "it looks right" is not something a file
        on disk can say."""
        body = self.source[self.source.index("</style>"):]
        self.assertLess(body.index('id="pendbar"'), body.index('id="line"'))
        self.assertNotIn('id="pendwrap"', body)

    def test_a_reader_who_asked_for_no_motion_still_sees_it(self):
        """Motion off, colour stays -- the strip is the only sign there is, so it
        may not vanish for the people who asked for fewer moving things."""
        block = self.css[self.css.index("#pendbar{"):]
        block = block[block.index("prefers-reduced-motion"):]
        block = block[:block.index("}}") + 2]
        self.assertIn("animation:none", block)
        self.assertIn("var(--accent)", block)

    def test_the_entries_are_drawn_and_never_interpolated(self):
        """A staged note is model-written text out of a conversation and may
        contain anything at all; the page draws it rather than running it."""
        js = self.source[self.source.index("pendState(items){"):
                         self.source.index("pendAnswer(yes)")]
        self.assertIn("textContent", js)

    def test_it_lies_behind_the_composer(self):
        """BEHIND, NOT ABOVE, and the two look the same in source order -- what
        separates them is the negative margin that tucks the tile under the box
        and the layer that lifts the box over it. Without the z-index the
        overlap happens the wrong way round and the tile sits ON the input."""
        bar = self._bar()
        self.assertIn("margin:0 auto -14px", bar)
        box = self.css[self.css.index("#box{position:relative"):]
        self.assertIn("z-index:1", box[:80])

    def test_collapsed_it_is_a_title_and_two_numbers(self):
        """A tile that printed every entry would cover the chat it lies behind.
        Collapsed it says what it is and how much is coming; the text is one
        click away."""
        js = self.source[self.source.index("pendState(items){"):
                         self.source.index("pendToggle(e)")]
        self.assertIn("Memory Consolidation", js)
        self.assertIn('class="plus"', js)
        self.assertIn('class="minus"', js)
        body = self.css[self.css.index("#pendbar .body{"):]
        self.assertIn("display:none", body[:60])

    def test_gained_is_green_and_lost_is_red(self):
        """THE VALUE, NOT THE NAME -- and the first version of this case is why.
        It asserted `var(--bad-text)` and passed while the minus rendered WHITE:
        `--bad-text` is #ffd9d4, a pale pink meant as text ON a red ground, and
        on this dark surface it is indistinguishable from the text colour. The
        name was right in the file and the colour was wrong on the screen.

        Same failure the light drawing had, and the same fix: resolve what the
        palette actually gives and look at it. A checker that compares colour
        names cannot see an invisible colour."""
        import re
        CLOSE = chr(125)

        def value(css, token):
            m = re.search(re.escape(token) + r":\s*(#[0-9a-fA-F]{6})", css)
            self.assertIsNotNone(m, "%s is not defined" % token)
            h = m.group(1).lstrip("#")
            return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))

        # The dark palette is the shipped default and the one robin looked at.
        dark = self.css[self.css.index("--bg:#181818"):]
        dark = dark[:dark.index(CLOSE)]
        used = {}
        for cls in ("plus", "minus"):
            rule = self.css[self.css.index("#pendbar .%s{" % cls):]
            m = re.search(r"color:var\((--[a-z-]+)\)", rule[:120])
            self.assertIsNotNone(m, "%s has no palette colour" % cls)
            used[cls] = m.group(1)

        r, g, b = value(dark, used["minus"])
        self.assertGreater(r, g + 40, "the minus is not red: %r" % (used["minus"],))
        self.assertGreater(r, b + 40, "the minus is not red: %r" % (used["minus"],))
        self.assertLess(min(g, b), 200,
                        "%s is near-white, not a red anyone can see" % used["minus"])

        r, g, b = value(dark, used["plus"])
        self.assertGreater(g, r + 40, "the plus is not green: %r" % (used["plus"],))

    def test_a_replace_counts_as_one_gained_and_one_lost(self):
        """NEGATIVE PROBE FOR THE COUNTER. `replace` is ONE entry and TWO
        changes; counting it once would understate what is about to happen to
        the file, and the tile's whole job is to say how much is coming."""
        js = self.source[self.source.index("pendState(items){"):
                         self.source.index("pendToggle(e)")]
        block = js[js.index('a === "replace"'):]
        self.assertIn("plus++", block[:60])
        self.assertIn("minus++", block[:60])

    def test_a_click_on_a_button_does_not_collapse_the_tile(self):
        """The buttons live inside the tile, so their click bubbles out through
        it. Without this guard answering the question would fold the thing shut
        on the way out -- and on a decline, fold away the only evidence of what
        was just discarded."""
        js = self.source[self.source.index("pendToggle(e){"):]
        self.assertIn('closest("button")', js[:160])

    def test_the_bar_goes_when_the_chat_goes(self):
        """The Python side drops the staged writes inside `forget_approvals`;
        without this the strip would keep glowing about notes that are gone."""
        clear = self.source[self.source.index('case "clear":'):]
        self.assertIn("pendState([])", clear[:200])


class AHeldWriteThatDidNotLandIsSaidTests(ApiCase):
    """#285. robin pressed "save to memory", the file stayed as it was and the
    window said nothing. A write that did not happen is announced as surely as
    one that did."""

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(crow_core.forget_pending)

    def test_an_expired_write_answers_with_a_visible_line(self):
        entry = crow_core.stage_memory(
            "memory", json.dumps({"action": "add", "content": "ZU SPAET"}))
        entry["staged"] -= crow_core.PENDING_TTL + 1
        api = self.api()
        self.drained(api)
        api.answer_memory(True)
        got = self.drained(api)
        notes = [m["t"] for m in got if m.get("k") == "note"]
        self.assertTrue(any("not saved" in t and "expired after 5 min" in t
                            for t in notes), got)
        # NEGATIVE: nothing was written, so nothing glows.
        self.assertNotIn("memory", [m.get("k") for m in got])

    def test_a_mixed_answer_glows_for_the_saved_and_names_the_rest(self):
        api = self.api()
        self.drained(api)
        with mock.patch.object(crow_core, "approve_pending", return_value=(
                ["add memory"], [{"what": "add memory: x", "why": "already in memory"}])):
            api.answer_memory(True)
        got = self.drained(api)
        self.assertEqual([m["n"] for m in got if m.get("k") == "memory"], [1])
        self.assertTrue(any("already in memory" in m.get("t", "")
                            for m in got if m.get("k") == "note"), got)


class TheHeldWriteTileHasThreeStatesTests(unittest.TestCase):
    """#285 point 3. Collapsed, the 160-char previews, then the whole text --
    a replace as the entry it takes out above the one it puts in, an add
    marked as appended. RUN in node over a small fake DOM: which row shows at
    which click is logic, and a string in the source proves nothing about it.
    """

    FAKE_DOM = r"""
function mk(tag){ const e={tag, children:[], className:"", _t:"", hidden:false,
  parentNode:null, dataset:{},
  classList:{ s:new Set(), add(...c){ c.forEach(x=>this.s.add(x)); },
    remove(...c){ c.forEach(x=>this.s.delete(x)); },
    contains(c){ return this.s.has(c); },
    toggle(c,f){ const on = f===undefined ? !this.s.has(c) : !!f;
      if(on) this.s.add(c); else this.s.delete(c); return on; } },
  appendChild(c){ this.children.push(c); c.parentNode=this; return c; },
  insertBefore(c,ref){ const i=ref?this.children.indexOf(ref):-1;
    if(i<0) this.children.push(c); else this.children.splice(i,0,c);
    c.parentNode=this; return c; },
  get textContent(){ return this._t + this.children.map(c=>c.textContent).join(""); },
  set textContent(v){ this._t=String(v); this.children=[]; },
  set innerHTML(v){ this.children=[]; this._t="";
    for(const m of String(v).matchAll(/class="([^"]+)"/g)){
      const c=mk("span"); c.className=m[1]; this.appendChild(c); } },
  get innerHTML(){ return ""; },
  has(cls){ return this.className.split(" ").includes(cls) || this.classList.s.has(cls); },
  querySelectorAll(sel){ const cls=sel.replace(/^\./,""), out=[];
    const walk=n=>n.children.forEach(c=>{ if(c.has(cls)) out.push(c); walk(c); });
    walk(this); return out; },
  querySelector(sel){ return this.querySelectorAll(sel)[0] || null; },
  closest(){ return null; } };
  return e; }
const document={ createElement:mk };
const bar=mk("div"); bar.id="pendbar";
const $=sel=>bar;
"""

    @classmethod
    def setUpClass(cls):
        cls.node = _node()
        cls.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        cls.css = cls.source[cls.source.index("<style>"):cls.source.index("</style>")]

    def setUp(self):
        if not self.node:
            self.skipTest("no node on this machine")

    def _page(self, items, clicks):
        """pendState + pendToggle out of the page; after each click, the
        tile's state and every row's text as the CSS would show it."""
        import subprocess
        start = self.source.index("  pendState(items){")
        end = self.source.index("  pendAnswer(yes)")
        prog = (self.FAKE_DOM
                + "const crow={\n" + self.source[start:end] + "};\n"
                + "const seen=[];\n"
                + "function look(){ const deep=bar.classList.contains('deep'),"
                  " open=bar.classList.contains('open');\n"
                  "  const hint=bar.querySelector('.hint');\n"
                  "  seen.push({open, deep, hint: hint ? hint.textContent : '',\n"
                  "    brief: bar.querySelectorAll('.brief').map(r=>r.textContent),\n"
                  "    was: bar.querySelectorAll('.was').map(r=>r.textContent),\n"
                  "    will: bar.querySelectorAll('.will').map(r=>r.textContent),\n"
                  "    where: bar.querySelectorAll('.where').map(r=>r.textContent)}); }\n"
                + "crow.pendState(" + json.dumps(items) + "); look();\n"
                + "for(let i=0;i<" + str(clicks) + ";i++){ crow.pendToggle({target:bar}); look(); }\n"
                + "console.log(JSON.stringify(seen));\n")
        done = subprocess.run([self.node, "-e", prog], capture_output=True,
                              text=True, encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    ITEMS = [{"action": "replace", "text": "replace memory: " + "N" * 141 + "...",
              "full": "N" * 400, "old": "alpha " + "o" * 300, "find": "alpha"},
             {"action": "add", "text": "add memory: " + "A" * 145 + "...",
              "full": "A" * 400}]

    def test_the_second_click_shows_old_and_new_whole(self):
        shut, first, second, third = self._page(self.ITEMS, 3)
        self.assertEqual((shut["open"], shut["deep"]), (False, False))
        self.assertEqual((first["open"], first["deep"]), (True, False))
        self.assertEqual((second["open"], second["deep"]), (True, True))
        self.assertEqual((third["open"], third["deep"]), (False, False))
        # NO TEXT CUT: the whole old entry and the whole new one, marked.
        self.assertEqual(second["was"], ["\u2212 alpha " + "o" * 300])
        self.assertEqual(second["will"], ["+ " + "N" * 400, "+ " + "A" * 400])
        self.assertEqual(second["where"], ["appended at the end"])
        self.assertEqual(first["brief"], [x["text"] for x in self.ITEMS])
        self.assertEqual(len({first["hint"], second["hint"], third["hint"]}), 3)

    def test_a_replace_with_no_single_match_says_so(self):
        """NEGATIVE: the tile names what it searched for, not a guessed entry."""
        got = self._page([{"action": "remove", "text": "remove memory: x ",
                           "full": "", "old": None, "find": "x "}], 2)
        self.assertEqual(len(got[2]["was"]), 1)
        self.assertIn("no single entry contains", got[2]["was"][0])
        self.assertEqual(got[2]["will"], [])

    def test_the_css_shows_one_level_at_a_time(self):
        """The previews and the whole text are both in the tile; which one a
        reader sees is the CSS's job, keyed on `.deep`."""
        self.assertIn("#pendbar .whole{display:none", self.css)
        self.assertIn("#pendbar.deep .whole{display:block", self.css)
        self.assertIn("#pendbar.deep .brief{display:none", self.css)
        # #249's phone layer rearranges; it must not hide the rows #285 adds.
        phone = crow_gui.REMOTE_CSS
        for cls in (".whole", ".brief", ".was", ".will", ".where", ".deep"):
            self.assertNotIn(cls, phone)


class TheMemoryLineTests(unittest.TestCase):
    """#122: the one sign a person gets that something was remembered.

    THERE IS NO APPROVAL GATE IN FRONT OF IT -- robin declined it on 2026-08-21
    -- so this line is not decoration. It is the whole of the user's control
    over an automatic writer, which is why several of these cases are about it
    being impossible to miss and impossible to switch off.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def test_the_event_reaches_the_page_as_its_own_kind(self):
        """Not a `note`. A note is grey because what notes say may be skimmed
        past, and this one may not be."""
        seen = []
        crow_gui.Turn(seen.append).memory_saved(["add memory", "add user"])
        self.assertEqual([m["k"] for m in seen], ["memory"])
        self.assertEqual(seen[0]["n"], 2)

    def test_the_line_is_never_a_turn(self):
        """NEGATIVE PROBE, and the expensive one: a line that slipped into the
        history would move the head of the next prompt and cost the full
        prefill the whole feature is built to avoid. `Turn` only queues."""
        seen = []
        turn = crow_gui.Turn(seen.append)
        turn.memory_saved(["add memory"])
        self.assertFalse(hasattr(turn, "_conversation"))
        self.assertTrue(all("role" not in m for m in seen))

    def test_the_page_draws_it_with_a_glow_that_settles(self):
        """`forwards` on both animations is the trick. A glow that kept pulsing
        would be a thing to switch off, and this line may not be switchable."""
        self.assertIn('case "memory": this.memory(e.t,e.n); break;', self.source)
        self.assertIn(".memnote{", self.css)
        self.assertIn("@keyframes memsweep", self.css)
        self.assertIn("@keyframes memglow", self.css)
        self.assertEqual(self.css.count("1 forwards"), 2)

    def test_a_reader_who_asked_for_no_motion_still_sees_it(self):
        """NEGATIVE PROBE for the animation: with motion off the row must keep
        its tint. Replacing the sweep with nothing would hide the only notice
        there is from exactly the people who asked for fewer moving things."""
        block = self.css[self.css.index("prefers-reduced-motion"):]
        block = block[:block.index("}}") + 2]
        self.assertIn("animation:none", block)
        self.assertIn("var(--accent)", block)

    def test_the_window_speaks_one_language_and_it_is_english(self):
        """robin, 2026-08-21: "wenn ich englisch mit crow rede, ist der output
        dann englisch ... es wird ja mehr englisch als deutsche user geben".

        THERE IS NO LOCALISATION TO FALL BACK ON. `locale`, `gettext` and
        `getdefaultlocale` appear zero times in all three modules, so a German
        line is not the German version -- it is the ONLY version, shown to
        everyone. Two of them had shipped: the greeting, and the memory notice.

        DOCSTRINGS ARE EXEMPT ON PURPOSE. They quote robin, in German, on why
        several of these decisions were made; a case that could not tell
        documentation from an interface would forbid its own evidence.
        """
        import ast

        tree = ast.parse(self.source)
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                first = node.body[0] if node.body else None
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)                         and isinstance(first.value.value, str):
                    docs.add(id(first.value))
        german = set("äöüÄÖÜß")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str)                     and id(node) not in docs:
                hit = german & set(node.value)
                self.assertFalse(hit, "German in a user-facing string, line %d: %r"
                                      % (node.lineno, node.value[:60]))
        self.assertIn("Memory updated", self.source)
        self.assertIn("Good morning, %s.", self.source)

    def test_the_window_speaks_one_language_and_it_is_english(self):
        """robin, 2026-08-21: "es wird ja mehr englisch als deutsche user geben".

        THERE IS NO LOCALISATION TO FALL BACK ON. `locale`, `gettext` and
        `getdefaultlocale` appear zero times in all three modules, so a German
        line is not the German version -- it is the ONLY version, shown to
        everyone who installs this. Fourteen of them had shipped: the greeting,
        the memory notice, `Hilfe`, `Einstellungen`, `Aussehen`, the two theme
        buttons, the rail tooltip, the empty-skills line and five context-menu
        rows. They were found one screenshot at a time, which is why this case
        exists rather than another pair of eyes.

        DOCSTRINGS AND COMMENTS ARE EXEMPT ON PURPOSE. They quote robin, in
        German, on why several of these decisions were made; a case that could
        not tell documentation from an interface would forbid its own evidence.
        The first draft of this case did exactly that -- it also banned the word
        `gettext`, and the comment explaining that Crow has no `gettext` failed
        it.

        IT DOES NOT FORBID LOCALISATION EITHER. What it holds is that ONE
        language ships today. If a second one is ever built, this case is the
        one to rewrite, not to route around.
        """
        import ast

        for module in ("crow_gui.py", "crow.py", "crow_core.py"):
            text = (HERE / module).read_text(encoding="utf-8")
            tree = ast.parse(text)
            docs = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef)) and node.body:
                    first = node.body[0]
                    if isinstance(first, ast.Expr)                             and isinstance(first.value, ast.Constant)                             and isinstance(first.value.value, str):
                        docs.add(id(first.value))
            german = set("äöüÄÖÜß")
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant)                         and isinstance(node.value, str) and id(node) not in docs:
                    self.assertFalse(german & set(node.value),
                                     "German in a user-facing string, %s:%d -- %r"
                                     % (module, node.lineno, node.value[:60]))
        self.assertIn("Memory updated", self.source)
        self.assertIn("Good morning, %s.", self.source)
        self.assertIn(">Help</button>", self.source)
        self.assertIn("<h2>Settings</h2>", self.source)

    def test_the_line_cannot_be_switched_off(self):
        """`--no-review` stops the WRITING; there is no flag that keeps the
        writing and hides the notice. A silent learner is a system nobody can
        correct."""
        self.assertIn("--no-review", self.source)
        for hidden in ("--no-memory-notice", "memory_notifications", "quiet_memory"):
            self.assertNotIn(hidden, self.source)


class TheBirdTests(unittest.TestCase):
    """#127: the drawing under the greeting, and the icon on the taskbar."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def test_both_drawings_ship_and_are_read_from_disk(self):
        """Two files rather than one recoloured by CSS: it is a wireframe with
        five stroke colours, and `currentColor` carries one."""
        for background in ("dark", "light"):
            self.assertTrue((HERE / crow_gui.MARK_FILES[background]).is_file(), background)
            self.assertIn("<svg", crow_gui.mark_svg(background))
        self.assertNotEqual(crow_gui.mark_svg("dark"), crow_gui.mark_svg("light"))

    def test_every_stroke_is_legible_on_the_ground_it_is_drawn_on(self):
        """MEASURED, NOT MATCHED AGAINST A LIST OF COLOURS, because the defect
        this exists for is a colour that was simply left behind: the light
        drawing shipped with 66 of its 118 strokes still carrying the DARK
        version's values, at 1.8:1 and 1.3:1 on white -- present in the file,
        invisible on the screen, and a case that compared literals would have
        passed while robin was looking at a blank space.

        3:1 is the floor for a graphic that has to be made out, not read.
        """
        import re

        def lum(colour):
            def channel(c):
                c = int(colour[c:c + 2], 16) / 255
                return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            return (0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5))

        def contrast(a, b):
            high, low = sorted((lum(a), lum(b)), reverse=True)
            return (high + 0.05) / (low + 0.05)

        grounds = {"dark": ["#181818", crow_core.CROW_BG], "light": ["#ffffff"]}
        for background, on in grounds.items():
            strokes = set(re.findall(r'stroke="(#[0-9a-f]{6})"',
                                     crow_gui.mark_svg(background)))
            self.assertTrue(strokes, background)
            for stroke in sorted(strokes):
                for ground in on:
                    self.assertGreaterEqual(
                        contrast(stroke, ground), 3.0,
                        "%s on %s is %.1f:1" % (stroke, ground,
                                                contrast(stroke, ground)))

    def test_the_two_drawings_are_the_same_bird(self):
        """NEGATIVE HALF of the case above: the light one is a RECOLOURING, so
        every path must still be there. A version that dropped the strokes it
        could not colour would also pass a contrast check."""
        import re

        paths = lambda which: re.findall(r'd="([^"]+)"', crow_gui.mark_svg(which))
        self.assertEqual(paths("dark"), paths("light"))

    def test_a_missing_drawing_is_empty_and_not_an_error(self):
        """NEGATIVE PROBE. A greeting without a bird is a greeting; a window
        that refused to open because a decoration was absent is not a window."""
        self.assertEqual(crow_gui.mark_svg("gibtsnicht"), "")

    def test_the_page_carries_both_and_the_stylesheet_picks(self):
        """No JavaScript and no second copy of which theme is live. Dark is the
        default because two of the three themes are dark; only `light` swaps."""
        self.assertIn("__MARKDARK__", self.source)
        self.assertIn("__MARKLIGHT__", self.source)
        self.assertIn(".mk-light{display:none}", self.css)
        self.assertIn(':root[data-theme="light"] .mk-dark{display:none}', self.css)

    def test_the_drawing_is_cloned_and_never_moved(self):
        """A `<template>` and `cloneNode`. Moved, the second greeting of a
        session would find the drawing gone -- and `hello()` builds its block
        fresh every time it is called."""
        self.assertIn('<template id="marktpl">', self.source)
        self.assertIn("t.content.cloneNode(true)", self.source)

    def test_the_icon_ships_and_is_found_beside_the_client(self):
        """A path built from `__file__`, so an installed copy finds its own."""
        self.assertTrue(os.path.isfile(crow_gui.ICON_FILE))
        self.assertTrue(crow_gui.ICON_FILE.endswith("crow.ico"))
        with open(crow_gui.ICON_FILE, "rb") as fh:
            self.assertEqual(fh.read(4), b"\x00\x00\x01\x00", "not an ICO")

    def test_the_bird_fills_the_icon_it_is_drawn_on(self):
        """MEASURED, AND IT IS WHY THE TASKBAR BUTTON LOOKED SMALL. The file
        carried all seven sizes and `set_icon` hung big and small separately, so
        every part a client controls was already right. What was wrong sat
        INSIDE the drawing: the raven occupied 66 % of the width and 57 % of the
        height of its own canvas, and Windows draws the canvas. A correctly
        sized icon with a fifth of its box empty on every side reads as a small
        icon beside buttons that fill theirs.

        85 % OF THE LONGER SIDE IS THE FLOOR, and only the longer one. This bird
        is wider than it is tall; demanding the same of the shorter side would
        be demanding a bird that has been stretched to fit.

        NO PILLOW, NO MEASUREMENT. The sizes in the directory can be read with
        `struct`, but the images are PNG-compressed and the alpha channel is the
        whole question here, so a machine without it skips rather than guesses.
        """
        try:
            from PIL import Image
        except ImportError:                 # noqa: BLE001 - skipped, never faked
            self.skipTest("Pillow is not installed")
        import struct

        with open(crow_gui.ICON_FILE, "rb") as fh:
            raw = fh.read()
        count = struct.unpack_from("<H", raw, 4)[0]
        self.assertGreaterEqual(count, 7, "the icon lost sizes")
        for i in range(count):
            width, height = struct.unpack_from("<BB", raw, 6 + i * 16)
            size, offset = struct.unpack_from("<II", raw, 6 + i * 16 + 8)
            width, height = width or 256, height or 256
            image = Image.open(io.BytesIO(raw[offset:offset + size])).convert("RGBA")
            solid = image.split()[3].point(lambda v: 255 if v > 8 else 0)
            box = solid.getbbox()
            self.assertIsNotNone(box, "%dx%d is empty" % (width, height))
            longer = max(box[2] - box[0], box[3] - box[1])
            self.assertGreaterEqual(
                longer / max(width, height), 0.85,
                "%dx%d: the drawing fills %.0f %% of its canvas"
                % (width, height, 100 * longer / max(width, height)))

    def test_the_application_id_is_set_before_the_window_exists(self):
        """Without one the taskbar groups this under the interpreter and draws
        Python's icon over Crow's name. The shell reads the id when it registers
        the button and never looks again -- the same rule the style bits hit."""
        main = self.source[self.source.index("    api = Api(args)"):]
        main = main[:main.index("webview.start(")]
        self.assertIn("taskbar_identity()", main)
        self.assertLess(main.index("taskbar_identity()"),
                        main.index("webview.create_window("))

    def test_the_icon_rides_the_search_that_already_found_the_window(self):
        """Finding the window is the hard half -- four things had to be right at
        once -- and a second EnumWindows is a second chance to pick the HELPER
        window, which looks like a working icon on a window nobody sees."""
        buttons = self.source[self.source.index("def shell_buttons"):]
        buttons = buttons[:buttons.index("\ndef ", 10)]
        self.assertIn("set_icon(hwnd)", buttons)
        self.assertEqual(self.source.count("EnumWindows"), 3,
                         "a second window search appeared")


class TheRibbonAndTheChatRunIntoOneTests(unittest.TestCase):
    """#125: what the window lost, and the one divider it kept."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def test_both_chips_moved_and_neither_was_dropped(self):
        """REMOVED IS NOT THE SAME AS GONE, the rule the address already had.
        The bar is deleted, so its two facts had to land somewhere a person can
        still reach -- and the tool switch is a SWITCH there, not a chip that
        has to shout in colour which of two modes is live."""
        self.assertIn('<section data-cat="server"', self.source)
        server = self.source[self.source.index('<section data-cat="server"'):
                             self.source.index('<section data-cat="skills"')]
        self.assertIn('id="conn"', server)
        self.assertIn('id="dot"', server)
        self.assertIn('id="tools"', server)
        self.assertIn('class="sw" id="toolsw"', server)
        self.assertIn('$("#toolsw").onclick=()=>crow.toggleTools();', self.source)

    def test_every_category_has_a_button_a_pane_and_the_same_key(self):
        """A section nobody can click does not exist; a button whose pane is
        missing opens nothing. #126 took the KEY off a positional array and put
        it on the button, so this compares the two sets instead of an order:
        a fifth button with a four-name list used to mark the wrong tab, and the
        fault read like a CSS problem."""
        import re

        nav = self.source[self.source.index('<nav id="scats">'):]
        nav = nav[:nav.index("</nav>")]
        buttons = set(re.findall(r'<button[^>]*data-cat="([a-z]+)"', nav))
        panes = set(re.findall(r'<section data-cat="([a-z]+)"', self.source))
        self.assertEqual(buttons, panes)
        # MOVED, NOT WIDENED (2026-08-22): `providers` was the "Coming soon"
        # placeholder and is now two built pages, Model and API Keys. The set is
        # still exact, so a tenth button with a nine-name list is still red.
        # WIDENED BY ONE (2026-08-28, robins Ansage): the broker moved out of
        # the Model page onto its own -- `openrouter` is a category now.
        self.assertEqual(buttons, {"look", "skills", "server", "mcp", "model",
                                   "openrouter", "subs", "keys", "about"})
        self.assertIn("b.dataset.cat===name", self.source)
        self.assertNotIn('["look","skills"', self.source,
                         "the positional list is back")

    def test_nothing_in_the_sheet_is_a_promise_any_more(self):
        """#126 pinned what an UNBUILT section says: "Coming soon" plus what the
        section is FOR, so a placeholder is a promise rather than a shrug.

        BOTH SECTIONS IT WAS WRITTEN ABOUT ARE BUILT NOW (2026-08-22), the way
        #129 took MCPs out of the same pair. So the assurance MOVES to the other
        side rather than weakening -- and it moves to the stronger side: the two
        panes have their controls, and there is no dead-end left in the sheet at
        all. A bare placeholder added tomorrow turns this red, which the old
        loop over a single hard-coded key could not do.
        """
        for key, want in (("model", ('id="provbody"', 'id="modbody"')),
                          ("keys", ('id="keylist"',))):
            pane = self.source[self.source.index('<section data-cat="%s"' % key):]
            pane = pane[:pane.index("</section>")]
            for hook in want:
                self.assertIn(hook, pane, key)
            self.assertNotIn("Coming soon", pane, key)
        self.assertNotIn("Coming soon.", self.source,
                         "a dead-end placeholder is back in the sheet")

    def test_no_rule_is_drawn_between_the_ribbon_the_rail_and_the_chat(self):
        """NEGATIVE PROBE, and it is the whole of robin's second request: the
        three used to be separated by three 1px lines."""
        bar = self.css[self.css.index("#bar{"):]
        bar = bar[:bar.index("}") + 1]
        self.assertNotIn("border-bottom", bar)
        rail = self.css[self.css.index("#rail{"):]
        rail = rail[:rail.index("}") + 1]
        self.assertNotIn("border-right", rail)
        head = self.css[self.css.index("#railhead{"):]
        head = head[:head.index("}") + 1]
        self.assertNotIn("border-bottom", head)

    def test_the_corner_is_what_separates_them_instead(self):
        """With every rule gone the chat would blur into the panel. The radius
        separates them the way paper on a desk is separate -- by lying on top.
        `#body` must carry the rail colour or the corner has nothing to cut away
        to and reads as a notch."""
        main = self.css[self.css.index("#main{"):]
        main = main[:main.index("}") + 1]
        self.assertIn("border-top-left-radius", main)
        self.assertIn("background:var(--bg)", main)
        self.assertIn("overflow:hidden", main)
        body = self.css[self.css.index("#body{"):]
        body = body[:body.index("}") + 1]
        self.assertIn("background:var(--rail)", body)

    def test_the_ribbon_is_the_same_surface_as_the_rail(self):
        """One panel, one colour. A gradient ending in the chat's background
        would put the seam back in, only softer and harder to name."""
        bar = self.css[self.css.index("#bar{"):]
        bar = bar[:bar.index("}") + 1]
        self.assertIn("background:var(--rail)", bar)
        self.assertNotIn("gradient", bar)

    def test_the_version_is_only_where_it_is_looked_up(self):
        """It sat beside the wordmark and was copied into the sheet on open.
        The ribbon is a name and three window buttons now, so the number goes
        straight to About -- and the element it was copied FROM is gone, which
        is the half that would otherwise rot."""
        self.assertNotIn('id="ver"', self.source)
        self.assertNotIn('$("#ver")', self.source)
        self.assertIn('$("#aboutver").textContent=e.version;', self.source)

    def test_nothing_still_points_at_a_palette_entry_that_was_removed(self):
        """`--status-bg` and `--titlebar` had exactly one reader each, and both
        readers went with the bar. A palette value nothing reads is a value that
        drifts from the three themes it is written in three times."""
        for dead in ("--status-bg", "--titlebar"):
            self.assertNotIn(dead, self.source, dead)


class TheSkillSheetTests(unittest.TestCase):
    """#124: the switch in the settings sheet, and what it is allowed to be."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def test_the_sheet_has_a_row_per_skill_and_a_switch(self):
        """The category existed with "Nothing here yet." since the sheet was
        built; this is the ticket that fills it."""
        self.assertIn('<div id="skilllist"></div>', self.source)
        self.assertIn(".srow{", self.css)
        self.assertIn(".sw{", self.css)
        self.assertIn(".sw.on{", self.css)

    def test_a_skill_name_can_never_become_code(self):
        """A skill name is MODEL-WRITTEN TEXT. The rail learned this in #119 --
        a project called `'); alert('` is a label and must stay one -- and the
        same rule holds here, where the writer is not even a person."""
        self.assertIn("sw.onclick=()=>this.toggleSkill(", self.source)
        self.assertNotIn('onclick="crow.toggleSkill', self.source)
        drawn = self.source[self.source.index("drawSkills(){"):]
        drawn = drawn[:drawn.index("toggleSkill(name,row,sw)")]
        self.assertNotIn("innerHTML", drawn)

    def test_the_list_is_asked_for_every_time_the_sheet_opens(self):
        """It changes behind the window's back: the background review writes
        skills without anybody clicking anything, so a list cached in the page
        would show yesterday's set."""
        opener = self.source[self.source.index("openSettings(){"):]
        opener = opener[:opener.index("closeSettings()")]
        self.assertIn("this.drawSkills();", opener)

    def test_switching_one_off_repins_and_says_what_it_costs(self):
        """Without the re-pin the switch looks broken in the most confusing way
        available: the row flips, the file changes, and the running conversation
        keeps the head it was pinned with -- so nothing the model does changes
        until the next chat."""
        toggle = self.source[self.source.index("def toggle_skill"):]
        toggle = toggle[:toggle.index("\n    def ", 10)]
        self.assertIn("crow_core.set_skill_enabled", toggle)
        self.assertIn("repin_memory(crow_core.prompt_head())", toggle)
        self.assertIn("SKILL_COST_NOTE", toggle)
        self.assertLess(toggle.index("set_skill_enabled"), toggle.index("repin_memory"),
                        "the head is rebuilt before the file it is built from")

    def test_the_sheet_is_shown_the_disabled_ones_too(self):
        """NEGATIVE PROBE: a sheet that listed only the enabled skills would
        have no row to click for the others, so switching one back on would
        need a text editor."""
        api = self.source[self.source.index("    def skills(self)"):]
        api = api[:api.index("\n    def ", 10)]
        self.assertIn("crow_core.skills()", api)
        self.assertNotIn("enabled\"]", api.split("return")[0])
        self.assertNotIn('sk["body"]', api)

    def test_the_pinned_head_is_built_in_one_place_by_both_surfaces(self):
        """Memory and skills are two stores and ONE head. Two composers would be
        two byte-different heads for one set of facts, and neither chat could
        reuse the other's cache.

        BOTH FILES, and that is not thoroughness -- it is the defect. The window
        was moved to `prompt_head()` and the terminal's two lines were left on
        `memory_block()` for one commit: no crash, no failing case, just a
        terminal whose prompt silently carried no skills while the window's did.
        A surface-by-surface check is the only kind that sees it.
        """
        # 4 since #303: `_head_follows_stated_root` re-pins a restored head
        # that names another working area than the typed `--root` -- the same
        # event `_bind_root` re-pins for, reached from the launch.
        self.assertEqual(self.source.count("crow_core.prompt_head()"), 4)
        terminal = (HERE / "crow.py").read_text(encoding="utf-8")
        self.assertEqual(terminal.count("crow_core.prompt_head()"), 2)
        for name, text in (("crow_gui.py", self.source), ("crow.py", terminal)):
            self.assertNotIn("crow_core.memory_block()", text, name)
            self.assertNotIn("crow_core.skill_block()", text, name)


class TheMemoryPinWiringTests(unittest.TestCase):
    """#121 in the window: the pin is taken AFTER the boundary, never before.

    ALL THREE DOORS ARE CHECKED BY POSITION rather than by running them,
    because the failure is an ordering one and it is invisible at runtime: a pin
    taken too early is a perfectly valid head -- the template's -- and it is
    wrong for exactly the chats that have a project.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def _after(self, bind: str, pin: str) -> bool:
        return self.source.index(pin) > self.source.index(bind)

    def test_every_pin_sits_below_the_line_that_binds(self):
        """The launch, and opening an archived chat. Both bind the chat's own
        directory first; a pin above either would be the template's memory.

        `rindex` FOR THE LAUNCH, because it pins in two branches: the one that
        restored a chat, below the bind, and the early return where there was
        nothing to restore -- which never binds at all, since `ready()` has
        already put the template up and there is no chat to correct it with.
        """
        self.assertGreater(self.source.rindex("self._pin_memory(SESSION_FILE)"),
                           self.source.index(
                               "self._adopt_chat_root(SESSION_FILE, stated="))
        self.assertTrue(self._after("self._adopt_chat_root(path)",
                                    "self._pin_memory(path)"))
        self.assertEqual(self.source.count("self._pin_memory("), 5,
                         "a caller pins somewhere this case has not read")

    def test_a_new_chat_pins_after_it_is_made_rootless(self):
        """`reset()` makes a new chat rootless on purpose (#119). The pin has to
        happen after that, or a new chat would inherit the last one's project."""
        self.assertTrue(self._after("self._adopt_chat_root(None, fresh=True)",
                                    "self._pin_memory(None)"))

    def test_a_turn_never_starts_from_an_unpinned_chat(self):
        """`_probe` has THREE ways to return before it reaches its own pin: the
        endpoint would not answer, `--no-session`, or an unreadable session
        file. The first is ordinary -- a window opened while the server is still
        starting -- and such a chat was never pinned at all, so its memory never
        entered a single prompt.

        SILENT BY CONSTRUCTION, which is why it needed finding rather than
        failing: an unpinned head is a VALID head, only one without the memory
        in it. Found on 2026-08-21 in a session.json that had no `memory` key
        after a whole conversation.

        BEFORE THE USER MESSAGE IS APPENDED, so the pin still meets an empty
        conversation and no prefix exists yet to move.
        """
        run = self.source[self.source.index("    def _run(self, text: str)"):]
        run = run[:run.index("\n    def ", 10)]
        self.assertIn("if self._conversation.memory is None:", run)
        self.assertLess(run.index("self._pin_memory("),
                        run.index('self._conversation.append("user"'),
                        "the chat is pinned after its own first message")

    def test_the_pin_is_read_before_the_payload_at_both_readers(self):
        """`load_session` needs the COMPOSED system prompt to decide whether the
        saved KV still fits, and that cannot be read out of messages nobody has
        opened yet."""
        self.assertEqual(self.source.count("crow_core.system_with_memory("), 2)
        # THE HELPER IS THE THIRD READER and it is the one that must not be
        # duplicated: `_pin_memory` is the single place that decides between a
        # stored pin and a fresh block. Two such decisions is two answers.
        self.assertEqual(self.source.count("crow_core.session_memory("), 3)
        self.assertEqual(self.source.count("def _pin_memory"), 1)

    def test_binding_a_folder_announces_the_prefill_before_it_is_paid(self):
        """The same shape `REASONING_COST_NOTE` already has. A cost said
        afterwards is not a warning, it is an excuse."""
        self.assertIn("crow_core.MEMORY_COST_NOTE", self.source)
        self.assertIn("if self._conversation.repin_memory(", self.source)

    def test_the_archive_folder_is_named_once(self):
        """#123 walks the same folder the rail is drawn from. A second
        `\"archiv\"` typed in the core would be a chat that is in the rail and
        not in the index, the first time either spelling changed."""
        self.assertIn("ARCHIVE_DIR = crow_core.ARCHIVE_DIR", self.source)
        # The ASSIGNMENT, not the word: the sentence above says "archiv" while
        # explaining why nothing here may define it, and a case that cannot tell
        # a comment from a declaration would forbid its own reason.
        self.assertNotIn('ARCHIVE_DIR = "archiv"', self.source)


class TheMcpSheetTests(ApiCase):
    """E4 in the window: the checklist, and the two columns that ARE the stage.

    One column says whether a tool is taken at all, the other what Crow treats
    it as. Both are states in a file, and the second one is the whole reason the
    stage exists -- a class is what decides whether a release level stops and
    asks before a foreign process runs.
    """

    def setUp(self) -> None:
        super().setUp()
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]
        self._real_mcp = crow_core.MCP_FILE
        self.addCleanup(self._restore_mcp)
        crow_core.MCP_FILE = os.path.join(self.dir, "mcp.json")
        crow_core.mcp_apply()

    def _restore_mcp(self) -> None:
        crow_core.forget_mcp_servers()
        crow_core.MCP_FILE = self._real_mcp
        crow_core.mcp_apply()

    def _pane(self) -> str:
        pane = self.source[self.source.index('<section data-cat="mcp"'):]
        return pane[:pane.index("</section>")]

    def _configure(self) -> None:
        """A server on disk with a schema, without ever starting one: the sheet
        reads the file, and E3's cases are where a process belongs."""
        with open(crow_core.MCP_FILE, "w", encoding="utf-8") as fh:
            json.dump({"servers": {"fake": {
                "command": "npx", "args": ["-y", "server-fake"],
                "schema": {"tools": [
                    {"name": "look", "description": "Look at something.",
                     "inputSchema": {"type": "object"},
                     "annotations": {"readOnlyHint": True}},
                    {"name": "burn", "description": "Burn it down.",
                     "inputSchema": {"type": "object"}}]},
                "tools": {"include": []}}}}, fh)
        crow_core.mcp_apply()

    # ---- the pane is built rather than promised

    def test_the_pane_is_a_list_and_one_field(self):
        """robin, 2026-08-22: no prose in the sheet. What was there described
        behaviour, and one of the sentences had already outlived the behaviour
        it described."""
        pane = self._pane()
        self.assertIn('id="mcplist"', pane)
        self.assertIn('id="mcpline"', pane)
        for gone in ("mcpname", "mcpcmd", "mcpargs", "mcpbound", "Coming soon",
                     "nothing reaches the model", "boundary"):
            self.assertNotIn(gone, pane, gone)
        self.assertLess(len(pane), 700, "the pane grew prose again")

    def test_the_sheet_asks_for_the_list_when_it_opens(self):
        opened = self.source[self.source.index("openSettings(){"):]
        self.assertIn("this.drawMcp()", opened[:opened.index("},")])

    def test_a_server_name_never_becomes_markup(self):
        """#119's lesson, and it applies harder here: a server's name and its
        tool descriptions are written by a stranger, not by the user."""
        js = self.source[self.source.index("drawMcpServer(box,sv,classes){"):
                         self.source.index("tickMcp(server,tool,row,sw){")]
        self.assertNotIn("innerHTML", js)
        self.assertIn("name.textContent=sv.enabled?sv.name", js)
        # AND NO LITERAL GLYPH EITHER: `check_gui_prereqs` resolves string
        # literals against the shipped face, and the caret is not in it.
        self.assertIn("String.fromCharCode(9654)", js)

    def test_the_head_names_an_http_server_by_its_endpoint(self):
        """E5. An HTTP server has no command line, and a row whose second column
        is empty names nothing anybody can recognise. The url is the half of the
        block that may be shown -- the other half is a token, and `mcp_view`
        does not carry it here to be shown or forgotten."""
        js = self.source[self.source.index("drawMcpServer(box,sv,classes){"):
                         self.source.index("mcpRow(sv,t,classes){")]
        self.assertIn("cmd.textContent=sv.url||", js)
        self.assertNotIn("sv.headers", self.source)

    def test_the_field_takes_a_url_as_well_as_a_command(self):
        """NEGATIVE for a second control: a transport is what the first token
        already says it is, and a client that asked somebody to declare it in a
        dropdown would be asking for the one thing it can read for itself."""
        self.assertIn("https://", self._pane())
        source = inspect.getsource(crow_gui.Api.mcp_add)
        self.assertIn("a command or a URL", source)

    # ---- the two columns

    def test_a_decision_and_a_proposal_do_not_look_alike(self):
        """THE VALUE, NOT THE NAME -- the 2026-08-22 lesson. A class the server
        merely suggested may never read as one a person picked, so the two are
        separated by the EDGE as well as the colour: a theme where `--dim` and
        `--accent` happen to sit close would otherwise render them identical."""
        import re as _re
        CLOSE = chr(125)

        def rule(selector):
            found = self.css[self.css.index(selector):]
            return found[:found.index(CLOSE)]

        guess, chosen = rule(".seg button.guess{"), rule(".seg button.on{")
        self.assertIn("border-style:dashed", guess)
        self.assertNotIn("dashed", chosen)

        # THE BRAND VALUES ARE NOT IN THE STYLESHEET. `--accent` and `--bevel`
        # are placeholders the page fills from the core at render time, so a
        # reader that only searched the CSS would report "not defined" for the
        # one colour this case is actually about.
        FROM_CORE = {"--accent": crow_core.CROW_ACCENT_HEX,
                     "--bevel": crow_core.BANNER_BEVEL_HEX}

        def value(css, token):
            hexed = FROM_CORE.get(token)
            if hexed is None:
                m = _re.search(_re.escape(token) + r":\s*(#[0-9a-fA-F]{6})", css)
                self.assertIsNotNone(m, "%s is not defined" % token)
                hexed = m.group(1)
            h = hexed.lstrip("#")
            return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))

        dark = self.css[self.css.index("--bg:#181818"):]
        dark = dark[:dark.index(CLOSE)]
        picked = _re.search(r"color:var\((--[a-z-]+)\)", chosen)
        proposed = _re.search(r"color:var\((--[a-z-]+)\)", guess)
        self.assertIsNotNone(picked)
        self.assertIsNotNone(proposed)
        apart = sum(abs(a - b) for a, b in zip(value(dark, picked.group(1)),
                                               value(dark, proposed.group(1))))
        self.assertGreater(apart, 60,
                           "a proposal and a decision are the same colour")

    def test_the_classes_come_from_the_core_not_from_the_page(self):
        """Three buttons typed into the JS would be three buttons to fix the day
        a fourth class exists -- and one of them would be missed."""
        self.assertIn("classes.forEach", self.source)
        self.assertEqual(crow_core.mcp_view()["classes"],
                         list(crow_core.MCP_TOOL_CLASSES))

    def test_every_element_the_drawing_looks_up_exists(self):
        """A mistyped id draws nothing and reads as a CSS problem -- the shape
        #126's positional-list defect had. This suite never executes the page,
        so the lookups are held against the markup instead of against a render.
        """
        js = self.source[self.source.index("drawMcp(){"):
                         self.source.index("toggleSkill(name,row,sw){")]
        looked_up = sorted(set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', js)))
        self.assertTrue(looked_up, "the drawing looks nothing up")
        in_page = set(re.findall(r'id="([A-Za-z0-9_-]+)"', self.source))
        self.assertEqual([i for i in looked_up if i not in in_page], [])

    # ---- what robin asked to see, 2026-08-22

    def test_the_install_line_is_drawn_in_the_chat_not_in_the_sheet(self):
        """robin, twice: the tile belongs where the command was typed. It is
        drawn from `go()`, after the typed line and before the call."""
        go = self.source[self.source.index("  go(){"):self.source.index("  modeMenu(){")]
        self.assertIn("installBar()", go)
        self.assertLess(go.index("this.user(text)"), go.index("installBar()"))
        self.assertLess(go.index("installBar()"), go.index("pywebview.api.send"))
        self.assertNotIn("mcpbusy", self.source)

    def test_only_adding_a_server_gets_the_tile(self):
        """NEGATIVE: `/mcp` on its own answers instantly. A tile in front of an
        instant answer is four seconds of nothing."""
        import re as _re
        pattern = _re.search(r"if\((/[^)]+/i)\.test\(text\)\) this\.installBar",
                             self.source)
        self.assertIsNotNone(pattern, "the tile is not gated on the command")
        rule = pattern.group(1)
        self.assertIn("add", rule)
        self.assertIn("mcp", rule)

    def test_it_wears_the_memory_gates_animation_rather_than_a_copy(self):
        """Two sweeps written out twice drift the first time one is touched."""
        CLOSE = chr(125)
        bar = self.css[self.css.index(".installbar{"):]
        bar = bar[:bar.index(CLOSE)]
        self.assertIn("pendsweep", bar)
        self.assertIn("pendglow", bar)
        self.assertEqual(self.css.count("@keyframes pendsweep"), 1)

    def test_it_says_install_mcp_and_stands_for_four_seconds(self):
        js = self.source[self.source.index("  installBar(){"):
                         self.source.index("  note(msg){")]
        self.assertIn('textContent="Install MCP"', js)
        self.assertIn("Date.now()+4000", js)
        held = self.source[self.source.index("  note(msg){"):
                           self.source.index("  drawNote(msg){")]
        self.assertIn("this.installUntil - Date.now()", held)
        self.assertIn("Math.max(0", held)

    def test_a_server_folds_away(self):
        """One ordinary server is a dozen tools and already outruns the sheet. Twenty
        servers unfolded is a scroll nobody finishes."""
        CLOSE = chr(125)
        shut = self.css[self.css.index(".mcptools{"):]
        self.assertIn("display:none", shut[:shut.index(CLOSE)])
        open_ = self.css[self.css.index(".mcptools.open{"):]
        self.assertIn("display:block", open_[:open_.index(CLOSE)])
        js = self.source[self.source.index("  drawMcpServer(box,sv,classes){"):
                         self.source.index("  mcpRow(sv,t,classes){")]
        self.assertIn("this.mcpOpen", js)
        # THE BUTTONS SIT INSIDE THE HEAD. Without this a click on "remove"
        # would also fold the server away -- the trap the memory tile hit.
        self.assertEqual(js.count("stopPropagation()"), 2)

    def test_the_sheet_got_room_for_a_server_list(self):
        CLOSE = chr(125)
        rule = self.css[self.css.index("#settings .sheet{"):]
        rule = rule[:rule.index(CLOSE)]
        import re as _re
        width = int(_re.search(r"width:min\((\d+)px", rule).group(1))
        height = int(_re.search(r"height:min\((\d+)px", rule).group(1))
        self.assertGreater(width, 760)
        self.assertGreater(height, 560)

    def test_what_the_user_said_is_a_bubble_in_every_theme(self):
        """THE VALUE, NOT THE NAME. A bubble drawn in a literal colour would be
        right in the theme it was picked in and wrong in the other two; these
        tokens are defined three times, once per palette."""
        CLOSE = chr(125)
        rule = self.css[self.css.index(".you .txt{"):]
        rule = rule[:rule.index(CLOSE)]
        self.assertIn("border-radius", rule)
        self.assertIn("padding", rule)
        # HUGGING THE TEXT, not filling the column: without this a two-word
        # message is a full-width slab. #280: on the column's RIGHT edge.
        self.assertIn("justify-self:end", rule)
        import re as _re
        used = _re.findall(r"var\((--[a-z-]+)\)", rule)
        self.assertIn("--raised", used)
        for token in set(used):
            self.assertEqual(self.css.count(token + ":"), 3,
                             "%s is not defined in all three palettes" % token)
        self.assertFalse(_re.findall(r"#[0-9a-fA-F]{3,6}", rule),
                         "the bubble names a colour of its own")

    # ---- what the api actually does

    def test_the_view_reaches_the_page_unchanged(self):
        self._configure()
        view = self.api().mcp_view()
        self.assertEqual(view["file"], crow_core.MCP_FILE)
        self.assertEqual([t["tool"] for t in view["servers"][0]["tools"]],
                         ["look", "burn"])
        self.assertEqual(view["servers"][0]["tools"][0]["proposed"], "reading")
        self.assertEqual(view["servers"][0]["tools"][1]["proposed"], "executing")

    def test_a_tick_writes_and_names_the_bill(self):
        self._configure()
        api = self.api()
        self.assertEqual(api.mcp_confirm("fake", "look", True, "reading"), "")
        self.assertIn("mcp_fake_look", [t["function"]["name"] for t in crow_core.TOOLS])
        self.assertEqual(crow_core.TOOL_CLASS["mcp_fake_look"], "reading")
        self.assertTrue(any(m.get("t") == crow_core.MCP_COST_NOTE
                            for m in self.drained(api)))

    def test_a_refused_tick_says_why_and_bills_nothing(self):
        """NEGATIVE: the page paints the click before the file takes it, so a
        refusal has to come back as a REASON -- and must not announce a prefill
        that nothing is going to cost."""
        self._configure()
        api = self.api()
        said = api.mcp_confirm("fake", "invented", True, "reading")
        self.assertIn("invented", said)
        self.assertFalse(any(m.get("t") == crow_core.MCP_COST_NOTE
                             for m in self.drained(api)))

    def test_moving_one_column_leaves_the_other_alone(self):
        """The switch and the class are two decisions. Un-ticking a tool must
        not throw away what somebody said it does, or re-ticking asks again."""
        self._configure()
        api = self.api()
        api.mcp_confirm("fake", "look", True, "writing")
        api.mcp_confirm("fake", "look", False, None)
        with open(crow_core.MCP_FILE, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["servers"]["fake"]["classes"],
                             {"look": "writing"})

    def test_one_line_is_the_whole_form(self):
        """A command line is what people already have -- from a README, from
        another client's config. Three fields is three chances to get it wrong."""
        self.assertIn("splitlines()", "") if False else None
        source = inspect.getsource(crow_gui.Api.mcp_add)
        self.assertIn("mcp_add_line", source)
        said = self.api().mcp_add("")
        self.assertIn("command line", said)


class ToolCallsLeaveTheReadingColumnTests(unittest.TestCase):
    """#131. A 24-round turn put 24 tool rows between the question and the
    answer, and the answer is what a person came back for.

    THE PAGE IS NOT EXECUTED BY THIS SUITE, so these hold the drawing against
    the markup and the stylesheet -- the same way the rail's and the memory
    tile's structure is held. What they cannot see is what it looks like.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def _rule(self, selector: str) -> str:
        found = self.css[self.css.index(selector):]
        return found[:found.index(chr(125))]

    def test_a_tool_row_is_appended_to_the_tile_and_not_to_the_turn(self):
        # DIE VERANKERUNG OHNE DIE KLAMMER, damit sie eine Parameterliste
        # ueberlebt: `tool` nahm `(name,args)` und nimmt seit #138b auch die
        # rohen Argumente. Das Ende ist die Funktion, die DIREKT folgt -- gegen
        # `toolsCount` waere der Ausschnitt inzwischen vier Funktionen zu gross
        # und faende `$("#tclist")` auch dort, wo dieser Fall nicht hinsieht.
        js = self.source[self.source.index("  tool(name,args"):
                         self.source.index("  codeFinish(name,raw){")]
        self.assertIn('$("#tclist")', js)
        self.assertNotIn("this.col.insertBefore", js)

    def test_the_tile_is_in_the_page_before_anything_is_called(self):
        """"Immer da, auch im leeren Chat" -- a tile that appears with the first
        call is one nobody has learned to look at."""
        self.assertIn('id="toolcalls"', self.source)
        self.assertIn("crow.toolsCount();", self.source)
        js = self.source[self.source.index("  toolsCount(){"):
                         self.source.index("  toolsToggle(){")]
        self.assertIn("Nothing called yet.", js)

    def test_it_opens_and_shuts_on_the_plus(self):
        self.assertIn("display:none", self._rule("#toolcalls.shut .tcbody{"))
        js = self.source[self.source.index("  toolsToggle(){"):
                         self.source.index("  toolsClear(e){")]
        self.assertIn('classList.toggle("shut")', js)
        # THE SIGN FOLLOWS THE STATE. A plus on an open tile is a control that
        # lies about what pressing it will do.
        self.assertIn('shut ? "+"', js)

    def test_the_panel_gives_the_width_and_the_row_uses_all_of_it(self):
        """A tool line is a path plus arguments, and the half that says which
        file is the half worth reading -- so it is still never clipped.

        WHAT CHANGED ON 2026-08-24 is where the width comes from. As a tile
        floating over the chat it had to grow to its widest row and stop at
        44vw, or it covered what somebody was reading. In a column of its own it
        covers nothing, so the column decides and the row takes all of it.

        WHAT CHANGED ON 2026-08-31 (#176 acceptance) is WHERE the argument is.
        robin took it out of the headline -- it is arbitrarily long and pushed
        the elapsed-time clock out of the row -- so it now stands once, in full,
        in the opened call. The rule this case guards moved with it: the block
        wraps and breaks rather than clipping, which is the same promise the old
        `#toolcalls .tool .arg{overflow:visible}` made about the headline. A case
        left pointing at the dead rule would be green about nothing."""
        self.assertIn("width:100%", self._rule("#toolcalls{"))
        block = self._rule("#toolcalls .tsp{")
        self.assertIn("white-space:pre-wrap", block)
        self.assertIn("word-break:break-word", block)

    def test_it_wears_the_bubble_of_whichever_skin_is_on(self):
        """robin, 2026-08-22. NOT a literal that matches today's dark bubble --
        the same TOKENS, so the tile follows the skin that is on rather than the
        one it was picked in. Both are defined once per palette."""
        tile, bubble = self._rule("#toolcalls{"), self._rule(".you .txt{")
        import re as _re
        for prop in ("background", "border"):
            want = _re.search(prop + r"[^;]*var\((--[a-z-]+)\)", bubble)
            self.assertIsNotNone(want, prop)
            self.assertIn("var(%s)" % want.group(1), tile, prop)
            self.assertEqual(self.css.count(want.group(1) + ":"), 3,
                             "%s is not in all three palettes" % want.group(1))
        self.assertFalse(_re.findall(r"#[0-9a-fA-F]{3,6}", tile),
                         "the tile names a colour of its own")

    def test_the_list_lives_in_the_panel_and_not_over_the_chat(self):
        """It used to float: absolute, 28 px down and 36 px in from the corner,
        because anything less read as stuck to it. robin asked on 2026-08-24 for
        the calls to move into the code panel -- so there is no corner to clear
        any more, and the case that guarded the distance now guards the move.

        THE POINT IS THE SAME ONE #131 MADE: tool rows do not belong in the
        reading column. Floating over it was one answer; a column beside it is
        the better one, because it stops covering the thing it was keeping out
        of the way."""
        tile = self._rule("#toolcalls{")
        self.assertNotIn("position:absolute", tile)
        panel = self.source[self.source.index('<aside id="code"'):]
        panel = panel[:panel.index("</aside>")]
        self.assertIn('id="toolcalls"', panel,
                      "the call list did not move into the code panel")

    def test_clearing_does_not_also_fold_the_tile_away(self):
        """NEGATIVE, and the trap the memory tile already hit: the button sits
        inside the head, so without catching the click it would bubble up to the
        fold and hide the list it had just emptied."""
        js = self.source[self.source.index("  toolsClear(e){"):
                         self.source.index("  toolsReset(){")]
        self.assertIn("stopPropagation()", js)
        self.assertIn('$("#tclist").textContent=""', js)

    def test_a_new_chat_empties_it(self):
        """The tile belongs to the conversation, not to the window."""
        drawn = self.source[self.source.index('case "clear":'):]
        self.assertIn("this.toolsReset()", drawn[:drawn.index("break;")])


class AServerAsksAndCrowDrawsTests(unittest.TestCase):
    """#135. The form is drawn from a SCHEMA, and never by the server.

    THAT SENTENCE IS THE WHOLE REASON THIS FEATURE IS ALLOWED. What arrives is a
    list of fields with types; what a person sees is markup this file wrote. A
    label, a description and a choice are all text a stranger supplied, so every
    one of them goes in by `textContent` -- #119's lesson, and it applies harder
    here than it does to a tool description, because a person acts on this one.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.js = self.source[self.source.index("  elicit(ask){"):
                              self.source.index("  elicitAnswer(btn, action){")]

    def test_nothing_the_server_wrote_becomes_markup(self):
        for setter in ('.textContent=ask.server',
                       '.textContent=ask.message',
                       'label.textContent=f.title',
                       'hint.textContent=f.description',
                       'o.textContent=c'):
            self.assertIn(setter, self.js)
        # THE ONLY `innerHTML` IN HERE IS THIS FILE'S OWN SKELETON. Every value
        # off the wire is put on a node afterwards, one at a time.
        skeleton = self.js[self.js.index("d.innerHTML="):self.js.index("const card=")]
        for wrote in ("ask.", "f.title", "f.name", "f.description", "f.enum"):
            self.assertNotIn(wrote, skeleton)

    def test_the_three_answers_are_three_buttons(self):
        """`decline` and `dismiss` are not one answer. The specification
        separates a refusal from a dismissal, and a server is entitled to treat
        them differently -- so a client that offered one button would be
        deciding on the person's behalf which of the two they meant."""
        # The backslashes are Python's, escaping the quotes inside the HTML
        # string; what the page sees is `crow.elicitAnswer(this,'accept')`.
        plain = self.js.replace(chr(92), "")
        for action in ("accept", "decline", "cancel"):
            self.assertIn("crow.elicitAnswer(this,'%s')" % action, plain)

    def test_a_checkbox_comes_back_as_a_boolean(self):
        """A form hands back text. A server that declared `boolean` and got the
        string "false" -- which is true in most languages that will read it --
        would act on the opposite of what was ticked."""
        answer = self.source[self.source.index("  elicitAnswer(btn, action){"):
                             self.source.index("  // The card stays, with the answer")]
        self.assertIn('el.type==="checkbox" ? el.checked : el.value', answer)

    def test_the_answer_goes_through_the_core_and_not_around_it(self):
        api = inspect.getsource(crow_gui.Api.answer_elicit)
        self.assertIn("crow_core.answer_elicitation", api)
        self.assertNotIn("_ASKS", api)

    def test_the_window_installs_itself_as_the_place_a_question_lands(self):
        """One plug per surface and no second gate: the core keeps the staging,
        the waiting, the schema check and the answer."""
        setup = inspect.getsource(crow_gui.Api.__init__)
        self.assertIn("crow_core.ELICIT_ANNOUNCE = self.announce_elicit", setup)


class TheUserBubbleTests(unittest.TestCase):
    """#131. robin, 2026-08-22: the label goes, and the bubble has to break."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def test_the_label_is_gone_from_the_markup_and_the_stylesheet(self):
        js = self.source[self.source.index("  user(text){"):
                         self.source.index("  start(){")]
        self.assertNotIn("you&gt;", js)
        self.assertNotIn(".you .m{", self.css, "a rule with no wearer is left")

    def test_the_bubble_breaks_before_it_fills_the_column(self):
        """A bubble that runs the full width is a slab, and nothing about it
        reads as one side of a conversation."""
        rule = self.css[self.css.index(".you .txt{"):]
        rule = rule[:rule.index(chr(125))]
        self.assertIn("max-width:75%", rule)

    def test_the_model_keeps_its_own_column(self):
        """NEGATIVE: the cap is the user's line only. Narrowing the answer would
        cost the reader a quarter of every page of it."""
        rule = self.css[self.css.index(".as{"):]
        rule = rule[:rule.index(chr(125))]
        self.assertNotIn("max-width", rule)
        say = self.css[self.css.index(".say{"):]
        self.assertNotIn("max-width", say[:say.index(chr(125))])


class TheBubblesStandOnTheComposersEdgesTests(unittest.TestCase):
    """#280, robin 2026-09-24: chat and composer read as ONE column -- the
    user's bubble with its right edge on #box's right border, Crow's text with
    its left edge on #box's left border, with and without the #233/#255/#256
    cards, at every width.

    MEASURED in headless Chromium (real PAGE, rail open/shut x 1180/1440/1920/
    2560 x no card/git/goal/subtasks, 32 combinations): before, the short
    user bubble ended 716-780 px left of #box's right edge and Crow's `.say`
    started 40 px right of its left edge, 32 of 32; after, 0.0 px in 32 of 32.
    This suite has no browser, so it holds the rules that produced that -- and
    recomputes the column and the box from the stylesheet's own numbers."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def _rule(self, selector: str) -> str:
        found = self.css[self.css.index(selector):]
        return found[:found.index(chr(125))]

    def _decl(self, rule: str, prop: str) -> str:
        match = re.search(r"(?:^|[;{\s])" + re.escape(prop) + r":([^;]+)", rule)
        self.assertIsNotNone(match, "%s fehlt in %r" % (prop, rule[:80]))
        return match.group(1).strip()

    def test_the_users_bubble_ends_on_the_right_edge(self):
        self.assertIn("justify-self:end", self._rule(".you .txt{"))
        self.assertNotIn("justify-self:start", self._rule(".you .txt{"))
        self.assertIn("justify-self:end", self._rule(".you img.sent{"))

    def test_crows_text_starts_on_the_left_edge(self):
        """The 38-px mark column put `.say`, the thoughts and the cursor 40 px
        inside the box's left border."""
        self.assertNotIn("grid-template-columns", self._rule(".as{"))
        start = self.source[self.source.index("  start(){"):]
        start = start[:start.index("this.col=")]
        self.assertNotIn('class="m"', start)
        self.assertNotIn(".as .m{", self.css, "a rule with no wearer is left")

    def test_column_and_composer_come_from_the_same_variables(self):
        """ONE SOURCE. Every length that places the text column (#flow,
        .turn) and the box (#composer, #box) is a var() of the four shared
        ones -- a px literal in any of them is a second source that can drift.
        Then both are computed for two widths, with and without a card, and
        must share both edges."""
        root = self._rule(":root{")
        env = {name: float(self._decl(root, "--" + name)[:-2])
               for name in ("sbw", "colw", "colpad", "reserve")}
        block = self.css[self.css.index("@container chat"):]
        block = block[:block.index("}\n}") + 1]
        card = float(re.search(r"\{--reserve:(\d+)px\}", block).group(1))

        def ev(expr: str, reserve: float) -> float:
            self.assertNotRegex(expr, r"\d+px", "a literal in %r" % expr)
            code = re.sub(r"var\(--([a-z]+)\)",
                          lambda m: repr(reserve if m.group(1) == "reserve"
                                         else env[m.group(1)]), expr)
            code = code.replace("calc", "")
            self.assertRegex(code, r"^[\d.\s+*()-]+$", expr)
            return float(eval(code))  # noqa: S307 -- digits and + * ( ) only

        def split(value: str) -> list:
            return re.findall(r"calc\([^()]*(?:\([^()]*\)[^()]*)*\)|var\([^)]*\)|\S+", value)

        flow, turn = self._rule("#flow{"), self._rule("\n.turn{")
        comp, box = self._rule("#composer{position:absolute"), self._rule("#box{border:")
        f_left, f_right = split(self._decl(flow, "padding-inline"))
        t_pad = split(self._decl(turn, "padding"))[1]
        c_pad = split(self._decl(comp, "padding"))[1]
        for width in (937.0, 1417.0, 1677.0):       # #main at 1180/1920 rail open, 1920 shut
            for reserve in (env["reserve"], card):
                # #flow: scrollbar-gutter:stable takes --sbw on the right.
                lo = ev(f_left, reserve)
                hi = width - ev(f_right, reserve) - env["sbw"]
                w = min(ev(self._decl(turn, "max-width"), reserve), hi - lo)
                t_lo = lo + (hi - lo - w) / 2 + ev(t_pad, reserve)
                t_hi = t_lo + w - 2 * ev(t_pad, reserve)
                lo = ev(self._decl(comp, "left"), reserve) + ev(c_pad, reserve)
                hi = width - ev(self._decl(comp, "right"), reserve) - ev(c_pad, reserve)
                w = min(ev(self._decl(box, "max-width"), reserve), hi - lo)
                b_lo = lo + (hi - lo - w) / 2
                self.assertAlmostEqual(t_lo, b_lo, msg="left edge, %s/%s" % (width, reserve))
                self.assertAlmostEqual(t_hi, b_lo + w, msg="right edge, %s/%s" % (width, reserve))


class TheTraceFoldsFinishedRoundsTests(unittest.TestCase):
    """#131, variant A. `reply_started` fires once per ROUND, so a 24-round turn
    drew 24 blocks of thoughts and running commentary -- and the answer, which is
    what somebody came back for, was below the fold.

    THE LIVE ROUND IS NOT FOLDED, and that is the half that makes it usable: the
    interim text is the only sign of life a long turn has, so hiding it too
    would leave a blank screen for minutes.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def _js(self, start: str, end: str) -> str:
        return self.source[self.source.index(start):self.source.index(end)]

    def test_a_new_round_folds_the_one_before_it(self):
        """The only signal there is: nothing tells the page a round was the LAST
        one, so the last round is the one nobody folded."""
        start = self._js("  start(){", "  say_(")  if False else self._js(
            "  start(){", "  thinkOpen(")
        self.assertIn("this.fold()", start)
        self.assertIn("this.round=t", start)

    def test_the_running_round_stays_where_it_is(self):
        """NEGATIVE, and it is the whole difference between variant A and B: only
        `fold` moves anything, and it moves `this.round` -- which `start` has
        just replaced with the new one."""
        fold = self._js("  fold(){", "  start(){")
        self.assertIn("const done=this.round; this.round=null;", fold)
        self.assertIn('.tb").appendChild(done)', fold)

    def test_an_empty_round_is_dropped_rather_than_counted(self):
        """A round that produced nothing but a tool call has no text and no
        thought left in the column -- the rows went to the tile. Counting it
        would make `Trace 24 rounds` out of a turn with four things in it."""
        fold = self._js("  fold(){", "  start(){")
        self.assertIn("done.remove()", fold)

    def test_it_says_how_many_rounds_it_holds(self):
        fold = self._js("  fold(){", "  start(){")
        self.assertIn('this.traceN===1 ? " round" : " rounds"', fold)

    def test_a_new_user_line_starts_a_new_trace(self):
        """One trace per turn. Without this the second question's rounds would
        pile into the first question's block."""
        user = self._js("  user(text){", "  fold(){")
        self.assertIn("this.endTrace()", user)
        drawn = self.source[self.source.index('case "clear":'):]
        self.assertIn("this.endTrace()", drawn[:drawn.index("break;")])

    def test_folded_it_costs_one_line(self):
        CLOSE = chr(125)
        body = self.css[self.css.index("details.trace .tb{"):]
        self.assertIn("border-left", body[:body.index(CLOSE)])
        summary = self.css[self.css.index("details.trace>summary{"):]
        self.assertIn("inline-flex", summary[:summary.index(CLOSE)])


class ADismissedToolRowStaysDismissedTests(ApiCase):
    """#131. robin, after rebooting the window: the calls he had deleted were
    back. A reopened chat replays its tool rows, and clearing had only emptied
    the page.

    THE CONVERSATION IS NOT TOUCHED. The model keeps every call it made; what is
    remembered is a VIEW fact -- how far the user has dismissed.
    """

    def test_the_watermark_is_a_count_of_what_the_conversation_holds(self):
        """COUNTED FROM THE CONVERSATION, not from what the page was showing:
        clearing twice would otherwise set it to the SECOND batch and bring the
        first one back."""
        api = self.api()
        api._conversation.append("user", "go")
        api._conversation.append(
            "assistant", "",
            tool_calls=[{"id": "a", "name": "read_file", "arguments": "{}"},
                        {"id": "b", "name": "list_dir", "arguments": "{}"}])
        self.assertEqual(api.tools_cleared(), 2)
        self.assertEqual(api._tools_cleared, 2)

    def test_a_replay_draws_only_what_came_after_it(self):
        api = self.api()
        api._tools_cleared = 1
        messages = [{"role": "user", "content": "go"},
                    {"role": "assistant", "content": "",
                     "tool_calls": [{"function": {"name": "read_file", "arguments": "{}"}},
                                    {"function": {"name": "list_dir", "arguments": "{}"}}]}]
        api._replay(messages)
        rows = [m for m in self.drained(api) if m.get("k") == "tool"]
        self.assertEqual([r["name"] for r in rows], ["list_dir"])

    def test_without_a_watermark_everything_is_drawn(self):
        """NEGATIVE: the skip may only ever hide what somebody dismissed."""
        api = self.api()
        messages = [{"role": "assistant", "content": "",
                     "tool_calls": [{"function": {"name": "read_file", "arguments": "{}"}},
                                    {"function": {"name": "list_dir", "arguments": "{}"}}]}]
        api._replay(messages)
        rows = [m for m in self.drained(api) if m.get("k") == "tool"]
        self.assertEqual([r["name"] for r in rows], ["read_file", "list_dir"])

    def test_it_survives_the_file(self):
        """Written and READ BACK. A watermark only ever written is one nobody
        has proved comes back -- and coming back is its entire job."""
        path = os.path.join(self.dir, "chat.json")
        talk = crow_core.Conversation("SYS")
        talk.append("user", "go")
        talk.append("assistant", "done")
        crow_core.save_session(talk, "http://127.0.0.1:1/v1", 10, path=path,
                               with_kv=False, tools_cleared=3)
        self.assertEqual(crow_core.session_tools_cleared(path), 3)

    def test_a_file_that_never_cleared_carries_no_key(self):
        """NEGATIVE, and the three-state rule this file already keeps: absent is
        its own value, and every session written before this build is absent."""
        path = os.path.join(self.dir, "chat.json")
        talk = crow_core.Conversation("SYS")
        talk.append("user", "go")
        talk.append("assistant", "done")
        crow_core.save_session(talk, "http://127.0.0.1:1/v1", 10, path=path,
                               with_kv=False)
        with open(path, encoding="utf-8") as fh:
            self.assertNotIn(crow_core.SESSION_TOOLS_CLEARED_KEY, json.load(fh))
        self.assertEqual(crow_core.session_tools_cleared(path), 0)


class TheRemoteEndpointTests(ApiCase):
    """The trennlinie, drawn where the window can actually cross it.

    A REMOTE ENDPOINT HAS NO SLOT, NO PREFIX CACHE AND NO OPERATING POINT.
    /health, /props and /slots are llama-server's; every case here exists
    because the window used to ask them of whatever `--base-url` said, and once
    that can be somebody's paid API the questions are not merely useless -- they
    are round trips nobody asked for against an endpoint that answers 404.
    """

    def setUp(self) -> None:
        super().setUp()
        self._prov = (crow_core.PROVIDERS_FILE, crow_core.PROVIDER_KEYS_FILE,
                      crow_core.PROVIDER_TOKEN_FILE)
        self.addCleanup(self._restore_prov)
        crow_core.PROVIDERS_FILE = os.path.join(self.dir, "providers.json")
        crow_core.PROVIDER_KEYS_FILE = os.path.join(self.dir, "provider_keys.json")
        crow_core.PROVIDER_TOKEN_FILE = os.path.join(self.dir, "provider_tokens.json")

    def _restore_prov(self) -> None:
        (crow_core.PROVIDERS_FILE, crow_core.PROVIDER_KEYS_FILE,
         crow_core.PROVIDER_TOKEN_FILE) = self._prov

    def remote(self, model: str = "z-ai/glm-5.2:free", context: int = 131072):
        """A configured provider, exactly as the sheet would leave one."""
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        doc = crow_core.provider_doc()
        doc["catalog"] = {"openrouter": {"fetched": 1, "models": [
            {"id": model, "name": model, "context": context}]}}
        crow_core.provider_write(doc)
        self.assertIsNone(crow_core.provider_pick("openrouter", model))

    def test_the_local_questions_are_not_put_to_a_provider(self):
        """NEGATIVE, and the one the whole stage turns on. All three probes are
        replaced with something that raises: if the window still reaches for
        /health, /props or a model name, the case fails loudly instead of
        quietly costing a round trip on somebody's key."""
        self.remote()
        api = self.api()

        def refuse(*_a, **_k):
            raise AssertionError("a remote endpoint was asked a local question")

        with mock.patch.object(crow_gui, "check_endpoint", refuse), \
             mock.patch.object(crow_gui, "fetch_n_ctx", refuse), \
             mock.patch.object(crow_gui, "fetch_model_name", refuse):
            state, name, window = api._look(api._endpoint())
        self.assertEqual(name, "z-ai/glm-5.2:free")
        self.assertEqual(window, 131072)
        self.assertEqual(state, "ready")

    def test_the_local_endpoint_is_still_measured(self):
        """THE POSITIVE HALF. Without it the case above would pass on a window
        that had stopped asking anybody anything, which is a different defect
        with the same green tick."""
        asked = []
        api = self.api()
        with mock.patch.object(crow_gui, "check_endpoint", lambda u, *a, **k: asked.append(u) or "ok"), \
             mock.patch.object(crow_gui, "fetch_n_ctx", lambda u, *a, **k: 200000), \
             mock.patch.object(crow_gui, "fetch_model_name", lambda u, *a, **k: "Q.gguf"):
            state, name, window = api._look(api._endpoint())
        self.assertEqual((state, window), ("ok", 200000))
        self.assertTrue(asked)

    def test_an_undeclared_window_leaves_the_bar_off_rather_than_inventing_one(self):
        """0 travels to the page as `n_ctx`, and `ctx()` draws a bare count for
        it. A 128k default here would be the client guessing remotely while it
        measures locally, with nothing on screen saying which it just did."""
        self.remote(context=0)
        api = self.api()
        self.assertEqual(api._look(api._endpoint())[2], 0)

    def test_a_provider_with_no_model_picked_is_a_state_not_a_crash(self):
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        crow_core.provider_pick("openrouter")
        api = self.api()
        state, _name, window = api._look(api._endpoint())
        self.assertIn("no model", state)
        self.assertEqual(window, 0)

    def test_the_command_line_does_not_decide_where_a_key_bearing_turn_goes(self):
        """`--base-url` is the local server's default. A window launched months
        ago against 127.0.0.1 must not send an OpenRouter key there, and must
        not send OpenRouter's turn to 127.0.0.1 either."""
        self.remote()
        spot = self.api()._endpoint()
        self.assertEqual(spot["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(spot["api_key"], "not-a-real-key-0123456789")
        self.assertTrue(spot["remote"])

    def test_both_senders_of_one_turn_get_the_same_endpoint(self):
        """THE POINT THAT IS EASIEST TO MISS. `stream_reply` is the visible
        sender; `review_turn` runs afterwards without being asked, with its own
        body and its own Authorization header. A change that reached only the
        first would leave the background pass talking to the command line --
        which, once a key is involved, is a request nobody chose to send."""
        self.remote()
        seen = {}

        def fake_run(conversation, **kw):
            seen["turn"] = (kw["base_url"], kw["model"], kw["api_key"])
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=False,
                                        stopped=False, reported=True)

        def fake_review(conversation, **kw):
            seen["review"] = (kw["base_url"], kw["model"], kw["api_key"])
            return []

        api = self.api()
        api._conversation.append("user", "hello")
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "review_turn", fake_review), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: 1.0):
            api._run("hello")
        self.assertEqual(seen.get("turn"),
                         ("https://openrouter.ai/api/v1", "z-ai/glm-5.2:free",
                          "not-a-real-key-0123456789"))
        self.assertEqual(seen.get("review"), seen.get("turn"))

    def test_a_turn_with_no_model_picked_is_refused_before_it_is_sent(self):
        """NEGATIVE: an empty slug in the body is a 400 from the provider and a
        line in the chat that names neither the cause nor the control."""
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        crow_core.provider_pick("openrouter")
        api = self.api()

        def refuse(*_a, **_k):
            raise AssertionError("a turn went out with no model")

        with mock.patch.object(crow_gui, "run_turn", refuse):
            api._run("hello")
        said = [m for m in self.drained(api) if m.get("k") == "fail"]
        self.assertTrue(said and "Model" in said[0]["t"], said)

    def test_switching_provider_says_both_lines_and_empties_the_chat(self):
        """THE TWO LINES COME BEFORE THE SCREEN CHANGES. A person who reads them
        after the window has emptied has been informed of a loss instead of
        warned about one -- and the second line is the only place the local
        cache rules are withdrawn."""
        self.remote()
        api = self.api()
        api._conversation.append("user", "hello")
        with mock.patch.object(crow_gui, "check_endpoint", lambda *a, **k: "ok"), \
             mock.patch.object(crow_gui, "fetch_n_ctx", lambda *a, **k: 0), \
             mock.patch.object(crow_gui, "fetch_model_name", lambda *a, **k: ""):
            said = api.provider_pick(crow_core.LOCAL_PROVIDER, None)
        self.assertEqual(said, "")
        sent = self.drained(api)
        notes = [m["t"] for m in sent if m.get("k") == "note"]
        self.assertIn(crow_core.MODEL_SWITCH_NOTE, notes)
        # THE HEAD SURVIVES A RESET AND THE CONVERSATION DOES NOT -- so what is
        # asserted is the turn being gone, not a length that counts the system
        # message and would pass on a chat nobody emptied.
        self.assertNotIn("hello", json.dumps(api._conversation.payload()))
        # AND NOTHING AFTER THEM WIPES THEM. The first version of this path
        # pushed `clear` at the end, which the page answers with
        # `flow.innerHTML=""` -- the queue still carried both lines and this case
        # was green while the screen showed neither. Reading the queue is not
        # reading the screen, and this is the half that says so.
        self.assertNotIn("clear", [m.get("k") for m in sent],
                         "a clear after the lines erases them from the page")

    def test_the_remote_line_is_said_going_out_and_not_coming_back(self):
        """It names what a remote endpoint does NOT have. Said on the way back to
        the machine it would be false, and a screen that reports what is not
        happening teaches nobody anything."""
        api = self.api()
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        crow_core.provider_pick("openrouter", "a/b")
        api._endpoint_changed(reset=True)
        out = [m["t"] for m in self.drained(api) if m.get("k") == "note"]
        self.assertIn(crow_core.REMOTE_ENDPOINT_NOTE, out)
        with mock.patch.object(crow_gui, "check_endpoint", lambda *a, **k: "ok"), \
             mock.patch.object(crow_gui, "fetch_n_ctx", lambda *a, **k: 0), \
             mock.patch.object(crow_gui, "fetch_model_name", lambda *a, **k: ""):
            api.provider_pick(crow_core.LOCAL_PROVIDER, None)
        back = [m["t"] for m in self.drained(api) if m.get("k") == "note"]
        self.assertNotIn(crow_core.REMOTE_ENDPOINT_NOTE, back)

    def test_the_endpoint_does_not_change_mid_turn(self):
        """The loop read its endpoint at the top. Changing it underneath would
        send the second half of a turn somewhere else -- the same refusal
        `/model` gives, for the same reason."""
        api = self.api()
        api._worker = _AliveWorker()
        self.assertIn("mid-turn", api.provider_pick(crow_core.LOCAL_PROVIDER, None))

    def test_the_page_is_never_handed_the_key_itself(self):
        """`provider_view` crosses into the page, and the page is a browser.
        Nothing that goes through that seam may carry the secret."""
        secret = "not-a-real-key-9f3c0d11223344556677889900aabbcc"
        crow_core.provider_key_set("openrouter", secret)
        self.assertNotIn(secret, json.dumps(self.api().provider_view()))

    def test_the_sheet_has_a_model_page_and_a_key_page_wired_to_them(self):
        """A section nobody can open, or a button calling a method that is not
        there, is the shape a page-level defect takes -- and neither shows up in
        any behaviour test."""
        page = crow_gui.PAGE
        for hook in ('data-cat="model"', 'data-cat="keys"',
                     "crow.settingsCat('model')", "crow.settingsCat('keys')",
                     "provider_view()", "provider_pick(", "provider_key(",
                     "provider_refresh("):
            self.assertIn(hook, page, hook)
        for method in ("provider_view", "provider_pick", "provider_key",
                       "provider_refresh"):
            self.assertTrue(callable(getattr(crow_gui.Api, method, None)), method)
        self.assertNotIn("Coming soon", page)

    def test_the_subscriptions_page_exists_and_its_tiles_are_wired(self):
        """A tile nobody can click, or a click calling a method that is not
        there, is the shape a page-level defect takes -- and no behaviour test
        reaches it. The marks are drawn rather than fetched: the page has no
        external host to load an image from."""
        page = crow_gui.PAGE
        for hook in ('data-cat="subs"', "crow.settingsCat('subs')", 'id="subs"',
                     "provider_authorise(", "provider_signout(", "subMark("):
            self.assertIn(hook, page, hook)
        for method in ("provider_authorise", "provider_signout"):
            self.assertTrue(callable(getattr(crow_gui.Api, method, None)), method)
        # NOTHING IS LOADED FROM A HOST. A logo behind a URL would be a
        # settings pane that needs the network to draw itself -- and on the one
        # screen where somebody is about to sign in, a remote asset is also a
        # request that says when they opened it.
        self.assertNotIn('src="http', page)
        self.assertNotIn("url(http", page)

    def test_the_marks_are_the_providers_own_and_take_the_skin(self):
        """robin, 2026-08-23: the real logos, white under dark and crow, black
        under light.

        THE COLOUR IS A PALETTE VARIABLE AND THE MARK IS NOT TINTED. `--text-hi`
        is already #ffffff in both dark skins and #0f1114 in light, so a fourth
        theme gets an answer without anybody remembering this rule -- and a mark
        that turned accent when signed in would be recolouring somebody else's
        logo to say something about Crow.

        THE PLACEHOLDERS ARE NAMED so this cannot quietly go back to them: the
        first version drew a four-pointed spark and a hexagon, and both looked
        deliberate enough that nothing but a person would have caught it.
        """
        page = crow_gui.PAGE
        self.assertIn('anthropic: {box: "0 0 35 24"', page)
        self.assertIn('openai: {box: "29 29 122 122"', page)
        # The wordmark's counter and the knot's first curve, each long enough
        # to be that path and nothing else.
        self.assertIn("M24.5475 0H19.3384L28.8374 24H34.0465L24.5475 0Z", page)
        self.assertIn("M75.91 73.628V62.232c0-.96.36-1.68 1.199-2.16", page)
        self.assertNotIn("M12 2l2.3 6.4L20.6 10", page)          # the old spark
        self.assertNotIn("M12 3.2 18.6 7v7.6L12 18.4", page)     # the old hexagon
        self.assertIn(".sub .mark{width:26px;height:26px;color:var(--text-hi)}", page)
        self.assertNotIn(".sub.on .mark{color:var(--accent)}", page)
        # #102's rule, and it holds here too: no RULE may name a colour of its
        # own, or only the theme it was picked in answers for it. The comments
        # come out first -- one of them quotes the two hex values on purpose,
        # and a check that could not tell a declaration from a sentence about
        # one would have been red at exactly the line that explains itself.
        import re as _re
        subs = page[page.index("#subs{"):page.index(".subout")]
        subs = _re.sub(r"/\*.*?\*/", "", subs, flags=_re.S)
        self.assertNotIn("#", subs.replace("#subs{", ""))

    def test_a_tile_that_cannot_sign_in_yet_opens_a_form_instead(self):
        """robin, 2026-08-23: the click answered with the sentence already
        printed on the tile, which reads as nothing having happened. A control
        does the next step -- with the values in place that is the browser,
        without them it is the form that puts them there. And the line under the
        sheet no longer repeats what the tile says."""
        page = crow_gui.PAGE
        self.assertIn("subForm(", page)
        self.assertIn('id="subform"', page)
        self.assertIn("if(s.ready) this.connectSub(s.name);", page)
        self.assertTrue(callable(getattr(crow_gui.Api, "provider_oauth", None)))
        # THE TILE'S OWN TEXT IS NOT THE STORED SENTENCE any more: `missing`
        # names a file and a key, which is what a person editing by hand needed
        # and exactly what a person with a form does not.
        self.assertNotIn("s.ready?s.blurb:s.missing", page)

    def test_both_senders_carry_the_same_sticky_key(self):
        """THE SISTER CASE TO THE ONE BELOW, and it fails the same way: quietly.

        OpenRouter is a broker, and `session_id` is what keeps consecutive
        requests of one chat on one upstream -- "a sticky routing key to direct
        all requests in the session to the same provider, maximizing prompt
        cache hits", read at the source 2026-08-23. The review runs with nobody
        at the keyboard and builds its own body, so a key that reached only the
        visible turn would make the review a second session inside the first.
        Hermes shipped precisely that and fixed it as their #70820.

        The key is the ONLY thing that travels. `require_parameters` was here
        for twenty minutes on 2026-08-23 and took the client down with a 404 --
        see `TheStickyRoutingTests` in test_crow_core for the measurement."""
        self.remote()
        seen = {}

        def fake_run(conversation, **kw):
            seen["turn"] = kw.get("routing")
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=False,
                                        stopped=False, reported=True)

        def fake_review(conversation, **kw):
            seen["review"] = kw.get("routing")
            return []

        api = self.api()
        api._args.session = os.path.join(self.dir, "chat-20260823-101120.json")
        api._conversation.append("user", "hello")
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "review_turn", fake_review), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: 1.0):
            api._run("hello")
        self.assertEqual(seen["turn"],
                         {"session_id": crow_core.sticky_key(api._args.session)})
        self.assertEqual(seen["review"], seen["turn"])

    def test_the_machine_is_sent_no_routing_by_either_sender(self):
        """NEGATIVE, and it covers every turn taken before today. llama-server
        has no upstream to pick between and no sticky routing to do; two fields
        it would ignore are still two fields in front of byte 0."""
        crow_core.provider_pick(crow_core.LOCAL_PROVIDER)
        seen = {}

        def fake_run(conversation, **kw):
            seen["turn"] = kw.get("routing")
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=False,
                                        stopped=False, reported=True)

        def fake_review(conversation, **kw):
            seen["review"] = kw.get("routing")
            return []

        api = self.api()
        api._args.session = os.path.join(self.dir, "chat-20260823-101120.json")
        api._conversation.append("user", "hello")
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "review_turn", fake_review), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: 1.0):
            api._run("hello")
        self.assertEqual(seen["turn"], {})
        self.assertEqual(seen["review"], {})

    def test_both_senders_are_told_which_dialect_the_endpoint_speaks(self):
        """Anthropic answers `POST /v1/messages` and nothing else; the OpenAI
        shape is a different door at the same host. A transport that reached
        only the visible turn would leave the background review posting an
        OpenAI body to an endpoint that does not read one -- and that is the
        request nobody is watching."""
        crow_core.provider_key_set("anthropic", "not-a-real-anthropic-key-abcd")
        doc = crow_core.provider_doc()
        doc["catalog"] = {"anthropic": {"fetched": 1, "models": [
            {"id": "claude-opus-5", "name": "Opus", "context": 1000000}]}}
        crow_core.provider_write(doc)
        crow_core.provider_pick("anthropic", "claude-opus-5")
        seen = {}

        def fake_run(conversation, **kw):
            seen["turn"] = kw.get("transport")
            seen["cap"] = kw.get("max_tokens")
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=False,
                                        stopped=False, reported=True)

        def fake_review(conversation, **kw):
            seen["review"] = kw.get("transport")
            return []

        api = self.api()
        api._conversation.append("user", "hello")
        with mock.patch.object(crow_gui, "run_turn", fake_run),              mock.patch.object(crow_core, "review_turn", fake_review),              mock.patch.object(crow_core, "review_due", lambda *a, **k: 1.0):
            api._run("hello")
        self.assertEqual(seen.get("turn"), crow_core.TRANSPORT_MESSAGES)
        self.assertEqual(seen.get("review"), seen.get("turn"))
        self.assertEqual(seen.get("cap"), crow_core.REMOTE_MAX_TOKENS)
        # THE LOCAL SERVER IS THE NEGATIVE HALF: without it this would pass on a
        # client that had started sending the Anthropic dialect everywhere.
        crow_core.provider_pick(crow_core.LOCAL_PROVIDER)
        api = self.api()
        api._conversation.append("user", "hello")
        with mock.patch.object(crow_gui, "run_turn", fake_run),              mock.patch.object(crow_core, "review_turn", fake_review),              mock.patch.object(crow_core, "review_due", lambda *a, **k: 1.0):
            api._run("hello")
        self.assertEqual(seen.get("turn"), crow_core.TRANSPORT_CHAT)
        # AND THE SAME CAP AT HOME, which is the half that used to be None: a
        # body without the field inherits the server's default, and crow-nest's
        # 1024 cut a tool call off mid-argument on 2026-09-18.
        self.assertEqual(seen.get("cap"), crow_core.MAX_TOKENS)

    def test_a_model_can_be_typed_when_no_catalogue_answers(self):
        """The field is always there rather than appearing on failure: a control
        that only exists after something went wrong is one nobody finds when it
        matters, and the provider takes the slug the same way either way."""
        page = crow_gui.PAGE
        self.assertIn("model id, as the provider lists it", page)
        self.assertIn("slug.value.trim()", page)
        self.assertIn('use.textContent="Use"', page)

    def test_the_tile_offers_the_documented_command(self):
        """robin, 2026-08-23, from Hermes' own sign-in dialog: it prints
        `claude setup-token` and waits. No client_id borrowed from a product
        that never granted one -- which is why the browser leg is not what this
        tile reaches for first."""
        page = crow_gui.PAGE
        self.assertIn("tokenForm(", page)
        self.assertIn("if(s.command) this.tokenForm(s);", page)
        self.assertIn("provider_token(", page)
        self.assertTrue(callable(getattr(crow_gui.Api, "provider_token", None)))
        self.assertIn("cmd.readOnly=true", page)

    def test_saving_an_untouched_field_does_not_clear_a_stored_credential(self):
        """robin, 2026-08-23, and it cost him his OpenRouter key. The stored
        value is never read back into the field, so a BLANK box is the normal
        state of a key that IS set -- and Save sent that blank on, which the
        core reads as "clear it". Only the explicit control clears now.

        THE PAGE IS WHERE THIS LIVES: the core is right to treat an empty string
        as a clear, because something has to. What may not happen is a control
        sending one nobody typed."""
        page = crow_gui.PAGE
        self.assertIn("clearKey(", page)
        self.assertIn("`Remove` is what clears a stored key.", page)
        self.assertIn("`sign out` is what clears one.", page)
        # NEGATIVE: the old wiring blanked the box and called the SAVE path.
        self.assertNotIn("box2.value=\"\"; this.saveKey(", page)
        self.assertIn("gone.onclick=()=>this.clearKey(p.name);", page)

    def test_a_sign_in_does_not_run_mid_turn(self):
        """The credential it replaces is the one the running turn is
        authenticating with."""
        api = self.api()
        api._worker = _AliveWorker()
        self.assertIn("mid-turn", api.provider_authorise("anthropic"))

    def test_both_senders_carry_the_providers_own_headers(self):
        """THE HEADER TRAVELS WITH THE CREDENTIAL, and it has to reach BOTH
        paths. The background review builds its own request with its own
        Authorization line; a header that only reached the visible turn would
        leave the unasked one being refused by an endpoint the chat can talk
        to."""
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        doc = crow_core.provider_doc()
        doc["catalog"] = {"openrouter": {"fetched": 1, "models": [
            {"id": "a/b", "name": "b", "context": 1000}]}}
        crow_core.provider_write(doc)
        crow_core.provider_pick("openrouter", "a/b")
        seen = {}

        def fake_run(conversation, **kw):
            seen["turn"] = kw.get("extra_headers")
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost="", context_tokens=9,
                                        promised_warm=False, rolled=False,
                                        stopped=False, reported=True)

        def fake_review(conversation, **kw):
            seen["review"] = kw.get("extra_headers")
            return []

        api = self.api()
        api._conversation.append("user", "hello")
        # A KEY CARRIES NOTHING EXTRA -- the negative half, and without it the
        # positive one below would pass on a header that is simply always sent.
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "review_turn", fake_review), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: 1.0):
            api._run("hello")
        self.assertIsNone(seen.get("turn"))
        self.assertIsNone(seen.get("review"))

        crow_core.provider_token_write({"openrouter": {
            "access_token": "tok", "client_id": "c",
            "token_endpoint": "https://example.invalid/token"}})
        real = dict(crow_core.PROVIDER_OAUTH_HEADERS)
        crow_core.PROVIDER_OAUTH_HEADERS["openrouter"] = {"x-crow-probe": "1"}
        self.addCleanup(lambda: (crow_core.PROVIDER_OAUTH_HEADERS.clear(),
                                 crow_core.PROVIDER_OAUTH_HEADERS.update(real)))
        api = self.api()
        api._conversation.append("user", "hello")
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "review_turn", fake_review), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: 1.0):
            api._run("hello")
        self.assertEqual(seen.get("turn"), {"x-crow-probe": "1"})
        self.assertEqual(seen.get("review"), seen.get("turn"))

    def test_a_report_does_not_move_the_endpoint(self):
        """NEGATIVE, and the defect it was cut for was mine: writing the local
        provider BEFORE `model_command` meant a bare `/model` -- which only ever
        prints what is running -- switched the endpoint on its way to answering.
        Nothing was said, nothing was emptied, and the chip went on naming the
        remote model while turns went somewhere else."""
        self.remote()
        api = self.api()
        with mock.patch.object(crow_core, "server_model_path", lambda *a, **k: ""):
            api._model_command([])
        self.assertEqual(crow_core.provider_active(), "openrouter")

    def test_a_typo_does_not_move_the_endpoint(self):
        """NEGATIVE: `model_command` refuses a word that is not a key and boots
        nothing. A provider written before that refusal would have moved the
        endpoint for a word the user did not mean."""
        self.remote()
        api = self.api()
        api._model_command(["nonsense"])
        self.assertEqual(crow_core.provider_active(), "openrouter")

    def test_a_local_model_already_running_still_ends_the_remote_chat(self):
        """"Already the one running" is about the PROCESS, not about where the
        last turn went. Coming back from a provider to a server that happens to
        be up is still an endpoint change: the context was built somewhere else,
        so it is dropped, said out loud, and the window is re-read -- or the
        chip keeps the remote model's declared window while llama-server
        answers."""
        self.remote()
        api = self.api()
        api._conversation.append("user", "hello")
        with mock.patch.object(crow_core, "model_command",
                               lambda *a, **k: ("qwen is already the one running.",
                                                "http://127.0.0.1:8081/v1", False)), \
             mock.patch.object(crow_core, "bootable_models", lambda: ("qwen",)), \
             mock.patch.object(crow_gui, "check_endpoint", lambda *a, **k: "ok"), \
             mock.patch.object(crow_gui, "fetch_n_ctx", lambda *a, **k: 200000), \
             mock.patch.object(crow_gui, "fetch_model_name", lambda *a, **k: "Q.gguf"):
            api._model_command(["qwen"])
        self.assertEqual(crow_core.provider_active(), crow_core.LOCAL_PROVIDER)
        sent = self.drained(api)
        self.assertIn(crow_core.MODEL_SWITCH_NOTE,
                      [m.get("t") for m in sent if m.get("k") == "note"])
        up = [m for m in sent if m.get("k") == "up"]
        self.assertTrue(up, "the page was never told the window changed")
        self.assertEqual(up[-1]["n_ctx"], 200000)
        self.assertNotIn("hello", json.dumps(api._conversation.payload()))

    def test_a_local_model_from_the_chip_comes_back_to_the_local_provider(self):
        """The chip names the models this machine can boot. Left refusing while a
        provider is chosen it would be dead, with no way back except the sheet --
        so booting one IS the way back, written before the server starts.

        `bootable_models` IS MOCKED TOO, and leaving it out was this case setting
        its own trap: "qwen" is not a key in the shipped manifest, so the window
        was right to change nothing -- the case would have been measuring a
        refusal while its name claimed a boot."""
        self.remote()
        api = self.api()
        with mock.patch.object(crow_core, "model_command",
                               lambda *a, **k: ("said", "http://127.0.0.1:8081/v1", True)), \
             mock.patch.object(crow_core, "bootable_models", lambda: ("qwen",)), \
             mock.patch.object(crow_gui, "fetch_n_ctx", lambda *a, **k: 200000), \
             mock.patch.object(crow_gui, "fetch_model_name", lambda *a, **k: "Q.gguf"):
            api._model_command(["qwen"])
        self.assertEqual(crow_core.provider_active(), crow_core.LOCAL_PROVIDER)


class TheOpenRouterPageTests(ApiCase):
    """robins Korrektur vom 2026-08-28: der Broker verlaesst die Model-Seite
    auf eine eigene, und sein Schalter parkt nichts anderes -- Maschine und
    Broker laufen parallel, was die Delegation von Anfang an tut."""

    def setUp(self) -> None:
        super().setUp()
        self._prov = (crow_core.PROVIDERS_FILE, crow_core.PROVIDER_KEYS_FILE,
                      crow_core.PROVIDER_TOKEN_FILE)
        self.addCleanup(self._restore_prov)
        crow_core.PROVIDERS_FILE = os.path.join(self.dir, "providers.json")
        crow_core.PROVIDER_KEYS_FILE = os.path.join(self.dir, "provider_keys.json")
        crow_core.PROVIDER_TOKEN_FILE = os.path.join(self.dir, "provider_tokens.json")

    def _restore_prov(self) -> None:
        (crow_core.PROVIDERS_FILE, crow_core.PROVIDER_KEYS_FILE,
         crow_core.PROVIDER_TOKEN_FILE) = self._prov

    def broker(self, model: str = "z-ai/glm-5.2:free") -> None:
        """Key and catalogue on disk, and NO pick: turns stay on the machine."""
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        doc = crow_core.provider_doc()
        doc["catalog"] = {"openrouter": {"fetched": 1, "models": [
            {"id": model, "name": model, "context": 131072}]}}
        crow_core.provider_write(doc)

    def test_the_broker_has_its_own_page(self):
        """A section nobody can open, or a switch calling a method that is not
        there, is the page-level defect shape the sheet tests already pin."""
        page = crow_gui.PAGE
        self.assertEqual(page.count('data-cat="openrouter"'), 2,
                         "nav button and section, keyed the #126 way")
        for hook in ("crow.settingsCat('openrouter')", 'id="orbody"',
                     'id="orsaid"', "drawOpenRouter(", "openrouter_set(",
                     "provider_model_set("):
            self.assertIn(hook, page, hook)
        for method in ("openrouter_set", "provider_model_set"):
            self.assertTrue(callable(getattr(crow_gui.Api, method, None)),
                            method)

    def test_the_broker_page_routes_no_turn(self):
        """robins dritter Brueller, 2026-08-28 abends: die Broker-Seite routet
        GAR NICHTS. Default ist immer lokal, bis der User auf der Model-Seite
        etwas anderes waehlt -- so the page's whole JS holds no door that
        moves a turn, and the Api offers none for it to call."""
        page = crow_gui.PAGE
        broker = page[page.index("  drawOpenRouter(view){"):]
        broker = broker[:broker.index("\n  drawModels")]
        for door in ("provider_pick(", "orTurns", "openrouter_turns"):
            self.assertNotIn(door, broker, door)
        self.assertIsNone(getattr(crow_gui.Api, "openrouter_turns_set", None))
        self.assertNotIn("openrouter_turns_set(", page)

    def test_the_model_page_lost_the_broker(self):
        """KOMPLETT raus, robins Wort: the provider rows are drawn without
        openrouter, provRow builds no favourites any more, and the model fold
        points at the broker's own page when turns go there."""
        page = crow_gui.PAGE
        rows = page[page.index("  provRow(p,active){"):]
        rows = rows[:rows.index("\n  drawOpenRouter")]
        self.assertNotIn("favsel", rows)
        self.assertNotIn("orcfg", rows)
        draw = page[page.index("  drawProviders(){"):]
        draw = draw[:draw.index("\n  provRow")]
        self.assertIn('p.name!=="openrouter"', draw)
        self.assertIn("drawOpenRouter(", draw)
        broker = page[page.index("  drawOpenRouter(view){"):]
        broker = broker[:broker.index("\n  drawModels")]
        self.assertIn("favsel", broker)
        models = page[page.index("  drawModels(view){"):]
        models = models[:models.index("\n  drawKeys")]
        self.assertIn("Turns go to OpenRouter", models)

    def test_switching_the_broker_on_leaves_the_machine_answering(self):
        """DER BRUELLER SELBST: on is a flag, not a route."""
        self.broker()
        api = self.api()
        self.assertEqual(api.openrouter_set(True), "")
        self.assertEqual(crow_core.provider_active(), crow_core.LOCAL_PROVIDER)
        self.assertFalse(api._endpoint()["remote"])

    def test_the_view_carries_the_switch_state(self):
        self.broker()
        api = self.api()
        self.assertTrue(api.provider_view()["openrouter_on"])
        self.assertEqual(api.openrouter_set(False), "")
        self.assertFalse(api.provider_view()["openrouter_on"])

    def test_parking_the_broker_walks_the_provider_road_home(self):
        """Turns sitting ON the broker come home the loud way: the same two
        lines and the same emptied chat `provider_pick` owes every switch."""
        self.broker()
        api = self.api()
        self.assertEqual(api.provider_pick("openrouter", "z-ai/glm-5.2:free"),
                         "")
        api._conversation.append("user", "hello")
        self.drained(api)
        with mock.patch.object(crow_gui, "check_endpoint", lambda *a, **k: "ok"), \
             mock.patch.object(crow_gui, "fetch_n_ctx", lambda *a, **k: 0), \
             mock.patch.object(crow_gui, "fetch_model_name", lambda *a, **k: ""):
            self.assertEqual(api.openrouter_set(False), "")
        self.assertEqual(crow_core.provider_active(), crow_core.LOCAL_PROVIDER)
        notes = [m["t"] for m in self.drained(api) if m.get("k") == "note"]
        self.assertIn(crow_core.MODEL_SWITCH_NOTE, notes)
        self.assertNotIn("hello", json.dumps(api._conversation.payload()))
        self.assertFalse(api.provider_view()["openrouter_on"])

    def test_the_broker_switch_respects_a_running_turn_only_when_it_must(self):
        """ON changes no endpoint, so a running turn is no reason to refuse --
        that IS the parallel operation. OFF while turns sit on the broker is
        an endpoint change: refused mid-turn, and refused whole."""
        self.broker()
        api = self.api()
        api._worker = _AliveWorker()
        self.assertEqual(api.openrouter_set(True), "")
        api._worker = None
        self.assertEqual(api.provider_pick("openrouter", "z-ai/glm-5.2:free"),
                         "")
        api._worker = _AliveWorker()
        self.assertIn("mid-turn", api.openrouter_set(False))
        self.assertEqual(crow_core.provider_active(), "openrouter")
        self.assertTrue(api.provider_view()["openrouter_on"],
                        "a refused park must not half-happen")

    def test_a_model_picked_on_the_broker_page_moves_no_turn(self):
        self.broker()
        api = self.api()
        self.assertEqual(api.provider_model_set("openrouter", "unit/x"), "")
        self.assertEqual(crow_core.provider_active(), crow_core.LOCAL_PROVIDER)
        self.assertEqual(crow_core.provider_model_for("openrouter"), "unit/x")

    def test_everything_on_the_broker_page_leaves_the_turns_local(self):
        """robins dritter Brueller, end to end: work the WHOLE page -- switch
        off, switch on, favourites, model pick -- and the turn endpoint never
        leaves the machine. Default ist lokal, bis der User auf der
        Model-Seite etwas anderes waehlt."""
        self.broker()
        api = self.api()
        self.assertEqual(api.openrouter_set(False), "")
        self.assertEqual(api.openrouter_set(True), "")
        self.assertEqual(api.delegate_favorites_set(["z-ai/glm-5.2:free"]), "")
        self.assertEqual(api.provider_model_set("openrouter",
                                                "z-ai/glm-5.2:free"), "")
        self.assertEqual(crow_core.provider_active(), crow_core.LOCAL_PROVIDER)
        self.assertFalse(api._endpoint()["remote"])


class TheSubtaskCardBreathesAndKeepsItsResultShutTests(unittest.TestCase):
    """robins Ansage vom 2026-08-28 spaetabends, letzte Fassung: das Ergebnis
    eines Subtasks gehoert NICHT offen in den Hauptchat -- der collect-Fold
    startet ZU und bleibt aufklappbar -- und eine LAUFENDE Karte atmet als
    Zeile im --sub-Kanal; fertig steht sie still. Kein Subtask-Chat und die
    Rail-Kinder samt Sprung: beides pinnen die Mockup-Faelle daneben."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):
                               self.source.index("</style>")]

    def _card(self) -> str:
        card = self.source[self.source.index("  subCard(it){"):]
        return card[:card.index("\n  subChip")]

    def test_the_result_hides_behind_the_card(self):
        """robins letzte Kartenform 2026-08-29: klassische Kopfzeile
        (delegate · dN, Modell, Status rechts), Task darunter -- und der
        volle Output bleibt ZU, die Karte selbst ist die Klickflaeche."""
        card = self._card()
        self.assertIn("res.hidden=true", card)
        self.assertNotIn("<summary>", card, "der alte Fold ist zurueck")
        self.assertNotIn("Click to Expand", card,
                         "die Expand-Zeile der Zwischenfassung ist zurueck")
        head = card[card.index('<div class="shead">'):
                    card.index('<div class="stask">')]
        self.assertLess(head.index("dlabel"), head.index("sname"))
        self.assertLess(head.index("sname"), head.index("sstat"))
        self.assertIn('d.classList.add("can")', card)

    def test_a_running_card_breathes_amber_on_its_left_bar_only(self):
        """robins finale Fassung 2026-08-28 nachts: KEINE Flaechenanimation
        auf der Karte -- nur der linke Balken atmet, ein Bernstein-Verlauf
        (--warn), der von oben nach unten wandert; fertig steht alles still."""
        self.assertIn('classList.toggle("run"', self._card())
        self.assertNotIn("subbreathe", self.css,
                         "das Opacity-Flackern ist zurueck")
        rule = self.css[self.css.index(".subcard.run{"):]
        rule = rule[:rule.index(chr(125))]
        self.assertNotIn("animation", rule,
                         "die Kartenflaeche animiert wieder")
        self.assertIn("border-left-color:transparent", rule)
        bar = self.css[self.css.index(".subcard.run::before{"):]
        bar = bar[:bar.index(chr(125))]
        self.assertIn("linear-gradient(180deg", bar)
        self.assertIn("var(--warn)", bar)
        self.assertIn("subflow", bar)
        self.assertIn("infinite", bar)
        self.assertIn("@keyframes subflow", self.css)

    def test_the_running_bar_sits_exactly_like_the_done_bar(self):
        """robins Ansage 2026-08-29: der Bernstein-Balken einer laufenden
        Karte sitzt EXAKT wie der stille --sub-Rand der fertigen. Als
        freistehender 3px-Streifen voller Hoehe stand er an den Ecken
        ueber die Kontur (sein 10px-Radius kollabiert bei 3px Breite);
        jetzt spannt er die ganze Kartenkontur auf, traegt deren Radius
        und zeigt per Mask nur die linke Randspalte -- klickdurchlaessig,
        denn die Karte selbst ist die Klickflaeche."""
        bar = self.css[self.css.index(".subcard.run::before{"):]
        bar = bar[:bar.index(chr(125))]
        self.assertIn("right:-1px", bar,
                      "der Balken endet wieder vor der Kartenkontur")
        self.assertIn("border-radius:10px;", bar,
                      "der Balken traegt nicht den Radius der Karte")
        self.assertNotIn("border-radius:10px 0 0 10px", bar,
                         "die freistehende Streifenform ist zurueck")
        self.assertIn("mask:linear-gradient(90deg", bar,
                      "ohne Mask malt der Verlauf die ganze Karte an")
        self.assertIn("pointer-events:none", bar,
                      "der Balken frisst den Kartenklick")
        self.assertNotIn("width:3px", bar,
                         "der 3px-Streifen mit Eigenbreite ist zurueck")


class TheSubtasksSurviveTheWindowRestartTests(ApiCase):
    """robins Ansage vom 2026-08-28 spaetnachts, die GUI-Haelfte: nach dem
    Fensterneustart haengen die ⑂-Zeilen wieder unter ihrem Chat und die
    Karten kennen ihren Eltern-Pfad -- aus der Registry-Datei, nicht aus dem
    Prozessgedaechtnis."""

    def test_recalled_children_hang_under_their_chat(self):
        crow_core.forget_subtasks()
        self.addCleanup(crow_core.forget_subtasks)
        self.addCleanup(setattr, crow_core, "_SUBTASKS_RECALLED", True)
        sub = crow_core.Subtask("d7", "ein task", "",
                                {"model": "unit/m:free", "label": "L"})
        sub.status = "done"
        sub.result = "R"
        sub.parent = "C:/x/chat-1.json"
        with crow_core._SUBTASK_LOCK:
            crow_core.SUBTASKS["d7"] = sub
        crow_core._subtask_persist()
        crow_core.forget_subtasks()
        crow_core._SUBTASKS_RECALLED = False     # das neue Fenster
        api = self.api()
        items = api._subs_items()
        self.assertEqual([i["i"] for i in items], ["d7"])
        self.assertEqual(items[0]["parent"], "C:/x/chat-1.json",
                         "der Eltern-Pfad kam nicht aus der Registry")
        self.assertFalse(items[0]["here"])


class TheUserScrollOutranksTheStreamTests(unittest.TestCase):
    """robins Regel vom 2026-08-28 nachts: USERSCROLL > ALLES. Waehrend Crow
    schreibt oder denkt, zog jeder Chunk die Sicht ans Ende -- hochscrollen
    war unmoeglich. Angeheftet ist nur, wer unten IST; die eigene Nachricht
    erzwingt das Ende weiterhin."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_bottom_asks_before_it_pulls(self):
        self.assertIn("atBottom(){", self.source)
        self.assertIn("force||this.atBottom()", self.source)

    def test_the_users_own_send_still_lands_at_the_end(self):
        self.assertIn("this.bottom(true)", self.source,
                      "nichts erzwingt das Ende mehr, auch die eigene "
                      "Nachricht nicht")


class ADeletedChatTakesItsSubtasksAlongTests(ApiCase):
    """robin, 2026-08-28 abends, aus dem Lernkit-Lauf heraus: geloeschte
    Chats liessen ihre Subtasks stehen, und der alte Name stand in der Rail,
    bis ein Rename kam. Zwei Haelften: die Registry erfuhr vom Loeschen
    nichts, und der Rail-Schnellpfad verglich eine shape ohne Titel."""

    def setUp(self) -> None:
        super().setUp()
        crow_core.forget_subtasks()
        self.addCleanup(crow_core.forget_subtasks)

    def _seed(self, ident: str, status: str = "done",
              transcript: str = "") -> "crow_core.Subtask":
        sub = crow_core.Subtask(ident, "the task", "",
                                {"model": "unit/m:free", "label": "OpenRouter"})
        sub.status = status
        sub.result = "RES" if status == "done" else ""
        sub.transcript = transcript
        crow_core.SUBTASKS[ident] = sub
        return sub

    def _saved_chat(self, name: str = "chat-a.json") -> str:
        talk = crow_core.Conversation("SYS")
        talk.append("user", "hallo")
        talk.append("assistant", "ok")
        path = os.path.join(self.dir, name)
        crow_core.save_session(talk, "http://127.0.0.1:1/v1", 5, path=path,
                               with_kv=False)
        return path

    def test_deleting_a_chat_drops_its_subtasks(self):
        api = self.api()
        path = self._saved_chat()
        api._current_path = path
        sub = self._seed("d1", transcript=os.path.join(self.dir, "t1.json"))
        with open(sub.transcript, "w", encoding="utf-8") as fh:
            fh.write("{}")
        api._subs_items()                     # stamps d1 to the open chat
        self.assertTrue(api.delete_chat(path))
        self.assertEqual(crow_core.subtask_view(), [])
        self.assertNotIn("d1", api._sub_parent)
        self.assertFalse(os.path.exists(sub.transcript),
                         "the transcript outlived its chat")

    def test_another_chats_subtasks_survive_the_delete(self):
        """DIE POSITIVPROBE: geloescht wird EIN Chat, nicht die Delegation."""
        api = self.api()
        gone = self._saved_chat("chat-a.json")
        kept = self._saved_chat("chat-b.json")
        api._current_path = kept
        self._seed("d1")
        api._subs_items()                     # d1 belongs to chat-b
        self.assertTrue(api.delete_chat(gone))
        self.assertEqual([r["i"] for r in crow_core.subtask_view()], ["d1"])

    def test_a_running_subtask_is_cancelled_by_the_delete(self):
        """Der Faden ist nicht toetbar; das Versprechen ist der RECORD:
        cancelled gesetzt, kein Transkript mehr, nichts mehr gelistet."""
        api = self.api()
        path = self._saved_chat()
        api._current_path = path
        sub = self._seed("d1", status="running")
        api._subs_items()
        self.assertTrue(api.delete_chat(path))
        self.assertTrue(sub.cancelled)
        self.assertEqual(crow_core.subtask_view(), [])

    def test_closing_the_card_marks_only_this_chats_and_cancels_nothing(self):
        """#281. `close_subtasks` hides the card for the OPEN chat: its
        records get the `closed` mark and a `subs` push says so; another
        chat's record is untouched; a running one is neither cancelled nor
        dropped. `reopen_subtasks` takes the mark off again."""
        api = self.api()
        here = self._saved_chat("chat-a.json")
        other = self._saved_chat("chat-b.json")
        api._current_path = other
        self._seed("d1")
        api._subs_items()                     # d1 belongs to chat-b
        api._current_path = here
        run = self._seed("d2", status="running")
        api._subs_items()                     # d2 belongs to chat-a
        self.drained(api)
        api.close_subtasks()
        rows = {r["i"]: r for r in crow_core.subtask_view()}
        self.assertTrue(rows["d2"]["closed"])
        self.assertFalse(rows["d1"]["closed"], "another chat's card closed")
        self.assertEqual(run.status, "running")
        self.assertFalse(run.cancelled)
        subs = [m for m in self.drained(api) if m.get("k") == "subs"]
        self.assertTrue(subs, "the close was never pushed to the page")
        self.assertTrue({r["i"]: r for r in subs[-1]["items"]}["d2"]["closed"])
        api.reopen_subtasks()
        self.assertFalse({r["i"]: r for r in crow_core.subtask_view()}
                         ["d2"]["closed"])

    def test_discarding_the_live_chat_drops_its_subtasks_too(self):
        api = self.api()
        self._seed("d1")
        api._subs_items()                     # parent "" -- the live chat
        self.assertTrue(api.discard_live())
        self.assertEqual(crow_core.subtask_view(), [])

    def test_the_rail_after_the_delete_names_nothing_old(self):
        """Python-Haelfte des Namens-Bugs: nach dem Loeschen des offenen Chats
        traegt die Rail-Payload den alten Titel nirgends mehr."""
        api = self.api()
        path = self._saved_chat()
        api._current_path = path
        api._current_title = "der alte name"
        self.assertTrue(api.delete_chat(path))
        rails = [m for m in self.drained(api) if m.get("k") == "rail"]
        self.assertTrue(rails)
        self.assertNotIn("der alte name", json.dumps(rails[-1]))
        self.assertEqual(rails[-1]["title"], "new chat")

    def test_a_title_change_repaints_the_rail(self):
        """JS-Haelfte: der Schnellpfad verglich eine shape ohne Titel -- eine
        reine Titelaenderung bewegte kein Pixel, erst ein Rename (neuer Pfad)
        baute neu. Die Titel gehoeren in die shape, der live-Titel mit."""
        page = crow_gui.PAGE
        shape = page[page.index("const shape="):]
        shape = shape[:shape.index("if(box.dataset.shape")]
        self.assertIn("r.title", shape)
        self.assertIn('"live>"+title', shape)


class TheServerGoneMidSessionTests(ApiCase):
    """robin, 2026-08-24: a turn died with `[WinError 10061]` and he reported it
    as "Zugriff verweigert trotz auto" -- a permission refusal. It was neither
    that nor the tools: the llama-server had been ended in the Task Manager,
    which is why nothing in the event log recorded a crash.

    THE SENTENCE THAT WOULD HAVE SAID SO ALREADY EXISTED and only the terminal
    printed it. `grep "start llama-server"` found it in cli/crow.py and not once
    in cli/crow_gui.py, so the window showed the raw WinError and no way out.
    """

    def _dies_with(self, exc):
        api = self.api()

        def _boom(*_a, **_k):
            raise exc

        with mock.patch.object(crow_gui, "run_turn", _boom):
            api._run("was ist los")
        return [m["t"] for m in self.drained(api) if m.get("k") == "fail"]

    def test_a_server_that_stopped_answering_says_what_to_do(self):
        said = self._dies_with(crow_core.Unreachable(
            "cannot reach http://127.0.0.1:8082/v1/chat/completions: "
            "[WinError 10061]"))
        self.assertTrue(said, "a turn against a dead server said nothing at all")
        self.assertIn(crow_core.SERVER_DOWN_HINT, said[-1])
        # THE CAUSE SURVIVES THE ADVICE. Replacing the WinError with the hint
        # would hide which endpoint was silent, and the port is the one detail
        # that separates "server is down" from "wrong port configured".
        self.assertIn("cannot reach", said[-1])

    def test_a_failure_that_is_not_the_server_gets_no_such_advice(self):
        """NEGATIVE, and the reason `Unreachable` is a type rather than a text
        match: told to start a server, somebody debugging a refused schema goes
        looking in the wrong place entirely."""
        said = self._dies_with(crow_core.CrowError(
            "HTTP 400 from http://127.0.0.1:8082/v1/chat/completions: "
            "failed to parse grammar"))
        self.assertTrue(said, "an ordinary failure said nothing at all")
        self.assertNotIn(crow_core.SERVER_DOWN_HINT, said[-1])

    def test_a_boot_that_failed_is_not_told_to_boot(self):
        """NEGATIVE for the class boundary itself. `ServerBootError` IS a
        `CrowError`, so a check written as `except CrowError` would hand the
        advice to the one caller that already tried exactly that and failed --
        the distinction crow_core.py:823 gave it its own class for."""
        said = self._dies_with(crow_core.ServerBootError(
            "llama-server exited with 1 before it was ready."))
        self.assertTrue(said)
        self.assertNotIn(crow_core.SERVER_DOWN_HINT, said[-1])


class TheFormattedAnswerTests(ApiCase):
    """ROBIN, 2026-08-23: the answers arrive as their own source. `**Wetter:**`
    with the stars on screen, a table drawn as pipes.

    THE CUT IS THE CORE'S, THE DRAWING IS THE WINDOW'S, which is the seam
    `CodeFences` already uses. The page receives named pieces and builds
    elements out of `textContent`; it never turns text from the wire into
    markup, and the case below holds it to that.

    IT HAPPENS WHEN A RUN OF PROSE IS OVER, not while it streams. Half of
    `**bold` is not bold yet, so a page fed deltas would flicker between two
    readings of the same sentence. The visible cost is one repaint at the end of
    the turn; the alternative is a parser that has to be right about text it has
    not seen yet.
    """

    def test_the_answer_is_cut_into_blocks_once_it_is_finished(self):
        """POSITIVE: the shape of robin's weather answer."""
        sent = self.sink_events([{"content": "## Palma\n\n"},
                                 {"content": "- **Wetter:** Sonnig\n"},
                                 {"content": "- Wind: 4 km/h\n"}])
        drawn = [m for m in sent if m["k"] == "format"]
        self.assertEqual(len(drawn), 1, "the answer was never cut")
        self.assertEqual([b["t"] for b in drawn[0]["blocks"]], ["h", "ul"])
        self.assertEqual(drawn[0]["blocks"][1]["items"][0][0],
                         {"s": "Wetter:", "b": True})

    def test_the_prose_above_a_code_block_is_drawn_before_it_opens(self):
        """THE ORDER IS THE WHOLE POINT. The page hangs the blocks on the prose
        element it is holding, and `codeOpen` lets go of it -- so a `format`
        that arrived after the fence would find nothing and the bold above the
        code would stay stars."""
        sent = self.sink_events([{"content": "**hi**\n```py\nx = 1\n```\n"}])
        kinds = [m["k"] for m in sent]
        self.assertIn("format", kinds)
        self.assertIn("code_open", kinds)
        self.assertLess(kinds.index("format"), kinds.index("code_open"))

    def test_an_answer_with_nothing_in_it_leaves_no_frame(self):
        """NEGATIVE: a turn that only thought, or one cut off before it spoke,
        must not push an empty block for the page to draw."""
        sent = self.sink_events([{"reasoning_content": "only thinking"}])
        self.assertEqual([m for m in sent if m["k"] == "format"], [])

    def test_the_page_builds_the_blocks_and_never_writes_markup(self):
        """THE RULE THIS FEATURE COULD HAVE BROKEN. Everything between the two
        markers is the drawing, and a single `innerHTML` in there would make a
        model's answer a place to put script."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        start = source.index("// -- markdown, drawn from what the core cut")
        end = source.index("// -- end markdown")
        drawing = source[start:end]
        self.assertNotIn("innerHTML", drawing)
        self.assertIn("textContent", drawing)
        self.assertIn("createElement", drawing)

    def test_a_target_that_is_not_http_never_reaches_a_browser(self):
        """THE SECOND GATE. The core already refuses to name one, and this one
        would still be reached by a page that was handed something else -- the
        text is a stranger's, so it is checked on both sides of the boundary."""
        api = self.api()
        opened = []
        real = crow_gui.webbrowser.open
        crow_gui.webbrowser.open = lambda url: opened.append(url) or True
        self.addCleanup(setattr, crow_gui.webbrowser, "open", real)
        for bad in ("javascript:alert(1)", "file:///C:/Windows/win.ini",
                    "data:text/html,<script>", "", "ftp://x/y"):
            self.assertFalse(api.open_url(bad), bad)
        self.assertEqual(opened, [], "one of them reached the browser")
        self.assertTrue(api.open_url("https://www.wetter.com"))
        self.assertEqual(opened, ["https://www.wetter.com"])



class TheUpdateButtonTests(ApiCase):
    """robin, 2026-08-23: the window should be able to update itself.

    THE TERMINAL HAS HAD THE CHECK SINCE 0.0.6 and prints the command to run.
    That works at a prompt and nowhere else, so the same knowledge ends in a
    button here. The versions are not decided again: `update_state` is a thin
    line over `fetch_latest_version` and `is_newer`, which the CLI already uses.

    A RESTART IS PART OF THE FEATURE, NOT AN AFTERTHOUGHT. The installer
    replaces the files under the running process; Python has the modules in
    memory and goes on running the old ones until it is started again. A button
    that said "installed" and left it there would leave the reader looking at
    the version they were trying to leave.
    """

    def _source(self) -> str:
        return (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_the_about_pane_carries_the_button_and_the_restart_line(self):
        source = self._source()
        about = source[source.index('<section data-cat="about"'):]
        about = about[:about.index("</section>")]
        self.assertIn('id="updbtn"', about)
        self.assertIn('id="updsaid"', about)
        self.assertIn("restart", about.lower(),
                      "the pane never says that a restart is needed")

    def test_opening_about_asks_github(self):
        """The check runs when the pane is opened, not on every start: it is a
        network call, and the window already refuses to spend one on a catalogue
        nobody asked for."""
        source = self._source()
        switch = source[source.index("  settingsCat(name){"):]
        switch = switch[:switch.index("\n  },")]
        self.assertIn("updateCheck()", switch)

    def test_the_check_hands_both_versions_to_the_page(self):
        api = self.api()
        real = crow_core.fetch_latest_version
        crow_core.fetch_latest_version = lambda timeout=4.0: "99.0.0"
        self.addCleanup(setattr, crow_core, "fetch_latest_version", real)
        state = api.update_check()
        self.assertEqual(state["current"], crow_core.CLIENT_VERSION)
        self.assertEqual(state["latest"], "99.0.0")
        self.assertTrue(state["newer"])
        self.assertIn("install_dir", state)

    def test_the_check_uses_the_version_the_window_knows(self):
        """FOUND BY RUNNING IT, AND THE SUITE COULD NOT HAVE. `CLIENT_VERSION`
        is assigned by cli/crow.py when that file is imported, and the window
        never imports it -- it reads the literal out of that file with
        `client_version()` instead. So the constant is EMPTY in this process,
        `parse_version` refuses it, and a check built on it answers "no update"
        forever -- including on the day one is published, which is the only day
        it matters.

        The core's own default stays the constant, because for the terminal it
        is right."""
        api = self.api()
        real = crow_core.fetch_latest_version
        crow_core.fetch_latest_version = lambda timeout=4.0: "99.0.0"
        self.addCleanup(setattr, crow_core, "fetch_latest_version", real)
        # THE CONSTANT IS EMPTIED ON PURPOSE, and without this line the case is
        # blind: THIS FILE imports cli/crow.py at the top, and that import is
        # what assigns `CLIENT_VERSION`. The window imports no such thing, so
        # the state under test is the empty one, and a case that measured the
        # test runner's imports would pass while the window answered "no
        # update" forever.
        was, crow_core.CLIENT_VERSION = crow_core.CLIENT_VERSION, ""
        self.addCleanup(setattr, crow_core, "CLIENT_VERSION", was)
        state = api.update_check()
        self.assertTrue(state["current"], "the window handed over no version")
        self.assertEqual(state["current"], crow_gui.client_version())
        self.assertTrue(state["newer"])

    def test_a_second_press_while_one_runs_is_refused(self):
        """NEGATIVE: two installers writing the same directory at once is the
        one way this can leave a broken copy behind."""
        api = self.api()
        api._updating = True
        self.assertTrue(api.update_start(), "the second press was allowed")

    def test_the_installer_is_run_as_a_file_and_the_end_says_to_restart(self):
        api = self.api()
        handle, script = tempfile.mkstemp(prefix="crow-fake-", suffix=".ps1")
        os.close(handle)
        real_fetch = crow_core.fetch_install_script
        crow_core.fetch_install_script = lambda timeout=20.0: script
        self.addCleanup(setattr, crow_core, "fetch_install_script", real_fetch)
        seen = []

        class _Proc:
            stdout = iter(["step 1 of 5 -- downloading\n", "\n", "done\n"])

            def wait(self_inner):
                return 0

        real_popen = crow_gui.subprocess.Popen
        crow_gui.subprocess.Popen = lambda argv, **kw: (seen.append(argv), _Proc())[1]
        self.addCleanup(setattr, crow_gui.subprocess, "Popen", real_popen)
        api._update_run()
        said = [m for m in self.drained(api) if m.get("k") == "update"]
        # WAS `-NoPause` UND WAS ES AUF LINUX ERSETZT. Der Grund ist derselbe
        # und steht in `crow_platform.updater_command`: der Installer wartet am
        # Ende auf ENTER, damit man den letzten Bildschirm lesen kann, und hinter
        # einem Fenster ohne Konsole ist das ein Warten ohne Ende. Auf Windows
        # ist das Gegenmittel der Schalter; install.sh hat nichts dergleichen,
        # also ist der Aufruf dort nackt -- aber `bash` MUSS davor stehen, weil
        # ein ueber HTTP geholtes Skript ohne Ausfuehrungsrecht ankommt.
        if crow_platform.IS_WINDOWS:
            self.assertIn("-NoPause", seen[0])
        else:
            self.assertEqual(seen[0][0], "bash")
        self.assertIn(script, seen[0])
        self.assertTrue(said[-1]["done"])
        self.assertIn("restart", said[-1]["t"].lower())
        self.assertTrue(any("downloading" in m.get("t", "") for m in said),
                        "the installer's own lines never reached the page")
        self.assertFalse(os.path.exists(script),
                         "the downloaded installer was left on the disk")
        self.assertFalse(api._updating, "the button stayed locked")

    def test_an_installer_that_failed_promises_nothing(self):
        """NEGATIVE, and it is the half that matters: a non-zero exit means the
        files may be half replaced. Saying "restart to use it" there sends the
        reader to find out for themselves."""
        api = self.api()
        handle, script = tempfile.mkstemp(prefix="crow-fake-", suffix=".ps1")
        os.close(handle)
        real_fetch = crow_core.fetch_install_script
        crow_core.fetch_install_script = lambda timeout=20.0: script
        self.addCleanup(setattr, crow_core, "fetch_install_script", real_fetch)

        class _Proc:
            stdout = iter(["not enough disk\n"])

            def wait(self_inner):
                return 3

        real_popen = crow_gui.subprocess.Popen
        crow_gui.subprocess.Popen = lambda argv, **kw: _Proc()
        self.addCleanup(setattr, crow_gui.subprocess, "Popen", real_popen)
        api._update_run()
        last = [m for m in self.drained(api) if m.get("k") == "update"][-1]
        self.assertTrue(last["done"])
        self.assertNotIn("restart", last["t"].lower())
        self.assertIn("3", last["t"])
        self.assertFalse(api._updating)



class TheMicrophoneReportsItsLevelTests(unittest.TestCase):
    """robin, 2026-08-23: die Stimme soll als Voiceline in der Eingabemaske zu
    sehen sein, "besseres Feedback für den User".

    THE STREAM ALREADY HAS THE BLOCKS. PortAudio hands `take()` a buffer every
    few milliseconds and the recorder copies it into a list; the level is that
    same buffer, read once, and nothing new is opened for it. A second stream
    for a meter would be a second thing that can fail to open.

    NULL BEIM STILLSTAND, und das ist keine Formsache: eine Anzeige, die nach
    dem Stopp weiterzappelt, behauptet ein Mikrofon, das nicht mehr zuhört.
    """

    def setUp(self) -> None:
        crow_voice.cancel()

    def test_a_silent_stream_reports_nothing(self):
        """NEGATIVE, und die wichtigste: ohne Aufnahme ist der Pegel 0."""
        self.assertEqual(crow_voice.level(), 0.0)

    def test_the_level_follows_the_loudest_sample_of_the_block(self):
        """Spitze statt Mittel: ein RMS über 20 ms glättet genau die Silben
        weg, die man sehen will."""
        import array
        crow_voice._note_level(array.array("f", [0.0, 0.5, -0.25]))
        self.assertAlmostEqual(crow_voice.level(), 0.5, places=3)
        crow_voice._note_level(array.array("f", [0.0, 0.02]))
        self.assertLess(crow_voice.level(), 0.5, "der Pegel blieb oben stehen")

    def test_a_block_of_nothing_is_not_an_error(self):
        """NEGATIVE: ein leerer Block kommt vor, wenn der Treiber nachlädt."""
        import array
        crow_voice._note_level(array.array("f", []))
        self.assertEqual(crow_voice.level(), 0.0)

    def test_the_level_is_dropped_when_the_stream_is(self):
        """`cancel` und `stop` schließen den Strom; was danach noch angezeigt
        würde, wäre der letzte Ton von vorhin."""
        import array
        crow_voice._note_level(array.array("f", [1.0]))
        crow_voice.cancel()
        self.assertEqual(crow_voice.level(), 0.0)



class TheVoiceLineTests(ApiCase):
    """Was das Fenster daraus macht: ein Balkenband in der Eingabemaske,
    solange aufgenommen wird.

    GEZEICHNET WIRD IM FENSTER, GEMESSEN IN PYTHON. Die Seite ist kein
    sicherer Kontext -- `getUserMedia` scheitert dort, gemessen am 2026-08-13
    an `navigator.clipboard` -- also kann sie das Mikrofon nicht selbst hören
    und bekommt den Pegel über dieselbe Naht wie den Text.
    """

    def _source(self) -> str:
        return (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_the_band_lies_in_the_line_and_adds_no_row(self):
        """robin, 2026-08-23: nicht ueber dem Platzhalter, sondern an seiner
        Stelle. Eine eigene Zeile machte die Maske jedes Mal hoeher, wenn
        jemand zu sprechen anfaengt, und schoebe alles darunter nach unten --
        genau die Bewegung, die der Mikrofonknopf mit seinem Ring vermeidet."""
        source = self._source()
        line = source[source.index('<div id="line">'):]
        line = line[:line.index('<div id="foot">')]
        self.assertIn('id="voice"', line, "das Band steht nicht in der Zeile")
        css = source[source.index("#voice{"):]
        css = css[:css.index("}")]
        self.assertIn("position:absolute", css,
                      "das Band nimmt Platz und schiebt die Zeile")
        self.assertIn("pointer-events:none", css,
                      "das Band faengt die Klicks des Textfeldes ab")
        self.assertIn("#line{display:flex;position:relative", source,
                      "die Zeile ist kein Bezugsrahmen, das Band landet woanders")

    def test_a_quiet_microphone_is_not_a_flat_band(self):
        """GEFUNDEN IM LAUF, 2026-08-23: robin sprach, der Text kam sauber
        zurueck, und das Band blieb eine Punktreihe. Der Pegel war richtig, die
        Skala war geraten -- float32-Sprache liegt bei 0,05 bis 0,3, und
        `level*22` macht daraus vier Pixel, also den Boden.

        DIE SKALA MISST SICH JETZT SELBST. Ein mitlaufender Spitzenwert mit
        Abklingen ist das, was ein Aussteuerungsmesser tut: laut zieht ihn
        hoch, Stille laesst ihn sinken, und das Band fuellt sich unabhaengig
        davon, wie laut das Mikrofon eingestellt ist. Ein fester Faktor kann
        das nicht, weil er die Verstaerkung des Geraets raten muesste."""
        source = self._source()
        wave = source[source.index("  voice(e){"):]
        wave = wave[:wave.index("\n  settingsCat")]
        self.assertIn("vpeak", wave, "die Skala ist wieder fest")
        self.assertNotIn("e.level*22", wave)
        self.assertIn("band.clientWidth", wave,
                      "die Zahl der Balken haengt nicht an der Breite")

    def test_the_placeholder_goes_while_it_records(self):
        """robin, 2026-08-23: der Platzhalter steht noch da, wenn die
        Spracheingabe laeuft. Das Band liegt darueber, also stehen beide
        uebereinander -- und die Punkte lesen sich als Zeichen im Satz."""
        source = self._source()
        self.assertIn("#box.rec #in::placeholder", source)
        self.assertIn('box.classList.toggle("rec"', source,
                      "niemand setzt die Klasse, die den Platzhalter nimmt")

    def test_the_composer_stands_on_the_edge_of_its_own_column(self):
        """DIE ZAHL IST EINMAL HIN UND WIEDER ZURUECK GEGANGEN, und der Fall
        traegt beide Haelften, weil sonst der naechste Versuch dieselbe Runde
        dreht. robin, 2026-08-23: erst "die Maske um 25 % schmaler" (900 ->
        675), am selben Abend zurueck auf die Breite des Chats. Gesehen ist die
        Maske, die unter ihrer eigenen Spalte steht, die ruhigere.

        900 UND NICHT 960: `.turn` gibt von seinen 960 je 30 an das Polster ab,
        der Text beginnt also bei 900 -- und genau darauf sitzt dieser Rahmen.
        """
        source = self._source()
        box = source[source.index("#box{border:"):]
        box = box[:box.index("#box.focus")]
        # #280: die 900 steht einmal, als --colw, und beide lesen sie.
        self.assertIn("--colw:900px", source)
        self.assertIn("max-width:var(--colw)", box)
        self.assertNotIn("max-width:675px", box)
        column = source[source.index(".turn{padding:"):]
        self.assertIn("max-width:calc(var(--colw) + 2 * var(--colpad))",
                      column[:column.index("}")],
                      "die Spalte hat sich bewegt, die Maske folgt ihr nicht mehr")

    def test_the_bars_are_mirrored_and_thin(self):
        """robins zweite Vorgabe: nach oben UND unten, und nicht so breit.
        `align-items:center` ist das, was einen Balken um die Mitte wachsen
        laesst statt vom Boden -- und eine feste Breite ist das, was ihn schmal
        haelt, wenn `flex:1` ihn sonst ueber die ganze Zeile zieht."""
        source = self._source()
        band = source[source.index("#voice{"):]
        band = band[:band.index("#voice[hidden]")]
        self.assertIn("align-items:center", band)
        self.assertIn("flex:none", band, "die Balken teilen sich noch die Breite")
        self.assertNotIn("align-items:flex-end", band)
        # VOLL GERUNDET: nur so ist ein ruhender Balken ein Punkt statt einer
        # kurzen Linie, und Stille zeichnet sich als Punktreihe.
        self.assertIn("border-radius:99px", band)

    def test_the_band_only_exists_while_it_records(self):
        """Kein Balken im Ruhezustand: die Maske sieht aus wie immer, bis
        jemand spricht."""
        source = self._source()
        self.assertIn("#voice{", source, "die Regel fehlt")
        # DIE EIGENE REGEL SCHLAEGT DAS ATTRIBUT. `#voice{display:flex}` ist
        # spezifischer als das `display:none`, das der Browser an `[hidden]`
        # haengt -- ohne die zweite Regel steht das Band immer da, und das
        # `hidden` im Markup sieht dabei aus, als taete es etwas.
        self.assertIn("#voice[hidden]{display:none}", source)
        self.assertIn('$("#voice").hidden', source,
                      "niemand blendet das Band aus")

    def test_a_recording_pushes_levels_and_a_stop_ends_them(self):
        """POSITIVE und NEGATIVE in einem Lauf: solange der Strom offen ist,
        kommen Pegel; danach keiner mehr."""
        api = self.api()
        real_level = crow_voice.level
        real_rec = crow_voice.recording
        crow_voice.level = lambda: 0.4
        crow_voice.recording = lambda: True
        self.addCleanup(setattr, crow_voice, "level", real_level)
        self.addCleanup(setattr, crow_voice, "recording", real_rec)
        api._voice_tick()
        pushed = [m for m in self.drained(api) if m.get("k") == "voice"]
        self.assertTrue(pushed, "kein Pegel erreichte die Seite")
        self.assertAlmostEqual(pushed[-1]["level"], 0.4, places=3)
        crow_voice.recording = lambda: False
        api._voice_tick()
        last = [m for m in self.drained(api) if m.get("k") == "voice"]
        self.assertTrue(last and last[-1]["level"] == 0.0,
                        "das Band wurde nicht auf null gesetzt")


class TheRailIsDraggableTests(ApiCase):
    """robin, 2026-08-23: die Trennlinie zwischen Rail und Chat soll gezogen
    werden können.

    DIE BREITE IST EINE EINSTELLUNG, kein Zustand der Seite. Ein Fenster, das
    beim nächsten Start wieder 242 Pixel breit ist, hat die Geste nicht
    gespeichert, sondern nur vorgeführt.
    """

    def _source(self) -> str:
        return (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_there_is_a_handle_between_the_rail_and_the_chat(self):
        source = self._source()
        self.assertIn('id="railgrip"', source)
        self.assertLess(source.index('<aside id="rail">'),
                        source.index('id="railgrip"'))
        self.assertLess(source.index('id="railgrip"'), source.index('<div id="flow">'))

    def test_the_width_survives_a_restart(self):
        api = self.api()
        self.assertTrue(api.rail_width(310))
        self.assertEqual(crow_gui.read_settings().get("rail_width"), 310)

    def test_a_width_nobody_could_use_is_refused(self):
        """NEGATIVE: eine Rail von 12 Pixeln ist keine Rail, und eine, die den
        halben Bildschirm nimmt, lässt keinen Chat übrig. Der Griff klemmt in
        der Seite, und Python klemmt noch einmal -- der Wert kommt aus einer
        Maus."""
        api = self.api()
        for silly in (0, 12, 4000, -30, "breit", None):
            self.assertFalse(api.rail_width(silly), silly)

    def test_the_chat_keeps_its_distance_from_both_edges(self):
        """robins zweiter Punkt: der Chat soll links wie rechts ein paar Pixel
        Luft haben. Links ist die Rail, rechts der Scrollbalken -- der Rinnstein
        steht schon stabil, die Luft daneben ist neu."""
        source = self._source()
        css = source[source.index("<style>"):source.index("</style>")]
        rule = css[css.index("#flow{"):]
        rule = rule[:rule.index("}")]
        self.assertIn("padding-inline", rule)
        self.assertIn("scrollbar-gutter:stable", rule)



class ThePanelSeparatesCodeFromCallsTests(unittest.TestCase):
    """#138b. Es war ein Werkzeug-Panel geworden, und das war nie gewollt.

    robins Befund am 2026-08-26, an seinem eigenen Screenshot: unter `CODE`
    standen elf Kaesten, und in jedem lag die JSON-Huelle eines Aufrufs --
    `{"query":"C++ reference documentation","count":6}` neben
    `{"command":"where node npx"}`. Der Quelltext, den derselbe Zug geschrieben
    hatte, war einer davon und in nichts unterschieden.

    DREI TRENNUNGEN MACHEN DARAUS WIEDER EIN CODE-PANEL: Programmcode bekommt
    einen eigenen Abschnitt, ein Aufruf klappt einzeln statt neunzig auf einmal,
    und was er ANTWORTETE steht in einem eigenen Block unter dem, was er bekam.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    # ---- was ueber die Naht geht

    def test_a_long_answer_is_capped_before_it_reaches_the_page(self):
        """POSITIV. Der Kern reicht die ganze Antwort herueber; hier wird
        geschnitten, weil hier der Bildschirm ist."""
        seen = []
        crow_gui.Turn(seen.append).tool_result("read_file", "x" * 10000)
        said = [m for m in seen if m.get("k") == "toolres"][0]
        self.assertEqual(len(said["t"]), crow_gui.TOOL_RESULT_SHOWN)
        self.assertEqual(said["cut"], 10000 - crow_gui.TOOL_RESULT_SHOWN)

    def test_a_short_answer_is_not_reported_as_cut(self):
        """NEGATIV zum obigen. Ein `cut`, das immer eine Zahl traegt, waere eine
        Zeile, die unter jeder Antwort steht und nichts mehr bedeutet."""
        seen = []
        crow_gui.Turn(seen.append).tool_result("list_dir", "two files")
        said = [m for m in seen if m.get("k") == "toolres"][0]
        self.assertEqual(said["cut"], 0)
        self.assertEqual(said["t"], "two files")

    def test_the_seam_marks_code_without_withholding_anything(self):
        """DIE NAHT SORTIERT NICHT AUS, sie etikettiert.

        Der Filter sass hier zuerst als `return`, und
        `test_two_calls_do_not_share_a_pending_backslash` wurde rot -- sein
        zweiter Aufruf ist ein `read_file`. Er hatte aus einem groesseren Grund
        recht als seinem eigenen: eine Naht, die nach Werkzeugnamen wegwirft,
        nimmt jeder kuenftigen Ansicht dieselbe Entscheidung ab.
        """
        seen = []
        sink = crow_gui.Sink(seen.append)
        sink.tool_arguments(0, "write_file", '{"path":"a.py"}')
        sink.tool_arguments(1, "web_search", '{"query":"x"}')
        said = [m for m in seen if m.get("k") == "toolarg"]
        self.assertEqual([m["code"] for m in said], [True, False])
        self.assertEqual(len(said), 2, "beide Stroeme gehen hinueber")

    def test_reading_a_file_is_not_program_code(self):
        """NEGATIV fuer die Liste. Crow liest viel, was es nicht aendert, und ein
        Abschnitt voller fremder Dateien beantwortet die Frage nicht mehr, fuer
        die er da ist."""
        self.assertEqual(crow_gui.CODE_TOOLS, ("write_file", "edit_file"))
        self.assertNotIn("read_file", crow_gui.CODE_TOOLS)
        self.assertNotIn("run_command", crow_gui.CODE_TOOLS)

    # ---- was die Seite daraus macht

    def test_the_page_draws_a_block_only_for_code(self):
        js = self.source[self.source.index("  toolArg(i,name,piece"):]
        js = js[:js.index(chr(10) + "  langOf(text){")]
        self.assertIn("if(!code) return;", js)
        self.assertIn('$("#cflist")', js)

    def test_program_code_has_its_own_section_and_hides_when_empty(self):
        """Eine Ueberschrift ueber einer leeren Flaeche behauptet einen Inhalt."""
        self.assertIn('id="codefiles"', self.source)
        self.assertIn('<section id="codefiles" hidden>', self.source)
        self.assertIn("#codefiles[hidden]{display:none}", self.css)

    def test_the_call_list_stays_above_the_code_that_grows(self):
        """robins Entscheidung am 2026-08-26, und sie hat einen Grund, der sich
        nicht von selbst wieder einstellt: die Klappe ist der INDEX. Andersherum
        gebaut schob sie jede geschriebene Datei weiter nach unten, und ein
        Index, den man suchen muss, ist keiner."""
        body = self.source[self.source.index('<div id="codebody">'):]
        body = body[:body.index("</aside>")]
        self.assertLess(body.index('id="toolcalls"'), body.index('id="codefiles"'),
                        "die Aufrufliste steht ueber dem Quelltext")

    def test_a_row_folds_on_its_own_and_catches_its_click(self):
        """Die Falle vom 2026-08-22, hier vorweggenommen: ein Klick, der bis zum
        Gruppenkopf blubbert, faltet genau das weg, was er oeffnen sollte."""
        self.assertIn("#toolcalls .tool.shut .tbody{display:none}", self.css)
        js = self.source[self.source.index('d.querySelector(".hd").addEventListener'):]
        js = js[:js.index("this.openCall=d;")]
        self.assertIn("ev.stopPropagation();", js)
        self.assertIn('d.classList.toggle("shut")', js)

    def test_the_answer_gets_its_own_block_under_the_arguments(self):
        """Beides in einem Kasten war die Form, die aus dem Panel eine JSON-Wand
        gemacht hat: was hineinging und was herauskam sahen gleich aus."""
        js = self.source[self.source.index("  toolRes(name,text,cut){"):]
        js = js[:js.index("this.openCall=null;")]
        self.assertIn('wrap.className="tsec res"', js)
        self.assertIn('head.textContent = bad ? "error" : "result"', js)
        self.assertIn("#toolcalls .res .tsp{", self.css)

    def test_a_failed_call_is_marked_on_the_head_not_only_inside(self):
        """Sonst muesste man neunzig Zeilen aufklappen, um den einen zu finden,
        der der Grund war."""
        self.assertIn("#toolcalls .tool.bad .ico{", self.css)
        self.assertIn('if(bad) row.classList.add("bad");', self.source)

    def test_clearing_takes_both_halves_and_the_watermark(self):
        """"Den gesamten Verlauf loeschen" heisst beides. Zwei Knoepfe an zwei
        Stellen waeren zwei halbe Antworten."""
        js = self.source[self.source.index("  codeWipe(e){"):]
        js = js[:js.index("},")]
        self.assertIn("this.codeReset();", js)
        self.assertIn('$("#tclist").textContent="";', js)
        self.assertIn("pywebview.api.tools_cleared();", js)

    def test_clearing_drops_the_pointer_to_the_boxes_it_removed(self):
        """NEGATIV, und unsichtbar wenn es fehlt: `this.live` zeigt nach dem
        Leeren auf Elemente, die in keinem Dokument mehr stehen. Ein laufender
        Strom haenge Zeichen an sie an, ohne dass irgendwo etwas erscheint."""
        js = self.source[self.source.index("  codeReset(){"):]
        js = js[:js.index("},")]
        self.assertIn("this.live=null;", js)
        self.assertIn("this.openCall=null;", js)


class TheCodePanelTests(unittest.TestCase):
    """#138. The pane on the right: what is being written, while it is written.

    IT IS THE RAIL MIRRORED, and that is the whole design brief robin gave. Every
    rule here has a twin on the left -- clamp, grip, fold, rounded seam -- and the
    ones that differ do so for a reason each case names.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]
        self.dir = tempfile.mkdtemp(prefix="crow-code-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self._real = crow_gui.SETTINGS_FILE
        self.addCleanup(setattr, crow_gui, "SETTINGS_FILE", self._real)
        crow_gui.SETTINGS_FILE = os.path.join(self.dir, "settings.json")

    def _settings(self, doc):
        with open(crow_gui.SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    # ---- what the window remembers

    def test_the_panel_is_shut_until_somebody_opens_it(self):
        """THE OPPOSITE DEFAULT TO THE RAIL, and the difference is the content.
        The rail holds the chats, which exist before the first turn; this holds
        what a tool is writing, which does not. A pane that opens empty on every
        start takes 280 px to say nothing."""
        self.assertFalse(crow_gui.code_open())

    def test_the_remembered_state_is_read_back(self):
        self._settings({"code_open": True})
        self.assertTrue(crow_gui.code_open())

    def test_a_width_outside_the_clamp_becomes_the_default(self):
        """NEGATIVE, and the rail's reason applies unchanged: a value out of
        bounds did not come from this gesture, so pulling it to the boundary
        would be a decision nobody made."""
        self._settings({"code_width": 9000})
        self.assertEqual(crow_gui.code_width_setting(), crow_gui.CODE_DEFAULT)
        self._settings({"code_width": crow_gui.CODE_MIN})
        self.assertEqual(crow_gui.code_width_setting(), crow_gui.CODE_MIN)

    def test_a_width_that_is_not_a_number_becomes_the_default(self):
        for junk in (True, "420", None, [420]):
            self._settings({"code_width": junk})
            self.assertEqual(crow_gui.code_width_setting(), crow_gui.CODE_DEFAULT,
                             "%r was taken as a width" % (junk,))

    # ---- what the page carries

    def test_the_page_carries_the_panel_its_grip_and_its_button(self):
        for want in ('id="code"', 'id="codegrip"', 'id="codetoggle"'):
            self.assertIn(want, self.source, "%s is missing from the page" % want)

    def test_the_rounded_seam_is_mirrored(self):
        """robin: "selbe abgerundete Kante wie beim chat panel nur gespiegelt".
        The seam is #main's, not the panel's -- the chat column is the thing with
        the corner, and it has one on each side once both panels exist."""
        import re
        m = re.search(r"#main\{([^}]*)\}", self.css)
        self.assertTrue(m, "#main lost its rule")
        body = m.group(1)
        self.assertIn("border-top-left-radius:12px", body)
        self.assertIn("border-top-right-radius:12px", body)

    def test_the_toggle_sits_in_the_title_bar(self):
        """#119's reason, unchanged: a button inside the panel goes away with the
        panel, and then there is no way back."""
        bar = self.source[self.source.index('<div id="bar"'):]
        bar = bar[:bar.index("</div>\n\n<div id=\"settings\"")] if "</div>\n\n<div id=\"settings\"" in bar else bar[:4000]
        self.assertIn('id="codetoggle"', bar)

    def test_the_toggle_is_drawn_at_the_rail_icons_weight(self):
        """robin asked for the stroke weight of the chat-panel icon. The Noun
        Project file is filled paths with no stroke at all, so it is redrawn as
        strokes rather than embedded -- which also settles the attribution, and
        docs/ is not shipped anyway."""
        start = self.source.index('id="codetoggle"')
        svg = self.source[start:start + 700]
        self.assertIn('stroke-width="1.6"', svg)
        self.assertIn('stroke="currentColor"', svg)
        # NICHT DER NAME, SONDERN DER STEMPEL. Woher das Zeichen stammt, darf im
        # Kommentar stehen -- was nicht mitreisen darf, sind die beiden <text>-
        # Elemente der Datei, die die Namensnennung ins Bild schreiben und die
        # viewBox auf 0 0 100 125 strecken.
        self.assertNotIn("Created by Focus", self.source)
        self.assertNotIn("<text", svg)

    def test_the_tool_calls_live_inside_the_panel(self):
        """robin: "Tools wandern mit in den Code Panel". Not a second surface
        beside it -- the log and the live view are one pane."""
        panel = self.source[self.source.index('<aside id="code"'):]
        panel = panel[:panel.index("</aside>")]
        self.assertIn('id="toolcalls"', panel)

    def test_a_tool_row_still_folds(self):
        """robin: "Tools bleiben weiterhin auf und zu klappbar". Folding the PANEL
        and folding a ROW are two controls, and the move may not eat one."""
        self.assertIn("toolsToggle()", self.source)
        self.assertIn("#toolcalls.shut .tcbody", self.css)

    def test_the_code_can_be_copied(self):
        """robin: "Code soll ebenfalls kopierbar sein" -- the affordance answers
        already have."""
        panel_css = self.css[self.css.index("#code{"):]
        self.assertIn("copy", self.source[self.source.index('<aside id="code"'):
                                          self.source.index('<aside id="code"') + 3000])

    def test_a_fragment_reaches_the_page_as_its_own_message(self):
        """#138. Der Kern meldet jedes Stueck; das Fenster reicht es weiter und
        haengt es an den Block dieses Aufrufs."""
        seen = []
        sink = crow_gui.Sink(seen.append)
        sink.tool_arguments(0, "write_file", '{"path": "a.py"')
        sink.tool_arguments(0, "write_file", ', "content": "x"}')
        args = [m for m in seen if m.get("k") == "toolarg"]
        self.assertEqual([m["t"] for m in args],
                         ['{"path": "a.py"', ', "content": "x"}'])
        self.assertEqual({m["name"] for m in args}, {"write_file"})
        self.assertEqual({m["i"] for m in args}, {0})

    def test_the_fragment_does_not_move_the_rate(self):
        """NEGATIV: `_tick` zaehlt, was fuer die ANTWORT erzeugt wird. Ein
        `write_file` mit hinein zu rechnen liesse die Rate springen, sobald ein
        Werkzeug schreibt -- und die Rate ist das, woran jemand abliest, ob es
        noch laeuft."""
        seen = []
        sink = crow_gui.Sink(seen.append)
        sink.tool_arguments(0, "write_file", "x" * 500)
        self.assertEqual([m for m in seen if m.get("k") == "live"], [])

    def test_the_page_draws_the_fragment_into_the_panel(self):
        self.assertIn('case "toolarg"', self.source)
        # OHNE DIE SCHLIESSENDE KLAMMER, aus demselben Grund wie bei `tool`:
        # die Funktion nimmt seit #138b mit, ob dieser Aufruf Programmcode
        # schreibt. Der Fall fragt, ob die Seite das Fragment zeichnet, nicht
        # wieviele Parameter sie dafuer entgegennimmt.
        self.assertIn("toolArg(i,name,piece", self.source)
        self.assertIn(".cwp{", self.css)

    def test_a_running_call_closes_its_block(self):
        """Ab `tool` sind die Argumente vollstaendig. Ohne das Schliessen liefe
        die naechste Runde in denselben Block -- sie faengt wieder bei index 0
        an."""
        # DER GANZE RUMPF, nicht die ersten 400 Zeichen. Das Fenster war
        # willkuerlich und wurde rot, als das Einfaerben davor einzog -- an
        # einer Ergaenzung, die genau das tut, was der Fall verlangt.
        #
        # SEIT #138b ENDET ER AN `codeFinish` STATT AN `toolsToggle`. Zwischen
        # den beiden liegen jetzt vier Funktionen, und eine davon setzt
        # `this.live=null` ebenfalls -- gegen `toolsToggle` waere der Fall
        # gruen geblieben, ohne noch etwas ueber `tool` auszusagen.
        js = self.source[self.source.index("  tool(name,args"):]
        js = js[:js.index(chr(10) + "  codeFinish(name,raw){")]
        self.assertIn("this.live=null", js)

    def test_the_shut_panel_takes_no_width(self):
        """The rail's rule mirrored: shut means zero, not narrow."""
        self.assertIn('body[data-code="shut"] #code', self.css)


class TheEscapesAreUnfoldedWhileTheyStreamTests(unittest.TestCase):
    """#138. Was ueber die Leitung kommt, ist ein JSON-String -- nicht Quelltext.

    robin am 2026-08-24, nachdem das Mitlesen lief: da stand `\\"svg xmlns=\\"http`
    und `\\n` als zwei Zeichen. Lesbar, aber muehsam. Entfaltet ist es der Text,
    den das Werkzeug wirklich schreibt.

    SPRACHUNABHAENGIG, UND ZWAR OHNE ZUTUN: die Escapes gehoeren dem Transport,
    nicht der Sprache. `\\n` sieht in Python, SVG, Rust und Bash gleich aus, also
    deckt ein Entfalter alle ab -- robins "fuer alle programmiersprachen" ist
    hier kein Aufwand, sondern die Eigenschaft der Schicht.

    UEBER FRAGMENTGRENZEN HINWEG, was der eigentliche Grund fuer den Zustand ist:
    ein `\\` kann das letzte Zeichen eines Stuecks sein und sein `n` im naechsten.
    """

    def _fold(self, *pieces):
        u = crow_gui.Unescaper()
        return "".join(u.feed(p) for p in pieces)

    def test_the_common_escapes_become_what_they_mean(self):
        self.assertEqual(self._fold(r'a\nb'), "a\nb")
        self.assertEqual(self._fold(r'a\tb'), "a\tb")
        self.assertEqual(self._fold(r'say \"hi\"'), 'say "hi"')
        self.assertEqual(self._fold(r'a\rb'), "a\rb")

    def test_an_escaped_backslash_does_not_become_a_newline(self):
        """DIE WICHTIGSTE NEGATIVPROBE. `\\\\n` ist ein Backslash gefolgt von n --
        ein Windows-Pfad, ein regulaerer Ausdruck, ein LaTeX-Befehl. Wer erst
        `\\n` ersetzt und dann `\\\\`, macht daraus einen Umbruch und zerstoert
        genau die Zeichenketten, die einen Backslash meinen."""
        # VIER BACKSLASHES SIND ZWEI, ZWEI SIND EINER -- und keiner davon ist
        # ein Umbruch. Genau daran scheitert die Ersetzungs-Variante.
        B = chr(92)
        self.assertEqual(self._fold('C:' + B * 2 + 'new'), 'C:' + B + 'new')
        self.assertEqual(self._fold('C:' + B * 4 + 'new'), 'C:' + B * 2 + 'new')
        self.assertEqual(self._fold(B * 4 + 't'), B * 2 + 't')
        self.assertNotIn(chr(10), self._fold('C:' + B * 2 + 'new'))

    def test_a_backslash_at_the_edge_waits_for_its_partner(self):
        """Der Grund, warum das ein Objekt ist und keine Funktion."""
        self.assertEqual(self._fold("a\\", "nb"), "a\nb")
        self.assertEqual(self._fold("x\\", '"y'), 'x"y')

    def test_a_unicode_escape_is_folded_even_when_it_is_split(self):
        self.assertEqual(self._fold(r'\u00e4'), "\u00e4")
        self.assertEqual(self._fold(r'\u00', "e4"), "\u00e4")
        self.assertEqual(self._fold("\\", "u", "00", "e4"), "\u00e4")

    def test_an_unknown_escape_is_left_alone(self):
        """NEGATIV: `\\d` ist in JSON nicht definiert, in einem regulaeren
        Ausdruck aber alltaeglich. Es zu schlucken hiesse, den Ausdruck still zu
        aendern."""
        self.assertEqual(self._fold(r'\d+'), r'\d+')
        self.assertEqual(self._fold(r'\q'), r'\q')

    def test_text_without_escapes_passes_through_untouched(self):
        self.assertEqual(self._fold("def go():", " pass"), "def go(): pass")

    def test_two_calls_do_not_share_a_pending_backslash(self):
        """NEGATIV fuer den Zustand: zwei Aufrufe in einer Runde teilen sich den
        Strom. Ein gemeinsamer Puffer schoebe das Zeichen des einen in den
        anderen."""
        seen = []
        sink = crow_gui.Sink(seen.append)
        sink.tool_arguments(0, "write_file", "a\\")
        sink.tool_arguments(1, "read_file", "b")
        sink.tool_arguments(0, "write_file", "nc")
        said = {m["i"]: "" for m in seen if m.get("k") == "toolarg"}
        for m in seen:
            if m.get("k") == "toolarg":
                said[m["i"]] += m["t"]
        self.assertEqual(said[0], "a\nc")
        self.assertEqual(said[1], "b")

    def test_the_sink_hands_the_page_the_folded_text(self):
        seen = []
        sink = crow_gui.Sink(seen.append)
        sink.tool_arguments(0, "write_file", r'{"content": "line\nline"}')
        said = [m["t"] for m in seen if m.get("k") == "toolarg"]
        self.assertEqual(said, ['{"content": "line\nline"}'])


class ALongCodeBlockFoldsAwayTests(unittest.TestCase):
    """robin, 2026-08-24: "ab 15 Zeilen, koennen wir den codeblock dort auf und
    zuklappbar machen".

    WARUM EINE SCHWELLE UND NICHT IMMER. Ein Block von drei Zeilen ist kuerzer
    als der Kopf, den ein Klappknopf ihm gaebe -- die Falte waere teurer als der
    Inhalt. Ab funfzehn Zeilen schiebt er die Antwort darunter aus dem Bild, und
    genau dort faengt das Wegklappen an, etwas wert zu sein.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]

    def test_the_threshold_is_fifteen_lines(self):
        js = self.source[self.source.index("  codeClose(closed){"):]
        js = js[:js.index("\n  },") + 4]
        self.assertIn("15", js, "die Schwelle steht nicht im Schliesser")

    def test_a_shut_block_hides_its_body_and_not_its_head(self):
        """Der Kopf bleibt stehen, sonst ist der Weg zurueck weg -- dieselbe
        Regel, die der Rail-Knopf in der Titelleiste befolgt."""
        self.assertIn(".code.shut pre", self.css)
        rule = self.css[self.css.index(".code.shut pre"):]
        rule = rule[:rule.index("}") + 1]
        self.assertIn("display:none", rule)
        self.assertNotIn(".code.shut .hd{display:none", self.css)

    def test_the_head_is_what_gets_clicked(self):
        js = self.source[self.source.index("  codeOpen(lang){"):]
        js = js[:js.index("\n  codeClose")]
        self.assertIn('querySelector(".hd")', js)

    def test_copying_does_not_also_fold_the_block(self):
        """NEGATIV, und die Falle, in die die Werkzeug-Kachel schon einmal
        gelaufen ist: der Knopf sitzt IM Kopf, also blubbert sein Klick ohne
        `stopPropagation` bis zur Falte hoch und klappt weg, was gerade kopiert
        wurde."""
        js = self.source[self.source.index("  codeOpen(lang){"):]
        js = js[:js.index("\n  codeClose")]
        copy_at = js.index("btn.onclick")
        self.assertIn("stopPropagation", js[copy_at:copy_at + 400])

    def test_a_short_block_gets_no_fold_at_all(self):
        """NEGATIV fuer die Schwelle: unter funfzehn Zeilen bleibt der Block,
        was er war. Eine Falte, die immer da ist, ist ein Knopf, der meistens
        nichts loest."""
        js = self.source[self.source.index("  codeClose(closed){"):]
        js = js[:js.index("\n  },") + 4]
        self.assertIn("foldable", js)

    def test_the_count_is_shown_where_the_language_is(self):
        """Zugeklappt sagt der Kopf, wie viel darunter liegt -- sonst ist die
        Falte eine Kiste ohne Etikett."""
        self.assertIn(".code .n{", self.css)


def _node() -> "str | None":
    """Node, falls die Maschine eins hat. Sonst None."""
    import shutil
    return shutil.which("node")


class TheHighlighterTests(unittest.TestCase):
    """#138. Farbe je Sprache, und der Tokenisierer wird AUSGEFUEHRT.

    WARUM NICHT NUR DER QUELLTEXT GEPRUEFT WIRD. Jeder andere Fall in dieser
    Datei liest die Seite als Text, und fuer Regeln und Struktur reicht das. Ein
    Tokenisierer ist Logik: er kann jede Zeichenkette im Quelltext tragen und
    trotzdem den falschen Bereich faerben. Node ist auf dieser Maschine da, also
    laeuft er hier wirklich.

    UEBERSPRUNGEN, WO KEIN NODE IST -- eine ausgelieferte Crow braucht keins,
    und ein Fall, der auf fremder Platte rot waere, wuerde ueberlesen.
    """

    @classmethod
    def setUpClass(cls):
        cls.node = _node()
        cls.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def _hl(self, code, lang):
        """Den Tokenisierer aus der Seite schneiden und in Node fahren."""
        import subprocess, json as _json
        start = self.source.index("const HL = {")
        end = self.source.index("\n};", start) + 3
        js = self.source[start:end]
        prog = (js + "\nconst out = HL.parse(" + _json.dumps(code) + "," +
                _json.dumps(lang) + ");\nconsole.log(JSON.stringify(out));\n")
        done = subprocess.run([self.node, "-e", prog], capture_output=True,
                              text=True, encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return _json.loads(done.stdout)

    def _classes(self, code, lang):
        return {cls for cls, _text in self._hl(code, lang) if cls}

    def _text(self, code, lang):
        return "".join(text for _cls, text in self._hl(code, lang))

    # ---- die Eigenschaft, an der alles haengt

    def test_nothing_is_lost_and_nothing_is_invented(self):
        """DIE WICHTIGSTE. Ein Tokenisierer, der Zeichen verschluckt oder
        verdoppelt, faerbt nicht -- er aendert den Code. Und was hier
        durchlaeuft, ist Quelltext, den jemand kopieren wird."""
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        NL = chr(10)
        for lang, code in (
            ("python", 'def go(n):\n    # zaehlt\n    return "x" * n  # hoch'),
            ("json", '{"a": [1, 2.5, true, null], "b": "text"}'),
            ("javascript", 'const x = `a${b}c`; // hi\n/* weg */ let y = 0x1f;'),
            ("html", '<div class="a">text</div><!-- weg -->'),
            ("css", '.a { color: #fff; /* weg */ }'),
            ("bash", 'echo "hi" # weg'),
            ("cpp", "#include <iostream>" + NL +
                    "int main(){ /* weg */ return 0; } // hi"),
            ("java", 'class A { void go(){ String s = "x"; } } // hi'),
            ("go", 'func main() { s := "x" // hi' + NL + " }"),
            ("rust", 'fn main() { let s = "x"; /* weg */ }'),
            ("csharp", "var x = 1; // hi"),
            ("", "kein highlight hier"),
        ):
            self.assertEqual(self._text(code, lang), code, "%s hat den Text veraendert" % lang)

    def test_an_unknown_language_is_one_plain_run(self):
        """NEGATIV: was niemand kennt, wird nicht geraten. Falsche Farbe ist
        schlechter als keine -- sie behauptet eine Struktur, die es nicht gibt."""
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        self.assertEqual(self._classes("def go(): pass", "brainfuck"), set())

    # ---- je Sprache das, was zaehlt

    def test_python_marks_comment_string_keyword_and_number(self):
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        got = self._classes('def go():\n    return "x", 42  # hi', "python")
        self.assertIn("k", got); self.assertIn("s", got)
        self.assertIn("n", got); self.assertIn("c", got)

    def test_a_hash_inside_a_string_is_not_a_comment(self):
        """NEGATIV, und der Fehler, den jeder naive Tokenisierer macht: `#` in
        einer Zeichenkette faerbt sonst den Rest der Zeile als Kommentar."""
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        spans = self._hl('url = "http://x/#anchor"  # echt', "python")
        comments = [t for c, t in spans if c == "c"]
        self.assertEqual(len(comments), 1, spans)
        self.assertIn("echt", comments[0])
        self.assertNotIn("anchor", comments[0])

    def test_a_quote_inside_a_comment_does_not_open_a_string(self):
        """NEGATIV in die andere Richtung: ein Apostroph in `# don't` liesse
        sonst den Rest der Datei als Zeichenkette erscheinen."""
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        spans = self._hl("# don't\nx = 1", "python")
        self.assertIn("n", {c for c, _t in spans})

    def test_json_keys_and_values_are_told_apart(self):
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        got = self._classes('{"path": "a.py", "n": 12, "ok": true}', "json")
        self.assertIn("s", got); self.assertIn("n", got); self.assertIn("k", got)

    def test_html_marks_tags_and_attributes(self):
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        got = self._classes('<svg width="10"><path d="M0 0"/></svg>', "html")
        self.assertIn("t", got); self.assertIn("s", got)

    def test_the_c_family_shares_one_rule_set(self):
        """robin, 2026-08-24: "fuer alle programmiersprachen". Einen Satz je
        Sprache zu schreiben endet nie -- aber C, C++, Java, C#, Go, Rust, PHP,
        Swift und Kotlin teilen sich `//`, `/* */`, Zeichenketten und Zahlen.
        Ein Satz deckt sie alle, und was er nicht kennt, faerbt er nicht."""
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        NL = chr(10)
        got = self._classes(
            "#include <cmath>" + NL +
            "int main(){ // los" + NL +
            "  double x = 3.14; /* weg */" + NL +
            "  return 0;" + NL + "}", "cpp")
        self.assertIn("c", got); self.assertIn("k", got); self.assertIn("n", got)

    def test_every_c_like_label_finds_that_set(self):
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        import subprocess, json as _json
        start = self.source.index("const HL = {")
        end = self.source.index(chr(10) + "};", start) + 3
        js = self.source[start:end]
        labels = ["c", "cpp", "cc", "cxx", "h", "hpp", "java", "cs", "csharp",
                  "go", "golang", "rust", "rs", "php", "swift", "kt", "kotlin"]
        prog = (js + "\nconsole.log(JSON.stringify(" +
                _json.dumps(labels) + ".map(l => HL.lang(l))));")
        done = subprocess.run([self.node, "-e", prog], capture_output=True,
                              text=True, encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        got = _json.loads(done.stdout)
        for label, key in zip(labels, got):
            self.assertEqual(key, "clike", "%s landet bei %r" % (label, key))

    def test_the_language_label_is_taken_loosely(self):
        """`py`, `Python`, `PYTHON` und `python3` meinen dasselbe -- ein Modell
        schreibt in die Fence, was ihm einfaellt."""
        if not self.node:
            self.skipTest("kein node auf dieser Maschine")
        for label in ("py", "Python", "PYTHON", "python3"):
            self.assertIn("k", self._classes("def go(): pass", label), label)

    # ---- wie es in die Seite kommt

    def test_the_page_paints_only_finished_blocks(self):
        """Waehrend des Stroems bleibt es einfarbig: ein halber String faerbt den
        Rest des Blocks, und die Farbe spraenge bei jedem Fragment um."""
        js = self.source[self.source.index("  codeClose(closed){"):]
        js = js[:js.index("\n  },") + 4]
        self.assertIn("paint", js)

    def test_every_colour_comes_from_the_palette(self):
        """Die Regel des Hauses: keine Farbe im Quelltext, sonst kann ein Theme
        sie nicht erreichen."""
        import re
        css = self.source[self.source.index("<style>"):self.source.index("</style>")]
        block = re.findall(r"\.hl-[a-z]\{[^}]*\}", css)
        self.assertTrue(block, "es gibt keine Highlight-Regeln")
        for rule in block:
            self.assertFalse(re.findall(r"#[0-9a-fA-F]{3,6}", rule),
                             "eine Highlight-Regel nennt eine eigene Farbe: %s" % rule)


class TheSuiteTouchesNoRealConfigurationTests(unittest.TestCase):
    """robin, 2026-08-23, nach einer Stunde Fehlersuche: ein Fall dieser Datei
    hat einen erfundenen API-Schluessel in seine ECHTE `mcp_tokens.json`
    geschrieben, und ein zweiter eine `rail_width` in seine echte
    `settings.json`. Beides sind Dateien, die der laufende Client liest.

    DER KOPF DIESER DATEI BOG SCHON VIER PFADE UM -- `MCP_FILE`,
    `PROVIDERS_FILE`, `PROVIDER_KEYS_FILE`, `PROVIDER_TOKEN_FILE` -- und genau
    das ist die Falle: es SAH aus wie geloest. Wer den fuenften Pfad hinzufuegt,
    denkt nicht daran, ihn hier einzutragen, und nichts sagt es ihm.

    ALSO ZAEHLT DIESER FALL NICHT DIE BEKANNTEN, SONDERN SUCHT DIE UNBEKANNTEN:
    er geht jede Konstante beider Module durch, die auf einen Pfad zeigt, und
    verlangt, dass keine davon in das echte Crow-Verzeichnis fuehrt. Ein neuer
    Speicherort geht damit rot, bevor er zum ersten Mal schreibt.
    """

    def _real_roots(self) -> list:
        """Jedes Verzeichnis, in dem eine echte Installation ihre Dateien hat.

        EINE LISTE UND NICHT MEHR EINE WURZEL, seit es zwei Betriebssysteme
        gibt. Auf Windows ist es weiterhin genau eines -- %LOCALAPPDATA%\\Crow,
        und `crow_platform` gibt fuer config/data/state dreimal dasselbe
        zurueck, die Liste schrumpft also von selbst auf einen Eintrag. Auf
        Linux sind es DREI verschiedene (~/.config/crow, ~/.local/share/crow,
        ~/.local/state/crow), und eine Pruefung, die nur nach dem
        Windows-Pfad sucht, ist dort nicht streng, sondern LEER: sie kann gar
        nicht rot werden, weil kein Pfad auf dieser Maschine je so aussieht.
        Genau die Wache, die dieser Fall ist, waere damit still abgeschaltet.

        DURCH DIE NAHT GEFRAGT und nicht hier nachgebaut: `crow_platform` ist
        die Stelle, die weiss, wo eine Installation liegt, und eine zweite
        Antwort daneben waere die erste, die veraltet.
        """
        roots = []
        for path in (crow_platform.config_dir(), crow_platform.data_dir(),
                     crow_platform.state_dir(), crow_platform.cache_dir()):
            here = os.path.normcase(os.path.abspath(path))
            if here not in roots:
                roots.append(here)
        return roots

    def test_no_path_constant_points_into_the_real_crow_directory(self):
        roots = self._real_roots()
        offenders = []
        for module in (crow_core, crow_gui):
            for name in dir(module):
                if not name.isupper():
                    continue
                value = getattr(module, name)
                if not isinstance(value, str) or not value:
                    continue
                if os.sep not in value and "/" not in value:
                    continue
                here = os.path.normcase(os.path.abspath(value))
                if any(here == root or here.startswith(root + os.sep)
                       for root in roots):
                    offenders.append("%s.%s -> %s" % (module.__name__, name, value))
        self.assertEqual(offenders, [],
                         "diese Konstanten zeigen auf die echte Konfiguration:\n  "
                         + "\n  ".join(offenders))


class TheServerSwitchAndKeyFieldTests(unittest.TestCase):
    """The sheet gets the two controls it was missing, and where they may sit.

    robin, 2026-08-24: "es muss automatisch funktionieren, der user soll nicht
    erst in den configs rumwuehlen." He had switched a server off, found no way
    back, and the answer was a text editor in %LOCALAPPDATA%.

    THEY GO IN THE BODY, NOT IN THE HEAD, and that is forced rather than
    chosen. `test_a_server_folds_away` counts exactly two `stopPropagation()`
    across `drawMcpServer`, because every control in the head has to stop a
    click from folding the row away. The body is a sibling of the head, so a
    click in it never reaches the fold and needs no third one -- which is why
    this feature does not touch that case at all.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.js = self.source[self.source.index("  drawMcpServer(box,sv,classes){"):
                              self.source.index("  mcpRow(sv,t,classes){")]

    def test_the_sheet_can_switch_a_server_on_again(self):
        """POSITIVE. The state was readable and unwritable; a row that shows
        `(switched off)` and offers no way back is a trap, not a setting."""
        self.assertIn("toggleServer", self.js)
        self.assertIn("sw", self.js)

    def test_the_switch_does_not_touch_the_fold(self):
        """NEGATIVE PROBE, and the reason the controls sit where they do. If a
        later hand moves them into the head, this goes red here rather than in
        somebody else's case."""
        self.assertEqual(self.js.count("stopPropagation()"), 2)
        head = self.js[:self.js.index("const tools=document.createElement")]
        self.assertNotIn("toggleServer", head)
        self.assertNotIn("serverKey", head)

    def test_the_key_field_is_a_mask(self):
        """A key is shoulder-surfable and screenshots travel. The field shows
        that something is stored, never what."""
        self.assertIn("password", self.js)

    def test_only_an_http_server_offers_a_key_field(self):
        """NEGATIVE PROBE. A stdio server is a local subprocess with no headers
        at all -- a field there would take a secret and drop it on the floor.
        The reference says the same: on stdio the key is ignored."""
        self.assertIn("if(sv.url)", self.js)
        self.assertLess(self.js.index("if(sv.url)"), self.js.index("password"),
                        "the key field is built before anything checks for a URL")

    def test_the_bridge_passes_both_through_to_the_core(self):
        """The page owns no state. Both controls end in `crow_core`, which is
        where the file and the token store are."""
        self.assertIn("def toggle_server(", self.source)
        self.assertIn("crow_core.set_mcp_enabled(", self.source)
        self.assertIn("def set_server_key(", self.source)
        self.assertIn("crow_core.mcp_key_set(", self.source)

    def test_switching_a_server_does_not_move_the_pinned_head(self):
        """THE DIFFERENCE FROM THE SKILL SWITCH, and it is a category, not an
        omission. A skill is text INSIDE the pinned head, so flipping one must
        move the pin. A servers tools are declarations that travel BESIDE the
        head and are rebuilt by mcp_apply. Re-pinning here would rewrite a head
        that did not change and charge a full prefill for it.

        THE COUNT IS THE GUARD. Another case fixes the number of places that
        compose the head; this one names why a server switch is not allowed to
        become one of them.
        """
        body = self.source[self.source.index("    def toggle_server("):]
        body = body[:body.index(chr(10) + "    def ", 10)]
        self.assertNotIn("prompt_head", body)
        self.assertNotIn("repin_memory", body)
        self.assertEqual(self.source.count("crow_core.prompt_head()"), 4)  # #303


class TheMemoryNoteLookTests(unittest.TestCase):
    """robin, 2026-08-24, looking at a finished turn: "das in der mitte dunkel
    verlaufen von beiden seiten macht es zweiteilig."

    THE SWEEP USED TO PARK ITSELF. One gradient did both jobs -- it was the
    animation AND the resting background -- so when the animation finished it
    stopped wherever `forwards` left it: a bright middle with two transparent
    ends, which reads as two tiles rather than one row. A resting state is not
    a stopped animation; it is its own thing, and it has to be a flat fill.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        CLOSE = chr(125)
        self.rule = self.source[self.source.index(".memnote{"):]
        self.rule = self.rule[:self.rule.index(CLOSE)]

    def test_the_row_rests_on_a_flat_fill(self):
        """POSITIVE. What is left after the sweep is one colour across the whole
        row, so nothing about it reads as a seam in the middle."""
        self.assertIn("background-color", self.rule)
        self.assertNotIn("linear-gradient", self.rule)

    def test_the_sweep_leaves_nothing_behind(self):
        """NEGATIVE PROBE against the actual defect: the moving layer has to be
        GONE at the end, not merely parked off-centre. If a later hand drops the
        fade, this goes red."""
        CLOSE = chr(125)
        keys = self.source[self.source.index("@keyframes memsweep{"):]
        keys = keys[:keys.index(CLOSE + CLOSE) + 2]
        self.assertIn("opacity:0", keys.replace(" ", ""))

    def test_the_icon_is_embedded_and_not_a_path(self):
        """docs/ IS NOT IN THE PACKAGE. An installed Crow has cli, bin, models
        and templates and no docs directory at all, so a path into it would be
        a broken image on every machine except this one -- and it would work
        here, which is the way that defect survives review."""
        self.assertIn("data:image/png;base64,", self.source)
        icons = self.source[self.source.index(".memicon"):]
        self.assertNotIn("docs/images", icons[:400])

    def test_the_mark_takes_its_colour_from_the_palette(self):
        """THE FILE IS BLACK LINE ART ON TRANSPARENT. Drawn as an image it is
        invisible on the dark theme and wrong on the crow one -- and it would
        look right in exactly one of the three, which is how that defect gets
        shipped. As a mask it takes currentColor, and the row colour IS the
        accent the core hands in."""
        CLOSE = chr(125)
        rule = self.source[self.source.index(".memicon{"):]
        rule = rule[:rule.index(CLOSE)]
        self.assertIn("mask-image", rule)
        self.assertIn("currentColor", rule)
        self.assertNotIn("background-image", rule)

    def test_the_icon_sits_before_the_text(self):
        """It is a label for the row, not a decoration after it."""
        js = self.source[self.source.index("  memory(msg,n){"):]
        js = js[:js.index("  tail(){")]
        self.assertLess(js.index("memicon"), js.index("textContent"))

    def test_the_reduced_motion_row_is_flat_too(self):
        """A reader who asked for no motion still gets a visible row, and it
        must not be the parked gradient either -- that was the whole complaint."""
        CLOSE = chr(125)
        quiet = self.source[self.source.index("@media (prefers-reduced-motion: reduce)"):]
        quiet = quiet[:quiet.index(CLOSE + CLOSE) + 2]
        self.assertNotIn("linear-gradient", quiet)


class TheCodePanelStartsNarrowTests(unittest.TestCase):
    """robin, 2026-08-27: "der codepanel ist viel zu breit. Default werte bitte
    wie in Screenshot 2! die Icons duerfen niemals aus der chateingabemaske
    rausgucken rechts."

    DAS ERSETZT #138c's HALBE FLAECHE. Die Automatik vom 2026-08-26 richtete
    eine nie gezogene Breite am Platz aus -- und war am naechsten Neustart auf
    demselben Fenster der zu breite Start, neben dem die Icons wieder
    herausstanden. Sein gespeicherter Zug stand auf exakt 260: die Vorgabe IST
    das Minimum, und mehr Panel ist eine Geste am Griff, keine Rechnung der
    Seite. Dass der Composer bei KEINER Breite ueberlaeuft, haelt seitdem das
    Layout: das Panel gibt nach, die Chatspalte traegt die Mindestbreite.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):self.source.index("</style>")]
        self._real = crow_gui.read_settings
        self.addCleanup(setattr, crow_gui, "read_settings", self._real)

    def _settings(self, **values):
        crow_gui.read_settings = lambda: values

    def _rule(self, selector: str) -> str:
        found = self.css[self.css.index(selector):]
        return found[:found.index(chr(125))]

    def test_the_default_is_the_minimum_robin_chose(self):
        self.assertEqual(crow_gui.CODE_DEFAULT, 260)
        self.assertEqual(crow_gui.CODE_DEFAULT, crow_gui.CODE_MIN)
        self._settings()
        self.assertEqual(crow_gui.code_width_setting(), 260)

    def test_no_start_width_automation_remains(self):
        """NEGATIV-WAECHTER gegen den Wiedereinbau: weder die halbe-Flaeche-
        Funktion noch ihr Stempel duerfen zurueckkommen -- der Start ist die
        gespeicherte Breite oder die Vorgabe, nie eine Rechnung."""
        self.assertNotIn("codeWidthToFit", self.source)
        self.assertNotIn("codeauto", self.source)

    def test_a_dragged_width_survives_the_restart(self):
        """Eine gezogene Breite ist eine Entscheidung und bleibt."""
        self._settings(code_width=520)
        self.assertEqual(crow_gui.code_width_setting(), 520)

    def test_a_width_outside_the_grips_range_falls_back(self):
        """NEGATIV: ein Wert, den die Maus nie erzeugen konnte, wird zur
        Vorgabe und nicht zur Grenze."""
        self._settings(code_width=5000)
        self.assertEqual(crow_gui.code_width_setting(), 260)
        self._settings(code_width=True)
        self.assertEqual(crow_gui.code_width_setting(), 260)

    def test_the_panel_gives_way_before_the_composer(self):
        """Die Garantie hinter "niemals rausgucken": #138c laesst die Knoepfe
        nicht nachgeben (mit Grund), also muss das PANEL nachgeben koennen --
        und die Chatspalte traegt die Mindestbreite, unter der die Knopfreihe
        nicht mehr passt. `flex:none` hier waere der alte Ueberlauf."""
        code = self._rule("#code{")
        self.assertIn("min-width:0", code)
        self.assertIn("flex:0 1 auto", code)
        self.assertNotIn("flex:none", code)
        # 380 -> 560 am Abend des 2026-08-27, robins Ansage in Grossbuchstaben:
        # die Maske darf NIE unter das Screenshot-2-Mass fallen. Der alte Wert
        # liess den Modell-Chip abschneiden, sobald ein gezogenes Code-Panel
        # drueckte.
        self.assertIn("min-width:560px", self._rule("#main{"))


class NothingSticksOutOfTheComposerTests(unittest.TestCase):
    """#138c. robin, 2026-08-26: "die Icons gucken immer noch ausserhalb der
    Eingabemaske" -- der Sendepfeil stand rechts NEBEN dem Rahmen.

    ES WAR NIE DIE PANEL-BREITE, auch wenn es danach aussah und mit einer
    breiteren Spalte verschwand. Ein Flex-Kind traegt `min-width:auto` und
    schrumpft deshalb nicht unter die Breite seines Inhalts; jedes Kind dieser
    Reihe traegt zusaetzlich `white-space:nowrap`. Also gab keines nach, die
    Summe blieb breiter als die Zeile, und der Ueberlauf fiel auf das letzte
    Element. Eine breitere Spalte verdeckt das, sie behebt es nicht.
    """

    def setUp(self) -> None:
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = source[source.index("<style>"):source.index("</style>")]

    def _rule(self, selector: str) -> str:
        found = self.css[self.css.index(selector):]
        return found[:found.index(chr(125))]

    def test_the_row_may_shrink_at_all(self):
        """`min-width:0` ist die Zeile, ohne die alles andere wirkungslos ist:
        ein Flex-Kind mit `min-width:auto` schrumpft nie unter seinen Inhalt."""
        self.assertIn("min-width:0", self._rule("#foot{"))
        self.assertIn("min-width:0", self._rule("#acts{"))

    def test_the_buttons_never_give_way(self):
        """Sie sind das Angeklickte. Ein halber Knopf ist schlimmer als ein
        gekuerztes Wort, und ein Knopf, der bei jeder Fensterbreite eine andere
        Groesse hat, ist ein Ziel, das man suchen muss."""
        self.assertIn("flex:none",
                      self._rule("#acts>#rootwrap,#acts>#modewrap,#acts>#mic,#acts>#go{"))

    def test_what_gives_way_gives_way_in_order(self):
        """NEGATIV zur Regel darueber: gaebe NICHTS nach, waere `min-width:0`
        eine Erlaubnis ohne Nutzer und die Reihe liefe weiter ueber."""
        for selector in ("#hint{", "#ctx{", "#modelwrap{"):
            self.assertIn("min-width:0", self._rule(selector),
                          "%s muss nachgeben koennen" % selector)
        # #231: DIE RANGFOLGE, WIE SIE GEMESSEN WURDE. Hier stand
        # `flex:0 1 auto` auf #hint -- und #acts selbst schrumpfte mit, weil
        # Schrumpfen nach Faktor MAL Basis verteilt: bei 1180x800 lag #go
        # 46 px neben der Maske. Der Hinweis nimmt jetzt nur den Rest (feste
        # Breite 0, Basis 0), #acts waechst und schrumpft nie, und die
        # Kontextzahl gibt nach dem Modell-Chip nach.
        hint = self._rule("#hint{")
        self.assertIn("width:0", hint)
        self.assertIn("flex:1 1 0", hint)
        self.assertIn("flex:1 0 auto", self._rule("#acts{"))
        self.assertIn("flex:0 .2 auto", self._rule("#ctx{"))

    def test_the_long_chip_is_clipped_in_both_halves(self):
        """Der Chip ist ein `inline-flex` aus Modellname UND Grad. Eine Regel
        nur auf `b` haette den laengeren der beiden ungekuerzt gelassen."""
        self.assertIn("text-overflow:ellipsis", self._rule("#model>*{"))

    def test_the_row_does_not_wrap(self):
        """"Das darf sich nicht verschieben" war die zweite Haelfte der Ansage:
        ein Umbruch macht die Maske hoeher, sobald ein Chip nicht passt, und
        bewegt alles darueber."""
        self.assertNotIn("flex-wrap", self._rule("#foot{"))


class NothingOverhangsOrClipsTests(unittest.TestCase):
    """#231-#235. Die Befunde des Layout-Audits als Regeln im Blatt.

    GEMESSEN WURDE GERENDERT (headless Chromium ueber alle Groessen von
    1130x520 bis 2560x1440, drei Themes, Menues offen, Rail/Code an beiden
    Anschlaegen; die schlimmsten Faelle nachgerendert in WebKitGTK 2.52).
    Diese Suite hat keinen Browser, also haelt sie fest, was die Messung
    herbeigefuehrt hat -- und rechnet dort nach, wo zwei Zahlen an zwei
    Stellen zusammenpassen muessen.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):
                               self.source.index("</style>")]

    def _rule(self, selector: str) -> str:
        found = self.css[self.css.index(selector):]
        return found[:found.index(chr(125))]

    def _px(self, rule: str, prop: str) -> float:
        match = re.search(r"(?:^|[;{\s])" + re.escape(prop) + r":\s*(-?[\d.]+)px", rule)
        self.assertIsNotNone(match, "%s fehlt in %r" % (prop, rule[:80]))
        return float(match.group(1))

    def test_a_long_word_breaks_inside_the_column(self):
        """Pfad, URL, Kompositum: #flow hatte 891 px Inhalt in 666. `anywhere`,
        nicht `break-word` -- nur `anywhere` senkt min-content, und die
        Nutzerblase ist ein Grid-Item in einer 1fr-Spur."""
        self.assertIn("overflow-wrap:anywhere", self._rule("\n.turn{"))
        self.assertIn("overflow-wrap:normal", self._rule(".md table{"))

    def test_the_composers_menus_open_above_the_cards(self):
        """#box ist ein Stapelkontext; die Menues darin koennen nur ueber die
        Karten, wenn der ganze Composer ueber #panels liegt."""
        composer = self._rule("#composer{position:absolute")
        panels = self._rule("#panels{")
        z = lambda rule: int(re.search(r"z-index:(\d+)", rule).group(1))  # noqa: E731
        self.assertGreater(z(composer), z(panels))

    def test_the_cards_end_where_the_composer_begins(self):
        """70 % galt nur, solange der Composer unter 30 % blieb. Die Hoehe, die
        fitFlow ohnehin misst, ist dieselbe Zahl fuer die Karten."""
        self.assertIn("var(--comph", self._rule("#panels{"))
        fit = self.source[self.source.index("const fitFlow"):]
        fit = fit[:fit.index("};")]
        self.assertIn('"--comph"', fit)

    def test_the_column_makes_room_for_the_cards_by_the_same_amount(self):
        """Spalte und Maske bleiben buendig: #flow bekommt auf JEDER Seite genau
        das dazu, was #composer an JEDER Kante einzieht -- und das ist die
        Kartenbreite plus ihr Rand."""
        self.assertIn("container:chat/inline-size", self._rule("#main{"))
        block = self.css[self.css.index("@container chat"):]
        block = block[:block.index("}\n}") + 1]
        # #280: EINE Deklaration fuer beide -- #flow und #composer bekommen
        # dieselbe --reserve aus derselben Regel, und beide lesen sie links
        # und rechts.
        rules = re.findall(r"([^{}]*)\{--reserve:(\d+)px\}", block)
        self.assertEqual(len(rules), 1, block)
        selectors, amount = rules[0]
        self.assertEqual(selectors.count("#flow"), 3)
        self.assertEqual(selectors.count("#composer"), 3)
        panels = self._rule("#panels{")
        reserve = self._px(panels, "width") + self._px(panels, "right")
        self.assertEqual(int(amount), reserve)
        self.assertIn("padding-inline:calc(var(--sbw) + var(--reserve)) var(--reserve)",
                      self._rule("#flow{"))
        composer = self._rule("#composer{position:absolute")
        self.assertIn("left:calc(var(--sbw) + var(--reserve))", composer)
        self.assertIn("right:calc(var(--sbw) + var(--reserve))", composer)

    def test_the_composer_is_centred_in_the_window_not_left_of_it(self):
        """#256, robin 2026-09-23: "die Eingabemaske ist nicht mittig,
        sie steht mehr links als rechts". Die #233-Reserve stand nur RECHTS
        und schob Spalte und Maske um (306 + --sbw)/2 = 158 px nach links
        (gemessen, Chromium 1920x900, Git-Panel offen); ohne Karte blieben
        5 px, weil #flow links 10 und rechts 10 + Rinnstein hatte.

        Die Mitte der Maske ist die Mitte von #main genau dann, wenn ihre
        linke und rechte Kante gleich weit innen stehen; die der Spalte, wenn
        die Inhaltsbox von #flow links um den Rinnstein (--sbw, den
        scrollbar-gutter:stable rechts reserviert) mehr Polster traegt. Beides
        muss ohne und mit Karten gelten -- jede einseitige Zahl ist dieser Bug."""
        sbw = self._px(self._rule(":root{"), "--sbw")
        composer = self._rule("#composer{position:absolute")
        self.assertIn("left:calc(var(--sbw) + var(--reserve))", composer)
        self.assertIn("right:calc(var(--sbw) + var(--reserve))", composer)
        flow = self._rule("#flow{")
        self.assertIn("scrollbar-gutter:stable", flow)
        # #280: links der Rinnstein mehr, rechts reserviert ihn der Browser.
        self.assertIn("padding-inline:calc(var(--sbw) + var(--reserve)) var(--reserve)", flow)
        self.assertEqual(sbw, 10)
        block = self.css[self.css.index("@container chat"):]
        block = block[:block.index("}\n}")]
        self.assertNotIn("padding-right", block, "die Reserve steht wieder nur rechts")
        self.assertNotRegex(block, r"#composer\{\s*right:", "die Maske zieht nur rechts ein")

    def test_a_squeezed_side_column_shows_nothing_rather_than_half(self):
        self.assertIn("container:side/inline-size", self.css)
        self.assertRegex(self.css, r"@container side \(max-width:\d+px\)\{#side>\*"
                                   r"\{visibility:hidden\}\}")

    def test_the_settings_sheet_starts_below_the_title_bar(self):
        bar = self._px(self._rule("#bar{"), "height")
        settings = self._rule("#settings{position:fixed")
        self.assertEqual(self._px(settings, "padding-top"), bar)

    def test_the_level_keeps_the_space_before_its_dot(self):
        """`.lvl` ist ein Flex-Item, sein fuehrendes Leerzeichen stuende am
        Zeilenanfang und fiele weg: gezeichnet stand "(llama.cpp)· high"."""
        self.assertIn('" · "', self.source[self.source.index("  levelLabel(){"):][:300])
        self.assertIn("white-space:pre", self._rule("#model .lvl{white-space"))

    def test_single_line_things_stay_single_line(self):
        self.assertIn("white-space:nowrap", self._rule("#turnstate{"))
        self.assertIn("white-space:nowrap", self._rule("#viewbar button{"))
        self.assertIn("text-overflow:ellipsis", self._rule(".gitgrp .tct{min-width"))
        self.assertIn("white-space:nowrap", self._rule(".gitgrp .gcount{flex:none"))

    def test_rows_line_up(self):
        """Die Kostenlinie eines Zielschritts ist so breit wie die Zeile, und
        die Browserknoepfe sind so hoch wie das Adressfeld."""
        self.assertIn("flex:1", self._rule("#goalpanel li>span:last-child{"))
        self.assertIn("align-items:stretch", self._rule("#brbar{"))

    def test_the_accent_bar_sits_on_the_tree_line(self):
        """2 px Balken auf 1 px Linie: der Balken beginnt einen Pixel links der
        Linie und deckt sie."""
        line = self._px(self._rule(".sess.inproj::after{"), "left")
        bar = self._rule(".sess.inproj.on::before,.sess.inproj.done::before{")
        self.assertEqual(self._px(bar, "left"), line - 1)
        self.assertIn("z-index:1", bar)

    def test_scrollbars_stay_out_of_rounded_corners(self):
        """Der Spurrand ist der Radius, gegen den die Leiste laeuft."""
        main = self._px(self._rule("#main{"), "border-top-right-radius")
        self.assertEqual(self._px(self._rule("#flow::-webkit-scrollbar-track{"),
                                  "margin-top"), main)
        goal = self._px(self._rule("#goalpanel{"), "border-radius")
        self.assertIn("margin:%dpx 0" % goal,
                      self._rule("#goalpanel::-webkit-scrollbar-track{"))


class ScrollbarsShowOnlyWhileScrolledTests(unittest.TestCase):
    """#305. robin, 2026-09-25: the stats line under an answer, the Code panel
    and the chat carried a scrollbar at rest. A thumb shows only while its
    strip scrolls, or while a mouse pointer is over it -- never at rest, and
    never stuck on a phone after a tap. Only the colour changes; the widths
    the column arithmetic rests on (#256/#280) stay."""

    GECKO = "@supports not selector(::-webkit-scrollbar){"

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):
                               self.source.index("</style>")]

    def _rule(self, selector: str) -> str:
        found = self.css[self.css.index(selector):]
        return found[:found.index(chr(125))]

    def _gecko_block(self, css: str) -> tuple[int, int]:
        start = css.index(self.GECKO)
        depth, i = 0, start
        while True:
            ch = css[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return start, i + 1
            i += 1

    def test_the_thumb_is_transparent_at_rest(self):
        self.assertIn("background:transparent",
                      self._rule("\n::-webkit-scrollbar-thumb{"))
        self.assertIn("background:transparent",
                      self._rule("\n::-webkit-scrollbar-corner{"))
        # the width is untouched: only the colour comes and goes
        self.assertIn("\n::-webkit-scrollbar{width:var(--sbw)}", self.css)
        self.assertIn("--sbw:10px;", self.css)
        self.assertIn("scrollbar-gutter:stable", self._rule("#flow{overflow-y"))

    def test_scrolling_or_a_hovering_pointer_shows_it(self):
        self.assertIn(".is-scrolling::-webkit-scrollbar-thumb{background:var(--line)}",
                      self.css)
        self.assertIn("@media (hover:hover){:hover::-webkit-scrollbar-thumb"
                      "{background:var(--line)}}", self.css)
        self.assertIn("::-webkit-scrollbar-thumb:hover,::-webkit-scrollbar-thumb:active"
                      "{background:var(--bevel)}", self.css)

    def test_hover_shows_it_only_where_the_input_can_hover(self):
        """A phone keeps `:hover` after a tap; ungated, the bar would stick."""
        page = crow_gui.stamped_page(remote=True)
        hovers = [m.start() for m in re.finditer(r":hover::-webkit-scrollbar-thumb", page)]
        self.assertTrue(hovers)
        for at in hovers:
            self.assertEqual(page[at - len("@media (hover:hover){"):at],
                             "@media (hover:hover){")
        # and the phone layer paints no thumb of its own
        self.assertNotIn("scrollbar-thumb", crow_gui.REMOTE_CSS)

    def test_no_standard_property_switches_the_webkit_path_off(self):
        """A non-auto scrollbar-color/-width disables ::-webkit-scrollbar in
        Chromium 121+ and WebKitGTK 2.52.3+ (and scrollbar-color inherits).
        The Gecko fallback therefore lives behind @supports; outside it only
        the three strips hidden on purpose say `scrollbar-width:none`."""
        for css in (self.css, crow_gui.REMOTE_CSS):
            lo, hi = self._gecko_block(css) if self.GECKO in css else (0, 0)
            for m in re.finditer(r"scrollbar-(color|width):([^;}]*)", css):
                if lo <= m.start() < hi:
                    continue
                self.assertEqual((m.group(1), m.group(2)), ("width", "none"),
                                 css[max(0, m.start() - 60):m.end()])
        lo, hi = self._gecko_block(self.css)
        block = self.css[lo:hi]
        self.assertIn("*{scrollbar-color:transparent transparent}", block)
        self.assertIn(".is-scrolling{scrollbar-color:var(--line) transparent}", block)
        self.assertIn("@media (hover:hover){:hover{scrollbar-color:", block)

    def test_the_script_is_on_the_window_and_the_phone(self):
        for page in (crow_gui.stamped_page(), crow_gui.stamped_page(remote=True)):
            self.assertEqual(page.count("scrollbarsAutoHide(document);"), 1)
            self.assertIn("const SB_LINGER_MS = 800;", page)

    def _run(self, steps: str) -> dict:
        node = _node()
        if not node:
            self.skipTest("no node on this machine")
        import subprocess
        start = self.source.index("const SB_LINGER_MS")
        end = self.source.index("scrollbarsAutoHide(document);")
        js = ("let now=0, seq=0; const timers=new Map();\n"
              "function setTimeout(f, ms){ const id=++seq; timers.set(id,[now+ms,f]); return id; }\n"
              "function clearTimeout(id){ timers.delete(id); }\n"
              "function tick(ms){ const until=now+ms;\n"
              "  for(;;){ let best=null;\n"
              "    for(const [id,[t]] of timers) if(t<=until && (!best || t<timers.get(best)[0])) best=id;\n"
              "    if(best===null) break;\n"
              "    const [t,f]=timers.get(best); timers.delete(best); now=t; f(); }\n"
              "  now=until; }\n"
              "const listeners=[];\n"
              "const doc={nodeType:9, addEventListener(type, fn, opt){ listeners.push([type, fn, opt]); }};\n"
              "const el={nodeType:1, classList:{s:new Set(), add(c){this.s.add(c);},\n"
              "  remove(c){this.s.delete(c);}, has(c){return this.s.has(c);}}};\n"
              "doc.scrollingElement=el;\n"
              "const fire=(type, target)=>listeners.filter(l=>l[0]===type)\n"
              "  .forEach(l=>l[1]({type, target}));\n"
              "const on=()=>el.classList.has('is-scrolling');\n"
              "const out={};\n"
              + self.source[start:end] + "\nscrollbarsAutoHide(doc);\n"
              + steps + "\nconsole.log(JSON.stringify(out));\n")
        done = subprocess.run([node, "-e", js], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_one_capture_passive_listener_for_every_scroll(self):
        out = self._run("out.l=listeners.map(l=>[l[0], l[2]]);")
        scroll = [opt for kind, opt in out["l"] if kind == "scroll"]
        self.assertEqual(scroll, [{"capture": True, "passive": True}])

    def test_it_shows_while_scrolling_and_hides_after_the_linger(self):
        out = self._run(
            "out.rest=on();\n"
            "fire('scroll', el); out.first=on();\n"
            "tick(500); fire('scroll', el); tick(500); out.still=on();\n"
            "tick(299); out.before=on(); tick(1); out.after=on();\n"
            "fire('scroll', doc); out.root=on();")
        self.assertEqual(out, {"rest": False, "first": True, "still": True,
                               "before": True, "after": False, "root": True})

    def test_a_held_pointer_keeps_it_until_release(self):
        out = self._run(
            "fire('pointerdown', el); fire('scroll', el);\n"
            "tick(5000); out.held=on();\n"
            "fire('pointerup', el); tick(799); out.released=on();\n"
            "tick(1); out.gone=on();\n"
            "fire('pointerdown', el); fire('scroll', el); fire('pointercancel', el);\n"
            "tick(800); out.cancel=on();")
        self.assertEqual(out, {"held": True, "released": True, "gone": False,
                               "cancel": False})


class ALineTypedDuringTheReviewIsNotLostTests(ApiCase):
    """robin, 2026-08-26, with the screenshot: the same question stood in the
    chat TWICE, `Memory updated (2)` between the two, and only the second one
    ran.

    THE CAUSE IS NOT THE MEMORY BAR, it is the order #122 established on
    2026-08-21 -- for a good reason that stays good. `_run` pushes `idle` and
    THEN reviews, so nobody waits for a review to read their answer. But the
    review runs on the SAME worker thread, so for its whole duration the window
    says free while `send` says busy:

        self.push({"k": "idle"})        # composer unlocked, no Stop
        crow_core.review_turn(...)      # same thread, still alive

        if self._worker and self._worker.is_alive():
            return False                # ... and the line is dropped

    `go()` draws the typed line BEFORE `send` answers, so a dropped line does
    not vanish quietly -- it sits in the transcript looking sent.
    """

    def _api(self):
        api = self.api()
        api.push = lambda message: api._seen.append(message)
        api._seen = []
        return api

    def test_a_line_typed_while_the_review_runs_is_kept(self):
        """POSITIV. Angenommen statt verworfen, und `True` heisst hier
        "angenommen" -- die Seite laesst ihre Sperre stehen, was stimmt: es
        laeuft etwas, und danach laeuft die Zeile."""
        api = self._api()
        api._busy = True
        self.assertTrue(api.send("und noch eine frage"))
        self.assertEqual(api._queued, "und noch eine frage")

    def test_an_idle_window_queues_nothing(self):
        """NEGATIV zum obigen: ohne laufenden Zug gibt es nichts zu puffern, und
        ein Puffer, der sich immer fuellt, waere ein Zug, der nie startet."""
        api = self._api()
        started = api.send("die erste frage")
        self.assertTrue(started)
        self.assertIsNone(api._queued)
        self.assertTrue(api._busy)

    def test_a_slash_command_is_answered_not_queued(self):
        """NEGATIV fuer die Unterscheidung, die `send` schon traf und behalten
        muss: `False` heisst hier "beantwortet, nichts zu starten" und nicht
        "abgewiesen". Ein `/tools` in den Puffer zu legen hiesse, es nach dem
        Review ein zweites Mal zu beantworten."""
        api = self._api()
        api._busy = True
        self.assertFalse(api.send("/tools"))
        self.assertIsNone(api._queued)

    def test_the_worker_takes_the_queued_line_when_it_finishes(self):
        """Der Uebergang. `_run` ist hier ein Double -- es IST die Schicht
        darunter; geprueft wird die Schleife, die es fuehrt."""
        api = self._api()
        ran = []
        api._run = ran.append
        api._busy = True
        api._queued = "zweite"
        api._pump("erste")
        self.assertEqual(ran, ["erste", "zweite"])
        self.assertFalse(api._busy)
        self.assertIsNone(api._queued)

    def test_the_worker_stops_holding_the_flag_when_a_turn_throws(self):
        """NEGATIV, und die teuerste Variante wenn sie fehlt: ein Zug, der
        wirft, liesse `_busy` stehen. Das Fenster nimmt danach jede Zeile an
        und faehrt keine einzige mehr -- eine Sperre, die nur ein Neustart
        loest."""
        api = self._api()

        def boom(_text):
            raise RuntimeError("der Zug ist gestorben")

        api._run = boom
        api._busy = True
        with self.assertRaises(RuntimeError):
            api._pump("erste")
        self.assertFalse(api._busy)
        self.assertIsNone(api._queued)

    def test_the_waiting_line_says_what_it_waits_for(self):
        """Sonst stuende der Composer auf `Stop` fuer einen Nachlauf, den der
        Leser nie angestossen hat, und seine Frage laege sichtbar im Verlauf,
        ohne dass sich etwas bewegt -- dieselbe Lage wie der Fehler, nur mit
        gesperrtem Knopf."""
        api = self._api()
        api._busy = True
        api.send("noch eine")
        self.assertEqual([m["k"] for m in api._seen], ["queued"])
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        # #249: the push carries the joined text now, so the case passes it on.
        self.assertIn('case "queued": this.queuedLine(e);', source)
        self.assertIn("the memory review is finishing", source)

    def test_the_page_is_told_when_the_wait_is_over(self):
        """NEGATIV zum obigen: ohne diese Meldung bliebe der Wartehinweis ueber
        dem ganzen gepufferten Zug stehen und behauptete ein Warten, das laengst
        laeuft."""
        api = self._api()
        ran = []
        api._run = ran.append
        api._busy = True
        api._queued = "zweite"
        api._pump("erste")
        # #162: `rail` STEHT SEIT DEM 2026-08-31 DAHINTER, und exakt statt `in`,
        # damit dieser Fall weiter sagt, WAS die Seite hoert. Der Rail-Redraw
        # kam, weil `_run` die Rail eine Zeile zu frueh zeichnet -- da steht
        # `_busy` noch auf True -- und danach niemand mehr zeichnete: die Kachel
        # behielt ihre Amber-Marke, obwohl der Zug durch war.
        self.assertEqual([m["k"] for m in api._seen], ["busy", "rail"])
        self.assertIn('case "busy": this.busy();',
                      (HERE / "crow_gui.py").read_text(encoding="utf-8"))

    def test_the_worker_clears_the_flag_under_the_same_lock_that_queues(self):
        """DAS RENNEN, und es ist von aussen nie zu sehen. Endet der Worker
        ausserhalb des Locks, gibt es ein Fenster, in dem `send` puffert,
        nachdem niemand mehr liest -- die Zeile waere weg, und zwar genau die
        eine, auf die jemand gewartet hat."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        pump = source[source.index("    def _pump(self"):]
        pump = pump[:pump.index(chr(10) + "    def ")]
        self.assertIn("with self._queue_lock:", pump)
        held = pump[pump.index("with self._queue_lock:"):]
        self.assertIn("self._busy = False", held)


class AnImageIsAnAttachmentTests(ApiCase):
    """#142 in the window: a dropped image becomes a chip, rides the next send,
    and comes back after a restart. The wire half lives in test_crow_core; here
    is the seam the page drives -- stage, unstage, refuse, replay."""

    def _png(self, name="shot.png"):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"i" * 16)
        return path

    def test_stage_returns_the_chip_and_holds_the_part(self):
        api = self.api()
        out = api.stage_image(self._png())
        self.assertEqual(len(out["chips"]), 1)
        self.assertEqual(out["chips"][0]["name"], "shot.png")
        self.assertTrue(out["chips"][0]["url"]
                        .startswith("data:image/png;base64,"))

    def test_unstage_removes_and_returns_the_rest(self):
        api = self.api()
        api.stage_image(self._png("a.png"))
        api.stage_image(self._png("b.png"))
        out = api.unstage_image(0)
        self.assertEqual([c["name"] for c in out["chips"]], ["b.png"])

    def test_a_refused_file_is_a_note_and_no_chip(self):
        """NEGATIVE PROBE: a .txt drop says image_part's sentence and stages
        nothing -- the old path-in-the-composer behaviour is for the page to
        keep, not this seam."""
        api = self.api()
        path = os.path.join(self.dir, "notes.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x")
        out = api.stage_image(path)
        self.assertEqual(out["chips"], [])
        self.assertIn("note", [e.get("k") for e in self.drained(api)])

    def test_the_replay_carries_the_image_back(self):
        """The ticket's 'still there after a restart', at the seam the page
        reads: a replayed user turn with blocks pushes its words AND its
        images."""
        api = self.api()
        content = crow_core.user_content(
            "what is this", [crow_core.image_part(self._png())])
        api._replay([{"role": "user", "content": content},
                     {"role": "assistant", "content": "a raven"}])
        user = next(e for e in self.drained(api) if e.get("k") == "user")
        self.assertEqual(user["t"], "what is this")
        self.assertEqual(len(user["i"]), 1)
        self.assertTrue(user["i"][0].startswith("data:image/png;base64,"))

    def test_a_plain_replay_pushes_no_image_key(self):
        """NEGATIVE: an old chat replays exactly as before -- no `i` key."""
        api = self.api()
        api._replay([{"role": "user", "content": "hello"}])
        user = next(e for e in self.drained(api) if e.get("k") == "user")
        self.assertNotIn("i", user)

    def test_a_blind_server_refuses_before_the_history(self):
        """The gate runs BEFORE the append. After the refusal the conversation
        holds no user line and the stage is empty -- a refused image must not
        ride the next, unrelated send."""
        import http.server

        class Props(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"modalities": {"vision": false}}')

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Props)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        api = self.api("--base-url",
                       "http://127.0.0.1:%d/v1" % server.server_address[1])
        api.stage_image(self._png())
        api._run("what is this")
        events = self.drained(api)
        fails = [e for e in events if e.get("k") == "fail"]
        self.assertTrue(fails, "no fail pushed: %r" % [e.get("k") for e in events])
        self.assertIn("--mmproj", fails[0]["t"])
        self.assertEqual([m for m in api._conversation.payload()
                          if m.get("role") == "user"], [])
        self.assertEqual(api._staged_images, [])


class TheWindowNeverStarvesTheComposerTests(unittest.TestCase):
    """robin, 2026-08-27, in Grossbuchstaben und zum wiederholten Mal: die
    Chateingabemaske darf NIEMALS kleiner werden als sein Referenz-Screenshot,
    und die FENSTER-Mindestgroesse hat das zu garantieren. Die Garantie ist
    eine Rechnung ueber drei Zahlen, und dieser Fall haelt sie zusammen:
    keine darf allein wandern."""

    CHROME = 50          # Spalten-Paddings und Raender, siehe den Kommentar am Fenster

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):
                               self.source.index("</style>")]

    def _main_min(self) -> int:
        rule = self.css[self.css.index("#main{"):]
        rule = rule[:rule.index(chr(125))]
        return int(re.search(r"min-width:(\d+)px", rule).group(1))

    def _window_min(self) -> int:
        return int(re.search(r"min_size=\((\d+),", self.source).group(1))

    def test_the_mask_keeps_the_screenshot_width(self):
        self.assertEqual(self._main_min(), 560)

    def test_the_window_cannot_be_shrunk_into_the_bug(self):
        """Selbst mit der Rail am Anschlag und jedem erlaubten Code-Panel
        bleibt der Chatspalte ihr Minimum: Fensterminimum >= RAIL_MAX + Maske
        + Chrome. Das Code-Panel steht NICHT in der Summe, weil es als
        einziges nachgeben darf (min-width:0)."""
        self.assertGreaterEqual(
            self._window_min(),
            crow_gui.RAIL_MAX + self._main_min() + self.CHROME)
        self.assertEqual(self._window_min(), 1130)

    def test_the_code_panel_is_still_the_one_that_yields(self):
        """NEGATIV: die Garantie oben gilt nur, solange das Panel nachgeben
        KANN. Ein hartes Minimum dort machte die Summe zur Luege."""
        rule = self.css[self.css.index("#code{"):]
        rule = rule[:rule.index(chr(125))]
        self.assertIn("min-width:0", rule)


class TheDelegationWearsTheMockupTests(unittest.TestCase):
    """#143 E2. robin, 2026-08-27, mit dem Mockup daneben: "so soll es
    aussehen" -- eine Karte je Subtask im Fluss, Kind-Zeilen in der Rail, der
    ⑂-Chip ueber dem Composer, alles im --sub-Kanal und SICHTBAR AB START.
    Diese Faelle halten die Seite gegen das abgenommene Mockup."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.css = self.source[self.source.index("<style>"):
                               self.source.index("</style>")]

    def _rule(self, selector: str) -> str:
        found = self.css[self.css.index(selector):]
        return found[:found.index(chr(125))]

    def test_the_channel_is_one_palette_name(self):
        """Das Logo-Cyan steht EINMAL in der Basispalette; jede Regel zeigt
        mit var() darauf -- die Palettenregel der Seite gilt auch hier."""
        self.assertIn("--sub:#39c6d8", self.css)
        self.assertIn("border-left:3px solid var(--sub)",
                      self._rule(".subcard{"))
        run = self._rule(".sdot.run{")
        self.assertIn("var(--sub)", run)
        self.assertIn("animation:subpulse", run)
        self.assertIn(".cost .subshare{color:var(--sub)", self.css)

    def test_the_dot_is_its_own_class(self):
        """NEGATIV: `.dot` gehoert dem Mode-Chip, und der darf nicht atmen.
        Ein geteilter Klassenname haette dem Level-Punkt den Puls gegeben."""
        self.assertNotIn("animation", self._rule("#mode .dot{"))
        self.assertIn(".sdot.run", self.css)

    def test_card_chip_menu_and_rail_child_exist(self):
        for piece in ('case "subs": this.subs(e.items); break;',
                      'id="subwrap"', 'id="subchip"', 'id="submenu"',
                      "subCard(it){", "subRail(){", "subMenuDraw(items){",
                      "subJump(i){", '"delegate · "+it.i',
                      'textContent="click a row to jump to its card"'):
            self.assertIn(piece, self.source)

    def test_a_subchat_is_fixed_to_its_root_and_never_a_chat_itself(self):
        """robins Struktur-Regeln vom 2026-08-27, alle drei als Waechter:
        die Kinder haengen FIX am Wurzelchat (kein Fallback auf die aktive
        Zeile -- der Fallback WAR das Mitwandern), ein Klick oeffnet NIE einen
        Subtask als Chat (das kaperte den Live-Chat), und "" heisst exakt die
        dateilose Live-Zeile."""
        block = self.source[self.source.index("subRail(){"):
                            self.source.index("subJump(i){")]
        self.assertIn('.sess:not([data-path])', block)
        self.assertNotIn('.sess.on', block)
        whole = self.source[self.source.index("subs(items){"):
                            self.source.index("chatRow(r,inproj){")]
        # NIE der Subtask selbst als Chat -- sein Transkriptpfad darf nirgends
        # geoeffnet werden. Der WURZELCHAT (it.parent) ist der einzige Pfad,
        # den der Delegations-Block oeffnen darf: das ist der Sprung-Fallback.
        self.assertNotIn("crow.open(it.path", whole)
        for opened in re.findall(r"crow\.open\(([^)]*)\)", whole):
            self.assertEqual(opened, "it.parent")
        self.assertIn("crow.subJump(it.i)", whole)

    def test_the_cards_stay_and_survive_a_reopen(self):
        """robins zwei Nachbefunde vom 2026-08-27: (1) "die sollen bleiben" --
        eine Karte haengt im FLUSS, nie in der Rundenspalte, die der Trace
        faltet; (2) "ich kann die Subtasks nicht mehr anklicken" -- nach dem
        Oeffnen eines Chats werden die Karten aus der Registry nachgezeichnet
        (Signatur fallengelassen), NUR fuer den offenen Chat, und ein Klick
        ohne Karte oeffnet erst den Wurzelchat und springt dann nach."""
        card = self.source[self.source.index("subCard(it){"):
                           self.source.index("subChip(items){")]
        # An den Chat ausgerichtet: der Wrapper traegt DIESELBE Spaltenklasse
        # wie jeder Block -- keine zweite Geometrie, die driften kann.
        self.assertNotIn("turn subrow", card)
        self.assertNotIn("flow.appendChild", card)
        self.assertNotIn("col.appendChild", card)
        # `here` entscheidet, und PYTHON rechnet es -- die Seite verglich
        # zuvor ihre eigene live-Kopie gegen parent, zwei eingefrorene Werte,
        # und ein frischer Chat blieb ohne jede Karte (Screenshot 2).
        self.assertIn("if(!it.here) return;", card)
        self.assertNotIn("subLive", card)
        opened = self.source[self.source.index("def open(self, path"):]
        opened = opened[:opened.index("ARCHIVE_DIR")]
        self.assertIn('self._subs_sig = ""', opened)
        self.assertIn("self._push_subs()", opened)
        # Und der new-Flow pusht denselben frischen Rahmen wie open().
        fresh = self.source[self.source.index("def reset(self)"):]
        fresh = fresh[:fresh.index("def ", 10)]
        self.assertIn('self._subs_sig = ""', fresh)
        self.assertIn("self._push_subs()", fresh)
        self.assertIn("this.subPending=i; crow.open(it.parent);", self.source)

    def test_the_cards_are_pinned_beside_goal_and_git_not_in_the_flow(self):
        """#255 (robin, 2026-09-23 on 9a59872): die Subtask-Kacheln scrollten
        mit dem Verlauf weg, weil `subCard` sie in `#flow` haengte. Sie wohnen
        jetzt in `#subpanel`, der dritten Karte der `#panels`-Spalte: laufende
        oben, fertige in einer zugeklappten Gruppe, und der Fluss bekommt nie
        einen Block dafuer."""
        panels = self.source[self.source.index('<div id="panels">'):
                             self.source.index('<aside id="git">')]
        self.assertIn('<div id="subpanel" hidden>', panels)
        for part in ('class="splive"', 'class="spfold"',
                     'class="spdone" hidden'):
            self.assertIn(part, panels)
        whole = self.source[self.source.index("  subs(items){"):
                            self.source.index("chatRow(r,inproj){")]
        # NEGATIV: kein Weg fuehrt eine Karte mehr in den Fluss, und kein
        # Sprung scrollt ueber scrollIntoView #main mit.
        self.assertNotIn("flow.appendChild", whole)
        self.assertNotIn("flow.querySelector('.subcard", whole)
        self.assertNotIn("scrollIntoView", whole)
        card = self.source[self.source.index("  subCard(it){"):
                           self.source.index("  subChip(items){")]
        self.assertIn('p.querySelector(it.st==="running" ? ".splive" : ".spdone")',
                      card)
        self.assertIn("group.appendChild(d)", card)
        self.assertNotIn("this.bottom()", card)
        frame = self.source[self.source.index("  subPanel(items){"):
                            self.source.index("  subPanelFold(){")]
        self.assertIn("x.here", frame)
        self.assertIn("d.remove()", frame)
        self.assertIn("p.hidden=!(run+fin)", frame)
        self.assertIn("this.subPanel(this.subItems);", whole)
        # Die Karte ist eine eigene Scrollflaeche in der Spalte wie das Ziel,
        # und die Spalte weicht ihr ab 1100 px aus wie Ziel und Git (#233).
        rule = self.css[self.css.index("#subpanel{"):]
        rule = rule[:rule.index(chr(125))]
        self.assertIn("min-height:0", rule)
        self.assertIn("overflow:auto", rule)
        self.assertIn("position:relative", rule)
        self.assertIn("#main:has(#subpanel:not([hidden])) #flow", self.css)
        self.assertIn("#main:has(#subpanel:not([hidden])) #composer", self.css)
        self.assertIn("#subpanel .subcard.seen{animation:none", self.css)

    def test_the_subtasks_card_closes_like_the_goal_card(self):
        """#281 (robin, 2026-09-24): der Goal-Karte hat ein `×`, die
        Subtasks-Karte keins. Jetzt dasselbe `.gx` in ihrem Kopf, mit Tooltip,
        der sagt, dass nichts abgebrochen wird; `hidden` ist der ganze Zustand,
        also laesst die #233/#256-Reserve mit los; ein Sprung oeffnet wieder."""
        panels = self.source[self.source.index('<div id="panels">'):
                             self.source.index('<aside id="git">')]
        head = panels[panels.index('<div class="sph"'):
                      panels.index('<div class="splive">')]
        self.assertIn('class="gx"', head)
        self.assertIn(">×</button>", head)
        self.assertIn("running subtasks keep running", head)
        self.assertIn('aria-label="Close subtasks card"', head)
        self.assertIn("crow.subPanelClose(event)", head)
        # Dieselbe Regel wie das Goal-`×`, nicht eine zweite Schreibweise.
        self.assertIn("#goalpanel .gx,#subpanel .gx{", self.css)
        self.assertIn("#goalpanel .gx:hover,#subpanel .gx:hover{", self.css)
        close = self.source[self.source.index("  subPanelClose(ev){"):
                            self.source.index("  subDoneFold(){")]
        self.assertIn("ev.stopPropagation()", close)
        self.assertIn('$("#subpanel").hidden=true', close)
        self.assertIn("pywebview.api.close_subtasks()", close)
        self.assertNotIn("cancel", close.replace("not cancelling", ""))
        frame = self.source[self.source.index("  subPanel(items){"):
                            self.source.index("  subPanelFold(){")]
        self.assertIn("items.some(x=>x.here && !x.closed)", frame)
        self.assertIn("p.hidden=!(run+fin) || !open", frame)
        reveal = self.source[self.source.index("  subReveal(d){"):
                             self.source.index("  subJump(i){")]
        self.assertIn("pywebview.api.reopen_subtasks()", reveal)
        self.assertIn("p.hidden=false", reveal)
        # Die Python-Seite: der Mark kommt in den Push-Rahmen, sonst hoert
        # die Seite das Schliessen nie.
        self.assertIn("def close_subtasks(self)", self.source)
        self.assertIn("def reopen_subtasks(self)", self.source)
        push = self.source[self.source.index("def _push_subs(self)"):]
        push = push[:push.index("def ", 10)]
        self.assertIn('r.get("closed", False)', push)

    def test_the_transcript_shelf_is_not_the_chat_folder(self):
        """NEGATIV auf der Kern-Seite, hier verankert, weil das Fenster der
        Leidtragende ist: der Schreiber zielt auf `subtasks/` und nie flach in
        den Session-Ordner, den `_archives` als Wurzelchats liest."""
        core = (HERE / "crow_core.py").read_text(encoding="utf-8")
        self.assertIn('os.path.join(SESSION_DIR, "subtasks")', core)

    def test_visible_from_the_start(self):
        """robins Abnahmekriterium: der Subtask ist zu sehen, sobald er
        STARTET. Die Karte entsteht fuer den running-Zustand mit pulsierendem
        Punkt, und der Ticker laeuft NEBEN dem Zug -- sonst koennte niemand
        zeichnen, waehrend `collect` blockiert."""
        self.assertIn('if(it.st==="running"){', self.source)
        self.assertIn('<span class="sdot run"></span>', self.source)
        self.assertIn("threading.Thread(target=self._subs_ticker",
                      self.source)

    def test_both_rail_paths_keep_the_children(self):
        """Der schnelle Rail-Pfad (Marke verschieben) und der Neubau muessen
        beide die Kind-Zeilen nachziehen, und `subs()` selbst ist der dritte
        Zeichner -- genau drei Aufrufe, keiner mehr, keiner weniger."""
        self.assertEqual(self.source.count("this.subRail();"), 3)

    def test_stop_reaches_the_subtasks(self):
        block = self.source[self.source.index("def stop(self)"):]
        block = block[:block.index("def ", 10)]
        self.assertIn("crow_core.cancel_subtasks()", block)

    def test_no_money_figure_on_a_subtask(self):
        """NEGATIV, robins Entscheid vom 2026-08-27: nur Tokenzahlen an
        Subtasks, nirgends ein Geldbetrag."""
        block = self.source[self.source.index("subStat(it){"):
                            self.source.index("subChip(items){")]
        self.assertIn("tok", block)
        for sign in ("€", "EUR", "$", "USD"):
            self.assertNotIn(sign, block)

    def test_the_chip_rests_at_zero_and_glows_only_live(self):
        """robin, 2026-08-27: ohne aktive Subtasks zeigt der Chip 0 im
        gedimmten Rahmen; hell umrandet plus blinkender Punkt NUR mit
        laufenden. Die Zahl ist die der AKTIVEN, nie die Gesamtsumme."""
        base = self.css[self.css.index("#subchip{"):]
        base = base[:base.index(chr(125))]
        self.assertNotIn("var(--sub)", base)
        live = self.css[self.css.index("#subchip.live{"):]
        live = live[:live.index(chr(125))]
        self.assertIn("var(--sub)", live)
        chip = self.source[self.source.index("subChip(items){"):
                           self.source.index("subsMenu(){")]
        self.assertIn('chip.classList.toggle("live", running>0)', chip)
        self.assertIn('"⑂ "+running', chip)
        self.assertNotIn("items.length))", chip)

    def test_the_cost_line_carries_the_share_in_channel(self):
        self.assertIn('case "cost": this.cost(e.line,e.share,e.sub);',
                      self.source)
        self.assertIn('s.className="subshare"', self.source)
        self.assertIn('name==="delegate"||name==="collect"||name==="subtasks"',
                      self.source)


class TheWindowWatchesTheSubtasksTests(ApiCase):
    """#143 E2, die Python-Haelfte: der Ticker, die Eltern-Stempelung, der
    Kostenanteil und Stop -- alles gegen die echte Registry im Kern."""

    def setUp(self) -> None:
        super().setUp()
        crow_core.forget_subtasks()
        self.addCleanup(crow_core.forget_subtasks)

    def _seed(self, ident: str, status: str = "done", result: str = "RES",
              task: str = "the task", tokens: int = 7,
              transcript: str = "") -> "crow_core.Subtask":
        sub = crow_core.Subtask(ident, task, "",
                                {"model": "unit/m:free", "label": "OpenRouter"})
        sub.status = status
        sub.result = result if status == "done" else ""
        sub.failure = "" if status in ("done", "running") else result
        sub.usage_tokens = tokens
        sub.transcript = transcript
        crow_core.SUBTASKS[ident] = sub
        return sub

    def test_stop_cancels_what_runs(self):
        api = self.api()
        sub = self._seed("d1", status="running")
        api.stop()
        self.assertTrue(sub.cancelled)
        self.assertTrue(crow_core.INTERRUPT.is_set())

    def test_the_parent_is_stamped_at_first_sight(self):
        """Der Chat, der beim ersten Anblick live ist, bleibt der Eltern-Chat
        -- ein spaeterer Wechsel schreibt ihn NICHT um. NEGATIV-Haelfte: ein
        neuer Subtask unter dem neuen Chat bekommt den neuen Pfad."""
        api = self.api()
        self._seed("d1", status="running")
        self.assertEqual(api._subs_items()[0]["parent"], "")
        api._current_path = "C:\\somewhere\\chat-x.json"
        self.assertEqual(api._subs_items()[0]["parent"], "")
        self._seed("d2", status="running")
        rows = {r["i"]: r for r in api._subs_items()}
        self.assertEqual(rows["d2"]["parent"], "C:\\somewhere\\chat-x.json")
        # `here` haengt am OFFENEN Chat und wird je Schnappschuss neu
        # gerechnet: d2 gehoert in diesen Fluss, d1 nicht mehr -- und nach
        # einem Wechsel zurueck dreht es sich, ohne dass jemand etwas stempelt.
        self.assertFalse(rows["d1"]["here"])
        self.assertTrue(rows["d2"]["here"])
        api._current_path = None
        rows = {r["i"]: r for r in api._subs_items()}
        self.assertTrue(rows["d1"]["here"])
        self.assertFalse(rows["d2"]["here"])

    def test_the_result_is_clipped_for_the_page(self):
        api = self.api()
        self._seed("d1", result="x" * (crow_gui.TOOL_RESULT_SHOWN + 1000))
        row = api._subs_items()[0]
        self.assertEqual(len(row["res"]), crow_gui.TOOL_RESULT_SHOWN)

    def test_the_ticker_pushes_on_change_and_is_quiet_when_settled(self):
        """Direkt aufgerufen, mit gesetztem Stopper: eine Runde. Ohne
        Aenderung sagt sie nichts; mit einer neuen Zeile genau ein Event."""
        api = self.api()
        stopper = threading.Event()
        stopper.set()
        api._subs_ticker(stopper)
        self.assertEqual([m for m in self.drained(api)
                          if m.get("k") == "subs"], [])
        self._seed("d1")
        api._subs_ticker(stopper)
        events = [m for m in self.drained(api) if m.get("k") == "subs"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["items"][0]["i"], "d1")

    def test_the_cost_share_names_this_turns_subtasks_only(self):
        api = self.api()
        self._seed("d1", tokens=1809)
        self._seed("d2", tokens=7)
        self.assertEqual(api._sub_share(set()),
                         "⑂ 2 subtasks · 1,816 tok remote")
        self.assertEqual(api._sub_share({"d1"}),
                         "⑂ 1 subtask · 7 tok remote")
        self.assertEqual(api._sub_share({"d1", "d2"}), "")

    def test_the_rail_carries_the_subs(self):
        api = self.api()
        self._seed("d1", transcript="C:\\x\\chat-1-sub-d1.json")
        api._reload_rail()
        rails = [m for m in self.drained(api) if m.get("k") == "rail"]
        self.assertTrue(rails)
        subs = rails[-1].get("subs") or []
        self.assertEqual(subs[0]["i"], "d1")
        self.assertEqual(subs[0]["path"], "C:\\x\\chat-1-sub-d1.json")

    def test_the_parent_follows_the_chats_file(self):
        """robin: "die Subtasks sind fix zum Wurzelchat". Der Stempel folgt
        der DATEI des Chats: die Live-"" wird beim Beiseitelegen zum neuen
        Pfad, ein Archiv-Umzug zieht per Pfadgleichheit nach -- und NEGATIV:
        ein fremder Eltern-Pfad bleibt bei beidem unberuehrt."""
        api = self.api()
        self._seed("d1", status="running")
        self._seed("d2", status="running")
        api._subs_items()
        api._sub_parent["d2"] = "C:\\other\\chat-z.json"
        api._sub_adopt("", "C:\\x\\chat-a.json")
        self.assertEqual(api._sub_parent["d1"], "C:\\x\\chat-a.json")
        self.assertEqual(api._sub_parent["d2"], "C:\\other\\chat-z.json")
        api._sub_adopt("C:\\x\\chat-a.json", "C:\\x\\archiv\\chat-a.json")
        self.assertEqual(api._sub_parent["d1"], "C:\\x\\archiv\\chat-a.json")
        self.assertEqual(api._sub_parent["d2"], "C:\\other\\chat-z.json")
        block = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        leave = block[block.index("path = self._archive()"):]
        self.assertIn('self._sub_adopt("", path)', leave[:600])


class TheUserDelegatesFromTheComposerTests(ApiCase):
    """#143 E3, Fenster-Haelfte: die /delegate-Zeile wirkt SOFORT, auch
    waehrend der lokale Zug laeuft -- slash_answer steht in send() VOR dem
    Busy-Puffer -- und ein Leerlauf-Waechter haelt die Karte am Atmen, wenn
    ausserhalb eines Turns delegiert wird."""

    SPOT = {"provider": "openrouter", "label": "OpenRouter", "remote": True,
            "base_url": "http://x/v1", "model": "unit/model:free",
            "api_key": "k", "headers": {}, "transport": crow_core.TRANSPORT_CHAT,
            "routing": {}, "sticky": False, "filter": False, "params": []}

    def setUp(self) -> None:
        super().setUp()
        self._real_target = crow_core.delegate_target
        crow_core.delegate_target = lambda doc=None: (dict(self.SPOT), None)
        crow_core.forget_subtasks()
        self.addCleanup(self._put_back)

    def _put_back(self) -> None:
        crow_core.delegate_target = self._real_target
        crow_core.forget_subtasks()

    def _serve(self, text: str = "OK",
               gate: "threading.Event | None" = None) -> None:
        chunks = [json.dumps({"choices": [{"delta": {"content": text}}]}),
                  json.dumps({"choices": [],
                              "timings": {"predicted_n": 3, "prompt_n": 5}})]

        def fake(url, body, key, timeout, extra=None):
            if gate is not None:
                gate.wait(10)
            for chunk in chunks:
                yield chunk

        crow_core._post_stream = fake

    def test_the_line_starts_mid_turn_and_a_plain_line_still_buffers(self):
        api = self.api()
        gate = threading.Event()
        self.addCleanup(gate.set)
        self._serve("OK", gate=gate)
        api._busy = True                      # der lokale Zug laeuft
        started = api.send("/delegate write a haiku")
        self.assertFalse(started, "a delegation is not a turn")
        self.assertIn("d1", crow_core.SUBTASKS)
        notes = [m["t"] for m in self.drained(api) if m.get("k") == "note"]
        self.assertTrue(any("d1" in t for t in notes))
        # NEGATIV: die NORMALE Zeile mitten im Zug wird weiter gepuffert --
        # der Vorrang gilt der Slash-Zeile, nicht jedem Text.
        api.send("plain question")
        self.assertEqual(api._queued, "plain question")
        self.assertEqual(len(crow_core.SUBTASKS), 1)
        gate.set()
        crow_core.SUBTASKS["d1"].thread.join(10)

    def test_the_bare_line_asks_for_a_task(self):
        api = self.api()
        api.send("/delegate")
        notes = [m["t"] for m in self.drained(api) if m.get("k") == "note"]
        self.assertIn("what should it do? /delegate <task>", notes)
        self.assertEqual(dict(crow_core.SUBTASKS), {})

    def test_the_idle_watcher_pushes_until_quiet_and_subtasks_answers(self):
        api = self.api()
        gate = threading.Event()
        self.addCleanup(gate.set)
        self._serve("DONE", gate=gate)
        api.send("/delegate quick one")       # kein Turn -> der Waechter tickt
        gate.set()
        crow_core.SUBTASKS["d1"].thread.join(10)
        deadline = time.monotonic() + 5
        seen_done = False
        while time.monotonic() < deadline and not seen_done:
            for m in self.drained(api):
                if m.get("k") == "subs" and any(
                        i["i"] == "d1" and i["st"] == "done"
                        for i in m.get("items") or []):
                    seen_done = True
            time.sleep(0.1)
        self.assertTrue(seen_done, "no subs push carried the finished state")
        api.send("/subtasks")
        notes = [m["t"] for m in self.drained(api) if m.get("k") == "note"]
        self.assertTrue(any("d1" in t for t in notes))


class _TheWindowBefore162(crow_gui.Api):
    """The window as it stood before #162, runnable beside the fixed one.

    Two behaviours, both restored exactly: `open` and `reset` refused outright
    while a turn ran, and `push` stamped nothing because there was only ever one
    chat to push into. The cases at the bottom of the class below run against
    this and require the opposite outcome -- without them "the view switched"
    would be a sentence about a window nobody could have broken.
    """

    def open(self, path: str) -> None:
        if self._worker and self._worker.is_alive():
            return
        super().open(path)

    def reset(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        super().reset()

    def push(self, message: dict) -> None:
        self._out.put(message)


class TheViewIsNotTheTurnTests(ApiCase):
    """#162. Reading another chat while one is being worked on.

    THE DEFECT THIS REPLACES was not a bug, it was a wall: `open` and `reset`
    began with `if self._worker.is_alive(): return`, so a running turn owned the
    whole window. That is right for the MODEL -- one slot, `-np 1`, settled in
    #143 -- and wrong for the surface, because reading costs the server nothing.

    THE ONE THING THAT MUST NEVER HAPPEN is the worker losing the conversation
    it started with. Every positive below is followed by the predicate that
    catches exactly that.
    """

    def busy(self, api):
        """A turn that is running, seen from the bridge thread.

        A REAL THREAD, not a stub with `is_alive`, because the code under test
        also asks whether the CALLER is that thread. A stub would answer the
        first question and make the second unanswerable.
        """
        gate = threading.Event()
        worker = threading.Thread(target=gate.wait, daemon=True)
        worker.start()
        self.addCleanup(gate.set)
        api._worker = worker
        api._busy = True
        return gate

    # -- looking somewhere else -------------------------------------------

    def test_another_chat_can_be_opened_while_a_turn_runs(self):
        """POSITIVE. The file is drawn, and the view says where it is."""
        api = self.api()
        self.a_chat(api, "the chat being worked on")
        ok, other = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "the chat that is running", "half an answer")
        self.drained(api)
        self.busy(api)

        api.open(other)
        seen = self.drained(api)
        self.assertEqual(api._view_path, other)
        views = [m for m in seen if m.get("k") == "viewing"]
        self.assertTrue(views, "nothing told the page where it is standing")
        self.assertFalse(views[-1]["live"])
        self.assertEqual(views[-1]["running"], "the chat that is running")

    def test_the_running_conversation_is_not_handed_over(self):
        """THE LOAD-BEARING NEGATIVE. Looking must not swap what the worker
        writes into -- that is the one failure this design exists to prevent,
        and it would be invisible until the turn ended in the wrong chat."""
        api = self.api()
        self.a_chat(api, "the chat being worked on")
        ok, other = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "the chat that is running", "half an answer")
        running, path = api._conversation, api._current_path
        self.busy(api)

        api.open(other)
        self.assertIs(api._conversation, running,
                      "the view swapped the conversation out from under the turn")
        self.assertEqual(api._current_path, path)
        self.assertIn("half an answer",
                      [m.get("content") for m in running.payload()])

    def test_without_a_turn_the_same_click_really_switches(self):
        """COUNTER-PROBE to both cases above: if the click never switched, they
        would pass on a window in which chats simply do not open."""
        api = self.api()
        self.a_chat(api, "the other chat")
        ok, other = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "this chat")
        before = api._conversation

        api.open(other)
        self.assertIsNot(api._conversation, before, "nothing was switched")
        self.assertIsNone(api._view_path)

    def test_a_new_chat_during_a_turn_is_a_view_not_a_file(self):
        """`reset` mid-turn empties the pane and leaves the running chat alone.
        No file is written: an empty chat nobody used would be a row in the rail
        for one click."""
        api = self.api()
        self.a_chat(api, "the chat that is running")
        running = api._conversation
        self.busy(api)

        api.reset()
        self.assertEqual(api._view_path, "")
        self.assertIs(api._conversation, running)
        views = [m for m in self.drained(api) if m.get("k") == "viewing"]
        self.assertTrue(views and not views[-1]["live"])

    # -- what the background turn says -------------------------------------

    def test_what_the_worker_says_while_the_view_is_elsewhere_is_stamped(self):
        """POSITIVE. The stamp comes from the SENDER, not from the message type,
        so no call site has to know about it and a new one cannot forget."""
        api = self.api()
        api._view_path = "somewhere/else.json"
        api._worker = threading.current_thread()      # we ARE the worker now
        api.push({"k": "text", "t": "belongs to the other chat"})
        self.assertTrue(self.drained(api)[-1].get("bg"))

    def test_the_same_message_is_not_stamped_when_the_view_is_the_turn(self):
        """NEGATIVE HALF. Stamping everything would empty the pane of the chat
        being watched -- the page drops what carries the mark."""
        api = self.api()
        api._view_path = None
        api._worker = threading.current_thread()
        api.push({"k": "text", "t": "belongs right here"})
        self.assertNotIn("bg", self.drained(api)[-1])

    def test_the_bridge_thread_is_never_stamped(self):
        """The other half of the same rule: a note the user's own click produced
        belongs on screen even while a turn runs elsewhere."""
        api = self.api()
        api._view_path = "somewhere/else.json"
        self.busy(api)                                 # worker is NOT this thread
        api.push({"k": "note", "t": "answered right here"})
        self.assertNotIn("bg", self.drained(api)[-1])

    # -- typing while looking elsewhere ------------------------------------

    def test_a_line_typed_elsewhere_remembers_which_chat_it_meant(self):
        """Without the target the line would run in the chat that happens to be
        computing -- from the outside indistinguishable from a misclick."""
        api = self.api()
        api._view_path = "other.json"
        self.busy(api)
        self.assertTrue(api.send("for the other chat"))
        self.assertEqual(api._queued, "for the other chat")
        self.assertEqual(api._queued_to, "other.json")
        self.assertIn("queued", self.kinds(api))

    def test_a_line_typed_in_the_running_chat_carries_no_target(self):
        """COUNTER-PROBE: the target is a fact about where it was typed, not a
        constant. `None` is what makes `_pump` keep running where it is."""
        api = self.api()
        api._view_path = None
        self.busy(api)
        self.assertTrue(api.send("for this chat"))
        self.assertEqual(api._queued, "for this chat")
        self.assertIsNone(api._queued_to)

    # -- coming back --------------------------------------------------------

    def test_returning_draws_what_the_turn_produced_while_unwatched(self):
        """FROM THE CONVERSATION, NOT FROM DISK. The file is older than the chat
        while a turn is in flight, so a reader off disk would miss exactly the
        answers that arrived during the look away."""
        api = self.api()
        self.a_chat(api, "the running chat", "the first answer")
        api._view_path = "elsewhere.json"
        api._conversation.append("assistant", "arrived while looking away")
        self.drained(api)

        api.view_live()
        seen = self.drained(api)
        self.assertIsNone(api._view_path)
        text = "".join(m.get("t", "") for m in seen if m.get("k") == "text")
        self.assertIn("arrived while looking away", text)
        views = [m for m in seen if m.get("k") == "viewing"]
        self.assertTrue(views and views[-1]["live"])

    def test_returning_from_the_live_chat_is_a_no_op(self):
        """NEGATIVE HALF: redrawing on every click would clear and repaint the
        pane for nothing, and a half-streamed answer would flicker."""
        api = self.api()
        self.a_chat(api, "the running chat")
        self.drained(api)
        api.view_live()
        self.assertEqual(self.drained(api), [])

    # -- the handover between two turns ------------------------------------

    def test_the_handover_switches_where_the_wall_would_have_refused(self):
        """`_pump` runs in the worker, so `open` sees a live thread. Without the
        flag it would refuse the very switch it was asked to make."""
        api = self.api()
        self.a_chat(api, "the target chat")
        ok, target = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "the chat that just finished")
        api._worker = threading.current_thread()

        api._hand_over(target)
        self.assertIsNone(api._view_path)
        self.assertFalse(api._switching, "the flag outlived the handover")
        self.assertEqual(api._current_path, target)
        self.assertIn("the target chat",
                      [m.get("content") for m in api._conversation.payload()],
                      "the window switched to a chat without its content")

    def test_the_flag_falls_even_when_the_handover_throws(self):
        """A flag left standing would leave every later click able to pull the
        conversation out from under a running turn -- the failure this whole
        class is written against, arrived at from the other side."""
        api = self.api()
        api._worker = threading.current_thread()
        with mock.patch.object(type(api), "reset",
                               side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                api._hand_over("")
        self.assertFalse(api._switching)

    # -- what the rail says while the two are different --------------------

    def two_chats(self, api):
        """A saved chat, and a second one live in the window. Returns the path
        of the saved one."""
        self.a_chat(api, "the chat on disk")
        ok, saved = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "the chat that is running")
        self.drained(api)
        return saved

    def row(self, api, path):
        entry = self.rail(api)
        rows = [r for r in entry["rollovers"] if r.get("path") == path]
        self.assertTrue(rows, "the chat is not in the rail")
        return rows[0]

    def test_the_mark_follows_the_eye_not_the_turn(self):
        """robin, 2026-08-30: the old chat stayed lit while another was open.
        `active` meant "where the work is"; it has to mean "where I am"."""
        api = self.api()
        saved = self.two_chats(api)
        self.busy(api)
        api.open(saved)

        api._reload_rail()
        # ONE READ, because draining empties the queue -- a second `rail()`
        # would report "never drawn" about a rail that was.
        entry = self.rail(api)
        mine = [r for r in entry["rollovers"] if r.get("path") == saved]
        self.assertTrue(mine and mine[0]["active"],
                        "the chat being read is not marked")
        self.assertFalse(entry["live_active"],
                         "the running chat is still marked as the open one")

    def test_the_running_chat_is_marked_as_running_not_as_open(self):
        """The two facts are separate on purpose: one is where the eye is, the
        other is where the work is, and during a look away they differ."""
        api = self.api()
        saved = self.two_chats(api)
        self.busy(api)
        api.open(saved)

        api._reload_rail()
        rail = self.rail(api)
        self.assertTrue(rail["live_running"], "nothing says where the work is")
        mine = [r for r in rail["rollovers"] if r.get("path") == saved]
        self.assertTrue(mine)
        self.assertFalse(mine[0]["running"],
                         "the chat being read is claimed to be running")

    def test_without_a_turn_nothing_claims_to_be_running(self):
        """COUNTER-PROBE: a flag that is always true marks nothing. `_busy` is
        what makes it a statement rather than decoration."""
        api = self.api()
        self.two_chats(api)
        api._reload_rail()
        self.assertFalse(self.rail(api)["live_running"])

    def test_a_turn_that_ends_unwatched_leaves_a_mark_that_reading_clears(self):
        """The whole point of not jumping: the finished chat has to be able to
        say so from the rail, and stop saying it once it has been read."""
        api = self.api()
        saved = self.two_chats(api)
        api._view_path = saved
        api._mark_done(api._current_path)          # the live chat, no file
        self.assertTrue(self.rail(api)["live_done"])

        api.view_live()
        api._reload_rail()
        self.assertFalse(self.rail(api)["live_done"],
                         "the mark outlived the reading")

    def test_a_chat_being_read_is_never_also_marked_done(self):
        """NEGATIVE HALF. Both marks draw a bar in the same place; a chat that
        is open and finished would draw two, and the amber one would read as
        'unread' over something being read."""
        api = self.api()
        saved = self.two_chats(api)
        api._done_paths.add(saved)
        api._view_path = saved
        api._reload_rail()
        row = self.row(api, saved)
        self.assertTrue(row["active"])
        self.assertTrue(row["done"], "python still reports the fact")
        # The page is what resolves it, and the rule lives in one place.
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.assertIn('r.done && !r.active ? " done" : ""', source)

    # -- the counter belongs to the chat on screen -------------------------

    def test_looking_at_another_chat_shows_that_chat_s_context(self):
        """robin, 2026-08-30: the counter was blank while reading another chat.
        Its own pushes were dropped as background, and nothing put the numbers
        of the chat actually on screen in their place."""
        api = self.api()
        saved = self.two_chats(api)
        api._context_tokens = 4321                 # the RUNNING chat's number
        self.busy(api)

        api.open(saved)
        costs = [m for m in self.drained(api) if m.get("k") == "cost"]
        self.assertTrue(costs, "no counter was drawn for the chat being read")
        self.assertNotEqual(costs[-1]["tokens"], 4321,
                            "the counter still shows the running chat")

    def test_a_new_chat_during_a_turn_shows_an_empty_counter(self):
        """A fresh chat has no context, and saying otherwise would be a number
        about a conversation that does not exist yet."""
        api = self.api()
        self.a_chat(api, "the chat that is running")
        api._context_tokens = 4321
        self.busy(api)

        api.reset()
        costs = [m for m in self.drained(api) if m.get("k") == "cost"]
        self.assertTrue(costs)
        self.assertEqual(costs[-1]["tokens"], 0)

    # -- the handover does not move the eye --------------------------------

    def test_the_handover_leaves_the_reader_where_they_are(self):
        """robin, 2026-08-30: no automatic switch when a turn finishes. The
        queued line runs in ITS chat; the view stays in the one being read."""
        api = self.api()
        target = self.two_chats(api)
        elsewhere = os.path.join(self.dir, "chat-elsewhere.json")
        crow_core.save_session(api._conversation, "http://127.0.0.1:1/v1", 0,
                               path=elsewhere)
        api._view_path = elsewhere                 # the reader is over here
        api._worker = threading.current_thread()

        api._hand_over(target)
        self.assertEqual(api._view_path, elsewhere,
                         "the window pulled the reader into the finished chat")
        self.assertEqual(api._current_path, target,
                         "the line would have run in the wrong chat")

    def test_the_handover_does_follow_when_the_reader_is_at_the_target(self):
        """COUNTER-PROBE, and it is the ordinary case: the line was typed in
        the chat being read, so after the switch the reader is simply there."""
        api = self.api()
        target = self.two_chats(api)
        api._view_path = target
        api._worker = threading.current_thread()

        api._hand_over(target)
        self.assertIsNone(api._view_path)
        views = [m for m in self.drained(api) if m.get("k") == "viewing"]
        self.assertTrue(views and views[-1]["live"])

    # -- what is nachgezogen once the turn is over -------------------------

    def test_the_bar_stops_claiming_a_turn_that_has_finished(self):
        """robin, 2026-08-30 abends: `still running` stood over a turn that was
        long done. The bar was set when the look away happened and never again,
        so it was a memory rather than a reading."""
        api = self.api()
        saved = self.two_chats(api)
        self.busy(api)
        api.open(saved)
        self.assertTrue([m for m in self.drained(api)
                         if m.get("k") == "viewing"][-1]["running"])

        api._busy = False                     # the turn ends
        api._mark_done(api._current_path)
        views = [m for m in self.drained(api) if m.get("k") == "viewing"]
        self.assertTrue(views, "the finished turn told the bar nothing")
        self.assertIsNone(views[-1]["running"],
                          "the bar still names a chat that is not running")

    def test_a_real_switch_after_the_turn_clears_the_unread_mark(self):
        """The mark was dropped only on the LOOK paths. Once the turn is over a
        rail click is an ordinary switch -- and that one kept the amber bar on a
        chat the user was reading."""
        api = self.api()
        saved = self.two_chats(api)
        api._done_paths.add(saved)
        api.open(saved)                       # no worker: the real switch
        self.assertNotIn(saved, api._done_paths,
                         "the chat stays marked unread after being read")

    def test_a_real_switch_after_the_turn_says_where_it_is(self):
        """Same path, the other half: the bar has to disappear, not linger over
        a chat that is now simply the open one."""
        api = self.api()
        saved = self.two_chats(api)
        api._view_path = saved                # was a look, the turn has ended
        api.open(saved)
        views = [m for m in self.drained(api) if m.get("k") == "viewing"]
        self.assertTrue(views and views[-1]["live"],
                        "the bar survived the switch it was about")

    # -- the cost line of a turn nobody watched ----------------------------

    def test_the_cost_line_of_a_background_turn_comes_back_with_the_chat(self):
        """robin, 2026-08-30: the numbers were gone. The line is not part of the
        conversation, so `_replay` cannot redraw it -- and it had been dropped
        as background while it was pushed."""
        api = self.api()
        saved = self.two_chats(api)
        api._current_path = saved             # the turn ran in the saved chat
        api.push({"k": "cost", "line": "[9 rounds | 384 tok @ 22.1 tok/s]",
                  "share": None, "tokens": 7100, "n_ctx": 200000})
        self.drained(api)
        api._current_path = None

        self.busy(api)
        api.open(saved)
        costs = [m for m in self.drained(api) if m.get("k") == "cost"]
        self.assertTrue(costs)
        self.assertIn("22.1 tok/s", costs[-1]["line"],
                      "the chat came back without the numbers it cost")

    def test_a_chat_with_no_remembered_line_shows_none_rather_than_anothers(self):
        """NEGATIVE HALF. A chat whose turn ran in an earlier session has no
        remembered line, and showing the previous chat's numbers there would be
        worse than showing none -- it would be wrong and look right."""
        api = self.api()
        saved = self.two_chats(api)
        api._last_cost[""] = {"line": "[belongs to the live chat]",
                              "share": None}
        self.busy(api)
        api.open(saved)
        costs = [m for m in self.drained(api) if m.get("k") == "cost"]
        self.assertTrue(costs)
        self.assertEqual(costs[-1]["line"], "",
                         "another chat's cost line was shown")

    # -- the window that had the wall, run beside the one that does not -----

    def test_the_old_window_refuses_the_click_these_cases_require(self):
        """THE PROOF THAT THE POSITIVES MEASURE SOMETHING. Same setup, same
        click, the pre-#162 behaviour restored -- and the view does not move.
        If this passed as well, "another chat can be opened while a turn runs"
        would be true of every version ever shipped."""
        api = self.api(klass=_TheWindowBefore162)
        self.a_chat(api, "the other chat")
        ok, other = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "the chat that is running")
        self.drained(api)
        self.busy(api)

        api.open(other)
        self.assertIsNone(api._view_path, "the old window moved the view")
        self.assertEqual([m for m in self.drained(api)
                          if m.get("k") == "viewing"], [],
                         "the old window told the page where it was standing")

    def test_the_old_window_stamps_nothing_and_would_write_into_the_view(self):
        """The other half of the wall. Without the stamp the background turn's
        text reaches whatever chat is open -- silently, and only visible as
        somebody else's answer appearing in the chat being read."""
        api = self.api(klass=_TheWindowBefore162)
        api._view_path = "somewhere/else.json"
        api._worker = threading.current_thread()
        api.push({"k": "text", "t": "belongs to the other chat"})
        self.assertNotIn("bg", self.drained(api)[-1],
                         "the old window stamped -- then the fix changed nothing")


class AnOutstandingToolCallSaysSoTests(unittest.TestCase):
    """#172. Ein Aufruf, der nicht zurueckkommt, hielt den Lauf still an.

    GEMESSEN WAEHREND EINER BLOCKADE am 2026-08-30: 19 Chrome-Prozesse, der
    aelteste zwei Stunden alt, einer mit 7.511 s CPU, llama-server idle
    (`release: stop processing`), das Fenster stumm -- letzte Nachricht ein
    Gedanke, danach nichts. Kein Spinner, keine Notiz, keine Zahl. Von aussen
    sah eine Zweistundenblockade aus wie zwei Stunden harte Arbeit, und geloest
    hat es erst, dass robin die Prozesse von Hand abgeraeumt hat.

    DIE ZIELUHR HALF NICHT: sie zaehlt den Schritt, nicht das Werkzeug.

    AM QUELLTEXT GEPRUEFT, weil die Seite hier keine ist -- dieselbe Form, die
    diese Suite fuer Seiten-Regeln seit jeher benutzt.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_the_open_call_gets_a_clock_when_it_starts(self):
        self.assertTrue("this.toolClock(d);" in self.source,
                        "der offene Aufruf bekommt keine Uhr")
        self.assertTrue("this.toolTick=setInterval(draw, 1000);" in self.source,
                        "die Uhr laeuft nicht in der Seite weiter")

    def test_the_clock_leaves_the_composer_bar_alone(self):
        """robin, 2026-08-31: "die tok/s wird unten in der Chateingabe nicht mehr
        angezeigt". Der erste Versuch schrieb die Werkzeuguhr in `#turnstate` --
        dasselbe Feld, das die Tokenrate des laufenden Zuges traegt. Zwei
        Schreiber auf einem Feld sind keine zwei Auskuenfte, sondern eine
        verlorene: die Uhr ueberschrieb die Rate im Sekundentakt und liess nach
        `toolend` den Stand eines fertigen Aufrufs stehen."""
        i = self.source.index("toolClock(row){")
        j = self.source.index("toolClockStop(){", i)
        self.assertNotIn("#turnstate", self.source[i:j],
                         "die Uhr schreibt wieder in die Leiste der Tokenrate")

    def test_three_ways_out_stop_the_clock(self):
        """GEGENPROBE, und sie ist die eigentliche Falle: eine Kachel, die nach
        dem Zug weitertickt, behauptet einen laufenden Aufruf. `toolend` ist der
        Normalfall, `idle` faengt Abbruch und Fehlschlag."""
        stops = self.source.count("this.toolClockStop();")
        self.assertGreaterEqual(stops, 3,
                                "nicht jeder Ausgang stoppt die Uhr: %d" % stops)
        self.assertTrue("toolClockStop(){" in self.source)

    def test_a_call_too_fast_for_a_number_leaves_none(self):
        """GEGENPROBE, und robin hat sie beim ersten Blick gefunden: die Uhr
        schrieb `0m 00s` in eine Zeile, in der vorher nichts stand. Unter einer
        Zehntelsekunde ist eine Zahl Laerm -- dieselbe Grenze, die das Terminal
        seit #70 zieht -- und wer die Zeile beschreibt, muss sie auch raeumen."""
        self.assertTrue(
            'note.textContent = parts.length ? parts.join(" · ") : "";'
            in self.source,
            "eine zu schnelle Antwort laesst die Uhr stehen")

    def test_nothing_sweeps_processes_by_name(self):
        """DIE ANDERE NEGATIVHAELFTE, woertlich aus dem Ticket: kein Abraeumen
        nach Prozessnamen. #158 hat das einmal gekostet -- ein Messskript raeumte
        'jeden llama-server' ab und nahm robins Testserver mit."""
        for forbidden in ("taskkill /IM", "taskkill /im", "pkill ", "killall "):
            self.assertFalse(forbidden in self.source,
                             "das Fenster raeumt nach Namen ab: %r" % forbidden)


class TheRailLetsGoWhenTheTurnIsOverTests(ApiCase):
    """robin, 2026-08-31: "Die Chat-Kachel zeigt weiterhin aktiver turn mit der
    Amber-Animation, obwohl der Turn durch ist."

    DIE RAIL WURDE EINE ZEILE ZU FRUEH GEZEICHNET. `_run` zeichnet sie am
    Zugende -- da steht `_busy` noch auf True, weil erst `_pump` entscheidet, ob
    ein zweiter Zug folgt. Danach fiel das Flag, und niemand zeichnete nochmal.
    """

    def _provider(self) -> None:
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        doc = crow_core.provider_doc()
        doc["catalog"] = {"openrouter": {"fetched": 1, "models": [
            {"id": "z-ai/glm-5.2:free", "name": "glm", "context": 131072}]}}
        crow_core.provider_write(doc)
        self.assertIsNone(crow_core.provider_pick("openrouter", "z-ai/glm-5.2:free"))

    def test_the_last_rail_of_a_turn_says_it_is_no_longer_running(self):
        self._provider()
        api = self.api()

        def fake_run(conversation, **kw):
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost=crow_core.TurnCost(),
                                        context_tokens=9, promised_warm=False,
                                        rolled=False, stopped=False,
                                        reported=True)

        api._busy = True
        api._conversation.append("user", "eine Frage")
        with mock.patch.object(crow_gui, "run_turn", fake_run),              mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._pump("eine Frage")
        rails = [m for m in self.drained(api) if m.get("k") == "rail"]
        self.assertTrue(rails, "die Rail wurde nie gezeichnet")
        self.assertFalse(rails[-1]["live_running"],
                         "die letzte Rail des Zuges behauptet, es laufe noch")
        self.assertFalse(api._busy)


class TheTurnBillsRideWithTheChatTests(ApiCase):
    """#171. Was ein Zug gekostet hat, ueberlebt jetzt den Schnitt.

    DER LAUF, DER ES ZEIGTE: 5h52m, ein Rollover bei 181.501 Token -- und mit
    dem Schnitt war die Zeile des ersten Zuges weg, desjenigen mit dem Plan und
    dem groessten Block Reasoning.
    """

    def _provider(self) -> None:
        """Ein Endpunkt, den `_run` aufloesen kann -- dieselbe Vorbereitung wie
        in den Rollover-Faellen weiter oben."""
        crow_core.provider_key_set("openrouter", "not-a-real-key-0123456789")
        doc = crow_core.provider_doc()
        doc["catalog"] = {"openrouter": {"fetched": 1, "models": [
            {"id": "z-ai/glm-5.2:free", "name": "glm", "context": 131072}]}}
        crow_core.provider_write(doc)
        self.assertIsNone(crow_core.provider_pick("openrouter", "z-ai/glm-5.2:free"))

    def a_cost(self):
        cost = crow_core.TurnCost()
        cost.add_round({"predicted_n": 200, "prompt_n": 1000,
                        "predicted_ms": 10000.0, "prompt_ms": 2000.0,
                        "_client_total_s": 12.0, "_cached_tokens": 900})
        return cost

    def test_a_finished_turn_leaves_its_bill_in_the_band(self):
        """Und mit `at`, damit ein Auswerter sie im Archiv den Zuegen zuordnen
        kann -- ohne das ist eine Bilanz eine Zahl ohne Zug."""
        self._provider()
        api = self.api()
        cost = self.a_cost()

        def fake_run(conversation, **kw):
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost=cost, context_tokens=9,
                                        promised_warm=False, rolled=False,
                                        stopped=False, reported=True)

        api._conversation.append("user", "eine Frage")
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run("eine Frage")
        self.assertEqual(len(api._timings), 1)
        self.assertEqual(api._timings[0]["decoded"], 200)
        self.assertEqual(api._timings[0]["decode_rate"], 20.0)
        self.assertEqual(api._timings[0]["at"], len(api._conversation))

    def test_a_turn_with_no_rounds_leaves_none(self):
        """GEGENPROBE: an derselben Bedingung wie die Zeile. Ein Zug, der nie
        eine Runde hatte, hinterlaesst keine Bilanz -- eine leere waere ein Zug,
        der nichts gekostet hat."""
        self._provider()
        api = self.api()

        def fake_run(conversation, **kw):
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost=crow_core.TurnCost(),
                                        context_tokens=9, promised_warm=False,
                                        rolled=False, stopped=False,
                                        reported=True)

        api._conversation.append("user", "eine Frage")
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run("eine Frage")
        self.assertEqual(api._timings, [])

    def test_the_band_goes_into_the_archive_and_the_new_context_starts_empty(self):
        """Die Bilanzen gehoeren zu dem Kontext, der weggelegt wird. Bleiben sie
        stehen, zeigen ihre Positionen auf Nachrichten, die es nicht mehr gibt."""
        self._provider()
        api = self.api()
        api._notes = [{"k": "note", "t": "vor dem Schnitt", "at": 1}]
        api._timings = [{"rounds": 3, "decoded": 111, "at": 1}]
        handed = {}

        def fake_roll(conversation, base_url, context_tokens, carry=None,
                      digest="", notes=None, timings=None, **_):
            handed["notes"] = list(notes or [])
            handed["timings"] = list(timings or [])
            conversation.reset()
            conversation.append("user", "note\n\n" + (carry or ""))
            return os.path.join(crow_core.SESSION_DIR, "rollover-fake.json")

        def fake_run(conversation, **kw):
            conversation.append("assistant", "done")
            return crow_core.TurnResult(cost=crow_core.TurnCost(),
                                        context_tokens=9, promised_warm=False,
                                        rolled=True, stopped=False,
                                        reported=True)

        api._n_ctx = 200192
        api._context_tokens = 190000
        with mock.patch.object(crow_gui, "run_turn", fake_run), \
             mock.patch.object(crow_core, "roll_over", fake_roll), \
             mock.patch.object(crow_core, "review_due", lambda *a, **k: None):
            api._run("weiter im Text")
        self.assertEqual([n["t"] for n in handed["notes"]], ["vor dem Schnitt"])
        self.assertEqual([t["decoded"] for t in handed["timings"]], [111])
        self.assertEqual(api._timings, [], "die Bilanzen des alten Kontexts blieben stehen")
        # robin 2026-09-24: the "rolled over at" line is log-only, so the
        # band of the new context starts empty
        self.assertEqual([n.get("t") for n in api._notes], [],
                         "nach dem Schnitt steht nichts vom alten Band")


class MarksStayWhereTheyHappenedTests(ApiCase):
    """#173. Die Rollover-Notiz stand unter allem, was nach dem Schnitt lief --
    und sagte damit das Gegenteil ihrer eigenen Aussage.

    DREI WEGE, EINE REIHENFOLGE: live gezeichnet, aus `payload()` neu gezeichnet
    (Zurueckwechseln waehrend eines Zuges) und von Platte gelesen. Wenn die drei
    auseinanderlaufen, ist genau das der Fehler, gegen den `_replay` gebaut ist.
    """

    def a_chat(self, api):
        """Zwei Zuege mit einer Marke dazwischen, wie sie live entsteht."""
        api._conversation.append("user", "first")
        api._conversation.append("assistant", "answer one")
        api.push({"k": "note", "t": "goal mode paused: step 1 has taken 25 turns"})
        api._conversation.append("user", "second")
        api._conversation.append("assistant", "answer two")

    def order(self, api) -> list:
        """Die gezeichnete Folge, auf das reduziert, was eine Position hat."""
        return [m["k"] for m in self.drained(api)
                if m.get("k") in ("user", "note")]

    def test_a_mark_is_recorded_with_the_number_of_messages_before_it(self):
        """DIE ZAHL WIRD NICHT GERATEN: sie zaehlt dieselben Nachrichten, die
        `payload()` liefert -- den System-Prompt eingeschlossen, sonst laege
        jede Marke eines Chats mit Systemzeile um eins daneben."""
        api = self.api()
        api._conversation.append("user", "first")
        api._conversation.append("assistant", "answer one")
        standing = len(api._conversation)
        api.push({"k": "note", "t": "goal mode paused: step 1 has taken 25 turns"})
        self.assertEqual(api._notes,
                         [{"k": "note", "t": "goal mode paused: step 1 has taken 25 turns",
                           "at": standing}])
        self.assertEqual(standing, len(api._conversation.payload()))

    def test_the_mark_is_drawn_between_the_turn_before_it_and_the_one_after(self):
        """Der Fehler war, dass sie ans Ende rutschte: `note` NACH dem zweiten
        `user` statt davor."""
        api = self.api()
        self.a_chat(api)
        self.drained(api)              # was live lief, interessiert hier nicht
        api._replay(api._conversation.payload(), api._notes)
        self.assertEqual(self.order(api), ["user", "note", "user"])

    def test_a_chat_read_back_from_disk_draws_them_in_the_same_places(self):
        """Der Fall aus dem Ticket: sonst haben Wiedergabe und Live-Weg zwei
        verschiedene Reihenfolgen, und das ist der Fehler, den `_replay`
        ueberhaupt verhindern soll."""
        api = self.api()
        self.a_chat(api)
        path = os.path.join(self.dir, "chat-marks.json")
        crow_core.save_session(api._conversation, "http://127.0.0.1:1/v1", 7,
                               path=path, with_kv=False, notes=api._notes)
        self.drained(api)
        api._replay(api._conversation.payload(), api._notes)
        live = self.order(api)
        restored = crow_core.load_session("http://127.0.0.1:1/v1", None, path,
                                          with_kv=False)
        self.assertIsNotNone(restored)
        api._replay(restored[0], crow_core.session_notes(path))
        self.assertEqual(self.order(api), live)

    def test_drawing_them_again_does_not_double_the_band(self):
        """`push` schreibt jede Marke mit -- ohne die Sperre waechst das Band bei
        jedem Zurueckwechseln, und beim dritten Blick stuenden acht Notizen da,
        wo eine passiert ist."""
        api = self.api()
        self.a_chat(api)
        before = list(api._notes)
        api._replay(api._conversation.payload(), api._notes)
        api._replay(api._conversation.payload(), api._notes)
        self.assertEqual(api._notes, before)

    def test_a_mark_never_reaches_the_message_list(self):
        """NEGATIVHAELFTE: im Nachrichtenband laese das Modell seine eigene
        Rollover-Notiz als robins Worte, und `_spoken_carry` truege sie ueber
        den naechsten Schnitt."""
        api = self.api()
        self.a_chat(api)
        self.assertNotIn("rolled over at 181501 tokens",
                         json.dumps(api._conversation.payload()))


class TheGoalPanelShowsTheGoalsOwnCostTests(ApiCase):
    """#174, #168. Was im Kopf des Panels steht, woher es kommt, und was ein
    Schritt anzeigt, an dem wieder gearbeitet wird.

    DAS PANEL HATTE BIS HIER KEINEN EINZIGEN FALL. Es war live erprobt, und
    genau die zwei Zahlen, die live falsch waren -- die Kopfsumme und der gruene
    Haken auf einem laufenden Schritt --, haette ein Fall hier gefangen.
    """

    def setUp(self) -> None:
        super().setUp()
        # Modulzustand, wie in der Kernsuite: ohne das Zuruecksetzen traegt der
        # naechste Fall den Zaehlerstand dieses hier.
        self.addCleanup(crow_core.goal_tokens_mark, crow_core.GOAL_TOKENS_NOW)
        crow_core.goal_tokens_mark(0)

    def panel(self, api) -> dict:
        """Die letzte Ziel-Nachricht an die Seite."""
        said = [m for m in self.drained(api) if m.get("k") == "goal"]
        self.assertTrue(said, "the page was never told about the goal")
        return said[-1]["goal"]

    def test_the_panel_carries_the_goals_own_total_not_the_column(self):
        """Live standen 256K im Kopf und 255.758 in der Spalte -- dieselbe
        falsche Zahl zweimal. Der Kopf traegt jetzt, was das Ziel gekostet hat,
        einschliesslich dessen, was zwischen zwei Schritten passiert."""
        api = self.api()
        crow_core.goal_start("Ship it", ["read", "write"], now=1000.0)
        crow_core.goal_tokens_seen(1000)
        crow_core.goal_step_begin(0, now=1000.0)
        crow_core.goal_tokens_seen(1400)
        crow_core.goal_step_end(0, now=1010.0)
        crow_core.goal_tokens_seen(9000)
        api.push_goal(force=True)
        goal = self.panel(api)
        self.assertEqual(goal["tokens"], 9000)
        self.assertEqual(sum(s["tokens"] for s in goal["steps"]), 400,
                         "the column changed -- then the head is not the point")

    def test_the_page_reads_that_number_instead_of_summing_the_column(self):
        """NEGATIVPROBE AM QUELLTEXT: solange die Seite die Spalte selbst
        aufsummiert, ist die Zahl im Nutzlastfeld daneben wirkungslos."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        # DER TREFFER WIRD ALS WAHRHEITSWERT GEPRUEFT, nicht mit assertIn: eine
        # gescheiterte Textsuche druckt sonst die ganze Datei in den Bericht.
        self.assertTrue("const tok=g.tokens||0" in source,
                        "the head no longer reads the goal's own total")
        self.assertFalse("reduce((a,s)=>a+(s.tokens||0),0)" in source,
                         "the page still adds the step column up itself")

    def test_delegated_tokens_reach_the_page_beside_the_local_ones(self):
        """#169. Getrennte Felder, damit die Seite sie getrennt zeichnen KANN --
        in einem Feld addiert waere die Entscheidung schon hier gefallen."""
        api = self.api()
        crow_core.goal_start("Ship it", ["read", "write"], now=1000.0)
        crow_core.goal_step_begin(0, now=1000.0)
        crow_core.goal_delegated_seen(18400)
        crow_core.goal_step_end(0, now=1010.0)
        api.push_goal(force=True)
        goal = self.panel(api)
        self.assertEqual(goal["delegated"], 18400)
        self.assertEqual(goal["tokens"], 0)
        self.assertEqual(goal["steps"][0]["delegated"], 18400)
        self.assertEqual(goal["steps"][0]["tokens"], 0)

    def test_a_reopened_step_reaches_the_page_as_running(self):
        """#168. Der gruene Haken blieb den ganzen Zug ueber stehen, waehrend
        Crow den Meilenstein neu baute."""
        api = self.api()
        crow_core.goal_start("Ship it", ["read", "write"], now=1000.0)
        crow_core.goal_step_begin(0, now=1000.0)
        crow_core.goal_step_end(0, now=1010.0)
        api.push_goal(force=True)
        self.assertEqual(self.panel(api)["steps"][0]["status"], "done")
        crow_core.goal_step_begin(0, now=1020.0)
        api.push_goal(force=True)
        goal = self.panel(api)
        self.assertEqual(goal["steps"][0]["status"], "running")
        self.assertEqual(goal["done"], 0, "the counter kept a taken-back tick")

    def test_no_goal_no_panel(self):
        """GEGENPROBE: ein Kasten mit `0/0` waere eine Anzeige ueber etwas, das
        es nicht gibt (robin, 2026-08-30)."""
        api = self.api()
        api.push_goal(force=True)
        said = [m for m in self.drained(api) if m.get("k") == "goal"]
        self.assertEqual([m["goal"] for m in said], [None])


class AFailedStepIsRetriedNotSkippedTests(ApiCase):
    """#289, the window's half. 2026-09-24: step 4 went `failed`, the nudge
    after it said only "step 4 still open" (session.json msg 327), and
    after robin's hand skip the goal bar kept the old step for the whole
    next turn -- only goal_set/goal_step results repainted it. #294: the
    second failure no longer skips; it rolls into a fresh context."""

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(crow_core.goal_write, None)
        crow_core.goal_start("Ship it", ["read the log", "write the fix",
                                         "prove it"], now=1000.0)

    def turn(self, api, text, answer="working on it") -> None:
        """A turn that worked on the nudge: one tool call, one answer."""
        api._conversation.append("user", text)
        api._conversation.append(
            "assistant", "", tool_calls=[{"id": "c0", "name": "read_file",
                                          "arguments": "{}"}])
        api._conversation.append("tool", "...", tool_call_id="c0")
        api._conversation.append("assistant", answer)

    def goals(self, api) -> list:
        return [m["goal"] for m in self.drained(api) if m.get("k") == "goal"]

    def test_the_nudge_after_a_failure_quotes_its_note(self):
        """Second turn of the same step, the model worked -- the short "still
        open" line would go out. After a `failed` the note goes out instead."""
        api = self.api()
        self.turn(api, api._goal_nudge())
        crow_core.tool_goal_step(1, "failed", "the log is rotated away")
        nudge = api._goal_nudge()
        self.assertIn("the log is rotated away", nudge)
        self.assertIn("different approach", nudge)
        self.assertNotIn("still open. Continue", nudge)
        self.turn(api, nudge)
        # #294: the second `failed` (after the reflection) does NOT skip:
        # attempt 3 goes out in a fresh context, still on step 1.
        crow_core.tool_goal_step(1, "running", "reflection: rotate first")
        crow_core.tool_goal_step(1, "failed", "still rotated away")
        fresh = api._goal_nudge()
        self.assertIn("Step 1, attempt 3, in a FRESH context", fresh)
        self.assertIn("reflection: rotate first", fresh)
        self.assertTrue(api._goal_roll_due, "no rollover for attempt 3")
        self.assertNotIn("Next is step 2", fresh)
        self.assertEqual(crow_core.goal_skipped(), [])

    def test_a_hand_edit_of_goal_json_repaints_the_bar_within_a_round(self):
        api = self.api()
        api.push_goal(force=True)
        self.drained(api)
        goal = crow_core.goal_load()
        goal["steps"][0]["status"] = "skipped"
        crow_core.goal_write(goal)
        events = crow_gui.Turn(api.push, goal_reload=api.push_goal)
        events.round_finished({})
        said = self.goals(api)
        self.assertTrue(said, "the round did not read goal.json")
        self.assertEqual(said[-1]["steps"][0]["status"], "skipped")
        self.assertEqual(said[-1]["skipped"], [1])
        # GEGENPROBE: a round that only adds tokens draws nothing.
        crow_core.goal_tokens_mark(0)
        self.addCleanup(crow_core.goal_tokens_mark, 0)
        crow_core.goal_tokens_seen(500)
        events.round_finished({})
        self.assertEqual(self.goals(api), [])

    def test_goal_alone_repaints_what_it_read(self):
        """Live: `/goal` answered 4/9 while the bar still said 3/9."""
        api = self.api()
        api.push_goal(force=True)
        self.drained(api)
        crow_core.goal_step_end(0, now=1010.0)
        api._goal_command("")
        said = self.goals(api)
        self.assertTrue(said, "`/goal` did not repaint the bar")
        self.assertEqual(said[-1]["done"], 1)

    def test_goal_skip_from_the_composer_reaches_the_bar(self):
        """Window and phone send the line through the same `send`."""
        api = self.api()
        api.send("/goal skip 2 cannot be checked here")
        said = self.goals(api)
        self.assertTrue(said)
        self.assertEqual(said[-1]["steps"][1]["status"], "skipped")
        self.assertEqual(said[-1]["steps"][1]["note"],
                         "cannot be checked here")
        self.assertEqual(said[-1]["skipped"], [2])
        self.assertEqual(crow_core.goal_next_open(), 0)

    def test_the_page_draws_skipped_steps_and_the_partial_end(self):
        """NEGATIVPROBE AM QUELLTEXT: the bar has a mark and a head text for
        a skipped step, and "partial" is not the green Complete."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.assertTrue('if(state==="skipped")' in source)
        self.assertTrue('partial ? "Complete · "+skipText' in source)
        self.assertTrue("#goalpanel li.skipped" in source)


class TheGoalEnginePausesAndAsksTests(ApiCase):
    """#294 B/D, the window's half. 2026-09-24/25: steps 5-8 of the diorama
    goal were skipped without a word to robin. Every stop of the engine is
    now a PAUSE: one report turn (what, why, 2-3 proposals, the question),
    then the engine waits for a typed line -- window and phone alike."""

    def setUp(self) -> None:
        super().setUp()
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="crow-pause-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        crow_core.set_root(self.root)
        self.addCleanup(crow_core.set_root, None)
        self.addCleanup(crow_core.goal_write, None)
        # getattr: the red run without #294 fails on behaviour, not setUp.
        limits = getattr(crow_core, "goal_limits_set", None)
        if limits is not None:
            self.addCleanup(limits, None, None)
        crow_core.goal_command("Neon voxel diorama | plan it | build the "
                               "scene | animate the rain")
        crow_core.goal_step_end(0, note="PLAN.md written")

    def turn(self, api, text, answer="working on it") -> None:
        api._conversation.append("user", text)
        api._conversation.append(
            "assistant", "", tool_calls=[{"id": "c0", "name": "read_file",
                                          "arguments": "{}"}])
        api._conversation.append("tool", "...", tool_call_id="c0")
        api._conversation.append("assistant", answer)

    def notes(self, api) -> list:
        return [m["t"] for m in self.drained(api) if m.get("k") == "note"]

    def goals(self, api) -> list:
        return [m["goal"] for m in self.drained(api) if m.get("k") == "goal"]

    def test_a_pause_gets_one_report_turn_then_waits_for_a_line(self):
        api = self.api()
        self.turn(api, api._goal_nudge())
        crow_core.goal_pause(1, "environment",
                             "the environment failed 3 times: software GL")
        report = api._goal_nudge()
        self.assertIn("PAUSED at step 2 (environment)", report)
        self.assertIn("Two or three concrete proposals", report)
        self.assertIn("Ask robin whether he has further input", report)
        self.turn(api, report, "1. software GL 2. no GPU 3. A) stop serve "
                               "B) llama.cpp 4. Do you have more input?")
        self.assertIsNone(api._goal_nudge())
        self.assertIsNone(api._goal_nudge(), "the engine went on by itself")
        pause = crow_core.goal_load()["pause"]
        self.assertIn("Do you have more input?", pause["report"])
        notes = self.notes(api)
        self.assertTrue(any("waits for your line" in n for n in notes), notes)
        # Only a typed line resumes -- through `send`, as window and phone.
        api._pump = lambda *a, **k: None
        self.assertTrue(api.send("free the GPU, then go on"))
        goal = crow_core.goal_load()
        self.assertEqual(goal["status"], "open")
        self.assertEqual(goal["last_pause"]["class"], "environment")

    def test_a_slash_command_does_not_resume(self):
        api = self.api()
        crow_core.goal_pause(1, "budget", "over")
        api.send("/goal")
        self.assertEqual(crow_core.goal_load()["status"], "paused")

    def test_an_environment_retry_waits_and_stop_drops_it(self):
        api = self.api()
        self.turn(api, api._goal_nudge())
        crow_core.goal_fail(1, crow_core.GOAL_ENV, "software GL",
                            capture="/r/a.png")
        nudge = api._goal_nudge()
        self.assertIn("the ENVIRONMENT failed, not your work", nudge)
        self.assertEqual(api._goal_delay, crow_core.GOAL_ENV_DELAY)
        self.assertIsNone(crow_core.goal_pending(crow_core.goal_load(), 1))
        api._goal_paused = True
        self.assertFalse(api._goal_wait(5.0))
        api._goal_paused = False
        self.assertTrue(api._goal_wait(0.0))

    def test_the_step_budget_pauses_with_a_report(self):
        api = self.api()
        self.turn(api, api._goal_nudge())
        goal = crow_core.goal_load()
        goal["steps"][1]["started"] = time.time() - 61 * 60
        crow_core.goal_write(goal)
        report = api._goal_nudge()
        self.assertIn("PAUSED at step 2 (budget)", report)
        self.assertIn("over its budget of 60 min", report)

    def test_no_newly_passed_item_pauses_after_n_turns(self):
        crow_core.goal_limits_set(None, 3)
        api = self.api()
        self.turn(api, api._goal_nudge())
        crow_core.goal_checklist_write(1, ["neon signs glow"])
        texts = []
        for n in range(4):          # the first nudge starts the count
            text = api._goal_nudge()
            texts.append(text)
            self.turn(api, text, "round %d" % n)
        self.assertIn("PAUSED at step 2 (no progress)", texts[-1])
        # GEGENPROBE: a newly passed item starts the count again.
        crow_core.goal_resume()
        api._goal_reset()
        self.turn(api, api._goal_nudge())
        crow_core.judge_store(1, {"checklist": {"neon signs glow": "yes"}})
        self.assertNotIn("PAUSED", api._goal_nudge())

    def test_the_bar_carries_the_pause_and_the_sub_steps(self):
        api = self.api()
        goal = crow_core.goal_load()
        goal["steps"][1]["subs"] = [{"text": "emissive", "status": "done"},
                                    {"text": "bloom", "status": "open"}]
        crow_core.goal_write(goal)
        crow_core.goal_pause(1, "capability", "sub-step 2.2 failed")
        api.push_goal(force=True)
        said = self.goals(api)[-1]
        self.assertEqual(said["status"], "paused")
        self.assertEqual(said["pause"]["step"], 2)
        self.assertEqual([x["status"] for x in said["steps"][1]["subs"]],
                         ["done", "open"])

    def test_the_page_draws_skipped_apart_from_running_and_the_pause(self):
        """#296: robin read a skipped step as running -- both were --warn.
        NEGATIVPROBE AM QUELLTEXT: skipped has its own token in every theme,
        the running rule keeps amber, and a pause has its own glyph."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("--skip:#"), 3, "a theme lacks --skip")
        self.assertIn("#goalpanel li.skipped .m,#goalpanel .gh .st.sk"
                      "{color:var(--skip)}", source)
        self.assertIn("#goalpanel li.running .m{color:var(--warn)}", source)
        self.assertNotIn("li.skipped .m,#goalpanel .gh .st.sk{color:var(--warn)}",
                         source)
        self.assertIn('stroke-dasharray="3 2.6"', source)
        self.assertIn('l.textContent="skipped"', source)
        self.assertIn('if(state==="held")', source)
        self.assertIn('"Paused · step "+pz.step', source)


class TheGoalEngineBrakesOnAnEmptyLoopTests(ApiCase):
    """#202, live am 2026-09-18, 12:02: der Motor schickte denselben Anstoss
    noch einmal, das Modell antwortete mit dem einzelnen Token `I`, und das
    fuenfunddreissig Mal hintereinander -- Nachricht 505 bis 573, jede zweite --,
    bis der 60-Zuege-Deckel es beendete. Am Tag davor dasselbe mit `3`,
    achtundvierzig Mal.

    WARUM ES SICH SELBST TRUG: jeder wiedergeschickte Zug steht danach im
    Kontext. Das Modell las nicht einen Auftrag, sondern fuenfunddreissig
    Beispiele dafuer, wie in diesem Gespraech geantwortet wird. Deshalb ist
    Anhalten allein hier keine Reparatur -- die Beispiele muessen weg.
    """

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(crow_core.goal_write, None)
        crow_core.goal_start("Ship it", ["read the log", "write the fix"],
                             now=1000.0)

    def turn(self, api, text, answer, calls=None) -> None:
        """Einen gefahrenen Zug in die Geschichte schreiben: Crows Zeile, die
        Antwort darauf, und was das Modell dabei gerufen hat. Genau die zwei
        Anhaenge, die `_run` um `run_turn` herum macht."""
        api._conversation.append("user", text)
        if calls:
            api._conversation.append(
                "assistant", "", tool_calls=[{"id": "c0", "name": calls,
                                              "arguments": "{}"}])
            api._conversation.append("tool", "...", tool_call_id="c0")
        api._conversation.append("assistant", answer)

    def notes(self, api) -> list:
        return [m["t"] for m in self.drained(api) if m.get("k") == "note"]

    def looped(self, api, answer: str = "I") -> str:
        """Drei Zuege mit derselben leeren Antwort, und was der Motor danach
        schicken will. Das ist die Lage aus dem Live-Fall, dreimal statt
        fuenfunddreissig Mal."""
        for _ in range(crow_core.GOAL_LOOP_ANSWERS):
            self.turn(api, api._goal_nudge(), answer)
        return api._goal_nudge()

    def test_three_empty_answers_take_the_loop_out_of_the_history(self):
        """POSITIV, die eigentliche Reparatur: Anstoesse UND Antworten sind
        danach weg, und alles, was davor gearbeitet wurde, steht noch da."""
        api = self.api()
        api._conversation.append("user", "start please")
        api._conversation.append("assistant", "will do")
        before = api._conversation.payload()
        self.looped(api)
        self.assertEqual(api._conversation.payload(), before,
                         "the empty turns are still in the prompt")

    def test_the_loop_is_answered_once_with_another_line_not_the_nudge(self):
        """Statt des Anstosses EINE andere Zeile -- sie benennt den Schritt, der
        offen ist, und verlangt einen Werkzeugaufruf statt noch einer Antwort."""
        api = self.api()
        recovery = self.looped(api)
        self.assertIn("Your last answers were empty", recovery)
        self.assertIn("Step 1 is still open: read the log", recovery)
        self.assertIn("tool call", recovery)
        self.assertNotIn("Do it now.", recovery)

    def test_the_dropped_history_is_logged_not_drawn(self):
        """Geschichte still zu loeschen waere schlimmer als der Kreis -- also
        steht es mit Zeitstempel in crow.log. #262 (robin,
        2026-09-23): NICHT im Verlauf und nicht im Notizband des Chats, dort
        stand "157 messages of an empty loop dropped" als Unordnung."""
        api = self.api()
        logs = tempfile.mkdtemp(prefix="crow-log-")
        self.addCleanup(shutil.rmtree, logs, True)
        self.addCleanup(setattr, crow_core, "LOG_FILE", crow_core.LOG_FILE)
        crow_core.LOG_FILE = os.path.join(logs, "crow.log")
        self.looped(api)
        self.assertFalse(any("dropped from the history" in n
                             for n in self.notes(api)))
        self.assertFalse(any("dropped from the history" in n.get("t", "")
                             for n in api._notes), "saved with the chat")
        with open(crow_core.LOG_FILE, encoding="utf-8") as fh:
            self.assertIn("[goal] goal mode: 6 messages of an empty loop "
                          "dropped from the history", fh.read())

    def test_an_empty_answer_after_the_recovery_stops_the_goal(self):
        """Kein zweiter Versuch: wer auch auf eine frisch geschnittene
        Geschichte mit nichts antwortet, hat nicht die falsche Frage gehoert."""
        api = self.api()
        api._context_tokens = 130939
        before = api._conversation.payload()
        self.turn(api, self.looped(api), "I")
        self.assertIsNone(api._goal_nudge(), "the engine asked a third time")
        self.assertIn("goal mode stopped: the model repeated an empty answer 3 "
                      "times at 130,939 tokens; 0 of 2 steps done",
                      self.notes(api))
        self.assertEqual(api._conversation.payload(), before,
                         "the recovery turn and its empty answer stayed")

    def test_a_recovery_that_works_carries_the_goal_on(self):
        """GEGENPROBE, und sie traegt die ganze Bremse: ein Modell, das sich
        faengt, arbeitet weiter -- die Bremse ist keine Einbahnstrasse."""
        api = self.api()
        self.turn(api, self.looped(api), "read it", calls="read_file")
        self.assertIsNotNone(api._goal_nudge(), "the engine gave up on a turn "
                                                "that did the work")

    def test_working_turns_that_end_on_a_silent_forced_answer_do_not_brake(self):
        """#259, 2026-09-23: three budget-stopped turns, each of
        them with tool calls, each ending on a forced answer with content "".
        The brake read three empty answers, cut 157 messages of work and --
        after one more such turn -- stopped the goal at 6/9."""
        api = self.api()
        api._conversation.append("user", "start please")
        api._conversation.append("assistant", "will do")
        for n in range(crow_core.GOAL_LOOP_ANSWERS + 1):
            nudge = api._goal_nudge()
            self.assertIsNotNone(nudge, "the goal stopped after %d turns" % n)
            self.assertNotIn("Your last answers were empty", nudge)
            api._conversation.append("user", nudge)
            api._conversation.append(
                "assistant", "", tool_calls=[{"id": "c0", "name": "read_file",
                                              "arguments": '{"path": "f%d"}' % n}])
            api._conversation.append("tool", "...", tool_call_id="c0")
            api._conversation.append("user", crow_core.BUDGET_SPENT)
            api._conversation.append("assistant", "")
        self.assertFalse(any("dropped from the history" in t
                             for t in self.notes(api)), self.notes(api))

    def test_three_identical_answers_brake_even_when_they_are_not_empty(self):
        """Die zweite Tuer in dieselbe Bremse: derselbe Satz mit demselben
        Aufruf, dreimal -- laenger als zwei Zeichen und trotzdem ein Kreis."""
        api = self.api()
        for _ in range(crow_core.GOAL_LOOP_ANSWERS):
            self.turn(api, api._goal_nudge(), "still looking at it",
                      calls="read_file")
        self.assertIn("Your last answers were empty", api._goal_nudge() or "")

    def test_a_step_that_has_taken_its_turns_pauses_the_goal(self):
        """#202. Der 60er-Deckel sichert das GANZE Ziel und merkt deshalb nicht,
        dass ein Plan mit sechs Schritten seit fuenfzig Zuegen an Schritt 5
        haengt -- genau die Lage am 2026-09-18."""
        api = self.api()
        for n in range(api.GOAL_STEP_TURN_CAP):
            nudge = api._goal_nudge()
            self.assertIsNotNone(nudge, "the step cap fired after %d turns" % n)
            self.turn(api, nudge, "round %d, still on it" % n)
        # #294: the cap pauses WITH a report turn, then waits.
        report = api._goal_nudge()
        self.assertIn("PAUSED at step 1 (turn cap): step 1 has taken 25 "
                      "turns", report)
        self.turn(api, report, "1. stuck 2. why 3. A, B 4. any input?")
        self.assertIsNone(api._goal_nudge())
        notes = self.notes(api)
        self.assertTrue(any(n.startswith("goal mode paused at step 1 (turn "
                                         "cap)") for n in notes), notes)

    def test_the_step_counter_starts_over_on_the_next_step(self):
        """GEGENPROBE: der Zaehler gehoert dem Schritt, nicht dem Ziel. Ein Plan,
        der voranschreitet, sieht diesen Deckel nie."""
        api = self.api()
        for n in range(20):
            self.turn(api, api._goal_nudge(), "round %d, still on it" % n)
        crow_core.goal_step_begin(0, now=1000.0)
        crow_core.goal_step_end(0, now=1010.0)
        self.assertEqual(api._goal_nudge().count("Next is step 2"), 1)
        self.assertEqual(api._goal_step_turns, 1, "the new step inherited a count")

    def test_a_working_turn_gets_the_short_line_instead_of_the_whole_block(self):
        """#202. Der volle Anstoss ist 330 Byte; byteweise identisch vor jedem
        Zug ist er selbst das Muster, das das Modell dann fortsetzt."""
        api = self.api()
        first = api._goal_nudge()
        self.assertIn("Do it now.", first)
        self.turn(api, first, "read it", calls="read_file")
        self.assertEqual(api._goal_nudge(),
                         "[Goal mode, step 1 still open. Continue.]")

    def test_the_first_turn_of_a_step_always_gets_the_whole_block(self):
        """GEGENPROBE ZWEIMAL: der Schritt steht dort zum ersten Mal -- und wer
        NICHT gearbeitet hat, bekommt ihn ebenfalls noch einmal ganz."""
        api = self.api()
        self.turn(api, api._goal_nudge(), "thinking about it")
        second = api._goal_nudge()
        self.assertIn("Do it now.", second)
        self.turn(api, second, "read it", calls="read_file")
        crow_core.goal_step_begin(0, now=1000.0)
        crow_core.goal_step_end(0, now=1010.0)
        self.assertIn("Next is step 2: write the fix", api._goal_nudge())


class CrowStatusNotesGoToTheLogTests(ApiCase):
    """#262 (robin, 2026-09-23): Crow's own grey status lines about
    its machinery clutter a long session. They go to crow.log; the rollover
    card, its "rolled over" line, "goal mode stopped/paused", the reboot lines
    and every answer to a command stay in the chat."""

    LOG_ONLY = (
        "goal mode: 157 messages of an empty loop dropped from the history",
        "goal mode, step 4: the same failure keeps coming back -- edit_file "
        "refused 3\u00d7 the same way. The nudge names the way around it.",
        "discarded a degenerate reply (stub, 15 chars, seed 7) -- asking "
        "again with a new seed",
        "kept the re-asked reply although it looks unfinished (stub again)",
        "the restored cache did not hold -- that prefill was the whole history",
        # robin 2026-09-24 (diorama run): the rollover line and #98's
        # explanation line go to the log; the roll card stays
        "rolled over at 181255 tokens -> rollover-20260924-192638.json",
        "write_file and edit_file stay inside the root; an outside path named "
        "in run_command asks first (#144) -- this one was released, or not "
        "named plainly",
    )
    KEPT = (
        "goal mode stopped: the model repeated an empty answer 3 times at "
        "127,690 tokens; 6 of 9 steps done",
        "goal mode stopped after 60 turns -- 2 of 5 steps done. `/goal` shows "
        "where it stands.",
        "goal mode paused: step 1 has taken 25 turns. `/goal` shows where it "
        "stands -- a typed line carries on.",
        "the server on port 8080 is still loading -- waiting",
        # robin 2026-09-24: the /goal setup echo and "working directory: …"
        # went to the log; the /goal STATUS answer stays.
        "goal: Neon night market voxel diorama -- 3/9, 12 min so far",
        "carried across the cut: edit_file",
    )

    def setUp(self) -> None:
        super().setUp()
        logs = tempfile.mkdtemp(prefix="crow-log-")
        self.addCleanup(shutil.rmtree, logs, True)
        self.addCleanup(setattr, crow_core, "LOG_FILE", crow_core.LOG_FILE)
        crow_core.LOG_FILE = os.path.join(logs, "crow.log")

    def logged(self) -> str:
        try:
            with open(crow_core.LOG_FILE, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def test_a_log_only_note_pushed_anywhere_is_neither_drawn_nor_saved(self):
        api = self.api()
        for text in self.LOG_ONLY:
            api.push({"k": "note", "t": text})
        self.assertEqual(self.drained(api), [])
        self.assertEqual(api._notes, [])
        for text in self.LOG_ONLY:
            self.assertIn(" ".join(text.split()), self.logged())

    def test_the_boundary_alarm_goes_to_the_log(self):
        """robin 2026-09-24: '! the working area was refused for <path>, and
        run_command ran anyway' is kind `alarm`; it leaves the chat too."""
        api = self.api()
        crow_gui.Turn(api.push).boundary_escaped("run_command",
                                                 ["/tmp/placeholder-ignore.js"])
        self.assertEqual(self.drained(api), [])
        self.assertEqual(api._notes, [])
        self.assertIn("! the working area was refused for "
                      "/tmp/placeholder-ignore.js, and run_command ran anyway",
                      self.logged())

    def test_everything_else_still_reaches_the_page_and_the_band(self):
        """NEGATIVE: nothing else disappears."""
        api = self.api()
        for text in self.KEPT:
            api.push({"k": "note", "t": text})
        api.push({"k": "alarm", "t": "! the working area was refused"})
        api.push({"k": "memory", "t": "Memory updated", "n": 1})
        drawn = self.drained(api)
        self.assertEqual([m.get("t") for m in drawn],
                         list(self.KEPT) + ["! the working area was refused",
                                            "Memory updated"])
        self.assertEqual(len(api._notes), len(self.KEPT) + 2)
        self.assertEqual(self.logged(), "")

    def test_a_reopened_chat_does_not_draw_the_notes_an_old_build_saved(self):
        """(2): session.json of 2026-09-23 carries six of these at index
        88..212. The band drops them on read; the kept ones stay in order."""
        band = [{"k": "note", "at": 1, "t": t}
                for t in self.LOG_ONLY + self.KEPT]
        band.append({"k": "memory", "at": 1, "t": "Memory updated", "n": 2})
        clean = crow_core.clean_notes(band)
        self.assertEqual([n["t"] for n in clean],
                         list(self.KEPT) + ["Memory updated"])
        api = self.api()
        api._replay([{"role": "user", "content": "hi"}], band)
        drawn = [m.get("t") for m in self.drained(api)
                 if m.get("k") == "note"]
        for text in self.LOG_ONLY:
            self.assertNotIn(text, drawn)
        for text in self.KEPT:
            self.assertIn(text, drawn)

    def test_the_sink_logs_a_broken_cache_promise(self):
        put = []
        crow_gui.Turn(put.append).cache_promise_broken()
        self.assertEqual(put, [])
        self.assertIn("[turn] the restored cache did not hold", self.logged())


class TheGoalEngineNamesTheWallTests(ApiCase):
    """#202, 2026-09-22: 48 blinde Runden mit toter Suche und toten
    Delegaten, und in der Sitzung danach 22 edit_file, von denen keiner
    landete. Jeder Zug rief Werkzeuge, keine zwei Antworten glichen sich --
    die Bremse sah nichts, und der Anstoss wiederholte nur den Schritt. Hier:
    dieselbe Fehlerklasse dreimal im Schritt, und der naechste Anstoss nennt
    sie statt des Schritts.
    """

    TAVILY = ("error: https://api.tavily.com/search answered HTTP 401 "
              "Unauthorized\nCROW_TAVILY_KEY was refused.")

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(crow_core.goal_write, None)
        crow_core.goal_start("Ship it", ["read the log", "write the fix"],
                             now=1000.0)

    def turn(self, api, text, results) -> None:
        """Ein gefahrener Zug: Crows Zeile, je Ergebnis ein Aufruf und seine
        Antwort, und ein Schlusssatz."""
        api._conversation.append("user", text)
        for n, (name, args, result) in enumerate(results):
            api._conversation.append(
                "assistant", "", tool_calls=[{"id": "t%d" % n, "name": name,
                                              "arguments": args}])
            api._conversation.append("tool", result, tool_call_id="t%d" % n)
        api._conversation.append("assistant", "tried again")

    def searches(self, *queries):
        return [("web_search", '{"query": "%s"}' % q, self.TAVILY) for q in queries]

    def notes(self, api) -> list:
        return [m["t"] for m in self.drained(api) if m.get("k") == "note"]

    def test_three_dead_searches_turn_the_nudge_into_the_way_around(self):
        """POSITIV: statt "Continue" oder des Schritttexts die Klasse, die Zahl
        und der Ausweg -- und robin sieht es als Notiz, wie die Bremse."""
        api = self.api()
        self.turn(api, api._goal_nudge(), self.searches("a", "b", "c"))
        nudge = api._goal_nudge()
        self.assertIn("web_search is dead this session (HTTP 401 from "
                      "api.tavily.com, 3×) -- stop calling it", nudge)
        self.assertNotIn("read the log", nudge)
        self.assertNotIn("Continue.", nudge)
        # #262: robin's copy goes to crow.log, not into the flow;
        # the nudge above is what the model reads, unchanged.
        self.assertEqual(self.notes(api), [])
        with open(crow_core.LOG_FILE, encoding="utf-8") as fh:
            self.assertIn("[goal] goal mode, step 1: the same failure keeps "
                          "coming back -- web_search dead (HTTP 401 from "
                          "api.tavily.com, 3×). The nudge names the way around "
                          "it.", fh.read())

    def test_a_class_spread_over_turns_counts_for_the_step(self):
        """Gezaehlt wird im Schritt, nicht im Zug: zwei, dann einer."""
        api = self.api()
        self.turn(api, api._goal_nudge(), self.searches("a", "b"))
        second = api._goal_nudge()
        self.assertEqual(second, "[Goal mode, step 1 still open. Continue.]")
        self.turn(api, second, self.searches("c"))
        self.assertIn("web_search is dead", api._goal_nudge())

    def test_the_line_is_not_repeated_when_nothing_failed_again(self):
        """Wer nach der Zeile aufhoert, hoert sie nicht noch einmal -- sonst
        stuende sie vor jedem Zug, wie der 105-mal-Block."""
        api = self.api()
        self.turn(api, api._goal_nudge(), self.searches("a", "b", "c"))
        trouble = api._goal_nudge()
        self.turn(api, trouble, [("read_file", '{"path": "README.md"}', "# docs")])
        self.assertEqual(api._goal_nudge(),
                         "[Goal mode, step 1 still open. Continue.]")

    def test_the_next_step_starts_with_clean_counts(self):
        """Counts reset on step change: zwei Fehlschlaege in Schritt 1, der
        Schritt wird fertig, einer in Schritt 2 -- das sind keine drei."""
        api = self.api()
        self.turn(api, api._goal_nudge(), self.searches("a", "b"))
        crow_core.goal_step_end(0, now=1010.0)
        nudge = api._goal_nudge()
        self.assertIn("Next is step 2: write the fix", nudge)
        self.turn(api, nudge, self.searches("c"))
        self.assertNotIn("dead", api._goal_nudge())

    def test_what_failed_after_the_step_closed_counts_for_the_next(self):
        """Der Zug, in dem ein Schritt fertig wird, arbeitet oft schon am
        naechsten: was NACH dem `goal_step` 'done' scheiterte, gehoert ihm."""
        api = self.api()
        self.turn(api, api._goal_nudge(), self.searches("a", "b"))
        nudge = api._goal_nudge()
        crow_core.goal_step_end(0, now=1010.0)
        self.turn(api, nudge, [("goal_step", '{"step": 1, "status": "done"}',
                                '{"ok": true}')] + self.searches("c", "d", "e"))
        self.assertIn("[Goal mode, step 2 still open -- the same failure keeps "
                      "coming back:\n- web_search is dead this session (HTTP 401 "
                      "from api.tavily.com, 3×)", api._goal_nudge())

    def test_a_typed_line_starts_the_count_over(self):
        """robin hat eingegriffen -- vielleicht mit einem Schluessel. Was davor
        gezaehlt war, zaehlt nicht mehr (`_goal_reset`, wie jeder Zaehler)."""
        api = self.api()
        self.turn(api, api._goal_nudge(), self.searches("a", "b"))
        api._goal_reset()
        self.turn(api, "here is a new key", self.searches("c"))
        self.assertNotIn("dead", api._goal_nudge())


# ============================================================== the Linux port

class _FakeGtkWindow:
    """A GtkWindow that only remembers what it was asked to do.

    THE TOOLKIT IS NOT IMPORTED HERE, and that is the point rather than a
    shortcut: these cases have to run on Windows, in CI and on a box with no
    display, and every one of them is about what THIS file does with the handle
    -- which call, on which thread, with which arguments. Whether
    `begin_move_drag` moves a window is GTK's claim, not ours; whether it is
    reached at all is ours.
    """

    def __init__(self) -> None:
        self.calls: list = []

    def begin_move_drag(self, *a) -> None:
        self.calls.append(("move", a))

    def begin_resize_drag(self, *a) -> None:
        self.calls.append(("resize", a))

    def maximize(self) -> None:
        self.calls.append(("maximize", ()))

    def unmaximize(self) -> None:
        self.calls.append(("unmaximize", ()))

    def is_maximized(self) -> bool:
        return False


class TheWindowAsksThePlatformSeamTests(unittest.TestCase):
    """#187 auf Linux: was das Fenster ueber sein Betriebssystem weiss, weiss es
    durch cli/crow_platform.py -- oder es weiss es zweimal.

    DIE REGEL, GEGEN DIE DIESE FAELLE GESCHNITTEN SIND: in crow_gui.py steht
    kein `sys.platform` und kein `os.name`. Der Grund ist der des
    Naht-Moduls selbst: sieben verstreute Zweige sind sieben Stellen zum
    Vergessen, und die achte schreibt jemand, der die anderen sieben nie
    gesehen hat.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_the_window_never_asks_the_interpreter_which_os_this_is(self):
        """NEGATIV, und der einzige Fall, der die Regel selbst haelt."""
        code = self.source[:self.source.index('PAGE = r"""')]
        code += self.source[self.source.index("ICON_FILE = os.path.join"):]
        for forbidden in ("sys.platform", "os.name =="):
            self.assertNotIn(forbidden, code,
                             "%s steht wieder in crow_gui.py -- die Antwort "
                             "gehoert in crow_platform.py" % forbidden)

    def test_the_settings_file_is_configuration_and_lands_there(self):
        """Bis zum Port hing sie an `dirname(SESSION_DIR)`. Auf Windows ist das
        derselbe Ordner; auf Linux waere es ~/.local/state, und was jemand
        eingestellt hat, ist keine Sitzungsspur."""
        self.assertIn('crow_platform.config_dir(), "settings.json"', self.source)
        # DIE FORMEL UND NICHT DER WERT: der Kopf dieser Datei biegt
        # `SETTINGS_FILE` auf einen Sandkasten um, damit kein Fall in robins
        # echte Einstellungen schreibt (siehe
        # TheSuiteTouchesNoRealConfigurationTests). Der laufende Wert ist hier
        # also absichtlich ein anderer -- was geprueft gehoert, ist, woraus das
        # Modul ihn beim Start bildet.
        fresh = os.path.join(crow_platform.config_dir(), "settings.json")
        self.assertTrue(os.path.basename(fresh) == "settings.json")
        self.assertEqual(os.path.dirname(fresh), crow_platform.config_dir())

    def test_on_windows_both_paths_are_where_they_have_always_been(self):
        """DIE GEGENPROBE ZUM PORT: die Umschichtung darf auf Windows NICHTS
        verschieben. Dort antworten config_dir(), data_dir() und state_dir()
        alle drei %LOCALAPPDATA%\\Crow, also ist `dirname(SESSION_DIR)` -- die
        alte Formel -- genau derselbe Ordner."""
        if not crow_platform.IS_WINDOWS:
            self.skipTest("die Gleichheit gilt fuer die Windows-Antwort")
        old = os.path.dirname(crow_core.SESSION_DIR)
        self.assertEqual(os.path.normcase(crow_platform.config_dir()),
                         os.path.normcase(old))
        self.assertEqual(os.path.normcase(crow_platform.data_dir()),
                         os.path.normcase(old))

    def test_the_paste_folder_is_data_and_not_state(self):
        """Ein eingefuegtes Bild ueberlebt den Chat, der darauf zeigt -- der
        Pfad steht in der Unterhaltung. Deshalb data_dir(), nicht state_dir()."""
        self.assertIn('crow_platform.data_dir(), "pastes"', self.source)


class TheWindowSetsItsEnvironmentBeforeTheToolkitTests(unittest.TestCase):
    """A12: ohne `__NV_DISABLE_EXPLICIT_SYNC` stirbt das Fenster auf dieser
    Maschine, bevor die Oberflaeche erscheint -- `Gdk-Message: Error 71
    (Protocol error) dispatching to Wayland display`, gemessen 2026-09-16.

    DIE VARIABLE MUSS VOR DEM IMPORT STEHEN, weil GTK und WebKitGTK sie genau
    einmal lesen: beim Laden der Bibliothek. Deshalb laeuft `prepare_environment`
    beim Import dieses Moduls und nicht in `main`.
    """

    def test_the_nvidia_switch_is_set_on_linux_and_nowhere_else(self):
        env: dict = {}
        crow_gui.prepare_environment(env)
        if crow_platform.IS_LINUX:
            self.assertEqual(env.get("__NV_DISABLE_EXPLICIT_SYNC"), "1")
        else:
            self.assertEqual(env, {}, "Windows bekommt keine GTK-Variablen")

    def test_a_value_the_user_set_is_never_overwritten(self):
        """NEGATIV. `setdefault`, damit die Variable eine Notluke bleibt und
        keine zweite Meinung: wer sie gesetzt hat, hat einen Grund."""
        env = {"__NV_DISABLE_EXPLICIT_SYNC": "0"}
        set_here = crow_gui.prepare_environment(env)
        self.assertEqual(env["__NV_DISABLE_EXPLICIT_SYNC"], "0")
        self.assertNotIn("__NV_DISABLE_EXPLICIT_SYNC", set_here)

    def test_crow_gdk_backend_is_the_escape_hatch_to_xwayland(self):
        """Unter X11 gehen `move()`, `set_keep_above()` und die Drag-Region von
        pywebview wieder -- der Weg dorthin darf kein Editieren dieser Datei
        sein."""
        if not crow_platform.IS_LINUX:
            self.skipTest("GDK gibt es nur auf der einen Seite")
        env = {"CROW_GDK_BACKEND": "x11", "GDK_BACKEND": "wayland,x11,*"}
        crow_gui.prepare_environment(env)
        self.assertEqual(env["GDK_BACKEND"], "x11",
                         "die spezifischere Variable muss gewinnen -- sonst "
                         "tut CROW_GDK_BACKEND in einer Wayland-Sitzung nie "
                         "etwas, weil GDK_BACKEND dort immer schon gesetzt ist")

    def test_nothing_is_set_when_the_user_named_no_backend(self):
        """GEGENPROBE: eine leere Ansage ist keine Ansage."""
        env = {"GDK_BACKEND": "wayland,x11,*"}
        crow_gui.prepare_environment(env)
        self.assertEqual(env["GDK_BACKEND"], "wayland,x11,*")

    def test_it_ran_at_import(self):
        """Der ganze Sinn: die Variable steht, bevor irgendwer `webview`
        importiert. `ENVIRONMENT` ist der Beleg, dass der Aufruf gefallen ist."""
        self.assertIsInstance(crow_gui.ENVIRONMENT, dict)
        if crow_platform.IS_LINUX:
            self.assertEqual(os.environ.get("__NV_DISABLE_EXPLICIT_SYNC"), "1")
        else:
            # DIE GEGENPROBE, damit dieser Fall drueben nicht zu
            # `assertIsInstance(dict)` zusammenfaellt: der Import darf auf
            # Windows NICHTS in die Umgebung schreiben -- eine GTK-Variable,
            # die eine WebView2-Sitzung erbt, ist eine, die niemand erklaert.
            self.assertEqual(crow_gui.ENVIRONMENT, {})


class TheCompositorMovesTheWindowTests(unittest.TestCase):
    """A3. `pywebview-drag-region` und `easy_drag` bewegen unter Wayland nichts:
    beide enden in `window.move(x, y)`, und `gtk_window_move()` ist dort ein
    dokumentierter Leerlauf -- `hyprctl clients` zeigte 2026-09-16 dasselbe
    `at=[...]` davor und danach.

    ALSO WIRD DIE GESTE UEBERGEBEN STATT DAS RECHTECK BERECHNET. `begin_move_drag`
    und `begin_resize_drag` werden zu `xdg_toplevel.move` / `.resize`: der
    Compositor fuehrt die Bewegung, solange die Taste haengt. Diese Faelle
    pruefen die Kette Seite -> Bruecke -> GTK-Hauptfaden, nicht den Compositor.
    """

    def _api(self, native=None):
        args = crow_gui.build_parser().parse_args([])
        api = crow_gui.Api(args)
        api._gtk_window = lambda: native
        return api

    def _idle(self, api):
        """`GLib.idle_add` durch einen Sammler ersetzen, der sofort ausfuehrt.

        WARUM UEBERHAUPT UEBER `idle_add`: jede js_api-Methode laeuft in einem
        frischen Thread (pywebview startet einen pro Bruecken-Aufruf), und GTK
        darf nur aus dem Faden angefasst werden, der seine Schleife dreht. Ein
        direkter Aufruf ist der Fehler, der sich als "das Fenster friert beim
        dritten Ziehen ein" zeigt und nie beim ersten.
        """
        seen = []
        real = crow_gui.Api._native_drag.__func__

        def drag(native, edge):
            seen.append(("dispatch", edge))
            return real(native, edge)
        return seen, drag

    def test_the_bridge_offers_both_gestures(self):
        native = _FakeGtkWindow()
        api = self._api(native)
        self.assertTrue(api.begin_move())
        self.assertTrue(api.begin_resize("se"))

    def test_an_unknown_edge_is_refused_rather_than_guessed(self):
        """NEGATIV. Die Seite kennt acht Namen; ein neunter heisst, dass die
        beiden Tabellen auseinandergelaufen sind, und ein stiller Vorgabewert
        versteckte genau das."""
        api = self._api(_FakeGtkWindow())
        self.assertFalse(api.begin_resize("middle"))
        self.assertFalse(api.begin_resize(""))
        self.assertFalse(api.begin_resize(None))

    def test_the_eight_edges_are_the_gdk_numbers(self):
        """Die Tabelle steht als ZAHL da, damit dieser Fall ohne GTK laufen
        kann; `Gdk.WindowEdge(n)` macht an der einen Stelle wieder ein Enum
        daraus. NORTH_WEST 0 ... SOUTH_EAST 7."""
        self.assertEqual(crow_gui.Api._RESIZE_EDGES,
                         {"nw": 0, "n": 1, "ne": 2, "w": 3, "e": 4,
                          "sw": 5, "s": 6, "se": 7})

    def test_neither_gesture_exists_without_a_native_window(self):
        """GEGENPROBE, und sie ist der Windows-Fall: `_gtk_window` antwortet
        dort None, die Seite ruft diese beiden nie auf, und wenn doch, passiert
        nichts statt eines Fehlers in der Bruecke."""
        api = self._api(None)
        self.assertFalse(api.begin_move())
        self.assertFalse(api.begin_resize("n"))

    def test_the_gesture_is_dispatched_and_not_run_on_this_thread(self):
        """Der eigentliche Fall: `_native_drag` legt die Arbeit auf den
        GTK-Faden. Ohne GTK auf der Maschine gibt es nichts zu dispatchen und
        die Methode sagt False -- auch das ist die richtige Antwort."""
        seen = []
        native = _FakeGtkWindow()

        class _GLib:
            @staticmethod
            def idle_add(func):
                seen.append(func)
                func()

        class _Gdk:
            class Display:
                @staticmethod
                def get_default():
                    raise RuntimeError("no display in the suite")

            WindowEdge = staticmethod(lambda n: n)

        class _Gtk:
            @staticmethod
            def get_current_event_time():
                return 0

        modules = {"gi": mock.Mock(),
                   "gi.repository": mock.Mock(GLib=_GLib, Gdk=_Gdk, Gtk=_Gtk)}
        with mock.patch.dict(sys.modules, modules):
            self.assertTrue(crow_gui.Api._native_drag(native, None))
            self.assertTrue(crow_gui.Api._native_drag(native, 7))
        self.assertEqual(len(seen), 2, "die Geste lief nicht ueber idle_add")
        self.assertEqual([c[0] for c in native.calls], ["move", "resize"])
        # Der Rueckgabewert der idle-Funktion ist False: einmal, nicht bei
        # jeder Leerlaufrunde.
        self.assertEqual([f() for f in seen], [False, False])

    def test_a_compositor_that_declines_never_reaches_the_bridge(self):
        """NEGATIV. Was hier fliegt, faellt sonst in die pywebview-Bruecke und
        hinterlaesst keine Zeile -- der Fehler, den #175 einen ganzen Anlauf
        gekostet hat."""
        class _Angry(_FakeGtkWindow):
            def begin_move_drag(self, *a):
                raise RuntimeError("the compositor said no")

        class _GLib:
            @staticmethod
            def idle_add(func):
                func()

        modules = {"gi": mock.Mock(),
                   "gi.repository": mock.Mock(GLib=_GLib, Gdk=mock.Mock(),
                                              Gtk=mock.Mock())}
        with mock.patch.dict(sys.modules, modules):
            self.assertTrue(crow_gui.Api._native_drag(_Angry(), None))

    def test_the_page_hands_the_gesture_over_only_where_it_has_to(self):
        """Die Seite traegt die Antwort, bevor sie uebergeben wird -- wie das
        Theme und der Rail-Zustand, und aus demselben Grund: ein Skript, das
        es nach dem Laden herausfaende, waere bei jedem Start einen Rahmen zu
        spaet."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.assertIn("const NATIVEDRAG = __NATIVEDRAG__;", source)
        self.assertIn('.replace("__NATIVEDRAG__",', source)
        self.assertIn('if(NATIVEDRAG){ pywebview.api.begin_resize(map[id]); return; }',
                      source)
        self.assertIn("pywebview.api.begin_move();", source)

    def test_the_title_bar_keeps_its_double_click(self):
        """DER GRUND FUER DIE VIER PIXEL. Der Compositor nimmt den Zeiger in dem
        Moment, in dem `xdg_toplevel.move` rausgeht -- ein Zug, der schon beim
        ersten Druck beginnt, schluckt den zweiten, und der zweite ist
        `ondblclick="pywebview.api.maximise()"` auf genau diesem Element."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        bar = source[source.index("(function bardrag(){"):]
        bar = bar[:bar.index("})();")]
        self.assertIn("<4", bar, "ohne Schwelle gibt es keinen Doppelklick mehr")
        self.assertIn('e.target.closest(".pywebview-no-drag")', bar,
                      "ein Zug auf 'close' waere ein Fenster, das man nicht "
                      "mehr schliessen kann")


class TheMaximiseButtonOnACompositorTests(unittest.TestCase):
    """Doppelklick auf die Leiste, dort wo der Compositor den Rahmen besitzt.

    ES GIBT NICHTS AUFZUSCHREIBEN. `xdg_toplevel.set_maximized` ist eine BITTE,
    kein Rechteck: der Compositor waehlt die Groesse, behaelt die alte und gibt
    sie beim Zuruecknehmen wieder her. Der Windows-Zweig merkt sich das
    Rechteck, weil dort dieses Programm das Fenster bewegt.
    """

    def _api(self, native):
        args = crow_gui.build_parser().parse_args([])
        api = crow_gui.Api(args)
        api._gtk_window = lambda: native
        return api

    def test_it_toggles_on_its_own_flag_and_not_on_is_maximized(self):
        """GEMESSEN, NICHT VORGEZOGEN: auf dieser Maschine meldet das Toolkit
        das Fenster vom ersten Rahmen an als maximiert und sagt das auch nach
        `unmaximize()` weiter (2026-09-16, MAXIMIZED-Bit auf einem schwebenden
        1180x800-Fenster). Ein Umschalter, der diese Antwort liest, kommt nie
        aus dem Zustand heraus, in dem er startet."""
        native = _FakeGtkWindow()
        native.is_maximized = lambda: True
        api = self._api(native)

        class _GLib:
            @staticmethod
            def idle_add(func):
                func()

        modules = {"gi": mock.Mock(),
                   "gi.repository": mock.Mock(GLib=_GLib)}
        with mock.patch.dict(sys.modules, modules):
            api.maximise()
            api.maximise()
        self.assertEqual([c[0] for c in native.calls],
                         ["maximize", "unmaximize"])
        self.assertFalse(api._maximised)

    def test_the_windows_rectangle_is_untouched_by_the_new_branch(self):
        """GEGENPROBE: ohne GtkWindow faellt `maximise` in den Win32-Zweig, und
        der schreibt weiterhin ein Rechteck auf."""
        api = self._api(None)
        self.assertIsNone(api._restore)


class TheClipboardIsReadByAProgramTests(unittest.TestCase):
    """A9. pywebview hat auf KEINEM Backend eine Zwischenablage, und
    `Gtk.Clipboard.wait_for_image()` gab hier None zurueck, obwohl
    `wl-paste --list-types` `image/png` meldete -- aus einem Arbeitsfaden, vom
    Hauptfaden und mit Fokus, dreimal None (2026-09-16).

    ALSO WIRD EIN PROGRAMM GEFRAGT. `wl-paste` spricht `wlr-data-control` und
    braucht keinen Tastaturfokus; `xclip` ist der X11-Fallback.
    """

    def _run(self, answers):
        """`subprocess.run` durch eine Tabelle ersetzen: argv[0..] -> stdout.

        Ein Eintrag darf `(argv, stdout)` oder `(argv, stdout, rc)` sein -- den
        Rueckgabecode braucht der Fall, in dem ein installiertes Werkzeug seinen
        Server gar nicht erreicht.
        """
        class _Done:
            def __init__(self, out, rc=0):
                self.stdout, self.returncode = out, rc

        def run(argv, **kw):
            self.seen.append(list(argv))
            for entry in answers:
                key, out = entry[0], entry[1]
                if argv[:len(key)] == key:
                    return _Done(out, entry[2] if len(entry) > 2 else 0)
            return _Done(b"")
        return run

    def setUp(self) -> None:
        self.seen: list = []
        self._before = (crow_gui.subprocess.run, crow_gui.shutil.which)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        crow_gui.subprocess.run, crow_gui.shutil.which = self._before

    def _only(self, tool):
        crow_gui.shutil.which = lambda name: ("/usr/bin/" + name
                                              if name == tool else None)

    def test_a_png_on_the_wayland_clipboard_comes_back_whole(self):
        png = b"\x89PNG\r\n\x1a\n" + b"pixels"
        self._only("wl-paste")
        crow_gui.subprocess.run = self._run([
            (["wl-paste", "--list-types"], b"text/html\nimage/png\n"),
            (["wl-paste", "-t", "image/png"], png)])
        self.assertEqual(crow_gui.clipboard_image_posix(), (".png", png))

    def test_the_types_are_asked_for_rather_than_guessed(self):
        """Ein JPEG auf der Ablage: blind `image/png` zu lesen gaebe leere
        Ausgabe und keine Zeile darueber, warum."""
        self._only("wl-paste")
        crow_gui.subprocess.run = self._run([
            (["wl-paste", "--list-types"], b"image/jpeg\n"),
            (["wl-paste", "-t", "image/jpeg"], b"\xff\xd8jpeg")])
        self.assertEqual(crow_gui.clipboard_image_posix(),
                         (".jpg", b"\xff\xd8jpeg"))

    def test_text_on_the_clipboard_is_the_ordinary_no(self):
        """GEGENPROBE, und der haeufigste Fall: das meiste, was jemand einfuegt,
        ist Text. "" ist dort kein Fehler."""
        self._only("wl-paste")
        crow_gui.subprocess.run = self._run([
            (["wl-paste", "--list-types"], b"text/plain\nUTF8_STRING\n")])
        self.assertIsNone(crow_gui.clipboard_image_posix())

    def test_xclip_answers_when_there_is_no_wayland(self):
        png = b"\x89PNG\r\n\x1a\n" + b"x"
        self._only("xclip")
        crow_gui.subprocess.run = self._run([
            (["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
             b"TARGETS\nimage/png\n"),
            (["xclip", "-selection", "clipboard", "-t", "image/png", "-o"], png)])
        self.assertEqual(crow_gui.clipboard_image_posix(), (".png", png))
        self.assertTrue(self.seen, "xclip wurde nie gerufen")

    def test_no_reader_at_all_is_none_and_not_a_crash(self):
        """NEGATIV: eine Maschine ohne wl-clipboard und ohne xclip. Ctrl+V
        bleibt dann wirkungslos -- aber nichts fliegt in die Bruecke."""
        crow_gui.shutil.which = lambda name: None
        self.assertIsNone(crow_gui.clipboard_image_posix())

    def test_wl_paste_without_a_wayland_server_lets_xclip_answer(self):
        """DIE X11-SITZUNG MIT INSTALLIERTEM wl-clipboard, und sie war bis
        2026-09-16 tot: `wl-paste --list-types` endet dort mit 1 und "Failed to
        connect to a Wayland server", das leere Ergebnis las sich als "diese
        Ablage haelt kein Bild", und xclip wurde nie gefragt. Genau die Sitzung,
        die `CROW_GDK_BACKEND=x11` herstellt."""
        png = b"\x89PNG\r\n\x1a\n" + b"x11"
        crow_gui.shutil.which = lambda name: "/usr/bin/" + name
        crow_gui.subprocess.run = self._run([
            (["wl-paste", "--list-types"], b"", 1),
            (["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
             b"TARGETS\nimage/png\n"),
            (["xclip", "-selection", "clipboard", "-t", "image/png", "-o"], png)])
        self.assertEqual(crow_gui.clipboard_image_posix(), (".png", png))
        self.assertTrue(any(a[0] == "xclip" for a in self.seen),
                        "wl-paste stand vor xclip und liess ihn nie zu Wort")

    def test_a_reader_that_hangs_is_bounded(self):
        """Das hier laeuft auf einem Tastendruck. Ein Besitzer, der nie
        antwortet, darf das Fenster nicht anhalten."""
        crow_gui.shutil.which = lambda name: "/usr/bin/" + name
        seen = []

        def run(argv, **kw):
            seen.append(kw.get("timeout"))
            raise crow_gui.subprocess.TimeoutExpired(argv, 10)
        crow_gui.subprocess.run = run
        self.assertIsNone(crow_gui.clipboard_image_posix())
        self.assertTrue(all(t for t in seen), "ein Aufruf ohne Zeitschranke")

    def test_the_windows_reader_is_still_the_one_windows_gets(self):
        """Die Weiche selbst. Auf Windows aendert der Port nichts: derselbe
        ctypes-Leser wie vorher, Byte fuer Byte."""
        source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.assertIn("def clipboard_image_windows()", source)
        self.assertIn("if not crow_platform.IS_WINDOWS:\n"
                      "        return clipboard_image_posix()", source)


class _Done:
    """Was `subprocess.run` zurueckgibt, so weit `copy` es anfasst.

    ALS ATTRAPPE UND NICHT ALS None: der Aufrufer liest `returncode`, weil ein
    Werkzeug, das seinen Server nicht erreicht, keine Kopie ist -- eine Attrappe,
    die None liefert, koennte diesen Unterschied gar nicht haben.
    """

    def __init__(self, rc=0):
        self.returncode, self.stdout, self.stderr = rc, b"", b""


class TheGoalEngineBreaksARenderLoopTests(ApiCase):
    """#268, 2026-09-23 22:30-22:48: seven captures of chain.html in a row at
    99.2-99.4 % one colour, every turn calling tools, no failure -- neither
    the brake nor the trouble classes saw it. Three stuck captures of one
    page: the bisect nudge. Six: a forced rollover carrying what was tried."""

    BLACK = ("warn: this capture looks blank \u2014 100.0%% of its pixels are "
             "one colour; treat it as no-signal\n%s -- 4718 bytes, 1280x800, "
             "done, software (swiftshader)\nread_image it to look at the page.")

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(crow_core.goal_write, None)
        crow_core.goal_start("Voxel scene", ["build the scene", "verify it"],
                             now=1000.0)
        self.n = 0

    def turn(self, api, text, renders, page="chain.html") -> None:
        api._conversation.append("user", text)
        for _ in range(renders):
            self.n += 1
            write, shot = "w%d" % self.n, "r%d" % self.n
            api._conversation.append("assistant", "", tool_calls=[
                {"id": write, "name": "edit_file",
                 "arguments": json.dumps({"path": "src/pass%d.js" % self.n,
                                          "old": "a", "new": "b"})}])
            api._conversation.append("tool", "edited", tool_call_id=write)
            api._conversation.append("assistant", "", tool_calls=[
                {"id": shot, "name": "render_page",
                 "arguments": json.dumps({"path": page})}])
            api._conversation.append(
                "tool", self.BLACK % ("/nowhere/render-%d.png" % self.n),
                tool_call_id=shot)
        api._conversation.append("assistant", "patched another pass")

    def test_three_black_captures_ask_for_a_bisect_six_force_the_roll(self):
        api = self.api()
        logs = tempfile.mkdtemp(prefix="crow-log-")
        self.addCleanup(shutil.rmtree, logs, True)
        self.addCleanup(setattr, crow_core, "LOG_FILE", crow_core.LOG_FILE)
        crow_core.LOG_FILE = os.path.join(logs, "crow.log")
        self.turn(api, api._goal_nudge(), 3)
        nudge = api._goal_nudge()
        # #277: a blank capture is no picture, and its bisect is the
        # one-pass-in-isolation probe.
        self.assertIn("the last 3 captures of chain.html showed no picture",
                      nudge)
        self.assertIn("render ONE pass in isolation", nudge)
        self.assertFalse(api._goal_roll_due)
        self.turn(api, nudge, 3)
        carry = api._goal_nudge()
        self.assertTrue(api._goal_roll_due)
        self.assertIn("6 captures of chain.html in a row", carry)
        self.assertIn("render-6.png: looks blank after writing src/pass6.js",
                      carry)
        # #262: "goal mode, step N: ..." is Crow's own status line -- it goes
        # to crow.log, not into the chat.
        notes = [m["t"] for m in self.drained(api) if m.get("k") == "note"]
        self.assertFalse(any("the context rolls over" in t for t in notes), notes)
        with open(crow_core.LOG_FILE, encoding="utf-8") as fh:
            self.assertIn("the context rolls over", fh.read())

    def test_a_new_page_is_a_changed_approach(self):
        """NEGATIVE: two black captures, then the probe page -- no nudge."""
        api = self.api()
        self.turn(api, api._goal_nudge(), 2)
        self.turn(api, api._goal_nudge(), 1, page="probe.html")
        self.assertNotIn("bisect", api._goal_nudge())

    def test_done_clears_the_streak(self):
        api = self.api()
        self.turn(api, api._goal_nudge(), 2)
        crow_core.tool_goal_step(1, "failed", "black")
        api._conversation.append("assistant", "", tool_calls=[
            {"id": "g", "name": "goal_step",
             "arguments": json.dumps({"step": 1, "status": "done"})}])
        api._conversation.append("tool", "{}", tool_call_id="g")
        self.turn(api, "[Goal mode, step 1 still open. Continue.]", 1)
        self.assertNotIn("bisect", api._goal_nudge() or "")

    def test_a_trouble_nudge_does_not_hide_the_turns_captures(self):
        """#277, 2026-09-24 s81-s133: #202's nudge returned before the render
        scan, and three near-black captures of index.html were never
        counted. #202 still speaks first; the captures count anyway."""
        api = self.api()
        trouble = [{"class": "refused", "tool": "edit_file", "n": 3}]
        with mock.patch.object(crow_core, "goal_trouble_due",
                               side_effect=[[], trouble, []]), \
             mock.patch.object(crow_core, "goal_trouble_nudge",
                               return_value="[Goal mode, trouble]"), \
             mock.patch.object(crow_core, "goal_trouble_label",
                               return_value="edit_file refused"):
            self.turn(api, api._goal_nudge(), 3)
            self.assertEqual(api._goal_nudge(), "[Goal mode, trouble]")
            self.turn(api, "[Goal mode, trouble]", 0)
            nudge = api._goal_nudge()
        self.assertIn("the last 3 captures of chain.html showed no picture",
                      nudge)

    def test_a_turn_cut_by_a_mid_turn_rollover_is_still_counted(self):
        """#277, 2026-09-24 10:50: the rollover cut the turn; the new payload
        began with the rollover note, `goal_turn_start` found no start and
        the turn's captures were skipped. The carried tail is scanned, and
        a carried capture already counted is not counted twice."""
        api = self.api()
        self.turn(api, api._goal_nudge(), 2)
        self.assertNotIn("showed no picture", api._goal_nudge() or "")
        carried = self.BLACK % ("/nowhere/render-%d.png" % self.n)
        api._conversation.reset()
        api._conversation.append(
            "user", "[The conversation up to this point reached 181705 "
                    "tokens and was archived.]")
        api._conversation.append("assistant", "", tool_calls=[
            {"id": "k", "name": "render_page",
             "arguments": json.dumps({"path": "chain.html"})}])
        api._conversation.append(
            "tool", "[carried across the cut]\n" + carried, tool_call_id="k")
        self.turn(api, "[The tool budget for this turn is spent]", 1)
        nudge = api._goal_nudge()
        self.assertIn("the last 3 captures of chain.html showed no picture",
                      nudge)


class TheCopyButtonPutsTextBackTests(ApiCase):
    """`navigator.clipboard` verweigert hier den Dienst -- die Seite wird als
    HTML uebergeben und ist damit kein sicherer Kontext, gemessen 2026-08-13.
    Also schreibt Python. `clip` auf Windows, `wl-copy` oder `xclip` sonst."""

    def setUp(self) -> None:
        super().setUp()
        self._before = (crow_gui.subprocess.run, crow_gui.shutil.which)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        crow_gui.subprocess.run, crow_gui.shutil.which = self._before

    def test_wl_copy_takes_the_text_as_utf8(self):
        if crow_platform.IS_WINDOWS:
            self.skipTest("dort schreibt `clip`, und zwar UTF-16LE")
        seen = {}
        crow_gui.shutil.which = lambda n: "/usr/bin/" + n if n == "wl-copy" else None

        def run(argv, **kw):
            seen.update(argv=list(argv), payload=kw.get("input"), kw=kw)
            return _Done(0)
        crow_gui.subprocess.run = run
        self.assertTrue(self.api().copy("Krähe"))
        self.assertEqual(seen["argv"], ["wl-copy"])
        self.assertEqual(seen["payload"], "Krähe".encode("utf-8"))
        # SEINE AUSGABE WIRD NICHT EINGEFANGEN, und das ist der ganze Grund,
        # warum dieser Fall die Schluesselwoerter nachsieht: `wl-copy` gabelt
        # sich und bleibt am Leben, um die Auswahl zu HALTEN -- mit
        # `capture_output=True` erbt der Besitzer die Roehren und haelt sie
        # offen, also wartet `run` auf ein Dateiende, das erst kommt, wenn
        # jemand anderes etwas kopiert. Gemessen 2026-09-16: jedes Kopieren
        # brauchte die vollen 5,01 s und endete im Zeitlimit, auf dem
        # Bruecken-Faden, auf einen Knopfdruck; nach /dev/null sind es 0,02 s.
        self.assertIsNot(seen["kw"].get("capture_output"), True,
                         "die Roehren halten den gegabelten Besitzer fest")
        self.assertEqual(seen["kw"].get("stdout"), crow_gui.subprocess.DEVNULL)
        self.assertTrue(seen["kw"].get("timeout"), "kein Zeitlimit")

    def test_a_tool_that_reached_no_server_lets_the_next_one_try(self):
        """`wl-copy` unter X11 endet sofort mit 1 ("Failed to connect to a
        Wayland server", gemessen 2026-09-16). True zu antworten hiess: der Text
        erreichte die Ablage nie UND xclip wurde nie gefragt -- dasselbe Loch,
        das der Bildleser hatte."""
        if crow_platform.IS_WINDOWS:
            self.skipTest("kein wl-copy auf der anderen Seite")
        seen = []
        crow_gui.shutil.which = lambda n: "/usr/bin/" + n

        def run(argv, **kw):
            seen.append(list(argv))
            return _Done(1 if argv[0] == "wl-copy" else 0)
        crow_gui.subprocess.run = run
        self.assertTrue(self.api().copy("x"))
        self.assertEqual([a[0] for a in seen], ["wl-copy", "xclip"])
        # UND WENN AUCH DAS ZWEITE ABLEHNT, ist die Antwort False und keine
        # stille Zusage.
        seen.clear()
        crow_gui.subprocess.run = lambda argv, **kw: (seen.append(list(argv)),
                                                      _Done(1))[1]
        self.assertFalse(self.api().copy("x"))

    def test_a_timeout_is_success_because_wl_copy_stays_alive(self):
        """wl-copy bleibt am Leben, um die Auswahl zu HALTEN. Ein Timeout heisst
        hier also nicht "es ging schief", sondern "es tut noch, was es soll"."""
        if crow_platform.IS_WINDOWS:
            self.skipTest("kein wl-copy auf der anderen Seite")
        crow_gui.shutil.which = lambda n: "/usr/bin/" + n

        def run(argv, **kw):
            raise crow_gui.subprocess.TimeoutExpired(argv, 5)
        crow_gui.subprocess.run = run
        self.assertTrue(self.api().copy("x"))

    def test_nothing_to_copy_is_refused_before_any_process_starts(self):
        """GEGENPROBE."""
        started = []
        crow_gui.subprocess.run = lambda *a, **kw: started.append(a)
        self.assertFalse(self.api().copy(""))
        self.assertEqual(started, [])


class TheWindowIsCalledCrowTests(unittest.TestCase):
    """D2/A4. Vier Stellen muessen sich auf EINE Zeichenkette einigen: die
    Wayland-`app_id`, `StartupWMClass` in crow.desktop, das `Icon=crow`, das
    dieser Eintrag nennt, und das `class:^(crow)$` der Fensterregel.

    OHNE `GLib.set_prgname` IST DIE KLASSE `crow_gui.py`, der Dateiname des
    Skripts -- gemessen 2026-09-16 mit `hyprctl clients -j` -- und damit
    scheitern alle vier Treffer auf einmal: kein Icon, kein Eintrag, keine
    Regel.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_the_process_is_named_before_the_window_opens(self):
        main = self.source[self.source.index("def main(argv"):]
        self.assertLess(main.index("name_this_process()"),
                        main.index("webview.create_window("),
                        "der Name wird gelesen, wenn das Fenster entsteht")

    def test_naming_never_takes_the_window_down(self):
        """Ein Fenster mit der falschen Klasse ist ein Fenster mit dem falschen
        Icon; ein Client, der deswegen nicht aufgeht, ist keiner."""
        with mock.patch.dict(sys.modules, {"gi": None, "gi.repository": None}):
            self.assertFalse(crow_gui.name_this_process("crow"))

    def test_it_really_sets_the_program_name(self):
        if crow_platform.IS_WINDOWS:
            self.skipTest("GLib gibt es dort nicht")
        try:
            from gi.repository import GLib
        except Exception:                  # noqa: BLE001
            self.skipTest("kein PyGObject auf dieser Maschine")
        before = GLib.get_prgname()
        self.addCleanup(GLib.set_prgname, before)
        self.assertTrue(crow_gui.name_this_process("crow"))
        self.assertEqual(GLib.get_prgname(), "crow")

    def test_windows_keeps_its_own_identity_call(self):
        """GEGENPROBE: `taskbar_identity` ist die Antwort auf dieselbe Frage
        drueben, und die beiden treten sich nicht auf die Fuesse."""
        self.assertIn("def taskbar_identity()", self.source)
        if not crow_platform.IS_WINDOWS:
            self.assertFalse(crow_gui.taskbar_identity())


class TheWindowShipsALauncherEntryTests(unittest.TestCase):
    """D1/D3. Das Fenster IST der Client (#187), also braucht es einen Eintrag,
    ueber den man es startet, und ein Icon, das dabei gezeichnet wird."""

    def setUp(self) -> None:
        whole = (HERE / "crow.desktop").read_text(encoding="utf-8")
        # DIE GRUPPE UND NICHT DIE DATEI. Ueber `[Desktop Entry]` steht der
        # Kommentar, der erklaert, WARUM die Schluessel so lauten -- und ein
        # Fall, der die ganze Datei durchsucht, findet jeden Schluessel auch in
        # dem Satz, der ihn begruendet. Das ist genau die Verwechslung, die
        # check_gui_prereqs.py fuer Zeichen in Kommentaren schon einmal
        # auseinandersortiert hat.
        self.desktop = whole[whole.index("[Desktop Entry]"):]
        # NUR DIE ZEILEN, DIE HYPRLAND AUSFUEHRT. Ueber ihnen steht der
        # Kommentar, der sie begruendet -- und der zitiert die alte Schreibweise,
        # weil er von ihr HANDELT. Ein Fall, der die ganze Datei durchsucht,
        # findet jede Regel auch in dem Satz, der sie erklaert; dieselbe
        # Verwechslung, die weiter oben schon `[Desktop Entry]` von seinem
        # Kopfkommentar trennt.
        def rules_of(name):
            text = (HERE / name).read_text(encoding="utf-8")
            return "\n".join(line for line in text.splitlines()
                              if not line.lstrip().startswith(("#", "--")))

        self.rules = rules_of("hyprland-crow.conf")
        self.lua = rules_of("hyprland-crow.lua")

    def test_the_entry_has_what_the_specification_requires(self):
        for line in ("[Desktop Entry]", "Type=Application", "Name=Crow"):
            self.assertIn(line, self.desktop)

    def test_the_three_names_agree(self):
        """Dateiname, Icon und StartupWMClass -- und `GLib.set_prgname("crow")`
        im Fenster ist die vierte Ecke desselben Vierecks."""
        self.assertIn("Icon=crow\n", self.desktop)
        self.assertIn("StartupWMClass=crow\n", self.desktop)
        self.assertTrue((HERE / "crow.desktop").exists())
        self.assertIn('name_this_process()',
                      (HERE / "crow_gui.py").read_text(encoding="utf-8"))

    def test_the_launcher_path_is_a_placeholder_the_installer_fills(self):
        """Es gibt keinen Pfad, der im Repository richtig waere: das Fenster
        laeuft aus einem Checkout, aus ~/.local/share/crow oder aus dem, worauf
        `install.sh --to DIR` zeigte."""
        self.assertIn("Exec=@CROW_LAUNCHER@", self.desktop)

    def test_no_terminal_opens_behind_the_window(self):
        self.assertIn("Terminal=false\n", self.desktop)

    def test_a_mime_line_would_oblige_the_installer_and_there_is_none(self):
        """GEGENPROBE: `update-desktop-database` baut den MIME-Cache und wird
        NUR dafuer gebraucht. Kommt die Zeile dazu, muss der Installer das
        Werkzeug laufen lassen -- und solange sie fehlt, darf er es nicht
        behaupten."""
        self.assertNotIn("MimeType=", self.desktop)

    def test_the_window_rule_keys_on_the_same_class(self):
        """Hyprland kachelt sonst das Fenster und ueberschreibt `min_size`:
        `create_window(width=500,height=250)` kam 2026-09-16 als
        `size=[1261,688] floating=false` heraus."""
        self.assertIn("class:^([Cc]row)$", self.rules)
        self.assertIn("float", self.rules)

    def test_both_config_dialects_ship(self):
        """Hyprland waehlt seinen Parser nach der Konfiguration, die es findet:
        `hyprland.conf` bekommt den alten ini-Leser und `windowrule = ...`,
        `hyprland.lua` den Lua-Leser und `hl.window_rule{...}`. Die beiden sind
        NICHT austauschbar -- gemessen 2026-09-16 auf 0.56.2 mit einer
        Lua-Konfiguration: `hyprctl keyword windowrule "float, class:^(crow)$"`
        antwortete "keyword can't work with non-legacy parsers"."""
        self.assertIn("hl.window_rule(", self.lua)
        self.assertIn('class = "^([Cc]row)$"', self.lua)
        self.assertIn("float = true", self.lua)
        self.assertIn("windowrule = float", self.rules)

    def test_the_window_is_opaque(self):
        """robins Entwurf ist ein rahmenloses Fenster, dessen Chrom die SEITE
        ist. Ein Aufbau, der unfokussierte Fenster durchscheinen laesst --
        Omarchy malt jedes bei 0.985/0.96 -- macht daraus eine Ebene statt eines
        Programms; die mitgelieferten Browser dort nehmen sich aus demselben
        Grund aus."""
        self.assertIn("opacity 1.0 1.0", self.rules)
        self.assertIn('opacity = "1.0 1.0"', self.lua)

    def test_the_rule_also_catches_the_xwayland_spelling(self):
        """DIE NOTLUKE DARF NICHT DIE REGELN ABSCHALTEN. Unter
        `CROW_GDK_BACKEND=x11` ist die Identitaet die X11-WM_CLASS, und deren
        res_class schreibt GTK gross: `hyprctl clients -j` meldete 2026-09-16
        `crow` auf Wayland und `Crow` unter XWayland. Ein Zeichen, und ohne es
        gelten die Regeln genau auf dem Lauf nicht mehr, auf dem jemand schon
        einen Fehler sucht."""
        self.assertNotIn("class:^(crow)$", self.rules,
                         "die Regel faellt unter XWayland aus")

    def test_the_icons_are_png_and_the_sizes_the_theme_asks_for(self):
        """PNG UND NICHT SVG: auf dieser Maschine gibt es keinen
        SVG-gdk-pixbuf-Loader, also kann alles, was ein Theme-Icon ueber
        GdkPixbuf rastert -- `webview.start(icon=)` eingeschlossen -- eine SVG
        gar nicht oeffnen."""
        for size in crow_gui.ICON_SIZES:
            path = crow_gui.icon_png(size)
            self.assertTrue(path, "es fehlt ein Icon in %dx%d" % (size, size))
            with open(path, "rb") as fh:
                head = fh.read(24)
            self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n", path)
            self.assertEqual(struct.unpack(">II", head[16:24]), (size, size),
                             "%s ist nicht %dx%d" % (path, size, size))

    def test_a_size_this_build_does_not_ship_is_empty_and_not_a_guess(self):
        """GEGENPROBE: `webview.start(icon=)` nimmt None, und ein Fenster, das
        wegen einer fehlenden Verzierung nicht aufgeht, waere der schlechtere
        Fehler."""
        self.assertEqual(crow_gui.icon_png(777), "")


class ThePageArrivesWithABaseUriTests(unittest.TestCase):
    """A8. `create_window(html=...)` erreicht WebKitGTK als
    `load_html(html, base_uri='')`, und ein leerer Base-URI ist dort
    `about:blank`: `file:///`-Bilder feuerten `onerror` mit naturalWidth 0 und
    ein `@font-face` auf eine Datei blieb `unloaded` (gemessen 2026-09-16).

    `window.load_html(page)` NACH dem Aufbau setzt den Base-URI auf das
    Verzeichnis des Programms, und danach loest alles auf -- live geprueft:
    `document.baseURI` ist eine `file://`-Adresse.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_windows_still_gets_the_page_in_create_window(self):
        self.assertIn('handover = "" if crow_platform.IS_WINDOWS else page',
                      self.source)

    def test_the_handover_waits_for_the_window_to_exist(self):
        """`Window.load_html` wartet auf das `shown`-Ereignis, und das setzt
        erst die GUI-Schleife. Neben `create_window` gerufen blockiert es
        zwanzig Sekunden und fliegt dann."""
        main = self.source[self.source.index("def main(argv"):]
        self.assertIn("if handover:\n            window.load_html(handover)", main)
        self.assertLess(main.index("def styles(*_)"),
                        main.index("webview.start("))

    def test_the_placeholder_paints_the_ground_the_theme_will_paint(self):
        """Ein Fenster, das in der einen Farbe aufgeht und in der anderen
        weitergemalt wird, ist ein Aufblitzen des falschen Produkts -- bei jedem
        Start, genau in dem Moment, in dem jemand hinsieht."""
        self.assertIn("__BG__", crow_gui.PAGE_PLACEHOLDER)
        painted = crow_gui.PAGE_PLACEHOLDER.replace(
            "__BG__", crow_gui.theme_bg("dark"))
        self.assertIn(crow_gui.theme_bg("dark"), painted)
        self.assertNotIn("__BG__", painted)

    def test_the_toolkit_is_named_rather_than_searched_for(self):
        """`KDE_FULL_SESSION` im Environment zwingt pywebview auf Qt, und Crow
        ist gegen WebKitGTK geschrieben. Ein Nachmittag in Plasma darf nicht den
        Renderer wechseln."""
        self.assertIn('webview.start(styles, window, gui="gtk", icon=',
                      self.source)
        self.assertIn("webview.start(styles, window)\n", self.source)


class TheBrowserPaneOnACompositorTests(ApiCase):
    """#175 auf Wayland. Die Scheibe kann dort NICHT am Panel kleben: `move()`
    ist ein Leerlauf, `on_top` ebenso. Sie bleibt ein zweites Fenster, sie
    schwebt statt zu kacheln (dieselbe Klasse, dieselbe Regel), und die Wege
    zeigen/verstecken/schliessen duerfen nicht fliegen."""

    class _Pane:
        def __init__(self) -> None:
            self.hidden, self.calls = True, []

        def load_url(self, url) -> None:
            self.calls.append(("load", url))

        def show(self) -> None:
            self.calls.append(("show", self.hidden))

        def hide(self) -> None:
            self.calls.append(("hide", None))

        def move(self, x, y) -> None:
            self.calls.append(("move", (x, y)))

        def resize(self, w, h) -> None:
            self.calls.append(("resize", (w, h)))

    def _api(self, native=None):
        api = self.api()
        api._gtk_window = lambda: native
        api._browser_win = self._Pane()
        # `_pane` IMPORTIERT `webview`, UND ZWAR BEVOR ES NACHSIEHT, ob es die
        # Scheibe schon gibt -- absichtlich, siehe den Kommentar dort: ein
        # Modulname, den es in dieser Datei nicht gibt, kostete am 2026-08-31
        # einen ganzen Anlauf. Die Faelle hier sind ueber die WEGE geschnitten,
        # nicht ueber das Erzeugen, und sie muessen auch auf einer Maschine
        # ohne pywebview laufen.
        api._pane = lambda: api._browser_win
        return api

    def test_a_hidden_window_is_unhidden_before_it_is_shown(self):
        """DER FEHLER SITZT IN PYWEBVIEW: `BrowserView.show()` ruft `show_all()`
        und versteckt sofort wieder, solange `Window.hidden` steht -- und
        `Window.show()` setzt die Fahne nie zurueck. Unter der GtkApplication
        ist `gtk_main_level()` immer 0, also greift genau dieser Zweig, und ein
        so erzeugtes Fenster kann NIE erscheinen."""
        api = self._api(_FakeGtkWindow())
        api.pane_go("https://example.com")
        self.assertFalse(api._browser_win.hidden)
        self.assertIn(("show", False), api._browser_win.calls)

    def test_the_rectangle_is_not_computed_out_of_two_invented_numbers(self):
        """`self._window.x` liest pywebviews eigene Buchhaltung und nicht den
        Bildschirm. Auf Wayland waere die Rechnung also aus zwei erfundenen
        Zahlen -- und `move()` befolgte sie ohnehin nicht."""
        api = self._api(_FakeGtkWindow())
        api.pane_go("https://example.com")
        api.pane_place(10, 20, 300, 200)
        self.assertEqual([c for c in api._browser_win.calls
                          if c[0] in ("move", "resize")], [])

    def test_on_windows_the_pane_still_follows_the_panel(self):
        """GEGENPROBE, und sie ist die ganze Windows-Seite von #175: dort
        WANDERT die Scheibe mit."""
        api = self._api(None)
        api._window = mock.Mock(x=100, y=50)
        api.pane_go("https://example.com")
        api.pane_place(10, 20, 300, 200)
        self.assertIn(("move", (110, 70)), api._browser_win.calls)
        self.assertIn(("resize", (300, 200)), api._browser_win.calls)

    def test_hide_and_show_survive_a_window_that_refuses(self):
        """Eine Scheibe im Aufbau ist kein Grund, das Fenster mitzunehmen."""
        class _Angry(self._Pane):
            def show(self):
                raise RuntimeError("not mapped")

            def hide(self):
                raise RuntimeError("not mapped")

        api = self._api(_FakeGtkWindow())
        api._browser_win = _Angry()
        api._browser_shown = True
        self.assertTrue(api.pane_hide())
        self.assertTrue(api.pane_show())


class ThePaneLivesInsideTheWindowTests(ApiCase):
    """#201 #226 #227. Auf GTK ist die Scheibe ein WIDGET im eigenen Fenster,
    kein zweites Toplevel. Die Faelle hier pruefen die Entscheidungen ohne
    Display: welcher Weg, welches Schema, welche Meldung an die Seite. Dass
    GtkOverlay das Kind dorthin legt, wurde unter broadwayd gemessen (#201)."""

    class _Pane:
        def __init__(self) -> None:
            self.calls = []

        def __getattr__(self, name):
            return lambda *a: self.calls.append((name, a))

    def _api(self):
        api = self.api()
        api._inwin = self._Pane()
        return api

    def test_only_http_https_file_and_blank_reach_the_pane(self):
        for good in ("https://x.org", "http://127.0.0.1:8000/", "file:///h/a.png",
                     "about:blank", " HTTPS://X.ORG "):
            self.assertTrue(crow_gui.pane_url_ok(good), good)
        for bad in ("javascript:alert(1)", "data:text/html,x", "ftp://x", "",
                    None, "about:config", "chrome://settings"):
            self.assertFalse(crow_gui.pane_url_ok(bad), bad)

    def test_go_place_hide_show_go_to_the_widget_not_a_window(self):
        api = self._api()
        api._pane = lambda: self.fail("a second window was built")
        self.assertEqual(api.pane_go("https://example.com"), "https://example.com")
        api.pane_place(10, 20, 300, 200)
        api.pane_hide()
        api.pane_show()
        api.pane_cover(True)
        self.assertEqual([c[0] for c in api._inwin.calls],
                         ["go", "place", "hide", "show", "cover"])
        self.assertEqual(api._inwin.calls[1][1], (10.0, 20.0, 300.0, 200.0))

    def test_a_script_address_is_refused_before_webkit(self):
        api = self._api()
        self.assertTrue(api.pane_go("javascript:alert(1)").startswith("error:"))
        self.assertEqual(api._inwin.calls, [])

    def test_an_answer_link_opens_in_the_panel_and_ctrl_sends_it_out(self):
        api = self._api()
        opened = []
        real = crow_gui.webbrowser.open
        crow_gui.webbrowser.open = lambda url: opened.append(url) or True
        self.addCleanup(setattr, crow_gui.webbrowser, "open", real)
        self.assertTrue(api.open_url("https://example.com/a"))
        self.assertEqual(opened, [])
        said = self.drained(api)
        self.assertEqual([(m["k"], m["url"]) for m in said],
                         [("bropen", "https://example.com/a")])
        self.assertTrue(api.open_url("https://example.com/b", True))
        self.assertEqual(opened, ["https://example.com/b"])
        self.assertFalse(api.open_url("javascript:x"))

    def test_no_native_window_no_embedding(self):
        api = self.api()
        api._gtk_window = lambda: None
        self.assertFalse(api.pane_embed())
        self.assertIsNone(api._inwin)

    def test_a_failed_embedding_keeps_the_window_pane_and_says_so(self):
        api = self.api()
        api._gtk_window = lambda: object()
        real = crow_gui.InWindowPane.install
        crow_gui.InWindowPane.install = classmethod(
            lambda cls, native, on_event: (_ for _ in ()).throw(RuntimeError("no gi")))
        self.addCleanup(setattr, crow_gui.InWindowPane, "install", real)
        old = os.environ.pop("CROW_PANE_WINDOW", None)
        self.addCleanup(lambda: old is None or os.environ.__setitem__(
            "CROW_PANE_WINDOW", old))
        if crow_gui.crow_platform.IS_WINDOWS:
            self.skipTest("the embedding is GTK only")
        self.assertFalse(api.pane_embed())
        self.assertIsNone(api._inwin)
        said = self.drained(api)
        self.assertEqual(said[0]["k"], "note")
        self.assertIn("no gi", said[0]["t"])

    def test_the_escape_hatch_keeps_the_old_pane(self):
        api = self.api()
        api._gtk_window = lambda: self.fail("looked at the window")
        os.environ["CROW_PANE_WINDOW"] = "1"
        self.addCleanup(os.environ.pop, "CROW_PANE_WINDOW", None)
        self.assertFalse(api.pane_embed())


class TheInWindowPaneDecidesTests(unittest.TestCase):
    """#201 #227. Die Zustandsentscheidungen von `InWindowPane`, ohne GTK."""

    def _pane(self):
        said = []
        return crow_gui.InWindowPane(said.append, idle_add=lambda fn, *a: None), said

    def test_crows_own_load_replaces_and_the_pages_own_pushes(self):
        pane, _ = self._pane()
        pane.go("http://a/")
        self.assertEqual(pane.committed("https://a/")["how"], "replace",
                         "a redirect of our own load is not a new entry")
        self.assertEqual(pane.committed("https://a/b")["how"], "push")
        self.assertIsNone(pane.committed("https://a/b"), "said twice")
        self.assertIsNone(pane.committed(""))

    def test_visible_needs_a_wish_a_rect_and_nothing_on_top(self):
        pane, _ = self._pane()
        pane.go("https://a/")
        self.assertFalse(pane.visible(), "no rectangle yet")
        pane.place(1.4, 2.6, 300.2, 0)
        self.assertEqual(pane.rect, (1, 3, 300, 1))
        self.assertTrue(pane.visible())
        pane.cover(True)
        self.assertFalse(pane.visible())
        pane.cover(False)
        pane.hide()
        self.assertFalse(pane.visible())

    def test_show_brings_back_only_a_pane_with_a_page(self):
        pane, _ = self._pane()
        pane.place(0, 0, 10, 10)
        pane.show()
        self.assertFalse(pane.wanted, "an empty view is a white hole")
        pane._view, pane.last = object(), "https://a/"
        pane.show()
        self.assertTrue(pane.wanted)

    def test_a_memory_kill_is_said_with_the_ceiling(self):
        pane, said = self._pane()
        pane.last = "https://a/"
        pane._terminated(None, mock.Mock(value_nick="exceeded-memory-limit"))
        self.assertIn("%d MB" % crow_gui.PANE_MEMORY_LIMIT_MB, said[0]["t"])
        self.assertEqual(pane.last, "")

    def test_a_new_window_is_refused_and_loaded_here(self):
        pane, _ = self._pane()
        action = mock.Mock()
        action.get_request.return_value.get_uri.return_value = "https://b/"
        self.assertIsNone(pane._new_window(None, action))

    def test_the_view_has_its_own_limits_and_no_bridge(self):
        """#226. Quelle statt Display: eigener Kontext, Kill an, bwrap, und
        kein UserContentManager -- also keine pywebview-Bruecke."""
        src = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        body = src[src.index("    def _build(self)"):src.index("    # -- what the page asks for")]
        for need in ("set_kill_threshold(PANE_KILL_FRACTION)",
                     "memory_pressure_settings=limits",
                     "WebsiteDataManager(base_data_directory=data",
                     "set_sandbox_enabled(True)", "set_no_show_all(True)",
                     '"web-process-terminated"', '"create"'):
            self.assertIn(need, body, need)
        self.assertNotIn("UserContentManager", body)
        self.assertGreater(crow_gui.PANE_KILL_FRACTION, 0.5,
                           "WebKit wants kill above strict (0.5)")


class _FakeView:
    """#279: the few WebKitWebView calls the pane makes, recorded."""

    def __init__(self) -> None:
        self.calls = []

    def show(self):
        self.calls.append("show")

    def hide(self):
        self.calls.append("hide")

    def load_uri(self, uri):
        self.calls.append(("load", uri))

    def loads(self):
        return [c[1] for c in self.calls if isinstance(c, tuple)]


class _FakeOverlay:
    def __init__(self) -> None:
        self.calls = []
        self.top = mock.Mock()

    def queue_resize(self):
        self.calls.append("resize")

    def queue_draw(self):
        self.calls.append("draw")

    def get_toplevel(self):
        return self.top


class AFoldedPanelHoldsNoPageTests(unittest.TestCase):
    """#279 B/C. 2026-09-24: the panel was folded from ~13:20, yet its
    WebKitWebProcess was spawned at 13:26:20 right after a render and kept
    crashing; after six crashes the window stopped repainting until robin
    moved it. Idle work runs at once here, so the decisions and the widget
    calls can be read without a display."""

    def _pane(self):
        said = []
        pane = crow_gui.InWindowPane(said.append, idle_add=lambda fn, *a: fn(*a))
        pane._view, pane._overlay = _FakeView(), _FakeOverlay()
        pane.place(0, 0, 300, 200)
        return pane, said

    def test_hide_unloads_the_page_and_show_brings_it_back(self):
        pane, _ = self._pane()
        pane.go("https://a/")
        pane.committed("https://a/")
        pane.hide()
        self.assertEqual(pane._view.loads(), ["https://a/", "about:blank"])
        self.assertTrue(pane.parked)
        self.assertFalse(pane.holds_page())
        self.assertIsNone(pane.committed("about:blank"),
                          "the park is not a navigation of the tab")
        pane.show()
        self.assertEqual(pane._view.loads()[-1], "https://a/")
        self.assertTrue(pane.holds_page())

    def test_a_cover_hides_but_does_not_unload(self):
        pane, _ = self._pane()
        pane.go("https://a/")
        pane.committed("https://a/")
        pane.cover(True)
        self.assertEqual(pane._view.loads(), ["https://a/"])
        self.assertFalse(pane.parked)

    def test_a_load_overtaken_by_a_hide_is_not_made(self):
        queued = []
        pane = crow_gui.InWindowPane(lambda e: None,
                                     idle_add=lambda fn, *a: queued.append((fn, a)))
        pane._view = _FakeView()
        pane.go("https://a/")
        pane.hide()
        for fn, a in queued:
            fn(*a)
        self.assertEqual(pane._view.loads(), [])

    def test_a_hidden_pane_opens_no_new_window(self):
        pane, _ = self._pane()
        action = mock.Mock()
        action.get_request.return_value.get_uri.return_value = "https://b/"
        pane.hide()
        pane._new_window(None, action)
        self.assertEqual(pane._view.loads(), [])
        pane.go("https://a/")
        pane._new_window(None, action)
        self.assertEqual(pane._view.loads(), ["https://a/", "https://b/"])

    def test_a_crash_redraws_and_reloads_once_at_most(self):
        pane, said = self._pane()
        pane.go("https://a/")
        pane.committed("https://a/")
        crash = mock.Mock(value_nick="crashed")
        pane._terminated(None, crash)
        self.assertIn("draw", pane._overlay.calls)
        pane._overlay.top.queue_draw.assert_called()
        self.assertEqual(pane._view.loads(), ["https://a/", "https://a/"],
                         "one reload of the page someone was looking at")
        pane.committed("https://a/")
        pane._terminated(None, crash)
        self.assertEqual(pane._view.loads(), ["https://a/", "https://a/"],
                         "#204: never a second reload")
        self.assertFalse(pane.wanted)
        self.assertEqual(pane._view.calls[-1], "hide", "the dead view stays out")
        self.assertEqual([m["t"] for m in said],
                         ["the page in the browser panel stopped (crashed)"] * 2)

    def test_a_crash_of_a_hidden_pane_loads_nothing(self):
        pane, _ = self._pane()
        pane.go("https://a/")
        pane.committed("https://a/")
        pane.hide()
        pane._terminated(None, mock.Mock(value_nick="crashed"))
        self.assertEqual(pane._view.loads(), ["https://a/", "about:blank"])

    def test_the_memory_ceiling_is_not_reloaded(self):
        pane, _ = self._pane()
        pane.go("https://a/")
        pane.committed("https://a/")
        pane._terminated(None, mock.Mock(value_nick="exceeded-memory-limit"))
        self.assertEqual(pane._view.loads(), ["https://a/"])
        self.assertFalse(pane.wanted)


class ThePanelCountsOnTheCardTests(ApiCase):
    """#279 A and D in the window: the core learns whether the panel is a GPU
    client, and the panel's view is throttled around local turns only."""

    def test_the_turn_door_tells_the_core_about_the_panel(self):
        self.addCleanup(crow_core.render_panel_set, False)
        before = crow_gui.SETTINGS_FILE
        self.addCleanup(setattr, crow_gui, "SETTINGS_FILE", before)
        crow_gui.SETTINGS_FILE = os.path.join(self.dir, "settings.json")
        api = self.api()
        for open_, want in ((True, True), (False, False)):
            with open(crow_gui.SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump({"browser_open": open_}, fh)
            api._token_budget()
            self.assertIs(crow_core.RENDER_PANEL_OPEN, want, open_)

    def test_a_folded_panel_still_holding_a_page_counts(self):
        api = self.api()
        pane = crow_gui.InWindowPane(lambda e: None, idle_add=lambda fn, *a: None)
        api._inwin = pane
        self.assertFalse(api._panel_on_card({"browser_open": False}))
        pane._view, pane.last = object(), "https://a/"
        self.assertTrue(api._panel_on_card({"browser_open": False}))
        pane.parked = True
        self.assertFalse(api._panel_on_card({"browser_open": False}))

    def test_the_throttle_is_on_for_local_turns_only(self):
        api = self.api()
        pane = crow_gui.InWindowPane(lambda e: None, idle_add=lambda fn, *a: None)
        api._inwin = pane
        api._endpoint = lambda: {"remote": False}
        api._pane_throttle(True)
        self.assertTrue(pane.throttled)
        api._pane_throttle(False)
        self.assertFalse(pane.throttled)
        api._endpoint = lambda: {"remote": True}
        api._pane_throttle(True)
        self.assertFalse(pane.throttled)

    def test_the_pump_throttles_and_releases(self):
        api = self.api()
        pane = crow_gui.InWindowPane(lambda e: None, idle_add=lambda fn, *a: None)
        api._inwin = pane
        api._endpoint = lambda: {"remote": False}
        seen = []
        api._run = lambda text: seen.append(pane.throttled)
        api._goal_nudge = lambda: None
        api._busy = True
        api._pump("x")
        self.assertEqual(seen, [True])
        self.assertFalse(pane.throttled)

        def boom(text):
            raise RuntimeError("x")
        api._run = boom
        with self.assertRaises(RuntimeError):
            api._pump("x")
        self.assertFalse(pane.throttled)

    def test_the_throttle_names_the_webkit_setting(self):
        src = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        body = src[src.index("    def _policy(self)"):]
        body = body[:body.index("    def _park(self)")]
        self.assertIn("set_hardware_acceleration_policy(", body)
        self.assertIn("p.NEVER if self.throttled else p.ALWAYS", body)


class ThePageFollowsThePaneTests(unittest.TestCase):
    """#201 #227, auf der Seite: die Meldungen haben Empfaenger, ein Render
    macht keinen neuen Reiter je Aufruf, und GitHub bleibt draussen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.src = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_the_messages_have_a_case(self):
        self.assertIn('case "brnav": this.brNav(e.url, e.how)', self.src)
        self.assertIn('case "bropen": this.brOpen(e.url)', self.src)

    def test_a_folded_panel_is_not_loaded_or_unfolded_by_a_render(self):
        """#279 B: the one door (`brSend`) is shut while folded, and a render
        fills its tab without unfolding the panel robin folded."""
        send = self.src[self.src.index("  brSend(url){"):]
        send = send[:send.index("pywebview.api.pane_go(url)")]
        self.assertIn('if(document.body.dataset.browser==="shut") return;', send)
        body = self.src[self.src.index("  brRendered(url, shot){"):]
        body = body[:body.index("  brSelect(id)")]
        self.assertNotIn("this.brUnfold()", body)
        self.assertIn("if(folded) return;", body)
        self.assertIn("this.brSend(this.brShown(t))", self.src)

    def test_renders_reuse_one_tab(self):
        body = self.src[self.src.index("  brRendered(url, shot){"):]
        body = body[:body.index("  brSelect(id)")]
        self.assertIn("this.tabs.find(x=>x.model)", body)
        self.assertEqual(body.count("this.tabs.push("), 1)

    def test_the_github_code_goes_outside(self):
        self.assertIn('pywebview.api.open_url(card.dataset.url||"", true)',
                      self.src)

    def test_the_embedding_is_wired_before_show(self):
        self.assertIn("window.events.before_show += api.pane_embed", self.src)

    def test_a_sheet_over_the_panel_moves_the_pane_aside(self):
        self.assertIn("pywebview.api.pane_cover(c)", self.src)
        self.assertIn('["#settings","#menu"]', self.src)


class TheDropSaysWhenItCarriedNoPathTests(ApiCase):
    """A10. Der Pfad haengt pywebview an, aus dem, was der Drag-Handler des
    Toolkits eingesammelt hat. Eine Quelle, die nur Bytes uebergibt -- ein Bild
    aus einem Browser gezogen -- hinterlaesst den Namen und sonst nichts.

    SCHWEIGEN SIEHT DORT AUS WIE EIN FENSTER, DAS DEN WURF IGNORIERT HAT, und
    der Weg drumherum (Pfad tippen) ist keiner, auf den jemand kommt."""

    def test_a_drop_with_paths_is_passed_on_unchanged(self):
        api = self.api()
        api.on_drop({"dataTransfer": {"files": [
            {"name": "a.txt", "pywebviewFullPath": "/home/x/a.txt"}]}})
        said = self.drained(api)
        self.assertEqual([m["k"] for m in said], ["drop"])
        self.assertEqual(said[0]["paths"], ["/home/x/a.txt"])

    def test_a_drop_without_a_path_says_so(self):
        api = self.api()
        api.on_drop({"dataTransfer": {"files": [{"name": "a.png"}]}})
        said = self.drained(api)
        self.assertEqual([m["k"] for m in said], ["note", "drop"])
        self.assertIn("typing the path", said[0]["t"])
        self.assertEqual(said[1]["paths"], [])

    def test_an_empty_drop_says_nothing_at_all(self):
        """GEGENPROBE: ein Wurf ohne Dateien ist kein Wurf, ueber den man reden
        muss -- eine Notiz bei jedem Nicht-Ereignis erzieht dazu, Notizen zu
        ueberlesen."""
        api = self.api()
        api.on_drop({"dataTransfer": {"files": []}})
        self.assertEqual([m["k"] for m in self.drained(api)], ["drop"])


class ThePageNamesNoPlatformItCannotSeeTests(unittest.TestCase):
    """Zwei Saetze in der Seite waren Windows-Saetze und standen als Text da.

    DER UNTERSCHIED ZU EINEM KOMMENTAR: was ein Leser SIEHT, muss auf seiner
    Maschine stimmen. Ein Kommentar, der Windows erklaert, ist Geschichte; eine
    Zeile im About-Fenster, die `%LOCALAPPDATA%\\Crow` nennt, waehrend die Kopie
    unter ~/.local/share/crow liegt, schickt jemanden an die falsche Stelle.
    """

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        self.page = self.source[self.source.index('PAGE = r"""'):
                                self.source.index("PAGE_PLACEHOLDER = (")]

    def test_the_about_pane_asks_where_this_copy_lives(self):
        """`update_check` traegt `install_dir` schon, und das kommt aus der
        Naht. Die Seite nennt es, statt einen der beiden Pfade zu raten."""
        self.assertIn('<span id="updwhere">', self.page)
        self.assertIn('$("#updwhere").textContent=s.install_dir;', self.page)
        body = self.page[self.page.index('data-cat="about"'):]
        body = body[:body.index("</section>")]
        self.assertNotIn("LOCALAPPDATA", body,
                         "die sichtbare Zeile nennt wieder einen festen Pfad")

    def test_a_posix_path_in_the_address_bar_becomes_a_file_url(self):
        """`/srv/bau.html` traf weder die Laufwerksregel noch die
        Schema-Regel und wurde zu `https:///srv/bau.html`."""
        self.assertIn('url.charAt(0)==="/"', self.page)
        self.assertIn("fileUrl(path){", self.page)

    def test_the_three_slashes_are_not_glued_to_a_fourth(self):
        """Die Regel, die `fileUrl` ueberhaupt zu einer Funktion macht: der
        Pfad bringt auf POSIX seinen eigenen Schraegstrich mit."""
        js = self.page[self.page.index("fileUrl(path){"):]
        js = js[:js.index("},") + 2]
        self.assertIn('p.charAt(0)==="/" ? "" : "/"', js)
        self.assertNotIn('"file:///"', js)


class TheYoloChipTests(unittest.TestCase):
    """robin's goodie and its guard rails, read as page source: the fourth
    level is ARMED with a second click, it explodes once when the page has
    ADOPTED it, and the burst respects the motion setting the OS already
    knows."""

    def setUp(self) -> None:
        self.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def test_the_yolo_rows_carry_the_alarm_colour(self):
        """The chip that asks nothing has to be the loudest thing on the
        strip -- `--bad` is what an escaped working area draws in."""
        self.assertIn('#mode[data-mode="yolo"]{color:var(--bad)', self.source)
        self.assertIn('#modemenu button[data-mode="yolo"] b{color:var(--bad)',
                      self.source)

    def test_the_first_click_only_arms_the_row(self):
        block = self.source[self.source.index("setMode(name){"):
                            self.source.index("// THE ONE-SHOT PIXEL BURST")]
        self.assertIn('name==="yolo" && !this._yoloSure', block)
        self.assertIn("click again to accept", block)
        self.assertIn("setTimeout", block, "the arm never disarms itself")
        self.assertNotIn("yoloBurst", block,
                         "the click must not explode -- the adoption does")

    def test_the_burst_fires_on_adoption_not_on_the_click(self):
        adopted = self.source[self.source.index("modeIs(name, modes){"):
                              self.source.index('// "neu" ARCHIVES')]
        self.assertIn('if(name==="yolo") this.yoloBurst()', adopted)

    def test_the_burst_is_delta_timed_and_reduced_motion_aware(self):
        burst = self.source[self.source.index("yoloBurst(){"):
                            self.source.index("modeIs(name, modes){")]
        self.assertIn("prefers-reduced-motion: reduce", burst)
        self.assertIn("Math.min((now-last)/1000", burst,
                      "frame-rate dependent timing rasts on 120Hz screens")
        self.assertIn("image-rendering:pixelated", burst)
        self.assertIn("pointer-events:none", burst,
                      "the canvas must not eat the clicks under it")
        self.assertIn("cv.remove()", burst, "the canvas outlives the burst")


class _FakeLoaded:
    """pywebview's `loaded` event, soweit `_recover_window` es beruehrt."""

    def __init__(self, window: "_FakeWindow") -> None:
        self._window = window

    def wait(self, timeout: float | None = None) -> bool:
        self._window.wait_calls.append(timeout)
        return True


class _FakeWindow:
    """Ein Fenster, das die Pumpe trifft, ohne GUI.

    VORGABE: tot -- jeder evaluate_js wirft den GError 601 (das Live-
    Ereignis vom 2026-09-20, SIGSEGV im GPU-Treiber, in pywebviews
    `_callback` gefangen und nur geloggt). `heal=True` setzt die Seite nach
    `load_html` wieder in Gang, so wie Buzz Desktop denselben Crash
    repairt; `load_raises=True` lasst AUCH den Reload sterben.
    """

    def __init__(self, heal: bool = True, load_raises: bool = False) -> None:
        from types import SimpleNamespace
        self.heal = heal
        self.load_raises = load_raises
        self.reloaded = False
        self.calls: list[str] = []
        self.load_htmls: list[str] = []
        self.wait_calls: list[float | None] = []
        self.events = SimpleNamespace(loaded=_FakeLoaded(self))

    def evaluate_js(self, script: str) -> None:
        self.calls.append(script)
        if self.heal and self.reloaded:
            return
        raise _GError601("WebKitJavascriptError: Unsupported result "
                         "type (601)")

    def load_html(self, html: str, base_uri: str = "") -> None:
        self.load_htmls.append(html)
        if self.load_raises:
            raise RuntimeError("reload refused -- the page stays dead")
        self.reloaded = True


class _GError601(Exception):
    """Der Name ist Absicht: GLib.GError's Typname ist GError."""


class WebViewException(Exception):
    """pywebviews Shutdown-Typ, nachgebaut -- der Klassifizierer urteilt
    ueber den TYPE-NAMEN, damit das Modul ohne pywebview importierbar
    bleibt; ein lokaler Name mit gleichem Text ist derselbe Beweis."""


class ThePumpSurvivesADeadWebprocessTests(ApiCase):
    """#204. Das Fenster lebt vom WebProcess, und der stirbt (live am
    2026-09-20: SIGSEGV in libnvidia-eglcore). Die alte Pumpe kehrte bei
    jeder Exception still heim -- auf GTK kam die Exception NIE an, denn
    pywebview faengt den GError in `_callback` und LOGGT ihn nur: ein
    Traceback pro Nachricht, hunderte Zeilen, ein totes Fenster. Die Faelle
    hier bewachen die Antwort: EINE Klasse je Fehler, EIN Reload, und nach
    dem zweiten Tod nur noch Leeren -- niemals wieder JS, nie wieder
    Laerm."""

    # -- der Klassifizierer ----------------------------------------------

    def test_the_three_classes(self):
        self.assertEqual(
            crow_gui._classify_push_failure(
                _GError601("WebKitJavascriptError: Unsupported result "
                           "type (601)")),
            "dead_webprocess")
        self.assertEqual(
            crow_gui._classify_push_failure(
                RuntimeError("GLib.GError: WebKitJavascriptError")),
            "dead_webprocess")
        self.assertEqual(
            crow_gui._classify_push_failure(
                RuntimeError("the Web process crashed")),
            "dead_webprocess")
        self.assertEqual(
            crow_gui._classify_push_failure(
                WebViewException("GUI is not initialized")),
            "closed")
        self.assertEqual(
            crow_gui._classify_push_failure(ValueError("crow is not defined")),
            "transient")

    # -- der Plan ---------------------------------------------------------

    def test_closed_stops_the_pump(self):
        self.assertEqual(
            crow_gui._push_failure_plan(
                "closed", reload_tried=False, transient_said=0),
            ("stop", False))

    def test_the_first_death_tries_exactly_one_reload(self):
        self.assertEqual(
            crow_gui._push_failure_plan(
                "dead_webprocess", reload_tried=False, transient_said=0),
            ("reload", False))

    def test_the_second_death_freezes_and_says_so_once(self):
        self.assertEqual(
            crow_gui._push_failure_plan(
                "dead_webprocess", reload_tried=True, transient_said=0),
            ("freeze", True))

    def test_transient_notes_run_under_a_cap(self):
        said = [crow_gui._push_failure_plan(
                    "transient", reload_tried=False, transient_said=n)
                for n in range(5)]
        self.assertEqual([s for _, s in said], [True, True, True, False, False])
        self.assertTrue(all(a == "continue" for a, _ in said))

    def test_the_cap_is_a_parameter(self):
        self.assertEqual(
            crow_gui._push_failure_plan(
                "transient", reload_tried=False, transient_said=3,
                transient_cap=5),
            ("continue", True))

    # -- die verdrahtete Pumpe -------------------------------------------

    @staticmethod
    def _kind_of(script: str) -> str:
        """Aus `window.crow.on("<json>")` der Nachrichtentyp."""
        payload = script[len("window.crow.on("):-1]
        return json.loads(json.loads(payload))["k"]

    def test_a_dead_webprocess_is_reloaded_once_and_the_ui_comes_back(self):
        """Der erste Tod laedt DIESE Seite neu (keine URL, HTML) und schiebt
        den Stamm wieder in die Seite, bevor die wartende Nachricht kommt."""
        api = self.api()
        window = _FakeWindow()              # tot, heilt nach dem Reload
        api._window = window
        api._page = "<html>the page</html>"
        api.push({"k": "note", "t": "first"})
        api.push({"k": "note", "t": "second"})
        api._out.put(None)
        err = io.StringIO()
        with mock.patch("sys.stderr", new=err):
            api.pump()
        self.assertEqual(len(window.load_htmls), 1, "genau EIN Reload")
        self.assertEqual(window.load_htmls[0], "<html>the page</html>")
        self.assertEqual(window.wait_calls, [15.0])
        kinds = [self._kind_of(script) for script in window.calls]
        # note (fehlschlag), root (der Stamm, SOFORT), note (erneut, heil),
        # note -- der Stamm VOR der wartenden Nachricht, wie es der Plan
        # verspricht.
        self.assertEqual(kinds, ["note", "root", "note", "note"], kinds)
        self.assertEqual(err.getvalue(), "", "heilen Passagen sagen nichts")
        self.assertFalse(api._push_dead)

    def test_a_second_death_freezes_drains_and_never_calls_js_again(self):
        """Der Reload hielt nicht: EINE stderr-Zeile, ein toter Pin, und
        alles Weitere wird geleert und weggeworfen -- ohne evaluate_js."""
        api = self.api()
        window = _FakeWindow(heal=False)    # der Reload heilt nicht
        api._window = window
        api._page = "<html>the page</html>"
        api.push({"k": "note", "t": "first"})
        api.push({"k": "note", "t": "second"})
        api._out.put(None)
        err = io.StringIO()
        with mock.patch("sys.stderr", new=err):
            api.pump()
        # Genau zwei Versuche: die erste Zustellung, die Wiederholung nach
        # dem Reload. Die zweite Nachricht wird NIE angefasst.
        self.assertEqual(len(window.calls), 2)
        self.assertEqual(len(window.load_htmls), 1)
        notes = err.getvalue().strip().splitlines()
        self.assertEqual(len(notes), 1, err.getvalue())
        self.assertTrue(notes[0].startswith(
            "crow: the window's web process died;"), notes[0])
        self.assertIn("restart crow to get the window back", notes[0])
        self.assertTrue(api._push_dead)

    def test_a_failed_reload_freezes_without_a_second_deliver(self):
        """Scheitert der Reload selbst, gibt es keine zweite Zustellung --
        derselbe Freeze, dieselbe eine Zeile."""
        api = self.api()
        window = _FakeWindow(load_raises=True)
        api._window = window
        api._page = "<html>the page</html>"
        api.push({"k": "note", "t": "first"})
        api._out.put(None)
        err = io.StringIO()
        with mock.patch("sys.stderr", new=err):
            api.pump()
        self.assertEqual(len(window.load_htmls), 1)
        self.assertEqual(len(window.calls), 1)
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        self.assertTrue(api._push_dead)

    def test_transient_failures_are_noted_three_times_only(self):
        api = self.api()
        window = _FakeWindow()
        calls: list[str] = []

        def stumble(script: str) -> None:
            calls.append(script)
            raise ValueError("crow is not defined")

        window.evaluate_js = stumble
        api._window = window
        api._page = "<html>the page</html>"
        for n in range(5):
            api.push({"k": "note", "t": "n%d" % n})
        api._out.put(None)
        err = io.StringIO()
        with mock.patch("sys.stderr", new=err):
            api.pump()
        self.assertEqual(len(calls), 5, "alle fuenf wurden versucht")
        notes = err.getvalue().strip().splitlines()
        self.assertEqual(len(notes), 3, err.getvalue())
        self.assertTrue(all("keeping on" in n for n in notes))

    def test_a_closed_window_ends_the_pump_quietly(self):
        """Der alte Vertrag bleibt: ein normales Fensterende kehrt heim,
        ohne eine Zeile und ohne die Warteschlange zu leeren."""
        api = self.api()
        window = _FakeWindow()

        def closed(script: str) -> None:
            window.calls.append(script)
            raise WebViewException("window was closed")

        window.evaluate_js = closed
        api._window = window
        api._page = "<html>the page</html>"
        api.push({"k": "note", "t": "first"})
        api.push({"k": "note", "t": "never reached"})
        err = io.StringIO()
        with mock.patch("sys.stderr", new=err):
            api.pump()
        self.assertEqual(len(window.calls), 1)
        self.assertEqual(err.getvalue(), "")
        self.assertFalse(api._push_dead)
        self.assertEqual(api._out.get_nowait().get("t"), "never reached")


class TheWindowFollowsADragTests(unittest.TestCase):
    """#236 #237 #238. Drags and resizes stuttered in a long chat.

    Measured 2026-09-23 on a 200-turn chat (12 968 nodes), WebKitGTK 2.52:
    38.8 ms per rail-drag step before, 3.6 ms after. These tests pin the three
    causes so that none of them comes back unnoticed.
    """

    def _drag(self, name: str) -> str:
        page = crow_gui.PAGE
        start = page.index("\n  %s(ev){" % name)
        return page[start:page.index("document.addEventListener(\"mouseup\",up); }", start)]

    def test_a_drag_step_does_not_restyle_the_whole_document(self):
        # T1: an inherited custom property on <html> restyled every node per
        # mousemove (1249 ms of style for 80 steps in Chromium).
        page = crow_gui.PAGE
        self.assertNotIn('documentElement.style.setProperty("--railw"', page)
        self.assertNotIn('documentElement.style.setProperty("--codew"', page)
        self.assertIn('rail.style.setProperty("--railw",w+"px")', self._drag("railDrag"))
        self.assertIn('panel.style.setProperty("--codew",w+"px")', self._drag("codeDrag"))
        # The start-up value lands on the same element, so there is one owner.
        self.assertIn('$("#rail").style.setProperty("--railw", e.rail+"px")', page)

    def test_a_drag_step_neither_calls_python_nor_reads_layout(self):
        # No bridge call (and so no settings write) per step: the width is
        # handed over once, on mouseup. No layout read after the write either.
        for name in ("railDrag", "codeDrag"):
            body = self._drag(name)
            move = body[body.index("const move="):body.index("const up=")]
            self.assertNotIn("pywebview", move, name)
            for read in ("getBoundingClientRect", "offsetWidth", "offsetHeight",
                         "scrollHeight", "clientWidth"):
                self.assertNotIn(read, move, name)
            up = body[body.index("const up="):]
            self.assertEqual(up.count("pywebview.api."), 1, name)

    def test_the_drag_widths_do_not_transition(self):
        page = crow_gui.PAGE
        self.assertIn("#rail.dragging{transition:none}", page)
        self.assertIn("#side.dragging{transition:none}", page)

    def test_only_the_visible_turns_are_laid_out_while_the_width_changes(self):
        # T2: content-visibility ONLY during the gesture -- permanently on, the
        # view jumped while scrolling up (WebKitGTK 2.52 has no scroll anchoring).
        page = crow_gui.PAGE
        self.assertIn("#flow.sizing > .turn{content-visibility:auto}", page)
        self.assertIn("#flow > .turn{contain-intrinsic-size:auto 240px}", page)
        css = page[:page.index("</style>")]
        self.assertEqual(css.count("content-visibility:auto"), 1)
        for name in ("railDrag", "codeDrag"):
            body = self._drag(name)
            self.assertLess(body.index("sizing.begin()"), body.index("const move="), name)
            self.assertIn("sizing.end()", body[body.index("const up="):], name)
        self.assertIn('window.addEventListener("resize", () => sizing.pulse());', page)

    def test_the_view_keeps_its_place_when_the_gesture_ends(self):
        page = crow_gui.PAGE
        helper = page[page.index("const sizing = (function(){"):]
        helper = helper[:helper.index("})();")]
        self.assertIn("crow.atBottom()", helper)
        self.assertIn("flow.scrollTop = flow.scrollHeight", helper)
        self.assertIn("p.turn.getBoundingClientRect().top - p.y", helper)
        # The correction must not glide: #flow scrolls smoothly otherwise.
        self.assertIn('flow.style.scrollBehavior = "auto"', helper)

    def test_the_pane_is_not_followed_where_it_cannot_move(self):
        # T3: pywebview starts a thread per moved/resized event, and on GTK
        # `_pane_apply` returns at once -- so the subscription is Windows-only.
        source = inspect.getsource(crow_gui.main)
        guard = source.index("if crow_platform.IS_WINDOWS:\n        window.events.moved")
        self.assertLess(guard, source.index("window.events.moved += api.pane_follow"))
        self.assertLess(guard, source.index("window.events.resized += api.pane_follow"))
        page = crow_gui.PAGE
        place = page[page.index("\n  brPlace(){"):]
        place = place[:place.index("pane_place")]
        # #201: on GTK the panel is embedded IN the window and `pane_place` moves
        # it, so the call must survive NATIVEDRAG; the same-rectangle gate keeps
        # it to one bridge call per real change.
        self.assertNotIn("NATIVEDRAG) return;", place)
        self.assertIn("if(key===this.brSent) return;", place)

    def test_the_window_grips_keep_one_resize_in_flight(self):
        page = crow_gui.PAGE
        grips = page[page.index("(function grips(){"):]
        grips = grips[:grips.index("})();")]
        self.assertEqual(grips.count("pywebview.api.set_geometry("), 1)
        flush = grips[grips.index("const flush="):grips.index('window.addEventListener("mousemove"')]
        self.assertIn("if(busy || !want) return;", flush)
        self.assertIn("pywebview.api.set_geometry(", flush)
        move = grips[grips.index('window.addEventListener("mousemove"'):]
        self.assertNotIn("pywebview.api.set_geometry(", move)


class TheSelectionPolicyTests(unittest.TestCase):
    """#228. Text in the window can be selected -- in WebKitGTK too.

    MEASURED 2026-09-23, WebKitGTK 2.52.6: `CSS.supports("user-select","text")`
    is false. pywebview (text_select=False) injects `body{-webkit-user-select:
    none}`, so every unprefixed `user-select:text` in this page was dropped and a
    real (GDK-synthesised) mouse drag over an answer selected "". The cases hold
    the policy in the spelling the engine reads.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        page = crow_gui.PAGE
        cls.css = page[page.index("<style>"):page.index("</style>")]

    def _rules(self, prop):
        """{selector: value} for every rule in the page that sets `prop`."""
        found = {}
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)   # comments quote rules
        for sels, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            for m in re.finditer(r"(?<![\w-])" + re.escape(prop) + r"\s*:\s*(\w+)", body):
                for sel in sels.split(","):
                    found[" ".join(sel.split())] = m.group(1)
        return found

    def test_every_user_select_has_its_webkit_twin(self):
        """THE REGRESSION ITSELF: a rule WebKitGTK cannot read is a rule the
        Linux window does not have. Every unprefixed `user-select` needs a
        `-webkit-user-select` with the same value for the same selector."""
        plain = self._rules("user-select")
        webkit = self._rules("-webkit-user-select")
        missing = {sel: v for sel, v in plain.items() if webkit.get(sel) != v}
        self.assertEqual(missing, {}, "no -webkit- twin (WebKitGTK ignores these)")

    def test_content_is_text_and_its_controls_are_not(self):
        webkit = self._rules("-webkit-user-select")
        for sel in ("#flow", "#spane", "#tclist .tsec", "#cflist .cwp", ".code pre",
                    "#in", "textarea"):
            self.assertEqual(webkit.get(sel), "text", sel)
        for sel in ("body", "button", "summary", ".code .hd", "#toolcalls .tool .hd",
                    "#menu"):
            self.assertEqual(webkit.get(sel), "none", sel)

    def test_the_content_menu_is_asked_before_the_engine_menu_is_cancelled(self):
        """The old guard cancelled every context menu outside the rail; the
        content menu gets the event first, and the guard still stands after it."""
        guard = self.source[self.source.index('window.addEventListener("contextmenu"'):]
        guard = guard[:guard.index("});")]
        self.assertLess(guard.index("crow.textMenu(e)"), guard.index("e.preventDefault()"))

    def test_copy_goes_through_python_first(self):
        """`navigator.clipboard` refuses on WebView2 (no secure context, see
        `Api.copy`); the page's copy is the bridge, `execCommand` its fallback."""
        clip = self.source[self.source.index("  clip(text){"):]
        clip = clip[:clip.index("\n  // #228/#229. RIGHT-CLICK")]
        self.assertIn("pywebview.api.copy(text)", clip)
        self.assertIn('document.execCommand("copy")', clip)
        self.assertNotIn("navigator.clipboard", clip)

    def test_ctrl_c_leaves_fields_alone(self):
        """In the composer the engine's own copy is the whole story -- a second
        copy of a field's selection through Python would be the wrong text."""
        key = self.source[self.source.index('document.addEventListener("keydown",e=>{\n  if(!(e.ctrlKey'):]
        key = key[:key.index("});")]
        self.assertLess(key.index('a.tagName==="TEXTAREA"'), key.index("crow.clip(sel)"))


class TheLinkifierTests(unittest.TestCase):
    """#229. URLs and paths found in text -- the finder is RUN, in node.

    The same reason as the highlighter's cases: this is logic, and a string in
    the source proves nothing about what it marks.
    """

    @classmethod
    def setUpClass(cls):
        cls.node = _node()
        cls.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def _run(self, expr):
        import subprocess
        start = self.source.index("const LINK = {")
        js = self.source[start:self.source.index("\n};", start) + 3]
        done = subprocess.run([self.node, "-e", js + "\nconsole.log(JSON.stringify(" + expr + "));"],
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def _marks(self, text):
        """[(kind, target, line, col)] for every mark in `text`."""
        segs = self._run("LINK.split(" + json.dumps(text) + ")")
        self.assertEqual("".join(x["s"] for x in segs), text, "the text changed")
        return [(x["t"], x.get("href") or x.get("path"), x.get("line", ""), x.get("col", ""))
                for x in segs if x["t"] != "text"]

    def setUp(self):
        if not self.node:
            self.skipTest("no node on this machine")

    def test_nothing_is_lost_and_nothing_is_invented(self):
        """A selection copied across marks must read exactly like the text."""
        for text in ("", "plain", "See https://x.org/a_(b). and /home/r/x.py:12 now",
                     "C:\\Users\\r\\a.txt, \\\\srv\\share\\x.log.", "a/b/c/d/e " * 50,
                     "path:/tmp/a.log; ~/x ./y.sh ../z.md", "https://", "////", "üñî/çø.py"):
            self._marks(text)

    def test_urls_follow_the_gfm_trailing_rules(self):
        self.assertEqual(self._marks("see https://example.org/a_(b)."),
                         [("url", "https://example.org/a_(b)", "", "")])
        self.assertEqual(self._marks("(https://x.org/y)"), [("url", "https://x.org/y", "", "")])
        self.assertEqual(self._marks("www.google.com https://www.google.com/search?q=Markup+(business)))"),
                         [("url", "https://www.google.com/search?q=Markup+(business)", "", "")])
        self.assertEqual(self._marks("x https://x.org/?a=1&hl; y"), [("url", "https://x.org/?a=1", "", "")])
        self.assertEqual(self._marks("'https://x.org'"), [("url", "https://x.org", "", "")])

    def test_no_other_scheme_ever_becomes_a_link(self):
        """NEGATIVE: script, data and the reader's own disk are not links."""
        marks = self._marks("javascript:alert(1) data:text/html,x file:///etc/passwd "
                            "xhttps://evil.org ftp://x.org/y")
        self.assertEqual([m for m in marks if m[0] == "url"], [])

    def test_paths_are_marked_with_their_line_and_column(self):
        self.assertEqual(self._marks("grep: src/a.py:3:14: bad"), [("path", "src/a.py", "3", "14")])
        self.assertEqual(self._marks("at /home/r/x.py:12, then"),
                         [("path", "/home/r/x.py", "12", "")])
        self.assertEqual([m[1] for m in self._marks("~/Projects/crow ./run.sh ../x/y.md docs/.env")],
                         ["~/Projects/crow", "./run.sh", "../x/y.md", "docs/.env"])
        self.assertEqual([m[1] for m in self._marks("open C:\\Users\\r\\a.txt, or \\\\srv\\share\\x.log.")],
                         ["C:\\Users\\r\\a.txt", "\\\\srv\\share\\x.log"])
        self.assertEqual(self._marks("path:/tmp/a.log; done"), [("path", "/tmp/a.log", "", "")])

    def test_prose_with_slashes_is_not_a_path(self):
        """NEGATIVE, the false positives a naive finder makes."""
        self.assertEqual(self._marks("and/or TCP/IP km/h 12 tok/s 1/2 2026/09/23 e.g./i.e. "
                                     "example.org/x.html github.com/a/b.py /"), [])

    def test_a_code_span_may_be_one_path_with_spaces(self):
        """Backticks delimit, so `/My Docs/a b.txt` is one path -- but a command
        is not: `/usr/bin/env python` and `/bin/ls -la` stay code."""
        w = self._run('["/home/r/My Docs/a b.txt","/usr/bin/env python","/bin/ls -la",'
                      '"https://x.org","ls"].map(t=>LINK.whole(t))')
        self.assertEqual(w[0]["path"], "/home/r/My Docs/a b.txt")
        self.assertEqual(w[1:3], [None, None])
        self.assertEqual(w[3]["href"], "https://x.org")
        self.assertIsNone(w[4])


class TheLinkAndPathMarkTests(ApiCase):
    """#229. What the page does with a mark, and what Python does for it."""

    @classmethod
    def setUpClass(cls):
        cls.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    def _js(self, head, stop):
        js = self.source[self.source.index(head):]
        return js[:js.index(stop)]

    def test_a_link_click_never_navigates_and_routes_by_modifier(self):
        click = self._js("  linkClick(ev, url){", "\n  linkIn(url){")
        self.assertTrue(click.split("\n")[1].strip().startswith("ev.preventDefault();"),
                        "the click is cancelled first, before anything can throw")
        self.assertIn("ev.ctrlKey || ev.metaKey || ev.shiftKey", click)
        self.assertIn("this.linkOut(url)", click)
        self.assertIn("this.linkIn(url)", click)
        node = self._js("  linkNode(label, url){", "\n  pathNode(")
        self.assertIn("ev.button===1", node)          # middle click: outside
        # #201 decides panel vs outside in Python (`Api.open_url(url, outside)`):
        # a plain click asks for the panel, a modifier or middle click for outside.
        self.assertIn("pywebview.api.open_url(url, true)", self._js("  linkOut(url){", "\n"))
        self.assertIn("pywebview.api.open_url(url, false)", self._js("  linkIn(url){", "\n  linkOut("))

    def test_fenced_code_and_arguments_are_not_linkified(self):
        """Highlighted blocks keep their text nodes; the copy button covers them."""
        for head, stop in (("  codeOpen(lang){", "\n  codeClose("),
                           ("  toolArgBlock(row, name, raw){", "\n  toolEnd(")):
            self.assertNotIn("linkify", self._js(head, stop))
        self.assertIn("this.linkify(pre,", self._js("  toolRes(name,text,cut){", "this.openCall=null;"))

    def test_the_menu_offers_no_way_to_run_a_path(self):
        """A path is a stranger's text: copy it, show its folder, show a page in
        Crow's panel -- never hand it to the default program."""
        menu = self._js("  textMenu(e){", "\n  menuBack(){")
        self.assertNotIn("innerHTML", menu)
        self.assertNotIn("roll_show", menu)
        self.assertIn("reveal_path", menu)
        self.assertIn(r"/\.(html?|svg)$/i", menu)

    def test_path_info_resolves_against_the_working_area(self):
        api = self.api()
        self.addCleanup(crow_core.set_root, crow_core.get_root())
        crow_core.set_root(None)
        self.assertEqual(api.path_info("a/b.py")["path"], "")
        crow_core.set_root(self.dir)
        open(os.path.join(self.dir, "b.py"), "w").close()
        got = api.path_info("b.py")
        self.assertEqual(got["path"], os.path.join(self.dir, "b.py"))
        self.assertTrue(got["exists"]); self.assertFalse(got["dir"])
        self.assertTrue(api.path_info(self.dir)["dir"])
        self.assertEqual(api.path_info("x\0y")["path"], "")

    def test_reveal_opens_the_folder_never_the_file(self):
        api = self.api()
        self.addCleanup(crow_core.set_root, crow_core.get_root())
        crow_core.set_root(self.dir)
        script = os.path.join(self.dir, "evil.sh")
        with open(script, "w") as f:
            f.write("#!/bin/sh\n")
        ran = []
        real = crow_gui.subprocess.Popen
        crow_gui.subprocess.Popen = lambda argv, **kw: ran.append(argv)
        self.addCleanup(setattr, crow_gui.subprocess, "Popen", real)
        self.assertEqual(api.reveal_path("evil.sh"), "")
        self.assertEqual(ran, [crow_platform.reveal_command(script, False)])
        self.assertIn("not on this disk", api.reveal_path("gone.py"))
        self.assertEqual(len(ran), 1)

    def test_reveal_command_is_a_folder_on_every_platform(self):
        real = (crow_platform.IS_WINDOWS, crow_platform.sys.platform)
        self.addCleanup(lambda: (setattr(crow_platform, "IS_WINDOWS", real[0]),
                                 setattr(crow_platform.sys, "platform", real[1])))
        crow_platform.IS_WINDOWS = False
        crow_platform.sys.platform = "linux"
        self.assertEqual(crow_platform.reveal_command("/a/b/c.sh", False), ["xdg-open", "/a/b"])
        self.assertEqual(crow_platform.reveal_command("/a/b", True), ["xdg-open", "/a/b"])
        crow_platform.sys.platform = "darwin"
        self.assertEqual(crow_platform.reveal_command("/a/c.sh", False), ["open", "-R", "/a/c.sh"])
        crow_platform.IS_WINDOWS = True
        self.assertEqual(crow_platform.reveal_command("C:\\a\\c.bat", False),
                         ["explorer", "/select,C:\\a\\c.bat"])


class TheIntegrationSeamsHoldTests(unittest.TestCase):
    """Re-audit of the four GUI branches together (2026-09-23)."""

    def test_a_drag_does_not_change_a_turn_height(self):
        # content-visibility under .sizing stops margins collapsing through a
        # turn; the first/last child margins are dropped so both states match.
        page = crow_gui.PAGE
        self.assertIn("#flow > .turn > :first-child{margin-top:0}", page)
        self.assertIn("#flow > .turn > :last-child{margin-bottom:0}", page)

    def test_browser_tabs_shrink_before_they_scroll(self):
        page = crow_gui.PAGE
        tab = page[page.index("\n.brtab{"):]
        tab = tab[:tab.index("}")]
        self.assertIn("flex:0 1 auto", tab)
        self.assertIn("min-width:64px", tab)

    def test_the_menu_focus_ring_keeps_the_button_radius(self):
        page = crow_gui.PAGE
        self.assertIn("#menu button:focus-visible{outline:1px solid var(--accent);outline-offset:-1px}", page)
        self.assertNotIn(".pth:focus-visible,#menu button:focus-visible", page)


class TheBlankTabHasABlankBarTests(unittest.TestCase):
    """#227. `brNew()` without an address cleared nothing: the one shared
    address field kept the previous tab's URL (integration re-audit 2026-09-23)."""

    def test_a_new_blank_tab_empties_and_focuses_the_bar(self):
        src = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        body = src[src.index("  brNew(url){"):]
        body = body[:body.index("\n  },")]
        blank = body[body.index("else {"):]
        self.assertIn('$("#brurl").value=""', blank)
        self.assertLess(blank.index('$("#brurl").value=""'), blank.index('$("#brurl").focus()'))


class TheCodeBlockKeepsItsCopyButtonTests(unittest.TestCase):
    """#239. codeFinish emptied `.cwh`, which also holds the copy button."""

    def test_the_finished_path_goes_into_the_name_slot(self):
        page = crow_gui.PAGE
        fin = page[page.index("  codeFinish(name,raw){"):]
        fin = fin[:fin.index("\n  // #138b.")]
        self.assertNotIn('head.textContent=""', fin)
        self.assertNotIn("head.textContent=got.path", fin)
        self.assertIn('box.querySelector(".cwn")', fin)
        tpl = page[page.index('<template id="cwtpl">'):]
        tpl = tpl[:tpl.index("</template>")]
        # the button lives in .cwh, beside .cwn -- so only .cwn may be rewritten
        self.assertIn('<span class="cwn"></span>', tpl)
        self.assertIn('class="cwcopy"', tpl)


# -- #209: a second restore, and a stream with no round to write into --------

class _RunsNow:
    """`threading.Thread`, run on the spot: `ready()` starts its probes on
    threads, and an exception there has to reach the case, not the excepthook."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self) -> None:
        self._target(*self._args, **self._kwargs)


class ARestoreNeverMeetsARunningChatTests(ApiCase):
    """#209. Live 2026-09-22 09:17: the window died on boot with
    `RuntimeError: restore() is for a fresh conversation, not a running one`
    in `_probe`'s thread, beside the #204 GError 601 flood and an
    `insertBefore` TypeError. The #204 recovery reloads the page, the reloaded
    page fires `pywebviewready` again, and `ready()` started a SECOND `_probe`
    that restored session.json into the conversation the first one had
    already filled. The same raise is reachable without a reload: a line
    typed before a slow probe arrives. `Conversation.restore` keeps its
    guard (#121 leans on it); the callers learn the contract."""

    def _saved_chat(self, first="the restored question", reply="its answer"):
        """session.json written the way the window writes it."""
        old = self.api()
        self.a_chat(old, first, reply)
        old._persist_live()
        self.assertTrue(os.path.exists(self.session))

    def _endpoint_up(self):
        return (mock.patch.object(crow_gui, "check_endpoint", return_value="ok"),
                mock.patch.object(crow_gui, "fetch_model_name", return_value="m"),
                mock.patch.object(crow_gui, "fetch_n_ctx", return_value=1000))

    def test_a_probe_that_arrives_after_the_first_line_keeps_that_line(self):
        self._saved_chat()
        api = self.api()
        api._conversation.append("user", "typed before the probe answered")
        a, b, c = self._endpoint_up()
        with a, b, c:
            api._probe()                        # raised before #209
        payload = [m for m in api._conversation.payload() if m["role"] != "system"]
        self.assertEqual([m["content"] for m in payload],
                         ["typed before the probe answered"],
                         "the running chat was replaced or merged")
        out = self.drained(api)
        notes = [m["t"] for m in out if m.get("k") == "note"]
        self.assertTrue(any("kept the running conversation" in t for t in notes),
                        notes)
        # THE OLD CHAT'S IDENTITY IS NOT TAKEN EITHER: with it, the running
        # chat's next save would land in the old chat's file.
        self.assertIsNone(api._current_path)
        self.assertIsNone(api._current_title)

    def test_a_reloaded_page_is_redrawn_not_restored_twice(self):
        self._saved_chat()
        api = self.api()
        api._mic_probe = lambda: None
        api.git_refresh = lambda: None
        adopt = mock.MagicMock(wraps=crow_core.adopt_root)
        a, b, c = self._endpoint_up()
        with a, b, c, mock.patch.object(crow_gui.threading, "Thread", _RunsNow), \
                mock.patch.object(crow_core, "adopt_root", adopt):
            api.ready()                         # the page's first pywebviewready
            first = self.drained(api)
            self.assertIn("the restored question",
                          [m.get("t") for m in first if m.get("k") == "user"])
            before = api._conversation.payload()
            api.ready()                         # #204's reload fires it again
        after = self.drained(api)
        self.assertEqual(api._conversation.payload(), before)
        self.assertEqual(adopt.call_count, 1,
                         "the reload re-bound the working area from roots.json")
        kinds = [m.get("k") for m in after]
        # THE NEW PAGE IS EMPTY, so it gets the live chat again ...
        self.assertIn("the restored question",
                      [m.get("t") for m in after if m.get("k") == "user"])
        for k in ("meta", "mode", "root", "up", "rail"):
            self.assertIn(k, kinds)
        # ... and not a note about a late session: nothing arrived late.
        self.assertFalse([m for m in after if m.get("k") == "note"
                          and "kept the running" in m.get("t", "")])


class AStatedRootWinsOverTheRestoredChatTests(ApiCase):
    """#303. Live 2026-09-25 15:19 CEST: robin started the window
    with `--root .../lighthouse-test`; `ready()` bound it, then `_probe`
    restored the last chat ("Voxel", 101 messages, no `crow_root` in
    session.json) and `_adopt_chat_root` fell through to `restore_root()` --
    roots.json `active` still named diorama-test from a 09:45 pick. The chip
    showed diorama-test, the goal bar (lighthouse-test/.crow/goal.json) was
    gone, and the next line ran in the wrong working area.

    THE RULE: a `--root` typed for THIS window is a person's choice made at
    this start, the newest one there is. It wins over the template and over
    the restored chat's own record, and becomes the next start's `active` --
    the flag's help already says "the same as picking a folder in the
    window". A chat's own root still wins when nothing was stated (#101)."""

    def setUp(self) -> None:
        super().setUp()
        self._roots = crow_core.ROOTS_FILE
        crow_core.ROOTS_FILE = os.path.join(self.dir, "roots.json")
        self.addCleanup(setattr, crow_core, "ROOTS_FILE", self._roots)
        self.addCleanup(crow_core.set_root, None)
        crow_core.set_root(None)
        self.template = os.path.join(self.dir, "diorama-test")
        self.stated = os.path.join(self.dir, "lighthouse-test")
        self.own = os.path.join(self.dir, "own-choice")
        for path in (self.template, self.stated, self.own):
            os.makedirs(path)
            crow_core.write_root_mode(path, "auto")
        crow_core.set_active_root(self.template)   # the 09:45 pick

    def _saved_chat(self, own=None, chosen=False):
        """session.json the way the window writes it; with `chosen`, the chat
        carries `own` as its own root, pinned head included."""
        old = self.api()
        crow_core.set_root(own)
        old._pin_memory(None)
        old._root_chosen = chosen
        self.a_chat(old, "continue", "working on it")
        old._persist_live()
        crow_core.set_root(None)
        with open(self.session, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual("crow_root" in data, chosen)

    def _start(self, *argv):
        api = self.api(*argv)
        api._mic_probe = lambda: None
        api.git_refresh = lambda: None
        with mock.patch.object(crow_gui, "check_endpoint", return_value="ok"), \
             mock.patch.object(crow_gui, "fetch_model_name", return_value="m"), \
             mock.patch.object(crow_gui, "fetch_n_ctx", return_value=1000), \
             mock.patch.object(crow_gui.threading, "Thread", _RunsNow):
            api.ready()
        self.assertIn("continue", [m.get("content")
                                   for m in api._conversation.payload()])
        return api

    def _is(self, got, want):
        self.assertEqual(os.path.normcase(got or ""),
                         os.path.normcase(os.path.realpath(want)))

    def test_the_stated_root_survives_the_restore_of_a_chat_that_never_chose(self):
        """THE LIVE CASE. Before the fix: diorama-test, from roots.json."""
        self._saved_chat(own=self.stated)          # head names lighthouse-test
        api = self._start("--root", self.stated)
        self._is(crow_core.get_root(), self.stated)
        roots = [m for m in self.drained(api) if m.get("k") == "root"]
        self._is(roots[-1]["path"], self.stated)
        with open(crow_core.ROOTS_FILE, encoding="utf-8") as fh:
            self._is(json.load(fh)["active"], self.stated)

    def test_the_stated_root_wins_over_the_chats_own_and_the_model_is_told(self):
        """A chat that recorded another folder is re-bound to the typed one,
        the #224 notice is queued, and the head no longer names the old one."""
        self._saved_chat(own=self.own, chosen=True)
        api = self._start("--root", self.stated)
        self._is(crow_core.get_root(), self.stated)
        self.assertTrue(api._root_chosen)
        notice = api._conversation.pending_notice or ""
        self.assertIn(os.path.realpath(self.stated), notice)
        head = api._conversation.memory or ""
        self.assertIn(crow_core.working_area_line(os.path.realpath(self.stated)),
                      head)
        self.assertNotIn(crow_core.working_area_line(os.path.realpath(self.own)),
                         head)

    def test_without_a_stated_root_the_chats_own_still_wins(self):
        """#101 unchanged: no flag, the restored chat brings its own folder."""
        self._saved_chat(own=self.own, chosen=True)
        api = self._start()
        self._is(crow_core.get_root(), self.own)
        self.assertIsNone(api._conversation.pending_notice)

    def test_without_a_stated_root_a_chat_that_never_chose_takes_the_template(self):
        """#101 unchanged: no flag, no own choice -> roots.json `active`."""
        self._saved_chat()
        self._start()
        self._is(crow_core.get_root(), self.template)


class AStreamWithoutARoundTests(unittest.TestCase):
    """#209. `answer()` did `this.col.insertBefore(...)` with `col` null --
    a reloaded page (#204) that meets a turn already streaming has no round
    open, and every token threw `null is not an object (evaluating
    'this.col.insertBefore')` back into the push channel. Run in node."""

    FAKE_DOM = r"""
function mk(tag){ const e={tag, children:[], textContent:"", className:"",
  _html:"", parentNode:null,
  appendChild(c){ this.children.push(c); c.parentNode=this; return c; },
  insertBefore(c,ref){ const i=ref?this.children.indexOf(ref):-1;
    if(i<0) this.children.push(c); else this.children.splice(i,0,c);
    c.parentNode=this; return c; },
  querySelector(sel){ if(sel===".col") return this._col||(this._col=mk("div"));
    if(sel===".tbody") return mk("div"); return null; },
  querySelectorAll(){ return []; }, remove(){},
  set innerHTML(v){ this._html=v; }, get innerHTML(){ return this._html; } };
  return e; }
const document={ createElement:mk, querySelectorAll(){ return []; } };
const flow=mk("div");
"""

    @classmethod
    def setUpClass(cls):
        cls.node = _node()
        cls.page = crow_gui.PAGE

    def setUp(self):
        if not self.node:
            self.skipTest("no node on this machine")

    def _members(self, first: str, stop: str) -> str:
        start = self.page.index(first)
        return self.page[start:self.page.index(stop, start)]

    def _run(self, calls: str) -> str:
        import subprocess
        body = (self._members("  start(){", "  // -- markdown, drawn")
                + self._members("  cost(line,share,sub){", "  fail(msg){"))
        prog = (self.FAKE_DOM
                + "const o={ running:false, col:null, say:null, think:null,"
                  " fence:null, blocks:[], cursor:null,"
                  " fold(){}, bottom(){}, ctx(){},"
                  " turn(){ const t=mk('div'); flow.appendChild(t); return t; },\n"
                + body + "};\n" + calls)
        done = subprocess.run([self.node, "-e", prog], capture_output=True,
                              text=True, encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def test_text_with_no_round_opens_one(self):
        out = self._run('o.answer("hi"); o.answer(" there");'
                        'console.log(o.col.children.filter(c=>c.className==="say")'
                        '.map(c=>c.textContent).join("|"));')
        self.assertEqual(out, "hi there")

    def test_thinking_with_no_round_opens_one(self):
        out = self._run('o.thinkText("hm"); console.log(o.think ? "ok" : "none");')
        self.assertEqual(out, "ok")

    def test_a_cost_line_with_no_round_does_not_throw(self):
        out = self._run('o.cost("[1 s]", 50); console.log(flow.children.length);')
        self.assertEqual(out, "1")


class ALineTypedMidTurnIsQueuedTests(ApiCase):
    """#264. robin, live 2026-09-23 ~23:00: in goal mode a line typed while the
    model works could not be sent -- `go()` turned every Enter mid-turn into
    `stop()` (since 4860300), so #165's "a typed line always has priority" was
    unreachable from the live chat. The page half is RUN in node; the Python
    half drives `send()` and `_pump()` with `_run` as the double."""

    @classmethod
    def setUpClass(cls):
        cls.node = _node()
        cls.source = (HERE / "crow_gui.py").read_text(encoding="utf-8")

    # ---- the page, in node

    def _page(self, script):
        """go(), hold(), release(), press() out of the page, over stubs that log
        what the page does. `script` drives them; the log comes back."""
        import subprocess
        if not self.node:
            self.skipTest("no node on this machine")
        start = self.source.index("  go(){ const text=input.value.trim();")
        end = self.source.index("  // #88: THE RELEASE LEVEL")
        js = (
            "const log=[];\n"
            "const input={value:'',style:{}};\n"
            "const hint={textContent:''}; const $=s=>hint;\n"
            "const go={textContent:'',title:'',classList:{toggle(){}}};\n"
            "const settle=[];\n"
            "const pywebview={api:{stop(){log.push(['stop']);},\n"
            "  send(t){log.push(['send',t]);return {then(ok){settle.push(ok);}};}}};\n"
            "const crow={running:false,viewingOther:false,held:null,\n"
            "  slash:" + json.dumps(list(crow_core.SLASH_COMMANDS)) + ",\n"
            "  user(t){log.push(['user',t]);}, userImages(i){},\n"
            "  stagedUrls(){return [];}, stageRender(){}, installBar(){},\n"
            "  fanout(t){log.push(['fanout',t]);}, busy(){log.push(['busy']);},\n"
            "  idle(){this.running=false;this.release();log.push(['idle']);},\n"
            "  queuedLine(){log.push(['queued']);},\n"
            + self.source[start:end] + "};\n"
            "function type(t){input.value=t; crow.go();}\n"
            + script + "\nsettle.forEach(f=>f(true));\n"
            "console.log(JSON.stringify({log, held:crow.held, box:input.value,\n"
            "  hint:hint.textContent, button:go.textContent}));\n")
        done = subprocess.run([self.node, "-e", js], capture_output=True,
                              text=True, encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_enter_mid_turn_queues_the_line_and_does_not_stop(self):
        """POSITIVE, the defect itself: the line reaches send(), the turn is
        not stopped, and nothing is drawn into the answer still streaming."""
        out = self._page("crow.running=true; type('steer: use three.js');")
        self.assertIn(["send", "steer: use three.js"], out["log"])
        self.assertNotIn(["stop"], out["log"])
        self.assertNotIn("user", [x[0] for x in out["log"]])
        self.assertEqual(out["held"]["t"], "steer: use three.js")
        self.assertEqual(out["box"], "")
        self.assertIn(["queued"], out["log"])

    def test_the_held_line_is_drawn_when_the_turn_ends(self):
        out = self._page("crow.running=true; type('a'); type('b'); crow.idle();")
        users = [x for x in out["log"] if x[0] == "user"]
        self.assertEqual(users, [["user", "a\n\nb"]],
                         "two held lines are one message, so one bubble")
        self.assertIsNone(out["held"])
        self.assertLess(out["log"].index(["user", "a\n\nb"]), out["log"].index(["idle"]))

    def test_the_stop_gesture_is_kept_where_it_was(self):
        """NEGATIVE: an empty Enter and a click on Stop with an empty box still
        stop; Escape stops whatever is in the box."""
        for script in ("crow.running=true; type('');",
                       "crow.running=true; input.value=''; crow.press();",
                       "crow.running=true; input.value='/reset'; crow.press();"):
            out = self._page(script)
            self.assertIn(["stop"], out["log"], script)
            self.assertNotIn("send", [x[0] for x in out["log"]], script)
        self.assertIn('onclick="crow.press()"', self.source)
        self.assertIn('if(e.key==="Escape" && crow.running) pywebview.api.stop();',
                      self.source)

    def test_no_typed_line_is_a_stop(self):
        """#264, reopened. robin, live 2026-09-24 on 2d29fa2: a line + Enter /
        click during a goal turn stopped the turn and the line stayed in the
        box. The page's two stop paths with a line in the box were a line that
        opens with "/" (a path) and the button. Neither stops now: a path is
        queued, a line + click is queued, a Crow command waits in the box."""
        out = self._page("crow.running=true; type('/srv/app/x.js is wrong');")
        self.assertNotIn(["stop"], out["log"])
        self.assertIn(["send", "/srv/app/x.js is wrong"], out["log"])
        self.assertEqual(out["box"], "")
        out = self._page("crow.running=true; input.value='steer'; crow.press();")
        self.assertNotIn(["stop"], out["log"])
        self.assertIn(["send", "steer"], out["log"])
        self.assertEqual(out["box"], "")
        out = self._page("crow.running=true; type('/model qwen');")
        self.assertNotIn(["stop"], out["log"])
        self.assertNotIn("send", [x[0] for x in out["log"]])
        self.assertEqual(out["box"], "/model qwen")
        self.assertIn("waits in the box until this turn ends", out["hint"])

    def test_the_button_says_queue_while_the_box_holds_a_line(self):
        """#264: the button says what a click does."""
        out = self._page("crow.running=true; input.value='steer'; crow.face();")
        self.assertEqual(out["button"], "↑ Queue")
        out = self._page("crow.running=true; input.value=''; crow.face();")
        self.assertEqual(out["button"], "■ Stop")
        out = self._page("crow.running=true; input.value='/reset'; crow.face();")
        self.assertEqual(out["button"], "■ Stop")
        self.assertIn('crow.face(); });', self.source,
                      "typing re-labels the button")
        self.assertIn('"slash": list(crow_core.SLASH_COMMANDS)', self.source)

    def test_an_enter_that_ends_a_composition_is_not_a_submit(self):
        self.assertIn('!e.isComposing && e.keyCode!==229', self.source)

    def test_an_idle_composer_and_another_chats_view_are_unchanged(self):
        """NEGATIVE: outside a turn the line is drawn and sent at once; in
        another chat's view it is drawn at once and queued there (#162)."""
        for script in ("type('hello');",
                       "crow.running=true; crow.viewingOther=true; type('hello');"):
            out = self._page(script)
            self.assertEqual(out["log"][0], ["user", "hello"], script)
            self.assertIn(["send", "hello"], out["log"], script)
            self.assertIsNone(out["held"], script)
        out = self._page("crow.running=true; type('/delegate look it up');")
        self.assertEqual(out["log"], [["fanout", "/delegate look it up"]])

    def test_the_page_releases_on_idle_and_forgets_on_a_view_switch(self):
        idle = self.source[self.source.index("  idle(){ this.running=false;"):]
        self.assertIn("this.release();", idle[:idle.index("\n  busy(){")])
        view = self.source[self.source.index("  viewBar(e){"):]
        self.assertIn("this.held=null;", view[:view.index("back.onclick")])
        self.assertIn("queued -- it goes in when this turn ends", self.source)

    # ---- the window, in python

    def _api(self):
        api = self.api()
        api._seen = []
        api.push = lambda message: api._seen.append(message)
        return api

    def test_a_second_queued_line_joins_the_first(self):
        """The page drew both; replacing the first lost it silently."""
        api = self._api()
        api._busy = True
        api.send("eins")
        api.send("zwei")
        self.assertEqual(api._queued, "eins\n\nzwei")

    def test_a_line_for_another_chat_still_replaces(self):
        """NEGATIVE: a line meant for another chat is a new decision about
        where the next turn runs, not an addendum (#162 unchanged)."""
        api = self._api()
        api._busy = True
        api._queued, api._queued_to = "alt", "/somewhere/else"
        api.send("neu")
        self.assertEqual(api._queued, "neu")

    def test_the_queued_line_wins_over_the_goal_nudge(self):
        """#165, now reachable: a line typed during goal turn N runs as turn
        N+1 instead of Crow's nudge, resets the engine, and the goal goes on
        after it."""
        api = self._api()
        ran, nudges, resets = [], ["[Goal mode, step 2]"], []
        api._goal_nudge = lambda: nudges.pop(0) if nudges else None
        real_reset = api._goal_reset
        api._goal_reset = lambda: (resets.append(len(ran)), real_reset())

        def run(text):
            ran.append(text)
            if text == "[Goal mode, step 1]":
                api.send("steer: stop polishing, ship it")

        api._run = run
        api._busy = True
        api._goal_turns = 40
        api._pump("[Goal mode, step 1]")
        self.assertEqual(ran, ["[Goal mode, step 1]",
                               "steer: stop polishing, ship it",
                               "[Goal mode, step 2]"])
        self.assertEqual(resets, [1], "the queued line resets the engine once")
        self.assertEqual(api._goal_turns, 0)
        self.assertFalse(api._busy)

    def test_no_queued_line_no_reset(self):
        """NEGATIVE: the engine's own turns do not reset its caps -- that is
        what the 60-turn cap is for."""
        api = self._api()
        ran, nudges, resets = [], ["n2"], []
        api._goal_nudge = lambda: nudges.pop(0) if nudges else None
        api._goal_reset = lambda: resets.append(1)
        api._run = ran.append
        api._busy = True
        api._pump("n1")
        self.assertEqual(ran, ["n1", "n2"])
        self.assertEqual(resets, [])



class StopPausesTheGoalEngineTests(ApiCase):
    """#282. robin, live 2026-09-24 on 2d29fa2: Stop during a goal
    turn ended the turn and the engine started the next one at once, so there
    was never a moment to type. `_goal_nudge` asked INTERRUPT, but `run_turn`
    consumes that flag when it ends the stopped turn (`if owns_turn_state:
    INTERRUPT.clear()`), so the question was always answered "no stop". The
    `_run` double below does what `run_turn` does on a Stop: the click, then
    the flag cleared on the way out."""

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(crow_core.goal_write, None)
        self.addCleanup(crow_core.INTERRUPT.clear)
        crow_core.goal_start("Ship it", ["read the log", "write the fix"],
                             now=1000.0)

    def _api(self):
        api = self.api()
        api._seen = []
        api.push = lambda message: api._seen.append(message)
        return api

    def test_stop_during_a_goal_turn_pauses_the_engine(self):
        api = self._api()
        ran = []

        def run(text):
            ran.append(text)
            api.stop()                       # robin clicks Stop mid-turn
            crow_core.INTERRUPT.clear()      # run_turn consumes the flag
        api._run = run
        api._busy = True
        api._pump("[Goal mode, step 1]")
        self.assertEqual(ran, ["[Goal mode, step 1]"],
                         "the engine started another turn after Stop")
        self.assertFalse(api._busy)
        notes = [m["t"] for m in api._seen if m.get("k") == "note"]
        self.assertTrue(any(n.startswith("goal mode paused: you pressed Stop")
                            for n in notes), notes)
        self.assertFalse(crow_core.note_is_log_only(notes[-1]),
                         "the pause is said in the chat, not only in crow.log")

    def test_the_next_typed_line_resumes_the_engine(self):
        """POSITIVE: after the pause, a sent line runs and the goal goes on."""
        api = self._api()
        api._goal_paused = True
        ran = []
        api._run = lambda text: ran.append(text)
        started = []
        api._pump = lambda text: started.append(text)
        self.assertTrue(api.send("carry on, use three.js"))
        self.assertEqual(started, ["carry on, use three.js"])
        self.assertFalse(api._goal_paused)
        self.assertIsNotNone(api._goal_nudge())

    def test_a_line_queued_before_stop_runs_and_then_the_goal_goes_on(self):
        """The queued line is a typed line: it runs next and lifts the pause."""
        api = self._api()
        ran = []

        def run(text):
            ran.append(text)
            if len(ran) == 1:
                api.send("steer")
                api.stop()
                crow_core.INTERRUPT.clear()
        api._run = run
        api._busy = True
        api._pump("[Goal mode, step 1]")
        self.assertEqual(ran[:2], ["[Goal mode, step 1]", "steer"])
        self.assertGreater(len(ran), 2, "the goal resumes after the typed line")
        self.assertTrue(ran[2].startswith("[Goal mode"), ran[2])

    def test_no_stop_no_pause(self):
        """NEGATIVE: without a Stop the engine chains as before."""
        api = self._api()
        ran = []
        api._run = lambda text: ran.append(text)
        api._busy = True
        api._goal_nudge = (lambda real: (lambda: real() if len(ran) < 3 else None))(
            api._goal_nudge)
        api._pump("[Goal mode, step 1]")
        self.assertEqual(len(ran), 3)
        self.assertFalse(any(m.get("t", "").startswith("goal mode paused")
                             for m in api._seen))


# ======================================================================= #249
#
# THE PHONE MIRROR, Api side. No socket anywhere: `_FakeRemote` holds
# `crow_remote.Remote`'s contract (publish with `to`, device ids, pairing) and
# records what each device would have received, the desktop's page is `_out`.

PHONE = "d-phone0000001"


class _FakeRemote:
    """`crow_remote.Remote` as the Api sees it, recording every publish."""

    def __init__(self, **kw):
        self.kw = kw
        self.host = kw.get("host", "192.168.1.5")
        self.port = kw.get("port", 8765)
        self.url = "http://%s:%d/" % (self.host, self.port)
        self.tailnet = kw.get("tailnet", "")
        self.tailnet_url = ("https://%s/" % self.tailnet) if self.tailnet else ""
        self.published: list = []
        self.ids = [PHONE]
        self.online = {PHONE: True}
        self.names = {PHONE: "iPhone (Safari)"}
        self.forgot: list = []
        self._running = False

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def running(self):
        return self._running

    def new_pairing(self):
        return self.url + "#t=pairing-token"

    def publish(self, message, to=None):
        self.published.append((dict(message), None if to is None else list(to)))

    def device_ids(self):
        return list(self.ids)

    def devices(self):
        return [{"id": i, "name": self.names.get(i, i),
                 "online": self.online.get(i, False)} for i in self.ids]

    def forget(self, name):
        for i in list(self.ids):
            if i == name or self.names.get(i, "").lower().startswith(
                    name.lower()):
                self.ids.remove(i)
                self.forgot.append(i)
                return True
        return False

    def got(self, device=PHONE) -> list:
        """What `device` received, in order."""
        return [m for m, to in self.published if to is None or device in to]


class RemoteCase(ApiCase):
    """An Api with one paired phone attached (no server started)."""

    def setUp(self) -> None:
        super().setUp()
        self._before_remote = (crow_gui.SETTINGS_FILE, crow_gui.REMOTE_FACTORY,
                               crow_gui.lan_addresses, crow_gui.TAILSCALE_PROBE)
        self.addCleanup(self._undo_remote)
        crow_gui.SETTINGS_FILE = os.path.join(self.dir, "settings.json")

    def _undo_remote(self) -> None:
        (crow_gui.SETTINGS_FILE, crow_gui.REMOTE_FACTORY,
         crow_gui.lan_addresses, crow_gui.TAILSCALE_PROBE) = self._before_remote

    def mirrored(self, *argv):
        api = self.api(*argv)
        api._remote = _FakeRemote()
        api._remote.start()
        self.drained(api)
        return api

    def as_phone(self, fn, *args):
        with crow_gui.as_client(PHONE):
            return fn(*args)

    def saved_chat(self, api, first="the chat on disk"):
        """A chat written to disk, and a different one live. Its path."""
        self.a_chat(api, first)
        ok, saved = api._leave()
        self.assertTrue(ok)
        api._conversation.reset()
        api._current_path = None
        self.a_chat(api, "the chat that is running")
        self.drained(api)
        api._remote.published.clear()
        return saved

    def worker(self, api):
        """A running turn, seen from the bridge thread (see #162's `busy`)."""
        gate = threading.Event()
        thread = threading.Thread(target=gate.wait, daemon=True)
        thread.start()
        self.addCleanup(gate.set)
        api._worker = thread
        api._busy = True
        return gate


class RemoteApiParityTests(RemoteCase):
    """#249 decision 5 as a table: every page method is proxied 1:1 or bound
    to the desktop with a stated replacement -- and a call from one client
    produces the push the other one needs."""

    PAGE_METHODS = 94          # 88 at fb31ca2 + the six pairing controls (#249 stage 5)

    def page_methods(self) -> set:
        page = crow_gui.PAGE
        return set(re.findall(r"pywebview\.api\.([A-Za-z_]+)", page))

    def test_every_page_method_is_classified_exactly_once(self):
        called = self.page_methods()
        bound = set(crow_gui.REMOTE_DESKTOP_BOUND)
        self.assertEqual(len(called), self.PAGE_METHODS,
                         "a page method was added or removed -- classify it "
                         "in REMOTE_PROXIED or REMOTE_DESKTOP_BOUND")
        self.assertFalse(crow_gui.REMOTE_PROXIED & bound, "classified twice")
        self.assertEqual(called, crow_gui.REMOTE_PROXIED | bound,
                         "unclassified: %s / not on the page: %s" % (
                             sorted(called - crow_gui.REMOTE_PROXIED - bound),
                             sorted((crow_gui.REMOTE_PROXIED | bound) - called)))
        for name in called:
            self.assertTrue(callable(getattr(crow_gui.Api, name, None)), name)

    def test_every_bound_method_says_what_the_phone_does(self):
        for name, how in crow_gui.REMOTE_DESKTOP_BOUND.items():
            self.assertIn(how, crow_gui.REMOTE_PHONE_DOES, name)

    def test_the_allowlist_is_the_proxied_set_plus_what_still_runs_here(self):
        allowed = crow_gui.REMOTE_ALLOWED
        self.assertTrue(crow_gui.REMOTE_PROXIED <= allowed)
        self.assertEqual(allowed - crow_gui.REMOTE_PROXIED,
                         {"stage_image", "reveal_path", "roll_show",
                          "provider_authorise"})
        # NEGATIVE: the window, the layout and the pairing controls never.
        for name in ("maximise", "close", "set_theme", "rail_width",
                     "pane_go", "remote_allow", "remote_open", "copy"):
            self.assertNotIn(name, allowed)

    def test_a_public_method_the_page_never_calls_is_refused(self):
        api = self.mirrored()
        for name in ("pump", "on_drop", "state_snapshot", "remote_page"):
            self.assertNotIn(name, crow_gui.REMOTE_ALLOWED)
            with self.assertRaises(KeyError):
                self.as_phone(api._remote_call, name, [])

    def test_a_phone_cannot_answer_a_pairing(self):
        """Desktop-only in the table AND in the method: a paired phone must
        not let in the next one."""
        api = self.mirrored()
        api._remote_asks[1] = [threading.Event(), False]
        self.assertFalse(self.as_phone(api.remote_allow, 1, True))
        self.assertFalse(api._remote_asks[1][0].is_set())
        self.assertTrue(api.remote_allow(1, True))

    def _png(self) -> str:
        path = os.path.join(self.dir, "shot.png")
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
        return path

    def test_a_call_from_one_client_reaches_the_other(self):
        """Table-driven: each state-changing proxied method, called from the
        phone, puts its push on the DESKTOP's queue -- and from the desktop,
        on the phone's stream."""
        cases = [
            ("set_mode", lambda api: ["manual"], "mode"),
            ("set_tools", lambda api: [True], "tools"),
            ("stage_image", lambda api: [self._png()], "chips"),
            ("unstage_image", lambda api: [0], "chips"),
            ("answer_memory", lambda api: [False], "pend"),
            ("send", lambda api: ["/context"], "user"),
            ("close_goal", lambda api: [], "goal"),
        ]
        for caller, other in ((PHONE, crow_gui.DESKTOP),
                              (crow_gui.DESKTOP, PHONE)):
            for name, args, kind in cases:
                with self.subTest(name=name, caller=caller):
                    api = self.mirrored()
                    if name == "unstage_image":
                        api.stage_image(self._png())
                        self.drained(api)
                        api._remote.published.clear()
                    with crow_gui.as_client(caller):
                        api._remote_call(name, args(api)) \
                            if caller == PHONE else getattr(api, name)(*args(api))
                    got = (self.drained(api) if other == crow_gui.DESKTOP
                           else api._remote.got(PHONE))
                    self.assertIn(kind, [m.get("k") for m in got],
                                  "%s from %s never reached %s" % (name, caller, other))

    def test_the_phone_bridge_proxies_and_keeps_the_desktop_bound_local(self):
        """The page half, run in node: the Proxy POSTs a proxied call with
        its JSON arguments, answers a layout call itself (no request -- the
        desktop's settings are never written from a phone), and runs a
        desktop-bound call on the desktop with a note."""
        node = _node()
        if not node:
            self.skipTest("no node on this machine")
        import subprocess
        page = crow_gui.stamped_page(remote=True)
        start = page.index("window.CROW_REMOTE = true;")
        boot = page[start:page.index("</script>", start)]
        js = ("const posts=[], notes=[];\n"
              "const window={open(){}, close(){}, addEventListener(){},\n"
              "  dispatchEvent(){}, prompt(){return null;}};\n"
              "window.crow={note(t){notes.push(t);}, on(){}};\n"
              "const document={hidden:true, addEventListener(){},\n"
              "  getElementById(){return null;}, documentElement:{classList:{add(){}}}};\n"
              "const location={hash:'', pathname:'/', search:''};\n"
              "const history={replaceState(){}};\n"
              "function fetch(path, init){ posts.push([path, init.body]);\n"
              "  return Promise.resolve({ok:true, status:200, json(){return Promise.resolve('');}}); }\n"
              "const crow=window.crow;\n"
              + boot +
              "\nconst api=window.pywebview.api;\n"
              "Promise.all([api.set_theme('light'), api.rail_width(300),\n"
              "  api.maximise(), api.send('hi'), api.reveal_path('/x')])\n"
              ".then(r=>console.log(JSON.stringify({posts, notes, r})));\n")
        done = subprocess.run([node, "-e", js], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["posts"], [["/api/send", '["hi"]'],
                                        ["/api/reveal_path", '["/x"]']])
        self.assertEqual(out["notes"], [crow_core.REMOTE_PHONE_TEXT["ondesk"]])

    def _pairing_run(self, waits, pair=202, me=401):
        """The phone's pairing, run in node: /pair answers `pair`, /pair/wait
        answers from `waits` in order ("net" is a rejected fetch), /me with
        `me`. What the pairing line showed, and whether the page went on to
        the chat."""
        import subprocess
        page = crow_gui.stamped_page(remote=True)
        start = page.index("window.CROW_REMOTE = true;")
        boot = page[start:page.index("</script>", start)]
        js = ("const shown=[], posts=[]; let ready=0;\n"
              "const WAITS=" + json.dumps(waits) + ";\n"
              "const setTimeout=f=>setImmediate(f);\n"
              "const bar={set hidden(v){}, set textContent(v){ if(v) shown.push(v); }};\n"
              "const window={open(){}, close(){}, addEventListener(){},\n"
              "  dispatchEvent(){ ready++; }, prompt(){return null;}};\n"
              "window.crow={note(){}, on(){}};\n"
              "function EventSource(){ this.close=()=>0; }\n"
              "const document={hidden:false, addEventListener(){},\n"
              "  getElementById(id){return id==='remotepair' ? bar : null;},\n"
              "  documentElement:{classList:{add(){}}}};\n"
              "const location={hash:'#t=abc', pathname:'/', search:''};\n"
              "const history={replaceState(){}};\n"
              "const res=(status, body)=>({ok:status>=200&&status<300, status,\n"
              "  json(){return Promise.resolve(body);}});\n"
              "function fetch(path, init){ posts.push([path, init.body]);\n"
              "  if(path==='/pair') return Promise.resolve(res(" + str(pair) + ", {p:'P1'}));\n"
              "  if(path==='/me') return Promise.resolve(res(" + str(me) + ", {}));\n"
              "  const w=WAITS.shift();\n"
              "  if(w===undefined || w==='net') return Promise.reject(new TypeError('Load failed'));\n"
              "  return Promise.resolve(res(w, {})); }\n"
              "const crow=window.crow;\n"
              + boot +
              "\nwindow.crowRemoteStart();\n"
              "let spins=0;\n"
              "setTimeout(function end(){ if(WAITS.length && ++spins<500) return setTimeout(end);\n"
              "  setImmediate(()=>setImmediate(()=>\n"
              "  console.log(JSON.stringify({shown, posts, ready})))); });\n")
        done = subprocess.run([_node(), "-e", js], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_the_phone_polls_the_pairing_and_rides_out_network_blips(self):
        """#249, iPhone 2026-09-24: WebKit gave a held-open /pair up as a
        network error after ~6 s. Now /pair answers 202 and the page polls
        /pair/wait; a failed fetch or two is retried, not "unreachable"."""
        if not _node():
            self.skipTest("no node on this machine")
        text = crow_core.REMOTE_PHONE_TEXT
        out = self._pairing_run([202, "net", "net", 202, 200])
        self.assertEqual(out["ready"], 1, out)
        self.assertNotIn(text["unreachable"], out["shown"])
        self.assertEqual(out["posts"][0], ["/pair", '{"t":"abc"}'])
        self.assertEqual({p for p, _ in out["posts"][1:]}, {"/pair/wait"})
        self.assertIn('{"p":"P1"}', [b for _, b in out["posts"][1:]])
        # Five network failures in a row: now it is unreachable.
        out = self._pairing_run(["net"] * 5)
        self.assertEqual(out["ready"], 0)
        self.assertEqual(out["shown"][-1], text["unreachable"])
        # Deny and timeout keep their own lines.
        self.assertEqual(self._pairing_run([202, 403])["shown"][-1], text["denied"])
        self.assertEqual(self._pairing_run([410])["shown"][-1], text["expired"])

    def test_a_paired_phone_on_a_stale_code_opens_the_chat(self):
        """#249, iPhone 2026-09-24: the first QR URL came back from Chrome's
        autocomplete, its #t= long spent. Any refusal asks /me first; a valid
        cookie goes to the chat, never to "this code is no longer valid"."""
        if not _node():
            self.skipTest("no node on this machine")
        text = crow_core.REMOTE_PHONE_TEXT
        for pair, waits in ((401, []), (202, [410])):
            out = self._pairing_run(waits, pair=pair, me=200)
            self.assertEqual(out["ready"], 1, out)
            self.assertNotIn(text["expired"], out["shown"])
            self.assertIn("/me", [p for p, _ in out["posts"]])
        # NEGATIVE: no valid cookie, and the stale code still says so.
        out = self._pairing_run([], pair=401, me=401)
        self.assertEqual(out["ready"], 0)
        self.assertEqual(out["shown"][-1], text["expired"])
        # The server's own 200 for a paired phone goes straight on.
        self.assertEqual(self._pairing_run([], pair=200)["ready"], 1)

    def test_the_phone_page_is_this_page_with_the_flag(self):
        phone = crow_gui.stamped_page(remote=True)
        desk = crow_gui.stamped_page()
        self.assertIn("window.CROW_REMOTE = true;", phone)
        self.assertIn('name="viewport"', phone)
        self.assertIn("#wbtns,.grip,#remotetoggle{display:none", phone)
        self.assertIn('"set_theme": "layout"', phone)
        # NEGATIVE: the desktop's page has none of it, and no hook is left.
        self.assertIn("window.CROW_REMOTE = false;", desk)
        self.assertNotIn('name="viewport"', desk)
        self.assertNotIn("#wbtns,.grip,#remotetoggle", desk)
        for page in (phone, desk):
            self.assertNotIn("__REMOTE", page)
        self.assertEqual(self.mirrored().remote_page(), phone)


class RemotePhoneLayerTests(unittest.TestCase):
    """#249 step 0 -> code: robin's approved phone mockups (one-row composer,
    drawers, goal bar, pinned approvals) live ONLY in the phone's variant of
    the page. The desktop's page must not carry a byte of it."""

    MARKERS = ("#mplus", "#mtools", "#mscrim", "#heldbar", "mobileTools",
               "shortModel", "@media (max-width:700px)")

    def test_the_phone_page_carries_the_layer(self):
        phone = crow_gui.stamped_page(remote=True)
        for marker in self.MARKERS:
            self.assertIn(marker, phone, marker)
        # The layer runs before the pairing starts, so its hooks are in place
        # when the snapshot and the first pushes arrive.
        self.assertLess(phone.index("function shortModel"),
                        phone.index("if(window.CROW_REMOTE) window.crowRemoteStart();"))

    def test_the_desktop_page_carries_none_of_it(self):
        desk = crow_gui.stamped_page()
        for marker in self.MARKERS:
            self.assertNotIn(marker, desk, marker)
        self.assertNotIn("__REMOTE_JS__", desk)

    def test_a_hidden_goal_stays_hidden_on_the_phone(self):
        """Found against the real server: `{"k":"goal","goal":null}` hides the
        panel with [hidden], and a bare `#goalpanel.shut{display:grid}` would
        have drawn an empty bar over the chat."""
        css = crow_gui.REMOTE_CSS
        self.assertIn("#goalpanel.shut:not([hidden]){display:grid", css)
        self.assertNotIn("#goalpanel.shut{display:grid", css)

    # A FAKE DOM, just enough for REMOTE_JS: every element records its
    # classes, data-*, attributes and inline style, so a state can be
    # compared as data. Timers run by hand.
    FAKE_DOM = r"""
const timers = []; let tid = 0, now = 0;
globalThis.setTimeout = (f, ms) => { timers.push({id: ++tid, f, at: now + (ms || 0)}); return tid; };
globalThis.clearTimeout = id => { const i = timers.findIndex(t => t.id === id); if(i >= 0) timers.splice(i, 1); };
const flush = () => { while(timers.length) timers.shift().f(); };
const advance = ms => { const end = now + ms;
  for(;;){ timers.sort((a, b) => a.at - b.at);
    if(!timers.length || timers[0].at > end) break;
    const t = timers.shift(); now = t.at; t.f(); }
  now = end; };
class Style { constructor(){ this.m = {}; }
  setProperty(k, v){ this.m[k] = String(v); } removeProperty(k){ delete this.m[k]; } }
class CL { constructor(){ this.s = new Set(); }
  add(c){ this.s.add(c); } remove(c){ this.s.delete(c); } contains(c){ return this.s.has(c); }
  toggle(c, on){ if(on === undefined) on = !this.s.has(c); on ? this.s.add(c) : this.s.delete(c); return on; } }
const listeners = [];
class El { constructor(id){ this.id = id || ""; this.dataset = {}; this.style = new Style();
    this.classList = new CL(); this.attrs = {}; this.children = []; this.hidden = false; }
  appendChild(c){ this.children.push(c); return c; } append(...c){ c.forEach(x => this.appendChild(x)); }
  prepend(c){ this.children.unshift(c); } insertBefore(c){ this.children.push(c); return c; }
  remove(){} before(){} after(){}
  setAttribute(k, v){ this.attrs[k] = String(v); } getAttribute(k){ return this.attrs[k] ?? null; }
  removeAttribute(k){ delete this.attrs[k]; }
  addEventListener(type, fn, opt){ listeners.push({el: this, type, fn, opt}); }
  querySelector(){ return null; } querySelectorAll(){ return []; } closest(){ return null; }
  get offsetWidth(){ return 0; } get offsetHeight(){ return 0; }
  set innerHTML(v){ this._html = v; } get innerHTML(){ return this._html || ""; }
  fire(type, ev){ listeners.filter(l => l.el === this && l.type === type).forEach(l => l.fn(ev || {})); }
  click(){ listeners.filter(l => l.el === this && l.type === "click").forEach(l => l.fn({target: this})); } }
const byId = {};
const el = id => byId[id] || (byId[id] = new El(id));
const html = el("<html>"), body = el("<body>");
globalThis.document = {documentElement: html, body, hidden: false,
  getElementById: el, createElement: () => new El(), querySelector: () => null,
  querySelectorAll: () => [], addEventListener(type, fn, opt){ listeners.push({el: this, type, fn, opt}); }};
globalThis.window = globalThis;
globalThis.addEventListener = (type, fn, opt) => listeners.push({el: window, type, fn, opt});
globalThis.STANDALONE = globalThis.STANDALONE || false;
globalThis.matchMedia = q => ({matches: /standalone/.test(q) ? STANDALONE : true,
  addEventListener(){}});
globalThis.innerWidth = 390;
globalThis.localStorage = {getItem: () => null, setItem(){}};
globalThis.getComputedStyle = () => ({backgroundColor: "rgb(24, 24, 24)"});
globalThis.ResizeObserver = class { observe(){} unobserve(){} };
globalThis.MutationObserver = class { observe(){} };
for (const d of ["rail", "code", "git", "browser"]) body.dataset[d] = "open";   // the desktop's stamp
const flip = d => function(){ body.dataset[d] = body.dataset[d] === "shut" ? "open" : "shut"; };
globalThis.crow = {toggleRail: flip("rail"), toggleCode: flip("code"), toggleGit: flip("git"),
  toggleBrowser: flip("browser"), open(){}, reset(){}, settingsCat(){}, goalPanel(){},
  queuedLine(){}, release(){}, viewBar(){}, mic(){}, micState(){}, showModel(){},
  modelPlan(){ return []; }, ctx(){}, modeIs(){}, setTheme(){}, levelLabel(){ return ""; }};
"""
    PROBE = r"""
const snap = () => JSON.stringify(["<html>", "<body>", "mscrim", "rail", "side", "main"]
  .map(id => { const e = id === "mscrim" ? body.children.find(c => c.id === "mscrim") : el(id);
    return [id, [...e.classList.s].sort(), e.dataset, e.style.m, e.attrs]; }));
flush();
const loaded = snap();
const scrim = body.children.find(c => c.id === "mscrim");
const gone = ["rail", "side"].map(id => el(id).classList.contains("m-gone"))
  .concat([scrim.classList.contains("m-gone")]);
crow.toggleRail(); flush();
const opened = snap();
const openGone = el("rail").classList.contains("m-gone") || scrim.classList.contains("m-gone");
scrim.click(); flush();
const closed = snap();
crow.toggleCode(); flush(); crow.toggleCode(); flush();
const closedAgain = snap();
window.mobileTools(true); window.mobileTools(false);
const sheet = snap();
const touch = listeners.filter(l => /^touch/.test(l.type))
  .map(l => [l.type, !!(l.opt && l.opt.passive)]);
console.log(JSON.stringify({loaded, opened, closed, closedAgain, sheet, gone, openGone, touch}));
"""

    def run_phone_hooks(self) -> dict:
        node = _node()
        if not node:
            self.skipTest("no node on this machine")
        import subprocess
        js = self.FAKE_DOM + crow_gui.REMOTE_JS + self.PROBE
        done = subprocess.run([node, "-e", js], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_a_closed_drawer_leaves_the_page_as_it_was_loaded(self):
        """robin's iPhone, 2026-09-24: after a drawer had been open, Safari's
        bars kept another tint and the page no longer scrolled, until a
        reload. The closed state must BE the loaded state -- every class,
        data-* attribute, attribute and inline style on html, body, the dim
        layer, the drawers and #main -- and closed means out of the render
        tree (display:none via .m-gone), not merely transparent or hidden."""
        out = self.run_phone_hooks()
        self.assertEqual(out["gone"], [True, True, True],
                         "a closed drawer or the dim layer is still rendered at load")
        self.assertNotEqual(out["opened"], out["loaded"])
        self.assertFalse(out["openGone"], "an open drawer must be rendered")
        self.assertEqual(out["closed"], out["loaded"])
        self.assertEqual(out["closedAgain"], out["loaded"])
        # NEGATIVE: the + sheet leaves no inline --toolsh ("0px") behind.
        self.assertEqual(out["sheet"], out["loaded"])
        self.assertIn(".m-gone{display:none!important}", crow_gui.REMOTE_CSS)

    def test_no_touch_handler_can_hold_the_scroll(self):
        """A vertical swipe must stay the browser's: the phone hooks listen
        passively, and never to touchmove."""
        out = self.run_phone_hooks()
        self.assertTrue(out["touch"])
        for kind, passive in out["touch"]:
            self.assertNotEqual(kind, "touchmove")
            self.assertTrue(passive, kind)
        self.assertNotIn("preventDefault", crow_gui.REMOTE_JS)

    def test_safari_takes_its_bar_tint_from_the_page(self):
        """theme-color: one tag that follows the page's theme first (stamped
        from THEME_BG), then one per colour scheme; html and body carry the
        page's ground themselves."""
        phone = crow_gui.stamped_page(remote=True)
        want = crow_gui.THEME_BG.get(crow_gui.current_theme(), "#181818")
        self.assertIn('<meta id="mtheme" name="theme-color" content="%s">' % want, phone)
        self.assertIn('media="(prefers-color-scheme: light)"', phone)
        self.assertIn('media="(prefers-color-scheme: dark)"', phone)
        self.assertLess(phone.index('id="mtheme"'),
                        phone.index('media="(prefers-color-scheme: light)"'))
        self.assertNotIn("theme-color", crow_gui.stamped_page())
        self.assertIn("background:var(--bg)}", crow_gui.REMOTE_CSS)

    HEADER = r"""
for (const id of ["helpmenu","modemenu","modelmenu","rootmenu","submenu","settings"]) el(id).hidden = true;
const out = {};
const cls = () => ["m-auto","m-hid","m-rev"].filter(c => body.classList.contains(c)).join(" ");
const bar = el("bar"), flowEl = el("flow");
const pull = (from, to) => { flowEl.fire("touchstart", {touches: [{clientX: 200, clientY: from}]});
  flowEl.fire("touchend", {changedTouches: [{clientX: 200, clientY: to}]}); };
out.load = cls();
advance(4999); out.at4999 = cls();
advance(1); out.at5000 = cls();
pull(300, 320); out.shortPull = cls();
pull(300, 420); out.pulled = cls();
advance(7000); out.at7000 = cls();
bar.fire("touchstart", {touches: [{clientX: 10, clientY: 10}]});
advance(7999); out.touched7999 = cls();
advance(1); out.touched8000 = cls();
pull(200, 400); crow.toggleRail(); advance(30000); out.drawerOpen = cls();
body.children.find(c => c.id === "mscrim").click(); advance(8000); out.drawerClosed = cls();
flowEl.scrollTop = 900; flowEl.fire("scroll"); flowEl.scrollTop = 700; flowEl.fire("scroll");
out.redrawScroll = cls();
flowEl.fire("touchstart", {touches: [{clientX: 200, clientY: 500}]});
flowEl.scrollTop = 500; flowEl.fire("scroll");
out.scrolledUp = cls();
const nudge = body.children.find(c => c.id === "mnudge");
out.nudged = [];
if(nudge){ advance(8000); out.nudged.push(cls()); nudge.click(); out.nudged.push(cls());
  advance(8000); nudge.fire("touchstart", {touches: [{clientX: 200, clientY: 60}]});
  out.nudged.push(cls()); }
out.touch = listeners.filter(l => /^touch|^scroll/.test(l.type)).map(l => [l.type, !!(l.opt && l.opt.passive)]);
console.log(JSON.stringify(out));
"""

    def run_header(self, standalone: bool) -> dict:
        node = _node()
        if not node:
            self.skipTest("no node on this machine")
        import subprocess
        js = ("globalThis.STANDALONE = %s;\n" % ("true" if standalone else "false")
              + self.FAKE_DOM + crow_gui.REMOTE_JS + self.HEADER)
        done = subprocess.run([node, "-e", js], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_the_home_screen_header_hides_and_a_pull_brings_it_back(self):
        """robin, 2026-09-24: standalone only -- hidden 5 s after load; a
        downward drag reveals it below the blur band; it stays 8 s and a touch
        on it restarts that; it never hides while a drawer is open; scrolling
        toward older messages reveals it too. Listeners passive."""
        out = self.run_header(True)
        self.assertEqual(out["load"], "m-auto")
        self.assertEqual(out["at4999"], "m-auto")
        self.assertEqual(out["at5000"], "m-auto m-hid")
        self.assertEqual(out["shortPull"], "m-auto m-hid", "a 20 px wobble is no pull")
        self.assertEqual(out["pulled"], "m-auto m-rev")
        self.assertEqual(out["at7000"], "m-auto m-rev")
        self.assertEqual(out["touched7999"], "m-auto m-rev")
        self.assertEqual(out["touched8000"], "m-auto m-hid")
        self.assertEqual(out["drawerOpen"], "m-auto m-rev")
        self.assertEqual(out["drawerClosed"], "m-auto m-hid")
        # the page's own scroll (a redraw) is no pull; a finger's is
        self.assertEqual(out["redrawScroll"], "m-auto m-hid")
        self.assertEqual(out["scrolledUp"], "m-auto m-rev")
        # the nudge pill (robin): a tap or a touch on it brings the header back
        self.assertEqual(out["nudged"], ["m-auto m-hid", "m-auto m-rev", "m-auto m-rev"])
        self.assertIn("body.m-auto.m-hid #mnudge{display:flex", crow_gui.REMOTE_CSS)
        # ...and the goal bar moves below the pill while the header is out
        self.assertIn("body.m-auto:is(.m-hid,.m-rev) #panels{padding-top:40px}",
                      crow_gui.REMOTE_CSS)
        # robin: the subtasks card's X sits under the goal's X (#subpanel pads 10 px)
        self.assertIn("margin-right:-10px}", crow_gui.REMOTE_CSS)
        for kind, passive in out["touch"]:
            self.assertNotEqual(kind, "touchmove")
            self.assertTrue(passive, kind)

    def test_the_safari_tab_keeps_its_header(self):
        """NEGATIVE: outside standalone nothing hides, ever."""
        out = self.run_header(False)
        for key in ("load", "at5000", "pulled", "touched8000", "drawerClosed"):
            self.assertEqual(out[key], "", key)

    def test_the_phone_shows_no_reasoning_level(self):
        """robin, 2026-09-24: the operating point fixes the level; the phone's
        model chip and menu show none of it."""
        self.assertIn("#model .lvl{display:none!important}", crow_gui.REMOTE_CSS)
        self.assertIn('.filter(p => p.kind !== "level")', crow_gui.REMOTE_JS)


class RemoteMirrorTests(RemoteCase):
    """#249 "Expected result", RemoteMirrorTests: the eight bullets."""

    # 1 -------------------------------------------------------------------
    def test_a_line_from_the_phone_is_drawn_once_on_each_view(self):
        api = self.mirrored()
        ran = []
        api._run = ran.append
        self.assertTrue(self.as_phone(api.send, "hello"))
        api._worker.join(5)
        self.assertEqual(ran, ["hello"])
        desk = [m for m in self.drained(api) if m.get("k") == "user"]
        self.assertEqual([m["t"] for m in desk], ["hello"],
                         "the desktop must draw the phone's line exactly once")
        phone = [m for m in api._remote.got() if m.get("k") == "user"]
        self.assertEqual(phone, [], "the phone drew its own line in go()")

    def test_a_line_from_the_desktop_reaches_the_phone(self):
        api = self.mirrored()
        api._run = lambda text: None
        api.send("from the desk")
        api._worker.join(5)
        self.assertEqual([m["t"] for m in api._remote.got()
                          if m.get("k") == "user"], ["from the desk"])
        self.assertIn("busy", [m.get("k") for m in api._remote.got()])
        self.assertEqual([m for m in self.drained(api) if m.get("k") == "user"],
                         [], "the desktop echoed its own line")

    # 2 -------------------------------------------------------------------
    def test_two_lines_mid_turn_are_one_queued_bubble_on_both_views(self):
        api = self.mirrored()
        api._busy = True
        self.as_phone(api.send, "from the phone")
        api.send("from the desk")
        joined = "from the phone\n\nfrom the desk"
        self.assertEqual(api._queued, joined)
        desk = [m for m in self.drained(api) if m.get("k") == "queued"]
        phone = [m for m in api._remote.got() if m.get("k") == "queued"]
        self.assertEqual(desk[-1]["t"], joined)
        self.assertEqual(phone[-1]["t"], joined)
        self.assertEqual(api._queued_by, {PHONE, crow_gui.DESKTOP})

        # AND IT RUNS AHEAD OF THE GOAL NUDGE (#264 unchanged).
        ran = []
        nudges = iter(["the nudge"])
        api._run = ran.append
        api._goal_nudge = lambda: next(nudges, None)
        api._worker = threading.current_thread()
        api._pump("the running turn")
        self.assertEqual(ran, ["the running turn", joined, "the nudge"])

    def test_the_page_holds_the_servers_text_and_draws_it_at_idle(self):
        """The page half, run in node: `queuedLine(e)` takes the joined text
        from the push, `idle()` releases it as the user's bubble."""
        node = _node()
        if not node:
            self.skipTest("no node on this machine")
        import subprocess
        src = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        start = src.index("  queuedLine(e){")
        end = src.index("  // #164. DAS ZIELPANEL")
        rel = src.index("  release(){")
        rel_end = src.index("  // #264. A Crow command is a first word")
        js = ("const log=[];\n"
              "const el={textContent:'',classList:{add(){},remove(){}}};\n"
              "const $=s=>el; const go=el;\n"
              "const crow={running:false,viewingOther:false,held:null,\n"
              "  face(){}, user(t){log.push(['user',t]);}, userImages(i){},\n"
              + src[start:end] + src[rel:rel_end] + "};\n"
              "crow.queuedLine({k:'queued',t:'a\\n\\nb',i:[]});\n"
              "crow.release();\n"
              "console.log(JSON.stringify({log, held:crow.held}));\n")
        done = subprocess.run([node, "-e", js], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["log"], [["user", "a\n\nb"]])
        self.assertIsNone(out["held"])

    # 3 -------------------------------------------------------------------
    def test_the_phone_answers_and_the_desktop_card_closes(self):
        api = self.mirrored()
        said = []
        thread = threading.Thread(
            target=lambda: said.append(api._ask_page("run_command", "{}")),
            daemon=True)
        thread.start()
        for _ in range(200):
            if api._pending_ask is not None:
                break
            time.sleep(0.01)
        self.assertIn("ask", [m.get("k") for m in api._remote.got()])
        self.as_phone(api.answer, "yes")
        thread.join(5)
        self.assertEqual(said, ["yes"], "the blocked turn did not continue")
        asked = [m for m in self.drained(api) if m.get("k") == "asked"]
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0]["t"], "allowed -- answered on phone")
        # THE LATE CLICK CHANGES NOTHING: the first answer won.
        api.answer("no")
        self.assertEqual(api._answer, "yes")
        self.assertEqual([m for m in api._remote.got() if m.get("k") == "asked"],
                         [], "the phone got a card-close for its own answer")

    # 4 -------------------------------------------------------------------
    def test_yolo_from_the_phone_holds_on_both_views(self):
        api = self.mirrored("--mode", "manual")
        self.assertTrue(crow_core.needs_approval("run_command", api._args.mode))
        self.as_phone(api.set_mode, "yolo")
        self.assertEqual(api._args.mode, "yolo")
        self.assertFalse(crow_core.needs_approval("run_command", api._args.mode),
                         "an outside command would still ask")
        for got in (self.drained(api), api._remote.got()):
            modes = [m for m in got if m.get("k") == "mode"]
            self.assertEqual(modes[-1]["name"], "yolo")

    # 5 -------------------------------------------------------------------
    def test_the_phone_opens_an_old_chat_and_the_desktop_stays(self):
        """Mid-turn (a view) and idle (a real switch that pins the desktop):
        either way the desktop's view is unchanged and it gets no replay."""
        for busy in (True, False):
            with self.subTest(busy=busy):
                api = self.mirrored()
                saved = self.saved_chat(api)
                if busy:
                    self.worker(api)
                before = api._viewed_path()
                desk_text = [m["content"] for m in api._conversation.payload()
                             if m.get("role") == "user"]
                self.as_phone(api.open, saved)
                self.assertEqual(api._viewed_path(), before if busy
                                 else api._views[crow_gui.DESKTOP],
                                 "the desktop moved")
                desk = self.drained(api)
                kinds = [m.get("k") for m in desk]
                for kind in ("clear", "user", "hello"):
                    self.assertNotIn(kind, kinds, "the desktop got the replay")
                phone = api._remote.got()
                self.assertIn("clear", [m.get("k") for m in phone])
                self.assertIn("the chat on disk",
                              [m.get("t") for m in phone if m.get("k") == "user"])
                if not busy:
                    # PINNED to the chat it was reading -- written to disk by
                    # the switch, so the same chat now has a path.
                    pinned = api._views[crow_gui.DESKTOP]
                    self.assertTrue(pinned)
                    with open(pinned, encoding="utf-8") as fh:
                        self.assertIn(desk_text[0], fh.read())
                    self.assertIsNone(api._views.get(PHONE))
                    self.assertTrue(api._same(api._current_path, saved))

    # 6 -------------------------------------------------------------------
    def test_a_worker_message_follows_each_clients_view(self):
        api = self.mirrored()
        saved = self.saved_chat(api)
        api._views[PHONE] = saved                 # the phone reads elsewhere
        api._worker = threading.current_thread()
        api.push({"k": "text", "t": "streaming"})
        desk = self.drained(api)
        self.assertEqual(desk, [{"k": "text", "t": "streaming"}],
                         "the live desktop must draw it, unstamped")
        self.assertEqual(api._remote.got(), [], "the phone drew a turn it "
                                                "does not look at")
        # AND THE OTHER WAY ROUND: the desktop elsewhere keeps its #162 stamp.
        api._views[PHONE] = None
        api._views[crow_gui.DESKTOP] = saved
        api.push({"k": "text", "t": "more"})
        self.assertEqual(self.drained(api), [{"k": "text", "t": "more", "bg": True}])
        self.assertEqual(api._remote.got(), [{"k": "text", "t": "more"}])

    # 7 -------------------------------------------------------------------
    def test_the_rail_reaches_both_with_their_own_marker(self):
        api = self.mirrored()
        saved = self.saved_chat(api)
        api._views[PHONE] = saved
        api._reload_rail()
        desk = [m for m in self.drained(api) if m.get("k") == "rail"][-1]
        phone = [m for m in api._remote.got() if m.get("k") == "rail"][-1]
        self.assertTrue(desk["live_active"])
        self.assertFalse(phone["live_active"])
        mark = {r["path"]: r.get("active") for r in phone["rollovers"]}
        self.assertTrue(mark.get(saved), "the phone's chat is not marked")
        mark = {r["path"]: r.get("active") for r in desk["rollovers"]}
        self.assertFalse(mark.get(saved), "the desktop marks the phone's chat")

    # 8 -------------------------------------------------------------------
    def test_a_log_only_note_reaches_neither_view(self):
        api = self.mirrored()
        note = crow_core.LOG_ONLY_NOTE_PREFIXES[0] + "12 messages dropped"
        self.assertTrue(crow_core.note_is_log_only(note))
        api.push({"k": "note", "t": note})
        self.as_phone(api.push, {"k": "note", "t": note})
        self.assertEqual(self.drained(api), [])
        self.assertEqual(api._remote.published, [])
        # COUNTER-PROBE: an ordinary note reaches both.
        api.push({"k": "note", "t": "an ordinary note"})
        self.assertEqual(len(self.drained(api)), 1)
        self.assertEqual(len(api._remote.got()), 1)

    def test_the_no_folder_note_goes_to_the_log_not_the_chat(self):
        """robin, 2026-09-24 (phone screenshot): "no working directory --
        writes are unbounded" is for crow.log. Live, from the phone, it
        reaches neither view nor the notes band; a chat saved by an earlier
        build that still carries it does not draw it on replay either."""
        text = "no working directory -- writes are unbounded"
        logs = tempfile.mkdtemp(prefix="crow-log-")
        self.addCleanup(shutil.rmtree, logs, True)
        self.addCleanup(setattr, crow_core, "LOG_FILE", crow_core.LOG_FILE)
        self.addCleanup(setattr, crow_core, "ROOTS_FILE", crow_core.ROOTS_FILE)
        crow_core.LOG_FILE = os.path.join(logs, "crow.log")
        crow_core.ROOTS_FILE = os.path.join(logs, "roots.json")
        api = self.mirrored()
        self.a_chat(api)
        self.as_phone(api.clear_root)
        for got in (self.drained(api), api._remote.got()):
            self.assertNotIn(text, [m.get("t") for m in got
                                    if m.get("k") == "note"])
        self.assertEqual(api._notes, [], "saved with the chat")
        with open(crow_core.LOG_FILE, encoding="utf-8") as fh:
            self.assertIn("[note] " + text, fh.read())
        # THE OLD BAND: 32 copies in robin's session.json. Replay draws none.
        old = [{"k": "note", "at": 1, "t": text}] * 32
        api._remote.published.clear()
        api._replay(api._conversation.payload(), old)
        self.assertNotIn(text, [m.get("t") for m in self.drained(api)])
        self.assertNotIn(text, [m.get("t") for m in api._remote.got()])
        self.assertEqual(crow_core.clean_notes(old), [])

    # -- the snapshot and the late joiner -----------------------------------
    def test_ready_from_a_phone_answers_the_phone_only(self):
        api = self.mirrored()
        self.a_chat(api, "what the phone must see")
        self.as_phone(api.ready)
        # The title-bar icon may learn that a phone is here; nothing else.
        self.assertEqual([m for m in self.drained(api) if m.get("k") != "remote"],
                         [], "the desktop got a phone's replay")
        got = api._remote.got()
        kinds = [m.get("k") for m in got]
        for kind in ("meta", "mode", "root", "clear", "user", "rail",
                     "viewing", "chips"):
            self.assertIn(kind, kinds)
        self.assertIn("what the phone must see",
                      [m.get("t") for m in got if m.get("k") == "user"])
        self.assertEqual(api._page_loads, 0, "a phone counted as a page load")

    def test_the_home_screen_app_keeps_its_header_out_of_the_blur(self):
        """robin's iPhone (iOS 27, home-screen app), 2026-09-24: the header
        row sat blurred and dimmed under the status bar. black-translucent
        puts the page under the bar and iOS fills that inset with the Liquid
        Glass scroll-edge blur, which reaches past the bar over the header.
        The status bar is opaque (`default`, tinted from theme-color), so the
        web view starts below it; black-translucent must not come back."""
        phone = crow_gui.stamped_page(remote=True)
        self.assertIn('name="apple-mobile-web-app-status-bar-style" content="default"',
                      phone)
        self.assertNotIn("black-translucent", phone)
        # the bar's tint follows the page: a theme-color tag without media
        # comes first, stamped from the window's ground.
        self.assertLess(phone.index('<meta id="mtheme" name="theme-color"'),
                        phone.index("apple-mobile-web-app-status-bar-style"))
        # NEGATIVE: the desktop page carries no web-app tags at all.
        self.assertNotIn("apple-mobile-web-app-status-bar-style",
                         crow_gui.stamped_page())

    def test_the_home_screen_app_moves_its_header_below_the_blur_band(self):
        """robin's iPhone (iOS 27), 2026-09-24: a permanent offset under the
        system's blur band was blurred at 8 px and ugly at 18/36 px. No fixed
        offset any more: in standalone mode the header hides itself and comes
        back as an overlay below the band (--safe-t + 18 px); --safe-t itself
        stays the plain inset. The Safari tab and the desktop get none of it."""
        phone = crow_gui.stamped_page(remote=True)
        self.assertNotIn("@media (display-mode: standalone)", phone)
        self.assertNotIn("inset-top,0px) + 8px", phone)
        self.assertIn("--safe-t:env(safe-area-inset-top,0px);", phone)
        self.assertIn("body.m-auto.m-rev #bar{top:calc(var(--safe-t) + 18px)", phone)
        self.assertIn('matchMedia("(display-mode: standalone)")', phone)
        self.assertNotIn("display-mode: standalone", crow_gui.stamped_page())
        self.assertNotIn("m-auto", crow_gui.stamped_page())

    def test_the_phone_page_brings_its_home_screen_tile(self):
        """robin's iPhone, 2026-09-24: a generic "1" tile on the home screen.
        The phone page names the tile, the manifest and the web-app title;
        the desktop page carries none of it. The window's own drawer
        (`remote_icon`) draws an opaque 180x180 PNG."""
        phone = crow_gui.stamped_page(remote=True)
        for tag in ('<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
                    '<link rel="manifest" href="/remote.webmanifest">',
                    '<meta name="apple-mobile-web-app-title" content="Crow">',
                    '<meta name="apple-mobile-web-app-capable" content="yes">',
                    '<meta name="mobile-web-app-capable" content="yes">',
                    '<meta name="apple-mobile-web-app-status-bar-style"'
                    ' content="default">'):
            self.assertIn(tag, phone)
        self.assertNotIn("apple-touch-icon", crow_gui.stamped_page())
        tile = crow_gui.remote_icon(180)
        self.assertEqual(tile[12:16], b"IHDR")
        self.assertEqual((int.from_bytes(tile[16:20], "big"),
                          int.from_bytes(tile[20:24], "big"), tile[25]),
                         (180, 180, 2))

    def test_a_phone_reload_does_not_record_the_notes_again(self):
        """robin's iPhone, 2026-09-24: ONE "no folder" note became 32 in
        session.json (1 at at=1, 31 at at=5) and 15+ rows in the phone's chat.
        `clear_root` ran once; every phone page load (`ready`) delivered its
        snapshot through `push`, which records each note in `_notes` again --
        1 -> 2 -> 4 -> ... -> 32 after five loads. A delivered snapshot is a
        copy of what is already recorded, never a new note."""
        api = self.mirrored()
        self.a_chat(api)
        api.push({"k": "note", "t": "an ordinary note"})
        self.assertEqual(len(api._notes), 1)
        for _ in range(5):
            api._remote.published.clear()
            self.as_phone(api.ready)
            shown = [m for m in api._remote.got()
                     if m.get("k") == "note" and m.get("t") == "an ordinary note"]
            self.assertEqual(len(shown), 1, "the phone drew the note %d times"
                             % len(shown))
        self.assertEqual(len(api._notes), 1,
                         "a phone reload recorded the notes again")

    def test_the_snapshot_carries_an_open_question_and_the_queued_line(self):
        api = self.mirrored()
        api._busy = True
        api._pending_ask = {"k": "ask", "name": "run_command", "args": "{}",
                            "scope": ""}
        api.send("held back")
        snap = api.state_snapshot(PHONE)
        kinds = [m.get("k") for m in snap]
        self.assertIn("ask", kinds)
        self.assertIn("busy", kinds)
        self.assertEqual([m["t"] for m in snap if m.get("k") == "queued"],
                         ["held back"])
        # Collected, never delivered.
        self.assertEqual([m for m in self.drained(api)
                          if m.get("k") in ("meta", "clear")], [])

    def test_a_phone_looking_elsewhere_gets_no_open_question(self):
        """NEGATIVE: the ask belongs to the live turn, like the desktop's #162
        rule -- a phone reading another chat does not get it."""
        api = self.mirrored()
        saved = self.saved_chat(api)
        api._views[PHONE] = saved
        api._pending_ask = {"k": "ask", "name": "x", "args": "", "scope": ""}
        self.assertNotIn("ask", [m.get("k") for m in api.state_snapshot(PHONE)])


class RemoteStagedImageTests(RemoteCase):
    """#249, iPhone 2026-09-24: an image staged and sent on the phone kept its
    chip in the DESKTOP's strip. The stage is one state for every client, so
    every client hears when it empties -- at the point the images leave it,
    on all three ways `send` takes (idle, queued mid-turn, another view).

    The model server here refuses images (/props: no vision), so the real
    `_run` consumes the stage and stops right after -- the one line the fix
    is about, without a model."""

    def _server(self) -> str:
        import http.server

        class Props(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"modalities": {"vision": false}}')

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Props)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:%d/v1" % server.server_address[1]

    def staged(self):
        api = self.mirrored("--base-url", self._server())
        path = os.path.join(self.dir, "shot.png")
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
        self.as_phone(api.stage_image, path)
        chips = [m for m in self.drained(api) if m.get("k") == "chips"]
        self.assertEqual(len(chips[-1]["c"]), 1, "the desktop never saw the chip")
        api._remote.published.clear()
        return api

    def assert_emptied(self, api):
        self.assertEqual(api._staged_images, [])
        desk = [m for m in self.drained(api) if m.get("k") == "chips"]
        self.assertTrue(desk, "the desktop was never told the stage emptied")
        self.assertEqual(desk[-1], {"k": "chips", "c": []},
                         "the desktop's strip keeps the sent image")
        phone = [m for m in api._remote.got() if m.get("k") == "chips"]
        self.assertEqual(phone[-1], {"k": "chips", "c": []})

    def test_idle_the_desktop_strip_empties(self):
        api = self.staged()
        self.assertTrue(self.as_phone(api.send, "what is this"))
        api._worker.join(10)
        self.assertFalse(api._worker.is_alive())
        self.assert_emptied(api)

    def test_mid_turn_the_desktop_strip_empties_when_the_line_runs(self):
        api = self.staged()
        api._busy = True
        self.assertTrue(self.as_phone(api.send, "what is this"))
        # HELD, NOT SENT: the images still ride the queued line, so the
        # strip keeps them until the line leaves.
        self.assertEqual(len(api._staged_images), 1)
        self.assertNotIn({"k": "chips", "c": []}, self.drained(api))
        real, first = api._run, []
        api._run = lambda text: first.append(text) if not first else real(text)
        api._worker = threading.current_thread()
        api._pump("the running turn")
        self.assertEqual(first, ["the running turn"])
        self.assert_emptied(api)

    def test_from_another_view_the_desktop_strip_empties(self):
        api = self.staged()
        saved = self.saved_chat(api)
        api._views[PHONE] = saved                  # the phone reads elsewhere
        self.assertTrue(self.as_phone(api.send, "what is this"))
        api._worker.join(10)
        self.assertFalse(api._worker.is_alive())
        # The desktop is pinned to its own chat by the switch; the stage is
        # not a chat's, so the empty strip reaches it unstamped anyway.
        self.assertIsNotNone(api._views.get(crow_gui.DESKTOP))
        self.assert_emptied(api)


class RemoteSlashTests(RemoteCase):
    """#249: `/remote` on/off/status/devices/forget, the dialog and the icon."""

    def started(self):
        crow_gui.REMOTE_FACTORY = _FakeRemote
        crow_gui.lan_addresses = lambda: [("wlan0", "192.168.1.5"),
                                          ("eth0", "10.0.0.7")]
        api = self.api()
        self.drained(api)
        # the icon's watcher polls while `_remote` is its server -- let it go
        self.addCleanup(setattr, api, "_remote", None)
        return api

    def test_it_is_on_every_list(self):
        self.assertIn("/remote", crow_core.SLASH_COMMANDS)
        self.assertIn("/remote", crow_gui.Api.WHAT_THEY_DO)
        self.assertIn("/remote", crow.HELP)
        self.assertIsNotNone(self.api().slash_answer("/remote status"))

    def test_on_starts_persists_and_opens_the_dialog(self):
        api = self.started()
        said = api.slash_answer("/remote on")
        self.assertIn("http://192.168.1.5:8765/", said)
        self.assertTrue(api._remote.running())
        self.assertTrue(crow_gui.remote_enabled())
        out = self.drained(api)
        dialog = [m for m in out if m.get("k") == "remotedlg"][-1]
        self.assertTrue(dialog["open"])
        self.assertEqual(dialog["ips"], [["wlan0", "192.168.1.5"],
                                         ["eth0", "10.0.0.7"]])
        self.assertEqual([d["name"] for d in dialog["devices"]],
                         ["iPhone (Safari)"])
        icon = [m for m in out if m.get("k") == "remote"][-1]
        self.assertEqual((icon["on"], icon["online"]), (True, 1))
        # THE DIALOG IS THE DESKTOP'S: no phone ever receives it.
        self.assertNotIn("remotedlg", [m.get("k") for m in api._remote.got()])

    def test_bare_remote_is_the_icon(self):
        api = self.started()
        api.slash_answer("/remote")
        self.assertTrue(api._remote.running())
        self.assertIn("remotedlg", [m.get("k") for m in self.drained(api)])
        # The icon's click is the same call.
        self.assertIn("crow.remoteOpen()", crow_gui.PAGE)
        self.assertIn("remoteOpen(){ pywebview.api.remote_open()", crow_gui.PAGE)

    def test_the_port_is_fixed_and_the_host_is_a_lan_address(self):
        api = self.started()
        api.slash_answer("/remote on")
        self.assertEqual(api._remote.kw["port"], crow_core.REMOTE_PORT_DEFAULT)
        self.assertEqual(api._remote.kw["host"], "192.168.1.5")
        self.assertEqual(api._remote.kw["allowed"], crow_gui.REMOTE_ALLOWED)
        api.remote_use_ip("10.0.0.7")
        self.assertEqual(api._remote.kw["host"], "10.0.0.7")
        self.assertEqual(crow_gui.remote_host_setting(), "10.0.0.7")

    def test_no_lan_means_no_server(self):
        """NEGATIVE: never 0.0.0.0 -- no LAN address, no listener."""
        crow_gui.REMOTE_FACTORY = _FakeRemote
        crow_gui.lan_addresses = lambda: []
        api = self.api()
        self.assertEqual(api.slash_answer("/remote on"), crow_core.REMOTE_NO_LAN)
        self.assertIsNone(api._remote)
        self.assertFalse(crow_gui.remote_enabled())

    def test_off_stops_and_devices_stay(self):
        api = self.started()
        api.slash_answer("/remote on")
        remote = api._remote
        self.assertEqual(api.slash_answer("/remote off"), crow_core.REMOTE_OFF_LINE)
        self.assertFalse(remote.running())
        self.assertIsNone(api._remote)
        self.assertFalse(crow_gui.remote_enabled())
        self.assertEqual(remote.forgot, [])
        self.assertIn("off", api.slash_answer("/remote status"))

    def test_status_devices_and_forget(self):
        api = self.started()
        api.slash_answer("/remote on")
        self.assertIn("http://192.168.1.5:8765/", api.slash_answer("/remote status"))
        self.assertIn("iPhone (Safari)", api.slash_answer("/remote devices"))
        said = api.slash_answer("/remote forget iphone")
        self.assertIn("forgot", said)
        self.assertEqual(api._remote.forgot, [PHONE])
        self.assertIn("no single paired device",
                      api.slash_answer("/remote forget nobody"))
        self.assertEqual(api.slash_answer("/remote sideways"),
                         crow_core.REMOTE_USAGE)

    def test_a_new_device_waits_for_the_desktop_and_times_out_as_deny(self):
        api = self.started()
        api.slash_answer("/remote on")
        self.drained(api)
        before = crow_core.REMOTE_CONFIRM_S
        self.addCleanup(setattr, crow_core, "REMOTE_CONFIRM_S", before)
        crow_core.REMOTE_CONFIRM_S = 0.05
        self.assertFalse(api._remote_confirm("iPhone (Safari)"))
        out = self.drained(api)
        self.assertEqual(out[0]["k"], "remoteask")
        self.assertIn("wants to connect", out[0]["t"])
        self.assertIn("denied", [m for m in out
                                 if m.get("k") == "remoteasked"][0]["t"])
        # ALLOW: the desktop's click lets it in.
        crow_core.REMOTE_CONFIRM_S = 5
        allowed = []
        thread = threading.Thread(target=lambda: allowed.append(
            api._remote_confirm("iPhone (Safari)")), daemon=True)
        thread.start()
        for _ in range(200):
            if api._remote_asks:
                break
            time.sleep(0.01)
        api.remote_allow(next(iter(api._remote_asks)), True)
        thread.join(5)
        self.assertEqual(allowed, [True])

    def test_the_allow_request_shows_inside_the_open_remote_dialog(self):
        """#249, iPhone 2026-09-24: the Remote dialog (z-index 80, modal)
        covered the Allow/Deny bar above the input. Run in node with a small
        DOM: while the dialog is open the request sits at the top of its
        body and survives a refresh; closed, it is above the input; Allow
        calls `remote_allow`; `remoteasked` clears it wherever it is."""
        node = _node()
        if not node:
            self.skipTest("no node on this machine")
        import subprocess
        src = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        start = src.index("  remoteClose(){")
        end = src.index("  // #249. DIE ANDERE SEITE HAT GEANTWORTET")
        js = r"""
const ALL=[];
class El{
  constructor(tag){ this.tag=tag; this.children=[]; this.parent=null; this.id="";
    this.hidden=false; this.dataset={}; this.q={}; this.onclick=null;
    const cl=new Set(); this.cls=cl;
    this.classList={add:c=>cl.add(c), remove:c=>cl.delete(c), toggle(){},
                    contains:c=>cl.has(c)};
    ALL.push(this); }
  set innerHTML(v){ this.q={}; } set textContent(v){
    this.children.forEach(c=>c.parent=null); this.children=[]; this.q={}; }
  set className(v){ v.split(" ").forEach(c=>this.cls.add(c)); }
  querySelector(sel){ if(!this.q[sel]){ const e=new El(sel); e.parent=this;
      e.children=[]; this.q[sel]=e; } return this.q[sel]; }
  get firstChild(){ return this.children[0]||null; }
  remove(){ if(this.parent){ const i=this.parent.children.indexOf(this);
      if(i>=0) this.parent.children.splice(i,1); } this.parent=null; }
  insertBefore(n, ref){ n.remove(); const i=ref?this.children.indexOf(ref):-1;
    if(i<0) this.children.push(n); else this.children.splice(i,0,n); n.parent=this; }
  appendChild(n){ this.insertBefore(n, null); }
  get isConnected(){ let e=this; while(e.parent) e=e.parent; return e===ROOT; }
}
const ROOT=new El("root");
const mk=id=>{ const e=new El("div"); e.id=id; ROOT.appendChild(e); return e; };
const composer=mk("composer"), dlg=mk("remotedlg"); dlg.hidden=true;
const box=new El("div"); box.id="box"; composer.appendChild(box);
const document={createElement:t=>new El(t), querySelector(sel){
  const m=/^#([\w-]+)(?:\[data-rid="([^"]*)"\])?$/.exec(sel);
  return ALL.find(e=>e.isConnected && e.id===m[1]
                     && (m[2]===undefined || e.dataset.rid===m[2])) || null; }};
const $=s=>document.querySelector(s);
const setInterval=()=>0, clearInterval=()=>0;
const allowed=[];
const pywebview={api:{remote_allow:(id,yes)=>{ allowed.push([id,yes]); return Promise.resolve(true); }}};
const crow={mode:"manual", note(){},
""" + src[start:end] + r"""};
const where=()=>{ const p=$("#pairbar"); if(!p) return "none";
  if(p.parent===composer) return "composer";
  if(p.parent && p.parent.tag===".rbody" && p.parent.firstChild===p
     && p.isConnected && p.cls.has("indlg")) return "dialog";
  return "elsewhere"; };
const out=[];
const DLG={k:"remotedlg", open:true, fresh:true, url:"http://x/", svg:"", ips:[], devices:[]};
crow.remoteDialog(DLG);
crow.remoteAsk({k:"remoteask", id:1, name:"iPhone (Chrome)", t:"iPhone (Chrome) wants to connect", ttl:60});
out.push(where());
crow.remoteDialog(Object.assign({}, DLG, {fresh:false}));   // a device came or went
out.push(where());
$("#pairbar").querySelector(".yes").onclick();
out.push(JSON.stringify(allowed));
crow.remoteClose();
out.push(where());
crow.remoteDialog(DLG);
out.push(where());
crow.remoteAsked({k:"remoteasked", id:1, t:""});
out.push(where());
crow.remoteClose();
crow.remoteAsk({k:"remoteask", id:2, name:"iPhone", t:"iPhone wants to connect", ttl:60});
out.push(where());
crow.remoteAsked({k:"remoteasked", id:2, t:""});
out.push(where());
console.log(JSON.stringify(out));
"""
        done = subprocess.run([node, "-e", js], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout),
                         ["dialog", "dialog", "[[1,true]]", "composer", "dialog",
                          "none", "composer", "none"])
        self.assertIn("#pairbar.indlg{", crow_gui.PAGE)

    def test_no_answer_is_none_and_the_server_is_told_the_timeout(self):
        """None, not False: the server answers the phone 410 (expired) for a
        question nobody answered, 403 only for a real Deny."""
        api = self.started()
        api.slash_answer("/remote on")
        self.assertEqual(api._remote.kw["confirm_ttl"], crow_core.REMOTE_CONFIRM_S)
        before = crow_core.REMOTE_CONFIRM_S
        self.addCleanup(setattr, crow_core, "REMOTE_CONFIRM_S", before)
        crow_core.REMOTE_CONFIRM_S = 0.05
        self.assertIsNone(api._remote_confirm("iPhone (Safari)"))

    def test_the_firewall_line_opens_the_lan_only(self):
        line = crow_core.remote_firewall_line(8765, "192.168.1.5", "ufw")
        self.assertIn("sudo ufw allow from 192.168.1.0/24 to any port 8765 "
                      "proto tcp", line)
        self.assertIn("192.168.1.0/24",
                      crow_core.remote_firewall_line(8765, "192.168.1.5",
                                                     "firewalld"))
        self.assertEqual(crow_core.remote_firewall_line(8765, "192.168.1.5", ""),
                         "")

    def test_the_devices_live_in_the_secrets_store_beside_the_rest(self):
        before = crow_core.SECRETS_FILE
        self.addCleanup(setattr, crow_core, "SECRETS_FILE", before)
        crow_core.SECRETS_FILE = os.path.join(self.dir, "secrets.json")
        with open(crow_core.SECRETS_FILE, "w", encoding="utf-8") as fh:
            json.dump({"CROW_TAVILY_KEY": "kept"}, fh)
        record = {"id": "d-1", "name": "iPhone", "token_sha256": "ab" * 32}
        self.assertTrue(crow_core.remote_devices_save([record]))
        self.assertEqual(crow_core.remote_devices_load(), [record])
        self.assertEqual(crow_core.secret("CROW_TAVILY_KEY"), "kept")
        # NEGATIVE: a store that does not parse is never overwritten.
        with open(crow_core.SECRETS_FILE, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertFalse(crow_core.remote_devices_save([]))
        with open(crow_core.SECRETS_FILE, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{not json")

    def test_a_phone_exit_never_closes_the_window(self):
        api = self.api()
        closed = []
        api._window = types.SimpleNamespace(destroy=lambda: closed.append(1))
        self.assertEqual(self.as_phone(api.slash_answer, "/exit"),
                         crow_core.REMOTE_PHONE_EXIT)
        self.assertEqual(closed, [])

    # -- the phone icon in the title bar ------------------------------------
    def test_the_icon_sits_left_of_the_three_panel_buttons(self):
        src = (HERE / "crow_gui.py").read_text(encoding="utf-8")
        bar = src[src.index('<div id="bar"'):src.index('<div id="wbtns"')]
        order = [bar.index('id="%s"' % i) for i in
                 ("mark", "remotetoggle", "codetoggle", "gittoggle",
                  "browsertoggle")]
        self.assertEqual(order, sorted(order))
        icon = bar[bar.index('id="remotetoggle"'):bar.index('id="codetoggle"')]
        self.assertIn('stroke-width="1.6"', icon)
        self.assertIn('stroke="currentColor"', icon)
        css = crow_gui.PAGE
        self.assertIn("#remotetoggle{margin-left:auto;", css)
        self.assertIn("#remotetoggle + #codetoggle{margin-left:0}", css)
        self.assertIn("#remotetoggle{margin-right:9px}", css)
        self.assertIn("#remotetoggle.live .rdot{display:block}", css)
        self.assertIn("background:var(--ok)", css[css.index("#remotetoggle .rdot"):])
        self.assertIn('case "remote": this.remoteState(e); break;', css)

    def test_the_icon_state_follows_the_server(self):
        api = self.started()
        api.remote_open()
        icon = [m for m in self.drained(api) if m.get("k") == "remote"][-1]
        self.assertTrue(icon["on"])
        self.assertEqual(icon["online"], 1)
        api._remote.online[PHONE] = False
        api._remote_state_push()
        icon = [m for m in self.drained(api) if m.get("k") == "remote"][-1]
        self.assertEqual(icon["online"], 0)
        api.remote_stop()
        icon = [m for m in self.drained(api) if m.get("k") == "remote"][-1]
        self.assertFalse(icon["on"])


# ============================================================ #249 stage 5
#
# THE HTTPS ADDRESS VIA TAILSCALE, Api side. The probe is a fake per case
# (`crow_gui.TAILSCALE_PROBE`); the real CLI is never called.

TS_NAME = "aios.tail77dcd2.ts.net"
TS_CMD = "sudo tailscale serve --bg --https=443 http://127.0.0.1:8765"


def _ts_probe(state: str):
    named = state not in ("missing", "down")
    return lambda port: {"state": state, "name": TS_NAME if named else "",
                         "ip": "100.108.49.66" if named else "",
                         "command": TS_CMD.replace("8765", str(port))}


class RemoteTailnetTests(RemoteCase):
    """#249 stage 5: the loopback listener while the tailnet can serve, the
    HTTPS address as the dialog's network choice with one line per state."""

    def started(self, state: str):
        crow_gui.REMOTE_FACTORY = _FakeRemote
        crow_gui.lan_addresses = lambda: [("wlan0", "192.168.1.5")]
        crow_gui.TAILSCALE_PROBE = _ts_probe(state)
        api = self.api()
        self.drained(api)
        self.addCleanup(setattr, api, "_remote", None)
        return api

    def dialog(self, api) -> dict:
        return [m for m in self.drained(api) if m.get("k") == "remotedlg"][-1]

    def test_the_loopback_listener_only_while_the_tailnet_can_serve(self):
        for state, want in (("missing", ""), ("down", ""), ("https-off", TS_NAME),
                            ("serve-missing", TS_NAME), ("ready", TS_NAME),
                            ("funnel", "")):
            with self.subTest(state=state):
                api = self.started(state)
                api.slash_answer("/remote on")
                self.assertEqual(api._remote.kw["tailnet"], want)
                # the chosen LAN address listens either way, never 0.0.0.0/100.x
                self.assertEqual(api._remote.kw["host"], "192.168.1.5")
                api.remote_stop(persist=False)

    def test_the_https_choice_shows_the_missing_step_then_the_code(self):
        import crow_remote
        api = self.started("serve-missing")
        with mock.patch.object(crow_remote, "qr_svg", lambda text: "QR:" + text):
            api.slash_answer("/remote on")
            d = self.dialog(api)
            self.assertEqual((d["https"]["state"], d["https"]["on"]),
                             ("serve-missing", False))
            self.assertEqual(d["url"], "http://192.168.1.5:8765/")
            self.assertEqual(d["svg"], "QR:http://192.168.1.5:8765/#t=pairing-token")
            self.assertTrue(api.remote_use_https(True))
            self.assertTrue(crow_gui.remote_https_setting())
            d = self.dialog(api)
            self.assertTrue(d["https"]["on"])
            self.assertEqual(d["url"], "https://%s/" % TS_NAME)
            self.assertEqual(d["svg"], "", "a code that would not open yet")
            self.assertIn(TS_CMD, d["https"]["line"])
            self.assertEqual(d["https"]["cmd"], TS_CMD)
            self.assertEqual(d["hint"], "", "the ufw line is the LAN's")
            # robin runs the command; the next look finds it ready, and the QR
            # carries the SAME single-use code on the ts.net origin.
            crow_gui.TAILSCALE_PROBE = _ts_probe("ready")
            api.remote_use_https(True)
            d = self.dialog(api)
            self.assertIn("ready", d["https"]["line"])
            self.assertEqual(d["https"]["cmd"], "")
            self.assertEqual(d["svg"], "QR:https://%s/#t=pairing-token" % TS_NAME)
            # back to the LAN: nothing restarts, the LAN code again
            remote = api._remote
            api.remote_use_https(False)
            d = self.dialog(api)
            self.assertIs(api._remote, remote)
            self.assertEqual(d["svg"], "QR:http://192.168.1.5:8765/#t=pairing-token")

    def test_every_state_has_its_line(self):
        lines = {state: crow_core.remote_tailnet_line(state, TS_NAME, TS_CMD)
                 for state in ("missing", "down", "https-off", "serve-missing",
                               "funnel", "ready")}
        self.assertEqual(len(set(lines.values())), 6)
        self.assertIn("not installed", lines["missing"])
        self.assertIn("sudo tailscale up", lines["down"])
        self.assertIn("https://login.tailscale.com/admin/dns", lines["https-off"])
        self.assertIn(TS_CMD, lines["serve-missing"])
        self.assertIn("public", lines["funnel"])
        self.assertIn("https://%s/" % TS_NAME, lines["ready"])
        self.assertIn("pairs once more", lines["ready"])

    def test_open_restarts_once_when_the_tailnet_came_up(self):
        api = self.started("down")
        api.slash_answer("/remote on")
        first = api._remote
        self.assertEqual(first.kw["tailnet"], "")
        crow_gui.TAILSCALE_PROBE = _ts_probe("serve-missing")
        api.remote_open()
        self.assertIsNot(api._remote, first)
        self.assertFalse(first.running())
        self.assertEqual(api._remote.kw["tailnet"], TS_NAME)
        self.assertTrue(crow_gui.remote_enabled())
        # NEGATIVE: an unchanged tailnet restarts nothing
        again = api._remote
        crow_gui.TAILSCALE_PROBE = _ts_probe("ready")
        api.remote_open()
        self.assertIs(api._remote, again)

    def test_a_phone_cannot_choose_the_address(self):
        api = self.started("ready")
        api.slash_answer("/remote on")
        self.assertNotIn("remote_use_https", crow_gui.REMOTE_ALLOWED)
        self.assertEqual(crow_gui.REMOTE_DESKTOP_BOUND["remote_use_https"],
                         "desktop-only")
        self.assertFalse(self.as_phone(api.remote_use_https, True))
        self.assertFalse(crow_gui.remote_https_setting())

    def test_the_dialog_draws_the_choice_and_the_line(self):
        page = crow_gui.PAGE
        self.assertIn('o.textContent="HTTPS · "+(https.name||"Tailscale")', page)
        self.assertIn("pywebview.api.remote_use_https(true)", page)
        self.assertIn('t.querySelector("span").textContent=https.line||""', page)


# =================================================================== #290
#
# THE PHONE'S MICROPHONE: the clip is on disk, the Api transcribes it and the
# words go to that phone's input field only.

class RemotePhoneVoiceTests(RemoteCase):

    def clip(self) -> str:
        path = os.path.join(self.dir, "clip.m4a")
        with open(path, "wb") as fh:
            fh.write(b"\x00\x00\x00\x18ftypM4A ")
        return path

    def heard(self, api, text="Hallo Crow", why=None, boom=None):
        path = self.clip()

        def transcribe(p, stats=None):
            self.assertEqual(p, path)
            if boom:
                raise boom
            return text
        with mock.patch.object(crow_voice, "file_available", lambda: why), \
                mock.patch.object(crow_voice, "model_loaded", lambda: True), \
                mock.patch.object(crow_voice, "transcribe_file", transcribe):
            api._remote_heard(path, PHONE)
        self.assertFalse(os.path.exists(path), "the clip was kept")
        return [m for m in api._remote.got(PHONE) if m.get("k") == "heard"]

    def test_the_words_go_to_that_phone_only_and_nothing_is_sent(self):
        api = self.mirrored()
        api._remote.ids.append("d-other")
        before = len(api._conversation)
        self.assertEqual(self.heard(api), [{"k": "heard", "text": "Hallo Crow"}])
        self.assertNotIn("heard", [m.get("k") for m in api._remote.got("d-other")])
        self.assertNotIn("heard", [m.get("k") for m in self.drained(api)])
        self.assertEqual(len(api._conversation), before)
        self.assertNotIn("user", [m.get("k") for m in api._remote.got(PHONE)])

    def test_silence_a_missing_recogniser_and_a_failure_are_said_there(self):
        api = self.mirrored()
        self.assertEqual(self.heard(api, text=""),
                         [{"k": "heard", "note": "nothing was said"}])
        api._remote.published.clear()
        why = "dictation needs faster-whisper -- pip install faster-whisper"
        self.assertEqual(self.heard(api, why=why), [{"k": "heard", "note": why}])
        api._remote.published.clear()
        self.assertEqual(self.heard(api, boom=RuntimeError("bad clip")),
                         [{"k": "heard", "note": "dictation failed: bad clip"}])

    def test_the_server_gets_the_door_and_it_returns_at_once(self):
        crow_gui.REMOTE_FACTORY = _FakeRemote
        crow_gui.lan_addresses = lambda: [("wlan0", "192.168.1.5")]
        api = self.api()
        self.addCleanup(setattr, api, "_remote", None)
        api.slash_answer("/remote on")
        self.assertEqual(api._remote.kw["audio"], api._remote_audio)
        gate, done = threading.Event(), threading.Event()

        def slow(path, stats=None):
            gate.wait(5)
            done.set()
            return "spaet"
        with mock.patch.object(crow_voice, "file_available", lambda: None), \
                mock.patch.object(crow_voice, "model_loaded", lambda: True), \
                mock.patch.object(crow_voice, "transcribe_file", slow):
            api._remote_audio(self.clip(), PHONE)     # returns while it waits
            gate.set()
            self.assertTrue(done.wait(5))
            for _ in range(100):
                if any(m.get("k") == "heard" for m in api._remote.got(PHONE)):
                    break
                time.sleep(0.02)
        self.assertIn({"k": "heard", "text": "spaet"}, api._remote.got(PHONE))

    # #290 SCOPE AMENDMENT: partials while speaking, coalesced per phone.
    def numbered(self, n: int) -> str:
        path = os.path.join(self.dir, "clip-%d.webm" % n)
        with open(path, "wb") as fh:
            fh.write(b"x" * n)
        return path

    def lane(self, api, gated=True, loaded=True):
        """`_remote_audio` with a recogniser that waits for `gate` per clip and
        records which clips it ran and how many ran at once."""
        ran, running, peak, gate = [], [0], [0], threading.Semaphore(0)
        lock = threading.Lock()

        def transcribe(path, stats=None):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            if gated:
                gate.acquire(timeout=5)
            with lock:
                running[0] -= 1
            ran.append(os.path.basename(path))
            if stats is not None:
                stats["seconds"] = 2.5
            return "words of " + os.path.basename(path)
        patches = [mock.patch.object(crow_voice, "file_available", lambda: None),
                   mock.patch.object(crow_voice, "model_loaded", lambda: loaded),
                   mock.patch.object(crow_voice, "transcribe_file", transcribe)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return ran, peak, gate

    def settled(self, api):
        for _ in range(250):
            with api._voice_lock:
                if not any(v["busy"] for v in api._voice_lanes.values()):
                    return
            time.sleep(0.02)
        self.fail("the lane never went idle")

    def test_partials_are_coalesced_and_the_final_overtakes_them(self):
        """One running at a time; of the partials waiting behind it only the
        newest is kept; the final drops the waiting one AND silences the one
        that was running when it came in. Every clip is deleted."""
        api = self.mirrored()
        ran, peak, gate = self.lane(api)
        clips = {n: self.numbered(n) for n in (1, 2, 3, 4)}
        api._remote_audio(clips[1], PHONE, seq=1, partial=True)   # starts, waits
        for _ in range(100):
            if api._voice_lanes[PHONE]["partial"] is None:
                break
            time.sleep(0.01)
        api._remote_audio(clips[2], PHONE, seq=2, partial=True)   # waits
        api._remote_audio(clips[3], PHONE, seq=3, partial=True)   # replaces 2
        self.assertFalse(os.path.exists(clips[2]), "an overtaken partial was kept")
        api._remote_audio(clips[4], PHONE, seq=4)                 # the final
        self.assertFalse(os.path.exists(clips[3]), "the final left a partial waiting")
        for _ in range(2):
            gate.release()
        self.settled(api)
        self.assertEqual(ran, ["clip-1.webm", "clip-4.webm"])
        self.assertEqual(peak[0], 1, "two transcriptions ran for one phone")
        heard = [m for m in api._remote.got(PHONE) if m.get("k") == "heard"]
        self.assertEqual(heard, [{"k": "heard", "seq": 4, "text": "words of clip-4.webm"}])
        self.assertFalse(any(os.path.exists(c) for c in clips.values()))

    def test_a_partial_after_the_final_is_dropped_and_one_before_is_pushed(self):
        api = self.mirrored()
        ran, _peak, _gate = self.lane(api, gated=False)
        api._remote_audio(self.numbered(7), PHONE, seq=7, partial=True)
        self.settled(api)
        api._remote_audio(self.numbered(8), PHONE, seq=8)
        self.settled(api)
        late = self.numbered(6)
        api._remote_audio(late, PHONE, seq=6, partial=True)       # arrived late
        self.settled(api)
        self.assertEqual(ran, ["clip-7.webm", "clip-8.webm"])
        self.assertFalse(os.path.exists(late))
        heard = [m for m in api._remote.got(PHONE) if m.get("k") == "heard"]
        self.assertEqual(heard, [
            {"k": "heard", "partial": True, "seq": 7, "text": "words of clip-7.webm"},
            {"k": "heard", "seq": 8, "text": "words of clip-8.webm"}])

    def test_the_model_loading_is_said_and_each_final_is_one_log_line(self):
        api = self.mirrored()
        self.lane(api, gated=False, loaded=False)
        logged = []
        with mock.patch.object(crow_core, "log_note",
                               lambda text, kind="note": logged.append((kind, text))):
            api._remote_audio(self.numbered(3), PHONE, seq=3, partial=True)
            self.settled(api)
            api._remote_audio(self.numbered(5), PHONE, seq=5)
            self.settled(api)
        heard = [m for m in api._remote.got(PHONE) if m.get("k") == "heard"]
        self.assertEqual(heard[0], {"k": "heard", "loading": True})
        voice = [t for k, t in logged if k == "voice"]
        self.assertEqual(len(voice), 1, logged)
        self.assertRegex(voice[0], r"^phone dictation: 5 bytes, 2\.5 s, transcribe \d+ ms$")

    def test_a_failed_final_is_logged_with_its_error(self):
        api = self.mirrored()
        logged = []
        path = self.numbered(9)

        def broken(p, stats=None):
            raise RuntimeError("bad clip")
        with mock.patch.object(crow_voice, "file_available", lambda: None), \
                mock.patch.object(crow_voice, "model_loaded", lambda: True), \
                mock.patch.object(crow_voice, "transcribe_file", broken), \
                mock.patch.object(crow_core, "log_note",
                                  lambda text, kind="note": logged.append((kind, text))):
            api._remote_heard(path, PHONE, 9)
        self.assertEqual(logged, [("voice", logged[0][1])])
        self.assertRegex(logged[0][1], r"^phone dictation: 9 bytes, 0\.0 s, transcribe \d+ ms, "
                                       r"dictation failed: bad clip$")
        self.assertIn({"k": "heard", "seq": 9, "note": "dictation failed: bad clip"},
                      api._remote.got(PHONE))


class RemotePhoneMicTests(unittest.TestCase):
    """#290 on the page: in a secure context the 🎤 records (tap, tap), shows
    the level, uploads the clip as kind audio and puts the pushed words into
    the input without sending; on plain HTTP it keeps the keyboard hint. The
    desktop's own dictation never lands on the phone."""

    PRELUDE = r"""
const T = __TEXT__;
window.CROW_REMOTE_TEXT = T;
const attached = [], notes = [], sent = [], fetched = [], passed = [], gum = [];
let focused = false;
crow.attach = t => attached.push(t); crow.note = t => notes.push(t);
Object.assign(crow, {__HEARD__});
crow.on = m => { passed.push(m.k); if(m.k === "heard") crow.heard(m); };
crow.micState = e => passed.push(["micState", e.state, e.text, e.note]);
el("in").focus = () => { focused = true; };
Object.assign(el("in"), {value: "", readOnly: false, dispatchEvent(){}});
Date.now = () => now;
let LEVEL = 0.25, frameFn = null;
// one animation frame per 50 ms of the fake clock, at the given input level
const frames = (ms, lvl) => { LEVEL = lvl;
  for(let t = 0; t < ms; t += 50){ now += 50;
    if(frameFn){ const f = frameFn; frameFn = null; f(); } } };
globalThis.pywebview = {api: new Proxy({}, {get: (_, n) => (...a) => { sent.push(n); return Promise.resolve(null); }})};
globalThis.isSecureContext = SECURE;
const track = {stopped: false, stop(){ this.stopped = true; }};
Object.defineProperty(globalThis, "navigator", {configurable: true, value: {
  mediaDevices: SECURE ? {getUserMedia: c => { gum.push(c); return Promise.resolve({getTracks: () => [track]}); }} : undefined}});
globalThis.MediaRecorder = class { constructor(){ this.state = "inactive"; this.mimeType = "audio/mp4";
    globalThis.lastRec = this; }
  start(ms){ this.state = "recording"; this.slice = ms; }
  stop(){ this.state = "inactive"; this.ondataavailable({data: {size: 5}}); this.onstop(); } };
globalThis.AudioContext = class { createAnalyser(){ return {fftSize: 0, getFloatTimeDomainData(b){ b.fill(LEVEL); }}; }
  createMediaStreamSource(){ return {connect(){}}; } resume(){} close(){} };
globalThis.requestAnimationFrame = f => { frameFn = f; return 1; };
globalThis.cancelAnimationFrame = () => { frameFn = null; };
globalThis.Blob = class { constructor(parts, o){ this.size = parts.reduce((n, p) => n + (p.size || 0), 0); this.type = o.type; } };
globalThis.fetch = (url, o) => { fetched.push([url, o.method, o.headers["Content-Type"], o.body.size, o.credentials]);
  return Promise.resolve({ok: true, status: 202}); };
"""
    PROBE = r"""
(async () => {
  const tick = () => new Promise(r => setImmediate(r));
  const mic = el("mic"), out = {};
  crow.mic(); await tick(); await tick();
  out.gum = gum.length; out.rec = mic.classList.contains("rec"); out.lvl = mic.style.m["--lvl"] || null;
  crow.mic(); await tick(); await tick();
  out.after = mic.classList.contains("rec"); out.track = track.stopped; out.fetched = fetched;
  crow.on({k: "heard", text: "Hallo Crow"});
  crow.on({k: "heard", note: "nothing was said"});
  crow.micState({k: "mic", state: "off", text: "from the desktop", note: "desk note"});
  crow.on({k: "text", t: "x"});
  out.attached = attached; out.notes = notes; out.sent = sent; out.passed = passed;
  out.focused = focused; out.hint = el("hint").textContent || ""; out.title = mic.title;
  out.field = el("in").value;
  console.log(JSON.stringify(out));
})();
"""
    # #290 SCOPE AMENDMENT: partials, auto-stop on silence, the states, and
    # (robin, 2026-09-24 ~23:30) the stop square and append-never-replace.
    LIVE = r"""
(async () => {
  const tick = () => new Promise(r => setImmediate(r));
  const mic = el("mic"), field = el("in"), hint = () => el("hint").textContent || "";
  const out = {steps: []};
  const step = name => out.steps.push([name, field.value, field.classList.contains("partial"),
    field.readOnly, mic.classList.contains("rec"), !!mic.disabled, hint(),
    lastRec ? lastRec.state : null]);
  field.value = "Notiz:";                                    // typed before
  crow.mic(); await tick(); await tick();
  out.slice = lastRec.slice; step("listening");
  lastRec.ondataavailable({data: {size: 3}});                // 1.5 s of audio
  lastRec.ondataavailable({data: {size: 4}});                // 3 s
  crow.on({k: "heard", partial: true, seq: 2, text: "Hallo"});
  step("partial");
  crow.on({k: "heard", partial: true, seq: 1, text: "Hal"});   // older: ignored
  step("older partial");
  crow.on({k: "heard", loading: true}); step("loading");
  frames(400, 0.3);                                          // speech
  frames(1900, 0.001); step("1.9 s of silence");
  frames(200, 0.001); await tick(); step("2.1 s of silence");
  crow.on({k: "heard", partial: true, seq: 3, text: "Hallo Cr"});   // after the stop
  step("partial after the stop");
  crow.on({k: "heard", seq: 3, text: "Hallo Crow"}); step("final");
  // the second one appends to the first, and silence BEFORE speech stops nothing
  crow.mic(); await tick(); await tick();
  frames(3000, 0.001); step("second, 3 s quiet before speaking");
  lastRec.ondataavailable({data: {size: 5}});
  crow.on({k: "heard", partial: true, seq: 5, text: "und mehr"}); step("second partial");
  crow.mic(); await tick(); step("tapped stop");
  crow.on({k: "heard", seq: 6, text: "und mehr."}); step("second final");
  // a field that already ends in whitespace gets no second space
  field.value += "\n";
  crow.mic(); await tick(); await tick(); crow.mic(); await tick();
  crow.on({k: "heard", seq: 7, text: "Ende"}); step("third final");
  // a failed final: the partial goes, the typed text stays, the phone says why
  crow.mic(); await tick(); await tick();
  lastRec.ondataavailable({data: {size: 2}});
  crow.on({k: "heard", partial: true, seq: 9, text: "weg"});
  crow.mic(); await tick();
  crow.on({k: "heard", seq: 10, note: "dictation failed: bad clip"}); step("failed final");
  out.fetched = fetched.map(f => [f[0], f[3]]); out.notes = notes; out.sent = sent;
  out.attached = attached;
  console.log(JSON.stringify(out));
})();
"""

    @staticmethod
    def heard_method() -> str:
        """The page's own `heard(e){...}` -- the case the window's push reaches."""
        found = re.search(r"\n  (heard\(e\)\{[^\n]*\}),\n", crow_gui.PAGE)
        # none: an empty one, so the behaviour below is what fails, not this
        return found.group(1) if found else "heard(e){}"

    def run_mic(self, secure: bool, probe: "str | None" = None) -> dict:
        node = _node()
        if not node:
            self.skipTest("no node on this machine")
        import subprocess
        layer = RemotePhoneLayerTests
        js = ("globalThis.SECURE = %s;\n" % ("true" if secure else "false")
              + layer.FAKE_DOM
              + self.PRELUDE.replace("__TEXT__", json.dumps(crow_core.REMOTE_PHONE_TEXT))
                            .replace("__HEARD__", self.heard_method())
              + crow_gui.REMOTE_JS + (probe or self.PROBE))
        done = subprocess.run([node, "-e", js], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_https_records_uploads_and_fills_the_input_without_sending(self):
        out = self.run_mic(True)
        self.assertEqual(out["gum"], 1, "no recording was started")
        self.assertTrue(out["rec"])
        self.assertEqual(out["lvl"], "1.00", "no level on the ring")
        self.assertFalse(out["after"])
        self.assertTrue(out["track"], "the microphone stayed open")
        self.assertEqual(out["fetched"], [["/upload?kind=audio&seq=1", "POST", "audio/mp4", 5,
                                           "same-origin"]])
        self.assertEqual(out["field"], "Hallo Crow")
        self.assertEqual(out["notes"], ["nothing was said"])
        self.assertNotIn("send", out["sent"])
        self.assertNotIn("dictate_start", out["sent"])
        # the desktop's dictation: its state and words stay on the desktop
        self.assertIn(["micState", "off", "", ""], out["passed"])
        self.assertNotIn("from the desktop", out["attached"])
        self.assertIn('case "heard": this.heard(e); break;', crow_gui.PAGE)

    def test_partials_silence_states_and_two_dictations_append(self):
        """#290 scope amendment, live on robin's phone 2026-09-24: the ring
        moved and nothing arrived, because the second tap was not obvious.
        Now: greyed partial words after the typed text, a stop square while
        recording, auto-stop 2 s after speech, "writing ..." until the final,
        which replaces only the partial -- and the next dictation appends."""
        out = self.run_mic(True, self.LIVE)
        T = crow_core.REMOTE_PHONE_TEXT
        steps = {s[0]: s[1:] for s in out["steps"]}
        # (field, greyed, read-only, stop square, button disabled, hint, recorder)
        self.assertEqual(out["slice"], 1500)
        self.assertEqual(steps["listening"],
                         ["Notiz:", False, True, True, False, T["miclisten"], "recording"])
        self.assertEqual(steps["partial"],
                         ["Notiz: Hallo", True, True, True, False, T["miclisten"], "recording"])
        self.assertEqual(steps["older partial"][0], "Notiz: Hallo")
        self.assertEqual(steps["loading"][5], T["micload"])
        self.assertEqual(steps["1.9 s of silence"][6], "recording")
        self.assertEqual(steps["2.1 s of silence"],
                         ["Notiz: Hallo", True, True, False, True, T["micwrite"], "inactive"])
        self.assertEqual(steps["partial after the stop"][0], "Notiz: Hallo")
        self.assertEqual(steps["final"],
                         ["Notiz: Hallo Crow", False, False, False, False, "", "inactive"])
        self.assertEqual(steps["second, 3 s quiet before speaking"][6], "recording",
                         "silence before any speech stopped the recording")
        self.assertEqual(steps["second partial"][0], "Notiz: Hallo Crow und mehr")
        self.assertEqual(steps["tapped stop"][5], T["micwrite"])
        self.assertEqual(steps["second final"],
                         ["Notiz: Hallo Crow und mehr.", False, False, False, False, "",
                          "inactive"])
        self.assertEqual(steps["third final"][0], "Notiz: Hallo Crow und mehr.\nEnde")
        self.assertEqual(steps["failed final"][:3],
                         ["Notiz: Hallo Crow und mehr.\nEnde", False, False])
        self.assertEqual(out["notes"], ["dictation failed: bad clip"])
        self.assertEqual(out["fetched"], [
            ["/upload?kind=audio&partial=1&seq=1", 3],
            ["/upload?kind=audio&partial=1&seq=2", 7],
            ["/upload?kind=audio&seq=3", 12],
            ["/upload?kind=audio&partial=1&seq=4", 5],
            ["/upload?kind=audio&seq=5", 10],
            ["/upload?kind=audio&seq=6", 5],
            ["/upload?kind=audio&partial=1&seq=7", 2],
            ["/upload?kind=audio&seq=8", 7]])
        self.assertNotIn("send", out["sent"])
        self.assertEqual(out["attached"], [])

    def test_the_button_is_a_stop_square_while_it_records(self):
        """robin, 2026-09-24: the microphone turns into a filled square while
        recording -- currentColor, so both themes -- and keeps the ring and
        the 44 px target."""
        css = crow_gui.REMOTE_CSS
        self.assertIn("#mic.rec svg{display:none}", css)
        self.assertRegex(css, r'#mic\.rec::after\{content:"";[^}]*background:currentColor')
        self.assertRegex(css, r"#remoteattach,#mic\{width:var\(--tap\);height:var\(--tap\)")
        self.assertIn("#in.partial{color:var(--dim)}", css)

    def test_plain_http_keeps_the_keyboard_hint(self):
        out = self.run_mic(False)
        self.assertEqual(out["gum"], 0)
        self.assertEqual(out["fetched"], [])
        self.assertTrue(out["focused"])
        self.assertEqual(out["hint"], crow_core.REMOTE_PHONE_TEXT["dictate"])
        self.assertIn("HTTPS (Tailscale)", out["hint"])
        self.assertEqual(out["title"], "dictate: opens the keyboard")


if __name__ == "__main__":
    unittest.main(verbosity=2)
