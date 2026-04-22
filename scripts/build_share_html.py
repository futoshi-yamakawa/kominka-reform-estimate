#!/usr/bin/env python3
from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
SHARE_PATH = ROOT / "kominka_reform_estimate_share.html"


def embed_image(match: re.Match[str]) -> str:
    prefix = match.group(1)
    src = match.group(2)
    suffix = match.group(3)
    if src.startswith("data:"):
        return match.group(0)
    image_path = ROOT / src
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f'{prefix}data:{mime_type};base64,{encoded}{suffix}'


def main() -> None:
    html = INDEX_PATH.read_text(encoding="utf-8")
    html = re.sub(r'(<img\b[^>]*\bsrc=")(image_assets/[^"]+)(")', embed_image, html)
    SHARE_PATH.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
