# unclassic — Makefile
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

CLI_BIN   = $(BUILD)/unclassic
TEST_BIN  = $(BUILD)/unit_tests

all: $(CLI_BIN) $(TEST_BIN)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/%.o: src/%.c include/unclassic.h src/unc_internal.h | $(BUILD)
	$(CC) $(WARN) $(CFLAGS) $(INC) -c $< -o $@

# third_party is exempt from our warning set (vendored code)
$(BUILD)/zlib_%.o: third_party/zlib/%.c | $(BUILD)
	$(CC) -std=c99 $(CFLAGS) -Ithird_party/zlib -c $< -o $@

$(CLI_BIN): cli/main.c $(ENGINE_OBJ) $(THIRD_OBJ) | $(BUILD)
	$(CC) $(WARN) $(CFLAGS) $(INC) cli/main.c $(ENGINE_OBJ) $(THIRD_OBJ) -o $@

$(TEST_BIN): tests/unit_main.c $(ENGINE_OBJ) $(THIRD_OBJ) | $(BUILD)
	$(CC) $(WARN) $(CFLAGS) $(INC) -Isrc tests/unit_main.c $(ENGINE_OBJ) $(THIRD_OBJ) -o $@

test: all
	$(TEST_BIN)

clean:
	rm -rf $(BUILD)

.PHONY: all test clean
