#!/usr/bin/env python3
"""Optionally vendor the official ALTCHA v3.2.1 browser bundle.

Run once with network access, inspect the JS and its SHA-256, then commit both
resulting files. Python does not generate the upstream JS file.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

VERSION = "3.2.1"
BASE = f"https://cdn.jsdelivr.net/npm/altcha@{VERSION}"
RESOURCES = {
    f"altcha-{VERSION}.min.js": BASE + "/dist/main/altcha.min.js",
    f"altcha-{VERSION}.LICENSE.txt": BASE + "/LICENSE.txt",
}
TARGET = Path(__file__).resolve().parents[1] / "static" / "js"


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "crackmesone-altcha-vendor/1.0"})
    with urlopen(request, timeout=25) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Download returned HTTP {resp.status}: {url}")
        return resp.read(2_000_000)


def main() -> int:
    payloads = {}
    try:
        for filename, url in RESOURCES.items():
            payloads[filename] = fetch(url)
    except (OSError, URLError, RuntimeError) as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1

    js = payloads[f"altcha-{VERSION}.min.js"]
    license_text = payloads[f"altcha-{VERSION}.LICENSE.txt"]
    if not (50_000 <= len(js) <= 1_000_000 and b'altcha' in js.lower()
            and b'<html' not in js[:300].lower()):
        print("Refusing unexpected ALTCHA JavaScript content", file=sys.stderr)
        return 1
    if b'MIT License' not in license_text and b'Permission is hereby granted' not in license_text:
        print("Refusing unexpected ALTCHA license content", file=sys.stderr)
        return 1
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, content in payloads.items():
        path = TARGET / name
        path.write_bytes(content)
        print(f"Wrote {path.relative_to(TARGET.parent.parent)} "
              f"({len(content)} bytes, SHA-256 {hashlib.sha256(content).hexdigest()})")
    print("Set Altcha.WidgetUrl to /static/js/altcha-3.2.1.min.js and commit the files")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
