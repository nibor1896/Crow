//! The NVIDIA wheels in the run (crate::run, crate::nvidia): fetched with the
//! model files after the packages are installed, extracted before the check,
//! deleted afterwards, fetched again when a package step removed their
//! libraries. On the fake Steps with its fake wheel switched on.

use crowsetup_core::api::{Event, FileKind, StepStatus};
use crowsetup_core::run::testing::{expected_order, run_once, selection, FakeSteps};
use crowsetup_core::run::Outcome;
use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(r"C:\crowsetup-nvidia-root")
}

fn with_wheel() -> FakeSteps {
    let f = FakeSteps::default();
    f.shared.lock().unwrap().nvidia = true;
    f
}

#[test]
fn the_wheel_is_fetched_with_the_models_and_extracted_before_the_check() {
    let mut f = with_wheel();
    let (o, ev) = run_once(&mut f, &selection(&["27b"], &root()));
    assert_eq!(o, Outcome::Done);
    let log = f.log();
    // the order without the wheel, with its download after whisper and its
    // extraction after the last model file
    let mut want = expected_order(&["27b"]);
    let w = want.iter().position(|l| l == "download whisper from 0").unwrap();
    want.insert(w + 1, "download nvidia-fake from 0".into());
    let c = want.iter().position(|l| l == "check 27b").unwrap();
    want.insert(c, "unpack nvidia nvidia-fake".into());
    assert_eq!(log, want);
    // the plan the UI gets carries the wheel and its bytes
    let Some(Event::Planned(plan)) = ev.iter().find(|e| matches!(e, Event::Planned(_))) else { panic!("no plan") };
    let j = plan.jobs.iter().find(|j| j.id == "nvidia-fake").unwrap();
    assert_eq!(j.kind, FileKind::NvidiaWheel);
    assert_eq!(plan.download_bytes, plan.jobs.iter().map(|j| j.bytes).sum::<u64>());
    assert!(ev.iter().any(|e| matches!(e, Event::Step { name, status: StepStatus::Ok, .. } if name == "nvidia")));
    // the wheel is deleted once its libraries are out
    assert!(!f.shared.lock().unwrap().present.contains("nvidia-fake"));
    let saved = f.shared.lock().unwrap().saved.clone().unwrap();
    assert!(saved.steps_done.iter().any(|s| s.starts_with("nvidia:")));
}

#[test]
fn no_point_no_wheel() {
    let mut f = with_wheel();
    let (_, ev) = run_once(&mut f, &selection(&[], &root()));
    assert!(!f.log().iter().any(|l| l.contains("nvidia")));
    assert!(!ev.iter().any(|e| matches!(e, Event::FileStarted { id, .. } if id == "nvidia-fake")));
}

#[test]
fn a_done_wheel_is_not_fetched_again() {
    let mut f = with_wheel();
    let sel = selection(&["27b"], &root());
    run_once(&mut f, &sel);
    {
        let mut sh = f.shared.lock().unwrap();
        sh.log.clear();
        if let Some(s) = sh.saved.as_mut() {
            s.steps_done.retain(|x| x != "done" && x != "shortcuts");
        }
    }
    let (o, ev) = run_once(&mut f, &sel);
    assert_eq!(o, Outcome::Done);
    let log = f.log();
    assert!(!log.iter().any(|l| l.contains("nvidia")), "{log:?}");
    assert!(ev.iter().any(|e| matches!(e, Event::FileVerified { id } if id == "nvidia-fake")));
}

#[test]
fn libraries_a_package_step_removed_are_fetched_and_extracted_again() {
    let mut f = with_wheel();
    let sel = selection(&["27b"], &root());
    run_once(&mut f, &sel);
    {
        let mut sh = f.shared.lock().unwrap();
        sh.log.clear();
        sh.nvidia_gone = true;
        if let Some(s) = sh.saved.as_mut() {
            s.steps_done.retain(|x| x != "done" && x != "shortcuts");
        }
    }
    let (o, _) = run_once(&mut f, &sel);
    assert_eq!(o, Outcome::Done);
    let log = f.log();
    let d = log.iter().position(|l| l.starts_with("download nvidia-fake")).expect("fetched again");
    let u = log.iter().position(|l| l == "unpack nvidia nvidia-fake").expect("extracted again");
    let c = log.iter().position(|l| l == "check 27b").unwrap();
    assert!(d < u && u < c, "{log:?}");
}

#[test]
fn a_failed_extraction_waits_for_retry_and_ends_fatal_without_one() {
    let mut f = with_wheel();
    f.shared.lock().unwrap().fail_step.insert("nvidia".into(), 1);
    let (o, ev) = run_once(&mut f, &selection(&["27b"], &root()));
    assert!(matches!(o, Outcome::Fatal(_)), "{o:?}");
    assert!(ev.iter().any(|e| matches!(e, Event::Step { name, status: StepStatus::Failed, .. } if name == "nvidia")));
    assert!(!f.log().iter().any(|l| l.starts_with("check")), "no check without the libraries");
}

#[test]
fn the_disk_check_counts_the_extracted_libraries() {
    // fake plan for 27b: 600 + 49 + 150 + 1880 = 2679, the wheel 30 more and its
    // libraries 70 beside it: a peak of 2779
    let mut f = with_wheel();
    f.shared.lock().unwrap().disk_free = Some(2778);
    let (o, _) = run_once(&mut f, &selection(&["27b"], &root()));
    assert!(matches!(o, Outcome::Fatal(ref m) if m.contains("free disk")), "{o:?}");
    let mut g = with_wheel();
    g.shared.lock().unwrap().disk_free = Some(2779);
    let (o, _) = run_once(&mut g, &selection(&["27b"], &root()));
    assert_eq!(o, Outcome::Done);
}
