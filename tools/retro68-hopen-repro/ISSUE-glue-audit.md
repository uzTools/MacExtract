# Upstream issue draft: four more fields multiversal's glue leaves unset

**Not filed.** Ready for the maintainer to post on autc04/Retro68, like #320
(`ISSUE.md`); the body below embeds `glue-audit.patch` and `glue_audit.c`
as they were when measured — regenerate it if either changes. Measured
2026-10-15 against multiversal `4c78d24` (master, the commit that fixed
#320); the results table is README.md's, *glue_audit*.

---

**Title:** More File Manager glue reads uninitialised param-block fields: `GetWDInfo`, `SetFInfo`, `HSetFInfo`, and `ioVersNum` in the `HOpen` family

**Body:**

Thanks for the quick fix on #320! I went through the rest of the File Manager glue in `custom/glue.c` against the parameter tables in Inside Macintosh: Files (ch. 2), and four more spots read a field the glue never sets, or overwrite one it needs:

1. **`GetWDInfo`** never sets `ioNamePtr` or `ioWDIndex`. Both are inputs to `PBGetWDInfo`: a non-zero `ioWDIndex` makes it index working directories instead of looking up `wdRefNum`, and the volume name is written through `ioNamePtr` unless it's NIL. With non-zero stack contents, `GetWDInfo` returns `nsvErr` (-35) and garbage outputs for a valid WD; with `ioNamePtr` pointing at a buffer, the File Manager writes 8 bytes into it.
2. **`SetFInfo`** never sets `ioFDirIndex`, and drops the result of `PBGetFInfoSync`, so `if(err)` tests an uninitialised variable (`-Wall` flags it). With `ioFDirIndex = 1` left on the stack, `SetFInfo("B", ...)` returns `noErr` but sets the Finder info **of file A** (index 1), and overwrites the caller's file-name string with `"A"`.
3. **`HSetFInfo`** doesn't restore `ioDirID` after `PBHGetFInfoSync`, which replaces it with the file ID (`HCreate` does restore it, with a comment). So `PBHSetFInfo` gets the file ID as a directory ID and fails with `fnfErr` (-43) on HFS, in the root and in a subfolder, even with a zeroed stack: it doesn't depend on garbage at all.
4. **`HOpen`/`HOpenRF`/`HOpenDF`** never set `ioVersNum`. HFS ignores it, but on an MFS volume the version number is part of the file's identity: with a non-zero byte left there, `HOpen` of an existing file returns `fnfErr`. `FSOpen`, `OpenDF` and `OpenRF` already set it to 0.

Measured with the repro below: Mini vMac Mac Plus, Systems 3.0, 6.0.8 and 7.0.1 (identical results on all three), with an HFS and an MFS test disk. It calls verbatim copies of the `4c78d24` glue with the stack filled first with zeroes (control) and then with a non-zero pattern; building it with `-DGLUE_FIXED` applies the patch below, after which every row matches the control:

| case | stack zero | stack non-zero | non-zero, with the patch (6.0.8) |
|---|---|---|---|
| `GetWDInfo` on a valid WD | `noErr` | `nsvErr`, garbage outputs | `noErr` |
| `SetFInfo("B")`, HFS and MFS | B changed | `noErr`, **A** changed, name now `"A"` | B changed |
| `HSetFInfo`, HFS, root and subfolder | `fnfErr` | (not run) | `noErr` (zeroed stack) |
| `HOpen`, MFS | `noErr` | `fnfErr` | `noErr` |
| `HOpen`, HFS | `noErr` | `noErr` | `noErr` |

The fix, same style as #320:

```diff
--- a/custom/glue.c
+++ b/custom/glue.c
@@ -232,6 +232,7 @@
     pb.fileParam.ioNamePtr = (StringPtr)name;
     pb.ioParam.ioPermssn = perm;
     pb.ioParam.ioMisc = NULL;
+    pb.fileParam.ioFVersNum = 0;
     OSErr err = PBHOpenRFSync(&pb);
     *refp = pb.ioParam.ioRefNum;
     return err;
@@ -245,6 +246,7 @@
     pb.fileParam.ioNamePtr = (StringPtr)name;
     pb.ioParam.ioPermssn = perm;
     pb.ioParam.ioMisc = NULL;
+    pb.fileParam.ioFVersNum = 0;
     OSErr err = PBHOpenSync(&pb);
     *refp = pb.ioParam.ioRefNum;
     return err;
@@ -259,6 +261,7 @@
     pb.fileParam.ioNamePtr = (StringPtr)name;
     pb.ioParam.ioPermssn = perm;
     pb.ioParam.ioMisc = NULL;
+    pb.fileParam.ioFVersNum = 0;
     OSErr err = PBHOpenDFSync(&pb);
     *refp = pb.ioParam.ioRefNum;
     return err;
@@ -414,7 +417,9 @@
 {
     OSErr err;
     WDPBRec pb;
+    pb.ioNamePtr = NULL;
     pb.ioVRefNum = wdRefNum;
+    pb.ioWDIndex = 0;
     err = PBGetWDInfoSync(&pb);
     *vRefNum = pb.ioWDVRefNum;
     *dirID = pb.ioWDDirID;
@@ -444,7 +449,8 @@
     pb.fileParam.ioVRefNum = vRefNum;
     pb.fileParam.ioNamePtr = (StringPtr)fileName;
     pb.fileParam.ioFVersNum = 0;
-    PBGetFInfoSync(&pb);
+    pb.fileParam.ioFDirIndex = 0;
+    err = PBGetFInfoSync(&pb);
     if(err)
         return err;
     pb.fileParam.ioFlFndrInfo = *fndrInfo;
@@ -491,6 +497,8 @@
     if(err)
         return err;
     pb.fileParam.ioFlFndrInfo = *fndrInfo;
+    // reset directory ID, overwritten by PBHGetFInfo
+    pb.fileParam.ioDirID = dirID;
     return PBHSetFInfoSync(&pb);
 }
```

<details><summary>glue_audit.c (400 lines) — needs a blank HFS volume named GlueHFS and an MFS volume named GlueMFS mounted</summary>

```c
/* glue_audit.c — four more param-block fields multiversal's File Manager glue
 * leaves to whatever is on the stack.
 *
 * The G_* functions are VERBATIM copies of custom/glue.c at multiversal
 * 4c78d24 (2026-10-14, the commit that fixed Retro68 #320), renamed so they do
 * not collide with the toolchain's own copies. -DGLUE_FIXED applies
 * glue-audit.patch to them, and nothing else. Each case calls one twice: once
 * after filling the stack with zeroes (control) and once with a non-zero
 * pattern, and prints what changed. Field directions are Inside Macintosh:
 * Files (1992), chapter 2, the parameter-block table of each call.
 *
 * Needs two extra disks: an HFS volume named "GlueHFS" and an MFS volume
 * named "GlueMFS" (README.md).
 */
#include <Quickdraw.h>
#include <Windows.h>
#include <Fonts.h>
#include <Files.h>
#include <Menus.h>
#include <TextEdit.h>
#include <Dialogs.h>
#include <Events.h>
#include <Memory.h>
#include <stdio.h>
#include <string.h>

/* ---- verbatim from multiversal 4c78d24 custom/glue.c -------------------- */

pascal OSErr G_HOpen(INTEGER vref, LONGINT dirid, ConstStringPtr name,
                   SignedByte perm, INTEGER *refp)
{
    HParamBlockRec pb;
    pb.fileParam.ioVRefNum = vref;
    pb.fileParam.ioDirID = dirid;
    pb.fileParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioPermssn = perm;
    pb.ioParam.ioMisc = NULL;
#ifdef GLUE_FIXED
    pb.fileParam.ioFVersNum = 0;
#endif
    OSErr err = PBHOpenSync(&pb);
    *refp = pb.ioParam.ioRefNum;
    return err;
}

pascal OSErr G_GetWDInfo(short wdRefNum, short *vRefNum, long *dirID,
                       long *procID)
{
    OSErr err;
    WDPBRec pb;
#ifdef GLUE_FIXED
    pb.ioNamePtr = NULL;
    pb.ioWDIndex = 0;
#endif
    pb.ioVRefNum = wdRefNum;
    err = PBGetWDInfoSync(&pb);
    *vRefNum = pb.ioWDVRefNum;
    *dirID = pb.ioWDDirID;
    *procID = pb.ioWDProcID;
    return err;
}

pascal OSErr G_SetFInfo(ConstStr255Param fileName, short vRefNum,
                      FInfo *fndrInfo)
{
    ParamBlockRec pb;
    OSErr err;
    pb.fileParam.ioVRefNum = vRefNum;
    pb.fileParam.ioNamePtr = (StringPtr)fileName;
    pb.fileParam.ioFVersNum = 0;
#ifdef GLUE_FIXED
    pb.fileParam.ioFDirIndex = 0;
    err = PBGetFInfoSync(&pb);
#else
    PBGetFInfoSync(&pb);
#endif
    if(err)
        return err;
    pb.fileParam.ioFlFndrInfo = *fndrInfo;
    return PBSetFInfoSync(&pb);
}

pascal OSErr G_HSetFInfo(short vRefNum, long dirID, ConstStr255Param fileName,
                       const FInfo *fndrInfo)
{
    HParamBlockRec pb;
    OSErr err;
    pb.fileParam.ioVRefNum = vRefNum;
    pb.fileParam.ioNamePtr = (StringPtr)fileName;
    pb.fileParam.ioFVersNum = 0; // ???
    pb.fileParam.ioFDirIndex = 0;
    pb.fileParam.ioDirID = dirID;
    err = PBHGetFInfoSync(&pb);
    if(err)
        return err;
    pb.fileParam.ioFlFndrInfo = *fndrInfo;
#ifdef GLUE_FIXED
    pb.fileParam.ioDirID = dirID;
#endif
    return PBHSetFInfoSync(&pb);
}

/* ---- end of the verbatim copy ------------------------------------------- */

static volatile long sink;
static short row;
static char line[96];
static char lines[28][96];

static void DrawAll(void)
{
    short i;
    for (i = 0; i < row; i++) {
        MoveTo(6, 32 + 11 * i);
        DrawText(lines[i], 0, strlen(lines[i]));
    }
}

/* Keep every line: the window is erased once after it is first drawn, and
 * an update has to put them back. */
static void Say(void)
{
    if (row < 28) strcpy(lines[row++], line);
    DrawAll();
}

static void Idle(void)
{
    EventRecord ev;
    for (;;) {
        SystemTask();
        if (GetNextEvent(everyEvent, &ev) && ev.what == updateEvt) {
            BeginUpdate((WindowPtr)ev.message);
            EraseRect(&((WindowPtr)ev.message)->portRect);
            DrawAll();
            EndUpdate((WindowPtr)ev.message);
        }
    }
}

/* Fill the stack the next call will use with one 16-bit pattern, so every
 * field of a param block built there reads as that pattern however the block
 * is aligned: a long field reads (p << 16) | p. */
static __attribute__((noinline)) void Poison(unsigned short p)
{
    unsigned short s[512]; int i;
    for (i = 0; i < 512; i++) s[i] = p;
    sink += s[0] + s[511];
}

static void Zero(void *p, long n) { while (n--) ((char *)p)[n] = 0; }

static OSErr OwnCreate(short vol, long dir, const unsigned char *name,
                       OSType type)
{
    HParamBlockRec pb; OSErr err;
    Zero(&pb, sizeof pb);
    pb.fileParam.ioNamePtr = (StringPtr)name;
    pb.fileParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = dir;
    PBHDeleteSync(&pb);
    err = PBHCreateSync(&pb);
    if (err) return err;
    Zero(&pb, sizeof pb);
    pb.fileParam.ioNamePtr = (StringPtr)name;
    pb.fileParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = dir;
    err = PBHGetFInfoSync(&pb);
    if (err) return err;
    pb.fileParam.ioFlFndrInfo.fdType = type;
    pb.fileParam.ioFlFndrInfo.fdCreator = type;
    pb.fileParam.ioDirID = dir;
    return PBHSetFInfoSync(&pb);
}

static OSType OwnType(short vol, long dir, const unsigned char *name)
{
    HParamBlockRec pb;
    Zero(&pb, sizeof pb);
    pb.fileParam.ioNamePtr = (StringPtr)name;
    pb.fileParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = dir;
    if (PBHGetFInfoSync(&pb)) return '----';
    return pb.fileParam.ioFlFndrInfo.fdType;
}

static void T4(char *o, OSType t)
{
    o[0] = (char)(t >> 24); o[1] = (char)(t >> 16);
    o[2] = (char)(t >> 8);  o[3] = (char)t; o[4] = 0;
}

static short FindVol(const char *want, unsigned short *sig)
{
    HParamBlockRec pb; Str255 nm; short i;
    for (i = 1; i < 20; i++) {
        Zero(&pb, sizeof pb);
        pb.volumeParam.ioNamePtr = nm;
        pb.volumeParam.ioVolIndex = i;
        if (PBHGetVInfoSync(&pb)) return 0;
        if (nm[0] == strlen(want) && !memcmp(nm + 1, want, nm[0])) {
            *sig = pb.volumeParam.ioVSigWord;
            return pb.volumeParam.ioVRefNum;
        }
    }
    return 0;
}

/* A folder "D" at the root, created or found; returns its directory ID. */
static long Folder(short vol, OSErr *e)
{
    HParamBlockRec pb; CInfoPBRec ci;
    Zero(&pb, sizeof pb);
    pb.fileParam.ioNamePtr = "\pD";
    pb.fileParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = 2;
    *e = PBDirCreateSync(&pb);
    if (*e != dupFNErr) return pb.fileParam.ioDirID;
    Zero(&ci, sizeof ci);
    ci.dirInfo.ioNamePtr = "\pD";
    ci.dirInfo.ioVRefNum = vol;
    ci.dirInfo.ioDrDirID = 2;
    *e = PBGetCatInfoSync(&ci);
    return ci.dirInfo.ioDrDirID;
}

/* ---- 1. GetWDInfo: ioNamePtr (out-pointer) and ioWDIndex (input) -------- */
static unsigned char *decoy;           /* 512 bytes at an address (h<<16)|h */
static unsigned short decoyH;

static void Case1(short vol)
{
    WDPBRec pb; OSErr err; short v; long d, p; int i, changed; short wd;

    OSErr e;
    long dir = Folder(vol, &e);
    Zero(&pb, sizeof pb);              /* a working directory to ask about: */
    pb.ioVRefNum = vol;                /* not the root, whose WD is the vRef */
    pb.ioWDDirID = dir;
    pb.ioWDProcID = 'GLUE';
    err = PBOpenWDSync(&pb);
    wd = pb.ioVRefNum;
    sprintf(line, "1 GetWDInfo   OpenWD(D=%ld) err=%d wd=%d  decoy@%08lx",
            dir, err, wd, (long)decoy);
    Say();

    for (i = 0; i < 2; i++) {          /* each field alone, no glue */
        int k;
        for (k = 0; k < 512; k++) decoy[k] = 0x55;
        Zero(&pb, sizeof pb);
        pb.ioVRefNum = wd;
        if (i) pb.ioWDIndex = 1; else pb.ioNamePtr = decoy;
        err = PBGetWDInfoSync(&pb);
        for (k = 0, changed = 0; k < 512; k++) if (decoy[k] != 0x55) changed++;
        sprintf(line, "  PB %s: err=%d vRef=%d dir=%ld proc=%08lx decoy=%d B",
                i ? "ioWDIndex=1   " : "ioNamePtr=decoy", err, pb.ioWDVRefNum,
                pb.ioWDDirID, pb.ioWDProcID, changed);
        Say();
    }

    for (i = 0; i < 2; i++) {
        unsigned short pat = i ? decoyH : 0;
        int k;
        for (k = 0; k < 512; k++) decoy[k] = 0x55;
        Poison(pat);
        err = G_GetWDInfo(wd, &v, &d, &p);
        for (k = 0, changed = 0; k < 512; k++) if (decoy[k] != 0x55) changed++;
        sprintf(line, "  stack %04x: err=%d vRef=%d dir=%ld proc=%08lx decoy=%d B",
                pat, err, v, d, p, changed);
        Say();
        if (changed) {
            sprintf(line, "    decoy holds \"%.*s\"", decoy[0] < 40 ? decoy[0] : 40,
                    (char *)decoy + 1);
            Say();
        }
    }
}

/* ---- 2. SetFInfo: ioFDirIndex never set, err never assigned ------------- */
static void Case2(short vol, const char *what)
{
    FInfo fi; OSErr err; int i; char ta[5], tb[5], tz[5];
    static unsigned char nameB[64];

    for (i = 0; i < 2; i++) {
        unsigned short pat = i ? 0x0001 : 0;
        OwnCreate(vol, 2, "\pA", 'AAAA');
        OwnCreate(vol, 2, "\pB", 'BBBB');
        memcpy(nameB, "\pB", 2);
        fi.fdType = 'ZZZZ'; fi.fdCreator = 'ZZZZ'; fi.fdFlags = 0;
        fi.fdLocation.h = fi.fdLocation.v = 0; fi.fdFldr = 0;
        Poison(pat);
        err = G_SetFInfo(nameB, vol, &fi);
        T4(ta, OwnType(vol, 2, "\pA")); T4(tb, OwnType(vol, 2, "\pB"));
        sprintf(line, "2 SetFInfo %s stack %04x: err=%d A=%s B=%s name=\"%.*s\"",
                what, pat, err, ta, tb, nameB[0] < 20 ? nameB[0] : 20,
                (char *)nameB + 1);
        Say();
    }
    (void)tz;
}

/* ---- 3. HSetFInfo: ioDirID left holding the file ID --------------------- */
static void Case3(short vol)
{
    HParamBlockRec pb; FInfo fi; OSErr err, e2; long dir; char tf[5], tb[5];

    dir = Folder(vol, &e2);
    OwnCreate(vol, dir, "\pF", 'FFFF');
    OwnCreate(vol, 2, "\pB", 'BBBB');

    fi.fdType = 'ZZZZ'; fi.fdCreator = 'ZZZZ'; fi.fdFlags = 0;
    fi.fdLocation.h = fi.fdLocation.v = 0; fi.fdFldr = 0;
    Poison(0);
    err = G_HSetFInfo(vol, dir, "\pF", &fi);
    T4(tf, OwnType(vol, dir, "\pF"));
    sprintf(line, "3 HSetFInfo D:F (dir %ld, mk %d): err=%d F=%s", dir, e2, err, tf);
    Say();
    Poison(0);
    err = G_HSetFInfo(vol, 2, "\pB", &fi);
    T4(tb, OwnType(vol, 2, "\pB"));
    sprintf(line, "3 HSetFInfo root:B:          err=%d B=%s", err, tb);
    Say();
}

/* ---- 4. HOpen: ioFVersNum never set ------------------------------------- */
static void Case4(short vol, const char *what)
{
    HParamBlockRec pb; OSErr err; short ref; int i;

    OwnCreate(vol, 2, "\pV", 'VVVV');
    for (i = 0; i < 2; i++) {
        unsigned short pat = i ? 0x4141 : 0;
        ref = 0;
        Poison(pat);
        err = G_HOpen(vol, 2, "\pV", fsRdPerm, &ref);
        if (!err) { Zero(&pb, sizeof pb); pb.ioParam.ioRefNum = ref;
                    PBCloseSync((ParmBlkPtr)&pb); }
        sprintf(line, "4 HOpen %s stack %04x: err=%d", what, pat, err);
        Say();
    }
    Zero(&pb, sizeof pb);              /* the field itself, no glue */
    pb.ioParam.ioNamePtr = "\pV";
    pb.ioParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = 2;
    pb.ioParam.ioPermssn = fsRdPerm;
    pb.ioParam.ioVersNum = 0x41;
    err = PBHOpenSync(&pb);
    if (!err) PBCloseSync((ParmBlkPtr)&pb);
    sprintf(line, "4 PBHOpen %s ioVersNum=0x41: err=%d", what, err);
    Say();
}

int main(void)
{
    WindowPtr w; Rect r; short hfs, mfs; unsigned short shfs = 0, smfs = 0;
    Ptr blk; long size = 140000L, a, h;

    InitGraf(&qd.thePort); InitFonts(); InitWindows(); InitMenus();
    TEInit(); InitDialogs(NULL); InitCursor();
    r = qd.screenBits.bounds;
    w = NewWindow(NULL, &r, "\p", true, plainDBox, (WindowPtr)-1, false, 0);
    SetPort(w);
    TextFont(4); TextSize(9);           /* Monaco 9 */

    /* A decoy at an address whose two halves are equal, so a long read from
     * a stack filled with that half points at it whatever the alignment. */
    blk = NewPtr(size);
    if (!blk) { strcpy(line, "no memory for the decoy"); Say(); Idle(); }
    h = ((long)blk + 65536L) / 65537L;
    if (h & 1) h++;
    a = h * 65537L;
    if (a + 512 > (long)blk + size) { strcpy(line, "decoy does not fit"); Say(); Idle(); }
    decoy = (unsigned char *)a;
    decoyH = (unsigned short)h;

    {   /* GetNextEvent mounts inserted disks; give them time to arrive */
        EventRecord ev; long t0 = TickCount();
        do {
            GetNextEvent(everyEvent, &ev);
            SystemTask();
            hfs = FindVol("GlueHFS", &shfs);
            mfs = FindVol("GlueMFS", &smfs);
        } while ((!hfs || !mfs) && TickCount() - t0 < 1200);
    }
    sprintf(line, "GlueHFS vRef=%d sig=%04x  GlueMFS vRef=%d sig=%04x  (4c78d24%s)",
            hfs, shfs, mfs, smfs,
#ifdef GLUE_FIXED
            " + glue-audit.patch"
#else
            ""
#endif
            );
    Say();

    if (hfs) { Case1(hfs); Case2(hfs, "HFS"); Case3(hfs); Case4(hfs, "HFS"); }
    if (mfs) { Case2(mfs, "MFS"); Case4(mfs, "MFS"); }
    strcpy(line, "done"); Say();
    Idle();
}
```

</details>
