"""Backend bridge that reuses an existing Prime Video add-on.

The PrimeFlix UI never talks to Prime Video directly. Instead, this module
binds to an installed Prime Video add-on (such as Amazon VOD) using two
strategies:

* **Direct import**: load the backend's Python modules and call helper
  functions when available.
* **Plugin/JSON-RPC**: invoke the backend through ``Addons.ExecuteAddon`` and
  parse the returned JSON payload.

All public functions raise :class:`BackendUnavailable` when the backend cannot
be reached and :class:`BackendError` for other failures.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

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

        @staticmethod
        def executeJSONRPC(payload: str) -> str:
            return json.dumps({"result": {"value": None}})

    xbmc = _XBMCStub()  # type: ignore
    xbmcaddon = type(  # type: ignore
        "addon",
        (),
        {"Addon": lambda addon_id=None: type("AddonStub", (), {"getAddonInfo": lambda self, k: os.getcwd()})()},
    )

LOG_PREFIX = "[PrimeFlix-backend]"
BACKEND_CANDIDATES = (
    "plugin.video.amazon-test",
    "plugin.video.amazonprime",
    "plugin.video.amazonvod",
    "plugin.video.amazon",
    "plugin.video.primevideo",
)


class BackendUnavailable(RuntimeError):
    """Raised when the Prime backend cannot be reached."""


class BackendError(RuntimeError):
    """Raised when the Prime backend returns an unexpected response."""


@dataclass
class Playable:
    url: str
    manifest_type: str
    license_key: Optional[str]
    headers: Dict[str, str]
    metadata: Dict[str, Any]


class _DirectStrategy:
    """Attempt to call backend helpers via direct import."""

    def __init__(self, addon_id: str) -> None:
        self.addon_id = addon_id
        self._module = self._load_module(addon_id)

    @staticmethod
    def _load_module(addon_id: str):
        addon = xbmcaddon.Addon(addon_id)
        addon_path = addon.getAddonInfo("path")
        candidates = (
            os.path.join(addon_path, "resources", "lib", "api.py"),
            os.path.join(addon_path, "resources", "lib", "backend.py"),
        )
        for candidate in candidates:
            if os.path.exists(candidate):
                spec = importlib.util.spec_from_file_location("prime_backend", candidate)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)  # type: ignore[arg-type]
                    return module
        raise BackendUnavailable("Direct import not supported by backend")

    def _call(self, func_name: str, *args, **kwargs):
        func = getattr(self._module, func_name, None)
        if callable(func):
            return func(*args, **kwargs)
        raise BackendUnavailable("Backend helper not present")

    def get_home_rails(self) -> List[Dict[str, Any]]:
        return self._call("get_home_rails")

    def get_rail_items(self, rail_id: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        data = self._call("get_rail_items", rail_id, cursor)
        if isinstance(data, tuple) and len(data) == 2:
            return data
        return data, None  # type: ignore[misc]

    def get_playable(self, asin: str) -> Playable:
        payload = self._call("get_playable", asin)
        return normalize_playable(payload)

    def search(self, query: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        data = self._call("search", query, cursor)
        if isinstance(data, tuple) and len(data) == 2:
            return data
        return data, None  # type: ignore[misc]

    def get_region_info(self) -> Dict[str, Any]:
        return self._call("get_region_info") or {}

    def is_drm_ready(self) -> Optional[bool]:
        try:
            return bool(self._call("is_drm_ready"))
        except BackendUnavailable:
            return None


class _RpcStrategy:
    """Fallback strategy that calls the backend through JSON-RPC."""

    def __init__(self, addon_id: str) -> None:
        self.addon_id = addon_id

    def _execute(self, action: str, **params) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "Addons.ExecuteAddon",
            "params": {"addonid": self.addon_id, "params": {"action": action, **{k: v for k, v in params.items() if v is not None}}},
        }
        response = json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
        value = response.get("result", {}).get("value")
        if value is None:
            raise BackendUnavailable("Backend did not return a response")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return value
        return value

    def get_home_rails(self) -> List[Dict[str, Any]]:
        data = self._execute("home_rails")
        if not isinstance(data, list):
            raise BackendError("Unexpected home rails format")
        return data

    def get_rail_items(self, rail_id: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        data = self._execute("rail_items", rail=rail_id, cursor=cursor)
        if isinstance(data, dict):
            items = data.get("items") or []
            next_cursor = data.get("next")
            return items, next_cursor
        if isinstance(data, list):
            return data, None
        raise BackendError("Unexpected rail items format")

    def get_playable(self, asin: str) -> Playable:
        payload = self._execute("play", asin=asin)
        return normalize_playable(payload)

    def search(self, query: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        data = self._execute("search", query=query, cursor=cursor)
        if isinstance(data, dict):
            return data.get("items", []), data.get("next")
        if isinstance(data, list):
            return data, None
        raise BackendError("Unexpected search payload")

    def get_region_info(self) -> Dict[str, Any]:
        data = self._execute("region")
        return data if isinstance(data, dict) else {}

    def is_drm_ready(self) -> Optional[bool]:
        try:
            data = self._execute("is_drm_ready")
        except BackendUnavailable:
            return None
        if isinstance(data, bool):
            return data
        if isinstance(data, dict) and "ready" in data:
            ready = data.get("ready")
            if isinstance(ready, bool):
                return ready
        return None


def discover_backend() -> Optional[str]:
    for candidate in BACKEND_CANDIDATES:
        try:
            xbmcaddon.Addon(candidate)
            return candidate
        except Exception:
            continue
    return None


def _log(level: int, message: str) -> None:
    xbmc.log(f"{LOG_PREFIX} {message}", level)


class PrimeAPI:
    """Facade that selects the best available backend strategy."""

    def __init__(self, backend_id: Optional[str] = None) -> None:
        self.backend_id = backend_id or discover_backend()
        if not self.backend_id:
            raise BackendUnavailable("No compatible backend installed")
        self._strategy_label = "rpc"
        try:
            self._strategy = _DirectStrategy(self.backend_id)
            self._strategy_label = "direct"
            _log(xbmc.LOGINFO, f"Using direct backend strategy for {self.backend_id}")
        except BackendUnavailable:
            self._strategy = _RpcStrategy(self.backend_id)
            _log(xbmc.LOGINFO, f"Falling back to RPC backend strategy for {self.backend_id}")

    @property
    def strategy(self) -> str:
        return self._strategy_label

    def get_home_rails(self) -> List[Dict[str, Any]]:
        data = self._strategy.get_home_rails()
        return [normalize_rail(item) for item in data]

    def get_rail_items(self, rail_id: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items, next_cursor = self._strategy.get_rail_items(rail_id, cursor)
        normalized = [normalize_item(item) for item in items]
        return normalized, next_cursor

    def get_playable(self, asin: str) -> Playable:
        return self._strategy.get_playable(asin)

    def get_region_info(self) -> Dict[str, Any]:
        data = self._strategy.get_region_info()
        return data if isinstance(data, dict) else {}

    def is_drm_ready(self) -> Optional[bool]:
        return self._strategy.is_drm_ready()

    def search(self, query: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items, next_cursor = self._strategy.search(query, cursor)
        return [normalize_item(item) for item in items], next_cursor


def normalize_rail(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(raw.get("id") or raw.get("slug") or ""),
        "title": str(raw.get("title") or raw.get("name") or ""),
        "type": (raw.get("type") or "mixed").lower(),
    }


def normalize_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    asin = str(raw.get("asin") or raw.get("id") or raw.get("asin_id") or "")
    art = raw.get("art") or {}
    return {
        "asin": asin,
        "title": str(raw.get("title") or raw.get("name") or ""),
        "plot": raw.get("plot") or raw.get("description") or "",
        "year": _as_int(raw.get("year")),
        "duration": _as_int(raw.get("duration")),
        "art": {
            "poster": art.get("poster") or art.get("landscape"),
            "fanart": art.get("fanart") or art.get("background"),
            "thumb": art.get("thumb") or art.get("poster"),
        },
        "is_movie": bool(raw.get("is_movie", False) or raw.get("type") == "movie"),
        "is_show": bool(raw.get("is_show", False) or raw.get("type") == "show"),
    }


def normalize_playable(payload: Any) -> Playable:
    if not isinstance(payload, dict):
        raise BackendError("Playable payload must be a mapping")
    url = payload.get("url") or payload.get("manifest")
    if not url:
        raise BackendError("Playable payload missing URL")
    headers = payload.get("headers") or {}
    license_key = payload.get("license_key") or payload.get("license")
    manifest_type = payload.get("manifest_type") or payload.get("type") or "mpd"
    metadata = payload.get("metadata") or {}
    return Playable(
        url=str(url),
        manifest_type=str(manifest_type),
        license_key=str(license_key) if license_key else None,
        headers={str(k): str(v) for k, v in headers.items()},
        metadata=metadata,
    )


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_backend_instance: Optional[PrimeAPI] = None


def get_backend(backend_id: Optional[str] = None) -> PrimeAPI:
    global _backend_instance
    if _backend_instance is None or (backend_id and _backend_instance.backend_id != backend_id):
        _backend_instance = PrimeAPI(backend_id)
    return _backend_instance

