//! #342: the run with a local source that links. A prefilled derived output
//! marks the convert done before any download, so its inputs are neither fetched
//! nor counted; files that are hard links cost no disk in the disk check.

use crowsetup_core::api::{Event, FileJob, Plan, PreflightReport, Selection};
use crowsetup_core::fetch::FetchError;
use crowsetup_core::python::PythonInfo;
use crowsetup_core::run::testing::{FakeSteps, run_once, selection};
use crowsetup_core::run::{Outcome, Steps};
use crowsetup_core::state::StateStore;
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;

/// FakeSteps with the two local-source answers set.
struct Linking {
    fake: FakeSteps,
    prefill: bool,
    free: bool,
}

impl Steps for Linking {
    fn preflight(&mut self, r: &Path) -> PreflightReport {
        self.fake.preflight(r)
    }
    fn plan(&mut self, sel: &Selection) -> Result<Plan, String> {
        self.fake.plan(sel)
    }
    fn load_state(&mut self, p: &Path) -> std::io::Result<StateStore> {
        self.fake.load_state(p)
    }
    fn save_state(&mut self, s: &StateStore) -> std::io::Result<()> {
        self.fake.save_state(s)
    }
    fn present(&mut self, j: &FileJob) -> bool {
        self.fake.present(j)
    }
    fn discard(&mut self, j: &FileJob) {
        self.fake.discard(j)
    }
    fn disk_free(&mut self, d: &Path) -> u64 {
        self.fake.disk_free(d)
    }
    fn download(&mut self, j: &FileJob, s: &mut StateStore, on: &mut dyn FnMut(Event), c: &AtomicBool) -> Result<(), FetchError> {
        self.fake.download(j, s, on, c)
    }
    fn install_crow(&mut self, z: &Path, r: &Path) -> Result<String, String> {
        self.fake.install_crow(z, r)
    }
    fn install_engine(&mut self, z: &Path, r: &Path) -> Result<String, String> {
        self.fake.install_engine(z, r)
    }
    fn ensure_python(&mut self, r: &Path) -> Result<PythonInfo, String> {
        self.fake.ensure_python(r)
    }
    fn convert(&mut self, p: &PythonInfo, r: &Path, m: &Path) -> Result<(), String> {
        self.fake.convert(p, r, m)
    }
    fn check_point(&mut self, p: &PythonInfo, r: &Path, m: &Path, pt: &str) -> Result<(), String> {
        self.fake.check_point(p, r, m, pt)
    }
    fn shortcuts(&mut self, p: &PythonInfo, r: &Path, d: &[PathBuf]) -> Result<(), String> {
        self.fake.shortcuts(p, r, d)
    }
    fn open_boot_menu(&mut self, p: &PythonInfo, r: &Path) -> Result<(), String> {
        self.fake.open_boot_menu(p, r)
    }
    fn prefill_derived(&mut self, _plan: &Plan, _models: &Path) -> bool {
        self.prefill
    }
    fn costs_no_disk(&mut self, _job: &FileJob) -> bool {
        self.free
    }
}

fn run(steps: &mut Linking, sel: &Selection) -> (Outcome, Vec<Event>) {
    // run_once drives a FakeSteps; the same driver, by hand, for the wrapper
    let (tx, rx) = std::sync::mpsc::channel();
    tx.send(crowsetup_core::run::Input::Command(crowsetup_core::api::Command::Start(sel.clone()))).unwrap();
    drop(tx);
    let mut ev = Vec::new();
    let opts = crowsetup_core::run::testing::options(&sel.install_root);
    let out = crowsetup_core::run::run(steps, &opts, &mut |e| ev.push(e), rx);
    (out, ev)
}

#[test]
fn a_prefilled_text_encoder_skips_its_inputs_and_the_convert() {
    let sel = selection(&["image-stack"], Path::new("/r"));
    let mut s = Linking { fake: FakeSteps::default(), prefill: true, free: false };
    let (out, ev) = run(&mut s, &sel);
    assert_eq!(out, Outcome::Done, "{ev:?}");
    let log = s.fake.log();
    assert!(!log.iter().any(|l| l.starts_with("download qi-text-encoder ")), "{log:?}");
    assert!(!log.iter().any(|l| l == "convert"), "{log:?}");
    assert!(log.iter().any(|l| l.starts_with("download qi-transformer ")), "{log:?}");
    assert!(ev.iter().any(|e| matches!(e, Event::Step { name, .. } if name == "convert")), "the UI still sees the step");

    // without a prefill the order is the one every other test knows
    let mut plain = FakeSteps::default();
    let (out, _) = run_once(&mut plain, &sel);
    assert_eq!(out, Outcome::Done);
    assert!(plain.log().iter().any(|l| l == "convert"));
}

#[test]
fn linked_files_cost_no_disk() {
    let sel = selection(&["27b"], Path::new("/r"));
    let tight = |free: bool| {
        let fake = FakeSteps::default();
        fake.shared.lock().unwrap().disk_free = Some(10);
        let mut s = Linking { fake, prefill: false, free };
        run(&mut s, &sel)
    };
    let (out, ev) = tight(false);
    assert!(matches!(out, Outcome::Fatal(ref m) if m.contains("free disk")), "{out:?} {ev:?}");
    let (out, ev) = tight(true);
    assert_eq!(out, Outcome::Done, "{ev:?}");
}
