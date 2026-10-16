# Historical read-only audit of initial HEAD def677fac8ca662e45ad4fb40c9ddd18bfe86bd8

This audit predates the permission fixes in d6d04c5; its PTE-only/unsupported-request findings describe the initial source, not the current checkpoint. Other prerequisites remain unresolved. No runtime verification was performed by this audit.

## Outcome

**B19 remains unresolved; current mappings are supervisor-only, not a working ring-3 boundary.** Read-only inspection confirmed branch `maintenance/phase10`, HEAD `def677fac8ca662e45ad4fb40c9ddd18bfe86bd8`. No builds, tests, QEMU, acceptance, or writes performed.

### Permission propagation and supervisor coverage

- `entry_value()` sets **PRESENT|WRITABLE, never USER** (`src/memory/paging.rs:55–57`). Both boot PDEs and identity PTEs use it (`:478–484`).
- Runtime-created PDEs also use that supervisor-writable value (`:217–230`). Runtime PTEs always set PRESENT and optionally copy writable/user (`:237–244`): **`PagePerms.present` is ignored**.
- `permissions()` reports **PTE-only** flags, not effective PDE∧PTE permissions (`:176–186`). Thus a requested user PTE can report `user=true` while its supervisor PDE still prevents ring-3 access. Effective present/user/write access requires the corresponding permission at both levels; supervisor writes additionally depend on CR0.WP.
- Paging activation sets CR0.PG and then CR0.WP (`:554–571`). NX is explicitly unsupported (`:183–185`). Existing identity mappings are writable—including kernel text—and do not provide W^X.
- Identity coverage is `[0, window_end)`, excluding null and the heap-growth window (`:441–477`), **not just usable RAM**. `window_end` follows highest usable-memory/kernel end (`src/memory/mod.rs:43–54`), while physical allocation is capped at 256 MiB (`src/memory/frame.rs:29–33`).
- Consequently kernel image/boot stack, bootstrap heap, paging structures, VGA, and covered boot/module metadata are supervisor mappings. Growth adds supervisor-writable identity mappings using `KERNEL_PERMS` (`src/memory/mod.rs:230–245`; `src/allocator.rs:5–15`).
- Runtime unmap protects kernel/VGA, live directory/table identity aliases, and permanent boot pins (`src/memory/paging.rs:264–273,318–326`). Production pins page-round nonusable inventory spans and the boot header (`src/memory/mod.rs:96–130`). These are **unmap/lifetime protections**, not read-only protections.

### Safe-API and ownership holes

1. **Retained shared PageMap aliases:** `page_map_ref()` exports `&'static PageMap`, while `heap_grow_frame()` independently constructs `&mut PageMap` (`src/memory/mod.rs:216–219,235–239`). Safe callers can retain the shared borrow across mutation; frame locking does not repair Rust aliasing. The host growth test does exactly that (`tests_kernel/src/lib.rs:869–885`). This matches B19 (`docs/PHASE9_5_AUDIT.md:331–343`).
   - Boot-copy validation now ends its borrow before allocating (`src/memory/boot_copy.rs:29–38`), and fsstress scopes inspection before output (`src/fs_stress.rs:192–209`); neither closes the public API hole.

2. **Safe numeric addresses confer unchecked memory authority:** `PageMap::map()` checks alignment/range/conflict, but not ownership, reservation status, or alias permissions of the supplied physical frame (`src/memory/paging.rs:194–244`). A frame can be free, kernel-owned, or already aliased writable. Public builders also trust the caller’s allocator/window pairing before physically zeroing frames (`:394–429,496–499`).

3. **Frame ownership is conventional, not encoded:** public `FRAME_ALLOC` permits reinitialization and freeing numeric addresses (`src/memory/mod.rs:34–35`; `src/memory/frame.rs:136–148,298–342`). `free()` cannot prove mappings/references ended or distinguish stale ownership after reallocation. No ownership token connects map/unmap/free; unmap itself does not free payload frames (`src/memory/paging.rs:281–292`).

4. **Safe heap-region insertion writes arbitrary addresses:** `KernelHeap::add_region()` is safe, but accepts numeric spans and writes free-list headers without establishing backing, exclusivity, disjointness, or nonoverlap (`src/allocator.rs:119–127,153–159`). Multiple safe heap instances can register the same region.

5. **Null protection is boot-only policy:** the builder skips page zero, but runtime `map()` does not reject linear zero (`src/memory/paging.rs:201–214,468–471`). A safe caller can restore a null mapping.

6. **Heap capacity loss remains visible in the implementation:** allocation discards alignment prefixes and sub-`MIN_BLOCK` tails, records only `need`, and deallocation restores only that recorded span (`src/allocator.rs:246–264,292–303`). This affects bounded-resource reliability independently of ring-3 permissions. Invalid-deallocation checks occur after reading the header; they are not pointer validation, although `GlobalAlloc::dealloc` is correctly unsafe.

### Lock ordering and harness limits

- Current growth order: **heap → frame** (`src/allocator.rs:308–316,269–277`; `src/memory/mod.rs:235–239`).
- Production preparation allocates backing before acquiring frame, and releases frame before failed backing destruction; validation cleanup follows the same discipline (`src/memory/mod.rs:151–189`). The owning builder remains hazardous under a frame guard on failure, explicitly documented (`src/memory/paging.rs:389–404`).
- `SpinMutex` does not mask interrupts and is nonreentrant (`src/utils/mutex.rs:35–46`). Future scheduling/IRQ allocation must not interrupt a holder and reacquire these locks.
- Host paging uses thread-local mirrors and no-op TLB invalidation/enablement (`src/memory/paging.rs:332–370,575–576`); it cannot establish CPU permission enforcement.
- Existing tests cover read-only PTE reporting, conflicts, unmap, and growth, **not effective USER propagation** (`tests_kernel/src/lib.rs:790–885`).
- Separate B26 instrumentation watches allocation **and destruction** under frame guards, with disclosed layout filtering on partial builds (`tests_b26/src/lib.rs:72–113,118–176`). Published-global lifecycle tests use subprocess isolation (`tests_b26/src/growth_tests.rs:4–27`).

### Minimal dependency plan before ring 3

1. Close PageMap aliasing with a synchronized owner and scalar/snapshot query APIs; expose no retained references or allocating callbacks under paging ownership.
2. Encapsulate frame/map/heap authority: explicit unsafe boundaries or ownership tokens, checked backing/disjointness, and coordinated mapping teardown before release.
3. Define separate requested/effective permissions; retain supervisor-only kernel mappings and reject unsupported requests until a dedicated user-mapping path exists. Do **not** globally set kernel PDEs USER.
4. Establish user address-space policy, initialized user frames, alias-aware writable permissions, user-stack bounds, and checked copy-in/out. Preallocate metadata outside mapping locks; select and document one acyclic heap/frame/paging order.
5. Add user descriptors, TSS/kernel-entry stack and robust privilege-transition/exception handling. Current GDT contains only null/kernel code/kernel data (`src/gdt.rs:136–151`); IDT defaults are DPL0 and general exceptions share no-error-code handler typing (`src/interrupt.rs:9,117–131`).
6. Only then authorize CPU ring-3 denial/entry/fault/cleanup tests. Host mirrors are insufficient evidence.

### Bounded first TDD fix

**Fail closed on unsupported mapping requests, without enabling user execution.**

- RED cases: `user=true` and `present=false` must reject before allocating a table or changing mappings; check unchanged translation and frame/table/map/TLB counts, with only rejection accounting changing.
- GREEN: validate these requests at the start of `PageMap::map()`; keep `KERNEL_PERMS`, PDE construction, growth, and boot mappings unchanged.
- Retain supervisor read-only/writable regression cases. Follow with effective-permission reporting and PageMap ownership work; this first slice alone does **not** resolve B19.

**Files changed:** none. Existing untracked `d1/` and `scripts/b13_boot_fixture.py.backup` remained unchanged. `allocator.rs` is at `src/allocator.rs`, not under `src/memory/`. Findings are source-review conclusions, not formal verification or fresh runtime acceptance.
