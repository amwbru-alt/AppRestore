"""Owned apps not found in checked App Store storefronts; catalog only supplies metadata."""

from __future__ import annotations

import re
from .region import to_status
from apprevive_core.region_probe import RegionStatus

TITLE = "Удалённые из App Store"
CLOSE = "Закрыть"
ACTION = "Восстановить"
PLACEHOLDER = "Название приложения или ID"
ID_PLACEHOLDER = "ID приложения, если его нет в списке"
ID_ACTION = "Скачать"
ID_BAD = "Нужен ID приложения — число из ссылки App Store"
SIGNIN_TEXT = "Войдите в Apple ID, чтобы увидеть историю покупок"
SIGNIN_LINK = "Войти"
EMPTY_TEXT = "В этом Apple ID пока нет покупок"
NO_MATCH = "В истории нет такого названия"
LOADING = "Загружаем историю покупок…"
FAILED = "Историю покупок не удалось обновить."

# App Store adam ids are 8–12 digits. A pasted card link looks like …/id492224193.
_STORE_ID = re.compile(r"[1-9]\d{7,11}")
_ID_LINK = re.compile(r"(?i)(?:^|[^a-z0-9])id([1-9]\d{7,11})(?!\d)")


def _purchase_word(count: int) -> str:
    n = abs(count) % 100
    tail = n % 10
    if 11 <= n <= 14 or tail == 0 or tail >= 5:
        return "покупок"
    if tail == 1:
        return "покупка"
    return "покупки"


def parse_store_id(text: object) -> str:
    """The App Store id from digits or from one ``id…`` in a pasted link."""

    raw = str(text or "").strip()
    if not raw:
        return ""
    compact = re.sub(r"\s+", "", raw)
    if _STORE_ID.fullmatch(compact):
        return compact
    found = _ID_LINK.findall(raw)
    if len(found) == 1:
        return found[0]
    return ""


def name_for_store_id(items: list[dict[str, object]], store_id: str) -> str:
    """The history title for this id, when the list already has the app."""

    for item in items:
        sid = str(item.get("trackId") or item.get("track_id") or "").strip()
        if sid != store_id:
            continue
        name = str(item.get("name") or "").strip()
        if name and name != store_id and not name.isdigit():
            return name
    return ""


def _norm(text: object) -> str:
    return str(text or "").casefold().replace("ё", "е")


_TOKEN = re.compile(r"[0-9a-zа-я]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(_norm(text))


def _matches(needle: str, name: str, bundle: str, store_id: str) -> bool:
    """A short query is a whole word. «вк» inside «доставка» is not VK."""

    if not needle:
        return True
    if needle in store_id:
        return True
    folded_name, folded_bundle = _norm(name), _norm(bundle)
    if len(needle) >= 3:
        return needle in folded_name or needle in folded_bundle
    tokens = _tokens(name) + _tokens(bundle)
    if needle in ("вк", "vk"):
        return any(
            token in ("вк", "vk") or token.startswith(("вконтакте", "vkontakte"))
            for token in tokens
        )
    return needle in tokens


def _date(value: object) -> str:
    text = str(value or "")[:10]
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match is None:
        return ""
    year, month, day = match.groups()
    return f"{day}.{month}.{year}"


def _rows(items: list[dict[str, object]], query: str) -> list[dict[str, object]]:
    needle = _norm(query).strip()
    seen: set[str] = set()
    picked: list[dict[str, object]] = []
    for item in items:
        store_id = str(item.get("trackId") or item.get("track_id") or "").strip()
        if not store_id.isdigit() or store_id in seen:
            continue
        name = str(item.get("name") or "").strip() or str(item.get("bundleId") or "").strip() or "Приложение"
        bundle = str(item.get("bundleId") or item.get("bundle_id") or "")
        if needle and not _matches(needle, name, bundle, store_id):
            continue
        seen.add(store_id)
        raw_date = str(item.get("date") or item.get("purchase_date") or "")[:10]
        shown = _date(raw_date)
        picked.append({
            "kind": "app",
            "storeId": store_id,
            "bundleId": bundle,
            "iconUrl": str(item.get("iconUrl") or ""),
            "name": name,
            "developer": f"куплено {shown}" if shown else "",
            "action": ACTION,
            "enabled": True,
            "_date": raw_date,
        })
    picked.sort(key=lambda row: _norm(row["name"]))
    picked.sort(key=lambda row: str(row["_date"]), reverse=True)
    for row in picked:
        row.pop("_date", None)
    return picked


def history_view(
    items: list[dict[str, object]],
    *,
    signed_in: bool,
    busy: bool = False,
    failed: bool = False,
    query: str = "",
    id_note: str = "",
    catalog: list[dict[str, object]] | None = None,
    statuses: dict[str, object] | None = None,
    checking: bool = False,
    installed_ids: set[str] | None = None,
) -> dict[str, object]:
    """Only owned, absent-from-store candidates; catalog is metadata, not proof."""
    statuses = statuses or {}
    installed_ids = installed_ids or set()
    metadata = {str(item.get("trackId")): item for item in (catalog or [])}
    eligible = []
    if signed_in:
        for item in items:
            sid = str(item.get("trackId") or item.get("track_id") or "")
            if sid not in installed_ids and to_status(statuses.get(sid)) is RegionStatus.DELISTED:
                item = dict(item)
                if not item.get("name") or str(item.get("name")).isdigit():
                    item["name"] = metadata.get(sid, {}).get("name") or item.get("name")
                eligible.append(item)
    rows = _rows(eligible, query)
    metadata = {str(item.get("trackId")): item for item in (catalog or [])}
    for row in rows:
        info = metadata.get(row["storeId"], {})
        if info.get("iconUrl"):
            row["iconUrl"] = str(info["iconUrl"])
        if row["name"] == "Приложение" and info.get("name"):
            row["name"] = str(info["name"])
        row["developer"] = "Есть в истории Apple ID · Не найдено в проверенных витринах"
    unknown = sum(to_status(statuses.get(str(item.get("trackId") or item.get("track_id") or ""))) is RegionStatus.UNKNOWN for item in items) if signed_in else 0
    if not signed_in:
        empty, link, lead = SIGNIN_TEXT, SIGNIN_LINK, ""
    else:
        link = ""
        if busy or checking:
            lead = "Проверяем историю Apple ID и доступность приложений…"
            empty = ""
        elif failed:
            lead = FAILED
            empty = "Нет подтверждённых результатов. Повторите проверку." if not rows else ""
        elif unknown:
            lead = f"Найдено: {len(rows)}. Не удалось проверить: {unknown}."
            empty = "Проверка части приложений не завершена. Повторите позже." if not rows else ""
        else:
            lead = f"Найдено: {len(rows)}"
            empty = "Совпадений нет." if query.strip() and not rows else "В истории Apple ID не найдено приложений, недоступных в проверенных витринах." if not rows else ""
        lead += " Наличие в других странах и возможность загрузки могут отличаться."
    return {
        "title": TITLE, "close": CLOSE, "placeholder": PLACEHOLDER,
        "signedIn": signed_in, "allowManualId": False,
        "idPlaceholder": ID_PLACEHOLDER, "idAction": ID_ACTION,
        "idNote": id_note if signed_in else "",
        "lead": lead, "spinner": "Проверяем приложения…" if signed_in and (busy or checking) else "",
        "empty": empty, "emptyLink": link, "rows": rows,
    }
