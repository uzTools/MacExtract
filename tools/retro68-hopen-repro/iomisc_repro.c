/* iomisc_repro.c — Retro68's HOpen glue leaves ioMisc uninitialised, and the
 * File Manager writes through it.
 *
 * multiversal/custom/glue.c's HOpen, HOpenRF and HOpenDF declare an
 * HParamBlockRec on the stack and set four fields; ioMisc keeps whatever the
 * stack held. For _HOpen, ioMisc is an input: a pointer to the caller's own
 * access path buffer, or NULL for the volume buffer.
 * Source: Technote FL 1041 (Inside Macintosh: Files errata), "Parameter
 * blocks missing ioMisc field": "ioMisc must be initialized to zero before
 * calling PBHOpenDF, PBHOpenRF, or PBHOpen. Failure to initialize ioMisc to
 * zero on some Macintosh models will cause the system to crash."
 *
 * Three cases, each followed by a 4-byte FSRead and FSClose:
 *   1  PBHOpenSync, ioMisc = NULL      the control: decoy untouched
 *   2  PBHOpenSync, ioMisc = decoy     the File Manager uses ioMisc
 *   3  HOpen, decoy's address left on the stack by an earlier call
 * Case 3 changing the decoy is the bug: memory the caller never passed is
 * overwritten.
 *
 * Measured, Mini vMac 36.04 Mac Plus, Retro68 335fa54f6d (multiversal glue.c
 * byte-identical to 28eac84, 2026-10-13):
 *   System 6.0.8:  1 -> 0   2 -> 131   3 -> 131 longs changed (524 bytes)
 *   System 7.0.1:  1 -> 0   2 -> 3     3 -> 3
 */
#include <Quickdraw.h>
#include <Windows.h>
#include <Fonts.h>
#include <Files.h>
#include <Events.h>
#include <Menus.h>
#include <TextEdit.h>
#include <Dialogs.h>

static long decoy[256];             /* 1 KB, more than an access path buffer */
static short row;
static volatile long sink;

static void Say(const char *s, long v)
{
    unsigned char line[80], tmp[12];
    int n = 0;
    line[0] = 0;
    while (*s) line[++line[0]] = (unsigned char)*s++;
    if (v < 0) { line[++line[0]] = '-'; v = -v; }
    do { tmp[n++] = (unsigned char)('0' + v % 10); v /= 10; } while (v);
    while (n) line[++line[0]] = tmp[--n];
    MoveTo(10, 20 + 14 * row++);
    DrawString(line);
}

static void FillDecoy(void)
{
    int i;
    for (i = 0; i < 256; i++) decoy[i] = 0x55555555L;
}

static long DecoyChanged(void)
{
    long n = 0;
    int i;
    for (i = 0; i < 256; i++) if (decoy[i] != 0x55555555L) n++;
    return n;
}

/* Leave decoy's address all over the stack the next call will use. noinline,
 * or GCC folds the array into main's frame and HOpen never sees it. */
static __attribute__((noinline)) void PoisonStack(void)
{
    long p[128];
    int i;
    for (i = 0; i < 128; i++) p[i] = (long)decoy;
    sink += p[0] + p[127];
}

static void ReadAndClose(short ref)
{
    char buf[4];
    long count = 4;
    FSRead(ref, &count, buf);
    FSClose(ref);
}

static void ZeroPB(HParamBlockRec *pb)
{
    unsigned i;
    for (i = 0; i < sizeof *pb; i++) ((char *)pb)[i] = 0;
    pb->ioParam.ioNamePtr = "\pT";
    pb->ioParam.ioPermssn = fsRdPerm;
}

int main(void)
{
    WindowPtr w;
    Rect r;
    HParamBlockRec pb;
    short ref;
    long count = 512;
    static char data[512];
    OSErr err;

    InitGraf(&qd.thePort); InitFonts(); InitWindows(); InitMenus();
    TEInit(); InitDialogs(NULL); InitCursor();
    SetRect(&r, 10, 40, 500, 330);
    w = NewWindow(NULL, &r, "\pioMisc", true, plainDBox, (WindowPtr)-1, false, 0);
    SetPort(w);

    /* A 512-byte file "T" in the default directory. FSOpen zeroes ioMisc. */
    HDelete(0, 0, "\pT");
    HCreate(0, 0, "\pT", 'test', 'TEXT');
    FSOpen("\pT", 0, &ref);
    FSWrite(ref, &count, data);
    FSClose(ref);

    FillDecoy();
    ZeroPB(&pb);
    err = PBHOpenSync(&pb);
    Say("1 PBHOpen ioMisc=NULL   err=", err);
    ReadAndClose(pb.ioParam.ioRefNum);
    Say("    decoy longs changed: ", DecoyChanged());

    FillDecoy();
    ZeroPB(&pb);
    pb.ioParam.ioMisc = (Ptr)decoy;
    err = PBHOpenSync(&pb);
    Say("2 PBHOpen ioMisc=&decoy err=", err);
    ReadAndClose(pb.ioParam.ioRefNum);
    Say("    decoy longs changed: ", DecoyChanged());

    FillDecoy();
    PoisonStack();
    err = HOpen(0, 0, "\pT", fsRdPerm, &ref);
    Say("3 HOpen, poisoned stack err=", err);
    ReadAndClose(ref);
    Say("    decoy longs changed: ", DecoyChanged());

    Say("done ", 0);
    for (;;) SystemTask();     /* stay up so the screen can be read */
}
