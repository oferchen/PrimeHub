"""
Native backend for Prime Video, communicating directly with Amazon's APIs.
This module demonstrates the use of several design patterns:
- Singleton: get_backend() ensures a single instance of the PrimeAPI.
- Facade: PrimeAPI provides a simplified interface to the complex backend.
- Strategy: _NativeAPIIntegration is a strategy for backend communication.
- Adapter: normalize_rail and normalize_item adapt backend data for the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import xbmc
    import xbmcaddon
except ImportError:
    from .mock_kodi import xbmc, xbmcaddon

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
        self._session = None # Placeholder for HTTP session (e.g., requests.Session)
        # TODO: Implement session loading/saving from/to disk

    def login(self, username: str, password: str) -> bool:
        """
        Handles the authentication flow with Amazon.
        This is a stub and needs a real implementation.
        """
        _log(xbmc.LOGINFO, f"Attempting login for user: {username}")
        # TODO: Implement actual login logic (e.g., using requests library)
        # This would involve POSTing to Amazon's login endpoints, handling MFA,
        # and storing session cookies.
        if username and password:
            self._session = {"cookie": "mock_session_cookie"} # Mock session
            return True
        return False

    def logout(self) -> None:
        """Clears the current session."""
        _log(xbmc.LOGINFO, "Logging out.")
        self._session = None

    def is_logged_in(self) -> bool:
        """Checks if a valid session exists."""
        return self._session is not None

    def get_home_rails(self) -> List[Dict[str, Any]]:
        """
        Fetches home screen content (rails) from the backend.
        This is a stub and should return mock data.
        """
        if not self.is_logged_in():
            raise AuthenticationError("User is not logged in.")
        
        # TODO: Implement actual API call to fetch home rails.
        # For now, return mock data.
        return [
            {"id": "continue_watching", "title": "Continue Watching", "type": "mixed"},
            {"id": "movies", "title": "Movies", "type": "movies"},
            {"id": "tv", "title": "TV Shows", "type": "tv"},
        ]

    # ... Other methods like get_rail_items, get_playable, search would follow ...
    # These would also be stubs for now.


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
