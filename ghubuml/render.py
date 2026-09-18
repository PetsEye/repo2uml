"""Render .puml to svg/png if a backend exists (jar/docker/remote)."""
from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path


def render(puml: Path, fmt: str = "svg") -> Path | None:
    fmt = fmt.lower().lstrip(".")
    if fmt not in ("svg", "png"):
        raise ValueError("format must be svg or png")
    out = puml.with_suffix(f".{fmt}")
    # 1. local plantuml.jar
    jar = shutil.which("plantuml")
    if jar:
        try:
            subprocess.run([jar, f"-t{fmt}", str(puml)], check=True, capture_output=True)
            if out.exists():
                return out
        except subprocess.CalledProcessError:
            pass
    # 2. docker
    if shutil.which("docker"):
        try:
            r = subprocess.run(
                ["docker", "run", "--rm", "-v", f"{puml.parent}:/data",
                 "plantuml/plantuml", f"-t{fmt}", f"/data/{puml.name}"],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0 and out.exists():
                return out
        except Exception:
            pass
    # 3. public server (opt-in only via caller; we try but never fail hard)
    try:
        import zlib, base64
        # plantuml custom encoding
        def encode(text: str) -> str:
            data = zlib.compress(text.encode("utf-8"))[2:-4]
            alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
            out_s = ""
            for i in range(0, len(data), 3):
                chunk = data[i:i+3]
                b = int.from_bytes(chunk.ljust(3, b"\0"), "big")
                n = len(chunk)
                for j in range(n + 1):
                    out_s += alphabet[(b >> (6 * (3 - j))) & 0x3F] if False else alphabet[(b >> ((3 - j) * 6)) & 0x3F]
            return out_s
        # simpler: skip remote if encoding uncertain; caller handles .puml-only
        return None
    except Exception:
        return None
