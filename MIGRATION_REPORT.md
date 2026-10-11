# Rosti → Rust-OS Migration Report (2026-10-11)

## 1. Old Git corruption diagnosis
**No corruption.** `git fsck --full` on `C:\Users\iamsv\Documents\rosti` exits 0 — no missing objects, no broken packs, no invalid refs, no unreachable commits, no broken tags. The reported corruption was a false alarm.

Verified against the repo:
- `1f560d9` — `feat(rosti): establish v0.1.0 interactive kernel baseline` ✓
- `d3c4f15` — docs backfill ✓
- `e374805` — host-test cargo config override ✓ (was HEAD on `feature/physical-memory-paging`)
- Annotated tag `v0.1.0` → `1f560d904dd785350f7712097dc1bf51119be1c0` ✓ (valid, not fabricated)

## 2. History recovery
Full history preserved by **fetching the healthy old repo as a remote** (`rosti-source`) into `Rust-OS` and merging with `--allow-unrelated-histories` (Rust-OS had its own unrelated 2-commit history from GitHub `Hua-Boyu/Rust-OS`, kept intact). Tag `v0.1.0` carried over. Branches preserved as `rosti-source/main` and `rosti-source/feature/physical-memory-paging`.

## 3. Backup
`C:\Users\iamsv\Documents\rosti-backup-20261011T132141Z` — full source copy (96 files, build caches excluded), SHA256 manifest `manifest.csv`, plus `recovery/git-metadata.tar` (original `.git` archived, never moved). Secrets (`.pve_auth`, `$AUTH`) were NOT copied into the backup or the new repo. Original project left untouched as rollback source.

## 4. New canonical location
`C:\Users\iamsv\Documents\Rust-OS` (README kept as the old Rosti README per user decision). Old `rosti` directory preserved unchanged.

## 5. Source verification
All project files copied (src, scripts, tests_kernel, test_results, dist ISOs, .cargo, manifests, docs). Release ISOs retained locally, excluded from Git tracking (`dist/` gitignored). ISO hashes: `rosti.iso` `bbfa45f9…` (matches deployed release), `rosti_rollback.iso` `0fffc984…`.

## 6. Path repairs
All hardcoded `Documents\rosti` references replaced with root-relative resolution (`Path(__file__).resolve().parent.parent` in Python, `BASH_SOURCE` in shell). WSL mapping fixed to `/mnt/<drive>` (a Windows-drive bug in the naive mapping was found and fixed). Historical test records (old paths in `deploy_report.json`, `boot_results.csv`) left as historical evidence.

## 7. Cargo build
`cargo fmt --check` PASS; `cargo build` PASS (18 pre-existing naming warnings only).

## 8. Host tests
- Committed v0.1.0 baseline: **27/27 PASS** (verified in a scratch checkout).
- Current working tree: FAILS — pre-existing WIP issue in uncommitted `src/memory/mod.rs` (`io::serial` not exposed to the host-test harness), identical in the old repo. Not a migration failure.

## 9. Keyboard integration
PASS (all stages: sendkey acceptance, decode echo, dispatch-exactly-once) against the baseline kernel via the migrated harness.

## 10. QEMU boot regression
10/10 PASS against the committed baseline kernel through the migrated `scripts/boot_test.py` (results written to the new `test_results/`). Working-tree WIP kernel fails (enter-only, init incomplete) — same as in the old repo (pre-existing WIP state, e.g. `run_01` FAIL recorded before migration).

## 11. GRUB ISO
Build + QEMU boot test PASS via the fixed WSL path mapping (`grub-mkrescue`, markers `entered kernel_main` + `boot complete`).

## 12. Proxmox VM 103
Unchanged and verified live via MCP: VM 103 `rosti-dev` on node `pve`, SeaBIOS, 1 core, 512 MiB, `serial0: socket`, ISO `local:iso/rosti_20261010T154256Z.iso` attached, running. No new upload performed. Dry-run checks: deploy script resolves to `Rust-OS`, finds the local ISO, targets VMID 103 only, credentials read from environment only (not set in this session — no live API call attempted; no remote writes made).

## 13. Git commit and tags
- `d6f04db` — `chore(repo): migrate Rosti project to Rust-OS` (scripts + docs; staged secret scan clean).
- `b3cb0a3` — history merge commit.
- Tag `v0.1.0` intact → `1f560d9`. `git fsck --full` clean in the new repo. Nothing pushed.

## 14. Security audit
No tracked secrets (`git ls-files` clean). `.gitignore` covers `.pve_auth`, `$AUTH`, `.env*`, build caches, `dist/`. Secret files remain only in the old project, not copied. `deploy-proxmox.py` obtains credentials exclusively from `PVE_TOKEN_ID` / `PVE_TOKEN_SECRET` / `PVE_ROOT_PASSWORD` environment variables.

## 15. Remaining issues
- Uncommitted Phase-4 WIP (memory module) fails host-test compilation and boot harness — pre-existing, to be fixed in Phase 4.
- `rosti-source` remote points at the old directory; remove it once the old repo is retired.
- `run_tests.sh` needs `pwd -W`-style native paths when invoked through git-bash (fixed).
- Orphan-QEMU warning in harness output is cosmetic (watchdog timing), process cleaned up.

Next phase (not started): **Physical memory management and paging.**
