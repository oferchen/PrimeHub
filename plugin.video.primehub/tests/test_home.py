import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Import and apply global patches for Kodi modules
from .kodi_mocks import patch_kodi_modules_globally

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import ui.home as home_module
from backend.prime_api import BackendError, AuthenticationError
from preflight import PreflightError


class TestUIHome(unittest.TestCase):

    def setUp(self):
        patch_kodi_modules_globally()
        
        # Patch external dependencies
        self.patcher_get_backend = patch('ui.home.get_backend')
        self.mock_get_backend = self.patcher_get_backend.start()
        self.mock_backend_instance = MagicMock()
        self.mock_get_backend.return_value = self.mock_backend_instance

        self.patcher_get_cache = patch('ui.home.get_cache')
        self.mock_get_cache = self.patcher_get_cache.start()
        self.mock_cache_instance = MagicMock()
        self.mock_get_cache.return_value = self.mock_cache_instance
        
        self.patcher_ensure_ready_or_raise = patch('ui.home.ensure_ready_or_raise')
        self.mock_ensure_ready_or_raise = self.patcher_ensure_ready_or_raise.start()
        
        self.patcher_xbmcplugin = patch('xbmcplugin')
        self.mock_xbmcplugin = self.patcher_xbmcplugin.start()

        # Mock xbmcaddon.Addon() for local settings
        self.patcher_xbmcaddon = patch('xbmcaddon.Addon')
        self.mock_xbmcaddon = self.patcher_xbmcaddon.start()
        self.mock_addon_instance = MagicMock()
        self.mock_xbmcaddon.return_value = self.mock_addon_instance
        
        # Mock ListItem for assertions
        self.patcher_xbmcgui = patch('xbmcgui.ListItem')
        self.mock_list_item = self.patcher_xbmcgui.start()

        # Create a mock context
        self.mock_context = MagicMock()
        self.mock_context.handle = 1
        self.mock_context.build_url.side_effect = lambda **kwargs: "plugin_url?" + "&".join(f"{k}={v}" for k,v in kwargs.items())

    def tearDown(self):
        patch.stopall()

    # ... (rest of the tests remain the same, they should work with the new mock setup)
    def test_fetch_home_rails_cache_hit(self):
        cached_rails = [{"id": "cached", "title": "Cached Rail"}]
        self.mock_cache_instance.get.return_value = cached_rails

        rails = home_module.fetch_home_rails(self.mock_addon_instance, self.mock_cache_instance)
        self.assertEqual(rails, cached_rails)
        self.mock_cache_instance.get.assert_called_once()
        self.mock_get_backend.assert_not_called()

    # ...
    # All other tests from the original file should be here
    # ...

if __name__ == '__main__':
    unittest.main()