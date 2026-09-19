# PLANNED_WORK.md — shedding XADMaster's code, one row at a time

**Written 2026-09-19 as a brief for another session. Delete this file when
its items are done or abandoned** — a plan file that keeps completed rows
stops being readable as a list of what is left (DECISIONS.md 2026-08-24,
*PLANNED_WORK.md, closed*). Status lives in OPEN_ITEMS.md (*What is still
XADMaster's*), reasoning in DECISIONS.md, numbers in FORMATS.md. This file
holds the HOW and the acceptance criteria, and nothing that belongs in
those three.

Read CLAUDE.md first. Everything below assumes its rules: 68000
discipline, `./ci.sh` green before every commit, `dist/` rebuilt in the
same commit as any `src/` change, small focused commits pushed to `main`,
never a tag.

---

## The one rule that governs all of it

**Nothing is rewritten for the licence alone, and nothing is kept unless
it is measured.** The engine stays LGPL until the last XADMaster
transcription is gone, so a rewrite that is slower, bigger or hungrier
buys nothing today and costs a user something on a 1 MB Mac Plus. A row
is taken when it is at least neutral on every axis and better on one.
The `-lh1-` coder is the template (DECISIONS.md 2026-09-19, *the tree
that was Yoshizaki's*): the XADMaster version was kept in a scratch copy,
the new one built behind the same interface, both priced, the better one
committed with its numbers.

"Neutral" means: Mac engine ticks within noise (two runs of the same
build have differed by 2 ticks in 800 this week; treat ±0.5 % as noise),
peak heap not higher on any fixture the format has, `CODE` not higher
unless another axis paid for it and the ratchet comment says so.

## The measurement protocol, per row

Four axes, each with the instrument that prices it. Do all four before
and after, on the same fixtures, and put the table in the DECISIONS.md
entry.

1. **Correctness**: `./ci.sh`, plus the format's own suite where it has
   one outside the differential suite (`tools/run_crypt.py`,
   `tools/run_lzh.py`, `tools/run_arcplus.py`, `tools/run_dart.py`,
   `tools/run_now.py`). A per-entry CRC mismatch is a failure, never a
   skip.
2. **Speed, Linux** (ranks, does not price):
   `valgrind --tool=callgrind --callgrind-out-file=/tmp/x.out
   build/rel/macextract t fixtures/<f>`; totals from the `summary:`
   line, per-function from `callgrind_annotate`.
3. **Speed, Mac** (prices): the tick probe at authentic 7 MHz,
   `python3 tools/vmac/run.py --emu mv-4M-1x -D UNC_AT_TIMING
   --timeout <s> --poll 20 --json /tmp/t.json fixtures/<f>`. It reports
   FAIL by construction; read `values[3]` (whole run) minus `values[4..6]`
   (reads, writes, catalog) = engine ticks. A fixture without an oracle
   manifest needs `--expect`. Runs take minutes; run them in the
   background and do not touch the tree until they finish, because
   `run.py` builds the application from the tree at its start.
4. **Size**: build the Mac application from a scratch copy of the tree
   (`cp -r src include third_party mac tools /tmp/x && cd /tmp/x && cmake
   -B build -S mac -DCMAKE_TOOLCHAIN_FILE=/opt/Retro68-build/toolchain/m68k-apple-macos/cmake/retro68.toolchain.cmake
   -DCMAKE_BUILD_TYPE=Release && cmake --build build`), then
   `m68k-apple-macos-size build/MacExtract.code.bin.gdb` for CODE (text)
   and A5 (data + bss), and the same `size` on the `.c.obj` of the file
   you changed. Both ratchets in `tools/build_mac.sh` are set at the
   current size: raise or LOWER them with a dated comment saying what
   bought the bytes.
5. **Heap**: `build/rel/macextract t --stats fixtures/<f>` prints the
   high-water mark; `UNC_TRACE_ALLOC=1` prints every request.

## Traps met this week, so nobody meets them again

- **A private `make BUILD=/tmp/x` that fails on `-Werror` leaves the OLD
  binary in place**, and `| grep -i error` hides the failure because the
  compile lines contain "-Werror". Two rounds of Now Compress checks ran
  a stale binary before this was noticed. Look at `ls -la` of the binary,
  or `rm -rf` the directory first.
- **`ci.sh` builds a `UNC_ARS_FORCE_SAMPLED` variant of the engine.** A
  helper placed inside `#ifndef UNC_ARS_FORCE_SAMPLED` in
  `sit_arsenic.c` compiles in the normal build and not in that one.
- **`check_docs.py` runs FIRST in `ci.sh`** and fails on a DECISIONS.md
  index line that differs from its heading by so much as a backtick.
- **The harness Out volume is a 1,440 KB floppy.** An entry larger than
  that fails at `SetEOF` in twenty seconds with `ret` −9, `UNC_ERR_SINK`,
  and looks exactly like a memory refusal. `--out-kb 2400` for EasyFind.
- **A fixture near its memory minimum takes minutes even all-out**, and
  the default 300 s timeout then reads as a failure. XMenu at 562,000 B
  took 704 s, EasyFind 1,427 s.
- **Linux instruction counts overstate what the Plus gives.** The `-lh1-`
  rewrite was −18 to −24 % on Linux and −10.1 % in ticks; the Compact Pro
  `UNC_HOT` was priced only in ticks and came out −14.8 %.
- **A cost estimated from reading is a cost unknown.** Three "roughly
  zero" claims this week measured +468 B, +7.8 % and +756 B. Price before
  writing the number down.

---

## Item 1 — StuffIt's DES as standard DES around a permutation

**Files:** `src/unc_crypt.c` (`sitdes_setkey`, `sitdes_round`,
`sitdes_crypt`, `revbits`, `sit_nibble`, the `CRYPT_TAB_SITDES` branch of
`des_sp_entry`), `tools/gen_crypt_tables.py`, `tests/unit_formats.c`.

**What is known.** 2026-09-19 fitted XADMaster's `DES_SPtrans` against
the standard S boxes and P: it IS standard DES's round tables with the
six-bit index taking the E-expansion bits in order, bit 0 first, and
output bit k at word bit (k − 1 + 3) mod 32 (DECISIONS.md 2026-09-19,
*the transient tables*; the generator asserts it). So StuffIt's "little-
endian DES" is the standard round function in a rotated, bit-reversed
word layout, with no IP/FP. What is NOT yet known is whether
`sitdes_setkey`'s nibble schedule equals the standard PC-1/PC-2 schedule
of some fixed permutation of the key. Find out first.

**Steps.**
1. In Python, using `src/crypt_tables.h`'s tables and a transcription of
   `sitdes_setkey`, test the hypothesis: for random 8-byte keys, does
   there exist ONE bit permutation π of the 64 key bits such that the
   standard schedule of π(key), re-laid into the rotated word order
   (word bit (k − 1 + 3) mod 32, six-bit groups in E order), equals
   `sitdes_setkey(key)` for all 16 rounds? Solve for π bit by bit (each
   subkey bit is one key bit through PC-1, shifts and PC-2, so π is
   determined by matching single-bit keys). If it exists, the whole
   StuffIt formulation is: permute the key, standard `des_setkey`;
   permute the block in, run the standard rounds WITHOUT IP/FP, permute
   out. If it does not, keep `sitdes_setkey` (it is format knowledge,
   measured on three archives StuffIt Deluxe wrote) and fold only the
   round: one `des_round(l, r, subkey, sp)` shared by both ciphers, with
   the StuffIt subkeys re-laid into the standard six-bit-group form once
   at setup.
2. Either way, `CRYPT_TAB_SITDES` disappears: one table kind, one
   `des_sp_entry` without the `sit` branch, and the generator's SPtrans
   assertion is rewritten as an assertion about the permutation.
3. Grade: the unit tests' DES vectors, `tools/run_crypt.py` (35 cases,
   three of them StuffIt Deluxe 3.5.1 archives with 8-, 9- and
   17-character passwords), `./ci.sh`.
4. Price: code (expect a fall — `sitdes_*` is ~80 lines and the second
   table branch goes), heap (unchanged, one 2 KB table either way), ticks
   (nothing measurable: encrypted entries are not in the corpus and key
   setup is once per entry; say so rather than run one).

**Acceptance:** `run_crypt.py` 35/35, `ci.sh` green, CODE not up, NOTICE's
XADMaster paragraph no longer needs `XADStuffItDESHandle.m` for code —
only for the fact that the format's key derivation is what it is, which
the three real archives grade.

## Item 2 — Arsenic from the write-up

**Files:** `src/sit_arsenic.c` (rewrite behind the same
`unc_arsenic_decode(UncBufIn *, UncAlloc *, uint32_t, UncForkOut *)`),
possibly `src/fmt_sit5.c` for the parser (Russotto documents SIT5 too).

**Reference:** `reference/notes/arsenic_russotto.md`, Matthew T.
Russotto's description of the format — the arithmetic coder (26-bit,
MSB-first, the `range`/`code` renormalisation), the adaptive models with
their increments and limits, the selector alphabet with RUNA/RUNB zero
runs, MTF, the randomisation table and its schedule, the block-end CRC-32,
and the inverse BWT. Do NOT read `XADStuffItArsenicHandle.m` or the
current `sit_arsenic.c` while writing the new decoder; keep the current
file as the A/B oracle and as the fallback if the new one is not better.
The randomisation table's 256 values are format facts and may be copied
from wherever they are written down.

**What is fixed by the format** (bit-exact, no freedom): the decoder's
arithmetic — `renorm = range / total`, `frequency = code / renorm`, the
symbol whose cumulative range holds it, the advance, the renormalise-
while-`range ≤ HALF` loop; model increments (1/8/4/4/4/2/2/1), limits
(256/1024), reset points; the MTF; the selector's meaning; the
randomisation schedule; the RLE-of-four rule; the CRC.

**What is free** (where the gain is): how the models store frequencies
and find the symbol — the current linear search averages 10.4 steps on
the ISBN fixture and, with the two divisions, is over half the fast
path's instructions; how the renormalisation takes its bits (one bit per
inline read now; taking `k` bits at once is a hypothesis worth one tick
run); how the inverse BWT is stored (three bytes an entry, since
2026-09-19) and how the sampled index is laid out; the block buffer's
growth policy (read `ars_block_reserve`'s comment on the fragmentation
trail before changing it).

**What must survive**, because the 1 MB floor depends on it: the two
inverse-BWT paths and the `target`-halving dial between them; block
sizing from `min(outlen, blocksize)`; progress by OUTPUT through
`unc_progress_at` with the pump held; per-entry `UNC_ERR_MEM`; the
`UNC_ARS_FORCE_SAMPLED` and `ARS_INDEX_TARGET` build knobs `ci.sh` uses.

**Fixtures to price on**, all 31 StuffIt 5 fixtures for correctness
(`t` verifies the internal CRC-32), and for ticks:
- `derived-a2basic.dmg.sit` at 4 MB — the fast path, 542 s wall on the
  table, the shortest Arsenic run that is not trivial;
- `derived-KeyGraphics.sit` — 24 s, for a quick smoke;
- the 1 MB sampled path is priced with `--emu mv-1M-1x`, and takes
  12–24 minutes a run; do it once at the end for a2basic.

**Acceptance:** 31/31 at unlimited budget, at 648,100 B and under the
400 KB cap (24 of 31 fully today); the six bisected minimums in
FORMATS.md (*StuffIt 5: the Arsenic block size*) not higher; a2basic
ticks not higher; CODE not higher unless ticks paid for it. If it is
merely equal, keep the OLD file: equal is not a reason to move.

## Item 3 — Compact Pro's LZH and RLE stages, fused (gain only)

**Files:** `src/fmt_cpt.c` (`unc_cpt_lzh_fork`, `cpt_rle_push`,
`unc_cpt_rle_fork`), shared with `src/fmt_dd.c` method 8.

No non-copyleft description of the format exists, so this row is for
speed and does not touch the licence; say so in its DECISIONS.md entry.
The 2026-09-19 `UNC_HOT` bought 14.8 %; the remaining shape is that every
LZ output byte goes through an out-of-line state machine
(`cpt_rle_push`) one byte at a time. Candidates: write LZ output into the
window and run the RLE over RUNS out of it, the way the LZ coders now
flush; or inline the common case (state NONE, byte ≠ 0x81) at the two
production sites and keep the call for the rest. The docs record that an
inline fast path lost twice when the baseline had no call; here the
baseline has one per byte, which is a different situation — measure.

**Fixture:** `derived-XferIt_1.5b4.sea`, 10,409 → 8,884 ticks today.
**Acceptance:** 108 Compact Pro fixtures byte-exact, `tools/run_segments.py`
(Compact Pro segments), DiskDoubler method 8 fixtures, ticks lower, heap
not up (24 KB today).

## Item 4 — static LZH from lhasa (ISC)

**Files:** `src/fmt_lzh.c` (`lzh_static`, `lzh_read_code`,
`lzh_read_literal_code`), possibly `src/unc_lzdyn.c` for `-lzs-`/`-lz5-`
if they live there.

`reference/lhasa/lib/` implements `-lh4-`..`-lh7-`, `-lzs-`, `-lz5-` under
the ISC licence (`lh5_decoder.c`, `lh6_decoder.c`, `lh7_decoder.c`,
`lz5_decoder.c`, `lzs_decoder.c`, `tree_decode.c`). Write from lhasa,
keep our `UncCanon` fast tables and bit reader (they are ours and
measured), keep MacLHA's MacBinary split and the window sizing from the
entry. `-lh2-`/`-lh3-` have no permissive reference (lhasa has neither;
LHa for UNIX's licence is its own) and no corpus archive: leave
`unc_lzdyn.c` alone.

**Fixtures:** the 8 `.lzh` fixtures and `tools/run_lzh.py` (182 archives
from fourteen writers, plus LHa 1.14i's own sets). Ticks on
`lhasa-unix114i-h2_lh7.lzh` (41 KB peak, `-lh7-`).
**Acceptance:** all of the above byte-exact, ticks within noise or
better, CODE not up.

## Item 5 — LZW from Welch, and the canonical code from any textbook

**Files:** `src/unc_lzw.c`, `src/unc_huffman.c` (`unc_canon_build_ext`,
`unc_canon_decode`; `unc_huff_read_tree` is macutils' as much as
XADMaster's).

Licence-only; expect neutral. The compress(1) stream is public (9–16 bit
codes, LSB-first, code 256 clears in block mode, the 8-code-group
padding after a clear that XADMaster calls "dumb" and that is a fact
about compress). The chain-walked-once and width-schedule sizing are ours
and stay. Write the decoder from the algorithm, keep the interface, A/B
against the current file on `popper-1.7.tar.Z`, `derived-xmasbeeps.sit`
(StuffIt method 2), `arc2pak1.pak` (ARC's LZW methods), DiskDoubler
method 1. If it is not at least equal in ticks, keep the old one and
record the attempt.

## Item 6 — re-cite the container parsers

**Files:** `src/fmt_binhex.c`, `fmt_macbinary.c`, `fmt_applesingle.c`,
`fmt_exo.c`, `fmt_sitseg.c`, `fmt_zipseg.c`, `fmt_stubs.c`, `NOTICE`.

These cite XADMaster for FACTS: the BinHex alphabet (RFC 1741), the
MacBinary header (the MacBinary II/III specification), AppleSingle's
magic and entry table (RFC 1740), zip's records (APPNOTE.TXT), gzip's
header (RFC 1952), ustar (POSIX.1). Re-derive each cited fact from the
public document, cite that, and keep XADMaster only where it is the sole
source of a fact — the StuffIt segment header, the MacBinary I heuristics
and the CRC fallback for buggy encoders, the "less than 256 parts"
assumption. A comment change, no code, no measurement; `ci.sh` for the
docs check. Update NOTICE's first paragraph to list what still owes
XADMaster code once items 1–5 have moved.

## Bonus — pin the two A/UX DART specimens

OPEN_ITEMS.md, *Two real DART "best" archives*: fetch the StuffIt from the
Macintosh Garden FTP into `reference/` (or the fixture cache), unpack the
two members with this engine's own CLI, add a `fixtures/SOURCES.md` row
each, and two cases in `tools/run_dart.py` asserting the raw volume's
DC42 checksums (E257EF53, 3DF12BA6) and that the 72-block header path was
taken. MacMount's `tools/get_real_samples.py` has the member SHA-256s.

---

## Reporting, so the work can be assessed afterwards

For each item, one commit (or a short series) whose message carries the
four-axis table, and a DECISIONS.md entry with the same table, the
reference it was written from, and what was NOT claimed. The assessment
that follows will re-run the ticks on one fixture per item, diff the
outputs of old and new against each other on the corpus, and read the
new file against the reference it names. A row that turned out neutral
and was therefore NOT taken is a result too: record it in DECISIONS.md
and strike it from OPEN_ITEMS.md's inventory with the number.
