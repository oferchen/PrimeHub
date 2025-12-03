"""Capability checks to ensure backend availability and DRM readiness.

This module is called by routing/UI layers and by
:mod:`resources.lib.backend.prime_api` to ensure the environment is usable
before any navigation or playback happens. It performs backend discovery,
verifies required add-ons such as ``inputstream.adaptive`` are installed and
enabled, and optionally queries the Prime backend for DRM readiness via
JSON-RPC.
"""

from __future__ import annotations

import json
from typing import Optional

from .perf import log_info, log_warning

try:  # pragma: no cover - Kodi runtime
    import xbmc
    import xbmcaddon
    import xbmcgui
except ImportError:  # pragma: no cover - local dev fallback

    class _XBMC:
        LOGDEBUG = 0
        LOGINFO = 1
        LOGWARNING = 2
        LOGERROR = 3

        @staticmethod
        def log(msg: str, level: int = 0) -> None:
            print(f"[xbmc:{level}] {msg}")

        @staticmethod
        def executeJSONRPC(payload: str) -> str:
            return json.dumps({"result": {"addons": []}})

    class _Addon:
        def __init__(self, addon_id: Optional[str] = None):
            self._id = addon_id or "plugin.video.primeflix"

        def getAddonInfo(self, key: str) -> str:
            if key == "id":
                return self._id
            if key == "name":
                return "PrimeHub"
            return ""

        def getLocalizedString(self, code: int) -> str:
            return str(code)

    class _Dialog:
        @staticmethod
        def ok(title: str, message: str) -> None:
            print(f"DIALOG: {title}: {message}")

    xbmc = _XBMC()  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": _Addon})  # type: ignore
    xbmcgui = type("gui", (), {"Dialog": _Dialog})  # type: ignore

from .backend.prime_api import get_backend

LOG_PREFIX = "[PrimeHub]"
INPUTSTREAM_ADDON_ID = "inputstream.adaptive"


class PreflightError(RuntimeError):
    """Raised when the environment is not ready."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _has_inputstream() -> bool:
    """Return whether inputstream.adaptive is installed and enabled."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "Addons.GetAddonDetails",
            "params": {"addonid": INPUTSTREAM_ADDON_ID, "properties": ["enabled"]},
            "id": 2,
        }
        response = json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
        enabled = response.get("result", {}).get("addon", {}).get("enabled")
        if isinstance(enabled, bool):
            return enabled
    except Exception:
        pass
    return False # Assume not available if check fails


def ensure_ready_or_raise() -> None:
    """
    Ensure the environment is ready for playback.
    Checks for a valid login, inputstream component, and DRM readiness.
    """
    backend = get_backend()
    if not backend.is_logged_in():
        raise PreflightError(_get_message("#21090")) # "Please log in..."

    if not _has_inputstream():
        raise PreflightError(_get_message("#21100"))

    if backend.is_drm_ready() is False:
        raise PreflightError(_get_message("#21110"))

    log_info("Preflight checks successful.")


def _get_message(message_id: str) -> str:
    addon = xbmcaddon.Addon()
    try:
        return addon.getLocalizedString(int(message_id.strip("#")))
    except Exception:
        return message_id


def show_preflight_error(error: PreflightError) -> None:
    """Display a preflight failure in a Kodi-friendly way."""
    message = getattr(error, "message", str(error))
    addon = xbmcaddon.Addon()
    title = addon.getAddonInfo("name")
    try:
        dialog = xbmcgui.Dialog()
        dialog.ok(title, message)
    except Exception:
        log_warning(message)
