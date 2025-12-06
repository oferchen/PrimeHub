"""
Network utility functions for making API calls, conforming to API_DOCS.md.
"""
from __future__ import annotations
from typing import Optional, Dict, Tuple

try:
    import xbmc
except ImportError:
    from ...tests.kodi_mocks import xbmc

from .session import SessionManager

def _log(level: int, message: str) -> None:
    xbmc.log(f"[PrimeHub-Network] {message}", level)

def getURL(url: str, useCookie: bool = False, headers: Optional[Dict] = None, postdata: Optional[Dict] = None) -> str:
    _log(xbmc.LOGINFO, f"getURL (MOCK) to {url}")
    # In a real implementation, this would use the session to make a request.
    return "<html><body>Mock HTML Response</body></html>"

def GrabJSON(url: str, postData: Optional[Dict] = None) -> Dict:
    _log(xbmc.LOGINFO, f"GrabJSON (MOCK) from {url}")
    if "storefront" in url:
        return {"mainMenu": {"links": [{"id": "pv-nav-movies", "text": "Movies", "href": "/movies"}]}}
    elif "search" in url:
        return {"items": [{"asin": "B0SEARCH", "title": "Mock Search Result"}]}
    else: # For a rail
        return {"items": [{"asin": "B0RAILITEM", "title": "Mock Rail Item"}]}

def getURLData(mode: str, asin: str, **kwargs) -> Tuple[bool, Dict | str]:
    _log(xbmc.LOGINFO, f"getURLData (MOCK) for {mode} with asin {asin}")
    if mode == "catalog/GetPlaybackResources":
        return (True, {
            "manifestUrl": "http://mock.playback/manifest.mpd",
            "licenseUrl": "http://mock.license/server"
        })
    return (False, "Unknown mode in getURLData")

def MechanizeLogin(username, password) -> requests.Session:
    _log(xbmc.LOGINFO, f"MechanizeLogin (MOCK) for user {username}")
    # This would perform the complex, multi-step login.
    # For now, it just returns the current session.
    return SessionManager.get_instance().get_session()