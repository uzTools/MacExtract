# BRANCHES.md — what each branch is for

One line each. **Everything else about a branch lives in `BRANCH_NOTES.md`
on that branch**, where it has one. Each row's figure carries the date it was
taken; an undated figure here cannot be told stale (DECISIONS.md 2026-09-25,
*the parked decision that outlived its numbers*). Checked against `origin` 2026-10-25.

| branch | what it explores | state |
|---|---|---|
| `eta-backstep` | the progress dialog's time left from byte counts, timed per layer | **merged 2026-10-16** (DECISIONS.md 2026-10-16, *the estimate that went back up*) |
| `rom64k` | `GrowApplZone()` in place of `MaxApplZone`, so the application starts on a 64K ROM | **merged 2026-10-16**; kept for its `BRANCH_NOTES.md`, 11 commits not reachable from `main` (DECISIONS.md 2026-10-15, *the purge MaxApplZone never did*) |
| `probes-one-place` | every probe in its reader's `_probe.c` | **merged 2026-10-20**, 0 B resident, −32 B for StuffIt classic's probe (DECISIONS.md 2026-10-20, *one place for every probe*) |
| `selective-extract` | choosing entries in the Macintosh application | **PARKED BY DECISION 2026-09-26**, out of scope (OPEN_ITEMS.md, *Out by the brief*; DECISIONS.md 2026-09-26, *the feature that was parked, and is now out*). 3 commits ahead of `main`; its notes predate the overlays: no current figure. Do not start work on it |
| `overlay-eager`, `selective-loading` | the two overlay lifetimes | **RETIRED, merged 2026-09-25**: eager is what `dist/` ships, lazy is `UNC_OVL_LAZY=1` (`ci.sh` variant 4c) (DECISIONS.md 2026-09-25, *two branches that were one file apart*). `selective-loading` keeps 8 commits of 2026-09-09→25 not reachable from `main`. Do not start work on either |
| `meta-archives`, `meta-envelopes`, `meta-localtime`, `meta-macosx`, `meta-plumbing`, `meta-sitclassic`, `meta-sitclassic-research`, `meta-spotlight` | M69/M70's Finder metadata, one reader family each | **merged 2026-10-17/18**, nothing ahead of `main` (PROGRESS.md, M69, M70) |
| `no-foreign` | recognising nothing that is not extracted | **merged 2026-10-18**, nothing ahead (PROGRESS.md, M71) |
| `runtime-trim` | the trimmed runtime, graded on Mac OS 9.2 | **merged 2026-10-22**, nothing ahead |

**`ndif-udif` is DELETED, 2026-09-25**, at `7269acd`: compressed disk images
left this project's scope with DART (DECISIONS.md 2026-09-25, *the disk images
that found another home*). The SHA is recorded so the work can be recovered.

Branches that exist only in a working copy are not listed.
