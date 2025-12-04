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
    from ...tests.kodi_mocks import MockXBMCAddon as xbmcaddon
    from ...tests.kodi_mocks import MockXBMCGUI as xbmcgui
    from ...tests.kodi_mocks import MockXBMCPlugin as xbmcplugin

from ..backend.prime_api import BackendError, BackendUnavailable, get_backend
from ..cache import Cache, get_cache
from ..perf import timed
from ..preflight import PreflightError, ensure_ready_or_raise


async def fetch_home_rails(
    addon: xbmcaddon.Addon, cache: Cache
) -> List[Dict[str, Any]]:
    """Fetch home rails from cache or backend, mapping to Netflix-style categories."""
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

    raw_rails: List[Dict[str, Any]]
    try:
        backend = get_backend()
        raw_rails = await backend.get_home_rails()
    except (BackendError, BackendUnavailable):
        # Fallback for when the native backend fails to return rails
        raw_rails = [
            {"id": "login", "title": "Login Required", "plugin_url": "plugin://plugin.video.primeflix/?action=login"},
        ]
        if use_cache:
            cache.set(cache_key, raw_rails, ttl_seconds=cache_ttl)
        return raw_rails

    # Map raw rails to desired Netflix-style categories
    mapped_rails: List[Dict[str, Any]] = []
    found_raw_rails = {rail["id"]: rail for rail in raw_rails}

    # Define desired categories with localized titles
    DESIRED_RAIL_CATEGORIES = [
        {
            "id": "continue_watching",
            "title_id": 40000,
            "default_title": "Continue Watching",
        },
        {
            "id": "prime_originals",
            "title_id": 40001,
            "default_title": "Prime Originals",
        },
        {"id": "movies", "title_id": 40002, "default_title": "Movies"},
        {"id": "tv", "title_id": 40003, "default_title": "TV"},
        {
            "id": "recommended_for_you",
            "title_id": 40004,
            "default_title": "Recommended For You",
        },
    ]

    for category in DESIRED_RAIL_CATEGORIES:
        localized_title = (
            addon.getLocalizedString(category["title_id"]) or category["default_title"]
        )
        if category["id"] in found_raw_rails:
            rail = found_raw_rails[category["id"]]
            mapped_rails.append(
                {
                    "id": rail["id"],
                    "title": rail.get(
                        "title", localized_title
                    ),  # Prefer backend title if available
                    "type": rail.get("type", "mixed"),
                    "path": rail.get("path", ""),
                }
            )
        else:
            mapped_rails.append(
                {
                    "id": category["id"],
                    "title": localized_title,
                    "type": "mixed",  # Default type for placeholder
                    "path": "",  # Placeholder path
                }
            )

    # Only display the desired rails in the specified order.
    # Unmapped rails from the backend will be ignored.
    if use_cache:
        cache.set(cache_key, mapped_rails, ttl_seconds=cache_ttl)
    return mapped_rails


@timed("home_build")
async def show_home(context) -> None:
    """Build and display PrimeHub home with Netflix-style rails."""
    ensure_ready_or_raise()
    addon = xbmcaddon.Addon()
    cache = get_cache()

    xbmcplugin.setContent(context.handle, "videos")

    rails = await fetch_home_rails(addon, cache)
    addon_fanart = addon.getAddonInfo("fanart")

    list_items = []
    for rail in rails:
        li = xbmcgui.ListItem(label=rail.get("title", ""))
        li.setInfo(
            "video",
            {
                "title": rail.get("title", ""),
                "plot": f"Browse {rail.get('title', 'content')}",
            },
        )
        li.setArt({"icon": "DefaultFolder.png", "fanart": addon_fanart})

        if "plugin_url" in rail:
            url = rail["plugin_url"]
        else:
            url = context.build_url(action="list", rail=rail.get("id"))
        list_items.append((url, li, True))

    search_li = xbmcgui.ListItem(label=addon.getLocalizedString(30000))
    search_li.setArt({"icon": "DefaultAddonSearch.png", "fanart": addon_fanart})
    search_url = context.build_url(action="search")
    list_items.append((search_url, search_li, True))

    diag_li = xbmcgui.ListItem(label=addon.getLocalizedString(30020))
    diag_li.setArt({"icon": "DefaultAddonSettings.png", "fanart": addon_fanart})
    diag_url = context.build_url(action="diagnostics")
    list_items.append((diag_url, diag_li, True))

    logout_li = xbmcgui.ListItem(label=addon.getLocalizedString(32007))
    logout_li.setArt({"icon": "DefaultFolder.png", "fanart": addon_fanart}) # Or a specific logout icon
    logout_url = context.build_url(action="logout")
    list_items.append((logout_url, logout_li, True))

    xbmcplugin.addDirectoryItems(context.handle, list_items)
