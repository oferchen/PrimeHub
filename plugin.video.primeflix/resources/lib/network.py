"""
Network utility functions for making API calls.
This module replicates the structure of the network functions found in
the Sandmann79 codebase, providing a framework for handling HTTP requests,
cookies, and JSON parsing.
"""
from __future__ import annotations
import json
import os
from typing import Optional, Dict

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
except ImportError:
    from ...tests.kodi_mocks import xbmc, xbmcaddon, xbmcgui

from .common import Globals, Settings
from .session import SessionManager

_g = Globals()
_s = Settings()

def getURL(url: str, useCookie: bool = False, headers: Optional[Dict] = None, postdata: Optional[Dict] = None) -> str:
    """
    Makes a mock HTTP request and returns the raw response text.
    In a real implementation, this would use requests.
    """
    _log(xbmc.LOGINFO, f"getURL (MOCK): to {url}")
    # In a real implementation, this would use the session to make the call.
    # session = SessionManager.get_instance().get_session()
    # response = session.request(...)
    # For now, return a mock empty HTML page.
    return "<html><body>Mock Response</body></html>"

def GrabJSON(url: str, postData: Optional[Dict] = None) -> Dict:
    """
    Extracts JSON from a URL, simulating the GrabJSON logic.
    """
    _log(xbmc.LOGINFO, f"GrabJSON (MOCK): from {url}")
    # This simulates finding JSON within an HTML page or getting it directly.
    # A real implementation would parse the response from getURL.
    if "storefront" in url: # For BuildRoot
        return {"widgets": [{"type": "RailWidget", "id": "home_rail", "title": {"default": "Home Rail"}}]}
    return {} # Default empty JSON

def getURLData(mode: str, asin: str, **kwargs) -> Tuple[bool, Dict | str]:
    """
    Constructs an ATV API URL and returns mock data, simulating getURLData.
    """
    url = f"{_g.ATVUrl}/cdp/{mode}?asin={asin}"
    _log(xbmc.LOGINFO, f"getURLData (MOCK): for {url}")

    if mode == "catalog/GetPlaybackResources":
        return True, {
            "manifestUrl": "http://mock.playback/manifest.mpd",
            "licenseUrl": "http://mock.license/server"
        }
    return False, "Unknown mode in getURLData"

def _log(level: int, message: str) -> None:
    xbmc.log(f"[PrimeHub-Network] {message}", level)
