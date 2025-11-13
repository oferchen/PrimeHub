from __future__ import annotations

import sys
import urllib.parse
from typing import Dict, List, Optional

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
from ..backend import prime_api
from . import home

SEARCH_TTL = 60


def show_list(handle: int, rail_id: str | None, page: int) -> None:
    if not rail_id:
        return
    backend = prime_api.get_backend()
    if not backend:
        return
    addon = xbmcaddon.Addon() if xbmcaddon else None
    use_cache = home._get_setting_bool(addon, "use_cache", True)  # type: ignore[attr-defined]
    cache_ttl = home._get_setting_int(addon, "cache_ttl", home.DEFAULT_CACHE_TTL)  # type: ignore[attr-defined]

    items, has_more, from_cache = home.get_rail_page(rail_id, page, use_cache, cache_ttl)
    _log_fetch(rail_id, page, from_cache)

    if xbmcplugin:
        xbmcplugin.setContent(handle, _content_type(items))

    for item in items:
        _add_item(handle, item)

    if has_more:
        _add_more_item(handle, rail_id, page)


def start_search(handle: int, params: Optional[Dict[str, str]]) -> None:
    query = params.get("query") if params else None
    page = int(params.get("page", "1")) if params and params.get("page") else 1
    if not query:
        if not xbmcgui:
            return
        query = xbmcgui.Dialog().input("Prime Video")
        if not query:
            return
        page = 1
    _show_search_results(handle, query, page)


def _show_search_results(handle: int, query: str, page: int) -> None:
    backend = prime_api.get_backend()
    if not backend:
        return
    cache_key = f"search:{query}:{page}"
    cached = cache.get(cache_key)
    if cached:
        items, has_more = cached.get("items", []), bool(cached.get("has_more"))
        from_cache = True
    else:
        def fetch():
            return backend.search(query, page)

        items, has_more = measure(f"search:{page}", fetch, 500)
        cache.set(cache_key, {"items": items, "has_more": has_more}, ttl_seconds=SEARCH_TTL)
        from_cache = False
    _log_fetch(f"search:{query}", page, from_cache)

    if xbmcplugin:
        xbmcplugin.setPluginCategory(handle, f"Search: {query}")
        xbmcplugin.setContent(handle, _content_type(items))

    for item in items:
        _add_item(handle, item)

    if has_more:
        params = {"action": "search", "query": query, "page": page + 1}
        url = f"{sys.argv[0]}?{urllib.parse.urlencode(params)}"
        label = f"More results ({page + 1})"
        listitem = xbmcgui.ListItem(label=label) if xbmcgui else None
        if xbmcplugin and listitem:
            xbmcplugin.addDirectoryItem(handle, url, listitem, isFolder=True)


def _add_item(handle: int, item: Dict) -> None:
    if not xbmcgui or not xbmcplugin:
        return
    label = item.get("title") or item.get("name")
    listitem = xbmcgui.ListItem(label=label)
    art = item.get("art") or {}
    if art:
        listitem.setArt({k: v for k, v in art.items() if v})
    info = item.get("info") or {}
    info.setdefault("title", label)
    media_type = item.get("type") or info.get("mediatype")
    if media_type:
        info.setdefault("mediatype", media_type)
    listitem.setInfo("video", info)

    if item.get("is_folder"):
        params = {"action": "list", "rail": item.get("params", {}).get("rail", item.get("asin"))}
        url = f"{sys.argv[0]}?{urllib.parse.urlencode(params)}"
        xbmcplugin.addDirectoryItem(handle, url, listitem, isFolder=True)
    else:
        asin = item.get("asin")
        if asin:
            params = {"action": "play", "asin": asin}
            url = f"{sys.argv[0]}?{urllib.parse.urlencode(params)}"
            listitem.setProperty("IsPlayable", "true")
            xbmcplugin.addDirectoryItem(handle, url, listitem, isFolder=False)


def _add_more_item(handle: int, rail_id: str, page: int) -> None:
    if not xbmcgui or not xbmcplugin:
        return
    params = {"action": "list", "rail": rail_id, "page": page + 1}
    url = f"{sys.argv[0]}?{urllib.parse.urlencode(params)}"
    label = f"More… ({page + 1})"
    listitem = xbmcgui.ListItem(label=label)
    xbmcplugin.addDirectoryItem(handle, url, listitem, isFolder=True)


def _content_type(items: List[Dict]) -> str:
    if not items:
        return "videos"
    types = {item.get("type") for item in items if item.get("type")}
    if types == {"movie"}:
        return "movies"
    if types == {"episode"} or types == {"tvshow"}:
        return "tvshows"
    return "videos"


def _log_fetch(identifier: str, page: int, from_cache: bool) -> None:
    source = "cache" if from_cache else "backend"
    level = xbmc.LOGINFO if xbmc else 1  # type: ignore[attr-defined]
    if xbmc:
        xbmc.log(f"[PrimeFlix] Rail {identifier} page {page} served from {source}", level)
    else:  # pragma: no cover - development fallback
        print(f"[PrimeFlix] Rail {identifier} page {page} served from {source}")
