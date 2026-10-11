/* aesit.c — ask StuffIt Deluxe for the one archive this project cannot
 * otherwise get: a StuffIt 5 archive that is ENCRYPTED and carries an
 * ARCHIVE COMMENT.
 *
 * WHY THIS EXISTS. `src/fmt_sit5.c` reads bit 5 of the archive flag byte
 * (header byte 83) as "a comment block is present", which moves the
 * password hash four bytes along inside the `SIT5_ARCH_CRYPTED` branch.
 * What bit 5 MEANS is measured off an archive StuffIt Deluxe 5.5 ships;
 * where the hash then goes needs an archive setting bits 5 AND 7, and
 * nothing anywhere here had one. Two of them came out of this, on
 * 2026-10-06 (FORMATS.md, *StuffIt 5's archive flag byte, and what bit 5
 * is*; tools/derive_sit5crypt.py grades them).
 *
 * WHY BY APPLE EVENT. `Edit Comment…` has no Command key in any box that
 * runs here, and a keyless menu item is not selectable on either guest
 * (tools/vmac/README.md, *What the pointer cannot select*). StuffIt
 * Deluxe 7.0.3's 'aete' declares `comment` and `password` as settable
 * properties of its `archive` class, so the specimen is two events and
 * no coordinates. The dictionary is printed by
 * `tools/vmac/sitcomment.py --aete`.
 *
 * WHAT WORKED, which is not what was tried first: `make new archive`
 * refuses every shape of `at` this has built (-1701), so nothing here
 * CREATES an archive. It opens one that is already on the volume and
 * changes it — a comment onto an encrypted archive, a password and an
 * item onto a commented one — and both ways land at 0xb0.
 *
 * WHAT IT DOES NOT KNOW. An 'aete' says what a term MEANS, not what the
 * handler will coerce — aetran.c learned that the expensive way — so
 * every reply's 'errn' is written to a file beside the application after
 * each step, and a run that produces no archive still reports which step
 * refused and with what error. And an 'errn' of 0 says the term was
 * understood, not that anything was written: this reads byte 83 back off
 * the archive itself and prints it, which is the only output of the run
 * that is about the FORMAT.
 *
 * This is a HARNESS tool. It is never built by ci.sh, it is System 7 and
 * later only, and the 68000 discipline the engine follows does not apply
 * to it beyond compiling for -mcpu=68000, which it does.
 */
#include <AppleEvents.h>
#include <Errors.h>
#include <Events.h>
#include <Files.h>
#include <Fonts.h>
#include <Memory.h>
#include <Processes.h>
#include <Quickdraw.h>
#include <TextUtils.h>
#include <Windows.h>

/* Everything the folder is expected to hold. The names are compiled in:
 * this runs with no dialog and no keyboard, so there is nothing for a
 * mistyped name to land in. MacRoman 0xAA is the trademark sign, part of
 * 5.5's real file name. */
static const unsigned char kApp703[]   = "\016StuffIt Deluxe";
static const unsigned char kApp55[]    = "\017StuffIt Deluxe\xAA";
/* The two archives the run works on, both written by Aladdin's own
 * software and both already on the volume. Phase 1 adds a password to an
 * archive that HAS a comment; phase 2 adds a comment to one that is
 * already encrypted. Either one produces the specimen, and they fail
 * independently. */
static const unsigned char kCommented[] = "\013Comment.sit";
static const unsigned char kEncrypted[] = "\015Encrypted.sit";
static const unsigned char kSubject[]   = "\007Subject";
static const unsigned char kLogName[]  = "\010AEResult";
static const char kPassword[] = "swordfish";       /* FORMATS.md names the
                                                    * three DropStuff
                                                    * passwords; this is one
                                                    * of them, so the hash
                                                    * is already derivable */
static const char kComment[]  = "MacExtract bit 5";

/* Constants Retro68's headers do not carry. Source: Inside Macintosh —
 * Interapplication Communication, *Resolving and Creating Object
 * Specifier Records* (the four keywords and the key forms) and the Apple
 * Event Registry (the Core suite's event IDs). */
#define launchNoFileFlags 0x0800
#ifndef typeNull
#define typeNull            'null'
#endif
#define typeEnumeratedX     'enum'
#define typeObjectSpecifier 'obj '
#define typeIntlTextX       'itxt'
#define keyAEDesiredClass   'want'
#define keyAEContainer      'from'
#define keyAEKeyForm        'form'
#define keyAEKeyData        'seld'
#define formAbsolutePosition 'indx'
#define formPropertyID      'prop'
#define cProperty           'prop'
#define keyAEData           'data'
#define keyAEObjectClass    'kocl'
#define keyAEInsertHere     'insh'
#define keyAEPropData       'prdt'
#define kAECoreSuite        'core'
#define kAESetData          'setd'
#define kAECreateElement    'crel'
#define kAESave             'save'
#define kAEClose            'clos'
#define kCoreEventClassX    'aevt'
#define kAEOpenDocumentsX   'odoc'
#define kAEQuitApplicationX 'quit'
#define keyErrNumber        'errn'
#ifndef typeWildCard
#define typeWildCard        '****'
#endif

/* AEPutKeyPtr and AEPutKeyDesc are the same Apple Event Manager selectors
 * as AEPutParamPtr and AEPutParamDesc — an AERecord is an AppleEvent —
 * and Apple's own header defines them as these macros. Retro68's does
 * not declare them at all. */
#define AEPutKeyPtr(r, k, t, p, s)  AEPutParamPtr((AppleEvent *)(r), k, t, p, s)
#define AEPutKeyDesc(r, k, d)       AEPutParamDesc((AppleEvent *)(r), k, d)

/* StuffIt Deluxe 7.0.3's own terms, read out of its 'aete'. */
#define kSITCreator  'SIT!'
#define cArchive703  'ARCH'
#define pComment703  'COMM'
#define pPassword703 'PASS'
#define kStuff703    'stff'
#define kStuffSuite  'STFF'
#define keyInto703   'dest'
#define keyPass703   'PASS'
#define keyFormat703 'eFRM'
#define kFormatSIT5  'SIT5'

/* And 5.5's, which differ in every code — the fallback if 7.0.3 is not
 * the box on the volume. */
#define cArchive55   'Arc '
#define pComment55   'comm'
#define pPassword55  'pass'
#define kStuff55     'STUF'
#define kSITSuite55  'SIT!'
#define keyInto55    'dest'
#define keyEncr55    'encr'

static WindowPtr gWin;
static short gLine;
static char gLog[4096];
static short gLogLen;
static FSSpec gFolder;              /* the folder this application is in */
static Boolean gIs703;

/* ---------------------------------------------------------------- */
/* Saying what happened, on the screen and in a file                 */
/* ---------------------------------------------------------------- */

static void logs(const char *s)
{
    unsigned char p[256];
    short n = 0;
    while (s[n] && n < 200) {
        p[n + 1] = (unsigned char)s[n];
        if (gLogLen < (short)sizeof(gLog) - 2)
            gLog[gLogLen++] = s[n];
        n++;
    }
    p[0] = (unsigned char)n;
    if (gLogLen < (short)sizeof(gLog) - 2)
        gLog[gLogLen++] = '\r';
    if (gWin) {
        SetPort(gWin);
        gLine += 11;
        if (gLine > 330) gLine = 11;
        MoveTo(6, gLine);
        DrawString(p);
    }
}

static void lognum(const char *label, long v)
{
    char buf[96];
    short i = 0, j;
    Str255 num;
    while (label[i] && i < 70) { buf[i] = label[i]; i++; }
    NumToString(v, num);
    for (j = 1; j <= num[0]; j++) buf[i++] = (char)num[j];
    buf[i] = 0;
    logs(buf);
}

/* The log file is the result of the run, and it is rewritten after every
 * step rather than once at the end: a step that blocks on a dialog in the
 * other application leaves everything before it readable. */
static void writelog(void)
{
    FSSpec spec;
    short ref;
    long count = gLogLen;
    spec = gFolder;
    BlockMoveData(kLogName, spec.name, kLogName[0] + 1);
    FSpDelete(&spec);
    if (FSpCreate(&spec, 'ttxt', 'TEXT', smSystemScript) != noErr) return;
    if (FSpOpenDF(&spec, fsWrPerm, &ref) != noErr) return;
    FSWrite(ref, &count, gLog);
    SetEOF(ref, gLogLen);
    FSClose(ref);
    FlushVol(NULL, gFolder.vRefNum);
}

static void step(const char *label, OSErr err)
{
    lognum(label, err);
    writelog();
}

/* ---------------------------------------------------------------- */
/* Waiting                                                           */
/* ---------------------------------------------------------------- */

static pascal Boolean AEIdle(EventRecord *ev, long *sleep, RgnHandle *rgn)
{
    (void)ev;
    *sleep = 6;
    *rgn = NULL;
    return false;
}

static void spin(long ticks)
{
    EventRecord ev;
    long stop = TickCount() + ticks;
    while (TickCount() < stop)
        WaitNextEvent(everyEvent, &ev, 6, NULL);
}

/* ---------------------------------------------------------------- */
/* Object specifiers                                                 */
/* ---------------------------------------------------------------- */

/* desiredClass, container, keyForm, keyData -> one 'obj ' descriptor.
 * Source: Inside Macintosh — Interapplication Communication, *Creating
 * Object Specifier Records*: a record with those four keywords, coerced
 * to typeObjectSpecifier. */
static OSErr objSpec(DescType cls, AEDesc *container, DescType form,
                     AEDesc *key, AEDesc *out)
{
    AERecord rec;
    OSErr err = AECreateList(NULL, 0, true, &rec);
    if (err != noErr) return err;
    err = AEPutKeyPtr(&rec, keyAEDesiredClass, typeType, &cls, sizeof cls);
    if (err == noErr) err = AEPutKeyDesc(&rec, keyAEContainer, container);
    if (err == noErr)
        err = AEPutKeyPtr(&rec, keyAEKeyForm, typeEnumeratedX, &form,
                          sizeof form);
    if (err == noErr) err = AEPutKeyDesc(&rec, keyAEKeyData, key);
    if (err == noErr) err = AECoerceDesc(&rec, typeObjectSpecifier, out);
    AEDisposeDesc(&rec);
    return err;
}

/* `archive 1`, which is what every box here calls the frontmost one. */
static OSErr archiveByIndex(AEDesc *out)
{
    AEDesc null, key;
    long one = 1;
    OSErr err = AECreateDesc(typeNull, NULL, 0, &null);
    if (err != noErr) return err;
    err = AECreateDesc(typeSInt32, &one, sizeof one, &key);
    if (err == noErr) {
        err = objSpec(gIs703 ? cArchive703 : cArchive55, &null,
                      formAbsolutePosition, &key, out);
        AEDisposeDesc(&key);
    }
    AEDisposeDesc(&null);
    return err;
}

/* `<prop> of <archive>` */
static OSErr propOf(AEDesc *archive, DescType prop, AEDesc *out)
{
    AEDesc key;
    OSErr err = AECreateDesc(typeType, &prop, sizeof prop, &key);
    if (err != noErr) return err;
    err = objSpec(cProperty, archive, formPropertyID, &key, out);
    AEDisposeDesc(&key);
    return err;
}

static OSErr aliasDesc(FSSpec *spec, AEDesc *out)
{
    AliasHandle alias = NULL;
    OSErr err = NewAlias(NULL, spec, &alias);
    if (err != noErr) return err;
    HLock((Handle)alias);
    err = AECreateDesc(typeAlias, *alias, GetHandleSize((Handle)alias), out);
    HUnlock((Handle)alias);
    DisposeHandle((Handle)alias);
    return err;
}

/* ---------------------------------------------------------------- */
/* Finding, and if need be starting, StuffIt Deluxe                  */
/* ---------------------------------------------------------------- */

static Boolean findProcess(OSType creator, ProcessSerialNumber *psn)
{
    ProcessSerialNumber p;
    ProcessInfoRec info;
    Str255 name;
    FSSpec spec;
    p.highLongOfPSN = 0;
    p.lowLongOfPSN = kNoProcess;
    while (GetNextProcess(&p) == noErr) {
        info.processInfoLength = sizeof(info);
        info.processName = name;
        info.processAppSpec = &spec;
        if (GetProcessInformation(&p, &info) != noErr) continue;
        if (info.processSignature == creator) { *psn = p; return true; }
    }
    return false;
}

static OSErr launchApp(FSSpec *app, ProcessSerialNumber *psn)
{
    LaunchParamBlockRec pb;
    OSErr err;
    short tries;
    pb.reserved1 = 0;
    pb.reserved2 = 0;
    pb.launchBlockID = extendedBlock;
    pb.launchEPBLength = extendedBlockLen;
    pb.launchFileFlags = 0;
    pb.launchControlFlags = launchContinue | launchNoFileFlags;
    pb.launchAppSpec = app;
    pb.launchAppParameters = NULL;
    err = LaunchApplication(&pb);
    if (err != noErr) return err;
    *psn = pb.launchProcessSN;
    /* Launched is not ready: an event that arrives before the handlers
     * are installed comes back errAEEventNotHandled. These boxes are
     * large and this guest is slow, so the wait is generous. */
    for (tries = 0; tries < 120; tries++) {
        spin(30);
        if (findProcess(kSITCreator, psn)) return noErr;
    }
    return procNotFound;
}

/* ---------------------------------------------------------------- */
/* Sending                                                           */
/* ---------------------------------------------------------------- */

static ProcessSerialNumber gPSN;

/* One event, built by the caller through `fill`, sent, and the reply's
 * 'errn' returned — which is the only thing that says whether the OTHER
 * application liked the shape. A transport error is returned as itself. */
typedef OSErr (*FillProc)(AppleEvent *evt, void *ctx);

static long gTimeout = 3600L;          /* ticks; one minute by default */

static OSErr sendEvent(AEEventClass cls, AEEventID id, FillProc fill,
                       void *ctx, AEDesc *replyObj)
{
    AEAddressDesc target;
    AppleEvent evt, reply;
    OSErr err;
    DescType got;
    Size size;
    long code = 0;

    if (replyObj) { replyObj->descriptorType = typeNull;
                    replyObj->dataHandle = NULL; }
    err = AECreateDesc(typeProcessSerialNumber, &gPSN, sizeof gPSN, &target);
    if (err != noErr) return err;
    err = AECreateAppleEvent(cls, id, &target, kAutoGenerateReturnID,
                             kAnyTransactionID, &evt);
    AEDisposeDesc(&target);
    if (err != noErr) return err;
    if (fill) err = fill(&evt, ctx);
    if (err != noErr) { AEDisposeDesc(&evt); return err; }

    reply.descriptorType = typeNull;
    reply.dataHandle = NULL;
    /* Interaction is ALLOWED: a box that wants a dialog is a result
     * worth photographing, and refusing it would read as a refusal of
     * the shape. The cost is bounded by `gTimeout` rather than by the
     * Apple Event Manager's default, because eight events that each wait
     * out a stuck dialog is longer than the boot. */
    err = AESend(&evt, &reply, kAEWaitReply | kAECanInteract,
                 kAENormalPriority, gTimeout, (IdleUPP)AEIdle, NULL);
    AEDisposeDesc(&evt);
    if (err != noErr) { AEDisposeDesc(&reply); return err; }
    if (AEGetParamPtr(&reply, keyErrNumber, typeSInt32, &got,
                      (Ptr)&code, sizeof code, &size) == noErr && code)
        err = (OSErr)code;
    if (replyObj)
        AEGetParamDesc(&reply, keyDirectObject, typeWildCard, replyObj);
    AEDisposeDesc(&reply);
    return err;
}

/* ------------------------------------------------- the individual fills */

typedef struct {
    AEDesc *obj;                /* direct object, or NULL */
    AEDesc *data;               /* keyAEData, or NULL */
    AEKeyword k1; AEDesc *d1;   /* up to three more keyed parameters */
    AEKeyword k2; AEDesc *d2;
    AEKeyword k3; AEDesc *d3;
} Fill;

static OSErr fillGeneric(AppleEvent *evt, void *ctx)
{
    Fill *f = (Fill *)ctx;
    OSErr err = noErr;
    if (f->obj) err = AEPutParamDesc(evt, keyDirectObject, f->obj);
    if (err == noErr && f->data)
        err = AEPutParamDesc(evt, keyAEData, f->data);
    if (err == noErr && f->d1) err = AEPutParamDesc(evt, f->k1, f->d1);
    if (err == noErr && f->d2) err = AEPutParamDesc(evt, f->k2, f->d2);
    if (err == noErr && f->d3) err = AEPutParamDesc(evt, f->k3, f->d3);
    return err;
}

/* ---------------------------------------------------------------- */
/* The run                                                           */
/* ---------------------------------------------------------------- */

static OSErr ownFolder(FSSpec *out)
{
    ProcessSerialNumber me;
    ProcessInfoRec info;
    Str255 name;
    FSSpec spec;
    OSErr err;
    GetCurrentProcess(&me);
    info.processInfoLength = sizeof(info);
    info.processName = name;
    info.processAppSpec = &spec;
    err = GetProcessInformation(&me, &info);
    if (err != noErr) return err;
    *out = spec;
    return noErr;
}

/* A Pascal string literal's length byte is written by hand and nothing
 * checks it. `Encrypted.sit` shipped once as `\017` — fifteen, for
 * thirteen characters — and the only symptom was the file reading as
 * absent, which is also what a missing file looks like. */
static Boolean pstrOK(const unsigned char *name, short literal)
{
    if (name[0] == literal - 2) return true;
    lognum("BAD compiled-in name length, byte says ", name[0]);
    lognum("  literal is ", literal - 2);
    return false;
}


static Boolean exists(const unsigned char *name, FSSpec *out)
{
    FSSpec spec = gFolder;
    FInfo fi;
    BlockMoveData(name, spec.name, name[0] + 1);
    if (FSpGetFInfo(&spec, &fi) != noErr) return false;
    *out = spec;
    return true;
}

/* Setting one property of the archive, through both text types. An
 * 'itxt' carries a script and language code ahead of its bytes and a
 * 'TEXT' does not; which one a handler coerces is not in the 'aete'. */
static OSErr setProp(AEDesc *archive, DescType prop, const char *text,
                     const char *label)
{
    AEDesc target, data;
    OSErr err;
    Fill f;
    short n = 0;
    char itxt[128];
    while (text[n]) n++;
    data.descriptorType = typeNull;
    data.dataHandle = NULL;

    err = propOf(archive, prop, &target);
    if (err != noErr) { step(label, err); return err; }

    f.obj = &target; f.data = &data;
    f.d1 = f.d2 = f.d3 = NULL;

    err = AECreateDesc(typeChar, text, n, &data);
    if (err == noErr) {
        err = sendEvent(kAECoreSuite, kAESetData, fillGeneric, &f, NULL);
        AEDisposeDesc(&data);
    }
    step(label, err);
    if (err != noErr) {
        /* 'itxt': script code, language code, then the bytes. */
        itxt[0] = itxt[1] = 0; itxt[2] = 0; itxt[3] = 0;
        BlockMoveData(text, itxt + 4, n);
        if (AECreateDesc(typeIntlTextX, itxt, n + 4, &data) == noErr) {
            err = sendEvent(kAECoreSuite, kAESetData, fillGeneric, &f, NULL);
            AEDisposeDesc(&data);
        }
        step("  as itxt ", err);
    }
    AEDisposeDesc(&target);
    return err;
}

/* One archive, opened and worked on. `aevt/odoc` is the only way in:
 * 7.0.3's `make` wants an insertion location this harness has not built
 * (the first run's ladder: `make` answered errAEDescNotFound to every
 * shape of `at`), and an archive that is already on the volume needs no
 * `make` at all. */
static Boolean openArchive(FSSpec *spec, AEDesc *archive)
{
    AEDesc one, list;
    OSErr err;
    Fill f;

    archive->descriptorType = typeNull;
    archive->dataHandle = NULL;
    if (aliasDesc(spec, &one) != noErr) { logs("alias failed"); return false; }
    /* `odoc` takes a LIST of aliases, which is what the Finder sends and
     * what the Required Suite handler expects; the 'aete' calls the
     * direct parameter an object and means the list's members. */
    err = AECreateList(NULL, 0, false, &list);
    if (err == noErr) err = AEPutDesc(&list, 1, &one);
    AEDisposeDesc(&one);
    if (err != noErr) { lognum("list ", err); return false; }

    f.obj = &list; f.data = NULL;
    f.d1 = f.d2 = f.d3 = NULL;
    gTimeout = 18000L;
    err = sendEvent(kCoreEventClassX, kAEOpenDocumentsX, fillGeneric, &f,
                    archive);
    gTimeout = 3600L;
    step("open ", err);
    AEDisposeDesc(&list);
    if (err != noErr) return false;

    /* The reply may or may not be an object. `archive 1` is what every
     * box documents and what the first run's ladder built successfully,
     * so it is the fallback rather than the exception. */
    if (archive->descriptorType != typeObjectSpecifier) {
        AEDisposeDesc(archive);
        err = archiveByIndex(archive);
        step("archive 1 spec ", err);
        if (err != noErr) return false;
        logs("  using archive 1");
    } else {
        logs("  using the open reply's object");
    }
    return true;
}

/* The archive's own flag byte, read off the disk inside the guest. This
 * is the measurement the run exists for, and reading it here means a
 * screenshot says what happened without the volume having to come back:
 * byte 83 of a StuffIt 5 header is the archive-level flags. */
static void logFlags(const unsigned char *name)
{
    FSSpec spec;
    short ref;
    long count = 1;
    unsigned char b = 0;
    char msg[64];
    short i;
    if (!exists(name, &spec)) { logs("  (not there to read)"); return; }
    if (FSpOpenDF(&spec, fsRdPerm, &ref) != noErr) { logs("  no open"); return; }
    if (SetFPos(ref, fsFromStart, 83) == noErr) FSRead(ref, &count, &b);
    FSClose(ref);
    for (i = 0; i < name[0] && i < 30; i++) msg[i] = (char)name[1 + i];
    msg[i] = 0;
    lognum(msg, b);
}


static void finish(AEDesc *archive)
{
    Fill f;
    f.obj = archive; f.data = NULL;
    f.d1 = f.d2 = f.d3 = NULL;
    gTimeout = 18000L;
    /* `save` is in 7.0.3's own 'aedt' and answers errAEEventNotHandled
     * to an archive object (measured 2026-10-06), so `close` is what has
     * to write. */
    step("close ", sendEvent(kAECoreSuite, kAEClose, fillGeneric, &f, NULL));
    gTimeout = 3600L;
}

static void run(void)
{
    FSSpec appSpec, spec, subject;
    AEDesc archive;
    OSErr err;

    if (ownFolder(&gFolder) != noErr) { logs("no own FSSpec"); return; }

    pstrOK(kApp703, sizeof kApp703);
    pstrOK(kApp55, sizeof kApp55);
    pstrOK(kCommented, sizeof kCommented);
    pstrOK(kEncrypted, sizeof kEncrypted);
    pstrOK(kSubject, sizeof kSubject);
    pstrOK(kLogName, sizeof kLogName);

    if (exists(kApp703, &appSpec)) { gIs703 = true; logs("box: 7.0.3"); }
    else if (exists(kApp55, &appSpec)) { gIs703 = false; logs("box: 5.5"); }
    else { logs("no StuffIt Deluxe beside me"); writelog(); return; }

    if (findProcess(kSITCreator, &gPSN)) logs("already running");
    else {
        err = launchApp(&appSpec, &gPSN);
        step("launch ", err);
        if (err != noErr) return;
    }
    spin(600);              /* the splash, and 7.0.3's registration nag */

    /* ---- phase 1: an encrypted archive, given a comment. One event,
     * and the archive already carries everything else. ---- */
    if (exists(kEncrypted, &spec)) {
        logs("-- phase 1: Encrypted.sit + comment");
        if (openArchive(&spec, &archive)) {
            setProp(&archive, gIs703 ? pComment703 : pComment55,
                    kComment, "  set comment ");
            finish(&archive);
            AEDisposeDesc(&archive);
        }
        logFlags(kEncrypted);
    } else {
        logs("no Encrypted.sit");
    }

    /* ---- phase 2: a commented archive, given a password AND a new
     * item. The password alone was accepted and written nowhere on
     * 2026-10-06 — `set password` answered 0 and the file came back byte
     * for byte — so this one makes the archive be rewritten. ---- */
    if (exists(kCommented, &spec) && exists(kSubject, &subject)) {
        logs("-- phase 2: Comment.sit + password + an item");
        if (openArchive(&spec, &archive)) {
            setProp(&archive, gIs703 ? pPassword703 : pPassword55,
                    kPassword, "  set password ");
            {
                AEDesc subjAlias, pass;
                Boolean yes = true;
                Fill f;
                pass.descriptorType = typeNull;
                pass.dataHandle = NULL;
                if (aliasDesc(&subject, &subjAlias) == noErr) {
                    f.obj = &subjAlias; f.data = NULL;
                    f.k1 = gIs703 ? keyInto703 : keyInto55; f.d1 = &archive;
                    f.k2 = 0; f.d2 = NULL;
                    f.k3 = 0; f.d3 = NULL;
                    if (gIs703) {
                        if (AECreateDesc(typeChar, kPassword,
                                         (Size)sizeof kPassword - 1,
                                         &pass) == noErr) {
                            f.k2 = keyPass703; f.d2 = &pass;
                        }
                    } else if (AECreateDesc(typeBoolean, &yes, sizeof yes,
                                            &pass) == noErr) {
                        f.k2 = keyEncr55; f.d2 = &pass;
                    }
                    gTimeout = 18000L;
                    step("  stuff into ",
                         sendEvent(gIs703 ? kStuffSuite : kSITSuite55,
                                   gIs703 ? kStuff703 : kStuff55,
                                   fillGeneric, &f, NULL));
                    gTimeout = 3600L;
                    AEDisposeDesc(&pass);
                    AEDisposeDesc(&subjAlias);
                }
            }
            finish(&archive);
            AEDisposeDesc(&archive);
        }
        logFlags(kCommented);
    } else {
        logs("no Comment.sit or no Subject");
    }

    /* ---- quit, and WAIT for it: the volume cannot be unmounted while
     * the application is running off it, which is what -47 meant on the
     * first run. ---- */
    step("quit ", sendEvent(kCoreEventClassX, kAEQuitApplicationX, NULL,
                            NULL, NULL));
    {
        short tries;
        ProcessSerialNumber psn;
        for (tries = 0; tries < 60; tries++) {
            spin(30);
            if (!findProcess(kSITCreator, &psn)) break;
        }
        lognum("waited for it to go, half-seconds ", tries);
    }
    writelog();
}

int main(void)
{
    Rect r;
    long resp;
    EventRecord ev;

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();
    SetRect(&r, 8, 44, 500, 400);
    gWin = NewWindow(NULL, &r, "\006aesit", true, documentProc, (WindowPtr)-1,
                     false, 0);
    SetPort(gWin);
    TextFont(kFontIDMonaco);
    TextSize(9);

    if (Gestalt('evnt', &resp) != noErr) {
        logs("no Apple Event Manager");
    } else {
        run();
    }
    logs("done - the log file is AEResult");
    writelog();
    /* Unmounting is what makes the volume readable from outside: the
     * guest writes through its cache on an unmount and on nothing else
     * that this application can ask for (tools/vmac/README.md). */
    FlushVol(NULL, gFolder.vRefNum);
    {
        OSErr u = fBsyErr;
        short tries;
        for (tries = 0; tries < 10 && u != noErr; tries++) {
            spin(120);
            u = UnmountVol(NULL, gFolder.vRefNum);
        }
        lognum("unmount ", u);
    }
    while (!Button()) WaitNextEvent(everyEvent, &ev, 30, NULL);
    return 0;
}
