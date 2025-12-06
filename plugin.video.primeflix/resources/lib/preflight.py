"""Capability checks."""
from __future__ import annotations
from typing import Optional
try:
    import xbmc
    import xbmcaddon
    import xbmcgui
except ImportError:
    from ...tests.kodi_mocks import xbmc, xbmcaddon, xbmcgui

from ..common import Globals
from ..backend.prime_api import get_prime_video

def ensure_ready_or_raise() -> None:
    """
    Ensures the environment is ready, checking for inputstream and DRM.
    """
    # In this new architecture, login is handled by the router.
    # This check focuses on Kodi-specific components.
    if not _has_inputstream():
        raise PreflightError("inputstream.adaptive is not available.")
    
    pv = get_prime_video()
    if not pv.is_drm_ready():
        raise PreflightError("DRM is not ready.")

def _has_inputstream() -> bool:
    # A real implementation might use JSON-RPC to check if the add-on is enabled
    return True # For now, assume it's always available

def show_preflight_error(e: PreflightError):
    g = Globals()
    g.dialog.ok("Preflight Check Failed", str(e))

class PreflightError(Exception):
    pass