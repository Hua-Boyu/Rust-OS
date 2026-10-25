# F5 timing remedy 08 — R2 qualified

STATUS=R2_QUALIFIED; F5 remains PARTIAL; no F5 acceptance or approval is claimed.

R1 was considered once and rejected on actual-host memory safety: os.cpu_count=24,
Windows logical count=24, affinity permits24; only1358344192 bytes available out of
64014364672 (97.9% in use). CPU availability is not dedicated capacity. A bounded
2-second CPU sample and memory snapshot are in recovery.json; system idle is not a
consumer despite psutil's per-process percentage. Known Hermes/model services are
infrastructure, not automatically writers. Other unattributed services are UNKNOWN;
no foreign process was killed. No Cargo/rustc/link/QEMU was observed. No R1
implementation or calibration was attempted; extra parallel fixture processes were
not judged safe. R2 is explicitly user-authorized, not an implicit design waiver.

## Performance candidate disposition

No recorded complete-suite10% benefit exists. The retained96-test candidate timed
out at900.0255737999687s, with95 successful rows and no summary. It is rejected.
Only scripts/test_acceptance_harness.py was restored from the historical
mock_perf_20261024T111033Z_0367d0/test_acceptance_harness.before.txt, authenticated
against full_source_freeze_07.json. Before raw SHA256:
0bd1916220db382f809a0a07d3c179da65edcbaacf41019865b96b6d2f72e824.
After raw SHA256:
f6274eac8eb8ef3075597ed3d946df5a41f19fed14b0e616efe6038404288d2f.
The previous bytes are additionally preserved as performance_candidate_preserved.py.txt.
All242 recorded run07 input hashes matched after restoration and before R2 edits.

## Full-suite observations

- Historical corrected95-test complete PASS: unittest806.791s; recorder
  wall807.0620000000345s; actual exit0; zero skips.
  phase11f5_cpl3_proof/mock_repair_20261024T100110Z_e9c56f/full_mock_02.json/.log.
- Run07 reached900s, incomplete89 dots; right-censored, not a complete duration.
- Unaccepted96-test candidate reached900.0255737999687s, incomplete; right-censored,
  not a complete duration and not used to compute W.
- Fresh restored95-test measurement: unittest712.796s; wall713.1870000000345s;
  actual exit0; all95 identities exactly once, all ok, complete OK, unchanged
  script inputs, no remaining exact-suite process observed. measurement.json/.log.
  This1500-second provisional ceiling was measurement only, not canonical PASS.

W=max(807.0620000000345,713.1870000000345)=807.0620000000345s.
1.25W=1008.8275000000431s. T=ceil(1.25W)=1009s, below1500.
No additional allowance. Old mock bound900s; proposed new bound1009s.
Maximum extra failure-detection latency109s. Qualification must complete under1009s;
if it establishes a slower complete W, the margin must be recomputed, not assumed.
Qualification completed actual exit0: all95 exact identities ok, no skips, complete
summary694.791s, wall695.0779999999795s under1009s, stable inputs, no remaining
suite process observed. W remains807.0620000000345;1009 remains the minimum.
Qualification evidence: qualification.json/.log. Owned launcherPID40072, Hermes
sessionproc_e5487d8a360e; measurementPID62124/sessionproc_f22681109b58.

## Scope

scripts/phase6_verify.py: only the timeout literal for the existing
`acceptance runner regressions` gate changes900->1009. Every gate identity,
command, validator and other timeout is unchanged.
scripts/test_f5_cpl3_harness.py: matching explicit timeout assertion changes only
that gate's expected bound900->1009; all other assertions are retained.
The95-test suite's raw source, test bodies, discovery and production validators
remain exact run07. No tests removed/skipped/xfail, no real-validator/pin_tree cache.
The full verification driver's matching mock timeout and freeze location will be
updated before a new freeze only after successful qualification.

The historical Design03 timeout requirement is explicitly superseded only for
this mock gate by the current user's scoped R2 authorization. All accepted design
and historical REVIEW/REJECT records stay byte-identical. Fresh independent full
candidate approval must cover the exception, source and measurement evidence.
No full component stream, F4 regression, canonical acceptance, commit or Phase12
work is authorized by qualification alone.
