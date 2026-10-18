//! T3 convert: tools/te_rename.py builds text_encoder_sdcli/, then text_encoder/
//! goes. The script here is a fake with the real one's argv and exit codes.

use crowsetup_core::{convert, python};
use std::fs;
use std::path::Path;

fn py() -> python::PythonInfo {
    python::find().expect("these tests run the fake te_rename.py with a Python 3.10+")
}

const OK_SCRIPT: &str = r#"
import os, sys
src, dst = sys.argv[1], sys.argv[2]
assert os.path.isdir(src), src
os.makedirs(dst, exist_ok=True)
for name in os.listdir(src):
    with open(os.path.join(src, name), "rb") as a, open(os.path.join(dst, name), "wb") as b:
        b.write(a.read())
sys.exit(0)
"#;

const FAIL_SCRIPT: &str = r#"
import sys
print("te_rename: shard model-00002-of-00004.safetensors: unknown prefix 'foo.'", file=sys.stderr)
sys.exit(1)
"#;

fn setup(script: &str) -> (tempfile::TempDir, std::path::PathBuf, std::path::PathBuf) {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().join("Crow");
    let models = tmp.path().join("models");
    fs::create_dir_all(root.join("tools")).unwrap();
    fs::write(root.join("tools/te_rename.py"), script).unwrap();
    let te = models.join("qwen-image-2.1/text_encoder");
    fs::create_dir_all(&te).unwrap();
    fs::write(te.join("model.safetensors.index.json"), b"{}").unwrap();
    fs::write(te.join("model-00001-of-00004.safetensors"), b"shard").unwrap();
    (tmp, root, models)
}

fn sd(models: &Path) -> std::path::PathBuf {
    models.join("qwen-image-2.1/text_encoder_sdcli")
}

#[test]
fn a_successful_rename_deletes_the_upstream_text_encoder() {
    let (_tmp, root, models) = setup(OK_SCRIPT);
    convert::image_text_encoder(&py(), &root, &models).unwrap();
    assert!(sd(&models).join("model.safetensors.index.json").is_file());
    assert!(sd(&models).join("model-00001-of-00004.safetensors").is_file());
    assert!(!models.join("qwen-image-2.1/text_encoder").exists(), "text_encoder/ stayed");
}

#[test]
fn a_failed_rename_keeps_the_text_encoder_and_says_why() {
    let (_tmp, root, models) = setup(FAIL_SCRIPT);
    let err = convert::image_text_encoder(&py(), &root, &models).unwrap_err();
    assert!(err.contains("unknown prefix"), "{err}");
    assert!(models.join("qwen-image-2.1/text_encoder/model-00001-of-00004.safetensors").is_file());
}

#[test]
fn a_rerun_after_the_delete_is_done_not_an_error() {
    let (_tmp, root, models) = setup(OK_SCRIPT);
    convert::image_text_encoder(&py(), &root, &models).unwrap();
    // text_encoder/ is gone now; the script would fail on it, so it must not run
    fs::write(root.join("tools/te_rename.py"), FAIL_SCRIPT).unwrap();
    convert::image_text_encoder(&py(), &root, &models).unwrap();
    assert!(sd(&models).join("model.safetensors.index.json").is_file());
}

#[test]
fn a_missing_script_is_named() {
    let (_tmp, root, models) = setup(OK_SCRIPT);
    fs::remove_file(root.join("tools/te_rename.py")).unwrap();
    let err = convert::image_text_encoder(&py(), &root, &models).unwrap_err();
    assert!(err.contains("te_rename.py"), "{err}");
    assert!(models.join("qwen-image-2.1/text_encoder").is_dir());
}
