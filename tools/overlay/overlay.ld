/* Flat overlay image: entry at offset 0, code then read-only data, nothing
 * else. .data/.bss are deliberately absent — an overlay with mutable globals
 * would need an A5 world it does not have. The build fails if any appear. */
ENTRY(ovl_main)
SECTIONS
{
    /* GCC's MacsBug names, one per function, before anything can claim them:
     * ld gives an input section to the FIRST rule that matches, and .text*
     * below would. 11,652 B across the seventeen images on 2026-10-22, each
     * byte heap for the format that keeps the image. */
    /DISCARD/ : { *(.text.*.macsbug) }
    . = 0;
    .text : { *(.text.ovl_main) *(.text*) *(.rodata*) }
    .data : { *(.data*) }
    .bss  : { *(.bss*) *(COMMON) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
