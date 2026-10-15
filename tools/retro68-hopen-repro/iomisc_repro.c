/* HOpen leaves ioMisc uninitialised; the File Manager writes through it.
 * Prints how many longs of a 1 KB decoy each open + FSRead + FSClose changed. */
#include <Quickdraw.h>
#include <Windows.h>
#include <Fonts.h>
#include <Files.h>
#include <Menus.h>
#include <TextEdit.h>
#include <Dialogs.h>
#include <Events.h>
#include <stdio.h>
#include <string.h>

static long decoy[256];
static volatile long sink;
static short row;

static __attribute__((noinline)) void PoisonStack(void)
{   /* leave &decoy all over the stack HOpen is about to use */
    long p[128]; int i;
    for (i = 0; i < 128; i++) p[i] = (long)decoy;
    sink += p[0] + p[127];
}

static void Check(const char *label, OSErr err, short ref)
{
    char buf[4], line[64]; long n = 4, changed = 0; int i;
    FSRead(ref, &n, buf);
    FSClose(ref);
    for (i = 0; i < 256; i++) if (decoy[i] != 0x55555555L) changed++;
    sprintf(line, "%s err=%d, decoy longs changed: %ld", label, err, changed);
    MoveTo(10, 20 + 14 * row++);
    DrawText(line, 0, strlen(line));
    for (i = 0; i < 256; i++) decoy[i] = 0x55555555L;
}

int main(void)
{
    WindowPtr w; Rect r; HParamBlockRec pb; short ref; long n = 512;
    static char data[512]; OSErr err;

    InitGraf(&qd.thePort); InitFonts(); InitWindows(); InitMenus();
    TEInit(); InitDialogs(NULL); InitCursor();
    SetRect(&r, 10, 40, 500, 200);
    w = NewWindow(NULL, &r, "\p", true, plainDBox, (WindowPtr)-1, false, 0);
    SetPort(w);
    for (n = 0; n < 256; n++) decoy[n] = 0x55555555L;
    n = 512;

    HDelete(0, 0, "\pT");                    /* a 512-byte test file */
    HCreate(0, 0, "\pT", 'test', 'TEXT');
    FSOpen("\pT", 0, &ref); FSWrite(ref, &n, data); FSClose(ref);

    memset(&pb, 0, sizeof pb);               /* 1: control */
    pb.ioParam.ioNamePtr = "\pT";
    err = PBHOpenSync(&pb);
    Check("1 PBHOpen, ioMisc=NULL  ", err, pb.ioParam.ioRefNum);

    memset(&pb, 0, sizeof pb);               /* 2: the File Manager uses ioMisc */
    pb.ioParam.ioNamePtr = "\pT";
    pb.ioParam.ioMisc = (Ptr)decoy;
    err = PBHOpenSync(&pb);
    Check("2 PBHOpen, ioMisc=decoy ", err, pb.ioParam.ioRefNum);

    PoisonStack();                           /* 3: the glue */
    err = HOpen(0, 0, "\pT", fsRdPerm, &ref);
    Check("3 HOpen, poisoned stack ", err, ref);

    for (;;) SystemTask();
}
