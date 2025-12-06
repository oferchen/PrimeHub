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
    import xbmcvfs
except ImportError:
    from ...tests.kodi_mocks import xbmc, xbmcaddon, xbmcvfs

# (Data Models and Exceptions remain the same)
@dataclass
class Playable:
    url: str
    manifest_type: str
    license_key: Optional[str]
    headers: Dict[str, str]
    metadata: Dict[str, Any]

class BackendError(RuntimeError):
    """Raised for general backend errors."""

class AuthenticationError(BackendError):
    """Raised for login/authentication failures."""

def _log(level: int, message: str) -> None:
    xbmc.log(f"[PrimeHub-Native] {message}", level)

class _NativeAPIIntegration:
    """
    The concrete implementation of the backend communication strategy.
    Now uses an async-first approach with a central request handler.
    """
    def __init__(self, addon: xbmcaddon.Addon) -> None:
        self._addon = addon
        self._session_manager = SessionManager.get_instance()

    async def _handle_request(self, method: str, url: str, params: Optional[Dict] = None, payload: Optional[Dict] = None) -> Dict:
        _log(xbmc.LOGINFO, f"API Request (MOCK): {method} {url}")
        # In a real implementation, this is where the async HTTP call would happen.
        # session = self._session_manager.get_session()
        # async with session.request(method, url, params=params, json=payload) as response:
        #     response.raise_for_status()
        #     return await response.json()
        if "GetPage?pageId=Home" in url:
            return self._get_mock_home_response()
        elif "GetPage?pageId=" in url:
            return self._get_mock_rail_items_response()
        elif "Search" in url:
            return self._get_mock_search_response(query=params.get("query", ""))
        elif "GetPlaybackResources" in url:
            return self._get_mock_playback_response()
        raise BackendError(f"No mock response for API call: {url}")

    async def get_home_rails(self) -> List[Dict[str, Any]]:
        if not self._session_manager.is_logged_in(): raise AuthenticationError("User is not logged in.")
        response = await self._handle_request("GET", constants.URLS["home"], params=constants.DEVICE_INFO)
        return self._parse_rails_from_widgets(response)
        
    async def get_rail_items(self, rail_id: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not self._session_manager.is_logged_in(): raise AuthenticationError("User is not logged in.")
        url = constants.URLS["rail_items"].format(rail_id=rail_id)
        params = {**constants.DEVICE_INFO, "page": cursor or 1}
        response = await self._handle_request("GET", url, params=params)
        return self._parse_items_from_collection(response)
        
    async def search(self, query: str, cursor: Optional[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not self._session_manager.is_logged_in(): raise AuthenticationError("User is not logged in.")
        url = constants.URLS["search"].format(query=query)
        params = {"query": query}
        response = await self._handle_request("GET", url, params=params)
        return self._parse_items_from_collection(response)

    async def get_playable(self, asin: str) -> Playable:
        if not self._session_manager.is_logged_in(): raise AuthenticationError("User is not logged in.")
        payload = {**constants.DEVICE_INFO, "asin": asin}
        response = await self._handle_request("POST", constants.URLS["get_playback"], payload=payload)
        return self._parse_playback_resources(response, asin)

    def _parse_rails_from_widgets(self, response: Dict) -> List[Dict[str, Any]]:
        rails = []
        for item in response.get("widgets", []):
            if item.get("type") == "RailWidget":
                rails.append({"id": item.get("id"), "title": item.get("title", {}).get("default"), "type": "mixed"})
        return rails

    def _parse_items_from_collection(self, response: Dict) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        return response.get("items", []), response.get("nextPageCursor")

    def _parse_playback_resources(self, response: Dict, asin: str) -> Playable:
        return Playable(
            url=response.get("manifestUrl"), manifest_type="mpd", license_key=response.get("licenseUrl"),
            headers={}, metadata={"title": f"Playable for {asin}"}
        )

    # (login, logout, etc., and mock response generators remain)
# ... (rest of file as before)
