# MacExtract — Makefile
# Engine is C99, no VLAs. Build variants are driven by ci.sh.

CC      ?= gcc
CFLAGS  ?= -O2
WARN     = -std=c99 -Wall -Wextra -Wshadow -Wconversion -Wvla -pedantic
INC      = -Iinclude

BUILD  ?= build

ENGINE_SRC = $(wildcard src/*.c)
ENGINE_OBJ = $(patsubst src/%.c,$(BUILD)/%.o,$(ENGINE_SRC))

THIRD_SRC = $(wildcard third_party/zlib/*.c)
THIRD_OBJ = $(patsubst third_party/zlib/%.c,$(BUILD)/zlib_%.o,$(THIRD_SRC))

CLI_BIN   = $(BUILD)/macextract
TEST_BIN  = $(BUILD)/unit_tests

all: $(CLI_BIN) $(TEST_BIN)

$(BUILD):
	mkdir -p $(BUILD)

# Every header, not two: `src/` carries GENERATED ones (sit6_tables.h,
# sit13_tables.h, ss_dict.h), and an object left stale against one of
# those is invisible until something downstream disagrees — which is how
# a rebuilt engine and a stale reference binary came to disagree about
# the same file on an emulated Mac (2026-08-23).
ENGINE_HDR = include/unclassic.h $(wildcard src/*.h)

$(BUILD)/%.o: src/%.c $(ENGINE_HDR) | $(BUILD)
	$(CC) $(WARN) $(CFLAGS) $(INC) -c $< -o $@

# third_party is exempt from our warning set (vendored code).
#
# Two defines, both because the engine uses zlib for ONE thing: raw
# inflate, via inflateInit2(&zs, -15).
#
#   Z_TESTW=0  leaves W undefined, dropping crc32.c's braided tables and
#              the code that reads them. zlib never computes a CRC here;
#              unc_crc32 does. 5,120 B of A5 world.
#   NO_GZIP    drops inflate.c's gzip-wrapper state machine — the header
#              parse, the name/comment/extra fields and their CRC. The
#              engine reads the gzip header and trailer itself in
#              fmt_exo.c and hands zlib a raw stream, so none of it was
#              ever reachable. 2,618 B of code.
#
# Neither modifies third_party/zlib, which stays vendored unmodified.
# FORMATS.md, `Resident memory`, has the figures.
$(BUILD)/zlib_%.o: third_party/zlib/%.c | $(BUILD)
	$(CC) -std=c99 $(CFLAGS) -DZ_TESTW=0 -DNO_GZIP -Ithird_party/zlib -c $< -o $@

$(CLI_BIN): cli/main.c $(ENGINE_OBJ) $(THIRD_OBJ) | $(BUILD)
	$(CC) $(WARN) $(CFLAGS) $(INC) cli/main.c $(ENGINE_OBJ) $(THIRD_OBJ) -o $@

$(TEST_BIN): tests/unit_main.c tests/unit_formats.c $(ENGINE_OBJ) $(THIRD_OBJ) | $(BUILD)
	$(CC) $(WARN) $(CFLAGS) $(INC) -Isrc tests/unit_main.c $(ENGINE_OBJ) $(THIRD_OBJ) -o $@

test: all
	$(TEST_BIN)

clean:
	rm -rf $(BUILD)

.PHONY: all test clean
