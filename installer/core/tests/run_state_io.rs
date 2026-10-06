//! #338: a state file that cannot be read or written is never ignored silently.

use crowsetup_core::api::{Event, Package, Packages, Source, StepStatus};
use crowsetup_core::run::testing::{run_once, selection, FakeSteps};
use crowsetup_core::run::{state_path, utc_stamp, Outcome, RealSteps, Steps};
use std::io::ErrorKind;
use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(r"C:\crowsetup-test-root")
}

#[test]
fn unreadable_state_stops_before_any_fetch() {
    let mut f = FakeSteps::default();
    f.shared.lock().unwrap().fail_load = Some(ErrorKind::PermissionDenied);
    let (out, events) = run_once(&mut f, &selection(&["27b"], &root()));

    let path = state_path(&root()).display().to_string();
    match &out {
        Outcome::Fatal(m) => assert!(m.contains(&path) && m.contains("fake load failure"), "message: {m}"),
        o => panic!("outcome {o:?}, expected Fatal"),
    }
    assert!(events.iter().any(|e| matches!(e, Event::Fatal { .. })), "no Fatal event: {events:?}");
    let log = f.log();
    assert!(!log.iter().any(|l| l.starts_with("download") || l.starts_with("install")), "log: {log:?}");
    // the file it could not read is not overwritten with an empty state
    assert!(f.shared.lock().unwrap().saved.is_none());
    let notes = f.shared.lock().unwrap().notes.clone();
    assert!(notes.len() == 1 && notes[0].starts_with("setup.log: ") && notes[0].contains(&path), "notes: {notes:?}");
}

#[test]
fn failed_save_warns_once_and_still_lands() {
    let mut f = FakeSteps::default();
    f.shared.lock().unwrap().fail_save = Some(ErrorKind::PermissionDenied);
    let (out, events) = run_once(&mut f, &selection(&["27b"], &root()));

    assert_eq!(out, Outcome::Done);
    let warnings: Vec<&String> = events
        .iter()
        .filter_map(|e| match e {
            Event::Step { name, status: StepStatus::Warning, detail } if name == "state" => Some(detail),
            _ => None,
        })
        .collect();
    let path = state_path(&root()).display().to_string();
    assert_eq!(warnings.len(), 1, "state warnings: {warnings:?}");
    assert!(warnings[0].contains(&path) && warnings[0].contains("fake save failure"), "{}", warnings[0]);
    let notes = f.shared.lock().unwrap().notes.clone();
    assert!(notes.len() == 1 && notes[0].starts_with("setup.log: ") && notes[0].contains(&path), "notes: {notes:?}");
}

#[test]
fn a_run_that_saves_writes_no_note() {
    let mut f = FakeSteps::default();
    let (out, events) = run_once(&mut f, &selection(&["27b"], &root()));
    assert_eq!(out, Outcome::Done);
    assert!(!events.iter().any(|e| matches!(e, Event::Step { name, .. } if name == "state")));
    assert!(f.shared.lock().unwrap().notes.is_empty());
}

#[test]
fn log_stamp_is_utc() {
    // reference values from Python's datetime.fromtimestamp(s, timezone.utc)
    for (secs, want) in [
        (0, "1970-01-01T00:00:00Z"),
        (951_782_399, "2000-02-28T23:59:59Z"),
        (951_782_400, "2000-02-29T00:00:00Z"),
        (4_107_542_400, "2100-03-01T00:00:00Z"),
        (1_791_279_667, "2026-10-06T09:41:07Z"),
    ] {
        assert_eq!(utc_stamp(secs), want, "{secs}");
    }
}

#[test]
fn the_real_steps_append_to_setup_log() {
    let p = |a: &str| Package { asset: a.into(), url: "https://unused.invalid/".into(), bytes: 1, sha256: "0".repeat(64), version: "1".into() };
    let mut steps = RealSteps::new(Source::Remote, Packages { crow: p("c"), engine: p("e") }, None, None);
    let dir = tempfile::tempdir().unwrap();
    // the setup folder does not exist yet
    let log = dir.path().join("setup").join("setup.log");
    steps.note(&log, "first");
    steps.note(&log, "second");
    let text = std::fs::read_to_string(&log).unwrap();
    let lines: Vec<&str> = text.lines().collect();
    assert_eq!(lines.len(), 2, "{text}");
    for (line, want) in lines.iter().zip(["first", "second"]) {
        let (stamp, rest) = line.split_once(' ').unwrap();
        assert!(stamp.len() == 20 && stamp.ends_with('Z'), "{line}");
        assert_eq!(rest, want);
    }
}
