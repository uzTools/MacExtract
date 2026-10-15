/*
 * macextract_strings.h — every piece of text the Macintosh application
 * shows, in one place. License: LGPL-2.1-or-later.
 *
 * Included by BOTH macextract.r (Rez) and macextract_mac.c (C), so it holds
 * nothing but #defines of plain string literals. The two languages do not
 * share escapes: Rez writes the ellipsis as "\0xC9", C would need "\xC9", so
 * a string meant for one of them is never used by the other. Each section
 * says which.
 *
 * Fragments joined at run time keep their spaces; <...> in a comment is what
 * the code fills in. Rewording a report line? tools/run_macnames.py matches
 * some of them word for word.
 *
 * The engine's own text (format names, unc_strerror) is in src/unc_engine.c,
 * shared with the CLI; two of its strings reach this application:
 * unc_format_name in S_OUT_FOREIGN_*, unc_strerror(UNC_ERR_MODULE) in a
 * report line. The version in S_ABOUT is held to UNC_VERSION by
 * tools/check_docs.py.
 */
#ifndef MACEXTRACT_STRINGS_H
#define MACEXTRACT_STRINGS_H

/* ---- Rez: menus, dialogs and alerts (macextract.r) ----------------- */

#define S_MENU_ABOUT        "About MacExtract\0xC9"
#define S_MENU_FILE         "File"
#define S_MENU_QUIT         "Quit"

#define S_ABOUT             "MacExtract 0.40.0"

#define S_BTN_OK            "OK"
#define S_BTN_CANCEL        "Cancel"

/* The progress window. Its status line is replaced before it is drawn. */
#define S_PROGRESS_TITLE    "MacExtract"
#define S_PROGRESS_STATUS   "Extracting"

/* The decoders could not be read again for the next archive. */
#define S_NO_RELOAD         "MacExtract could not get ready for the next " \
                            "archive. Open it again."

/* A part of a segmented archive was not found. ^0 is
 * `Part <N> of "<name>"`, ^1 is S_SEG_LEFT_* or empty. */
#define S_SEG_FIND          "Find..."
#define S_SEG_SKIP          "Skip"
#define S_SEG_MISSING       "^0 has not been found.^1"
#define S_SEG_EJECTED       "Please insert the disk containing ^0.^1"

#define S_REPORT_SAVE       "Save as Text\0xC9"

/* ---- C: progress window (macextract_mac.c) -------------------------- */

/* "Extracting <archive>" */
#define S_PROG_EXTRACTING   "Extracting "
/* "<N>%   about <N> minutes left", "<N>%   estimating time left" */
#define S_PROG_PERCENT      "%"
#define S_PROG_ESTIMATING   "   estimating time left"
#define S_PROG_ABOUT        "   about "
#define S_PROG_SECONDS      " seconds left"
#define S_PROG_MINUTE       " minute left"
#define S_PROG_MINUTES      " minutes left"
#define S_PROG_START        "0" S_PROG_PERCENT S_PROG_ESTIMATING

/* ---- C: password dialog --------------------------------------------- */

/* The first ask: '"<archive>" is encrypted. ...'. Every ask after it:
 * S_PASS_REFUSED alone. */
#define S_PASS_OPEN_QUOTE   "\""
#define S_PASS_ENCRYPTED    "\" is encrypted. Please enter its password."
#define S_PASS_REFUSED      "Incorrect password."

/* ---- C: segmented archives ------------------------------------------ */

/* ^0 of the alerts above: `Part <N> of "<name>"` */
#define S_SEG_PART          "Part "
#define S_SEG_OF            " of \""
#define S_SEG_CLOSE_QUOTE   "\""
/* ^1: " About <N>K still to read." or " About <N> bytes still to read." */
#define S_SEG_LEFT_ABOUT    " About "
#define S_SEG_LEFT_K        "K"
#define S_SEG_LEFT_BYTES    " bytes"
#define S_SEG_LEFT_END      " still to read."
/* Find... picked the wrong part: "This is part <N>. Please choose Part <M>." */
#define S_SEG_OTHER_PART    "This is part "
#define S_SEG_OTHER_SAME    ". Please choose Part "
#define S_SEG_OTHER_NEEDED  "."
#define S_SEG_NOT_PART      "Incorrect file."

/* ---- C: Standard File ----------------------------------------------- */

/* Standard File's prompt does not wrap: about 200 points, then it is cut. */
#define S_SF_DEST_PROMPT    "Extract into this folder:"
#define S_SF_DEST_NAME      "Extract here"
#define S_SF_REPORT_PROMPT  "Save the report as:"
#define S_SF_REPORT_NAME    "Extraction Report"

/* ---- C: names written to the disk ----------------------------------- */

#define S_FILE_COMMENTS     "Comments"
/* "MacExtract part <N>", temporary, deleted after the run */
#define S_FILE_PART         "MacExtract part "

/* ---- C: the report's lines ------------------------------------------ */

/* Every line starts with the entry's name, <name> below. */
#define S_REP_UNNAMED       "An unnamed entry"
/* "and <N> more, which this list had no room for" */
#define S_REP_MORE          "and "
#define S_REP_MORE_END      " more, which this list had no room for"

/* "[Folder ]<name> renamed to <new>", "Folder <name> combined with <other>" */
#define S_REP_FOLDER        "Folder "
#define S_REP_RENAMED       " renamed to "
#define S_REP_COMBINED      " combined with "
#define S_REP_LOST_CHARS    " was named in characters this Macintosh " \
                            "cannot write"
#define S_REP_PATH_CUT      " is in a folder whose path had to be shortened"
/* "The archive's comment: Comments written as <new>" */
#define S_REP_COMMENT       "The archive's comment: "
#define S_REP_WRITTEN_AS    " written as "
#define S_REP_NOTE_LOST     "The note this archive carries could not be " \
                            "written to the disk"

/* "<name>" followed by one of these. */
#define S_REP_DIR_FAILED    " could not be made on the disk"
#define S_REP_NO_NAME       " could not be given a name of its own"
#define S_REP_OVER_2GB      " is over 2 GB, too large here"
#define S_REP_NOT_CREATED   " could not be created on the disk"
#define S_REP_INEXACT       " opens, but is not the original file"
#define S_REP_TOOLARGE      " is too large for this version and was not " \
                            "extracted"
#define S_REP_MEM           " needs more memory than was free"
#define S_REP_UNSUPPORTED   " uses a method this version cannot read"
#define S_REP_CRC           " is damaged: its checksum does not match"
#define S_REP_TRUNCATED     " ends early: the archive is incomplete"
#define S_REP_ENCRYPTED     " is encrypted and was skipped"
#define S_REP_SINK          " could not be written to the disk"
#define S_REP_IO            " could not be read from the archive"
#define S_REP_FAILED        " could not be extracted"

/* ---- C: how the run ended -------------------------------------------- */

/* An alert of its own, or the report's last line. Listed in the order
 * they are tested in: the first that applies is the one shown. The alert
 * wraps between 32 and 36 characters, and a third line sits level with
 * the OK button. */
#define S_OUT_DISK_FULL     "The disk is full. Free up some space and " \
                            "try again."
#define S_OUT_CANCELLED     "Extraction cancelled."
#define S_OUT_MORE_PARTS    "This archive has more parts. Find them and " \
                            "try again."
#define S_OUT_CANNOT_OPEN   "Could not open the archive."
/* "Needs at least <N>K more memory. ..." */
#define S_OUT_NEEDS         "Needs at least "
#define S_OUT_NEEDS_GROW    "K more memory. Give MacExtract more in Get " \
                            "Info, or start up without MultiFinder."
#define S_OUT_NEEDS_FREE    "K more memory than this Macintosh has free."
#define S_OUT_FRAGMENTED    "Memory is too broken up. Quit other programs " \
                            "and try again."
/* "MacExtract cannot open <format> files." */
#define S_OUT_FOREIGN       "MacExtract cannot open "
#define S_OUT_FOREIGN_END   " files."
#define S_OUT_STOPPED       "Extraction stopped part way through this " \
                            "archive."
#define S_OUT_FAILED        "This file could not be extracted."
#define S_OUT_SOME_UNSUPP   "Some entries use a method this version " \
                            "cannot read yet."
#define S_OUT_SOME_FAILED   "Some entries could not be extracted."
/* Instead of the two above when the report lists the entries. */
#define S_OUT_FINISHED      "Extraction finished."
#define S_OUT_COMPLETE      "Extraction complete."

#endif
