"""Home screen rendering for PrimeFlix."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

try:  # pragma: no cover - Kodi runtime
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    class _Addon:
        def getAddonInfo(self, key: str) -> str:
            return "PrimeFlix"

        def getLocalizedString(self, code: int) -> str:
            return str(code)

        def getSettingBool(self, key: str) -> bool:
            return True

        def getSettingInt(self, key: str) -> int:
            return 300

    class _GUI:
        class ListItem:
            def __init__(self, label: str = ""):
                self.label = label

            def setArt(self, art: Dict[str, str]) -> None:
                pass

            def setInfo(self, info_type: str, info_labels: Dict[str, str]) -> None:
                pass

            def setProperty(self, key: str, value: str) -> None:
                pass

    class _Plugin:
        @staticmethod
        def addDirectoryItem(handle, url, listitem, isFolder=False):
            print(f"ADD DIR: {url}")

        @staticmethod
        def addDirectoryItems(handle, items):
            for args in items:
                _Plugin.addDirectoryItem(handle, *args)

        @staticmethod
        def setContent(handle, content):
            print(f"SET CONTENT {content}")

    xbmcaddon = type("addon", (), {"Addon": _Addon})  # type: ignore
    xbmcgui = _GUI  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore

from ..backend.prime_api import get_backend
from ..cache import get_cache
from ..perf import log_info, log_warning, timed
from ..preflight import ensure_ready_or_raise
from ..router import PluginContext


@dataclass
class RailDefinition:
    identifier: str
    label_id: int
    content_type: str
    limit: int = 25


HOME_RAILS: List[RailDefinition] = [
    RailDefinition("continue", 20000, "episodes"),
    RailDefinition("originals", 20010, "videos"),
    RailDefinition("movies", 20020, "movies"),
    RailDefinition("tv", 20030, "tvshows"),
    RailDefinition("recommended", 20040, "videos"),
]

CACHE_PREFIX = "rail::"
CACHE_DEFAULT_TTL = 300
COLD_THRESHOLD_MS = 1500
WARM_THRESHOLD_MS = 300
RAIL_COLD_THRESHOLD_MS = 500
RAIL_WARM_THRESHOLD_MS = 150


def _addon() -> xbmcaddon.Addon:
    return xbmcaddon.Addon()


@timed("home.show_home", warn_threshold_ms=COLD_THRESHOLD_MS)
def show_home(context: PluginContext) -> None:
    start = time.perf_counter()
    addon = _addon()
    ensure_ready_or_raise()
    backend = get_backend()
    region = backend.get_region()
    preferred_region = ["us", "uk", "de", "jp"][addon.getSettingInt("region")]
    if region and region.lower() != preferred_region.lower():
        message = addon.getLocalizedString(21110).format(preferred=preferred_region.upper(), backend=region.upper())
        log_info(message)

    xbmcplugin.setContent(context.handle, "videos")
    instrumentation: List[Dict[str, Any]] = []
    for rail in HOME_RAILS:
        _render_rail(context, rail, instrumentation)
    _render_diagnostics(context)
    _render_search(context)

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    threshold = COLD_THRESHOLD_MS if _is_cold_run(instrumentation) else WARM_THRESHOLD_MS
    if elapsed_ms > threshold:
        log_warning(f"Home build exceeded target {elapsed_ms:.2f} ms (threshold {threshold} ms)")
    else:
        log_info(f"Home build completed in {elapsed_ms:.2f} ms")


def _render_rail(context: PluginContext, rail: RailDefinition, instrumentation: List[Dict[str, Any]]) -> None:
    addon = _addon()
    data, metrics = _load_rail_data(rail)
    instrumentation.append(metrics)

    items = []
    for entry in data.get("items", [])[: rail.limit]:
        listitem = xbmcgui.ListItem(label=entry.get("title", ""))
        art = {
            "thumb": entry.get("thumb") or entry.get("poster"),
            "poster": entry.get("poster") or entry.get("thumb"),
            "fanart": entry.get("fanart"),
        }
        listitem.setArt({k: v for k, v in art.items() if v})
        info_labels = {
            "title": entry.get("title"),
            "plot": entry.get("plot"),
            "year": entry.get("year"),
            "duration": entry.get("duration"),
            "genre": ", ".join(entry.get("genres", entry.get("genre", []) or [])) if isinstance(entry.get("genres"), list) else entry.get("genre"),
            "mediatype": detect_media_type(entry),
        }
        listitem.setInfo("video", {k: v for k, v in info_labels.items() if v})
        listitem.setProperty("IsPlayable", "true")
        asin = entry.get("asin")
        url = context.build_url(action="play", asin=asin) if asin else context.build_url()
        items.append((url, listitem, False))

    if data.get("next_token"):
        more_label = addon.getLocalizedString(20060)
        listitem = xbmcgui.ListItem(label=f"{addon.getLocalizedString(rail.label_id)} · {more_label}")
        listitem.setProperty("SpecialSort", "bottom")
        url = context.build_url(action="list", rail=rail.identifier, cursor=data["next_token"])
        items.append((url, listitem, True))

    if items:
        xbmcplugin.addDirectoryItems(context.handle, items)

    threshold = RAIL_COLD_THRESHOLD_MS if not metrics["cached"] else RAIL_WARM_THRESHOLD_MS
    if metrics["duration"] > threshold:
        log_warning(
            f"{rail.identifier} rail exceeded target {metrics['duration']:.2f} ms (threshold {threshold} ms)"
        )


def _render_search(context: PluginContext) -> None:
    addon = _addon()
    label = addon.getLocalizedString(20050)
    listitem = xbmcgui.ListItem(label=label)
    listitem.setArt({"icon": "DefaultAddonsSearch.png"})
    xbmcplugin.addDirectoryItem(
        context.handle,
        context.build_url(action="search"),
        listitem,
        True,
    )


def _render_diagnostics(context: PluginContext) -> None:
    addon = _addon()
    label = addon.getLocalizedString(21040)
    listitem = xbmcgui.ListItem(label=label)
    listitem.setProperty("SpecialSort", "bottom")
    xbmcplugin.addDirectoryItem(
        context.handle,
        context.build_url(action="diagnostics"),
        listitem,
        True,
    )


def detect_media_type(item: Dict[str, str]) -> str:
    media_type = item.get("type")
    if media_type:
        return media_type
    duration = item.get("duration")
    if duration and isinstance(duration, int) and duration > 3600:
        return "movie"
    return "episode"


def _is_cold_run(instrumentation: List[Dict[str, Any]]) -> bool:
    return any(not entry.get("cached") for entry in instrumentation)


def clear_home_cache() -> None:
    cache = get_cache()
    cache.clear_all()


def collect_home_metrics(force_refresh: bool = False) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    for rail in HOME_RAILS:
        _, rail_metrics = _load_rail_data(rail, force_refresh=force_refresh)
        metrics.append(rail_metrics)
    return metrics


def _load_rail_data(rail: RailDefinition, force_refresh: bool = False) -> Tuple[Dict[str, Any], Dict[str, float]]:
    addon = _addon()
    backend = get_backend()
    cache = get_cache()
    ttl_setting = addon.getSettingInt("cache_ttl") or CACHE_DEFAULT_TTL
    use_cache = addon.getSettingBool("use_cache") and not force_refresh
    cache_key = f"{CACHE_PREFIX}{rail.identifier}"

    start = time.perf_counter()
    cached = cache.get(cache_key, ttl_setting) if use_cache else None
    used_cache = cached is not None
    if used_cache:
        data = cached[0]
    else:
        page = backend.fetch_rail(rail.identifier, limit=rail.limit)
        data = {
            "items": page.items,
            "next_token": page.next_token,
        }
        if addon.getSettingBool("use_cache"):
            cache.set(cache_key, data, ttl_setting)
    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics = {"rail": rail.identifier, "duration": duration_ms, "cached": used_cache}
    return data, metrics
