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
        return mock_addon

class MockXBMCGUI:
    ListItem = MagicMock()

class MockXBMCPlugin:
    SORT_METHOD_UNSORTED = 0
    def addDirectoryItems(self, handle, items): pass
    def setContent(self, handle, content): pass

# Patch Kodi modules globally before other imports
sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = MockXBMCAddon()
sys.modules['xbmcgui'] = MockXBMCGUI()
sys.modules['xbmcplugin'] = MockXBMCPlugin()

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import ui.diagnostics as diagnostics_module
from preflight import PreflightError


class TestUIDiagnostics(unittest.TestCase):

    def setUp(self):
        # Patch external dependencies
        self.patcher_get_backend = patch('ui.diagnostics.get_backend')
        self.mock_get_backend = self.patcher_get_backend.start()
        self.mock_backend_instance = MagicMock()
        self.mock_backend_instance.strategy = "mock_strategy"
        self.mock_get_backend.return_value = self.mock_backend_instance

        self.patcher_get_cache = patch('ui.diagnostics.get_cache')
        self.mock_get_cache = self.patcher_get_cache.start()
        self.mock_cache_instance = MagicMock()
        self.mock_get_cache.return_value = self.mock_cache_instance
        
        self.patcher_ensure_ready_or_raise = patch('ui.diagnostics.ensure_ready_or_raise')
        self.mock_ensure_ready_or_raise = self.patcher_ensure_ready_or_raise.start()
        
        self.patcher_fetch_home_rails = patch('ui.diagnostics.fetch_home_rails')
        self.mock_fetch_home_rails = self.patcher_fetch_home_rails.start()
        self.mock_fetch_home_rails.return_value = [{"id": "mock_rail", "title": "Mock Rail"}]

        self.patcher_log_duration = patch('ui.diagnostics.log_duration')
        self.mock_log_duration = self.patcher_log_duration.start()

        # Mock xbmcaddon.Addon() for local settings
        self.mock_addon_instance = MagicMock(spec=xbmcaddon.Addon)
        self.mock_addon_instance.getLocalizedString.side_effect = (
            lambda code: f"LocalizedString_{code}"
        )
        sys.modules['xbmcaddon'].Addon.return_value = self.mock_addon_instance
        
        # Mock ListItem for assertions
        sys.modules['xbmcgui'].ListItem.reset_mock()
        self.mock_list_item = MagicMock()
        sys.modules['xbmcgui'].ListItem.return_value = self.mock_list_item

        # Mock xbmcplugin methods
        self.patcher_addDirectoryItems = patch.object(sys.modules['xbmcplugin'], 'addDirectoryItems')
        self.mock_addDirectoryItems = self.patcher_addDirectoryItems.start()
        self.patcher_setContent = patch.object(sys.modules['xbmcplugin'], 'setContent')
        self.mock_setContent = self.patcher_setContent.start()


        # Create a mock context
        self.mock_context = MagicMock()
        self.mock_context.handle = 1

    def tearDown(self):
        patch.stopall()

    def test_show_results_success(self):
        # Simulate different timings for cold/warm runs
        with patch('time.perf_counter', side_effect=[0, 1.0, 1.0, 1.1, 1.1, 1.15]): # 1000ms, 100ms, 50ms
            diagnostics_module.show_results(self.mock_context)
            
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_cache_instance.clear_prefix.assert_called_once_with("home")
        
        self.assertEqual(self.mock_fetch_home_rails.call_count, 3)
        self.mock_fetch_home_rails.assert_has_calls([
            call(self.mock_addon_instance, self.mock_cache_instance),
            call(self.mock_addon_instance, self.mock_cache_instance),
            call(self.mock_addon_instance, self.mock_cache_instance)
        ])
        
        self.assertEqual(self.mock_log_duration.call_count, 3)
        self.mock_log_duration.assert_has_calls([
            call('home', 1000.0, warm=False, warm_threshold_ms=300.0, cold_threshold_ms=1500.0),
            call('home', 100.0, warm=True, warm_threshold_ms=300.0, cold_threshold_ms=1500.0),
            call('home', 50.0, warm=True, warm_threshold_ms=300.0, cold_threshold_ms=1500.0)
        ])
        
        self.mock_setContent.assert_called_once_with(self.mock_context.handle, "videos")
        self.mock_addDirectoryItems.assert_called_once()
        
        # Check output items
        args, _ = self.mock_addDirectoryItems.call_args
        items = args[1]
        self.assertEqual(len(items), 3)
        self.assertEqual(self.mock_list_item.setInfo.call_count, 3)
        self.assertIn("Run 1: 1000 ms (cold, strategy=mock_strategy)", items[0][1].label)
        self.assertIn("Run 2: 100 ms (warm, strategy=mock_strategy)", items[1][1].label)
        self.assertIn("Run 3: 50 ms (warm, strategy=mock_strategy)", items[2][1].label)


    def test_show_results_preflight_failure(self):
        self.mock_ensure_ready_or_raise.side_effect = PreflightError("Preflight failed")
        
        with self.assertRaisesRegex(PreflightError, "Preflight failed"):
            diagnostics_module.show_results(self.mock_context)
            
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_cache_instance.clear_prefix.assert_not_called()
        self.mock_fetch_home_rails.assert_not_called()
        self.mock_addDirectoryItems.assert_not_called()

if __name__ == '__main__':
    unittest.main()
