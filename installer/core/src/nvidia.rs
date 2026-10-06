//! NVIDIA's CUDA libraries, taken from NVIDIA's own wheels (stack.json
//! `nvidia_files`).
//!
//! CROW SHIPS NO NVIDIA FILE. Neither Crow's package nor crow-nest's engine
//! package carries NVRTC, cuBLAS or the CUDA runtime any more; CrowSetup
//! downloads the wheel NVIDIA publishes on PyPI (pinned by bytes and sha256,
//! fetched like every other file into `setup/downloads`) and takes out ONLY the
//! members stack.json names, to the paths the packages used to carry them at
//! (`bin/` for NVRTC and the Windows cuBLAS, `cuda/lib/` for the Linux CUDA
//! runtime and cuBLAS that sd-server links). Boot, `lib_path` and the check
//! step therefore see the same files as before.
//!
//! WHEN: a wheel is installed on its own platform when a selected point runs
//! one of its `servers`. A point runs its engine (`engine.kind`, default
//! `serve`), and `sd-server` when it has an `image_server` or sets
//! `CROW_IMAGE_MODEL_DIR` in `crow_env` (Crow starts sd-server on demand for
//! such a point). So NVRTC comes with every crow-nest point, cuBLAS (and on
//! Linux the CUDA runtime) with every point that runs llama-server or sd-server.
//!
//! CHECKED TWICE, REFUSED WHOLE. Before a byte is written every member must be
//! listed in the wheel's `*.dist-info/RECORD` with a `sha256=` (urlsafe base64,
//! no padding) and a size equal to what stack.json pins, and its name must stay
//! inside the wheel (no absolute path, no `..`, no drive); its dest must stay
//! under the install root. Each member is then streamed to
//! `<dest>.crowsetup-new` while it is hashed and renamed over `dest` only when
//! its bytes and sha256 match. A file already at `dest` with those bytes (an
//! older package that still carried it) is left as it is: the bytes are the
//! same. A dest that is held by a running server is moved aside to `.old` on
//! Windows (the package step's rule; its next run sweeps `bin\*.old`).
//!
//! A local `--source` holds a wheel at `pypi/<package>/<wheel file name>`.

use crate::api::{FileJob, FileKind, Selection};
use crate::layout::safe_rel;
use crate::stack::{NvidiaWheel, Point, Stack, resolve_path};
use crate::verify::Sha256Stream;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};

/// One member to take out of the wheel.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NvidiaMember {
    /// The path inside the wheel, as RECORD lists it.
    pub member: String,
    pub dest: PathBuf,
    pub bytes: u64,
    /// Lower-case hex.
    pub sha256: String,
}

/// One wheel: the download (a [`FileJob`] of kind `NvidiaWheel`) and what to
/// take out of it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NvidiaJob {
    pub file: FileJob,
    pub install_root: PathBuf,
    pub members: Vec<NvidiaMember>,
}

impl NvidiaJob {
    /// The bytes the members take on disk once extracted.
    pub fn extracted_bytes(&self) -> u64 {
        self.members.iter().map(|m| m.bytes).sum()
    }
}

/// `windows` or `linux`: the platform this build installs for.
pub fn platform() -> &'static str {
    if cfg!(windows) { "windows" } else { "linux" }
}

/// The servers a point runs: its engine (`engine.kind`, default `serve`) and
/// `sd-server` when it has an image server or Crow starts one for it
/// (`CROW_IMAGE_MODEL_DIR` in `crow_env`).
pub fn point_servers(p: &Point) -> BTreeSet<String> {
    let mut s = BTreeSet::new();
    s.insert(p.engine["kind"].as_str().unwrap_or("serve").to_string());
    if !p.image_server.is_null() || p.crow_env.get("CROW_IMAGE_MODEL_DIR").is_some() {
        s.insert("sd-server".to_string());
    }
    s
}

/// The wheels `sel` needs on `platform`, in stack.json order.
pub fn jobs_for(stack: &Stack, sel: &Selection, platform: &str) -> Result<Vec<NvidiaJob>, String> {
    let install = sel.install_root.as_path();
    let servers: BTreeSet<String> =
        stack.points.iter().filter(|p| sel.points.contains(&p.id)).flat_map(point_servers).collect();
    stack
        .nvidia_files
        .iter()
        .filter(|w| w.platform == platform && w.servers.iter().any(|s| servers.contains(s)))
        .map(|w| job(w, install))
        .collect()
}

/// [`jobs_for`] on this build's platform.
pub fn jobs(stack: &Stack, sel: &Selection) -> Result<Vec<NvidiaJob>, String> {
    jobs_for(stack, sel, platform())
}

fn job(w: &NvidiaWheel, install: &Path) -> Result<NvidiaJob, String> {
    // ${MODELS} is not a root for these: resolve it to a path nothing matches
    let nowhere = Path::new("");
    let dest = resolve_path(&w.dest, install, nowhere)?;
    let name = w.url.rsplit('/').next().unwrap_or_default().to_string();
    let members = w
        .extract
        .iter()
        .map(|m| {
            let dest = resolve_path(&m.dest, install, nowhere)?;
            if !dest.starts_with(install) || dest == install {
                return Err(format!("{}: {} is not under the install root", w.id, m.dest));
            }
            Ok(NvidiaMember { member: m.member.clone(), dest, bytes: m.bytes, sha256: m.sha256.to_ascii_lowercase() })
        })
        .collect::<Result<_, String>>()?;
    Ok(NvidiaJob {
        file: FileJob {
            id: w.id.clone(),
            kind: FileKind::NvidiaWheel,
            url: w.url.clone(),
            local_rel: format!("pypi/{}/{name}", w.package),
            dest,
            bytes: w.bytes,
            sha256: w.sha256.to_ascii_lowercase(),
            points: Vec::new(),
        },
        install_root: install.to_path_buf(),
        members,
    })
}

/// Urlsafe base64 without padding (RECORD's `sha256=` value) to bytes.
pub fn b64url_decode(s: &str) -> Option<Vec<u8>> {
    let s = s.trim_end_matches('=');
    let mut out = Vec::with_capacity(s.len() * 3 / 4);
    let (mut acc, mut bits) = (0u32, 0u32);
    for c in s.bytes() {
        let v = match c {
            b'A'..=b'Z' => c - b'A',
            b'a'..=b'z' => c - b'a' + 26,
            b'0'..=b'9' => c - b'0' + 52,
            b'-' => 62,
            b'_' => 63,
            _ => return None,
        } as u32;
        acc = (acc << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((acc >> bits) as u8);
            acc &= (1 << bits) - 1;
        }
    }
    // a lone 6-bit tail, or leftover bits that are not zero, is not base64
    (bits < 6 && acc == 0).then_some(out)
}

/// RECORD (PEP 376/427): `path,sha256=<urlsafe b64>,size` per line, as
/// path -> (lower-case hex sha256, size). Lines without a sha256 (RECORD
/// itself) are left out; another hash algorithm is left out too.
pub fn parse_record(text: &str) -> Result<BTreeMap<String, (String, u64)>, String> {
    let mut out = BTreeMap::new();
    for line in text.lines().map(str::trim).filter(|l| !l.is_empty()) {
        let mut parts = line.rsplitn(3, ',');
        let (size, hash, path) = (parts.next(), parts.next(), parts.next());
        let (Some(size), Some(hash), Some(path)) = (size, hash, path) else {
            return Err(format!("RECORD line {line:?} is not path,hash,size"));
        };
        let Some(b64) = hash.strip_prefix("sha256=") else { continue };
        let digest = b64url_decode(b64).filter(|d| d.len() == 32).ok_or_else(|| format!("RECORD: bad sha256 for {path}"))?;
        let size: u64 = size.parse().map_err(|_| format!("RECORD: bad size for {path}"))?;
        let path = path.trim_matches('"').to_string();
        if out.insert(path.clone(), (hex::encode(digest), size)).is_some() {
            return Err(format!("RECORD lists {path} twice"));
        }
    }
    Ok(out)
}

/// A member name that stays inside the wheel: relative, `/`-separated, no
/// `.`, `..`, empty part, backslash or drive.
fn member_is_safe(name: &str) -> bool {
    !name.is_empty()
        && !name.starts_with('/')
        && !name.contains('\\')
        && name.split('/').all(|p| !p.is_empty() && p != "." && p != ".." && !p.contains(':'))
        && safe_rel(name).is_some()
}

/// `path` holds exactly `bytes` bytes hashing to `sha256`.
fn matches(path: &Path, bytes: u64, sha256: &str) -> bool {
    fs::metadata(path).is_ok_and(|m| m.is_file() && m.len() == bytes)
        && crate::verify::sha256_file(path).is_ok_and(|s| s.eq_ignore_ascii_case(sha256))
}

/// Every member is at its dest with its pinned bytes and sha256.
pub fn is_current(job: &NvidiaJob) -> bool {
    job.members.iter().all(|m| matches(&m.dest, m.bytes, &m.sha256))
}

fn with_suffix(p: &Path, suffix: &str) -> PathBuf {
    let mut s = p.as_os_str().to_os_string();
    s.push(suffix);
    PathBuf::from(s)
}

/// The wheel's RECORD: the one `<name>.dist-info/RECORD` at its top level.
fn read_record(zip: &mut zip::ZipArchive<fs::File>, shown: &str) -> Result<BTreeMap<String, (String, u64)>, String> {
    let names: Vec<String> = zip
        .file_names()
        .filter(|n| n.split('/').count() == 2 && n.ends_with(".dist-info/RECORD"))
        .map(str::to_string)
        .collect();
    let [name] = names.as_slice() else {
        return Err(format!("refusing {shown}: it holds {} dist-info RECORD files, expected one", names.len()));
    };
    let mut text = String::new();
    zip.by_name(name)
        .map_err(|e| format!("{shown}: {name}: {e}"))?
        .read_to_string(&mut text)
        .map_err(|e| format!("{shown}: {name}: {e}"))?;
    parse_record(&text).map_err(|e| format!("refusing {shown}: {e}"))
}

/// Rename `tmp` over `dest`; on Windows a dest a running server holds is moved
/// to `<dest>.old` first (a running image can be renamed, not replaced).
fn place(tmp: &Path, dest: &Path) -> Result<(), String> {
    let first = match fs::rename(tmp, dest) {
        Ok(()) => return Ok(()),
        Err(e) => e,
    };
    if cfg!(windows) && dest.exists() {
        let old = with_suffix(dest, ".old");
        let _ = fs::remove_file(&old);
        if fs::rename(dest, &old).is_ok() && fs::rename(tmp, dest).is_ok() {
            return Ok(());
        }
    }
    let _ = fs::remove_file(tmp);
    Err(format!("cannot put {} in place ({first}); stop the running server and try again", dest.display()))
}

fn extract_one(
    zip: &mut zip::ZipArchive<fs::File>,
    m: &NvidiaMember,
    shown: &str,
    cancel: &AtomicBool,
) -> Result<(), String> {
    let mut entry = zip.by_name(&m.member).map_err(|e| format!("{shown}: {}: {e}", m.member))?;
    if entry.is_dir() || entry.enclosed_name().is_none() {
        return Err(format!("refusing {shown}: {} is not a file inside the wheel", m.member));
    }
    if let Some(parent) = m.dest.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("cannot create {}: {e}", parent.display()))?;
    }
    let tmp = with_suffix(&m.dest, ".crowsetup-new");
    let _ = fs::remove_file(&tmp);
    let res = (|| -> Result<(), String> {
        let mut out = fs::File::create(&tmp).map_err(|e| format!("cannot write {}: {e}", tmp.display()))?;
        let mut h = Sha256Stream::new();
        let mut buf = vec![0u8; 1 << 20];
        let mut n = 0u64;
        loop {
            if cancel.load(Ordering::SeqCst) {
                return Err("cancelled".into());
            }
            let got = entry.read(&mut buf).map_err(|e| format!("{shown}: {}: {e}", m.member))?;
            if got == 0 {
                break;
            }
            n += got as u64;
            if n > m.bytes {
                return Err(format!("refusing {shown}: {} is larger than its RECORD says", m.member));
            }
            h.update(&buf[..got]);
            out.write_all(&buf[..got]).map_err(|e| format!("cannot write {}: {e}", tmp.display()))?;
        }
        out.flush().map_err(|e| format!("cannot write {}: {e}", tmp.display()))?;
        drop(out);
        let sha = h.finish();
        if n != m.bytes || sha != m.sha256 {
            return Err(format!(
                "refusing {shown}: {} does not match its RECORD ({n} bytes, sha256 {sha}; expected {} bytes, {})",
                m.member, m.bytes, m.sha256
            ));
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            // shared libraries as the packages shipped them (pack-release.sh: 0755)
            let lib = m.dest.file_name().is_some_and(|n| n.to_string_lossy().contains(".so"));
            fs::set_permissions(&tmp, fs::Permissions::from_mode(if lib { 0o755 } else { 0o644 }))
                .map_err(|e| format!("cannot set the mode of {}: {e}", tmp.display()))?;
        }
        place(&tmp, &m.dest)
    })();
    if res.is_err() {
        let _ = fs::remove_file(&tmp);
    }
    res
}

/// Take the members out of the downloaded wheel. Returns the one-line summary.
pub fn unpack(job: &NvidiaJob, cancel: &AtomicBool) -> Result<String, String> {
    let shown = job.file.dest.file_name().unwrap_or_default().to_string_lossy().into_owned();
    let file = fs::File::open(&job.file.dest).map_err(|e| format!("cannot open {}: {e}", job.file.dest.display()))?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| format!("{shown} is not a readable wheel: {e}"))?;
    let record = read_record(&mut zip, &shown)?;
    // every member is checked before a single byte is written
    for m in &job.members {
        if !member_is_safe(&m.member) {
            return Err(format!("refusing {shown}: member {:?} leaves the wheel", m.member));
        }
        if !m.dest.starts_with(&job.install_root) || m.dest == job.install_root {
            return Err(format!("refusing {shown}: {} is not under {}", m.dest.display(), job.install_root.display()));
        }
        match record.get(&m.member) {
            None => return Err(format!("refusing {shown}: its RECORD does not list {} with a sha256", m.member)),
            Some((sha, bytes)) if *bytes != m.bytes || !sha.eq_ignore_ascii_case(&m.sha256) => {
                return Err(format!(
                    "refusing {shown}: its RECORD gives {} as {bytes} bytes, sha256 {sha}; stack.json pins {} bytes, {}",
                    m.member, m.bytes, m.sha256
                ));
            }
            Some(_) => {}
        }
    }
    let (mut written, mut kept) = (0usize, 0usize);
    for m in &job.members {
        if matches(&m.dest, m.bytes, &m.sha256) {
            kept += 1;
            continue;
        }
        extract_one(&mut zip, m, &shown, cancel)?;
        written += 1;
    }
    let mut s = format!("{shown} from NVIDIA ({written} files written");
    if kept > 0 {
        s.push_str(&format!(", {kept} already in place"));
    }
    s.push(')');
    Ok(s)
}
