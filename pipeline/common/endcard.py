"""Text cards rendered with Pillow: the end card (the AI label) and, in rough cuts, a placeholder for
a shot whose keyframe is not chosen yet. Step 5 replaces the font fallback chain with the OFL
font in assets/fonts/."""

from __future__ import annotations

import io
from pathlib import Path

from .cache import atomic_write_bytes
from .env import ROOT

BG = (42, 33, 28)          # warm dark brown from the palette
FG = (244, 236, 222)       # paper white
ACCENT = (214, 150, 74)    # ochre


def font(size: int):
    from PIL import ImageFont

    for name in ("assets/fonts/AtkinsonHyperlegible-Regular.ttf", "C:/Windows/Fonts/arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def wrap(text: str, f, max_w: float, draw) -> list[str]:
    """Break at the " · " separators first, then at spaces, so each row fits `max_w` pixels."""
    if draw.textlength(text, font=f) <= max_w:
        return [text]
    sep = " · " if " · " in text else " "
    rows, cur = [], ""
    for piece in text.split(sep):
        trial = f"{cur}{sep}{piece}" if cur else piece
        if cur and draw.textlength(trial, font=f) > max_w:
            rows.append(cur)
            cur = piece
        else:
            cur = trial
    return rows + [cur]


def card(lines: list[str], w: int, h: int, out: Path, *, title_scale: float = 1.6) -> Path:
    """Centred lines; the first one larger and in the accent colour."""
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(im)
    base = max(18, round(min(w, h) * 0.04))
    body = font(base)
    lines = [lines[0]] + [row for line in lines[1:] for row in wrap(line, body, w * 0.86, draw)]
    fonts = [font(round(base * title_scale))] + [body] * (len(lines) - 1)
    sizes = [draw.textbbox((0, 0), t, font=f) for t, f in zip(lines, fonts)]
    gap = round(base * 0.7)
    total = sum(b[3] - b[1] for b in sizes) + gap * (len(lines) - 1) + (gap if len(lines) > 1 else 0)
    y = (h - total) / 2
    for i, (t, f, b) in enumerate(zip(lines, fonts, sizes)):
        x = (w - (b[2] - b[0])) / 2 - b[0]
        draw.text((x, y - b[1]), t, font=f, fill=ACCENT if i == 0 else FG)
        y += (b[3] - b[1]) + gap + (gap if i == 0 else 0)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    atomic_write_bytes(out, buf.getvalue())
    return out
