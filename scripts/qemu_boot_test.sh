#!/bin/bash
# QEMU boot smoke test.
#
# Requirements met:
# - isolated emulator run, finite timeout (watchdog kills QEMU)
# - captures serial console output via `-serial file:` (kernel writes debug
#   markers to COM1 through src/io/serial.rs)
# - success requires the explicit marker "ROSTI: boot complete" — merely
#   launching QEMU is NOT proof of boot
# - detects triple fault / reboot loop via -no-reboot: QEMU exits on triple
#   fault, which the watchdog cannot kill; we check output for markers
# - nonzero exit code on any failure
set -u

QEMU="/c/Program Files/qemu/qemu-system-i386.exe"
KERNEL="C:/Users/iamsv/Documents/rosti/target/target/debug/kernel"
OUT="$LOCALAPPDATA/Temp/rosti_serial.txt"
LOG="$LOCALAPPDATA/Temp/rosti_qemu_log.txt"
rm -f "$OUT"

# Run QEMU headless for 10s, then kill it. Verified empirically: the serial
# file is flushed per-byte by QEMU's `file:` device, so a plain kill preserves
# all output; the monitor-quit variant exited QEMU too early on this host.
"$QEMU" -kernel "$KERNEL" -display none -no-reboot -no-shutdown -m 128 \
  -serial "file:$OUT" -monitor none -D "$LOG" 2>>"$LOG" &
QPID=$!
( sleep 10 && kill $QPID 2>/dev/null ) &
WATCHDOG=$!
wait $QPID 2>/dev/null
QEXIT=$?
kill $WATCHDOG 2>/dev/null

echo "=== serial output ==="
cat "$OUT" 2>/dev/null
echo "=== qemu log ==="
cat "$LOG" 2>/dev/null

# Triple fault with -no-reboot makes QEMU exit early (exit code nonzero or
# 'shutting down on triple fault' in the log).
if grep -qi "triple fault" "$LOG" 2>/dev/null; then
  echo "FAIL: triple fault detected"
  exit 1
fi

if grep -q "ROSTI: boot complete" "$OUT" 2>/dev/null; then
  echo "PASS: kernel booted and completed init (markers found)"
  exit 0
fi

if grep -q "ROSTI: entered kernel_main" "$OUT" 2>/dev/null; then
  echo "FAIL: kernel entered but init did not complete"
  exit 1
fi

echo "FAIL: no boot markers — kernel never executed (QEMU exit code $QEXIT)"
exit 1
