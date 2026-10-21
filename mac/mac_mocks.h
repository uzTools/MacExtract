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
typedef uint32_t       OSType;   /* 4 bytes, as on the Mac */
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
#define fLckdErr     (-45)
#define paramErr     (-50)
#define fsRdPerm     1
#define fsWrPerm     2
#define fsFromStart  1
#define fsFromLEOF   2
#define true  1
#define false 0

/* Finder info and the catalog param blocks, laid out as the 68000 lays
 * them: 2-byte packing, so that FInfo, FXInfo, DInfo and DXInfo are 16
 * bytes each and HFileInfo and DirInfo share the offsets of the dates,
 * the extended Finder info and the directory IDs, which the shell relies
 * on (StampCat uses the file view for a folder). Field order is
 * Multiverse.h's (Retro68's universal interfaces). Pointers stay host
 * pointers, which moves both views' heads by the same amount. */
#pragma pack(push, 2)
typedef struct Point { short v, h; } Point;
typedef struct FInfo { OSType fdType; OSType fdCreator; uint16_t fdFlags;
                       Point fdLocation; uint16_t fdFldr; } FInfo;
typedef struct FXInfo { uint16_t fdIconID; uint16_t fdUnused[4];
                        uint16_t fdComment; int32_t fdPutAway; } FXInfo;
typedef struct DInfo { short frRect[4]; uint16_t frFlags; Point frLocation;
                       uint16_t frView; } DInfo;
typedef struct DXInfo { Point frScroll; int32_t frOpenChain;
                        uint16_t frUnused; uint16_t frComment;
                        int32_t frPutAway; } DXInfo;

typedef struct HFileInfo {
    Ptr        ioCompletion;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      ioFRefNum;
    SignedByte ioFVersNum;
    SignedByte filler1;
    short      ioFDirIndex;
    SignedByte ioFlAttrib;
    SignedByte ioACUser;
    FInfo      ioFlFndrInfo;
    int32_t    ioDirID;
    short      ioFlStBlk;
    int32_t    ioFlLgLen, ioFlPyLen;
    short      ioFlRStBlk;
    int32_t    ioFlRLgLen, ioFlRPyLen;
    uint32_t   ioFlCrDat, ioFlMdDat, ioFlBkDat;
    FXInfo     ioFlXFndrInfo;
    int32_t    ioFlParID;
    int32_t    ioFlClpSiz;
} HFileInfo;

typedef struct DirInfo {
    Ptr        ioCompletion;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      ioFRefNum;
    SignedByte ioFVersNum;
    SignedByte filler1;
    short      ioFDirIndex;
    SignedByte ioFlAttrib;
    SignedByte ioACUser;
    DInfo      ioDrUsrWds;
    int32_t    ioDrDirID;
    uint16_t   ioDrNmFls;
    uint16_t   filler3[9];
    uint32_t   ioDrCrDat, ioDrMdDat, ioDrBkDat;
    DXInfo     ioDrFndrInfo;
    int32_t    ioDrParID;
} DirInfo;

typedef union CInfoPBRec { HFileInfo hFileInfo; DirInfo dirInfo; } CInfoPBRec;

typedef struct HFileParam {
    Ptr        ioCompletion;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      ioFRefNum;
    SignedByte ioFVersNum;
    SignedByte filler1;
    short      ioFDirIndex;
    SignedByte ioFlAttrib;
    SignedByte ioFlVersNum;
    FInfo      ioFlFndrInfo;
    int32_t    ioDirID;
} HFileParam;
typedef struct HIOParam {
    Ptr        ioCompletion;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      ioRefNum;
    char       ioVersNum;
    char       ioPermssn;
    Ptr        ioMisc;
    Ptr        ioBuffer;
    int32_t    ioReqCount;
} HIOParam;
typedef union HParamBlockRec {
    HFileParam fileParam;
    HIOParam   ioParam;
} HParamBlockRec;

/* The Desktop Manager's block: only the fields the shell uses, in
 * Multiverse.h's order. */
typedef struct DTPBRec {
    Ptr        ioCompletion;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      ioDTRefNum;
    short      ioIndex;
    int32_t    ioTagInfo;
    Ptr        ioDTBuffer;
    int32_t    ioDTReqCount;
    int32_t    ioDTActCount;
    char       ioFiller1;
    SignedByte ioIconType;
    short      ioFiller2;
    int32_t    ioDirID;
    OSType     ioFileCreator;
    OSType     ioFileType;
} DTPBRec;

/* A working directory's block, Multiverse.h's layout, for the three
 * fields DTBundle sets and the one PBOpenWD answers in. */
typedef struct WDPBRec {
    Ptr        qLink;
    short      qType;
    short      ioTrap;
    Ptr        ioCmdAddr;
    Ptr        ioCompletion;
    OSErr      ioResult;
    StringPtr  ioNamePtr;
    short      ioVRefNum;
    short      filler1;
    short      ioWDIndex;
    int32_t    ioWDProcID;
    short      ioWDVRefNum;
    short      filler2[7];
    int32_t    ioWDDirID;
} WDPBRec;
#pragma pack(pop)

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
OSErr PBHSetFLockSync(HParamBlockRec *pb);
OSErr PBHRstFLockSync(HParamBlockRec *pb);
OSErr PBHGetVolParmsSync(HParamBlockRec *pb);
OSErr PBDTGetPath(DTPBRec *pb);
OSErr PBDTSetCommentSync(DTPBRec *pb);
OSErr PBDTFlushSync(DTPBRec *pb);
OSErr PBDTAddAPPLSync(DTPBRec *pb);
OSErr PBDTAddIconSync(DTPBRec *pb);
/* The Resource Manager, as far as DTBundle reads an application's fork. */
short  CurResFile(void);
void   UseResFile(short ref);
void   SetResLoad(Boolean load);
OSErr  PBOpenWDSync(WDPBRec *pb);
OSErr  PBCloseWDSync(WDPBRec *pb);
short  OpenRFPerm(ConstStr255Param name, short vref, SignedByte perm);
void   CloseResFile(short ref);
short  Count1Resources(OSType type);
Handle Get1IndResource(OSType type, short index);
Handle Get1Resource(OSType type, short id);
void   ReleaseResource(Handle h);
void   HLock(Handle h);
Size   GetHandleSize(Handle h);

#endif /* MAC_MOCKS_H */
