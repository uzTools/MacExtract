#!/usr/bin/env python3
"""os9.py — boot Mac OS 9 on emulated PowerPC with the application attached.

The Retro68 application is 68k-only and would run on a PowerPC Mac through the
68LC040 emulator built into Mac OS. That layer, and everything else above
System 6 — the WaitNextEvent branch, `SFReply.vRefNum` as a System 7+ working
directory reference, HFS+ names, the SIZE partition under a real Process
Manager — has never been exercised. This is the harness for exercising it.

    tools/vmac/os9.py --setup                 # fetch the Mac OS 9 disk image
    tools/vmac/os9.py fixtures/foo.sit -o shots/            # boot only
    tools/vmac/os9.py fixtures/foo.sit -o shots/ --launch   # boot, run, check

It boots `qemu-system-ppc -M mac99,via=pmu` headless, attaches a second disk
built by mkapmdisk.py holding the application and one archive, and screenshots
through QEMU's own monitor (`screendump`) — no X server involved, unlike the
Mini vMac harness.

**STATUS: --launch works.** Established 2026-08-02, with screenshots and a
byte-for-byte check of the output:

  * Mac OS 9.2 boots to the Finder desktop under this configuration. An idle
    host reaches it in under two minutes; a loaded one takes very much longer,
    and the wide range earlier notes gave (four minutes, then 20-45 minutes)
    was host load being written down as a property of the guest. `settle()`
    waits for the desktop rather than predicting it.
  * The transfer volume mounts and appears on the desktop.
  * The 68k application launches from it and extracts, driven entirely from
    the KEYBOARD — which needs no coordinates; the pointer works as well,
    see tools/vmac/os9mouse.py and
    XFER_VOLUME_ICON — and `verify_output()` then pulls both forks of what it
    wrote straight out of the transfer image and compares them against the
    same engine's Linux output.

  * `--hfsplus` extracts onto the HFS+ BOOT volume instead, by renaming it to
    `Out` from the keyboard and running the autotest build, which finds its
    volumes by name. The answer comes back as a report FILE on the plain-HFS
    input volume, because `at_report()`'s 1bpp framebuffer grid is invisible
    on a 32-bit screen — that reporting channel, not the filesystem, is what
    kept HFS+ untested for so long.

  * `--autotest` runs that same autotest build with the output volume plain
    HFS as well — a third APM disk named `Out` — which is the combination the
    other two do not cover between them: against `--launch` it changes the
    BUILD and nothing else. `-D UNC_AT_SAMEVOL` moves the sink onto the
    archive's own volume, which is where the interactive application writes.

What is still NOT covered here: names HFS+ permits that HFS does not (a 68k
application reaching it through the classic File Manager is capped at 31
characters either way, so they may be unreachable at all — unproven), and real
PowerPC silicon. See OPEN_ITEMS.md.
"""
import argparse, os, re, shutil, signal, socket, subprocess, sys, time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402
sys.path.insert(0, os.path.join(R.REPO, "tools"))
from vmac_check import mac_component, names_are_utf8         # noqa: E402


def _die_cleanly(signum, frame):
    """Turn a signal into a normal unwind so `finally` blocks run.

    Both harnesses start their emulator with start_new_session=True, on
    purpose: a stray signal to the process group must not take it down
    mid-write. The cost is that a driver killed by a `timeout` never reaches
    its cleanup and the emulator survives as an orphan — observed repeatedly,
    including two Xvfb displays and a qemu-system-ppc that had to be killed by
    hand, all of them competing for the CPU the next run needs. Raising
    SystemExit instead of dying in place lets the existing cleanup do its job.
    """
    raise SystemExit(f"interrupted by signal {signum}")


signal.signal(signal.SIGTERM, _die_cleanly)
signal.signal(signal.SIGINT, _die_cleanly)

QEMU_HOME = os.path.join(os.path.dirname(R.VMAC_HOME), "qemu-ppc")

# Desktop icon positions on the settled 1024x768 Mac OS 9 desktop, measured
# off desktop.png. Volumes stack down the right-hand edge in mount order: the
# boot disk ("untitled") first, then the transfer volume ("MacExtract").
#
# NOTHING DRIVES THE GUEST WITH THESE ANY MORE, and they are kept only because
# they are correct and were expensive to measure. The pointer is NOT unusable —
# see tools/vmac/os9mouse.py, which positions it to within 3 px and clicks, and
# BLOCKERS.md for what the probe below actually measured. This harness stays on
# the keyboard because a fixture run needs no coordinates. The old note:
# tools/vmac/os9probe.py, 2026-08-02, measured five separate mouse probes on a
# booted desktop — a held press on a menu bar title, its release, a click on
# bare desktop, a single click on this icon and a double click on it — and
# every one of them changed exactly 0.0000 of the watched rectangle. The
# same run located the cursor by diffing screenshots: it appears only at
# (0,0) and (1023,767), never at any of three requested desktop positions,
# which changed nothing at all. So `mouse_move` does not position the cursor
# in this guest and clicks land wherever it is pinned.
#
# The Finder is driven from the KEYBOARD instead — type-to-select, Cmd-Down to
# open — which needs no coordinates, no double-click timing and no pointer.
# That works, first try, all the way to an extraction. See launch_by_keyboard().
XFER_VOLUME_ICON = (974, 120)
# The application inside the transfer volume's window, once opened. Measured
# off volume.png — re-measure it there if the volume's contents change.
XFER_APP_ICON = (60, 100)
DISK = os.path.join(QEMU_HOME, "MacOS9.img")

# A pre-installed Mac OS 9.2 disk, Apple-partitioned, from the Internet
# Archive. Apple's copyright, so it is fetched and hashed like everything else
# under fixtures/ — never committed.
DISK_URL = "https://archive.org/download/mac-os9/MacOS9.img"
# archive.org publishes a SHA-1 per file; setup.sh hashes everything it fetches
# and this did not, which is how the local copy drifted from upstream without
# anyone noticing. See verify_disk().
DISK_SHA1 = "a6e39e049d99c56d0a2c08bf2631079f6f14bd56"


class Qemu:
    def __init__(self, disks, monitor, tablet=True, pointer=False):
        # -device usb-tablet makes an ABSOLUTE pointer available, so the
        # monitor's `mouse_move X Y` means "go to X, Y" rather than "move by
        # X, Y". mac99's built-in pointer is an ADB mouse, which is relative —
        # `info mice` duly reports "QEMU HID Mouse" — and feeding it the
        # 0..32767 absolute coordinates this harness computes slams the
        # pointer into a screen corner.
        #
        # Whether the guest can USE the tablet is a separate question from
        # whether QEMU offers it, and `tablet=False` exists to test exactly
        # that: classic Mac OS ships a USB HID driver for mice and there is no
        # reason to assume it binds an absolute tablet. Do not treat either
        # setting as known-good without a pointer-movement probe —
        # tools/vmac/os9probe.py measures it.
        #
        # `pointer=True` asks for the configuration os9mouse.py measured
        # instead: no tablet, one `usb-mouse`, driven by RELATIVE deltas and
        # a closed loop. It is what --cancel-click needs, and nothing else
        # here does — every other route is keyboard-only.
        argv = ["qemu-system-ppc", "-M", "mac99,via=pmu", "-m", "512",
                "-boot", "c", "-g", "1024x768x32", "-display", "none",
                "-monitor", f"unix:{monitor},server,nowait"]
        if pointer:
            argv[-2:-2] = ["-device", "usb-mouse"]
        elif tablet:
            argv[-2:-2] = ["-device", "usb-tablet"]
        for i, d in enumerate(disks):
            argv += ["-drive", f"file={d},format=raw,media=disk,index={i}"]
        self.mon_path = monitor
        self._scratchdir = os.path.dirname(monitor)   # where frame() writes
        if os.path.exists(monitor):
            os.remove(monitor)
        self.proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     start_new_session=True)
        for _ in range(240):        # wait for the monitor to accept a client
            if os.path.exists(monitor):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(monitor)
                    s.close()
                    return
                except OSError:
                    pass
            if self.proc.poll() is not None:
                raise SystemExit("os9: qemu exited:\n" + self.proc.stdout.read())
            time.sleep(0.5)
        raise SystemExit("os9: qemu monitor never came up")

    def use_absolute_pointer(self):
        """Make the USB tablet the ACTIVE pointer.

        Adding -device usb-tablet is necessary and not sufficient. QEMU keeps
        the original relative ADB mouse selected, and `info mice` shows which
        with a leading '*':

            Mouse #3: QEMU HID Tablet (absolute)
          * Mouse #2: QEMU HID Mouse          <- still the active one

        `mouse_move` goes to the ACTIVE device, so without this the absolute
        coordinates are still applied as deltas and every click still lands in
        a corner. Verified against `info mice` rather than assumed, because the
        symptom of getting it wrong is indistinguishable from a bad icon
        coordinate — which cost three boots to work out the first time."""
        reply = self.ask("info mice")
        index = None
        for line in reply.splitlines():
            if "(absolute)" in line:
                m = re.search(r"Mouse #(\d+)", line)
                if m:
                    index = m.group(1)
                    break
        if index is None:
            raise SystemExit("os9: qemu reports no absolute pointing device; "
                             "clicking cannot work. Is -device usb-tablet "
                             "still on the command line?\n" + reply)
        self.mon(f"mouse_set {index}")
        after = self.ask("info mice")
        if not any(l.strip().startswith("*") and "(absolute)" in l
                   for l in after.splitlines()):
            raise SystemExit("os9: mouse_set did not take; the active pointer "
                             "is still relative:\n" + after)
        return index

    def ask(self, cmd, wait=1.2):
        """Send a monitor command and return its reply, stripped of the
        terminal escapes the HMP echoes back."""
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.mon_path)
        time.sleep(0.4)
        try:
            s.recv(65536)
        except OSError:
            pass
        s.sendall((cmd + "\n").encode())
        time.sleep(wait)
        try:
            out = s.recv(1 << 16).decode(errors="replace")
        except OSError:
            out = ""
        s.close()
        return re.sub(r"\x1b\[[0-9;]*[A-Za-z]|[\x00-\x08\x0b-\x1f]", "", out)

    def mon(self, cmd, wait=1.2):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.mon_path)
        time.sleep(0.3)
        try:
            s.recv(65536)
        except OSError:
            pass
        s.sendall((cmd + "\n").encode())
        time.sleep(wait)
        s.close()

    def burst(self, cmds, gap=0.03, wait=0.4):
        """Several monitor commands down ONE connection.

        `mon()` opens a socket and sleeps 0.3 s per command, which is fine for
        a keystroke and useless for a pointer: one `goto()` sends dozens of
        `mouse_move`s, and the two halves of a click have to be closer
        together than the Mac's double-click threshold. This is the interface
        os9mouse.Pointer drives."""
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.mon_path)
        time.sleep(0.25)
        try:
            s.recv(65536)
        except OSError:
            pass
        for c in cmds:
            s.sendall((c + "\n").encode())
            time.sleep(gap)
        time.sleep(wait)
        s.close()

    def frame(self, tag, workdir=None):
        """A screenshot as (w, h, pixels), which is what Pointer diffs.

        Straight from QEMU's PPM: the pointer code compares pixels, so the
        ImageMagick conversion shot() does for the human-readable screenshots
        would only be a round trip through a second format."""
        import os9mouse
        d = workdir or self._scratchdir
        p = os.path.join(d, "." + tag + ".ppm")
        if os.path.exists(p):
            os.remove(p)
        self.mon(f"screendump {p}", 0.8)
        for _ in range(25):
            if os.path.exists(p) and os.path.getsize(p) > 100000:
                break
            time.sleep(0.3)
        return os9mouse.readppm(p)

    def shot(self, path):
        """QEMU writes PPM; convert so the result is viewable like the rest.

        Returns the path, or None if the screenshot did not happen. Checking
        the conversion — not just the screendump — matters: this used to return
        `path` unconditionally once the PPM existed, so a `convert` that failed
        still read as success. Passing a directory instead of a file was enough
        to trigger it, and the failure was silent all the way up into settle(),
        which then compared two empty buffers, found them equal and announced a
        settled desktop 43 s into a boot."""
        ppm = path + ".ppm"
        self.mon(f"screendump {ppm}")
        if not os.path.exists(ppm):
            return None
        subprocess.run(["convert", ppm, path], capture_output=True)
        os.remove(ppm)
        return path if os.path.isfile(path) and os.path.getsize(path) else None

    def click(self, x, y, double=False):
        """Click at 1024x768 screen coordinates. QEMU's absolute pointer uses
        a 0..32767 space on both axes regardless of the guest resolution.

        The button events go down ONE monitor connection in a single write.
        They used to be four separate mon() calls, and mon() sleeps 0.3 s
        before sending so the monitor's banner can arrive — which put roughly
        0.9 s between the two clicks of a "double click". The classic Mac
        double-click threshold is about half that, so the Finder saw two
        single clicks, the volume never opened, and the failure looked like a
        mis-measured icon coordinate rather than a broken primitive."""
        self.mon(f"mouse_move {int(x * 32767 / 1024)} {int(y * 32767 / 768)}", 0.5)
        # One connection, with deliberate gaps between the button events:
        # 60 ms down/up, 180 ms between clicks — inside the Mac's ~0.5 s
        # double-click threshold and above one 60 Hz input frame. This timing
        # was NOT what broke the Finder clicks (the pointer was in the wrong
        # place entirely; see usb-tablet above), but the original four separate
        # mon() calls really did put ~0.9 s between clicks, which would have
        # bitten the moment the pointer was fixed.
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.mon_path)
        time.sleep(0.3)
        try:
            s.recv(65536)
        except OSError:
            pass
        for i in range(2 if double else 1):
            if i:
                time.sleep(0.18)
            s.sendall(b"mouse_button 1\n")
            time.sleep(0.06)
            s.sendall(b"mouse_button 0\n")
            time.sleep(0.06)
        time.sleep(0.6)
        s.close()
        time.sleep(0.8)

    def settle(self, scratch, interval=20.0, timeout=1200.0, stable=2):
        """Screenshot until the screen stops changing; return seconds waited.

        Replaces a fixed sleep. The fixed wait was 260 s "because OS 9 takes
        about four minutes to reach the Finder here", which was true on the
        machine that measured it and false on a loaded one — the boot simply
        had not finished when the screenshot was taken, and the run produced
        nothing at all rather than saying why. Booting is exactly the kind of
        thing whose duration is a property of the host, not of the guest, so
        it should be waited for and not predicted.

        `scratch` is a FILE path, not a directory.

        Two things here are defensive, and both come from one incident where
        this returned "settled after 43 s" with the guest still on the startup
        splash. The cause was a caller passing a directory as `scratch`; the
        screenshot silently failed, `_body` returned empty bytes twice, and two
        empty buffers compare equal. So:

        * a screenshot that did not happen no longer counts towards stability,
          it resets it — comparing nothing to nothing is not evidence of calm;
        * stability is necessary but not sufficient, so settling also requires
          a POSITIVE signal that the desktop is really up: the Finder's menu
          bar on screen. "Nothing changed for a while" is a proxy for "ready",
          and a proxy is not the thing (BLOCKERS.md, at length).

        The menu bar gate would not have caught that particular bug — it would
        have hung to the timeout instead, which is at least loud. The `shot()`
        return check is what actually catches it."""
        started = time.time()
        prev, same = None, 0
        while time.time() - started < timeout:
            time.sleep(interval)
            if self.proc.poll() is not None:
                return None                       # qemu died; caller reports
            if not self.shot(scratch):
                prev, same = None, 0              # no screenshot, no evidence
                continue
            if not self._menubar_present(scratch):
                prev, same = None, 0              # still booting; start over
                continue
            cur = self._body(scratch)
            if not cur:
                prev, same = None, 0
                continue
            same = same + 1 if cur == prev else 0
            prev = cur
            if same >= stable - 1:
                return time.time() - started
        return None

    @staticmethod
    def _menubar_present(path):
        """Is the Finder's menu bar on screen?

        The top 20 rows are a near-white menu bar once the desktop is up and
        the desktop pattern (or the startup splash) before then, which
        separates cleanly on mean brightness — measured on real screenshots
        from two runs, not guessed:

            startup splash        0.404
            settled desktop       0.766  (twice, two different runs)

        0.6 sits between the two clusters and is not tuned to either."""
        out = subprocess.run(["convert", path, "-crop", "1024x20+0+0", "+repage",
                              "-colorspace", "Gray", "-format", "%[fx:mean]",
                              "info:"], capture_output=True, text=True)
        try:
            return float(out.stdout.strip()) > 0.6
        except ValueError:
            return False

    @staticmethod
    def _body(path):
        """The screen BELOW the menu bar, as raw pixels.

        Comparing whole frames does not work on Mac OS 9: the menu bar carries
        a clock, so two shots a minute apart are never byte-identical and a
        settled desktop never looks settled. The first version of settle() hung
        until its timeout on a machine that had in fact reached the Finder
        minutes earlier. Everything this harness cares about — volume icons,
        windows, dialogs — is below the menu bar."""
        out = subprocess.run(["convert", path, "-crop", "1024x748+0+20",
                              "+repage", "-depth", "8", "rgb:-"],
                             capture_output=True)
        return out.stdout

    def key(self, *names, wait=0.35):
        """Send keystrokes by QEMU keycode name.

        This is how the Finder is driven here. See the note at
        XFER_VOLUME_ICON: the keyboard drives this guest completely, and it
        needs no coordinates. (The pointer is usable too — os9mouse.py.)"""
        for k in names:
            self.mon(f"sendkey {k}", wait)

    def region(self, path, rect):
        """Raw pixels of one rectangle of a screenshot, for change detection.

        `rect` is (w, h, x, y), ImageMagick's -crop order."""
        w, h, x, y = rect
        out = subprocess.run(["convert", path, "-crop", f"{w}x{h}+{x}+{y}",
                              "+repage", "-depth", "8", "rgb:-"],
                             capture_output=True)
        return out.stdout

    def wait_change(self, before, rect, scratch, timeout=180.0, poll=5.0,
                    want=0.02):
        """Wait until `rect` stops looking the way it did in `before`.

        Returns (fraction changed, seconds waited). A fixed sleep would be the
        boot-sleep mistake in miniature: opening a Finder window takes an
        instant, launching a 68k application through the 68LC040 emulator does
        not, and neither is a duration this harness can predict from the host.
        The elapsed time is returned because it is itself a measurement — how
        long a 68k launch takes under emulation is a number Mac OS 9 has never
        been characterised for."""
        base = self.region(before, rect)
        started = time.time()
        frac = 0.0
        while time.time() - started < timeout:
            time.sleep(poll)
            if not self.shot(scratch):
                continue
            cur = self.region(scratch, rect)
            if not cur or len(cur) != len(base):
                continue
            frac = sum(a != b for a, b in zip(base, cur)) / len(base)
            if frac >= want:
                break
        return frac, time.time() - started

    def close(self):
        try:
            os.killpg(os.getpgid(self.proc.pid), 9)
        except (ProcessLookupError, PermissionError):
            pass


# Middle of the screen: where a Finder window, SFGetFile and the application's
# alert all land. Clear of the menu bar and of the right-hand icon column.
WINDOW_RECT = (600, 500, 200, 100)

# The progress dialog's title line — "Extracting archive.sit" — measured off
# 15-progress.png: the dialog is at (80,65)-(405,195) and the line sits at
# y=86..110. It is the one part of that dialog that does NOT repaint while the
# extraction runs, which is what makes it a state signature: it changes when
# the dialog is REPLACED, by the result alert or by the cancelled one, and at
# no other time. Waiting for the screen to go still cannot do this job — a
# progress dialog reading "0%  estimating time left" is perfectly still for as
# long as the first percent takes, and on 2026-08-28 that read as a finished
# extraction 14 s into a 30 s one.
PROGRESS_TITLE = (300, 24, 90, 86)

# The transfer volume's Finder window, measured off 12-volume-open.png: title
# bar at y=25, bottom edge at y=270, left edge at x=8. Cropped out of the last
# screenshot so the extracted NAMES are legible without opening the full
# 1024x768 frame — which is what the 8-bit-name photograph is for.
VOLUME_WINDOW = (460, 260, 0, 18)

# The middle of the progress dialog's Cancel BUTTON, in screen pixels.
# Computed from the resources rather than eyeballed: 'DLOG' 128 is at global
# (80,80)-(400,190) and does not autocentre, and the button is item 1 of
# 'DITL' 128 at local (220,78)-(300,98) — so (80+260, 80+88). Confirmed
# against 15-progress.png, where the button's frame runs x=300..380,
# y=158..178. Re-derive it from mac/macextract.r if the dialog moves.
CANCEL_BUTTON = (340, 168)

# The password dialog's MESSAGE area — item 4 of 'DITL' 132, local
# (20,10)-(372,64) inside a 'DLOG' at global (60,80)-(452,214), so
# (80,90)+352x54. It is what the refusal changes: the second ask prepends
# "That password was refused. " and the text rewraps from two lines to three.
# WINDOW_RECT cannot see that — the whole dialog is a small part of it, and one
# rewrapped message moved 0.43 % of it, under the 2 % threshold, so the wait
# ran to its 120 s timeout and printed "NO CHANGE" about a dialog that had in
# fact changed (measured 2026-08-28, `15c-refused.png`). **A change threshold
# is only as good as the rectangle it is measured over.**
PASSWORD_MSG = (352, 54, 80, 90)


def launch_by_keyboard(q, outdir, wait=240.0, cancel=False, click=False,
                       click_at=CANCEL_BUTTON, password=None,
                       wrong_first="wrongone"):
    """Drive the Finder to launch the application and extract, using no mouse.

    Every step here was measured by tools/vmac/os9probe.py on 2026-08-02 and
    is reproduced in the screenshots this function writes. The order matters:

      1. The Mac OS Setup Assistant is frontmost on EVERY boot — the harness
         boots a pristine copy each time, so the assistant is never marked
         done. Cmd-Q quits it; it asks "are you sure", and Return confirms.
         Until it is gone the Finder is not the front application.
      2. Typing selects by name in the Finder, and Cmd-Down opens the
         selection. "mac" matches the transfer volume `MacExtract` and not
         the boot volume `untitled` — nor `Mail`, which is why two letters
         are not enough. It typed "unc" until 2026-08-27, from before the
         project was renamed, and selected nothing at all.
      3. Inside the volume window the same two keystrokes launch the
         application, whose SFGetFile opens with `archive.sit` already
         selected — it sorts first — so Return opens it.
      4. Return opens the SFPutFile destination dialog, and a SECOND Return
         accepts it: "Extract here", beside the archive.
      5. The extraction runs. NOT waited for with one changed rectangle:
         the progress dialog repaints ten times a second, so the first
         change after the destination dialog is that dialog appearing and
         never the result. The default path waits for the screen to go
         still, which is a proxy and says so (`still()`); the --cancel path
         watches PROGRESS_TITLE instead, which is exact.
      6. Return dismisses the result alert, which puts SFGetFile back up —
         the repaint is a step of its own — and Cmd-. is Standard File's
         Cancel, which ends the application's SFGetFile loop and quits it.
         Cmd-Q does not: Standard File is modal and never sees it.

    Until 2026-08-28 this stopped at step 4 with three keystrokes: one Return
    for the archive, one for what the code called "the alert", and a Cmd-Q
    that was swallowed by the modal dialog. So `14-result.png` photographed
    the DESTINATION dialog under the name of the result, `15-quit.png` caught
    the alert the run had not waited for, the application never quit, and the
    step that reported "extraction reported" had timed the destination dialog
    opening. Nothing was wrong with the extraction — the verdict comes from
    the disk — but every screenshot in the tier was one step behind its label.

    With `cancel=True` the extraction is interrupted with Cmd-. instead of
    being waited out, which is the route the Mini vMac tiers have driven since
    M10 and this one had never been asked for. The pass condition is then a
    strict, non-empty subset of the entries — see verify_output(partial).

    With `password` the archive is encrypted, and step 5 becomes a dialog
    rather than a wait: the engine asks its host for a password only when an
    entry turns out to need one, so this is the one path that cannot be
    reached by choosing a fixture. `wrong_first` is typed and refused before
    the real one, because the retry is the path a user actually meets — and
    because an application that ignored what was typed and decrypted anyway
    would pass a single-password run. Both dialogs are keyboard work:
    `PassFilter` maps Return to OK and Escape to Cancel.

    `click=True` cancels through the BUTTON instead of the chord. They are two
    different branches of ProgressPump() — the chord is its own keyDown test,
    the button is the DialogSelect beside it — and until this route existed
    only the chord had ever run here. The pointer is parked on the button
    while the DESTINATION dialog is still up, because positioning costs ~40 s
    and the progress dialog exists only while the extraction does; the click
    itself is then instant and needs no move.

    Returns the list of (label, screenshot) pairs it captured."""
    shots = []

    def shot(tag):
        p = os.path.join(outdir, tag + ".png")
        q.shot(p)
        shots.append((tag, p))
        return p

    scratch = os.path.join(outdir, ".wait.png")

    def step(before, label, timeout, poll=5.0, rect=WINDOW_RECT):
        """Wait for the screen to react, and say so either way.

        A step that times out does NOT stop the run: the screenshots are worth
        having, and the verdict comes from verify_output() reading the disk,
        not from a pixel threshold. But it must be visible in the log, because
        "the next screenshot looks wrong" is exactly the non-observation this
        harness spent five boots learning not to reason from."""
        frac, secs = q.wait_change(before, rect, scratch,
                                   timeout=timeout, poll=poll)
        verdict = "" if frac >= 0.02 else "  <- NO CHANGE, continuing anyway"
        print(f"os9: {label} ({frac:.4f} changed in {secs:.0f}s){verdict}")

    def chord(name):
        """Send a Command-key chord and check the monitor did not reject it.

        `key()` writes down a monitor connection and never reads the reply, so
        a keycode name QEMU does not know is indistinguishable from a
        keystroke the guest ignored — and the whole cancel route rests on one
        chord being real. HMP answers an unknown name with an error, so this
        asks rather than tells."""
        reply = q.ask(f"sendkey {name}")
        if re.search(r"unknown|invalid|not found", reply, re.I):
            print(f"os9: sendkey {name} REJECTED by the monitor: "
                  f"{reply.strip()}  <- the keystroke never reached the guest")
        return reply

    def replaced(before, timeout, poll=3.0):
        """Has the progress dialog been replaced by an alert?

        Returns the fraction of PROGRESS_TITLE that changed, 0.0 if it never
        did. Exact where `still()` is a proxy: see PROGRESS_TITLE."""
        base = q.region(before, PROGRESS_TITLE)
        started = time.time()
        while time.time() - started < timeout:
            time.sleep(poll)
            if not q.shot(scratch):
                continue
            cur = q.region(scratch, PROGRESS_TITLE)
            if not cur or len(cur) != len(base):
                continue
            frac = sum(a != b for a, b in zip(base, cur)) / len(base)
            if frac >= 0.02:
                return frac
        return 0.0

    def still(label, timeout):
        """Wait for the screen to STOP changing, and report how long it took.

        What ends an extraction is an alert, and what precedes it is a
        progress dialog repainting continuously; the first is a still screen
        and the second is not, so this is the only wait that can tell them
        apart. The number is a measurement worth keeping — how long a 68k
        extraction takes under the 68LC040 emulator is not derivable from the
        Mac Plus figures in FORMATS.md."""
        secs = q.settle(scratch, interval=5.0, timeout=timeout)
        if secs is None:
            print(f"os9: {label} — STILL MOVING after {timeout:.0f}s, "
                  f"continuing anyway")
        else:
            print(f"os9: {label} (screen still after ~{secs:.0f}s)")
        return secs

    shot("10-desktop")

    q.key("meta_l-q", "ret")                     # quit the Setup Assistant
    time.sleep(4)
    front = shot("11-assistant-quit")

    q.key("m", "a", "c", "meta_l-down")          # select and open the volume
    step(front, "volume window opened", 60.0)
    vol = shot("12-volume-open")

    q.key("m", "a", "c", "meta_l-down")          # select and launch the app
    step(vol, "application launched", wait)
    sfg = shot("13-sfgetfile")

    q.key("ret")                                 # open the selected archive
    step(sfg, "destination dialog opened", wait)
    dest = shot("14-destination")

    ptr = None
    if click:
        # Park the cursor on the Cancel button NOW, while a modal dialog that
        # waits forever is on screen. The progress dialog is up only while the
        # extraction runs — seconds, on this machine — and goto() is a closed
        # loop that costs ~40 s, so aiming after the fact cannot work. The
        # SFPutFile name field blinks a caret; Pointer masks it (os9mouse.py).
        sys.path.insert(0, HERE)
        import os9mouse
        ptr = os9mouse.Pointer(q.burst, lambda t: q.frame(t, outdir))
        got = ptr.goto(*click_at)
        if got is None or abs(got[0]-click_at[0]) > 4 \
                or abs(got[1]-click_at[1]) > 4:
            print(f"os9: the cursor is at {got}, not at {click_at}  <- a "
                  f"click from here is not the click this run means to make")
        shot("14b-parked")

    q.key("ret")                                 # Save: extract beside it
    if password:
        # The password dialog hides the progress dialog behind it
        # (MacAskPassword's HideWindow), so waiting for one rectangle to
        # change is exact here in a way it is not for the progress dialog.
        step(dest, "password dialog up", wait, poll=2.0)
        asked = shot("15-password")
        for ch in wrong_first:                   # refused on purpose
            q.key(ch)
        shot("15b-typed-wrong")
        q.key("ret")
        # Over the MESSAGE, not the window: the refusal is a rewrapped
        # paragraph inside a dialog that is otherwise identical.
        step(asked, "asked again after the wrong password", 120.0, poll=2.0,
             rect=PASSWORD_MSG)
        shot("15c-refused")
        for ch in password:
            q.key(ch)
        q.key("ret")
        still("extraction finished", wait)
    elif cancel:
        # Poll fast here and shoot at once: the window to reach the progress
        # dialog is the whole extraction, and on this machine that is seconds
        # for anything small. A cancel that arrives after the last entry is
        # not a failed application, it is a failed TEST, and verify_output()
        # says so rather than passing.
        step(dest, "progress dialog up", 120.0, poll=1.0)
        prog = shot("15-progress")
        # Cmd-. is sent until the dialog goes away, not once, and the
        # COUNT is printed. ProgressPump() runs only from prog_tick, which
        # the engine calls per 8-16 KB of input consumed, so an application
        # decoding a format that does not tick is not pumping at all and a
        # chord into it is indistinguishable from a chord that does not
        # work. That is not a hypothesis: it is how Now Compress's missing
        # progress callback was found here (DECISIONS.md 2026-08-28,
        # tools/run_ticks.py). 1 means the first landed, more means the
        # early ones were lost, none prints "Cmd-. DID NOT CANCEL".
        #
        # A click is counted the same way, for the same reason: an application
        # that is not pumping events cannot see one either, and a button press
        # into a frozen dialog looks exactly like a button that does nothing.
        what = "click" if click else "Cmd-."
        sent, hit = 0, 0.0
        deadline = time.time() + wait
        while time.time() < deadline:
            if click:
                # No move: the cursor has been on the button since before the
                # extraction started. The button is held down (Pointer.press)
                # so DialogSelect's TrackControl still sees it down when the
                # progress callback gets round to dequeuing the mouseDown.
                ptr.press(hold=0.9)
            else:
                chord("meta_l-dot")
            sent += 1
            hit = replaced(prog, 6.0)
            if hit:
                break
        if hit:
            # Replaced is not the same as cancelled: an extraction that
            # finishes on its own replaces the dialog too. Which one happened
            # is read off the volume, never off this line.
            print(f"os9: the progress dialog was replaced after {sent} "
                  f"{what} ({hit:.4f} of the title line changed) — cancelled "
                  f"or finished, the volume says which")
        else:
            print(f"os9: {sent} {what} sent and the progress dialog is still "
                  f"up  <- {what.upper()} DID NOT CANCEL")
    else:
        still("extraction finished", wait)
    alert = shot("16-result")

    q.key("ret")                                 # dismiss the alert
    step(alert, "SFGetFile repainted", 120.0)
    back = shot("17-back")

    chord("meta_l-dot")                          # Standard File Cancel: quit
    step(back, "application quit", 120.0)
    fin = shot("18-finder")

    # The names the Mac wrote, as the Finder draws them. Every tier checks the
    # BYTES of an 8-bit MacRoman name; only a photograph says what the glyphs
    # look like, and this tier had never taken one.
    crop = os.path.join(outdir, "19-names.png")
    w, h, x, y = VOLUME_WINDOW
    if fin and subprocess.run(["convert", fin, "-crop", f"{w}x{h}+{x}+{y}",
                               "+repage", crop],
                              capture_output=True).returncode == 0:
        shots.append(("19-names", crop))
    if os.path.exists(scratch):
        os.remove(scratch)
    for f in os.listdir(outdir):            # frame()'s PPMs: 2.3 MB apiece
        if f.startswith(".") and f.endswith(".ppm"):
            os.remove(os.path.join(outdir, f))
    return shots


# ---- checking what the Mac actually wrote --------------------------------
#
# The System 6 harness reads its result off the framebuffer, because a floppy
# written by Mini vMac is awkward to get at. Nothing here needs that: the
# transfer volume IS a file on the host, so the extracted forks can be pulled
# straight out of it and compared byte for byte against the same engine's
# Linux output. That is a stronger check than a CRC painted on a screen, and
# it does not depend on decoding pixels.

def hfs_partition(img, dest):
    """Copy the Apple_HFS partition out of an Apple-partitioned image.

    hfsutils cannot mount an APM disk directly — `hmount` on the whole image
    says "not a Macintosh HFS volume" — so the partition is lifted out by the
    same block offset mkapmdisk.py wrote it at."""
    sys.path.insert(0, HERE)
    import mkapmdisk                                          # noqa: E402
    start = mkapmdisk.find_hfs_start(img) * 512
    with open(img, "rb") as src, open(dest, "wb") as out:
        src.seek(start)
        shutil.copyfileobj(src, out)
    return dest


def macbinary_forks(path):
    """(type, creator, data fork, resource fork) from a MacBinary file.

    hfsutils has no way to copy a resource fork on its own; `hcopy -m` writes
    both forks in one MacBinary file, so that is what gets parsed. Offsets are
    the ones documented and sourced in src/fmt_macbinary.c (from XADMaster) —
    not re-derived here."""
    b = open(path, "rb").read()
    # Validate before trusting the length fields. A short or non-MacBinary
    # file here means hcopy produced something unexpected, and reading lengths
    # out of it would hand the comparison two truncated forks that happen to
    # be equal — a false PASS built on a failed copy.
    if len(b) < 128 or b[0] != 0 or b[74] != 0 or not 1 <= b[1] <= 63:
        raise SystemExit(f"os9: {path} is not a MacBinary file; hcopy -m "
                         f"failed or wrote something else")
    dlen = int.from_bytes(b[83:87], "big")
    rlen = int.from_bytes(b[87:91], "big")

    def pad(n):
        return (n + 127) // 128 * 128

    doff = 128 + pad(int.from_bytes(b[120:122], "big"))   # secondary header
    roff = doff + pad(dlen)
    if roff + rlen > len(b):
        raise SystemExit(f"os9: {path} is truncated: header says {dlen} B data "
                         f"+ {rlen} B rsrc, file is {len(b)} B")
    return b[65:69], b[69:73], b[doff:doff + dlen], b[roff:roff + rlen]


def _ostype(b):
    """A four-byte OSType as something safe to print.

    An entry with no type/creator carries four NULs, and printing those raw
    put NUL bytes in the run log — enough for grep to call the whole file
    binary and silently refuse to match anything in it, which is a poor way to
    lose a test result."""
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)


# What the Finder and the harness put on the volume themselves; anything else
# is output the application wrote. Applied at the volume root only — a FOLDER
# with one of these names inside an archive is the archive's business.
# What mkapmdisk.py writes the archive as, on every run. Named because the
# in-place formats extract to it — see verify_output.
ARCHIVE_ON_VOLUME = "archive.sit"

NOT_OUTPUT = {ARCHIVE_ON_VOLUME, "MacExtract", "Desktop DB", "Desktop DF",
              "Desktop Folder", "TheVolumeSettingsFolder", "Trash"}


def _walk_volume(env, mac_dir="", depth=0):
    """Every FILE on the mounted volume, as '/'-joined relative paths.

    Recursive, because archives contain folders and the Mac shell creates
    them: `synth-exo-tar.tar` extracts to `README.txt`, `bin/` and `docs/`,
    and a checker that lists only the volume root sees one file of four and
    calls the other three missing. That is what the first sweep reported.

    Names come back as MacRoman bytes and are decoded as such, then
    NFC-normalized, so they can be compared with the CLI's UTF-8 output —
    the same normalization tools/run_diff.py does for the same reason. Reading
    them as UTF-8 mangles every 8-bit character: `App\xe9` (PackIt's fixture)
    came back as two different manglings on the two sides and compared unequal
    while both were in fact correct.

    `hls` takes an HFS path, so no `hcd` state is involved. Returns
    `{POSIX-ish relative path: the HFS path hcopy wants}` — a dict rather
    than a list because the two cannot be derived from each other. A
    classic Mac name may CONTAIN '/' (it is ':' that is forbidden, which
    is why the engine swaps the two), so joining components with '/'
    produces a string that cannot be split back: `SD! Utilities /
    MSWord4.0` inside `PLEASE READ` came out as
    `:Read Me and More:PLEASE READ:SD! Utilities : MSWord4.0` and hcopy
    answered "no such file or directory" for a file that was there and
    correct. The HFS path is therefore built from the components while
    the walk still has them, and the POSIX one is kept only for
    comparing against Linux, where the same ambiguity is harmless
    because both sides build it the same way. (2026-08-27, the first
    fixture here whose names hold the swap.)
    """
    if depth > 8:                       # archives here are not this deep
        return {}
    out = {}
    # The folder's path goes out as MacRoman bytes, like hcopy's argument in
    # verify_output: passed as a str it is encoded UTF-8, `hls` finds no such
    # folder, and every file inside it is reported missing while sitting on
    # the volume. A FILE with an 8-bit name at the root had been checked
    # since 2026-08-28; a FOLDER with one was first walked on 2026-09-04
    # (`Terrainman 2.0 \xc4` — DiskDoubler's `derived-Terrainman_2.0__.sea`),
    # and the harness failed a run the application had completed.
    # -a, because without it `hls` shows neither a name beginning with a dot
    # nor a file whose Finder INVISIBLE bit is set — and an archive holds
    # both: `.DS_Store`, and the `Icon\r` every custom folder icon on a Mac
    # is called, which comes out invisible because that is what the archive
    # says. Measured 2026-09-22 on the volume this tier wrote: `hls -F -1`
    # lists four of the five entries and `hls -a -F -1` lists five. Until
    # then a file the Mac had written correctly was reported MISSING, and an
    # invisible entry was invisible to the COMPARISON as well as the Finder.
    # checkdisk.py has had both rules since it was written.
    listing = subprocess.run(["hls", "-a", "-F", "-1"]
                             + ([mac_dir.encode("mac_roman", "replace")]
                                if mac_dir else []),
                             capture_output=True, env=env)
    for raw in listing.stdout.split(b"\n"):
        # NOT rstrip(): a carriage return is a legal HFS filename character,
        # and it is the LAST character of `Icon\r`. `hls -1` ends each line
        # with \n and adds nothing else, so splitting on \n has already
        # removed everything that is not name.
        entry = raw.decode("mac_roman")
        if not entry:
            continue
        isdir = entry.endswith(":")
        name = entry[:-1] if isdir or entry.endswith("*") else entry
        if depth == 0 and name in NOT_OUTPUT:
            continue
        rel = f"{mac_dir_to_rel(mac_dir)}/{name}" if mac_dir else name
        hfs = (mac_dir or ":") + name
        if isdir:
            out.update(_walk_volume(env, hfs + ":", depth + 1))
        else:
            out[unicodedata.normalize("NFC", rel)] = hfs
    return out


def _mac_path(rel):
    """A POSIX-ish relative path as an absolute HFS path (`:a:b:c`).

    Only correct where no component contains '/' — see _walk_volume."""
    return ":" + rel.replace("/", ":")


def mac_dir_to_rel(mac_dir):
    """`:bin:` back to `bin`."""
    return mac_dir.strip(":").replace(":", "/")


def verify_output(xfer, fixture, workdir, partial=False, password=None):
    """Compare what the Mac wrote against the same engine's Linux output.

    Returns (ok, list of report lines). With `partial` the run was CANCELLED
    part way through, so the pass condition changes and does not soften: what
    the Mac wrote must be a strict, NON-EMPTY subset of the entries, and every
    file in it must still be byte-exact. A complete set means the cancel
    arrived after the last entry and tested nothing; an empty one means it
    arrived before the first finished, and neither can distinguish a working
    Cancel from a dead keystroke. Both are reported as failures of the TEST,
    with the fixture to change, rather than as failures of the application. The reference is `macextract x`,
    with the auto-unwrap loop ON, because THIS harness launches the
    INTERACTIVE build and that one takes envelopes off (`ExtractOne` in
    mac/macextract_mac.c). It ran `-nr` until 2026-08-27, copied from
    tools/vmac_check.py, where it is right for a different reason: the
    AUTOTEST build calls RunExtract once and has no such loop. os9.py
    changed which application it launches and the reference stayed put,
    which nothing could notice while this tier was not being run —
    `export-hc.hqx` failed as "MISSING Export.sit, UNEXPECTED Export"
    on a Mac that had correctly opened the BinHex, then the StuffIt
    inside it, and written the HyperCard stack byte-for-byte.
    The `--hfsplus` path below runs the autotest build and keeps
    `-nr`."""
    lines, ok = [], True
    hfs = hfs_partition(xfer, os.path.join(workdir, "xfer.hfs"))
    home = os.path.join(workdir, "hfshome")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ, HOME=home)
    run = lambda *a: subprocess.run(a, capture_output=True, text=True, env=env)

    m = run("hmount", hfs)
    if m.returncode != 0:
        return False, [f"cannot mount the transfer volume: {m.stderr.strip()}"]
    names = _walk_volume(env)

    ref = os.path.join(workdir, "linux-out")
    shutil.rmtree(ref, ignore_errors=True)
    os.makedirs(ref)
    cli = os.path.join(R.REPO, "build", "rel", "macextract")
    # Run the reference against a copy named exactly what the Mac saw. For
    # gzip and .Z the engine has no stored name and falls back to the archive
    # filename minus its last extension, so the reference has to be given the
    # same input name or the two sides derive different output names for the
    # same bytes — `archive` here, `synth-exo-Z` from the fixture's own name.
    # mkapmdisk.py always writes the archive to the volume as `archive.sit`.
    # The copy lives outside the output directory so it cannot collide with
    # the output, which is also true of the archive on the Mac after the fix
    # in mac/macextract_mac.c.
    asmac = os.path.join(workdir, "as-the-mac-saw-it", "archive.sit")
    os.makedirs(os.path.dirname(asmac), exist_ok=True)
    shutil.copyfile(fixture, asmac)
    # `-p` where the Mac was given one in its dialog: the reference has to
    # decrypt the same entries, or every one of them is "missing on Linux".
    subprocess.run([cli, "x", "--forks", "hidden"]
                   + (["-p", password] if password else [])
                   + [asmac, "-o", ref], capture_output=True)

    # Everything the reference wrote, as relative paths. The reference is
    # extracted with `--forks hidden`, so a "._" file is a resource fork and
    # an archive entry never is — the Mac has no sidecars at all, its forks
    # live inside the file. DECISIONS.md, 2026-08-08.
    expected = set()
    for root, _, files in os.walk(ref):
        for f in files:
            if f.startswith("._"):
                continue
            rel = os.path.relpath(os.path.join(root, f), ref)
            expected.add(rel)

    # The Mac writes each COMPONENT the way ComponentToStr63() does — the
    # engine's ':' back to '/', cut at 31 characters — so the two sides
    # spell some names differently while both being right. `mac_of` maps
    # the name the Mac would write to the reference path it came from,
    # and everything below compares in the Mac's spelling. Added
    # 2026-08-27 with the SuperDisk! fixture, whose archive holds
    # `SD! Utilities : MacWrite`: a colon on Linux and a slash on the
    # Mac, which the set comparison would otherwise call one missing file
    # and one unexpected one. The HFS+ path has done this since M12.
    # The KEY is what the Mac wrote and is NFC, because _walk_volume()
    # normalizes what it reads off the volume; the VALUE is the path on the
    # Linux disk, UNNORMALIZED, because that is the one that has to be
    # opened below. Both matter, and the order does: the fold reads the
    # archive's own bytes, so it runs BEFORE the normalization and not
    # after it (mac_leaf, and checkdisk.py, which learned it first).
    mac_of = {}
    collided = {}
    utf8 = names_are_utf8(fixture)
    for e in sorted(expected):
        m = "/".join(unicodedata.normalize("NFC", mac_leaf(c, utf8))
                     for c in e.split("/"))
        if m in mac_of:
            collided[m] = [mac_of[m], e]
        mac_of[m] = e
    expected = set(mac_of)

    # SpaceSaver compresses a file IN PLACE, so its one output is named after
    # the archive — there is no other name in the container to use. The two
    # sides then spell it differently for a reason that is not a defect: the
    # reference extracts into its own directory and writes `archive.sit`,
    # while the Mac extracts BESIDE the archive, where that name is taken, so
    # the shell's collision numbering writes `archive.sit~1`. Reconciled here,
    # and only here: until 2026-08-28 the NOT_OUTPUT guard below refused the
    # whole fixture as ungradeable, which is why no SpaceSaver file had ever
    # been replayed on this tier.
    #
    # This does not soften anything. A shell that overwrote the archive still
    # fails (the name is in NOT_OUTPUT, so it reads as no output at all), and
    # one that stripped the extension and wrote `archive` still fails as one
    # MISSING and one UNEXPECTED — which is exactly the defect the first run
    # of this fixture found in mac/macextract_mac.c.
    if ARCHIVE_ON_VOLUME in expected:
        mac_of[ARCHIVE_ON_VOLUME + "~1"] = mac_of.pop(ARCHIVE_ON_VOLUME)
        expected = set(mac_of)
        lines.append(f"in-place format: the Mac writes {ARCHIVE_ON_VOLUME}~1 "
                     f"beside the archive it expanded, Linux writes "
                     f"{ARCHIVE_ON_VOLUME} into an empty directory")

    if not expected and not names:
        # Both sides produced nothing, which for a detect-only format is the
        # CORRECT outcome and not a failure: the engine recognises it and
        # declines. Treating "nothing" as failure would mark a working refusal
        # as broken — and refusing cleanly on an unsupported format is
        # behaviour worth verifying on Mac OS 9 like any other.
        why = subprocess.run([cli, "l", "-nr", asmac], capture_output=True,
                             text=True)
        note = (why.stdout + why.stderr).strip().splitlines()
        lines.append("neither side produced output, and they agree: "
                     + (note[-1] if note else "the engine wrote nothing"))
        run("humount")
        return True, lines
    if not names:
        run("humount")
        if partial:
            return False, lines + [
                "the cancel landed before the first entry was written, so "
                "nothing came off the volume to compare. That is legal "
                "behaviour and a useless test: use a bigger archive, or one "
                "with more entries."]
        return False, lines + ["the Mac wrote no output files, but Linux wrote "
                               + ", ".join(sorted(expected))]
    lines.append(f"{len(names)} file(s) on the Mac volume: "
                 f"{', '.join(sorted(names))}")

    # Compare the SETS of names before comparing any bytes. Without this a Mac
    # that wrote one of three entries would pass: every file present would
    # match, and the two that never appeared would be invisible to a loop over
    # what is there. The check has to run in both directions.
    stolen = expected & NOT_OUTPUT
    if stolen:
        run("humount")
        return False, lines + [
            f"cannot check this fixture: it extracts to {sorted(stolen)}, which "
            f"is also a name the harness or the Finder puts on the volume, so "
            f"the two cannot be told apart. Rename the archive on the transfer "
            f"disk, or pick another fixture."]
    if collided:
        run("humount")
        return False, lines + [
            f"cannot check this fixture: {sorted(collided.values())} shorten "
            f"to one name on the Mac, where the shell numbers the second `~1`, "
            f"so the harness cannot say which reference file either one is. "
            f"Pick another fixture."]
    missing = expected - set(names)
    extra = set(names) - expected
    if partial and not missing:
        ok = False
        lines.append("the cancel arrived too late: all "
                     f"{len(expected)} entries were written, so nothing was "
                     "interrupted and this run tested nothing. Use a bigger "
                     "archive.")
    elif partial:
        lines.append(f"cancelled with {len(names)} of {len(expected)} entries "
                     f"written and {len(missing)} never started — a strict "
                     f"subset, which is the result being tested")
    elif missing:
        ok = False
        lines.append(f"MISSING on the Mac: {', '.join(sorted(missing))}")
    if extra:
        ok = False
        lines.append(f"UNEXPECTED on the Mac: {', '.join(sorted(extra))}")

    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    from vmac_check import mask_reserved                       # noqa: E402

    for name in sorted(names):
        mb = os.path.join(workdir, "forks", name.replace("/", "_") + ".macbin")
        os.makedirs(os.path.dirname(mb), exist_ok=True)
        # hcopy wants an HFS path, and the NAME is MacRoman on the volume, so
        # the argument has to go back out as MacRoman bytes rather than as the
        # UTF-8 Python would encode by default.
        c = subprocess.run(["hcopy", "-m",
                            names[name].encode("mac_roman", "replace"),
                            mb.encode()],
                           capture_output=True, env=env)
        if c.returncode != 0:
            ok = False
            lines.append(f"  {name}: cannot copy off the volume: "
                         f"{c.stderr.decode(errors='replace').strip()}")
            continue
        typ, crt, data, rsrc = macbinary_forks(mb)
        refrel = mac_of.get(name, name)     # the reference's spelling of it
        want_d = os.path.join(ref, refrel)
        head, _, tail = refrel.rpartition("/")
        want_r = os.path.join(ref, head, "._" + tail) if head \
            else os.path.join(ref, "._" + tail)
        for label, got, path, mask in (("data", data, want_d, False),
                                       ("rsrc", rsrc, want_r, True)):
            if not os.path.exists(path):
                if got:
                    ok = False
                    lines.append(f"  {name} {label}: Mac wrote {len(got)} B, "
                                 f"Linux wrote no such fork")
                continue
            expect = open(path, "rb").read()
            a, b = (mask_reserved(got), mask_reserved(expect)) if mask else (got, expect)
            if a == b:
                lines.append(f"  {name} {label}: {len(got)} B byte-exact")
            else:
                ok = False
                lines.append(f"  {name} {label}: MISMATCH — Mac {len(got)} B, "
                             f"Linux {len(expect)} B")
        lines.append(f"  {name} type/creator: {_ostype(typ)}/{_ostype(crt)}")
    run("humount")
    return ok, lines


# ---- HFS+ : extracting onto a volume the host cannot read ----------------
#
# Everything above extracts onto the transfer volume, which is HFS, so nothing
# in this project has ever written to HFS+ — the row MANUAL_TESTS.md has
# carried since M10. The OS 9 boot volume IS HFS+, and no tool in this
# environment can read it, which is why the answer has to come back another
# way: the AUTOTEST build reads both forks back through the File Manager on
# the Mac, CRC-32s them, and now also writes that plus every output NAME to a
# file on the plain-HFS input volume (at_report_file in mac/macextract_mac.c).
#
# It finds its volumes by name — "In" and "Out" — so pointing it at HFS+ needs
# no new code at all: rename the boot volume to `Out` in the Finder, from the
# keyboard, and the same autotest binary that runs on a Mac Plus writes to
# HFS+ instead.

def read_report(path):
    """Parse the autotest file report. Returns (vals, [(dirID, name), ...])."""
    b = open(path, "rb").read()
    u32 = lambda o: int.from_bytes(b[o:o + 4], "big")
    if len(b) < 12 or b[:4] != b"UNCR":
        raise SystemExit(f"os9: {path} is not an autotest report")
    if u32(4) != 1:
        raise SystemExit(f"os9: report version {u32(4)}, expected 1")
    n = u32(8)
    vals = [u32(12 + 4 * i) for i in range(n)]
    o = 12 + 4 * n
    nrec = u32(o)
    o += 4
    recs = []
    for _ in range(nrec):
        dirid = u32(o)
        o += 4
        ln = b[o]
        o += 1
        recs.append((dirid, b[o:o + ln].decode("mac_roman")))
        o += ln
    return vals, recs


def mac_leaf(name, utf8=False):
    """A CLI output filename as the Mac shell would write it.

    ComponentToStr63() in mac/macextract_mac.c: undo the engine's '/'->':'
    swap and cap at 31 characters. That cap is the whole reason this run
    exists — HFS+ permits 255-character names, but a 68k application reaching
    it through the classic File Manager is still limited to 31, and whether
    that holds on HFS+ had never been checked.

    `utf8` folds a StuffIt 5 name into MacRoman first (Utf8ToMacRoman),
    which the shell does on HFS+ exactly as it does on HFS — the limit it
    is written for is the classic File Manager's, not the volume's.
    tools/vmac_check.py has both rules.

    **This runs on the archive's own spelling, before any Unicode
    normalization**, because that is what the shell folds: a DECOMPOSED
    name folds to one '_' per code point, so an NFC fold predicts one
    too few. Both callers normalized first until 2026-09-22, which was
    latent while no fixture on this tier had a non-ASCII StuffIt 5 name;
    `derived-800saywhat301j.sit` is the one that bites it, and they fold
    first and normalize the KEY afterwards now, as checkdisk.py does.
    The reference path stays unnormalized because it has to be
    opened."""
    return mac_component(name, utf8)


def report_present(xfer, workdir):
    """Has the Mac written its report file yet?

    Read from the HOST's copy of the transfer image while the guest is still
    running: QEMU's writeback cache means a flushed guest write is visible
    here. A torn read just reads as "not yet" and the loop tries again; the
    verdict always comes from the read after the emulator has exited."""
    home = os.path.join(workdir, "pollhome")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ, HOME=home)
    try:
        hfs = hfs_partition(xfer, os.path.join(workdir, ".poll.hfs"))
    except OSError:
        return False
    if subprocess.run(["hmount", hfs], capture_output=True,
                      env=env).returncode != 0:
        return False
    # -a for the reason _walk_volume gives: `hls` hides a file whose Finder
    # INVISIBLE bit is set. A report the shell had marked invisible would
    # never be seen here, and the symptom is a poll that never fires — a
    # timeout, not a wrong answer, but a timeout that would be read as the
    # application having hung.
    out = subprocess.run(["hls", "-a", "-1"], capture_output=True,
                         env=env).stdout
    subprocess.run(["humount"], capture_output=True, env=env)
    return b"report" in out


def wrapper_names(boot, workdir):
    """The root listing of the boot volume's HFS WRAPPER, or None.

    This is what turns "we extracted onto HFS+" from an inference into a
    measurement. The OS 9 boot volume is HFS+ inside an HFS wrapper; hfsutils
    can only see the wrapper, whose root holds one placeholder file. If the
    application had really written to a plain HFS volume, its output would be
    visible here. It is not — so the output went to the embedded HFS+ volume.

    Reading a claim off a signature word was tried instead and rejected: the
    classic File Manager reports 'BD' for an HFS+ volume for compatibility, so
    a negative there would mean nothing. This test has no such ambiguity, and
    misreading a signature at a fixed offset is precisely how the "the boot
    volume is plain HFS" claim went wrong in the first place (BLOCKERS.md).

    **`-a`, because this is a NEGATIVE.** The verdict is that none of the
    output is here, and `hls` without `-a` hides any file whose Finder
    invisible bit is set — so the listing this is read against was the
    one that makes the negative EASIEST to satisfy. Adding it can only
    lengthen the list and can only make the assertion harder to pass,
    which is the direction a negative wants (2026-09-22)."""
    home = os.path.join(workdir, "wraphome")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ, HOME=home)
    # hfsutils takes a partition number, so the 2 GB image needs no copy.
    if subprocess.run(["hmount", boot, "1"], capture_output=True,
                      env=env).returncode != 0:
        return None
    out = subprocess.run(["hls", "-a", "-1"], capture_output=True, env=env)
    subprocess.run(["humount"], capture_output=True, env=env)
    return [l.decode("mac_roman") for l in out.stdout.split(b"\n") if l.strip()]


def run_hfsplus(fixture, outdir, args):
    """Extract onto the HFS+ boot volume; verify through the report file."""
    os.makedirs(outdir, exist_ok=True)
    sys.path.insert(0, HERE)
    from run import build_autotest_app                       # noqa: E402
    appbin = build_autotest_app()

    # The volume MUST be called "In": that is the name the autotest build
    # looks for (FindVolWait). "Out" is the boot volume, renamed in the Finder
    # once the desktop is up.
    xfer = os.path.join(outdir, "transfer.img")
    R.sh(sys.executable, os.path.join(HERE, "mkapmdisk.py"), DISK, xfer,
         "32", "In",
         "--macbinary", f"{appbin}:MacExtract",
         "--data", f"{fixture}:archive.sit")

    verify_disk()
    boot = boot_copy(outdir)
    q = Qemu([boot, xfer], os.path.join(outdir, "mon.sock"))
    try:
        scratch = os.path.join(outdir, ".settle.png")
        waited = q.settle(scratch, timeout=args.boot_wait)
        if waited is None:
            raise SystemExit("os9: never reached the Finder desktop")
        print(f"os9: desktop settled after ~{waited:.0f}s")

        def shot(tag):
            p = os.path.join(outdir, tag + ".png")
            q.shot(p)
            return p

        shot("20-desktop")
        q.key("meta_l-q", "ret")                  # quit the Setup Assistant
        time.sleep(4)
        shot("21-assistant-quit")

        # Rename the boot volume `untitled` -> `Out`. Return on a selected
        # icon opens its name for editing with the whole name selected, so
        # typing replaces it; Return again commits. Classic Mac OS lets the
        # startup volume be renamed, unlike later systems.
        q.key("u", "n", "t")                      # select `untitled`
        time.sleep(1)
        q.key("ret")                              # open the name for editing
        time.sleep(2)
        q.key("shift-o", "u", "t")                # type `Out`
        q.key("ret")                              # commit
        time.sleep(3)
        shot("22-renamed")

        # Launch the autotest app off the In volume.
        q.key("i", "n", "meta_l-down")            # open the In volume
        frac, secs = q.wait_change(os.path.join(outdir, "22-renamed.png"),
                                   WINDOW_RECT, scratch, timeout=60.0)
        print(f"os9: In volume opened ({frac:.4f} changed in {secs:.0f}s)")
        shot("23-in-open")
        q.key("m", "a", "c", "meta_l-down")       # launch `MacExtract`

        # Wait for the REPORT FILE, not for anything on the screen.
        #
        # The autotest build paints nothing — no window, no dialog — and its
        # framebuffer grid is invisible here (see at_report_file). The first
        # version of this waited for the screen to change and then for it to
        # go black, and both timed out at their full 240 s on a run that had
        # in fact succeeded: eight minutes of waiting for proxies that could
        # not fire. QEMU's writeback cache makes the guest's writes visible in
        # the host's copy of the disk, so the harness can simply watch for the
        # artifact it is actually waiting for.
        started = time.time()
        seen = False
        while time.time() - started < args.launch_wait:
            time.sleep(10)
            if report_present(xfer, outdir):
                seen = True
                print(f"os9: report file written after "
                      f"~{time.time() - started:.0f}s")
                break
        if not seen:
            print(f"os9: no report file after {args.launch_wait:.0f}s — "
                  f"continuing, the read-back below is the verdict")
        shot("24-reported")
        if os.path.exists(scratch):
            os.remove(scratch)
    finally:
        q.close()

    # Before the boot copy is thrown away: what can a plain-HFS tool see on
    # the volume that was just written to?
    wrapper = wrapper_names(boot, outdir)
    if not args.keep_boot:
        try:
            os.remove(boot)
        except OSError:
            pass

    return verify_hfsplus(xfer, fixture, outdir, wrapper,
                          expect_refusal=args.expect_refusal)


def verify_hfsplus(xfer, fixture, workdir, wrapper=None, expect_refusal=False):
    """Read the report off the In volume and compare with the Linux engine.

    `expect_refusal` inverts the verdict for the memory-budget test: the run
    PASSES when the Mac declines the entry and writes nothing, provided the
    Linux engine DOES extract it. Without that second half the test would pass
    on an empty or broken archive, which is the usual way a negative test
    quietly stops testing anything."""
    lines, ok = [], True
    hfs = hfs_partition(xfer, os.path.join(workdir, "xfer.hfs"))
    home = os.path.join(workdir, "hfshome")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ, HOME=home)
    if subprocess.run(["hmount", hfs], capture_output=True,
                      env=env).returncode != 0:
        return False, ["cannot mount the In volume"]
    rep = os.path.join(workdir, "report")
    c = subprocess.run(["hcopy", "-r", "report", rep], capture_output=True,
                       env=env)
    subprocess.run(["humount"], capture_output=True, env=env)
    if c.returncode != 0:
        return False, ["the Mac wrote no report file — it never reached the "
                       "end of a run (screenshots in " + workdir + ")"]

    vals, recs = read_report(rep)
    nfiles, ret, errors, sdc, sdl, src, srl, peak = vals[:8]
    ret = ret - (1 << 32) if ret >= (1 << 31) else ret
    for code, what in ((-1001, 'no volume named "In"'),
                       (-1002, 'no volume named "Out" — the Finder rename of '
                               'the boot volume did not take')):
        if ret == code:
            return False, [f"the application reported: {what}"]

    ref = os.path.join(workdir, "linux-out")
    shutil.rmtree(ref, ignore_errors=True)
    os.makedirs(ref)
    cli = os.path.join(R.REPO, "build", "rel", "macextract")
    # Named what the Mac saw, for the reason verify_output() gives: this route
    # compares NAMES too (want_names, below), so gzip and .Z — which fall back
    # to the archive's filename — need the reference to be handed the same one.
    asmac = os.path.join(workdir, "as-the-mac-saw-it", ARCHIVE_ON_VOLUME)
    os.makedirs(os.path.dirname(asmac), exist_ok=True)
    shutil.copyfile(fixture, asmac)
    subprocess.run([cli, "x", "-nr", "--forks", "hidden", asmac, "-o", ref],
                   capture_output=True)

    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    from vmac_check import aggregate_dir                      # noqa: E402
    want_names = []
    enf, esdc, esdl, esrc, esrl = aggregate_dir(ref, want_names)

    lines.append(f"engine ret={ret} errors={errors}, peak heap "
                 f"{peak/1024.0:.1f} KB")

    if expect_refusal:
        # The SIZE-partition test: the application was given a partition too
        # small for this fixture's block, and the CORRECT outcome is a clean
        # per-entry refusal — UNC_OK for the archive, a counted error for the
        # entry, nothing written. A tiny peak heap is the diagnostic that the
        # block was rejected at REQUEST time rather than allocated and then
        # failed over: parser state only.
        checks = [("the Linux engine does extract this fixture", enf > 0),
                  ("the Mac wrote nothing", nfiles == 0),
                  ("the archive itself did not fail (ret == UNC_OK)", ret == 0),
                  ("at least one entry was counted as refused", errors >= 1)]
        for what, good in checks:
            ok = ok and good
            lines.append(f"  {'ok  ' if good else 'NO  '} {what}")
        lines.append(f"  Linux extracts {enf} file(s), {esdl + esrl} bytes; "
                     f"the Mac declined with a peak heap of {peak/1024.0:.1f} KB")
        return ok, lines

    for label, got, want in (("files", nfiles, enf),
                             ("data CRC sum", sdc, esdc),
                             ("data bytes", sdl, esdl),
                             ("rsrc CRC sum", src, esrc),
                             ("rsrc bytes", srl, esrl)):
        same = got == want
        ok = ok and same
        lines.append(f"  {label:>13}: Mac {got}  Linux {want}"
                     f"{'' if same else '   <- MISMATCH'}")
    if ret != 0 or errors:
        ok = False
        lines.append("  the engine did not return UNC_OK with zero per-entry "
                     "errors")

    # Names, which no aggregate can carry — and the point of an HFS+ run.
    got_names = sorted(n for _d, n in recs)
    exp_names = sorted(mac_leaf(n, names_are_utf8(fixture)) for n in want_names)
    if got_names == exp_names:
        lines.append(f"  {len(got_names)} name(s) on HFS+ exactly as the "
                     f"31-character rule predicts")
    else:
        ok = False
        lines.append(f"  NAME MISMATCH on HFS+")
        for g, e in zip(got_names, exp_names):
            if g != e:
                lines.append(f"    Mac {g!r}  expected {e!r}")
    trunc = [n for n in want_names if len(n) > 31]
    if trunc:
        lines.append(f"  {len(trunc)} name(s) were longer than 31 characters "
                     f"and had to be truncated, e.g. {trunc[0]!r}")

    # Was the output volume really HFS+? Measured, not assumed.
    if wrapper is None:
        ok = False
        lines.append("  cannot confirm the output volume was HFS+: the boot "
                     "image's HFS wrapper would not mount")
    else:
        leaked = sorted(set(got_names) & set(wrapper))
        placeholder = [w for w in wrapper if "my_files_gone" in w]
        if leaked:
            ok = False
            lines.append(f"  the output is visible in the plain-HFS WRAPPER "
                         f"({', '.join(leaked[:3])}) — it did not go to HFS+")
        elif not placeholder:
            ok = False
            lines.append(f"  the boot volume does not look like an HFS+ "
                         f"wrapper (root: {wrapper}); the HFS+ claim is "
                         f"unproven")
        else:
            lines.append(f"  output volume confirmed HFS+: the HFS wrapper "
                         f"still holds only {placeholder[0]!r}, so none of "
                         f"these {len(got_names)} files went to plain HFS")
    return ok, lines


# ---- The AUTOTEST build with BOTH volumes plain HFS ----------------------
#
# The one cell the Mac OS 9 DiskDoubler evidence is missing (BLOCKERS.md,
# *Mac OS 9.2 bombs on every DiskDoubler archive*). `--launch` runs the
# INTERACTIVE build onto a plain-HFS transfer volume and bombs; `--hfsplus`
# runs the AUTOTEST build onto the HFS+ boot volume and passes. Those two runs
# differ in the BUILD and in the VOLUME at once, so the pair convicts neither.
# This one runs the autotest build with a plain-HFS output volume — a third
# APM disk named `Out` — which leaves the build as the only difference from
# the run that bombs.
#
# It needs no Finder rename, so it is also the shortest route from the desktop
# to a running application of the three.

def run_autotest_hfs(fixture, outdir, args):
    """Autotest build, plain-HFS `In` and plain-HFS `Out`."""
    os.makedirs(outdir, exist_ok=True)
    sys.path.insert(0, HERE)
    from run import build_autotest_app                       # noqa: E402
    appbin = build_autotest_app(args.defines)

    inimg = os.path.join(outdir, "in.img")
    outimg = os.path.join(outdir, "out.img")
    R.sh(sys.executable, os.path.join(HERE, "mkapmdisk.py"), DISK, inimg,
         "32", "In",
         "--macbinary", f"{appbin}:MacExtract",
         "--data", f"{fixture}:{ARCHIVE_ON_VOLUME}")
    # Empty, and plain HFS. This is the volume under test.
    R.sh(sys.executable, os.path.join(HERE, "mkapmdisk.py"), DISK, outimg,
         "32", "Out")

    verify_disk()
    boot = boot_copy(outdir)
    q = Qemu([boot, inimg, outimg], os.path.join(outdir, "mon.sock"))
    try:
        scratch = os.path.join(outdir, ".settle.png")
        waited = q.settle(scratch, timeout=args.boot_wait)
        if waited is None:
            raise SystemExit("os9: never reached the Finder desktop")
        print(f"os9: desktop settled after ~{waited:.0f}s")

        def shot(tag):
            p = os.path.join(outdir, tag + ".png")
            q.shot(p)
            return p

        shot("20-desktop")
        q.key("meta_l-q", "ret")                  # quit the Setup Assistant
        time.sleep(4)
        shot("21-assistant-quit")

        q.key("i", "n", "meta_l-down")            # open the In volume
        frac, secs = q.wait_change(os.path.join(outdir, "21-assistant-quit.png"),
                                   WINDOW_RECT, scratch, timeout=60.0)
        print(f"os9: In volume opened ({frac:.4f} changed in {secs:.0f}s)")
        shot("22-in-open")
        q.key("m", "a", "c", "meta_l-down")       # launch `MacExtract`

        # Wait for the REPORT FILE, not for anything on the screen: the
        # autotest build paints nothing and its 1bpp grid is invisible on a
        # 32-bit screen, exactly as in run_hfsplus above.
        started = time.time()
        seen = False
        while time.time() - started < args.launch_wait:
            time.sleep(10)
            if report_present(inimg, outdir):
                seen = True
                print(f"os9: report file written after "
                      f"~{time.time() - started:.0f}s")
                break
        if not seen:
            print(f"os9: no report file after {args.launch_wait:.0f}s — "
                  f"continuing, the read-back below is the verdict")
        shot("23-reported")
        if os.path.exists(scratch):
            os.remove(scratch)
    finally:
        q.close()
        if not args.keep_boot:
            try:
                os.remove(boot)
            except OSError:
                pass

    return verify_autotest_hfs(inimg, outimg, fixture, outdir,
                               samevol="UNC_AT_SAMEVOL" in args.defines)


def verify_autotest_hfs(inimg, outimg, fixture, workdir, samevol=False):
    """The report off `In`, and then every fork off `Out`, byte for byte.

    Stricter than either existing Mac OS 9 path, because on this one both
    channels are open at once: `--hfsplus` can compare only the aggregate and
    the names, since no host tool opens HFS+, and `--launch` reads the volume
    but has no report to cross-check it against. A run that writes the right
    bytes to the wrong volume, or reports an aggregate its own output volume
    does not hold, fails here and would pass there.

    With `samevol` the application was built to extract onto the archive's OWN
    volume — what the interactive build does — so the output is read off `In`
    and `Out` is checked to be empty, which is what proves the switch took."""
    lines, ok = [], True
    home = os.path.join(workdir, "hfshome")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ, HOME=home)

    inhfs = hfs_partition(inimg, os.path.join(workdir, "in.hfs"))
    if subprocess.run(["hmount", inhfs], capture_output=True,
                      env=env).returncode != 0:
        return False, ["cannot mount the In volume"]
    rep = os.path.join(workdir, "report")
    c = subprocess.run(["hcopy", "-r", "report", rep], capture_output=True,
                       env=env)
    subprocess.run(["humount"], capture_output=True, env=env)
    if c.returncode != 0:
        return False, ["the Mac wrote no report file — it never reached the "
                       "end of a run (screenshots in " + workdir + ")"]

    vals, recs = read_report(rep)
    if len(vals) >= 14:                  # -D UNC_AT_BUDGET: run.budget_probe
        sv = [R.signed32(v) for v in vals]
        lines.append("probe: " + " ".join(
            [f"{k}={sv[8 + i]}" for i, k in enumerate(R.BUDGET_FIELDS)] +
            [f"bg={sv[7]}", f"short={sv[1]}", f"why={sv[5]}",
             f"free0={sv[3]}"]))
    nfiles, ret, errors, sdc, sdl, src, srl, peak = vals[:8]
    ret = ret - (1 << 32) if ret >= (1 << 31) else ret
    for code, what in ((-1001, 'no volume named "In"'),
                       (-1002, 'no volume named "Out" — the third disk did '
                               'not mount')):
        if ret == code:
            return False, [f"the application reported: {what}"]

    ref = os.path.join(workdir, "linux-out")
    shutil.rmtree(ref, ignore_errors=True)
    os.makedirs(ref)
    cli = os.path.join(R.REPO, "build", "rel", "macextract")
    # Against a copy named what the MAC saw, for the reason verify_output()
    # gives at length: gzip and .Z store no name and fall back to the archive
    # filename minus its extension, and mkapmdisk.py always writes the archive
    # to the volume as `archive.sit`. Given the fixture's own path instead,
    # the two sides derive different names for identical bytes and the run
    # reads as a failure — which is how this route scored 19/22 on a healthy
    # build until 2026-09-25. verify_output() has done this since 2026-08-08;
    # this verifier was written later and did not inherit it.
    asmac = os.path.join(workdir, "as-the-mac-saw-it", ARCHIVE_ON_VOLUME)
    os.makedirs(os.path.dirname(asmac), exist_ok=True)
    shutil.copyfile(fixture, asmac)
    # `-nr`: the AUTOTEST build calls RunExtract once and takes no envelopes
    # off, unlike the interactive build verify_output() grades.
    cr = subprocess.run([cli, "x", "-nr", "--forks", "hidden", asmac,
                         "-o", ref], capture_output=True)

    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    from vmac_check import aggregate_dir, mask_reserved        # noqa: E402
    enf, esdc, esdl, esrc, esrl = aggregate_dir(ref)

    lines.append(f"engine ret={ret} errors={errors}, peak heap "
                 f"{peak/1024.0:.1f} KB")
    for label, got, want in (("files", nfiles, enf),
                             ("data CRC sum", sdc, esdc),
                             ("data bytes", sdl, esdl),
                             ("rsrc CRC sum", src, esrc),
                             ("rsrc bytes", srl, esrl)):
        same = got == want
        ok = ok and same
        lines.append(f"  {label:>13}: Mac {got}  Linux {want}"
                     f"{'' if same else '   <- MISMATCH'}")
    # An archive the ENGINE refuses is not a failure of the Macintosh: this
    # harness grades the Mac against the same engine on Linux, and a
    # detect-only format (RAR, and every other row of FORMATS.md that is named
    # but not extracted) is refused on both sides with nothing written. The
    # reference exits non-zero and writes no file; the Mac must then report a
    # refusal of its own and write no file, and agreeing is a PASS. It stays
    # strict where it can: identical counts, a non-zero ret on the Mac, and
    # zero files on both sides, so a Macintosh that silently wrote nothing
    # while the engine extracted still fails.
    both_refuse = cr.returncode != 0 and enf == 0 and nfiles == 0 and ret != 0
    if both_refuse:
        why = (cr.stderr or b"").decode("utf-8", "replace").strip()
        lines.append(f"  both sides REFUSE this archive and wrote nothing "
                     f"(Mac ret={ret}; Linux: {why.splitlines()[-1] if why else 'no output'})")
    elif ret != 0 or errors:
        ok = False
        lines.append("  the engine did not return UNC_OK with zero per-entry "
                     "errors")

    # And now the half no HFS+ run can do: read the output volume back.
    outhfs = hfs_partition(outimg, os.path.join(workdir, "out.hfs"))
    if subprocess.run(["hmount", outhfs], capture_output=True,
                      env=env).returncode != 0:
        return False, lines + ["cannot mount the Out volume"]
    if samevol:
        # `Out` has to be MOUNTED — FindVolWait looks it up before the switch
        # redirects the sink — but nothing should have been written to it.
        stray = _walk_volume(env)
        subprocess.run(["humount"], capture_output=True, env=env)
        if stray:
            ok = False
            lines.append(f"UNC_AT_SAMEVOL did not take: {len(stray)} file(s) "
                         f"landed on the separate Out volume "
                         f"({', '.join(sorted(stray))})")
        else:
            lines.append("Out is empty, so the extraction really went to the "
                         "archive's own volume")
        if subprocess.run(["hmount", inhfs], capture_output=True,
                          env=env).returncode != 0:
            return False, lines + ["cannot re-mount the In volume"]
    names = _walk_volume(env)
    if samevol:
        # The report goes to the INPUT volume by design, so on this route it
        # sits among the output and is not part of it.
        names.pop("report", None)

    expected = set()
    for root, _d, files in os.walk(ref):
        for f in files:
            if f.startswith("._"):
                continue                  # sidecar; it travels with its data
            expected.add(os.path.relpath(os.path.join(root, f), ref))
    # Compare in the Mac's spelling, as verify_output() does: the shell writes
    # each component through ComponentToStr63(), and a StuffIt 5 name through
    # Utf8ToMacRoman before that — the fold first, then the normalization,
    # and the reference path kept unnormalized so it can be opened.
    mac_of = {}
    utf8 = names_are_utf8(fixture)
    for e in sorted(expected):
        mac_of["/".join(unicodedata.normalize("NFC", mac_leaf(c, utf8))
                        for c in e.split("/"))] = e
    expected = set(mac_of)

    lines.append(f"{len(names)} file(s) on the "
                 f"{'In' if samevol else 'Out'} volume: "
                 f"{', '.join(sorted(names)) or '(none)'}")
    missing = expected - set(names)
    extra = set(names) - expected
    if missing:
        ok = False
        lines.append(f"MISSING on the Mac: {', '.join(sorted(missing))}")
    if extra:
        ok = False
        lines.append(f"UNEXPECTED on the Mac: {', '.join(sorted(extra))}")

    for name in sorted(names):
        mb = os.path.join(workdir, "forks", name.replace("/", "_") + ".macbin")
        os.makedirs(os.path.dirname(mb), exist_ok=True)
        c = subprocess.run(["hcopy", "-m",
                            names[name].encode("mac_roman", "replace"),
                            mb.encode()], capture_output=True, env=env)
        if c.returncode != 0:
            ok = False
            lines.append(f"  {name}: cannot copy off the volume: "
                         f"{c.stderr.decode(errors='replace').strip()}")
            continue
        typ, crt, data, rsrc = macbinary_forks(mb)
        refrel = mac_of.get(name, name)     # the reference's spelling of it
        head, _, tail = refrel.rpartition("/")
        want_d = os.path.join(ref, refrel)
        want_r = os.path.join(ref, head, "._" + tail) if head \
            else os.path.join(ref, "._" + tail)
        for label, got, path, mask in (("data", data, want_d, False),
                                       ("rsrc", rsrc, want_r, True)):
            if not os.path.exists(path):
                if got:
                    ok = False
                    lines.append(f"  {name} {label}: Mac wrote {len(got)} B, "
                                 f"Linux wrote no such fork")
                continue
            expect = open(path, "rb").read()
            a, b = (mask_reserved(got), mask_reserved(expect)) if mask \
                else (got, expect)
            if a == b:
                lines.append(f"  {name} {label}: {len(got)} B byte-exact")
            else:
                ok = False
                lines.append(f"  {name} {label}: MISMATCH — Mac {len(got)} B, "
                             f"Linux {len(expect)} B")
        lines.append(f"  {name} type/creator: {_ostype(typ)}/{_ostype(crt)}")
    subprocess.run(["humount"], capture_output=True, env=env)
    return ok, lines


ENCRYPTED_PW = "hushnow"


def build_encrypted(workdir):
    """The encrypted subject, written here rather than taken from `fixtures/`.

    Nothing in the corpus is encrypted — measured, `lsar -j` over every
    fixture (FORMATS.md, *Encryption*) — so the only way to reach the
    application's password dialog is to generate the archive, exactly as the
    Mini vMac phase does (`interactive.py --password`). StuffIt classic's
    DES is the right one to bring here: its verifier, `'MKey'` 0, lives in the
    archive's RESOURCE fork, so this also asks whether the Mac shell finds key
    material in a fork that Linux only sees through an envelope.

    Returns the MacBinary file to put on the transfer volume, both forks in
    it. Regenerable on a clone, which the cached DropStuff specimens are not.
    """
    sys.path.insert(0, os.path.join(R.REPO, "tools"))
    import synth_crypt as SC
    import synth_wrapped as W
    sit, rsrc, _ = SC.build_sit_des(ENCRYPTED_PW.encode("mac_roman"))
    path = os.path.join(workdir, "secret.bin")
    os.makedirs(workdir, exist_ok=True)
    with open(path, "wb") as f:
        f.write(W.macbinary("archive.sit", sit, rsrc, b"SIT!", b"SIT!"))
    return path


def sha1(path):
    import hashlib
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_disk(fatal=True):
    """Is the master image still the one upstream published?

    It matters more here than it looks. Mac OS 9 writes to its boot volume as a
    matter of course — Desktop DB, temporary items, the "unmounted cleanly"
    flag — so a single boot leaves the image different from what was fetched,
    and a QEMU run that is killed rather than shut down leaves it dirty. That
    is why nothing may boot this file directly; see boot_copy()."""
    got = sha1(DISK)
    if got == DISK_SHA1:
        return True
    msg = (f"os9: {DISK} does not match the published SHA-1\n"
           f"os9:   want {DISK_SHA1}\n"
           f"os9:   got  {got}\n"
           f"os9: it has been written to — re-fetch it with --setup --force")
    if fatal:
        raise SystemExit(msg)
    print(msg)
    return False


def filesystem_kind(path):
    """The filesystem type `path` sits on, or "" when it cannot be told.

    Walks /proc/self/mounts for the longest mount point that is a prefix of
    the resolved path; no psutil, no findmnt, nothing this harness does not
    already depend on."""
    try:
        real = os.path.realpath(path)
        best, kind = "", ""
        with open("/proc/self/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mnt, ty = parts[1].replace("\\040", " "), parts[2]
                if (real == mnt or real.startswith(mnt.rstrip("/") + "/")) \
                        and len(mnt) >= len(best):
                    best, kind = mnt, ty
        return kind
    except OSError:
        return ""


def boot_copy(workdir):
    """A throwaway copy of the master image to actually boot.

    tools/vmac/run.py has done this since M10 ("every run starts from a
    pristine image: System 6 writes to the boot volume as it goes"), and
    BLOCKERS.md records that repeated boot-and-kill cycles corrupt it. That
    lesson was never carried over here: os9.py booted the master in place, so
    every run quietly damaged the one artifact it depends on, and there was no
    hash to notice."""
    dst = os.path.join(workdir, "boot.img")
    # A 2 GB copy per fixture onto a tmpfs is 2 GB of RAM per fixture, on a
    # host that is also running the emulator. Measured 2026-09-25 with -o
    # under /tmp on an 8 GB machine: the host went into swap and the guest
    # missed its settle timeout, which the harness can only report as "never
    # reached the Finder desktop" — a boot failure's symptom for a host
    # memory problem. Say so before spending the copy, since the fix is one
    # argument.
    fs = filesystem_kind(workdir)
    if fs in ("tmpfs", "ramfs"):
        print(f"os9: WARNING — {workdir} is on {fs}, which is RAM. Each "
              f"fixture copies a 2 GB boot image there and the guest runs "
              f"beside it; pass -o somewhere on disk if this host is small.")
    print(f"os9: copying the master image to {dst} (2 GB; the master is never booted)")
    shutil.copyfile(DISK, dst)
    return dst


def setup(force=False):
    os.makedirs(QEMU_HOME, exist_ok=True)
    if os.path.exists(DISK) and not force:
        if verify_disk(fatal=False):
            print(f"have {DISK}")
            return
        raise SystemExit("os9: refusing to overwrite silently — pass --force")
    print(f"fetching {DISK_URL} (2 GB)")
    subprocess.run(["curl", "-fsSL", "-o", DISK + ".part", DISK_URL], check=True)
    got = sha1(DISK + ".part")
    if got != DISK_SHA1:
        raise SystemExit(f"os9: SHA-1 mismatch on the download: got {got}, "
                         f"want {DISK_SHA1} — check upstream by hand")
    os.rename(DISK + ".part", DISK)
    print(f"os9: ready — {DISK}")


def run_one(fixture, appbin, outdir, args):
    """One fixture: build the transfer disk, boot, extract, check.

    Every fixture gets its own boot from a pristine copy of the master image.
    That is not tidiness — Mac OS 9 writes to its boot volume as it goes, and
    a run that is killed rather than shut down leaves it dirty, which is how
    the master drifted from upstream before verify_disk() existed."""
    os.makedirs(outdir, exist_ok=True)
    xfer = os.path.join(outdir, "transfer.img")
    # An encrypted StuffIt classic keeps its verifier in the archive's
    # RESOURCE fork, so that subject goes onto the volume as MacBinary; every
    # other fixture is a data fork and nothing else.
    carry = (["--macbinary", f"{fixture}:archive.sit"] if args.encrypted
             else ["--data", f"{fixture}:archive.sit"])
    R.sh(sys.executable, os.path.join(HERE, "mkapmdisk.py"), DISK, xfer,
         "32", "MacExtract",
         "--macbinary", f"{appbin}:MacExtract", *carry)

    verify_disk()
    boot = boot_copy(outdir)
    q = Qemu([boot, xfer], os.path.join(outdir, "mon.sock"),
             pointer=args.cancel_click)
    try:
        # use_absolute_pointer() is deliberately NOT called. It succeeds — QEMU
        # really does offer the tablet and really does select it — and it buys
        # nothing, because the guest does not position the cursor from it
        # (XFER_VOLUME_ICON). Calling it would only give this run a way to
        # abort over a device it no longer uses.
        scratch = os.path.join(outdir, ".settle.png")
        waited = q.settle(scratch, timeout=args.boot_wait)
        if waited is None:
            raise SystemExit(
                f"os9: the screen never stopped changing within "
                f"{args.boot_wait:.0f}s, or qemu exited. A loaded host boots "
                f"very much more slowly than the ~110 s an idle one takes; "
                f"raise --boot-wait rather than assuming the guest is broken.")
        print(f"os9: desktop settled after ~{waited:.0f}s")
        print(q.shot(os.path.join(outdir, "desktop.png")))

        if args.launch:
            # Drive the Finder from the KEYBOARD. There is no way to avoid the
            # Finder here — the boot volume is HFS+ inside an HFS wrapper and
            # nothing in this environment can write HFS+, so the application
            # cannot be placed in Startup Items offline (BLOCKERS.md) — but
            # there is a way to avoid the mouse, which is just as well, because
            # the mouse does not work in this guest. See XFER_VOLUME_ICON.
            launch_by_keyboard(q, outdir, wait=args.launch_wait,
                               cancel=args.cancel or args.cancel_click,
                               click=args.cancel_click,
                               click_at=args.click_at,
                               password=ENCRYPTED_PW if args.encrypted else None)
        if os.path.exists(scratch):
            os.remove(scratch)
    finally:
        q.close()
        if not args.keep_boot:
            # 2 GB per fixture; a sweep fills the disk otherwise.
            try:
                os.remove(boot)
            except OSError:
                pass

    if not args.launch:
        print("os9: the transfer volume should be on the desktop. Pass "
              "--launch to run the application and check what it wrote.")
        return True, []

    # Only now that the emulator is gone: the transfer volume is a plain file
    # on the host, so what the Mac wrote can be compared byte for byte with
    # what the same engine writes on Linux. This is also the check on whether
    # the guest flushed — an unflushed volume shows up here as a failed mount
    # or a missing file, not as a silent pass.
    cancelled = args.cancel or args.cancel_click
    ok, lines = verify_output(xfer, fixture, outdir, partial=cancelled,
                              password=ENCRYPTED_PW if args.encrypted else None)
    print(f"\nos9: {'PASS' if ok else 'FAIL'} — "
          f"{os.path.basename(fixture)} on Mac OS 9.2"
          f"{', cancelled part way' if cancelled else ''}"
          f"{' (the BUTTON)' if args.cancel_click else ''}"
          f"{', decrypted through the password dialog' if args.encrypted else ''}")
    for l in lines:
        print("os9: " + l)
    print(f"os9: screenshots in {outdir}")
    return ok, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixture", nargs="?", help="archive to put on the transfer disk")
    ap.add_argument("--force", action="store_true",
                    help="with --setup, re-fetch even if a copy is present "
                         "(use when verify_disk() reports drift)")
    ap.add_argument("--setup", action="store_true", help="fetch the Mac OS 9 disk")
    ap.add_argument("--list", metavar="FILE",
                    help="a file of fixture names, one per line, '#' comments "
                         "ignored — the same format as tools/vmac/sample.txt. "
                         "Each gets its own boot from a pristine image")
    ap.add_argument("--hfsplus", action="store_true",
                    help="extract onto the HFS+ BOOT volume instead of the "
                         "HFS transfer volume, by renaming it to `Out` in the "
                         "Finder and running the autotest build. The result "
                         "comes back as a report FILE on the input volume, "
                         "because nothing on this host can read HFS+")
    ap.add_argument("--autotest", action="store_true",
                    help="run the AUTOTEST build with BOTH volumes plain HFS "
                         "— a third disk named `Out` — instead of the "
                         "interactive build. The one combination --launch and "
                         "--hfsplus between them do not cover: it changes the "
                         "BUILD and nothing else against --launch.")
    ap.add_argument("-D", "--define", dest="defines", action="append",
                    default=[], metavar="SWITCH",
                    help="with --autotest: a build switch passed to "
                         "build_autotest_app, e.g. -D UNC_AT_SAMEVOL to "
                         "extract onto the archive's OWN volume, which is "
                         "what the interactive application does")
    ap.add_argument("--expect-refusal", action="store_true",
                    help="with --hfsplus: PASS when the Mac DECLINES the "
                         "archive and writes nothing, provided the Linux "
                         "engine extracts it. For the SIZE-partition test, "
                         "where a clean per-entry refusal is the correct "
                         "outcome — see tools/vmac/README.md")
    ap.add_argument("--keep-boot", action="store_true",
                    help="keep each run's 2 GB boot copy instead of deleting "
                         "it (a sweep would otherwise need 2 GB per fixture)")
    # Under the cache dir, not the working directory: a run puts a 2 GB boot
    # copy and a 34 MB transfer image here, and neither belongs in the repo.
    ap.add_argument("-o", "--outdir",
                    default=os.path.join(os.path.dirname(R.VMAC_HOME),
                                         "os9-shots"))
    ap.add_argument("--launch", action="store_true",
                    help="after the desktop settles, open the transfer volume "
                         "from the keyboard, launch the application, extract "
                         "the archive, and then compare both forks of what it "
                         "wrote against the same engine's Linux output. Exits "
                         "non-zero on a mismatch")
    ap.add_argument("--cancel", action="store_true",
                    help="with --launch: interrupt the extraction with Cmd-. "
                         "while the progress dialog is up, instead of waiting "
                         "it out. PASSES when what the Mac wrote is a strict, "
                         "non-empty subset of the entries and every file in it "
                         "is byte-exact; a cancel that arrives after the last "
                         "entry fails as a useless test rather than passing. "
                         "Needs an archive slow enough to catch — seconds is "
                         "not enough on this machine")
    ap.add_argument("--cancel-click", action="store_true",
                    help="like --cancel, but through the progress dialog's "
                         "Cancel BUTTON instead of Cmd-. — a different branch "
                         "of ProgressPump(). Boots with a relative usb-mouse "
                         "and parks the cursor on the button while the "
                         "destination dialog is still up, because positioning "
                         "costs ~40 s and the progress dialog does not last "
                         "that long. Same pass condition as --cancel")
    ap.add_argument("--encrypted", action="store_true",
                    help="with --launch: extract an ENCRYPTED archive and "
                         "answer the application's password dialog. Needs no "
                         "fixture — nothing in the corpus is encrypted, so the "
                         "subject is generated by tools/synth_crypt.py: a "
                         "StuffIt classic whose verifier is in its RESOURCE "
                         "fork, carried onto the volume as MacBinary. A WRONG "
                         "password is typed and refused first")
    ap.add_argument("--click-at", metavar="X,Y", default=None,
                    help="with --cancel-click: click somewhere OTHER than the "
                         "Cancel button. This is the control, and it is the "
                         "only thing that establishes the test can fail: "
                         "`--click-at 150,168` presses the progress dialog's "
                         "blank background, the extraction must then run to "
                         "completion, and the run must FAIL as a cancel that "
                         "arrived too late")
    ap.add_argument("--launch-wait", type=float, default=240.0,
                    help="seconds to allow each of the application launch and "
                         "the extraction; the 68LC040 emulator makes both "
                         "slower than they are natively. Waited for, not slept")
    ap.add_argument("--boot-wait", type=float, default=1800.0,
                    help="host seconds to allow for the desktop to SETTLE (the "
                         "harness waits for the screen to stop changing rather "
                         "than sleeping a fixed time). An idle host reaches the "
                         "desktop in under two minutes; a loaded one takes very "
                         "much longer, so this bound is generous on purpose")
    args = ap.parse_args()

    if args.setup:
        setup(args.force)
        return 0
    if not (args.fixture or args.list or args.encrypted):
        ap.error("give a fixture, --list, --encrypted or --setup")
    if args.encrypted:
        if not args.launch:
            ap.error("--encrypted drives the password dialog, so it needs "
                     "--launch")
        if args.hfsplus or args.cancel or args.cancel_click:
            ap.error("--encrypted brings its own subject and runs it to "
                     "completion; it does not combine with --hfsplus or "
                     "either cancel route")
        if args.fixture or args.list:
            ap.error("--encrypted generates its own archive — nothing in the "
                     "corpus is encrypted — so it takes no fixture")
    if args.autotest:
        if args.hfsplus or args.launch or args.cancel or args.cancel_click \
                or args.encrypted:
            ap.error("--autotest runs the autotest build on its own volumes; "
                     "it does not combine with --launch, --hfsplus, either "
                     "cancel route or --encrypted")
    elif args.defines:
        ap.error("-D is a build switch for the autotest application, so it "
                 "means nothing without --autotest")
    if (args.cancel or args.cancel_click) and not args.launch:
        ap.error("--cancel drives the application, so it needs --launch")
    if (args.cancel or args.cancel_click) and args.hfsplus:
        ap.error("--cancel drives the INTERACTIVE application; --hfsplus "
                 "runs the autotest build, which has no progress dialog")
    if args.click_at and not args.cancel_click:
        ap.error("--click-at is the control for --cancel-click, and means "
                 "nothing without it")
    if args.click_at:
        try:
            x, y = (int(v) for v in args.click_at.split(","))
        except ValueError:
            ap.error("--click-at wants X,Y in screen pixels, e.g. 150,168")
        args.click_at = (x, y)
    else:
        args.click_at = CANCEL_BUTTON
    if args.cancel and args.cancel_click:
        ap.error("--cancel and --cancel-click are two routes to the same "
                 "cancel; run them one at a time so the log says which one "
                 "was tested")
    if not os.path.exists(DISK):
        raise SystemExit("os9: no Mac OS 9 disk — run tools/vmac/os9.py --setup")

    fixtures = [args.fixture] if args.fixture else []
    if args.encrypted:
        fixtures = [build_encrypted(args.outdir)]
    if args.list:
        with open(args.list) as f:
            for line in f:
                name = line.split("#")[0].strip()
                if name:
                    fixtures.append(os.path.join(R.REPO, "fixtures", name))
    missing = [f for f in fixtures if not os.path.exists(f)]
    if missing:
        raise SystemExit("os9: no such fixture: " + ", ".join(missing))

    os.makedirs(args.outdir, exist_ok=True)
    sys.path.insert(0, HERE)
    appbin = None
    if not (args.hfsplus or args.autotest):   # both build the autotest app
        from interactive import build_interactive_app
        appbin = build_interactive_app()

    results = []
    for fixture in fixtures:
        name = os.path.basename(fixture)
        out = args.outdir if len(fixtures) == 1 else os.path.join(args.outdir, name)
        if args.autotest:
            ok, lines = run_autotest_hfs(fixture, out, args)
            where = ("the archive's own volume"
                     if "UNC_AT_SAMEVOL" in args.defines
                     else "a plain-HFS Out volume")
            print(f"\nos9: {'PASS' if ok else 'FAIL'} — {name}, autotest "
                  f"build onto {where}")
            for l in lines:
                print("os9: " + l)
            print(f"os9: screenshots in {out}")
        elif args.hfsplus:
            ok, lines = run_hfsplus(fixture, out, args)
            print(f"\nos9: {'PASS' if ok else 'FAIL'} — {name} onto HFS+")
            for l in lines:
                print("os9: " + l)
            print(f"os9: screenshots in {out}")
        else:
            ok, _ = run_one(fixture, appbin, out, args)
        results.append((name, ok))

    if len(results) > 1:
        print("\nos9: Mac OS 9.2 results")
        for name, ok in results:
            print(f"os9:   {'PASS' if ok else 'FAIL'}  {name}")
        print(f"os9: {sum(1 for _, ok in results if ok)}/{len(results)} "
              f"byte-exact against the Linux engine")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
