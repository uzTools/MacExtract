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
    def __init__(self, disks, monitor, tablet=True):
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
        argv = ["qemu-system-ppc", "-M", "mac99,via=pmu", "-m", "512",
                "-boot", "c", "-g", "1024x768x32", "-display", "none",
                "-monitor", f"unix:{monitor},server,nowait"]
        if tablet:
            argv[-2:-2] = ["-device", "usb-tablet"]
        for i, d in enumerate(disks):
            argv += ["-drive", f"file={d},format=raw,media=disk,index={i}"]
        self.mon_path = monitor
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


def launch_by_keyboard(q, outdir, wait=240.0):
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
      4. Return again dismisses the result alert, and Cmd-Q quits.

    Returns the list of (label, screenshot) pairs it captured."""
    shots = []

    def shot(tag):
        p = os.path.join(outdir, tag + ".png")
        q.shot(p)
        shots.append((tag, p))
        return p

    scratch = os.path.join(outdir, ".wait.png")

    def step(before, label, timeout):
        """Wait for the screen to react, and say so either way.

        A step that times out does NOT stop the run: the screenshots are worth
        having, and the verdict comes from verify_output() reading the disk,
        not from a pixel threshold. But it must be visible in the log, because
        "the next screenshot looks wrong" is exactly the non-observation this
        harness spent five boots learning not to reason from."""
        frac, secs = q.wait_change(before, WINDOW_RECT, scratch, timeout=timeout)
        verdict = "" if frac >= 0.02 else "  <- NO CHANGE, continuing anyway"
        print(f"os9: {label} ({frac:.4f} changed in {secs:.0f}s){verdict}")

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
    step(sfg, "extraction reported", wait)
    shot("14-result")

    q.key("ret")                                 # dismiss the alert
    time.sleep(3)
    q.key("meta_l-q")                            # quit the application
    time.sleep(8)
    shot("15-quit")
    if os.path.exists(scratch):
        os.remove(scratch)
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
NOT_OUTPUT = {"archive.sit", "MacExtract", "Desktop DB", "Desktop DF",
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

    `hls` takes an HFS path, so no `hcd` state is involved. Returns paths in
    POSIX form; `_mac_path()` turns one back into the colon form hcopy wants.
    """
    if depth > 8:                       # archives here are not this deep
        return []
    out = []
    listing = subprocess.run(["hls", "-F", "-1"] + ([mac_dir] if mac_dir else []),
                             capture_output=True, env=env)
    for raw in listing.stdout.split(b"\n"):
        entry = raw.rstrip().decode("mac_roman")
        if not entry:
            continue
        isdir = entry.endswith(":")
        name = entry[:-1] if isdir or entry.endswith("*") else entry
        if depth == 0 and name in NOT_OUTPUT:
            continue
        rel = f"{mac_dir_to_rel(mac_dir)}/{name}" if mac_dir else name
        if isdir:
            out += _walk_volume(env, _mac_path(rel) + ":", depth + 1)
        else:
            out.append(unicodedata.normalize("NFC", rel))
    return out


def _mac_path(rel):
    """A POSIX-ish relative path as an absolute HFS path (`:a:b:c`)."""
    return ":" + rel.replace("/", ":")


def mac_dir_to_rel(mac_dir):
    """`:bin:` back to `bin`."""
    return mac_dir.strip(":").replace(":", "/")


def verify_output(xfer, fixture, workdir):
    """Compare what the Mac wrote against the same engine's Linux output.

    Returns (ok, list of report lines). The reference is `macextract x -nr`:
    single-level, because the Mac shell calls unc_extract once with no
    auto-unwrap loop — the same reasoning, and the same flag, as
    tools/vmac_check.py."""
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
    subprocess.run([cli, "x", "-nr", "--forks", "hidden", asmac, "-o", ref],
                   capture_output=True)

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
    expected = {unicodedata.normalize("NFC", e) for e in expected}

    # The Mac writes each COMPONENT the way ComponentToStr63() does — the
    # engine's ':' back to '/', cut at 31 characters — so the two sides
    # spell some names differently while both being right. `mac_of` maps
    # the name the Mac would write to the reference path it came from,
    # and everything below compares in the Mac's spelling. Added
    # 2026-08-27 with the SuperDisk! fixture, whose archive holds
    # `SD! Utilities : MacWrite`: a colon on Linux and a slash on the
    # Mac, which the set comparison would otherwise call one missing file
    # and one unexpected one. The HFS+ path has done this since M12.
    mac_of = {}
    collided = {}
    for e in sorted(expected):
        m = "/".join(mac_leaf(c) for c in e.split("/"))
        if m in mac_of:
            collided[m] = [mac_of[m], e]
        mac_of[m] = e
    expected = set(mac_of)

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
            f"to one name on the Mac, and the shell does not number a "
            f"collision (OPEN_ITEMS.md), so one file is lost and the harness "
            f"cannot say which."]
    missing = expected - set(names)
    extra = set(names) - expected
    if missing:
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
                            _mac_path(name).encode("mac_roman", "replace"),
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


def mac_leaf(name):
    """A CLI output filename as the Mac shell would write it.

    ComponentToStr63() in mac/macextract_mac.c: undo the engine's '/'->':'
    swap and cap at 31 characters. That cap is the whole reason this run
    exists — HFS+ permits 255-character names, but a 68k application reaching
    it through the classic File Manager is still limited to 31, and whether
    that holds on HFS+ had never been checked."""
    return name.replace(":", "/")[:31] or "_"


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
    out = subprocess.run(["hls", "-1"], capture_output=True, env=env).stdout
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
    volume is plain HFS" claim went wrong in the first place (BLOCKERS.md)."""
    home = os.path.join(workdir, "wraphome")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ, HOME=home)
    # hfsutils takes a partition number, so the 2 GB image needs no copy.
    if subprocess.run(["hmount", boot, "1"], capture_output=True,
                      env=env).returncode != 0:
        return None
    out = subprocess.run(["hls", "-1"], capture_output=True, env=env)
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
    subprocess.run([cli, "x", "-nr", "--forks", "hidden", fixture, "-o", ref],
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
    exp_names = sorted(mac_leaf(n) for n in want_names)
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


def boot_copy(workdir):
    """A throwaway copy of the master image to actually boot.

    tools/vmac/run.py has done this since M10 ("every run starts from a
    pristine image: System 6 writes to the boot volume as it goes"), and
    BLOCKERS.md records that repeated boot-and-kill cycles corrupt it. That
    lesson was never carried over here: os9.py booted the master in place, so
    every run quietly damaged the one artifact it depends on, and there was no
    hash to notice."""
    dst = os.path.join(workdir, "boot.img")
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
    R.sh(sys.executable, os.path.join(HERE, "mkapmdisk.py"), DISK, xfer,
         "32", "MacExtract",
         "--macbinary", f"{appbin}:MacExtract",
         "--data", f"{fixture}:archive.sit")

    verify_disk()
    boot = boot_copy(outdir)
    q = Qemu([boot, xfer], os.path.join(outdir, "mon.sock"))
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
            launch_by_keyboard(q, outdir, wait=args.launch_wait)
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
    ok, lines = verify_output(xfer, fixture, outdir)
    print(f"\nos9: {'PASS' if ok else 'FAIL'} — "
          f"{os.path.basename(fixture)} on Mac OS 9.2")
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
    if not (args.fixture or args.list):
        ap.error("give a fixture, --list, or --setup")
    if not os.path.exists(DISK):
        raise SystemExit("os9: no Mac OS 9 disk — run tools/vmac/os9.py --setup")

    fixtures = [args.fixture] if args.fixture else []
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
    if not args.hfsplus:            # --hfsplus builds the autotest app instead
        from interactive import build_interactive_app
        appbin = build_interactive_app()

    results = []
    for fixture in fixtures:
        name = os.path.basename(fixture)
        out = args.outdir if len(fixtures) == 1 else os.path.join(args.outdir, name)
        if args.hfsplus:
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
