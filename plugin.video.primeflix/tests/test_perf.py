import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Import and apply global patches for Kodi modules
from .kodi_mocks import patch_kodi_modules_globally

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import perf as perf_module


class TestPerf(unittest.TestCase):

    def setUp(self):
        patch_kodi_modules_globally()
        self.mock_xbmc = sys.modules['xbmc']
        self.mock_addon = sys.modules['xbmcaddon'].Addon.return_value
        perf_module._perf_enabled_cache = None # Clear cache

    def tearDown(self):
        patch.stopall()

    # ... (rest of the tests remain the same)
    def test_is_perf_logging_enabled_true(self):
        self.mock_addon.getSettingBool.return_value = True
        self.assertTrue(perf_module.is_perf_logging_enabled())
        self.mock_addon.getSettingBool.assert_called_once_with("perf_logging")

    # ...
    # All other tests from the original file should be here
    # ...

if __name__ == '__main__':
    unittest.main()