# Canonical lifecycle discovery — finalization10 (pre-approval record)

STATUS: NOT LAUNCHED. This document does not authorize admission by itself.

## Real interfaces

- Shared runner `scripts/phase6_verify.py` is READ ONLY, raw394dfcfa9e5d40ebb56c614ac2356a4c930fbbd80b418c408f46b30daf388b20.
- Current CLI (`_run_acceptance`, lines571–576): `--output-dir`, `--f5-review`, `--f5-review-sha256`. Use absolute Python `C:/Users/iamsv/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe` (the verified pycdlib-bearing environment), `-B`, exact new task-local review path/raw SHA256. Review argument is mandatory through admission even though argparse itself makes it optional.
- Planned short output parent: `C:/Users/iamsv/Documents/Rust-OS/test_results/f5acc/r01`, provided still unused at admission. Runner creates its own unique acceptance_TIMESTAMP_SUFFIX child. Do not substitute an undocumented wrapper or invent an aggregate path.
- `main` holds a nonblocking OS-held lock on `dist/.phase6_acceptance.lock` throughout acceptance/restoration. Never unlink that path or infer stale authority from PID metadata.
- Exact authenticated contract remains72 inherited F4 identities plus four F5 identities=76, independently compared to accepted F4 acceptance raw3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4. Source collector currently enumerates234canonical inputs; full candidate freeze has262.

## Deadlines and process host

The canonical runner intentionally has no whole-run orchestration deadline in its current code. Each gate retains its explicit approved subprocess timeout. Only the mock gate is1049 seconds (line960); this is NOT a whole-run deadline. The inherited/genuine F5 hardware gate limits remain900, with fresh F1 inner890/outer900. No deadline has been changed for this correction.

The current Hermes tool schema supports `terminal(background=true, notify=true)` and returns actual session_id, pid and notify_on_complete. This was exercised successfully by the real F1 composition and full stream. Local source `tools/terminal_tool_background.py:129–183` delegates to process_registry.spawn_local without passing a timeout; `tools/process_registry.py:817–868` starts a persistent Popen/reader thread, not a foreground timed subprocess. No background whole-process runtime deadline appears in this exercised local spawn path. Session stale-age accounting is not itself a process-kill deadline. No host timeout was altered or disabled.

The foreground transport did time out at420 seconds on an OS-handle waiter despite a requested600-second tool timeout. That waiter did not launch or own the background verification and did not invalidate its observed later exit0. Therefore foreground transport is not suitable to host the whole canonical run. Process-manager wait windows are separately clamped180 seconds; such a wait-window timeout is not the runner result. Use native completion notification, or a documented blocking wait; never poll active canonical reports/process status, launch competing Cargo/QEMU/mock jobs, edit frozen inputs or unlink the lock.

The F5 component driver's14400-second bound applies only to its adapted predecessor subprocess. It is not imposed on the genuine canonical runner. Fresh predecessor r03 completed actualexit0/PASS72/72 in3720.422 seconds and proves a real comparable total lifecycle was supported by native background execution.

## Resource recovery and admission boundary

Pre-component available RAM4053094400 bytes. Mid-predecessor available635236352 bytes was a severe-pressure sample, not ignored; its exact process tree/working sets are in resource_observation_10.json. There were no additional concurrent task-heavy jobs. Owned predecessor native interpreter peak working set296730624 bytes and sampled512MiB guest working set129425408 bytes are observations, not a joint whole-run peak bound. QEMU also reserves larger committed virtual space; do not equate resident set with total commit demand.

The owned full stream/predecessor/QEMU processes all completed/released. Finished task-manifest large objects were deleted and garbage-collected through the owned execution kernel; remaining kernel RSS26628096 bytes, not a cache/service to terminate. Native postrelease probe observed no Cargo/rustc/link/QEMU and available2031443968 bytes; reported swap/pagefile free126043668480 bytes. No foreign/unknown or infrastructure process was terminated, no cache cleared, no service disabled, and no pagefile setting changed. The full sequential workload actually completed under the recorded fluctuating pressure.

Do not enforce a fabricated universal4GiB threshold. Before canonical launch, take a FRESH native process/resource/source/review snapshot and assess margin against the verified sequential workload, existing OS commit headroom and no concurrent heavy work. If severe pressure remains without a defensible margin after safe owned cleanup, stop PARTIAL or seek actual extra authorization; never gamble on a canonical OOM or claim implementation failure from resource pressure.

## Required admission and completion

Comprehensive independent candidate APPROVE/zero blockers/complete_scope, exact source/input rehash and real production validate_f5_review admission are still pending at document creation. Only after those pass and resources are adequate may one canonical run launch. Capture the actual returned session/pid, observe actual completion/exit0 and exact76/76, validate nested fresh F1 cleanup and F1–F5 evidence/source/ELF/ISO identities/owned cleanup, then obtain separate independent final canonical readback. A component PASS or fresh predecessor72 is not F5 acceptance.
