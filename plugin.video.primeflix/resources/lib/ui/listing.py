"""Rail listings and search handling."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

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
        def __init__(self):
            self._settings = {
                "region": "0",
                "cache_ttl": "300",
                "use_cache": "true",
            }

        def getLocalizedString(self, code: int) -> str:
            return str(code)

        def getSetting(self, key: str) -> str:
            return self._settings.get(key, "")

        def getSettingInt(self, key: str) -> int:
            return int(self._settings.get(key, "0"))

        def getSettingBool(self, key: str) -> bool:
            return self._settings.get(key, "false").lower() == "true"

        def getAddonInfo(self, key: str) -> str:
            if key == "name":
                return "PrimeFlix"
            return ""

    class _Dialog:
        INPUT_ALPHANUM = 0

        @staticmethod
        def input(heading: str, defaultt: str = "", type: int = 0) -> str:  # noqa: A002 - Kodi signature
            print(f"INPUT({heading}): {defaultt}")
            return defaultt

        @staticmethod
        def notification(title: str, message: str, time: int = 3000) -> None:  # noqa: A003 - Kodi signature
            print(f"NOTIFY {title}: {message}")

    class _ListItem:
        def __init__(self, label: str = "") -> None:
            self.label = label
            self._art = {}
            self._info: Dict[str, Dict[str, Any]] = {}
            self._props: Dict[str, str] = {}

        def setArt(self, art: Dict[str, Optional[str]]) -> None:
            self._art.update({k: v for k, v in art.items() if v})

        def setInfo(self, info_type: str, info: Dict[str, Any]) -> None:
            self._info[info_type] = info

        def setProperty(self, key: str, value: str) -> None:
            self._props[key] = value

        def setContentLookup(self, enabled: bool) -> None:
            self._props["content_lookup"] = str(enabled)

    class _Plugin:
        def __init__(self) -> None:
            self.handle = 1

        @staticmethod
        def addDirectoryItem(handle: int, url: str, listitem: _ListItem, isFolder: bool = False) -> None:
            print(f"ADD {url} folder={isFolder} label={listitem.label}")

        @staticmethod
        def setContent(handle: int, content: str) -> None:
            print(f"SET CONTENT: {content}")

    xbmc = _XBMC()  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": _Addon})  # type: ignore
    xbmcgui = type(
        "gui",
        (),
        {
            "Dialog": _Dialog,
            "ListItem": _ListItem,
            "INPUT_ALPHANUM": 0,
        },
    )  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore

from ..backend.prime_api import BackendError, get_backend
from ..perf import log_info, log_warning
from ..preflight import PreflightError
from .home import HOME_RAILS, RAIL_COLD_THRESHOLD_MS, RAIL_WARM_THRESHOLD_MS, RailSpec

MORE_LABEL_ID = 30021
SEARCH_PROMPT_ID = 30030
NO_RESULTS_ID = 30031
SEARCH_CONTENT_TTL = 60
DEFAULT_LIMIT = 25

RAIL_MAP = {spec.identifier: spec for spec in HOME_RAILS}


def _get_setting_int(addon: Any, setting_id: str, default: int) -> int:
    try:
        return addon.getSettingInt(setting_id)
    except AttributeError:
        try:
            return int(addon.getSetting(setting_id))
        except Exception:
            return default


def _get_setting_bool(addon: Any, setting_id: str, default: bool) -> bool:
    try:
        return addon.getSettingBool(setting_id)
    except AttributeError:
        value = addon.getSetting(setting_id)
        if isinstance(value, str):
            return value.lower() == "true"
        return default


def _is_perf_logging_enabled(addon: Any) -> bool:
    return _get_setting_bool(addon, "perf_logging", False)


def _add_video_item(handle: int, context, item: Dict[str, Any]) -> None:
    label = item.get("title", "")
    listitem = xbmcgui.ListItem(label=label)
    art = item.get("art", {})
    listitem.setArt({k: v for k, v in art.items() if v})
    info = item.get("info", {})
    if info:
        listitem.setInfo("video", info)
    if item.get("is_playable", True):
        listitem.setProperty("IsPlayable", "true")
        url = context.build_url(action="play", asin=item["asin"])
        listitem.setContentLookup(False)
        xbmcplugin.addDirectoryItem(handle, url, listitem, isFolder=False)
    else:
        target_rail = item.get("rail") or item.get("target")
        if target_rail:
            url = context.build_url(action="list", rail=target_rail)
            xbmcplugin.addDirectoryItem(handle, url, listitem, isFolder=True)
        else:
            xbmcplugin.addDirectoryItem(handle, context.build_url(action="play", asin=item["asin"]), listitem, isFolder=False)


def _notify(addon: Any, message: str) -> None:
    title = "PrimeFlix"
    try:
        title = addon.getAddonInfo("name") or title
    except Exception:
        pass
    try:
        xbmcgui.Dialog().notification(title, message)
    except Exception:
        log_warning(message)


def show_list(context, rail_id: str, cursor: Optional[str]) -> None:
    addon = xbmcaddon.Addon()
    try:
        backend = get_backend()
    except (PreflightError, BackendError) as exc:
        _notify(addon, str(exc))
        return

    spec: Optional[RailSpec] = RAIL_MAP.get(rail_id)
    content_type = spec.content if spec else "videos"
    ttl = max(30, _get_setting_int(addon, "cache_ttl", 300))
    use_cache = _get_setting_bool(addon, "use_cache", True)
    xbmcplugin.setContent(context.handle, content_type)
    verbose = _is_perf_logging_enabled(addon)

    start = time.perf_counter()
    data, from_cache = backend.get_rail(rail_id, cursor, DEFAULT_LIMIT, ttl, use_cache, force_refresh=False)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    threshold = RAIL_WARM_THRESHOLD_MS if from_cache else RAIL_COLD_THRESHOLD_MS
    if elapsed_ms > threshold:
        log_warning(
            f"Rail {rail_id} listing exceeded target ({'warm' if from_cache else 'cold'}): {elapsed_ms:.2f} ms"
        )
    elif verbose:
        log_info(f"Rail {rail_id} listing completed in {elapsed_ms:.2f} ms")

    if not data.items:
        _notify(addon, addon.getLocalizedString(NO_RESULTS_ID))
        return

    for item in data.items:
        _add_video_item(context.handle, context, item)

    if data.cursor:
        more_label = addon.getLocalizedString(MORE_LABEL_ID)
        more_item = xbmcgui.ListItem(label=more_label)
        more_item.setArt({"icon": "DefaultFolder.png"})
        more_url = context.build_url(action="list", rail=rail_id, cursor=data.cursor)
        xbmcplugin.addDirectoryItem(context.handle, more_url, more_item, isFolder=True)


def show_search(context, query: Optional[str] = None, cursor: Optional[str] = None) -> None:
    addon = xbmcaddon.Addon()
    if not query:
        heading = addon.getLocalizedString(SEARCH_PROMPT_ID)
        input_type = getattr(xbmcgui, "INPUT_ALPHANUM", 0)
        try:
            query = xbmcgui.Dialog().input(heading, type=input_type)
        except Exception:
            query = ""
        if not query:
            return

    try:
        backend = get_backend()
    except (PreflightError, BackendError) as exc:
        _notify(addon, str(exc))
        return

    use_cache = _get_setting_bool(addon, "use_cache", True)
    xbmcplugin.setContent(context.handle, "videos")
    verbose = _is_perf_logging_enabled(addon)

    start = time.perf_counter()
    data, from_cache = backend.search(query, cursor, DEFAULT_LIMIT, SEARCH_CONTENT_TTL, use_cache)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    threshold = RAIL_WARM_THRESHOLD_MS if from_cache else RAIL_COLD_THRESHOLD_MS
    if elapsed_ms > threshold:
        log_warning(
            f"Search '{query}' exceeded target ({'warm' if from_cache else 'cold'}): {elapsed_ms:.2f} ms"
        )
    elif verbose:
        log_info(f"Search '{query}' completed in {elapsed_ms:.2f} ms")

    if not data.items:
        _notify(addon, addon.getLocalizedString(NO_RESULTS_ID))
        return

    for item in data.items:
        _add_video_item(context.handle, context, item)

    if data.cursor:
        more_label = addon.getLocalizedString(MORE_LABEL_ID)
        more_item = xbmcgui.ListItem(label=more_label)
        more_item.setArt({"icon": "DefaultFolder.png"})
        more_url = context.build_url(action="search", query=query, cursor=data.cursor)
        xbmcplugin.addDirectoryItem(context.handle, more_url, more_item, isFolder=True)
