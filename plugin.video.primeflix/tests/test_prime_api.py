import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Import and apply global patches for Kodi modules
from kodi_mocks import patch_kodi_modules_globally

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
from backend import prime_api
from backend.prime_api import _NativeAPIIntegration, AuthenticationError, Playable

class TestNativeAPIIntegrationAsync(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patch_kodi_modules_globally()
        self.patcher_session = patch('backend.prime_api.SessionManager')
        self.mock_session_manager_cls = self.patcher_session.start()
        self.mock_session_manager = self.mock_session_manager_cls.get_instance.return_value
        
        self.mock_addon = MagicMock()
        self.integration = _NativeAPIIntegration(self.mock_addon)

    def tearDown(self):
        self.patcher_session.stop()

    @patch.object(_NativeAPIIntegration, '_handle_request', new_callable=AsyncMock)
    async def test_get_home_rails(self, mock_handle_request):
        self.integration.is_logged_in = MagicMock(return_value=True)
        mock_handle_request.return_value = {
            "widgets": [{"type": "RailWidget", "id": "test_rail", "title": {"default": "Test Rail"}}]
        }
        
        rails = await self.integration.get_home_rails()
        self.assertEqual(len(rails), 1)
        self.assertEqual(rails[0]['id'], 'test_rail')
        mock_handle_request.assert_awaited_once()

    @patch.object(_NativeAPIIntegration, '_handle_request', new_callable=AsyncMock)
    async def test_get_rail_items(self, mock_handle_request):
        self.integration.is_logged_in = MagicMock(return_value=True)
        mock_handle_request.return_value = {
            "items": [{"asin": "B0TEST", "title": "Test Item"}],
            "nextPageCursor": "next_cursor"
        }
        
        items, cursor = await self.integration.get_rail_items("test_rail", None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['asin'], 'B0TEST')
        self.assertEqual(cursor, 'next_cursor')
        
    @patch.object(_NativeAPIIntegration, '_handle_request', new_callable=AsyncMock)
    async def test_search(self, mock_handle_request):
        self.integration.is_logged_in = MagicMock(return_value=True)
        mock_handle_request.return_value = {
            "items": [{"asin": "B0SEARCH", "title": "Search Result"}],
            "nextPageCursor": None
        }
        
        items, cursor = await self.integration.search("query", None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['asin'], 'B0SEARCH')
        self.assertIsNone(cursor)

    @patch.object(_NativeAPIIntegration, '_handle_request', new_callable=AsyncMock)
    async def test_get_playable(self, mock_handle_request):
        self.integration.is_logged_in = MagicMock(return_value=True)
        mock_handle_request.return_value = {
            "manifestUrl": "http://test.mpd",
            "licenseUrl": "http://test.lic"
        }
        
        playable = await self.integration.get_playable("B0PLAY")
        self.assertIsInstance(playable, Playable)
        self.assertEqual(playable.url, "http://test.mpd")
        self.assertEqual(playable.license_key, "http://test.lic")

if __name__ == '__main__':
    unittest.main()
