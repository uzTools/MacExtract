#!/bin/sh
# mkoverlay.sh <out.r> <source.c>... — build a loadable overlay.
#
# Produces a Rez 'OVLY' resource holding a FLAT, position-independent image
# whose entry point is at offset 0. The application loads it with GetResource
# only when an archive needs it, so its code is not resident and does not come
# off the engine's budget (FORMATS.md, *What the application costs the engine*).
#
# -mpcrel is what makes it relocatable-free: internal references become
# PC-relative and the LINKER resolves them, so nothing is left to patch at run
# time. The build FAILS if any relocation survives, if the image needs .bss,
# or if it exceeds the +-32 KB that PC-relative addressing reaches.
#
# .data is ALLOWED and travels inside the image — this header said otherwise
# until 2026-09-01, and BRANCH_NOTES.md repeated it, which mattered: it is the
# reason nobody tried putting a DECODER in an overlay. Every decoder has
# tables, tables are .data, and "an overlay cannot carry .data" ruled the
# whole set out on paper. The code twenty lines below has always said the
# opposite, and the code is right.
set -e
cd "$(dirname "$0")/../.."
OUT=$1; shift
T=${RETRO68:-/opt/Retro68-build/toolchain}/bin
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

# The resource id comes from overlay.h, by name. It used to be a number in
# mac/CMakeLists.txt beside a second copy in overlay.h, and the two disagreeing
# is not something a build can notice: the image is simply numbered something
# other than what the shim's GetResource asks for, and the failure is on the
# Macintosh (tools/overlay/ovlid.py).
OVL_ID=$(python3 tools/overlay/ovlid.py "${OVL_ID:-OVL_ID_CRYPT}") || exit 1
# One function, because the flag list is the interface between an image and
# the compiler and two copies of it drift. Every object in an image — the
# caller's sources and the runtime net below — is built with exactly these.
#
# -fno-tree-loop-distribute-patterns, because an overlay links no libc.
# -fno-builtin does not cover this: the pattern pass rewrites a plain
# `for (i = 0; i < n; i++) p[i] = 0;` into a CALL to memset, and the
# engine has several. Resident they resolve against Retro68's libc; in
# an image there is nothing to resolve against, and the link fails with
# an undefined reference — which is how main's fused Compact Pro LZH
# and RLE stages arrived here (DECISIONS.md 2026-09-19, *the byte that
# went to two places at once*). The loop is then emitted as written,
# and every one of them zeroes a window once per fork.
ovl_cc() {
    "$T/m68k-apple-macos-gcc" -c -Os -mcpu=68000 -mpcrel \
        -ffunction-sections -fdata-sections -fno-builtin \
        -fno-tree-loop-distribute-patterns \
        -Itools/overlay -Iinclude -Isrc ${OVL_INC:+-I$OVL_INC} \
        "$1" -o "$2"
}

OBJS=""
for src in "$@"; do
    o="$TMP/$(basename "$src" .c).o"
    ovl_cc "$src" "$o"
    OBJS="$OBJS $o"
done

# The runtime net. The flag above stops ONE idiom; the compiler has more of
# them, and with every flag above in place a 400-byte struct assignment still
# emits a call to memcpy (measured 2026-09-25). tools/overlay/ovl_rt.c defines
# memcpy, memmove, memset and memcmp so such a call links instead of ending
# the build, and --gc-sections below drops every one nothing references — so
# an image that needs none is byte-identical to the image it was before this
# object joined the link, which mkoverlay verified rather than assumed.
ovl_cc tools/overlay/ovl_rt.c "$TMP/ovl_rt.o"
OBJS="$OBJS $TMP/ovl_rt.o"
# --gc-sections, with ovl_main as the root: an overlay links no libc, and
# zlib reaches for memcpy/malloc/free from paths this engine never takes —
# inflateCopy, and the zcalloc/zcfree that unc_inflate.c replaces with its
# own allocator. Dropping what nothing calls is both the fix and a size win
# for every other image. The sources are already compiled with
# -ffunction-sections -fdata-sections, which is what makes it work.
"$T/m68k-apple-macos-ld" -T tools/overlay/overlay.ld ${OVL_GC:---gc-sections --entry=ovl_main} -q -o "$TMP/ovl.elf" $OBJS \
    "$("$T/m68k-apple-macos-gcc" -print-libgcc-file-name)"

# ABSOLUTE relocations, and why this is no longer a refusal.
#
# Until 2026-09-02 this ran `objdump -r` on the FULLY LINKED image and
# required zero, which is a check that cannot fail: the linker has already
# resolved every relocation into the data, so there is nothing left to count.
# It passed for a year and hid a real defect — see mkreloctrailer.py. Link
# with -q, which KEEPS the relocations, and hand the absolute ones to the
# loader. -mpcrel makes CODE position-independent; nothing makes a pointer
# stored in data so.
# ONLY the sections that end up in the image. `readelf -r` also lists
# .rela.debug_line, .rela.debug_info and .rela.debug_aranges, whose R_68K_32
# offsets are offsets into DEBUG sections that objcopy never emits — feeding
# those to the loader patches arbitrary words of the image, which is a hang
# rather than a wrong answer, and is what the first version of this did.
RELOCS=$("$T/m68k-apple-macos-readelf" -r "$TMP/ovl.elf" 2>/dev/null \
         | awk "/^Relocation section/ {
                    keep = (\$3 == \"'.rela.text'\" || \$3 == \"'.rela.data'\" ||
                            \$3 ~ /^.\\.rela\\.rodata/)
                 }
                 /R_68K_32/ && keep { print \$1 }" | sort | uniq)   # hex
NREL=$(printf '%s' "$RELOCS" | grep -c . || true)
# .bss is refused and .data is allowed, and the difference matters: objcopy
# writes .data INTO the image, where it lands inside the locked Handle and is
# writable, while .bss is only a SIZE and lives past the image end — a blob
# writing there would corrupt the heap. So an overlay's mutable state must be
# initialised. (This check found exactly that bug on the first real overlay.)
sz=$("$T/m68k-apple-macos-size" -A "$TMP/ovl.elf" | awk '$1==".bss"{print $2}')
[ -z "$sz" ] || [ "$sz" = 0 ] || { echo "mkoverlay: .bss is $sz B — it lives past the image end;" >&2
                                  echo "mkoverlay: initialise the static so it lands in .data" >&2; exit 1; }
"$T/m68k-apple-macos-objcopy" -O binary "$TMP/ovl.elf" "$TMP/ovl.bin"
python3 tools/overlay/mkreloctrailer.py "$TMP/ovl.bin" $RELOCS || exit 1
n=$(wc -c < "$TMP/ovl.bin")
[ "$n" -le 32768 ] || { echo "mkoverlay: $n B exceeds the 32 KB PC-relative reach" >&2; exit 1; }

{ echo "/* GENERATED by tools/overlay/mkoverlay.sh — do not edit. */"
  echo "data 'OVLY' ($OVL_ID, \"overlay\") {"
  od -An -tx1 -v "$TMP/ovl.bin" | tr -d ' \n' | fold -w 64 | sed 's/^/    $"/; s/$/"/'
  echo "};"
} > "$OUT"
# Which runtime routines survived --gc-sections, i.e. which ones this image
# actually calls. Printed because the net is silent by design and the one
# thing it can cost is speed: these are byte-wise, and the resident build
# calls Retro68's libc. A routine appearing here on a decoder's hot path is
# worth measuring; a routine appearing here at all is worth knowing about.
RT=$("$T/m68k-apple-macos-nm" --defined-only "$TMP/ovl.elf" 2>/dev/null \
     | awk '$3=="memcpy"||$3=="memmove"||$3=="memset"||$3=="memcmp"{printf " %s", $3}')
echo "mkoverlay: $OUT — $n B, $NREL relocation(s) applied at load, entry at 0${RT:+, runtime:$RT}"
