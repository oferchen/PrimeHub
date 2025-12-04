"""
Native backend for Prime Video, communicating directly with Amazon's APIs.
This module demonstrates the use of several design patterns:
- Singleton: get_backend() ensures a single instance of the PrimeAPI.
- Facade: PrimeAPI provides a simplified interface to the complex backend.
- Strategy: _NativeAPIIntegration is a strategy for backend communication.
- Adapter: normalize_rail and normalize_item adapt backend data for the UI.
"""
from __future__ import annotations

import json # Required for session serialization
import os   # Required for file path operations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import sys
import os

# Add vendor directory to sys.path for bundled libraries
# prime_api.py is in resources/lib/backend/
# Vendor directory is in resources/lib/vendor/
vendor_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'vendor'))
if vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

# Import requests for making HTTP calls. Note: This library will need to be
# bundled with the Kodi add-on or ensured as a dependency.
import requests

try:
    import xbmc
    import xbmcaddon
    import xbmcvfs # Required for file system operations in Kodi
except ImportError:
    from ...tests.kodi_mocks import xbmc, xbmcaddon, xbmcvfs # Mocks from tests/kodi_mocks.py

# --- Data Models ---

@dataclass
class Playable:
    url: str
    manifest_type: str
    license_key: Optional[str]
    headers: Dict[str, str]
    metadata: Dict[str, Any]

# --- Exceptions ---

class BackendError(RuntimeError):
    """Raised for general backend errors."""

class AuthenticationError(BackendError):
    """Raised for login/authentication failures."""

# --- Strategy Pattern: Concrete Strategy ---

class _NativeAPIIntegration:
    """
    The concrete implementation of the backend communication strategy,
    handling direct HTTP requests to Amazon's APIs.
    """
    def __init__(self, addon: xbmcaddon.Addon) -> None:
        self._addon = addon
        self._session_path = os.path.join(addon.getAddonInfo('profile'), 'session.json')
        self._session: Optional[requests.Session] = None
        self._load_session()

    def _load_session(self) -> None:
        """Loads a previously saved session from disk."""
        _log(xbmc.LOGINFO, "Attempting to load session.")
        if xbmcvfs.exists(self._session_path):
            try:
                with xbmcvfs.File(self._session_path, 'r') as f:
                    session_data = json.loads(f.read())
                
                self._session = requests.Session()
                # Reconstruct cookies
                self._session.cookies.update(session_data.get('cookies', {}))
                # TODO: Reconstruct other session aspects like headers if necessary
                _log(xbmc.LOGINFO, "Session loaded successfully.")
                
                # Robust check after loading: ping a protected endpoint
                if not self._verify_session():
                    _log(xbmc.LOGWARNING, "Loaded session is invalid. Clearing.")
                    self.logout() # Clear invalid session
            except Exception as e:
                _log(xbmc.LOGERROR, f"Failed to load session: {e}")
                self.logout() # Clear corrupted session
        else:
            _log(xbmc.LOGINFO, "No session file found.")
            self._session = requests.Session() # Initialize a new session if none exists

    def _save_session(self) -> None:
        """Saves the current session to disk."""
        if self._session and self._session.cookies:
            _log(xbmc.LOGINFO, "Saving session.")
            session_data = {
                'cookies': requests.utils.dict_from_cookiejar(self._session.cookies),
                # TODO: Save other session aspects like headers if necessary
            }
            try:
                with xbmcvfs.File(self._session_path, 'w') as f:
                    f.write(json.dumps(session_data))
                _log(xbmc.LOGINFO, "Session saved successfully.")
            except Exception as e:
                _log(xbmc.LOGERROR, f"Failed to save session: {e}")
        else:
            _log(xbmc.LOGINFO, "No active session to save.")

    def _verify_session(self) -> bool:
        """Pings a protected Amazon endpoint to verify session validity."""
        if not self._session:
            return False
        
        # TODO: Implement a lightweight API call to a protected endpoint.
        # This is highly dependent on Amazon's API. For now, a mock check.
        _log(xbmc.LOGINFO, "Verifying session validity (mock).")
        # Example: response = self._session.get("https://www.amazon.com/gp/your-account/order-history")
        # return response.status_code == 200 and "Sign-in" not in response.text
        return True # Mock always valid for now

    def login(self, username: str, password: str) -> bool:
        """
        Handles the authentication flow with Amazon.
        This is a stub and needs a real implementation.
        """
        _log(xbmc.LOGINFO, f"Attempting login for user: {username}")
        
        # Ensure a fresh session for login attempt
        self.logout() 
        self._session = requests.Session()

        login_page_url = "https://www.amazon.com/ap/signin"
        try:
            login_page_response = self._session.get(login_page_url, timeout=10)
            login_page_response.raise_for_status()
        except requests.exceptions.RequestException as e:
            _log(xbmc.LOGERROR, f"Failed to fetch login page: {e}")
            raise AuthenticationError("Could not reach Amazon login page.")

        # TODO: Parse login_page_response.text to find CSRF token and other hidden form fields.
        # This requires detailed knowledge of Amazon's current login page HTML structure.
        # Example: extracted_csrf_token = extract_csrf_from_html(login_page_response.text)
        extracted_csrf_token = "mock_csrf_token" # Placeholder

        login_data = {
            "email": username,
            "password": password,
            "csrf_token": extracted_csrf_token, # Example form data
            "appActionToken": "mock_appActionToken", # Other potential fields
            "appAction": "SIGNIN",
            "metadata1": "mock_metadata1" # Add any other fields Amazon's form requires
        }
        post_response = self._session.post(login_page_url, data=login_data, allow_redirects=True, timeout=10)
        
        # TODO: Robustly check post_response for successful login.
        # This is highly dependent on Amazon's current login flow.
        if "ap/signin" not in post_response.url and self._verify_session(): # Basic check for redirection + session validity
            _log(xbmc.LOGINFO, "Login successful (mock implementation based on redirection).")
            self._save_session() # Save session on successful login
            return True
        else:
            _log(xbmc.LOGWARNING, "Login failed (mock implementation). Check credentials.")
            self.logout()
            raise AuthenticationError("Invalid username or password, or other login issue.")

    def logout(self) -> None:
        """Clears the current session and deletes saved session data."""
        _log(xbmc.LOGINFO, "Logging out.")
        if self._session:
            self._session.close()
        self._session = None
        if xbmcvfs.exists(self._session_path):
            xbmcvfs.delete(self._session_path)
            _log(xbmc.LOGINFO, "Session file deleted.")

    def is_logged_in(self) -> bool:
        """Checks if a valid session exists."""
        return self._session is not None and self._verify_session()

    def get_home_rails(self) -> List[Dict[str, Any]]:
        """
        Fetches home screen content (rails) from the backend.
        This is a stub and should return mock data.
        """
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")
        
        _log(xbmc.LOGINFO, "Fetching home rails (mock data).")
        # TODO: Implement actual API call to fetch home rails.
        # For now, return mock data.
        return [
            {"id": "continue_watching", "title": "Continue Watching", "type": "mixed"},
            {"id": "movies", "title": "Movies", "type": "movies"},
            {"id": "tv", "title": "TV Shows", "type": "tv"},
        ]

    def add_to_watchlist(self, asin: str) -> bool:
        """
        Adds an item to the user's watchlist.
        This is a stub and needs a real implementation.
        """
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")
        _log(xbmc.LOGINFO, f"Adding {asin} to watchlist (stub).")
        # TODO: Implement actual API call to add to watchlist.
        return True # Mock success

    def mark_as_watched(self, asin: str, watched_status: bool) -> bool:
        """
        Marks an item as watched or unwatched.
        This is a stub and needs a real implementation.
        """
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")
        status = "watched" if watched_status else "unwatched"
        _log(xbmc.LOGINFO, f"Marking {asin} as {status} (stub).")
        # TODO: Implement actual API call to mark as watched.
        return True # Mock success


# --- Facade & Singleton Patterns ---

class PrimeAPI:
    """
    Provides a simplified, unified interface (Facade) to the backend.
    The get_backend() function ensures that only one instance of this class
    is created (Singleton).
    """
    def __init__(self, addon: xbmcaddon.Addon) -> None:
        # The strategy is now hardcoded to our native implementation
        self._strategy = _NativeAPIIntegration(addon)

    def login(self, username: str, password: str) -> bool:
        return self._strategy.login(username, password)

    def logout(self) -> None:
        self._strategy.logout()

    def is_logged_in(self) -> bool:
        return self._strategy.is_logged_in()

    def get_home_rails(self) -> List[Dict[str, Any]]:
        # The Facade calls the strategy, and the Adapter normalizes the data
        raw_rails = self._strategy.get_home_rails()
        return [normalize_rail(rail) for rail in raw_rails]

    def add_to_watchlist(self, asin: str) -> bool:
        return self._strategy.add_to_watchlist(asin)

    def mark_as_watched(self, asin: str, watched_status: bool) -> bool:
        return self._strategy.mark_as_watched(asin, watched_status)

    # ... Other facade methods mirroring the strategy ...


_backend_instance: Optional[PrimeAPI] = None

def get_backend() -> PrimeAPI:
    """Factory function to get the singleton backend instance."""
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = PrimeAPI(xbmcaddon.Addon())
    return _backend_instance


# --- Adapter Pattern ---

def normalize_rail(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapts the raw rail data from the backend into a consistent format
    for the UI.
    """
    return {
        "id": str(raw.get("id") or ""),
        "title": str(raw.get("title") or ""),
        "type": str(raw.get("type") or "mixed"),
    }

def normalize_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapts the raw item data from the backend into a consistent format
    for the UI. (Stub for now)
    """
    return raw

# --- Logging ---

def _log(level: int, message: str) -> None:
    xbmc.log(f"[PrimeHub-Native] {message}", level)