# Ready-to-post upstream issues (github.com/MacPaw/XADMaster)

**Not filed, and not to be filed from here.** The maintainer posts these from
his own account (MANUAL_TESTS.md §7, CLAUDE.md Rules) — no session working in
this repository should submit one. It is also not possible from here, for the
same reason as `tools/retro68-hopen-repro/`: no `gh` CLI, no credentials, and
an unauthenticated POST to the issues API returns 401.

Four findings below. Reproduction: `make_repro.py` for the first,
`make_repro_unchecked.py` for the other three (2026-11-05); both scripts
are in this directory.

---

## DiskDoubler DDn (method 10) reads one byte past the fork

`unar` 1.10.8 fails on some DiskDoubler DDn forks with

    Failed! (Attempted to read more data than was available)

on archives that are not damaged. The decoder itself is correct — it is the
input bound that is one byte short.

### Reproduction

    tools/xadmaster-ddn-repro/make_repro.py -o /tmp/repro.dd
    unar -f /tmp/repro.dd

1,166 bytes: one `0xABCD0054` container, one file, two DDn forks (data
1,335 → 665, resource 712 → 417). Both forks fail.

Declare **one** more compressed byte and append one pad byte:

    tools/xadmaster-ddn-repro/make_repro.py --slack 1 -o /tmp/ok.dd
    unar -f /tmp/ok.dd            # succeeds

One byte is enough; the compressed data is untouched. A sweep of 0, 1, 2, 4,
8 … 64 bytes of slack flips at exactly 1.

### That the output is right

With the slack, `unar`'s output is byte-for-byte identical to two other
implementations across all 33 forks of the two archives this was found in:

* this project's own decoder, and
* **DiskDoubler's own expander**, run under Mini vMac on System 7 (the
  archives are self-extracting, so each ships the original implementation).

So the codec agrees with everybody; only the bound is off.

### Why it bites some forks and not others

It depends on where the last block's bit stream ends relative to the byte
boundary, not on the size of the fork. In the two archives here it hits 11 of
33 forks, and the affected ones range from 393 to 16,524 bytes compressed
while unaffected ones sit on either side of that range.

### Where to look

`XADDiskDoublerDDnHandle.m`, and the length the parser hands the handle in
`XADDiskDoublerParser.m` case 10. The symptom is a refill of the input buffer
after the final bits have already been consumed, before the "do I still owe
output?" test.

---

## DiskDoubler DDn (method 10): an unbounded literal run reads past its buffer

`unar` 1.10.8 segfaults on some malformed DiskDoubler DDn forks, reading one
byte past a fixed-size heap buffer.

### Reproduction

    tools/xadmaster-ddn-repro/make_repro_unchecked.py -o /tmp/ddn
    unar -f /tmp/ddn/case_d.dd

218 bytes: one `0xABCD0054` container, one DDn block declaring `numliterals
= 1` and a length-code run of `1 << 22` literals (a legal code, 150, no
arithmetic overflow — just more literals than the block declared). `unar`
writes part of the declared output, then

    Segmentation fault

reproduced 3/3 runs; same fault instruction and address every time
(`movzbl (%rax),%eax`, a 1-byte read at a page boundary, under gdb).

A second, independent path reaches the identical fault: `case_b.dd` (also
written by the same script) sets the length code to symbol 159, where
`int length=1<<(code-128)` overflows a 32-bit signed int. With the block's
own declared size large enough that nothing else bounds the resulting
(corrupted) literal count first, it segfaults at the same instruction and
the same address as `case_d.dd`. Reproduced 3/3 runs.

### Pinned to `literalptr` by name, not just by register

Building the same, unmodified `reference/XADMaster` with `-g
-fsanitize=address` and feeding `case_b.dd`/`case_d.dd` to the handle
directly (bypassing the CLI) turns the stock crash into a symbol-resolved
one, at the same source line both times:

    AddressSanitizer: heap-buffer-overflow ... READ of size 1
    #0 -[XADDiskDoublerDDnHandle nextLiteralOrOffset:andLength:atPosition:]
       XADDiskDoublerDDnHandle.m:60   (return *literalptr++;)
    ... located 0 bytes after 65920-byte region [0x...028800,0x...038980)

`ivar_getOffset` (Objective-C runtime introspection, not guesswork) places
`buffer` at object offset 336..65,872 of a 65,904-byte instance
(`class_getInstanceSize`; the allocator's own 16 B brings the heap block
to 65,920). The fault address is exactly the end of that block — 48 B
*past* `buffer`'s own end, in the object's own trailing ivars
(`literalptr`, `offsetptr`, `nextblock`, the two `BOOL`s) and the
allocator's padding, not literally at `buffer+0x10000`: the read walks
through the handle's own bookkeeping before it ever reaches unmapped
memory. One consequence worth being precise about: the fault always lands
at this same fixed, object-relative address once the declared literal run
is long enough to reach it — it does not move with how many *more*
literals the crafted block demands beyond that.

Stock `unar`'s own crash is the identical mechanism at a coarser grain:
under gdb, `%rax` at the fault is `0x555555a72000`, exactly the top of the
process's `[heap]` mapping (`info proc mappings`) — in that run the handle
happened to be the heap's last allocation, so the same one-byte overread
lands on an unmapped page instead of an ASan redzone. **Confirmed**, not
merely consistent with the hypothesis.

### Where to look

`XADDiskDoublerDDnHandle.m`, `-nextLiteralOrOffset:andLength:atPosition:`:
`literalptr` (and `offsetptr`, read the same way) is read with no check
against `numliterals` (`numoffsets`) — three `// TODO: check for literals
left` comments mark the reads. `buffer` is a fixed `uint8_t[0x10000]` on
the handle; nothing stops `literalptr` walking past it once `literalsleft`
exceeds what the block actually populated.

### That it needs a crafted file

A correct DDn encoder's length-code stream is driven by the same counts it
writes as `numliterals`/`numoffsets` — the two cannot disagree in a file
DiskDoubler itself wrote. This project's own decoder (`src/fmt_dd.c`
`dd_ddn_run`) added the missing bound in commit 7520f9a09d7a (2026-11-03,
`DECISIONS.md`, *the symbols no encoder writes*) after finding the same gap
by reading the reference; that fix's evidence was UBSan on this project's
own build, not a run against `unar`. This is that run.

---

## DiskDoubler DDn (method 10): the same unchecked read leaks heap memory into the extracted file

The crash above needs a declared block size large enough to walk `literalptr`
off the end of its heap allocation. A smaller declared size reaches the same
unchecked read, stays inside mapped memory, and `unar` exits 0 having copied
part of its own heap into the file it just "successfully" extracted.

### Reproduction

    tools/xadmaster-ddn-repro/make_repro_unchecked.py -o /tmp/ddn
    unar -f -o /tmp/ddn-out /tmp/ddn/case_e.dd   # OK, exit 0

225 bytes: one DDn block declaring 16 real literals, every one the byte
`0x5A`, and a length-code run clamped by the block's own declared size to
204,096 bytes total — comfortably on the safe side of the boundary a sweep
against this same binary found (262,145 B still exits 0; 300,000 B already
segfaults). Every output byte after the first 16 is something the crafted
stream never supplied.

### What came out, three runs

| run | exit | output bytes | bytes ≠ `0x5A` |
|---|---|---|---|
| 1 | 0 | 204,096 | 204,080 |
| 2 | 0 | 204,096 | 201,159 |
| 3 | 0 | 204,096 | 204,080 |

Runs 1 and 3 match; run 2 differs by 2,937 bytes that happened to collide
with the marker value by chance — the leaked content itself is not bit-for-
bit identical run to run, consistent with live heap state rather than a
fixed pattern. Most of what's copied in is zero (freshly-mapped, untouched
memory), but not all of it: a handful of other byte values each recur a few
thousand times, which is not what zero-fill alone would produce.

### Why this is worse than the crash

The crash fails loudly. This does not: `unar` reports success, and the
output file is wrong in a way nothing downstream is positioned to notice —
it is larger than anything the archive actually contained, and the extra
bytes are process memory, not file content. Whatever was live in that
memory (a previous archive's path, buffered output, anything else allocated
nearby) ends up on disk under the extracted file's name.

### Where to look

Same as the crash: `XADDiskDoublerDDnHandle.m`,
`-nextLiteralOrOffset:andLength:atPosition:`. Fixing the crash (bounding
`literalptr` against `numliterals`) fixes this too — the two are the same
missing check, reached with two different declared sizes.

---

## DiskDoubler DDn (method 10): two offset-code gaps decode to wrong bytes, not an error

Two more gaps in the same handle do not crash `unar` — each decodes to the
wrong bytes with no error, `unar` reporting success (exit 0).

### Reproduction

    tools/xadmaster-ddn-repro/make_repro_unchecked.py -o /tmp/ddn
    unar -f /tmp/ddn/case_a.dd   # writes "ABCDEFGHHHH"
    unar -f /tmp/ddn/case_c.dd   # writes "ABCDEFGH\x00\x00\x00"

**`case_a.dd`** (171 B): one match whose offset-code symbol (64) is past
the 32 symbols any correct offset code assigns (a code has up to 256
symbols, but a real encoder only ever uses the first 32). `(2+(slot&1))<<bits`
is then shifted by `slot/2-1 = 31` with no bound, and the result is
truncated on storing into `uint16_t offsetptr[]`. The 3-byte match this
decodes reads back whatever that truncated value names, not an error.

**`case_c.dd`** (148 B): one match whose offset-code symbol is 31 with
every one of its 14 extra bits set. That is slot 31's own maximum — the
next slot (32, never assigned by a real encoder) would start at 65,537 —
so the arithmetic is right to give 65,536; it is `uint16_t offsetptr[]`
that cannot hold it, and stores 0. `offset > pos` lets 0 through (0 is
never greater than a non-negative position), and the match reads
`windowbuffer[pos & windowmask]` — the position it is about to write,
read before it is. The window starts zeroed, so the 3 bytes this decodes
to are 0, not the file's own earlier bytes a correct offset would read.

### Why this is not a crash

Every window access in the handle's base class is masked
(`reference/XADMaster/XADLZSSHandle.m`, `windowbuffer[x & windowmask]`), so
a garbage *offset value* is confined to the window buffer whatever it is —
these two gaps corrupt what is decoded, not where the decoder reads or
writes.

### Where to look

`XADDiskDoublerDDnHandle.m`, `-nextLiteralOrOffset:andLength:atPosition:`,
the `else` branch that computes an offset from a slot. Bound `slot` before
the shift (this project's reader refuses `slot > 31`, `src/fmt_dd.c`), and
treat 65,536 as a long offset refused by `offset > wpos` rather than a
0 that passes it (this project's reader refuses `offset == 0`).

### That it needs a crafted file, same as the crash above

The same correct-encoder argument applies: `tools/derive_dd.py`'s own DDn
reader (written independently from the reference, for the format tables
rather than for unar) never emits an offset-code symbol past 31, because no
real DDn stream carries one.
