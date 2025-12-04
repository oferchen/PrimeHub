"""
Session Manager for handling a persistent requests.Session object.
This module implements the Singleton design pattern to ensure that only
one instance of the session manager exists throughout the add-on,
providing a single, consistent entry point for all network operations.
"""
from __future__ import annotations
import json
import os
import requests
from typing import Optional

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
        """Get the singleton instance of the SessionManager."""
        if cls._instance is None:
            cls._instance = SessionManager()
        return cls._instance

    def get_session(self) -> requests.Session:
        """Returns the current requests session, creating one if it doesn't exist."""
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _load_session(self) -> None:
        """Loads a previously saved session from disk."""
        _log(xbmc.LOGINFO, "Attempting to load session.")
        if xbmcvfs.exists(self._session_path):
            try:
                with xbmcvfs.File(self._session_path, 'r') as f:
                    session_data = json.loads(f.read())
                
                self._session = requests.Session()
                self._session.cookies.update(session_data.get('cookies', {}))
                _log(xbmc.LOGINFO, "Session loaded successfully.")
            except Exception as e:
                _log(xbmc.LOGERROR, f"Failed to load session: {e}")
                self.logout()
        else:
            _log(xbmc.LOGINFO, "No session file found.")
            self._session = requests.Session()

    def save_session(self) -> None:
        """Saves the current session to disk."""
        if self._session and self._session.cookies:
            _log(xbmc.LOGINFO, "Saving session.")
            session_data = {'cookies': requests.utils.dict_from_cookiejar(self._session.cookies)}
            try:
                with xbmcvfs.File(self._session_path, 'w') as f:
                    f.write(json.dumps(session_data))
                _log(xbmc.LOGINFO, "Session saved successfully.")
            except Exception as e:
                _log(xbmc.LOGERROR, f"Failed to save session: {e}")

    def logout(self) -> None:
        """Clears the current session and deletes saved session data."""
        _log(xbmc.LOGINFO, "Logging out and clearing session data.")
        if self._session:
            self._session.close()
        self._session = None
        if xbmcvfs.exists(self._session_path):
            xbmcvfs.delete(self._session_path)
            _log(xbmc.LOGINFO, "Session file deleted.")
