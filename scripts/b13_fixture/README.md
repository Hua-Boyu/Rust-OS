# B13 entry fixture and reusable mutation helper

From the repository root:

```bash
python -B scripts/test_b13_boot.py --report test_results/phase9_6/b13_host_NEW.json
python -B scripts/b13_boot_fixture.py --build --run-qemu --production-kernel target/target/debug/kernel --output-dir test_results/phase9_6/b13_qemu_NEW
python -B scripts/test_b13_entry_inject.py
python -B scripts/b13_grub_smoke.py --output-dir test_results/phase9_6/b13_grub_NEW
```

Choose new output directories: guest evidence directories are exclusive-create.
Build the production kernel first (`cargo build`). The injection host suite
reads the isolated fixture ELF, so run it after the fixture build above. The
official acceptance pipeline enforces this same order on a clean checkout.
Do not run alongside any other QEMU harness. The fixture builds to
`target/b13_fixture`, never the canonical kernel target. It links the production
`src/boot.s` and uses the production linker layout with a test-only ELF entry.
It cycles through all incoming ESP residues, sets DF and IF using STD/STI, and
jumps directly to `_start` under STI's one-instruction interrupt shadow.
The naked C entry checks raw ESP, IF/DF, EAX/EBX and both stack arguments.
Exactly 16 `P` debugcon bytes and isa-debug-exit status 33 are required.

The current compiler's ordinary extern-C caller demonstrably uses only four-byte
alignment on `i686-unknown-none` despite `S128`; B13 intentionally establishes a
stronger sixteen-byte **pre-CALL** bootstrap guarantee (callee ESP = 12 mod 16).
The inspection records both generated assembly and linked opcode bytes.

## Pre-entry B11/B18 mutation API

Import `run_injected` from `scripts/b13_entry_inject.py` (scripts is already on
`sys.path` when another script in that directory runs). No GDB executable or
third-party Python packages are needed: this is a bounded local i386 RSP client.

```python
import struct
from b13_entry_inject import run_injected

def mutate(gdb, before):
    root = before['ebx']
    header = gdb.read(root, 116)
    # Construct an explicitly bounded test-owned metadata copy; never blindly
    # follow an injected length or alter firmware/real disk state.
    gdb.write(0x18000, header)
    gdb.set_registers(ebx=0x18000)

report = run_injected(kernel, output, mutate, memory=128,
    serial_markers=('ROSTI: entered kernel_main', 'ROSTI: boot complete', 'rosti>'))
```

The callback runs before `_start`'s first instruction, at an address obtained
from the supplied ELF's symbol table. `read(address, length)`, `write(address,
bytes)` and `set_registers(eax=..., ebx=..., esp=..., eflags=...)` are available.
Writes are read back and recorded; read-only observations may be appended to
`gdb.mutations`. At this Multiboot entry paging is off, so these GDB memory
accesses address the flat physical map. Do not generalize that to later paging.
Use `boot_iso=exact_iso_path` for a GRUB-loaded kernel with the matching ELF.
The GRUB smoke records root flags/mmap fields before entry and then invokes the
existing `paging_test.py --iso ... --output-dir <absolute>` at both RAM sizes.

Only the owned Popen is killed/waited. There is no global orphan-kill, physical
media, attached data image, remote operation, production build or canonical ISO
write. The standalone GRUB stage and ISO have fresh task-owned names under dist.

## Retained harness failures

`b13_qemu_01` and `_02` captured all 16 passing entry bytes but failed the required
process-exit contract. `-no-shutdown` suppresses isa-debug-exit's process exit in
this QEMU; it was removed, not treated as a kernel failure or waived.
The RSP client detaches before guest continuation, avoiding dependence on consuming
GDB exit packets. `_03` completed the full four-guest matrix and owned cleanup.
