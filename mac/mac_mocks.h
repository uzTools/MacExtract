/*
 * mac_mocks.h — Linux-backed mock of the classic Mac Toolbox subset
 * that macextract_mac.c's sink/allocator/io code uses. Lets the ACTUAL
 * Mac sink code be compiled and run on Linux (native or, more usefully,
 * big-endian m68k via qemu) under ASan/Valgrind, so memory bugs in the
 * sink glue are caught deterministically.  Test build only
 * (UNC_SINK_TEST); never part of the real Mac app.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef MAC_MOCKS_H
#define MAC_MOCKS_H

#include <stdint.h>
#include <stddef.h>

typedef unsigned char  Boolean;
typedef signed char    SignedByte;
typedef short          OSErr;
typedef short          INTEGER;
typedef long           LONGINT;
typedef char          *Ptr;
typedef Ptr           *Handle;
typedef long           Size;
typedef unsigned long  OSType;
typedef unsigned char  Str63[64];
typedef unsigned char  Str255[256];
typedef const unsigned char *ConstStr255Param;
typedef const unsigned char *ConstStringPtr;
typedef unsigned char *StringPtr;
typedef void          *DialogPtr;
typedef void          *WindowPtr;

#define noErr        0
#define eofErr       (-39)
#define dupFNErr     (-48)
#define fnfErr       (-43)
#define ioErr        (-36)
#define dskFulErr    (-34)
#define fsRdPerm     1
#define fsWrPerm     2
#define fsFromStart  1
#define fsFromLEOF   2
#define true  1
#define false 0

/* Finder info + catalog param block: only the fields the sink uses. */
typedef struct FInfo { OSType fdType; OSType fdCreator; short fdFlags;
                       short fdY, fdX; short fdFldr; } FInfo;
typedef struct DInfo { char pad[16]; } DInfo;

typedef struct HFileInfo {
    Ptr        ioCompletion;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      ioFRefNum;
    char       filler1;
    short      ioFDirIndex;
    SignedByte ioFlAttrib;
    SignedByte ioACUser;
    FInfo      ioFlFndrInfo;
    long       ioDirID;
    long       ioFlStBlk, ioFlLgLen, ioFlPyLen;
    long       ioFlRStBlk, ioFlRLgLen, ioFlRPyLen;
    unsigned long ioFlCrDat, ioFlMdDat;
} HFileInfo;

typedef struct DirInfo {
    Ptr        ioCompletion;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      ioFRefNum;
    char       filler1;
    short      ioFDirIndex;
    SignedByte ioFlAttrib;
    SignedByte ioACUser;
    DInfo      ioDrUsrWds;
    long       ioDrDirID;
} DirInfo;

typedef union CInfoPBRec { HFileInfo hFileInfo; DirInfo dirInfo; } CInfoPBRec;

typedef struct HFileParam {
    Ptr        ioCompletion;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      ioFRefNum;
    char       filler1;
    short      ioFDirIndex;
    long       ioDirID;
} HFileParam;
/* IOParam overlaps HFileParam's prefix (ioNamePtr/ioVRefNum at the same
 * offsets); ioRefNum/ioPermssn stay before ioDirID so the two views don't
 * clobber each other in MyOpenFork/MyHCreate. */
typedef struct HIOParam {
    Ptr        ioCompletion;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      ioRefNum;
    char       ioVersNum;
    char       ioPermssn;
} HIOParam;
typedef union HParamBlockRec {
    HFileParam fileParam;
    HIOParam   ioParam;
} HParamBlockRec;

/* Toolbox calls, implemented in tests/mac_sink_test.c. */
Ptr  NewPtr(Size n);
Ptr  NewPtrClear(Size n);
void DisposePtr(Ptr p);
long FreeMem(void);
void PurgeSpace(Size *total, Size *contig);
void BlockMoveData(const void *src, void *dst, Size n);
void NumToString(long v, StringPtr s);

OSErr HCreate(short vref, long dir, ConstStr255Param name, OSType cr, OSType ty);
OSErr HOpen(short vref, long dir, ConstStr255Param name, SignedByte perm, short *ref);
OSErr HOpenRF(short vref, long dir, ConstStr255Param name, SignedByte perm, short *ref);
OSErr PBHOpenSync(HParamBlockRec *pb);
OSErr PBHOpenRFSync(HParamBlockRec *pb);
OSErr PBHCreateSync(HParamBlockRec *pb);
OSErr PBHDeleteSync(HParamBlockRec *pb);
OSErr FSRead(short ref, long *count, void *buf);
OSErr FSWrite(short ref, long *count, const void *buf);
OSErr FSClose(short ref);
OSErr SetFPos(short ref, short mode, long off);
OSErr GetFPos(short ref, long *pos);
OSErr GetEOF(short ref, long *eof);
OSErr SetEOF(short ref, long eof);
OSErr PBGetCatInfoSync(CInfoPBRec *pb);
OSErr PBSetCatInfoSync(CInfoPBRec *pb);
OSErr PBDirCreateSync(HParamBlockRec *pb);
OSErr FlushVol(ConstStringPtr volName, short vRefNum);

#endif /* MAC_MOCKS_H */
