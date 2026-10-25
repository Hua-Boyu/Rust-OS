# Entry-source conformance issue — investigation only

STATUS=UNRESOLVED / NOT A DESIGN AMENDMENT / NOT AN APPROVAL

This records a separate implementation/design mismatch discovered during continuation04. It does not replace design03, consume a new design revision, authorize implementation, or alter accepted F2 bytes.

## Binding requirements

- Current user continuation: `src/exception_entry.s` must remain byte-identical to accepted source; raw SHA-256 identities cannot be normalized.
- Approved design03 section1 lines17-21: parameterized **source-shared** stub/common normalizer expansion, not another independent decoder.
- Design review03 checklist10 lines1445-1454: conditional approval specifically accepts source-shared parameterized macros preserving the fixed F2 contract, default symbols/instructions/bridge and 68-byte layout, with emitted comparison.

## Actual source

- `src/exception_entry.s:3-28,62-94` defines F2_STUB and an F2 normalizer directly.
- `src/f5_exception_entry.s:6-31,65-97` separately defines F5_STUB and an F5 normalizer directly.
- `src/f5_runtime.rs:28-31` includes only the F5 file for that expansion. No parameterized common source inclusion was found.
- In-memory substitution of F5 symbol names with accepted F2 names yields equal macro/normalizer instruction lines (`entry_source_equivalence_diagnosis_04.json`). This is evidence of algorithm correspondence, **not** literal source sharing, linked instruction equivalence, hardware correctness, or amendment authority.
- The live F2 raw file also differs from accepted design03/F4 pins solely by LF/CRLF diagnosis. `f4_provenance_readback_04.json` retains both full hashes. The source has not been normalized or rewritten.

## Disposition boundary

A failure-policy-only supplement cannot retroactively approve an unrelated entry architecture change. Do not mark the existing duplicate expansion as conforming by redefining “source-shared.” Do not modify the approved design or protected F2 source merely to make these requirements appear compatible. The independent reviewer has been asked to identify whether this is a separate candidate prerequisite or requires scoped amendment authorization.

If a conforming bounded implementation can truly preserve accepted F2 raw bytes while deriving both actual emitted paths from the approved common source algorithm, identify and independently review that approach before source edits. If instead keeping the current duplicate expansion is desired, a fresh explicit design disposition/amendment and any required user authorization are necessary; emitted equality alone is not that authorization.

No runtime defect or changed exception ABI has been demonstrated by this source-structure finding. No F5 PASS or canonical acceptance follows from it.
