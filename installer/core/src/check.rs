//! T3: the check step. Resolves every selected point exactly like the boot
//! menu (`crow_boot` plan) and verifies files, sizes, sha and that the binaries start.
//!
//! The plan is not re-derived here: `cli/crow_boot.py --plan <point> --json`
//! prints what the menu itself would start (the same `plan_point` and the same
//! placeholder resolution), so the installer checks exactly what the boot menu
//! will use. Then:
//!
//! * every file of the point exists with its size. A file that is an INPUT of a
//!   derived job (the Image Stack's `text_encoder/`, consumed and deleted by the
//!   convert step) is not asked for; the derived outputs are, by size, and by
//!   sha256 where stack.json pins one.
//! * sha256 is computed only for files the run's state (`<root>/setup/state.json`,
//!   T1's `StateStore`) does not already mark `verified`. Those were hashed once
//!   on download, before their rename; hashing up to 105 GB a second time would
//!   cost minutes for nothing. The size is still compared for every file.
//! * the engine starts: crow-nest's serve has no `--help` (`serve.rs`
//!   `parse_args` exits 2 on an argument it does not know, printing
//!   `[serve] --help needs a value (usage: serve [--port <n>] [--slot-save-path <dir>])`),
//!   so `serve.exe --help` counts as started when it exits 2 with that usage (or
//!   exits 0). A missing DLL ends a process before `main` with an NTSTATUS exit
//!   code (0xC0000135) and no output, which is exactly what this tells apart.
//!   For the Image Stack `sd-server.exe --help` must exit 0.
//! * Linux (#342): a missing library ends the process with the loader's
//!   "error while loading shared libraries" (exit 127), which the same rules
//!   report. serve runs with the plan's own env; sd-server with
//!   `LD_LIBRARY_PATH=<root>/cuda/lib`, exactly what crow_core's
//!   `_image_server_env` gives it at start.

use crate::python::{output_tail, quiet, PythonInfo};
use crate::state::StateStore;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::{Duration, Instant};

#[derive(Debug, Clone, PartialEq, serde::Deserialize)]
pub struct PlanServer {
    pub binary: PathBuf,
    #[serde(default)]
    pub argv: Vec<String>,
    #[serde(default)]
    pub cwd: Option<PathBuf>,
    #[serde(default)]
    pub env: BTreeMap<String, String>,
    pub port: u16,
    #[serde(default)]
    pub readiness: serde_json::Value,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize)]
pub struct PlanFile {
    pub id: String,
    pub dest: PathBuf,
    pub bytes: u64,
    pub sha256: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize)]
pub struct PlanOutput {
    pub dest: PathBuf,
    pub bytes: u64,
    pub sha256: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize)]
pub struct PlanDerived {
    pub id: String,
    pub dest: PathBuf,
    #[serde(default)]
    pub inputs: Vec<String>,
    #[serde(default)]
    pub outputs: Vec<PlanOutput>,
}

/// `crow_boot.py --plan <point> --json`, the parts the check reads.
#[derive(Debug, Clone, PartialEq, serde::Deserialize)]
pub struct BootPlan {
    pub point: String,
    pub serve: PlanServer,
    pub image: Option<PlanServer>,
    #[serde(default)]
    pub files: Vec<PlanFile>,
    #[serde(default)]
    pub derived: Vec<PlanDerived>,
    /// #340: the video server, of which the check reads only the program.
    #[serde(default)]
    pub video: Option<PlanVideo>,
    /// #348: file ids the runtime step unpacks and deletes (the ComfyUI 7z).
    #[serde(default)]
    pub runtime_archives: Vec<String>,
}

/// The part of `--plan`'s `video` the check needs: the program inside the
/// unpacked runtime, which stands in for the archive it came from.
#[derive(Debug, Clone, PartialEq, serde::Deserialize)]
pub struct PlanVideo {
    pub binary: PathBuf,
}

/// When a `--help` run counts as "the binary starts".
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StartRule {
    /// Exit 0, or any exit whose output contains this usage text (serve: exit 2).
    UsageOrZero(&'static str),
    ExitZero,
}

const START_TIMEOUT: Duration = Duration::from_secs(60);

pub fn parse_plan(json: &str) -> Result<BootPlan, String> {
    serde_json::from_str(json).map_err(|e| format!("the boot menu's plan is not what the installer expects: {e}"))
}

fn check_one(path: &Path, bytes: u64, sha: Option<&str>, hash: bool, problems: &mut Vec<String>) {
    match fs::metadata(path) {
        Err(_) => problems.push(format!("missing: {}", path.display())),
        Ok(m) if !m.is_file() => problems.push(format!("not a file: {}", path.display())),
        Ok(m) if m.len() != bytes => {
            problems.push(format!("{} is {} bytes, expected {bytes}", path.display(), m.len()))
        }
        Ok(_) => {
            if let (true, Some(want)) = (hash, sha) {
                match crate::layout::sha256_file_hex(path) {
                    Ok(got) if got.eq_ignore_ascii_case(want) => {}
                    Ok(got) => problems.push(format!("{}: sha256 {got}, expected {}", path.display(), want.to_lowercase())),
                    Err(e) => problems.push(format!("{}: cannot read ({e})", path.display())),
                }
            }
        }
    }
}

/// Binaries present, every file present with its size, sha256 where `verified`
/// says the run has not checked it yet. All problems in one message.
pub fn check_files(plan: &BootPlan, verified: &dyn Fn(&str) -> bool) -> Result<(), String> {
    let mut problems = Vec::new();
    for server in std::iter::once(&plan.serve).chain(plan.image.as_ref()) {
        if !server.binary.is_file() {
            problems.push(format!("missing: {}", server.binary.display()));
        }
    }
    // #348: an unpacked runtime is checked by its program; the archive is gone.
    if let Some(video) = &plan.video {
        if !plan.runtime_archives.is_empty() && !video.binary.is_file() {
            problems.push(format!("missing: {}", video.binary.display()));
        }
    }
    let consumed: BTreeSet<&str> = plan
        .derived
        .iter()
        .flat_map(|d| d.inputs.iter().map(String::as_str))
        .chain(plan.runtime_archives.iter().map(String::as_str))
        .collect();
    for f in plan.files.iter().filter(|f| !consumed.contains(f.id.as_str())) {
        check_one(&f.dest, f.bytes, f.sha256.as_deref(), !verified(&f.id), &mut problems);
    }
    for d in &plan.derived {
        for o in &d.outputs {
            check_one(&o.dest, o.bytes, o.sha256.as_deref(), true, &mut problems);
        }
    }
    if problems.is_empty() {
        Ok(())
    } else {
        Err(format!("{} is not complete: {}", plan.point, problems.join("; ")))
    }
}

fn ntstatus_hint(code: u32) -> &'static str {
    match code {
        0xC000_0135 => ": a DLL it needs is missing",
        0xC000_007B => ": a DLL it loads is for another architecture",
        0xC000_0142 => ": a DLL failed to initialise",
        0xC000_0005 => ": access violation",
        _ => "",
    }
}

/// Did this `--help` run show a binary that loads? `code` None = no exit code.
pub fn judge_start(what: &str, rule: StartRule, code: Option<i32>, output: &str) -> Result<(), String> {
    let Some(code) = code else {
        return Err(format!("{what} ended without an exit code"));
    };
    let raw = code as u32;
    if raw >= 0xC000_0000 {
        return Err(format!("{what} does not start (exit 0x{raw:08X}{})", ntstatus_hint(raw)));
    }
    let ok = match rule {
        StartRule::ExitZero => code == 0,
        StartRule::UsageOrZero(usage) => code == 0 || output.contains(usage),
    };
    if ok {
        return Ok(());
    }
    let tail: Vec<&str> = output.lines().filter(|l| !l.trim().is_empty()).collect();
    Err(format!(
        "{what} --help exited {code} without its usage: {}",
        tail[tail.len().saturating_sub(3)..].join(" | ")
    ))
}

/// Run `exe args`, wait up to `timeout`, judge it by `rule`.
pub fn binary_starts(exe: &Path, args: &[&str], rule: StartRule, timeout: Duration) -> Result<(), String> {
    binary_starts_env(exe, args, rule, timeout, &[])
}

/// [`binary_starts`] with variables added to the inherited environment.
pub fn binary_starts_env(
    exe: &Path,
    args: &[&str],
    rule: StartRule,
    timeout: Duration,
    env: &[(String, String)],
) -> Result<(), String> {
    let what = exe.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| exe.display().to_string());
    if !exe.is_file() {
        return Err(format!("{what} is missing: {}", exe.display()));
    }
    let mut child = quiet(exe)
        .args(args)
        .envs(env.iter().map(|(k, v)| (k, v)))
        .current_dir(exe.parent().unwrap_or(Path::new(".")))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("{what} does not start: {e}"))?;
    let drain = |r: Option<Box<dyn Read + Send>>| {
        std::thread::spawn(move || {
            let mut buf = Vec::new();
            if let Some(mut r) = r {
                let _ = r.read_to_end(&mut buf);
            }
            buf
        })
    };
    let out = drain(child.stdout.take().map(|s| Box::new(s) as Box<dyn Read + Send>));
    let err = drain(child.stderr.take().map(|s| Box::new(s) as Box<dyn Read + Send>));
    let began = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(s)) => break s,
            Ok(None) if began.elapsed() < timeout => std::thread::sleep(Duration::from_millis(50)),
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(format!("{what} --help did not exit within {} s", timeout.as_secs()));
            }
            Err(e) => return Err(format!("{what}: {e}")),
        }
    };
    let text = format!(
        "{}\n{}",
        String::from_utf8_lossy(&out.join().unwrap_or_default()),
        String::from_utf8_lossy(&err.join().unwrap_or_default())
    );
    judge_start(&what, rule, status.code(), &text)
}

/// File ids the run's state marks verified. Read only when the state file
/// exists; an unreadable state means "hash everything" (slower, never wrong).
fn verified_ids(install_root: &Path) -> BTreeSet<String> {
    let path = install_root.join("setup").join("state.json");
    if !path.is_file() {
        return BTreeSet::new();
    }
    match StateStore::load(&path) {
        Ok(state) => state.files.into_iter().filter(|(_, f)| f.verified).map(|(id, _)| id).collect(),
        Err(_) => BTreeSet::new(),
    }
}

/// The boot menu's plan for `point`, as JSON from `crow_boot.py --plan --json`.
pub fn boot_plan(py: &PythonInfo, install_root: &Path, models_root: &Path, point: &str) -> Result<BootPlan, String> {
    let script = install_root.join("cli").join("crow_boot.py");
    let out = quiet(&py.exe)
        .arg(&script)
        .arg("--install-root")
        .arg(install_root)
        .arg("--models")
        .arg(models_root)
        .args(["--plan", point, "--json"])
        .current_dir(install_root)
        .output()
        .map_err(|e| format!("cannot run {}: {e}", script.display()))?;
    if !out.status.success() {
        return Err(format!("the boot menu has no plan for {point} ({}): {}", out.status, output_tail(&out, 3)));
    }
    parse_plan(&String::from_utf8_lossy(&out.stdout))
}

/// `LD_LIBRARY_PATH` with `<root>/cuda/lib` in front (crow_core `_image_server_env`).
pub fn image_server_env(install_root: &Path, inherited: Option<&str>) -> Vec<(String, String)> {
    let lib = install_root.join("cuda").join("lib").to_string_lossy().into_owned();
    let value = match inherited.filter(|v| !v.is_empty()) {
        Some(have) => format!("{lib}:{have}"),
        None => lib,
    };
    vec![("LD_LIBRARY_PATH".into(), value)]
}

#[cfg(windows)]
pub fn check_point(py: &PythonInfo, install_root: &Path, models_root: &Path, point: &str) -> Result<(), String> {
    let plan = boot_plan(py, install_root, models_root, point)?;
    let verified = verified_ids(install_root);
    check_files(&plan, &|id: &str| verified.contains(id))?;
    binary_starts(&plan.serve.binary, &["--help"], StartRule::UsageOrZero("usage: serve"), START_TIMEOUT)?;
    if let Some(image) = &plan.image {
        binary_starts(&image.binary, &["--help"], StartRule::ExitZero, START_TIMEOUT)?;
    }
    Ok(())
}

#[cfg(not(windows))]
pub fn check_point(py: &PythonInfo, install_root: &Path, models_root: &Path, point: &str) -> Result<(), String> {
    let plan = boot_plan(py, install_root, models_root, point)?;
    let verified = verified_ids(install_root);
    check_files(&plan, &|id: &str| verified.contains(id))?;
    let serve_env: Vec<(String, String)> = plan.serve.env.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
    binary_starts_env(&plan.serve.binary, &["--help"], StartRule::UsageOrZero("usage: serve"), START_TIMEOUT, &serve_env)?;
    if let Some(image) = &plan.image {
        let env = image_server_env(install_root, std::env::var("LD_LIBRARY_PATH").ok().as_deref());
        binary_starts_env(&image.binary, &["--help"], StartRule::ExitZero, START_TIMEOUT, &env)?;
    }
    Ok(())
}
