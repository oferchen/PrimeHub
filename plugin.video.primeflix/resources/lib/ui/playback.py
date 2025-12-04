"""Playback route handing off manifests to Kodi.

Invoked from :mod:`resources.lib.router` when the user selects a playable
item. The function constructs a configured ListItem using the backend-provided
manifest and passes it to ``setResolvedUrl``.
"""

from __future__ import annotations

from typing import Any, Dict

try:  # pragma: no cover - Kodi runtime
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    from ...tests.kodi_mocks import MockXBMCGUI as xbmcgui
    from ...tests.kodi_mocks import MockXBMCPlugin as xbmcplugin

from ..backend.prime_api import BackendError, BackendUnavailable, Playable, get_backend
from ..perf import timed
from ..preflight import PreflightError, ensure_ready_or_raise

INPUTSTREAM_ID = "inputstream.adaptive"


@timed("playback_handoff")
def play(context, asin: str) -> None:
    ensure_ready_or_raise()
    addon = xbmcaddon.Addon() # Need addon for localized strings
    backend = get_backend()
    try:
        playable = backend.get_playable(asin)
    except (BackendUnavailable, BackendError) as exc:
        # Display a more user-friendly error notification for content fetching failures
        xbmcgui.Dialog().notification(
            addon.getLocalizedString(32005), # "Login Failed" (re-purposed for error)
            addon.getLocalizedString(41000), # New string for "Content Unavailable"
            xbmcgui.NOTIFICATION_ERROR
        )
        raise PreflightError(str(exc))

    list_item = _build_list_item(playable)
    xbmcplugin.setResolvedUrl(context.handle, True, list_item)


def _build_list_item(playable: Playable):
    li = xbmcgui.ListItem(label=playable.metadata.get("title", "Prime Video"))
    li.setContentLookup(False)
    li.setProperty("inputstream", INPUTSTREAM_ID)
    li.setProperty("inputstream.adaptive.manifest_type", playable.manifest_type)
    if playable.license_key:
        li.setProperty("inputstream.adaptive.license_type", "com.widevine.alpha")
        li.setProperty("inputstream.adaptive.license_key", playable.license_key)
    headers = "\n".join([f"{k}: {v}" for k, v in playable.headers.items()])
    if headers:
        li.setProperty("inputstream.adaptive.stream_headers", headers)
    li.setProperty("path", playable.url)
    li.setInfo("video", playable.metadata or {})
    return li
