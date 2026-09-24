from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "assets" / "icon-source"
TARGET = ROOT / "assets" / "icon.png"
EXPECTED_SHA256 = "5a9e2e442d4dec6e36f998c522643cefe2801d7998e271286343f213c25383e8"

encoded = "".join((PARTS / name).read_text(encoding="ascii").strip() for name in ("00.b64", "01.b64"))
raw = base64.b64decode(encoded, validate=True)

actual = hashlib.sha256(raw).hexdigest()
if actual != EXPECTED_SHA256:
    raise SystemExit(f"App icon source checksum mismatch: {actual}")

with Image.open(BytesIO(raw)) as image:
    image.load()
    if image.size != (64, 64) or image.format != "JPEG":
        raise SystemExit(f"Unexpected app icon source: {image.format} {image.size}")
    image = image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
    image.save(TARGET, format="PNG", optimize=False, compress_level=6)

with Image.open(TARGET) as check:
    check.load()
    if check.size != (1024, 1024) or check.format != "PNG":
        raise SystemExit("Generated app icon failed validation")

print(f"Prepared app icon: {TARGET} ({TARGET.stat().st_size} bytes)")
