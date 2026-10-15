#!/usr/bin/env python3
"""guard.py — every emulator and X server a harness starts, bounded and reaped.
Ported from MacMount's tools/guard.py (0BSD).

One day of Mac OS 9 runs on this host left 10.5 GiB of disk images in a
tmpfs /tmp and froze the machine: each run copied its images into a work
directory nobody deleted, and a shell loop retried every timeout.  So
every process a harness starts goes through here, and four rules hold for
all of them:

  - **A hard limit.**  The command runs under `timeout --kill-after=10`,
    so it dies at `limit` seconds even if the Python that started it hangs
    or is SIGKILLed.  A run that hits it is a FAILED run to diagnose —
    `timed_out()` says so — never one to retry.
  - **The whole process group.**  It is started in a session of its own
    and `reap()` signals the group, TERM then KILL.  `atexit` reaps
    whatever is still alive, SIGTERM/SIGINT/SIGHUP become SystemExit so
    every `finally` runs, and the child carries PR_SET_PDEATHSIG, so even
    a harness killed with -9 takes its emulator with it.
  - **Temporary files in the repository.**  `TMP` is `<repo>/.tmp/`,
    gitignored.  `tempfile` is pointed at `.tmp/proc-<pid>/`, which goes
    at exit (and on the next import if this process was killed), so not
    even a `mkdtemp()` nobody removes reaches /tmp or outlives its
    process.  `work_dir()` refuses /tmp outright.
  - **Only the last few runs.**  `run_dir()` makes one directory per run
    and prunes older ones of the same tag down to `KEEP`.  Every directory
    `run_dir()` or `work_dir()` hands out is `finish()`ed at exit — its
    images deleted, its screenshots and logs kept — however the harness
    left; HARNESS_KEEP_IMAGES=1 keeps the images, for a run being
    debugged.

What this cannot see: a process the harness started WITHOUT `spawn()`,
and a grandchild that leaves the group with setsid() of its own.  Neither
QEMU, Mini vMac, Basilisk II nor Xvfb does that.

Port it, do not import it across repositories: each project keeps its own
copy so that its `.tmp/` is its own.
"""
import atexit
import ctypes
import os
import shutil
import signal
import subprocess
import tempfile
import time


def _repo():
    d = os.path.dirname(os.path.abspath(__file__))
    while d != "/" and not os.path.exists(os.path.join(d, ".git")):
        d = os.path.dirname(d)
    return d if d != "/" else os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))


REPO = _repo()
TMP = os.path.join(REPO, ".tmp")
PROC_TMP = os.path.join(TMP, "proc-%d" % os.getpid())
os.makedirs(PROC_TMP, exist_ok=True)
tempfile.tempdir = PROC_TMP
os.environ["TMPDIR"] = PROC_TMP     # and for anything a harness shells out to

# Seconds.  The longest single run any harness here has needed is a Mac OS
# 9 boot on a contended host plus its steps; nothing gets longer than this
# without asking for it by name.
LIMIT = int(os.environ.get("HARNESS_LIMIT", "900"))
KEEP = int(os.environ.get("HARNESS_KEEP", "3"))

# What finish() deletes: anything that is an image or a socket, or simply
# large.  Screenshots, logs and reports stay.
BULKY = (".iso", ".dsk", ".img", ".hfv", ".qcow2", ".raw", ".scratch",
         ".sock", ".ppm", ".toast", ".cdr", ".image")
BIG = 8 << 20

_live = set()
_runs = []
PR_SET_PDEATHSIG = 1


def _child_setup():
    # The signal timeout(1) forwards and then follows with KILL.
    ctypes.CDLL(None).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)


def spawn(cmd, limit=None, **kw):
    """subprocess.Popen, under a hard limit, in a process group of its own."""
    limit = int(limit or LIMIT)
    kw.pop("start_new_session", None)
    p = subprocess.Popen(["timeout", "--kill-after=10", str(limit)]
                         + [str(c) for c in cmd],
                         start_new_session=True, preexec_fn=_child_setup, **kw)
    p.limit = limit
    _live.add(p)
    return p


def timed_out(p):
    """Did the hard limit end it?  124 is timeout(1)'s TERM; 137 its KILL."""
    return p.returncode in (124, 137)


def why(p, what="the emulator"):
    if timed_out(p):
        return ("%s hit the hard limit of %ds — a failed run to diagnose, "
                "not to retry" % (what, p.limit))
    return "%s exited early (rc=%s)" % (what, p.returncode)


def reap(p, grace=5.0):
    """Stop p's whole process group: TERM, `grace` seconds, then KILL."""
    if p is None:
        return
    _live.discard(p)
    if p.poll() is not None:
        # timeout(1) has exited, and with it everything it ran: it only
        # exits once its command has.  The pid may already be reused, so
        # nothing is signalled.
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            return
        try:
            p.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue
    p.wait()


def _reap_all():
    for p in list(_live):
        reap(p, grace=2.0)


def _drop_proc_tmp():
    shutil.rmtree(PROC_TMP, ignore_errors=True)


def _finish_runs():
    if os.environ.get("HARNESS_KEEP_IMAGES") == "1":
        return
    for d in _runs:
        if os.path.isdir(d):
            finish(d)


# Registered in reverse of the order they run: reap every process, then
# delete the runs' images, then this process's own temporary directory.
atexit.register(_drop_proc_tmp)
atexit.register(_finish_runs)
atexit.register(_reap_all)


def _die(signum, frame):
    raise SystemExit("interrupted by signal %d" % signum)


for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(_sig, _die)


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def prune(tag, keep=KEEP):
    """Delete all but the newest `keep` run directories of `tag` whose run
    is over.  A directory whose process is still alive is never touched,
    so a concurrent run keeps its files."""
    mine = sorted(d for d in os.listdir(TMP) if d.startswith(tag + "-"))
    over = []
    for d in mine:
        try:
            pid = int(d.rsplit("-", 1)[1])
        except ValueError:
            continue
        if not _alive(pid) or pid == os.getpid():
            over.append(d)
    for d in over[:max(0, len(over) - keep)]:
        shutil.rmtree(os.path.join(TMP, d), ignore_errors=True)


def _prune_proc_tmp():
    for d in os.listdir(TMP):
        if d.startswith("proc-"):
            try:
                pid = int(d[5:])
            except ValueError:
                continue
            if pid != os.getpid() and not _alive(pid):
                shutil.rmtree(os.path.join(TMP, d), ignore_errors=True)


_prune_proc_tmp()


def run_dir(tag):
    """A fresh `<repo>/.tmp/<tag>-<time>-<pid>/`, older runs pruned so this
    one makes KEEP."""
    prune(tag, KEEP - 1)
    d = os.path.join(TMP, "%s-%s-%d" % (tag, time.strftime("%Y%m%d-%H%M%S"),
                                        os.getpid()))
    os.makedirs(d, exist_ok=True)
    _runs.append(d)
    return d


def work_dir(path, tag):
    """The caller's --work, or a fresh run_dir(tag).  Never /tmp: a tmpfs
    there is RAM, and that is where 10.5 GiB of images froze the host."""
    if not path:
        return run_dir(tag)
    real = os.path.realpath(path)
    for bad in ("/tmp", "/dev/shm", "/run", "/var/tmp"):
        if real == bad or real.startswith(bad + "/"):
            raise SystemExit("--work %s is under %s; leave --work out and "
                             "the run gets a directory under %s"
                             % (path, bad, TMP))
    os.makedirs(real, exist_ok=True)
    _runs.append(real)
    return real


def finish(d):
    """Delete a run's images, sockets and anything large; keep the rest.
    Returns the bytes freed."""
    freed = 0
    for root, dirs, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            try:
                st = os.lstat(p)
            except FileNotFoundError:
                continue
            if f.endswith(BULKY) or st.st_size > BIG:
                freed += st.st_blocks * 512
                os.unlink(p)
    return freed
