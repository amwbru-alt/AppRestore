"""Bundled application IDs from pdx15/ipatool-webGUI, available offline."""
from __future__ import annotations
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def _catalog() -> tuple[tuple[str, str], ...]:
    data = json.loads((Path(__file__).parent / "data" / "standard_apps.json").read_text(encoding="utf-8"))
    return tuple((item["trackId"], item["name"]) for item in data)


def standard_apps() -> list[dict[str, object]]:
    return [{"trackId": store_id, "name": name} for store_id, name in _catalog()]
