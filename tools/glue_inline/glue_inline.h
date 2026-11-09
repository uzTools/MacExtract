/* glue_inline.h — multiversal's hand-written File Manager glue as gnu_inline
 * definitions, for measuring what inline glue would cost MacExtract. Not
 * built by default (tools/glue_inline/README.md).
 *
 * Source: multiversal custom/glue.c, unchanged since d7642c2 (read at
 * 580f330 in /opt/Retro68/multiversal): HOpenRF, HOpen, HDelete, FSClose,
 * FlushVol, FSRead, FSWrite, GetEOF, SetEOF, SetFPos, each body statement
 * for statement; checked against the disassembly of glue.o in the
 * toolchain's libInterface.a (same traps, same parameter-block offsets).
 * The wrapper is the one multiversal f619744 (pull request 20,
 * cincludes.rb) generates for traps with register outputs:
 * `__gnu_inline__ extern __inline__ pascal` under TARGET_CPU_68K, so a call
 * is expanded and an address-taken use still links the library copy.
 * That multiversal would emit these bodies the same way is a hypothesis:
 * its generator has no path for custom/glue.c today.
 *
 * Include after <Files.h>. GLUE_INLINE_HFS selects the first three,
 * GLUE_INLINE_IO the other seven. */
#ifndef GLUE_INLINE_H
#define GLUE_INLINE_H

#include <Files.h>

#if TARGET_CPU_68K
#define GLUE_INLINE_ __attribute__((__gnu_inline__)) extern __inline__ pascal

#ifdef GLUE_INLINE_HFS
GLUE_INLINE_ OSErr HOpenRF(INTEGER vref, LONGINT dirid, ConstStringPtr name,
                           SignedByte perm, INTEGER *refp)
{
    HParamBlockRec pb;
    pb.fileParam.ioVRefNum = vref;
    pb.fileParam.ioDirID = dirid;
    pb.fileParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioPermssn = perm;
    pb.ioParam.ioMisc = NULL;
    pb.fileParam.ioFVersNum = 0;
    OSErr err = PBHOpenRFSync(&pb);
    *refp = pb.ioParam.ioRefNum;
    return err;
}

GLUE_INLINE_ OSErr HOpen(INTEGER vref, LONGINT dirid, ConstStringPtr name,
                         SignedByte perm, INTEGER *refp)
{
    HParamBlockRec pb;
    pb.fileParam.ioVRefNum = vref;
    pb.fileParam.ioDirID = dirid;
    pb.fileParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioPermssn = perm;
    pb.ioParam.ioMisc = NULL;
    pb.fileParam.ioFVersNum = 0;
    OSErr err = PBHOpenSync(&pb);
    *refp = pb.ioParam.ioRefNum;
    return err;
}

GLUE_INLINE_ OSErr HDelete(short vRefNum, long dirID, ConstStr255Param fileName)
{
    HParamBlockRec pb;
    pb.fileParam.ioVRefNum = vRefNum;
    pb.fileParam.ioNamePtr = (StringPtr)fileName;
    pb.fileParam.ioDirID = dirID;
    pb.fileParam.ioFVersNum = 0;
    return PBHDeleteSync(&pb);
}
#endif /* GLUE_INLINE_HFS */

#ifdef GLUE_INLINE_IO
GLUE_INLINE_ OSErr FSClose(short refNum)
{
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    return PBCloseSync(&pb);
}

GLUE_INLINE_ OSErr FlushVol(ConstStr63Param volName, short vRefNum)
{
    ParamBlockRec pb;
    pb.fileParam.ioNamePtr = (StringPtr)volName;
    pb.fileParam.ioVRefNum = vRefNum;
    return PBFlushVolSync(&pb);
}

GLUE_INLINE_ OSErr FSRead(short refNum, long *count, void *buffPtr)
{
    OSErr err;
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    pb.ioParam.ioBuffer = buffPtr;
    pb.ioParam.ioReqCount = *count;
    pb.ioParam.ioPosMode = fsAtMark;
    err = PBReadSync(&pb);
    *count = pb.ioParam.ioActCount;
    return err;
}

GLUE_INLINE_ OSErr FSWrite(short refNum, long *count, const void *buffPtr)
{
    OSErr err;
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    pb.ioParam.ioBuffer = (void *)buffPtr;
    pb.ioParam.ioReqCount = *count;
    pb.ioParam.ioPosMode = fsAtMark;
    err = PBWriteSync(&pb);
    *count = pb.ioParam.ioActCount;
    return err;
}

GLUE_INLINE_ OSErr GetEOF(short refNum, long *logEOF)
{
    OSErr err;
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    err = PBGetEOFSync(&pb);
    *logEOF = (long)pb.ioParam.ioMisc;
    return err;
}

GLUE_INLINE_ OSErr SetEOF(short refNum, long logEOF)
{
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    pb.ioParam.ioMisc = (Ptr)logEOF;
    return PBSetEOFSync(&pb);
}

GLUE_INLINE_ OSErr SetFPos(short refNum, short posMode, long posOff)
{
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    pb.ioParam.ioPosMode = posMode;
    pb.ioParam.ioPosOffset = posOff;
    return PBSetFPosSync(&pb);
}
#endif /* GLUE_INLINE_IO */

#undef GLUE_INLINE_
#endif /* TARGET_CPU_68K */
#endif /* GLUE_INLINE_H */
