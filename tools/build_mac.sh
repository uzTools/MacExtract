#!/bin/sh
# build_mac.sh — cross-compile the Macintosh shell.
#
# Locates a Retro68 toolchain via (in order): $RETRO68, m68k-apple-macos-gcc
# in PATH, or /opt/Retro68-build/toolchain. Skips gracefully when absent.
# Output: build/mac/macextract.{APPL,bin,dsk}
set -e
cd "$(dirname "$0")/.."

TOOLCHAIN=""
if [ -n "$RETRO68" ] && [ -d "$RETRO68" ]; then
    TOOLCHAIN="$RETRO68"
elif command -v m68k-apple-macos-gcc >/dev/null 2>&1; then
    TOOLCHAIN="$(dirname "$(dirname "$(command -v m68k-apple-macos-gcc)")")"
elif [ -x /opt/Retro68-build/toolchain/bin/m68k-apple-macos-gcc ]; then
    TOOLCHAIN=/opt/Retro68-build/toolchain
fi

CMAKEFILE="$TOOLCHAIN/m68k-apple-macos/cmake/retro68.toolchain.cmake"
if [ -z "$TOOLCHAIN" ] || [ ! -f "$CMAKEFILE" ]; then
    echo "mac: Retro68 m68k toolchain not found — skipping the Mac build."
    echo "mac: to build it: clone https://github.com/autc04/Retro68 and run"
    echo "mac:   ./build-toolchain.bash   then set RETRO68=<install prefix>"
    exit 0
fi

echo "mac: using Retro68 at $TOOLCHAIN"
cmake -B build/mac -S mac \
      -DCMAKE_TOOLCHAIN_FILE="$CMAKEFILE" \
      -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build build/mac -- -j"$(nproc)"
ls -la build/mac/MacExtract.APPL build/mac/MacExtract.bin build/mac/MacExtract.dsk
echo "mac: OK — this only proves it compiles. tools/vmac/run.py replays fixtures"
echo "mac: on a real emulated Mac Plus; tools/vmac/README.md is how to run it."
