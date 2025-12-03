import unittest
from unittest.mock import MagicMock, patch, call
import sys
import os
import json

# Mock Kodi imports for testing outside Kodi
class MockXBMC:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 3
    def log(self, message: str, level: int = 0) -> None: pass

class MockXBMCAddon:
    def Addon(self, addon_id=None):
        mock_addon = MagicMock()
        mock_addon.getLocalizedString.side_effect = lambda code: f"LocalizedString_{code}"
        mock_addon.getSettingBool.return_value = True # Default use cache
        mock_addon.getSettingInt.return_value = 300 # Default cache TTL
        mock_addon.getAddonInfo.return_value = "/mock/path/to/fanart.jpg" # Default fanart
        mock_addon.getSetting.side_effect = lambda key: {
            "use_cache": "true",
            "cache_ttl": "300",
        }.get(key, "")
        return mock_addon

class MockXBMCGUI:
    ListItem = MagicMock()
    Dialog = MagicMock()

class MockXBMCPlugin:
    SORT_METHOD_UNSORTED = 0
    def addDirectoryItems(self, handle, items): pass
    def endOfDirectory(self, handle, succeeded=True): pass
    def setContent(self, handle, content): pass

# Patch Kodi modules globally before other imports
sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = MockXBMCAddon()
sys.modules['xbmcgui'] = MockXBMCGUI()
sys.modules['xbmcplugin'] = MockXBMCPlugin()

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import ui.listing as listing_module
from backend.prime_api import BackendError, BackendUnavailable
from preflight import PreflightError


class TestUIListing(unittest.TestCase):

    def setUp(self):
        self.mock_addon_instance = MagicMock(spec=xbmcaddon.Addon)
        self.mock_addon_instance.getLocalizedString.side_effect = lambda code: f"LocalizedString_{code}"
        self.mock_addon_instance.getSettingBool.return_value = True
        self.mock_addon_instance.getSettingInt.return_value = 300
        sys.modules['xbmcaddon'].Addon.return_value = self.mock_addon_instance
        
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
        
        # Mock xbmcplugin methods
        self.patcher_addDirectoryItems = patch.object(sys.modules['xbmcplugin'], 'addDirectoryItems')
        self.mock_addDirectoryItems = self.patcher_addDirectoryItems.start()
        self.patcher_setContent = patch.object(sys.modules['xbmcplugin'], 'setContent')
        self.mock_setContent = self.patcher_setContent.start()

        # Mock xbmcgui.ListItem
        sys.modules['xbmcgui'].ListItem.reset_mock()
        self.mock_list_item = MagicMock()
        sys.modules['xbmcgui'].ListItem.return_value = self.mock_list_item
        
        # Mock xbmcgui.Dialog for search prompt
        self.mock_dialog_instance = MagicMock()
        sys.modules['xbmcgui'].Dialog.return_value = self.mock_dialog_instance


        # Create a mock context
        self.mock_context = MagicMock()
        self.mock_context.handle = 1
        self.mock_context.build_url.side_effect = lambda **kwargs: "plugin_url?" + "&".join(f"{k}={v}" for k,v in kwargs.items())

    def tearDown(self):
        patch.stopall()

    # --- Tests for show_list ---
    def test_show_list_cache_hit(self):
        cached_data = {"items": [{"asin": "c1", "title": "Cached Item"}], "next": None}
        self.mock_cache_instance.get.return_value = cached_data
        
        listing_module.show_list(self.mock_context, "my_rail")
        
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_cache_instance.get.assert_called_once_with("rail:my_rail:root", ttl_seconds=300)
        self.mock_backend_instance.get_rail_items.assert_not_called()
        self.mock_addDirectoryItems.assert_called_once()
        
    def test_show_list_cache_miss_backend_success(self):
        self.mock_cache_instance.get.return_value = None
        self.mock_backend_instance.get_rail_items.return_value = (
            [{"asin": "b1", "title": "Backend Item", "art": {"poster": "p.jpg"}}], "next_page"
        )
        
        listing_module.show_list(self.mock_context, "my_rail")
        
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_cache_instance.get.assert_called_once()
        self.mock_backend_instance.get_rail_items.assert_called_once_with("my_rail", None)
        self.mock_cache_instance.set.assert_called_once()
        self.mock_addDirectoryItems.assert_called_once()
        
        # Verify content of ListItem and addDirectoryItems call
        args, _ = self.mock_addDirectoryItems.call_args
        items = args[1]
        self.assertEqual(len(items), 2) # 1 item + "More..."
        self.assertEqual(self.mock_list_item.setArt.call_args[0][0], {"poster": "p.jpg"})
        
    def test_show_list_backend_failure(self):
        self.mock_cache_instance.get.return_value = None
        self.mock_backend_instance.get_rail_items.side_effect = BackendError("Backend failed")
        
        with self.assertRaisesRegex(PreflightError, "Backend failed"):
            listing_module.show_list(self.mock_context, "my_rail")
        
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_backend_instance.get_rail_items.assert_called_once()
        self.mock_addDirectoryItems.assert_not_called()

    # --- Tests for show_search ---
    def test_show_search_prompt_and_success(self):
        self.mock_dialog_instance.input.return_value = "my query"
        self.mock_backend_instance.search.return_value = ([{"asin": "s1", "title": "Search Result"}], None)
        
        listing_module.show_search(self.mock_context, None) # No query given, should prompt
        
        self.mock_dialog_instance.input.assert_called_once_with("LocalizedString_30030")
        self.mock_backend_instance.search.assert_called_once_with("my query", None)
        self.mock_addDirectoryItems.assert_called_once()
        
    def test_show_search_query_provided_success(self):
        self.mock_backend_instance.search.return_value = ([{"asin": "s1", "title": "Search Result"}], None)
        
        listing_module.show_search(self.mock_context, "predefined query")
        
        self.mock_dialog_instance.input.assert_not_called()
        self.mock_backend_instance.search.assert_called_once_with("predefined query", None)
        self.mock_addDirectoryItems.assert_called_once()
        
    def test_show_search_prompt_cancelled(self):
        self.mock_dialog_instance.input.return_value = "" # User cancels input
        
        listing_module.show_search(self.mock_context, None)
        
        self.mock_dialog_instance.input.assert_called_once()
        self.mock_backend_instance.search.assert_not_called()
        self.mock_addDirectoryItems.assert_not_called()

if __name__ == '__main__':
    unittest.main()
