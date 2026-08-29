/* macmime.c — make a MIME message ON a Macintosh, with the Macintosh
 * code that invented the format.
 *
 * WHY THIS EXISTS. Every message `src/fmt_mime.c` is graded against was
 * built by `tools/run_mime.py` on Linux or read by munpack on Linux
 * (TESTING.md, *base64 and MIME*). What none of them can settle is the
 * half no Unix tool has: how a real Macintosh laid out the
 * `application/applefile` part of a `multipart/appledouble`, and what it
 * put in the Finder-info entry. That was filed in OPEN_ITEMS.md as
 * waiting for a specimen somebody else would have to send.
 *
 * It does not have to be waited for. mpack's own Macintosh port is in
 * `reference/mpack` — README.mac, macfile.c, the lot — and
 * `encode_applefile()` there is the writer in question. This tool
 * compiles that function and `encode()` VERBATIM out of the reference
 * tree, adds the twenty lines of host glue THINK C used to provide, and
 * runs the result on an emulated Mac Plus. What comes off the disk is a
 * message a Macintosh wrote, with a real resource fork and real Finder
 * info in it, produced by the program `src/fmt_mime.c` is transcribed
 * from.
 *
 * WHAT IS OURS AND WHAT IS THEIRS. Everything that decides a byte of the
 * message is mpack's: encode.c, macfile.c, codes.c (base64 and MD5),
 * magic.c, md5c.c, xmalloc.c, all compiled unmodified. Ours is this
 * file — the Toolbox glue, the fork copies, and the two `os_` entry
 * points macos.c would otherwise supply. Where that boundary moved a
 * byte, this file says so:
 *
 *   * `os_genid()` — macos.c builds the id from TickCount(),
 *     GetDateTime() and the host name out of the application's prefs.
 *     There are no prefs here, so the host is a constant. The id
 *     appears in Message-ID and in no MIME structure.
 *   * Every FILE * mpack touches is one this file made with `funopen()`
 *     over hand-filled, fully-zeroed File Manager param blocks. macos.c
 *     did the same job by reaching into THINK C's FILE internals
 *     (`__getfile`, `fp->refnum`); Retro68's newlib has no equivalent,
 *     and its own file I/O cannot be used here at all — MEASURED: a
 *     bare `open("Probe1.tmp", O_WRONLY|O_CREAT|O_TRUNC)` on System
 *     6.0.8 never returns, photographed twice 40 s apart. Which of the
 *     HCreate, HOpenDF or HOpen inside `_open_r` (Retro68
 *     libretro/syscalls.c) is responsible is NOT established, so that
 *     is a symptom and not an attribution. The forks mpack reads are
 *     therefore the live ones, which is what Macopen gave it too.
 *   * Line endings are newlib's, not THINK C's. encode.c writes "\n"
 *     and THINK C's text mode turned that into CR on the way to disk;
 *     newlib does not. The harness MEASURES what came out rather than
 *     assuming either (tools/vmac/macmime.py --check).
 *
 * A HARNESS TOOL, not part of the shipping application. `ci.sh` never
 * builds it. The engine's 68000 discipline does not govern reference
 * code compiled for one specimen — mpack recurses nowhere, but it does
 * call malloc and it does use libc, both of which the engine forbids
 * itself and neither of which matters in a program that runs once.
 *
 * Subject file, output and log all live in the folder it is launched
 * from, and no name is ever typed at it.
 */
#include <Devices.h>
#include <Dialogs.h>
#include <Events.h>
#include <Files.h>
#include <Fonts.h>
#include <Memory.h>
#include <OSUtils.h>
#include <Quickdraw.h>
#include <TextUtils.h>
#include <Windows.h>

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* mpack's own, out of reference/mpack */
extern int encode_applefile(FILE *outfile, HFileInfo *fpb,
                            FILE *rfork, FILE *dfork);
extern int encode(FILE *infile, FILE *applefile, char *fname,
                  FILE *descfile, char *subject, char *headers,
                  long int maxsize, char *typeoverride, char *outfname);

/* The Finder flags the subject is given on the Mac. hasBeenInited, the
 * everyday one; nothing here runs the Finder, so nothing clears it.
 * tools/vmac/macmime.py expects this exact value. */
#define kSubjectFlags 0x0100

/* the two globals macfile.c's header declares */
char copy_buf[1024];
Cursor watch;
short didchat;

/* ---------------------------------------------------------------- */
/* the host glue macos.c would supply                                */

/* Source: reference/mpack/macos.c, os_createnewfile() — `fopen(fname,
 * "w")` there. It cannot be that here (newlib's file I/O hangs on
 * System 6), so it is the same thing through the File Manager:
 * create-and-truncate, in the folder the application was launched
 * from. */
static short gVol;                     /* set once, in main() */
static FILE *macfopen(short vol, long dir, ConstStr255Param name,
                      int write, int rsrc);
static void c2p(const char *s, Str255 out);

FILE *os_createnewfile(char *fname)
{
    Str255 p;
    c2p(fname, p);
    return macfopen(gVol, 0L, p, 1, 0);
}

/* Source: reference/mpack/macos.c, os_genid() — TickCount() and
 * GetDateTime(), joined to a host name. macos.c reads the host out of
 * `(*mpack_prefs)->internet_host`; this tool has no preferences file,
 * so the host is a constant. */
char *os_genid(void)
{
    static char result[64];
    unsigned long tick, when;

    tick = TickCount();
    GetDateTime(&when);
    sprintf(result, "%lu.%lu@macmime.local", tick, when);
    while (tick == (unsigned long)TickCount())
        ;
    return result;
}

void os_perror(char *str)
{
    (void)str;
}

/* Retro68 DECLARES GetTime and ships no implementation of it — it is
 * glue in InterfaceLib rather than a trap. Source: Inside Macintosh:
 * Operating System Utilities — GetTime returns the date and time held in
 * the low-memory global Time, converted by SecondsToDate. Both halves
 * are in Retro68's own header: LMGetTime() is 0x020C and SecondsToDate
 * is trap 0xA9C6 (Multiverse.h). macfile.c uses the result for the
 * applefile's `access` date and nothing else. */
pascal void GetTime(DateTimeRec *d)
{
    SecondsToDate(LMGetTime(), d);
}

/* `decode_applefile()` is compiled because it shares macfile.c with the
 * encoder, and it is never called: this tool only writes. These are the
 * two application entry points it would reach for. If a run ever lands
 * in one of them, that is a bug in this file and not a quiet fallback. */
void NAputFile(void) { }
void statrefresh(void) { }

/* ---------------------------------------------------------------- */
/* the window, so a screenshot of a run that stops says where         */

static WindowPtr gWin;
static short gLine;

static void say(const char *s)
{
    Str255 p;
    short n = 0;
    while (s[n] && n < 254) { p[n + 1] = (unsigned char)s[n]; n++; }
    p[0] = (unsigned char)n;
    if (gWin) {
        SetPort(gWin);
        MoveTo(8, 16 + gLine * 12);
        DrawString(p);
    }
    gLine++;
}

static void sayNum(const char *s, long v)
{
    char buf[128];
    sprintf(buf, "%s%ld", s, v);
    say(buf);
}

/* ---------------------------------------------------------------- */

/* ---------------------------------------------------------------- */
/* FILE * over the File Manager                                       */
/*                                                                    */
/* Retro68's newlib cannot open a file on System 6.0.8 (see the top of */
/* this file), and mpack speaks nothing but FILE *. newlib's funopen() */
/* bridges the two: it makes a FILE * out of four callbacks, so every  */
/* byte mpack reads or writes goes through the same fully-zeroed HFS   */
/* param blocks the shipping application uses.                        */

typedef struct MacF {
    short ref;
} MacF;

static int mf_read(void *c, char *buf, int n)
{
    long count = n;
    OSErr err = FSRead(((MacF *)c)->ref, &count, buf);
    if (err != noErr && err != eofErr) return -1;
    return (int)count;                 /* 0 at end of file, which is EOF */
}

static int mf_write(void *c, const char *buf, int n)
{
    long count = n;
    OSErr err = FSWrite(((MacF *)c)->ref, &count, (Ptr)buf);
    if (err != noErr) return -1;
    return (int)count;
}

static fpos_t mf_seek(void *c, fpos_t off, int whence)
{
    short ref = ((MacF *)c)->ref;
    long pos = 0, eof = 0;

    if (whence == SEEK_SET) {
        pos = (long)off;
    } else if (whence == SEEK_CUR) {
        if (GetFPos(ref, &pos) != noErr) return -1;
        pos += (long)off;
    } else {
        if (GetEOF(ref, &eof) != noErr) return -1;
        pos = eof + (long)off;
    }
    if (SetFPos(ref, fsFromStart, pos) != noErr) return -1;
    return (fpos_t)pos;
}

static int mf_close(void *c)
{
    short ref = ((MacF *)c)->ref;
    short vref = 0;
    GetVRefNum(ref, &vref);
    FSClose(ref);
    FlushVol(0L, vref);                /* commit: the host reads the image */
    free(c);
    return 0;
}

/* Open one fork of `name` and wrap it in a FILE *.
 *   write != 0 — the file is deleted and re-created first
 *   rsrc  != 0 — the resource fork rather than the data fork
 * The param blocks are zeroed whole before use, which is the one thing
 * that made the File Manager behave for this project's application
 * (BLOCKERS.md, *the fix that unblocked M10*). */
static FILE *macfopen(short vol, long dir, ConstStr255Param name,
                      int write, int rsrc)
{
    HParamBlockRec pb;
    MacF *c;
    FILE *f;
    OSErr err;
    long z;

    if (write) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.fileParam.ioNamePtr = (StringPtr)name;
        pb.fileParam.ioVRefNum = vol;
        pb.fileParam.ioDirID = dir;
        PBHDeleteSync(&pb);            /* may fail: it need not exist yet */

        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.fileParam.ioNamePtr = (StringPtr)name;
        pb.fileParam.ioVRefNum = vol;
        pb.fileParam.ioDirID = dir;
        err = PBHCreateSync(&pb);
        if (err != noErr && err != dupFNErr) {
            sayNum("create err ", err);
            return NULL;
        }
    }

    for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
    pb.ioParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioVRefNum = vol;
    pb.ioParam.ioPermssn = write ? fsRdWrPerm : fsRdPerm;
    pb.fileParam.ioDirID = dir;
    err = rsrc ? PBHOpenRFSync(&pb) : PBHOpenSync(&pb);
    if (err != noErr) { sayNum("open err ", err); return NULL; }

    c = (MacF *)malloc(sizeof *c);
    if (!c) { FSClose(pb.ioParam.ioRefNum); say("out of memory"); return NULL; }
    c->ref = pb.ioParam.ioRefNum;
    if (write) SetEOF(c->ref, 0L);

    f = funopen((void *)c, mf_read, mf_write, mf_seek, mf_close);
    if (!f) { FSClose(c->ref); free(c); say("funopen failed"); return NULL; }
    return f;
}

/* The name mpack hands os_createnewfile() is a C string; everything in
 * this run is at the top of one folder, so it becomes a Pascal string
 * and nothing else. */
static void c2p(const char *s, Str255 out)
{
    short n = 0;
    while (s[n] && n < 255) { out[n + 1] = (unsigned char)s[n]; n++; }
    out[0] = (unsigned char)n;
}

int main(void)
{
    CInfoPBRec ci;
    HFileInfo *fpb = (HFileInfo *)&ci;
    Str255 subjName = "\007Subject";
    Str255 tmpName  = "\011Apple.tmp";
    FILE *rfork, *dfork, *applefile;
    OSErr err;
    long z;
    Rect r;

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(0L);
    InitCursor();

    SetRect(&r, 20, 50, 480, 300);
    gWin = NewWindow(0L, &r, "\007macmime", true, documentProc,
                     (WindowPtr)-1L, false, 0L);
    SetPort(gWin);
    TextFont(4);          /* Monaco */
    TextSize(9);
    say("macmime: mpack's Macintosh encoder");

    err = GetVol(0L, &gVol);
    if (err != noErr) { sayNum("GetVol err ", err); goto done; }
    sayNum("volume ", gVol);

    /* Catalogue info for the subject: this record is where every field of
     * the applefile's name, Finder-info and dates entries comes from. */
    for (z = 0; z < (long)sizeof ci; z++) ((char *)&ci)[z] = 0;
    fpb->ioVRefNum = gVol;
    fpb->ioNamePtr = subjName;
    fpb->ioDirID = 0;
    fpb->ioFDirIndex = 0;
    err = PBGetCatInfoSync(&ci);
    if (err != noErr) { sayNum("PBGetCatInfo err ", err); goto done; }
    sayNum("data fork bytes ", fpb->ioFlLgLen);
    sayNum("rsrc fork bytes ", fpb->ioFlRLgLen);

    /* Give the subject a Finder flag, HERE, so the Finder-info entry has
     * something in it that a reader can be wrong about. It cannot be done
     * on the host: hfsutils' `hcopy -m` does not carry the flags onto the
     * volume — measured off-Mac, a MacBinary whose byte 73 is 0x01 comes
     * back out of the image as 0x00 — so a run that trusted the transfer
     * was grading the applefile against a word that was zero before the
     * Macintosh ever saw the file. Set it with the File Manager and read
     * the catalogue AGAIN, so what reaches mpack is what the volume holds
     * and not what this file wanted it to hold. */
    {
        HParamBlockRec fi;
        for (z = 0; z < (long)sizeof fi; z++) ((char *)&fi)[z] = 0;
        fi.fileParam.ioNamePtr = subjName;
        fi.fileParam.ioVRefNum = gVol;
        fi.fileParam.ioDirID = 0;
        fi.fileParam.ioFlFndrInfo = fpb->ioFlFndrInfo;
        fi.fileParam.ioFlFndrInfo.fdFlags = kSubjectFlags;
        err = PBHSetFInfoSync(&fi);
        if (err != noErr) { sayNum("SetFInfo err ", err); goto done; }

        for (z = 0; z < (long)sizeof ci; z++) ((char *)&ci)[z] = 0;
        fpb->ioVRefNum = gVol;
        fpb->ioNamePtr = subjName;
        fpb->ioDirID = 0;
        fpb->ioFDirIndex = 0;
        err = PBGetCatInfoSync(&ci);
        if (err != noErr) { sayNum("re-read err ", err); goto done; }
        sayNum("finder flags ", fpb->ioFlFndrInfo.fdFlags);
    }

    rfork = macfopen(gVol, 0L, subjName, 0, 1);
    if (!rfork) goto done;
    dfork = macfopen(gVol, 0L, subjName, 0, 0);
    if (!dfork) goto done;
    say("both forks open");

    /* AppleDOUBLE: the data fork travels as its own part, so
     * encode_applefile() gets a null dfork and writes magic 00051607.
     * That is the shape the open item is about. */
    applefile = macfopen(gVol, 0L, tmpName, 1, 0);
    if (!applefile) goto done;
    if (encode_applefile(applefile, fpb, rfork, (FILE *)0) < 0) {
        say("encode_applefile FAILED");
        goto done;
    }
    fflush(applefile);
    rewind(applefile);
    say("applefile written");

    if (encode(dfork, applefile, "Subject", (FILE *)0,
               "A message written on a Macintosh", (char *)0,
               0L, (char *)0, "Out.mime") != 0) {
        say("encode FAILED");
        goto done;
    }
    /* Commit before the host reads the volume off the image. Twice, the
     * way the shipping application does it (mac/macextract_mac.c): the
     * emulator's write-back lands on a flush, and a run killed without
     * one has written nothing the host can see. */
    FlushVol(0L, gVol);
    FlushVol(0L, gVol);
    say("Out.mime written");
    say("DONE");

done:
    /* Leave the window up: the harness photographs it, and the frame is
     * the only report a run that died before writing a file can give. */
    for (z = 0; z < 200000L; z++) {
        EventRecord ev;
        WaitNextEvent(everyEvent, &ev, 10L, 0L);
    }
    return 0;
}
