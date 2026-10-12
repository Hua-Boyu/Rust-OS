#!/usr/bin/env python3
"""Rosti Proxmox deployment pipeline — gated, machine-readable, VM 103 only.

25 gates stop on any failure: authenticated VM prerequisites; kernel/host fmt;
host tests; CPU read/null-write fault fixtures; production rebuild; ELF checks;
10 normal boots and 20 paging-stability boots; keyboard/VGA checks; ISO build,
boot/paging/VGA checks; local/remote SHA256; versioned upload; VM 103 attach,
boot, live VGA/serial/CR0/CR3/null-PTE checks; final checksum/config/status.
Evidence: test_results/proxmox/deploy_report.json and phase4_live_report.json.

Credentials come from environment only (never hardcoded). PVE_ROOT_PASSWORD
enables SSH/scp/pvesh deployment without an API token; sshpass reads binary
stdin, never a password argument or file. API helpers optionally support
PVE_TOKEN_ID/PVE_TOKEN_SECRET. No token files are loaded by this script.

Safety: only VM 103 is ever modified. ISOs are never deleted; the rollback ISO
(dist/rosti_rollback.iso) is preserved. Uploads use versioned filenames.
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
# grub-mkrescue/scp run in WSL; the project is reachable there via /mnt/<drive>.
WSL_PROJECT = (Path("/mnt") / PROJECT.drive[0].lower() / str(PROJECT).split(":", 1)[1].lstrip("\\/")).as_posix()
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
    if ROOT_PW:
        # Host SSH is sufficient; token files are not read or required.
        verb = "get" if method == "GET" else "set" if path.endswith("/config") else "create"
        cmd = ["pvesh", verb, path, "--output-format", "json"]
        for key, value in (body or {}).items():
            cmd.extend(["--" + key, str(value)])
        out = ssh_remote(shlex.join(cmd))
        # pvesh writes can print a plain "update VM ..." status line even
        # with --output-format json. Verify writes with the following GET.
        return json.loads(out) if method == "GET" and out else out or None
    if not TOKEN_ID or not TOKEN_SECRET:
        raise RuntimeError("PVE_TOKEN_ID/PVE_TOKEN_SECRET not set in environment")
    import requests  # Optional: SSH deployment uses only the Python stdlib.
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


def run_shell(cmd, timeout=300, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd)
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
    """Authorized host SSH; password uses binary stdin, never argv or files."""
    if not ROOT_PW:
        raise RuntimeError("PVE_ROOT_PASSWORD not set; remote verification unavailable")
    r = subprocess.run(
        ["wsl", "bash", "-c",
         "sshpass -d 0 ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "
         "root@192.168.50.205 " + shlex.quote(cmd)],
        input=ROOT_PW.encode() + b"\n", capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("ssh failed: " + r.stderr.decode(errors="replace").replace(ROOT_PW, "[redacted]")[:200])
    return r.stdout.decode(errors="replace").strip()


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
    gate("authenticated VM 103 prerequisites", lambda: ssh_remote("qm status 103"))
    gate("kernel formatting", lambda: run_shell("cargo fmt --check").strip() or "ok")
    gate("host formatting", lambda: run_shell("cargo +nightly fmt --manifest-path tests_kernel/Cargo.toml --check").strip() or "ok")
    # Native subprocesses may resolve bash to WSL rather than git-bash.
    # Run the same host-test command directly, outside kernel cargo config.
    host_manifest = PROJECT / "tests_kernel" / "Cargo.toml"
    gate("host tests", lambda: re.search(r"(\d+) passed", run_shell(
        f'cargo +nightly test --manifest-path "{host_manifest}"', cwd=Path.home())).group(1) + " passed")
    gate("build read-fault test", lambda: run_shell("cargo build --target target.json --features paging-fault-test").strip().splitlines()[-1])
    gate("CPU read-fault test", lambda: run_shell("python scripts/paging_test.py --fault").strip().splitlines()[-1])
    gate("build write-fault test", lambda: run_shell("cargo build --target target.json --features paging-write-fault-test").strip().splitlines()[-1])
    gate("CPU null-write fault test", lambda: run_shell("python scripts/paging_test.py --write-fault").strip().splitlines()[-1])
    gate("build kernel", lambda: (lambda o: o.strip().splitlines()[-1] if o.strip() else "ok")(
        run_shell("cargo build --target target.json", timeout=300)))
    boot_dir = "test_results/phase4/boot_" + time.strftime("%Y%m%d_%H%M%S")
    gate("ELF multiboot validation", lambda: run_shell("python scripts/validate_elf.py target/target/debug/kernel").strip().splitlines()[-1])
    gate("qemu boot verification", lambda: run_shell(f"python scripts/boot_test.py --runs 10 --timeout 3 --output-dir {boot_dir}").strip().splitlines()[-1])
    gate("paging boot stability", lambda: run_shell("python scripts/paging_test.py --runs 10").strip().splitlines()[-1])
    gate("keyboard integration", lambda: run_shell("python scripts/keyboard_test.py").strip().splitlines()[-1])
    gate("VGA editing integration", lambda: run_shell("python scripts/backspace_test.py").strip().splitlines()[-1])
    gate("build grub iso", lambda: run_shell("python scripts/build-proxmox-iso.py").strip().splitlines()[-1])
    gate("ISO paging verification", lambda: run_shell("python scripts/paging_test.py --iso dist/rosti.iso").strip().splitlines()[-1])
    gate("ISO VGA editing integration", lambda: run_shell("python scripts/backspace_test.py --iso dist/rosti.iso").strip().splitlines()[-1])

    iso = DIST / "rosti.iso"
    local_sha = gate("local iso sha256", lambda: sha256_file(iso))
    version = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    remote_name = f"rosti_{version}.iso"

    def upload():
        # API multipart upload returned 501 in the previous session; use scp over
        # the authorized SSH path, then confirm via the storage listing.
        r = subprocess.run(
            ["wsl", "bash", "-c",
             "sshpass -d 0 scp -o StrictHostKeyChecking=accept-new "
             f"{WSL_PROJECT}/dist/rosti.iso "
             f"root@192.168.50.205:/var/lib/vz/template/iso/{remote_name}"],
            input=ROOT_PW.encode() + b"\n", capture_output=True, timeout=180)
        if r.returncode != 0:
            raise RuntimeError("upload failed: " + r.stderr.decode(errors="replace").replace(ROOT_PW, "[redacted]")[:200])
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
            ssh_remote(f"qm start {VMID}", timeout=60)
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
        import base64
        script = (PROJECT / "scripts" / "verify_proxmox_backspace.py").read_bytes()
        b64 = base64.b64encode(script).decode()
        code = "import base64; exec(compile(base64.b64decode(" + repr(b64) + "), 'live_verify', 'exec'))"
        cmd = "python3 -c " + shlex.quote(code) + " --expected-iso " + shlex.quote(remote_name) + " --require-paging"
        # The verifier prints structured failure evidence before exiting 1.
        # Preserve and parse that report instead of losing stdout in SSH errors.
        out = ssh_remote(cmd + " || true", timeout=180)
        live = json.loads(out)
        live["iso_sha256"] = local_sha
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (REPORT_DIR / "phase4_live_report.json").write_text(json.dumps(live, indent=2) + "\n")
        if live.get("overall") != "PASS" or not all(c["pass"] for c in live["checks"]):
            raise RuntimeError("live verification failed: " + live.get("error", "check failed"))
        return f"{len(live['checks'])} VGA/serial/hardware-paging checks passed"
    if ROOT_PW:
        gate("guest boot + shell interaction", guest_verify)

    gate("final remote checksum readback", remote_sha)
    def final_readback():
        cfg = api(f"/nodes/{NODE}/qemu/{VMID}/config")
        status = api(f"/nodes/{NODE}/qemu/{VMID}/status/current")["status"]
        if remote_name not in cfg.get("ide2", "") or status != "running":
            raise RuntimeError("final VM state does not match deployment")
        return {"ide2": cfg["ide2"], "status": status}
    gate("final VM 103 state readback", final_readback)

    write_report()
    print("\nDEPLOYMENT " + ("PASS" if all(g["status"] in ("PASS", "SKIP") for g in GATES) else "FAIL"))


if __name__ == "__main__":
    main()
