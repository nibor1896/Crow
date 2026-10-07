//! T2: selection -> fetch list. Every number is checked twice: as a literal and
//! against stack.json's own `bytes` blocks, so a manifest change that forgets the
//! plan (or the other way round) goes red here.

use crowsetup_core::api::{FileKind, Package, Packages, Selection};
use crowsetup_core::plan::plan;
use crowsetup_core::stack::{Stack, Status};
use std::path::{Path, PathBuf};

const CROW_PKG: u64 = 41_000_000;
const ENGINE_PKG: u64 = 310_000_000;
/// config.json + vocabulary.txt + tokenizer.json + model.bin of faster-whisper-small.
const WHISPER: u64 = 486_212_372;
const PKGS: u64 = CROW_PKG + ENGINE_PKG;
/// The upstream text_encoder/ (index + 4 shards), deleted after te_rename.
const TEXT_ENCODER: u64 = 17_534_407_283;
const SDCLI: u64 = 17_534_419_188;

fn packages() -> Packages {
    Packages {
        crow: Package {
            asset: "crow-3.0.0-win-x64.zip".into(),
            url: "https://github.com/nibor1896/Crow/releases/download/v3.0.0/crow-3.0.0-win-x64.zip".into(),
            bytes: CROW_PKG,
            sha256: "AA".repeat(32),
            version: "3.0.0".into(),
        },
        engine: Package {
            asset: "crow-nest-engine-0.9.0-win-x64.zip".into(),
            url: "https://github.com/nibor1896/crow-nest/releases/download/v0.9.0/crow-nest-engine-0.9.0-win-x64.zip".into(),
            bytes: ENGINE_PKG,
            sha256: "bb".repeat(32),
            version: "0.9.0".into(),
        },
    }
}

fn sel(points: &[&str], install: &Path) -> Selection {
    Selection { points: points.iter().map(|s| s.to_string()).collect(), install_root: install.to_path_buf(), shortcut_dir: None }
}

fn default_root() -> PathBuf {
    PathBuf::from(r"C:\Crow")
}

fn plan_for(points: &[&str]) -> crowsetup_core::api::Plan {
    let root = default_root();
    plan(&Stack::embedded(), &sel(points, &root), &root.join("models"), &packages()).expect("plan")
}

fn point_files(id: &str) -> u64 {
    Stack::embedded().point(id).unwrap().bytes.files
}

fn ids(p: &crowsetup_core::api::Plan) -> Vec<&str> {
    p.jobs.iter().map(|j| j.id.as_str()).collect()
}

#[test]
fn flash_next_alone() {
    let p = plan_for(&["flash-next"]);
    assert_eq!(p.jobs.len(), 2 + 4 + 9);
    assert_eq!(point_files("flash-next"), 105_644_572_922);
    assert_eq!(p.download_bytes, PKGS + WHISPER + 105_644_572_922);
    assert_eq!(p.download_bytes, PKGS + WHISPER + point_files("flash-next"));
    assert_eq!(p.disk_bytes, p.download_bytes);
    assert!(p.derived.is_empty());
    assert_eq!(p.jobs.last().unwrap().id, "fn-cnq");
}

#[test]
fn twenty_seven_b_alone() {
    let p = plan_for(&["27b"]);
    assert_eq!(p.jobs.len(), 2 + 4 + 7);
    assert_eq!(p.download_bytes, PKGS + WHISPER + 18_784_665_622);
    assert_eq!(p.download_bytes, PKGS + WHISPER + point_files("27b"));
    assert_eq!(p.disk_bytes, p.download_bytes);
    assert!(p.derived.is_empty());
}

#[test]
fn image_stack_alone_derives_sdcli_and_drops_the_text_encoder() {
    let p = plan_for(&["image-stack"]);
    assert_eq!(p.jobs.len(), 2 + 4 + 17);
    assert_eq!(p.download_bytes, PKGS + WHISPER + 51_900_384_939);
    assert_eq!(p.download_bytes, PKGS + WHISPER + point_files("image-stack"));
    assert_eq!(p.derived.len(), 1);
    let d = &p.derived[0];
    assert_eq!(d.id, "qi-text-encoder-sdcli");
    assert_eq!(d.bytes, SDCLI);
    assert_eq!(d.bytes, Stack::embedded().point("image-stack").unwrap().bytes.derived);
    assert_eq!(d.points, vec!["image-stack".to_string()]);
    assert_eq!(d.dest, default_root().join("models").join("qwen-image-2.1").join("text_encoder_sdcli"));
    // download + derived - the upstream text_encoder/ deleted after conversion
    assert_eq!(p.disk_bytes, p.download_bytes + SDCLI - TEXT_ENCODER);
    assert_eq!(p.disk_bytes, PKGS + WHISPER + 51_900_384_939 + 11_905);
}

#[test]
fn twenty_seven_b_and_image_stack_share_the_27b_files() {
    let p = plan_for(&["27b", "image-stack"]);
    assert_eq!(p.jobs.len(), 2 + 4 + 17, "the seven 27B files are fetched once");
    assert_eq!(p.download_bytes, PKGS + WHISPER + point_files("image-stack"));
    let mut seen = std::collections::HashSet::new();
    assert!(p.jobs.iter().all(|j| seen.insert(j.id.clone())), "no id twice: {:?}", ids(&p));
    for id in ["27b-cnq", "27b-sidecar", "27b-mmproj", "27b-tokenizer", "27b-tokenizer-config", "27b-sha256sums", "27b-license"] {
        let j = p.jobs.iter().find(|j| j.id == id).unwrap();
        assert_eq!(j.points, vec!["27b".to_string(), "image-stack".to_string()], "{id}");
    }
    let qi = p.jobs.iter().find(|j| j.id == "qi-vae").unwrap();
    assert_eq!(qi.points, vec!["image-stack".to_string()]);
    assert_eq!(p.disk_bytes, p.download_bytes + SDCLI - TEXT_ENCODER);
}

#[test]
fn image_stack_alone_lists_only_itself_on_the_27b_files() {
    let p = plan_for(&["image-stack"]);
    let j = p.jobs.iter().find(|j| j.id == "27b-cnq").unwrap();
    assert_eq!(j.points, vec!["image-stack".to_string()]);
}

#[test]
fn all_three() {
    let p = plan_for(&["image-stack", "flash-next", "27b"]);
    assert_eq!(p.jobs.len(), 2 + 4 + 9 + 17);
    assert_eq!(p.download_bytes, PKGS + WHISPER + 105_644_572_922 + 51_900_384_939);
    assert_eq!(p.download_bytes, PKGS + WHISPER + point_files("flash-next") + point_files("image-stack"));
    assert_eq!(p.disk_bytes, p.download_bytes + SDCLI - TEXT_ENCODER);
    let sum: u64 = p.jobs.iter().map(|j| j.bytes).sum();
    assert_eq!(sum, p.download_bytes);
    // points are listed in stack.json order, not selection order
    let j = p.jobs.iter().find(|j| j.id == "27b-mmproj").unwrap();
    assert_eq!(j.points, vec!["27b".to_string(), "image-stack".to_string()]);
}

#[test]
fn no_point_is_crow_alone() {
    let p = plan_for(&[]);
    assert_eq!(ids(&p), vec!["crow-package", "engine-package", "whisper-config", "whisper-vocabulary", "whisper-tokenizer", "whisper-model"]);
    assert_eq!(p.download_bytes, PKGS + WHISPER);
    assert_eq!(p.disk_bytes, PKGS + WHISPER);
}

#[test]
fn order_packages_then_whisper_then_models_smallest_first() {
    let p = plan_for(&["27b", "image-stack", "flash-next"]);
    assert_eq!(p.jobs[0].kind, FileKind::CrowPackage);
    assert_eq!(p.jobs[1].kind, FileKind::EnginePackage);
    assert_eq!(&ids(&p)[2..6], &["whisper-config", "whisper-vocabulary", "whisper-tokenizer", "whisper-model"]);
    assert!(p.jobs[2..6].iter().all(|j| j.kind == FileKind::Whisper));
    let models = &p.jobs[6..];
    assert!(models.iter().all(|j| j.kind == FileKind::Model));
    assert!(models.windows(2).all(|w| (w[0].bytes, &w[0].id) <= (w[1].bytes, &w[1].id)), "{:?}", ids(&p));
    assert_eq!(models.first().unwrap().id, "27b-sha256sums");
    assert_eq!(models.first().unwrap().bytes, 266);
    assert_eq!(models.last().unwrap().id, "fn-cnq");
    // equal sizes break by id: the two tokenizer.json copies
    let a = ids(&p).iter().position(|i| *i == "27b-tokenizer").unwrap();
    let b = ids(&p).iter().position(|i| *i == "fn-tokenizer").unwrap();
    assert_eq!(b, a + 1);
}

#[test]
fn packages_are_jobs_with_release_paths() {
    let root = PathBuf::from(r"D:\Apps\CrowTest");
    let p = plan(&Stack::embedded(), &sel(&["27b"], &root), &root.join("models"), &packages()).unwrap();
    let c = &p.jobs[0];
    assert_eq!(c.id, "crow-package");
    assert_eq!(c.url, packages().crow.url);
    assert_eq!(c.local_rel, "releases/crow-3.0.0-win-x64.zip");
    assert_eq!(c.dest, root.join("setup").join("downloads").join("crow-3.0.0-win-x64.zip"));
    assert_eq!(c.bytes, CROW_PKG);
    assert_eq!(c.sha256, "aa".repeat(32), "sha256 is lower-cased");
    assert!(c.points.is_empty());
    let e = &p.jobs[1];
    assert_eq!(e.id, "engine-package");
    assert_eq!(e.local_rel, "releases/crow-nest-engine-0.9.0-win-x64.zip");
    assert_eq!(e.dest, root.join("setup").join("downloads").join("crow-nest-engine-0.9.0-win-x64.zip"));
}

#[test]
fn dest_resolution_with_a_non_default_install_and_models_root() {
    // built with join so the test holds on both platforms (#342)
    let install = PathBuf::from(r"D:\Apps\CrowTest");
    let models = PathBuf::from(r"E:\big\models");
    let p = plan(&Stack::embedded(), &sel(&["image-stack"], &install), &models, &packages()).unwrap();
    let dest = |id: &str| p.jobs.iter().find(|j| j.id == id).unwrap().dest.clone();
    let under = |root: &Path, parts: &[&str]| parts.iter().fold(root.to_path_buf(), |p, x| p.join(x));
    assert_eq!(dest("27b-cnq"), under(&models, &["Qwen3.8-27B-CNQ4.5", "Qwen3.8-27B-CNQ4.5.cnq"]));
    assert_eq!(
        dest("qi-transformer-1"),
        under(&models, &["qwen-image-2.1", "transformer", "diffusion_pytorch_model-00001-of-00002.safetensors"])
    );
    // ${INSTALL}, not ${MODELS}: crow_voice.py loads <crow>/models/whisper-small
    assert_eq!(dest("whisper-model"), under(&install, &["models", "whisper-small", "model.bin"]));
    assert_eq!(p.derived[0].dest, under(&models, &["qwen-image-2.1", "text_encoder_sdcli"]));
}

#[test]
fn urls_are_pinned_and_local_rel_is_repo_path() {
    let p = plan_for(&["flash-next", "image-stack"]);
    let job = |id: &str| p.jobs.iter().find(|j| j.id == id).unwrap().clone();
    assert!(p.jobs.iter().all(|j| !j.url.contains("/resolve/main/")));
    let cnq = job("fn-cnq");
    assert_eq!(
        cnq.url,
        "https://huggingface.co/nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M/resolve/3ebead456fbff1ceebe600fddc83cb13106b06ce/Qwen3.8-Flash-Next-CNQ4.5-M.cnq"
    );
    assert_eq!(cnq.local_rel, "nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M/Qwen3.8-Flash-Next-CNQ4.5-M.cnq");
    assert_eq!(cnq.sha256, "7c058e555667b1c3d8f7d804d4a3393ba3664161dd307305718d85e4f33646b7");
    let qi = job("qi-text-encoder-1");
    assert_eq!(
        qi.url,
        "https://huggingface.co/Qwen/Qwen-Image-2.1/resolve/d26bb61231c349cf6b7896fa83353113880e1ba3/text_encoder/model-00001-of-00004.safetensors"
    );
    assert_eq!(qi.local_rel, "Qwen/Qwen-Image-2.1/text_encoder/model-00001-of-00004.safetensors");
    let w = job("whisper-tokenizer");
    assert_eq!(
        w.url,
        "https://huggingface.co/Systran/faster-whisper-small/resolve/536b0662742c02347bc0e980a01041f333bce120/tokenizer.json"
    );
    assert_eq!(w.local_rel, "Systran/faster-whisper-small/tokenizer.json");
    assert!(w.points.is_empty());
}

#[test]
fn foreign_files_come_from_their_original_repo_and_our_hotset_from_ours() {
    // #340, the owner 2026-10-03: only our own work goes into our repos. The
    // projectors and tokenizers are fetched from unsloth and Qwen, under their
    // own repo path. The crow-nest hotset is ours: mirror-pending until its
    // upload on 2026-10-07 (#196), fetched from our repo since.
    let p = plan_for(&["flash-next", "27b"]);
    let job = |id: &str| p.jobs.iter().find(|j| j.id == id).unwrap().clone();
    let mm = job("27b-mmproj");
    assert_eq!(
        mm.url,
        "https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/4ca720788d1e01f1bff70c033e0d0028fd02e502/mmproj-F16.gguf"
    );
    assert_eq!(mm.local_rel, "unsloth/Qwen3.8-27B-GGUF/mmproj-F16.gguf");
    assert_eq!(mm.bytes, 927_607_488);
    let tok = job("fn-tokenizer");
    assert_eq!(
        tok.url,
        "https://huggingface.co/Qwen/Qwen3.8-Flash-Next/resolve/de4b8e4d43b917e7706784d8bb445c9af86a3540/tokenizer.json"
    );
    assert_eq!(tok.local_rel, "Qwen/Qwen3.8-Flash-Next/tokenizer.json");
    let hot = job("fn-hotsets-crow0924");
    assert_eq!(
        hot.url,
        "https://huggingface.co/nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M/resolve/ce0ddccda55b6092e12111ae9e9d65bb1f66a21b/hotsets-M-crow0924-n160.json"
    );
    assert_eq!(hot.local_rel, "nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M/hotsets-M-crow0924-n160.json");
    // every model file that is not in our repo is a foreign original
    let elsewhere: Vec<&str> = p.jobs.iter().filter(|j| !j.url.contains("/nibor1896/Qwen3.8-") && j.kind == FileKind::Model).map(|j| j.id.as_str()).collect();
    assert_eq!(elsewhere.len(), 6, "{elsewhere:?}");
    let s = Stack::embedded();
    let pending: Vec<&str> = s.files.iter().filter(|f| f.status == Status::MirrorPending).map(|f| f.id.as_str()).collect();
    assert!(pending.is_empty(), "{pending:?}");
    let (fnx, b27) = (s.point("flash-next").unwrap(), s.point("27b").unwrap());
    assert_eq!((fnx.bytes.mirror_pending, b27.bytes.mirror_pending), (0, 0));
    assert_eq!(fnx.bytes.upstream + b27.bytes.upstream, 916_868_415 - 37_167 + 940_434_736);
}

#[test]
fn unknown_point_is_an_error_and_a_repeated_one_is_not() {
    let root = default_root();
    let err = plan(&Stack::embedded(), &sel(&["9b"], &root), &root.join("models"), &packages()).unwrap_err();
    assert!(err.contains("9b"), "{err}");
    let p = plan_for(&["27b", "27b"]);
    assert_eq!(p.jobs.len(), 2 + 4 + 7);
    assert_eq!(p.jobs.iter().find(|j| j.id == "27b-cnq").unwrap().points, vec!["27b".to_string()]);
}

#[test]
fn embedded_stack_parses_with_its_crow_files() {
    let s = Stack::embedded();
    assert_eq!(s.points.iter().map(|p| p.id.as_str()).collect::<Vec<_>>(), ["flash-next", "27b", "image-stack", "media-stack"]);
    assert_eq!(s.files.len(), 36);
    assert_eq!(s.crow_files.len(), 4);
    assert_eq!(s.crow_files.iter().map(|f| f.bytes).sum::<u64>(), WHISPER);
    assert!(Stack::parse("{").is_err());
    let mut raw = s.raw.clone();
    raw["points"][1]["files"].as_array_mut().unwrap().push("27b-ghost".into());
    let err = Stack::parse(&raw.to_string()).unwrap_err();
    assert!(err.contains("27b-ghost"), "{err}");
}

#[test]
fn an_upstream_file_is_fetched_from_its_host_and_a_gate_rides_on_the_job() {
    // #340: GitHub raw files, GitHub release assets and gated Hugging Face repos.
    let mut doc = Stack::embedded().raw.clone();
    for f in doc["files"].as_array_mut().unwrap() {
        match f["id"].as_str().unwrap() {
            "qi-license" => f["host"] = "github".into(),
            "qi-vae" => {
                f["host"] = "github-release".into();
                f["tag"] = "v0.38.0".into();
            }
            "qi-transformer-1" => f["gated"] = true.into(),
            _ => {}
        }
    }
    let s = Stack::parse(&doc.to_string()).expect("parse");
    let root = default_root();
    let p = plan(&s, &sel(&["image-stack"], &root), &root.join("models"), &packages()).expect("plan");
    let job = |id: &str| p.jobs.iter().find(|j| j.id == id).unwrap().clone();
    let (lic, vae, t1, t2) = (job("qi-license"), job("qi-vae"), job("qi-transformer-1"), job("qi-transformer-2"));
    let f = |id: &str| s.file(id).unwrap().clone();
    assert_eq!(lic.url, format!("https://raw.githubusercontent.com/Qwen/Qwen-Image-2.1/{}/{}", f("qi-license").revision.unwrap(), f("qi-license").path));
    assert_eq!(vae.url, format!("https://github.com/Qwen/Qwen-Image-2.1/releases/download/v0.38.0/{}", f("qi-vae").path));
    assert!(t1.url.starts_with("https://huggingface.co/Qwen/Qwen-Image-2.1/resolve/"), "{}", t1.url);
    assert!(t2.url.starts_with("https://huggingface.co/"), "{}", t2.url);
    assert_eq!((f("qi-transformer-1").gated, f("qi-transformer-2").gated, f("qi-vae").gated), (true, false, false));
    assert_eq!(vae.local_rel, format!("Qwen/Qwen-Image-2.1/{}", f("qi-vae").path));
}

#[test]
fn an_unpacked_runtime_counts_on_disk_and_its_deleted_archive_does_not() {
    // #340: the archive is deleted once unpacked, like a convert input.
    let mut doc = Stack::embedded().raw.clone();
    let mut file = doc["files"].as_array().unwrap().iter().find(|f| f["id"] == "qi-vae").unwrap().clone();
    file["id"] = "comfyui-portable".into();
    file["role"] = "runtime".into();
    file["bytes"] = 1_994_326_521u64.into();
    file["dest"] = "${INSTALL}/setup/downloads/ComfyUI_windows_portable_nvidia.7z".into();
    doc["files"].as_array_mut().unwrap().push(file);
    let rt = serde_json::json!({"file": "comfyui-portable", "dir": "${INSTALL}/comfyui",
                                "strip": "ComfyUI_windows_portable", "bytes": 4_384_588_275u64});
    let pt = doc["points"].as_array_mut().unwrap().iter_mut().find(|p| p["id"] == "27b").unwrap();
    pt["files"].as_array_mut().unwrap().push("comfyui-portable".into());
    pt["video_server"] = serde_json::json!({"runtime": {"windows": rt.clone(), "linux": rt}});
    let s = Stack::parse(&doc.to_string()).unwrap();
    let root = default_root();
    let with = plan(&s, &sel(&["27b"], &root), &root.join("models"), &packages()).unwrap();
    let without = plan_for(&["27b"]);
    assert_eq!(with.download_bytes, without.download_bytes + 1_994_326_521);
    assert_eq!(with.disk_bytes, without.disk_bytes + 4_384_588_275);
}
