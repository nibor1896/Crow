//! T2: typed view of `manifests/stack.json` (the embedded [`crate::STACK_JSON`]).
//!
//! Typed: everything the plan and preflight read, i.e. `files`, `crow_files`,
//! `nvidia_files` (crate::nvidia), `derived` and each point's `id`, `menu`,
//! `files`, `derived`, `bytes` and `preflight`. Kept as `serde_json::Value`: a point's `engine`, `image_server`
//! and `crow_env` (the boot-time wiring; the check step resolves them like
//! `crow_boot.plan_point`), plus the whole document in [`Stack::raw`].
//! Keys starting with `_` are documentation and ignored. `tools/check_stack.py`
//! is the validator; [`Stack::parse`] only refuses what would make a lookup
//! fail later (an id a point names that is not declared).

use serde::Deserialize;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct Stack {
    pub raw: serde_json::Value,
    pub files: Vec<StackFile>,
    /// Files every install gets, whatever points are chosen (the dictation model).
    pub crow_files: Vec<StackFile>,
    /// NVIDIA's CUDA libraries, taken from NVIDIA's own wheels (crate::nvidia).
    pub nvidia_files: Vec<NvidiaWheel>,
    pub derived: Vec<Derived>,
    pub points: Vec<Point>,
}

/// One member CrowSetup takes out of an NVIDIA wheel.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct WheelMember {
    /// The path inside the wheel, as its RECORD lists it.
    pub member: String,
    /// `${INSTALL}/...`, where the packages used to carry the file.
    pub dest: String,
    pub bytes: u64,
    pub sha256: String,
}

/// An NVIDIA wheel on PyPI, pinned by bytes and sha256 (`nvidia_files`).
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct NvidiaWheel {
    pub id: String,
    pub package: String,
    pub version: String,
    /// `windows` or `linux`: the only platform that installs it.
    pub platform: String,
    /// The servers that load it: `serve`, `llama-server`, `sd-server`.
    pub servers: Vec<String>,
    pub url: String,
    pub bytes: u64,
    pub sha256: String,
    /// Where the wheel is downloaded to (`${INSTALL}/setup/downloads/...`).
    pub dest: String,
    pub license: String,
    pub extract: Vec<WheelMember>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Status {
    /// In our Hugging Face repo at the pinned revision.
    Published,
    /// Planned for our repo at `repo`/`path`; `revision` is null until the upload,
    /// so the bytes come from `source`.
    MirrorPending,
    /// The third-party repo at the pinned revision.
    Upstream,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Host {
    Huggingface,
    Github,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct FileSource {
    pub host: Host,
    pub repo: String,
    pub path: String,
    pub revision: String,
    pub bytes: u64,
    pub sha256: String,
}

impl FileSource {
    /// The pinned download URL at the upstream origin.
    pub fn url(&self) -> String {
        match self.host {
            Host::Huggingface => hf_url(&self.repo, &self.revision, &self.path),
            Host::Github => format!(
                "https://raw.githubusercontent.com/{}/{}/{}",
                self.repo, self.revision, self.path
            ),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct StackFile {
    pub id: String,
    pub repo: String,
    pub path: String,
    pub revision: Option<String>,
    pub bytes: u64,
    pub sha256: String,
    /// With `${MODELS}` or `${INSTALL}`, forward slashes.
    pub dest: String,
    #[serde(default)]
    pub source: Option<FileSource>,
    pub status: Status,
    pub license: String,
    pub role: String,
    /// Where a published or upstream file lives (#340); absent = Hugging Face.
    #[serde(default)]
    pub host: Option<UpstreamHost>,
    /// The release tag of a `github-release` asset; `revision` is its commit.
    #[serde(default)]
    pub tag: Option<String>,
    /// A Hugging Face repo whose files need the user's token (the LTX gate).
    #[serde(default)]
    pub gated: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum UpstreamHost {
    Huggingface,
    /// A raw file at a commit.
    Github,
    /// A release asset, by its tag.
    GithubRelease,
}

impl StackFile {
    /// The pinned URL of a published or upstream file at its host.
    pub fn url(&self, revision: &str) -> Result<String, String> {
        Ok(match self.host.unwrap_or(UpstreamHost::Huggingface) {
            UpstreamHost::Huggingface => hf_url(&self.repo, revision, &self.path),
            UpstreamHost::Github => format!("https://raw.githubusercontent.com/{}/{}/{}", self.repo, revision, self.path),
            UpstreamHost::GithubRelease => {
                let tag = self.tag.as_deref().ok_or_else(|| format!("file {} on github-release has no tag", self.id))?;
                format!("https://github.com/{}/releases/download/{}/{}", self.repo, tag, self.path)
            }
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct DerivedOutput {
    pub path: String,
    pub bytes: u64,
    pub sha256: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct Derived {
    pub id: String,
    pub tool: String,
    pub argv: Vec<String>,
    /// File ids consumed; the installer deletes them after the conversion (#196:
    /// `text_encoder/` goes once `text_encoder_sdcli/` is built).
    pub inputs: Vec<String>,
    pub dest: String,
    pub outputs: Vec<DerivedOutput>,
    pub bytes: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct Menu {
    pub title: String,
    pub line: String,
}

/// A point's own byte totals as stack.json states them (check_stack.py holds
/// them to the sums of the listed files).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub struct PointBytes {
    pub published: u64,
    pub mirror_pending: u64,
    pub upstream: u64,
    pub files: u64,
    pub derived: u64,
    /// files + derived: the peak, before converter inputs are deleted.
    pub disk: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct HostRam {
    /// Host RAM the engine pins at most; null for the dense points.
    pub pinned_max_gib: Option<u64>,
    /// Host RAM the point's peak was measured at, outside the engine (#340: the
    /// Media Stack's ComfyUI during a 20 s clip). Like a pin, it needs 64 GB.
    #[serde(default)]
    pub peak_gib: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct PointPreflight {
    pub gpu: serde_json::Value,
    pub host_ram: HostRam,
    /// The point's own peak disk need (files + derived).
    pub disk_bytes: u64,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Point {
    pub id: String,
    pub menu: Menu,
    pub files: Vec<String>,
    pub derived: Vec<String>,
    pub bytes: PointBytes,
    pub preflight: PointPreflight,
    pub engine: serde_json::Value,
    pub image_server: serde_json::Value,
    pub crow_env: serde_json::Value,
}

#[derive(Deserialize)]
struct Doc {
    files: Vec<StackFile>,
    #[serde(default)]
    crow_files: Vec<StackFile>,
    #[serde(default)]
    nvidia_files: Vec<NvidiaWheel>,
    derived: Vec<Derived>,
    points: Vec<Point>,
}

impl Stack {
    pub fn parse(json: &str) -> Result<Stack, String> {
        let raw: serde_json::Value = serde_json::from_str(json).map_err(|e| format!("stack.json: {e}"))?;
        let doc: Doc = serde_json::from_value(raw.clone()).map_err(|e| format!("stack.json: {e}"))?;
        let stack = Stack {
            raw,
            files: doc.files,
            crow_files: doc.crow_files,
            nvidia_files: doc.nvidia_files,
            derived: doc.derived,
            points: doc.points,
        };
        for p in &stack.points {
            if let Some(id) = p.files.iter().find(|id| stack.file(id).is_none()) {
                return Err(format!("stack.json: point {} names file {id}, which is not declared", p.id));
            }
            if let Some(id) = p.derived.iter().find(|id| stack.derived_entry(id).is_none()) {
                return Err(format!("stack.json: point {} names derived {id}, which is not declared", p.id));
            }
        }
        for d in &stack.derived {
            if let Some(id) = d.inputs.iter().find(|id| stack.file(id).is_none()) {
                return Err(format!("stack.json: derived {} input {id} is not a file", d.id));
            }
        }
        Ok(stack)
    }

    pub fn embedded() -> Stack {
        Stack::parse(crate::STACK_JSON).expect("embedded stack.json parses")
    }

    pub fn file(&self, id: &str) -> Option<&StackFile> {
        self.files.iter().find(|f| f.id == id)
    }

    pub fn derived_entry(&self, id: &str) -> Option<&Derived> {
        self.derived.iter().find(|d| d.id == id)
    }

    pub fn point(&self, id: &str) -> Option<&Point> {
        self.points.iter().find(|p| p.id == id)
    }
}

/// `https://huggingface.co/<repo>/resolve/<revision>/<path>`.
pub fn hf_url(repo: &str, revision: &str, path: &str) -> String {
    format!("https://huggingface.co/{repo}/resolve/{revision}/{path}")
}

/// A stack.json path (`${MODELS}/a/b`, `${INSTALL}/a/b`, or bare `${INSTALL}`)
/// as a platform path. Anything else is an error: check_stack.py allows no other root.
pub fn resolve_path(s: &str, install_root: &Path, models_root: &Path) -> Result<PathBuf, String> {
    let (root, rest) = if let Some(rest) = s.strip_prefix("${MODELS}") {
        (models_root, rest)
    } else if let Some(rest) = s.strip_prefix("${INSTALL}") {
        (install_root, rest)
    } else {
        return Err(format!("path {s:?} does not start with ${{MODELS}} or ${{INSTALL}}"));
    };
    if !(rest.is_empty() || rest.starts_with('/')) {
        return Err(format!("path {s:?}: a placeholder must be followed by / or end the path"));
    }
    let mut out = root.to_path_buf();
    for part in rest.split('/').filter(|p| !p.is_empty()) {
        if part == ".." || part.contains("${") {
            return Err(format!("path {s:?}: {part:?} is not allowed"));
        }
        out.push(part);
    }
    Ok(out)
}
