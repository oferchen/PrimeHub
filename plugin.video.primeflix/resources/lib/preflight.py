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
                return "PrimeFlix"
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

from .perf import log_info, log_warning

BACKEND_CANDIDATES = (
    "plugin.video.amazon-test",
    "plugin.video.amazonprime",
    "plugin.video.amazonvod",
    "plugin.video.amazon",
    "plugin.video.primevideo",
)

INPUTSTREAM_ADDON_ID = "inputstream.adaptive"


class PreflightError(RuntimeError):
    """Raised when the environment is not ready."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _addon_exists(addon_id: str) -> bool:
    try:
        xbmcaddon.Addon(addon_id)
        return True
    except Exception:
        return False


def _has_inputstream() -> bool:
    """Return whether inputstream.adaptive is installed and enabled."""

    # Prefer JSON-RPC to confirm the add-on is enabled (works on Kodi runtime)
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

    # Fallback to presence check
    try:
        xbmcaddon.Addon(INPUTSTREAM_ADDON_ID)
        return True
    except Exception:
        return False


def ensure_ready_or_raise(target_backend: Optional[str] = None) -> str:
    """Ensure backend and inputstream components exist.

    Returns the resolved backend add-on id.
    """

    backend_id = target_backend
    if backend_id is None:
        backend_id = _discover_backend()
    if backend_id is None:
        raise PreflightError(_get_message("#21090"))

    if not _has_inputstream():
        raise PreflightError(_get_message("#21100"))

    drm_ready = _backend_drm_ready(backend_id)
    if drm_ready is False:
        raise PreflightError(_get_message("#21110"))

    log_info(f"Preflight successful for backend {backend_id}")
    return backend_id


def _notify_missing(message_id: str) -> None:
    addon = xbmcaddon.Addon()
    dialog = xbmcgui.Dialog()
    title = addon.getAddonInfo("name")
    message = _get_message(message_id)
    try:
        dialog.ok(title, message)
    except Exception:
        log_warning(message)


def _get_message(message_id: str) -> str:
    addon = xbmcaddon.Addon()
    try:
        return addon.getLocalizedString(int(message_id.strip("#")))
    except Exception:
        return message_id


def show_preflight_error(error: PreflightError) -> None:
    """Display a preflight failure in a Kodi-friendly way."""

    message = getattr(error, "message", str(error))
    _notify_missing(message)


def _discover_backend() -> Optional[str]:
    for candidate in BACKEND_CANDIDATES:
        if _addon_exists(candidate):
            return candidate

    # Fall back to JSON-RPC enumeration
    try:
        response = xbmc.executeJSONRPC(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "Addons.GetAddons",
                    "params": {"type": "xbmc.addon.video"},
                    "id": 1,
                }
            )
        )
        data = json.loads(response)
        for addon in data.get("result", {}).get("addons", []):
            addon_id = addon.get("addonid")
            if addon_id and addon_id.lower().startswith("plugin.video.amazon"):
                return addon_id
    except Exception:
        pass

    return None


def _backend_drm_ready(addon_id: str) -> Optional[bool]:
    """Ask backend whether DRM is ready using JSON-RPC ExecuteAddon.

    Returns ``True`` when explicitly reported ready, ``False`` when a response
    indicates DRM is not ready, and ``None`` when unknown/unsupported.
    """

    payload = {
        "jsonrpc": "2.0",
        "method": "Addons.ExecuteAddon",
        "params": {
            "addonid": addon_id,
            "params": {"action": "is_drm_ready"},
        },
        "id": 3,
    }
    try:
        response = json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
        result = response.get("result", {})
        value = result.get("value") if isinstance(result, dict) else None
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "yes", "ready"):
                return True
            if lowered in ("false", "no", "not ready", "unavailable"):
                return False
        if isinstance(value, bool):
            return value
        if isinstance(value, dict):
            ready = value.get("ready")
            if isinstance(ready, bool):
                return ready
    except Exception:
        return None
    return None
