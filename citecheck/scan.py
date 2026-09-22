"""Turn a clean Item 9A section into something that looks like a scan, then OCR it.

Every filing in this corpus is clean HTML from EDGAR. Real audit evidence is
scanned paper, screenshots and photographed documents, which is the harder half
of the problem and the half that isn't here.

Going to find real scanned filings would mean losing the ground truth, and the
labels took long enough the first time. So the documents are degraded instead:
render the known text to a page, rough it up the way a scanner does, and read it
back with OCR. That leaves both versions of the same document in hand, which is
what makes the interesting measurement possible.

A citation can resolve perfectly against OCR output that OCR got wrong. The
quote matches, the offsets are right, and the underlying document says something
else. That failure cannot happen when the text layer is exact, and it is the one
a real audit workflow runs into first.
"""
from __future__ import annotations

import random
import textwrap
from dataclasses import dataclass

import pytesseract
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PAGE = (1700, 2200)          # ~200 dpi letter
MARGIN = 150
LINE_HEIGHT = 34
WRAP = 92

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/Library/Fonts/Times New Roman.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _font(size: int = 26) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


@dataclass
class Degradation:
    """How rough to make the page. Defaults are a decent office scanner."""

    rotation: float = 0.4     # degrees of skew
    blur: float = 0.6
    noise: int = 12           # max per-pixel deviation
    jpeg_quality: int = 55
    seed: int = 0

    @classmethod
    def clean(cls) -> "Degradation":
        """Render and OCR with no damage, to separate rendering loss from scan loss."""
        return cls(rotation=0.0, blur=0.0, noise=0, jpeg_quality=95)

    @classmethod
    def rough(cls) -> "Degradation":
        """A bad fax or a photographed page."""
        return cls(rotation=1.1, blur=1.2, noise=26, jpeg_quality=35)


def render(text: str, font_size: int = 26) -> list[Image.Image]:
    """Lay the section out over as many pages as it needs."""
    font = _font(font_size)
    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, WRAP) or [""])

    per_page = (PAGE[1] - 2 * MARGIN) // LINE_HEIGHT
    pages = []
    for start in range(0, len(lines), per_page):
        image = Image.new("L", PAGE, 255)
        draw = ImageDraw.Draw(image)
        y = MARGIN
        for line in lines[start : start + per_page]:
            draw.text((MARGIN, y), line, fill=20, font=font)
            y += LINE_HEIGHT
        pages.append(image)
    return pages


def degrade(image: Image.Image, how: Degradation) -> Image.Image:
    rng = random.Random(how.seed)
    out = image
    if how.rotation:
        out = out.rotate(rng.uniform(-how.rotation, how.rotation),
                         resample=Image.BILINEAR, fillcolor=255)
    if how.blur:
        out = out.filter(ImageFilter.GaussianBlur(how.blur))
    if how.noise:
        pixels = out.load()
        width, height = out.size
        # Sampling beats touching every pixel and looks the same to OCR.
        for _ in range((width * height) // 40):
            x, y = rng.randrange(width), rng.randrange(height)
            value = pixels[x, y] + rng.randint(-how.noise, how.noise)
            pixels[x, y] = max(0, min(255, value))
    return out


def ocr(pages: list[Image.Image]) -> str:
    """Read the pages back. One config, no per-document tuning."""
    return "\n".join(
        pytesseract.image_to_string(page, config="--psm 6") for page in pages
    ).strip()


def scan(text: str, how: Degradation | None = None) -> str:
    """Clean text in, OCR'd text out."""
    how = how or Degradation()
    return ocr([degrade(page, how) for page in render(text)])
