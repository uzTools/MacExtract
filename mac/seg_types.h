/*
 * seg_types.h — the segment host's types, shared by macextract_mac.c and
 * the image that sets a set up (tools/overlay/ovl_segsetup.c, with
 * UNC_POC_PARTDLG). Both must see the same layout: the image defines
 * UNC_POC_PARTDLG itself, as an image is built without -D.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_SEG_TYPES_H
#define UNC_SEG_TYPES_H

typedef struct {
    short    refNum;
    uint32_t size;
    uint32_t pos;
} FileIO;

#define kSegMaxKnown 64      /* parts we can remember where to find */
#define kSegVols 24          /* volumes the part dialog keeps track of */

typedef struct {
    short vRefNum;
    long  dirID;
    Str63 name;
#ifdef UNC_POC_PARTDLG
    short drive;        /* its disk's drive when remembered; 0 for none */
#endif
} SegLoc;

typedef struct {
    UncSegmentDesc desc;
    SegLoc  loc[kSegMaxKnown + 1];   /* loc[p].name[0] == 0 => unknown */
    /* Payload bytes of each part actually opened, so that "how much is
     * left" is a sum over what has been SEEN rather than a running
     * total. Indexed by part, so a part opened twice counts once. */
    uint32_t psize[kSegMaxKnown + 1];
    FileIO  fio;                     /* the one open part */
    short   refNum;                  /* 0 = nothing open */
    DialogPtr hide;                  /* progress dialog to hide while asking */
    int     asked;                   /* nonzero once the user was involved */
    int     cancelled;               /* user chose Cancel in the alert */
    /* Name-placed schemes only: the stem the family shares, and the
     * highest member number seen — which is how a set missing a part in
     * the middle is told from one that simply ends there. */
    unsigned char stem[64];
    short   stemlen;
    int     highest;
    /* Where a part that arrived inside an envelope is decoded to, and
     * whether any was. */
    short   tmpVol;
    long    tmpDir;
    int     peeled;
#ifdef UNC_POC_PARTDLG
    unsigned char skipped[kSegMaxKnown + 1];   /* Cancel: go on without it */
    Str63   opened;      /* the file opened: the set's name where it has none */
    unsigned char askLast;   /* the part asked for may not exist (a split) */
    uint32_t plen[kSegMaxKnown + 1];  /* a part's length, kept past its disk */
    short   lastDrive;   /* the drive the part read last came off; 0 none */
    /* The part dialog's own, here rather than in globals so that they
     * cost the heap only while a set is being joined: the folder
     * Standard File showed last, and the volumes mounted when the
     * dialog opened with the drive each was in (0: offline, or none). */
    short   shownVol;
    long    shownDir;
    short   volRef[kSegVols], volDrv[kSegVols], volN;
#endif
} SegHost;

typedef struct {
    short    outRef;         /* PEEL: fork being written, 0 in peek mode */
    uint8_t *head;           /* PEEK: where the first bytes go           */
    int32_t  cap, len;
    int      entries;
    int      err;
} EnvSink;

/* SegSetup's inputs: what ExtractOne knows about the file it opened. */
typedef struct {
    SegHost *sh;
    const UncSegmentDesc *desc;     /* the opened file's, when it said one */
    const unsigned char *name;      /* the opened file's name */
    const unsigned char *famStem;   /* NAME of NAME.001 / NAME.zip */
    short famStemLen;
    int   famSplit, famZip;
    short inVol, origVol, outVol;
    long  inDir, origDir, outDir;
} SegSetupArgs;

/* What the image calls back: the application's own helpers, the engine's
 * entry points, and the File Manager calls Retro68 provides as library
 * glue rather than inline traps. */
typedef struct {
    OSErr (*MyOpenFork)(short, long, ConstStr255Param, SignedByte, int, short *);
    OSErr (*MyHDelete)(short, long, ConstStr255Param);
    pascal OSErr (*FSClose)(short);
    pascal OSErr (*GetEOF)(short, long *);
    pascal OSErr (*FSWrite)(short, long *, const void *);
    pascal OSErr (*FlushVol)(ConstStringPtr, short);
    int  (*SegTmpOpen)(SegHost *, int, Str255, short *);
    void (*SegRemember)(SegHost *, int, short, long, ConstStr255Param);
    void (*SegScanDir)(SegHost *, short, long);
    void (*SegScanFamily)(SegHost *, short, long, int, Str63);
    uint32_t (*SegPartLength)(SegHost *, int);
    int  (*SegPartOf)(SegHost *, short, long, ConstStr255Param);
    UncFormat (*unc_sniff_envelope)(UncIO *);
    int  (*unc_format_is_envelope)(UncFormat);
    int  (*unc_extract_as)(UncFormat, UncIO *, UncSink *, UncAlloc *,
                           UncProgress *, const UncOptions *);
    int  (*unc_segment_describe)(UncIO *, UncSegmentDesc *);
    int  (*unc_segment_match)(const UncSegmentDesc *, const uint8_t *, int32_t);
    int32_t   (*fio_read)(void *, void *, int32_t);
    int       (*fio_seek)(void *, unc_off_t);
    unc_off_t (*fio_tell)(void *);
    unc_off_t (*fio_size)(void *);
} SegSetupFns;

#endif
