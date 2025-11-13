"""Performance utilities for logging execution time."""
from __future__ import annotations

import functools
import time
from typing import Callable, Optional

try:  # pragma: no cover - Kodi runtime
    import xbmc
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


LOG_PREFIX = "[PrimeFlix]"


def _log(level: int, message: str) -> None:
    xbmc.log(f"{LOG_PREFIX} {message}", level)


def timed(label: str, warn_threshold_ms: Optional[float] = None) -> Callable:
    """Decorate *func* so that runtime is logged with *label*."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            _log(xbmc.LOGDEBUG, f"{label} started")
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            level = xbmc.LOGDEBUG
            if warn_threshold_ms is not None and elapsed_ms > warn_threshold_ms:
                level = xbmc.LOGWARNING
            _log(level, f"{label} finished in {elapsed_ms:.2f} ms")
            return result

        return wrapper

    return decorator


def log_warning(message: str) -> None:
    _log(xbmc.LOGWARNING, message)


def log_info(message: str) -> None:
    _log(xbmc.LOGINFO, message)


def log_debug(message: str) -> None:
    _log(xbmc.LOGDEBUG, message)
