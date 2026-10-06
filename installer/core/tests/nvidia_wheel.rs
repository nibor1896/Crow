//! NVIDIA's CUDA libraries from NVIDIA's own wheels (crate::nvidia): which
//! wheels a selection needs per platform, and the extraction against the
//! wheel's RECORD, on small synthetic wheels (no network).

use crowsetup_core::api::{FileJob, FileKind, Selection};
use crowsetup_core::nvidia::{self, NvidiaJob, NvidiaMember};
use crowsetup_core::stack::Stack;
use crowsetup_core::verify::Sha256Stream;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;

fn sha_hex(b: &[u8]) -> String {
    let mut h = Sha256Stream::new();
    h.update(b);
    h.finish()
}

/// Urlsafe base64 without padding, as RECORD writes it.
fn b64url(b: &[u8]) -> String {
    const A: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut out = String::new();
    for c in b.chunks(3) {
        let n = (c[0] as u32) << 16 | (*c.get(1).unwrap_or(&0) as u32) << 8 | *c.get(2).unwrap_or(&0) as u32;
        for i in 0..=c.len() {
            out.push(A[(n >> (18 - 6 * i) & 63) as usize] as char);
        }
    }
    out
}

fn sha_b64(b: &[u8]) -> String {
    b64url(&hex::decode(sha_hex(b)).unwrap())
}

const DLL: &[u8] = b"MZ fake cublas64_13.dll bytes";
const LT: &[u8] = b"MZ fake cublasLt64_13.dll, a little longer";
const EULA: &[u8] = b"NVIDIA CUDA Toolkit EULA (fixture)";
const DIST: &str = "nvidia_cublas-13.6.0.2.dist-info";

/// A wheel with `files` and a RECORD that lists `record` (path, bytes it claims).
fn wheel(dir: &Path, files: &[(&str, &[u8])], record: &[(&str, &[u8])]) -> PathBuf {
    let path = dir.join("nvidia_cublas-13.6.0.2-py3-none-win_amd64.whl");
    let mut z = zip::ZipWriter::new(fs::File::create(&path).unwrap());
    let opts = zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
    for (name, data) in files {
        z.start_file(*name, opts).unwrap();
        z.write_all(data).unwrap();
    }
    let mut rec = String::new();
    for (name, data) in record {
        rec.push_str(&format!("{name},sha256={},{}\n", sha_b64(data), data.len()));
    }
    rec.push_str(&format!("{DIST}/RECORD,,\n"));
    z.start_file(format!("{DIST}/RECORD"), opts).unwrap();
    z.write_all(rec.as_bytes()).unwrap();
    z.finish().unwrap();
    path
}

fn member(name: &str, dest: PathBuf, data: &[u8]) -> NvidiaMember {
    NvidiaMember { member: name.into(), dest, bytes: data.len() as u64, sha256: sha_hex(data) }
}

fn job(wheel: PathBuf, root: &Path, members: Vec<NvidiaMember>) -> NvidiaJob {
    NvidiaJob {
        file: FileJob {
            id: "cublas-windows".into(),
            kind: FileKind::NvidiaWheel,
            url: "https://example.invalid/w.whl".into(),
            local_rel: "pypi/w.whl".into(),
            dest: wheel,
            bytes: 1,
            sha256: "0".repeat(64),
            points: vec![],
        },
        install_root: root.to_path_buf(),
        members,
    }
}

/// The good wheel and its job: two DLLs into bin/, the EULA into licenses/.
fn good(tmp: &Path) -> (NvidiaJob, PathBuf) {
    let files: &[(&str, &[u8])] = &[
        ("nvidia/cu13/bin/x86_64/cublas64_13.dll", DLL),
        ("nvidia/cu13/bin/x86_64/cublasLt64_13.dll", LT),
        ("nvidia/cu13/include/cublas.h", b"/* header we do not take */"),
        ("nvidia_cublas-13.6.0.2.dist-info/licenses/License.txt", EULA),
    ];
    let w = wheel(tmp, files, files);
    let root = tmp.join("Crow");
    let bin = root.join("bin");
    let j = job(
        w,
        &root,
        vec![
            member("nvidia/cu13/bin/x86_64/cublas64_13.dll", bin.join("cublas64_13.dll"), DLL),
            member("nvidia/cu13/bin/x86_64/cublasLt64_13.dll", bin.join("cublasLt64_13.dll"), LT),
            member(
                "nvidia_cublas-13.6.0.2.dist-info/licenses/License.txt",
                root.join("licenses").join("NVIDIA-CUDA-EULA.txt"),
                EULA,
            ),
        ],
    );
    (j, root)
}

fn unpack(j: &NvidiaJob) -> Result<String, String> {
    nvidia::unpack(j, &AtomicBool::new(false))
}

fn no_leftovers(dir: &Path) {
    if let Ok(rd) = fs::read_dir(dir) {
        for e in rd.flatten() {
            let n = e.file_name().to_string_lossy().into_owned();
            assert!(!n.ends_with(".crowsetup-new"), "temporary file left behind: {n}");
        }
    }
}

#[test]
fn the_named_members_land_at_their_dests_and_nothing_else() {
    let tmp = tempfile::tempdir().unwrap();
    let (j, root) = good(tmp.path());
    assert!(!nvidia::is_current(&j));
    let said = unpack(&j).unwrap();
    assert!(said.contains("3 files written"), "{said}");
    assert_eq!(fs::read(root.join("bin").join("cublas64_13.dll")).unwrap(), DLL);
    assert_eq!(fs::read(root.join("bin").join("cublasLt64_13.dll")).unwrap(), LT);
    assert_eq!(fs::read(root.join("licenses").join("NVIDIA-CUDA-EULA.txt")).unwrap(), EULA);
    assert!(!root.join("nvidia").exists() && !root.join("bin").join("cublas.h").exists(), "only the named members");
    assert_eq!(fs::read_dir(root.join("bin")).unwrap().count(), 2);
    assert!(nvidia::is_current(&j));
    no_leftovers(&root.join("bin"));
}

#[test]
fn a_file_an_older_package_left_with_the_same_bytes_is_kept() {
    let tmp = tempfile::tempdir().unwrap();
    let (j, root) = good(tmp.path());
    fs::create_dir_all(root.join("bin")).unwrap();
    fs::write(root.join("bin").join("cublas64_13.dll"), DLL).unwrap();
    let said = unpack(&j).unwrap();
    assert!(said.contains("2 files written") && said.contains("1 already in place"), "{said}");
    // and a second run writes nothing
    let again = unpack(&j).unwrap();
    assert!(again.contains("0 files written") && again.contains("3 already in place"), "{again}");
}

#[test]
fn a_different_file_at_the_dest_is_replaced() {
    let tmp = tempfile::tempdir().unwrap();
    let (j, root) = good(tmp.path());
    fs::create_dir_all(root.join("bin")).unwrap();
    fs::write(root.join("bin").join("cublasLt64_13.dll"), b"an older build").unwrap();
    unpack(&j).unwrap();
    assert_eq!(fs::read(root.join("bin").join("cublasLt64_13.dll")).unwrap(), LT);
    assert!(nvidia::is_current(&j));
}

#[test]
fn a_member_whose_bytes_do_not_match_its_record_is_refused() {
    let tmp = tempfile::tempdir().unwrap();
    // RECORD and stack.json agree on DLL's hash; the wheel carries other bytes
    let w = wheel(
        tmp.path(),
        &[("nvidia/cu13/bin/x86_64/cublas64_13.dll", b"MZ tampered bytes, same story")],
        &[("nvidia/cu13/bin/x86_64/cublas64_13.dll", DLL)],
    );
    let root = tmp.path().join("Crow");
    let j = job(w, &root, vec![member("nvidia/cu13/bin/x86_64/cublas64_13.dll", root.join("bin").join("cublas64_13.dll"), DLL)]);
    let e = unpack(&j).unwrap_err();
    assert!(e.contains("does not match its RECORD"), "{e}");
    assert!(!root.join("bin").join("cublas64_13.dll").exists());
    no_leftovers(&root.join("bin"));
}

#[test]
fn a_record_that_disagrees_with_stack_json_refuses_before_writing() {
    let tmp = tempfile::tempdir().unwrap();
    let files: &[(&str, &[u8])] = &[("nvidia/cu13/bin/x86_64/cublas64_13.dll", DLL), ("nvidia/cu13/bin/x86_64/cublasLt64_13.dll", LT)];
    let w = wheel(tmp.path(), files, files);
    let root = tmp.path().join("Crow");
    let bin = root.join("bin");
    let mut wrong = member("nvidia/cu13/bin/x86_64/cublasLt64_13.dll", bin.join("cublasLt64_13.dll"), LT);
    wrong.sha256 = "ab".repeat(32);
    // the first member is fine, the second is pinned differently: nothing is written
    let j = job(w, &root, vec![member("nvidia/cu13/bin/x86_64/cublas64_13.dll", bin.join("cublas64_13.dll"), DLL), wrong]);
    let e = unpack(&j).unwrap_err();
    assert!(e.contains("stack.json pins"), "{e}");
    assert!(!bin.exists(), "refused before a single byte");
}

#[test]
fn a_member_missing_from_record_is_refused() {
    let tmp = tempfile::tempdir().unwrap();
    let w = wheel(tmp.path(), &[("nvidia/cu13/bin/x86_64/cublas64_13.dll", DLL)], &[]);
    let root = tmp.path().join("Crow");
    let j = job(w, &root, vec![member("nvidia/cu13/bin/x86_64/cublas64_13.dll", root.join("bin").join("cublas64_13.dll"), DLL)]);
    let e = unpack(&j).unwrap_err();
    assert!(e.contains("RECORD does not list"), "{e}");
}

#[test]
fn a_member_path_that_climbs_out_is_refused() {
    let tmp = tempfile::tempdir().unwrap();
    for name in ["../evil.dll", "nvidia/../../evil.dll", "/abs/evil.dll", "C:/evil.dll", "nvidia\\evil.dll"] {
        let w = wheel(tmp.path(), &[(name, DLL)], &[(name, DLL)]);
        let root = tmp.path().join("Crow");
        let j = job(w, &root, vec![member(name, root.join("bin").join("evil.dll"), DLL)]);
        let e = unpack(&j).unwrap_err();
        assert!(e.contains("leaves the wheel"), "{name}: {e}");
        assert!(!root.join("bin").exists(), "{name}");
    }
}

#[test]
fn a_dest_outside_the_install_root_is_refused() {
    let tmp = tempfile::tempdir().unwrap();
    let files: &[(&str, &[u8])] = &[("nvidia/cu13/bin/x86_64/cublas64_13.dll", DLL)];
    let w = wheel(tmp.path(), files, files);
    let root = tmp.path().join("Crow");
    let j = job(w, &root, vec![member(files[0].0, tmp.path().join("elsewhere").join("cublas64_13.dll"), DLL)]);
    let e = unpack(&j).unwrap_err();
    assert!(e.contains("is not under"), "{e}");
    assert!(!tmp.path().join("elsewhere").exists());
}

#[test]
fn a_wheel_without_one_record_is_refused() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("no-record.whl");
    let mut z = zip::ZipWriter::new(fs::File::create(&path).unwrap());
    z.start_file("nvidia/cu13/bin/x86_64/cublas64_13.dll", zip::write::SimpleFileOptions::default()).unwrap();
    z.write_all(DLL).unwrap();
    z.finish().unwrap();
    let root = tmp.path().join("Crow");
    let j = job(path, &root, vec![member("nvidia/cu13/bin/x86_64/cublas64_13.dll", root.join("bin").join("cublas64_13.dll"), DLL)]);
    let e = unpack(&j).unwrap_err();
    assert!(e.contains("RECORD"), "{e}");
}

#[test]
fn record_parsing_and_urlsafe_base64() {
    assert_eq!(nvidia::b64url_decode(&b64url(b"\xfb\xff\xfe")).unwrap(), b"\xfb\xff\xfe");
    assert_eq!(nvidia::b64url_decode("-_8").unwrap(), vec![0xfb, 0xff]);
    assert!(nvidia::b64url_decode("a+b/").is_none(), "standard base64 is not urlsafe");
    // the real RECORD line of cublas64_13.dll in nvidia-cublas 13.6.0.2 win_amd64
    let r = nvidia::parse_record(
        "nvidia/cu13/bin/x86_64/cublas64_13.dll,sha256=jGusJEdK8pYn7JZQACWl1BCht-j_oA4f4TsXgfxrPdw,52697712\r\n\
         nvidia_cublas-13.6.0.2.dist-info/RECORD,,\r\n",
    )
    .unwrap();
    assert_eq!(
        r["nvidia/cu13/bin/x86_64/cublas64_13.dll"],
        ("8c6bac24474af29627ec96500025a5d410a1b7e8ffa00e1fe13b1781fc6b3ddc".to_string(), 52697712)
    );
    assert_eq!(r.len(), 1, "RECORD's own line carries no hash");
    assert!(nvidia::parse_record("a,sha256=AAAA,1\na,sha256=AAAA,1\n").is_err());
}

// ------------------------------------------------- which wheels, per platform

fn sel(points: &[&str], root: &Path) -> Selection {
    Selection { points: points.iter().map(|s| s.to_string()).collect(), install_root: root.to_path_buf(), shortcut_dir: None }
}

fn ids(points: &[&str], platform: &str) -> Vec<String> {
    let root = PathBuf::from("crow-root");
    nvidia::jobs_for(&Stack::embedded(), &sel(points, &root), platform)
        .unwrap()
        .into_iter()
        .map(|j| j.file.id)
        .collect()
}

#[test]
fn every_point_gets_the_wheels_of_the_servers_it_runs() {
    // crow-nest's serve loads NVRTC; llama-server and sd-server load cuBLAS
    assert_eq!(ids(&["flash-next"], "windows"), ["nvrtc-windows"]);
    assert_eq!(ids(&["27b"], "windows"), ["nvrtc-windows"]);
    assert_eq!(ids(&["image-stack"], "windows"), ["nvrtc-windows", "cublas-windows"]);
    assert_eq!(ids(&["media-stack"], "windows"), ["cublas-windows"], "llama-server + sd-server, no serve");
    assert_eq!(ids(&["flash-next", "media-stack"], "windows"), ["nvrtc-windows", "cublas-windows"]);
    // Linux: sd-server also links the CUDA runtime from cuda/lib
    assert_eq!(ids(&["flash-next"], "linux"), ["nvrtc-linux"]);
    assert_eq!(ids(&["image-stack"], "linux"), ["nvrtc-linux", "cublas-linux", "cudart-linux"]);
    assert!(ids(&[], "windows").is_empty() && ids(&[], "linux").is_empty());
}

#[test]
fn the_libraries_land_where_the_packages_used_to_carry_them() {
    let root = PathBuf::from("crow-root");
    let stack = Stack::embedded();
    let dests = |platform: &str| -> Vec<(String, PathBuf, u64)> {
        nvidia::jobs_for(&stack, &sel(&["image-stack"], &root), platform)
            .unwrap()
            .into_iter()
            .flat_map(|j| j.members.into_iter().map(|m| (m.member, m.dest, m.bytes)))
            .collect()
    };
    let at = |parts: &[&str]| parts.iter().fold(root.clone(), |p, x| p.join(x));
    let win = dests("windows");
    for (name, bytes) in [
        ("nvrtc64_130_0.dll", 101_385_328),
        ("nvrtc-builtins64_133.dll", 6_684_784),
        ("cublas64_13.dll", 52_697_712),
        ("cublasLt64_13.dll", 463_655_536),
    ] {
        assert!(win.iter().any(|(_, d, b)| *d == at(&["bin", name]) && *b == bytes), "{name}: {win:?}");
    }
    assert!(!win.iter().any(|(m, ..)| m.contains("nvblas")), "not nvblas");
    let lin = dests("linux");
    for (member, dest) in [
        ("nvidia/cu13/lib/libnvrtc.so.13", at(&["bin", "libnvrtc.so"])),
        ("nvidia/cu13/lib/libnvrtc-builtins.so.13.3", at(&["bin", "libnvrtc-builtins.so.13.3"])),
        ("nvidia/cu13/lib/libcublas.so.13", at(&["cuda", "lib", "libcublas.so.13"])),
        ("nvidia/cu13/lib/libcublasLt.so.13", at(&["cuda", "lib", "libcublasLt.so.13"])),
        ("nvidia/cu13/lib/libcudart.so.13", at(&["cuda", "lib", "libcudart.so.13"])),
    ] {
        assert!(lin.iter().any(|(m, d, _)| m == member && *d == dest), "{member}: {lin:?}");
    }
    // the EULA every wheel carries, beside ComfyUI's licence
    assert!(win.iter().chain(&lin).filter(|(m, ..)| m.ends_with("licenses/License.txt")).all(|(_, d, _)| *d == at(&["licenses", "NVIDIA-CUDA-EULA.txt"])));
}

#[test]
fn the_wheels_are_pinned_downloads_from_pypi() {
    let root = PathBuf::from("crow-root");
    let stack = Stack::embedded();
    assert_eq!(stack.nvidia_files.len(), 5);
    for platform in ["windows", "linux"] {
        for j in nvidia::jobs_for(&stack, &sel(&["image-stack", "media-stack"], &root), platform).unwrap() {
            let f = &j.file;
            assert_eq!(f.kind, FileKind::NvidiaWheel);
            assert!(f.url.starts_with("https://files.pythonhosted.org/packages/") && f.url.ends_with(".whl"), "{}", f.url);
            assert_eq!(f.sha256.len(), 64);
            assert!(f.points.is_empty());
            assert_eq!(f.dest, root.join("setup").join("downloads").join(f.url.rsplit('/').next().unwrap()));
            assert!(j.members.iter().all(|m| m.sha256.len() == 64 && m.bytes > 0));
        }
    }
    let lic = &stack.raw["licenses"]["nvidia-cuda-eula"];
    assert_eq!(lic["show_at_install"], true);
    assert_eq!(lic["url"], "https://docs.nvidia.com/cuda/eula/index.html");
    assert!(stack.nvidia_files.iter().all(|w| w.license == "nvidia-cuda-eula"));
}

// ------------------------------------------ with the packages that carried them

/// A flat engine zip (crow-nest pack-engine) with its MANIFEST.json.
fn engine_zip(dir: &Path, version: &str, files: &[(&str, &[u8])]) -> PathBuf {
    let path = dir.join(format!("crow-nest-engine-{version}-win-x64.zip"));
    let mut z = zip::ZipWriter::new(fs::File::create(&path).unwrap());
    let opts = zip::write::SimpleFileOptions::default();
    let mut manifest = Vec::new();
    for (name, data) in files {
        z.start_file(*name, opts).unwrap();
        z.write_all(data).unwrap();
        manifest.push(serde_json::json!({"path": name, "bytes": data.len(), "sha256": sha_hex(data)}));
    }
    z.start_file("MANIFEST.json", opts).unwrap();
    z.write_all(serde_json::to_string(&manifest).unwrap().as_bytes()).unwrap();
    z.finish().unwrap();
    path
}

#[test]
fn an_engine_without_nvrtc_installs_and_the_wheel_puts_nvrtc_back() {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().join("Crow");
    const NVRTC: &[u8] = b"MZ fake nvrtc64_130_0.dll";
    // the older engine still carried NVRTC
    let old = engine_zip(tmp.path(), "0.9.1", &[("serve.exe", b"MZ serve 0.9.1"), ("nvrtc64_130_0.dll", NVRTC)]);
    crowsetup_core::layout::install_engine_package(&old, &root).unwrap();
    let dll = root.join("bin").join("nvrtc64_130_0.dll");
    assert_eq!(fs::read(&dll).unwrap(), NVRTC);
    // the new one does not: its manifest drops the file, the install removes it
    let new = engine_zip(tmp.path(), "0.9.2", &[("serve.exe", b"MZ serve 0.9.2")]);
    crowsetup_core::layout::install_engine_package(&new, &root).unwrap();
    assert!(!dll.exists());
    // and the nvidia step that follows puts NVIDIA's own bytes there
    let files: &[(&str, &[u8])] = &[("nvidia/cu13/bin/x86_64/nvrtc64_130_0.dll", NVRTC)];
    let w = wheel(tmp.path(), files, files);
    let j = job(w, &root, vec![member(files[0].0, dll.clone(), NVRTC)]);
    unpack(&j).unwrap();
    assert_eq!(fs::read(&dll).unwrap(), NVRTC);
    assert!(nvidia::is_current(&j));
}
