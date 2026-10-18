#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build-sd-server.sh -- build the Crow CUDA image server for Linux, no root
# ---------------------------------------------------------------------------
#
# WHAT
#   Produces $CROW_HOME/bin/sd-server and $CROW_HOME/bin/sd-cli: the CUDA
#   stable-diffusion.cpp binaries behind generate_image (and edit_image while
#   the image model was Qwen-Image 2.1; Ming-Image has no edit path)
#   (crow_core.image_server_binary(), #300 phase 3, #308, #311), built for
#   Blackwell (sm_120, RTX 5090) from a pinned tree. Before #314 no installer
#   provided them: the tools worked on robin's machine only because sd-server
#   2f88688 had been copied into ~/.local/share/crow/bin by hand on 2026-09-27.
#
#   It reuses what tools/build-llama-server.sh already put under $CROW_HOME:
#   the CUDA 13.3.1 prefix in $CROW_HOME/cuda and cmake/ninja in
#   $CROW_HOME/venv-build. That script is SOURCED for ensure_cmake_ninja and
#   ensure_cuda, so a machine that built llama-server downloads nothing for the
#   toolkit here, and a machine that did not gets the same ~970 MB component
#   download, from the same code, into the same place. One toolkit, one copy
#   of the fetch logic. Its "WHY CUDA 13.3", "HOST COMPILER" and "CUDA RUNTIME
#   PINNING" blocks hold for this build unchanged.
#
# WHY THIS PIN
#   stable-diffusion.cpp 2f016e8e30ab0d0051c268944ae96c0951dba4f0, tag
#   master-970-2f016e8 (2026-10-16), for Ming-Image 0.1 Design (#400, #402).
#   Ming-Image support landed in f8890b9 (PR #2063, 2026-09-27): the Ling-mini-2.0
#   text encoder, the DiT and the RGBA VAE, text-to-image only -- there is no
#   reference-image edit path for it. The head commit, 2f016e8 (PR #2145), makes
#   sd-cli and sd-server open UTF-8 file paths on Windows.
#   The previous pin, 2f88688 (master-920-2f88688), is four commits before
#   f8890b9 and has no Ming-Image code. It is the tree every Qwen-Image 2.1
#   measurement in #300 phase 3 was taken on (G1, G2, E1-E3, B4, B5), built by
#   hand on 2026-09-26 as ~/.local/share/crow/src/stable-diffusion.cpp-2f88688
#   (cmake.log there; the blocks below cite it).
#   NOTHING WAS MEASURED ON THIS TREE YET: no image, no speed, no memory line.
#   As with llama.cpp: a newer tree is a different engine, and the 2f88688
#   numbers do not carry over. On 2026-10-18 it was compiled on Windows with
#   the recipe in docs/user-guide/install.md (no weights loaded); this script
#   has not been run at this pin.
#
#   The submodules at that pin, read from the git tree of 2f016e8 -- the same
#   four paths and .gitmodules as at 2f88688, ggml and the frontend moved -- and
#   checked against the tree on every run (verify_src):
#       ggml                      d25b121ce1d6ae0c7e62ad080460d9fc1e46dd93
#       thirdparty/libwebp        0c9546f7efc61eac7f79ae115c3f99c91c21c443
#       thirdparty/libwebm        5bf12267eea773a32fcf4949de52b0add158a8d5
#       examples/server/frontend  8e7c11505925c0dbf9aaea56a3a5058b8690d66b
#   The first three are compiled in. The frontend is recorded and NOT fetched;
#   see WHY NO FRONTEND. ggml d25b121 is the head of no leejet/ggml branch, so
#   `git submodule update` fetches it by SHA, as it did 4bf5f60 before.
#
# WHY NO FRONTEND (SD_SERVER_BUILD_FRONTEND=OFF)
#   examples/server/CMakeLists.txt builds the web UI with `pnpm install` +
#   `pnpm run build` at build time when pnpm is on PATH -- a network fetch of
#   the node dependency tree in the middle of a compile -- and embeds the
#   result as HAVE_INDEX_HTML. Without pnpm and without a pre-built
#   dist/gen_index_html.h it warns and builds the server with no page at "/".
#   The measured 2026-09-26 build is exactly that case ("pnpm not found;
#   frontend build disabled.", cmake.log), and Crow only speaks the HTTP API
#   (/sdcpp/v1/..., crow_core). OFF gives the same binary on every machine,
#   pnpm or not, and needs neither node nor the frontend submodule.
#
# CONFIGURE LINE
#   The 2026-09-26 hand build, reproduced: Release, SD_CUDA=ON,
#   CMAKE_CUDA_ARCHITECTURES=120 (ggml turns it into 120a: "Replacing 120 in
#   CMAKE_CUDA_ARCHITECTURES with 120a", cmake.log), nvcc from $CROW_HOME/cuda,
#   -allow-unsupported-compiler (gcc 16.2.1), GGML_NATIVE on, static libs.
#   Added, as in build-llama-server.sh: Ninja, CUDAToolkit_ROOT and a DT_RPATH
#   to $CROW_HOME/cuda/lib. The hand build had no RPATH and started only with
#   LD_LIBRARY_PATH=<data>/cuda/lib (measured 2026-09-27, _image_server_env);
#   with the RPATH the binary finds its own runtime, and the variable Crow
#   still sets is harmless.
#
# USAGE
#   tools/build-sd-server.sh                   # full build, reuses everything
#   JOBS=8 tools/build-sd-server.sh            # gentler on the machine
#   CLEAN=1 tools/build-sd-server.sh           # nuke the build dir first
#   SD_SRC_DIR=<tree> tools/build-sd-server.sh # build an existing checkout of
#                                              # the pin; it is verified, and
#                                              # left alone when it matches
#   SD_RELEASE=1 tools/build-sd-server.sh      # the binary Crow's Linux package
#                                              # ships (#342): see RELEASE BUILD
#
# RELEASE BUILD (SD_RELEASE=1, #342)
#   The local build is for this machine: GGML_NATIVE, and a DT_RPATH to the
#   absolute $CROW_HOME/cuda/lib -- 236 builder-path hits in the 2026-09-27
#   binary, which tools/pack-release.sh refuses. The release build differs in
#   exactly three ways and lands in its own build dir and $SD_OUT_DIR (default
#   $CROW_HOME/build/sd-release), never in bin/:
#   * RPATH $ORIGIN/../cuda/lib -- the installed layout <root>/bin/sd-server
#     beside <root>/cuda/lib. $SD_OUT_DIR/cuda links to $CROW_HOME/cuda so the
#     verification resolves the libraries the same way.
#   * -ffile-prefix-map for $HOME, the source and the build dir (C, C++ and
#     nvcc's host compiler), so __FILE__ and debug paths carry no home.
#   * GGML_NATIVE off with AVX, AVX2, FMA and F16C on (x86-64-v3, Haswell and
#     later): -march=native would bake the build CPU into a binary that runs
#     elsewhere. The text encoder runs on the CPU (te=cpu), so the floor is
#     v3 and not baseline x86-64.
#
# Idempotent: a re-run after a completed build fetches nothing, lets ninja find
# nothing to do, leaves identical binaries in bin/ untouched and re-runs the
# verification. An sd-cli or sd-server of ANOTHER commit already in bin/ is
# kept as sd-cli-<commit> / sd-server-<commit>, never deleted.
# ---------------------------------------------------------------------------

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# say, run, ensure_cmake_ninja, ensure_cuda and the CUDA_* layout. Sourcing runs
# nothing: the llama builder calls main only when executed.
# shellcheck source-path=SCRIPTDIR source=build-llama-server.sh
. "$HERE/build-llama-server.sh"

# --- parameters ------------------------------------------------------------
SD_PIN="${SD_PIN:-2f016e8e30ab0d0051c268944ae96c0951dba4f0}"
SD_TAG="${SD_TAG:-master-970-2f016e8}"
# path:sha at SD_PIN. BUILT ones are fetched and checked out; the rest are
# only checked against the pin's tree.
SD_SUBMODULES_BUILT="ggml:d25b121ce1d6ae0c7e62ad080460d9fc1e46dd93
thirdparty/libwebp:0c9546f7efc61eac7f79ae115c3f99c91c21c443
thirdparty/libwebm:5bf12267eea773a32fcf4949de52b0add158a8d5"
SD_SUBMODULES_RECORDED="examples/server/frontend:8e7c11505925c0dbf9aaea56a3a5058b8690d66b"
SD_UPSTREAM="${SD_UPSTREAM:-https://github.com/leejet/stable-diffusion.cpp.git}"

SD_SRC_DIR="${SD_SRC_DIR:-$CROW_HOME/src/stable-diffusion.cpp-${SD_PIN:0:7}}"
# Per pin, and outside the source tree like llama-cuda. NOT build/sd-cuda: on
# robin's machine that directory holds the 137f740 build (#206) of a different
# source dir, and CMake refuses a cache made for another source.
SD_BUILD_DIR="$CROW_HOME/build/sd-cuda-${SD_PIN:0:7}"
SD_TARGETS="sd-cli sd-server"
SD_RELEASE="${SD_RELEASE:-0}"
if [ "$SD_RELEASE" = "1" ]; then
    SD_BUILD_DIR="$SD_BUILD_DIR-release"
    SD_OUT_DIR="${SD_OUT_DIR:-$CROW_HOME/build/sd-release}"
    BIN_DIR="$SD_OUT_DIR/bin"
fi

# Disk, in MB. Measured on the 2026-09-26 build: build dir 513 MB, the two
# binaries 110 MB each, the source tree with submodules ~290 MB. A fresh CUDA
# prefix is 2.3 GB unpacked plus ~970 MB of archives.
SD_NEED_BUILD_MB=1000
SD_NEED_SRC_MB=600
SD_NEED_CUDA_MB=3500
SD_DISK_RESERVE_MB="${SD_DISK_RESERVE_MB:-1024}"

# --- 0. disk ---------------------------------------------------------------
free_mb() {
    local target="$1"
    while [ ! -d "$target" ] && [ "$target" != "/" ]; do target="$(dirname "$target")"; done
    df -Pm "$target" | awk 'NR==2 {print $4}'
}

ensure_disk() {
    say "disk"
    local need=0 free
    [ -x "$SD_BUILD_DIR/bin/sd-server" ] || need=$((need + SD_NEED_BUILD_MB))
    [ -d "$SD_SRC_DIR/.git" ] || [ -f "$SD_SRC_DIR/.git" ] || need=$((need + SD_NEED_SRC_MB))
    cuda_prefix_complete "$CUDA_ROOT" || command -v nvcc >/dev/null 2>&1 || need=$((need + SD_NEED_CUDA_MB))
    free="$(free_mb "$CROW_HOME")"
    echo "    $free MB free under $CROW_HOME, this run needs ~$need MB + $SD_DISK_RESERVE_MB MB reserve"
    if [ "$free" -lt $((need + SD_DISK_RESERVE_MB)) ]; then
        echo "not enough disk: $free MB free, ~$((need + SD_DISK_RESERVE_MB)) MB needed" >&2
        exit 1
    fi
}

# --- 1. source tree --------------------------------------------------------
# The gitlink a tree records for <path>, and the commit checked out there.
gitlink_of() { git -C "$SD_SRC_DIR" ls-tree HEAD "$1" | awk '{print $3}'; }
checked_out() { git -C "$SD_SRC_DIR/$1" rev-parse HEAD 2>/dev/null || true; }

# Everything this script would produce, already in place: HEAD on the pin, every
# recorded submodule pin matching the pin's tree, every built submodule checked
# out at it, and no tracked file modified (a `--dirty=+` version would follow).
src_matches() {
    local entry path sha
    [ "$(git -C "$SD_SRC_DIR" rev-parse HEAD 2>/dev/null)" = "$SD_PIN" ] || return 1
    for entry in $SD_SUBMODULES_BUILT $SD_SUBMODULES_RECORDED; do
        path="${entry%%:*}"; sha="${entry#*:}"
        [ "$(gitlink_of "$path")" = "$sha" ] || return 1
    done
    for entry in $SD_SUBMODULES_BUILT; do
        path="${entry%%:*}"; sha="${entry#*:}"
        [ "$(checked_out "$path")" = "$sha" ] || return 1
    done
    [ -z "$(git -C "$SD_SRC_DIR" status --porcelain --untracked-files=no 2>/dev/null)" ] || return 1
    return 0
}

# A shallow fetch of the pin and its tag -- the tag because the version string
# is `git describe --tags` at configure time (CMakeLists.txt:249), and without
# it the binary reports "version unknown", as 137f740 does. GitHub serves full
# SHAs directly, so no history is cloned.
ensure_src() {
    say "stable-diffusion.cpp source"
    if [ -e "$SD_SRC_DIR" ] && src_matches; then
        echo "    $SD_SRC_DIR is at $SD_TAG with the recorded submodules, untouched"
    else
        if [ ! -d "$SD_SRC_DIR/.git" ] && [ ! -f "$SD_SRC_DIR/.git" ]; then
            mkdir -p "$(dirname "$SD_SRC_DIR")"
            run git init -q "$SD_SRC_DIR"
            run git -C "$SD_SRC_DIR" remote add origin "$SD_UPSTREAM"
        fi
        rm -f "$SD_SRC_DIR/.git/shallow.lock" "$SD_SRC_DIR/.git/index.lock"
        if ! git -C "$SD_SRC_DIR" cat-file -e "${SD_PIN}^{commit}" 2>/dev/null \
           || ! git -C "$SD_SRC_DIR" rev-parse -q --verify "refs/tags/$SD_TAG" >/dev/null; then
            run git -C "$SD_SRC_DIR" fetch --depth 1 -q origin \
                "$SD_PIN" "+refs/tags/$SD_TAG:refs/tags/$SD_TAG"
        fi
        run git -C "$SD_SRC_DIR" checkout -q --detach "$SD_PIN"
        run git -C "$SD_SRC_DIR" reset -q --hard "$SD_PIN"
        local entry paths=""
        for entry in $SD_SUBMODULES_BUILT; do paths="$paths ${entry%%:*}"; done
        # shellcheck disable=SC2086
        run git -C "$SD_SRC_DIR" submodule update --init --force --depth 1 -- $paths
    fi
    verify_src
}

# Not trusted, looked at: the tag must name the pin, and every pin in the
# tables above must be the one the tree records. A mismatch here means the
# tables and the tree disagree, and a build from either would be a guess.
verify_src() {
    local entry path sha have bad=0
    have="$(git -C "$SD_SRC_DIR" rev-parse "refs/tags/$SD_TAG^{commit}" 2>/dev/null || true)"
    if [ "$have" != "$SD_PIN" ]; then
        echo "tag $SD_TAG is ${have:-absent} in $SD_SRC_DIR, expected $SD_PIN" >&2; bad=1
    fi
    for entry in $SD_SUBMODULES_BUILT $SD_SUBMODULES_RECORDED; do
        path="${entry%%:*}"; sha="${entry#*:}"
        have="$(gitlink_of "$path")"
        if [ "$have" != "$sha" ]; then
            echo "submodule $path: the pin records ${have:-nothing}, this script expects $sha" >&2; bad=1
        fi
    done
    for entry in $SD_SUBMODULES_BUILT; do
        path="${entry%%:*}"; sha="${entry#*:}"
        have="$(checked_out "$path")"
        if [ "$have" != "$sha" ]; then
            echo "submodule $path is checked out at ${have:-nothing}, expected $sha" >&2; bad=1
        fi
    done
    [ "$bad" -eq 0 ] || exit 1
    echo "    pin: $(git -C "$SD_SRC_DIR" log -1 --format='%h %s') ($SD_TAG)"
    for entry in $SD_SUBMODULES_BUILT $SD_SUBMODULES_RECORDED; do
        echo "      ${entry%%:*} ${entry#*:}"
    done
}

# --- 2. configure + build --------------------------------------------------
configure_build() {
    say "configure"
    [ "$CLEAN" = "1" ] && rm -rf "$SD_BUILD_DIR"
    local native="-DGGML_NATIVE=ON" rpath="$CUDA_ROOT/lib" cflags="" cudaflags="-allow-unsupported-compiler"
    local -a cpu=()
    if [ "$SD_RELEASE" = "1" ]; then
        native="-DGGML_NATIVE=OFF"
        cpu=(-DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON)
        # shellcheck disable=SC2016  # $ORIGIN is for the dynamic loader, not the shell
        rpath='$ORIGIN/../cuda/lib'
        # the more specific prefixes last: GCC applies the last one that matches
        cflags="-ffile-prefix-map=$HOME=~ -ffile-prefix-map=$SD_SRC_DIR=. -ffile-prefix-map=$SD_BUILD_DIR=build"
        cudaflags="$cudaflags -Xcompiler=-ffile-prefix-map=$HOME=~ -Xcompiler=-ffile-prefix-map=$SD_SRC_DIR=. -Xcompiler=-ffile-prefix-map=$SD_BUILD_DIR=build"
        mkdir -p "$SD_OUT_DIR"
        ln -sfn "$CUDA_ROOT" "$SD_OUT_DIR/cuda"
    fi
    run "$CMAKE" -S "$SD_SRC_DIR" -B "$SD_BUILD_DIR" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DSD_CUDA=ON \
        -DSD_SERVER_BUILD_FRONTEND=OFF \
        -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH" \
        -DCMAKE_CUDA_COMPILER="$NVCC" \
        -DCUDAToolkit_ROOT="$CUDA_ROOT" \
        -DCMAKE_CUDA_FLAGS="$cudaflags" \
        -DCMAKE_C_FLAGS="$cflags" \
        -DCMAKE_CXX_FLAGS="$cflags" \
        "$native" "${cpu[@]}" \
        -DSD_BUILD_SHARED_LIBS=OFF \
        -DCMAKE_MAKE_PROGRAM="$NINJA" \
        -DCMAKE_INSTALL_RPATH="$rpath" \
        -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
        -DCMAKE_EXE_LINKER_FLAGS="-Wl,--disable-new-dtags"

    say "build ($SD_TARGETS, -j$JOBS)"
    # shellcheck disable=SC2086
    run "$CMAKE" --build "$SD_BUILD_DIR" --target $SD_TARGETS -j "$JOBS"
}

# --- 3. install + verify ---------------------------------------------------
# "2f016e8" out of `<bin> --version`, or "unknown". LD_LIBRARY_PATH because a
# hand-copied binary without an RPATH does not start without it (2026-09-27).
commit_of() {
    local out
    out="$(LD_LIBRARY_PATH="$CUDA_ROOT/lib" "$1" --version 2>/dev/null || true)"
    out="$(printf '%s\n' "$out" | sed -n 's/.*commit \([0-9a-f]\{7,\}\).*/\1/p' | head -1)"
    echo "${out:-unknown}"
}

# Install one binary. Same bytes: nothing to do. Another commit's binary at the
# same name: renamed to <name>-<commit> first -- robin's bin/ carried a 137f740
# sd-cli (#206) that is still a reference point, and this script deletes nothing.
install_one() {
    local name="$1" src="$SD_BUILD_DIR/bin/$1" dest="$BIN_DIR/$1" old keep
    if [ -f "$dest" ] && cmp -s "$src" "$dest"; then
        echo "    $name: unchanged"
        return
    fi
    if [ -f "$dest" ]; then
        old="$(commit_of "$dest")"
        if [ "$old" != "${SD_PIN:0:7}" ]; then
            keep="$BIN_DIR/$name-$old"
            [ -e "$keep" ] && ! cmp -s "$dest" "$keep" && keep="$keep.$(date +%Y%m%d%H%M%S)"
            [ -e "$keep" ] || run mv "$dest" "$keep"
            echo "    $name: the previous one ($old) is kept as $(basename "$keep")"
        fi
    fi
    run install -m 0755 "$src" "$dest"
}

verify_one() {
    local exe="$BIN_DIR/$1" lib real cudalib ver
    cudalib="$(realpath "$CUDA_ROOT/lib")"
    echo "    -- $1: ldd (CUDA libraries) --"
    ldd "$exe" | grep -Ei 'cuda|cublas|nvjit' | sed 's/^/    /' || true
    if ldd "$exe" | grep -qE '=> not found'; then
        echo "unresolved shared libraries in $exe" >&2; ldd "$exe" | grep 'not found' >&2; exit 1
    fi
    if ldd "$exe" | grep -qE 'libcudart\.so\.12|libcublas\.so\.12'; then
        echo "$exe links a CUDA 12 runtime while compiling with $("$NVCC" --version | tail -2 | head -1)" >&2
        exit 1
    fi
    # Resolved to THIS prefix, not merely resolved: see CUDA RUNTIME PINNING in
    # build-llama-server.sh. Compared as real paths, so a linked cuda/ passes.
    for lib in libcudart.so.13 libcublas.so.13 libcublasLt.so.13; do
        real="$(ldd "$exe" | awk -v l="$lib" '$1 == l {print $3}')"
        if [ -z "$real" ] || [ "$(dirname "$(realpath "$real")")" != "$cudalib" ]; then
            echo "$exe: $lib resolves to '${real:-nothing}', not into $CUDA_ROOT/lib" >&2; exit 1
        fi
    done
    ver="$("$exe" --version 2>&1 | head -1)"
    echo "    -- $1 --version --"
    echo "    $ver"
    case "$ver" in
        *"version $SD_TAG, commit ${SD_PIN:0:7}"*) ;;
        *) echo "$exe reports '$ver', expected version $SD_TAG, commit ${SD_PIN:0:7}" >&2; exit 1 ;;
    esac
}

install_verify() {
    say "install"
    mkdir -p "$BIN_DIR"
    local t
    for t in $SD_TARGETS; do install_one "$t"; done
    say "verify"
    for t in $SD_TARGETS; do verify_one "$t"; done
}

sd_main() {
    say "crow sd-server build  (CROW_HOME=$CROW_HOME)"
    mkdir -p "$CROW_HOME"
    ensure_disk
    ensure_cmake_ninja
    ensure_cuda
    ensure_src
    configure_build
    install_verify
    say "done: $BIN_DIR/sd-server, $BIN_DIR/sd-cli"
    echo "    generate_image also needs the Ming-Image 0.1 Design model directory:"
    echo "    \$CROW_IMAGE_MODEL_DIR, else <models>/ming-image-0.1-design, else"
    echo "    ming-image-0.1-design beside the tree <install>/models links to"
    echo "    (crow_core.image_model_dir())."
}

sd_main "$@"
