# BRANCHES.md — what each branch is for

One line of orientation each. **Everything else about a branch lives in
`BRANCH_NOTES.md` on that branch** — what it measures, what it costs, what
would close it. Nothing here is a status this file keeps up to date; check out
the branch and read its notes.

| branch | what it explores | state |
|---|---|---|
| `rom64k` | one guard, `Has128KROM()`, so the application starts on a 64K-ROM Macintosh instead of bombing on `MaxApplZone` | starts and its interface works under emulation; cannot extract without HFS, and no hardware has run it (MANUAL_TESTS.md §7) |
| `selective-loading` | the ciphers as an overlay, fetched from an `OVLY` resource when a format turns out to want them | mechanism works on a Mac Plus; the decoders it would take next need the probes separated from them first |
| `overlay-eager` | the same overlay, loaded at launch and released as soon as the archive proves it cannot want it | the release reaches the engine's budget as of 2026-09-02; worth 18,116 B on a format that releases |

`selective-loading` and `overlay-eager` are two sides of one coin — load what
is wanted, or unload what is not — and share a mechanism, so read them
together.

Branches that exist only in a working copy are not listed; if it is not on
`origin`, it is not a branch anyone else can read.
