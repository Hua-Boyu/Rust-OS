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

## Shell Backspace and memory-init boot hang (2026-10-12)

- Backspace previously decremented `LINE_LEN` without erasing the VGA echo.
  It now blanks the previous cell and rewinds the writer, including across
  wrapped input. Serial output emits `BS SPACE BS`. Empty input cannot erase
  the prompt, and whitespace-only commands now reset the input length.
- Memory initialization attempted three `FRAME_ALLOC.lock()` calls inside
  one `println!`; temporary guards survived to the end of the call, causing
  a non-reentrant deadlock. Statistics are copied under one scoped guard.
- Regression observed failing on the original display behavior, then passing
  after the fix: `scripts/backspace_test.py` reads actual VGA cells via QMP.
  Final ELF and ISO runs passed 13 checks each at 512 MiB. Host tests: 38/38;
  independent boot stability: 10/10. Evidence is under `test_results/backspace/`.

## Phase 4 memory protections and active paging (2026-10-12)

- Freeing a reserved frame inside a usable mmap range could underflow stats
  and make it allocatable. Release now requires aligned in-bounds addresses
  and evidence that the allocator actually handed the frame out.
- Partial usable frames and overlapping ACPI/reserved entries were unsafe.
  Only fully usable frames are admitted; reserved coverage takes precedence.
  Range arithmetic rejects overflowing usable ranges and conservatively clips
  overflowing reserved ranges.
- The mapping window incorrectly discarded RAM ranges ending above the frame
  cap. Identity coverage now uses the addressable RAM window independently of
  the 256 MiB physical-allocation cap; paging is active on the 512 MiB VM.
- Bump initialization could extend across mmap gaps and claimed all high RAM.
  Bootstrap allocations now use a bounded 1 MiB heap inside kernel BSS. Boot
  metadata/map buffers and module payloads are separately protected.
- Page tables are explicitly zeroed, null is unmapped, partial tail pages are
  validated, and failed table builds return allocated frames.
- Multiboot VBE/framebuffer field widths were wrong; wire-layout tests now
  verify offsets and the header size. Allocation/parser arithmetic is checked.
- Evidence: 49 host tests, four real CPU-fault cases, 20 paging-stability boots,
  25 deployment gates and 20 live checks pass. See `test_results/phase4/acceptance.json`.

## Phase 5 defects found and fixed (2026-10-12)

- `KernelHeap.alloc_inner` returned the header pointer instead of the payload
  pointer (off-by-HEADER_SIZE). Fixed; regression test asserts payload address.
- Alignment waste was double-counted when the payload was aligned past the
  block start. Fixed to count the prefix once.
- `PageMap.unmap` rejected growth-window addresses (window_end bound only),
  so heap growth pages could never be unmapped. Fixed to allow the growth
  window while still rejecting out-of-managed-space addresses.
- OOM on an uninitialized heap returned null without counting `failed_allocs`;
  the shell now reports accurate failure counts.
- `add_region` did not mark the heap initialized, so host tests could not
  allocate. Fixed.
- Real hazard: page-table frames could be allocated inside the heap growth
  window, where virtual ≠ physical breaks `write_entry` (it assumes identity
  mapping). Growth-window frames are now reserved for the heap and claimed
  via `claim_growth_frame`; page tables can never live there. Regression test
  asserts identity growth mapping and double-claim rejection.
- `FrameStats` lacked `Copy`, breaking the shell's copy-then-print pattern
  (E0507). Fixed with `Clone, Copy`.
- Live verifier bug: VGA screen parsing used an 80-byte row stride instead of
  the actual 160 bytes (char+attribute), producing garbage screens; and
  `sendkey " "` is invalid on this QEMU monitor build (`spc` is the valid
  name). Both fixed in `scripts/live_phase5_check.py`; the corrected run
  passed 13/13 live checks.
- A root password had been written into a `deploy-proxmox.py` comment; removed.
  Credentials must come from the process environment only.

## Current remaining limitations

- Vector 14 fatal diagnostics are CPU-tested (unmapped read and null write);
  other error-code exception handlers and recoverable faults remain future work.
- PS/2 command/data handling is a minimal enable stub (no timeout handling on
  command writes, no ACK byte checking).
- Spinlocks are not interrupt-safe (no reentrancy guard); acceptable while
  ISRs avoid mutex-backed writers, but should be hardened.
- RTC and a general-purpose allocator beyond bump are not implemented.
  (Phase 5 adds the reclaiming `KernelHeap`; `BumpAlloc` remains for early boot.)
- Physical allocation below 256 MiB; mapping extends above it. Bootstrap heap
  is fixed at 1 MiB; no demand paging, swapping, user isolation or general
  reclaiming heap. Boot string/config buffers conservatively reserve 4 KiB.
- Phase 5 status: the dynamic heap reuses freed memory and grows one page at a
  time inside the virtual growth window [0x800000, 0xE00000); growth is verified
  in host tests but was not exercised on VM 103 (workload stayed under 1 MiB).
  NX is not supported in 32-bit single-directory paging and is not claimed;
  CR0.WP is set so read-only pages fault on supervisor writes. The 256 MiB
  frame-tracking cap remains: lifting it requires a larger bitmap and verified
  checked arithmetic; deferred until a task requires it.

## Phase 6 filesystem and shell safeguards

- Path reduction must not bypass type checks: traversal checks each current
  node before processing `.` or `..`; `file/..` is an error, not root access.
- Length-only storage accounting would undercount retained capacity after
  truncate. Quotas now use Vec capacity; `stat` reports logical length.
- Infallible Vec growth could panic on filesystem allocation failure. Growth
  is staged with `try_reserve_exact`; failed replace/write/truncate leave the
  original contents and accounting intact. The new shell also rolls back
  creation if its first write fails.
- Slots have generation IDs and cannot resurrect stale file handles. Slots
  retire on generation exhaustion rather than wrap. Directory removal never
  recursively frees descendants; nonempty directories and root are protected.
- Control characters in filenames could inject false console evidence; path
  validation rejects them. The host regression was observed RED, then GREEN.
- Overlong shell lines previously silently dropped bytes, allowing a partial
  file overwrite. A QEMU keyboard test reproduced this. Overflow is now
  latched until Enter and rejects the whole command, including after editing.
- Cwd deletion protection initially obscured a nonempty-directory error as
  `invalid path`. QEMU and a host regression caught it: the shell now reports
  `directory not empty` first, while still protecting an empty cwd.
- Keyboard queue overflow now latches a lock-free loss flag. The consumer
  discards all pending scancodes (including earlier Enter events), resets
  modifiers and rejects the affected line until a new Enter. A host RED/GREEN
  test covers discarding an earlier Enter plus a later damaged command. ISR
  work remains bounded and allocation-free. This does not claim detection of
  loss upstream in the PS/2 controller.
- `mem` previously printed heap/paging details only on VGA. Its main-context
  output now mirrors to serial via allocation-free formatting, with scalar
  snapshots copied after releasing allocator guards. No ISR writer changed.

Remaining limits: RAM-only storage; PS/2 command/ACK limitations and exception
handler limitations are unchanged. File reads and diagnostics execute
serially in the main loop; there is no scheduler or concurrent filesystem I/O.

## Phase 7 descriptor safeguards

- Descriptor slots and open records carry generations. A released slot's
  generation is bumped on close, so a handle captured before close fails as
  `StaleHandle` even after the slot is reused (no ABA aliasing). Generation
  exhaustion retires the slot instead of wrapping.
- Rights are validated on every operation, not at open time only. Duplication
  uses `attenuate()`: any requested bit outside the source mask is rejected,
  so a read-only descriptor can never become writable. Default-deny applies to
  console descriptors until they are wired to real console operations.
- The shared offset lives in the open-file description, not the descriptor
  slot; duplication shares it. A denied write does not advance the offset —
  the initial test expectation (offset moved on denied write) was corrected to
  the defined semantics before any code change.
- Double close is rejected (`InvalidDescriptor` after release); refcounted
  records release only on the last close. Node bindings are generation-checked
  through the VFS, so deleting an open file fails cleanly instead of dangling.
- Directories cannot be read/written as regular files (resource type
  mismatch); offset arithmetic is checked (`OffsetOverflow`).
- Table exhaustion returns `TableFull` without touching filesystem metadata;
  no fd path allocates, so heap fragmentation and lock inversion are
  impossible by construction.
- Live media check: the harness compares the exact QMP file leaf; the live run
  must pass the full runtime path (`/var/lib/vz/template/iso/...`) as
  `--expected-iso`, not a bare filename. This was a harness usage error, not a
  kernel defect; the assertion was not weakened.
