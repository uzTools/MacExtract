#!/usr/bin/env python3
"""macclock.py — the emulated Mac's own clock and screen, read from the host.

Mini vMac keeps the emulated RAM in one block of its own address space, in
the Mac's byte order (src/ENDIANAC.h: `do_get_mem_long` swaps on a
little-endian host, so RAM holds big-endian longs). A harness that started
the emulator is its ancestor, which is what Yama's ptrace_scope 1 asks of a
reader of /proc/<pid>/mem — so the host can read, without stopping the
emulator and without writing a file, two things at any instant:

  - `Ticks` ($16A), the count of vertical-blanking interrupts since boot:
    the Mac's own clock, 60.15 per emulated second;
  - the 21,888-byte screen buffer at `ScrnBase` ($824): what the Mac has
    DRAWN, before Mini vMac copies it to the X window.

Source for the three addresses: Retro68's multiversal
CIncludes/Multiverse.h — `LMGetTicks() (*(ULONGINT*)0x016A)`,
`LMGetMemTop() (*(Ptr*)0x0108)`, `LMGetScrnBase() (*(Ptr*)0x0824)`.
The 60.15 Hz is Mini vMac's own tick (MyInvTimeStep, 16,626 us, in
src/OSGLUXWN.c) and a Mac Plus's vertical retrace.

`Watch` turns that into a stopwatch: it polls both at `hz` and keeps a
timeline of the samples at which the screen changed, each stamped with the
host's monotonic clock AND the Mac's Ticks. A duration is then read in
emulated ticks, which is Mac Plus time whatever the host was doing, and in
host seconds beside it; the two agree only while Mini vMac keeps real time,
so their ratio is printed with every reading.

Why ticks and not the host clock: at 1x Mini vMac runs one emulated tick per
16.6 ms of host time, catches up when it falls behind by up to 8 ticks, and
DROPS the rest (PROGMAIN.c, RunEmulatedTicksToTrueTime: "emulation not fast
enough"). A loaded host therefore stretches host seconds but not ticks — a
run on a busy machine reads long on a host clock and right on this one.

What it cannot see
------------------
- **Whether Mini vMac's 68000 is a real 68000's speed.** A tick is a fixed
  budget of emulated instructions; how close that is to a real Mac Plus is
  the emulator's fidelity, and nothing on this machine can measure it
  (MANUAL_TESTS.md has the hardware).
- **Disk time.** Mini vMac's disk driver completes inside one emulated
  instruction; a real floppy or SCSI disk is not free.
- **Ticks lost while interrupts are masked.** `Ticks` counts the VBL
  interrupts the Mac took; one masked for longer than a tick is one tick
  short. The calibration (`clockcal`) reads ticks against TickCount, the
  same variable, so it cannot see this either.
- **Anything that is not on the screen.** "Finished" is the last change to
  the screen buffer before it held still for `quiet` seconds. Work that
  continues without drawing — Expander's writes sitting in the File
  Manager's cache until it quits — is after the end this sees.
- **The cursor is in the screen buffer.** A Mac Plus draws its own pointer,
  so a pointer the Mac moves or animates is a change. The harnesses park the
  X pointer; the emulated one stays where it was last put.
"""
import os
import struct
import time

TICKS = 0x016A
MEMTOP = 0x0108
SCRNBASE = 0x0824
SCREEN_BYTES = 512 * 342 // 8
TICK_HZ = 1e6 / 16626.0                  # Mini vMac MyInvTimeStep, 60.15 Hz


def emulator_pid(proc, name="minivmac", timeout=10.0):
    """The emulator under a guard.spawn() process (which is `timeout`)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        todo = [proc.pid]
        while todo:
            p = todo.pop()
            try:
                if open(f"/proc/{p}/comm").read().strip() == name:
                    return p
                for t in os.listdir(f"/proc/{p}/task"):
                    kids = open(f"/proc/{p}/task/{t}/children").read().split()
                    todo += [int(k) for k in kids]
            except OSError:
                pass
        time.sleep(0.1)
    raise SystemExit(f"macclock: no {name} under pid {proc.pid}")


class MacMemory:
    """Read-only window on one Mini vMac's emulated RAM."""

    def __init__(self, pid, ram_size, timeout=60.0):
        self.pid = pid
        self.ram_size = ram_size
        self.fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
        self.base = None
        deadline = time.time() + timeout
        while self.base is None:
            self.base = self._find()
            if self.base is None:
                if time.time() > deadline:
                    raise SystemExit("macclock: emulated RAM not found — "
                                     "has the Mac booted?")
                time.sleep(0.5)
        self.scrn = self.long(SCRNBASE)

    def _find(self):
        """The host address of emulated $0, located by what the ROM leaves
        in low memory once it has sized RAM: MemTop is the RAM size and
        ScrnBase is $5900 below it (a Mac Plus's main screen buffer and
        sound buffer at the top of RAM)."""
        want = struct.pack(">II", self.ram_size, self.ram_size - 0x5900)
        for line in open(f"/proc/{self.pid}/maps"):
            f = line.split()
            lo, hi = (int(x, 16) for x in f[0].split("-"))
            if "rw" not in f[1] or hi - lo < self.ram_size or len(f) > 5 \
                    and f[5].startswith("/"):
                continue
            try:
                blob = os.pread(self.fd, hi - lo, lo)
            except OSError:
                continue
            memtop = want[:4]
            i = blob.find(memtop)
            while i >= 0:
                o = i - MEMTOP
                if o >= 0 and o + self.ram_size <= len(blob) and \
                        blob[o + SCRNBASE:o + SCRNBASE + 4] == want[4:]:
                    return lo + o
                i = blob.find(memtop, i + 1)
        return None

    def read(self, addr, n):
        return os.pread(self.fd, n, self.base + addr)

    def long(self, addr):
        return struct.unpack(">I", self.read(addr, 4))[0]

    def ticks(self):
        return self.long(TICKS)

    def screen(self):
        return self.read(self.scrn, SCREEN_BYTES)

    def close(self):
        os.close(self.fd)


class Watch:
    """Poll screen and Ticks; keep only the samples where the screen changed.

    Each sample is (host monotonic seconds, Ticks). Poll cost is one 21 KB
    pread and one hash, ~0.1 ms, so 50 Hz is ~0.5 % of a core.
    """

    def __init__(self, mem, hz=50.0):
        self.mem, self.dt = mem, 1.0 / hz
        self.prev = None

    def sample(self):
        s = self.mem.screen()
        return time.monotonic(), self.mem.ticks(), hash(s), s

    def mark(self):
        """(host, ticks) now — taken just before an action is sent."""
        t, k, h, _ = self.sample()
        self.prev = h
        return t, k

    def until_quiet(self, quiet, timeout, snap=None):
        """Poll until the screen has not changed for `quiet` host seconds.

        Returns (changes, timed_out): every change seen, as (host, ticks),
        oldest first. The LAST is the end of the work; the first is the
        Mac's response to the action. `snap` is (seconds, callable): called
        once, that long after the start — one evidence screenshot, which
        costs the emulator ~0.1 s of CPU and both applications the same."""
        start = time.monotonic()
        changes = []
        last = start
        while True:
            time.sleep(self.dt)
            if snap and time.monotonic() - start >= snap[0]:
                snap[1]()
                snap = None
            t, k, h, _ = self.sample()
            if h != self.prev:
                self.prev = h
                changes.append((t, k))
                last = t
            elif t - last >= quiet:
                return changes, False
            if t - start > timeout:
                return changes, True


def reading(action, changes):
    """The duration from `action` to the last change, both clocks.

    Returns a dict: ticks, mac_s (ticks / 60.15), host_s, ratio (host time
    per emulated time; 1.00 is real time), first_s (the Mac's first visible
    response, in Mac seconds), n (changes seen)."""
    if not changes:
        return None
    (t0, k0), (t1, k1) = action, changes[-1]
    dk = (k1 - k0) & 0xFFFFFFFF
    mac = dk / TICK_HZ
    host = t1 - t0
    return {"ticks": dk, "mac_s": round(mac, 3), "host_s": round(host, 3),
            "ratio": round(host / mac, 4) if mac else None,
            "first_s": round(((changes[0][1] - k0) & 0xFFFFFFFF) / TICK_HZ, 3),
            "n": len(changes)}
