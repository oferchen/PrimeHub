"""Capability checks to ensure backend availability."""
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


def _addon_exists(addon_id: str) -> bool:
    try:
        xbmcaddon.Addon(addon_id)
        return True
    except Exception:
        return False


def _has_inputstream() -> bool:
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
        _notify_missing("#21090")
        raise PreflightError("Prime backend missing")

    if not _has_inputstream():
        _notify_missing("#21100")
        raise PreflightError("inputstream.adaptive missing")

    log_info(f"Preflight successful for backend {backend_id}")
    return backend_id


def _notify_missing(message_id: str) -> None:
    addon = xbmcaddon.Addon()
    dialog = xbmcgui.Dialog()
    title = addon.getAddonInfo("name")
    message = addon.getLocalizedString(int(message_id.strip("#")))
    try:
        dialog.ok(title, message)
    except Exception:
        log_warning(message)


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
