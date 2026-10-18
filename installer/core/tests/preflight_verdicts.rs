//! T2: nvidia-smi parsing and the verdict table. Parsing and verdicts take no
//! probe, so every machine below is a fixture.

use crowsetup_core::api::Blocked;
use crowsetup_core::preflight::{Facts, Gpu, nearest_existing, parse_nvidia_smi, pick_gpu, verdicts, webview2_pv_installed};
use crowsetup_core::stack::Stack;

/// Captured once on robin's machine, 2026-10-01:
/// `nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader,nounits`
/// (CRLF as Windows prints it).
const RTX5090_REAL: &str = "NVIDIA GeForce RTX 5090, 32607, 12.0\r\n";
/// Same machine, GlobalMemoryStatusEx ullTotalPhys (a 64 GB host shows 63.38 GiB).
const RAM_64GB_REAL: u64 = 68_053_331_968;
const RTX4090: &str = "NVIDIA GeForce RTX 4090, 24564, 8.9\r\n";
const RTX5080: &str = "NVIDIA GeForce RTX 5080, 16303, 12.0\r\n";
const TWO_GPUS: &str = "NVIDIA GeForce RTX 4090, 24564, 8.9\r\nNVIDIA GeForce RTX 5090, 32607, 12.0\r\n";
const NO_GPU: &str = "No devices were found\r\n";
const GIB: u64 = 1 << 30;

fn gpu(name: &str, vram: u64, cc: &str) -> Gpu {
    Gpu { name: name.into(), vram_mib: Some(vram), compute_cap: Some(cc.into()) }
}

fn robins_machine() -> Facts {
    Facts {
        os_64bit: true,
        gpus: parse_nvidia_smi(RTX5090_REAL),
        ram_bytes: RAM_64GB_REAL,
        disk_free_bytes: 500 * GIB,
        webview2: true,
    }
}

fn blocked(list: &[Blocked]) -> Vec<(&str, &str)> {
    list.iter().map(|b| (b.point.as_str(), b.reason.as_str())).collect()
}

#[test]
fn parses_the_real_rtx5090_line() {
    assert_eq!(parse_nvidia_smi(RTX5090_REAL), vec![gpu("NVIDIA GeForce RTX 5090", 32607, "12.0")]);
}

#[test]
fn parses_synthetic_lines() {
    assert_eq!(parse_nvidia_smi(RTX4090), vec![gpu("NVIDIA GeForce RTX 4090", 24564, "8.9")]);
    assert_eq!(parse_nvidia_smi(NO_GPU), vec![]);
    assert_eq!(parse_nvidia_smi(""), vec![]);
    assert_eq!(
        parse_nvidia_smi(TWO_GPUS),
        vec![gpu("NVIDIA GeForce RTX 4090", 24564, "8.9"), gpu("NVIDIA GeForce RTX 5090", 32607, "12.0")]
    );
    // a field the driver cannot read
    assert_eq!(
        parse_nvidia_smi("NVIDIA GeForce RTX 5090, [N/A], 12.0\n"),
        vec![Gpu { name: "NVIDIA GeForce RTX 5090".into(), vram_mib: None, compute_cap: Some("12.0".into()) }]
    );
}

#[test]
fn picks_the_blackwell_card_of_two() {
    let gpus = parse_nvidia_smi(TWO_GPUS);
    assert_eq!(pick_gpu(&gpus).unwrap().name, "NVIDIA GeForce RTX 5090");
    assert_eq!(pick_gpu(&[]), None);
}

#[test]
fn robins_machine_runs_everything() {
    let r = verdicts(&robins_machine(), &Stack::embedded());
    assert_eq!(r.hard_block, None);
    assert_eq!(r.blocked, vec![]);
    assert_eq!(r.gpu_name.as_deref(), Some("NVIDIA GeForce RTX 5090"));
    assert_eq!(r.vram_mib, Some(32607));
    assert_eq!(r.compute_cap.as_deref(), Some("12.0"));
    assert_eq!(r.ram_bytes, RAM_64GB_REAL);
    assert_eq!(r.disk_free_bytes, 500 * GIB);
    assert!(r.os_64bit && r.webview2);
}

#[test]
fn hard_blocks() {
    let s = Stack::embedded();
    let mut f = robins_machine();
    f.os_64bit = false;
    let r = verdicts(&f, &s);
    let want = if cfg!(windows) {
        "Crow needs 64-bit Windows, and this machine runs 32-bit Windows."
    } else {
        "Crow needs 64-bit Linux, and this machine runs 32-bit Linux."
    };
    assert_eq!(r.hard_block.as_deref(), Some(want));
    assert_eq!(r.blocked, vec![], "a hard block says it once, not per point");

    let mut f = robins_machine();
    f.gpus = parse_nvidia_smi(NO_GPU);
    let r = verdicts(&f, &s);
    assert_eq!(r.hard_block.as_deref(), Some("Crow needs an NVIDIA RTX 50 series GPU, and nvidia-smi reports none on this machine."));
    assert_eq!(r.gpu_name, None);

    let mut f = robins_machine();
    f.gpus = parse_nvidia_smi(RTX4090);
    let r = verdicts(&f, &s);
    assert_eq!(
        r.hard_block.as_deref(),
        Some("Crow needs an NVIDIA RTX 50 series GPU, and this machine has an NVIDIA GeForce RTX 4090 (compute 8.9).")
    );
    assert_eq!(r.compute_cap.as_deref(), Some("8.9"));
    assert_eq!(r.blocked, vec![]);

    let mut f = robins_machine();
    f.gpus = parse_nvidia_smi(TWO_GPUS);
    let r = verdicts(&f, &s);
    assert_eq!(r.hard_block, None);
    assert_eq!(r.gpu_name.as_deref(), Some("NVIDIA GeForce RTX 5090"));
}

#[test]
fn sentences_are_short_and_plain() {
    let s = Stack::embedded();
    let mut machines = vec![];
    for (os, gpus, ram, disk) in [
        (false, RTX5090_REAL, RAM_64GB_REAL, 500 * GIB),
        (true, NO_GPU, RAM_64GB_REAL, 500 * GIB),
        (true, RTX4090, RAM_64GB_REAL, 500 * GIB),
        (true, RTX5080, 16 * GIB, 10 * GIB),
    ] {
        machines.push(Facts { os_64bit: os, gpus: parse_nvidia_smi(gpus), ram_bytes: ram, disk_free_bytes: disk, webview2: true });
    }
    for f in machines {
        let r = verdicts(&f, &s);
        for text in r.hard_block.iter().chain(r.blocked.iter().map(|b| &b.reason)) {
            assert!(!text.contains('\u{2014}') && !text.contains('\u{2013}'), "dash in {text:?}");
            assert!(text.len() <= 110, "too long: {text:?}");
            assert!(text.ends_with('.'), "{text:?}");
        }
    }
}

#[test]
fn verdict_table_ram_vram_disk() {
    let s = Stack::embedded();

    // 32 GB of RAM: Flash-Next and GLM-5.3-Flash (#365) pin up to 46 GiB host RAM
    let mut f = robins_machine();
    f.ram_bytes = 34_190_000_000; // a "32 GB" host, 31.84 GiB visible
    assert_eq!(
        blocked(&verdicts(&f, &s).blocked),
        vec![
            ("flash-next", "Needs 64 GB RAM. This machine has 32 GB."),
            ("glm53-flash", "Needs 64 GB RAM. This machine has 32 GB."),
            ("media-stack", "Needs 64 GB RAM. This machine has 32 GB."),
        ]
    );

    // 60 GiB visible still counts as a 64 GB host (firmware and iGPU reserve some)
    f.ram_bytes = 60 * GIB;
    assert_eq!(verdicts(&f, &s).blocked, vec![]);
    f.ram_bytes = 60 * GIB - 1;
    assert_eq!(
        blocked(&verdicts(&f, &s).blocked),
        vec![
            ("flash-next", "Needs 64 GB RAM. This machine has 60 GB."),
            ("glm53-flash", "Needs 64 GB RAM. This machine has 60 GB."),
            ("media-stack", "Needs 64 GB RAM. This machine has 60 GB."),
        ]
    );

    // an RTX 5080: Blackwell, but 16 GB of VRAM blocks every point
    let mut f = robins_machine();
    f.gpus = parse_nvidia_smi(RTX5080);
    let why = "Needs 32 GB of VRAM. This GPU has 16 GB.";
    let r = verdicts(&f, &s);
    assert_eq!(r.hard_block, None);
    assert_eq!(blocked(&r.blocked), vec![("flash-next", why), ("27b", why), ("glm53-flash", why), ("image-stack", why), ("media-stack", why)]);

    // 50 GB free: the 27B fits (17.5 GiB), Flash-Next (98.4 GiB) and the image stack (63.4 GiB, #403) do not
    let mut f = robins_machine();
    f.disk_free_bytes = 50_000_000_000;
    assert_eq!(
        blocked(&verdicts(&f, &s).blocked),
        vec![
            ("flash-next", "Needs 99 GB free disk. This drive has 46 GB free."),
            ("glm53-flash", "Needs 117 GB free disk. This drive has 46 GB free."),
            ("image-stack", "Needs 64 GB free disk. This drive has 46 GB free."),
            ("media-stack", "Needs 99 GB free disk. This drive has 46 GB free."),
        ]
    );

    // exactly the point's own need is enough
    let mut f = robins_machine();
    f.disk_free_bytes = s.point("image-stack").unwrap().preflight.disk_bytes;
    assert_eq!(
        blocked(&verdicts(&f, &s).blocked),
        vec![
            ("flash-next", "Needs 99 GB free disk. This drive has 63 GB free."),
            ("glm53-flash", "Needs 117 GB free disk. This drive has 63 GB free."),
            ("media-stack", "Needs 99 GB free disk. This drive has 63 GB free."),
        ]
    );

    // one reason per point, the first of VRAM, RAM, disk
    let mut f = robins_machine();
    f.ram_bytes = 16 * GIB;
    f.disk_free_bytes = 10 * GIB;
    assert_eq!(
        blocked(&verdicts(&f, &s).blocked),
        vec![
            ("flash-next", "Needs 64 GB RAM. This machine has 16 GB."),
            ("27b", "Needs 18 GB free disk. This drive has 10 GB free."),
            ("glm53-flash", "Needs 64 GB RAM. This machine has 16 GB."),
            ("image-stack", "Needs 64 GB free disk. This drive has 10 GB free."),
            ("media-stack", "Needs 64 GB RAM. This machine has 16 GB."),
        ]
    );

    // unknown VRAM is not a block
    let mut f = robins_machine();
    f.gpus = vec![Gpu { name: "NVIDIA GeForce RTX 5090".into(), vram_mib: None, compute_cap: Some("12.0".into()) }];
    assert_eq!(verdicts(&f, &s).blocked, vec![]);
}

#[test]
fn webview2_pv_values() {
    assert!(webview2_pv_installed(Some("141.0.3537.71")));
    assert!(!webview2_pv_installed(Some("0.0.0.0")));
    assert!(!webview2_pv_installed(Some("")));
    assert!(!webview2_pv_installed(None));
}

#[test]
fn nearest_existing_walks_up() {
    let tmp = tempfile::tempdir().unwrap();
    let deep = tmp.path().join("Crow").join("not").join("yet");
    assert_eq!(nearest_existing(&deep).unwrap(), tmp.path());
    assert_eq!(nearest_existing(tmp.path()).unwrap(), tmp.path());
}

#[cfg(windows)]
#[test]
fn live_probe_reads_this_machine() {
    let tmp = tempfile::tempdir().unwrap();
    let r = crowsetup_core::preflight::run(&Stack::embedded(), &tmp.path().join("Crow"));
    eprintln!("{r:?}"); // shown with --nocapture: what this machine reports
    assert!(r.os_64bit);
    assert!(r.ram_bytes > 1 << 30, "{}", r.ram_bytes);
    assert!(r.disk_free_bytes > 0);
}

/// #342: with a linking `--source` a point's disk need is what cannot be linked.
#[test]
fn the_disk_need_can_be_handed_in() {
    let s = Stack::embedded();
    let mut f = robins_machine();
    f.disk_free_bytes = 57 * GIB;
    let r = verdicts(&f, &s);
    assert!(r.blocked.iter().any(|b| b.point == "image-stack" && b.reason.contains("free disk")), "{:?}", r.blocked);
    let r = crowsetup_core::preflight::verdicts_with_disk(&f, &s, &|_p| GIB);
    assert!(r.blocked.is_empty(), "{:?}", r.blocked);
}

#[test]
fn ram_comes_from_proc_meminfo() {
    let text = "MemTotal:       65536000 kB\nMemFree:         1000 kB\n";
    assert_eq!(crowsetup_core::preflight::parse_meminfo(text), 65_536_000 * 1024);
    assert_eq!(crowsetup_core::preflight::parse_meminfo("nothing"), 0);
}
