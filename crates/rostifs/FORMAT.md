# RostiFS v0.1 (wire version 1)

This is the authoritative portable-core format and API contract. The crate is
`no_std`, has no dependencies, uses no heap allocation or unsafe code, and owns
one exclusively borrowed device. It is not compatible with the abandoned
in-place bitmap/inode implementation. No conversion or automatic formatting exists.

## Bounds and layout

* Logical sectors: exactly 512 bytes. Filesystem blocks: 4,096 bytes (8 sectors).
  Translation checks multiplication, addition, full-block capacity and buffer
  length before any I/O; filesystem block 0 is never accessible through it.
* Volume: exactly 7..65,536 complete blocks; 28 KiB..256 MiB. Header geometry
  must match the device's entire reported capacity, including no partial tail.
* 64 node slots including root; at most 63 children in any directory, subject
  to the global slot limit. Names: 1..60 UTF-8 bytes. Paths: 1..256 bytes,
  including canonical absolute path bounds. Controls, slash/backslash in names,
  invalid UTF-8, `.`/`..` creation leaves, and noncanonical padding are rejected.
* File: 0..262,144 bytes, one bounded contiguous extent of 0..64 blocks.
  Nested directories use inline parent/name metadata, not directory data pages.
* Block 0 (sectors 0..7) is reserved and never written by the core. Host image
  creation puts the 14-byte `ROSTI-TESTDISK` marker at sector 0 and zeroes its
  remainder. The marker is a safety guardrail, not authorization or isolation.
* Block 1: root A (bank 0). Block 2: root B (bank 1).
* Blocks 3..4: metadata bank 0. Blocks 5..6: metadata bank 1.
* Blocks 7..end: COW file data.

There is no separate allocation bitmap. Each validated snapshot's extent
inventory is its authoritative allocation metadata. The allocator protects the
**union of both valid roots' data extents**, not just the latest root. Overlapping
extents within one snapshot, extents into metadata, range overflow, references to
free or non-directory parents, cycles, duplicate sibling names, invalid kinds,
size/extent-count mismatch and inconsistent free slots are rejected. Unreferenced
COW residue is reclaimable; it is not a leak or a third committed snapshot.

## Encoding

All integers are explicitly little-endian; structs are never transmuted.
Every root is exactly 4 KiB, zero-padded:

| Offset | Width | Meaning |
|---|---|---|
| 0 | 8 | `ROSTIFS` followed by byte 1 |
| 8 | u32 | format version, exactly 1 |
| 12 | u32 | block size, exactly 4,096 |
| 16 | u32 | total blocks |
| 20 | u32 | bank, exactly 0 for A or 1 for B |
| 24 | u64 | filesystem identifier |
| 32 | u64 | transaction generation |
| 40 | u32 | CRC32C of metadata bank page 0 |
| 44 | u32 | CRC32C of metadata bank page 1 |
| 48 | u32 | root inode reference, exactly 0 |
| 52 | u32 | allocation/data boundary, exactly 7 |
| 56..4092 | bytes | reserved, must be zero |
| 4092 | u32 | CRC32C of root bytes 0..4092 |

Each bank contains 64 consecutive 128-byte node records (32 per page):

| Offset | Width | Meaning |
|---|---|---|
| 0 | u32 | slot-lifetime generation |
| 4 | u8 | kind: free=0, file=1, directory=2 |
| 5 | u8 | parent slot |
| 6 | u8 | name byte length |
| 7 | u8 | reserved zero |
| 8 | u32 | logical file length |
| 12 | u32 | first data block (zero for empty files/directories) |
| 16 | u32 | data block count |
| 20 | u32 | CRC32C of the entire padded data extent |
| 24..84 | bytes | inline 60-byte name; unused bytes zero |
| 84..128 | bytes | reserved zero |

Free records retain only their slot generation; every other byte is zero.
Root is a directory with generation/parent/name length zero and zero data fields.
Directory length and data fields are zero. Empty file CRC/start/count are zero.
File count is exactly ceil(length/4096); writers zero all gaps and final padding.

CRC32C uses reflected Castagnoli polynomial `0x82f63b78`, initial state
`0xffffffff` and final complement. Check vectors: empty=0,
`123456789=e3069283`, `a=c1d04330`. CRC detects accidental corruption, not
malicious changes or cryptographic collisions.

## Commit and recovery

1. Stage one operation in the instance's fixed metadata array.
2. Allocate a whole replacement extent disjoint from both committed snapshots.
   Write new data, including preserved old bytes, zeros, and supplied updates.
3. Explicitly flush all data writes.
4. Write the complete inactive metadata bank and calculate its page CRCs.
5. Explicitly flush metadata writes.
6. Write the inactive CRC-protected root with the next u64 generation.
7. Explicitly flush the root. Only then replace the in-memory committed state.

Creation, removal, replace, offset write, append, and truncate are each one
transaction. Multi-operation shell commands are not one combined transaction.
Successful root publication makes old latest become the previous protected
snapshot; the former older extent set becomes reusable at the next operation.
Conservative retention can make a write fail despite enough space after deleting
or replacing a file. A later metadata transaction advances retention. A whole
contiguous destination is required; fragmentation can also report full.

Any write/flush failure returns `DeviceIo`, leaves the old RAM state visible,
and poisons subsequent mutations until explicit remount. Failure can mean a
complete new root reached media: the commit outcome is deliberately ambiguous.
Mount validates **each root, its whole bank, all references and all file CRCs**,
then selects the higher valid generation. Two valid roots must have matching
filesystem IDs/geometry and adjacent generations. One valid root allows degraded
recovery; no valid root is an error. Any candidate I/O error or unsupported
version fails closed rather than mounting an older snapshot whose allocation
protection might be unknown. Mount performs no writes or repair.

The tested storage model permits rejected/torn sector writes and arbitrarily
reordered/lost unflushed sectors, but a successful `flush()` must durably order
all preceding writes. Driver/firmware dishonesty, arbitrary old-sector damage,
CRC collisions and physical power-loss behavior are not proved. **No physical
power-loss safety claim is made.** Checker reports degraded redundancy as failure;
inspector can display the remaining recoverable snapshot. Neither repairs.

## API and memory

`BlockDevice` requires `sector_size`, `capacity_sectors`, `read_sector`,
`write_sector`, `test_owned`, and **`flush` with no default implementation**.
Default checked helpers: `block_first_sector`, `read_block`, `write_block`.
`BlockError::{OutOfRange, BufferSizeMismatch, Protected, Rejected, Torn}` remain.

`engine::RostiFs::new(&mut dyn BlockDevice)` is `const`. Use it only in a static
const initializer for the kernel, then call `mount_in_place(&mut self)`. The
by-value `new`/`mount` convenience may use large construction stack temporaries;
**do not construct or return a filesystem by value on the boot stack**.
`format(device, fs_id)` exists only under `cfg(test)` or feature `host-tools`.
Other public methods: `mount`, `mount_info`, `metadata_bytes`, `append`.
The existing `vfs::Vfs` signatures remain unchanged: root, lookup, create_file,
create_dir, metadata, read, write, replace, truncate, remove_file, remove_dir,
list, path, stats. Shared-reference reads use fallible `RefCell` borrowing,
not unsafe aliasing; listing callbacks may safely perform another read.

`NodeId` is slot u8 plus slot generation u32. Unrelated transactions and file
updates never invalidate it. Removal increments generation; exhausted slots
retire rather than wrap. Transaction generation u64 also never wraps. Handles
are scoped to their mounted instance/session; do not carry them across recovery,
where selection of an older snapshot can legitimately restore deleted nodes.

Three 64-entry metadata arrays (current, previous, staging), 84 bytes per node,
occupy 16,128 bytes. There is **one shared 4,096-byte scratch buffer in the
instance**, also protected by RefCell. Measured size: **20,296 bytes on the
x86_64 Windows host; 20,276 bytes on i686-unknown-linux-gnu**. No disk-size RAM
bitmap or file-sized staging buffer exists. `metadata_bytes` includes scratch and
device borrow state. `stats.allocated_bytes` counts latest file extents only;
`mount_info.used_blocks/free_blocks` count reserved blocks plus the union of both
snapshots. `valid_roots` reports 1/2 validated roots; `leaked_blocks` is zero
because allocation is derived from references.

Debug i686 assembly inspection measured local stack reservations (including
summed push/sub instructions, not a hardware stack high-water proof):
mount_in_place 896 B, load_candidate 700 B, validate 512 B, change 612 B,
commit 212 B, write_metadata 260 B. The shared scratch is not on the stack.
Kernel driver, caller, interrupt and compiler-version overhead still require
kernel/QEMU verification; host measurements do not prove privileged behavior.

## Host tools

Build with `cargo +nightly build --features host-tools --manifest-path
C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml` from
`C:/Users/iamsv`, outside the repository's kernel cargo configuration.

```
mkrostifs --test-owned-image C:/Users/iamsv/Documents/Rust-OS/dist/<real-subdir>/owned.img --blocks 1024
rostifsck --test-owned-image C:/Users/iamsv/Documents/Rust-OS/dist/<real-subdir>/owned.img
rostifs-inspect --test-owned-image C:/Users/iamsv/Documents/Rust-OS/dist/<real-subdir>/owned.img
```

Only absolute `.img` paths beneath this repository's canonical `dist/` are
accepted. Parent directories must already exist and must not be symlinks.
Physical disks, UNC/device paths, alternate streams, Windows reserved device
filenames, non-regular images and outside paths are refused. Formatting always
uses `create_new`; existing files are never opened writable by the formatter.
Reader tools open read-only and require the test marker. The formatter uses an
OS-seeded `RandomState` hash plus path/process/time for a probabilistic u64 ID;
64-bit collisions remain possible and IDs are not cryptographic UUIDs.
These checks assume no hostile concurrent host directory replacement; they are
operator guardrails, not an adversarial path-race security boundary.

## Host verification

Default `cargo test` executes **20 core tests**, no production fault feature.
`cargo test --all-features` additionally executes **4 host-tool integration
 tests** with real subprocesses, exclusive images, reopen persistence, refusal
and whole-image read-only checks. Temporary owned fixtures are cleaned up.

Measured crash cases derive from successful event traces, not hardcoded write
counts: **2,639** rejected/torn/flush-failure cases across 11 mutation forms;
**2,328** crash cuts with six reversed pending-sector subsets; **4,104**
root-sector cases covering every prefix tear length 0..512 at each of 8 sectors.
Tests compare the complete recovered directory tree and exact file bytes to
old/new snapshots, including unrelated data, and assert poisoning after errors.
Additional coverage includes 240 deterministic modeled mutations with remount,
48 repeated failed-commit/recovery/reuse cycles, corrupt references with correctly
recomputed CRCs, full slots/disk, maximum names/files/paths, generation retirement,
and preserved ownership block. Subset sampling is not exhaustive enumeration of
all possible reorder permutations or arbitrary sector bit patterns.
