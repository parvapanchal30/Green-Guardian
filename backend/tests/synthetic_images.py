"""SYNTHETIC test images. These are random geometric drawings generated from a seed: they are fixtures for exercising the
data-quality code and are NOT plants, leaves or any biological data, and must never be described as such."""

from __future__ import annotations

import io
import random

from PIL import Image, ImageDraw


def drawing(seed: int, size: int = 128) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new("RGB", (size, size), tuple(rng.randrange(256) for _ in range(3)))
    d = ImageDraw.Draw(img)
    for _ in range(12):
        x0, y0 = rng.randrange(size), rng.randrange(size)
        x1, y1 = x0 + rng.randrange(10, size // 2), y0 + rng.randrange(10, size // 2)
        colour = tuple(rng.randrange(256) for _ in range(3))
        (d.ellipse if rng.random() < 0.5 else d.rectangle)((x0, y0, x1, y1), fill=colour)
    return img


def encode(img: Image.Image, fmt: str = "PNG", **kw) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


def png(seed: int, size: int = 128) -> bytes:
    return encode(drawing(seed, size), "PNG")


def jpeg(seed: int, size: int = 128, quality: int = 90) -> bytes:
    return encode(drawing(seed, size), "JPEG", quality=quality)
