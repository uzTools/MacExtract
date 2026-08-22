# BLOCKERS.md

## Status

**No open blockers.** The engine and Linux CLI were never affected by anything
in this file. The Retro68 Mac shell runs and extracts byte-exact on every
system the project claims:

| tier | result |
|---|---|
| System 6.0.8, 4 MB Mac Plus (Mini vMac, a true 68000) | **62/62** sampled fixtures |
| System 6.0.8, **1 MB** — the floor target | **62/62**; no memory-budget refusals remain, and DiskDoubler method 5's 396 KB allocation succeeds here |
| System 7.0.1, 4 MB | **62/62** |
| Mac OS 9.2 (QEMU PowerPC, 68LC040 emulation) | 13/13, plus HFS+ and the `SIZE` partition; DiskDoubler still recorded there as the refusal it was pre-M12 |

All three Mini vMac tiers re-run **2026-08-22**, with M15–M23's codecs in
and three fixtures added to the sample for them — DiskDoubler methods 3, 4
and 5, which nothing in the list had exercised. Per-fixture tables and how
the sample grew: FORMATS.md. How to re-run any of
it: `tools/vmac/README.md`. What no emulator here can settle:
MANUAL_TESTS.md.

---

## What is true, and load-bearing

**How the Mac shell is verified.** The autotest build CRC-32s both forks after
reading them back through the real File Manager and paints the aggregate to
the framebuffer; the host decodes a screenshot and compares against the same
engine's Linux output. Since 2026-08-02 the Out volume is also read directly,
which adds the one thing an aggregate cannot carry — **names**. The off-Mac
blind spot is real: the qemu-m68k mock calls the sink directly and never
touches the Toolbox glue, so only Mini vMac exercises that layer.

**The fix that unblocked M10 — and what is still unknown about it.** Driving
the File Manager through explicit, fully-zeroed HFS param blocks
(`PBHOpenSync` / `PBHOpenRFSync` / `PBHCreateSync` / `PBHDeleteSync`)
unblocked everything at once and is what ships. **Why it worked is not
established.** The original attribution — a broken Retro68 `HOpen` — was
disproved (below). The likeliest remaining explanation is that the helpers
zero the whole param block where the pre-fix code passed partly-uninitialised
state, but that has never been reduced to a reproduction, so it is a guess and
not a finding. It is not being chased: the app is verified byte-exact as it
stands.

The one upstream finding that survived: **both `OpenDF` and `HOpenDF` return
`paramErr` on System 6**, because the `_OpenDF` trap is System 7 and neither
has a fallback — `FSOpen`, in the same glue file, does. Written up in
`tools/retro68-hopen-repro/ISSUE.md`, deliberately not filed; the maintainer
will post it.

**`HideCursor()` before drawing the grid — CONFIRMED, with a reproduction.**
Built without it and with the host pointer dragged through the grid's cell
centres, the decoded result comes back as `0x04000000` — one flipped bit, a
cell stamped over by the cursor's saved background. The stock build survives the same drag.
Reproduced twice. The two things that must be right before the test means
anything are in `tools/vmac/README.md`; both early attempts "passed" while
testing nothing.

**Detect-only gap — RESOLVED.** DiskCopy 4.2 was named in `unc_sniff` and
never detected, for want of a reference. One was obtained
(`reference/notes/DiskCopy42.md`) and the probe is real: a synthetic 800K GCR
image and a real one match, 0 false positives across the corpus. Still
detect-only — disk images are out of scope for v1.

---

## Withdrawn claims

**Kept deliberately, and this is the part of the file to read first.** Twice a
live claim has been re-tested *because* it sat beside an already-withdrawn one,
and one of those was worth 39/44 → 40/44 at the floor target. Eight mechanisms
keep finding the next one, and two of them need no insight at all:

- a live claim sitting next to an already-withdrawn one;
- **two files disagreeing** — a cross-file contradiction is a disproof nobody
  has collected yet;
- a limitation written one paragraph from its own remedy;
- **a limitation stated about the environment that is true only of one tool.**
  Read every "cannot be done here" for the name of the tool it is really about;
- **somebody else complaining about the tool you grade yourself by.** Added
  2026-08-21: a test corpus's README said `unar` was "hit-or-miss" on
  DiskDoubler Pro and that the same files unpacked fine on the Mac. That is a
  bug report against the oracle, written by someone who had already ruled out
  the files;
- **inputs from outside the corpus.** Added 2026-08-21: nine archives nobody
  here had seen, and five of them failed in the first minute (below). A suite
  that is green on the files it has says nothing about the files it has not,
  and this is the only mechanism here that needs no insight — just files.
- **what the corpus never does that the claim would allow.** Added
  2026-08-21: a rule inferred from the records it was drawn from fits every
  one of them, so counting those proves nothing. Count the records it does
  NOT cover instead — 30 `0x1000` entries fitted the claim and 45 in the same
  fifteen files contradicted it (below).
- **a harness that ends its runs differently from the harness beside it.**
  Added 2026-08-22: three SpaceSaver runs "measured unchanged" on a machine
  that never booted, because their image had been copied out of a KILLED
  emulator. `arcmac.py` had picked Special ▸ Shut Down for exactly that
  reason since the ARC specimens; nothing compared the two.

Each entry is what was claimed, what disproved it, and what it COST. The cost
line is what makes the next one worth re-testing.

| claim | disproved by | withdrawn |
|---|---|---|
| Retro68's `HOpen` glue is broken on System 6 | `tools/retro68-hopen-repro/`, 10 cases | 2026-07-25 |
| Three non-relocatable staging blocks bomb the Memory Manager | `UNC_AT_SEPARATE_BLOCKS` | 2026-07-25 |
| `derived-RWAsm_Folder.sit` fails on a 4 MB Mac Plus | committed harness re-run | 2026-07-25 |
| QuickDraw bombs after File Manager activity | `tools/quickdraw-repro/`, 12 configurations | 2026-08-01 |
| The OS 9 boot volume is plain HFS | `drEmbedSigWord` = `'H+'` | 2026-08-02 |
| Interleaved reads and writes on one volume return zeros | `UNC_AT_INTERLEAVE`, 3 read shapes | 2026-08-02 |
| Mini vMac's write-back is lazy and partial | `checkdisk.py`, 44/44 off the disk | 2026-08-02 |
| `pkill -9` never flushes; boot+kill corrupts the image | 11 boot+kill cycles | 2026-08-02 |
| The three 1 MB StuffIt 5 refusals each fill a 512 KB block | instrumenting `numbytes` where the transform vector is allocated | 2026-08-03 |
| Nine fixtures are ground truth the oracle cannot produce | `unar -k hidden`; all nine build, all 774 existing manifests unchanged | 2026-08-08 |
| There is no oracle for StuffIt method 6, and no second fixture to test one on | `macunpack` from `reference/`, and `tools/synth_sit6.py` | 2026-08-08 |
| Even `unar` fails on the two PKZIP 1.x zips, so they stay corpus-only | their own manifests: `unar` adjudicates 5 of the 7 entries | 2026-08-08 |
| The Macintosh application unwraps nested files (`.sit.hqx`) automatically | running it: one layer came off and it stopped | 2026-08-14 |
| No second implementation of Now Compress exists, so four forks cannot be graded | the archive is self-extracting: its own 1995 extractor agrees on every fork | 2026-08-16 |
| Nothing documents which fork an ArcMac payload starts with, and no oracle reads ArcMac | ArcMac 1.3c archiving a two-fork file under Mini vMac: data fork first | 2026-08-16 |
| Alysis SuperDisk! has no reference anywhere, so rule #1 forbids reading it | both corpus archives are self-extracting: the layout, the method table and every codec are inside them | 2026-08-20 |
| Nothing reachable writes DiskDoubler methods 1–5 or 7, so none can be graded | DiskDoubler 3.7 under Mini vMac writes method 1 from its own menu; its distribution disk ships two method 7 files | 2026-08-20 |
| The three DiskDoubler containers are read; the corpus exercises every one | nine archives from `ssokolow/diskdoubler-test-files`: five fail at their third entry, on a `DDA2` entry type neither we nor XADMaster implement | 2026-08-21 |
| The `SPLT` specimens are four parts across two sets | the same clone: six parts across three, the third with a 14 KB resource fork | 2026-08-21 |
| The Mac sample is 63 fixtures, and every tier result is 63/63 | counting the file: 63 lines, 59 distinct — four listed twice | 2026-08-21 |
| Macintosh Garden has DiskDoubler 3.7 and 4.x only | it also has 3.2 and DDExpand 2.03; 3.2's menu offers the same two software methods, and 2.03 is an expander | 2026-08-21 |
| The `0x1000` `DDA2` record is what DiskDoubler Pro writes for a file it could not shrink | the same fifteen archives hold 45 ordinary headers whose data fork is stored; all 30 `0x1000` records are the files with NO resource fork | 2026-08-21 |
| A `0x1000` record with a resource fork is waiting to be found | DiskDoubler 4.1.1 writes the form only for a fork-less file — all four cells of compressible x forked measured in one archive | 2026-08-21 |
| No DiskDoubler COMPRESSOR older than 3.2 is reachable, so methods 2-5 cannot be graded | WinWorld carries Salient's **3.1.2** distribution floppy (1991), which holds a method 2 fork | 2026-08-21 |
| DiskDoubler methods 3, 4 and 5 cannot be graded, because no specimen of them exists | the 1991 disk carries Salient's own expander: it reads forks THIS project encoded, and all three come back byte-exact | 2026-08-21 |
| 8 resource forks have no off-Mac oracle, so they cannot be ground truth | `unar`'s DDn reads ONE byte past the declared compressed length; give it one and it decodes all 33 forks byte-exact | 2026-08-22 |
| SuperDisk!'s compressor does not survive here, only its expander | Macintosh Repository has the 1991 `SuperDisk!` control panel; it installs, runs, and compresses on demand | 2026-08-22 |
| A matching name merely APPEARING does not fire SpaceSaver's rule — tested, fourteen minutes, unchanged | that run never booted: its own frames are the striped garbage screen, every one of them | 2026-08-22 |
| The `--namevol` run that did not boot was a one-off infrastructure failure | it reproduces exactly, and the cause is in the harness: the enrolled image was copied out of a KILLED emulator, so it is torn. Three runs were built on it | 2026-08-22 |
| SpaceSaver's trigger is known: rename a file to end in `small` and it compresses | four runs that booted AND flushed do it correctly and nothing compresses; the OTHER rename rule on the same page fires on the same event, turning `Forked` into a StuffIt archive | 2026-08-22 |

**DiskDoubler methods 1–5 and 7 "cannot be graded".** Declined per entry
since M12 on the grounds that no corpus fixture uses one and nothing reachable
writes one. The first half was true and the second was never tested. Running
the application says otherwise, twice over:

- **DiskDoubler 3.7's own Settings dialog offers exactly two software
  methods**, "Method A (fastest)" and "Method B (usually smaller)", and A
  writes **method 1** — Unix compress, which OPEN_ITEMS.md had already named
  as the cheapest one to add "if a fixture ever turns up". A fixture turns up
  in four minutes: `tools/vmac/diskdoubler.py --make A`.
- **Method 7 needed no emulator at all.** The 3.7 distribution disk ships two
  THINK C libraries compressed with it, because Salient built the disk on a
  machine with the Sigma Designs card fitted. They were sitting in a zip on
  Macintosh Garden the whole time, and each carries the checksum that grades
  it.

**Cost: two methods, and with method 1 the default output of DiskDoubler's own
era** — 3.7's fast setting, on a product that shipped from 1990. The smell is
the one this file already names: *a limitation stated about the environment
that is true only of one tool*. "No fixture in the corpus" was read as "no
specimen exists", and the corpus is 812 files that a URL harvester could
reach, not the set of DiskDoubler files in the world. The other half of the
same claim — that "the reference marks 3 and 4 unimplemented and 5 untested" —
was also wrong in the direction that mattered less: XADMaster implements 4 and
5 (untested) and macutils implements 3 (untested), so the references cover
three of the four methods still declined. What is missing for those is a
specimen, not code. (Method 2 was implemented on 2026-08-21, so the three
still declined are 3, 4 and 5 — and every one of them has a reference. Which
one covers which, read out of the source: OPEN_ITEMS.md.)

**`DDA2` was read as far as the corpus went, and the corpus stopped early.**
Not one of the six DiskDoubler fixtures is a `DDA2` holding a file DiskDoubler
Pro could not compress, so 809 green fixtures said nothing about the entry
type that describes one — and neither did the reference, which raises on it
too. **Cost: every DiskDoubler Pro archive containing a file that would not
compress, which is most archives that contain an image or a sound.** Five of
the nine real ones tried here. **No smell above found this one** — inputs
from outside the corpus did, which is a sixth mechanism and the only one that
needs no cleverness. What named the cause in minutes was the fifth.
DECISIONS.md 2026-08-21.

**"SuperDisk!'s compressor does not survive here, only its expander."** The
reason methods 10, 13 and 20 sat in *waiting on a file*. Macintosh Repository
carries the 1991 ` SuperDisk!` control panel — `cdev`/`AlyS`, an 89 KB
resource fork — and it is the half that compresses. It installs into
`System Folder:Control Panels`, opens under System 7 with Compress
(Off/Light/Tighter), Speed and Memory settings, and its "Make File" button
turned an 11,136-byte subject into a 2,372-byte `.x` on the first run that
reached it (`tools/vmac/sdcompress.py --compress`).

**Cost: three methods filed as ungradeable, on a sentence about what
survives that nobody had searched for.** The same site had already supplied
the Symantec DiskDoubler release earlier the same day. The smell is the
fourth again — a limitation stated about the environment — and the specific
correction is dull and repeatable: **"X does not survive" is a claim about
somebody's search, and it decays.**

What it did NOT close: the archives it writes are a container this engine has
never read — SuperDisk!'s single-file form, not the record stream the corpus
uses (DECISIONS.md 2026-08-22, later). The item moved from *waiting on a
file* to *waiting on a layout*, with the file now producible on demand.

**"These 8 forks have no second implementation."** `unar` refuses them,
macunpack has no DDn at all, and DiskDoubler's own expander only runs on a
Mac — which restamps a resource fork's bytes 16..127 as it writes it. Every
step true, and the conclusion still did not follow: **`unar`'s DDn reads one
byte past the fork's declared compressed length**, and the container is ours
to build. Declare one more, append a pad byte, and all 33 forks of the two
archives come back byte-for-byte equal to this engine and to what the Mac
produced outside the stamped window. `oracle-unadjudicated` fell from 24
forks across 12 fixtures to 16 across 10.

**Cost: eight forks carried as "not ground truth" since M12**, and an
OPEN_ITEMS entry that told three later sessions to go looking for an
implementation that was already installed. The smell is the fourth again — *a
limitation stated about the environment that is true only of one tool* — with
a twist worth naming on its own: the limitation was true OF that tool, on
that input. **An oracle that refuses one input may accept a presentation of
the same bytes.** What is fixed is the tool's bug; what was ours to choose
was what we handed it.

The bug is reduced to a 1,166-byte reproduction in
`tools/xadmaster-ddn-repro/`, because this file already records what
attributing a root cause without one costs.

**"Methods 3, 4 and 5 cannot be graded."** True of decoding, and the whole
question was pointed the wrong way. Grading a decoder needs a specimen;
grading a READING of the format needs an implementation, and Salient's own
`DiskDoubler™ App` comes off the 1991 disk uncompressed and runs. Encode a
fork, hand it to 1991, and it either expands to the bytes that went in or it
does not: all three do (`tools/vmac/ddencode.py --expand`), and 4.1.1
confirms method 5 a second time. **Cost: the last three methods of the
format, held behind a rule about oracles while the oracle was on the disk
that had just been downloaded for something else.**

The smell is the third in the list — *a limitation written one paragraph from
its own remedy*. OPEN_ITEMS.md said what was missing was "a file to grade a
decoder against" in the same entry that named two reference implementations;
what nobody asked was whether the grading had to run in that direction. The
sharper form: **an oracle you can only feed is still an oracle.**

It also found a second `#ifdef UNTESTED` that is untested in the worst way.
macutils declares method 3's escape byte as `#define ESC 0x144` — 324, which
no byte can equal — so its escape branch is unreachable and its method 3
copies input to output. Read as decimal 144 the algorithm is RLE90 exactly.
That is twice now in one file: **a reference marked untested can be untested
into a no-op, which counts as "implemented" to anyone counting references and
decodes nothing.**

**"No compressor older than 3.2 is reachable."** The reason methods 2-5 were
declined, and false. Salient's own **3.1.2** distribution floppy is on
WinWorld — 1991, 800K, SHA-1 published — and it carries **a method 2 fork**
(`XCMD.h`, 564 → 386 B), the only one anybody here has seen, plus 22 method 7
forks of up to eight chunks where the 3.7 disk's two hold one each. Method 2
is implemented and graded from it; the multi-chunk question closed with it.

**Cost: one of the eleven methods, for the life of the project**, and an open
item that read as "wait for somebody to find a file" when the file was one
page load away. The smell is the fourth in the list — *a limitation stated
about the environment that is true only of one tool* — where the tool was the
three sites somebody thought to search. All three are Macintosh archives;
WinWorld is a PC abandonware library that also carries Mac software, and
nothing had ever looked there. The sharper form, for next time: **when an
open item says what is missing is a FILE, search for the file and not for the
story.** Every search this project ran about DiskDoubler was about its
history, which is genuinely what dated methods 2-5 to the Salient era — and
which could never have returned a floppy image.

**The headerless `DDA2` record "is for a file DiskDoubler Pro could not
shrink".** True, and half a condition. The other half is that the file must
have **no resource fork**: `Test Text` is eleven bytes, stored, and gets a
full `0xABCD0054` header because it has a 332-byte one. Measured on the Mac
across all four cells of compressible x forked, and visible in the corpus the
claim was derived from all along — 30 `0x1000` records, every one fork-less,
beside 45 stored-data-fork headers that are not. **Cost: two emulator
sessions spent looking for a file that cannot exist**, and a byte at `+87`
documented as a resource fork's checksum when no `0x1000` record can carry a
resource fork at all. It also kept an entry in OPEN_ITEMS.md's *waiting on a
file* list, which is the section whose whole point is that somebody might
turn up with the file.

**No smell here found this one either, and none would have.** The claim was
inferred from real records and was merely incomplete, so it had no tell. What
found it was looking in the corpus for what the claim would ALLOW and the
corpus never does. That is the seventh mechanism, and DECISIONS.md
2026-08-21 (the Symantec release) states it as a habit: a rule inferred from
the cases it was drawn from always fits them.

**Four `SPLT` parts, two sets.** Written into FORMATS.md and OPEN_ITEMS.md
the day the scheme was derived, and the corpus it was derived from holds six
parts across three sets — the third being the DiskDoubler Pro self-extractor,
whose resource fork is 14,128 bytes. **Cost: the joiner's resource-fork path
had a 342-byte fork behind it in real specimens, and 47 times that was sitting
in the same directory**, along with the only set whose parts are 20 KB rather
than 12. All three now join byte-exact, forks included, and the CRC at `+48`
is exact on all six rather than on four. The smell is the oldest one here: a
number copied forward instead of re-counted. Nothing re-derived it because
the harness that reads the corpus grades files, and these are sets.

**"Macintosh Garden has 3.7 and 4.x only."** Written as the reason methods
2-5 cannot be graded, and false: the same site carries `DiskDoubler_App_3.2`
and `DiskDoubler2.03.sit`. Neither closes the gap — 3.2's `MENU 5019` offers
"Method A (fastest)" and "Method B", the same two 3.7 has, and the 2.03
download is DDExpand, the free EXPANDER, which compresses nothing — but the
CONCLUSION was being carried by a fact nobody had checked, and the check is
one page load. **Cost: none yet**, and that is the point of collecting it: the
next reader would have stopped at the sentence instead of at the search. The
smell is the one this file names first — a limitation stated about the
environment. OPEN_ITEMS.md now says what is on that page.

**63 sampled fixtures.** `tools/vmac/sample.txt` held 63 lines and 59 names:
`derived-MAZv143.sea`, `derived-DD_Expand.sea`, `derived-MacPass390.sea` and
`derived-Expand_Now_1.0.1.sea` were already in the list as REFUSAL cases when
M12 added them again as extractions, and nothing deduplicates a list of file
names. **Cost: four emulator runs on every sweep of every tier since
2026-08-15 — minutes each, at 1x tens of minutes — and a coverage number 7%
higher than the coverage.** It also inflated a gap: OPEN_ITEMS.md read "the
seven fixtures M12 added" have never run on System 7, and M12 added TWO new
names to this list. The smell is a cross-file contradiction that no file
carried, because both numbers were computed from the same list by hand and
neither by counting. A list of names is not a set of names until something
makes it one.

**macunpack is not a second implementation of method 7.** Built with
`-DUNTESTED` its `dd_lzss` segfaults on the first specimen: it takes the
32-bit value at offset 6 as a byte count to skip, where the field is a chunk
COUNT, and never initialises the bit pointer it then reads through. The
grading uses `unar` and the fork's own checksum instead. An `#ifdef UNTESTED`
is a claim about the code, and this one is accurate.

**"The trigger is a NAME RULE."** Found on the panel's *Compression and Other
Settings* page, written up as the answer to five failed attempts, and repeated
in three files. The page does say it — *"Immediately compress files, folders,
and disks whose Name begins or ends with: small"* — and the rule does not fire.
Four runs renamed a subject to match, on a machine that booted and was shut
down cleanly, and the file came back byte-identical every time. The disproof is
on the same page: its OTHER rule, *"Stuff or expand item when its name is
changed by adding the following suffixes: .SIT"*, fires on the same event —
`Forked` renamed to `Forked.SIT` came back a 228-byte StuffIt archive with the
original gone. So renames reach the extension, the extension acts, and its
output survives; compression specifically does not happen.

**Cost: five runs before the flush was fixed and four after it**, and a
sentence in OPEN_ITEMS.md that made the specimen look one keystroke away for a
day. **The smell is a familiar one wearing new clothes: the claim was read off
the software's own UI rather than out of its behaviour.** A settings page is
documentation, and this repository already distrusts documentation it has not
run — that is why every method table here is derived from module headers rather
than from a manual.

**Three SpaceSaver runs that "measured unchanged" never booted.** The
enrolled image every one of them started from — `--namefirst`,
`--namevol` twice — was made by `--enroll`, which drove the control
panel correctly (its own screenshot shows the startup disk added to the
Idle Time list) and was then **killed**. Mini vMac writes a guest's
sectors through buffered stdio and flushes when a volume is ejected, so
what was copied out of `/tmp` was a torn image: it does not boot, and
the runs built on it photographed the striped garbage screen and read
their subjects back unchanged. Those readbacks were written up as facts
about SpaceSaver — that a matching name appearing does not fire the
rule, that eighteen minutes of idling changes nothing.

**Cost: the specimen, for a day, and the whole of the trigger
investigation.** "A rename EVENT is required" was inferred from one of
these dead runs, and it sent five more at driving the Finder's name box.
The fix was already in this repository and had been since the ARC
specimens: `arcmac.py`'s `shutdown()` says *"killing the emulator with
the volume still mounted loses everything the guest wrote"* and picks
Special ▸ Shut Down instead. `spacesaver.py` simply never called it.
**The smell is a new one worth keeping: a harness that ends its runs
differently from the harness beside it.** Same emulator, same flush
problem, one of them solved — and nothing compared them.

**Alysis SuperDisk! "has no reference".** Filed under OPEN_ITEMS.md's
*"rule #1 forbids inventing a format"* for as long as that section has
existed, on the grounds that XADMaster does not implement it, `unar` and
`macunpack` stop at the envelope, and no layout is published. Every one of
those statements is true and the conclusion did not follow: both corpus
archives are self-extracting APPLs, so each ships an implementation — a 2,694
byte `CODE 2` that walks the container, a 982-byte `SuperDisk! Add-In Module`
in the data fork that decodes method 11, and, once that method decodes, the
Disk Expander extension whose `Cmpr` resources are the entire codec set with
their method numbers and names.

**Cost: the only format in the corpus that a user got *unknown* for, for the
whole life of the project** — two archives, five forks, four documents and an
application nobody could get at. It is the fourth withdrawal of this exact
shape, after StuffIt method 6 ("there is no oracle" — the second oracle was in
`reference/`), Now Compress's 1995 archive and ArcMac's fork order. The smell
is the same every time: **a claim that no implementation exists, made without
opening the file that needs one.** A self-extracting archive is never missing
its decoder.

**Retro68's `HOpen` glue.** Claimed to return `noErr` without writing back the
refNum, and recorded as M10's root cause. Ten cases — real vRefNum, non-zero
dirID, write permission, a poisoned stack, a cross-volume open — show `HOpen`
writing the refNum every time and agreeing with a hand-filled `PBHOpenSync`.
The same write-up also said `HOpenDF` was the odd one out "unlike the
non-hierarchical `OpenDF` beside it"; wrong, they are broken identically.
**Cost:** the true cause of the M10 saga is still unknown and every conclusion
from that period had to be re-tested — the next three entries. Twice a claim
about one source file was wrong because the file was read rather than run.

**Three non-relocatable staging blocks bomb the Memory Manager.** Re-tested
with the glue fixed: two separate `NewPtr` staging blocks plus the archive
buffer extract a two-fork file byte-exact with no crash. The shared block is
kept as marginally more heap-friendly, but its stated justification was wrong.
**Cost:** none beyond the write-up.

**`derived-RWAsm_Folder.sit` fails at 4 MB.** Does not reproduce: all 38
entries byte-exact at the same 643.2 KB peak the failing run reported. What
differed cannot be established — the harness that produced the old numbers was
never committed and its working directory is gone. Closed as
not-reproducible, not as fixed. **Cost:** it is why `tools/vmac/` is committed
and fetches its copyrighted inputs by URL.

**QuickDraw bombs after File Manager activity.** Twelve configurations of
`tools/quickdraw-repro/` — including `GetNewDialog`, eight interleaved rounds,
and a held 200 KB non-relocatable block — every call succeeding with
`MemError() == 0`, its log written by poking the framebuffer so the report
cannot depend on what is being tested. Both proposed explanations fail too.
**Cost:** as stated it meant the shipped interactive build was broken —
SFGetFile, a progress dialog, then an alert is exactly File Manager followed by
QuickDraw — and nobody noticed, because it was filed under *harness lessons*.
**Filing a hypothesis under "lessons" hides it.**

**The OS 9 boot volume is plain HFS.** A signature was read at a fixed offset
(`'BD'`) without checking `drEmbedSigWord`, which says `'H+'`. The proposal
built on it — drop the app into Startup Items with hfsutils, skip Finder
automation — is not merely untried but impossible, since nothing here writes
HFS+. **Cost:** a day's plan; and the same mistake shape (reading a field at an
offset instead of asking what qualifies it) is why the HFS+ runs now prove
their output volume by mounting the wrapper.

**Interleaved reads and writes on one volume return zeros.** This justified
reading the whole archive into RAM. `UNC_AT_INTERLEAVE` reads one file three
ways on one volume and gets an identical CRC every time, at 4 MB and 1 MB, on
two fixtures. **Cost:** the archive buffer came out of the engine's budget, so
at the floor target the archive's own size decided which StuffIt 5 entries were
affordable. Removing it took the sample 39/44 → 40/44.

**Mini vMac's write-back is lazy and partial** — "it can commit one fork of a
file but not the other". The whole sample was replayed with `--keep-disks` and
every Out volume read back: **55/55 byte-exact**, both forks, names and folder
structure included, `derived-RWAsm_Folder.sit` alone being 38 files and 73
forks. **Cost: the highest of any of these.** It forced verification through
the framebuffer grid, which carries counts and summed CRCs — and a summed CRC
cannot carry a name. That is why the System 6 and 7 tiers never checked an
output NAME, and why a real defect in the gzip/`.Z` fallback name sat in the
corpus for weeks until the Mac OS 9 harness, which reads its volume, caught it
on its first sweep.

**`pkill -9` never flushes; repeated boot+kill corrupts the boot image.**
Neither half survives: the sample was read back off its Out volumes after
exactly that kill, and 6 boot+kill cycles re-using one boot-shell image leave
it byte-identical (that configuration never writes to its boot volume), while
5 `--finder` cycles change the hash every time and still boot to a healthy
desktop. **Cost:** none — and the practice is kept for the better reason the
OS 9 master-image incident taught: the image DRIFTS, so reusing it makes two
runs months apart incomparable. That is reproducibility, not corruption.

**The three 1 MB StuffIt 5 refusals each fill a 512 KB block.** This closed the
floor target as needing "a fundamentally different inverse BWT". Instrumenting
`numbytes` says otherwise: none of the three fills a 512 KB block and one holds
under a quarter of it — the table is FORMATS.md, *Floor target verification*.
**Cost: the largest still outstanding.** The false figure made the gap look
like a 3× shortfall requiring a redesign when the worst entry needed ~650 KB
against ~700 KB free, and nobody re-derived it for a day because the item read
as closed. **Why it survived is the part worth keeping:** the disproof was
already in this repository — DECISIONS.md said that fixture's blocks "really do
hold ~316 KB", one file away from the claim it contradicts. The tier reached
44/44 on 2026-08-07 without a new algorithm (DECISIONS.md 2026-08-06 and -07).

**Nine fixtures are ground truth the oracle cannot produce.** Seven were filed
as *structurally undecidable* (an archive holding both `X` and `X.rsrc`) and
two as *oracle-buggy*. Both are properties of `unar -k visible`, the flag this
repository happened to pick. Rebuilt with `-k hidden`, all nine produce
manifests and all 774 pre-existing manifests come back entry-for-entry
identical. **Cost:** nine fixtures sat outside the differential suite from
2026-07-23 to 2026-08-08, including shapes nothing else covers; worse, the
ongoing half — `harvest.py` accepts a candidate by asking whether a manifest
can be built, so every THINK C-shaped archive the corpus might have grown by
was being dropped silently. **Why it survived:** it was filed under *cannot be
closed in this environment*, where items go to stop being re-examined, and the
remedy was quoted verbatim in TESTING.md one paragraph above the limitation.
**Check which of your limits are limits of a flag you chose.**

**There is no oracle for StuffIt method 6.** XADMaster refuses the method,
therefore nothing here can adjudicate an implementation — every step follows
except the first: `macunpack` has decoded it since 1991 and was already in
`reference/`, fetched by this repository's own script. **Cost:** one corpus
fork unextractable and 22 forks of *other* methods left unadjudicated, all
settled within an hour of building it; and the claim was restated in four
status files, which is how a fact about one tool became a fact about the
environment.

**Even `unar` fails on the two PKZIP 1.x zips.** True at M8, when a manifest
was all-or-nothing. Per-entry manifests gave both ground truth for 5 of 7
entries — and the claim survived the morning that disproved it, because
`run_diff.py` skipped those fixtures whole on the strength of our own
"recognized but unsupported" output. **Cost:** 10 adjudicated forks ungraded
for a day, and a skip that could not fail: a regression turning a supported
method into "unsupported" would have been recorded as a skip.

**The Macintosh application unwraps nested files automatically.** Claimed by
README.md, in the section describing the APPLICATION. True of the Linux CLI,
false of the application, which took exactly one layer off and stopped —
measured by running it. **Cost:** a user with a `.sit.hqx`, which is most of
what was distributed, had to open the result again by hand for as long as the
application has existed. **Why it survived:** the autotest is graded per layer
on purpose, so the harness that replays the sample could never catch it, and
nothing else read the README as a specification. **A claim in the user-facing
document had no test at all** — every other claim here is checked by something.

**No second implementation of Now Compress exists.** Written while a copy of
one sat in the corpus: the 1995 fixture is SELF-EXTRACTING, so the decoder
Now Software shipped with it is in its resource fork.
`nowcompress.py --adjudicate` runs it under the emulator; it agrees with us on
all four forks, 9.9 MB byte for byte (resource forks with bytes 16..127 masked,
the `vmac_check.py` convention). **Cost:** one day of those forks being
defended structurally instead of adjudicated — and the same shape as the
method-6 entry above, which is why this one was worth re-reading.
**Twice now the answer to "nothing can grade this" has been in the repository.**

**Nothing documents ArcMac's fork order, and no oracle reads ArcMac.** Both
halves wrong, and both fell to one wiki page (justsolve.archiveteam.org/wiki/
ArcMac, read 2026-08-16). The format HAS a published specification — *ArcMac
File Structure* in the `ARCMAC.DOC` that ships with every distribution — which
states the fork lengths are stored "using Intel 80xxx byte sex"; the decoder
had been reading them big-endian. It does not give the order, so that was
measured instead: `tools/vmac/arcmac.py` has ArcMac 1.3c archive a two-fork
file under Mini vMac, and the payload is **data fork then resource fork**,
byte-exact both ways, confirmed a second time with the `s` (stored) modifier
where the two forks are legible raw. The page also named two real archives —
neither had ever been searched for. **Cost:** every ArcMac entry's payload,
declined for a day; every ArcMac entry's fork SIZES, reported as garbage for
the same day, by a decoder and a unit test that were wrong the same way, so
the suite could not see it. **Three times now the answer to "nothing can grade
this" was one search away**, and this time the withdrawn claim above is what
made the third worth attempting.

### Corrected figures and superseded write-ups

- **The OS 9 boot time** was recorded as "about four minutes", then "20-45
  minutes". An idle host settles the desktop in **~110 s**; both earlier
  figures were host load written down as a property of the guest.
- **`macburger-helper.hqx` was written up three times as an anomaly.** It
  simply takes 150 s. A decode rate this non-uniform expires every fixed
  timeout mid-run, and **a timeout expiring is not a measurement**
  (`tools/vmac/README.md`).
- **`popper-1.7.tar.Z` and `PCCTS.tar.gz` at 1 MB** were root-caused and
  fixed: the sink accumulated each whole fork in a `NewPtr` block, so the
  shell needed `archive + engine peak + largest output fork`. Streaming writes
  took the sweep 37/44 → 39/44; the old path stays buildable as
  `UNC_MAC_STAGE_WRITES`.
- **The "all-black screen crash"** chased during M10 was a harness artifact: a
  launcher that backgrounded the emulator and exited took it down by SIGHUP,
  and a dead X window reads as pure black.
- **The `mio_seek` eofErr fix** is correct and kept, but it was not the M10
  blocker either.
- **The Mac OS 9 harness was damaging its own disk image** by booting the
  master in place and never hashing it. Fixed: the published SHA-1 is verified
  before every run and the master is copied to a throwaway
  (`tools/vmac/README.md`).
