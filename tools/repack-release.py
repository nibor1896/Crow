#!/usr/bin/env python3
r"""Pack the Windows release on a machine that cannot build the Windows engine.

WHAT THIS IS. tools/pack-release.ps1 stages bin/ from a Windows CUDA build tree,
resolves every DLL import, adds cli/, kits/, templates/, manifests/operating-point.json,
LICENSE, NOTICE, README.md, writes MANIFEST.json (path, bytes, sha256) and zips
crow-<version>-win-x64.zip. install.ps1 downloads that asset by version and
verifies every file against MANIFEST.json, so a tag without the asset breaks
every Windows install in the minutes raw.githubusercontent.com caches the
script (vault, 2026-08-08: pack, push, cut the release at once).

WHY IT EXISTS. The Linux port (2.2.0) changes cli/, manifests/ and the docs and
leaves the engine untouched: bin/ of the previous release is bit for bit the
engine the operating point was measured with. On Linux there is no dumpbin, no
MSVC runtime and no Windows build tree, but there is the previous asset. So
this takes bin/ FROM THE PREVIOUS PACKAGE, verified against that package's own
MANIFEST.json before a byte is reused, and stages everything else from the
checkout exactly as pack-release.ps1 does: cli/ and kits/ without test_*.py,
__pycache__ and runs/ logs (2.1.0 and 2.8.5 each shipped ten of them),
templates/0731-chat-template.jinja, manifests/operating-point.json,
manifests/stack.json (the boot menu's, #196 P1), tools/te_rename.py (CrowSetup's
Image Stack convert step, #196 P2), the three root files. MANIFEST.json is written in the shape install.ps1 reads: a JSON
array of {path, bytes, sha256}, backslash paths, upper-case hex.

HOW IT IS CHECKED. --verify re-reads the finished zip the way install.ps1 does
(walk the manifest, hash every named file, then the other direction: every
file in the package is named) and refuses to print a result line otherwise.
When the engine DOES change, this tool is the wrong one: use pack-release.ps1
on Windows, which resolves the imports.

NO NVIDIA FILE SHIPS. The previous packages carried cublas64_13.dll and
cublasLt64_13.dll in bin/; this package carries neither. previous_bin() reads
them out of the previous package, checks them against its manifest like every
other byte and leaves them out, and shipped_set_violations() refuses a package
that holds one. CrowSetup fetches them at install time from NVIDIA's own PyPI
wheel (nvidia-cublas) and puts the same files in bin/ (see NOTICE).

WHAT MAY SHIP (#196 C2). One declared set, the same in pack-release.ps1:
SHIP_TOP_DIRS, SHIP_ROOT_FILES and SHIP_SINGLE_FILES say where a file may live;
EXCLUDE_DIRS and EXCLUDE_FILES say what never ships (runs/, *.log, __pycache__,
*.pyc, test_*.py, .env*, secrets.json, session and state files). A package
that would hold anything else is refused. test_repack_release.py compares
these lists with the ones in pack-release.ps1, so the two packers cannot drift
apart again (2.8.5 shipped logs because only one of them filtered).

THE PRIVACY GATE. Before the archive or its manifest is written, every file
that would be packed -- bin/ reused from the previous package included -- is
searched as raw bytes, in UTF-8 and in UTF-16LE, ignoring ASCII case, for:
the builder's profile path (both slash spellings and the JSON-escaped one), the
user name (as a path segment, \Users\<name>\ and /home/<name>/, and bare), the host name (only between separators: a NUL, punctuation or a line end on both sides),
and every --private-pattern. A hit prints file, pattern and count, and the
tool exits 1. There is no override switch. ONE scoped allowlist exists (PRIVACY_ALLOW):
upstream words that merely contain the owner's bare name (the "round-robin" of the llama
server's web UI, tokenizer vocabulary in the sd binaries) pass in the named file, in the
named byte context, up to a maximum count, and are listed as INFO; anything else refuses.
Path patterns and the host name are never allowlisted. The patterns describe THIS machine:
bin/ taken from a package another machine built carries THAT machine's paths,
so name them (--private-pattern "\Users\<builder>\").

    python tools/repack-release.py --previous dist/crow-2.1.0-win-x64.zip \
        --version 2.2.0 --out dist/
"""
from __future__ import annotations

import argparse
import fnmatch
import getpass
import hashlib
import json
import os
import re
import socket
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# ---- what may ship (keep identical to the $SHIP_* / $EXCLUDE_* in pack-release.ps1)
SHIP_ROOT_FILES = ("LICENSE", "NOTICE", "README.md")
SHIP_TOP_DIRS = ("bin", "cli", "kits")
SHIP_SINGLE_FILES = ("templates\\0731-chat-template.jinja", "manifests\\operating-point.json",
                     "manifests\\stack.json", "tools\\te_rename.py")
EXCLUDE_DIRS = ("runs", "__pycache__", ".crow", "digests", "sessions")
EXCLUDE_FILES = ("*.log", "*.pyc", "*.pyo", "*.jsonl", "test_*.py", ".env*", "secrets.json",
                 "session*.json", "state*.json", "settings.json", "*_tokens.json")
# NVIDIA files this package never carries: CrowSetup downloads them at install time from
# NVIDIA's own PyPI wheels (nvidia-cublas 13.6.0.2) and puts them at the same paths.
# An explicit list of names, never a pattern. Keep identical to $NVIDIA_AT_INSTALL in
# pack-release.ps1; test_repack_release.py compares them.
NVIDIA_AT_INSTALL = ("cublas64_13.dll", "cublasLt64_13.dll")
KIT_REQUIRED = ("crow-pathtracer.js", "kit.json", "voxel-kit.js", "SKILL.md", "check_diorama.py",
                "scaffold\\index.html", "scaffold\\scene.js",
                "LICENSE.three", "LICENSE.three-mesh-bvh", "LICENSE.three-gpu-pathtracer")

# ---- the privacy gate's scoped allowlist (keep identical to $PRIVACY_ALLOW in pack-release.ps1)
# Only the BARE user name can be allowlisted, never a path pattern or the host name. Each entry
# is "file glob @@ name @@ max @@ label @@ context regex": the glob is relative to the package
# (backslashes, case-insensitive), the name is the owner it is about, max is the most hits the
# file may carry, the regex describes the bytes that make a hit benign. It is matched against
# the ASCII-lowercased bytes around the hit, starting at or before the hit and running across it,
# and holds only syntax that Python and .NET read the same way. Measured 2026-10-01 on the
# binaries rebuilt from a neutral path (#196 C5): the word "round-robin" twice in the embedded
# web UI of llama-server-impl.dll, and tokenizer vocabulary (BPE merges lines, vocab JSON keys:
# Robinson, probing, robinet ...) 29 times in each sd binary. Only UTF-8 hits can be allowed.
PRIVACY_ALLOW = (
    r'bin\llama-server-impl.dll @@ robin @@ 2 @@ round-robin (embedded web UI) @@ round-robin',
    r'bin\sd-*.exe @@ robin @@ 29 @@ tokenizer vocabulary (BPE merges, vocab JSON) @@ (?:\n(?:[a-z]|\xe2\x96\x81|\xc4\xa0){0,24} (?:[a-z]|\xe2\x96\x81|\xc4\xa0){0,24}(?:</w>)?\n|"(?:[a-z]|\xe2\x96\x81|\xc4\xa0){0,24}"(?:: ?[0-9]+,|,))',
)
# The owner's public namespace (GitHub, Hugging Face, Ko-fi) is the same word as the Linux
# login on robin's box, so on that box the bare name is also allowed in exactly these
# contexts (robin, 2026-10-02). Globs match either separator. On a machine with another
# user name these entries match nothing.
NAMESPACE_ALLOW = (
    r'* @@ nibor1896 @@ 64 @@ public namespace URL @@ (?:github\.com|githubusercontent\.com|huggingface\.co|ko-fi\.com)/nibor1896(?![a-z0-9_-])',
    r'manifests/stack.json @@ nibor1896 @@ 32 @@ model repo id @@ "repo": "nibor1896/',
    r'cli/crow_core.py @@ nibor1896 @@ 1 @@ the GitHub repo constant @@ repo = "nibor1896/crow"',
    r'readme.md @@ nibor1896 @@ 1 @@ the repo link text @@ >nibor1896/crow<',
    r'license @@ nibor1896 @@ 1 @@ the copyright line @@ copyright \(c\) 20[0-9][0-9] nibor1896\n',
)
ALLOW_WINDOW = 64  # bytes of context read on each side of a hit


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def excluded(rel: str) -> str | None:
    """The rule that keeps `rel` out of a package, or None. Either separator."""
    parts = rel.replace("/", "\\").split("\\")
    for d in parts[:-1]:
        if d.lower() in EXCLUDE_DIRS:
            return "directory " + d + "\\"
    name = parts[-1].lower()
    for pat in EXCLUDE_FILES:
        if fnmatch.fnmatchcase(name, pat):
            return "file pattern " + pat
    return None


def is_nvidia_at_install(rel: str) -> bool:
    """True when the file name of `rel` is one of NVIDIA_AT_INSTALL (any folder, any case)."""
    return rel.replace("/", "\\").split("\\")[-1].lower() in {n.lower() for n in NVIDIA_AT_INSTALL}


def shipped_set_violations(paths) -> list[tuple[str, str]]:
    """Every path that is not in the declared shipped set, with the reason."""
    bad = []
    singles = {s.lower() for s in SHIP_SINGLE_FILES}
    for p in paths:
        rel = p.replace("/", "\\")
        low = rel.lower()
        if low == "manifest.json":
            continue
        parts = low.split("\\")
        if len(parts) == 1:
            if rel not in SHIP_ROOT_FILES:
                bad.append((rel, "top-level file outside the shipped set"))
                continue
        elif low not in singles and parts[0] not in SHIP_TOP_DIRS:
            bad.append((rel, "outside the shipped set (top level " + parts[0] + "\\)"))
            continue
        why = excluded(rel)
        if why:
            bad.append((rel, "excluded: " + why))
        elif is_nvidia_at_install(rel):
            bad.append((rel, "an NVIDIA library: CrowSetup downloads it at install time, it is not redistributed here"))
    return bad


# ---- the privacy gate
def _dedupe(items) -> list[str]:
    seen, out = set(), []
    for i in items:
        if i and i.lower() not in seen:
            seen.add(i.lower())
            out.append(i)
    return out


def private_patterns(extra=(), profile=None, user=None, host=None) -> tuple[list[str], list[str]]:
    """(patterns, notes). Defaults describe this machine; the arguments let a test
    stand in for another one."""
    notes: list[str] = []
    pats: list[str] = []
    if profile is None:
        profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    profile = (profile or "").rstrip("\\/")
    if profile:
        bs = profile.replace("/", "\\")
        pats += [bs, profile.replace("\\", "/"), bs.replace("\\", "\\\\")]
    if user is None:
        try:
            user = os.environ.get("USERNAME") or getpass.getuser()
        except Exception:
            user = os.path.basename(profile)
    if user:
        pats += ["\\Users\\%s\\" % user, "/Users/%s/" % user,
                 "\\\\Users\\\\%s\\\\" % user, "/home/%s/" % user]
        # The bare name too (#196 C2): "no references to the builder" is wider than paths.
        if len(user) < 4:
            notes.append("user name '%s' is shorter than 4 characters and is not searched bare" % user)
        else:
            pats.append(user)
    for h in _dedupe(_hosts(host)):
        if len(h) < 4:
            notes.append("host name %r is shorter than 4 characters and is not searched" % h)
        else:
            pats.append(h)
    pats += [e for e in extra if e]
    return _dedupe(pats), notes


def _hosts(host=None) -> list:
    return [host] if host is not None else [os.environ.get("COMPUTERNAME"), socket.gethostname()]


def host_names(host=None) -> list[str]:
    """The host-name patterns private_patterns() searches, for scan_private(hosts=...)."""
    return [h for h in _dedupe(_hosts(host)) if len(h) >= 4]


# What may stand right beside a host name: printable ASCII that is not a letter or digit
# (separators, quotes, punctuation), NUL (a C string), tab and line ends, or the file edge.
_SEP = frozenset(c for c in range(0x20, 0x7F) if not chr(c).isalnum()) | {0, 9, 10, 13}


def _count_bounded(low: bytes, needle: bytes, enc: str) -> int:
    """Occurrences of needle with a separator (_SEP) or the file edge on both sides.
    A host name sits between separators ("\\aios\\", "aios.local", "@aios", "aios\\0");
    four letters inside compressed CUDA data or a base64 run are not one (measured
    2026-10-02: the v3.0.0 bin\\ had 4 such hits for 'aios': "\\xcfaioSse",
    "\\x9aaioS\\r", "LAiosc8p")."""
    step = 2 if enc == "utf-16le" else 1

    def sep(k: int) -> bool:
        if k < 0 or k + step > len(low):
            return True
        return low[k] in _SEP and (step == 1 or low[k + 1] == 0)

    n, i = 0, low.find(needle)
    while i != -1:
        if sep(i - step) and sep(i + len(needle)):
            n += 1
        i = low.find(needle, i + 1)
    return n


def scan_private(files: dict[str, bytes], patterns, hosts=()) -> list[tuple[str, str, str, int]]:
    """(path, pattern, encoding, count) for every pattern found in any file. A pattern in
    `hosts` counts only where no ASCII letter or digit touches it (_count_bounded)."""
    bounded = {h.lower() for h in hosts}
    hits = []
    for path in sorted(files):
        low = files[path].lower()  # bytes.lower folds ASCII only, which is what paths are
        for pat in patterns:
            for enc in ("utf-8", "utf-16le"):
                needle = pat.lower().encode(enc)
                n = _count_bounded(low, needle, enc) if pat.lower() in bounded else low.count(needle)
                if n:
                    hits.append((path, pat, enc, n))
    return hits


def _allow_entries(allow=PRIVACY_ALLOW) -> list[dict]:
    out = []
    for e in allow:
        parts = e.split(" @@ ", 4)
        if len(parts) != 5:
            raise ValueError("privacy allowlist entry is malformed: " + e)
        glob, name, mx, label, rx = parts
        out.append({"glob": glob.lower(), "name": name.lower(), "max": int(mx), "label": label,
                    "re": re.compile(rx.encode("latin-1"))})
    return out


def bare_user_name(patterns) -> str | None:
    """The pattern that is the bare user name: the one whose \\Users\\<it>\\ is also searched."""
    low = [p.lower() for p in patterns]
    for p in low:
        if "\\users\\%s\\" % p in low:
            return p
    return None


def _covered(window: bytes, hit_at: int, hit_len: int, rx) -> bool:
    """True when rx matches starting at or before the hit and running across all of it."""
    for s in range(hit_at, -1, -1):
        m = rx.match(window, s)
        if m and m.end() >= hit_at + hit_len:
            return True
    return False


def split_allowed(files: dict[str, bytes], hits, patterns, allow=PRIVACY_ALLOW):
    """(refused, allowed). refused is [(path, pattern, encoding, count, reason)]; allowed is
    [(path, label, count, max)]. Only the bare user name, only as UTF-8, only in a file an
    entry names, only inside the entry's context, only up to its maximum; every other hit
    stays refused."""
    bare = bare_user_name(patterns)
    entries = _allow_entries(allow)
    refused, allowed = [], []
    for path, pat, enc, n in hits:
        mine = []
        if bare and enc == "utf-8" and pat.lower() == bare:
            where = path.lower().replace("\\", "/")
            mine = [e for e in entries if e["name"] == bare and fnmatch.fnmatchcase(where, e["glob"].replace("\\", "/"))]
        if not mine:
            refused.append((path, pat, enc, n, ""))
            continue
        if n > sum(e["max"] for e in mine):
            refused.append((path, pat, enc, n, "more than the allowed maximum of %d" % sum(e["max"] for e in mine)))
            continue
        low = files[path].lower()
        needle = pat.lower().encode("utf-8")
        tally = [0] * len(mine)
        uncovered = 0
        i = low.find(needle)
        while i != -1:
            lo = max(0, i - ALLOW_WINDOW)
            window = low[lo:i + len(needle) + ALLOW_WINDOW]
            for k, e in enumerate(mine):
                if _covered(window, i - lo, len(needle), e["re"]):
                    tally[k] += 1
                    break
            else:
                uncovered += 1
            i = low.find(needle, i + len(needle))
        if uncovered:
            refused.append((path, pat, enc, uncovered, "outside the allowed contexts"))
        for e, t in zip(mine, tally):
            if t > e["max"]:
                refused.append((path, pat, enc, t, "more than the allowed maximum of %d for %s" % (e["max"], e["label"])))
            elif t:
                allowed.append((path, e["label"], t, e["max"]))
    return refused, allowed


def privacy_gate(files: dict[str, bytes], extra=()) -> bool:
    """True when the files are clean. Prints every hit; the caller must refuse."""
    pats, notes = private_patterns(extra)
    for n in notes:
        print("  privacy gate note: " + n)
    hits = scan_private(files, pats, hosts=host_names())
    print("privacy gate: %d files, %d patterns (profile path x3 spellings, user name, host, %d extra), UTF-8 and UTF-16LE"
          % (len(files), len(pats), len([e for e in extra if e])))
    refused, allowed = split_allowed(files, hits, pats, allow=PRIVACY_ALLOW + NAMESPACE_ALLOW)
    for path, label, n, mx in allowed:
        print("  privacy gate INFO: allowed %s  %s  x%d (maximum %d)" % (path, label, n, mx))
    if not refused:
        print("  privacy gate: clean" + (" (%d allowed hits, see INFO)" % sum(a[2] for a in allowed) if allowed else ""))
        return True
    print("PRIVACY GATE: REFUSING TO PACK -- %d hits in %d files" % (len(refused), len({h[0] for h in refused})))
    for path, pat, enc, n, why in refused:
        print("  %s  pattern '%s'  %s  x%d%s" % (path, pat, enc, n, "  (%s)" % why if why else ""))
    print("  nothing was written. Remove the data from the source (or rebuild with path remapping); there is no override.")
    return False


# ---- the package
def read_manifest(z: zipfile.ZipFile) -> list[dict]:
    raw = z.read("MANIFEST.json").decode("utf-8-sig")
    return json.loads(raw)


def previous_bin(path: str, left_out: list | None = None) -> dict[str, bytes]:
    """bin\\* of the previous package, every byte checked against its manifest.
    The NVIDIA libraries it carries (NVIDIA_AT_INSTALL) are checked too, then left out;
    their names go to `left_out` when it is given."""
    with zipfile.ZipFile(path) as z:
        by_path = {e["path"]: e for e in read_manifest(z)}
        out = {}
        for name in z.namelist():
            key = name.replace("/", "\\")
            if not key.startswith("bin\\"):
                continue
            data = z.read(name)
            want = by_path.get(key)
            if want is None:
                raise SystemExit("previous package: %s is not in its MANIFEST.json" % key)
            if sha256_bytes(data) != want["sha256"].upper() or len(data) != want["bytes"]:
                raise SystemExit("previous package: %s does not match its own manifest" % key)
            if is_nvidia_at_install(key):
                if left_out is not None:
                    left_out.append(key)
                continue
            out[key] = data
    if not out:
        raise SystemExit("previous package carries no bin/")
    return out


def version_literal(repo: str = REPO) -> str:
    """cli/crow_core.py owns the literal since #187; cli/crow.py is the fallback
    for a checkout from before, whose core carries none."""
    for name in ("crow_core.py", "crow.py"):
        path = os.path.join(repo, "cli", name)
        if not os.path.isfile(path):
            continue
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', read_bytes(path).decode("utf-8"), re.M)
        if m:
            return m.group(1)
    raise SystemExit("no VERSION literal in cli/crow_core.py (nor in an older cli/crow.py)")


def _walk_shipped(repo: str, sub: str, files: dict[str, bytes]) -> None:
    for dirpath, dirnames, filenames in os.walk(os.path.join(repo, sub)):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in EXCLUDE_DIRS)
        for f in sorted(filenames):
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, repo).replace("/", "\\")
            if excluded(rel):
                continue
            files[rel] = read_bytes(full)


def stage_from_checkout(repo: str = REPO) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    _walk_shipped(repo, "cli", files)
    for f in SHIP_ROOT_FILES:
        files[f] = read_bytes(os.path.join(repo, f))
    files["templates\\0731-chat-template.jinja"] = read_bytes(
        os.path.join(repo, "manifests", "0731-chat-template.jinja"))
    op = read_bytes(os.path.join(repo, "manifests", "operating-point.json"))
    json.loads(op.decode("utf-8-sig"))  # must survive as readable JSON
    files["manifests\\operating-point.json"] = op
    # #196 P1: cli/crow_boot.py starts every operating point from this file and
    # finds it at ..\manifests\stack.json beside cli\. Required, as in
    # pack-release.ps1: a package without it has a boot menu that starts nothing.
    stack = os.path.join(repo, "manifests", "stack.json")
    if not os.path.isfile(stack):
        raise SystemExit("manifests/stack.json missing -- the boot menu starts every operating point from it")
    data = read_bytes(stack)
    json.loads(data.decode("utf-8-sig"))  # must survive as readable JSON
    files["manifests\\stack.json"] = data
    # #196 P2: CrowSetup's convert step runs <install>\tools\te_rename.py to build
    # the Image Stack's text_encoder_sdcli\. Required, as in pack-release.ps1.
    te = os.path.join(repo, "tools", "te_rename.py")
    if not os.path.isfile(te):
        raise SystemExit("tools/te_rename.py missing -- CrowSetup's Image Stack step needs it")
    files["tools\\te_rename.py"] = read_bytes(te)
    if "cli\\fonts\\OFL.txt" not in files:
        raise SystemExit("cli/fonts/OFL.txt missing -- the typeface may not ship without it")
    # The voxel kit (#298) ships in every package, beside cli\ -- pack-release.ps1 does the same.
    if not os.path.isdir(os.path.join(repo, "kits")):
        raise SystemExit("kits/ missing -- the voxel kit ships in every package")
    _walk_shipped(repo, "kits", files)
    for f in KIT_REQUIRED:
        if "kits\\pathtracer\\" + f not in files:
            raise SystemExit("kits/pathtracer/%s missing -- the kit or its licence notice would ship incomplete"
                             % f.replace("\\", "/"))
    want = json.loads(files["kits\\pathtracer\\kit.json"].decode("utf-8-sig"))["bundle"]["sha256"]
    if sha256_bytes(files["kits\\pathtracer\\crow-pathtracer.js"]) != want.upper():
        raise SystemExit("kits/pathtracer/crow-pathtracer.js does not match kit.json")
    return files


def write_package(out_zip: str, files: dict[str, bytes]) -> list[dict]:
    manifest = [{"path": p, "bytes": len(b), "sha256": sha256_bytes(b)}
                for p, b in sorted(files.items())]
    body = "﻿" + json.dumps(manifest, indent=4)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p, b in sorted(files.items()):
            z.writestr(p, b)
        z.writestr("MANIFEST.json", body.encode("utf-8"))
    return manifest


def verify(out_zip: str) -> tuple[int, list[str]]:
    """install.ps1's check, both directions."""
    problems = []
    with zipfile.ZipFile(out_zip) as z:
        manifest = read_manifest(z)
        # zipfile writes "/" on Windows and keeps "\\" elsewhere; compare on one spelling
        real = {n.replace("/", "\\"): n for n in z.namelist()}
        names = set(real)
        for e in manifest:
            if e["path"] not in names:
                problems.append("missing: " + e["path"]); continue
            data = z.read(real[e["path"]])
            if sha256_bytes(data) != e["sha256"] or len(data) != e["bytes"]:
                problems.append("corrupt: " + e["path"])
        named = {e["path"] for e in manifest} | {"MANIFEST.json"}
        for n in names:
            if n not in named:
                problems.append("unlisted: " + n)
    return len(manifest), problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--previous", required=True, help="the previous release's crow-*-win-x64.zip")
    ap.add_argument("--version", default=None, help="defaults to cli/crow_core.py's VERSION")
    ap.add_argument("--out", default=os.path.join(REPO, "dist"))
    ap.add_argument("--repo", default=REPO, help="the checkout to stage from (default: the one this tool is in)")
    ap.add_argument("--private-pattern", action="append", default=[], metavar="TEXT",
                    help="a further string that must not appear in any packed file (repeatable); "
                         "use it for the paths of the machine that built bin/")
    a = ap.parse_args(argv)
    version = a.version or version_literal(a.repo)
    if a.version and a.version != version_literal(a.repo):
        print("NOTE: --version %s but the checkout says %s" % (a.version, version_literal(a.repo)))
    nvidia = []
    files = previous_bin(a.previous, nvidia)
    print("bin/ reused from %s: %d files, every byte matched its manifest" % (a.previous, len(files)))
    if nvidia:
        print("  left out, NVIDIA's (CrowSetup downloads them at install time): " + ", ".join(sorted(nvidia)))
    staged = stage_from_checkout(a.repo)
    print("staged from the checkout: %d files" % len(staged))
    files.update(staged)
    bad = shipped_set_violations(files)
    if bad:
        print("REFUSING TO PACK -- %d files are not in the shipped set:" % len(bad))
        for rel, why in bad:
            print("  %s  (%s)" % (rel, why))
        return 1
    if not privacy_gate(files, a.private_pattern):
        return 1
    os.makedirs(a.out, exist_ok=True)
    out_zip = os.path.join(a.out, "crow-%s-win-x64.zip" % version)
    manifest = write_package(out_zip, files)
    n, problems = verify(out_zip)
    for p in problems:
        print("  FAILED   " + p)
    if problems:
        return 1
    total = sum(e["bytes"] for e in manifest)
    print("RESULT: %d files in the manifest (+ MANIFEST.json = %d in the package), %.1f MB staged, %.1f MB zipped"
          % (n, n + 1, total / 1e6, os.path.getsize(out_zip) / 1e6))
    print("  " + out_zip)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
