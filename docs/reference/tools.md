[← README](../../README.md) · [Docs index](../README.md)

## Tools

30 built in, plus whatever [MCP servers](../user-guide/mcp.md) are configured. `/tools` lists
them in either surface, derived from the declarations themselves rather than written beside them.

`read_file` `read_image` `render_page` `write_file` `append_file` `edit_file` `list_dir` `find_files`
`search_text` `run_command` `build_bundle` `web_search` `fetch_url` `memory` `skill` `session_search`
`delegate` `subtasks` `collect` `goal_set` `goal_step` `judge` `git_status` `git_diff` `git_log`
`git_commit` `git_push` `github_connect` `generate_image` `edit_image`.

An MCP tool joins the same list as `mcp_<server>_<tool>`, above the built-ins, and carries its
own class.

### `render_page` (#175)

`render_page(path, wait_ms=4000, width=1280, height=800, frames=1, frame_ms=500)` — a page in a browser Crow owns, rendered on the GPU only (#293).

| | |
|---|---|
| class | `executing` — it starts a process and writes a file |
| browser | Chrome, then Edge; every candidate resolved through environment variables |
| target | a file in the working area, or an `http(s)` URL. A local page keeps a `?query` / `#fragment` (`index.html?shot=default&w=960`, #272): the file is checked without it, then the percent-encoded `file://` URL (drive letter / UNC per RFC 8089) gets it back. A file really named with `?` or `#` wins. A missing file is `no such page: <file>` |
| remote host (#288) | an `http(s)` target's host must already appear in the conversation: the user's words (URL or bare name), a tool result (URL), the goal's title/steps or `PLAN.md` (read at the miss). A subdomain of a named host counts; loopback always passes. Otherwise `error: refused: <host> appears nowhere in this conversation -- a URL you made up?` and no browser starts. Always on, yolo included. `fetch_url` keeps the same guard. Across a rollover the note carries the hosts in one line (newest 60) and the next turn rebuilds the set from it |
| dedupe | the byte-identical warning (#175) keys on the full URL, so `?shot=default` and `?shot=stall` are two pages. With `frames` > 1 it is skipped: page time is Crow's there, so two calls are meant to match, and `precheck.max_frame_diff` is the motion test (#293) |
| output | `<root>/.crow/renders/render-<stamp>.png`, plus the console lines from stderr |
| isolation | its own `--user-data-dir` per run. Without it Chrome hands the job to a running instance and returns exit 0 with no screenshot |
| driving (Linux) | `--remote-debugging-pipe` (fd 3/4, NUL-separated CDP JSON, no library): load, run `wait_ms` **real** milliseconds, `Page.captureScreenshot`. A page with no load event after 15 s is captured anyway |
| driving (Windows) | the command-line `--screenshot` with `--virtual-time-budget=wait_ms`; the pipe there needs handle inheritance nobody has measured yet |
| `wait_ms` | real time after load, 200–20,000. A larger value never rescues a page too heavy to draw. Exception (#302): a local page containing the path-tracing kit's `[crow-pt]` marker may wait 200–120,000, because a progressive path tracer keeps adding samples (~15 samples/s at 1024², RTX 5090); the kit's skill asks for 60,000–90,000 on night or dark scenes |
| caps | one ceiling for the whole call: 15 s load + `wait_ms` + 10 s for the frame. It does not grow with anything the page does |
| GPU only (#293) | the VRAM gate first: ≥ 512 MiB free, or ≥ 1,536 MiB while the window's browser panel is open or holds a page (a second GPU client on the same card, #279). Then, over the pipe, `WEBGL_debug_renderer_info` / `UNMASKED_RENDERER_WEBGL` on `about:blank` before the page loads and in the page after the last capture: a software string (SwiftShader, llvmpipe, lavapipe, softpipe, Microsoft Basic Render) or, with an NVIDIA card in nvidia-smi, a string without "NVIDIA" ends the call. Either failure is `error: ENVIRONMENT -- render_page renders on the GPU only, and the GPU is unavailable: <reason>` with the free VRAM against the bound (#271's wording) or the renderer string, and **no image**. There is no software fallback |
| VRAM loan (#297) | below the bound, when this turn's endpoint is local (loopback, not a remote provider): `POST /v1/crow/vram/lend {"mib": bound - free + 256, "ttl_s": attempts × (15 s load + wait_ms + 10 s capture + frames × frame_ms + 15 s close) + 30 s, ≤ 600}` to crow-nest serve (crow-nest#117), then nvidia-smi again. Clears the bound: the render goes on. Still short: the ENVIRONMENT error adds `lending was tried: the model server lent N MiB … and M MiB were free after it`. Any other answer (404 llama.cpp or an older serve, 501 off, 409 already lent, 400, none): the ENVIRONMENT error as before; after no answer (10 s) the idempotent return is sent anyway, in case serve reads the lend later. `tool_render_page`'s `finally` returns the loan (`POST /v1/crow/vram/return`, 503 retried 3× at 1 s) after the browser is gone; `judge` returns any loan still out before its own request, because serve parks chat requests while lent. Loans and returns are logged as `render:` lines in `crow.log` |
| flags | ANGLE backends in order: `vulkan` (`--enable-gpu --use-gl=angle --use-angle=vulkan --enable-features=Vulkan --disable-vulkan-surface --ignore-gpu-blocklist`), then one retry on `default` (`--use-gl=angle`, measured 2026-09-22: "ANGLE (NVIDIA …, OpenGL ES 3.2)"), each with a fresh profile. `CROW_RENDER_ANGLE=vulkan\|default` pins one. Never `--enable-unsafe-swiftshader`. Its absence is not the guard: measured 2026-09-25, Chromium 152 with `--disable-gpu` still gave WebGL a SwiftShader context. `CROW_RENDER_GL=angle` skips the VRAM gate, and `swiftshader` is a refusal |
| `frames` (#293) | 1–4, default 1 (one capture after `wait_ms` of real time). With more frames, a page clock is installed before the page's first script (`Page.addScriptToEvaluateOnNewDocument`): `Date`, `performance.now`, `setTimeout`/`setInterval` and `requestAnimationFrame` stand at page time 0, and `Math.random` is seeded. After load + `wait_ms` (real async work such as fetch or shader compiles still finishes), each capture follows one `runFor(frame_ms)`, which fires timers and 60 Hz frames in time order with a real macrotask between them. Frame *i* shows page time (*i*+1)·`frame_ms`. Files: `render-<stamp>.png`, `-f2` … `-f4`, and `-sheet.png` (2×2, each frame at half size, the sheet as large as one frame; the newest `render-*.png`, so the judge's default). CSS animations, `<video>` and workers keep their own clocks. Linux only (it needs the pipe) |
| record (#293) | the first line of every capture and of every ENVIRONMENT error: `render: {"render_mode": "gpu"\|"unavailable", "renderer", "frames": [paths], "contact_sheet", "precheck", "backend", "free_mib"}` (+ `reason` when unavailable). |
| precheck (#293) | the same ≤ 100,000-px sample as the metrics. On the last frame: `uniform` (≥ 98 % one colour or < 16 colours), `distinct_colours`, `one_colour_pct`, `dark_pct` (luma < 16), `clipped_pct` (R, G, B ≥ 250). Over all frame pairs: `max_frame_diff` (% of pixels whose largest channel delta is > 25, three.js' pixelThreshold 0.1) and `identical_frames` (`max_frame_diff` < 0.5 %). Both are `null` for one frame. `warn: precheck -- …` for uniform, ≥ 90 % dark and no motion; these lines never feed #268's stuck count |
| memory | Linux: its own user scope, `MemoryMax=6G`, swap 0 (#213). A browser started through `run_command` instead runs under that tool's 8G scope (#218) |
| kill | `proc.kill()` on its own handle, then its session. Never by name, never a process list (#158) |
| pipes | stdout and stderr go to a file: `communicate()` hangs on Windows after a kill when a grandchild holds the write end. The two DevTools pipes are Crow's own ends, read with `select` and a deadline |
| metrics (#265) | after the file line, `metrics:` lines from the capture's own pixels (the #213 decoder, PNG only): the content box on a near-uniform background, its coverage of the frame and ~visual tokens (~1,030 px per token, measured), distinct colours in a ≤100,000-px sample, mean luma and an 8-bin luma histogram. `warn:` when coverage is under 25 % or under 16 colours. Under 50 % coverage the box plus a margin is saved enlarged as `render-<stamp>-crop.png` and named — `read_image` it for detail |
| API hints (#253) | after the capture, one `Runtime.evaluate` (3 s, `RENDER_PROBE_S`) lists the page's own interface prototypes with each member's `length` (WebIDL: the required argument count). Every console line is then read against it: `X.name is not a function` gets a `hint:` line naming the nearest real member within 1-2 edits and the interface that has it (or says the name is real on another object, or exists nowhere), plus the page's own `name=function` probe line when there is one; `WebGL: INVALID_*: fn: …` gets the call's top-level argument count from the source line the console names (the page or its own folder only) against the live `fn.length`, and a sibling with that arity. Linux only: without the pipe (Windows) or without an answer, only the page's own probe lines and the argument count are claimed |

A failed capture (the GPU was there but no frame came) says that a larger `wait_ms` will not help —
the old `timed out after 20000 ms` read as "give it more", and a model escalated
6000 → 12000 → 20000 on a page whose cost did not depend on it.

Smoke, 2026-09-25, Chromium 152.0.7977.82, no GPU (`--disable-gpu`, the check bypassed for the second part), a
canvas-2D page with a rotating square and 200 `Math.random` dots, 640×400, `wait_ms` 500:

| case | wall clock | result |
|---|---|---|
| the renderer probe on a GPU-less browser | 0.5 s | `error: ENVIRONMENT … software rasterer: ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) …` (both backends tried), no image |
| `frames=4, frame_ms=250`, twice | 1.6 s each | page time 250/500/750/1000 ms in the frames, 4 pairwise different frames, the second call byte-identical to the first (sha256); `max_frame_diff` 5.549, `identical_frames` false |

Measured 2026-09-22, Chromium 152.0.7977.82, RTX 5090 free, before #293 (software was still an arm then):

| case | wall clock | result |
|---|---|---|
| WebGL voxel diorama (23k voxels), software, old path, virtual budget 1000 / 2000 / 4000 | 32.7 / 32.8 / 32.8 s | flat: 0.345 s per software frame, ~90 frames before the CLI draws. The old deadline was 9 / 10 / 12 s |
| same page, software, `wait_ms=4000` | 6.9 s | 1280×720 capture of the scene |
| same page, GPU, `wait_ms=4000` | 5.7 s | capture; the page's own 90-frame loop settled |
| same page with an endless animation loop, software, `wait_ms=20000` | 22.8 s | capture (old path: once 31 s, once no image in 40 s) |
| page settling at 300 ms, `wait_ms=1500` | 1.8 s | settled text; "almost one colour" note (99.96 % white) |
| endless `fetch` loop, `wait_ms=1200` | 1.5 s | capture (old path, measured 2026-08-31: no image after 9.3 s) |
| `while(true){}` | 25.1 s | `error: ... no frame within 10 s of the capture request, and no load event within 15 s before it` plus the rasterer advice |

The #253 hints, replayed over the 47 real `render_page` results of 2026-09-23 (the diorama run,
where the model's own code called `gl2.texImage33D` and read Chromium's correct error as a
missing API): 18 carried a failing name or WebGL error; a hint was given for 0 of 18 before and
17 of 18 after with the live names (the 18th is a real shader failure), 10 of 18 in the fallback
without names.

Under the old virtual clock the GPU arm drew **no** `requestAnimationFrame` frame at all
(a page-side counter stayed below 10 while the budget ran out in ~10 ms of real time);
real time is what an animated page actually needs.

The console line `GL Driver Message (OpenGL, Performance, GL_CLOSE_PATH_NV, High): GPU
stall due to ReadPixels` comes from Chromium's bundled ANGLE, not from the NVIDIA driver:
measured, it appears only in the SwiftShader arm, and the string is in the `chromium`
binary and in no `libnvidia-*`. The result opens as a tab in the
[browser panel](../user-guide/browser.md).

In goal mode, a run of `render_page` captures of one page that come back blank or nearly the same
is counted: after 3 the next nudge says to bisect, and after 6 the context rolls over with a list
of what was tried (#268, see [goals and subagents](../user-guide/goals-and-subagents.md)).

### `run_command` (#207, #218, #309, #310)

`run_command(command, cwd=<working area>)` — one shell line, bash on Linux, cmd.exe on
Windows, stdin closed.

| | |
|---|---|
| class | `executing` — outside paths ask first ([Outside paths ask](#outside-paths-ask-144)) |
| clock | `COMMAND_TIMEOUT` = 120 s |
| `cwd` (#221) | resolved against the working area, `~` expanded. A `cwd` that is not an existing directory runs nothing and asks nobody -- it is refused before the approval card: `error: no such directory: … -- the command did not run.` (or `cwd is a file, not a directory`), with the working area and a near miss found on disk (per path component, edit distance 1-2 against the existing siblings, the unique best match, case-insensitive on Windows only): `'nibor11896' is 'nibor1896' here`. `read_file` (missing parent), `list_dir` and the outside-root write refusal carry the same hint. Measured over every stored session (2026-09-22): 5 of 18 distinct `cwd` calls named a home that does not exist, and each cost a `pwd` round after a bare Errno 2 |
| capture | 32 MiB per stream in the reader threads (#207); 16 KB of it reach the model |
| memory (Linux) | its own user scope per call, `crow-cmd-<pid>-<hex>.scope` in `session.slice`: `MemoryMax=8G`, `MemorySwapMax=0`, `OOMPolicy=kill` (#218), no `MemoryHigh`: memory.high throttles and never kills, so a command over budget sat at 7G instead of dying at 8G (#309). `CROW_COMMAND_MEMORY_MAX` moves the kill bound (any systemd size), `none` keeps only the swap cap; `CROW_COMMAND_SCOPE=0` runs the shell bare |
| why 8G | measured 2026-09-22 as each scope's `memory.peak`: diorama three.js esbuild bundle 106 MiB, `npm ls --all` 46 MiB, node importing three 21 MiB, gcc 9 MiB, `test_crow` 60 MiB, `test_crow_core` 109 MiB. 8G stops the 54 GiB software-WebGL runaway a seventh of the way and leaves a node build room up to V8's own ~4 GiB heap |
| at the ceiling | the kernel kills every process in the scope at once (`OOMPolicy=kill` = `memory.oom.group`); the result reads `error: command exceeded its memory ceiling (MemoryMax=8G, no swap) and was killed, with everything it started: <command>` followed by the output up to the kill. The reason comes from the unit's `Result=oom-kill`, not from the exit code — `kill -9 $$` stays `[exit -9]`. The failed unit is reset |
| kill | the clock and the capture cap SIGKILL the shell's whole process group (`start_new_session`, `killpg`), then the scope (`systemctl --user kill`), which also takes a descendant that left the group with `setsid`. A command that ends by itself keeps what it put in the background (`server &`); that process stays in its scope and under its ceiling |
| Stop (#310) | Stop during a running command ends it within ~2 s: SIGTERM to the shell's group and its scope, up to 2 s (`STOP_GRACE`) for a cleanup, then the same SIGKILL sweep as the clock. The result reads `error: stopped by the user after <N>s -- the command and everything it started in this call were ended: <command>` followed by the output up to the Stop, and it is counted like a declined call, not a failed one. Every call of the round after it does not run (`error: stopped by the user -- not run`), and no further request goes to the server. A job an **earlier** call left in the background (`nohup … &`) is not touched. `build_bundle` and the syntax check stop the same way |
| background jobs (#309) | a scope that still holds a process when the call returns is recorded. Every later tool result reads each recorded scope once and starts with a `note:` (after the first line of an `error:` result) when the job was killed at its ceiling — `` note: the background job from `<command>` (<unit>) was killed at its memory ceiling (MemoryMax=8G, no swap), with everything it started. `` — or when its `memory.pressure` reads `full avg60` ≥ 50: `… has been stalled on memory N% of the last 60 s at X GiB of its 8.0 GiB ceiling (no swap): it is thrashing, not progressing.` The kill's witness is `session.slice`'s kernel `oom_kill` count rising while the scope vanished; several scopes vanishing at one kill are named together as candidates. Nothing is recorded on Windows or without a scope |
| literal | `--expand-environment=no` on systemd ≥ 254: systemd-run expands `${VAR}` and `$$` in its own command line (measured on 261: `${X}` came out empty) |
| without systemd | no `systemd-run` or no reachable user manager (container, CI, SSH without a session): no scope, no ceiling; the process-group kill still holds |
| Windows | no scope and no group: the clock, the cap and Stop end `cmd.exe` and its children with `taskkill /T /F` (#310; not measured on Windows). A child whose parent already exited can outlive it — a Job Object would be the fix, not built |
| headless browser | a browser name and `--headless`/`--screenshot` in the line add `note: render_page takes this screenshot inside the render's own memory ceiling …` to the result. A note, not a refusal: the browser is bounded here too, a headless browser has uses `render_page` does not cover (`--dump-dom`, `--print-to-pdf`), and a refused line comes back as a script file no pattern sees |
| background output | a process left in the background that still holds stdout keeps its reader: the runner waits 0.25 s (`BOUNDED_RUN_SETTLE`) and returns without what it prints later. Redirect it (`server >log 2>&1 &`) and read the file |

### `build_bundle` (#212)

`build_bundle(entry, out=<entry>.bundle.html|.js, global_name="", minify=true)` — a module
graph as ONE offline file, built by the esbuild already on the machine.

The rule it exists for: a page opened from `file://` has origin `null`, and Chromium fetches
module scripts in CORS mode, so every `import` between local files is refused ("Cross origin
requests are only supported for protocol schemes: … http, https"). Import maps do not change
that. A classic `<script>` is not affected — so the offline shape is one classic script holding
the whole graph, which is esbuild's `--format=iife`. The tool description says this to the
model, together with "never flatten a library by hand".

| | |
|---|---|
| class | `executing` — it starts a process and writes a file; an "always" is keyed to the tool, never to `run_command esbuild` |
| entry `.html` | every `<script type="module">` (`src` or inline) bundled and inlined at the end of `<body>` in document order (modules are deferred; a classic script in `<head>` would run before the canvas exists); the import map becomes `--alias` pairs (targets made absolute: esbuild resolves an alias in its working directory); local stylesheets bundled into `<style>`; local classic scripts inlined as they are |
| entry `.js/.mjs/.ts` | `out` `.js` → the IIFE (`global_name` names its exports; without it an IIFE's exports are unreachable, and when the same esm probe as below finds any, the result says so under the `built` line: "warn: no global_name -- app.js exports boot, and an IIFE without a global leaves it unreachable ..." — warned, not defaulted: a derived name would put `app`/`main` on `window` where it can shadow a page global, and a module that starts itself needs none; no exports or a failed probe say nothing. Measured on the diorama graph: 0.07 s → 0.13 s with the probe); `out` `.html` → the IIFE wrapped in an EMPTY page: no markup, no call to any export. The result then says so right under the `built` line and names the entry's exports ("app.js exports: boot -- nothing calls it"), read from a second, unminified `--format=esm --metafile` run into the temp directory — esbuild's metafile lists `exports` only for esm, for the IIFE it is `[]`. A failed probe says "could not be read" and costs the build nothing |
| a page = an `.html` entry | the tool description says it: write the page as HTML (canvas, markup) with a `<script type="module">` that imports and starts the app, then bundle THAT. A `.js` entry to `.html` is warned, not refused: a module that builds its own DOM and starts itself on load (the three.js-example shape) works through it, and nothing short of running it tells that apart from a `boot()`-shaped one |
| argv | `--bundle --format=iife --platform=browser --charset=utf8 --log-level=warning --log-limit=20`, `--minify` by default, text loader for `.glsl .vert .frag .vs .fs .wgsl .txt`, data URLs for images, fonts, `.glb .gltf .hdr .exr .ktx2 .bin .wasm` |
| esbuild, in order | `CROW_ESBUILD` (Crow's own environment, a pin for one launch); the `bundler` setting / `--bundler` (#274); `node_modules` walking up from the entry (`@esbuild/<platform>`, `esbuild/bin`, `.bin`); `esbuild` on `PATH`; the deno cache (`$DENO_DIR/dl/esbuild-*/`, default `$XDG_CACHE_HOME/deno` = `~/.cache/deno` on Linux — `~/.cache/crow/deno` before #274) and the npx cache (`~/.npm/_npx/*/node_modules/@esbuild/`), newest version wins there. Every candidate must answer `--version`. Another program's `node_modules` is never searched; name it in `bundler` |
| no esbuild | the error lists every place searched and what works: link (or copy) an esbuild into `<working area>/node_modules/.bin/esbuild`, or ask the user for `"bundler"` in `settings.json` / `--bundler`. It says that an `export` in `run_command` does not reach Crow (#274) |
| none found | the result lists every place searched and says not to hand-flatten |
| kit names (#298) | `crow-voxel-kit` and `crow-pathtracer` are always `--alias`ed to `<install>/kits/pathtracer/voxel-kit.js` / `crow-pathtracer.js` when the kit is there, for page and module entries alike. A page import map for the same name wins. The [voxel kit](../user-guide/voxel-kit.md)'s scaffold built this way: 970,310 bytes, 0 errors, 0 warnings, 0.07 s (esbuild 0.28.2, 2026-09-25) |
| caps | one clock for the whole build (`BUNDLE_TIMEOUT` = 120 s), the #207 capture cap in the reader threads, 64 MiB on the result, 8 MiB on the entry page. Every esbuild call, the `--version` probes included, runs through `_bounded_run` — the one runner `run_command` uses; a grandchild left holding the pipe (a node wrapper's shape) does not hold the clock, and a kill takes esbuild's whole process group (#218) |
| write | esbuild writes to a temporary directory; Crow writes `out` behind `write_file`'s fence. A file carrying the `crow build_bundle` mark (a `<meta name="generator">` / a first-line comment) is replaced freely; any other existing file only after a read in this conversation, unchanged on disk since ([Read before write](#read-before-write-215)) |
| result | path, bytes, errors, warnings, seconds, which esbuild and where from, what was inlined, and whether the page still loads anything from disk. On errors nothing is written and the esbuild log comes back |
| cache | never answered from the repeat cache: an edit to a source changes the result of the same call |

Measured 2026-09-22 on a copy of the diorama-test app graph (three.js 0.186 plus post-processing,
esbuild 0.28.2 from its `node_modules`): 957,335 bytes as an IIFE and 957,410 bytes as a page,
0 errors, 0 warnings, 0.07 s wall. The page rendered the scene through `render_page`; the
module source page next to it logged the CORS refusal above. The same graph with `src/app.js`
as the entry and an `.html` out built just as clean and rendered one colour: the app exports
`boot(canvas, opts)` and needs `<canvas id="c">`, and that page has neither — the trap the
warning above names (0.13 s with the exports probe, `exports: boot`).

### `read_file` (#301)

`read_file(path, start_line?, end_line?)` — UTF-8 text, whole or a line range, capped at 16,000 characters.

| | |
|---|---|
| binary (#301) | the first 8,000 bytes are sniffed before either branch reads: a NUL byte (git's `buffer_is_binary` rule), or a PNG / JPEG / GIF / WebP / BMP / `%PDF-` signature, is a refusal, whatever the extension. No ratio heuristic, so multi-byte UTF-8 split at the edge stays text |
| image | `error: <path> is a PNG image (543x768, 502,797 bytes) -- read_file returns text only; use read_image to see it` (size for PNG and GIF); a name `read_image` does not accept adds `copy it to a .png name first` |
| PDF | `… is a PDF document (N bytes) -- …; get its text with run_command (pdftotext <file> - \| head -200)` |
| other binary | `… is a binary file (N bytes, NUL bytes in its first 8,000) -- …; inspect it with run_command (file <file>; xxd <file> \| head)` |
| not marked read | a refused file is not recorded for the read-before-write rule (#215) |

Measured before the fix (2026-09-25 lighthouse run, session msg 8): `read_file reference/island.png` returned
16,056 characters (~5,946 tokens) of the PNG decoded as UTF-8; the model then saved "read_image returns raw bytes"
into `.crow/MEMORY.md`.

### `read_image` (#170)

`read_image(path)` — the model's own way to a picture; `/image`, drop and Ctrl+V are the
user's.

| | |
|---|---|
| class | `reading` — asks at no level |
| types | `.png .jpg .jpeg .gif .webp .bmp`, other extensions refused by name |
| path | resolved against the working area, like every other reader (#177) |
| result | tool message content becomes `[{text}, {image_url}]` (or `[{text}, frame, crop]`, below) — the block a pasted image travels as; the server reads it in any role |
| no projector | `refuse_images` checks `/props` before the block is attached; without `--mmproj` the sentence comes back instead of an image (a picture to a blind server is HTTP 500, not a recoverable tool error) |
| size | none of its own — the server caps at `--image-max-tokens` (4,096) |
| small scene (#265) | a PNG whose content sits on a near-uniform background and covers under 50 % of the frame gets a **second** block: the content box plus a margin, nearest-neighbour enlarged to a 1024-px long edge (≤ 4×, ≤ ~1,024 visual tokens). The frame stays first and unchanged; the text says `TWO images`, the coverage (`the content fills 8 % of the 1280x720 frame`), the crop box and the scale |
| missing crop (#301) | `read_image <stamp>-crop.png` when only `<stamp>.png` exists: `error: no such image: … -- render_page writes a -crop.png only when the content covers under 50 % of the frame (its result then has a 'metrics: crop' line); this capture has none: read_image <frame>` |

How the content box is found: 16-px cells, each cell's mean colour against the per-channel
median of the outer ring of cells (the ring must be ≥ 60 % ground, else no claim); a cell off
by more than 12 on any channel is content; 8-connected regions at least a quarter the size of the
largest are kept, so a HUD line in a corner drops out. Cell means average film grain away — the
diorama page's ground holds only ~67 % of its pixels in one exact colour.

Measured 2026-09-24 on the 62 renders of the 2026-09-23 diorama run (the served tower bills
~1,030 px per token: 984×552 → 527 tokens, 1280×720 → 880): frames with the scene in view
cover 7.0–22.2 % (`render-20260923-232855.png`: box x 512–768, y 224–512, 8.0 %, ~72 tokens;
crop x 471–809, y 180–556 at 2.7× → 920×1024), blank captures give no box, a page drawn edge to
edge gives no crop. Decode plus detection: 0.03–0.23 s per render.

### `generate_image` and `edit_image` (#300, #308, #311)

`generate_image(prompt, aspect_ratio="16:9", seed=None)` makes a new picture.
`edit_image(images, instruction, description, aspect_ratio=None)` changes 1–10 pictures.
Both use Qwen-Image 2.1 on a resident `sd-server`.

| | |
|---|---|
| class | `executing`: they start a process, hold the GPU for minutes and write a file. Never answered from the repeat cache |
| server | `sd-server` (stable-diffusion.cpp 2f88688) from `<install>/bin`, on `127.0.0.1:8097`. Linux builds it with `tools/build-sd-server.sh` or `install.sh --build-image-server` ([Linux](../user-guide/linux.md#image-server)); the Windows package carries `sd-server.exe` when it was packed with `pack-release.ps1 -SdBuildDir` ([Install](../user-guide/install.md#image-server-windows)). Without it both tools answer `the image server is not installed`. It starts on the first call if nothing answers `GET /sdcpp/v1/capabilities` and then stays loaded. Its working directory is `<state>/image-server`, an empty folder, never the window's (#324): sd-server walks it on every capabilities probe (`--lora-model-dir` defaults to `.`). A 5xx on capabilities ends the start at once with the server's `EXCEPTION_WHAT` text; no answer at all is waited for up to 180 s. Linux adds `LD_LIBRARY_PATH=<data>/cuda/lib`. It is detached, in its own user scope like `llama-server`, and stopped when Crow exits (by handle; a server someone else started is used, never stopped). `crow_core.image_server_warm()` starts it and sends a 256×256, 1-step job so the first real job does not pay the weight load |
| argv | `--diffusion-model <M>/transformer/…index.json --llm <M>/text_encoder_sdcli/…index.json --vae <M>/vae/…safetensors --backend te=cpu --diffusion-fa --max-vram 7 --vae-tiling --model-args qwen_image_2_1_prefix_cache_type=q8_0 --listen-port 8097 -v`. Windows: + `--mmap` (#320): under WDDM every CUDA allocation also counts against the system commit limit, and without it sd-server needs ~37 GB of commit beside serve's 26.7 GB (no pagefile, limit 64,901 MB); with it the job completed in 237.7 s at 51,149 MB commit |
| model | `M` = `$CROW_IMAGE_MODEL_DIR`, else `<models_dir()>/qwen-image-2.1`. On a Linux install `models_dir()` is a link to one text model's tree, so the variable is how a models root elsewhere is found |
| licence | [`Qwen/Qwen-Image-2.1`](https://huggingface.co/Qwen/Qwen-Image-2.1): Qwen Research License Agreement (release date 2026-09-20): research and evaluation only; commercial use needs a separate licence from Qwen (model-business@notice.qwencloud.com), sections 2a/2b of its `LICENSE` |
| log | the server's stdout and stderr in `<log_dir>/sd-server-8097.log`, rewritten per start, the previous one kept as `.prev.log` |
| API | `POST /sdcpp/v1/img_gen` (202 + job id), then `GET /sdcpp/v1/jobs/{id}` every 0.5 s until `completed`, `failed` or `cancelled`. Body: `prompt`, `width`, `height`, `seed`, `sample_params {sample_steps 40, euler, txt_cfg 1.0}`. `vae_tiling_params` is never sent |
| sizes | the model card's table: 1:1 2048×2048, 4:3 2400×1792, 3:4 1792×2400, 3:2 2528×1696, 2:3 1696×2528, 16:9 2752×1536 (default), 9:16 1536×2752 |
| edit, stage 1 | the edit at ~1 MP. Each reference is resized by the server (`image_preprocess` `target=ref,index=k,mode=stretch,width,height,filter=lanczos`) to diffusers' `calculate_dimensions(1024², its ratio)` rounded to /32. The output uses the target shape's 1 MP size (16:9 → 1376×768). `ref_image_args` is `vae_input_max_pixels=1048576` and the prompt is `instruction` |
| edit, stage 2 | img2img at the full size with **no references**: `init_image` = the stage-1 PNG (the server stretches it: `target=init,mode=stretch,…,filter=lanczos`), `strength` 0.25, prompt = `description`. The model sees only this text and that picture, so `description` has to describe the whole final image |
| edit shape | `aspect_ratio`, else the last image's width:height snapped to the nearest table row (by log ratio). Sizes come from the file header (PNG, JPEG, WebP, GIF); Crow has no Pillow |
| inputs | `read_image`'s checks (working-area path, the `IMAGE_TYPES` table, 32 MiB) plus magic bytes. A path outside the working area is refused unless the user named it or released it with "always". A release that contains the working area itself (`/`, `/home`) releases nothing here |
| output | `<root>/images/<YYYYmmdd-HHMMSS>-<slug>.png`, created exclusively and never overwritten (`-2`, `-3`, …). The result names the path, W×H, bytes, seconds and seed (edit: both stage times), and the PNG goes on `read_image`'s ride so the model sees it. On a server without a projector the result stays a success and says the picture is not shown |
| progress | `TurnEvents.tool_progress(name, state)` while the call runs. `state` has `job`, `kind`, `phase` (queued, loading, encoding, sampling, decoding, refining, saved, error, stopped), `stage` (`1/2`, `2/2` or empty), `i`, `n`, `eta_s`, `line`, and the final `width`/`height` from the first event. The phases come from the server's log (`SdProgress`, #308's table). ETA = remaining steps × median of the last ≤ 5 step times, step 1 excluded. After the result, `image_created(path, source, job)`. The terminal redraws its one open line with `\r` and prints `image: <path> (W×H, N KB)` |
| stop | `sd-server` cancels only a queued job (409 while generating). Stop ends the wait, the result says the server finishes the job in the background, and nothing is saved |
| failures | a missing binary or model, a server that exits or stops answering (with its last log lines), a `failed` job (with its message), or 20 minutes without a result per job. Each is an `error:` result, never a hang. When the log since the job's start holds `cudaMalloc failed: out of memory` or an `[ERROR` line with `failed to allocate`, the result says `the image server ran out of GPU memory: <line>` (`memory` for a host buffer) instead of the server's `generate_image returned no results`; a `ggml_cuda_host_malloc: failed ... pinned memory` line alone gives `could not allocate pinned host memory: <line>`. On Windows the result adds that the system memory commit limit (RAM plus pagefile) may be the cause (#320) |
| notes | a chat's `image` notes keep only `path`, `name`, `w`, `h`, `bytes`, `source` and `job`, never pixels. `imgjob` notes (one per job, kept current by the window) keep `job`, `kind`, `phase`, `stage`, `w`, `h` and `line`, so a restart can show an unfinished job as interrupted. `video` notes (#340, `animate_image`'s clips, announced through `TurnEvents.video_created`) keep the same fields as `image` |
| thread | `tool_progress` is always called on the turn's own thread: the tool polls the job and reads the log in its own loop, and the sink is thread-local, so a helper thread's `report_progress` reaches nothing |

Measured on Linux 2026-09-27, RTX 5090 beside the 27B serve (8.15 GiB free after its load), 62 GiB host,
sd-server 2f88688 with the argv above, 40 steps (crow-nest `decode_out/p3-img`, RESULTS.md):

| job | wall clock | result |
|---|---|---|
| generate 2752×1536, cold (first job loads the weights) | 175.3 s | clean; card peak 31,322 MiB |
| generate 2752×1536, warm | 155.2 s | clean; no text-encoder reload |
| edit at 4 MP (ref 2752×1536, out 2752×1536) | 697.2 s | grain over the whole frame, edit not applied |
| edit, ref 1376×768, out 2752×1536 | 251.4 s | frame-wide grain |
| edit stage 1 (E3): ref 1376×768, out 1376×768 | 105.7 s | clean, edit applied |
| stage 2 (B5): E3 to 2752×1536, strength 0.25 | 55.3 s | clean, closest to E3 |

The two-stage edit is therefore about 161 s, close to one warm generation.

Windows, 2026-09-28 (#320): RTX 5090 beside the crow-nest 27B `serve.exe` (24,020 MiB after its boot), 63 GB host without a pagefile, sd-server 2f88688 with the argv above plus `--mmap`, 40 steps: generate 2752×1536 three times in a row, 235.1 s (first, loads the weights), 218.1 s, 218.5 s; 0 out-of-memory lines, card peak 31,861 MiB. Without `--mmap` all three failed in under 4 s (Windows commit limit).
Both tools ran end to end in the window on 2026-09-27 (robin's live check, #308/#311): generate 162.2 s and 163.6 s, edit 109.4 s + 60.3 s at 2752×1536 (`sd-server-8097.log`); the table's numbers come from the measurement script's requests.
One difference: B5's init was E3 upscaled beforehand (`E3-up.png`), while the tool lets the
server stretch it (`image_preprocess`); the live edit on 2026-09-27 came out clean at 2752×1536
this way (looked at, not measured against B5).

**No negative prompt (#339).** `generate_image` sends `txt_cfg` 1.0 and no `negative_prompt`. At 1.0,
sd-server ignores a negative prompt. Windows, 2026-10-07: an RTX 5090 beside the crow-nest 27B
`serve.exe`, the argv above plus `--mmap`, 2752×1536, 40 steps, 10 prompt/seed pairs × `txt_cfg`
{1.0, 3.0, 6.0} with the pair's object as `negative_prompt`, rated blind by the owner
(`runs/339-negative-cfg/`, PREREG and addendum 1):

| `txt_cfg` | object absent | degraded | warm wall clock | card peak |
|---|---|---|---|---|
| 1.0, no negative prompt | 0 of 6 | 3 of 6 | median 216.5 s (216.0–217.5, n = 10) | 31,411 MiB, 0 OOM |
| 3.0 + negative prompt | 2 of 6 | 1 of 6 | median 398.7 s (398.3–398.9, n = 10), 1.84× | 31,411 MiB, 0 OOM |
| 6.0 + negative prompt | 3 of 6 | 2 of 6 | median 398.6 s (397.8–399.5, n = 10), 1.84× | 31,411 MiB, 0 OOM |

"Object absent" and "degraded" are counted over the 6 pairs whose 1.0 picture showed the object. To
pass, a value needed the object absent in at least 8 of 10 pairs and no degraded picture, so neither
3.0 nor 6.0 passed. Once the negative prompt added the object it was meant to exclude: no bananas at
1.0, bananas at 3.0 and 6.0. An exclusion therefore belongs in the prompt itself, phrased positively
("an empty table" instead of "no bananas").

### Delegation (#143)

Parallelism is bought at a provider, not from the card: `delegate(task)` starts a second
session on a remote spot and returns its id immediately — the local slot (`-np 1`, warm
cache) is refused as a target, hard. `subtasks()` lists where things stand; `collect(id)`
(or `collect("all")`) blocks once and returns the result. A subtask sees only what was
sent to it. Stop cancels the local turn **and** the subtasks; whatever a stream still
delivers is dropped and the card ends `interrupted`. Tokens are counted from the remote's
`usage` block — remote endpoints send no llama timings. The default spot is the free
pool's best answer, pinned only after a model answered twice in a row and carried a real
delegation; the user's own `/delegate <task>` does the same from the composer, [also
while a turn is running](../user-guide/window.md). A failed spot falls forward by what
its error means: sick (429/5xx/timeout) and refusing (403, no endpoints, 402 on a paid
favourite) spots are skipped, while 401, a free spot's 402 and schema errors stop the chain.
The failure names every spot tried and why each one failed ([details](../user-guide/goals-and-subagents.md)).
Up to six refusing spots are skipped without counting against the three transient retries.
Known and open (#242, found offline, not seen live): a subtask stopped while its current spot's
request is failing ends `failed` instead of `interrupted` and marks that spot dead for the session.

| release level | asks before |
|---|---|
| `auto` (default) | nothing |
| `allowedit` | executing |
| `manual` | writing and executing |
| `yolo` | nothing, and it MEANS it: the outside-path ask (#144) and `git_commit` fall silent with it. `git_push` asks at **every** level, yolo's included -- checked before the dial, so no position of it can lie |

Reading never asks, at any level. `yolo` is a session's word: it never reaches the root file, and it dies with the process.

### Goals (#165)

`goal_set(title, steps)` writes the plan; `goal_step(step, status, note)` moves one step to
`running`, `done` or `failed`. Two tools and not one, because they cost different things: the
plan sits in the pinned head of every prompt, so writing one costs a full prefill, while ticking
a step off writes only `<root>/.crow/goal.json` and moves no byte of the prompt. The head carries
the plan, the file carries the state — see
[goals and subagents](../user-guide/goals-and-subagents.md).

`running` on a step that is already running changes nothing on its clock: `started` and the token
mark stay, so the whole stretch is billed when it closes (#275). A `note` given with `running` is
stored on the step; `done`/`failed` replace it with theirs.

`failed` never skips a step (#294, replacing #289's skip on the second `failed`). The answer
carries `failure` (`class`, `counted`, `action`) and `then`, the sentence saying what comes next.
The class comes from the step's last capture, not from the note. On a GPU step, a capture that is
software-rendered, `unavailable`, blank or frozen is *environment*. Anything else is *capability*.
Environment: two retries, then a pause. Capability: a reflection (`goal_step(n, "running",
note="reflection: …")`), then attempt 3 in a fresh context, then `goal_step(n, "split",
substeps=[2–3 items])`. Sub-steps are reported with `goal_step(n, "done"|"failed", note, sub=k)`,
and a failed sub-step pauses. While the goal is paused, `goal_step`, `goal_set` and `judge` refuse.
`checklist=[…]` with `running` writes the step's checklist once (#295); a second write is refused
and the answer shows the frozen one. A step the user skipped cannot be set `done` or `running` by
the model; `/goal redo <n>` takes the skip back (#296). A goal whose steps are all `done` or
`skipped` ends "complete with N skipped" (`ended` in the answer), never `done`. Only the user skips
a step: `/goal skip <n> [reason]`.

A `done` is not taken on the model's word alone (#250). `goal_step(…, "done", note)` is refused
when its own note reports a failure ("in spirit", "with deviation", "cannot be created",
"unreachable", …), and when it has no note on a step last reported `failed`. A user's plan may
end in `check: <command>` (`/goal title | step | step | check: <command>`): the `done` that would
close the goal runs that command through `run_command` (its clock, capture cap and memory scope),
and a non-zero exit refuses the `done` and keeps the goal open. The check lives in the session
directory (`goal-checks.json`), not in the working area's `goal.json`, because the model can write
there and a command it wrote would run unasked at `allowedit`; a model's replan keeps it, `/goal
off` drops it. Replayed on the 10 real `done` calls of 2026-09-23: 6 refused, the 4 with positive
notes passed.

On a visual goal (#267), `done` on a step that makes something to look at must cite a capture
written during this goal (a path, or a bare `render-….png` name from `.crow/renders/`). A step
with a frozen checklist also needs a `judge` verdict with every must-item "yes" (#295). A verdict
stored before the checklist (v2.6.0) is still held to `judge_threshold` (default 8). Steps that only plan
are exempt. `"visual": true|false` in `goal.json` overrides the keyword guess. See
[goals and subagents](../user-guide/goals-and-subagents.md).

### `judge` (#266, #295)

`judge(images="", criteria="", step=None)` has a separate model with fresh eyes check a capture of
visual work against the step's **frozen checklist**. The judge receives **one** request containing
the image(s), the checklist, the goal's title and the step's text. It never receives the
conversation: the maker's own story ("the black screen was a viewport leak, now fixed") is exactly
what talked the maker into its own score. Seen on 2026-09-23: "Every criterion reads 9+ on the
capture" over a small box in a black frame.

| | |
|---|---|
| Precheck (#295) | before any model is asked. It checks the render's `render_mode`: `unavailable`, or `software` on a GPU step (webgl, shader, 3d, voxel, ray…, diorama, three.js; `"gpu": true\|false` in goal.json overrides). It checks the render's `precheck`: `uniform`, under 16 `distinct_colours`, `dark_pct` ≥ 98, or `identical_frames` on a step that needs motion (animate, rain, splash, steam, weather, particles, …). It checks the first image's own pixels: ≥ 98 % one colour, luma mean ≤ 4, under 16 colours. A hit is an **environment** failure: `class: environment`, `judge_called: false`, and the step's retry/pause rung ([goals](#goals-165)) |
| Images | the newest `render-*.png` in `.crow/renders/` by default. When `render_page` recorded clock-stepped `frames` for it, those frames go instead (up to 4); else its `contact_sheet` with the capture; else the capture plus its `-crop.png`. The render facts are read from the result's `render: {…}` line (the #293 contract) in `run_tool`, and stored on the running step as `capture`. Reference images come last |
| Checklist | frozen once per step (`checklist`, `checklist_from`, `checklist_at` in goal.json). It comes from the user's `accept:` lines when the step starts (`accept: 5: <item>` binds to step 5, an unnumbered line to every visual step), else the model's `goal_step(n, "running", checklist=[…])`, else the first `judge` call (`criteria`, or "the frame shows the scene itself"). Except under `accept:` lines, `delivers: <step>` leads (#286). `optional:` items do not gate. `criteria` on a later call changes nothing |
| References | `/goal … \| reference: <image> -- <criterion>` (at most 2, stored in `goal-references.json` in the session directory, never in goal.json). Each adds the advisory item "as good as the reference image <name> on: <criterion>" and sends the image after the capture, for a pairwise answer |
| Answer | JSON: `checklist` (yes/no/unknown per item), `evidence` (one line per item), `passes` (every must-item yes), `overall` (1–10, secondary), `weakest`, `verdict`, `judge`, `chosen_as`, `checklist_from`, `images`, `step`. On a miss: `failure` and `next` (reflect / fresh context / split / pause). `fresh_context_only: true` when the actor's own weights judged. An answer in the old `scores` form is read against `judge_threshold` |
| Stored | on the step in `goal.json` (`judge`: model, checklist, evidence, must, pass, no, unknown, images, references, time). Items answered yes join the step's `passed`, which the no-progress timer watches (#294) |
| Class | `network`: the capture leaves the machine when a remote model judges |

**Who judges**, strongest reachable first, and never inside the maker's context:

1. `providers.json` → `"judge": {"provider": "…", "model": "…"}` when it is set
   (`{"provider": "local"}` means the local model only);
2. the delegate spot, then its fallbacks (your favourites first, then free models by window), at
   most three remote tries. A model whose catalogue row declares it cannot take images is skipped.
   A row that does not say gets tried. The catalogue records `vision` from OpenRouter's
   `architecture.input_modalities` after its next refresh (289 of 458 models listed `image` on
   2026-09-24);
3. this conversation's own model, in a **fresh** request with the images and the rubric only. It is
   refused up front when the server's `/props` says it cannot see. On a one-slot local server it
   also costs the next turn a cold prefill, and the result says so.

A spot that fails (rate limit, 403, no JSON, fewer than half the checklist answered) hands on to the
next one, and the answer lists it under `tried_first`. When no spot answers, that is an environment
failure of the step (#294).

Measured on 2026-09-24 on `render-20260923-232855.png` (the diorama frame the model had scored
9+), with the prompt's seven criteria and four free OpenRouter vision models pinned in turn. All
four returned `min` 2: nemotron-3-nano-omni (26 s), nex-n2.5-pro (26 s), dots-3-note-preview
(22 s) and nex-n2.5-mini (2 s). Each weakest list named the empty black frame, the tiny scene or
the missing reflections. On the same day `inclusionai/ling-3.0-flash-vl:free` (the configured
favourite) answered 404 "unavailable for free", both `inkling` models answered 403, and gemma-4
and qwen3.8 answered 429.

### Git (#156)

`git_status` `git_diff` `git_log` read; `git_commit` `git_push` write. All five run a
fixed argument list **without a shell** — a branch or path that looks like an option
stays data — against the repository the working directory is bound to.

`git_commit` stages exactly the paths it is given: no `-a`, no `.`. `git_push` uses
git's own credentials on this machine; the GitHub token below is for the account, not
for the push.

| | |
|---|---|
| asks | `git_commit` and `git_push`, **at every release level, `auto` included** |
| `always` | impossible for those two — they have no approval scope, so no answer makes the next one silent |
| release level | cannot release them: they are not in the level table at all |

`github_connect` runs the OAuth **device flow**: it returns the code immediately and
polls in the background — the browser leg takes minutes and no tool call may hold the
turn that long. The token lands in `provider_keys.json`, owner-only, and is never
handed to a surface; what a surface shows is the login name. Needs a client id, see
[the window's git panel](../user-guide/window.md).

### `write_file` and `append_file` (#244, #251, #252, #254)

`write_file(path, content)` replaces a file whole; `append_file(path, content)` adds to its end
(a missing final newline is added) and carries no read-first guard, because appending destroys
nothing. Both run the working-area boundary first, then (write only) [the read rule](#read-before-write-215),
then the directory check, and only then touch the disk.

| | |
|---|---|
| how much one call carries (#254) | `whole_write_bytes()` = half the output cap divided by 0.75 tokens per byte, rounded down to whole KB: **10 KB at the default cap of 16384**, 5 KB at 8192 (`CROW_MAX_TOKENS`). Both descriptions state the number and the cap, filled in once at import so the tool list stays byte-stable. A file up to that size goes whole through `write_file`; only a larger one is `write_file` of the first part plus `append_file` parts of up to that size, never "one append per section". An append that leaves a file at or under the limit says once per path: `note: the whole file is N bytes -- one write_file carries up to about 10 KB …`. A call cut at the cap (#203, `TRUNCATED_CALL`) names `append_file` and the part size |
| why that number | measured 2026-09-23 on robin's diorama run (crow-nest, cap 16384, three session files): 61 `write_file` (median 940 B) and 50 `append_file` (median 319 B), each alone in its round, 0 cut off; 49 of the 50 appends left a file of at most 10 KB. With the model's own tokenizer the 111 calls were 0.456 tokens/byte overall and 0.735 at the densest call of 1 KB or more; the reasoning in the same round was at most 1,042 tokens. Half the cap stays free for that |
| the receipt (#252) | `wrote N bytes to P` / `appended to P (+N bytes, file now M bytes)` counts **bytes** of the UTF-8 content (it counted characters until #252; 32 of 112 writes on 2026-09-23 held non-ASCII text). The file is read back and the result adds `(sha256 <12 hex>, file N bytes). Byte-exact: the file holds [ends with] exactly the bytes this call sent; a later read returns them. A mistake in them was in the content.` A read-back that does not end with the bytes sent says `WARNING: the file does not end with the bytes sent` instead |
| the syntax check (#251) | `.js .mjs .cjs` through `node --check <file>`; `.html .htm` inline scripts (no `src`, a classic or `module` type, not a data block such as `importmap` or `x-shader/*`) one by one through stdin, padded so the line number is the page's. One 5 s deadline for the whole check through `_bounded_run`, files over 8 MiB and scripts past the 16th skipped, the first error only: line, message and a 160-char window of the source line with the caret. The result then ends `syntax check (node --check) FAILED -- the error is in the content this file was given:`; an append that does not parse adds that a file still built in pieces may not parse yet. **No `node` on `PATH`, no word**: the check is a help, not a gate, and the write always stands. Replayed on 2026-09-23: 20 of 98 JS/HTML writes would have carried their error |
| edit_file and the check table (#269) | `edit_file` runs the same check on the whole file after the edit. When it fails, the text as it was before the edit is parsed in a scratch copy, and the result adds either `the file parsed before this edit: this edit broke it` or `the file did not parse before this edit either`. Any other format is one row of `syntax_checks` in `settings.json` (see [Settings](settings.md)); a row serves `write_file`, `append_file` and `edit_file` alike, with the same 5 s deadline and 8 MiB limit, and shows the command's first 12 lines on a non-zero exit |
| directories (#244) | a path holding a control character (`pipeline.py\n`) is refused every time, naming the stripped path when that is clean. When the parent is missing, the first missing name is compared with the directories beside it (#221's edit metric, or a proper prefix of exactly one: `w` → `work`) and refused **once** with `did you mean: …` and `Nothing was created`; the identical call again creates it. Every created directory is said: `(new directory: X)`. Measured in the stored sessions: `testcases/w/fs.py` beside `testcases/work` (2026-09-18), 6 of 111 write paths held a control character, 4 of them a trailing newline |
| arguments | `file_path` is taken as `path`, and for `write_file` `file_text` as `content` ([Argument names](#argument-names-207-214-215)) |

### `edit_file` when 'old' misses (#276)

The first line stays `error: 'old' does not appear in <path>` (the goal brake counts it).
Below it:

| case | answer |
|---|---|
| a region resembles 'old' | `The closest text is at lines a-b (similarity r).`, then either `It differs only in whitespace: …` (indentation, tabs against spaces, line breaks) or up to 6 `file N:` / `old:` line pairs; then the file lines with 2 lines of context in `N: text` form (at most 24 lines, 160 chars each, 2,500 chars in all) |
| nothing resembles it | `No part of the file resembles 'old'. read_file it again …` |
| file over 2 MiB | the first line only |

One inexact match is applied: 'old' is whole lines, exactly one window of the file equals it
line by line after `strip()`, every non-blank line differs by the same leading-whitespace prefix,
and every non-blank line of 'new' can take that shift. Then 'new' is shifted the same way and the
result says so: `replaced 1 occurrence in P -- matched only after ignoring indentation: 'old'
had 1 leading space too many on every line, and 'new' was shifted the same way (lines 112-129)`.
The syntax check (#269) runs as on an exact edit. Inner whitespace, tabs against spaces, uneven
indentation, a wrapped line and two candidate windows are never applied.

Measured 2026-09-23/24 (robin's diorama runs, 147 `edit_file` calls): 16 missed. Reconstructed:
3 uniform indentation (applied now; the m292 replay is byte-identical to the model's own retry),
1 line wrap, 6 one-token drift, 3 non-contiguous lines, 2 stale after the model's own edit,
1 not reconstructable. CRLF, tabs and escaped quotes: 0.

### `edit_file` and line endings (#283)

The file is read as it is (`newline=""`). 'old' and 'new' are matched against the file with every
CRLF read as LF, which is what `read_file` shows. Only the matched span is replaced. Lines the edit
does not touch keep their bytes, including a file with mixed endings. The line breaks in 'new' take
the ending of the span they replace. When that span has no line break, they take the file's
majority. A lone CR stays as it is.

| file (40 lines) | CRLF / LF after a one-line edit, before #283 | after |
|---|---|---|
| CRLF | 0 / 40 | 40 / 0 |
| 20 CRLF + 20 LF, edit in the LF half | 0 / 40 | 20 / 20 |

`write_file` and `append_file` write the bytes they are given (`newline=""`). `append_file`'s
added final `\n` is LF.

### `search_text` and `find_files` (#207, #215)

Both walk the tree with one shared prune list (`.git node_modules __pycache__ .venv venv build
dist target .cache`) and one deadline, and both stop at 200 hits or 16,000 bytes of result.

| | |
|---|---|
| binary | `search_text` reads the first 4 KiB of a file; a NUL there means binary, and the file is skipped |
| size | a file over 2 MiB is skipped **before** it is opened (the `--max-filesize` contract) |
| skipped | counted and said: `[skipped N file(s) over 2 MiB or binary -- a hit in them is not a hit you can use this way]` |
| deadline | 30 s over the walk (`SEARCH_DEADLINE`), checked per directory: the hits so far come back with `[stopped after N s -- the walk over R did not finish; narrow the root …]` |
| a file as root | `search_text` searches that file (#215); the glob does not filter it out again |

The incident (filed 2026-09-21): a pattern without hits walked the working area with the 105 GB CNQ
container in it, read every byte as text, and the turn hung until the app was killed (#207).

### Read before write (#215)

`write_file` (on an existing file) and `edit_file` refuse a file the model does not know.
Per path Crow keeps the `(mtime_ns, size)` the file had when `read_file` read it — a line
range counts — or when Crow itself last wrote it (`write_file`, `edit_file`, `build_bundle`;
`append_file` keeps an already-known file known). The call goes through while the file on
disk still carries that stamp.

| state | answer |
|---|---|
| never read in this conversation | `refusing to overwrite … without reading it first in this conversation` / `read … before editing it, in this conversation` |
| read, then changed on disk (another program, the user, a deletion) | `… it changed on disk since you read it -- read it again, then retry the call.` |
| read or written by Crow, unchanged | allowed, across any number of turns |

A read counts for the conversation, not the turn: goal mode's `[Goal mode ...]` nudges are
user messages, and until #215 each of them emptied the state (measured 2026-09-22: 4 of 15
read-rule refusals were edits of a file read one nudge earlier). The state empties where the
model stops holding the contents: a rollover (mid-turn too), a new chat or `/reset`, a
model switch, `--resume` and a chat switch in the window. A delegated subtask neither sees
nor changes it. A rewrite that keeps both the size and the modification time is not seen.

### Outside paths ask (#144)

`run_command` touching paths outside the working directory asks first, at every release
level — one card, every outside path named. An approval covers ALL outside paths of that
command, not just the first; `always` is kept in `approvals.json` — under
`%LOCALAPPDATA%\Crow\` on Windows, `~/.config/crow/` on Linux — and survives the restart. Directories the conversation was pointed at pass without asking.
An obfuscated path does not ask — the gate is a question, not a sandbox.

What counts as "pointed at" is what the **user** named. Four things that look like the user's
words are not (#221, #223, #240, #241): a bare filesystem root in prose (`4120 / package`, which
had released `/` for a whole session on 2026-09-22), the rollover note (a record written by Crow
and the model; only the user's carried lines and the typed line count), goal-mode nudges (they
carry the model's own plan text; a `/goal` plan the user typed still counts, recorded as `by` in
`goal.json`), and the working-area notice of #224 or an image-only turn's notice.

The null device is no outside path (#243): exactly `/dev/null` on POSIX, `nul`, `\\.\nul` or
`//./nul` on Windows (any case), with a trailing `)` from `$(… 2>/dev/null)` shed first. A real
path beside it, a path under it, `/dev/sda` and `/dev/nullx` still ask, and the `cwd` argument is
not exempted. Measured 2026-09-23: 202 of 775 distinct stored `run_command` lines carried
`/dev/null` and stopped at `auto` for it.

### Argument names (#207, #214, #215)

A tool is called with the names its declaration gives. Three cases fall outside that, and
each one is said, never swallowed.

**A sibling harness's name** for the same argument is taken — declared in
`ARGUMENT_ALIASES`, not guessed — and the result opens with what was taken:
`[took old_string as old, new_string as new]`.

| tool | taken as declared |
|---|---|
| `edit_file` | `file_path` → `path`, `old_string` / `old_str` → `old`, `new_string` / `new_str` → `new` |
| `read_file` `append_file` | `file_path` → `path` |
| `write_file` | `file_path` → `path`, `file_text` → `content` |
| `search_text` `find_files` | `path` → `root` |
| `memory` | `new_text` → `content` |

Two names for one argument with different values are an error, not a pick; the same value
twice runs, with `[dropped …]`.

**A key no declaration names** is ignored, and the result opens with
`[unknown argument(s) ignored: …]` (#207).

**A key that is unknown while a required one is missing** is a misnamed argument, and then
nothing runs. The answer names the signature, and it comes before the tool's own checks —
the read-before-edit gate included:

```
error: edit_file was called with unknown argument(s) replace, search and without the
required old, new -- nothing was run. Its arguments are: path, old, new.
```

A required key missing on its own gets the tool's own sentence; `edit_file` says a missing
`old` or `new` before its read rule (`new=""` deletes, a missing `new` no longer does).
`search_text` given a file as its root searches that file.

Measured 2026-09-22 after a rollover: 22 of 22 `edit_file` calls arrived as
`old_string`/`new_string`, all 22 failed, and 15 of them were first told to read the file —
so the model read it and sent the same wrong keys again. 4 of those 15 had read the file one
`[Goal mode ...]` nudge earlier — the read rule was per turn then, and every nudge opened
one. It now lasts the conversation and ends where the file changes
([Read before write](#read-before-write-215)).

The request after a rollover declares the same `tools` array, the same sampler and the same
thinking fields as the one before; only the messages, the pinned head and the per-round
`seed` differ (pinned by `TheSeamKeepsTheRequestTests`; the seed is drawn fresh for every
round, see below).

Since #214 the messages after the cut also show calls that worked. Behind the rollover note
come the last 3 tool rounds before the cut, verbatim: each is the assistant's call(s) and
every matching result, with no dangling `tool_call_id`. A round is carried only when every
call names a declared tool with only declared keys and all required ones, and when no
result was an error (`error: ...`, also behind the bracket notes, or a non-zero `[exit N]`).
So an `old_string` call that #215 resolved is not carried, since it would teach the wrong
name. Reasoning and prose stay behind. Results start with `[carried across the cut]` and
are clipped to 2000 chars (`-- clipped to the first 2000 of N chars`). An image is replaced
by a sentence. The rounds share a budget of 3000 tokens (at 3 chars per token; measured
2.85 on the 17:12 archive). A round that does not fit is skipped whole, never cut. If none
of the three shows `edit_file`, `write_file` or `append_file`, the latest one that does
and fits takes the oldest one's place. The typed line comes after the rounds. Without
rounds the note and the line stay one message. `_READ` stays per turn, so a carried read
grants no edit. At the 17:12 cut this would have carried two `run_command` rounds and the
final `edit_file` (`path, old, new`): 3,755 JSON chars, about 1,250 tokens.

### Rounds that are not answers (#217)

Every round is classified before it may enter the history (`classify_round`):

| class | what it is | what happens |
|---|---|---|
| `markup` | no parsed call, and tool-call markup in the content: crow-nest's `crow_malformed_calls` says `raw_in_content`, or (any other engine) a line starting `<tool_call>`, `</function>`, `<function=`, `function=` or `<parameter=` outside a code fence | not stored; asked again once |
| `stub` | no call, finish `stop`, tools declared, and the text ends on a colon, or shows within 200 chars that a sentence stopped: a comma, dash or opening bracket last, an inline code span or `**` left open, or a last word that cannot end a sentence (an article, a conjunction, a possessive; a form of "to be" right after a noun). No punctuation alone is not enough: `Ja`, `Erledigt`, `42`, `src/app.js` are answers | not stored; asked again once; a stub again on the retry is kept as the answer |
| `think_only` | reasoning and no visible text (#150) | the one visible-answer nudge, as before |

The re-request is on the same prefix — no message is added, so the read ledger, the goal step
and the prompt cache stand — with a new `seed`. A line in `crow.log` (not in the chat) says `discarded a degenerate reply
(<class>, N chars, seed S) -- asking again with a new seed`. If the retry is a stub, it is
stored as the answer with a `crow.log` line (`kept the re-asked reply although it looks unfinished`):
a short answer is never refused twice. If the retry is markup, the turn ends with one red
line naming both classes and both seeds, and the history gets `[no usable reply: markup]`
instead of either round. Replayed over the stored rounds of 2026-09-18..22 (3,155 assistant
rounds in 27 files): 8 markup and 79 stub rounds flagged, 86 of them followed by a goal
nudge; no healthy answer flagged.

Every local request now carries `seed`, drawn per round (1..2^31-1) and recorded as
`_seed` in the round's timings and as `seeds` in the turn's bill in `session.json`. The
rollover digest and the memory pass draw their own and record them as `leg_seeds` in a bill
(the window; the terminal keeps no bills). The seed goes to the sampler, not the template,
so the digest still asks on the warm prefix. crow-nest
samples with seed 0 when none is sent, so a re-request of the same prefix returned the same
tokens. Remote requests carry no seed (`_REMOTE_DROPS`).

A call's raw markup that arrived beside the parsed call is cut out of the stored content.
A call the generation left open gets one of three results, chosen by crow-nest's record for
that call when there is one, else by `finish_reason`: at `stop`,
`error: the generation stopped inside this call's arguments (`path` had run to N chars) ...
This was not the output token limit`; at `length`, the output-limit answer (#203) as before;
a `bad-param-name` record, the declared-names answer. A `finish_reason` of `abort` (crow-nest
#99: the client left or the server shut down) is never an answer: the turn treats it as a
broken stream (one retry, #151), the rollover digest as failed, the memory pass writes nothing.

---

### /verify (#149)

The maker is not the checker. `/verify` (both surfaces) assembles what this conversation
wrote — `write_file` whole, `edit_file` as replaced/with, reads deliberately absent — and
delegates it to the remote spot with review instructions; `collect` fetches the verdict.
User-triggered on purpose: a maker that may skip its own checker will.
