//! #340: the video server's runtime -- ComfyUI's portable 7z -- unpacked into
//! its folder, the top folder stripped, the model paths written beside main.py.

use crowsetup_core::runtime::{self, ModelPaths, RuntimeJob};
use sevenz_rust2::{ArchiveEntry, ArchiveWriter};
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;

fn archive(dir: &Path, name: &str, entries: &[(&str, Option<&[u8]>)]) -> PathBuf {
    let path = dir.join(name);
    let mut w = ArchiveWriter::create(&path).unwrap();
    for (n, data) in entries {
        match data {
            Some(d) => {
                w.push_archive_entry(ArchiveEntry::new_file(n), Some(*d)).unwrap();
            }
            None => {
                w.push_archive_entry::<&[u8]>(ArchiveEntry::new_directory(n), None).unwrap();
            }
        }
    }
    w.finish().unwrap();
    path
}

fn job(tmp: &Path, archive: PathBuf, sha: &str) -> RuntimeJob {
    RuntimeJob {
        point: "media-stack".into(),
        file_id: "comfyui-portable".into(),
        archive,
        sha256: sha.into(),
        dir: tmp.join("install").join("comfyui"),
        strip: "ComfyUI_windows_portable".into(),
        model_paths: Some(ModelPaths {
            file: "ComfyUI/extra_model_paths.yaml".into(),
            base: tmp.join("models").join("ltx-2.5"),
            folders: vec!["diffusion_models".into(), "text_encoders".into(), "vae".into()],
        }),
        bytes: 0,
    }
}

const PORTABLE: &[(&str, Option<&[u8]>)] = &[
    ("ComfyUI_windows_portable", None),
    ("ComfyUI_windows_portable/ComfyUI", None),
    ("ComfyUI_windows_portable/ComfyUI/main.py", Some(b"print('comfy')\n")),
    ("ComfyUI_windows_portable/python_embeded/python.exe", Some(b"MZ fake")),
    ("ComfyUI_windows_portable/README_VERY_IMPORTANT.txt", Some(b"run run_nvidia_gpu.bat")),
];

fn unpack(j: &RuntimeJob) -> Result<String, String> {
    runtime::unpack(j, &AtomicBool::new(false), &mut |_, _| {})
}

#[test]
fn the_top_folder_is_stripped_and_the_model_paths_land_beside_main_py() {
    let tmp = tempfile::tempdir().unwrap();
    let a = archive(tmp.path(), "c.7z", PORTABLE);
    let j = job(tmp.path(), a, &"ab".repeat(32));
    let said = unpack(&j).unwrap();
    assert!(said.contains("3 files"), "{said}");
    assert_eq!(std::fs::read(j.dir.join("ComfyUI/main.py")).unwrap(), b"print('comfy')\n");
    assert!(j.dir.join("python_embeded/python.exe").is_file());
    assert!(!j.dir.join("ComfyUI_windows_portable").exists());
    let yaml = std::fs::read_to_string(j.dir.join("ComfyUI/extra_model_paths.yaml")).unwrap();
    let base = tmp.path().join("models").join("ltx-2.5");
    assert!(yaml.contains(&format!("base_path: '{}'", base.display())), "{yaml}");
    for f in ["diffusion_models: diffusion_models", "text_encoders: text_encoders", "vae: vae"] {
        assert!(yaml.contains(f), "{yaml}");
    }
    assert!(runtime::is_current(&j));
    assert!(!tmp.path().join("install").join("comfyui.part").exists());
}

#[test]
fn the_same_archive_again_is_up_to_date_and_a_new_one_replaces_the_folder() {
    let tmp = tempfile::tempdir().unwrap();
    let a = archive(tmp.path(), "c.7z", PORTABLE);
    let j = job(tmp.path(), a, &"ab".repeat(32));
    unpack(&j).unwrap();
    std::fs::write(j.dir.join("stray.txt"), "left by a run").unwrap();
    assert!(unpack(&j).unwrap().contains("up to date"));
    assert!(j.dir.join("stray.txt").exists(), "an up-to-date runtime is not touched");
    let b = archive(tmp.path(), "d.7z", &[("ComfyUI_windows_portable/ComfyUI/main.py", Some(b"v2"))]);
    let j2 = RuntimeJob { archive: b, sha256: "cd".repeat(32), ..job(tmp.path(), PathBuf::new(), "") };
    unpack(&j2).unwrap();
    assert_eq!(std::fs::read(j2.dir.join("ComfyUI/main.py")).unwrap(), b"v2");
    assert!(!j2.dir.join("stray.txt").exists(), "the old runtime is gone, not merged");
    assert!(!j2.dir.join("python_embeded").exists());
    assert!(!tmp.path().join("install").join("comfyui.old").exists());
}

#[test]
fn an_entry_outside_the_top_folder_or_climbing_out_is_refused_and_nothing_lands() {
    let tmp = tempfile::tempdir().unwrap();
    for (name, entries) in [
        ("outside.7z", vec![("ComfyUI_windows_portable/ComfyUI/main.py", Some(&b"x"[..])), ("elsewhere/evil.exe", Some(&b"x"[..]))]),
        ("climb.7z", vec![("ComfyUI_windows_portable/../evil.exe", Some(&b"x"[..]))]),
    ] {
        let a = archive(tmp.path(), name, &entries);
        let j = job(tmp.path(), a, &"ef".repeat(32));
        let err = unpack(&j).unwrap_err();
        assert!(err.contains("evil.exe"), "{name}: {err}");
        assert!(!j.dir.exists(), "{name}: nothing may land");
        assert!(!tmp.path().join("evil.exe").exists());
        assert!(!tmp.path().join("install").join("evil.exe").exists());
    }
}

#[test]
fn a_cancel_keeps_the_runtime_that_was_there() {
    let tmp = tempfile::tempdir().unwrap();
    let a = archive(tmp.path(), "c.7z", PORTABLE);
    let j = job(tmp.path(), a, &"ab".repeat(32));
    unpack(&j).unwrap();
    let b = archive(tmp.path(), "d.7z", &[("ComfyUI_windows_portable/ComfyUI/main.py", Some(b"v2"))]);
    let j2 = RuntimeJob { archive: b, sha256: "cd".repeat(32), ..job(tmp.path(), PathBuf::new(), "") };
    let err = runtime::unpack(&j2, &AtomicBool::new(true), &mut |_, _| {}).unwrap_err();
    assert!(err.contains("cancelled"), "{err}");
    assert_eq!(std::fs::read(j.dir.join("ComfyUI/main.py")).unwrap(), b"print('comfy')\n");
    assert!(runtime::is_current(&j));
}

#[test]
fn a_quote_in_the_models_path_is_doubled_for_yaml() {
    let mp = ModelPaths { file: "x.yaml".into(), base: PathBuf::from("D:/Ann's models/ltx"), folders: vec!["vae".into()] };
    let y = runtime::model_paths_yaml(&mp);
    assert!(y.contains("base_path: 'D:/Ann''s models/ltx'"), "{y}");
}

/// The real archive: `CROW_COMFY_7Z=<ComfyUI_windows_portable_nvidia.7z>
/// cargo test --test runtime_unpack -- --ignored`. v0.38.0 measured
/// 2026-10-03: 58,293 files, 4,384,588,275 B, 40.9 s on one thread.
#[test]
#[ignore]
fn the_real_comfyui_archive() {
    let a = PathBuf::from(std::env::var("CROW_COMFY_7Z").expect("CROW_COMFY_7Z"));
    let tmp = tempfile::tempdir().unwrap();
    let j = job(tmp.path(), a, &"00".repeat(32));
    let said = unpack(&j).unwrap();
    eprintln!("{said}");
    for f in ["ComfyUI/main.py", "python_embeded/python.exe", "run_nvidia_gpu.bat", "ComfyUI/extra_model_paths.yaml"] {
        assert!(j.dir.join(f).is_file(), "{f}");
    }
}

#[test]
fn the_jobs_come_from_the_selected_points_runtime_for_this_platform() {
    use crowsetup_core::api::Selection;
    use crowsetup_core::stack::Stack;
    let mut doc = Stack::embedded().raw.clone();
    let mut file = doc["files"].as_array().unwrap().iter().find(|f| f["id"] == "qi-vae").unwrap().clone();
    file["id"] = "comfyui-portable".into();
    file["role"] = "runtime".into();
    file["dest"] = "${INSTALL}/setup/downloads/ComfyUI_windows_portable_nvidia.7z".into();
    doc["files"].as_array_mut().unwrap().push(file);
    let rt = serde_json::json!({
        "file": "comfyui-portable", "dir": "${INSTALL}/comfyui", "strip": "ComfyUI_windows_portable",
        "model_paths": {"file": "ComfyUI/extra_model_paths.yaml", "base": "${MODELS}/ltx-2.5",
                        "folders": ["diffusion_models", "vae"]}});
    let pt = doc["points"].as_array_mut().unwrap().iter_mut().find(|p| p["id"] == "27b").unwrap();
    pt["files"].as_array_mut().unwrap().push("comfyui-portable".into());
    pt["video_server"] = serde_json::json!({"runtime": {"windows": rt.clone(), "linux": rt}});
    let s = Stack::parse(&doc.to_string()).unwrap();
    let root = PathBuf::from(r"C:\Crow");
    let models = root.join("models");
    let sel = |pts: &[&str]| Selection { points: pts.iter().map(|p| p.to_string()).collect(), install_root: root.clone(), shortcut_dir: None };
    assert!(runtime::jobs(&s, &sel(&["flash-next"]), &models).is_empty());
    let jobs = runtime::jobs(&s, &sel(&["27b", "image-stack"]), &models);
    assert_eq!(jobs.len(), 1, "one runtime, even for two points");
    let j = &jobs[0];
    assert_eq!((j.point.as_str(), j.file_id.as_str()), ("27b", "comfyui-portable"));
    assert_eq!(j.archive, root.join("setup").join("downloads").join("ComfyUI_windows_portable_nvidia.7z"));
    assert_eq!(j.dir, root.join("comfyui"));
    assert_eq!(j.sha256, s.file("comfyui-portable").unwrap().sha256);
    let mp = j.model_paths.as_ref().unwrap();
    assert_eq!((mp.base.clone(), mp.folders.clone()), (models.join("ltx-2.5"), vec!["diffusion_models".to_string(), "vae".to_string()]));
}
