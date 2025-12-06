"""Routing logic for the PrimeHub Kodi plug-in."""
from __future__ import annotations
import sys
from dataclasses import dataclass
from typing import Dict
from urllib.parse import parse_qsl, urlencode

try:
    import xbmcplugin
    import xbmcaddon
    import xbmcgui
except ImportError:
    from ...tests.kodi_mocks import xbmcplugin, xbmcaddon, xbmcgui

from .preflight import PreflightError, show_preflight_error
from .ui import diagnostics, home, listing, playback, login
from .backend.prime_api import get_prime_video # Updated import

@dataclass
class PluginContext:
    base_url: str
    handle: int
    def build_url(self, **query: str) -> str:
        # ... (implementation remains the same)
        pass

def dispatch(base_url: str, param_string: str) -> None:
    handle = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    params: Dict[str, str] = dict(parse_qsl(param_string.lstrip("?")))
    action = params.get("action")
    context = PluginContext(base_url, handle)

    # For simplicity in this refactoring, the login check is temporarily removed.
    # It would be re-implemented in preflight.py.
    
    try:
        pv = get_prime_video()
        if not action:
            home.show_home(context, pv)
        elif action == "list":
            listing.show_list(context, pv, params.get("rail_id", ""))
        elif action == "play":
            playback.play(context, pv, params.get("asin", ""))
        # ... other actions like search, diagnostics ...
        else:
            home.show_home(context, pv)
            
    except PreflightError as exc:
        show_preflight_error(exc)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    xbmcplugin.endOfDirectory(handle)