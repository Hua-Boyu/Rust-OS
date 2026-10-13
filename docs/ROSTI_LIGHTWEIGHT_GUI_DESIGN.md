# Rosti lightweight GUI — independent design proposal

**Status: DESIGN ONLY / NOT IMPLEMENTED.** Optional text-first/software-rendered UI for the existing i686 kernel. No production source, GRUB configuration, drivers or executable ABI are changed. This does not start Phase 10 or require a GPU, AI stack, SMP, networking or a 64-bit migration.

## 1. Source-grounded starting point

Inspected [`vga.rs`](../src/io/vga.rs), [`kbd.rs`](../src/kbd.rs), [`shell.rs`](../src/shell.rs), [`interrupt.rs`](../src/interrupt.rs), [`main.rs`](../src/main.rs), [`multiboot.rs`](../src/multiboot.rs), [`paging.rs`](../src/memory/paging.rs), [`fd.rs`](../src/fd.rs), [`fs_commands.rs`](../src/fs_commands.rs), [architecture](../ARCHITECTURE.md) and [RostiFSv1](../crates/rostifs/FORMAT.md).

Today the renderer is a mutex-backed 80x25 VGA text writer at `0xb8000`, with serial mirroring and tested wrapped-line Backspace/prompt protection. It writes bytes, not Unicode glyphs. Keyboard IRQ input goes through a fixed raw SPSC ring with latched loss recovery; the shell is currently its sole consumer. BootInfo contains VBE/framebuffer fields and reserves flagged framebuffer ranges, but there is no validated graphics accessor, framebuffer mapper/pixel renderer, mouse decoder, window manager or app GUI API. Presence of struct fields is not implemented graphics support. Runtime PageMap bounds serve the kernel's identity/growth map and cannot simply map arbitrary graphics MMIO.

Official Menuet docs describe CPU-computed transparency and a compact drawing/event API; [example](https://menuetos.net/e64.asm) and [syscalls](https://menuetos.net/syscalls.txt) show redraw/key/button events, wait/check, rectangles and draw begin/end. Adopt only the independently reasoned event/bounded-rendering principle. Do not copy Menuet code/assets, ABI numbers, unlimited direct device access or its unverified assembly-performance claims. See [licensing/source comparison](MINIMAL_OS_COMPARISON.md).

## 2. Goal and deliberate exclusions

A small diagnostic/file-browser/editor interface must remain optional and keyboard-operable. The command shell and serial recovery path must work without display hardware, framebuffer metadata, a mouse, valid persistent disk or GUI memory. Storage actions remain FdTable → MountedFs/VFS → RostiFS → BlockDevice; UI never handles raw sectors or changes the RostiFSv1 format.

Initial scope: text panels, then opaque rectangular CPU-rendered windows with bitmap font, focus, bounded clipping/damage, keyboard events and explicit close. No transparency, animation, wallpaper decoding, retained per-window pixel surfaces, desktop effects, arbitrary shaders, GPU drivers, fonts from untrusted files, clipboard, screenshots to disk, accessibility claims beyond keyboard navigation, or foreign GUI compatibility. Unicode file bytes/names remain preserved; unsupported glyphs use replacement/escaped display, not byte corruption or a claim of full Unicode rendering.

## 3. Ownership and incremental stages

| Stage | Proposed deliverable | Dependency/stop condition |
|---|---|---|
| A | Optional text panel model using existing text hardware | Pure model/clip/input tests, shell regression; no framebuffer requirement |
| B | Validated boot framebuffer plus one opaque kernel diagnostic window | Explicit mapping/reservation/cache policy and bounded renderer verified; no external apps |
| C | At most eight bounded kernel-owned windows, keyboard focus and damage | Input broker/queue loss handling; no scheduler or untrusted payload assumption |
| D | App-owned windows with versioned resource/event calls | Only after [native application boundary](ROSTI_APPLICATION_ABI_DESIGN.md) is implemented and privileged-tested |
| E | Optional PS/2 mouse and later selected hardware acceleration | Separate driver/IRQ authorization and tests, not prerequisite for A–D |

One main-loop UI owner handles model changes and rendering. Introduce a single input broker as the sole consumer of the current keyboard ring; do not have shell and GUI race to pop it. Broker decodes once, tracks state, routes to focus or recovery shell and propagates loss. Existing shell behavior is the reference contract, not replaced with truncated command acceptance.

IRQs never draw, allocate, acquire VGA/FS/frame locks or do disk I/O. Timer ISR only records work; rendering and resource APIs run in main/task context. Model updates, FS operations and rendering are separate steps. Snapshot scalar diagnostics, release guards, then format/draw. No application callbacks while holding GUI guards; no filesystem listing inside a renderer lock. Preserve heap→frame lock order and main-context storage serialization.

Stage A should be explicit opt-in: default raw shell layout remains unchanged so existing VGA/serial acceptance is not accidentally invalidated by a panel taking prompt rows. Focus switch redraws from bounded model state; recovery mode takes display/input ownership and leaves a clean prompt. No second concurrent owner of the VGA writer.

## 4. Framebuffer admission and fallback

For Stage B, boot through unchanged Multiboot v1/GRUB architecture with an **optional future** framebuffer request. Do not issue BIOS `int 0x10` mode changes from protected mode or replace GRUB. Validate flag presence and read packed fields safely before arithmetic. Initially accept only direct RGB 32-bpp modes with nonoverlapping 8-bit channel masks/positions supported by the converter; X byte ignored/zeroed. Reject indexed/text/unknown formats rather than guessing RGB order.

Proposed admission caps: width <= 800, height <= 600, nonzero geometry, pitch >= width*4 and pitch <= 4096 B; checked `pitch * height`, address+length, page-rounded mapping and each row/pixel offset. Prefer a smaller 640x480 mode, but cannot assume the bootloader will provide it. Framebuffer physical span must fit below 4 GiB for this i686 path, must not alias kernel/stack/heap/page tables/modules, and must be kept out of the frame allocator. Validate physical-resource ownership even when the address happens to be identity-mapped. Add an explicit supervisor-only MMIO mapping region instead of relaxing all PageMap bounds. No user mapping of the framebuffer.

Pitch may contain padding; copying width*4*height as one contiguous rectangle is wrong. Write only valid row bytes, preserve padding, and never assume the chosen mode is 640x480. Hardware frontbuffer bytes are mapping/physical residency, not necessarily kernel heap allocation. Report framebuffer aperture and software allocations separately.

Start with a conservative supported MMIO cache mapping policy and volatile writes. Menuet FAQ's MTRR settings are hardware-dependent: never copy arbitrary write-back/write-combining masks into Rosti or alias the same physical range with conflicting memory types. Cache tuning is separately measured/authorized work.

**Failure matrix:** absent flag, unsupported pixel format, high address, invalid pitch/range, mapping failure or allocation refusal disables graphics and reports a bounded serial reason. If boot remains VGA text mode, use existing VGA+serial shell. If GRUB already switched to graphics, writes to `0xb8000` may be invisible: serial is the guaranteed fallback; an allocation-free text raster console is possible only after the frontbuffer itself validated. Otherwise require reboot with a text-mode GRUB option. Do not promise a working VGA display while still in graphics mode.

## 5. Rendering strategy and calculated budgets

Prefer direct opaque rendering plus a reusable 64x32 tile scratch buffer; repaint from bounded window state rather than retain eight window framebuffers. Tearing is initially accepted and documented. Optional one full-screen backbuffer is a later measured tradeoff; full double-buffer composition is not mandatory. Hardware frontbuffer, one software backbuffer, scratch and control structures must never be counted as interchangeable.

Python calculations used these formulas: packed frame = width*height*4; actual frontbuffer = pitch*height; tile = 64*32*4; events = 128*32. **These are proposed bounds/estimates, not measured target layouts.**

| Packed 32-bpp geometry | One frame | Two equal full frames |
|---|---:|---:|
| 640x480 | 1,228,800 B | 2,457,600 B |
| 800x600 | 1,920,000 B | 3,840,000 B |
| 1024x768 | 3,145,728 B | 6,291,456 B |
| 1920x1080 | 8,294,400 B | 16,588,800 B |

The two-frame column is hardware front plus one software backbuffer at packed pitch, **not two additional heap buffers**. Initial admission rejects the last two modes. A 640x480 full frame at 30 updates/s writes 36,864,000 B/s before overdraw/source reads; this is calculated traffic, not measured bandwidth or guaranteed frame rate.

Proposed common nonframe resources:

| Item | Bound |
|---|---:|
| Reusable tile scratch | 8,192 B |
| Global GUI event queue (128 records x 32 B) | 4,096 B |
| Window/command/damage/control arena allowance | 16,384 B |
| Built-in font (256 glyphs x 16 rows x 1 B) | 4,096 B |
| Text shadow (80x25 x 2 B), text mode only | 4,000 B |

Packed 640x480 direct graphics + common resources = **1,261,568 B**; with one backbuffer = **2,490,368 B**. Packed 800x600 direct = **1,952,768 B**. Text mode shadow + events/control/font without tile = **28,576 B**. These totals exclude existing kernel/FS/FD state, software allocation headers, task stacks, mapping tables, page alignment, serial buffering and any app data. Font may be image-resident rather than heap; keep accounting categories distinct. Actual frontbuffer pitch up to 4096 requires its own larger mapped-aperture admission calculation; do not use packed totals as the hardware-span ceiling.

Reserve control/font/scratch statically where appropriate, without constructing large values on the 16 KiB boot stack. Obtain optional buffers fallibly outside guards, enforce a GUI-specific quota independent of RAMFS's 4 MiB payload quota and never consume filesystem allocations silently. Current heap starts at 1 MiB and has a bounded growth window: do not assume a full-screen allocation succeeds simply because machine RAM is 128/512 MiB. OOM downgrades before window publication; release unpublished buffers and return to recovery. Allocation-free repaint must not require disk reads.

## 6. Model, draw protocol and clipping

At most eight windows total, one foreground/input focus, fixed z-order array, generational WindowId scoped to owner task and retired on exhaustion. Store bounded title/text/widget state, not arbitrary callback pointers. The 16 KiB control arena is a provisional cap covering eight window records, a 4 KiB command staging area, at most 32 damage rectangles and metadata; exact target sizes must fit by assertions before implementation is accepted.

Native future GUI extension is versioned and feature-negotiated separately from base ABI. Proposed operations: CREATE_WINDOW, DESTROY_WINDOW, SET_TITLE, SUBMIT_DRAW, POLL/WAIT_EVENT. GUI tokens cannot be shoehorned into the current file Rights byte; use a distinct bounded resource class/registry with explicit ownership. No public pixel pointer, port/IRQ handle or kernel object pointer.

SUBMIT_DRAW uses a copied, explicit LE command buffer at most 4096 B and 64 commands. Only fill rectangle, border, bounded text and clipped line initially. Each command has opcode/byte length and fixed-width coordinates; text is length-delimited, UTF-8 validated, controls escaped and constrained by command-buffer limit. Whole batch is syntactically validated before any visible drawing; source buffer is copied once to prevent mutation during validation/execution. Draw failure before publication leaves previous model intact. Hardware writes themselves are not promised to be atomic; begin/end does not block IRQs or guarantee tear-free display.

Use checked arithmetic and signed clipping for negative/offscreen coordinates before conversion to offsets. Clip to client region, window-visible region and screen; derive row bounds using pitch. Unknown opcodes/flags fail, never treated as trusted memory addresses. Overflow/excess damage coalesces to one full repaint flag, not unbounded rectangle storage. Maximum eight windows and 64 commands keep traversal finite; split repaint into bounded row/tile work units and process pending input between units. Frame pacing is a configurable cap (proposed <=30 Hz), not a timing guarantee; an idle UI uses the established sleep mechanism rather than busy-waiting for events.

## 7. Input/events and responsiveness

Proposed fixed 32-byte event record: `size:u16, version:u16, kind:u32, window_id:u32, sequence:u32, flags:u32, a:u32, b:u32, c:u32`, explicit LE, version 1. Kinds initially KEY, FOCUS, REDRAW, CLOSE_REQUEST, INPUT_LOST; mouse events reserved until a tested driver exists. Delivery is to the owning task only. Payload and window ownership validated, no callbacks from IRQs.

One 128-record global queue is the planning budget, not 128 per window/task. Use bounded owner indexes and quotas, retaining per-owner sticky redraw/close/loss flags outside the queue. Coalesce redraw and future pointer motion; do not silently drop key releases or destructive action boundaries. On raw-ring loss discard the pending snapshot, reset modifiers, invalidate the affected edit/command and notify INPUT_LOST. On GUI queue loss discard affected pending action state, reset logical modifiers and require fresh explicit confirmation before destructive operations; an earlier queued Enter must not acknowledge a later damaged action. Upstream PS/2 controller loss remains an existing unverified limitation.

Keyboard navigation must work without mouse: explicit next/previous focus, activate, cancel and recovery-shell switch. Extended key parsing and Ctrl/Alt tracking are new requirements, not features claimed from today's limited decoder. A recovery hotkey must be broker-owned and cannot be captured by a focused app. Stage C trusted windows cannot supply unbounded callbacks. Stage D malicious app responsiveness depends on the verified user preemption/fault boundary in the ABI design, not merely an event API.

Synchronous ATA PIO/whole-file COW may delay the UI even though interrupts continue enqueueing. Do not promise real-time responsiveness. Bound UI operations and expose busy/error state; defer asynchronous disk workers until scheduling/ownership is separately designed. Never allocate or read FS while holding display guards.

## 8. File UI authority and failure behavior

Browser receives a restricted directory grant and uses descriptor-mediated authorized listing/open, not direct VFS access borrowed from kernel shell internals. Existing shell listing checks/CREATE/DELETE paths are not a ready-made untrusted GUI policy. Preserve semantic mounted traversal, 60-byte persistent names, 256-byte paths and opaque node identities. Escape control characters and show full names through bounded scrolling, never execute display text as shell syntax.

Initial editor is view-only with READ/STAT/SEEK descriptors. A later editor needs an explicit write grant and bounded document size; file save must use a deliberately defined replace transaction rather than truncate-and-write. UI confirmation is not authority. Display DeviceIo/poisoned persistence as uncertain outcome; do not automatically retry, remount, format, repair or declare success. Mounted cwd/open references including duplicates/deleted-open records retain mount pins. GUI teardown closes only its own resources and does not discard shell cwd/descriptors. Corrupt/absent volume leaves RAMFS/serial recovery independent.

## 9. Future verification and open decisions

### Kernel UI versus user-space compositor

| Model | Benefit | Required boundary and cost | Recommendation |
|---|---|---|---|
| Trusted kernel diagnostic UI | Small initial owner, existing recovery/console integration | Only built-in bounded models; no arbitrary app callbacks, filesystem work or rendering from IRQs | Optional early text/opaque diagnostics, not a complete desktop |
| User-space compositor | Window policy/rendering faults can be contained outside the kernel | Validated ring3 processes, IPC/resource ownership, copied bounded present requests and protected input; software surfaces/IPC buffers must be budgeted | Prefer for future application UI after actual isolation tests |
| Minimal kernel present/input mechanisms plus user policy | Retains clipping/physical ownership and recovery independence while keeping rich UI policy out of core | Explicit framebuffer/window grants, bounded blit/present contract, exclusive input broker; no raw MMIO/IRQ/ATA authority for apps | Long-term architectural direction, design only |

Do not force compositor/window state into heap/frame/filesystem owners. A
compositor crash must not block the independent serial recovery shell or release
another task's windows/descriptors. No current process/IPC boundary exists, so
these are future options rather than implementation choices already available.

### Optional remote framebuffer transport

Defer until networking, authentication/encryption and task isolation exist. A
future read-only view can send bounded dirty tiles/rectangles with versioned
geometry/length fields, reuse a fixed staging buffer and coalesce overflow into
a full-redraw request rather than queue unlimited frames. Authenticate remote
input separately from viewing; do not interpret pixel data or event text as
shell commands or grant disk/mount authority. Network IRQs enqueue only; they
must not render, allocate or access FS. Account packet/staging/backpressure memory
separately from the local framebuffer budget. No RFB/VNC protocol compatibility,
server, encryption or remote-input functionality is implemented or benchmarked.

No tests/builds/QEMU were run for this design. Implementation acceptance, when authorized, must include:

- Host pixel vectors for every admitted RGB mask/pitch; arithmetic overflow, clipping, partial rows, padding preservation, malformed commands and prepublication rejection.
- Host ownership/generation retirement, arena/queue exhaustion, redraw coalescing, loss around Enter/key release, focus routing, explicit close and resource cleanup.
- Privileged ELF/GRUB at 128/512 MiB: valid optional framebuffers, forced absent/invalid metadata, mapping/buffer OOM, text-mode boots, actual visible fallback and serial recovery. Verify pixels independently; serial output alone cannot prove rendering.
- Keyboard-only usability, prompt/Backspace/overflow regressions, no allocation/FS/VGA from IRQ, interrupt progress during tiled repaint and disk operations, bounded stack high-water and actual resident memory.
- All existing Phase 9 gates unchanged; Stage D additionally requires verified application isolation and task fault recovery. No remote changes or physical display claims follow from emulator tests.

Open decisions: Multiboot mode-request packaging, safe MMIO mapper/cache policy, concrete control-arena layout, input extended-key state machine, dirty-region fairness and GUI public-token encoding. Measure before choosing full buffering/transparency; keep the text/serial path permanently supported.
