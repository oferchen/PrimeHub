from __future__ import annotations

import sys
import time
import urllib.parse
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - development fallback
    xbmc = None
    xbmcaddon = None
    xbmcgui = None
    xbmcplugin = None

from .. import cache
from ..perf import measure
from ..preflight import PreflightError, run
from ..backend import prime_api

HOME_WARN_COLD_MS = 1500
HOME_WARN_WARM_MS = 300
RAIL_WARN_COLD_MS = 500
RAIL_WARN_WARM_MS = 150
DEFAULT_CACHE_TTL = 300

HOME_RAILS = [
    ("continue", 32000),
    ("prime", 32001),
    ("movie", 32002),
    ("tv", 32003),
    ("recommend", 32004)
]


def show_home(handle: int) -> None:
    start = time.perf_counter()
    try:
        run()
    except PreflightError as exc:
        _log(f"[PrimeFlix] Preflight failed: {exc}", level=xbmc.LOGERROR if xbmc else 4)  # type: ignore[attr-defined]
        return

    backend = prime_api.get_backend()
    if not backend:
        _log("[PrimeFlix] Backend unavailable", level=xbmc.LOGERROR if xbmc else 4)  # type: ignore[attr-defined]
        return

    addon = xbmcaddon.Addon() if xbmcaddon else None
    preferred_region = _get_setting(addon, "preferred_region", "us")
    backend_region = backend.get_region()
    if backend_region and preferred_region and backend_region.lower() != preferred_region.lower():
        _log(f"[PrimeFlix] Preferred region={preferred_region}, backend region={backend_region} — using backend.")

    use_cache = _get_setting_bool(addon, "use_cache", True)
    cache_ttl = _get_setting_int(addon, "cache_ttl", DEFAULT_CACHE_TTL)

    def _build():
        return build_home_snapshot(addon, backend, use_cache, cache_ttl)

    rail_results, warm_flags = measure("home", _build)

    if xbmcplugin:
        xbmcplugin.setContent(handle, "videos")

    for rail_id, title, items, has_more, _ in rail_results:
        _add_rail_entry(handle, rail_id, title, items, has_more)

    _add_search_entry(handle, addon)
    _add_diagnostics_entry(handle, addon)

    total_ms = (time.perf_counter() - start) * 1000.0
    threshold = HOME_WARN_WARM_MS if all(warm_flags) and warm_flags else HOME_WARN_COLD_MS
    if total_ms > threshold:
        _log(f"[PrimeFlix] WARNING home build took {total_ms:.1f} ms", level=xbmc.LOGWARNING if xbmc else 2)  # type: ignore[attr-defined]
    else:
        _log(f"[PrimeFlix] Home build finished in {total_ms:.1f} ms")


def _select_rails(rails, addon) -> List[Tuple[str, str]]:
    localized = {token: _localize(addon, label_id) for token, label_id in HOME_RAILS}
    selected: List[Tuple[str, str]] = []
    used: set[str] = set()
    for token, label_id in HOME_RAILS:
        match = _match_rail(rails, token, used)
        if match:
            used.add(match.identifier)
            title = localized.get(token) or match.title
            selected.append((match.identifier, title))
    return selected


def _match_rail(rails, token: str, used: Iterable[str]):
    lower_token = token.lower()
    for rail in rails:
        if rail.identifier in used:
            continue
        identifier = (rail.identifier or "").lower()
        title = (rail.title or "").lower()
        if lower_token in identifier or lower_token in title:
            return rail
    for rail in rails:
        if rail.identifier in used:
            continue
        return rail
    return None


def _get_or_fetch_rail_page(backend, rail_id: str, cache_ttl: int, use_cache: bool) -> Tuple[List[Dict], bool, bool]:
    cache_key = f"rail:{rail_id}:page:1"
    cached = cache.get(cache_key) if use_cache else None
    if cached:
        def from_cache():
            return cached.get("items", []), bool(cached.get("has_more"))

        items, has_more = measure(f"rail:{rail_id}:cache", from_cache, RAIL_WARN_WARM_MS)
        return items, has_more, True

    def fetch():
        return backend.get_rail_items(rail_id, page=1)

    items, has_more = measure(f"rail:{rail_id}", fetch, RAIL_WARN_COLD_MS)
    if use_cache:
        cache.set(cache_key, {"items": items, "has_more": has_more}, ttl_seconds=cache_ttl)
    return items, has_more, False


def _add_rail_entry(handle: int, rail_id: str, title: str, items: List[Dict], has_more: bool) -> None:
    if not xbmcgui or not xbmcplugin:
        return
    listitem = xbmcgui.ListItem(label=title)
    art = _rail_art(items)
    if art:
        listitem.setArt(art)
    listitem.setInfo("video", {"title": title})
    params = {"action": "list", "rail": rail_id}
    url = f"{sys.argv[0]}?{urllib.parse.urlencode(params)}"
    xbmcplugin.addDirectoryItem(handle, url, listitem, isFolder=True)


def _rail_art(items: List[Dict]) -> Dict[str, str]:
    if not items:
        return {}
    for item in items:
        art = item.get("art")
        if art:
            return {k: v for k, v in art.items() if v}
    return {}


def _add_search_entry(handle: int, addon) -> None:
    if not xbmcgui or not xbmcplugin:
        return
    label = _localize(addon, 32005) or "Search"
    listitem = xbmcgui.ListItem(label=label)
    listitem.setArt({"icon": "DefaultAddonsSearch.png"})
    url = f"{sys.argv[0]}?action=search"
    xbmcplugin.addDirectoryItem(handle, url, listitem, isFolder=True)


def _add_diagnostics_entry(handle: int, addon) -> None:
    if not xbmcgui or not xbmcplugin:
        return
    label = _localize(addon, 32006) or "Diagnostics"
    listitem = xbmcgui.ListItem(label=label)
    listitem.setArt({"icon": "DefaultAddonNone.png"})
    url = f"{sys.argv[0]}?action=diagnostics"
    xbmcplugin.addDirectoryItem(handle, url, listitem, isFolder=True)


def _localize(addon, string_id: int) -> Optional[str]:
    if not addon:
        return None
    return addon.getLocalizedString(string_id)


def _get_setting(addon, setting_id: str, fallback: str) -> str:
    if not addon:
        return fallback
    try:
        return addon.getSetting(setting_id)
    except Exception:
        return fallback


def _get_setting_bool(addon, setting_id: str, fallback: bool) -> bool:
    if not addon:
        return fallback
    if hasattr(addon, "getSettingBool"):
        return addon.getSettingBool(setting_id)
    return addon.getSetting(setting_id).lower() == "true"


def _get_setting_int(addon, setting_id: str, fallback: int) -> int:
    if not addon:
        return fallback
    if hasattr(addon, "getSettingInt"):
        return addon.getSettingInt(setting_id)
    try:
        return int(addon.getSetting(setting_id))
    except (TypeError, ValueError):
        return fallback


def _log(message: str, level: int = xbmc.LOGINFO if xbmc else 1) -> None:  # type: ignore[attr-defined]
    if xbmc:
        xbmc.log(message, level)
    else:  # pragma: no cover - development fallback
        print(f"[xbmc][{level}] {message}")


def get_rail_page(rail_id: str, page: int, use_cache: bool, cache_ttl: int):
    backend = prime_api.get_backend()
    if not backend:
        raise RuntimeError("Prime backend unavailable")
    cache_key = f"rail:{rail_id}:page:{page}"
    cached = cache.get(cache_key) if use_cache else None
    if cached:
        def from_cache():
            return cached.get("items", []), bool(cached.get("has_more"))

        items, has_more = measure(f"rail:{rail_id}:page:{page}:cache", from_cache, RAIL_WARN_WARM_MS)
        return items, has_more, True

    def fetch():
        return backend.get_rail_items(rail_id, page=page)

    items, has_more = measure(f"rail:{rail_id}:page:{page}", fetch, RAIL_WARN_COLD_MS if page == 1 else None)
    if use_cache:
        cache.set(cache_key, {"items": items, "has_more": has_more}, ttl_seconds=cache_ttl)
    return items, has_more, False


def build_home_snapshot(addon, backend, use_cache: bool, cache_ttl: int):
    rails = backend.get_home_rails()
    selected = _select_rails(rails, addon)
    results = []
    warm_flags: List[bool] = []
    for rail_id, title in selected:
        items, has_more, from_cache = _get_or_fetch_rail_page(backend, rail_id, cache_ttl, use_cache)
        warm_flags.append(from_cache)
        results.append((rail_id, title, items, has_more, from_cache))
    return results, warm_flags
