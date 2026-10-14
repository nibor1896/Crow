[← README](../../README.md) · [Docs index](../README.md)

# Browser tab (#175, #384)

The globe in the title bar adds a **Browser** tab to the [inspector](window.md) beside the chat and
selects it, opening the inspector when it is shut; switching the globe off removes the tab, and the
inspector returns to the tab before (#384). That button is the only way to close it, as the branch
icon is for the Git tab. The open state survives a restart (`browser_open` in `settings.json`).

The page is a native view over the window, so it shows only while the Browser tab is selected and
the inspector is open. On any other tab it is hidden with `pane_hide` and kept, and `pane_show`
brings it back; a page sent to it meanwhile loads when the tab shows again. A link that opens in
the browser (see [Links](#links)) adds a tab here and shows the Browser tab (#384). `pane_cover` is
not used for hiding: it does nothing on Windows.

## What it is

A **second web view with its own top-level browsing context**, not an iframe.

- **Linux (#201):** a second `WebKitWebView` *inside Crow's own GtkWindow*. pywebview's content
  is wrapped in a `GtkOverlay` at `before_show`, and the view is an overlay child placed on the
  CSS rect of `#brbody`. It is not a window, so `hyprctl clients` shows one Crow and nothing else,
  and the compositor has nothing to float, tile or centre.
- **Windows:** still a second frameless WebView2 window laid over the panel rect (#175). Moving it
  works there.

`CROW_PANE_WINDOW=1` brings back the old separate window on Linux for comparison.

| | |
|---|---|
| why not an iframe | `X-Frame-Options` / `frame-ancestors` refuse embedding. Measured 2026-09-23: 15 of 20 common sites refuse a foreign frame (#201) |
| own profile (#226) | cookies and storage in `~/.local/state/crow/browser`, separate from Crow's UI; logins survive a restart |
| memory ceiling (#226) | WebKit kills the panel's page above 2048 MB (checked every second) and the chat says so |
| sandbox (#226) | the panel's web process runs under `bwrap` when bwrap is installed (`CROW_PANE_SANDBOX=0` turns it off). `file://` pages still load |
| no bridge | foreign pages get no `window.pywebview` |
| geometry | the page reports the CSS rect of `#brbody`. On Linux that rect *is* the overlay position; on Windows Python adds the main window's corner |
| follows | a `ResizeObserver` on the rect (window size, grip, inspector width). Measured under Broadway before #384: the view matched `#brbody` exactly after a window resize and after the code panel took half the column |
| Crow's own sheets | when Settings or the context menu opens over the panel, the page is hidden until the sheet closes; a native view would otherwise cover them (Linux only) |
| one view for all tabs | switching tabs reloads the page |
| folded away | hidden, not destroyed, and **no page kept** (#279): the view goes to `about:blank`, so no WebGL keeps the card. Unfolding or restoring the window loads the tab's entry again (a render tab: its capture). A render while folded fills the render tab and does not unfold the panel |
| crash (#279) | a crashed page (`web-process-terminated`) is taken out of the window and the window is redrawn. A page someone was looking at is reloaded once; a second crash of the same load is not reloaded (#204). The line goes to `crow.log`, not the chat |
| during a turn (#279) | while a turn runs on the local model server, the panel's view uses WebKit's `hardware-acceleration-policy` `NEVER` (no GPU, CPU rendering; a WebGL page may look wrong or slow until the turn ends), then `ALWAYS` again. The chat page keeps the GPU. A remote endpoint leaves the panel alone |
| render_page (#279, #293) | an open panel, or one holding a page, counts as a second GPU client: render_page takes the card only with ≥ 1,536 MiB free instead of 512 (a local crow-nest serve is asked to lend the shortfall first, #297), and otherwise returns an ENVIRONMENT error with no image (it renders on the GPU only) |

## Controls

| | |
|---|---|
| `+` | new tab |
| tab `×` | close; the neighbour takes over, not the first |
| `‹` `›` | per-tab history, kept in a list. On Linux, links clicked inside the page, redirects and `pushState` land in it too (#227) |
| `⟳` | reload |
| address | a URL, a bare host (`example.com` → `https://`), or a local path (`C:\dir\page.html`, `/home/you/page.html` → `file:///`) |
| tab name | the hostname, or the file name for `file://`. The page title is cross-origin |

**One pane for all tabs**, so switching reloads the page. Measured 2026-09-23 (#201): a Chromium
tab per page grew by about 73 MB per page with no bound (271 → 1012 MB PSS over 10 pages). The one
Linux pane stayed flat at about 370 MB for Crow and the pane together after the fourth of 10
cross-site loads.

## Links

On Linux, a link in an answer opens as a **new tab in the panel** (#201). **Ctrl**-click or
middle-click still sends it to the system browser. The GitHub sign-in code always opens in the
system browser, because that is where you are signed in to GitHub. Inside the panel,
`target=_blank` and `window.open` load in the panel instead of starting the system browser (#227).
On Windows, links still open in the system browser (not verified there, #247).

## Width

The inspector's 612 px cap is lifted while the browser is open — a page at 612 is a mobile layout.
The bound is then `innerWidth − 560 − rail`: `#main` keeps its `min-width: 560px`, so the
composer still never overflows. With the browser folded away the cap is back at 612. A dragged
width is stored and read back up to 4,096 px, so a wide one survives a restart (#388); a fresh
install starts at 340 px.

## render_page

`render_page(path)` (class `executing`) shows its result in **one render tab**. Each render is a
new entry in that tab's history, not a new tab (#201). It shows **the screenshot**,
not the live page: the page can have changed since the model looked, and the chat would then
describe something else. The real address is in the bar — Enter loads it live.

See [tools](../reference/tools.md#render_page-175) for the flags, the caps and the measured
cases.

## Offline pages

A page opened from a file cannot load ES modules — the browser refuses every `import` between
local files. `build_bundle` turns the page and its modules into one self-contained file with the
esbuild already on the machine; render that file, not the module source. See
[tools](../reference/tools.md#build_bundle-212).

## Windows (#247)

Windows keeps the old second frameless WebView2 window for the panel. Checked on the owner's Windows
machine on 2026-09-30 (#247); the rows marked *fixed* were fixed after that check and are not yet
run live:

| | |
|---|---|
| the pane | follows the window and the sidebar. It was TopMost over every application (`on_top=True`, seen over Discord); it is now **owned** by Crow's window: above Crow only, behind other apps with it, minimised with it (#329, fixed) |
| profile | pywebview's private default dropped logins on every restart; Crow now starts it with its own storage in `%LOCALAPPDATA%\Crow\webview` (#326, fixed). #226's memory kill and sandbox stay Linux only |
| address and tab | follow each page load (#330, fixed). `pushState` and `#hash` changes fire no load and are not followed |
| after a restart | a panel restored open came up with no tab and stayed blank until `+`; it now starts with a tab, and Enter in the bar without a tab opens one (#327, fixed). `crow.log` has `[pane]` lines for each panel event |
| copy and menu | Ctrl+C and the context menu copy into Notepad with umlauts intact; checked |
| Show in file manager | `explorer /select,<path>` opens the folder with the file selected, also for a path with a space; checked |
| edge grips | the window follows a fast drag and stops on release (#238); checked |
