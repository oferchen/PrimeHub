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
from .session import SessionManager # Use the new SessionManager

try:
    import xbmc
    import xbmcaddon
except ImportError:
    from ...tests.kodi_mocks import xbmc, xbmcaddon

# (Data Models and Exceptions remain the same)

class _NativeAPIIntegration:
    """
    The concrete implementation of the backend communication strategy.
    """
    def __init__(self, addon: xbmcaddon.Addon) -> None:
        self._addon = addon
        self._session_manager = SessionManager.get_instance()
        self._session = self._session_manager.get_session()

    def login(self, username: str, password: str) -> bool:
        """Handles the authentication flow with Amazon."""
        _log(xbmc.LOGINFO, f"Attempting login for user: {username}")
        
        # Logout to ensure a fresh session
        self._session_manager.logout()
        self._session = self._session_manager.get_session()

        # ... (stubbed login logic remains the same)
        # On success:
        self._session_manager.save_session()
        return True

    def logout(self) -> None:
        """Delegates logout to the SessionManager."""
        self._session_manager.logout()
        self._session = None # Ensure local reference is cleared

    def is_logged_in(self) -> bool:
        """Checks if a valid session exists via the SessionManager."""
        # A more robust check would ping a protected Amazon endpoint.
        session = self._session_manager.get_session()
        return session is not None and len(session.cookies) > 0

    # ... (other stubbed methods remain the same)
    def get_home_rails(self) -> List[Dict[str, Any]]:
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")
        return []

    def add_to_watchlist(self, asin: str) -> bool:
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")
        return True
        
    def mark_as_watched(self, asin: str, watched_status: bool) -> bool:
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")
        return True

# (PrimeAPI Facade, get_backend Singleton, and Adapters remain the same)
# ... (rest of the file)
