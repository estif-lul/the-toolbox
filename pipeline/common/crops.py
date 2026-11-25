"""Where each export cuts the square master. One function, used by the keyframe crop previews
(so a choice is made on what will really be seen) and by the edit (so it cuts exactly there).

The masters are 1024x1024. A 9:16 export keeps a 576x1024 column, a 16:9 export a 1024x576 band;
the s10 split screen keeps a 1024x910 band per half in 9:16 (two 720x640 halves stacked) and a
910x1024 column per half in 16:9 (two 640x720 halves side by side). `crop_focus` (0..1) says
where the column or band sits; it is clamped so the crop never leaves the frame.
"""

from __future__ import annotations

# export name -> (target w, target h) for full frames and for one half of the split screen
FULL = {"9x16": (720, 1280), "16x9": (1280, 720)}
HALF = {"9x16": (720, 640), "16x9": (640, 720)}


def crop_box(target_w: int, target_h: int, focus: dict | None = None, size: int = 1024) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the largest region of a size x size square with the target's aspect,
    centred on `focus` as far as the frame allows. Even numbers (yuv420p needs them)."""
    fx = float((focus or {}).get("x", 0.5))
    fy = float((focus or {}).get("y", 0.5))
    if target_w < target_h:  # portrait: a full-height column
        w, h = round(size * target_w / target_h), size
    else:
        w, h = size, round(size * target_h / target_w)
    w, h = w - w % 2, h - h % 2
    x = min(max(round(fx * size - w / 2), 0), size - w)
    y = min(max(round(fy * size - h / 2), 0), size - h)
    return x - x % 2, y - y % 2, w, h


def export_crop(export: str, focus: dict | None = None, *, half: bool = False, size: int = 1024):
    tw, th = (HALF if half else FULL)[export]
    return crop_box(tw, th, focus, size)
