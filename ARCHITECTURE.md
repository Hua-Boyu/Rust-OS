# ARCHITECTURE

Bare-metal i686 kernel, Rust (nightly, custom JSON target `target.json`,
build-std core/alloc), no external crates beyond core/alloc.

## Boot path

1. Multiboot v1 header in `.multiboot` section (magic 0x1BADB002, flags
   ALIGN|MEMINFO), 4-byte aligned within the first 8192 bytes, inside the
   PT_LOAD segment (linker.ld emits a correct PT_LOAD; `scripts/validate_elf.py`
   checks the contract).
2. `_start` (src/boot.s): sets up a 16 KiB stack, pushes `%eax` (magic) and
   `%ebx` (multiboot info pointer) as args, calls `kernel_main`.
3. Two boot paths verified in QEMU: direct ELF load (`-kernel`) and GRUB
   multiboot from `dist/rosti.iso` (SeaBIOS).

## Modules

- `src/main.rs` — entry, panic handler (serial + VGA), init sequence:
  serial/VGA → bootstrap heap → mmap/boot reservations → frames/page tables →
  GDT/IDT → validated paging → PS/2/PIT → shell and `hlt` idle loop.
- `src/multiboot.rs` — BootInfo layout per spec; pure host-testable mmap
  parser honoring variable entry sizes with bounds checks; allocation-free
  `find_usable_block`; boot-owned buffers/module payloads reserved by flags.
- `src/allocator.rs` — `SpinMutex<BumpAlloc>` over a page-aligned 1 MiB heap
  inside kernel BSS, with checked allocation arithmetic. It cannot cross mmap
  gaps or overlap bootloader payloads; dealloc resets when no live allocations remain.
- `src/gdt.rs` — null/code/data descriptors, correct access-byte OR semantics,
  lgdt limit = wire size − 1, segment reload.
- `src/interrupt.rs` — 256-entry IDT, PIC remap to 0x20/0x28, IRQ1 unmasked;
  keyboard ISR; hardware-IRQ dummy handlers send EOI. **ISRs must use the
  lockfree serial writer only** — the VGA writer is behind a non-reentrant
  SpinMutex and deadlocks if the interrupted context holds it.
- `src/io/ports.rs` — 64 KiB port allocator, `Port` with RAII release;
  lockfree in/out for interrupt-context-safe access.
- `src/io/serial.rs` — COM1 16550 polled writer (debug channel; per-byte
  observable through QEMU `-serial file:`).
- `src/io/vga.rs` — 80x25 text writer behind a SpinMutex (main-path only).
  Supports erasing the previous echoed input cell across wrapped rows; the
  shell's input length protects prompts and previous output from deletion.
- `src/shell.rs` — keyboard-ring consumer, command input buffer, VGA and serial
  echo. Backspace synchronizes buffer removal with both displays. Dispatch
  resets input length even for whitespace-only commands.
- `src/memory/` — bitmap frame allocator (checked arithmetic, reservation
  precedence, double-alloc/double-free rejection, exhaustion returns None;
  physical allocation capped at 256 MiB) and i686 4 KiB identity page tables,
  prepared before GDT/IDT initialization. Paging enables only after mapping
  validation and IDT setup. Identity coverage spans the addressable RAM window
  independently of the 256 MiB allocation cap. Tables are zeroed; the null page
  is absent; allocation failure returns table frames; validation checks every
  intersecting page.
  Phase 5: `PageMap` supports runtime `map`/`unmap`/`translate`/`permissions`
  with conflict rejection, alignment checks, per-page TLB invalidation, and
  explicit `PagePerms` (present/writable/user; NX is NOT claimed —
  `nx_supported=false` for the current single-level 4 KiB mode). A reserved
  virtual growth window [0x800000, 0xE00000) is excluded from the boot identity
  map and mapped one page at a time on demand; growth-window frames are
  reserved for the heap and claimed via `claim_growth_frame`, so page tables
  never live in the window (entry writes assume identity mapping).
- `src/allocator.rs` — `SpinMutex<BumpAlloc>` over a page-aligned 1 MiB heap
  inside kernel BSS, with checked allocation arithmetic. It cannot cross mmap
  gaps or overlap bootloader payloads; dealloc resets when no live allocations
  remain. Phase 5: `KernelHeap` (first-fit reclaiming free list, address-sorted,
  coalescing on free, 8-byte headers, alignment-waste tracking, OOM returns null
  and counts `failed_allocs`, invalid deallocs rejected) is the global
  allocator; its initial region is the 1 MiB bootstrap heap and it grows one
  growth-window page at a time. Lock order is heap → frame allocator (growth
  path only); the frame allocator never re-enters the heap. `BumpAlloc` remains
  available for early boot and regression tests.
- `src/utils/` — bit manipulation trait, SpinMutex.

## Test separation

Host unit tests (`tests_kernel/`, run via `scripts/run_tests.sh` from outside
the project dir) cover pure algorithms only; privileged asm is cfg-gated out.
Privileged execution is verified through local QEMU boot/paging/fault tests
and the live Proxmox QMP/serial verifier. Fatal-fault Cargo features are test
fixtures only; the ISO builder rejects them. See TESTING.md and HANDOVER.md.
