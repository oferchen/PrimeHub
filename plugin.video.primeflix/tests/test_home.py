import unittest
from unittest.mock import MagicMock, patch, call
import sys
import os

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
        return mock_addon

class MockXBMCGUI:
    ListItem = MagicMock()

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
import ui.home as home_module
from backend.prime_api import BackendError, AuthenticationError
from preflight import PreflightError


class TestUIHome(unittest.TestCase):

    def setUp(self):
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
        
        self.patcher_xbmcplugin = patch.object(sys.modules['xbmcplugin'], 'addDirectoryItems')
        self.mock_xbmcplugin_addDirectoryItems = self.patcher_xbmcplugin.start()
        self.patcher_xbmcplugin_setContent = patch.object(sys.modules['xbmcplugin'], 'setContent')
        self.mock_xbmcplugin_setContent = self.patcher_xbmcplugin_setContent.start()


        # Mock xbmcaddon.Addon() for local settings
        self.mock_addon_instance = MagicMock(spec=xbmcaddon.Addon)
        self.mock_addon_instance.getSettingBool.return_value = True
        self.mock_addon_instance.getSettingInt.return_value = 300
        self.mock_addon_instance.getAddonInfo.return_value = "/mock/path/to/fanart.jpg"
        self.mock_addon_instance.getLocalizedString.side_effect = (
            lambda code: f"LocalizedString_{code}"
        )
        sys.modules['xbmcaddon'].Addon.return_value = self.mock_addon_instance
        
        # Mock ListItem for assertions
        sys.modules['xbmcgui'].ListItem.reset_mock()
        self.mock_list_item = MagicMock()
        sys.modules['xbmcgui'].ListItem.return_value = self.mock_list_item

        # Create a mock context
        self.mock_context = MagicMock()
        self.mock_context.handle = 1
        self.mock_context.build_url.side_effect = lambda **kwargs: "plugin_url?" + "&".join(f"{k}={v}" for k,v in kwargs.items())

    def tearDown(self):
        patch.stopall()

    # --- Tests for fetch_home_rails ---
    def test_fetch_home_rails_cache_hit(self):
        cached_rails = [{"id": "cached", "title": "Cached Rail"}]
        self.mock_cache_instance.get.return_value = cached_rails

        rails = home_module.fetch_home_rails(self.mock_addon_instance, self.mock_cache_instance)
        self.assertEqual(rails, cached_rails)
        self.mock_cache_instance.get.assert_called_once()
        self.mock_get_backend.assert_not_called()

    def test_fetch_home_rails_cache_miss_backend_success(self):
        self.mock_cache_instance.get.return_value = None
        self.mock_backend_instance.get_home_rails.return_value = [
            {"id": "movies", "title": "Movies from Backend"},
            {"id": "new_stuff", "title": "New Stuff"},
        ]
        
        rails = home_module.fetch_home_rails(self.mock_addon_instance, self.mock_cache_instance)
        self.mock_get_backend.assert_called_once()
        self.mock_backend_instance.get_home_rails.assert_called_once()
        self.mock_cache_instance.set.assert_called_once()
        
        # Check mapping and appending of new stuff
        self.assertGreater(len(rails), 0)
        self.assertIn({'id': 'movies', 'title': 'Movies from Backend', 'type': 'mixed', 'path': ''}, rails)
        self.assertIn({'id': 'new_stuff', 'title': 'New Stuff', 'type': 'mixed', 'path': ''}, rails)


    def test_fetch_home_rails_backend_failure_returns_login_fallback(self):
        self.mock_cache_instance.get.return_value = None
        self.mock_backend_instance.get_home_rails.side_effect = AuthenticationError("Not logged in")
        
        rails = home_module.fetch_home_rails(self.mock_addon_instance, self.mock_cache_instance)
        self.mock_get_backend.assert_called_once()
        self.mock_backend_instance.get_home_rails.assert_called_once()
        self.mock_cache_instance.set.assert_called_once() # Should cache the fallback

        self.assertEqual(len(rails), 1)
        self.assertEqual(rails[0]['id'], 'login')
        self.assertEqual(rails[0]['title'], 'Login Required')
        self.assertIn("action=login", rails[0]['plugin_url'])

    def test_fetch_home_rails_mapping_and_placeholders(self):
        self.mock_cache_instance.get.return_value = None
        self.mock_backend_instance.get_home_rails.return_value = [
            {"id": "movies", "title": "Backend Movies"},
            # "tv" is missing
            {"id": "continue_watching", "title": "My CW"},
        ]
        
        rails = home_module.fetch_home_rails(self.mock_addon_instance, self.mock_cache_instance)
        # Check order and placeholders
        self.assertEqual(rails[0]['id'], 'continue_watching')
        self.assertEqual(rails[0]['title'], 'My CW') # Prefer backend title
        
        self.assertEqual(rails[1]['id'], 'prime_originals')
        self.assertEqual(rails[1]['title'], 'LocalizedString_40001') # Placeholder
        
        self.assertEqual(rails[2]['id'], 'movies')
        self.assertEqual(rails[2]['title'], 'Backend Movies')
        
        self.assertEqual(rails[3]['id'], 'tv')
        self.assertEqual(rails[3]['title'], 'LocalizedString_40003') # Placeholder


    # --- Tests for show_home ---
    def test_show_home_success(self):
        self.mock_ensure_ready_or_raise.return_value = None
        home_module.fetch_home_rails = MagicMock(return_value=[
            {"id": "movies", "title": "Movies", "path": "", "type": "movies"},
        ])
        
        home_module.show_home(self.mock_context)
        
        self.mock_ensure_ready_or_raise.assert_called_once()
        home_module.fetch_home_rails.assert_called_once_with(self.mock_addon_instance, self.mock_cache_instance)
        self.mock_xbmcplugin_setContent.assert_called_once_with(1, "videos")
        
        # Check items passed to addDirectoryItems
        args, _ = self.mock_xbmcplugin_addDirectoryItems.call_args
        items = args[1]
        self.assertEqual(len(items), 4) # 1 rail + Search + Diagnostics + Logout

        self.assertEqual(items[0][0], "plugin_url?action=list&rail=movies") # Movies rail
        self.assertEqual(items[1][0], "plugin_url?action=search") # Search
        self.assertEqual(items[2][0], "plugin_url?action=diagnostics") # Diagnostics
        self.assertEqual(items[3][0], "plugin_url?action=logout") # Logout
        
        self.mock_list_item.setArt.assert_called() # Should be called for each item


    def test_show_home_preflight_failure(self):
        self.mock_ensure_ready_or_raise.side_effect = PreflightError("Preflight failed")
        
        with self.assertRaises(PreflightError): # Re-raises
            home_module.show_home(self.mock_context)
            
        self.mock_ensure_ready_or_raise.assert_called_once()
        home_module.fetch_home_rails.assert_not_called()
        self.mock_xbmcplugin_addDirectoryItems.assert_not_called()

if __name__ == '__main__':
    unittest.main()
