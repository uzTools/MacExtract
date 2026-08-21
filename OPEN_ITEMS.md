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
byte-exact against the oracle across 916 fixtures in `./ci.sh`.

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
| Encrypted archives | **detected and reported** | out by the brief; PackIt PMa5/6 resync rather than fail |
| Disk images (Disk Copy 4.2) | **detect-only**, with a real probe | out by the brief — the probe matches a synthetic 800K GCR image and a real one, 0 false positives |
| LZH / LHA extraction | **detect-only**, tested rather than asserted (DECISIONS.md 2026-08-14) | the corpus contains **no `.lzh` at all** — Macintosh software was not distributed that way — and Compact Pro's LZH is a different algorithm from LHA's, so it is ~550 new lines for nothing the corpus can grade |
| Zip64 spanned sets | `unc_zipseg_describe` answers `UNC_ERR_UNSUPPORTED`, cleanly | an EOCD with disk number `0xFFFF` defers to a locator nothing here parses. Zip64 postdates every machine this project targets by a decade and a set that needs it is 2 GB+; refusing it cleanly is the right answer, not a missing feature (2026-08-14) |
| Compact Pro archive comments | read, CRC'd, discarded | Expander 4.0.2 writes them out beside the extracted items; a comment is not a file and the sink writes files. Recorded so the difference is a decision rather than an oversight |

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

## 1. DiskDoubler and SuperDisk!: what is not verified

Verification gaps — things this project has and has not checked.
What it does not HAVE is section 2.

- **8 resource forks across 2 fixtures are not ground truth**, though
  DiskDoubler's own expander agrees with every one of them: 33 forks
  compared under System 7 on 2026-08-21, all 33 identical, and the 3
  data forks are in the manifests (DECISIONS.md, FORMATS.md). A
  resource fork the Mac wrote is never byte-exact, so these 8 stay
  unadjudicated. **What would close it:** an implementation that runs
  off a Mac — for these methods, transcribing one — or a copy of the
  same archive from a machine that never opened it.
- **The Mac OS 9.2 tier has not run since DiskDoubler, Now Compress, ARC
  and uuencode were added.** The other three tiers have (FORMATS.md).
  Its sample still records DiskDoubler as a refusal, which is what it
  was when that tier last ran. **What would close it:** an OS 9 sweep,
  which costs a full PowerPC boot per fixture — tens of minutes, against
  five for the whole System 7 tier.

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

- **A method 7 fork longer than one chunk has never been decoded.** The
  fork header counts its compressed chunks and gives each a 16-bit
  length; both specimens hold exactly one, and the codec reads the
  chunks as one continuous bit stream because that is what the
  reference does. A fork over ~64 KB would settle whether that is
  right. **What would close it:** a bigger method 7 file, which needs
  the Sigma Designs card DiskDoubler 3.x wrote them with — no emulator
  here has one. Running DiskDoubler's own expander on the two we have is
  not a way round it: `STR# 1` in DiskDoubler 4.1.1 answers *the file
  cannot be expanded because it was compressed with Sigma hardware and
  no hardware is installed in this Macintosh*, so this engine reads
  something the original application cannot (DECISIONS.md 2026-08-21,
  the Symantec release).
- **DiskDoubler methods 2, 3, 4 and 5, ARC 0x0a/0x0b, and SuperDisk! methods
  10, 13 and 20.** No corpus fixture uses any of them and nothing reachable
  writes them, so an implementation could not be graded — code no oracle can
  check is the same bargain LZH refuses. What is left is earlier DiskDoubler
  work, and it is now bounded rather than guessed: **five releases have been
  read or run and not one offers a method between 2 and 5** — 3.2 and 3.7,
  whose menus offer two software methods and neither is one of them, and
  4.0, 4.1 and **4.1.1**, whose `MENU 195/196/197` and photographed
  *Compress Using* submenu carry AD 1, AD 2, DD 1, DD 2, DD 3 and nothing
  else. The vendor's own display vocabulary agrees: `STR# 403` is twelve
  labels — `AD 1 | AD 2 | DD 1 | DD 2 | DD 3 | AIC | other | A | B | Sigma
  | S | none` — with a word for stored, for methods 1, 7 and 8 and for
  AutoDoubler's internal compressor, and none for 2-5, which fall through
  to `other`. They are Salient's 1.x and 2.x, before the 1992 sale
  (DECISIONS.md 2026-08-21, the Symantec release), and no COMPRESSOR older
  than 3.2 is reachable. What Macintosh
  Garden has, checked 2026-08-21 rather than assumed: **DiskDoubler 3.2**,
  whose `MENU 5019` offers the same two software methods as 3.7 ("Method A
  (fastest)", "Method B") and so writes the same two; **DDExpand 2.03**,
  which is the free EXPANDER of the 2.x era and compresses nothing —
  the file is called `DiskDoubler2.03.sit`, which is what makes it worth
  writing down; 3.7.x, and 4.x. The 1990 shareware "DiskDoubler .05" on funet
  writes MacCompress files (its INIT carries `ZIVM`/`LZIV` and none of the
  three DiskDoubler magics), so it predates the container entirely.
  **What would close it:** a copy of the DiskDoubler 1.x or 2.x
  COMPRESSOR, or one file written by one. 4.1.1 does not help, and that is
  measured here now rather than read off somebody else's corpus: it is the
  application on the **Norton DiskDoubler Pro 1.1** floppy, it has been run
  under Mini vMac (`tools/vmac/ndd.py`), and its five menu entries write
  methods 9, 6 and 10 three ways. The three
  SuperDisk! methods are cheaper still in one sense and no cheaper in the
  other: their 68k modules sit inside the corpus, named and complete
  (FORMATS.md ✧✧), so transcribing them needs no research at all — and there
  would still be nothing to check the result against, because SuperDisk!'s
  compressor does not survive here, only its expander.
- **AppleLink `.pkg` and StuffIt SpaceSaver.** Neither has a reference
  implementation or a published layout anywhere reachable. Searched
  2026-08-15: the only AppleLink format with documented internals is the
  Apple II `.acu` (CiderPress2's format notes, magic `fZink`), which that page
  explicitly distinguishes from the Macintosh Package format; SpaceSaver has
  no specification, no open implementation, and Aladdin's own later Expanders
  dropped it. Neither can even be **sniffed** without inventing a magic
  number, so a user gets *unknown* rather than a name. **What would change
  it:** a specimen plus the original application, derived under Mini vMac the
  way Compact Pro's segment layout and Now Compress's block shapes were — or
  one published description. **A SELF-EXTRACTING specimen would settle it on
  its own**, which is what the SuperDisk! withdrawal cost this project four
  documents to learn (BLOCKERS.md); neither has one here, or a specimen of
  any kind.

---

## 3. Cannot be closed in this environment

- **Real 68k hardware: never run.** No genuine floppy I/O, no real media errors
  mid-write, no real 8 KB stack underneath a real ROM's own usage. The
  per-entry I/O error path has never seen an actual I/O failure. The 1 MB
  figures come from an emulated 1 MB machine with a stripped System Folder; a
  real Plus with a Chooser extension or two has less free heap than any number
  recorded here.
- **Real PowerPC hardware: never run.** Mac OS 9 is verified under QEMU only.
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

- **Why the pointer does not work under QEMU on Mac OS 9.** Measured to
  0.0000 effect across five mouse primitives; the mechanism behind that has no
  reproduction and is labelled a guess. The keyboard route works, so this costs
  nothing.
- **Names HFS+ permits that HFS does not.** Probably unreachable from this
  binary at all — the classic File Manager caps components at 31 characters on
  either filesystem — but that is unproven either way.

---

## 5. Untested code, named so it is not mistaken for tested

- **The interactive UI above System 6 is deliberate scope**, not a gap
  (2026-08-02). System 6 is the UI's target and it is driven end to end there.
  What that leaves unexercised: `ProgressPump()` branches on `gHasWNE`, and the
  cancel routes inside it — Cmd-., the Cancel button via `DialogSelect`, the
  dialog repainting — have only ever run on the `GetNextEvent` side. Mac OS 9
  runs the `WaitNextEvent` side, but only where nothing is cancelled. The
  engine and sink semantics of a cancel are covered separately: unit tests,
  both write paths through the qemu-m68k mock in `ci.sh`, and `UNC_AT_CANCEL`
  on-Mac at 4 MB and 1 MB.
- **SuperDisk! methods 1-6, 8 and 9 have never decoded anything.** Both corpus
  archives use one method each — 7 and 11, counted block by block — so the
  13-bit context (1-4), two of the four wide variants and Huffman-alone (9)
  are transcribed and compiled and nothing more. The Huffman decoder itself
  and the wide context ARE exercised, since method 7 is both. The unit test
  cannot help: it builds stored blocks, because writing coded ones would mean
  writing an encoder and grading this decoder against it. **What would change
  it:** an archive that uses one of them, or the `Cmpr` modules run under
  emulation as a second implementation — the same route the adjudication
  already takes, applied per method instead of per archive.
- **Files larger than the HFS 2 GB cap**, and the engine's 32-bit-only
  arithmetic against them.
- **MacRoman filename display and 8-bit characters above System 6.** The bytes
  are checked everywhere; how they *look* on 7 and 9 is not.
