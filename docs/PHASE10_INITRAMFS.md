# Phase 10 implementation status

**IN PROGRESS — not a release or deployment checkpoint.**

Development branch: `maintenance/phase10`. The accepted Phase 9.6 artifacts
and Proxmox VM 103 must remain untouched. No Phase 10 guest acceptance is
claimed by this document.

## Module retention/copy integration — diagnostic only

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
