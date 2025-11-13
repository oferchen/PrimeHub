"""Diagnostics route for measuring PrimeFlix performance."""
from __future__ import annotations

import time
from typing import List

try:  # pragma: no cover - Kodi runtime
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    class _Addon:
        def getLocalizedString(self, code: int) -> str:
            return str(code)

    class _GUI:
        class ListItem:
            def __init__(self, label: str = ""):
                self.label = label

            def setProperty(self, key: str, value: str) -> None:
                pass

    class _Plugin:
        @staticmethod
        def addDirectoryItem(handle, url, listitem, isFolder=False):
            print(f"ADD {url}: {listitem.label}")

        @staticmethod
        def setContent(handle, content):
            print(f"SET CONTENT {content}")

    xbmcaddon = type("addon", (), {"Addon": _Addon})  # type: ignore
    xbmcgui = _GUI  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore

from ..backend.prime_api import get_backend
from ..perf import log_info
from ..preflight import ensure_ready_or_raise
from ..router import PluginContext
from . import home

RUNS = 3


def show_results(context: PluginContext) -> None:
    addon = xbmcaddon.Addon()
    ensure_ready_or_raise()
    backend = get_backend()
    summary = backend.get_backend_summary()
    xbmcplugin.setContent(context.handle, "files")

    title_item = xbmcgui.ListItem(label=addon.getLocalizedString(21120))
    xbmcplugin.addDirectoryItem(context.handle, context.build_url(action="diagnostics"), title_item, False)

    header = addon.getLocalizedString(21050).format(
        strategy=summary.get("strategy", "unknown"), addon=summary.get("id", "n/a")
    )
    xbmcplugin.addDirectoryItem(
        context.handle, context.build_url(action="diagnostics"), xbmcgui.ListItem(label=header), False
    )

    durations: List[float] = []
    for index in range(1, RUNS + 1):
        cold_run = index == 1
        if cold_run:
            home.clear_home_cache()
        start = time.perf_counter()
        metrics = home.collect_home_metrics(force_refresh=cold_run)
        duration_ms = (time.perf_counter() - start) * 1000.0
        durations.append(duration_ms)
        state = "cold" if cold_run else "warm"
        threshold = home.COLD_THRESHOLD_MS if cold_run else home.WARM_THRESHOLD_MS
        label_id = 21060
        if duration_ms > threshold:
            label = addon.getLocalizedString(21130).format(rail="Home", duration=f"{duration_ms:.0f}", state=state)
        else:
            label = addon.getLocalizedString(label_id).format(index=index, duration=f"{duration_ms:.0f}", state=state)
        xbmcplugin.addDirectoryItem(
            context.handle, context.build_url(action="diagnostics"), xbmcgui.ListItem(label=label), False
        )
        _emit_rail_metrics(context, metrics, addon, cold_run)

    log_info(
        "Diagnostics completed: "
        + ", ".join(f"run {idx + 1}={durations[idx]:.2f}ms" for idx in range(len(durations)))
    )


def _emit_rail_metrics(context: PluginContext, metrics: List[dict], addon, cold_run: bool) -> None:
    for entry in metrics:
        threshold = home.RAIL_COLD_THRESHOLD_MS if cold_run or not entry.get("cached") else home.RAIL_WARM_THRESHOLD_MS
        duration = entry.get("duration", 0.0)
        rail_name = entry.get("rail", "?")
        state = "cold" if cold_run or not entry.get("cached") else "warm"
        if duration > threshold:
            label = addon.getLocalizedString(21130).format(rail=rail_name.title(), duration=f"{duration:.0f}", state=state)
        else:
            label = addon.getLocalizedString(21070).format(rail=rail_name.title(), duration=f"{duration:.0f}", state=state)
        xbmcplugin.addDirectoryItem(
            context.handle, context.build_url(action="diagnostics"), xbmcgui.ListItem(label=label), False
        )
