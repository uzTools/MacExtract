/* mac_start.c — the application's entry point, in place of Retro68's.
 *
 * Retro68's `_start` relocates the image, registers its destructor walk
 * with `atexit`, runs the constructors, calls main and leaves through
 * newlib's `exit`. That last call is what links newlib's exit chain —
 * `exit`, `__call_exitprocs`, the `atexit` table, the stdio file array and
 * `_impure_data` — into an application that never opens a stdio stream and
 * has no constructor or destructor at all (tools/build_mac.sh fails the
 * build if one appears, since this entry would not run it). So this does
 * the one job of `_start` the application needs, the relocation, and leaves
 * the way Retro68's `_exit` does, through ExitToShell (DECISIONS.md
 * 2026-10-22, *the runtime the application did not need*).
 *
 * It also gives back the relocation table. The application is linked with
 * Elf2Mac's --mac-single: one CODE resource holding code, data and, after
 * them, the relocations Retro68Relocate applies once at launch. Nothing
 * reads them again, and the resource is locked for the life of the run, so
 * without this they would sit in the heap until ExitToShell.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include <Memory.h>
#include <Resources.h>
#include <SegLoad.h>
#include <stdint.h>
#include <Retro68Runtime.h>

int main(void);

/* The linker script's bounds of the image: code, then data. */
extern uint8_t _stext[], _edata[];

/* CODE 1 is a 4-byte header (Elf2Mac's word 0, word 1), the image, and
 * the relocations. Shrink it to the first two, and only when the handle is
 * provably the block the image runs from: GetResource answers the copy the
 * Segment Loader already read, with no disk access, and RecoverHandle of
 * the address four bytes before `_stext` must name that same handle.
 * Anything else leaves the resource as it is, which costs the 1.4 KB and
 * nothing more. Shrinking a block never moves it, locked or not. */
static void give_back_relocations(void)
{
    Handle code = GetResource('CODE', 1);
    long keep = 4 + (long)(_edata - _stext);
    if (code == NULL || *code == NULL) return;
    if (RecoverHandle((Ptr)(_stext - 4)) != code) return;
    if (GetHandleSize(code) <= keep) return;
    SetHandleSize(code, keep);
}

void unc_mac_start(void)
{
    /* Before this returns the image holds link-time addresses: nothing
     * here may touch a global or call by address until it has. The macro
     * reaches Retro68Relocate PC-relatively, as Retro68's own _start does. */
    RETRO68_RELOCATE();
    give_back_relocations();
    main();
    ExitToShell();
}
