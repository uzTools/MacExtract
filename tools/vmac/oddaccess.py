#!/usr/bin/env python3
"""oddaccess.py — a Mini vMac that reports what a real 68000 would bomb on.

A 68000 raises an address error (vector 3, the System's "ID = 02") on a word
or long access at an odd address and on a jump to an odd address. Mini
vMac's 68000 core has no vector-3 path at all: `get_word_ext` and
`put_word_ext` in its `src/MINEM68K.c` split an odd access into two byte
accesses and carry on. So no emulator tier here can bomb on one, and the
Mac Plus that bombed on v0.45.0's destination dialog never did under
emulation (DECISIONS.md 2026-11-14, *the gray at an odd address*).

This copies a configured emulator directory, `$UNC_VMAC_HOME/<emu>`, to
`<emu>-ae`, patches its core and rebuilds it. The patched emulator still
completes every odd access, as before, and also appends one line per access
(the first 400) to the file named by `$MV_ODDLOG`, or to stderr:

    ODD R addr=A0065BDF pc=00409826 D0=... A7=...

R and W are an odd word or long read or write (a long is logged as its two
word halves), J a jump, return or exception to an odd address, B a short
branch by an odd displacement. `pc` is the first word of the instruction
being executed, so a ROM address (0x400000 up on a Plus) means a trap was
handed an odd pointer; the registers say by whom.

    tools/vmac/oddaccess.py mv-1M-1d1          # builds $V/mv-1M-1d1-ae
    MV_ODDLOG=$PWD/.tmp/odd.log tools/vmac/run.py --emu mv-1M-ae ...

Every harness passes its environment to the emulator, so any of them takes
`--emu <emu>-ae`. **No log file at all is the passing result**; the control
is v0.45.0's `dist/MacExtract-800K.img` driven to its destination dialog,
which logs four reads from PC 0x409826 (`_PenPat`'s `move.l (a1)+`).

What it CANNOT see: a fault on a path the run does not take, and anything
a 68000 faults on that is not an alignment error (a bus error, an
illegal instruction Mini vMac happens to implement). Odd accesses Mini
vMac's own glue makes outside the 68000 core are not logged and would
not be faults.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402

HDR = r'''
#include <stdio.h>
#include <stdlib.h>
static ui5r ae_ipc;
static FILE *ae_f;
static int ae_n;

LOCALPROC ae_note(int kind, ui5r addr)
{
	int i;
	if (ae_f == NULL) {
		char *e = getenv("MV_ODDLOG");
		ae_f = e ? fopen(e, "a") : stderr;
		if (ae_f == NULL) ae_f = stderr;
	}
	if (ae_n++ >= 400) return;
	fprintf(ae_f, "ODD %c addr=%08lX pc=%08lX", kind,
		(unsigned long)addr, (unsigned long)ae_ipc);
	for (i = 0; i < 16; ++i)
		fprintf(ae_f, " %c%d=%08lX", i < 8 ? 'D' : 'A', i & 7,
			(unsigned long)V_regs.regs[i]);
	fprintf(ae_f, "\n");
	fflush(ae_f);
}
'''

# (anchor, text inserted after it). Each anchor must occur exactly once, so
# a Mini vMac whose core has moved on fails here rather than half-patched.
EDITS = [
    ("LOCALINLINEFUNC CPTR m68k_getpc(void)\n{\n"
     "\treturn V_regs.pc + (V_pc_p - V_regs.pc_pLo);\n}\n", HDR),
    ("\tdo {\n\t\tV_regs.CurDecOpY = y;\n",
     "\t\tae_ipc = m68k_getpc() - 2;\n"),
    ("LOCALFUNC ui5r my_reg_call get_word_ext(CPTR addr)\n{\n\tui5r Data;\n\n"
     "\tif (0 != (addr & 0x01)) {\n", "\t\tae_note('R', addr);\n"),
    ("LOCALPROC my_reg_call put_word_ext(CPTR addr, ui5r w)\n{\n"
     "\tif (0 != (addr & 0x01)) {\n", "\t\tae_note('W', addr);\n"),
    ("LOCALPROC my_reg_call m68k_setpc(CPTR newpc)\n{\n",
     "\tif (newpc & 1) ae_note('J', newpc);\n"),
    ("\tsi5r offset = (si5r)(si3b)(ui3b)(V_regs.CurDecOpY.v[1].ArgDat);\n"
     "\tui3p s = V_pc_p + offset;\n",
     "\tif (offset & 1) ae_note('B', m68k_getpc() + offset);\n"),
]


def patch(src):
    s = open(src).read()
    if "ae_note" in s:
        raise SystemExit(f"oddaccess: {src} is already patched")
    for anchor, text in EDITS:
        if s.count(anchor) != 1:
            raise SystemExit(f"oddaccess: anchor not found once in {src}: "
                             f"{anchor.splitlines()[0]!r}")
        s = s.replace(anchor, anchor + text)
    open(src, "w").write(s)


def main():
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        raise SystemExit(__doc__)
    emu = sys.argv[1]
    src = os.path.join(R.VMAC_HOME, emu)
    dst = src + "-ae"
    if not os.path.exists(os.path.join(src, "Makefile")):
        raise SystemExit(f"oddaccess: no configured emulator at {src}")
    if "ae_note" in open(os.path.join(src, "src", "MINEM68K.c")).read():
        raise SystemExit(f"oddaccess: {src} is already patched")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)
    patch(os.path.join(dst, "src", "MINEM68K.c"))
    obj = os.path.join(dst, "bld", "MINEM68K.o")
    if os.path.exists(obj):
        os.remove(obj)
    subprocess.run(["make", "-C", dst], check=True, capture_output=True)
    print(f"oddaccess: {os.path.join(dst, 'minivmac')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
