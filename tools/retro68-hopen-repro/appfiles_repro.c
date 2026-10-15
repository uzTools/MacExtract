/* GetAppFiles never returns for index >= 2: AppFilePtr's while(index) loop
 * never decrements index. This puts the list the Finder leaves for two
 * documents in AppParmHandle (layout: Inside Macintosh, Segment Loader),
 * then asks for each in turn. Each line is drawn before its call. */
#include <Quickdraw.h>
#include <Windows.h>
#include <Fonts.h>
#include <Memory.h>
#include <SegLoad.h>
#include <stdio.h>
#include <string.h>

static short row;

static void Say(const char *s)
{
    MoveTo(10, 40 + 14 * row++);
    DrawText((Ptr)s, 0, strlen(s));
}

int main(void)
{
    static const unsigned char list[] = {
        0, 0,  0, 2,                                     /* appOpen, 2 files */
        0xFF, 0xFF, 'T','E','X','T', 0, 0, 5, 'F','i','r','s','t',
        0xFF, 0xFF, 'T','E','X','T', 0, 0, 6, 'S','e','c','o','n','d', 0
    };
    WindowPtr w; Rect r; Handle h; AppFile f; short msg, n, i; char t[80];

    InitGraf(&qd.thePort); InitFonts(); InitWindows();
    SetRect(&r, 10, 40, 500, 200);
    w = NewWindow(NULL, &r, "\p", true, plainDBox, (WindowPtr)-1, false, 0);
    SetPort(w);

    PtrToHand(list, &h, sizeof list);
    LMSetAppParmHandle(h);
    CountAppFiles(&msg, &n);
    sprintf(t, "CountAppFiles: message=%d count=%d", msg, n);
    Say(t);
    for (i = 1; i <= n; i++) {
        sprintf(t, "GetAppFiles(%d)...", i);
        Say(t);
        GetAppFiles(i, &f);
        sprintf(t, "  returned \"%.*s\"", f.fName[0], (char *)f.fName + 1);
        Say(t);
    }
    Say("done");
    for (;;) SystemTask();
}
