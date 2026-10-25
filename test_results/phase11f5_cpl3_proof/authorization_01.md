# F5 scope supplement 01 — user authorization

The user answered the clarification form with:

> Authorize the narrow GDT extension and required reviews/revalidation

The question explicitly requested a narrow F3 GDT extension to add missing DPL3 code/data descriptors, preserve existing TSS selectors and stack layouts, and undergo independent compatibility/design review plus full revalidation.

This resolves the scope-authorization part of F5-GDT-01. It does not itself approve a design, authorize general userland or later phases, waive any review/gate, or establish a CPL3 result. No production edit has yet occurred. Initial preflight/design-stop documents remain preserved as historical checkpoints and will be superseded by current STATE entries, not silently rewritten as approvals.

Preferred design direction for review: keep original F3Context, TSS objects, five descriptors and all existing selectors/layouts byte-for-byte; install an F5-only seven-entry descriptor-table extension containing equivalent copies of original slots0–4 and new DPL3 code/data slots5–6. The separate extension must prove TSS bases/limits/busy state and task-gate selector compatibility, and must never be used by inherited F3/F4 fixture entry paths. This is a proposal, not an approved implementation.
