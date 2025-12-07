import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Import and apply global patches for Kodi modules
from .kodi_mocks import patch_kodi_modules_globally

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import ui.playback as playback_module
from backend.prime_api import BackendError, BackendUnavailable, Playable
from preflight import PreflightError


class TestUIPlayback(unittest.TestCase):

    def setUp(self):
        patch_kodi_modules_globally()
        
        # Patch external dependencies
        self.patcher_get_backend = patch('ui.playback.get_backend')
        self.mock_get_backend = self.patcher_get_backend.start()
        self.mock_backend_instance = MagicMock()
        self.mock_get_backend.return_value = self.mock_backend_instance

        self.patcher_ensure_ready_or_raise = patch('ui.playback.ensure_ready_or_raise')
        self.mock_ensure_ready_or_raise = self.patcher_ensure_ready_or_raise.start()
        
        # Mock xbmcplugin and xbmcgui from sys.modules
        self.mock_xbmcplugin = sys.modules['xbmcplugin']
        self.mock_xbmcgui = sys.modules['xbmcgui']
        
        # Mock ListItem
        self.mock_list_item_instance = self.mock_xbmcgui.ListItem.return_value
        
        # Create a mock context
        self.mock_context = MagicMock()
        self.mock_context.handle = 1

    def tearDown(self):
        patch.stopall()

    # ... (rest of the tests remain the same)
    def test_play_success(self):
        mock_playable = Playable(
            url="http://mock.manifest/url.mpd",
            manifest_type="mpd",
            license_key="http://mock.license/key",
            headers={"User-Agent": "MockUserAgent"},
            metadata={"title": "Mock Title", "plot": "Mock Plot"}
        )
        self.mock_backend_instance.get_playable.return_value = mock_playable
        
        playback_module.play(self.mock_context, "mock_asin")
        
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_backend_instance.get_playable.assert_called_once_with("mock_asin")
        self.mock_list_item_instance.setInfo.assert_called_once_with("video", mock_playable.metadata)
        self.mock_list_item_instance.setProperty.assert_any_call("inputstream.adaptive.manifest_type", "mpd")
        self.mock_xbmcplugin.setResolvedUrl.assert_called_once_with(self.mock_context.handle, True, self.mock_list_item_instance)

if __name__ == '__main__':
    unittest.main()