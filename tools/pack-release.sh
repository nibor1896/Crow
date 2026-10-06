#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# pack-release.sh -- the Linux twin of tools/pack-release.ps1 (#342)
# ---------------------------------------------------------------------------
#
# WHAT
#   Packs dist/crow-<version>-linux-x64.tar.gz, the Crow package CrowSetup
#   installs on Linux:
#     the payload of every package, staged exactly like the Windows ones by
#       tools/repack-release.py stage_from_checkout(): cli/ and kits/ through
#       the exclude rules, templates/0731-chat-template.jinja,
#       manifests/{operating-point,stack}.json, tools/te_rename.py, LICENSE,
#       NOTICE, README.md;
#     bin/sd-server                       the image server (--sd-server).
#   NO NVIDIA FILE IS PACKED. sd-server links libcudart.so.13, libcublas.so.13
#   and libcublasLt.so.13 (NVIDIA_AT_INSTALL below); CrowSetup downloads them at
#   install time from NVIDIA's own PyPI wheels (nvidia-cuda-runtime 13.3.29,
#   nvidia-cublas 13.6.0.2) and puts the same files in <install>/cuda/lib/ (see
#   NOTICE). The package holds nothing under cuda/ and no file of those names.
#   crow_core._image_server_env puts <install>/cuda/lib on LD_LIBRARY_PATH.
#   MANIFEST.json is a bare JSON array of {path, bytes, sha256}: forward
#   slashes, upper-case hex, MANIFEST.json not listed in itself.
#
# THE CHECKS, IN THIS ORDER, BEFORE A BYTE IS WRITTEN
#   1. completeness: every NEEDED of bin/sd-server (readelf -d) is in the
#      package, is a library every glibc system or the NVIDIA driver has
#      (SYSTEM_LIBS below), or is one of the three NVIDIA libraries named in
#      NVIDIA_AT_INSTALL, which CrowSetup provides at install time. Nothing
#      else of NVIDIA's is accepted, and any other missing library refuses.
#      pack-release.ps1's dumpbin check, for ELF.
#   2. the shipped set: tools/repack-release.py shipped_set_violations() on
#      every file (cuda/lib/ is still exempt from it, see below), then
#      nvidia_violations(): a file of an NVIDIA_AT_INSTALL name, or anything
#      under cuda/, refuses the pack.
#   3. THE PRIVACY GATE: tools/repack-release.py privacy_gate() -- the same
#      patterns and the same scoped allowlist as pack-release.ps1: $HOME (three
#      spellings), the user name (as a path segment and bare, case-insensitive),
#      the host name (between separators), every --private-pattern, in UTF-8 and UTF-16LE -- plus
#      /home/<any user>/ in both encodings, which no allowlist covers. The
#      Linux builder's user name is also the project's public namespace, so
#      LINUX_ALLOW below lets the bare name pass in its URL, repo-id, link and
#      copyright contexts only (repack-release.py's allowlist format). A hit
#      prints file, pattern and count and exits 1; nothing is written. There is
#      no override switch.
#   The archive is then written (.part, renamed when complete) with neutral
#   headers -- uid/gid 0, no user or group name, mtime 0, regular files only --
#   and read back: every member against the manifest in both directions, and
#   the tar stream itself through the gate once more.
#
# USAGE
#   tools/pack-release.sh --sd-server PATH [--out DIR]
#                         [--version V] [--private-pattern TEXT]...
#   tools/pack-release.sh --selftest
#   tools/pack-release.sh --gate FILE...   the privacy gate alone, on files named
#                                          by their base name (installer/build.sh)
#   --cuda-lib is accepted and ignored (it named the toolkit the libraries were
#   copied from; none are copied any more).
#
# NOT HERE
#   Building sd-server: tools/build-sd-server.sh. A binary built in a home
#   folder carries that path (the 2026-09-27 sd-server: 236 hits) and is
#   refused; build it with the compiler's path mapping and RPATH $ORIGIN, or
#   from a neutral folder.
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "pack-release.sh: python3 is required (the gate is tools/repack-release.py)" >&2; exit 2; }
command -v readelf >/dev/null 2>&1 || { echo "pack-release.sh: readelf (binutils) is required for the completeness check" >&2; exit 2; }

exec "$PY" - "$REPO" "$@" <<'PY'
import argparse, gzip, hashlib, importlib.util, io, json, os, re, shutil, subprocess, sys, tarfile, tempfile

REPO = sys.argv[1]
spec = importlib.util.spec_from_file_location("repack", os.path.join(REPO, "tools", "repack-release.py"))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)

# NVIDIA's libraries sd-server links, which the package does NOT carry: CrowSetup downloads
# them at install time from NVIDIA's PyPI wheels (nvidia-cuda-runtime 13.3.29, nvidia-cublas
# 13.6.0.2) into <install>/cuda/lib/. An explicit list of names, never a pattern.
NVIDIA_AT_INSTALL = ("libcudart.so.13", "libcublas.so.13", "libcublasLt.so.13")
# What every glibc system has, plus the driver's libcuda. Anything else a
# packed binary needs has to be in the package.
SYSTEM_LIBS = {
    "libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "librt.so.1",
    "ld-linux-x86-64.so.2", "libgcc_s.so.1", "libstdc++.so.6", "libgomp.so.1",
    "libcuda.so.1",  # the NVIDIA driver's, never redistributable
}
HOME_ANY = re.compile(rb"/home/[a-z0-9._-]+/")
HOME_ANY16 = re.compile(rb"/\x00h\x00o\x00m\x00e\x00/\x00(?:[a-z0-9._-]\x00)+/\x00")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest().upper()


def needed(path: str) -> list:
    out = subprocess.run(["readelf", "-d", path], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("readelf failed on %s: %s" % (path, out.stderr.strip()))
    return re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out.stdout)


def completeness(binaries: dict, needed_of=None) -> list:
    """(file, library) for every NEEDED that is neither shipped, nor a system library, nor one of
    the NVIDIA_AT_INSTALL names CrowSetup provides. `binaries` maps package path -> file on disk;
    `needed_of` replaces readelf (selftest)."""
    needed_of = needed_of or needed
    shipped = {os.path.basename(p) for p in binaries}
    gaps = []
    for rel, src in sorted(binaries.items()):
        for lib in needed_of(src):
            if lib not in shipped and lib not in SYSTEM_LIBS and lib not in NVIDIA_AT_INSTALL:
                gaps.append((rel, lib))
    return gaps


def home_hits(files: dict) -> list:
    """(path, encoding, count) for /home/<anyone>/ in any file, ASCII case folded."""
    hits = []
    for p in sorted(files):
        low = files[p].lower()
        for enc, rx in (("utf-8", HOME_ANY), ("utf-16le", HOME_ANY16)):
            n = len(rx.findall(low))
            if n:
                hits.append((p, enc, n))
    return hits


# The Linux builder's user name is the project's public namespace (GitHub,
# Hugging Face, Ko-fi), so the bare name is allowed in exactly these contexts,
# in the format and with the rules of tools/repack-release.py PRIVACY_ALLOW:
# file glob @@ name @@ max hits per file @@ label @@ context regex (matched on
# the ASCII-lowercased bytes, starting at or before the hit, across it). Only
# the bare name and only UTF-8; path patterns, /home/<user>/ and the host name
# are never allowed. On a machine with another user name these entries match
# nothing.
LINUX_ALLOW = rr.NAMESPACE_ALLOW + (
    # installer/build.sh gates the CrowSetup binary, which embeds manifests/stack.json
    r'crowsetup* @@ nibor1896 @@ 32 @@ model repo id (embedded stack.json) @@ "repo": "nibor1896/',
)


def gate(files: dict, extra) -> bool:
    """tools/repack-release.py privacy_gate() with LINUX_ALLOW added, then /home/<anyone>/."""
    pats, notes = rr.private_patterns(extra)
    for n in notes:
        print("  privacy gate note: " + n)
    hits = rr.scan_private(files, pats, hosts=rr.host_names())
    print("privacy gate: %d files, %d patterns (profile path x3 spellings, user name, host, %d extra) + /home/<user>/, UTF-8 and UTF-16LE"
          % (len(files), len(pats), len([e for e in extra if e])))
    refused, allowed = rr.split_allowed(files, hits, pats, allow=rr.PRIVACY_ALLOW + LINUX_ALLOW)
    for path, label, n, mx in allowed:
        print("  privacy gate INFO: allowed %s  %s  x%d (maximum %d)" % (path, label, n, mx))
    ok = not refused
    if refused:
        print("PRIVACY GATE: REFUSING TO PACK -- %d hits in %d files" % (len(refused), len({h[0] for h in refused})))
        for path, pat, enc, n, why in refused:
            print("  %s  pattern '%s'  %s  x%d%s" % (path, pat, enc, n, "  (%s)" % why if why else ""))
    hits = home_hits(files)
    for p, enc, n in hits:
        print("  %s  pattern '/home/<user>/'  %s  x%d" % (p, enc, n))
    if hits:
        print("PRIVACY GATE: REFUSING TO PACK -- /home/<user>/ in %d files; there is no override." % len({h[0] for h in hits}))
    if ok and not hits:
        print("  privacy gate: clean" + (" (%d allowed hits, see INFO)" % sum(a[2] for a in allowed) if allowed else ""))
    return ok and not hits


def stage(repo: str, sd_server: str) -> tuple:
    """(files {forward-slash path: bytes}, {package path: source file} of the ELF files)."""
    files = {k.replace("\\", "/"): v for k, v in rr.stage_from_checkout(repo).items()}
    elf = {}
    if not os.path.isfile(sd_server):
        raise SystemExit("--sd-server %s: not a file" % sd_server)
    files["bin/sd-server"] = rr.read_bytes(sd_server)
    elf["bin/sd-server"] = os.path.realpath(sd_server)
    return files, elf


def shipped_violations(files: dict) -> list:
    linux_only = {"cuda/lib/" + n for n in NVIDIA_AT_INSTALL}
    return rr.shipped_set_violations([p for p in files if p not in linux_only])


def nvidia_violations(files: dict) -> list:
    """(path, reason) for every file that is NVIDIA's: a name in NVIDIA_AT_INSTALL (or in
    repack-release.py's Windows list), in any folder, or anything under cuda/."""
    names = {n.lower() for n in NVIDIA_AT_INSTALL + tuple(rr.NVIDIA_AT_INSTALL)}
    bad = []
    for p in sorted(files):
        if os.path.basename(p).lower() in names:
            bad.append((p, "an NVIDIA library: CrowSetup downloads it at install time, it is not redistributed here"))
        elif p.startswith("cuda/"):
            bad.append((p, "cuda/ is where CrowSetup puts NVIDIA's libraries; the package holds nothing there"))
    return bad


def manifest_of(files: dict) -> bytes:
    m = [{"path": p, "bytes": len(b), "sha256": sha(b)} for p, b in sorted(files.items())]
    return json.dumps(m, indent=2).encode("utf-8")


def mode_of(path: str) -> int:
    return 0o755 if path == "bin/sd-server" or path.startswith("cuda/lib/") else 0o644


def write_tar(out: str, files: dict) -> None:
    part = out + ".part"
    with open(part, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as t:
                items = sorted(files.items()) + [("MANIFEST.json", manifest_of(files))]
                for p, b in items:
                    ti = tarfile.TarInfo(p)
                    ti.size, ti.mode, ti.mtime = len(b), mode_of(p), 0
                    ti.uid = ti.gid = 0
                    ti.uname = ti.gname = ""
                    t.addfile(ti, io.BytesIO(b))
    os.replace(part, out)


def verify(out: str, extra) -> list:
    """CrowSetup's own check (both directions, regular files only), and the gate on the raw tar."""
    problems, seen = [], {}
    with gzip.open(out, "rb") as gz:
        raw = gz.read()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as t:
        for m in t.getmembers():
            if not m.isreg():
                problems.append("not a regular file: " + m.name); continue
            if m.name.startswith("/") or ".." in m.name.split("/"):
                problems.append("unsafe name: " + m.name); continue
            if m.uname or m.gname or m.uid or m.gid:
                problems.append("owner in the header: " + m.name)
            seen[m.name] = t.extractfile(m).read()
    manifest = json.loads(seen.pop("MANIFEST.json", b"[]"))
    named = set()
    for e in manifest:
        named.add(e["path"])
        b = seen.get(e["path"])
        if b is None:
            problems.append("missing: " + e["path"])
        elif len(b) != e["bytes"] or sha(b) != e["sha256"]:
            problems.append("corrupt: " + e["path"])
    problems += ["unlisted: " + n for n in seen if n not in named]
    # Each member through the gate under its own path, as at staging: the
    # allowlist is per file, so the tar as ONE blob would refuse every allowed
    # context (2026-10-02: x20 for the public namespace). The member names are
    # gated on their own; the headers are checked above (no owner).
    seen["MANIFEST.json"] = json.dumps(manifest).encode()
    names = "\n".join(sorted(seen)).encode()
    if not gate(seen, extra) or not gate({"<tar member names>": names}, extra):
        problems.append("the written archive does not pass the privacy gate")
    return problems, len(manifest)


def pack(a) -> int:
    version = a.version or rr.version_literal(REPO)
    print("packing crow %s (linux-x64)" % version)
    print("  sd-server: %s" % a.sd_server)
    print("  cuda/lib : none -- %s are NVIDIA's, CrowSetup downloads them at install time" % ", ".join(NVIDIA_AT_INSTALL))
    if a.cuda_lib:
        print("  NOTE: --cuda-lib is ignored; no NVIDIA file is packed")
    files, elf = stage(REPO, a.sd_server)
    print("  staged %d files, %.1f MB" % (len(files), sum(map(len, files.values())) / 1e6))

    gaps = completeness(elf)
    if gaps:
        print("REFUSING TO PACK -- the package is incomplete:")
        for rel, lib in gaps:
            print("  %s needs %s, which is neither packed, a system library, nor one CrowSetup downloads from NVIDIA" % (rel, lib))
        return 1
    print("  completeness: OK (%s are provided at install time from NVIDIA)" % ", ".join(NVIDIA_AT_INSTALL))
    nv = nvidia_violations(files)
    if nv:
        print("REFUSING TO PACK -- %d NVIDIA files are in the package, which must carry none:" % len(nv))
        for rel, why in nv:
            print("  %s  (%s)" % (rel, why))
        return 1
    print("  no NVIDIA file: OK")
    bad = shipped_violations(files)
    if bad:
        print("REFUSING TO PACK -- %d files are not in the shipped set:" % len(bad))
        for rel, why in bad:
            print("  %s  (%s)" % (rel, why))
        return 1
    print("  shipped set: OK")
    if not gate(files, a.private_pattern):
        print("  nothing was written")
        return 1

    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, "crow-%s-linux-x64.tar.gz" % version)
    write_tar(out, files)
    problems, n = verify(out, a.private_pattern)
    for p in problems:
        print("  FAILED   " + p)
    if problems:
        os.remove(out)
        return 1
    with open(out, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print("RESULT: %d files in the manifest (+ MANIFEST.json = %d in the package), %.1f MB staged, %.1f MB packed"
          % (n, n + 1, sum(map(len, files.values())) / 1e6, os.path.getsize(out) / 1e6))
    print("  %s" % out)
    print("  sha256 %s" % digest)
    return 0


# ------------------------------------------------------------------ selftest
def selftest() -> int:
    ok = red = 0

    def check(name, passed):
        nonlocal ok, red
        print(("  ok   " if passed else "  FAIL ") + name)
        ok, red = (ok + 1, red) if passed else (ok, red + 1)

    home = os.path.expanduser("~")
    user = os.path.basename(home)
    host = __import__("socket").gethostname()
    clean = {"bin/sd-server": b"\x7fELF built in /build/sd and remapped to ~/src"}
    check("a clean file passes", gate(clean, []))
    check("$HOME (UTF-8) is refused", not gate({"x": ("rpath " + home + "/.local/lib").encode()}, []))
    check("$HOME (UTF-16LE) is refused", not gate({"x": (home + "/x").encode("utf-16le")}, []))
    check("/home/<another user>/ is refused", not gate({"x": b"/home/someone-else/src/sd.cpp"}, []))
    check("/HOME/<user>/ in upper case is refused", not gate({"x": b"/HOME/OTHER/x"}, []))
    check("/home/<user>/ in UTF-16LE is refused", not gate({"x": "/home/other/x".encode("utf-16le")}, []))
    if len(user) >= 4:
        check("the bare user name is refused, any case", not gate({"x": ("built by " + user.upper()).encode()}, []))
    if len(host) >= 4:
        check("the host name is refused", not gate({"x": ("host " + host).encode()}, []))
    check("--private-pattern is refused", not gate({"x": b"secret-lab-name"}, ["secret-lab-name"]))
    if user == "nibor1896":
        check("the public namespace passes in its contexts",
              gate({"README.md": b"see https://github.com/nibor1896/Crow and https://huggingface.co/nibor1896/Qwen",
                    "manifests/stack.json": b'"repo": "nibor1896/Qwen3.8-27B-CNQ4.5"',
                    "LICENSE": b"Copyright (c) 2026 nibor1896\n"}, []))
        check("the bare name in prose is still refused", not gate({"cli/crow_core.py": b"# for the real `nibor1896`"}, []))
        check("an allowed context in another file is refused", not gate({"cli/x.py": b'"repo": "nibor1896/x"'}, []))
        check("the installer binary may embed stack.json's repo ids",
              gate({"crowsetup": b'x "repo": "nibor1896/Qwen3.8-27B-CNQ4.5" https://github.com/nibor1896/Crow/releases'}, []))

    check("the cuda libs are named, a stray top-level dir is not",
          shipped_violations({"cuda/lib/libcudart.so.13": b"", "cli/a.py": b""}) == []
          and shipped_violations({"cuda/lib/libnvrtc.so": b""}) != [])
    check("runs/ and *.log never ship", shipped_violations({"cli/runs/x.log": b""}) != [])

    # NVIDIA at install time: the named allowlist, the closure that uses it, and a package without a NVIDIA file.
    check("the install-time NVIDIA list is exactly libcudart, libcublas, libcublasLt (.so.13)",
          sorted(NVIDIA_AT_INSTALL) == ["libcublas.so.13", "libcublasLt.so.13", "libcudart.so.13"])
    fake = {"sd-server": ["libc.so.6", "libcudart.so.13", "libcublas.so.13", "libcublasLt.so.13", "libcuda.so.1"],
            "odd": ["libmystery.so.1"], "older": ["libcublas.so.12"], "rtc": ["libnvrtc.so.13"]}
    nd = lambda path: fake[os.path.basename(path)]  # noqa: E731
    check("completeness: the three NVIDIA libraries are accepted as provided at install time",
          completeness({"bin/sd-server": "sd-server"}, nd) == [])
    check("NEGATIVE: an unrelated missing library still refuses, and is the only one named",
          completeness({"bin/sd-server": "sd-server", "bin/odd": "odd"}, nd) == [("bin/odd", "libmystery.so.1")])
    check("NEGATIVE: another cublas version and libnvrtc are not on the list",
          completeness({"bin/older": "older", "bin/rtc": "rtc"}, nd) == [("bin/older", "libcublas.so.12"), ("bin/rtc", "libnvrtc.so.13")])
    check("NEGATIVE: a staged NVIDIA file is refused, by name in any folder and anything under cuda/",
          [p for p, _ in nvidia_violations({"bin/libcublas.so.13": b"", "cuda/lib/x.so": b"", "bin/cublas64_13.dll": b"",
                                            "cli/a.py": b""})] == ["bin/cublas64_13.dll", "bin/libcublas.so.13", "cuda/lib/x.so"])
    nv_sd = os.path.join(tempfile.gettempdir(), "pack-release-selftest-sd-server")
    with open(nv_sd, "wb") as fh:
        fh.write(b"\x7fELF sd")
    try:
        staged, staged_elf = stage(REPO, nv_sd)
    finally:
        os.remove(nv_sd)
    check("no NVIDIA file is staged (this checkout plus sd-server): nothing under cuda/, none of the names",
          nvidia_violations(staged) == [] and not [p for p in staged if p.startswith("cuda/")])
    check("and only sd-server is read for imports", sorted(staged_elf) == ["bin/sd-server"])

    tmp = tempfile.mkdtemp(prefix="pack-release-selftest-")
    try:
        true = shutil.which("true") or "/usr/bin/true"
        check("completeness: a binary needing only libc passes", completeness({"bin/sd-server": true}) == [])
        libs = [l for l in needed(true)]
        check("readelf reads NEEDED", "libc.so.6" in libs)
        global SYSTEM_LIBS
        saved = SYSTEM_LIBS
        SYSTEM_LIBS = set()
        check("completeness: an unshipped library is named", completeness({"bin/sd-server": true}) == [("bin/sd-server", "libc.so.6")])
        SYSTEM_LIBS = saved

        files = {"bin/sd-server": b"\x7fELF sd", "cli/crow_core.py": b'VERSION = "9.9.9"\n',
                 "cuda/lib/libcudart.so.13": b"\x7fELF rt"}
        out = os.path.join(tmp, "crow-9.9.9-linux-x64.tar.gz")
        write_tar(out, files)
        problems, n = verify(out, [])
        check("the archive reads back against its manifest", problems == [] and n == 3)
        with tarfile.open(out) as t:
            m = {x.name: x for x in t.getmembers()}
        check("headers carry no owner and mtime 0", all(x.uname == "" and x.uid == 0 and x.mtime == 0 for x in m.values()))
        check("sd-server and the libs are executable", m["bin/sd-server"].mode == 0o755 and m["cuda/lib/libcudart.so.13"].mode == 0o755
              and m["cli/crow_core.py"].mode == 0o644)
        man = json.loads(t_read(out, "MANIFEST.json"))
        check("MANIFEST.json: forward slashes, upper-case hex, not listed in itself",
              all("/" in e["path"] or e["path"] == "LICENSE" for e in man)
              and all(e["sha256"] == e["sha256"].upper() for e in man)
              and "MANIFEST.json" not in {e["path"] for e in man})
        bad = os.path.join(tmp, "crow-9.9.8-linux-x64.tar.gz")
        write_tar(bad, {"bin/sd-server": ("x " + home + "/y").encode()})
        check("a written archive with a home path fails verification", verify(bad, [])[0] != [])
        ok_ns = os.path.join(tmp, "crow-9.9.7-linux-x64.tar.gz")
        write_tar(ok_ns, {"manifests/stack.json": b'"repo": "nibor1896/Qwen3.8-27B-CNQ4.5"'})
        check("an allowed context reads back clean (gated per member)", verify(ok_ns, [])[0] == [])
        if len(user) >= 4:
            bad_name = os.path.join(tmp, "crow-9.9.6-linux-x64.tar.gz")
            write_tar(bad_name, {"cli/x.py": ("# built by " + user).encode()})
            check("the bare user name in a member still fails verification", verify(bad_name, [])[0] != [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = ok + red
    if red:
        print("RESULT: %d of %d FAILED" % (red, total))
        return 1
    print("RESULT: SELFTEST OK - %d checks" % total)
    return 0


def t_read(out: str, name: str) -> bytes:
    with tarfile.open(out) as t:
        return t.extractfile(name).read()


def main(argv) -> int:
    ap = argparse.ArgumentParser(prog="tools/pack-release.sh", description="Pack crow-<version>-linux-x64.tar.gz (#342).")
    ap.add_argument("--sd-server", help="the image server binary (tools/build-sd-server.sh)")
    ap.add_argument("--cuda-lib", default="", help="ignored: no NVIDIA library is packed any more (CrowSetup downloads them)")
    ap.add_argument("--out", default=os.path.join(REPO, "dist"))
    ap.add_argument("--version", default=None, help="defaults to cli/crow_core.py's VERSION")
    ap.add_argument("--private-pattern", action="append", default=[], metavar="TEXT")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--gate", nargs="+", metavar="FILE", help="only run the privacy gate over these files")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.gate:
        return 0 if gate({os.path.basename(f): rr.read_bytes(f) for f in a.gate}, a.private_pattern) else 1
    if not a.sd_server:
        ap.error("--sd-server is required (or --selftest)")
    return pack(a)


sys.exit(main(sys.argv[2:]))
PY
