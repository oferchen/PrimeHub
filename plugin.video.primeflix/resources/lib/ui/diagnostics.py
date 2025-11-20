"""Diagnostics route exposing strategy and timing information.

Called from :mod:`resources.lib.router` for ``action=diagnostics``. Runs rail
fetches under cold/warm conditions and surfaces backend strategy selection to
the user.
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

from ..backend.prime_api import RAIL_COLD_THRESHOLD_MS, BackendError, get_backend
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

    rail_id = str(RAIL_DEFINITIONS[0]["id"]) if RAIL_DEFINITIONS else "movies"
    runs: List[Tuple[str, bool, float]] = []
    for run in range(1, 4):
        if run == 1:
            cache.clear_prefix("rail::")
            force_refresh = True
        else:
            force_refresh = False
        start = time.perf_counter()
        try:
            data, from_cache = backend.get_rail(rail_id, None, 10, ttl, use_cache, force_refresh=force_refresh)
        except BackendError:
            break
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        runs.append(("cold" if run == 1 else "warm", from_cache, elapsed_ms))
        log_duration(
            f"diagnostics:rail:{rail_id}",
            elapsed_ms,
            warm=(run > 1 or from_cache),
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
            title = slow_template.format(run=idx, rail=rail_id, time=int(elapsed_ms), state=display_state)
        listitem = xbmcgui.ListItem(title)
        items.append((context.build_url(), listitem, False))

    strategy_label = addon.getLocalizedString(30042)
    strategy_value = backend.strategy_name
    strategy_item = xbmcgui.ListItem(f"{strategy_label}: {strategy_value}")
    items.append((context.build_url(), strategy_item, False))

    if hasattr(xbmcplugin, "addDirectoryItems"):
        xbmcplugin.addDirectoryItems(context.handle, items)
    else:  # pragma: no cover - stub fallback
        for url, listitem, isFolder in items:
            xbmcplugin.addDirectoryItem(context.handle, url, listitem, isFolder=isFolder)
