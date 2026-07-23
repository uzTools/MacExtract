# PROGRESS.md — milestone status

| Milestone | Status | Notes |
|---|---|---|
| M0 scaffold | **DONE** | build matrix (ASan/UBSan/alignment, -m32, release -Werror), unit harness, diff/robustness harnesses, corpus+manifest tooling, empty engine sniffs gracefully |
| M1 MacBinary + AppleSingle/Double | **DONE** | 195 oracle fixtures byte-exact (data+rsrc+type/creator); 1950 corrupt variants clean; found & excluded a GNUstep oracle bug on `~`-prefixed names |
| M2 BinHex 4 | **DONE** | 179 fixtures byte-exact incl. mail-wrapped banners at >512 B offsets; header+fork CRCs enforced; 3740 corrupt variants clean |
| M3 PackIt | todo | |
| M4 Compact Pro | todo | |
| M5 StuffIt classic 0–3 | todo | |
| M6 StuffIt method 13 (+corpus methods) | todo | |
| M7 SIT5 + Arsenic | todo | |
| M8 zip/gzip/tar/.Z | todo | |
| M9 CLI polish & hardening | todo | |
| M10 Retro68 Mac app (stretch) | todo | |
