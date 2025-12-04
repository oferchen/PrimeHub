import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import requests

# Add the test directory to sys.path to allow imports of kodi_mocks
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from kodi_mocks import patch_kodi_modules_globally

# Apply patches globally before other imports
patch_kodi_modules_globally()

# Add the lib directory to sys.path for the module under test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))
from backend import prime_api
from backend.prime_api import PrimeAPI, _NativeAPIIntegration, AuthenticationError, Playable

class TestNativeAPIIntegration(unittest.TestCase):
    def setUp(self):
        # This will be called before each test
        self.patcher_session = patch('backend.prime_api.SessionManager')
        self.mock_session_manager_cls = self.patcher_session.start()
        self.mock_session_manager = self.mock_session_manager_cls.get_instance.return_value
        
        self.mock_addon = MagicMock()
        self.integration = _NativeAPIIntegration(self.mock_addon)

    def tearDown(self):
        self.patcher_session.stop()

    def test_get_rail_items_success(self):
        self.integration.is_logged_in = MagicMock(return_value=True)
        items, next_cursor = self.integration.get_rail_items("movies", None)
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)
        self.assertIsNotNone(next_cursor)
        self.integration.is_logged_in.assert_called_once()

    def test_get_rail_items_not_logged_in(self):
        self.integration.is_logged_in = MagicMock(return_value=False)
        with self.assertRaises(AuthenticationError):
            self.integration.get_rail_items("movies", None)

    def test_search_success(self):
        self.integration.is_logged_in = MagicMock(return_value=True)
        items, next_cursor = self.integration.search("the boys", None)
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)
        self.assertIsNone(next_cursor)
        self.assertIn("the boys", items[0]['title'], "Mock search result should contain the query")

    def test_search_not_logged_in(self):
        self.integration.is_logged_in = MagicMock(return_value=False)
        with self.assertRaises(AuthenticationError):
            self.integration.search("the boys", None)

    def test_get_playable_success(self):
        self.integration.is_logged_in = MagicMock(return_value=True)
        playable = self.integration.get_playable("B012345")
        self.assertIsInstance(playable, Playable)
        self.assertIn("http", playable.url)
        self.assertIn("mpd", playable.manifest_type)

    def test_get_playable_not_logged_in(self):
        self.integration.is_logged_in = MagicMock(return_value=False)
        with self.assertRaises(AuthenticationError):
            self.integration.get_playable("B012345")

    @patch('os.path.exists')
    def test_is_drm_ready_found(self, mock_os_exists):
        mock_os_exists.return_value = True
        self.assertTrue(self.integration.is_drm_ready())

    @patch('os.path.exists')
    def test_is_drm_ready_not_found(self, mock_os_exists):
        mock_os_exists.return_value = False
        self.assertFalse(self.integration.is_drm_ready())

    def test_get_region_info_success(self):
        self.integration.is_logged_in = MagicMock(return_value=True)
        info = self.integration.get_region_info()
        self.assertIn("country", info)
        self.assertIn("language", info)

    def test_get_region_info_not_logged_in(self):
        self.integration.is_logged_in = MagicMock(return_value=False)
        with self.assertRaises(AuthenticationError):
            self.integration.get_region_info()

if __name__ == '__main__':
    unittest.main()