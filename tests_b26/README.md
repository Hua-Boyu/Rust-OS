# B26 / CURRENT-R3 host regression harness

Run from outside the kernel Cargo configuration (`C:/Users/iamsv`):

```bash
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_b26/Cargo.toml
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_b26/Cargo.toml -- --test-threads=1
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_b26/Cargo.toml b26_ -- --test-threads=1
```

The required `b26_` filter runs nine regressions: six ownership/lock tests
(including builder retry), plus three allocation-refusal/validation regressions.
The unfiltered harness additionally includes 19 source tests (12 B11, six
permanent-mapping/pin/tail-validation tests, one bit-helper test). The copied wire
`MmapEntry` fixture isolates concurrent boot-inventory work. This independently
rooted crate instruments its own global allocator; the crate root is `cfg(test)`
to avoid ordinary-library compilation of privileged hardware paths.

## Fallible preparation contract

Production `memory::prepare` returns `Result<u64, &'static str>`. Pin backing and
1024 table slots use `try_reserve_exact` outside the frame guard. Reservation
failure returns a static diagnostic without allocating fallback error storage or
initializing/changing frame accounting. Required regions are streamed; validation
returns the first missing static region name without heap allocation. The old
Vec-returning region/validation helpers are `cfg(test)` compatibility helpers for
unlocked callers only. The boot fixture diagnostic remains exactly
`frame exhaustion during page table build`.

- Directory exhaustion watches **all** owner-thread allocations/deallocations
  under `FRAME_ALLOC`; no host page-table mirrors are created on this path.
- Partial exhaustion at one through four frames watches production table/error
  layouts only, excluding the host-only HashMap/4 KiB Vec page-table MIRROR.
  Rollback checks exact free/allocated and invalid/double-free accounting.
- Borrowed construction retains backing on failure and transfers it on success.
  The retry regression verifies rollback clears stale ownership slots before a
  second failed build while two frames are held by another owner.
- Validation failure returns every unpublished directory/table frame and drops
  backing only after releasing the guard.
- Growth rejection preserves its reserved frame and conflicting PTE, permits
  retry, and rejects repeated prepare without replacing a live map. This
  publishing lifecycle runs in a subprocess so other tests remain order-independent.
- R3 independently refuses the first allocation (pins) and second allocation
  (tables). The allocator then allows but counts subsequent allocation attempts,
  making an unsafe fallback a deterministic assertion failure rather than an
  abort. Both tests assert the exact static error, no publication, and unchanged
  free/reserved/allocated/invalid/double-free counts.
- R3 counts unlocked allocations during a validation-failing prepare: exactly the
  two fallible backing allocations are allowed; region/diagnostic allocations are
  forbidden. Host mirror allocations occur under the guard and are excluded from
  this specific count, not from the directory-exhaustion watchdog.

The watchdog enable flag and refusal controls belong to the invoking thread;
unrelated Rust harness or parallel-test allocations cannot produce false lock-order
reports. Tests mutating shared boot state hold `TEST_LOCK`; publishing tests use
subprocess isolation. The existing owning builder is only for unlocked callers;
production uses the borrowed builder with pins, retaining backing until unlock.

This proves host refusal/rollback and allocation behavior, not real guest heap
exhaustion, privileged mapping or hardware lock behavior. No QEMU runs here.

Evidence: `test_results/phase9_6/b26*.json` and `r3_*.json`. R3 RED observed one
fallback allocation after each refused reserve and four unlocked allocations
instead of two during validation. Final GREEN includes all 27 tests both serially
and with default parallel execution. An initial full run exposed growth-test
publication leaking process-global state into later tests; its failure report is
retained, and subprocess isolation fixes test order dependence. Subsequent
coverage adds usable-tail validation to both host harnesses and retains the R3
tests under the mandatory `b26_` acceptance filter.
The final unfiltered parallel run passes 28/28 in `b26_final_unfiltered.json`.
