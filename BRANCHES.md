# BRANCHES.md — what each branch is for

One line each. **Everything else about a branch lives in `BRANCH_NOTES.md`
on that branch**, where it has one. Each row's figure carries the date it was
taken; an undated figure here cannot be told stale (DECISIONS.md 2026-09-25,
*the parked decision that outlived its numbers*). Checked against `origin` 2026-11-02.

| branch | what it explores | state |
|---|---|---|
| `companion-expander55` | StuffIt Expander 5.5 handing its downloads to MacExtract through Internet Config | **open**, 28 commits ahead of `main` (2026-11-02) |
| `rom64k` | `GrowApplZone()` in place of `MaxApplZone`, so the application starts on a 64K ROM | **merged 2026-10-16**; kept for its `BRANCH_NOTES.md`, 11 commits not reachable from `main` (DECISIONS.md 2026-10-15, *the purge MaxApplZone never did*) |
| `selective-extract` | choosing entries in the Macintosh application | **PARKED BY DECISION 2026-09-26**, out of scope (OPEN_ITEMS.md, *Out by the brief*; DECISIONS.md 2026-09-26, *the feature that was parked, and is now out*). 3 commits ahead of `main`; its notes predate the overlays: no current figure. Do not start work on it |

**Thirteen merged branches DELETED, 2026-11-02**, none with a commit
outside `main`: `eta-backstep` `2b20a47`, `meta-archives` `87d0f0d`,
`meta-envelopes` `0ec740f`, `meta-localtime` `a666195`, `meta-macosx`
`40a5f7f`, `meta-plumbing` `55ca137`, `meta-sitclassic` `f9c6a9e`,
`meta-sitclassic-research` `d32cff8`, `meta-spotlight` `c0be3ab`,
`no-foreign` `970f1b4`, `overlay-eager` `2836cdb`, `probes-one-place`
`9be493e`, `runtime-trim` `cb1dc73`. **`selective-loading` DELETED the
same day** at `2fc0b91`: its 5 commits outside `main` were DART's overlay
(DART has left scope), the stale-image fix `main` has from `overlay-eager`,
and `BRANCH_NOTES.md` figures for the 2026-09-24 lazy build.

**`ndif-udif` is DELETED, 2026-09-25**, at `7269acd`: compressed disk images
left this project's scope with DART (DECISIONS.md 2026-09-25, *the disk images
that found another home*). The SHA is recorded so the work can be recovered.

Branches that exist only in a working copy are not listed.
