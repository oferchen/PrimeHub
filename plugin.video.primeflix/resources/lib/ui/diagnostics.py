from __future__ import annotations

import sys
import time
from typing import Dict, List

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - development fallback
    xbmc = None
    xbmcaddon = None
    xbmcgui = None
    xbmcplugin = None

from .. import cache
from ..perf import clear_records, get_records
from ..backend import prime_api
from . import home


def show_results(handle: int) -> None:
    backend = prime_api.get_backend()
    if not backend or not xbmcgui or not xbmcplugin:
        return

    addon = xbmcaddon.Addon() if xbmcaddon else None
    use_cache = home._get_setting_bool(addon, "use_cache", True)  # type: ignore[attr-defined]
    cache_ttl = home._get_setting_int(addon, "cache_ttl", home.DEFAULT_CACHE_TTL)  # type: ignore[attr-defined]

    if use_cache:
        cache.clear()

    runs: List[Dict] = []
    for index in range(3):
        clear_records()
        start = time.perf_counter()
        _, _ = home.build_home_snapshot(addon, backend, use_cache, cache_ttl)
        duration = (time.perf_counter() - start) * 1000.0
        records = get_records()
        rail_metrics = _extract_rail_metrics(records)
        run_kind = "cold" if index == 0 else ("warm" if use_cache else "cold")
        runs.append({
            "index": index + 1,
            "duration": duration,
            "kind": run_kind,
            "rail_metrics": rail_metrics,
        })

    xbmcplugin.setContent(handle, "files")
    xbmcplugin.setPluginCategory(handle, "Diagnostics")

    backend_info = backend.get_backend_info()
    info_label = f"Backend: {backend_info.get('addon_id')} ({backend_info.get('strategy')})"
    diagnostics_url = f"{sys.argv[0]}?action=diagnostics"
    listitem = xbmcgui.ListItem(label=info_label)
    xbmcplugin.addDirectoryItem(handle, diagnostics_url, listitem, isFolder=False)

    for run in runs:
        slow = any(metric["slow"] for metric in run["rail_metrics"])
        label = f"Run {run['index']}: {run['duration']:.1f} ms ({run['kind']})"
        if slow:
            label = "[SLOW] " + label
        plot = _format_metrics(run["rail_metrics"])
        listitem = xbmcgui.ListItem(label=label)
        listitem.setInfo("video", {"title": label, "plot": plot})
        xbmcplugin.addDirectoryItem(handle, diagnostics_url, listitem, isFolder=False)


def _extract_rail_metrics(records: Dict[str, List[float]]) -> List[Dict]:
    metrics = []
    for label, durations in records.items():
        if not durations or not label.startswith("rail:"):
            continue
        duration = durations[-1]
        name = label.split(":", 1)[1]
        if name.endswith(":cache"):
            threshold = home.RAIL_WARN_WARM_MS
            kind = "warm"
            name = name[:-6]
        else:
            threshold = home.RAIL_WARN_COLD_MS
            kind = "cold"
        slow = duration > threshold
        metrics.append({
            "name": name,
            "duration": duration,
            "slow": slow,
            "kind": kind,
        })
    metrics.sort(key=lambda item: item["name"])
    return metrics


def _format_metrics(metrics: List[Dict]) -> str:
    lines = []
    for metric in metrics:
        prefix = "[SLOW] " if metric["slow"] else ""
        lines.append(f"{prefix}{metric['name']} ({metric['kind']}): {metric['duration']:.1f} ms")
    return "\n".join(lines) if lines else "No rail metrics captured."
