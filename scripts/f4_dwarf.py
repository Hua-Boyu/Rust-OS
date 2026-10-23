"""Derive F4 target layouts from the exact ELF's DWARF via readelf.

No guessed repr(Rust) offsets. Refuse unsupported member-location expressions.
The large readelf stream stays out of chat; retain its digest and small layouts.
"""
import hashlib
from pathlib import Path
import re
import subprocess


def need(value, message):
    if not value:
        raise ValueError(message)


def number(value):
    need(re.fullmatch(r"(?:0x[0-9a-fA-F]+|[0-9]+)", value.strip()) is not None,
         "nonconstant DWARF number: " + value)
    return int(value, 0) if value.startswith("0x") else int(value)


def name(node):
    raw = node["attrs"].get("name", "")
    return raw.rsplit("): ", 1)[-1]


def reference(node, attribute="type"):
    raw = node["attrs"].get(attribute, "")
    match = re.fullmatch(r"<0x([0-9a-fA-F]+)>", raw)
    need(match is not None, "unsupported DWARF reference " + raw)
    return int(match.group(1), 16)


def parse(text):
    nodes, stack, current = {}, [], None
    for line in text.splitlines():
        h = re.match(r"\s*<(\d+)><([0-9a-fA-F]+)>:.*?(?:\((DW_TAG_\w+)\))?\s*$", line)
        if h:
            depth, offset = int(h.group(1)), int(h.group(2), 16)
            # Explicitly re-read tag; the optional regex must not swallow it.
            tag = re.search(r"\((DW_TAG_\w+)\)", line)
            while stack and stack[-1]["depth"] >= depth:
                stack.pop()
            current = None
            if tag:
                node = {"offset": offset, "depth": depth, "tag": tag.group(1), "attrs": {}, "children": []}
                if stack:
                    stack[-1]["children"].append(node)
                nodes[offset] = node
                stack.append(node)
                current = node
            continue
        attr = re.search(r"DW_AT_(\w+)\s*:\s*(.*)$", line)
        if attr and current is not None:
            current["attrs"][attr.group(1)] = attr.group(2)
    return nodes


def members(node):
    return {name(c): c for c in node["children"] if c["tag"] == "DW_TAG_member" and name(c)}


def layout(node):
    return {"size": number(node["attrs"]["byte_size"]),
            "fields": {n: number(c["attrs"]["data_member_location"]) for n, c in members(node).items()}}


def select(nodes, type_name, required):
    candidates = [n for n in nodes.values() if n["tag"] == "DW_TAG_structure_type"
                  and name(n) == type_name and "byte_size" in n["attrs"]
                  and set(required) <= set(members(n))]
    need(candidates, "DWARF type absent: " + type_name)
    signatures = [layout(n) for n in candidates]
    need(all(s == signatures[0] for s in signatures), "ambiguous target layout " + type_name)
    return candidates[0]


def unwrap_offset(nodes, mutex):
    inner = members(mutex)["inner"]
    cell = nodes[reference(inner)]
    value = members(cell)["value"]
    return number(inner["attrs"]["data_member_location"]) + number(value["attrs"]["data_member_location"])


def extract(kernel):
    kernel = Path(kernel).resolve()
    need(kernel.is_file() and re.match(r"^[A-Za-z]:", str(kernel)), "native Windows ELF path required")
    posix = kernel.as_posix()
    wsl_path = "/mnt/" + posix[0].lower() + posix[2:]
    command = ["wsl.exe", "-d", "Ubuntu", "--", "readelf", "--debug-dump=info", wsl_path]
    process = subprocess.run(command, capture_output=True, timeout=180)
    need(process.returncode == 0, "readelf failed: " + process.stderr.decode(errors="replace")[-1000:])
    nodes = parse(process.stdout.decode("utf-8"))
    owner = select(nodes, "RetainedOwner", ("payload", "sentinel", "user_stack", "arena_table", "arena_capture", "capture"))
    allocator = select(nodes, "FrameAllocator", ("domain", "alloc_id", "runtime_pins", "structure_pins", "stats"))
    lease = select(nodes, "FrameLease", ("addr", "id", "domain"))
    owner_mutex = select(nodes, "SpinMutex<kernel::memory::paging::retained_owner::RetainedOwner>", ("inner", "lock"))
    allocator_mutex = select(nodes, "SpinMutex<kernel::memory::frame::FrameAllocator>", ("inner", "lock"))
    stats = nodes[reference(members(allocator)["stats"])]
    option = nodes[reference(members(owner)["payload"])]
    part = [n for n in option["children"] if n["tag"] == "DW_TAG_variant_part"]
    need(len(part) == 1, "one option variant part")
    discr = nodes[reference(part[0], "discr")]
    variants = [n for n in part[0]["children"] if n["tag"] == "DW_TAG_variant"]
    some = [n for n in variants if number(n["attrs"]["discr_value"]) == 1]
    none = [n for n in variants if number(n["attrs"]["discr_value"]) == 0]
    need(len(some) == len(none) == 1 and len(variants) == 2, "explicit None0/Some1 Option discriminants")
    some_member = members(some[0])["Some"]
    some_type = nodes[reference(some_member)]
    payload = members(some_type)["__0"]
    need(reference(payload) == lease["offset"], "option payload is reviewed FrameLease type")
    option_layout = {"size": number(option["attrs"]["byte_size"]),
                     "discriminant_offset": number(discr["attrs"]["data_member_location"]),
                     "some_discriminant": 1, "none_discriminant": 0,
                     "lease_offset": number(some_member["attrs"]["data_member_location"]) + number(payload["attrs"]["data_member_location"])}
    need(option_layout["lease_offset"] + layout(lease)["size"] <= option_layout["size"], "Option lease range")
    version = subprocess.check_output(["wsl.exe", "-d", "Ubuntu", "--", "readelf", "--version"], text=True).splitlines()[0]
    return {"schema": "rosti.f4-target-dwarf.v1", "kernel_sha256": hashlib.sha256(kernel.read_bytes()).hexdigest(),
            "command": command, "readelf_exit": process.returncode, "readelf_version": version,
            "readelf_stdout_sha256": hashlib.sha256(process.stdout).hexdigest(),
            "RetainedOwner": layout(owner), "FrameAllocator": layout(allocator), "FrameLease": layout(lease),
            "FrameStats": layout(stats), "OwnerMutex": layout(owner_mutex), "AllocatorMutex": layout(allocator_mutex),
            "owner_inner_offset": unwrap_offset(nodes, owner_mutex),
            "allocator_inner_offset": unwrap_offset(nodes, allocator_mutex), "OptionFrameLease": option_layout}
