//! T3: unpack Crow's package and the engine package into the install root,
//! with install.ps1's update rules (version from crow_core.py, manifest-directed
//! removal, `.old` for locked files incl. serve.exe).
//!
//! The order is install.ps1's, plus one step in front of it:
//!
//! 1. the package is checked against its own MANIFEST.json INSIDE the zip
//!    (every listed file present with its bytes and sha256, nothing unlisted).
//!    A package that fails is refused before a single byte is written.
//! 2. the version decides (`resolve_action`, install.ps1 `Resolve-InstallAction`
//!    without `-Force`: the installer has no such switch). Equal versions are
//!    "up to date" only when every manifest file on disk still matches;
//!    otherwise the same version is written again (a crash mid-extraction, a
//!    damaged file).
//! 3. the PREVIOUS manifest is read before extraction overwrites it.
//! 4. extraction. A file in `bin\` that cannot be opened for writing (a running
//!    serve.exe, sd-server.exe or llama-server.exe and the DLLs they hold) is
//!    renamed to `<name>.old` and written fresh: Windows locks a running image
//!    against writing, not against renaming (install.ps1 `Move-LockedAside`).
//!    This asks the file rather than the process list, so it covers every
//!    binary and DLL by the same rule. MANIFEST.json is written last, so an
//!    interrupted run still has the old one to compute removals from.
//! 5. every file on disk is verified against the new manifest (`Compare-Manifest`).
//! 6. files the OLD manifest listed and the new one does not are removed
//!    (`Find-DroppedFiles`): a manifest-to-manifest question, never a directory
//!    listing, so `models\`, `session\` and the user's own files cannot be
//!    selected. Counted by looking afterwards.
//! 7. `bin\*.old` is swept, and what stays (still held) is reported, by looking
//!    (`Remove-StaleOld`).
//!
//! The engine zip (crow-nest `tools/pack-engine.ps1`) is flat and lands in
//! `<root>\bin\`, its MANIFEST.json as `bin\MANIFEST.json`. It carries no version
//! inside; the version in the summary comes from the zip's name and "up to date"
//! means every engine file on disk already matches.
//!
//! LINUX (#342): the packages are `crow-<v>-linux-x64.tar.gz` and
//! `crow-nest-engine-<v>-linux-x64.tar.gz`, read in two streamed passes (verify,
//! then write) because a gzip stream has no index. Tar names may carry `./`;
//! absolute names, `..`, links and device entries refuse the package. The engine
//! MANIFEST.json is an object `{"glibc_min", "files": [...]}`; a host glibc older
//! than `glibc_min` refuses the engine before a byte is written. A file is
//! written beside its target and renamed over it, so a running serve or
//! sd-server keeps its old inode and nothing is moved aside; the tar entry's
//! mode is kept (serve and sd-server are executables).
//!
//! NVIDIA FILES: neither package needs to carry NVRTC, cuBLAS or the CUDA
//! runtime; the `nvidia` step (crate::nvidia) puts them in place from NVIDIA's
//! wheels after both packages are installed. An older package that still
//! carries them installs as before (the bytes are NVIDIA's, identical), and an
//! update that drops them from its manifest removes them like any dropped
//! file; the `nvidia` step that follows puts them back.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize)]
pub struct ManifestEntry {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Install,
    Update,
    UpToDate,
    Downgrade,
    Unknown,
}

/// Top-level folders of the install root that belong to the installer, not to
/// a package: they never make a root "occupied" and are never removed.
#[cfg(not(unix))]
const INSTALLER_OWN: &[&str] = &["setup", "models", "python", "session"];
/// Linux adds the venv the installer creates under the root (#342).
#[cfg(unix)]
const INSTALLER_OWN: &[&str] = &["setup", "models", "python", "session", "venv"];

fn manifest_value(bytes: &[u8]) -> Result<serde_json::Value, String> {
    let text = std::str::from_utf8(bytes).map_err(|e| format!("MANIFEST.json is not UTF-8: {e}"))?;
    let text = text.trim_start_matches('\u{feff}');
    serde_json::from_str(text).map_err(|e| format!("MANIFEST.json is not valid JSON: {e}"))
}

/// MANIFEST.json as the packers write it: a JSON array of {path, bytes, sha256},
/// usually with a UTF-8 BOM; PowerShell writes a one-entry list as an object.
/// crow-nest's Linux pack (#342) writes an object `{"glibc_min", "files": [...]}`.
pub fn parse_manifest(bytes: &[u8]) -> Result<Vec<ManifestEntry>, String> {
    let list = match manifest_value(bytes)? {
        serde_json::Value::Array(a) => a,
        serde_json::Value::Object(mut o) if o.contains_key("files") => match o.remove("files") {
            Some(serde_json::Value::Array(a)) => a,
            _ => return Err("MANIFEST.json: \"files\" is not a list".into()),
        },
        obj @ serde_json::Value::Object(_) => vec![obj],
        _ => return Err("MANIFEST.json is neither a list nor an entry".into()),
    };
    list.into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| format!("MANIFEST.json entry: {e}")))
        .collect()
}

/// `VERSION = "x"` at the start of a line (install.ps1 / pack-release.ps1's pattern).
pub fn version_literal(text: &str) -> Option<String> {
    for line in text.lines() {
        let Some(rest) = line.strip_prefix("VERSION") else { continue };
        let rest = rest.trim_start();
        let Some(rest) = rest.strip_prefix('=') else { continue };
        let rest = rest.trim_start();
        let Some(rest) = rest.strip_prefix('"') else { continue };
        if let Some(end) = rest.find('"')
            && end > 0
        {
            return Some(rest[..end].to_string());
        }
    }
    None
}

/// The installed Crow version: cli\crow_core.py first, cli\crow.py for installs
/// from before #187 (install.ps1 `Get-InstalledVersion`).
pub fn installed_version(root: &Path) -> Option<String> {
    ["crow_core.py", "crow.py"].iter().find_map(|name| {
        let text = fs::read(root.join("cli").join(name)).ok()?;
        version_literal(&String::from_utf8_lossy(&text))
    })
}

fn parse_version(v: &str) -> Option<Vec<u64>> {
    let parts: Vec<&str> = v.split('.').collect();
    if !(2..=4).contains(&parts.len()) {
        return None;
    }
    parts.iter().map(|p| p.parse::<u64>().ok()).collect()
}

/// install.ps1 `Resolve-InstallAction` without `-Force`. `occupied`: the root
/// holds something that is neither the installer's own nor this package's.
pub fn resolve_action(installed: Option<&str>, target: &str, occupied: bool) -> Action {
    let Some(installed) = installed else {
        return if occupied { Action::Unknown } else { Action::Install };
    };
    match (parse_version(installed), parse_version(target)) {
        (Some(a), Some(b)) if b > a => Action::Update,
        (Some(a), Some(b)) if b == a => Action::UpToDate,
        (Some(_), Some(_)) => Action::Downgrade,
        _ => Action::Unknown,
    }
}

fn norm_key(p: &str) -> String {
    p.replace('\\', "/").to_lowercase()
}

/// install.ps1 `Find-DroppedFiles`: paths the previous manifest listed that the
/// current one does not. Case-insensitive, separator-agnostic, `/` in the answer.
pub fn find_dropped(previous: &[String], current: &[String]) -> Vec<String> {
    let now: BTreeSet<String> = current.iter().map(|p| norm_key(p)).collect();
    let mut seen = BTreeSet::new();
    let mut out = Vec::new();
    for p in previous {
        let key = norm_key(p);
        if now.contains(&key) || !seen.insert(key) {
            continue;
        }
        out.push(p.replace('\\', "/"));
    }
    out
}

/// `glibc_min` of an object MANIFEST.json (crow-nest's Linux pack), if any.
pub fn manifest_glibc_min(bytes: &[u8]) -> Option<String> {
    manifest_value(bytes).ok()?.get("glibc_min")?.as_str().map(str::to_string)
}

/// `crow-nest-engine-<version>-win-x64.zip` / `...-linux-x64.tar.gz` -> `<version>`.
pub fn engine_version_from_name(zip: &Path) -> Option<String> {
    let name = zip.file_name()?.to_str()?;
    let rest = name.strip_prefix("crow-nest-engine-")?;
    let v = rest.strip_suffix("-win-x64.zip").or_else(|| rest.strip_suffix("-linux-x64.tar.gz"))?;
    (!v.is_empty()).then(|| v.to_string())
}

/// `a.b.c` against `a.b`: true when `have` is at least `need` (missing parts are 0).
pub fn version_at_least(have: &str, need: &str) -> bool {
    let nums = |v: &str| -> Vec<u64> {
        v.split('.').map(|p| p.chars().take_while(char::is_ascii_digit).collect::<String>().parse().unwrap_or(0)).collect()
    };
    let (a, b) = (nums(have), nums(need));
    let n = a.len().max(b.len());
    let pad = |v: &Vec<u64>| (0..n).map(|i| v.get(i).copied().unwrap_or(0)).collect::<Vec<_>>();
    pad(&a) >= pad(&b)
}

/// The C library version this process runs on (`gnu_get_libc_version`); None off glibc.
pub fn host_glibc() -> Option<String> {
    #[cfg(all(unix, target_env = "gnu"))]
    {
        // SAFETY: returns a pointer to a static NUL-terminated string.
        let p = unsafe { libc::gnu_get_libc_version() };
        if p.is_null() {
            return None;
        }
        // SAFETY: p is non-null and points at a static C string.
        return Some(unsafe { std::ffi::CStr::from_ptr(p) }.to_string_lossy().into_owned());
    }
    #[allow(unreachable_code)]
    None
}

/// Is `path` a `.tar.gz` package (Linux) rather than a zip (Windows)?
pub fn is_tar_gz(path: &Path) -> bool {
    let n = path.file_name().map(|n| n.to_string_lossy().to_lowercase()).unwrap_or_default();
    n.ends_with(".tar.gz") || n.ends_with(".tgz")
}

fn sha256_reader(mut r: impl Read) -> io::Result<(u64, String)> {
    let mut h = crate::verify::Sha256Stream::new();
    let n = h.update_reader(&mut r)?;
    Ok((n, h.finish()))
}

/// Lower-case hex sha256 of a whole file (streamed).
pub fn sha256_file_hex(path: &Path) -> io::Result<String> {
    crate::verify::sha256_file(path)
}

/// A relative path from a zip entry or a manifest, `\` or `/`, refused when it
/// could leave the target (absolute, drive, `..`).
pub(crate) fn safe_rel(name: &str) -> Option<PathBuf> {
    let mut out = PathBuf::new();
    for part in name.split(['/', '\\']) {
        if part.is_empty() || part == "." {
            continue;
        }
        if part == ".." || part.contains(':') {
            return None;
        }
        out.push(part);
    }
    match out.components().next() {
        Some(Component::Normal(_)) => Some(out),
        _ => None,
    }
}

enum Archive {
    Zip(zip::ZipArchive<fs::File>),
    /// The `.tar.gz`, opened again for each streamed pass.
    #[cfg(unix)]
    TarGz(PathBuf),
}

/// The package, checked against its own manifest before anything is written.
struct Package {
    archive: Archive,
    manifest: Vec<ManifestEntry>,
    manifest_bytes: Vec<u8>,
    /// normalised manifest key -> zip index (tar: 0, presence only)
    index: BTreeMap<String, usize>,
    /// tar: the few entries read back before the write pass (the version files)
    #[cfg_attr(not(unix), allow(dead_code))]
    small: BTreeMap<String, Vec<u8>>,
}

fn open_package(zip_path: &Path) -> Result<Package, String> {
    if is_tar_gz(zip_path) {
        #[cfg(unix)]
        return open_tar(zip_path);
        #[cfg(not(unix))]
        return Err(format!("{} is a Linux package", zip_path.display()));
    }
    let file = fs::File::open(zip_path).map_err(|e| format!("cannot open {}: {e}", zip_path.display()))?;
    let mut archive =
        zip::ZipArchive::new(file).map_err(|e| format!("{} is not a readable zip: {e}", zip_path.display()))?;
    let mut entries: BTreeMap<String, usize> = BTreeMap::new();
    let mut manifest_at = None;
    for i in 0..archive.len() {
        let f = archive.by_index(i).map_err(|e| format!("zip entry {i}: {e}"))?;
        if f.is_dir() {
            continue;
        }
        let name = f.name().to_string();
        if safe_rel(&name).is_none() {
            return Err(format!("the package holds an unsafe path: {name}"));
        }
        let key = norm_key(&name);
        if key == "manifest.json" {
            manifest_at = Some(i);
        } else {
            entries.insert(key, i);
        }
    }
    let at = manifest_at.ok_or_else(|| format!("{} has no MANIFEST.json, nothing to verify against", zip_path.display()))?;
    let mut manifest_bytes = Vec::new();
    archive
        .by_index(at)
        .and_then(|mut f| f.read_to_end(&mut manifest_bytes).map_err(Into::into))
        .map_err(|e| format!("cannot read MANIFEST.json: {e}"))?;
    let manifest = parse_manifest(&manifest_bytes)?;

    let mut problems = Vec::new();
    let mut index = BTreeMap::new();
    for e in &manifest {
        let key = norm_key(&e.path);
        if safe_rel(&e.path).is_none() {
            problems.push(format!("unsafe path in MANIFEST.json: {}", e.path));
            continue;
        }
        let Some(&i) = entries.get(&key) else {
            problems.push(format!("missing from the package: {}", e.path));
            continue;
        };
        let f = archive.by_index(i).map_err(|err| format!("{}: {err}", e.path))?;
        match sha256_reader(f) {
            Ok((n, sha)) if n == e.bytes && sha.eq_ignore_ascii_case(&e.sha256) => {}
            Ok(_) => problems.push(format!("does not match MANIFEST.json: {}", e.path)),
            Err(err) => problems.push(format!("unreadable in the package: {} ({err})", e.path)),
        }
        index.insert(key, i);
    }
    for key in entries.keys() {
        if !index.contains_key(key) {
            problems.push(format!("not listed in MANIFEST.json: {key}"));
        }
    }
    if !problems.is_empty() {
        return Err(format!(
            "refusing {}: {}",
            zip_path.file_name().unwrap_or_default().to_string_lossy(),
            problems.join("; ")
        ));
    }
    Ok(Package { archive: Archive::Zip(archive), manifest, manifest_bytes, index, small: BTreeMap::new() })
}

/// Entries the tar pass keeps in memory for [`Package::read_entry`].
#[cfg(unix)]
const TAR_SMALL: [&str; 2] = ["cli/crow_core.py", "cli/crow.py"];

#[cfg(unix)]
fn tar_archive(path: &Path) -> Result<tar::Archive<flate2::read::GzDecoder<io::BufReader<fs::File>>>, String> {
    let file = fs::File::open(path).map_err(|e| format!("cannot open {}: {e}", path.display()))?;
    Ok(tar::Archive::new(flate2::read::GzDecoder::new(io::BufReader::new(file))))
}

/// The manifest key of a tar entry; None for what carries no file (directories,
/// pax headers). Links, devices, absolute names and `..` refuse the package.
#[cfg(unix)]
pub(crate) fn tar_entry_key(kind: tar::EntryType, name: &[u8]) -> Result<Option<String>, String> {
    use tar::EntryType as T;
    let name = std::str::from_utf8(name).map_err(|_| format!("the package holds a non-UTF-8 name: {}", String::from_utf8_lossy(name)))?;
    if kind.is_dir() || matches!(kind, T::XHeader | T::XGlobalHeader | T::GNULongName | T::GNULongLink) {
        return Ok(None);
    }
    if !(kind.is_file() || kind == T::Continuous) {
        return Err(format!("the package holds a link or special file: {name}"));
    }
    if name.starts_with('/') {
        return Err(format!("the package holds an absolute path: {name}"));
    }
    let rel = safe_rel(name).ok_or_else(|| format!("the package holds an unsafe path: {name}"))?;
    let parts: Vec<String> = rel.components().map(|c| c.as_os_str().to_string_lossy().into_owned()).collect();
    Ok(Some(norm_key(&parts.join("/"))))
}

/// Pass 1 over a `.tar.gz`: hash every file, read MANIFEST.json, compare.
#[cfg(unix)]
fn open_tar(path: &Path) -> Result<Package, String> {
    let shown = path.file_name().unwrap_or_default().to_string_lossy().into_owned();
    let mut archive = tar_archive(path)?;
    let mut seen: BTreeMap<String, (u64, String)> = BTreeMap::new();
    let mut small = BTreeMap::new();
    let mut manifest_bytes = None;
    let entries = archive.entries().map_err(|e| format!("{shown} is not a readable tar.gz: {e}"))?;
    for entry in entries {
        let mut e = entry.map_err(|err| format!("{shown} is not a readable tar.gz: {err}"))?;
        let Some(key) = tar_entry_key(e.header().entry_type(), &e.path_bytes())? else { continue };
        if key == "manifest.json" {
            let mut b = Vec::new();
            e.read_to_end(&mut b).map_err(|err| format!("cannot read MANIFEST.json: {err}"))?;
            manifest_bytes = Some(b);
            continue;
        }
        if seen.contains_key(&key) {
            return Err(format!("refusing {shown}: {key} is in the package twice"));
        }
        let got = if TAR_SMALL.contains(&key.as_str()) {
            let mut b = Vec::new();
            e.read_to_end(&mut b).map_err(|err| format!("{key}: {err}"))?;
            let r = sha256_reader(&b[..]);
            small.insert(key.clone(), b);
            r
        } else {
            sha256_reader(&mut e)
        };
        let got = got.map_err(|err| format!("refusing {shown}: unreadable in the package: {key} ({err})"))?;
        seen.insert(key, got);
    }
    let manifest_bytes = manifest_bytes.ok_or_else(|| format!("{} has no MANIFEST.json, nothing to verify against", path.display()))?;
    let manifest = parse_manifest(&manifest_bytes)?;
    let mut problems = Vec::new();
    let mut index = BTreeMap::new();
    for e in &manifest {
        let key = norm_key(&e.path);
        if safe_rel(&e.path).is_none() {
            problems.push(format!("unsafe path in MANIFEST.json: {}", e.path));
            continue;
        }
        match seen.get(&key) {
            None => problems.push(format!("missing from the package: {}", e.path)),
            Some((n, sha)) if *n == e.bytes && sha.eq_ignore_ascii_case(&e.sha256) => {}
            Some(_) => problems.push(format!("does not match MANIFEST.json: {}", e.path)),
        }
        index.insert(key, 0);
    }
    for key in seen.keys() {
        if !index.contains_key(key) {
            problems.push(format!("not listed in MANIFEST.json: {key}"));
        }
    }
    if !problems.is_empty() {
        return Err(format!("refusing {shown}: {}", problems.join("; ")));
    }
    Ok(Package { archive: Archive::TarGz(path.to_path_buf()), manifest, manifest_bytes, index, small })
}

impl Package {
    fn read_entry(&mut self, path: &str) -> Option<Vec<u8>> {
        let key = norm_key(path);
        let i = *self.index.get(&key)?;
        match &mut self.archive {
            Archive::Zip(z) => {
                let mut out = Vec::new();
                z.by_index(i).ok()?.read_to_end(&mut out).ok()?;
                Some(out)
            }
            #[cfg(unix)]
            Archive::TarGz(_) => self.small.get(&key).cloned(),
        }
    }

    /// Write every manifest file under `dest`; returns how many were written.
    fn write_all(&mut self, dest: &Path, in_bin: &dyn Fn(&Path) -> bool, moved: &mut Vec<String>) -> Result<usize, String> {
        let entries = self.manifest.clone();
        #[cfg(unix)]
        if let Archive::TarGz(path) = &self.archive {
            let by_key: BTreeMap<String, &ManifestEntry> = entries.iter().map(|e| (norm_key(&e.path), e)).collect();
            let mut written = BTreeSet::new();
            let mut archive = tar_archive(path)?;
            let all = archive.entries().map_err(|e| format!("cannot read {}: {e}", path.display()))?;
            for entry in all {
                let mut e = entry.map_err(|err| format!("cannot read {}: {err}", path.display()))?;
                let Some(key) = tar_entry_key(e.header().entry_type(), &e.path_bytes())? else { continue };
                let Some(m) = by_key.get(&key) else { continue };
                let rel = safe_rel(&m.path).ok_or_else(|| format!("unsafe path {}", m.path))?;
                let mode = e.header().mode().ok();
                write_stream(&dest.join(&rel), &mut e, mode)?;
                written.insert(key);
            }
            if written.len() != by_key.len() {
                return Err(format!("{} changed while it was installed", path.display()));
            }
            return Ok(written.len());
        }
        for e in &entries {
            let rel = safe_rel(&e.path).ok_or_else(|| format!("unsafe path {}", e.path))?;
            let data = self.read_entry(&e.path).ok_or_else(|| format!("cannot read {} from the package", e.path))?;
            write_file(&dest.join(&rel), &data, in_bin(&rel), moved)?;
            #[cfg(unix)]
            if let (Archive::Zip(z), Some(&i)) = (&mut self.archive, self.index.get(&norm_key(&e.path))) {
                if let Some(mode) = z.by_index(i).ok().and_then(|f| f.unix_mode()) {
                    set_mode(&dest.join(&rel), mode)?;
                }
            }
        }
        Ok(entries.len())
    }

    fn paths(&self) -> Vec<String> {
        self.manifest.iter().map(|e| e.path.clone()).collect()
    }
}

/// Missing or mismatched manifest files under `dir` (install.ps1 `Compare-Manifest`).
fn compare_on_disk(dir: &Path, manifest: &[ManifestEntry]) -> Vec<String> {
    let mut bad = Vec::new();
    for e in manifest {
        let Some(rel) = safe_rel(&e.path) else {
            bad.push(format!("unsafe: {}", e.path));
            continue;
        };
        let p = dir.join(rel);
        match fs::metadata(&p) {
            Err(_) => bad.push(format!("missing: {}", e.path)),
            Ok(m) if m.len() != e.bytes => bad.push(format!("corrupt: {}", e.path)),
            Ok(_) => match sha256_file_hex(&p) {
                Ok(s) if s.eq_ignore_ascii_case(&e.sha256) => {}
                _ => bad.push(format!("corrupt: {}", e.path)),
            },
        }
    }
    bad
}

fn read_previous_manifest(dir: &Path, notes: &mut Vec<String>) -> Vec<String> {
    let path = dir.join("MANIFEST.json");
    let Ok(bytes) = fs::read(&path) else { return Vec::new() };
    match parse_manifest(&bytes) {
        Ok(m) => m.into_iter().map(|e| e.path).collect(),
        Err(_) => {
            // not knowing what the last package left means removing nothing
            notes.push("previous MANIFEST.json unreadable, nothing removed".into());
            Vec::new()
        }
    }
}

/// Linux: write `<dest>.crowsetup-new`, then rename it over `dest`. A running
/// binary or a mapped library keeps its old inode; nothing is moved aside.
#[cfg(unix)]
fn write_stream(dest: &Path, r: &mut dyn Read, mode: Option<u32>) -> Result<(), String> {
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("cannot create {}: {e}", parent.display()))?;
    }
    let mut tmp = dest.as_os_str().to_os_string();
    tmp.push(".crowsetup-new");
    let tmp = PathBuf::from(tmp);
    let _ = fs::remove_file(&tmp);
    let res = (|| {
        let mut f = fs::File::create(&tmp).map_err(|e| format!("cannot write {}: {e}", tmp.display()))?;
        io::copy(r, &mut f).map_err(|e| format!("cannot write {}: {e}", dest.display()))?;
        f.flush().map_err(|e| format!("cannot write {}: {e}", dest.display()))?;
        if let Some(m) = mode {
            set_mode(&tmp, m)?;
        }
        fs::rename(&tmp, dest).map_err(|e| format!("cannot replace {}: {e}", dest.display()))
    })();
    if res.is_err() {
        let _ = fs::remove_file(&tmp);
    }
    res
}

/// The permission bits of a package entry (owner read/write always kept).
#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode((mode & 0o777) | 0o600))
        .map_err(|e| format!("cannot set the mode of {}: {e}", path.display()))
}

#[cfg(unix)]
fn write_file(dest: &Path, data: &[u8], _may_move_aside: bool, _moved: &mut Vec<String>) -> Result<(), String> {
    write_stream(dest, &mut &data[..], None)
}

/// Write one file; in `bin` a file that cannot be opened for writing is renamed
/// to `.old` first (Windows lets a running image be renamed, not written).
#[cfg(not(unix))]
fn write_file(dest: &Path, data: &[u8], may_move_aside: bool, moved: &mut Vec<String>) -> Result<(), String> {
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("cannot create {}: {e}", parent.display()))?;
    }
    let first = fs::File::create(dest);
    let mut file = match first {
        Ok(f) => f,
        Err(e) if may_move_aside && dest.exists() => {
            let mut old = dest.as_os_str().to_os_string();
            old.push(".old");
            let old = PathBuf::from(old);
            // an interrupted update may have left one behind; it is in the way now
            let _ = fs::remove_file(&old);
            fs::rename(dest, &old).map_err(|re| {
                format!(
                    "{} is in use and cannot be moved aside ({e}; {re}); stop the running server and try again",
                    dest.display()
                )
            })?;
            moved.push(dest.file_name().unwrap_or_default().to_string_lossy().into_owned());
            fs::File::create(dest).map_err(|e| format!("cannot write {}: {e}", dest.display()))?
        }
        Err(e) => return Err(format!("cannot write {}: {e}", dest.display())),
    };
    file.write_all(data).map_err(|e| format!("cannot write {}: {e}", dest.display()))
}

/// Delete `bin\*.old`; returns (removed, still held), by looking afterwards.
fn sweep_old(bin: &Path) -> (usize, Vec<String>) {
    let list = |bin: &Path| -> Vec<PathBuf> {
        fs::read_dir(bin)
            .map(|rd| {
                rd.filter_map(|e| e.ok().map(|e| e.path()))
                    .filter(|p| p.is_file() && p.extension().is_some_and(|x| x.eq_ignore_ascii_case("old")))
                    .collect()
            })
            .unwrap_or_default()
    };
    let before = list(bin);
    for p in &before {
        let _ = fs::remove_file(p);
    }
    let kept: Vec<String> = list(bin)
        .iter()
        .map(|p| p.file_name().unwrap_or_default().to_string_lossy().into_owned())
        .collect();
    (before.len() - kept.len(), kept)
}

/// Remove dropped files under `dir`; returns (removed, could not remove).
fn remove_dropped(dir: &Path, dropped: &[String]) -> (usize, Vec<String>) {
    let mut targets = Vec::new();
    for rel in dropped {
        let Some(p) = safe_rel(rel) else { continue };
        // belt and braces: no manifest lists these, and none may ever be cleaned
        let top = p.components().next().map(|c| c.as_os_str().to_string_lossy().to_lowercase());
        if top.is_some_and(|t| INSTALLER_OWN.contains(&t.as_str())) {
            continue;
        }
        let full = dir.join(&p);
        if full.is_file() {
            targets.push((rel.clone(), full));
        }
    }
    for (_, full) in &targets {
        let _ = fs::remove_file(full);
    }
    let stuck: Vec<String> = targets.iter().filter(|(_, f)| f.exists()).map(|(r, _)| r.clone()).collect();
    (targets.len() - stuck.len(), stuck)
}

/// Does `root` hold anything that is neither the installer's own nor a path
/// this package writes? (install.ps1 refuses any non-empty unidentified target;
/// the installer's own `setup\`/`models\` and the files of an interrupted first
/// install of this same package must not count.)
fn occupied(root: &Path, manifest: &[ManifestEntry]) -> bool {
    let ours: BTreeSet<String> = manifest.iter().map(|e| norm_key(&e.path)).collect();
    fn walk(dir: &Path, rel: &str, ours: &BTreeSet<String>) -> bool {
        let Ok(rd) = fs::read_dir(dir) else { return false };
        for e in rd.flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            let r = if rel.is_empty() { name.clone() } else { format!("{rel}/{name}") };
            if rel.is_empty() && (INSTALLER_OWN.contains(&name.to_lowercase().as_str()) || name.eq_ignore_ascii_case("MANIFEST.json")) {
                continue;
            }
            let p = e.path();
            if p.is_dir() {
                if walk(&p, &r, ours) {
                    return true;
                }
            } else if !ours.contains(&r.to_lowercase()) {
                return true;
            }
        }
        false
    }
    walk(root, "", &ours)
}

struct Outcome {
    written: usize,
    removed: usize,
    stuck: Vec<String>,
    moved: Vec<String>,
    swept: usize,
    held: Vec<String>,
    notes: Vec<String>,
}

/// Steps 3-7 for a package already checked: write into `dest`, verify, remove
/// dropped files, sweep `bin\*.old`. `in_bin(rel)` says whether a locked file may
/// be moved aside.
fn lay_down(pkg: &mut Package, dest: &Path, bin: &Path, in_bin: &dyn Fn(&Path) -> bool) -> Result<Outcome, String> {
    let mut notes = Vec::new();
    let previous = read_previous_manifest(dest, &mut notes);
    let mut moved = Vec::new();
    let entries = pkg.manifest.clone();
    pkg.write_all(dest, in_bin, &mut moved)?;
    let mbytes = pkg.manifest_bytes.clone();
    write_file(&dest.join("MANIFEST.json"), &mbytes, false, &mut moved)?;

    let bad = compare_on_disk(dest, &entries);
    if !bad.is_empty() {
        return Err(format!("the files on disk do not match the package: {}", bad.join("; ")));
    }
    let dropped = find_dropped(&previous, &pkg.paths());
    let (removed, stuck) = remove_dropped(dest, &dropped);
    let (swept, held) = sweep_old(bin);
    Ok(Outcome { written: entries.len(), removed, stuck, moved, swept, held, notes })
}

fn describe(head: String, o: &Outcome) -> String {
    let mut s = format!("{head} ({} files", o.written);
    if o.removed > 0 {
        s.push_str(&format!(", {} dropped files removed", o.removed));
    }
    s.push(')');
    if !o.moved.is_empty() {
        s.push_str(&format!("; moved aside as .old while running: {}", o.moved.join(", ")));
    }
    tail(&mut s, o.swept, &o.held, &o.stuck, &o.notes);
    s
}

fn tail(s: &mut String, swept: usize, held: &[String], stuck: &[String], notes: &[String]) {
    if swept > 0 {
        s.push_str(&format!("; {swept} stale .old files removed"));
    }
    if !held.is_empty() {
        s.push_str(&format!("; still held until the server stops: {}", held.join(", ")));
    }
    if !stuck.is_empty() {
        s.push_str(&format!("; could not remove: {}", stuck.join(", ")));
    }
    for n in notes {
        s.push_str("; ");
        s.push_str(n);
    }
}

fn up_to_date(head: String, bin: &Path) -> String {
    let (swept, held) = sweep_old(bin);
    let mut s = head;
    tail(&mut s, swept, &held, &[], &[]);
    s
}

/// Crow's package (`crow-<version>-win-x64.zip`, Linux `crow-<version>-linux-x64.tar.gz`) into `install_root`.
pub fn install_crow_package(zip: &Path, install_root: &Path) -> Result<String, String> {
    let mut pkg = open_package(zip)?;
    let target = ["cli/crow_core.py", "cli/crow.py"]
        .iter()
        .find_map(|p| pkg.read_entry(p).and_then(|b| version_literal(&String::from_utf8_lossy(&b))))
        .ok_or("the package carries no VERSION in cli/crow_core.py")?;
    fs::create_dir_all(install_root).map_err(|e| format!("cannot create {}: {e}", install_root.display()))?;
    let installed = installed_version(install_root);
    let bin = install_root.join("bin");
    let busy = installed.is_none() && occupied(install_root, &pkg.manifest);
    let action = resolve_action(installed.as_deref(), &target, busy);
    let head = match action {
        Action::Unknown => {
            return Err(match &installed {
                Some(v) => format!("cannot compare the installed version {v} with {target}; nothing was changed"),
                None => format!(
                    "{} holds files that do not identify themselves as a Crow install; choose an empty folder",
                    install_root.display()
                ),
            });
        }
        Action::Downgrade => {
            return Err(format!(
                "a newer Crow is installed ({}, this installs {target}); nothing was changed",
                installed.unwrap_or_default()
            ));
        }
        Action::UpToDate => {
            if compare_on_disk(install_root, &pkg.manifest).is_empty() {
                return Ok(up_to_date(format!("Crow {target} is up to date"), &bin));
            }
            format!("Crow {target} repaired")
        }
        Action::Update => format!("Crow {} -> {target} updated", installed.unwrap_or_default()),
        Action::Install => format!("Crow {target} installed"),
    };
    let in_bin = |rel: &Path| {
        rel.components()
            .next()
            .is_some_and(|c| c.as_os_str().eq_ignore_ascii_case("bin"))
    };
    let out = lay_down(&mut pkg, install_root, &bin, &in_bin)?;
    Ok(describe(head, &out))
}

/// A refusal when the engine needs a newer glibc than this system has.
pub fn glibc_refusal(need: Option<&str>, have: Option<&str>) -> Option<String> {
    let (need, have) = (need?, have?);
    (!version_at_least(have, need)).then(|| {
        format!("this engine needs glibc {need} or newer and this system has {have}; nothing was changed")
    })
}

/// The crow-nest engine (`crow-nest-engine-<version>-win-x64.zip`, Linux
/// `crow-nest-engine-<version>-linux-x64.tar.gz`) into `<root>\bin\`.
pub fn install_engine_package(zip: &Path, install_root: &Path) -> Result<String, String> {
    let mut pkg = open_package(zip)?;
    if let Some(why) = glibc_refusal(manifest_glibc_min(&pkg.manifest_bytes).as_deref(), host_glibc().as_deref()) {
        return Err(why);
    }
    let version = engine_version_from_name(zip).unwrap_or_else(|| "(unversioned)".into());
    let bin = install_root.join("bin");
    fs::create_dir_all(&bin).map_err(|e| format!("cannot create {}: {e}", bin.display()))?;
    let had = bin.join("MANIFEST.json").is_file();
    if had && compare_on_disk(&bin, &pkg.manifest).is_empty() {
        return Ok(up_to_date(format!("engine {version} is up to date"), &bin));
    }
    let head = if had {
        format!("engine updated to {version}")
    } else {
        format!("engine {version} installed")
    };
    let out = lay_down(&mut pkg, &bin, &bin, &|_rel: &Path| true)?;
    Ok(describe(head, &out))
}
