"""Diagnostics route to measure performance and backend strategy.

Triggered via ``action=diagnostics`` from :mod:`resources.lib.router`, this
module warms/cools cache runs to gauge timing, checks the current backend
strategy, and renders human-readable results for troubleshooting.
"""
from __future__ import annotations

import time
from typing import List, Tuple

try:  # pragma: no cover - Kodi runtime
    import xbmcplugin
    import xbmcgui
    import xbmcaddon
except ImportError:  # pragma: no cover - local dev fallback
    class _PluginStub:
        handle = 1

        @staticmethod
        def addDirectoryItems(handle, items):  # type: ignore[override]
            for url, listitem, isFolder in items:
                print(f"ADD: {listitem.getLabel()} -> {url} ({'folder' if isFolder else 'item'})")

        @staticmethod
        def addDirectoryItem(handle, url, listitem, isFolder=False):
            print(f"ADD: {listitem.getLabel()} -> {url} ({'folder' if isFolder else 'item'})")

        @staticmethod
        def setContent(handle, content):
            print(f"SET CONTENT: {content}")

    class _ListItemStub:
        def __init__(self, label: str):
            self._label = label

        def getLabel(self) -> str:
            return self._label

    class _AddonStub:
        @staticmethod
        def getLocalizedString(code: int) -> str:
            return str(code)

    xbmcplugin = _PluginStub()  # type: ignore
    xbmcgui = type("gui", (), {"ListItem": _ListItemStub})  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": lambda *args, **kwargs: _AddonStub()})  # type: ignore

from ..backend.prime_api import (
    HOME_COLD_THRESHOLD_MS,
    HOME_WARM_THRESHOLD_MS,
    RAIL_COLD_THRESHOLD_MS,
    BackendError,
    get_backend,
)
from ..cache import get_cache
from ..perf import log_duration, timed
from ..preflight import ensure_ready_or_raise
from .listing import RAIL_DEFINITIONS

HOME_CONTENT_TYPE = "videos"
WARM_THRESHOLD_MS = 150.0


def _addon():
    return xbmcaddon.Addon()


def _bool_setting(addon: object, key: str, default: bool) -> bool:
    try:
        return addon.getSettingBool(key)
    except Exception:
        try:
            return str(addon.getSetting(key)).lower() == "true"
        except Exception:
            return default


def _int_setting(addon: object, key: str, default: int) -> int:
    try:
        return addon.getSettingInt(key)
    except Exception:
        try:
            return int(addon.getSetting(key))
        except Exception:
            return default


def _thresholds(warm: bool) -> Tuple[float, float]:
    return (None, WARM_THRESHOLD_MS) if warm else (RAIL_COLD_THRESHOLD_MS, None)


@timed("diagnostics.show_results")
def show_results(context) -> None:
    ensure_ready_or_raise()
    addon = _addon()
    backend = get_backend()
    cache = get_cache()
    xbmcplugin.setContent(context.handle, HOME_CONTENT_TYPE)

    ttl = _int_setting(addon, "cache_ttl", 300)
    use_cache = _bool_setting(addon, "use_cache", True)

    runs: List[Tuple[str, bool, float]] = []
    for run in range(1, 4):
        force_refresh = run == 1
        if force_refresh:
            cache.clear_prefix("home::")
        start = time.perf_counter()
        try:
            _rails, from_cache = backend.get_home_rails(ttl, use_cache, force_refresh=force_refresh)
        except BackendError as exc:
            _notify(addon, str(exc))
            return
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        runs.append(("cold" if force_refresh else "warm", from_cache, elapsed_ms))
        log_duration(
            "diagnostics:home",
            elapsed_ms,
            warm=(run > 1 or from_cache),
            warm_threshold_ms=HOME_WARM_THRESHOLD_MS,
            cold_threshold_ms=HOME_COLD_THRESHOLD_MS,
            details=f"run={run}",
        )

    rail_id = str(RAIL_DEFINITIONS[0]["id"]) if RAIL_DEFINITIONS else "movies"
    start = time.perf_counter()
    try:
        data, from_cache = backend.get_rail(rail_id, None, 10, ttl, use_cache, force_refresh=True)
    except BackendError:
        data, from_cache = None, False
    rail_elapsed_ms = (time.perf_counter() - start) * 1000.0
    log_duration(
        f"diagnostics:rail:{rail_id}",
        rail_elapsed_ms,
        warm=from_cache,
        warm_threshold_ms=WARM_THRESHOLD_MS,
        cold_threshold_ms=RAIL_COLD_THRESHOLD_MS,
    )

    items = []
    for idx, (state, _cached, elapsed_ms) in enumerate(runs, start=1):
        cold_threshold, warm_threshold = _thresholds(state != "cold")
        threshold = warm_threshold if state != "cold" else cold_threshold
        label_template = addon.getLocalizedString(30040)
        display_state = addon.getLocalizedString(30044 if state == "cold" else 30043)
        title = label_template.format(number=idx, time=int(elapsed_ms), state=display_state)
        if threshold and elapsed_ms > threshold:
            slow_template = addon.getLocalizedString(30041)
            title = slow_template.format(run=idx, rail="home", time=int(elapsed_ms), state=display_state)
        listitem = xbmcgui.ListItem(title)
        items.append((context.build_url(), listitem, False))

    if data is not None:
        display_state = addon.getLocalizedString(30044)
        threshold_exceeded = rail_elapsed_ms > RAIL_COLD_THRESHOLD_MS
        if threshold_exceeded:
            slow_template = addon.getLocalizedString(30041)
            rail_title = slow_template.format(
                run=1,
                rail=rail_id,
                time=int(rail_elapsed_ms),
                state=display_state,
            )
        else:
            label_template = addon.getLocalizedString(30040)
            rail_title = label_template.format(number=1, time=int(rail_elapsed_ms), state=display_state)
        items.append((context.build_url(), xbmcgui.ListItem(rail_title), False))

    strategy_label = addon.getLocalizedString(30042)
    strategy_value = backend.strategy_name
    strategy_item = xbmcgui.ListItem(f"{strategy_label}: {strategy_value}")
    items.append((context.build_url(), strategy_item, False))

    if hasattr(xbmcplugin, "addDirectoryItems"):
        xbmcplugin.addDirectoryItems(context.handle, items)
    else:  # pragma: no cover - stub fallback
        for url, listitem, isFolder in items:
            xbmcplugin.addDirectoryItem(context.handle, url, listitem, isFolder=isFolder)


def _notify(addon: object, message: str) -> None:
    try:
        dialog = xbmcgui.Dialog()
        dialog.notification(addon.getAddonInfo("name"), message)  # type: ignore[attr-defined]
    except Exception:
        pass
