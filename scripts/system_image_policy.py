"""Build-time policy check, never derive or update a trust anchor from an image."""
import hashlib
import hmac
import re

from build_initramfs import build


def trusted_archive(project):
    policy = (project / 'src/system_image.rs').read_text(encoding='utf-8')
    match = re.search(r'const EXPECTED_SHA256:\s*\[u8;\s*32\]\s*=\s*\[([^\]]+)\];', policy)
    if match is None:
        raise ValueError('invalid trusted digest policy')
    words = [part.strip() for part in match[1].split(',') if part.strip()]
    if len(words) != 32 or any(re.fullmatch(r'0x[0-9a-fA-F]{2}', word) is None for word in words):
        raise ValueError('invalid trusted digest policy')
    expected = bytes(int(word, 16) for word in words)
    data = build(project / 'system')
    if not hmac.compare_digest(hashlib.sha256(data).digest(), expected):
        raise ValueError('system archive digest differs from trusted kernel policy; review inputs and explicitly update policy')
    return data
