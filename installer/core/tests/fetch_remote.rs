//! T1 (#196): resumable HTTP download against a local tiny_http server.

mod fetch_support;

use crowsetup_core::api::{Event, Source};
use crowsetup_core::fetch::{FetchError, download};
use crowsetup_core::state::{FileState, StateStore};
use fetch_support::*;
use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};
use tiny_http::{Response, StatusCode};

const ETAG: &str = "\"v1-abc\"";

fn store(dir: &Path) -> StateStore {
    StateStore::load(&dir.join("setup").join("state.json")).unwrap()
}

/// A `.part` with the first `n` bytes and a state that checkpointed them.
fn seed_part(dir: &Path, st: &mut StateStore, id: &str, dest: &Path, bytes: &[u8], etag: &str) {
    std::fs::create_dir_all(dest.parent().unwrap()).unwrap();
    std::fs::write(part_of(dest), bytes).unwrap();
    st.files.insert(
        id.to_string(),
        FileState {
            etag: Some(etag.to_string()),
            bytes_done: bytes.len() as u64,
            verified: false,
        },
    );
    st.save().unwrap();
    assert!(dir.join("setup").join("state.json").exists());
}

fn run(
    job: &crowsetup_core::api::FileJob,
    st: &mut StateStore,
    o: &crowsetup_core::fetch::FetchOptions,
) -> (Result<(), FetchError>, Vec<Event>) {
    let mut ev = Vec::new();
    let cancel = AtomicBool::new(false);
    let r = download(job, st, o, &mut |e| ev.push(e), &cancel);
    (r, ev)
}

fn assert_done(job: &crowsetup_core::api::FileJob, content: &[u8], st: &StateStore, ev: &[Event]) {
    assert_eq!(std::fs::read(&job.dest).unwrap(), content, "dest bytes");
    assert!(!part_of(&job.dest).exists(), "part renamed away");
    assert!(st.files[&job.id].verified, "state marks the file verified");
    assert!(verified(ev, &job.id), "FileVerified emitted");
    // The state on disk agrees with memory.
    let disk = StateStore::load(&st.path).unwrap();
    assert!(disk.files[&job.id].verified);
}

#[test]
fn range_206_continues_an_existing_part() {
    let content = data(200_000, 1);
    let c = content.clone();
    let srv = TestServer::start(move |_, seen, rq| serve_range(seen, rq, &c, ETAG));
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("models").join("a.bin");
    let job = job("a", &format!("{}/a.bin", srv.base), &dest, &content);
    let mut st = store(tmp.path());
    seed_part(tmp.path(), &mut st, "a", &dest, &content[..70_000], ETAG);

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    r.unwrap();
    assert_eq!(checking(&ev), Some(70_000), "existing part re-hashed");
    let seen = srv.seen();
    assert_eq!(seen.len(), 1);
    assert_eq!(seen[0].range.as_deref(), Some("bytes=70000-"));
    assert_eq!(seen[0].if_range.as_deref(), Some(ETAG));
    assert!(retries(&ev).is_empty());
    assert_done(&job, &content, &st, &ev);
}

#[test]
fn a_dropped_connection_resumes_where_it_broke() {
    let content = data(150_000, 2);
    let c = content.clone();
    let srv = TestServer::start(move |n, seen, rq| {
        if n == 0 {
            serve_broken(rq, 200, ETAG, "", &c[..50_000], Duration::from_millis(200));
        } else {
            serve_range(seen, rq, &c, ETAG);
        }
    });
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("b.bin");
    let job = job("b", &format!("{}/b.bin", srv.base), &dest, &content);
    let mut st = store(tmp.path());

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    r.unwrap();
    let seen = srv.seen();
    assert_eq!(seen.len(), 2, "one retry");
    assert_eq!(seen[0].range, None);
    assert_eq!(
        seen[1].range.as_deref(),
        Some("bytes=50000-"),
        "resumed, not restarted"
    );
    assert_eq!(
        seen[1].if_range.as_deref(),
        Some(ETAG),
        "strong ETag sent back"
    );
    assert_eq!(retries(&ev).len(), 1);
    assert_done(&job, &content, &st, &ev);
}

#[test]
fn a_stall_drops_the_connection_and_retries() {
    let content = data(120_000, 3);
    let c = content.clone();
    let srv = TestServer::start(move |n, seen, rq| {
        if n == 0 {
            // 30 kB, then silence for 6 s with the socket open.
            serve_broken(rq, 200, ETAG, "", &c[..30_000], Duration::from_secs(6));
        } else {
            serve_range(seen, rq, &c, ETAG);
        }
    });
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("c.bin");
    let job = job("c", &format!("{}/c.bin", srv.base), &dest, &content);
    let mut st = store(tmp.path());
    let mut o = opts(Source::Remote);
    o.stall_secs = 1;

    let t0 = Instant::now();
    let (r, ev) = run(&job, &mut st, &o);
    r.unwrap();
    assert!(
        t0.elapsed() < Duration::from_secs(5),
        "did not wait for the server: {:?}",
        t0.elapsed()
    );
    let reasons = retries(&ev);
    assert_eq!(reasons.len(), 1, "{reasons:?}");
    assert!(reasons[0].contains("no bytes"), "{reasons:?}");
    assert_eq!(srv.seen()[1].range.as_deref(), Some("bytes=30000-"));
    assert_done(&job, &content, &st, &ev);
}

#[test]
fn a_changed_etag_gets_200_and_restarts_from_zero() {
    let old = data(100_000, 4);
    let new = data(100_000, 5);
    let n2 = new.clone();
    let srv = TestServer::start(move |_, seen, rq| serve_range(seen, rq, &n2, "\"v2\""));
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("d.bin");
    let job = job("d", &format!("{}/d.bin", srv.base), &dest, &new);
    let mut st = store(tmp.path());
    seed_part(tmp.path(), &mut st, "d", &dest, &old[..40_000], "\"v1\"");

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    r.unwrap();
    let seen = srv.seen();
    assert_eq!(seen.len(), 1, "the 200 body is used, no second request");
    assert_eq!(seen[0].if_range.as_deref(), Some("\"v1\""));
    let reasons = retries(&ev);
    assert_eq!(reasons.len(), 1, "{reasons:?}");
    assert!(reasons[0].contains("200"), "{reasons:?}");
    assert_eq!(
        st.files["d"].etag.as_deref(),
        Some("\"v2\""),
        "new ETag stored"
    );
    assert_done(&job, &new, &st, &ev);
}

#[test]
fn a_complete_part_gets_416_and_is_only_verified() {
    let content = data(64_000, 6);
    let c = content.clone();
    let srv = TestServer::start(move |_, seen, rq| serve_range(seen, rq, &c, ETAG));
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("e.bin");
    let job = job("e", &format!("{}/e.bin", srv.base), &dest, &content);
    let mut st = store(tmp.path());
    seed_part(tmp.path(), &mut st, "e", &dest, &content, ETAG);

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    r.unwrap();
    let seen = srv.seen();
    assert_eq!(seen.len(), 1);
    assert_eq!(seen[0].range.as_deref(), Some("bytes=64000-"));
    assert!(retries(&ev).is_empty());
    assert_done(&job, &content, &st, &ev);
}

#[test]
fn not_found_is_permanent_and_does_not_loop() {
    let srv = TestServer::start(|_, _, rq| {
        let _ = rq.respond(Response::from_string("no").with_status_code(StatusCode(404)));
    });
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("f.bin");
    let content = data(1000, 7);
    let job = job("f", &format!("{}/f.bin", srv.base), &dest, &content);
    let mut st = store(tmp.path());

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    match r {
        Err(FetchError::Permanent(m)) => assert!(m.contains("404"), "{m}"),
        other => panic!("expected Permanent, got {other:?}"),
    }
    thread::sleep(Duration::from_millis(300));
    assert_eq!(srv.seen().len(), 1, "exactly one request");
    assert!(retries(&ev).is_empty());
    assert!(!dest.exists());
}

#[test]
fn a_503_is_retried_then_succeeds() {
    let content = data(30_000, 8);
    let c = content.clone();
    let srv = TestServer::start(move |n, seen, rq| {
        if n == 0 {
            let _ = rq.respond(Response::from_string("busy").with_status_code(StatusCode(503)));
        } else {
            serve_range(seen, rq, &c, ETAG);
        }
    });
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("g.bin");
    let job = job("g", &format!("{}/g.bin", srv.base), &dest, &content);
    let mut st = store(tmp.path());

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    r.unwrap();
    let reasons = retries(&ev);
    assert_eq!(reasons.len(), 1, "{reasons:?}");
    assert!(reasons[0].contains("503"), "{reasons:?}");
    assert_eq!(srv.seen().len(), 2);
    assert_done(&job, &content, &st, &ev);
}

#[test]
fn a_sha_mismatch_refetches_once_then_fails() {
    let good = data(20_000, 9);
    let bad = data(20_000, 10);
    let b = bad.clone();
    let srv = TestServer::start(move |_, seen, rq| serve_range(seen, rq, &b, ETAG));
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("h.bin");
    let job = job("h", &format!("{}/h.bin", srv.base), &dest, &good);
    let mut st = store(tmp.path());

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    match r {
        Err(FetchError::Mismatch { expected, got, .. }) => {
            assert_eq!(expected, sha_hex(&good));
            assert_eq!(got, sha_hex(&bad));
        }
        other => panic!("expected Mismatch, got {other:?}"),
    }
    let seen = srv.seen();
    assert_eq!(seen.len(), 2, "one refetch, no loop");
    assert!(seen.iter().all(|s| s.range.is_none()), "both from 0");
    assert!(
        !dest.exists() && !part_of(&dest).exists(),
        "bad bytes deleted"
    );
    assert!(!st.files.get("h").is_some_and(|f| f.verified));
    assert!(!verified(&ev, "h"));
}

#[test]
fn a_sha_mismatch_then_good_bytes_succeeds_on_the_refetch() {
    let good = data(20_000, 11);
    let bad = data(20_000, 12);
    let (g, b) = (good.clone(), bad.clone());
    let srv = TestServer::start(move |n, seen, rq| {
        serve_range(seen, rq, if n == 0 { &b } else { &g }, ETAG)
    });
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("i.bin");
    let job = job("i", &format!("{}/i.bin", srv.base), &dest, &good);
    let mut st = store(tmp.path());

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    r.unwrap();
    assert_eq!(srv.seen().len(), 2);
    assert!(retries(&ev).iter().any(|r| r.contains("sha256")));
    assert_done(&job, &good, &st, &ev);
}

#[test]
fn cancel_mid_file_then_a_second_call_resumes_from_the_checkpoint() {
    let content = data(300_000, 13);
    let c = content.clone();
    let srv = TestServer::start(move |n, seen, rq| {
        if n == 0 {
            let slow = Slow {
                data: c.clone(),
                pos: 0,
                step: 2048,
                delay: Duration::from_millis(10),
            };
            let resp = Response::new(
                StatusCode(200),
                vec![hdr("ETag", ETAG)],
                slow,
                Some(c.len()),
                None,
            );
            let _ = rq.respond(resp);
        } else {
            serve_range(seen, rq, &c, ETAG);
        }
    });
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("j.bin");
    let job = job("j", &format!("{}/j.bin", srv.base), &dest, &content);
    let mut st = store(tmp.path());

    let cancel = Arc::new(AtomicBool::new(false));
    let c2 = cancel.clone();
    let setter = thread::spawn(move || {
        thread::sleep(Duration::from_millis(400));
        c2.store(true, Ordering::SeqCst);
        Instant::now()
    });
    let mut ev = Vec::new();
    let r = download(
        &job,
        &mut st,
        &opts(Source::Remote),
        &mut |e| ev.push(e),
        &cancel,
    );
    let returned = Instant::now();
    let set_at = setter.join().unwrap();
    assert!(matches!(r, Err(FetchError::Cancelled)), "{r:?}");
    assert!(
        returned.duration_since(set_at) < Duration::from_secs(1),
        "cancel is prompt"
    );

    // State on disk and the part agree, and both hold real progress.
    let disk = StateStore::load(&st.path).unwrap();
    let fs = &disk.files["j"];
    let part_len = std::fs::metadata(part_of(&dest)).unwrap().len();
    assert!(
        fs.bytes_done > 0 && fs.bytes_done < content.len() as u64,
        "{fs:?}"
    );
    assert_eq!(fs.bytes_done, part_len);
    assert_eq!(fs.etag.as_deref(), Some(ETAG));
    assert_eq!(
        std::fs::read(part_of(&dest)).unwrap(),
        &content[..part_len as usize]
    );
    assert!(!dest.exists());

    // A fresh run (new process: state loaded from disk) resumes by Range.
    let mut st2 = StateStore::load(&st.path).unwrap();
    let (r2, ev2) = run(&job, &mut st2, &opts(Source::Remote));
    r2.unwrap();
    assert_eq!(checking(&ev2), Some(part_len));
    let seen = srv.seen();
    assert_eq!(seen.len(), 2);
    assert_eq!(seen[1].range, Some(format!("bytes={part_len}-")));
    assert_eq!(seen[1].if_range.as_deref(), Some(ETAG));
    assert_done(&job, &content, &st2, &ev2);
}

#[test]
fn a_302_to_another_host_keeps_range_and_is_resolved_every_attempt() {
    let content = data(180_000, 14);
    let c = content.clone();
    let cdn = TestServer::start(move |n, seen, rq| {
        if n == 0 {
            // First CDN attempt breaks after 20 kB more.
            let from = range_start(seen).unwrap_or(0) as usize;
            let cr = format!(
                "Content-Range: bytes {from}-{}/{}\r\n",
                c.len() - 1,
                c.len()
            );
            serve_broken(
                rq,
                206,
                ETAG,
                &cr,
                &c[from..from + 20_000],
                Duration::from_millis(200),
            );
        } else {
            serve_range(seen, rq, &c, ETAG);
        }
    });
    let cdn_base = cdn.base.clone();
    let origin = TestServer::start(move |n, _, rq| {
        let loc = format!("{cdn_base}/signed/k.bin?sig={n}");
        let _ = rq.respond(
            Response::empty(StatusCode(302))
                .with_header(hdr("Location", &loc))
                .with_header(hdr("X-Linked-ETag", "\"lfs-sha\"")),
        );
    });
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("k.bin");
    let job = job(
        "k",
        &format!("{}/resolve/main/k.bin", origin.base),
        &dest,
        &content,
    );
    let mut st = store(tmp.path());
    seed_part(tmp.path(), &mut st, "k", &dest, &content[..60_000], ETAG);

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    r.unwrap();
    let o = origin.seen();
    let s = cdn.seen();
    assert_eq!(o.len(), 2, "the redirect is fetched again on the retry");
    assert_eq!(s.len(), 2);
    assert_eq!(s[0].url, "/signed/k.bin?sig=0");
    assert_eq!(s[1].url, "/signed/k.bin?sig=1", "fresh signed URL");
    assert_eq!(
        s[0].range.as_deref(),
        Some("bytes=60000-"),
        "Range reaches the final host"
    );
    assert_eq!(s[0].if_range.as_deref(), Some(ETAG));
    assert_eq!(s[1].range.as_deref(), Some("bytes=80000-"));
    assert_eq!(retries(&ev).len(), 1);
    assert_done(&job, &content, &st, &ev);
}

#[test]
fn a_weak_etag_is_never_sent_as_if_range() {
    let content = data(90_000, 15);
    let c = content.clone();
    let srv = TestServer::start(move |n, seen, rq| {
        if n == 0 {
            serve_broken(
                rq,
                200,
                "W/\"weak\"",
                "",
                &c[..10_000],
                Duration::from_millis(200),
            );
        } else {
            serve_range(seen, rq, &c, "W/\"weak\"");
        }
    });
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("w.bin");
    let job = job("w", &format!("{}/w.bin", srv.base), &dest, &content);
    let mut st = store(tmp.path());

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    r.unwrap();
    let seen = srv.seen();
    assert_eq!(seen[1].range.as_deref(), Some("bytes=10000-"));
    assert_eq!(seen[1].if_range, None);
    assert_eq!(st.files["w"].etag, None);
    assert_done(&job, &content, &st, &ev);
}

#[test]
fn an_already_verified_file_returns_without_network() {
    let content = data(5000, 16);
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("v.bin");
    std::fs::write(&dest, &content).unwrap();
    let srv = TestServer::start(|_, _, rq| {
        let _ = rq.respond(Response::empty(StatusCode(404)));
    });
    let job = job("v", &format!("{}/v.bin", srv.base), &dest, &content);
    let mut st = store(tmp.path());
    st.files.insert(
        "v".into(),
        FileState {
            etag: None,
            bytes_done: 5000,
            verified: true,
        },
    );

    let (r, ev) = run(&job, &mut st, &opts(Source::Remote));
    r.unwrap();
    assert!(verified(&ev, "v"));
    assert!(!ev.iter().any(|e| matches!(e, Event::FileStarted { .. })));
    assert!(srv.seen().is_empty(), "no request");
}

#[test]
fn an_upload_pending_file_is_refused_by_name_without_a_request() {
    // #365: plan.rs leaves an upload-pending file's url empty; a download names it
    // and points at --source instead of asking a server for "".
    let content = data(1_000, 7);
    let tmp = tempfile::tempdir().unwrap();
    let dest = tmp.path().join("models").join("glm.cnq");
    let job = job("glm-cnq", "", &dest, &content);
    let mut st = store(tmp.path());
    let (r, _) = run(&job, &mut st, &opts(Source::Remote));
    let err = r.unwrap_err().to_string();
    assert!(err.contains("glm-cnq is not published yet") && err.contains("--source"), "{err}");
    assert!(!dest.exists());
}
