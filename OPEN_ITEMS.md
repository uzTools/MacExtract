# OPEN_ITEMS.md — what is missing, and what is deliberately not

Two kinds of thing live here, and they are kept apart on purpose:

1. **Out of scope** — decided, recorded so nobody re-litigates it, and the
   first section below because it is the thing a session most needs to know
   before starting work on a format.
2. **Open items** — a standing audit of the gaps: things not done, things done
   but not verified, and things this repository asserts more confidently than
   the evidence supports. Each says what would close it.

**Not** BLOCKERS.md, which records investigations that went wrong and the
claims withdrawn from them. Nothing here stops the engine or the CLI, which are
byte-exact against the oracle across 932 fixtures in `./ci.sh`.

Detail lives in one place per finding — status in BLOCKERS.md, reasoning in
DECISIONS.md, how to re-run in TESTING.md or `tools/vmac/README.md`, what needs
real hardware in MANUAL_TESTS.md, results in FORMATS.md — and is
cross-referenced from here rather than repeated.

**Filing something here is a decision to stop looking at it, so it had
better be true.**

**Only OPEN items live in part 2.** A closed one moves out rather than being
annotated: the lesson to DECISIONS.md, the withdrawn claim to BLOCKERS.md,
the numbers to FORMATS.md. A section that empties is the point of the file.

---

# Part 1 — Out of scope for v1

**Decided, or impossible. Not open.** Everything here is either a boundary
somebody chose or a property of a format that no evidence can change; nothing
here is closed by finding a file, and what is waiting for one is Part 2,
section 2. "Out of scope" is today's answer and not a refusal — the brief has
grown before, on request.

## Out by the brief

| what | status | why it stays out |
|---|---|---|
| Compression | not implemented | this is an extractor |
| StuffIt X (`.sitx`) | **detect-only** | out by the brief |
| PKWARE "strong encryption" in a zip (flag 0x40) | **named, refused per entry** | its key material is in a record nothing here parses, and XADMaster refuses it too. Every OTHER encryption these formats have — including WinZip's AES, which postdates the machines by a decade and is read anyway — is decrypted since 2026-08-23 (FORMATS.md, *Encryption*) |
| Disk images | **out by the brief**; Disk Copy 4.2 (`.image`) is **detect-only**, with a real probe | extracting one means a filesystem, not a codec. The probe matches a synthetic 800K GCR image and a real one, 0 false positives. Naming the OTHER disk-image extensions is open, and detect-only is all it would ever be (part 2, section 6) |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header. PMarc is a Japanese PC format with its own coders, `-lhx-` is UNLHA32's extension; neither reached a Macintosh, and LZH itself only just did (2026-08-23) |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | the archive sits behind DOS, Amiga, Atari or X68000 machine code, and finding it means knowing each of those loaders. `unar` has a parser per platform; here the answer is to hand the `.lzh` itself to the extractor |
| RAR, 7z, bzip2, xz, and the rest of Keka's modern list (lzip, zstd, brotli, lrzip, AAR, WIM, zipx, cab, msi, cpio, pax, …) | **not recognised** | modern, PC-side formats. None of them is a Macintosh archive format, none carries a resource fork or Finder metadata, and every one is served by a maintained extractor on any machine that can run one. A file in one of these beside classic Mac software is a wrapper somebody applied recently, and unwrapping it is that tool's job, not this one's (raised 2026-08-25, Macintosh Garden forum, *Archive formats*) |
| Zip64 for files larger than 4 GB | **read for its COUNTS since 2026-08-25; over-4-GB fields refused per archive**, and `unc_zipseg_describe` still answers `UNC_ERR_UNSUPPORTED` for a spanned set | the entry count, central-directory size and offset are taken from the Zip64 record as `uint32` halves, which is what makes a 70,000-entry archive extract (FORMATS.md, *Size limits*). ADDRESSING past 4 GB is the part that stays out: it would put 64-bit offsets in `UncIO` and every format would pay for them on a 68000. A field whose high half is set returns `UNC_ERR_UNSUPPORTED` (2026-08-14, revised 2026-08-25) |

Everything detect-only is **named** by `unc_sniff`, so a UI can tell the user
what the file is and extraction returns cleanly unsupported.

## Limits of the formats themselves

- **A uuencoded set missing a MIDDLE part decodes short, and silently.** A
  document posted in several parts joins and decodes — the mail headers
  between parts are stepped over — but uuencode carries no length and no
  checksum anywhere, so nothing can notice that a part never arrived. A
  missing LAST part IS caught: the terminator and `end` live there. Asserted
  rather than described — `tools/run_uu.py` builds a gapped set and requires
  exactly this result, so the day the format turns out to have a check, the
  suite says so. **What would change it:** nothing in the format. A host that
  knows the parts were numbered `1/5` could check the count, which is a naming
  question and not a decoding one.

---

# Part 2 — Open items

---

## 1. What is not verified

Verification gaps — things this project has and has not checked.
What it does not HAVE is section 2.

- **The Mac OS 9.2 tier has not run since M12.** Everything from
  DiskDoubler and Now Compress onwards postdates it — ARC, uuencode,
  SuperDisk!, SpaceSaver, decryption and btoa — and its sample still
  records DiskDoubler as a refusal, which is what it was when that tier
  last ran. The other two tiers are re-run after every change
  (BLOCKERS.md). **What would close it:** an OS 9 sweep, which costs a
  full PowerPC boot per fixture — tens of minutes, against five for the
  whole System 7 tier.

- **Two things only that tier can show, and it has never been asked
  for either.** The interactive UI's cancel routes — Cmd-., the Cancel
  button, the dialog repainting afterwards — run on System 6.0.8 and,
  since 2026-08-25, on System 7.0.1 (TESTING.md, layer 10); on Mac OS 9
  the application has only ever been driven to completion. And how an
  8-bit MacRoman filename LOOKS there is unphotographed: the bytes are
  checked on every tier, the glyphs on the two Mini vMac ones.

---

## 2. Waiting on a file this machine does not have

**Not scope decisions, and not effort.** Every entry here is a format or a
method whose decoder is written or writeable; what is missing is something to
grade it against. They sit together across formats because that is how they
close — by somebody finding a file, and the finding usually arrives from
outside the format it settles. The question to bring here is *what did I just
find?*

Each says which of the two is missing, because the searches are different:

- a **reference** — a spec, an implementation, or a self-extracting specimen,
  which is one; rule #1 forbids writing a format without it;
- a **gradeable specimen** — a file written by something else, so our output
  has something to be wrong against.

Unlike section 3, none of this is impossible here: a download would do it.

**Four questions before filing anything here**, each of which has emptied
this section at least once: **is there an implementation that could be
FED?** (DECISIONS.md, methods 3, 4 and 5); **is "X does not survive" a claim
about somebody's search?** (BLOCKERS.md, SuperDisk!'s compressor); **does
the search name the right tool?** (BLOCKERS.md 2026-08-25 — a year was spent
looking for PKARC files that never existed); and **have you looked at all?**
An entry here is a claim and takes the same evidence as any other: the ARC 7
row was filed and disproved the same day, and its specimen was the writer's
own distribution (BLOCKERS.md, the same date).

- **SuperDisk! method 13.** No corpus fixture uses it, and every
  setting of Alysis's own control panel produces method 1 or 6
  (`sdcompress.py --sweep`). **Two of the three methods that used to
  sit here left on 2026-08-25**: 10 was transcribed from its module and
  graded three ways, and **20 turned out not to be a block method at
  all** — its module is an ENCODER whose output declares method 11
  (FORMATS.md, the method table). 13 is the same shape as 20 —
  command 2 only — and what leaves it open is that its output is not
  shaped like a block here: it writes `length+8`, the word 13, then a
  **32-bit** uncompressed length, where every block this container
  holds has a six-byte header with a 16-bit one. **What would close
  it:** a file that actually contains one, which would say whether
  method 13 lives in a different container (the extension's
  `compressFile` command has its own) or whether the block header has
  a shape this project has not seen. The module itself is no longer
  the obstacle: it runs, given the 64 KB working buffer it demands and
  the one `_BlockMove` the runner now answers.

  The writer of all of them was searched for on 2026-08-25 and not found.
  The vendor's own technology page names SuperDisk! **2.x** as the release
  with "faster and tighter compression algorithms"; it is not on
  Macintosh Repository, Macintosh Garden, Info-Mac's `cmp` directory or
  in archive.org's index, and the two 1.x releases that survive have no
  module loader in them at all (no `Cmpr`, no "Add-In", measured). Of
  the later Alysis products that carry the module library, **Alysis
  Resource Compressor 2.0** (1993) compresses into APPLE's container
  with `defProcID` 0 rather than a `Cmpr` codec
  (`tools/vmac/rescomp.py`), and eDisk 1.2 and More Disk Space 1.1 carry
  only methods 1, 11 and a 13 named " Copy". The one candidate left in
  hand is Disk Expander 1.2's own extension, whose `INIT 32` has a
  compress path walking a method table. One lead not followed: the panel's help offers JPEG lossy,
  lossy sound and a lossless sound/video mode that no `Cmpr` name
  accounts for — and a lossy mode is something an extractor cannot grade
  against its input by construction.

- **A SpaceSaver file written by SpaceSaver.** Nothing here has made
  the application compress anything. Only the CONTAINER now rests on it:
  every codec is graded against Aladdin's own modules, but the method
  choice, the 256-byte rounding and the 84-byte header are the
  application's, and this engine reads them from containers it builds
  itself (FORMATS.md, *StuffIt SpaceSaver*).

  **Nine conditions are now known to hold at once** (2026-08-25, each
  photographed): SpaceSaver switched On in its panel; the startup volume
  ENROLLED in the Idle Time list, which the installed image leaves
  empty; subjects named to match the `small` rule; dated 1990, older
  than that page's "not modified in the last 1 Months"; *Idle Now*
  picked from SpaceSaver's OWN menu with the item highlighted; the panel
  closed with its close box, since Cmd-W does not close it; nine minutes
  without input afterwards; a 400 KB subject beside the 11 KB one; and,
  in other runs, Magic Menu's *SpaceSaver Compress* on the selection.
  Every write path declines in silence — no `STR# 1001` alert, no
  progress window — while *SpaceSaver Info...* reports the file
  correctly, so the engine is reachable and answering.

  Eliminated by running them: the name rule, a size floor, the type
  exemption list (`Exem 1000` holds `PACT`, `MooV`, `JPEG`, `INIT`,
  `cdev` — not `TEXT` or `PICT`), and the idea that a rename is an
  event at all (`INIT 1` patches `_MenuSelect`, `_MenuKey` and
  `_PBEject`, and nothing in the File Manager).

  **The panel's own defaults, read with Cancel and changed nothing**
  (`--pages`): *Compression and Other* has BOTH name rules ticked —
  "Name begins or ends with `small`" and "Stuff or expand item when its
  name is changed by adding or removing .SIT/.SEA" — and the second one
  is the rule this project has already seen FIRE, so rename events do
  reach the software. *Idle Time* ships with an EMPTY list of disks,
  which is a real gate nobody had checked. Enrolling the disk and then
  renaming in the Finder, both in one flushed boot (`--enrollrename`),
  still compresses nothing: the names commit — the volume comes back
  holding `Alphasmall`, `Bigonesmall`, `Forkedsmall` — and the files do
  not change.

  **The name rule is inert; the rule beside it is not** (2026-08-25,
  five runs, each renaming IN THE FINDER with a control in the same
  boot). `Forked` -> `Forked.SIT` becomes a StuffIt archive every time,
  so the watcher is awake; `Alphasmall`, `Alpha small` and `small Alpha`
  all come back untouched, so it is not the spacing and not which end
  the keyword goes on. Nor is it the kind of item: renaming the DISK to
  `System_7_0_1 small` — the guide's own "everything contained on that
  disk gets compressed" — commits the name and compresses nothing. The 5.0 User's Guide — in the emulator cache,
  and worth reading before the next attempt — says the two default
  keywords are `small` (compress) and `big` (NEVER compress), that
  attaching one "immediately compresses that item", and that the
  keyword may be at either end.

  So StuffIt Deluxe's *Archive via Rename* works and SpaceSaver's
  *name-based compression* does not, on a machine where the panel shows
  SpaceSaver **On**, the disk enrolled, and *SpaceSaver Info...*
  answering correctly about the file. Every SpaceSaver WRITE path
  declines in silence; every StuffIt-side operation works.

  **What would close it:** what makes the engine refuse a SpaceSaver
  compress while serving a Stuff. Two leads, neither examined:
  `STR# 1001` #6 is *"SpaceSaver could not find the latest version of
  the StuffIt Engine"* — a refusal that would be raised at STARTUP,
  which this harness cannot photograph (tools/vmac/README.md, the icon
  parade) — and the panel's `PERS -4064` carries a name with the serial
  field zeroed. Or one SpaceSaver file from anywhere.
- **AppleLink `.pkg`: one file, which would settle two questions.**
  Named since 2026-08-23 from Aladdin's own recogniser (FORMATS.md,
  *AppleLink packages*), and detect-only because nothing here can grade
  a decoder. Three measured things suggest there is nothing to decode —
  that a package is a transfer manifest naming files beside it rather
  than a container — in which case this closes as a property of the
  format (DECISIONS.md 2026-08-23). **What is missing is a specimen**,
  which answers both.

---

## 3. Cannot be closed in this environment

- **Real 68k hardware: never run.** No genuine floppy I/O, no real media errors
  mid-write, no real stack underneath a real ROM's own usage — 32 KB of it,
  since `kStackBump` takes 24 KB off `ApplLimit` on top of the 8 KB default
  (FORMATS.md, *Stack*, which has the deepest chain the engine reaches). The
  per-entry I/O error path has never seen an actual I/O failure. The 1 MB
  figures come from an emulated 1 MB machine with a stripped System Folder; a
  real Plus with a Chooser extension or two has less free heap than any number
  recorded here.
- **Real PowerPC hardware: never run.** Mac OS 9 is verified under QEMU only.
- **The COLOUR icon members are unverified.** `ICN#`/`ics#` are photographed
  bound and drawn by a real Finder (DECISIONS.md 2026-08-24, *the icon*),
  but Mini vMac emulates a 1-bit Mac Plus, so `icl4`/`ics4`/`icl8`/`ics8`
  have never been displayed by anything. The 256-colour indices also assume
  the Macintosh palette is a 6x6x6 cube at `36*r + 6*g + b` with black at
  255 — **reconstructed, not transcribed from a reference**, and stated as
  such in `tools/icon/make_icon.py`. What would close it: opening the
  application's folder on the Mac OS 9 tier (`tools/vmac/os9.py`, which has
  colour) and photographing the icon, or a reference for the system palette.
- **A btoa file written by a Mac.** Every stream the btoa decoder is graded
  against comes out of one encoder, btoa 5.2.1 on Linux (TESTING.md, *btoa*).
  The independent one would be Aladdin's own `btoa/atob Translator`, and it is
  reachable only through a hierarchical menu, which cannot be selected under
  Mini vMac (`tools/vmac/README.md`, *sitcrypt.py*). **`--btoa-drop` was never
  going to work**: `DropConvert™` is `APPL/SITC` and its own strings —
  `Archive.sit`, `.sit`, `Archive.sea`, `.sea`, *"Unable to convert this
  archive…"* — say it converts ARCHIVES between StuffIt and self-extracting,
  not documents between encodings (measured 2026-08-25, off the installed
  image with `hcopy`; no emulator). What would close it: a route to the
  translator that is not a submenu. One is untried and is the shape of
  `tools/sdmodule/` — a translator is a subroutine (`main(pb, selector)`,
  DECISIONS.md 2026-08-23), so it could run under `qemu-m68k` like Alysis's
  codecs do, except that it calls Toolbox traps and would need a few of them
  answered.
- **The XADMaster DDn report is not filed.** Its DDn reads one byte past a
  fork's declared compressed length; reduced to a 1,166-byte reproduction and
  written up ready to post in `tools/xadmaster-ddn-repro/`. **Deliberately
  not submitted, and no future session should submit it** — same terms as the
  Retro68 report below, and not possible from here either.
- **The Retro68 `OpenDF`/`HOpenDF` report is not filed.** The `_OpenDF` trap is
  System 7 and neither falls back to a plain open on `paramErr`, so both are
  unusable on System 6; `FSOpen` in the same file does fall back. Measured,
  cases 8 and 11 of `tools/retro68-hopen-repro/`, written up in that
  directory's `ISSUE.md`. **Deliberately not submitted, and no future session
  should submit it** — the maintainer will post it from his own account. (It is
  also not possible from here: an unauthenticated POST to the issues API
  returns 401.)

---

## 4. Known unknowns, not being chased

- **A zip's end-of-central-directory comment is read past and dropped.**
  `UncSink` has carried a comment callback since 2026-08-23 and Compact
  Pro's fills it; `fmt_exo.c` still skips zip's, which one corpus
  fixture has 495 bytes of (`derived-MUSFMT10.ZIP`). Not chased because
  a zip comment is usually the writer's boilerplate rather than
  somebody's note, and `unar` does not write one out either. **What
  would close it:** the EOCD comment length is already parsed — one
  call to the callback, and the manifest's `comment` key stops being
  excused for `Zip` in `tools/run_diff.py`.
- **A tar member over the 2 GB cap aborts the whole archive, not the
  entry.** Measured 2026-08-25: a tar of `[1 GiB, 3 GiB, 1 GiB]` lists
  the first member and stops, so the third is lost though its position
  is known from the padded length. Every other per-entry failure in
  this engine is per-entry (`CLAUDE.md`). Not chased because a 2 GB
  member cannot exist on the machines this targets — HFS caps a fork
  there — so the case is reachable only from a foreign tar. **What
  would close it:** skipping the member and reporting the error through
  the sink, with a case in `tools/run_ziplarge.py`'s shape to hold it.
- **Names HFS+ permits that HFS does not.** Probably unreachable from this
  binary at all — the classic File Manager caps components at 31 characters on
  either filesystem — but that is unproven either way.

---

## 5. Untested code, named so it is not mistaken for tested

- **SuperDisk!, where a Huffman region's neighbour begins.** The two
  Alysis implementations disagree with each other by one 32-bit refill
  when a coded flag bitmap ends exactly on a refill: this engine follows
  the 1991 self-extractor, the 1992 Add-In Module has already fetched the
  next long (FORMATS.md, the method table). Reachable only through
  `tools/sdmodule/`'s own encoder; all 18 real blocks — both corpus
  archives and Alysis's own compressor, including four subjects made for
  this on 2026-08-25 — decode identically under both, so it is not known
  to cost anything. **What would close it:** a real block whose coded
  flag bitstream is a multiple of 32 bits. Sizing the subject does NOT
  produce one, which is what those four established: the 1991 panel
  codes the flags one bit each, so the bit length is data-dependent and
  the byte count says nothing about it.
- **DiskDoubler's methods 3, 4 and 5 have never decoded a fork this
  project did not write.** All three are byte-exact through Salient's own 1991 expander,
  which grades the reading of the format rather than the decoder
  (DECISIONS.md, methods 3, 4 and 5) — so what is untested is every
  encoding our own encoder does not emit: run lengths it never chooses,
  Huffman tree shapes it never builds, contexts it never reaches.
  **What would change it:** one real fork of any of the three.
- **DiskDoubler method 5's tree-count byte is only confirmed at 0.** 0 means 256 and
  expands byte-exact under both the 1991 and the 4.1.1 expander; a count of
  16 is rejected by both with *Checksum failed*, and encoder and decoder
  here share one reading, so the shared reading of the non-zero case is
  what is wrong — or non-zero counts do not occur. The branch is kept
  because it is XADMaster's reading and it fails as a per-entry checksum
  error rather than silently. **What would change it:** a method 5 fork
  with a non-zero count.
- **The Mac binary's own size ceiling has never been exercised.** The
  Linux limits are measured (FORMATS.md, *Size limits*): 4 GB per
  container, 2 GB per declared tar member, no ceiling on streamed
  output. The Mac shell's are not — `SetFPos` takes a signed `long`,
  which puts its ceiling at 2 GB, and HFS caps a fork there anyway.
  **What would close it:** nothing available here. An HFS volume large
  enough to hold a 2 GB file is beyond what any emulator tier runs, so
  this is a MANUAL_TESTS.md-shaped question rather than a suite one.

---

## 6. Not implemented, and nothing blocks it

Neither a reference nor a specimen is missing here — only the code. That is
what separates this section from section 2, and it is why each entry names
what would grade it rather than what would close it.

- **base64 and MIME (`.b64`, `.mime`) are not read, and are not a scope
  decision either — they were simply never listed.** Every sibling
  encoding this corpus meets is implemented (BinHex, uuencode, btoa,
  MacBinary, AppleSingle/Double); base64 is the one that is neither in
  FORMATS.md's table nor in part 1, and `.b64` was a real Usenet and
  AOL-era carrier for MacBinary payloads. **The reference is already in
  `reference/`:** deark's `modules/xfer.c` decodes plain base64 and the
  `begin-base64 <mode> <name>` framing that `.b64` files carry, in its
  uuencode module beside the `begin` shape `fmt_uu.c` was written from.
  **What would grade it:** deark itself, and `base64 -d` on a payload
  this project encodes — the same bargain btoa took (TESTING.md,
  *btoa*), with the envelope auto-unwrap making `.bin.b64` fall out for
  free. Raised 2026-08-25 from the Macintosh Garden forum thread
  *Archive formats*, which lists `.b64` and `.mime` among what a
  downloader actually meets.

- **The other disk-image extensions are not named: `.dmg`, `.iso`,
  `.cdr`, `.toast`, `.img`, `.smi`, `.cpgz`.** Extraction stays out by
  the brief (part 1) — what is open is only that `unc_sniff` returns
  UNKNOWN for them, so a UI cannot tell the user what the file is, which
  is the one thing detect-only exists to do. The same forum thread
  reports the cost of that silence: `.image` files are routinely
  mistaken for JPEGs and passed over. **What would grade it:** the
  measurement the Disk Copy 4.2 and AppleLink probes were held to — 0
  false positives across the corpus (FORMATS.md, the format table, and
  *AppleLink packages*). **The probes are not one shape.** `.smi` is an
  application with an image behind it and `.cpgz` is cpio under gzip, so
  both have something to match; a raw `.iso`, `.img` or `.cdr` has no
  header of its own at all, and naming one means probing the filesystem
  inside it — a reference this project does not yet have, and rule #1
  applies.
