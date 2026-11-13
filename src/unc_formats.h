/*
 * unc_formats.h — every format this engine reads, in one place.
 *
 * A format is its own source files and its lines here: no other file in
 * the tree keeps a list of formats. Every table that has a row per format
 * is expanded from the four lists here by the file that owns the table,
 * which hands each list the macro that makes its row:
 *
 *   UNC_FORMATS(FORMAT)   FORMAT(id, name, kind, extract, run, keep, join),
 *                         one row a format
 *   UNC_PROBES(PROBE)     PROBE(fn, answers), the sniffer's probes, IN THE
 *                         ORDER THEY RUN
 *   UNC_SEGIDS(SEGID)     SEGID(id, describe, match), the set schemes'
 *                         identity, IN THE ORDER unc_segment_describe
 *                         tries them
 *   UNC_DECODERS(DECODER) DECODER(fn), each extractor an overlay image
 *                         carries, once
 *
 * Lists of macro calls rather than a file included once per table, because
 * a table built inside a macro's argument (src/unc_engine.c, unc_maps)
 * cannot include anything there. Comments inside a list are fine; a line
 * that does not end in a backslash ends the list, and the compiler says
 * so.
 *
 * FORMAT's columns:
 *   id       the UncFormat value (include/macextract.h)
 *   name     what unc_format_name says
 *   kind     FILE, a format read as a file; ENVELOPE, one that holds
 *            exactly one file worth looking inside (unc_format_is_envelope;
 *            src/unc_engine.c says what qualifies); PART, one read only as
 *            part of a SET, which unc_extract_as refuses
 *   extract  the extractor, for FILE and ENVELOPE (0 for PART)
 *   run      the Macintosh build's dispatch row (mac/ovl_shim.c, gRun):
 *            RUN(image, entry point, flags), or NORUN for a format that
 *            dispatches through no image (mac/ovl_shim.c, unc_run_file)
 *   keep     what the eager release keeps for it (mac/release_plan.inc.c,
 *            gKeepSet): KEEP(flags), its run row's image and those flags,
 *            or NOKEEP, which keeps the whole bundle
 *   join     what it is as a set scheme (src/unc_segment.c, seg_schemes):
 *            JOIN_READ(flags, reader), parts read as an archive by
 *            `reader`; JOIN_EMIT(flags), parts joined into one file; or
 *            NOJOIN. THE ORDER OF THE JOIN ROWS below is the order of the
 *            Macintosh build's seg_schemes table, which is bytes in the
 *            application: keep it unless the bytes are meant to move.
 *
 * Adding a format is its own files and these lines; removing one, the
 * same out. What else it has, every place a compiler or a check names
 * when it is missing:
 *
 *   include/macextract.h   its UncFormat value, appended (ABI: a removed
 *                          format's number stays reserved there)
 *   this file              its FORMAT row; its PROBE where the probe
 *                          order's argument puts it; a SEGID if it is a
 *                          set scheme; a DECODER if its extractor is new
 *                          and in an image
 *   src/unc_internal.h     a set's match, if it has one; every other
 *                          function listed here is declared from the lists
 *   tools/overlay/         its entry point in its image: an OVL_*_EXTRACT
 *                          number in overlay.h and a case in ovl_<image>.c;
 *                          its sources in that image's rule in
 *                          mac/CMakeLists.txt, and out of the resident
 *                          link there. A new image is an OVL_ID_* in
 *                          overlay.h, an ovl_<image>.c and a rule; every
 *                          list of images follows from those
 *                          (tools/overlay/images.py)
 *   tools/retake_budgets.py   run, in the same commit, for every figure the
 *                          new bytes move; then tools/make_dist.sh
 *   its tests              fixtures/SOURCES.md and manifests, and its
 *                          harnesses: files in tests/harness/, which ci.sh
 *                          runs every one of, each named by a `Harness:`
 *                          line in its source's header
 *                          (tools/check_harnesses.py)
 *   its docs               FORMATS.md, README.md and the list in
 *                          tools/make_dist.sh, DECISIONS.md
 *
 * tools/check_ovl_rows.py cross-checks what a compiler cannot: that every
 * format the Macintosh dispatches has a run row and an alias.
 *
 * SPDX-License-Identifier: 0BSD
 */

#ifndef UNC_FORMATS_H
#define UNC_FORMATS_H

/* ------------------------------------------------------------------ */
/* Formats                                                            */
/* ------------------------------------------------------------------ */

#define UNC_FORMATS(FORMAT) \
    FORMAT(UNC_FORMAT_UNKNOWN, "unknown", PART, 0, NORUN, NOKEEP, NOJOIN) \
    \
    /* The envelopes, by the image their reader is in. An envelope keeps its \
     * own reader and what the format under it keeps, when the first bytes of \
     * its payload say (KEEP_PEEK; mac/release_plan.inc.c). */ \
    FORMAT(UNC_FORMAT_MACBINARY, "MacBinary", ENVELOPE, unc_macbinary_extract, \
           RUN(OVL_ID_BINHEX, OVL_MACBINARY_EXTRACT, 0), KEEP(KEEP_PEEK), NOJOIN) \
    FORMAT(UNC_FORMAT_APPLESINGLE, "AppleSingle", ENVELOPE, unc_appledouble_extract, \
           RUN(OVL_ID_BINHEX, OVL_APPLEDOUBLE_EXTRACT, 0), KEEP(KEEP_PEEK), NOJOIN) \
    FORMAT(UNC_FORMAT_APPLEDOUBLE, "AppleDouble", ENVELOPE, unc_appledouble_extract, \
           RUN(OVL_ID_BINHEX, OVL_APPLEDOUBLE_EXTRACT, 0), KEEP(KEEP_PEEK), NOJOIN) \
    FORMAT(UNC_FORMAT_BINHEX, "BinHex 4", ENVELOPE, unc_binhex_extract, \
           RUN(OVL_ID_BINHEX, OVL_BINHEX_EXTRACT, RUN_CODECS), KEEP(KEEP_PEEK), NOJOIN) \
    /* .hex and .hcx, both written by BinHex 2.0 (src/fmt_hecx.c). An envelope \
     * on the same terms as BinHex 4: it carries its own forks. Reached through \
     * unc_binhex_extract, which looks at UncCtx.fmt. */ \
    FORMAT(UNC_FORMAT_BINHEX_OLD, "BinHex hex/hcx", ENVELOPE, unc_binhex_extract, \
           RUN(OVL_ID_BINHEX, OVL_BINHEX_EXTRACT, RUN_CODECS), KEEP(KEEP_PEEK), NOJOIN) \
    /* .dl, SUMacC's, older than both: a resource fork alone. The same decoder, \
     * entered the same way. */ \
    FORMAT(UNC_FORMAT_DL, "SUMacC dl", ENVELOPE, unc_binhex_extract, \
           RUN(OVL_ID_BINHEX, OVL_BINHEX_EXTRACT, RUN_CODECS), KEEP(KEEP_PEEK), NOJOIN) \
    FORMAT(UNC_FORMAT_GZIP, "Gzip", ENVELOPE, unc_gzip_extract, \
           RUN(OVL_ID_EXO, OVL_GZIP_EXTRACT, RUN_CODECS), KEEP(KEEP_PEEK), NOJOIN) \
    FORMAT(UNC_FORMAT_COMPRESS_Z, "Unix compress", ENVELOPE, unc_compressz_extract, \
           RUN(OVL_ID_EXO, OVL_COMPRESSZ_EXTRACT, RUN_CODECS), KEEP(KEEP_PEEK), NOJOIN) \
    /* One stream in a frame, as `.Z`: mar 0.2.0's other compressed form of a \
     * MAR (src/fmt_lz4.c). */ \
    FORMAT(UNC_FORMAT_LZ4, "LZ4", ENVELOPE, unc_lz4_extract, \
           RUN(OVL_ID_ZIPOLD, OVL_LZ4_EXTRACT, 0), KEEP(KEEP_PEEK), NOJOIN) \
    FORMAT(UNC_FORMAT_UU, "uuencode", ENVELOPE, unc_uu_extract, \
           RUN(OVL_ID_TEXT, OVL_UU_EXTRACT, RUN_CODECS), KEEP(KEEP_PEEK), NOJOIN) \
    FORMAT(UNC_FORMAT_BTOA, "btoa", ENVELOPE, unc_btoa_extract, \
           RUN(OVL_ID_BTOA, OVL_BTOA_EXTRACT, RUN_CODECS), KEEP(KEEP_PEEK), NOJOIN) \
    FORMAT(UNC_FORMAT_BASE64, "base64", ENVELOPE, unc_b64_extract, \
           RUN(OVL_ID_TEXT, OVL_B64_EXTRACT, RUN_CODECS), KEEP(KEEP_PEEK), NOJOIN) \
    \
    /* StuffIt. A format that may carry an encrypted entry keeps the ciphers \
     * (KEEP_CRYPT): encryption is found per entry, and the release decides \
     * before it knows. */ \
    FORMAT(UNC_FORMAT_SIT, "StuffIt", FILE, unc_sit_extract, \
           RUN(OVL_ID_STUFFIT, OVL_SIT_EXTRACT, RUN_CODECS), KEEP(KEEP_CRYPT), NOJOIN) \
    FORMAT(UNC_FORMAT_SIT5, "StuffIt 5", FILE, unc_sit5_extract, \
           RUN(OVL_ID_STUFFIT, OVL_SIT5_EXTRACT, RUN_CODECS), KEEP(KEEP_CRYPT), NOJOIN) \
    /* A StuffIt segment: its parts join into one FILE, which unc_sitseg_emit \
     * writes; what that file is is unknown until it is joined, so it keeps \
     * the whole bundle. */ \
    FORMAT(UNC_FORMAT_SITSEG, "StuffIt segment", FILE, unc_sitseg_extract, \
           NORUN, NOKEEP, JOIN_EMIT(SEG_HOOK_SIT)) \
    FORMAT(UNC_FORMAT_SPACESAVER, "StuffIt SpaceSaver", FILE, unc_spacesaver_extract, \
           RUN(OVL_ID_SPACESAVER, OVL_SPACESAVER_EXTRACT, RUN_CODECS), \
           KEEP(0), NOJOIN) \
    /* An envelope: one file in, one file out — and the file PF Encrypt puts \
     * in is always a StuffIt archive it made first (fmt_pf.c). Its reader is \
     * in the StuffIt image beside the archive it always decrypts to, and its \
     * cipher calls cross to the crypt image through the resident shims, so \
     * it keeps the whole bundle. */ \
    FORMAT(UNC_FORMAT_PRIVATEFILE, "Private File", ENVELOPE, unc_pf_extract, \
           RUN(OVL_ID_STUFFIT, OVL_PF_EXTRACT, 0), NOKEEP, NOJOIN) \
    \
    /* Compact Pro, and its sets: addressed, read by the same reader over the \
     * joined parts, and matched in that reader's image, which the set keeps \
     * (RUN_MATCH). */ \
    FORMAT(UNC_FORMAT_COMPACTPRO, "Compact Pro", FILE, unc_cpt_extract, \
           RUN(OVL_ID_CPTDD, OVL_CPT_EXTRACT, RUN_CODECS), KEEP(KEEP_CRYPT), NOJOIN) \
    FORMAT(UNC_FORMAT_CPTSEG, "Compact Pro segment", PART, 0, \
           RUN(OVL_ID_CPTDD, OVL_CPT_EXTRACT, RUN_CODECS | RUN_MATCH), \
           KEEP(KEEP_CRYPT), JOIN_READ(SEG_ADDRESSED, unc_cpt_extract)) \
    \
    /* DiskDoubler, and its `SPLT` sets: the only scheme whose parts state their \
     * own payload length, joined into one FILE. */ \
    FORMAT(UNC_FORMAT_DISKDOUBLER, "DiskDoubler", FILE, unc_dd_extract, \
           RUN(OVL_ID_CPTDD, OVL_DD_EXTRACT, RUN_CODECS), KEEP(0), NOJOIN) \
    FORMAT(UNC_FORMAT_DDSEG, "DiskDoubler split", FILE, unc_ddseg_extract, \
           NORUN, NOKEEP, JOIN_EMIT(SEG_HOOK_DD)) \
    \
    /* Zip, and a spanned zip, read by zip's reader over the joined parts. \
     * KEEP_ZIPOLD is zip's Shrink, Reduce and Implode, which nothing else \
     * calls. */ \
    FORMAT(UNC_FORMAT_ZIP, "Zip", FILE, unc_zip_extract, \
           RUN(OVL_ID_EXO, OVL_ZIP_EXTRACT, RUN_CODECS | RUN_ZIPOLD), \
           KEEP(KEEP_CRYPT | KEEP_ZIPOLD), NOJOIN) \
    FORMAT(UNC_FORMAT_ZIPSEG, "Zip segment", FILE, unc_zipseg_extract, \
           RUN(OVL_ID_EXO, OVL_ZIP_EXTRACT, RUN_CODECS | RUN_ZIPOLD), \
           KEEP(KEEP_CRYPT | KEEP_ZIPOLD), JOIN_READ(SEG_ADDRESSED, unc_zip_extract)) \
    \
    /* The rest of the archives, each in its own image or beside a relative. */ \
    FORMAT(UNC_FORMAT_PACKIT, "PackIt", FILE, unc_packit_extract, \
           RUN(OVL_ID_PACKIT, OVL_PACKIT_EXTRACT, RUN_CODECS), KEEP(KEEP_CRYPT), NOJOIN) \
    FORMAT(UNC_FORMAT_LZH, "LZH", FILE, unc_lzh_extract, \
           RUN(OVL_ID_LZH, OVL_LZH_EXTRACT, RUN_CODECS), KEEP(0), NOJOIN) \
    FORMAT(UNC_FORMAT_ARC, "ARC", FILE, unc_arc_extract, \
           RUN(OVL_ID_ARC, OVL_ARC_EXTRACT, RUN_CODECS), KEEP(KEEP_CRYPT), NOJOIN) \
    FORMAT(UNC_FORMAT_NOWCOMPRESS, "Now Compress", FILE, unc_now_extract, \
           RUN(OVL_ID_NOW, OVL_NOW_EXTRACT, RUN_CODECS), KEEP(0), NOJOIN) \
    FORMAT(UNC_FORMAT_SUPERDISK, "SuperDisk!", FILE, unc_superdisk_extract, \
           RUN(OVL_ID_SUPERDISK, OVL_SUPERDISK_EXTRACT, RUN_CODECS), KEEP(0), NOJOIN) \
    /* An AppleLink package cannot be encrypted: the format has no password \
     * anywhere in it, and its own expander never asks for one. */ \
    FORMAT(UNC_FORMAT_SQP, "AppleLink package", FILE, unc_sqp_extract, \
           RUN(OVL_ID_SQP, OVL_SQP_EXTRACT, RUN_CODECS), KEEP(0), NOJOIN) \
    /* Tar is in zip's old-methods image; src/fmt_tar.c says why. */ \
    FORMAT(UNC_FORMAT_TAR, "Tar", FILE, unc_tar_extract, \
           RUN(OVL_ID_ZIPOLD, OVL_TAR_EXTRACT, RUN_CODECS), KEEP(0), NOJOIN) \
    /* MAR beside it: stored forks, no codec, no password (src/fmt_mar.c). Not \
     * an envelope even as a `.mac`, which holds one file: the format is the \
     * same when it holds a folder. */ \
    FORMAT(UNC_FORMAT_MAR, "MAR", FILE, unc_mar_extract, \
           RUN(OVL_ID_ZIPOLD, OVL_MAR_EXTRACT, 0), KEEP(0), NOJOIN) \
    /* And the Installer Tome: its own window, no codec (src/fmt_tome.c). */ \
    FORMAT(UNC_FORMAT_TOME, "Installer Tome", FILE, unc_tome_extract, \
           RUN(OVL_ID_ZIPOLD, OVL_TOME_EXTRACT, 0), KEEP(0), NOJOIN) \
    /* Apple Backup, one disk of a set: read only as a set, a set of one \
     * included, because only the joiner can hand the reader the next disk. \
     * Addressed, its reader asking for each disk in turn and never reading \
     * past one's used length; matched in its reader's image (fmt_abk.c). */ \
    FORMAT(UNC_FORMAT_ABK, "Apple Backup", PART, 0, \
           RUN(OVL_ID_ZIPOLD, OVL_ABK_EXTRACT, RUN_MATCH), KEEP(0), \
           JOIN_READ(SEG_ADDRESSED, unc_abk_extract)) \
    \
    /* MIME. A message keeps the whole bundle: its parts can be anything. A \
     * message/partial part is half a message; the parts join into a MESSAGE, \
     * read by the MIME walk, with no file emitted in between. */ \
    FORMAT(UNC_FORMAT_MIME, "MIME message", FILE, unc_mime_extract, \
           RUN(OVL_ID_TEXT, OVL_MIME_EXTRACT, RUN_CODECS), NOKEEP, NOJOIN) \
    FORMAT(UNC_FORMAT_MIMESEG, "message/partial part", PART, 0, \
           RUN(OVL_ID_TEXT, OVL_MIME_EXTRACT, RUN_CODECS), NOKEEP, \
           JOIN_READ(SEG_HOOK_MIME, unc_mime_extract)) \
    \
    /* A part of a plain NAME.001 split is an anonymous slice of bytes: no \
     * header to read it as, so unc_extract_as has no case for it, and the \
     * host's names and sizes are the whole map. The host decides by name and \
     * calls unc_extract_segments. */ \
    FORMAT(UNC_FORMAT_SPLIT, "Split file", PART, 0, NORUN, NOKEEP, \
           JOIN_EMIT(SEG_ANONYMOUS))

/* ------------------------------------------------------------------ */
/* The sniffer's probes                                               */
/*                                                                    */
/* Content only, never extensions: each probe is handed the first     */
/* bytes of the file, and those that need more context (MacBinary     */
/* CRC, tar at 257, Compact Pro trailer) get the io handle too. The   */
/* first to answer wins. ENVELOPE marks a probe that can answer an    */
/* envelope format, which unc_sniff_envelope runs alone, in this      */
/* order; ARCHIVE, one that answers only formats that are not.        */
/*                                                                    */
/* The order IS the algorithm, and each step of it is argued below.   */
/* Nothing here is alphabetical or accidental: a probe that cannot be */
/* wrong goes before one that can, and a probe for a PART of a set    */
/* goes before the probe for the whole it resembles.                  */
/* ------------------------------------------------------------------ */

#define UNC_PROBES(PROBE) \
    /* Strong magic numbers first. */ \
    PROBE(unc_sit5_probe, ARCHIVE) \
    PROBE(unc_sit_probe, ARCHIVE) \
    PROBE(unc_sitseg_probe, ARCHIVE) \
    /* DiskDoubler's `SPLT`: two copies of its magic, 90 bytes apart. */ \
    PROBE(unc_ddseg_probe, ARCHIVE) \
    /* 'SIT!' again, but with 'DFD3' behind it: SpaceSaver's header, and \
     * the StuffIt probe above would never claim it (its second long is \
     * 'rLau'). */ \
    PROBE(unc_spacesaver_probe, ARCHIVE) \
    PROBE(unc_packit_probe, ARCHIVE) \
    PROBE(unc_gzip_probe, ENVELOPE) \
    PROBE(unc_compressz_probe, ENVELOPE) \
    /* A 4-byte magic and a descriptor's version and reserved bits \
     * (fmt_lz4_probe.c). */ \
    PROBE(unc_lz4_probe, ENVELOPE) \
    /* 'CSIT' and a version word, confirmed by a second 'CSIT' twelve \
     * bytes from the end. Neither StuffIt probe above can take one: their \
     * magics are 'SIT!' and the StuffIt 5 banner (fmt_pf.c). */ \
    PROBE(unc_pf_probe, ENVELOPE) \
    /* "MAR" 0x80 and a CRC-32 of the 124 bytes before the one it ends \
     * the record with (fmt_mar.c). Its byte 0 is 'M', so MacBinary \
     * below could not take one either. */ \
    PROBE(unc_mar_probe, ARCHIVE) \
    /* 'CMWL' at +2 and 'RLDW' at 0x600 (fmt_abk_probe.c). Ahead of the \
     * Compact Pro segment probe below, which a byte 0 of 1 would reach. */ \
    PROBE(unc_abk_probe, ARCHIVE) \
    /* "kc" 00 01, the records' offset and a table that fits the file \
     * (fmt_tome_probe.c). Byte 0 is 'k', which MacBinary below wants \
     * zero. */ \
    PROBE(unc_tome_probe, ARCHIVE) \
    /* MacBinary has no magic number, only a header CRC and structural \
     * constraints, which is why it used to sit LAST — the weakest test \
     * claims a file only when nothing stronger has. It is here instead \
     * because of what it costs to leave it there: MacBinary is 234 of \
     * the corpus's 932 fixtures, the most common format in it, and every \
     * one of them walked a 64 KB backwards scan for a zip's \
     * end-of-central-directory record, then twenty more probes, before \
     * reaching a test that is a CRC-16 over 124 bytes it has already \
     * read. It is placed AFTER the magic numbers, so nothing with a \
     * signature can be taken from it, and the constraints it adds to \
     * that CRC — byte 0, byte 74, byte 82 and bytes 108..115 all zero, \
     * plus a valid Pascal name — reject the head of every format probed \
     * below (AppleSingle's 0x00051600 fails the name test; Compact Pro, \
     * ARC, tar and Disk Copy all have a non-zero byte 0). 932 fixtures \
     * and 9,320 robustness variants are what actually grade that. */ \
    PROBE(unc_macbinary_probe, ENVELOPE) \
    /* Four more magic numbers, and the two Compact Pro probes, AHEAD of \
     * the zip pair rather than behind it (2026-09-18). The spanned-zip \
     * probe below scans the last 64 KB of the file backwards in 1 KB \
     * reads, so every file that reached it paid up to 65 reads before \
     * its own probe ran — on a Mac Plus reading a floppy, that is the \
     * open latency. None of these six can take a zip or a part of one: \
     * every zip head starts 'P' 'K', where LZH wants '-' at byte 2, \
     * Now Compress 0x00 0x02 at byte 0, DiskDoubler one of three \
     * four-byte magics, AppleSingle its own, and both Compact Pro \
     * probes a first byte of 1. The reverse — a Compact Pro archive \
     * carrying a stored zip part in its last 64 KB — used to be claimed \
     * as a zip segment, and is now the archive it is. SuperDisk! stays \
     * behind the zip pair, being weak on its own (below). */ \
    PROBE(unc_lzh_probe, ARCHIVE) \
    PROBE(unc_nowcompress_probe, ARCHIVE) \
    PROBE(unc_diskdoubler_probe, ARCHIVE) \
    /* One probe, two formats: they share a magic and differ in it. */ \
    PROBE(unc_applesingle_probe, ENVELOPE) \
    /* Before the plain Compact Pro probe, and for the same reason the \
     * spanned-zip probe precedes the zip one: the FINAL segment of a set \
     * carries a valid index and would be claimed as a whole archive, \
     * which would then read every entry at an offset belonging to some \
     * other volume. What separates them is the volume byte and the index \
     * offset, and only this probe looks at those. */ \
    PROBE(unc_cptseg_probe, ARCHIVE) \
    PROBE(unc_cpt_probe, ARCHIVE) \
    /* Before the plain zip probe, and not after: the two parts of a \
     * spanned set that are recognizable at all both look enough like a \
     * zip for that probe to claim them, and it would then be reported \
     * as an archive that happens to be broken rather than as a piece of \
     * one. This costs every file that reaches here a bounded backwards \
     * scan for an end-of-central-directory record; a whole zip has one \
     * in its last 512 bytes, so it pays a single read. \
     * \
     * It is also where a zip is recognised BEHIND something else — a \
     * self-extracting archive, whose first bytes are code. The record \
     * this probe already has in hand says where the central directory \
     * is, absolutely, so the decoder needs nothing extra and neither \
     * does the sniff: one four-byte read confirms the directory is \
     * there. Nothing below is reached by such a file today, and nothing \
     * above can be taken from it — every probe ahead of this one has a \
     * magic number at a fixed offset, and 8,364 files that are not \
     * archives were swept for the claim (FORMATS.md, *What the zip pair \
     * claims, and what it costs*). */ \
    PROBE(unc_zipseg_probe, ARCHIVE) \
    PROBE(unc_zip_probe, ARCHIVE) \
    /* SuperDisk!'s own mark is a module signature or a record tag at \
     * byte 8, either way confirmed by the 0x27 record that must end \
     * the file — weak on its own, so it sits after the magics. */ \
    PROBE(unc_superdisk_probe, ARCHIVE) \
    /* An AppleLink package has no magic number at all, so its probe is \
     * the container's own arithmetic — a version byte, eight zero bytes \
     * and a directory whose forks tile the file to its last byte. It \
     * costs a file that is not one ten bytes already read, which is why \
     * it sits here rather than at the end: everything below scans, and a \
     * package that reached them would pay for the scan before being \
     * recognised (fmt_sqp_probe.c). */ \
    PROBE(unc_sqp_probe, ARCHIVE) \
    \
    /* Weaker/structural probes. */ \
    PROBE(unc_tar_probe, ARCHIVE) \
    /* ARC's magic is one byte (0x1a), so the probe leans on the whole \
     * header: a printable 13-byte name, a known method, and sizes that \
     * land on the next header or the end marker. */ \
    PROBE(unc_arc_probe, ARCHIVE) \
    /* BinHex last: it scans for a banner amid mail garbage. uuencode \
     * and btoa sit beside it — same habitat, same kind of scan — and \
     * before it, because BinHex's probe reads on past its own banner \
     * and neither of those has one to find. btoa goes first of the \
     * three: its marker is a whole word at the start of a line, where \
     * uuencode's is a "begin" that prose contains. */ \
    /* Before those three, and not after: each of them scans for a \
     * document ANYWHERE in a file, so a multipart message holding one \
     * as a part would be claimed whole on the strength of that part, \
     * and every other part dropped — measured, and the reason this \
     * entry exists (DECISIONS.md 2026-08-29, a part that hid its \
     * message). Only a message declaring a multipart WITH a boundary is \
     * claimed here; a posting whose body is one uuencoded or BinHex \
     * document has no boundary and still belongs to its own format. */ \
    /* A part of a SET before the whole it resembles, which is the same \
     * rule the spanned-zip and Compact Pro segment probes sit under: \
     * part 1 of a message/partial set is a message and would be read \
     * as the one it is a slice of. */ \
    PROBE(unc_mimeseg_probe, ARCHIVE) \
    PROBE(unc_mime_probe_multipart, ARCHIVE) \
    PROBE(unc_btoa_probe, ENVELOPE) \
    PROBE(unc_uu_probe, ENVELOPE) \
    PROBE(unc_binhex_probe, ENVELOPE) \
    /* Last of all, and deliberately: base64 has no marker at all in its \
     * bare shape, and a MIME message is claimed only when it carries a \
     * part to extract. Everything the three probes above read — a \
     * BinHex banner, a "begin" line with a length that agrees, btoa's \
     * word — is a stronger claim on the same kind of file, and a mail \
     * message with a .hqx in its body is a BinHex file that happens to \
     * have headers rather than a message with an attachment. */ \
    PROBE(unc_mime_probe, ARCHIVE) \
    PROBE(unc_b64_probe, ENVELOPE)

/* ------------------------------------------------------------------ */
/* Which set a file belongs to (src/unc_segid.c)                      */
/*                                                                    */
/* The ORDER is the order unc_segment_describe tries them in. SPLIT   */
/* has no row: a part of a plain NAME.001 split is an anonymous slice */
/* of bytes, so nothing here can recognise one, and a host that has   */
/* decided by name builds the descriptor itself. A match of 0 is a    */
/* scheme whose parts carry no identity, which is not the same as     */
/* "no" (include/macextract.h says why).                              */
/* ------------------------------------------------------------------ */

#define UNC_SEGIDS(SEGID) \
    /* StuffIt first: it decides on 100 bytes at offset 0, where the zip \
     * scheme has to hunt backwards from the end of the file. */ \
    SEGID(UNC_FORMAT_SITSEG,  unc_sitseg_describe,  unc_sitseg_match) \
    /* Apple Backup ahead of Compact Pro, whose describe would take one of \
     * its disks: a version byte of 1 at 0 and a non-zero longword at 4 are \
     * all a Compact Pro segment has to show. 'CMWL' at +2 is what an Apple \
     * Backup disk has, and every disk states the count. */ \
    SEGID(UNC_FORMAT_ABK,     unc_abk_describe,     unc_abk_match) \
    /* Compact Pro next: like StuffIt it decides on a header at offset 0. \
     * Unlike StuffIt, a part that is not the LAST one answers with \
     * nparts == 0 - it knows the set it belongs to but not how big the set \
     * is, and the host is expected to go and find the final segment. */ \
    SEGID(UNC_FORMAT_CPTSEG,  unc_cptseg_describe,  unc_cptseg_match) \
    /* DiskDoubler's `SPLT`, also decided at offset 0 - and on a second copy \
     * of its magic at offset 90, so it is the cheapest to refuse. */ \
    SEGID(UNC_FORMAT_DDSEG,   unc_ddseg_describe,   unc_ddseg_match) \
    SEGID(UNC_FORMAT_ZIPSEG,  unc_zipseg_describe,  0) \
    /* message/partial, whose describe() reads a mail header block and is \
     * therefore the dearest of them: it goes after every scheme that decides \
     * on a magic at offset 0. */ \
    SEGID(UNC_FORMAT_MIMESEG, unc_mimeseg_describe, 0)

/* ------------------------------------------------------------------ */
/* The extractors the overlay images carry, each once: on the         */
/* Macintosh build with images every one of them is an alias of the  */
/* one dispatch, which finds its row by UncCtx.fmt (mac/ovl_shim.c).  */
/* ------------------------------------------------------------------ */

#define UNC_DECODERS(DECODER) \
    DECODER(unc_spacesaver_extract) \
    DECODER(unc_cpt_extract) \
    DECODER(unc_dd_extract) \
    DECODER(unc_lzh_extract) \
    DECODER(unc_arc_extract) \
    DECODER(unc_now_extract) \
    DECODER(unc_superdisk_extract) \
    DECODER(unc_packit_extract) \
    DECODER(unc_sqp_extract) \
    DECODER(unc_mime_extract) \
    DECODER(unc_uu_extract) \
    DECODER(unc_btoa_extract) \
    DECODER(unc_b64_extract) \
    DECODER(unc_binhex_extract) \
    DECODER(unc_macbinary_extract) \
    DECODER(unc_appledouble_extract) \
    DECODER(unc_sit_extract) \
    DECODER(unc_sit5_extract) \
    DECODER(unc_pf_extract) \
    DECODER(unc_zip_extract) \
    DECODER(unc_gzip_extract) \
    DECODER(unc_compressz_extract) \
    DECODER(unc_tar_extract) \
    DECODER(unc_mar_extract) \
    DECODER(unc_lz4_extract) \
    DECODER(unc_abk_extract) \
    DECODER(unc_tome_extract)

#endif /* UNC_FORMATS_H */
