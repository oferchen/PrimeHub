"""Home screen builder for PrimeFlix."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, List, Tuple

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
                "perf_logging": "false",
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
        @staticmethod
        def ok(title: str, message: str) -> None:
            print(f"DIALOG: {title}: {message}")

    class _ListItem:
        def __init__(self, label: str = "") -> None:
            self.label = label
            self._art = {}
            self._info = {}
            self._properties = {}

        def setArt(self, art: dict) -> None:
            self._art.update({k: v for k, v in art.items() if v})

        def setInfo(self, info_type: str, info: dict) -> None:
            self._info[info_type] = info

        def setProperty(self, key: str, value: str) -> None:
            self._properties[key] = value

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
    xbmcgui = type("gui", (), {"Dialog": _Dialog, "ListItem": _ListItem})  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore

from ..backend.prime_api import BackendError, RailData, get_backend
from ..perf import log_info, log_warning
from ..preflight import PreflightError

HOME_COLD_THRESHOLD_MS = 1500.0
HOME_WARM_THRESHOLD_MS = 300.0
RAIL_COLD_THRESHOLD_MS = 500.0
RAIL_WARM_THRESHOLD_MS = 150.0
DEFAULT_RAIL_LIMIT = 25


@dataclass(frozen=True)
class RailSpec:
    identifier: str
    label_id: int
    content: str
    optional: bool = False


@dataclass
class RailSnapshot:
    spec: RailSpec
    data: RailData
    from_cache: bool
    elapsed_ms: float


HOME_RAILS: List[RailSpec] = [
    RailSpec("continue", 30010, "episodes", optional=True),
    RailSpec("originals", 30011, "tvshows"),
    RailSpec("movies", 30012, "movies"),
    RailSpec("tv", 30013, "tvshows"),
    RailSpec("recommended", 30014, "videos", optional=True),
]
SEARCH_LABEL_ID = 30020


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


def _notify_error(title: str, message: str) -> None:
    try:
        dialog = xbmcgui.Dialog()
        dialog.ok(title, message)
    except Exception:
        log_warning(message)


def build_home_snapshot(backend, use_cache: bool, ttl: int, force_refresh: bool = False) -> Tuple[List[RailSnapshot], dict]:
    rail_snapshots: List[RailSnapshot] = []
    total_start = time.perf_counter()
    for spec in HOME_RAILS:
        start = time.perf_counter()
        data, from_cache = backend.get_rail(spec.identifier, None, DEFAULT_RAIL_LIMIT, ttl, use_cache, force_refresh)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        rail_snapshots.append(RailSnapshot(spec, data, from_cache, elapsed_ms))
    total_ms = (time.perf_counter() - total_start) * 1000.0
    metrics = {
        "total_ms": total_ms,
        "rail_timings": [
            {
                "id": snapshot.spec.identifier,
                "elapsed_ms": snapshot.elapsed_ms,
                "from_cache": snapshot.from_cache,
                "count": len(snapshot.data.items),
            }
            for snapshot in rail_snapshots
        ],
    }
    return rail_snapshots, metrics


def show_home(context) -> None:
    addon = xbmcaddon.Addon()
    try:
        backend = get_backend()
    except PreflightError as exc:
        _notify_error(addon.getAddonInfo("name"), str(exc))
        return
    except BackendError as exc:
        _notify_error(addon.getAddonInfo("name"), str(exc))
        return

    region = backend.get_region()
    ttl = max(30, _get_setting_int(addon, "cache_ttl", 300))
    use_cache = _get_setting_bool(addon, "use_cache", True)
    verbose = _is_perf_logging_enabled(addon)
    xbmcplugin.setContent(context.handle, "videos")

    if verbose and region:
        log_info(f"Backend region in use: {region.upper()}")

    snapshots, metrics = build_home_snapshot(backend, use_cache=use_cache, ttl=ttl, force_refresh=False)
    total_ms = metrics["total_ms"]
    warm = all(snapshot.from_cache for snapshot in snapshots)
    threshold = HOME_WARM_THRESHOLD_MS if warm else HOME_COLD_THRESHOLD_MS
    if total_ms > threshold:
        log_warning(
            f"Home build exceeded target ({'warm' if warm else 'cold'}): {total_ms:.2f} ms"
        )
    elif verbose:
        log_info(f"Home build completed in {total_ms:.2f} ms")

    for snapshot in snapshots:
        rail_threshold = RAIL_WARM_THRESHOLD_MS if snapshot.from_cache else RAIL_COLD_THRESHOLD_MS
        if snapshot.elapsed_ms > rail_threshold:
            log_warning(
                f"Rail {snapshot.spec.identifier} exceeded target ({'warm' if snapshot.from_cache else 'cold'}): {snapshot.elapsed_ms:.2f} ms"
            )
        elif verbose:
            log_info(
                f"Rail {snapshot.spec.identifier} ready in {snapshot.elapsed_ms:.2f} ms (items={len(snapshot.data.items)})"
            )
        if not snapshot.data.items and snapshot.spec.optional:
            continue
        label = addon.getLocalizedString(snapshot.spec.label_id)
        listitem = xbmcgui.ListItem(label=label)
        if snapshot.data.items:
            art = snapshot.data.items[0].get("art", {})
            listitem.setArt({k: v for k, v in art.items() if v})
        url = context.build_url(action="list", rail=snapshot.spec.identifier)
        xbmcplugin.addDirectoryItem(context.handle, url, listitem, isFolder=True)

    search_label = addon.getLocalizedString(SEARCH_LABEL_ID)
    search_item = xbmcgui.ListItem(label=search_label)
    search_item.setArt({"icon": "DefaultAddonsSearch.png", "thumb": "DefaultAddonsSearch.png"})
    search_url = context.build_url(action="search")
    xbmcplugin.addDirectoryItem(context.handle, search_url, search_item, isFolder=True)
