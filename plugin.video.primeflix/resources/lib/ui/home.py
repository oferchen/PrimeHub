"""Home route building Netflix-style rails for PrimeFlix.

Called from :mod:`resources.lib.router` and responsible for building the root
listing quickly using cached backend data when available.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:  # pragma: no cover - Kodi runtime
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    class _ListItem:
        def __init__(self, label=""):
            self.label = label

        def setArt(self, art: Dict[str, str]):
            self.art = art

        def setInfo(self, type_: str, info: Dict[str, Any]):
            self.info = (type_, info)

    class _XBMCPlugin:
        SORT_METHOD_UNSORTED = 0

        @staticmethod
        def addDirectoryItems(handle, items):
            print(f"ADD {len(items)} items")

        @staticmethod
        def setContent(handle, content):
            print(f"SET CONTENT {content}")

    class _Addon:
        def getSettingBool(self, key: str) -> bool:
            return False

        def getSettingInt(self, key: str) -> int:
            return 300

        def getAddonInfo(self, key: str) -> str:
            return "PrimeFlix"

        def getLocalizedString(self, code: int) -> str:
            return ""

    xbmcgui = type("xbmcgui", (), {"ListItem": _ListItem})  # type: ignore
    xbmcplugin = _XBMCPlugin()  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": lambda *a, **k: _Addon()})  # type: ignore

from ..backend import BackendError, BackendUnavailable, get_backend
from ..cache import get_cache
from ..perf import timed
from ..preflight import PreflightError, ensure_ready_or_raise

DEFAULT_CACHE_TTL = 300


def _get_setting_bool(addon, key: str, default: bool) -> bool:
    try:
        return addon.getSettingBool(key)
    except Exception:
        try:
            return str(addon.getSetting(key)).lower() == "true"
        except Exception:
            return default


def _get_setting_int(addon, key: str, default: int) -> int:
    try:
        return int(addon.getSettingInt(key))
    except Exception:
        try:
            return int(addon.getSetting(key))
        except Exception:
            return default


@timed("home_build")
def show_home(context) -> None:
    backend_id = ensure_ready_or_raise()
    addon = xbmcaddon.Addon()
    cache = get_cache()
    rails = fetch_home_rails(addon, cache, backend_id)
    search_label = _safe_get_string(addon, 30000, "Search")
    _build_directory(context, rails, search_label)


def fetch_home_rails(addon, cache, backend_id: str) -> List[Dict[str, Any]]:
    use_cache = _get_setting_bool(addon, "use_cache", True)
    cache_ttl = _get_setting_int(addon, "cache_ttl", DEFAULT_CACHE_TTL)

    rails: Optional[List[Dict[str, Any]]] = None
    cache_key = "home_rails"
    if use_cache:
        rails = cache.get(cache_key, ttl_seconds=cache_ttl)

    if rails is None:
        backend = get_backend(backend_id)
        try:
            rails = backend.get_home_rails()
            if use_cache:
                cache.set(cache_key, rails, cache_ttl)
        except (BackendUnavailable, BackendError) as exc:
            raise PreflightError(str(exc))

    return rails or []


def _build_directory(context, rails: List[Dict[str, Any]], search_label: str) -> None:
    xbmcplugin.setContent(context.handle, "videos")
    items = []
    for rail in rails:
        url = context.build_url(action="list", rail=rail.get("id", ""))
        li = xbmcgui.ListItem(label=rail.get("title", ""))
        li.setInfo(
            "video",
            {
                "title": rail.get("title", ""),
                "plot": rail.get("title", ""),
            },
        )
        items.append((url, li, True))

    # Search shortcut always last
    search_url = context.build_url(action="search")
    search_item = xbmcgui.ListItem(label=search_label)
    search_item.setInfo("video", {"title": search_label})
    items.append((search_url, search_item, True))

    xbmcplugin.addDirectoryItems(context.handle, items)


def _safe_get_string(addon, code: int, fallback: str) -> str:
    try:
        value = addon.getLocalizedString(code)
        return value or fallback
    except Exception:
        return fallback

