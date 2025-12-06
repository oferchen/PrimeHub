"""
Native backend for Prime Video, communicating directly with Amazon's APIs.
This module is a refactored, native implementation based on the analysis
of the Sandmann79 Amazon VOD add-on. It aims to replicate the original
plugin's core logic for API interaction, data parsing, and session management.
"""
from __future__ import annotations
from collections import OrderedDict
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple
import sys
import os

# Add vendor directory to sys.path for bundled libraries
vendor_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'vendor'))
if vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

from .common import Globals, Settings, Singleton
from . import network as net

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
except ImportError:
    from ...tests.kodi_mocks import xbmc, xbmcaddon, xbmcgui

class PrimeVideo(metaclass=Singleton):
    """
    Wrangler of all things PrimeVideo.com. This class handles all API
    interactions after a session has been established.
    """
    _catalog = {}

    def __init__(self) -> None:
        self._g = Globals()
        self._s = Settings()
        # In a real implementation, we would load a catalog cache here
        
    def BuildRoot(self) -> bool:
        """
        Parses the top menu and builds the root catalog.
        This is a stub that returns a mock catalog.
        """
        self._catalog['root'] = OrderedDict()
        
        # In a real implementation, this would call GrabJSON and parse the result
        # home_data = net.GrabJSON(self._g.BaseUrl + '/gp/video/storefront')
        home_data = {"mainMenu": {"links": [
            {"id": "pv-nav-mystuff", "text": "My Stuff"},
            {"id": "pv-nav-home", "text": "Home", "href": "/"},
            {"id": "pv-nav-movies", "text": "Movies", "href": "/movies"},
        ]}}
        
        self._catalog['root']['Watchlist'] = {'title': 'Watchlist', 'lazyLoadURL': '/watchlist'}
        
        for link in home_data.get("mainMenu", {}).get("links", []):
            if "mystuff" not in link.get("id", ""):
                self._catalog['root'][link['id']] = {'title': link['text'], 'lazyLoadURL': link.get('href')}
                
        self._catalog['root']['Search'] = {'title': 'Search', 'endpoint': '/gp/video/search?phrase={}'}
        return True

    def Browse(self, path: str) -> Tuple[List[Dict], Optional[str]]:
        """
        "Browses" a path in the catalog, returning items and a next page cursor.
        This is a stub that returns mock data.
        """
        if not self._catalog: self.BuildRoot()
        
        if path == 'root':
            # Return the main menu items
            items = list(self._catalog['root'].values())
            return items, None
        else:
            # Return mock rail items
            items = [{"asin": "B012345", "title": "The Grand Tour"}, {"asin": "B067890", "title": "The Boys"}]
            return items, "nextPageCursor"

    def Search(self, query: str) -> Tuple[List[Dict], Optional[str]]:
        """Performs a search."""
        return [{"asin": f"B0SEARCH{i}", "title": f"Search Result {i+1} for {query}"} for i in range(2)], None

    def GetStream(self, asin: str) -> Tuple[bool, Dict | str]:
        """Gets playback resources for a given ASIN."""
        # This would call net.getURLData in a real implementation
        # success, data = net.getURLData("catalog/GetPlaybackResources", asin)
        success, data = True, {
            "manifestUrl": "http://mock.playback/manifest.mpd",
            "licenseUrl": "http://mock.license/server"
        }
        return success, data

    def is_drm_ready(self) -> bool:
        # In a real implementation, this would check for Widevine CDM
        return True

# This is now a simple factory function for the PrimeVideo Singleton
def get_prime_video() -> PrimeVideo:
    return PrimeVideo()