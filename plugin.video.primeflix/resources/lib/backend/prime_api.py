"""Integration with existing Amazon Prime Video Kodi add-ons."""
from __future__ import annotations

import importlib
import json
import os
import sys
import threading
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # pragma: no cover - Kodi runtime
    import xbmc
    import xbmcaddon
except ImportError:  # pragma: no cover - local dev fallback
    class _XBMC:
        LOGDEBUG = 0
        LOGINFO = 1
        LOGWARNING = 2
        LOGERROR = 3

        @staticmethod
        def log(message: str, level: int = 0) -> None:
            print(f"[xbmc:{level}] {message}")

        @staticmethod
        def executeJSONRPC(payload: str) -> str:
            return json.dumps({"result": {}})

        @staticmethod
        def getCondVisibility(expression: str) -> bool:
            return False

    class _Addon:
        def __init__(self, addon_id: Optional[str] = None):
            self._id = addon_id or "plugin.video.primeflix"

        def getAddonInfo(self, key: str) -> str:
            mapping = {
                "id": self._id,
                "name": "PrimeFlix",
                "path": os.getcwd(),
            }
            return mapping.get(key, "")

        def getSettingString(self, key: str) -> str:
            return ""

        def getSettingBool(self, key: str) -> bool:
            return False

        def getSettingInt(self, key: str) -> int:
            return 0

    xbmc = _XBMC()  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": _Addon})  # type: ignore

from ..perf import log_debug, log_info, log_warning
from ..preflight import ensure_ready_or_raise

# Candidate module names for direct import strategy
DIRECT_MODULE_CANDIDATES = (
    "amazon_prime",
    "prime_video",
    "primevideo",
    "resources.lib.amazon_prime",
    "resources.lib.prime_video",
    "resources.lib.api",
)

DIRECT_CLASS_CANDIDATES = (
    "PrimeVideo",
    "PrimeVideoApi",
    "PrimeVideoAPI",
    "PrimeApi",
    "PrimeAPI",
    "Navigation",
)

# Fallback plugin routes for indirect strategy
INDIRECT_RAIL_LABELS = {
    "continue": ("Continue Watching", "watchlist"),
    "originals": ("Prime Originals", "prime-originals"),
    "movies": ("Movies", "movies"),
    "tv": ("TV", "tv"),
    "recommended": ("Recommended", "recommended"),
}

INDIRECT_SEARCH_ROUTE = "search"


class BackendNotAvailableError(RuntimeError):
    """Raised when no backend implementation can be resolved."""


@dataclass
class RailPage:
    items: List[Dict[str, Any]]
    next_token: Optional[str]


class PrimeBackend:
    """Facade exposing operations required by the PrimeFlix UI."""

    def __init__(self) -> None:
        self._addon = xbmcaddon.Addon()
        self._backend_id: Optional[str] = None
        self._strategy: Optional[str] = None
        self._adapter: Optional[_BaseAdapter] = None
        self._lock = threading.RLock()

    def ensure_initialized(self) -> None:
        if self._adapter:
            return
        with self._lock:
            if self._adapter:
                return
            backend_id = ensure_ready_or_raise()
            adapter = self._create_adapter(backend_id)
            self._backend_id = backend_id
            self._adapter = adapter
            log_info(f"Prime backend ready using {self._strategy} strategy ({backend_id})")

    def _create_adapter(self, backend_id: str) -> "_BaseAdapter":
        errors: List[str] = []
        # Direct import strategy
        try:
            adapter = _DirectAdapter(backend_id)
            adapter.ping()
            self._strategy = "direct"
            return adapter
        except Exception as exc:
            errors.append(f"direct: {exc}")
            log_debug(f"Direct adapter failed for {backend_id}: {exc}")

        # Indirect strategy
        try:
            adapter = _IndirectAdapter(backend_id)
            adapter.ping()
            self._strategy = "indirect"
            return adapter
        except Exception as exc:
            errors.append(f"indirect: {exc}")
            log_debug(f"Indirect adapter failed for {backend_id}: {exc}")

        raise BackendNotAvailableError("; ".join(errors))

    @property
    def strategy(self) -> str:
        self.ensure_initialized()
        return self._strategy or "unknown"

    @property
    def backend_id(self) -> Optional[str]:
        self.ensure_initialized()
        return self._backend_id

    def fetch_rail(self, rail_id: str, limit: int = 25, cursor: Optional[str] = None) -> RailPage:
        self.ensure_initialized()
        assert self._adapter is not None
        return self._adapter.fetch_rail(rail_id, limit, cursor)

    def search(self, query: str, limit: int = 30) -> List[Dict[str, Any]]:
        self.ensure_initialized()
        assert self._adapter is not None
        return self._adapter.search(query, limit)

    def get_playable(self, asin: str) -> Dict[str, Any]:
        self.ensure_initialized()
        assert self._adapter is not None
        return self._adapter.get_playable(asin)

    def get_region(self) -> Optional[str]:
        self.ensure_initialized()
        assert self._adapter is not None
        return self._adapter.get_region()

    def get_backend_summary(self) -> Dict[str, Any]:
        self.ensure_initialized()
        return {
            "id": self._backend_id,
            "strategy": self._strategy,
        }


class _BaseAdapter:
    def __init__(self, addon_id: str) -> None:
        self.addon_id = addon_id

    def ping(self) -> None:
        raise NotImplementedError

    def fetch_rail(self, rail_id: str, limit: int, cursor: Optional[str]) -> RailPage:
        raise NotImplementedError

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def get_playable(self, asin: str) -> Dict[str, Any]:
        raise NotImplementedError

    def get_region(self) -> Optional[str]:
        return None


class _DirectAdapter(_BaseAdapter):
    """Adapter that imports Python modules from the backend add-on."""

    def __init__(self, addon_id: str) -> None:
        super().__init__(addon_id)
        self._api: Optional[Any] = None
        self._module: Optional[ModuleType] = None
        self._discover()

    def _discover(self) -> None:
        addon = xbmcaddon.Addon(self.addon_id)
        addon_path = addon.getAddonInfo("path")
        search_paths = [addon_path, os.path.join(addon_path, "resources", "lib")]
        for path in search_paths:
            if path and path not in sys.path:
                sys.path.insert(0, path)
        errors: List[str] = []
        for module_name in DIRECT_MODULE_CANDIDATES:
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                errors.append(f"{module_name}: {exc}")
                continue
            api = self._locate_api_object(module)
            if api is not None:
                self._module = module
                self._api = api
                log_debug(f"Direct backend module resolved: {module_name}")
                return
        raise BackendNotAvailableError(" | ".join(errors))

    def _locate_api_object(self, module: ModuleType) -> Optional[Any]:
        for attribute in DIRECT_CLASS_CANDIDATES:
            api_candidate = getattr(module, attribute, None)
            if api_candidate is None:
                continue
            try:
                instance = api_candidate() if callable(api_candidate) else api_candidate
            except Exception:
                continue
            if self._has_required_capabilities(instance):
                return instance
        # Fall back to module-level functions
        if self._has_required_capabilities(module):
            return module
        return None

    @staticmethod
    def _has_required_capabilities(obj: Any) -> bool:
        has_rail = any(hasattr(obj, name) for name in ("get_rail", "get_section", "get_menu"))
        has_playable = any(hasattr(obj, name) for name in ("get_playable", "play", "get_stream"))
        if not (has_rail and has_playable):
            return False
        if not any(hasattr(obj, name) for name in ("search", "find", "search_titles")):
            log_warning("Backend API missing optional capability search")
        return True

    def _ensure_api(self) -> Any:
        if self._api is None:
            raise BackendNotAvailableError("Direct API unavailable")
        return self._api

    def ping(self) -> None:
        self._ensure_api()

    def fetch_rail(self, rail_id: str, limit: int, cursor: Optional[str]) -> RailPage:
        api = self._ensure_api()
        data = self._invoke(api, ("get_rail", "get_section", "get_menu"), rail_id=rail_id, limit=limit, cursor=cursor)
        return self._normalize_listing(data)

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        api = self._ensure_api()
        results = self._invoke(api, ("search", "find", "search_titles"), query=query, limit=limit)
        return [self._normalize_item(item) for item in results]

    def get_playable(self, asin: str) -> Dict[str, Any]:
        api = self._ensure_api()
        playable = self._invoke(api, ("get_playable", "play", "get_stream"), asin)
        return playable

    def get_region(self) -> Optional[str]:
        api = self._ensure_api()
        region = getattr(api, "get_region", None)
        if callable(region):
            try:
                return region()
            except Exception:
                return None
        return getattr(api, "region", None)

    def _normalize_listing(self, data: Any) -> RailPage:
        items: List[Dict[str, Any]] = []
        next_token: Optional[str] = None
        if isinstance(data, dict):
            items = [self._normalize_item(it) for it in data.get("items", [])]
            next_token = data.get("next") or data.get("next_token")
        elif isinstance(data, (list, tuple)):
            items = [self._normalize_item(it) for it in data]
        return RailPage(items, next_token)

    def _normalize_item(self, item: Any) -> Dict[str, Any]:
        if isinstance(item, dict):
            return item
        mapping = {}
        for attr in ("asin", "title", "plot", "year", "genre", "genres", "duration", "image", "thumb", "poster", "fanart", "type"):
            if hasattr(item, attr):
                mapping[attr] = getattr(item, attr)
        return mapping

    @staticmethod
    def _invoke(api: Any, method_names: Iterable[str], *args, **kwargs) -> Any:
        for name in method_names:
            method = getattr(api, name, None)
            if callable(method):
                return method(*args, **kwargs)
        raise BackendNotAvailableError(f"Backend API missing methods {', '.join(method_names)}")


class _IndirectAdapter(_BaseAdapter):
    """Adapter that interacts with the backend through plugin URLs and JSON-RPC."""

    def __init__(self, addon_id: str) -> None:
        super().__init__(addon_id)
        self._home_cache: Dict[str, str] = {}

    def ping(self) -> None:
        # Fetch root directory to confirm backend is responsive
        self._refresh_home_routes()

    def _refresh_home_routes(self) -> None:
        result = self._get_directory(f"plugin://{self.addon_id}/")
        files = result.get("files", []) if result else []
        mapping = {}
        for entry in files:
            label = entry.get("label", "").lower()
            url = entry.get("file")
            if not url:
                continue
            mapping[label] = url
        self._home_cache = mapping

    def fetch_rail(self, rail_id: str, limit: int, cursor: Optional[str]) -> RailPage:
        label_hint, route_hint = INDIRECT_RAIL_LABELS.get(rail_id, (rail_id, rail_id))
        target_url = self._resolve_rail_url(label_hint.lower(), route_hint)
        if cursor:
            delimiter = "&" if "?" in target_url else "?"
            target_url = f"{target_url}{delimiter}cursor={cursor}"
        payload = self._get_directory(target_url)
        items = [self._convert_entry(entry) for entry in payload.get("files", [])]
        next_token = payload.get("limits", {}).get("next")
        return RailPage(items, next_token)

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        url = f"plugin://{self.addon_id}/?action={INDIRECT_SEARCH_ROUTE}&term={query}"
        payload = self._get_directory(url)
        files = payload.get("files", [])
        return [self._convert_entry(entry) for entry in files[:limit]]

    def get_playable(self, asin: str) -> Dict[str, Any]:
        url = f"plugin://{self.addon_id}/?action=play&asin={asin}&output=json"
        response = xbmc.executeJSONRPC(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "Addons.ExecuteAddon",
                    "params": {
                        "addonid": self.addon_id,
                        "params": {"action": "play", "asin": asin, "output": "json"},
                    },
                    "id": 1,
                }
            )
        )
        data = json.loads(response)
        result = data.get("result")
        if isinstance(result, dict):
            details = result.get("details")
            if isinstance(details, dict):
                return details
            if any(key in result for key in ("url", "stream_url", "license_key")):
                return result
        raise BackendNotAvailableError("Unable to retrieve playable stream from backend")

    def get_region(self) -> Optional[str]:
        response = xbmc.executeJSONRPC(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "Addons.ExecuteAddon",
                    "params": {
                        "addonid": self.addon_id,
                        "params": {"action": "region"},
                    },
                    "id": 1,
                }
            )
        )
        data = json.loads(response)
        if isinstance(data.get("result"), dict):
            return data["result"].get("region")
        return None

    def _get_directory(self, plugin_url: str) -> Dict[str, Any]:
        response = xbmc.executeJSONRPC(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "Files.GetDirectory",
                    "params": {
                        "directory": plugin_url,
                        "media": "files",
                        "properties": [
                            "title",
                            "art",
                            "streamdetails",
                            "file",
                            "mimetype",
                            "showtitle",
                            "season",
                            "episode",
                            "fanart",
                            "thumbnail",
                            "dateadded",
                        ],
                    },
                    "id": 1,
                }
            )
        )
        data = json.loads(response)
        return data.get("result", {})

    def _resolve_rail_url(self, label_hint: str, route_hint: str) -> str:
        if not self._home_cache:
            self._refresh_home_routes()
        for label, url in self._home_cache.items():
            if label_hint in label:
                return url
        return f"plugin://{self.addon_id}/?action={route_hint}"

    def _convert_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "title": entry.get("label") or entry.get("title"),
            "asin": self._extract_asin(entry.get("file", "")),
            "plot": entry.get("plot"),
            "year": entry.get("year"),
            "duration": entry.get("runtime"),
            "genre": entry.get("genre"),
            "thumb": entry.get("thumbnail") or entry.get("art", {}).get("thumb"),
            "poster": entry.get("art", {}).get("poster"),
            "fanart": entry.get("art", {}).get("fanart"),
            "type": entry.get("type"),
        }
        return info

    @staticmethod
    def _extract_asin(url: str) -> Optional[str]:
        if "asin=" in url:
            return url.split("asin=")[-1].split("&")[0]
        return None


_backend_instance: Optional[PrimeBackend] = None


def get_backend() -> PrimeBackend:
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = PrimeBackend()
    return _backend_instance
