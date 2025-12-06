"""Playback route handing off manifests to Kodi."""
from __future__ import annotations
from typing import Any, Dict

try:
    import xbmcgui
    import xbmcplugin
except ImportError:
    from ...tests.kodi_mocks import xbmcgui, xbmcplugin

from ..backend.prime_api import PrimeVideo, Playable
from ..preflight import PreflightError

def play(context, pv: PrimeVideo, asin: str) -> None:
    """Gets playback resources and hands them off to Kodi."""
    try:
        success, stream_info = pv.GetStream(asin)
        if not success:
            raise PreflightError(stream_info)
        
        playable = Playable(
            url=stream_info.get("manifestUrl"),
            manifest_type="mpd",
            license_key=stream_info.get("licenseUrl"),
            headers={},
            metadata={"title": f"Playable for {asin}"}
        )
        
        list_item = _build_list_item(playable)
        xbmcplugin.setResolvedUrl(context.handle, True, list_item)
        
    except Exception as e:
        xbmcgui.Dialog().notification("Error", f"Could not get playback stream: {e}")

def _build_list_item(playable: Playable) -> xbmcgui.ListItem:
    li = xbmcgui.ListItem(label=playable.metadata.get("title", "Prime Video"))
    li.setProperty("inputstream", "inputstream.adaptive")
    li.setProperty("inputstream.adaptive.manifest_type", playable.manifest_type)
    if playable.license_key:
        li.setProperty("inputstream.adaptive.license_type", "com.widevine.alpha")
        li.setProperty("inputstream.adaptive.license_key", playable.license_key)
    li.setMimeType("application/dash+xml")
    li.setContentLookup(False)
    return li