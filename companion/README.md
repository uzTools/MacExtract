# companion — opening archives in MacExtract by double-click

The Finder opens a double-clicked document with the application whose
creator matches the document's, so a `.sit` goes to StuffIt or nowhere.
A **stub** is a small application that claims one creator. The Finder
launches it for that creator's archives, and it starts MacExtract, which
opens the archive as it opens one dropped on its icon. MacExtract itself
is not changed. Why it works this way, and what has been measured, is
DECISIONS.md 2026-10-10 and 2026-10-11 (*the double-click that goes by
the application's creator*, *where the stubs can live*, *the stub that
hands it on*).

    cmake -B build/stub -S companion/stub \
      -DCMAKE_TOOLCHAIN_FILE=/opt/Retro68-build/toolchain/m68k-apple-macos/cmake/retro68.toolchain.cmake
    cmake --build build/stub
    python3 companion/make_stub.py build/stub/Stub.bin \
      --creator 'SIT!' --types 'SIT!' -o 'SIT! Helper.bin'

The stub goes in a folder beside MacExtract (`MacExtract Helpers`), and
the Finder has to know it: a desktop rebuild registers it from its own
bundle, or an entry in the volume's `Desktop` file does
(`tools/vmac/deskclaim.py` writes one). Nothing yet writes the stubs or
those entries on a Macintosh; that is the companion application, which
does not exist.

| file | what |
|---|---|
| `stub/stub.c`, `stub/stub.r` | the stub: find MacExtract, launch it |
| `make_stub.py` | the stub for one creator: creator, bundle, icons |
| `../tools/icon/make_archive_icon.py` | the archive icon the stubs carry |
