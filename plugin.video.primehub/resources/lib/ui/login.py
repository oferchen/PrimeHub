"""UI for handling login, inspired by Sandmann79/login.py."""
from __future__ import annotations
try:
    import xbmcgui
except ImportError:
    from ...tests.kodi_mocks import xbmcgui

from ..common import Globals
from ..backend.prime_api import get_prime_video

def show_login_screen() -> bool:
    """
    Displays a dialog for login and calls the backend to handle it.
    """
    g = Globals()
    pv = get_prime_video()
    
    username = g.dialog.input("Username (email)")
    if not username: return False
    
    password = g.dialog.input("Password", option=xbmcgui.INPUT_PASSWORD)
    if not password: return False

    try:
        if pv.login(username, password):
            g.dialog.notification("Login Successful", "You are now logged in.")
            return True
        else:
            g.dialog.ok("Login Failed", "Please check your credentials or logs.")
            return False
    except Exception as e:
        g.dialog.ok("Login Error", f"An unexpected error occurred: {e}")
        return False
