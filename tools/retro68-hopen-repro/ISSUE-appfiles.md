# Upstream issue draft: GetAppFiles never returns for index 2 and up

**Filed 2026-10-15** by the maintainer as
https://github.com/autc04/Retro68/issues/323, the body below verbatim;
the issue is the record. The body embeds `appfiles.patch` and `appfiles_repro.c`;
regenerate it if either changes. Measured 2026-10-15 under Mini vMac (Mac
Plus) on Systems 3.0, 6.0.8 and 7.0.1: the stock glue (identical in
Retro68 `335fa54f6d` and multiversal `4c78d24`) and the same glue with the
patch (`mkgluelib.sh`, `-DGLUE_LIB_DIR`).

---

**Title:** `GetAppFiles`/`ClrAppFiles` never return for index 2 and up

**Body:**

`AppFilePtr` in `custom/glue.c` never decrements `index` in its `while(index)` loop, so `GetAppFiles` and `ClrAppFiles` never return for an index above 1, e.g. when the Finder opens an application with two documents.

```diff
--- a/custom/glue.c
+++ b/custom/glue.c
@@ -105,6 +105,7 @@
     {
         AppFile *f = (AppFile *)p;
         p += (8 + 1 + f->fName[0] + 1) & ~1;
+        index--;
     }
     return (AppFile *)p;
 }
```

Tested on Mini vMac (Mac Plus), Systems 3.0, 6.0.8 and 7.0.1 with the repro below: the current glue hangs in `GetAppFiles(2)`; with the fix, every document is returned.

<details><summary>appfiles_repro.c (49 lines)</summary>

```c
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
```

</details>
