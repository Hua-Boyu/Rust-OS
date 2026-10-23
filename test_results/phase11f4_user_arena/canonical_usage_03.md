# F4 review04 blocker corrections — task-local v3

These utilities are NOT approval, acceptance evidence, a new source freeze, or F4 completion. Historical numbered utilities, manifests and REJECT reviews are preserved. Production inputs are untouched.

## Admission and freeze contract

The parent must create a new immutable manifest after these files are finalized, then obtain a complete independent resolution review of its exact raw bytes. Pin all four tools (`run_canonical_03.py`, `canonical_readback_03.py`, `canonical_identity_readback_03.py`, `canonical_provenance_03.py`) in `artifact_sha256`, alongside the preserved full candidate evidence. Also retain these test/usage/log/report artifacts as appropriate. The manifest needs exact source discovery map/count, artifact map/count, the existing exact72 `gate_identities`, terminal ELF and inherited metadata required by reader02. Do not create a hash cycle by pinning the later review inside its reviewed manifest.

The new review schema is exactly `rosti.f4-independent-candidate-review.v5`. Require `review_complete: true`, `verdict: "APPROVE"`, `blockers: []`, integer `blocker_count: 0`, `authorizes_canonical_acceptance: true`, exact `source_sha256`, and both `candidate_manifest: {path, sha256}` and `candidate_manifest_sha256` agreeing with explicitly supplied manifest bytes/path. `checks` must be a list containing each of the 19 exact `REQUIRED_AREAS` strings exported by `canonical_provenance_03.py` exactly once, every check with `status: "PASS"`. Extra unique PASS areas are allowed. Qualifications belong in findings/limitations, not a non-PASS authorization status. Full unchanged independent03 findings may be explicitly incorporated with authenticated original scope; no spot-check approval or waiver is supplied by these tools. Review04's four direct areas plus all fifteen independent03 areas must appear in that list. Independent reviewers must actually resolve launcher/readback blockers and validate every scope, not copy the MOCK test fixture.

Admission rehashes all candidate artifact pins, checks all required utility pins, rehashes and compares exact rediscovered source bytes, and rejects the insufficient review02 raw digest explicitly. JSON duplicate keys, REJECT, missing/contradictory authorization, incomplete checks, path/hash/source drift and optimized Python are refused before output creation or Popen. Dynamic explicit manifest/review arguments avoid hardcoding a future manifest hash.

## Later authorized CLI (NOT EXECUTED here)

Use the verified absolute interpreter:
`C:/Users/iamsv/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`.

From repository root, after a genuinely complete APPROVE of a new frozen manifest:

```
<absolute-python> -B test_results/phase11f4_user_arena/run_canonical_03.py <complete-review-path> <raw-review-sha256> <new-manifest-path> <raw-manifest-sha256>
```

The parent must use `terminal(background=true, notify=true)`, one invocation, no polling, no source/harness edits, foreign kills or lock unlinking. The launcher uses one captured Popen handle and blocking wait, and relies on the unchanged acceptance runner's OS-held lock. It never kills processes or unlinks a lock. A conservative quiescence scan refuses AccessDenied rather than assuming quiescence. This scan is observational, not atomic exclusion; the runner lock remains authoritative.

Output is fixed to the fresh short `test_results/f4acc/c03`. The real `scripts/phase6_verify.py` CLI implementation, lines434-439, treats `--output-dir` as a parent and creates `acceptance_<timestamp>_<unique>/acceptance.json` beneath it, not a direct report. Both new launcher and shared reader enforce exactly that invocation-owned immediate-child layout. Tests never create the production output root. No kernel/guest/acceptance command is executed in these tests.

After real completion:

```
<absolute-python> -B test_results/phase11f4_user_arena/canonical_readback_03.py test_results/f4acc/c03/driver_result.json
<absolute-python> -B test_results/phase11f4_user_arena/canonical_identity_readback_03.py test_results/f4acc/c03/driver_result.json
```

The driver records exact manifest/review raw identities, command/interpreter/cwd/output path, owned PID and Popen.wait actual exit, before/after source maps, log digest and one invocation-owned acceptance path/hash. Shared readback checks this contract before all inherited reader02 deep evidence checks, official B13 host artifact, boot CSV, exact gate/Rust identities, F2/F3/F4 validators, Phase10 exact56, nested evidence, ISO payload/GREEN kernel identity and final source/pin stability. Outputs use new exclusive numbered names: `parent_canonical_readback_03.json`, `canonical_iso_kernel_03.bin`, `canonical_identity_readback_03.json`. A failed reader's exclusive output must be preserved; use a new revision for any repair/retry.

## Safe host-only controls

```
<absolute-python> -B test_results/phase11f4_user_arena/test_canonical_03.py
```

All complete approval/driver fixtures are clearly MOCK-only, confined to temporary newly created task-root directories, and admitted by pure validators only. No successful launcher Popen is exercised. Real review02 launcher CLI refusal and actual optimized/inherited-PYTHONOPTIMIZE refusals run Python-only subprocesses; patched rejection controls assert no acceptance subprocess starts. Therefore these tests cannot establish a real successful process record, real PASS72, toolchain path-length compatibility, ISO readback, or independent approval. Those remain mandatory later evidence.
