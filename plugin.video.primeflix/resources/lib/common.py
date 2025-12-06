"""
Common utilities and singleton classes for the PrimeHub add-on.
This mirrors the structure found in the Sandmann79 codebase, providing
a centralized way to manage global state and settings.
"""
from __future__ import annotations
import os
from typing import Optional

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    from xbmcvfs import translatePath
except ImportError:
    from ...tests.kodi_mocks import xbmc, xbmcaddon, xbmcgui, translatePath

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class Globals(metaclass=Singleton):
    """A singleton for managing global state and objects."""
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.dialog = xbmcgui.Dialog()
        self.pluginid = "plugin.video.primeflix"
        self.DATA_PATH = translatePath(self.addon.getAddonInfo('profile'))
        self.PLUGIN_PATH = translatePath(self.addon.getAddonInfo('path'))
        
        # Marketplace/Region info (will be updated by the backend)
        self.MarketID = "ATVPDKIKX0DER" # Default to US
        self.BaseUrl = "https://www.amazon.com"
        self.ATVUrl = "https://atv-ps.amazon.com"

class Settings(metaclass=Singleton):
    """A singleton for accessing add-on settings."""
    def __init__(self):
        self._g = Globals()
    
    def __getattr__(self, name):
        # In a real implementation, this would handle type conversions.
        return self._g.addon.getSetting(name)
