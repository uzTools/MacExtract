/*
 * dcmptest — call a StuffIt 2.0 Optimizer module, and see whether the ABI is right.
 *
 * The reading: the application locks the 'COMP'/'DCMP' resource handle,
 * dereferences it and jumps to the module's first byte, which is a
 * `bra.s` over a sixteen-byte header ('COMP' or 'DCMP' at +4, the
 * module's own id at +8). The call is Pascal and the callee pops
 * twelve bytes:
 *
 *     pascal void Module(Ptr buffer, long *selector, ProcPtr io);
 *
 * `*selector` carries the request AND the answer. This probe uses the
 * cheapest one, **-3**, which every module answers by copying its own
 * name into `buffer` with _BlockMove and writing 1 back — no files, no
 * Memory Manager, no callback, so what it proves is the calling
 * convention and nothing else. FORMATS.md, *The module ABI*.
 *
 * If the name comes out, the convention is right. If the machine bombs,
 * the mark before the bomb says how far it got: 0 alive, 1 resource
 * file open, 2 module found and locked, 3 returned from the call, 4 the
 * answer was 1, 5 the name is non-empty.
 *
 * Put it on a volume that has StuffIt Deluxe 2.0.1's Optimizers
 * installed (tools/vmac/sitopt.py --install). Built by hand, not by
 * ci.sh — tools/vmac/README.md.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include <Quickdraw.h>
#include <Fonts.h>
#include <Windows.h>
#include <Resources.h>
#include <Memory.h>
#include <string.h>

QDGlobals qd;

/* The module under test, as a full pathname: this probe is launched
 * from the volume's root and the Optimizers live in the System Folder. */
#define MODULE_PATH "\pMacintosh:System Folder:Optimizers:MacPaint 1"

typedef pascal void (*ModuleProc)(Ptr buffer, long *selector, ProcPtr io);

static void mark(short n)
{
    Rect r;
    short col = (short)(n % 8), row = (short)(n / 8);
    SetRect(&r, (short)(10 + col * 62), (short)(25 + row * 28),
            (short)(58 + col * 62), (short)(45 + row * 28));
    PaintRect(&r);
}

static void say(short line, const unsigned char *s)
{
    MoveTo(12, (short)(120 + line * 16));
    DrawString(s);
}

int main(void)
{
    short ref;
    Handle mod;
    long sel;
    char buf[256];
    unsigned char msg[64];

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    mark(0);

    ref = OpenResFile((ConstStr255Param)MODULE_PATH);
    if (ref == -1) {
        say(0, "\pno module: OpenResFile failed");
        for (;;) { }
    }
    mark(1);
    UseResFile(ref);

    /* Get1IndResource, exactly as the application does: a module file
     * holds one, and its id is the module's number rather than 1. */
    mod = Get1IndResource('DCMP', 1);
    if (mod == NULL) {
        say(0, "\pno DCMP in it");
        for (;;) { }
    }
    HLock(mod);
    mark(2);

    /* The module's id is at +8 of its own resource, after the tag. */
    {
        short id = *(short *)(*mod + 8);
        msg[0] = 8;
        memcpy(msg + 1, "id = ?  ", 8);
        msg[6] = (unsigned char)('0' + (id % 10));
        say(1, msg);
    }

    memset(buf, 0, sizeof buf);
    sel = -3L;
    (*(ModuleProc)(*mod))((Ptr)buf, &sel, (ProcPtr)0);
    mark(3);

    if (sel == 1L) mark(4);

    /* The module copies a Pascal string in. Show it. */
    if ((unsigned char)buf[0] > 0 && (unsigned char)buf[0] < 64) {
        mark(5);
        say(2, (const unsigned char *)buf);
    } else {
        say(2, "\pname came back empty");
    }

    /* Never return: the Finder repaints the desktop long before a
     * screenshot can be taken (traptest says the same). */
    for (;;) { }
    return 0;
}
