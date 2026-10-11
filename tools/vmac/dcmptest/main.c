/*
 * dcmptest — call a StuffIt 2.0 Optimizer module and drive its DATA PATH.
 *
 * The reading: the application locks the 'COMP'/'DCMP' resource handle,
 * dereferences it and jumps to the module's first byte, which is a
 * `bra.s` over a sixteen-byte header ('COMP' or 'DCMP' at +4, the
 * module's own id at +8). The call is Pascal and the callee pops
 * twelve bytes:
 *
 *     pascal void Module(Ptr buffer, long *selector, void *third);
 *
 * `*selector` carries the request AND the answer, and the THIRD
 * argument is overloaded by it: at the setup selectors it points at a
 * two-long record, and at `*selector > 0` it is a ProcPtr a 'COMP'
 * calls to hand its output back. A 'DCMP' never calls it: it writes the
 * file itself. FORMATS.md, *The module ABI*.
 *
 * The run is a ROUND TRIP, and nothing but the document goes in:
 *
 *   1. selector -3, the cheapest request there is — every module
 *      answers it by copying its own name into `buffer` with
 *      _BlockMove and writing 1 back. No file, no callback.
 *   2. the 'COMP' over `Painting`: -1 with a CInfoPBRec, then -4, which
 *      leaves its output in `{system}Optimizers:Paint Temp 0`. That
 *      file is the remnant an optimized archive stores.
 *   3. the 'DCMP' over a fresh `Rebuilt`: -1 with a CInfoPBRec, then
 *      that remnant fed in 512-byte chunks, then -2, where the module
 *      rebuilds the document through the File Manager.
 *
 * So the bytes the 'DCMP' is asked to rebuild from are the ones
 * Aladdin's own 'COMP' produced, and neither half is handed anything
 * this project made up.
 *
 * Two things this learned the hard way, both about reading a file
 * rather than about StuffIt: **one `FSRead` is not a read** — a short
 * count is legal and this volume gives one at a file's first extent —
 * and **`_FlushVol` is not Shut Down**, which is why the probe powers
 * the machine off at the end.
 *
 * The marks along the top say how far it got if the machine bombs.
 *
 * Put it on a volume that has StuffIt Deluxe 2.0.1's Optimizers
 * installed and a `PNTG` document called `Painting` in its root
 * (tools/vmac/sitopt.py --dcmpdata). Built by hand, not by ci.sh —
 * tools/vmac/README.md.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include <Quickdraw.h>
#include <Fonts.h>
#include <Windows.h>
#include <Resources.h>
#include <Memory.h>
#include <Files.h>
#include <TextUtils.h>
#include <Multiverse.h>
#include <Events.h>
#include <string.h>

QDGlobals qd;

/* The module under test. Its 'COMP' leaves its output in
 * `{system}Optimizers:Paint Temp 0` — the name is the module's own
 * STR# 128 — which --dcmpdata copies off the image afterwards. */
#define MODULE_PATH "\pMacintosh:System Folder:Optimizers:MacPaint 1"
#define REBUILT_NAME "\pRebuilt"
#define ORIGINAL_NAME "\pPainting"

/* The third argument, at every selector but a positive one. Read out of
 * the application's own CODE 8: it fills a local pair of longs and
 * passes its address, and the module tests the LOW WORD of the first
 * (zero means "I cannot do this", and it then accepts the file and does
 * nothing at all) and writes its own answers into both. */
typedef struct {
    long flags;
    long size;
} ModRec;

typedef pascal void (*ModuleProc)(Ptr buffer, long *selector, void *third);

/* What a 'COMP' calls at `*selector > 0`, and the only use either half
 * of `MacPaint 1` makes of the third argument there: the helper inside
 * the module pushes room for a long result, then the buffer, then the
 * NEGATED byte count, and discards what comes back. Nothing here needs
 * to do anything with it — the same call hands the bytes to the caller
 * in `buffer`, which is where this probe takes them from. */
static pascal long ioProc(Ptr buffer, long count)
{
    (void)buffer;
    (void)count;
    return 0;
}

static short gLine;

static void mark(short n)
{
    Rect r;
    SetRect(&r, (short)(6 + n * 20), 4, (short)(22 + n * 20), 14);
    PaintRect(&r);
}

/* One line of "label number". Everything this probe has to say is a
 * label and a number, so there is only one output routine. */
static void say(const char *label, long v)
{
    Str255 s, n;
    short i = 0, j;

    while (label[i] != '\0' && i < 200) {
        s[i + 1] = (unsigned char)label[i];
        i++;
    }
    s[0] = (unsigned char)i;
    NumToString(v, n);
    for (j = 1; j <= n[0]; j++) {
        s[0]++;
        s[s[0]] = n[j];
    }
    MoveTo(8, (short)(28 + gLine * 11));
    DrawString(s);
    gLine++;
}

/* The same, with the number shown as the four characters of an OSType —
 * which is how the acceptance test's field is meant to read. */
static void sayType(const char *label, long v)
{
    Str255 s;
    short i = 0;

    while (label[i] != '\0' && i < 200) {
        s[i + 1] = (unsigned char)label[i];
        i++;
    }
    s[0] = (unsigned char)i;
    s[0] += 4;
    s[s[0] - 3] = (unsigned char)((v >> 24) & 0xff);
    s[s[0] - 2] = (unsigned char)((v >> 16) & 0xff);
    s[s[0] - 1] = (unsigned char)((v >> 8) & 0xff);
    s[s[0]] = (unsigned char)(v & 0xff);
    MoveTo(8, (short)(28 + gLine * 11));
    DrawString(s);
    gLine++;
}

static void hang(void)
{
    /* Never return: the Finder repaints the desktop long before a
     * screenshot can be taken (traptest says the same). */
    for (;;) { }
}

/* A CInfoPBRec for one file in one directory, filled the way the
 * application fills it — PBGetCatInfo — and then with the three fields
 * PBGetCatInfo is documented to consume put back. It returns the file
 * number in ioDirID, so a record handed on unchanged would name the
 * wrong directory. */
static OSErr catRecord(CInfoPBRec *cpb, StringPtr name, short vref, long dir)
{
    OSErr err;

    memset(cpb, 0, sizeof *cpb);
    cpb->hFileInfo.ioNamePtr = name;
    cpb->hFileInfo.ioVRefNum = vref;
    cpb->hFileInfo.ioDirID = dir;
    cpb->hFileInfo.ioFDirIndex = 0;
    err = PBGetCatInfoSync(cpb);
    cpb->hFileInfo.ioNamePtr = name;
    cpb->hFileInfo.ioVRefNum = vref;
    cpb->hFileInfo.ioDirID = dir;
    return err;
}

int main(void)
{
    short ref, vref;
    long dir, len, pos, sel;
    Handle dcmp, comp;
    Ptr blob;
    OSErr err;
    Str255 vol, dst, src;
    CInfoPBRec cpb;
    ModRec mr;
    char buf[280];

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    /* The desktop is a grey pattern and DrawString over it is
     * unreadable in a 512x342 screenshot — the first run of this pass
     * photographed eighteen lines nobody could make out. */
    {
        Rect scr = qd.screenBits.bounds;
        PenNormal();
        FillRect(&scr, &qd.white);
    }
    TextFont(4);                                    /* Monaco */
    TextSize(9);
    mark(0);

    /* The five offsets this probe relies on are the five the modules
     * read. Print them out of Retro68's own CInfoPBRec, so the claim
     * that the record IS a CInfoPBRec is checked and not just asserted. */
    say("ioNamePtr at +", (long)((char *)&cpb.hFileInfo.ioNamePtr -
                                 (char *)&cpb));
    say("ioVRefNum at +", (long)((char *)&cpb.hFileInfo.ioVRefNum -
                                 (char *)&cpb));
    say("fdType    at +", (long)((char *)&cpb.hFileInfo.ioFlFndrInfo.fdType -
                                 (char *)&cpb));
    say("ioDirID   at +", (long)((char *)&cpb.hFileInfo.ioDirID -
                                 (char *)&cpb));
    say("ioFlParID at +", (long)((char *)&cpb.hFileInfo.ioFlParID -
                                 (char *)&cpb));

    ref = OpenResFile((ConstStr255Param)MODULE_PATH);
    if (ref == -1) {
        say("no module: OpenResFile failed, err ", (long)ResError());
        hang();
    }
    mark(1);
    UseResFile(ref);

    /* Get1IndResource, exactly as the application does: a module file
     * holds one of each, and its id is the module's number rather
     * than 1. */
    dcmp = Get1IndResource('DCMP', 1);
    comp = Get1IndResource('COMP', 1);
    if (dcmp == NULL || comp == NULL) {
        say("module lacks COMP or DCMP", 0);
        hang();
    }
    HLock(dcmp);
    HLock(comp);
    mark(2);
    say("module id at +8 of the DCMP: ", (long)*(short *)(*dcmp + 8));

    /* ------------------------------------------------------------- *
     * 1. selector -3 — the name, and nothing else.
     * ------------------------------------------------------------- */
    memset(buf, 0, sizeof buf);
    sel = -3L;
    (*(ModuleProc)(*dcmp))((Ptr)buf, &sel, NULL);
    mark(3);
    say("-3 wrote back ", sel);
    if ((unsigned char)buf[0] > 0 && (unsigned char)buf[0] < 64) {
        MoveTo(8, (short)(28 + gLine * 11));
        DrawString((const unsigned char *)buf);
        gLine++;
    } else {
        say("the name came back empty", 0);
        hang();
    }

    /* The volume everything below lives in. The default volume at boot
     * is the boot volume; the root is dirID 2 by definition. */
    vref = 0;
    if (GetVol(vol, &vref) != noErr) {
        say("GetVol failed", 0);
        hang();
    }
    dir = 2L;
    mark(4);

    /* ------------------------------------------------------------- *
     * 2. the COMP, to MAKE the remnant. -1 then -4, and no -2, which is
     *    the call that would delete the temp file this needs.
     * ------------------------------------------------------------- */
    memcpy(src, ORIGINAL_NAME, sizeof ORIGINAL_NAME);
    err = catRecord(&cpb, src, vref, dir);
    if (err != noErr) {
        say("no Painting in the root, err ", (long)err);
        hang();
    }
    sayType("Painting's +32 reads ", cpb.hFileInfo.ioFlFndrInfo.fdType);
    say("Painting data fork ", cpb.hFileInfo.ioFlLgLen);
    mr.flags = 1;                          /* low word non-zero: proceed */
    mr.size = 0;
    sel = -1L;
    (*(ModuleProc)(*comp))((Ptr)&cpb, &sel, &mr);
    say("COMP -1 wrote back ", sel);
    say("  and left flags at ", mr.flags);
    if (sel != 1L) {
        say("the COMP declined the document", 0);
        hang();
    }
    mark(5);
    sel = -4L;
    (*(ModuleProc)(*comp))(NULL, &sel, &mr);
    mark(6);
    say("COMP -4 made a remnant of ", mr.size);

    /* **Take the bytes back through the module, not off the disk.**
     * Opening the temp file gives -49, opWrErr: the 'COMP' holds a
     * write path on it until -2, which is the call that deletes it.
     * And `*selector > 0` on a 'COMP' is the read-out — it reads its
     * own temp file into the caller's buffer and returns the count —
     * so this is how the application gets an optimized fork out, and
     * the probe does not need a second path onto the file at all. */
    len = mr.size;
    blob = NewPtr(len);
    if (blob == NULL || len <= 0) {
        say("NewPtr for the remnant failed, len ", len);
        hang();
    }
    pos = 0;
    while (pos < len) {
        sel = len - pos;
        if (sel > 512L) sel = 512L;
        (*(ModuleProc)(*comp))((Ptr)(blob + pos), &sel, (void *)ioProc);
        if (sel <= 0L) break;
        pos += sel;
    }
    say("remnant read back, bytes ", pos);
    say("  the last call answered ", sel);
    say("its first long says ", *(long *)blob);
    if (pos != len) {
        say("short read - nothing below this would mean anything", 0);
        hang();
    }
    mark(7);

    /* ------------------------------------------------------------- *
     * 3. the DCMP data path: -1, then the remnant, then -2.
     * ------------------------------------------------------------- */
    memcpy(dst, REBUILT_NAME, sizeof REBUILT_NAME);
    HDelete(vref, dir, dst);
    err = HCreate(vref, dir, dst, 'MPNT', 'PNTG');
    if (err != noErr) {
        say("HCreate of Rebuilt failed, err ", (long)err);
        hang();
    }
    err = catRecord(&cpb, dst, vref, dir);
    if (err != noErr) {
        say("PBGetCatInfo on Rebuilt failed, err ", (long)err);
        hang();
    }
    mr.flags = 1;
    mr.size = 0;
    sel = -1L;
    (*(ModuleProc)(*dcmp))((Ptr)&cpb, &sel, &mr);
    mark(8);
    say("DCMP -1 wrote back ", sel);
    if (sel != 1L) {
        say("the DCMP declined the file", 0);
        hang();
    }

    /* Feed it in chunks, the way a caller decoding an entry would. */
    pos = 0;
    while (pos < len) {
        long n = len - pos;
        if (n > 512L) n = 512L;
        sel = n;
        (*(ModuleProc)(*dcmp))((Ptr)(blob + pos), &sel, &mr);
        if (sel != 0L) {
            say("a chunk came back with ", sel);
            break;
        }
        pos += n;
    }
    mark(9);
    say("fed, bytes ", pos);

    sel = -2L;
    (*(ModuleProc)(*dcmp))((Ptr)&cpb, &sel, &mr);
    mark(10);
    say("DCMP -2 wrote back ", sel);

    if (catRecord(&cpb, dst, vref, dir) == noErr) {
        say("Rebuilt data fork ", cpb.hFileInfo.ioFlLgLen);
        say("Rebuilt rsrc fork ", cpb.hFileInfo.ioFlRLgLen);
    }
    DisposePtr(blob);
    mark(11);

    err = FlushVol(NULL, vref);
    say("FlushVol err ", (long)err);

    /* And then SHUT DOWN. `_FlushVol` returned 0 in an earlier run and
     * the rebuilt file's catalog entry still came off the image reading
     * zero length; Shut Down is what the rest of this harness uses and
     * what actually gets a volume onto the image (tools/vmac/README.md).
     * The wait is for the screenshots. */
    {
        unsigned long until = TickCount() + 60UL * 240UL;
        while (TickCount() < until) { }
    }
    mark(12);
    ShutDwnPower();
    hang();
    return 0;
}
