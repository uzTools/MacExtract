/* macmpack.h — the two declarations `reference/mpack/macfile.c` includes
 * this header for, and nothing else.
 *
 * WHY A SHIM. macfile.c is compiled here VERBATIM out of the read-only
 * reference tree: it is the Macintosh port of mpack, and
 * `encode_applefile()` is the function that laid out every
 * `application/applefile` part a Macintosh ever mailed. Its own
 * macmpack.h is the whole application's header — windows, TCP, Internet
 * Config, a dialog layer — none of which this tool has or wants. It
 * needs `copy_buf` and `watch` from it, so those are what this provides,
 * along with the Toolbox headers macfile.c expects to have been included
 * already.
 *
 * Placed on the include path AHEAD of reference/mpack, so `#include
 * "macmpack.h"` finds this one. reference/ is never modified.
 */
#ifndef MACMIME_MACMPACK_H
#define MACMIME_MACMPACK_H

#include <Files.h>
#include <OSUtils.h>
#include <Quickdraw.h>
#include <Memory.h>

/* Retro68's headers carry the trap under its later name. Same trap
 * (_DateToSeconds, 0xA9C7 — Multiverse.h); Date2Secs is what the
 * Universal Interfaces of macfile.c's era called it. */
#define Date2Secs DateToSeconds

/* macfile.c reads ONE field of this, `vMAttrib`, and only after
 * PBHGetVolParmsSync has returned noErr — which needs the Desktop
 * Manager, i.e. System 7 or an AppleShare volume. This tool runs on
 * System 6.0.8, where that call fails and the field is never read.
 *
 * Retro68 has no GetVolParmsInfoBuffer and no copy of Inside Macintosh:
 * Files is in reference/, so the layout below is NOT transcribed from
 * anything: it is an opaque buffer big enough for the call, with the one
 * named field macfile.c mentions. That is sound only for as long as the
 * call keeps failing, so the harness CHECKS it rather than assuming:
 * `tools/vmac/macmime.py --check` requires the produced applefile's
 * ENT_COMMENT entry to be 0 bytes long, which is what a failed lookup
 * produces. If that check ever fires, this struct is the first thing to
 * distrust — and the fix is a real reference, not a guess. */
#define bHasDesktopMgr 4
typedef struct GetVolParmsInfoBuffer {
    long vMAttrib;
    char opaque[124];
} GetVolParmsInfoBuffer;

/* buffer for copy operations — the real macmpack.h's own size */
#define COPY_BUFSIZE 1024
extern char copy_buf[COPY_BUFSIZE];

/* `decode_applefile()` sits in the same file and is compiled with it;
 * this tool never calls it. These two are what IT needs: the chat state
 * the real macmpack.h declares, and the arrow cursor, which classic
 * QuickDraw keeps in the `qd` globals rather than in a name of its own. */
extern short didchat;
#define arrow qd.arrow

/* watch cursor — declared because macmpack.h declares it; macfile.c's
 * encode_applefile() never touches it. */
extern Cursor watch;

#endif
