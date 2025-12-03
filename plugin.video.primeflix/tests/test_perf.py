import unittest
from unittest.mock import MagicMock, patch, call
import sys
import os

# Mock Kodi imports for testing outside Kodi
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    def log(self, message: str, level: int = 0) -> None:
        pass # Suppress logging during tests

class MockXBMCAddon:
    def Addon(self, addon_id=None):
        mock_addon = MagicMock()
        mock_addon.getSetting.side_effect = lambda key: {
            "perf_logging": "true" if key == "perf_logging" else "false",
        }.get(key, "false")
        mock_addon.getSettingBool.side_effect = lambda key: {
            "perf_logging": True if key == "perf_logging" else False,
        }.get(key, False)
        return mock_addon

# Patch Kodi modules globally before other imports
sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = MockXBMCAddon()

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import perf as perf_module


class TestPerf(unittest.TestCase):

    def setUp(self):
        # Reset mocks before each test
        self.mock_xbmc = sys.modules['xbmc']
        self.mock_xbmc.log.reset_mock()
        self.mock_addon = sys.modules['xbmcaddon'].Addon.return_value
        self.mock_addon.reset_mock()
        perf_module._perf_enabled_cache = None # Clear cache for is_perf_logging_enabled

    # --- Tests for is_perf_logging_enabled ---
    def test_is_perf_logging_enabled_true(self):
        self.mock_addon.getSettingBool.return_value = True
        self.assertTrue(perf_module.is_perf_logging_enabled())
        self.mock_addon.getSettingBool.assert_called_once_with("perf_logging")

    def test_is_perf_logging_enabled_false(self):
        self.mock_addon.getSettingBool.return_value = False
        self.assertFalse(perf_module.is_perf_logging_enabled())
        self.mock_addon.getSettingBool.assert_called_once_with("perf_logging")

    def test_is_perf_logging_enabled_caches_result(self):
        self.mock_addon.getSettingBool.return_value = True
        self.assertTrue(perf_module.is_perf_logging_enabled())
        self.assertTrue(perf_module.is_perf_logging_enabled()) # Call again
        self.mock_addon.getSettingBool.assert_called_once() # Should only be called once

    # --- Tests for timed decorator ---
    @patch('time.perf_counter', side_effect=[0, 1.0]) # Simulate 1000ms elapsed
    def test_timed_logs_when_enabled(self, mock_perf_counter):
        self.mock_addon.getSettingBool.return_value = True # Enable perf logging

        @perf_module.timed("test_label")
        def test_func():
            return "result"
        
        result = test_func()
        self.assertEqual(result, "result")
        self.mock_xbmc.log.assert_called_with("[PrimeFlix] test_label finished in 1000.00 ms", self.mock_xbmc.LOGDEBUG)

    @patch('time.perf_counter', side_effect=[0, 1.0]) # Simulate 1000ms elapsed
    def test_timed_no_log_when_disabled(self, mock_perf_counter):
        self.mock_addon.getSettingBool.return_value = False # Disable perf logging

        @perf_module.timed("test_label")
        def test_func():
            return "result"
        
        result = test_func()
        self.assertEqual(result, "result")
        self.mock_xbmc.log.assert_not_called()

    @patch('time.perf_counter', side_effect=[0, 1.0]) # Simulate 1000ms elapsed
    def test_timed_logs_warning_on_threshold_exceeded(self, mock_perf_counter):
        self.mock_addon.getSettingBool.return_value = False # Disable debug logging
        
        @perf_module.timed("test_label", warn_threshold_ms=500.0) # Threshold 500ms
        def test_func():
            pass
        
        test_func()
        self.mock_xbmc.log.assert_called_with("[PrimeFlix] test_label finished in 1000.00 ms", self.mock_xbmc.LOGWARNING)

    def test_timed_propagates_exception(self):
        @perf_module.timed("test_label")
        def test_func():
            raise ValueError("Test Error")
        
        with self.assertRaises(ValueError):
            test_func()

    # --- Tests for log_duration ---
    def test_log_duration_logs_info_when_enabled(self):
        self.mock_addon.getSettingBool.return_value = True # Enable perf logging
        perf_module.log_duration("test_label", 100.0)
        self.mock_xbmc.log.assert_called_with("[PrimeFlix] test_label completed in 100.00 ms (cold)", self.mock_xbmc.LOGINFO)

    def test_log_duration_no_log_when_disabled(self):
        self.mock_addon.getSettingBool.return_value = False # Disable perf logging
        perf_module.log_duration("test_label", 100.0)
        self.mock_xbmc.log.assert_not_called()

    def test_log_duration_logs_warning_on_cold_threshold_exceeded(self):
        self.mock_addon.getSettingBool.return_value = False # Disable debug logging
        perf_module.log_duration("test_label", 2000.0, warm=False, cold_threshold_ms=1500.0)
        self.mock_xbmc.log.assert_called_with("[PrimeFlix] test_label exceeded target (cold): 2000.00 ms (threshold 1500 ms)", self.mock_xbmc.LOGWARNING)

    def test_log_duration_logs_warning_on_warm_threshold_exceeded(self):
        self.mock_addon.getSettingBool.return_value = False # Disable debug logging
        perf_module.log_duration("test_label", 500.0, warm=True, warm_threshold_ms=300.0)
        self.mock_xbmc.log.assert_called_with("[PrimeFlix] test_label exceeded target (warm): 500.00 ms (threshold 300 ms)", self.mock_xbmc.LOGWARNING)

if __name__ == '__main__':
    unittest.main()
