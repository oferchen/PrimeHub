"""
Native backend for Prime Video, communicating directly with Amazon's APIs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import sys
import os

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
    """
    def __init__(self, addon: xbmcaddon.Addon) -> None:
        self._addon = addon
        self._session_manager = SessionManager.get_instance()
        self._session = self._session_manager.get_session()

    # ... (login, logout, is_logged_in remain the same)

    def _make_api_call(self, method: str, url: str, params: Optional[Dict] = None) -> Dict:
        """Helper to make a generic API call and handle errors."""
        # TODO: This is where the live network call would happen.
        # For now, it returns a mock response based on the URL.
        _log(xbmc.LOGINFO, f"Making API call (MOCK): {method} {url} with params {params}")
        
        if "GetPage?pageId=Home" in url:
            return self._get_mock_home_response()
        elif "GetPage?pageId=" in url:
            return self._get_mock_rail_items_response()
        elif "Search" in url:
            return self._get_mock_search_response()
        elif "GetPlaybackResources" in url:
            return self._get_mock_playback_response()
            
        raise BackendError(f"No mock response for API call: {url}")

    def get_home_rails(self) -> List[Dict[str, Any]]:
        """Fetches home screen content from the backend."""
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")
        
        # response = self._make_api_call("GET", constants.URLS["home"], params=constants.DEVICE_INFO)
        response = self._get_mock_home_response() # Using mock directly
        
        # TODO: The parsing logic depends entirely on the real API response structure.
        # This is a guess based on typical API designs.
        rails = []
        for item in response.get("widgets", []):
            if item.get("type") == "RailWidget":
                rails.append({
                    "id": item.get("id"),
                    "title": item.get("title", {}).get("default"),
                    "type": "mixed" # This would need to be inferred from content
                })
        return rails
        
    def get_rail_items(self, rail_id: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")

        url = constants.URLS["rail_items"].format(rail_id=rail_id)
        params = {**constants.DEVICE_INFO, "page": cursor or 1}
        
        # response = self._make_api_call("GET", url, params=params)
        response = self._get_mock_rail_items_response() # Using mock directly
        
        items = response.get("items", [])
        next_cursor = response.get("nextPageCursor")
        return items, next_cursor
        
    def search(self, query: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")

        url = constants.URLS["search"].format(query=query)
        # response = self._make_api_call("GET", url)
        response = self._get_mock_search_response()
        
        items = response.get("items", [])
        next_cursor = response.get("nextPageCursor")
        return items, next_cursor

    def get_playable(self, asin: str) -> Playable:
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")
            
        payload = {**constants.DEVICE_INFO, "asin": asin}
        # response = self._make_api_call("POST", constants.URLS["get_playback"], params=payload)
        response = self._get_mock_playback_response()
        
        # TODO: Parse the real response to get these details
        return Playable(
            url=response.get("manifestUrl"),
            manifest_type="mpd",
            license_key=response.get("licenseUrl"),
            headers={},
            metadata={"title": f"Playable for {asin}"}
        )
    
    # --- Mock Response Generators ---
    def _get_mock_home_response(self) -> Dict:
        return {
            "widgets": [
                {"type": "RailWidget", "id": "continue_watching", "title": {"default": "Continue Watching"}},
                {"type": "RailWidget", "id": "movies_we_think_youll_like", "title": {"default": "Movies For You"}},
            ]
        }

    def _get_mock_rail_items_response(self) -> Dict:
        return {
            "items": [{"asin": "B012345", "title": "The Grand Tour"}],
            "nextPageCursor": "cursor123"
        }

    def _get_mock_search_response(self) -> Dict:
        return {
            "items": [{"asin": "B054321", "title": "Search Result"}],
            "nextPageCursor": None
        }
        
    def _get_mock_playback_response(self) -> Dict:
        return {
            "manifestUrl": "http://mock.url/manifest.mpd",
            "licenseUrl": "http://mock.license/server"
        }
# ... (rest of the file remains the same)