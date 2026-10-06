<#
.SYNOPSIS
Packs the Crow release: the built binaries plus every runtime library they need,
and proves the result is complete before writing the archive.

.DESCRIPTION
The build tree is not shippable on its own. Measured 2026-08-08 (#57): ggml-cuda.dll
imports cublas64_13.dll, which imports cublasLt64_13.dll, and neither is in
bin/Release -- they sit in the installed CUDA toolkit, which an end user does not
have. The MSVC runtime is missing for the same reason.

THE PACKAGE CARRIES NO NVIDIA FILE. Those two libraries used to be copied into bin\.
They are NVIDIA's, so CrowSetup now downloads them at install time from NVIDIA's own
PyPI wheel (nvidia-cublas 13.6.0.2) and puts the same files at <install>\bin\ (see
NOTICE). The completeness check below therefore accepts exactly the names in
$NVIDIA_AT_INSTALL as "provided at install time from NVIDIA", and nothing else of
NVIDIA's: no wildcard, and any other missing DLL still refuses. Step 1 leaves those
names out of the build copy, and the gate refuses a stage that holds one.

So the interesting part of this tool is not the copying. It is the completeness
check: every import of every DLL in the package must resolve to a file that is
also in the package, or to a Windows system library. Anything else is a file the
user will be missing, and the tool refuses to write an archive rather than ship one
that fails on somebody else's machine.

.PARAMETER SdBuildDir
Optional. The bin directory of a Windows stable-diffusion.cpp build (pin 2f88688,
CUDA 13, -DSD_CUDA=ON; recipe in docs/user-guide/install.md). sd-server.exe and
sd-cli.exe from it go into bin\ beside llama-server.exe, the image server of
generate_image/edit_image (#314). Their DLLs are resolved exactly like
llama-server's, so both builds' cublas imports stay on the install-time list. Without
it the package has no image server and says so when it is packed.

.PARAMETER BuildDir
The bin directory of the llama.cpp Windows build to pack. Required to pack; it
has no default, because a default is somebody's machine (it used to be the
author's lab tree). The environment variable CROW_BUILD_DIR stands in for it.

.PARAMETER PrivatePattern
Optional, repeatable. Further text that must not appear in any packed file, on
top of what the gate derives from this machine (see the privacy gate below).

.PARAMETER Selftest
Run the checks against synthetic cases, including ones that must fail, and exit.

.NOTES
WHAT MAY SHIP (#196 C2). One declared set, the same in tools/repack-release.py:
$SHIP_* say where a file may live, $EXCLUDE_* say what never ships (runs\, *.log,
__pycache__, *.pyc, test_*.py, .env*, secrets.json, session and state files).
The package is refused if it would hold anything else. 2.8.5 shipped ten
cli\runs\llama-server-*.log because this script filtered only __pycache__, *.pyc
and test_*.py while the other packer filtered runs\ -- tools/test_repack_release.py
now compares the two lists.

THE PRIVACY GATE. After staging and before MANIFEST.json or the zip exist, every
staged file is searched as raw bytes, in UTF-8 and in UTF-16LE, ignoring ASCII
case, for: $env:USERPROFILE (backslash, slash and JSON-escaped spellings), the
user name (as a path segment, \Users\<name>\ and /home/<name>/, and bare), $env:COMPUTERNAME,
and every -PrivatePattern. A hit prints file, pattern and count, removes the
stage and exits 1. ONE scoped allowlist exists ($PRIVACY_ALLOW): upstream words that merely
contain the owner's bare name (the "round-robin" of the llama server's web UI, tokenizer
vocabulary in the sd binaries) pass in the named file, in the named byte context, up to a
maximum count, and are listed as INFO; anything else refuses. Path patterns and the host
name are never allowlisted. THERE IS NO OVERRIDE SWITCH, on purpose: a switch that ships
private data on request is a switch somebody passes at 23:00 on release night.
Fix the source, or rebuild with path remapping, and pack again.
#>
[CmdletBinding()]
param(
    [string]   $BuildDir  = $env:CROW_BUILD_DIR,
    [string]   $CudaBin   = "",
    [string]   $OutDir    = "",
    [string]   $Version   = "",
    [string]   $SdBuildDir = "",
    [string[]] $PrivatePattern = @(),
    [switch]   $Selftest
)

$ErrorActionPreference = "Stop"

# Libraries that ship with Windows itself. A dependency resolving to one of these
# is fine; anything else has to be in the package. The api-ms-win-* set is the
# Universal CRT, present on Windows 10 and 11.
$SYSTEM_DLLS = @(
    'kernel32.dll', 'user32.dll', 'advapi32.dll', 'shell32.dll', 'ole32.dll',
    'oleaut32.dll', 'gdi32.dll', 'ws2_32.dll', 'crypt32.dll', 'bcrypt.dll',
    'dbghelp.dll', 'psapi.dll', 'setupapi.dll', 'cfgmgr32.dll', 'winmm.dll',
    'shlwapi.dll', 'version.dll', 'userenv.dll', 'ntdll.dll', 'rpcrt4.dll',
    'nvcuda.dll'      # installed by the NVIDIA display driver, not redistributable
)

# NVIDIA libraries the package does NOT carry: CrowSetup downloads them at install time
# from NVIDIA's own PyPI wheel (nvidia-cublas 13.6.0.2) and puts them in <install>\bin\.
# An explicit list of names, never a pattern. Keep identical to NVIDIA_AT_INSTALL in
# tools/repack-release.py; tools/test_repack_release.py compares them.
$NVIDIA_AT_INSTALL = @('cublas64_13.dll', 'cublasLt64_13.dll')

function Test-NvidiaAtInstall {
    # True for exactly the names above, case-insensitive. Not a system DLL (Test-SystemDll
    # stays false for them): an import of one is only accepted when the caller says the
    # install provides it.
    param([string] $Name)
    return $NVIDIA_AT_INSTALL -contains ([IO.Path]::GetFileName($Name))
}

function Get-NvidiaFiles {
    # The paths in $Paths that are one of the named NVIDIA libraries. A package must hold none.
    param([string[]] $Paths)
    return ,@($Paths | Where-Object { $_ -and (Test-NvidiaAtInstall $_) })
}

function Test-SystemDll {
    param([string] $Name)
    $n = $Name.ToLowerInvariant()
    if ($n -like 'api-ms-win-*') { return $true }
    if ($n -like 'ext-ms-win-*') { return $true }
    return $SYSTEM_DLLS -contains $n
}

function Find-Dumpbin {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { throw "vswhere.exe not found -- no Visual Studio installation" }
    $hit = & $vswhere -latest -products * -find "**\dumpbin.exe" 2>$null | Select-Object -First 1
    if (-not $hit) { throw "dumpbin.exe not found through vswhere" }
    return $hit
}

function Get-Imports {
    param([string] $Dumpbin, [string] $Path)
    $out = & $Dumpbin /dependents $Path 2>&1
    if ($LASTEXITCODE -ne 0) { throw "dumpbin failed on ${Path}: exit $LASTEXITCODE" }
    # dumpbin indents each imported name by four spaces. Section headers are not
    # indented that way, which is what keeps this from swallowing the summary.
    $names = @()
    foreach ($line in $out) {
        if ($line -match '^\s{4}(\S+\.dll)\s*$') { $names += $Matches[1] }
    }
    return $names
}

<#
    Locates a runtime library on this machine by name. Searches the CUDA toolkit
    and the MSVC redistributable directories -- deliberately NOT the PATH, because
    the PATH is exactly what an end user does not have and searching it would let
    the developer machine answer a question about somebody else's.
#>
function Find-RuntimeLibrary {
    param([string] $Name)

    $roots = @()
    if ($CudaBin) { $roots += $CudaBin }
    $roots += (Get-ChildItem "$env:ProgramFiles\NVIDIA GPU Computing Toolkit\CUDA" -Directory -ErrorAction SilentlyContinue |
               Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'bin\x64' })

    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $vsRoot = & $vswhere -latest -products * -property installationPath 2>$null
        if ($vsRoot) {
            $roots += (Get-ChildItem (Join-Path $vsRoot 'VC\Redist\MSVC') -Directory -ErrorAction SilentlyContinue |
                       Sort-Object Name -Descending |
                       ForEach-Object { Get-ChildItem $_.FullName -Directory -Filter 'x64.*' -ErrorAction SilentlyContinue } |
                       ForEach-Object { $_.FullName })
        }
    }

    foreach ($r in $roots) {
        if (-not $r -or -not (Test-Path $r)) { continue }
        $hit = Get-ChildItem $r -Recurse -File -Filter $Name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

<#
    The completeness check. Returns the list of unresolved imports; empty means
    the package stands on its own.

    -NvidiaAtInstall (the packing path sets it): an import of one of the named
    $NVIDIA_AT_INSTALL libraries is not missing, because CrowSetup downloads that
    file from NVIDIA at install time. Only those names; every other import that is
    neither in the package nor a system library is still reported.
#>
function Test-PackageComplete {
    param([string] $Dumpbin, [string[]] $Files, [switch] $NvidiaAtInstall)

    $present = @{}
    foreach ($f in $Files) { $present[[IO.Path]::GetFileName($f).ToLowerInvariant()] = $true }

    $missing = @()
    foreach ($f in $Files) {
        if ($f -notmatch '\.(dll|exe)$') { continue }
        foreach ($imp in (Get-Imports -Dumpbin $Dumpbin -Path $f)) {
            $k = $imp.ToLowerInvariant()
            if ($present.ContainsKey($k)) { continue }
            if (Test-SystemDll $imp)      { continue }
            if ($NvidiaAtInstall -and (Test-NvidiaAtInstall $imp)) { continue }
            $missing += [pscustomobject]@{ Needs = $imp; RequiredBy = [IO.Path]::GetFileName($f) }
        }
    }
    return $missing
}

<#
    THE IMAGE SERVER'S TWO EXECUTABLES, AND ONLY THOSE (#314).

    SD_BUILD_SHARED_LIBS is OFF by default, so ggml and stable-diffusion are
    linked INTO each exe and the only DLLs they need are CUDA's and the MSVC
    runtime, which the resolver below finds exactly as it does for llama-server.
    Taking the whole directory instead would bring a ggml*.dll of ANOTHER build
    under the same name as llama-server's own -- one of them would silently
    overwrite the other in bin\. So the two names are asked for, and a missing
    one is an error rather than a smaller package.
#>
$SD_BINARIES = @('sd-server.exe', 'sd-cli.exe')

function Get-SdBinaries {
    param([string] $Dir)
    if (-not (Test-Path -LiteralPath $Dir)) { throw "-SdBuildDir not found: $Dir" }
    $out = @()
    foreach ($n in $SD_BINARIES) {
        $p = Join-Path $Dir $n
        if (-not (Test-Path -LiteralPath $p)) { throw "$n missing from -SdBuildDir $Dir" }
        $out += $p
    }
    return ,@($out)
}

<#
    Which of the incoming files would REPLACE a different file of the same name
    already in $Dest. The same bytes under the same name is not a clash -- that is
    cublas64_13.dll from the one CUDA 13 toolkit both builds use, and it is kept
    once. Different bytes is: two builds disagree about a file only one can win.
#>
function Get-NameClashes {
    param([string] $Dest, [string[]] $Incoming)
    $clash = @()
    foreach ($f in $Incoming) {
        $d = Join-Path $Dest ([IO.Path]::GetFileName($f))
        if ((Test-Path -LiteralPath $d) -and
            ((Get-FileHash -LiteralPath $d -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash)) {
            $clash += [IO.Path]::GetFileName($f)
        }
    }
    return ,@($clash)
}

<#
    The version the package is stamped with, read out of a cli\ directory.

    cli\crow_core.py owns the literal since #187 (the terminal client cli\crow.py
    no longer ships). cli\crow.py is the fallback for a tree from before that,
    whose crow_core.py carries no literal. $null when neither has one. Same
    pattern as install.ps1's Get-InstalledVersion, so the stamp and the reader
    cannot disagree about where the number lives.
#>
function Get-VersionLiteral {
    param([string] $CliDir)
    foreach ($name in @('crow_core.py', 'crow.py')) {
        $f = Join-Path $CliDir $name
        if (-not (Test-Path -LiteralPath $f)) { continue }
        $m = Select-String -LiteralPath $f -Pattern '^VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($m) { return $m.Matches[0].Groups[1].Value }
    }
    return $null
}

function Resolve-BuildDir {
    <#
    The build directory, or a refusal. There is no default (#196 C2): the one this
    replaces was a path inside the author's home, and a script that quietly packs
    "the build that happens to be on that disk" is how a stale tree gets shipped.
    #>
    param([string] $Value)
    if (-not $Value) {
        throw "-BuildDir is required (the bin directory of the llama.cpp Windows build), or set CROW_BUILD_DIR"
    }
    return $Value
}

# ---------------------------------------------------------------------------
# What may ship (#196 C2). Keep identical to SHIP_* / EXCLUDE_* in
# tools/repack-release.py; tools/test_repack_release.py fails when they differ.
# The lists are plain literals because that test reads them as text.
# ---------------------------------------------------------------------------
$SHIP_ROOT_FILES   = @('LICENSE', 'NOTICE', 'README.md')
$SHIP_TOP_DIRS     = @('bin', 'cli', 'kits')
$SHIP_SINGLE_FILES = @('templates\0731-chat-template.jinja', 'manifests\operating-point.json', 'manifests\stack.json',
                       'tools\te_rename.py')
$EXCLUDE_DIRS      = @('runs', '__pycache__', '.crow', 'digests', 'sessions')
$EXCLUDE_FILES     = @('*.log', '*.pyc', '*.pyo', '*.jsonl', 'test_*.py', '.env*', 'secrets.json',
                       'session*.json', 'state*.json', 'settings.json', '*_tokens.json')
$KIT_REQUIRED      = @('crow-pathtracer.js', 'kit.json', 'voxel-kit.js', 'SKILL.md', 'check_diorama.py',
                       'scaffold\index.html', 'scaffold\scene.js',
                       'LICENSE.three', 'LICENSE.three-mesh-bvh', 'LICENSE.three-gpu-pathtracer')

function Get-ExcludeRule {
    # The rule that keeps this relative path out of a package, or $null.
    # -contains and -like are case-insensitive, as the file system is.
    param([string] $RelPath)
    $parts = $RelPath.Replace('/', '\').Split('\')
    for ($i = 0; $i -lt $parts.Count - 1; $i++) {
        if ($EXCLUDE_DIRS -contains $parts[$i]) { return "directory $($parts[$i])\" }
    }
    $name = $parts[$parts.Count - 1]
    foreach ($pat in $EXCLUDE_FILES) {
        if ($name -like $pat) { return "file pattern $pat" }
    }
    return $null
}

function Get-ShippedSetViolations {
    # Every relative path that is not in the declared shipped set, with the reason.
    param([string[]] $Paths)
    $bad = @()
    $singles = @($SHIP_SINGLE_FILES | ForEach-Object { $_.ToLowerInvariant() })
    foreach ($p in $Paths) {
        $rel   = $p.Replace('/', '\')
        $low   = $rel.ToLowerInvariant()
        if ($low -eq 'manifest.json') { continue }
        $parts = $low.Split('\')
        if ($parts.Count -eq 1) {
            if ($SHIP_ROOT_FILES -cnotcontains $rel) {
                $bad += [pscustomobject]@{ Path = $rel; Reason = 'top-level file outside the shipped set' }
                continue
            }
        } elseif (($singles -notcontains $low) -and ($SHIP_TOP_DIRS -notcontains $parts[0])) {
            $bad += [pscustomobject]@{ Path = $rel; Reason = "outside the shipped set (top level $($parts[0])\)" }
            continue
        }
        $why = Get-ExcludeRule -RelPath $rel
        if ($why) { $bad += [pscustomobject]@{ Path = $rel; Reason = "excluded: $why" } }
    }
    return ,@($bad)
}

function Copy-ManifestFiles {
    <#
    Stages the two manifests that ship: manifests\operating-point.json (sampling
    per model, read by the client) and manifests\stack.json (#196 P1: the boot
    menu cli\crow_boot.py starts every operating point from it and looks for it
    at ..\manifests\ beside cli\). Each is read back as JSON: a truncated copy
    would install cleanly and fail only when used. Returns the staged paths.
    #>
    param([string] $Repo, [string] $Stage)
    New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'manifests') | Out-Null
    $out = @()
    foreach ($name in @('operating-point.json', 'stack.json')) {
        $dest = Join-Path $Stage "manifests\$name"
        Copy-Item -LiteralPath (Join-Path $Repo "manifests\$name") -Destination $dest
        try { Get-Content -LiteralPath $dest -Raw | ConvertFrom-Json | Out-Null }
        catch { throw "manifests/$name did not survive staging as readable JSON: $_" }
        $out += $dest
    }
    return ,@($out)
}

function Copy-ToolFiles {
    <#
    Stages tools\te_rename.py (#196 phase 2): CrowSetup's convert step runs it
    from <install>\tools\ to build the Image Stack's text_encoder_sdcli\ on the
    machine. Required: without it the Image Stack cannot be installed. Copied
    byte for byte; returns the staged path.
    #>
    param([string] $Repo, [string] $Stage)
    $src = Join-Path $Repo 'tools\te_rename.py'
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) {
        throw "tools/te_rename.py missing -- CrowSetup's Image Stack convert step runs it from the package"
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'tools') | Out-Null
    $dest = Join-Path $Stage 'tools\te_rename.py'
    Copy-Item -LiteralPath $src -Destination $dest
    if ((Get-FileHash -LiteralPath $dest).Hash -ne (Get-FileHash -LiteralPath $src).Hash) {
        throw "tools/te_rename.py changed on the way into the package"
    }
    return $dest
}

function Copy-ShippedTree {
    <#
    Copies a source tree file by file and leaves out what Get-ExcludeRule names.
    This replaces `Copy-Item -Recurse` plus a clean-up pass: a recursive copy that
    removes the unwanted afterwards ships whatever the clean-up forgot, which is how
    cli\runs\*.log reached the 2.8.5 package.
    #>
    param([string] $Source, [string] $Dest)
    $src = (Resolve-Path -LiteralPath $Source).Path.TrimEnd('\')
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    $copied = 0
    $left   = @()
    foreach ($f in Get-ChildItem -LiteralPath $src -Recurse -File -Force) {
        $rel = $f.FullName.Substring($src.Length + 1)
        if (Get-ExcludeRule -RelPath $rel) { $left += $rel; continue }
        $target = Join-Path $Dest $rel
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $f.FullName -Destination $target
        $copied++
    }
    return [pscustomobject]@{ Copied = $copied; Left = @($left) }
}

# ---------------------------------------------------------------------------
# The privacy gate (#196 C2)
# ---------------------------------------------------------------------------

# The gate's scoped allowlist (#196 C6; keep identical to PRIVACY_ALLOW in repack-release.py).
# Only the BARE user name can be allowlisted, never a path pattern or the host name. Each entry
# is 'file glob @@ name @@ max @@ label @@ context regex': the glob is relative to the package
# (backslashes, case-insensitive), the name is the owner it is about, max is the most hits the
# file may carry, the regex describes the bytes that make a hit benign. It is matched against
# the ASCII-lowercased bytes (read as Latin-1) around the hit, anchored at or before the hit and
# running across it, and holds only syntax that .NET and Python read the same way. Measured
# 2026-10-01 on the binaries rebuilt from a neutral path (#196 C5): the word "round-robin" twice
# in the embedded web UI of llama-server-impl.dll, and tokenizer vocabulary (BPE merges lines,
# vocab JSON keys: Robinson, probing, robinet ...) 29 times in each sd binary. Only UTF-8 hits
# can be allowed. The closing paren of the list stays on a line of its own: the drift test
# in test_repack_release.py reads the list between "@(" and that line.
$PRIVACY_ALLOW = @(
    'bin\llama-server-impl.dll @@ robin @@ 2 @@ round-robin (embedded web UI) @@ round-robin',
    'bin\sd-*.exe @@ robin @@ 29 @@ tokenizer vocabulary (BPE merges, vocab JSON) @@ (?:\n(?:[a-z]|\xe2\x96\x81|\xc4\xa0){0,24} (?:[a-z]|\xe2\x96\x81|\xc4\xa0){0,24}(?:</w>)?\n|"(?:[a-z]|\xe2\x96\x81|\xc4\xa0){0,24}"(?:: ?[0-9]+,|,))'
)
$ALLOW_WINDOW = 64   # bytes of context read on each side of a hit

# A byte search compiled once. Streams the file in 4 MB blocks (the DLLs are
# hundreds of MB), folds ASCII A-Z so the match ignores case, and counts each
# needle without counting a match twice across a block boundary.
$CROW_BYTE_SCAN_SOURCE = @'
using System;
using System.IO;
public static class CrowByteScan {
    public static int[] Count(string path, byte[][] needles) {
        int[] counts = new int[needles.Length];
        int maxLen = 1;
        bool[] first = new bool[256];
        for (int k = 0; k < needles.Length; k++) {
            if (needles[k].Length == 0) continue;
            if (needles[k].Length > maxLen) maxLen = needles[k].Length;
            first[needles[k][0]] = true;
        }
        const int CH = 4 * 1024 * 1024;
        byte[] buf = new byte[CH + maxLen];
        int keep = 0;
        using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite, 65536)) {
            bool eof = false;
            while (!eof) {
                int read = fs.Read(buf, keep, CH);
                if (read <= 0) { eof = true; read = 0; }
                int total = keep + read;
                for (int i = keep; i < total; i++) {
                    byte b = buf[i];
                    if (b >= 65 && b <= 90) buf[i] = (byte)(b + 32);
                }
                int limit = eof ? total : Math.Max(0, total - (maxLen - 1));
                for (int i = 0; i < limit; i++) {
                    if (!first[buf[i]]) continue;
                    for (int k = 0; k < needles.Length; k++) {
                        byte[] nd = needles[k];
                        int len = nd.Length;
                        if (len == 0 || nd[0] != buf[i] || i + len > total) continue;
                        int j = 1;
                        while (j < len && buf[i + j] == nd[j]) j++;
                        if (j == len) counts[k]++;
                    }
                }
                if (!eof) {
                    keep = total - limit;
                    if (keep > 0) Buffer.BlockCopy(buf, limit, buf, 0, keep);
                }
            }
        }
        return counts;
    }

    // Where needle (already lower case) starts, case-folded like Count, in file order.
    // Stops collecting after limit offsets: the caller refuses a file with more anyway.
    public static long[] Offsets(string path, byte[] needle, int limit) {
        var res = new System.Collections.Generic.List<long>();
        int n = needle.Length;
        if (n == 0) return res.ToArray();
        const int CH = 4 * 1024 * 1024;
        byte[] buf = new byte[CH + n];
        int keep = 0;
        long baseOff = 0;
        using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite, 65536)) {
            bool eof = false;
            while (!eof && res.Count < limit) {
                int read = fs.Read(buf, keep, CH);
                if (read <= 0) { eof = true; read = 0; }
                int total = keep + read;
                for (int i = keep; i < total; i++) {
                    byte b = buf[i];
                    if (b >= 65 && b <= 90) buf[i] = (byte)(b + 32);
                }
                int lim = eof ? total : Math.Max(0, total - (n - 1));
                for (int i = 0; i + n <= total && i < lim && res.Count < limit; i++) {
                    if (buf[i] != needle[0]) continue;
                    int j = 1;
                    while (j < n && buf[i + j] == needle[j]) j++;
                    if (j == n) res.Add(baseOff + i);
                }
                if (!eof) {
                    keep = total - lim;
                    if (keep > 0) Buffer.BlockCopy(buf, lim, buf, 0, keep);
                    baseOff += lim;
                }
            }
        }
        return res.ToArray();
    }
}
'@

function Get-PrivatePatterns {
    <#
    What must not appear in a package, derived from THIS machine unless the
    parameters say otherwise (the selftest stands in for another machine that way).
    Returns Patterns (strings; each is searched in UTF-8 and UTF-16LE) and Notes.
    #>
    param(
        [string[]] $Extra = @(),
        [string]   $ProfilePath,
        [string]   $User,
        [string[]] $Hosts
    )
    if (-not $PSBoundParameters.ContainsKey('ProfilePath')) { $ProfilePath = $env:USERPROFILE }
    if (-not $PSBoundParameters.ContainsKey('User'))        { $User        = $env:USERNAME }
    if (-not $PSBoundParameters.ContainsKey('Hosts'))       { $Hosts       = @($env:COMPUTERNAME, [Environment]::MachineName) }

    $pats  = @()
    $notes = @()
    $ProfilePath = ([string]$ProfilePath).TrimEnd('\', '/')
    if ($ProfilePath) {
        $bs    = $ProfilePath.Replace('/', '\')
        $pats += $bs
        $pats += $ProfilePath.Replace('\', '/')
        $pats += $bs.Replace('\', '\\')
    }
    if ($User) {
        $pats += "\Users\$User\"
        $pats += "/Users/$User/"
        $pats += "\\Users\\$User\\"
        $pats += "/home/$User/"
        # The bare name too (#196 C2): "no references to the builder" is wider than paths.
        if ($User.Length -lt 4) { $notes += "user name '$User' is shorter than 4 characters and is not searched bare" }
        else                    { $pats  += $User }
    }
    foreach ($h in $Hosts) {
        if (-not $h) { continue }
        if ($h.Length -lt 4) { $notes += "host name '$h' is shorter than 4 characters and is not searched"; continue }
        $pats += $h
    }
    foreach ($e in $Extra) { if ($e) { $pats += $e } }
    $seen = @{}
    $uniq = @()
    foreach ($p in $pats) {
        $k = $p.ToLowerInvariant()
        if (-not $seen.ContainsKey($k)) { $seen[$k] = $true; $uniq += $p }
    }
    return [pscustomobject]@{ Patterns = [string[]]$uniq; Notes = [string[]]$notes }
}

function Find-PrivateData {
    # Path, Pattern, Encoding and Count for every pattern found in any file under Root.
    param([string] $Root, [string[]] $Patterns)
    if (-not ('CrowByteScan' -as [type])) { Add-Type -TypeDefinition $CROW_BYTE_SCAN_SOURCE -Language CSharp }
    $meta    = @()
    $needles = @()
    foreach ($p in $Patterns) {
        foreach ($enc in @(@{ N = 'utf-8'; E = [Text.Encoding]::UTF8 }, @{ N = 'utf-16le'; E = [Text.Encoding]::Unicode })) {
            $meta    += [pscustomobject]@{ Pattern = $p; Encoding = $enc.N }
            $needles += ,([byte[]]$enc.E.GetBytes($p.ToLowerInvariant()))
        }
    }
    $arr = New-Object 'byte[][]' $needles.Count
    for ($i = 0; $i -lt $needles.Count; $i++) { $arr[$i] = $needles[$i] }
    $root = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\')
    $hits = @()
    foreach ($f in Get-ChildItem -LiteralPath $root -Recurse -File -Force) {
        $counts = [CrowByteScan]::Count($f.FullName, $arr)
        for ($i = 0; $i -lt $counts.Length; $i++) {
            if ($counts[$i] -gt 0) {
                $hits += [pscustomobject]@{
                    Path = $f.FullName.Substring($root.Length + 1); Pattern = $meta[$i].Pattern
                    Encoding = $meta[$i].Encoding; Count = $counts[$i] }
            }
        }
    }
    return ,@($hits)
}

function ConvertFrom-AllowEntry {
    param([string] $Entry)
    $f = $Entry -split ' @@ ', 5
    if ($f.Count -ne 5) { throw "privacy allowlist entry is malformed: $Entry" }
    return [pscustomobject]@{ Glob = $f[0]; Name = $f[1]; Max = [int]$f[2]; Label = $f[3]; Regex = $f[4] }
}

function Get-BareUserName {
    # The pattern that is the bare user name: the one whose \Users\<it>\ is also searched.
    # $null when there is none (a name under 4 characters is not searched bare).
    param([string[]] $Patterns)
    foreach ($p in $Patterns) {
        if ($Patterns -contains ('\Users\' + $p + '\')) { return $p }
    }
    return $null
}

function Test-HitInAllowedContext {
    # $true when Re matches starting at or before the hit and running across all of it.
    param([string] $Window, [int] $HitAt, [int] $HitLen, [regex] $Re)
    for ($s = $HitAt; $s -ge 0; $s--) {
        $m = $Re.Match($Window, $s)
        if ($m.Success -and $m.Index -eq $s -and ($m.Index + $m.Length) -ge ($HitAt + $HitLen)) { return $true }
    }
    return $false
}

function Get-HitWindow {
    # The bytes around a hit, ASCII-lowercased, as a Latin-1 string, and where the hit sits in it.
    param([string] $Path, [long] $Offset, [int] $Len)
    $lo  = [Math]::Max([long]0, $Offset - $ALLOW_WINDOW)
    $buf = New-Object byte[] ([int]($Offset - $lo) + $Len + $ALLOW_WINDOW)
    $fs  = New-Object IO.FileStream($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        [void]$fs.Seek($lo, [IO.SeekOrigin]::Begin)
        $got = 0
        while ($got -lt $buf.Length) {
            $r = $fs.Read($buf, $got, $buf.Length - $got)
            if ($r -le 0) { break }
            $got += $r
        }
    } finally { $fs.Dispose() }
    for ($i = 0; $i -lt $got; $i++) { if ($buf[$i] -ge 65 -and $buf[$i] -le 90) { $buf[$i] += 32 } }
    return [pscustomobject]@{
        Text  = [Text.Encoding]::GetEncoding('iso-8859-1').GetString($buf, 0, $got)
        HitAt = [int]($Offset - $lo)
    }
}

function Split-AllowedHits {
    <#
    Splits the hits into Refused and Allowed. Only the bare user name, only as UTF-8, only in a
    file an entry names, only inside the entry's context, only up to its maximum is allowed;
    every other hit stays refused. Refused hits carry a Reason ('' when none to give).
    #>
    param([string] $Root, $Hits, [string[]] $Patterns, [string[]] $Allow = $PRIVACY_ALLOW)
    $bare    = Get-BareUserName -Patterns $Patterns
    $entries = @($Allow | ForEach-Object { ConvertFrom-AllowEntry -Entry $_ })
    $refused = @()
    $allowed = @()
    foreach ($h in $Hits) {
        $mine = @()
        if ($bare -and $h.Encoding -eq 'utf-8' -and $h.Pattern -ieq $bare) {
            $mine = @($entries | Where-Object { $_.Name -ieq $bare -and $h.Path -like $_.Glob })
        }
        $keep = { param($n, $why) [pscustomobject]@{ Path = $h.Path; Pattern = $h.Pattern; Encoding = $h.Encoding; Count = $n; Reason = $why } }
        if ($mine.Count -eq 0) { $refused += (& $keep $h.Count ''); continue }
        $cap = ($mine | Measure-Object -Property Max -Sum).Sum
        if ($h.Count -gt $cap) { $refused += (& $keep $h.Count "more than the allowed maximum of $cap"); continue }
        $full    = Join-Path $Root $h.Path
        $needle  = [byte[]][Text.Encoding]::UTF8.GetBytes($h.Pattern.ToLowerInvariant())
        $offsets = [CrowByteScan]::Offsets($full, $needle, $cap + 1)
        $res     = @($mine | ForEach-Object { [regex]::new('\G(?:' + $_.Regex + ')') })
        $tally   = New-Object 'int[]' $mine.Count
        $uncovered = 0
        foreach ($off in $offsets) {
            $w = Get-HitWindow -Path $full -Offset $off -Len $needle.Length
            $k = -1
            for ($i = 0; $i -lt $mine.Count; $i++) {
                if (Test-HitInAllowedContext -Window $w.Text -HitAt $w.HitAt -HitLen $needle.Length -Re $res[$i]) { $k = $i; break }
            }
            if ($k -ge 0) { $tally[$k]++ } else { $uncovered++ }
        }
        if ($uncovered -gt 0) { $refused += (& $keep $uncovered 'outside the allowed contexts') }
        for ($i = 0; $i -lt $mine.Count; $i++) {
            if ($tally[$i] -gt $mine[$i].Max) {
                $refused += (& $keep $tally[$i] ("more than the allowed maximum of {0} for {1}" -f $mine[$i].Max, $mine[$i].Label))
            } elseif ($tally[$i] -gt 0) {
                $allowed += [pscustomobject]@{ Path = $h.Path; Label = $mine[$i].Label; Count = $tally[$i]; Max = $mine[$i].Max }
            }
        }
    }
    return [pscustomobject]@{ Refused = @($refused); Allowed = @($allowed) }
}

function Invoke-PrivacyGate {
    # $true when the tree is clean. Prints every hit; the caller has to refuse.
    param([string] $Root, [string[]] $Patterns, [string[]] $Notes = @())
    foreach ($n in $Notes) { Write-Host "  privacy gate note: $n" }
    $nFiles = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Force).Count
    Write-Host ("privacy gate: $nFiles files, $($Patterns.Count) patterns, UTF-8 and UTF-16LE")
    $found = Find-PrivateData -Root $Root -Patterns $Patterns
    $split = Split-AllowedHits -Root (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\') -Hits $found -Patterns $Patterns
    foreach ($a in $split.Allowed) {
        Write-Host ("  privacy gate INFO: allowed {0}  {1}  x{2} (maximum {3})" -f $a.Path, $a.Label, $a.Count, $a.Max)
    }
    $hits = @($split.Refused)
    if ($hits.Count -eq 0) {
        $nAllowed = ($split.Allowed | Measure-Object -Property Count -Sum).Sum
        Write-Host ("  privacy gate: clean" + $(if ($nAllowed) { " ($nAllowed allowed hits, see INFO)" } else { '' }))
        return $true
    }
    $nHit = @($hits | ForEach-Object { $_.Path } | Sort-Object -Unique).Count
    Write-Host "PRIVACY GATE: REFUSING TO PACK -- $($hits.Count) hits in $nHit files" -ForegroundColor Red
    foreach ($h in $hits) {
        Write-Host (("  {0}  pattern '{1}'  {2}  x{3}" -f $h.Path, $h.Pattern, $h.Encoding, $h.Count) + $(if ($h.Reason) { "  ($($h.Reason))" } else { '' }))
    }
    Write-Host "  nothing was written. Remove the data from the source (or rebuild with path remapping); there is no override." -ForegroundColor Red
    return $false
}

function Invoke-StageGate {
    <#
    Both checks on a finished stage, before MANIFEST.json or the zip exist: nothing
    outside the shipped set, then the privacy scan. $true means the stage may be
    packed. One function so the packing path calls ONE thing and the selftest can
    call the same thing.
    #>
    param([string] $Stage, [string[]] $Patterns, [string[]] $Notes = @())
    $root  = (Resolve-Path -LiteralPath $Stage).Path.TrimEnd('\')
    $rels  = @(Get-ChildItem -LiteralPath $root -Recurse -File -Force | ForEach-Object { $_.FullName.Substring($root.Length + 1) })
    $bad   = Get-ShippedSetViolations -Paths $rels
    if ($bad.Count -gt 0) {
        Write-Host "REFUSING TO PACK -- $($bad.Count) files are not in the shipped set:" -ForegroundColor Red
        foreach ($b in $bad) { Write-Host "  $($b.Path)  ($($b.Reason))" }
        return $false
    }
    return (Invoke-PrivacyGate -Root $root -Patterns $Patterns -Notes $Notes)
}

$script:selftestOk  = 0
$script:selftestRed = 0

function Check {
    param([string] $Name, [bool] $Passed)
    if ($Passed) { Write-Host "  ok   $Name";                          $script:selftestOk++ }
    else         { Write-Host "  FAIL $Name" -ForegroundColor Red;     $script:selftestRed++ }
}

function Get-DevOnlyFiles {
    <#
    Which of these files are developer equipment that must not ship?

    A predicate rather than a literal list at the copy site, and it lives ABOVE
    the selftest exit on purpose. The version this replaces would have made the
    decision below `if ($Selftest) { exit }`, where no check can reach it -- the
    same shape that let install.ps1 report "42 checks pass" on 2026-08-10 while
    the code those checks were written for sat 113 lines further down.

    Matching is on the file NAME, so a path separator or a parent directory
    cannot smuggle one through.

    RETURNS `,@(...)` AND NOT `@(...)`. PowerShell unwraps a one-element array on
    return, and one element is the normal case here -- exactly one suite ships in
    cli/. Without the comma the caller gets a String, `.Count` still answers 1,
    and `[0]` hands back the letter "C" of "C:\...". Caught by the check below on
    2026-08-10, which is the only reason this line reads the way it does.
    #>
    param([string[]] $Paths)
    return ,@($Paths | Where-Object {
        $null -ne $_ -and [System.IO.Path]::GetFileName($_) -like 'test_*.py'
    })
}

<#
    The interpreter the repository checkers run under.

    Resolved rather than assumed, and a miss is an ERROR at the call site rather
    than a skip: a gate that quietly passes when it cannot find Python is a gate
    that passes on exactly the machine where nobody would notice.
#>
function Find-PythonCommand {
    foreach ($c in @('python', 'python3')) {
        $hit = Get-Command $c -ErrorAction SilentlyContinue
        if ($hit) { return ,@($hit.Source) }
    }
    # The launcher needs the version argument; without it a machine with only
    # Python 2 registered would answer.
    $py = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($py) { return ,@($py.Source, '-3') }
    return ,@()
}

<#
    THE GATE, AND IT IS THE REASON check_shared_core.py IS NOT A SECOND OPINION.

    Measured 2026-08-12 while planning #90's E7: check_operating_point.py runs in
    no .github/workflows, no git hook and no call from this script -- it runs only
    when a human thinks of it. A second checker of the same build would inherit
    that defect on the day it was written.

    So both run HERE, before anything is staged. This is the cheapest place there
    is, because every release goes through this script anyway, and it is the only
    path somebody MUST take. A checker that does not run when a package is cut is
    an opinion.

    BEFORE THE STAGE DIRECTORY IS TOUCHED, not after: the caller's demand is that
    a red checker leaves NO stage behind, and a gate that fires after
    `Remove-Item $stage` has already destroyed the previous one.

    Returns the checkers that came back non-zero. -Names and -Root are parameters
    so the selftest can point it at a deliberately red script -- a gate whose own
    failure path is never exercised is the next thing to rot.
#>
function Invoke-RepoCheckers {
    param(
        [string[]] $Names = @('check_shared_core.py', 'check_operating_point.py'),
        [string]   $Root  = $PSScriptRoot
    )

    $prefix = Find-PythonCommand
    if ($prefix.Count -eq 0) {
        throw "no Python interpreter found (tried python, python3, py -3) -- the release checkers cannot run, and a release that skips them is not checked"
    }
    $exe  = $prefix[0]
    $rest = @()
    if ($prefix.Count -gt 1) { $rest = $prefix[1..($prefix.Count - 1)] }

    $red = @()
    foreach ($name in $Names) {
        $tool = Join-Path $Root $name
        if (-not (Test-Path $tool)) { throw "release checker missing: $tool" }
        Write-Host "  $name"
        $argv = $rest + @($tool)
        & $exe @argv | ForEach-Object { Write-Host "    $_" }
        if ($LASTEXITCODE -ne 0) { $red += "$name (exit $LASTEXITCODE)" }
    }
    return ,@($red)
}

function Invoke-Selftest {

    Write-Host "pack-release selftest"

    # System-library classification, both directions. A classifier that says yes to
    # everything would make the completeness check vacuous, so both are asserted.
    Check "KERNEL32.dll counts as a system library"      (Test-SystemDll 'KERNEL32.dll')
    Check "api-ms-win-crt-math-l1-1-0.dll counts too"    (Test-SystemDll 'api-ms-win-crt-math-l1-1-0.dll')
    Check "nvcuda.dll counts (driver, not redistributable)" (Test-SystemDll 'nvcuda.dll')
    Check "cublas64_13.dll does NOT count"          (-not (Test-SystemDll 'cublas64_13.dll'))
    Check "MSVCP140.dll does NOT count"             (-not (Test-SystemDll 'MSVCP140.dll'))
    Check "ggml-base.dll does NOT count"            (-not (Test-SystemDll 'ggml-base.dll'))

    # NVIDIA at install time: the named allowlist, and the closure check that uses it.
    Check "the install-time NVIDIA list is exactly cublas64_13.dll and cublasLt64_13.dll" ((($NVIDIA_AT_INSTALL | Sort-Object) -join ',') -eq 'cublas64_13.dll,cublasLt64_13.dll')
    Check "both names are on it, in any case"       ((Test-NvidiaAtInstall 'CUBLAS64_13.DLL') -and (Test-NvidiaAtInstall 'cublasLt64_13.dll'))
    Check "NEGATIVE: no other NVIDIA name is (cudart, nvrtc, another cublas version, a wildcard match)" (
        -not ((Test-NvidiaAtInstall 'cudart64_13.dll') -or (Test-NvidiaAtInstall 'nvrtc64_130_0.dll') -or
              (Test-NvidiaAtInstall 'cublas64_12.dll') -or (Test-NvidiaAtInstall 'cublasXX64_13.dll') -or (Test-NvidiaAtInstall 'cublas64_13.dll.bak')))
    Check "an NVIDIA file in a staged set is found"  ((Get-NvidiaFiles -Paths @('C:\s\bin\llama-server.exe', 'C:\s\bin\cublasLt64_13.dll')).Count -eq 1)
    Check "a set without one is clean"               ((Get-NvidiaFiles -Paths @('C:\s\bin\llama-server.exe', 'C:\s\bin\msvcp140.dll')).Count -eq 0)
    & {
        # The closure check against synthetic imports: dumpbin is replaced for this scope only.
        function Get-Imports {
            param([string] $Dumpbin, [string] $Path)
            switch ([IO.Path]::GetFileName($Path)) {
                'ggml-cuda.dll' { return @('KERNEL32.dll', 'cublas64_13.dll', 'cublasLt64_13.dll') }
                'sd-server.exe' { return @('cublasLt64_13.dll', 'MSVCP140.dll') }
                'odd.dll'       { return @('mystery64.dll') }
                'older.dll'     { return @('cublas64_12.dll') }
                'cudart.dll'    { return @('cudart64_13.dll') }
                default         { return @() }
            }
        }
        $ng = @('C:\s\bin\ggml-cuda.dll', 'C:\s\bin\sd-server.exe', 'C:\s\bin\msvcp140.dll')
        Check "the NVIDIA imports are accepted when the install provides them"  ((Test-PackageComplete -Dumpbin 'x' -Files $ng -NvidiaAtInstall).Count -eq 0)
        Check "without that switch they are still reported (the old closure)"   ((Test-PackageComplete -Dumpbin 'x' -Files $ng).Needs -contains 'cublas64_13.dll')
        $bad = @(Test-PackageComplete -Dumpbin 'x' -Files ($ng + 'C:\s\bin\odd.dll') -NvidiaAtInstall)
        Check "NEGATIVE: an unrelated missing DLL still refuses, and is the only one named" ($bad.Count -eq 1 -and $bad[0].Needs -eq 'mystery64.dll' -and $bad[0].RequiredBy -eq 'odd.dll')
        Check "NEGATIVE: an NVIDIA DLL that is not on the list still refuses (cublas 12)" ((Test-PackageComplete -Dumpbin 'x' -Files @('C:\s\bin\older.dll') -NvidiaAtInstall).Needs -contains 'cublas64_12.dll')
        Check "NEGATIVE: cudart64_13.dll is not on the list either"               ((Test-PackageComplete -Dumpbin 'x' -Files @('C:\s\bin\cudart.dll') -NvidiaAtInstall).Needs -contains 'cudart64_13.dll')
        Check "a DLL present in the package still satisfies its import"           ((@(Test-PackageComplete -Dumpbin 'x' -Files @('C:\s\bin\odd.dll', 'C:\s\bin\mystery64.dll') -NvidiaAtInstall)).Count -eq 0)
    }

    # What ships and what does not. Both directions again, because a predicate
    # that says no to everything would quietly put the suite back in the package
    # and this check would still be green.
    $cli = @('C:\r\cli\crow_gui.py', 'C:\r\cli\test_crow_gui.py', 'C:\r\cli\fonts\OFL.txt')
    $dev = Get-DevOnlyFiles -Paths $cli
    Check "the unit suite is developer-only"        ($dev.Count -eq 1 -and $dev[0] -like '*test_crow_gui.py')
    Check "the client itself is NOT"                ($dev -notcontains 'C:\r\cli\crow_gui.py')
    Check "and neither is the font licence"         ($dev -notcontains 'C:\r\cli\fonts\OFL.txt')
    # A nested copy must not slip past on its parent directory.
    Check "a suite in a subdirectory is caught too" ((Get-DevOnlyFiles -Paths @('C:\r\cli\sub\test_x.py')).Count -eq 1)
    Check "an empty list is not an error"           ((Get-DevOnlyFiles -Paths @()).Count -eq 0)

    # The version stamp (#187): crow_core.py owns it, crow.py is the fallback
    # for a tree from before, and a tree with neither gives no number.
    $vDir = Join-Path ([IO.Path]::GetTempPath()) ("crow-ver-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $vDir | Out-Null
    try {
        Set-Content -LiteralPath (Join-Path $vDir 'crow_core.py') -Encoding utf8 -Value @('"""core"""', 'VERSION = "9.9.9"')
        Check "the version is read from crow_core.py"      ((Get-VersionLiteral -CliDir $vDir) -eq '9.9.9')
        Set-Content -LiteralPath (Join-Path $vDir 'crow_core.py') -Encoding utf8 -Value @('"""core"""')
        Set-Content -LiteralPath (Join-Path $vDir 'crow.py') -Encoding utf8 -Value @('VERSION = "2.8.5"')
        Check "an older tree falls back to crow.py"        ((Get-VersionLiteral -CliDir $vDir) -eq '2.8.5')
        Set-Content -LiteralPath (Join-Path $vDir 'crow.py') -Encoding utf8 -Value @('VERSIONS = ["1.2.3"]')
        Check "NEGATIVE: no literal in either reads as null" ($null -eq (Get-VersionLiteral -CliDir $vDir))
    } finally {
        Remove-Item $vDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    $own = Get-VersionLiteral -CliDir (Join-Path $PSScriptRoot '..\cli')
    Check "this checkout's own version is found ($own)" ($own -match '^\d+\.\d+\.\d+$')

    # The release gate, both directions. A gate that has only ever been seen
    # green is a gate nobody has watched refuse, and refusing is its whole job.
    $python = Find-PythonCommand
    Check "a Python interpreter is available for the checkers" ($python.Count -gt 0)
    if ($python.Count -gt 0) {
        $gateDir = Join-Path ([IO.Path]::GetTempPath()) ("crow-gate-" + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Force -Path $gateDir | Out-Null
        try {
            Set-Content -LiteralPath (Join-Path $gateDir 'green.py') -Encoding utf8 `
                -Value 'import sys; print("RESULT: fixture agrees"); sys.exit(0)'
            Set-Content -LiteralPath (Join-Path $gateDir 'red.py') -Encoding utf8 `
                -Value 'import sys; print("RESULT: fixture disagrees"); sys.exit(1)'
            $ok  = Invoke-RepoCheckers -Names @('green.py') -Root $gateDir
            Check "a checker that exits 0 does not stop the pack" ($ok.Count -eq 0)
            $bad = Invoke-RepoCheckers -Names @('red.py', 'green.py') -Root $gateDir
            Check "a checker that exits 1 is collected and named" ($bad.Count -eq 1 -and $bad[0] -like 'red.py*')
            # Both checkers run even when the first is red: a gate that stops at
            # the first failure hides the second, and the person fixing this
            # would then cut a package to find out.
            $both = Invoke-RepoCheckers -Names @('red.py', 'red.py') -Root $gateDir
            Check "a red checker does not short-circuit the rest" ($both.Count -eq 2)
        } finally {
            Remove-Item $gateDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    # Named rather than assumed: this is the list the packing path below runs,
    # and #90's E7 exists because check_operating_point.py was in no such list.
    # Read off the function itself, so dropping one from the default list is
    # caught here rather than at the next release nobody checked.
    $gateBody = ${function:Invoke-RepoCheckers}.ToString()
    Check "the gate's default list names check_shared_core.py"     ($gateBody -match 'check_shared_core\.py')
    Check "the gate's default list names check_operating_point.py" ($gateBody -match 'check_operating_point\.py')

    # The image server (#314): which files are taken, and when two builds clash.
    # Synthetic files -- no Windows toolchain is needed to answer either question.
    $sdDir = Join-Path ([IO.Path]::GetTempPath()) ("crow-sd-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path (Join-Path $sdDir 'build'), (Join-Path $sdDir 'stage'), (Join-Path $sdDir 'half') | Out-Null
    try {
        foreach ($n in @('sd-server.exe', 'sd-cli.exe', 'ggml-base.dll', 'stable-diffusion.lib')) {
            Set-Content -LiteralPath (Join-Path $sdDir "build\$n") -Value $n
        }
        $sd = Get-SdBinaries -Dir (Join-Path $sdDir 'build')
        Check "-SdBuildDir yields sd-server.exe and sd-cli.exe"   ($sd.Count -eq 2 -and ($sd | Split-Path -Leaf) -contains 'sd-server.exe' -and ($sd | Split-Path -Leaf) -contains 'sd-cli.exe')
        Check "NEGATIVE: and not a ggml DLL of its own build"      (($sd | Split-Path -Leaf) -notcontains 'ggml-base.dll')
        Set-Content -LiteralPath (Join-Path $sdDir 'half\sd-server.exe') -Value 'x'
        $threw = $false
        try { Get-SdBinaries -Dir (Join-Path $sdDir 'half') | Out-Null } catch { $threw = $_.Exception.Message -like '*sd-cli.exe*' }
        Check "NEGATIVE: a build without sd-cli.exe is refused, and named" $threw
        Set-Content -LiteralPath (Join-Path $sdDir 'stage\cublas64_13.dll') -Value 'same'
        Set-Content -LiteralPath (Join-Path $sdDir 'build\cublas64_13.dll') -Value 'same'
        Check "a shared cublas64_13.dll with the same bytes is not a clash" ((Get-NameClashes -Dest (Join-Path $sdDir 'stage') -Incoming @((Join-Path $sdDir 'build\cublas64_13.dll'))).Count -eq 0)
        Set-Content -LiteralPath (Join-Path $sdDir 'build\cublas64_13.dll') -Value 'other'
        $c = Get-NameClashes -Dest (Join-Path $sdDir 'stage') -Incoming @((Join-Path $sdDir 'build\cublas64_13.dll'), (Join-Path $sdDir 'build\sd-cli.exe'))
        Check "NEGATIVE: the same name with other bytes is a clash, and only that one" ($c.Count -eq 1 -and $c[0] -eq 'cublas64_13.dll')
    } finally {
        Remove-Item $sdDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    # What may ship, and the privacy gate (#196 C2). Synthetic trees only: a fake
    # builder, so no check depends on who runs this. The first tree has the shape of
    # the 2.8.5 mistake -- a cli\runs\*.log -- and a binary that carries the
    # builder's profile path as UTF-16LE, which is how a DLL stores a __FILE__.
    $fakeProfile = 'C:\Users\crow-selftest-fake'
    $fakeHost    = 'FAKEHOST-SELFTEST'
    $fake = Get-PrivatePatterns -Extra @('lab-secret-name') -ProfilePath $fakeProfile -User 'crow-selftest-fake' -Hosts @($fakeHost)
    $pkRoot = Join-Path ([IO.Path]::GetTempPath()) ("crow-pack-" + [Guid]::NewGuid().ToString('N'))
    try {
        $src = Join-Path $pkRoot 'src'
        foreach ($rel in @('cli\crow_core.py', 'cli\fonts\OFL.txt', 'cli\runs\x.log', 'cli\runs\llama-server-8080.log',
                           'cli\sub\notes.log', 'cli\__pycache__\a.pyc', 'cli\test_a.py', 'cli\.env', 'cli\secrets.json',
                           'cli\session.json', 'kits\pathtracer\runs\y.log')) {
            $p = Join-Path $src $rel
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $p) | Out-Null
            Set-Content -LiteralPath $p -Value 'synthetic'
        }
        $cliCopy = Copy-ShippedTree -Source (Join-Path $src 'cli') -Dest (Join-Path $pkRoot 'stage\cli')
        $kitCopy = Copy-ShippedTree -Source (Join-Path $src 'kits') -Dest (Join-Path $pkRoot 'stage\kits')
        $has = { param($r) Test-Path -LiteralPath (Join-Path $pkRoot "stage\$r") }
        Check "cli\runs\x.log is not copied (the 2.8.5 finding)" (-not (& $has 'cli\runs\x.log') -and -not (& $has 'cli\runs\llama-server-8080.log'))
        Check "a *.log anywhere under cli is not copied"          (-not (& $has 'cli\sub\notes.log'))
        Check "__pycache__, *.pyc and test_*.py are not copied"   (-not (& $has 'cli\__pycache__\a.pyc') -and -not (& $has 'cli\test_a.py'))
        Check ".env, secrets.json and session files are not copied" (-not (& $has 'cli\.env') -and -not (& $has 'cli\secrets.json') -and -not (& $has 'cli\session.json'))
        Check "a runs\ directory inside kits is not copied"       (-not (& $has 'kits\pathtracer\runs\y.log'))
        Check "the client and the font licence ARE copied"        ((& $has 'cli\crow_core.py') -and (& $has 'cli\fonts\OFL.txt') -and $cliCopy.Copied -eq 2)

        $okSet  = @('LICENSE', 'cli\crow_core.py', 'bin\llama-server.exe', 'kits\pathtracer\kit.json',
                    'templates\0731-chat-template.jinja', 'manifests\operating-point.json', 'MANIFEST.json')
        $badSet = @('docs\x.md', 'stray.txt', 'manifests\shared-core.json', 'templates\other.jinja',
                    'cli\runs\x.log', 'bin\a.log', 'cli\.env.local', 'kits\pathtracer\runs\y.log', 'cli\sessions\a.txt')
        Check "the declared shipped set accepts what ships"              ((Get-ShippedSetViolations -Paths $okSet).Count -eq 0)
        $mfRepo = Join-Path $pkRoot 'mf-repo'
        New-Item -ItemType Directory -Force -Path (Join-Path $mfRepo 'manifests') | Out-Null
        foreach ($n in @('operating-point.json', 'stack.json')) { Set-Content -LiteralPath (Join-Path $mfRepo "manifests\$n") -Value '{"x": 1}' -Encoding ascii }
        $mfStaged = Copy-ManifestFiles -Repo $mfRepo -Stage (Join-Path $pkRoot 'mf-stage')
        Check "manifests\stack.json is staged and in the shipped set (#196 P1)" ((Test-Path -LiteralPath (Join-Path $pkRoot 'mf-stage\manifests\stack.json')) -and $mfStaged.Count -eq 2 -and (Get-ShippedSetViolations -Paths @('manifests\stack.json')).Count -eq 0)
        Check "NEGATIVE: anything outside it or on an exclude rule is named" ((Get-ShippedSetViolations -Paths $badSet).Count -eq $badSet.Count)
        $teRepo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
        $teStaged = Copy-ToolFiles -Repo $teRepo -Stage (Join-Path $pkRoot 'te-stage')
        Check "tools\te_rename.py is staged byte for byte and in the shipped set (#196 P2)" ((Test-Path -LiteralPath $teStaged) -and (Get-FileHash -LiteralPath $teStaged).Hash -eq (Get-FileHash -LiteralPath (Join-Path $teRepo 'tools\te_rename.py')).Hash -and (Get-ShippedSetViolations -Paths @('tools\te_rename.py')).Count -eq 0)
        Check "NEGATIVE: any other tools\ file is outside the shipped set" ((Get-ShippedSetViolations -Paths @('tools\pack-release.ps1', 'tools\check_stack.py')).Count -eq 2)
        Check "te_rename.py passes the privacy gate"                     ((Find-PrivateData -Root (Join-Path $pkRoot 'te-stage') -Patterns $fake.Patterns).Count -eq 0)
        $teThrew = $false
        try { Copy-ToolFiles -Repo $mfRepo -Stage (Join-Path $pkRoot 'te-stage2') | Out-Null } catch { $teThrew = $true }
        Check "NEGATIVE: a checkout without tools\te_rename.py is refused" $teThrew

        # the gate, one spelling at a time
        $scan = Join-Path $pkRoot 'scan'
        New-Item -ItemType Directory -Force -Path (Join-Path $scan 'bin') | Out-Null
        $dll = Join-Path $scan 'bin\fake.dll'
        $bytes = [byte[]]@(0x4D, 0x5A, 0x00, 0x90) + [Text.Encoding]::Unicode.GetBytes($fakeProfile + '\dev\llama.cpp\ggml.c') + [byte[]]@(0, 0, 0)
        [IO.File]::WriteAllBytes($dll, $bytes)
        $h = Find-PrivateData -Root $scan -Patterns $fake.Patterns
        Check "the profile path as UTF-16LE inside a binary is found" ($h.Count -ge 1 -and @($h | Where-Object { $_.Encoding -eq 'utf-16le' -and $_.Path -eq 'bin\fake.dll' }).Count -ge 1)
        [IO.File]::WriteAllBytes($dll, [Text.Encoding]::UTF8.GetBytes(($fakeProfile + '\a ') * 3))
        $h = Find-PrivateData -Root $scan -Patterns $fake.Patterns
        Check "the same path as UTF-8 is found, and counted per occurrence" (@($h | Where-Object { $_.Encoding -eq 'utf-8' -and $_.Pattern -eq $fakeProfile -and $_.Count -eq 3 }).Count -eq 1)
        $spellings = @('c:/USERS/Crow-Selftest-Fake/dev', 'see /home/crow-selftest-fake/.cache',
                       'C:\\Users\\crow-selftest-fake\\x', "built on $($fakeHost.ToLowerInvariant())", 'a lab-secret-name b')
        $missed = @()
        foreach ($t in $spellings) {
            [IO.File]::WriteAllBytes($dll, [Text.Encoding]::UTF8.GetBytes($t))
            if ((Find-PrivateData -Root $scan -Patterns $fake.Patterns).Count -eq 0) { $missed += $t }
        }
        Check "slash spelling and case, JSON-escaped, /home/<user>/, host name, extra pattern are all found" ($missed.Count -eq 0)
        if ($missed.Count -gt 0) { Write-Host ("       missed: " + ($missed -join ' | ')) -ForegroundColor Red }
        # The needle starts 4 bytes before the end of the first 4 MB read block, so a
        # scanner that forgets to carry bytes across blocks misses it, and one that
        # carries them carelessly counts it twice.
        $fs = [IO.File]::Open($dll, 'Create')
        $fs.Write([byte[]]@(0x4D, 0x5A), 0, 2)
        $zeros = New-Object byte[] (4194304 - 4 - 2)
        $fs.Write($zeros, 0, $zeros.Length)
        $u = [Text.Encoding]::Unicode.GetBytes($fakeProfile)
        $fs.Write($u, 0, $u.Length)
        $fs.Close()
        $h = Find-PrivateData -Root $scan -Patterns $fake.Patterns
        Check "a hit straddling the 4 MB read block is found, once" (@($h | Where-Object { $_.Encoding -eq 'utf-16le' -and $_.Pattern -eq $fakeProfile -and $_.Count -eq 1 }).Count -eq 1)
        [IO.File]::WriteAllBytes($dll, [byte[]]@(0x4D, 0x5A) + [Text.Encoding]::Unicode.GetBytes('C:\Windows\System32\kernel32.dll') + [Text.Encoding]::UTF8.GetBytes('/usr/lib/x'))
        Check "NEGATIVE: a clean binary has no hits" ((Find-PrivateData -Root $scan -Patterns $fake.Patterns).Count -eq 0)
        $mine = Get-PrivatePatterns
        Check "by default the gate searches THIS machine's profile path" ((-not $env:USERPROFILE) -or ($mine.Patterns -contains $env:USERPROFILE.TrimEnd('\')))
        $short = Get-PrivatePatterns -ProfilePath $fakeProfile -User 'crow-selftest-fake' -Hosts @('pc')
        Check "a host name under 4 characters is noted, not searched" ($short.Patterns -notcontains 'pc' -and $short.Notes.Count -eq 1)

        # The bare user name, not only as a path segment: prose such as a model prompt
        # ("Write a report for <name>") is a reference to the builder too.
        [IO.File]::WriteAllBytes($dll, [Text.Encoding]::UTF8.GetBytes('Write a report for Crow-Selftest-Fake about the run'))
        $h = Find-PrivateData -Root $scan -Patterns $fake.Patterns
        $proseUtf8 = @($h | Where-Object { $_.Encoding -eq 'utf-8' -and $_.Pattern -eq 'crow-selftest-fake' })
        [IO.File]::WriteAllBytes($dll, [Text.Encoding]::Unicode.GetBytes('Write a report for Crow-Selftest-Fake about the run'))
        $h = Find-PrivateData -Root $scan -Patterns $fake.Patterns
        $proseUtf16 = @($h | Where-Object { $_.Encoding -eq 'utf-16le' -and $_.Pattern -eq 'crow-selftest-fake' })
        Check "the bare user name in prose is found, in UTF-8 and in UTF-16LE" ($proseUtf8.Count -ge 1 -and $proseUtf16.Count -ge 1)
        $shortUser = Get-PrivatePatterns -ProfilePath $fakeProfile -User 'abc' -Hosts @($fakeHost)
        Check "a user name under 4 characters is noted, not searched bare" ($shortUser.Patterns -notcontains 'abc' -and @($shortUser.Notes | Where-Object { $_ -like "*'abc'*" }).Count -eq 1)

        # the stage, end to end: the log is out AND the gate refuses on the DLL
        $stage = Join-Path $pkRoot 'stage'
        New-Item -ItemType Directory -Force -Path (Join-Path $stage 'bin') | Out-Null
        [IO.File]::WriteAllBytes((Join-Path $stage 'bin\fake.dll'), $bytes)
        $refused = Invoke-StageGate -Stage $stage -Patterns $fake.Patterns -Notes $fake.Notes 6>$null
        Check "a stage with a profile path in a DLL is refused, its log already out" ((-not $refused) -and -not (& $has 'cli\runs\x.log'))
        [IO.File]::WriteAllBytes((Join-Path $stage 'bin\fake.dll'), [byte[]]@(0x4D, 0x5A, 0, 0))
        $passed = Invoke-StageGate -Stage $stage -Patterns $fake.Patterns -Notes $fake.Notes 6>$null
        Check "the same stage with a clean DLL passes" ([bool]$passed)
        Set-Content -LiteralPath (Join-Path $stage 'cli\runs-copy.log') -Value 'x'
        $leaked = Invoke-StageGate -Stage $stage -Patterns $fake.Patterns -Notes $fake.Notes 6>$null
        Check "NEGATIVE: a *.log that reached the stage anyway is refused" (-not $leaked)

        # The scoped allowlist (#196 C6): upstream words that merely contain the owner's name.
        # The fake owner is "robin" because the allowlist is about that name; every other
        # case is synthetic, so no check depends on who runs this.
        $own   = Get-PrivatePatterns -ProfilePath 'C:\Users\robin' -User 'robin' -Hosts @($fakeHost)
        $alStg = Join-Path $pkRoot 'allowstage'
        $rr    = [Text.Encoding]::ASCII.GetBytes('east-stats random round-robin source-hash static-port')
        $mz    = [byte[]]@(0x4D, 0x5A, 0)
        $runAllow = {
            param([hashtable] $Files)
            if (Test-Path -LiteralPath $alStg) { Remove-Item -LiteralPath $alStg -Recurse -Force }
            New-Item -ItemType Directory -Force -Path (Join-Path $alStg 'bin') | Out-Null
            foreach ($k in $Files.Keys) { [IO.File]::WriteAllBytes((Join-Path $alStg $k), [byte[]]$Files[$k]) }
            $o = @(Invoke-StageGate -Stage $alStg -Patterns $own.Patterns -Notes $own.Notes 6>&1)
            [pscustomobject]@{
                Ok  = [bool]($o | Where-Object { $_ -is [bool] } | Select-Object -Last 1)
                Log = (($o | Where-Object { $_ -isnot [bool] } | ForEach-Object { "$_" }) -join "`n")
            }
        }
        $impl = 'bin\llama-server-impl.dll'
        $two  = $mz + $rr + [byte]0 + $rr
        $a = & $runAllow @{ $impl = $two }
        Check "ALLOW: round-robin twice in llama-server-impl.dll passes, and is logged as INFO" ($a.Ok -and $a.Log -match 'INFO: allowed bin\\llama-server-impl\.dll.*round-robin.*x2')
        $b = & $runAllow @{ 'bin\llama-server.exe' = ($mz + $rr) }
        Check "NEGATIVE: the same word in another file is refused" ($a.Ok -and -not $b.Ok -and $b.Log -match 'llama-server\.exe')
        $c = & $runAllow @{ $impl = ($two + [byte]0 + $rr) }
        Check "NEGATIVE: a third occurrence beyond the maximum is refused" ($a.Ok -and -not $c.Ok -and $c.Log -match 'maximum')
        $d = & $runAllow @{ $impl = ($two + [Text.Encoding]::ASCII.GetBytes(' Write a report for Robin about the run')) }
        Check "NEGATIVE: a bare name outside any allowed context, in an allowed file, is refused" ($a.Ok -and -not $d.Ok)
        $paths = @('C:\Users\robin\dev\llama.cpp\x.cpp', '/home/robin/src', '\Users\robin\')
        $leakedPaths = @($paths | Where-Object { (& $runAllow @{ $impl = ($two + [Text.Encoding]::ASCII.GetBytes(" $_")) }).Ok })
        Check "NEGATIVE: a profile path, /home/<name>/ or \Users\<name>\ in an allowed file is refused" ($a.Ok -and $leakedPaths.Count -eq 0)
        $e = & $runAllow @{ $impl = ($two + [Text.Encoding]::ASCII.GetBytes(" $fakeHost")) }
        Check "NEGATIVE: the host name is never allowlisted" ($a.Ok -and -not $e.Ok)
        $f = & $runAllow @{ $impl = ($mz + [Text.Encoding]::Unicode.GetBytes('round-robin')) }
        Check "NEGATIVE: the allowed word as UTF-16LE is not allowed" ($a.Ok -and -not $f.Ok)
        $other = Get-PrivatePatterns -ProfilePath 'C:\Users\round' -User 'round' -Hosts @($fakeHost)
        [IO.File]::WriteAllBytes((Join-Path $alStg $impl), [byte[]]$two)
        $g = @(Invoke-StageGate -Stage $alStg -Patterns $other.Patterns -Notes $other.Notes 6>&1 | Where-Object { $_ -is [bool] })
        Check "NEGATIVE: for a machine whose user is not robin the allowlist gives nothing" ($a.Ok -and -not [bool]($g | Select-Object -Last 1))
        # tokenizer vocabulary, the lines verbatim from sd-cli.exe: BPE merges and vocab JSON
        $vocab = [byte[]]@()
        foreach ($v in @('robin son</w>', '"Robin": 101068,', '"probing": 109172,', '"odrobin",', '"robinet",')) {
            $vocab += [byte[]]@(10)
            $vocab += [Text.Encoding]::ASCII.GetBytes($v)
        }
        $vocab += [byte[]]@(10, 0xE2, 0x96, 0x81, 0x52, 0x6F, 0x62, 0x69, 0x6E, 0x73, 0x20, 0x6F, 0x6E, 10)            # <U+2581>Robins on
        $vocab += [byte[]]@(10, 0xC4, 0xA0, 0x20, 0x52, 0x6F, 0x62, 0x69, 0x6E, 10)                                   # <U+0120> Robin
        $vocab += [byte[]]@(0x22, 0xE2, 0x96, 0x81, 0x52, 0x6F, 0x62, 0x69, 0x6E, 0x73, 0x6F, 0x6E, 0x22, 0x3A, 0x31, 0x2C) # "<U+2581>Robinson":1,
        $h1 = & $runAllow @{ 'bin\sd-cli.exe' = ($mz + $vocab); 'bin\sd-server.exe' = ($mz + $vocab) }
        Check "ALLOW: tokenizer vocabulary (merges lines, vocab JSON keys) passes in the sd binaries" ($h1.Ok -and $h1.Log -match 'INFO: allowed bin\\sd-cli\.exe.*tokenizer vocabulary')
        $h2 = & $runAllow @{ 'bin\llama.dll' = ($mz + $vocab) }
        Check "NEGATIVE: the same vocabulary in another file is refused" ($h1.Ok -and -not $h2.Ok)
        $line = [byte[]]@(10, 0xE2, 0x96, 0x81, 0x20, 0x52, 0x6F, 0x62, 0x69, 0x6E, 0x73, 0x6F, 0x6E, 10)
        $many = { param($n) $x = [byte[]]@(); for ($i = 0; $i -lt $n; $i++) { $x += $line }; $x }
        $h3 = & $runAllow @{ 'bin\sd-cli.exe' = (& $many 29) }
        $h4 = & $runAllow @{ 'bin\sd-cli.exe' = (& $many 30) }
        Check "vocabulary: 29 hits pass, a 30th is refused (the maximum)" ($h3.Ok -and -not $h4.Ok -and $h4.Log -match 'maximum')
        $h5 = & $runAllow @{ 'bin\sd-cli.exe' = ((& $many 2) + [Text.Encoding]::ASCII.GetBytes('Write a report for Robin about the run')) }
        Check "NEGATIVE: prose with the name in an sd binary is refused" ($h3.Ok -and -not $h5.Ok)
        $self0 = Get-Content -LiteralPath $PSCommandPath -Raw
        Check "the allowlist is declared as a literal list the drift test can read" ($self0 -match '(?m)^\$PRIVACY_ALLOW\s*=\s*@\(\s*\r?\n')
    } finally {
        Remove-Item $pkRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    # No personal default, and the packing path really calls the gate. The second
    # reads the script itself: the packing code sits below the selftest exit,
    # where no check can run it (the shape the comment on Get-DevOnlyFiles warns of).
    $ast  = [System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$null, [ref]$null)
    $bdp  = $ast.ParamBlock.Parameters | Where-Object { $_.Name.VariablePath.UserPath -eq 'BuildDir' }
    Check "-BuildDir has no path as its default"       ($bdp.DefaultValue.Extent.Text -eq '$env:CROW_BUILD_DIR')
    $threw = $false
    try { Resolve-BuildDir -Value '' | Out-Null } catch { $threw = $_.Exception.Message -like '*-BuildDir is required*CROW_BUILD_DIR*' }
    Check "NEGATIVE: no -BuildDir and no CROW_BUILD_DIR is refused, and says how" $threw
    Check "-BuildDir is returned when given"           ((Resolve-BuildDir -Value 'D:\x') -eq 'D:\x')
    $self = Get-Content -LiteralPath $PSCommandPath -Raw
    Check "the packing path calls Invoke-StageGate before the manifest" ($self -match '(?s)Invoke-StageGate -Stage \$stage -Patterns \$pp\.Patterns.*# 5 - manifest')
    Check "and copies cli and kits through Copy-ShippedTree" (([regex]::Matches($self, 'Copy-ShippedTree -Source \(Join-Path \$repo')).Count -eq 2)
    Check "the packing path resolves and gates with -NvidiaAtInstall (both calls)" (([regex]::Matches($self, 'Test-PackageComplete -Dumpbin \$dumpbin -Files \(Get-ChildItem \$binOut -File\)\.FullName -NvidiaAtInstall')).Count -eq 2)
    Check "step 1 leaves NVIDIA's libraries out of the build copy"             ($self -match 'if \(Test-NvidiaAtInstall \$f\.Name\)\s+\{ \$binLeft \+= \$f\.Name; continue \}')
    Check "and the gate refuses a stage that holds one"                          ($self -match '(?s)Get-NvidiaFiles -Paths @\(Get-ChildItem \$stage -Recurse.*?an NVIDIA library is in the package')

    $dumpbin = Find-Dumpbin
    Check "dumpbin located" ([bool]$dumpbin)

    # Against the real build tree: the package must be INCOMPLETE, because that is
    # exactly the finding this tool exists for. A green result here would mean the
    # check cannot see the problem it was built to catch.
    if ($BuildDir -and (Test-Path $BuildDir)) {
        $built  = (Get-ChildItem $BuildDir -File | Where-Object { $_.Extension -in '.dll', '.exe' }).FullName
        # With -SdBuildDir the image server is part of the set from the start, so
        # the closure below is the one the real package gets.
        $sdBins = @()
        if ($SdBuildDir) { $sdBins = Get-SdBinaries -Dir $SdBuildDir; $built = @($built) + $sdBins }
        $bare   = Test-PackageComplete -Dumpbin $dumpbin -Files $built
        Check "bin\Release alone is incomplete (the #57 finding)" ($bare.Count -gt 0)
        $names  = ($bare.Needs | Sort-Object -Unique)
        Check "cublas64_13.dll is among the missing"  ($names -contains 'cublas64_13.dll')
        Write-Host ("       missing: " + ($names -join ', '))

        # The positive control, and it has to be the real one: add exactly the files
        # the check just named as missing, and the set must come back closed. A
        # checker that only ever reports "incomplete" would pass every case above
        # while being useless for the job it exists to do.
        # Resolving has to iterate: cublas64_13.dll only reveals that it needs
        # cublasLt64_13.dll once it is itself in the set. A single pass would
        # produce a package that is one file short and looks finished.
        $extra  = @()
        $rounds = 0
        $set    = $built
        while ($true) {
            $gap = Test-PackageComplete -Dumpbin $dumpbin -Files $set
            if ($gap.Count -eq 0) { break }
            $rounds++
            if ($rounds -gt 8) { break }
            $added = $false
            foreach ($n in ($gap.Needs | Sort-Object -Unique)) {
                $src = Find-RuntimeLibrary -Name $n
                if ($src -and ($extra -notcontains $src)) { $extra += $src; $set = $built + $extra; $added = $true }
            }
            if (-not $added) { break }
        }

        $final = Test-PackageComplete -Dumpbin $dumpbin -Files ($built + $extra)
        Check "resolving needed more than one pass (transitive imports)" ($rounds -gt 1)
        Check "build tree plus resolved libraries is complete"            ($final.Count -eq 0)
        Write-Host ("       resolved in $rounds rounds, " + $extra.Count + " libraries added:")
        foreach ($e in $extra) { Write-Host ("         " + [IO.Path]::GetFileName($e)) }
        if ($final.Count -gt 0) {
            Write-Host ("       STILL MISSING: " + (($final.Needs | Sort-Object -Unique) -join ', ')) -ForegroundColor Red
        }
        if ($sdBins.Count -gt 0) {
            $sdNeeds = @()
            foreach ($b in $sdBins) { $sdNeeds += (Get-Imports -Dumpbin $dumpbin -Path $b) | ForEach-Object { $_.ToLowerInvariant() } }
            Check "sd-server.exe imports cublas64_13.dll, as llama-server does" ($sdNeeds -contains 'cublas64_13.dll')
            $extraNames = @($extra | ForEach-Object { [IO.Path]::GetFileName($_).ToLowerInvariant() })
            Check "NEGATIVE: no runtime library is added twice with the image server" (($extraNames | Sort-Object -Unique).Count -eq $extraNames.Count)
        } else {
            Write-Host "  skip image-server closure -- no -SdBuildDir" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  skip build-tree cases -- no -BuildDir/CROW_BUILD_DIR, or $BuildDir not present" -ForegroundColor Yellow
    }

    Write-Host ""
    $total = $script:selftestOk + $script:selftestRed
    if ($script:selftestRed -gt 0) {
        Write-Host "RESULT: $($script:selftestRed) of $total FAILED" -ForegroundColor Red
        return 1
    }
    Write-Host "RESULT: SELFTEST OK - $total checks" -ForegroundColor Green
    return 0
}

if ($Selftest) { exit (Invoke-Selftest) }

# ---------------------------------------------------------------------------
# 0 - the repository checkers, before one byte is staged
# ---------------------------------------------------------------------------
#
# #90's third done criterion is "shared behaviour lives in exactly one place, and
# there is a check that says so". A check that says so only when a human
# remembers to type it does not say so. This is where it gets said, because a
# release cannot be cut without coming through here.
#
# THE PRICE IS PAID ON PURPOSE, and it is not small: a red checker blocks a
# release, and manifests/shared-core.json is hand-written, so that file now
# stands between robin and a package. The alternative is a criterion that is met
# on paper.
$BuildDir = Resolve-BuildDir -Value $BuildDir

Write-Host "checking the repository before packing"
$redCheckers = Invoke-RepoCheckers
if ($redCheckers.Count -gt 0) {
    throw ("release checkers failed, nothing was staged: " + ($redCheckers -join ', ') +
           " -- fix the finding, or say in the issue why the package ships against it")
}
Write-Host "  checkers: OK"
Write-Host ""

# ---------------------------------------------------------------------------
# Packing
# ---------------------------------------------------------------------------

if (-not $Version) {
    $cliDir  = Join-Path $PSScriptRoot '..\cli'
    $Version = Get-VersionLiteral -CliDir $cliDir
    if (-not $Version) { throw "cannot read VERSION from $cliDir\crow_core.py -- pass -Version" }
}
if (-not $OutDir) { $OutDir = Join-Path $PSScriptRoot "..\dist" }

$repo  = Resolve-Path (Join-Path $PSScriptRoot '..')
$stage = Join-Path $OutDir "crow-$Version-win-x64"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
# Resolve after creating: the manifest strips this prefix off FullName, and an
# unresolved path carrying ".." is a different string from the one Get-ChildItem
# returns -- which is a crash after the copy, at the least useful moment.
$stage  = (Resolve-Path $stage).Path
$OutDir = (Resolve-Path $OutDir).Path

Write-Host "packing crow $Version"
Write-Host "  build : $BuildDir"
Write-Host "  stage : $stage"

if (-not (Test-Path $BuildDir)) { throw "build directory not found: $BuildDir" }
$dumpbin = Find-Dumpbin

# 1 - the built binaries
$binOut = Join-Path $stage 'bin'
New-Item -ItemType Directory -Force -Path $binOut | Out-Null
$built = @()
$binLeft = @()
foreach ($f in Get-ChildItem $BuildDir -File -Force) {
    if (Get-ExcludeRule -RelPath $f.Name) { $binLeft += $f.Name; continue }
    if (Test-NvidiaAtInstall $f.Name)     { $binLeft += $f.Name; continue }   # NVIDIA's: fetched at install time
    Copy-Item -LiteralPath $f.FullName -Destination $binOut
    $built += (Join-Path $binOut $f.Name)
}
Write-Host ("  copied $($built.Count) build files" + $(if ($binLeft.Count -gt 0) { ", left out $($binLeft.Count) ($($binLeft -join ', '))" } else { "" }))

# 1b - the image server (#314), two executables beside llama-server.exe. Step 2
#      resolves their DLLs with llama-server's: a name already staged is not
#      copied again. cublas64_13.dll/cublasLt64_13.dll are NVIDIA's and ship in
#      neither; CrowSetup downloads them at install time.
if ($SdBuildDir) {
    $sdBins = Get-SdBinaries -Dir $SdBuildDir
    $clash  = Get-NameClashes -Dest $binOut -Incoming $sdBins
    if ($clash.Count -gt 0) { throw ("-SdBuildDir would replace a different file of the same name: " + ($clash -join ', ')) }
    foreach ($b in $sdBins) {
        Copy-Item -LiteralPath $b -Destination $binOut
        $built += (Join-Path $binOut ([IO.Path]::GetFileName($b)))
    }
    Write-Host "  image server: sd-server.exe, sd-cli.exe from $SdBuildDir"
} else {
    Write-Host "  image server: none (no -SdBuildDir) -- generate_image/edit_image will answer 'the image server is not installed'" -ForegroundColor Yellow
}

# 2 - every runtime library they need, resolved transitively
$extra  = @()
$rounds = 0
while ($true) {
    $gap = Test-PackageComplete -Dumpbin $dumpbin -Files (Get-ChildItem $binOut -File).FullName -NvidiaAtInstall
    if ($gap.Count -eq 0) { break }
    $rounds++
    if ($rounds -gt 8) { throw "dependency resolution did not settle after 8 rounds" }
    $added = $false
    foreach ($n in ($gap.Needs | Sort-Object -Unique)) {
        $src = Find-RuntimeLibrary -Name $n
        if (-not $src) { throw "required library not found on this machine: $n (needed by $(($gap | Where-Object Needs -eq $n).RequiredBy -join ', '))" }
        $dest = Join-Path $binOut ([IO.Path]::GetFileName($src))
        if (-not (Test-Path $dest)) { Copy-Item -LiteralPath $src -Destination $dest; $extra += $dest; $added = $true }
    }
    if (-not $added) { throw "resolution stalled with $($gap.Count) imports unresolved" }
}
Write-Host ("  added $($extra.Count) runtime libraries in $rounds rounds")

# 3 - the client, and the terms it must ship under.
#     Copied file by file through Get-ExcludeRule, not recursively and cleaned up
#     after: a recursive copy shipped crow.cpython-313.pyc into the first package
#     built here, the unit suite (73,792 bytes nobody runs) into every later one,
#     and ten cli\runs\llama-server-*.log into 2.8.5. The rule list leaves out
#     __pycache__, *.pyc, test_*.py, runs\, *.log, .env*, secrets.json and the
#     session and state files, and Invoke-StageGate below checks the result.
$cliCopy = Copy-ShippedTree -Source (Join-Path $repo 'cli') -Dest (Join-Path $stage 'cli')
Write-Host ("  cli/: $($cliCopy.Copied) files copied, $($cliCopy.Left.Count) left out by the exclude rules")
$stray = Get-ChildItem (Join-Path $stage 'cli') -Recurse -File -Include '*.pyc', '*.pyo'
if ($stray) { throw ("compiled Python left in the package: " + ($stray.Name -join ', ')) }
# Looked at again rather than trusted. The unit suite is also the first file the
# removal path in install.ps1 has to deal with -- every install from 0.0.1 on has
# a copy sitting in cli/.
$devLeft = Get-DevOnlyFiles -Paths @(Get-ChildItem (Join-Path $stage 'cli') -Recurse -File | ForEach-Object { $_.FullName })
if ($devLeft.Count -gt 0) { throw ("test code left in the package: " + (($devLeft | Split-Path -Leaf) -join ', ')) }
foreach ($f in @('LICENSE', 'NOTICE', 'README.md')) {
    Copy-Item -LiteralPath (Join-Path $repo $f) -Destination $stage
}

# The chat template is part of the product since 0.1.0: the installer's printed
# server line points at it, and without the file that line fails on start. It
# ships byte-exact -- the golden-vector proof is a byte comparison, and the
# repo's .gitattributes carries -text for the same reason.
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'templates') | Out-Null
Copy-Item -LiteralPath (Join-Path $repo 'manifests\0731-chat-template.jinja') `
          -Destination (Join-Path $stage 'templates\0731-chat-template.jinja')
if ((Get-Item (Join-Path $stage 'templates\0731-chat-template.jinja')).Length -ne
    (Get-Item (Join-Path $repo 'manifests\0731-chat-template.jinja')).Length) {
    throw "template changed size on the way into the package -- a byte-checked file may not do that"
}

# THE OPERATING POINT SHIPS SINCE #112, AND THE DIRECTORY NAME IS LOAD-BEARING.
# cli/crow_core.py resolves it as `..\manifests\operating-point.json` from its
# own location, which is the same relative step in the repo and in an install --
# so there is no "am I installed?" branch anywhere, and exactly one path can be
# wrong. Renaming this directory the way the template was renamed to templates/
# would break the client silently: a missing manifest is not an error, it is the
# 0.5.1 behaviour, so the model's own sampling would just quietly stop arriving.
#
# WHY IT SHIPS AT ALL: per-model sampling has to come from data rather than from
# a second set of literals in the client, because tools/check_operating_point.py
# counts the places a default is written and allows exactly one. A table in the
# core spelling min_p twice is the drift this project keeps finding, so the
# numbers that differ per model live here.
# Read back as JSON rather than checked for existence: this file is now product,
# and a truncated copy would install cleanly and answer every sampling question
# with the fallback -- which looks exactly like a correct old installation.
# manifests\stack.json rides along (#196 P1, the boot menu); Copy-ManifestFiles
# stages and reads back both.
Copy-ManifestFiles -Repo $repo -Stage $stage | Out-Null
# tools\te_rename.py (#196 phase 2): CrowSetup runs it from <install>\tools\ to
# build the Image Stack's text_encoder_sdcli\. The only file of tools\ that ships.
Copy-ToolFiles -Repo $repo -Stage $stage | Out-Null

# The OFL is not a formality: without it, redistributing the typeface is a licence
# violation. Refuse rather than ship a package that breaks it.
if (-not (Test-Path (Join-Path $stage 'cli\fonts\OFL.txt'))) {
    throw "cli/fonts/OFL.txt missing from the package -- the typeface may not be redistributed without it"
}

# THE VOXEL KIT (#298): kits\pathtracer ships in every package, beside cli\,
# because crow_core resolves it as <install>\kits\pathtracer -- the same step as
# the manifests above. install.ps1 -PathTracer only switches its skill on. The
# three MIT notices travel with the bundle or the bundle does not travel.
# check_diorama.py (#299) runs from the kit folder and leaves its __pycache__
# there; the same exclude rules as cli\ keep it out. tools/repack-release.py
# ships kits\ the same way (it did not until #196 C2).
$kitCopy = Copy-ShippedTree -Source (Join-Path $repo 'kits') -Dest (Join-Path $stage 'kits')
Write-Host ("  kits/: $($kitCopy.Copied) files copied, $($kitCopy.Left.Count) left out by the exclude rules")
$stray = Get-ChildItem (Join-Path $stage 'kits') -Recurse -File -Include '*.pyc', '*.pyo'
if ($stray) { throw ("compiled Python left in the kits: " + ($stray.Name -join ', ')) }
foreach ($f in $KIT_REQUIRED) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage "kits\pathtracer\$f"))) {
        throw "kits/pathtracer/$f missing from the package -- the kit or its licence notice would ship incomplete"
    }
}
$kitWant = (Get-Content -LiteralPath (Join-Path $stage 'kits\pathtracer\kit.json') -Raw | ConvertFrom-Json).bundle.sha256
$kitHave = (Get-FileHash -LiteralPath (Join-Path $stage 'kits\pathtracer\crow-pathtracer.js') -Algorithm SHA256).Hash
if ($kitHave -ne $kitWant.ToUpperInvariant()) { throw "kits/pathtracer/crow-pathtracer.js does not match kit.json" }

# 4 - the gate: nothing in the package may need something outside it
$final = Test-PackageComplete -Dumpbin $dumpbin -Files (Get-ChildItem $binOut -File).FullName -NvidiaAtInstall
if ($final.Count -gt 0) {
    throw ("package is incomplete: " + (($final.Needs | Sort-Object -Unique) -join ', '))
}
Write-Host ("  completeness: OK (imports of " + ($NVIDIA_AT_INSTALL -join ', ') + " are provided at install time from NVIDIA)")
# No NVIDIA file may be in the package, whichever way it got there.
$nvStaged = Get-NvidiaFiles -Paths @(Get-ChildItem $stage -Recurse -File | ForEach-Object { $_.FullName })
if ($nvStaged.Count -gt 0) {
    throw ("an NVIDIA library is in the package, which must carry none: " + (($nvStaged | Split-Path -Leaf) -join ', '))
}

# 4b - the shipped set and the privacy gate (#196 C2), on the finished stage and
#      BEFORE the manifest or the zip exist. A refusal removes the stage so no
#      directory holding private data is left in dist\ to be zipped by hand.
$pp = Get-PrivatePatterns -Extra $PrivatePattern
if (-not (Invoke-StageGate -Stage $stage -Patterns $pp.Patterns -Notes $pp.Notes)) {
    Remove-Item $stage -Recurse -Force
    Write-Host "  stage removed; no manifest, no zip" -ForegroundColor Red
    exit 1
}

# 5 - manifest, then archive. The manifest is written before the zip so a crash
#     leaves a staging folder without one, rather than an archive nobody can verify.
$manifest = Get-ChildItem $stage -Recurse -File | ForEach-Object {
    [pscustomobject]@{
        path   = $_.FullName.Substring($stage.Length + 1)
        bytes  = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
}
$manifest | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $stage 'MANIFEST.json') -Encoding utf8

$zip = Join-Path $OutDir "crow-$Version-win-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal

$total = ($manifest | Measure-Object bytes -Sum).Sum
Write-Host ""
# {0} IS THE MANIFEST COUNT, NOT THE DIRECTORY COUNT, and the wording says so
# because the two differ by exactly one and that one is not an error: MANIFEST.json
# cannot list and hash itself, so a package of N manifest entries always holds N+1
# files. Read as "N files staged" the line disagrees with `dir` every single time,
# and someone eventually goes looking for the missing file.
Write-Host ("RESULT: {0} files in the manifest (+ MANIFEST.json = {1} in the package), {2:N1} MB staged, {3:N1} MB zipped" -f $manifest.Count, ($manifest.Count + 1), ($total/1MB), ((Get-Item $zip).Length/1MB)) -ForegroundColor Green
Write-Host "  $zip"
exit 0
