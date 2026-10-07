/*
 * depthtest — how deep classic System software will actually nest folders.
 *
 * `UNC_PATH_MAXDEPTH` is 24 and the engine refuses to descend past it. That
 * number was chosen, not derived: three formats "chose 24 independently"
 * (src/unc_internal.h) and nothing had ever asked what the destination
 * allows. The HFS VOLUME FORMAT allows at least 89 levels, measured with
 * hfsutils on Linux — but hfsutils is not a Macintosh, and the question
 * that decides whether a depth limit should exist at all is what the File
 * Manager does.
 *
 * Two numbers, because there are two different routes to a file and only
 * one of them has a string in it:
 *
 *   BY DIR ID   PBDirCreateSync with a parent dirID per level, which is what
 *               `mac/macextract_mac.c`'s EnsureDir does. No pathname is ever
 *               built, so if there is a depth limit it is the File Manager's
 *               own.
 *   BY PATHNAME PBGetCatInfo handed a full "Volume:a:b:c" string, which is a
 *               Str255 and therefore cannot exceed 255 bytes by construction.
 *               Where this stops is a LENGTH limit wearing a depth costume.
 *
 * It writes to the boot volume, so run it on a disk image that can be
 * thrown away. Put it on as `Finder` and never return: when a shell quits
 * the System repaints the desktop over the numbers (tools/vmac/memtest has
 * the same note and the same reason).
 *
 * Built by hand, not by ci.sh — see tools/vmac/README.md.
 */
#include <Quickdraw.h>
#include <Fonts.h>
#include <Windows.h>
#include <OSUtils.h>
#include <Files.h>

QDGlobals qd;

static short gLine;

static void Say(const unsigned char *label, long value)
{
    Str255 s;
    MoveTo(12, (short)(30 + gLine * 16));
    DrawString(label);
    NumToString(value, s);
    DrawString(s);
    gLine++;
}

/* The same call `EnsureDir` makes, with the same parameter block. */
static OSErr MakeDir(short vRefNum, long parent, StringPtr name, long *created)
{
    HParamBlockRec pb;
    OSErr err;
    pb.fileParam.ioCompletion = NULL;
    pb.fileParam.ioNamePtr = name;
    pb.fileParam.ioVRefNum = vRefNum;
    pb.fileParam.ioDirID = parent;
    err = PBDirCreateSync(&pb);
    *created = pb.fileParam.ioDirID;
    return err;
}

/* Is this directory reachable by its dirID alone? */
static OSErr StatDir(short vRefNum, long dirID)
{
    CInfoPBRec pb;
    Str255 nm;
    nm[0] = 0;
    pb.dirInfo.ioCompletion = NULL;
    pb.dirInfo.ioNamePtr = nm;
    pb.dirInfo.ioVRefNum = vRefNum;
    pb.dirInfo.ioDrDirID = dirID;
    pb.dirInfo.ioFDirIndex = -1;          /* by dirID, not by name */
    return PBGetCatInfoSync(&pb);
}

/* ...and by a full pathname? `path` is "Volume:D001:D002:...:" */
static OSErr StatPath(StringPtr path)
{
    CInfoPBRec pb;
    pb.dirInfo.ioCompletion = NULL;
    pb.dirInfo.ioNamePtr = path;
    pb.dirInfo.ioVRefNum = 0;
    pb.dirInfo.ioDrDirID = 0;
    pb.dirInfo.ioFDirIndex = 0;           /* by name */
    return PBGetCatInfoSync(&pb);
}

#define LIMIT 250

int main(void)
{
    Str255 name, path, volname;
    long parent, created, rootID = 2L;    /* fsRtDirID */
    short vRefNum = 0;                    /* the default (boot) volume */
    int level, deepestMade = 0, deepestStat = 0, deepestPath = 0;
    OSErr err = noErr, makeErr = noErr, pathErr = noErr;
    long madeID[LIMIT + 1];
    HParamBlockRec vpb;

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    FillRect(&qd.screenBits.bounds, &qd.white);

    /* The boot volume's name, which a full pathname has to start with. */
    volname[0] = 0;
    vpb.volumeParam.ioCompletion = NULL;
    vpb.volumeParam.ioNamePtr = volname;
    vpb.volumeParam.ioVRefNum = 0;
    vpb.volumeParam.ioVolIndex = 0;
    (void)PBHGetVInfoSync(&vpb);

    /* 1. Create, by dirID, until the File Manager says no. */
    parent = rootID;
    madeID[0] = rootID;
    for (level = 1; level <= LIMIT; level++) {
        name[0] = 4;
        name[1] = (unsigned char)('0' + (level / 100) % 10);
        name[2] = (unsigned char)('0' + (level / 10) % 10);
        name[3] = (unsigned char)('0' + level % 10);
        name[4] = 'd';
        makeErr = MakeDir(vRefNum, parent, name, &created);
        if (makeErr != noErr) break;
        madeID[level] = created;
        parent = created;
        deepestMade = level;
    }

    /* 2. Read the deepest one back by dirID, which uses no string. */
    if (deepestMade > 0) {
        err = StatDir(vRefNum, madeID[deepestMade]);
        if (err == noErr) deepestStat = deepestMade;
    }

    /* 3. And by a full PATHNAME, which is a Str255 and so must stop
     *    somewhere near 255 bytes however shallow the tree is. */
    path[0] = volname[0];
    BlockMoveData(volname + 1, path + 1, volname[0]);
    for (level = 1; level <= deepestMade; level++) {
        unsigned char n = path[0];
        if ((int)n + 5 > 255) break;      /* a Str255 cannot say more */
        path[n + 1] = ':';
        path[n + 2] = (unsigned char)('0' + (level / 100) % 10);
        path[n + 3] = (unsigned char)('0' + (level / 10) % 10);
        path[n + 4] = (unsigned char)('0' + level % 10);
        path[n + 5] = 'd';
        path[0] = (unsigned char)(n + 5);
        pathErr = StatPath(path);
        if (pathErr != noErr) break;
        deepestPath = level;
    }

    Say("\pdeepest CREATED by dirID   ", (long)deepestMade);
    Say("\p  and the error that ended it ", (long)makeErr);
    Say("\pdeepest READ BACK by dirID ", (long)deepestStat);
    Say("\pdeepest READ BY PATHNAME   ", (long)deepestPath);
    Say("\p  and the error that ended it ", (long)pathErr);
    Say("\p  that pathname's length   ", (long)path[0]);
    Say("\pUNC_PATH_MAXDEPTH is       ", 24L);

    for (;;) SystemTask();
    return 0;
}
