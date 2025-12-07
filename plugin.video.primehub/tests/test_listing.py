import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Import and apply global patches for Kodi modules
from .kodi_mocks import patch_kodi_modules_globally, MockXBMCGUI

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import ui.listing as listing_module
from backend.prime_api import BackendError, BackendUnavailable
from preflight import PreflightError


class TestUIListing(unittest.TestCase):

    def setUp(self):
        patch_kodi_modules_globally()
        
        # Patch external dependencies
        self.patcher_get_backend = patch('ui.listing.get_backend')
        self.mock_get_backend = self.patcher_get_backend.start()
        self.mock_backend_instance = MagicMock()
        self.mock_get_backend.return_value = self.mock_backend_instance

        self.patcher_get_cache = patch('ui.listing.get_cache')
        self.mock_get_cache = self.patcher_get_cache.start()
        self.mock_cache_instance = MagicMock()
        self.mock_get_cache.return_value = self.mock_cache_instance
        
        self.patcher_ensure_ready_or_raise = patch('ui.listing.ensure_ready_or_raise')
        self.mock_ensure_ready_or_raise = self.patcher_ensure_ready_or_raise.start()
        
        # Mock xbmcplugin and xbmcgui from sys.modules
        self.mock_xbmcplugin = sys.modules['xbmcplugin']
        self.mock_xbmcgui = sys.modules['xbmcgui']
        self.mock_xbmcaddon = sys.modules['xbmcaddon']

        # Mock ListItem and Dialog for assertions
        self.mock_list_item_instance = self.mock_xbmcgui.ListItem.return_value
        self.mock_dialog_instance = self.mock_xbmcgui.Dialog.return_value


        # Create a mock context
        self.mock_context = MagicMock()
        self.mock_context.handle = 1
        self.mock_context.build_url.side_effect = lambda **kwargs: "plugin_url?" + "&".join(f"{k}={v}" for k,v in kwargs.items())

    def tearDown(self):
        patch.stopall()

    # ... (rest of the tests remain the same)
    def test_show_list_cache_hit(self):
        cached_data = {"items": [{"asin": "c1", "title": "Cached Item"}], "next": None}
        self.mock_cache_instance.get.return_value = cached_data
        
        listing_module.show_list(self.mock_context, "my_rail")
        
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_cache_instance.get.assert_called_once_with("rail:my_rail:root", ttl_seconds=300)
        self.mock_backend_instance.get_rail_items.assert_not_called()
        self.mock_xbmcplugin.addDirectoryItems.assert_called_once()

if __name__ == '__main__':
    unittest.main()