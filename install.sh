#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# install.sh -- Crow on Linux: one command, five steps, no root.
# ---------------------------------------------------------------------------
#
#     curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh | bash
#
# THE CONTRACT IS install.ps1's, TRANSLATED, NOT REINVENTED. Same five steps in
# the same order (preflight, source, install, runtime, what is left to do), same
# per-file sha256 verification, same refusal to elevate, same refusal to
# download the model. What differs is only what the platform makes differ:
#
#   %LOCALAPPDATA%\Crow   ->  ${XDG_DATA_HOME:-~/.local/share}/crow
#   WebView2              ->  WebKitGTK 4.1 through PyGObject
#   Win32 clipboard       ->  wl-clipboard
#   a Start-menu shortcut ->  a .desktop entry, hicolor icons, a Hyprland rule
#   a packaged engine     ->  tools/build-llama-server.sh, built here from a pin
#
# ORDER MATTERS, and it is install.ps1's reason verbatim: every check that can
# reject this machine runs BEFORE anything is downloaded. Finding out afterwards
# that the card is too small is the most expensive possible failure.
#
# NO ROOT, ANYWHERE. Nothing is written outside $HOME. The one thing this script
# cannot do without a password -- installing the GTK/WebKit bindings from pacman
# -- it does not attempt: it prints the line and says the window needs it. A
# script that runs sudo behind a pipe from the internet is the wrong shape.
#
# THE MODEL IS NOT DOWNLOADED HERE. 73.45 GiB, not ours to redistribute, and an
# installer that spends an hour on somebody else's file before the user has seen
# anything work is the wrong shape. The last step prints the two commands.
#
# THE MODEL ROOT IS A LINK AND NOT A VARIABLE. $CROW_HOME/models is a symlink to
# whatever tree `--models DIR` names, because <install>/models is what
# crow_platform.models_dir() answers with nothing set -- so the window, the
# terminal client and tools/start-server.py all read the same tree with no
# environment at all. A CHECKOUT IS ITS OWN <install> (crow_core.INSTALL_ROOT is
# the parent of cli/), so a checkout takes the same link of its own; the last
# step prints that line. See link_models().
#
# IDEMPOTENT. Run it twice and the second run copies the same bytes, reuses the
# venv, reuses the engine, and reports what changed underneath it since the last
# run -- that is what $CROW_HOME/manifest.sha256 is for. It never deletes
# anything it did not install: bin/, cuda/, src/, build/, venv/ and the model
# tree survive every re-run, because the only files it removes are the ones the
# PREVIOUS manifest listed and the new payload no longer ships. That direction
# is install.ps1's Find-DroppedFiles, and the direction is the whole design --
# asked the other way round ("what is on disk that the manifest does not name?")
# it deletes the user's data and needs a list of exceptions nobody can write.
#
# USAGE
#   bash install.sh                      from a checkout: install what is here
#   curl -fsSL <raw>/install.sh | bash   no checkout: fetch CROW_REF (main)
#   bash install.sh --models DIR         where the GGUFs live (linked, see below)
#   bash install.sh --voice              also faster-whisper + sounddevice
#   bash install.sh --tailscale          also the phone over HTTPS: what is missing
#                                        for Tailscale, as commands (never sudo)
#   bash install.sh --build-engine       build llama-server now (~20 min)
#   bash install.sh --pathtracer         also switch on the voxel-diorama skill: the
#                                        model path-traces voxel scenes with the kit
#                                        in kits/pathtracer (three.js, shipped always)
#   bash install.sh --selftest           check this script, install nothing
#
# ENVIRONMENT
#   CROW_HOME          install root, default ${XDG_DATA_HOME:-~/.local/share}/crow
#   CROW_MODELS        override the model root for one shell; --models makes the link
#   CROW_REF           branch or tag to fetch when there is no checkout (main)
#   CROW_BUILD_ENGINE  1 is --build-engine
# ---------------------------------------------------------------------------

set -euo pipefail

# --- what this machine has to bring ----------------------------------------
# The numbers are install.ps1's, and they are the same numbers because they
# describe the same operating point on the same card. 16000 is the floor below
# which nothing was ever measured; 32000 is the profile every figure in
# README.md was taken at.
VRAM_SUPPORTED_MB=16000
VRAM_TARGET_MB=32000
# 60 and not 64: this machine reports 62 GiB of a nominal 64, because firmware
# and hardware reservations come off the top before the kernel sees the memory.
# A threshold at the nominal size would warn exactly the configuration every
# measurement was taken on. install.ps1 carries the same 60 for -ncmoe's L2.
RAM_WARN_GB=60
DISK_INSTALL_GB=2
DISK_MODEL_GB=85          # reported, never enforced -- the model is a later step
PY_MIN="3.9"              # measured: cli/crow_core.py uses str.removesuffix (3.9)

REPO_SLUG="nibor1896/Crow"
PACMAN_LINE="sudo pacman -S --needed python-gobject gtk3 webkit2gtk-4.1 wl-clipboard"

# The payload. Directories are copied whole minus the exclusions in
# payload_paths(); files are copied if they exist.
PAYLOAD_DIRS="cli manifests tools patches kits"
PAYLOAD_FILES="README.md LICENSE NOTICE CHANGELOG.md install.sh"

ICON_SIZES="16 24 32 48 64 128 256 512"

# --- output ----------------------------------------------------------------
if [ -t 1 ]; then B=$'\033[1m'; D=$'\033[90m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; Z=$'\033[0m'
else B=""; D=""; G=""; Y=""; R=""; Z=""; fi

STEP=0
TOTAL_STEPS=5
step()  { STEP=$((STEP + 1)); printf '\n%s[%d/%d] %s%s\n' "$B" "$STEP" "$TOTAL_STEPS" "$*" "$Z"; }
ok()    { printf '  %sok%s    %s\n'   "$G" "$Z" "$*"; }
warn()  { printf '  %swarn%s  %s\n'   "$Y" "$Z" "$*"; }
bad()   { printf '  %sno%s    %s\n'   "$R" "$Z" "$*"; }
note()  { printf '        %s%s%s\n'   "$D" "$*" "$Z"; }
cmd()   { printf '    %s\n' "$*"; }
die()   { printf '\n%serror:%s %s\n' "$R" "$Z" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Pure helpers. Everything the selftest drives lives here, and everything here
# is a function of its arguments -- install.ps1's rule, for install.ps1's
# reason: a check that can only be run by performing the install is a check
# nobody runs.
# ---------------------------------------------------------------------------

# The version literal, read from the one place that owns it.
# tools/check_operating_point.py holds cli/crow.py, install.ps1 and the README
# badge against the manifest. This script deliberately carries NO copy of the
# number: a fourth place nobody checks is a fourth place that drifts.
version_from_crow_py() {
    [ -f "$1" ] || return 0
    # awk and not `sed | head`: `pipefail` is on, and a producer that is still
    # writing when head closes the pipe turns a correct answer into exit 141.
    awk '/^VERSION[ \t]*=[ \t]*"/ { s = $0
        sub(/^VERSION[ \t]*=[ \t]*"/, "", s); sub(/".*/, "", s); print s; exit }' "$1"
}

# Where to fetch from when there is no checkout. A ref that looks like a release
# is a TAG, anything else is a BRANCH -- the Linux port has no tag yet, so the
# default is a branch and the release path is exercised the day there is one.
# NOT the Windows release asset: crow-<version>-win-x64.zip carries llama-server.exe.
tarball_url() {
    local ref="$1"
    case "$ref" in
        v[0-9]*.[0-9]*.[0-9]*|[0-9]*.[0-9]*.[0-9]*)
            printf 'https://github.com/%s/archive/refs/tags/v%s.tar.gz\n' \
                   "$REPO_SLUG" "${ref#v}" ;;
        *)
            printf 'https://github.com/%s/archive/refs/heads/%s.tar.gz\n' \
                   "$REPO_SLUG" "$ref" ;;
    esac
}

# The three preflight verdicts, as pure functions so the selftest can drive the
# rejecting side of each without a machine that fails.
vram_verdict() {
    if   [ "$1" -lt "$VRAM_SUPPORTED_MB" ]; then echo fail
    elif [ "$1" -lt "$VRAM_TARGET_MB" ];    then echo warn
    else echo ok; fi
}
ram_verdict()  { [ "$1" -lt "$RAM_WARN_GB" ] && echo warn || echo ok; }
disk_verdict() {
    if   [ "$1" -lt "$DISK_INSTALL_GB" ]; then echo fail
    elif [ "$1" -lt $((DISK_INSTALL_GB + DISK_MODEL_GB)) ]; then echo warn
    else echo ok; fi
}

# The .desktop entry is a TEMPLATE and @CROW_LAUNCHER@ is its contract -- see the
# comment at the head of cli/crow.desktop. A template that does not carry the
# placeholder is a template that lost it, and writing it out unsubstituted would
# install a launcher entry whose Exec line is the literal string.
desktop_substitute() {
    local template="$1" launcher="$2" line
    grep -q '@CROW_LAUNCHER@' "$template" \
        || { echo "no @CROW_LAUNCHER@ in $template" >&2; return 1; }
    # NICHT sed, UND DAS IST DER PUNKT: der Pfad ist DATEN, und die rechte Seite
    # eines `s|...|...|` ist es nicht. `&` heisst dort "der ganze Treffer", ein
    # `\` leitet eine Maskierung ein, und ein `|` beendet den Ausdruck mit
    # "unknown option to `s'". Alle drei sind ueber `--to` erreichbar, alle drei
    # gemessen 2026-09-16: `/opt/a&b/crow` wurde zu `/opt/a@CROW_LAUNCHER@b/crow`,
    # `/opt/a|b/crow` zu einem sed-Fehler und damit -- wegen der Umleitung an der
    # Aufrufstelle -- zu einer LEEREN crow.desktop. Die Ersetzung in bash kennt
    # keine dieser Sonderbedeutungen; das Anfuehrungszeichen um "$launcher"
    # schaltet zusaetzlich `patsub_replacement` aus, das seit bash 5.2 an ist und
    # `&` genauso liest wie sed.
    while IFS= read -r line || [ -n "$line" ]; do
        printf '%s\n' "${line//@CROW_LAUNCHER@/"$launcher"}"
    done < "$template"
}

sha_of() { sha256sum "$1" | cut -d' ' -f1; }

# An absolute path, WITHOUT asking the filesystem. The first version resolved
# the parent with `cd "$(dirname X)" && pwd`, which is correct for a directory
# that exists and silently wrong for one that does not: `--models
# /does/not/exist/models` became `/models`, because the failing `cd` was not
# what the assignment took its exit status from. A path the user names may
# legitimately not exist yet -- that is the ordinary case for a model root the
# download has not created -- so this is pure string work.
abspath() {
    case "$1" in
        /*)  printf '%s\n' "$1" ;;
        "~") printf '%s\n' "$HOME" ;;
        "~/"*) printf '%s\n' "$HOME/${1#\~/}" ;;
        *)   printf '%s\n' "$PWD/$1" ;;
    esac
}

# --- the model root: ONE mechanism, and it is a link ------------------------
# IT USED TO BE A VARIABLE AND THE VARIABLE REACHED EXACTLY ONE ENTRY POINT.
# `--models DIR` wrote `export CROW_MODELS="DIR"` into $CROW_HOME/env and only
# the generated launcher sourced that file, so the window found the models and
# NOTHING ELSE DID: `python3 $CROW_HOME/tools/start-server.py flash-next-q2-k-xl`
# and `python cli/crow_gui.py` out of a checkout both answered "model is not on
# disk" (gemessen 2026-09-16). An environment variable set in one process is not
# a path on disk, and a path that only one of five entry points can see is the
# same failure crow_platform.models_dir() warns about in its own docstring.
#
# So the installer writes the path where every entry point already looks:
# $CROW_HOME/models, a symlink to the tree. models_dir() falls back to
# <install>/models with no variable set at all, and install_dir() on Linux is
# the XDG data directory whether Crow is started from the desktop entry or from
# a checkout -- so one link answers all of them. $CROW_MODELS survives as what
# its docstring always said it was: the override, for one shell.
#
# What may be done to $CROW_HOME/models, decided from the filesystem alone:
#   link   absent, a symlink already, or an empty directory -- (re)point it
#   keep   a real directory with files in it: that is somebody's model tree
#   clash  anything else, i.e. a regular file -- not ours to delete either
models_link_verdict() {
    local link="$1"
    # -L IS ASKED FIRST because a symlink to a directory is also -d, and a
    # dangling one is not -e: asked in any other order, the two cases that
    # MUST be retargeted would read as "keep" and "clash".
    if   [ -L "$link" ];   then printf 'link\n'
    elif [ ! -e "$link" ]; then printf 'link\n'
    elif [ -d "$link" ];   then
        if [ -n "$(ls -A "$link" 2>/dev/null)" ]; then printf 'keep\n'; else printf 'link\n'; fi
    else printf 'clash\n'
    fi
}

# Is this $CROW_HOME/env one WE wrote? Only then is it ours to delete. The three
# lines below, in this order, and nothing else -- a user who put their own
# exports in that file keeps every one of them and is told the file is dead,
# because deleting what somebody else edited is not a thing an installer does.
installer_env_p() {
    [ -f "$1" ] || return 1
    awk 'NR == 1 && /^# Sourced by .* before the window starts\. Written by install\.sh\.$/ { a = 1; next }
         NR == 2 && $0 == "# Change the model root here, or re-run install.sh --models DIR." { b = 1; next }
         NR == 3 && /^export CROW_MODELS="[^"]*"$/ { c = 1; next }
         { extra = 1 }
         END { exit !(a && b && c && !extra && NR == 3) }' "$1"
}

# --pathtracer (#298). The kit ships with every install (kits/pathtracer,
# ~1 MB); the flag switches its skill on, because a switched-off skill costs the
# prompt nothing and a switched-on one costs every turn a line.
#
# The kit's bundle against its own kit.json: ok | missing | corrupt. The first
# `"sha256": "` in kit.json is the bundle's -- tools/build-pathtracer-kit.sh
# writes the bundle block first, and the licence hashes sit under another key.
pathtracer_kit_verdict() {
    local kit="$1" want
    [ -f "$kit/kit.json" ] && [ -f "$kit/crow-pathtracer.js" ] || { echo missing; return 0; }
    want="$(awk -F'"' '/"sha256": "/ { print $4; exit }' "$kit/kit.json")"
    if [ -n "$want" ] && [ "$(sha_of "$kit/crow-pathtracer.js")" = "$want" ]; then echo ok
    else echo corrupt; fi
}

# The voxel-diorama skill's switch, read from its SKILL.md: on | off | absent.
# Absent is the normal state of a machine that has not started Crow since the
# kit shipped -- the core seeds the skill (off) at its next start.
kit_skill_state() {
    local file="$1"
    [ -f "$file" ] || { echo absent; return 0; }
    if grep -qx 'enabled: false' "$file"; then echo off; else echo on; fi
}

# Switch the skill on through the core's own function, the same act as the
# switch in the settings sheet. Prints enabled | already | missing, or !error.
enable_kit_skill() {
    local py="$1" cli="$2"
    "$py" - "$cli" <<'EOF' 2>/dev/null || echo "!the core could not be imported"
import sys
sys.path.insert(0, sys.argv[1])
try:
    import crow_core
    print(crow_core.enable_kit_skill())
except Exception as exc:
    print("!%s" % exc)
EOF
}

# The files this package ships, as paths relative to ROOT, sorted.
#
# test_*.py IS NOT SHIPPED, and that is pack-release.ps1's rule rather than a
# new one: the suites are developer equipment, nothing outside the repository
# refers to them, and cli/test_crow_gui.py alone is 900 kB in every install.
# __pycache__ for the reason the Windows packager states: -Recurse once shipped
# a .pyc of the packaging machine's Python version.
#
# tools/archive/ IS NOT SHIPPED EITHER, for the same reason one directory over:
# it is the lab -- the dated measurement harnesses that produced the numbers in
# CHANGELOG.md, PowerShell and CUDA probes against a machine nobody installing
# this has. Nothing on any path the product takes reads them (that is the rule
# in docs/plans/linux-implementation-plan.md 5.3 and why they are archived), and
# they are the larger half of tools/ by file count.
payload_paths() {
    local root="$1" d f
    {
        for d in $PAYLOAD_DIRS; do
            [ -d "$root/$d" ] || continue
            ( cd "$root" && find "$d" -type f \
                ! -path '*/__pycache__/*' \
                ! -path 'tools/archive/*' \
                ! -name '*.pyc' ! -name '*.pyo' \
                ! -name 'test_*.py' -print )
        done
        for f in $PAYLOAD_FILES; do
            # `if` and not `[ ... ] && printf`: under `set -e` a loop whose last
            # command is a false AND-list ends the subshell, and `pipefail` then
            # carries that 1 out through the sort.
            if [ -f "$root/$f" ]; then printf '%s\n' "$f"; fi
        done
    } | LC_ALL=C sort
}

# `<sha256>  <path>` per file, i.e. sha256sum's own format, so a user who wants
# a second opinion can run `sha256sum -c manifest.sha256` and get one.
manifest_of() {
    local root="$1" rel
    payload_paths "$root" | while IFS= read -r rel; do
        printf '%s  %s\n' "$(sha_of "$root/$rel")" "$rel"
    done
}

# What happened to the files the last run installed, asked BEFORE this run
# overwrites them. Prints one `<state> <path>` line per file that is not as the
# manifest left it; silent when nothing moved.
manifest_audit() {
    local root="$1" manifest="$2" want rel
    [ -f "$manifest" ] || return 0
    while read -r want rel; do
        [ -n "${rel:-}" ] || continue
        if [ ! -f "$root/$rel" ]; then printf 'missing %s\n' "$rel"
        elif [ "$(sha_of "$root/$rel")" != "$want" ]; then printf 'changed %s\n' "$rel"
        fi
    done < "$manifest"
    return 0
}

# Which files did the PREVIOUS package install that this one no longer ships?
# The direction is install.ps1's Find-DroppedFiles and it is the whole design:
# asked this way the answer is exact and needs no exception list, so a file the
# user put in $CROW_HOME can never be selected -- it was never in a manifest.
manifest_dropped() {
    local prev="$1" next="$2"
    LC_ALL=C comm -23 \
        <(awk '{print $2}' "$prev" | LC_ALL=C sort -u) \
        <(awk '{print $2}' "$next" | LC_ALL=C sort -u)
}

# What this package brings that the last one did not: "<added> <changed>".
# install.ps1 reports unchanged / changed / new / removed, and the count is what
# turns "161 files copied" into a sentence about this run rather than about the
# size of the package.
manifest_changes() {
    awk 'NR == FNR { seen[$2] = $1; next }
         { if (!($2 in seen)) added++; else if (seen[$2] != $1) changed++ }
         END { printf "%d %d\n", added + 0, changed + 0 }' "$1" "$2"
}

# --- Tailscale (--tailscale, #249 stage 5): READ, PRINT, NEVER RUN ----------
# The phone's HTTPS address is `tailscale serve` in front of the mirror's
# loopback listener. Every step that changes something needs root, and this
# script never asks for a root password (see the head of the file), so
# --tailscale only READS where this machine stands and prints the steps that
# are still missing -- in order, each one exactly once. The reading is
# crow_remote.tailscale_state, the same function the Remote dialog uses, so
# the installer and the dialog cannot disagree about which step comes next.
# Its only calls are `tailscale status --json` and `tailscale serve status
# --json`, neither of which needs sudo.
TAILSCALE_ADMIN_DNS="https://login.tailscale.com/admin/dns"
TAILSCALE_KB_LINUX="https://tailscale.com/kb/1031/install-linux"
TAILSCALE_DOWNLOAD="https://tailscale.com/download"
TAILSCALE_IOS="https://apps.apple.com/app/tailscale/id1470499037"
TAILSCALE_ANDROID="https://play.google.com/store/apps/details?id=com.tailscale.ipn"
REMOTE_PORT_DEFAULT=8765     # crow_core.REMOTE_PORT_DEFAULT

# The install line for this distribution, from an os-release file. Arch and
# everything that says it is like Arch (Omarchy, EndeavourOS, CachyOS, Manjaro)
# takes the package from `extra`; everything else takes Tailscale's own script,
# which kb/1031 names for Debian, Ubuntu, Fedora and the rest.
tailscale_install_line() {
    local ids=""
    # os-release is shell syntax by specification; read in a subshell so its
    # variables never reach this script.
    [ -f "$1" ] && ids="$( (. "$1" >/dev/null 2>&1; printf '%s %s' "${ID:-}" "${ID_LIKE:-}") )"
    case " $ids " in
        *" arch "*) printf 'sudo pacman -S tailscale\n' ;;
        *)          printf 'curl -fsSL https://tailscale.com/install.sh | sh\n' ;;
    esac
}

# remote_port out of settings.json, with crow_gui.remote_port_setting's rule:
# an int in 1024-65535 (not a bool), else the default.
remote_port_of() {
    local port=""
    if [ -n "$PY" ] && [ -f "$1" ]; then
        port="$("$PY" - "$1" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    v = json.load(open(sys.argv[1], encoding="utf-8")).get("remote_port")
except Exception:
    v = None
ok = isinstance(v, int) and not isinstance(v, bool) and 1024 <= v <= 65535
print(v if ok else "")
PYEOF
)"
    fi
    printf '%s\n' "${port:-$REMOTE_PORT_DEFAULT}"
}

# "<state> <name> <phone>" -- the state is crow_remote.tailscale_state's
# (missing, down, https-off, serve-missing, funnel, ready), <name> the ts.net
# name or "-", <phone> 1 when an iOS or Android device is already in the
# tailnet. Without python or the module: "missing - 0" when there is no
# tailscale on PATH, else "unknown - 0", which prints every step after the
# install.
tailscale_probe() {
    local cli="$1" port="$2"
    local fallback="unknown - 0"
    command -v tailscale >/dev/null 2>&1 || fallback="missing - 0"
    [ -n "$PY" ] && [ -f "$cli/crow_remote.py" ] || { printf '%s\n' "$fallback"; return 0; }
    "$PY" - "$cli" "$port" <<'PYEOF' 2>/dev/null || printf '%s\n' "$fallback"
import json, sys
sys.path.insert(0, sys.argv[1])
import crow_remote
seen = {}
def run(argv):
    code, out = crow_remote._tailscale_run(argv)
    if argv[1:] == ["status", "--json"] and code == 0:
        seen["status"] = out
    return code, out
st = crow_remote.tailscale_state(int(sys.argv[2]), run=run)
phone = 0
try:
    peers = (json.loads(seen.get("status") or "{}").get("Peer") or {}).values()
    phone = int(any(str(p.get("OS", "")).lower() in ("ios", "android") for p in peers))
except Exception:
    pass
print(st["state"], st["name"] or "-", phone)
PYEOF
}

# The steps still missing, one `cmd`/`note` per line, for a state. Pure: the
# state, the install line, the port, the name and the phone bit in, text out.
tailscale_steps() {
    local state="$1" install="$2" port="$3" name="$4" phone="$5" n=0
    local serve="sudo tailscale serve --bg --https=443 http://127.0.0.1:$port"
    say() { n=$((n + 1)); printf '  %d. %s\n' "$n" "$1"; }
    case "$state" in
        missing)
            say "install Tailscale ($TAILSCALE_KB_LINUX):"
            cmd "$install" ;;
    esac
    case "$state" in
        missing|down|unknown)
            say "start the daemon at every boot, then log in (prints a login URL):"
            cmd "sudo systemctl enable --now tailscaled"
            cmd "sudo tailscale up" ;;
    esac
    case "$state" in
        missing|down|unknown|https-off)
            say "admin console -> DNS -> HTTPS Certificates -> Enable HTTPS:"
            cmd "$TAILSCALE_ADMIN_DNS" ;;
    esac
    case "$state" in
        missing|down|unknown|https-off|serve-missing)
            say "the one-time serve command (survives reboots, renews its certificate):"
            cmd "$serve" ;;
        funnel)
            say "Funnel is on for $name:443 -- public on the internet. Crow refuses it; turn it off:"
            cmd "sudo tailscale funnel --https=443 off" ;;
    esac
    if [ "$phone" != 1 ]; then
        say "the phone: install Tailscale, log in with the SAME account:"
        cmd "iPhone   $TAILSCALE_IOS"
        cmd "Android  $TAILSCALE_ANDROID"
    fi
    if [ "$state" = ready ]; then
        say "done: in Crow, /remote on -> Remote dialog -> HTTPS, then scan the QR:"
        cmd "https://$name/"
    else
        say "then in Crow: /remote on -> Remote dialog -> HTTPS, then scan the QR"
    fi
}

tailscale_screen() {
    local cli="$1" port probe state name phone
    port="$(remote_port_of "${XDG_CONFIG_HOME:-$HOME/.config}/crow/settings.json")"
    probe="$(tailscale_probe "$cli" "$port")"
    read -r state name phone <<< "$probe"
    printf '\n  %sTailscale -- the phone from anywhere, over HTTPS%s (--tailscale)\n' "$B" "$Z"
    case "$state" in
        missing)       note "tailscale is not installed" ;;
        down)          note "tailscale is installed but not running or not logged in" ;;
        https-off)     note "logged in as $name; HTTPS certificates are off for this tailnet" ;;
        serve-missing) note "logged in as $name, HTTPS on; nothing serves :443 -> 127.0.0.1:$port yet" ;;
        funnel)        note "logged in as $name; Funnel is on for :443" ;;
        ready)         note "ready: https://$name/ -> 127.0.0.1:$port" ;;
        *)             note "state not readable here; the full list follows" ;;
    esac
    note "this script never runs sudo -- the lines below are yours to type:"
    printf '\n'
    tailscale_steps "$state" "$(tailscale_install_line /etc/os-release)" "$port" "$name" "$phone"
    printf '\n'
    note "all platforms: $TAILSCALE_DOWNLOAD"
    note "the whole setup: https://github.com/$REPO_SLUG/blob/main/docs/user-guide/remote-tailscale.md"
}

# ---------------------------------------------------------------------------
# Selftest -- checks that must pass and checks that must fail. Downloads
# nothing, writes only into its own temp directory.
# ---------------------------------------------------------------------------
selftest() {
    local pass=0 fail=0 tmp
    check() {  # check <description> <verdict 0|1> [detail]
        if [ "$2" -eq 0 ]; then pass=$((pass + 1)); printf '  %sOK%s      %s\n' "$G" "$Z" "$1"
        else fail=$((fail + 1)); printf '  %sFAILED%s  %s\n      %s\n' "$R" "$Z" "$1" "${3:-}"; fi
    }
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN

    printf '%sinstall.sh selftest%s\n\n' "$B" "$Z"

    # 1-2. The version literal. The regex has to find the real one and has to
    # find nothing in a file that does not declare one -- a regex that answers
    # something for every input would silently tag a release "".
    printf 'VERSION = "9.9.9"\n' > "$tmp/crow.py"
    local v; v="$(version_from_crow_py "$tmp/crow.py")"
    check "the version regex reads the literal out of cli/crow.py" \
          "$([ "$v" = "9.9.9" ] && echo 0 || echo 1)" "got '$v'"
    printf '# no version here\nVERSIONS = ["1.2.3"]\n' > "$tmp/noversion.py"
    v="$(version_from_crow_py "$tmp/noversion.py")"
    check "NEGATIVE: a file without the literal yields nothing, not a guess" \
          "$([ -z "$v" ] && echo 0 || echo 1)" "got '$v'"
    # And against the real file, which is the one that matters.
    if [ -n "$REPO" ]; then
        v="$(version_from_crow_py "$REPO/cli/crow.py")"
        check "the regex finds this repository's own version ($v)" \
              "$(printf '%s' "$v" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' && echo 0 || echo 1)" \
              "got '$v'"
    fi

    # 3-4. The source URL. A release ref is a tag, anything else is a branch.
    check "a release ref resolves to the tag tarball" \
          "$([ "$(tarball_url 2.1.0)" = "https://github.com/$REPO_SLUG/archive/refs/tags/v2.1.0.tar.gz" ] && echo 0 || echo 1)" \
          "$(tarball_url 2.1.0)"
    check "a branch ref resolves to the branch tarball" \
          "$([ "$(tarball_url linux)" = "https://github.com/$REPO_SLUG/archive/refs/heads/linux.tar.gz" ] && echo 0 || echo 1)" \
          "$(tarball_url linux)"

    # 5-7. The preflight verdicts, each driven over its own boundary.
    check "VRAM: 8 GB refused, 24 GB warned, 32 GB accepted" \
          "$([ "$(vram_verdict 8000)" = fail ] && [ "$(vram_verdict 24000)" = warn ] \
             && [ "$(vram_verdict 32607)" = ok ] && echo 0 || echo 1)" \
          "$(vram_verdict 8000)/$(vram_verdict 24000)/$(vram_verdict 32607)"
    check "RAM: 62 GB is fine, 48 GB warns" \
          "$([ "$(ram_verdict 62)" = ok ] && [ "$(ram_verdict 48)" = warn ] && echo 0 || echo 1)" \
          "$(ram_verdict 62)/$(ram_verdict 48)"
    check "disk: 1 GB refused, 20 GB warned, 200 GB accepted" \
          "$([ "$(disk_verdict 1)" = fail ] && [ "$(disk_verdict 20)" = warn ] \
             && [ "$(disk_verdict 200)" = ok ] && echo 0 || echo 1)" \
          "$(disk_verdict 1)/$(disk_verdict 20)/$(disk_verdict 200)"

    # 8-9. The desktop substitution, both ways.
    printf '[Desktop Entry]\nExec=@CROW_LAUNCHER@\nIcon=crow\n' > "$tmp/t.desktop"
    local out; out="$(desktop_substitute "$tmp/t.desktop" "/opt/x y/crow")"
    check "the .desktop template takes the launcher path" \
          "$(printf '%s' "$out" | grep -qxF 'Exec=/opt/x y/crow' && echo 0 || echo 1)" "$out"
    # DIE DREI ZEICHEN, DIE EINE ERSETZUNG SIND UND KEIN PFAD. Solange die
    # Substitution ueber sed lief, war jedes davon ein anderer Fehler: `&` wurde
    # zum ganzen Treffer, `\` verschwand, `|` beendete den Ausdruck und liess
    # eine LEERE crow.desktop zurueck. Alle drei kommen ueber `--to` herein.
    out="$(desktop_substitute "$tmp/t.desktop" '/opt/a&b|c\d/crow')"
    check "a launcher path with & | and a backslash survives whole" \
          "$(printf '%s' "$out" | grep -qxF 'Exec=/opt/a&b|c\d/crow' && echo 0 || echo 1)" "$out"
    printf '[Desktop Entry]\nExec=/usr/bin/crow\n' > "$tmp/bad.desktop"
    check "NEGATIVE: a template that lost @CROW_LAUNCHER@ is refused, not shipped" \
          "$(desktop_substitute "$tmp/bad.desktop" /x >/dev/null 2>&1 && echo 1 || echo 0)"

    # A path the user names may not exist yet, and that must not change it.
    check "an absolute path survives, a relative one is anchored, ~ is expanded" \
          "$([ "$(abspath /does/not/exist/models)" = "/does/not/exist/models" ] \
             && [ "$(abspath "~/m")" = "$HOME/m" ] \
             && [ "$(abspath m)" = "$PWD/m" ] && echo 0 || echo 1)" \
          "$(abspath /does/not/exist/models) | $(abspath "~/m") | $(abspath m)"

    # 10-13. The sha256 manifest, round-tripped in a temp tree: it has to be
    # silent about an untouched install, and it has to name a file that was
    # edited, a file that was deleted, and a file the new payload dropped.
    # Silence is the interesting half -- a manifest that reports drift on a
    # clean install is one nobody reads by the third run.
    mkdir -p "$tmp/src/cli" "$tmp/src/tools/archive/2026-08" "$tmp/dst"
    printf 'print(1)\n' > "$tmp/src/cli/crow.py"
    printf 'print(2)\n' > "$tmp/src/cli/crow_gui.py"
    printf 'x\n'        > "$tmp/src/LICENSE"
    printf 'print(3)\n' > "$tmp/src/cli/test_crow.py"      # must not ship
    printf 'x\n'        > "$tmp/src/tools/start-server.py" # must ship
    printf 'x\n'        > "$tmp/src/tools/archive/2026-08/measure-vram.ps1"  # must not
    ( cd "$tmp/src" && tar cf - . ) | ( cd "$tmp/dst" && tar xf - )
    rm -f "$tmp/dst/cli/test_crow.py" "$tmp/dst/tools/archive/2026-08/measure-vram.ps1"
    # A MODEL TREE IS NOT PAYLOAD, in either direction: 73 GiB must never be
    # sha256'd into manifest.sha256 on the way in, and the link at
    # <install>/models must not read as drift on the way back out. Both hold
    # because payload_paths names four directories and models is not one of
    # them, and manifest_audit asks only about the paths the manifest lists --
    # but an install that reports drift on every re-run is one nobody reads by
    # the third run, so it is checked rather than reasoned about.
    mkdir -p "$tmp/src/models" "$tmp/tree"
    printf 'gguf\n' > "$tmp/src/models/m.gguf"
    ln -sfn "$tmp/tree" "$tmp/dst/models"
    manifest_of "$tmp/src" > "$tmp/dst/manifest.sha256"
    check "the manifest is silent about an install nobody touched" \
          "$([ -z "$(manifest_audit "$tmp/dst" "$tmp/dst/manifest.sha256")" ] && echo 0 || echo 1)" \
          "$(manifest_audit "$tmp/dst" "$tmp/dst/manifest.sha256")"
    check "test_*.py is not in the payload" \
          "$(grep -q 'test_crow.py' "$tmp/dst/manifest.sha256" && echo 1 || echo 0)"
    check "NEGATIVE: a models/ tree in the source is not in the payload either" \
          "$(grep -q ' models/' "$tmp/dst/manifest.sha256" && echo 1 || echo 0)" \
          "$(grep ' models/' "$tmp/dst/manifest.sha256" || true)"
    check "the models link in an install is not drift on the next run" \
          "$([ -L "$tmp/dst/models" ] \
             && [ -z "$(manifest_audit "$tmp/dst" "$tmp/dst/manifest.sha256")" ] && echo 0 || echo 1)" \
          "$(manifest_audit "$tmp/dst" "$tmp/dst/manifest.sha256")"
    # THE LAB DOES NOT SHIP, and the positive half is the half that matters: a
    # `find tools` that excluded too much would pass an "archive is absent" check
    # by shipping no tools at all.
    check "tools/archive is not in the payload, and the rest of tools/ is" \
          "$(grep -q 'tools/archive/' "$tmp/dst/manifest.sha256" && echo 1 \
             || { grep -q ' tools/start-server.py$' "$tmp/dst/manifest.sha256" && echo 0 || echo 1; })" \
          "$(grep ' tools/' "$tmp/dst/manifest.sha256" | sed 's/^.*  //' | tr '\n' ' ')"
    printf 'print(99)\n' > "$tmp/dst/cli/crow_gui.py"
    rm -f "$tmp/dst/LICENSE"
    out="$(manifest_audit "$tmp/dst" "$tmp/dst/manifest.sha256")"
    check "an edited file reads 'changed' and a deleted one 'missing'" \
          "$(printf '%s' "$out" | grep -q '^changed cli/crow_gui.py$' \
             && printf '%s' "$out" | grep -q '^missing LICENSE$' && echo 0 || echo 1)" "$out"
    rm -f "$tmp/src/cli/crow_gui.py"
    manifest_of "$tmp/src" > "$tmp/next.sha256"
    out="$(manifest_dropped "$tmp/dst/manifest.sha256" "$tmp/next.sha256")"
    check "a file the new payload no longer ships is reported dropped" \
          "$([ "$out" = "cli/crow_gui.py" ] && echo 0 || echo 1)" "$out"

    out="$(manifest_changes "$tmp/dst/manifest.sha256" "$tmp/next.sha256")"
    check "a package that dropped one file and changed none reads '0 0'" \
          "$([ "$out" = "0 0" ] && echo 0 || echo 1)" "$out"
    printf 'print(4)\n' > "$tmp/src/cli/crow.py"
    printf 'new\n'      > "$tmp/src/cli/crow_extra.py"
    manifest_of "$tmp/src" > "$tmp/next2.sha256"
    out="$(manifest_changes "$tmp/dst/manifest.sha256" "$tmp/next2.sha256")"
    check "one new file and one edited file read '1 1'" \
          "$([ "$out" = "1 1" ] && echo 0 || echo 1)" "$out"

    # The model root, driven through the real link_models over the three things
    # that can be sitting at $CROW_HOME/models. These are locals and the globals
    # of a run are untouched: nothing here is installed anywhere.
    local CROW_HOME MODELS_DIR LAUNCHER
    CROW_HOME="$tmp/home"; MODELS_DIR="$tmp/tree"; LAUNCHER="$CROW_HOME/bin/crow"
    mkdir -p "$CROW_HOME"
    link_models >/dev/null 2>&1
    check "the model root is a link at <install>/models, which every entry point reads" \
          "$([ -L "$CROW_HOME/models" ] && [ "$(readlink "$CROW_HOME/models")" = "$tmp/tree" ] \
             && echo 0 || echo 1)" "$(ls -ld "$CROW_HOME/models" 2>&1)"
    # -sfn AND NOT -sf: without -n the second link lands inside the first one's
    # target and the install keeps reading the old tree.
    mkdir -p "$tmp/tree2"; MODELS_DIR="$tmp/tree2"
    link_models >/dev/null 2>&1
    check "a later --models retargets that link instead of nesting one" \
          "$([ "$(readlink "$CROW_HOME/models")" = "$tmp/tree2" ] \
             && [ ! -e "$tmp/tree/tree2" ] && echo 0 || echo 1)" \
          "$(readlink "$CROW_HOME/models") | $(ls -A "$tmp/tree")"
    rm -f "$CROW_HOME/models"
    mkdir -p "$CROW_HOME/models"; printf 'gguf\n' > "$CROW_HOME/models/m.gguf"
    out="$(link_models 2>&1)"
    check "NEGATIVE: a real <install>/models with files in it is kept, and the line printed" \
          "$([ ! -L "$CROW_HOME/models" ] && [ -f "$CROW_HOME/models/m.gguf" ] \
             && printf '%s' "$out" | grep -q 'ln -s' && echo 0 || echo 1)" "$out"

    # $CROW_HOME/env: the file this script used to write is removed, because
    # left behind it is a second model root that only the launcher can see.
    printf '# Sourced by %s before the window starts. Written by install.sh.\n' "$LAUNCHER" > "$CROW_HOME/env"
    printf '# Change the model root here, or re-run install.sh --models DIR.\n' >> "$CROW_HOME/env"
    printf 'export CROW_MODELS="%s"\n' "$tmp/tree" >> "$CROW_HOME/env"
    drop_installer_env >/dev/null 2>&1
    check "the \$CROW_HOME/env this installer wrote is removed" \
          "$([ ! -e "$CROW_HOME/env" ] && echo 0 || echo 1)"
    printf '# Sourced by %s before the window starts. Written by install.sh.\n' "$LAUNCHER" > "$CROW_HOME/env"
    printf '# Change the model root here, or re-run install.sh --models DIR.\n' >> "$CROW_HOME/env"
    printf 'export CROW_MODELS="%s"\nexport MY_OWN_KEY=hunter2\n' "$tmp/tree" >> "$CROW_HOME/env"
    out="$(drop_installer_env 2>&1)"
    check "NEGATIVE: an env file with a line of the user's own is kept, and named" \
          "$([ -f "$CROW_HOME/env" ] && grep -q MY_OWN_KEY "$CROW_HOME/env" \
             && printf '%s' "$out" | grep -q 'left alone' && echo 0 || echo 1)" "$out"

    # --tailscale (#249 stage 5). The distro line, the port, and the probe
    # against a FAKE `tailscale` on a PATH that holds nothing else -- the real
    # CLI is never called from here, and neither is sudo. The fake logs every
    # argv it is given, so "reads only" is checked rather than claimed.
    printf 'ID=arch\n' > "$tmp/os-arch"
    printf 'ID=cachyos\nID_LIKE=arch\n' > "$tmp/os-cachy"
    printf 'ID=ubuntu\nID_LIKE=debian\n' > "$tmp/os-ubuntu"
    printf 'ID=fedora\n' > "$tmp/os-fedora"
    check "tailscale install line: Arch and Arch-likes use pacman" \
          "$([ "$(tailscale_install_line "$tmp/os-arch")" = "sudo pacman -S tailscale" ] \
             && [ "$(tailscale_install_line "$tmp/os-cachy")" = "sudo pacman -S tailscale" ] && echo 0 || echo 1)" \
          "$(tailscale_install_line "$tmp/os-arch") | $(tailscale_install_line "$tmp/os-cachy")"
    check "tailscale install line: Debian/Ubuntu/Fedora and unknown use kb/1031's script" \
          "$(for f in os-ubuntu os-fedora os-none; do
                 [ "$(tailscale_install_line "$tmp/$f")" = "curl -fsSL https://tailscale.com/install.sh | sh" ] || { echo 1; exit; }
             done; echo 0)" "$(tailscale_install_line "$tmp/os-ubuntu")"
    printf '{"remote_port": 9123}\n' > "$tmp/s-port.json"
    printf '{"remote_port": true}\n' > "$tmp/s-bool.json"
    printf '{"remote_port": 80}\n'   > "$tmp/s-low.json"
    check "remote_port is read from settings.json; bool, <1024 and no file fall back to 8765" \
          "$([ "$(remote_port_of "$tmp/s-port.json")" = 9123 ] && [ "$(remote_port_of "$tmp/s-bool.json")" = 8765 ] \
             && [ "$(remote_port_of "$tmp/s-low.json")" = 8765 ] && [ "$(remote_port_of "$tmp/none.json")" = 8765 ] \
             && echo 0 || echo 1)" \
          "$(remote_port_of "$tmp/s-port.json")/$(remote_port_of "$tmp/s-bool.json")/$(remote_port_of "$tmp/s-low.json")"

    if [ -n "$REPO" ] && [ -n "$PY" ]; then
        mkdir -p "$tmp/ts/bin" "$tmp/ts/empty"
        # #!/bin/sh and absolute paths: the fake runs with only its own
        # directory on PATH.
        cat > "$tmp/ts/bin/tailscale" <<'FAKE'
#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_TS/argv.log"
case "$*" in
    "status --json")       [ -f "$FAKE_TS/status.json" ] || exit 1; exec /bin/cat "$FAKE_TS/status.json" ;;
    "serve status --json") [ -f "$FAKE_TS/serve.json" ]  || exit 1; exec /bin/cat "$FAKE_TS/serve.json" ;;
esac
exit 99
FAKE
        chmod +x "$tmp/ts/bin/tailscale"
        local name="pc.tail1234.ts.net" probe
        ts_probe() { FAKE_TS="$tmp/ts" PATH="$1" tailscale_probe "$REPO/cli" 8765; }

        probe="$(ts_probe "$tmp/ts/empty")"
        check "tailscale probe: nothing on PATH reads 'missing'" \
              "$([ "$probe" = "missing - 0" ] && echo 0 || echo 1)" "$probe"
        rm -f "$tmp/ts/status.json" "$tmp/ts/serve.json"
        probe="$(ts_probe "$tmp/ts/bin")"
        check "tailscale probe: a daemon that answers nothing reads 'down'" \
              "$([ "$probe" = "down - 0" ] && echo 0 || echo 1)" "$probe"
        printf '{"BackendState":"Running","Self":{"DNSName":"%s.","TailscaleIPs":["100.64.0.1"]},"CertDomains":[],"Peer":{}}\n' \
               "$name" > "$tmp/ts/status.json"
        probe="$(ts_probe "$tmp/ts/bin")"
        check "tailscale probe: logged in without CertDomains reads 'https-off'" \
              "$([ "$probe" = "https-off $name 0" ] && echo 0 || echo 1)" "$probe"
        printf '{"BackendState":"Running","Self":{"DNSName":"%s.","TailscaleIPs":["100.64.0.1"]},"CertDomains":["%s"],"Peer":{"k":{"OS":"iOS"}}}\n' \
               "$name" "$name" > "$tmp/ts/status.json"
        printf '{}\n' > "$tmp/ts/serve.json"
        probe="$(ts_probe "$tmp/ts/bin")"
        check "tailscale probe: HTTPS on, no serve reads 'serve-missing', and sees the iPhone" \
              "$([ "$probe" = "serve-missing $name 1" ] && echo 0 || echo 1)" "$probe"
        printf '{"Web":{"%s:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8765"}}}}}\n' "$name" > "$tmp/ts/serve.json"
        probe="$(ts_probe "$tmp/ts/bin")"
        check "tailscale probe: serve pointing at 127.0.0.1:8765 reads 'ready'" \
              "$([ "$probe" = "ready $name 1" ] && echo 0 || echo 1)" "$probe"
        check "NEGATIVE: the probe ran nothing but 'status --json' and 'serve status --json'" \
              "$(sort -u "$tmp/ts/argv.log" | grep -vxE 'status --json|serve status --json' >/dev/null && echo 1 || echo 0)" \
              "$(sort -u "$tmp/ts/argv.log" | tr '\n' ';')"
    fi

    out="$(tailscale_steps missing "sudo pacman -S tailscale" 8765 - 0)"
    check "tailscale steps from 'missing': install, daemon, login, HTTPS, serve, phone, in that order" \
          "$(printf '%s' "$out" | awk '
               /sudo pacman -S tailscale/ && !a {a=NR} /systemctl enable --now tailscaled/ && !b {b=NR}
               /sudo tailscale up/ && !c {c=NR} /admin\/dns/ && !d {d=NR}
               /tailscale serve --bg --https=443 http:\/\/127.0.0.1:8765/ && !e {e=NR} /id1470499037/ && !f {f=NR}
               END { exit !(a && a<b && b<c && c<d && d<e && e<f) }' && echo 0 || echo 1)" "$out"
    out="$(tailscale_steps serve-missing "x" 9123 pc.t.ts.net 1)"
    check "tailscale steps from 'serve-missing': only serve, on the configured port" \
          "$(printf '%s' "$out" | grep -q 'http://127.0.0.1:9123' \
             && ! printf '%s' "$out" | grep -qE 'tailscale up|systemctl|admin/dns|pacman|apps.apple' && echo 0 || echo 1)" "$out"
    out="$(tailscale_steps ready "x" 8765 pc.t.ts.net 1)"
    check "NEGATIVE: 'ready' with a phone prints no command to type, only the address" \
          "$(printf '%s' "$out" | grep -q 'sudo' && echo 1 \
             || { printf '%s' "$out" | grep -q 'https://pc.t.ts.net/' && echo 0 || echo 1; })" "$out"
    [ -n "$REPO" ] && check "NEGATIVE: the --tailscale code path never runs sudo, it only prints it" \
          "$(sed -n '/^tailscale_install_line()/,/^# ---.*$/p' "$REPO/install.sh" \
             | grep -vE '^\s*#|printf|cmd |note |serve=|say ' | grep -q 'sudo' && echo 1 || echo 0)"

    # --pathtracer (#298): the kit verdict both ways, the switch reader,
    # and the enable path end to end against a throwaway config directory.
    mkdir -p "$tmp/kit"
    printf 'export const x = 1;\n' > "$tmp/kit/crow-pathtracer.js"
    printf '{\n  "bundle": {\n    "sha256": "%s"\n  },\n  "license_sha256": {\n    "LICENSE.x": "00"\n  }\n}\n' \
        "$(sha_of "$tmp/kit/crow-pathtracer.js")" > "$tmp/kit/kit.json"
    check "pathtracer: a kit whose bundle matches kit.json is 'ok'" \
          "$([ "$(pathtracer_kit_verdict "$tmp/kit")" = ok ] && echo 0 || echo 1)" "$(pathtracer_kit_verdict "$tmp/kit")"
    printf 'export const x = 2;\n' > "$tmp/kit/crow-pathtracer.js"
    check "NEGATIVE: pathtracer: one changed byte in the bundle is 'corrupt'" \
          "$([ "$(pathtracer_kit_verdict "$tmp/kit")" = corrupt ] && echo 0 || echo 1)" "$(pathtracer_kit_verdict "$tmp/kit")"
    check "NEGATIVE: pathtracer: no kit is 'missing'" \
          "$([ "$(pathtracer_kit_verdict "$tmp/nokit")" = missing ] && echo 0 || echo 1)"
    if [ -n "$REPO" ]; then
        check "pathtracer: this repository's kit matches its kit.json" \
              "$([ "$(pathtracer_kit_verdict "$REPO/kits/pathtracer")" = ok ] && echo 0 || echo 1)" \
              "$(pathtracer_kit_verdict "$REPO/kits/pathtracer")"
        check "pathtracer: the payload ships the kit and its licences" \
              "$(payload_paths "$REPO" | grep -qx 'kits/pathtracer/crow-pathtracer.js' \
                 && payload_paths "$REPO" | grep -qx 'kits/pathtracer/LICENSE.three-gpu-pathtracer' && echo 0 || echo 1)"
        check "pathtracer: --help lists --pathtracer" \
              "$(sed -n '/^# USAGE/,/^# ---/p' "$REPO/install.sh" | grep -q -- '--pathtracer' && echo 0 || echo 1)"
    fi
    printf -- '---\nname: voxel-diorama\nenabled: false\n---\nx\n' > "$tmp/off.md"
    printf -- '---\nname: voxel-diorama\nenabled: true\n---\nx\n' > "$tmp/on.md"
    check "pathtracer: the skill switch reads on / off / absent" \
          "$([ "$(kit_skill_state "$tmp/on.md")" = on ] && [ "$(kit_skill_state "$tmp/off.md")" = off ] \
             && [ "$(kit_skill_state "$tmp/none.md")" = absent ] && echo 0 || echo 1)"
    if [ -n "$REPO" ] && [ -n "$PY" ]; then
        local first second
        first="$(XDG_CONFIG_HOME="$tmp/cfg" XDG_STATE_HOME="$tmp/state" XDG_CACHE_HOME="$tmp/cache" \
                 XDG_DATA_HOME="$tmp/data" enable_kit_skill "$PY" "$REPO/cli")"
        second="$(XDG_CONFIG_HOME="$tmp/cfg" XDG_STATE_HOME="$tmp/state" XDG_CACHE_HOME="$tmp/cache" \
                  XDG_DATA_HOME="$tmp/data" enable_kit_skill "$PY" "$REPO/cli")"
        check "pathtracer: the opt-in switches the skill on, a second run says 'already'" \
              "$([ "$first" = enabled ] && [ "$second" = already ] \
                 && [ "$(kit_skill_state "$tmp/cfg/crow/skills/voxel-diorama/SKILL.md")" = on ] \
                 && [ -f "$tmp/cfg/crow/skills/skill-creator/SKILL.md" ] && echo 0 || echo 1)" \
              "first '$first', second '$second'"
    fi

    printf '\n%s%d checks, %d failed%s\n' "$B" "$((pass + fail))" "$fail" "$Z"
    [ "$fail" -eq 0 ] || return 1
    printf 'RESULT: PASS\n'
}

# ---------------------------------------------------------------------------
# 1 -- the machine
# ---------------------------------------------------------------------------
preflight() {
    step "Checking this machine"
    local problems=0

    # Python. BOTH clients need it; the terminal one needs nothing else.
    if [ -z "$PY" ]; then
        bad "no python3 on the PATH. Both clients are Python"
        problems=$((problems + 1))
    else
        local pv; pv="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
        if [ "$("$PY" -c 'import sys;print(int(sys.version_info[:2]>=(3,9)))')" = 1 ]; then
            ok "python $pv at $PY"
        else
            bad "python $pv, and $PY_MIN or newer is required"
            problems=$((problems + 1))
        fi
        if "$PY" -c 'import venv' 2>/dev/null; then
            ok "venv module present"
        else
            bad "python has no venv module (Debian/Ubuntu: python3-venv)"
            problems=$((problems + 1))
        fi
    fi

    # The window's half of the promise, and it is a WARNING rather than a
    # refusal for install.ps1's reason: a missing runtime costs one client, not
    # the install. The terminal client runs on the standard library alone.
    #
    # WE CANNOT INSTALL IT AND DO NOT PRETEND TO. PyGObject is not a wheel that
    # pip can build here without the GObject headers, and the headers come from
    # the distribution. So the line is printed; typing it is the user's.
    if [ -n "$PY" ] && "$PY" - <<'EOF' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2  # noqa: F401
EOF
    then
        ok "PyGObject with Gtk 3.0 and WebKit2 4.1 -- the window can render"
    else
        warn "no PyGObject / Gtk 3.0 / WebKit2 4.1. cli/crow.py runs in a terminal without"
        note "them; cli/crow_gui.py is the window and renders in WebKitGTK. Install them"
        note "with your package manager -- this script never asks for a root password:"
        cmd "$PACMAN_LINE"
    fi

    # Clipboard. crow_platform reaches for wl-paste/wl-copy first and falls back
    # to xclip under X11; without either, pasting an image into the window is
    # the one thing that stops working.
    if command -v wl-paste >/dev/null 2>&1; then ok "wl-clipboard ($(command -v wl-paste))"
    elif command -v xclip >/dev/null 2>&1;   then warn "no wl-clipboard; xclip found -- fine under X11, not under Wayland"
    else warn "no wl-clipboard and no xclip: pasting an image into the window will not work"
    fi

    # The optional helpers, install.ps1's Node row and its two Linux siblings.
    # None of them blocks: each costs one feature, and each feature says so
    # itself when it runs without it.
    #   node        -- MCP servers started with npx/node; write_file/append_file
    #                  run `node --check` over JS and inline HTML scripts (#251)
    #                  and SKIP the check without node; build_bundle finds
    #                  esbuild in the npx cache or node_modules (#212).
    #   bwrap       -- the in-window browser panel's web process runs sandboxed
    #                  only when bwrap exists (#226); without it, no sandbox.
    #   systemd-run -- the render browser and run_command get a user scope with
    #                  a memory ceiling (#213, #218); without a reachable user
    #                  manager they run unscoped.
    if command -v node >/dev/null 2>&1; then ok "node ($(command -v node)) -- MCP via npx, the JS syntax check, build_bundle"
    else warn "no node: MCP servers via npx, write_file's JS syntax check (#251) and build_bundle's npx esbuild are unavailable"
    fi
    if command -v bwrap >/dev/null 2>&1; then ok "bwrap -- the browser panel runs sandboxed"
    else warn "no bwrap: the browser panel runs without a sandbox (bubblewrap package)"
    fi
    if command -v systemd-run >/dev/null 2>&1; then ok "systemd-run -- render_page and run_command get a memory ceiling"
    else warn "no systemd-run: render_page and run_command run without a memory ceiling"
    fi

    # The card. This one CAN refuse the machine, and it is asked before a byte
    # is downloaded.
    if command -v nvidia-smi >/dev/null 2>&1; then
        local line name vram
        line="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 || true)"
        name="${line%%,*}"; vram="${line##*,}"; vram="${vram// /}"
        case "$vram" in ''|*[!0-9]*) vram=0 ;; esac
        VRAM_MB="$vram"
        case "$(vram_verdict "$vram")" in
            fail) bad "$name, $vram MB of VRAM -- below the $VRAM_SUPPORTED_MB MB minimum. Operation below that was never measured"
                  problems=$((problems + 1)) ;;
            warn) warn "$name, $vram MB of VRAM. The measured profile is $VRAM_TARGET_MB MB; expect fewer slots and less throughput" ;;
            ok)   ok "$name, $vram MB of VRAM" ;;
        esac
    else
        bad "no nvidia-smi on the PATH. Crow runs its experts on CUDA"
        problems=$((problems + 1))
    fi

    # RAM. -ncmoe 31 (30 on Windows) keeps the experts of 31 of 48 layers in system memory, so
    # this is not a comfort figure; it is where the operating point lives.
    local ramgb; ramgb="$(awk '/^MemTotal:/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)"
    if [ "$(ram_verdict "$ramgb")" = ok ]; then ok "$ramgb GB of system RAM"
    else warn "$ramgb GB of system RAM. Flash-Next wants 64; below 60 nothing has been run"; fi

    # Disk, on the filesystem the install will land on.
    local target diskgb
    target="$CROW_HOME"; while [ ! -d "$target" ] && [ "$target" != "/" ]; do target="$(dirname "$target")"; done
    diskgb="$(df -Pk "$target" | awk 'NR==2 {printf "%d", $4/1024/1024}')"
    case "$(disk_verdict "$diskgb")" in
        fail) bad "$diskgb GB free on $target, $DISK_INSTALL_GB GB needed for the package"
              problems=$((problems + 1)) ;;
        warn) warn "$diskgb GB free on $target. The package fits; the model needs about $DISK_MODEL_GB GB more" ;;
        ok)   ok "$diskgb GB free on $target" ;;
    esac

    # The engine is a build here, not a download, and the build needs a compiler.
    if command -v cc >/dev/null 2>&1 || command -v gcc >/dev/null 2>&1; then
        ok "a C compiler for tools/build-llama-server.sh"
    else
        warn "no cc/gcc: tools/build-llama-server.sh cannot build the CUDA engine here"
    fi

    [ "$problems" -eq 0 ] || die "$problems thing(s) above have to be fixed first. Nothing was installed."
}

# ---------------------------------------------------------------------------
# 2 -- the source: this checkout, or the tarball of a ref
# ---------------------------------------------------------------------------
resolve_source() {
    step "Getting the files"
    if [ -n "$REPO" ]; then
        SOURCE="$REPO"
        SOURCE_TMP=""
        VERSION="$(version_from_crow_py "$REPO/cli/crow.py")"
        ok "from this checkout: $REPO (version ${VERSION:-unknown})"
        return
    fi
    command -v curl >/dev/null 2>&1 || die "no curl, and there is no checkout to install from"
    local url; url="$(tarball_url "$CROW_REF")"
    SOURCE_TMP="$(mktemp -d)"
    ok "no checkout here -- fetching $CROW_REF"
    note "$url"
    curl -fsSL "$url" -o "$SOURCE_TMP/crow.tar.gz" \
        || die "could not download $url"
    tar -xzf "$SOURCE_TMP/crow.tar.gz" -C "$SOURCE_TMP"
    # GitHub's archive wraps everything in Crow-<ref>/.
    SOURCE="$(find "$SOURCE_TMP" -mindepth 1 -maxdepth 1 -type d | sed -n 1p)"
    [ -f "$SOURCE/cli/crow.py" ] || die "the tarball does not look like Crow: no cli/crow.py"
    VERSION="$(version_from_crow_py "$SOURCE/cli/crow.py")"
    ok "unpacked version ${VERSION:-unknown}"
}

# ---------------------------------------------------------------------------
# 3 -- the files, and a per-file sha256 that says what moved
# ---------------------------------------------------------------------------
install_payload() {
    step "Installing into $CROW_HOME"
    mkdir -p "$CROW_HOME"
    local manifest="$CROW_HOME/manifest.sha256" audit rel dropped n

    # BEFORE overwriting anything: what happened to the last install?
    if [ -f "$manifest" ]; then
        audit="$(manifest_audit "$CROW_HOME" "$manifest" || true)"
        if [ -z "$audit" ]; then
            ok "the previous install is exactly as it was left ($(wc -l < "$manifest") files)"
        else
            warn "$(printf '%s\n' "$audit" | wc -l) file(s) differ from the last install and are being replaced:"
            printf '%s\n' "$audit" | awk 'NR <= 10' | while read -r state rel; do note "$state  $rel"; done
        fi
    fi

    payload_paths "$SOURCE" > "$CROW_HOME/.manifest.paths.$$"
    n=0
    while IFS= read -r rel; do
        mkdir -p "$CROW_HOME/$(dirname "$rel")"
        cp -p "$SOURCE/$rel" "$CROW_HOME/$rel"
        n=$((n + 1))
    done < "$CROW_HOME/.manifest.paths.$$"
    rm -f "$CROW_HOME/.manifest.paths.$$"
    ok "$n files copied"

    manifest_of "$SOURCE" > "$CROW_HOME/manifest.sha256.new"
    if [ -f "$manifest" ]; then
        set -- $(manifest_changes "$manifest" "$CROW_HOME/manifest.sha256.new")
        if [ "$1" = 0 ] && [ "$2" = 0 ]; then ok "the same bytes as the last run -- nothing in the package moved"
        else ok "$1 new file(s), $2 changed since the last run"; fi
        dropped="$(manifest_dropped "$manifest" "$CROW_HOME/manifest.sha256.new" || true)"
        if [ -n "$dropped" ]; then
            printf '%s\n' "$dropped" | while IFS= read -r rel; do
                [ -n "$rel" ] && rm -f "$CROW_HOME/$rel"
            done
            ok "$(printf '%s\n' "$dropped" | wc -l) file(s) the new package no longer ships were removed"
        fi
    fi
    mv "$CROW_HOME/manifest.sha256.new" "$manifest"

    # Read back rather than trusted. install.ps1 verifies every file against the
    # package manifest after extracting, and a copy that silently truncated is
    # exactly the failure that installs cleanly and breaks at run time.
    audit="$(manifest_audit "$CROW_HOME" "$manifest" || true)"
    [ -z "$audit" ] || die "verification failed right after copying: $audit"
    ok "sha256 verified, all $n files"
}

# ---------------------------------------------------------------------------
# 4 -- the runtime: venv, engine, launcher, desktop
# ---------------------------------------------------------------------------
install_venv() {
    # --system-site-packages IS THE POINT AND NOT A CONVENIENCE. PyGObject comes
    # from the distribution (it needs the GObject headers to build), and a venv
    # that cannot see it cannot render the window at all. pywebview is installed
    # PLAIN and never as pywebview[gtk]: the extra pulls in a PyGObject wheel
    # that then shadows the system one with a build that has no typelibs.
    if [ ! -x "$CROW_HOME/venv/bin/python" ]; then
        "$PY" -m venv --system-site-packages "$CROW_HOME/venv" \
            || die "could not create the venv at $CROW_HOME/venv"
        ok "venv created at $CROW_HOME/venv"
    else
        ok "venv reused at $CROW_HOME/venv"
    fi
    "$CROW_HOME/venv/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
    if "$CROW_HOME/venv/bin/python" -m pip install --quiet --upgrade pywebview; then
        ok "pywebview $("$CROW_HOME/venv/bin/python" -m pip show pywebview 2>/dev/null | sed -n 's/^Version: //p')"
    else
        warn "pip could not install pywebview. The terminal client is unaffected:"
        cmd "$PY $CROW_HOME/cli/crow.py"
    fi
    if [ "$WITH_VOICE" = 1 ]; then
        if "$CROW_HOME/venv/bin/python" -m pip install --quiet --upgrade faster-whisper sounddevice; then
            ok "voice extra: faster-whisper + sounddevice"
            note "the dictation model (~486 MB) is fetched by the window on the first click"
        else
            warn "the voice extra did not install; everything else is fine"
        fi
    fi
}

install_engine() {
    local builder="$CROW_HOME/tools/build-llama-server.sh"
    if [ -x "$CROW_HOME/bin/llama-server" ] || [ -f "$CROW_HOME/bin/llama-server" ]; then
        ok "llama-server is already at $CROW_HOME/bin/llama-server"
        return
    fi
    if [ "$BUILD_ENGINE" = 1 ]; then
        ok "building llama-server -- this takes about 20 minutes"
        CROW_HOME="$CROW_HOME" bash "$builder" \
            || die "tools/build-llama-server.sh failed. Its output above says where."
        return
    fi
    warn "no engine at $CROW_HOME/bin/llama-server. Nothing can be served until there is one."
    note "It is built here, from llama.cpp pin 6c84c7d5d + PR #27880 + PR #28040, with a"
    note "CUDA toolkit unpacked under \$CROW_HOME -- no root, ~20 minutes, ~8 GB:"
    cmd "CROW_HOME=$CROW_HOME bash $builder"
}

# --pathtracer (#298): verify the kit, switch its skill on, say whether
# build_bundle has an esbuild to put it into a page. Without the flag: one line
# saying the kit is there and how to switch it on -- or that it already is.
install_pathtracer() {
    local kit="$CROW_HOME/kits/pathtracer" verdict state esb
    local skill="${XDG_CONFIG_HOME:-$HOME/.config}/crow/skills/voxel-diorama/SKILL.md"
    verdict="$(pathtracer_kit_verdict "$kit")"
    state="$(kit_skill_state "$skill")"
    if [ "$WITH_PATHTRACER" != 1 ]; then
        if [ "$state" = on ]; then ok "voxel kit: the voxel-diorama skill is on (kits/pathtracer, $verdict)"
        else note "voxel kit: installed, skill off -- re-run with --pathtracer to switch it on"; fi
        return 0
    fi
    case "$verdict" in
        ok)      ok "voxel kit: kits/pathtracer/crow-pathtracer.js matches kit.json" ;;
        missing) warn "voxel kit: $kit is missing -- the package did not ship it"; return 0 ;;
        *)       warn "voxel kit: the bundle does not match kit.json -- re-run install.sh"; return 0 ;;
    esac
    state="$(enable_kit_skill "$CROW_HOME/venv/bin/python" "$CROW_HOME/cli")"
    case "$state" in
        enabled) ok "voxel kit: the voxel-diorama skill is switched on" ;;
        already) ok "voxel kit: the voxel-diorama skill was already on" ;;
        *)       warn "voxel kit: could not switch the skill on (${state#!})"
                 note "switch it on by hand: the Skills page of the window's settings" ;;
    esac
    esb="$("$CROW_HOME/venv/bin/python" - "$CROW_HOME/cli" "$CROW_HOME" <<'EOF' 2>/dev/null || true
import sys
sys.path.insert(0, sys.argv[1])
import crow_core
exe, version, where, _ = crow_core.find_esbuild(sys.argv[2])
print("%s %s (%s)" % (exe, version, where) if exe else "")
EOF
)"
    if [ -n "$esb" ]; then ok "voxel kit: build_bundle has an esbuild: $esb"
    else warn "voxel kit: no esbuild on this machine -- build_bundle cannot inline the kit into a page"
         note "any esbuild works: a project's node_modules, PATH, the deno or npx cache, or"
         note "\"bundler\": \"<path>\" in ${XDG_CONFIG_HOME:-$HOME/.config}/crow/settings.json"
    fi
}

write_launcher() {
    mkdir -p "$CROW_HOME/bin"
    # The launcher is GENERATED and says so, because the one thing it decides --
    # which interpreter -- is decided at install time and a user who edits it
    # here loses the edit on the next run. IT SETS NO ENVIRONMENT AT ALL: it
    # used to source $CROW_HOME/env for $CROW_MODELS, and that is precisely how
    # the model root became a path only this one process could see.
    cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# Crow's window. Written by install.sh -- re-run install.sh rather than edit it.
# The model root is $CROW_HOME/models, a link; it is not set here.
set -euo pipefail
CROW_HOME="$CROW_HOME"
exec "\$CROW_HOME/venv/bin/python" "\$CROW_HOME/cli/crow_gui.py" "\$@"
EOF
    chmod +x "$LAUNCHER"
    ok "launcher at $LAUNCHER"

    # ~/.local/bin only if it is already on the PATH. Putting a directory on
    # somebody's PATH is editing their shell profile, and this script does not
    # edit files it did not write.
    case ":$PATH:" in
        *":$HOME/.local/bin:"*)
            mkdir -p "$HOME/.local/bin"
            # THE LAST INSTALL WINS, AND IT SAYS SO. `--to DIR` and a throwaway
            # $CROW_HOME both come through here, so `crow` would otherwise
            # silently start pointing at whichever tree was installed last --
            # the failure being a shortcut into a directory somebody deleted.
            local was=""
            [ -L "$HOME/.local/bin/crow" ] && was="$(readlink "$HOME/.local/bin/crow")"
            ln -sf "$LAUNCHER" "$HOME/.local/bin/crow"
            if [ -n "$was" ] && [ "$was" != "$LAUNCHER" ]; then
                warn "\`crow\` on your PATH now means this install"
                note "~/.local/bin/crow  $was  ->  $LAUNCHER"
            else
                ok "\`crow\` on your PATH (~/.local/bin/crow -> $LAUNCHER)"
            fi ;;
        *)
            note "~/.local/bin is not on your PATH, so no \`crow\` shortcut was made."
            note "Add it, or start the window with the full path above." ;;
    esac
}

# The model root, written where every entry point already looks: see the block
# above models_link_verdict() for why it is a link and not a variable.
link_models() {
    local link="$CROW_HOME/models" verdict was=""

    # The tree IS <install>/models -- nothing to point anywhere, and a link to
    # itself is a loop that resolves to nothing.
    if [ "$MODELS_DIR" = "$link" ]; then
        ok "model root: $link"
        [ -d "$MODELS_DIR" ] || note "it does not exist yet -- step 5 prints what to download into it"
        drop_installer_env
        return 0
    fi

    verdict="$(models_link_verdict "$link")"
    case "$verdict" in
        link)
            [ -L "$link" ] && was="$(readlink "$link")"
            # An EMPTY real directory is in the way of its own replacement --
            # `ln` will not write over a directory. rmdir and never rm -rf: if
            # anything appeared in it since the verdict, this fails and the
            # directory stays, which is the only safe direction.
            if [ ! -L "$link" ] && [ -d "$link" ]; then rmdir "$link" 2>/dev/null || true; fi
            # -n IS NOT DECORATION. Without it `ln -sf tree link` FOLLOWS the
            # existing link and writes the new one INSIDE the old target, i.e.
            # ~/Projects/models/qwen3.8-flash-next/qwen3.8-flash-next -- and the
            # install then still reads the old tree.
            ln -sfn "$MODELS_DIR" "$link" || die "could not link $link -> $MODELS_DIR"
            if [ -n "$was" ] && [ "$was" != "$MODELS_DIR" ]; then
                warn "the model root of this install moved"
                note "$link  $was  ->  $MODELS_DIR"
            else
                ok "model root: $link -> $MODELS_DIR"
            fi
            [ -d "$MODELS_DIR" ] || note "it does not exist yet -- step 5 prints what to download into it" ;;
        keep)
            # 73 GiB somebody put there. It is already the answer every entry
            # point gets, so nothing is broken -- it is simply not what --models
            # said, and the two lines that would change it are printed, not run.
            warn "$link is a real directory with files in it -- not replaced"
            note "Crow reads its models from there, whatever --models named. To point"
            note "it at $MODELS_DIR instead, move it aside and link by hand:"
            cmd "mv $link $link.old"
            cmd "ln -s $MODELS_DIR $link" ;;
        clash)
            warn "$link is a file, not a directory -- not replaced"
            note "No model resolves under it. Remove it and link the tree:"
            cmd "ln -sfn $MODELS_DIR $link" ;;
    esac
    drop_installer_env
}

# $CROW_HOME/env is not written any more, and the one an earlier run wrote is
# removed: left on disk it is a second mechanism that still works for the
# launcher ALONE, which is the bug this replaces. Only the file we wrote,
# matched line by line -- anything else is the user's and is kept and named.
drop_installer_env() {
    local envf="$CROW_HOME/env"
    [ -e "$envf" ] || return 0
    if installer_env_p "$envf"; then
        rm -f "$envf"
        ok "removed $envf -- the model root is the link, not a variable"
    else
        warn "$envf is not the file this installer wrote, so it was left alone"
        note "Nothing sources it any more -- $LAUNCHER no longer does."
        note "Whatever it exports has to move into your own shell profile."
    fi
}

install_desktop() {
    [ "$WITH_DESKTOP" = 1 ] || { note "desktop integration skipped (--no-desktop)"; return; }
    local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    local icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
    local src="$CROW_HOME/cli"

    if [ -f "$src/crow.desktop" ]; then
        mkdir -p "$apps"
        desktop_substitute "$src/crow.desktop" "$LAUNCHER" > "$apps/crow.desktop"
        chmod 644 "$apps/crow.desktop"
        ok "launcher entry at $apps/crow.desktop"
        # Captured rather than let loose: desktop-file-validate prints hints at
        # exit 0 (ours draws one for two main categories), and a hint landing
        # between two green lines reads like a failure that was ignored.
        if command -v desktop-file-validate >/dev/null 2>&1; then
            local said; said="$(desktop-file-validate "$apps/crow.desktop" 2>&1)" && {
                if [ -z "$said" ]; then ok "desktop-file-validate: clean"
                else ok "desktop-file-validate: valid, with a hint"
                     note "${said#*: }"; fi
            } || { warn "desktop-file-validate rejected the entry:"; note "$said"; }
        fi
    fi

    local n=0 size
    for size in $ICON_SIZES; do
        [ -f "$src/icons/crow-$size.png" ] || continue
        mkdir -p "$icons/${size}x${size}/apps"
        cp -p "$src/icons/crow-$size.png" "$icons/${size}x${size}/apps/crow.png"
        n=$((n + 1))
    done
    [ "$n" -gt 0 ] && ok "$n icons under $icons"
    # PNG and not SVG, and the .desktop file says why: this machine has no SVG
    # gdk-pixbuf loader, so a themed SVG icon cannot be opened at all.
    if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ "$n" -gt 0 ]; then
        if gtk-update-icon-cache -f -t "$icons" >/dev/null 2>&1; then
            ok "icon cache refreshed"
        else
            # Not a failure: a user icon directory with no index.theme has no
            # cache to refresh, and every launcher still reads the files.
            note "gtk-update-icon-cache found no theme index here -- the icons are still read"
        fi
    fi
}

install_hyprland() {
    [ "$WITH_DESKTOP" = 1 ] || return 0
    local hypr="${XDG_CONFIG_HOME:-$HOME/.config}/hypr"
    local src="$CROW_HOME/cli"
    # A FRAMELESS WINDOW WITH A HARD MINIMUM CANNOT ASK FOR ITS OWN FRAME. On
    # Wayland a client may not place, size or raise its toplevel; the rule is
    # how you talk to the compositor. See the head of cli/hyprland-crow.lua.
    #
    # THE USER'S OWN CONFIG IS NOT EDITED. One line has to be added by hand, and
    # it is printed rather than appended: a script that writes into hyprland.lua
    # is a script that has to parse it, and getting that wrong costs somebody
    # their session on the next reload.
    if [ -f "$hypr/hyprland.lua" ] && [ -f "$src/hyprland-crow.lua" ]; then
        cp -p "$src/hyprland-crow.lua" "$hypr/crow.lua"
        ok "Hyprland rule at $hypr/crow.lua (Lua config detected)"
        HYPR_LINE='require("hypr.crow")'
        HYPR_WHERE="$hypr/hyprland.lua"
    elif [ -f "$hypr/hyprland.conf" ] && [ -f "$src/hyprland-crow.conf" ]; then
        cp -p "$src/hyprland-crow.conf" "$hypr/crow.conf"
        ok "Hyprland rule at $hypr/crow.conf (ini config detected)"
        HYPR_LINE="source = $hypr/crow.conf"
        HYPR_WHERE="$hypr/hyprland.conf"
    else
        note "no Hyprland config found -- the window opens under any compositor, but"
        note "under a tiling one it will be tiled. cli/hyprland-crow.{lua,conf} has the rule."
    fi
}

# ---------------------------------------------------------------------------
# 5 -- what is left to do
# ---------------------------------------------------------------------------
# The by-hand server line is ASKED OF THE CORE, not written down here. README.md
# and install.ps1 carry copies of it and tools/check_operating_point.py holds
# both against manifests/operating-point.json; a third copy in this file would
# be a third thing to keep in step. crow_core.server_command() builds the argv
# from the manifest, so what is printed here cannot drift by construction.
# NO $CROW_MODELS IS SET FOR IT. The line printed has to be the line the window
# would run, and the window runs whatever <install>/models resolves to -- so
# letting models_dir() fall back is what makes this an end-to-end check of the
# link rather than a second opinion about it.
resolved_server_line() {
    "$CROW_HOME/venv/bin/python" - "$CROW_HOME" <<'EOF' 2>/dev/null || true
import os, shlex, sys
home = sys.argv[1]
sys.path.insert(0, os.path.join(home, "cli"))
try:
    import crow_core
    print(shlex.join(crow_core.server_command("flash-next-q2-k-xl", install=home)))
except Exception as exc:
    print("!%s" % exc)
EOF
}

final_screen() {
    step "What is left to do"
    local line

    printf '\n'
    # THE DEFAULT OPERATING POINT IS crow-nest (Rust), port 8099. It is its own
    # repository and its own build, so this installer prints the steps and runs
    # none of them. Commands as in crow-nest's README.
    printf '  %sDefault: crow-nest (Rust engine), port 8099%s\n\n' "$B" "$Z"
    printf '  1. Engine and model. The container is 104.7 GB, one file:\n\n'
    cmd "git clone https://github.com/nibor1896/crow-nest ~/Projects/crow-nest && cd ~/Projects/crow-nest"
    cmd "hf download nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M Qwen3.8-Flash-Next-CNQ4.5-M.cnq --local-dir converter"
    cmd "cd engine && cargo build --release --bin serve && cd .."
    printf '\n'
    note "Needs an NVIDIA Blackwell card (sm_120, 32 GB), 64 GB RAM and the CUDA 13.3 runtime."
    printf '\n'
    printf '  2. Start the engine, then the window:\n\n'
    cmd "cd ~/Projects/crow-nest && tools/serve-linux.sh --port 8099"
    cmd "crow --base-url http://127.0.0.1:8099/v1"
    printf '\n'

    printf '  %sSecond: llama.cpp, port 8083%s\n\n' "$B" "$Z"
    printf '  1. The model. It is NOT part of this install: 73.45 GiB in 3 shards, plus\n'
    printf '     904,004,000 B for the vision projector, and it belongs to somebody else.\n\n'
    cmd "hf download unsloth/Qwen3.8-Flash-Next-GGUF --include '*UD-Q2_K_XL*' --local-dir $MODELS_DIR"
    cmd "hf download unsloth/Qwen3.8-Flash-Next-GGUF mmproj-F16.gguf --local-dir $MODELS_DIR"
    printf '\n'
    note "The second line is the projector and the glob of the first walks past it --"
    note "it sits in the repository root, above the quant folder. hf prints a tick even"
    note "when it reached nothing, so check the byte counts."
    printf '\n'

    printf '  2. Then open the window. It boots the server itself, from the model menu:\n\n'
    cmd "crow"
    printf '\n'
    note "or the full path, if ~/.local/bin is not on your PATH:"
    cmd "$LAUNCHER"
    printf '\n'

    line="$(resolved_server_line)"
    if [ -n "$line" ] && [ "${line#!}" = "$line" ]; then
        printf '     By hand, the same line the window would run:\n\n'
        cmd "$line"
        printf '\n'
    else
        printf '     By hand, once the model is on disk:\n\n'
        cmd "$PY $CROW_HOME/tools/start-server.py flash-next-q2-k-xl"
        printf '\n'
        [ -n "$line" ] && note "(not resolvable yet: ${line#!})"
        printf '\n'
    fi

    if [ -n "$HYPR_LINE" ]; then
        printf '  Hyprland floats the window once this line is in %s:\n\n' "$HYPR_WHERE"
        cmd "$HYPR_LINE"
        printf '\n'
        note "then, in a terminal:"
        cmd "hyprctl reload"
        printf '\n'
    fi

    printf '  %sPaths%s\n' "$B" "$Z"
    note "install    $CROW_HOME"
    if [ -L "$CROW_HOME/models" ]; then
        note "models     $CROW_HOME/models -> $(readlink "$CROW_HOME/models")"
    else
        note "models     $CROW_HOME/models"
    fi
    note "settings   ${XDG_CONFIG_HOME:-$HOME/.config}/crow"
    note "sessions   ${XDG_STATE_HOME:-$HOME/.local/state}/crow"
    note "boot logs  ${XDG_STATE_HOME:-$HOME/.local/state}/crow/log"
    printf '\n'
    if [ -L "$CROW_HOME/models" ]; then
        note "$CROW_HOME/models is a link to your model tree; change it with"
    else
        note "$CROW_HOME/models is the model root every entry point reads; move it with"
    fi
    note "install.sh --models DIR, or point CROW_MODELS at another tree for one shell."
    # A CHECKOUT IS ITS OWN <install>. crow_core.INSTALL_ROOT is the parent of
    # the cli/ that is running, so `python cli/crow_gui.py` out of a clone
    # resolves <clone>/models and never looks here. The line is printed and not
    # run: this script does not write into somebody's git tree.
    if [ -n "$REPO" ] && [ "$REPO" != "$CROW_HOME" ] && [ ! -e "$REPO/models" ] \
       && [ "$MODELS_DIR" != "$REPO/models" ]; then
        printf '\n'
        note "Run from the checkout at $REPO, the core resolves $REPO/models"
        note "instead -- it takes the same link:"
        cmd "ln -s $MODELS_DIR $REPO/models"
    fi
    printf '\n'
    note "The terminal client needs nothing but Python:  $PY $CROW_HOME/cli/crow.py"
    [ "$WITH_TAILSCALE" = 1 ] || note "The phone from anywhere (HTTPS, Tailscale): re-run with --tailscale"
    note "The Linux page -- paths, the float rule, the escape hatches, troubleshooting:"
    note "https://github.com/$REPO_SLUG/blob/main/docs/user-guide/linux.md"
    printf '\n'
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
usage() {
    # DURCH EINE ROEHRE GIBT ES KEINE DATEI ZU LESEN. `${BASH_SOURCE[0]}` ist
    # dann das Wort "bash", und `curl -fsSL <raw>/install.sh | bash -s -- --help`
    # antwortete mit `sed: can't read bash` und gar keiner Hilfe (gemessen
    # 2026-09-16) -- ausgerechnet auf dem Weg, den der Kopf dieser Datei als
    # ersten nennt. DIE LISTE WIRD DESHALB NICHT EIN ZWEITES MAL HINGESCHRIEBEN:
    # sie steht im Kopf, und von dort ist sie auch im Netz zu lesen.
    local me="${BASH_SOURCE[0]:-}"
    if [ -n "$me" ] && [ -f "$me" ]; then
        sed -n '/^# USAGE/,/^# ---/p' "$me" | sed 's/^# \{0,1\}//;$d'
        return 0
    fi
    printf 'install.sh: the options are in the header of the script itself --\n'
    printf '  https://github.com/%s/blob/main/install.sh\n' "$REPO_SLUG"
}

CROW_HOME="${CROW_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/crow}"
CROW_REF="${CROW_REF:-main}"
BUILD_ENGINE="${CROW_BUILD_ENGINE:-0}"
WITH_VOICE=0
WITH_TAILSCALE=0
WITH_PATHTRACER=0
WITH_DESKTOP=1
WITH_ENGINE=1
MODELS_ARG=""
SELFTEST=0
HYPR_LINE=""
HYPR_WHERE=""
VERSION=""
SOURCE=""
SOURCE_TMP=""
VRAM_MB=0

while [ $# -gt 0 ]; do
    case "$1" in
        --to)           CROW_HOME="$2"; shift 2 ;;
        --models)       MODELS_ARG="$2"; shift 2 ;;
        --ref)          CROW_REF="$2"; shift 2 ;;
        --voice)        WITH_VOICE=1; shift ;;
        --tailscale)    WITH_TAILSCALE=1; shift ;;
        --pathtracer)   WITH_PATHTRACER=1; shift ;;
        --build-engine) BUILD_ENGINE=1; shift ;;
        --no-engine)    WITH_ENGINE=0; shift ;;
        --no-desktop)   WITH_DESKTOP=0; shift ;;
        --selftest)     SELFTEST=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "unknown option: $1  (--help lists them)" ;;
    esac
done

# Where this script is, IF it is in a checkout. Piped through bash there is no
# such path, and that is the branch that fetches a tarball instead.
REPO=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [ -f "$REPO/cli/crow.py" ] || REPO=""
fi

PY="$(command -v python3 || command -v python || true)"

if [ "$SELFTEST" = 1 ]; then
    selftest
    exit $?
fi

# The model root. Nothing is asked: the tree this machine already has wins, then
# the default beside the install. 80-110 GiB do not belong under ~/.local/share,
# which is why $CROW_MODELS exists at all.
if [ -n "$MODELS_ARG" ]; then
    MODELS_DIR="$(abspath "$MODELS_ARG")"
elif [ -n "${CROW_MODELS:-}" ]; then
    MODELS_DIR="$(abspath "$CROW_MODELS")"
elif [ -d "$HOME/Projects/models/qwen3.8-flash-next" ]; then
    MODELS_DIR="$HOME/Projects/models/qwen3.8-flash-next"
else
    MODELS_DIR="$CROW_HOME/models"
fi

CROW_HOME="$(abspath "$CROW_HOME")"
LAUNCHER="$CROW_HOME/bin/crow"

printf '\n%sCrow%s -- the window, the clients and the manifest, under %s\n' "$B" "$Z" "$CROW_HOME"

preflight
resolve_source
install_payload

step "The runtime"
install_venv
[ "$WITH_ENGINE" = 1 ] && install_engine || note "engine check skipped (--no-engine)"
install_pathtracer
write_launcher
link_models
install_desktop
install_hyprland

final_screen
if [ "$WITH_TAILSCALE" = 1 ]; then
    tailscale_screen "$CROW_HOME/cli"
    printf '\n'
fi

[ -n "$SOURCE_TMP" ] && rm -rf "$SOURCE_TMP"
exit 0
