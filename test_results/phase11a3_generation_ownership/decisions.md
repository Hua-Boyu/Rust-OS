# Material decisions

Decision ID: D1
Question: Recover unexpected preexisting implementation versus assume missing APIs?
Source evidence: initial Git diff frame.rs +115/-9; complete recovered design review; eight current tests.
Available options: erase draft; preserve and verify actual draft.
Clef recommendation: UNAVAILABLE (clef-omni absent from skill_view and installed list; approval connector is not equivalent).
Chosen action: preserve draft and correct oracle first; RED v4 must explicitly state actual failure causes.
Reason: current source outranks stale session description. No fabricated missing-API RED.
Revisit condition: new source identity or review blocker.

Decision ID: D2
Question: Continue after sibling-write warning?
Source evidence: write_file warning identifies agent 20261018_162915_4523ba; no live children in this session.
Available options: pause for sole-writer confirmation; continue blindly.
Clef recommendation: UNAVAILABLE.
Chosen action: pause edits, inspect process classifications, ask user; user confirmed earlier session stopped.
Reason: prevent concurrent source changes; no processes killed or acceptance lock touched.
Revisit condition: any new external source mutation.

Decision ID: D3
Question: How to test rejected by-value release without use-after-move?
Source evidence: approved review correction 7; release_frame consumes FrameLease; existing tests retain same token after consuming it.
Available options: cfg(test)-only duplicate token, or separate compile-fail harness.
Clef recommendation: UNAVAILABLE; design explicitly approves narrowly scoped test forgery.
Chosen action: duplicate probe only; keep legitimate token for cleanup. Negative trait inference asserts neither Copy nor Clone.
Reason: production remains nonduplicable; rejected release capacity and subsequent legitimate release both testable.
Revisit condition: supported compiler rejects negative assertion mechanism.

Decision ID: D4
Question: How to record authentic RED v4 when the recovered tree already has lease APIs?
Source evidence: complete git predecessor dde0788 frame.rs; current draft APIs; corrected move-only oracle.
Available options: mislabel draft compile errors as missing APIs; temporarily rollback live source; isolated predecessor snapshot.
Clef recommendation: UNAVAILABLE.
Chosen action: copy needed source/harness into task-local red_v4_predecessor, replace only frame.rs with exact git-show predecessor bytes, run existing wrapper from home.
Reason: authentic missing-API RED without overwriting inherited live implementation or weakening assertions; actual exit101/31 API errors recorded, zero runtime tests explicitly stated.
Revisit condition: source/oracle provenance does not match saved snapshot.

Decision ID: D5
Question: Which currently enabled numeric ownership paths need migration?
Source evidence: bounded symbol/type searches and full relevant paging/mod paths; caller_audit.md.
Available options: migrate all table inventories to leases now; retain audited private revoked structure inventories and exact growth claims.
Clef recommendation: UNAVAILABLE; existing approved design permits audited raw kernel paths.
Chosen action: preserve existing structure/growth boundaries, stamp raw ordinary allocations too, share release accounting; make production FRAME_ALLOC private and migrate only external diagnostic reads.
Reason: no production ordinary payload release exists outside those boundaries; avoid allocator/map redesign. Numeric map remains trusted, not a complete user capability API.
Revisit condition: independent reviewer identifies an unsafe currently enabled release path, or future process payload API added.

Decision ID: D6
Question: Resume after the apparent stale source view / writer warning?
Source evidence: user explicitly says earlier model is not running and permits overwrite; recovery and partial snapshot raw frame hashes are identical despite differing read_file length displays.
Available options: remain blocked on unproven concurrent mutation; proceed from actual bytes while preserving old snapshot.
Clef recommendation: UNAVAILABLE.
Chosen action: proceed; earlier PARTIAL capture is historical interrupted work, not final outcome.
Reason: user resolved operational ambiguity; identical raw hashes do not authenticate a simultaneous writer. No unrelated process killed.
Revisit condition: new actual byte mutation outside this session's edits.

Decision ID: D7
Question: How to perform reproducible final readback when the predecessor offline reader hardpins its old driver and totals?
Source evidence: old offline verify_checkpoint.py requires host305/B26full78 and historical driver; new actual candidate325/98 with three exact added gate families. Canonical runner itself remains unchanged except those tuples.
Available options: rewrite the canonical runner/framework; alter historical verifier pins; task-local offline reader reusing pinned historical helpers.
Clef recommendation: UNAVAILABLE.
Chosen action: independent agent authors task-local read-only verification overlay; parent reads all code and runs15 fail-closed contracts. No build/test/guest launch from the reader; only evidence validation and local process observation.
Reason: retain the single canonical acceptance framework and immutable historical proof; add reproducible check of actual wrapper completion, source/review/nested/artifact identities for this exact invocation.
Revisit condition: actual reader disagrees with independently inspected evidence; preserve failed output and resolve the oracle narrowly without changing frozen source or weakening gates.

Decision ID: D8
Question: Preserve exact CRLF design review bytes in Git despite default staged whitespace diagnostics?
Source evidence: original review has35 CRLF endings; raw copy/index blob hash is exact. Default staged --check labels those CR bytes trailing whitespace; all other paths pass default checking.
Available options: alter authenticated review bytes; omit review from commit; recognize CRLF only for that immutable artifact's check.
Clef recommendation: UNAVAILABLE.
Chosen action: retain exact original bytes/blob, run default --check on every other staged path and a one-command cr-at-eol-aware check on review_original.txt only; both actual exits0. No Git config/attributes or accepted source changes.
Reason: retain literal review provenance without suppressing whitespace checks on code or normalizing authoritative evidence.
Revisit condition: any non-newline whitespace defect or byte hash mismatch; staged_whitespace.json records exact check results.
