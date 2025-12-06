import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Import and apply global patches for Kodi modules
from .kodi_mocks import patch_kodi_modules_globally

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
from backend import prime_api
from backend.prime_api import PrimeVideo

class TestPrimeVideo(unittest.TestCase):
    def setUp(self):
        patch_kodi_modules_globally()
        # Reset the singleton for each test
        if 'prime_api.PrimeVideo' in sys.modules:
            del sys.modules['prime_api.PrimeVideo']
        self.pv = PrimeVideo()

    @patch('backend.prime_api.net.GrabJSON')
    def test_build_root(self, mock_grab_json):
        mock_grab_json.return_value = {
            "mainMenu": {
                "links": [{"id": "pv-nav-movies", "text": "Movies", "href": "/movies"}]
            }
        }
        self.assertTrue(self.pv.BuildRoot())
        self.assertIn("pv-nav-movies", self.pv._catalog['root'])

    @patch.object(PrimeVideo, 'BuildRoot')
    def test_browse_root(self, mock_build_root):
        self.pv._catalog = {'root': {'pv-nav-home': {'title': 'Home'}}}
        items, _ = self.pv.Browse('root')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Home')
        
    def test_search(self):
        items, _ = self.pv.Search("test")
        self.assertGreater(len(items), 0)
        self.assertIn("test", items[0]['title'])

    @patch('backend.prime_api.net.getURLData')
    def test_get_stream(self, mock_get_url_data):
        mock_get_url_data.return_value = (True, {"manifestUrl": "http://test.mpd"})
        success, data = self.pv.GetStream("B012345")
        self.assertTrue(success)
        self.assertEqual(data['manifestUrl'], "http://test.mpd")

if __name__ == '__main__':
    unittest.main()