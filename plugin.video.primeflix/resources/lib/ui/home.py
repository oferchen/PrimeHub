"""Home view building the Netflix-style rail list for PrimeFlix.

Called from :mod:`resources.lib.router` when no action is provided. Produces a
set of rail directories that route into :func:`resources.lib.ui.listing.show_list`
and a search entry.
"""
from __future__ import annotations

import time
from typing import Dict, List, Tuple

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

        def getLabel(self) -> str:
            return self._label

        def setArt(self, art):
            pass

        def setInfo(self, info_type, info):
            pass

    class _AddonStub:
        @staticmethod
        def getLocalizedString(code: int) -> str:
            return str(code)

    xbmcplugin = _PluginStub()  # type: ignore
    xbmcgui = type("gui", (), {"ListItem": _ListItemStub})  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": lambda *args, **kwargs: _AddonStub()})  # type: ignore

from ..backend.prime_api import BackendError, HOME_COLD_THRESHOLD_MS, HOME_WARM_THRESHOLD_MS, get_backend
from ..perf import log_duration, timed
from ..preflight import ensure_ready_or_raise
from .listing import RAIL_DEFINITIONS

HOME_CONTENT_TYPE = "videos"
_RAIL_LABEL_MAP: Dict[str, int] = {str(item["id"]): int(item.get("label", 0)) for item in RAIL_DEFINITIONS}


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


@timed("home_build", warn_threshold_ms=HOME_COLD_THRESHOLD_MS)
def show_home(context) -> None:
    ensure_ready_or_raise()
    addon = xbmcaddon.Addon()
    backend = get_backend()
    xbmcplugin.setContent(context.handle, HOME_CONTENT_TYPE)

    ttl = _int_setting(addon, "cache_ttl", 300)
    use_cache = _bool_setting(addon, "use_cache", True)

    start = time.perf_counter()
    try:
        rails, from_cache = backend.get_home_rails(ttl, use_cache)
    except BackendError as exc:
        _notify(addon, str(exc))
        return
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    log_duration(
        "home",
        elapsed_ms,
        warm=from_cache,
        warm_threshold_ms=HOME_WARM_THRESHOLD_MS,
        cold_threshold_ms=HOME_COLD_THRESHOLD_MS,
    )

    items: List[Tuple[str, xbmcgui.ListItem, bool]] = []
    for rail in rails:
        rail_id = str(rail.get("id", ""))
        label = str(rail.get("title") or _label_for(addon, rail_id))
        listitem = xbmcgui.ListItem(label)
        url = context.build_url(action="list", rail=rail_id)
        items.append((url, listitem, True))

    search_label = addon.getLocalizedString(30020)
    search_item = xbmcgui.ListItem(search_label)
    search_url = context.build_url(action="search")
    items.append((search_url, search_item, True))

    if hasattr(xbmcplugin, "addDirectoryItems"):
        xbmcplugin.addDirectoryItems(context.handle, items)
    else:  # pragma: no cover - stub fallback
        for url, listitem, isFolder in items:
            xbmcplugin.addDirectoryItem(context.handle, url, listitem, isFolder=isFolder)


def _label_for(addon: object, rail_id: str) -> str:
    label_id = _RAIL_LABEL_MAP.get(rail_id)
    if label_id:
        label = addon.getLocalizedString(label_id)
        if label:
            return label
    return rail_id


def _notify(addon: object, message: str) -> None:
    try:
        dialog = xbmcgui.Dialog()
        dialog.notification(addon.getAddonInfo("name"), message)  # type: ignore[attr-defined]
    except Exception:
        pass
