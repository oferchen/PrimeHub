"""Home route building Netflix-style rails for PrimeHub.

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
            return "PrimeHub"

        def getLocalizedString(self, code: int) -> str:
            return ""

    xbmcgui = type("xbmcgui", (), {"ListItem": _ListItem})  # type: ignore
    xbmcplugin = _XBMCPlugin()  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": lambda *a, **k: _Addon()})  # type: ignore

from ..backend import BackendError, BackendUnavailable, get_backend
from ..cache import Cache, get_cache
from ..perf import timed
from ..preflight import PreflightError, ensure_ready_or_raise


def fetch_home_rails(addon: xbmcaddon.Addon, cache: Cache, backend_id: str) -> List[Dict[str, Any]]:
    """Fetch home rails from cache or backend."""
    cache_key = "home:rails"
    try:
        use_cache = addon.getSettingBool("use_cache")
        cache_ttl = addon.getSettingInt("cache_ttl")
    except Exception:
        use_cache = True
        cache_ttl = 300

    if use_cache:
        cached = cache.get(cache_key, ttl_seconds=cache_ttl)
        if cached:
            return cached

    backend = get_backend(backend_id)
    try:
        rails = backend.get_home_rails()
        if use_cache:
            cache.set(cache_key, rails, ttl_seconds=cache_ttl)
        return rails
    except (BackendError, BackendUnavailable):
        amazon_addon_id = backend.backend_id
        return [
            {"id": "watchlist", "title": "My Watchlist", "plugin_url": f"plugin://{amazon_addon_id}/?mode=Watchlist"},
            {"id": "browse", "title": "Browse All", "plugin_url": f"plugin://{amazon_addon_id}/"},
        ]


@timed("home_build")
def show_home(context) -> None:
    """Build and display PrimeHub home with Netflix-style rails."""
    backend_id = ensure_ready_or_raise()
    addon = xbmcaddon.Addon()
    cache = get_cache()

    xbmcplugin.setContent(context.handle, "videos")

    rails = fetch_home_rails(addon, cache, backend_id)
    addon_fanart = addon.getAddonInfo('fanart')

    list_items = []
    for rail in rails:
        li = xbmcgui.ListItem(label=rail.get("title", ""))
        li.setInfo("video", {"title": rail.get("title", ""), "plot": f"Browse {rail.get('title', 'content')}"})
        li.setArt({'icon': 'DefaultFolder.png', 'fanart': addon_fanart})

        if "plugin_url" in rail:
            url = rail["plugin_url"]
        else:
            url = context.build_url(action="list", rail=rail.get("id"))
        list_items.append((url, li, True))

    search_li = xbmcgui.ListItem(label=addon.getLocalizedString(30000))
    search_li.setArt({'icon': 'DefaultAddonSearch.png', 'fanart': addon_fanart})
    search_url = context.build_url(action="search")
    list_items.append((search_url, search_li, True))

    diag_li = xbmcgui.ListItem(label=addon.getLocalizedString(30020))
    diag_li.setArt({'icon': 'DefaultAddonSettings.png', 'fanart': addon_fanart})
    diag_url = context.build_url(action="diagnostics")
    list_items.append((diag_url, diag_li, True))

    xbmcplugin.addDirectoryItems(context.handle, list_items)
