"""Routing logic for the PrimeFlix Kodi plug-in."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Dict
from urllib.parse import parse_qsl, urlencode

try:  # pragma: no cover - Kodi runtime
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    class _Plugin:
        def __init__(self):
            self.handle = 1

        @staticmethod
        def addDirectoryItem(handle, url, listitem, isFolder=False):
            print(f"ADD DIR: {url} ({'folder' if isFolder else 'item'})")

        @staticmethod
        def endOfDirectory(handle, succeeded=True):
            print("END OF DIRECTORY")

        @staticmethod
        def setContent(handle, content):
            print(f"SET CONTENT: {content}")

        @staticmethod
        def setResolvedUrl(handle, succeeded, listitem):
            print(f"RESOLVED: {succeeded}")

    xbmcplugin = _Plugin()  # type: ignore

from .ui import diagnostics, home, listing, playback


@dataclass
class PluginContext:
    base_url: str
    handle: int

    def build_url(self, **query: str) -> str:
        filtered = {k: v for k, v in query.items() if v is not None}
        if not filtered:
            return self.base_url
        return f"{self.base_url}?{urlencode(filtered)}"


def dispatch(base_url: str, param_string: str) -> None:
    handle = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    params: Dict[str, str] = dict(parse_qsl(param_string.lstrip("?")))
    action = params.get("action")
    context = PluginContext(base_url, handle)

    if not action:
        home.show_home(context)
    elif action == "list":
        rail_id = params.get("rail", "")
        cursor = params.get("cursor")
        listing.show_list(context, rail_id, cursor)
    elif action == "play":
        asin = params.get("asin")
        if asin:
            playback.play(context, asin)
        return
    elif action == "diagnostics":
        diagnostics.show_results(context)
    elif action == "search":
        listing.show_search(context)
    else:
        home.show_home(context)

    xbmcplugin.endOfDirectory(handle)
