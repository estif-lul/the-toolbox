"""`make choose ITEM=dad PICK=2`: record a choice in storyboard.json without reformatting it.

The storyboard is hand-formatted, so it is never rewritten with json.dump. The one
`*_choice` value is replaced in the text, the file is parsed again, and the edit is kept only if
exactly that field changed (anything else is a bug and nothing is written).

Items: `style`, a character id (`dad`, `me_child`, ...), a shot id (`s05`), or a split-screen
layer (`s10a`, `s10b`).
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .common import storyboard as sbm
from .common.cache import atomic_write_text


def _target(sb: dict, item: str) -> tuple[list, str]:
    """(path of keys to the object, field name) for an item."""
    if item == "style":
        return ["style"], "reference_choice"
    for i, c in enumerate(sb.get("characters") or []):
        if c["id"] == item:
            return ["characters", i], "reference_choice"
    for i, p in enumerate(sb.get("props") or []):
        if p["id"] == item:
            return ["props", i], "reference_choice"
    for i, s in enumerate(sb["shots"]):
        if s["id"] == item:
            return ["shots", i], "keyframe_choice"
        for j, layer in enumerate(s.get("layers") or []):
            if f"{s['id']}{layer['id']}" == item:
                return ["shots", i, "layers", j], "keyframe_choice"
    raise KeyError(f"unknown item {item!r}: use style, a character or prop id, a shot id or a layer like s10a")


def _anchor(sb: dict, path: list) -> list[str]:
    """Text anchors that lead to the object in the file, in order."""
    if path == ["style"]:
        return ['"style": {']
    obj = sb[path[0]][path[1]]
    anchors = [f'"id": "{obj["id"]}"']
    if len(path) > 2:
        layer = obj[path[2]][path[3]]
        anchors += ['"layers": [', f'"id": "{layer["id"]}"']
    return anchors


def choose(item: str, pick: int | None, path: Path = sbm.STORYBOARD) -> str:
    text = Path(path).read_text(encoding="utf-8")
    sb = json.loads(text)
    keys, field = _target(sb, item)
    pos = 0
    for a in _anchor(sb, keys):
        pos = text.find(a, pos)
        if pos < 0:
            raise ValueError(f"could not find {a!r} for {item} in {path}")
    m = re.compile(rf'"{field}":\s*(null|\d+)').search(text, pos)
    if not m:
        raise ValueError(f"no {field} after {item} in {path}")
    value = "null" if pick is None else str(int(pick))
    new_text = text[:m.start(1)] + value + text[m.end(1):]
    expected = copy.deepcopy(sb)
    obj = expected
    for k in keys:
        obj = obj[k]
    obj[field] = None if pick is None else int(pick)
    if json.loads(new_text) != expected:
        raise ValueError(f"refusing to write: the edit for {item} changed more than {field}")
    atomic_write_text(Path(path), new_text)
    return f"{item}: {field} = {value}"
