//! The window: a frameless tao window holding a wry WebView (WebView2 on
//! Windows) with the embedded page `installer/ui/index.html`.
//!
//! BRIDGE. UI -> exe: `window.ipc.postMessage(JSON)`, either a core
//! [`Command`] (`{"type":"start",...}`, `pause`, `resume`, `retry`,
//! `open_boot_menu`, `quit`) or a window message (`ready`, `log`, `minimize`,
//! `drag`, `close`, `pick_folder`, `hf_token` -- the user's token for a gated
//! Hugging Face repo, never logged). Exe -> UI: `evaluate_script` calling
//! `window.crow.init(..)`, `window.crow.event(<Event JSON>)` and
//! `window.crow.picked(..)`. Scripts before the page's `ready` are queued.
//!
//! TITLE BAR. The page marks it `app-region: drag` (WebView2 123+ moves the
//! window natively) and also posts `drag` on mousedown, which calls
//! `Window::drag_window` (wry 0.57 examples/custom_titlebar.rs does both).
//!
//! The run happens on a worker thread; its events reach the event loop
//! through an [`EventLoopProxy`] and the page through `evaluate_script`.

use crate::Setup;
use crowsetup_core::api::{Command, Event as CoreEvent};
use crowsetup_core::run::{self, Input};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::{Path, PathBuf};
use std::sync::mpsc::Sender;
use std::time::Duration;
use tao::dpi::LogicalSize;
use tao::event::{Event, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoopBuilder, EventLoopProxy};
use tao::window::{Icon, Window, WindowBuilder};
use wry::{WebContext, WebView, WebViewBuilder, http::Request};

const PAGE: &str = include_str!("../../ui/index.html");
const LOGO: &str = include_str!("../../../cli/mark-on-dark.svg");
const ICO: &[u8] = include_bytes!("../../../cli/crow.ico");
const OPERATING_POINT: &str = include_str!("../../../manifests/operating-point.json");
/// How the page references the logo when it is opened from the repo in a browser.
const LOGO_REF: &str = "../../cli/mark-on-dark.svg";
const BG: (u8, u8, u8, u8) = (0x18, 0x18, 0x18, 0xff);
const WIDTH: f64 = 900.0;
const HEIGHT: f64 = 640.0;

/// `data:` URI for an SVG (percent-encoded; no base64 needed).
fn svg_data_uri(svg: &str) -> String {
    let mut out = String::from("data:image/svg+xml,");
    for b in svg.trim().bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' | b'/' | b':' | b'=' | b',' | b' ' => {
                out.push(if b == b' ' { ' ' } else { b as char })
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out.replace(' ', "%20")
}

/// What the log says about one message from the page: nothing for the page's
/// own `log`, the message for the rest -- except a token, which is named, not shown.
fn ipc_log_line(v: &serde_json::Value, body: &str) -> Option<String> {
    match v["type"].as_str() {
        Some("log") => None,
        Some("hf_token") => Some("ipc <- hf_token (hidden)".into()),
        _ => Some(format!("ipc <- {body}")),
    }
}

/// The page as the WebView gets it: the logo inlined.
pub fn page() -> String {
    PAGE.replace(LOGO_REF, &svg_data_uri(LOGO))
}

/// `--selftest`: the embedded page is whole.
pub fn check_page() -> Result<(), String> {
    let p = page();
    if p.contains(LOGO_REF) || !p.contains("data:image/svg+xml,") {
        return Err("the logo is not inlined".into());
    }
    for needle in ["window.crow", "ipc.postMessage", "Flying to the nest", "Landed. Crow is ready."] {
        if !p.contains(needle) {
            return Err(format!("the page lacks {needle:?}"));
        }
    }
    // WebView2 refuses NavigateToString above 2 MB.
    if p.len() >= 2 * 1024 * 1024 {
        return Err(format!("the page is {} bytes", p.len()));
    }
    serde_json::from_str::<serde_json::Value>(OPERATING_POINT).map_err(|e| format!("operating-point.json: {e}"))?;
    Ok(())
}

/// The window icon from cli/crow.ico (its entries are PNGs).
fn icon(size: u8) -> Option<Icon> {
    let n = u16::from_le_bytes([*ICO.get(4)?, *ICO.get(5)?]) as usize;
    let entry = (0..n).map(|i| &ICO[6 + 16 * i..22 + 16 * i]).find(|e| e[0] == size)?;
    let len = u32::from_le_bytes(entry[8..12].try_into().ok()?) as usize;
    let off = u32::from_le_bytes(entry[12..16].try_into().ok()?) as usize;
    let mut dec = png::Decoder::new(std::io::Cursor::new(ICO.get(off..off + len)?));
    dec.set_transformations(png::Transformations::EXPAND);
    let mut reader = dec.read_info().ok()?;
    let mut buf = vec![0; reader.output_buffer_size()?];
    let info = reader.next_frame(&mut buf).ok()?;
    if info.color_type != png::ColorType::Rgba || info.bit_depth != png::BitDepth::Eight {
        return None;
    }
    buf.truncate(info.buffer_size());
    Icon::from_rgba(buf, info.width, info.height).ok()
}

/// A plain error dialog for when the window cannot start (bad arguments).
pub fn message_box(text: &str) {
    rfd::MessageDialog::new()
        .set_level(rfd::MessageLevel::Error)
        .set_title("Crow Setup")
        .set_description(text)
        .set_buttons(rfd::MessageButtons::Ok)
        .show();
}

/// The WebView2 user data folder: `<launch root>\setup\webview2`, where the
/// launch root is `--install-root` or %LOCALAPPDATA%\Crow. WebView2's default
/// is `<exe>.WebView2\` beside the exe, which put a folder into Downloads.
pub fn webview_data_dir(launch_root: &Path) -> PathBuf {
    launch_root.join("setup").join("webview2")
}

/// What the page needs before the first event.
fn init_json(s: &Setup) -> String {
    let stack: serde_json::Value = serde_json::from_str(crowsetup_core::STACK_JSON).unwrap_or_default();
    let op: serde_json::Value = serde_json::from_str(OPERATING_POINT).unwrap_or_default();
    let root = &s.opts.launch_root;
    serde_json::json!({
        "stack": stack,
        "op": op,
        "packages": { "crow": s.packages.crow.bytes, "engine": s.packages.engine.bytes },
        "root": root,
        "root_label": crate::folders::label(root),
        "desktop": s.desktop,
        "desktop_label": s.desktop.as_deref().map(crate::folders::label),
        "launcher_label": crate::folders::LAUNCHER_LABEL,
        // which `package_licenses` of stack.json apply to the package this exe installs
        "platform": if cfg!(windows) { "windows" } else { "linux" },
    })
    .to_string()
}

/// The `url` of licence `id` in `stack` (stack.json), the only addresses the page may
/// open: https, and nothing a command line could split.
fn licence_url(stack: &str, id: &str) -> Option<String> {
    let v: serde_json::Value = serde_json::from_str(stack).ok()?;
    let url = v["licenses"][id]["url"].as_str()?;
    let plain = !url.chars().any(|c| c.is_whitespace() || c == '"' || c.is_control());
    (url.starts_with("https://") && plain).then(|| url.to_string())
}

/// Open `url` in the user's browser, so a licence can be read before Install accepts it.
fn open_in_browser(url: &str) {
    #[cfg(windows)]
    let child = std::process::Command::new("rundll32.exe").args(["url.dll,FileProtocolHandler", url]).spawn();
    #[cfg(not(windows))]
    let child = std::process::Command::new("xdg-open").arg(url).spawn();
    match child {
        Ok(mut c) => {
            std::thread::spawn(move || {
                let _ = c.wait();
            });
        }
        Err(e) => eprintln!("crowsetup: cannot open {url}: {e}"),
    }
}

enum UserEvent {
    Js(String),
    Ipc(String),
    WorkerDone,
    ForceExit,
    /// The boot menu opened; Setup's job is done, so its window goes.
    CloseAfterBootMenu,
}

/// The owner's live test 2026-10-01: after "Open boot menu" opened the
/// operating-point window, Setup's "Landed" window stayed. Once the boot menu
/// opened, Setup closes the way "X" does (the run saves and ends); a failed
/// open keeps the window and its error row.
pub(crate) fn closes_after(e: &CoreEvent) -> bool {
    matches!(e, CoreEvent::Step { name, status: crowsetup_core::api::StepStatus::Ok, .. } if name == "boot_menu")
}

fn js_event(e: &CoreEvent) -> String {
    format!("window.crow&&window.crow.event({})", serde_json::to_string(e).unwrap_or_else(|_| "null".into()))
}

fn spawn_worker(s: &Setup, proxy: EventLoopProxy<UserEvent>) -> Sender<Input> {
    let (tx, rx) = std::sync::mpsc::channel();
    let (source, packages, opts) = (s.source.clone(), s.packages.clone(), s.opts.clone());
    let package_source = s.package_source.clone();
    std::thread::spawn(move || {
        let p2 = proxy.clone();
        let res = catch_unwind(AssertUnwindSafe(|| {
            let mut steps = run::RealSteps::new(source, packages, crate::bundle::PYTHON_ZIP, crate::bundle::GET_PIP)
                .with_package_source(package_source);
            run::run(&mut steps, &opts, &mut |e| {
                let _ = p2.send_event(UserEvent::Js(js_event(&e)));
                if closes_after(&e) {
                    let _ = p2.send_event(UserEvent::CloseAfterBootMenu);
                }
            }, rx)
        }));
        if let Err(p) = res {
            let why = p
                .downcast_ref::<&str>()
                .map(|s| s.to_string())
                .or_else(|| p.downcast_ref::<String>().cloned())
                .unwrap_or_else(|| "unknown".into());
            eprintln!("crowsetup: the run panicked: {why}");
            let e = CoreEvent::Fatal { message: format!("Setup stopped unexpectedly: {why}") };
            let _ = proxy.send_event(UserEvent::Js(js_event(&e)));
        }
        let _ = proxy.send_event(UserEvent::WorkerDone);
    });
    tx
}

/// The install folder for a picked folder: `<picked>\Crow` unless it already
/// is a folder named Crow (picking `D:\` must not spread files over D:\).
fn install_dir(picked: &Path) -> PathBuf {
    if picked.file_name().is_some_and(|n| n.eq_ignore_ascii_case("crow")) {
        picked.to_path_buf()
    } else {
        // Linux (#342): lower case, like `$XDG_DATA_HOME/crow`
        picked.join(if cfg!(windows) { "Crow" } else { "crow" })
    }
}

struct App {
    window: Window,
    webview: Option<WebView>,
    proxy: EventLoopProxy<UserEvent>,
    tx: Option<Sender<Input>>,
    init: String,
    ready: bool,
    queued: Vec<String>,
    closing: bool,
    worker_done: bool,
}

impl App {
    fn eval(&mut self, js: String) {
        if !self.ready {
            self.queued.push(js);
        } else if let Some(w) = &self.webview
            && let Err(e) = w.evaluate_script(&js)
        {
            eprintln!("crowsetup: evaluate_script: {e}");
        }
    }

    fn send(&self, i: Input) {
        if let Some(tx) = &self.tx {
            let _ = tx.send(i);
        }
    }

    /// Close: tell the run to stop (it saves the state), wait for it a moment.
    fn close(&mut self, cf: &mut ControlFlow) {
        if self.closing {
            return;
        }
        self.closing = true;
        self.send(Input::Command(Command::Quit));
        self.tx = None;
        self.window.set_visible(false);
        if self.worker_done {
            self.exit(cf);
            return;
        }
        let p = self.proxy.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs(5));
            let _ = p.send_event(UserEvent::ForceExit);
        });
    }

    fn exit(&mut self, cf: &mut ControlFlow) {
        self.webview.take();
        *cf = ControlFlow::Exit;
    }

    fn pick_folder(&mut self, purpose: &str, current: Option<&str>) {
        let mut d = rfd::FileDialog::new()
            .set_title(if purpose == "install" { "Install Crow into" } else { "Put the boot menu shortcut into" })
            .set_parent(&self.window);
        if let Some(c) = current.map(Path::new).and_then(crowsetup_core::preflight::nearest_existing) {
            d = d.set_directory(c);
        }
        let Some(picked) = d.pick_folder() else { return };
        let (path, free) = if purpose == "install" {
            let dir = install_dir(&picked);
            let free = crowsetup_core::preflight::probe(&dir).disk_free_bytes;
            (dir, Some(free))
        } else {
            self.send(Input::ShortcutDir(picked.clone()));
            (picked, None)
        };
        let msg = serde_json::json!({
            "for": purpose, "path": path, "label": crate::folders::label(&path), "disk_free": free,
        });
        self.eval(format!("window.crow.picked({msg})"));
    }

    fn ipc(&mut self, body: String, cf: &mut ControlFlow) {
        let v: serde_json::Value = match serde_json::from_str(&body) {
            Ok(v) => v,
            Err(e) => return eprintln!("crowsetup: bad ipc message: {e}"),
        };
        if let Some(line) = ipc_log_line(&v, &body) {
            eprintln!("{line}");
        }
        match v["type"].as_str().unwrap_or("") {
            "ready" => {
                self.ready = true;
                let init = format!("window.crow.init({})", self.init);
                self.eval(init);
                for js in std::mem::take(&mut self.queued) {
                    self.eval(js);
                }
            }
            "log" => eprintln!("ui: {}", v["msg"].as_str().unwrap_or("")),
            "minimize" => self.window.set_minimized(true),
            "drag" => {
                let _ = self.window.drag_window();
            }
            "close" => self.close(cf),
            // #340: the user's Hugging Face token for a gated repo; held by
            // the fetcher for this run only, never logged or written.
            "hf_token" => crowsetup_core::fetch::set_hf_token(v["token"].as_str().map(str::to_string)),
            "open_licence" => match licence_url(crowsetup_core::STACK_JSON, v["id"].as_str().unwrap_or("")) {
                Some(url) => open_in_browser(&url),
                None => eprintln!("crowsetup: no licence url for {}", v["id"]),
            },
            "pick_folder" => {
                let purpose = v["for"].as_str().unwrap_or("install").to_string();
                self.pick_folder(&purpose, v["current"].as_str());
            }
            _ => match serde_json::from_value::<Command>(v) {
                Ok(Command::Quit) => self.close(cf),
                Ok(c) => self.send(Input::Command(c)),
                Err(e) => eprintln!("crowsetup: unknown ipc message: {e}"),
            },
        }
    }
}

pub fn main(s: Setup) -> ! {
    // WebKitGTK's DMA-BUF renderer turns on Wayland explicit sync and commits
    // a buffer without an acquire point; Hyprland answers "Missing acquire
    // timeline", Gdk "Error 71 (Protocol error)", and the window dies at its
    // first frame (measured 2026-10-02, NVIDIA 610.57.04). The same fix as the
    // Crow window (`cli/crow_gui.py` prepare_environment), which keeps the
    // accelerated path. A value the user set wins.
    #[cfg(target_os = "linux")]
    if std::env::var_os("__NV_DISABLE_EXPLICIT_SYNC").is_none_or(|v| v.is_empty()) {
        // SAFETY: still single-threaded; no worker, GTK or WebKit thread yet.
        unsafe { std::env::set_var("__NV_DISABLE_EXPLICIT_SYNC", "1") };
    }
    let event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    let proxy = event_loop.create_proxy();

    let size = LogicalSize::new(WIDTH, HEIGHT);
    let builder = WindowBuilder::new()
        .with_title("Crow Setup")
        .with_decorations(false)
        .with_inner_size(size)
        .with_min_inner_size(size)
        .with_resizable(false)
        .with_maximizable(false)
        .with_window_icon(icon(64))
        .with_background_color(BG);
    #[cfg(windows)]
    let builder = {
        use tao::platform::windows::WindowBuilderExtWindows;
        builder.with_undecorated_shadow(true).with_taskbar_icon(icon(128))
    };
    let window = match builder.build(&event_loop) {
        Ok(w) => w,
        Err(e) => {
            message_box(&format!("The window could not be created: {e}"));
            std::process::exit(1);
        }
    };

    let ipc_proxy = proxy.clone();
    // wry hands this to CreateCoreWebView2EnvironmentWithOptions as the user
    // data folder; the run never returns, so the context outlives the view.
    let mut web_context = WebContext::new(Some(webview_data_dir(&s.opts.launch_root)));
    let builder = WebViewBuilder::new_with_web_context(&mut web_context)
        .with_html(page())
        .with_background_color(BG)
        .with_devtools(cfg!(debug_assertions))
        .with_ipc_handler(move |req: Request<String>| {
            let _ = ipc_proxy.send_event(UserEvent::Ipc(req.body().clone()));
        });
    #[cfg(windows)]
    let webview = builder.build(&window);
    // `build(&window)` is X11-only on Linux: under Wayland the window never
    // maps. tao's default GTK box works on both (wry 0.57 examples/simple.rs).
    #[cfg(not(windows))]
    let webview = {
        use tao::platform::unix::WindowExtUnix;
        use wry::WebViewBuilderExtUnix;
        match window.default_vbox() {
            Some(vbox) => builder.build_gtk(vbox),
            None => builder.build(&window),
        }
    };
    let webview = match webview {
        Ok(w) => w,
        Err(e) => {
            #[cfg(windows)]
            message_box(&format!(
                "Crow Setup needs the Microsoft Edge WebView2 runtime ({e}).\nRun CrowSetup.exe --headless instead."
            ));
            #[cfg(not(windows))]
            message_box(&format!(
                "Crow Setup needs WebKitGTK 4.1 ({e}).\nRun CrowSetup-linux-x64 --headless instead."
            ));
            std::process::exit(1);
        }
    };

    let tx = spawn_worker(&s, proxy.clone());
    let mut app = App {
        window,
        webview: Some(webview),
        proxy,
        tx: Some(tx),
        init: init_json(&s),
        ready: false,
        queued: Vec::new(),
        closing: false,
        worker_done: false,
    };

    event_loop.run(move |event, _, cf| {
        *cf = ControlFlow::Wait;
        match event {
            Event::WindowEvent { event: WindowEvent::CloseRequested, .. } => app.close(cf),
            Event::UserEvent(UserEvent::Js(js)) => app.eval(js),
            Event::UserEvent(UserEvent::Ipc(body)) => app.ipc(body, cf),
            Event::UserEvent(UserEvent::WorkerDone) => {
                app.worker_done = true;
                if app.closing {
                    app.exit(cf);
                }
            }
            Event::UserEvent(UserEvent::ForceExit) => app.exit(cf),
            Event::UserEvent(UserEvent::CloseAfterBootMenu) => app.close(cf),
            _ => {}
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_a_licence_url_of_the_stack_opens() {
        let stack = crowsetup_core::STACK_JSON;
        assert_eq!(
            licence_url(stack, "msvc-v14-runtime").as_deref(),
            Some("https://visualstudio.microsoft.com/license-terms/vs2026-ga-visualcpp-v14-redist-runtime/")
        );
        assert_eq!(licence_url(stack, "no-such-licence"), None);
        assert_eq!(licence_url(stack, ""), None);
        let fake = r#"{"licenses":{"a":{"url":"file:///C:/Windows/notepad.exe"},
            "b":{"url":"https://x.example/a b"},"c":{"url":"https://x.example/\"q"}}}"#;
        assert_eq!(licence_url(fake, "a"), None);
        assert_eq!(licence_url(fake, "b"), None);
        assert_eq!(licence_url(fake, "c"), None);
    }

    #[test]
    fn a_token_message_never_reaches_the_log() {
        let body = r#"{"type":"hf_token","token":"hf_secret123"}"#;
        let v: serde_json::Value = serde_json::from_str(body).unwrap();
        let line = ipc_log_line(&v, body).unwrap();
        assert!(!line.contains("hf_secret123"), "{line}");
        assert!(line.contains("hf_token"), "{line}");
        let start = r#"{"type":"start","points":["27b"]}"#;
        assert_eq!(ipc_log_line(&serde_json::from_str(start).unwrap(), start).as_deref(), Some(&*format!("ipc <- {start}")));
        assert_eq!(ipc_log_line(&serde_json::json!({"type": "log", "msg": "x"}), "{}"), None);
    }

    #[test]
    fn the_page_is_whole() {
        check_page().unwrap();
    }

    /// #196 P2-E2E fix 6: a JS error or an unhandled promise rejection reaches
    /// the exe's stderr log, from a script of its own ahead of the page's, so a
    /// syntax error in the page's script is reported too.
    #[test]
    fn errors_and_rejections_reach_the_log_before_the_main_script() {
        let p = page();
        let start = p.find("<script>").expect("a script");
        let block = &p[start..start + p[start..].find("</script>").expect("its end")];
        assert!(
            block.contains("window.onerror") && block.contains("unhandledrejection") && block.contains("ipc.postMessage"),
            "the first script does not forward errors: {}",
            &block[..block.len().min(120)]
        );
        assert!(!block.contains("window.crow"), "the forwarder must stand before the page's script");
    }

    /// #196 P2-E2E: the WebView2 profile goes under the launch root's setup
    /// folder (`--install-root` or %LOCALAPPDATA%\Crow), never beside the exe.
    #[test]
    fn the_webview_profile_lives_in_the_setup_folder() {
        let root = Path::new(r"D:\Test\Crow");
        assert_eq!(webview_data_dir(root), root.join("setup").join("webview2"));
        let default = crowsetup_core::run::default_install_root();
        assert_eq!(webview_data_dir(&default), default.join("setup").join("webview2"));
    }

    #[test]
    fn the_icon_decodes() {
        assert!(icon(64).is_some() && icon(128).is_some());
    }

    #[cfg(windows)]
    #[test]
    fn a_picked_drive_gets_a_crow_folder() {
        assert_eq!(install_dir(Path::new(r"D:\")), PathBuf::from(r"D:\Crow"));
        assert_eq!(install_dir(Path::new(r"D:\Apps\crow")), PathBuf::from(r"D:\Apps\crow"));
    }

    /// #342: a picked Linux folder gets `crow`, as `$XDG_DATA_HOME/crow`.
    #[cfg(not(windows))]
    #[test]
    fn a_picked_linux_folder_gets_a_crow_folder() {
        assert_eq!(install_dir(Path::new("/mnt/big")), PathBuf::from("/mnt/big/crow"));
        assert_eq!(install_dir(Path::new("/opt/Crow")), PathBuf::from("/opt/Crow"));
    }
}

#[cfg(test)]
mod close_after_boot_menu {
    use super::closes_after;
    use crowsetup_core::api::{Event, StepStatus};

    fn step(name: &str, status: StepStatus) -> Event {
        Event::Step { name: name.into(), status, detail: String::new() }
    }

    #[test]
    fn setup_closes_once_the_boot_menu_opened_and_not_otherwise() {
        assert!(closes_after(&step("boot_menu", StepStatus::Ok)));
        assert!(!closes_after(&step("boot_menu", StepStatus::Failed)), "a failed open keeps the error visible");
        assert!(!closes_after(&step("shortcuts", StepStatus::Ok)));
        assert!(!closes_after(&Event::Done { installed: vec![], shortcut: None }));
    }
}
