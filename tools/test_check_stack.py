"""Negative control for check_stack.py's offline checks.

Each case breaks exactly one promise in a copy of the real manifest and requires
the checker to go red at THAT check and name it; the first case requires the real
manifest to be green. The --online half needs the network and is not run here.
"""

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_stack as C  # noqa: E402

with open(C.MANIFEST, encoding="utf-8") as _f:
    REAL = json.load(_f)


def point(doc, pid):
    return next(p for p in doc["points"] if p["id"] == pid)


def file_(doc, fid):
    return next(f for f in doc["files"] if f["id"] == fid)


def pending_hotset(doc):
    """The crow0924 hot set as it stood before its upload (published 2026-10-07,
    Crow #196): mirror-pending, fetched from crow-nest on GitHub. The schema cases
    for mirror-pending need one such file, and the real manifest has none left."""
    f = file_(doc, "fn-hotsets-crow0924")
    f.update(revision=None, status="mirror-pending", source={
        "host": "github", "repo": "nibor1896/crow-nest",
        "path": "decode_out/hotsets-M-crow0924-n160.json",
        "revision": "f4a3bd86f7b33db883f59c251cc04b37ac1ceeda",
        "bytes": f["bytes"], "sha256": f["sha256"], "license": "apache-2.0"})
    b = point(doc, "flash-next")["bytes"]
    b["published"] -= f["bytes"]
    b["mirror_pending"] += f["bytes"]
    return f


class Base(unittest.TestCase):
    def setUp(self):
        self.doc = copy.deepcopy(REAL)

    def red(self, label, needle):
        r = C.run(self.doc)
        fails = [ln for ln in r.lines if ln.startswith("  FAIL")]
        self.assertTrue(r.failed, "expected a failure at %s" % label)
        hit = [ln for ln in fails if label in ln]
        self.assertTrue(hit, "no FAIL at %r in %s" % (label, fails))
        self.assertIn(needle, "\n".join(r.lines))


class RealManifest(unittest.TestCase):
    def test_real_manifest_is_green(self):
        r = C.run(REAL)
        self.assertEqual(r.failed, 0, "\n".join(r.lines))
        self.assertEqual([p["id"] for p in REAL["points"]], list(C.POINT_IDS))


class Schema(Base):
    def test_unknown_status(self):
        file_(self.doc, "27b-cnq")["status"] = "local"
        self.red("schema", "status 'local'")

    def test_a_pending_hotset_alone_is_green(self):
        # the helper below builds a valid mirror-pending file, so each case that
        # uses it is red for its own reason only
        pending_hotset(self.doc)
        r = C.run(self.doc)
        self.assertEqual(r.failed, 0, "\n".join(r.lines))

    def test_mirror_pending_with_a_revision(self):
        pending_hotset(self.doc)["revision"] = "0" * 40
        self.red("schema", "revision must be null")

    def test_published_without_a_revision(self):
        file_(self.doc, "fn-cnq")["revision"] = None
        self.red("schema", "40-hex commit revision")

    def test_source_disagreeing_with_the_file(self):
        pending_hotset(self.doc)["source"]["sha256"] = "a" * 64
        self.red("schema", "differ from its source")

    def test_a_licence_shown_at_install_names_what_it_covers(self):
        # #340: the selection screen says "<covers>: <name>"; it used to say
        # "Qwen-Image weights" for every licence it showed.
        del self.doc["licenses"]["qwen-research"]["covers"]
        self.red("schema", "licence qwen-research is shown at install but names nothing it covers")

    def test_non_commercial_licence_hidden(self):
        self.doc["licenses"]["qwen-research"]["show_at_install"] = False
        self.red("schema", "not shown at install")

    def test_missing_point(self):
        self.doc["points"] = [p for p in self.doc["points"] if p["id"] != "27b"]
        self.red("schema", "expected")

    def test_shared_dest(self):
        file_(self.doc, "fn-sidecar")["dest"] = file_(self.doc, "fn-cnq")["dest"]
        self.red("schema", "share dest")


class UpstreamHosts(Base):
    """#340: an upstream file may come from GitHub (a raw file or a release asset)
    and may sit behind a Hugging Face gate the user has to pass."""

    def green_schema(self):
        r = C.run(self.doc)
        self.assertFalse([ln for ln in r.lines if ln.startswith("  FAIL") and "schema" in ln], r.lines)

    def test_a_github_raw_file_and_a_release_asset_are_valid(self):
        file_(self.doc, "qi-license")["host"] = "github"
        f = file_(self.doc, "qi-vae")
        f["host"], f["tag"] = "github-release", "v0.38.0"
        self.green_schema()

    def test_a_gated_hugging_face_file_is_valid(self):
        file_(self.doc, "qi-vae")["gated"] = True
        self.green_schema()

    def test_unknown_host(self):
        file_(self.doc, "qi-vae")["host"] = "gitlab"
        self.red("schema", "host 'gitlab'")

    def test_a_release_asset_needs_its_tag(self):
        file_(self.doc, "qi-vae")["host"] = "github-release"
        self.red("schema", "github-release needs a tag")

    def test_a_tag_belongs_to_a_release_asset_only(self):
        file_(self.doc, "qi-vae")["tag"] = "v1"
        self.red("schema", "tag only with host github-release")

    def test_gated_is_true_or_absent(self):
        file_(self.doc, "qi-vae")["gated"] = "yes"
        self.red("schema", "gated must be true")

    def test_only_hugging_face_has_a_gate(self):
        f = file_(self.doc, "qi-vae")
        f["host"], f["gated"] = "github", True
        self.red("schema", "gated only on host huggingface")

    def test_a_mirror_pending_file_takes_its_host_from_source(self):
        pending_hotset(self.doc)["host"] = "github"
        self.red("schema", "mirror-pending: the host is its source's")


class Paths(Base):
    def test_absolute_env_path(self):
        point(self.doc, "27b")["engine"]["env"]["CROW_CNQ"] = "D:/models/Qwen3.8-27B-CNQ4.5.cnq"
        self.red("placeholders and paths", "absolute or personal path")

    def test_home_path_in_documentation(self):
        self.doc["_what"] += " See /home/someone/models."
        self.red("placeholders and paths", "/_what")

    def test_unknown_placeholder(self):
        file_(self.doc, "qi-vae")["dest"] = "${HOME}/vae.safetensors"
        self.red("placeholders and paths", "${HOME}")

    def test_user_name(self):
        with mock.patch.dict(os.environ, {"USERNAME": "zzqbuilder"}):
            self.doc["files"][0]["role"] = "container of zzqbuilder"
            self.red("placeholders and paths", "names the user")

    def test_repo_owner_is_not_the_user(self):
        # #343: a Hugging Face repo id's namespace is the public owner the installer
        # downloads from, not a leak, even when it equals the builder's login.
        owner = REAL["files"][0]["repo"].split("/")[0]
        with mock.patch.dict(os.environ, {"USER": owner, "LOGNAME": owner}):
            r = C.run(self.doc)
            self.assertFalse([ln for ln in r.lines if "names the user" in ln], "\n".join(r.lines))

    def test_user_name_in_the_repo_name_part(self):
        with mock.patch.dict(os.environ, {"USERNAME": "zzqbuilder"}):
            self.doc["files"][0]["repo"] = "someorg/zzqbuilder-model"
            self.red("placeholders and paths", "names the user")

    def test_user_name_in_a_dest_beside_a_repo_owner(self):
        owner = REAL["files"][0]["repo"].split("/")[0]
        with mock.patch.dict(os.environ, {"USER": owner}):
            self.doc["files"][0]["dest"] = "${MODELS}/%s/x.cnq" % owner
            self.red("placeholders and paths", "names the user")


class References(Base):
    def test_unused_file(self):
        point(self.doc, "flash-next")["files"].remove("fn-sidecar")
        self.red("references", "fn-sidecar is used by no point")

    def test_undeclared_file(self):
        point(self.doc, "27b")["files"].append("27b-ghost")
        self.red("references", "27b-ghost")

    def test_derived_input_missing_from_point(self):
        point(self.doc, "image-stack")["files"].remove("qi-text-encoder-3")
        self.red("references", "without its input qi-text-encoder-3")


class Sums(Base):
    def test_file_bytes_change_without_the_totals(self):
        file_(self.doc, "27b-sidecar")["bytes"] += 1
        file_(self.doc, "27b-sidecar")["source"] = None
        self.red("byte sums", "point 27b bytes.published")

    def test_preflight_disk(self):
        point(self.doc, "image-stack")["preflight"]["disk_bytes"] -= 1
        self.red("byte sums", "preflight.disk_bytes")

    def test_derived_outputs(self):
        self.doc["derived"][0]["outputs"][0]["bytes"] += 7
        self.red("byte sums", "outputs sum to")


class Wiring(Base):
    def test_env_names_another_points_file(self):
        point(self.doc, "27b")["engine"]["env"]["CROW_VIT_MMPROJ"] = \
            file_(self.doc, "fn-mmproj")["dest"]
        self.red("engine wiring", "CROW_VIT_MMPROJ")

    def test_identity_of_the_wrong_model(self):
        point(self.doc, "27b")["engine"]["identity"]["endswith"] = "Qwen3.8-Flash-Next-CNQ4.5-M.cnq"
        self.red("engine wiring", "identity")

    def test_menu_claims_more_context_than_served(self):
        point(self.doc, "image-stack")["menu"]["line"] = "200k context \u2014 pictures"
        self.red("engine wiring", "claims 200k context")

    def test_slot_dir_not_created(self):
        point(self.doc, "flash-next")["engine"]["dirs"] = []
        self.red("engine wiring", "--slot-save-path")

    def test_sd_server_path_not_installed(self):
        argv = point(self.doc, "image-stack")["image_server"]["argv"]
        i = argv.index("--llm") + 1
        argv[i] = argv[i].replace("text_encoder_sdcli", "text_encoder_missing")
        self.red("engine wiring", "neither installed nor derived")

    def test_port_mismatch(self):
        point(self.doc, "image-stack")["image_server"]["port"] = 8098
        self.red("engine wiring", "--listen-port")


class Platforms(Base):
    """#341: both platforms start every point; the real manifest named Windows only."""

    def test_engine_without_a_linux_binary(self):
        del point(self.doc, "27b")["engine"]["binary"]["linux"]
        self.red("platforms", "point 27b engine.binary names ['windows']")

    def test_image_server_without_a_linux_binary(self):
        del point(self.doc, "image-stack")["image_server"]["binary"]["linux"]
        self.red("platforms", "point image-stack image_server.binary names ['windows']")

    def test_linux_binary_is_another_program(self):
        point(self.doc, "flash-next")["engine"]["binary"]["linux"] = "${INSTALL}/bin/serve.exe"
        self.red("platforms", "are not one program")

    def test_lib_path_missing(self):
        del self.doc["lib_path"]
        self.red("platforms", "lib_path must map windows / linux")

    def test_lib_path_without_the_engine_folder(self):
        self.doc["lib_path"]["linux"] = ["${INSTALL}/cuda/lib"]
        self.red("platforms", "lib_path.linux lacks ${INSTALL}/bin")

    def test_lib_path_outside_the_install(self):
        self.doc["lib_path"]["linux"].append("${MODELS}/lib")
        self.red("platforms", "is not a list of ${INSTALL}/ folders")


class PackageLicenses(Base):
    """Third-party files inside Crow's own package: the five MSVC runtime DLLs of the
    Windows package, under Microsoft's end-user terms, accepted with Install."""

    def test_the_real_entry_is_green(self):
        self.assertEqual(C.check_package_licenses(self.doc), [])
        r = C.run(self.doc)
        self.assertTrue([ln for ln in r.lines if ln.startswith("  OK") and "package licences" in ln], r.lines)

    def test_an_undeclared_licence(self):
        # run() stops at the schema first: the declared licence then has no text either
        self.doc["package_licenses"][0]["license"] = "msvc-eula"
        self.assertEqual(C.check_package_licenses(self.doc), ["package licence msvc-eula is not declared"])

    def test_a_licence_not_shown_at_install(self):
        self.doc["licenses"]["msvc-v14-runtime"]["show_at_install"] = False
        self.red("package licences", "package licence msvc-v14-runtime is not shown at install")

    def test_an_unknown_platform(self):
        self.doc["package_licenses"][0]["platforms"] = ["windows", "macos"]
        self.red("package licences", "package licence msvc-v14-runtime platforms")

    def test_a_url_only_text_needs_an_https_url(self):
        self.doc["licenses"]["msvc-v14-runtime"]["url"] = "http://example.com/terms"
        self.red("schema", "licence msvc-v14-runtime text_file None is not a file with role license")

    def test_a_url_only_text_is_for_package_licences_only(self):
        """NEGATIVE: without the package entry the licence names no text Crow can point at."""
        self.doc["package_licenses"] = []
        self.red("schema", "licence msvc-v14-runtime text_file None is not a file with role license")


class Cli(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, os.path.join(HERE, "check_stack.py"), *args],
                              capture_output=True, text=True)

    def test_exit_codes(self):
        ok = self.cli()
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("RESULT:", ok.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            bad = copy.deepcopy(REAL)
            bad["files"][0]["bytes"] = -1
            path = os.path.join(tmp, "stack.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(bad, f)
            self.assertEqual(self.cli("--manifest", path).returncode, 1)
            self.assertEqual(self.cli("--manifest", os.path.join(tmp, "none.json")).returncode, 2)


class ImageServerArgvDrift(unittest.TestCase):
    """stack.json's sd-server line is the one Crow itself builds (#196).

    The manifest copies crow_core.image_server_command; a change on either side
    without the other would boot the installed image stack on a line nobody
    measured. Paths are compared after expanding ${MODELS}, the flags verbatim.
    """

    def test_the_manifest_argv_is_crow_cores_argv(self):
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cli"))
        import crow_core
        import crow_platform
        server = point(REAL, "image-stack")["image_server"]
        models = os.path.join("M", "models")
        model_dir = os.path.join(models, "qwen-image-2.1")
        for plat, extra in server["argv_platform"].items():
            with self.subTest(platform=plat), \
                    mock.patch.object(crow_core, "image_model_dir", return_value=model_dir), \
                    mock.patch.object(crow_core, "image_server_binary", return_value="sd-server"), \
                    mock.patch.object(crow_platform, "image_server_platform_args", return_value=list(extra)):
                built = crow_core.image_server_command(server["port"])[1:]
            want = [a.replace("${MODELS}", models).replace("/", os.sep) if "${MODELS}" in a else a
                    for a in server["argv"]] + list(extra)
            self.assertEqual(built, want)


def crow_file(doc, fid):
    return next(f for f in doc["crow_files"] if f["id"] == fid)


class CrowFiles(Base):
    """The Crow-wide group: the dictation model every install gets (#196 P2-T2)."""

    def test_group_missing(self):
        del self.doc["crow_files"]
        self.red("crow files", "crow_files missing or empty")

    def test_unpinned_revision(self):
        crow_file(self.doc, "whisper-model")["revision"] = "main"
        self.red("crow files", "whisper-model needs a 40-hex commit revision")

    def test_mirror_pending_refused(self):
        crow_file(self.doc, "whisper-config")["status"] = "mirror-pending"
        self.red("crow files", "status 'mirror-pending'")

    def test_dest_under_models(self):
        f = crow_file(self.doc, "whisper-tokenizer")
        f["dest"] = f["dest"].replace("${INSTALL}/models", "${MODELS}")
        self.red("crow files", "does not start with ${INSTALL}/")

    def test_no_model_bin(self):
        self.doc["crow_files"] = [f for f in self.doc["crow_files"] if f["path"] != "model.bin"]
        self.red("crow files", "holds no ${INSTALL}/models/whisper-small/model.bin")

    def test_id_shared_with_files(self):
        crow_file(self.doc, "whisper-config")["id"] = "fn-cnq"
        self.red("crow files", "crow file id fn-cnq twice")

    def test_bad_sha(self):
        crow_file(self.doc, "whisper-vocabulary")["sha256"] = "XYZ"
        self.red("crow files", "whisper-vocabulary sha256 is not 64 lowercase hex")

    def test_field_missing(self):
        del crow_file(self.doc, "whisper-model")["bytes"]
        self.red("crow files", "whisper-model lacks bytes")

    def test_real_group_values(self):
        got = {f["path"]: f["bytes"] for f in REAL["crow_files"]}
        self.assertEqual(got, {"config.json": 2370, "vocabulary.txt": 459861,
                               "tokenizer.json": 2203239, "model.bin": 483546902})
        self.assertEqual(sum(got.values()), 486212372)
        self.assertEqual({f["repo"] for f in REAL["crow_files"]}, {"Systran/faster-whisper-small"})


class CrowFilesOnline(unittest.TestCase):
    """The online half of the group against a fake hub (no network)."""

    class FakeHub:
        def __init__(self, measured, head):
            self.measured, self._head, self.limits = measured, head, []

        def measure(self, repo, rev, path, limit=C.SMALL):
            self.limits.append(limit)
            return self.measured[path]

        def head(self, repo):
            return self._head

    def run_online(self, measured, head=None):
        doc = copy.deepcopy(REAL)
        rev = doc["crow_files"][0]["revision"]
        hub = self.FakeHub(measured, head or rev)
        r = C.Report()
        C.check_online_crow(doc, r, hub)
        return r, hub

    def truth(self):
        return {f["path"]: (f["bytes"], f["sha256"]) for f in REAL["crow_files"]}

    def test_matching_source_is_green_and_allows_the_2mb_tokenizer(self):
        r, hub = self.run_online(self.truth())
        self.assertEqual(r.failed, 0, "\n".join(r.lines))
        self.assertEqual(r.total, 4)
        self.assertGreater(C.CROW_SMALL, 2203239)
        self.assertEqual(set(hub.limits), {C.CROW_SMALL})

    def test_changed_source_fails(self):
        m = self.truth()
        m["model.bin"] = (m["model.bin"][0], "0" * 64)
        r, _ = self.run_online(m)
        self.assertEqual(r.failed, 1)
        self.assertIn("whisper-model: source has 483546902 B 000000000000", "\n".join(r.lines))

    def test_moved_head_is_a_note(self):
        r, _ = self.run_online(self.truth(), head="f" * 40)
        self.assertEqual(r.failed, 0)
        self.assertIn("HEAD is ffffffffffff", "\n".join(r.lines))


class DictationDrift(unittest.TestCase):
    """crow_files holds what Crow loads: the directory cli/crow_voice.py reads and the
    four files install.ps1 fetched into it."""

    def test_manifest_matches_crow_voice_and_install_ps1(self):
        root = os.path.dirname(HERE)
        with open(os.path.join(root, "cli", "crow_voice.py"), encoding="utf-8") as f:
            voice = f.read()
        with open(os.path.join(root, "install.ps1"), encoding="utf-8") as f:
            ps1 = f.read()
        dirname = re.search(r'^MODEL_DIRNAME = "([^"]+)"', voice, re.M).group(1)
        repo = re.search(r'^\$WHISPER_REPO\s*=\s*"([^"]+)"', ps1, re.M).group(1)
        # the loop right after $whisperDir is made: the four files it fetches
        after = ps1[ps1.index("$whisperDir = "):]
        files = re.findall(r'"([^"]+)"', re.search(
            r'foreach \(\$f in @\(([^)]*)\)\)', after).group(1))
        group = REAL["crow_files"]
        self.assertEqual(dirname, "whisper-small")
        self.assertEqual({f["repo"] for f in group}, {repo})
        self.assertEqual(sorted(f["path"] for f in group), sorted(files))
        for f in group:
            self.assertEqual(f["dest"], "${INSTALL}/models/%s/%s" % (dirname, f["path"]))


class TheWindowsLine(Base):
    """#196: menu.gui is the operating-point window's line (the terminal menu
    keeps menu.line). Present for every point, no dash, its context claim held
    to the engine, no user name."""

    def test_the_real_texts_are_the_approved_ones(self):
        self.assertEqual({p["id"]: p["menu"]["gui"] for p in REAL["points"]}, {
            "flash-next": "200k context. Great for coding and vision.",
            "27b": "128k context. Great speed, coding and vision.",
            "image-stack": "27B with Qwen-Image 2.1. Create pictures.",
            "media-stack": "Qwen3.5-9B with Qwen-Image 2.1 and LTX-2.5. Create pictures and videos.",
        })

    def test_a_point_without_one(self):
        del point(self.doc, "27b")["menu"]["gui"]
        self.red("engine wiring", "point 27b has no menu gui text")

    def test_a_dash_in_it(self):
        point(self.doc, "flash-next")["menu"]["gui"] = "200k context \u2014 great for coding."
        self.red("engine wiring", "menu gui text has a dash")

    def test_it_claims_more_context_than_served(self):
        point(self.doc, "image-stack")["menu"]["gui"] = "200k context. Pictures."
        self.red("engine wiring", "menu gui text claims 200k context")

    def test_it_names_the_user(self):
        with mock.patch.dict(os.environ, {"USERNAME": "zzqbuilder"}):
            point(self.doc, "27b")["menu"]["gui"] = "Built by zzqbuilder."
            self.red("placeholders and paths", "names the user")


def media_like(doc):
    """27b rebuilt as a llama-server point with a video server (#340), valid as built."""
    base = file_(doc, "27b-cnq")
    doc["files"] += [
        dict(base, id="g-model", path="model-Q8_0.gguf", dest="${MODELS}/g/model-Q8_0.gguf"),
        dict(base, id="g-mmproj", path="mmproj-F16.gguf", dest="${MODELS}/g/mmproj-F16.gguf",
             role="projector"),
        dict(base, id="g-runtime", path="comfyui.zip", dest="${INSTALL}/setup/comfyui.zip", role="runtime"),
    ]
    pt = point(doc, "27b")
    pt["files"] = ["g-model", "g-mmproj", "g-runtime"]
    pt["engine"] = {
        "kind": "llama-server",
        "binary": {"windows": "${INSTALL}/bin/llama-server.exe", "linux": "${INSTALL}/bin/llama-server"},
        "cwd": "${INSTALL}", "env": {}, "dirs": [], "port": 8099, "context": 131072,
        "argv": ["-m", "${MODELS}/g/model-Q8_0.gguf", "--mmproj", "${MODELS}/g/mmproj-F16.gguf",
                 "--port", "8099"],
        "readiness": {"method": "GET", "path": "/health", "status": 200, "json": {"status": "ok"}},
        "identity": {"method": "GET", "path": "/props", "field": "model_path", "endswith": "model-Q8_0.gguf"},
    }
    pt["video_server"] = {
        "binary": {"windows": "${INSTALL}/comfyui/python_embeded/python.exe",
                   "linux": "${INSTALL}/comfyui/venv/bin/python"},
        "argv": ["-s", "${INSTALL}/comfyui/ComfyUI/main.py", "--port", "8188"],
        "port": 8188,
        "readiness": {"method": "GET", "path": "/system_stats", "status": 200},
        "runtime": {"windows": {"file": "g-runtime", "dir": "${INSTALL}/comfyui"},
                    "linux": {"file": "g-runtime", "dir": "${INSTALL}/comfyui"}},
    }
    return pt


class LlamaEngineAndVideo(unittest.TestCase):
    """engine.kind llama-server and video_server (#340), on a rebuilt 27b."""

    def setUp(self):
        self.doc = copy.deepcopy(REAL)
        self.pt = media_like(self.doc)

    def problems(self):
        return C.check_schema(self.doc) + C.check_wiring(self.doc) + C.check_platforms(self.doc)

    def red(self, needle):
        self.assertTrue(any(needle in p for p in self.problems()), self.problems())

    def test_the_fixture_is_green(self):
        self.assertEqual(self.problems(), [])

    def test_unknown_engine_kind(self):
        self.pt["engine"]["kind"] = "vllm"
        self.red("engine kind 'vllm' is not one of")

    def test_model_flag_names_no_container(self):
        self.pt["engine"]["argv"][1] = "${MODELS}/g/mmproj-F16.gguf"
        self.red("llama-server -m does not name its container")

    def test_identity_of_another_file(self):
        self.pt["engine"]["identity"]["endswith"] = "other.gguf"
        self.red("identity must be /props model_path ending in model-Q8_0.gguf")

    def test_mmproj_not_installed(self):
        self.pt["engine"]["argv"][3] = "${MODELS}/g/missing.gguf"
        self.red("--mmproj ${MODELS}/g/missing.gguf is no projector")

    def test_serve_still_needs_its_slot_dir(self):
        self.pt["engine"]["kind"] = "serve"
        self.red("--slot-save-path None is not created")

    def full_runtime(self):
        for rt in self.pt["video_server"]["runtime"].values():
            rt.update({"strip": "ComfyUI_windows_portable", "bytes": 4384588275,
                       "model_paths": {"file": "ComfyUI/extra_model_paths.yaml",
                                       "base": "${MODELS}/ltx-2.5",
                                       "folders": ["diffusion_models", "text_encoders", "vae"]}})
        return self.pt["video_server"]["runtime"]["windows"]

    def test_a_full_runtime_is_green_and_its_bytes_count_as_derived(self):
        self.full_runtime()
        self.assertEqual(self.problems(), [])
        self.assertEqual(C.point_sums(self.doc, self.pt)["derived"], 4384588275)

    def test_runtime_strip_is_one_folder_name(self):
        self.full_runtime()["strip"] = "a/../b"
        self.red("runtime.windows.strip 'a/../b' is not one folder name")

    def test_runtime_bytes_are_positive(self):
        self.full_runtime()["bytes"] = 0
        self.red("runtime.windows.bytes 0 is not a positive integer")

    def test_model_paths_base_sits_under_a_placeholder(self):
        self.full_runtime()["model_paths"]["base"] = "C:/models"
        self.red("runtime.windows.model_paths.base 'C:/models' does not start with")

    def test_model_paths_name_folders(self):
        self.full_runtime()["model_paths"]["folders"] = []
        self.red("runtime.windows.model_paths.folders must list folder kinds")

    def test_model_paths_file_is_relative(self):
        self.full_runtime()["model_paths"]["file"] = "../x.yaml"
        self.red("runtime.windows.model_paths.file '../x.yaml' is not inside the runtime")

    def test_video_server_field_missing(self):
        del self.pt["video_server"]["runtime"]
        self.red("video_server lacks runtime")

    def test_video_port_differs_from_argv(self):
        self.pt["video_server"]["port"] = 8189
        self.red("video server --port differs from port 8189")

    def test_video_shares_the_engine_port(self):
        self.pt["video_server"]["port"] = 8099
        self.pt["video_server"]["argv"][3] = "8099"
        self.red("video server shares port 8099")

    def test_runtime_file_without_role_runtime(self):
        self.pt["video_server"]["runtime"]["linux"]["file"] = "g-model"
        self.red("video_server.runtime.linux.file 'g-model' is no runtime file")

    def test_video_path_outside_its_runtime(self):
        self.pt["video_server"]["argv"][1] = "${INSTALL}/elsewhere/main.py"
        self.red("video server path ${INSTALL}/elsewhere/main.py is neither installed nor in its runtime")

    def test_video_without_a_linux_binary(self):
        del self.pt["video_server"]["binary"]["linux"]
        self.red("video_server.binary names ['windows'], expected windows and linux")

    def test_video_binary_outside_its_runtime_dir(self):
        self.pt["video_server"]["binary"]["windows"] = "${INSTALL}/bin/python.exe"
        self.red("video_server.binary.windows is not inside its runtime dir")

    def windows_only(self):
        self.pt["platforms"] = ["windows"]
        self.pt["_platforms"] = "the video runtime is the Windows portable build"
        for m in (self.pt["engine"]["binary"], self.pt["video_server"]["binary"],
                  self.pt["video_server"]["runtime"]):
            del m["linux"]

    def test_a_windows_only_point_with_a_reason_is_green(self):
        self.windows_only()
        self.assertEqual(self.problems(), [])

    def test_a_windows_only_point_needs_a_reason(self):
        self.windows_only()
        del self.pt["_platforms"]
        self.red("runs on windows only and gives no reason (_platforms)")

    def test_an_unknown_platform(self):
        self.pt["platforms"] = ["windows", "macos"]
        self.red("platforms ['windows', 'macos'] is not a list of windows / linux")

    def test_a_windows_only_point_naming_a_linux_binary(self):
        self.windows_only()
        self.pt["engine"]["binary"]["linux"] = "${INSTALL}/bin/llama-server"
        self.red("engine.binary names ['linux', 'windows'], expected windows")


class PointLists(unittest.TestCase):
    """The hand-written point lists (#340), each broken in a copy of its source file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for rel in {entry[1] for entry in C.POINT_LISTS}:
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)), exist_ok=True)
            with open(os.path.join(C.REPO, rel), encoding="utf-8") as f:
                text = f.read()
            with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
                f.write(text)

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, rel, old, new):
        path = os.path.join(self.root, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn(old, text, "fixture text moved in %s" % rel)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new, 1))

    def problems(self, doc=REAL):
        return C.check_point_lists(doc, self.root)[0]

    def test_the_repo_is_green(self):
        problems, n = C.check_point_lists(REAL)
        self.assertEqual(problems, [])
        self.assertEqual(n, 9)

    def test_a_new_point_only_in_stack_json(self):
        doc = copy.deepcopy(REAL)
        doc["points"].append(dict(point(doc, "image-stack"), id="test-only-point"))
        problems = self.problems(doc)
        hit = {label for label, *_ in C.POINT_LISTS if any(label in p for p in problems)}
        self.assertEqual(hit, {label for label, _, _, rule, *_ in C.POINT_LISTS if rule != "subset"})

    def test_cli_points_without_a_point(self):
        self.edit("installer/app/src/cli.rs", '"image-stack", "media-stack"]', '"image-stack"]')
        self.assertIn("cli.rs POINTS", "\n".join(self.problems()))

    def test_boot_icon_missing(self):
        self.edit("cli/crow_boot.py", '    "image-stack": ', '    "image-stackz": ')
        self.assertTrue(any("crow_boot ICONS" in p and "lacks ['image-stack']" in p for p in self.problems()))

    def test_fake_plan_without_a_point(self):
        self.edit("installer/core/src/run.rs", 'if has("flash-next")', 'if false')
        self.assertTrue(any("run.rs fake plan" in p and "flash-next" in p for p in self.problems()))

    def test_mock_selects_an_unknown_point(self):
        self.edit("installer/ui/mock.js", "var points = ['flash-next', '27b']", "var points = ['flash-next', 'video']")
        self.assertTrue(any("mock.js selection" in p and "video" in p for p in self.problems()))

    def test_a_list_that_moved(self):
        self.edit("installer/ui/index.html", "var DESC = {", "var DESCRIPTIONS = {")
        self.assertTrue(any("setup page DESC: list not found" in p for p in self.problems()))


class OnlineToken(unittest.TestCase):
    """#340: --online measures a gated repo (Lightricks/LTX-2.5) with the user's
    Hugging Face token; Hugging Face hides an LFS sha256 without it."""

    def test_the_token_is_found_where_huggingface_hub_looks(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, ".cache", "huggingface"))
            with open(os.path.join(home, ".cache", "huggingface", "token"), "w") as fh:
                fh.write("hf_file\n")
            self.assertEqual(C.hf_token({}, home), "hf_file")
            self.assertEqual(C.hf_token({"HUGGING_FACE_HUB_TOKEN": "hf_old"}, home), "hf_old")
            self.assertEqual(C.hf_token({"HF_TOKEN": " hf_env ", "HUGGING_FACE_HUB_TOKEN": "x"}, home), "hf_env")
            self.assertIsNone(C.hf_token({}, os.path.join(home, "nobody")))

    def test_only_hugging_face_gets_the_token(self):
        seen = []

        class Resp:
            headers = {}

            def read(self, *a):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=0):
            seen.append((req.full_url, req.get_header("Authorization")))
            return Resp()

        with mock.patch.object(C, "hf_token", return_value="hf_x"), \
             mock.patch.object(C.urllib.request, "urlopen", fake_urlopen):
            C.fetch("https://huggingface.co/api/models/a/b")
            C.fetch("https://api.github.com/repos/a/b")
            C.fetch("https://huggingface.co.evil.example/x")
        self.assertEqual(seen, [("https://huggingface.co/api/models/a/b", "Bearer hf_x"),
                                ("https://api.github.com/repos/a/b", None),
                                ("https://huggingface.co.evil.example/x", None)])

    def test_a_hidden_sha256_is_named_not_compared(self):
        hub = C.Hub()
        hub.trees[("Lightricks/LTX-2.5", "r")] = {
            "vae/v.safetensors": {"size": 5, "lfs": {"oid": "*" * 64, "size": 5}}}
        with self.assertRaises(LookupError) as cm:
            hub.measure("Lightricks/LTX-2.5", "r", "vae/v.safetensors")
        self.assertIn("HF_TOKEN", str(cm.exception))



def wheel_(doc, wid):
    return next(w for w in doc["nvidia_files"] if w["id"] == wid)


EULA_DEST = "${INSTALL}/licenses/NVIDIA-CUDA-EULA.txt"


class NvidiaLicence(Base):
    """A licence may name no text_file only when its text_dest is the dest of
    the dist-info licence members of nvidia_files under that very licence."""

    def test_the_real_licence_is_green_through_the_wheels(self):
        lic = self.doc["licenses"]["nvidia-cuda-eula"]
        self.assertIsNone(lic["text_file"])
        self.assertEqual(lic["text_dest"], EULA_DEST)
        self.assertTrue(C.nvidia_licence_text(self.doc, "nvidia-cuda-eula", EULA_DEST))

    def test_a_text_dest_no_member_writes(self):
        self.doc["licenses"]["nvidia-cuda-eula"]["text_dest"] = "${INSTALL}/licenses/OTHER.txt"
        self.red("schema", "licence nvidia-cuda-eula text_file None is not a file with role license")

    def test_a_text_dest_that_is_a_library_not_a_licence_text(self):
        self.doc["licenses"]["nvidia-cuda-eula"]["text_dest"] = "${INSTALL}/bin/cublas64_13.dll"
        self.red("schema", "text_file None is not a file with role license")

    def test_no_text_dest_at_all(self):
        del self.doc["licenses"]["nvidia-cuda-eula"]["text_dest"]
        self.red("schema", "text_file None is not a file with role license")

    def test_a_wheel_under_another_licence_writes_the_text(self):
        wheel_(self.doc, "cudart-linux")["license"] = "apache-2.0"
        self.red("schema", "text_file None is not a file with role license")

    def test_another_licence_cannot_borrow_the_nvidia_text(self):
        self.doc["licenses"]["apache-2.0"]["text_file"] = None
        self.doc["licenses"]["apache-2.0"]["text_dest"] = EULA_DEST
        self.red("schema", "licence apache-2.0 text_file None is not a file with role license")

    def test_without_nvidia_files_the_null_text_file_is_refused(self):
        del self.doc["nvidia_files"]
        self.red("schema", "text_file None is not a file with role license")

    def test_a_missing_text_file_key_stays_refused(self):
        del self.doc["licenses"]["nvidia-cuda-eula"]["text_file"]
        self.red("schema", "licence nvidia-cuda-eula lacks text_file")

    def test_neither_wheels_nor_their_licence_is_green(self):
        del self.doc["nvidia_files"]
        del self.doc["licenses"]["nvidia-cuda-eula"]
        r = C.run(self.doc)
        self.assertEqual(r.failed, 0, "\n".join(r.lines))


class NvidiaFiles(Base):
    def test_the_real_wheels_are_green(self):
        self.assertEqual(C.check_nvidia_files(self.doc), [])
        r = C.run(self.doc)
        self.assertTrue([ln for ln in r.lines if ln.startswith("  OK") and "nvidia files" in ln], r.lines)

    def test_a_short_sha256(self):
        wheel_(self.doc, "cublas-windows")["sha256"] = "ab" * 31
        self.red("nvidia files", "nvidia file cublas-windows sha256 is not 64 lowercase hex")

    def test_an_upper_case_member_sha256(self):
        wheel_(self.doc, "nvrtc-windows")["extract"][0]["sha256"] = "AB" * 32
        self.red("nvidia files", "member nvidia/cu13/bin/x86_64/nvrtc64_130_0.dll sha256 is not 64 lowercase hex")

    def test_zero_bytes(self):
        wheel_(self.doc, "nvrtc-linux")["bytes"] = 0
        self.red("nvidia files", "nvidia file nvrtc-linux bytes 0 is not a positive integer")

    def test_member_bytes_that_are_not_a_number(self):
        wheel_(self.doc, "nvrtc-linux")["extract"][0]["bytes"] = "120080992"
        self.red("nvidia files", "bytes '120080992' is not a positive integer")

    def test_a_url_off_pypi(self):
        w = wheel_(self.doc, "cublas-linux")
        w["url"] = "https://github.com/example/mirror/releases/download/v1/" + w["url"].rsplit("/", 1)[1]
        self.red("nvidia files", "nvidia file cublas-linux url")

    def test_a_url_of_another_wheel(self):
        w = wheel_(self.doc, "cudart-linux")
        w["version"] = "13.3.30"
        self.red("nvidia files", "nvidia file cudart-linux url names another wheel than nvidia-cuda-runtime 13.3.30")

    def test_an_unknown_platform(self):
        wheel_(self.doc, "nvrtc-windows")["platform"] = "macos"
        self.red("nvidia files", "nvidia file nvrtc-windows platform 'macos' is not one of windows, linux")

    def test_an_unknown_server(self):
        wheel_(self.doc, "cublas-windows")["servers"] = ["comfyui"]
        self.red("nvidia files", "nvidia file cublas-windows servers ['comfyui']")

    def test_no_server(self):
        wheel_(self.doc, "cublas-windows")["servers"] = []
        self.red("nvidia files", "nvidia file cublas-windows servers []")

    def test_a_wheel_dest_outside_the_install(self):
        wheel_(self.doc, "nvrtc-linux")["dest"] = "${MODELS}/nvidia.whl"
        self.red("nvidia files", "nvidia file nvrtc-linux dest '${MODELS}/nvidia.whl' is not under ${INSTALL}/")

    def test_a_member_dest_that_climbs_out(self):
        wheel_(self.doc, "nvrtc-linux")["extract"][0]["dest"] = "${INSTALL}/../bin/libnvrtc.so"
        self.red("nvidia files", "dest '${INSTALL}/../bin/libnvrtc.so' is not under ${INSTALL}/")

    def test_a_member_name_that_leaves_the_wheel(self):
        for name in ("../evil.dll", "/abs/evil.dll", "nvidia\\evil.dll", "C:/evil.dll", "nvidia//evil.dll"):
            doc = copy.deepcopy(REAL)
            wheel_(doc, "cublas-windows")["extract"][0]["member"] = name
            self.doc = doc
            self.red("nvidia files", "member %r leaves the wheel" % name)

    def test_a_member_dest_another_file_uses(self):
        wheel_(self.doc, "cublas-windows")["extract"][0]["dest"] = file_(self.doc, "comfyui-license")["dest"]
        self.red("nvidia files", "dest ${INSTALL}/licenses/ComfyUI-LICENSE is another file's")

    def test_two_wheels_write_different_bytes_to_one_dest(self):
        a = wheel_(self.doc, "cublas-windows")["extract"][0]
        b = wheel_(self.doc, "nvrtc-windows")["extract"][0]
        b["dest"] = a["dest"]
        self.red("nvidia files", "nvidia files nvrtc-windows and cublas-windows write different bytes to ${INSTALL}/bin/cublas64_13.dll on windows")

    def test_the_same_dest_on_two_platforms_is_fine(self):
        # the EULA text, and dests the platforms share by name, are per platform
        self.assertEqual(C.check_nvidia_files(self.doc), [])
        dests = [(w["platform"], m["dest"]) for w in self.doc["nvidia_files"] for m in w["extract"]]
        self.assertIn(("windows", EULA_DEST), dests)
        self.assertIn(("linux", EULA_DEST), dests)

    def test_a_missing_field(self):
        del wheel_(self.doc, "cudart-linux")["servers"]
        self.red("nvidia files", "nvidia file cudart-linux lacks servers")

    def test_a_member_without_its_sha256(self):
        del wheel_(self.doc, "cudart-linux")["extract"][0]["sha256"]
        self.red("nvidia files", "nvidia file cudart-linux member")

    def test_an_id_a_model_file_already_has(self):
        wheel_(self.doc, "cudart-linux")["id"] = "27b-cnq"
        self.red("nvidia files", "nvidia file id 27b-cnq twice")

    def test_a_status_other_than_upstream(self):
        wheel_(self.doc, "cudart-linux")["status"] = "published"
        self.red("nvidia files", "nvidia file cudart-linux status 'published'")

    def test_an_undeclared_licence(self):
        w = wheel_(self.doc, "nvrtc-linux")
        w["license"] = "nvidia-eula-2"
        # without the EULA member, so the licence's own text rule is not what fails
        w["extract"] = [m for m in w["extract"] if m["dest"] != EULA_DEST]
        self.red("nvidia files", "nvidia file nvrtc-linux licence 'nvidia-eula-2' is not declared")

    def test_nothing_to_extract(self):
        wheel_(self.doc, "nvrtc-linux")["extract"] = []
        self.red("nvidia files", "nvidia file nvrtc-linux extracts nothing")

    def test_not_a_list(self):
        self.doc["nvidia_files"] = {"nvrtc": {}}
        del self.doc["licenses"]["nvidia-cuda-eula"]  # its text needs the wheels
        self.red("nvidia files", "nvidia_files is not a list")


if __name__ == "__main__":
    unittest.main()
