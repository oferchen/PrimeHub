"""Rail listing and search views for PrimeFlix.

Routes from :mod:`resources.lib.router` with ``action=list`` and
``action=search`` land here. The module fetches paged rail data via
:mod:`resources.lib.backend.prime_api`, builds playable list items, and feeds
them to Kodi.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

try:  # pragma: no cover - Kodi runtime
    import xbmcplugin
    import xbmcgui
    import xbmcaddon
except ImportError:  # pragma: no cover - local dev fallback
    class _PluginStub:
        handle = 1

        @staticmethod
        def addDirectoryItems(handle, items):  # type: ignore[override]
            for url, listitem, isFolder in items:
                print(f"ADD: {listitem.getLabel()} -> {url} ({'folder' if isFolder else 'item'})")

        @staticmethod
        def addDirectoryItem(handle, url, listitem, isFolder=False):
            print(f"ADD: {listitem.getLabel()} -> {url} ({'folder' if isFolder else 'item'})")

        @staticmethod
        def setContent(handle, content):
            print(f"SET CONTENT: {content}")

    class _ListItemStub:
        def __init__(self, label: str):
            self._label = label
            self._art = {}
            self._info = {}
            self._properties: Dict[str, str] = {}

        def setArt(self, art: Dict[str, str]):
            self._art = art

        def setInfo(self, info_type: str, info: Dict[str, object]):
            self._info = info

        def setProperty(self, key: str, value: str) -> None:
            self._properties[key] = value

        def getLabel(self) -> str:
            return self._label

    class _AddonStub:
        @staticmethod
        def getLocalizedString(code: int) -> str:
            return str(code)

    class _DialogStub:
        @staticmethod
        def input(heading: str):
            print(f"INPUT REQUESTED: {heading}")
            return ""

    xbmcplugin = _PluginStub()  # type: ignore
    xbmcgui = type("gui", (), {"ListItem": _ListItemStub, "Dialog": _DialogStub})  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": lambda *args, **kwargs: _AddonStub()})  # type: ignore

from ..backend.prime_api import BackendError, get_backend
from ..perf import log_duration, timed
from ..preflight import ensure_ready_or_raise

# Rail definitions used by home, listings, and diagnostics
RAIL_DEFINITIONS: List[Dict[str, object]] = [
    {"id": "continue", "label": 30010, "type": "mixed", "page_size": 25},
    {"id": "originals", "label": 30011, "type": "mixed", "page_size": 25},
    {"id": "movies", "label": 30012, "type": "movies", "page_size": 25},
    {"id": "tv", "label": 30013, "type": "tv", "page_size": 25},
    {"id": "recommended", "label": 30014, "type": "mixed", "page_size": 25},
]

DEFAULT_SEARCH_PAGE_SIZE = 25
DEFAULT_RAIL_TYPE = "videos"
WARM_THRESHOLD_MS = 150.0
COLD_THRESHOLD_MS = 500.0


def _rail_meta(rail_id: str) -> Tuple[str, int, int]:
    for rail in RAIL_DEFINITIONS:
        if rail["id"] == rail_id:
            return rail.get("type", DEFAULT_RAIL_TYPE), int(rail.get("label", 0)), int(
                rail.get("page_size", DEFAULT_SEARCH_PAGE_SIZE)
            )
    return DEFAULT_RAIL_TYPE, 0, DEFAULT_SEARCH_PAGE_SIZE


def _addon() -> object:
    return xbmcaddon.Addon()


def _bool_setting(addon: object, key: str, default: bool) -> bool:
    try:
        return addon.getSettingBool(key)
    except Exception:
        try:
            return str(addon.getSetting(key)).lower() == "true"
        except Exception:
            return default


def _int_setting(addon: object, key: str, default: int) -> int:
    try:
        return addon.getSettingInt(key)
    except Exception:
        try:
            return int(addon.getSetting(key))
        except Exception:
            return default


def _build_listitem(video: Dict[str, object]) -> xbmcgui.ListItem:
    label = str(video.get("title", ""))
    listitem = xbmcgui.ListItem(label)
    art = video.get("art")
    if isinstance(art, dict):
        listitem.setArt(art)
    info = video.get("info")
    if isinstance(info, dict):
        listitem.setInfo("video", info)
    if video.get("is_playable", True):
        listitem.setProperty("IsPlayable", "true")
    return listitem


@timed("listing.show_list")
def show_list(context, rail_id: str, cursor: Optional[str]) -> None:
    ensure_ready_or_raise()
    addon = _addon()
    backend = get_backend()
    rail_type, label_id, page_size = _rail_meta(rail_id)
    xbmcplugin.setContent(context.handle, rail_type)

    ttl = _int_setting(addon, "cache_ttl", 300)
    use_cache = _bool_setting(addon, "use_cache", True)

    start = time.perf_counter()
    try:
        data, from_cache = backend.get_rail(rail_id, cursor, page_size, ttl, use_cache)
    except BackendError as exc:
        _show_notification(addon, str(exc))
        return
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    log_duration(
        f"rail:{rail_id}",
        elapsed_ms,
        warm=from_cache,
        warm_threshold_ms=WARM_THRESHOLD_MS,
        cold_threshold_ms=COLD_THRESHOLD_MS,
    )

    items = []
    for video in data.items:
        listitem = _build_listitem(video)
        url = context.build_url(action="play", asin=str(video.get("asin", "")))
        items.append((url, listitem, False))

    if data.cursor:
        more_label = addon.getLocalizedString(30021)
        listitem = xbmcgui.ListItem(more_label)
        listitem.setProperty("IsPlayable", "false")
        url = context.build_url(action="list", rail=rail_id, cursor=data.cursor)
        items.append((url, listitem, True))

    if hasattr(xbmcplugin, "addDirectoryItems"):
        xbmcplugin.addDirectoryItems(context.handle, items)
    else:  # pragma: no cover - stub fallback
        for url, listitem, isFolder in items:
            xbmcplugin.addDirectoryItem(context.handle, url, listitem, isFolder=isFolder)


@timed("listing.show_search")
def show_search(context, query: Optional[str], cursor: Optional[str]) -> None:
    ensure_ready_or_raise()
    addon = _addon()
    backend = get_backend()
    if not query:
        dialog = xbmcgui.Dialog()
        query = dialog.input(addon.getLocalizedString(30030))  # type: ignore[attr-defined]
    if not query:
        return

    xbmcplugin.setContent(context.handle, DEFAULT_RAIL_TYPE)
    ttl = _int_setting(addon, "cache_ttl", 300)
    use_cache = _bool_setting(addon, "use_cache", True)

    start = time.perf_counter()
    try:
        data, from_cache = backend.search(query, cursor, DEFAULT_SEARCH_PAGE_SIZE, ttl, use_cache)
    except BackendError as exc:
        _show_notification(addon, str(exc))
        return
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    log_duration(
        f"search:{query}",
        elapsed_ms,
        warm=from_cache,
        warm_threshold_ms=WARM_THRESHOLD_MS,
        cold_threshold_ms=COLD_THRESHOLD_MS,
    )

    items = []
    for video in data.items:
        listitem = _build_listitem(video)
        url = context.build_url(action="play", asin=str(video.get("asin", "")))
        items.append((url, listitem, False))

    if not items:
        listitem = xbmcgui.ListItem(addon.getLocalizedString(30031))
        items.append((context.build_url(), listitem, False))

    if data.cursor:
        more_label = addon.getLocalizedString(30021)
        listitem = xbmcgui.ListItem(more_label)
        listitem.setProperty("IsPlayable", "false")
        url = context.build_url(action="search", query=query, cursor=data.cursor)
        items.append((url, listitem, True))

    if hasattr(xbmcplugin, "addDirectoryItems"):
        xbmcplugin.addDirectoryItems(context.handle, items)
    else:  # pragma: no cover - stub fallback
        for url, listitem, isFolder in items:
            xbmcplugin.addDirectoryItem(context.handle, url, listitem, isFolder=isFolder)


def _show_notification(addon: object, message: str) -> None:
    try:
        dialog = xbmcgui.Dialog()
        dialog.notification(addon.getAddonInfo("name"), message)  # type: ignore[attr-defined]
    except Exception:
        pass
