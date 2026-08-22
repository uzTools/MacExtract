# Ready-to-post upstream issue (github.com/MacPaw/XADMaster)

**Not filed from this environment**, for the same reason as
`tools/retro68-hopen-repro/`: no `gh` CLI and no credentials here, and an
unauthenticated POST to the issues API returns 401. Post it manually if you
want it upstream. Reproduction: `make_repro.py` in this directory.

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
