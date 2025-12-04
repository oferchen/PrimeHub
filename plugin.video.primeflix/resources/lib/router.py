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


def dispatch(base_url: str, param_string: str) -> None:
    handle = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    params: Dict[str, str] = dict(parse_qsl(param_string.lstrip("?")))
    action = params.get("action")
    context = PluginContext(base_url, handle)

    # --- Authentication Check ---
    # All actions except 'login' require an authenticated session.
    backend = get_backend()
    if action != "login" and not backend.is_logged_in():
        # If not logged in, force the login screen.
        # If login is successful, we can proceed. Otherwise, we exit.
        if not login.show_login_screen():
            # User cancelled login or it failed, so prevent further action.
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return # Exit if login is cancelled or fails

    try:
        if action == "login":
            login.show_login_screen()
        elif action == "logout":
            backend.logout()
            # Inform the user they have been logged out.
            addon = xbmcaddon.Addon()
            xbmcgui.Dialog().notification(
                addon.getAddonInfo('name'),
                addon.getLocalizedString(32007) + " successful.", # "Logout successful."
                xbmcgui.NOTIFICATION_INFO
            )
            xbmcplugin.endOfDirectory(handle) # End the directory for logout action
            return
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
            query = params.get("query")
            cursor = params.get("cursor")
            listing.show_search(context, query, cursor)
        elif action == "add_to_watchlist":
            asin = params.get("asin")
            if asin:
                listing.handle_add_to_watchlist(context, asin)
        elif action == "mark_as_watched":
            asin = params.get("asin")
            status = params.get("status") == "true"
            if asin:
                listing.handle_mark_as_watched(context, asin, status)
        else: # Default action
            home.show_home(context)

    except PreflightError as exc:
        show_preflight_error(exc)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    xbmcplugin.endOfDirectory(handle)
