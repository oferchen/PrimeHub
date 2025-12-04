# Mock objects for running outside of Kodi
from unittest.mock import MagicMock
import os
import sys

# --- Mock Classes for Kodi Components ---

# xbmc module mocks
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    def log(self, message: str, level: int = 0) -> None:
        pass # Suppress logging during tests

    def executeJSONRPC(self, payload: str) -> str:
        return '{"result": {}}' # Default empty result for JSONRPC

# xbmcaddon module mocks
class MockXBMCAddon:
    def Addon(self, addon_id=None):
        mock_addon = MagicMock()
        mock_addon.getAddonInfo.side_effect = lambda key: {
            "id": addon_id or "plugin.video.primeflix",
            "profile": "/mock/path/to/profile",
            "path": "/mock/path/to/addon",
            "fanart": "/mock/path/to/fanart.jpg",
            "name": "PrimeHub"
        }.get(key, "")
        mock_addon.getSetting.side_effect = lambda key: {
            "region": "0", # us
            "max_resolution": "0", # auto
            "use_cache": "true",
            "cache_ttl": "300",
            "perf_logging": "false",
        }.get(key, "0")
        mock_addon.getSettingBool.side_effect = lambda key: {
            "use_cache": True,
            "perf_logging": False,
        }.get(key, False)
        mock_addon.getSettingInt.side_effect = lambda key: {
            "cache_ttl": 300,
        }.get(key, 0)
        mock_addon.getLocalizedString.side_effect = (
            lambda code: f"LocalizedString_{code}"
        )
        return mock_addon

# xbmcgui module mocks
class MockXBMCGUI:
    INPUT_PASSWORD = 1
    NOTIFICATION_INFO = 1
    NOTIFICATION_WARNING = 2
    NOTIFICATION_ERROR = 3

    Dialog = MagicMock() # Mock the Dialog class itself
    ListItem = MagicMock() # Mock the ListItem class itself

# xbmcplugin module mocks
class MockXBMCPlugin:
    SORT_METHOD_UNSORTED = 0
    def addDirectoryItems(self, handle, items): pass
    def endOfDirectory(self, handle, succeeded=True): pass
    def setContent(self, handle, content): pass
    def setResolvedUrl(self, handle, succeeded, listitem): pass

# xbmcvfs module mocks
class MockXBMCRuntime:
    def exists(self, path): return False
    def mkdirs(self, path): pass
    def translatePath(self, path): return path
    def delete(self, path): pass
    def File(self, path, mode='r'):
        mock_file = MagicMock()
        mock_file.read.return_value = ''
        mock_file.__enter__.return_value = mock_file
        return mock_file

# --- Centralized Patching of sys.modules for Kodi components ---
# This ensures that when any module imports xbmc, xbmcaddon, etc., they get our mocks.
def patch_kodi_modules_globally():
    sys.modules["xbmc"] = MockXBMC()
    sys.modules["xbmcaddon"] = MockXBMCAddon()
    sys.modules["xbmcgui"] = MockXBMCGUI()
    sys.modules["xbmcplugin"] = MockXBMCPlugin()
    sys.modules["xbmcvfs"] = MockXBMCRuntime()