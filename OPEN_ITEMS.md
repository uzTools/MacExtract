# OPEN_ITEMS.md — what is missing, as of 2026-08-01

A standing audit of the gaps in this project: things not done, things done but
not verified, and things the repository currently asserts more confidently than
the evidence supports.

This is **not** BLOCKERS.md. That file records milestones that could not be
completed and investigations that went wrong; it currently reports no open
blockers, and that is accurate. Everything here is either deliberate scope,
unverified-but-probably-fine, or a small hole worth closing — none of it stops
the engine or the CLI, which are byte-exact against the oracle across 771
fixtures in `./ci.sh`.

Ranked by how much it matters. Each item says what would close it.

---

## 1. Cancel with partial output is untested under streaming writes

**Status: a real hole, introduced 2026-07-25 with the streaming-write change
(04bfeb9), cheap to close.**

The Mac sink used to accumulate each whole fork in RAM and write it in
`sink_end`. It now writes each chunk straight through as the engine produces
it. That changes what a cancel means: under staging, an aborted entry had put
nothing on disk yet; under streaming, it has partial bytes on disk **and a fork
still open** when the user hits Cmd-. or the Cancel button.

Neither test covers that:

- `tests/mac_sink_test.c:232` (`--cancel`, run by `ci.sh` via
  `tests/run_mac_sink.sh`) calls `sink_begin` and then
  `sink_end(UNC_ERR_ABORTED)` **without ever calling `sink_write`**. Under
  staging that was the whole story. Under streaming it exercises only the
  "no fork was ever opened" path.
- The on-Mac interactive cancel test — the `derived-EmpireBuilderDemo.sit`
  partial-output check recorded at `MANUAL_TESTS.md:29` — was driven against
  the **pre-streaming** binary.

The code path looks correct: `sink_end` calls `StreamClose`
(`mac/unclassic_mac.c:679`) before `MyHDelete` (`mac/unclassic_mac.c:731`), so
the fork is closed before the partial file is deleted. But "looks correct" is
exactly what the staging-era comments claimed, and BLOCKERS.md is a record of
where that led.

**To close:** extend the `--cancel` mock case to write a chunk to each fork
before aborting, and assert the file is gone; then re-drive the interactive
cancel on Mini vMac and update the note at `MANUAL_TESTS.md:163`.

---

## 2. The `v0.1` tag is 10 commits behind and now misinforms

**Status: the repository states something untrue to anyone who checks out the
tag.**

`v0.1` points at `ba492ac` (`bd3323e v0.1: clarify 1 MB claim ...`). Since
then, three commits changed the headline results. The tagged tree still says:

| Tagged at v0.1 | True on master |
|---|---|
| 39/44 on-Mac at 4 MB, four timeouts | 44/44, no timeouts |
| `derived-RWAsm_Folder.sit` an unexplained failure | does not reproduce; 38/38 byte-exact |
| 36/44 at 1 MB | 39/44 |
| shell RAM limited by largest output fork | streaming; output size costs the shell nothing |
| "185 s on a 7 MHz 68000" | struck — the 1x setup that produced it is gone |

**To close:** tag `v0.2` at the current head, or re-tag, so the released marker
matches the released claims.

---

## 3. Verified in an emulator, never on hardware

**Status: documented in full at `MANUAL_TESTS.md` "Still untested"; repeated
here because it is the largest genuine unknown.**

- **Real 68k hardware: never run.** No genuine floppy I/O, no real media errors
  mid-write, no real 8 KB stack underneath a real ROM's own usage. The
  per-entry I/O error path has never seen an actual I/O failure.
- **Mac OS 9: never run.** The `WaitNextEvent` branch, `SFReply.vRefNum` as a
  System 7+ working-directory reference, HFS+ names, and the `SIZE` partition
  under a real Process Manager are all untested code.
- **The interactive application has not been re-driven on-Mac since the sink
  rewrite.** Only the `-DUNC_MAC_AUTOTEST` build has been replayed
  (`tools/vmac/run.py`), and it uses neither SFGetFile, nor the progress
  dialog, nor the alerts. The sink itself is shared and is covered; the UI
  around it is not.

**To close:** run the `MANUAL_TESTS.md` checklist on a real Mac Plus and on
OS 9. Nothing here can be closed on Linux.

---

## 4. Capability gaps that are deliberate, but still gaps

- **StuffIt 5 / Arsenic on a 1 MB machine: 1 of 6 sampled fixtures.** A block
  needs 0.6–2.6 MB (block + a 4x-block inverse-BWT vector), so the floor-target
  machine mostly cannot do StuffIt 5. The engine declines per entry and leaves
  the rest of the archive alone, which is the designed behaviour and is
  documented in FORMATS.md — but it is the one format the "runs on a Mac Plus"
  claim does not really cover. Closing it means a fundamentally lower-memory
  inverse BWT, not a bug fix.
- **No timing data at all.** The Mini vMac builds run "all out", so the harness
  measures correctness only. "Runs on a Mac Plus" is proven; "is usable on a
  Mac Plus" is not. Closing it means a third emulator build at `-speed z` and a
  small timing sweep.
- **Out of scope by the brief, and still out:** compression, StuffIt X
  (`.sitx`), encrypted archives, multi-segment archives, disk-image extraction,
  Now Compress, and LZH *extraction* — LZH was the optional half of M8 and is
  detect-only (`FORMATS.md:26`).

---

## 5. Loose ends

- **The Retro68 `HOpenDF` bug was never filed.** `PBHOpenDFSync` issues a
  System 7 trap and, unlike the non-hierarchical `OpenDF` beside it, has no
  fallback, so `HOpenDF` returns `paramErr` on System 6. Written up ready to
  post in `tools/retro68-hopen-repro/ISSUE.md`; not submitted because this
  environment has no GitHub credentials (`BLOCKERS.md:43`).
- **The true root cause of the original "every open fails" saga is unknown.**
  Rewriting the File Manager calls as fully-zeroed HFS param blocks fixed it;
  which field mattered was never established, and the `HOpen`-glue attribution
  was withdrawn after a minimal repro disproved it. BLOCKERS.md says so
  plainly. Not being chased — the app is verified byte-exact as it stands.
- **StuffIt method 1 (RLE) is unit-test-only.** No corpus fixture uses it, so
  it is pinned by hand-built vectors rather than by the oracle
  (`PROGRESS.md:10`).
- **Six StuffIt and two Compact Pro fixtures are excluded** as
  oracle-undecidable or oracle-buggy (`PROGRESS.md:9`, `PROGRESS.md:11`). They
  are not known failures; the oracle cannot adjudicate them.
