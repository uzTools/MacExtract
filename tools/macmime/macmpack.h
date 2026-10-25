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

/* macfile.c reads `vMAttrib` of GetVolParmsInfoBuffer, bit
 * bHasDesktopMgr, only after PBHGetVolParmsSync has returned noErr —
 * which needs the Desktop Manager, i.e. System 7 or an AppleShare volume.
 * Both come from Multiverse.h since multiversal 580f330 (Retro68 #327,
 * 0cbd3cb): Apple's layout, `vMAttrib` after a 2-byte `vMVersion`, and
 * bit 12. Until 2026-10-25 this header guessed them, `vMAttrib` at offset
 * 0 and bit 4, both wrong, which held only because the call fails on the
 * System 6.0.8 this tool runs on; `tools/vmac/macmime.py --check` still
 * requires the comment entry it produces there to be empty. */

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
