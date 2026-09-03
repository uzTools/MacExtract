# Branch `selective-extract` — show what is in the archive, extract what is ticked

**Branched from `main` at "Two folders that shorten alike are two folders,
not one", 2026-09-03**, to answer one question: *what does selective
extraction cost?* It is built, graded, and priced. It is **not merged**, and
the price is the reason to decide rather than the decision.

## What it does

The archive is walked twice. The first walk is `UncOptions.list_only`, which
decodes nothing and reports every entry through `begin_entry`; the names go
into a box with a tick each; the second walk answers **>0 from `begin_entry`
for everything that was not ticked**, which is the skip the engine has had
all along (`include/macextract.h`, *Sink*).

**No format and no decoder is touched.** The engine is unchanged: the whole
feature is `mac/macextract_mac.c`, `mac/macextract.r` and the two test
harnesses. The Linux CLI is unchanged too.

The box opens with **everything ticked**, so Return is what the application
did before it existed. `All` and `None` are buttons; `Extract` is the default
and is **disabled while nothing is ticked**, which is the whole of what an
empty choice has to be told.

## What it costs

Two numbers, and both come off the same place.

| | before | after | cost |
|---|---|---|---|
| `CODE` | 147,548 B | 150,192 B | **+2,644 B** |
| A5 world (data + bss) | 44,084 B | 44,160 B | **+76 B** |

**Both come off every extraction's budget on a 1 MB Mac Plus, one for one**
(FORMATS.md, *What the application costs the engine*), so the feature costs
**2,720 B of budget on every run, including the runs of a user who never
unticks anything**. Against the ~565–597 KB an extraction is granted there
that is 0.46 %; against the 5,988 B the overlay branches were built to win
back, it is 45 % of the prize, spent.

**The list itself costs the extraction nothing.** The store is one
`NewPtr` of **3,590 B** — 3,072 B of names, 128 entries' worth of offsets,
lengths and ticks — taken *before* the engine's budget is worked out and
given back *before* the extracting walk starts whenever everything is
ticked. A run that really does select a subset keeps it, and the budget
already knows: it is computed after the box closes, so the engine is told
about a heap the store is already out of.

**The cap is 128 entries and 3,072 B of names.** Past either, there is no
honest list to offer: everything is extracted and the report box says *"Too
many items to choose from, so all of them were extracted"* rather than the
box quietly showing a prefix of the archive. A 70,000-entry zip therefore
behaves exactly as it does on `main`.

## What is deliberately not covered

- **Envelope layers.** The listing walk runs on the LAST layer only — a
  format that is extractable and is not an envelope — so `.sit.hqx` is
  unwrapped to disk as before and the box appears once, over the `.sit`.
- **Segmented sets.** Their parts are fetched a disk at a time; a listing
  walk would send the user after every disk in the set before they had
  chosen anything.
- **Unticking a folder does not untick what is inside it.** A folder entry
  is one entry; its children are others. An unticked folder that a ticked
  child needs is still created, which is correct and is what the grader
  ignores.
- **A name too long for the box is cut, not wrapped**, so that one row is
  one tick. The head is kept: a path's folders come first.

## How it is graded

**Host-side, in `./ci.sh`** (`tests/run_mac_sink.sh` → `--select`,
`tools/check_mac_select.py`): extract the even-numbered entries, extract the
odd-numbered ones, and require that the two sets of files are **disjoint**
and together are **byte-for-byte** what extracting the whole archive
produces. Eight archives across four container families, including nested
folders and an archive comment.

That property is the point of the wording: a shell that ignored the choice
fails disjointness, one that skipped too much fails the union, and neither
can pass by accident. **Established that it can fail**: with the per-entry
test changed to `return 1` — extract everything — the same run reports ten
files in both halves and exits 1.

The same code is run big-endian on `qemu-m68k` by that suite, as the rest of
the Mac sink is.

## What the second walk costs on a 68000

**About 10 ms an entry**, and it is the ENTRY COUNT that prices it, not the
archive's size: the walk decodes nothing, so it is a header scan.

Measured with `UNC_AT_LISTWALK` — a build flag that makes the AUTOTEST
application do the listing walk and then extract everything, so the same
fixture with the flag and without it is the measurement. At authentic Mac
Plus speed (`run.py --emu mv-4M-1x`), one emulator at a time, System 6.0.8:

| fixture | entries | without | with | cost | poll |
|---|---|---|---|---|---|
| `derived-CursorAnimator.sit` | 107 | 64 s | 65 s | **+1.1 s** | 1 s |
| `derived-MacburgerHelper.sit` | 623 | 268 s | 273 s | **+5 s** | 5 s |
| `derived-EmpireBuilderDemo.sit` | 3 | 121 s | 121 s | **not visible** | 5 s |

Both measurable rows land on ~8–10 ms an entry and under 2 % of the
extraction. The three-entry row is not a null result to hide: a three-header
scan is invisible by construction, and it is in the table because it is what
most archives look like.

**The flag reaches the binary**, which is the half of a measurement like this
that fails silently: the `UNC_AT_LISTWALK` autotest build is 142,832 B of
code against 142,244 B without it.

**What this cannot see: a real floppy.** The emulator's volume is a disk
image the host holds in memory, so a seek costs nothing. The walk seeks over
every entry's compressed data, and on a Macintosh with one floppy drive that
is a stepper motor rather than a pointer move. Nobody here can measure that
(MANUAL_TESTS.md is where the machines this project cannot reach are
listed).

**`MacburgerHelper` is also the worst case whole:** 623 entries is past the
128 the box holds, so that walk is paid for and no choice is offered. It
fails in this harness for an unrelated and pre-existing reason — 623 entries
do not fit on the floppy-sized output volume the harness gives it, identically
with the flag and without — and is quoted only for the difference between two
runs that did the same work.

## On screen, on an emulated Mac Plus

`tools/vmac/interactive.py --choose`, System 6.0.8, 4 MB, 2026-09-03. A
generated six-entry archive, so the row order is known and a row can be
named: untick everything with `None`, tick rows 0 and 2, Extract, and
**read the volume back**.

    the volume holds :Alpha.txt, :Charlie.txt, :Desktop, :archive.sit, ...

The two that were ticked are there and **Bravo, Delta, Echo and Foxtrot are
not**; the scenario is self-checking and reports `choose COMPLETE`. Three
frames are kept in `docs/screens/`:

| frame | what it shows |
|---|---|
| `choose-1-box.png` | the box as it opens: everything ticked, `All`, `None`, `Cancel`, `Extract` with the default ring, and a live scroll bar |
| `choose-2-none.png` | after `None`: nothing ticked and **Extract dimmed**, which is the whole of what an empty choice is told |
| `choose-3-ticked.png` | rows 0 and 2 ticked — the two names that then turn up on the volume |

The assertion is the volume and not the photographs, deliberately: a picture
of a list with ticks in it cannot fail, and a file that should not be on the
disk can.

**And on System 3.0**, the floor — `--choose --system Sys30.img`, same
archive, same clicks, `choose COMPLETE`, and the box draws pixel for pixel
as it does on System 6. That tier is launched by double-click and wants the
application at the volume root, so the scenario builds its image with
`--finder` there (FORMATS.md, *System 3.0 tier*).

**One cosmetic edge:** the dimmed Extract button keeps its default-button
ring, because the ring is a `userItem` drawn by the report box's proc and
that proc does not know the button is disabled.

**One design consequence, found the hard way.** Return is Extract, so a
Return meant for the destination dialog lands on this box and takes
everything. The first System 3.0 run did exactly that and extracted all six
files with the box never photographed — which looked like the box failing to
appear and was a keystroke arriving one step early. The scenario now opens
the archive by double-click instead of click-and-Return.

That is safe rather than destructive — an early Return gets the behaviour the
application had before this box existed — but it is the reason the box cannot
be made to default to anything else. **If the box ever opens with entries
UNTICKED, this becomes a way to extract nothing by accident.**

## What would close it

Nothing on this branch's own terms: it is built, graded on this machine,
driven on both the System 6 and System 3.0 tiers, and priced. What is left
is the decision — 2,720 B of every 1 MB extraction's budget, for a box —
which is not this branch's to make.
