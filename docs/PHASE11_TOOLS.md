# Phase 11 tool manifest

## Current Phase 11A.2 continuation tooling

Evidence root: `test_results/phase11a2_continuation/`. `run_step.py` records
exact commands/cwd/timestamps/logs and actual subprocess statuses, including
intended RED exits. The standalone blocker probe compiles the real memory
modules with `rustc +nightly --test --edition=2024`; three actual assertion
failures are retained, not fabricated output or acceptance successes.
The inherited sequential driver `verify_registry.py --full-acceptance` runs
host serial/parallel, production build, focused local128/512MiB paging and
ELF/GRUB growth before invoking the official `scripts/phase6_verify.py`.
Its current run is `test_results/phase11a2_registry/run_20261017T175909_983725Z/`
(58/58 PASS, exit 0, including the new mandatory exception-ABI gate family).
It uses notified background execution; no source edits or competing QEMU may
occur during canonical acceptance. Never unlink the acceptance lock.
Final exact status and artifacts: `docs/PHASE11_HANDOVER.md`. The continuation
closeout independently rediscovers input membership/hashes and extracts ISO
payloads. No optional tools were installed; historical versions follow below.

## Historical Phase 11A.2 registry-repair invocation

Actual invocation:
`python -B test_results/phase11a2_registry/verify_registry.py --full-acceptance`.
Exact commands, working directories, timestamps, statuses, version-probe output,
host/build logs and guest evidence are retained under
`test_results/phase11a2_registry/run_20261017T152028_345139Z/`.
The two RED invocations and implementation limits are recorded in
`docs/PHASE11A2_REGISTRY_HANDOVER.md`. Main host284/0/2 ignored, B26-root51/0,
formatting, production build, paging and focused ELF/GRUB growth have exited0.
Fresh inherited prerequisite acceptance PASS56/56, actual runner exit0; read-only
closeout also exits0 and verifies139 input hashes/159 nested reports/280 cleanup
assertions, eight reviewed hashes, ISO contents and no QEMU remains. No full
ownership/TSS/CPL3 approval is claimed. No tools were installed.
Fresh exit0 probes record rustc1.101.0-nightly(1d81eb4ad),
Cargo1.101.0-nightly(f3865b2a4), Git2.55.0.windows.3 and Python3.11.15 in the
run logs. The exact QEMU `--version` command/output/status is additionally in
`test_results/phase11a2_registry/auxiliary_tools.json`: QEMU10.2.0.
Prior manifest entries below describe earlier checkpoints, not this tree.

## Phase 11A ownership/GDT continuation

Fresh probes and exact subprocess output are recorded in
`test_results/phase11a_ownership/tools.json`: rustc 1.101.0-nightly
(1d81eb4ad), Cargo 1.101.0-nightly (f3865b2a4), Clippy 0.1.101,
Git 2.55.0.windows.3, Python 3.11.15 and QEMU 10.2.0, each exit0.
The WSL combined availability probe exited0 and printed GNU binutils2.42,
GRUB2.12-1ubuntu7.3 and GDB15.1; its status is for the combined command,
not independently captured statuses for each semicolon-separated program.
No optional tool was installed. No GDB or Clippy kernel analysis is claimed.

Actual verification commands/results, with logs under that same evidence root:
- `cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml --lib heap_growth_maps_one_page_on_demand -- --exact`
  from `C:/Users/iamsv`: RED exit101 (missing new owned snapshot API), GREEN
  exit0, one test. Old API retained a reference across growth; new test retains
  only the copied before-value and verifies fresh mapping/count/permission data.
- Same manifest, `--lib phase11_gdt_tests:: -- --test-threads=1`: RED exit101,
  three intended access-byte failures; GREEN exit0, three pass.
- Same manifest, ordinary host tests default and `-- --test-threads=1`:
  exit0, 273 passed/0 failed/2 ignored each. B26 full host crate exit0,37 pass.
- `cargo build`: exit0 (`build_green.log`); `cargo fmt` and host formatting
  applied only the changed regions; later canonical formatting is mandatory.
- `python -B scripts/test_acceptance_harness.py`: RED exit1 (eight assertions
  across39 tests), GREEN exit0/all39 pass. Two new mandatory exact-identity
  gates retain all54 predecessor gates; no CPL3 acceptance claim.
- `python -B scripts/paging_test.py --output-dir <absolute-evidence-path>`:
  sequential128/512MiB. The initial relative output path caused a pathlib
  `relative_to(PROJECT)` harness error after the128MiB capture, exit1; its
  raw evidence is retained. The absolute-path retry exits0. Do not label the
  failed invocation a kernel fault or discard it.
- `python -B scripts/fs_test.py --ram 128|512 --stress --output-dir <absolute-path>`:
  sequential local owned guests; exact commands/statuses in `focused_retry.json`.

The canonical runner and final closeout results are recorded in the current
A–K handover; historical tool and acceptance records below remain unchanged.

Final actual command: `python -B scripts/phase6_verify.py --output-dir C:/Users/iamsv/Documents/Rust-OS/test_results/phase11a_ownership`,
notified background, exit0, PASS56/56. `runner_exit.json` captures the real
subprocess status and UTC start/end. Report:
`acceptance_20261016T234702Z_x057jmpa/acceptance.json` beneath the current root.
Read-only `python -B test_results/phase11a_ownership/verify_checkpoint.py test_results/phase11a_ownership/acceptance_20261016T234702Z_x057jmpa/acceptance.json`
exited0:136 frozen inputs/159 nested reports/29 reviewed raw hashes/production
ISO extraction and final QEMU absence verified. Final verification is repeated
after the documentation commit; no source/build inputs changed during freeze.

Read-only discovery at 2026-10-16T15:37:59.271844+00:00. No optional tools installed.
Full raw commands, output and statuses: `test_results/phase11/tools.json`;
reproducer: `python -B test_results/phase11/discover_tools.py`.

Production uses LLVM integrated assembly (`global_asm!`) and rust-lld, not GNU
as/ld; GNU availability is recorded for independent inspection. Custom target
`target.json` uses non-PAE i686 softfloat, core/alloc build-std. Miri and Kani
are not presumed capable of kernel verification.

## Rust nightly

- Classification: mandatory
- Purpose: Production custom i686 compilation
- Executable: `C:\Users\iamsv\.cargo\bin\rustc.EXE`
- Command arguments: `["rustc", "+nightly", "-vV"]`
- Exit status: 0
- Outcome/version: rustc 1.101.0-nightly (1d81eb4ad 2026-10-07)
- Log: `test_results/phase11/tools.json`

## Cargo

- Classification: mandatory
- Purpose: Host tests and production build
- Executable: `C:\Users\iamsv\.cargo\bin\cargo.EXE`
- Command arguments: `["cargo", "+nightly", "-V"]`
- Exit status: 0
- Outcome/version: cargo 1.101.0-nightly (f3865b2a4 2026-09-29)
- Log: `test_results/phase11/tools.json`

## rustfmt

- Classification: mandatory
- Purpose: Rust formatting
- Executable: `C:\Users\iamsv\.cargo\bin\rustfmt.EXE`
- Command arguments: `["rustfmt", "+nightly", "-V"]`
- Exit status: 0
- Outcome/version: rustfmt 1.11.0-nightly (1d81eb4ad9 2026-10-07)
- Log: `test_results/phase11/tools.json`

## rustup

- Classification: mandatory
- Purpose: Resolve actual toolchain
- Executable: `C:\Users\iamsv\.cargo\bin\rustup.EXE`
- Command arguments: `["rustup", "show", "active-toolchain"]`
- Exit status: 0
- Outcome/version: nightly-x86_64-pc-windows-msvc (overridden by 'C:\Users\iamsv\Documents\Rust-OS\rust-toolchain.toml')
- Log: `test_results/phase11/tools.json`

## GNU assembler

- Classification: mandatory
- Purpose: Inspect available assembler; production uses Rust global_asm
- Executable: `C:\WINDOWS\system32\wsl.EXE`
- Command arguments: `["wsl", "bash", "-lc", "command -v as; as --version"]`
- Exit status: 0
- Outcome/version: /usr/bin/as
- Log: `test_results/phase11/tools.json`

## GNU linker

- Classification: mandatory
- Purpose: Inspect available linker; production uses rust-lld
- Executable: `C:\WINDOWS\system32\wsl.EXE`
- Command arguments: `["wsl", "bash", "-lc", "command -v ld; ld --version"]`
- Exit status: 0
- Outcome/version: /usr/bin/ld
- Log: `test_results/phase11/tools.json`

## GNU GRUB

- Classification: mandatory
- Purpose: BIOS ISO packaging
- Executable: `C:\WINDOWS\system32\wsl.EXE`
- Command arguments: `["wsl", "bash", "-lc", "command -v grub-mkrescue; grub-mkrescue --version"]`
- Exit status: 0
- Outcome/version: /usr/bin/grub-mkrescue
- Log: `test_results/phase11/tools.json`

## QEMU i386

- Classification: mandatory
- Purpose: Privileged guest execution
- Executable: `C:/Program Files/qemu/qemu-system-i386.exe`
- Command arguments: `["C:/Program Files/qemu/qemu-system-i386.exe", "--version"]`
- Exit status: 0
- Outcome/version: QEMU emulator version 10.2.0 (v10.2.0-12105-g0f12d445bd)
- Log: `test_results/phase11/tools.json`

## Python

- Classification: mandatory
- Purpose: Acceptance orchestration
- Executable: `C:\Users\iamsv\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`
- Command arguments: `["C:\\Users\\iamsv\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe", "--version"]`
- Exit status: 0
- Outcome/version: Python 3.11.15
- Log: `test_results/phase11/tools.json`

## Git

- Classification: mandatory
- Purpose: Checkpoint and diff verification
- Executable: `C:\Program Files\Git\mingw64\bin\git.EXE`
- Command arguments: `["git", "--version"]`
- Exit status: 0
- Outcome/version: git version 2.55.0.windows.3
- Log: `test_results/phase11/tools.json`

## SHA-256

- Classification: mandatory
- Purpose: Artifact hashing; hashlib also used
- Executable: `C:\Program Files\Git\usr\bin\sha256sum.EXE`
- Command arguments: `["sha256sum", "--version"]`
- Exit status: 0
- Outcome/version: sha256sum (GNU coreutils) 8.32
- Log: `test_results/phase11/tools.json`

## objdump

- Classification: optional
- Purpose: Emitted i686 instruction inspection
- Executable: `C:\WINDOWS\system32\wsl.EXE`
- Command arguments: `["wsl", "bash", "-lc", "command -v objdump; objdump --version"]`
- Exit status: 0
- Outcome/version: /usr/bin/objdump
- Log: `test_results/phase11/tools.json`

## readelf

- Classification: optional
- Purpose: ELF section and segment inspection
- Executable: `C:\WINDOWS\system32\wsl.EXE`
- Command arguments: `["wsl", "bash", "-lc", "command -v readelf; readelf --version"]`
- Exit status: 0
- Outcome/version: /usr/bin/readelf
- Log: `test_results/phase11/tools.json`

## GDB

- Classification: optional
- Purpose: Optional QEMU remote debugging
- Executable: `C:\WINDOWS\system32\wsl.EXE`
- Command arguments: `["wsl", "bash", "-lc", "command -v gdb; gdb --version"]`
- Exit status: 0
- Outcome/version: /usr/bin/gdb
- Log: `test_results/phase11/tools.json`

## llvm-objdump

- Classification: optional
- Purpose: Optional alternate disassembler
- Executable: `None`
- Command arguments: `["llvm-objdump", "--version"]`
- Exit status: None
- Outcome/version: [WinError 2] The system cannot find the file specified
- Log: `test_results/phase11/tools.json`

## Clippy

- Classification: optional
- Purpose: Optional Rust linting
- Executable: `C:\Users\iamsv\.cargo\bin\cargo.EXE`
- Command arguments: `["cargo", "+nightly", "clippy", "-V"]`
- Exit status: 0
- Outcome/version: clippy 0.1.101 (1d81eb4ad9 2026-10-07)
- Log: `test_results/phase11/tools.json`

## Miri

- Classification: optional
- Purpose: Optional host pure-code checking, not kernel execution
- Executable: `C:\Users\iamsv\.cargo\bin\cargo.EXE`
- Command arguments: `["cargo", "+nightly", "miri", "--version"]`
- Exit status: 1
- Outcome/version: error: 'cargo-miri.exe' is not installed for the toolchain 'nightly-x86_64-pc-windows-msvc'.
- Log: `test_results/phase11/tools.json`

## Kani

- Classification: optional
- Purpose: Optional bounded pure-code proof, not custom target support
- Executable: `C:\Users\iamsv\.cargo\bin\cargo.EXE`
- Command arguments: `["cargo", "kani", "--version"]`
- Exit status: 101
- Outcome/version: error: no such command: `kani`
- Log: `test_results/phase11/tools.json`

## cargo-fuzz

- Classification: optional
- Purpose: Optional host parser fuzzing
- Executable: `C:\Users\iamsv\.cargo\bin\cargo.EXE`
- Command arguments: `["cargo", "fuzz", "--version"]`
- Exit status: 101
- Outcome/version: error: no such command: `fuzz`
- Log: `test_results/phase11/tools.json`

## process inventory

- Classification: mandatory
- Purpose: Read-only active worker names/PIDs; omit command lines
- Executable: `C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe`
- Command arguments: `["powershell.exe", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'qemu|cargo|rustc|python|codex|claude' } | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress"]`
- Exit status: 0
- Outcome/version: [{"ProcessId":27940,"ParentProcessId":34636,"Name":"python.exe"},{"ProcessId":25460,"ParentProcessId":27940,"Name":"python.exe"},{"ProcessId":29116,"ParentProcessId":29156,"Name":"python.exe"},{"ProcessId":37116,"ParentProcessId":29116,"Name":"python.exe"},{"ProcessId":47144,"ParentProcessId":17700,"Name":"python.exe"},{"ProcessId":20392,"ParentProcessId":47144,"Name":"python.exe"},{"ProcessId":28268,"ParentProcessId":39572,"Name":"python.exe"},{"ProcessId":8868,"ParentProcessId":28268,"Name":"python.exe"},{"ProcessId":47852,"ParentProcessId":25460,"Name":"python.exe"},{"ProcessId":45808,"ParentProcessId":47852,"Name":"python.exe"},{"ProcessId":47020,"ParentProcessId":20392,"Name":"python.exe"},{"ProcessId":51172,"ParentProcessId":47020,"Name":"python.exe"},{"ProcessId":53800,"ParentProcessId":22732,"Name":"python.exe"},{"ProcessId":52392,"ParentProcessId":53800,"Name":"python.exe"}]
- Log: `test_results/phase11/tools.json`

## local protection metadata

- Classification: optional
- Purpose: Local branch/upstream policy; remote protection not queried
- Executable: `C:\Program Files\Git\mingw64\bin\git.EXE`
- Command arguments: `["git", "config", "--get-regexp", "branch\\..*|receive\\.deny.*"]`
- Exit status: 0
- Outcome/version: branch.main.remote origin
- Log: `test_results/phase11/tools.json`

## Verification commands actually used

Actual production linker: Rust toolchain `lib/rustlib/x86_64-pc-windows-msvc/bin/rust-lld.exe`,
`-flavor gnu --version` -> **LLD 23.1.3**, exit 0
(`test_results/phase11/rust_lld_gnu_version.log`). The initial bare `--version`
probe exited 1 because rust-lld is a generic driver; retained in
`rust_lld_version.log`, not treated as tool absence or a build failure.

After the permission slice, broad host tests passed **270/0/2 ignored** in
both default parallel and serial modes (`host_green_parallel.log`,
`host_green_serial.log`), exit 0. Kernel and host formatting exited 0.
Acceptance-harness RED logged six intended failed assertions in 37 tests;
GREEN all 37 passed (`harness_red.log`, `harness_green.log`). These are host
contract tests, not fabricated guest results.

Full inherited runner launched as `python -B scripts/phase6_verify.py` through
a notified background terminal; final process exit0 and PASS54/54 were verified
(`runner_exit.json`, exact invocation report and gate logs). Independent
post-run extraction/source/cleanup verifier exited0, repeated after implementation
commit `d6d04c5`. No optional tool was
installed and no GDB/Clippy/Miri analysis is claimed from a version probe.

Initial git recovery commands exited 0, HEAD `def677fac8ca662e45ad4fb40c9ddd18bfe86bd8`.
Host Cargo baseline ran outside the repo and exited 0: 265 passed, zero failed,
two ignored (`test_results/phase11/baseline_host.log`).
Version probes are availability checks, not Clippy/Miri/GDB analysis of the kernel.
Remote branch protection was not queried; local config reports upstream only.

## Auxiliary tools actually invoked

`test_results/phase11/auxiliary_tools.json` records commands, exit statuses and
output for PowerShell **5.1.26100.9711** (read-only process-name/PID inventory),
subprocess-resolved GNU Bash **5.2.21(1)-release, x86_64-pc-linux-gnu** (WSL-side
availability probe, not an assertion about Git Bash's version), and rustup
**1.28.2** (toolchain manager). All three probes exited 0. Python package
**pycdlib 1.22.0** is already installed and used by the independent post-run
in-memory ISO extraction verifier; no installation was performed.

The exact closeout command is
`python -B test_results/phase11/verify_checkpoint.py test_results/phase11/acceptance_20261016T154710Z_q3u90_53/acceptance.json`.
Run it only after acceptance exits. It neither builds nor starts QEMU; its
scope is report/source/artifact identity and loaded-section accounting, not
CPU privilege-transition verification. Final results live in
`test_results/phase11/final_verification.json` and `resource_sections.json`.

## Checkpoint tooling outcome

Production `cargo build`, kernel/host formatting, host serial/parallel, every
canonical acceptance gate and independent closeout exited0. Existing warnings
were retained, not hidden by output pipelines or drive-by edits. The initial
generic-driver linker probe and intended RED failures remain preserved as such.
Raw logs remain unchanged locally; `sanitized_test_results.json` records their
actual summaries/hashes and `evidence_manifest.json` fingerprints228 gate/host
logs and nested JSON reports. Versioned media and raw debug captures are not
committed. Tool discovery/closeout helpers are evidence utilities, not alternate
optional acceptance runners; all required tests remain in phase6_verify.py.
