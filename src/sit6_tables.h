/*
 * sit6_tables.h — the fixed decode tree for StuffIt method 6, as the
 * twenty-six bytes it is.
 *
 * Every segment of a method-6 fork is coded with the SAME set of
 * Huffman codes — that is what "fixed" means here — and only the byte
 * each leaf stands for is declared per segment. This file used to
 * carry that code book as two 257-entry uint16_t arrays generated from
 * macutils, **1,028 bytes of .rodata measured on m68k**. It is a
 * run-length pair and an assignment rule instead, since 2026-09-21.
 *
 * Source: reference/deark/modules/stuffit.c, `sit_fixedhuff_init_tree`
 * (MIT; deark credits macunpack as documentation and uses none of its
 * code). The 257 code LENGTHS are `cdlen_RLEcounts` copies each of
 * `cdlen_RLElengths`; the code for each symbol follows the previous
 * one by "shift left when longer, shift right and add one when
 * shorter, add one when equal", taking the symbols in their own order
 * rather than sorted by length — which is why this is not a canonical
 * code and `unc_canon_build` cannot make it.
 *
 * **Equivalence to the table this replaces was checked over the whole
 * input space**, not by spot checks: all 8,192 bit paths of depth 13
 * reach the same leaf after the same number of bits in both trees, and
 * both have exactly 257 internal nodes (2026-09-21). The terminator is
 * the one place they could have differed — macunpack spends 13 bits on
 * it, reaching either of two leaves, where the code book gives symbol
 * 256 twelve — so `sit6_build` reproduces that split deliberately.
 */
#ifndef UNC_SIT6_TABLES_H
#define UNC_SIT6_TABLES_H

#include <stdint.h>

#define SIT6_LEAVES   258
#define SIT6_INTERNAL 257
#define SIT6_DEPTH    13
#define SIT6_CODES    257       /* symbols the fixed code book has */
#define SIT6_RUNS     13        /* run-length pairs that state it   */

static const uint8_t sit6_runlen[SIT6_RUNS] = {
    1, 1, 4, 12, 32, 16, 49, 2, 2, 40, 95, 2, 1
};
static const uint8_t sit6_runbits[SIT6_RUNS] = {
    3, 4, 5, 6, 7, 8, 9, 10, 9, 10, 11, 13, 12
};

#endif
