import unittest
from unittest.mock import MagicMock, patch

# Mock Kodi imports and environment for testing outside Kodi
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
        mock_addon.getLocalizedString.side_effect = lambda code: f"LocalizedString_{code}"
        return mock_addon

# Patch xbmc and xbmcaddon globally for the test environment
# This needs to be done before importing prime_api
original_sys_path = list(sys.path) # Store original sys.path
sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = MockXBMCAddon()
# sys.modules['xbmcgui'] = MagicMock() # Not used directly in prime_api

# Add the lib directory to sys.path so we can import prime_api
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test AFTER setting up mocks and path
import prime_api
from prime_api import PrimeAPI, BackendUnavailable, BackendError, Playable, _AmazonVODIntegration, _JsonRPCIntegration, normalize_rail, normalize_item

# Restore sys.path after import
sys.path = original_sys_path


class TestPrimeAPI(unittest.TestCase):

    def setUp(self):
        # Reset mocks before each test
        # Note: xbmc and xbmcaddon are global mocks here, so their state persists unless reset
        # For xbmc, we want to control its log behavior via our mock class
        # For xbmcaddon, we re-create the mock addon instance in our MockXBMCAddon factory

        # Ensure _backend_instance is reset for each test
        prime_api._backend_instance = None
        
        # Reset getSetting mocks to default for each test
        mock_addon_instance = xbmcaddon.Addon()
        mock_addon_instance.getSetting.side_effect = lambda key: {
            "region": "0", # us
            "max_resolution": "0", # auto
        }.get(key, "0")
        mock_addon_instance.getSettingBool.side_effect = lambda key: {
            "use_cache": True,
            "perf_logging": False,
        }.get(key, False)
        mock_addon_instance.getSettingInt.side_effect = lambda key: {
            "cache_ttl": 300,
        }.get(key, 0)
        mock_addon_instance.getLocalizedString.side_effect = lambda code: f"LocalizedString_{code}"


    @patch('prime_api.discover_backend', return_value="plugin.video.amazonvod")
    @patch('prime_api._AmazonVODIntegration')
    @patch('prime_api._JsonRPCIntegration')
    def test_primeapi_init_direct_success(self, MockJsonRPCIntegration, MockAmazonVODIntegration, mock_discover_backend):
        # Test case: Direct import succeeds
        mock_amazon_instance = MagicMock()
        MockAmazonVODIntegration.return_value = mock_amazon_instance
        
        api = PrimeAPI()
        self.assertIsInstance(api._strategy, MagicMock) # It's a MagicMock instance returned by patch
        self.assertEqual(api._strategy_name, "direct_import")
        MockAmazonVODIntegration.assert_called_once_with("plugin.video.amazonvod", api._addon)
        MockJsonRPCIntegration.assert_not_called()

    @patch('prime_api.discover_backend', return_value="plugin.video.amazonvod")
    @patch('prime_api._AmazonVODIntegration', side_effect=BackendUnavailable("Direct failed"))
    @patch('prime_api._JsonRPCIntegration')
    def test_primeapi_init_jsonrpc_fallback_success(self, MockJsonRPCIntegration, MockAmazonVODIntegration, mock_discover_backend):
        # Test case: Direct import fails, JSON-RPC succeeds
        mock_jsonrpc_instance = MagicMock()
        MockJsonRPCIntegration.return_value = mock_jsonrpc_instance
        
        api = PrimeAPI()
        self.assertIsInstance(api._strategy, MagicMock)
        self.assertEqual(api._strategy_name, "json_rpc")
        MockAmazonVODIntegration.assert_called_once_with("plugin.video.amazonvod", api._addon)
        MockJsonRPCIntegration.assert_called_once_with("plugin.video.amazonvod", api._addon)

    @patch('prime_api.discover_backend', return_value="plugin.video.amazonvod")
    @patch('prime_api._AmazonVODIntegration', side_effect=BackendUnavailable("Direct failed"))
    @patch('prime_api._JsonRPCIntegration', side_effect=BackendUnavailable("JSON-RPC failed"))
    def test_primeapi_init_all_fail(self, MockJsonRPCIntegration, MockAmazonVODIntegration, mock_discover_backend):
        # Test case: Both strategies fail
        with self.assertRaises(BackendUnavailable):
            PrimeAPI()
        # _addon is an instance of MockXBMCAddon.Addon(), which is also a MagicMock
        MockAmazonVODIntegration.assert_called_once_with("plugin.video.amazonvod", unittest.mock.ANY) 
        MockJsonRPCIntegration.assert_called_once_with("plugin.video.amazonvod", unittest.mock.ANY)

    @patch('prime_api.discover_backend', return_value=None)
    def test_primeapi_init_no_backend_found(self, mock_discover_backend):
        # Test case: No backend addon discovered
        with self.assertRaises(BackendUnavailable):
            PrimeAPI()

    # Add more tests for methods like get_home_rails, get_rail_items, get_playable, etc.

if __name__ == '__main__':
    unittest.main()
