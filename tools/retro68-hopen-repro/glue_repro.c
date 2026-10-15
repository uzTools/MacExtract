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
