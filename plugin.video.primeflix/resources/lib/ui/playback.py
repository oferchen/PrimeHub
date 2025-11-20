"""Playback hand-off for PrimeFlix.

Invoked by :mod:`resources.lib.router` for ``action=play`` URLs. Delegates to
:mod:`resources.lib.backend.prime_api` to resolve the playable stream and
instructs Kodi to play it via ``inputstream.adaptive``.
"""
from __future__ import annotations

from typing import Any, Dict

try:  # pragma: no cover - Kodi runtime
    import xbmcplugin
    import xbmcgui
    import xbmcaddon
except ImportError:  # pragma: no cover - local dev fallback
    class _PluginStub:
        handle = 1

        @staticmethod
        def setResolvedUrl(handle, succeeded, listitem):
            print(f"RESOLVED[{succeeded}]: {getattr(listitem, 'url', '')}")

    class _ListItemStub:
        def __init__(self, label: str):
            self._label = label
            self.url = ""
            self.info: Dict[str, Any] = {}
            self.properties: Dict[str, str] = {}
            self.art: Dict[str, str] = {}

        def setPath(self, path: str):
            self.url = path

        def setProperty(self, key: str, value: str):
            self.properties[key] = value

        def setInfo(self, info_type: str, info: Dict[str, Any]):
            self.info = info

        def setArt(self, art: Dict[str, str]):
            self.art = art

        def setContentLookup(self, value: bool):
            pass

        def getLabel(self) -> str:
            return self._label

    class _AddonStub:
        @staticmethod
        def getLocalizedString(code: int) -> str:
            return str(code)

    class _DialogStub:
        @staticmethod
        def notification(title: str, message: str, time: int = 3000):
            print(f"NOTIFY: {title}: {message}")

    xbmcplugin = _PluginStub()  # type: ignore
    xbmcgui = type("gui", (), {"ListItem": _ListItemStub, "Dialog": _DialogStub})  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": lambda *args, **kwargs: _AddonStub()})  # type: ignore

from ..backend.prime_api import BackendError, get_backend
from ..perf import timed
from ..preflight import ensure_ready_or_raise


@timed("playback_handoff")
def play(context, asin: str) -> None:
    ensure_ready_or_raise()
    backend = get_backend()
    addon = xbmcaddon.Addon()
    try:
        playback = backend.get_playable(asin)
    except BackendError as exc:
        _notify(addon, str(exc))
        return

    listitem = xbmcgui.ListItem(playback.get("title") or addon.getAddonInfo("name"))
    stream_url = playback.get("url") or playback.get("manifest") or playback.get("stream")
    if isinstance(stream_url, str):
        listitem.setPath(stream_url)

    _apply_inputstream_properties(listitem, playback)

    info = playback.get("info")
    if isinstance(info, dict):
        listitem.setInfo("video", info)
    art = playback.get("art")
    if isinstance(art, dict):
        listitem.setArt(art)

    listitem.setContentLookup(False)
    xbmcplugin.setResolvedUrl(context.handle, True, listitem)


def _apply_inputstream_properties(listitem, playback: Dict[str, Any]) -> None:
    listitem.setProperty("inputstream", "inputstream.adaptive")
    manifest_type = playback.get("manifest_type") or playback.get("type") or "mpd"
    listitem.setProperty("inputstream.adaptive.manifest_type", str(manifest_type))
    license_key = playback.get("license_key") or playback.get("licenseUrl") or playback.get("license_url")
    if license_key:
        listitem.setProperty("inputstream.adaptive.license_key", str(license_key))
    license_type = playback.get("license_type") or "com.widevine.alpha"
    listitem.setProperty("inputstream.adaptive.license_type", str(license_type))
    headers = playback.get("headers") or playback.get("license_headers")
    if isinstance(headers, dict) and license_key:
        header_str = "&".join(f"{k}={v}" for k, v in headers.items())
        listitem.setProperty("inputstream.adaptive.stream_headers", header_str)
    if playback.get("is_live"):
        listitem.setProperty("inputstream.adaptive.manifest_update_parameter", "full")


def _notify(addon: object, message: str) -> None:
    try:
        dialog = xbmcgui.Dialog()
        dialog.notification(addon.getAddonInfo("name"), message)  # type: ignore[attr-defined]
    except Exception:
        pass
