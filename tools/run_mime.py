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
and `unclassic` reads one of those through a decoder (fmt_applesingle.c)
that 932 corpus fixtures grade against `unar`. TESTING.md says this in
the same words.

Skips cleanly, and says so, when the references are not there.
"""
import base64
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


def build(script, binary):
    path = os.path.abspath(os.path.join(ROOT, binary))
    if os.path.exists(path):
        return path
    r = subprocess.run(["sh", os.path.join(ROOT, "tools", script)],
                       capture_output=True)
    return path if r.returncode == 0 and os.path.exists(path) else None


def b64(data, eol=b"\r\n"):
    return base64.encodebytes(data).replace(b"\n", eol)


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
    hdr = struct.pack(">II16sH", 0x00051607, 0x00020000, b"unclassic" + b"\0" * 7,
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


def extract(unclassic, path, extra=()):
    """Extract with the CLI; returns {name: bytes} including forks."""
    out = tempfile.mkdtemp()
    try:
        subprocess.run([unclassic, "x", "-nr", "-o", out] + list(extra) + [path],
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
    unclassic = os.path.join(ROOT, "build", "unclassic")
    args = sys.argv[1:]
    if "--unclassic" in args:
        unclassic = args[args.index("--unclassic") + 1]
    if not os.path.exists(unclassic):
        print("run_mime: no CLI at %s" % unclassic)
        return 1

    munpack = build("build_mpack.sh", "build/mpack/munpack")
    deark = build("build_deark.sh", "build/deark/deark")
    if not munpack:
        print("run_mime: SKIPPED — no reference/mpack "
              "(tools/fetch_references.sh)")
        return 0

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
            got = extract(unclassic, bare)
            check("bare base64 %s" % name, list(got.values()) == [content],
                  "wrote %r" % {k: len(v) for k, v in got.items()})
            if deark:
                check("bare base64 %s vs deark" % name,
                      deark_bytes(deark, bare, "base64") == [content])

            wrapped = write(name + ".w.b64",
                            b"begin-base64 644 " + name.encode() + b"\n"
                            + base64.encodebytes(content) + b"====\n")
            got = extract(unclassic, wrapped)
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
              extract(unclassic, tiny) == {"tiny.bin": b"!"})
        tinybare = write("tiny.b64", base64.encodebytes(b"!"))
        r = subprocess.run([unclassic, "sniff", tinybare], capture_output=True)
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
        got = extract(unclassic, two)
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
            got = extract(unclassic, p)
            check("begin-base64, %s line endings" % label.upper(),
                  got == {"eol.bin": DATA}, "wrote %r" % sorted(got))

        # Prose is not base64, and neither is a file whose head happens
        # to be alphabetic: the probe wants uniform full lines and an end
        # that closes the stream.
        prose = write("prose.txt",
                      b"Dear reader,\nthis mentions begin-base64 in passing\n"
                      b"and is otherwise an ordinary note about nothing.\n")
        r = subprocess.run([unclassic, "sniff", prose], capture_output=True)
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
            got = extract(unclassic, p)
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
        got = extract(unclassic, p)
        check("quoted-printable: =0D is a byte, not a line ending",
              got == {"c.bin": b"one\rtwo\r\nthree"},
              "wrote %r" % {k: v for k, v in got.items()})

        # LF-only, which is what a message saved by a Unix mailer has.
        p = write("lfonly.mim", cases[1][1].replace(b"\r\n", b"\n"))
        got = extract(unclassic, p)
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
        got = extract(unclassic, p)
        check("appledouble: both forks",
              got.get("My Mac File") == DATA and
              got.get("My Mac File.rsrc") == RSRC,
              "wrote %r" % {k: len(v) for k, v in got.items()})
        r = subprocess.run([unclassic, "l", p], capture_output=True)
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
        got2 = extract(unclassic, p2)
        check("appledouble: the applefile part reads as AppleDouble",
              any(v == RSRC for v in got2.values()),
              "wrote %r" % {k: len(v) for k, v in got2.items()})

        # A file with no data fork at all — on a Macintosh, most of them.
        adr = message([(b'Content-Type: application/applefile; name="Rsrc Only"\r\n'
                        b"Content-Transfer-Encoding: base64\r\n",
                        b64(applefile(b"Rsrc Only", RSRC)))],
                      ctype=b"multipart/appledouble")
        p = write("rsrconly.mim", adr)
        got = extract(unclassic, p)
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
        got = extract(unclassic, p)
        check("appledouble nested in a multipart/mixed",
              got.get("Nested") == DATA and got.get("Nested.rsrc") == RSRC,
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
        r = subprocess.run([unclassic, "sniff", hqx], capture_output=True)
        check("a BinHex posting is still BinHex", b"BinHex" in r.stdout,
              r.stdout.decode(errors="replace").strip())

        # A message with nothing to extract is not an archive.
        note = write("note.mim",
                     message([(b"Content-Type: text/plain\r\n", TEXT)]))
        r = subprocess.run([unclassic, "sniff", note], capture_output=True)
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
        r = subprocess.run([unclassic, "x", "-o", tmp + "/altout", alt],
                           capture_output=True)
        check("a note with no attachment refuses cleanly",
              r.returncode != 0 and not os.listdir(tmp + "/altout"),
              "rc=%d %r" % (r.returncode, r.stderr[:120]))

        # An ordinary text file that begins with something colon-shaped.
        colon = write("colon.txt",
                      b"Note: this is a plain text file\nwith no MIME in it\n"
                      b"at all, only a first line that has a colon.\n")
        r = subprocess.run([unclassic, "sniff", colon], capture_output=True)
        check("a colon on line one is not a message", b"MIME" not in r.stdout,
              r.stdout.decode(errors="replace").strip())

        # A message cut off mid-attachment yields the bytes that arrived
        # and no more. base64 carries no length and no checksum, so
        # nothing can tell a truncated stream from a complete one — the
        # same hole uuencode has (OPEN_ITEMS.md). Asserted, so that the
        # day a check turns out to exist this says so.
        full = cases[0][1]
        cut = write("cut.mim", full[:len(full) - 200])
        got = extract(unclassic, cut)
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
