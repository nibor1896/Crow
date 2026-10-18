//! T3 check: the boot menu's own plan (`crow_boot.py --plan <point> --json`),
//! then files, sizes, sha256 and whether the binaries start.

use crowsetup_core::check::{self, StartRule};
use crowsetup_core::python;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

fn py() -> python::PythonInfo {
    python::find().expect("these tests need a Python 3.10+")
}

fn sha_lower(data: &[u8]) -> String {
    hex::encode(Sha256::digest(data))
}

fn js(p: &Path) -> String {
    p.to_string_lossy().replace('\\', "\\\\")
}

struct World {
    _tmp: tempfile::TempDir,
    root: PathBuf,
    models: PathBuf,
}

/// A plan JSON in the shape `crow_boot.py --plan --json` prints, with real temp files.
fn world() -> World {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().join("Crow");
    let models = tmp.path().join("models");
    fs::create_dir_all(root.join("bin")).unwrap();
    fs::create_dir_all(models.join("m")).unwrap();
    fs::create_dir_all(models.join("qi/text_encoder_sdcli")).unwrap();
    fs::write(root.join("bin/serve.exe"), b"MZ").unwrap();
    fs::write(root.join("bin/sd-server.exe"), b"MZ").unwrap();
    fs::write(models.join("m/a.cnq"), b"container").unwrap();
    fs::write(models.join("m/tok.json"), b"{\"t\": 1}").unwrap();
    fs::write(models.join("qi/text_encoder_sdcli/model-1.safetensors"), b"shard1").unwrap();
    fs::write(models.join("qi/text_encoder_sdcli/index.json"), b"{}").unwrap();
    World { _tmp: tmp, root, models }
}

fn plan_json(w: &World, serve: &Path, image: Option<&Path>) -> String {
    let image = match image {
        Some(p) => format!(r#"{{"binary": "{}", "argv": ["--listen-port", "8097"], "port": 8097, "readiness": {{"path": "/sdcpp/v1/capabilities", "status": 200}}}}"#, js(p)),
        None => "null".into(),
    };
    format!(
        r#"{{
  "point": "image-stack",
  "serve": {{"binary": "{serve}", "argv": ["--port", "8099"], "cwd": "{root}", "env": {{"CROW_CNQ": "{cnq}"}}, "dirs": [], "port": 8099, "readiness": {{"path": "/health", "status": 200, "json": {{"status": "ok"}}}}}},
  "image": {image},
  "files": [
    {{"id": "cnq", "dest": "{cnq}", "bytes": 9, "sha256": "{cnq_sha}"}},
    {{"id": "tok", "dest": "{tok}", "bytes": 8, "sha256": "{tok_sha}"}},
    {{"id": "te-1", "dest": "{te1}", "bytes": 5, "sha256": "{te_sha}"}}
  ],
  "derived": [
    {{"id": "sdcli", "dest": "{sd}", "inputs": ["te-1"], "outputs": [
      {{"dest": "{sd1}", "bytes": 6, "sha256": null}},
      {{"dest": "{sdi}", "bytes": 2, "sha256": "{sdi_sha}"}}
    ]}}
  ]
}}"#,
        serve = js(serve),
        root = js(&w.root),
        cnq = js(&w.models.join("m/a.cnq")),
        tok = js(&w.models.join("m/tok.json")),
        te1 = js(&w.models.join("qi/text_encoder/model-1.safetensors")),
        sd = js(&w.models.join("qi/text_encoder_sdcli")),
        sd1 = js(&w.models.join("qi/text_encoder_sdcli/model-1.safetensors")),
        sdi = js(&w.models.join("qi/text_encoder_sdcli/index.json")),
        cnq_sha = sha_lower(b"container"),
        tok_sha = sha_lower(b"{\"t\": 1}").to_uppercase(),
        te_sha = sha_lower(b"shard"),
        sdi_sha = sha_lower(b"{}"),
        image = image,
    )
}

fn plan(w: &World) -> check::BootPlan {
    let text = plan_json(w, &w.root.join("bin/serve.exe"), Some(&w.root.join("bin/sd-server.exe")));
    check::parse_plan(&text).unwrap()
}

#[test]
fn the_plan_json_parses() {
    let w = world();
    let p = plan(&w);
    assert_eq!(p.point, "image-stack");
    assert_eq!(p.serve.port, 8099);
    assert_eq!(p.serve.env["CROW_CNQ"], w.models.join("m/a.cnq").to_string_lossy());
    assert_eq!(p.image.as_ref().unwrap().port, 8097);
    assert_eq!(p.files.len(), 3);
    assert_eq!(p.derived[0].inputs, vec!["te-1"]);
    assert!(check::parse_plan("{\"point\": 1}").is_err());
}

#[test]
fn a_complete_point_passes_and_a_consumed_input_is_not_asked_for() {
    // text_encoder/ (te-1) was deleted by the convert step; its output is what counts
    let w = world();
    check::check_files(&plan(&w), &|_id: &str| false).unwrap();
}

#[test]
fn a_missing_file_is_named() {
    let w = world();
    fs::remove_file(w.models.join("m/tok.json")).unwrap();
    let err = check::check_files(&plan(&w), &|_id: &str| false).unwrap_err();
    assert!(err.contains("tok.json") && err.contains("missing"), "{err}");
}

#[test]
fn a_wrong_size_is_named_even_for_a_verified_file() {
    let w = world();
    fs::write(w.models.join("m/a.cnq"), b"contain").unwrap();
    let err = check::check_files(&plan(&w), &|_id: &str| true).unwrap_err();
    assert!(err.contains("a.cnq") && err.contains("7") && err.contains("9"), "{err}");
}

#[test]
fn sha256_is_checked_only_for_files_the_run_has_not_verified() {
    let w = world();
    // same size, other bytes
    fs::write(w.models.join("m/a.cnq"), b"CONTAINER").unwrap();
    let err = check::check_files(&plan(&w), &|_id: &str| false).unwrap_err();
    assert!(err.contains("a.cnq") && err.contains("sha256"), "{err}");
    // the download already verified it: not hashed again
    check::check_files(&plan(&w), &|id: &str| id == "cnq").unwrap();
}

#[test]
fn a_derived_output_is_checked_by_size_and_by_sha_when_pinned() {
    let w = world();
    fs::write(w.models.join("qi/text_encoder_sdcli/index.json"), b"[]").unwrap();
    let err = check::check_files(&plan(&w), &|_id: &str| true).unwrap_err();
    assert!(err.contains("index.json"), "{err}");
    let w = world();
    fs::remove_file(w.models.join("qi/text_encoder_sdcli/model-1.safetensors")).unwrap();
    let err = check::check_files(&plan(&w), &|_id: &str| true).unwrap_err();
    assert!(err.contains("model-1.safetensors"), "{err}");
}

#[test]
fn a_missing_binary_is_named() {
    let w = world();
    fs::remove_file(w.root.join("bin/sd-server.exe")).unwrap();
    let err = check::check_files(&plan(&w), &|_id: &str| true).unwrap_err();
    assert!(err.contains("sd-server.exe"), "{err}");
}

#[test]
fn starting_is_judged_by_launch_and_usage_not_by_exit_zero() {
    let serve = StartRule::UsageOrZero("usage: serve");
    // serve's parse_args: `--help needs a value (usage: serve ...)`, exit 2
    check::judge_start("serve.exe", serve, Some(2), "[serve] --help needs a value (usage: serve [--port <n>])").unwrap();
    check::judge_start("serve.exe", serve, Some(0), "").unwrap();
    let err = check::judge_start("serve.exe", serve, Some(2), "something else").unwrap_err();
    assert!(err.contains("serve.exe"), "{err}");
    // STATUS_DLL_NOT_FOUND: the loader failed before main
    let err = check::judge_start("serve.exe", serve, Some(0xC000_0135_u32 as i32), "").unwrap_err();
    assert!(err.contains("C0000135") && err.contains("DLL"), "{err}");
    check::judge_start("sd-server.exe", StartRule::ExitZero, Some(0), "usage").unwrap();
    assert!(check::judge_start("sd-server.exe", StartRule::ExitZero, Some(1), "").is_err());
    assert!(check::judge_start("sd-server.exe", StartRule::ExitZero, None, "").is_err());
}

#[test]
fn a_real_process_is_started_and_judged() {
    let exe = py().exe;
    let t = Duration::from_secs(60);
    let usage = "import sys; sys.stderr.write('[serve] --help needs a value (usage: serve [--port <n>])\\n'); sys.exit(2)";
    check::binary_starts(&exe, &["-c", usage], StartRule::UsageOrZero("usage: serve"), t).unwrap();
    #[cfg(windows)]
    {
        let crash = "import sys; sys.exit(-1073741515)";
        let err = check::binary_starts(&exe, &["-c", crash], StartRule::UsageOrZero("usage: serve"), t).unwrap_err();
        assert!(err.contains("DLL"), "{err}");
    }
    // Linux (#342): the loader's own message and exit 127 for a missing library
    #[cfg(not(windows))]
    {
        let crash = "import sys; sys.stderr.write('serve: error while loading shared libraries: libnvrtc.so: \
                     cannot open shared object file\\n'); sys.exit(127)";
        let err = check::binary_starts(&exe, &["-c", crash], StartRule::UsageOrZero("usage: serve"), t).unwrap_err();
        assert!(err.contains("exited 127") && err.contains("libnvrtc.so"), "{err}");
    }
    let err = check::binary_starts(Path::new("C:\\nope\\serve.exe"), &["--help"], StartRule::ExitZero, t).unwrap_err();
    assert!(err.contains("serve.exe"), "{err}");
    let hang = "import time; time.sleep(30)";
    let err = check::binary_starts(&exe, &["-c", hang], StartRule::ExitZero, Duration::from_secs(2)).unwrap_err();
    assert!(err.contains("2 s") || err.contains("did not exit"), "{err}");
}

#[test]
fn check_point_runs_the_boot_menus_plan_and_the_binaries() {
    let w = world();
    let p = py();
    // the fake binaries are the interpreter: `python --help` launches and exits 0
    let text = plan_json(&w, &p.exe, Some(&p.exe));
    fs::create_dir_all(w.root.join("cli")).unwrap();
    fs::write(w.root.join("cli/plan.json"), &text).unwrap();
    let script = r#"
import os, sys
a = sys.argv[1:]
want = ["--install-root", os.environ["CHECK_ROOT"], "--models", os.environ["CHECK_MODELS"], "--plan", "image-stack", "--json"]
if a != want:
    print("unexpected argv %r" % a, file=sys.stderr); sys.exit(2)
sys.stdout.write(open(os.path.join(os.path.dirname(__file__), "plan.json")).read())
"#;
    fs::write(w.root.join("cli/crow_boot.py"), script).unwrap();
    // SAFETY: tests in this binary that read these two variables are only this one
    unsafe {
        std::env::set_var("CHECK_ROOT", &w.root);
        std::env::set_var("CHECK_MODELS", &w.models);
    }
    check::check_point(&p, &w.root, &w.models, "image-stack").unwrap();

    fs::remove_file(w.models.join("m/a.cnq")).unwrap();
    let err = check::check_point(&p, &w.root, &w.models, "image-stack").unwrap_err();
    assert!(err.contains("a.cnq"), "{err}");
}

#[test]
fn check_point_against_the_real_boot_menu_names_what_is_missing() {
    // the checkout itself as the install root: cli/crow_boot.py and
    // manifests/stack.json are real, bin\serve.exe and the models are not there
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
    assert!(repo.join("cli").join("crow_boot.py").is_file(), "{}", repo.display());
    let models = tempfile::tempdir().unwrap();
    let err = check::check_point(&py(), repo, models.path(), "27b").unwrap_err();
    if cfg!(windows) {
        assert!(err.contains("serve.exe"), "{err}");
    } else if err.contains("names no engine binary") {
        // #342: until manifests/stack.json carries `binary.linux` (#341) the boot
        // menu itself refuses, and says so; nothing more can be checked here
        return;
    } else {
        assert!(err.contains("bin/serve"), "{err}");
    }
    assert!(err.contains("Qwen3.8-27B-CNQ4.5.cnq"), "{err}");
    let err = check::check_point(&py(), repo, models.path(), "no-such-point").unwrap_err();
    assert!(err.contains("no-such-point"), "{err}");
}

/// #348: the Media Stack's shape. The runtime step deleted the ComfyUI 7z after
/// unpacking it; the check asks for the unpacked program instead.
fn runtime_plan(w: &World, archive_listed: bool) -> check::BootPlan {
    let archive = w.root.join("setup/downloads/comfy.7z");
    let python = w.root.join("comfyui/python_embeded/python.exe");
    let text = format!(
        r#"{{"point": "media-stack",
  "serve": {{"binary": "{serve}", "argv": [], "cwd": "{root}", "env": {{}}, "dirs": [], "port": 8099, "readiness": {{"path": "/health", "status": 200}}}},
  "image": null,
  "video": {{"binary": "{python}", "argv": [], "port": 8188, "readiness": {{"path": "/system_stats", "status": 200}}, "runtime": "{runtime}"}},
  "files": [{{"id": "comfyui-portable", "dest": "{archive}", "bytes": 4, "sha256": null}}],
  "derived": [],
  "runtime_archives": [{listed}]}}"#,
        serve = js(&w.root.join("bin/serve.exe")),
        root = js(&w.root),
        python = js(&python),
        runtime = js(&w.root.join("comfyui")),
        archive = js(&archive),
        listed = if archive_listed { "\"comfyui-portable\"" } else { "" },
    );
    check::parse_plan(&text).unwrap()
}

#[test]
fn a_runtime_archive_the_unpack_deleted_is_not_asked_for() {
    let w = world();
    fs::create_dir_all(w.root.join("comfyui/python_embeded")).unwrap();
    fs::write(w.root.join("comfyui/python_embeded/python.exe"), b"MZ").unwrap();
    check::check_files(&runtime_plan(&w, true), &|_id: &str| true).unwrap();
}

#[test]
fn an_unpacked_runtime_without_its_program_is_named() {
    let w = world();
    let err = check::check_files(&runtime_plan(&w, true), &|_id: &str| true).unwrap_err();
    assert!(err.contains("python.exe") && err.contains("missing"), "{err}");
}
