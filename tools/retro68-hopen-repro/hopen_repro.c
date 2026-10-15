/* hopen_repro.c — conformance test for Retro68's hierarchical File Manager
 * glue (HOpen / HOpenRF / HOpenDF) on System 6.
 *
 * WHY THIS EXISTS
 * ---------------
 * macextract spent a long debugging session on a Mac shell that could not open
 * any file on System 6.0.8, and the failure was written up as "Retro68's HOpen
 * glue returns noErr but never writes back the refNum". This program was built
 * to turn that claim into something a maintainer could reproduce.
 *
 * IT DOES NOT REPRODUCE. See RESULTS below: across ten cases, HOpen and a
 * hand-filled PBHOpenSync behave identically, and HOpen always writes the
 * refNum. The original diagnosis was wrong; the real fault was in macextract,
 * not in Retro68. This file is kept as the evidence for that correction and
 * as a regression test for the glue.
 *
 * WHAT IS ACTUALLY WRONG (small, and both in multiversal/custom/glue.c)
 * --------------------------------------------------------------------
 * Corrected 2026-10-13: (1) is not a bug. Technote FL 1041 documents paramErr
 * as how a caller detects a missing _OpenDF and tells it to retry with HOpen;
 * Retro68 issue #53 settled it that way in 2018. (2) is real and worse than
 * written: case 4's junk pointer was outside RAM, and a pointer into RAM is
 * written through (iomisc_repro.c, ISSUE.md).
 *
 * 1. BOTH OpenDF() and HOpenDF() return paramErr (-50) on System 6, because
 *    the _OpenDF trap is System 7 and later and neither falls back. Only
 *    FSOpen() in the same file handles it, with the comment "OpenDF not
 *    implemented, so use regular Open" and a fallback to PBOpenSync.
 *    (Cases 8 and 11.)
 *
 *    Corrected 2026-08-01: this said the fallback was in OpenDF() and only
 *    the hierarchical variant lacked it. It is in FSOpen(); OpenDF() is bare,
 *    exactly like HOpenDF(). Case 11 exists because that was the second wrong
 *    reading of this one source file, and the answer was on the machine.
 *
 * 2. HOpen/HOpenRF/HOpenDF declare an HParamBlockRec as an uninitialised
 *    stack local and set only four fields; ioMisc is left as stack garbage.
 *    For _Open/PBHOpen, ioMisc is an INPUT — a pointer to an optional access
 *    path buffer, or NULL to use the volume buffer (Inside Macintosh: Files).
 *    The non-hierarchical OpenDF()/OpenRF() in the same file do set it to
 *    NULL; the H-variants do not. System 6 tolerates the garbage in practice
 *    (cases 1 and 4 below pass with a deliberately poisoned ioMisc), so this
 *    is a latent inconsistency rather than the cause of any failure seen
 *    here — but it is still an uninitialised input field.
 *
 * RESULTS on System 6.0.8, Mac Plus (68000), Mini vMac 36.04, Retro68
 * 335fa54f6d ("update multiversal"):
 *
 *   1  HOpen   dirty stack   err=0   ref=378  eof=512  got=4     ok
 *   2  HOpen   zero  stack   err=0   ref=378  eof=512  got=4     ok
 *   3  PB      ioMisc=NULL   err=0   ref=378  eof=512  got=4     ok
 *   4  PB      ioMisc=junk   err=0   ref=378  eof=512  got=4     ok
 *   5  HOpen   vref, rd      err=0   ref=378  eof=512  got=4     ok
 *   6  HOpen   vref, wr      err=0   ref=378  eof=512  got=4     ok
 *   7  HOpenRF vref, wr      err=0   ref=378  eof=0    rdErr=-39 ok (no rsrc fork)
 *   8  HOpenDF vref, rd      err=-50                             BUG (1) above
 *   11 OpenDF  (plain)       err=-50 ref=2                       BUG (1) above
 *   9  HOpen   other volume  err=-43                             ok, matches 10
 *   10 PB      other volume  err=-43                             ok, matches 9
 *
 * Cases 9/10 open "System" at the ROOT of the boot volume, where it does not
 * live (it is inside the System Folder), so fnfErr is the correct answer —
 * the point is that the glue and the hand-written param block agree exactly.
 *
 * The four cases 1-4 vary only the stack contents and ioMisc, to test the
 * uninitialised-field theory; 5-8 use a real vRefNum, a real dirID and write
 * permission, as an application actually would; 9-10 cross volumes, which is
 * what macextract does (archive on one disk, output on another); 11 is the
 * non-hierarchical OpenDF, addressing the default volume exactly as 1-4 do,
 * so its paramErr cannot be confused with a missing file.
 *
 * Build and run instructions: README.md in this directory.
 */

#include <Quickdraw.h>
#include <Windows.h>
#include <Fonts.h>
#include <Events.h>
#include <Files.h>
#include <Memory.h>
#include <TextEdit.h>
#include <Dialogs.h>

/* The repro creates its own test file next to the application (default volume,
 * i.e. vRefNum 0 / dirID 0) so it depends on nothing already on the disk and
 * knows exactly what a correct open should report. */
#define TESTFILE  "\pHOpenTest"
#define TESTSIZE  512L
#define TESTBYTE  0xA5
#define fsRtDirID 2L

static short gRow;                  /* next text row to draw at */
static long  gSink;                 /* keeps DirtyStack from being optimised out */

/* ---- tiny screen printer: QuickDraw text into the Window Manager port ---- */
static void PrintLine(const unsigned char *s)
{
    MoveTo(8, 20 + gRow * 12);
    DrawString(s);
    gRow++;
}

static void AppendNum(unsigned char *dst, long v)
{
    unsigned char tmp[16];
    int n = 0, neg = 0;
    if (v < 0) { neg = 1; v = -v; }
    if (v == 0) tmp[n++] = '0';
    while (v > 0) { tmp[n++] = (unsigned char)('0' + (v % 10)); v /= 10; }
    if (neg) tmp[n++] = '-';
    while (n > 0) dst[++dst[0]] = tmp[--n];
}

static void AppendStr(unsigned char *dst, const char *s)
{
    while (*s) dst[++dst[0]] = (unsigned char)*s++;
}

/* Report one case: label, OSErr, refNum, then what the refNum is actually
 * good for — GetEOF and a 4-byte FSRead. A refNum that "opened fine" but
 * reports eof=0 and reads nothing is the bug. */
static void Report(const char *label, OSErr err, short ref)
{
    unsigned char line[256];
    long eof = -1, count = 4;
    char buf[4];
    OSErr e2 = -9999, e3 = -9999;

    if (err == noErr) {
        e2 = GetEOF(ref, &eof);
        e3 = FSRead(ref, &count, buf);
        FSClose(ref);
    }

    line[0] = 0;
    AppendStr(line, label);
    AppendStr(line, "  err=");   AppendNum(line, err);
    AppendStr(line, " ref=");    AppendNum(line, ref);
    AppendStr(line, " eofErr="); AppendNum(line, e2);
    AppendStr(line, " eof=");    AppendNum(line, eof);
    AppendStr(line, " rdErr=");  AppendNum(line, e3);
    AppendStr(line, " got=");    AppendNum(line, count);
    PrintLine(line);
}

/* Write a recognisable non-zero pattern over the stack region that the next
 * call's HParamBlockRec will occupy, then return so it becomes garbage. */
static void DirtyStack(void)
{
    unsigned char junk[512];
    int i;
    for (i = 0; i < (int)sizeof junk; i++)
        junk[i] = 0xA3;
    gSink += junk[0] + junk[(int)sizeof junk - 1];
}

/* Same footprint, zeroed — the "lucky" stack state where HOpen appears fine. */
static void CleanStack(void)
{
    unsigned char zero[512];
    int i;
    for (i = 0; i < (int)sizeof zero; i++)
        zero[i] = 0;
    gSink += zero[0] + zero[(int)sizeof zero - 1];
}

/* Zero a param block, then fill in the fields every case below shares. */
static void SetupPB(HParamBlockRec *pb)
{
    unsigned char *raw = (unsigned char *)pb;
    int i;
    for (i = 0; i < (int)sizeof *pb; i++) raw[i] = 0;
    pb->fileParam.ioVRefNum = 0;
    pb->fileParam.ioDirID   = 0;
    pb->fileParam.ioNamePtr = (StringPtr)TESTFILE;
    pb->ioParam.ioPermssn   = fsRdPerm;
}

/* Create the test file and fill its data fork with TESTSIZE known bytes.
 * Done through explicit, fully-initialised param blocks — the path we trust —
 * so that setup cannot itself be a victim of the bug under test. */
static OSErr MakeTestFile(void)
{
    HParamBlockRec pb;
    ParamBlockRec  io;
    unsigned char *raw;
    static unsigned char buf[TESTSIZE];
    short ref;
    OSErr err;
    int i;

    for (i = 0; i < (int)TESTSIZE; i++) buf[i] = TESTBYTE;

    SetupPB(&pb);
    (void)PBHDeleteSync(&pb);           /* ignore fnfErr on a fresh disk */

    SetupPB(&pb);
    if ((err = PBHCreateSync(&pb)) != noErr && err != dupFNErr) return err;

    SetupPB(&pb);
    pb.ioParam.ioPermssn = fsRdWrPerm;
    pb.ioParam.ioMisc    = NULL;        /* the field the glue forgets */
    if ((err = PBHOpenSync(&pb)) != noErr) return err;
    ref = pb.ioParam.ioRefNum;

    raw = (unsigned char *)&io;
    for (i = 0; i < (int)sizeof io; i++) raw[i] = 0;
    io.ioParam.ioRefNum   = ref;
    io.ioParam.ioBuffer   = (Ptr)buf;
    io.ioParam.ioReqCount = TESTSIZE;
    io.ioParam.ioPosMode  = fsFromStart;
    io.ioParam.ioPosOffset = 0;
    err = PBWriteSync(&io);
    FSClose(ref);
    return err;
}

int main(void)
{
    WindowPtr win;
    Rect r;
    short ref;
    OSErr err;
    HParamBlockRec pb;
    unsigned char *raw;
    int i;

    MaxApplZone();
    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();
    FlushEvents(everyEvent, 0);

    SetRect(&r, 4, 40, 508, 330);
    win = NewWindow(NULL, &r, "\pRetro68 HOpen repro", true, documentProc,
                    (WindowPtr)-1L, false, 0);
    SetPort(win);
    TextFont(4);        /* Monaco — fixed pitch, present on every System 6 */
    TextSize(9);

    PrintLine("\pRetro68 hierarchical File Manager glue vs. raw param blocks");
    PrintLine("\pfile HOpenTest, 512 bytes of 0xA5, next to the app");
    PrintLine("\pcorrect open => err=0 eof=512 got=4");
    gRow++;

    err = MakeTestFile();
    if (err != noErr) {
        unsigned char line[64];
        line[0] = 0;
        AppendStr(line, "setup failed, err=");
        AppendNum(line, err);
        PrintLine(line);
    }

    /* --- case 1: HOpen after the stack was dirtied -------------------- */
    ref = 0x5A5A;                    /* poison: visible if never written */
    DirtyStack();
    err = HOpen(0, 0, TESTFILE, fsRdPerm, &ref);
    Report("1 HOpen  dirty stack:", err, ref);

    /* --- case 2: HOpen after the stack was zeroed --------------------- */
    ref = 0x5A5A;
    CleanStack();
    err = HOpen(0, 0, TESTFILE, fsRdPerm, &ref);
    Report("2 HOpen  zero  stack:", err, ref);

    /* --- case 3: control — explicit param block, ioMisc = NULL -------- */
    SetupPB(&pb);
    pb.ioParam.ioMisc = NULL;
    err = PBHOpenSync(&pb);
    Report("3 PB  ioMisc=NULL  :", err, pb.ioParam.ioRefNum);

    /* --- case 4: same call, ioMisc = junk ----------------------------- */
    SetupPB(&pb);
    pb.ioParam.ioMisc = (Ptr)0xA3A3A3A2L;   /* even: no address error */
    err = PBHOpenSync(&pb);
    Report("4 PB  ioMisc=junk  :", err, pb.ioParam.ioRefNum);

    /* --- cases 5..8: the shape a real application actually uses -------
     * An app gets a vRefNum from SFGetFile/PBHGetVInfo and a dirID from the
     * catalog, and opens for writing — not the 0/0/fsRdPerm above. Re-run
     * with a real volume reference and a real directory ID. */
    {
        short vref = 0;
        OSErr verr;
        Str63 volname;                       /* GetVInfo writes up to 64 bytes */
        HParamBlockRec vpb;
        unsigned char *vraw = (unsigned char *)&vpb;
        unsigned char line[128];

        for (i = 0; i < (int)sizeof vpb; i++) vraw[i] = 0;
        volname[0] = 0;
        vpb.volumeParam.ioNamePtr  = volname;
        vpb.volumeParam.ioVRefNum  = 0;
        vpb.volumeParam.ioVolIndex = 0;      /* 0 = use ioVRefNum: default vol */
        verr = PBHGetVInfoSync(&vpb);
        if (verr == noErr)
            vref = vpb.volumeParam.ioVRefNum;
        (void)verr;
        /* The mounted volumes, including which one is the default, are
         * listed by the enumeration further down (vol[1], vol[2], ...). */
        gRow++;

        ref = 0x5A5A;
        DirtyStack();
        err = HOpen(vref, fsRtDirID, TESTFILE, fsRdPerm, &ref);
        Report("5 HOpen  vref,rd  :", err, ref);

        ref = 0x5A5A;
        DirtyStack();
        err = HOpen(vref, fsRtDirID, TESTFILE, fsWrPerm, &ref);
        Report("6 HOpen  vref,wr  :", err, ref);

        ref = 0x5A5A;
        DirtyStack();
        err = HOpenRF(vref, fsRtDirID, TESTFILE, fsWrPerm, &ref);
        Report("7 HOpenRF vref,wr :", err, ref);

        ref = 0x5A5A;
        DirtyStack();
        err = HOpenDF(vref, fsRtDirID, TESTFILE, fsRdPerm, &ref);
        Report("8 HOpenDF vref,rd :", err, ref);

        /* --- case 11: the NON-hierarchical OpenDF ---------------------
         * Added after the first write-up of case 8 claimed that the plain
         * OpenDF "already has the fallback" and only the H-variant lacks
         * it. It does not: reading glue.c, the fallback is in FSOpen, and
         * OpenDF calls PBOpenDFSync bare, exactly as HOpenDF does. That
         * makes this the control that decides whether the bug is one
         * function or two — and it is not a question to answer by
         * inspection, in a repository that has twice filed a wrong reading
         * of this same file. */
        ref = 0x5A5A;
        DirtyStack();
        err = OpenDF(TESTFILE, 0, &ref);
        Report("11 OpenDF (plain) :", err, ref);

        /* --- cases 9..10: CROSS-VOLUME open ---------------------------
         * The app that hit this opens a file on a volume that is NOT the
         * default one, with a vRefNum found by enumerating mounted volumes
         * (ioVolIndex 1, 2, ...). Find the boot volume that way and open
         * its "System" file, which every System 6 disk has. */
        {
            short bootv = 0;
            int idx;
            for (idx = 1; idx <= 4; idx++) {
                for (i = 0; i < (int)sizeof vpb; i++) vraw[i] = 0;
                volname[0] = 0;
                vpb.volumeParam.ioNamePtr  = volname;
                vpb.volumeParam.ioVRefNum  = 0;
                vpb.volumeParam.ioVolIndex = idx;
                if (PBHGetVInfoSync(&vpb) != noErr) break;
                line[0] = 0;
                AppendStr(line, "  vol[");
                AppendNum(line, idx);
                AppendStr(line, "] vRefNum=");
                AppendNum(line, vpb.volumeParam.ioVRefNum);
                AppendStr(line, " name=");
                for (i = 1; i <= volname[0] && i < 24; i++)
                    line[++line[0]] = volname[i];
                PrintLine(line);
                if (vpb.volumeParam.ioVRefNum != vref && bootv == 0)
                    bootv = vpb.volumeParam.ioVRefNum;
            }

            ref = 0x5A5A;
            DirtyStack();
            err = HOpen(bootv, fsRtDirID, "\pSystem", fsRdPerm, &ref);
            Report("9 HOpen  other vol:", err, ref);

            SetupPB(&pb);
            pb.ioParam.ioVRefNum = bootv;
            pb.fileParam.ioDirID = fsRtDirID;
            pb.ioParam.ioNamePtr = (StringPtr)"\pSystem";
            pb.ioParam.ioMisc    = NULL;
            err = PBHOpenSync(&pb);
            Report("10 PB    other vol:", err, pb.ioParam.ioRefNum);
        }
    }

    gRow++;
    PrintLine("\pDone - click to quit.");

    /* Idle so the result stays on screen; any click quits. */
    for (;;) {
        EventRecord ev;
        SystemTask();
        if (GetNextEvent(mDownMask | keyDownMask, &ev)) break;
    }
    return 0;
}
