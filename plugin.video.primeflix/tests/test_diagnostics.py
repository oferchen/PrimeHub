import unittest
from unittest.mock import MagicMock, patch, call
import sys
import os

# Import and apply global patches for Kodi modules
from .kodi_mocks import patch_kodi_modules_globally

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import ui.diagnostics as diagnostics_module
from preflight import PreflightError


class TestUIDiagnostics(unittest.TestCase):

    def setUp(self):
        patch_kodi_modules_globally()
        
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
        
        # Mock xbmcplugin and xbmcgui from sys.modules
        self.mock_xbmcplugin = sys.modules['xbmcplugin']
        self.mock_xbmcgui = sys.modules['xbmcgui']
        self.mock_xbmcaddon = sys.modules['xbmcaddon']

        self.mock_addon_instance = self.mock_xbmcaddon.Addon.return_value
        self.mock_list_item = self.mock_xbmcgui.ListItem.return_value

        # Create a mock context
        self.mock_context = MagicMock()
        self.mock_context.handle = 1

    def tearDown(self):
        patch.stopall()

    # ... (rest of tests remain the same)
    def test_show_results_success(self):
        # Simulate different timings for cold/warm runs
        with patch('time.perf_counter', side_effect=[0, 1.0, 1.0, 1.1, 1.1, 1.15]): # 1000ms, 100ms, 50ms
            diagnostics_module.show_results(self.mock_context)
            
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_cache_instance.clear_prefix.assert_called_once_with("home")
        
        self.assertEqual(self.mock_fetch_home_rails.call_count, 3)
        self.mock_log_duration.assert_called_with('home', 50.0, warm=True, warm_threshold_ms=300.0, cold_threshold_ms=1500.0)
        
        self.mock_xbmcplugin.setContent.assert_called_once_with(self.mock_context.handle, "videos")
        self.mock_xbmcplugin.addDirectoryItems.assert_called_once()


if __name__ == '__main__':
    unittest.main()