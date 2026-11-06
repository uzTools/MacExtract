/* pass_filter_test.c — the password dialog's key filter, typed into.
 *
 * PassFilter and gPassBuf (mac/macextract_mac.c, *Asking for a password*)
 * live inside the Toolbox-only part of the shell, which mac_sink_test.c
 * compiles out, so tests/run_mac_sink.sh lifts the two of them out of the
 * source as they stand (build/pass_filter_src.c) and this file supplies
 * the handful of Toolbox names they use. gPassBuf's declaration is turned
 * into a typedef on the way, so the buffer under test is the size the
 * source declares, followed in memory by a canary nothing else touches.
 *
 * Types 64 characters — UNC_PASSWORD_MAX, the most the engine takes — then
 * a 65th, and checks that all 64 are kept, the 65th is refused, and no
 * byte after the buffer moved. Until 2026-11-06 the buffer was a Str63 and
 * the 64th character went into the byte after it (DECISIONS.md 2026-11-06,
 * *the 64th character of a password*).
 *
 * Cannot see: the Dialog Manager's own field (the bullets), the mouse path,
 * or MacAskPassword's copy out of the buffer, which is not lifted; that
 * copy reads gPassBuf[1..len] with len <= UNC_PASSWORD_MAX, so it is in
 * bounds exactly when the typing is.
 */
#include <stdio.h>
#include <string.h>
#include "macextract.h"

typedef unsigned char Boolean;
typedef unsigned char Str63[64];
typedef void *DialogPtr, *GrafPtr, **Handle;
typedef struct { short v, h; } Point;
typedef struct { short top, left, bottom, right; } Rect;
typedef struct {
    unsigned short what;
    unsigned long  message;
    unsigned long  when;
    Point          where;
    unsigned short modifiers;
} EventRecord;
#define pascal
#define true  1
#define false 0
enum { mouseDown = 1, keyDown = 3, autoKey = 5 };
#define charCodeMask 0x000000FFUL
#define cmdKey       0x0100
#define StackSample() ((void)0)
static void GetPort(GrafPtr *p) { *p = 0; }
static void SetPort(GrafPtr p) { (void)p; }
static void GlobalToLocal(Point *p) { (void)p; }
static void GetDialogItem(DialogPtr d, short i, short *k, Handle *h, Rect *r)
{ (void)d; (void)i; *k = 0; *h = 0; memset(r, 0, sizeof *r); }
static Boolean PtInRect(Point p, const Rect *r) { (void)p; (void)r; return 0; }

/* The lifted declaration reads `typedef <its type> PassBufT; PASSBUF_STORAGE`. */
#define CANARY 16
#define PASSBUF_STORAGE \
    static struct { PassBufT buf; unsigned char canary[CANARY]; } gT;
#define gPassBuf gT.buf
#include "pass_filter_src.c"

static int canary_ok(void)
{
    int i;
    for (i = 0; i < CANARY; i++) if (gT.canary[i] != 0xC3) return 0;
    return 1;
}

static Boolean type_key(unsigned char ch)
{
    EventRecord ev;
    short item = 0;
    memset(&ev, 0, sizeof ev);
    ev.what = keyDown;
    ev.message = ch;
    return PassFilter(0, &ev, &item);
}

int main(void)
{
    int i, bad = 0;
    unsigned char want[UNC_PASSWORD_MAX];

    memset(gT.canary, 0xC3, CANARY);
    gT.buf[0] = 0;
    printf("pass-filter: gPassBuf is %u bytes, UNC_PASSWORD_MAX %d\n",
           (unsigned)sizeof gT.buf, UNC_PASSWORD_MAX);
    for (i = 0; i < UNC_PASSWORD_MAX; i++) {
        want[i] = (unsigned char)('!' + i);
        if (type_key(want[i]) != 0) {
            printf("pass-filter: character %d refused\n", i + 1);
            bad = 1;
        }
        if (!canary_ok()) {
            printf("pass-filter: character %d wrote past the buffer\n", i + 1);
            bad = 1;
            break;
        }
    }
    if (gT.buf[0] != UNC_PASSWORD_MAX
        || memcmp(gT.buf + 1, want, UNC_PASSWORD_MAX) != 0) {
        printf("pass-filter: after %d characters the buffer holds %u\n",
               UNC_PASSWORD_MAX, gT.buf[0]);
        bad = 1;
    }
    /* The 65th: swallowed (true), the length unchanged, nothing written. */
    if (type_key('Z') != 1 || gT.buf[0] != UNC_PASSWORD_MAX || !canary_ok()) {
        printf("pass-filter: character %d was not refused cleanly\n",
               UNC_PASSWORD_MAX + 1);
        bad = 1;
    }
    puts(bad ? "pass-filter: FAILED" : "pass-filter: OK");
    return bad;
}
