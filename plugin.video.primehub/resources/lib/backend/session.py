"""
Session Manager for handling a persistent requests.Session object.
"""
from __future__ import annotations
import json
import os
import requests
from typing import Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import xbmc
    import xbmcaddon
    import xbmcvfs
except ImportError:
    from ...tests.kodi_mocks import xbmc, xbmcaddon, xbmcvfs

def _log(level: int, message: str) -> None:
    xbmc.log(f"[PrimeHub-Session] {message}", level)

class SessionManager:
    _instance: Optional["SessionManager"] = None

    def __init__(self) -> None:
        if SessionManager._instance is not None:
            raise RuntimeError("Use get_instance() to get the singleton instance.")
        
        self._addon = xbmcaddon.Addon()
        self._session_path = os.path.join(self._addon.getAddonInfo('profile'), 'session.json')
        self._session: Optional[requests.Session] = None
        self._load_session()

    @classmethod
    def get_instance(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = SessionManager()
        return cls._instance

    def get_session(self) -> requests.Session:
        if self._session is None:
            session = requests.Session()
            retries = Retry(total=6, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504, 408, 429])
            adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retries)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            self._session = session
        return self._session

    def _load_session(self) -> None:
        # ... (rest of the file remains the same)
        pass
    
    def save_session(self) -> None:
        # ...
        pass
        
    def logout(self) -> None:
        # ...
        pass