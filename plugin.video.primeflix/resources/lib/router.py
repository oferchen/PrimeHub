"""Routing logic for the PrimeFlix Kodi plug-in."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Dict
from urllib.parse import parse_qsl, urlencode

try:  # pragma: no cover - Kodi runtime
    import xbmcplugin
    import xbmcaddon # Added for logout notification
    import xbmcgui # Added for logout notification
except ImportError:  # pragma: no cover - local dev fallback
    from ...tests.kodi_mocks import MockXBMCPlugin as xbmcplugin
    from ...tests.kodi_mocks import MockXBMCAddon as xbmcaddon
    from ...tests.kodi_mocks import MockXBMCGUI as xbmcgui

from .preflight import PreflightError, show_preflight_error
from .ui import diagnostics, home, listing, playback, login
from .backend.prime_api import get_backend

@dataclass
class PluginContext:
    base_url: str
    handle: int

    def build_url(self, **query: str) -> str:
        filtered = {k: v for k, v in query.items() if v is not None}
        if not filtered:
            return self.base_url
        return f"{self.base_url}?{urlencode(filtered)}"


import asyncio

# ... (imports remain the same)

def dispatch(base_url: str, param_string: str) -> None:
    """Main function to dispatch routes."""
    asyncio.run(async_dispatch(base_url, param_string))

async def async_dispatch(base_url: str, param_string: str) -> None:
    handle = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    params: Dict[str, str] = dict(parse_qsl(param_string.lstrip("?")))
    action = params.get("action")
    context = PluginContext(base_url, handle)

    backend = get_backend()
    if action != "login" and not backend.is_logged_in():
        if not login.show_login_screen():
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return

    try:
        if action == "login":
            login.show_login_screen()
        elif action == "logout":
            backend.logout()
            # ... (notification logic)
            xbmcplugin.endOfDirectory(handle)
            return
        elif action == "list":
            rail_id = params.get("rail", "")
            cursor = params.get("cursor")
            await listing.show_list(context, rail_id, cursor)
        elif action == "play":
            asin = params.get("asin")
            if asin:
                await playback.play(context, asin)
            return
        elif action == "diagnostics":
            await diagnostics.show_results(context)
        elif action == "search":
            query = params.get("query")
            cursor = params.get("cursor")
            await listing.show_search(context, query, cursor)
        elif action == "add_to_watchlist":
            # ... (this can remain synchronous if it doesn't await)
            pass
        elif action == "mark_as_watched":
            # ... (this can remain synchronous)
            pass
        else: # Default action
            await home.show_home(context)

    except PreflightError as exc:
        show_preflight_error(exc)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    xbmcplugin.endOfDirectory(handle)
