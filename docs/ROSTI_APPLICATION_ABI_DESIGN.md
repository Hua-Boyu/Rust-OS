# Rosti application ABI — independent design proposal

**Status: DESIGN ONLY / NOT IMPLEMENTED.** Phase 9.5 research does not authorize a loader, syscalls, scheduling or Phase 10 changes. This is a native Rosti contract, not Menuet, bootOS, POSIX or Linux compatibility. See [comparison and external citations](MINIMAL_OS_COMPARISON.md).

## 1. Existing contracts and missing boundary

Inspected [`main.rs`](../src/main.rs), [`gdt.rs`](../src/gdt.rs), [`interrupt.rs`](../src/interrupt.rs), [`paging.rs`](../src/memory/paging.rs), [`fd.rs`](../src/fd.rs), [`fs_commands.rs`](../src/fs_commands.rs), [`vfs.rs`](../src/fs/vfs.rs), [`multiboot.rs`](../src/multiboot.rs), [architecture](../ARCHITECTURE.md) and [RostiFS format](../crates/rostifs/FORMAT.md).

Today there is one privileged shell, kernel-only GDT code/data segments, DPL0 IDT gates and no TSS-backed application entry/return, task scheduler, app ELF loader or recoverable copy-user layer. Page permissions expose a user bit, but that does not establish a working user address space; the current identity map and runtime mapping bounds were designed for the kernel. Non-PAE paging does **not** enforce NX. Existing general exception behavior is not an application fault-containment policy.

`FdTable` is a useful bounded object layer, not a complete authorization service. `open` accepts caller-supplied rights; shell namespace creation/removal/listing call VFS directly in several paths. `DIRECTORY_READ`, `CREATE` and `DELETE` are not all enforced through dedicated descriptor operations today. Console descriptors 0/1/2 have rights zero and are not usable file read/write endpoints. Do not expose these internal entry points unchanged to untrusted programs. Descriptor table metadata is allocation-free; an operation on RAMFS can still allocate payload through VFS. Internal handle generations do not turn a reused numeric fd into a generation-protected public token.

## 2. Choice: static ELF32 first

### Executable-format comparison

| Option | Compatibility/tooling | Memory and file overhead | Parser attack surface | Complexity/evolution | Decision |
|---|---|---|---|---|---|
| A. Standard i686 ELF executables | Existing Rust/linker/debugger/objdump workflows; native Rosti ABI, not Linux compatibility | Program headers and alignment have a cost; resident BSS/pages/stacks dominate admission. No application measurement exists yet | Established structures still require strict checked subset; reject dynamic linking/interpreters/overlap/oversized BSS | Moderate bounded loader with mature tooling and documented segment flags | Preferred initial executable format |
| B. Minimal native Rosti format | Custom SDK/linker postprocessor/debug mappings; no existing compatibility benefit | A compact header might save file bytes; actual savings and resident-memory benefit are unmeasured | Fewer fields can simplify parsing, but custom lengths/flags/versions need an entirely new adversarial corpus | Highest long-term tool/ABI ownership; flat layout can obscure permissions and relocation constraints | Reject as initial loader without compelling measured benefit |
| C. ELF initially, optional compact native packaging later | Keep ELF as canonical build/debug representation; packaging can evolve independently | Optional transport/package savings need real representative binaries and bounded decompression/staging budgets | Adds a second outer parser and possibly decompressor; inner ELF validation remains mandatory | Incremental, but no second execution ABI should be invented just to save a header | Long-term option only if measured distribution constraints justify it |

ELF sections used only for debugging need not be resident. Compare loadable
segments, allocation/page-table budgets and parser complexity separately from
archive size; a smaller native header does not prove lower RAM or faster launch.
An optional compact package must not relax signature/trust, ELF bounds or user
isolation. No A/B/C loader, packager or benchmark is implemented in Phase 9.5.

Use little-endian ELF32, `EM_386`, `ET_EXEC`, statically linked native applications. Tool familiarity, segment boundaries and existing ELF inspection experience outweigh a marginally smaller bespoke flat header. Kernel Multiboot ELF validation remains separate; it is not an application loader. Initial scope excludes dynamic linking, `PT_INTERP`, relocations, TLS, threads, signals, FPU/SIMD use, mmap, swap, fork/exec and foreign syscall translation. Toolchain must emit soft-float/no-SIMD code; malicious unsupported instructions still require fault containment, not trust in compiler flags.

Proposed loader bounds:

- Executable file at most 256 KiB, compatible with current persistent file bound; at most eight program headers and eight loadable segments.
- At most 256 KiB total resident image including zero-filled BSS and page-rounding; a short file with huge `p_memsz` must not bypass this cap.
- Require a `ROSTI` ELF note identifying ABI major 1, minor 0 and required feature bits. Unknown major/required features fail closed. Optional extensions negotiated at runtime.
- Checked arithmetic for headers, file offsets, `filesz <= memsz`, VA endpoints, alignment, rounded page spans and sums. Reject truncated/overlapping ranges, page-sharing between segments, unsupported flags and executable+writable segment requests. Entry must lie in an image segment marked executable.
- Ignore no input merely because it is called padding: validate note sizes/alignment and reject contradictory/duplicate ABI notes. Section headers are not necessary to load, but reject unsupported program-header types except explicitly inert metadata types selected by the final loader specification.
- Proposed task-local image window starts at `0x40000000` and is at most 256 KiB. Proposed stack: 64 KiB ending at `0x7ff00000`, with an unmapped page below; read-only startup block in a distinct page near that region. These are **future task-local addresses**, outside today's mapping contract; do not map them through the existing identity-map API as if already supported.
- Load only from a launcher-authorized readable file descriptor through FdTable → MountedFs/VFS. No raw ATA, RostiFS layout knowledge or kernel pointer in the app format. Stage/validate before publication; reserve every frame fallibly and roll back partially constructed address space and descriptors on failure.

ELF executable/writable flags express policy. On current non-PAE hardware, read-only code can resist writes but writable user data remains executable; **W^X/NX enforcement is not claimed**. Do not make PAE/x86-64 a hidden prerequisite for preserving the i686 baseline.

## 3. Proposed entry and versioned trap convention

A dedicated DPL3 interrupt gate at **`int 0x80`** is proposed, not installed. It is outside current PIC vectors `0x20..0x2f`. Do not borrow bootOS's `int 0x20..0x25`, which collide with Rosti IRQs, or claim Linux semantics from vector choice. A small assembly shim must capture/restore a precisely specified i686 frame; the current placeholder interrupt frame cannot be reused blindly.

| Register/state | Proposed meaning |
|---|---|
| EAX on entry | `major << 16 | operation`; initial major 1 |
| EBX, ECX, EDX, ESI, EDI | Up to five 32-bit arguments, call-specific |
| EAX on return | Signed 32-bit result: nonnegative value/count or negative stable error |
| EBX, ECX, EDX, ESI, EDI, EBP | Preserved by trap ABI; no undocumented secondary return values |
| ESP, EIP, CS, SS | Restored from validated task trap state; never caller-supplied kernel targets |
| EFLAGS | User IF enabled, IOPL0; privileged/control flags sanitized; DF clear on entry to Rust and return; callers may not rely on condition-code preservation |

Choose `int` first for a transparent i686 entry path, not `sysenter`/64-bit `syscall`; optimize only with evidence. Internal application functions may use normal i386 C calling conventions through an SDK wrapper. At initial entry: ESP 16-byte aligned, EBX points to a read-only versioned startup block, other general registers zero, DF clear. Startup contains explicit u32 sizes/counts, bounded argv offsets into the block, negotiated feature mask and inherited resource tokens; never Rust enum/layout or host `usize`. `_start` calls application main and issues EXIT; returning into arbitrary memory is a task fault.

All multi-byte wire fields are explicit little-endian; structures begin with `size:u32, version:u32`. Unknown required bits/version are rejected, reserved fields zero. A smaller known prefix is accepted only when that specific operation documents it. No callbacks, user function pointers, NUL scanning or `repr(Rust)` crosses the boundary.

## 4. First operation set

The following numbers are proposed within major 1; no implementation is implied. Inputs not listed must be zero. Errors are stable ABI integers, not internal enum discriminants.

| Op | Call / arguments | Semantics |
|---|---|---|
| 0 | QUERY(buf=EBX,len=ECX) | Fixed version/features/resource limits; enough room required, no partial struct |
| 1 | EXIT(code=EBX) | Terminate caller and release only its resources; no return |
| 2 | READ(token=EBX,buf=ECX,len=EDX) | READ right, count including zero at EOF; maximum 4096 B |
| 3 | WRITE(token=EBX,buf=ECX,len=EDX) | WRITE right, count; maximum 4096 B; no automatic persistent retry |
| 4 | CLOSE(token=EBX) | Invalidate caller token; shared open record survives other references |
| 5 | DUP(token=EBX,mask=ECX) | Only attenuation; shared offset; returns independent public token |
| 6 | SEEK(token=EBX,offset=ECX) | Absolute u32 offset, SEEK right; result zero, not implied file extension |
| 7 | STAT(token=EBX,buf=ECX,len=EDX) | STAT right; explicit kind/size fields, no NodeId/Handle leak |
| 8 | WAIT_EVENT(buf=EBX,len=ECX,timeout_ms=EDX) | One fixed event; zero timeout is poll; finite timeout bounded by documented tick precision |
| 9 | OPEN_AT(dir_token=EBX,path=ECX,path_len=EDX,rights=ESI) | Lookup under launcher-authorized directory policy; cannot manufacture requested rights |
| 10 | READ_DIR(dir_token=EBX,cursor=ECX,buf=EDX,len=ESI) | DIRECTORY_READ checked on each call; bounded copied records, invalidated cursor fails cleanly |

Proposed stable errors: 1 INVALID_ARGUMENT, 2 BAD_RESOURCE, 3 DENIED, 4 NOT_FOUND, 5 WRONG_TYPE, 6 LIMIT, 7 NO_MEMORY, 8 IO, 9 CORRUPT, 10 UNSUPPORTED, 11 BUSY, 12 WOULD_BLOCK, 13 BAD_ADDRESS, 14 STALE. Returned as negatives. Preserve more detailed diagnostics internally; never reveal kernel addresses. Subsequent mutation calls require explicit authorization and separate minor feature negotiation; no CREATE/DELETE implementation is smuggled into OPEN_AT v1.0.

File writes preserve backend guarantees: RostiFS each storage mutation commits independently, errors poison future mutations until controlled remount, and ambiguous IO can have durably committed despite an error. Do not describe a multi-chunk application write as atomic, automatically replay it, or mask flush failure. Full-file REPLACE, if added later, requires a bounded single-request contract compatible with backend limits, not an unbounded staging buffer.

## 5. Resource authority and lifetime

Applications inherit **only** selected descriptors from a launcher policy, with explicit maximum rights. Native code cannot supply a mask to `FdTable::open` and thereby gain authority. Directory capabilities need an additional bounded policy containing lookup permission, permitted child rights and a confinement root; the existing eight-bit mask is already full with reserved MAP. Do not repurpose MAP or silently extend `Rights(u8)`.

Initial READ_DIR may operate on a supplied directory without authorizing recursive open. OPEN_AT requires a separate explicit namespace grant. Resolve paths component-by-component, retaining `file/..` failure. Restrict capability-relative paths, reject absolute escapes, and enforce `..` confinement including mounted-root parents; do not merely concatenate strings or lexically normalize. Root-launcher policy may deliberately allow an absolute namespace, but it is not inherited by default. Persistent names remain limited to 60 UTF-8 bytes; RAM names may use existing 63-byte limit. Paths retain 256-byte bounds and control/NUL rejection.

Expose a proposed nonnegative u32 token: low 6 bits select one of 64 task slots, next 25 bits are a public slot epoch, top bit zero so it fits positive EAX. Maintain a separate token→internal-fd mapping, validate epoch on every call and retire exhausted epochs. Internal open-file generation and public descriptor-slot epoch are different concepts. A stale application token must not reach a new resource after slot reuse. DUP returns a fresh token while sharing the existing open-file offset. Deletion invalidates node binding according to current Rosti semantics; do not promise POSIX deleted-open file access. Tokens are task-local references, not transferable bearer secrets or raw pointers.

The initial launcher admits **one application at a time**; the recovery shell keeps its own descriptors/cwd. Before multi-task support, redesign shared open-record ownership explicitly: merely allocating a separate current FdTable per task will not make cross-task duplicates share offsets/refcounts. All task descriptors/cwd, including duplicates/deleted-open records, participate in mount pins. No app mount/unmount, raw-disk, format, port, IRQ, frame or page-table authority.

## 6. User memory and execution prerequisites

Before any untrusted native app runs, implement and verify user segments, TSS/esp0 and kernel stack, per-task page directory ownership, supervisor-only kernel mappings, user-access checks at **both PDE and PTE** levels, CR0.WP preservation, trap entry/return flag sanitation and fault handling that distinguishes user faults from kernel bugs. Shared kernel aliases must never make app frames writable through a user mapping. Frame/table lifetime needs explicit ownership; kernel table-writing assumptions about identity addresses must remain valid.

Copy arguments before acting: maximum 4096 B transfer and 256 B path, checked pointer+length and every crossed page; nonzero length rejects null, kernel, unmapped and wrong-access pages. Zero-length byte transfers do not dereference the pointer. A main-context bounce buffer avoids retaining a user pointer across FS/ATA calls. Prevalidate output destination before advancing file offset; mapping ownership must prevent changes until copy-out finishes, and recoverable copy faults must not panic the kernel. No borrowed user slice survives scheduling. Reject invalid buffers before disk side effects.

Syscall entry is synchronous task context, **not a hardware IRQ handler**. Only a short capture/stack switch runs with interrupts masked; descriptor/FS/ATA work runs with IRQs enabled outside VGA/frame guards. Preserve heap→frame order and single main-context FS owner. IRQs only enqueue input/increment counters, never allocate, lock VGA/FS or switch tasks while those owners are active.

A cooperative launch/run/return experiment cannot contain an infinite loop. A future timer must be able to interrupt/terminate user execution safely, while deferring switches during kernel service ownership. Initial no-SIMD policy needs CR0/fault/context handling and SDK constraints. Until boundary, preemption/watchdog and cleanup are proven, only trusted built-in code is permitted; a loader parser alone must not be advertised as secure applications.

## 7. Proposed admission budgets

Python arithmetic was used for these **planning caps**, not measured structures:

| Per admitted task item | Bound |
|---|---:|
| Rounded resident image including BSS | 262,144 B |
| User stack | 65,536 B |
| Separate kernel stack | 16,384 B |
| Existing i686 descriptor-table baseline | 2,328 B |
| Shared per-active-request bounce/startup allowance | 4,096 B |
| Subtotal | 350,488 B |
| Provisional combined page-directory/table + task/token metadata allowance | 16,384 B |
| Proposed planning total | 366,872 B |

Four such slots would total 1,467,488 B, but four-task operation is **not** initial scope. These sums exclude existing kernel/FS state, allocator headers, page-rounding for nonpage items, inherited data, retained FS payloads and GUI memory. Kernel identity mapping tables and process-owned tables may exceed the provisional allowance; exact mappings, target layout and stack high-water must be measured before admission caps are finalized. No large task object is constructed by value on the current 16 KiB boot stack. Reject resource exhaustion before publishing the task; release staged frames, references and tokens deterministically.

## 8. Future verification gates, not executed here

1. Host malformed-ELF tests: every header truncation, length/VA overflow, note corruption, overlapping pages, oversized BSS, unsupported interpreter/relocations and failed allocation at each staging step.
2. Host ABI tests: wire vectors, unknown versions/features, full error mapping, pointer-page boundaries, token reuse/epoch retirement, attenuation, shared offsets, directory escape across mounts, console default-deny and task-only cleanup.
3. Privileged tests separately authorized: ring-3 entry/return, PDE/PTE supervisor denial, user `cli`/port access, null/kernel pointer and cross-page copy faults, timer preemption of infinite loop, user exception exit without kernel halt, kernel stack guards and recovery shell after every failure.
4. Existing Phase 9 acceptance unchanged, plus ELF/GRUB application loading and OOM at 128/512 MiB on owned images. Persistent errors must preserve poison/recovery behavior and mount pins. No new ABI claim until actual privileged evidence exists.

Unresolved decisions: exact assembly trap frame/SDK alignment proof, address-space layout implementation, directory grant encoding, page-table budget, timer quantum/timeout policy and cross-task shared-open registry. These are implementation prerequisites, not omitted safety requirements.
