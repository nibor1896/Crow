//! The contract between the installer's parts (#196 phase 2).
//!
//! Every module of `crowsetup-core` and the exe speak these types. Changing a
//! type here is a change for every owner: the lead merges such changes, a task
//! adds to its own module instead.

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// An operating point id as written in `manifests/stack.json`:
/// `flash-next`, `27b`, `image-stack`, `media-stack`.
pub type PointId = String;

/// What the user picked on the selection screen.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Selection {
    pub points: Vec<PointId>,
    /// `${INSTALL}`; the default is `%LOCALAPPDATA%\Crow`.
    pub install_root: PathBuf,
    /// Folder for the boot-menu shortcut; the Start menu entry is always written.
    pub shortcut_dir: Option<PathBuf>,
}

/// Where the bytes come from.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum Source {
    /// Hugging Face and GitHub releases, the URLs the plan carries.
    Remote,
    /// `--source <dir>`: a local folder that mirrors the remote layout
    /// (`<dir>/<repo>/<path>` for HF files, `<dir>/releases/<asset>` for packages).
    Local(PathBuf),
}

/// What a file is for; decides the install step that consumes it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FileKind {
    CrowPackage,
    EnginePackage,
    Model,
    Whisper,
    /// An NVIDIA wheel from PyPI; the `nvidia` step takes its libraries out
    /// (crate::nvidia) and deletes it.
    NvidiaWheel,
}

/// One file to fetch and verify.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FileJob {
    /// stack.json file id (e.g. `27b-cnq`) or a fixed id for packages.
    pub id: String,
    pub kind: FileKind,
    /// Remote URL, e.g. `https://huggingface.co/<repo>/resolve/<revision>/<path>`.
    pub url: String,
    /// Relative path under the local source root, used with [`Source::Local`].
    pub local_rel: String,
    /// Final destination; the download writes `<dest>.part` first.
    pub dest: PathBuf,
    pub bytes: u64,
    /// Lower-case hex.
    pub sha256: String,
    /// Points this file serves; a shared file lists several.
    pub points: Vec<PointId>,
}

/// One release asset (Crow's package, the engine zip). Known only when the
/// release is built, so `installer/build.ps1` writes them into
/// `installer/vendor/packages.json` and the exe embeds that file.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Package {
    /// `crow-<version>-win-x64.zip` / `crow-nest-engine-<version>-win-x64.zip`.
    pub asset: String,
    /// GitHub release download URL.
    pub url: String,
    pub bytes: u64,
    /// Lower-case hex.
    pub sha256: String,
    pub version: String,
}

/// The two packages every install needs.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Packages {
    pub crow: Package,
    pub engine: Package,
}

/// A file that is produced on the machine, not downloaded.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DerivedJob {
    pub id: String,
    pub dest: PathBuf,
    pub bytes: u64,
    pub points: Vec<PointId>,
    /// File ids the step consumes and deletes (the image stack's `text_encoder/`).
    #[serde(default)]
    pub inputs: Vec<String>,
}

/// The fetch list for a selection, deduplicated, smallest first.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Plan {
    pub jobs: Vec<FileJob>,
    pub derived: Vec<DerivedJob>,
    pub download_bytes: u64,
    pub disk_bytes: u64,
}

/// Why a point cannot be installed on this machine (shown under its row).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Blocked {
    pub point: PointId,
    pub reason: String,
}

/// The machine, as preflight read it.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PreflightReport {
    pub os_64bit: bool,
    pub gpu_name: Option<String>,
    pub vram_mib: Option<u64>,
    /// e.g. "12.0"; Crow's engine needs 12.x (Blackwell).
    pub compute_cap: Option<String>,
    pub ram_bytes: u64,
    pub disk_free_bytes: u64,
    pub webview2: bool,
    /// Set when nothing can be installed: one sentence for the selection screen.
    pub hard_block: Option<String>,
    pub blocked: Vec<Blocked>,
}

/// Progress and results, from the core to the UI (or the headless printer).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Event {
    Preflight(PreflightReport),
    Planned(Plan),
    /// Re-hashing an existing `.part` after a restart.
    Checking { id: String, bytes: u64 },
    FileStarted { id: String, from_byte: u64, total: u64 },
    FileProgress { id: String, done: u64, total: u64 },
    FileRetry { id: String, attempt: u32, reason: String },
    FileVerified { id: String },
    FileError { id: String, message: String, retryable: bool },
    /// An install step: `crow`, `engine`, `python`, `nvidia`, `runtime`,
    /// `convert`, `check`, `shortcuts`.
    Step { name: String, status: StepStatus, detail: String },
    Done { installed: Vec<PointId>, shortcut: Option<PathBuf> },
    Fatal { message: String },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StepStatus {
    Running,
    Ok,
    Warning,
    Failed,
}

/// From the UI to the core.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Command {
    Start(Selection),
    Pause,
    Resume,
    Retry { id: String },
    OpenBootMenu,
    Quit,
}
