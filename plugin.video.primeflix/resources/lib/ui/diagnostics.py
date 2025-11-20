"""Diagnostics route displaying performance runs and backend strategy.

Triggered by the router's ``action=diagnostics`` path to help validate
preflight readiness, cache warmth, and backend selection for QA.
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - Kodi runtime
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
except ImportError:  # pragma: no cover - local dev fallback
    class _Addon:
        def __init__(self) -> None:
            self._settings = {
                "cache_ttl": "300",
                "use_cache": "true",
            }

        def getAddonInfo(self, key: str) -> str:
            if key == "name":
                return "PrimeFlix"
            return ""

        def getSetting(self, key: str) -> str:
            return self._settings.get(key, "")

        def getSettingInt(self, key: str) -> int:
            return int(self._settings.get(key, "0"))

        def getSettingBool(self, key: str) -> bool:
            return self._settings.get(key, "false").lower() == "true"

        def getLocalizedString(self, code: int) -> str:
            return str(code)

    class _Dialog:
        @staticmethod
        def notification(title: str, message: str, time: int = 3000) -> None:  # noqa: A003 - Kodi signature
            print(f"NOTIFY {title}: {message}")

    class _ListItem:
        def __init__(self, label: str = "") -> None:
            self.label = label

        def setInfo(self, info_type: str, info: dict) -> None:
            pass

    class _Plugin:
        def __init__(self) -> None:
            self.handle = 1

        @staticmethod
        def addDirectoryItem(handle: int, url: str, listitem: _ListItem, isFolder: bool = False) -> None:
            print(f"ADD {url} label={listitem.label}")

        @staticmethod
        def setContent(handle: int, content: str) -> None:
            print(f"SET CONTENT {content}")

    xbmcaddon = type("addon", (), {"Addon": _Addon})  # type: ignore
    xbmcgui = type("gui", (), {"Dialog": _Dialog, "ListItem": _ListItem})  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore

from ..backend.prime_api import BackendError, get_backend
from ..perf import log_duration
from ..preflight import PreflightError
from .home import (
    HOME_COLD_THRESHOLD_MS,
    HOME_WARM_THRESHOLD_MS,
    RAIL_COLD_THRESHOLD_MS,
    RAIL_WARM_THRESHOLD_MS,
    RailSnapshot,
    build_home_snapshot,
)

RUN_LABEL_ID = 30040
SLOW_LABEL_ID = 30041
BACKEND_LABEL_ID = 30042
STATE_WARM_ID = 30043
STATE_COLD_ID = 30044


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


def _state_label(addon, warm: bool) -> str:
    return addon.getLocalizedString(STATE_WARM_ID if warm else STATE_COLD_ID)


def _format_run_label(addon, index: int, total_ms: float, warm: bool) -> str:
    template = addon.getLocalizedString(RUN_LABEL_ID)
    state = _state_label(addon, warm)
    if "{time}" in template:
        return template.format(number=index, time=f"{total_ms:.2f}", state=state)
    return f"Run {index}: {total_ms:.2f} ms ({state})"


def _format_slow_label(addon, run_index: int, snapshot: RailSnapshot, warm: bool) -> str:
    rail_name = addon.getLocalizedString(snapshot.spec.label_id)
    template = addon.getLocalizedString(SLOW_LABEL_ID)
    state = _state_label(addon, warm)
    if "{time}" in template:
        return template.format(run=run_index, rail=rail_name, time=f"{snapshot.elapsed_ms:.2f}", state=state)
    return f"Run {run_index} [SLOW] {rail_name}: {snapshot.elapsed_ms:.2f} ms ({state})"


def show_results(context) -> None:
    addon = xbmcaddon.Addon()
    try:
        backend = get_backend()
    except (PreflightError, BackendError) as exc:
        xbmcgui.Dialog().notification(addon.getAddonInfo("name"), str(exc))
        return

    ttl = max(30, _get_setting_int(addon, "cache_ttl", 300))
    use_cache_setting = _get_setting_bool(addon, "use_cache", True)
    xbmcplugin.setContent(context.handle, "files")

    backend_label = addon.getLocalizedString(BACKEND_LABEL_ID) or "Backend"
    header_text = f"{backend.strategy_name} ({backend.backend_id})"
    header = xbmcgui.ListItem(label=f"{backend_label}: {header_text}")
    xbmcplugin.addDirectoryItem(context.handle, context.build_url(action="diagnostics"), header, isFolder=False)

    for iteration in range(3):
        force_refresh = iteration == 0 and use_cache_setting
        snapshots, metrics = build_home_snapshot(
            backend,
            use_cache=use_cache_setting,
            ttl=ttl,
            force_refresh=force_refresh,
        )
        warm = use_cache_setting and all(s.from_cache for s in snapshots)
        total_ms = metrics["total_ms"]
        label = _format_run_label(addon, iteration + 1, total_ms, warm)
        run_item = xbmcgui.ListItem(label=label)
        xbmcplugin.addDirectoryItem(context.handle, context.build_url(action="diagnostics"), run_item, isFolder=False)
        log_duration(
            f"Diagnostics run {iteration + 1}",
            total_ms,
            warm=warm,
            warm_threshold_ms=HOME_WARM_THRESHOLD_MS,
            cold_threshold_ms=HOME_COLD_THRESHOLD_MS,
        )

        for snapshot in snapshots:
            rail_threshold = RAIL_WARM_THRESHOLD_MS if snapshot.from_cache else RAIL_COLD_THRESHOLD_MS
            if snapshot.elapsed_ms > rail_threshold:
                slow_label = _format_slow_label(addon, iteration + 1, snapshot, snapshot.from_cache)
                slow_item = xbmcgui.ListItem(label=slow_label)
                xbmcplugin.addDirectoryItem(
                    context.handle,
                    context.build_url(action="diagnostics"),
                    slow_item,
                    isFolder=False,
                )
            log_duration(
                f"Diagnostics rail {snapshot.spec.identifier} (run {iteration + 1})",
                snapshot.elapsed_ms,
                warm=snapshot.from_cache,
                warm_threshold_ms=RAIL_WARM_THRESHOLD_MS,
                cold_threshold_ms=RAIL_COLD_THRESHOLD_MS,
            )
