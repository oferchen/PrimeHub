"""Rail listing and search UI handlers."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
try:
    import xbmcgui
    import xbmcplugin
    import xbmcaddon
except ImportError:
    from ...tests.kodi_mocks import xbmcgui, xbmcplugin, xbmcaddon

from ..backend.prime_api import PrimeVideo
from ..preflight import PreflightError

def show_list(context, pv: PrimeVideo, rail_id: str) -> None:
    """Shows the items for a single rail."""
    try:
        items, next_page = pv.Browse(rail_id)
        _render_items(context, items, next_page)
    except Exception as e:
        xbmcgui.Dialog().notification("Error", f"Could not load content: {e}")

def show_search(context, pv: PrimeVideo, query: Optional[str]) -> None:
    """Handles search."""
    if not query:
        query = xbmcgui.Dialog().input("Search")
    if query:
        items, _ = pv.Search(query)
        _render_items(context, items)

def _render_items(context, items: List[Dict], next_page: Optional[str] = None):
    """Renders a list of items and sets the view to a poster layout."""
    try:
        import xbmc
    except ImportError:
        from ...tests.kodi_mocks import xbmc

    # Set the content type to "videos" to enable library-like features
    xbmcplugin.setContent(context.handle, "videos")

    list_items = []
    for item in items:
        li = xbmcgui.ListItem(label=item.get("title", ""))
        # Set the plot and other metadata
        li.setInfo("video", {
            "title": item.get("title", ""),
            "plot": item.get("plot", ""),
            "mediatype": "video" # Generic video type
        })
        # Set the artwork
        art = item.get("art", {})
        li.setArt({
            "poster": art.get("poster"),
            "fanart": art.get("fanart"),
            "icon": art.get("poster") # Use poster for icon as well
        })
        # Mark the item as playable
        li.setProperty("IsPlayable", "true")
        url = context.build_url(action="play", asin=item.get("asin"))
        list_items.append((url, li, False))

    if next_page:
        next_li = xbmcgui.ListItem(label="Next Page...")
        next_url = context.build_url(action="list", rail_id=next_page)
        list_items.append((next_url, next_li, True))

    xbmcplugin.addDirectoryItems(context.handle, list_items, len(list_items))
    
    # Set the view mode to a poster/wall view. 500 is a common ID for "Wall".
    xbmc.executebuiltin('Container.SetViewMode(500)')