# FORMATS.md — format support matrix

Status after M0–M9. "Oracle coverage" = fixtures with byte-exact
differential manifests (built from The Unarchiver's `unar`; see
TESTING.md); every one passes, plus 10 corruption variants each in the
robustness suite. "Peak RAM" = allocator high-water mark across the
whole corpus for that format (engine allocations only, via
`unclassic t --stats`).

| Format | Status | Methods | Oracle coverage | Peak RAM | 400 KB budget |
|---|---|---|---|---|---|
| MacBinary I/II/III | extract | — | 225 fixtures | 8 KB | full |
| AppleSingle/Double | extract | — | (unit tests + envelopes) | 8 KB | full |
| BinHex 4 (.hqx) | extract | RLE90 | 179 fixtures | 8 KB | full |
| PackIt (.pit) | extract | store, Huffman; encrypted detected | 4 fixtures (1 real + 3 synthetic PMa4) | 9 KB | full |
| Compact Pro (.cpt) | extract | RLE, LZH+RLE | 106 fixtures | 19 KB | full |
| StuffIt classic (.sit) | extract | 0 store, 1 RLE90*, 2 LZW, 3 Huffman, 5 LZAH, 8 MW, 13 LZSS+Huffman; 6 fixed-Huffman NOT implemented‡; encrypted detected | 211 fixtures | 76 KB | full |
| StuffIt 5 (.sit) | extract | 0, 13, 15 Arsenic; encrypted detected | 31 fixtures | 0.16–2.53 MB† | 11 of 31 fixtures extract FULLY; the rest refuse per entry |
| Zip | extract | store, deflate; others & encrypted per-entry errors | 3 fixtures (+2 PKZIP-1.x corpus-only) | 66 KB | full |
| Gzip | extract | deflate | 3 fixtures | 51 KB | full |
| Unix compress (.Z) | extract | LZW ≤16 bit | 4 fixtures | 268 KB | full |
| Tar (ustar/v7) | extract | — (links reported unsupported) | 3 fixtures (2 real 1990 v7 tars) + unit tests | 8 KB | full |
| StuffIt X (.sitx) | detect only | — | — | — | — |
| DiskDoubler (DD, DDAR, DDA2) | detect only | — | 4 sniffed | — | — |
| Now Compress | detect only | — | 1 sniffed | — | — |
| LZH/LHA (-lh?-, -lz?-) | detect only | — | — | — | — |
| DiskCopy 4.2 (.image) | detect only | — | synthetic 800K GCR + real 800K image; 0 false positives in 803 fixtures | — | — |

\* **Method 1 does occur** — once, a 470-byte resource fork in
`derived-New_Python.sit` — contrary to what this footnote said until
2026-08-01. The engine extracts that whole archive cleanly, every CRC-16
verified, so method 1 *is* exercised against a real file. What it has no
ORACLE coverage for is the same fixture: `unar` fails on it ("Attempted to
read more data than was available" on `It's A Bit Runny Sir`), so
`make_manifests.py` refuses a manifest and the differential suite never sees
it. Method 1 is therefore pinned by unit tests transcribed from
XADRLE90Handle *plus* one real archive checked against its own checksums —
not by the oracle.

‡ **Method 6, "Fixed Huffman", is present in the corpus and NOT implemented.**
`derived-INITLoader.sit` carries one 34,818-byte method-6 fork; the engine
returns a clean per-entry "recognized but unsupported". The name comes from
`reference/XADMaster/XADStuffItParser.m:284`; XADMaster does not implement it
either (`//case 6: fixed huffman`, line 319), which is why that fixture has no
manifest and why the gap went unnamed here until 2026-08-01. One fixture, one
fork, in a corpus of 344 StuffIt archives.

† **Every real Arsenic block is 512 KB.** The block size is `1 << (v+9)`
with `v` read from the stream, so other sizes are legal, but across the
31-fixture StuffIt 5 corpus **all 484 Arsenic streams — one per compressed
fork — declare 512 KB** (`v` = 10, blockbits 19). Measured directly by
instrumenting the point where `sit_arsenic.c` reads `v`, not inferred.

A note here previously claimed the blocks were "128 KB (14 fixtures,
dominant), 256 KB (9), 512 KB (8)". That was **wrong**, and the way it
went wrong is worth keeping: it was inferred from peak heap via
"peak ≈ 5× block", which does not hold, because only the *block* is
allocated at its declared size —

    peak  =  ~35 KB parser state  +  512 KB block  +  4 × actual block fill

— the inverse-BWT transform vector is sized to how much of the block the
entry actually fills (`transform = numbytes * 4`, `sit_arsenic.c:327`),
which is exactly what lets a small Arsenic entry fit a small budget. A
fixture peaking at 0.64 MB is therefore a 512 KB block holding ~24 KB,
not a 128 KB block; dividing by five turned every small payload into an
imaginary small block. Peak heap can never recover the declared block
size, so the claim was not just false but unmeasurable that way.

Measured peak heap over the corpus (`unclassic t --stats`): **min
0.16 MB / median 0.60 MB / mean 0.96 MB / max 2.53 MB**, the maximum
being the entries that genuinely fill a 512 KB block (35 KB + 512 KB +
2048 KB). **11 of the 31 fixtures now extract completely under a 400 KB
budget**, and 18 fit the ~700 KB a 1 MB Mac Plus has free.

Those figures improved on 2026-08-03, when the block stopped being allocated
at its DECLARED size. `blockbits` says 512 KB on every real stream, but the
fill varies enormously — the fixture that peaked at 643 KB was a 512 KB
allocation holding 24 KB — so the block is now grown on demand
(`ars_block_reserve`) and peak is `~35 KB parser + capacity + 4x fill` rather
than `~35 KB + 512 KB + 4x fill`. The previous figures were min 0.63 / median
0.97 / mean 1.23 MB with **every** entry over a 400 KB budget. Nothing about
the format or the decoder changed; only what is allocated to hold it. See
DECISIONS.md.

On a **1 MB Mac Plus** Arsenic is no longer mostly out of reach. It got there
in two steps, both of which were about not paying for memory the data does not
use rather than about the decoder:

- **2026-08-02** — the shell stopped reading the whole archive into RAM before
  the engine was given a budget, so each archive got its own size back.
- **2026-08-03** — the Arsenic block stopped being allocated at its declared
  512 KB and is grown to what each block actually holds, which is often a
  small fraction of it.

All six extract byte-exact at 4 MB.

Until 2026-08-02 the boundary was **the size of the archive** rather
than anything about the archive's contents, because the shell read the
whole thing into RAM before the engine got a budget — so a 202 KB
archive had 202 KB less to work with. That is gone: the archive is read
from the file as the engine asks for it, and every fixture got its own
size back in budget. The effect was large. `derived-Library_ISBN_Barcoder.sit`
went from refusing all 34 entries to extracting 31 of them, and
`derived-RWAsm_Folder.sit` from 36 of 38 to all 38. See the two Mini vMac
sections below for the per-fixture outcomes, and DECISIONS.md for why the
slurp existed and why it does not any more.

## Envelope auto-unwrap

`unclassic x` unwraps chained envelopes by content sniffing
(never by extension): MacBinary, BinHex, AppleSingle/Double, gzip and
.Z layers that yield exactly one file are recursively extracted and
the intermediate deleted (`-nr` disables; depth ≤ 8). Verified chains:
`.sit.bin`, `.sit.hqx`, `.tar.Z` (tools/run_unwrap.py, in CI).

## Hardening

- Differential: 769 fixtures byte-exact against `unar` manifests
  (both forks + type/creator), `./ci.sh`. That is every committed
  manifest whose format the engine extracts: 774 manifests less the 5
  detect-only DiskDoubler/Now Compress ones the harness skips. (A
  headline figure of 771 stood here for a while; `run_diff.py` prints
  the number it actually ran, and it is 769.)
- Robustness: 10 truncation/bit-flip variants per fixture — no
  crashes, hangs, or sanitizer trips under
  ASan+UBSan+`-fsanitize=alignment` (`-fno-sanitize-recover=all`).
- Fuzz: seeded mutation/splice/garbage fuzzing (tools/fuzz.py);
  4,000 cases clean at M9, 150-case smoke in every CI run.
- 32-bit `-m32` build runs the full suite (68000 discipline: no
  unaligned access, no recursion, 32-bit arithmetic in hot paths).

## Measured on a 7 MHz Mac Plus (Mini vMac 1x, System 6.0.8, 4 MB)

The first absolute timings this project has ever had. `run.py --emu mv-4M-1x`
separates boot from extraction — the application paints its "alive" grid
before touching a disk — so the extract column is the archive alone. Poll
interval 5 s, so that column is quantised to 5 s; it is an upper bound at this
resolution, not a stopwatch.

| Fixture | Format | In | Boot | Extract |
|---|---|---|---|---|
| derived-Export.sit | StuffIt | 1.6 KB | 10 s | 5 s |
| synth-packit-2.pit | PackIt | 3.4 KB | 10 s | 5 s |
| derived-keyAhead.cpt | Compact Pro | 0.9 KB | 10 s | <5 s |
| export-hc.hqx | BinHex | 3.1 KB | 10 s | 5 s |
| stuffit151mstr.bin | MacBinary | 0.5 KB | 10 s | <5 s |
| synth-exo-zip-store.zip | Zip | 8.4 KB | 10 s | 5 s |
| synth-exo-tar.tar | Tar | 20 KB | 10 s | 5 s |
| synth-exo-gz.gz | Gzip | 0.1 KB | 10 s | <5 s |
| macburger-helper.hqx | BinHex | 306 KB | 30 s | **150 s** |

**8/8, and the shape is the useful part: for small archives the BOOT dominates
and extraction is seconds.** A stripped System 6.0.8 reaches the application in
about 10 s; everything in this table then extracts in under five. The one
larger 1x measurement that exists — `derived-EmpireBuilderDemo.sit`, 278 KB in
and 417 KB out — took **~134 s**. So a few kilobytes is instant, a quarter of a
megabyte is a couple of minutes.

**The large BinHex is not an anomaly.** `macburger-helper.hqx` was written up
three times as one — it never finished inside the timeouts chosen for it — and
it simply takes 150 s. Instrumenting the engine's byte counter
(`-D UNC_AT_PROGRESS`) showed why the timeouts misled: the rate is very
non-uniform, 16% of the input in the first seven minutes and the last 205 KB
in a hundred seconds. See BLOCKERS.md.

## Relative decode cost per format (Linux, same engine)

Absolute Mac Plus timings are still missing (BLOCKERS.md says why), but the
engine's *relative* cost is a property of the code and transfers to any CPU as
a ratio. Measured with `unclassic t`, best of three, on the release build:

| Fixture | Format | In KB | Out KB | ms | in KB/s |
|---|---|---|---|---|---|
| kermitut9test.bin | MacBinary | 297 | 296 | 0.6 | 485,802 |
| derived-PCCTS.tar | Tar | 280 | 231 | 0.6 | 439,603 |
| derived-PackIt.pit | PackIt (stored) | 60 | 60 | 0.7 | 85,110 |
| macburger-helper.hqx | BinHex | 299 | 253 | 2.9 | 102,708 |
| derived-MUSFMT10.ZIP | Zip (deflate) | 168 | 498 | 3.9 | 42,704 |
| popper-1.7.tar.Z | Compress | 58 | — | 2.0 | 29,526 |
| PCCTS.tar.gz | Gzip | 62 | — | 2.0 | 31,162 |
| derived-EmpireBuilderDemo.sit | StuffIt (13) | 272 | 407 | 9.0 | 30,204 |
| derived-XferIt_1.5b4.sea | Compact Pro | 279 | 926 | 18.2 | 15,351 |
| derived-KeyGraphics.sit | StuffIt 5 (Arsenic) | 5 | 33 | 1.6 | 2,859 |

The ordering is the useful part: envelope formats (MacBinary, tar) are
essentially a copy; BinHex costs a few times that; the real compressors —
StuffIt 13 and Compact Pro's LZH — are 15-30x the cost of a copy per input
byte; and Arsenic is in a class of its own, two orders of magnitude off the
top of the table, which is consistent with its memory profile.

**This is not a Mac Plus timing.** It says a Compact Pro archive costs roughly
six times what a BinHex of the same size costs, on any CPU. The one authentic
1x measurement that exists — `derived-EmpireBuilderDemo.sit`, ~134 s for
278 KB — is in the StuffIt-13 row, so the ratios can be used to reason about
the others, cautiously and from a single anchor.

## Real-hardware verification (Mini vMac — System 6.0.8, 4 MB Mac Plus, 68000)

The Retro68 Mac shell was replayed against a 44-fixture sample spanning all
twelve formats on a **real System 6.0.8 / 4 MB Mac Plus** under Mini vMac
(a true 68000). Every extraction is verified ON THE MAC ITSELF: the app
CRC-32s both forks after reading them back through the File Manager and the
result — painted to the framebuffer, read from a screenshot — is
cross-checked against the same engine's Linux output (`tools/vmac_check.py`,
`tools/decode_grid.py`).

**44/44 byte-exact PASS** — data forks exact, resource forks exact bar the
OS-stamped reserved header (bytes 16–127). Re-run 2026-08-01 and reproduced,
with a caveat about the harness rather than the Mac: two fixtures came back
`EMUDIED` on the first pass — the emulator PROCESS exited within five seconds,
before the application could paint anything — and both passed on an immediate
re-run. That verdict now exists precisely so this is not mistaken for a
Mac-side failure again (`tools/vmac/README.md`). The sample is
`tools/vmac/sample.txt`; reproduce with

    tools/vmac/setup.sh                              # once
    tools/vmac/run.py --list tools/vmac/sample.txt   # 4 MB

An earlier record of this run reported 39/44 — four timeouts and one
unexplained failure (`derived-RWAsm_Folder.sit`, errors on all 38 entries).
Neither survives on the rebuilt harness: all four "timeouts" complete, and
RWAsm_Folder extracts its 38 entries byte-exact at the same 643.2 KB peak
the failing run reported. The old harness was not committed and no longer
exists, so what differed cannot be established; the numbers here are the
ones that reproduce.

Note that the emulator now runs **all out** rather than at Mac Plus speed,
so this harness measures correctness only — **no timing claim about a 7 MHz
68000 can be drawn from it**, including the previously recorded "185 s".

On-Mac engine peak heap (high-water mark) by format, matching the Linux
`--stats` figures:

| Format | on-Mac peak heap |
|---|---|
| MacBinary / BinHex / Tar | 8 KB |
| PackIt | 9 KB |
| Compact Pro | 19 KB |
| Zip | 12–65 KB |
| Gzip | 51 KB |
| StuffIt classic | 72–75 KB |
| Unix compress (.Z) | 268 KB |
| StuffIt 5 (Arsenic) | 0.63–2.53 MB (block *fill* dependent — see †) |
| DiskDoubler / Now Compress | detect-only — no allocation, cleanly not extracted |

## System 7 tier (Mini vMac — System 7.0.1, 4 MB Mac Plus, 68000)

Until 2026-08-01 every on-Mac result in this repository came from one point of
the System 6 → Mac OS 9 range the project claims: System 6.0.8. This is the
second point.

**System 7.0.1, not 7.1.** 7.1 survives on the mirrors only as floppy disk
sets and a beta ISO, and installing from emulated floppies is hours of GUI
automation for a system that differs in nothing this project exercises. What
matters is that it is System 7 rather than 6, because two things only exist
above System 6: Standard File returns a **working-directory** reference in
`SFReply.vRefNum` rather than a plain volume refNum, and the Process Manager
is always running, so the `SIZE` partition governs the launch. Mini vMac's
Mac Plus supports up to 7.5.5, so this is the same 68000 as every other row.

**44/44 byte-exact PASS at 4 MB** — the same committed sample, the same on-Mac
CRC-32 read-back, the same twelve formats:

    tools/vmac/run.py --system Sys7.img --list tools/vmac/sample.txt

Engine peak heap is **identical to System 6.0.8 on every fixture** (e.g.
`derived-RWAsm_Folder.sit` 643.2 KB, `derived-Library_ISBN_Barcoder.sit`
1810.8 KB, `derived-PuzzleGetter_0.8.sit` 710.6 KB), which is the expected
result — the engine allocates through the same callback and never asks the
system for anything — but it had never been shown.

**System 7.0.1 does not run at 1 MB at all.** A 1 MB probe painted nothing in
180 s: not a failed extraction, a system that cannot boot. System 7 wants 2 MB
and the floor-target machine has half of it. This is not a defect in the
application and there is no 1 MB row for this tier — **the 1 MB floor target
is System 6, and only System 6.** The application's own memory floor is
unchanged and is still demonstrated by the 41/44 System 6.0.8 run below.

## Floor target verification (Mini vMac — System 6.0.8, **1 MB** Mac Plus, 68000)

The same 44-fixture sample was replayed on a Mini vMac built for **1 MB of
RAM** — the project's floor target — one boot per fixture, same on-Mac
CRC-32 verification (`tools/vmac/run.py --mem 1M --list tools/vmac/sample.txt`).
The engine budget is derived from `FreeMem` at startup.

**41/44 byte-exact PASS.** Every fixture that does not pass is a StuffIt 5
memory-budget refusal, and each of the three now misses exactly **one** entry —
the one whose block genuinely fills. All three pass at 4 MB:

| Fixture | Format | Outcome at 1 MB | Peak heap |
|---|---|---|---|
| derived-KeyGraphics.sit | StuffIt 5 | all 1 entry byte-exact | 176.8 KB |
| derived-RWAsm_Folder.sit | StuffIt 5 | **all 38 entries byte-exact** | 163.2 KB |
| derived-PuzzleGetter_0.8.sit | StuffIt 5 | **all 26 entries byte-exact** | 262.6 KB |
| derived-Library_ISBN_Barcoder.sit | StuffIt 5 | 33 of 34 entries, 1 refused | 419.6 KB |
| derived-Troi-ClipSave-Plug-in1.1.sit | StuffIt 5 | 12 of 13 entries, 1 refused | 474.0 KB |
| derived-a2basic.dmg.sit | StuffIt 5 | clean per-entry refusal (1/1 entries) | 419.6 KB |

**This tier moved twice in two days, both times by not paying for memory the
data does not use.** On 2026-08-02 the shell stopped reading the whole archive
into RAM before the engine got a budget (39/44 → 40/44). On 2026-08-03 the
Arsenic block stopped being allocated at its declared 512 KB and is grown to
what each block actually holds (40/44 → 41/44). The peaks in the table are the
clearest measure: `derived-RWAsm_Folder.sit` went from 595.7 KB at the start of
this to **163.2 KB**, for the same 38 byte-exact entries.

**The three remaining refusals are the expected, accepted tier** (see †
above): an Arsenic entry needs its block plus four bytes of transform vector
per byte the block holds, and an entry whose block really does fill 512 KB
needs about 2.5 MB, which a 1 MB Mac cannot give. The engine declines *that
entry* and carries on, which is why two of the three still deliver 33 of 34
and 12 of 13 files. `derived-a2basic.dmg.sit` refuses everything only because
everything is one entry.


**`popper-1.7.tar.Z` and `PCCTS.tar.gz` used to fail here and no longer do.**
The Mac sink previously accumulated each whole output fork in a `NewPtr`
block and wrote it in `sink_end`, so the shell needed `archive + engine peak
+ largest output fork` — and those two fixtures have the sample's largest
output forks (174 KB and 287 KB), which a 1 MB machine could not spare. The
sink now writes each chunk straight to the File Manager as the engine
produces it, so **the shell's own RAM use no longer depends on output size
at all**. Both fixtures are byte-exact at 1 MB, with the engine's peak heap
unchanged. The old path is still buildable (`UNC_MAC_STAGE_WRITES`) and both
are byte-exact through the qemu-m68k mock in CI.

What unblocked all of this was rewriting the File Manager calls to use
explicit, fully-zeroed HFS param blocks. This was originally attributed to a
broken Retro68 `HOpen` glue; **that attribution has been withdrawn** — a
standalone minimal reproduction (`tools/retro68-hopen-repro/`) disproved it.
See DECISIONS.md and BLOCKERS.md.

## Mac OS 9 tier (QEMU PowerPC — Mac OS 9.2, `mac99`, 512 MB, 68LC040 emulation)

The third and last point of the System 6 → Mac OS 9 range the project claims,
and the only one where the 68k binary does not run on a 68k CPU: Mac OS 9.2 on
emulated PowerPC executes it through the **68LC040 emulator** built into the
system. Nothing above System 7 had ever run it.

**13/13 byte-exact** — `tools/vmac/os9sample.txt`, one fixture per format,
each in its own boot from a pristine copy of the master image:

    tools/vmac/os9.py --setup                                   # once
    tools/vmac/os9.py --list tools/vmac/os9sample.txt -o <dir> --launch

| fixture | format | files | data bytes | rsrc bytes | result |
|---|---|---|---|---|---|
| `export-hc.hqx` | BinHex | 1 | 1,615 | 0 | ✅ byte-exact |
| `derived-keyAhead.cpt` | Compact Pro | 1 | 0 | 1,233 | ✅ byte-exact |
| `synth-exo-Z.Z` | compress | 1 | 2,200 | 0 | ✅ byte-exact |
| `synth-exo-gz.gz` | gzip | 1 | 2,200 | 0 | ✅ byte-exact |
| `stuffit151mstr.bin` | MacBinary | 1 | 0 | 365 | ✅ byte-exact |
| `synth-packit-2.pit` | PackIt | 5 | 3,050 | 2,020 | ✅ byte-exact |
| `derived-Export.sit` | StuffIt | 1 | 6,944 | 0 | ✅ byte-exact |
| `derived-DDT.sit` | StuffIt with a resource fork | 2 | 1,473 | 3,504 | ✅ byte-exact |
| `derived-KeyGraphics.sit` | StuffIt 5 / Arsenic | 1 | 0 | 33,484 | ✅ byte-exact |
| `derived-XferIt_1.5b4.sea` | Compact Pro self-extracting | 10 | 679,423 | 268,752 | ✅ byte-exact |
| `derived-DandStoQIF2.sea` | DiskDoubler: must REFUSE | 0 | — | — | ✅ declined, as Linux does |
| `synth-exo-tar.tar` | tar | 4 | 7,788 | 0 | ✅ byte-exact |
| `synth-exo-zip-deflate.zip` | zip | 4 | 7,788 | 0 | ✅ byte-exact |

**13/13**, 32 files, 712,481 data bytes and 309,358 resource-fork bytes compared.

Two things differ from the Mini vMac tiers, and both make this check stronger
rather than weaker:

- **The result is read off the disk, not the screen.** The transfer volume is
  a file on the host, so after the emulator exits both forks of every
  extracted file are lifted out with hfsutils and compared **byte for byte**
  against `unclassic x -nr`. The Mini vMac tiers compare an on-screen CRC-32
  aggregate because getting a floppy back out mid-run is awkward; nothing here
  needs that.
- **Output names, folder structure and 8-bit characters are compared.** A
  summed CRC cannot carry a name, so the System 6 and 7 tiers have never
  checked one and cannot be made to fail on one. This tier does, and its first
  sweep immediately caught a real Mac-shell defect in the gzip/.Z fallback
  name — now fixed (BLOCKERS.md, DECISIONS.md). `derived-XferIt_1.5b4.sea`
  alone lands 10 files three folders deep, and PackIt's `Appé` is a MacRoman
  name that has to survive the round trip.

**The sample is small on purpose.** Each fixture costs a whole boot (~110 s on
an idle host, plus a 2 GB image copy), where Mini vMac replays a 44-fixture set
inside one boot. So this samples for breadth of format; the memory-budget
spread that `sample.txt` exists to exercise is a 1 MB question, and this
machine has 512 MB.

**The Finder is driven from the keyboard.** The pointer does not work in this
guest at all — five mouse primitives measured at exactly zero effect, cursor
pinned to screen corners. See BLOCKERS.md, and `tools/vmac/os9probe.py` for
the measurement.

### Onto HFS+ (the same machine, the boot volume instead of the transfer disk)

Everything above extracts onto the transfer volume, which is HFS. The OS 9
boot volume is HFS+, so `--hfsplus` renames it to `Out` from the keyboard and
runs the **autotest** build against it: the extraction lands on HFS+, and the
application CRC-32s both forks after reading them back through the File
Manager, exactly as the Mini vMac tiers do.

    tools/vmac/os9.py fixtures/derived-Berkeley_Packet_Monitor.sit \
                      -o <dir> --hfsplus

| fixture | files | data | rsrc | peak heap | result |
|---|---|---|---|---|---|
| `derived-Berkeley_Packet_Monitor.sit` | 31 | 372,301 B | — | 779.1 KB | ✅ CRC + length identical to Linux |
| `derived-XferIt_1.5b4.sea` | 10 | 679,423 B | 268,752 B | 18.8 KB | ✅ CRC + length identical to Linux |

Both report `ret=0` with zero per-entry errors, and every output **name** on
HFS+ is exactly what the 31-character rule predicts — including the one entry
in the Berkeley fixture whose name is 34 characters and must be truncated. A
68k application reaching HFS+ through the classic File Manager is capped at 31
characters just as it is on HFS, so HFS+ changes nothing here; that is the
result, and it was worth measuring rather than assuming.

Two things make this tier trustworthy:

- **The answer comes back as a file, not off the screen.** `at_report()` pokes
  1bpp pixels straight at the framebuffer — the right channel on a Mac Plus,
  and invisible on OS 9's 32-bit screen (confirmed by screenshot: the desktop
  is untouched after the run finishes). `at_report_file()` writes the same
  values, plus every output name, to the plain-HFS input volume. That is what
  made HFS+ reachable at all: the output volume was never the obstacle, the
  reporting channel was.
- **That the output really landed on HFS+ is measured.** The boot volume is
  HFS+ inside an HFS wrapper, and hfsutils can see only the wrapper. After the
  run the wrapper still contains exactly one file,
  `Where_have_all_my_files_gone?` — so none of those 41 files went to plain
  HFS. A signature word was considered and rejected: the classic File Manager
  reports `'BD'` for an HFS+ volume for compatibility, so a negative would
  prove nothing.

One corroboration falls out of it: the Mac's **unmasked** resource-fork CRC
equals Linux's **masked** one, so Mac OS 9 leaves the 112-byte reserved header
area alone where System 6 stamps it — the same thing the byte-level comparison
found on the HFS tier.

### The `SIZE` partition under OS 9's Process Manager

Built with a 600 KB preferred partition and run against
`derived-KeyGraphics.sit`, which needs ~656 KB: **1 entry refused, 0 files,
`ret == UNC_OK`, peak heap 35.5 KB** — the same figure System 7.0.1 gives, on
a machine with 512 MB of RAM. The partition governs, not the hardware, and
35.5 KB is parser state alone: the 512 KB Arsenic block was declined at
request time, never allocated. Method and the three-system table in
MANUAL_TESTS.md.

**Still not covered here:** names HFS+ permits that HFS does not — probably
unreachable through the classic File Manager at all, since it caps at 31
characters on either filesystem, but that is unproven either way. Real PowerPC
silicon, like real 68k silicon, remains untouched.
