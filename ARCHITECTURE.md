# ARCHITECTURE

## Phase 9.5B bounded occupancy diagnostics (C03)

`RostiFs::mount_info` sweeps the endpoints of current/previous inode extents,
counting their union clipped to `[DATA_START, total_blocks)`. It no longer tests
every block in the volume. Both snapshots remain represented; duplicates, overlap,
reserved-region clipping and unmounted/failed-remount diagnostic states retain
the old count semantics. The sweep advances strictly to an extent endpoint or
the volume end, with at most 257 inventories of 128 records inspected.

No cache, sorted temporary array, heap allocation, persistent field, unsafe code,
I/O, inode mutation or allocation-path change is introduced. The allocation
helper `occupied` is unchanged. Endpoint sums use u64 before clipping to avoid
32-bit intermediate overflow. Read-only statistics do not validate new media or
replace mount CRC/namespace checks. Work probes exist only under cfg(test).
Measurement and final acceptance are indexed in docs/PHASE9_5_C03_RESULTS.md.

## Phase 9.5B partial-read architecture

Ordinary RostiFS reads now transfer only sectors intersecting requested bytes.
Complete aligned 4 KiB reads retain the original read_block path. Both branches
reuse the same resident scratch, fallible RefCell borrowing and checked full-block
geometry; no cache, heap allocation, unsafe operation or persistent field is added.
EOF clamps the count before offset arithmetic. Mount/check still read complete
padded extents for CRC32C validation. Write/COW, delayed reuse, poisoning and every
flush are unchanged; so are capability validation and shared descriptor offsets.

An unrequested sector's device error is no longer probed by a small read. An error
may leave a copied prefix in the caller buffer; reads were not transactional before
this change. Command-owned descriptor cleanup still applies on every error path.
Exact memory/ELF/stack trade-offs and unavailable high-water metrics are recorded
in docs/PHASE9_5_OPTIMIZATION_RESULTS.md. The prior safe-API/boot-memory findings
remain prerequisites; this read optimization does not resolve them or start Phase 10.

## Phase 9.5 maintenance architecture

The storage and capability architecture below is retained. No format version,
mount lifetime, transaction ordering, bootloader, target or IRQ-storage contract
changed. `cat` now uses one 128-byte bounded stack buffer instead of issuing a
four-byte persistent read for every scalar. It overlaps up to three tail bytes
at refills, preserves UTF-8/invalid-byte escaping, per-scalar SEEK checks and
shared final offsets; a no-SEEK descriptor retains the prior four-byte denial
behavior. First and later I/O failures propagate and close only command-owned
descriptors. No heap cache or file-sized intermediate buffer was added.

Descriptor lifetime invalidation saturates/retire-at-MAX; exhausted console
installation fails closed, and failed open-record allocation restores the
unpublished descriptor generation and live count. Cumulative diagnostic counters
saturate, while live slot/record/ref counts remain exact. The single-bit helper
now clears correctly without changing other bits. Local SAFETY comments document
the unique non-IRQ static filesystem/descriptor/backend borrows.

Read-only findings and unresolved safe-API/boot-memory prerequisites are in
[PHASE9_5_AUDIT.md](docs/PHASE9_5_AUDIT.md); do not infer that passing current
QEMU tests proves safe arbitrary callers, user isolation or initramfs lifetimes.
In particular reserved growth-window/module mapping, boot entry ABI, general
exception signatures and fallible boot inventory need dedicated verification
before loading system modules. Existing trusted namespace APIs must not be
exported directly as untrusted capability syscalls.

[Application ABI](docs/ROSTI_APPLICATION_ABI_DESIGN.md) and
[optional GUI](docs/ROSTI_LIGHTWEIGHT_GUI_DESIGN.md) remain **design only**.
ELF32-first user loading, traps, processes, framebuffer rendering, mouse input,
networking and Phase 10 initramfs/verified system images are not implemented.
Measured comparisons and timing limitations:
[PHASE9_5_PERFORMANCE.md](docs/PHASE9_5_PERFORMANCE.md).

## Phase 9: current persistent-storage architecture

Applications/shell → capability-based `FdTable` → `Vfs`/`MountedFs` →
`RostiBackend` → portable `rostifs::engine::RostiFs` → `BlockDevice` →
shared ATA/IDE driver → authorized test image.

- `crates/rostifs/` is independently host-testable and `no_std`, with no unsafe
  code, heap allocations or third-party dependencies. Its authoritative wire
  format, bounds, checksums, transaction assumptions and recovery algorithm are
  specified in [FORMAT.md](crates/rostifs/FORMAT.md).
- `src/fs/mounted.rs` traverses mount boundaries component-by-component, including
  `..`; it preserves RAMFS type checks, quotas and absent-disk accounting.
  `/mnt/rosti` is exposed only after successful validation. Node identities are
  interned with generational bindings; RAMFS and mounted nodes cannot alias.
  Unmount rejects mounted cwd and active descriptors, including duplicates and
  deleted-but-open files. The shell does not expose unmount/remount yet.
- `src/fs/rosti.rs` adapts portable VFS types without layout casts. The core and
  adapter are const-initialized in static storage, mounted in place, and never
  returned by value on the 16 KiB boot stack. Root RAMFS remains independent.
- `src/storage.rs` provides distinct filesystem/diagnostic views of one ATA
  driver behind a main-context mutex; no mutable ATA reference is aliased. IRQs
  must never touch this mutex, descriptors or filesystem I/O. ATA sector writes
  still flush individually; an explicit bounded CACHE FLUSH implements each
  filesystem ordering barrier. Flush failures propagate, never become success.
- `src/fs_commands.rs` closes command-owned descriptors on every exit, including
  persistent I/O failures, without closing preexisting handles. Existing read-only
  rights, shared offsets, attenuation, stale-handle rejection and resource counts
  remain the descriptor layer's responsibility.

Allocation is derived from validated extent inventories, not a disk-size RAM
bitmap. Replacement extents cannot overlap either valid committed snapshot.
Deleting data frees it only after retained generations no longer reference it.
Directory parent/name records are inline in the bounded metadata bank. A file
update copies its complete bounded extent; fragmentation and COW headroom are
intentional v0.1 limitations.

The commit protocol publishes an alternating root only after data and metadata
barriers, then performs a final barrier before acknowledging success. I/O error
leaves the old RAM snapshot visible and poisons mutations until remount, because
the durable outcome may be old or new. Mount reads and validates both complete
snapshots, their file checksums, references and allocation before selecting the
higher valid generation. Unsupported versions or unreadable candidate roots
fail closed. One valid root is degraded recovery; `rostifsck` reports degradation
without repairs. No valid root leaves the RAMFS recovery shell reachable.

Memory measured from the actual i686 ELF and QEMU: namespace **6,940 B**, engine
plus adapter **21,300 B**, total filesystem static objects **28,240 B** (including
root RAMFS). Shared scratch **4,096 B**, included in the engine; no cache and no
per-operation heap allocation. The `rostifs` metadata-table diagnostic is
**22,324 B**, excluding RAMFS and 28 namespace control bytes. Descriptor table
is **2,328 B**, ATA driver/mutex **104 B**, separately accounted. These objects
remain resident even if mounting fails. Directory/path work uses bounded loops
and small inline buffers; file writes never allocate file-sized RAM staging.
Compiler stack reservations are not hardware high-water measurements. See
`test_results/phase9/memory_measurements.json` and the format's memory section.

Future, **not implemented**: optional LZ4, verified read-only OS images, signed
manifests, user snapshots, selective data COW, immutable-object deduplication,
file-backed mmap, swap-aware caches, HDD/SSD allocation policies, model-file
optimizations, SMB/NFS through VFS and Windows/Linux compatibility bridges.
These do not add GPU or AI requirements to this kernel.

The sections below describe prior milestone architecture; current storage
behavior is specified above and in FORMAT.md.

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

## Phase 6: minimal VFS and RAM filesystem

- `src/fs/vfs.rs`: backend-independent `Vfs` trait, `NodeId`, `NodeKind`,
  `Metadata`, `FsStats` and typed `FsError` with human-readable diagnostics.
  Interface: lookup, create file/directory, offset read/write, atomic replace,
  truncate, callback listing, metadata, canonical path and removal. No mount
  table, permissions, POSIX inode model or disk backend is claimed.
- `src/fs/mod.rs`: `RamFs`, a fixed 64-slot metadata table. Each occupied node
  stores its parent ID, inline UTF-8 name, type and a `Vec<u8>` file buffer.
  IDs combine a slot and generation; stale IDs fail and generation-exhausted
  slots retire rather than wrap. IDs are scoped to their filesystem instance.
- Paths are traversed component-by-component, iteratively, not blindly reduced
  lexically: `file/..`, `file/.` and `file/` fail as non-directories. Absolute
  paths start at root; relative paths start at cwd; excess parent traversal
  stays at root. Raw and canonical paths are at most 256 bytes; components are
  at most 63 bytes. Empty paths, controls/NUL and invalid creation leaves
  (`.`, `..`, root) are rejected. Trailing separators require a directory.
- Every growing buffer first uses `try_reserve_exact`, before changing bytes
  or metadata. A staged replacement preserves the old file on allocation
  failure. Offset writes zero-fill gaps; extending truncate zero-fills; shrinking
  retains capacity for reuse except truncate/replace to zero, which frees it.
  File deletion frees its buffer and reuses the metadata slot. Directories
  must be empty to remove; root is protected.
- Accounting: `logical_bytes` sums file lengths; `allocated_bytes` sums retained
  Vec capacities, capped at 4 MiB. Metadata is the fixed `size_of::<RamFs>()`,
  separate from payload and independent of occupied node count (5,888 bytes
  in the i686 kernel). Heap allocator headers/fragmentation are reported by
  `mem`, not misclassified as filesystem payload. Transactional staging can
  temporarily add at most one file-sized buffer (512 KiB), so the filesystem
  backing bound is 4.5 MiB plus fixed metadata and allocator overhead. The
  stress fixture's scratch/heap-fill buffers are separate diagnostic memory.
- `src/fs_commands.rs`: host-testable generic VFS shell adapter; it does not
  know RamFs internals. Output uses `fmt::Arguments` and callbacks, without
  allocating error/output strings. Failed first writes remove newly created
  empty files; failed overwrites preserve old contents. Cwd cannot be removed
  out from under the shell. File data preserves trailing whitespace. Since
  Phase 7 every file command dispatches through the descriptor layer
  (`Shell → Descriptor API → VFS → RAMFS`), plus `fdlist` diagnostics.
- `kernel_main` owns one statically initialized RamFs instance (`.data`) and a cwd ID, passed
  explicitly to `shell::poll`. The large metadata table never moves onto the
  16 KiB boot stack. Other RamFs instances are possible; the VFS does not rely
  on a global mutable singleton. Filesystem work runs only in main context,
  with interrupts enabled, outside VGA/heap/frame lock guards. There is no FS
  lock to invert the heap -> frame lock order; IRQs only enqueue/increment.
- `src/fs_stress.rs`: explicitly invoked, bounded fixture under `/__fsstress`,
  with cleanup on early returns. Checks complete file data, quota rejection,
  real KernelHeap OOM rollback and every growth-window PTE. Heap growth pages
  remain mapped after deletion for reuse; physical frames are not returned.

## Phase 7: capability-aware file descriptors and generational handles

`src/fd.rs` is a static, allocation-free kernel object subsystem. One
`FdTable` instance (`.data`) is owned by `kernel_main` and passed explicitly
to `shell::poll`; the shell's file commands open, read, write, seek, stat,
duplicate and close through it instead of calling the VFS directly.

- `Handle` is an internal generational reference (slot + generation), never a
  kernel pointer. Stale handles fail after slot reuse; exhausted generations
  are retired, never wrapped, so no ABA aliasing is possible.
- `OpenFile` is the open-file description: the shared offset and refcount live
  here, so duplicated descriptors share one offset through the same handle.
  A descriptor is a slot (handle + kind + rights), not the filesystem node.
- `Rights` is an 8-bit default-deny capability mask (READ, WRITE, SEEK, STAT,
  DIRECTORY_READ, CREATE, DELETE, MAP-reserved). Duplication can only
  attenuate (`attenuate()` rejects any bit outside the source mask); every
  operation validates rights at call time. Rights are capabilities, not
  isolation: the kernel still shares one privileged address space.
- `ResourceKind` covers File, Directory, ConsoleInput, ConsoleOutput; Pipe,
  Socket and Device are reserved for later phases. No dynamic dispatch, no
  allocation on any fd path.
- Node bindings are generation-checked through the VFS at every operation, so
  deleting an open file makes its descriptor fail cleanly (`StaleHandle` on
  resolve) rather than dangle; the record is released on close.
- Descriptors 0/1/2 are reserved for console input/output at boot with rights
  0 (default-deny until wired to real console operations).
- Tables are fixed: 64 descriptor slots + 64 open records. Asserted budget:
  slot ≤ 16 bytes, record ≤ 24 bytes → ≤ 2,560 bytes fixed overhead plus
  counters (smaller on i686). Exhaustion returns `TableFull`; it cannot
  fragment the heap or corrupt filesystem metadata.
- Lock order: descriptor table → VFS. No fd operation allocates, so the
  heap → frame order is never crossed. ISRs must not touch this subsystem
  (SpinMutex is not interrupt-safe); filesystem and descriptor work stays in
  main context.
- `FdStats` counters (opens, closes, denials, stale rejections, open slots,
  open records) are printed by `mem` and provide deterministic proof that
  dispatch went through the descriptor layer; `fdlist` lists each open
  descriptor with fd number, resource type, rights, offset and refcount.
- Unlink semantics are explicit: a deleted file invalidates open descriptors
  through generation-checked node binding; open records survive until their
  last close releases them.

The descriptor layer is filesystem-independent: it depends only on the `Vfs`
trait, so future disk filesystems (RostiFS) can back it without changes.
Handles are designed to support later file-backed memory mappings (MAP right
reserved). Swap, page reclamation and filesystem persistence remain separate
responsibilities.

The shell remains a single-task kernel shell. Kernel-ring overflow discards
pending events and rejects a damaged line; recovery resets modifier state.
Loss upstream in the PS/2 controller is not detected by this ring flag. UTF-8
file bytes are preserved and serial output is UTF-8, but VGA remains a
byte-oriented text console without Unicode glyph rendering.

No file persistence, users, processes,
symlinks, hardlinks, rename, timestamp metadata, disk mounts or Linux/POSIX
compatibility are implemented. The 256 MiB physical-frame tracking cap remains.

## Phase 8: persistent sectors, separate from the VFS

The block layer is a main-context, filesystem-independent subsystem. Its
`BlockDevice` interface describes sector size, sector capacity, one-sector
read/write, typed errors, ownership state and scalar statistics. An ATA bus
abstraction makes protocol behavior testable without executing privileged I/O;
the volatile host RAM backend is a test double, not persistence evidence.

Storage acceptance requires real ATA PIO on new QEMU raw images: every byte of
the diagnostic sector must survive a guest reboot and a completely new emulator
process. Diskless boot and refusal to write unmarked media are separate required
cases. The safety marker reserves sector 0; diagnostic writes target nonzero
sectors. This marker is a guardrail for explicitly owned test images, not a
substitute for disk-attachment authorization or hardware isolation.

Shell file commands continue through FdTable -> Vfs -> RamFs. The block layer
does not alter descriptor rights, node generations, RAM quotas, heap growth or
paging ownership. There is no disk VFS backend, mount table, partition parser,
persistent-file guarantee or crash-consistent RostiFS format in this milestone.
PIO is synchronous and bounded; ISRs must never perform disk work. A failed
sector write or cache flush may have changed media before returning an error;
this layer does not provide atomic writes, rollback or crash-consistent metadata.
