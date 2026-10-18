# Deferred backlog (inherited, UNVERIFIED unless explicitly noted)

These are not newly confirmed bugs and are not patched opportunistically. The
symbol anchors are investigation starting points, not a completed audit. This
checkpoint does not authorize USER/TSS/CPL3 or exception/allocator redesign.

| Priority | Source starting point | Suggested RED reproduction / next proof |
|---|---|---|
| P1 before USER | src/memory/paging.rs numeric PageMap::map and lifetime entry points | Define owned process mapping/token admission and virtual-page-zero refusal; stale numeric map observations must not grant another allocation's authority. No USER publication now. |
| P1 before dynamic teardown | src/memory/paging.rs PageMap retained/unpublished lifecycle | Model full per-map/shared/CPU references and actual CR3/stack continuation before reclamation. Current retained boot structures intentionally never release. |
| P1 before CPL3 | src/interrupt.rs error-code vector stubs, src/memory/phase11a2_abi_tests.rs | Actual CPU saved-frame/GPR/segments/DF/alignment/IRET and recoverable fault probes, independently encoded non-tautological #GP oracle. Existing host routing tests are not full ABI proof. |
| P2 | src/memory/mod.rs enable_paging; paging.rs diagnostics | Inject enable refusal and verify reported success state reflects actual publication/CPU state; inherited possible diagnostic issue unverified. |
| P2 | src/memory/paging.rs PageMap::entry/read_entry/write_entry | Inspect real physical PTE access semantics versus compiler/CPU requirements with a hardware-backed oracle, not only mirror reads. |
| P2 | src/memory/frame.rs set_runtime_pin/set_structure_pin | Fault inject invalid pin indexes and verify bounded refusal before bitmap mutation; setters currently rely on internal preflight. |
| P2 | src/memory/paging.rs cleanup/rollback and memory/mod.rs heap_grow_frame | Inject a raw-release refusal at each assumed-infallible cleanup edge; prove no success claim masks stranded ownership. No broad ignored-result cleanup attempted. |
| P2 | src/memory/structure_lifetime_tests.rs | Extend structure-lifetime fault coverage only when addressing a demonstrated remaining invariant; current exact-five coverage retained. |
| P2 | src/allocator.rs allocation span ownership | Exact free-capacity restoration across prefix alignment/tiny tail allocation-release sequences; do not conflate used=0 with full capacity restoration. |
| P2 | src/fs_stress.rs repeated shell fsstress | Repeat fresh and reused stress workloads, independently verify retained allocation/capacity/data and command boundaries. |
| P2 | src/shell.rs reboot path (exact controller implementation not investigated) | Trace bounded controller command sequences and actual guest reboot behavior before altering protocol. |
| P3 | src/gdt.rs and src/phase11_gdt_tests.rs | Independently decode flag/type boundary bytes; inherited possible gaps unverified, no TSS work. |
| P3 nonblocking source review | frame.rs FrameLease/release_frame rustdoc and FrameStats | Document consumed refusal/leak explicitly; consider must_use; clarify growth id0 and bitmap-only reporting. Review suggestions deferred to preserve frozen reviewed bytes. |
| P3 nonblocking source review | generation_ownership_tests.rs compile-time negative assertions | Add production-context compile-fail surface controls later; current runtime forgeries are not evidence of external unforgeability. |
