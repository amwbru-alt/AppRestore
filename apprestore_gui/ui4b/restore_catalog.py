"""Local name -> App Store ID hints, never evidence of account ownership."""
from __future__ import annotations

from .frequent import load

_VK = "564177498"


def search_candidates(query: str, owned_ids: set[str]) -> list[dict[str, object]]:
    term = query.strip().casefold().replace("ё", "е")
    if len(term) < 2:
        return []
    entries = list(load())
    from apprestore_core.delisted_search import builtin_entries
    for entry in builtin_entries():
        entries.append({"storeId": str(entry.track_id), "name": entry.name, "detail": entry.brand or ""})
    found = []
    seen = set(owned_ids)
    for entry in entries:
        sid = str(entry.get("storeId") or "")
        if not sid.isdigit() or sid in seen:
            continue
        name = str(entry.get("name") or "")
        text = (name + " " + str(entry.get("detail") or "")).casefold().replace("ё", "е")
        matches = term in text if len(term) >= 3 else term in text.split()
        if sid == _VK and term in {"vk", "вк", "вконтакте", "vkontakte"}:
            matches = True
        if not matches:
            continue
        seen.add(sid)
        found.append({"kind": "app", "storeId": sid, "bundleId": "", "name": name,
                      "developer": "Каталог восстановления · лицензия Apple ID ещё не проверена",
                      "action": "Проверить и вернуть", "enabled": True, "catalogHint": True})
    return found[:30]
