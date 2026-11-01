/*
 * seg_setup.inc.c — a segmented set's setup, before the join: finding its
 * parts (beside the opened one, inside envelopes, by name), counting them
 * and building the joiner's descriptor. Included by macextract_mac.c, and
 * with UNC_POC_PARTDLG by tools/overlay/ovl_segsetup.c instead, so that it
 * costs the heap nothing once the bundle is given back.
 *
 * SS(f) is how this file reaches anything resident: the function itself
 * when it is compiled into the application, the entry in SegSetupFns when
 * it is an image, which cannot name an application symbol.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
/* ------------------------------------------------------------------ */
/* Parts that arrived inside an envelope                               */
/*                                                                    */
/* A real download is per-part wrapped — Archive.sit.1.hqx — so the    */
/* envelope has to come off each part BEFORE the join. On this side    */
/* that means writing the decoded part somewhere, which is the whole   */
/* difference from the Linux CLI: it peeks ~100 bytes and decodes to a */
/* file, and so does this, but here the file lands on the output       */
/* volume and is deleted when the join is over.                        */
/*                                                                    */
/* StuffIt only, for the reason the CLI gives: its header is IN the    */
/* payload, so unwrapping is all that stands between a wrapped part    */
/* and the fingerprint check every other part gets. A spanned zip or a */
/* .NNN part is placed by FILENAME, and the filename of a wrapped part */
/* is the wrapper's.                                                   */
/* ------------------------------------------------------------------ */

/* Read the part count out of the one file that has it — the ".zip"
 * member of a spanned set. Returns nonzero on success, having filled in
 * the descriptor and recorded that file as the last part. */
static int SegDescribeLast(SegHost *h, short vol, long dir,
                           ConstStr255Param nm)
{
    UncSegmentDesc cand;
    FileIO probe;
    UncIO pio;
    short ref;
    long eof = 0;
    int ok;

    if (SS(MyOpenFork)(vol, dir, nm, fsRdPerm, 0, &ref) != noErr) return 0;
    SS(GetEOF)(ref, &eof);
    probe.refNum = ref;
    probe.size = (uint32_t)eof;
    probe.pos = 0;
    pio.ctx = &probe;
    pio.read = SS(fio_read);
    pio.seek = SS(fio_seek);
    pio.tell = SS(fio_tell);
    pio.size = SS(fio_size);
    ok = SS(unc_segment_describe)(&pio, &cand) == UNC_OK && cand.nparts;
    SS(FSClose)(ref);
    if (!ok) return 0;
    h->desc = cand;
    SS(SegRemember)(h, (int)cand.nparts, vol, dir, nm);
    if ((int)cand.nparts > h->highest) h->highest = (int)cand.nparts;
    return 1;
}


static int env_begin(void *ctx, const UncEntryInfo *info)
{
    EnvSink *e = (EnvSink *)ctx;
    if (info->is_dir) { e->entries++; return 1; }
    return e->entries++ ? 1 : 0;         /* the first file is the payload */
}


static int env_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{
    EnvSink *e = (EnvSink *)ctx;

    if (fork != UNC_FORK_DATA || len <= 0) return 0;
    if (e->outRef) {
        long count = (long)len;
        if (SS(FSWrite)(e->outRef, &count, (const void *)buf) != noErr ||
            count != (long)len) { e->err = 1; return -1; }
        return 0;
    }
    if (e->len < e->cap) {
        int32_t n = e->cap - e->len, i;
        const uint8_t *sp = (const uint8_t *)buf;
        if (n > len) n = len;
        for (i = 0; i < n; i++) e->head[e->len + i] = sp[i];
        e->len += n;
    }
    /* Enough to decide on; the abort is reported as a per-entry failure,
     * which is why a peek is judged by what it collected. */
    return e->len >= e->cap ? -1 : 0;
}


static int env_end(void *ctx, int status)
{
    EnvSink *e = (EnvSink *)ctx;
    if (e->outRef && status != UNC_OK) e->err = 1;
    return 0;
}


/* The allocator a peek runs on: plain NewPtr and DisposePtr, outside the
 * engine's budget. SegScanWrapped unwraps envelopes beside a set before
 * RunExtract has built `al`, and must not take the budget early either:
 * mal_alloc fixes it at its first call, and that is meant to come after
 * the overlay release. Until 2026-10-18 the peek was handed `al` still
 * uninitialised, harmless while no envelope reader allocated; AppleSingle's
 * comment then did, and a split set beside an AppleSingle with a comment
 * crashed the application (the maintainer's LC 475; DECISIONS.md
 * 2026-10-18, *the allocator nobody had built yet*). */
static void *peek_alloc(void *ctx, uint32_t size)
{
    (void)ctx;
    return NewPtr((Size)size);
}


static void peek_free(void *ctx, void *ptr)
{
    (void)ctx;
    if (ptr) DisposePtr((Ptr)ptr);
}


/* Run one envelope layer of a file into `es`. 0 if it is not one. */
static int EnvRun(short vol, long dir, ConstStr255Param nm, EnvSink *es,
                  UncAlloc *al)
{
    FileIO fio;
    UncIO eio;
    UncSink sk;
    UncProgress prog;
    UncFormat fmt;
    short ref;
    long eof = 0;
    int rc;

    if (SS(MyOpenFork)(vol, dir, nm, fsRdPerm, 0, &ref) != noErr) return 0;
    SS(GetEOF)(ref, &eof);
    fio.refNum = ref;
    fio.size = (uint32_t)eof;
    fio.pos = 0;
    eio.ctx = &fio;
    eio.read = SS(fio_read);
    eio.seek = SS(fio_seek);
    eio.tell = SS(fio_tell);
    eio.size = SS(fio_size);

    fmt = SS(unc_sniff_envelope)(&eio);
    if (!SS(unc_format_is_envelope)(fmt)) {
        SS(FSClose)(ref);
        return 0;
    }
    sk.ctx = es;
    sk.begin_entry = env_begin;
    sk.write = env_write;
    sk.end_entry = env_end;
    sk.comment = NULL;    /* an envelope layer carries none */
    prog.ctx = NULL;
    prog.tick = NULL;
    rc = SS(unc_extract_as)(fmt, &eio, &sk, al, NULL, NULL);
    SS(FSClose)(ref);
    if (es->outRef && rc != UNC_OK) es->err = 1;
    return 1;
}


/* Do the parts found so far account for the whole set? StuffIt states
 * the payload total in every part, so this is the same sum that ends the
 * joiner's walk — and it is the only question that decides whether
 * opening envelopes is worth anything. */
static int SegHaveAll(SegHost *h)
{
    uint32_t sum = 0;
    int p;

    if (h->desc.total == UNC_SIZE_UNKNOWN) return 0;
    for (p = 1; p <= kSegMaxKnown && h->loc[p].name[0]; p++) {
        uint32_t len = SS(SegPartLength)(h, p);
        if (len == UNC_SIZE_UNKNOWN || len <= h->desc.head_len) return 0;
        sum += len - h->desc.head_len;
        if (sum >= h->desc.total) return 1;
    }
    return 0;
}


/* Is this file an envelope holding a part of the set? If so it is
 * decoded whole, next to the output, and recorded. */
static int SegWrappedPartOf(SegHost *h, short vol, long dir,
                            ConstStr255Param nm, UncAlloc *al)
{
    uint8_t head[UNC_SEG_HEAD];
    EnvSink es;
    Str255 tmp;              /* PStrCat's contract is Str255, not Str63 */
    int part;
    short ref;
    long z;

    for (z = 0; z < (long)sizeof es; z++) ((char *)&es)[z] = 0;
    es.head = head;
    es.cap = (int32_t)sizeof head;
    if (!EnvRun(vol, dir, nm, &es, al)) return 0;
    part = es.len > 0 ? SS(unc_segment_match)(&h->desc, head, es.len) : 0;
    if (part < 1) return 0;
    if (h->loc[part].name[0]) return part;      /* already have that one */

    if (!SS(SegTmpOpen)(h, part, tmp, &ref)) return 0;
    for (z = 0; z < (long)sizeof es; z++) ((char *)&es)[z] = 0;
    es.outRef = ref;
    if (!EnvRun(vol, dir, nm, &es, al) || es.err) {
        SS(FSClose)(ref);
        SS(MyHDelete)(h->tmpVol, h->tmpDir, tmp);
        return 0;
    }
    SS(FSClose)(ref);
    SS(FlushVol)(NULL, h->tmpVol);
    SS(SegRemember)(h, part, h->tmpVol, h->tmpDir, tmp);
    h->peeled = 1;
    return part;
}


/* Walk a folder looking INSIDE envelopes. Only ever called when the set
 * is short of a part: a complete one opens nothing. */
static void SegScanWrapped(SegHost *h, short vol, long dir, UncAlloc *al)
{
    CInfoPBRec pb;
    Str63 nm;
    short idx;
    long z;

    for (idx = 1; idx < 32767; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        nm[0] = 0;
        pb.hFileInfo.ioNamePtr = nm;
        pb.hFileInfo.ioVRefNum = vol;
        pb.hFileInfo.ioDirID = dir;
        pb.hFileInfo.ioFDirIndex = idx;
        if (PBGetCatInfoSync(&pb) != noErr) break;
        if (pb.hFileInfo.ioFlAttrib & 0x10) continue;          /* a folder */
        if (SS(SegPartOf)(h, vol, dir, nm)) continue;      /* a part in its own right */
        SegWrappedPartOf(h, vol, dir, nm, al);
        if (SegHaveAll(h)) break;
    }
}


/* Which of these parts knows how many there are?
 *
 * Two schemes need this and for the same reason — Compact Pro, where
 * only the last segment carries the index, and message/partial, where
 * only the last part must carry `total`.
 *
 * Only the last one carries the index, and only the index says how many
 * segments there are — so a set opened at any other segment has no
 * count, and neither the joiner nor the "part N of M" arithmetic can
 * start. Every segment identifies itself (a 16-bit set identity in its
 * header), so the answer is here on the disk; it just has to be asked
 * for, one 8-byte header at a time. The CLI does exactly this.
 *
 * Leaves h->desc alone if no part answers, and the caller then reports
 * the set as incomplete, which it is: without the final segment there
 * is no directory anywhere. */
static void SegFindLast(SegHost *h)
{
    int p;

    for (p = 1; p <= kSegMaxKnown; p++) {
        UncSegmentDesc cand;
        FileIO probe;
        UncIO pio;
        short ref;
        long eof = 0;

        if (!h->loc[p].name[0]) continue;
        if (SS(MyOpenFork)(h->loc[p].vRefNum, h->loc[p].dirID, h->loc[p].name,
                       fsRdPerm, 0, &ref) != noErr) continue;
        SS(GetEOF)(ref, &eof);
        probe.refNum = ref;
        probe.size = (uint32_t)eof;
        probe.pos = 0;
        pio.ctx = &probe;
        pio.read = SS(fio_read);
        pio.seek = SS(fio_seek);
        pio.tell = SS(fio_tell);
        pio.size = SS(fio_size);
        if (SS(unc_segment_describe)(&pio, &cand) == UNC_OK && cand.nparts) {
            h->desc = cand;
            SS(FSClose)(ref);
            return;
        }
        SS(FSClose)(ref);
    }
}


/* Everything about a set that is settled before the join starts: where
 * its parts are, how many there are, and the descriptor the joiner is
 * handed. Moved here from ExtractOne whole; its failures were each four
 * lines of cleanup there, which the caller now does once. */
static int SegSetup(const SegSetupArgs *A)
{
    SegHost *sh = A->sh;
    const unsigned char *name = A->name;
    const unsigned char *famStem = A->famStem;
    short famStemLen = A->famStemLen;
    int famSplit = A->famSplit, famZip = A->famZip;
    short inVol = A->inVol, origVol = A->origVol, outVol = A->outVol;
    long inDir = A->inDir, origDir = A->origDir, outDir = A->outDir;

            if (famSplit || famZip) {
                short i;
                Str63 lastName;
                for (i = 0; i < famStemLen; i++) sh->stem[i] = famStem[i];
                sh->stemlen = famStemLen;
                SS(SegScanFamily)(sh, inVol, inDir, famSplit, lastName);
                if (famZip) {
                    /* Only the ".zip" member carries the part count, so
                     * it has to be read before anything else can be. */
                    if (!lastName[0] ||
                        !SegDescribeLast(sh, inVol, inDir, lastName)) {
                        return UNC_ERR_SEGMENTED;
                    }
                } else {
                    /* Nothing in a split says anything, so the whole
                     * descriptor is built here: the set is the
                     * consecutive run of NAME.NNN, the joined file is
                     * called NAME, and its length is the sum of the
                     * parts' — which is why every one is measured now
                     * rather than disk by disk. */
                    int p, run = 0;
                    uint32_t total = 0;
                    long z;
                    for (z = 0; z < (long)sizeof sh->desc; z++)
                        ((char *)&sh->desc)[z] = 0;
                    sh->desc.scheme = UNC_FORMAT_SPLIT;
                    sh->desc.part = 1;
                    sh->desc.head_len = 0;
                    for (i = 0; i < famStemLen && i < UNC_NAME_MAX; i++)
                        sh->desc.name[i] = famStem[i];
                    sh->desc.name[i] = 0;
                    sh->desc.name_len = (uint16_t)i;
                    while (run < kSegMaxKnown && sh->loc[run + 1].name[0])
                        run++;
#ifdef UNC_POC_PARTDLG
                    /* PoC: OPEN-ENDED (macextract.h, UNC_SEG_ENDS). The
                     * joiner asks for each next part as it gets there,
                     * and seg_need decides there whether the set may go
                     * on; a gap is asked for like any missing part. */
                    if (run >= 1) {
                        sh->desc.nparts = 0;
                        sh->desc.total = UNC_SIZE_UNKNOWN;
                        sh->desc.data_size = UNC_SIZE_UNKNOWN;
                        goto split_ready;
                    }
#endif
                    if (run < 1 || run < sh->highest) {
                        /* A member numbered past the end of the run says
                         * the gap is a missing part, not the end. */
                        return UNC_ERR_SEGMENTED;
                    }
                    for (p = 1; p <= run; p++) {
                        uint32_t len = SS(SegPartLength)(sh, p);
                        if (len == UNC_SIZE_UNKNOWN) { total = UNC_SIZE_UNKNOWN; break; }
                        total += len;
                    }
                    if (total == UNC_SIZE_UNKNOWN) {
                        return UNC_ERR_SEGMENTED;
                    }
                    sh->desc.nparts = (uint16_t)run;
                    sh->desc.total = total;
                    sh->desc.data_size = total;
#ifdef UNC_POC_PARTDLG
                split_ready: ;
#endif
                }
            } else {
            sh->desc = *A->desc;
            /* A `SPLT` set stores no name for the file it joins into.
             * The opened part's is all there is, minus the ".N" that
             * numbers it — for the output file, never for matching:
             * the parts are found by content like a StuffIt set's. */
            if (A->desc->scheme == UNC_FORMAT_DDSEG ||
                A->desc->scheme == UNC_FORMAT_MIMESEG) {
                short n = name[0], d, i;
                if (n > UNC_NAME_MAX) n = UNC_NAME_MAX;
                d = n;
                while (d >= 1 && name[d] >= '0' && name[d] <= '9') d--;
                if (d < n && d >= 2 && name[d] == '.') n = (short)(d - 1);
                for (i = 0; i < n; i++) sh->desc.name[i] = name[i + 1];
                sh->desc.name[n] = 0;
                sh->desc.name_len = (uint16_t)n;
            }
            sh->tmpVol = outVol;
            sh->tmpDir = outDir;
            /* The file we were opened on is a part, at the number its
             * own header states — so opening part 3 of a set works. */
            SS(SegRemember)(sh, (int)sh->desc.part, inVol, inDir, name);
            SS(SegScanDir)(sh, inVol, inDir);
            /* A part that arrived wrapped was unwrapped into the OUTPUT
             * folder, so the rest of the set is not there: it is still
             * where the user left it. */
            if (origVol != inVol || origDir != inDir)
                SS(SegScanDir)(sh, origVol, origDir);
            /* Only now, and only if something is still missing, is it
             * worth taking envelopes off to look — which is how a real
             * download arrives, and also how a half-unstuffed one does.
             * A complete set opens nothing beside it. */
            if (sh->desc.scheme == UNC_FORMAT_SITSEG && !SegHaveAll(sh)) {
                UncAlloc pal;
                pal.ctx = NULL;
                pal.alloc = peek_alloc;
                pal.free = peek_free;
                if (origVol != inVol || origDir != inDir)
                    SegScanWrapped(sh, origVol, origDir, &pal);
                SegScanWrapped(sh, inVol, inDir, &pal);
            }
            /* A message/partial set is required to state its part
             * count only on the LAST part (RFC 2046 5.2.2), so a set
             * opened anywhere else asks the parts it found — the same
             * question SegFindLast answers for Compact Pro, and the
             * same answer: the desc of whichever part knows. */
            if (sh->desc.nparts == 0 &&
                sh->desc.scheme == UNC_FORMAT_MIMESEG)
                SegFindLast(sh);
            /* A Compact Pro set opened anywhere but its last segment
             * does not yet know how many segments it has. */
            if (sh->desc.nparts == 0 &&
                sh->desc.scheme == UNC_FORMAT_CPTSEG) {
                SegFindLast(sh);
#ifdef UNC_POC_PARTDLG
                /* No index anywhere: the set is short of its last part,
                 * and reading on would only report it as damaged. */
                if (sh->desc.nparts == 0) {
                    return UNC_ERR_SEGMENTED;
                }
#endif
                if (sh->desc.nparts) {
                    /* With a count in hand the match rule is stricter —
                     * a middle segment must not carry an index and the
                     * last one must — so everything found under the
                     * looser one is looked at again. Two bytes of
                     * identity is not much to let a file in on. */
                    long z;
                    for (z = 0; z < (long)sizeof sh->loc; z++)
                        ((char *)sh->loc)[z] = 0;
                    SS(SegScanDir)(sh, inVol, inDir);
                }
            }
            }
    return UNC_OK;
}
