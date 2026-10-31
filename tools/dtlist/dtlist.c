/* dtlist.c — what the Desktop Manager holds for a few creators: on every
 * mounted volume with a desktop database, PBDTGetAPPL for each creator at
 * index 0 and up, name, parent folder and tag (the APPL entry's tag info),
 * drawn in a window (held 60 seconds, for a screenshot) and written to
 * `DTList` beside this application.
 *
 * WHY: on Mac OS 9 the Finder launched StuffIt Expander for `SITx` over a
 * `SITx` stub, but a stub over an identical Expander under any other
 * creator (DECISIONS.md 2026-10-31, *the stub that sorts*). The list is
 * what the Finder chooses from.
 *
 * Source: Inside Macintosh: Files, Desktop Manager (PBDTGetPath,
 * PBDTGetAPPL: ioFileCreator, ioIndex, ioNamePtr, ioAPPLParID,
 * ioTagInfo). What index 0 means is one of the things read off the log.
 * A HARNESS tool, never built by ci.sh.
 */
#include <Files.h>
#include <Fonts.h>
#include <Events.h>
#include <Memory.h>
#include <Quickdraw.h>
#include <Windows.h>
#include <Processes.h>
#include <TextUtils.h>

static char gLog[4096];
static short gLen;

static void put(const char *s) { while (*s && gLen < 4000) gLog[gLen++] = *s++; }

/* The log, one line per CR, drawn in the window. */
static void draw(WindowPtr w)
{
    short i, y = 12, start = 0;
    SetPort(w);
    for (i = 0; i <= gLen; i++) {
        if (i == gLen || gLog[i] == '\r') {
            MoveTo(4, y);
            DrawText(gLog, start, i - start);
            y += 11;
            start = i + 1;
        }
    }
}
static void putp(const unsigned char *p)
{
    short i;
    for (i = 1; i <= p[0] && gLen < 4000; i++) gLog[gLen++] = p[i];
}
static void putn(long v)
{
    Str255 s;
    NumToString(v, s);
    putp(s);
}
static void put4(OSType t)
{
    char c[5];
    c[0] = t >> 24; c[1] = t >> 16; c[2] = t >> 8; c[3] = t; c[4] = 0;
    put(c);
}

int main(void)
{
    static const OSType kCreators[] = { 'SITx', 'TQ01', 'MExt' };
    ProcessSerialNumber me;
    ProcessInfoRec info;
    Str255 myName, name, vname;
    FSSpec myself, log;
    HParamBlockRec v;
    DTPBRec dt;
    short vi, k, c, ref;
    long count;

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitCursor();

    GetCurrentProcess(&me);
    info.processInfoLength = sizeof(info);
    info.processName = myName;
    info.processAppSpec = &myself;
    GetProcessInformation(&me, &info);

    for (vi = 1; ; vi++) {
        v.volumeParam.ioCompletion = NULL;
        v.volumeParam.ioNamePtr = vname;
        v.volumeParam.ioVRefNum = 0;
        v.volumeParam.ioVolIndex = vi;
        if (PBHGetVInfoSync(&v)) break;
        put("volume "); putp(vname); put("\r");
        dt.ioCompletion = NULL;
        dt.ioNamePtr = NULL;
        dt.ioVRefNum = v.volumeParam.ioVRefNum;
        if (PBDTGetPath(&dt)) { put("  no desktop database\r"); continue; }
        for (c = 0; c < 3; c++) {
            for (k = 0; k < 8; k++) {
                OSErr e;
                dt.ioNamePtr = name;
                dt.ioIndex = k;
                dt.ioFileCreator = kCreators[c];
                e = PBDTGetAPPLSync(&dt);
                put("  "); put4(kCreators[c]); put(" index "); putn(k);
                if (e) { put(" err "); putn(e); put("\r"); if (k) break; else continue; }
                put(" "); putp(name); put(" dir "); putn(dt.ioAPPLParID);
                put(" tag "); putn(dt.ioTagInfo); put("\r");
            }
        }
    }

    {
        Rect r;
        WindowPtr w;
        EventRecord ev;
        long stop;
        SetRect(&r, 20, 60, 620, 460);
        w = NewWindow(NULL, &r, "\pdtlist", true, documentProc,
                      (WindowPtr)-1L, false, 0);
        SetPort(w);
        TextFont(kFontIDMonaco);
        TextSize(9);
        draw(w);
        stop = TickCount() + 60L * 60;
        while (TickCount() < stop) WaitNextEvent(everyEvent, &ev, 6, NULL);
    }

    log = myself;
    BlockMoveData("\pDTList", log.name, 7);
    FSpDelete(&log);
    if (FSpCreate(&log, 'ttxt', 'TEXT', smSystemScript) == noErr
        && FSpOpenDF(&log, fsWrPerm, &ref) == noErr) {
        count = gLen;
        FSWrite(ref, &count, gLog);
        FSClose(ref);
    }
    return 0;
}
