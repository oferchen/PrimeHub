"""Playback handoff to Kodi from PrimeFlix."""
from __future__ import annotations

from typing import Dict

try:  # pragma: no cover - Kodi runtime
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    class _XBMC:
        LOGWARNING = 2

        @staticmethod
        def log(message: str, level: int = 0) -> None:
            print(f"[xbmc:{level}] {message}")

    class _Addon:
        def getLocalizedString(self, code: int) -> str:
            return str(code)

    class _GUI:
        class Dialog:
            @staticmethod
            def notification(title: str, message: str, icon: str = "", time: int = 5000) -> None:
                print(f"NOTIFY {title}: {message}")

        class ListItem:
            def __init__(self, label: str = "", path: str = ""):
                self.label = label
                self.path = path

            def setProperty(self, key: str, value: str) -> None:
                pass

            def setInfo(self, info_type: str, info_labels: Dict[str, str]) -> None:
                pass

            def setMimeType(self, mimetype: str) -> None:
                pass

            def setContentLookup(self, enable: bool) -> None:
                pass

    class _Plugin:
        @staticmethod
        def setResolvedUrl(handle, succeeded, listitem):
            print(f"RESOLVED {succeeded} -> {getattr(listitem, 'path', '')}")

    xbmc = _XBMC()  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": _Addon})  # type: ignore
    xbmcgui = _GUI  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore

from ..backend.prime_api import get_backend
from ..perf import log_warning, timed
from ..preflight import ensure_ready_or_raise
from ..router import PluginContext


@timed("playback.handoff", warn_threshold_ms=500)
def play(context: PluginContext, asin: str) -> None:
    addon = xbmcaddon.Addon()
    ensure_ready_or_raise()
    backend = get_backend()
    try:
        payload = backend.get_playable(asin)
    except Exception as exc:  # pragma: no cover - runtime error path
        message = addon.getLocalizedString(21010)
        xbmcgui.Dialog().notification(addon.getAddonInfo("name"), f"{message}: {exc}")
        log_warning(f"Failed to retrieve playback data for {asin}: {exc}")
        return

    stream_url = payload.get("url") or payload.get("stream_url")
    if not stream_url:
        log_warning(f"Backend returned no stream URL for {asin}")
        xbmcgui.Dialog().notification(addon.getAddonInfo("name"), addon.getLocalizedString(21010))
        return

    listitem = xbmcgui.ListItem(path=stream_url)
    listitem.setProperty("inputstream", "inputstream.adaptive")
    listitem.setProperty("inputstream.adaptive.manifest_type", payload.get("manifest_type", "mpd"))
    license_key = payload.get("license_key")
    if license_key:
        listitem.setProperty("inputstream.adaptive.license_key", license_key)
    license_type = payload.get("license_type")
    if license_type:
        listitem.setProperty("inputstream.adaptive.license_type", license_type)
    headers = payload.get("headers") or {}
    if headers:
        header_string = "&".join(f"{k}={v}" for k, v in headers.items())
        listitem.setProperty("inputstream.adaptive.manifest_headers", header_string)
    stream_headers = payload.get("stream_headers") or {}
    if stream_headers:
        stream_header_string = "&".join(f"{k}={v}" for k, v in stream_headers.items())
        listitem.setProperty("inputstream.adaptive.stream_headers", stream_header_string)
    mime_type = payload.get("mime_type")
    if mime_type:
        listitem.setMimeType(mime_type)
    listitem.setContentLookup(False)
    metadata = payload.get("info") or {}
    if metadata:
        listitem.setInfo("video", metadata)

    xbmcplugin.setResolvedUrl(context.handle, True, listitem)
