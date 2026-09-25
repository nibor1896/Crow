<#
.SYNOPSIS
Installs Crow: one command, five steps, no elevation.

.DESCRIPTION
    irm https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1 | iex

Everything lands under %LOCALAPPDATA%\Crow. Nothing is written to Program Files,
the registry or the PATH by this script.

The model is NOT downloaded here. It is 95.9 GiB, it is not ours to redistribute,
and an installer that spends hours on somebody else's file before the user has
seen anything work is the wrong shape. The last step prints the one command that
fetches it.

Order matters: every check that can reject this machine runs BEFORE the 506 MB
download starts. Finding out afterwards that the card is too small is the most
expensive possible failure.

That order now covers the two checks that only WARN as well. Python and Tk cannot
refuse a machine -- a missing interpreter is a five-minute fix and the rest of the
install is still worth having -- but until this version they were asked in the
LAST step, after the 506 MB had already been fetched. "Your client will not start"
is the same sentence before the download and after it, and only one of the two
costs the user half a gigabyte to hear.

Crow ships TWO clients and this script installs both, with no opt-in switch: the
package contains cli\crow.py and cli\crow_gui.py either way, so a switch would
only decide whether this script mentions the second one. The last step prints both
start lines, the terminal client first. Neither is started here.

.PARAMETER Selftest
Run the checks against synthetic inputs, including ones that must fail, and exit.
Downloads nothing.

.PARAMETER Tailscale
Print what is still missing for the phone's HTTPS address over Tailscale
(install with winget, log in, Enable HTTPS in the admin console, the one-time
`tailscale serve` line for an elevated shell, the phone app) and exit. Reads
`tailscale status --json` and `tailscale serve status --json` only; installs,
downloads and elevates nothing. From the one-liner:
    &([scriptblock]::Create((irm https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1))) -Tailscale

.PARAMETER PathTracer
Also switch on the voxel-diorama skill (#298): the model builds path-traced
voxel scenes as one offline page with the kit in kits\pathtracer (three.js +
three-gpu-pathtracer, shipped with every package, ~1 MB). The flag verifies the
kit against its kit.json, switches the skill on through the client's own code
(the same switch as the Skills page in the settings) and says whether an
esbuild is there for build_bundle. On an install that is already current it
does only that and changes nothing else. Off, a skill costs the prompt nothing.

.PARAMETER NoPause
Do not wait for ENTER at the end. The wait exists so the last screen -- the model
to fetch and the two commands to run -- is still there to read; a script driving
this installation does not want it.

.PARAMETER SourceUrl
Where to take the package from, instead of the GitHub release. Accepts an
http(s) URL or a path to a local .zip.

This exists because an installer whose only source is a release can never be
tried before that release is published -- the first person to run it would be
the first person to test it. With a local path the whole thing runs end to end
against dist\crow-<version>-win-x64.zip, and only the download step is skipped.
A local package is never deleted afterwards; a downloaded one is.
#>
[CmdletBinding()]
param(
    [string] $Version   = "2.7.0",
    [string] $InstallTo = "$env:LOCALAPPDATA\Crow",
    [string] $SourceUrl = "",
    [switch] $Force,
    [switch] $NoPause,
    [switch] $Selftest,
    [switch] $Tailscale,
    [switch] $PathTracer
)

$ErrorActionPreference = "Stop"
$TOTAL_STEPS = 5

# Where this script lives when it is piped into iex. Printed back at the user in
# the one place where the run needs to be repeated with a switch, because
# `irm <url> | iex` cannot take parameters and telling somebody to "pass -Force"
# without the invocation that accepts it is advice they cannot act on.
$INSTALL_URL = "https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1"

# The target profile, decided on issue #25: 32 GB VRAM at a 200k context window. Below
# 16 GB VRAM the operating point was never measured, so the script refuses rather than
# pretending it knows what happens there.
# $RAM_MIN_GB is a warning threshold, not a measurement. Nothing below the 63.4 GB of the
# machine every figure was taken on has been run. 32 is what the README names as the
# configuration that runs without the host tier, at 1.63x less throughput -- the 16 that
# stood here came from #25's assumption about what a 16 GB-VRAM machine ships with.
$VRAM_SUPPORTED_MB = 16000
$VRAM_TARGET_MB    = 32000
$RAM_MIN_GB        = 32

# The host-RAM expert tier. 32 GiB is the ONLY size measured (2026-08-09, on a 63.4 GB machine:
# 1.40-1.47x throughput over three paired runs), and page-locked memory is taken away from the
# rest of the machine for the life of the process. So the installer offers it at exactly the
# ratio it was measured at and stays silent below that, rather than scaling a number nobody has
# run. A user with 48 GB can pass --moe-stream-l2 themselves; that is their measurement to make.
$L2_GIB            = 32
# 60 and not 64: Windows reports 63.4 GB on the 64 GB machine this was measured on, because
# firmware and hardware reservations come off the top before the OS ever sees the memory. A
# threshold at the nominal size excludes exactly the configuration that produced the figure.
$L2_RAM_REQUIRED_GB = 60
$DISK_INSTALL_GB   = 2      # the package, unpacked
# 85 and not 84: the 0731 UD-IQ2_XXS GGUF is 84.62 GiB across three shards (90,860,736,928 B,
# read from the tensor tables of all three, 2026-08-12). The line this feeds and the download hint
# below it disagreed by a gigabyte on the previous rung until that was fixed; keep them in step.
$DISK_MODEL_GB     = 85     # what the model will need later, reported not enforced

# The dictation model for the window's microphone. 486.2 MB across four files,
# measured against the HuggingFace API on 2026-08-21. `small` and not a bigger
# rung because the ceiling was "no gigabyte download", and the next one up
# (medium) is 1531 MB, turbo 1622 MB, large-v3 3087 MB. Multilingual on
# purpose: most users speak English into this box and its author speaks German,
# so a `distil-*` or a German-tuned checkpoint would have to be picked against
# one of them.
#
# NOT ADDED TO THE DISK GUARD. That guard already reserves $DISK_MODEL_GB for
# the LLM, and 0.47 GB inside 85 is below the resolution of the number it is
# compared against. It is ANNOUNCED in the preflight instead, which is what the
# user actually needs to know before the package download starts.
$WHISPER_REPO      = "Systran/faster-whisper-small"
$WHISPER_DIRNAME   = "whisper-small"
$WHISPER_MB        = 486

# The Tk floor the window is written against. DECIDED, not left open: 8.6. The
# reference value on the machine every figure on this page was taken on is 8.6.15
# under Python 3.13.3 [measured 2026-08-12]. tools/check_gui_prereqs.py carries
# the same number as MIN_TK and holds it against the machine the window is WRITTEN
# on; this one holds it against the machine it is INSTALLED on.
#
# That those are two copies of one number in two languages is said out loud rather
# than hidden: neither file can read the other at the moment its check runs -- this
# script is piped into iex with no repository behind it -- and the only alternative
# on offer was a preflight that prints a version without a threshold, which is a
# check with nothing to fail against.
$TK_MIN            = "8.6"

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

$script:StepNo = 0

function Write-Step {
    param([string] $Title)
    $script:StepNo++
    Write-Host ""
    Write-Host ("[{0}/{1}] {2}" -f $script:StepNo, $TOTAL_STEPS, $Title) -ForegroundColor Cyan
}

function Write-Item {
    param([string] $Text, [string] $Detail = "", [string] $Status = "")
    $line = "      $Text"
    if ($Detail) { $line += "  $Detail" }
    switch ($Status) {
        "ok"   { Write-Host $line -ForegroundColor Green }
        "warn" { Write-Host $line -ForegroundColor Yellow }
        "fail" { Write-Host $line -ForegroundColor Red }
        default { Write-Host $line -ForegroundColor DarkGray }
    }
}

# Invariant culture on purpose: PowerShell's -f operator formats with the system
# culture, so the same number prints as "482.9 MB" here and "482,9 MB" on a German
# machine. An installer's output should not depend on where it is run, and a test
# asserting one of the two forms would be red on half the world's desktops.
function Format-Num {
    param([double] $Value, [int] $Decimals = 1)
    return [string]::Format([Globalization.CultureInfo]::InvariantCulture, "{0:N$Decimals}", $Value)
}

function Format-Size {
    param([double] $Bytes)
    $inv = [Globalization.CultureInfo]::InvariantCulture
    if ($Bytes -ge 1GB) { return [string]::Format($inv, "{0:N2} GB", ($Bytes / 1GB)) }
    if ($Bytes -ge 1MB) { return [string]::Format($inv, "{0:N1} MB", ($Bytes / 1MB)) }
    if ($Bytes -ge 1KB) { return [string]::Format($inv, "{0:N0} KB", ($Bytes / 1KB)) }
    return "$Bytes B"
}

# ---------------------------------------------------------------------------
# Preflight -- everything that can say no, before anything is downloaded
# ---------------------------------------------------------------------------

<#
    How many GiB of host-RAM expert tier this machine gets, or 0 for none.

    Deliberately NOT a formula. Half the RAM, or RAM minus a constant, would produce a number for
    every machine and a measurement for none - and this one is page-locked, so a wrong guess does
    not degrade gracefully, it takes memory away from everything else until the process exits.
    Only the ratio that was actually run is offered.
#>
function Get-L2Gib {
    param([double] $RamGb)
    if ($RamGb -ge $L2_RAM_REQUIRED_GB) { return $L2_GIB }
    return 0
}

<#
    Is this Tk at or above the floor, comparing only as many components as the
    floor names?

    "8.6.15" against a floor of "8.6" compares (8, 6) with (8, 6) and holds; a
    floor of "8.6.16" would compare all three and would not. Anything that is not
    a dotted number is $false rather than an error -- an unreadable version is not
    a version that passed, and a preflight that threw here would take a machine
    down over a string.

    [version] would have been one line, and it is the wrong one: it accepts at most
    four components and refuses anything with a letter in it, so a Tk that reports
    "8.6.15" is fine and one that reports "8.7a2" is an exception rather than an
    answer. This is the same comparison tools/check_gui_prereqs.py makes in
    version_at_least, and the two are held to the same reference value.
#>
function Test-TkFloor {
    param(
        [string] $Patchlevel,
        [string] $Floor = $TK_MIN
    )

    function Split-Parts {
        param([string] $Text)
        if (-not $Text) { return $null }
        $out = @()
        foreach ($piece in ($Text -split '\.')) {
            # Leading digits only, so "8.7a2" reads as (8, 7) rather than as
            # nothing at all. A piece with no digit at its front is not a version
            # component and ends the whole reading.
            $m = [regex]::Match($piece, '^\d+')
            if (-not $m.Success) { return $null }
            $out += [int] $m.Value
        }
        if ($out.Count -eq 0) { return $null }
        return ,$out
    }

    $got  = Split-Parts $Patchlevel
    $want = Split-Parts $Floor
    if ($null -eq $got -or $null -eq $want) { return $false }
    for ($i = 0; $i -lt $want.Count; $i++) {
        # A version SHORTER than the floor loses: "8" against "8.6" says nothing
        # about the minor, and silence is not agreement.
        if ($i -ge $got.Count) { return $false }
        if ($got[$i] -gt $want[$i]) { return $true }
        if ($got[$i] -lt $want[$i]) { return $false }
    }
    return $true
}

<#
    Returns a verdict object rather than writing output, so the selftest can feed
    it synthetic values. A check that can only be exercised by owning the hardware
    it checks for is a check nobody ever tests.

    PythonPath and WebView2Version are empty strings when the probe found nothing.
    They live HERE, in the preflight, and not in the last step where the Python
    line used to sit: this function is the only thing in this script that runs
    before the download, and a warning is worth what it costs the person reading
    it. Neither can set Problems -- the install is still worth having on a machine
    with no interpreter, and the README says so in the same words.
#>
function Test-Preflight {
    param(
        [int]    $VramMb,
        [double] $RamGb,
        [double] $FreeDiskGb,
        [bool]   $HasNvidiaSmi,
        [bool]   $Is64Bit,
        [version] $PsVersion,
        [string] $PythonPath = "",
        [string] $WebView2Version = "",
        [string] $NodePath = ""
    )

    $problems = @()
    $warnings = @()

    if (-not $Is64Bit)                     { $problems += "64-bit Windows is required" }
    if ($PsVersion.Major -lt 5)            { $problems += "PowerShell 5.1 or newer is required (found $PsVersion)" }
    if (-not $HasNvidiaSmi)                { $problems += "no NVIDIA driver found -- nvidia-smi is not on the PATH. Crow runs its experts on CUDA" }
    elseif ($VramMb -lt $VRAM_SUPPORTED_MB) {
        $problems += ("{0} MB of VRAM, below the {1} MB minimum. Operation below that was never measured and is unsupported" -f $VramMb, $VRAM_SUPPORTED_MB)
    }
    elseif ($VramMb -lt $VRAM_TARGET_MB) {
        $warnings += ("{0} MB of VRAM. The measured target profile is {1} MB; expect fewer cache slots and lower throughput" -f $VramMb, $VRAM_TARGET_MB)
    }

    if ($RamGb -gt 0 -and $RamGb -lt $RAM_MIN_GB) {
        $warnings += ((Format-Num $RamGb 0) + " GB of system RAM, below the $RAM_MIN_GB GB the README names. Every figure was taken on 63.4 GB; below that nothing has been run")
    }
    if ($FreeDiskGb -gt 0 -and $FreeDiskGb -lt $DISK_INSTALL_GB) {
        $problems += ((Format-Num $FreeDiskGb) + " GB free on the install drive, $DISK_INSTALL_GB GB needed for the package")
    }
    elseif ($FreeDiskGb -gt 0 -and $FreeDiskGb -lt ($DISK_INSTALL_GB + $DISK_MODEL_GB)) {
        $warnings += ((Format-Num $FreeDiskGb 0) + " GB free. The package fits, but the model needs about $DISK_MODEL_GB GB more")
    }

    # ONE CAUSE, ONE LINE, which is why this is a chain and not two independent
    # ifs: without an interpreter there is nothing to ask about the window, and
    # an installer that prints "no python" and "no runtime" for one missing
    # download has told the user about two problems they do not have.
    #
    # THE WINDOW'S PROMISE HAS TWO HALVES AND ONLY ONE IS ASKED HERE. The
    # WebView2 runtime is readable from the registry before anything is
    # downloaded; whether `pip install pywebview` may write into the Python it
    # found is not knowable until it is tried, and that happens after the
    # download. Claiming both here would put a green line in front of a
    # condition that fails later -- the same shape as the Python row before
    # 0.2.0, which charged half a gigabyte for its warning.
    if (-not $PythonPath) {
        $warnings += "python is not on the PATH. BOTH clients need it -- the terminal one and the window. Python 3.8 or newer; the terminal client needs nothing beyond the standard library"
    }
    elseif (-not $WebView2Version) {
        $warnings += "no WebView2 runtime found. cli\crow.py runs in a terminal without it; cli\crow_gui.py is the window and renders in it. It ships with Windows 11 and with Edge"
    }

    # NODE IS THE THIRD PREREQUISITE AND THE ONLY WHOLLY OPTIONAL ONE, which is
    # why it warns here and blocks nowhere. Nothing in Crow needs it to run --
    # MCP servers do (nearly every published one starts with npx), and two
    # built-in tools get better with it: write_file/append_file run
    # `node --check` over JS and inline HTML scripts and put the first syntax
    # error into the result (#251; without node the check is skipped and the
    # result says nothing about syntax), and build_bundle finds esbuild in the
    # npx cache or a project's node_modules (#212). Decided
    # 2026-08-22: a preflight line, not a requirement. Refusing a machine over a
    # feature it may never configure charges everybody for the few, and the two
    # rows above already set the precedent for a prerequisite that costs one
    # client and not the install.
    #
    # NOT CHAINED to the pair above, because it is not the same cause: a machine
    # can have Python and no Node, and a user who reads "python missing" and
    # nothing else would find out about Node from a failed tool call instead.
    if (-not $NodePath) {
        $warnings += "node is not on the PATH. MCP servers started with npx or node need it; write_file/append_file skip their JS syntax check (#251) and build_bundle finds no esbuild from npx without it. The clients and the model run without it"
    }

    return [pscustomobject]@{
        Ok       = ($problems.Count -eq 0)
        Problems = $problems
        Warnings = $warnings
    }
}

function Get-MachineFacts {
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    $vram = 0
    $gpu  = "none"
    if ($smi) {
        # Collect first, take the first line second. `| Select-Object -First 1`
        # directly on a native command ends the pipeline early, PowerShell kills
        # the process, and $LASTEXITCODE lands on -1 -- measured 2026-08-08.
        # The script then exited 255 after a completely successful install,
        # which any caller reads as a failure.
        $lines = @(& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null)
        $q = if ($lines.Count) { $lines[0] } else { $null }
        if ($q) {
            $parts = $q -split ',\s*'
            $gpu   = $parts[0]
            $vram  = [int]$parts[1]
        }
    }
    $ramGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    $drive = (Split-Path $InstallTo -Qualifier)
    $free  = (Get-PSDrive ($drive -replace ':','') -ErrorAction SilentlyContinue).Free
    $freeGb = if ($free) { [math]::Round($free / 1GB, 1) } else { 0 }

    # The two client prerequisites, asked here so the preflight can report them
    # before anything is downloaded rather than after.
    #
    # THE RUNTIME IS READ OUT OF THE REGISTRY, and all three views are asked.
    # Measured 2026-08-13 on the development machine: the version sits under
    # HKLM\SOFTWARE\WOW6432Node -- the 32-bit view -- and BOTH the 64-bit view
    # and HKCU come back empty. A probe that asks only one of the three reports
    # "no runtime" on a machine that has one, and it reports it in the safe
    # direction, which is the direction nobody notices.
    #
    # No version floor. Crow has no measured one: the window renders in whatever
    # WebView2 the machine has, and the only question the preflight can answer
    # honestly before the download is whether there is one at all.
    $py     = Get-Command python -ErrorAction SilentlyContinue
    $pyPath = if ($py) { $py.Source } else { "" }
    # `node`, NOT `npx`, and the difference matters on this platform: npx is
    # npx.CMD, Get-Command reads PATHEXT and finds it, but CreateProcess does
    # not -- which is why cli/crow_core.py resolves the launcher itself before
    # starting one. What the preflight can honestly answer is whether a Node is
    # installed at all, and npm ships with it.
    $node     = Get-Command node -ErrorAction SilentlyContinue
    $nodePath = if ($node) { $node.Source } else { "" }
    $wv     = ""
    $guid   = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    foreach ($key in @(
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$guid",
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid",
        "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid")) {
        try {
            $pv = (Get-ItemProperty -LiteralPath $key -Name pv -ErrorAction Stop).pv
            if ($pv) { $wv = [string]$pv; break }
        } catch { }
    }

    return [pscustomobject]@{
        Gpu             = $gpu
        VramMb          = $vram
        RamGb           = $ramGb
        FreeDiskGb      = $freeGb
        HasNvidiaSmi    = [bool]$smi
        Is64Bit         = [Environment]::Is64BitOperatingSystem
        PsVersion       = $PSVersionTable.PSVersion
        PythonPath      = $pyPath
        WebView2Version = $wv
        NodePath        = $nodePath
    }
}

# ---------------------------------------------------------------------------
# Leaving
# ---------------------------------------------------------------------------

function Exit-Run {
    <#
    End the run with a status, without taking the user's shell down with it.

    `exit` inside a script FILE leaves the script. Inside a string executed by
    `iex` -- which is the documented way to install this, `irm ... | iex` -- it
    leaves the HOST SHELL. Measured 2026-08-08 on the first public install: the
    window closed the instant the installer finished, before anyone could read
    the server command it had just printed. The install had worked; there was
    simply no way to tell.

    So: exit only when there is a file to exit from. Otherwise set the status
    and let the caller `return`. $PSCommandPath is the file being run and is
    empty for a text run through iex, which is exactly the distinction needed.
    #>
    param([int] $Code = 0)

    if (Test-CanExitProcess $PSCommandPath) { exit $Code }
    $global:LASTEXITCODE = $Code
}

function Compare-Manifest {
    <#
    Hold what was installed against what the package says it should be.

    Takes entries that already carry their computed hash, so the decision is a
    pure function the selftest can drive both ways -- including the case that
    must fail. Reading files is the caller's job.

    Each entry: Path, Expected, Actual. Actual $null means the file is not there.
    #>
    param([object[]] $Entries)

    $missing    = @()
    $mismatched = @()
    foreach ($e in $Entries) {
        if ($null -eq $e.Actual)                          { $missing    += $e.Path; continue }
        if ($e.Actual.ToUpperInvariant() -ne $e.Expected.ToUpperInvariant()) { $mismatched += $e.Path }
    }
    return [pscustomobject]@{
        Ok         = (($missing.Count + $mismatched.Count) -eq 0)
        Missing    = $missing
        Mismatched = $mismatched
        Checked    = $Entries.Count
    }
}

function Find-DroppedFiles {
    <#
    Which files did the PREVIOUS package install that this one no longer ships?

    The update path knew "unchanged", "changed" and "new" and had no case for
    "removed", so a file dropped from a later package stayed on a machine
    forever. The verification above cannot see it: it walks the manifest and asks
    the disk, never the other way round.

    THE DIRECTION OF THIS QUESTION IS THE WHOLE DESIGN, and the first version got
    it backwards. It asked "what is on disk that the new manifest does not name?"
    and protected a hand-written list of exceptions -- session/, MANIFEST.json,
    *.old. Measured 2026-08-10 on a real install: that deleted
    %LOCALAPPDATA%\Crow\session-backup\, three files and 473 MB, made by the user
    minutes earlier on our own advice. It did not match `session/*`, so it was
    treated as rubbish. Every exception list has this failure in it, because it
    has to enumerate what a user might put in a directory, and nobody can.

    Asked in this direction the answer is exact and needs no exceptions: a file
    is removed only if a Crow package put it there and the new one does not. User
    data was never in a manifest, so it can never be selected. MANIFEST.json is
    not listed in itself, and *.old files are created by the rename step -- both
    fall out for free rather than by being remembered.

    Pure, like Compare-Manifest: two lists in, a verdict out. Whether the file is
    still on disk is the caller's question.

    Comparison is case-insensitive and separator-agnostic: NTFS does not care
    about case, and the manifest is written by one tool and read back by another.
    #>
    param(
        [string[]] $PreviousPaths,
        [string[]] $CurrentPaths
    )

    $current = @{}
    foreach ($p in $CurrentPaths) {
        if ($null -ne $p) { $current[($p -replace '\\', '/').ToLowerInvariant()] = $true }
    }

    $dropped = @()
    $seen    = @{}
    foreach ($raw in $PreviousPaths) {
        if ($null -eq $raw) { continue }
        $rel = $raw -replace '\\', '/'
        $key = $rel.ToLowerInvariant()
        if ($current.ContainsKey($key) -or $seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $dropped += $rel
    }

    return [pscustomobject]@{
        # @() on purpose: PowerShell hands back a bare String when a list holds
        # exactly one item, and one dropped file is the ordinary case. A caller
        # indexing [0] would then get a single character -- measured the same day
        # in pack-release.ps1, where the comma operator fixes the same thing.
        Dropped = @($dropped)
        # The denominator. "0 removed" out of nothing examined reads exactly like
        # "0 removed" out of a clean update, and one of those is a broken run.
        Checked = @($PreviousPaths).Count
    }
}

function Test-CanExitProcess {
    <#
    The decision Exit-Run rests on, split out so the selftest can drive both
    answers. Testing it through Exit-Run is impossible by construction: the
    branch under test ends the process.
    #>
    param([string] $CommandPath)
    return [bool]$CommandPath
}

# ---------------------------------------------------------------------------
# Where the package comes from
# ---------------------------------------------------------------------------

function Resolve-PackageSource {
    <#
    Returns @{ Uri = <url or full path>; IsLocal = <bool> }.

    Kept apart from the download so it can be exercised by the selftest without
    a network: everything that decides WHERE the package comes from is here, and
    everything that moves bytes is in Get-FileWithProgress.
    #>
    param([string] $SourceUrl, [string] $Asset, [string] $Version)

    if (-not $SourceUrl) {
        return @{ Uri = "https://github.com/nibor1896/Crow/releases/download/v$Version/$Asset"; IsLocal = $false }
    }
    if ($SourceUrl -match '^https?://') {
        return @{ Uri = $SourceUrl; IsLocal = $false }
    }

    $path = $SourceUrl
    if ($path -match '^file:///') { $path = ([Uri] $SourceUrl).LocalPath }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        # Named, not silently downloaded from the release instead: a typo in a
        # local path that quietly falls back would install a different package
        # than the one being tested.
        throw "no package at $path -- -SourceUrl wants an existing .zip or an http(s) URL"
    }
    return @{ Uri = (Resolve-Path -LiteralPath $path).Path; IsLocal = $true }
}

# ---------------------------------------------------------------------------
# Updating an installation that is already there
# ---------------------------------------------------------------------------

function Get-InstalledVersion {
    <#
    The version of the installation sitting in $Dir, or $null.

    Read out of the shipped cli\crow.py with the same pattern pack-release.ps1
    uses to stamp the package, so the two can never disagree about where the
    number lives. MANIFEST.json carries hashes, not a version.

    $null means "there is something here but it does not identify itself" --
    which is NOT the same as "nothing is installed", and the caller has to keep
    those apart before it overwrites a stranger's directory.
    #>
    param([string] $Dir)

    $cli = Join-Path $Dir "cli\crow.py"
    if (-not (Test-Path -LiteralPath $cli)) { return $null }
    $m = Select-String -LiteralPath $cli -Pattern '^VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
    if (-not $m) { return $null }
    return $m.Matches[0].Groups[1].Value
}

function Resolve-InstallAction {
    <#
    Returns @{ Action = 'install'|'update'|'uptodate'|'downgrade'|'unknown'; Message = <string> }.

    A pure function on purpose, like Resolve-PackageSource: the selftest drives
    every branch, including the ones that must refuse, without a filesystem and
    without a network.

    WHY THIS EXISTS. Until 2026-08-08 the installer refused any non-empty target
    with "pass -Force to overwrite" and exit 1. The documented one-liner is
    `irm ... | iex`, and a piped script cannot be given parameters at all -- so
    the advice it printed could not be followed by the person reading it. There
    was no way to move from one version to the next short of deleting the
    directory by hand. An installed base that cannot be updated is worse than
    one that was never installed.

    'unknown' is deliberately NOT treated as "install anyway": a directory whose
    contents we cannot identify may be somebody's own files, and overwriting it
    on a guess is not ours to do.
    #>
    param([string] $Installed, [string] $Target, [bool] $Force)

    if (-not $Installed) {
        if ($Force) { return @{ Action = 'install';  Message = "overwriting an unidentified install because -Force was passed" } }
        return @{ Action = 'unknown'; Message = "something is already in the target and does not identify itself -- pass -Force to overwrite it" }
    }

    $a = $null; $b = $null
    if (-not ([version]::TryParse($Installed, [ref] $a)) -or -not ([version]::TryParse($Target, [ref] $b))) {
        if ($Force) { return @{ Action = 'install'; Message = "version strings not comparable ($Installed -> $Target), proceeding because -Force was passed" } }
        return @{ Action = 'unknown'; Message = "cannot compare versions ($Installed -> $Target) -- pass -Force to install anyway" }
    }

    if ($b -gt $a) { return @{ Action = 'update';    Message = "$Installed -> $Target" } }
    if ($b -eq $a) {
        if ($Force) { return @{ Action = 'install';  Message = "reinstalling $Target because -Force was passed" } }
        return @{ Action = 'uptodate'; Message = "$Target is already installed -- nothing to do" }
    }
    if ($Force) { return @{ Action = 'install';      Message = "downgrading $Installed -> $Target because -Force was passed" } }
    return @{ Action = 'downgrade'; Message = "a newer version is installed ($Installed, this installs $Target) -- pass -Force to go back" }
}

function Resolve-LatestVersion {
    <#
    The newest published release tag, or $Fallback when the API cannot be reached.

    The one-liner fetches install.ps1 from main, so whatever number is hard-coded
    here is only as fresh as the last push to that file. Asking the release API
    makes the SAME one-liner install the newest version without anyone editing a
    default -- and the hard-coded value stays as the offline answer rather than
    the primary one.
    #>
    param([string] $Fallback)

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/nibor1896/Crow/releases/latest" `
                                 -Headers @{ "User-Agent" = "crow-installer" } -TimeoutSec 10
        $tag = "$($rel.tag_name)".TrimStart("v")
        if ($tag) { return $tag }
    } catch { }
    return $Fallback
}

# ---------------------------------------------------------------------------
# Download with a progress line that says what is happening
# ---------------------------------------------------------------------------

function Get-FileWithProgress {
    <#
    Downloads $Uri to $OutFile, and RETRIES, because a single attempt is not enough.

    Measured 2026-08-12 on this machine: GitHub's release-asset host answered a HEAD
    with 200 and Content-Length 531,018,248, and the very next GET died with an empty
    reply. A curl with --retry pulled the same range at 9.5 MB/s on its second try.
    Two installs in a row failed here with "Fehler beim Senden der Anforderung" thrown
    out of GetAsync -- after the preflight had already told the user everything was
    fine, which is the worst place to give up.

    So the whole attempt, connect and body, sits in a retry loop. A partial file is
    deleted before the next try rather than resumed: Range support on that host is not
    something this installer has measured, and a silently half-written archive would
    fail the size and hash check two steps later with a misleading message.
    #>
    param([string] $Uri, [string] $OutFile, [string] $Label,
          [int] $Attempts = 8, [int] $DelaySec = 1)

    # Windows PowerShell 5.1 does not load System.Net.Http by default, and the
    # failure is a TypeNotFound at the moment the download starts -- i.e. after
    # the preflight has already told the user everything is fine.
    Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    for ($try = 1; $try -le $Attempts; $try++) {
        try {
            return Get-FileOnce -Uri $Uri -OutFile $OutFile -Label $Label
        } catch {
            if (Test-Path $OutFile) { Remove-Item $OutFile -Force -ErrorAction SilentlyContinue }
            if ($try -ge $Attempts) {
                Write-Host ""
                throw ("download failed after {0} attempts: {1}" -f $Attempts, $_.Exception.Message)
            }
            # ONE LINE, REWRITTEN, NOT ONE PER ATTEMPT. Measured 2026-08-21 on the
            # first live install: huggingface.co refused the FIRST attempt on all
            # four model files and four in a row on one of them, so a four-file
            # download printed eleven failure lines around four successes. The
            # failures are real and worth seeing; they are not worth a line each.
            #
            # THE EXCEPTION TEXT IS DROPPED HERE AND KEPT AT THE THROW. It is long
            # enough to wrap the console, and a wrapped line cannot be overwritten
            # by the carriage return that makes this one line instead of ten.
            #
            # BACKING OFF FROM ONE SECOND, NOT THREE: these refusals come back
            # instantly, so the old flat 3 s spent twelve seconds waiting out a
            # failure that costs nothing to retry. Linear, capped at ten.
            $wait = [Math]::Min($DelaySec * $try, 10)
            Write-Host ("`r      {0}  attempt {1} of {2} failed, retrying in {3}s{4}" -f `
                $Label, $try, $Attempts, $wait, (" " * 30)) -NoNewline
            Start-Sleep -Seconds $wait
        }
    }
}

function Get-FileOnce {
    param([string] $Uri, [string] $OutFile, [string] $Label)

    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromHours(2)
    try {
        $resp = $client.GetAsync($Uri, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        if (-not $resp.IsSuccessStatusCode) {
            throw "HTTP $([int]$resp.StatusCode) $($resp.ReasonPhrase) for $Uri"
        }
        $total = $resp.Content.Headers.ContentLength
        $src   = $resp.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $dst   = [System.IO.File]::Create($OutFile)
        try {
            $buf  = New-Object byte[] 1048576
            $done = 0L
            $sw   = [Diagnostics.Stopwatch]::StartNew()
            $lastPaint = 0
            while (($n = $src.Read($buf, 0, $buf.Length)) -gt 0) {
                $dst.Write($buf, 0, $n)
                $done += $n
                # Repaint at most ten times a second: a progress line redrawn per
                # 1 MB block costs more wall clock than the copy on a fast link.
                if ($sw.ElapsedMilliseconds - $lastPaint -ge 100) {
                    $lastPaint = $sw.ElapsedMilliseconds
                    $rate = $done / [math]::Max($sw.Elapsed.TotalSeconds, 0.001)
                    if ($total) {
                        $pct = [int](100 * $done / $total)
                        $bar = ("#" * [int]($pct / 4)).PadRight(25, '.')
                        Write-Host ("`r      {0}  [{1}] {2,3}%  {3} / {4}  {5}/s   " -f `
                            $Label, $bar, $pct, (Format-Size $done), (Format-Size $total), (Format-Size $rate)) -NoNewline
                    } else {
                        Write-Host ("`r      {0}  {1}  {2}/s   " -f $Label, (Format-Size $done), (Format-Size $rate)) -NoNewline
                    }
                }
            }
            $sw.Stop()
            Write-Host ("`r      " + $Label + "  " + (Format-Size $done) + " in " + (Format-Num $sw.Elapsed.TotalSeconds 0) + "s" + (" " * 40))
            return $done
        } finally { $dst.Dispose(); $src.Dispose() }
    } finally { $client.Dispose() }
}

# ---------------------------------------------------------------------------
# Unpack, naming each file as it lands
# ---------------------------------------------------------------------------

function Expand-WithProgress {
    param([string] $ZipPath, [string] $Destination)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $entries = @($zip.Entries | Where-Object { $_.Name })   # skip directory entries
        $i = 0
        foreach ($e in $entries) {
            $i++
            $target = Join-Path $Destination $e.FullName
            $dir    = Split-Path $target -Parent
            if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target, $true)
            Write-Host ("`r      {0,4}/{1}  {2,-42} {3}   " -f $i, $entries.Count, `
                        $e.Name.Substring(0, [Math]::Min(42, $e.Name.Length)), (Format-Size $e.Length)) -NoNewline
        }
        Write-Host ("`r      {0} files extracted{1}" -f $entries.Count, (" " * 60))
        return $entries.Count
    } finally { $zip.Dispose() }
}

# ---------------------------------------------------------------------------
# A running server holds its own files
# ---------------------------------------------------------------------------
#
# These are functions rather than inline script for one reason: everything below
# the selftest's exit is unreachable to it. The first version of this fix sat at
# line 744, the selftest returns at 631, and it reported 42 of 42 green without
# executing a single line of it.

function Test-RunsFromDir {
    <#
    .SYNOPSIS
        Is this executable inside that directory?
    .DESCRIPTION
        The process NAME is not enough, and the difference is not academic: a
        development build of llama-server.exe running from somewhere else has the
        same name and holds nothing here. Matching on the name alone renames a
        bin\ directory that nothing is locking.
    #>
    param([string] $ExePath, [string] $Dir)
    if (-not $ExePath -or -not $Dir) { return $false }
    $prefix = $Dir.TrimEnd('\', '/') + '\'
    return $ExePath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-LockingServer {
    <# The llama-server running out of $BinDir, or $null when none is. #>
    param([string] $BinDir)
    foreach ($p in @(Get-Process -Name "llama-server" -ErrorAction SilentlyContinue)) {
        # .Path throws for a process this user cannot open. Not being able to
        # look is not the same as nothing being there, but it is all we have.
        $exe = $null
        try { $exe = $p.Path } catch { $exe = $null }
        if (Test-RunsFromDir -ExePath $exe -Dir $BinDir) { return $p }
    }
    return $null
}

function Move-LockedAside {
    <#
    .SYNOPSIS
        Rename every file in a directory to *.old so an extraction can write over it.
    .DESCRIPTION
        Windows locks a running binary against WRITING, not against renaming: the
        process keeps its handle to the file it opened, and the path is freed for
        the new one. Measured 2026-08-10 against a running executable -- the
        rename succeeded.

        Moved is counted by asking the filesystem afterwards, and Failed names
        what is still sitting there. A rename that quietly fails would hand the
        original IOException to the extraction with a layer of misdirection in
        front of it, which is worse than the bug it was meant to fix.
    #>
    param([string] $BinDir)
    $moved  = 0
    $failed = @()
    foreach ($f in @(Get-ChildItem -LiteralPath $BinDir -File -ErrorAction SilentlyContinue)) {
        if ($f.Name -like "*.old") { continue }
        $oldPath = $f.FullName + ".old"
        # An interrupted update may have left one behind; it is in the way now.
        if (Test-Path -LiteralPath $oldPath) {
            Remove-Item -LiteralPath $oldPath -Force -ErrorAction SilentlyContinue
        }
        Rename-Item -LiteralPath $f.FullName -NewName ($f.Name + ".old") -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $f.FullName) { $failed += $f.Name } else { $moved++ }
    }
    return [pscustomobject]@{ Moved = $moved; Failed = $failed }
}

function Remove-StaleOld {
    <#
    .SYNOPSIS
        Delete the *.old files left behind, and report what actually went.
    .DESCRIPTION
        A file the running server still has mapped CANNOT be deleted. Measured
        2026-08-10: the rename succeeds, the delete is denied, the file stays.
        And that is the NORMAL case here, because the reason it was renamed is
        that the server is still running.

        So Removed is the difference between before and after, taken by looking.
        Counting what was found and calling it "removed" prints a green line in
        exactly the situation where nothing was removed.
    #>
    param([string] $BinDir)
    $before = @(Get-ChildItem -LiteralPath $BinDir -Filter "*.old" -File -ErrorAction SilentlyContinue)
    foreach ($f in $before) {
        Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
    }
    $kept = @(Get-ChildItem -LiteralPath $BinDir -Filter "*.old" -File -ErrorAction SilentlyContinue |
              ForEach-Object { $_.Name })
    return [pscustomobject]@{ Removed = ($before.Count - $kept.Count); Kept = $kept }
}


# ---------------------------------------------------------------------------
# Tailscale (-Tailscale, #249 stage 5): read, print, never run
# ---------------------------------------------------------------------------
# The phone's HTTPS address is `tailscale serve` in front of the mirror's
# loopback listener. This script never elevates, so -Tailscale only READS where
# this machine stands -- `tailscale status --json` and `tailscale serve status
# --json`, the same two calls and the same state table as
# cli\crow_remote.py:tailscale_state, which the Remote dialog uses -- and
# prints the steps that are still missing, in order, each one once. It installs
# nothing and downloads nothing, so it runs on an installed machine without
# fetching the package again.
#
# The winget id is Tailscale.Tailscale, checked 2026-09-24 against
# microsoft/winget-pkgs (manifests/t/Tailscale/Tailscale, 1.102.4, the
# tailscale-setup-full .exe from pkgs.tailscale.com). kb/1022 itself names only
# the .exe and .msi installers. The package is machine-scope, so winget asks
# for elevation itself; this script does not.

$TAILSCALE_WINGET   = "winget install --id Tailscale.Tailscale -e"
$TAILSCALE_KB_WIN   = "https://tailscale.com/kb/1022/install-windows"
$TAILSCALE_DOWNLOAD = "https://tailscale.com/download"
$TAILSCALE_ADMIN    = "https://login.tailscale.com/admin/dns"
$TAILSCALE_IOS      = "https://apps.apple.com/app/tailscale/id1470499037"
$TAILSCALE_ANDROID  = "https://play.google.com/store/apps/details?id=com.tailscale.ipn"
$REMOTE_PORT_DEFAULT = 8765   # crow_core.REMOTE_PORT_DEFAULT

function Get-JsonProp {
    param($Obj, [string] $Name)
    if ($null -eq $Obj -or -not $Obj.PSObject) { return $null }
    $p = $Obj.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    return $null
}

function Get-RemotePort {
    <# remote_port out of settings.json, with crow_gui.remote_port_setting's
    rule: an integer in 1024-65535 (never a bool), else 8765. #>
    param([string] $SettingsPath)
    try {
        $s = Get-Content -LiteralPath $SettingsPath -Raw -ErrorAction Stop | ConvertFrom-Json
    } catch { return $REMOTE_PORT_DEFAULT }
    $v = Get-JsonProp $s "remote_port"
    if (($v -is [int] -or $v -is [long]) -and $v -ge 1024 -and $v -le 65535) { return [int] $v }
    return $REMOTE_PORT_DEFAULT
}

function Invoke-TailscaleRead {
    <# The real seam: one call, 3 s at most (crow_remote.TAILSCALE_TIMEOUT), so
    a hung daemon cannot hang the installer. Returns @{ Code; Out }. #>
    param([string[]] $Argv)
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Argv[0]
        $psi.Arguments = ($Argv[1..($Argv.Count - 1)] -join ' ')
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError  = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow  = $true
        $p = [System.Diagnostics.Process]::Start($psi)
        $stdout = $p.StandardOutput.ReadToEndAsync()
        $null = $p.StandardError.ReadToEndAsync()
        if (-not $p.WaitForExit(3000)) {
            try { $p.Kill() } catch { }
            return @{ Code = 1; Out = "" }
        }
        return @{ Code = $p.ExitCode; Out = $stdout.Result }
    } catch {
        return @{ Code = 1; Out = "" }
    }
}

function Get-TailscaleState {
    <# @{ State; Name; Phone } -- State is crow_remote.tailscale_state's:
    missing, down, https-off, serve-missing, funnel, ready. Phone is $true when
    an iOS or Android device is already in the tailnet. $Run is the seam the
    selftest fills with a fake; it is only ever given the two read calls. #>
    param([int] $Port, [string] $Exe, [scriptblock] $Run = { param($a) Invoke-TailscaleRead $a })
    $out = [pscustomobject]@{ State = "missing"; Name = ""; Phone = $false }
    if (-not $Exe) { return $out }
    $out.State = "down"
    $read = {
        param([string[]] $a)
        try { $r = & $Run $a } catch { return $null }
        if (-not $r -or $r.Code -ne 0) { return $null }
        try { return ($r.Out | ConvertFrom-Json) } catch { return $null }
    }
    $st = & $read @($Exe, "status", "--json")
    if (-not $st) { return $out }
    $peers = Get-JsonProp $st "Peer"
    if ($peers) {
        foreach ($p in $peers.PSObject.Properties) {
            if (@("ios", "android") -contains ("" + (Get-JsonProp $p.Value "OS")).ToLower()) { $out.Phone = $true }
        }
    }
    $name = ("" + (Get-JsonProp (Get-JsonProp $st "Self") "DNSName")).Trim().TrimEnd('.').ToLower()
    if ((Get-JsonProp $st "BackendState") -ne "Running" -or -not $name) { return $out }
    $out.Name = $name
    $certs = @(Get-JsonProp $st "CertDomains" | ForEach-Object { ("" + $_).TrimEnd('.').ToLower() })
    if ($certs -notcontains $name) { $out.State = "https-off"; return $out }
    $sv  = & $read @($Exe, "serve", "status", "--json")
    $key = $name + ":443"
    if ((Get-JsonProp (Get-JsonProp $sv "AllowFunnel") $key) -eq $true) { $out.State = "funnel"; return $out }
    $root  = Get-JsonProp (Get-JsonProp (Get-JsonProp (Get-JsonProp $sv "Web") $key) "Handlers") "/"
    $proxy = ("" + (Get-JsonProp $root "Proxy")).TrimEnd('/').ToLower()
    $want  = foreach ($s in @("http://", "")) { foreach ($h in @("127.0.0.1", "localhost")) { "$s${h}:$Port" } }
    $out.State = if ($want -contains $proxy) { "ready" } else { "serve-missing" }
    return $out
}

function Get-TailscaleSteps {
    <# The missing steps for a state, as @{ Kind = 'step'|'cmd'; Text }. Pure. #>
    param([string] $State, [int] $Port, [string] $Name = "", [bool] $Phone = $false)
    $l = New-Object System.Collections.Generic.List[object]
    $step = { param($t) $script:tsN++; $l.Add([pscustomobject]@{ Kind = 'step'; Text = "$($script:tsN). $t" }) }
    $cmd  = { param($t) $l.Add([pscustomobject]@{ Kind = 'cmd'; Text = $t }) }
    $script:tsN = 0
    if ($State -eq "missing") {
        & $step "install Tailscale (winget asks for elevation itself; or the installer from $TAILSCALE_KB_WIN):"
        & $cmd  $TAILSCALE_WINGET
    }
    if (@("missing", "down", "unknown") -contains $State) {
        & $step "log in: tray icon -> Log in, or in a terminal (prints a login URL):"
        & $cmd  "tailscale up"
    }
    if (@("missing", "down", "unknown", "https-off") -contains $State) {
        & $step "admin console -> DNS -> HTTPS Certificates -> Enable HTTPS:"
        & $cmd  $TAILSCALE_ADMIN
    }
    if (@("missing", "down", "unknown", "https-off", "serve-missing") -contains $State) {
        & $step "the one-time serve command, in an ELEVATED PowerShell (Run as administrator):"
        & $cmd  "tailscale serve --bg --https=443 http://127.0.0.1:$Port"
    }
    if ($State -eq "funnel") {
        & $step "Funnel is on for ${Name}:443 -- public on the internet. Crow refuses it; in an elevated PowerShell:"
        & $cmd  "tailscale funnel --https=443 off"
    }
    if (-not $Phone) {
        & $step "the phone: install Tailscale, log in with the SAME account:"
        & $cmd  "iPhone   $TAILSCALE_IOS"
        & $cmd  "Android  $TAILSCALE_ANDROID"
    }
    if ($State -eq "ready") {
        & $step "done: in Crow, /remote on -> Remote dialog -> HTTPS, then scan the QR:"
        & $cmd  "https://$Name/"
    } else {
        & $step "then in Crow: /remote on -> Remote dialog -> HTTPS, then scan the QR"
    }
    return $l.ToArray()
}

function Show-TailscaleSteps {
    $port = Get-RemotePort (Join-Path $InstallTo "settings.json")
    $exe  = (Get-Command tailscale -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $exe -and $env:ProgramFiles -and (Test-Path -LiteralPath (Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"))) {
        $exe = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
    }
    $ts = Get-TailscaleState -Port $port -Exe $exe
    $global:LASTEXITCODE = 0
    Write-Host ""
    Write-Host "  Tailscale -- the phone from anywhere, over HTTPS (-Tailscale)" -ForegroundColor Cyan
    $said = switch ($ts.State) {
        "missing"       { "tailscale is not installed" }
        "down"          { "tailscale is installed but not running or not logged in" }
        "https-off"     { "logged in as $($ts.Name); HTTPS certificates are off for this tailnet" }
        "serve-missing" { "logged in as $($ts.Name), HTTPS on; nothing serves :443 -> 127.0.0.1:$port yet" }
        "funnel"        { "logged in as $($ts.Name); Funnel is on for :443" }
        "ready"         { "ready: https://$($ts.Name)/ -> 127.0.0.1:$port" }
    }
    Write-Host "        $said" -ForegroundColor DarkGray
    Write-Host "        this script never elevates -- the lines below are yours to run:" -ForegroundColor DarkGray
    Write-Host ""
    foreach ($s in (Get-TailscaleSteps -State $ts.State -Port $port -Name $ts.Name -Phone $ts.Phone)) {
        if ($s.Kind -eq 'step') { Write-Host "  $($s.Text)" -ForegroundColor DarkGray }
        else                    { Write-Host "    $($s.Text)" -ForegroundColor White }
    }
    Write-Host ""
    Write-Host "        all platforms: $TAILSCALE_DOWNLOAD" -ForegroundColor DarkGray
    Write-Host "        the whole setup: https://github.com/nibor1896/Crow/blob/main/docs/user-guide/remote-tailscale.md" -ForegroundColor DarkGray
    Write-Host ""
}


# ---------------------------------------------------------------------------
# The voxel kit (-PathTracer, #298)
# ---------------------------------------------------------------------------
# The kit ships in every package (kits\pathtracer) and MANIFEST.json already
# verifies its bytes on an install. The flag switches its skill on; this check
# exists for the run that installs nothing (-PathTracer on a current install).

function Test-PathTracerKit {
    <#
    'ok' | 'missing' | 'corrupt': the bundle against the sha256 in kit.json.
    Pure over a directory, so the selftest drives all three.
    #>
    param([string] $KitDir)
    $json = Join-Path $KitDir "kit.json"
    $bundle = Join-Path $KitDir "crow-pathtracer.js"
    if (-not (Test-Path -LiteralPath $json) -or -not (Test-Path -LiteralPath $bundle)) { return "missing" }
    try { $want = (Get-Content -LiteralPath $json -Raw | ConvertFrom-Json).bundle.sha256 } catch { return "corrupt" }
    $have = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash
    if ($want -and $have -eq $want.ToUpperInvariant()) { return "ok" }
    return "corrupt"
}

function Invoke-PathTracerKit {
    <#
    Switch the voxel-diorama skill on with the client's own function and say
    what happened; without -PathTracer, one line on how to switch it on.
    #>
    param([string] $InstallTo, [string] $PythonPath, [bool] $Enable)
    $kit = Join-Path $InstallTo "kits\pathtracer"
    # The client's config directory is %LOCALAPPDATA%\Crow whatever -InstallTo says
    # (crow_platform.config_dir), so the skill is looked for there.
    $skill = Join-Path $env:LOCALAPPDATA "Crow\skills\voxel-diorama\SKILL.md"
    $isOn = (Test-Path -LiteralPath $skill) -and -not (Select-String -LiteralPath $skill -Pattern '^enabled: false$' -Quiet)
    if (-not $Enable) {
        if ($isOn) { Write-Item "voxel kit" "the voxel-diorama skill is on" "ok" }
        else { Write-Item "voxel kit" "installed, skill off -- -PathTracer switches it on" }
        return
    }
    $verdict = Test-PathTracerKit -KitDir $kit
    if ($verdict -ne "ok") {
        Write-Item "voxel kit" "kits\pathtracer is $verdict -- reinstall with -Force" "warn"
        return
    }
    Write-Item "voxel kit" "crow-pathtracer.js matches kit.json" "ok"
    if (-not $PythonPath) {
        Write-Item "voxel kit" "no Python -- switch the skill on in the window's settings, Skills page" "warn"
        return
    }
    $cli = Join-Path $InstallTo "cli"
    $code = "import sys; sys.path.insert(0, sys.argv[1]); import crow_core; " +
            "print(crow_core.enable_kit_skill()); " +
            "exe = crow_core.find_esbuild(sys.argv[2])[0]; print(exe or '')"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = @(& $PythonPath -c $code $cli $InstallTo 2>$null)
    } catch {
        $out = @()
    } finally {
        $ErrorActionPreference = $prevEap
    }
    $global:LASTEXITCODE = 0
    $state = if ($out.Count -gt 0) { "$($out[0])".Trim() } else { "" }
    switch ($state) {
        "enabled" { Write-Item "voxel kit" "the voxel-diorama skill is switched on" "ok" }
        "already" { Write-Item "voxel kit" "the voxel-diorama skill was already on" "ok" }
        default   { Write-Item "voxel kit" "could not switch the skill on -- use the Skills page in the settings" "warn" }
    }
    $esb = if ($out.Count -gt 1) { "$($out[1])".Trim() } else { "" }
    if ($esb) { Write-Item "voxel kit" "build_bundle has an esbuild: $esb" "ok" }
    else { Write-Item "voxel kit" "no esbuild found -- build_bundle cannot inline the kit into a page (Node's npx cache, a node_modules, PATH, or `"bundler`" in settings.json)" "warn" }
}

# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

function Invoke-Selftest {
    $ok = 0; $red = 0
    function C { param([string]$N, [bool]$P)
        if ($P) { Write-Host "  ok   $N"; $script:sOk++ } else { Write-Host "  FAIL $N" -ForegroundColor Red; $script:sRed++ } }
    $script:sOk = 0; $script:sRed = 0

    Write-Host "install.ps1 selftest"

    $good = @{ VramMb=32607; RamGb=63.4; FreeDiskGb=450; HasNvidiaSmi=$true; Is64Bit=$true; PsVersion=[version]"5.1"
               PythonPath="C:\Python313\python.exe"; WebView2Version="151.0.4129.78"
               NodePath="C:\Program Files\nodejs\node.exe" }

    C "the development machine passes"            ((Test-Preflight @good).Ok)
    C "and passes without warnings"               ((Test-Preflight @good).Warnings.Count -eq 0)

    # Each rejection, one value moved from the passing case. A preflight that
    # accepts everything would pass the first two checks and protect nobody.
    $noGpu = $good.Clone(); $noGpu.HasNvidiaSmi = $false; $noGpu.VramMb = 0
    C "no NVIDIA driver is rejected"              (-not (Test-Preflight @noGpu).Ok)

    $small = $good.Clone(); $small.VramMb = 12000
    C "12 GB VRAM is rejected as unmeasured"      (-not (Test-Preflight @small).Ok)

    $mid = $good.Clone(); $mid.VramMb = 24000
    C "24 GB VRAM passes with a warning"          ((Test-Preflight @mid).Ok -and (Test-Preflight @mid).Warnings.Count -gt 0)

    $x86 = $good.Clone(); $x86.Is64Bit = $false
    C "32-bit Windows is rejected"                (-not (Test-Preflight @x86).Ok)

    $oldPs = $good.Clone(); $oldPs.PsVersion = [version]"4.0"
    C "PowerShell 4 is rejected"                  (-not (Test-Preflight @oldPs).Ok)

    $noDisk = $good.Clone(); $noDisk.FreeDiskGb = 1
    C "1 GB free disk is rejected"                (-not (Test-Preflight @noDisk).Ok)

    $tight = $good.Clone(); $tight.FreeDiskGb = 5
    C "5 GB free passes, warns about the model"   ((Test-Preflight @tight).Ok -and (Test-Preflight @tight).Warnings.Count -gt 0)

    $lowRam = $good.Clone(); $lowRam.RamGb = 8
    C "8 GB RAM warns but does not block"         ((Test-Preflight @lowRam).Ok -and (Test-Preflight @lowRam).Warnings.Count -gt 0)

    # The two client prerequisites. What is being asserted here is not that they
    # refuse -- they must not, the install is worth having without them -- but that
    # they are asked in THIS function, which is the only thing in this script that
    # runs before the download. A copy of these checks in the last step would pass
    # nothing here and would still be too late.
    $noPy = $good.Clone(); $noPy.PythonPath = ""; $noPy.WebView2Version = ""
    C "no python warns and does NOT block"        ((Test-Preflight @noPy).Ok -and (Test-Preflight @noPy).Warnings.Count -gt 0)
    # One missing download, one line. Two warnings for one cause is the installer
    # describing a problem the user does not have.
    C "a missing python is one warning, not two"  ((Test-Preflight @noPy).Warnings.Count -eq 1)

    $noWv = $good.Clone(); $noWv.WebView2Version = ""
    C "no WebView2 runtime warns"                 ((Test-Preflight @noWv).Ok -and (Test-Preflight @noWv).Warnings.Count -gt 0)
    C "and does NOT block the install"            ((Test-Preflight @noWv).Ok)
    C "and says which client that costs"          ((((Test-Preflight @noWv).Warnings) -match 'crow_gui').Count -gt 0)
    C "a runtime that is there warns about none"  ((Test-Preflight @good).Warnings.Count -eq 0)

    # Node, decided 2026-08-22: reported, never required. The third check is the
    # one that keeps the decision honest -- an installer that refused here would
    # still pass the first two.
    $noNode = $good.Clone(); $noNode.NodePath = ""
    C "no node warns"                             ((Test-Preflight @noNode).Warnings.Count -gt 0)
    C "and does NOT block the install"            ((Test-Preflight @noNode).Ok)
    C "and names what needs it"                   ((((Test-Preflight @noNode).Warnings) -match 'MCP').Count -gt 0)
    C "a missing node is one warning, not two"    ((Test-Preflight @noNode).Warnings.Count -eq 1)
    C "node on the PATH warns about none"         ((Test-Preflight @good).Warnings.Count -eq 0)

    # THE PROMISE THE PREFLIGHT MAY NOT MAKE. pywebview is installed after the
    # download, so nothing before it may claim the window will run -- a green
    # line in front of a condition that fails later is the shape 0.2.0 removed
    # from the Python row, and putting it back for the window would undo it.
    C "the preflight says nothing about pywebview" (
        (((Test-Preflight @good).Warnings + (Test-Preflight @noWv).Warnings +
          (Test-Preflight @noPy).Warnings) -match 'pywebview').Count -eq 0)

    # THE PIP STEP, held against the source rather than run: running it would
    # write into this machine's Python, and a selftest that installs packages is
    # a selftest nobody dares run twice.
    $pipSrc = Get-Content -LiteralPath $PSCommandPath -Raw
    C "pip is called on the interpreter found"    ($pipSrc -match '\$facts\.PythonPath -m pip install')
    C "a failed pip prints the manual command"    ($pipSrc -match '-m pip install pywebview" -ForegroundColor White')
    C "and does not become the exit code"         ($pipSrc -match '(?s)pipRc = \$LASTEXITCODE.*?global:LASTEXITCODE = 0')
    C "a failed pip says the CLI is unaffected"   ($pipSrc -match 'terminal client is unaffected')

    # THE DICTATION STEP, held against the source for the same reason.
    C "dictation pip names both packages"        ($pipSrc -match '--quiet faster-whisper sounddevice')
    C "a failed one prints the manual command"   ($pipSrc -match '-m pip install faster-whisper sounddevice" -ForegroundColor White')
    C "and says typing still works"              ($pipSrc -match 'typing is unaffected')
    C "the model lands beside the client"        ($pipSrc -match 'Join-Path \$InstallTo "models"')
    C "a file already there is not re-fetched"   ($pipSrc -match 'if \(Test-Path -LiteralPath \$dest\) \{ continue \}')
    C "a failed model download is a warning"     ($pipSrc -match 'everything else installed')

    # BOTH START LINES, IN ORDER, AND THE SECOND ONE OUT OF THE CHECKER'S WINDOW.
    # This is the half state this stage was written against, and it cannot be
    # caught by reading the script: tools/check_operating_point.py finds the
    # printed server command by taking a 2000-character region from the
    # "llama-server" that precedes it, so a hint added ABOVE the start lines
    # pushes --moe-stream-l2 out of that region and reports this installer as
    # broken at the next release. Measured on this version, by padding the file
    # at the real path and running the checker: 179 characters inserted above the
    # --port line stay green, 180 go red ("1 of 12 flags differ").
    #
    # 179 and not the 176 the end of the last match suggests, and the three
    # characters are worth a sentence: the manifest pattern is
    # `(--moe-stream-l2)\s+\S+` and \S+ shortens as the region's edge arrives, so
    # the flag is still found after its printed value has been half cut off. The
    # margin is therefore measured by running the checker, never by counting to
    # the end of the match.
    #
    # Asserted here rather than remembered, because that margin moves with every
    # edit made above these lines. The file is normalised to LF first: the
    # checker reads through Python's universal newlines, and on a CRLF checkout a
    # raw byte offset would be larger than the one it actually sees -- which
    # would make this check pass while the checker fails, the one direction a
    # guard may not fail in.
    if ($PSCommandPath -and (Test-Path -LiteralPath $PSCommandPath)) {
        $src = (Get-Content -LiteralPath $PSCommandPath -Raw) -replace "`r`n", "`n"
        # EVERY NEEDLE IS ASSEMBLED, NEVER WRITTEN WHOLE, and the first version of
        # this block is why. A check that reads its own script finds ITS OWN
        # literal first -- these lines sit some six hundred lines above the ones
        # they are looking for -- so it measured the distance from a comment to
        # the selftest and reported the start lines as inside the window. It went
        # red on a file that is correct, which is the failure that gets a check
        # deleted rather than read.
        # SEARCHED FROM THE FINAL SCREEN DOWN, and two things forced that.
        # The needles appear in THIS block as literals six hundred lines above
        # the printed ones, which is why they are assembled rather than written
        # whole -- and since the installer leads with Qwen the terminal line now
        # carries --base-url, so it no longer ends at the colour argument the
        # old needle pinned it to. Starting after the step header answers both:
        # what this case is about is the ORDER of the two lines on the last
        # screen, not the flags either of them happens to carry.
        $tailAt = [Math]::Max($src.IndexOf('Write-Step "What is left' + ' to do"'), 0)
        $cliAt  = $src.IndexOf('cli\crow.py', $tailAt)
        $guiAt  = $src.IndexOf('cli\crow_gui.py', $tailAt)
        C "the terminal client's start line is printed" ($cliAt -ge 0)
        C "the window's start line is printed as well"  ($guiAt -ge 0)
        C "and the terminal one comes first"            ($cliAt -ge 0 -and $guiAt -gt $cliAt)

        # The anchor the checker actually lands on: the last "llama-server" at or
        # before the printed --moe-stream-l2, which is the region that has to hold
        # all twelve flags.
        $l2At   = $src.IndexOf('--moe-stream-l2 ' + '$l2"')
        $anchor = if ($l2At -ge 0) { $src.LastIndexOf('llama-server', $l2At) } else { -1 }
        C "the printed server line still has an anchor" ($anchor -ge 0)

        # THE MARGIN, AND THIS IS THE CASE THAT EARNS ITS PLACE. The first version
        # of this block asserted that the two start lines sit PAST the 2000
        # characters, which is the wrong direction and would have stayed green
        # through the exact failure it was written for: text inserted between the
        # server block and the start lines pushes those lines FURTHER away while
        # pushing --moe-stream-l2 out of the region. What has to be inside the
        # window is the last flag, so that is what is measured.
        #
        # DELIBERATELY THREE CHARACTERS STRICTER THAN THE CHECKER. This takes the
        # end of the whole match; the manifest pattern ends in \S+, which shortens
        # as the region's edge arrives, so the checker survives to 179 inserted
        # characters where this goes red at 177. Early is the only direction a
        # margin guard is allowed to be wrong in.
        $l2End = if ($l2At -ge 0) { $l2At + ('--moe-stream-l2 ' + '$l2"').Length } else { -1 }
        C "the last printed flag is inside the checker's window" `
          ($anchor -ge 0 -and $l2End -gt 0 -and $l2End -le ($anchor + 2000))
    }

    # The host tier is offered at exactly one ratio. Both directions are checked, because a rule
    # that only ever says yes is not a rule - and the 63.4 GB case is the development machine,
    # which must NOT get it: 63.4 is below 64, and rounding it up would hand out page-locked
    # memory on a machine the measurement did not cover.
    C "63.4 GB - the measured machine - gets 32"  ((Get-L2Gib -RamGb 63.4) -eq 32)
    C "128 GB RAM gets the same 32, not more"     ((Get-L2Gib -RamGb 128) -eq 32)
    C "48 GB gets no tier - never measured"       ((Get-L2Gib -RamGb 48) -eq 0)
    C "32 GB gets no tier"                        ((Get-L2Gib -RamGb 32) -eq 0)
    C "16 GB gets no tier"                        ((Get-L2Gib -RamGb 16) -eq 0)

    # Where the package comes from. No network: the decision is a pure function.
    $noSrc = Resolve-PackageSource -SourceUrl "" -Asset "crow-9.9.9-win-x64.zip" -Version "9.9.9"
    C "no -SourceUrl still points at the release" `
      ((-not $noSrc.IsLocal) -and $noSrc.Uri -eq "https://github.com/nibor1896/Crow/releases/download/v9.9.9/crow-9.9.9-win-x64.zip")

    $httpSrc = Resolve-PackageSource -SourceUrl "https://example.invalid/x.zip" -Asset "a.zip" -Version "9.9.9"
    C "an http source overrides the release"     ((-not $httpSrc.IsLocal) -and $httpSrc.Uri -eq "https://example.invalid/x.zip")

    $probe = Join-Path $env:TEMP ("crow-selftest-" + [guid]::NewGuid().ToString("N") + ".zip")
    Set-Content -LiteralPath $probe -Value "not really a zip" -Encoding ascii
    try {
        $localSrc = Resolve-PackageSource -SourceUrl $probe -Asset "a.zip" -Version "9.9.9"
        C "a local package is accepted"          ($localSrc.IsLocal -and $localSrc.Uri -eq $probe)
    } finally {
        Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
    }

    # The negative half: a path that is not there must stop the run rather than
    # fall back to the release, which would install something else than asked for.
    $missed = $false
    try   { Resolve-PackageSource -SourceUrl (Join-Path $env:TEMP "crow-does-not-exist.zip") -Asset "a.zip" -Version "9.9.9" | Out-Null }
    catch { $missed = $true }
    C "a missing local package is rejected"      $missed

    # Updating. Every branch, because the defect this replaced was a single
    # refusal that treated "an older Crow is here" the same as "a stranger's
    # files are here" -- and gave both the same unusable advice.
    C "an older install updates"                 ((Resolve-InstallAction "0.0.4" "0.0.5" $false).Action -eq 'update')
    C "a two-step gap updates"                   ((Resolve-InstallAction "0.0.1" "0.0.5" $false).Action -eq 'update')
    C "the same version does nothing"            ((Resolve-InstallAction "0.0.5" "0.0.5" $false).Action -eq 'uptodate')
    C "the same version reinstalls with -Force"  ((Resolve-InstallAction "0.0.5" "0.0.5" $true).Action  -eq 'install')
    C "a newer install is NOT overwritten"       ((Resolve-InstallAction "0.0.6" "0.0.5" $false).Action -eq 'downgrade')
    C "and goes back only with -Force"           ((Resolve-InstallAction "0.0.6" "0.0.5" $true).Action  -eq 'install')

    # The cases that must refuse. An unidentified directory is somebody's data
    # until proven otherwise; a version string that will not parse must not be
    # silently read as 0.0.0, which would make every unknown look like "older".
    C "an unidentified target refuses"           ((Resolve-InstallAction $null "0.0.5" $false).Action -eq 'unknown')
    C "and is overwritten only with -Force"      ((Resolve-InstallAction $null "0.0.5" $true).Action  -eq 'install')
    C "an unparseable version refuses"           ((Resolve-InstallAction "not-a-version" "0.0.5" $false).Action -eq 'unknown')
    C "an unparseable TARGET refuses too"        ((Resolve-InstallAction "0.0.3" "garbage" $false).Action -eq 'unknown')

    # Reading the version back out of a shipped tree, and the two ways that fails.
    $vdir = Join-Path $env:TEMP ("crow-selftest-v-" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Force -Path (Join-Path $vdir "cli") | Out-Null
        Set-Content -LiteralPath (Join-Path $vdir "cli\crow.py") -Encoding utf8 `
                    -Value @('#!/usr/bin/env python', 'VERSION = "1.2.3"', 'DEFAULT_MODEL = "crow"')
        C "the installed version is read"        ((Get-InstalledVersion $vdir) -eq "1.2.3")

        Set-Content -LiteralPath (Join-Path $vdir "cli\crow.py") -Encoding utf8 -Value @('no version line here')
        C "a file without VERSION reads as null" ($null -eq (Get-InstalledVersion $vdir))
    } finally {
        Remove-Item -LiteralPath $vdir -Recurse -Force -ErrorAction SilentlyContinue
    }
    C "an empty directory reads as null"         ($null -eq (Get-InstalledVersion (Join-Path $env:TEMP "crow-selftest-absent")))

    # The regression behind the 255: reading the machine must not leave a native
    # command's broken exit code behind, because the script's own exit code is
    # whatever the last native call left there.
    $global:LASTEXITCODE = 0
    $null = Get-MachineFacts
    C "reading the machine leaves a clean exit code" ($LASTEXITCODE -eq 0)

    # The regression that closed the first public install's window: `exit` in a
    # text run through iex takes the host shell with it.
    C "a run from a file may exit the process"   (Test-CanExitProcess "C:\x\install.ps1")
    C "a run through iex must not"               (-not (Test-CanExitProcess ""))

    # The check that did not exist until a flipped byte proved Expand-Archive
    # will not catch one. Both answers driven, because a verifier that cannot
    # report damage is a decoration.
    $good = @(
        [pscustomobject]@{ Path = "a.dll"; Expected = "AABB"; Actual = "aabb" }
        [pscustomobject]@{ Path = "b.exe"; Expected = "CCDD"; Actual = "CCDD" }
    )
    $v = Compare-Manifest $good
    C "a matching install passes"                 ($v.Ok -and $v.Checked -eq 2)
    C "and the hash compare ignores case"         ($v.Mismatched.Count -eq 0)

    $corrupt = @([pscustomobject]@{ Path = "a.dll"; Expected = "AABB"; Actual = "BEEF" })
    $v = Compare-Manifest $corrupt
    C "one wrong hash fails the install"          ((-not $v.Ok) -and $v.Mismatched -contains "a.dll")

    $gone = @([pscustomobject]@{ Path = "a.dll"; Expected = "AABB"; Actual = $null })
    $v = Compare-Manifest $gone
    C "a file that did not land fails too"        ((-not $v.Ok) -and $v.Missing -contains "a.dll")

    # The case the update path did not have until now: a file the package USED to
    # ship. Compare-Manifest above cannot see it -- it walks the current manifest,
    # and a dropped file is not in it by definition.
    $was = @("bin/llama.dll", "cli/crow.py", "cli/test_crow.py")
    $now = @("bin/llama.dll", "cli/crow.py")
    $d = Find-DroppedFiles -PreviousPaths $was -CurrentPaths $now
    C "a file the package dropped is found"       ($d.Dropped -contains "cli/test_crow.py" -and $d.Dropped.Count -eq 1)
    C "and the count carries its denominator"     ($d.Checked -eq 3)

    # THE REGRESSION, and it is not hypothetical. The first version of this asked
    # "what is on disk that the manifest does not name?" and kept an exception
    # list. On 2026-08-10 it deleted %LOCALAPPDATA%\Crow\session-backup\ -- three
    # files, 473 MB, created by the user minutes earlier on our own instructions.
    # It was not session/, so it was not on the list, so it was rubbish.
    # Asked in this direction the folder cannot be selected: no Crow package ever
    # installed it, so it is in neither manifest.
    $d = Find-DroppedFiles -PreviousPaths $was -CurrentPaths $now
    C "a folder no package installed is untouchable" (
        ($d.Dropped -notcontains "session-backup/session.json") -and
        ($d.Dropped -notcontains "session/crow-session.bin") -and
        ($d.Dropped -notcontains "notes.txt"))

    # Nothing dropped is a real answer and must not be confused with "nothing
    # examined" -- hence the denominator on the quiet path too.
    $d = Find-DroppedFiles -PreviousPaths $was -CurrentPaths $was
    C "an unchanged package drops nothing"        ($d.Dropped.Count -eq 0 -and $d.Checked -eq 3)

    # First install: no previous manifest exists, so there is nothing to remove.
    # The dangerous reading of an empty list is "everything is dropped".
    $d = Find-DroppedFiles -PreviousPaths @() -CurrentPaths $now
    C "a first install drops nothing"             ($d.Dropped.Count -eq 0 -and $d.Checked -eq 0)

    # The manifest is written by one tool and read back by another, and the two
    # do not agree on separators; NTFS does not agree on case with anyone. A
    # mismatch here would delete a file that is still shipped.
    $d = Find-DroppedFiles -PreviousPaths @("bin\llama.dll") -CurrentPaths @("bin/LLAMA.dll")
    C "separator and case do not drop a kept file" ($d.Dropped.Count -eq 0)

    # A path listed twice must be removed once, or the count reports work twice.
    $d = Find-DroppedFiles -PreviousPaths @("a.dll", "a.dll") -CurrentPaths @()
    C "a duplicate entry is dropped once"         ($d.Dropped.Count -eq 1)

    # Whose server is it. Both directions, because a rule that only ever says
    # yes renames a directory nothing is holding.
    C "an exe inside the install dir is ours"     (Test-RunsFromDir -ExePath "C:\Crow\bin\llama-server.exe" -Dir "C:\Crow\bin")
    C "case does not decide it"                   (Test-RunsFromDir -ExePath "c:\crow\BIN\llama-server.exe" -Dir "C:\Crow\bin")
    C "a dev build elsewhere is NOT ours"         (-not (Test-RunsFromDir -ExePath "C:\dev\wt-25\bin\llama-server.exe" -Dir "C:\Crow\bin"))
    C "a sibling directory is not inside it"      (-not (Test-RunsFromDir -ExePath "C:\Crow\bin-old\llama-server.exe" -Dir "C:\Crow\bin"))
    C "a process we cannot read is not a match"   (-not (Test-RunsFromDir -ExePath $null -Dir "C:\Crow\bin"))

    # Against real files with a real lock, because the entire question is what
    # Windows does with one. FileShare::None is the strict case: it cannot even
    # be renamed, which is the failure path that must not stay silent.
    $tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("crow-selftest-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    $held = $null
    try {
        Set-Content -LiteralPath (Join-Path $tmpDir "free.dll") -Value "x" -Encoding Ascii
        Set-Content -LiteralPath (Join-Path $tmpDir "held.dll") -Value "x" -Encoding Ascii
        $held = [System.IO.File]::Open((Join-Path $tmpDir "held.dll"), 'Open', 'Read', 'None')

        $aside = Move-LockedAside -BinDir $tmpDir
        C "an unheld file is moved aside"          ($aside.Moved -eq 1)
        C "a held file is REPORTED, not swallowed" ($aside.Failed -contains "held.dll")

        $held.Close(); $held = $null
        Set-Content -LiteralPath (Join-Path $tmpDir "stuck.dll.old") -Value "x" -Encoding Ascii
        $held = [System.IO.File]::Open((Join-Path $tmpDir "stuck.dll.old"), 'Open', 'Read', 'None')

        $swept = Remove-StaleOld -BinDir $tmpDir
        C "a free .old file is really removed"     ($swept.Removed -eq 1)
        C "and one still held is NOT called gone"  ($swept.Kept -contains "stuck.dll.old")
    } finally {
        if ($held) { $held.Close() }
        Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    C "Format-Size: bytes"     ((Format-Size 512) -eq "512 B")
    C "Format-Size: megabytes" ((Format-Size 506400000) -eq "482.9 MB")
    C "Format-Size: gigabytes" ((Format-Size 103000000000) -eq "95.93 GB")

    # -Tailscale (#249 stage 5). The state is read through a FAKE seam -- the
    # real CLI is never called from here, and the fake records every argv it
    # is given, so "reads only" is checked rather than claimed.
    $tsName = "pc.tail1234.ts.net"
    $script:tsCalls = New-Object System.Collections.Generic.List[string]
    $script:tsStatus = $null; $script:tsServe = $null
    $fake = { param([string[]] $a)
        $script:tsCalls.Add(($a[1..($a.Count - 1)] -join ' '))
        $j = if ($a[1] -eq "status") { $script:tsStatus } elseif ($a[1] -eq "serve") { $script:tsServe } else { $null }
        if ($null -eq $j) { return @{ Code = 1; Out = "" } }
        return @{ Code = 0; Out = $j } }
    C "tailscale: no executable reads 'missing'" ((Get-TailscaleState -Port 8765 -Exe "" -Run $fake).State -eq "missing")
    C "tailscale: a daemon that answers nothing reads 'down'" ((Get-TailscaleState -Port 8765 -Exe "C:\fake\tailscale.exe" -Run $fake).State -eq "down")
    $script:tsStatus = '{"BackendState":"Running","Self":{"DNSName":"' + $tsName + '."},"CertDomains":[],"Peer":{}}'
    C "tailscale: logged in without CertDomains reads 'https-off'" ((Get-TailscaleState -Port 8765 -Exe "C:\fake\tailscale.exe" -Run $fake).State -eq "https-off")
    $script:tsStatus = '{"BackendState":"Running","Self":{"DNSName":"' + $tsName + '."},"CertDomains":["' + $tsName + '"],"Peer":{"k":{"OS":"android"}}}'
    $script:tsServe = '{}'
    $r = Get-TailscaleState -Port 8765 -Exe "C:\fake\tailscale.exe" -Run $fake
    C "tailscale: HTTPS on, no serve reads 'serve-missing'" ($r.State -eq "serve-missing" -and $r.Name -eq $tsName)
    C "tailscale: and sees the Android phone"     ($r.Phone)
    $script:tsServe = '{"Web":{"' + $tsName + ':443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8765"}}}}}'
    C "tailscale: serve at 127.0.0.1:8765 reads 'ready'" ((Get-TailscaleState -Port 8765 -Exe "C:\fake\tailscale.exe" -Run $fake).State -eq "ready")
    C "tailscale: and at another port does not"   ((Get-TailscaleState -Port 9123 -Exe "C:\fake\tailscale.exe" -Run $fake).State -eq "serve-missing")
    $script:tsServe = '{"AllowFunnel":{"' + $tsName + ':443":true}}'
    C "tailscale: Funnel on reads 'funnel'"       ((Get-TailscaleState -Port 8765 -Exe "C:\fake\tailscale.exe" -Run $fake).State -eq "funnel")
    C "NEGATIVE: only the two read calls were made" (
        @($script:tsCalls | Where-Object { $_ -ne "status --json" -and $_ -ne "serve status --json" }).Count -eq 0)

    $all = (Get-TailscaleSteps -State "missing" -Port 8765) | ForEach-Object { $_.Text }
    $at  = { param($p) for ($i = 0; $i -lt $all.Count; $i++) { if ($all[$i] -like $p) { return $i } }; return -1 }
    C "tailscale steps from 'missing': winget, login, HTTPS, serve, phone, in order" (
        (& $at "winget install --id Tailscale.Tailscale -e") -ge 0 -and
        (& $at "winget install --id Tailscale.Tailscale -e") -lt (& $at "tailscale up") -and
        (& $at "tailscale up") -lt (& $at "*admin/dns") -and
        (& $at "*admin/dns") -lt (& $at "tailscale serve --bg --https=443 http://127.0.0.1:8765") -and
        (& $at "tailscale serve --bg*") -lt (& $at "iPhone*"))
    $few = ((Get-TailscaleSteps -State "serve-missing" -Port 9123 -Name "x" -Phone $true) | ForEach-Object { $_.Text }) -join "`n"
    C "tailscale steps from 'serve-missing': only serve, on the configured port" (
        $few -match '127\.0\.0\.1:9123' -and $few -notmatch 'winget|tailscale up|admin/dns|apps\.apple')
    C "and says the serve line needs an elevated shell" ($few -match 'ELEVATED')
    $done = ((Get-TailscaleSteps -State "ready" -Port 8765 -Name "pc.t.ts.net" -Phone $true) | ForEach-Object { $_.Text }) -join "`n"
    C "NEGATIVE: 'ready' with a phone prints no command, only the address" ($done -notmatch 'tailscale ' -and $done -match 'https://pc\.t\.ts\.net/')

    $sp = Join-Path $env:TEMP ("crow-selftest-s-" + [guid]::NewGuid().ToString("N") + ".json")
    try {
        Set-Content -LiteralPath $sp -Value '{"remote_port": 9123}' -Encoding ascii
        $p1 = Get-RemotePort $sp
        Set-Content -LiteralPath $sp -Value '{"remote_port": true}' -Encoding ascii
        $p2 = Get-RemotePort $sp
        Set-Content -LiteralPath $sp -Value '{"remote_port": 80}' -Encoding ascii
        $p3 = Get-RemotePort $sp
        C "remote_port is read; bool and <1024 fall back to 8765" ($p1 -eq 9123 -and $p2 -eq 8765 -and $p3 -eq 8765)
    } finally {
        Remove-Item -LiteralPath $sp -Force -ErrorAction SilentlyContinue
    }
    C "no settings file reads 8765"               ((Get-RemotePort (Join-Path $env:TEMP "crow-selftest-absent.json")) -eq 8765)

    # -PathTracer (#298): the kit verdict, all three answers.
    $kd = Join-Path $env:TEMP ("crow-selftest-kit-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $kd | Out-Null
    try {
        $b = Join-Path $kd "crow-pathtracer.js"
        Set-Content -LiteralPath $b -Value "export const x = 1;" -Encoding ascii -NoNewline
        $h = (Get-FileHash -LiteralPath $b -Algorithm SHA256).Hash.ToLowerInvariant()
        Set-Content -LiteralPath (Join-Path $kd "kit.json") -Value ('{"bundle": {"sha256": "' + $h + '"}}') -Encoding ascii
        C "pathtracer: a bundle that matches kit.json is 'ok'" ((Test-PathTracerKit -KitDir $kd) -eq "ok")
        Set-Content -LiteralPath $b -Value "export const x = 2;" -Encoding ascii -NoNewline
        C "NEGATIVE: pathtracer: one changed byte is 'corrupt'" ((Test-PathTracerKit -KitDir $kd) -eq "corrupt")
    } finally {
        Remove-Item -LiteralPath $kd -Recurse -Force -ErrorAction SilentlyContinue
    }
    C "NEGATIVE: pathtracer: no kit is 'missing'" ((Test-PathTracerKit -KitDir (Join-Path $env:TEMP "crow-selftest-nokit")) -eq "missing")
    if ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot "kits\pathtracer\kit.json"))) {
        C "pathtracer: this checkout's kit matches its kit.json" ((Test-PathTracerKit -KitDir (Join-Path $PSScriptRoot "kits\pathtracer")) -eq "ok")
    }
    if ($PSCommandPath -and (Test-Path -LiteralPath $PSCommandPath)) {
        $me = Get-Content -LiteralPath $PSCommandPath -Raw
        C "pathtracer: the switch is declared and documented" (
            $me.Contains('[switch] $PathTracer') -and $me.Contains('.PARAMETER PathTracer'))
    }

    Write-Host ""
    $total = $script:sOk + $script:sRed
    if ($script:sRed -gt 0) { Write-Host "RESULT: $($script:sRed) of $total FAILED" -ForegroundColor Red; return 1 }
    Write-Host "RESULT: SELFTEST OK - $total checks" -ForegroundColor Green
    return 0
}

if ($Selftest) { Exit-Run (Invoke-Selftest); return }
# -Tailscale installs nothing and downloads nothing: it reads, prints the steps
# still missing and ends. Run after the install, on the machine that has it.
if ($Tailscale) { Show-TailscaleSteps; Exit-Run 0; return }

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "  Crow $Version" -ForegroundColor Cyan

Write-Step "Checking this machine"

$facts = Get-MachineFacts
Write-Item "GPU"      $(if ($facts.HasNvidiaSmi) { "$($facts.Gpu), $($facts.VramMb) MB" } else { "none detected" }) $(if ($facts.HasNvidiaSmi) { "ok" } else { "fail" })
Write-Item "RAM"      ((Format-Num $facts.RamGb) + " GB")
Write-Item "Disk"     ((Format-Num $facts.FreeDiskGb) + " GB free on " + (Split-Path $InstallTo -Qualifier))
Write-Item "Windows"  $(if ($facts.Is64Bit) { "64-bit, PowerShell $($facts.PsVersion)" } else { "32-bit" })
Write-Item "Python"   $(if ($facts.PythonPath) { $facts.PythonPath } else { "not on the PATH" }) `
                      $(if ($facts.PythonPath) { "ok" } else { "warn" })
# Reported even when it is missing, because the two clients differ in exactly this
# one prerequisite and a line that only appears on machines that have it would
# leave the other half wondering which client the install is short of.
Write-Item "WebView2" $(if ($facts.WebView2Version) { "$($facts.WebView2Version), the window renders in it" } else { "not found -- the terminal client does not need it" }) `
                      $(if ($facts.WebView2Version) { "ok" } else { "warn" })
Write-Item "Node"     $(if ($facts.NodePath) { "$($facts.NodePath), for MCP servers, the JS syntax check and build_bundle" } else { "not on the PATH -- MCP servers, the JS syntax check and build_bundle want it" }) `
                      $(if ($facts.NodePath) { "ok" } else { "warn" })
# SAID HERE AND NOT AT THE DOWNLOAD, for the reason at the top of this file: a
# cost first mentioned after the package has landed is a cost mentioned at the
# most expensive possible moment.
Write-Item "dictation" "$WHISPER_MB MB speech model, fetched in the last step" "ok"

$pf = Test-Preflight -VramMb $facts.VramMb -RamGb $facts.RamGb -FreeDiskGb $facts.FreeDiskGb `
                     -HasNvidiaSmi $facts.HasNvidiaSmi -Is64Bit $facts.Is64Bit -PsVersion $facts.PsVersion `
                     -PythonPath $facts.PythonPath -WebView2Version $facts.WebView2Version `
                     -NodePath $facts.NodePath

foreach ($w in $pf.Warnings) { Write-Item "warning:" $w "warn" }
if (-not $pf.Ok) {
    Write-Host ""
    foreach ($p in $pf.Problems) { Write-Item "cannot install:" $p "fail" }
    Write-Host ""
    Write-Host "  Nothing was downloaded." -ForegroundColor DarkGray
    Exit-Run 1
    return
}
Write-Item "preflight" "passed" "ok"

# Asked AFTER the preflight and only when it can matter: a machine that is about
# to be refused should not wait on a network call first, and a run pointed at a
# local package by -SourceUrl has already been told which bytes to install.
# An explicit -Version wins over the release -- somebody naming a version means it.
if (-not $PSBoundParameters.ContainsKey('Version') -and -not $SourceUrl) {
    $latest = Resolve-LatestVersion -Fallback $Version
    if ($latest -ne $Version) {
        Write-Item "release" "$latest is the newest published (this file defaults to $Version)" "ok"
        $Version = $latest
    }
}

Write-Step "Downloading the package"

$asset = "crow-$Version-win-x64.zip"
# Caught rather than thrown on: every other refusal in this script prints one
# line and exits 1, and a raw PowerShell error record here would be the only
# place a user meets a stack trace.
try {
    $source = Resolve-PackageSource -SourceUrl $SourceUrl -Asset $asset -Version $Version
} catch {
    Write-Item "cannot install:" $_.Exception.Message "fail"
    Write-Host ""
    Write-Host "  Nothing was downloaded." -ForegroundColor DarkGray
    Exit-Run 1
    return
}
Write-Item "from" $source.Uri
if ($source.IsLocal) {
    $tmp   = $source.Uri
    $bytes = (Get-Item -LiteralPath $tmp).Length
    Write-Item "local package" "nothing downloaded" "ok"
} else {
    $tmp   = Join-Path $env:TEMP $asset
    $bytes = Get-FileWithProgress -Uri $source.Uri -OutFile $tmp -Label $asset
}

$sha = (Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash
Write-Item "size"   (Format-Size $bytes) "ok"
Write-Item "sha256" $sha

Write-Step "Installing to $InstallTo"

if (Test-Path $InstallTo) {
    $existing = @(Get-ChildItem $InstallTo -ErrorAction SilentlyContinue).Count
    if ($existing -gt 0) {
        $decision = Resolve-InstallAction -Installed (Get-InstalledVersion $InstallTo) `
                                          -Target $Version -Force ([bool] $Force)
        switch ($decision.Action) {
            'uptodate' {
                Write-Item "already current" $decision.Message "ok"
                if ($PathTracer) {
                    Invoke-PathTracerKit -InstallTo $InstallTo -PythonPath $facts.PythonPath -Enable $true
                }
                Write-Host ""
                Write-Host "  Nothing was changed. Pass -Force to reinstall the same version." -ForegroundColor DarkGray
                Exit-Run 0
                return
            }
            'update'   { Write-Item "updating" $decision.Message "ok" }
            'install'  { Write-Item "overwriting" $decision.Message "ok" }
            default    {
                # 'unknown' and 'downgrade': both refuse, and both print a route
                # that a piped one-liner can actually take. `irm | iex` cannot be
                # given parameters, so "pass -Force" alone is advice nobody
                # reading it is able to follow.
                Write-Item "not installing" $decision.Message "fail"
                Write-Host ""
                Write-Host "  The one-liner cannot pass -Force. To force it:" -ForegroundColor DarkGray
                Write-Host "    &([scriptblock]::Create((irm $INSTALL_URL))) -Force" -ForegroundColor White
                Exit-Run 1
                return
            }
        }
    }
}
# NOTHING IS DELETED HERE, and that is not laziness. The last step of this
# script tells the user to fetch the model into $InstallTo\models -- 95.9 GiB
# that is not part of any package. An update that "cleaned" the target first
# would throw that away and re-download it over the user's connection. Files
# that a newer package no longer ships are therefore left behind; the manifest
# check below verifies what SHOULD be there, and says nothing about extras.
New-Item -ItemType Directory -Force -Path $InstallTo | Out-Null

# Windows locks a running executable and its loaded DLLs. An update started
# while the server is up -- which is exactly the state the user is in when the
# client prints the one-liner -- hits a locked file and fails with an
# IOException that nothing catches. The fix: rename locked files before
# extraction. Windows allows renaming a running binary; the process keeps its
# handle to the old name and the path is freed for the new file.
$binDir = Join-Path $InstallTo "bin"
$holder = if (Test-Path -LiteralPath $binDir) { Get-LockingServer -BinDir $binDir } else { $null }
if ($holder) {
    Write-Item "server running" "llama-server.exe (pid $($holder.Id)) is holding $binDir" "warn"
    $aside = Move-LockedAside -BinDir $binDir
    if ($aside.Moved -gt 0) {
        Write-Item "moved aside" "$($aside.Moved) files renamed -- the running server keeps the old ones" "ok"
    }
    # Stopping here rather than letting the extraction discover it: below, the
    # same condition arrives as an IOException with a filename in it and no idea
    # why, and the user has already waited for a download by then.
    if ($aside.Failed.Count -gt 0) {
        Write-Item "could not move" "$($aside.Failed -join ', ')" "fail"
        Write-Item "stop llama-server and run this again" "those files cannot be overwritten while they are held" "fail"
        Exit-Run 1
        return
    }
}

# Read BEFORE extraction: the archive overwrites MANIFEST.json, and after that
# there is no record left of what the previous package put here. Without this the
# removal step below has to guess from the directory contents, which is how it
# deleted a user's own backup folder on 2026-08-10.
$previousManifest = @()
$prevPath = Join-Path $InstallTo "MANIFEST.json"
if (Test-Path -LiteralPath $prevPath) {
    try {
        $previousManifest = @((Get-Content -LiteralPath $prevPath -Raw | ConvertFrom-Json) |
                              ForEach-Object { $_.path })
    } catch {
        # A manifest we cannot read means we do not know what the last package
        # left. Saying so and removing nothing is the only safe answer.
        Write-Item "previous MANIFEST.json unreadable" "nothing will be removed this run" "warn"
        $previousManifest = @()
    }
}

try {
    $n = Expand-WithProgress -ZipPath $tmp -Destination $InstallTo
} catch [System.IO.IOException] {
    $lockedFile = $_.Exception.Message
    Write-Item "extraction failed" "a file is still locked: $lockedFile" "fail"
    Write-Host ""
    Write-Item "try again after stopping llama-server" "or restart your machine to release all file handles" "fail"
    Exit-Run 1
    return
} catch {
    Write-Item "extraction failed" "$($_.Exception.Message)" "fail"
    Exit-Run 1
    return
}
# Only what this script downloaded. A package handed in with -SourceUrl belongs
# to the caller, and deleting it would eat the artefact being tested.
if (-not $source.IsLocal) { Remove-Item $tmp -Force }
Write-Item "installed" "$n files" "ok"

Write-Step "Verifying what landed"

# This is the only real check in the run, and until 2026-08-08 it did not exist.
# Measured that day: Expand-Archive extracts a zip with a flipped byte WITHOUT an
# error and writes the wrong bytes to disk -- three offsets inside the compressed
# stream, three silent successes. TLS covers the wire and nothing covered the
# file, so a damaged install would have surfaced later as a DLL that will not
# load, and been diagnosed as anything but a bad download.
#
# The package carries a hash per file. Reading it is the whole fix.
$manifestPath = Join-Path $InstallTo "MANIFEST.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Item "MANIFEST.json" "not in the package -- nothing to verify against" "fail"
    Exit-Run 1
    return
}

$entries = @()
foreach ($e in (Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json)) {
    # -LiteralPath throughout: two of the shipped files are named
    # GoogleSansCode[MONO,wght].ttf, and Test-Path reads [...] as a wildcard.
    # A check that reports those two as missing on every single install would
    # have been worse than no check at all.
    $file = Join-Path $InstallTo $e.path
    $actual = if (Test-Path -LiteralPath $file) {
        (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    } else { $null }
    $entries += [pscustomobject]@{ Path = $e.path; Expected = $e.sha256; Actual = $actual }
}

$verdict = Compare-Manifest $entries
if (-not $verdict.Ok) {
    foreach ($p in $verdict.Missing)    { Write-Item "missing" $p "fail" }
    foreach ($p in $verdict.Mismatched) { Write-Item "corrupt" $p "fail" }
    Write-Host ""
    Write-Item "the install is damaged" "delete $InstallTo and run this again" "fail"
    Exit-Run 1
    return
}
Write-Item "sha256 per file" "$($verdict.Checked) of $($verdict.Checked) match" "ok"

# The other direction. Everything above walks the manifest and asks the disk; a
# file the package USED to ship and no longer does is invisible to it and stays
# forever. Order matters and is the same as everywhere else here: the files were
# written and read back first, and only a verified install gets anything deleted.
#
# Both lists are manifests, never a directory listing. A file this installer did
# not put here is not in either one and cannot be selected -- which is the entire
# difference to the version that deleted a user's backup folder.
$drop = Find-DroppedFiles -PreviousPaths $previousManifest -CurrentPaths $entries.Path
$targets = @($drop.Dropped | Where-Object { Test-Path -LiteralPath (Join-Path $InstallTo $_) })
foreach ($rel in $targets) {
    Remove-Item -LiteralPath (Join-Path $InstallTo $rel) -Force -ErrorAction SilentlyContinue
}
# Counted by looking afterwards, not by counting what was found -- the same
# lesson as Remove-StaleOld below: a locked or read-only file survives the call
# without raising, and reporting it as removed prints a green line for work that
# did not happen.
$stillThere = @($targets | Where-Object { Test-Path -LiteralPath (Join-Path $InstallTo $_) })
$gone = $targets.Count - $stillThere.Count
if ($gone -gt 0) {
    Write-Item "removed" "$gone files the previous package left, of $($drop.Checked) it had installed" "ok"
}
if ($stillThere.Count -gt 0) {
    Write-Item "could not remove" "$($stillThere.Count) of $($targets.Count): $($stillThere -join ', ')" "warn"
}
if ($targets.Count -eq 0) {
    # With the denominator, always. Without it this line is indistinguishable
    # from a run that had no previous manifest to compare against at all.
    Write-Item "nothing to remove" "$($drop.Checked) files the previous package installed are all still shipped" "ok"
}

# The .old files from the rename above. The ones the running server still has
# mapped cannot be deleted -- and that is the normal case, because the reason
# they were renamed is that it is still running. So the counts come from looking
# afterwards, and what stays is said out loud rather than counted as removed.
if (Test-Path -LiteralPath $binDir) {
    $swept = Remove-StaleOld -BinDir $binDir
    if ($swept.Removed -gt 0) {
        Write-Item "cleaned" "$($swept.Removed) stale .old files removed" "ok"
    }
    if ($swept.Kept.Count -gt 0) {
        Write-Item "still held" "$($swept.Kept.Count) .old files stay until llama-server stops" "warn"
    }
}

# --slot-save-path refuses to start against a path that is not an existing
# directory, so the server would fail on the very command this script prints.
# Created here rather than by the client, because the server needs it first.
New-Item -ItemType Directory -Force -Path (Join-Path $InstallTo "session") | Out-Null

# THE WINDOW'S ONE DEPENDENCY, and the only thing this installer puts anywhere
# outside its own directory. It runs HERE and not in the preflight because it
# cannot be answered earlier: whether pip may write into the interpreter this
# machine happens to have is knowable only by trying.
#
# A FAILURE DOES NOT END THE INSTALL. The terminal client is complete without
# it, everything downloaded is already on disk and verified, and the one thing
# the user needs in that case is the command that finishes the job by hand --
# printed with the interpreter's real path, because `pip` alone on the PATH can
# be a different Python than the one Crow will run.
if ($facts.PythonPath) {
    Write-Host ""
    Write-Host "  pywebview  the window needs it; installing into $($facts.PythonPath)" -ForegroundColor DarkGray
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $facts.PythonPath -m pip install --disable-pip-version-check --quiet pywebview 2>&1 |
            ForEach-Object { }
        $pipRc = $LASTEXITCODE
    } catch {
        $pipRc = 1
    } finally {
        $ErrorActionPreference = $prevEap
    }
    # The 255 lesson, third time: a failed pip must not become this script's
    # exit code on an install that otherwise landed.
    $global:LASTEXITCODE = 0
    if ($pipRc -eq 0) {
        Write-Item "pywebview" "installed" "ok"
    } else {
        Write-Item "pywebview" "could not be installed -- the terminal client is unaffected" "warn"
        Write-Host "             $($facts.PythonPath) -m pip install pywebview" -ForegroundColor White
    }
}

# ---------------------------------------------------------------------------
# The window's microphone: two packages, then one model
# ---------------------------------------------------------------------------
# A SECOND BLOCK AND NOT A WIDER FIRST ONE. Four selftest checks read the
# pywebview step above by its exact source text; adding two package names to
# its pip line would have broken all four to save six lines here. The two also
# fail differently -- without pywebview there is no window, without these there
# is a window that cannot listen.
if ($facts.PythonPath) {
    Write-Host ""
    Write-Host "  dictation  the microphone needs faster-whisper and sounddevice" -ForegroundColor DarkGray
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $facts.PythonPath -m pip install --disable-pip-version-check --quiet faster-whisper sounddevice 2>&1 |
            ForEach-Object { }
        $micRc = $LASTEXITCODE
    } catch {
        $micRc = 1
    } finally {
        $ErrorActionPreference = $prevEap
    }
    $global:LASTEXITCODE = 0
    if ($micRc -eq 0) {
        Write-Item "dictation" "faster-whisper and sounddevice installed" "ok"
    } else {
        Write-Item "dictation" "could not be installed -- typing is unaffected" "warn"
        Write-Host "             $($facts.PythonPath) -m pip install faster-whisper sounddevice" -ForegroundColor White
    }
}

# THE MODEL ITSELF, FOUR FILES. Fetched here rather than left to the first
# click, because faster-whisper would otherwise pull the same bytes into a
# HuggingFace cache the moment somebody presses the button: a silent wait,
# inside a window, on a machine whose owner believed the install had finished.
# cli/crow_voice.py looks in this directory FIRST and only falls back to that
# cache when it is empty.
#
# SMALLEST FILES FIRST, so a host that is refusing today costs three seconds
# rather than most of 486 MB before it says so. A file already on disk is left
# alone -- a re-install is not a second download -- and a failure here is a
# warning, not an end: everything else has landed, and the window opens with a
# microphone that names what is missing.
if ($InstallTo) {
    $whisperDir = Join-Path (Join-Path $InstallTo "models") $WHISPER_DIRNAME
    New-Item -ItemType Directory -Force -Path $whisperDir | Out-Null
    $whisperOk = $true
    foreach ($f in @("config.json", "vocabulary.txt", "tokenizer.json", "model.bin")) {
        $dest = Join-Path $whisperDir $f
        if (Test-Path -LiteralPath $dest) { continue }
        try {
            # $null =, because Get-FileWithProgress RETURNS the byte count and an
            # unassigned call drops it straight onto the console: the first live run
            # printed a bare 483546902 between two progress lines. The package
            # download above catches it in $bytes for the size check; here there is
            # nothing to compare it against, so it goes nowhere.
            $null = Get-FileWithProgress -Uri "https://huggingface.co/$WHISPER_REPO/resolve/main/$f" `
                                         -OutFile $dest -Label "speech model: $f"
        } catch {
            $whisperOk = $false
            break
        }
    }
    $global:LASTEXITCODE = 0
    if ($whisperOk) {
        Write-Item "dictation model" "$WHISPER_DIRNAME is in place" "ok"
    } else {
        Write-Item "dictation model" "not fetched -- everything else installed" "warn"
        Write-Host "             the window downloads it on the first click instead" -ForegroundColor White
    }
}

Invoke-PathTracerKit -InstallTo $InstallTo -PythonPath $facts.PythonPath -Enable ([bool] $PathTracer)

Write-Step "What is left to do"

# The python line that used to stand here has MOVED, it was not dropped: it is
# a Write-Item in step 1 now, beside the Tk line it belongs with, because a
# prerequisite reported after the 506 MB download is a prerequisite reported at
# the most expensive possible moment. See the two Write-Item calls under
# "Checking this machine" and the warnings Test-Preflight raises for them.

Write-Host ""
# THE DEFAULT OPERATING POINT IS crow-nest (Rust), port 8099. Its own repository
# and its own build, so these steps are printed and none of them is run here.
# Commands as in crow-nest's README. This block names no engine binary of the
# llama.cpp line on purpose: tools/check_operating_point.py anchors on that name.
Write-Host "  Default: crow-nest (Rust engine), port 8099" -ForegroundColor White
Write-Host ""
Write-Host "  1. Engine and model. The container is 104.7 GB, one file:" -ForegroundColor DarkGray
Write-Host ""
Write-Host "    git clone https://github.com/nibor1896/crow-nest; cd crow-nest" -ForegroundColor White
Write-Host "    hf download nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M Qwen3.8-Flash-Next-CNQ4.5-M.cnq --local-dir converter" -ForegroundColor White
Write-Host "    cd engine; cargo build --release --bin serve; cd .." -ForegroundColor White
Write-Host ""
Write-Host "     Needs an NVIDIA Blackwell card (sm_120, 32 GB), 64 GB RAM and the CUDA 13.3 runtime." -ForegroundColor DarkGray
Write-Host ""
Write-Host "  2. Start the engine, then the window:" -ForegroundColor DarkGray
Write-Host ""
Write-Host "    engine\target\release\serve.exe --port 8099" -ForegroundColor White
Write-Host "    python $InstallTo\cli\crow.py --base-url http://127.0.0.1:8099/v1" -ForegroundColor White
Write-Host "     or the window:" -ForegroundColor DarkGray
Write-Host "    python $InstallTo\cli\crow_gui.py --base-url http://127.0.0.1:8099/v1" -ForegroundColor White
Write-Host ""
Write-Host "  Second: llama.cpp" -ForegroundColor White
Write-Host ""
Write-Host "  1. The model. It is NOT part of this install: 16.4 GiB, one file, and it" -ForegroundColor DarkGray
Write-Host "     belongs to somebody else." -ForegroundColor DarkGray
Write-Host ""
Write-Host "       Qwen3.8-27B, quantised by unsloth to UD-Q4_K_XL" -ForegroundColor White
Write-Host "       https://huggingface.co/unsloth/Qwen3.8-27B-GGUF" -ForegroundColor DarkGray
Write-Host ""
Write-Host "    hf download unsloth/Qwen3.8-27B-GGUF --include '*UD-Q4_K_XL*' --local-dir $InstallTo\models\qwen38-gguf" -ForegroundColor White
# A SECOND LINE BECAUSE THE GLOB ABOVE DOES NOT CATCH IT. mmproj-F16.gguf is the
# vision projector (#142) -- without it the server boots the same model as a
# text-only one, silently. Found on 2026-08-27 when the measurement had to fetch
# the file the documented download had never brought.
Write-Host "    hf download unsloth/Qwen3.8-27B-GGUF mmproj-F16.gguf --local-dir $InstallTo\models\qwen38-gguf" -ForegroundColor White
Write-Host ""
# Measured 2026-08-07 on the other model, and it is the same tool: when hf cannot
# reach the repository it prints a tick and returns the local directory. Failure
# that looks like success is worth one line here, because the next thing the user
# does is start a server against nothing.
Write-Host "     If that finishes suspiciously fast, check that one file of" -ForegroundColor DarkGray
Write-Host "     17,559,178,144 B and one of 927,607,488 B arrived -- hf reports success" -ForegroundColor DarkGray
Write-Host "     even when it reached nothing." -ForegroundColor DarkGray
Write-Host ""
# -ctk/-ctv q8_0 and not f16: measured 2026-08-20, f16 KV leaves 332.8 MiB of the
# card free, a third of the 924 MiB at which this project has documented losses
# starting. q8_0 leaves 6,627. No --moe-stream: 16.4 GB dense, it fits whole and
# there are no expert tensors to route. No --chat-template-file: unlike 0731 the
# embedded template is the correct one.
Write-Host "  2. Then start the server, and the client in a second terminal:" -ForegroundColor DarkGray
Write-Host ""
Write-Host "    $InstallTo\bin\llama-server.exe -m $InstallTo\models\qwen38-gguf\Qwen3.8-27B-UD-Q4_K_XL.gguf ``" -ForegroundColor White
# NOT ON THE LAST LINE, same rule as --slot-save-path below: the value is a path
# and a path at the closing quote reaches the checker with the quote glued on.
Write-Host "      --mmproj $InstallTo\models\qwen38-gguf\mmproj-F16.gguf ``" -ForegroundColor White
Write-Host "      --port 8082 -c 200000 -ctk q8_0 -ctv q8_0 -ngl 99 -np 1 ``" -ForegroundColor White
# --slot-save-path IS NOT ON THE LAST LINE, and that is not layout. The checker
# reads this file as text and captures the path with \S+, so a value ending at
# the closing quote of a Write-Host comes back as `session"` and the flag reads
# as pointing somewhere it does not. Caught by the checker on the first run of
# this block. Anything that ends a printed command line must be a flag with no
# value, or a number.
Write-Host "      --slot-save-path $InstallTo\session ``" -ForegroundColor White
# NOT LAST, for the reason above: this flag carries a VALUE, and a value sitting
# at the closing quote comes back to the checker with the quote glued on. The
# jinja flag ends the block because it has nothing after it to swallow.
#
# Written without naming the flags in prose on purpose -- this file's own
# comments have been matched by the checker's regexes before.
Write-Host "      --spec-type draft-mtp ``" -ForegroundColor White
Write-Host "      --jinja" -ForegroundColor White
Write-Host ""
# 8082 rather than 8081, so the client has to be told -- and being told is the
# point: the port is what says which model answered.
Write-Host "    python $InstallTo\cli\crow.py --base-url http://127.0.0.1:8082/v1" -ForegroundColor White
Write-Host ""
# BOTH CLIENTS ARE INSTALLED AND NEITHER IS THE DEFAULT. The terminal one is
# printed first because it needs nothing but python; the window is printed second
# because it needs WebView2 as well, and step 1 has already said whether this
# machine has it.
Write-Host "     Or the same conversation in a window, if pywebview installed above:" -ForegroundColor DarkGray
Write-Host ""
Write-Host "    python $InstallTo\cli\crow_gui.py" -ForegroundColor White
Write-Host ""
Write-Host "     Same core, same session file, same server. Neither client wraps the other," -ForegroundColor DarkGray
Write-Host "     and neither is needed to use the other." -ForegroundColor DarkGray
Write-Host ""
# THE SECOND MODEL, AND IT IS PRINTED EVEN THOUGH THE INSTALLER DOES NOT FETCH IT.
# It is still shipped -- the binaries, the verified chat template and every flag
# below -- it is simply no longer the model this installer leads with. A line
# nobody runs today is still a line somebody copies the day they do, and an
# uncopied line is how the vault page ended up without --slot-save-path on
# 2026-08-10 while README.md and this file had it.
#
# THIS BLOCK NOW SITS LAST, AND THAT MOVED THE CHECKER'S REGION WITH IT. The
# 2000-character window opens at the "llama-server" printed below and runs to the
# end of this section, so --moe-stream-l2 has MORE room than it had when a second
# server block followed it, not less. The selftest measures the real distance
# rather than trusting that sentence.
#
# WHY --moe-stream-cache SAYS 58 AND NOT 64, and this note sits HERE rather than beside the flag on
# purpose: a long comment INSIDE that window pushes the last flags out of it and reports this
# installer as broken. Measured the hard way on 2026-08-11, which is also when the number changed.
#
# A slot costs 360.69 MiB on 0731 -- the server prints the cache size at every step and the figure is
# constant to five digits. Past a point the allocation no longer fits beside what the display holds,
# the driver moves the difference into host memory without printing anything, and the cost is not a
# constant slowdown but an unpredictable one: single requests halve at random, with identical graph
# executions, identical misses and the LOWEST load stall of the run.
#
# Measured 2026-08-11, with the number of runs behind each cell, VRAM read after load of 32,607 MiB:
#   64 -> prefill 15.28 median of 8, spread 8.69x / no decode series / 32,014 used /   593 free
#   62 -> 114.92 median of 5 / 14.62 median of 4, one request at 7.07 / 31,683      /   924
#   60 -> 113.53 median of 5 / 17.43 median of 8                     / 30,954      / 1,653
#   58 -> 112.69 median of 3 / 17.32 median of 8                     / 30,548      / 2,059  <- shipped
#   56 -> 110.30 median of 3 / 17.09 median of 8                     / 29,842      / 2,765
#
# THE ARITHMETIC IS THE EVIDENCE. 62 reads 31,683 and 60 reads 30,954 -- 729 MiB for two slots,
# against the 721 the printed slot size predicts. So 64 must read about 32,404, and it reads 32,014.
# Those 390 MiB are the ones the driver moved out. 58 against 60 is NOT a throughput difference
# (112.69 vs 113.53, 17.32 vs 17.43, while repeating one configuration eight times spans 1.09x);
# what separates them is the margin.
#
# THIS NUMBER IS DERIVED FROM 32,607 MiB OF VRAM AND WHATEVER THE DISPLAY HOLDS BESIDE IT. A smaller
# card, or a busier display, needs a smaller value. Deriving it from the machine the way
# --moe-stream-l2 is derived is tracked as #87 rather than guessed at here.
Write-Host "  3. Or the second model, DeepSeek-V4-Flash-0731 -- a separate 84.6 GiB" -ForegroundColor DarkGray
Write-Host "     download, not installed here:" -ForegroundColor DarkGray
Write-Host ""
Write-Host "    hf download unsloth/DeepSeek-V4-Flash-0731-GGUF --include 'UD-IQ2_XXS/*' --local-dir $InstallTo\models" -ForegroundColor White
Write-Host ""
Write-Host "    $InstallTo\bin\llama-server.exe -m $InstallTo\models\UD-IQ2_XXS\DeepSeek-V4-Flash-0731-UD-IQ2_XXS-00001-of-00003.gguf ``" -ForegroundColor White
# --jinja is not optional here. Without it llama-server uses its own built-in
# template instead of the model's, the client's replayed reasoning is dropped,
# and the prompt cache breaks on every turn -- measured 2026-08-08, 138.8-242.3 s
# of re-prefill per turn against 1.6-2.2 s.
Write-Host "      --port 8081 -c 200000 -ngl 99 -np 1 --jinja ``" -ForegroundColor White
# --slot-save-path is what lets a session survive at all. Without it the client
# can keep its messages but not the server's KV cache, and the next start pays a
# full prefill for the whole history -- measured 2026-08-08: 23,400 tokens took
# about 35 minutes, while restoring the same state took 22 ms.
Write-Host "      --slot-save-path $InstallTo\session ``" -ForegroundColor White
# 0731 ships no Jinja chat template, and the one embedded in the GGUF fails the
# model's own golden vector 4 (an action turn opens a think block it never
# closes). The verified template ships with this package; without the flag the
# server silently uses the embedded one and nothing looks wrong.
Write-Host "      --chat-template-file $InstallTo\templates\0731-chat-template.jinja ``" -ForegroundColor White
# 58 and not 64 -- the reason is above the block, outside the region the checker reads.
#
# The host-RAM tier is printed only on a machine with the RAM it was measured on. On anything
# smaller the line is left out entirely rather than carrying a smaller, unmeasured number - a flag
# in the command people copy is a recommendation, and this project does not recommend figures it
# has not run.
$l2 = Get-L2Gib -RamGb $facts.RamGb
if ($l2 -gt 0) {
    Write-Host "      --moe-stream --moe-stream-cache 58s --moe-stream-io-threads 8 --moe-stream-direct ``" -ForegroundColor White
    Write-Host "      --moe-stream-l2 $l2" -ForegroundColor White
} else {
    Write-Host "      --moe-stream --moe-stream-cache 58s --moe-stream-io-threads 8 --moe-stream-direct" -ForegroundColor White
}
Write-Host ""
Write-Host "    python $InstallTo\cli\crow.py" -ForegroundColor White
Write-Host ""

# THE THIRD MODEL (#140), PRINTED AND NOT FETCHED, same rule as the second: an
# uncopied line is a stale line the day somebody needs it. Still a LOCAL build
# by absolute path, but NO LONGER A FORK: PR #27742 merged into mainline on
# 2026-08-29, and this command names that merge commit (6c84c7d5d). The SHIPPED
# bin\llama-server.exe still cannot load the architecture -- it is b10269 from
# 2026-08-06 -- which is why the line points elsewhere at all.
# THE PIN CARRIES TWO PATCHES, both measured 2026-09-01 on this exact line,
# interleaved against a same-session control (Crow #159):
#   PR #28040 -- get_prev_tokens in O(log n) from the sequence position index,
#     instead of a scan over every used KV cell once per decoded token. It
#     replaced the closed draft #27992 at parity: fixed term +0.6 % against
#     1.335 ms of spread inside one arm. Ported by hand, 9 of 10 hunks.
#   PR #27880 -- the PLE embedding hoisted out of the per-layer loop into the
#     token embedding's graph split: 62 splits per decoded token instead of 64,
#     -0.99 ms on the fixed term in the one clean pair, inside the 1.35 ms
#     spread of one arm. Free and not worse. Merged upstream, applies cleanly.
# THE COMMIT IS STILL PINNED, AND THE REASON CHANGED ON 2026-09-01: b10687, one
# day younger, dies with 'MUL_MAT failed' during CUDA warmup. That was blamed on
# #27880 -- wrongly: #27880 isolated on this pin boots, warms up and serves.
# Whatever kills b10687 lives elsewhere in that day of mainline and is not
# attributed, so the pin does not move.
# Flags match manifests/operating-point.json.
Write-Host "  Third model, Qwen3.8-Flash-Next (#140) -- 73.45 GiB in 3 shards, mainline 6c84c7d5d + PR #28040 + PR #27880:" -ForegroundColor DarkGray
Write-Host ""
Write-Host "    hf download unsloth/Qwen3.8-Flash-Next-GGUF --include '*UD-Q2_K_XL*' --local-dir $InstallTo\models\qwen-next-gguf" -ForegroundColor White
# THE PROJECTOR SITS IN THE REPOSITORY ROOT, not in the quant folder, so the
# glob above walks straight past it -- the same second line the 27B needs, for
# the same reason (#170).
Write-Host "    hf download unsloth/Qwen3.8-Flash-Next-GGUF mmproj-F16.gguf --local-dir $InstallTo\models\qwen-next-gguf" -ForegroundColor White
Write-Host ""
Write-Host "    C:\Users\robin\dev\crow-lab\wt-27880\build-27880\bin\Release\llama-server.exe ``" -ForegroundColor White
Write-Host "      -m $InstallTo\models\qwen-next-gguf\UD-Q2_K_XL\Qwen3.8-Flash-Next-UD-Q2_K_XL-00001-of-00003.gguf ``" -ForegroundColor White
Write-Host "      --port 8083 -c 200000 -b 2048 -ub 2048 ``" -ForegroundColor White
Write-Host "      -ctk q8_0 -ctv q8_0 -ncmoe 30 ``" -ForegroundColor White
Write-Host "      --fit off --load-mode none -np 1 ``" -ForegroundColor White
Write-Host "      --mmproj $InstallTo\models\qwen-next-gguf\mmproj-F16.gguf ``" -ForegroundColor White
Write-Host "      --jinja" -ForegroundColor White
Write-Host ""
# DER STANDARD BRAUCHT KEIN --base-url MEHR, seit 2.0.0 zeigt DEFAULT_BASE_URL
# auf 8083. Eine Zeile, die den Standard noch einmal ausschreibt, liest sich wie
# eine Bedingung.
Write-Host "    python $InstallTo\cli\crow.py" -ForegroundColor White
Write-Host ""

# The phone from anywhere: -Tailscale prints the missing steps without
# reinstalling anything (#249 stage 5).
Write-Host "  The phone from anywhere (HTTPS over Tailscale) -- what is still missing:" -ForegroundColor DarkGray
Write-Host ""
Write-Host "    &([scriptblock]::Create((irm $INSTALL_URL))) -Tailscale" -ForegroundColor White
Write-Host ""

# The last screen is the only place these four commands appear -- the model, the
# server, and one start line per client -- and a console that was opened for the
# install closes with it. So the run ends on a keypress rather than on its own --
# measured the hard way on 2026-08-08, when the first public install finished
# correctly and the window was gone before anyone could read what it had just
# printed.
#
# Skipped when there is nobody to press it: -NoPause for a script driving this,
# and UserInteractive for a host with no console at all. A wait that cannot be
# satisfied is not a safety net, it is a hang.
if (-not $NoPause -and [Environment]::UserInteractive) {
    Write-Host "  Press ENTER to finish." -ForegroundColor DarkGray
    try { [void](Read-Host) } catch { }
    Write-Host ""
}

# Said out loud rather than inherited. Without this the run ends with whatever
# the last native call left in $LASTEXITCODE, which is how a finished install
# came to report 255. Every failure path above sets 1 explicitly, so reaching
# this line means it worked.
Exit-Run 0
