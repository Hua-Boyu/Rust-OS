# BUGFIXES

Confirmed defects, evidence, and fixes (this session unless noted).

## 1. ISR deadlock on the VGA writer SpinMutex (fixed)

- Evidence: 10-run probe was 7/10–8/10 with `KERNEL_FAULT (init incomplete)`.
  QEMU int-trace (`-d int`) showed `Servicing hardware INT=0x21` firing while
  the main path was inside `println!` (which holds the VGA writer mutex). The
  keyboard ISR called `println!` → re-locked a non-reentrant SpinMutex →
  deadlock; `ROSTI: boot complete` never printed.
- Fix: all ISRs write only through the lockfree serial writer
  (`io::serial::SerialWriter`), never `println!`.
- Result: 10/10 consecutive boots PASS after the fix.
- Regression rule: no `println!` (or any mutex-backed writer) inside an ISR.

## 2. Dummy IDT handlers never send EOI (fixed)

- A dummy handler for hardware IRQ slots (0x20–0x2F) leaves the PIC latched,
  so the PIC stops delivering further IRQs.
- Fix: hardware-IRQ-range dummy entries now point to `isr_hardware_dummy`,
  which sends EOI. Non-IRQ slots keep the plain dummy.

## 3. Uncontrolled busy loop at end of boot (fixed)

- `kernel_main` ended in `loop {}` with interrupts enabled — pure busy spin.
- Fix: `hlt` loop; CPU idles until the next interrupt. Verified: 10/10 boots
  still pass, ISO boot test passes.

## 4. PIC masking left IRQ1 (keyboard) masked (fixed, prior session)

- Master PIC mask 0xFD masked IRQ1, so the keyboard handler at 0x21 could
  never fire. Now both PICs are fully unmasked after remap.
- Verified live: keyboard scancode received through the IDT from the ISO boot
  path (`kb scancode: 97`).

## 5. Multiboot mmap parsing bounds (fixed, prior session; regression-tested)

- Variable-length entries: entry `size` field is honored; malformed/truncated
  entries stop parsing instead of reading out of bounds.
- Allocation-free `find_usable_block` avoids re-entering the allocator's own
  SpinMutex during `init()`.
- Regression coverage: `mmap_parse_variable_size_entries`,
  `mmap_parse_truncated_entry_stops`, `mmap_find_usable_block_skips_type2`,
  `mmap_find_usable_block_skips_base_zero` (host tests, all pass).

## 6. GDT descriptor encoding (fixed, prior session; regression-tested)

- Access byte built with OR, not XOR (XOR toggles off already-set bits, e.g.
  Accessed vs ReadWrite collide). `lgdt` limit = size − 1 using the wire size
  (8 bytes/descriptor), not `size_of::<GdtSegment>()`.
- Regression coverage: `gdt_code_descriptor_encoding`,
  `gdt_access_byte_or_not_xor`.

## 7. IDT gate encoding (regression-tested)

- 32-bit interrupt gate: offset split low/high 16 bits, selector, gate type
  0x8E, present bit. Coverage: `idt_entry_encoding`,
  `idt_invalid_entry_is_zero`.

## Still open / not yet implemented

- Exception handlers with CPU-pushed error codes: only slot 13 is registered;
  error-code exceptions (8, 10–14, 16) need dedicated ISRs.
- PS/2 command/data handling is a minimal enable stub (no timeout handling on
  command writes, no ACK byte checking).
- Spinlocks are not interrupt-safe (no reentrancy guard); acceptable while
  ISRs avoid mutex-backed writers, but should be hardened.
- Paging, RTC, allocator beyond bump — not implemented.
