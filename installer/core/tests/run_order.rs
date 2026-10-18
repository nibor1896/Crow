//! T4: the run order, resume, pause, retry and quit, on the fake Steps.

use crowsetup_core::api::{Blocked, Command, Event, StepStatus};
use crowsetup_core::run::testing::{expected_order, options, report, run_once, scenarios, selection, FakeSteps};
use crowsetup_core::run::{run, Input, Outcome};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{channel, Receiver, Sender};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

fn root() -> PathBuf {
    PathBuf::from(r"C:\crowsetup-test-root")
}

/// A run on its own thread with an open input channel.
struct Live {
    tx: Option<Sender<Input>>,
    events: Receiver<Event>,
    seen: Vec<Event>,
    handle: Option<JoinHandle<Outcome>>,
}

impl Live {
    fn start(steps: &FakeSteps, root: &Path) -> Live {
        let (tx, rx) = channel();
        let (etx, events) = channel();
        let mut s = steps.clone();
        let opts = options(root);
        let handle = std::thread::spawn(move || {
            run(
                &mut s,
                &opts,
                &mut |e| {
                    let _ = etx.send(e);
                },
                rx,
            )
        });
        Live { tx: Some(tx), events, seen: vec![], handle: Some(handle) }
    }

    fn send(&self, c: Command) {
        self.tx.as_ref().unwrap().send(Input::Command(c)).unwrap();
    }

    fn send_input(&self, i: Input) {
        self.tx.as_ref().unwrap().send(i).unwrap();
    }

    /// Wait (max 10 s) until an event matches.
    fn wait_event(&mut self, what: &str, f: impl Fn(&Event) -> bool) -> Event {
        if let Some(e) = self.seen.iter().find(|e| f(e)) {
            return e.clone();
        }
        let end = Instant::now() + Duration::from_secs(10);
        loop {
            let left = end.saturating_duration_since(Instant::now());
            match self.events.recv_timeout(left) {
                Ok(e) => {
                    self.seen.push(e.clone());
                    if f(&e) {
                        return e;
                    }
                }
                Err(_) => panic!("timed out waiting for {what}; seen {:#?}", self.seen),
            }
        }
    }

    fn finish(mut self) -> (Outcome, Vec<Event>) {
        self.tx.take();
        let out = self.handle.take().unwrap().join().unwrap();
        self.seen.extend(self.events.try_iter());
        (out, self.seen)
    }
}

fn wait_log(steps: &FakeSteps, what: &str) {
    let end = Instant::now() + Duration::from_secs(10);
    while !steps.log().iter().any(|l| l.starts_with(what)) {
        assert!(Instant::now() < end, "timed out waiting for log {what:?}: {:?}", steps.log());
        std::thread::sleep(Duration::from_millis(2));
    }
}

#[test]
fn full_order_for_one_point() {
    let mut f = FakeSteps::default();
    let (out, events) = run_once(&mut f, &selection(&["27b"], &root()));
    assert_eq!(out, Outcome::Done);
    assert_eq!(f.log(), expected_order(&["27b"]));
    assert!(matches!(events.first(), Some(Event::Preflight(_))));
    assert!(events.iter().any(|e| matches!(e, Event::Planned(_))));
    match events.last() {
        Some(Event::Done { installed, shortcut }) => {
            assert_eq!(installed, &vec!["27b".to_string()]);
            let file = crowsetup_core::finish::BOOT_SHORTCUT;
            assert_eq!(shortcut.as_deref(), Some(root().join("Desktop").join(file).as_path()));
        }
        e => panic!("last event {e:?}"),
    }
}

#[test]
fn full_order_packages_before_install_before_models() {
    let mut f = FakeSteps::default();
    let (out, _) = run_once(&mut f, &selection(&["flash-next", "27b"], &root()));
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    assert_eq!(log, expected_order(&["flash-next", "27b"]));
    let at = |s: &str| log.iter().position(|l| l.starts_with(s)).unwrap_or_else(|| panic!("{s} missing"));
    assert!(at("download crow-package") < at("install crow"));
    assert!(at("download engine-package") < at("install crow"));
    assert!(at("install crow") < at("install engine"));
    assert!(at("install engine") < at("python"));
    assert!(at("python") < at("download whisper"));
    assert!(at("download fn-cnq") < at("check flash-next"));
    assert!(!log.iter().any(|l| l == "convert"), "no convert without the image stack");
}

#[test]
fn image_stack_adds_convert_after_the_downloads() {
    let mut f = FakeSteps::default();
    let (out, events) = run_once(&mut f, &selection(&["image-stack"], &root()));
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    assert_eq!(log, expected_order(&["image-stack"]));
    let conv = log.iter().position(|l| l == "convert").expect("convert ran");
    let last_dl = log.iter().rposition(|l| l.starts_with("download")).unwrap();
    let check = log.iter().position(|l| l.starts_with("check")).unwrap();
    assert!(last_dl < conv && conv < check);
    assert!(events.iter().any(
        |e| matches!(e, Event::Step { name, status: StepStatus::Ok, .. } if name == "convert")
    ));
}

#[test]
fn resume_skips_done_steps_and_files() {
    let f = FakeSteps::default();
    let sel = selection(&["27b", "image-stack"], &root());
    // First run: interrupted before the finish (Done never saved).
    let mut first = f.clone();
    run_once(&mut first, &sel);
    {
        let mut sh = f.shared.lock().unwrap();
        sh.log.clear();
        let s = sh.saved.as_mut().unwrap();
        s.steps_done.retain(|x| x != "done" && x != "shortcuts");
        // The 27B container went missing on disk: only it is fetched again.
        sh.present.remove("27b-cnq");
        // Convert deleted its inputs; their state still says verified.
    }
    let mut live = Live::start(&f, &root());
    // Welcome back: the saved state is replayed before any Start.
    live.wait_event("planned", |e| matches!(e, Event::Planned(_)));
    live.wait_event("whisper verified", |e| matches!(e, Event::FileVerified { id } if id == "whisper"));
    live.send(Command::Resume);
    let (out, _) = live.finish();
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    let downloads: Vec<&String> = log.iter().filter(|l| l.starts_with("download")).collect();
    // Convert done: its verified inputs count as consumed, the 27B container does not (#196 P2-E2E fix 4).
    assert_eq!(downloads, vec!["download 27b-cnq from 1880"], "only the missing container is fetched again");
    assert!(!log.iter().any(|l| l.starts_with("install") || l == "convert"), "{log:?}");
    assert!(log.iter().any(|l| l == "python"), "python always runs: {log:?}");
    assert!(log.iter().any(|l| l == "check 27b") && log.iter().any(|l| l == "check image-stack"));
}

#[test]
fn resume_refetches_a_verified_file_that_is_gone() {
    let f = FakeSteps::default();
    let sel = selection(&["27b"], &root());
    run_once(&mut f.clone(), &sel);
    {
        let mut sh = f.shared.lock().unwrap();
        sh.log.clear();
        sh.saved.as_mut().unwrap().steps_done.retain(|x| x != "done");
        sh.present.remove("27b-cnq");
    }
    let (out, _) = run_once(&mut f.clone(), &sel);
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    let dl: Vec<&String> = log.iter().filter(|l| l.starts_with("download")).collect();
    assert_eq!(dl, vec!["download 27b-cnq from 1880"], "{log:?}");
}

#[test]
fn a_finished_install_is_not_offered_as_welcome_back() {
    let f = FakeSteps::default();
    run_once(&mut f.clone(), &selection(&["27b"], &root()));
    f.shared.lock().unwrap().log.clear();
    let mut live = Live::start(&f, &root());
    live.wait_event("preflight", |e| matches!(e, Event::Preflight(_)));
    live.send(Command::Resume); // ignored: nothing to continue
    live.send(Command::Quit);
    let (out, events) = live.finish();
    assert_eq!(out, Outcome::Quit);
    assert!(!events.iter().any(|e| matches!(e, Event::Planned(_))), "{events:?}");
    assert_eq!(f.log(), vec!["preflight"]);
}

#[test]
fn pause_stops_a_download_and_resume_continues_it() {
    let f = FakeSteps::default();
    f.shared.lock().unwrap().block_on = Some("27b-cnq".into());
    let mut live = Live::start(&f, &root());
    live.send(Command::Start(selection(&["27b"], &root())));
    live.wait_event("progress", |e| matches!(e, Event::FileProgress { id, done, .. } if id == "27b-cnq" && *done >= 50));
    live.send(Command::Pause);
    wait_log(&f, "cancelled 27b-cnq");
    // Paused: nothing else runs.
    std::thread::sleep(Duration::from_millis(50));
    let log = f.log();
    assert!(!log.iter().any(|l| l.starts_with("check")), "{log:?}");
    assert_eq!(log.iter().filter(|l| l.starts_with("download 27b-cnq")).count(), 1);
    f.shared.lock().unwrap().release = true;
    live.send(Command::Resume);
    let (out, events) = live.finish();
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    let cut: u64 = log
        .iter()
        .find_map(|l| l.strip_prefix("cancelled 27b-cnq at "))
        .and_then(|n| n.parse().ok())
        .unwrap();
    assert!(cut > 0);
    assert!(log.contains(&format!("download 27b-cnq from {cut}")), "{log:?}");
    let starts: Vec<u64> = events
        .iter()
        .filter_map(|e| match e {
            Event::FileStarted { id, from_byte, .. } if id == "27b-cnq" => Some(*from_byte),
            _ => None,
        })
        .collect();
    assert_eq!(starts, vec![0, cut]);
}

#[test]
fn permanent_failure_emits_an_error_row_and_retry_refetches_that_file() {
    let f = FakeSteps::default();
    f.shared.lock().unwrap().fail_permanent.insert("whisper".into(), 1);
    let mut live = Live::start(&f, &root());
    live.send(Command::Start(selection(&["27b"], &root())));
    let err = live.wait_event("file error", |e| matches!(e, Event::FileError { .. }));
    // Permanent: the fetcher does not loop on it; the UI offers Retry.
    assert!(matches!(&err, Event::FileError { id, retryable: false, message } if id == "whisper" && message.contains("404")));
    // The other files still come down before the run waits for Retry.
    wait_log(&f, "download 27b-cnq");
    std::thread::sleep(Duration::from_millis(30));
    assert!(!f.log().iter().any(|l| l.starts_with("check")), "waits for Retry: {:?}", f.log());
    live.send(Command::Retry { id: "some-other-id".into() }); // ignored
    live.send(Command::Retry { id: "whisper".into() });
    let (out, _) = live.finish();
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    assert_eq!(log.iter().filter(|l| l.starts_with("download whisper")).count(), 2, "{log:?}");
    assert_eq!(log.iter().filter(|l| l.starts_with("download 27b-cnq")).count(), 1, "{log:?}");
}

#[test]
fn sha_mismatch_is_an_error_row_not_a_second_refetch() {
    // fetch::download already refetched once before it returns Mismatch.
    let f = FakeSteps::default();
    f.shared.lock().unwrap().mismatch.insert("27b-cnq".into(), 1);
    let mut live = Live::start(&f, &root());
    live.send(Command::Start(selection(&["27b"], &root())));
    live.wait_event("mismatch row", |e| {
        matches!(e, Event::FileError { id, retryable: false, message } if id == "27b-cnq" && message.contains("sha256"))
    });
    std::thread::sleep(Duration::from_millis(30));
    assert_eq!(f.log().iter().filter(|l| l.starts_with("download 27b-cnq")).count(), 1, "{:?}", f.log());
    live.send(Command::Retry { id: "27b-cnq".into() });
    let (out, _) = live.finish();
    assert_eq!(out, Outcome::Done);
    assert_eq!(f.log().iter().filter(|l| l.starts_with("download 27b-cnq")).count(), 2);
}

#[test]
fn disk_check_uses_the_peak_and_counts_what_is_on_disk() {
    // Fake image stack plan: downloads 600+49+150+1880+1400 = 4079, derived 1750,
    // so the peak is 5829 while plan.disk_bytes leaves the derived side out.
    let sel = selection(&["image-stack"], &root());
    let mut f = FakeSteps::default();
    f.shared.lock().unwrap().disk_free = Some(5828);
    let (out, _) = run_once(&mut f, &sel);
    match out {
        Outcome::Fatal(m) => assert!(m.contains("free disk"), "{m}"),
        o => panic!("{o:?}"),
    }
    assert!(!f.log().iter().any(|l| l.starts_with("download")), "{:?}", f.log());

    let mut f = FakeSteps::default();
    f.shared.lock().unwrap().disk_free = Some(5829);
    assert_eq!(run_once(&mut f, &sel).0, Outcome::Done);

    // On a resume the verified 27B container (1880) is already had.
    let f = FakeSteps::default();
    run_once(&mut f.clone(), &sel);
    {
        let mut sh = f.shared.lock().unwrap();
        let s = sh.saved.as_mut().unwrap();
        s.steps_done.retain(|x| x != "done" && x != "convert");
        for (id, st) in s.files.iter_mut() {
            if id != "27b-cnq" {
                st.verified = false;
                st.bytes_done = 0;
            }
        }
        sh.disk_free = Some(5829 - 1880);
    }
    assert_eq!(run_once(&mut f.clone(), &sel).0, Outcome::Done, "{:?}", f.log());
}

#[test]
fn a_failed_step_waits_for_retry_by_name() {
    let f = FakeSteps::default();
    f.shared.lock().unwrap().fail_step.insert("engine".into(), 1);
    let mut live = Live::start(&f, &root());
    live.send(Command::Start(selection(&["27b"], &root())));
    live.wait_event("engine failed", |e| {
        matches!(e, Event::Step { name, status: StepStatus::Failed, .. } if name == "engine")
    });
    assert!(!f.log().iter().any(|l| l == "python"));
    live.send(Command::Retry { id: "engine".into() });
    let (out, _) = live.finish();
    assert_eq!(out, Outcome::Done);
    assert_eq!(f.log().iter().filter(|l| *l == "install engine").count(), 2);
}

#[test]
fn quit_ends_cleanly_mid_download_and_keeps_the_part() {
    let f = FakeSteps::default();
    f.shared.lock().unwrap().block_on = Some("27b-cnq".into());
    let mut live = Live::start(&f, &root());
    live.send(Command::Start(selection(&["27b"], &root())));
    live.wait_event("progress", |e| matches!(e, Event::FileProgress { id, done, .. } if id == "27b-cnq" && *done >= 30));
    live.send(Command::Quit);
    let (out, events) = live.finish();
    assert_eq!(out, Outcome::Quit);
    assert!(!events.iter().any(|e| matches!(e, Event::Done { .. } | Event::Fatal { .. })));
    let sh = f.shared.lock().unwrap();
    let saved = sh.saved.as_ref().unwrap();
    assert!(saved.files["27b-cnq"].bytes_done > 0 && !saved.files["27b-cnq"].verified);
    assert!(saved.selection.is_some() && !saved.steps_done.contains(&"done".to_string()));
}

#[test]
fn quit_before_start_runs_nothing() {
    let f = FakeSteps::default();
    let live = Live::start(&f, &root());
    live.send(Command::Quit);
    let (out, _) = live.finish();
    assert_eq!(out, Outcome::Quit);
    assert_eq!(f.log(), vec!["preflight"]);
    assert!(f.shared.lock().unwrap().saved.is_none(), "no state file before a selection");
}

#[test]
fn hard_block_and_blocked_points_refuse_to_start() {
    let mut f = FakeSteps::default();
    f.shared.lock().unwrap().report =
        Some(crowsetup_core::api::PreflightReport { hard_block: Some("No RTX 50.".into()), ..report() });
    let (out, _) = run_once(&mut f, &selection(&["27b"], &root()));
    assert_eq!(out, Outcome::Fatal("No RTX 50.".into()));
    assert!(!f.log().iter().any(|l| l.starts_with("download")));

    let mut f = FakeSteps::default();
    f.shared.lock().unwrap().report = Some(crowsetup_core::api::PreflightReport {
        blocked: vec![Blocked { point: "flash-next".into(), reason: "Needs 64 GB RAM.".into() }],
        ..report()
    });
    let (out, _) = run_once(&mut f, &selection(&["flash-next"], &root()));
    assert!(matches!(out, Outcome::Fatal(m) if m.contains("64 GB")));
}

#[test]
fn after_done_opens_the_boot_menu_and_moves_the_shortcut() {
    let f = FakeSteps::default();
    let mut live = Live::start(&f, &root());
    live.send(Command::Start(selection(&["27b"], &root())));
    live.wait_event("done", |e| matches!(e, Event::Done { .. }));
    live.send(Command::OpenBootMenu);
    live.wait_event("boot menu", |e| matches!(e, Event::Step { name, status: StepStatus::Ok, .. } if name == "boot_menu"));
    live.send_input(Input::ShortcutDir(root().join("Elsewhere")));
    live.wait_event("moved", |e| {
        matches!(e, Event::Step { name, status: StepStatus::Ok, detail } if name == "shortcuts" && detail.contains("Elsewhere"))
    });
    live.send(Command::Quit);
    let (out, _) = live.finish();
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    assert!(log.ends_with(&["boot menu".to_string(), "shortcuts 1".to_string()]), "{log:?}");
    let sh = f.shared.lock().unwrap();
    let sel = sh.saved.as_ref().unwrap().selection.as_ref().unwrap();
    assert_eq!(sel.shortcut_dir.as_deref(), Some(root().join("Elsewhere").as_path()));
}

#[test]
fn selftest_scenarios_pass() {
    for (name, r) in scenarios() {
        assert!(r.is_ok(), "{name}: {r:?}");
    }
}

/// #196 P2-E2E: the install steps return layout's one-line summary
/// ("Crow 2.8.5 installed (60 files)", "... is up to date"); the step row shows
/// it as it is. Measured headless: "[crow] ok Installed. Version Crow 2.8.5
/// installed (60 files)."
#[test]
fn package_steps_show_the_summary_as_it_is() {
    let mut f = FakeSteps::default();
    let (out, events) = run_once(&mut f, &selection(&["27b"], &root()));
    assert_eq!(out, Outcome::Done);
    let ok = |name: &str| {
        events.iter().find_map(|e| match e {
            Event::Step { name: n, status: StepStatus::Ok, detail } if n == name => Some(detail.clone()),
            _ => None,
        })
    };
    assert_eq!(ok("crow").as_deref(), Some("Crow 3.0.0 installed (60 files)."));
    assert_eq!(ok("engine").as_deref(), Some("Engine 0.9.0 installed (4 files)."));
}

/// #196 P2-E2E fix 4: after convert only the convert INPUTS count as consumed
/// when missing; any other verified file that is gone is fetched again.
#[test]
fn after_convert_a_missing_non_input_file_is_fetched_again() {
    let f = FakeSteps::default();
    let sel = selection(&["image-stack"], &root());
    run_once(&mut f.clone(), &sel);
    {
        let mut sh = f.shared.lock().unwrap();
        sh.log.clear();
        sh.saved.as_mut().unwrap().steps_done.retain(|x| x != "done");
        sh.present.remove("qi-transformer");
    }
    let (out, _) = run_once(&mut f.clone(), &sel);
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    let dl: Vec<&String> = log.iter().filter(|l| l.starts_with("download")).collect();
    assert_eq!(dl, vec!["download qi-transformer from 1400"], "{log:?}");
}

/// #196 P2-E2E fix 5: after a successful install the two package zips are
/// deleted (an update fetches the new ones); a finished install does not
/// fetch them again for a re-run.
#[test]
fn a_successful_install_deletes_the_package_zips() {
    let f = FakeSteps::default();
    let sel = selection(&["27b"], &root());
    assert_eq!(run_once(&mut f.clone(), &sel).0, Outcome::Done);
    {
        let sh = f.shared.lock().unwrap();
        assert!(!sh.present.contains("crow-package") && !sh.present.contains("engine-package"), "{:?}", sh.present);
        assert!(sh.present.contains("27b-cnq"));
    }
    f.shared.lock().unwrap().log.clear();
    assert_eq!(run_once(&mut f.clone(), &sel).0, Outcome::Done);
    let log = f.log();
    assert!(!log.iter().any(|l| l.starts_with("download") || l.starts_with("install")), "{log:?}");
}

/// #196 P2-E2E fix 5: a failed install keeps the zips for the resume.
#[test]
fn a_failed_install_keeps_the_package_zips() {
    let f = FakeSteps::default();
    f.shared.lock().unwrap().fail_step.insert("check".into(), 1);
    let (out, _) = run_once(&mut f.clone(), &selection(&["27b"], &root()));
    assert!(matches!(out, Outcome::Fatal(_)), "{out:?}");
    let sh = f.shared.lock().unwrap();
    assert!(sh.present.contains("crow-package") && sh.present.contains("engine-package"), "{:?}", sh.present);
}

// ------------------------------------------------- #340: the video runtime

#[test]
fn the_media_stack_unpacks_its_runtime_after_the_downloads_and_drops_the_archive() {
    let mut f = FakeSteps::default();
    let (out, events) = run_once(&mut f, &selection(&["media-stack"], &root()));
    assert_eq!(out, Outcome::Done);
    assert_eq!(f.log(), expected_order(&["media-stack"]));
    let log = f.log();
    let unpack = log.iter().position(|l| l == "unpack runtime comfyui-portable").expect("unpacked");
    assert!(log.iter().position(|l| l == "download comfyui-portable from 0").unwrap() < unpack);
    assert!(unpack < log.iter().position(|l| l == "check media-stack").unwrap());
    assert!(!f.shared.lock().unwrap().present.contains("comfyui-portable"), "the archive is deleted");
    assert!(events.iter().any(|e| matches!(e, Event::Step { name, status: StepStatus::Ok, .. } if name == "runtime")));
    let saved = f.shared.lock().unwrap().saved.clone().unwrap();
    assert!(saved.steps_done.iter().any(|s| s.starts_with("runtime:")), "{:?}", saved.steps_done);
}

#[test]
fn a_second_run_neither_fetches_nor_unpacks_the_runtime_again() {
    let f = FakeSteps::default();
    let sel = selection(&["media-stack"], &root());
    run_once(&mut f.clone(), &sel);
    f.shared.lock().unwrap().log.clear();
    let (out, _) = run_once(&mut f.clone(), &sel);
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    assert!(!log.iter().any(|l| l.contains("comfyui-portable")), "{log:?}");
}

#[test]
fn a_runtime_that_is_gone_is_fetched_and_unpacked_again() {
    let f = FakeSteps::default();
    let sel = selection(&["media-stack"], &root());
    run_once(&mut f.clone(), &sel);
    {
        let mut sh = f.shared.lock().unwrap();
        sh.log.clear();
        sh.runtime_gone = true;
    }
    let (out, _) = run_once(&mut f.clone(), &sel);
    assert_eq!(out, Outcome::Done);
    let log = f.log();
    assert!(log.iter().any(|l| l.starts_with("download comfyui-portable")), "{log:?}");
    assert!(log.iter().any(|l| l == "unpack runtime comfyui-portable"), "{log:?}");
}

#[test]
fn a_failed_unpack_waits_for_retry_of_the_runtime_step() {
    let f = FakeSteps::default();
    f.shared.lock().unwrap().fail_step.insert("runtime".into(), 1);
    let mut live = Live::start(&f, &root());
    live.send(Command::Start(selection(&["media-stack"], &root())));
    live.wait_event("runtime failed", |e| matches!(e, Event::Step { name, status: StepStatus::Failed, .. } if name == "runtime"));
    assert!(!f.log().iter().any(|l| l.starts_with("check")), "{:?}", f.log());
    live.send(Command::Retry { id: "runtime".into() });
    let (out, _) = live.finish();
    assert_eq!(out, Outcome::Done);
    assert_eq!(f.log().iter().filter(|l| *l == "unpack runtime comfyui-portable").count(), 2);
}

#[test]
fn the_disk_peak_holds_the_archive_and_its_unpacked_runtime_together() {
    // Fake media stack: downloads 600+49+150+199 = 998, the unpacked runtime
    // 4000 beside its archive until the archive is deleted: peak 4998.
    let sel = selection(&["media-stack"], &root());
    let mut f = FakeSteps::default();
    f.shared.lock().unwrap().disk_free = Some(4997);
    match run_once(&mut f, &sel).0 {
        Outcome::Fatal(m) => assert!(m.contains("free disk"), "{m}"),
        o => panic!("{o:?}"),
    }
    let mut f = FakeSteps::default();
    f.shared.lock().unwrap().disk_free = Some(4998);
    assert_eq!(run_once(&mut f, &sel).0, Outcome::Done);
}
