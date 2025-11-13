"""Simple TTL cache backed by JSON files."""
from __future__ import annotations

import json
import os
import threading
import time
from hashlib import sha1
from typing import Any, Optional, Tuple

try:  # pragma: no cover - Kodi runtime
    import xbmcvfs
    import xbmcaddon
except ImportError:  # pragma: no cover - local dev fallback
    class _VFSStub:
        def exists(self, path: str) -> bool:
            return os.path.exists(path)

        def mkdirs(self, path: str) -> None:
            os.makedirs(path, exist_ok=True)

        def translatePath(self, path: str) -> str:
            return path

        def delete(self, path: str) -> None:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

        def open(self, path: str, mode: str = "r"):
            return open(path, mode)

    class _AddonStub:
        def getAddonInfo(self, key: str) -> str:
            if key == "id":
                return "plugin.video.primeflix"
            if key == "profile":
                return os.path.join(os.getcwd(), "profile")
            if key == "path":
                return os.getcwd()
            raise KeyError(key)

    xbmcvfs = _VFSStub()  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": lambda *args, **kwargs: _AddonStub()})  # type: ignore


class Cache:
    """Thread-safe TTL cache stored inside Kodi profile."""

    def __init__(self) -> None:
        addon = xbmcaddon.Addon()
        addon_profile = addon.getAddonInfo("profile")
        base_path = addon_profile
        translate = getattr(xbmcvfs, "translatePath", None)
        if callable(translate):
            base_path = translate(addon_profile)
        base_path = os.path.join(base_path, "cache")
        if not xbmcvfs.exists(base_path):
            xbmcvfs.mkdirs(base_path)
        self._base_path = base_path
        self._lock = threading.Lock()

    def _filepath(self, key: str) -> str:
        digest = sha1(key.encode("utf-8")).hexdigest()
        return os.path.join(self._base_path, f"{digest}.json")

    def get(self, key: str, ttl_seconds: Optional[int] = None) -> Optional[Tuple[Any, float]]:
        path = self._filepath(key)
        if not xbmcvfs.exists(path):
            return None
        with self._lock:
            try:
                with xbmcvfs.open(path, "r") as stream:  # type: ignore[arg-type]
                    payload = json.load(stream)
            except Exception:
                self.delete(key)
                return None
        timestamp = payload.get("timestamp", 0)
        if ttl_seconds is not None and (time.time() - timestamp) > ttl_seconds:
            self.delete(key)
            return None
        return payload.get("data"), timestamp

    def set(self, key: str, data: Any, ttl_seconds: int) -> None:
        path = self._filepath(key)
        payload = {"timestamp": time.time(), "ttl": ttl_seconds, "key": key, "data": data}
        with self._lock:
            with xbmcvfs.open(path, "w") as stream:  # type: ignore[arg-type]
                json.dump(payload, stream)

    def delete(self, key: str) -> None:
        path = self._filepath(key)
        if xbmcvfs.exists(path):
            try:
                xbmcvfs.delete(path)
            except AttributeError:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass

    def clear_prefix(self, prefix: str) -> None:
        for filename in os.listdir(self._base_path):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self._base_path, filename)
            try:
                with xbmcvfs.open(path, "r") as stream:  # type: ignore[arg-type]
                    payload = json.load(stream)
                key = payload.get("key")
            except Exception:
                key = None
            if key is None or not str(key).startswith(prefix):
                continue
            self.delete(str(key))

    def clear_all(self) -> None:
        if not xbmcvfs.exists(self._base_path):
            try:
                xbmcvfs.mkdirs(self._base_path)
            except AttributeError:
                os.makedirs(self._base_path, exist_ok=True)
            return
        for filename in os.listdir(self._base_path):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self._base_path, filename)
            try:
                xbmcvfs.delete(path)
            except AttributeError:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    continue


_cache_instance: Optional[Cache] = None


def get_cache() -> Cache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = Cache()
    return _cache_instance
