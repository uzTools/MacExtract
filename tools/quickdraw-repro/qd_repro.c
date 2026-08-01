/* qd_repro.c — does QuickDraw really bomb after File Manager activity?
 *
 * WHY THIS EXISTS
 * ---------------
 * unclassic's BLOCKERS.md carried this, filed under "real test-harness lessons
 * (not app bugs)":
 *
 *     QuickDraw drawing (NewWindow/EraseRect) bombs "out of memory" when
 *     called after any File Manager activity, despite megabytes free — so the
 *     result grid is written by poking qd.screenBits directly.
 *
 * That claim was never reduced to a reproduction. It arrived in commit
 * 22e806b, whose headline root cause ("Retro68's HOpen glue is broken") was
 * later WITHDRAWN as confounded, and it matters far beyond the test harness:
 * the shipped interactive application's whole path is SFGetFile (File
 * Manager) -> a progress dialog (QuickDraw) -> a result alert (QuickDraw). If
 * the claim were true as stated, the interactive build would be broken.
 *
 * So: this program runs QuickDraw before and after File Manager work, on the
 * same System 6.0.8 / Mac Plus / Mini vMac setup, and says what happens.
 *
 * HOW IT REPORTS
 * --------------
 * Every line of its log is drawn by poking the 1bpp framebuffer through a 5x7
 * font — no QuickDraw, no Toolbox, no allocation — because the thing under
 * test cannot also be the thing that reports the result. The top eight scan
 * lines carry one marker square per completed probe, where System 6's system
 * error dialog cannot cover them: if the machine bombs at probe N, the marker
 * bar still says N.
 *
 * QuickDraw is confined to y >= 210 so that whatever it draws (or fails to
 * draw) cannot overwrite the log above it.
 *
 * Build variants (see CMakeLists.txt / run.py):
 *   default            SetApplLimit + MaxApplZone + 12x MoreMasters, as the
 *                      real application does
 *   QR_NO_MAXAPPLZONE  skip MaxApplZone (and MoreMasters — no zone to grow)
 *   QR_NO_MOREMASTERS  keep MaxApplZone, skip MoreMasters: master-pointer
 *                      heap fragmentation is the classic explanation for a
 *                      QuickDraw allocation failing with megabytes free
 *
 * License: LGPL-2.1-or-later, like the rest of unclassic.
 */

#include <Devices.h>
#include <Dialogs.h>
#include <Events.h>
#include <Files.h>
#include <Fonts.h>
#include <Memory.h>
#include <Menus.h>
#include <OSUtils.h>
#include <Quickdraw.h>
#include <TextEdit.h>
#include <Windows.h>

#define kStackBump  (24L * 1024)     /* matches mac/unclassic_mac.c */
#define kTestFile   "\pQDReproTest"
#define kChunk      2048L
#define kDataBytes  (64L * 1024)     /* data fork written, then read back  */
#define kRsrcBytes  (8L * 1024)      /* resource fork, same file           */
#define kBigPtr     (200L * 1024)    /* stands in for the archive buffer   */
#define kMixRounds  8
#define fsRtDirID   2L

/* ------------------------------------------------------------------ */
/* Framebuffer text: the reporting channel, independent of QuickDraw   */
/* ------------------------------------------------------------------ */

/* 5x7, columns, bit 0 = top row. ASCII 0x20..0x5A — enough for the log. */
static const unsigned char kFont[59][5] = {
    {0x00,0x00,0x00,0x00,0x00}, {0x00,0x00,0x5F,0x00,0x00},  /*   ! */
    {0x00,0x07,0x00,0x07,0x00}, {0x14,0x7F,0x14,0x7F,0x14},  /* " # */
    {0x24,0x2A,0x7F,0x2A,0x12}, {0x23,0x13,0x08,0x64,0x62},  /* $ % */
    {0x36,0x49,0x55,0x22,0x50}, {0x00,0x05,0x03,0x00,0x00},  /* & ' */
    {0x00,0x1C,0x22,0x41,0x00}, {0x00,0x41,0x22,0x1C,0x00},  /* ( ) */
    {0x14,0x08,0x3E,0x08,0x14}, {0x08,0x08,0x3E,0x08,0x08},  /* * + */
    {0x00,0x50,0x30,0x00,0x00}, {0x08,0x08,0x08,0x08,0x08},  /* , - */
    {0x00,0x60,0x60,0x00,0x00}, {0x20,0x10,0x08,0x04,0x02},  /* . / */
    {0x3E,0x51,0x49,0x45,0x3E}, {0x00,0x42,0x7F,0x40,0x00},  /* 0 1 */
    {0x42,0x61,0x51,0x49,0x46}, {0x21,0x41,0x45,0x4B,0x31},  /* 2 3 */
    {0x18,0x14,0x12,0x7F,0x10}, {0x27,0x45,0x45,0x45,0x39},  /* 4 5 */
    {0x3C,0x4A,0x49,0x49,0x30}, {0x01,0x71,0x09,0x05,0x03},  /* 6 7 */
    {0x36,0x49,0x49,0x49,0x36}, {0x06,0x49,0x49,0x29,0x1E},  /* 8 9 */
    {0x00,0x36,0x36,0x00,0x00}, {0x00,0x56,0x36,0x00,0x00},  /* : ; */
    {0x08,0x14,0x22,0x41,0x00}, {0x14,0x14,0x14,0x14,0x14},  /* < = */
    {0x00,0x41,0x22,0x14,0x08}, {0x02,0x01,0x51,0x09,0x06},  /* > ? */
    {0x32,0x49,0x79,0x41,0x3E}, {0x7E,0x11,0x11,0x11,0x7E},  /* @ A */
    {0x7F,0x49,0x49,0x49,0x36}, {0x3E,0x41,0x41,0x41,0x22},  /* B C */
    {0x7F,0x41,0x41,0x22,0x1C}, {0x7F,0x49,0x49,0x49,0x41},  /* D E */
    {0x7F,0x09,0x09,0x09,0x01}, {0x3E,0x41,0x49,0x49,0x7A},  /* F G */
    {0x7F,0x08,0x08,0x08,0x7F}, {0x00,0x41,0x7F,0x41,0x00},  /* H I */
    {0x20,0x40,0x41,0x3F,0x01}, {0x7F,0x08,0x14,0x22,0x41},  /* J K */
    {0x7F,0x40,0x40,0x40,0x40}, {0x7F,0x02,0x0C,0x02,0x7F},  /* L M */
    {0x7F,0x04,0x08,0x10,0x7F}, {0x3E,0x41,0x41,0x41,0x3E},  /* N O */
    {0x7F,0x09,0x09,0x09,0x06}, {0x3E,0x41,0x51,0x21,0x5E},  /* P Q */
    {0x7F,0x09,0x19,0x29,0x46}, {0x46,0x49,0x49,0x49,0x31},  /* R S */
    {0x01,0x01,0x7F,0x01,0x01}, {0x3F,0x40,0x40,0x40,0x3F},  /* T U */
    {0x1F,0x20,0x40,0x20,0x1F}, {0x3F,0x40,0x38,0x40,0x3F},  /* V W */
    {0x63,0x14,0x08,0x14,0x63}, {0x07,0x08,0x70,0x08,0x07},  /* X Y */
    {0x61,0x51,0x49,0x45,0x43}                               /* Z   */
};

#define FB_SCALE   2
#define FB_CELL_W  (6 * FB_SCALE)      /* 5 px glyph + 1 px gap */
#define FB_CELL_H  (8 * FB_SCALE)      /* 7 px glyph + 1 px gap */
#define FB_LOG_Y0  12                  /* below the marker bar */
#define FB_QD_TOP  210                 /* QuickDraw may not draw above this */

static Ptr  gFB;             /* framebuffer base                    */
static long gRB;             /* bytes per row                       */
static int  gRow;            /* next log line                       */
static int  gStep;           /* next marker square                  */

static void fb_rect(int x0, int y0, int x1, int y1, int black)
{
    int x, y;
    for (y = y0; y < y1; y++) {
        unsigned char *row = (unsigned char *)gFB + (long)y * gRB;
        for (x = x0; x < x1; x++) {
            unsigned char m = (unsigned char)(0x80 >> (x & 7));
            if (black) row[x >> 3] |= m;
            else       row[x >> 3] &= (unsigned char)~m;
        }
    }
}

static void fb_char(int x, int y, char c)
{
    int col, bit, sx, sy;
    const unsigned char *g;
    if (c < 0x20 || c > 0x5A) c = '?';
    g = kFont[c - 0x20];
    for (col = 0; col < 5; col++)
        for (bit = 0; bit < 7; bit++)
            if (g[col] & (1 << bit))
                for (sy = 0; sy < FB_SCALE; sy++)
                    for (sx = 0; sx < FB_SCALE; sx++)
                        fb_rect(x + col * FB_SCALE + sx,
                                y + bit * FB_SCALE + sy,
                                x + col * FB_SCALE + sx + 1,
                                y + bit * FB_SCALE + sy + 1, 1);
}

/* One log line. Deliberately not scrollable: the log is short by design and a
 * fixed line number makes a screenshot comparable between variants. */
static void fb_line(const char *s)
{
    int x = 2, y = FB_LOG_Y0 + gRow * FB_CELL_H;
    if (y + FB_CELL_H > FB_QD_TOP) return;      /* never intrude on the band */
    while (*s && x + FB_CELL_W < 512) {
        fb_char(x, y, *s++);
        x += FB_CELL_W;
    }
    gRow++;
}

/* One marker square, in the top 8 scan lines. System 6's system error dialog
 * is centred and cannot reach them, so the marker bar survives a bomb and
 * says which probe was running when the machine died. */
static void fb_mark(void)
{
    int x = 4 + gStep * 16;
    if (x + 12 < 512) fb_rect(x, 1, x + 12, 9, 1);
    gStep++;
}

/* ---- string building (no libc in this environment worth the trouble) ---- */

static void s_str(char *dst, const char *src)
{
    while (*dst) dst++;
    while (*src) *dst++ = *src++;
    *dst = 0;
}

static void s_num(char *dst, long v)
{
    char tmp[16];
    int n = 0;
    while (*dst) dst++;
    if (v < 0) { *dst++ = '-'; v = -v; }
    if (v == 0) tmp[n++] = '0';
    while (v > 0) { tmp[n++] = (char)('0' + (v % 10)); v /= 10; }
    while (n > 0) *dst++ = tmp[--n];
    *dst = 0;
}

/* ------------------------------------------------------------------ */
/* File Manager, driven exactly as the application drives it            */
/* ------------------------------------------------------------------ */
/* Explicit, fully-zeroed HFS param blocks — the shape mac/unclassic_mac.c
 * settled on. Using the same calls matters: the claim is about what the File
 * Manager leaves behind, so a different route to the disk would test a
 * different thing. */
static OSErr MyOpenFork(short vol, long dir, ConstStr255Param name,
                        SignedByte perm, int rsrc, short *refOut)
{
    HParamBlockRec pb;
    long z;
    OSErr err;
    *refOut = 0;
    for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
    pb.ioParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioVRefNum = vol;
    pb.ioParam.ioPermssn = perm;
    pb.fileParam.ioDirID = dir;
    err = rsrc ? PBHOpenRFSync(&pb) : PBHOpenSync(&pb);
    *refOut = pb.ioParam.ioRefNum;
    return err;
}

static OSErr MyHCreate(short vol, long dir, ConstStr255Param name)
{
    HParamBlockRec pb;
    long z;
    for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
    pb.ioParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = dir;
    return PBHCreateSync(&pb);
}

static OSErr MyHDelete(short vol, long dir, ConstStr255Param name)
{
    HParamBlockRec pb;
    long z;
    for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
    pb.ioParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = dir;
    return PBHDeleteSync(&pb);
}

static char gBuf[kChunk];

/* Create a two-fork file, write both forks, read the data fork back, walk the
 * volume's root catalogue, delete the file. That is the whole shape of what
 * the application does to a volume between putting up its progress dialog and
 * putting up its result alert. Returns the first error, or noErr. */
static OSErr FMWork(void)
{
    short ref;
    OSErr err;
    long n, left;

    MyHDelete(0, 0, kTestFile);                  /* leftovers from a rerun */
    err = MyHCreate(0, 0, kTestFile);
    if (err != noErr) return err;

    err = MyOpenFork(0, 0, kTestFile, fsWrPerm, 0, &ref);
    if (err != noErr) return err;
    for (left = kDataBytes; left > 0; left -= kChunk) {
        n = kChunk;
        err = FSWrite(ref, &n, gBuf);
        if (err != noErr) break;
    }
    FSClose(ref);
    if (err != noErr) return err;

    err = MyOpenFork(0, 0, kTestFile, fsWrPerm, 1, &ref);
    if (err != noErr) return err;
    for (left = kRsrcBytes; left > 0; left -= kChunk) {
        n = kChunk;
        err = FSWrite(ref, &n, gBuf);
        if (err != noErr) break;
    }
    FSClose(ref);
    if (err != noErr) return err;

    err = MyOpenFork(0, 0, kTestFile, fsRdPerm, 0, &ref);
    if (err != noErr) return err;
    for (left = kDataBytes; left > 0; left -= kChunk) {
        n = kChunk;
        err = FSRead(ref, &n, gBuf);
        if (err != noErr) break;
    }
    FSClose(ref);
    if (err != noErr) return err;

    {   /* the catalogue walk SFGetFile does, one level */
        CInfoPBRec cpb;
        Str63 nm;
        short idx;
        long z;
        for (idx = 1; idx < 64; idx++) {
            for (z = 0; z < (long)sizeof cpb; z++) ((char *)&cpb)[z] = 0;
            cpb.hFileInfo.ioNamePtr = nm;
            cpb.hFileInfo.ioVRefNum = 0;
            cpb.hFileInfo.ioDirID = fsRtDirID;
            cpb.hFileInfo.ioFDirIndex = idx;
            if (PBGetCatInfoSync(&cpb) != noErr) break;
        }
    }

    FlushVol(NULL, 0);
    return MyHDelete(0, 0, kTestFile);
}

/* ------------------------------------------------------------------ */
/* The QuickDraw probe                                                 */
/* ------------------------------------------------------------------ */
/* NewWindow + SetPort + EraseRect + DrawString + DisposeWindow, i.e. exactly
 * the sequence BLOCKERS.md says bombs. Returns 1 if the window came back
 * non-NULL; *memErr gets MemError() sampled immediately after NewWindow,
 * which is where an "out of memory" would show up as -108. */
static int QDProbe(const unsigned char *label, short *memErr)
{
    WindowPtr win;
    GrafPtr save;
    Rect r;

    /* SetRect takes left, top, right, bottom — and NewWindow's boundsRect is
     * the CONTENT rect, so documentProc's title bar lands just above
     * FB_QD_TOP and nothing QuickDraw draws can reach the log. */
    SetRect(&r, 8, FB_QD_TOP + 20, 500, 330);
    win = NewWindow(NULL, &r, label, true, documentProc, (WindowPtr)-1L,
                    false, 0);
    *memErr = MemError();
    if (win == NULL) return 0;

    GetPort(&save);
    SetPort(win);
    EraseRect(&win->portRect);
    TextFont(4);                                  /* Monaco, on every System 6 */
    TextSize(9);
    MoveTo(8, 20);
    DrawString(label);
    MoveTo(8, 34);
    DrawString("\pQuickDraw drew this. If you can read it, it worked.");
    SetPort(save);
    DisposeWindow(win);
    return 1;
}

/* Draw straight into the Window Manager port — the other half of the claim
 * ("EraseRect on the WMgr port"). Confined to the QuickDraw band. */
static short WMgrProbe(void)
{
    GrafPtr wmp, save;
    Rect r;
    GetPort(&save);
    GetWMgrPort(&wmp);
    SetPort(wmp);
    SetRect(&r, 8, FB_QD_TOP + 2, 500, FB_QD_TOP + 16);
    EraseRect(&r);
    FrameRect(&r);
    SetPort(save);
    return MemError();
}

static void Idle(void)
{
    for (;;) SystemTask();
}

int main(void)
{
    char line[128];
    short memErr;
    long freeBefore;
    int i, ok;
    OSErr err;
    WindowPtr win;
    DialogPtr dlg;
    Ptr big;

    /* Startup, in the three variants the claim implicates. MaxApplZone grows
     * the heap over the stack's slack; MoreMasters pre-allocates master
     * pointer blocks so the Memory Manager never has to carve one out of a
     * fragmented heap later — the classic explanation for an allocation
     * failing with megabytes free, and the reason it is a build variant here
     * rather than an assumption. */
#ifndef QR_NO_MAXAPPLZONE
    SetApplLimit((Ptr)((long)LMGetApplLimit() - kStackBump));
    MaxApplZone();
#ifndef QR_NO_MOREMASTERS
    for (i = 0; i < 12; i++) MoreMasters();
#endif
#endif

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();
    FlushEvents(everyEvent, 0);
    HideCursor();     /* or the cursor's saved background stamps over the log */

    gFB = qd.screenBits.baseAddr;
    gRB = (long)(qd.screenBits.rowBytes & 0x3FFF);
    fb_rect(0, 0, 512, FB_QD_TOP, 0);            /* white page for the log */

    for (i = 0; i < (int)sizeof gBuf; i++) gBuf[i] = (char)i;

    line[0] = 0;
    s_str(line, "QD REPRO  MAZ=");
#ifdef QR_NO_MAXAPPLZONE
    s_str(line, "0 MM=0");
#else
#ifdef QR_NO_MOREMASTERS
    s_str(line, "1 MM=0");
#else
    s_str(line, "1 MM=12");
#endif
#endif
    fb_line(line);
    fb_mark();

    freeBefore = FreeMem();
    line[0] = 0;
    s_str(line, "0 INIT      FREEK=");   s_num(line, freeBefore / 1024);
    s_str(line, " MAXBLKK=");            s_num(line, MaxBlock() / 1024);
    fb_line(line);
    fb_mark();

    /* 1. QuickDraw with no File Manager activity yet — the control. */
    ok = QDProbe("\pProbe 1: before any File Manager call", &memErr);
    line[0] = 0;
    s_str(line, "1 QD-BEFORE W=");  s_num(line, ok);
    s_str(line, " ME=");            s_num(line, memErr);
    s_str(line, " FREEK=");         s_num(line, FreeMem() / 1024);
    fb_line(line);
    fb_mark();

    /* 2. File Manager work: two forks written, one read back, catalogue
     *    walked, file deleted. */
    err = FMWork();
    line[0] = 0;
    s_str(line, "2 FM-WORK   ERR=");  s_num(line, err);
    s_str(line, " FREEK=");           s_num(line, FreeMem() / 1024);
    s_str(line, " MAXBLKK=");         s_num(line, MaxBlock() / 1024);
    fb_line(line);
    fb_mark();

    /* 3. The claim itself: the same QuickDraw sequence, now after the File
     *    Manager has run. */
    ok = QDProbe("\pProbe 3: after File Manager activity", &memErr);
    line[0] = 0;
    s_str(line, "3 QD-AFTER  W=");  s_num(line, ok);
    s_str(line, " ME=");            s_num(line, memErr);
    s_str(line, " FREEK=");         s_num(line, FreeMem() / 1024);
    fb_line(line);
    fb_mark();

    /* 4. Interleaved, because "after any File Manager activity" should get
     *    worse, not better, with repetition. */
    {
        int rounds = 0;
        short worst = 0;
        for (i = 0; i < kMixRounds; i++) {
            if (FMWork() != noErr) break;
            if (!QDProbe("\pProbe 4: interleaved", &memErr)) break;
            if (memErr != noErr) worst = memErr;
            rounds++;
        }
        line[0] = 0;
        s_str(line, "4 MIX       OK=");  s_num(line, rounds);
        s_str(line, "/");                s_num(line, kMixRounds);
        s_str(line, " ME=");             s_num(line, worst);
        fb_line(line);
        fb_mark();
    }

    /* 5. Holding a big non-relocatable block across the whole sequence — the
     *    application holds exactly one of these (the slurped archive) while
     *    its progress dialog is up, and a NewPtr that size is what makes the
     *    heap look "megabytes free" but badly shaped. */
    big = NewPtr(kBigPtr);
    err = (big != NULL) ? FMWork() : noErr;
    ok = QDProbe("\pProbe 5: with a 200K NewPtr held", &memErr);
    line[0] = 0;
    s_str(line, "5 BIGPTR    P=");  s_num(line, big != NULL);
    s_str(line, " ERR=");           s_num(line, err);
    s_str(line, " W=");             s_num(line, ok);
    s_str(line, " ME=");            s_num(line, memErr);
    fb_line(line);
    if (big) DisposePtr(big);
    fb_mark();

    /* 6. The Dialog Manager route, which is what the shipped application
     *    actually uses: GetNewDialog allocates a window record and a DITL
     *    handle, after all of the above. */
    dlg = GetNewDialog(128, NULL, (WindowPtr)-1L);
    memErr = MemError();
    if (dlg) { DrawDialog(dlg); DisposeDialog(dlg); }
    line[0] = 0;
    s_str(line, "6 DIALOG    D=");  s_num(line, dlg != NULL);
    s_str(line, " ME=");            s_num(line, memErr);
    fb_line(line);
    fb_mark();

    /* 7. EraseRect on the Window Manager port, named in the claim. */
    memErr = WMgrProbe();
    line[0] = 0;
    s_str(line, "7 WMGRPORT  ME=");  s_num(line, memErr);
    fb_line(line);
    fb_mark();

    /* 8. Leave a window on screen, so a reader can see QuickDraw output
     *    coexisting with the framebuffer log rather than taking it on trust. */
    {
        Rect r;
        SetRect(&r, 8, FB_QD_TOP + 20, 500, 330);
        win = NewWindow(NULL, &r, "\pProbe 8: still alive", true, documentProc,
                        (WindowPtr)-1L, false, 0);
        memErr = MemError();
        if (win) {
            SetPort(win);
            EraseRect(&win->portRect);
            TextFont(4); TextSize(9);
            MoveTo(8, 20);
            DrawString("\pAll probes finished. QuickDraw is drawing this AFTER");
            MoveTo(8, 32);
            DrawString("\p64 KB of File Manager writes, reads and a catalog walk.");
            MoveTo(8, 50);
            DrawString("\pFREE bytes:");
            {
                Str255 p;
                char t[32];
                int n;
                t[0] = 0;
                s_num(t, FreeMem());
                for (n = 0; t[n]; n++) p[n + 1] = (unsigned char)t[n];
                p[0] = (unsigned char)n;
                MoveTo(110, 50);
                DrawString(p);
            }
        }
    }
    line[0] = 0;
    s_str(line, "8 FINAL-QD  W=");  s_num(line, win != NULL);
    s_str(line, " ME=");            s_num(line, memErr);
    s_str(line, "   DONE");
    fb_line(line);
    fb_mark();

    Idle();
    return 0;
}
