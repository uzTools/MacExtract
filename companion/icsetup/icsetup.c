/* icsetup.c — make MacExtract the helper Internet Config hands downloaded
 * archives to, and put the map back on request.
 *
 * What it changes: in Internet Config's `Mapping` preference, every entry
 * whose extension is one MacExtract extracts (kExts) AND which is already
 * post-processed gets post-processor creator 'MExt' and name "MacExtract".
 * An entry nobody post-processes stays so: on Mac OS 9.2's stock map that
 * keeps `.ascii` (plain text, SimpleText) and `.sea` (an application, run
 * rather than opened) out, and takes the 20 entries StuffIt Expander had.
 * The entry's own type and creator are left alone, so the file is still
 * stamped as before and a stub that claims that creator still opens it
 * on a double-click. Extensions with no entry are not added: choosing a
 * type and creator for them is not this program's business.
 *
 * Undo: before the first change, the whole `Mapping` is saved under this
 * program's own key, kBackupKey; Restore writes it back and deletes
 * nothing else.
 *
 * Why the raw preference and not the per-entry calls: ICGetPref/ICSetPref
 * exist in every Internet Config, 1.x included; ICGetIndMapEntry and
 * friends are 2.0's. The entry layout is ICMapEntry. Source:
 * reference/mpack/macICKeys.h (ICMapEntry, ICmap_post_mask) and
 * macmpack.c's walk of kICMapping; the same struct is in Apple's
 * InternetConfig.h (Universal Interfaces, IC 2.5).
 *
 * What it does NOT make work: a second download finishing while
 * MacExtract is already running. MacExtract is not high-level-event
 * aware, so that Open Documents event is lost (DECISIONS.md 2026-10-31,
 * *the hand-off that arrives once*).
 */
#include <Dialogs.h>
#include <Fonts.h>
#include <Memory.h>
#include <Menus.h>
#include <OSUtils.h>
#include <TextEdit.h>
#include <TextUtils.h>
#include <ToolUtils.h>
#include <Windows.h>
#include <InternetConfig.h>

#define kHelperSig   'MExH'
#define kMExt        'MExt'
/* Source: reference/mpack/macICKeys.h, ICmap_post_mask. */
#define kPostMask    0x00000008L

/* Alerts, in icsetup.r. */
enum { kAskUse = 128, kAskRestore = 129, kDone = 130, kFail = 131,
       kNoIC = 132, kNothing = 133 };
enum { kBtnUse = 1, kBtnCancel = 2, kBtnRestore = 3 };

static const unsigned char kMappingKey[] = "\pMapping";
/* Per-application keys in the stock file are the creator in hex, a
 * bullet (MacRoman 0xA5) and a name: `646F6777•WebReadColor`. */
static const unsigned char kBackupKey[] = "\p4D457874\xA5SavedMapping";
static const unsigned char kPostName[]  = "\pMacExtract";
static const unsigned char kEmpty[]     = "\p";
static const unsigned char kRestored[]  = "\pThe file map is as it was before.";
static const unsigned char kNowOpen[]   =
    "\p file types now open in MacExtract after a download.";

/* The extensions of the formats FORMATS.md's table says MacExtract
 * extracts, as Internet Config's map spells them (with the dot), matched
 * without regard to case. Disk images and mail are not archives here. */
static const char *const kExts[] = {
    ".sit", ".sea", ".hqx", ".bin", ".cpt", ".pit", ".zip", ".gz", ".tgz",
    ".z", ".taz", ".tar", ".arc", ".lha", ".lzh", ".pkg", ".uu", ".uue",
    ".pf", ".dd", ".hex", ".hcx", ".ascii", ".b64", ".mime", NULL
};

static Boolean ours(const unsigned char *ext)
{
    short i, j, n = ext[0];
    for (i = 0; kExts[i]; i++) {
        const char *e = kExts[i];
        for (j = 0; j < n && e[j]; j++) {
            unsigned char c = ext[j + 1];
            if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
            if (c != (unsigned char)e[j]) break;
        }
        if (j == n && e[j] == 0) return true;
    }
    return false;
}

static short get16(const unsigned char *p) { return (short)((p[0] << 8) | p[1]); }
static long get32(const unsigned char *p)
{
    return ((long)p[0] << 24) | ((long)p[1] << 16) | ((long)p[2] << 8) | p[3];
}
static void put16(unsigned char *p, short v) { p[0] = v >> 8; p[1] = (unsigned char)v; }
static void put32(unsigned char *p, long v)
{
    p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = (unsigned char)v;
}

/* Walk `map`; return how many entries are ours and how many of those
 * already name MacExtract. -1 if the walk does not land on the end. */
static long survey(const unsigned char *map, long size, long *already)
{
    long q = 0, n = 0;
    *already = 0;
    while (q < size) {
        short total, fixed;
        if (size - q < 22) return -1;
        total = get16(map + q);
        fixed = get16(map + q + 2);
        if (total < fixed + 5 || fixed < 22 || q + total > size) return -1;
        if (ours(map + q + fixed) && (get32(map + q + 18) & kPostMask)) {
            n++;
            if (get32(map + q + 14) == kMExt &&
                (get32(map + q + 18) & kPostMask)) (*already)++;
        }
        q += total;
    }
    return n;
}

/* A new map with ours rewritten. Each entry's fixed part is copied with
 * postCreator and the post bit set; its five strings are copied, the
 * third (the post-processor's name) replaced. Anything past the five
 * strings in an entry is kept. */
static Ptr rewrite(const unsigned char *map, long size, long *outSize)
{
    long q = 0, o = 0;
    Ptr out = NewPtr(size + 64L * 256);   /* names may grow, 63 B each */
    unsigned char *w = (unsigned char *)out;
    if (!out) return NULL;
    while (q < size) {
        short total = get16(map + q), fixed = get16(map + q + 2);
        const unsigned char *e = map + q;
        if (!ours(e + fixed) || !(get32(e + 18) & kPostMask)) {
            if (o + total > GetPtrSize(out)) { DisposePtr(out); return NULL; }
            BlockMoveData(e, w + o, total);
            o += total;
        } else {
            long start = o, p = fixed, k;
            if (o + total + 256 > GetPtrSize(out)) { DisposePtr(out); return NULL; }
            BlockMoveData(e, w + o, fixed);
            put32(w + o + 14, kMExt);
            o += fixed;
            for (k = 0; k < 5; k++) {
                const unsigned char *s = (k == 2) ? kPostName : e + p;
                BlockMoveData(s, w + o, s[0] + 1);
                o += s[0] + 1;
                p += e[p] + 1;
            }
            if (p < total) {                 /* whatever follows */
                BlockMoveData(e + p, w + o, total - p);
                o += total - p;
            }
            put16(w + start, (short)(o - start));
        }
        q += total;
    }
    *outSize = o;
    return out;
}

static void num(long v, unsigned char *s) { NumToString(v, s); }

static short ask(short id, long a, long b)
{
    Str255 sa, sb;
    num(a, sa);
    num(b, sb);
    ParamText(sa, sb, kEmpty, kEmpty);
    return Alert(id, NULL);
}

static void fail(const char *where, long err)
{
    Str255 w, e;
    short i = 0;
    while (where[i] && i < 200) { w[i + 1] = where[i]; i++; }
    w[0] = (unsigned char)i;
    num(err, e);
    ParamText(w, e, kEmpty, kEmpty);
    StopAlert(kFail, NULL);
}

int main(void)
{
    ICInstance inst;
    ICAttr attr;
    OSStatus err;
    long size = 0, bsize = 0, n, already, newSize;
    Ptr map = NULL, fresh = NULL;
    Boolean haveBackup;
    short item;

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();

    err = ICStart(&inst, kHelperSig);
    if (err != noErr) { StopAlert(kNoIC, NULL); return 0; }
    err = ICFindConfigFile(inst, 0, NULL);
    if (err != noErr) { fail("ICFindConfigFile", err); goto stop; }

    err = ICGetPref(inst, kMappingKey, &attr, NULL, &size);
    if (err != noErr || size <= 0) { fail("reading the file map", err); goto stop; }
    map = NewPtr(size);
    if (!map) { fail("memory", MemError()); goto stop; }
    err = ICGetPref(inst, kMappingKey, &attr, map, &size);
    if (err != noErr) { fail("reading the file map", err); goto stop; }
    n = survey((unsigned char *)map, size, &already);
    if (n < 0) { fail("reading the file map", -1); goto stop; }
    haveBackup = ICGetPref(inst, kBackupKey, &attr, NULL, &bsize) == noErr
                 && bsize > 0;

    if (n == 0) { NoteAlert(kNothing, NULL); goto stop; }
    item = (already == n && haveBackup) ? ask(kAskRestore, n, already)
                                        : ask(kAskUse, n, already);
    if (item == kBtnCancel) goto stop;

    err = ICBegin(inst, icReadWritePerm);
    if (err != noErr) { fail("opening Internet Config", err); goto stop; }
    if (item == kBtnRestore) {
        Ptr saved;
        if (!haveBackup) { ICEnd(inst); goto stop; }
        saved = NewPtr(bsize);
        if (!saved) { ICEnd(inst); fail("memory", MemError()); goto stop; }
        err = ICGetPref(inst, kBackupKey, &attr, saved, &bsize);
        if (err == noErr)
            err = ICSetPref(inst, kMappingKey, kICAttrNoChange, saved, bsize);
        DisposePtr(saved);
        ICEnd(inst);
        if (err != noErr) { fail("restoring the file map", err); goto stop; }
        ParamText(kRestored, kEmpty, kEmpty, kEmpty);
        NoteAlert(kDone, NULL);
        goto stop;
    }
    /* Use: keep the map as it was the FIRST time, so a second run over
     * a map this program already changed does not overwrite the backup
     * with its own work. */
    if (!haveBackup) {
        err = ICSetPref(inst, kBackupKey, 0, map, size);
        if (err != noErr) { ICEnd(inst); fail("saving the file map", err); goto stop; }
    }
    fresh = rewrite((unsigned char *)map, size, &newSize);
    if (!fresh) { ICEnd(inst); fail("memory", MemError()); goto stop; }
    err = ICSetPref(inst, kMappingKey, kICAttrNoChange, fresh, newSize);
    ICEnd(inst);
    if (err != noErr) { fail("writing the file map", err); goto stop; }
    {
        Str255 s;
        num(n, s);
        ParamText(s, kNowOpen, kEmpty, kEmpty);
    }
    NoteAlert(kDone, NULL);

stop:
    if (fresh) DisposePtr(fresh);
    if (map) DisposePtr(map);
    ICStop(inst);
    return 0;
}
