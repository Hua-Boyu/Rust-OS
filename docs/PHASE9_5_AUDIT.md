# Phase 9.5 read-only architecture audit

## Initial evidence and change boundary

Initial HEAD `9da1d48e9c51207b51c31d8c296cf31fd080c49c`; branch created:
`maintenance/phase9-5`. The only initial untracked file was
`scripts/__pycache__/phase6_verify.cpython-311.pyc`; it is unrelated and preserved.
`git fsck --no-reflogs` exited zero with dangling objects, not corruption;
no pruning, reset or history rewrite was performed.

Before any production refactor, `test_results/phase9_5/phase9_reverification.json`
recorded an exact match of all 80 Phase 9 source/build input hashes, PASS 36/36,
and the accepted ELF/ISO SHA256. The accepted image and rollback images remain.
Read HANDOVER, NEXT_SESSION_PROMPT, ARCHITECTURE, TESTING, BUGFIXES, PROXMOX,
README and crates/rostifs/FORMAT.md. Parallel read-only audits cover the kernel,
storage and harnesses. External comparison is in MINIMAL_OS_COMPARISON.md.

Baseline instrumentation is host-only `scripts/phase9_5_bench.py`, not a change
to production behavior. Baseline PASS: six independent GRUB/QEMU runs, three
at each of 128/512 MiB, recorded in `test_results/phase9_5/baseline.json`.
Identical fixed workload consumed 520 ATA reads and 112 writes in every run;
heap remained 8,232 B, capacity 1,048,576 B, growth pages zero. Timing is host
monotonic observation including QMP/key pacing, not guest cycles or physical disk
bandwidth. Peak stack/transient allocations and separate mount latency are not
instrumented and remain unavailable, rather than estimated as measurements.

Severity: P0 immediate integrity/security risk; P1 material correctness or
resource/maintainability issue; P2 bounded cleanup or measurement gap. These
findings are evidence of specific limitations, not evidence that Phase 9 failed.

## B01 — scalar-sized cat reads amplify persistent I/O (P1)

- **Affected files/evidence:** pre-change src/fs_commands.rs:230–273 repeatedly
  reads up to four bytes and seeks back after each scalar. Portable RostiFS
  reads whole 4 KiB blocks through its shared scratch for each read request.
  The baseline's 64-byte ASCII file workload performs 520 sector reads.
- **Correctness impact:** output is correct but synchronous main-loop storage
  work can delay event consumption; no IRQ storage access is involved.
- **Memory impact:** currently four bytes local scratch; a small 128-byte bounded
  buffer would add 124 bytes, not a heap allocation or filesystem cache.
- **Performance impact:** same file block repeatedly transferred for each ASCII
  scalar. Benefit must be checked using ATA counters, not source-line reduction.
- **Proposed change:** batch cat reads in a small fixed buffer, preserve UTF-8
  scalars across chunk boundaries, escape invalid/control bytes identically,
  retain descriptor checks/offset semantics and command cleanup.
- **Regression risk:** split multibyte sequences, truncated/invalid tails,
  shared offsets, read failures; moderate but localized.
- **Verification plan:** test bounded backend-read counts on a real portable
  filesystem; exact mixed UTF-8/control/invalid data across all chunk boundaries;
  stale/rights/cleanup regressions; repeat baseline and full acceptance.

## B02 — kernel static borrows rely on main-loop ownership (P1)

- **Affected files/evidence:** src/main.rs:185–207 takes mutable references to
  static FILESYSTEM, DESCRIPTORS and BACKEND. FS_DISK initializer documents its
  unique borrow, but the neighboring static borrows lack local SAFETY comments.
- **Correctness impact:** safe under the current single entry, no reentrancy,
  main-context-only contract; future scheduling could violate it.
- **Memory impact:** none; keep large objects off the 16 KiB boot stack.
- **Performance impact:** none expected.
- **Proposed change:** document exact single-entry/lifetime/non-IRQ invariants;
  do not invent a general ownership framework during this milestone.
- **Regression risk:** documentation-only is low; changing ownership is high.
- **Verification plan:** review all IRQ callers and final diff; production build
  and unchanged static symbol budgets.

## B03 — ELF validation duplicated with unequal checks (P1)

- **Affected files/evidence:** scripts/build-proxmox-iso.py:41–62 independently
  parses ELF while scripts/validate_elf.py is the canonical validation gate.
  The builder does not enforce the full canonical BSS/segment contract.
- **Correctness impact:** standalone packaging has a weaker validation boundary;
  full acceptance still runs both and is stronger.
- **Memory impact:** host-only; no guest impact.
- **Performance impact:** not a measured kernel optimization.
- **Proposed change:** reuse canonical validation after dedicated malformed-ELF
  tests; preserve builder interface and detailed diagnostics.
- **Regression risk:** parser/API changes and callers; defer unless independently
  verified within scope.
- **Verification plan:** malformed/truncated/BSS/entry/header fixtures, unchanged
  production ELF, GRUB boot and complete acceptance.

## B04 — per-sector durability plus transaction barriers (P2)

- **Affected files/evidence:** src/storage.rs:55–57; ATA write_sector performs a
  flush for each sector; portable commit additionally flushes transaction stages.
- **Correctness impact:** conservative ordering is intentional and accepted.
- **Memory impact:** no cache is allocated.
- **Performance impact:** likely flush overhead, not quantified by current
  diagnostics (no flush command counter).
- **Proposed change:** reject batching in Phase 9.5: separating diagnostic and
  filesystem durability semantics requires a new independently fault-tested
  driver contract, not simply deleting flushes.
- **Regression risk:** high, ambiguous writes and crash ordering.
- **Verification plan:** any later batching must preserve data/metadata/root
  barriers, slow/busy/error tests and crash suites plus QEMU persistence.

## B05 — tracked interpreter caches (P2)

- **Affected files/evidence:** git ls-files scripts/__pycache__ lists five tracked
  .pyc files. .gitignore lacks an interpreter cache rule.
- **Correctness impact:** generated interpreter-specific bytes do not belong in
  reviewed release inputs; source remains authoritative.
- **Memory impact:** no guest memory impact.
- **Performance impact:** no speed claim.
- **Proposed change:** untrack those generated files while retaining local copies;
  ignore __pycache__/ and *.py[cod]. Preserve unrelated untracked cache.
- **Regression risk:** low; Python regenerates caches, acceptance uses -B.
- **Verification plan:** git cached diff contains only five cache removals and
  ignore rules; Python host and full acceptance unchanged.

## B06 — timeout is not boot latency; guest high-water metrics absent (P2)

- **Affected files/evidence:** scripts/boot_test.py:77–100 waits until timeout and
  stores time.time elapsed, not marker arrival. Existing host tests and QEMU mem
  diagnostics report retained usage, not peak transient allocations.
- **Correctness impact:** no kernel bug; risk of publishing misleading metrics.
- **Memory impact:** unmeasured peak stack/transient allocation cannot be zero.
- **Performance impact:** establish host monotonic start-to-prompt and
  Enter-to-prompt observations without labeling them kernel cycles.
- **Proposed change:** separate bounded baseline script reusing canonical owned
  media/QMP harness; mark unsupported measurements null and explain scope.
- **Regression risk:** low; no production instrumentation.
- **Verification plan:** require exact output, all-true checks, cleanup of each
  owned process, three independent runs each RAM size and unchanged inputs.

## Disposition

## B09 — allocator drops alignment prefixes and tiny suffixes (P1, deferred)

- **Affected files/evidence:** src/allocator.rs:246–265 removes the whole free
  block but only reinserts a suffix >= MIN_BLOCK. The aligned prefix is counted
  as waste but never reinserted; the allocated header records only `need`.
  :292–303 deallocation therefore cannot return those bytes.
- **Correctness impact:** valid allocation/free cycles can reduce free capacity;
  used returning to baseline is not proof that free capacity recovered.
- **Memory impact:** workload-dependent lost prefixes/tails, not quantified by
  the persistent benchmark (which does not allocate FS heap memory).
- **Performance impact:** eventual avoidable growth/OOM; no observed timing
  attribution or byte total is claimed here.
- **Proposed change:** separately test exact free-capacity restoration under
  mixed size/alignment and reclaim the entire allocation span. Defer changing
  unsafe allocator headers/ownership in this localized storage milestone.
- **Regression risk:** high; alignment, header encoding, coalescing, OOM rollback
  and real growth mappings must be proven together.
- **Verification plan:** repeated alloc/free/alignment vectors, near-capacity
  tails, coalescing, exhaustion, growth and real fsstress at both RAM sizes.

## B10 — future user boundary is not present (P1, design prerequisite)

- **Affected files/evidence:** src/gdt.rs kernel-only segments; src/interrupt.rs
  DPL0 gates and placeholder general interrupt frame; src/fd.rs:247–255 accepts
  requested rights from trusted kernel callers; src/fs_commands.rs:63–87,
  :159–166,:183–187 uses trusted direct namespace operations.
- **Correctness impact:** safe only as trusted ring-0 shell APIs. A syscall
  exposing caller-selected rights or direct VFS mutation would bypass policy.
- **Memory impact:** task stacks/maps/user-copy budgets not implemented.
- **Performance impact:** not measured; no scheduler frequency recommendation.
- **Proposed change:** design only; ELF32 native apps, explicit namespace grants,
  validated copy-user, per-task ownership, traps/fault cleanup before execution.
- **Regression risk:** high if implementation rushed; no ring0 arbitrary bytes.
- **Verification plan:** application ABI design lists host parser/policy and real
  ring3/privilege/fault/preemption gates; current descriptors are not isolation.

## B08 — single-bit clear passes arguments in the wrong order (P1)

- **Affected files/evidence:** src/utils/bits.rs:29–36 implements set_bits as
  (shift, length, value), but set_one_bit passes (shift, enabled, 1).
- **Correctness impact:** enable=true coincidentally works; enable=false builds
  a zero-length mask and does not clear the bit. Current IDT callers only set
  true, so this is a latent reusable-helper defect, not a failed boot.
- **Memory/performance impact:** none; one expression, no allocation or loops.
- **Proposed change:** pass length=1 and value=enabled, clarify trait parameter
  names to match implementation without changing positional semantics.
- **Regression risk:** low; public helper behavior becomes its stated contract.
- **Verification plan:** RED/GREEN clear and neighbor-preservation across all
  u8/u16/u32/u64 bits, existing mask/IDT/GDT tests, production/full acceptance.

## B07 — descriptor retirement and failed-open rollback (P1)

- **Affected files/evidence:** src/fd.rs:229–244 install increments without a
  retirement guard; :291–302 can allocate an open record at generation MAX;
  :435–452 last-close increments that MAX unchecked. :261–262 allocates a
  descriptor before fallible open-record allocation without rollback.
- **Correctness impact:** final-generation close can panic/wrap; an exhausted
  record pool can consume descriptor slots on failed open. These violate
  retirement/failure atomicity guarantees; no accepted ordinary test reaches
  billions of reuse cycles.
- **Memory impact:** no heap impact, but fixed slots can be lost on errors.
- **Performance impact:** saturated diagnostic counters avoid lifetime panic;
  no speed improvement claimed.
- **Proposed change:** saturate retirement on release, reject exhausted install,
  rollback just-allocated descriptor when record allocation fails; saturate
  monotonic diagnostic counters, not bounded live counts.
- **Regression risk:** slot/record generation and reference-count semantics;
  moderate, localized to descriptors.
- **Verification plan:** RED/GREEN near-MAX open/last-close/install tests,
  artificially exhausted record pool with unchanged descriptor stats, counter
  saturation, existing attenuation/shared-offset/stale/close tests and acceptance.

B01 is the selected localized performance refactor; B02 documents ownership;
B05 consolidates generated artifacts. B04 batching is deliberately rejected.
B03 and broader ownership changes remain follow-up unless separately justified.
Kernel and storage reviewers' findings are consolidated below; duplicate reports
are counted once (K05/S01/S02 -> B07, K10 -> B08, K04 -> B09,
K06 -> B10, K14/S04 -> B01, S07 -> B03).
No Phase 10 implementation, disk-format change, automatic repair, remote change,
new syscall or graphical subsystem is authorized by this maintenance work.

## Broader read-only findings (pre-existing; not silently declared fixed)

These findings arrived from the independent read-only reviews. Source references
refer to the initial checkpoint. Proposed verification is not executed evidence.
Memory/performance impacts below are qualitative unless specifically measured.

### B11 — P1: growth claims ignore competing reservations (K01)
- **Files/evidence:** src/memory/frame.rs:200–223 reserves boot/nonusable ranges,
  but :285–304 claim_growth_frame checks coverage/prior claims only;
  src/multiboot.rs:95–102 reserves modules; paging.rs:405–408,451–454 excludes
  the growth window even for module payloads.
- **Correctness:** a reserved module overlapping usable coverage in the growth
  window can be overwritten; live modules there also lack identity mapping.
- **Memory:** a corrected eligibility map may reduce available growth frames.
- **Performance:** no measured effect; reserved data must win over capacity.
- **Change:** exclude every competing reservation from growth eligibility;
  explicitly map/pin boot payloads or reject conflicting placement safely.
- **Risk:** high, contiguous growth assumptions and boot/module mappings.
- **Verify:** one-byte reserved overlaps, module placement inside/outside growth,
  payload hashes during exhaustion and real ELF/GRUB recovery. **Phase 10 blocker.**

### B12 — P1: #GP uses the wrong error-code handler signature (K02)
- **Files/evidence:** src/interrupt.rs:248,322–328 installs a no-error-code
  vector-13 handler which returns; other error-code vectors also use that ABI.
- **Correctness:** unconsumed CPU error code corrupts the iret frame; fatal
  handlers hide the return issue but still have the wrong contract.
- **Memory/performance:** no measured budget change; fault/reset risk dominates.
- **Change:** typed error-code signatures and controlled fatal #GP handling;
  preserve CPU-tested page-fault behavior.
- **Risk:** moderate, compiler trap ABI and diagnostics.
- **Verify:** real #GP/#SS/#NP fixtures, exact code/one terminal diagnostic/no
  reset loop and generated epilogue inspection; deferred, no user-mode claim.

### B13 — P1: boot stack/DF prerequisites are not established (K03)
- **Files/evidence:** src/boot.s:18–23,33–41 pushes two args before call without
  padding or cld; target.json declares 16-byte stack alignment.
- **Correctness:** callee stack alignment and direction-flag assumptions are
  not guaranteed by Multiboot; accepted boots are not general ABI proof.
- **Memory:** padding consumes a few reserved stack bytes, not a larger stack.
- **Performance:** not measured; correctness prerequisite, not assembly tuning.
- **Change:** deliberate cld/alignment padding/controlled IRQ state.
- **Risk:** moderate argument ordering/entry contract.
- **Verify:** incoming ESP/DF fixtures including DF-set handoff, assembly and
  both boot paths. Deferred rather than changing startup without new fixtures.

### B14 — P1: safe Port can outlive/move its allocator (K07)
- **Files/evidence:** src/io/ports.rs:15–21,45–48,66–69 stores allocator raw
  address without a lifetime and writes through it in Drop.
- **Correctness:** the safe abstraction permits dangling pointer use; current
  static/scoped boot callers are not evidence of general API soundness.
- **Memory:** no intentional heap use; risk is invalid memory access.
- **Performance:** no measured effect.
- **Change:** stable lifetime-encoded owner/permanent reservation tokens;
  alternatively make immovability/exclusive lifetime obligations explicit.
- **Risk:** moderate PIC/PS2/ATA reservation release semantics.
- **Verify:** compile-fail move/drop lifetime cases and reservation collisions.
  Deferred owner redesign, not claimed safe for arbitrary future callers.

### B15 — P1: guard auto-traits permit Sync for non-Sync content (K08)
- **Files/evidence:** src/utils/mutex.rs:14–20,50–59 guard holds only a reference
  to SpinMutex, which is Sync for Send T; shared guard exposes &T.
- **Correctness:** safe cross-thread access to non-Sync T is possible; existing
  single-core ownership does not justify the public auto-trait contract.
- **Memory:** marker-based correction need not allocate; layout must be checked.
- **Performance:** no expected runtime cost, unmeasured.
- **Change:** encode T's guard auto-trait requirements with a marker/constraint.
- **Risk:** low–moderate compile-time caller compatibility.
- **Verify:** positive/negative trait assertions using Cell and Sync values plus
  synchronization tests. Deferred; no SMP or scheduler exposure in this phase.

### B16 — P1: safe ring API does not enforce SPSC (K09)
- **Files/evidence:** src/kbd.rs:137–144,162–181,189–195 unconditional Sync and
  shared safe operations access non-atomic UnsafeCell bytes.
- **Correctness:** multiple producers/consumers can race; current IRQ/main
  wiring follows SPSC, but API soundness is conditional.
- **Memory:** endpoint ownership may be zero-allocation; exact layout unmeasured.
- **Performance:** not measured; avoid broad queue replacement for line count.
- **Change:** unique producer/consumer endpoints or explicitly enforced unsafe
  ownership contract; preserve loss snapshot/rejection semantics.
- **Risk:** moderate ISR/consumer overflow wiring.
- **Verify:** endpoint uniqueness/concurrency models and all ring-loss/keyboard
  regressions; deferred before any multi-consumer graphics/scheduling work.

### B17 — P1: PS/2 configuration sequence relies on inherited state (K11)
- **Files/evidence:** src/main.rs:150–153 reads configuration response from
  status port 0x64 rather than data 0x60, then sends it as a command.
- **Correctness:** interrupts/translation are not deliberately configured;
  firmware/QEMU success does not establish physical-controller correctness.
- **Memory:** no measured change; response/scancode confusion affects input.
- **Performance:** bounded setup waits would need timeout measurements.
- **Change:** tested command/data/status state machine and finite waits before
  IRQ consumption, with absent/stuck-controller recovery.
- **Risk:** hardware variability and pending replies; moderate–high.
- **Verify:** scripted port sequences, missing/busy/error controller and real
  ELF/GRUB keyboard. Existing accepted path retained; hardware limit disclosed.

### B18 — P1: boot metadata lacks fallible recovery boundary (K12)
- **Files/evidence:** src/multiboot.rs:93–100,139–145,173–193 raw spans/assertions;
  src/main.rs:66–103 no fallible boot inventory; memory/mod.rs:52–93 omits
  explicit live module mappings.
- **Correctness:** malformed boot metadata can halt before shell; valid trusted
  Multiboot acceptance is not malformed-module recovery proof.
- **Memory:** bounded module inventory and lifetime reservation required.
- **Performance:** not measured; no unbounded parser/allocation permitted.
- **Change:** checked fallible inventory and explicit physical mapping/lifetime.
- **Risk:** high rejection policy and boot ownership.
- **Verify:** malformed/truncated/count/range vectors, missing/corrupt module
  ELF/GRUB with independent shell. **Phase 10 prerequisite**, not implemented.

### B19 — P1: page-map aliases and future effective permissions (K13)
- **Files/evidence:** src/memory/mod.rs:160–181 returns static shared PageMap
  while growth independently forms mutable access; paging.rs:194–208 sets USER
  only in PTE, forces PRESENT; :143–152 reports only PTE flags.
- **Correctness:** retained shared views can cross mutation; future user mappings
  would report permissions not granted by PDE. Current supervisor use only.
- **Memory:** owner/scoped views and task table budgets not measured.
- **Performance:** no claimed benefit.
- **Change:** scoped/snapshot access and explicit PDE/PTE effective permissions
  before exposing user mappings; do not casually mark kernel PDEs USER.
- **Risk:** high for mapping/heap ownership, moderate diagnostics.
- **Verify:** lifetime/effective-permission tests, growth regressions and later
  CPU user-denial tests; no working user boundary claimed.

### B20 — P1: fatal path and stack headroom need stronger contracts (K15)
- **Files/evidence:** src/main.rs:36–41 panic re-locks VGA and busy-spins;
  io/vga.rs:173 formats under nonreentrant lock; boot stack is unguarded 16 KiB;
  interrupt.rs:100,131 trap gates allow nested activity.
- **Correctness:** panic-under-VGA can deadlock; unmeasured nested stack remains
  a risk, not a proved overflow in accepted workloads.
- **Memory:** stack high-water and canary/guard overhead unavailable.
- **Performance:** terminal busy-spin wastes CPU; no idle-loop regression.
- **Change:** IRQ-disabled lockfree serial fatal halt, optional try-lock VGA;
  separately establish stack watermark/guard before archive/crypto call growth.
- **Risk:** moderate diagnostic and linker/exception contracts.
- **Verify:** panic-under-lock fixture, bounded terminal diagnostics, stack
  checks across mount/stress/fault; deferred startup/fatal-path changes.

### B21 — P1: create succeeds before descriptor-full reopen fails (S03)
- **Files/evidence:** src/fs_commands.rs:113–118 creates missing file then uses
  fallible reopen; :128–132 rollback handles only later replace failure.
- **Correctness:** table-full `write new data` can leave a new empty file;
  persistent create is already a separate acknowledged transaction.
- **Memory:** can retain an unintended node; no file payload growth required.
- **Performance:** no measured effect.
- **Change:** preflight descriptor capacity or explicitly include reopen in
  command-owned creation failure handling, without claiming disk-error rollback.
- **Risk:** moderate ambiguous persistent outcomes/poisoned cleanup.
- **Verify:** full table missing-file test, unchanged RAM/node accounting and
  preexisting handles. Deferred semantic change; existing two-commit contract kept.

### B22 — P2: Unicode C1 controls pass current output policy (S05)
- **Files/evidence:** initial fs_commands.rs:258–265 checks first UTF8 byte,
  not decoded scalar; e.g. U+009B can reach sink.
- **Correctness:** terminal hygiene gap; not a memory-corruption claim.
- **Memory/performance:** none expected; not measured.
- **Change:** scalar is_control policy with explicit newline/tab exceptions;
  byte escaping for rejected scalars. Not bundled into exact-output refactor.
- **Risk:** low but observable output change.
- **Verify:** U+0085/U+009B plus ordinary Unicode/ASCII controls/binary vectors.

### B23 — P1: shared harness close failure can skip owned reap (S06)
- **Files/evidence:** scripts/fs_test.py:393–404 closes transports before owned
  process kill/wait; exceptions skip reap. RostiFS has nested compensation.
- **Correctness:** orphaned local QEMU can invalidate subsequent isolation.
- **Memory/performance:** host emulator resource leak, no guest implementation
  effect; no measured resource total.
- **Change:** unconditional finally reap preserving live-mode nontermination;
  benchmark adds its own guaranteed cleanup before PASS.
- **Risk:** moderate local/live distinction; never kill a remote guest.
- **Verify:** mocked stream/socket/live close failures and process exit evidence;
  all real final acceptance processes independently enumerated after completion.

### B24 — P1: acceptance discovers reports but does not require all (S08)
- **Files/evidence:** initial phase6_verify.py:128–131 counts CSV without exact
  ten rows; :158–172 accepts absent reports/default PASS/no-check objects.
- **Correctness:** successful subprocess alone can mask missing evidence.
- **Memory/performance:** host-only; no speed or resident-memory change.
- **Change:** mandatory per-gate artifact contracts, exact row totals and
  explicit PASS/nonempty all-true schemas; keep source freeze/publication order.
- **Risk:** moderate differing report schemas and fixture updates.
- **Verify:** missing/{}/missing-status/empty/false rows and nine/failed boots
  prohibit publication; independently validate final nested reports and totals.

### B25 — P2: uptime is a wrapping counter, not indefinitely monotonic
- **Files/evidence:** src/timer.rs:35–47 AtomicU32 tick count can wrap.
- **Correctness:** very-long-run uptime semantics misleading, not boot failure.
- **Memory:** extended counter could require extra synchronization; unmeasured.
- **Performance:** no need to change PIT frequency.
- **Change:** document wrapping or introduce reviewed extension only if needed.
- **Risk:** low documentation, moderate atomic rollover implementation.
- **Verify:** boundary vectors and real timer progression; deferred implementation.

### B26 — P1: memory-prepare error allocates while frame guard lives
- **Files/evidence:** src/memory/mod.rs:111–120 creates error Vec under frame
  guard; lock order is otherwise heap -> frame.
- **Correctness:** error allocation that triggers heap growth could reenter
  frame lock. Current small boot error normally fits initial heap, not proof.
- **Memory:** unexpected error-path allocation; no measured peak.
- **Performance:** potential deadlock, not normal-path contention measurement.
- **Change:** return a scalar status after releasing guard, then format/allocate.
- **Risk:** low–moderate error diagnostics/API signature.
- **Verify:** force table exhaustion with heap exhaustion and verify bounded
  recovery/no guard-held allocation. Deferred to boot-memory prerequisite work.

## Final disposition and acceptance

Programmatically deduplicated **26 findings: P0 0, P1 21, P2 5**. Severity
describes the present supported single-owner/trusted-GRUB environment; unsafe
API findings remain real prerequisites, not proof of general soundness.
**Seven addressed:** B01 bounded cat batching, B02 local ownership invariants
(documentation, not a new owner type), B05 generated-cache consolidation,
B06 honest monotonic host observations/unsupported-metric nulls, B07 descriptor
retirement/rollback/saturating diagnostics, B08 bit-clear regression, B24
mandatory invocation-owned evidence. **One rejected:** B04 flush removal.
**Eighteen remain deferred**, with per-finding evidence/risks/tests above.
No assertion that those APIs are now safe for arbitrary threads/user programs.

Full acceptance completed **37/37 PASS** in
`test_results/phase9_5/acceptance_20261013T221730Z_ibgi0pg6/acceptance.json`;
82 input hashes and 52 nested reports independently verified. No new unsafe
operation, storage-format/transaction change, lock order, IRQ storage path or
remote write was introduced. Source diffs preserve portable core, ATA, storage,
boot assembly, memory mappings, linker and target configuration. Final same-host
old/new replay retains exact sector-count benefit and unchanged heap budgets;
512 MiB host boot is 7.420% slower and explicitly disclosed without attribution.
All 10 requested documents exist; design proposals are not implementation.

Phase 10 may proceed only by addressing boot/module/growth lifetime blockers
B11/B18/B26 first, while retaining independent recovery. Broader trap/stack,
Port/guard/ring and mapping/fatal-path issues remain before untrusted execution.
