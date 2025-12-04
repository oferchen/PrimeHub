"""
Native backend for Prime Video, communicating directly with Amazon's APIs.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import sys
import os
import json

# Add vendor directory to sys.path for bundled libraries
vendor_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'vendor'))
if vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

import requests
from .session import SessionManager
from . import constants

try:
    import xbmc
    import xbmcaddon
except ImportError:
    from ...tests.kodi_mocks import xbmc, xbmcaddon

# (Data Models and Exceptions remain the same)
# ...

class _NativeAPIIntegration:
    """
    The concrete implementation of the backend communication strategy.
    Now uses an async-first approach with a central request handler.
    """
    def __init__(self, addon: xbmcaddon.Addon) -> None:
        self._addon = addon
        self._session_manager = SessionManager.get_instance()
        self._session = self._session_manager.get_session()

    async def _handle_request(self, method: str, url: str, params: Optional[Dict] = None, payload: Optional[Dict] = None) -> Dict:
        """
        Central request handler for all API calls. It manages making the
        (stubbed) request, logging metrics, and handling errors.
        """
        _log(xbmc.LOGINFO, f"API Request (MOCK): {method} {url}")
        
        # In a real implementation, this is where the async HTTP call would be made.
        # e.g., using a library like `aiohttp`:
        # async with self._session.request(method, url, params=params, json=payload) as response:
        #     response.raise_for_status()
        #     return await response.json()
        
        # For now, we return a mock response based on the URL.
        if "GetPage?pageId=Home" in url:
            return self._get_mock_home_response()
        elif "GetPage?pageId=" in url:
            return self._get_mock_rail_items_response()
        elif "Search" in url:
            return self._get_mock_search_response(query=params.get("query"))
        elif "GetPlaybackResources" in url:
            return self._get_mock_playback_response()
        
        raise BackendError(f"No mock response for API call: {url}")

    async def get_home_rails(self) -> List[Dict[str, Any]]:
        """Fetches home screen content from the backend asynchronously."""
        if not self._session_manager.is_logged_in():
            raise AuthenticationError("User is not logged in.")
        
        response = await self._handle_request("GET", constants.URLS["home"], params=constants.DEVICE_INFO)
        
        rails = []
        for item in response.get("widgets", []):
            if item.get("type") == "RailWidget":
                rails.append({ "id": item.get("id"), "title": item.get("title", {}).get("default") })
        return rails
        
    async def get_rail_items(self, rail_id: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not self._session_manager.is_logged_in():
            raise AuthenticationError("User is not logged in.")

        url = constants.URLS["rail_items"].format(rail_id=rail_id)
        params = {**constants.DEVICE_INFO, "page": cursor or 1}
        response = await self._handle_request("GET", url, params=params)
        
        return response.get("items", []), response.get("nextPageCursor")
        
    async def search(self, query: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not self._session_manager.is_logged_in():
            raise AuthenticationError("User is not logged in.")

        url = constants.URLS["search"].format(query=query)
        params = {"query": query} # Pass query for mock response generator
        response = await self._handle_request("GET", url, params=params)
        
        return response.get("items", []), response.get("nextPageCursor")

    async def get_playable(self, asin: str) -> Playable:
        if not self._session_manager.is_logged_in():
            raise AuthenticationError("User is not logged in.")
            
        payload = {**constants.DEVICE_INFO, "asin": asin}
        response = await self._handle_request("POST", constants.URLS["get_playback"], payload=payload)
        
        return Playable(
            url=response.get("manifestUrl"),
            manifest_type="mpd",
            license_key=response.get("licenseUrl"),
            headers={},
            metadata={"title": f"Playable for {asin}"}
        )
    
    # ... (other methods like login, logout, add_to_watchlist remain synchronous for now)
    
    # --- Mock Response Generators ---
    def _get_mock_home_response(self) -> Dict:
        # ...
        pass
    # ... (other mock response generators)
# ... (rest of file)
class PrimeAPI:
    """
    Provides a simplified, unified interface (Facade) to the backend.
    """
    def __init__(self, addon: xbmcaddon.Addon) -> None:
        self._strategy = _NativeAPIIntegration(addon)

    # Synchronous methods
    def login(self, username: str, password: str) -> bool:
        return self._strategy.login(username, password)

    def logout(self) -> None:
        self._strategy.logout()

    def is_logged_in(self) -> bool:
        return self._strategy.is_logged_in()

    def add_to_watchlist(self, asin: str) -> bool:
        return self._strategy.add_to_watchlist(asin)
        
    def mark_as_watched(self, asin: str, watched_status: bool) -> bool:
        return self._strategy.mark_as_watched(asin, watched_status)
        
    def is_drm_ready(self) -> Optional[bool]:
        return self._strategy.is_drm_ready()
        
    def get_region_info(self) -> Dict[str, Any]:
        return self._strategy.get_region_info()

    # Asynchronous methods
    async def get_home_rails(self) -> List[Dict[str, Any]]:
        raw_rails = await self._strategy.get_home_rails()
        return [normalize_rail(rail) for rail in raw_rails]
    
    async def get_rail_items(self, rail_id: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items, next_cursor = await self._strategy.get_rail_items(rail_id, cursor)
        return [normalize_item(item) for item in items], next_cursor

    async def search(self, query: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items, next_cursor = await self._strategy.search(query, cursor)
        return [normalize_item(item) for item in items], next_cursor
        
    async def get_playable(self, asin: str) -> Playable:
        return await self._strategy.get_playable(asin)