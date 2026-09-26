#!/bin/sh
# run_overlay_host.sh — the overlay loader, run and asserted off the Macintosh.
#
# The application ships fourteen 'OVLY' images and until 2026-09-26 no
# automated suite reached one: the images exist only in a Retro68 build, so the
# 932-fixture corpus, the 9,320 robustness variants and every sanitiser build
# exercise the decoders as ordinary linked code. Whether an image is FOUND,
# RELOCATED, KEPT, RELEASED or RE-READ was answered by emulator tiers, by hand,
# at minutes per fixture — and three defects lived in that gap, each found by
# something other than a test (OPEN_ITEMS.md, *The overlay loader*).
#
# What this does about it, in four lanes:
#
#   1. the fourteen images, built from the SAME sources with the SAME flags by
#      tools/overlay/mkoverlay.sh, with the m68k-linux toolchain instead of
#      Retro68's (OVL_TOOL);
#   2. the REAL loader — mac/ovl_load_eager.c or mac/ovl_load_lazy.c,
#      unmodified — against those images through the mock Memory and Resource
#      Managers in tests/ovlbox/, natively under ASan and big-endian under
#      qemu-m68k: read counts, keep and release, the relocation of every image
#      at the address it runs at, and the documented cache flush;
#   3. fixtures EXTRACTED through the images, byte-exact against the same
#      oracle manifests the Mac sink suite uses, under qemu-m68k — the images
#      are m68k code and this is where it is executed;
#   4. one fixture per image, the overlay build against the RESIDENT build of
#      the same engine, which is the only oracle for an image no manifest
#      covers (SuperDisk!, btoa, MIME).
#
# WHAT IT CANNOT SEE: tests/ovlbox/ovlbox.c's header is the list, and
# TESTING.md (*The overlay loader, off the Macintosh*) repeats it. The short
# form: no instruction cache, so a flush is counted and never needed; no
# Resource Manager; no fragmentation; and not Retro68's code generation — the
# same compiler family, not the same compiler. The emulator tiers stay.
#
# `--mutate` is the answer to "a test that passes may not be testing
# anything": it breaks the loader five ways and requires each break to be
# caught. Run by ci.sh like everything else here.
set -e
cd "$(dirname "$0")/.."

MODE=${1:-}
# --shipped-only grades the RETRO68 images instead of building any: the ones
# `build/mac/` holds, which are the bytes dist/ ships. They load here and their
# relocations can be checked; they cannot be CALLED from an m68k-linux binary
# (measured: SIGSEGV, two toolchains' conventions), so that lane stops at the
# loader. ci.sh runs it after variant 4, which is what builds them.
if [ "$MODE" = "--shipped-only" ]; then B=build/ovlhost-shipped; else B=build/ovlhost; fi
GEN=$B/gen
IMG=$B/img

if ! command -v m68k-linux-gnu-gcc >/dev/null 2>&1; then
    echo "overlay-host: no m68k-linux-gnu-gcc — skipping (the images are m68k)"
    exit 0
fi

fail() { echo "overlay-host: FAILED — $1" >&2; exit 1; }

rm -rf $B
mkdir -p $GEN $IMG

# The inventory is mac/CMakeLists.txt's, parsed rather than restated: a second
# copy of it here would grade images that are not the ones the Macintosh loads
# (tools/overlay/images.py).
python3 tools/overlay/images.py --check || fail "the image inventory"
python3 tools/overlay/mkforwards.py $GEN >/dev/null || fail "mkforwards"

if [ "$MODE" = "--shipped-only" ]; then
    [ -f build/mac/ovl_bundle.bin ] || {
        echo "overlay-host: no build/mac/ovl_bundle.bin — run ci.sh variant 4"
        echo "overlay-host: (the Retro68 build is what writes the shipped images)"
        exit 0; }
else

echo "overlay-host: fourteen images, m68k-linux toolchain"
python3 tools/overlay/images.py > $B/inv.txt
while read -r ident srcs; do
    resolved=""
    for s in $srcs; do
        if [ -f "$s" ]; then resolved="$resolved $s"
        else resolved="$resolved $GEN/$(basename "$s")"; fi
    done
    OVL_ID=$ident OVL_INC=$GEN OVL_TOOL=m68k-linux-gnu- \
        sh tools/overlay/mkoverlay.sh $IMG/$ident.r $resolved >$B/mk.log 2>&1 \
        || { cat $B/mk.log; fail "building image $ident"; }
    id=$(python3 tools/overlay/ovlid.py "$ident")
    cp $IMG/$ident.bin $IMG/$id.bin          # the loader test wants them by id
    printf '%s %s/%s.bin\n' "$id" "$IMG" "$id" >> $B/manifest_lazy.txt
done < $B/inv.txt
[ "$(wc -l < $B/manifest_lazy.txt)" = 14 ] || fail "not fourteen images"

# The eager lifetime reads ONE resource: the bundle, with every image in it.
pairs=""
while read -r ident srcs; do pairs="$pairs $ident:$IMG/$ident.bin"; done < $B/inv.txt
python3 tools/overlay/mkbundle.py $IMG/bundle.r --bin $IMG/bundle.bin $pairs \
    >/dev/null || fail "mkbundle"
printf '128 %s/bundle.bin\n' "$IMG" > $B/manifest_eager.txt
fi

# The engine sources that are NOT resident in an overlay build — the same list
# mac/CMakeLists.txt filters out, read from it for the same reason.
RESIDENT_SRC=$(python3 - <<'PY'
import glob, os, subprocess
ex = set(subprocess.check_output(
    ["python3", "tools/overlay/images.py", "--resident"]).decode().split())
print(" ".join(p for p in sorted(glob.glob("src/*.c"))
                if os.path.basename(p) not in ex))
PY
)

INC="-Iinclude -Isrc -Imac -Itools/overlay -Itests/ovlbox -Itests/ovlbox/toolbox -I$GEN -Ithird_party/zlib"
# UNC_AT_BUDGET is what defines gWantedAfterRelease/gKeepFail/gFlushHas/
# gFlushCalls — the probe fields a Macintosh only shows on its completion
# alert. Here they are assertions.
DEFS="-DUNC_AT_OVERLAY -DUNC_AT_BUDGET '-DOVL_LOWMEM_ROM85=ovlbox_rom85()'"
# The sink lane does NOT define UNC_AT_BUDGET: in mac/macextract_mac.c that
# switch turns on a heap probe built out of ApplicationZone, LMGetApplLimit and
# MaxBlock, which the mock Toolbox does not carry and which has nothing to do
# with overlays. The loader test is where those fields are read.
SINK_DEFS="-DUNC_AT_OVERLAY '-DOVL_LOWMEM_ROM85=ovlbox_rom85()'"

build_loadtest() {   # <out> <loader.c> <extra-defs> <cc...>
    out=$1; loader=$2; extra=$3; shift 3
    eval "$* -std=gnu99 $INC $DEFS $extra \
        tests/ovlbox/ovl_load_test.c tests/ovlbox/ovlbox.c \
        mac/ovl_shim.c mac/ovl_reloc.c $loader $RESIDENT_SRC -o $out" \
        2>$B/cc.log || { grep -v multi-char $B/cc.log | head -20; \
                         fail "building $out"; }
}

NATIVE="gcc -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all"
M68K="m68k-linux-gnu-gcc -O2 -static -mcpu=68000"

if [ "$MODE" = "--shipped-only" ]; then
    # The shipped images, by resource id, and the shipped bundle as resource
    # 128. `ovlid.py` resolves each name, so a renamed image fails here rather
    # than being quietly left out.
    for f in build/mac/ovl_*.bin; do
        n=$(basename "$f" .bin)
        case $n in ovl_bundle|ovl_bundle.r.rsrc) continue;; esac
        ident="OVL_ID_$(printf '%s' "${n#ovl_}" | tr 'a-z' 'A-Z')"
        id=$(python3 tools/overlay/ovlid.py "$ident") || fail "no id for $n"
        cp "$f" $IMG/$id.bin
        printf '%s %s/%s.bin\n' "$id" "$IMG" "$id" >> $B/manifest_lazy.txt
    done
    [ "$(wc -l < $B/manifest_lazy.txt)" = 14 ] \
        || fail "not fourteen shipped images"
    cp build/mac/ovl_bundle.bin $IMG/bundle.bin
    printf '128 %s/bundle.bin\n' "$IMG" > $B/manifest_eager.txt
    echo "overlay-host: the SHIPPED images (Retro68), $(stat -c%s $IMG/bundle.bin) B of bundle"
fi

echo "overlay-host: the loader, native (ASan+UBSan)"
build_loadtest $B/loadtest_eager mac/ovl_load_eager.c -DOVL_LANE_EAGER $NATIVE
build_loadtest $B/loadtest_lazy  mac/ovl_load_lazy.c  ""                $NATIVE
OVLBOX_IMAGES=$B/manifest_eager.txt $B/loadtest_eager $IMG \
    || fail "the eager loader (native)"
OVLBOX_IMAGES=$B/manifest_lazy.txt $B/loadtest_lazy $IMG \
    || fail "the lazy loader (native)"
# A 64K ROM has neither flush trap, and every image must still load with the
# flush falling through. The route is latched on the first call, so this is a
# whole run of its own rather than a switch inside one.
OVLBOX_NO_FLUSH_ROUTE=1 OVLBOX_IMAGES=$B/manifest_eager.txt $B/loadtest_eager $IMG \
    >/dev/null || fail "the eager loader with no flush trap"

if ! command -v qemu-m68k >/dev/null 2>&1; then
    echo "overlay-host: no qemu-m68k — the native loader lanes passed; the "
    echo "overlay-host: images cannot be CALLED without it, skipping the rest"
    exit 0
fi

echo "overlay-host: the loader, big-endian m68k (qemu)"
build_loadtest $B/loadtest_eager_m68k mac/ovl_load_eager.c -DOVL_LANE_EAGER $M68K
build_loadtest $B/loadtest_lazy_m68k  mac/ovl_load_lazy.c  ""               $M68K
OVLBOX_IMAGES=$B/manifest_eager.txt qemu-m68k $B/loadtest_eager_m68k $IMG \
    || fail "the eager loader (m68k)"
OVLBOX_IMAGES=$B/manifest_lazy.txt qemu-m68k $B/loadtest_lazy_m68k $IMG \
    || fail "the lazy loader (m68k)"

if [ "$MODE" = "--shipped-only" ]; then
    # And no further. These images are Retro68's, and a Retro68 image called
    # from an m68k-linux host binary segfaults — measured 2026-09-26, not
    # assumed, on `synth-sit-rle90.sit` through the lazy sink. What this lane
    # grades is that the SHIPPED bytes are found, relocated correctly at the
    # address they run at, kept and released; executing them is the emulator
    # tiers' (DECISIONS.md 2026-09-26, *the loader that could be run after
    # all*).
    echo "overlay-host: shipped images ok (loaded and relocated; not called)"
    exit 0
fi

# ---------------------------------------------------------------------------
# Extraction THROUGH the images. tests/mac_sink_test.c is the same harness the
# sink suite uses, built with -DUNC_AT_OVERLAY: the decoders are gone from the
# link and arrive as images, loaded by the real loader and called.
# ---------------------------------------------------------------------------
build_sink() {  # <out> <loader.c|""> <defs>
    out=$1; loader=$2; defs=$3
    eval "$M68K -std=gnu99 $INC $defs \
        tests/mac_sink_test.c $loader -o $out" 2>$B/cc.log \
        || { grep -v multi-char $B/cc.log | head -20; fail "building $out"; }
}
echo "overlay-host: extraction through the images (qemu-m68k)"
build_sink $B/sink_eager "tests/ovlbox/ovlbox.c mac/ovl_shim.c mac/ovl_reloc.c mac/ovl_load_eager.c $RESIDENT_SRC" "$SINK_DEFS"
build_sink $B/sink_lazy  "tests/ovlbox/ovlbox.c mac/ovl_shim.c mac/ovl_reloc.c mac/ovl_load_lazy.c $RESIDENT_SRC"  "$SINK_DEFS"
# The control: the same engine with every decoder LINKED, which is the only
# oracle for an image no manifest covers.
build_sink $B/sink_resident "src/*.c third_party/zlib/*.c" ""

# TWO gradings, because they answer different questions.
#
# `oracle` is the sink suite's OWN fixture list, read out of
# tests/run_mac_sink.sh rather than copied: those fixtures have committed
# manifests AND the Mac shell's naming is already graded against them, so the
# overlay build can be held to byte-exactness there. (A fixture outside that
# list is not a fair oracle test: tools/check_mac_sink.py compares names the
# shell derives, and the resident build disagrees with the manifest for some of
# them too — measured on ddtf-dd377dda-testfile.png, where both builds write
# the same tree and neither matches. That is a naming question, not an overlay
# one.)
#
# `control` is one fixture per IMAGE against the resident build of the same
# engine, which is the only oracle for an image no manifest covers — SuperDisk!,
# btoa and MIME have none. It grades ONLY that the mechanism is transparent: a
# decoder that is wrong in both builds passes, and that is what the 932-fixture
# corpus is for.
ORACLE_FIXTURES=$(sed -n '/^FIXTURES="/,/"$/p;/^BOTHFORK_FIXTURES="/,/"$/p' \
                  tests/run_mac_sink.sh | sed 's/^[A-Z_]*="//; s/"$//; s/\\$//')
# One per image, smallest first because every run is emulated. Between them
# these reach thirteen of the fourteen images; the ciphers are loaded and kept
# by the loader lane above, and no fixture here can exercise them because the
# sink harness has no password to give.
CONTROL_FIXTURES="synth-sit-rle90.sit derived-KeyGraphics.sit
                  derived-keyAhead.cpt ddtf-dd377dda-testfile.png
                  lhasa-maclha-l1_subdir.lzh arc2pak1.pak synth-now-mixed.now
                  synth-packit-2.pit synth-exo-zip-deflate.zip
                  synth-exo-tar.tar synth-exo-gz.gz synth-exo-Z.Z
                  export-hc.hqx synth-uu-mac.uu derived-SD__Utilities.x
                  synth-os9-btoa.btoa synth-os9-mime.mim"

graded=0
for fx in $ORACLE_FIXTURES; do
    [ -f "fixtures/$fx" ] || continue
    [ -f "fixtures/manifests/$fx.json" ] || continue
    for lane in eager lazy; do
        out=$(mktemp -d)
        OVLBOX_IMAGES=$B/manifest_$lane.txt qemu-m68k $B/sink_$lane \
            "fixtures/$fx" "$out" >/dev/null 2>&1 \
            || { rm -rf "$out"; fail "$lane: extracting $fx"; }
        python3 tools/check_mac_sink.py "fixtures/manifests/$fx.json" \
            "$out" "fixtures/$fx" >/dev/null \
            || { rm -rf "$out"; fail "$lane: $fx is not byte-exact"; }
        rm -rf "$out"
    done
    graded=$((graded + 1))
done
echo "overlay-host: $graded fixture(s) byte-exact against the oracle, both lifetimes"

perimage=0
for fx in $CONTROL_FIXTURES; do
    [ -f "fixtures/$fx" ] || { echo "  absent, skipped: $fx"; continue; }
    # The EXIT STATUS is compared as well as the tree, and neither is required
    # to be success: two of this list's entries fail per-entry under the mock
    # File Manager, which cannot give them names of their own. What the lane
    # asserts is that the overlay build does exactly what the resident one
    # does — including failing the same entry.
    ctl=$(mktemp -d)
    # `if`, not `cmd; rc=$?`: `set -e` is on, so a plain failing command ends
    # the script before the status can be read — which it silently did here
    # once, making the whole lane look like it had passed.
    if qemu-m68k $B/sink_resident "fixtures/$fx" "$ctl" >/dev/null 2>&1
    then rc_ctl=0; else rc_ctl=$?; fi
    for lane in eager lazy; do
        out=$(mktemp -d)
        if OVLBOX_IMAGES=$B/manifest_$lane.txt qemu-m68k $B/sink_$lane \
               "fixtures/$fx" "$out" >/dev/null 2>&1
        then rc_lane=0; else rc_lane=$?; fi
        [ "$rc_lane" = "$rc_ctl" ] \
            || { rm -rf "$out" "$ctl"; fail "$lane: $fx exited $rc_lane, the resident build $rc_ctl"; }
        diff -r "$ctl" "$out" >/dev/null \
            || { rm -rf "$out" "$ctl"; fail "$lane: $fx differs from the resident build"; }
        rm -rf "$out"
    done
    rm -rf "$ctl"
    perimage=$((perimage + 1))
done
echo "overlay-host: $perimage fixture(s) identical to the resident build, both lifetimes"

# ---------------------------------------------------------------------------
# Can it fail? Five breaks, each of which a green run must catch. This is the
# project's rule about tests that cannot fail, applied to the newest suite
# here rather than discovered about it later (CLAUDE.md, *Traps*).
# ---------------------------------------------------------------------------
if [ "$1" = "--mutate" ]; then
    echo "overlay-host: can it fail? six breaks"
    MUT=$B/mut
    # <name> <loader.c> <extra-defs> <manifest> <file> <old> <new>
    #
    # The mutation is applied by tests/ovlbox/mutate.py, which FAILS when its
    # pattern is absent: a sed that matches nothing exits 0, and the first
    # version of this lane reported a break as uncaught when it had never been
    # applied at all.
    mutate() {
        name=$1; loader=$2; extra=$3; man=$4; target=$5; old=$6; new=$7
        rm -rf $MUT; mkdir -p $MUT
        cp mac/ovl_reloc.c mac/ovl_load_eager.c mac/ovl_load_lazy.c $MUT/
        python3 tests/ovlbox/mutate.py "$MUT/$target" "$old" "$new" \
            || fail "the mutation '$name' did not apply"
        eval "$NATIVE -std=gnu99 -I$MUT $INC $DEFS $extra \
            tests/ovlbox/ovl_load_test.c tests/ovlbox/ovlbox.c \
            mac/ovl_shim.c $MUT/ovl_reloc.c $MUT/$(basename $loader) \
            $RESIDENT_SRC -o $B/mut_bin" 2>$B/cc.log \
            || { grep -v multi-char $B/cc.log | head; fail "building mutant $name"; }
        if OVLBOX_IMAGES=$man $B/mut_bin $IMG >$B/mut.log 2>&1; then
            echo "  NOT CAUGHT: $name" >&2
            sed -n '1,12p' $B/mut.log >&2
            fail "the loader test passed with '$name' broken"
        fi
        echo "  caught: $name"
    }
    # The relocation arithmetic itself.
    mutate "the delta dropped" mac/ovl_load_eager.c -DOVL_LANE_EAGER \
        $B/manifest_eager.txt ovl_reloc.c \
        "+ (unsigned long)delta;" "+ 0;"
    # The trailer read with the table in the wrong place, which makes every
    # offset look like it is outside the image and skips the lot.
    mutate "the trailer table mislocated" mac/ovl_load_eager.c -DOVL_LANE_EAGER \
        $B/manifest_eager.txt ovl_reloc.c \
        "table = size - 4 - n * 4;" "table = size - 4;"
    # The kept copy's SECOND fixup, by the DIFFERENCE of two addresses — the
    # subtlest line in either loader, and the one no tier can see fail.
    mutate "the kept copy relocated by its own address" mac/ovl_load_eager.c \
        -DOVL_LANE_EAGER $B/manifest_eager.txt ovl_load_eager.c \
        "(long)*h - (long)p);" "(long)*h);"
    # The documented instruction-cache flush, at the bundle site.
    mutate "the bundle fixup does not flush" mac/ovl_load_eager.c \
        -DOVL_LANE_EAGER $B/manifest_eager.txt ovl_load_eager.c \
        "    ovl_flush_code();
}

/* Called from main()" "}

/* Called from main()"
    # An image left unlocked, which the mock's compacting heap then moves.
    mutate "the lazy loader does not lock" mac/ovl_load_lazy.c "" \
        $B/manifest_lazy.txt ovl_load_lazy.c \
        "        HLock(h);" "        /* HLock(h); */"
    # And the release that keeps nothing it must: the codecs image, which
    # every decoder reaches through the host vector.
    mutate "the codecs image is not kept" mac/ovl_load_eager.c -DOVL_LANE_EAGER \
        $B/manifest_eager.txt ovl_load_eager.c \
        "    ovl_keep(OVL_ID_CODECS, 2);" "    /* not kept */"
fi

echo "overlay-host: ok"
