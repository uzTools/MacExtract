# TESTING.md — how unclassic is validated

## Layers

1. **Unit tests** (`tests/unit_main.c` + `tests/unit_formats.c`):
   CRC check values, big-endian readers, per-format probe/decoder tests
   on synthetic buffers. Run by `make test` and every `ci.sh` variant.
2. **Differential tests** (`tools/run_diff.py`): every fixture is
   extracted by the engine and compared byte-for-byte against a
   committed oracle manifest.
3. **Robustness tests** (`tools/run_robustness.py`): truncated and
   bit-flipped fixture variants must produce clean per-entry errors —
   never a crash, hang, or sanitizer trip. Run under
   ASan+UBSan+`-fsanitize=alignment` with `-fno-sanitize-recover=all`,
   so any violation is fatal and caught.

## The oracle

The oracle is The Unarchiver's CLI (`unar`/`lsar` 1.10.8, Debian
package `unar`), whose XADMaster engine is also our primary reference.
`macunpack` (macutils) is a secondary cross-check for old formats.

### Resource forks on Linux

`unar --help` documents `-forks (-k) <visible|hidden|skip>`; with
`-k visible` (the default) each resource fork is written as an
**AppleDouble container** named `<file>.rsrc` beside the data fork.
Manifest building therefore parses the AppleDouble (magic
`0x00051607`; entry id 2 = raw resource fork, id 9 = Finder info with
type/creator) to recover raw fork bytes and metadata — see
`tools/make_manifests.py::parse_appledouble`.

### Exact oracle invocation

```
lsar -j -nr -e macintosh <fixture>     # format name + metadata (JSON)
unar -nr -D -f -q -k visible -e macintosh -o <tmpdir> <fixture>
```

- `-nr`: no recursion — each manifest describes exactly one container
  layer (see DECISIONS.md; nesting is tested by chaining layers).
- `-e macintosh`: pin filename decoding to MacRoman rather than
  auto-detection, so manifests are deterministic.
- `-D`: no wrapper directory.

### Manifest format

`fixtures/manifests/<fixture>.json`: fixture sha256/size, lsar format
name, and per entry: name (UTF-8, NFC-normalized), data fork
sha256+size, resource fork sha256+size, and type/creator when the
oracle exposes them.

### Comparison normalization

The engine emits raw MacRoman filename bytes; the CLI converts to
UTF-8 (table in `cli/main.c`). `run_diff.py` NFC-normalizes both the
manifest names and the engine's output paths before comparing, and
compares forks by SHA-256. Type/creator are compared through
`unclassic l` output. Dates are recorded loosely but not compared (v1;
see DECISIONS.md).

## Corpus

`fixtures/` is gitignored (copyrighted historical software); committed
are only `fixtures/SOURCES.md` (name, sha256, size, URL per fixture)
and `fixtures/manifests/`. `tools/harvest.py --restore` re-downloads
the corpus; `--probe URL` adds a candidate, accepting it only if lsar
can read it.

## Running everything

```
./ci.sh          # full matrix; must be green before every commit
```
