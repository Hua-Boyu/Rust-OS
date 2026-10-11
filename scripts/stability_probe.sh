#!/bin/bash
# Stability probe: N consecutive independent QEMU boot runs.
# Thin wrapper around scripts/boot_test.py (the deterministic runner), which
# handles Windows paths, per-run output dirs, marker detection, timeouts and
# orphan-process checks. The old bash probe failed because it wrote output
# files under a Windows temp path mishandled by bash and used a `pipe:`
# chardev whose child died before flushing.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(dirname "$SCRIPT_DIR")"
RUNS="${1:-10}"
python3 "$SCRIPT_DIR/boot_test.py" --runs "$RUNS"
