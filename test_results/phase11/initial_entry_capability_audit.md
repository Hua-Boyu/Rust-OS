# Historical read-only audit of initial HEAD def677fac8ca662e45ad4fb40c9ddd18bfe86bd8

This audit predates the permission fixes in d6d04c5; its PTE-only/unsupported-request findings describe the initial source, not the current checkpoint. Other prerequisites remain unresolved. No runtime verification was performed by this audit.

## Outcome

**Ring3 remains blocked by actual trap-ABI defects and missing privilege/ownership infrastructure.** Read-only audit completed against verified HEAD `def677fac8ca662e45ad4fb40c9ddd18bfe86bd8`. Loaded `rosti-kernel-development`; inspected the requested source and Phase9 safety/design documents. No builds, tests, QEMU, writes, or implementation performed.

### Actual defects and prerequisites

- **Returning #GP handler has the wrong ABI.** Vector 13 is installed through the no-error-code handler type (`src/interrupt.rs:9,248`); its handler returns normally (`322–328`). The CPU error word is not accounted for by that signature, so return cannot consume the correct IRET frame. This is the unresolved B12 finding (`docs/PHASE9_5_AUDIT.md:243–253`), not merely missing ring3 functionality.
- **Other error-code exceptions also use no-error signatures.** The common table/macro covers #DF, #TS, #NP, #SS with that signature (`src/interrupt.rs:117–131,348–386`). Vector 17/#AC incorrectly enters the generic “reserved range” handler (`429–437`). Fatal halting currently hides their return-frame problem.
- **#PF is deliberately fatal, not a reusable returning ABI.** Its error word is embedded in its first by-value frame argument (`src/interrupt.rs:258–273`), and it always halts (`295–297`). Preserve the existing diagnostic behavior, but do not reuse this shape for returning traps or infer application containment from it.
- **General frame is an opaque placeholder.** `[u8;48]` exposes no validated EIP/CS/EFLAGS or privilege-transition tail (`src/interrupt.rs:167–178`). It cannot support privilege classification, syscall results, safe return, or register capture.
- **No user descriptors, TSS, or ring3 entry/continuation.** GDT contains only null/kernel code/kernel data (`src/gdt.rs:126–147`); initialization only loads/reloads those segments (`150–183`). All installed IDT gates are DPL0 (`src/interrupt.rs:85–104,116–140`). Timer only increments ticks and acknowledges PIC (`341–345`); main has one shell loop (`src/main.rs:479–485`).
- **GDT encoder has a latent nonzero-base defect relevant to TSS.** `src/gdt.rs:57–59` ORs the *entire* `base << 16` into the descriptor instead of masking the low base word. Upper base bits contaminate already-encoded high descriptor fields. Current flat base-zero segments avoid it; do not reuse this encoder unchanged for a TSS.
- **Boot entry is already hardened—not an outstanding B13 defect.** CLI/CLD, owned aligned stack, padding and argument order are explicit (`src/boot.s:29–50`); `kernel_main` documents that contract (`src/main.rs:166–173`). Historical B13 text is superseded by `docs/PHASE9_6_SAFETY_HARDENING.md:59–85`.
- **Paging is not user-address-space support.** `map` accepts USER only in the PTE and restricts linear addresses to the managed/growth windows (`src/memory/paging.rs:209–243`); `permissions` reports PTE flags rather than effective PDE∧PTE permissions (`176–186`). No NX is available. Retained shared PageMap access remains (`src/memory/mod.rs:216–218`). User mapping/ownership must be designed, not achieved by toggling existing kernel mappings.

### Required exception/entry contract

Specify and verify an explicit i686 assembly/Rust boundary:

- Normalize **vector + error word**, using synthetic zero only for exceptions without CPU error codes. Architectural error-code cases include #DF(8), #TS(10), #NP(11), #SS(12), #GP(13), #PF(14), #AC(17); account for feature-dependent #CP(21), #VC(29), #SX(30) if exposed. #DF/#AC push zero-valued errors; #PF has its own bit interpretation.
- Hardware return state is **EIP, CS, EFLAGS**, followed by **old ESP, old SS only on privilege transition**. Classify via saved CS.RPL; never read a ring3 tail from a same-ring frame.
- Save all GPRs plus **DS/ES/FS/GS** before using scratch registers. CPU privilege entry does not install kernel data segments. Load valid kernel DS/ES, establish a defined FS/GS policy, clear DF before Rust, and restore saved segment state on ordinary IRQ return.
- Align the Rust call stack independently of interrupted ESP. Remove normalized/error bookkeeping before IRET; keep software-saved registers distinct from CPU return state.
- Preserve interrupted state for IRQs; define syscall-preserved registers separately. Validate user CS/SS/EIP/ESP and sanitize return flags: IOPL0, no NT/VM, controlled IF/TF/RF and explicit DF policy. Capture CR2 before nesting can overwrite it.
- Source contains no explicit common segment/DF capture shim. **Compiler-emitted ISR behavior was not inspected**, so this audit does not assert exactly which implicit saves the compiler currently emits.

### TSS and continuation design

**Proposed, not implemented:**

- Use a correctly encoded, stable 32-bit TSS descriptor and `ltr`; set SS0 and an owned supervisor kernel-stack ESP0. Deny user port I/O through IOPL0 and an absent/out-of-limit I/O bitmap.
- Keep the bootstrap/shell continuation separate from the application trap stack. Save the launcher’s callee-saved registers, stack, flags and address-space state through a defined assembly call boundary.
- On EXIT, user fault or timeout, first return to a safe kernel continuation/address space; only then release user frames, page tables and the task stack. Never free the stack currently executing cleanup.
- Keep IRQs capture/counter-only. Syscall filesystem work must retain single-main-context ownership, with interrupts enabled when safe. Timer cancellation may redirect a **user** return; do not switch away while kernel filesystem/allocator ownership is live.
- Retain a fatal kernel-fault policy distinct from user termination; existing #PF/common handlers halt the whole context. FPU/SIMD containment is also required: `src/cpu.rs:20–43` only queries vendor, while `target.json:14,21` constrains generated kernel code—not hostile user instructions.

### Capability lifecycle integration

- Existing useful invariants: rights checks (`src/fd.rs:349–361`), attenuating duplicates/shared offsets (`425–443`), last-close refcounts and saturation-based retirement (`446–468`), failed-open rollback (`264–274`). **Historical B07 is already addressed**, not a current leak finding.
- **Do not expose `FdTable::open` directly.** It accepts requested rights without an authority ceiling (`src/fd.rs:250–285`). VFS supplies unrestricted namespace operations (`src/fs/vfs.rs:83–99`); shell directly creates/removes/lists (`src/fs_commands.rs:63–86,101–117,159–166,183–187`).
- Keep task-local public token epochs separate from internal open-record generations. Current API consumes reusable numeric `u8` fds; internal Handle generations do not make stale public fds safe.
- Preserve shell-owned descriptors/cwd: these currently have one static main-loop owner (`src/main.rs:262–279`). Add explicit task-owned close-all/rollback. Separate FdTables do **not** provide cross-context shared offsets because each embeds its own open-record array (`src/fd.rs:178–181`); use an explicit shared registry or document independent-open inheritance.
- Console slots currently have zero rights and no open record (`src/fd.rs:216–245`); normal read/write require file records (`349–378`). User console I/O needs deliberate endpoint support.
- Directory authority requires a confinement policy: normal lookup permits absolute-root restart and mounted-root `..` escape (`src/fs/mounted.rs:444–471`). Preserve semantic `file/..` rejection while adding capability confinement.
- Mount pins must include **all** contexts. Current unmount checks just one FdTable and cwd (`src/fs/mounted.rs:313–334`). `/system` is permanently pinned/read-only (`97–103,503–507`), but archive authentication is not execution authorization (`src/system_image.rs:1–7`; `src/main.rs:323–361`).

### Staged tests to authorize next

1. **Host:** descriptor/TSS encoding with nonzero bases; exact normalized frame layouts/error-vector classification; flags policy; task-token retirement, authority attenuation, inheritance rollback, task-only cleanup, mount pins and confined traversal.
2. **Emitted-code review:** segment/GPR saves, CLD, Rust stack alignment, error-word removal and IRET; verify no compiler-ABI assumptions remain.
3. **Privileged fixtures:** returning #GP/#NP/#SS diagnostics, ring3 IRQs with nondefault/null data segments and DF set, TSS stack switching, user I/O/CLI denial, PDE/PTE isolation, cross-page copy rejection, EXIT/fault/timeout restoration of shell and resource baselines.
4. **Full regression acceptance:** existing ELF/GRUB and RAM-size matrix, allocation refusal, repeated launch/failure cleanup, persistent-I/O poison behavior and guarded-stack/headroom checks.

**Residual safety scope:** Phase9.6 explicitly leaves trap, Port lifetime, mutex guard auto-traits, ring SPSC API, PageMap aliasing and panic/stack contracts unresolved (`docs/PHASE9_6_SAFETY_HARDENING.md:203–205`). Preserve single-owner assumptions or harden them before expanding concurrency.

**Files changed:** none. Final HEAD/status matched initial inspection; existing untracked `d1/` and `scripts/b13_boot_fixture.py.backup` were untouched. No runtime verification is claimed.
