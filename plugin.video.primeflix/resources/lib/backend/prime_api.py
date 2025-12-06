"""
Native backend for Prime Video, conforming to API_DOCS.md.
"""
from __future__ import annotations
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from ..common import Globals, Settings, Singleton
from .. import network as net
from .session import SessionManager

try:
    import xbmc
except ImportError:
    from ...tests.kodi_mocks import xbmc

class PrimeVideo(metaclass=Singleton):
    _catalog = {}

    def __init__(self) -> None:
        self._g = Globals()
        self._s = Settings()
        self._session_manager = SessionManager.get_instance()

    def login(self, username, password) -> bool:
        session = net.MechanizeLogin(username, password)
        # The mock MechanizeLogin now adds a cookie, so we can check for it
        return "session-id" in session.cookies

    def BuildRoot(self) -> bool:
        if not self._session_manager.is_logged_in(): return False
        data = net.GrabJSON(f"{self._g.BaseUrl}/gp/video/storefront")
        self._catalog['root'] = self._parse_main_menu(data)
        return True

    def Browse(self, path: str) -> Tuple[List[Dict], Optional[str]]:
        if not self._catalog: self.BuildRoot()
        if path == 'root':
            return list(self._catalog.get('root', {}).values()), None
        
        # This simulates a _LazyLoad call for a specific rail
        data = net.GrabJSON(f"{self._g.BaseUrl}{path}")
        return self._parse_item_list(data)

    def Search(self, query: str) -> Tuple[List[Dict], Optional[str]]:
        data = net.GrabJSON(f"{self._g.BaseUrl}/gp/video/search?phrase={query}")
        return self._parse_item_list(data)

    def GetStream(self, asin: str) -> Tuple[bool, Dict | str]:
        return net.getURLData("catalog/GetPlaybackResources", asin)

    def _parse_main_menu(self, data: Dict) -> OrderedDict:
        menu = OrderedDict()
        links = data.get("mainMenu", {}).get("links", [])
        for link in links:
            if "mystuff" not in link.get("id", ""):
                menu[link['id']] = {'title': link['text'], 'lazyLoadURL': link.get('href')}
        return menu

    def _parse_item_list(self, data: Dict) -> Tuple[List[Dict], Optional[str]]:
        items = data.get("items", [])
        next_page = data.get("nextPageCursor")
        return items, next_page

def get_prime_video() -> PrimeVideo:
    return PrimeVideo()