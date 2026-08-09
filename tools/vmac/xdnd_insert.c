/*
 * xdnd_insert.c — drop a disk image onto a running Mini vMac, so that a
 * volume appears WHILE the Mac is running.
 *
 * Why this exists: Mini vMac's X11 build takes a disk at runtime through
 * exactly one door. Its control mode (Control-held) offers magnify, full
 * screen, reset, interrupt, quit and speed — no "open disk" — and it is
 * built here with `NeedRequestInsertDisk 0` and `EnableDragDrop 1`. So
 * the only runtime path is XDND, and `ParseOneUri` turns a `file:` URI
 * into `Sony_Insert1a`, which is the insert (src/OSGLUXWN.c in the
 * Mini vMac source `setup.sh` fetches).
 *
 * There is no window manager and no file manager on the harness display,
 * so there is nothing to drag FROM. This is that missing half: a minimal
 * XDND source, enough of the protocol to make one drop happen.
 *
 *     cc -o xdnd_insert xdnd_insert.c -lX11
 *     ./xdnd_insert /path/to/disk.dsk            # finds the window itself
 *     ./xdnd_insert /path/to/disk.dsk 0x1400003  # or name it
 *
 * Exits nonzero, with a reason on stderr, if no XdndAware window is
 * found or the target never acknowledges the drop — a silent success
 * here would be indistinguishable from a Mac that ignored the disk,
 * which is the thing being tested.
 *
 * License: LGPL-2.1-or-later, as the rest of this repository.
 */
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>

static Display *dpy;
static Atom XA_XdndAware, XA_XdndEnter, XA_XdndPosition, XA_XdndStatus;
static Atom XA_XdndDrop, XA_XdndFinished, XA_XdndSelection;
static Atom XA_XdndActionCopy, XA_UriList;

/* The deepest window under `w` that advertises XdndAware. Mini vMac sets
 * it on its main window; with no window manager there is no reparenting
 * to confuse this, but recursion costs nothing and survives one. */
static Window find_aware(Window w, int depth)
{
    Atom type;
    int fmt;
    unsigned long n, after;
    unsigned char *prop = NULL;
    Window root, parent, *kids = NULL, found = None;
    unsigned int nkids, i;

    if (depth > 8) return None;
    if (XGetWindowProperty(dpy, w, XA_XdndAware, 0, 1, False, AnyPropertyType,
                           &type, &fmt, &n, &after, &prop) == Success && prop) {
        XFree(prop);
        if (n > 0) return w;
    }
    if (!XQueryTree(dpy, w, &root, &parent, &kids, &nkids)) return None;
    for (i = 0; i < nkids && found == None; i++)
        found = find_aware(kids[i], depth + 1);
    if (kids) XFree(kids);
    return found;
}

static void send_msg(Window target, Window src, Atom type,
                     long d1, long d2, long d3, long d4)
{
    XEvent e;
    memset(&e, 0, sizeof e);
    e.xclient.type = ClientMessage;
    e.xclient.display = dpy;
    e.xclient.window = target;
    e.xclient.message_type = type;
    e.xclient.format = 32;
    e.xclient.data.l[0] = (long)src;
    e.xclient.data.l[1] = d1;
    e.xclient.data.l[2] = d2;
    e.xclient.data.l[3] = d3;
    e.xclient.data.l[4] = d4;
    XSendEvent(dpy, target, False, NoEventMask, &e);
    XFlush(dpy);
}

int main(int argc, char **argv)
{
    Window target, src;
    char abs[PATH_MAX], uri[PATH_MAX + 16];
    XEvent ev;
    int served = 0, finished = 0, tries;

    if (argc < 2) {
        fprintf(stderr, "usage: xdnd_insert <disk-image> [window-id]\n");
        return 2;
    }
    if (!realpath(argv[1], abs)) {
        perror("xdnd_insert: realpath");
        return 2;
    }
    /* Mini vMac skips "file://<host>" and keeps the path from the first
     * '/', so an absolute path is all that has to survive. No escaping:
     * it un-escapes %XX, and the harness controls these names. */
    snprintf(uri, sizeof uri, "file://%s\r\n", abs);

    if (!(dpy = XOpenDisplay(NULL))) {
        fprintf(stderr, "xdnd_insert: cannot open DISPLAY\n");
        return 1;
    }
    XA_XdndAware      = XInternAtom(dpy, "XdndAware", False);
    XA_XdndEnter      = XInternAtom(dpy, "XdndEnter", False);
    XA_XdndPosition   = XInternAtom(dpy, "XdndPosition", False);
    XA_XdndStatus     = XInternAtom(dpy, "XdndStatus", False);
    XA_XdndDrop       = XInternAtom(dpy, "XdndDrop", False);
    XA_XdndFinished   = XInternAtom(dpy, "XdndFinished", False);
    XA_XdndSelection  = XInternAtom(dpy, "XdndSelection", False);
    XA_XdndActionCopy = XInternAtom(dpy, "XdndActionCopy", False);
    XA_UriList        = XInternAtom(dpy, "text/uri-list", False);

    if (argc > 2) {
        target = (Window)strtoul(argv[2], NULL, 0);
    } else {
        target = find_aware(DefaultRootWindow(dpy), 0);
        if (target == None) {
            fprintf(stderr, "xdnd_insert: no XdndAware window on this "
                            "display — is the emulator running?\n");
            return 1;
        }
    }

    src = XCreateSimpleWindow(dpy, DefaultRootWindow(dpy), 0, 0, 1, 1, 0, 0, 0);
    XSelectInput(dpy, src, PropertyChangeMask);
    XSetSelectionOwner(dpy, XA_XdndSelection, src, CurrentTime);
    if (XGetSelectionOwner(dpy, XA_XdndSelection) != src) {
        fprintf(stderr, "xdnd_insert: could not own XdndSelection\n");
        return 1;
    }

    /* Version 5, one type, offered in data.l[2]. */
    send_msg(target, src, XA_XdndEnter, (5L << 24), (long)XA_UriList, 0, 0);
    send_msg(target, src, XA_XdndPosition, 0, (100L << 16) | 100L,
             CurrentTime, (long)XA_XdndActionCopy);
    send_msg(target, src, XA_XdndDrop, 0, CurrentTime, 0, 0);

    /* Serve the selection, then wait to be told the drop was taken. */
    for (tries = 0; tries < 400 && !finished; tries++) {
        while (XPending(dpy)) {
            XNextEvent(dpy, &ev);
            if (ev.type == SelectionRequest) {
                XSelectionRequestEvent *r = &ev.xselectionrequest;
                XEvent n;
                if (r->target == XA_UriList) {
                    XChangeProperty(dpy, r->requestor, r->property,
                                    XA_UriList, 8, PropModeReplace,
                                    (unsigned char *)uri, (int)strlen(uri));
                    served = 1;
                }
                memset(&n, 0, sizeof n);
                n.xselection.type = SelectionNotify;
                n.xselection.display = dpy;
                n.xselection.requestor = r->requestor;
                n.xselection.selection = r->selection;
                n.xselection.target = r->target;
                n.xselection.property = served ? r->property : None;
                n.xselection.time = r->time;
                XSendEvent(dpy, r->requestor, False, NoEventMask, &n);
                XFlush(dpy);
            } else if (ev.type == ClientMessage
                       && ev.xclient.message_type == XA_XdndFinished) {
                finished = 1;
            }
        }
        usleep(25000);
    }

    XDestroyWindow(dpy, src);
    XCloseDisplay(dpy);
    if (!served) {
        fprintf(stderr, "xdnd_insert: the target never asked for the "
                        "file list — nothing was inserted\n");
        return 1;
    }
    if (!finished)
        fprintf(stderr, "xdnd_insert: served the drop but saw no "
                        "XdndFinished; continuing\n");
    return 0;
}
