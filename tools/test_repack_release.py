"""Tests for tools/repack-release.py: what may ship, and the privacy gate (#196 C2).

Run: python -m unittest discover -s tools   (or python tools/test_repack_release.py)

Everything here is synthetic. The fake builder is "fakebuilder" on "FAKEHOST1";
no check depends on who runs the suite.
"""
import contextlib
import hashlib
import importlib.util
import io
import os
import re
import tempfile
import unittest
import zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, "pack-release.ps1")

_spec = importlib.util.spec_from_file_location("repack_release", os.path.join(HERE, "repack-release.py"))
rr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rr)

FAKE_PROFILE = "C:\\Users\\fakebuilder"
FAKE_HOST = "FAKEHOST1"


def put(root, rel, data=b"x"):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def make_repo(root):
    """A checkout with everything that ships and everything that must not."""
    bundle = b"// the bundle\n"
    kit = '{"bundle": {"sha256": "%s"}}' % hashlib.sha256(bundle).hexdigest()
    put(root, "LICENSE", b"MIT")
    put(root, "NOTICE", b"notice")
    put(root, "README.md", b"# crow")
    put(root, "cli/crow_core.py", b'VERSION = "9.9.9"\n')
    put(root, "cli/fonts/OFL.txt", b"OFL")
    put(root, "manifests/0731-chat-template.jinja", b"{{ x }}")
    put(root, "manifests/operating-point.json", b"{}")
    put(root, "manifests/stack.json", b"{}")
    put(root, "tools/te_rename.py", b"# te_rename\n")
    put(root, "manifests/shared-core.json", b"{}")
    put(root, "kits/pathtracer/crow-pathtracer.js", bundle)
    put(root, "kits/pathtracer/kit.json", kit.encode())
    for f in ("voxel-kit.js", "SKILL.md", "check_diorama.py", "scaffold/index.html", "scaffold/scene.js",
              "LICENSE.three", "LICENSE.three-mesh-bvh", "LICENSE.three-gpu-pathtracer"):
        put(root, "kits/pathtracer/" + f)
    # not for shipping
    put(root, "cli/runs/llama-server-8080.log", b"loading C:\\Users\\fakebuilder\\models\\x.gguf")
    put(root, "cli/runs/x.log")
    put(root, "cli/sub/notes.log")
    put(root, "cli/__pycache__/crow_core.cpython-313.pyc")
    put(root, "cli/test_crow_core.py")
    put(root, "cli/.env", b"KEY=1")
    put(root, "cli/secrets.json", b"{}")
    put(root, "cli/session.json", b"{}")
    put(root, "kits/pathtracer/__pycache__/c.pyc")
    put(root, "kits/pathtracer/runs/y.log")
    return root


def make_previous(path, dll=b"MZ clean binary"):
    rr.write_package(path, {"bin\\llama-server.exe": dll})
    return path


def run_main(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = rr.main(args)
    return code, buf.getvalue()


class ShippedSetTest(unittest.TestCase):
    def test_staging_leaves_out_runs_logs_and_state(self):
        with tempfile.TemporaryDirectory() as d:
            files = rr.stage_from_checkout(make_repo(d))
        names = sorted(files)
        for gone in ("runs", ".log", ".pyc", "test_", ".env", "secrets.json", "session.json", "shared-core"):
            self.assertFalse([n for n in names if gone in n], "%s shipped: %s" % (gone, names))
        for kept in ("cli\\crow_core.py", "cli\\fonts\\OFL.txt", "kits\\pathtracer\\kit.json",
                     "kits\\pathtracer\\scaffold\\scene.js", "templates\\0731-chat-template.jinja",
                     "manifests\\operating-point.json", "LICENSE", "NOTICE", "README.md"):
            self.assertIn(kept, names)

    def test_staging_ships_the_kit(self):
        # repack-release used to stage no kits\ at all; pack-release.ps1 always did
        with tempfile.TemporaryDirectory() as d:
            files = rr.stage_from_checkout(make_repo(d))
        self.assertTrue([n for n in files if n.startswith("kits\\pathtracer\\")])

    def test_a_kit_whose_bundle_does_not_match_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            put(d, "kits/pathtracer/crow-pathtracer.js", b"tampered")
            with self.assertRaises(SystemExit):
                rr.stage_from_checkout(d)

    def test_the_declared_set_is_a_closed_list(self):
        ok = ["LICENSE", "cli\\crow_core.py", "bin\\llama-server.exe", "kits\\pathtracer\\kit.json",
              "templates\\0731-chat-template.jinja", "manifests\\operating-point.json", "MANIFEST.json"]
        self.assertEqual(rr.shipped_set_violations(ok), [])
        bad = ["docs\\x.md", "stray.txt", "manifests\\shared-core.json", "templates\\other.jinja",
               "cli\\runs\\x.log", "bin\\a.log", "cli\\.env.local", "kits\\pathtracer\\runs\\y.log",
               "cli\\sessions\\a.txt", "cli/test_x.py"]
        got = {p.replace("/", "\\") for p, _ in rr.shipped_set_violations(bad)}
        self.assertEqual(got, {b.replace("/", "\\") for b in bad})

    def test_lists_match_the_ones_in_pack_release_ps1(self):
        with open(PS1, encoding="utf-8") as fh:
            ps = fh.read()

        def ps_list(name):
            m = re.search(r"\$" + name + r"\s*=\s*@\((.*?)\)", ps, re.S)
            self.assertTrue(m, "$%s not declared in pack-release.ps1" % name)
            return tuple(re.findall(r"'([^']*)'", m.group(1)))
        self.assertEqual(ps_list("SHIP_ROOT_FILES"), rr.SHIP_ROOT_FILES)
        self.assertEqual(ps_list("SHIP_TOP_DIRS"), rr.SHIP_TOP_DIRS)
        self.assertEqual(ps_list("SHIP_SINGLE_FILES"), rr.SHIP_SINGLE_FILES)
        self.assertEqual(ps_list("EXCLUDE_DIRS"), rr.EXCLUDE_DIRS)
        self.assertEqual(ps_list("EXCLUDE_FILES"), rr.EXCLUDE_FILES)
        self.assertEqual(ps_list("KIT_REQUIRED"), rr.KIT_REQUIRED)

    def test_the_privacy_allowlist_matches_the_one_in_pack_release_ps1(self):
        # The closing paren of the list is on a line of its own: the regexes hold parens.
        with open(PS1, encoding="utf-8") as fh:
            ps = fh.read()
        m = re.search(r"\$PRIVACY_ALLOW\s*=\s*@\(\s*\n(.*?)\n\)", ps, re.S)
        self.assertTrue(m, "$PRIVACY_ALLOW not declared in pack-release.ps1")
        self.assertEqual(tuple(re.findall(r"'([^']*)'", m.group(1))), rr.PRIVACY_ALLOW)


class PrivacyGateTest(unittest.TestCase):
    def pats(self, extra=()):
        return rr.private_patterns(extra, profile=FAKE_PROFILE, user="fakebuilder", host=FAKE_HOST)[0]

    def hit(self, blob, extra=()):
        return rr.scan_private({"bin\\x.dll": blob}, self.pats(extra))

    def test_profile_path_in_utf16le_binary_is_found(self):
        blob = b"MZ\x00\x90" + (FAKE_PROFILE + "\\dev\\llama.cpp\\ggml.c").encode("utf-16le") + b"\x00" * 9
        hits = self.hit(blob)
        self.assertTrue(hits and all(h[2] == "utf-16le" for h in hits), hits)
        self.assertEqual(hits[0][0], "bin\\x.dll")

    def test_profile_path_in_utf8_is_found_and_counted(self):
        blob = (FAKE_PROFILE + "\\a ").encode() * 3
        hits = self.hit(blob)
        self.assertIn(("bin\\x.dll", FAKE_PROFILE, "utf-8", 3), hits)

    def test_spellings_case_and_user_segments(self):
        for blob in (b"C:/Users/fakebuilder/dev", b"c:\\USERS\\FakeBuilder\\x", b"C:\\\\Users\\\\fakebuilder\\\\x",
                     b"see /home/fakebuilder/.cache", b"\\Users\\fakebuilder\\Desktop"):
            self.assertTrue(self.hit(blob), blob)

    def test_host_name_and_extra_patterns(self):
        self.assertTrue(self.hit(b"built on " + FAKE_HOST.lower().encode()))
        self.assertTrue(self.hit(b"x", extra=("x",)))
        self.assertTrue(self.hit(("secret-lab-name").encode("utf-16le"), extra=("secret-lab-name",)))

    def test_clean_bytes_pass(self):
        blob = b"MZ" + b"\x00" * 100 + "C:\\Windows\\System32\\kernel32.dll".encode("utf-16le") + b"/usr/lib/x"
        self.assertEqual(self.hit(blob), [])

    def test_the_gate_derives_this_machines_profile_by_default(self):
        pats, _ = rr.private_patterns()
        home = os.path.expanduser("~").rstrip("\\/")
        self.assertIn(home.replace("/", "\\").lower(), [p.lower() for p in pats])

    def test_the_bare_user_name_in_prose_is_found_in_both_encodings(self):
        text = "Write a report for FakeBuilder about the run"
        for enc in ("utf-8", "utf-16le"):
            hits = self.hit(text.encode(enc))
            self.assertTrue([h for h in hits if h[2] == enc], (enc, hits))

    def test_a_very_short_user_name_is_noted_not_searched_bare(self):
        pats, notes = rr.private_patterns(profile=FAKE_PROFILE, user="abc", host=FAKE_HOST)
        self.assertNotIn("abc", pats)
        self.assertTrue([n for n in notes if "'abc'" in n])

    def test_a_very_short_host_name_is_noted_not_searched(self):
        pats, notes = rr.private_patterns(profile=FAKE_PROFILE, user="fakebuilder", host="pc")
        self.assertNotIn("pc", pats)
        self.assertTrue(notes)


# What the real, rebuilt binaries carry (measured 2026-10-01): "round-robin" twice in the
# embedded web UI of llama-server-impl.dll, and tokenizer vocabulary (BPE merges, vocab
# JSON) in the two sd binaries, 29 hits each. These lines are verbatim from sd-cli.exe.
VOCAB = (b"\nrobin son</w>\n", b"\n\xe2\x96\x81Robins on\n", b"\n\xe2\x96\x81 Robinson\n",
         b"\n\xc4\xa0 Robin\n", b'"\xe2\x96\x81Robinson":29149,', b'"Robin": 101068,',
         b'"\xc4\xa0probing": 109172,', b'"\xe2\x96\x81odrobin",', b'"\xe2\x96\x81robinet",')
ROUND_ROBIN = b"east-stats random round-robin source-hash static-port"


class PrivacyAllowlistTest(unittest.TestCase):
    """The bare-name check stays, with a scoped allowlist: an upstream word that merely
    contains the owner's name is allowed in one named file, in one named context, up to
    a maximum count. Everything else refuses. The fake owner here is "robin" because the
    allowlist is about that name; no check depends on who runs the suite."""

    OWNER = "C:\\Users\\robin"
    IMPL = "bin\\llama-server-impl.dll"

    def gate(self, files, user="robin", profile=None):
        pats, notes = rr.private_patterns(profile=profile or self.OWNER, user=user, host=FAKE_HOST)
        buf = io.StringIO()
        with mock.patch.object(rr, "private_patterns", return_value=(pats, notes)), \
                contextlib.redirect_stdout(buf):
            ok = rr.privacy_gate(files)
        return ok, buf.getvalue()

    def impl(self, n=2, extra=b""):
        return {self.IMPL: b"MZ" + (ROUND_ROBIN + b"\x00") * n + extra}

    def test_round_robin_in_llama_server_impl_passes_and_is_logged(self):
        ok, out = self.gate(self.impl(2))
        self.assertTrue(ok, out)
        self.assertIn("INFO", out)
        self.assertIn(self.IMPL, out)
        self.assertIn("round-robin", out)
        self.assertIn("x2", out)

    def test_the_same_word_in_another_file_refuses(self):
        self.assertTrue(self.gate(self.impl(2))[0])  # control: the allowed shape
        ok, out = self.gate({"bin\\llama-server.exe": b"MZ" + ROUND_ROBIN})
        self.assertFalse(ok, out)
        self.assertIn("bin\\llama-server.exe", out)
        self.assertIn("REFUSING TO PACK", out)

    def test_a_third_occurrence_beyond_the_maximum_refuses(self):
        self.assertTrue(self.gate(self.impl(2))[0])
        ok, out = self.gate(self.impl(3))
        self.assertFalse(ok, out)
        self.assertIn("maximum", out)

    def test_a_bare_name_outside_any_allowed_context_refuses(self):
        self.assertTrue(self.gate(self.impl(1))[0])
        ok, out = self.gate(self.impl(1, b" Write a report for Robin about the run"))
        self.assertFalse(ok, out)
        self.assertIn(self.IMPL, out)

    def test_the_allowed_word_as_utf16le_is_not_allowed(self):
        self.assertTrue(self.gate(self.impl(2))[0])
        ok, out = self.gate({self.IMPL: b"MZ" + ROUND_ROBIN.decode().encode("utf-16le")})
        self.assertFalse(ok, out)

    def test_a_profile_path_in_an_allowed_file_refuses(self):
        self.assertTrue(self.gate(self.impl(2))[0])
        for path in (b"C:\\Users\\robin\\dev\\llama.cpp\\x.cpp", b"/home/robin/src", b"\\Users\\robin\\"):
            ok, out = self.gate(self.impl(2, b" " + path))
            self.assertFalse(ok, (path, out))
            self.assertIn("REFUSING TO PACK", out)

    def test_the_host_name_is_not_allowlisted(self):
        self.assertTrue(self.gate(self.impl(2))[0])
        ok, out = self.gate(self.impl(2, b" " + FAKE_HOST.encode()))
        self.assertFalse(ok, out)

    def test_tokenizer_vocabulary_passes_in_the_sd_binaries_only(self):
        blob = b"MZ" + b"".join(VOCAB)
        for name in ("bin\\sd-cli.exe", "bin\\sd-server.exe"):
            ok, out = self.gate({name: blob})
            self.assertTrue(ok, (name, out))
            self.assertIn("INFO", out)
        ok, out = self.gate({"bin\\llama.dll": blob})
        self.assertFalse(ok, out)

    def test_tokenizer_vocabulary_has_a_maximum_and_a_shape(self):
        line = b"\n\xe2\x96\x81 Robinson\n"
        self.assertTrue(self.gate({"bin\\sd-cli.exe": line * 29})[0])
        ok, out = self.gate({"bin\\sd-cli.exe": line * 30})
        self.assertFalse(ok, out)
        ok, out = self.gate({"bin\\sd-cli.exe": line + b"Write a report for Robin about the run"})
        self.assertFalse(ok, out)

    def test_the_allowlist_is_about_the_owner_robin_only(self):
        # control: for the owner robin the shape passes; for a machine whose user is someone
        # else it is not a word the allowlist was written for (round-robin contains "round")
        self.assertTrue(self.gate(self.impl(2))[0])
        ok, out = self.gate(self.impl(2), user="round", profile="C:\\Users\\round")
        self.assertFalse(ok, out)

    def test_a_pack_with_the_allowed_words_in_bin_packs(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(os.path.join(d, "repo"))
            prev = os.path.join(d, "prev.zip")
            rr.write_package(prev, {"bin\\llama-server-impl.dll": b"MZ" + ROUND_ROBIN * 2,
                                    "bin\\sd-cli.exe": b"MZ" + b"".join(VOCAB)})
            pats, notes = rr.private_patterns(profile=self.OWNER, user="robin", host=FAKE_HOST)
            with mock.patch.object(rr, "private_patterns", return_value=(pats, notes)):
                code, out = run_main(["--previous", prev, "--repo", repo, "--out", os.path.join(d, "out"),
                                      "--version", "9.9.9"])
            self.assertEqual(code, 0, out)
            self.assertIn("INFO", out)


class HostNameAndNamespaceTest(unittest.TestCase):
    """2026-10-02, v3.1.0 repack on the Linux box 'aios': three 'aios' hits inside the
    v3.0.0 bin\\ (compressed CUDA data "\\xcfaioSse", a base64 run "LAiosc8p") refused
    the package, and so did the public namespace, which repack had no allowlist for."""
    HOST = "aios"

    def scan(self, blob):
        pats = rr.private_patterns(profile=FAKE_PROFILE, user="fakebuilder", host=self.HOST)[0]
        return [h for h in rr.scan_private({"bin\\x.dll": blob}, pats, hosts=rr.host_names(self.HOST))
                if h[1] == self.HOST]

    def test_a_host_name_inside_a_word_or_binary_data_is_not_one(self):
        self.assertEqual(self.scan(b"\x9a\xcfaioSse\x97 bWwhzgRS4A8LAiosc8pfFKS4 \xbc\x9aaioS\r\x92"), [])

    def test_a_host_name_between_separators_is_found_in_both_encodings(self):
        for s in ("\\\\AIOS\\share", "aios.local", "user@aios:", "C:/build/aios/x", "\x00aios\x00"):
            for enc in ("utf-8", "utf-16le"):
                self.assertTrue(self.scan(b"\x00" + s.encode(enc) + b"\x00"), (s, enc))

    def test_the_gate_takes_the_namespace_in_a_windows_package(self):
        user = "nibor1896"
        files = {"README.md": b'<a href="https://github.com/nibor1896/Crow">x</a>',
                 "manifests\\stack.json": b'{"repo": "nibor1896/Qwen3.8-27B-CNQ4.5"}'}
        pats = rr.private_patterns(profile="/home/" + user, user=user, host=self.HOST)[0]
        hits = rr.scan_private(files, pats, hosts=rr.host_names(self.HOST))
        refused, allowed = rr.split_allowed(files, hits, pats, allow=rr.PRIVACY_ALLOW + rr.NAMESPACE_ALLOW)
        self.assertEqual(refused, [])
        self.assertEqual(len(allowed), 2)
        files["cli\\notes.py"] = b"# ask nibor1896 first"
        hits = rr.scan_private(files, pats, hosts=rr.host_names(self.HOST))
        refused, _ = rr.split_allowed(files, hits, pats, allow=rr.PRIVACY_ALLOW + rr.NAMESPACE_ALLOW)
        self.assertEqual([r[0] for r in refused], ["cli\\notes.py"])


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.repo = make_repo(os.path.join(self.tmp, "repo"))
        self.out = os.path.join(self.tmp, "out")

    def args(self, previous, *more):
        return ["--previous", previous, "--repo", self.repo, "--out", self.out, "--version", "9.9.9", *more]

    def test_a_dirty_bin_refuses_and_writes_nothing(self):
        dll = b"MZ" + (FAKE_PROFILE + "\\dev\\x.cpp").encode("utf-16le")
        prev = make_previous(os.path.join(self.tmp, "prev.zip"), dll)
        code, out = run_main(self.args(prev, "--private-pattern", FAKE_PROFILE))
        self.assertEqual(code, 1, out)
        self.assertIn("REFUSING TO PACK", out)
        self.assertIn("bin\\llama-server.exe", out)
        self.assertIn("utf-16le", out)
        self.assertIn(FAKE_PROFILE, out)
        self.assertFalse(os.path.exists(os.path.join(self.out, "crow-9.9.9-win-x64.zip")))

    def test_dirty_source_text_refuses_too(self):
        put(self.repo, "cli/crow_core.py", b'VERSION = "9.9.9"\n' + rb'P = "C:\Users\fakebuilder\Desktop"' + b'\n')
        prev = make_previous(os.path.join(self.tmp, "prev.zip"))
        code, out = run_main(self.args(prev, "--private-pattern", FAKE_PROFILE))
        self.assertEqual(code, 1, out)
        self.assertIn("cli\\crow_core.py", out)
        self.assertFalse(os.path.exists(self.out) and os.listdir(self.out))

    def test_a_clean_tree_packs_without_the_logs(self):
        prev = make_previous(os.path.join(self.tmp, "prev.zip"))
        code, out = run_main(self.args(prev, "--private-pattern", FAKE_PROFILE))
        self.assertEqual(code, 0, out)
        zpath = os.path.join(self.out, "crow-9.9.9-win-x64.zip")
        with zipfile.ZipFile(zpath) as z:
            # zipfile turns a backslash into "/" on Windows (the ZIP spec's separator)
            # and keeps it on Linux, so the names are compared in one form.
            names = [n.replace("/", "\\") for n in z.namelist()]
        self.assertIn("cli\\crow_core.py", names)
        self.assertIn("kits\\pathtracer\\kit.json", names)
        self.assertFalse([n for n in names if n.endswith(".log") or "\\runs\\" in n.replace("/", "\\")
                          or ".pyc" in n], names)

    def test_a_previous_bin_with_a_log_in_it_is_refused(self):
        rr.write_package(os.path.join(self.tmp, "prev.zip"),
                         {"bin\\llama-server.exe": b"MZ", "bin\\server.log": b"hello"})
        code, out = run_main(self.args(os.path.join(self.tmp, "prev.zip")))
        self.assertEqual(code, 1, out)
        self.assertIn("bin\\server.log", out)


class TheBootMenuManifestShipsTest(unittest.TestCase):
    """#196 P1: cli/crow_boot.py starts every operating point from
    manifests/stack.json and looks for it beside cli/, so the package carries it."""

    def test_the_checkout_s_stack_json_is_staged_byte_for_byte(self):
        files = rr.stage_from_checkout(rr.REPO)
        self.assertIn("manifests\\stack.json", files)
        with open(os.path.join(rr.REPO, "manifests", "stack.json"), "rb") as fh:
            self.assertEqual(files["manifests\\stack.json"], fh.read())
        self.assertEqual(rr.shipped_set_violations(["manifests\\stack.json"]), [])

    def test_a_synthetic_checkout_with_one_ships_it(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            put(d, "manifests/stack.json", b'{"points": []}')
            files = rr.stage_from_checkout(d)
        self.assertEqual(files["manifests\\stack.json"], b'{"points": []}')

    def test_a_checkout_without_one_is_refused(self):
        # pack-release.ps1 requires it too; a package without it boots nothing
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            os.remove(os.path.join(d, "manifests", "stack.json"))
            with self.assertRaises(SystemExit):
                rr.stage_from_checkout(d)

    def test_it_names_no_builder_and_no_profile_path(self):
        with open(os.path.join(rr.REPO, "manifests", "stack.json"), "rb") as fh:
            files = {"manifests\\stack.json": fh.read()}
        pats, _ = rr.private_patterns(profile=FAKE_PROFILE, user="fakebuilder", host=FAKE_HOST)
        self.assertEqual(rr.scan_private(files, pats + ["\\Users\\", "/Users/", "/home/"]), [])


class TheTextEncoderConverterShipsTest(unittest.TestCase):
    """#196 P2: CrowSetup runs <install>/tools/te_rename.py to build the Image
    Stack's text_encoder_sdcli/, so the package carries it -- and nothing else
    of tools/."""

    def test_the_staged_package_contains_it_byte_for_byte(self):
        files = rr.stage_from_checkout(rr.REPO)
        self.assertIn("tools\\te_rename.py", files)
        with open(os.path.join(rr.REPO, "tools", "te_rename.py"), "rb") as fh:
            self.assertEqual(files["tools\\te_rename.py"], fh.read())
        self.assertEqual([n for n in files if n.lower().startswith("tools\\")], ["tools\\te_rename.py"])

    def test_it_is_in_the_shipped_set_and_no_other_tool_is(self):
        self.assertEqual(rr.shipped_set_violations(["tools\\te_rename.py", "tools/te_rename.py"]), [])
        bad = ["tools\\repack-release.py", "tools\\check_stack.py", "tools\\sub\\te_rename.py"]
        self.assertEqual({p for p, _ in rr.shipped_set_violations(bad)}, set(bad))

    def test_it_passes_the_privacy_gate(self):
        with open(os.path.join(rr.REPO, "tools", "te_rename.py"), "rb") as fh:
            files = {"tools\\te_rename.py": fh.read()}
        pats, _ = rr.private_patterns(profile=FAKE_PROFILE, user="fakebuilder", host=FAKE_HOST)
        self.assertEqual(rr.scan_private(files, pats + ["\\Users\\", "/Users/", "/home/"]), [])

    def test_a_checkout_without_it_is_refused(self):
        # pack-release.ps1 refuses too; a package without it breaks the Image Stack step
        with tempfile.TemporaryDirectory() as d:
            make_repo(d)
            os.remove(os.path.join(d, "tools", "te_rename.py"))
            with self.assertRaises(SystemExit):
                rr.stage_from_checkout(d)

    def test_pack_release_ps1_stages_it_in_the_packing_path(self):
        with open(PS1, encoding="utf-8") as fh:
            ps = fh.read()
        self.assertRegex(ps, r"(?m)^Copy-ToolFiles -Repo \$repo -Stage \$stage")


class NoNvidiaFileShipsTest(unittest.TestCase):
    """CrowSetup downloads cuBLAS from NVIDIA's own wheel at install time; no package carries it."""

    NAMES = ("cublas64_13.dll", "cublasLt64_13.dll")

    def test_the_install_time_list_is_exactly_the_two_names(self):
        self.assertEqual(tuple(sorted(rr.NVIDIA_AT_INSTALL)), tuple(sorted(self.NAMES)))

    def test_pack_release_ps1_declares_the_same_list(self):
        with open(PS1, encoding="utf-8") as fh:
            ps = fh.read()
        m = re.search(r"\$NVIDIA_AT_INSTALL\s*=\s*@\((.*?)\)", ps, re.S)
        self.assertTrue(m, "$NVIDIA_AT_INSTALL not declared in pack-release.ps1")
        self.assertEqual(tuple(re.findall(r"'([^']*)'", m.group(1))), rr.NVIDIA_AT_INSTALL)

    def test_a_package_holding_one_is_refused_in_any_case_and_folder(self):
        got = {p for p, _ in rr.shipped_set_violations(
            ["bin\\cublas64_13.dll", "bin\\CUBLASLT64_13.DLL", "bin/sub/cublasLt64_13.dll"])}
        self.assertEqual(got, {"bin\\cublas64_13.dll", "bin\\CUBLASLT64_13.DLL", "bin\\sub\\cublasLt64_13.dll"})
        self.assertIn("NVIDIA", rr.shipped_set_violations(["bin\\cublas64_13.dll"])[0][1])

    def test_it_is_a_named_list_not_a_pattern(self):
        ok = ["bin\\ggml-cuda.dll", "bin\\cublas64_12.dll", "bin\\cudart64_13.dll", "bin\\cublasXX64_13.dll",
              "bin\\cublas64_13.dll.bak"]
        self.assertEqual(rr.shipped_set_violations(ok), [])

    def test_a_previous_package_with_them_repacks_without_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"))
            prev = os.path.join(tmp, "prev.zip")
            rr.write_package(prev, {"bin\\llama-server.exe": b"MZ clean", "bin\\ggml-cuda.dll": b"MZ cuda",
                                    "bin\\cublas64_13.dll": b"MZ nvidia", "bin\\cublasLt64_13.dll": b"MZ nvidia2"})
            out = os.path.join(tmp, "out")
            code, text = run_main(["--previous", prev, "--repo", repo, "--out", out, "--version", "9.9.9",
                                   "--private-pattern", FAKE_PROFILE])
            self.assertEqual(code, 0, text)
            self.assertIn("cublas64_13.dll", text)  # named as left out
            with zipfile.ZipFile(os.path.join(out, "crow-9.9.9-win-x64.zip")) as z:
                names = {n.replace("/", "\\") for n in z.namelist()}
            self.assertIn("bin\\llama-server.exe", names)
            self.assertIn("bin\\ggml-cuda.dll", names)
            self.assertFalse([n for n in names if "cublas" in n.lower()], names)

    def test_previous_bin_still_checks_their_bytes_against_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = os.path.join(tmp, "prev.zip")
            rr.write_package(prev, {"bin\\llama-server.exe": b"MZ", "bin\\cublas64_13.dll": b"MZ nvidia"})
            tampered = os.path.join(tmp, "tampered.zip")
            with zipfile.ZipFile(prev) as zin, zipfile.ZipFile(tampered, "w") as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    zout.writestr(item.filename, b"MZ other" if "cublas" in item.filename else data)
            with self.assertRaises(SystemExit):
                rr.previous_bin(tampered)
            left = []
            self.assertEqual(sorted(rr.previous_bin(prev, left)), ["bin\\llama-server.exe"])
            self.assertEqual(left, ["bin\\cublas64_13.dll"])

    def test_pack_release_ps1_leaves_them_out_and_gates_on_them(self):
        with open(PS1, encoding="utf-8") as fh:
            ps = fh.read()
        self.assertRegex(ps, r"(?m)^\s*if \(Test-NvidiaAtInstall \$f\.Name\)\s+\{ \$binLeft \+= \$f\.Name; continue \}")
        self.assertRegex(ps, r"(?s)Get-NvidiaFiles -Paths @\(Get-ChildItem \$stage -Recurse.*?an NVIDIA library is in the package")


if __name__ == "__main__":
    unittest.main()
