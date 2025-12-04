import unittest
from unittest.mock import MagicMock, patch, call
import os
import sys
import json
import requests # Import requests for mocking

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
        mock_addon.getLocalizedString.side_effect = (
            lambda code: f"LocalizedString_{code}"
        )
        return mock_addon

# Mock xbmcvfs for file operations
class MockXBMCRuntime:
    def exists(self, path): return False
    def File(self, path, mode='r'):
        mock_file = MagicMock()
        mock_file.read.return_value = ''
        mock_file.__enter__.return_value = mock_file
        return mock_file
    def delete(self, path): pass

# Patch Kodi modules globally for the test environment
original_sys_path = list(sys.path)
sys.modules["xbmc"] = MockXBMC()
sys.modules["xbmcaddon"] = MockXBMCAddon()
sys.modules["xbmcvfs"] = MockXBMCRuntime() # Add xbmcvfs mock

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test AFTER setting up mocks and path
import prime_api
from prime_api import (
    PrimeAPI, BackendUnavailable, AuthenticationError, Playable, _NativeAPIIntegration, normalize_rail, normalize_item
)

# Restore sys.path
sys.path = original_sys_path


class TestPrimeAPI(unittest.TestCase):

    def setUp(self):
        prime_api._backend_instance = None
        # Reset xbmcvfs mock for each test
        sys.modules['xbmcvfs'] = MockXBMCRuntime()
        
    @patch('prime_api.xbmcaddon.Addon')
    @patch('prime_api._NativeAPIIntegration')
    def test_primeapi_init_success(self, MockNativeAPIIntegration, MockAddon):
        mock_addon_instance = MockAddon.return_value
        mock_native_integration_instance = MagicMock()
        MockNativeAPIIntegration.return_value = mock_native_integration_instance

        api = PrimeAPI()
        self.assertIsInstance(api._strategy, MagicMock)
        MockNativeAPIIntegration.assert_called_once_with(mock_addon_instance)
        
        # Test facade methods delegate to strategy
        api.login("user", "pass")
        mock_native_integration_instance.login.assert_called_once_with("user", "pass")
        
        api.logout()
        mock_native_integration_instance.logout.assert_called_once()
        
        api.is_logged_in()
        mock_native_integration_instance.is_logged_in.assert_called_once()
        
        api.get_home_rails()
        mock_native_integration_instance.get_home_rails.assert_called_once()
        
        api.add_to_watchlist("asin123")
        mock_native_integration_instance.add_to_watchlist.assert_called_once_with("asin123")


class TestNativeAPIIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_addon = MagicMock(spec=xbmcaddon.Addon)
        self.mock_addon.getAddonInfo.return_value = "/mock/path/to/profile" # for session_path
        
        # Mock requests.Session for network calls
        self.mock_session = MagicMock(spec=requests.Session)
        self.mock_session.cookies = MagicMock(spec=requests.cookies.RequestsCookieJar)
        self.mock_session.get.return_value.raise_for_status.return_value = None
        self.mock_session.post.return_value.raise_for_status.return_value = None
        
        # Patch requests.Session to return our mock session
        self.patcher_requests_session = patch('requests.Session', return_value=self.mock_session)
        self.patcher_requests_session.start()

        # Mock xbmcvfs file operations
        self.mock_xbmcvfs = sys.modules['xbmcvfs']
        self.mock_xbmcvfs.exists.return_value = False # Default to no session file

        self.integration = _NativeAPIIntegration(self.mock_addon)
        self.integration._session = self.mock_session # Ensure session is our mock


    def tearDown(self):
        self.patcher_requests_session.stop()
        
    def test_init_loads_session_if_exists(self):
        self.mock_xbmcvfs.exists.return_value = True
        self.mock_xbmcvfs.File.return_value.__enter__.return_value.read.return_value = json.dumps({'cookies': {'c1': 'v1'}})
        
        integration = _NativeAPIIntegration(self.mock_addon) # Re-init to trigger load
        self.mock_xbmcvfs.exists.assert_called_once_with(integration._session_path)
        integration._session.cookies.update.assert_called_once_with({'c1': 'v1'})
        self.assertTrue(integration.is_logged_in())

    def test_init_starts_new_session_if_no_file(self):
        self.mock_xbmcvfs.exists.return_value = False
        integration = _NativeAPIIntegration(self.mock_addon)
        self.mock_xbmcvfs.exists.assert_called_once_with(integration._session_path)
        self.assertIsInstance(integration._session, MagicMock) # It's a mock requests.Session
        self.assertFalse(integration.is_logged_in())

    def test_login_success(self):
        self.mock_session.get.return_value.url = "https://www.amazon.com/ap/signin"
        self.mock_session.post.return_value.url = "https://www.amazon.com/gp/prime" # Simulate redirect away from signin
        
        # Mock verify_session for successful login
        self.integration._verify_session = MagicMock(return_value=True)

        result = self.integration.login("user", "pass")
        self.assertTrue(result)
        self.mock_session.get.assert_called_once()
        self.mock_session.post.assert_called_once()
        self.mock_xbmcvfs.File.assert_called_once() # Should save session
        self.integration._verify_session.assert_called_once()

    def test_login_failure_bad_credentials(self):
        self.mock_session.get.return_value.url = "https://www.amazon.com/ap/signin"
        self.mock_session.post.return_value.url = "https://www.amazon.com/ap/signin?error=1" # Simulate no redirect
        
        self.integration._verify_session = MagicMock(return_value=False) # Will be called, but should return False

        with self.assertRaises(AuthenticationError):
            self.integration.login("user", "wrong_pass")
        self.mock_session.get.assert_called_once()
        self.mock_session.post.assert_called_once()
        self.assertFalse(self.integration.is_logged_in()) # Session should be cleared
        self.mock_xbmcvfs.delete.assert_called_once() # Should clear session file if failure after partial save

    def test_login_request_exception(self):
        self.mock_session.get.side_effect = requests.exceptions.RequestException("Network Error")
        with self.assertRaisesRegex(AuthenticationError, "Could not reach Amazon login page."):
            self.integration.login("user", "pass")

    def test_load_session_corrupted_file(self):
        self.mock_xbmcvfs.exists.return_value = True
        self.mock_xbmcvfs.File.return_value.__enter__.return_value.read.return_value = "not json"
        
        integration = _NativeAPIIntegration(self.mock_addon)
        self.assertIsNone(integration._session) # Session should be cleared
        self.mock_xbmcvfs.delete.assert_called_once() # Should delete corrupted file

    def test_is_logged_in_false_empty_cookies(self):
        self.integration._session = self.mock_session
        self.integration._session.cookies = requests.cookies.RequestsCookieJar() # Empty cookie jar
        self.assertFalse(self.integration.is_logged_in())

    def test_add_to_watchlist_success(self):
        self.integration.is_logged_in = MagicMock(return_value=True) # Ensure logged in
        result = self.integration.add_to_watchlist("asin123")
        self.assertTrue(result)
        self.integration.is_logged_in.assert_called_once()

    def test_add_to_watchlist_not_logged_in(self):
        self.integration.is_logged_in = MagicMock(return_value=False) # Ensure not logged in
        with self.assertRaises(AuthenticationError):
            self.integration.add_to_watchlist("asin123")


class TestNormalizeFunctions(unittest.TestCase):
    def test_normalize_rail(self):
        raw_rail = {"id": "test_id", "title": "Test Title", "type": "movies"}
        normalized = normalize_rail(raw_rail)
        self.assertEqual(normalized['id'], 'test_id')
        self.assertEqual(normalized['title'], 'Test Title')
        self.assertEqual(normalized['type'], 'movies')

    def test_normalize_item(self):
        raw_item = {"asin": "a1", "title": "Item Title", "plot": "Plot"}
        normalized = normalize_item(raw_item)
        self.assertEqual(normalized["asin"], "a1")
        self.assertEqual(normalized["title"], "Item Title")

if __name__ == '__main__':
    unittest.main()
