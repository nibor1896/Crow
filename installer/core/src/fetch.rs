//! T1: resumable download of one [`FileJob`] (Range + If-Range, unbounded
//! retries, stall detection, `.part` + 64 MB checkpoints, sha256 before rename).
//!
//! Redirects are followed by hand (`max_redirects(0)`): every hop gets the same
//! `Range`/`If-Range`, so they reach the final (CDN) host, and the job URL is
//! requested again on every attempt because the signed CDN URL may expire.
//! ureq has no per-read timeout (`timeout_recv_body` is a total budget), so each
//! attempt runs in a worker thread and the caller watches the channel for
//! stalls and `cancel`.
//!
//! IP FAMILY (#196 P2-E2E): on the owner's machine Hugging Face over IPv6
//! accepts the TCP connection and then resets it (os error 10054, 15 of 15
//! attempts) while IPv4 answers. ureq moves to the next resolved address only
//! when a connect fails, not when an accepted connection is reset, so a request
//! that fails before any response flips the family for the next attempt:
//! any -> IPv4 only (ureq `IpFamily::Ipv4Only`) -> any. The family that got a
//! response is kept, for the rest of this download and for the later files of
//! the same run (a process-wide flag). IPv4-only is never the starting default.
//!
//! LOCAL SOURCE ON LINUX (#342): a `--source` file on the same file system as
//! its destination is hard-linked instead of copied, after its sha256 matched
//! (so the semantics stay: nothing unverified is ever renamed into place). The
//! source is never opened for writing; the install only ever replaces or
//! deletes its own link. A `.part` already begun, another file system, a
//! sha256 that does not match, or a link that fails falls back to the copy.

use crate::api::{Event, FileJob, Source};
use crate::state::StateStore;
use crate::verify::Sha256Stream;
use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};

/// The family the next request uses: false = any (IPv6 first where the
/// resolver says so), true = IPv4 only. See the module docs.
static IPV4_ONLY: AtomicBool = AtomicBool::new(false);

fn family_name(v4: bool) -> &'static str {
    if v4 { "IPv4" } else { "IPv4/IPv6" }
}
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, SyncSender};
use std::time::{Duration, Instant};

#[derive(Debug, Clone)]
pub struct FetchOptions {
    pub source: Source,
    /// Seconds without a byte before the connection is dropped (spec: 30).
    pub stall_secs: u64,
    /// Bytes between fsync + state checkpoints (spec: 64 MiB).
    pub checkpoint_bytes: u64,
    /// Backoff cap in seconds (spec: 30).
    pub max_backoff_secs: u64,
    /// A local source file on the destination's file system is hard-linked
    /// instead of copied (Linux, #342; see the module docs).
    pub link_local: bool,
}

impl FetchOptions {
    /// The spec's values: 30 s stall, 64 MiB checkpoints, 30 s backoff cap.
    pub fn production(source: Source) -> FetchOptions {
        FetchOptions {
            source,
            stall_secs: 30,
            checkpoint_bytes: 64 * 1024 * 1024,
            max_backoff_secs: 30,
            link_local: cfg!(unix),
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum FetchError {
    /// 401/403/404 and friends: not retried in a loop, the UI offers Retry.
    #[error("{0}")]
    Permanent(String),
    #[error("sha256 mismatch for {id}: expected {expected}, got {got}")]
    Mismatch {
        id: String,
        expected: String,
        got: String,
    },
    #[error("cancelled")]
    Cancelled,
    #[error("{0}")]
    Io(#[from] std::io::Error),
}

const CHUNK: usize = 256 * 1024;
const POLL: Duration = Duration::from_millis(50);
const PROGRESS_EVERY: Duration = Duration::from_millis(250);
const PROGRESS_BYTES: u64 = 4 << 20;
const MAX_HOPS: usize = 10;

/// Fetch `job` to `job.dest`, resuming from `<dest>.part` when present.
pub fn download(
    job: &FileJob,
    state: &mut StateStore,
    opts: &FetchOptions,
    on: &mut dyn FnMut(Event),
    cancel: &AtomicBool,
) -> Result<(), FetchError> {
    if let Some(dir) = job.dest.parent().filter(|d| !d.as_os_str().is_empty()) {
        std::fs::create_dir_all(dir)?;
    }
    let mut cx = Cx {
        job,
        state,
        opts,
        on,
        cancel,
        attempt: 0,
    };
    if cx.already_there()? {
        return Ok(());
    }
    // A `verified` entry whose file is not there (deleted, or the image
    // stack's convert input) is stale: start the file over, or a stop
    // part-way leaves a partial file recorded as verified.
    if cx.state.files.get(&job.id).is_some_and(|f| f.verified) {
        cx.state.files.insert(job.id.clone(), Default::default());
        cx.state.save()?;
    }
    #[cfg(unix)]
    if let Source::Local(root) = &opts.source
        && opts.link_local
        && cx.try_link(root)?
    {
        return Ok(());
    }
    for pass in 0..2 {
        let got = cx.transfer()?;
        if got.eq_ignore_ascii_case(&job.sha256) {
            std::fs::rename(part_path(&job.dest), &job.dest)?;
            let f = cx.state.file_mut(&job.id);
            f.verified = true;
            f.bytes_done = job.bytes;
            cx.state.save()?;
            (cx.on)(Event::FileVerified { id: job.id.clone() });
            return Ok(());
        }
        // Only this file is fetched again, once, from byte 0.
        std::fs::remove_file(part_path(&job.dest))?;
        cx.state.files.insert(job.id.clone(), Default::default());
        cx.state.save()?;
        if pass == 1 {
            return Err(FetchError::Mismatch {
                id: job.id.clone(),
                expected: job.sha256.clone(),
                got,
            });
        }
        cx.retry_event(format!(
            "sha256 mismatch (got {got}); fetching again from 0"
        ));
    }
    unreachable!("the second pass returns")
}

/// `<dest>.part`.
fn part_path(dest: &Path) -> PathBuf {
    let mut s = dest.as_os_str().to_owned();
    s.push(".part");
    s.into()
}

fn cancelled(cancel: &AtomicBool) -> Result<(), FetchError> {
    if cancel.load(Ordering::Relaxed) {
        Err(FetchError::Cancelled)
    } else {
        Ok(())
    }
}

/// Hash the first `len` bytes of `file`, stopping promptly on `cancel`.
fn hash_prefix(file: &mut File, len: u64, cancel: &AtomicBool) -> Result<Sha256Stream, FetchError> {
    let mut h = Sha256Stream::new();
    file.seek(SeekFrom::Start(0))?;
    let mut buf = vec![0u8; CHUNK * 4];
    let mut left = len;
    while left > 0 {
        cancelled(cancel)?;
        let n = left.min(buf.len() as u64) as usize;
        file.read_exact(&mut buf[..n])?;
        h.update(&buf[..n]);
        left -= n as u64;
    }
    Ok(h)
}

fn strong(etag: Option<String>) -> Option<String> {
    etag.filter(|e| !e.starts_with("W/") && !e.is_empty())
}

struct Cx<'a> {
    job: &'a FileJob,
    state: &'a mut StateStore,
    opts: &'a FetchOptions,
    on: &'a mut dyn FnMut(Event),
    cancel: &'a AtomicBool,
    /// Counts every retry of this file for [`Event::FileRetry`].
    attempt: u32,
}

/// Why one attempt ended without the whole body.
enum Stop {
    Retry(String),
    Fatal(FetchError),
}

impl From<FetchError> for Stop {
    fn from(e: FetchError) -> Self {
        Stop::Fatal(e)
    }
}

impl From<std::io::Error> for Stop {
    fn from(e: std::io::Error) -> Self {
        Stop::Fatal(e.into())
    }
}

impl Cx<'_> {
    fn retry_event(&mut self, reason: String) {
        self.attempt += 1;
        (self.on)(Event::FileRetry {
            id: self.job.id.clone(),
            attempt: self.attempt,
            reason,
        });
    }

    /// `dest` is already in place: verified in state (return at once), or
    /// present with the right size but unknown to state (hash it once).
    fn already_there(&mut self) -> Result<bool, FetchError> {
        let job = self.job;
        let Ok(meta) = std::fs::metadata(&job.dest) else {
            return Ok(false);
        };
        if !meta.is_file() || meta.len() != job.bytes {
            return Ok(false);
        }
        if !self.state.files.get(&job.id).is_some_and(|f| f.verified) {
            (self.on)(Event::Checking {
                id: job.id.clone(),
                bytes: meta.len(),
            });
            let got = hash_prefix(&mut File::open(&job.dest)?, meta.len(), self.cancel)?.finish();
            if !got.eq_ignore_ascii_case(&job.sha256) {
                return Ok(false);
            }
            let f = self.state.file_mut(&job.id);
            f.verified = true;
            f.bytes_done = job.bytes;
            self.state.save()?;
        }
        (self.on)(Event::FileVerified { id: job.id.clone() });
        Ok(true)
    }

    /// Linux, `--source`: hard-link the source file into place when it is on
    /// the same file system and its sha256 matches. False: copy it instead.
    #[cfg(unix)]
    fn try_link(&mut self, root: &Path) -> Result<bool, FetchError> {
        use std::os::unix::fs::MetadataExt;
        let job = self.job;
        if part_path(&job.dest).exists() {
            return Ok(false);
        }
        // a symlinked source tree links the file itself, never the symlink
        let Ok(src) = std::fs::canonicalize(root.join(&job.local_rel)) else { return Ok(false) };
        let Ok(meta) = std::fs::metadata(&src) else { return Ok(false) };
        let dest_dev = job.dest.parent().and_then(|d| std::fs::metadata(d).ok()).map(|m| m.dev());
        if !meta.is_file() || meta.len() != job.bytes || dest_dev != Some(meta.dev()) {
            return Ok(false);
        }
        (self.on)(Event::Checking { id: job.id.clone(), bytes: meta.len() });
        let got = hash_prefix(&mut File::open(&src)?, meta.len(), self.cancel)?.finish();
        if !got.eq_ignore_ascii_case(&job.sha256) {
            // the copy reports it, with its one refetch, exactly as before
            return Ok(false);
        }
        // a wrong file in the way (already_there said so) goes; the copy would replace it too
        let _ = std::fs::remove_file(&job.dest);
        if std::fs::hard_link(&src, &job.dest).is_err() {
            return Ok(false);
        }
        let f = self.state.file_mut(&job.id);
        f.verified = true;
        f.bytes_done = job.bytes;
        self.state.save()?;
        (self.on)(Event::FileVerified { id: job.id.clone() });
        Ok(true)
    }

    /// Bring `<dest>.part` to the end of the file; returns its sha256.
    fn transfer(&mut self) -> Result<String, FetchError> {
        let mut part = self.open_part()?;
        (self.on)(Event::FileStarted {
            id: self.job.id.clone(),
            from_byte: part.done,
            total: self.job.bytes,
        });
        let (opts, job) = (self.opts, self.job);
        let r = match &opts.source {
            // #365: an upload-pending file has no URL yet (plan.rs).
            Source::Remote if job.url.is_empty() => Err(FetchError::Permanent(not_published(&job.id))),
            Source::Remote => self.remote(&mut part),
            Source::Local(root) => self.local(&mut part, &root.join(&job.local_rel)),
        };
        match r {
            Ok(()) => {
                part.progress(self, true);
                part.checkpoint(self)?;
                Ok(part.hash.finish())
            }
            Err(e) => {
                // Cancel, Permanent, I/O: leave part and state in step.
                let _ = part.checkpoint(self);
                Err(e)
            }
        }
    }

    /// Open the part, cut it back to the last checkpoint and re-hash it.
    fn open_part(&mut self) -> Result<Part, FetchError> {
        let path = part_path(&self.job.dest);
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&path)?;
        let len = file.metadata()?.len();
        // Bytes past the last fsync'd checkpoint may be garbage after a power
        // loss. Without a state entry, the part's length is all we know; the
        // sha256 at the end decides.
        let start = match self.state.files.get(&self.job.id) {
            Some(f) => f.bytes_done.min(len),
            None => len,
        };
        if start < len {
            file.set_len(start)?;
        }
        let hash = if start > 0 {
            (self.on)(Event::Checking {
                id: self.job.id.clone(),
                bytes: start,
            });
            hash_prefix(&mut file, start, self.cancel)?
        } else {
            Sha256Stream::new()
        };
        file.seek(SeekFrom::Start(start))?;
        Ok(Part {
            file,
            hash,
            done: start,
            ckpt_at: start,
            progress_at: Instant::now(),
            progress_bytes: start,
        })
    }

    fn local(&mut self, part: &mut Part, src_path: &Path) -> Result<(), FetchError> {
        let mut src = match File::open(src_path) {
            Ok(f) => f,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                return Err(FetchError::Permanent(format!(
                    "{} is not in the source folder",
                    src_path.display()
                )));
            }
            Err(e) => return Err(e.into()),
        };
        if part.done >= src.metadata()?.len() {
            return Ok(()); // like a 416: the part is complete, verify it
        }
        src.seek(SeekFrom::Start(part.done))?;
        let mut buf = vec![0u8; CHUNK];
        loop {
            cancelled(self.cancel)?;
            let n = match src.read(&mut buf) {
                Ok(0) => return Ok(()),
                Ok(n) => n,
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(e) => return Err(e.into()),
            };
            part.write(self, &buf[..n])?;
        }
    }

    /// Unbounded retries with backoff 1, 2, 4, ... s capped at
    /// `max_backoff_secs`; the backoff restarts after an attempt that moved.
    fn remote(&mut self, part: &mut Part) -> Result<(), FetchError> {
        // one agent per family; the attempt picks by IPV4_ONLY
        let agents = [agent(self.opts, false), agent(self.opts, true)];
        let mut fails: u32 = 0;
        loop {
            cancelled(self.cancel)?;
            let before = part.done;
            let v4 = IPV4_ONLY.load(Ordering::SeqCst);
            match self.attempt(&agents[usize::from(v4)], part) {
                Ok(()) => return Ok(()),
                Err(Stop::Fatal(e)) => return Err(e),
                Err(Stop::Retry(reason)) => {
                    if part.done > before {
                        fails = 0;
                    }
                    let delay = (1u64 << fails.min(20)).min(self.opts.max_backoff_secs);
                    fails = fails.saturating_add(1);
                    self.retry_event(reason);
                    part.checkpoint(self)?;
                    let until = Instant::now() + Duration::from_secs(delay);
                    while Instant::now() < until {
                        cancelled(self.cancel)?;
                        std::thread::sleep(POLL);
                    }
                }
            }
        }
    }

    /// One request (following redirects) and its body into the part.
    fn attempt(&mut self, agent: &ureq::Agent, part: &mut Part) -> Result<(), Stop> {
        let id = self.job.id.clone();
        let offset = part.done;
        let if_range = if offset > 0 {
            strong(self.state.files.get(&id).and_then(|f| f.etag.clone()))
        } else {
            None
        };
        let rx = spawn_request(agent.clone(), self.job.url.clone(), offset, if_range, hf_token());
        let stall = Duration::from_secs(self.opts.stall_secs.max(1));
        let mut last = Instant::now();
        loop {
            cancelled(self.cancel)?;
            let msg = match rx.recv_timeout(POLL) {
                Ok(m) => m,
                Err(RecvTimeoutError::Timeout) if last.elapsed() < stall => continue,
                Err(RecvTimeoutError::Timeout) => {
                    return Err(Stop::Retry(format!(
                        "no bytes for {} s; reconnecting",
                        stall.as_secs()
                    )));
                }
                Err(RecvTimeoutError::Disconnected) => {
                    return Err(Stop::Retry("the connection ended unexpectedly".into()));
                }
            };
            last = Instant::now();
            match msg {
                Msg::Head {
                    status,
                    etag,
                    range_start,
                } => match status {
                    206 => {
                        if range_start != Some(offset) {
                            return Err(Stop::Retry(format!(
                                "206 starts at {range_start:?}, asked for byte {offset}"
                            )));
                        }
                        self.state.file_mut(&id).etag = strong(etag);
                    }
                    200 => {
                        if offset > 0 {
                            self.retry_event(format!(
                                "the server sent the whole file (200, not 206): it changed \
                                 upstream; restarting from 0 (had {offset} bytes)"
                            ));
                            part.restart()?;
                        }
                        self.state.file_mut(&id).etag = strong(etag);
                        if offset > 0 {
                            part.checkpoint(self)?;
                        }
                    }
                    416 => return Ok(()), // the part is complete; sha256 decides
                    401 | 403 | 404 | 410 => {
                        return Err(Stop::Fatal(FetchError::Permanent(refused(status, &self.job.url))));
                    }
                    s => return Err(Stop::Retry(format!("HTTP {s}"))),
                },
                Msg::Data(buf) => part.write(self, &buf)?,
                Msg::End if part.done < self.job.bytes => {
                    return Err(Stop::Retry(format!(
                        "the body ended at byte {} of {}",
                        part.done, self.job.bytes
                    )));
                }
                Msg::End => return Ok(()),
                Msg::Fail(reason) => return Err(Stop::Retry(reason)),
                Msg::NoResponse(reason) => {
                    // flip only if no other download flipped it meanwhile
                    let was = IPV4_ONLY.load(Ordering::SeqCst);
                    let _ = IPV4_ONLY.compare_exchange(was, !was, Ordering::SeqCst, Ordering::SeqCst);
                    return Err(Stop::Retry(format!(
                        "{reason} (over {}); next attempt over {}",
                        family_name(was),
                        family_name(!was)
                    )));
                }
            }
        }
    }
}

/// The open `.part`, its running hash and the checkpoint/progress bookkeeping.
struct Part {
    file: File,
    hash: Sha256Stream,
    done: u64,
    ckpt_at: u64,
    progress_at: Instant,
    progress_bytes: u64,
}

impl Part {
    fn write(&mut self, cx: &mut Cx, data: &[u8]) -> Result<(), FetchError> {
        self.file.write_all(data)?;
        self.hash.update(data);
        self.done += data.len() as u64;
        if self.done - self.ckpt_at >= cx.opts.checkpoint_bytes.max(1) {
            self.checkpoint(cx)?;
        }
        self.progress(cx, false);
        Ok(())
    }

    /// fsync the part, then record its length (and the ETag) in state.json.
    fn checkpoint(&mut self, cx: &mut Cx) -> Result<(), FetchError> {
        self.file.sync_data()?;
        cx.state.file_mut(&cx.job.id).bytes_done = self.done;
        cx.state.save()?;
        self.ckpt_at = self.done;
        Ok(())
    }

    fn progress(&mut self, cx: &mut Cx, force: bool) {
        if force
            || self.progress_at.elapsed() >= PROGRESS_EVERY
            || self.done.saturating_sub(self.progress_bytes) >= PROGRESS_BYTES
        {
            (cx.on)(Event::FileProgress {
                id: cx.job.id.clone(),
                done: self.done,
                total: cx.job.bytes,
            });
            self.progress_at = Instant::now();
            self.progress_bytes = self.done;
        }
    }

    fn restart(&mut self) -> std::io::Result<()> {
        self.file.set_len(0)?;
        self.file.seek(SeekFrom::Start(0))?;
        self.hash = Sha256Stream::new();
        self.done = 0;
        self.ckpt_at = 0;
        self.progress_bytes = 0;
        Ok(())
    }
}

fn agent(opts: &FetchOptions, ipv4_only: bool) -> ureq::Agent {
    let t = Some(Duration::from_secs(opts.stall_secs.max(1)));
    ureq::Agent::config_builder()
        .max_redirects(0)
        .http_status_as_error(false)
        // gzip is a default ureq feature; byte offsets must be of the file.
        .accept_encoding("identity")
        .timeout_connect(t)
        .timeout_send_request(t)
        .timeout_recv_response(t)
        .ip_family(if ipv4_only { ureq::config::IpFamily::Ipv4Only } else { ureq::config::IpFamily::Any })
        .build()
        .new_agent()
}

/// What the request thread reports.
enum Msg {
    Head {
        status: u16,
        etag: Option<String>,
        range_start: Option<u64>,
    },
    Data(Vec<u8>),
    End,
    Fail(String),
    /// The request failed before any response (connect, TLS, reset): the
    /// next attempt tries the other IP family.
    NoResponse(String),
}

fn spawn_request(
    agent: ureq::Agent,
    url: String,
    offset: u64,
    if_range: Option<String>,
    token: Option<String>,
) -> Receiver<Msg> {
    let (tx, rx) = mpsc::sync_channel(8);
    std::thread::spawn(move || request_worker(agent, url, offset, if_range, token, tx));
    rx
}

/// Runs until the body ends or the receiver is gone (stall/cancel: the read in
/// flight returns when the socket does, then the next send fails).
fn request_worker(
    agent: ureq::Agent,
    mut url: String,
    offset: u64,
    if_range: Option<String>,
    token: Option<String>,
    tx: SyncSender<Msg>,
) {
    for _ in 0..=MAX_HOPS {
        let mut req = agent.get(&url);
        // asked per hop: a redirect off huggingface.co carries no token
        if let Some(auth) = auth_header(&url, token.as_deref()) {
            req = req.header("Authorization", auth);
        }
        if offset > 0 {
            req = req.header("Range", format!("bytes={offset}-"));
            if let Some(e) = &if_range {
                req = req.header("If-Range", e);
            }
        }
        let resp = match req.call() {
            Ok(r) => r,
            Err(e) => {
                let _ = tx.send(Msg::NoResponse(e.to_string()));
                return;
            }
        };
        let status = resp.status().as_u16();
        let header = |name: &str| {
            resp.headers()
                .get(name)
                .and_then(|v| v.to_str().ok())
                .map(str::to_string)
        };
        if matches!(status, 301 | 302 | 303 | 307 | 308) {
            match header("location") {
                Some(loc) => {
                    url = join_url(&url, &loc);
                    continue;
                }
                None => {
                    let _ = tx.send(Msg::Fail(format!("HTTP {status} without Location")));
                    return;
                }
            }
        }
        let head = Msg::Head {
            status,
            etag: header("etag"),
            range_start: header("content-range")
                .as_deref()
                .and_then(content_range_start),
        };
        if tx.send(head).is_err() || !matches!(status, 200 | 206) {
            return;
        }
        let mut body = resp.into_body().into_reader();
        let mut buf = vec![0u8; CHUNK];
        loop {
            match body.read(&mut buf) {
                Ok(0) => {
                    let _ = tx.send(Msg::End);
                    return;
                }
                Ok(n) => {
                    if tx.send(Msg::Data(buf[..n].to_vec())).is_err() {
                        return;
                    }
                }
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => {}
                Err(e) => {
                    let _ = tx.send(Msg::Fail(format!("the connection broke: {e}")));
                    return;
                }
            }
        }
    }
    let _ = tx.send(Msg::Fail(format!("more than {MAX_HOPS} redirects")));
}

// ------------------------------------------------- the Hugging Face token (#340)
// A gated repo (Lightricks/LTX-2.5) answers 401/403 without the user's token.
// The token is the user's own: it goes to https://huggingface.co only, never
// across a redirect to a CDN or any other host, never into an event, a log or
// the state file. The window sets it (`set_hf_token`); without that the
// places huggingface_hub 1.21 reads are asked, in its order.

static HF_TOKEN: std::sync::Mutex<Option<String>> = std::sync::Mutex::new(None);

/// The token the user typed into the window; `None` or blank clears it.
pub fn set_hf_token(token: Option<String>) {
    *HF_TOKEN.lock().unwrap_or_else(|e| e.into_inner()) =
        token.map(|t| t.trim().to_string()).filter(|t| !t.is_empty());
}

/// The window's token, else the environment's or the Hugging Face CLI's.
pub fn hf_token() -> Option<String> {
    if let Some(t) = HF_TOKEN.lock().unwrap_or_else(|e| e.into_inner()).clone() {
        return Some(t);
    }
    let home = std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" }).map(PathBuf::from);
    find_hf_token(&|k: &str| std::env::var(k).ok(), home.as_deref())
}

/// huggingface_hub's order: HF_TOKEN, HUGGING_FACE_HUB_TOKEN, then the file at
/// HF_TOKEN_PATH, else `$HF_HOME/token`, else
/// `${XDG_CACHE_HOME:-~/.cache}/huggingface/token` (constants.py, _auth.py).
pub fn find_hf_token(env: &dyn Fn(&str) -> Option<String>, home: Option<&Path>) -> Option<String> {
    let clean = |v: String| Some(v.trim().to_string()).filter(|t| !t.is_empty());
    if let Some(t) = env("HF_TOKEN").and_then(clean).or_else(|| env("HUGGING_FACE_HUB_TOKEN").and_then(clean)) {
        return Some(t);
    }
    let file = match (env("HF_TOKEN_PATH"), env("HF_HOME")) {
        (Some(p), _) => PathBuf::from(p),
        (None, Some(h)) => PathBuf::from(h).join("token"),
        (None, None) => {
            let cache = env("XDG_CACHE_HOME").map(PathBuf::from).or_else(|| home.map(|h| h.join(".cache")))?;
            cache.join("huggingface").join("token")
        }
    };
    std::fs::read_to_string(file).ok().and_then(clean)
}

/// `Authorization` for this URL: only https://huggingface.co/..., with a token.
fn auth_header(url: &str, token: Option<&str>) -> Option<String> {
    if !url.starts_with("https://huggingface.co/") {
        return None;
    }
    token.map(|t| format!("Bearer {t}"))
}

/// #365: the sentence for an upload-pending file asked for over the network.
pub fn not_published(id: &str) -> String {
    format!("{id} is not published yet: install this point from a local folder (--source).")
}

/// The sentence for a refused request. A Hugging Face 401/403 is the gate.
fn refused(status: u16, url: &str) -> String {
    if matches!(status, 401 | 403)
        && let Some(rest) = url.strip_prefix("https://huggingface.co/")
    {
        let repo: Vec<&str> = rest.splitn(3, '/').take(2).collect();
        let page = format!("https://huggingface.co/{}", repo.join("/"));
        return format!(
            "HTTP {status} from Hugging Face: {page} is gated. Sign in there, accept its licence, \
             then give CrowSetup a read access token (the token field, or HF_TOKEN)"
        );
    }
    format!("HTTP {status} for {url}")
}

/// `bytes 100-999/1000` -> 100.
fn content_range_start(v: &str) -> Option<u64> {
    v.trim()
        .strip_prefix("bytes ")?
        .split_once('-')?
        .0
        .trim()
        .parse()
        .ok()
}

/// Resolve a `Location` against the URL that answered with it.
fn join_url(base: &str, loc: &str) -> String {
    if loc.starts_with("http://") || loc.starts_with("https://") {
        return loc.to_string();
    }
    let (scheme, rest) = base.split_once("://").unwrap_or(("https", base));
    if let Some(l) = loc.strip_prefix("//") {
        return format!("{scheme}://{l}");
    }
    let auth_end = rest.find(['/', '?', '#']).unwrap_or(rest.len());
    let origin = format!("{scheme}://{}", &rest[..auth_end]);
    if loc.starts_with('/') {
        return format!("{origin}{loc}");
    }
    let path = rest[auth_end..].split(['?', '#']).next().unwrap_or("");
    let dir = &path[..path.rfind('/').map_or(0, |i| i + 1)];
    let dir = if dir.is_empty() { "/" } else { dir };
    format!("{origin}{dir}{loc}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn locations_resolve_like_a_browser() {
        let b = "https://huggingface.co/r/resolve/abc/m.gguf?x=1";
        assert_eq!(
            join_url(b, "https://cdn.example/s?sig=1"),
            "https://cdn.example/s?sig=1"
        );
        assert_eq!(join_url(b, "//cdn.example/s"), "https://cdn.example/s");
        assert_eq!(join_url(b, "/api/x"), "https://huggingface.co/api/x");
        assert_eq!(
            join_url(b, "n.gguf"),
            "https://huggingface.co/r/resolve/abc/n.gguf"
        );
        assert_eq!(join_url("http://h:1", "a"), "http://h:1/a");
    }

    #[test]
    fn the_token_goes_to_hugging_face_over_https_only() {
        let t = Some("hf_x");
        let hf = "https://huggingface.co/Lightricks/LTX-2.5/resolve/abc/m.safetensors";
        assert_eq!(auth_header(hf, t).as_deref(), Some("Bearer hf_x"));
        assert_eq!(auth_header(hf, None), None);
        for other in [
            "http://huggingface.co/r/resolve/a/m",
            "https://cas-bridge.xethub.hf.co/xet/abc?sig=1",
            "https://cdn-lfs.huggingface.co/r/abc",
            "https://huggingface.co.evil.example/r",
            "https://github.com/x/y/releases/download/v1/a.7z",
            "https://huggingface.co@evil.example/r",
        ] {
            assert_eq!(auth_header(other, t), None, "{other}");
        }
    }

    #[test]
    fn a_refused_gate_says_what_to_do_and_never_the_token() {
        let url = "https://huggingface.co/Lightricks/LTX-2.5/resolve/abc/vae/v.safetensors";
        for status in [401, 403] {
            let m = refused(status, url);
            assert!(m.contains("https://huggingface.co/Lightricks/LTX-2.5"), "{m}");
            assert!(m.contains("token"), "{m}");
            assert!(m.contains(&format!("HTTP {status}")), "{m}");
        }
        assert_eq!(refused(404, url), format!("HTTP 404 for {url}"));
        let gh = "https://github.com/x/y/releases/download/v1/a.7z";
        assert_eq!(refused(403, gh), format!("HTTP 403 for {gh}"));
    }

    #[test]
    fn the_token_is_found_where_huggingface_hub_looks() {
        let dir = std::env::temp_dir().join(format!("crow-hf-token-{}", std::process::id()));
        let home = dir.join("home");
        std::fs::create_dir_all(home.join(".cache").join("huggingface")).unwrap();
        let env = |pairs: &'static [(&'static str, &'static str)]| {
            move |k: &str| pairs.iter().find(|(n, _)| *n == k).map(|(_, v)| v.to_string())
        };
        // nothing anywhere
        assert_eq!(find_hf_token(&env(&[]), Some(&home)), None);
        // the default file, trimmed
        std::fs::write(home.join(".cache/huggingface/token"), "hf_file\r\n").unwrap();
        assert_eq!(find_hf_token(&env(&[]), Some(&home)).as_deref(), Some("hf_file"));
        // the environment wins, HF_TOKEN before the old name
        assert_eq!(find_hf_token(&env(&[("HUGGING_FACE_HUB_TOKEN", "hf_old")]), Some(&home)).as_deref(), Some("hf_old"));
        assert_eq!(find_hf_token(&env(&[("HF_TOKEN", " hf_env "), ("HUGGING_FACE_HUB_TOKEN", "hf_old")]), Some(&home)).as_deref(), Some("hf_env"));
        // HF_HOME moves the file; HF_TOKEN_PATH names it
        let moved = dir.join("hfhome");
        std::fs::create_dir_all(&moved).unwrap();
        std::fs::write(moved.join("token"), "hf_home").unwrap();
        let hf_home: &'static str = Box::leak(moved.to_string_lossy().into_owned().into_boxed_str());
        assert_eq!(find_hf_token(&env(Box::leak(Box::new([("HF_HOME", hf_home)]))), Some(&home)).as_deref(), Some("hf_home"));
        let path: &'static str = Box::leak(moved.join("token").to_string_lossy().into_owned().into_boxed_str());
        assert_eq!(find_hf_token(&env(Box::leak(Box::new([("HF_TOKEN_PATH", path), ("HF_HOME", "/nowhere")]))), None).as_deref(), Some("hf_home"));
        // an empty value is no token
        assert_eq!(find_hf_token(&env(&[("HF_TOKEN", "  ")]), None), None);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn content_range_parses_the_start() {
        assert_eq!(content_range_start("bytes 100-999/1000"), Some(100));
        assert_eq!(content_range_start("bytes */1000"), None);
    }
}
