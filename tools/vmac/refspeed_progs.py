"""refspeed_progs.py — how refspeed.py drives each format's own program.

One dict per program, each drive measured off this harness's own frames
(`drive.py` at all-out speed first, then the 1x runs' `*-selected.png`,
`*-2b-started.png` and `*-3-finished.png`). The programs are MacBinary files
in ~/.cache/macextract/vmac/speed/, made from the corpus or downloaded
(tools/vmac/README.md, *Each format's own program — `refspeed.py`*).
"""
import os
import run as R

S = os.path.join(R.VMAC_HOME, "speed")

REFS = {
    # Compact Pro 1.51 (Bill Goodman, 1995), out of the corpus's
    # `derived-Compact_Pro_Package__English_`. Nag -> Not Yet; File > Open;
    # Edit > Select All; Archive > Extract; its destination dialog's own
    # "Extract" button (pressed, not Command-E, so no modifier hold sits
    # inside the timed span).
    "cpt151": dict(
        app=os.path.join(S, "CompactPro.bin"), app_name="Compact Pro",
        ftype=("PACT", "CPCT"),
        pre=[("click", 431, 247), ("sleep", 2.0), ("cmd", "o"), ("sleep", 3.0),
             ("select",), ("shot", "selected"), ("key", "Return"),
             ("sleep", 6.0), ("cmd", "a"), ("sleep", 1.0), ("cmd", "e"),
             ("sleep", 3.0), ("shot", "destination"), ("move", 395, 246)],
        act=("press",),
        post=[("cmd", "q"), ("sleep", 10.0)]),
}

# PackIt III 1.3 (Harry Chesley, 1987), out of the corpus's
# `derived-PackIt.pit`, which it is the payload of. Splash -> click;
# File > Unpack files (Command-U); its file dialog; "Save All" in the
# per-file save dialog; "All done." alert -> Return; Command-Q.
REFS["packit3"] = dict(
    app=os.path.join(S, "PackIt3.bin"), app_name="PackIt III",
    ftype=("PIT ", "PIT "),
    pre=[("click", 250, 200), ("sleep", 2.0), ("cmd", "u"), ("sleep", 3.0),
         ("select",), ("shot", "selected"), ("key", "Return"), ("sleep", 3.0),
         ("shot", "destination"), ("move", 182, 250)],
    act=("press",),
    post=[("key", "Return"), ("sleep", 2.0), ("cmd", "q"), ("sleep", 10.0)])

# tar 4.0b (Craig Ruff; public domain), out of the corpus's
# `derived-tar.sit`. File > Extract (Command-E); the archive; the
# "Extraction Directory" dialog's Select button. It draws no progress: the
# end is the pointer's watch cursor going back (checked against the files
# on the volume). MacTar 68k 2.x (Gryphel) was tried first and stops at
# launch on System 6 with "out of memory".
REFS["tar40"] = dict(
    app=os.path.join(S, "Tar.bin"), app_name="tar",
    ftype=("TARF", "TAR "),
    pre=[("cmd", "e"), ("sleep", 3.0), ("select",), ("shot", "selected"),
         ("key", "Return"), ("sleep", 3.0), ("shot", "destination"),
         ("move", 370, 213)],
    act=("press",),
    post=[("cmd", "q"), ("sleep", 10.0)])

# UnZip 1.01 for the Macintosh, out of the corpus's `derived-Unzip101.sit`.
# File > Open ZIP file (Command-O); the archive (listed in a window);
# Processing > Extract Files (Command-E, the timed key); the "ZIP file
# extraction completed!" alert -> Return. Run with `--free 3`: on the stock
# 23 MB-free volume it skips every file "no space on volume".
REFS["unzip101"] = dict(
    app=os.path.join(S, "UnZip.bin"), app_name="UnZip",
    ftype=("ZIP ", "pZIP"),
    pre=[("cmd", "o"), ("sleep", 3.0), ("select",), ("shot", "selected"),
         ("key", "Return"), ("sleep", 4.0), ("shot", "destination")],
    act=("cmd", "e"),
    post=[("key", "Return"), ("sleep", 2.0), ("cmd", "q"), ("sleep", 10.0)])

# MacLHa 2.00 (Kazuaki Ishizaki), out of the corpus's
# `derived-MacLHa_2.00.sit` (specimens/maclha/MacLHa.bin). File > Open
# Archive; Edit > Select All; the window's Extract button; "Save All" in its
# save dialog, which opens on the application's own folder (the System
# Folder here), so nothing is ignored there and `before` excludes what was.
# Options > MacBinary left as shipped (checked).
REFS["maclha"] = dict(
    app=os.path.join(R.VMAC_HOME, "specimens", "maclha", "MacLHa.bin"),
    app_name="MacLHa", ftype=("LHA ", "LARC"), ignore=(),
    pre=[("cmd", "o"), ("sleep", 3.0), ("select",), ("shot", "selected"),
         ("key", "Return"), ("sleep", 4.0), ("cmd", "a"), ("sleep", 1.0),
         ("click", 465, 79), ("sleep", 3.0), ("shot", "destination"),
         ("move", 389, 259)],
    act=("press",),
    post=[("cmd", "q"), ("sleep", 10.0)])

# UUTool 2.3.2 (Jean-Pierre Gachen), off ~/.cache/macextract/vmac/uutool/
# (UUTool-FAT, the corpus's, stops on System 6 with "System software needs
# updating! -5551"). File > UUcode > decode (Command-D); its two-list
# dialog: the file, Open (adds it), Okay; then "Decode file as?" -> Save.
# It removes the uuencode layer only, so it is graded with `-nr`, and the
# archive inside is timed separately under the program that reads it.
REFS["uutool"] = dict(
    app=os.path.join(S, "UUTool.bin"), app_name="UUTool",
    ftype=("TEXT", "ttxt"), nr=True,
    pre=[("cmd", "d"), ("sleep", 3.0), ("select",), ("key", "Return"),
         ("sleep", 2.0), ("shot", "selected"), ("click", 397, 224),
         ("sleep", 3.0), ("shot", "destination"), ("move", 387, 225)],
    act=("press",),
    post=[("cmd", "q"), ("sleep", 10.0)])

# DD Expand 3.7.7 (Fifth Generation Systems), the Info-Mac II CD's copy
# (specimens/diskdoubler/ddexpand-377.bin, diskdoubler.py --ddar). It runs
# on System 6. File > Expand (Command-E); the file dialog's Expand button.
REFS["ddexp377"] = dict(
    app=os.path.join(R.VMAC_HOME, "specimens", "diskdoubler",
                     "ddexpand-377.bin"),
    app_name="DD Expand", ftype=("DDAR", "DDAP"),
    pre=[("cmd", "e"), ("sleep", 3.0), ("select",), ("shot", "selected"),
         ("move", 375, 220)],
    act=("press",),
    post=[("cmd", "q"), ("sleep", 10.0)])

