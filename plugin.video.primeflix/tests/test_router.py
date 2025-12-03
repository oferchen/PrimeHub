import unittest
from unittest.mock import MagicMock, patch

# Mock Kodi imports and environment for testing outside Kodi
class MockXBMCPlugin:
    SORT_METHOD_UNSORTED = 0
    def addDirectoryItems(self, handle, items): pass
    def endOfDirectory(self, handle, succeeded=True): pass
    def setContent(self, handle, content): pass
    def setResolvedUrl(self, handle, succeeded, listitem): pass

class MockXBMC:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 3
    def log(self, message: str, level: int = 0) -> None: pass

# Patch Kodi modules globally before other imports
sys.modules = {
    'xbmcplugin': MagicMock(spec=MockXBMCPlugin),
    'xbmc': MockXBMC(),
    'xbmcaddon': MagicMock(),
    'xbmcgui': MagicMock()
}

# Set up sys.argv for router to parse
import sys
sys.argv = ['default.py', '1', '']

# Add the lib directory to sys.path so we can import router
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test AFTER setting up mocks
import router
from router import dispatch, PluginContext
from preflight import PreflightError

class TestRouter(unittest.TestCase):
    def setUp(self):
        # Reset mocks before each test
        sys.argv = ['default.py', '1', '']
        sys.modules['xbmcplugin'].reset_mock()
        
        # Start and manage patches manually for clarity
        self.patchers = {
            'home': patch('router.home').start(),
            'listing': patch('router.listing').start(),
            'playback': patch('router.playback').start(),
            'diagnostics': patch('router.diagnostics').start(),
            'login': patch('router.login').start(),
            'show_preflight_error': patch('router.show_preflight_error').start(),
            'get_backend': patch('router.get_backend').start()
        }
        self.mock_backend = self.patchers['get_backend'].return_value

    def tearDown(self):
        patch.stopall() # Stop all patches started in setUp

    def test_plugin_context_build_url(self):
        context = PluginContext("plugin://plugin.video.primeflix/", 1)
        url = context.build_url(action="list", rail="movies")
        self.assertEqual(url, "plugin://plugin.video.primeflix/?action=list&rail=movies")

    @patch('sys.argv', ['default.py', '1', ''])
    def test_dispatch_not_logged_in_redirects_to_login(self):
        self.mock_backend.is_logged_in.return_value = False
        self.patchers['login'].show_login_screen.return_value = False # Simulate user cancels login
        
        dispatch("plugin://plugin.video.primeflix/", "")
        self.patchers['get_backend'].assert_called_once()
        self.mock_backend.is_logged_in.assert_called_once()
        self.patchers['login'].show_login_screen.assert_called_once()
        self.patchers['home'].show_home.assert_not_called() # Should not proceed to home

    @patch('sys.argv', ['default.py', '1', ''])
    def test_dispatch_proceeds_if_login_successful(self):
        self.mock_backend.is_logged_in.return_value = False
        self.patchers['login'].show_login_screen.return_value = True # Simulate successful login
        
        dispatch("plugin://plugin.video.primeflix/", "")
        self.patchers['home'].show_home.assert_called_once() # Should now proceed to home

    @patch('sys.argv', ['default.py', '1', '?action=login'])
    def test_dispatch_login_action(self):
        self.mock_backend.is_logged_in.return_value = False # Does not matter for this action
        dispatch("plugin://plugin.video.primeflix/", "?action=login")
        self.patchers['login'].show_login_screen.assert_called_once()
        sys.modules['xbmcplugin'].endOfDirectory.assert_called_once_with(1)

    @patch('sys.argv', ['default.py', '1', '?action=logout'])
    def test_dispatch_logout_action(self):
        self.mock_backend.is_logged_in.return_value = True
        dispatch("plugin://plugin.video.primeflix/", "?action=logout")
        self.mock_backend.logout.assert_called_once()
        sys.modules['xbmcplugin'].endOfDirectory.assert_called_once_with(1)

    @patch('sys.argv', ['default.py', '1', ''])
    def test_dispatch_default_action_when_logged_in(self):
        self.mock_backend.is_logged_in.return_value = True
        dispatch("plugin://plugin.video.primeflix/", "")
        self.patchers['home'].show_home.assert_called_once()
        sys.modules['xbmcplugin'].endOfDirectory.assert_called_once_with(1)
        
    @patch('sys.argv', ['default.py', '1', '?action=list&rail=my_rail'])
    @patch('router.listing.show_list', side_effect=PreflightError("Test Preflight Error"))
    def test_dispatch_preflight_error_handling(self, mock_show_list):
        self.mock_backend.is_logged_in.return_value = True # Assume logged in for this test
        dispatch("plugin://plugin.video.primeflix/", "action=list&rail=my_rail")
        self.patchers['show_preflight_error'].assert_called_once_with(unittest.mock.ANY)
        sys.modules['xbmcplugin'].endOfDirectory.assert_called_once_with(1, succeeded=False)

if __name__ == '__main__':
    unittest.main()