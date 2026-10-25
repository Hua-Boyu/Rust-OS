# P12-A decisions log

## D-05 Continuation02 one-package authorization and verified candidate

Current user explicitly authorizes one additional bounded package despite unresolved historical budget; this supersedes D-04's historical stop only for that package. HISTORICAL_CORRECTION_CYCLES_USED=UNKNOWN and HISTORICAL_ATTEMPTS_BY_DEFECT=UNKNOWN remain unchanged; new packages max1/used1, no reset or second package. No semantic/capacity/state/refusal/runtime expansion.

Six exported Eq derives and const new corrected; existing24 policy identities retained with stronger bidirectional queue invariant and per-operation long replay/literal fairness. All required focused/full host/B26 serial/parallel/list, formatting, no_std and fresh production build/isolation pass. Host416pass/two inherited ignores/list418; B26149pass. Production ELF still exact A=B=AFTER; Class T preservation skips remain explicit, not fresh hardware PASS. No new canonical gates; CANONICAL_ACCEPTANCE=NOT_APPLICABLE_NO_NEW_GATES, F5 historical exact76 retained.

The contract explicitly requires one mock run for added canonical source membership: actual95/zero skips/exit0,887.375s wall under enforced1049s. A final task-local transitive authority-closure repair adds11missing design pins (plus final verification wrapper), yielding dynamically enumerated298raw/236canonical freeze04. Every canonical acceptance input hash/member equals the actual mock-run freeze03; authority docs captured unchanged before/after. All affected reader/integrity/focused/host/B26/format/build/isolation checks rerun. No unnecessary second mock. Source-freeze counts were computed, not historical targets. Detailed disposition in freeze_extension_disposition_01.json; independent reviewer must assess sufficiency.

Parent_candidate05 exit0 checks immutable candidate manifest via external raw index02, complete freeze04, F5exact76/562bindings, original eight protected paths and real native process observation. Manifest has no own hash; candidate report/manifest snapshots prevent later finalization docs from changing reviewed pins. Current reader rejects all mandatory tampering controls;46lightweight controls pass. Failed bare-child Python invocation, edition-only host formatting failure, old freezes/wrappers and original REJECTs remain.

Original RED executed scaffold/test raw bytes remain UNVERIFIABLE_HISTORICAL; genuine24-executed/3pass/21fail log is authenticated, but post-RED UnknownId oracle correction/four removed inhibition assertions are disclosed. No unchanged-test TDD history invented. Both historical uncertainties were mandatory independent review scope before dispatch. Separate actual reviewer completed APPROVE — ZERO BLOCKERS — COMPLETE SCOPE (15areas,450rawpins), and parent independently read back every reviewed pin. Implementation commit receipt records the actual scoped source commit. Final documentation commit and ordinary push must satisfy closeout_commit_receipt_01.json before P12-A is ACCEPTED. Current user permits normal scoped final push (superseding old no-push wording) and only conditionally P12-B design after accepted synchronized closeout; no runtime implementation authority.

## D-06 Noncircular final metadata and conditional design handoff

Immutable FINAL_REPORT_candidate_01.md, evidence_manifest_candidate_01.json and input02 remain unchanged after independent approval. Live report/STATE/manifest record approval and actual source commit, with final containing documentation SHA, push result and complete remote equality deliberately externalized to postcommit closeout_commit_receipt_01.json. This uses the established F5 postcommit-receipt method, not a fabricated self hash or guessed containing HEAD. Exactly two scoped nonempty closeout commits follow approval. P12-A completion is conditional until the actual receipt says ACCEPTED; no premature acceptance from this paragraph. P12-B preparation may only activate after the real receipt; its own STATE tracks design-only work, and no B implementation is authorized.


## D-04 Backup-first checkpoint and budget stop

The current user explicitly authorized normal non-force checkpoint push before development, superseding prior no-push directions only for this scoped workflow. Original branch/HEAD were maintenance/phase10 at d9cebe28eb5139b6b614b7000688857361e2afc4. Branch tracking selected origin, unchanged GitHub push URL. Only wip/phase12-p12a-checkpoint was created/pushed. Backup c03e13fb67f38b3ea6d968afba020e1c4772a9f9 has independently queried equal remote SHA, accepted F5 ancestry and matching committed raw blobs; no original-branch merge or update. Exact positive paths/shared hunk and omitted/protected raw identities are in git_backup_manifest_01.json. The remote accepted an existing historical 54.84 MB F5 review artifact with a size warning. No source edit or expensive verification preceded verified backup.

Independent reviews/budget_reconstruction_01.json completed PARTIAL_STOP_BUDGET_UNRESOLVED; raw15dc826eb5438e2396e554db421a0904dcf05937780f69141dcd13199b48b783. Original session history is unavailable; surviving compiler logs and selected audit excerpts do not reliably distinguish substantive cycles or cumulative distinct failed approaches. UNKNOWN is neither zero nor proof of exhaustion. Under current user section9.1, STOP before another substantive correction. No counter reset or waiver inferred; no policy/test repairs, new expensive suites, candidate approval, acceptance closeout commit/push, or P12-B design undertaken.

Readiness findings retain precise CONFIRMED/RESOLVED/BLOCKED dispositions in readiness_status_02.json. Lightweight prerequisite_readback_02.json confirms incomplete old freeze and preserves explicit six-line host-wiring/F5 historical-pin disposition; it is not complete source-frozen verification. Current report: BACKUP_FIRST_PARTIAL_REPORT_01.md. New documentation remains local/uncommitted after verified backup. Recover authenticated history or obtain explicit user disposition before resuming substantive repair; independent candidate APPROVE and accepted final push remain mandatory before P12-B.

## Preserved prior decisions

## D-00 Baseline recovery (no source/test edits)

- HEAD d9cebe28eb5139b6b614b7000688857361e2afc4 equals accepted F5 closeout; ancestry exit 0.
- Phase 12 design files verified present and all 39 review pins + 30 inventory inputs match (preflight_01.json). Design is locally ignored/untracked, NOT committed; recorded truthfully, not misrepresented as a committed kickoff.
- F5 canonical acceptance path/hash recovered from F5 FINAL_REPORT.md + evidence_manifest.json (not from memory): acceptance.json raw 21247dcb…, 76-gate multiset recorded in preflight_01.json.
- Fresh baseline re-derivation before any P12-A edit (test_results/p12a/b01/report.json): host --list 394, host serial 392 passed / 0 failed / 2 ignored exit 0; B26 --list 149, serial 149 passed / 0 failed exit 0.
- Baseline production ELF A and B built at unmodified HEAD with `cargo +nightly build` (repo CWD, default features, kernel-crate cargo clean before each): both raw 981f373a7a6530cbcc861261947b9aaa71f69661cb4e2a100b73901c4a1854e4, equal to each other and to the accepted F5 ELF. Reproducibility A=B established; Class T byte-identity shortcut is available if the post-change build matches.
- git status before/after baseline identical; protected worktree untouched.

## D-01 Contract v01 smallest-safe choices (proposed, awaiting reviewer approval)

Each resolves an option the approved design leaves open; all marked as proposed choices in p12a_contract.md.

- Capacity: exactly 2 worker slots / FIFO length 2 (design §4/§8 two workers + separate idle). No priority, quantum, ticks or counters (design does not define them; smallest safe = none).
- IDs: u8 1..=254 valid; 0 reserved idle/unused; 255 reserved invalid. Deterministic tie-break = admission order (FIFO), not numeric order.
- States: design's UNUSED→READY→RUNNING→READY/RETIRED exactly; no reuse/reclaim API (design excludes it); fresh Policy instance is the only reset.
- Selection: request_reschedule performs the abstract decision only; admission never switches current; completion dequeues next Ready or returns Idle. One-worker yield selects itself.
- Inhibition: checked u8 depth (max 255) with explicit InhibitOverflow/InhibitUnderflow refusals; pending coalesces once; final leave drains exactly once. Admission and completion while inhibited refuse (conservative proposed rule — avoids mutating the queue inside the inhibited regime).
- Errors: full enum named in contract; every Err returns an unmodified Snapshot (atomicity asserted by tests).
- Test set: 24 exact identities, prefix p12a_policy_tests::, zero new ignored; filter audit (filter_audit_01.json) shows no substring/prefix collision with any inherited filter or identity.
- Acceptance: Option A (host-only, no new canonical gates) — the approved design §9:95 leaves the acceptance contract to a separately approved choice and does not require new gates. Not choosing Option B because earlier phases had gates.
- Mock gate: REQUIRED under §4.7 case (b) — phase6_verify.source_snapshot() (scripts/phase6_verify.py:450–490) enumerates *.rs under src/ and tests_kernel/, so adding src/p12a_policy.rs + tests_kernel/src/p12a_policy_tests.rs + editing tests_kernel/src/lib.rs changes snapshot membership (expected 234→236, to be verified). Existing 1049 s bound unchanged for that gate only.
- Classification: Class T hypothesis — policy compiled only into the host test crate via #[path] wiring identical to F5's f5_cpl3_tests (tests_kernel/src/lib.rs:52–56); src/main.rs module graph and the bin-only production manifest exclude it. Post-change ELF compared against A/B; mismatch ⇒ one bounded look then Class P unless reviewed alternative.
- Preservation under proven Class T: fresh F1–F5 guest reruns and emitted-closure rerun skipped, justified by identical production ELF (emitted instructions/roots unchanged) + accepted F5 closure bound to the same hash; explicitly reported as skipped, never as freshly passed. Mock gate still runs (snapshot membership changed).

## D-02 Process/resource discipline

- One parent-owned stream at a time; no overlapping heavy runs or reviewer dispatches.
- Available RAM ≥ ~4.3 GB at every baseline step (recorded per step in report.json); no triage needed.
- No cargo/rustc/link/qemu processes observed; Hermes/Strata = INFRASTRUCTURE, hub.py = UNKNOWN, untouched. No foreign/unknown process killed.

## D-03 Reviewer mechanism

- Independent review dispatched through delegate_task (leaf), the interface earlier phases used; schema verified before dispatch.
- Verdict is only known after reading design_review_01.json from disk; the delegate ID does not survive the session.
