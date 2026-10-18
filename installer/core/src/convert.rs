//! T3: run tools/te_rename.py for the image stack, then delete text_encoder/.
//!
//! `te_rename.py <models>/qwen-image-2.1/text_encoder <models>/qwen-image-2.1/text_encoder_sdcli`
//! (exit 0: every shard and the index written and verified). Only then is
//! `text_encoder/` (17.5 GB) deleted: the owner's decision, checked 2026-10-01 --
//! nothing but stack.json's download list and te_rename.py reads it. On failure
//! it stays, so a rerun can convert again without downloading it again.
//! A rerun after the delete finds `text_encoder/` gone and the output index in
//! place (te_rename writes the index last) and is done.

use crate::python::{output_tail, quiet, PythonInfo};
use std::fs;
use std::path::Path;

pub fn image_text_encoder(py: &PythonInfo, install_root: &Path, models_root: &Path) -> Result<(), String> {
    let base = models_root.join("qwen-image-2.1");
    let src = base.join("text_encoder");
    let dst = base.join("text_encoder_sdcli");
    let index = dst.join("model.safetensors.index.json");
    if !src.exists() && index.is_file() {
        return Ok(());
    }
    let script = install_root.join("tools").join("te_rename.py");
    if !script.is_file() {
        return Err(format!("{} is missing from the install; text_encoder/ was kept", script.display()));
    }
    let out = quiet(&py.exe)
        .arg(&script)
        .arg(&src)
        .arg(&dst)
        .output()
        .map_err(|e| format!("cannot run {}: {e}", script.display()))?;
    if !out.status.success() {
        return Err(format!(
            "te_rename.py failed ({}): {}; text_encoder/ was kept",
            out.status,
            output_tail(&out, 4)
        ));
    }
    if !index.is_file() {
        return Err(format!("te_rename.py exited 0 but {} is not there; text_encoder/ was kept", index.display()));
    }
    fs::remove_dir_all(&src).map_err(|e| format!("text_encoder_sdcli/ is built, but {} could not be deleted: {e}", src.display()))
}
