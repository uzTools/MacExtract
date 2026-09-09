#!/usr/bin/env python3
"""run_mime.py — base64 and MIME, graded by two other implementations.

The corpus has neither: no `.mim`, no `.b64` and no saved mail message
(measured 2026-08-26 — the sniff sweep over all 915 fixture files claims
none of them). So every case here is generated, and a generated case
graded by its own generator proves nothing (DECISIONS.md, M13). Two
independent readers grade instead:

  * **munpack 1.6** (CMU), which is where src/fmt_mime.c is transcribed
    from, built by tools/build_mpack.sh. It reads the same message and
    has to produce the same bytes.
  * **deark**, an independent base64 implementation, built by
    tools/build_deark.sh and already this project's third oracle for
    ARC method 0x0b.

What neither can grade is the RESOURCE fork: the Unix munpack has no
notion of one and writes an application/applefile part out whole, deark
has no notion of one either. The appledouble cases carry their own
adjudicator instead — the applefile part is a plain AppleDouble file,
and `macextract` reads one of those through a decoder (fmt_applesingle.c)
that 932 corpus fixtures grade against `unar`. TESTING.md says this in
the same words.

Skips cleanly, and says so, when the references are not there.
"""
import base64
import binascii
import os
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")

DATA = bytes(range(256)) * 5 + b"trailing\r"
RSRC = b"RESOURCE FORK " * 31
TEXT = b"The note the sender typed.\r\nTwo lines of it.\r\n"


def build(script, binary, srcdir):
    """An oracle, and WHY it is not there when it is not.

    Returns (path, None) when the binary is available, (None, None) when
    the reference tree was never fetched — a fresh clone, and a real
    skip — and (None, why) when the tree IS there and the build failed.
    Those last two are not the same thing and this used to report them
    as one: a build that died on a timestamp race came out as "no
    reference/mpack" about a directory that was right there, and the
    suite then returned 0 and CI stayed green with no second
    implementation grading anything (DECISIONS.md 2026-09-09).
    """
    path = os.path.abspath(os.path.join(ROOT, binary))
    if os.path.exists(path):
        return path, None
    if not os.path.isdir(srcdir):
        return None, None
    r = subprocess.run(["sh", os.path.join(ROOT, "tools", script)],
                       capture_output=True)
    if r.returncode == 0 and os.path.exists(path):
        return path, None
    why = (r.stderr or r.stdout).decode("utf-8", "replace").strip()
    return None, why or "%s exited %d and said nothing" % (script,
                                                           r.returncode)


def oracle_gone(name, tree, why):
    """The message for a reference that is present and will not build.
    Shared wording, because three suites ask the same question."""
    print("run_%s: %s is present and its oracle will not build, so "
          "nothing here is graded against a second implementation."
          % (name, tree))
    for line in why.splitlines():
        print("run_%s:   %s" % (name, line))
    print("run_%s: fix the build, or delete %s to make this a skip."
          % (name, tree))


def b64(data, eol=b"\r\n"):
    return base64.encodebytes(data).replace(b"\n", eol)


def uu(name, data, eol=b"\r\n"):
    """A uuencoded document, as uuencode(1) writes one: the "begin" line
    with mode and name, 45 payload bytes per line, the zero-length line,
    "end"."""
    out = [b"begin 644 " + name]
    for i in range(0, len(data), 45):
        out.append(binascii.b2a_uu(data[i:i + 45]).rstrip(b"\n"))
    out += [b"`", b"end", b""]
    return eol.join(out)


def qp(data):
    """Quoted-printable, written here rather than by Python's quopri so
    that the encoder is not the thing under test's twin: every byte that
    is not a printable ASCII character is escaped — INCLUDING newlines,
    because this is binary and a hard line break would decode as CRLF
    (which is what the first version of this function did, and both
    decoders caught it) — and lines are wrapped with a soft break at 70.
    """
    out, col = bytearray(), 0
    for byte in data:
        if 33 <= byte <= 126 and byte != 0x3D:
            piece = bytes([byte])
        else:
            piece = b"=%02X" % byte
        if col + len(piece) > 70:
            out += b"=\r\n"
            col = 0
        out += piece
        col += len(piece)
    return bytes(out)


def applefile(name, rsrc, type_creator=b"APPLTTXT"):
    """An AppleDouble header file, laid out as reference/mpack/macfile.c
    encode_applefile() writes one: real name, Finder info, resource
    fork."""
    finfo = type_creator + b"\x00\x20" + b"\x00" * 22
    parts = [(3, name), (9, finfo), (2, rsrc)]
    off = 26 + 12 * len(parts)
    hdr = struct.pack(">II16sH", 0x00051607, 0x00020000, b"macextract" + b"\0" * 7,
                      len(parts))
    body = b""
    for eid, payload in parts:
        hdr += struct.pack(">III", eid, off + len(body), len(payload))
        body += payload
    return hdr + body


def message(parts, ctype=None, boundary=b"=_bnd_=", headers=b""):
    """Build a message. `parts` is a list of (headers, body) pairs; with
    a `ctype` they become a multipart, without one there must be exactly
    one part and it is the message itself."""
    out = b"From: mac@example\r\nSubject: a file\r\nMIME-Version: 1.0\r\n"
    out += headers
    if ctype is None:
        h, body = parts[0]
        return out + h + b"\r\n" + body
    out += b'Content-Type: %s; boundary="%s"\r\n\r\n' % (ctype, boundary)
    out += b"This is a multi-part message in MIME format.\r\n"
    for h, body in parts:
        out += b"--%s\r\n%s\r\n%s" % (boundary, h, body)
    out += b"--%s--\r\n" % boundary
    return out


def extract(macextract, path, extra=()):
    """Extract with the CLI; returns {name: bytes} including forks."""
    out = tempfile.mkdtemp()
    try:
        subprocess.run([macextract, "x", "-nr", "-o", out] + list(extra) + [path],
                       capture_output=True)
        got = {}
        for root, _dirs, files in os.walk(out):
            for f in files:
                p = os.path.join(root, f)
                got[os.path.relpath(p, out)] = open(p, "rb").read()
        return got
    finally:
        shutil.rmtree(out, ignore_errors=True)


def munpack_files(munpack, path):
    """What munpack writes, minus its `.desc` files: those hold the note
    the sender typed, which munpack saves beside an attachment and this
    engine does not save at all (mpack's handleText — a text part with
    no filename is the message body)."""
    out = tempfile.mkdtemp()
    try:
        subprocess.run([munpack, "-f", os.path.abspath(path)], cwd=out,
                       capture_output=True)
        got = {}
        for f in os.listdir(out):
            if f.endswith(".desc"):
                continue
            got[f] = open(os.path.join(out, f), "rb").read()
        return got
    finally:
        shutil.rmtree(out, ignore_errors=True)


def partial_set(msg, ident, n, eol=b"\r\n"):
    """Cut `msg` into `n` message/partial parts by hand, the way
    reference/mpack/encode.c writes one: the body of part k is the kth
    slice, and the enclosing headers carry number, total and a shared
    id. Returns a list of complete part messages.

    `total` is on EVERY part here, which is what mpack does; the RFC
    requires it only on the last, and one case below strips it from all
    but that one."""
    step = (len(msg) + n - 1) // n
    out = []
    for k in range(n):
        body = msg[k * step:(k + 1) * step]
        hdr = (b"From: mac@example" + eol +
               b"Subject: split (%02d/%02d)" % (k + 1, n) + eol +
               b"MIME-Version: 1.0" + eol +
               b'Content-Type: message/partial; number=%d; total=%d;' % (k + 1, n)
               + eol + b'\t id="' + ident + b'"' + eol + eol)
        out.append(hdr + body)
    return out


def munpack_partial(munpack, paths):
    """Reassemble a set with munpack, which is the oracle for the join.

    Two quirks, both of which cost a run here and are written up in
    DECISIONS.md 2026-08-29: munpack reassembles through a FIXED
    directory, /usr/tmp/m-prts-$USER, which it does not create; and it
    creates that directory's `CT` file with O_EXCL, so a part after the
    first dies with "CT: File exists" unless it is removed in between.
    That is mpack failing to round-trip with its own twin.

    Returns the files it wrote, or None where the machine has no
    /usr/tmp to reassemble through."""
    root = "/usr/tmp/m-prts-" + (os.environ.get("USER") or "nobody")
    try:
        os.makedirs(root, exist_ok=True)
    except OSError:
        return None
    for sub in os.listdir(root):
        shutil.rmtree(os.path.join(root, sub), ignore_errors=True)
    out = tempfile.mkdtemp()
    try:
        for p in paths:
            for sub in os.listdir(root):
                try:
                    os.remove(os.path.join(root, sub, "CT"))
                except OSError:
                    pass
            subprocess.run([munpack, "-f", os.path.abspath(p)], cwd=out,
                           capture_output=True)
        got = {}
        for f in os.listdir(out):
            if f.endswith(".desc"):
                continue
            got[f] = open(os.path.join(out, f), "rb").read()
        return got
    finally:
        shutil.rmtree(out, ignore_errors=True)


def deark_bytes(deark, path, module=None):
    out = tempfile.mkdtemp()
    try:
        cmd = [deark]
        if module:
            cmd += ["-m", module]
        cmd += [os.path.abspath(path), "-o", os.path.join(out, "d")]
        subprocess.run(cmd, capture_output=True)
        blobs = [open(os.path.join(out, f), "rb").read()
                 for f in sorted(os.listdir(out))]
        return blobs
    finally:
        shutil.rmtree(out, ignore_errors=True)


def main():
    macextract = os.path.join(ROOT, "build", "macextract")
    args = sys.argv[1:]
    if "--macextract" in args:
        macextract = args[args.index("--macextract") + 1]
    if not os.path.exists(macextract):
        print("run_mime: no CLI at %s" % macextract)
        return 1

    munpack, why = build("build_mpack.sh", "build/mpack/munpack",
                         os.path.join(ROOT, "reference", "mpack"))
    if not munpack:
        if why is None:
            print("run_mime: SKIPPED — no reference/mpack "
                  "(tools/fetch_references.sh)")
            return 0
        oracle_gone("mime", "reference/mpack", why)
        return 1
    deark, dwhy = build("build_deark.sh", "build/deark/deark",
                        os.path.join(ROOT, "reference", "deark"))
    if not deark and dwhy is not None:
        oracle_gone("mime", "reference/deark", dwhy)
        return 1

    problems, ran = [], 0
    tmp = tempfile.mkdtemp()

    def check(label, cond, detail=""):
        nonlocal ran
        ran += 1
        if not cond:
            problems.append("%s: %s" % (label, detail or "failed"))

    def write(name, data):
        p = os.path.join(tmp, name)
        open(p, "wb").write(data)
        return p

    try:
        # ---------------------------------------------------------- #
        # base64, on its own                                          #
        # ---------------------------------------------------------- #
        subjects = {
            # Lengths either side of a group boundary: the last group is
            # padded with one '=', two, or none at all.
            "pad0.bin": b"x" * 300,
            "pad1.bin": b"y" * 301,
            "pad2.bin": b"z" * 302,
            "all256.bin": DATA,
        }
        for name, content in sorted(subjects.items()):
            bare = write(name + ".b64", base64.encodebytes(content))
            got = extract(macextract, bare)
            check("bare base64 %s" % name, list(got.values()) == [content],
                  "wrote %r" % {k: len(v) for k, v in got.items()})
            if deark:
                check("bare base64 %s vs deark" % name,
                      deark_bytes(deark, bare, "base64") == [content])

            wrapped = write(name + ".w.b64",
                            b"begin-base64 644 " + name.encode() + b"\n"
                            + base64.encodebytes(content) + b"====\n")
            got = extract(macextract, wrapped)
            check("begin-base64 %s" % name, got == {name: content},
                  "wrote %r" % sorted(got))
            if deark:
                check("begin-base64 %s vs deark" % name,
                      deark_bytes(deark, wrapped) == [content])

        # A one-byte file. With the marker it is read like any other;
        # BARE it cannot be — four characters on one line is not enough
        # shape for any probe to claim, and this asserts that limit
        # rather than leaving it to be discovered (FORMATS.md, base64).
        tiny = write("tiny.w.b64", b"begin-base64 644 tiny.bin\n"
                     + base64.encodebytes(b"!") + b"====\n")
        check("begin-base64, a one-byte file",
              extract(macextract, tiny) == {"tiny.bin": b"!"})
        tinybare = write("tiny.b64", base64.encodebytes(b"!"))
        r = subprocess.run([macextract, "sniff", tinybare], capture_output=True)
        check("a bare base64 file too short to have a shape is not claimed",
              b"base64" not in r.stdout,
              r.stdout.decode(errors="replace").strip())

        # Two documents in one file, the shape a newsgroup posting has.
        two = write("two.b64",
                    b"begin-base64 644 first.bin\n"
                    + base64.encodebytes(b"first" * 40) + b"====\n"
                    + b"and a word between them\n"
                    + b"begin-base64 644 second.bin\n"
                    + base64.encodebytes(b"second" * 40) + b"====\n")
        got = extract(macextract, two)
        check("two documents in one file",
              got == {"first.bin": b"first" * 40,
                      "second.bin": b"second" * 40},
              "wrote %r" % sorted(got))

        # Line endings. The encoder writes LF; a file that reached a Mac
        # and was saved there comes back CR-terminated, and CRLF is what
        # a mailer writes. All three are the same file.
        for label, eol in (("cr", b"\r"), ("crlf", b"\r\n"), ("lf", b"\n")):
            p = write("eol.%s.b64" % label,
                      (b"begin-base64 644 eol.bin\n"
                       + base64.encodebytes(DATA) + b"====\n").replace(b"\n", eol))
            got = extract(macextract, p)
            check("begin-base64, %s line endings" % label.upper(),
                  got == {"eol.bin": DATA}, "wrote %r" % sorted(got))

        # Prose is not base64, and neither is a file whose head happens
        # to be alphabetic: the probe wants uniform full lines and an end
        # that closes the stream.
        prose = write("prose.txt",
                      b"Dear reader,\nthis mentions begin-base64 in passing\n"
                      b"and is otherwise an ordinary note about nothing.\n")
        r = subprocess.run([macextract, "sniff", prose], capture_output=True)
        check("prose is not claimed", b"base64" not in r.stdout,
              r.stdout.decode(errors="replace").strip())

        # ---------------------------------------------------------- #
        # MIME                                                        #
        # ---------------------------------------------------------- #
        cases = []

        cases.append((
            "single base64 attachment",
            message([(b'Content-Type: application/octet-stream; name="thing.sit"\r\n'
                      b"Content-Transfer-Encoding: base64\r\n", b64(DATA))]),
            {"thing.sit": DATA}))

        cases.append((
            "multipart, a note and two attachments",
            message([(b"Content-Type: text/plain\r\n", TEXT),
                     (b'Content-Type: application/octet-stream; name="a.bin"\r\n'
                      b"Content-Transfer-Encoding: base64\r\n", b64(DATA)),
                     (b"Content-Type: application/octet-stream\r\n"
                      b'Content-Disposition: attachment; filename="b.bin"\r\n'
                      b"Content-Transfer-Encoding: base64\r\n", b64(RSRC))],
                    ctype=b"multipart/mixed"),
            {"a.bin": DATA, "b.bin": RSRC}))

        # Quoted-printable twice. munpack grades the CR-free subject:
        # mpack's fromqp() DROPS a decoded '\r' — "if (c != '\r')" — so
        # a subject containing one is a case the two implementations
        # cannot agree on, and this engine keeps the byte, because =0D
        # is an explicit encoding of it and dropping it corrupts a
        # binary file (DECISIONS.md 2026-08-26).
        cases.append((
            "quoted-printable",
            message([(b'Content-Type: application/octet-stream; name="q.bin"\r\n'
                      b"Content-Transfer-Encoding: quoted-printable\r\n",
                      qp(DATA.replace(b"\r", b"")))]),
            {"q.bin": DATA.replace(b"\r", b"")}))

        cases.append((
            "a part with no encoding at all",
            message([(b'Content-Type: application/octet-stream; name="p.txt"\r\n',
                      b"seven bit, straight through\r\n")]),
            {"p.txt": b"seven bit, straight through\r\n"}))

        # Folded headers, which real mail is full of: a `Received:` over
        # three lines sits in front of the ones that matter, and a
        # `Content-Type:` is itself folded. Taking a continuation line
        # for the start of the body ends the headers half way through
        # them, which is what this catches.
        cases.append((
            "folded headers in front of the ones that matter",
            message([(b"Content-Type: application/octet-stream;\r\n"
                      b'\tname="folded.bin"\r\n'
                      b"Content-Transfer-Encoding:\r\n base64\r\n", b64(DATA))],
                    headers=b"Received: from a.example (a.example [10.0.0.1])\r\n"
                            b"\tby b.example with SMTP id 42\r\n"
                            b"\tfor <mac@example>; Tue, 1 Oct 1996 12:00:00 -0400\r\n"),
            {"folded.bin": DATA}))

        cases.append((
            "a part with no name",
            message([(b"Content-Type: application/octet-stream\r\n"
                      b"Content-Transfer-Encoding: base64\r\n", b64(DATA))]),
            {"part1": DATA}))

        for name, msg, expect in cases:
            p = write(name.replace(" ", "_").replace(",", "") + ".mim", msg)
            got = extract(macextract, p)
            check("MIME: %s" % name, got == expect,
                  "wrote %r, wanted %r" % (sorted(got), sorted(expect)))
            # munpack reads the same message, LF-terminated: mpack 1.6
            # is a text-mode reader and CANNOT read the CRLF form a
            # mailer writes — it takes the blank line after the headers
            # as body, and a quoted-printable soft break "=\r\n" as a
            # bad hex escape, inventing a byte per line (both measured
            # 2026-08-26, DECISIONS.md). So each implementation is given
            # the input it was written for, and both have to produce the
            # same file.
            #
            # The BYTES are what is compared, not the names: munpack
            # mangles them (a space becomes 'X'), and it never uses a
            # Content-Disposition filename at all — after matching the
            # token `filename` its getDispositionFilename() requires a
            # ';' where the '=' is, so it falls through to "part1" every
            # time (mpack 1.6, decode.c).
            plf = write("lf_" + os.path.basename(p), msg.replace(b"\r\n", b"\n"))
            mp = munpack_files(munpack, plf)
            want = sorted(v.replace(b"\r\n", b"\n") for v in expect.values())
            check("MIME: %s vs munpack" % name, sorted(mp.values()) == want,
                  "munpack wrote %r" % {k: len(v) for k, v in mp.items()})

        # ...and the CR that munpack cannot keep. Nothing else in this
        # suite would notice it going missing.
        p = write("qpcr.mim",
                  message([(b'Content-Type: application/octet-stream; name="c.bin"\r\n'
                            b"Content-Transfer-Encoding: quoted-printable\r\n",
                            qp(b"one\rtwo\r\nthree"))]))
        got = extract(macextract, p)
        check("quoted-printable: =0D is a byte, not a line ending",
              got == {"c.bin": b"one\rtwo\r\nthree"},
              "wrote %r" % {k: v for k, v in got.items()})

        # LF-only, which is what a message saved by a Unix mailer has.
        p = write("lfonly.mim", cases[1][1].replace(b"\r\n", b"\n"))
        got = extract(macextract, p)
        check("MIME: LF line endings", got == cases[1][2],
              "wrote %r" % sorted(got))

        # ---------------------------------------------------------- #
        # multipart/appledouble — both forks and the Finder info       #
        # ---------------------------------------------------------- #
        af = applefile(b"My Mac File", RSRC)
        ad = message([(b'Content-Type: application/applefile; name="My Mac File"\r\n'
                       b"Content-Transfer-Encoding: base64\r\n", b64(af)),
                      (b'Content-Type: application/octet-stream; name="My Mac File"\r\n'
                       b"Content-Transfer-Encoding: base64\r\n", b64(DATA))],
                     ctype=b'multipart/appledouble; name="My Mac File"')
        p = write("appledouble.mim", ad)
        got = extract(macextract, p)
        check("appledouble: both forks",
              got.get("My Mac File") == DATA and
              got.get("My Mac File.rsrc") == RSRC,
              "wrote %r" % {k: len(v) for k, v in got.items()})
        r = subprocess.run([macextract, "l", p], capture_output=True)
        check("appledouble: type and creator", b"APPL/TTXT" in r.stdout,
              r.stdout.decode(errors="replace").strip())
        mp = munpack_files(munpack, p)
        check("appledouble: munpack agrees on the data fork",
              DATA in mp.values(),
              "munpack wrote %r" % {k: len(v) for k, v in mp.items()})
        # The applefile part on its own is an AppleDouble file, and the
        # decoder that reads THOSE is graded by 932 corpus fixtures.
        # That is what stands in for an oracle on the resource fork.
        p2 = write("applefile.ad", af)
        got2 = extract(macextract, p2)
        check("appledouble: the applefile part reads as AppleDouble",
              any(v == RSRC for v in got2.values()),
              "wrote %r" % {k: len(v) for k, v in got2.items()})

        # A file with no data fork at all — on a Macintosh, most of them.
        adr = message([(b'Content-Type: application/applefile; name="Rsrc Only"\r\n'
                        b"Content-Transfer-Encoding: base64\r\n",
                        b64(applefile(b"Rsrc Only", RSRC)))],
                      ctype=b"multipart/appledouble")
        p = write("rsrconly.mim", adr)
        got = extract(macextract, p)
        check("appledouble: resource fork with no data part",
              got.get("Rsrc Only.rsrc") == RSRC,
              "wrote %r" % {k: len(v) for k, v in got.items()})

        # Nested: a covering multipart/mixed with the appledouble inside
        # it, which is what a mailer sends when there is a note as well.
        nested = message([(b"Content-Type: text/plain\r\n", TEXT),
                          (b'Content-Type: multipart/appledouble; boundary="inner"\r\n',
                           b"--inner\r\n"
                           b'Content-Type: application/applefile; name="Nested"\r\n'
                           b"Content-Transfer-Encoding: base64\r\n\r\n"
                           + b64(applefile(b"Nested", RSRC)) +
                           b"--inner\r\n"
                           b'Content-Type: application/octet-stream; name="Nested"\r\n'
                           b"Content-Transfer-Encoding: base64\r\n\r\n"
                           + b64(DATA) +
                           b"--inner--\r\n")],
                         ctype=b"multipart/mixed", boundary=b"outer")
        p = write("nested.mim", nested)
        got = extract(macextract, p)
        check("appledouble nested in a multipart/mixed",
              got.get("Nested") == DATA and got.get("Nested.rsrc") == RSRC,
              "wrote %r" % {k: len(v) for k, v in got.items()})

        # ---------------------------------------------------------- #
        # A document pasted into a part                                #
        # ---------------------------------------------------------- #
        # Mail carried files inside its text long before it carried
        # attachments, and a message can hold both. Until 2026-08-29 the
        # uuencode probe claimed such a message whole and the rest of it
        # was dropped: `l` listed the uuencoded file alone where munpack
        # wrote the attachment (DECISIONS.md, a part that hid its
        # message). munpack is the oracle for the half that matters —
        # it reads every part the uu document was hiding, and does not
        # decode the uu document itself.
        UUP = b"a file somebody pasted into a message\r\n" * 3
        both = message([(b"Content-Type: text/plain\r\n", uu(b"pasted.txt", UUP)),
                        (b'Content-Type: application/octet-stream; name="also.bin"\r\n'
                         b"Content-Transfer-Encoding: base64\r\n", b64(DATA))],
                       ctype=b"multipart/mixed")
        p = write("uupart.mim", both)
        got = extract(macextract, p)
        check("a uuencoded part no longer hides the rest of its message",
              got == {"pasted.txt": UUP, "also.bin": DATA},
              "wrote %r" % {k: len(v) for k, v in got.items()})
        mp = munpack_files(munpack, write("lf_uupart.mim",
                                          both.replace(b"\r\n", b"\n")))
        check("a uuencoded part: munpack gets the attachment, and so do we",
              [v for v in mp.values() if v == DATA.replace(b"\r\n", b"\n")] != []
              or DATA in mp.values(),
              "munpack wrote %r" % {k: len(v) for k, v in mp.items()})

        # The same message with the encoding NAMED. mpack has no such
        # value — parseEncoding warns and falls through to enc_none —
        # so the header changes nothing here either: the body decides.
        named = message([(b"Content-Type: text/plain\r\n"
                          b"Content-Transfer-Encoding: x-uuencode\r\n",
                          uu(b"pasted.txt", UUP)),
                         (b'Content-Type: application/octet-stream; name="also.bin"\r\n'
                          b"Content-Transfer-Encoding: base64\r\n", b64(DATA))],
                        ctype=b"multipart/mixed")
        got = extract(macextract, write("uunamed.mim", named))
        check("x-uuencode names an encoding no implementation knows",
              got == {"pasted.txt": UUP, "also.bin": DATA},
              "wrote %r" % {k: len(v) for k, v in got.items()})

        # A multipart whose ONLY part is uuencoded. This one already
        # decoded before the sniff order changed — through the uuencode
        # walk, which stepped over the boundary lines — so it is the
        # case that says the change cost nothing.
        only = message([(b"Content-Type: text/plain\r\n",
                         uu(b"alone.txt", UUP))], ctype=b"multipart/mixed")
        got = extract(macextract, write("uuonly.mim", only))
        check("a multipart holding nothing but a uuencoded part",
              got == {"alone.txt": UUP},
              "wrote %r" % {k: len(v) for k, v in got.items()})

        # A BinHex document in the same position is kept as it lies:
        # this walk has no BinHex decoder, and saving the bytes is what
        # keeps the sniff change from costing what the BinHex probe used
        # to do with the message. The saved part is a .hqx, and the
        # extractor says so when it is handed back.
        HQX = (b"(This file must be converted with BinHex 4.0)\r\n"
               b":#R4bB@a[E'8ZFQpY,R0cmr$8!*!%!3#3\"!d0!*!$%J!!N!3\"!!!:\r\n")
        withhqx = message([(b"Content-Type: text/plain\r\n", HQX),
                           (b'Content-Type: application/octet-stream; name="also.bin"\r\n'
                            b"Content-Transfer-Encoding: base64\r\n", b64(DATA))],
                          ctype=b"multipart/mixed")
        got = extract(macextract, write("hqxpart.mim", withhqx))
        # Less the CRLF in front of the boundary, which belongs to the
        # boundary and not to the part (RFC 2046; mpack's part.c).
        body = HQX[:-2]
        check("a BinHex document pasted into a part is kept, not dropped",
              sorted(got.values()) == sorted([body, DATA]),
              "wrote %r" % {k: len(v) for k, v in got.items()})
        kept = [k for k, v in got.items() if v == body]
        if kept:
            r = subprocess.run([macextract, "sniff",
                                write("kept.hqx", got[kept[0]])],
                               capture_output=True)
            check("the kept part is a BinHex file", b"BinHex" in r.stdout,
                  r.stdout.decode(errors="replace").strip())

        # ...and a note that merely says "begin" is still a note. The
        # test for a pasted document is the line AFTER the begin line,
        # exactly as the uuencode probe's is.
        prosepart = message([(b"Content-Type: text/plain\r\n",
                              b"begin the meeting at ten, and bring\r\n"
                              b"the file we discussed yesterday.\r\n"),
                             (b'Content-Type: application/octet-stream; name="also.bin"\r\n'
                              b"Content-Transfer-Encoding: base64\r\n", b64(DATA))],
                            ctype=b"multipart/mixed")
        got = extract(macextract, write("prosepart.mim", prosepart))
        check("a note that says \"begin\" is still a note",
              got == {"also.bin": DATA},
              "wrote %r" % {k: len(v) for k, v in got.items()})

        # ---------------------------------------------------------- #
        # message/partial: a message split across several FILES        #
        # ---------------------------------------------------------- #
        # The sixth join scheme (FORMATS.md, Segmented archives). mpack
        # writes the set and munpack reassembles it, so both ends of
        # this are somebody else's: what is graded is that the engine
        # joins the same parts into the same bytes.
        mpack = os.path.join(os.path.dirname(munpack), "mpack")
        pdir = os.path.join(tmp, "partial")
        os.mkdir(pdir)
        subject = write("partial/subject.bin", DATA * 12)   # 15,468 B
        made = subprocess.run([mpack, "-m", "4000", "-o", "set.mime",
                               "-s", "split", "subject.bin"],
                              cwd=pdir, capture_output=True)
        parts = sorted(os.path.join(pdir, f) for f in os.listdir(pdir)
                       if f.startswith("set.mime."))
        check("mpack -m wrote a multi-file set", len(parts) >= 3,
              "wrote %r (%s)" % (sorted(os.listdir(pdir)),
                                 made.stderr.decode(errors="replace")[:80]))

        if len(parts) >= 3:
            want = {"subject.bin": DATA * 12}
            # Anchored at part 1, and at a MIDDLE part: every part
            # carries the set's id and its own number, so which one the
            # user happens to open decides nothing.
            for anchor_at in (0, len(parts) // 2, len(parts) - 1):
                got = extract(macextract, parts[anchor_at])
                check("message/partial: joined from part %d of %d"
                      % (anchor_at + 1, len(parts)), got == want,
                      "wrote %r" % {k: len(v) for k, v in got.items()})

            mp = munpack_partial(munpack, parts)
            if mp is None:
                print("run_mime: message/partial vs munpack SKIPPED "
                      "(no writable /usr/tmp to reassemble through)")
            else:
                check("message/partial: munpack joins it the same way",
                      list(mp.values()) == [DATA * 12],
                      "munpack wrote %r" % {k: len(v) for k, v in mp.items()})

            # A missing MIDDLE part is refused, and nothing is written.
            # Unlike a uuencoded posting missing one, this set counts
            # its parts, so the gap is visible (OPEN_ITEMS.md part 1).
            gapdir = os.path.join(tmp, "gap")
            os.mkdir(gapdir)
            for i, p2 in enumerate(parts):
                if i == 1:
                    continue
                shutil.copy(p2, gapdir)
            r = subprocess.run([macextract, "x", "-o", tmp + "/gapout",
                                os.path.join(gapdir, os.path.basename(parts[0]))],
                               capture_output=True)
            check("message/partial: a missing part is refused",
                  r.returncode != 0 and not os.listdir(tmp + "/gapout"),
                  "rc=%d %r" % (r.returncode, r.stderr[:120]))

        # Two sets in one directory. Parts are placed by the `id` every
        # part of a set repeats — never by filename — so interleaving
        # them changes nothing.
        two = os.path.join(tmp, "twosets")
        os.mkdir(two)
        adm = message([(b'Content-Type: application/applefile; name="Split Mac File"\r\n'
                        b"Content-Transfer-Encoding: base64\r\n",
                        b64(applefile(b"Split Mac File", RSRC))),
                       (b'Content-Type: application/octet-stream; name="Split Mac File"\r\n'
                        b"Content-Transfer-Encoding: base64\r\n", b64(DATA))],
                      ctype=b'multipart/appledouble; name="Split Mac File"')
        other = message([(b'Content-Type: application/octet-stream; name="other.bin"\r\n'
                          b"Content-Transfer-Encoding: base64\r\n", b64(RSRC))])
        for i, part in enumerate(partial_set(adm, b"alpha@example", 3)):
            open(os.path.join(two, "a%d.txt" % (i + 1)), "wb").write(part)
        for i, part in enumerate(partial_set(other, b"beta@example", 2)):
            open(os.path.join(two, "b%d.txt" % (i + 1)), "wb").write(part)
        got = extract(macextract, os.path.join(two, "a2.txt"))
        check("message/partial: both forks through the join",
              got.get("Split Mac File") == DATA and
              got.get("Split Mac File.rsrc") == RSRC,
              "wrote %r" % {k: len(v) for k, v in got.items()})
        got = extract(macextract, os.path.join(two, "b1.txt"))
        check("message/partial: the other set in the same directory",
              got == {"other.bin": RSRC},
              "wrote %r" % {k: len(v) for k, v in got.items()})

        # `total` is required only on the LAST part (RFC 2046 5.2.2),
        # and a set opened at any other one then has to ask around for
        # its count — the shape a Compact Pro set has.
        lastonly = os.path.join(tmp, "lastonly")
        os.mkdir(lastonly)
        ps = partial_set(other, b"gamma@example", 3)
        for i, part in enumerate(ps):
            if i != len(ps) - 1:
                part = part.replace(b"; total=3", b"")
            open(os.path.join(lastonly, "g%d.txt" % (i + 1)), "wb").write(part)
        got = extract(macextract, os.path.join(lastonly, "g1.txt"))
        check("message/partial: only the last part says how many there are",
              got == {"other.bin": RSRC},
              "wrote %r" % {k: len(v) for k, v in got.items()})

        # ---------------------------------------------------------- #
        # What must NOT be claimed                                     #
        # ---------------------------------------------------------- #
        # A BinHex posting has mail headers too, and it is a BinHex file
        # rather than a message with an attachment: the probe order in
        # unc_sniff says so, and this is what would notice it changing.
        hqx = write("posted.hqx",
                    b"From: someone\r\nSubject: here is the file\r\n"
                    b"MIME-Version: 1.0\r\nContent-Type: text/plain\r\n\r\n"
                    b"(This file must be converted with BinHex 4.0)\r\n"
                    b":#R4bB@a[E'8ZFQpY,R0cmr$8!*!%!3#3\"!d0!*!$%J!!N!3\"!!!:\r\n")
        r = subprocess.run([macextract, "sniff", hqx], capture_output=True)
        check("a BinHex posting is still BinHex", b"BinHex" in r.stdout,
              r.stdout.decode(errors="replace").strip())

        # The same for a uuencoded posting: no boundary, no multipart,
        # nothing for the MIME walk to enumerate, so the strict probe
        # unc_sniff runs before the uuencode one declines it.
        uupost = write("posted.uu",
                       b"From: someone\r\nSubject: here it is\r\n"
                       b"MIME-Version: 1.0\r\nContent-Type: text/plain\r\n\r\n"
                       + uu(b"posted.bin", DATA))
        r = subprocess.run([macextract, "sniff", uupost], capture_output=True)
        check("a uuencode posting is still uuencode", b"uuencode" in r.stdout,
              r.stdout.decode(errors="replace").strip())

        # A message with nothing to extract is not an archive.
        note = write("note.mim",
                     message([(b"Content-Type: text/plain\r\n", TEXT)]))
        r = subprocess.run([macextract, "sniff", note], capture_output=True)
        check("a plain note is not claimed", b"MIME" not in r.stdout,
              r.stdout.decode(errors="replace").strip())

        # A multipart with nothing but text in it — the two-part note
        # every mailer sends — is claimed by the probe (it has a
        # boundary) and then has nothing to extract. That has to be a
        # clean refusal, not a crash and not an empty success.
        alt = write("alt.mim",
                    message([(b"Content-Type: text/plain\r\n", TEXT),
                             (b"Content-Type: text/html\r\n",
                              b"<html><body>the same note</body></html>\r\n")],
                            ctype=b"multipart/alternative"))
        r = subprocess.run([macextract, "x", "-o", tmp + "/altout", alt],
                           capture_output=True)
        check("a note with no attachment refuses cleanly",
              r.returncode != 0 and not os.listdir(tmp + "/altout"),
              "rc=%d %r" % (r.returncode, r.stderr[:120]))

        # An ordinary text file that begins with something colon-shaped.
        colon = write("colon.txt",
                      b"Note: this is a plain text file\nwith no MIME in it\n"
                      b"at all, only a first line that has a colon.\n")
        r = subprocess.run([macextract, "sniff", colon], capture_output=True)
        check("a colon on line one is not a message", b"MIME" not in r.stdout,
              r.stdout.decode(errors="replace").strip())

        # A message cut off mid-attachment yields the bytes that arrived
        # and no more. base64 carries no length and no checksum, so
        # nothing can tell a truncated stream from a complete one — the
        # same hole uuencode has (OPEN_ITEMS.md). Asserted, so that the
        # day a check turns out to exist this says so.
        full = cases[0][1]
        cut = write("cut.mim", full[:len(full) - 200])
        got = extract(macextract, cut)
        check("a truncated message decodes short, and silently",
              len(got) == 1 and 0 < len(list(got.values())[0]) < len(DATA),
              "wrote %r" % {k: len(v) for k, v in got.items()})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("run_mime: " + p)
    print("base64/MIME: %d case(s) checked, %d problem(s)"
          % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
