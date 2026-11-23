/*
 * seg_run.inc.c — a segmented set's run-time shell code: finding a part
 * (by its header, in a folder, on the disks, by asking), opening it for
 * the joiner and closing it again. Included by tools/overlay/ovl_segrun.c,
 * an image that only a set keeps (mac/release_plan.inc.c), and by
 * macextract_mac.c in the builds without the bundle (UNC_SHELL_IMAGES).
 *
 * Every resident name it uses is the function itself when it is compiled
 * into the application, and the SegRunFns entry when it is an image
 * (ovl_segrun.c's defines), which cannot name an application symbol.
 *
 * SPDX-License-Identifier: 0BSD
 */
#ifndef SEG_DATA
#define SEG_DATA     /* an image's .data, where it has no .bss (ovl_segrun.c) */
#endif
/* Read a candidate file's header and return its part number, or 0. */
static int SegPartOf(SegHost *h, short vol, long dir, ConstStr255Param name)
{
    short ref;
    long count;
    uint8_t head[UNC_SEG_HEAD];
    OSErr err;
    int part;

    if (MyOpenFork(vol, dir, name, fsRdPerm, 0, &ref) != noErr) return 0;
    /* A message/partial part says which set it belongs to in its mail
     * headers, which are longer than the 100 bytes unc_segment_match
     * is given — so the candidate is DESCRIBED instead. Still identity
     * by content: what is compared is the `id` every part repeats. The
     * Linux CLI does the same (macextract.h, UNC_FORMAT_MIMESEG). */
    if (h->desc.scheme == UNC_FORMAT_MIMESEG) {
        UncSegmentDesc cand;
        FileIO probe;
        UncIO pio;
        long eof = 0;
        int ok, i;
        GetEOF(ref, &eof);
        probe.refNum = ref;
        probe.size = (uint32_t)eof;
        probe.pos = 0;
        pio.ctx = &probe;
        pio.read = fio_read;
        pio.seek = fio_seek;
        pio.tell = fio_tell;
        pio.size = fio_size;
        ok = unc_segment_describe_as(&pio, UNC_FORMAT_MIMESEG,
                                     &cand) == UNC_OK;
        if (ok)
            for (i = 0; i < UNC_SEG_FP_LEN; i++)
                if (cand.fp[i] != h->desc.fp[i]) { ok = 0; break; }
        FSClose(ref);
        return ok ? (int)cand.part : 0;
    }
    count = (long)sizeof head;
    err = FSRead(ref, &count, head);
    FSClose(ref);
    if (err != noErr && err != eofErr) return 0;
    if (count < (long)sizeof head) return 0;
    part = unc_segment_match(&h->desc, head, (int32_t)count);
    return part;
}

/* ------------------------------------------------------------------ */
/* The schemes that are placed by NAME                                 */
/*                                                                    */
/* A spanned zip part and a plain .NNN split part carry nothing that   */
/* says which set they belong to — only the FIRST and LAST parts of a  */
/* spanned zip are recognizable at all, and a split part is not even   */
/* that. So the family is decided by filename, by the engine's        */
/* unc_segment_name_part — the rule the Linux CLI uses too — and what  */
/* keeps a wrong file out is not this scan but the check the engine    */
/* makes on the ASSEMBLED set (macextract.h, unc_extract_segments).    */
/* Names propose; content disposes.                                    */
/* ------------------------------------------------------------------ */

static void SegRemember(SegHost *h, int part, short vol, long dir,
                        ConstStr255Param name);
static short SegDriveOf(short vol);

/* Walk one folder and record every member of the family, by name. The
 * zip family's ".zip" member is the LAST part, and its number is only
 * known once that part has been read, so it is reported separately. */
static void SegScanFamily(SegHost *h, short vol, long dir, int split,
                          Str63 lastName)
{
    CInfoPBRec pb;
    Str63 nm;
    short idx;
    long z;

    lastName[0] = 0;
    for (idx = 1; idx < 32767; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        nm[0] = 0;
        pb.hFileInfo.ioNamePtr = nm;
        pb.hFileInfo.ioVRefNum = vol;
        pb.hFileInfo.ioDirID = dir;
        pb.hFileInfo.ioFDirIndex = idx;
        if (PBGetCatInfoSync(&pb) != noErr) break;
        if (pb.hFileInfo.ioFlAttrib & 0x10) continue;         /* a folder */
        {
            int part = unc_segment_name_part(
                split ? UNC_FORMAT_SPLIT : UNC_FORMAT_ZIPSEG,
                h->stem, (uint32_t)h->stemlen, nm + 1, nm[0]);
            if (part == UNC_SEG_NAME_LAST) {
                for (z = 0; z <= (long)nm[0]; z++) lastName[z] = nm[z];
                /* Once its count is known, the ".zip" is that part: one
                 * found on a disk inserted later is the last part back
                 * (one drive: 3, 1, 2, then 3 again for its tail). */
                if (!split && h->desc.nparts)
                    SegRemember(h, (int)h->desc.nparts, vol, dir, nm);
                continue;
            }
            if (part >= 1) {
                SegRemember(h, part, vol, dir, nm);
                if (part > h->highest) h->highest = part;
                h->psize[part <= kSegMaxKnown ? part : 0] = 0;
            }
        }
    }
}

/* The length of a part, without opening it: a directory lookup, which
 * on a hard disk is free and on a floppy costs nothing the user can
 * see. A plain split needs every one of them before extraction starts,
 * because the sum IS the joined length and nothing else states it
 * (DECISIONS.md 2026-08-10). */
static uint32_t SegPartLength(SegHost *h, int part)
{
    CInfoPBRec pb;
    Str63 nm;
    long z;
    short i;

    if (part < 1 || part > kSegMaxKnown) return UNC_SIZE_UNKNOWN;
    /* Measured when the part was found and kept: a split's total is the sum
     * of its parts, and on floppies a part's disk is ejected (and its
     * location forgotten) before the next is asked for. */
    if (h->plen[part]) return h->plen[part];
    if (!h->loc[part].name[0]) return UNC_SIZE_UNKNOWN;
    for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
    for (i = 0; i <= (short)h->loc[part].name[0]; i++)
        nm[i] = h->loc[part].name[i];
    pb.hFileInfo.ioNamePtr = nm;
    pb.hFileInfo.ioVRefNum = h->loc[part].vRefNum;
    pb.hFileInfo.ioDirID = h->loc[part].dirID;
    pb.hFileInfo.ioFDirIndex = 0;
    if (PBGetCatInfoSync(&pb) != noErr) return UNC_SIZE_UNKNOWN;
    h->plen[part] = (uint32_t)pb.hFileInfo.ioFlLgLen;
    return (uint32_t)pb.hFileInfo.ioFlLgLen;
}


/* "MacExtract part N", created empty and open for writing — on the
 * output volume, which is the one place this application knows it may
 * write. A stale one is removed first. */
static int SegTmpOpen(SegHost *h, int part, Str255 tmp, short *ref)
{
    tmp[0] = 0;
    PStrCat(tmp, S_FILE_PART);
    PStrCatNum(tmp, (long)part);
    MyHDelete(h->tmpVol, h->tmpDir, tmp);
    if (MyHCreate(h->tmpVol, h->tmpDir, tmp) == noErr &&
        MyOpenFork(h->tmpVol, h->tmpDir, tmp, fsWrPerm, 0, ref) == noErr)
        return 1;
    MyHDelete(h->tmpVol, h->tmpDir, tmp);
    return 0;
}

/* Remove the decoded parts: this application's own litter, and a join
 * that failed is when a user is least helped by finding pieces of one. */
static void SegPeelClean(SegHost *h)
{
    int p;
    if (!h->peeled) return;
    for (p = 1; p <= kSegMaxKnown; p++) {
        Str255 tmp;
        tmp[0] = 0;
        PStrCat(tmp, S_FILE_PART);
        PStrCatNum(tmp, (long)p);
        MyHDelete(h->tmpVol, h->tmpDir, tmp);
    }
    FlushVol(NULL, h->tmpVol);
    h->peeled = 0;
}

static uint32_t SegPartLength(SegHost *h, int part);
static void SegRemember(SegHost *h, int part, short vol, long dir,
                        ConstStr255Param name)
{
    short i;
    if (part < 1 || part > kSegMaxKnown) return;
    if (h->loc[part].name[0]) return;         /* first match wins */
    h->loc[part].vRefNum = vol;
    h->loc[part].dirID = dir;
    for (i = 0; i <= (short)name[0]; i++) h->loc[part].name[i] = name[i];
    h->loc[part].drive = SegDriveOf(vol);
    (void)SegPartLength(h, part);        /* kept while the disk is here */
}

/* The schemes whose parts say nothing of their set (macextract.h): they are
 * found by NAME. */
static int SegByName(SegHost *h)
{
    return h->desc.scheme == UNC_FORMAT_ZIPSEG ||
           h->desc.scheme == UNC_FORMAT_SPLIT;
}

/* Walk one folder, recording every part of this set that it holds. */
static void SegScanDir(SegHost *h, short vol, long dir)
{
    CInfoPBRec pb;
    Str63 nm;
    short idx;
    long z;

    /* By name, the folder's names are what is read (SegScanFamily);
     * opening each file would find nothing, at a file open apiece. */
    if (SegByName(h)) return;
    for (idx = 1; idx < 512; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.hFileInfo.ioNamePtr = nm;
        pb.hFileInfo.ioVRefNum = vol;
        pb.hFileInfo.ioDirID = dir;
        pb.hFileInfo.ioFDirIndex = idx;
        if (PBGetCatInfoSync(&pb) != noErr) return;    /* past the last item */
        if (pb.hFileInfo.ioFlAttrib & ioDirMask) continue;
        {
            int part = SegPartOf(h, vol, dir, nm);
            if (part) SegRemember(h, part, vol, dir, nm);
        }
    }
}

#ifndef UNC_MAC_AUTOTEST
#define kSegALRT        131
#define kSegEjectALRT   136     /* the same, after an eject */
#define kSegFindItem    1
#define kSegSkipItem    2
#define kSegCancelItem  3
#define kSegDiskItem    4    /* NOT in the DITL — see SegDiskFilter */

#define kSegRootDirID   2L   /* fsRtDirID; the headers here do not define it */

/* An alert filter takes no context, so these say which part the alert
 * currently on screen is waiting for. The shell already keeps state this
 * way (gBarPct); the no-global rule is the engine's. */
static SEG_DATA SegHost *gSegAsking = NULL;
static SEG_DATA int gSegWantPart = 0;
static SEG_DATA long gSegNextPoll = 0;    /* TickCount: throttles SegDiskFilter */

/* Record every part of this set that is on the volume in `drive`.
 * PBHGetVInfo reports a volume's drive in ioVDrvInfo, so the disk just
 * put in is found by number rather than by walking every volume
 * mounted — a hard disk's root is not worth scanning again. */
static void SegScanDrive(SegHost *h, short drive)
{
    HParamBlockRec pb;
    Str63 nm;
    short idx;
    long z;

    for (idx = 1; idx < 64; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.volumeParam.ioNamePtr = nm;
        pb.volumeParam.ioVolIndex = idx;
        if (PBHGetVInfoSync(&pb) != noErr) return;   /* past the last volume */
        if (pb.volumeParam.ioVDrvInfo != drive) continue;
        SegScanDir(h, pb.volumeParam.ioVRefNum, kSegRootDirID);
        return;
    }
}

/* Notice a disk going in while the alert is asking for a part.
 *
 * This is the whole feature: the user is told "part 2 has not been
 * found", puts the disk in, and the extraction carries on rather than
 * making them answer an alert about a disk already in the machine.
 *
 * Two things about it are not obvious, and both cost a run to find.
 *
 * The event handed to a filter is never the one wanted. `ModalDialog`
 * "calls the Event Manager function GetNextEvent with a mask that
 * excludes disk-inserted events" (Inside Macintosh: Toolbox Essentials,
 * ModalDialog), so a diskEvt is never delivered — a build that dismissed
 * the alert on ANY diskEvt reaching this filter sat through two
 * insertions unmoved. The queue has to be asked directly, which is done
 * here on every event including the null ones, and that is what makes it
 * work with nobody touching the mouse.
 *
 * And fetching the event is not merely how we hear about the disk, it is
 * what gets the disk MOUNTED: a version that left the queue alone and
 * instead polled the volume list twice a second never saw a new volume
 * at all. The mount result is what the event's high word carries, so
 * nothing has mounted until somebody fetches it. */
static pascal Boolean SegDiskFilter(DialogPtr dlg, EventRecord *evt,
                                    INTEGER *itemHit)
{
    StackSample();   /* inside ModalDialog: the Toolbox's frames are below us */
    EventRecord de;

    (void)dlg;
    if (gSegAsking == NULL) return false;

    /* Return and Enter press the default button — and doing that here is
     * not a courtesy, it is replacing what was lost. An alert with no
     * filter gets a standard one that maps them to item 1; supplying our
     * own takes that away, and the symptom is not subtle in hindsight:
     * the alert simply ignored its own default button, and every later
     * step of --segments clicked into a dialog that should have closed.
     * Handled on every pass, unthrottled, because a keystroke is not
     * something to poll for. */
    if (evt->what == keyDown || evt->what == autoKey) {
        char c = (char)(evt->message & charCodeMask);
        if (c == '\r' || c == 0x03) {
            *itemHit = kSegFindItem;
            return true;
        }
    }

    /* THROTTLED, and that is not an optimisation. Calling GetNextEvent
     * on every pass takes events out from under the modal loop that
     * owns them: with it unthrottled the alert stopped acting on its
     * own buttons — Return was still sitting on an undismissed alert
     * three seconds later, and every later step of --segments then
     * clicked into a dialog that should have been gone. Twice a second
     * is far quicker than anyone swaps a floppy. */
    if (TickCount() < gSegNextPoll) return false;
    gSegNextPoll = TickCount() + 30;

    if (!GetNextEvent(diskMask, &de)) return false;

    /* Nonzero result: no HFS volume mounted. This shell has nothing to
     * offer for that — it is not the Finder, and formatting somebody's
     * disk is not its business — so the alert simply stays up. */
    if ((short)((de.message >> 16) & 0xFFFFL) != noErr) return false;

    SegScanDrive(gSegAsking, (short)(de.message & 0xFFFFL));

    if (gSegWantPart >= 1 && gSegWantPart <= kSegMaxKnown
        && gSegAsking->loc[gSegWantPart].name[0]) {
        *itemHit = kSegDiskItem;
        return true;               /* the disk had it: take the alert down */
    }
    return false;                  /* some other disk: keep asking */
}

/* Payload bytes of this set not yet read, or 0 if that cannot be said.
 *
 * "Part 2 of 3" is what a person wants and the format does not store a
 * part count, so it cannot be said at all — but how much is left CAN
 * be: the header carries the total payload of the whole set, and the
 * parts already opened account for the rest. It answers roughly the
 * same question, "how many more floppies is this", without inventing a
 * number the file does not contain. */
static uint32_t SegRemaining(SegHost *h)
{
    uint32_t seen = 0;
    short p;

    if (h->desc.total == 0) return 0;
    /* A spanned zip states a part COUNT and no size: "about 4194251K still
     * to read" was this subtracting from UNC_SIZE_UNKNOWN (measured, the
     * part dialog on System 6.0.8 and 7.0.1; the old alert built the same
     * message). Nothing is said instead. */
    if (h->desc.total == UNC_SIZE_UNKNOWN) return 0;
    for (p = 1; p <= kSegMaxKnown; p++) seen += h->psize[p];
    return seen < h->desc.total ? h->desc.total - seen : 0;
}

/* Append "About 33K still to read." for a size worth mentioning. */
static void SegCatRemaining(Str255 msg, uint32_t left)
{
    if (left == 0) return;
    PStrCat(msg, S_SEG_LEFT_ABOUT);
    if (left >= 1024) {
        PStrCatNum(msg, (long)((left + 512) / 1024));
        PStrCat(msg, S_SEG_LEFT_K);
    } else {
        PStrCatNum(msg, (long)left);
        PStrCat(msg, S_SEG_LEFT_BYTES);
    }
    PStrCat(msg, S_SEG_LEFT_END);
}

#endif  /* !UNC_MAC_AUTOTEST, opened again below */

/* The drive the volume `vol` is in, or 0 for none: a server volume, or
 * one already ejected. `vol` may be a working directory. The autotest
 * build's too: a set's setup and the parts it remembers ask it. */
static short SegDriveOf(short vol)
{
    HParamBlockRec pb;
    pb.volumeParam.ioNamePtr = NULL;
    pb.volumeParam.ioVRefNum = vol;
    pb.volumeParam.ioVolIndex = 0;
    if (PBHGetVInfoSync(&pb) != noErr) return 0;
    return pb.volumeParam.ioVDrvInfo;
}

#ifndef UNC_MAC_AUTOTEST

/* The volume the file `ref` is open on, or 0. */
static short SegFileVol(short ref)
{
    FCBPBRec fcb;
    fcb.ioNamePtr = NULL;
    fcb.ioVRefNum = 0;
    fcb.ioRefNum = ref;
    fcb.ioFCBIndx = 0;
    return PBGetFCBInfoSync(&fcb) == noErr ? fcb.ioFCBVRefNum : 0;
}

/* A part not found beside the one before it is on another disk, and on a
 * one-drive Mac the drive holds a disk that is not wanted. The ask looks
 * at the disk in each ejectable drive: one holding the part is used and
 * nothing is asked; otherwise the first that is not the System's or this
 * application's is shown in the dialog and ejected, and putting the next
 * one in is the whole answer (the maintainer's design, 2026-10-13).
 * Not ejected: a disk the drive queue calls nonejectable, a volume in no
 * drive (a server), and the disk holding this application or the System
 * (the Toolbox reads both while the dialog is up).
 *
 * Source for the flag byte: Inside Macintosh: Files, File Manager
 * Reference, "Drive queue" — four flag bytes precede each DrvQEl; byte 1
 * is "0 if no disk in drive; 1 or 2 if disk in drive; 8 if nonejectable
 * disk in drive; $FC-$FF if disk was ejected within last 1.5 seconds;
 * $48 if disk in drive is nonejectable but driver wants a call". */
static void SegCopyIn(SegHost *h, int part);
static void SegScanHere(SegHost *h, short v, long d);
/* Set by SegAskUser: the part dialog's hook answers Standard File's
 * Eject on its first call, as if clicked, and clears it. */
static SEG_DATA Boolean gSegEjectNow;
/* The disks in the drives are looked at, not remembered: the part may
 * already be on one (found, no dialog), and otherwise the first one that
 * is not the System's or this application's is the one to eject. Returns
 * 1 if the part is found on a disk in a drive, else 0; *out is the volume
 * to eject, or 0. */
static int SegLookInDrives(SegHost *h, int part, short *out)
{
    HParamBlockRec pb;
    DrvQEl *q;
    short idx, v, d;
    unsigned char f;
    long z;
    *out = 0;
    for (idx = 1; idx < 64; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.volumeParam.ioVolIndex = idx;
        if (PBHGetVInfoSync(&pb) != noErr) break;
        v = pb.volumeParam.ioVRefNum;
        d = pb.volumeParam.ioVDrvInfo;
        if (d <= 0) continue;
        for (q = (DrvQEl *)LMGetDrvQHdr().qHead; q; q = (DrvQEl *)q->qLink)
            if (q->dQDrive == d) break;
        if (q == NULL) continue;
        f = ((unsigned char *)q)[-3];
        if (f != 1 && f != 2) continue;
        if (v == SegFileVol(LMGetCurApRefNum()) ||
            v == SegFileVol(LMGetSysMap())) continue;
        SegScanHere(h, v, kSegRootDirID);
        if (h->loc[part].name[0]) return 1;
        if (*out == 0) *out = v;
    }
    return 0;
}

/* Unmounted as well as ejected: Eject alone leaves the volume mounted
 * offline, and the Finder keeps a dimmed icon for it, one per disk of a
 * long set (the LC 475, 2026-10-13). Parts remembered on the disk are
 * forgotten, because their refNums die with the volume; a MIME part on it
 * is copied off first (the LC 475, 2026-10-31). The eject itself is
 * Standard File's own, answered by the dialog's hook (SegPartHook). */
static void SegForgetDisk(SegHost *h, short vol)
{
    int p;
    short drive = SegDriveOf(vol);
    for (p = 1; p <= kSegMaxKnown; p++)
        if (h->loc[p].name[0] && SegDriveOf(h->loc[p].vRefNum) == drive) {
            if (h->desc.scheme == UNC_FORMAT_MIMESEG) {
                SegCopyIn(h, p);
                if (SegDriveOf(h->loc[p].vRefNum) != drive) continue;
            }
            h->loc[p].name[0] = 0;
        }
}

/* Find… opens in the folder of the lowest-numbered part located so far,
 * not in the one Standard File last showed, which by then is the
 * destination. SFSaveDisk holds the volume's reference number negated and
 * CurDirStore the folder's ID (Inside Macintosh: Files, *Standard File
 * Package*, Setting the Current Directory). A part's location may be a
 * working directory with folder 0, as SFGetFile answers; PBGetWDInfo
 * gives its volume and folder, and a real volume reference number comes
 * back unchanged with the root's ID. Where it fails, Standard File keeps
 * its own folder. */
static void SegStartIn(SegHost *h)
{
    WDPBRec w;
    int p;
    for (p = 1; p <= kSegMaxKnown && !h->loc[p].name[0]; p++) ;
    if (p > kSegMaxKnown) return;
    w.ioNamePtr = NULL;
    w.ioWDIndex = 0;
    w.ioWDProcID = 0;
    w.ioVRefNum = h->loc[p].vRefNum;
    if (PBGetWDInfoSync(&w) != noErr) return;
    LMSetSFSaveDisk(-w.ioWDVRefNum);
    LMSetCurDirStore(h->loc[p].dirID ? h->loc[p].dirID : w.ioWDDirID);
}

/* Ask the user to point at part `part`. Returns nonzero once it has been
 * located. The autotest build has no user, so this is not compiled there
 * and a part that was not found beside the archive is simply missing. */
/* The part is asked for in ONE dialog, Standard File's Open with a
 * prompt (DLOG/DITL 142, or 143 after an eject; mac/macextract_partdlg.r):
 * the alert and its Find..., Skip and Cancel go. Cancel means "go on
 * without this part", which is what Skip did, and the part is not asked
 * for again: on a set addressed by (part, offset), a spanned zip or
 * Compact Pro, the other parts still give up their files (measured with
 * the CLI: 10 of 12 against Cancel's 1); on a joined set Skip and Cancel
 * gave the same, nothing. Stopping the whole extraction is the progress
 * window's Cancel, as it always was.
 *
 * The disk watch is SegDiskFilter's, unchanged in what it does, as this
 * dialog's filter: when the disk put in holds the part, it closes the
 * dialog through Cancel (item 3) and says so in gSegFound. */
#define kPartDLOG       142
#define kPartEjectDLOG  143
static SEG_DATA Boolean gSegFound;

/* SegHost's volRef/volDrv: a volume that comes online after the dialog
 * opened was put in while it was up, whoever took the disk event:
 * Standard File takes it on System 6.0.8 and 7.0.1 under Mini vMac and
 * shows the disk (measured), and something else did on the maintainer's
 * 7.6.1, where the list stayed put. */

/* A disk put in that holds no part this dialog wants goes straight back
 * out, so that on a one-drive Mac the next one can go in. Never the disk
 * of this application or of the System (SegLookInDrives says why). The
 * parts it did hold are forgotten with it: asked for again when needed. */
static void SegEjectInserted(SegHost *h, short drive)
{
    ParamBlockRec pb;
    int p;
    if (drive <= 0 || drive == SegDriveOf(SegFileVol(LMGetCurApRefNum())) ||
        drive == SegDriveOf(SegFileVol(LMGetSysMap()))) return;
    for (p = 1; p <= kSegMaxKnown; p++)
        if (h->loc[p].name[0] && SegDriveOf(h->loc[p].vRefNum) == drive)
            h->loc[p].name[0] = 0;
    SysBeep(1);
    pb.volumeParam.ioNamePtr = NULL;
    pb.volumeParam.ioVRefNum = drive;
    (void)PBUnmountVol(&pb);
    pb.volumeParam.ioVRefNum = drive;
    (void)PBEject(&pb);
    /* The next disk in this drive may be given the same volume reference
     * number (hypothesis, from a System 6.0.8 run where the next disk went
     * unscanned), so the number is marked out of its drive and the shown
     * folder forgotten. */
    for (p = 0; p < h->volN; p++)
        if (h->volDrv[p] == drive) h->volDrv[p] = 0;
    h->shownVol = 0;
}


/* Each online volume that was not online at the last look, by vRefNum and
 * drive, in turn; 0 when there is none left. Records it as seen. */
static short SegNextNewVolume(SegHost *h, short *drive)
{
    HParamBlockRec pb;
    short idx, k;
    long z;
    for (idx = 1; idx < 64; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.volumeParam.ioVolIndex = idx;
        if (PBHGetVInfoSync(&pb) != noErr) return 0;
        for (k = 0; k < h->volN; k++)
            if (h->volRef[k] == pb.volumeParam.ioVRefNum) break;
        if (pb.volumeParam.ioVDrvInfo <= 0) {                  /* offline */
            if (k < h->volN) h->volDrv[k] = 0;    /* back online = put in */
            continue;
        }
        if (k < h->volN && h->volDrv[k] == pb.volumeParam.ioVDrvInfo)
            continue;                                           /* known */
        if (k == h->volN) {
            if (h->volN == kSegVols) return 0;
            h->volN++;
        }
        h->volRef[k] = pb.volumeParam.ioVRefNum;
        h->volDrv[k] = pb.volumeParam.ioVDrvInfo;
        *drive = pb.volumeParam.ioVDrvInfo;
        return pb.volumeParam.ioVRefNum;
    }
    return 0;
}

/* Called when the dialog opens: every volume online now is known. An
 * offline one is not, so it counts as put in when it comes back. */
static void SegKnowVolumes(SegHost *h)
{
    short drive;
    h->volN = 0;
    while (SegNextNewVolume(h, &drive) != 0) ;
}

/* A folder, then its family by name for a name scheme. */
static void SegScanHere(SegHost *h, short v, long d)
{
    SegScanDir(h, v, d);
    if (SegByName(h)) {
        Str63 last;
        SegScanFamily(h, v, d, h->desc.scheme == UNC_FORMAT_SPLIT, last);
    }
}

/* The disks put in since the last look, each scanned; one without the
 * wanted part goes back out, whatever the scheme. A part renamed on a
 * floppy is then found only once copied off it (the maintainer's call,
 * 2026-10-31: one drive, and the disk is out of the way). True if one
 * was ejected. */
static Boolean SegTakeNewDisks(SegHost *h)
{
    short v, drive;
    Boolean out = false;
    while ((v = SegNextNewVolume(h, &drive)) != 0) {
        SegScanHere(h, v, kSegRootDirID);
        if (h->loc[gSegWantPart].name[0]) break;
        SegEjectInserted(h, drive);
        out = true;
    }
    return out;
}

/* Source: Inside Macintosh, Standard File Package: the dialog hook gets each
 * item hit and, between them, sfHookNullEvent (100); the item it returns is
 * acted on as if clicked, getEject (5) being Eject. A getEject returned on
 * sfHookFirstCall (-1) was ignored (Mac Plus, 2026-11-16), so it waits for
 * the first null event. */
static pascal short SegPartHook(short item, DialogPtr dlg)
{
    (void)dlg;
    if (item == sfHookNullEvent && gSegEjectNow) {
        gSegEjectNow = 0;
        return getEject;
    }
    return item;
}

static pascal Boolean SegPartFilter(DialogPtr dlg, EventRecord *evt,
                                    short *itemHit)
{
    EventRecord de;
    SegHost *h = gSegAsking;
    StackSample();
    /* Back in front: drawn whole, not just where the System thinks it was
     * covered (the maintainer's LC 475, 2026-10-31: after clicks in the
     * Finder, the buttons came back part-erased). */
    if (evt->what == osEvt &&
        (evt->message & 0xFF000000) == SUSPENDRESUMEBITS &&
        !(gBackground = (evt->message & RESUME) == 0)) {
        SetPort((GrafPtr)dlg);
        InvalRect(&dlg->portRect);
    }
    if (h == NULL) return false;
    /* A disk put in: its event is taken here, at once, which mounts it
     * before Standard File can switch to it (measured: acting on the event
     * passed in, or every 30 ticks, came after Standard File had shown the
     * disk, even one then ejected). */
    if (GetNextEvent(diskMask, &de))
        (void)SegTakeNewDisks(h);
    if (TickCount() < gSegNextPoll) return false;
    gSegNextPoll = TickCount() + 30;
    /* The folder Standard File shows is scanned whenever it changes: a part
     * merely navigated to is found, and so is one on a disk Standard File
     * switched to by itself. SFSaveDisk and CurDirStore are kept up to
     * date by 6.0.8 and 9.2; System 3.0 keeps its own copy, so there only
     * a disk's root is seen. */
    {
        short v = -LMGetSFSaveDisk();
        long d = LMGetCurDirStore();
        if (v != h->shownVol || d != h->shownDir) {
            h->shownVol = v;
            h->shownDir = d;
            SegScanHere(h, v, d);
        }
    }
    (void)SegTakeNewDisks(h);      /* a disk whose event another took */
    if (h->loc[gSegWantPart].name[0]) {   /* 1..kSegMaxKnown: seg_need's */
        gSegFound = true;
        *itemHit = 3;              /* getCancel: closes the dialog */
        return true;
    }
    return false;
}

static int SegAskUser(SegHost *h, int part)
{
    Str255 msg;
    Str63 left;
    SFReply reply;
    Point where;
    short savedMask;
    short dlg = kPartDLOG, ejVol;

    if (SegLookInDrives(h, part, &ejVol)) return 1;   /* already in a drive */
    if (ejVol) {
        SegForgetDisk(h, ejVol);
        gSegEjectNow = 1;
        dlg = kPartEjectDLOG;
    }

    WaitForFront();

    for (;;) {
        msg[0] = 0;
        PStrCat(msg, S_SEG_PART);
        PStrCatNum(msg, (long)part);
        PStrCat(msg, S_SEG_OF);
        /* The set's own name; a spanned zip states none, and then it is
         * the name of the file that was opened ("" before). */
        {   const unsigned char *nm = h->desc.name;
            short n = (short)h->desc.name_len, i;
            if (!n) { nm = h->opened + 1; n = h->opened[0]; }
            for (i = 0; i < n && msg[0] < 200; i++) msg[++msg[0]] = nm[i];
        }
        PStrCat(msg, S_SEG_CLOSE_QUOTE);
        left[0] = 0;
        if (h->askLast) {          /* a split's next part, maybe none */
            PStrCat(left, S_SEG_NO_PART);
            PStrCatNum(left, (long)part);
            PStrCat(left, S_SEG_NO_PART_END);
        } else
            SegCatRemaining(left, SegRemaining(h));
        ParamText(msg, left, "\p", "\p");

        if (h->hide) HideWindow((WindowPtr)h->hide);
        gSegAsking = h;
        gSegWantPart = part;
        gSegFound = false;
        h->shownVol = 0;
        h->shownDir = -1;
        SegKnowVolumes(h);
        savedMask = LMGetSysEvtMask();
        LMSetSysEvtMask(savedMask | diskMask);
        gSegNextPoll = 0;
        SetPt(&where, 90, 90);
        reply.good = false;
        SegStartIn(h);
        if (gSegEjectNow) {         /* Standard File's Eject takes this disk */
            LMSetSFSaveDisk(-ejVol);   /* 2 = fsRtDirID */
            LMSetCurDirStore(2);
        }
        SFPGetFile(where, "\p", NewFileFilterUPP(HideInvisible), -1, NULL,
                   NewDlgHookUPP(SegPartHook), &reply, dlg, NewModalFilterUPP(SegPartFilter));
        LMSetSysEvtMask(savedMask);
        gSegAsking = NULL;
        h->asked = 1;

        if (gSegFound) break;      /* the disk put in had it */
        if (!reply.good) {         /* Cancel: go on without this part */
            h->skipped[part] = 1;
            gSegShort = true;
            break;
        }
        {
            int got = SegByName(h) ? part
                    : SegPartOf(h, reply.vRefNum, 0, reply.fName);
            if (got == part) {
                SegRemember(h, part, reply.vRefNum, 0, reply.fName);
                SegScanDir(h, reply.vRefNum, 0);
                break;
            }
            if (got) {
                Str255 t;
                t[0] = 0;
                PStrCat(t, S_SEG_THAT_PART);
                PStrCatNum(t, (long)got);
                PStrCat(t, S_SEG_NOT_PART_N);
                PStrCatNum(t, (long)part);
                PStrCat(t, ".");
                ShowNote(kErrorALRT, t);
                SegRemember(h, got, reply.vRefNum, 0, reply.fName);
            } else {
                ShowNote(kErrorALRT, "\p" S_SEG_NOT_PART);
            }
        }
    }
    if (h->hide) ShowWindow((WindowPtr)h->hide);
    return h->loc[part].name[0] != 0;
}
#endif  /* !UNC_MAC_AUTOTEST */

/* A message/partial set is read three times over (fmt_mime.c: the walk,
 * each entry's sizing pass, its writing pass), which on floppies is
 * every disk three times. So a part on another disk than the output is
 * copied beside the output the first time it is needed, as an envelope's
 * part is (SegWrappedPartOf), and read from there; SegPeelClean removes
 * it. A copy that fails is deleted, and the part is read where it is. */
static void SegCopyIn(SegHost *h, int part)
{
    SegLoc *l = &h->loc[part];
    Str255 tmp;
    short in, out, drive = l->drive;
    long n;
    OSErr e;
    Ptr buf;

    if (drive <= 0 || SegDriveOf(l->vRefNum) == SegDriveOf(h->tmpVol))
        return;
    if (MyOpenFork(l->vRefNum, l->dirID, l->name, fsRdPerm, 0, &in) != noErr)
        return;
    if ((buf = NewPtr(1024)) != NULL && SegTmpOpen(h, part, tmp, &out)) {
        do {
            n = 1024;
            e = FSRead(in, &n, buf);
            if (n > 0 && FSWrite(out, &n, buf) != noErr) e = ioErr;
        } while (e == noErr);
        FSClose(out);
        if (e == eofErr) {
            FlushVol(NULL, h->tmpVol);
            l->name[0] = 0;
            SegRemember(h, part, h->tmpVol, h->tmpDir, tmp);
            l->drive = drive;            /* still the floppy it came off */
            h->peeled = 1;
        } else
            MyHDelete(h->tmpVol, h->tmpDir, tmp);
    }
    if (buf) DisposePtr(buf);
    FSClose(in);
}

static int seg_need(void *ctx, const UncSegmentDesc *desc, int part, UncIO *io)
{
    SegHost *h = (SegHost *)ctx;
    uint32_t end = UNC_SIZE_UNKNOWN;
    long eof;
    int rsrc;

    if (part < 1 || part > kSegMaxKnown) return UNC_ERR_SEGMENTED;
#ifndef UNC_MAC_AUTOTEST
    /* A part remembered on a disk that has since left its drive (ejected,
     * still mounted) is forgotten, so this dialog asks for it rather than
     * the System's alert, which names a disk and whose Cancel fails the
     * read. A server volume never had a drive and is left alone. */
    {   SegLoc *l = &h->loc[part];
        /* An open-ended split (nparts 0): nothing says how many parts
         * there are, so whether to ask for one not found by name is
         * decided here, as the joiner reaches it. Below the highest
         * number seen, it is a gap and missing. Past it, the set may go
         * on after .001, or after a part as long as the one before it (a
         * cutter cuts fixed pieces and the remainder goes last): then it
         * is asked for, and Cancel says the set ends there. After a
         * shorter part it ends without a question. */
        Boolean split = h->desc.scheme == UNC_FORMAT_SPLIT &&
                        h->desc.nparts == 0;
        Boolean open = split && part > h->highest;
        if (l->name[0] && l->drive > 0 && SegDriveOf(l->vRefNum) == 0)
            l->name[0] = 0;
        if (!l->name[0] && !h->cancelled) {
            if (open && (h->skipped[part] || !(part == 2 ||
                    SegPartLength(h, part - 1) == SegPartLength(h, part - 2))))
                return UNC_SEG_ENDS;
            if (!h->skipped[part]) {
                h->askLast = open;
                SegAskUser(h, part);
                h->askLast = 0;
                if (open && !h->cancelled && !l->name[0]) return UNC_SEG_ENDS;
                if (split && l->name[0]) {     /* and its neighbours by name */
                    Str63 last;
                    SegScanFamily(h, l->vRefNum, l->dirID, 1, last);
                }
            }
        }
    }
    if (h->cancelled) return UNC_ERR_ABORTED;
#endif
    if (!h->loc[part].name[0]) {
        gSegShort = true;
        return UNC_ERR_SEGMENTED;
    }
    if (h->desc.scheme == UNC_FORMAT_MIMESEG) SegCopyIn(h, part);

    /* A fat installer's part 1 goes on past its segment, and its resource
     * fork says where the segment stops (unc_segment_first_end): for part
     * 1 the loop opens that fork first and closes it again, so that one
     * fork is open at a time. SegHaveAll still counts the whole data
     * fork, so it can take a fat set for complete one part early; the
     * engine then asks for that part like any other. */
    for (rsrc = part == 1; ; rsrc = 0) {
        eof = 0;
        if (MyOpenFork(h->loc[part].vRefNum, h->loc[part].dirID,
                       h->loc[part].name, fsRdPerm, rsrc, &h->refNum) == noErr)
            GetEOF(h->refNum, &eof);
        if (eof <= 0) {
            if (h->refNum) FSClose(h->refNum);
            h->refNum = 0;
            if (rsrc) continue;
            return UNC_ERR_SEGMENTED;
        }
        h->fio.refNum = h->refNum;
        h->fio.size = (uint32_t)eof;
        h->fio.pos = 0;
        io->ctx = &h->fio;
        io->read = fio_read;
        io->seek = fio_seek;
        io->tell = fio_tell;
        io->size = fio_size;
        if (!rsrc) break;
        end = unc_segment_first_end(desc, io, end);
        FSClose(h->refNum);
        h->refNum = 0;
    }
    if (end < h->fio.size) h->fio.size = end;

    /* What this part contributes to the whole, for the "still to read"
     * line in the alert. Every part carries the same header, which is
     * not payload. */
    h->psize[part] = h->fio.size > h->desc.head_len
                   ? h->fio.size - h->desc.head_len : 0;
    return UNC_OK;
}

/* A part's size, for the progress bar's total only (macextract.h,
 * UncVolumeSource.size): the length recorded when the part was found,
 * else unknown. Never by looking, as a disk that is out would be asked
 * for. Without this the bar of a spanned zip or a Compact Pro set never
 * had a total, from a hard disk or from floppies (the LC 475,
 * 2026-10-30); the joiner estimates the parts not seen yet. */
static uint32_t seg_part_size(void *ctx, const UncSegmentDesc *desc, int part)
{
    SegHost *h = (SegHost *)ctx;
    (void)desc;
    if (part < 1 || part > kSegMaxKnown || !h->plen[part])
        return UNC_SIZE_UNKNOWN;
    return h->plen[part];
}

static void seg_release(void *ctx, UncIO *io)
{
    SegHost *h = (SegHost *)ctx;
    (void)io;
    if (h->refNum) { FSClose(h->refNum); h->refNum = 0; }
}
