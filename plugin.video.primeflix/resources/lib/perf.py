"""Performance utilities for logging execution time.

The timing helpers in this module are used by routing and UI layers to keep
the add-on fast without overwhelming logs. Logging honours the
``perf_logging`` setting so users can opt into verbose timing traces while
always emitting warnings when thresholds are exceeded.
"""
from __future__ import annotations

import functools
import time
from typing import Callable, Optional

try:  # pragma: no cover - Kodi runtime
    import xbmc
    import xbmcaddon
except ImportError:  # pragma: no cover - local dev fallback
    class _XBMCStub:
        LOGDEBUG = 0
        LOGINFO = 1
        LOGWARNING = 2
        LOGERROR = 3

        @staticmethod
        def log(message: str, level: int = 0) -> None:
            print(f"[xbmc:{level}] {message}")

    xbmc = _XBMCStub()  # type: ignore
    xbmcaddon = type(  # type: ignore
        "addon",
        (),
        {
            "Addon": lambda *args, **kwargs: type(
                "AddonStub",
                (),
                {
                    "getSetting": staticmethod(lambda key: "false"),
                    "getSettingBool": staticmethod(lambda key: False),
                },
            )(),
        },
    )


LOG_PREFIX = "[PrimeFlix]"
_PERF_SETTING_ID = "perf_logging"
_perf_enabled_cache: Optional[bool] = None


def _log(level: int, message: str) -> None:
    xbmc.log(f"{LOG_PREFIX} {message}", level)


def is_perf_logging_enabled() -> bool:
    """Return whether verbose performance logging is enabled by the user."""

    global _perf_enabled_cache
    if _perf_enabled_cache is not None:
        return _perf_enabled_cache
    try:
        addon = xbmcaddon.Addon()
        try:
            enabled = addon.getSettingBool(_PERF_SETTING_ID)
        except AttributeError:
            enabled = str(addon.getSetting(_PERF_SETTING_ID)).lower() == "true"
    except Exception:
        enabled = False
    _perf_enabled_cache = bool(enabled)
    return _perf_enabled_cache


def timed(label: str, warn_threshold_ms: Optional[float] = None) -> Callable:
    """Decorate *func* so that runtime is logged with *label*."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logging_enabled = is_perf_logging_enabled()
            if not logging_enabled and warn_threshold_ms is None:
                return func(*args, **kwargs)
            start = time.perf_counter()
            if logging_enabled:
                _log(xbmc.LOGDEBUG, f"{label} started")
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if warn_threshold_ms is not None and elapsed_ms > warn_threshold_ms:
                _log(xbmc.LOGWARNING, f"{label} finished in {elapsed_ms:.2f} ms")
            elif logging_enabled:
                _log(xbmc.LOGDEBUG, f"{label} finished in {elapsed_ms:.2f} ms")
            return result

        return wrapper

    return decorator


def log_warning(message: str) -> None:
    _log(xbmc.LOGWARNING, message)


def log_info(message: str) -> None:
    _log(xbmc.LOGINFO, message)


def log_debug(message: str) -> None:
    _log(xbmc.LOGDEBUG, message)


def log_duration(
    label: str,
    elapsed_ms: float,
    *,
    warm: Optional[bool] = None,
    warm_threshold_ms: Optional[float] = None,
    cold_threshold_ms: Optional[float] = None,
    details: str = "",
) -> None:
    """Log elapsed time with threshold awareness.

    Warnings are always emitted when thresholds are exceeded. Informational
    messages respect the ``perf_logging`` setting.
    """

    suffix = f" {details}" if details else ""
    state_label = "warm" if warm else "cold"
    threshold = warm_threshold_ms if warm else cold_threshold_ms
    if threshold is not None and elapsed_ms > threshold:
        log_warning(
            f"{label} exceeded target ({state_label}): {elapsed_ms:.2f} ms (threshold {threshold:.0f} ms){suffix}"
        )
    elif is_perf_logging_enabled():
        log_info(f"{label} completed in {elapsed_ms:.2f} ms ({state_label}){suffix}")
