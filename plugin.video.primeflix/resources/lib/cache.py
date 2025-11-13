import json
import os
import time
from contextlib import suppress

try:
    import xbmc
    import xbmcaddon
    import xbmcvfs
except ImportError:  # pragma: no cover - development fallback
    xbmc = None
    xbmcaddon = None
    xbmcvfs = None


class JSONCache:
    """Simple TTL JSON cache stored under the add-on profile directory."""

    def __init__(self):
        self._addon_id = None
        self._base_dir = None
        self._ensure_dirs()

    def _ensure_dirs(self):
        addon_id = self._addon_id or self._get_addon_id()
        if not addon_id:
            return
        path = self._translate_path(f"special://profile/addon_data/{addon_id}/cache")
        self._base_dir = path
        if xbmcvfs:
            if not xbmcvfs.exists(path):
                xbmcvfs.mkdirs(path)
        else:  # pragma: no cover - development fallback
            os.makedirs(path, exist_ok=True)

    def _get_addon_id(self):
        if self._addon_id:
            return self._addon_id
        if xbmcaddon:
            self._addon_id = xbmcaddon.Addon().getAddonInfo("id")
        else:  # pragma: no cover - development fallback
            self._addon_id = "plugin.video.primeflix"
        return self._addon_id

    def _translate_path(self, path):
        if xbmcvfs:
            return xbmcvfs.translatePath(path)
        if xbmc:  # pragma: no cover - legacy fallback
            return xbmc.translatePath(path)
        return os.path.expandvars(path.replace("special://profile", os.path.join(os.path.expanduser("~"), ".kodi")))

    def _file_path(self, key):
        if not self._base_dir:
            self._ensure_dirs()
        safe_key = key.replace("/", "_")
        return os.path.join(self._base_dir, f"{safe_key}.json")

    def get(self, key):
        path = self._file_path(key)
        if xbmcvfs and xbmcvfs.exists(path):
            with suppress(Exception):
                with xbmcvfs.File(path, "r") as fh:  # type: ignore[attr-defined]
                    raw = fh.read()
                data = json.loads(raw)
                if data.get("expires", 0) > time.time():
                    return data.get("value")
                self.delete(key)
        elif os.path.exists(path):  # pragma: no cover - development fallback
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("expires", 0) > time.time():
                return data.get("value")
            self.delete(key)
        return None

    def set(self, key, value, ttl_seconds=300):
        if ttl_seconds <= 0:
            self.delete(key)
            return
        payload = {"value": value, "expires": time.time() + ttl_seconds}
        path = self._file_path(key)
        if xbmcvfs:
            with xbmcvfs.File(path, "w") as fh:  # type: ignore[attr-defined]
                fh.write(json.dumps(payload))
        else:  # pragma: no cover - development fallback
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)

    def delete(self, key):
        path = self._file_path(key)
        if xbmcvfs and xbmcvfs.exists(path):
            xbmcvfs.delete(path)
        elif os.path.exists(path):  # pragma: no cover - development fallback
            os.remove(path)

    def clear(self):
        if not self._base_dir:
            self._ensure_dirs()
        if not self._base_dir:
            return
        if xbmcvfs:
            dirs, files = xbmcvfs.listdir(self._base_dir)
            for file_name in files:
                xbmcvfs.delete(os.path.join(self._base_dir, file_name))
        else:  # pragma: no cover - development fallback
            for file_name in os.listdir(self._base_dir):
                os.remove(os.path.join(self._base_dir, file_name))


CACHE = JSONCache()


def get(key):
    return CACHE.get(key)


def set(key, value, ttl_seconds=300):
    CACHE.set(key, value, ttl_seconds)


def clear():
    CACHE.clear()
