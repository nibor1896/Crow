//! `--headless`: the same run, events as plain text lines on stdout.

use crowsetup_core::api::{Command, Event, Selection, StepStatus};
use crowsetup_core::run::{self, Input, Outcome, RunOptions, Steps, gb};
use std::collections::HashMap;
use std::time::{Duration, Instant};

/// Exit code: 0 Done, 1 Fatal, 2 Quit / nothing to do.
pub fn main(steps: &mut dyn Steps, opts: &RunOptions, sel: Option<Selection>) -> i32 {
    let (tx, rx) = std::sync::mpsc::channel();
    match &sel {
        Some(s) => tx.send(Input::Command(Command::Start(s.clone()))).unwrap(),
        None => tx.send(Input::Command(Command::Resume)).unwrap(),
    }
    // No one can send Retry or Resume later: a failure ends the run.
    drop(tx);
    for line in package_licence_lines(crowsetup_core::STACK_JSON, if cfg!(windows) { "windows" } else { "linux" }) {
        println!("{line}");
    }
    let mut printer = Printer::default();
    let out = run::run(steps, opts, &mut |e| printer.print(&e), rx);
    match out {
        Outcome::Done => 0,
        Outcome::Fatal(_) => 1,
        Outcome::Quit => {
            if !printer.planned {
                println!("Nothing to continue. Pass --points (flash-next, 27b, image-stack, media-stack).");
            }
            2
        }
    }
}

/// The licences of third-party files inside Crow's own package on `platform`
/// (stack.json `package_licenses`), one line each: what the window shows under Crow.
fn package_licence_lines(stack: &str, platform: &str) -> Vec<String> {
    let v: serde_json::Value = serde_json::from_str(stack).unwrap_or_default();
    let mut out = Vec::new();
    for e in v["package_licenses"].as_array().into_iter().flatten() {
        let on = e["platforms"].as_array().is_some_and(|p| p.iter().any(|x| x == platform));
        let lic = &v["licenses"][e["license"].as_str().unwrap_or("")];
        if let (true, Some(name)) = (on, lic["name"].as_str()) {
            out.push(format!(
                "Licence: {}: {name} ({}). Installing means you accept them.",
                lic["covers"].as_str().unwrap_or(""),
                lic["url"].as_str().unwrap_or("")
            ));
        }
    }
    out
}

#[derive(Default)]
struct Printer {
    planned: bool,
    last: HashMap<String, (Instant, u64)>,
}

impl Printer {
    fn print(&mut self, e: &Event) {
        match e {
            Event::Preflight(r) => {
                println!(
                    "Machine: {} ({} MiB, compute {}), RAM {}, free disk {}",
                    r.gpu_name.as_deref().unwrap_or("no NVIDIA GPU"),
                    r.vram_mib.unwrap_or(0),
                    r.compute_cap.as_deref().unwrap_or("?"),
                    gb(r.ram_bytes),
                    gb(r.disk_free_bytes)
                );
                if let Some(h) = &r.hard_block {
                    println!("Blocked: {h}");
                }
                for b in &r.blocked {
                    println!("Not on this machine: {}: {}", b.point, b.reason);
                }
            }
            Event::Planned(p) => {
                self.planned = true;
                println!(
                    "Plan: {} files, {} to download, {} on disk.",
                    p.jobs.len(),
                    gb(p.download_bytes),
                    gb(p.disk_bytes)
                );
            }
            Event::Checking { id, bytes } => println!("{id}: checking what is already here ({})", gb(*bytes)),
            Event::FileStarted { id, from_byte, total } => {
                if *from_byte > 0 {
                    println!("{id}: continuing at {} of {}", gb(*from_byte), gb(*total));
                } else {
                    println!("{id}: {}", gb(*total));
                }
            }
            Event::FileProgress { id, done, total } => {
                // At most every 5 s per file, and at the end.
                let now = Instant::now();
                let due = self.last.get(id).is_none_or(|(t, _)| now.duration_since(*t) >= Duration::from_secs(5));
                if due || done == total {
                    self.last.insert(id.clone(), (now, *done));
                    let pct = if *total > 0 { *done as f64 * 100.0 / *total as f64 } else { 100.0 };
                    println!("{id}: {} of {} ({pct:.0} %)", gb(*done), gb(*total));
                }
            }
            Event::FileRetry { id, attempt, reason } => println!("{id}: reconnecting, attempt {attempt}: {reason}"),
            Event::FileVerified { id } => println!("{id}: verified"),
            Event::FileError { id, message, .. } => println!("{id}: ERROR {message}"),
            Event::Step { name, status, detail } => {
                let s = match status {
                    StepStatus::Running => "...",
                    StepStatus::Ok => "ok",
                    StepStatus::Warning => "WARNING",
                    StepStatus::Failed => "FAILED",
                };
                println!("[{name}] {s} {detail}");
            }
            Event::Done { installed, shortcut } => {
                println!("Landed. Crow is ready. Installed: {}.", installed.join(", "));
                if let Some(s) = shortcut {
                    println!("Shortcut: {}", s.display());
                }
            }
            Event::Fatal { message } => println!("FATAL: {message}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::package_licence_lines;

    #[test]
    fn the_windows_package_names_microsofts_terms_and_linux_none() {
        let win = package_licence_lines(crowsetup_core::STACK_JSON, "windows");
        assert_eq!(win.len(), 1, "{win:?}");
        assert!(win[0].starts_with("Licence: Microsoft Visual C++ runtime (bin/msvcp140.dll"), "{}", win[0]);
        assert!(win[0].contains("(https://visualstudio.microsoft.com/license-terms/vs2026-ga-visualcpp-v14-redist-runtime/)"));
        assert!(package_licence_lines(crowsetup_core::STACK_JSON, "linux").is_empty());
    }
}
