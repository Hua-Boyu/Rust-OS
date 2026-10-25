# P12-A remediation compliance — one authorized package

Historical cycles and attempts remain UNKNOWN; original executed RED source/test bytes remain UNVERIFIABLE_HISTORICAL. See red_provenance_01.json and reviewer_disclosure_preflight_01.json. Package1 is in progress; no second package.

| Type | Contract requires Eq | Implemented | Verified |
|---|---|---|---|
| State | Yes, contract43 | derived Eq alongside PartialEq | api_green_pre rustc exit0; focused empty-policy trait bounds pass |
| Context | Yes, contract43 | derived Eq alongside PartialEq | api_green_pre rustc exit0; focused empty-policy trait bounds pass |
| TaskKind | Yes, contract43 | derived Eq alongside PartialEq | api_green_pre rustc exit0; focused empty-policy trait bounds pass |
| Error | Yes, contract43 | derived Eq alongside PartialEq | api_green_pre rustc exit0; focused empty-policy trait bounds pass |
| Slot | Yes, contract43 | derived Eq alongside PartialEq | api_green_pre rustc exit0; focused empty-policy trait bounds pass |
| Snapshot | Yes, contract43 | derived Eq alongside PartialEq | api_green_pre rustc exit0; focused empty-policy trait bounds pass |

All fields are fieldless enums or u8/bool/arrays of Eq values, no generic or floating fields. Structural equality is reflexive and consistent; no custom equality. Only these six derives changed. `Policy::new` is const, literal fixed storage only; initial snapshot including zero queue verified in existing empty_policy test. no_std API probe compiles. Scheduling bodies unchanged except formatting. Existing24 test names retained; Ready=>queued and sustained per-operation replay strengthened. Fresh frozen full evidence is required separately, not inferred from focused checks.
