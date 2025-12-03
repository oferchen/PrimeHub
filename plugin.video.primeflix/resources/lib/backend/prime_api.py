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
        {
            "Addon": lambda addon_id=None: type(
                "AddonStub", (), {"getAddonInfo": lambda self, k: os.getcwd()}
            )()
        },
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


def _log(level: int, message: str) -> None:
    xbmc.log(f"{LOG_PREFIX} {message}", level)


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
            common = importlib.import_module("common")

            # Initialize Globals singleton (required by Amazon VOD)
            self._globals = common.Globals()

            # Import web_api (contains PrimeVideo class)
            web_api = importlib.import_module("web_api")

            # Create PrimeVideo instance
            self._pv = web_api.PrimeVideo()

            # Build root catalog
            if hasattr(self._pv, "BuildRoot"):
                self._pv.BuildRoot()

            _log(
                xbmc.LOGINFO, f"Successfully initialized Amazon VOD API from {lib_path}"
            )

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

        # TODO: The underlying self._pv API's exact method signatures for passing
        # region and resolution are unknown. For now, we only read these settings.
        # Future work (e.g., inspecting the Amazon VOD addon's source) would be
        # required to correctly pass these parameters to self._pv methods.
        _log(
            xbmc.LOGDEBUG,
            f"Getting home rails (Region: {region_str}, Resolution: {resolution_str})",
        )

        if not self._pv or not hasattr(self._pv, "_catalog"):
            return self._get_default_rails()

        catalog = getattr(self._pv, "_catalog", {})
        root = catalog.get("root", {})

        rails = []
        for key, node in root.items():
            if isinstance(node, dict) and node.get("title"):
                rails.append(
                    {
                        "id": key,
                        "title": node.get("title", key),
                        "type": "mixed",
                        "path": key,
                    }
                )

        if not rails:
            rails = self._get_default_rails()

        _log(
            xbmc.LOGDEBUG,
            f"Found {len(rails)} rails in Amazon VOD catalog (Region: {region_str}, Resolution: {resolution_str})",
        )
        return rails

    def _get_default_rails(self) -> List[Dict[str, Any]]:
        """Default rails if catalog unavailable."""
        return [
            {
                "id": "watchlist",
                "title": "My Watchlist",
                "type": "mixed",
                "path": "watchlist",
            },
            {"id": "root", "title": "Home", "type": "mixed", "path": ""},
            {"id": "search", "title": "Search", "type": "mixed", "path": "search"},
        ]

    def get_rail_items(
        self, rail_id: str, cursor: Optional[str]
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetch items for a rail from Amazon VOD catalog."""
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        # TODO: The underlying self._pv API's exact method signatures for passing
        # region and resolution are unknown. For now, we only read these settings.
        # Future work (e.g., inspecting the Amazon VOD addon's source) would be
        # required to correctly pass these parameters to self._pv methods.
        _log(
            xbmc.LOGDEBUG,
            f"Getting rail items for {rail_id} (Region: {region_str}, Resolution: {resolution_str})",
        )

        if not self._pv:
            return [], None

        try:
            if hasattr(self._pv, "_catalog"):
                catalog = getattr(self._pv, "_catalog", {})
                root = catalog.get("root", {})
                node = root.get(rail_id, {})

                if isinstance(node, dict):
                    content = node.get("content", [])
                    items = self._parse_catalog_items(content)
                    if items:
                        return items, None

            return self._create_launcher_item(rail_id), None

        except Exception as e:
            _log(xbmc.LOGWARNING, f"Failed to get items for {rail_id}: {e}")
            return self._create_launcher_item(rail_id), None

    def _parse_catalog_items(self, content: List[Any]) -> List[Dict[str, Any]]:
        """Parse catalog items into normalized format."""
        items = []
        for item in content:
            if not isinstance(item, dict):
                continue

            asin = item.get("asin") or item.get("titleId") or ""
            if not asin:
                continue

            items.append(
                {
                    "asin": asin,
                    "title": item.get("title", ""),
                    "plot": item.get("synopsis", ""),
                    "year": item.get("year"),
                    "duration": item.get("runtime"),
                    "art": {
                        "poster": item.get("poster", ""),
                        "fanart": item.get("fanart", ""),
                        "thumb": item.get("thumb", ""),
                    },
                    "is_movie": item.get("contentType") == "movie",
                    "is_show": item.get("contentType") in ("show", "series"),
                }
            )

        return items

    def _create_launcher_item(self, rail_id: str) -> List[Dict[str, Any]]:
        """Create an item that launches Amazon VOD."""
        return [
            {
                "asin": f"LAUNCHER_{rail_id}",
                "title": f"Browse {rail_id.title()} in Amazon VOD",
                "plot": "Click to open Amazon Prime Video and browse this category",
                "year": None,
                "duration": None,
                "art": {},
                "is_movie": False,
                "is_show": False,
                "plugin_url": f"plugin://{self.addon_id}/?mode={rail_id}",
            }
        ]

    def get_playable(self, asin: str) -> Playable:
        """Get playback info from Amazon VOD."""
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        # TODO: The underlying self._pv API's exact method signatures for passing
        # region and resolution are unknown. For now, we only read these settings.
        # Future work (e.g., inspecting the Amazon VOD addon's source) would be
        # required to correctly pass these parameters to self._pv methods.
        _log(
            xbmc.LOGDEBUG,
            f"Getting playable for {asin} (Region: {region_str}, Resolution: {resolution_str})",
        )

        if not self._pv or not hasattr(self._pv, "GetStream"):
            _log(
                xbmc.LOGWARNING,
                "Backend does not support direct playback. Falling back to plugin URL.",
            )
            raise BackendError(
                f"Use Amazon VOD for playback: plugin://{self.addon_id}/?mode=PlayVideo&asin={asin}"
            )

        try:
            stream_data = self._pv.GetStream(asin=asin, play=False)
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
            if (
                drm_info
                and drm_info.get("type") == "com.widevine.alpha"
                and drm_info.get("license_url")
            ):
                license_key = drm_info["license_url"]
                if "headers" in drm_info:
                    license_key += "|" + "&".join(
                        [f"{k}={v}" for k, v in drm_info["headers"].items()]
                    )

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

    def search(
        self, query: str, cursor: Optional[str]
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search via Amazon VOD."""
        region_code = self._addon.getSetting("region")
        max_res_code = self._addon.getSetting("max_resolution")
        region_str = REGION_MAP.get(region_code, "us")
        resolution_str = RESOLUTION_MAP.get(max_res_code, "auto")

        # TODO: The underlying self._pv API's exact method signatures for passing
        # region and resolution are unknown. For now, we only read these settings.
        # Future work (e.g., inspecting the Amazon VOD addon's source) would be
        # required to correctly pass these parameters to self._pv methods.
        _log(
            xbmc.LOGDEBUG,
            f"Search for '{query}' (Region: {region_str}, Resolution: {resolution_str})",
        )

        if not self._pv or not hasattr(self._pv, "Search"):
            return [], None

        try:
            search_results = self._pv.Search(query, page=cursor)
            if not search_results or not isinstance(search_results, dict):
                return [], None

            content = search_results.get("content", [])
            items = self._parse_catalog_items(content)
            next_cursor = search_results.get("next_page_cursor") or search_results.get(
                "next"
            )

            return items, next_cursor
        except Exception as e:
            _log(xbmc.LOGWARNING, f"Failed to execute search for '{query}': {e}")
            return [], None
