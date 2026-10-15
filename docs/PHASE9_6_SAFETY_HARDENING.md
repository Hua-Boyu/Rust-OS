# Phase 9.6 — kernel safety hardening

## Release state

**Phase 9.6 acceptance: PASS 47/47 (final, source-frozen). Phase 10 is
unblocked and authorized; implementation has not started.**

Starting HEAD: `17de9fd12d31e60f7f3dcaef726f4e579871d4dd`, branch
`maintenance/phase9-5b`. Contrary to the handover's clean-tree expectation, the
first fresh status found existing Phase 9.6 source, tests and an initial review
report. Those changes and all historical evidence were recovered, reviewed and
continued, not reset or represented as a clean start. Git fsck exited zero with
dangling objects; no pruning or history rewrite occurred.

Historical acceptance remains immutable:
`test_results/phase9_5/acceptance_20261014T142055Z_qg7d7qid/acceptance.json`.
The accepted Phase 9.5C ISO still hashes to
`5294625001799bfb5bdac7d6c01d95f7332b1e0255dc65927a1aff2c900e3331`;
the retained kernel hashes to
`0a5046e9d05d3642cc5876335372d298ba1bc703064774d8f0e3e972072c3248`.

This milestone implements no initramfs, image authentication, applications,
scheduler, syscalls, userspace isolation, networking or GUI. RostiFS wire format
v1, 4 KiB blocks, metadata, CRC32C, COW, retained roots, capability checks and
transaction/flush ordering are unchanged. C04/C05 optimizations remain deferred.

## B11 — reservation precedence and growth ownership

Original defect: growth claims checked usable coverage/history, but did not deny
competing firmware or boot reservations. A growth-window reservation was already
absent from the ordinary free pool, so removing free bits alone could not fix it.

`src/memory/frame.rs` now distinguishes complete usable coverage, competing
reservation denial, ordinary free frames, allocation history and live growth
claims. The precedence is:

1. No complete usable frame: never allocatable.
2. Any overlapping nonusable/kernel/null/VGA/boot/bootstrap span denies allocation.
3. Growth's own reservation excludes ordinary/page-table allocation but is not
   permission to override any denial in step 2.
4. A live claim excludes another claim. Release/failed-map rollback restores only
   growth-reserved capacity, never the ordinary free pool.

One-byte overlaps deny a complete frame, independent of input order. Invalid
usable arithmetic contributes no capacity; overflowing nonusable arithmetic is
conservatively denied to the managed end. Explicit reversed reservations fail
closed. The exact-address growth API never searches beyond a blocked slot: this
preserves the contiguous identity-mapped heap contract and produces safe OOM.
The frame bitmap cap remains 256 MiB, distinct from the larger paging window.

Tests: `tests_kernel/src/b11_frame_tests.rs` includes order/overlap/partial-frame,
address/overflow, explicit-span union oracle, release/retry, duplicate release,
ordinary-pool isolation and accounting regressions. Historical RED/GREEN reports
are `test_results/phase9_6/b11*.json`. Fresh focused host tests passed 12/12;
four ELF guests passed accepted-module preservation and blocked-growth tests at
128/512 MiB in `b11_continuation/boot_metadata_cafsno87/report.json`.
Commit: `f12d1ced9dd26e8ed60009e75c4814c3245f67f3`.

## B13 — actual assembly-to-Rust contract

Original defect: `_start` inherited DF and did not deliberately establish its
stack contract before pushing the two Multiboot arguments.

`src/boot.s` executes CLI first, clears DF, installs its own 16-byte-aligned
16 KiB BSS stack, reserves eight bytes, pushes EBX then EAX and calls the
`unsafe extern "C"` entry. EAX/EBX are preserved until their arguments are
installed. Pre-CALL ESP is zero modulo 16; raw callee ESP is 12 modulo 16 after
the return address is pushed. The Multiboot header, flags, checksum and entry
symbol are preserved. No larger stack was introduced.

The custom soft-float `i686-unknown-none` target advertises S128, but an actual
compiler-generated ordinary C caller only enforces four-byte alignment. The
bootstrap's sixteen-byte pre-CALL alignment is an explicit stronger guarantee,
not a claim that all subsequent generated C calls have that alignment. IDT load
later enables maskable interrupts; CLI is not protection against NMI or evidence
that all early initialization remains interrupt-disabled.

The isolated fixture links the production assembly. A naked observer verifies
raw ESP, IF/DF, registers and argument order for all sixteen incoming ESP
residues, with DF set and an STI-shadow handoff. Linked opcodes and generated
caller assembly are inspected. Fresh four-guest ELF fixture/production tests
passed at both RAM sizes; separate GRUB entry/paging smoke passed both sizes.
See `b13_continuation/report.json` and `b13_grub_continuation/report.json` under
`test_results/phase9_6`. The helper also has deterministic EOF and transport-close
failure regressions; closing a transport cannot bypass owned-process reap.
Commit: `53e27fb5c71aff408ef13f4945ace1f4da64e69f`.

## B18 — bounded fallible boot inventory and lifetime

Original defect: production boot followed raw pointers/assertions without a
complete fallible inventory boundary, and live module mappings/lifetimes were
not a deliberate contract.

`src/boot_inventory.rs` checks magic, flags and every address/length before its
source callback. Root/header and mmap reads are restricted to conventional RAM
`[4096, 0xA0000)` before a RAM map can be trusted. The memory map is bounded to
128 records / 32 KiB, module descriptors to 32, and each accessed string to 4096
bytes including its terminator. Variable record sizes, trailing truncation,
physical arithmetic, module tables/ranges/overlaps, late metadata overlaps,
optional metadata and all three VBE-owned spans are checked. Allocation uses
fallible pre-reservation. Legacy raw BootInfo methods are host-test-only.

After the bootstrap map, pointed spans must fit described usable RAM and avoid
competing nonusable bytes, the kernel and the heap-growth window. VGA text
framebuffer metadata is accepted only within the known VGA aperture; arbitrary
graphics framebuffers and unbounded BIOS configuration tables are rejected.
Missing optional modules remain ordinary boot, not an error.

Independent review found the a.out symbol reservation omitted its leading size
word. It now checked-adds four bytes and validates the reserved field. Two new
independent wire regressions caught the released partial tail frame and final
four-byte growth/firmware intersections before the correction. Existing full-
width arithmetic tests retain their coverage with the corrected format oracle.

Accepted metadata/module spans become synthetic type-2 reservations before any
page-table frame allocation. PageMap owns page-rounded permanent pins, checks
their mappings, and refuses to unmap their identity aliases. Directory/table
identity aliases are also protected, including runtime-created tables. Accepted
module payloads outside growth remain supervisor identity-mapped and reserved
until reboot. No contents are executed or imported. **No boot reservation is
reclaimed in Phase 9.6.** Dropping copied inventories does not release physical
pins. Phase 10 must retain sanitized module descriptors before their local Vec
is dropped; it must not resurrect the old unchecked BootInfo dereferences.

Placements intersecting `[0x800000, 0xE00000)` are explicitly rejected rather
than silently skipped, relocated, or made growth-eligible. The parser runs with
paging disabled and flat segments, not through a separately fault-safe early
mapping. It relies on readable conventional RAM and truthful loader/firmware RAM
backing; arithmetic checks cannot defend against malicious firmware or perform
fault-safe physical probing. These are explicit compatibility/trust limits.

Rejection records an atomic first-error latch before shell dispatch. ATA probe,
RostiFS mount and raw shell writes are gated off; RAMFS and the bounded BSS heap
remain independent. Recovery `mem` reports actual runtime counters even without
a validated RAM map. The new guest fixtures attach exclusively-created owned
media, refuse a raw write, exercise RAMFS create/read/delete and bootstrap-only
OOM, terminate the owned guest, then require an unchanged whole-image hash.
Fresh focused rejected-magic and page-table-exhaustion guests pass in
`rejected_recovery_green/boot_metadata_8wu6js9m/report.json`; the initial missing
recovery diagnostics failure is retained, not relabeled PASS.

## B26 — preparation, destruction and rollback

Original defect: error Vec allocation and consumed page-table Vec destruction
could occur under FRAME_ALLOC, opposing heap-growth's heap -> frame ordering.

Preparation allocates pin/table backing fallibly before the guard. The builder
borrows both Vecs; failure leaves backing with the caller, success transfers it
without allocation. Guards end before backing destruction and error handling.
Unpublished validation failures return all owned paging frames, then unlock
before PageMap destruction. A published map rejects reinitialization before any
frame allocator reset.

Review also exposed stale freed addresses retained in failed builder backing.
The builder now requires zeroed length-1024 backing, clears each returned slot
on rollback, and supports a retry without freeing an interleaved owner's frames.
Growth checks for a PageMap before claiming; map rejection restores growth-only
ownership and leaves an existing PTE unchanged.

The final preparation API returns `Result<u64, &'static str>`. Required regions
and first-missing validation are streamed without allocations. Pin/table reserve
failure returns a static diagnostic, never a fallback allocating Vec. Allocator-
refusal tests separately exercise both backing reservations and prove validation
needs only those two fallible unlocked allocations. The production validation
also checks usable tails whose records begin inside the growth window; only
individual growth pages, not the complete record, are omitted.

`tests_b26` is an independent host crate with an owner-thread heap watchdog,
allocation refusal controls, directory/partial exhaustion, validation rollback,
reprepare, growth conflict/missing map and backing retry tests. The watchdog is
thread-local so unrelated parallel-test allocations cannot masquerade as owner
lock inversion. The host-only page-table mirror allocates; partial-build probes
explicitly filter mirror-only layouts, while directory exhaustion watches every
owner heap operation. Refusal/validation allocation counts are separate tests.
Guest frame exhaustion leaves paging disabled, returns both acquired frames and
reaches the shell with zero live paging frames. No guest heap high-water claim
is inferred from these host controls.

## Review, acceptance and artifacts

The original independent review is retained as
`test_results/phase9_6/review_current.json` (three blocking findings, not a PASS).
B11/B13 static review passed in `review_b11_b13.json`; the GRUB fixture
repack/scenario review passed in `review_grub_fixture.json`. All three findings
were closed in source and confirmed by the final integrated review
`test_results/phase9_6/review_final.json` (passed=true, prior findings
CURRENT-R1/R2/R3 each `fixed_by_static_inspection` with evidence lines
re-verified against the live source). The runner includes mandatory
B11/B18/B26 host families, B13 host/privileged proof, and the 44-scenario metadata
ELF/GRUB x 128/512 MiB matrix, in addition to all inherited acceptance gates.
The expanded metadata matrix has a bounded 1800-second orchestration budget;
per-guest deadlines, ATA polls and filesystem checks were not weakened.

Official command: `python -B scripts/phase6_verify.py`, notified background,
one QEMU owner at a time, source/build inputs frozen. Interpreter: Python
3.11.15; compiler: rustc 1.101.0-nightly (1d81eb4ad 2026-10-07).

**Final acceptance: PASS 47/47 gates, `test_results/phase9_6/acceptance_20261015T070148Z_tg2yx8i8/acceptance.json` (timestamp 20261015T070148Z).** Host 204, B11 12, B18 38, B26 9, RostiFS host 23 + tools 4 + read 4 + write 3, B13 host 3 + QEMU 4, boot-metadata 53 (44 scenarios), ELF 8, boot 128/512 10+10, paging 20, fault 2+2, ISO paging 2; all block/VFS and RostiFS cross-reboot matrices PASS with zero failures. 102 nested reports, all nonempty; all 84 owned-QEMU reports record `owned_qemu_exited: true`. All 111 frozen source hashes re-verified byte-for-byte against the live worktree. ISO `dist/rosti_phase9_6_20261015T070148Z.iso` (10,401,792 bytes) SHA256 `e840439338360710b775c06e489c4bc8b1bb312fc9a545d3cb0917fc9c1821ff`; extracted kernel SHA256 `8a72342b4afc14e2d6f87c8758aea2869963c4dabea4e14dd22a5f3c149a7fec`. The earlier stopped attempt `acceptance_20261015T064712Z_klfznt_b` (synthetic GRUB-fixture layout failure) is retained separately, not relabeled.

## Residual limitations

B09 stranded allocator capacity/C05 and C04 scan optimization remain deferred.
B12 exception error-code ABI, B14 Port-owner lifetime, B15 guard auto-traits,
B16 ring SPSC API, B17 physical PS/2 configuration, B19 retained shared PageMap
aliases/effective user permissions and B20 panic/stack contracts are not broadly
resolved here. Other historical audit findings retain their documented status.
The 16 KiB stack has no measured full-chain/interrupt high-water or guard proof.
CRC32C is corruption detection, not authentication; modeled crash cases are not
physical power-loss proof. The historical intermittent ATA poll timeout is not
closed by a successful retry or unchanged storage source.

Current supported ownership remains trusted ring-0, single-core, single boot /
main-loop context, with allocation-free IRQ paths. This work does not establish
safe arbitrary-thread APIs or untrusted userspace isolation.

## Proxmox boundary

Read-only GETs confirm VM 103 `rosti-dev` running on pve, SeaBIOS/pc, 512 MiB,
one vCPU, only the Phase 7 CD-ROM and no data disk. Configuration digest remains
`c0253f4f9bc55e6c3f222dcc893833cc46157a4b`. No deployment, reset, disk attachment,
formatting, storage-pool/host-partition operation, unrelated-service change,
push, tag or history rewrite is authorized or performed.
