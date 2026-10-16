# Phase 10B implementation and acceptance

## Phase 10B COMPLETE — local acceptance verified

Source checkpoint: `449ed434ed5dbf1518b99821178a5fcd1d343b75` on `maintenance/phase10`.
Full acceptance: **PASS 53/53 gates**, invocation-owned
**56/56 initramfs scenarios, 3379/3379 matrix checks**.
Evidence: `test_results/phase10b/acceptance_20261016T120546Z_psboeekn/acceptance.json`;
independent closeout: `test_results/phase10b/final_verification.json`.
All 134 source/build inputs were independently rediscovered and hash-matched.
Scoped independent review: no blocking findings (`test_results/phase10b/independent_scoped_review_20261016T111204Z_f632dad1df.json`).

Trusted complete-byte SHA-256 verification precedes parse/publication at read-only
`/system`. The kernel is the trust anchor, not the module. Real GRUB and injected
ELF recovery, allocator exhaustion, mount failure and reboot are covered at
128/512 MiB. No archive code is executed; RAMFS recovery is independently owned.
Host serial/parallel: **265 passed, zero failed, two ignored** each. Inherited
B11/B13/B18/B26, CPU faults/paging, keyboard/VGA, growth/OOM, ATA/RostiFS and all
9,071 modeled crash cases remain covered. Old failures below are historical.

Accepted ISO: `dist\rosti_phase10b_20261016T120546Z.iso` (11096064 bytes), SHA256
`117c7b2c0a1f21dc53442a7a1c558b45b8367cb163d405d4d6ef5956596993d8`. Independently extracted production kernel SHA256:
`f292cd2e406487ead05a2b9008e0cf6bf39d145b122f7ebac160ba4d1c53386f`. Fixture features are excluded.
No local QEMU remains. Historical Phase 9.6 ISO is unchanged.

No Phase 10 deployment, VM/storage mutation, Phase 11, tag or history rewrite.
Fresh read-only inspection shows VM 103 running Phase 9.6 ISO, 512 MiB/one vCPU,
SeaBIOS/pc, no data disk; stale Phase 7 references below are historical.
Commit/push of completed Phase 10B is explicitly authorized. Unrelated `d1/`
and `scripts/b13_boot_fixture.py.backup` stay excluded and preserved.

Limits: trusted-loader/single-owner ring-0 assumptions; no hardware secure boot
or hostile-userspace isolation. Runtime heap/stack high-water is **unknown**.
The 546,228-byte import capacity bound excludes allocator overhead/fragmentation
and is not a measured peak. Guest malformed/truncated images prove digest
rejection; authenticated structural-parser rejection is covered on the host.
See `docs/PHASE10_INITRAMFS.md` for exact contracts and retained failures.

## Final artifact and resource accounting

- Production ELF: 5970396 file bytes; 1958406
  SHF_ALLOC bytes, of which 820730 initialized; static address span
  1969164 bytes. Debug bytes are not resident RAM.
- Versus independently extracted accepted Phase 9.6: file +691848,
  allocated +131136, initialized +131572,
  static span +130636 bytes. Full section table:
  `test_results/phase10b/final_resource_sections.json`.
- Complete system archive: 1,024 bytes, SHA256
  `8ff3bfdc925e1b0e60441b072f4c4c0c4f6b16f68dfce0c0ff50bb609d64a6a7`.
  Limits: 256 KiB complete input, 32 explicit entries, 64 KiB/file,
  255-byte relative path and 63-byte component. No decompression/symlink/device
  execution or dynamic unmount is provided.
- Compile-time import capacity bound: input 262,144 + indexes 17,152 + snapshot
  266,932 = 546,228 bytes; excludes allocator overhead/fragmentation and stack.
  Runtime heap/stack peak remains null, not inferred from this bound.
- Guest timing uses a 100 Hz PIT (10 ms granularity), not sub-ms measurements.
  Final guest reports retain memory/system snapshots, growth/PTE evidence,
  media hashes, QEMU identity and verified cleanup.

## Review and claim boundaries

Independent review has no blockers in its trust/mount/recovery/harness scope;
reviewed runtime/kernel hashes match, with later harness changes covered by
the separate bounded lock/count/attribute follow-up review. It is not a general unsafe/paging/allocator
audit. Broader B19/public-API/exception/stack findings remain outside scope.
Review S1 suggests an optional final guest content reread after all denied
mutations; the current oracle checks listing, with unchanged content enforced
by backend/routing host tests and earlier focused guest evidence. No optional
change was applied during the frozen run. Review S2 distinguishes guest
DigestMismatch for malformed/truncated production-pinned images from host
authenticated structural-parser checks. Do not claim otherwise.

## Retained failed attempts and diagnosed corrections

Six failed and two aborted acceptance directories are retained, alongside their failing
aggregate and relevant gate logs:

- `acceptance_20261015T222050Z_1hv_dup5`: B26 compile failed on missing `alloc`;
  explicit crate import restored the independently rooted host fixture.
- `acceptance_20261015T222704Z_r10hprwr`: ISO RAMFS cleanup incorrectly expected
  an empty root after legitimate `/system` publication; now asserts equality
  with the captured baseline listing.
- `acceptance_20261015T230854Z_9e32askh`: guest matrix timed out. Oversized RSP
  injection exceeded stub packet bounds; writes and reads now chunk and verify
  each chunk. Full matrix budget accommodates all strict workloads.
- `acceptance_20261016T001517Z_lnwa0gjl`: all 10 boot rows passed but global
  orphan check failed after the prior timed-out matrix. It remains FAIL.
- `acceptance_20261016T004624Z_l53tp5aj`: B13 fixture missed strict exit/markers.
  STI+JMP consumes the interrupt shadow before destination CLI, allowing a PIC
  IRQ with no test IDT. Masking IRQ sources retains IF=1/DF=1 and all stack/ABI
  assertions; 40/40 strict stress replays and final acceptance pass.

- `acceptance_20261016T105259Z_3f7c1scc`: all 53 runtime gates passed, but
  the final aggregate rejected 103 RAMFS checks against stale 102. Preserved
  FAIL; the corrected exact contract and attribute freeze required a fresh run.
- `acceptance_20261016T113923Z_a014ckrm` and
  `acceptance_20261016T115632Z_t2de_xv1`: ABORTED after independently started
  runners overlapped. Neither contributes release acceptance.

No markers, expected matrix rows, crash cases, privileged assertions, media
checks or cleanup requirements were removed to achieve PASS. Historical
positive-probe failures and earlier bounded reviews remain below for context.

## Exact accepted count index

```json
{
  "host": {
    "pass": 265,
    "fail": 0
  },
  "b11": {
    "pass": 12,
    "fail": 0
  },
  "b18": {
    "pass": 46,
    "fail": 0
  },
  "b26": {
    "pass": 9,
    "fail": 0
  },
  "rostifs_host": {
    "pass": 23,
    "fail": 0
  },
  "rostifs_tools": {
    "pass": 4,
    "fail": 0
  },
  "rostifs_read": {
    "pass": 4,
    "fail": 0
  },
  "rostifs_write": {
    "pass": 3,
    "fail": 0
  },
  "b13_host": {
    "pass": 3,
    "fail": 0
  },
  "b13_qemu": {
    "pass": 4,
    "fail": 0
  },
  "boot_metadata": {
    "pass": 53,
    "fail": 0
  },
  "boot_metadata_scenarios": {
    "pass": 44,
    "fail": 0
  },
  "elf": {
    "pass": 8,
    "fail": 0
  },
  "boot_128": {
    "pass": 10,
    "fail": 0
  },
  "boot_512": {
    "pass": 10,
    "fail": 0
  },
  "phase10_scenarios": {
    "pass": 56,
    "fail": 0
  }
}
```

Full detailed index: `test_results/phase10b/acceptance_20261016T120546Z_psboeekn/acceptance.json` and
`test_results/phase10b/final_verification.json`; do not add aggregate checks to
child checks as though they were disjoint tests.

### Final reproducibility and exclusive-execution closure

Selected sanitized reports, CSVs and clean gate logs are committed. Nine raw
host logs with generated trailing blank lines remain unchanged locally rather
than weakening Git whitespace checks; their exact hashes and full numeric test
and crash-case results are retained in `sanitized_host_results.json`. Raw media,
ELFs, VGA/serial captures and QEMU debug logs remain local, excluded from Git.

The RAMFS baseline-root listing legitimately adds one `VGA prompt after ls` row:
all four complete workloads now have exactly 103 checks, with zero inherited
checks removed. RED/GREEN regressions accept 103 and reject both 102 and 104
before publication. The full runner retains exact ATA/RostiFS counts 98/168.

`system/** -text` in `.gitattributes` preserves trusted asset bytes under Windows
`core.autocrlf=true`; a fresh staged-index checkout reproduced the exact archive
and pinned digest. No asset normalization or trust-anchor change was made.
Attributes are now included among the 134 frozen inputs. This proves narrow
asset-byte reproducibility, not cross-configuration raw hashes for every source.

Two independently launched pipelines overlapped before the guard existed; both
were stopped only through verified task-owned runner trees and preserved as
ABORTED (original reports retained alongside interruption evidence). The final
accepted run is exactly `acceptance_20261016T120546Z_psboeekn`, not whichever
report sorts last. The desktop worker won the new lock; the completion agent
adopted its matching frozen run, and its own contender correctly exited 2.

The runner now holds a nonblocking OS lock at `dist/.phase6_acceptance.lock`
from before report creation/builds through final production restoration. Never
unlink that file to clear a PID: OS handle lifetime releases ownership on exit.
Real Windows and WSL POSIX tests cover contention, normal release and forced
owner exit; all 35 acceptance-harness host tests pass. A live canonical contender
created no report and started no work. Native Windows venv redirectors are only
wrappers, so forced-owner tests use the actual base interpreter. This guard
coordinates cooperating runners on each OS; it is not a general barrier to
manual builds, standalone QEMU or mixed-runtime/remote work.

`independent_lock_followup_review.json` records a separate no-blocker excerpt
review of the final guard/count/attribute changes. Its scope and supplied-test
premises are explicit; the actual contextmanager decorator was also checked.
`exclusive_runner_exit.json` records exit 0 through a captured Windows process
HANDLE. `exclusive_process_watchdog.json` records sampled QEMU ancestry; no
unowned guest was observed. Sampling is not continuous absence proof.
All evidence paths above are beneath `test_results/phase10b/`.

## Historical implementation notes (not current status)

# Phase 10 implementation status

**IN PROGRESS — not a release or deployment checkpoint.**

Development branch: `maintenance/phase10`. The accepted Phase 9.6 artifacts
and Proxmox VM 103 must remain untouched. No Phase 10 guest acceptance is
claimed by this document.

## Phase 10B integration progress (not final acceptance)

The module descriptor's reserved word is ignored by the OS as required by the
Multiboot v1 consumer contract; the loader must still write zero. GRUB 2.12's
producer leaves it uninitialized. This is not a sentinel or authentication token.
Only the module-word zero check changed; meaningful descriptor bounds, overlaps,
labels, reservations and identity-map/pin checks remain enforced. Evidence and
independent scoped review: `test_results/phase10b/grub_consumer_review_01.json`.
The failed historical positive probe below is preserved, not current behavior.

Boot now authenticates the entire owned module copy with SHA-256 against
`src/system_image.rs::EXPECTED_SHA256`, using `sha2` software-only/no_std and
`subtle` fixed-length comparison. The pinned digest is
`8ff3bfdc925e1b0e60441b072f4c4c0c4f6b16f68dfce0c0ff50bb609d64a6a7`.
Every archive byte, including padding, is covered. The trust assumption is an
independently trusted kernel image; this is not hardware secure boot. Verified
bytes are parsed before constructing an owned `ArchiveFs`, then transactionally
published at `/system`; no archive commands are executed. RAMFS recovery and
persistent-storage eligibility remain independent of archive acceptance.

Real-GRUB publication was tested RED then GREEN at 128/512 MiB in
`test_results/phase10b/trust_mount_red` and `trust_mount_green`. Separate QMP
shell checks passed at both sizes in `real_grub_shell_128_odvkyrt0` and
`real_grub_shell_512_5n9sz9bw`: exact reads/listing, all six shell mutation verbs
denied, trusted bytes unchanged, and RAMFS write/read/delete recovery. The
initial listing-expectation failure is retained (`docs/`, not `docs`).

The opt-in `initramfs-failure-test` kernel exposes an initialized-data mode byte
for pre-entry injection: existing `/system` collision, failure after creating a
mountpoint, and real allocator exhaustion. The last fixture uses bounded static
buffer metadata and fallible allocation tiers, attempts the real archive build,
drops all pressure, and checks failed-allocation growth plus restored used/live
accounting before printing success. Its ELF128 RED/GREEN evidence is
`real_oom_red` / `real_oom_green`. It must not be packaged as production.

Production and fixture builds pass. Host suite and complete ELF/ISO recovery
matrix are being reverified; these focused runs are NOT Phase 10 acceptance.
No release, deployment, commit or push is claimed here. The sections below
record historical slices and their then-outstanding work.

## Module retention/copy integration — diagnostic only (historical)

The inventory now retains owned printable ASCII module labels (63 bytes maximum)
and selects exact `rosti.initramfs` labels, rejecting ambiguity without releasing
accepted reservations. Main retains the selected descriptor after inventory drop.
`memory::boot_copy` limits the copy to 256 KiB and requires active paging, permanent
pins and identity translation for every intersecting page. No PageMap borrow spans
fallible allocation/heap growth. No public arbitrary physical slice is exposed.
The temporary copy and parser index are dropped after diagnostics; **no image
content is trusted or published**.

Latest production build passed. Parallel and serial host runs each passed
**243 tests, zero failures, two ignored**. Injected ELF probes passed valid,
corrupt, absent, ambiguous and oversized cases at both 128 and 512 MiB (10 cases).
The pre-hook RED guest booted but lacked the new marker; `module_probe_red`
preserves it. Latest ordinary no-module boots passed 10/10 at each RAM size in
`module_slice_boot_128/512`. Aggregate: `test_results/phase10/module_slice_verification.json`.
Independent static review returned `no_findings` in `module_slice_review.json`;
all reviewed source hashes were independently matched to the working tree.
These are copy/parser probes, not mounted-system or full recovery acceptance.

### Real GRUB module compatibility blocker

A real GRUB `module /boot/system.cpio rosti.initramfs` directive supplied the
correct label/payload but a nonzero reserved descriptor field (`0xfffffffc`).
The inherited validator safely rejects this as `BootError::Module`; validation
was **not weakened**. The failed success attempt is preserved under
`grub_module_probe_01/boot_128`. Diagnostic serial is retained under
`grub_module_inspect`.

A separate explicit negative test under `grub_module_refusal_02` verified
metadata rejection, storage-gate closure and boot completion at both RAM sizes.
Its PASS means safe refusal, **not successful GRUB archive import**. The observed
descriptor is recorded in `observed_descriptor.json`. The new local fixture ISO's
ELF was independently extracted and matched byte-for-byte to the production ELF.
The accepted Phase 9.6 ISO and VM 103 remain untouched.

Resolve this loader/specification compatibility contract before claiming a
successful real GRUB module boot. Trusted digest verification, `/system` mounting
and the complete keyboard/VGA/OOM/recovery matrix remain outstanding.

## Host archive builder

`scripts/build_initramfs.py SOURCE dist/NAME.cpio` creates a new file exclusively
and refuses overwriting an existing target. Output is restricted to `.cpio`
files directly under this repository's `dist` directory. Inputs are trusted
build-tree files, not an adversarial concurrently modified directory tree.
Symlinks, special files and hardlinked regular files are rejected.

The deterministic archive uses uncompressed CPIO newc (`070701`), uid/gid and
mtime zero, regular-file permissions 0644, directory permissions 0755, ordered
entries, four-byte name/data alignment and final 512-byte padding. Limits:
256 KiB complete archive, 32 explicit entries, 64 KiB per regular file,
255-byte relative paths (256 including the VFS leading slash) and 63-byte
components. Empty directories are retained.
No package manager, execution or decompression is provided.

The command prints SHA256 of the complete output. **This alone is not image
authentication.** Expected-digest pinning in a trusted kernel build and boot-time
verification are not yet integrated; an image-provided digest is not a trust root.

Builder checks: `python -B scripts/test_build_initramfs.py` passed seven tests,
including entry/archive limits, reserved trailer-name refusal and the absolute
VFS path-size boundary. GNU cpio
in WSL independently
listed `dist/phase10_builder_check.cpio` and
reported its `hello.txt` entry as 11 bytes. A separate GNU-produced newc fixture
was generated under `test_results/phase10/gnu_newc.cpio` for interoperability
checking; it is not a production system image.

## Earlier host-only no-module boot regression

`cargo +nightly build` succeeded for the production target. The resulting ELF
passed ordered entry/boot-complete markers in ten independent local QEMU boots
at each of 128 and 512 MiB. Commands used `scripts/boot_test.py --runs 10
--timeout 5 --memory 128|512` with separate evidence directories:
`test_results/phase10/host_slice_final_boot_128` and `host_slice_final_boot_512`.
Initial smoke evidence is retained in the corresponding `host_slice_boot_*`
directories. Final runs used the rebuilt production ELF.
Both final CSVs were independently parsed: exactly ten PASS rows per RAM size;
no `qemu-system-i386.exe` process remained. These are ordinary no-module ELF
boot regressions only: the archive is not yet wired into kernel boot, so these
runs do not prove initramfs, GRUB, mounted `/system` or recovery acceptance.

## Remaining Phase 10 acceptance scope

The earlier repaired parser/backend host slice passed the kernel host harness:
232 passed, zero failed, two ignored benchmarks (234 total). Parent verification
log: `test_results/phase10/parent_host_verification.log`; aggregate scope and
source hashes: `test_results/phase10/host_slice_verification.json`. The snapshot
owns copied payloads, builds transactionally with fallible reserves, and rejects
mutations with `FsError::ReadOnly`. Host correctness does not establish physical
module lifetime, identity mappings, real allocator exhaustion or guest boot.

Still required before release:

- Resolve actual GRUB module reserved-field compatibility, preserving the failed
  positive probe and existing fail-closed policy until reviewed.
- Extend the diagnostic-only retained-descriptor/copy path into trusted publication.
- Trusted expected-digest verification before namespace publication.
- Read-only `/system` mount alongside `/mnt/rosti`, explicit ownership and
  transactional attachment/lifecycle diagnostics.
- Bounded startup-data handling with independent kernel-owned RAMFS recovery.
- Complete absent/rejected/corrupt/OOM recovery matrices through ELF and GRUB,
  at 128 and 512 MiB, with disposable-media hash and cleanup evidence.
- Extended fail-closed acceptance runner, independent review, resource budgets,
  source freeze, versioned ISO/extracted-kernel hashes and updated handover.

No commit, push, tag or Proxmox modification is implied by this in-progress work.
