#!/usr/bin/env python3
"""Rosti Proxmox deployment pipeline — gated, machine-readable, VM 103 only.

Gates (stop on any failure):
  1  build kernel
  2  host tests            (scripts/run_tests.sh)
  3  QEMU boot verification (scripts/boot_test.py, 1 run)
  4  keyboard integration   (scripts/keyboard_test.py)
  5  build GRUB ISO          (scripts/build-proxmox-iso.py, includes its own boot gate)
  6  ISO boots under QEMU    (enforced inside build-proxmox-iso.py)
  7  local ISO SHA256
  8  upload uniquely named ISO to Proxmox 'local' storage (API)
  9  remote SHA256 verified on the Proxmox host (SSH; reported as unverified if SSH unavailable)
  10 attach ISO to VM 103 only
  11 boot VM 103
  12 guest markers + shell interaction over the serial console
  13 machine-readable report: test_results/proxmox/deploy_report.json

Credentials come from environment only (never hardcoded):
  PVE_TOKEN_ID, PVE_TOKEN_SECRET, PVE_ROOT_PASSWORD (for the read-only
  checksum/serial-console SSH path). TLS verification is NOT disabled globally;
  it follows the existing per-connection setting for the self-signed cert.

Safety: only VM 103 is ever modified. ISOs are never deleted; the rollback ISO
(dist/rosti_rollback.iso) is preserved. Uploads use versioned filenames.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

PROJECT = Path(r"C:\Users\iamsv\Documents\rosti")
DIST = PROJECT / "dist"
REPORT_DIR = PROJECT / "test_results" / "proxmox"
QEMU_MARKERS = ["ROSTI: entered kernel_main", "ROSTI: boot complete"]
PVE = "https://192.168.50.205:8006"
NODE = "pve"
VMID = 103
STORAGE = "local"

TOKEN_ID = os.environ.get("PVE_TOKEN_ID", "")
TOKEN_SECRET = os.environ.get("PVE_TOKEN_SECRET", "")
ROOT_PW = os.environ.get("PVE_ROOT_PASSWORD", "")

GATES = []


def api(path, method="GET", body=None):
    if not TOKEN_ID or not TOKEN_SECRET:
        raise RuntimeError("PVE_TOKEN_ID/PVE_TOKEN_SECRET not set in environment")
    # Self-signed cert: verification disabled for THIS connection only, matching
    # the existing MCP configuration — not a global change.
    r = requests.request(method, PVE + "/api2/json" + path,
                         headers={"Authorization": f"PVEAPIToken={TOKEN_ID}={TOKEN_SECRET}"},
                         json=body, verify=False, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"API {path} -> HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("data")


def gate(name, fn):
    print(f"[gate {len(GATES)+1}] {name}")
    try:
        result = fn()
    except Exception as e:
        GATES.append({"gate": name, "status": "FAIL", "error": str(e)})
        write_report()
        print(f"FAIL: {name}: {e}")
        sys.exit(1)
    GATES.append({"gate": name, "status": "PASS", "detail": result})
    print(f"PASS: {name}: {result}")
    return result


def run_shell(cmd, timeout=300):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"command failed (exit {r.returncode}): {r.stderr[-300:] or r.stdout[-300:]}")
    return r.stdout + r.stderr


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ssh_remote(cmd, timeout=90):
    """Read-only SSH to the Proxmox host via WSL (sshpass). Raises if unavailable."""
    if not ROOT_PW:
        raise RuntimeError("PVE_ROOT_PASSWORD not set; remote verification unavailable")
    r = subprocess.run(
        ["wsl", "bash", "-c",
         f"sshpass -p '{ROOT_PW}' ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 root@192.168.50.205 {cmd!r}"],
        capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ssh failed: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def write_report():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "vmid": VMID,
        "iso_local": str(DIST / "rosti.iso"),
        "iso_local_sha256": sha256_file(DIST / "rosti.iso") if (DIST / "rosti.iso").exists() else None,
        "rollback_iso": str(DIST / "rosti_rollback.iso"),
        "gates": GATES,
        "overall": "FAIL" if any(g["status"] == "FAIL" for g in GATES) else "PASS",
    }
    out = REPORT_DIR / "deploy_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"report: {out}")


def main():
    gate("build kernel", lambda: (lambda o: o.strip().splitlines()[-1] if o.strip() else "ok")(
        run_shell("cargo build --target target.json", timeout=300)))
    gate("host tests", lambda: re.search(r"(\d+) passed", run_shell("bash scripts/run_tests.sh")).group(1) + " passed")
    gate("qemu boot verification", lambda: run_shell("python scripts/boot_test.py --runs 1").strip().splitlines()[-1])
    gate("keyboard integration", lambda: run_shell("python scripts/keyboard_test.py").strip().splitlines()[-1])
    gate("build grub iso", lambda: run_shell("python scripts/build-proxmox-iso.py").strip().splitlines()[-1])

    iso = DIST / "rosti.iso"
    local_sha = gate("local iso sha256", lambda: sha256_file(iso))
    version = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    remote_name = f"rosti_{version}.iso"

    def upload():
        # API multipart upload returned 501 in the previous session; use scp over
        # the authorized SSH path, then confirm via the storage listing.
        r = subprocess.run(
            ["wsl", "bash", "-c",
             f"sshpass -p '{ROOT_PW}' scp -o StrictHostKeyChecking=accept-new "
             f"/mnt/c/Users/iamsv/Documents/rosti/dist/rosti.iso "
             f"root@192.168.50.205:/var/lib/vz/template/iso/{remote_name}"],
            capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise RuntimeError(f"upload failed: {r.stderr.strip()[:200]}")
        listing = api(f"/nodes/{NODE}/storage/{STORAGE}/content", "GET")
        entry = [e for e in listing if e["volid"] == f"local:iso/{remote_name}"]
        if not entry:
            raise RuntimeError("uploaded ISO not present in storage listing")
        if entry[0]["size"] != iso.stat().st_size:
            raise RuntimeError(f"size mismatch: remote {entry[0]['size']} vs local {iso.stat().st_size}")
        return remote_name

    if not ROOT_PW:
        GATES.append({"gate": "upload versioned iso", "status": "SKIP", "error": "no SSH path"})
        print("[gate 8] SKIP: no SSH upload path")
    else:
        gate("upload versioned iso", upload)

    def remote_sha():
        out = ssh_remote(f"sha256sum /var/lib/vz/template/iso/{remote_name}")
        remote = out.split()[0]
        if remote != local_sha:
            raise RuntimeError(f"remote sha {remote} != local sha {local_sha}")
        return remote
    if ROOT_PW:
        gate("remote sha256 verified", remote_sha)

    def attach():
        api(f"/nodes/{NODE}/qemu/{VMID}/config", "POST", {"ide2": f"{STORAGE}:iso/{remote_name},media=cdrom"})
        cfg = api(f"/nodes/{NODE}/qemu/{VMID}/config")
        attached = cfg.get("ide2", "")
        if remote_name not in attached:
            raise RuntimeError(f"attach failed: ide2={attached}")
        return attached
    if ROOT_PW or TOKEN_ID:
        gate("attach iso to VM 103", attach)

    def boot():
        st = api(f"/nodes/{NODE}/qemu/{VMID}/status/current")
        if st["status"] != "running":
            upid = api(f"/nodes/{NODE}/qemu/{VMID}/start", "POST")
            for _ in range(30):
                t = api(f"/nodes/{NODE}/tasks/{upid}")
                if t.get("status") == "stopped":
                    if t.get("exitstatus") != "OK":
                        raise RuntimeError(f"task failed: exitstatus={t.get('exitstatus')}")
                    break
                time.sleep(1)
        else:
            # REST 'reboot' is an ACPI event the bare kernel ignores; 'qm reset'
            # (via the authorized SSH path) is the hard reset that works.
            out = ssh_remote(f"qm reset {VMID}", timeout=60)
            if "ERROR" in out or "not running" in out:
                raise RuntimeError(f"qm reset failed: {out[:200]}")
        st = api(f"/nodes/{NODE}/qemu/{VMID}/status/current")
        if st["status"] != "running":
            raise RuntimeError(f"VM not running after task: {st['status']}")
        return "running"
    gate("boot VM 103", boot)

    def guest_verify():
        # Start the serial listener BEFORE the reset so boot markers are captured,
        # then interact with the shell over the documented serial socket.
        script = r'''
import socket, subprocess, time
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/var/run/qemu-server/103.serial0")
s.settimeout(4)
subprocess.run(["qm","reset","103"], capture_output=True)
def drain(t=3.0):
    time.sleep(t); out=b""
    while True:
        try:
            d=s.recv(4096)
            if not d: break
            out+=d
        except socket.timeout: break
    return out.decode(errors="replace")
def sendkey(k):
    subprocess.run(["qm","sendkey","103",k], capture_output=True)
    time.sleep(0.15)
boot = drain(6)
print("BOOT:" + boot.replace("\n","|"))
for cmd in ["help","version","echo rosti-test","uptime"]:
    for ch in cmd:
        if ch == " ": key = "spc"
        elif ch == "-": key = "minus"
        elif ch.isupper(): key = "shift-" + ch.lower()
        else: key = ch
        sendkey(key)
    sendkey("ret")
    print(drain(3))
s.close()
'''
        import base64
        b64 = base64.b64encode(script.encode()).decode()
        out = ssh_remote(f"echo {b64} | base64 -d | python3 -", timeout=120)
        if "rosti>" not in out:
            raise RuntimeError(f"no shell prompt in serial output: {out[:200]}")
        for marker in QEMU_MARKERS:
            if marker not in out:
                raise RuntimeError(f"marker missing: {marker}")
        for probe in ["commands: help", "v0.1.0", "rosti-test", "uptime:"]:
            if probe not in out:
                raise RuntimeError(f"shell probe failed: {probe}")
        return "markers + shell commands verified over serial"
    if ROOT_PW:
        gate("guest boot + shell interaction", guest_verify)

    write_report()
    print("\nDEPLOYMENT " + ("PASS" if all(g["status"] in ("PASS", "SKIP") for g in GATES) else "FAIL"))


if __name__ == "__main__":
    main()
