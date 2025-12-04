"""UI for handling login."""
from __future__ import annotations

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
except ImportError:
    from ...tests.kodi_mocks import MockXBMC as xbmc
    from ...tests.kodi_mocks import MockXBMCAddon as xbmcaddon
    from ...tests.kodi_mocks import MockXBMCGUI as xbmcgui

from .prime_api import get_backend, AuthenticationError

def show_login_screen() -> bool:
    """
    Displays a dialog to prompt for username and password and attempts to log in.
    Returns True on successful login, False otherwise.
    """
    addon = xbmcaddon.Addon()
    dialog = xbmcgui.Dialog()
    
    username = dialog.input(addon.getLocalizedString(32001)) # "Username"
    if not username:
        return False
        
    password = dialog.input(addon.getLocalizedString(32002), option=xbmcgui.INPUT_PASSWORD) # "Password"
    if not password:
        return False

    backend = get_backend()
    try:
        if backend.login(username, password):
            dialog.ok(addon.getLocalizedString(32003), addon.getLocalizedString(32004)) # "Login Successful", "You are now logged in."
            return True
        else:
            dialog.ok(addon.getLocalizedString(32005), addon.getLocalizedString(32006)) # "Login Failed", "Please check your credentials."
            return False
    except AuthenticationError as e:
        dialog.ok(addon.getLocalizedString(32005), str(e))
        return False
