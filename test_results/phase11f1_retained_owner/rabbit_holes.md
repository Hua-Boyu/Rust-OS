# F1 rabbit-hole control

- Initial all-file hash capture printed too much JSON for terminal transport; JSON parsing failed before a file write. Recovery: compute hashes in local execute_code and persist through write_file, printing only count. No source changes or fabricated hash results.
- A regex with escaped parentheses was rewritten by the Windows search path layer and rejected. Recovery: simpler identifier-alternative search; no repeated malformed regex.
- Relative read_file requests unexpectedly reported missing files after external-working-directory test activity; retrying absolute paths returned shared read-cache dedup rather than content. All future task paths are absolute. No files were recreated or overwritten to compensate for lookup failures.
- Do not resolve unknown future exception-stack sizes by declaring a type-size estimate or inventing safe headroom. Obtain independent numeric-policy review; preserve partial status if a concrete approved inventory remains blocked.
- First isolated probe compilation failed E0507 because PagingStats is not Copy. Use a scoped shared stats borrow while building an owned snapshot; no mutation occurs during the borrow. Retry passed compilation and preserved both exact-one runtime failures. No new Clone/Copy production API was added.
- Two-frame-only full-F1 proposal rejected; twelve-frame alternative only conditionally recommended pending concrete fixed metadata, joint seal and terminal integration. Recovery is a smaller reviewed baseline RED/evidence checkpoint, not speculative source changes or invented stack safety.
