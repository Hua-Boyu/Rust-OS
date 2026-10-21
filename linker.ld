/* From OSDev Bare Bones tutorial, adapted for ld.lld.
   The bootloader will look at this image and start execution at the symbol
   designated as the entry point. */
ENTRY(_start)

/* QEMU's multiboot loader requires program headers (or a PVH note).
   rust-lld emits none by default for the `none` target, so declare one
   PT_LOAD segment covering the whole kernel image. */
OUTPUT_FORMAT(elf32-i386)

/* One PT_LOAD segment covering the whole kernel image. rust-lld emits no
   program headers for the `none` target without an explicit PHDRS block, and
   QEMU's multiboot ELF loader requires them. */
PHDRS
{
    kernel PT_LOAD FLAGS(7);
}

MEMORY
{
    kernel (RWX) : ORIGIN = 0x200000, LENGTH = 4M
}

/* Tell where the various sections of the object files will be put in the final
   kernel image. */
SECTIONS
{
    /* 2M load address (safer than the traditional 1M under UEFI-era firmware).
       This kernel does not use the multiboot2 relocation feature, so the load
       address is fixed. */

    . = 0x200000;
    KERNEL_START = .;

    /* The multiboot header must be its own explicit output section with KEEP:
       it contains no symbols, so --gc-sections would otherwise discard it, and
       it must land within the first 8192 bytes of the file the bootloader scans. */
    .multiboot ALIGN(4K) : { KEEP(*(.multiboot)) } >kernel

    /* Retain the opt-in terminal F3 contract for production emitted-code audit.
       KEEP is not a boot invocation; ordinary kernel_main never calls it. */
    .text ALIGN(4K) : { KEEP(*(.text.f3_contract)) *(.text*) } >kernel

    /* Read-only data. */
    .rodata ALIGN(4K) : { *(.rodata*) } >kernel

    /* Read-write data (initialized) */
    .data ALIGN(4K) : { *(.data*) } >kernel

    /* Read-write data (uninitialized) and stack */
    .bss ALIGN(4K) : { *(COMMON) *(.bss*) } >kernel

    KERNEL_END = .;

    /* The compiler may produce other sections, by default it will put them in
       a segment with the same name. Simply add stuff here as needed. */
}
