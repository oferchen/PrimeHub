"""Backend bridge that uses Amazon VOD's internal API modules.

PrimeHub imports Amazon VOD's modules and uses the same backend API
to fetch real Prime Video catalog data and playback URLs.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

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
        {"Addon": lambda addon_id=None: type("AddonStub", (), {"getAddonInfo": lambda self, k: os.getcwd()})()},
    )

LOG_PREFIX = "[PrimeHub-backend]"
BACKEND_CANDIDATES = (
    "plugin.video.amazon-test",
    "plugin.video.amazonprime",
    "plugin.video.amazonvod",
    "plugin.video.amazon",
    "plugin.video.primevideo",
)

REGION_MAP = {
    "0": "us",
    "1": "uk",
    "2": "de",
    "3": "jp",
}

RESOLUTION_MAP = {
    "0": "auto",
    "1": "1080p",
    "2": "720p",
}


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


class _AmazonVODIntegration:
    """Integration using Amazon VOD's internal API."""

    def __init__(self, addon_id: str, addon: xbmcaddon.Addon) -> None:
        self.addon_id = addon_id
        self._addon = addon
        self._pv = None
        self._globals = None
        self._init_amazon_modules()

    def _init_amazon_modules(self) -> None:
        """Import Amazon VOD modules and initialize PrimeVideo."""
        addon = xbmcaddon.Addon(self.addon_id)
        addon_path = addon.getAddonInfo("path")
        lib_path = os.path.join(addon_path, "resources", "lib")

        # Add Amazon VOD lib to path
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)

        try:
            # Import Amazon VOD's modules
            import importlib

            # Import common (contains Globals singleton)
            common = importlib.import_module('common')

            # Initialize Globals singleton (required by Amazon VOD)
            self._globals = common.Globals()

            # Import web_api (contains PrimeVideo class)
            web_api = importlib.import_module('web_api')

            # Create PrimeVideo instance
            self._pv = web_api.PrimeVideo()

            # Build root catalog
            if hasattr(self._pv, 'BuildRoot'):
                self._pv.BuildRoot()

            _log(xbmc.LOGINFO, f"Successfully initialized Amazon VOD API from {lib_path}")

        except Exception as e:
            _log(xbmc.LOGERROR, f"Failed to initialize Amazon VOD modules: {e}")
            _log(xbmc.LOGDEBUG, f"sys.path: {sys.path}")
            raise BackendUnavailable(f"Cannot initialize Amazon VOD API: {e}")

    def get_home_rails(self) -> List[Dict[str, Any]]:
        """Get rails from Amazon VOD catalog."""
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        # For direct import, we assume the underlying PrimeVideo object might be configured
        # with region/resolution settings at a higher level, or its methods take them.
        # As we don't know the exact API of self._pv, we read the settings here
        # but do not modify the calls to self._pv methods yet.
        # This will be addressed in the "Validate assumptions" task.
        if not self._pv or not hasattr(self._pv, '_catalog'):
            return self._get_default_rails()

        catalog = getattr(self._pv, '_catalog', {})
        root = catalog.get('root', {})

        rails = []
        for key, node in root.items():
            if isinstance(node, dict) and node.get('title'):
                rails.append({
                    "id": key,
                    "title": node.get('title', key),
                    "type": "mixed",
                    "path": key,
                })

        if not rails:
            rails = self._get_default_rails()

        _log(xbmc.LOGDEBUG, f"Found {len(rails)} rails in Amazon VOD catalog (Region: {region_str}, Resolution: {resolution_str})")
        return rails

    def _get_default_rails(self) -> List[Dict[str, Any]]:
        """Default rails if catalog unavailable."""
        return [
            {"id": "watchlist", "title": "My Watchlist", "type": "mixed", "path": "watchlist"},
            {"id": "root", "title": "Home", "type": "mixed", "path": ""},
            {"id": "search", "title": "Search", "type": "mixed", "path": "search"},
        ]

    def get_rail_items(self, rail_id: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetch items for a rail from Amazon VOD catalog."""
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        if not self._pv:
            return [], None

        try:
            if hasattr(self._pv, '_catalog'):
                catalog = getattr(self._pv, '_catalog', {})
                root = catalog.get('root', {})
                node = root.get(rail_id, {})

                if isinstance(node, dict):
                    content = node.get('content', [])
                    items = self._parse_catalog_items(content)
                    if items:
                        return items, None

            return self._create_launcher_item(rail_id)

        except Exception as e:
            _log(xbmc.LOGWARNING, f"Failed to get items for {rail_id}: {e}")
            return self._create_launcher_item(rail_id)

    def _parse_catalog_items(self, content: List[Any]) -> List[Dict[str, Any]]:
        """Parse catalog items into normalized format."""
        items = []
        for item in content:
            if not isinstance(item, dict):
                continue

            asin = item.get('asin') or item.get('titleId') or ''
            if not asin:
                continue

            items.append({
                "asin": asin,
                "title": item.get('title', ''),
                "plot": item.get('synopsis', ''),
                "year": item.get('year'),
                "duration": item.get('runtime'),
                "art": {
                    "poster": item.get('poster', ''),
                    "fanart": item.get('fanart', ''),
                    "thumb": item.get('thumb', ''),
                },
                "is_movie": item.get('contentType') == 'movie',
                "is_show": item.get('contentType') in ('show', 'series'),
            })

        return items

    def _create_launcher_item(self, rail_id: str) -> List[Dict[str, Any]]:
        """Create an item that launches Amazon VOD."""
        return [{
            "asin": f"LAUNCHER_{rail_id}",
            "title": f"Browse {rail_id.title()} in Amazon VOD",
            "plot": "Click to open Amazon Prime Video and browse this category",
            "year": None,
            "duration": None,
            "art": {},
            "is_movie": False,
            "is_show": False,
            "plugin_url": f"plugin://{self.addon_id}/?mode={rail_id}",
        }]

    def get_playable(self, asin: str) -> Playable:
        """Get playback info from Amazon VOD."""
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        if not self._pv or not hasattr(self._pv, "GetStream"):
            _log(xbmc.LOGWARNING, "Backend does not support direct playback. Falling back to plugin URL.")
            raise BackendError(f"Use Amazon VOD for playback: plugin://{self.addon_id}/?mode=PlayVideo&asin={asin}")

        try:
            # We assume GetStream might accept region/resolution, but as we don't know the exact API,
            # we just log the settings and pass a play=False parameter.
            stream_data = self._pv.GetStream(asin=asin, play=False)
            _log(xbmc.LOGDEBUG, f"GetStream for {asin} (Region: {region_str}, Resolution: {resolution_str})")

            if not stream_data or not isinstance(stream_data, dict):
                raise BackendError("Failed to get stream data from backend.")

            metadata = stream_data.get("metadata", {})
            if not metadata and "title" in stream_data:
                metadata = {
                    k: stream_data[k]
                    for k in ["title", "plot", "year", "duration", "art"]
                    if k in stream_data
                }

            license_key = ""
            drm_info = stream_data.get("drm")
            if drm_info and drm_info.get("type") == "com.widevine.alpha" and drm_info.get("license_url"):
                license_key = drm_info["license_url"]
                if "headers" in drm_info:
                    license_key += "|" + "&".join([f"{k}={v}" for k, v in drm_info["headers"].items()])

            return Playable(
                url=stream_data.get("url", ""),
                manifest_type=stream_data.get("type", "mpd"),
                license_key=license_key,
                headers=stream_data.get("headers", {}),
                metadata=metadata,
            )
        except Exception as e:
            _log(xbmc.LOGERROR, f"Failed to get playable item for {asin}: {e}")
            raise BackendError(f"Could not retrieve playable stream for {asin}.")

    def search(self, query: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search via Amazon VOD."""
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        if not self._pv or not hasattr(self._pv, "Search"):
            return [], None

        try:
            search_results = self._pv.Search(query, page=cursor)
            _log(xbmc.LOGDEBUG, f"Search for '{query}' (Region: {region_str}, Resolution: {resolution_str})")

            if not search_results or not isinstance(search_results, dict):
                return [], None

            content = search_results.get("content", [])
            items = self._parse_catalog_items(content)
            next_cursor = search_results.get("next_page_cursor") or search_results.get("next")

            return items, next_cursor
        except Exception as e:
            _log(xbmc.LOGWARNING, f"Failed to execute search for '{query}': {e}")
            return [], None

    def get_region_info(self) -> Dict[str, Any]:
        """Get region info from Amazon VOD."""
        if not self._pv or not hasattr(self._pv, 'getRegion'):
            return {}

        try:
            region_data = self._pv.getRegion()
            if isinstance(region_data, dict):
                return region_data
        except Exception as e:
            _log(xbmc.LOGWARNING, f"Failed to get region info: {e}")
        return {}

    def is_drm_ready(self) -> Optional[bool]:
        """DRM handled by Amazon addon."""
        if not self._pv or not hasattr(self._pv, 'isDRMReady'):
            return None

        try:
            return self._pv.isDRMReady()
        except Exception as e:
            _log(xbmc.LOGWARNING, f"Failed to get DRM readiness: {e}")
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


class _JsonRPCIntegration:
    """Integration using JSON-RPC Addons.ExecuteAddon."""

    def __init__(self, addon_id: str, addon: xbmcaddon.Addon) -> None:
        self.addon_id = addon_id
        self._addon = addon
        if not self._is_addon_available():
            raise BackendUnavailable(f"JSON-RPC backend {addon_id} not available.")

    def _is_addon_available(self) -> bool:
        try:
            xbmcaddon.Addon(self.addon_id)
            return True
        except Exception:
            return False

    def _execute_action(self, action: str, **kwargs) -> Any:
        params = {"action": action}
        params.update(kwargs)
        payload = {
            "jsonrpc": "2.0",
            "method": "Addons.ExecuteAddon",
            "params": {"addonid": self.addon_id, "params": urlencode(params)},
            "id": 1,
        }
        response_str = xbmc.executeJSONRPC(json.dumps(payload))
        response = json.loads(response_str)
        if "error" in response:
            raise BackendError(f"JSON-RPC error for action {action}: {response['error']}")

        result = response.get("result")
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return result
        return result

    def get_home_rails(self) -> List[Dict[str, Any]]:
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        data = self._execute_action("get_home_rails", region=region_str, resolution=resolution_str)
        if not isinstance(data, list):
            raise BackendError("get_home_rails returned invalid data")
        return data

    def get_rail_items(self, rail_id: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        params = {"rail_id": rail_id}
        if cursor:
            params["cursor"] = cursor
        params["region"] = region_str
        params["resolution"] = resolution_str

        data = self._execute_action("get_rail_items", **params)
        if not isinstance(data, dict):
            raise BackendError("get_rail_items returned invalid data")
        return data.get("items", []), data.get("next_cursor")

    def get_playable(self, asin: str) -> Playable:
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        data = self._execute_action("get_playable", asin=asin, region=region_str, resolution=resolution_str)
        if not isinstance(data, dict):
            raise BackendError("get_playable returned invalid data")

        return Playable(
            url=data.get("url", ""),
            manifest_type=data.get("manifest_type", "mpd"),
            license_key=data.get("license_key"),
            headers=data.get("headers", {}),
            metadata=data.get("metadata", {}),
        )

    def search(self, query: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search via JSON-RPC."""
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        params = {"query": query}
        if cursor:
            params["cursor"] = cursor
        params["region"] = region_str
        params["resolution"] = resolution_str

        try:
            data = self._execute_action("search", **params)
            if not isinstance(data, dict):
                raise BackendError("search returned invalid data")
            return data.get("items", []), data.get("next_cursor")
        except BackendError as e:
            _log(xbmc.LOGWARNING, f"JSON-RPC search failed for '{query}': {e}")
            return [], None

    def get_region_info(self) -> Dict[str, Any]:
        """Get region info via JSON-RPC."""
        try:
            data = self._execute_action("get_region_info")
            if isinstance(data, dict):
                return data
        except BackendError as e:
            _log(xbmc.LOGWARNING, f"JSON-RPC get_region_info failed: {e}")
        return {}

    def is_drm_ready(self) -> Optional[bool]:
        """DRM readiness via JSON-RPC."""
        try:
            data = self._execute_action("is_drm_ready")
            if isinstance(data, bool):
                return data
            elif isinstance(data, dict) and 'ready' in data and isinstance(data['ready'], bool):
                return data['ready']
        except BackendError as e:
            _log(xbmc.LOGWARNING, f"JSON-RPC is_drm_ready failed: {e}")
        return None


def get_backend(backend_id: Optional[str] = None) -> PrimeAPI:
    global _backend_instance
    if _backend_instance is None or (backend_id and _backend_instance.backend_id != backend_id):
        addon = xbmcaddon.Addon()
        _backend_instance = PrimeAPI(backend_id, addon)
    return _backend_instance


class PrimeAPI:
    """Facade for Amazon VOD API integration."""

    def __init__(self, backend_id: Optional[str] = None, addon: Optional[xbmcaddon.Addon] = None) -> None:
        self.backend_id = backend_id or discover_backend()
        if not self.backend_id:
            raise BackendUnavailable("No compatible Amazon addon installed")

        self._addon = addon or xbmcaddon.Addon()

        try:
            self._strategy = _AmazonVODIntegration(self.backend_id, self._addon)
            self._strategy_name = "direct_import"
            _log(xbmc.LOGINFO, f"PrimeHub using direct import backend API: {self.backend_id}")
        except BackendUnavailable:
            _log(xbmc.LOGWARNING, f"Direct import failed for {self.backend_id}. Trying JSON-RPC fallback.")
            try:
                self._strategy = _JsonRPCIntegration(self.backend_id, self._addon)
                self._strategy_name = "json_rpc"
                _log(xbmc.LOGINFO, f"PrimeHub using JSON-RPC backend API: {self.backend_id}")
            except BackendUnavailable:
                _log(xbmc.LOGERROR, "All backend integration strategies failed.")
                raise BackendUnavailable("Could not connect to backend addon via direct import or JSON-RPC.")

    @property
    def strategy(self) -> str:
        return self._strategy_name

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
        return self._strategy.get_region_info()

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
        "path": raw.get("path", ""),
    }


def normalize_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    asin = str(raw.get("asin") or raw.get("id") or raw.get("asin_id") or "")
    art = raw.get("art") or {}

    # Check if this is a launcher item
    plugin_url = raw.get("plugin_url")

    return {
        "asin": asin,
        "title": str(raw.get("title") or raw.get("name") or ""),
        "plot": raw.get("plot") or raw.get("description") or "",
        "year": _as_int(raw.get("year")),
        "duration": _as_int(raw.get("duration")),
        "art": {
            "poster": art.get("poster") or art.get("landscape") or "",
            "fanart": art.get("fanart") or art.get("background") or "",
            "thumb": art.get("thumb") or art.get("poster") or "",
        },
        "is_movie": bool(raw.get("is_movie", False) or raw.get("type") == "movie"),
        "is_show": bool(raw.get("is_show", False) or raw.get("type") == "show"),
        "plugin_url": plugin_url,
    }


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_backend_instance: Optional[PrimeAPI] = None
