# BRANCHES.md — what each branch is for

One line of orientation each. **Everything else about a branch lives in
`BRANCH_NOTES.md` on that branch** — what it measures, what it costs, what
would close it. Check out the branch and read its notes.

**Each row's headline figure carries the date it was taken**, and that is the
only status this file keeps. A branch goes on being worked after the decision
about it is parked, and its findings land in its own notes, which nothing on
`main` reads: the overlay rows sat three weeks at a seventeenth of the
mechanism's measured value, agreeing with neither the branch nor OPEN_ITEMS.md
(DECISIONS.md 2026-09-25, *the parked decision that outlived its numbers*). An
undated figure here is one nobody can tell is stale.

| branch | what it explores | state |
|---|---|---|
| `rom64k` | one guard, `Has128KROM()`, so the application starts on a 64K-ROM Macintosh instead of bombing on `MaxApplZone` | starts and its interface works under emulation; cannot extract without HFS, and no hardware has run it (MANUAL_TESTS.md §7) |
| `selective-extract` | list the archive, tick what should come out, extract only that — a `list_only` walk, a box, and the skip `begin_entry` has always had | built, graded in `ci.sh`, and driven on screen on System 6.0.8 and System 3.0; **costs 2,720 B of every 1 MB extraction's budget**, and the second walk ~10 ms an entry |

**Merging `main` into `rom64k` deletes the guard, silently.** `main` carries
the removal commit `2dbe26d` ("the 64K-ROM guard lives on rom64k") and the
branch has not touched `mac/macextract_mac.c` since it forked, so git replays
that removal with **no conflict at all** and takes the branch's whole reason
for existing with it. Check before committing any such merge —
`git merge-tree origin/main rom64k` and grep the result for `Has128KROM`; five
occurrences on the tip, zero in the naive merge — and restore it afterwards
with `git show 2dbe26d -- mac/macextract_mac.c tools/make_dist.sh | git apply
-R`. Done on 2026-09-09; DECISIONS.md that date has the general shape.

**`ndif-udif` is DELETED, 2026-09-25**, at `7269acd`. NDIF and UDIF were
built and meant to merge; expanding compressed disk images left this
project's scope the same day DART did, because what reads one is a mounter
(DECISIONS.md 2026-09-25, *the disk images that found another home*). The ref
is gone from `origin`; the SHA is recorded so the work can be recovered by
anyone who still holds the objects.

**`overlay-eager` and `selective-loading` are RETIRED, merged 2026-09-25.**
Both lifetimes live on `main` now — eager is what `dist/` ships, lazy is
`UNC_OVL_LAZY=1` and is compiled by `ci.sh` variant 4c — and the refs are kept
only so their histories can be read. Nothing on them is ahead of `main`, and
the same fix had to be written on both of them once, which is what merging
them was for (DECISIONS.md 2026-09-25, *two branches that were one file
apart*). Do not start work on either.

Branches that exist only in a working copy are not listed; if it is not on
`origin`, it is not a branch anyone else can read.
