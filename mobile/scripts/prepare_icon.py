from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "icon-source.jpg.b64"
TARGET = ROOT / "assets" / "icon.png"

raw = base64.b64decode(SOURCE.read_text(encoding="ascii"), validate=True)

with Image.open(BytesIO(raw)) as image:
    image.load()
    if image.width != image.height:
        raise SystemExit("App icon source must be square")
    image = image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
    image.save(TARGET, format="PNG", optimize=False, compress_level=6)

with Image.open(TARGET) as check:
    check.load()
    if check.size != (1024, 1024) or check.format != "PNG":
        raise SystemExit("Generated app icon failed validation")

print(f"Prepared app icon: {TARGET} ({TARGET.stat().st_size} bytes)")
