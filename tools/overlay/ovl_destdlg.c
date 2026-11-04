/* ovl_destdlg.c — the destination dialog with a New
 * Folder button on every System, looking like System 7.0.1's and Mac OS
 * 9.2's own Save dialogs (DLOG/DITL 140 and 141, mac/macextract_destdlg.r).
 * Standard File before System 7 has no New Folder at all: neither 3.0's nor
 * 6.0.8's PACK 3 calls DirCreate.
 *
 * Shell code in an image, so that none of it is resident while the engine
 * extracts: run from the bundle, which the eager lifetime keeps whole and
 * locked until after this dialog, and given back with it (as the sniffer's
 * image is; DECISIONS.md 2026-10-21, *the probes that left with the bundle*).
 * Standard File calls the hook, the filter and the user item back here, all
 * before SFPPutFile returns. What an image may use: inline Toolbox traps
 * only (no glue links), nothing resident by name, no .bss (S, below, is
 * initialised so that it lands in .data).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "overlay.h"
#include <Dialogs.h>
#include <StandardFile.h>
#include <Resources.h>
#include <Files.h>
#include <Icons.h>
#include <LowMem.h>
#include "../../mac/macextract_strings.h"

/* Everything this image keeps between calls, initialised so it is .data.
 * The bundle is read again between archives the Finder hands over
 * (ovl_reload), which starts it afresh: the icon is read again then. */
static struct {
    short       inited;         /* 1: always, so the struct is .data */
    short       haveSICN;       /* sicn holds a 16x16 bitmap to copy */
    CIconHandle cicn;           /* Mac OS 9's folder, disposed after the dialog */
    unsigned char sicn[32];
    Boolean     drawn;          /* item 10 has its drawing routine */
    short       step;           /* 0 idle; 1..len typing; then 103; then 101 */
    long        dir;
    unsigned char name[32];
} S = { 1 };

/* QuickDraw's gray, which an image cannot reach as qd.gray. */
static const Pattern kGray = { { 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55 } };

/* Gestalt, guarded: there is no Gestalt trap on a 64K ROM or before System
 * 6.0.4. The inline puts the selector in D0 and the response in A0, stored
 * through A1; the result in D0. Source: Universal Interfaces 3.4,
 * Gestalt.h: `#pragma parameter __D0 Gestalt(__D0, __A1)`,
 * TWOWORDINLINE(0xA1AD, 0x2288); Multiverse declares it as glue, which an
 * image cannot link. The same guard as ZoneProbe's. */
static Boolean GestaltOK(long selector, long *resp)
{
    *resp = 0;
    if (*(const short *)0x028EL <= 0) return false;          /* ROM85 */
    if (GetOSTrapAddress(0xA1AD) == GetToolTrapAddress(_Unimplemented))
        return false;
    {
        register long d0 __asm__("d0") = selector;
        register long *a1 __asm__("a1") = resp;
        __asm__ volatile (".short 0xA1AD\n\t.short 0x2288"
                          : "+r" (d0), "+r" (a1)
                          :
                          : "d1", "d2", "a0", "cc", "memory");
        return (short)d0 == 0;
    }
}

/* The folder on the New button, chosen as Apple's own button chooses on the
 * two Systems that have one (read out of each System and Finder file, and
 * matched pixel for pixel on screen):
 *   cicn -6046, in Mac OS 9.2's System file and not in 7.0.1's, 6.0.8's or
 *     3.0's: Mac OS 9's button draws it. Needs Color QuickDraw ('qd  ' >=
 *     0x100); System 7 on a Mac Plus has neither;
 *   else ics# -3999, its black-and-white bits copied: System 7.0.1's
 *     button (which answers no Gestalt('icon'), measured);
 *   else the Finder's SICN 128, first icon, copied: Systems 3.0 and 6.0.8
 *     have no button to copy and no small icon in the System file.
 * Read at launch, while the startup disk, which holds the Finder, is in. */
static void LoadFolderIcon(void)
{
    long r;
    short cur, ref;
    Handle h;
    if (S.cicn || S.haveSICN) return;
    if (GestaltOK('qd  ', &r) && r >= 0x100
            && (S.cicn = GetCIcon(-6046)) != NULL)
        return;
    h = GetResource('ics#', -3999);
    if (h && GetHandleSize(h) >= 32) {
        BlockMoveData(*h, S.sicn, 32);
        S.haveSICN = 1;
        return;
    }
    if (*(const short *)0x028EL <= 0) return;   /* ROM85: no OpenRFPerm */
    cur = CurResFile();
    ref = OpenRFPerm(LMGetFinderName(), LMGetBootDrive(), fsRdPerm);
    if (ref == -1) return;
    h = Get1Resource('SICN', 128);
    if (h && GetHandleSize(h) >= 32) {
        BlockMoveData(*h, S.sicn, 32);
        S.haveSICN = 1;
    }
    /* Never close a file this application was already using: with another
     * shell than the Finder, FinderName can name this application. */
    if (ref != LMGetSysMap() && ref != LMGetCurApRefNum())
        CloseResFile(ref);
    UseResFile(cur);
}

/* Item 10: New's word and folder, and the divider below it, drawn once per
 * repaint, as Apple's button is drawn rather than titled. Every position
 * is measured off Apple's own dialogs. Not drawn from the hook: Mac OS 9
 * smooths text, and smoothed text drawn over itself pass after pass lost
 * its grey edges. */
static void DrawNewButton(DialogPtr d)
{
    GrafPtr save;
    Rect r;
    /* The word at a fixed pen, not centred. Apple's ink starts 14 px in on
     * System 7.0.1 and 15 on Mac OS 9.2, and both fonts put ink one pixel
     * after the pen, so the pen differs by one, told apart by the icon.
     * Mac OS 9 smooths against the port's background colour, not the
     * pixels under the text: it gets the button face, grey 221. */
    RGBColor face = { 0xDDDD, 0xDDDD, 0xDDDD }, was;
    GetPort(&save);
    SetPort((GrafPtr)d);
    if (S.cicn) {
        GetBackColor(&was);
        RGBBackColor(&face);
    }
    MoveTo(S.cicn ? 266 : 265, 102);
    DrawString("\p" S_NF_NEW);
    if (S.cicn) {
        RGBBackColor(&was);
        SetRect(&r, 298, 90, 314, 106);
        PlotCIcon(&r, S.cicn);
    } else if (S.haveSICN) {
        BitMap bm;
        bm.baseAddr = (Ptr)S.sicn;
        bm.rowBytes = 2;
        SetRect(&bm.bounds, 0, 0, 16, 16);
        SetRect(&r, 304, 88, 320, 104);
        CopyBits(&bm, &((GrafPtr)d)->portBits, &bm.bounds, &r, srcOr, NULL);
    }
    /* System 7.0.1's divider: one row, every other pixel. */
    PenPat(&kGray);
    MoveTo(251, 119);
    LineTo(333, 119);
    PenNormal();
    SetPort(save);
}

static pascal void NewButtonItem(DialogPtr d, short item)
{
    (void)item;
    DrawNewButton(d);
}

/* Create's ring where the Dialog Manager draws none (before System 7):
 * three pixels wide, four outside the button, corners of 16 — the ring
 * System 7.0.1 draws itself, compared on screen pixel for pixel. */
static pascal void RingItem(DialogPtr d, short item)
{
    short t;
    Handle h;
    Rect r;
    (void)item;
    GetDialogItem(d, 1, &t, &h, &r);
    InsetRect(&r, -4, -4);
    PenSize(3, 3);
    FrameRoundRect(&r, 16, 16);
    PenNormal();
}

/* The New Folder window, System 7's own layout (DITL 141). */
static int AskFolderName(Str255 name)
{
    DialogPtr d;
    short hit, type;
    Handle h;
    Rect r;
    d = GetNewDialog(141, NULL, (WindowPtr)-1);
    if (!d) return 0;
    /* Create is the default: from System 7 on, the Dialog Manager is told
     * so and draws the System's own ring around it. */
    {   long v;
        if (GestaltOK('sysv', &v) && v >= 0x0700) SetDialogDefaultItem(d, 1);
        else
        {   GetDialogItem(d, 5, &type, &h, &r);
            SetDialogItem(d, 5, type, (Handle)NewUserItemUPP(RingItem), &r); } }
    SelectDialogItemText(d, 3, 0, 32767);
    do ModalDialog(NULL, &hit); while (hit != 1 && hit != 2);
    GetDialogItem(d, 3, &type, &h, &r);
    GetDialogItemText(h, name);
    DisposeDialog(d);
    return hit == 1 && name[0] > 0;
}

/* Creating the folder, then moving Standard File into it, on every System
 * in the same order, through pseudo-items Standard File has had since
 * System 3.0 (its PACK 3 and 6.0.8's, disassembled):
 *   101, then 4096 + each character, then 103: reread the list, which now
 *   shows the folder; type-select it; open the selection. This moves 3.0
 *   and 6.0.8, and System 3.0's 101 rereads from its own copy of the
 *   directory, never from CurDirStore;
 *   then CurDirStore = the folder and 101 again: what moves Mac OS 9.2,
 *   whose Save dialog does not type-select from a hook and ignores a 103
 *   with nothing selected. A no-op on 3.0 and 6.0.8.
 * Neither 3.0's nor 6.0.8's 103 checks that a row is selected, so it is
 * sent only once the folder is known to be in the list. */
static pascal short DestHook(short item, DialogPtr dlg)
{
    Str255 name;
    HParamBlockRec pb;
    if (!S.drawn) {
        short t;
        Handle h;
        Rect r;
        GrafPtr save;
        GetDialogItem(dlg, 10, &t, &h, &r);
        SetDialogItem(dlg, 10, t, (Handle)NewUserItemUPP(NewButtonItem), &r);
        GetPort(&save);
        SetPort((GrafPtr)dlg);
        InvalRect(&r);
        SetPort(save);
        S.drawn = true;
    }
    if (S.step) {
        short n = S.step++;
        if (n <= S.name[0]) return 0x1000 + S.name[n];
        if (n == S.name[0] + 1) return sfHookOpenFolder;
        S.step = 0;
        LMSetCurDirStore(S.dir);
        return sfHookRebuildList;
    }
    if (item != 9 || !AskFolderName(name)) return item;
    if (name[0] > 31) name[0] = 31;
    /* DirCreate; HFileParam.ioDirID carries the parent in and the new
     * directory out. The resident MyDirCreate, which an image cannot name. */
    pb.fileParam.ioCompletion = NULL;
    pb.fileParam.ioNamePtr = name;
    pb.fileParam.ioVRefNum = -LMGetSFSaveDisk();
    pb.fileParam.ioDirID = LMGetCurDirStore();
    if (PBDirCreateSync(&pb) != noErr) {
        SysBeep(1);             /* a name already taken only beeps */
        return item;
    }
    S.dir = pb.fileParam.ioDirID;
    BlockMoveData(name, S.name, name[0] + 1);
    S.step = 1;
    return sfHookRebuildList;
}

/* A press on New is tracked here so the word and folder are drawn again
 * after it: Mac OS 8 and 9 repaint a pressed button outside any update.
 * Cmd-N presses it too. */
static pascal Boolean DestFilter(DialogPtr d, EventRecord *e, short *item)
{
    if (e->what == mouseDown) {
        short t;
        Handle h;
        Rect r;
        Point p = e->where;
        GrafPtr save;
        GetPort(&save);
        SetPort((GrafPtr)d);
        GlobalToLocal(&p);
        GetDialogItem(d, 9, &t, &h, &r);
        if (PtInRect(p, &r)) {
            short part = TrackControl((ControlHandle)h, p, NULL);
            DrawNewButton(d);
            SetPort(save);
            if (part) {
                *item = 9;
                return true;
            }
            e->what = nullEvent;
            return false;
        }
        SetPort(save);
    }
    if (e->what == keyDown && (e->modifiers & cmdKey)
            && ((e->message & charCodeMask) | 0x20) == 'n') {
        *item = 9;
        return true;
    }
    return false;
}

/* The prompt is the layout's item 11: Standard File writes this call's
 * into item 3, parked off-screen. */
static int32_t Ask(OvlDestArgs *a)
{
    SFReply dest;
    Point where;
    where.v = a->v;
    where.h = a->h;
    LoadFolderIcon();           /* a no-op unless a reload started S afresh */
    S.drawn = false;
    S.step = 0;
    SFPPutFile(where, "\p", "\p" S_SF_DEST_NAME, NewDlgHookUPP(DestHook),
               &dest, 140, NewModalFilterUPP(DestFilter));
    if (S.cicn) {               /* heap the engine's budget would lose */
        DisposeCIcon(S.cicn);
        S.cicn = NULL;
    }
    S.haveSICN = 0;
    if (!dest.good) return 0;
    a->vol = dest.vRefNum;
    return 1;
}

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)host;
    (void)b;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_DEST_LOADICON:
        LoadFolderIcon();
        return 0;
    case OVL_DEST_ASK:
        return Ask((OvlDestArgs *)a);
    default:
        return -1;
    }
}
