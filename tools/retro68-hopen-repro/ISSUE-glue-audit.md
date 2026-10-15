# Upstream issue draft: four more fields multiversal's glue leaves unset

**Not filed.** For the maintainer to post on autc04/Retro68, as #320 was
(`ISSUE.md`). The body embeds `glue-audit.patch` and `glue_repro.c`;
regenerate it if either changes. Measured 2026-10-15 with `glue_repro.c`
linked against multiversal `4c78d24`'s glue (`mkgluelib.sh`) and against
the same glue with the patch, on Systems 3.0, 6.0.8 and 7.0.1; the claims
the short repro does not show (the root-folder `HSetFInfo`, `HOpen` on
HFS, the 8 bytes `PBGetWDInfo` writes) are `glue_audit.c`'s (README.md).

---

**Title:** More File Manager glue reads uninitialised param-block fields: `GetWDInfo`, `SetFInfo`, `HSetFInfo`, and `ioFVersNum` in the `HOpen` family

**Body:**

Thanks for the quick fix on #320! I went through the rest of the File Manager glue in `custom/glue.c` against Inside Macintosh: Files (ch. 2), and found four more spots that read a field the glue never sets, or overwrite one it needs:

1. **`GetWDInfo`** never sets `ioNamePtr` or `ioWDIndex`, and both are inputs to `PBGetWDInfo`: a non-zero `ioWDIndex` selects a working directory by index instead of by `wdRefNum`, and the volume name is written through `ioNamePtr` unless it's NIL. With a non-zero pattern on the stack, `GetWDInfo` on a valid working directory returns `nsvErr` (-35) and a wrong `dirID`. (Called directly with `ioNamePtr` pointing at a buffer, `PBGetWDInfo` writes the volume name into it.)
2. **`SetFInfo`** never sets `ioFDirIndex`, and ignores the result of `PBGetFInfoSync`, so `if(err)` tests an uninitialised variable (`-Wall` warns). With `0x0001` on the stack, `SetFInfo("B", ...)` returns `noErr` but sets the Finder info **of file A**, index 1 in that folder, and overwrites the caller's file name with `"A"`.
3. **`HSetFInfo`** doesn't restore `ioDirID` after `PBHGetFInfoSync`, which replaces it with the file ID (`HCreate` does restore it, with a comment). `PBHSetFInfo` then takes the file ID as a directory ID and fails with `fnfErr` (-43), even with a zeroed stack. No header declares `HSetFInfo`, so only code with its own prototype reaches it.
4. **`HOpen`/`HOpenRF`/`HOpenDF`** never set `ioFVersNum`, of which IM says "This field is no longer used and you should always set it to 0." HFS ignores it, but on an MFS volume a non-zero byte left there makes `HOpen` of an existing file return `fnfErr`. `FSOpen`, `OpenDF` and `OpenRF` already set it to 0.

The repro below fills the stack with zeroes, then with a non-zero pattern, before each call. Mini vMac Mac Plus, Systems 3.0, 6.0.8 and 7.0.1, with an HFS and an MFS disk mounted, linked against the glue from multiversal `4c78d24`. All three Systems print the same thing:

```
1 GetWDInfo, stack 0000: err=0 dirID=219 (want 0, 219)
1 GetWDInfo, stack 0004: err=-35 dirID=262148 (want 0, 219)
2 SetFInfo("B"), stack 0000: err=0 A=AAAA B=ZZZZ name="B"
2 SetFInfo("B"), stack 0001: err=0 A=ZZZZ B=BBBB name="A"
3 HSetFInfo("B"), stack 0000: err=-43
4 HOpen on MFS, stack 0000: err=0
4 HOpen on MFS, stack 4141: err=-43
```

(The `dirID` and the `GetWDInfo` pattern vary with the System; that's 6.0.8.) With the patch below applied to the same glue, every line reads `err=0`, `GetWDInfo` returns the right `dirID`, and `SetFInfo` changes B and leaves the name alone, on all three:

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

<details><summary>glue_repro.c (122 lines)</summary>

```c
/* GetWDInfo, SetFInfo, HSetFInfo and HOpen read param-block fields they never
 * set. Each call runs after the stack is filled with zeroes, then with a
 * non-zero pattern. Needs an HFS volume; mount an MFS one too for line 4. */
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

/* glue.c defines it, but no header declares it */
pascal OSErr HSetFInfo(short vRefNum, long dirID, ConstStr255Param fileName,
                       const FInfo *fndrInfo);

static char lines[12][100];
static short row;
static volatile long sink;

static void Say(const char *s) { strcpy(lines[row++], s); }

static __attribute__((noinline)) void Poison(unsigned short p)
{   /* every field of a block built here reads p, or (p << 16) | p */
    unsigned short s[512]; int i;
    for (i = 0; i < 512; i++) s[i] = p;
    sink += s[0] + s[511];
}

static OSType TypeOf(short vref, long dir, ConstStr255Param name)
{
    FInfo fi;
    return HGetFInfo(vref, dir, name, &fi) ? '----' : fi.fdType;
}

int main(void)
{
    WindowPtr w; EventRecord ev; HParamBlockRec pb; WDPBRec wp; FInfo fi;
    Str255 nameB; char t[100]; short vol = 0, wd, mfs = 0, ref, v, i, pat[2];
    long dir, d, proc, a, h; Ptr blk; OSErr err;

    InitGraf(&qd.thePort); InitFonts(); InitWindows(); InitMenus();
    TEInit(); InitDialogs(NULL); InitCursor();
    w = NewWindow(NULL, &qd.screenBits.bounds, "\p", true, plainDBox,
                  (WindowPtr)-1, false, 0);
    SetPort(w);
    for (a = TickCount(); TickCount() - a < 300; )   /* mount inserted disks */
        GetNextEvent(everyEvent, &ev);

    for (i = 1; !vol || !mfs; i++) {    /* the first HFS and MFS volumes */
        memset(&pb, 0, sizeof pb);
        pb.volumeParam.ioVolIndex = i;
        if (PBHGetVInfoSync(&pb)) break;
        v = pb.volumeParam.ioVRefNum;
        if (pb.volumeParam.ioVSigWord == 0x4244 && !vol) vol = v;
        if (pb.volumeParam.ioVSigWord == 0xD2D7 && !mfs) mfs = v;
    }
    /* a scratch folder at its root, and a working directory on it */
    memset(&pb, 0, sizeof pb);
    pb.fileParam.ioNamePtr = "\pGlueTest"; pb.fileParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = 2;            /* fsRtDirID */
    PBDirCreateSync(&pb);
    dir = pb.fileParam.ioDirID;
    memset(&wp, 0, sizeof wp);
    wp.ioVRefNum = vol; wp.ioWDDirID = dir; wp.ioWDProcID = 'GLUE';
    PBOpenWDSync(&wp);
    wd = wp.ioVRefNum;
    /* GetWDInfo's non-zero pattern: half of an address inside our own
     * block, so the name it may write through ioNamePtr lands there */
    blk = NewPtr(140000L);
    h = ((long)blk + 65536L) / 65537L; if (h & 1) h++;
    pat[0] = 0; pat[1] = (unsigned short)h;
    for (i = 0; i < 2; i++) {
        Poison(pat[i]);
        err = GetWDInfo(wd, &v, &d, &proc);
        sprintf(t, "1 GetWDInfo, stack %04x: err=%d dirID=%ld (want 0, %ld)",
                pat[i], err, d, dir);
        Say(t);
    }
    pat[1] = 0x0001;
    fi.fdCreator = 'ZZZZ'; fi.fdFlags = 0; fi.fdFldr = 0;
    fi.fdLocation.h = fi.fdLocation.v = 0;
    for (i = 0; i < 2; i++) {
        HDelete(vol, dir, "\pA"); HCreate(vol, dir, "\pA", 'AAAA', 'AAAA');
        HDelete(vol, dir, "\pB"); HCreate(vol, dir, "\pB", 'BBBB', 'BBBB');
        memcpy(nameB, "\pB", 2); fi.fdType = 'ZZZZ';
        Poison(pat[i]);
        err = SetFInfo(nameB, wd, &fi);
        sprintf(t, "2 SetFInfo(\"B\"), stack %04x: err=%d A=%.4s B=%.4s name=\"%.*s\"",
                pat[i], err, (char *)&(OSType){TypeOf(vol, dir, "\pA")},
                (char *)&(OSType){TypeOf(vol, dir, "\pB")}, nameB[0], nameB + 1);
        Say(t);
    }
    err = HSetFInfo(vol, dir, "\pB", &fi);
    sprintf(t, "3 HSetFInfo(\"B\"), stack 0000: err=%d", err);
    Say(t);
    pat[1] = 0x4141;
    if (mfs) HCreate(mfs, 0, "\pV", 'VVVV', 'VVVV');
    for (i = 0; mfs && i < 2; i++) {
        Poison(pat[i]);
        err = HOpen(mfs, 0, "\pV", fsRdPerm, &ref);
        if (!err) FSClose(ref);
        sprintf(t, "4 HOpen on MFS, stack %04x: err=%d", pat[i], err);
        Say(t);
    }
    if (!mfs) Say("4 HOpen: no MFS volume mounted");

    for (;;) {                          /* redraw on every update */
        SystemTask();
        if (GetNextEvent(everyEvent, &ev) && ev.what == updateEvt) {
            BeginUpdate(w); EraseRect(&w->portRect);
            for (i = 0; i < row; i++) {
                MoveTo(10, 40 + 14 * i);
                DrawText(lines[i], 0, strlen(lines[i]));
            }
            EndUpdate(w);
        }
    }
}
```

</details>
