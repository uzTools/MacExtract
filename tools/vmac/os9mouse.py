#!/usr/bin/env python3
"""os9mouse.py — drive the Mac OS 9 guest with its POINTER.

`os9.py` drives this guest from the keyboard, and for fixture runs it should:
that route needs no coordinates. What it cannot do is operate an application —
click a checkbox, walk an installer — which is what this module is for, and
what produced the StuffIt 5 encryption specimens.

How to use it: tools/vmac/README.md, *Mac OS 9 with the pointer*.
Why the older "the pointer does not work" reading was wrong, and what that
cost: BLOCKERS.md, *Withdrawn claims*, and DECISIONS.md 2026-08-26.

Four measured facts this code is built on, kept here because they are what the
code would otherwise look arbitrary for:

  * the absolute `usb-tablet` moves the cursor 0 px — Mac OS 9 has no driver
    for it, so `mouse_set` must leave a RELATIVE device active;
  * a relative delta saturates at ±63 px per ADB packet, hence `step()`;
  * the menu-bar clock (`CLOCK_BOX`) and a blinking text caret both survive
    frame-differencing, hence `largest_blob` — an arrow is ~100 changed
    pixels, a caret a sliver;
  * `goto()` costs ~40 s, longer than a sticky menu stays open: use Command
    keys, and match a moving button's LABEL rather than its position
    (`find_not_yet`).
"""
import os, re, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                          # noqa: E402
import guard                                            # noqa: E402

CACHE = os.path.join(os.path.dirname(R.VMAC_HOME), "sit5")
MASTER = os.path.join(os.path.dirname(R.VMAC_HOME), "qemu-ppc", "MacOS9.img")
# The StuffIt Deluxe 5.0.1 CD, fetched by tools/vmac/spacesaver.py --setup.
ISO = os.path.join(R.VMAC_HOME, "spacesaver", "STUFFIT_DLX_SS_501.ISO")
OVERLAY = os.path.join(CACHE, "os9-sit.qcow2")
XFER = os.path.join(CACHE, "xfer.img")
MON = os.path.join(CACHE, "mon.sock")
SHOTS = os.path.join(CACHE, "shots")
W, H = 1024, 768
PARK = (1000, 740)
# The menu-bar clock and the application menu, which repaint on their own.
# Excluded permanently rather than per-call: locating the cursor ON the menu
# bar is necessary (menus are up there) and the clock is the only thing up
# there that moves by itself.
CLOCK_BOX = (820, 0, W, 21)
DONE_BUTTON = (692, 320)          # the "did not shut down properly" alert


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)


def readppm(path):
    d = open(path, "rb").read()
    if not d.startswith(b"P6"):
        raise RuntimeError("not a PPM: " + path)
    tok, i = [], 2
    while len(tok) < 3:
        while i < len(d) and d[i:i+1].isspace(): i += 1
        if d[i:i+1] == b"#":
            while d[i:i+1] != b"\n": i += 1
            continue
        j = i
        while j < len(d) and not d[j:j+1].isspace(): j += 1
        tok.append(int(d[i:j])); i = j
    i += 1
    w, h, _ = tok
    return (w, h, d[i:i + w*h*3])


def diff(a, b, ignore=None, thresh=24, box=None, mask=None):
    w, h, pa = a
    _, _, pb = b
    n = 0; x0 = y0 = 1 << 30; x1 = y1 = -1
    ys = range(box[1], box[3]) if box else range(h)
    xs = range(box[0], box[2]) if box else range(w)
    for y in ys:
        row = y * w * 3
        for x in xs:
            if mask is not None and mask[y * w + x]:
                continue
            k = row + x * 3
            if abs(pa[k]-pb[k]) + abs(pa[k+1]-pb[k+1]) + abs(pa[k+2]-pb[k+2]) < thresh:
                continue
            if ignore and abs(x-ignore[0]) < 40 and abs(y-ignore[1]) < 40:
                continue
            n += 1
            x0 = min(x0, x); x1 = max(x1, x); y0 = min(y0, y); y1 = max(y1, y)
    return (n, None) if x1 < 0 else (n, (x0, y0, x1, y1))


def noise_mask(frames, thresh=24):
    """Pixels that change on their own: the menu-bar clock, a blinking text
    caret, a progress bar, an animation. Anything in here is worthless for
    locating the cursor, and leaving it in is what sent one goto() to the
    clock at (899,5) and made another give up entirely inside a dialog whose
    caret was blinking. Built from three frames of an IDLE screen."""
    w, h, _ = frames[0]
    mask = bytearray(w * h)
    for a, b in zip(frames, frames[1:]):
        pa, pb = a[2], b[2]
        for i in range(w * h):
            k = i * 3
            if abs(pa[k]-pb[k]) + abs(pa[k+1]-pb[k+1]) + abs(pa[k+2]-pb[k+2]) >= thresh:
                mask[i] = 1
    return mask


def largest_blob(points, gap=6):
    """Split changed pixels into clusters and return the biggest.

    Even after masking and the three-frame test, a blinking text caret can
    survive -- its phase can align with the sampling. But an arrow cursor is
    a ~16x16 blob of roughly a hundred pixels and a caret is a 1x12 sliver,
    so the largest cluster is the cursor. Without this, every dialog with a
    text field made goto() fail with "cursor not seen"."""
    todo = set(points)
    best = None
    while todo:
        seed = todo.pop()
        blob = [seed]
        frontier = [seed]
        while frontier:
            x, y = frontier.pop()
            for dx in range(-gap, gap + 1):
                for dy in range(-gap, gap + 1):
                    q = (x + dx, y + dy)
                    if q in todo:
                        todo.discard(q)
                        blob.append(q)
                        frontier.append(q)
        if best is None or len(blob) > len(best):
            best = blob
    return best


def diff_points(a, b, box, ignore=None, thresh=24, mask=None):
    """The set of (x,y) that differ, inside `box`."""
    w, h, pa = a
    _, _, pb = b
    out = set()
    for y in range(box[1], box[3]):
        row = y * w * 3
        for x in range(box[0], box[2]):
            if mask is not None and mask[y*w + x]:
                continue
            k = row + x*3
            if abs(pa[k]-pb[k]) + abs(pa[k+1]-pb[k+1]) + abs(pa[k+2]-pb[k+2]) < thresh:
                continue
            if ignore and abs(x-ignore[0]) < 40 and abs(y-ignore[1]) < 40:
                continue
            if (CLOCK_BOX[0] <= x < CLOCK_BOX[2]
                    and CLOCK_BOX[1] <= y < CLOCK_BOX[3]):
                continue
            out.add((x, y))
    return out


NAG_BUTTONS = [(478, 495), (661, 495), (478, 524), (661, 524)]
NOT_YET_TPL = os.path.join(CACHE, "notyet.tpl")


def find_not_yet(frame):
    """Which of DropStuff's four nag buttons is "Not Yet" THIS time?

    The nag shuffles its four buttons on every appearance, so a fixed
    coordinate eventually hits "Order Info" instead -- which opens an order
    form save dialog and swallows every keystroke meant for the password.
    That is exactly what wrecked one specimen cycle. So the label is matched
    against a template cut from a frame where its position was known."""
    import os
    if not os.path.exists(NOT_YET_TPL):
        return None
    tpl = open(NOT_YET_TPL, "rb").read()
    tw, th = 100, 18
    w, h, p = frame
    best = None
    for cx, cy in NAG_BUTTONS:
        x0, y0 = cx - 48, cy - 9
        score = 0
        for j in range(th):
            row = (y0 + j) * w
            for i in range(tw):
                score += abs(p[(row + x0 + i) * 3] - tpl[j * tw + i])
        score /= (tw * th)
        if best is None or score < best[0]:
            best = (score, (cx, cy))
    return best


class Pointer:
    """Closed-loop positioning, against anything this repository can
    screenshot and send monitor commands to.

    `Mac` is one such guest; `os9.py`'s `Qemu` is another, and it needs the
    pointer for exactly one thing — clicking the progress dialog's Cancel
    button, which no keyboard route reaches. A second copy of the four facts
    in this module's docstring would be a second copy to get wrong, so the
    algorithm lives here and both callers hand it their own plumbing:

      * `burst(cmds, gap=, wait=)` — monitor commands down ONE connection,
        which is what keeps the two halves of a click inside the Mac's
        double-click threshold;
      * `frame(tag)` — a screenshot as `(w, h, pixels)`.
    """

    def __init__(self, burst, frame):
        self.burst = burst
        self.frame = frame
        self.pos = None

    def park(self):
        self.burst(["mouse_move 60 60"] * 45, gap=0.02)
        self.pos = (W - 1, H - 1)

    def step(self, dx, dy, size=40):
        cmds = []
        while dx or dy:
            sx = max(-size, min(size, dx)); sy = max(-size, min(size, dy))
            cmds.append(f"mouse_move {sx} {sy}")
            dx -= sx; dy -= sy
        self.burst(cmds, gap=0.02)

    def reference(self, tag="_ref"):
        """A frame with the cursor parked, plus a mask of what blinks."""
        f = [self.frame(tag)]
        for i in (1, 2):
            time.sleep(0.8)
            f.append(self.frame(tag))
        return f[-1], noise_mask(f)

    def locate(self, ref, predicted=None, radius=260, tag="loc"):
        """Where is the cursor? Only pixels that differ from `ref` in THREE
        successive frames count.

        A cursor is static; a blinking caret, a ticking clock and a spinning
        progress bar are not. Two frames are not enough -- the caret's phase
        can alias with the sampling interval, which is exactly how a dialog
        with a text field defeated the two-frame version. The search is also
        confined to a box around where the step should have landed, which
        makes it both faster and blind to anything moving elsewhere."""
        base = ref[0] if isinstance(ref, tuple) and len(ref) == 2 else ref
        mask = ref[1] if isinstance(ref, tuple) and len(ref) == 2 else None
        if predicted:
            box = (max(0, predicted[0]-radius), max(0, predicted[1]-radius),
                   min(W, predicted[0]+radius), min(H, predicted[1]+radius))
        else:
            box = (0, 0, W, H)
        hits = None
        cur = None
        for i in range(3):
            if i:
                time.sleep(0.6)
            cur = self.frame(tag)
            pts = diff_points(base, cur, box, ignore=PARK, mask=mask)
            hits = pts if hits is None else (hits & pts)
            if not hits:
                return (None, cur)
        blob = largest_blob(hits)
        if not blob:
            return (None, cur)
        xs = [p[0] for p in blob]; ys = [p[1] for p in blob]
        if max(xs)-min(xs) > 64 or max(ys)-min(ys) > 64:
            return (None, cur)
        return ((min(xs), min(ys)), cur)

    def goto(self, x, y, tries=6, verbose=True):
        """Closed-loop positioning: move, look, correct."""
        self.park()
        ref = self.reference("_ref")
        pos = self.pos
        for i in range(tries):
            self.step(x - pos[0], y - pos[1])
            got, _ = self.locate(ref, predicted=(x, y), tag="_loc")
            if got is None:
                if verbose: print(f"    goto({x},{y}): cursor not seen", flush=True)
                return None
            pos = got
            if abs(got[0]-x) <= 4 and abs(got[1]-y) <= 4:
                if verbose: print(f"    goto({x},{y}) -> {got}", flush=True)
                self.pos = got
                return got
        if verbose: print(f"    goto({x},{y}) -> closest {pos}", flush=True)
        self.pos = pos
        return pos

    def press(self, double=False, hold=0.08, settle=1.5):
        """Click where the cursor already IS, holding the button down for
        `hold` seconds.

        The hold is the whole reason this is not one 60 ms tap. An application
        that only pumps events from a progress callback dequeues a mouseDown
        up to a tick after it arrives, and `DialogSelect` then calls
        `TrackControl`, which asks whether the button is STILL down: a tap
        that is already over reads as a click that ended outside the button
        and returns no item. The Finder is fast enough not to care; the
        progress dialog is not necessarily."""
        cmds = []
        for i in range(2 if double else 1):
            cmds += ["mouse_button 1", "mouse_button 0"]
        self.burst(cmds, gap=hold, wait=settle)
        return True

    def click(self, x=None, y=None, double=False, settle=1.5, hold=0.08):
        if x is not None:
            if self.goto(x, y) is None:
                return False
        return self.press(double=double, hold=hold, settle=settle)


class Mac:
    """Either boots a guest, or ATTACHES to one already running.

    attach=True skips the launch and just connects to the monitor socket, so
    a long-lived guest can be driven by one short script after another. A
    boot is three minutes; attaching is instant, and an install is a dozen
    steps that each need a look at a screenshot before the next one."""

    # Hard seconds for the guest (tools/guard.py). A session here is driven
    # by hand, frame by frame, so the bound is generous; pass limit= for
    # more. A Python that exits takes its guest with it.
    LIMIT = 3 * 3600

    def __init__(self, cd=True, fresh=False, attach=False, xfer=True,
                 limit=None):
        self.ptr = Pointer(self.burst, self.shot)
        if attach:
            if not os.path.exists(MON):
                raise SystemExit("no guest is running (no monitor socket)")
            self.proc = None
            return
        os.makedirs(CACHE, exist_ok=True)
        os.makedirs(SHOTS, exist_ok=True)
        if fresh and os.path.exists(OVERLAY):
            os.remove(OVERLAY)
        if not os.path.exists(OVERLAY):
            r = sh("qemu-img", "create", "-f", "qcow2", "-F", "raw",
                   "-b", MASTER, OVERLAY)
            print(r.stdout.strip() or r.stderr.strip(), flush=True)
        if os.path.exists(MON):
            os.remove(MON)
        argv = ["qemu-system-ppc", "-M", "mac99,via=pmu", "-m", "512",
                "-boot", "c", "-g", f"{W}x{H}x32", "-display", "none",
                "-device", "usb-mouse",
                "-monitor", f"unix:{MON},server,nowait",
                "-drive", f"file={OVERLAY},format=qcow2,media=disk,index=0"]
        if xfer and os.path.exists(XFER):
            argv += ["-drive", f"file={XFER},format=raw,media=disk,index=1"]
        if cd:
            argv += ["-drive", f"file={ISO},format=raw,media=cdrom,index=2"]
        # Output to a log, not a pipe nobody drains; under guard.spawn,
        # with a hard limit, in a process group kill() takes whole.
        log = os.path.join(CACHE, "qemu.log")
        self.proc = None
        with open(log, "w") as f:
            self.proc = guard.spawn(argv, limit=limit or self.LIMIT,
                                    stdout=f, stderr=subprocess.STDOUT)
        try:
            for _ in range(240):
                if os.path.exists(MON):
                    try:
                        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        s.connect(MON); s.close(); break
                    except OSError:
                        pass
                if self.proc.poll() is not None:
                    with open(log, errors="replace") as f:
                        raise SystemExit("%s:\n%s" % (
                            guard.why(self.proc, "qemu"), f.read()))
                time.sleep(0.5)
            else:
                raise SystemExit("monitor never came up")
        except BaseException:
            self.kill()
            raise
        self.pos = None

    # ---- monitor plumbing -------------------------------------------
    def burst(self, cmds, gap=0.03, wait=0.4):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(MON); time.sleep(0.25)
        try: s.recv(65536)
        except OSError: pass
        for c in cmds:
            s.sendall((c + "\n").encode()); time.sleep(gap)
        time.sleep(wait); s.close()

    def ask(self, cmd, wait=1.0):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(MON); time.sleep(0.35)
        try: s.recv(65536)
        except OSError: pass
        s.sendall((cmd + "\n").encode()); time.sleep(wait)
        try: out = s.recv(1 << 16).decode(errors="replace")
        except OSError: out = ""
        s.close()
        return re.sub(r"\x1b\[[0-9;]*[A-Za-z]|[\x00-\x08\x0b-\x1f]", "", out)

    def shot(self, tag="scratch"):
        p = os.path.join(SHOTS, tag + ".ppm")
        if os.path.exists(p):
            os.remove(p)
        self.burst([f"screendump {p}"], wait=1.0)
        for _ in range(25):
            if os.path.exists(p) and os.path.getsize(p) > 100000:
                break
            time.sleep(0.3)
        return readppm(p)

    def png(self, tag, shoot=True):
        """Screenshot (unless told not to) and convert it for viewing.

        This used to only convert: a caller that had not taken a shot with
        the same tag got a path to a file that was never written, and one
        whole specimen cycle ran blind because of it."""
        if shoot:
            self.shot(tag)
        sh("convert", os.path.join(SHOTS, tag + ".ppm"),
           os.path.join(SHOTS, tag + ".png"))
        return os.path.join(SHOTS, tag + ".png")

    def key(self, *names, wait=0.35):
        for k in names:
            self.burst([f"sendkey {k}"], wait=wait)

    def typestr(self, s, wait=0.25):
        m = {" ": "spc", ".": "dot", "-": "minus", "/": "slash", "™": None}
        for ch in s:
            k = m.get(ch, ch)
            if k is None:
                continue
            if ch.isupper():
                self.burst([f"sendkey shift-{ch.lower()}"], wait=wait)
            else:
                self.burst([f"sendkey {k}"], wait=wait)

    # ---- pointer ----------------------------------------------------
    # The algorithm is Pointer's, above; these forward to it so the calls
    # documented in tools/vmac/README.md keep working unchanged.
    @property
    def pos(self):
        return self.ptr.pos

    @pos.setter
    def pos(self, v):
        self.ptr.pos = v

    def park(self):
        return self.ptr.park()

    def step(self, dx, dy, size=40):
        return self.ptr.step(dx, dy, size)

    def reference(self, tag="_ref"):
        return self.ptr.reference(tag)

    def locate(self, ref, predicted=None, radius=260, tag="loc"):
        return self.ptr.locate(ref, predicted=predicted, radius=radius, tag=tag)

    def goto(self, x, y, tries=6, verbose=True):
        return self.ptr.goto(x, y, tries=tries, verbose=verbose)

    def click(self, x=None, y=None, double=False, settle=1.5):
        return self.ptr.click(x, y, double=double, settle=settle)

    # ---- waiting ----------------------------------------------------
    def settle(self, tag="settle", floor=80, limit=420, quiet_px=3000, need=2):
        t0 = time.time(); prev = None; quiet = 0
        while time.time() - t0 < limit:
            time.sleep(12)
            cur = self.shot(tag)
            if prev is not None:
                n, _ = diff(prev, cur)
                print(f"  t+{time.time()-t0:.0f}s {n} px", flush=True)
                if time.time() - t0 > floor and n < quiet_px:
                    quiet += 1
                    if quiet >= need:
                        break
                else:
                    quiet = 0
            prev = cur
        return time.time() - t0

    def put_away(self, volume="sitwork"):
        """Unmount a volume from inside the guest, which FLUSHES it.

        The host cannot read what the guest has not written out, and this
        guest does not come back from Special > Shut Down under QEMU (the
        screen goes black and a monitor `system_reset` does not revive it).
        Selecting the volume and pressing Cmd-Y does flush it, and leaves the
        guest running for the next specimen."""
        self.click(500, 650, settle=1.5)          # focus the Finder desktop
        self.typestr(volume, wait=0.25)
        time.sleep(1.2)
        self.key("meta_l-y", wait=1.2)
        time.sleep(8)

    def kill(self):
        guard.reap(self.proc, grace=15.0)
        self.proc = None
