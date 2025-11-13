from __future__ import annotations

import json

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
except ImportError:  # pragma: no cover - development fallback
    xbmc = None
    xbmcaddon = None
    xbmcgui = None

from .backend import prime_api


class PreflightError(RuntimeError):
    """Raised when the environment is not ready."""


def _log(message, level=xbmc.LOGINFO if xbmc else 1):  # type: ignore[attr-defined]
    if xbmc:
        xbmc.log(message, level)
    else:  # pragma: no cover - development fallback
        print(f"[xbmc][{level}] {message}")


def _check_inputstream():
    if not xbmcaddon:
        return True
    try:
        addon = xbmcaddon.Addon("inputstream.adaptive")
    except Exception:  # pragma: no cover - Kodi raises RuntimeError when missing
        return False
    enabled = addon.getAddonInfo("name") is not None
    if xbmc:
        state = xbmc.getCondVisibility("System.AddonIsEnabled(inputstream.adaptive)")
        return bool(state and enabled)
    return enabled


def _check_backend():
    backend = prime_api.get_backend()
    return backend is not None


def ensure_ready_or_raise():
    errors = []
    if not _check_backend():
        errors.append(32007)
    if not _check_inputstream():
        errors.append(32008)

    if errors:
        message = _localize_errors(errors)
        if xbmcgui:
            dialog = xbmcgui.Dialog()
            dialog.ok("PrimeFlix", message)
        raise PreflightError(message)


def run():
    ensure_ready_or_raise()
    backend = prime_api.get_backend()
    if backend:
        info = backend.get_backend_info()
        _log(f"[PrimeFlix] Backend info: {json.dumps(info)}")


def _localize_errors(error_ids):
    if not xbmcaddon:
        return "\n".join(str(err) for err in error_ids)
    addon = xbmcaddon.Addon()
    messages = [addon.getLocalizedString(err) for err in error_ids]
    return "\n".join(messages)
