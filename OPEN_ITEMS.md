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
| Disk images (`.image`, `.img`, `.iso`, `.cdr`, `.toast`, `.dmg`, `.smi`) | **not recognised**, since 2026-08-26, and not extracted | extracting one means a filesystem rather than a codec, and naming one is worth nothing either: a disk image is not an archive, so the name leaves a user exactly where "not recognized" does. Disk Copy 4.2 went the same day, for the same reason. The probes are complete, graded and kept in `attic/` (DECISIONS.md 2026-08-26) |
| PMarc (`-pm0-`, `-pm1-`, `-pm2-`) and `-lhx-` | **not recognised** | a different family behind an LZH-shaped header. PMarc is a Japanese PC format with its own coders, `-lhx-` is UNLHA32's extension; neither reached a Macintosh, and LZH itself only just did (2026-08-23) |
| Self-extracting LZH (an executable with an archive behind it) | **not recognised** | the archive sits behind DOS, Amiga, Atari or X68000 machine code, and finding it means knowing each of those loaders. `unar` has a parser per platform; here the answer is to hand the `.lzh` itself to the extractor |
| RAR, 7z, bzip2, xz, Cabinet, Zoo, ar/`.deb`, cpio, ARJ | **named since 2026-08-26, never extracted** | none is a Macintosh archive format, none carries a resource fork or Finder metadata, and every one is served by a maintained extractor on any machine that can run one (raised 2026-08-25, Macintosh Garden forum, *Archive formats*). NAMING them is in — the name is an instruction inside the frame the user arrived with (DECISIONS.md 2026-08-26; FORMATS.md, *Archives named but not extracted*) |
| Zip64 for files larger than 4 GB | **the counts are read since 2026-08-25 and the per-ENTRY escape since 2026-08-27; over-4-GB fields are refused, per archive or per entry**, and `unc_zipseg_describe` still answers `UNC_ERR_UNSUPPORTED` for a spanned set | the entry count, central-directory size and offset come from the Zip64 record as `uint32` halves, and so does an entry's own size and offset from extra field 0x0001 — which is what makes a 70,000-entry archive extract, and a 3.4 GB one (FORMATS.md, *Size limits*). ADDRESSING past 4 GB is the part that stays out: it would put 64-bit offsets in `UncIO` and every format would pay for them on a 68000. A field whose high half is set returns `UNC_ERR_UNSUPPORTED` for the archive or `UNC_ERR_TOOLARGE` for the entry (2026-08-14, revised 2026-08-25 and 2026-08-27) |

Everything detect-only is **named** by `unc_sniff`, and both front ends say
the name: the CLI prints *"recognized as RAR, which v1 cannot extract"* and
the Macintosh application's alert reads *"MacExtract cannot open RAR files."*
(photographed on System 6.0.8, 2026-08-26). Extraction returns cleanly
unsupported either way.

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

- **Two formats are absent from the Mac OS 9 sample, and neither
  absence is a scope decision.** **SpaceSaver**, whose only specimens
  are cache-only and cannot be committed or regenerated on a clone,
  and an **encrypted entry**, because the application asks for the
  password in a dialog and a fixture run drives the Finder from the
  keyboard, never the application (`tools/vmac/os9sample.txt` says
  both in place). **What would close them:** a committable SpaceSaver
  specimen for the first; for the second, a harness step that answers
  the password dialog — the pointer that `--cancel-click` now uses
  reaches it (TESTING.md, layer 8).

---

## 2. Waiting on a file this machine does not have

**Not scope decisions, and not effort.** Everything here is written or
writeable; what is missing is something to grade it against. They sit together across formats because that is how they
close — by somebody finding a file, and the finding usually arrives from
outside the format it settles. The question to bring here is *what did I just
find?*

Each says which of the two is missing, because the searches are different:

- a **reference** — a spec, an implementation, or a self-extracting specimen,
  which is one; rule #1 forbids writing a format without it;
- a **gradeable specimen** — a file written by something else, so our output
  has something to be wrong against.

None of this is impossible here: a download would do it.

**Four questions before filing anything here**, each of which has emptied this
section at least once: is there an implementation that could be **FED**
(DECISIONS.md, methods 3, 4 and 5); is *"X does not survive"* a claim about
somebody's **search** (BLOCKERS.md, SuperDisk!'s compressor); does the search
name the **right tool** (BLOCKERS.md 2026-08-25); and **have you looked at
all** (BLOCKERS.md, the ARC 7 row, filed and disproved the same day).

- **Five archive formats are still unnamed for want of a reference:
  zstd, lzip, brotli, lrzip and WIM.** Missing: a **reference**. Nine
  others were named on 2026-08-26 out of `reference/XADMaster` and
  `reference/deark` (FORMATS.md, *Archives named but not extracted*); rule #1
  does not bend for a constant that is easy to look up. Extraction stays out
  of scope either way (Part 1). **What would close it:** an implementation or
  spec in `reference/` for any of them.

- **SuperDisk! method 13.** No corpus fixture uses it, and every setting of
  Alysis's own control panel produces method 1 or 6 (`sdcompress.py --sweep`).
  Its module is command-2 only, like method 20's, and its output is not shaped
  like a block here: it writes `length+8`, the word 13, then a **32-bit**
  uncompressed length, where every block this container holds has a six-byte
  header with a 16-bit one. The module itself is no longer the obstacle — it
  runs, given the 64 KB working buffer it demands and the one `_BlockMove` the
  runner now answers. **What would close it:** a file that actually contains
  one, which would say whether method 13 lives in a different container or
  whether the block header has a shape this project has not seen.

  Missing: a **gradeable specimen**. The writer was searched for on 2026-08-25
  and not found — SuperDisk! 2.x is on no archive this project can reach, the
  two surviving 1.x releases have no module loader in them at all, and of the
  later Alysis products that carry the module library, Alysis Resource
  Compressor 2.0 compresses into Apple's container and eDisk 1.2 and More Disk
  Space 1.1 carry only methods 1, 11 and a 13 named " Copy" (DECISIONS.md
  2026-08-25; `tools/vmac/rescomp.py`). One lead not followed: Disk Expander
  1.2's `INIT 32` has a compress path walking a method table.

- **A SpaceSaver file written by SpaceSaver.** Every codec is graded against
  Aladdin's own modules (FORMATS.md, *StuffIt SpaceSaver*), so what rests on
  this is the CONTAINER: the method the application picks for its CPU, the
  data fork's length rounded up to 256 bytes, the 84-byte header, and the
  type, creator and Finder flags it moves aside — all currently read from
  containers this project builds itself. **Nothing here can make the
  application compress anything**; about twenty emulator runs are accounted
  for in BLOCKERS.md, and the request now sits in MANUAL_TESTS.md §6.
  Missing: a **gradeable specimen** — one SpaceSaver file, with the original
  beside it.

- **AppleLink `.pkg`: one file, which would settle two questions.**
  Named since 2026-08-23 from Aladdin's own recogniser (FORMATS.md,
  *AppleLink packages*), and detect-only because nothing here can grade
  a decoder. Three measured things suggest there is nothing to decode —
  that a package is a transfer manifest naming files beside it rather
  than a container — in which case this closes as a property of the
  format (DECISIONS.md 2026-08-23). **What is missing is a specimen**,
  which answers both.

- **A MIME message written by a MACINTOSH.** Every message the reader is
  graded against was built by `tools/run_mime.py` or read by munpack on
  Linux (TESTING.md, *base64 and MIME*). The independent specimen would be
  one written on the machine this is for — by mpack's own Macintosh port,
  by Eudora (1.2 is in the corpus as `eudora12qa.bin`), or by Claris
  Emailer — because what it would settle is the half no Unix tool has: how
  a real Mac laid out the `application/applefile` part, and what it put in
  the Finder-info entry. **What is missing is a gradeable specimen.**

- **A MIME part encoded `x-uuencode`, inside a multipart.** mpack decodes
  those; this does not. A uuencoded body posted to mail IS read — the
  uuencode probe runs before the MIME one and steps over the headers
  (FORMATS.md, *uuencode*) — so what is missing is only the case where one
  part of a MULTIPART message is uuencoded and another part is what the
  user wants. No specimen has been seen; the decoder is the uu one, which
  already exists.

- **`message/partial`: a message split across several FILES is not
  reassembled.** munpack does it, keyed by the `id` parameter and a
  reassembly directory. Here each file decodes on its own, and a part that
  is half an attachment yields half a file. The engine already joins
  multi-file sets four other ways (FORMATS.md, *Segmented archives*), so
  what is missing is a specimen to grade the fifth against, not a
  mechanism.

---

## 3. Untested code, named so it is not mistaken for tested

- **The Macintosh application does not read `UncEntryInfo.name_truncated`,
  and does not number a collision the way the CLI now does.** Added
  2026-08-27, when the engine started reporting a name it had to cut. The
  Mac shell shortens every name to 31 characters per component anyway, so
  it behaves exactly as it did before — which is defensible and undecided
  rather than done. Two entries whose names shorten alike still collide
  there, and a folder tree deep enough to sum past 255 bytes still puts a
  file under a name that is not the archive's, silently. **What would close
  it:** a decision about where the notice belongs on a Mac screen, `~1`
  numbering in `mac/macextract_mac.c`, and a tier run against a synthetic
  deep-tree `.sit`, which nothing in the corpus provides (FORMATS.md,
  *Name limits*).

- **DiskDoubler and SuperDisk! reach the path cap through code that is
  tested, in a container nothing here writes.** `unc_path_leaf` keeps the
  uncut path since 2026-08-27 (DECISIONS.md, *the path builder's own
  cap*), and `tools/run_names.py` grades it on a nine-deep Now Compress
  tree against `unar`. The other two formats run that same helper, and
  neither has a fixture whose path sums past 255 bytes: what is untested
  is their own header walks — DiskDoubler's 63-byte components and two
  level schemes, SuperDisk!'s up-directory record — not the assembly.
  **What would close it:** a deep-tree `DDAR` and a deep-tree SuperDisk!
  record stream. Nothing here writes either container, and `unar` reads
  the first, so DiskDoubler's is a writer away from being graded.

- **SuperDisk!, where a Huffman region's neighbour begins.** The two Alysis
  implementations disagree by one 32-bit refill when a coded flag bitmap ends
  exactly on a refill: this engine follows the 1991 self-extractor, the 1992
  Add-In Module has already fetched the next long (FORMATS.md, the method
  table). All 18 real blocks decode identically under both, so it is not known
  to cost anything. **What would close it:** a real block whose coded flag
  bitstream is a multiple of 32 bits — and sizing the subject does not produce
  one, because the 1991 panel codes the flags one bit each.
- **DiskDoubler's methods 3, 4 and 5 have never decoded a fork this project
  did not write.** All three are byte-exact through Salient's own 1991
  expander, which grades the reading of the format rather than the decoder
  (DECISIONS.md, methods 3, 4 and 5); what is untested is every encoding our
  own encoder does not emit. **What would change it:** one real fork of any of
  the three.
- **DiskDoubler method 5's tree-count byte is only confirmed at 0.** 0 means
  256 and expands byte-exact under both the 1991 and the 4.1.1 expander; a
  count of 16 is rejected by both, and encoder and decoder here share one
  reading, so either that shared reading of the non-zero case is wrong or
  non-zero counts do not occur. The branch is kept because it is XADMaster's
  reading and it fails as a per-entry checksum error rather than silently.
  **What would change it:** a method 5 fork with a non-zero count.
