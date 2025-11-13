"""Playback handoff to Kodi."""
from __future__ import annotations

from typing import Any, Dict

try:  # pragma: no cover - Kodi runtime
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    class _XBMC:
        LOGDEBUG = 0
        LOGINFO = 1
        LOGWARNING = 2
        LOGERROR = 3

        @staticmethod
        def log(message: str, level: int = 0) -> None:
            print(f"[xbmc:{level}] {message}")

    class _Addon:
        def getAddonInfo(self, key: str) -> str:
            if key == "name":
                return "PrimeFlix"
            return ""

    class _Dialog:
        @staticmethod
        def notification(title: str, message: str, time: int = 3000) -> None:  # noqa: A003 - Kodi signature
            print(f"NOTIFY {title}: {message}")

    class _ListItem:
        def __init__(self, label: str = "") -> None:
            self.label = label
            self._props: Dict[str, str] = {}
            self._info: Dict[str, Dict[str, Any]] = {}
            self._art: Dict[str, str] = {}
            self._path = ""

        def setProperty(self, key: str, value: str) -> None:
            self._props[key] = value

        def setInfo(self, info_type: str, info: Dict[str, Any]) -> None:
            self._info[info_type] = info

        def setArt(self, art: Dict[str, str]) -> None:
            self._art.update({k: v for k, v in art.items() if v})

        def setPath(self, path: str) -> None:
            self._path = path

        def setContentLookup(self, enabled: bool) -> None:
            self._props["content_lookup"] = str(enabled)

        def setMimeType(self, mimetype: str) -> None:
            self._props["mimetype"] = mimetype

    class _Plugin:
        def __init__(self) -> None:
            self.handle = 1

        @staticmethod
        def setResolvedUrl(handle: int, succeeded: bool, listitem: _ListItem) -> None:
            print(f"RESOLVE {succeeded} path={listitem._path}")

    xbmc = _XBMC()  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": _Addon})  # type: ignore
    xbmcgui = type("gui", (), {"Dialog": _Dialog, "ListItem": _ListItem})  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore

from ..backend.prime_api import BackendError, get_backend
from ..perf import log_warning, timed
from ..preflight import PreflightError

PLAYBACK_THRESHOLD_MS = 800.0


def _notify(message: str) -> None:
    addon = xbmcaddon.Addon()
    title = addon.getAddonInfo("name")
    try:
        xbmcgui.Dialog().notification(title, message)
    except Exception:
        log_warning(message)


def _format_headers(headers: Dict[str, Any]) -> str:
    return "&".join(f"{key}={value}" for key, value in headers.items())


@timed("Playback handoff", warn_threshold_ms=PLAYBACK_THRESHOLD_MS)
def play(context, asin: str) -> None:
    try:
        backend = get_backend()
    except (PreflightError, BackendError) as exc:
        _notify(str(exc))
        return

    try:
        payload = backend.get_playable(asin)
    except BackendError as exc:
        _notify(str(exc))
        return

    if not isinstance(payload, dict):
        _notify("Invalid playback payload")
        return

    url = payload.get("url") or payload.get("manifest") or payload.get("stream")
    if not url:
        _notify("Playback URL missing")
        return

    listitem = xbmcgui.ListItem(label=payload.get("title", ""))
    listitem.setPath(url)
    listitem.setContentLookup(False)
    listitem.setProperty("inputstream", "inputstream.adaptive")
    listitem.setProperty("inputstreamaddon", "inputstream.adaptive")

    info = payload.get("info")
    if isinstance(info, dict):
        listitem.setInfo("video", info)
    art = payload.get("art")
    if isinstance(art, dict):
        listitem.setArt(art)

    mimetype = payload.get("mimetype") or payload.get("mime_type")
    if isinstance(mimetype, str):
        listitem.setMimeType(mimetype)

    headers = payload.get("headers") or payload.get("manifest_headers")
    if isinstance(headers, dict) and headers:
        header_string = _format_headers(headers)
        listitem.setProperty("inputstream.adaptive.manifest_headers", header_string)
        listitem.setProperty("inputstream.adaptive.stream_headers", header_string)

    inputstream_props = payload.get("inputstream") or payload.get("properties")
    if isinstance(inputstream_props, dict):
        for key, value in inputstream_props.items():
            if value is None:
                continue
            listitem.setProperty(str(key), str(value))

    license_key = payload.get("license_key")
    if isinstance(license_key, str):
        listitem.setProperty("inputstream.adaptive.license_key", license_key)

    xbmcplugin.setResolvedUrl(context.handle, True, listitem)
