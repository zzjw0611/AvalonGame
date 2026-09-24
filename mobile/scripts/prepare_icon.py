from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "assets" / "icon-source"
TARGET = ROOT / "assets" / "icon.png"
EXPECTED_SHA256 = "cf4fe07f1f2a2249c52a748abb4ecf7d6db4f38dbb7cdd38592abe419fba334e"

encoded = "".join(path.read_text(encoding="ascii").strip() for path in sorted(PARTS.glob("*.b64")))
raw = base64.b64decode(encoded, validate=True)

actual = hashlib.sha256(raw).hexdigest()
if actual != EXPECTED_SHA256:
    raise SystemExit(f"App icon source checksum mismatch: {actual}")

with Image.open(BytesIO(raw)) as image:
    image.load()
    if image.size != (128, 128) or image.format != "JPEG":
        raise SystemExit(f"Unexpected app icon source: {image.format} {image.size}")
    image = image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
    image.save(TARGET, format="PNG", optimize=False, compress_level=6)

with Image.open(TARGET) as check:
    check.load()
    if check.size != (1024, 1024) or check.format != "PNG":
        raise SystemExit("Generated app icon failed validation")

print(f"Prepared app icon: {TARGET} ({TARGET.stat().st_size} bytes)")
