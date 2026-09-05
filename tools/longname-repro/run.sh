#!/bin/sh
# run.sh — build repro.c against the engine under ASan and run it over
# one fixture per family. Expected: the three path-walking formats
# (DiskDoubler, SuperDisk!, Now Compress) die in path_full_add with a
# heap-buffer-overflow WRITE; Compact Pro and StuffIt list cleanly; and
# every one of them lists cleanly with --null. See README.md.
set -e
cd "$(dirname "$0")/../.."
OUT=${OUT:-/tmp/longname-repro}
gcc -std=c99 -g -O1 -fsanitize=address,undefined -fno-omit-frame-pointer \
    -Iinclude -Isrc -Ithird_party/zlib -DZ_TESTW=0 -DNO_GZIP \
    src/*.c third_party/zlib/*.c tools/longname-repro/repro.c -o "$OUT"
for f in derived-DandStoQIF2.sea derived-SD__Utilities.x synth-now-mixed.now \
         derived-XferIt_1.5b4.sea derived-Export.sit; do
    [ -f "fixtures/$f" ] || { echo "skip $f (not fetched)"; continue; }
    echo "=== $f, garbage-shaped long_name"
    ASAN_OPTIONS=detect_leaks=0 "$OUT" "fixtures/$f" 2>&1 | \
        grep -m1 -E "ERROR: AddressSanitizer|entries" || true
    echo "=== $f, --null"
    ASAN_OPTIONS=detect_leaks=0 "$OUT" --null "fixtures/$f" 2>&1 | \
        grep -m1 -E "ERROR: AddressSanitizer|entries" || true
done
