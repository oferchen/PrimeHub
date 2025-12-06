"""UI for handling login."""
from __future__ import annotations
try:
    import xbmcgui
except ImportError:
    from ...tests.kodi_mocks import xbmcgui

from ..common import Globals
from ..backend.prime_api import get_prime_video

def show_login_screen() -> bool:
    """Displays a dialog for login and returns True on success."""
    g = Globals()
    pv = get_prime_video()
    
    # This would be a more complex flow in reality, potentially with a custom window
    username = g.dialog.input("Username")
    if not username: return False
    
    password = g.dialog.input("Password", option=xbmcgui.INPUT_PASSWORD)
    if not password: return False

    # The login logic would be more sophisticated, with error handling
    # success = pv.login(username, password)
    # For now, we'll just assume it works for the stub.
    g.dialog.notification("Login", "Login successful (mock).")
    return True