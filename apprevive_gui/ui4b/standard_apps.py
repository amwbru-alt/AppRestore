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
    metadata = _bank_metadata()
    return [dict(trackId=store_id, name=name, **metadata.get(store_id, {})) for store_id, name in _catalog()]


@lru_cache(maxsize=1)
def _bank_metadata():
    groups = json.loads((Path(__file__).parent / "data" / "bank_groups.json").read_text(encoding="utf-8"))
    return {app["trackId"]: dict(groupId=group["id"], groupName=group["name"], groupIconUrl=group.get("iconUrl", ""))
            for group in groups for app in group["apps"]}
