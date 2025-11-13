"""Listing screens for PrimeFlix rails and search."""
from __future__ import annotations

from typing import Optional

try:  # pragma: no cover - Kodi runtime
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    class _Addon:
        def getLocalizedString(self, code: int) -> str:
            return str(code)

    class _GUI:
        class Dialog:
            @staticmethod
            def input(title: str) -> str:
                return ""

        class ListItem:
            def __init__(self, label: str = ""):
                self.label = label

            def setArt(self, art):
                pass

            def setInfo(self, info_type, info_labels):
                pass

            def setProperty(self, key, value):
                pass

    class _Plugin:
        @staticmethod
        def addDirectoryItems(handle, items):
            for url, listitem, folder in items:
                print(f"ADD {url} ({'folder' if folder else 'item'})")

        @staticmethod
        def addDirectoryItem(handle, url, listitem, isFolder=False):
            print(f"ADD {url}")

        @staticmethod
        def setContent(handle, content):
            print(f"SET CONTENT {content}")

    xbmcaddon = type("addon", (), {"Addon": _Addon})  # type: ignore
    xbmcgui = _GUI  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore

from ..backend.prime_api import get_backend
from ..router import PluginContext
from . import home


def show_list(context: PluginContext, rail_id: str, cursor: Optional[str]) -> None:
    addon = xbmcaddon.Addon()
    xbmcplugin.setContent(context.handle, rail.content_type)
    backend = get_backend()
    rail = next((r for r in home.HOME_RAILS if r.identifier == rail_id), None)
    if rail is None:
        rail = home.RailDefinition(rail_id, 20020, "videos")
    page = backend.fetch_rail(rail_id, limit=rail.limit, cursor=cursor)
    items = [_build_video_item(context, entry) for entry in page.items]
    if page.next_token:
        label = addon.getLocalizedString(20060)
        listitem = xbmcgui.ListItem(label=f"{addon.getLocalizedString(rail.label_id)} · {label}")
        url = context.build_url(action="list", rail=rail_id, cursor=page.next_token)
        items.append((url, listitem, True))
    if items:
        xbmcplugin.addDirectoryItems(context.handle, items)


def show_search(context: PluginContext) -> None:
    addon = xbmcaddon.Addon()
    dialog = xbmcgui.Dialog()
    query = dialog.input(addon.getLocalizedString(21020))
    if not query:
        return
    xbmcplugin.setContent(context.handle, "videos")
    backend = get_backend()
    results = backend.search(query, limit=30)
    if not results:
        listitem = xbmcgui.ListItem(label=addon.getLocalizedString(21030))
        xbmcplugin.addDirectoryItem(context.handle, context.build_url(), listitem, False)
        return
    items = [_build_video_item(context, entry) for entry in results]
    if items:
        xbmcplugin.addDirectoryItems(context.handle, items)


def _build_video_item(context: PluginContext, entry: dict) -> tuple:
    listitem = xbmcgui.ListItem(label=entry.get("title", ""))
    art = {
        "thumb": entry.get("thumb") or entry.get("poster"),
        "poster": entry.get("poster") or entry.get("thumb"),
        "fanart": entry.get("fanart"),
    }
    listitem.setArt({k: v for k, v in art.items() if v})
    genre_value = entry.get("genre")
    if isinstance(entry.get("genres"), list):
        genre_value = ", ".join(entry.get("genres"))
    info_labels = {
        "title": entry.get("title"),
        "plot": entry.get("plot"),
        "year": entry.get("year"),
        "duration": entry.get("duration"),
        "genre": genre_value,
        "mediatype": home.detect_media_type(entry),
    }
    listitem.setInfo("video", {k: v for k, v in info_labels.items() if v})
    listitem.setProperty("IsPlayable", "true")
    asin = entry.get("asin")
    url = context.build_url(action="play", asin=asin) if asin else context.build_url()
    return (url, listitem, False)
