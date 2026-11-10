/* MacExtract - application icon family, classic Mac OS.
   The icon members (ID 128) are a designer's, imported by
   tools/icon/import_icons.py - re-run it to change them, not the hex. The
   FREFs, the BNDL, the signature and both 'vers' below are written by
   hand and the import leaves them alone.

   A box lettered EXTRACT, with a document and a block rising out. The
   label states what the application does; the application is MacExtract.

   All members share resource ID 128. The Finder picks the deepest member the
   screen can show, so this is additive: a 1-bit Mac Plus under System 6 uses
   'ICN#' and never looks at the colour members. The colour members carry no
   mask of their own - the Finder reuses the 'ICN#'/'ics#' mask.

   PALETTE: every 'icl8'/'ics8' pixel is one of Apple's 34 icon colours,
   because only those darken when the Finder draws the icon selected
   (Human Interface Guidelines, ch. 8); the import refuses any other.

   After installing, rebuild the Desktop file (hold Cmd-Option at boot) or
   the Finder will keep showing the previous icon.                        */

/* Retro68's Rez has no built-in type declarations: without this include it
   stops at the first resource with "Can't find type definition for 'ICN#'".
   Multiverse.r is the only RInclude that declares ICN#, ics#, icl4, ics4,
   icl8, ics8, FREF and BNDL. */
#include "Multiverse.r"

resource 'ICN#' (128) {
    {  /* icon */
        $"00000000 00000000"
        $"00000000 00000000"
        $"0007FF80 000400C0"
        $"000400A0 00040090"
        $"1FFC00F8 100C0008"
        $"100C0008 100C0008"
        $"178C0008 149C0008"
        $"17A40008 10240008"
        $"109C0008 7FFFFFFE"
        $"80000001 80000001"
        $"80000001 80000001"
        $"BABB11B9 A292AA11"
        $"B1133A11 A292AA11"
        $"BA92A991 80000001"
        $"80000001 80000001"
        $"7FFFFFFE 00000000"
    ,   /* mask */
        $"00000000 00000000"
        $"00000000 00000000"
        $"0007FF80 0007FFC0"
        $"0007FFE0 0007FFF0"
        $"1FFFFFF8 1FFFFFF8"
        $"1FFFFFF8 1FFFFFF8"
        $"1FFFFFF8 1FFFFFF8"
        $"1FFFFFF8 1FFFFFF8"
        $"1FFFFFF8 7FFFFFFE"
        $"FFFFFFFF FFFFFFFF"
        $"FFFFFFFF FFFFFFFF"
        $"FFFFFFFF FFFFFFFF"
        $"FFFFFFFF FFFFFFFF"
        $"FFFFFFFF FFFFFFFF"
        $"FFFFFFFF FFFFFFFF"
        $"7FFFFFFE 00000000"
    }
};

resource 'ics#' (128) {
    {  /* icon */
        $"0000 0000 01F8 010C"
        $"7F0E 4102 4102 4102"
        $"4102 7FFE 8001 BBF5"
        $"A4A9 BAA5 8001 7FFE"
    ,   /* mask */
        $"0000 0000 01F8 01FC"
        $"7FFE 7FFE 7FFE 7FFE"
        $"7FFE 7FFE FFFF FFFF"
        $"FFFF FFFF FFFF 7FFE"
    }
};

/* 16 colours. */

resource 'icl4' (128) {
        $"00000000000000000000000000000000"
        $"00000000000000000000000000000000"
        $"00000000000000000000000000000000"
        $"00000000000000000000000000000000"
        $"0000000000000FFFFFFFFFFFF0000000"
        $"0000000000000F0000000000FF000000"
        $"0000000000000F0000000000F0F00000"
        $"0000000000000F0000000000F00F0000"
        $"000FFFFFFFFFFF0000000000FFFFF000"
        $"000F00000000DF00000000000000F000"
        $"000F00000000DF00000000000000F000"
        $"000F00000000DF00000000000000F000"
        $"000F0FFFF000DF00000000000000F000"
        $"000F0F00F00FFF00000000000000F000"
        $"000F0FFFF0FCCF00000000000000F000"
        $"000F000000FCCF00000000000000F000"
        $"000FCCCCFCCFFFCCCCCCCCCCCCCCF000"
        $"0FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0"
        $"F000000000000000000000000000000F"
        $"FCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCF"
        $"FCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCF"
        $"FCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCF"
        $"FCFFFCFCFCFFFCFFCCCFCCCFFCFFFCCF"
        $"FCFCCCFCFCCFCCFCFCFCFCFCCCCFCCCF"
        $"FCFFCCCFCCCFCCFFCCFFFCFCCCCFCCCF"
        $"FCFCCCFCFCCFCCFCFCFCFCFCCCCFCCCF"
        $"FCFFFCFCFCCFCCFCFCFCFCCFFCCFCCCF"
        $"FCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCF"
        $"FCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCF"
        $"FDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDF"
        $"0FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0"
        $"00000000000000000000000000000000"
};

resource 'ics4' (128) {
        $"0000000000000000 0000000000000000"
        $"0000000FFFFFF000 0000000F0000FF00"
        $"0FFFFFFF0000FFF0 0F0000CF000000F0"
        $"0F0000CF000000F0 0F0000CF000000F0"
        $"0F0000CFCCCCCCF0 0FFFFFFFFFFFFFF0"
        $"F00000000000000F FCFFFCFFFFFFCFCF"
        $"FCFCCFCCFCFCFCCF FCFFFCFCFCFCCFCF"
        $"FCCCCCCCCCCCCCCF 0FFFFFFFFFFFFFF0"
};

/* 256 colours, Apple's icon colours only - see PALETTE above. */

resource 'icl8' (128) {
        $"0000000000000000000000000000000000000000000000000000000000000000"
        $"0000000000000000000000000000000000000000000000000000000000000000"
        $"0000000000000000000000000000000000000000000000000000000000000000"
        $"0000000000000000000000000000000000000000000000000000000000000000"
        $"00000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF00000000000000"
        $"00000000000000000000000000FFF5F5F5F5F5F5F5F5F5F5FFFF000000000000"
        $"00000000000000000000000000FFF5F5F5F5F5F5F5F5F5F5FFF5FF0000000000"
        $"00000000000000000000000000FFF5F5F5F5F5F5F5F5F5F5FFF5F5FF00000000"
        $"000000FFFFFFFFFFFFFFFFFFFFFFF5F5F5F5F5F5F5F5F5F5FFFFFFFFFF000000"
        $"000000FFF5F5F5F5F5F5F5F5FAFFF5F5F5F5F5F5F5F5F5F5F5F5F5F5FF000000"
        $"000000FFF5F5F5F5F5F5F5F5FAFFF5F5F5F5F5F5F5F5F5F5F5F5F5F5FF000000"
        $"000000FFF5F5F5F5F5F5F5F5FAFFF5F5F5F5F5F5F5F5F5F5F5F5F500FF000000"
        $"000000FFF5FFFFFFFFF5F5F5FAFFF5F5F5F5F5F5F5F5F5F5F5F5F5F5FF000000"
        $"000000FFF5FF4848FFF5F5FFFFFFF5F5F5F5F5F5F5F5F5F5F5F5F5F5FF000000"
        $"000000FFF5FFFFFFFFF5FF1313FFF5F5F5F5F5F5F5F5F5F5F5F5F5F5FF000000"
        $"000000FFF5F5F5F5F5F5FF1313FFF5F5F5F5F5F5F5F5F5F5F5F5F5F5FF000000"
        $"000000FF2B2B2B2BFF2B2BFFFFFF2B2B2B2B2B2B2B2B2B2B2B2B2B2BFF000000"
        $"00FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00"
        $"FF000000000000000000000000000000000000000000000000000000000000FF"
        $"FF2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2BFF"
        $"FF2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2BFF"
        $"FF2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2BFF"
        $"FF2BFFFFFF2BFF2BFF2BFFFFFF2BFFFF2B2B2BFF2B2B2BFFFF2BFFFFFF2B2BFF"
        $"FF2BFF2B2B2BFF2BFF2B2BFF2B2BFF2BFF2BFF2BFF2BFF2B2B2B2BFF2B2B2BFF"
        $"FF2BFFFF2B2B2BFF2B2B2BFF2B2BFFFF2B2BFFFFFF2BFF2B2B2B2BFF2B2B2BFF"
        $"FF2BFF2B2B2BFF2BFF2B2BFF2B2BFF2BFF2BFF2BFF2BFF2B2B2B2BFF2B2B2BFF"
        $"FF2BFFFFFF2BFF2BFF2B2BFF2B2BFF2BFF2BFF2BFF2B2BFFFF2B2BFF2B2B2BFF"
        $"FF2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2BFF"
        $"FF2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2B2BFF"
        $"FFFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFAFF"
        $"00FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00"
        $"0000000000000000000000000000000000000000000000000000000000000000"
};

resource 'ics8' (128) {
        $"00000000000000000000000000000000"
        $"00000000000000000000000000000000"
        $"00000000000000FFFFFFFFFFFF000000"
        $"00000000000000FFF5F5F5F5FFFF0000"
        $"00FFFFFFFFFFFFFFF5F5F5F5FFFFFF00"
        $"00FFF5F5F5F52BFFF5F5F5F5F5F5FF00"
        $"00FFF5F5F5F52BFFF5F5F5F5F5F5FF00"
        $"00FFF5F5F5F52BFFF5F5F5F5F5F5FF00"
        $"00FFF5F5F5F52BFF2B2B2B2B2B2BFF00"
        $"00FFFFFFFFFFFFFFFFFFFFFFFFFFFF00"
        $"FF0000000000000000000000000000FF"
        $"FF2BFFFFFF2BFFFFFFFFFFFF2BFF2BFF"
        $"FF2BFF2B2BFF2B2BFF2BFF2BFF2B2BFF"
        $"FF2BFFFFFF2BFF2BFF2BFF2B2BFF2BFF"
        $"FF2B2B2B2B2B2B2B2B2B2B2B2B2B2BFF"
        $"00FFFFFFFFFFFFFFFFFFFFFFFFFFFF00"
};

/* The BNDL owner must match the application's creator code. Keep it in step
   with the creator set in the build and in the 'SIZE' resource.          */

resource 'FREF' (128) { 'APPL', 0, "" };

/* '****' is the Finder's wildcard: every file type, whatever it says it is.
   Source: Inside Macintosh: Macintosh Toolbox Essentials, Finder Interface —
   "You can create a file reference resource that specifies '****' as the file
   type to allow users to drag all file types--including applications, system
   extensions, documents, and so on, but not including disks or folders--to
   your application icon." ('disk' and 'fold' are the other two, and neither
   is wanted: this application extracts one file.)

   The wildcard rather than a list of archive types, because the files this
   program is FOR are the ones whose type is wrong — a .hqx is 'TEXT', a raw
   download is '????' — and an enumeration would have refused exactly those.
   What is inside is unc_sniff's business, not the Finder's.

   Measured as well as read: with this resource and a file typed '????', the
   drop launches the application on System 7.0.1, and without it the same
   drag only moves the icon. Nothing below System 7 has the gesture at all
   (DECISIONS.md 2026-08-31). Local ID 1 maps to the archive icon,
   'ICN#' 129 (mac/macextract_archive_icons.r): the Finder draws a document
   by its CREATOR, so this shows only on files whose creator is ours, which
   MacStamp writes when the user picks MacExtract. Until 2026-10-25 it was
   the application's own 'ICN#', on the reading that no file carried our
   creator, and those archives drew as the application (DECISIONS.md
   2026-10-25, *the archives that drew as the application*). */
resource 'FREF' (129) { '****', 1, "" };

/* The exact types as well, one FREF each, because the wildcard is not a
   CLAIM. Mac OS 9's Finder, finding no application for a document's
   creator, offers "an alternate program" from the Desktop database's
   per-type entries, which the bundle's exact FREF types make and '****'
   does not: measured 2026-10-23 on Mac OS 9.2 with a BINA file — absent
   with the wildcard alone, listed above StuffIt Expander with 'BINA'
   (DECISIONS.md 2026-10-23, *the format 7.0.3 sniffs*). The list is the
   one MacStamp offers MacExtract for (its data/choices.tsv and
   formats.tsv, re-read 2026-10-24 at its 16948e9): the type each of those formats carries, and the
   `also` types beside it. That includes `SDar`, the maintainer's choice
   on 2026-10-24 for a SuperDisk! archive's data fork alone; a
   self-extractor that keeps its resource fork stays `APPL` with its own
   creator (`AlYS` or `alyS`), with `SDar`/`MExt` offered beside it. No
   file in MacStamp's 104,437-file census, TCDB or Apple's Internet Config
   tables carries the type `SDar`. NOT `Part`, though StuffIt Expander
   claims it: TCDB's "Translation in Process", and all eight such files
   on Info-Mac IV are finished programs with empty data forks, an
   expansion that stopped before retyping them — claimed 2026-10-24 and
   dropped the same day, and MacStamp's tables dropped it too. Re-read at
   MacStamp's 6896433 on 2026-10-25: the same 29 types. Each maps to icon
   local ID 1, the archive icon, for the reason above. The resource fork grows by about 12 bytes a type
   and no code changes. */
resource 'FREF' (130) { 'BINA', 1, "" };   /* MacBinary, AppleSingle (Apple's table) */
resource 'FREF' (131) { 'ApSi', 1, "" };   /* AppleSingle (StuffIt Expander's own) */
resource 'FREF' (132) { 'TEXT', 1, "" };   /* BinHex */
resource 'FREF' (133) { 'TARF', 1, "" };   /* tar */
resource 'FREF' (134) { 'PIT ', 1, "" };   /* PackIt */
resource 'FREF' (135) { 'SITD', 1, "" };   /* StuffIt */
resource 'FREF' (136) { 'SIT!', 1, "" };   /* StuffIt */
resource 'FREF' (137) { 'SIT5', 1, "" };   /* StuffIt 5 */
resource 'FREF' (138) { 'PACT', 1, "" };   /* Compact Pro */
resource 'FREF' (139) { 'DDA2', 1, "" };   /* DiskDoubler */
resource 'FREF' (140) { 'DDAR', 1, "" };   /* DiskDoubler */
resource 'FREF' (141) { 'Gzip', 1, "" };   /* gzip */
resource 'FREF' (142) { 'ZIP ', 1, "" };   /* zip */
resource 'FREF' (143) { 'ZIVU', 1, "" };   /* Unix compress */
resource 'FREF' (144) { 'LHA ', 1, "" };   /* LZH */
resource 'FREF' (145) { 'NCar', 1, "" };   /* Now Compress */
resource 'FREF' (146) { 'mArc', 1, "" };   /* ARC / ArcMac */
resource 'FREF' (147) { 'ZIVM', 1, "" };   /* MacCompress, the 1990 DiskDoubler header */
resource 'FREF' (148) { 'HBSF', 1, "" };   /* AppleLink package */
resource 'FREF' (149) { 'CSIT', 1, "" };   /* Private File */
resource 'FREF' (150) { 'SPSV', 1, "" };   /* StuffIt SpaceSaver */
resource 'FREF' (151) { 'SDar', 1, "" };   /* Alysis SuperDisk! archive: the maintainer's pair, 2026-10-24 */
resource 'FREF' (152) { 'Seg1', 1, "" };   /* StuffIt segment, first part */
resource 'FREF' (153) { 'Seg2', 1, "" };   /* StuffIt segment */
resource 'FREF' (154) { 'Seg3', 1, "" };   /* StuffIt segment */
resource 'FREF' (155) { 'SegN', 1, "" };   /* StuffIt segment */
resource 'FREF' (156) { 'SegM', 1, "" };   /* StuffIt segment */
resource 'FREF' (158) { 'DDSP', 1, "" };   /* DiskDoubler split part */
resource 'FREF' (157) { 'ARC7', 1, "" };   /* ARC 6/7 (ARC+Plus), which ArcMac cannot unpack */
/* DiskDoubler's single compressed files, creator `DDAP`: the types its own
   expanders declare — `DD01`, `DD02` (DDExpand 2.03a), `DDF0`-`DDF5`
   (DDExpand 3.1; DECISIONS.md, the expanders' BNDL table), `DDF6`, `DDF7`,
   `DDFL` (DD Expand, companion/app-bundles.tsv) — and `DDf4`, found on
   real files with `DDF0`-`DDF3`, `DD01` and `DDFL` by MacStamp's census
   (DECISIONS.md 2026-11-01, *the floor, and the second double-click*).
   MacExtract opens them by content already; without the types the Finder
   refuses them dropped on it and a `DDAP` helper passes them on. Not
   DiskDoubler's other declared types (`DDDA`, `DDTM`, `DDTD`, `DDCR`,
   `DDCP`, `DDCT`, `ADDA`): nothing here shows they are compressed files. */
resource 'FREF' (159) { 'DD01', 1, "" };
resource 'FREF' (160) { 'DD02', 1, "" };
resource 'FREF' (161) { 'DDF0', 1, "" };
resource 'FREF' (162) { 'DDF1', 1, "" };
resource 'FREF' (163) { 'DDF2', 1, "" };
resource 'FREF' (164) { 'DDF3', 1, "" };
resource 'FREF' (165) { 'DDF4', 1, "" };
resource 'FREF' (166) { 'DDF5', 1, "" };
resource 'FREF' (167) { 'DDF6', 1, "" };
resource 'FREF' (168) { 'DDF7', 1, "" };
resource 'FREF' (169) { 'DDFL', 1, "" };
resource 'FREF' (170) { 'DDf4', 1, "" };
/* MAR, the types mar 0.2.0 gives the archives it writes, creator `MARc`
   (reference/mar/mar-0.2.0-src/src/mar_io.c): `MARd` a folder's `.mar`,
   `MARf` a file's `.mac`. Its LZW-compressed archive is `ZIVU`, claimed
   above. DECISIONS.md 2026-11-03, *the archive that carries its own CRCs*.
   `LZ4-` is the type mar's own bundle declares for an LZ4-wrapped archive
   (reference/mar/mar-0.2.0-src/src/rsrc.r, FREF 132); mar writes none.
   DECISIONS.md 2026-11-04, *the frame mar 0.2.0 reads*. `LZ4 ` is the type
   MacStamp gives any other LZ4 frame, creator `MExt` (macstamp e0a62d7,
   the maintainer's choice): claimed for the archive icon and for a drop on
   MacExtract; a double-click opens it without (macstamp 08a9583). */
resource 'FREF' (171) { 'MARd', 1, "" };
resource 'FREF' (172) { 'MARf', 1, "" };
resource 'FREF' (173) { 'LZ4-', 1, "" };
resource 'FREF' (174) { 'LZ4 ', 1, "" };
/* Apple Backup, creator `OBBa`: `OBDa`, the type of "Apple Backup Data" on
   each backup floppy (three real disks, fixtures/SOURCES.md, abk-perfB-*);
   `OBDc`, the type of a restore CD's "Data File" copies: all 105 on the
   Performa 5400/6400 Software Restore CD (691-1264-A,B, 1996), read by
   MacStamp (macstamp a960b6c), whose rows for both pairs came after these
   claims. DECISIONS.md 2026-11-10, *the backup on floppies*. */
resource 'FREF' (175) { 'OBDa', 1, "" };
resource 'FREF' (176) { 'OBDc', 1, "" };
/* The Apple Installer Tome, `idcp`/`kakc`: read off the 39 Tomes of the
   System 7.5.5 and Mac OS 8.6 install media. No application claims the
   creator — the Installer is `kajr`, and its bundle names `kajr`, `bbkr`,
   `judy` and `bjbc` — so the `kakc` helper is what opens one by
   double-click. DECISIONS.md 2026-11-10, *the archive the Installer reads*. */
resource 'FREF' (177) { 'idcp', 1, "" };

resource 'BNDL' (128) {
    'MExt', 0,
    { 'ICN#', { 0, 128, 1, 129 },
       'FREF', { 0, 128, 1, 129,
                2, 130, 3, 131, 4, 132, 5, 133, 6, 134, 7, 135, 8, 136, 9, 137, 10, 138, 11, 139, 12, 140, 13, 141, 14, 142, 15, 143, 16, 144, 17, 145, 18, 146,
                19, 147, 20, 148, 21, 149, 22, 150, 23, 151,
                24, 152, 25, 153, 26, 154, 27, 155, 28, 156, 29, 158,
                30, 157,
                31, 159, 32, 160, 33, 161, 34, 162, 35, 163, 36, 164, 37, 165,
                38, 166, 39, 167, 40, 168, 41, 169, 42, 170,
                43, 171, 44, 172, 45, 173, 46, 174, 47, 175, 48, 176, 49, 177 } }
};

/* The SIGNATURE resource: type = the creator code, ID 0. The Finder wants
   it present to register an application's bundle; without it the 'BNDL' is
   ignored and the generic application diamond is drawn, with every other
   piece correct. Emitted as raw `data` because Rez has no type declaration
   for an arbitrary four-character type. Contents are conventionally a
   Pascal string describing the application. */
data 'MExt' (0, "MacExtract") {
    $"0A4D616345787472616374"
};

/* The version the FINDER shows, and the only place a user meets a version
   number without a command line. 'vers' 1 is the file's own version — Get
   Info's "Version:" line, and the Version column in a System 7 list view;
   'vers' 2 is the version of the package the file belongs to, which for a
   one-file distribution is the same number.

   Costs the application nothing: no code here opens these, so they are read
   by the Finder out of the resource fork and never enter this application's
   heap (BLOCKERS.md, the ballast row — only CODE is charged to the engine's
   budget).

   WHICH Finders display it is NOT measured here. System 7 and later do;
   whether Finder 5.1 under System 3.0 has a version line at all is open.

   Get Info shows the LONG string, and it is the VERSION — not the name. The
   box is already titled "MacExtract Info" and draws the name above the line,
   so "MacExtract 0.29.0" said it twice (photographed on System 6.0.8 and
   System 7.0.1 before this was fixed). The slot conventionally carries a
   copyright notice after the number; this one carries the number alone.

   The four numeric bytes are for programmatic comparison and are not what
   is displayed. Byte 2 carries the minor and bug-fix numbers as one BCD
   digit each (Multiverse.r declares the layout; the stage constants are its
   own names), so a minor of 35 does not fit and 0x35 is written for a reader
   that takes the byte whole — the hex digits read as the number. That byte
   said 0x31 from v0.31.0 to v0.34.0, and 0x35 from v0.36.0 to v0.37.0
   after this comment said it moved with them, because only the STRINGS
   were checked; tools/check_docs.py holds it too since v0.38.0. The
   STRINGS carry the real number, and check_docs.py holds both of them
   against UNC_VERSION — this file is
   the fourth place the version is written, after include/macextract.h,
   README.md and dist/README.txt, and the About alert in macextract_strings.h is
   the fifth. */

resource 'vers' (1, "MacExtract") {
    0x00, 0x45, release, 0x00, verUS,
    "0.45.0",
    "0.45.0"
};

resource 'vers' (2, "MacExtract") {
    0x00, 0x45, release, 0x00, verUS,
    "0.45.0",
    "0.45.0"
};
