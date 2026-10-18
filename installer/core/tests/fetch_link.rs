//! #342: `--source` on Linux. A file on the destination's file system is
//! hard-linked after its sha256 matched (never copied, never written); a source
//! may mirror the remote layout or be a models tree (`crow-stack/`); a source
//! that holds the Image Stack's converted text encoder skips the convert.
#![cfg(unix)]

mod fetch_support;

use crowsetup_core::api::{FileKind, Package, Packages, Selection, Source};
use crowsetup_core::fetch::{FetchError, FetchOptions, download};
use crowsetup_core::run::{RealSteps, Steps, local_rel_for, models_root};
use crowsetup_core::stack::Stack;
use crowsetup_core::state::StateStore;
use fetch_support::*;
use std::fs;
use std::os::unix::fs::MetadataExt;
use std::path::Path;
use std::sync::atomic::AtomicBool;

fn linking(source: Source) -> FetchOptions {
    FetchOptions { link_local: true, ..opts(source) }
}

fn ino(p: &Path) -> u64 {
    fs::metadata(p).unwrap().ino()
}

#[test]
fn production_links_on_linux() {
    assert!(FetchOptions::production(Source::Remote).link_local);
}

#[test]
fn a_same_file_system_source_is_linked_not_copied() {
    let content = data(300_000, 51);
    let tmp = tempfile::tempdir().unwrap();
    let src = tmp.path().join("src");
    let dest = tmp.path().join("install/models/m.bin");
    let job = job("m", "https://unused.invalid/m.bin", &dest, &content);
    fs::create_dir_all(src.join("repo")).unwrap();
    fs::write(src.join(&job.local_rel), &content).unwrap();
    let mut st = StateStore::load(&tmp.path().join("state.json")).unwrap();
    let mut ev = Vec::new();
    download(&job, &mut st, &linking(Source::Local(src.clone())), &mut |e| ev.push(e), &AtomicBool::new(false)).unwrap();
    assert_eq!(ino(&dest), ino(&src.join(&job.local_rel)), "not a hard link");
    assert_eq!(fs::read(src.join(&job.local_rel)).unwrap(), content, "the source changed");
    assert!(!part_of(&dest).exists());
    assert!(verified(&ev, "m") && checking(&ev) == Some(content.len() as u64));
    assert!(!ev.iter().any(|e| matches!(e, crowsetup_core::api::Event::FileStarted { .. })), "nothing was copied");
    assert!(StateStore::load(&st.path).unwrap().files["m"].verified);
}

#[test]
fn a_symlinked_source_tree_links_the_file_not_the_symlink() {
    let content = data(10_000, 52);
    let tmp = tempfile::tempdir().unwrap();
    let real = tmp.path().join("real");
    fs::create_dir_all(&real).unwrap();
    fs::write(real.join("m.bin"), &content).unwrap();
    let src = tmp.path().join("mirror");
    fs::create_dir_all(&src).unwrap();
    std::os::unix::fs::symlink(&real, src.join("repo")).unwrap();
    let dest = tmp.path().join("install/m.bin");
    let job = job("m", "https://unused.invalid/m.bin", &dest, &content);
    let mut st = StateStore::load(&tmp.path().join("state.json")).unwrap();
    download(&job, &mut st, &linking(Source::Local(src)), &mut |_| {}, &AtomicBool::new(false)).unwrap();
    assert!(fs::symlink_metadata(&dest).unwrap().file_type().is_file());
    assert_eq!(ino(&dest), ino(&real.join("m.bin")));
}

#[test]
fn wrong_source_bytes_fall_back_to_the_copy_and_its_mismatch() {
    let good = data(10_000, 53);
    let bad = data(10_000, 54);
    let tmp = tempfile::tempdir().unwrap();
    let src = tmp.path().join("src");
    let dest = tmp.path().join("m.bin");
    let job = job("m", "https://unused.invalid/m.bin", &dest, &good);
    fs::create_dir_all(src.join("repo")).unwrap();
    fs::write(src.join(&job.local_rel), &bad).unwrap();
    let mut st = StateStore::load(&tmp.path().join("state.json")).unwrap();
    let mut ev = Vec::new();
    let r = download(&job, &mut st, &linking(Source::Local(src.clone())), &mut |e| ev.push(e), &AtomicBool::new(false));
    assert!(matches!(r, Err(FetchError::Mismatch { .. })), "{r:?}");
    assert_eq!(retries(&ev).len(), 1, "the copy's one refetch, as without linking");
    assert!(!dest.exists());
    assert_eq!(fs::read(src.join(&job.local_rel)).unwrap(), bad, "the source changed");
}

#[test]
fn a_part_already_begun_continues_as_a_copy() {
    let content = data(50_000, 55);
    let tmp = tempfile::tempdir().unwrap();
    let src = tmp.path().join("src");
    let dest = tmp.path().join("m.bin");
    let job = job("m", "https://unused.invalid/m.bin", &dest, &content);
    fs::create_dir_all(src.join("repo")).unwrap();
    fs::write(src.join(&job.local_rel), &content).unwrap();
    fs::write(part_of(&dest), &content[..1000]).unwrap();
    let mut st = StateStore::load(&tmp.path().join("state.json")).unwrap();
    download(&job, &mut st, &linking(Source::Local(src.clone())), &mut |_| {}, &AtomicBool::new(false)).unwrap();
    assert_eq!(fs::read(&dest).unwrap(), content);
    assert_ne!(ino(&dest), ino(&src.join(&job.local_rel)));
}

fn packages() -> Packages {
    let p = |a: &str| Package { asset: a.into(), url: format!("https://unused.invalid/{a}"), bytes: 1, sha256: "0".repeat(64), version: "1".into() };
    Packages { crow: p("crow-1-linux-x64.tar.gz"), engine: p("crow-nest-engine-1-linux-x64.tar.gz") }
}

#[test]
fn a_models_tree_is_a_source_too() {
    let tmp = tempfile::tempdir().unwrap();
    let models = tmp.path().join("crow/models");
    let src = tmp.path().join("crow-stack");
    fs::create_dir_all(src.join("Qwen3.8-27B-CNQ4.5")).unwrap();
    let content = data(20_000, 56);
    fs::write(src.join("Qwen3.8-27B-CNQ4.5/tokenizer.json"), &content).unwrap();
    let mut j = job("27b-tokenizer", "https://unused.invalid/t", &models.join("Qwen3.8-27B-CNQ4.5/tokenizer.json"), &content);
    j.local_rel = "nibor1896/Qwen3.8-27B-CNQ4.5/tokenizer.json".into();
    assert_eq!(local_rel_for(&src, &j, &models), "Qwen3.8-27B-CNQ4.5/tokenizer.json");
    // the remote layout wins where both exist
    fs::create_dir_all(src.join("nibor1896/Qwen3.8-27B-CNQ4.5")).unwrap();
    fs::write(src.join(&j.local_rel), &content).unwrap();
    assert_eq!(local_rel_for(&src, &j, &models), j.local_rel);
    fs::remove_file(src.join(&j.local_rel)).unwrap();
    // neither: the remote layout is named in the error
    let mut k = j.clone();
    k.dest = models.join("elsewhere/x.json");
    assert_eq!(local_rel_for(&src, &k, &models), k.local_rel);

    // through the real steps: plan() sets the models root, download() links
    let mut steps = RealSteps::new(Source::Local(src.clone()), packages(), None, None);
    let sel = Selection { points: vec!["27b".into()], install_root: tmp.path().join("crow"), shortcut_dir: None };
    steps.plan(&sel).unwrap();
    assert_eq!(models_root(&sel.install_root), models);
    assert!(steps.costs_no_disk(&j), "a linkable file costs no disk");
    let mut st = StateStore::load(&tmp.path().join("state.json")).unwrap();
    steps.download(&j, &mut st, &mut |_| {}, &AtomicBool::new(false)).unwrap();
    assert_eq!(ino(&j.dest), ino(&src.join("Qwen3.8-27B-CNQ4.5/tokenizer.json")));

    let mut remote = RealSteps::new(Source::Remote, packages(), None, None);
    remote.plan(&sel).unwrap();
    assert!(!remote.costs_no_disk(&j));
}

/// The embedded stack with the Image Stack's derived outputs made small: four
/// shards checked by size, the index by size and sha256, as stack.json pins them.
fn small_stack(index: &[u8]) -> (Stack, Vec<(String, Vec<u8>)>) {
    let mut s = Stack::embedded();
    let d = &mut s.derived[0];
    let mut files = Vec::new();
    for (i, o) in d.outputs.iter_mut().enumerate() {
        let body = if o.sha256.is_some() { index.to_vec() } else { data(1000 + i, 60 + i as u32) };
        o.bytes = body.len() as u64;
        if o.sha256.is_some() {
            o.sha256 = Some(sha_hex(&body));
        }
        files.push((o.path.clone(), body));
    }
    (s, files)
}

#[test]
fn a_source_holding_the_converted_text_encoder_skips_the_convert() {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().join("crow");
    let src = tmp.path().join("crow-stack");
    let sdcli = src.join("qwen-image-2.1/text_encoder_sdcli");
    fs::create_dir_all(&sdcli).unwrap();
    let (stack, files) = small_stack(b"{\"weight_map\": {}}");
    for (name, body) in &files {
        fs::write(sdcli.join(name), body).unwrap();
    }
    let sel = Selection { points: vec!["image-stack".into()], install_root: root.clone(), shortcut_dir: None };
    let mut steps = RealSteps::new(Source::Local(src.clone()), packages(), None, None).with_stack(stack.clone());
    let plan = steps.plan(&sel).unwrap();
    let models = models_root(&root);
    assert!(steps.prefill_derived(&plan, &models));
    let dest = models.join("qwen-image-2.1/text_encoder_sdcli");
    for (name, body) in &files {
        assert_eq!(ino(&dest.join(name)), ino(&sdcli.join(name)), "{name} is not linked");
        assert_eq!(&fs::read(sdcli.join(name)).unwrap(), body, "the source changed");
    }
    // again: already in place, still true
    assert!(steps.prefill_derived(&plan, &models));

    // one shard of the wrong size: nothing is prefilled, nothing is left behind
    let root2 = tmp.path().join("crow2");
    fs::write(sdcli.join(&files[1].0), b"short").unwrap();
    let sel2 = Selection { install_root: root2.clone(), ..sel.clone() };
    let mut steps2 = RealSteps::new(Source::Local(src.clone()), packages(), None, None).with_stack(stack.clone());
    let plan2 = steps2.plan(&sel2).unwrap();
    assert!(!steps2.prefill_derived(&plan2, &models_root(&root2)));
    assert!(!models_root(&root2).join("qwen-image-2.1/text_encoder_sdcli").join(&files[0].0).exists());

    // a remote source never prefills
    let mut remote = RealSteps::new(Source::Remote, packages(), None, None).with_stack(stack);
    let plan3 = remote.plan(&sel2).unwrap();
    assert!(!remote.prefill_derived(&plan3, &models_root(&root2)));
}

#[test]
fn package_source_packages_are_linked_too() {
    let tmp = tempfile::tempdir().unwrap();
    let pk = tmp.path().join("packs");
    fs::create_dir_all(&pk).unwrap();
    let body = data(5000, 70);
    let asset = "crow-1-linux-x64.tar.gz";
    fs::write(pk.join(asset), &body).unwrap();
    let mut pkgs = packages();
    pkgs.crow.bytes = body.len() as u64;
    pkgs.crow.sha256 = sha_hex(&body);
    let mut steps = RealSteps::new(Source::Remote, pkgs, None, None).with_package_source(Some(pk.clone()));
    let sel = Selection { points: vec!["27b".into()], install_root: tmp.path().join("crow"), shortcut_dir: None };
    let plan = steps.plan(&sel).unwrap();
    let crow = plan.jobs.iter().find(|j| j.kind == FileKind::CrowPackage).unwrap().clone();
    assert!(steps.costs_no_disk(&crow));
    let mut st = StateStore::load(&tmp.path().join("state.json")).unwrap();
    steps.download(&crow, &mut st, &mut |_| {}, &AtomicBool::new(false)).unwrap();
    assert_eq!(ino(&crow.dest), ino(&pk.join(asset)));
}
