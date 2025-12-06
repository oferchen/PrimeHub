import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Import and apply global patches for Kodi modules
from .kodi_mocks import patch_kodi_modules_globally

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import router
from router import dispatch, PluginContext
from preflight import PreflightError

class TestRouter(unittest.TestCase):
    def setUp(self):
        patch_kodi_modules_globally()
        
        # Start and manage patches manually
        self.patchers = {
            'home': patch('router.home').start(),
            'listing': patch('router.listing').start(),
            'playback': patch('router.playback').start(),
            'login': patch('router.login').start(),
            'show_preflight_error': patch('router.show_preflight_error').start(),
            'get_prime_video': patch('router.get_prime_video').start()
        }
        self.mock_pv = self.patchers['get_prime_video'].return_value

    def tearDown(self):
        patch.stopall()

    @patch('sys.argv', ['default.py', '1', ''])
    def test_dispatch_default_action(self):
        dispatch("plugin://plugin.video.primeflix/", "")
        self.patchers['home'].show_home.assert_called_once_with(unittest.mock.ANY, self.mock_pv)

    @patch('sys.argv', ['default.py', '1', '?action=list&rail_id=my_rail'])
    def test_dispatch_list_action(self):
        dispatch("plugin://plugin.video.primeflix/", "action=list&rail_id=my_rail")
        self.patchers['listing'].show_list.assert_called_once_with(unittest.mock.ANY, self.mock_pv, "my_rail")

    @patch('sys.argv', ['default.py', '1', '?action=play&asin=B012345'])
    def test_dispatch_play_action(self):
        dispatch("plugin://plugin.video.primeflix/", "action=play&asin=B012345")
        self.patchers['playback'].play.assert_called_once_with(unittest.mock.ANY, self.mock_pv, "B012345")

    @patch('sys.argv', ['default.py', '1', '?action=search&query=my_query'])
    def test_dispatch_search_action(self):
        # Assuming show_search is in listing.py
        dispatch("plugin://plugin.video.primeflix/", "action=search&query=my_query")
        self.patchers['listing'].show_search.assert_called_once_with(unittest.mock.ANY, self.mock_pv, "my_query")

if __name__ == '__main__':
    unittest.main()