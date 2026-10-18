# Rabbit-hole recovery

## Oracle patch ambiguity (two failed patch applications)
Objective: repair move-only oracle and allocator-state assertions.
Category: edit tool context ambiguity, not Rust semantics.
What changed: second patch used more context but separate @@ blocks still matched repeated statements.
Rejected: further small hunks matching repeated allocator lines.
Replacement: rewrite the enclosing small test file with write_file after rereading, preserving all eight test identities and ABA assertions; use independent capacity snapshots rather than invalid hardcoded zero/one counts (PageMap owns structures).
Outcome: file written; compilation pending. No tests claimed passing.

## Concurrent-writer warning
Paused semantic edits on explicit sibling-write warning. Local process inspection found no Cargo/rustc/QEMU; initial broad text classification matched the inspecting command itself, so it was not treated as an active acceptance process. User confirmed earlier session stopped. No unrelated process terminated.

Resolution: user explicitly authorized overwrite/resume. Initial recovery hash and
partial snapshot frame hash are identical, despite differing partial read_file
line/size displays. The apparent change is not authenticated concurrent-write
evidence. Continue from actual current bytes; do not keep investigating runtime
session internals after user clarification. Intermediate snapshot stays intact.

## Expected RED is not a failed implementation attempt

RED v4 intentionally compiles corrected oracles against exact isolated predecessor
allocator bytes:101/31 missing-API errors, zero runtime tests. New runner contracts
intentionally fail before their gate tuples exist:3 methods/41 assertions-subtests.
These are useful newly produced evidence, not retries of failed fixes. Both have
subsequent GREEN results; no test assertion was removed to manufacture success.

## Offline reader interpreter mismatch (one failed attempt)

The recorded child command `python -B .../test_verify_checkpoint.py` resolved to
a Python without pycdlib even though the direct terminal interpreter has it.
Actual failure:15 methods,1 ModuleNotFoundError in synthetic ISO extraction.
No source/harness assertion was weakened and no package installed. Replacement:
explicit C:/Users/iamsv/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe
in the wrapper child argv. All15 reader contracts then passed. Preserve both
generation_reader_contracts and generation_reader_contracts_venv records/logs.
Use that absolute interpreter for the actual offline closeout as well.

## Authenticated CRLF review versus default whitespace checker

Default staged --check flagged every CRLF in the byte-preserved original review.
Do not rewrite that external evidence to satisfy a style check. All other paths
pass the default checker; only the immutable review is checked with per-command
cr-at-eol recognition, also exit0. Working copy and staged review bytes still
match exactly. No persistent Git configuration/attributes or accepted source
changed. Exact two-command results: staged_whitespace.json.
