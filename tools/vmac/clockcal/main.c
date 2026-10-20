/*
 * clockcal — a known duration for tools/vmac/macclock.py to measure.
 *
 * The stopwatch in macclock.py reads the emulated Mac's Ticks and screen
 * from the host. This gives it something whose length is known in advance:
 * a key starts a busy wait of a fixed number of ticks, drawn at both ends.
 *
 *   'a'..'z'  wait (letter - 'a' + 1) * 60 ticks   ('j' = 600, 'k' = 660)
 *   '1'..'9'  wait digit * 600 ticks               ('6' = 3,600: a minute)
 *
 * On the key: TickCount is read, a mark is inverted (the start the
 * stopwatch should see within a tick of the keystroke), the program spins on
 * TickCount until the wait is over, and then paints a second mark and the
 * ticks it actually waited: the END event. 'j' and 'k' differ by exactly 60
 * ticks, which is the deliberately shifted end the instrument must report as
 * one second more.
 *
 * Busy, not Delay(): an extraction keeps the 68000 busy, and so does this.
 * The pointer is hidden, so nothing but the two marks and the number draws.
 *
 * Launched as the boot shell by `tools/vmac/expander.py --calibrate`, which
 * builds it. Not built by ci.sh.
 */
#include <Quickdraw.h>
#include <Fonts.h>
#include <Windows.h>
#include <Events.h>
#include <OSUtils.h>
#include <TextUtils.h>

QDGlobals qd;

int main(void)
{
    EventRecord ev;
    Rect all, a, b, num;
    short row = 0;

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    FlushEvents(everyEvent, 0);
    HideCursor();

    all = qd.screenBits.bounds;
    FillRect(&all, &qd.white);
    MoveTo(12, 20);
    DrawString("\pclockcal: a..z = n*60 ticks, 1..9 = n*600 ticks");

    for (;;) {
        if (GetNextEvent(keyDownMask, &ev)) {
            char c = (char)(ev.message & charCodeMask);
            long n = 0, t0, t1;
            Str255 s;
            if (c >= 'a' && c <= 'z') n = (long)(c - 'a' + 1) * 60L;
            else if (c >= '1' && c <= '9') n = (long)(c - '0') * 600L;
            if (n == 0) continue;
            t0 = TickCount();
            SetRect(&a, 12, (short)(40 + row * 20), 28, (short)(56 + row * 20));
            InvertRect(&a);                              /* start mark */
            while (TickCount() - t0 < n)
                ;
            t1 = TickCount();
            SetRect(&b, 36, (short)(40 + row * 20), 52, (short)(56 + row * 20));
            InvertRect(&b);                              /* end mark */
            SetRect(&num, 60, (short)(40 + row * 20), 300, (short)(56 + row * 20));
            EraseRect(&num);
            MoveTo(60, (short)(53 + row * 20));
            NumToString(n, s);
            DrawString(s);
            DrawString("\p asked, ");
            NumToString(t1 - t0, s);
            DrawString(s);
            DrawString("\p waited");
            row = (short)((row + 1) % 12);
        }
    }
    return 0;
}
