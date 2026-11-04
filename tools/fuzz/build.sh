#!/bin/sh
# build.sh — build every decoder harness in tools/fuzz/ under libFuzzer,
# ASan and UBSan. Needs clang with -fsanitize=fuzzer; refuses without it
# rather than building something weaker (TESTING.md, *Fuzzing each decoder
# on its own*).
#
#     sh tools/fuzz/build.sh [outdir]          # default build/fuzz
#
# The engine is compiled once with fuzzer-no-link instrumentation, so its
# edges count as coverage; each harness is linked against all of it except
# the file it includes to reach a static entry point (fz_decoders.c).
set -e
cd "$(dirname "$0")/../.."
CC=${CC:-clang}
OUT=${1:-build/fuzz}
command -v "$CC" >/dev/null 2>&1 || { echo "fuzz: no $CC" >&2; exit 2; }
mkdir -p "$OUT/obj"
echo 'int LLVMFuzzerTestOneInput(const unsigned char*d,unsigned long n){return 0;}' \
    > "$OUT/probe.c"
"$CC" -fsanitize=fuzzer "$OUT/probe.c" -o "$OUT/probe" 2>/dev/null \
    || { echo "fuzz: $CC has no -fsanitize=fuzzer" >&2; exit 2; }
rm -f "$OUT/probe.c" "$OUT/probe"

SAN="-fsanitize=address,undefined -fno-sanitize-recover=all"
CFL="-O1 -g -std=c99 -DUNC_OFF64 -Iinclude -Isrc $SAN"
for f in src/*.c third_party/zlib/*.c; do
    o="$OUT/obj/$(basename "$f" .c).o"
    case "$f" in third_party/*) o="$OUT/obj/zlib_$(basename "$f" .c).o";; esac
    "$CC" $CFL -fsanitize=fuzzer-no-link -c "$f" -o "$o"
done

# target : the engine file its harness includes (none: links them all)
for spec in SIT: SIT13: SIT14: ARSENIC: DD:fmt_dd DDN:fmt_dd \
            LZH_STATIC:fmt_lzh LZH_DYN:fmt_lzh NOW:fmt_now \
            SPACESAVER:fmt_spacesaver SUPERDISK:fmt_superdisk \
            IMPLODE: SHRINK: REDUCE:; do
    t=${spec%%:*}
    skip=${spec#*:}
    objs=""
    for o in "$OUT"/obj/*.o; do
        [ -n "$skip" ] && [ "$(basename "$o" .o)" = "$skip" ] && continue
        objs="$objs $o"
    done
    lower=$(echo "$t" | tr 'A-Z' 'a-z')
    "$CC" $CFL -fsanitize=fuzzer -Wno-unused-function -DFZ_$t \
        tools/fuzz/fz_decoders.c $objs -o "$OUT/fz_$lower"
    echo "fuzz: built $OUT/fz_$lower"
done
