import unittest
from unittest.mock import MagicMock, patch
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
    def setResolvedUrl(self, handle, succeeded, listitem): pass

# Patch Kodi modules globally before other imports
sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = MockXBMCAddon()
sys.modules['xbmcgui'] = MockXBMCGUI()
sys.modules['xbmcplugin'] = MockXBMCPlugin()

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import ui.playback as playback_module
from backend.prime_api import BackendError, BackendUnavailable, Playable
from preflight import PreflightError


class TestUIPlayback(unittest.TestCase):

    def setUp(self):
        # Patch external dependencies
        self.patcher_get_backend = patch('ui.playback.get_backend')
        self.mock_get_backend = self.patcher_get_backend.start()
        self.mock_backend_instance = MagicMock()
        self.mock_get_backend.return_value = self.mock_backend_instance

        self.patcher_ensure_ready_or_raise = patch('ui.playback.ensure_ready_or_raise')
        self.mock_ensure_ready_or_raise = self.patcher_ensure_ready_or_raise.start()
        
        # Mock xbmcplugin methods
        self.patcher_setResolvedUrl = patch.object(sys.modules['xbmcplugin'], 'setResolvedUrl')
        self.mock_setResolvedUrl = self.patcher_setResolvedUrl.start()

        # Mock xbmcgui.ListItem
        sys.modules['xbmcgui'].ListItem.reset_mock()
        self.mock_list_item_instance = MagicMock()
        sys.modules['xbmcgui'].ListItem.return_value = self.mock_list_item_instance
        
        # Create a mock context
        self.mock_context = MagicMock()
        self.mock_context.handle = 1

    def tearDown(self):
        patch.stopall()

    # --- Tests for play function ---
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
        self.mock_list_item_instance.setProperty.assert_any_call("inputstream.adaptive.license_key", "http://mock.license/key")
        self.mock_setResolvedUrl.assert_called_once_with(self.mock_context.handle, True, self.mock_list_item_instance)

    def test_play_backend_failure(self):
        self.mock_backend_instance.get_playable.side_effect = BackendError("Backend failed")
        
        with self.assertRaisesRegex(PreflightError, "Backend failed"):
            playback_module.play(self.mock_context, "mock_asin")
            
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_backend_instance.get_playable.assert_called_once()
        self.mock_setResolvedUrl.assert_not_called()

    def test_play_preflight_failure(self):
        self.mock_ensure_ready_or_raise.side_effect = PreflightError("Preflight failed")
        
        with self.assertRaisesRegex(PreflightError, "Preflight failed"):
            playback_module.play(self.mock_context, "mock_asin")
            
        self.mock_ensure_ready_or_raise.assert_called_once()
        self.mock_backend_instance.get_playable.assert_not_called()
        self.mock_setResolvedUrl.assert_not_called()

    # --- Tests for _build_list_item function ---
    def test_build_list_item_with_license(self):
        mock_playable = Playable(
            url="http://mock.manifest/url.mpd",
            manifest_type="mpd",
            license_key="http://mock.license/key",
            headers={"User-Agent": "MockUserAgent"},
            metadata={"title": "Test Title"}
        )
        list_item = playback_module._build_list_item(mock_playable)
        
        self.mock_list_item_instance.setInfo.assert_called_once_with("video", mock_playable.metadata)
        self.mock_list_item_instance.setProperty.assert_any_call("inputstream", "inputstream.adaptive")
        self.mock_list_item_instance.setProperty.assert_any_call("inputstream.adaptive.manifest_type", "mpd")
        self.mock_list_item_instance.setProperty.assert_any_call("inputstream.adaptive.license_type", "com.widevine.alpha")
        self.mock_list_item_instance.setProperty.assert_any_call("inputstream.adaptive.license_key", "http://mock.license/key")
        self.mock_list_item_instance.setProperty.assert_any_call("inputstream.adaptive.stream_headers", "User-Agent: MockUserAgent")
        self.mock_list_item_instance.setProperty.assert_any_call("path", "http://mock.manifest/url.mpd")

    def test_build_list_item_without_license(self):
        mock_playable = Playable(
            url="http://mock.manifest/url.mpd",
            manifest_type="mpd",
            license_key=None,
            headers={},
            metadata={"title": "Test Title No DRM"}
        )
        list_item = playback_module._build_list_item(mock_playable)
        
        self.mock_list_item_instance.setProperty.assert_any_call("inputstream.adaptive.manifest_type", "mpd")
        # Ensure license properties are NOT set
        self.assertNotIn(call("inputstream.adaptive.license_type", "com.widevine.alpha"), self.mock_list_item_instance.setProperty.call_args_list)
        self.assertNotIn(call("inputstream.adaptive.license_key", unittest.mock.ANY), self.mock_list_item_instance.setProperty.call_args_list)

if __name__ == '__main__':
    unittest.main()
