"""Regenerate the app's icons from the brand sources in this folder.

    python3 docs/brand/build_icons.py        (needs Pillow: pip install pillow)

Sources:
    icon.jpg        colored app icon (favicon, home-screen and app icons)
    logo-white.png  white logo with transparent background (used inside the app)

Outputs:
    frontend/public/favicon.ico            16, 32 and 48 px
    frontend/public/icon-192.png           web app manifest
    frontend/public/icon-512.png           web app manifest
    frontend/public/apple-touch-icon.png   180 px, opaque (iOS rounds the corners itself)
    frontend/src/assets/logo-mask.png      the white logo as a stencil (320 px): its bands are
                                           opaque, its dark outlines and background
                                           transparent, so the app can colour it per theme
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PUBLIC = ROOT / "frontend" / "public"
ASSETS = ROOT / "frontend" / "src" / "assets"
ICON_SRC = HERE / "icon.jpg"
LOGO_SRC = HERE / "logo-white.png"

MASK_SIZE = 320  # largest in-app use is 48 px, so this stays sharp up to ~6x pixel density
BRIGHT = 250  # sum of RGB above which a pixel counts as part of the coloured border


def _is_bright(p: tuple[int, ...]) -> bool:
    return sum(p[:3]) > BRIGHT


def border_box(img: Image.Image) -> tuple[int, int, int, int]:
    """Outer edges of the rounded border line, found on the middle row and column."""
    w, h = img.size
    xs = [x for x in range(w) if _is_bright(img.getpixel((x, h // 2)))]
    ys = [y for y in range(h) if _is_bright(img.getpixel((w // 2, y)))]
    return xs[0], ys[0], xs[-1], ys[-1]


def corner_radius(img: Image.Image, left: int) -> int:
    """The border crosses the diagonal at left + r * (1 - 1/sqrt(2))."""
    d = next(t for t in range(img.width // 2) if _is_bright(img.getpixel((t, t))))
    return round((d - left) / (1 - 1 / math.sqrt(2)))


def rounded_mask(size: int, radius: int, scale: int = 4) -> Image.Image:
    big = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(big).rounded_rectangle(
        (0, 0, size * scale - 1, size * scale - 1), radius=radius * scale, fill=255
    )
    return big.resize((size, size), Image.LANCZOS)


def build_app_icons() -> None:
    src = Image.open(ICON_SRC).convert("RGB")
    left, top, right, bottom = border_box(src)
    radius = corner_radius(src, left)
    pad = 3
    box = (left - pad, top - pad, right + pad + 1, bottom + pad + 1)
    square = src.crop(box)
    size = min(square.size)
    square = square.crop((0, 0, size, size))

    # Transparent corners outside the rounded border
    icon = square.convert("RGBA")
    icon.putalpha(rounded_mask(size, radius + pad))

    PUBLIC.mkdir(parents=True, exist_ok=True)
    for px in (192, 512):
        icon.resize((px, px), Image.LANCZOS).save(PUBLIC / f"icon-{px}.png", optimize=True)
    icon.resize((256, 256), Image.LANCZOS).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    # iOS wants an opaque square and applies its own corner mask
    bg = src.getpixel((left + radius, top + 12))
    opaque = Image.new("RGB", square.size, bg)
    opaque.paste(square, (0, 0), icon)
    opaque.resize((180, 180), Image.LANCZOS).save(PUBLIC / "apple-touch-icon.png", optimize=True)
    print(f"app icons: border {left},{top}-{right},{bottom}, corner radius {radius}px")


def build_logo_mask() -> None:
    img = Image.open(LOGO_SRC).convert("RGBA")
    r, g, b, a = img.split()
    luminance = Image.merge("RGB", (r, g, b)).convert("L")
    alpha = ImageChops.multiply(a, luminance)  # white bands stay, black outlines become gaps
    alpha = alpha.crop(alpha.point(lambda v: 255 if v > 8 else 0).getbbox())

    side = max(alpha.size)
    square = Image.new("L", (side, side), 0)
    square.paste(alpha, ((side - alpha.width) // 2, (side - alpha.height) // 2))
    square = square.resize((MASK_SIZE, MASK_SIZE), Image.LANCZOS)

    # Grey + alpha is enough for a stencil and keeps the file small
    white = Image.new("L", square.size, 255)
    ASSETS.mkdir(parents=True, exist_ok=True)
    Image.merge("LA", (white, square)).save(ASSETS / "logo-mask.png", optimize=True)
    print(f"logo mask: {MASK_SIZE}x{MASK_SIZE}")


if __name__ == "__main__":
    build_app_icons()
    build_logo_mask()
