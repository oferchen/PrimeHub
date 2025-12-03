"""Diagnostics route for validating backend strategy and performance.

Invoked from :mod:`resources.lib.router` to run repeated home builds and show
timing/strategy information in a user-visible listing.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

try:  # pragma: no cover - Kodi runtime
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    class _ListItem:
        def __init__(self, label=""):
            self.label = label

        def setInfo(self, type_: str, info: Dict[str, Any]):
            self.info = (type_, info)

    class _Plugin:
        @staticmethod
        def addDirectoryItems(handle, items):
            print(f"ADD {len(items)} items")

        @staticmethod
        def setContent(handle, content):
            print(f"SET CONTENT {content}")

    xbmcgui = type("xbmcgui", (), {"ListItem": _ListItem, "Dialog": lambda: None})  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore
    xbmcaddon = type(
        "addon",
        (),
        {
            "Addon": lambda *a, **k: type(
                "AddonStub",
                (),
                {
                    "getSettingBool": lambda self, k: False,
                    "getSettingInt": lambda self, k: 0,
                    "getSetting": lambda self, k: 0,
                    "getLocalizedString": lambda self, k: "",
                },
            )(),
        },
    )  # type: ignore

from ..backend import get_backend
from ..cache import get_cache
from ..perf import log_duration, timed
from ..preflight import ensure_ready_or_raise
from .home import fetch_home_rails


@timed("diagnostics")
def show_results(context) -> None:
    backend_id = ensure_ready_or_raise()
    backend = get_backend(backend_id)
    cache = get_cache()
    addon = xbmcaddon.Addon()

    results: List[Dict[str, Any]] = []

    # Clear cache for home rails once before starting to ensure the first run is cold
    cache.clear_prefix("home")

    for idx in range(3):
        warm = idx > 0
        start = time.perf_counter()

        fetch_home_rails(addon, cache, backend_id)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        log_duration("home", elapsed_ms, warm=warm, warm_threshold_ms=300.0, cold_threshold_ms=1500.0)
        results.append({
            "label": f"Run {idx + 1}: {elapsed_ms:.0f} ms ({'warm' if warm else 'cold'}, strategy={backend.strategy})",
            "elapsed": elapsed_ms,
        })

    _render_results(context, results)


def _render_results(context, results: List[Dict[str, Any]]) -> None:
    xbmcplugin.setContent(context.handle, "videos")
    items = []
    for result in results:
        li = xbmcgui.ListItem(label=result["label"])
        li.setInfo("video", {"title": result["label"], "plot": result["label"]})
        items.append(("", li, False))
    xbmcplugin.addDirectoryItems(context.handle, items)

