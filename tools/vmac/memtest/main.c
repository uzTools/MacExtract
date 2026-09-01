/*
 * memtest — how much memory a machine actually leaves an application.
 *
 * The 512 KB tier's budget was measured through the application itself
 * (FORMATS.md, *512 KB machines*). A Macintosh 128K never reaches that code:
 * it bombs on launch, so the only way to get a number off it is a probe small
 * enough to load. This is that probe.
 *
 * It reports the low-memory globals that bound an application partition, then
 * bisects the largest single NewPtr the heap will give — which is the figure
 * a CODE resource has to fit in, since CODE resources are handles in this
 * heap (FORMATS.md, *What the application costs the engine*).
 *
 * MaxApplZone is guarded exactly as the `rom64k` branch guards it: it is
 * [Not in ROM] on a 64K ROM (Inside Macintosh II-30) and Retro68 emits it as
 * a trap, so calling it unguarded is itself a bomb and would measure nothing.
 *
 * Put it on an MFS volume as `Finder` (mkmfs.py memtest.bin:Finder) and never
 * return: when a shell quits, the System repaints the desktop over the
 * numbers before a screenshot can be taken.
 *
 * Built by hand, not by ci.sh — see tools/vmac/README.md.
 */
#include <Quickdraw.h>
#include <Fonts.h>
#include <Windows.h>
#include <OSUtils.h>
#include <LowMem.h>
#include <Memory.h>

QDGlobals qd;

static short gLine;

static void Say(const unsigned char *label, long value)
{
    Str255 s;
    MoveTo(12, (short)(40 + gLine * 18));
    DrawString(label);
    NumToString(value, s);
    DrawString(s);
    gLine++;
}

/* Source: Inside Macintosh IV, Preface, "Compatibility" — a ROM version word
 * (Inside Macintosh II, ROMBase+8) of $00xx below $75 is a 64K ROM. Written
 * as "not positively a 64K ROM" so an unsurveyed value behaves as before. */
static Boolean Has128KROM(void)
{
    const unsigned char *rom = (const unsigned char *)LMGetROMBase();
    return (Boolean)!(rom[8] == 0 && rom[9] < 0x75);
}

/* Largest single block the heap will hand out, by bisection. MaxBlock is not
 * used: what matters here is what NewPtr actually returns, which is the call
 * the engine's allocator makes. */
static long LargestPtr(void)
{
    long lo = 0, hi = 4L * 1024L * 1024L;
    while (hi - lo > 256) {
        long mid = lo + (hi - lo) / 2;
        Ptr p = NewPtr(mid);
        if (p) { DisposePtr(p); lo = mid; } else { hi = mid; }
    }
    return lo;
}

int main(void)
{
    long freeBefore, freeAfter, biggest;
    Ptr code2;

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();

    /* White ground first: the desktop pattern is a 50% grey and digits drawn
     * over it cannot be read back off a screenshot, which is the whole
     * output of this probe. */
    FillRect(&qd.screenBits.bounds, &qd.white);

    freeBefore = FreeMem();
    if (Has128KROM()) MaxApplZone();
    freeAfter = FreeMem();

    Say("\pMemTop        ", (long)LMGetMemTop());
    Say("\pApplZone      ", (long)LMGetApplZone());
    Say("\pApplLimit     ", (long)LMGetApplLimit());
    Say("\pHeapEnd       ", (long)LMGetHeapEnd());
    Say("\pCurStackBase  ", (long)LMGetCurStackBase());
    Say("\pFreeMem       ", freeBefore);
    Say("\pFreeMem grown ", freeAfter);

    biggest = LargestPtr();
    Say("\pLargest NewPtr", biggest);

    /* CODE 2 of the shipping application, the segment the Segment Loader has
     * to place before any of the engine runs. Its size is read off
     * dist/MacExtract.bin's resource map. */
    code2 = NewPtr(142152L);
    Say("\pCODE 2 fits   ", code2 ? 1 : 0);
    if (code2) DisposePtr(code2);

    for (;;) SystemTask();
    return 0;
}
