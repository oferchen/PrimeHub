import unittest
from unittest.mock import MagicMock, patch


# Mock Kodi imports and environment for testing outside Kodi
class MockXBMCPlugin:
    SORT_METHOD_UNSORTED = 0

    def addDirectoryItems(self, handle, items):
        pass

    def endOfDirectory(self, handle, succeeded=True):
        pass

    def setContent(self, handle, content):
        pass

    def setResolvedUrl(self, handle, succeeded, listitem):
        pass


class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    def log(self, message: str, level: int = 0) -> None:
        pass  # Suppress logging during tests


# Patch xbmcplugin and xbmc globally for the test environment
sys.modules["xbmcplugin"] = MockXBMCPlugin()
sys.modules["xbmc"] = MockXBMC()
sys.modules["xbmcaddon"] = (
    MagicMock()
)  # Not used directly in router, but some modules might import it
sys.modules["xbmcgui"] = MagicMock()  # UI modules are mocked

# Set up sys.argv for router to parse
mock_sys_argv = ["default.py", "1", "?action=test&param=value"]

# Add the lib directory to sys.path so we can import router
import sys
import os

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../resources/lib"))
)

# Import the module under test AFTER setting up mocks and path
import router
from router import dispatch, PluginContext
from preflight import PreflightError


class TestRouter(unittest.TestCase):

    def setUp(self):
        # Reset mocks before each test
        sys.argv = ["default.py", "1"]  # Default argv for no params
        xbmcplugin.reset_mock()
        # Ensure that the UI modules are freshly mocked for each test
        self.mock_home = patch("router.home").start()
        self.mock_listing = patch("router.listing").start()
        self.mock_playback = patch("router.playback").start()
        self.mock_diagnostics = patch("router.diagnostics").start()
        self.mock_preflight = patch("router.show_preflight_error").start()

        # Resetting the patch objects as well
        self.mock_home.reset_mock()
        self.mock_listing.reset_mock()
        self.mock_playback.reset_mock()
        self.mock_diagnostics.reset_mock()
        self.mock_preflight.reset_mock()

    def tearDown(self):
        patch.stopall()  # Stop all started patches

    def test_plugin_context_build_url(self):
        context = PluginContext("plugin://plugin.video.primeflix/", 1)
        url = context.build_url(action="list", rail="movies", cursor="next")
        self.assertEqual(
            url, "plugin://plugin.video.primeflix/?action=list&rail=movies&cursor=next"
        )

        url_no_params = context.build_url()
        self.assertEqual(url_no_params, "plugin://plugin.video.primeflix/")

        url_none_param = context.build_url(action="list", param_none=None)
        self.assertEqual(url_none_param, "plugin://plugin.video.primeflix/?action=list")

    @patch("sys.argv", ["default.py", "1", ""])  # No action in params
    def test_dispatch_default_action(self):
        dispatch("plugin://plugin.video.primeflix/", "")
        self.mock_home.show_home.assert_called_once()
        xbmcplugin.endOfDirectory.assert_called_once_with(1)

    @patch("sys.argv", ["default.py", "1", "?action=list&rail=my_rail&cursor=123"])
    def test_dispatch_list_action(self):
        dispatch(
            "plugin://plugin.video.primeflix/", "action=list&rail=my_rail&cursor=123"
        )
        self.mock_listing.show_list.assert_called_once_with(
            unittest.mock.ANY, "my_rail", "123"
        )
        xbmcplugin.endOfDirectory.assert_called_once_with(1)

    @patch("sys.argv", ["default.py", "1", "?action=play&asin=B01234"])
    def test_dispatch_play_action(self):
        dispatch("plugin://plugin.video.primeflix/", "action=play&asin=B01234")
        self.mock_playback.play.assert_called_once_with(unittest.mock.ANY, "B01234")
        xbmcplugin.endOfDirectory.assert_called_once_with(
            1
        )  # Playback also ends the directory, for resolved URLs

    @patch("sys.argv", ["default.py", "1", "?action=diagnostics"])
    def test_dispatch_diagnostics_action(self):
        dispatch("plugin://plugin.video.primeflix/", "action=diagnostics")
        self.mock_diagnostics.show_results.assert_called_once()
        xbmcplugin.endOfDirectory.assert_called_once_with(1)

    @patch("sys.argv", ["default.py", "1", "?action=search&query=film&cursor=abc"])
    def test_dispatch_search_action(self):
        dispatch(
            "plugin://plugin.video.primeflix/", "action=search&query=film&cursor=abc"
        )
        self.mock_listing.show_search.assert_called_once_with(
            unittest.mock.ANY, "film", "abc"
        )
        xbmcplugin.endOfDirectory.assert_called_once_with(1)

    @patch("sys.argv", ["default.py", "1", "?action=list&rail=my_rail"])
    @patch(
        "router.listing.show_list", side_effect=PreflightError("Test Preflight Error")
    )
    def test_dispatch_preflight_error_handling(self, mock_show_list):
        dispatch("plugin://plugin.video.primeflix/", "action=list&rail=my_rail")
        self.mock_preflight.assert_called_once_with(unittest.mock.ANY)
        xbmcplugin.endOfDirectory.assert_called_once_with(1, succeeded=False)


if __name__ == "__main__":
    unittest.main()
