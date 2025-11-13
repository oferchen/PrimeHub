from __future__ import annotations

from typing import Dict, Optional

try:
    import xbmc
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - development fallback
    xbmc = None
    xbmcgui = None
    xbmcplugin = None

from ..perf import measure
from ..backend import prime_api

PLAYBACK_WARN_MS = 500


def play(handle: int, asin: Optional[str]) -> None:
    if not asin:
        return
    backend = prime_api.get_backend()
    if not backend or not xbmcgui or not xbmcplugin:
        return
    try:
        playback_data = measure(f"playback:{asin}", backend.get_playable, PLAYBACK_WARN_MS, asin)
    except Exception as exc:
        _notify(str(exc))
        _log(f"[PrimeFlix] Playback error for {asin}: {exc}", level=xbmc.LOGERROR if xbmc else 4)  # type: ignore[attr-defined]
        return

    url = playback_data.get("url") or playback_data.get("stream") or playback_data.get("manifest")
    if not url:
        _notify("Missing stream URL")
        return

    listitem = xbmcgui.ListItem(path=url)
    listitem.setProperty("IsPlayable", "true")
    listitem.setProperty("inputstream", "inputstream.adaptive")

    headers = playback_data.get("headers") or {}
    if headers:
        header_string = "&".join(f"{key}={value}" for key, value in headers.items())
        listitem.setProperty("inputstream.adaptive.stream_headers", header_string)

    inputstream_props: Dict[str, str] = playback_data.get("inputstream", {})
    for key, value in inputstream_props.items():
        listitem.setProperty(f"inputstream.adaptive.{key}", str(value))

    if playback_data.get("license_key"):
        listitem.setProperty("inputstream.adaptive.license_key", playback_data["license_key"])

    if playback_data.get("mime_type"):
        listitem.setMimeType(playback_data["mime_type"])

    info = playback_data.get("info") or {}
    if info:
        listitem.setInfo("video", info)

    xbmcplugin.setResolvedUrl(handle, True, listitem)


def _notify(message: str) -> None:
    if xbmcgui:
        xbmcgui.Dialog().notification("PrimeFlix", message, xbmcgui.NOTIFICATION_ERROR, 5000)
    else:  # pragma: no cover - development fallback
        print(f"[PrimeFlix] {message}")


def _log(message: str, level: int = xbmc.LOGINFO if xbmc else 1) -> None:  # type: ignore[attr-defined]
    if xbmc:
        xbmc.log(message, level)
    else:  # pragma: no cover - development fallback
        print(f"[PrimeFlix] {message}")
