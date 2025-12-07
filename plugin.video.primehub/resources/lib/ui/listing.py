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
    # ... (implementation to create and add ListItems)
    pass