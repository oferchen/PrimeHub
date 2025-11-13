import functools
import time
from collections import defaultdict
from typing import Any, Callable, Optional

try:
    import xbmc
except ImportError:  # pragma: no cover - development fallback
    xbmc = None

_LOG_LEVEL_INFO = 1
_LOG_LEVEL_WARNING = 2

_records = defaultdict(list)


def _log(message, level=_LOG_LEVEL_INFO):
    if xbmc:
        xbmc.log(message, level)
    else:  # pragma: no cover - development fallback
        print(f"[xbmc][{level}] {message}")


def timed(label, warn_threshold_ms=None):
    """Decorator that measures execution time and logs the result."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return measure(label, func, warn_threshold_ms, *args, **kwargs)

        return wrapper

    return decorator


def measure(label: str, func: Callable[..., Any], warn_threshold_ms: Optional[float] = None, *args, **kwargs):
    start = time.perf_counter()
    _log(f"[PrimeFlix] START {label}")
    try:
        return func(*args, **kwargs)
    finally:
        duration = (time.perf_counter() - start) * 1000.0
        _records[label].append(duration)
        if warn_threshold_ms and duration > warn_threshold_ms:
            _log(f"[PrimeFlix] WARNING {label} took {duration:.1f} ms", _LOG_LEVEL_WARNING)
        else:
            _log(f"[PrimeFlix] END {label}: {duration:.1f} ms")


def get_records():
    return {label: list(values) for label, values in _records.items()}


def clear_records():
    _records.clear()
