/* Flat overlay image: entry at offset 0, code then read-only data, nothing
 * else. .data/.bss are deliberately absent — an overlay with mutable globals
 * would need an A5 world it does not have. The build fails if any appear. */
ENTRY(ovl_main)
SECTIONS
{
    . = 0;
    .text : { *(.text.ovl_main) *(.text*) *(.rodata*) }
    .data : { *(.data*) }
    .bss  : { *(.bss*) *(COMMON) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
