# BUGFIXES

## Phase 11 first prerequisite — partial B19 repair

- Effective permissions no longer report a PTE's access when its PDE denies it.
  PRESENT/RW/USER are intersected; absent grants are normalized to false.
  Mapping/translation now respect directory presence too.
- Raw kernel mapping refuses unsupported USER requests rather than reporting
  user access that was never granted at the directory. No kernel PDE elevation.
- Nonpresent requests no longer silently become present mappings; use unmap.
- All refusals happen before allocation or entry mutation; exact ownership and
  mapping counters tested. Three intended RED regressions and GREEN retained.
- This does NOT resolve retained static PageMap borrows, general safe raw-frame
  ownership, legacy exception ABI, user recovery or unguarded stacks. 11A is
  incomplete; no syscall/ELF/user launch was introduced.

Host270 passed/2 ignored and harness37 passed. Full inherited prerequisite
acceptance PASS54/54, actual exit0; independent source/artifact/cleanup closeout
PASS. Exact report `test_results/phase11/acceptance_20261016T154710Z_q3u90_53/acceptance.json`.
This is not full Phase11 acceptance. See Phase11 handover/design for unresolved
aliasing/frame ownership/exception ABI blockers; no user launch was attempted.

## Phase 10B COMPLETE — local acceptance verified

Source checkpoint: `449ed434ed5dbf1518b99821178a5fcd1d343b75` on `maintenance/phase10`.
Full acceptance: **PASS 53/53 gates**, invocation-owned
**56/56 initramfs scenarios, 3379/3379 matrix checks**.
Evidence: `test_results/phase10b/acceptance_20261016T120546Z_psboeekn/acceptance.json`;
independent closeout: `test_results/phase10b/final_verification.json`.
All 134 source/build inputs were independently rediscovered and hash-matched.
Scoped independent review: no blocking findings (`test_results/phase10b/independent_scoped_review_20261016T111204Z_f632dad1df.json`).

Trusted complete-byte SHA-256 verification precedes parse/publication at read-only
`/system`. The kernel is the trust anchor, not the module. Real GRUB and injected
ELF recovery, allocator exhaustion, mount failure and reboot are covered at
128/512 MiB. No archive code is executed; RAMFS recovery is independently owned.
Host serial/parallel: **265 passed, zero failed, two ignored** each. Inherited
B11/B13/B18/B26, CPU faults/paging, keyboard/VGA, growth/OOM, ATA/RostiFS and all
9,071 modeled crash cases remain covered. Old failures below are historical.

Accepted ISO: `dist\rosti_phase10b_20261016T120546Z.iso` (11096064 bytes), SHA256
`117c7b2c0a1f21dc53442a7a1c558b45b8367cb163d405d4d6ef5956596993d8`. Independently extracted production kernel SHA256:
`f292cd2e406487ead05a2b9008e0cf6bf39d145b122f7ebac160ba4d1c53386f`. Fixture features are excluded.
No local QEMU remains. Historical Phase 9.6 ISO is unchanged.

No Phase 10 deployment, VM/storage mutation, Phase 11, tag or history rewrite.
Fresh read-only inspection shows VM 103 running Phase 9.6 ISO, 512 MiB/one vCPU,
SeaBIOS/pc, no data disk; stale Phase 7 references below are historical.
Commit/push of completed Phase 10B is explicitly authorized. Unrelated `d1/`
and `scripts/b13_boot_fixture.py.backup` stay excluded and preserved.

Limits: trusted-loader/single-owner ring-0 assumptions; no hardware secure boot
or hostile-userspace isolation. Runtime heap/stack high-water is **unknown**.
The 546,228-byte import capacity bound excludes allocator overhead/fragmentation
and is not a measured peak. Guest malformed/truncated images prove digest
rejection; authenticated structural-parser rejection is covered on the host.
See `docs/PHASE10_INITRAMFS.md` for exact contracts and retained failures.

### Acceptance blocker closure

B26 now imports alloc explicitly. RAMFS cleanup compares the captured baseline
root listing, not a hardcoded empty root that wrongly rejected valid /system.
GDB injection writes/readbacks use bounded chunks. The B13 fixture masks PIC
IRQs before deliberate IF=1 entry, retaining strict flags/registers/stack-residue
markers and exact exit proof; 40/40 stress replays passed. A timed-out matrix
and its orphan-induced ten-boot failure remain preserved, not counted as PASS.

## Phase 9.6 safety prerequisites (current)

- **B11:** competing reservations now deny both ordinary and exact-slot growth
  allocation. Growth release/map failure restores growth-only ownership and
  exact accounting; blocked slots are not skipped. One-byte/order/overflow,
  independent union-oracle and real module/growth regressions cover the policy.
- **B13:** CLI/CLD and deliberate stack/argument placement establish the actual
  Rust entry contract. Naked hostile-handoff, emitted-code and ELF/GRUB fixtures
  verify it without inferring peak stack usage from a prologue.
- **B18:** bounded fallible inventory checks source spans before reads, validates
  complete mmap/module/string metadata and pins accepted buffers until reboot.
  The a.out leading size word and final partial frame are now reserved too.
  Malformed boot gates persistent storage off while independent RAMFS survives.
  Recovery mem diagnostics no longer disappear when boot RAM totals are absent.
- **B26:** borrowed backing, static errors and allocation-free validation remove
  guard-held heap allocation/destruction and fallback error allocation. All
  unpublished paging frames return on failure; retry slots are cleared and
  published maps cannot be replaced. Allocation-refusal and interleaved-owner
  retries supplement lock-watchdog and guest frame-exhaustion tests.
- **Adjacent:** permanent module/metadata/table identity aliases reject unmap;
  usable ranges beginning in growth still validate their later tail. New B13
  transport EOF/close failures cannot spin forever or skip owned-process reap.

Exact acceptance status/evidence and residual limitations are in
`docs/PHASE9_6_SAFETY_HARDENING.md`. This does not fix B09 capacity loss or broadly
close the historical trap, stack, PageMap aliasing and public-API findings below.

## Phase 9.5C unnecessary preservation transfers

- Full old-block preservation reads ran even when all live old bytes were
  supplied by an offset write. A full 8,193-byte overwrite was RED at 24 reads
  versus zero. The bounded coverage condition skips only wholly redundant reads;
  complete COW writes, CRCs, zero padding and three barriers remain unchanged.
- Three focused regressions exercise bytes, budgets, remount validation, holes,
  truncation, remaining read failures and poisoning after an earlier COW write.
  Acceptance now mandates these tests; incomplete totals cannot publish an ISO.
- C04 scan costs and C05 stranded prefixes/tails are measured but NOT FIXED.
  B11/B13/B18/B26 remain blockers. B26 also includes destruction of the consumed
  page-table Vec while the frame guard lives; moving error allocation alone is
  insufficient. See docs/PHASE9_5C_RESULTS.md for exact measurements and plans.

## Phase 9.5B volume-scaled diagnostic work (C03)

- Occupancy diagnostics scanned every data block against both inode inventories,
  even on an empty volume. The bounded-work regression was RED: 15,488 probes on
  a 128-block empty volume versus a 128-probe budget. The endpoint union sweep
  preserves the count while bounding work by metadata, not volume size.
- Three portable regressions cover empty-volume work, all 128 interleaved extents,
  and a BTreeSet oracle for 320 synthetic clipped/overlapping inventory states.
  A panic-on-I/O device enforces that diagnostics remain read-only computations.
  These synthetic states are not a claim of newly validated corruption handling.
- The host capacity-only diagnostic fixture is not a full-volume device benchmark.
  Existing crash, CRC, mount, COW, flush and capability semantics are unchanged.
  See docs/PHASE9_5_C03_RESULTS.md for measured latency and release evidence.

## Phase 9.5B read amplification

- Previously an ordinary 64-byte portable read loaded a complete 4 KiB block
  (eight sectors), even after the earlier shell batching improvement. A new
  instrumented budget regression was RED at eight versus one. Partial reads
  now use intersecting sectors and the existing scratch; complete aligned blocks
  keep read_block. No mount CRC, format, write, durability or capability change.
- The initial all-sector prototype made full-block host reads slower and was
  rejected. Its unchanged workload observations are retained, not hidden. The
  hybrid was tested with the exact original workload and an independent review.
- Shell first/second-refill failures now use call indices 0/1 rather than 0/8;
  the output prefix, error, descriptor ownership and shared-offset assertions
  are unchanged. Transfer counts now require one sector, not eight.
- Four dedicated portable regressions and a mandatory acceptance gate cover
  geometry, cross-boundary bytes, EOF and every mixed-path device failure.
  Historical safety findings in PHASE9_5_AUDIT.md remain unresolved; no claim of
  arbitrary-thread/user API soundness or physical crash safety follows.

## Phase 9.5 bounded maintenance changes

- `set_one_bit(false)` passed a zero mask length because the helper swapped
  length/value. All-bit/all-width clear regression was RED then GREEN after
  correcting the argument order and matching trait parameter names.
- Final-generation descriptor/open-record release previously incremented MAX;
  records now retire without panic/wrap. Console installation rejects exhaustion.
  Failed open-record allocation previously leaked its provisional descriptor;
  rollback restores occupancy, live counts and unpublished generation. Near-MAX,
  retired/full-record and diagnostic-counter regressions were RED then GREEN.
- `cat` read four bytes then rewound for each scalar, repeatedly loading the same
  4 KiB persistent block. A real portable-core 64-byte ASCII test was RED at 512
  sector reads and GREEN at eight. A 128-byte fixed buffer preserves output/
  rights/offset behavior with overlap at scalar boundaries; no FS heap cache.
  First and later read failures retain error reporting and descriptor cleanup.
  The exact partial-output prefix at arbitrary device failure can differ because
  the read schedule changes; it is not promised equivalent to byte-at-a-time I/O.
- Acceptance now requires the complete mandatory report matrix and exactly ten
  successful boot rows. Missing reports/nine-row regressions were RED then GREEN;
  no existing gate/check was removed or lowered. Milestone naming is 9.5.
- New host benchmark evidence cannot overwrite prior output; failure/cleanup
  contracts are tested. Generated tracked interpreter caches are untracked and
  ignored, while local copies and the unrelated initial cache are retained.

The audit explicitly records unresolved pre-existing issues, not fixes:
growth eligibility versus boot reservations/module mapping, entry stack/DF,
general error-code exception ABI, allocator lost alignment bytes, Port lifetime,
mutex guard auto-traits, ring SPSC API, PS/2 setup, page-map borrowing/effective
permissions, fatal-path locking/stack high-water, trusted namespace policy and
two-stage shell create/reopen failure. See docs/PHASE9_5_AUDIT.md for evidence,
risk and verification plans. Existing test success does not erase these findings.

## Phase 9 corrections and verification boundaries

- The first full acceptance passed ELF persistence but failed on GRUB/ISO ATA
  cache-flush completion. Reproduction captured a real `poll timeout`, not a
  checksum or mount failure. Port 0x80 is not a wall-clock delay in QEMU; the old
  4,000-read budget could expire before asynchronous writeback completed. The
  driver now permits a hard maximum of 100,000 status reads. An 8,192-busy-poll
  scripted flush regression was RED with the old budget and GREEN with the fix;
  permanently busy devices still time out. The unchanged ISO persistence checks
  passed 168/168 in three independent reproduction runs. This is an iteration
  bound, not a real-time timeout or proof of physical disk durability.
- ATA/RAM-disk statistics used unchecked `usize` increments. On i686, cumulative
  transferred bytes could overflow after 4 GiB of I/O and panic despite valid
  filesystem addresses. Transfer, error and denial counters now saturate; a
  near-address-width regression was observed RED then GREEN. Counters at their
  maximum no longer represent an exact cumulative count.
- An explicit fragmented-volume regression fills all eight test data blocks,
  deletes alternating files, advances retained generations, rejects a two-block
  extent despite four isolated free blocks, then reuses a merged deleted run
  and verifies all surviving binary data after remount. Duplicate deletion is
  rejected without freeing another file's blocks.

- The initial uncommitted RostiFS used in-place metadata, inconsistent bitmap
  geometry, unstamped free slots, invalid name/page boundaries and unrelated
  transaction generations as node lifetimes. It did not mount its own formatted
  image and failed 10 of 18 host tests. It was replaced, not declared complete:
  two COW metadata banks, independently validated roots, protected old data,
  fixed inline directories and slot-lifetime generations fix the architecture.
- CRC32C code was correct, but its draft reference tests were wrong:
  `123456789` is `e3069283` and `a` is `c1d04330`. Established vectors and real
  byte corruption tests now validate the checksum, not self-invented values.
- A draft `UnsafeCell` accessor could manufacture aliased mutable references
  through shared VFS reads. The portable core now uses fallible `RefCell`
  borrowing and contains no unsafe code. Hardware diagnostic/FS views serialize
  access to the same ATA owner instead of sharing `&mut AtaDevice` references.
- Draft crash tests hardcoded block counts while the device performed eight
  sector writes per block and skipped flush boundaries. Current tests derive
  injection points from real successful event traces, check exact old/new trees
  and data, tear sectors/root prefixes, reject writes/flushes and reorder pending
  sectors. A failed commit poisons subsequent writes until remount.
- Multiple local 4 KiB buffers and by-value filesystem construction threatened
  the 16 KiB boot stack. One instance-owned 4 KiB scratch buffer and const static
  in-place mounting avoid these buffers on the kernel stack. Host-only by-value
  constructors remain unsuitable for the boot stack.
- Shell errors after opening a descriptor leaked it (e.g. `cat` on a directory,
  failed writes/listing/removal). Commands now close only newly opened handles
  on every exit. A regression retains an unrelated handle while exercising
  all failing command paths.
- Root/source freeze now includes portable crate sources, integration tests,
  manifests and locks; newly added storage code cannot evade acceptance hashing.
  Production acceptance explicitly checks resolved Cargo features and rejects
  the deliberate fatal-fault ELF marker. Existing tests were not weakened.
- The kernel's explicit top-level workspace and a separately rooted path
  dependency produced Cargo's `multiple workspace roots` error even with an
  exclusion. The one-package kernel now uses package resolver 2; the portable
  and host test crates remain independently rooted. Failed build evidence is
  retained in `test_results/phase9/`.

Known limits are deliberate, not fixed by this release: contiguous allocation
may fail under fragmentation; old-root retention delays reuse; shell create
plus write is two commits; ordinary post-mount data reads do not revalidate the
whole-file checksum until the next mount/check. Hardware power-loss honesty,
CRC collisions, hostile concurrent host path replacement, Unicode VGA rendering
and scheduler/user-mode isolation are not proved. FORMAT.md specifies the
tested failure model. No physical power-loss safety or cryptographic integrity
claim is made.

Confirmed defects, evidence, and fixes (this session unless noted).

## Phase 8 defects found in the unfinished block layer

- Boot held a reference to the temporary `PORT_MANAGER.lock()` guard across
  the entire `kernel_main` body. ATA initialization then re-entered that same
  non-reentrant lock. PS/2 setup now has an explicit scope before acquiring ATA
  ports; retained port ownership, ISR behavior and lock ordering are preserved.
- ATA DRQ was encoded as `0x40` (DRDY) instead of `0x08`. The old scripted bus
  repeated the same incorrect value, hiding the hardware mismatch. A regression
  against the protocol bit was observed RED, then GREEN with DRQ corrected.
- The original IDENTIFY parser used only word 60 for capacity and only words
  27..36 for the model. ATA LBA28 capacity uses words 60/61; the model spans
  words 27..46. Unsupported addressing and device-fault states need explicit
  rejection rather than treating arbitrary IDENTIFY data as usable capacity.
- Acceptance hashed only the files discovered at the start and omitted target
  configuration. New source files and a changed `target.json` both falsely
  passed. New source-freeze regressions were observed RED, then GREEN after
  rediscovering source/build inputs for the final comparison.
- Acceptance copied the versioned ISO before checking source stability. A RED
  regression showed a failed source freeze still left a release-named artifact.
  The freeze check now precedes versioned publication; regression is GREEN.

Phase 8 live-I/O and complete regression results are recorded separately in
HANDOVER.md and `test_results/phase8/`; host fixtures are not hardware proof.


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
