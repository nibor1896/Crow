"""Hold manifests/stack.json to its own promises, offline; with --online, to Hugging Face.

WHAT THE MANIFEST IS. The one machine-readable description of the three
operating points (flash-next, 27b, image-stack) that the installer and the boot
script consume: every file with a pinned revision, bytes and sha256, the engine
env and argv, the ports, the readiness probe and the identity. A wrong number in
it is a download that never verifies or a serve that boots the wrong model, on a
machine that is not ours. So:

OFFLINE (the default, no network):
  * schema       - every required field, the right type, a known status;
  * paths        - every path starts with ${INSTALL} or ${MODELS}; no other
                   placeholder, no drive letter, no home directory, no user name
                   anywhere in the file (documentation keys included: they ship);
  * references   - every id a point names exists, every file and derived entry
                   is used by some point, a derived entry's inputs are in each
                   point that uses it;
  * sums         - each point's bytes per status, files, derived and disk equal
                   the sum of what it lists; preflight disk equals that sum;
  * wiring       - every env and argv path names a file or derived output the
                   SAME point installs; the identity is the CROW_CNQ file name
                   (engine.kind "llama-server": the GGUF after -m, --mmproj a
                   projector); an optional video_server (#340) has its own port,
                   HTTP 200 readiness, a runtime file of role "runtime" per
                   platform and every path inside that runtime's dir;
                   the slot dir is created; ports agree with argv; a menu line
                   never claims more context than the point serves;
  * platforms    - #341: every engine and image server names its binary for
                   windows AND linux, the same program under ${INSTALL}/bin/
                   (.exe on Windows only); argv_platform names only those two;
                   lib_path (the folders in front of LD_LIBRARY_PATH) holds
                   ${INSTALL}/ folders, and on Linux the engine's own folder;
  * nvidia files - NVIDIA's CUDA libraries from NVIDIA's own wheels (nvidia_files,
                   CrowSetup's crate::nvidia): every field, a 64-hex sha256 and
                   positive bytes for the wheel and each member it takes, the wheel
                   on files.pythonhosted.org named after its package and version, a
                   known platform and known servers, every dest under ${INSTALL}/,
                   member names that stay inside the wheel, one set of bytes per
                   dest and platform, no dest another file group already uses.
                   A licence may name no text_file only when its text_dest is
                   exactly the dest of dist-info members of nvidia_files under
                   that licence (the EULA text every NVIDIA wheel carries);
  * crow files   - the Crow-wide group (crow_files: the dictation model) has every
                   field, a pinned 40-hex revision, a status of published or
                   upstream, a dest under ${INSTALL}/ that no other file uses, and
                   holds model.bin under ${INSTALL}/models/whisper-small/, the
                   directory cli/crow_voice.py loads;
  * point lists  - the point ids are also written by hand in the code (POINT_LISTS
                   below: the CLI list, the boot icons, the setup page, ...). Each
                   such list must name exactly the points of stack.json, or for a
                   per-point table at least each of them; the mock's selection only
                   real ones. A point added to stack.json and forgotten in one place
                   turns this red (#340).

ONLINE (--online): bytes, sha256 and revision of every file re-read from the
source - the tree API at the pinned revision (lfs oid for LFS files, a download
of at most 1 MiB for small ones), raw GitHub for a GitHub source. A mirror-pending
file is checked at its source, and the planned location in our repo is looked
at: present and equal is a NOTE (flip it to published), present and different
is a failure. A repo whose HEAD moved past the pin is a NOTE: the pin still holds.
The crow_files group is re-read the same way at its pinned revision (a non-LFS
file there may be up to CROW_SMALL, the dictation tokenizer is 2.2 MB).

Usage:  check_stack.py [--manifest <file>] [--online]
Exit 0 = every check holds.  1 = at least one does not.  2 = setup error.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MANIFEST = os.path.join(REPO, "manifests", "stack.json")

SCHEMA = "crow-stack/1"
POINT_IDS = ("flash-next", "27b", "image-stack", "media-stack")
# engine.kind: crow-nest's serve (the default, a CNQ container in CROW_CNQ) or
# llama.cpp's llama-server (a GGUF given with -m), #340.
ENGINE_KINDS = ("serve", "llama-server")
# A point's optional video server (#340): started by Crow on first use, never at
# boot; its program lives in an unpacked runtime (runtime.<platform>.dir).
VIDEO_FIELDS = ("binary", "argv", "port", "readiness", "runtime")
STATUSES = ("published", "mirror-pending", "upstream")
PLACEHOLDERS = ("INSTALL", "MODELS")
FILE_FIELDS = ("id", "repo", "path", "revision", "bytes", "sha256", "dest", "source",
               "status", "license", "role")
SOURCE_FIELDS = ("host", "repo", "path", "revision", "bytes", "sha256", "license")
# Where a published or upstream file is fetched from (#340); optional, default
# huggingface. A mirror-pending file names its host in `source`.
HOSTS = ("huggingface", "github", "github-release")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REPO_ID = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+$")
PLACEHOLDER = re.compile(r"\$\{([^}]*)\}")
PATH_ROOTS = ("${INSTALL}/", "${MODELS}/")
# absolute or personal paths: a drive letter, a UNC root, a home directory
# A Hugging Face repo id, `<namespace>/<name>` (#343). The namespace is the public
# owner the installer downloads from, so it is not held to the user-name check.
REPO_ID = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
PERSONAL = re.compile(r"(?i)(\b[a-z]:[\\/]|\\\\[a-z0-9]|(^|[\s\"'(=])~[\\/]|[\\/](users|home)[\\/])")
SMALL = 1 << 20
CROW_SMALL = 8 << 20
CROW_FILE_FIELDS = ("id", "repo", "path", "revision", "bytes", "sha256", "dest", "status",
                    "license", "role")
CROW_STATUSES = ("published", "upstream")
WHISPER_DIR = "${INSTALL}/models/whisper-small/"
PLATFORMS = ("windows", "linux")
# nvidia_files (CrowSetup crate::nvidia): the servers a wheel can serve, where the
# wheels come from, and the fields of a wheel and of a member it takes.
NVIDIA_SERVERS = ("serve", "llama-server", "sd-server")
PYPI_FILES = "https://files.pythonhosted.org/packages/"
NVIDIA_FIELDS = ("id", "package", "version", "platform", "servers", "url", "bytes", "sha256",
                 "dest", "status", "license", "role", "extract")
NVIDIA_MEMBER_FIELDS = ("member", "dest", "bytes", "sha256")


def point_platforms(pt) -> "tuple[str, ...]":
    """The platforms a point runs on: its `platforms`, else both (#340)."""
    return tuple(pt.get("platforms") or PLATFORMS)
BIN_DIR = "${INSTALL}/bin/"
HF = "https://huggingface.co"


def user_names() -> "list[str]":
    names = set()
    for var in ("USERNAME", "USER", "LOGNAME"):
        v = (os.environ.get(var) or "").strip()
        if len(v) >= 3:
            names.add(v.lower())
    home = os.path.basename(os.path.expanduser("~").rstrip("\\/"))
    if len(home) >= 3:
        names.add(home.lower())
    return sorted(names)


def strings(node, where=""):
    """Every (location, string) in the document, keys included."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield where + "/" + k, k
            yield from strings(v, where + "/" + k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from strings(v, "%s[%d]" % (where, i))
    elif isinstance(node, str):
        yield where, node


def is_path(value: str) -> bool:
    return "/" in value or "\\" in value or value.startswith("${")


class Report:
    def __init__(self):
        self.lines = []
        self.failed = 0
        self.total = 0

    def check(self, label: str, problems: "list[str]", ok_detail: str = ""):
        self.total += 1
        if problems:
            self.failed += 1
            self.lines.append("  FAIL     %-28s %s" % (label, problems[0]))
            for p in problems[1:]:
                self.lines.append("  %-37s %s" % ("", p))
        else:
            self.lines.append("  OK       %-28s %s" % (label, ok_detail))

    def note(self, text: str):
        self.lines.append("  NOTE     %s" % text)


def host_problems(f) -> "list[str]":
    """#340: where an upstream or published file lives. `host` is huggingface
    (the default), github (a raw file at a commit) or github-release (a release
    asset, which needs its `tag`; `revision` is the tag's commit). `gated`: a
    Hugging Face repo whose files need the user's token."""
    fid, p = f.get("id", "?"), []
    host = f.get("host", "huggingface")
    if f["status"] == "mirror-pending" and "host" in f:
        p.append("file %s is mirror-pending: the host is its source's" % fid)
    if host not in HOSTS:
        p.append("file %s host %r is not one of %s" % (fid, host, ", ".join(HOSTS)))
    if host == "github-release" and not (isinstance(f.get("tag"), str) and f["tag"]):
        p.append("file %s on github-release needs a tag" % fid)
    if "tag" in f and host != "github-release":
        p.append("file %s carries a tag only with host github-release" % fid)
    if "gated" in f and f["gated"] is not True:
        p.append("file %s: gated must be true or absent" % fid)
    if f.get("gated") is True and host != "huggingface":
        p.append("file %s: gated only on host huggingface" % fid)
    return p


def check_schema(doc) -> "list[str]":
    p = []
    if doc.get("schema") != SCHEMA:
        p.append("schema is %r, expected %r" % (doc.get("schema"), SCHEMA))
    ph = doc.get("placeholders")
    if not isinstance(ph, dict) or sorted(ph) != sorted(PLACEHOLDERS):
        p.append("placeholders must declare exactly %s" % ", ".join(PLACEHOLDERS))
    for key, kind in (("licenses", dict), ("files", list), ("derived", list), ("points", list)):
        if not isinstance(doc.get(key), kind):
            p.append("%s missing or not a %s" % (key, kind.__name__))
    if p:
        return p
    licenses = doc["licenses"]
    ids = {}
    for f in doc["files"]:
        fid = f.get("id", "?")
        missing = [k for k in FILE_FIELDS if k not in f]
        if missing:
            p.append("file %s lacks %s" % (fid, ", ".join(missing)))
            continue
        if fid in ids:
            p.append("file id %s twice" % fid)
        ids[fid] = f
        if f["status"] not in STATUSES:
            p.append("file %s status %r is not one of %s" % (fid, f["status"], ", ".join(STATUSES)))
        if not isinstance(f["bytes"], int) or isinstance(f["bytes"], bool) or f["bytes"] <= 0:
            p.append("file %s bytes %r is not a positive integer" % (fid, f["bytes"]))
        if not isinstance(f["sha256"], str) or not HEX64.match(f["sha256"]):
            p.append("file %s sha256 is not 64 lowercase hex" % fid)
        if not isinstance(f["repo"], str) or not REPO_ID.match(f["repo"]):
            p.append("file %s repo %r is not owner/name" % (fid, f["repo"]))
        if not isinstance(f["path"], str) or not f["path"] or f["path"].startswith("/"):
            p.append("file %s path %r is not repo-relative" % (fid, f["path"]))
        if f["license"] not in licenses:
            p.append("file %s licence %r is not declared under licenses" % (fid, f["license"]))
        p.extend(host_problems(f))
        if f["status"] in ("published", "upstream"):
            if not isinstance(f["revision"], str) or not HEX40.match(f["revision"]):
                p.append("file %s (%s) needs a 40-hex commit revision" % (fid, f["status"]))
            if f["source"] is not None:
                p.append("file %s (%s) carries a source; only mirror-pending does" % (fid, f["status"]))
        elif f["status"] == "mirror-pending":
            if f["revision"] is not None:
                p.append("file %s is mirror-pending: revision must be null until the upload" % fid)
            s = f["source"]
            if not isinstance(s, dict) or [k for k in SOURCE_FIELDS if k not in s]:
                p.append("file %s source needs %s" % (fid, ", ".join(SOURCE_FIELDS)))
            else:
                if s["host"] not in ("huggingface", "github"):
                    p.append("file %s source host %r unknown" % (fid, s["host"]))
                if not isinstance(s["revision"], str) or not HEX40.match(s["revision"]):
                    p.append("file %s source needs a 40-hex commit revision" % fid)
                if s["bytes"] != f["bytes"] or s["sha256"] != f["sha256"]:
                    p.append("file %s bytes/sha256 differ from its source's" % fid)
                if s["license"] not in licenses:
                    p.append("file %s source licence %r is not declared" % (fid, s["license"]))
    dests = {}
    for f in doc["files"]:
        d = f.get("dest")
        if d in dests:
            p.append("files %s and %s share dest %s" % (dests[d], f.get("id"), d))
        dests[d] = f.get("id")
    for name, lic in licenses.items():
        for k in ("name", "non_commercial", "show_at_install", "text_file", "summary"):
            if k not in lic:
                p.append("licence %s lacks %s" % (name, k))
        if lic.get("non_commercial") and not lic.get("show_at_install"):
            p.append("licence %s is non-commercial but not shown at install" % name)
        # #340: the selection screen writes "<covers>: <name>" under the point.
        if lic.get("show_at_install") and not (isinstance(lic.get("covers"), str) and lic["covers"]):
            p.append("licence %s is shown at install but names nothing it covers" % name)
        if lic.get("text_file") is None and "text_file" in lic \
                and nvidia_licence_text(doc, name, lic.get("text_dest")):
            continue  # the text comes out of NVIDIA's wheels (nvidia_files)
        if lic.get("text_file") is None and "text_file" in lic                 and str(lic.get("url") or "").startswith("https://")                 and name in package_licence_ids(doc):
            continue  # a file inside Crow's package; the owner publishes the text at url
        tf = ids.get(lic.get("text_file"))
        if tf is None or tf.get("role") != "license":
            p.append("licence %s text_file %r is not a file with role license"
                     % (name, lic.get("text_file")))
    for d in doc["derived"]:
        for k in ("id", "tool", "argv", "inputs", "dest", "outputs", "bytes"):
            if k not in d:
                p.append("derived %s lacks %s" % (d.get("id", "?"), k))
    for pt in doc["points"]:
        for k in ("id", "menu", "files", "derived", "bytes", "engine", "image_server",
                  "crow_env", "preflight"):
            if k not in pt:
                p.append("point %s lacks %s" % (pt.get("id", "?"), k))
        plats = pt.get("platforms")
        if plats is not None:
            if not isinstance(plats, list) or not plats or len(set(plats)) != len(plats) \
                    or set(plats) - set(PLATFORMS):
                p.append("point %s platforms %r is not a list of %s"
                         % (pt.get("id", "?"), plats, " / ".join(PLATFORMS)))
            elif sorted(plats) != sorted(PLATFORMS) and not pt.get("_platforms"):
                p.append("point %s runs on %s only and gives no reason (_platforms)"
                         % (pt.get("id", "?"), ", ".join(plats)))
        eng = pt.get("engine")
        if isinstance(eng, dict) and eng.get("kind", "serve") not in ENGINE_KINDS:
            p.append("point %s engine kind %r is not one of %s"
                     % (pt.get("id", "?"), eng.get("kind"), ", ".join(ENGINE_KINDS)))
        vs = pt.get("video_server")
        if vs is not None:
            if not isinstance(vs, dict):
                p.append("point %s video_server is not an object or null" % pt.get("id", "?"))
            else:
                for k in VIDEO_FIELDS:
                    if k not in vs:
                        p.append("point %s video_server lacks %s" % (pt.get("id", "?"), k))
    got = [pt.get("id") for pt in doc["points"]]
    if got != list(POINT_IDS):
        p.append("points are %s, expected %s" % (got, list(POINT_IDS)))
    return p


def nvidia_licence_text(doc, name, text_dest) -> bool:
    """`text_dest` is exactly the dest of nvidia_files members that are the
    licence text in a wheel's dist-info, every wheel carrying them is under
    licence `name`, and no other member writes there."""
    if not isinstance(text_dest, str) or not text_dest.startswith("${INSTALL}/"):
        return False
    wheels = doc.get("nvidia_files")
    if not isinstance(wheels, list):
        return False
    hits = 0
    for w in wheels:
        if not isinstance(w, dict) or not isinstance(w.get("extract"), list):
            continue
        for m in w["extract"]:
            if not isinstance(m, dict) or m.get("dest") != text_dest:
                continue
            member = m.get("member")
            if not (isinstance(member, str) and re.fullmatch(r"[^/]+\.dist-info/(licenses/)?[^/]+", member)
                    and w.get("license") == name):
                return False
            hits += 1
    return hits > 0


def member_name_is_safe(name) -> bool:
    """A wheel member that stays inside the wheel: relative, `/`-separated, no
    empty, `.` or `..` part, no backslash, no drive."""
    return (isinstance(name, str) and bool(name) and not name.startswith("/") and "\\" not in name
            and all(part not in ("", ".", "..") and ":" not in part for part in name.split("/")))


def package_licence_ids(doc) -> "set[str]":
    return {e.get("license") for e in doc.get("package_licenses") or [] if isinstance(e, dict)}


def check_package_licenses(doc) -> "list[str]":
    """Licences of third-party files inside Crow's own package (the Windows package's
    MSVC runtime DLLs): declared, shown on the selection page, on a known platform."""
    p = []
    entries = doc.get("package_licenses")
    if not isinstance(entries, list):
        return ["package_licenses must be a list"]
    for e in entries:
        name = e.get("license") if isinstance(e, dict) else None
        lic = (doc.get("licenses") or {}).get(name)
        if lic is None:
            p.append("package licence %s is not declared" % name)
            continue
        if not lic.get("show_at_install"):
            p.append("package licence %s is not shown at install" % name)
        plats = e.get("platforms")
        if not isinstance(plats, list) or not plats or set(plats) - set(PLATFORMS):
            p.append("package licence %s platforms %r is not a list of %s" % (name, plats, " / ".join(PLATFORMS)))
    return p


def check_nvidia_files(doc) -> "list[str]":
    wheels = doc.get("nvidia_files")
    if wheels is None:
        return []
    if not isinstance(wheels, list):
        return ["nvidia_files is not a list"]
    p = []
    taken = {f.get("dest"): f.get("id") for group in ("files", "crow_files")
             for f in doc.get(group) or [] if isinstance(f, dict)}
    other_ids = {f.get("id") for group in ("files", "crow_files") for f in doc.get(group) or []
                 if isinstance(f, dict)}
    licenses = doc.get("licenses") or {}
    seen_ids, wheel_dests, member_at = set(), {}, {}

    def pos_int(v):
        return isinstance(v, int) and not isinstance(v, bool) and v > 0

    def under_install(v):
        return isinstance(v, str) and v.startswith("${INSTALL}/") and ".." not in v.split("/")

    for w in wheels:
        if not isinstance(w, dict):
            p.append("nvidia_files entry %r is not an object" % (w,))
            continue
        wid = w.get("id", "?")
        missing = [k for k in NVIDIA_FIELDS if k not in w]
        if missing:
            p.append("nvidia file %s lacks %s" % (wid, ", ".join(missing)))
            continue
        if wid in seen_ids or wid in other_ids:
            p.append("nvidia file id %s twice (files, crow_files and nvidia_files share one id space)" % wid)
        seen_ids.add(wid)
        if not isinstance(w["sha256"], str) or not HEX64.match(w["sha256"]):
            p.append("nvidia file %s sha256 is not 64 lowercase hex" % wid)
        if not pos_int(w["bytes"]):
            p.append("nvidia file %s bytes %r is not a positive integer" % (wid, w["bytes"]))
        url, pkg, ver = w["url"], w["package"], w["version"]
        if not (isinstance(url, str) and url.startswith(PYPI_FILES) and url.endswith(".whl")):
            p.append("nvidia file %s url %r is not a wheel on %s" % (wid, url, PYPI_FILES))
        elif not (isinstance(pkg, str) and isinstance(ver, str)
                  and url.rsplit("/", 1)[1].startswith("%s-%s-" % (pkg.replace("-", "_"), ver))):
            p.append("nvidia file %s url names another wheel than %s %s" % (wid, pkg, ver))
        if w["platform"] not in PLATFORMS:
            p.append("nvidia file %s platform %r is not one of %s" % (wid, w["platform"], ", ".join(PLATFORMS)))
        servers = w["servers"]
        if not isinstance(servers, list) or not servers or not all(x in NVIDIA_SERVERS for x in servers):
            p.append("nvidia file %s servers %r are not a list of %s" % (wid, servers, ", ".join(NVIDIA_SERVERS)))
        if not under_install(w["dest"]):
            p.append("nvidia file %s dest %r is not under ${INSTALL}/" % (wid, w["dest"]))
        elif w["dest"] in wheel_dests or w["dest"] in taken:
            p.append("nvidia file %s dest %s is used twice" % (wid, w["dest"]))
        wheel_dests[w["dest"]] = wid
        if w["status"] != "upstream":
            p.append("nvidia file %s status %r: NVIDIA's wheels are upstream" % (wid, w["status"]))
        if w["license"] not in licenses:
            p.append("nvidia file %s licence %r is not declared under licenses" % (wid, w["license"]))
        if not isinstance(w["extract"], list) or not w["extract"]:
            p.append("nvidia file %s extracts nothing" % wid)
            continue
        for m in w["extract"]:
            if not isinstance(m, dict) or [k for k in NVIDIA_MEMBER_FIELDS if k not in m]:
                p.append("nvidia file %s member %r needs %s" % (wid, m, ", ".join(NVIDIA_MEMBER_FIELDS)))
                continue
            name = m["member"]
            if not member_name_is_safe(name):
                p.append("nvidia file %s member %r leaves the wheel" % (wid, name))
            if not under_install(m["dest"]):
                p.append("nvidia file %s member %s dest %r is not under ${INSTALL}/" % (wid, name, m["dest"]))
            elif m["dest"] in taken or m["dest"] in wheel_dests:
                p.append("nvidia file %s member %s dest %s is another file's" % (wid, name, m["dest"]))
            if not isinstance(m["sha256"], str) or not HEX64.match(m["sha256"]):
                p.append("nvidia file %s member %s sha256 is not 64 lowercase hex" % (wid, name))
            if not pos_int(m["bytes"]):
                p.append("nvidia file %s member %s bytes %r is not a positive integer" % (wid, name, m["bytes"]))
            key = (w["platform"], m["dest"])
            got = (m["bytes"], m["sha256"])
            if key in member_at and member_at[key][0] != got:
                p.append("nvidia files %s and %s write different bytes to %s on %s"
                         % (member_at[key][1], wid, m["dest"], w["platform"]))
            member_at.setdefault(key, (got, wid))
    return p


def check_paths(doc) -> "list[str]":
    p = []
    names = user_names()
    for where, s in strings(doc):
        for name in PLACEHOLDER.findall(s):
            if name not in PLACEHOLDERS:
                p.append("%s: unknown placeholder ${%s}" % (where, name))
        if PERSONAL.search(s):
            p.append("%s: absolute or personal path in %r" % (where, s[:80]))
        low = s.lower()
        if where.endswith("/repo") and REPO_ID.fullmatch(s):
            low = low.split("/", 1)[1]
        for n in names:
            if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(n), low):
                p.append("%s: names the user %r" % (where, n))
    for f in doc["files"]:
        if not str(f.get("dest", "")).startswith(PATH_ROOTS):
            p.append("file %s dest %r does not start with ${INSTALL}/ or ${MODELS}/"
                     % (f.get("id"), f.get("dest")))
    for d in doc["derived"]:
        for v in [d.get("dest")] + list(d.get("argv") or []):
            if not str(v).startswith(PATH_ROOTS):
                p.append("derived %s path %r is not under a placeholder" % (d.get("id"), v))
    for pt in doc["points"]:
        for label, values in path_values(pt):
            for v in values:
                if is_path(v) and not v.startswith(PATH_ROOTS) and v != "${INSTALL}":
                    p.append("point %s %s %r is not under a placeholder" % (pt.get("id"), label, v))
    return p


def path_values(pt):
    eng = pt.get("engine") or {}
    yield "engine.binary", list((eng.get("binary") or {}).values())
    yield "engine.cwd", [eng.get("cwd", "")]
    yield "engine.env", list((eng.get("env") or {}).values())
    yield "engine.argv", list(eng.get("argv") or [])
    yield "engine.dirs", list(eng.get("dirs") or [])
    img = pt.get("image_server")
    if img:
        yield "image_server.binary", list((img.get("binary") or {}).values())
        yield "image_server.argv", list(img.get("argv") or [])
    vs = pt.get("video_server")
    if vs:
        yield "video_server.binary", list((vs.get("binary") or {}).values())
        yield "video_server.argv", list(vs.get("argv") or [])
        yield "video_server.runtime", [rt.get("dir", "") for rt in (vs.get("runtime") or {}).values()
                                       if isinstance(rt, dict)]
    yield "crow_env", list((pt.get("crow_env") or {}).values())


def check_references(doc) -> "list[str]":
    p = []
    files = {f["id"]: f for f in doc["files"]}
    derived = {d["id"]: d for d in doc["derived"]}
    used_f, used_d = set(), set()
    for d in derived.values():
        for i in d["inputs"]:
            if i not in files:
                p.append("derived %s input %s is not a file" % (d["id"], i))
    for pt in doc["points"]:
        for fid in pt["files"]:
            if fid not in files:
                p.append("point %s names file %s, which is not declared" % (pt["id"], fid))
            used_f.add(fid)
        if len(set(pt["files"])) != len(pt["files"]):
            p.append("point %s names a file twice" % pt["id"])
        for did in pt["derived"]:
            if did not in derived:
                p.append("point %s names derived %s, which is not declared" % (pt["id"], did))
                continue
            used_d.add(did)
            for i in derived[did]["inputs"]:
                if i not in pt["files"]:
                    p.append("point %s derives %s without its input %s" % (pt["id"], did, i))
    for fid in files:
        if fid not in used_f:
            p.append("file %s is used by no point" % fid)
    for did in derived:
        if did not in used_d:
            p.append("derived %s is used by no point" % did)
    return p


def point_sums(doc, pt) -> dict:
    files = {f["id"]: f for f in doc["files"]}
    derived = {d["id"]: d for d in doc["derived"]}
    s = {"published": 0, "mirror_pending": 0, "upstream": 0}
    for fid in pt["files"]:
        f = files[fid]
        s[f["status"].replace("-", "_")] += f["bytes"]
    s["files"] = s["published"] + s["mirror_pending"] + s["upstream"]
    s["derived"] = sum(derived[d]["bytes"] for d in pt["derived"])
    # #340: an unpacked runtime is produced on the machine like a derived file
    # (its archive is deleted afterwards; the peak holds both).
    runtimes = ((pt.get("video_server") or {}).get("runtime") or {}).values()
    s["derived"] += max([rt.get("bytes") or 0 for rt in runtimes if isinstance(rt, dict)] or [0])
    s["disk"] = s["files"] + s["derived"]
    return s


def check_sums(doc) -> "list[str]":
    p = []
    for d in doc["derived"]:
        total = sum(o["bytes"] for o in d["outputs"])
        if total != d["bytes"]:
            p.append("derived %s bytes %d, its outputs sum to %d" % (d["id"], d["bytes"], total))
    for pt in doc["points"]:
        want = point_sums(doc, pt)
        got = pt["bytes"]
        for k, v in want.items():
            if got.get(k) != v:
                p.append("point %s bytes.%s is %r, the listed files sum to %d"
                         % (pt["id"], k, got.get(k), v))
        if pt["preflight"].get("disk_bytes") != want["disk"]:
            p.append("point %s preflight.disk_bytes is %r, files + derived = %d"
                     % (pt["id"], pt["preflight"].get("disk_bytes"), want["disk"]))
    return p


def flag_value(argv, flag):
    if flag in argv and argv.index(flag) + 1 < len(argv):
        return argv[argv.index(flag) + 1]
    return None


FOLDER_KIND = re.compile(r"^[a-z][a-z0-9_]*$")


def runtime_problems(pid, plat, rt) -> "list[str]":
    """#340: the optional unpack fields of video_server.runtime.<platform>:
    `strip` (the archive's top folder), `bytes` (unpacked size), `model_paths`
    (ComfyUI's extra_model_paths.yaml: file inside the runtime, base under a
    placeholder, folder kinds)."""
    p, at = [], "point %s video_server.runtime.%s" % (pid, plat)
    if "strip" in rt:
        v = rt["strip"]
        if not isinstance(v, str) or not v or any(c in v for c in "/\\:") or v in (".", ".."):
            p.append("%s.strip %r is not one folder name" % (at, v))
    if "bytes" in rt:
        v = rt["bytes"]
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            p.append("%s.bytes %r is not a positive integer" % (at, v))
    mp = rt.get("model_paths")
    if mp is not None:
        if not isinstance(mp, dict):
            return p + ["%s.model_paths is not an object" % at]
        f = mp.get("file")
        if not isinstance(f, str) or not f or f.startswith(("/", "\\")) \
                or ".." in f.replace("\\", "/").split("/") or ":" in f:
            p.append("%s.model_paths.file %r is not inside the runtime" % (at, f))
        base = mp.get("base")
        if not isinstance(base, str) or not base.startswith(PATH_ROOTS):
            p.append("%s.model_paths.base %r does not start with %s" % (at, base, " or ".join(PATH_ROOTS)))
        folders = mp.get("folders")
        if not isinstance(folders, list) or not folders \
                or not all(isinstance(x, str) and FOLDER_KIND.match(x) for x in folders):
            p.append("%s.model_paths.folders must list folder kinds" % at)
    return p


def check_wiring(doc) -> "list[str]":
    p = []
    files = {f["id"]: f for f in doc["files"]}
    derived = {d["id"]: d for d in doc["derived"]}
    for pt in doc["points"]:
        pid = pt["id"]
        installed = {files[f]["dest"]: files[f] for f in pt["files"] if f in files}
        produced = set()
        for did in pt["derived"]:
            d = derived.get(did)
            if d:
                produced.update(d["dest"] + "/" + o["path"] for o in d["outputs"])
        eng = pt["engine"]
        dirs = set(eng.get("dirs") or [])
        env = eng.get("env") or {}
        for k, v in env.items():
            if is_path(v) and v not in installed:
                p.append("point %s env %s=%s is no file this point installs" % (pid, k, v))
        argv = list(eng.get("argv") or [])
        llama = eng.get("kind", "serve") == "llama-server"
        # serve loads the CNQ container named by CROW_CNQ; llama-server the GGUF after -m.
        model = installed.get(flag_value(argv, "-m") if llama else env.get("CROW_CNQ"))
        if model is None or model.get("role") != "container":
            p.append("point %s %s does not name its container"
                     % (pid, "llama-server -m" if llama else "CROW_CNQ"))
        else:
            ident = eng.get("identity") or {}
            if ident.get("path") != "/props" or ident.get("field") != "model_path" \
                    or ident.get("endswith") != model["path"].rsplit("/", 1)[-1]:
                p.append("point %s identity must be /props model_path ending in %s"
                         % (pid, model["path"].rsplit("/", 1)[-1]))
        mmproj = flag_value(argv, "--mmproj")
        if llama and mmproj is not None and (installed.get(mmproj) or {}).get("role") != "projector":
            p.append("point %s llama-server --mmproj %s is no projector this point installs" % (pid, mmproj))
        ready = eng.get("readiness") or {}
        if ready.get("path") != "/health" or ready.get("json") != {"status": "ok"}:
            p.append("point %s readiness must be GET /health answering {\"status\": \"ok\"}" % pid)
        if flag_value(argv, "--port") != str(eng.get("port")):
            p.append("point %s engine --port %r differs from port %r"
                     % (pid, flag_value(argv, "--port"), eng.get("port")))
        slot = flag_value(argv, "--slot-save-path")
        if (slot is not None or not llama) and (slot is None or slot not in dirs):
            p.append("point %s --slot-save-path %r is not created (engine.dirs)" % (pid, slot))
        for v in argv:
            if is_path(v) and v not in dirs and v not in installed:
                p.append("point %s engine argv path %s is neither a created dir nor a file" % (pid, v))
        img = pt["image_server"]
        if img:
            iargv = list(img.get("argv") or [])
            if flag_value(iargv, "--listen-port") != str(img.get("port")):
                p.append("point %s sd-server --listen-port differs from port %r" % (pid, img.get("port")))
            if img.get("port") == eng.get("port"):
                p.append("point %s engine and image server share port %r" % (pid, img.get("port")))
            if (img.get("readiness") or {}).get("status") != 200:
                p.append("point %s image readiness must expect HTTP 200" % pid)
            for v in iargv:
                if is_path(v) and v not in installed and v not in produced:
                    p.append("point %s sd-server path %s is neither installed nor derived" % (pid, v))
        vs = pt.get("video_server")
        if vs:
            vargv = list(vs.get("argv") or [])
            if flag_value(vargv, "--port") != str(vs.get("port")):
                p.append("point %s video server --port differs from port %r" % (pid, vs.get("port")))
            if vs.get("port") in (eng.get("port"), (img or {}).get("port")):
                p.append("point %s video server shares port %r" % (pid, vs.get("port")))
            if (vs.get("readiness") or {}).get("status") != 200:
                p.append("point %s video readiness must expect HTTP 200" % pid)
            roots = []
            for plat, rt in sorted((vs.get("runtime") or {}).items()):
                fid = (rt or {}).get("file")
                if fid not in pt["files"] or (files.get(fid) or {}).get("role") != "runtime":
                    p.append("point %s video_server.runtime.%s.file %r is no runtime file of this point"
                             % (pid, plat, fid))
                roots.append((rt or {}).get("dir") or "")
                p.extend(runtime_problems(pid, plat, rt or {}))
            for v in vargv + list((vs.get("binary") or {}).values()):
                if is_path(v) and v not in installed and v not in produced \
                        and not any(r and v.startswith(r + "/") for r in roots):
                    p.append("point %s video server path %s is neither installed nor in its runtime"
                             % (pid, v))
        for k, v in (pt.get("crow_env") or {}).items():
            if is_path(v) and not any(x == v or x.startswith(v + "/") for x in list(installed) + list(produced)):
                p.append("point %s crow_env %s=%s holds nothing this point installs" % (pid, k, v))
        line = (pt.get("menu") or {}).get("line", "")
        if not line:
            p.append("point %s has no menu line" % pid)
        for k in re.findall(r"(\d+)k context", line):
            if int(k) * 1000 > int(eng.get("context") or 0):
                p.append("point %s menu claims %sk context, the engine serves %r"
                         % (pid, k, eng.get("context")))
        # #196: the operating-point window's own line (cli/crow_boot_gui.py shows
        # it; the terminal menu keeps `line`). Sentences, no dash; its context
        # claim is held to the engine like the menu's. A user name in it is the
        # "placeholders and paths" check's, which walks every string.
        gui = (pt.get("menu") or {}).get("gui", "")
        if not gui:
            p.append("point %s has no menu gui text (the operating-point window's line)" % pid)
        if "\u2014" in gui or "\u2013" in gui:
            p.append("point %s menu gui text has a dash; the window writes sentences" % pid)
        for k in re.findall(r"(\d+)k context", gui):
            if int(k) * 1000 > int(eng.get("context") or 0):
                p.append("point %s menu gui text claims %sk context, the engine serves %r"
                         % (pid, k, eng.get("context")))
    return p


def check_platforms(doc) -> "list[str]":
    """#341: both platforms can start every point (cli/crow_boot.py plan_point),
    unless the point names fewer in `platforms` with a reason (#340)."""
    p = []
    lib_path = doc.get("lib_path")
    if not isinstance(lib_path, dict) or sorted(set(lib_path) - set(PLATFORMS)):
        p.append("lib_path must map %s to folder lists" % " / ".join(PLATFORMS))
        lib_path = {}
    for plat, dirs in lib_path.items():
        if not isinstance(dirs, list) or not all(isinstance(d, str) and d.startswith("${INSTALL}/")
                                                 for d in dirs):
            p.append("lib_path.%s %r is not a list of ${INSTALL}/ folders" % (plat, dirs))
    for pt in doc["points"]:
        plats = point_platforms(pt)
        specs = [("engine", pt.get("engine") or {})]
        if pt.get("image_server"):
            specs.append(("image_server", pt["image_server"]))
        vs = pt.get("video_server")
        if vs:
            # The video server's program is in its unpacked runtime, not in bin/,
            # so the bin/ rules below do not apply to it.
            binary, runtime = vs.get("binary") or {}, vs.get("runtime") or {}
            for name, m in (("binary", binary), ("runtime", runtime)):
                if sorted(m) != sorted(plats):
                    p.append("point %s video_server.%s names %s, expected %s"
                             % (pt["id"], name, sorted(m) or "nothing", " and ".join(plats)))
            for plat in plats:
                root = ((runtime.get(plat) or {}).get("dir") or "").rstrip("/")
                if plat in binary and (not root or not binary[plat].startswith(root + "/")):
                    p.append("point %s video_server.binary.%s is not inside its runtime dir"
                             % (pt["id"], plat))
        for what, spec in specs:
            binary = spec.get("binary") or {}
            if sorted(binary) != sorted(plats):
                p.append("point %s %s.binary names %s, expected %s"
                         % (pt["id"], what, sorted(binary) or "nothing", " and ".join(plats)))
                continue
            if not all(b.startswith(BIN_DIR) for b in binary.values()):
                p.append("point %s %s.binary is not under %s" % (pt["id"], what, BIN_DIR))
            win, lin = binary.get("windows"), binary.get("linux")
            if win is not None and not win.endswith(".exe"):
                p.append("point %s %s.binary.windows %s is not an .exe" % (pt["id"], what, win))
            if win is not None and lin is not None and (lin.endswith(".exe") or win[:-4] != lin):
                p.append("point %s %s.binary: windows %s and linux %s are not one program"
                         % (pt["id"], what, win, lin))
            if what == "engine" and lin is not None \
                    and lin.rsplit("/", 1)[0] not in (lib_path.get("linux") or []):
                p.append("point %s: lib_path.linux lacks %s, where the NVRTC beside serve lives"
                         % (pt["id"], lin.rsplit("/", 1)[0]))
            extra = spec.get("argv_platform")
            if extra is not None and (not isinstance(extra, dict) or set(extra) - set(PLATFORMS)):
                p.append("point %s %s.argv_platform names a platform other than %s"
                         % (pt["id"], what, " / ".join(PLATFORMS)))
    return p


def check_crow_files(doc) -> "list[str]":
    group = doc.get("crow_files")
    if not isinstance(group, list) or not group:
        return ["crow_files missing or empty (the dictation model every install gets)"]
    p = []
    file_ids = {f.get("id") for f in doc.get("files") or []}
    dests = {f.get("dest"): f.get("id") for f in doc.get("files") or []}
    seen = set()
    for f in group:
        if not isinstance(f, dict):
            p.append("crow_files entry %r is not an object" % (f,))
            continue
        fid = f.get("id", "?")
        missing = [k for k in CROW_FILE_FIELDS if k not in f]
        if missing:
            p.append("crow file %s lacks %s" % (fid, ", ".join(missing)))
            continue
        if fid in seen or fid in file_ids:
            p.append("crow file id %s twice (crow_files and files share one id space)" % fid)
        seen.add(fid)
        if f["status"] not in CROW_STATUSES:
            p.append("crow file %s status %r is not one of %s" % (fid, f["status"], ", ".join(CROW_STATUSES)))
        if not isinstance(f["revision"], str) or not HEX40.match(f["revision"]):
            p.append("crow file %s needs a 40-hex commit revision" % fid)
        if not isinstance(f["bytes"], int) or isinstance(f["bytes"], bool) or f["bytes"] <= 0:
            p.append("crow file %s bytes %r is not a positive integer" % (fid, f["bytes"]))
        if not isinstance(f["sha256"], str) or not HEX64.match(f["sha256"]):
            p.append("crow file %s sha256 is not 64 lowercase hex" % fid)
        if not isinstance(f["repo"], str) or not REPO_ID.match(f["repo"]):
            p.append("crow file %s repo %r is not owner/name" % (fid, f["repo"]))
        if not isinstance(f["path"], str) or not f["path"] or f["path"].startswith("/"):
            p.append("crow file %s path %r is not repo-relative" % (fid, f["path"]))
        if not isinstance(f["license"], str) or not f["license"]:
            p.append("crow file %s has no licence" % fid)
        d = f["dest"]
        if not str(d).startswith("${INSTALL}/"):
            p.append("crow file %s dest %r does not start with ${INSTALL}/" % (fid, d))
        if d in dests:
            p.append("crow file %s and %s share dest %s" % (fid, dests[d], d))
        dests[d] = fid
    if WHISPER_DIR + "model.bin" not in {f.get("dest") for f in group if isinstance(f, dict)}:
        p.append("crow_files holds no %smodel.bin, the file cli/crow_voice.py loads by" % WHISPER_DIR)
    return p


# ---- online ----

def hf_token(env=None, home=None):
    """#340: the user's Hugging Face token, where huggingface_hub 1.21 reads it:
    HF_TOKEN, HUGGING_FACE_HUB_TOKEN, then the file at HF_TOKEN_PATH, else
    $HF_HOME/token, else ${XDG_CACHE_HOME:-~/.cache}/huggingface/token. The
    installer's fetch.rs find_hf_token reads the same places."""
    env = os.environ if env is None else env
    home = os.path.expanduser("~") if home is None else home
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        if (env.get(key) or "").strip():
            return env[key].strip()
    path = env.get("HF_TOKEN_PATH") or os.path.join(
        env.get("HF_HOME") or os.path.join(env.get("XDG_CACHE_HOME") or os.path.join(home, ".cache"),
                                           "huggingface"), "token")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def fetch(url: str, limit: int = 0, tries: int = 16):
    """(body, headers); Hugging Face resets connections, so retry with pauses.
    A token goes to https://huggingface.co only (a gated repo hides its sha256)."""
    last = None
    headers = {"User-Agent": "crow-check-stack"}
    if url.startswith(HF + "/"):
        token = hf_token()
        if token:
            headers["Authorization"] = "Bearer " + token
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read(limit + 1) if limit else r.read()
                if limit and len(body) > limit:
                    raise ValueError("%s is larger than %d bytes" % (url, limit))
                return body, r.headers
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                raise
            last = e
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            last = e
        time.sleep(min(2 + 3 * i, 20))
    raise RuntimeError("giving up on %s: %s" % (url, last))


class Hub:
    def __init__(self):
        self.trees = {}
        self.heads = {}

    def head(self, repo):
        if repo not in self.heads:
            body, _ = fetch("%s/api/models/%s" % (HF, repo))
            self.heads[repo] = json.loads(body)["sha"]
        return self.heads[repo]

    def tree(self, repo, rev):
        key = (repo, rev)
        if key not in self.trees:
            url = "%s/api/models/%s/tree/%s?recursive=true&expand=true" % (HF, repo, rev)
            entries = {}
            while url:
                body, headers = fetch(url)
                for e in json.loads(body):
                    if e.get("type") == "file":
                        entries[e["path"]] = e
                url = None
                for part in (headers.get("Link") or "").split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")
            self.trees[key] = entries
        return self.trees[key]

    def measure(self, repo, rev, path, limit=SMALL):
        """(bytes, sha256) at the source, or raise."""
        e = self.tree(repo, rev).get(path)
        if e is None:
            raise LookupError("%s@%s has no %s" % (repo, rev[:12], path))
        if e.get("lfs"):
            if not HEX64.match(e["lfs"]["oid"] or ""):
                raise LookupError("%s@%s hides the sha256 of %s (a gated repo): set HF_TOKEN or log in "
                                  "with the Hugging Face CLI after accepting its licence" % (repo, rev[:12], path))
            return e["size"], e["lfs"]["oid"]
        body, _ = fetch("%s/%s/resolve/%s/%s" % (HF, repo, rev, path), limit=limit)
        return len(body), hashlib.sha256(body).hexdigest()


def github_measure(repo, rev, path):
    body, _ = fetch("https://raw.githubusercontent.com/%s/%s/%s" % (repo, rev, path), limit=SMALL)
    return len(body), hashlib.sha256(body).hexdigest()


def release_measure(repo, tag, rev, path):
    """(bytes, sha256) of a release asset from the GitHub API's `digest`, without
    the download; raises when the tag no longer points at `rev`."""
    body, _ = fetch("https://api.github.com/repos/%s/git/ref/tags/%s" % (repo, tag))
    obj = json.loads(body)["object"]
    if obj["type"] == "tag":
        body, _ = fetch(obj["url"])
        obj = json.loads(body)["object"]
    if obj["sha"] != rev:
        raise LookupError("tag %s of %s points at %s, pinned %s" % (tag, repo, obj["sha"][:12], rev[:12]))
    body, _ = fetch("https://api.github.com/repos/%s/releases/tags/%s" % (repo, tag))
    for a in json.loads(body)["assets"]:
        if a["name"] == path:
            digest = a.get("digest") or ""
            if not digest.startswith("sha256:"):
                raise LookupError("release asset %s has no sha256 digest" % path)
            return a["size"], digest[len("sha256:"):]
    raise LookupError("release %s of %s has no asset %s" % (tag, repo, path))


def upstream_measure(f, hub):
    """(bytes, sha256, where) of a published or upstream file at its host."""
    host = f.get("host", "huggingface")
    if host == "github":
        return github_measure(f["repo"], f["revision"], f["path"]) + (
            "github:%s@%s" % (f["repo"], f["revision"][:12]),)
    if host == "github-release":
        return release_measure(f["repo"], f["tag"], f["revision"], f["path"]) + (
            "release:%s@%s" % (f["repo"], f["tag"]),)
    return hub.measure(f["repo"], f["revision"], f["path"]) + (
        "%s@%s" % (f["repo"], f["revision"][:12]),)


def check_online(doc, report: Report):
    hub = Hub()
    for f in doc["files"]:
        problems = []
        try:
            if f["status"] == "mirror-pending":
                s = f["source"]
                if s["host"] == "github":
                    got = github_measure(s["repo"], s["revision"], s["path"])
                else:
                    got = hub.measure(s["repo"], s["revision"], s["path"])
                where = "%s:%s@%s" % (s["host"], s["repo"], s["revision"][:12])
                try:
                    ours = hub.measure(f["repo"], hub.head(f["repo"]), f["path"])
                except LookupError:
                    ours = None
                if ours is not None:
                    if ours == (f["bytes"], f["sha256"]):
                        report.note("%s is already in %s: flip it to published" % (f["id"], f["repo"]))
                    else:
                        problems.append("%s at %s/%s differs from its source" % (f["id"], f["repo"], f["path"]))
            else:
                *got, where = upstream_measure(f, hub)
                got = tuple(got)
                if f.get("host", "huggingface") == "huggingface" and hub.head(f["repo"]) != f["revision"]:
                    report.note("%s: %s HEAD is %s, pinned %s"
                                % (f["id"], f["repo"], hub.head(f["repo"])[:12], f["revision"][:12]))
            if got != (f["bytes"], f["sha256"]):
                problems.append("%s: source has %d B %s, the manifest %d B %s"
                                % (f["id"], got[0], got[1][:12], f["bytes"], f["sha256"][:12]))
        except Exception as e:  # a failed fetch is a failed check, named
            problems.append("%s: %s" % (f["id"], e))
            where = "?"
        report.check("online " + f["id"], problems, "%d B at %s" % (f["bytes"], where))
    check_online_crow(doc, report, hub)


def check_online_crow(doc, report: Report, hub):
    for f in doc.get("crow_files") or []:
        problems = []
        where = "%s@%s" % (f["repo"], f["revision"][:12])
        try:
            got = hub.measure(f["repo"], f["revision"], f["path"], limit=CROW_SMALL)
            if got != (f["bytes"], f["sha256"]):
                problems.append("%s: source has %d B %s, the manifest %d B %s"
                                % (f["id"], got[0], got[1][:12], f["bytes"], f["sha256"][:12]))
            if hub.head(f["repo"]) != f["revision"]:
                report.note("%s: %s HEAD is %s, pinned %s"
                            % (f["id"], f["repo"], hub.head(f["repo"])[:12], f["revision"][:12]))
        except Exception as e:  # a failed fetch is a failed check, named
            problems.append("%s: %s" % (f["id"], e))
        report.check("online " + f["id"], problems, "%d B at %s" % (f["bytes"], where))


# The point ids written by hand outside stack.json (#340). (label, file, regex whose
# group 1 holds the list, rule[, id regex; default: every quoted id in the list]). rule "equal": exactly the points of stack.json;
# "each": every point is there (more keys are allowed: a defaulted table, extra model
# lines); "subset": only real points (a sample selection).
POINT_LISTS = (
    ("cli.rs POINTS", "installer/app/src/cli.rs", r"pub const POINTS: \[&str; \d+\] = \[([^\]]*)\]", "equal"),
    ("crow_core ACTIVE_POINTS", "cli/crow_core.py", r"\nACTIVE_POINTS = \(([^)]*)\)", "equal"),
    ("check_stack POINT_IDS", "tools/check_stack.py", r"\nPOINT_IDS = \(([^)]*)\)", "equal"),
    ("setup page DESC", "installer/ui/index.html", r"var DESC = \{([^}]*)\}", "equal"),
    ("setup page selection", "installer/ui/index.html", r"\bsel: \{([^}]*)\}", "equal"),
    ("crow_boot ICONS", "cli/crow_boot.py", r"\nICONS = \{(.*?)\n\}", "each"),
    ("crow_boot_gui USUAL_START_S", "cli/crow_boot_gui.py", r"\nUSUAL_START_S = \{([^}]*)\}", "each"),
    ("run.rs fake plan", "installer/core/src/run.rs", r"(?s)(let has = \|p: &str\|.*?)let derived = ", "each",
     r'has\("([^"]+)"\)'),
    ("mock.js selection", "installer/ui/mock.js", r"var points = \[([^\]]*)\]", "subset"),
)
QUOTED_ID = re.compile(r"""["']([a-z0-9][a-z0-9.-]*)["']""")


def check_point_lists(doc, root=REPO) -> "tuple[list[str], int]":
    """Every hand-written point list against the ids of stack.json; (problems, lists read)."""
    points = [pt["id"] for pt in doc["points"]]
    p, cache = [], {}
    for label, rel, pattern, rule, *id_re in POINT_LISTS:
        if rel not in cache:
            try:
                with open(os.path.join(root, rel), encoding="utf-8") as f:
                    cache[rel] = f.read()
            except OSError as e:
                p.append("%s: cannot read %s (%s)" % (label, rel, e.strerror))
                continue
        m = re.search(pattern, cache[rel], re.S)
        if not m:
            p.append("%s: list not found in %s (pattern moved?)" % (label, rel))
            continue
        found = (re.compile(id_re[0]) if id_re else QUOTED_ID).findall(m.group(1))
        missing = [x for x in points if x not in found]
        unknown = [x for x in found if x not in points]
        if rule == "equal" and (missing or unknown or len(found) != len(points)):
            p.append("%s (%s) names %s, stack.json has %s" % (label, rel, found, points))
        elif rule == "each" and missing:
            p.append("%s (%s) lacks %s" % (label, rel, missing))
        elif rule == "subset" and unknown:
            p.append("%s (%s) names unknown points %s" % (label, rel, unknown))
    return p, len(POINT_LISTS)


def run(doc, online=False) -> Report:
    r = Report()
    schema = check_schema(doc)
    r.check("schema", schema, "%d files, %d derived, %d points"
            % (len(doc.get("files") or []), len(doc.get("derived") or []), len(doc.get("points") or [])))
    if schema:
        return r  # the other checks index fields the schema did not find
    r.check("placeholders and paths", check_paths(doc), "only ${INSTALL}/${MODELS}, nothing personal")
    refs = check_references(doc)
    r.check("references", refs, "every file and derived entry used, every id resolves")
    if refs:
        return r
    r.check("byte sums", check_sums(doc), "; ".join(
        "%s %d files %s B" % (pt["id"], len(pt["files"]), format(pt["bytes"]["disk"], ","))
        for pt in doc["points"]))
    r.check("engine wiring", check_wiring(doc), "env/argv paths are files of their own point")
    r.check("platforms", check_platforms(doc), "windows and linux binaries for every server, lib_path")
    crow = [f for f in doc.get("crow_files") or [] if isinstance(f, dict)]
    crow_problems = check_crow_files(doc)
    r.check("crow files", crow_problems, "%d files %s B, dictation in %s"
            % (len(crow), format(sum(f.get("bytes") or 0 for f in crow), ","), WHISPER_DIR))
    wheels = [w for w in doc.get("nvidia_files") or [] if isinstance(w, dict)]
    r.check("nvidia files", check_nvidia_files(doc), "%d wheels from PyPI, %d members"
            % (len(wheels), sum(len(w.get("extract") or []) for w in wheels)))
    pkg = [e for e in doc.get("package_licenses") or [] if isinstance(e, dict)]
    r.check("package licences", check_package_licenses(doc), "; ".join(
        "%s on %s" % (e.get("license"), "/".join(e.get("platforms") or [])) for e in pkg) or "none")
    lists, n_lists = check_point_lists(doc)
    r.check("point lists", lists, "%d lists, %d points" % (n_lists, len(doc["points"])))
    if crow_problems:
        return r  # the online half indexes the fields this check did not find
    if online:
        check_online(doc, r)
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--online", action="store_true")
    a = ap.parse_args(argv)
    try:
        with open(a.manifest, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        print("check_stack: cannot read %s: %s" % (a.manifest, e), file=sys.stderr)
        return 2
    r = run(doc, a.online)
    print("\n".join(r.lines))
    print()
    name = os.path.relpath(a.manifest, REPO).replace("\\", "/") if a.manifest == MANIFEST else a.manifest
    if r.failed:
        print("RESULT: %d of %d checks fail against %s" % (r.failed, r.total, name))
        return 1
    print("RESULT: %d of %d checks hold against %s" % (r.total, r.total, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
