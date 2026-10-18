//! T2: selection -> deduplicated fetch list, smallest first, with disk need.
//!
//! Order: Crow's package, the engine package, the Crow-wide files (the dictation
//! model, smallest first), then the model files of the selected points, smallest
//! first (ties by id). A file several points use is one job whose `points` lists
//! the selected ones in stack.json order. Packages and Crow-wide files serve no
//! single point: their `points` is empty.
//!
//! URLs are always pinned (`resolve/<revision>`, never `main`). A `mirror-pending`
//! file has no revision in our repo yet (the upload moves it), so its `url` is the
//! pinned upstream `source` URL (Hugging Face or raw GitHub) while `local_rel`
//! stays the planned `<repo>/<path>` in our repo, the layout `--source` mirrors.
//! When the mirror is uploaded, stack.json flips the file to `published` with a
//! revision and the URL follows; no runtime fallback is needed for that.
//! An `upload-pending` file (#365) has neither: its `url` stays empty, a local
//! `--source` supplies it, and a download refuses it by name (fetch.rs).
//!
//! `disk_bytes` is what stays on disk: download + derived - the derived entries'
//! inputs, which the convert step deletes (#196 phase 2 design; no shipped point
//! derives a file since #403). The peak during the conversion is higher by those
//! inputs; preflight checks each point's peak.

use crate::api::{DerivedJob, FileJob, FileKind, Package, Packages, Plan, Selection};
use crate::stack::{Stack, StackFile, Status, resolve_path};
use std::collections::BTreeSet;
use std::path::Path;

/// Where the release zips land before the install steps unpack them.
pub fn packages_dir(install_root: &Path) -> std::path::PathBuf {
    install_root.join("setup").join("downloads")
}

/// `models_root` is `${MODELS}` (`<install>/models` unless overridden).
/// Crow's package and the engine package come first in the plan.
pub fn plan(stack: &Stack, sel: &Selection, models_root: &Path, packages: &Packages) -> Result<Plan, String> {
    let install = sel.install_root.as_path();
    if let Some(bad) = sel.points.iter().find(|p| stack.point(p).is_none()) {
        return Err(format!("unknown point {bad:?}"));
    }
    // selected points in stack.json order
    let selected: Vec<_> = stack.points.iter().filter(|p| sel.points.contains(&p.id)).collect();

    let mut jobs = vec![
        package_job("crow-package", FileKind::CrowPackage, &packages.crow, install),
        package_job("engine-package", FileKind::EnginePackage, &packages.engine, install),
    ];

    let mut crow: Vec<FileJob> = stack
        .crow_files
        .iter()
        .map(|f| file_job(f, FileKind::Whisper, Vec::new(), install, models_root))
        .collect::<Result<_, _>>()?;
    crow.sort_by(|a, b| (a.bytes, &a.id).cmp(&(b.bytes, &b.id)));
    jobs.extend(crow);

    let mut ids = BTreeSet::new();
    for p in &selected {
        ids.extend(p.files.iter().map(String::as_str));
    }
    let mut models = Vec::new();
    for id in ids {
        let f = stack.file(id).ok_or_else(|| format!("file {id} is not declared"))?;
        let points = selected.iter().filter(|p| p.files.iter().any(|x| x == id)).map(|p| p.id.clone()).collect();
        models.push(file_job(f, FileKind::Model, points, install, models_root)?);
    }
    models.sort_by(|a, b| (a.bytes, &a.id).cmp(&(b.bytes, &b.id)));
    jobs.extend(models);

    let mut derived = Vec::new();
    let mut deleted = BTreeSet::new();
    for p in &selected {
        for did in &p.derived {
            if derived.iter().any(|d: &DerivedJob| &d.id == did) {
                continue;
            }
            let d = stack.derived_entry(did).ok_or_else(|| format!("derived {did} is not declared"))?;
            let points = selected.iter().filter(|q| q.derived.contains(did)).map(|q| q.id.clone()).collect();
            derived.push(DerivedJob {
                id: d.id.clone(),
                dest: resolve_path(&d.dest, install, models_root)?,
                bytes: d.bytes,
                points,
                inputs: d.inputs.clone(),
            });
            deleted.extend(d.inputs.iter().map(String::as_str));
        }
    }

    let download_bytes: u64 = jobs.iter().map(|j| j.bytes).sum();
    let derived_bytes: u64 = derived.iter().map(|d| d.bytes).sum();
    let deleted_bytes: u64 = deleted.iter().filter_map(|id| stack.file(id)).map(|f| f.bytes).sum();
    // #340: an unpacked runtime stays, its archive is deleted (crate::runtime).
    let plat = if cfg!(windows) { "windows" } else { "linux" };
    let (mut runtime_bytes, mut archives) = (0u64, BTreeSet::new());
    for p in &selected {
        let rt = stack.raw["points"].as_array().into_iter().flatten()
            .find(|q| q["id"] == p.id.as_str()).map(|q| &q["video_server"]["runtime"][plat]);
        if let Some(fid) = rt.and_then(|rt| rt["file"].as_str())
            && archives.insert(fid.to_string())
        {
            runtime_bytes += rt.and_then(|rt| rt["bytes"].as_u64()).unwrap_or(0);
        }
    }
    let archive_bytes: u64 = archives.iter().filter_map(|id| stack.file(id)).map(|f| f.bytes).sum();
    let disk_bytes = download_bytes + derived_bytes + runtime_bytes - deleted_bytes - archive_bytes;
    Ok(Plan { jobs, derived, download_bytes, disk_bytes })
}

fn package_job(id: &str, kind: FileKind, p: &Package, install: &Path) -> FileJob {
    FileJob {
        id: id.to_string(),
        kind,
        url: p.url.clone(),
        local_rel: format!("releases/{}", p.asset),
        dest: packages_dir(install).join(&p.asset),
        bytes: p.bytes,
        sha256: p.sha256.to_ascii_lowercase(),
        points: Vec::new(),
    }
}

fn file_job(f: &StackFile, kind: FileKind, points: Vec<String>, install: &Path, models: &Path) -> Result<FileJob, String> {
    let url = match (f.status, &f.revision, &f.source) {
        (Status::MirrorPending, _, Some(src)) => src.url(),
        (Status::MirrorPending, _, None) => return Err(format!("file {} is mirror-pending without a source", f.id)),
        (Status::UploadPending, _, _) => String::new(),
        (_, Some(rev), _) => f.url(rev)?,
        (_, None, _) => return Err(format!("file {} has no pinned revision", f.id)),
    };
    Ok(FileJob {
        id: f.id.clone(),
        kind,
        url,
        local_rel: format!("{}/{}", f.repo, f.path),
        dest: resolve_path(&f.dest, install, models)?,
        bytes: f.bytes,
        sha256: f.sha256.to_ascii_lowercase(),
        points,
    })
}
