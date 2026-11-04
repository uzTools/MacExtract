#!/usr/bin/env python3
"""synth_lz4.py — LZ4 frames written by the reference library, liblz4.

    synth_lz4.py IN -o OUT [--block 4..7] [--linked] [--content-checksum]
                 [--block-checksum] [--content-size] [--level N]
    synth_lz4.py --check          is liblz4 here; exit 1 if not

The encoder is the system's liblz4 (the `lz4` project's own library, 1.10
here), called through ctypes: LZ4F_compressFrame with explicit
LZ4F_preferences_t, laid out as lz4frame.h declares it. Nothing in this
file encodes; it only chooses the frame's options, so what the engine is
graded against is the reference implementation's output, not a reading of
the specification (reference/notes/lz4_Frame_format.md).

Deterministic: liblz4's output is a function of its input and options.
"""
import argparse
import ctypes
import os
import ctypes.util
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FrameInfo(ctypes.Structure):
    _fields_ = [("blockSizeID", ctypes.c_int), ("blockMode", ctypes.c_int),
                ("contentChecksumFlag", ctypes.c_int),
                ("frameType", ctypes.c_int),
                ("contentSize", ctypes.c_ulonglong), ("dictID", ctypes.c_uint),
                ("blockChecksumFlag", ctypes.c_int)]


class Prefs(ctypes.Structure):
    _fields_ = [("frameInfo", FrameInfo), ("compressionLevel", ctypes.c_int),
                ("autoFlush", ctypes.c_uint), ("favorDecSpeed", ctypes.c_uint),
                ("reserved", ctypes.c_uint * 3)]


def lib():
    name = ctypes.util.find_library("lz4") or "liblz4.so.1"
    try:
        L = ctypes.CDLL(name)
    except OSError:
        return None
    L.LZ4F_compressFrameBound.restype = ctypes.c_size_t
    L.LZ4F_compressFrameBound.argtypes = [ctypes.c_size_t,
                                          ctypes.POINTER(Prefs)]
    L.LZ4F_compressFrame.restype = ctypes.c_size_t
    L.LZ4F_compressFrame.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                     ctypes.c_void_p, ctypes.c_size_t,
                                     ctypes.POINTER(Prefs)]
    L.LZ4F_isError.restype = ctypes.c_uint
    L.LZ4F_isError.argtypes = [ctypes.c_size_t]
    L.LZ4_versionString.restype = ctypes.c_char_p
    return L


def frame(data, block=4, linked=False, content_checksum=False,
          block_checksum=False, content_size=False, level=0):
    """One LZ4 frame of `data`, from liblz4."""
    L = lib()
    if L is None:
        raise SystemExit("synth_lz4: no liblz4 on this machine")
    p = Prefs()
    p.frameInfo.blockSizeID = block
    p.frameInfo.blockMode = 0 if linked else 1
    p.frameInfo.contentChecksumFlag = 1 if content_checksum else 0
    p.frameInfo.blockChecksumFlag = 1 if block_checksum else 0
    p.frameInfo.contentSize = len(data) if content_size else 0
    p.compressionLevel = level
    cap = L.LZ4F_compressFrameBound(len(data), ctypes.byref(p))
    dst = ctypes.create_string_buffer(cap)
    src = ctypes.create_string_buffer(bytes(data), len(data))
    n = L.LZ4F_compressFrame(dst, cap, src, len(data), ctypes.byref(p))
    if L.LZ4F_isError(n):
        raise SystemExit("synth_lz4: LZ4F_compressFrame failed")
    return dst.raw[:n]


def skippable(payload, nibble=0):
    """A skippable frame (the frame spec, *Skippable Frames*): magic
    0x184D2A5X little-endian, a 4-byte size, the bytes."""
    return ((0x184D2A50 | nibble).to_bytes(4, "little")
            + len(payload).to_bytes(4, "little") + payload)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?")
    ap.add_argument("-o")
    ap.add_argument("--block", type=int, default=4, choices=range(4, 8))
    ap.add_argument("--linked", action="store_true")
    ap.add_argument("--content-checksum", action="store_true")
    ap.add_argument("--block-checksum", action="store_true")
    ap.add_argument("--content-size", action="store_true")
    ap.add_argument("--level", type=int, default=0)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        L = lib()
        print("liblz4", L.LZ4_versionString().decode() if L else "absent")
        return 0 if L else 1
    src = a.input
    if not os.path.exists(src):          # tools/harvest.py --restore names
        src = os.path.join(ROOT, src)    # its input from the repository
    data = open(src, "rb").read()
    out = frame(data, a.block, a.linked, a.content_checksum,
                a.block_checksum, a.content_size, a.level)
    open(a.o, "wb").write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
