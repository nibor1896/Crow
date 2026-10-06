"""Negative control for check_operating_point.py.

A drift checker that cannot go red is a decoration. Every case here breaks one
thing and requires the checker to name it, plus the two cases that must NOT fire.

Case 4 is the one this file exists for. On its first run the checker reported the
session directory as "refuses", because a bare \\S+ after --slot-save-path matched
the PROSE at install.ps1:1126 explaining what the flag does. A checker that reads
the comment about a flag instead of the flag is exactly the failure the stage was
written to prevent, so it gets a permanent case.

Case 12 is the one the SAMPLING rule exists for, and it is the case a comparing
checker gets wrong: two clients that BOTH hard-write the manifest's top_p. Every
copy agrees with the manifest, so "compare each copy" reports green - and the
damage (one of them edited, the same prompt drawing from a different
distribution) is then one edit away with nothing watching. It has to be red for
the count, not for the value.

Usage:  test_check_operating_point.py
Exit 0 = all cases behaved as required.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "check_operating_point.py")

# The fixture below builds its README and install.ps1 out of this line and holds them against the
# REAL manifest, so every literal here has to track manifests/operating-point.json. When the
# operating point moves, this line moves with it -- --moe-stream-cache went 64s -> 62s -> 58s on
# 2026-08-11 (#87) and tests 1, 4, 6 and 8 went red both times until it did.
GOOD_LINE = (
    "llama-server.exe -m %LOCALAPPDATA%\\Crow\\models\\UD-IQ3_XXS\\x.gguf "
    "--port 8081 -c 200000 -ngl 99 -np 1 --jinja "
    "--slot-save-path %LOCALAPPDATA%\\Crow\\session "
    "--chat-template-file %LOCALAPPDATA%\\Crow\\templates\\0731-chat-template.jinja "
    "--moe-stream --moe-stream-cache 58s --moe-stream-io-threads 8 --moe-stream-direct "
    "--moe-stream-l2 32\n"
)

# The second line, and it is APPENDED BY THE FIXTURE rather than named by each
# case. #111 made the manifest a map of one command line per model key, so a
# repo "that agrees" is one carrying BOTH -- and the moment it did, cases 1, 4,
# 6, 8 and 14 went red, exactly as the note above predicts for a moved operating
# point. Appending it centrally keeps every case saying what it was written to
# say: a case that breaks the 0731 line still goes red for the 0731 key, and
# only a case that breaks THIS line goes red for the Qwen one.
#
# Flags, and no others: this model declares no expert stream and no template
# file, which is what stops the 0731 region from satisfying this key and this
# region from satisfying 0731's.
#
# THE POSITIVE CONTROLS NOW LOOK FOR "6 of 6" AND NOT "4 of 4", and that is not
# bookkeeping. The checker's unit became one (file, model key) pair, so the
# number in the RESULT line is how many pairs it actually looked at -- and a
# checker that silently skipped a key would still exit 0 while printing a
# smaller number. Asserting the count is what makes cases 1 and 14 notice.
# It moves again when a third model key lands, and somebody should have to look.
QWEN_LINE = (
    "llama-server.exe -m %LOCALAPPDATA%\\Crow\\models\\qwen38-gguf\\x.gguf "
    "--port 8082 -c 200000 -ctk q8_0 -ctv q8_0 -ngl 99 -np 1 --jinja "
    "--slot-save-path %LOCALAPPDATA%\\Crow\\session "
    # 02f8d1d put the vision switch into the manifest as one field, and this mirror
    # never grew it -- so this key had been failing on 'mmproj: missing' ever since.
    "--mmproj qwen38-gguf/mmproj-F16.gguf "
    # #117. THIS LINE IS A MIRROR, and it went red the moment the real one grew a flag: the
    # fixture is synthetic but the MANIFEST it is checked against is the real file on disk, so
    # every flag the manifest starts demanding has to appear here too. That is the point of the
    # positive controls -- they fail when the mirror stops matching, which is what happened.
    "--spec-type draft-mtp\n"
)


# THE THIRD LINE, and the comment above said it would be needed: 'It moves again when
# a third model key lands, and somebody should have to look.' The key landed with #140
# (d7f3bf8) and nobody looked, because this suite was ALREADY red: e1bda23 broke case 10
# on 2026-08-21, and 02f8d1d broke the counting cases after it. A red suite hides the
# NEXT regression, which is the whole reason this file exists.
#
# Flags, and no others: this model declares NO -ngl, NO slot-save-path and NO template
# file, and it is the only one carrying -b/-ub/-ncmoe/--fit/--load-mode. That asymmetry
# is what stops any of the three regions from satisfying another one's key.
# The real documents never put two command lines next to each other: install.ps1 has
# Write-Host "" between them, README.md and docs/operating-points.md have blank lines and
# prose. command_regions reaches TWO LINES BACK from its anchor (2026-08-28, for the
# env prelude), so an adjacent previous command lands inside the next one's region and
# extract() takes ITS --port. Two blank lines is what the real files have and what the
# lookback needs; with one, the reach still lands on the previous command.
BLANK = "\n\n"

FLASH_LINE = (
    "llama-server.exe -m %LOCALAPPDATA%\\Crow\\models\\qwen-next-gguf\\x.gguf "
    "--port 8083 -c 200000 -b 2048 -ub 2048 -ctk q8_0 -ctv q8_0 "
    "-ncmoe 30 --fit off --load-mode none -np 1 --jinja --mmproj %LOCALAPPDATA%\\Crow\\models\\qwen-next-gguf\\mmproj-F16.gguf\n"
)

# THE LINUX COPY OF THE FLASH LINE, 2026-09-16. The manifest line carries a
# `linux` object (ncmoe 31, threads 24; `_why_linux` beside it), and the checker
# holds ONE document to the merged line under `docs [<key> on linux]`. So the
# fixture README carries this copy too, and every flag the object starts
# demanding has to appear here -- the same mirror rule as FLASH_LINE.
FLASH_LINUX_LINE = (
    "$HOME/.local/share/crow/bin/llama-server -m $CROW_MODELS/x.gguf "
    "--port 8083 -c 200000 -b 2048 -ub 2048 -ctk q8_0 -ctv q8_0 "
    "-ncmoe 31 -t 24 --fit off --load-mode mmap --image-min-tokens 1024 --no-mmproj-offload -np 1 --jinja --mmproj $CROW_MODELS/mmproj-F16.gguf\n"
)


def run(repo, extra=None):
    cmd = [sys.executable, TOOL, "--repo", repo]
    for e in extra or []:
        cmd += ["--extra", e]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def manifest_sampling():
    """The real manifest's sampling block, read rather than spelled."""
    src = json.load(open(os.path.join(REPO, "manifests", "operating-point.json"),
                         encoding="utf-8-sig"))
    return src["sampling"]


def client_source(sampling, keys=None, body_keys=None, prose=False):
    """A client that writes the sampling defaults the way the core does.

    EVERY NUMBER COMES OUT OF THE MANIFEST the fixture just wrote, and that is
    not tidiness. Case 9 went quietly vacuous once because it carried a typed
    "0.0.6" that stopped matching the day the version moved: the replace missed,
    both copies stayed equal, and the case that exists to catch a stale literal
    was itself the stale literal. A fixture that types 0.95 stops testing this
    rule the day the operating point picks a different value, and says nothing.

    `keys` are the defaults the client writes, `body_keys` the fields it puts on
    the wire - the two are separate because the GUI draft's failure was exactly
    that split: min_p had a default and the request body left it out.
    """
    values = [(k, v) for k, v in sampling.items() if not k.startswith("_")]
    names = [k for k, _ in values]
    keys = names if keys is None else keys
    body_keys = names if body_keys is None else body_keys
    seen = dict(values)
    out = []
    if prose:
        # Both shapes of prose in one client: the comment and the docstring. A
        # rule that counts either of them counts a sentence as a second copy.
        out.append('"""The card runs its agentic benchmarks at top_p = %s.\n\n'
                   'llama.cpp defaults min_p = %s elsewhere.\n"""\n'
                   % (seen["top_p"], seen["min_p"]))
        out.append("# the disagreement is real: top_p = %s in the card, 1.0 in the config\n"
                   % seen["top_p"])
    for key in keys:
        out.append('parser.add_argument("--%s", dest="%s", type=float, default=%r)\n'
                   % (key.replace("_", "-"), key, seen[key]))
    out.append("body = {\n")
    out.append('    "messages": messages,\n')
    for key in body_keys:
        out.append('    "%s": %s,\n' % (key, key))
    out.append('    "stream": True,\n')
    out.append("}\n")
    return "".join(out)


def fixture(tmp, readme=None, install=None, manifest_patch=None, client=None,
            gui=None, sep=None, linux_line=None, install_flash=None):
    """A minimal repo the checker can be pointed at."""
    gap = BLANK if sep is None else sep
    root = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(root, "manifests"), exist_ok=True)
    os.makedirs(os.path.join(root, "cli"), exist_ok=True)
    src = json.load(open(os.path.join(REPO, "manifests", "operating-point.json"), encoding="utf-8-sig"))
    if manifest_patch:
        manifest_patch(src)
    with open(os.path.join(root, "manifests", "operating-point.json"), "w", encoding="utf-8") as fh:
        json.dump(src, fh, indent=1)
    # THE THINKING ROWS, 2026-10-06. check_thinking (297a05b, #225) holds every entry
    # that declares `reasoning_fixed` to a row '| `<key>` | `<word>` |' in
    # docs/operating-points.md, and this fixture wrote no such page -- so every
    # positive control read one source short from the day that check landed. The rows
    # are READ from the manifest (after manifest_patch), the same mirror rule as the
    # command lines above. The page carries no command line, so the docs cases are
    # still decided on the README.
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    entries = (src.get("models") or {}).get("entries") or {}
    with open(os.path.join(root, "docs", "operating-points.md"), "w", encoding="utf-8") as fh:
        for key, entry in sorted(entries.items()):
            if (entry or {}).get("reasoning_fixed") is not None:
                fh.write("| `%s` | `%s` |\n" % (key, entry["reasoning_fixed"]))
    ver = src["version"]
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("version-%s-brightgreen\n\n```\n%s%s```\n"
                 % (ver, readme if readme is not None else GOOD_LINE,
                    gap + QWEN_LINE + gap + FLASH_LINE + gap
                    + (linux_line if linux_line is not None else FLASH_LINUX_LINE)))
    with open(os.path.join(root, "install.ps1"), "w", encoding="utf-8") as fh:
        fh.write('param([string] $Version = "%s")\n%s%s'
                 % (ver, install if install is not None else GOOD_LINE,
                    gap + QWEN_LINE + gap
                    + (install_flash if install_flash is not None else FLASH_LINE)))
    with open(os.path.join(root, "cli", "crow_core.py"), "w", encoding="utf-8") as fh:
        fh.write('VERSION = "%s"\n' % ver)
        fh.write(client_source(src["sampling"]) if client is None else client)
    if gui is not None:
        os.makedirs(os.path.join(root, "gui"), exist_ok=True)
        with open(os.path.join(root, "gui", "crow_gui.py"), "w", encoding="utf-8") as fh:
            fh.write(gui)
    return root


def main():
    fail = 0

    def check(label, cond, detail=""):
        nonlocal fail
        if cond:
            print("  OK       %s" % label)
        else:
            fail = 1
            print("  FAILED   %s%s" % (label, (": " + detail) if detail else ""))

    with tempfile.TemporaryDirectory() as tmp:
        # 1 - positive control on a fixture, so a red real repo cannot mask a
        #     checker that says no to everything.
        code, out = run(fixture(tmp, ))
        check("1 a repo that agrees passes", code == 0 and "10 of 10" in out, out.strip()[-200:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 2 - a changed value must be named, not just counted.
        bad = GOOD_LINE.replace("--moe-stream-cache 58s", "--moe-stream-cache 48s")
        code, out = run(fixture(tmp, readme=bad))
        check("2 a changed cache size goes red and is named",
              code == 1 and "moe_stream_cache" in out and "48s" in out, out.strip()[-200:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 3 - a dropped flag. This is the actual vault drift: the page carried
        #     neither --slot-save-path nor --moe-stream-l2.
        bad = GOOD_LINE.replace("--slot-save-path %LOCALAPPDATA%\\Crow\\session ", "")
        code, out = run(fixture(tmp, readme=bad))
        check("3 a dropped flag goes red as missing",
              code == 1 and "slot_save_path: missing" in out, out.strip()[-200:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 4 - THE case. Prose ABOUT the flag must not be read as the flag.
        prose = ("# --slot-save-path refuses to start against a path that is not\n"
                 "# an existing directory, so the server would fail.\n") + GOOD_LINE
        code, out = run(fixture(tmp, install=prose))
        check("4 a comment explaining a flag is not the flag",
              code == 0 and "refuses" not in out, out.strip()[-260:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 5 - and the half that must still fire: prose alone, with no real line,
        #     is a copy that lost the flag.
        only_prose = ("# --slot-save-path refuses to start against a path that is\n"
                      "# not an existing directory.\n") + GOOD_LINE.replace(
                          "--slot-save-path %LOCALAPPDATA%\\Crow\\session ", "")
        code, out = run(fixture(tmp, install=only_prose))
        check("5 prose alone does not satisfy the flag",
              code == 1 and "slot_save_path: missing" in out, out.strip()[-200:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 6 - --moe-stream-l2 carries a machine-dependent value. A different
        #     number is fine, a missing flag is not.
        code, out = run(fixture(tmp, install=GOOD_LINE.replace("--moe-stream-l2 32", "--moe-stream-l2 48")))
        check("6 a different L2 value is accepted", code == 0, out.strip()[-200:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        code, out = run(fixture(tmp, install=GOOD_LINE.replace(" --moe-stream-l2 32", "")))
        check("7 a missing L2 flag is not", code == 1 and "moe_stream_l2: missing" in out, out.strip()[-200:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 8 - the version literal, drifting in one place only.
        def bump(m):
            m["version"] = "9.9.9"
        code, out = run(fixture(tmp, manifest_patch=bump))
        check("8 a version that agrees everywhere passes", code == 0, out.strip()[-200:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        root = fixture(tmp)
        inst = open(os.path.join(root, "install.ps1"), encoding="utf-8").read()
        # The manifest's version, read rather than spelled: this line carried a
        # hard-coded "0.0.6" and went quietly vacuous the day the version moved
        # to 0.1.0 -- the replace missed, both copies stayed equal, and the case
        # that exists to catch a stale literal was itself the stale literal.
        current = json.load(open(os.path.join(root, "manifests", "operating-point.json"),
                                 encoding="utf-8-sig"))["version"]
        open(os.path.join(root, "install.ps1"), "w", encoding="utf-8").write(
            inst.replace('$Version = "%s"' % current, '$Version = "0.0.5"'))
        code, out = run(root)
        check("9 one stale version literal goes red",
              code == 1 and "0.0.5" in out and "differs" in out, out.strip()[-260:])
        shutil.rmtree(root)

        # 10 - a file that is not there must be an error. A checker that skips a
        #      missing file passes by having nothing to read.
        code, out = run(fixture(tmp), extra=[os.path.join(tmp, "nope.md")])
        check("10 a missing --extra file is an error, not a skip",
              code == 1 and "does not exist" in out, out.strip()[-200:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # ------------------------------------------------------------------
        # The sampling triple. Cases 11-16 hold the rule that COUNTS.
        # ------------------------------------------------------------------

        # 11 - the manifest moves and the client does not. The break is DERIVED
        #      from the manifest, never typed: a hard-coded 0.9 here stops
        #      breaking anything the day the operating point picks 0.9, and the
        #      case would go on reporting OK for a checker that no longer looks.
        root = fixture(tmp)
        mpath = os.path.join(root, "manifests", "operating-point.json")
        man = json.load(open(mpath, encoding="utf-8-sig"))
        current = man["sampling"]["top_p"]
        moved = round(current / 2, 6) if current else 0.5
        man["sampling"]["top_p"] = moved
        with open(mpath, "w", encoding="utf-8") as fh:
            json.dump(man, fh, indent=1)
        code, out = run(root)
        check("11 a moved top_p in the manifest goes red and names the value",
              moved != current and code == 1 and "top_p" in out and repr(moved) in out,
              out.strip()[-260:])
        shutil.rmtree(root)

        # 12 - THE case, and the one a comparing checker gets wrong. A second
        #      client writes the manifest's OWN value. Every copy agrees; the
        #      count does not. If this passes, the rule is a compare() and the
        #      next edit to either client goes unnoticed.
        code, out = run(fixture(tmp, gui=client_source(manifest_sampling())))
        check("12 a second client that also agrees with the manifest is still red",
              code == 1 and "written 2 times" in out and "gui/crow_gui.py" in out,
              out.strip()[-300:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 13 - the GUI draft's actual defect: the default exists, the request
        #      body leaves the field out. An omitted min_p is not the manifest's
        #      0.01, it is llama.cpp's 0.05 - a third value nobody chose.
        samp = manifest_sampling()
        keys = [k for k in samp if not k.startswith("_")]
        code, out = run(fixture(tmp, client=client_source(samp, body_keys=[k for k in keys if k != "min_p"])))
        check("13 a request body that omits min_p goes red and names it",
              code == 1 and "without min_p" in out, out.strip()[-300:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 14 - and the half that must NOT fire, in both shapes prose takes: a
        #      comment and a docstring that quote the value. Case 4's lesson,
        #      applied to the rule that counts - a sentence is not a copy.
        code, out = run(fixture(tmp, client=client_source(samp, prose=True)))
        check("14 prose quoting the value is not a second copy",
              code == 0 and "10 of 10" in out, out.strip()[-300:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 15 - written exactly once, but in the wrong file. "Exactly one" alone
        #      would be green here, and the surface would own the default the
        #      core is supposed to hold.
        code, out = run(fixture(tmp, client="", gui=client_source(samp)))
        check("15 the one copy has to sit in the core",
              code == 1 and "not in the core" in out and "cli/crow_core.py" in out,
              out.strip()[-300:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 16 - nobody writes it at all. That is not "nothing to check", it is
        #      every client inheriting the server's own defaults, which is the
        #      state top_p was in until #83.
        code, out = run(fixture(tmp, client=""))
        check("16 a value written nowhere is an error, not a skip",
              code == 1 and "written nowhere" in out, out.strip()[-300:])

        # 17 - COMMAND LINES THAT SIT CLOSE TOGETHER STILL BELONG TO THEMSELVES.
        #      command_regions clamps FORWARD -- a region stops at the next anchor,
        #      'so a long region can never merge two command lines into one that
        #      satisfies the manifest with halves of both'. It did NOT clamp
        #      BACKWARD: since 2026-08-28 the region reaches two lines above its
        #      anchor for the env prelude, and with one blank line between commands
        #      that reach lands on the PREVIOUS one. extract() then takes the first
        #      --port it sees, so key two reads key one's port and the document is
        #      reported as drifted while it is correct.
        #
        #      One blank line, not zero: a document with none is not a shape any of
        #      the real files take, but one is -- and one was enough to break it.
        code, out = run(fixture(tmp, sep="\n"))
        check("17 commands one blank line apart do not borrow each other's flags",
              code == 0 and "10 of 10" in out, out.strip()[-300:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 18 - the Linux copy is held to the MERGED line. Before 2026-09-16 a
        #      README whose bash line still said -ncmoe 30 was green, because
        #      compare() accepts either shape and the PowerShell line satisfied
        #      the key. Now the key has a second docs entry that only the merged
        #      line (ncmoe 31, -t 24) satisfies, so the Windows placement in the
        #      Linux copy is red and the message names the flag.
        wrong = FLASH_LINUX_LINE.replace("-ncmoe 31 -t 24", "-ncmoe 30")
        code, out = run(fixture(tmp, linux_line=wrong))
        check("18 a Linux copy at the Windows placement is red",
              code != 0 and "on linux]" in out and "9 of 10" in out, out.strip()[-300:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 19 - ONE FLAG AT A TIME, because case 18 drops two (-ncmoe 31 AND
        #      -t 24) and a case that changes two things proves neither. `-t` is
        #      the flag the `linux` object added, and its spec is the newest
        #      regex in FLAG_SPECS -- a lookbehind that let `-ctk`, `-ctv` or
        #      `--moe-stream-io-threads` match would make it green everywhere
        #      and this case is what notices.
        wrong = FLASH_LINUX_LINE.replace(" -t 24", "")
        code, out = run(fixture(tmp, linux_line=wrong))
        check("19 a Linux copy without -t is red and names threads",
              code != 0 and "on linux]" in out and "threads: missing" in out,
              out.strip()[-300:])
        shutil.rmtree(os.path.join(tmp, "repo"))

        # 20 - THE INSTALLER HAS ONE SHAPE AND IT IS THE WINDOWS ONE. install.ps1
        #      starts both servers on that machine, so a flag wrong there is a
        #      broken run. Until 2026-09-16 the installer was compared against
        #      the Linux shape as an alternative too, so this very file -- the
        #      Linux line pasted into install.ps1 -- read green.
        code, out = run(fixture(tmp, install_flash=FLASH_LINUX_LINE))
        check("20 install.ps1 at the Linux placement is red",
              code != 0 and "install.ps1 [flash-next-q2-k-xl]" in out
              and "ncmoe" in out, out.strip()[-400:])
        shutil.rmtree(os.path.join(tmp, "repo"))

    print()
    print("RESULT: PASS - the drift checker can go red, and does not go red at prose"
          if not fail else
          "RESULT: FAIL - see the FAILED lines above")
    return fail


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
