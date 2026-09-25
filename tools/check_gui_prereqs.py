#!/usr/bin/env python3
"""Measure the three things a tkinter GUI would stand on, before one is built.

WHY THIS EXISTS. #90 lists under "Not claimed": "That tkinter is the right
toolkit ... Nothing has compared it against the alternatives." Whoever builds
the sketch in that ticket one to one has made that decision without measuring
anything. This file is the measurement, and it is a SCRIPT rather than a ticket
comment because a comment cannot go red. A decision that rests on a run can be
re-run by the next person; one that rests on a remembered afternoon cannot.

WHAT WAS ALREADY KNOWN AND IS NOT THE QUESTION: whether Tk runs here at all.
`python -c "import tkinter"` succeeds in this repository, Tk 8.6.15 under
Python 3.13.3 [measured 2026-08-12]. That number is also the reference value
E13's installer preflight is written against - not "some Tk".

THE QUESTION THIS ANSWERS was narrower: does tkinter.font.families() carry a
PER-USER registered face, and under WHICH NAME. install_font() writes into HKCU
and the per-user store; all that was measured before today is that
System.Drawing.FontFamily::Families lists the face afterwards, and Tk takes a
different road to the font list. If Tk cannot see it, the surface language of
this candidate is not reachable with tkinter, and that is a reason to pick a
different toolkit rather than a detail to fix later.

THE ANSWER, measured 2026-08-13 on this machine: Tk lists it, under exactly
"Google Sans Code Monospace" - the same string cli/crow_core.py hands a
terminal in FONT_FAMILY. tkinter.font.families() returned 327 families and that
one is among them.

AND A TRAP FOUND ON THE WAY, which is why TK_FACE_LIMIT below is checked rather
than assumed: Tk gets its Windows face names through LOGFONT.lfFaceName and
they arrive CUT AT 31 CHARACTERS. The siblings show it in the same run -
"Google Sans Code Light Monospac", "Google Sans Code Medium Monospa", both
exactly 31, both cut mid-word. FONT_FAMILY is 26 and survives whole. A GUI that
later asks for "Google Sans Code Medium Monospace" (33) would be asking for a
name Tk never lists, and Tk answers a name it does not know with a substitute
face and no complaint at all.

THE THREE POINTS, all of them free:

  (i)   FAMILY. tkinter.font.families() lists the family cli/crow_core.py names,
        and the name is short enough that Windows did not cut it. The name Tk
        lists is printed, because that is the string crow_gui.py will ask for.
  (ii)  GLYPHS. Every character any surface writes is in the cmap of every face
        this repository ships, and the three ranges the existing comments record
        still measure what those comments say. This point went red on its first
        run and the finding is real: cli/crow.py prints U+2692 as its tool-call
        marker and neither shipped face has that glyph. See KNOWN_UNCOVERED.
  (iii) WINDOW RUNTIME. pywebview is importable AND a WebView2 runtime is
        registered. Both, because they fail separately: the import says the
        Python package is there, the registry says a window can actually open.
        Changed 2026-08-14 -- it read Tk's patchlevel against a floor of 8.6
        until then, which is the toolkit 0.3.0 removed. A point that reports
        3 of 3 green for something the package no longer ships is a point that
        cannot go red for what it is supposed to guard.

WHY THE GLYPH RUN READS THE FILE AND NOT THE FONT SYSTEM. Windows would answer
"can you draw U+2801" with a substitute face - it always has one - so asking it
measures the machine's font fallback, not the file this repository ships. The
cmap of the shipped .ttf is the only place where "the user who installed our
package has this glyph" is a fact rather than a hope.

WHY STRING LITERALS COUNT AND COMMENTS DO NOT, and the distinction is not
pedantry: cli/crow.py carries the braille cells (u+280B and friends) inside the
COMMENT that records why the spinner avoids them. A scan that read comments
would be red at the very sentence explaining the rule, and a checker that is
permanently red gets stopped rather than read. Docstrings ARE scanned - they
reach the screen through --help and /help, so a character in one can be drawn.

WHAT THIS TOOL DOES NOT DO: it does not install anything, register anything or
write anything. Two runs in a row produce the same bytes; that is checkable with
`diff` and it is meant to be checked.

Usage:  check_gui_prereqs.py [--repo <dir>] [--family <name>] [--min-tk <ver>]
        --family runs point (i) against a name of your choosing. That is the
        NEGATIVE CONTROL: point at a face that is not installed and the run has
        to say "not listed" and exit non-zero. A lookup that finds something
        whatever it is asked for is not checking anything.
        --min-tk is there for the self-test; the shipped bound is MIN_TK below.

Exit 0 = all three points hold.  1 = at least one does not.  2 = setup error.
"""

import argparse
import ast
import os
import shutil
import struct
import subprocess
import sys

# BORROWED, NOT COPIED. `read` already exists next door, and SURFACE_DIRS is the
# next door's answer to "where can a surface live" - a second copy of that tuple
# here is exactly the second truth the whole rebuild is against. check_shared_core
# discovers surfaces rather than taking them from a manifest, and the reason it
# gives holds here too: the file nobody remembered to add to a hand-kept list is
# the second surface, and that is the file this repository is about to grow.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_operating_point import read  # noqa: E402
from check_shared_core import SURFACE_DIRS  # noqa: E402

# The lower bound E13 ships, decided there rather than left open: Tk 8.6.
# Reference value on this machine 8.6.15 under Python 3.13.3 [measured
# 2026-08-12]. Written here as a constant and not read from a manifest because
# the installer is the place that enforces it against a user's machine; this
# tool checks the machine the GUI is being written on.
MIN_TK = "8.6"

# WebView2's update GUID and the three registry views it can answer from. Both
# are install.ps1:334-338's, quoted rather than re-derived: two sets of keys for
# one question is how they drift apart.
WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

# NO MEASURED FLOOR. 151.0.4129.78 is what this machine has and what the window
# was driven on; nothing has established the oldest runtime that still works, so
# claiming a number here would invent one. Empty means "any runtime the registry
# reports". --min-webview2 is what the self-test raises to prove this can go red.
MIN_WEBVIEW2 = ""

# Windows hands Tk its face names through LOGFONT.lfFaceName, 32 wide characters
# INCLUDING the terminating NUL, so 31 usable. See the module docstring for the
# two truncated siblings that measure it.
TK_FACE_LIMIT = 31

# ------------------------------------------------------- the Linux runtime ---
#
# WHAT THE WINDOW STANDS ON OVER THERE, and it is a different list because it is
# a different renderer: WebView2 is Edge and comes with the operating system,
# WebKitGTK is a library that either is installed or is not. Each of these fails
# SEPARATELY and each of them fails the window completely -- the same reason
# webview2_probe below asks two questions instead of one.
#
# The versions are the ones pywebview's GTK backend asks for in its own first
# lines (`Gtk 3.0`, `Gdk 3.0`, then `WebKit2 4.1` falling back to `4.0`), quoted
# rather than re-derived: two lists for one question is how they drift apart.
# THERE IS NO GTK4 BACKEND in pywebview 6.2.1, so asking for WebKit 6.0 here
# would be checking for something the window could not use if it found it.
GI_NAMESPACES = (("Gtk", "3.0"), ("Gdk", "3.0"), ("WebKit2", "4.1"))

# The clipboard reader the window shells out to for a pasted picture. pywebview
# has no clipboard API on any backend, and Gtk.Clipboard's own image read
# returned None here on a clipboard that demonstrably held a PNG [measured
# 2026-09-16, focused and unfocused, on the main loop and off it]. So this
# program is not a nicety: without it Ctrl+V on a screenshot does nothing at all.
CLIPBOARD_TOOLS = ("wl-paste", "xclip")

# THE VARIABLE THAT DECIDES WHETHER A WINDOW APPEARS AT ALL on NVIDIA under a
# Wayland compositor. Without it WebKitGTK's DMA-BUF renderer commits a buffer
# with explicit sync and no acquire point, the compositor answers
# `Gdk-Message: Error 71 (Protocol error)`, and the process dies before the
# surface maps. cli/crow_gui.py sets it at import (`prepare_environment`), which
# is why this is a NOTE and not a failure: the window brings its own answer, and
# a point that went red here would be red on every correct machine.
NVIDIA_SYNC_ENV = "__NV_DISABLE_EXPLICIT_SYNC"

# The three ranges the existing comments record, with the numbers those comments
# state. cli/crow.py:233-234 says U+2580-259F is 32 of 32 and U+2500-257F is 128
# of 128; cli/crow.py:318-319 and cli/crow_core.py:2177-2182 say braille
# U+2800-28FF is 0 of 256, measured 2026-08-07 against Cascadia Mono as a
# control. Re-measured here per shipped face. A deviation does not mean the GUI
# broke - it means one of those comments no longer describes the file beside it,
# and those comments are cited as evidence in the plan and in the suite.
RECORDED_RANGES = (
    (0x2500, 0x257F, "box drawing", 128),
    (0x2580, 0x259F, "block elements", 32),
    (0x2800, 0x28FF, "braille", 0),
)

# WHAT POINT (ii) FOUND ON ITS FIRST RUN, declared here rather than swallowed or
# quietly fixed. cli/crow.py:875 and :903 print U+2692 as the tool-call marker,
# and neither shipped face has that glyph: coverage stops at U+25D9 plus U+FFFD,
# 674 codepoints in each file [measured 2026-08-13]. Windows answers a missing
# glyph with a substitute face - the exact fallback cli/crow.py:317-321 keeps the
# spinner away from braille to avoid. It is a CLI defect, it predates this stage,
# and repairing it here would be the stage that was sent to MEASURE the client
# editing what it prints. So it is declared: named, reasoned, and printed on
# every run.
#
# THE DECLARATION IS NOT A SILENCER, and this half is what keeps it from becoming
# one: an entry no surface writes any more, or one the font has since gained, is
# RED. A list of exemptions that only ever grows is a rug; check_shared_core
# carries the same symmetric rule against its manifest, for the same reason.
# EMPTY SINCE 2026-08-14, and the entry that was here is why this tuple exists.
# U+2692 was the CLI's tool-call marker and neither shipped face had the glyph:
# Windows drew it from a substitute face, the exact fallback cli/crow.py keeps
# its spinner away from braille to avoid. E9 measured it, declared it here
# rather than swallowing it, and left the fix to a later stage. The marker is
# now U+25CF -- the same one the window already draws for a tool call, so both
# surfaces mark a call the same way and the glyph is in both faces.
#
# The declaration was not simply deleted alongside the edit: this checker went
# red at it first ("no surface writes it any more - drop the declaration"),
# which is the half of point (ii) that makes the other half worth reading.
KNOWN_UNCOVERED = ()


def sfnt_tables(data):
    """The table directory of a TrueType/OpenType file as {tag: (offset, len)}.

    Standard library only, like everything else here: fontTools would answer
    this in one line and would be the first third-party dependency in the
    package. The two tables this needs are 12 bytes of header and 16 bytes per
    entry, which is cheaper than the import would be.
    """
    if len(data) < 12:
        raise ValueError("not a font file: %d bytes" % len(data))
    tag, num, _, _, _ = struct.unpack(">IHHHH", data[:12])
    if tag not in (0x00010000, 0x74727565, 0x4F54544F):  # ttf, 'true', 'OTTO'
        raise ValueError("unknown sfnt tag 0x%08X" % tag)
    out = {}
    for i in range(num):
        off = 12 + i * 16
        if off + 16 > len(data):
            raise ValueError("table directory runs past the end of the file")
        name, _, toff, tlen = struct.unpack(">4sIII", data[off:off + 16])
        out[name.decode("latin-1")] = (toff, tlen)
    return out


def _cmap_format4(data, off):
    """Segment-mapped, the BMP subtable every Windows font carries."""
    segx2 = struct.unpack(">H", data[off + 6:off + 8])[0]
    seg = segx2 // 2
    base = off + 14
    ends = struct.unpack(">%dH" % seg, data[base:base + segx2])
    starts = struct.unpack(">%dH" % seg, data[base + segx2 + 2:base + segx2 * 2 + 2])
    deltas = struct.unpack(">%dh" % seg, data[base + segx2 * 2 + 2:base + segx2 * 3 + 2])
    ro_off = base + segx2 * 3 + 2
    ranges = struct.unpack(">%dH" % seg, data[ro_off:ro_off + segx2])
    out = set()
    for i in range(seg):
        if starts[i] > ends[i]:
            continue
        for cp in range(starts[i], min(ends[i], 0xFFFF) + 1):
            if ranges[i] == 0:
                glyph = (cp + deltas[i]) & 0xFFFF
            else:
                # The idRangeOffset indirection, and it is measured from the
                # position of the entry itself - not from the start of the
                # table. Getting this wrong reports a font as covering
                # everything, which is a false GREEN and the failure this whole
                # file exists to avoid.
                gi = ro_off + i * 2 + ranges[i] + (cp - starts[i]) * 2
                if gi + 2 > len(data):
                    continue
                glyph = struct.unpack(">H", data[gi:gi + 2])[0]
                if glyph:
                    glyph = (glyph + deltas[i]) & 0xFFFF
            # Glyph 0 is .notdef. A codepoint that maps there is NOT covered,
            # and a reader that counted it would report a font as carrying
            # every character in the range it happens to span.
            if glyph:
                out.add(cp)
    return out


def _cmap_format12(data, off):
    """Segmented coverage beyond the BMP. Neither shipped face uses one today
    (both carry format 4 twice, platform 0/3 and 3/1, measured 2026-08-13), but
    a font with an astral range would be silently half-read without this."""
    ngroups = struct.unpack(">I", data[off + 12:off + 16])[0]
    out = set()
    for i in range(ngroups):
        s, e, g = struct.unpack(">III", data[off + 16 + i * 12:off + 16 + i * 12 + 12])
        if g == 0:
            continue
        out.update(range(s, e + 1))
    return out


def cmap_codepoints(data):
    """Every codepoint the file maps to a real glyph, out of every subtable.

    The union across subtables rather than one chosen subtable: a font may carry
    the same coverage twice under two platform ids, and picking "the right one"
    is a judgement this does not need to make. A format nobody here parses is
    skipped, and if that leaves NOTHING parsed the caller is told - an empty set
    read as "covers nothing" would report every character as missing, which is a
    false red, but an empty set read as an error is the truth.
    """
    tables = sfnt_tables(data)
    if "cmap" not in tables:
        raise ValueError("font has no cmap table")
    coff = tables["cmap"][0]
    ntab = struct.unpack(">H", data[coff + 2:coff + 4])[0]
    out, parsed, seen = set(), 0, []
    for i in range(ntab):
        pid, eid, soff = struct.unpack(">HHI", data[coff + 4 + i * 8:coff + 4 + i * 8 + 8])
        sub = coff + soff
        fmt = struct.unpack(">H", data[sub:sub + 2])[0]
        seen.append(fmt)
        if fmt == 4:
            out |= _cmap_format4(data, sub)
            parsed += 1
        elif fmt == 12:
            out |= _cmap_format12(data, sub)
            parsed += 1
    if not parsed:
        raise ValueError("no readable cmap subtable, formats present: %s"
                         % ", ".join(str(f) for f in seen))
    return out


def literal_chars(text):
    """Non-ASCII characters inside string literals, as {char: [line, ...]}.

    PARSED, NOT TOKENIZED, and the difference is a hole rather than a style
    preference: the token text of "\\u280b" is seven ASCII characters, so a scan
    of token text reports a braille spinner written that way as clean. The AST
    hands over the value, which is the cell that gets drawn. Case 5 of the
    self-test writes it exactly that way for this reason.

    Comments carry no AST node at all, which is the separation this rule needs
    anyway: cli/crow.py keeps its braille sample inside the comment that records
    why the spinner avoids braille, and a checker red at that sentence would be
    stopped rather than read. Docstrings DO carry one - they reach the screen
    through --help and /help, so a character in one can be drawn.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        # A file the parser cannot finish is not silently skipped: the caller
        # gets None and reports it, because "we could not look" and "we looked
        # and it was clean" are different answers and only one of them is green.
        return None
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        line = getattr(node, "lineno", 0)
        for ch in node.value:
            if ord(ch) > 0x7F:
                out.setdefault(ch, [])
                if line not in out[ch]:
                    out[ch].append(line)
    return {ch: sorted(lines) for ch, lines in out.items()}


def surface_files(repo):
    """Every client source under the surface directories, sorted, as (rel, path).

    Test files are left out on purpose: a suite is not a surface, and
    cli/test_crow.py quotes the wordmark inside an assertion. A directory that
    does not exist yet (gui/) is not an error - it is where the second surface
    lands, and this tool picks it up the day it does.
    """
    out = []
    for d in SURFACE_DIRS:
        full = os.path.join(repo, d)
        if not os.path.isdir(full):
            continue
        for name in sorted(os.listdir(full)):
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            out.append((d + "/" + name, os.path.join(full, name)))
    return out


def version_at_least(patchlevel, minimum):
    """Compare only as many components as the bound names.

    "8.6.15" against a bound of "8.6" compares (8, 6) with (8, 6) and holds; a
    bound of "8.6.16" would compare all three and would not. Anything that is
    not a dotted number is False rather than an exception - an unreadable
    version is not a version that passed.
    """
    def parts(s):
        out = []
        for piece in str(s).split("."):
            digits = ""
            for ch in piece:
                if not ch.isdigit():
                    break
                digits += ch
            if not digits:
                return None
            out.append(int(digits))
        return tuple(out) if out else None

    got, want = parts(patchlevel), parts(minimum)
    if got is None or want is None:
        return False
    return got[:len(want)] >= want


def neighbours(family, families):
    """The families Tk lists whose name starts with the first word of the one
    asked for. This is what makes the negative control readable: against a face
    that is not installed the list is empty, and the report says so instead of
    just saying no."""
    head = family.split()[0].lower() if family.split() else ""
    if not head:
        return []
    return [f for f in families if f.lower().startswith(head)]


def family_problems(family, families):
    """Point (i) as a pure function, so it can be exercised without a display."""
    problems = []
    if len(family) > TK_FACE_LIMIT:
        problems.append("%r is %d characters; Windows hands Tk at most %d "
                        "(LOGFONT.lfFaceName), so Tk can never list it under "
                        "this name" % (family, len(family), TK_FACE_LIMIT))
    if family not in families:
        problems.append("tkinter.font.families() lists %d families, none of "
                        "them %r" % (len(families), family))
    return problems


def webview2_probe():
    """Point (iii): what the WINDOW needs -- pywebview, and a runtime under it.

    TWO ANSWERS, NOT ONE, and the second is the one that costs nothing to get
    wrong. `import webview` succeeding says the Python package is installed; it
    says nothing about whether Edge's WebView2 runtime exists on this machine,
    and a window with no runtime does not open. install.ps1:316-322 records the
    same trap for `tkinter.TkVersion`. A checker that only imports is a checker
    that cannot go red for the thing that actually breaks.

    ALL THREE REGISTRY VIEWS, because on this machine only one of them answers:
    `pv 151.0.4129.78` under HKLM\\WOW6432Node, with the 64-bit view and HKCU
    empty. Reading one view and concluding "no runtime" reports false, and it
    reports false in the safe direction -- unnoticed. The GUID and the three
    keys are install.ps1:334-338's, not a second set invented here.

    Returns (pywebview_version, runtime_version, which_view) with None for
    whatever is not there.
    """
    package = None
    try:
        import webview                              # noqa: F401
    except Exception:                               # noqa: BLE001 - reported
        package = None
    else:
        # THE VERSION COMES FROM THE METADATA, not from the module. pywebview
        # 6.2.1 carries no `__version__` attribute [measured 2026-08-14]; asking
        # the module for one yields "unknown" and hides which release is
        # installed, which is the one thing this line exists to report.
        try:
            import importlib.metadata as _md
            package = _md.version("pywebview")
        except Exception:                           # noqa: BLE001
            package = "installed, version unknown"

    runtime, view = None, None
    try:
        import winreg
    except ImportError:
        return package, None, None

    for hive, hive_name, path in (
            (winreg.HKEY_LOCAL_MACHINE, "HKLM",
             r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\%s" % WEBVIEW2_GUID),
            (winreg.HKEY_LOCAL_MACHINE, "HKLM",
             r"SOFTWARE\Microsoft\EdgeUpdate\Clients\%s" % WEBVIEW2_GUID),
            (winreg.HKEY_CURRENT_USER, "HKCU",
             r"SOFTWARE\Microsoft\EdgeUpdate\Clients\%s" % WEBVIEW2_GUID)):
        try:
            with winreg.OpenKey(hive, path) as key:
                value = str(winreg.QueryValueEx(key, "pv")[0])
        except OSError:
            continue
        if value:
            runtime, view = value, "%s\\%s" % (hive_name, path)
            break
    return package, runtime, view


def _tool(argv):
    """Run one small program and return its stdout. None when it is not here.

    NONE IS NOT AN EMPTY STRING, the same distinction cli/crow_gui.py draws for
    its clipboard readers: "the tool is missing" and "the tool answered nothing"
    are different answers, and only the second one is about the thing asked for.
    """
    if not shutil.which(argv[0]):
        return None
    try:
        done = subprocess.run(argv, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else ""


def fc_probe(shipped_path):
    """Point (i) on Linux: every family fontconfig lists, and OUR family name.

    THE FAMILY IS READ OFF THE SHIPPED FILE, and it is not the same string as on
    the other platform. Windows resolves a variable font into named instances
    and registers those, so the name a terminal has to be given there is
    "Google Sans Code Monospace" -- which is what cli/crow_core.py's FONT_FAMILY
    says and why it says it. fontconfig registers the FILE, under its name ID 1:
    `fc-query` answers "Google Sans Code" for the very same bytes [measured
    2026-09-16]. Asking Linux for the Windows string would report an installed
    font as missing, and that is a false red on the one point whose whole job is
    to be believed.

    Returns (families, our_family), with None for whatever fontconfig would not
    say.
    """
    listed = _tool(["fc-list", ":", "family"])
    if listed is None:
        return None, None
    families = set()
    for line in listed.splitlines():
        for name in line.split(","):
            if name.strip():
                families.add(name.strip())
    # THE `\n` IS PART OF THE FORMAT AND IS NOT DECORATION. fc-query repeats the
    # family once per named STYLE -- seven times for the shipped variable font
    # -- and without a separator in the format string they arrive as one
    # 119-character run of the same name, which is then a family nothing lists.
    said = _tool(["fc-query", "--format", "%{family}\n", shipped_path])
    lines = [line.strip() for line in (said or "").splitlines() if line.strip()]
    return tuple(sorted(families)), (lines[0] if lines else None)


def gtk_probe():
    """Point (iii) on Linux: can the toolkit the window renders in be loaded?

    THE TYPELIB AND NOT THE PACKAGE NAME. `import gi` says PyGObject is there;
    `gi.require_version('WebKit2', '4.1')` says the introspection data for the
    renderer is on this machine, which is the half that is actually missing on a
    fresh install. They fail separately, so they are asked separately.

    NOTHING IS INSTANTIATED. No window opens and no display is needed: a
    prerequisite check that required a session could not run in the place where
    a prerequisite check is worth running.

    Returns (problems, notes), both lists of finished lines.
    """
    problems, notes = [], []
    try:
        import gi
    except Exception as exc:                        # noqa: BLE001 - reported
        return (["PyGObject is not importable (%s: %s) -- the window has no "
                 "toolkit" % (type(exc).__name__, exc)], notes)
    notes.append("PyGObject %s" % getattr(gi, "__version__", "version unknown"))
    for namespace, version in GI_NAMESPACES:
        try:
            gi.require_version(namespace, version)
        except Exception as exc:                    # noqa: BLE001 - reported
            problems.append("%s %s is not available (%s)" % (namespace, version, exc))
            continue
        notes.append("%s %s" % (namespace, version))
    return problems, notes


def clipboard_probe():
    """Which clipboard reader the window would find, as (name, path) or (None, None)."""
    for name in CLIPBOARD_TOOLS:
        found = shutil.which(name)
        if found:
            return name, found
    return None, None


def tk_probe():
    """Ask Tk itself, in a root that is never mapped.

    withdraw() immediately: the root exists the moment Tk() returns, and a
    checker that flashes a grey square across the screen is a checker people
    stop running. destroy() in a finally, so a raising families() call does not
    leave an interpreter with a live window behind this process.
    """
    import tkinter
    from tkinter import font as tkfont
    root = tkinter.Tk()
    try:
        root.withdraw()
        patchlevel = str(root.tk.call("info", "patchlevel"))
        # Sorted and de-duplicated: Tk returns the list in whatever order the
        # platform enumerator produced, and this report is diffed against a
        # second run of itself.
        families = tuple(sorted(set(str(f) for f in tkfont.families(root))))
    finally:
        root.destroy()
    return patchlevel, families


def check_glyphs(repo, faces):
    """Point (ii): coverage of what the surfaces write, and the recorded ranges.

    Returns (problems, notes). Both are lists of finished lines, so the caller
    prints and does not decide.
    """
    problems, notes = [], []

    sources = surface_files(repo)
    if not sources:
        problems.append("no surface source found in %s - nothing was checked"
                        % ", ".join(d + "/" for d in SURFACE_DIRS))
    wanted = {}
    for rel, path in sources:
        found = literal_chars(read(path))
        if found is None:
            problems.append("%s could not be tokenized - its literals were not "
                            "read" % rel)
            continue
        for ch, lines in found.items():
            wanted.setdefault(ch, [])
            # Every site, not just the first in the file: U+2692 is written at
            # cli/crow.py:875 AND :903, and a report that named one of them
            # would send the reader to fix half a defect.
            for line in lines:
                wanted[ch].append((rel, line))

    declared = dict(KNOWN_UNCOVERED)

    # The stale half of the declaration, checked once rather than per face: a
    # codepoint nobody writes any more has no business being exempt.
    for cp, why in sorted(declared.items()):
        if not any(ord(ch) == cp for ch in wanted):
            problems.append("U+%04X is declared in KNOWN_UNCOVERED (%s) and no "
                            "surface writes it any more - drop the declaration"
                            % (cp, why))

    for name, data in faces:
        try:
            covered = cmap_codepoints(data)
        except (ValueError, struct.error) as exc:
            problems.append("%s: %s" % (name, exc))
            continue

        # The other stale half: the font gained the glyph, so the exemption is
        # now a note about nothing.
        for cp, why in sorted(declared.items()):
            if cp in covered:
                problems.append("%s covers U+%04X, which is still declared in "
                                "KNOWN_UNCOVERED (%s) - drop the declaration"
                                % (name, cp, why))

        missing = sorted((ch for ch in wanted if ord(ch) not in covered),
                         key=ord)
        for ch in missing:
            # Capped, because a punctuation character can be written on fifty
            # lines and a report nobody can read is a report nobody reads. The
            # cap is on the PRINTED sites, never on the rule.
            sites = sorted(wanted[ch])
            where = ", ".join("%s:%d" % (rel, line) for rel, line in sites[:4])
            if len(sites) > 4:
                where += " and %d more" % (len(sites) - 4)
            line = "%s does not cover U+%04X %r, written at %s" % (
                name, ord(ch), ch, where)
            if ord(ch) in declared:
                notes.append(line + " [declared: %s]" % declared[ord(ch)])
            else:
                problems.append(line)
        if not [ch for ch in missing if ord(ch) not in declared]:
            notes.append("%s covers %d of the %d characters the surfaces write, "
                         "%d codepoints in the file"
                         % (name, len(wanted) - len(missing), len(wanted),
                            len(covered)))

        for lo, hi, label, recorded in RECORDED_RANGES:
            got = sum(1 for cp in range(lo, hi + 1) if cp in covered)
            total = hi - lo + 1
            if got != recorded:
                problems.append("%s: %s U+%04X-%04X is %d of %d, the comments "
                                "in cli/ record %d - one of them is now stale"
                                % (name, label, lo, hi, got, total, recorded))
            else:
                notes.append("%s: %s U+%04X-%04X %d of %d, as recorded"
                             % (name, label, lo, hi, got, total))
    return problems, notes


def main(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--family", default=None,
                    help="face to look for; default is cli/crow_core.py's "
                         "FONT_FAMILY. Point it at something not installed to "
                         "run the negative control.")
    ap.add_argument("--min-tk", default=MIN_TK)
    ap.add_argument("--min-webview2", default=MIN_WEBVIEW2)
    args = ap.parse_args(argv[1:])

    # The family and the shipped faces come from the client, not from a second
    # list written here. A checker that carries its own copy of FONT_FAMILY goes
    # green while the two names drift apart, which is the exact defect the
    # comment above FONT_FAMILY was written after.
    sys.path.insert(0, os.path.join(args.repo, "cli"))
    try:
        import crow_core
    except ImportError as exc:
        print("SETUP ERROR: cannot import cli/crow_core.py from %s (%s)"
              % (args.repo, exc))
        return 2

    # WHICH PLATFORM'S QUESTIONS THIS RUN ASKS, taken from the client's own seam
    # rather than from a `sys.platform` written here. cli/crow_platform.py is the
    # one place in this repository allowed to know what OS this is, and a checker
    # with a second opinion is a second opinion.
    try:
        import crow_platform
    except ImportError as exc:
        print("SETUP ERROR: cannot import cli/crow_platform.py from %s (%s)"
              % (args.repo, exc))
        return 2

    family = args.family or crow_core.FONT_FAMILY
    names = crow_core.font_files()
    if not names:
        print("SETUP ERROR: no font files under %s" % crow_core.FONT_DIR)
        return 2
    faces = []
    for name in names:
        path = os.path.join(crow_core.FONT_DIR, name)
        with open(path, "rb") as fh:
            faces.append((name, fh.read()))

    failed = 0
    print("crow GUI prerequisites")
    print()

    # (i) -----------------------------------------------------------------
    if not crow_platform.IS_WINDOWS:
        # THE SAME QUESTION THROUGH THE OTHER FONT SYSTEM. Tk is not the toolkit
        # on either platform any more -- 0.3.0 replaced it with a webview -- but
        # the question this point asks outlives the toolkit: is the face this
        # repository SHIPS reachable on this machine, under a name something can
        # ask for? On Windows the reader is Tk's family list (and the
        # 31-character truncation that comes with it); here it is fontconfig,
        # which is what crow_platform.install_fonts writes into and what
        # `fc-cache -f` refreshes.
        #
        # NO TRUNCATION RULE ON THIS SIDE. LOGFONT.lfFaceName is a Win32
        # structure; fontconfig has no such limit, and carrying the check across
        # would be a measurement of the wrong machine.
        shipped = os.path.join(crow_core.FONT_DIR, names[0])
        listed, ours = fc_probe(shipped)
        # THE DEFAULT IS THE NAME THE FILE ITSELF DECLARES, see fc_probe. An
        # explicit --family still wins, so the negative control is unchanged:
        # a face nobody installed is not listed and the point goes red.
        wanted = args.family or ours or family
        if listed is None:
            failed += 1
            print("  FAILED   %-30s fontconfig did not answer"
                  % "(i) family in fontconfig")
            print("             neither fc-list nor fc-query is on PATH -- the "
                  "shipped faces can be copied but never found")
        elif wanted not in listed:
            failed += 1
            print("  FAILED   %-30s %r not usable"
                  % ("(i) family in fontconfig", wanted))
            print("             fc-list reports %d families, none of them %r"
                  % (len(listed), wanted))
            print("             `python cli/crow.py` installs the shipped faces "
                  "into %s on first start" % crow_platform.font_store())
            for near in neighbours(wanted, listed):
                print("             fontconfig does list %s" % near)
        else:
            print("  OK       %-30s %r, out of %d families"
                  % ("(i) family in fontconfig", wanted, len(listed)))
            print("             the shipped file declares %r; FONT_FAMILY in "
                  "cli/crow_core.py is %r, the WINDOWS named instance"
                  % (ours, crow_core.FONT_FAMILY))
            print("             per-user store %s, %d of %d shipped face(s) in it"
                  % (crow_platform.font_store(),
                     len(crow_core.font_installed()), len(names)))
    else:
        patchlevel, families, tk_error = None, (), None
        try:
            patchlevel, families = tk_probe()
        except Exception as exc:                      # noqa: BLE001 - see below
            # Deliberately broad: Tk answers a missing display with TclError, a
            # missing tcl library with ImportError, and a broken installation with
            # whatever the loader raises. All three are the same answer to the
            # question this tool asks - tkinter is not available here - and turning
            # any of them into a traceback would report the toolkit as unmeasured
            # rather than as unavailable.
            tk_error = "%s: %s" % (type(exc).__name__, exc)

        if tk_error is not None:
            failed += 1
            print("  FAILED   %-30s tkinter did not start" % "(i) family in Tk")
            print("             %s" % tk_error)
        else:
            problems = family_problems(family, families)
            if problems:
                failed += 1
                print("  FAILED   %-30s %r not usable" % ("(i) family in Tk", family))
                for p in problems:
                    print("             %s" % p)
                near = neighbours(family, families)
                if near:
                    print("             Tk does list, near that name:")
                    for f in near:
                        print("               %-34s %d chars" % (f, len(f)))
                else:
                    print("             and no family Tk lists begins with %r"
                          % (family.split()[0] if family.split() else family))
            else:
                print("  OK       %-30s %r, %d chars, out of %d families"
                      % ("(i) family in Tk", family, len(family), len(families)))
                near = [f for f in neighbours(family, families) if f != family]
                for f in near:
                    mark = "  <-- cut at %d" % TK_FACE_LIMIT if len(f) == TK_FACE_LIMIT else ""
                    print("             sibling %-34s %d chars%s" % (f, len(f), mark))
    # (ii) ----------------------------------------------------------------
    problems, notes = check_glyphs(args.repo, faces)
    if problems:
        failed += 1
        print("  FAILED   %-30s %d problem(s) over %d shipped face(s)"
              % ("(ii) glyphs the surface needs", len(problems), len(faces)))
        for p in problems:
            print("             %s" % p)
    else:
        print("  OK       %-30s %d shipped face(s), %d declared exception(s)"
              % ("(ii) glyphs the surface needs", len(faces),
                 len(KNOWN_UNCOVERED)))
    for n in notes:
        print("             %s" % n)

    # (iii) ---------------------------------------------------------------
    if not crow_platform.IS_WINDOWS:
        # THE SAME POINT, THE OTHER RENDERER. On Windows this asks two things
        # that fail separately -- the Python package, and the WebView2 runtime
        # under it. Here it asks three, for exactly the same reason: pywebview
        # imports without GTK, GTK loads without the WebKit2 typelib, and a
        # clipboard reader is a program that may simply not be installed. All
        # three are silent until a user clicks something.
        package = webview2_probe()[0]
        problems, notes = gtk_probe()
        tool, where = clipboard_probe()
        if package is None:
            problems.insert(0, "pywebview is not importable -- `pip install "
                               "pywebview` into the runtime venv (plain, NOT "
                               "pywebview[gtk]: that extra pins PyGObject and "
                               "would build it from source)")
        else:
            notes.insert(0, "pywebview %s" % package)
        if tool is None:
            problems.append("no clipboard reader on PATH (%s) -- Ctrl+V on a "
                            "picture reaches nothing"
                            % ", ".join(CLIPBOARD_TOOLS))
        else:
            notes.append("clipboard reader %s at %s" % (tool, where))
        if problems:
            failed += 1
            print("  FAILED   %-30s %d problem(s)"
                  % ("(iii) window runtime", len(problems)))
            for p in problems:
                print("             %s" % p)
        else:
            print("  OK       %-30s %s" % ("(iii) window runtime",
                                           ", ".join(notes[:2])))
        for n in notes:
            print("             %s" % n)
        # A NOTE AND NOT A POINT, see NVIDIA_SYNC_ENV: cli/crow_gui.py sets this
        # itself at import, so a machine that does not have it in the
        # environment is the NORMAL machine. It is printed because when a window
        # does die with `Gdk-Message: Error 71` this is the first line to read.
        print("             %s=%s (cli/crow_gui.py sets it at import; without "
              "it WebKitGTK dies on NVIDIA+Wayland with Gdk Error 71)"
              % (NVIDIA_SYNC_ENV, os.environ.get(NVIDIA_SYNC_ENV) or "unset"))
    else:
        package, runtime, view = webview2_probe()
        if package is None:
            failed += 1
            print("  FAILED   %-30s pywebview is not importable -- the window "
                  "cannot start" % "(iii) window runtime")
            print("             the installer runs `pip install pywebview`; the "
                  "terminal client does not need it")
        elif runtime is None:
            failed += 1
            print("  FAILED   %-30s pywebview %s, but NO WebView2 runtime in any "
                  "of the three registry views" % ("(iii) window runtime", package))
            print("             the import alone does not open a window -- Edge or "
                  "Windows 11 ships the runtime")
        elif args.min_webview2 and not version_at_least(runtime, args.min_webview2):
            failed += 1
            print("  FAILED   %-30s WebView2 %s is below the floor %s"
                  % ("(iii) window runtime", runtime, args.min_webview2))
        else:
            floor = args.min_webview2 or "none measured"
            print("  OK       %-30s pywebview %s, WebView2 %s, floor %s"
                  % ("(iii) window runtime", package, runtime, floor))
            print("             answered by %s" % view)
    print()
    print("RESULT: %d of 3 prerequisites hold" % (3 - failed))
    return 1 if failed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        # The report prints the characters it found missing. Without this a
        # console on cp1252 raises UnicodeEncodeError on exactly the run that
        # had something to say.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
