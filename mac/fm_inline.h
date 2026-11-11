/*
 * fm_inline.h — the seven File Manager calls the application makes
 * through high-level glue (FSRead, FSWrite, SetFPos, GetEOF, SetEOF,
 * FlushVol, FSClose), expanded at each call instead of linked from
 * Retro68's libInterface. Each is the parameter-block trap the library's
 * copy calls, so the behaviour is the library's; only the call is gone.
 * Included by macextract_mac.c and by the setup image
 * (tools/overlay/ovl_segsetup.c), which therefore calls them itself
 * rather than through SegSetupFns. Measured: DECISIONS.md 2026-11-09, *the
 * glue that was measured inline*, and 2026-11-11, *the glue the shell
 * expands*.
 *
 * Source: multiversal custom/glue.c (unchanged since d7642c2, read at
 * 580f330 in /opt/Retro68/multiversal), statement for statement, checked
 * against the disassembly of glue.o in the toolchain's libInterface.a:
 * the same traps and the same parameter-block fields. Field layout:
 * multiversal's ParamBlockRec, the same offsets as SUMacC's IOParam
 * (reference/sumacc/h/osintf.h, which also names ioMisc as _GetEOF's and
 * _SetEOF's logical end of file): ioNamePtr 18, ioVRefNum 22, ioRefNum 24,
 * ioMisc 28, ioBuffer 32, ioReqCount 36, ioActCount 40, ioPosMode 44,
 * ioPosOffset 46, offsetof on the toolchain's header. No routine clears
 * its block: each trap reads only the fields set here, as the library's
 * copies rely on.
 *
 * `gnu_inline` (the wrapper multiversal f619744 generates for traps with
 * register outputs) keeps the library's prototypes, so a call GCC chose
 * not to expand, or a pointer taken to one, would link the library copy
 * and nothing would fail; tools/build_mac.sh fails the build if any of
 * the seven is linked. Not in the Linux sink tests, whose mocks
 * (mac/mac_mocks.h) stand in for the same seven.
 *
 * SPDX-License-Identifier: 0BSD
 */
#ifndef UNC_FM_INLINE_H
#define UNC_FM_INLINE_H

#include <Files.h>

#if TARGET_CPU_68K
#define FM_INLINE_ __attribute__((__gnu_inline__)) extern __inline__ pascal

FM_INLINE_ OSErr FSClose(short refNum)
{
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    return PBCloseSync(&pb);
}

FM_INLINE_ OSErr FlushVol(ConstStr63Param volName, short vRefNum)
{
    ParamBlockRec pb;
    pb.fileParam.ioNamePtr = (StringPtr)volName;
    pb.fileParam.ioVRefNum = vRefNum;
    return PBFlushVolSync(&pb);
}

FM_INLINE_ OSErr FSRead(short refNum, long *count, void *buffPtr)
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

FM_INLINE_ OSErr FSWrite(short refNum, long *count, const void *buffPtr)
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

FM_INLINE_ OSErr GetEOF(short refNum, long *logEOF)
{
    OSErr err;
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    err = PBGetEOFSync(&pb);
    *logEOF = (long)pb.ioParam.ioMisc;
    return err;
}

FM_INLINE_ OSErr SetEOF(short refNum, long logEOF)
{
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    pb.ioParam.ioMisc = (Ptr)logEOF;
    return PBSetEOFSync(&pb);
}

FM_INLINE_ OSErr SetFPos(short refNum, short posMode, long posOff)
{
    ParamBlockRec pb;
    pb.ioParam.ioRefNum = refNum;
    pb.ioParam.ioPosMode = posMode;
    pb.ioParam.ioPosOffset = posOff;
    return PBSetFPosSync(&pb);
}

#undef FM_INLINE_
#endif /* TARGET_CPU_68K */
#endif /* UNC_FM_INLINE_H */
