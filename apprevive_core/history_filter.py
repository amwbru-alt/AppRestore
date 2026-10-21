"""Exact account history minus a successfully read device inventory.

An Apple acquisition is account evidence, not proof of installation on this
particular iPhone. Catalog names, local IPA files and probe success add no rows.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Mapping, Sequence

from .catalog import _app_records, _is_placeholder, enrich_app_record, find_store_id

_BUNDLE = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\Z")
_STORE = re.compile(r"[1-9][0-9]{7,11}\Z")

@dataclass(frozen=True)
class DeviceInventory:
    installed_bundles: frozenset[str]
    installed_ids: frozenset[str]


def device_inventory(payload: object) -> DeviceInventory:
    # Validate all records first. A malformed/failed device response is never
    # interpreted as an empty phone. Placeholders need restoration, so stay eligible.
    if not isinstance(payload, (Mapping, list)):
        raise ValueError('Cannot verify applications on the connected iPhone')
    records = _app_records(payload)
    if payload and not records:
        raise ValueError('Device inventory contains no usable application records')
    bundles, ids = set(), set()
    for bundle, info in records:
        if _is_placeholder(info):
            continue
        bundles.add(bundle)
        sid = find_store_id(enrich_app_record(info))
        if sid:
            ids.add(str(sid))
    return DeviceInventory(frozenset(bundles), frozenset(ids))


def missing_history(rows: Sequence[Mapping[str, object]], inventory: DeviceInventory | None) -> list[dict[str, object]]:
    if inventory is None:
        return []
    result, seen = [], set()
    for row in rows:
        sid = str(row.get('trackId') or row.get('track_id') or '').strip()
        bundle = str(row.get('bundleId') or row.get('bundle_id') or '').strip()
        # Without a bundle ID there is no reliable comparison to the phone.
        if not _STORE.fullmatch(sid) or not _BUNDLE.fullmatch(bundle):
            continue
        if sid in seen or bundle in inventory.installed_bundles or sid in inventory.installed_ids:
            continue
        seen.add(sid)
        result.append(dict(row))
    return result
