# StuffIt classic's password: the key schedule and the key derivation

What StuffIt Deluxe 3.5.1's own code does with a password, read out of it
and run under `qemu-m68k` (2026-11-09). Everything below is **measured**
unless it says otherwise.

**Where the code is.** Not in a `DCMP` module: 3.5.1 has no Encryptor
modules (FORMATS.md, *Where an archive names the module*). The cipher is in
the `StuffIt Engine™` extension 3.5.1 installs — version 3.5.2 by its `'vers'`
1, © 1990-94 — (type `SITL`, creator `SITe`, resource fork 504,902 B), in
two `CCOD` code resources:

| resource | size | is | how that is known |
|---|---|---|---|
| `CCOD` -2013 | 8,534 B | the **reader** | it fetches the archive's `'MKey'` with `GetResource('MKey', 0)` @0x1d9a, checks a password against it, and its fork transform @0x1f58 feeds back from its input XOR the key — from the ciphertext |
| `CCOD` -2045 | 21,144 B | the **writer** | it makes the `'MKey'` @0x1f72 and the sixteen bytes after each fork @0x2130, from random numbers (low memory's `Time` and `TickCount`, @0x0008..0x001a); its transform @0x3cf8 feeds back from its input, the plaintext |

Offsets are into each resource's data. Both are 68k code with their globals
off A4 and no trap in any routine the harness calls, so `tools/sitdes/sitdes_run.c`
calls them as they are, and `tools/sitdes/run_sitdes.py` checks the bytes
cited below before using them. The writer's schedule, block and fold are
the reader's instruction for instruction except for A4 offsets (-2045
@0x2ad0, @0x21ee, @0x2c58), and give the same answers on every key and
password the grader tries.

## The block cipher

`CCOD` -2013 @0x0f3e, `block(src, dst)`, under the schedule last set.

- **Sixteen rounds of DES's round function and nothing around them**: the
  first four bytes, big-endian, are L0, the last four R0; the output is R16
  then L16. No initial or final permutation. S-boxes 1, 3, 5, 7 and 2, 4, 6, 8 are
  two 1,024-byte tables in the code (@0x0f70, @0x1370), each entry already
  through P; the state is held rotated right one bit (@0x0f4c, @0x0f50),
  which makes the expansion E a byte mask (`0xfcfcfcfc`, @0x0f64) on R and
  on R rotated left four (@0x1796), and is undone on the way out (@0x1810,
  @0x1814).
- Equal, measured, to FIPS 46-3's sixteen rounds with no IP/FP given the
  schedule's subkeys as below: 8,128 blocks, the 64 single-bit keys
  encrypting, the 64 single-bit blocks decrypting, and random ones both
  ways.

## The key schedule

`CCOD` -2013 @0x1820, `setkey(key, mode)`. Sixteen rounds × eight bytes at
A4+31208.

1. The key is read as **sixteen nibbles**, high nibble of byte 0 first:
   nibble *n* is the high half of byte *n*/2 for even *n*, the low half for
   odd *n* (@0x1838..0x184a stores each times four).
2. Round *r* (0..15) reads nibbles at *r* plus a fixed offset, mod 16. Its
   eight six-bit subkeys come in **four pairs, each pair three nibbles
   read as one twelve-bit number**: the top six bits are the subkey of the
   odd S-box, the low six that of the even S-box after it.

   | pair | S-boxes | nibbles, as offsets from *r* | read @ |
   |---|---|---|---|
   | 0 | 1, 2 | 1, 8, 5 | 0x1870..0x18a4 |
   | 1 | 3, 4 | 10, 3, 14 | 0x18a8..0x18e0 |
   | 2 | 5, 6 | 6, 11, 2 | 0x18e4..0x191a |
   | 3 | 7, 8 | 13, 0, 9 | 0x191e..0x194c |

   So the middle nibble of each pair is split, its top two bits ending
   the odd subkey and its low two starting the even one.
3. Every one of the 64 key bits is read, so this is not DES's PC-1/PC-2
   schedule (PC-1 drops eight) and no permutation of the key makes it one.
4. **mode 0 stores round *r* at 8*r*, mode 1 at 8(15−*r*)** (@0x185a): the
   block routine always walks the table forwards, so mode 0 encrypts and
   mode 1 decrypts.
5. How it is stored, which matters only to read the table: subkeys for
   S-boxes 1, 3, 5, 7 in bytes 0..3 of the round and 2, 4, 6, 8 in bytes
   4..7, each shifted left two over a tag of 1, 2, 3, 0 that selects the
   table quarter (`addq` #1, #2, #3 @0x188e..0x1918; pair 3 none).

Measured: 8,264 schedules, reader and writer, both modes — the zero key,
all ones, the 64 single-bit keys and 2,000 random ones.

## The archive key, from the password

`CCOD` -2013 @0x19a8, `fold(password, out)`; the writer's @0x2c58 is the
same code.

1. The schedule is set from **`01 23 45 67 89 ab cd ef`**, encrypting
   (@0x19be, @0x19d0), and is not changed again during the fold.
2. A block starts as the same eight bytes.
3. **Up to eight password bytes, each ANDed with `0x7f`**, are XORed into
   the block from its first byte (@0x19e2..0x19ee), and the block is
   encrypted in place (@0x19f8).
4. Step 3 repeats while password bytes remain, and **runs at least once**
   (@0x19da, @0x1a00..0x1a06): an empty password is one fold of nothing;
   a password of 8 is one fold, 9 two, 17 three — `ceil(len/8)`, the count
   FORMATS.md (*StuffIt classic's archive key*) measured from archives.
5. The fold stops at a NUL byte (@0x19e4, @0x1a00): the password is a C
   string here. That @0x1e56 makes it one from the dialog's Pascal string
   is a hypothesis (a call through A4 that was not followed); nothing a
   dialog can type is a NUL either way.
6. The block is the archive key.

**An archive key whose eight bytes are all equal is not used**: the reader
folds again with the key's own eight bytes as the password (@0x1e70..0x1ea6,
`all_equal` @0x0662), as the writer does (@0x3452..0x3474), and the check
below refuses one outright (@0x0588). No password reaches it in practice;
see *What the engine does differently*.

Measured: 4,518 cases, two per password (its `'MKey'` and that `'MKey'`
one bit off): the empty password, 2,000 of 1..40 bytes, every single byte
value 1..255 and the three below, through the fold, the check and the file key below.

## The `'MKey'`, and what checks the password

The writer, `CCOD` -2045 @0x1f72: an eight-byte IV, whose first four bytes
are random and whose last four are the last four of
`E(AK, IV[0..3] ‖ 00 00 00 04)` (@0x1fb0..0x1fd8); the `'MKey'` 0 resource
is `E(AK, IV)` (@0x1fdc..0x1fe4).

The reader, `CCOD` -2013 @0x05ee (called by `check` @0x0580):

1. IV = `D(AK, MKey)` (@0x05fa..0x0606).
2. The password is right when **`E(AK, IV[0..3] ‖ 00 00 00 04)[4..7]`
   equals `IV[4..7]`** (@0x060a..0x0630); otherwise the archive key is put
   back and the check fails.
3. The IV is kept as the archive IV (@0x0650..0x0656).

On the three archives StuffIt Deluxe 3.5.1 wrote here (passwords of 8, 9
and 17 characters, `tools/vmac/sitcrypt.py`), Aladdin's own check accepts
the password and refuses it one character off.

## The file key and IV, from the sixteen bytes after each fork

The **last sixteen bytes of each encrypted fork** (the reader seeks to the
fork's end minus 16 and reads eight then eight, @0x0004..0x0062):

| bytes | decrypted under | then | is |
|---|---|---|---|
| 0..7 | the archive key (@0x069a..0x06ac) | XOR the archive IV (@0x06b0..0x06ba) | the **file key** |
| 8..15 | the file key (@0x06be..0x06d0) | — | the **file IV** |

The writer makes them the other way round (@0x2130): a random file key XOR
the archive IV encrypted under the archive key, then a random file IV
encrypted under the file key.

## The fork transform (for reference)

`CCOD` -2013 @0x1f58, per eight bytes, with the file key K and a state S
that starts as the file IV, all as two big-endian words:
`out = in ⊕ K ⊕ S`; the new S is `(S1, ror1(S0 ⊕ P0 ⊕ P1))`, P being the
plaintext half-words. The writer @0x3cf8 computes the same S from its
input. The fork is transformed in whole eight-byte blocks (@0x00bc). This
is `unc_crypt_apply`'s `UNC_CRYPT_SIT_DES`, graded here on 2,000 random
streams and on both forks of the three archives.

## What the engine does differently

- **The all-equal archive key** is neither refolded nor refused: a
  password reaches one with probability 2^-56, and handling it would be
  bytes for nothing that can be measured.
- **The password is its length, not a C string**, so a NUL byte inside it
  is folded; no dialog types one.

Both are listed in `tools/sitdes/run_sitdes.py` as what it cannot see.
