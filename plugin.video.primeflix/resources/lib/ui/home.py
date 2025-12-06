"""Home route building Netflix-style rails for PrimeHub."""
from __future__ import annotations
from typing import Any, Dict, List
try:
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:
    from ...tests.kodi_mocks import xbmcaddon, xbmcgui, xbmcplugin

from ..common import Globals, Settings
from ..backend.prime_api import PrimeVideo
from ..perf import timed
from ..preflight import ensure_ready_or_raise

def show_home(context, pv: PrimeVideo) -> None:
    """Build and display PrimeHub home with Netflix-style rails."""
    ensure_ready_or_raise()
    g = Globals()
    
    xbmcplugin.setContent(context.handle, "videos")
    
    # pv.Browse returns a tuple of (items, next_page_cursor)
    rails, _ = pv.Browse('root')
    
    list_items = []
    for rail in rails:
        li = xbmcgui.ListItem(label=rail.get("title", ""))
        li.setArt({"icon": "DefaultFolder.png", "fanart": g.DefaultFanart})
        url = context.build_url(action="list", rail_id=rail.get("lazyLoadURL"))
        list_items.append((url, li, True))

    # Add static items
    search_li = xbmcgui.ListItem(label="Search")
    search_li.setArt({"icon": "DefaultAddonSearch.png", "fanart": g.DefaultFanart})
    list_items.append((context.build_url(action="search"), search_li, True))

    xbmcplugin.addDirectoryItems(context.handle, list_items)