"""Home view building the Netflix-style rail list for PrimeFlix.

Called from :mod:`resources.lib.router` when no action is provided. Produces a
set of rail directories that route into :func:`resources.lib.ui.listing.show_list`
and a search entry.
"""
from __future__ import annotations

from typing import List, Tuple

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

from ..perf import timed
from ..preflight import ensure_ready_or_raise
from .listing import RAIL_DEFINITIONS

HOME_CONTENT_TYPE = "videos"


@timed("home_build", warn_threshold_ms=1500.0)
def show_home(context) -> None:
    ensure_ready_or_raise()
    addon = xbmcaddon.Addon()
    xbmcplugin.setContent(context.handle, HOME_CONTENT_TYPE)

    items: List[Tuple[str, xbmcgui.ListItem, bool]] = []
    for rail in RAIL_DEFINITIONS:
        label_id = int(rail.get("label", 0))
        label = addon.getLocalizedString(label_id) if label_id else str(rail.get("id", ""))
        listitem = xbmcgui.ListItem(label)
        url = context.build_url(action="list", rail=str(rail.get("id", "")))
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
