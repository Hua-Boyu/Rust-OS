# Phase 11 — verified dependency plan and privilege design

## Status and source

IN PROGRESS; **not a Phase 11 release**. Initial HEAD verified as
`def677fac8ca662e45ad4fb40c9ddd18bfe86bd8` on `maintenance/phase10`.
This is the expected documentation/evidence successor of accepted source
`449ed434ed5dbf1518b99821178a5fcd1d343b75`, not an unexplained implementation.
Historical acceptance is `test_results/phase10b/acceptance_20261016T120546Z_psboeekn/acceptance.json`.
Its PASS 53/53, host 265, initramfs 56 scenarios / 3379 checks are historical,
not new Phase 11 execution. A fresh unchanged host run also passed 265 tests.

## Discovered architecture

- `src/boot.s`: Multiboot v1, CLI/CLD, aligned 16 KiB BSS kernel stack,
  preserved EAX/EBX, eight bytes padding then two arguments before CALL.
  Do not modify the accepted B13 entry contract.
- `src/gdt.rs`: three descriptors only: null, DPL0 code 0x08, DPL0 data
  0x10. Heap-allocated leaked GDT. No user descriptors, TSS or LTR.
- `src/interrupt.rs`: 256 IDT entries, DPL0; PIC remapped 0x20/0x28,
  only PIT/keyboard unmasked. IRQ handlers do not allocate/touch VFS/VGA locks.
  Frame placeholder is 48 bytes, not an explicit i686 CPU frame. GP handler
  lacks a CPU error-code contract and returns; PF halts. Other error-code
  exceptions use no-error signatures. These are blockers to user execution.
- `src/timer.rs`: 100 Hz PIT, atomic wrapping tick counter; no scheduler.
- `src/memory/paging.rs`: non-PAE 4 KiB two-level identity paging.
  All initial PDEs/PTEs use 0x3: present/writable/supervisor. Null and
  8..14 MiB growth holes absent. The window follows usable RAM (up to 4 GiB),
  not the 256 MiB frame allocator cap. All holes/MMIO within the identity
  window are mapped supervisor, not automatically granted user access.
- Kernel text/data/BSS, bootstrap stack/heap, GDT/IDT, VGA, module/boot metadata,
  page directory/tables, growth heap and physical aliases are supervisor.
  CR0.PG and WP enabled after IDT. No PAE/NX; readonly does NOT mean nonexecute.
- `src/memory/mod.rs`: global map shared-reference API can survive independent
  mutable growth access (B19). Borrow must not survive any allocation/growth.
  This is an unresolved Rust aliasing boundary, not solved by CPU permissions.
- Frame reservations/boot pins and growth rollback are inherited Phase 9.6
  contracts. Heap -> frame is the only allowed lock order. Do not allocate or
  destroy heap-backed state while holding a frame guard.
- `src/fd.rs`: fixed generational descriptor/open-record tables, attenuated
  rights, shared offsets and explicit last-close invalidation. Currently the
  shell owns its table; do not give users the shell's descriptor namespace.
- `src/fs/{vfs,mounted,archive,rosti}.rs`, `src/system_image.rs`: RAMFS recovery,
  pinned read-only trusted `/system`, portable RostiFS v1. No guest ELF parser
  or executable loader. `scripts/validate_elf.py` validates the kernel image,
  NOT a user executable. Trust digest authenticates bytes, not memory safety.

## Critical answer and first bounded implementation

With the discovered boot mappings, a CPL3 access cannot read/write/fetch any
present privileged identity page: both levels have U/S clear. This is static
inspection, **not yet CPU CPL3 proof**. There is no CPL3 launch path today.

B19 diagnostic bug at recovered HEAD: `permissions()` reported only the PTE,
ignoring PDE U/S, R/W and present. `map()` accepted `user=true` without promoting
the PDE, so it could report access the CPU denies. It silently forced present for a
`present=false` request. Do NOT fix this by indiscriminately setting PDE.USER.
The first TDD slice now computes effective two-level flags, fails closed on
unsupported user mappings and nonpresent requests before allocation/mutation,
and proves existing supervisor identity maps at both window sizes on the host.
This deliberately keeps user execution disabled until owned mappings exist.
It does not close all B19 aliasing findings or complete milestone 11A.

## Dependency graph (mandatory ordering)

```text
Recovered source + historical evidence + tools
   |
   v
11A.0 effective PDE/PTE permissions + refuse unowned USER requests [first slice]
   |
   v
11A.1 scoped map snapshots / exclusive mutation, physical ownership tokens
   |
   v
11A.2 owned user virtual arena + transaction/rollback + separate guarded stacks
   |
   v
11A.3 static GDT/TSS + explicit error/no-error interrupt assembly contract
   |
   v
11A.4 CPU CPL3 isolation/fault/selector tests at 128 and 512 MiB
   |       STOP if any boundary fails; do not add ELF/syscalls
   v
11B synthetic one-context IRET entry + controlled completion + shell continuation
   |
   v
11C bounded versioned syscall ABI using existing capabilities
   |
   v
11D pure owned ELF32 load plan -> transactional privileged publication
   |
   v
11E process lifecycle/identity/cleanup and repeated launch/fault recovery
   |
   v
11F mandatory phase6_verify gates + inherited regressions + independent review
```

## Proposed memory map (not implemented; reservations must be validated)

```text
Virtual                  CPL0                     CPL3
0x00000000               absent                   absent
0x00001000..RAM end       supervisor identity      no read/write/fetch
  kernel/boot/heap/MMIO   permanent/pinned          never USER
0x00800000..0x00e00000    supervisor heap growth    never USER
0x40000000..0x40400000    proposed user arena       only owned published pages
  code                   readable, kernel copy    user read/execute, !write
  data                   readable/writable        user read/write (NX unavailable)
  guard                  absent                   absent
  user stack             owned 16 KiB proposed    user read/write
separate supervisor      transition stack         never USER
  guard + 16 KiB         TSS.ss0=0x10, esp0=top
```

The arena is above both tested RAM sizes but cannot blindly be assumed absent:
reject conflicts with the actual window (including large-RAM configurations),
boot pins and existing entries. A future owned mapping API must permit a bounded
nonidentity arena through the EXISTING PageMap, with checked frame ownership,
U/S at both levels and exact removal/restoration. Kernel physical aliases stay
supervisor. No public raw frame mapping may manufacture ownership. No duplicate
page-table manager. Audit 4 KiB-page mode and relevant CR4 state explicitly.

## Proposed privilege frame and continuation (not implemented)

Selectors: retain kernel CS=0x08/DS=0x10; proposed user CS=0x1b/DS=0x23;
TSS=0x28 (available 32-bit TSS, limit 103, I/O bitmap offset 104 beyond limit).
TSS.esp0 points to a checked, kernel-owned transition stack; SS0=0x10.
No hardware task switch. IOPL=0; VM/NT cleared, EFLAGS bit1 set, IF deliberately
chosen. User DS/ES/FS/GS installed before IRET; CS/SS and entry/stack bounds
validated while still on a valid CPL0 stack. CPL must be read, not inferred.

```text
kernel shell -> save kernel-owned continuation (callee-saved regs, ESP, flags)
             -> prepare TSS + mappings + canonical user frame
initial IRET: [EIP, CS, EFLAGS, user ESP, user SS] (five u32 words at final ESP)
CPL3 -> CPU stack switch via TSS -> [optional error, EIP, CS, EFLAGS, ESP, SS]
entry stub -> save GPRs/segments, CLD, load kernel data selectors, bounded handler
normal trap -> restore saved state -> IRETD to same user context
exit/fault -> mark completion -> restore saved kernel continuation explicitly
          -> return from launch on original stack -> reclaim -> shell
```

Do not IRET to a fabricated old Rust frame. Exit/fault is a nonlocal assembly
continuation with a documented compiler ABI, no skipped Rust-owned destructors,
no live map/VFS/heap guards, no stack release while CPU/TSS references it.
Normalize only error-code vectors correctly (8,10,11,12,13,14,17 and supported
newer vectors). Detect origin via saved CS.RPL, not PF error.user alone. Every
handler reachable during CPL3 must preserve segment state and normal GPRs.
Check actual emitted i686 assembly, not a host mirror only. Kernel-origin faults
remain fatal/lockfree, not mistaken for process failures. Invalid initial IRET
or selectors fail validation; an unexpected kernel exception is not recovered
as an arbitrary user failure. NMI/double-fault containment needs explicit review.

## Proposed syscall ABI v1 (not active)

Dedicated DPL3 32-bit interrupt gate 0x80, all other gates DPL0. Interrupt gate
keeps the single-owner handler nonreentrant; restore IF only at safe return.
EAX number (0 exit, 1 write); EBX first arg, ECX second, EDX third. EAX signed
result: nonnegative success, negative fixed errors (EINVAL=22, EFAULT=14,
EBADF=9, EACCES=13, ENOSYS=38, EBUSY=16). Preserve other registers/segments.
ABI v1 is fixed for the first fixtures; unsupported versions rejected at launch.
Max copy/write 4096 bytes, bounded kernel scratch (not VFS raw user pointers).
Check running identity, origin CPL3 and syscall number first; check owned
process-local descriptor and existing Rights.WRITE before touching resources;
check checked-add range and every effective user page before copy. Zero-length
valid request performs no copy; max length accepted, max+1 rejected. Keep
mapping stable during the bounded copy. No physical addresses/kernel pointers.
File read is deferred until safe owned descriptors/copy-out are reviewed.
Repeated exit/stale identities rejected; process cannot close shell-owned slots.
Validate the full register-width handle before any u8 conversion: a value such
as 257 must not truncate to descriptor 1. Test all register-width bounds before
calling the existing fixed-table API, including stale cross-launch identities.
Console byte output must not silently expand capabilities or permit kernel code
execution. Define partial-write/error policy in ABI tests before implementation.

## Proposed ELF32 subset (not active)

Pure byte parser produces bounded owned plan, independent of physical memory.
Require ELF32 LE version1, ET_EXEC/EM_386, 52-byte ELF and 32-byte PH headers,
1..8 headers, <=64 KiB file, <=64 owned user pages (including stacks, subject
to measured budget review). PT_LOAD only plus explicitly allowed nonexecuting
metadata; reject PT_INTERP/PT_DYNAMIC, unsupported relocations, unknown required
features, W+X flags, malformed/duplicate/overlapping rounded page spans.
Checked full-width offsets/sizes; filesz<=memsz, align=0/1 or bounded power of
two with congruent offsets/addresses; entry in file-backed executable user code.
Strict fixed addresses within approved arena, zero BSS before publication.
Non-PAE cannot enforce NX on data/stack: reject ELF W+X but do not claim hardware
W^X. Strong hardware W^X would need a separately reviewed PAE/NX milestone.
Validate whole plan before allocation, own all frames transactionally, copy/zero
through supervisor aliases, publish only after all stages succeed, rollback
only owned allocations. `/system` file/archive limits and digest fixture must
be updated reproducibly, not bypassed to make a program load.

## Lifecycle and test obligations

Created -> Loading -> Ready -> Running -> Exited/Faulted; one foreground owner,
opaque nonwrapping identity, no scheduler/multiple runnable tasks. Failure drops
unpublished resources; finished context loses CPU/TSS references before cleanup.
No persistent format/storage mutation or capability escalation. Frame counters,
owned mappings, descriptor counts and RAMFS/system content must be checked both
before/after, including repeated launches, fault/reboot, OOM and partial rollback.

Add each real milestone's mandatory gates to `scripts/phase6_verify.py` with
RED/GREEN harness regressions. Preserve its nonblocking OS lock and all inherited
rows. A host permission model is not a CPU denial oracle. Required final guests:
normal entry/exit/repeat, invalid/oversize ELF, supervisor read/write/fetch,
privileged instruction, invalid syscall/pointer, stale rights, stack overrun,
allocation failure, rollback, reboot after fault, RAMFS recovery, readonly system,
persistence; sequential 128/512 MiB and inherited ELF/GRUB paths. Keep independent
positive and negative outcomes, exact matrices, cleanup assertions, frozen-source
membership+hashes and independently extracted artifacts. Preserve failed evidence.

## Resource and release boundaries

Compare loaded/initialized/static bytes against accepted Phase 10B sections;
record GDT/TSS/stacks/frame budgets and actual timings separately. No claimed
peak stack/heap without measurements; PIT granularity is 10 ms. No optimization
before correctness. No automatic Phase12, push, branch, deploy or VM mutation.
Remote protection status is unknown; local policy shows this maintenance branch
tracks origin, and no isolation requirement justifies another branch. Existing
commits and immutable accepted media provide rollback without rewriting history.

## Read-only prerequisite audit follow-up

Two independent source audits of initial HEAD confirmed the outstanding B19
and trap-ABI blockers; these are not a passing review of complete Phase11.
The narrow permission change received a separate no-blocker review, with a
nonblocking suggestion to expand exact-five harness negative fixtures. Do not
alter frozen inputs merely to apply that suggestion during acceptance.

Additional next-slice obligations verified in source:

- A callback receiving `&PageMap` is not automatically a safe replacement for
  `page_map_ref`: its body can allocate and reenter growth. Prefer scalar/owned
  query results and nonescaping borrows; prove all reentrant mutation paths and
  reject retained references. Avoid adding a map mutex around an allocating
  callback that can reacquire itself through heap growth.
- Raw `PageMap::map` still takes numeric physical frames, not ownership tokens;
  it can map physical frame zero or recreate virtual page zero. Current heap
  callers do neither, but the API is not a user-mapping foundation. Reject
  reserved/null aliases and prove frame ownership before introducing USER maps.
- Ordinary frame free protects allocation history, not arbitrary kernel-object
  ownership. A future process must retain a private frame ledger and never free
  page-table frames/boot pins or payloads referenced by a running CPU context.
- B09 allocator alignment-prefix/tiny-tail loss is still present. Process
  cleanup must compare actual free capacity/largest block, not just used/live
  counters; frame-backed process storage cannot claim to solve generic heap loss.
- `FdTable::open` accepts a trusted kernel-selected rights mask; it is NOT an
  untrusted grant authority. `fd.write` is file-only: console syscall writes
  need an explicit existing-rights/kind-checked console path, not a bypass.
  Numeric u8 FD slots alone do not prevent stale cross-launch references;
  bind syscall-visible handles to the running nonwrapping process identity.
- Inherited Port lifetime, SpinMutexGuard auto-traits and keyboard SPSC API
  findings remain bounded by current single-CPU/main-loop usage, not generally
  repaired here. Do not expose these APIs to users or add concurrent consumers.

Source references: `src/memory/mod.rs` static map publication/reference/growth;
`src/memory/paging.rs` raw map/unmap; `src/allocator.rs` allocation/deallocation;
`src/fd.rs:250-258,336-388`; `docs/PHASE9_5_AUDIT.md` B09/B12/B14–B20.
No compiler-emitted IRQ segment/DF preservation was established by those
architecture audits; actual emitted-code and CPU fixtures remain required.

For the later supervisor-fetch guest, U/S still prevents CPL3 instruction
fetch from supervisor mappings even without NX. Do not require PF error bit4
to identify that fetch in this non-PAE mode: validate the deliberately selected
target/CR2, saved CS.RPL=3, protection/user bits, supervisor PDE/PTE values,
valid TSS transition-stack bounds and independent kernel/shell recovery.
Conversely, writable user data/stack remain executable without NX; an ELF
flag policy cannot turn that architectural limitation into hardware W^X.

## Verified first prerequisite checkpoint

Implementation `d6d04c5dececf0dbf78c27e2e71760a2084786d4`; independent four-file
diff review has no blockers and exact raw source hashes match. Three behavior
RED/GREEN cycles retained, host270/0/2 ignored serial+parallel, harness37 pass.
Canonical run `test_results/phase11/acceptance_20261016T154710Z_q3u90_53/acceptance.json`
PASS54/54, actual exit0, all inherited gates retained. Independent closeout
rediscovered135 frozen inputs and verified ISO-extracted kernel/archive plus
final cleanup. Loaded sections+720 bytes, static span unchanged; no user process,
TSS or transition-stack resources implemented. This is 11A.0 only, not full11A
or Phase11 acceptance. Resume at11A.1 ownership, not at ELF/syscall execution.
