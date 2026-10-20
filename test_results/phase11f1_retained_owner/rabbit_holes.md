# F1 rabbit-hole control

## V2 recovery

- Read bounded JSON sections rather than dumping multiple large reports: the first combined recovery print exceeded transport budget. Complete saved fields were then recovered selectively; no missing reviewer output is treated as approval.
- execute_code subprocess bash resolves the WSL executable despite native Windows Python; terminal explicitly confirms Git Bash5.3.15 and Windows Cargo x86_64-pc-windows-msvc. Use terminal for actual Cargo, never silently mix toolchains.
- Initial reviewer hit repeated terminal quoting failures while saving its verdict; parent steered it to direct pathlib/hashlib and write_file, without installing/repairing tools. Complete saved verdict was then recovered directly and all26 source pins verified; no summary truncation used as approval.
- write_file emitted a sibling-write metadata warning for the old task-local evidence_manifest after its original bytes had been read/verified through execute_code. This warning alone is not live source-writer evidence: historical raw pins matched at recovery, all150 current source inputs remain equal and the reviewer is scoped to its own verdict. Preserve original manifest under historical_evidence_manifest_pre_v2.json and stop if actual raw unexplained source drift appears.

## Historical notes

- Initial all-file hash capture printed too much JSON for terminal transport; JSON parsing failed before a file write. Recovery: compute hashes in local execute_code and persist through write_file, printing only count. No source changes or fabricated hash results.
- A regex with escaped parentheses was rewritten by the Windows search path layer and rejected. Recovery: simpler identifier-alternative search; no repeated malformed regex.
- Relative read_file requests unexpectedly reported missing files after external-working-directory test activity; retrying absolute paths returned shared read-cache dedup rather than content. All future task paths are absolute. No files were recreated or overwritten to compensate for lookup failures.
- Do not resolve unknown future exception-stack sizes by declaring a type-size estimate or inventing safe headroom. Obtain independent numeric-policy review; preserve partial status if a concrete approved inventory remains blocked.
- First isolated probe compilation failed E0507 because PagingStats is not Copy. Use a scoped shared stats borrow while building an owned snapshot; no mutation occurs during the borrow. Retry passed compilation and preserved both exact-one runtime failures. No new Clone/Copy production API was added.
- Two-frame-only full-F1 proposal rejected; twelve-frame alternative only conditionally recommended pending concrete fixed metadata, joint seal and terminal integration. Recovery is a smaller reviewed baseline RED/evidence checkpoint, not speculative source changes or invented stack safety.
