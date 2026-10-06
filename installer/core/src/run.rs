//! T4: the install run in order, emitting [`Event`]s; used by the window,
//! `--headless`, `--selftest` and the tests alike.
//!
//! THE ORDER: preflight, (welcome-back replay), wait for Start or Resume, plan,
//! the two packages, install Crow, install the engine, ensure Python, the model
//! files (whisper and the NVIDIA wheels included, in the plan's order), the
//! NVIDIA libraries out of their wheels (`nvidia`), the video runtime, convert
//! (when the plan carries derived files: the image stack), check every
//! selected point, shortcuts, Done.
//!
//! THE NVIDIA WHEELS (crate::nvidia): the plan of [`Steps::plan`] is the
//! stack's; the run adds the wheels [`Steps::nvidia`] names for the selection
//! (after whisper, before the models) and their extracted size to the disk.
//! A wheel is deleted once its libraries are out (`nvidia:<sha256>` in
//! `steps_done`). After the package steps, a done wheel whose libraries are no
//! longer all in place (an update of an older package removes the copies its
//! manifest listed) is fetched and extracted again. Every module call goes through [`Steps`], so the order,
//! resume and pause logic is tested with a fake and runs unchanged on
//! [`RealSteps`].
//!
//! THE STATE FILE is `<launch root>\setup\state.json`, where the launch root is
//! `--install-root` or `%LOCALAPPDATA%\Crow` ([`state_path`]). A normal start
//! therefore always finds `%LOCALAPPDATA%\Crow\setup\state.json`, whatever
//! install location was picked in the window (the saved [`Selection`] carries
//! that location), and a test install with `--install-root` never touches the
//! real one.
//!
//! RESUME: a file whose state says `verified` is not fetched again when its
//! destination exists, or, once the convert step is done, when it is one of
//! the convert's INPUTS (convert deletes the image stack's `text_encoder/`,
//! which the state still lists as verified). Any other verified file that is
//! gone is fetched again.
//!
//! THE PACKAGE ZIPS are deleted after Done (an update fetches the new ones);
//! a failed or interrupted install keeps them for the resume. A package whose
//! install step (`crow:<sha256>`) is done is not fetched again.
//! Install steps are recorded in `steps_done`: `crow:<sha256>` and
//! `engine:<sha256>` (a new package re-installs), `convert`, `shortcuts`,
//! `done`. Python and the check step always run: both are idempotent and the
//! check is the guarantee behind "Landed".
//!
//! A LOCAL SOURCE (`--source`, #342): a file is taken from `<dir>/<repo>/<path>`
//! (the remote layout) or, when that is not there, from `<dir>/<path under the
//! models root>` (a models tree such as `crow-stack/` or another install's
//! `models/`). On Linux, files on the same file system are hard-linked (see
//! fetch.rs) and cost no disk, which preflight and the disk check account for;
//! a source that already holds a derived output in full (the Image Stack's
//! `text_encoder_sdcli/`) is linked into place and the convert step counts as
//! done, so its inputs are not fetched.
//!
//! COMMANDS: Pause and Quit set the cancel flag, so a download stops inside
//! (the fetcher polls it) and the run stops between steps. Resume clears the
//! pause and, before Start, continues the saved selection (the welcome-back
//! "Continue"). Retry{id} re-runs a failed file (by its id) or a failed step
//! (by its name). OpenBootMenu and a new shortcut folder are served after Done.

use crate::api::{Command, Event, FileJob, FileKind, Packages, Plan, PreflightReport, Selection, Source, StepStatus};
use crate::fetch::{FetchError, FetchOptions};
use crate::nvidia::NvidiaJob;
use crate::python::PythonInfo;
use crate::runtime::RuntimeJob;
use crate::state::{FileState, StateStore};
use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Receiver;
use std::sync::{Arc, Condvar, Mutex};

/// One method per module call the run makes. [`RealSteps`] calls the modules;
/// tests and `--selftest` use [`testing::FakeSteps`].
pub trait Steps {
    fn preflight(&mut self, install_root: &Path) -> PreflightReport;
    fn plan(&mut self, sel: &Selection) -> Result<Plan, String>;
    /// A missing file is an empty store with `path` set.
    fn load_state(&mut self, path: &Path) -> std::io::Result<StateStore>;
    fn save_state(&mut self, state: &StateStore) -> std::io::Result<()>;
    /// #338: add one line to `log` (`setup\setup.log`), best effort: what
    /// the window only showed stays on disk as evidence. Default: nothing.
    fn note(&mut self, _log: &Path, _line: &str) {}
    /// Whether a fetched file is still on disk (its final `dest`).
    fn present(&mut self, job: &FileJob) -> bool;
    /// Delete a fetched file that is no longer needed (the package zips after Done).
    fn discard(&mut self, job: &FileJob);
    /// Free bytes on the drive that holds `dir` (or its nearest existing
    /// ancestor); 0 when unknown.
    fn disk_free(&mut self, dir: &Path) -> u64;
    fn download(
        &mut self,
        job: &FileJob,
        state: &mut StateStore,
        on: &mut dyn FnMut(Event),
        cancel: &AtomicBool,
    ) -> Result<(), FetchError>;
    /// Returns layout's one-line summary ("Crow 3.0.0 installed (60 files)",
    /// "engine 0.9.0 is up to date ..."), shown as the step's detail.
    fn install_crow(&mut self, zip: &Path, install_root: &Path) -> Result<String, String>;
    fn install_engine(&mut self, zip: &Path, install_root: &Path) -> Result<String, String>;
    fn ensure_python(&mut self, install_root: &Path) -> Result<PythonInfo, String>;
    fn convert(&mut self, py: &PythonInfo, install_root: &Path, models_root: &Path) -> Result<(), String>;
    fn check_point(&mut self, py: &PythonInfo, install_root: &Path, models_root: &Path, point: &str)
    -> Result<(), String>;
    fn shortcuts(&mut self, py: &PythonInfo, install_root: &Path, dirs: &[PathBuf]) -> Result<(), String>;
    fn open_boot_menu(&mut self, py: &PythonInfo, install_root: &Path) -> Result<(), String>;
    /// A local source that holds every derived output: put them in place and
    /// answer true (the convert step is then done). Default: never.
    fn prefill_derived(&mut self, _plan: &Plan, _models_root: &Path) -> bool {
        false
    }
    /// The job will take no space where it lands (a hard link). Default: never.
    fn costs_no_disk(&mut self, _job: &FileJob) -> bool {
        false
    }
    /// #340: the video server runtimes the selection needs. Default: none.
    fn runtimes(&mut self, _sel: &Selection) -> Vec<RuntimeJob> {
        Vec::new()
    }
    /// The runtime folder holds exactly this archive's contents. Default: no.
    fn runtime_current(&mut self, _job: &RuntimeJob) -> bool {
        false
    }
    /// Unpack one runtime; the summary is the step's detail.
    /// NVIDIA's CUDA libraries the selection needs on this platform.
    fn nvidia(&mut self, _sel: &Selection) -> Result<Vec<NvidiaJob>, String> {
        Ok(Vec::new())
    }
    /// Every library of the wheel is in place with its bytes.
    fn nvidia_current(&mut self, _job: &NvidiaJob) -> bool {
        true
    }
    /// Take the libraries out of the downloaded wheel.
    fn unpack_nvidia(&mut self, _job: &NvidiaJob, _cancel: &AtomicBool) -> Result<String, String> {
        Ok(String::new())
    }
    fn unpack_runtime(&mut self, _job: &RuntimeJob, _cancel: &AtomicBool) -> Result<String, String> {
        Err("this installer cannot unpack a runtime".into())
    }
}

/// What reaches the run from outside: the contract's [`Command`]s, plus the
/// shortcut folder picked on the "Landed" screen (not in the contract yet).
#[derive(Debug, Clone, PartialEq)]
pub enum Input {
    Command(Command),
    ShortcutDir(PathBuf),
}

impl From<Command> for Input {
    fn from(c: Command) -> Input {
        Input::Command(c)
    }
}

#[derive(Debug, Clone)]
pub struct RunOptions {
    /// `--install-root` or `%LOCALAPPDATA%\Crow`; preflight measures it.
    pub launch_root: PathBuf,
    pub state_path: PathBuf,
    /// The Start menu folder; the entry is always written when this is set.
    pub start_menu_dir: Option<PathBuf>,
}

/// How a run ended; `--headless` maps it to the exit code.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Outcome {
    Done,
    Quit,
    Fatal(String),
}

/// `%LOCALAPPDATA%\Crow`, the default install root.
#[cfg(windows)]
pub fn default_install_root() -> PathBuf {
    std::env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_else(std::env::temp_dir).join("Crow")
}

/// `$XDG_DATA_HOME/crow` (default `~/.local/share/crow`), install.sh's `CROW_HOME` (#342).
#[cfg(not(windows))]
pub fn default_install_root() -> PathBuf {
    crate::finish::default_install_root().unwrap_or_else(|| std::env::temp_dir().join("crow"))
}

/// `2026-10-06T09:41:07Z` for seconds since the Unix epoch (UTC; days to
/// civil date after H. Hinnant, "chrono-Compatible Low-Level Date Algorithms").
pub fn utc_stamp(secs: u64) -> String {
    let (days, rem) = ((secs / 86_400) as i64, secs % 86_400);
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!("{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z", rem / 3_600, rem / 60 % 60, rem % 60)
}

/// `<launch root>\setup\state.json` (see the module docs).
pub fn state_path(launch_root: &Path) -> PathBuf {
    launch_root.join("setup").join("state.json")
}

/// `${MODELS}` for the installer: always `<install>/models`. `$CROW_MODELS` is
/// a lab root for Crow's optional llama.cpp lines and never redirects an
/// install; the shortcuts and the boot menu button hand `--models` to
/// crow_boot, so the boot menu finds these files whatever it says (#196 P2-E2E).
pub fn models_root(install_root: &Path) -> PathBuf {
    install_root.join("models")
}

/// Decimal GB with one digit, MB below 1 GB (the UI's sizes).
pub fn gb(bytes: u64) -> String {
    if bytes >= 1_000_000_000 {
        format!("{:.1} GB", bytes as f64 / 1e9)
    } else {
        format!("{} MB", bytes.div_ceil(1_000_000))
    }
}

/// A summary as a step detail: first letter upper case, one closing period.
fn sentence(s: &str) -> String {
    let s = s.trim().trim_end_matches('.');
    let mut c = s.chars();
    match c.next() {
        Some(f) => format!("{}{}.", f.to_uppercase(), c.as_str()),
        None => String::new(),
    }
}

/// The shortcut file `crow_boot.py --create-shortcut DIR` writes (Linux: the
/// operating-point window's desktop entry, #342).
pub fn shortcut_file(dir: &Path) -> PathBuf {
    dir.join(crate::finish::BOOT_SHORTCUT)
}

// ------------------------------------------------------------------ control

#[derive(Default)]
struct Ctl {
    paused: bool,
    quit: bool,
    disconnected: bool,
    queue: VecDeque<Input>,
}

/// Shared between the run and the thread that drains the input channel.
struct Control {
    cancel: AtomicBool,
    ctl: Mutex<Ctl>,
    cv: Condvar,
}

impl Control {
    fn listen(self: &Arc<Self>, inputs: Receiver<Input>) {
        let me = Arc::clone(self);
        std::thread::spawn(move || {
            for input in inputs {
                let mut c = me.ctl.lock().unwrap();
                match &input {
                    Input::Command(Command::Pause) => {
                        c.paused = true;
                        me.cancel.store(true, Ordering::SeqCst);
                    }
                    Input::Command(Command::Quit) => {
                        c.quit = true;
                        me.cancel.store(true, Ordering::SeqCst);
                    }
                    Input::Command(Command::Resume) => {
                        c.paused = false;
                        c.queue.push_back(input.clone());
                    }
                    _ => c.queue.push_back(input.clone()),
                }
                drop(c);
                me.cv.notify_all();
            }
            me.ctl.lock().unwrap().disconnected = true;
            me.cv.notify_all();
        });
    }

    fn quit(&self) -> bool {
        self.ctl.lock().unwrap().quit
    }

    /// Blocks while paused. False when the run has to stop (Quit).
    fn gate(&self) -> bool {
        let mut c = self.ctl.lock().unwrap();
        while c.paused && !c.quit && !c.disconnected {
            c = self.cv.wait(c).unwrap();
        }
        if c.quit {
            return false;
        }
        // Disconnected while paused: nobody can resume, so the pause ends.
        c.paused = false;
        self.cancel.store(false, Ordering::SeqCst);
        true
    }

    /// The next queued input for which `want` returns Some; other inputs are
    /// dropped. None on Quit, or when the channel is gone and the queue empty.
    fn wait<T>(&self, mut want: impl FnMut(&Input) -> Option<T>) -> Option<T> {
        let mut c = self.ctl.lock().unwrap();
        loop {
            if c.quit {
                return None;
            }
            while let Some(input) = c.queue.pop_front() {
                if let Some(t) = want(&input) {
                    return Some(t);
                }
            }
            if c.disconnected {
                return None;
            }
            c = self.cv.wait(c).unwrap();
        }
    }
}

// ------------------------------------------------------------------- runner

enum Stop {
    Quit,
    Fatal(String),
}

enum FileResult {
    Ok,
    Failed(String),
}

struct Runner<'a> {
    steps: &'a mut dyn Steps,
    on: &'a mut dyn FnMut(Event),
    opts: &'a RunOptions,
    ctl: Arc<Control>,
    state: StateStore,
    /// Ids of the convert step's inputs (the files it deletes).
    inputs: std::collections::BTreeSet<String>,
    /// #340: the runtimes this selection unpacks (their archives are deleted).
    runtimes: Vec<RuntimeJob>,
    /// The NVIDIA wheels this selection extracts (they are deleted too).
    nvidia: Vec<NvidiaJob>,
    /// #338: a failed save was reported once this run.
    save_warned: bool,
}

/// Run the whole install. Returns when Done was emitted and the input channel
/// is gone (or Quit came), on Quit, or on a fatal error (emitted as `Fatal`).
pub fn run(steps: &mut dyn Steps, opts: &RunOptions, on: &mut dyn FnMut(Event), inputs: Receiver<Input>) -> Outcome {
    let ctl = Arc::new(Control { cancel: AtomicBool::new(false), ctl: Mutex::default(), cv: Condvar::new() });
    ctl.listen(inputs);
    let state = StateStore { path: opts.state_path.clone(), ..StateStore::default() };
    let mut r = Runner { steps, on, opts, ctl, state, inputs: Default::default(), runtimes: Vec::new(), nvidia: Vec::new(), save_warned: false };
    match r.go() {
        Ok(()) => Outcome::Done,
        Err(Stop::Quit) => {
            r.save();
            Outcome::Quit
        }
        Err(Stop::Fatal(m)) => {
            r.save();
            (r.on)(Event::Fatal { message: m.clone() });
            Outcome::Fatal(m)
        }
    }
}

impl Runner<'_> {
    fn emit(&mut self, e: Event) {
        (self.on)(e)
    }

    fn save(&mut self) {
        // Nothing to remember before a selection: closing the window at the
        // selection screen leaves no state file behind.
        if self.state.selection.is_none() {
            return;
        }
        // A failed checkpoint costs at most a re-hash on the next start, so
        // the run goes on; but it says so, once (#338).
        if let Err(e) = self.steps.save_state(&self.state)
            && !self.save_warned
        {
            self.save_warned = true;
            let m = format!("Progress is not being saved to {}: {e}", self.opts.state_path.display());
            self.note(&m);
            self.step_event("state", StepStatus::Warning, m);
        }
    }

    /// One line in `setup.log` next to the state file (#338).
    fn note(&mut self, line: &str) {
        let log = self.opts.state_path.with_file_name("setup.log");
        self.steps.note(&log, line);
    }

    fn done(&self, step: &str) -> bool {
        self.state.steps_done.iter().any(|s| s == step)
    }

    /// A fetched file is had when it is on disk, or when it is consumed.
    fn have(&mut self, job: &FileJob) -> bool {
        self.consumed(job) || self.steps.present(job)
    }

    /// A file a done step has used up and deleted: a convert input once the
    /// convert is done, a runtime archive once it is unpacked (#340), an
    /// NVIDIA wheel once its libraries are out.
    fn consumed(&self, job: &FileJob) -> bool {
        (self.done("convert") && self.inputs.contains(&job.id))
            || self.runtimes.iter().any(|r| r.file_id == job.id && self.done(&Self::runtime_key(r)))
            || self.nvidia.iter().any(|w| w.file.id == job.id && self.done(&Self::nvidia_key(w)))
    }

    /// `nvidia:<sha256>`: the wheel the libraries were taken from.
    fn nvidia_key(w: &NvidiaJob) -> String {
        format!("nvidia:{}", w.file.sha256)
    }

    /// The stack's plan plus the NVIDIA wheels: downloaded after whisper and
    /// before the models; on disk only their libraries stay.
    fn full_plan(&mut self, sel: &Selection) -> Result<(Plan, Vec<NvidiaJob>), String> {
        let mut plan = self.steps.plan(sel)?;
        let wheels = self.steps.nvidia(sel)?;
        let at = plan.jobs.iter().position(|j| j.kind == FileKind::Model).unwrap_or(plan.jobs.len());
        for (i, w) in wheels.iter().enumerate() {
            plan.jobs.insert(at + i, w.file.clone());
            plan.download_bytes += w.file.bytes;
            plan.disk_bytes += w.extracted_bytes();
        }
        Ok((plan, wheels))
    }

    /// `runtime:<sha256>`: the archive the runtime folder was unpacked from.
    fn runtime_key(r: &RuntimeJob) -> String {
        format!("runtime:{}", r.sha256)
    }

    /// `crow:<sha256>` / `engine:<sha256>`: the install step of a package job.
    fn install_key(job: &FileJob) -> String {
        let name = if job.kind == FileKind::CrowPackage { "crow" } else { "engine" };
        format!("{name}:{}", job.sha256)
    }

    fn mark(&mut self, step: &str) {
        if !self.done(step) {
            self.state.steps_done.push(step.to_string());
        }
        self.save();
    }

    fn step_event(&mut self, name: &str, status: StepStatus, detail: impl Into<String>) {
        self.emit(Event::Step { name: name.to_string(), status, detail: detail.into() });
    }

    fn go(&mut self) -> Result<(), Stop> {
        let report = self.steps.preflight(&self.opts.launch_root);
        self.emit(Event::Preflight(report.clone()));

        // An unreadable state is a stop with the path and the OS error, not a
        // silent start from nothing that fetches everything again (#338).
        self.state = match self.steps.load_state(&self.opts.state_path) {
            Ok(s) => s,
            Err(e) => {
                let m = format!(
                    "Cannot read {}: {e}. Close what holds it and start again.",
                    self.opts.state_path.display()
                );
                self.note(&m);
                return Err(Stop::Fatal(m));
            }
        };
        let saved = self.state.selection.clone().filter(|_| !self.done("done"));
        let resumable = match &saved {
            Some(sel) => match self.full_plan(sel) {
                Ok((plan, _)) => {
                    self.replay(&plan);
                    true
                }
                Err(_) => false,
            },
            None => false,
        };

        let (sel, fresh) = self
            .ctl
            .wait(|i| match i {
                Input::Command(Command::Start(sel)) => Some((sel.clone(), true)),
                Input::Command(Command::Resume) if resumable => saved.clone().map(|s| (s, false)),
                _ => None,
            })
            .ok_or(Stop::Quit)?;

        if let Some(why) = &report.hard_block {
            return Err(Stop::Fatal(why.clone()));
        }
        if let Some(b) = report.blocked.iter().find(|b| sel.points.contains(&b.point)) {
            return Err(Stop::Fatal(format!("{}: {}", b.point, b.reason)));
        }
        if sel.points.is_empty() {
            return Err(Stop::Fatal("Nothing selected.".into()));
        }

        if fresh {
            self.state.steps_done.retain(|s| s != "shortcuts" && s != "done");
        }
        self.state.selection = Some(sel.clone());
        self.save();

        let (plan, wheels) = self.full_plan(&sel).map_err(Stop::Fatal)?;
        self.nvidia = wheels;
        self.inputs = plan.derived.iter().flat_map(|d| d.inputs.iter().cloned()).collect();
        // A runtime folder that no longer holds its archive is unpacked again,
        // so its archive is fetched again (#340).
        self.runtimes = self.steps.runtimes(&sel);
        for r in self.runtimes.clone() {
            let key = Self::runtime_key(&r);
            if self.done(&key) && !self.steps.runtime_current(&r) {
                self.state.steps_done.retain(|s| s != &key);
            }
        }
        self.emit(Event::Planned(plan.clone()));
        let root = sel.install_root.clone();
        let models = models_root(&root);
        if !plan.derived.is_empty() && !self.done("convert") && self.steps.prefill_derived(&plan, &models) {
            self.mark("convert");
        }
        self.disk_check(&plan, &root)?;

        // The two packages, then Crow, then the engine. An installed package is
        // not fetched again (its zip is deleted after Done).
        let mut packages: Vec<&FileJob> = Vec::new();
        for j in plan.jobs.iter().filter(|j| matches!(j.kind, FileKind::CrowPackage | FileKind::EnginePackage)) {
            if self.done(&Self::install_key(j)) {
                self.emit(Event::FileVerified { id: j.id.clone() });
            } else {
                packages.push(j);
            }
        }
        self.fetch_all(&packages)?;
        for (kind, name) in [(FileKind::CrowPackage, "crow"), (FileKind::EnginePackage, "engine")] {
            let Some(job) = plan.jobs.iter().find(|j| j.kind == kind) else {
                return Err(Stop::Fatal(format!("The plan carries no {name} package.")));
            };
            let key = Self::install_key(job);
            if self.done(&key) {
                self.step_event(name, StepStatus::Ok, "Installed.");
                continue;
            }
            let zip = job.dest.clone();
            let root2 = root.clone();
            self.step(name, &mut |s| {
                let summary = if kind == FileKind::CrowPackage {
                    s.install_crow(&zip, &root2)?
                } else {
                    s.install_engine(&zip, &root2)?
                };
                Ok(sentence(&summary))
            })?;
            self.mark(&key);
        }
        // A package step may have removed a library an older package carried
        // (its manifest listed it): such a wheel is fetched and extracted again.
        for w in self.nvidia.clone() {
            let key = Self::nvidia_key(&w);
            if self.done(&key) && !self.steps.nvidia_current(&w) {
                self.state.steps_done.retain(|s| s != &key);
                self.save();
            }
        }

        let mut py = None;
        let root2 = root.clone();
        self.step("python", &mut |s| {
            let p = s.ensure_python(&root2)?;
            let how = if p.bundled { "installed" } else { "found" };
            let mut d = format!("Python {} {how}.", p.version);
            // Linux (#342): what the venv could not get (voice, PyGObject) is shown
            if cfg!(not(windows)) {
                for w in &p.warnings {
                    d.push(' ');
                    d.push_str(&sentence(w));
                }
            }
            py = Some(p);
            Ok(d)
        })?;
        let py = py.expect("python step succeeded");

        let models_jobs: Vec<&FileJob> = plan
            .jobs
            .iter()
            .filter(|j| matches!(j.kind, FileKind::Model | FileKind::Whisper | FileKind::NvidiaWheel))
            .collect();
        self.fetch_all(&models_jobs)?;

        // NVIDIA's libraries out of each wheel, which is then deleted.
        for w in self.nvidia.clone() {
            let key = Self::nvidia_key(&w);
            if self.done(&key) {
                self.step_event("nvidia", StepStatus::Ok, "NVIDIA libraries in place.");
                continue;
            }
            let ctl = Arc::clone(&self.ctl);
            self.step("nvidia", &mut |s| s.unpack_nvidia(&w, &ctl.cancel).map(|d| sentence(&d)))?;
            self.mark(&key);
            self.steps.discard(&w.file);
        }

        // #340: each runtime unpacked from its archive, which is then deleted.
        for r in self.runtimes.clone() {
            let key = Self::runtime_key(&r);
            if self.done(&key) {
                self.step_event("runtime", StepStatus::Ok, "Video runtime ready.");
                continue;
            }
            let ctl = Arc::clone(&self.ctl);
            self.step("runtime", &mut |s| s.unpack_runtime(&r, &ctl.cancel).map(|d| sentence(&d)))?;
            self.mark(&key);
            self.save();
            if let Some(job) = plan.jobs.iter().find(|j| j.id == r.file_id) {
                self.steps.discard(job);
            }
        }

        if !plan.derived.is_empty() {
            if self.done("convert") {
                self.step_event("convert", StepStatus::Ok, "Text encoder ready.");
            } else {
                let (r2, m2, p2) = (root.clone(), models.clone(), py.clone());
                self.step("convert", &mut |s| {
                    s.convert(&p2, &r2, &m2)?;
                    Ok("Text encoder ready.".into())
                })?;
                self.mark("convert");
            }
        }

        let (r2, m2, p2, pts) = (root.clone(), models.clone(), py.clone(), sel.points.clone());
        self.step("check", &mut |s| {
            for p in &pts {
                s.check_point(&p2, &r2, &m2, p).map_err(|e| format!("{p}: {e}"))?;
            }
            Ok(format!("{} checked.", pts.join(", ")))
        })?;

        let mut dirs: Vec<PathBuf> = sel.shortcut_dir.iter().cloned().collect();
        dirs.extend(self.opts.start_menu_dir.iter().cloned());
        let mut shortcut = sel.shortcut_dir.as_deref().map(shortcut_file);
        if !dirs.is_empty() && !self.done("shortcuts") {
            self.step_event("shortcuts", StepStatus::Running, "");
            match self.steps.shortcuts(&py, &root, &dirs) {
                Ok(()) => {
                    self.step_event("shortcuts", StepStatus::Ok, "Shortcuts written.");
                    self.mark("shortcuts");
                }
                Err(e) => {
                    // Not worth failing a finished install over: the boot menu
                    // is in the install root either way.
                    self.step_event("shortcuts", StepStatus::Warning, e);
                    shortcut = None;
                }
            }
        }

        self.mark("done");
        for job in plan.jobs.iter().filter(|j| matches!(j.kind, FileKind::CrowPackage | FileKind::EnginePackage)) {
            self.steps.discard(job);
        }
        self.emit(Event::Done { installed: sel.points.clone(), shortcut: shortcut.clone() });
        self.after_done(&py, &root, shortcut);
        Ok(())
    }

    /// The PEAK need against the free space where the install goes: every
    /// download plus the derived files, because the convert inputs
    /// (`text_encoder/`) and its output exist side by side until convert
    /// deletes the inputs. What is already on disk counts as had.
    fn disk_check(&mut self, plan: &Plan, root: &Path) -> Result<(), Stop> {
        // #340: a runtime still to unpack lands beside its archive; so do the
        // NVIDIA libraries beside their wheel.
        let unpack: u64 = self.runtimes.iter().filter(|r| !self.done(&Self::runtime_key(r))).map(|r| r.bytes).sum::<u64>()
            + self.nvidia.iter().filter(|w| !self.done(&Self::nvidia_key(w))).map(NvidiaJob::extracted_bytes).sum::<u64>();
        let peak = plan.download_bytes + plan.derived.iter().map(|d| d.bytes).sum::<u64>() + unpack;
        let converted = self.done("convert");
        let mut had: u64 = if converted { plan.derived.iter().map(|d| d.bytes).sum() } else { 0 };
        for job in &plan.jobs {
            let fs = self.state.files.get(&job.id).cloned().unwrap_or_default();
            let installed = matches!(job.kind, FileKind::CrowPackage | FileKind::EnginePackage)
                && self.done(&Self::install_key(job));
            // a convert input or an unpacked archive is never fetched again
            let consumed = self.consumed(job);
            had += if installed || consumed || (fs.verified && self.have(job)) || self.steps.costs_no_disk(job) {
                job.bytes
            } else {
                fs.bytes_done
            };
        }
        let need = peak.saturating_sub(had);
        let free = self.steps.disk_free(root);
        // 0 is "could not read": preflight already says so, do not block on it.
        if free > 0 && need > free {
            return Err(Stop::Fatal(format!(
                "Needs {} free disk at {}. This drive has {} free.",
                gb(need),
                root.display(),
                gb(free)
            )));
        }
        Ok(())
    }

    /// Before Start, a saved unfinished selection: tell the UI what is on disk.
    fn replay(&mut self, plan: &Plan) {
        self.emit(Event::Planned(plan.clone()));
        for job in &plan.jobs {
            let fs = self.state.files.get(&job.id).cloned().unwrap_or_default();
            if fs.verified {
                self.emit(Event::FileVerified { id: job.id.clone() });
            } else if fs.bytes_done > 0 {
                self.emit(Event::FileProgress { id: job.id.clone(), done: fs.bytes_done, total: job.bytes });
            }
        }
        let done: Vec<String> = self.state.steps_done.clone();
        for s in done {
            let name = s.split(':').next().unwrap_or(&s).to_string();
            self.step_event(&name, StepStatus::Ok, "Done before.");
        }
    }

    /// Run one install step; on failure wait for Retry{name} or Quit.
    fn step(&mut self, name: &str, f: &mut dyn FnMut(&mut dyn Steps) -> Result<String, String>) -> Result<(), Stop> {
        loop {
            if !self.ctl.gate() {
                return Err(Stop::Quit);
            }
            self.step_event(name, StepStatus::Running, "");
            match f(self.steps) {
                Ok(detail) => {
                    self.step_event(name, StepStatus::Ok, detail);
                    return Ok(());
                }
                Err(e) => {
                    self.step_event(name, StepStatus::Failed, e.clone());
                    let again = self.ctl.wait(|i| match i {
                        Input::Command(Command::Retry { id }) if id == name => Some(()),
                        _ => None,
                    });
                    if again.is_none() {
                        return Err(if self.ctl.quit() { Stop::Quit } else { Stop::Fatal(e) });
                    }
                }
            }
        }
    }

    /// Fetch every job; failures wait for Retry{id} after the rest is done.
    fn fetch_all(&mut self, jobs: &[&FileJob]) -> Result<(), Stop> {
        let mut failed: Vec<(&FileJob, String)> = Vec::new();
        for job in jobs {
            if let FileResult::Failed(m) = self.fetch_one(job)? {
                failed.push((job, m));
            }
        }
        while !failed.is_empty() {
            let ids: Vec<String> = failed.iter().map(|(j, _)| j.id.clone()).collect();
            let Some(id) = self.ctl.wait(|i| match i {
                Input::Command(Command::Retry { id }) if ids.contains(id) => Some(id.clone()),
                _ => None,
            }) else {
                if self.ctl.quit() {
                    return Err(Stop::Quit);
                }
                let list: Vec<String> = failed.iter().map(|(j, m)| format!("{}: {m}", j.id)).collect();
                return Err(Stop::Fatal(list.join("; ")));
            };
            let pos = failed.iter().position(|(j, _)| j.id == id).expect("id is in the failed list");
            let job = failed[pos].0;
            match self.fetch_one(job)? {
                FileResult::Ok => {
                    failed.remove(pos);
                }
                FileResult::Failed(m) => failed[pos].1 = m,
            }
        }
        Ok(())
    }

    fn fetch_one(&mut self, job: &FileJob) -> Result<FileResult, Stop> {
        let known = self.state.files.get(&job.id).cloned().unwrap_or_default();
        // a convert input is never needed once the convert is done (a source
        // that held the converted output never had the input at all, #342)
        let consumed = self.consumed(job);
        if consumed || (known.verified && self.have(job)) {
            self.emit(Event::FileVerified { id: job.id.clone() });
            return Ok(FileResult::Ok);
        }
        loop {
            if !self.ctl.gate() {
                return Err(Stop::Quit);
            }
            let ctl = Arc::clone(&self.ctl);
            let res = self.steps.download(job, &mut self.state, self.on, &ctl.cancel);
            match res {
                Ok(()) => {
                    let fs = self.state.files.entry(job.id.clone()).or_default();
                    fs.verified = true;
                    fs.bytes_done = job.bytes;
                    self.save();
                    return Ok(FileResult::Ok);
                }
                Err(FetchError::Cancelled) => {
                    self.save();
                    if self.ctl.quit() {
                        return Err(Stop::Quit);
                    }
                    // Paused: the gate waits for Resume, then the part continues.
                }
                Err(e) => {
                    // The fetcher retries the network itself and refetches a sha
                    // mismatch once; what reaches here does not heal by looping
                    // (retryable: false), the UI offers Retry. A local I/O error
                    // (disk full, file locked) may.
                    let retryable = matches!(e, FetchError::Io(_));
                    let message = e.to_string();
                    self.save();
                    self.emit(Event::FileError { id: job.id.clone(), message: message.clone(), retryable });
                    return Ok(FileResult::Failed(message));
                }
            }
        }
    }

    /// After Done: open the boot menu, move the shortcut, until Quit or the
    /// channel is gone.
    fn after_done(&mut self, py: &PythonInfo, root: &Path, mut shortcut: Option<PathBuf>) {
        while let Some(input) = self.ctl.wait(|i| match i {
            Input::Command(Command::OpenBootMenu) | Input::ShortcutDir(_) => Some(i.clone()),
            _ => None,
        }) {
            match input {
                Input::Command(Command::OpenBootMenu) => match self.steps.open_boot_menu(py, root) {
                    Ok(()) => self.step_event("boot_menu", StepStatus::Ok, "Boot menu opened."),
                    Err(e) => self.step_event("boot_menu", StepStatus::Failed, e),
                },
                Input::ShortcutDir(dir) => match self.steps.shortcuts(py, root, std::slice::from_ref(&dir)) {
                    Ok(()) => {
                        let new = shortcut_file(&dir);
                        if let Some(old) = shortcut.take().filter(|o| *o != new) {
                            let _ = std::fs::remove_file(old);
                        }
                        shortcut = Some(new);
                        if let Some(sel) = self.state.selection.as_mut() {
                            sel.shortcut_dir = Some(dir.clone());
                        }
                        self.save();
                        self.step_event("shortcuts", StepStatus::Ok, dir.display().to_string());
                    }
                    Err(e) => self.step_event("shortcuts", StepStatus::Warning, e),
                },
                _ => {}
            }
        }
    }
}

// --------------------------------------------------------------- real steps

/// The same file (one inode), so nothing needs linking.
fn same_file(a: &Path, b: &Path) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if let (Ok(x), Ok(y)) = (std::fs::metadata(a), std::fs::metadata(b)) {
            return x.dev() == y.dev() && x.ino() == y.ino();
        }
    }
    let _ = (a, b);
    false
}

/// The steps on the real modules (T1-T3).
pub struct RealSteps {
    pub source: Source,
    pub packages: Packages,
    pub python_zip: Option<&'static [u8]>,
    pub get_pip: Option<&'static [u8]>,
    /// `--package-source`: Crow's package and the engine package come from
    /// `<dir>/<asset>`, every other file from `source`.
    pub package_source: Option<PathBuf>,
    stack: Option<crate::stack::Stack>,
    /// `${MODELS}` of the last planned selection (for a local source's models layout).
    models: Option<PathBuf>,
}

/// The path of `job` inside a local source: `<repo>/<path>` when the folder
/// has it, else its path under `models_root` when the folder has that (a
/// models tree), else `<repo>/<path>` (the error names the remote layout).
pub fn local_rel_for(src: &Path, job: &FileJob, models_root: &Path) -> String {
    if src.join(&job.local_rel).is_file() {
        return job.local_rel.clone();
    }
    if let Ok(rel) = job.dest.strip_prefix(models_root) {
        let parts: Vec<String> = rel.components().map(|c| c.as_os_str().to_string_lossy().into_owned()).collect();
        let rel = parts.join("/");
        if !rel.is_empty() && src.join(&rel).is_file() {
            return rel;
        }
    }
    job.local_rel.clone()
}

/// Linux: the device of `path`'s nearest existing ancestor.
#[cfg(unix)]
fn device_of(path: &Path) -> Option<u64> {
    use std::os::unix::fs::MetadataExt;
    let p = crate::preflight::nearest_existing(path)?;
    std::fs::metadata(p).ok().map(|m| m.dev())
}

/// Linux: `src` resolves to a regular file of `bytes` on the device `dest` lands on.
#[cfg(unix)]
fn linkable_file(src: &Path, bytes: u64, dest: &Path) -> Option<PathBuf> {
    use std::os::unix::fs::MetadataExt;
    let real = std::fs::canonicalize(src).ok()?;
    let m = std::fs::metadata(&real).ok()?;
    (m.is_file() && m.len() == bytes && Some(m.dev()) == device_of(dest)).then_some(real)
}

impl RealSteps {
    pub fn new(
        source: Source,
        packages: Packages,
        python_zip: Option<&'static [u8]>,
        get_pip: Option<&'static [u8]>,
    ) -> RealSteps {
        RealSteps { source, packages, python_zip, get_pip, package_source: None, stack: None, models: None }
    }

    pub fn with_package_source(mut self, dir: Option<PathBuf>) -> RealSteps {
        self.package_source = dir;
        self
    }

    /// A stack other than the embedded one (tests).
    pub fn with_stack(mut self, stack: crate::stack::Stack) -> RealSteps {
        self.stack = Some(stack);
        self
    }

    fn stack(&mut self) -> &crate::stack::Stack {
        self.stack.get_or_insert_with(crate::stack::Stack::embedded)
    }

    fn fetch_options(&self) -> FetchOptions {
        FetchOptions::production(self.source.clone())
    }

    /// The local file a job would come from, when the job comes from a folder.
    #[cfg_attr(not(unix), allow(dead_code))]
    fn local_file(&self, job: &FileJob, models_root: &Path) -> Option<PathBuf> {
        match (job.kind, &self.package_source, &self.source) {
            (FileKind::CrowPackage | FileKind::EnginePackage, Some(dir), _) => Some(dir.join(job.dest.file_name()?)),
            (_, _, Source::Local(dir)) => Some(dir.join(local_rel_for(dir, job, models_root))),
            _ => None,
        }
    }

    /// Every output of `d` in the local source, as (source file, destination),
    /// when all are there with their size (and sha256 where pinned) on the
    /// device they land on. Linux only: elsewhere this is never a link.
    fn derived_from_source(&mut self, d: &crate::api::DerivedJob, models_root: &Path) -> Option<Vec<(PathBuf, PathBuf)>> {
        #[cfg(unix)]
        {
            let Source::Local(dir) = self.source.clone() else { return None };
            let entry = self.stack().derived_entry(&d.id)?.clone();
            let src_dir = dir.join(d.dest.strip_prefix(models_root).ok()?);
            let mut out = Vec::new();
            for o in &entry.outputs {
                let dest = d.dest.join(&o.path);
                let real = linkable_file(&src_dir.join(&o.path), o.bytes, &d.dest)?;
                if let Some(want) = &o.sha256
                    && !crate::layout::sha256_file_hex(&real).ok()?.eq_ignore_ascii_case(want)
                {
                    return None;
                }
                out.push((real, dest));
            }
            return (!out.is_empty()).then_some(out);
        }
        #[allow(unreachable_code)]
        {
            let _ = (d, models_root);
            None
        }
    }

    /// A point's disk need with a local source: what cannot be linked.
    #[cfg(unix)]
    fn point_disk_need(&mut self, stack: &crate::stack::Stack, p: &crate::stack::Point, root: &Path) -> u64 {
        let models = models_root(root);
        let sel = Selection { points: vec![p.id.clone()], install_root: root.to_path_buf(), shortcut_dir: None };
        let Ok(plan) = crate::plan::plan(stack, &sel, &models, &self.packages) else { return p.preflight.disk_bytes };
        let mut need = 0;
        let mut prefilled = std::collections::BTreeSet::new();
        for d in &plan.derived {
            if self.derived_from_source(d, &models).is_some() {
                prefilled.extend(d.inputs.iter().cloned());
            } else {
                need += d.bytes;
            }
        }
        for j in plan.jobs.iter().filter(|j| j.points.contains(&p.id) && !prefilled.contains(&j.id)) {
            let linked = self.local_file(j, &models).and_then(|f| linkable_file(&f, j.bytes, &j.dest)).is_some();
            if !linked {
                need += j.bytes;
            }
        }
        need
    }
}

impl Steps for RealSteps {
    fn preflight(&mut self, install_root: &Path) -> PreflightReport {
        let stack = self.stack().clone();
        #[cfg(unix)]
        if matches!(self.source, Source::Local(_)) {
            let facts = crate::preflight::probe(install_root);
            let needs: std::collections::BTreeMap<String, u64> =
                stack.points.iter().map(|p| (p.id.clone(), self.point_disk_need(&stack, p, install_root))).collect();
            let need = |p: &crate::stack::Point| needs.get(&p.id).copied().unwrap_or(p.preflight.disk_bytes);
            return crate::preflight::verdicts_with_disk(&facts, &stack, &need);
        }
        crate::preflight::run(&stack, install_root)
    }
    fn plan(&mut self, sel: &Selection) -> Result<Plan, String> {
        let packages = self.packages.clone();
        let models = models_root(&sel.install_root);
        self.models = Some(models.clone());
        crate::plan::plan(self.stack(), sel, &models, &packages)
    }
    fn prefill_derived(&mut self, plan: &Plan, models_root: &Path) -> bool {
        let mut pairs = Vec::new();
        for d in &plan.derived {
            match self.derived_from_source(d, models_root) {
                Some(p) => pairs.extend(p),
                None => return false,
            }
        }
        let mut made = Vec::new();
        for (src, dest) in &pairs {
            if same_file(src, dest) {
                continue;
            }
            let ok = dest.parent().is_some_and(|p| std::fs::create_dir_all(p).is_ok())
                && { let _ = std::fs::remove_file(dest); std::fs::hard_link(src, dest).is_ok() };
            if !ok {
                // all or nothing: the convert step runs on a clean folder
                for m in &made {
                    let _ = std::fs::remove_file(m);
                }
                return false;
            }
            made.push(dest.clone());
        }
        !pairs.is_empty()
    }
    fn costs_no_disk(&mut self, job: &FileJob) -> bool {
        #[cfg(unix)]
        {
            let Some(models) = self.models.clone() else { return false };
            return self.local_file(job, &models).and_then(|f| linkable_file(&f, job.bytes, &job.dest)).is_some();
        }
        #[allow(unreachable_code)]
        {
            let _ = job;
            false
        }
    }
    fn load_state(&mut self, path: &Path) -> std::io::Result<StateStore> {
        if path.exists() {
            StateStore::load(path)
        } else {
            Ok(StateStore { path: path.to_path_buf(), ..StateStore::default() })
        }
    }
    fn save_state(&mut self, state: &StateStore) -> std::io::Result<()> {
        state.save()
    }
    fn note(&mut self, log: &Path, line: &str) {
        use std::io::Write;
        // the log is evidence, not part of the install: a failure is dropped
        if let Some(dir) = log.parent() {
            let _ = std::fs::create_dir_all(dir);
        }
        let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_secs());
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(log) {
            let _ = writeln!(f, "{} {line}", utc_stamp(secs));
        }
    }
    fn present(&mut self, job: &FileJob) -> bool {
        job.dest.is_file()
    }
    fn discard(&mut self, job: &FileJob) {
        // a zip that cannot be deleted costs disk, not the install
        let _ = std::fs::remove_file(&job.dest);
    }
    fn runtimes(&mut self, sel: &Selection) -> Vec<RuntimeJob> {
        let models = models_root(&sel.install_root);
        crate::runtime::jobs(self.stack(), sel, &models)
    }
    fn runtime_current(&mut self, job: &RuntimeJob) -> bool {
        crate::runtime::is_current(job)
    }
    fn unpack_runtime(&mut self, job: &RuntimeJob, cancel: &AtomicBool) -> Result<String, String> {
        crate::runtime::unpack(job, cancel, &mut |_, _| {})
    }
    fn nvidia(&mut self, sel: &Selection) -> Result<Vec<NvidiaJob>, String> {
        crate::nvidia::jobs(self.stack(), sel)
    }
    fn nvidia_current(&mut self, job: &NvidiaJob) -> bool {
        crate::nvidia::is_current(job)
    }
    fn unpack_nvidia(&mut self, job: &NvidiaJob, cancel: &AtomicBool) -> Result<String, String> {
        crate::nvidia::unpack(job, cancel)
    }
    fn disk_free(&mut self, dir: &Path) -> u64 {
        crate::preflight::disk_free(dir)
    }
    fn download(
        &mut self,
        job: &FileJob,
        state: &mut StateStore,
        on: &mut dyn FnMut(Event),
        cancel: &AtomicBool,
    ) -> Result<(), FetchError> {
        if let (FileKind::CrowPackage | FileKind::EnginePackage, Some(dir)) = (job.kind, &self.package_source) {
            // same .part, resume and sha256 rules, from <dir>/<asset>
            let mut local = job.clone();
            local.local_rel = job.dest.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            return crate::fetch::download(&local, state, &FetchOptions::production(Source::Local(dir.clone())), on, cancel);
        }
        if let (Source::Local(dir), Some(models)) = (&self.source, &self.models) {
            let rel = local_rel_for(dir, job, models);
            if rel != job.local_rel {
                let mut local = job.clone();
                local.local_rel = rel;
                return crate::fetch::download(&local, state, &self.fetch_options(), on, cancel);
            }
        }
        crate::fetch::download(job, state, &self.fetch_options(), on, cancel)
    }
    fn install_crow(&mut self, zip: &Path, install_root: &Path) -> Result<String, String> {
        crate::layout::install_crow_package(zip, install_root)
    }
    fn install_engine(&mut self, zip: &Path, install_root: &Path) -> Result<String, String> {
        crate::layout::install_engine_package(zip, install_root)
    }
    fn ensure_python(&mut self, install_root: &Path) -> Result<PythonInfo, String> {
        crate::python::ensure(install_root, self.python_zip, self.get_pip)
    }
    fn convert(&mut self, py: &PythonInfo, install_root: &Path, models_root: &Path) -> Result<(), String> {
        crate::convert::image_text_encoder(py, install_root, models_root)
    }
    fn check_point(
        &mut self,
        py: &PythonInfo,
        install_root: &Path,
        models_root: &Path,
        point: &str,
    ) -> Result<(), String> {
        crate::check::check_point(py, install_root, models_root, point)
    }
    fn shortcuts(&mut self, py: &PythonInfo, install_root: &Path, dirs: &[PathBuf]) -> Result<(), String> {
        crate::finish::shortcuts(py, install_root, dirs)
    }
    fn open_boot_menu(&mut self, py: &PythonInfo, install_root: &Path) -> Result<(), String> {
        crate::finish::open_boot_menu(py, install_root)
    }
}

// ------------------------------------------------------------------ testing

/// A [`Steps`] without network, disk writes or Python, for the tests and
/// `--selftest`. Every call is logged; failures and a blocking download are
/// configured per file id or step name.
pub mod testing {
    use super::*;
    use std::collections::BTreeMap;
    use std::time::Duration;

    /// What `save_state` last wrote (StateStore itself is not Clone).
    #[derive(Debug, Default, Clone)]
    pub struct Saved {
        pub selection: Option<Selection>,
        pub files: BTreeMap<String, FileState>,
        pub steps_done: Vec<String>,
    }

    #[derive(Default)]
    pub struct Shared {
        pub log: Vec<String>,
        /// The state as last saved; `load_state` returns it.
        pub saved: Option<Saved>,
        /// file id -> how many more downloads fail with a permanent error.
        pub fail_permanent: BTreeMap<String, u32>,
        /// file id -> how many more downloads end in a sha mismatch.
        pub mismatch: BTreeMap<String, u32>,
        /// step name -> how many more calls fail.
        pub fail_step: BTreeMap<String, u32>,
        /// A download of this id runs in chunks until cancelled or released.
        pub block_on: Option<String>,
        pub release: bool,
        pub report: Option<PreflightReport>,
        /// Ids of fetched files that are "on disk"; a test removes one to
        /// play a deleted file.
        pub present: std::collections::BTreeSet<String>,
        /// Free disk bytes; None is 1 TiB.
        pub disk_free: Option<u64>,
        /// #340: the unpacked runtime folder was deleted.
        pub runtime_gone: bool,
        /// The selection needs an NVIDIA wheel (`nvidia-fake`, 30 bytes, 70
        /// extracted); off by default, so the other tests' plans stay as they were.
        pub nvidia: bool,
        /// The libraries taken out of the fake wheel are gone again.
        pub nvidia_gone: bool,
        /// #338: `load_state` fails with this error kind.
        pub fail_load: Option<std::io::ErrorKind>,
        /// #338: every `save_state` fails with this error kind.
        pub fail_save: Option<std::io::ErrorKind>,
        /// #338: the lines `note` was given, as `<log file name>: <line>`.
        pub notes: Vec<String>,
    }

    #[derive(Clone, Default)]
    pub struct FakeSteps {
        pub shared: Arc<Mutex<Shared>>,
    }

    /// A machine that can run everything.
    pub fn report() -> PreflightReport {
        PreflightReport {
            os_64bit: true,
            gpu_name: Some("NVIDIA GeForce RTX 5090".into()),
            vram_mib: Some(32607),
            compute_cap: Some("12.0".into()),
            ram_bytes: 64 << 30,
            disk_free_bytes: 500 << 30,
            webview2: true,
            hard_block: None,
            blocked: vec![],
        }
    }

    fn job(id: &str, kind: FileKind, bytes: u64, points: &[&str], root: &Path) -> FileJob {
        FileJob {
            id: id.into(),
            kind,
            url: format!("https://example.invalid/{id}"),
            local_rel: id.into(),
            dest: root.join("fake").join(id),
            bytes,
            sha256: format!("{bytes:064x}"),
            points: points.iter().map(|p| p.to_string()).collect(),
        }
    }

    /// The fake plan, shaped like `plan::plan`: two packages and whisper with
    /// empty `points`, one container per point; the image stack shares the 27B
    /// container and carries a derived file.
    pub fn plan(sel: &Selection) -> Plan {
        let root = &sel.install_root;
        let mut jobs = vec![
            job("crow-package", FileKind::CrowPackage, 600, &[], root),
            job("engine-package", FileKind::EnginePackage, 49, &[], root),
            job("whisper", FileKind::Whisper, 150, &[], root),
        ];
        let has = |p: &str| sel.points.iter().any(|x| x == p);
        if has("27b") || has("image-stack") {
            let pts: Vec<&str> = ["27b", "image-stack"].into_iter().filter(|p| has(p)).collect();
            jobs.push(job("27b-cnq", FileKind::Model, 1880, &pts, root));
        }
        if has("image-stack") {
            jobs.push(job("qi-transformer", FileKind::Model, 1400, &["image-stack"], root));
            // The convert input (upstream text_encoder/); size 0 keeps the
            // tests' disk arithmetic as it was before the fake had one.
            jobs.push(job("qi-text-encoder", FileKind::Model, 0, &["image-stack"], root));
        }
        if has("flash-next") {
            jobs.push(job("fn-cnq", FileKind::Model, 10560, &["flash-next"], root));
        }
        if has("media-stack") {
            // #340: the video runtime's archive, unpacked and then deleted.
            jobs.push(job("comfyui-portable", FileKind::Model, 199, &["media-stack"], root));
        }
        let derived = if has("image-stack") {
            vec![crate::api::DerivedJob {
                id: "qi-text-encoder-sdcli".into(),
                dest: root.join("fake").join("sdcli"),
                bytes: 1750,
                points: vec!["image-stack".into()],
                inputs: vec!["qi-text-encoder".into()],
            }]
        } else {
            vec![]
        };
        let download_bytes = jobs.iter().map(|j| j.bytes).sum();
        Plan { download_bytes, disk_bytes: download_bytes, jobs, derived }
    }

    pub fn python() -> PythonInfo {
        PythonInfo { exe: PathBuf::from("python.exe"), version: "3.13.7".into(), bundled: false, warnings: vec![] }
    }

    impl FakeSteps {
        pub fn log(&self) -> Vec<String> {
            self.shared.lock().unwrap().log.clone()
        }
        fn push(&self, s: String) {
            self.shared.lock().unwrap().log.push(s);
        }
        /// Consume one configured failure of `name`.
        fn fails(&self, name: &str) -> Result<(), String> {
            let mut sh = self.shared.lock().unwrap();
            match sh.fail_step.get_mut(name) {
                Some(n) if *n > 0 => {
                    *n -= 1;
                    Err(format!("{name} failed (fake)"))
                }
                _ => Ok(()),
            }
        }
        fn step(&self, log: &str, name: &str) -> Result<(), String> {
            self.push(log.to_string());
            self.fails(name)
        }
    }

    impl Steps for FakeSteps {
        fn preflight(&mut self, _root: &Path) -> PreflightReport {
            self.push("preflight".into());
            self.shared.lock().unwrap().report.clone().unwrap_or_else(report)
        }
        fn plan(&mut self, sel: &Selection) -> Result<Plan, String> {
            self.push("plan".into());
            Ok(plan(sel))
        }
        fn load_state(&mut self, path: &Path) -> std::io::Result<StateStore> {
            if let Some(kind) = self.shared.lock().unwrap().fail_load {
                return Err(std::io::Error::new(kind, "fake load failure"));
            }
            let saved = self.shared.lock().unwrap().saved.clone().unwrap_or_default();
            Ok(StateStore {
                path: path.to_path_buf(),
                selection: saved.selection,
                files: saved.files,
                steps_done: saved.steps_done,
            })
        }
        fn save_state(&mut self, state: &StateStore) -> std::io::Result<()> {
            if let Some(kind) = self.shared.lock().unwrap().fail_save {
                return Err(std::io::Error::new(kind, "fake save failure"));
            }
            self.shared.lock().unwrap().saved = Some(Saved {
                selection: state.selection.clone(),
                files: state.files.clone(),
                steps_done: state.steps_done.clone(),
            });
            Ok(())
        }
        fn note(&mut self, log: &Path, line: &str) {
            let name = log.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            self.shared.lock().unwrap().notes.push(format!("{name}: {line}"));
        }
        fn present(&mut self, job: &FileJob) -> bool {
            self.shared.lock().unwrap().present.contains(&job.id)
        }
        fn discard(&mut self, job: &FileJob) {
            self.shared.lock().unwrap().present.remove(&job.id);
        }
        fn disk_free(&mut self, _dir: &Path) -> u64 {
            self.shared.lock().unwrap().disk_free.unwrap_or(1 << 40)
        }
        fn download(
            &mut self,
            job: &FileJob,
            state: &mut StateStore,
            on: &mut dyn FnMut(Event),
            cancel: &AtomicBool,
        ) -> Result<(), FetchError> {
            let from = state.files.get(&job.id).map(|f| f.bytes_done).unwrap_or(0);
            self.push(format!("download {} from {from}", job.id));
            {
                let mut sh = self.shared.lock().unwrap();
                if let Some(n) = sh.fail_permanent.get_mut(&job.id).filter(|n| **n > 0) {
                    *n -= 1;
                    return Err(FetchError::Permanent(format!("404 Not Found: {}", job.url)));
                }
                if let Some(n) = sh.mismatch.get_mut(&job.id).filter(|n| **n > 0) {
                    *n -= 1;
                    return Err(FetchError::Mismatch {
                        id: job.id.clone(),
                        expected: job.sha256.clone(),
                        got: "0".repeat(64),
                    });
                }
            }
            on(Event::FileStarted { id: job.id.clone(), from_byte: from, total: job.bytes });
            let blocking = self.shared.lock().unwrap().block_on.as_deref() == Some(job.id.as_str());
            let mut done = from;
            if blocking {
                loop {
                    if cancel.load(Ordering::SeqCst) {
                        state.files.entry(job.id.clone()).or_default().bytes_done = done;
                        self.push(format!("cancelled {} at {done}", job.id));
                        return Err(FetchError::Cancelled);
                    }
                    if self.shared.lock().unwrap().release {
                        break;
                    }
                    done = (done + 10).min(job.bytes - 1);
                    state.files.entry(job.id.clone()).or_default().bytes_done = done;
                    on(Event::FileProgress { id: job.id.clone(), done, total: job.bytes });
                    std::thread::sleep(Duration::from_millis(2));
                }
            }
            on(Event::FileProgress { id: job.id.clone(), done: job.bytes, total: job.bytes });
            let fs = state.files.entry(job.id.clone()).or_default();
            fs.bytes_done = job.bytes;
            fs.verified = true;
            self.shared.lock().unwrap().present.insert(job.id.clone());
            on(Event::FileVerified { id: job.id.clone() });
            Ok(())
        }
        fn install_crow(&mut self, _zip: &Path, _root: &Path) -> Result<String, String> {
            self.step("install crow", "crow").map(|_| "Crow 3.0.0 installed (60 files)".into())
        }
        fn install_engine(&mut self, _zip: &Path, _root: &Path) -> Result<String, String> {
            self.step("install engine", "engine").map(|_| "engine 0.9.0 installed (4 files)".into())
        }
        fn ensure_python(&mut self, _root: &Path) -> Result<PythonInfo, String> {
            self.step("python", "python").map(|_| python())
        }
        fn convert(&mut self, _py: &PythonInfo, _root: &Path, _models: &Path) -> Result<(), String> {
            self.step("convert", "convert")?;
            // like te_rename + the delete: the input is gone, its state stays verified
            self.shared.lock().unwrap().present.remove("qi-text-encoder");
            Ok(())
        }
        fn check_point(&mut self, _py: &PythonInfo, _root: &Path, _models: &Path, point: &str) -> Result<(), String> {
            self.step(&format!("check {point}"), "check")
        }
        fn runtimes(&mut self, sel: &Selection) -> Vec<RuntimeJob> {
            if !sel.points.iter().any(|p| p == "media-stack") {
                return Vec::new();
            }
            vec![RuntimeJob {
                point: "media-stack".into(),
                file_id: "comfyui-portable".into(),
                archive: sel.install_root.join("fake").join("comfyui-portable"),
                sha256: "comfyui-portable".into(),
                dir: sel.install_root.join("comfyui"),
                strip: "ComfyUI_windows_portable".into(),
                model_paths: None,
                bytes: 4000,
            }]
        }
        fn runtime_current(&mut self, _job: &RuntimeJob) -> bool {
            !self.shared.lock().unwrap().runtime_gone
        }
        fn nvidia(&mut self, sel: &Selection) -> Result<Vec<NvidiaJob>, String> {
            if !self.shared.lock().unwrap().nvidia || sel.points.is_empty() {
                return Ok(Vec::new());
            }
            let root = &sel.install_root;
            Ok(vec![NvidiaJob {
                file: job("nvidia-fake", FileKind::NvidiaWheel, 30, &[], root),
                install_root: root.clone(),
                members: vec![crate::nvidia::NvidiaMember {
                    member: "nvidia/cu13/lib/fake.so".into(),
                    dest: root.join("bin").join("fake.so"),
                    bytes: 70,
                    sha256: "0".repeat(64),
                }],
            }])
        }
        fn nvidia_current(&mut self, _job: &NvidiaJob) -> bool {
            !self.shared.lock().unwrap().nvidia_gone
        }
        fn unpack_nvidia(&mut self, job: &NvidiaJob, _cancel: &AtomicBool) -> Result<String, String> {
            self.step(&format!("unpack nvidia {}", job.file.id), "nvidia")?;
            self.shared.lock().unwrap().nvidia_gone = false;
            Ok("nvidia-fake.whl from NVIDIA (1 files written)".into())
        }
        fn unpack_runtime(&mut self, job: &RuntimeJob, _cancel: &AtomicBool) -> Result<String, String> {
            self.step(&format!("unpack runtime {}", job.file_id), "runtime")?;
            self.shared.lock().unwrap().runtime_gone = false;
            Ok("ComfyUI runtime unpacked (3 files, 0.0 GB)".into())
        }
        fn shortcuts(&mut self, _py: &PythonInfo, _root: &Path, dirs: &[PathBuf]) -> Result<(), String> {
            self.step(&format!("shortcuts {}", dirs.len()), "shortcuts")
        }
        fn open_boot_menu(&mut self, _py: &PythonInfo, _root: &Path) -> Result<(), String> {
            self.step("boot menu", "boot_menu")
        }
    }

    /// A selection under `root`, with a shortcut folder.
    pub fn selection(points: &[&str], root: &Path) -> Selection {
        Selection {
            points: points.iter().map(|p| p.to_string()).collect(),
            install_root: root.to_path_buf(),
            shortcut_dir: Some(root.join("Desktop")),
        }
    }

    pub fn options(root: &Path) -> RunOptions {
        RunOptions {
            launch_root: root.to_path_buf(),
            state_path: state_path(root),
            start_menu_dir: Some(root.join("Start Menu")),
        }
    }

    /// The calls a full fresh run logs, in order, for `points`.
    pub fn expected_order(points: &[&str]) -> Vec<String> {
        let sel = selection(points, Path::new("x"));
        let plan = plan(&sel);
        let mut v = vec!["preflight".to_string(), "plan".to_string()];
        for j in plan.jobs.iter().filter(|j| matches!(j.kind, FileKind::CrowPackage | FileKind::EnginePackage)) {
            v.push(format!("download {} from 0", j.id));
        }
        v.push("install crow".into());
        v.push("install engine".into());
        v.push("python".into());
        for j in plan.jobs.iter().filter(|j| matches!(j.kind, FileKind::Model | FileKind::Whisper)) {
            v.push(format!("download {} from 0", j.id));
        }
        if points.contains(&"media-stack") {
            v.push("unpack runtime comfyui-portable".into());
        }
        if !plan.derived.is_empty() {
            v.push("convert".into());
        }
        for p in points {
            v.push(format!("check {p}"));
        }
        v.push("shortcuts 2".into());
        v
    }

    /// Run to the end on a channel that carries Start(sel) and then closes.
    pub fn run_once(steps: &mut FakeSteps, sel: &Selection) -> (Outcome, Vec<Event>) {
        let (tx, rx) = std::sync::mpsc::channel();
        tx.send(Input::Command(Command::Start(sel.clone()))).unwrap();
        drop(tx);
        let mut events = Vec::new();
        let out = run(steps, &options(&sel.install_root), &mut |e| events.push(e), rx);
        (out, events)
    }

    /// The `--selftest` scenarios: (name, Ok or what went wrong).
    pub fn scenarios() -> Vec<(&'static str, Result<(), String>)> {
        let root = std::env::temp_dir().join("crowsetup-selftest");
        let order = |points: &[&str]| -> Result<(), String> {
            let mut f = FakeSteps::default();
            let (o, _) = run_once(&mut f, &selection(points, &root));
            if o != Outcome::Done {
                return Err(format!("outcome {o:?}"));
            }
            let (want, got) = (expected_order(points), f.log());
            if got != want {
                return Err(format!("order {got:?}, expected {want:?}"));
            }
            Ok(())
        };
        let resume = || -> Result<(), String> {
            let mut f = FakeSteps::default();
            let sel = selection(&["27b"], &root);
            run_once(&mut f, &sel);
            {
                let mut sh = f.shared.lock().unwrap();
                sh.log.clear();
                // Closed before Done: the state has everything but the finish.
                if let Some(s) = sh.saved.as_mut() {
                    s.steps_done.retain(|x| x != "done" && x != "shortcuts");
                }
            }
            let (o, _) = run_once(&mut f, &sel);
            let log = f.log();
            if o != Outcome::Done || log.iter().any(|l| l.starts_with("download") || l.starts_with("install")) {
                return Err(format!("{o:?} {log:?}"));
            }
            Ok(())
        };
        let permanent = || -> Result<(), String> {
            let mut f = FakeSteps::default();
            f.shared.lock().unwrap().fail_permanent.insert("27b-cnq".into(), 1);
            let (o, ev) = run_once(&mut f, &selection(&["27b"], &root));
            let err = ev.iter().any(|e| matches!(e, Event::FileError { retryable: false, .. }));
            if !matches!(o, Outcome::Fatal(_)) || !err {
                return Err(format!("{o:?}"));
            }
            Ok(())
        };
        vec![
            ("run order, 27b", order(&["27b"])),
            ("run order, image stack converts", order(&["27b", "image-stack"])),
            ("resume skips what is done", resume()),
            ("permanent failure without a retry ends fatal", permanent()),
        ]
    }
}
