# Ready-to-post upstream issue (github.com/autc04/Retro68)

**Not filed, and not to be filed from here.** The maintainer posts this from
his own account (MANUAL_TESTS.md §7, CLAUDE.md Rules). Reproduction:
`iomisc_repro.c` in this directory, pasted inline (this repository is private).

Re-verified 2026-10-13 against Retro68 master `d8b891a` (2026-10-09): its
pinned multiversal `d124fa6` and multiversal master `28eac84` carry a
`custom/glue.c` byte-identical to the one measured here.

**What is NOT in this issue, and why.** The 2026-08 draft led with "`OpenDF`
and `HOpenDF` return `paramErr` on System 6 and do not fall back". That is
Apple's documented contract, not a bug: Technote FL 1041 tells the caller to
retry with `HOpen` on `paramErr`, and Retro68 already settled exactly this in
issue #53 (2018) by doing so in `libretro/syscalls.c`. Withdrawn (BLOCKERS.md).

---

**Title:** `HOpen`/`HOpenRF`/`HOpenDF` don't initialise `ioMisc`, and the File Manager writes through it

**Body:**

Hi! `HOpen`, `HOpenRF` and `HOpenDF` in `multiversal/custom/glue.c` never set `ioMisc`, so it holds whatever was on the stack. But for `_HOpen` it's an input (a pointer to an access path buffer, or NULL), and Technote FL 1041 says:

> ioMisc must be initialized to zero before calling PBHOpenDF, PBHOpenRF, or PBHOpen. Failure to initialize ioMisc to zero on some Macintosh models will cause the system to crash.

The File Manager really does write through it. With the address of a 1 KB array left on the stack, `HOpen` succeeds and the array gets overwritten (524 bytes on System 6.0.8, 12 on 7.0.1). That's how my application ended up hanging or writing nothing on System 6: with a copy of the glue it fails, and adding just `pb.ioParam.ioMisc = NULL;` fixes it.

`FSOpen`, `OpenDF` and `OpenRF` in the same file already set it to NULL, so the H-variants just need the same line.

Repro below: build it as an app, run it, and read the three lines. Mini vMac Mac Plus, System 6.0.8 and 7.0.1, Retro68 `335fa54f6d`; master still has the same `glue.c`.

<details><summary>iomisc_repro.c (70 lines)</summary>

```c
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
```

</details>

Thanks for Retro68!
