import json, socket
s = socket.socket(socket.AF_UNIX)
s.settimeout(10)
s.connect("/var/run/qemu-server/103.qmp")
f = s.makefile("rwb")
json.loads(f.readline())
def cmd(name, **args):
    f.write(json.dumps({"execute": name, "arguments": args}).encode() + b"\n")
    f.flush()
    while True:
        r = json.loads(f.readline())
        if "error" in r: raise RuntimeError(r["error"])
        if "return" in r: return r["return"]
cmd("qmp_capabilities")
regs = cmd("human-monitor-command", **{"command-line": "info registers"})
out = {line.split("=")[0]: line.split("=")[1] for line in regs.splitlines() if line.startswith("CR")}
print(json.dumps(out))
