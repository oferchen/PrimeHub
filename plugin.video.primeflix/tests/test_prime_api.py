import unittest
from unittest.mock import MagicMock, patch
import sys
import os

from .kodi_mocks import patch_kodi_modules_globally
patch_kodi_modules_globally()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))
from backend.prime_api import PrimeVideo

# A mock JSON response for GetPlaybackResources, based on Sandmann79 analysis
MOCK_STREAM_JSON = {
    "playbackUrls": {
        "mainManifestUrl": "http://mock.playback/manifest.mpd"
    },
    "license": {
        "licenseUrl": "http://mock.license/server"
    },
    "audioTracks": [
        {"audioTrackId": "A1", "languageCode": "en_US"}
    ],
    "timedTextTracks": [
        {"languageCode": "en_US", "type": "SUBTITLE", "url": "http://mock.subtitle/en.srt"}
    ]
}

class TestPrimeVideo(unittest.TestCase):
    def setUp(self):
        # Reset the singleton for each test
        if PrimeVideo in PrimeVideo._instances:
            del PrimeVideo._instances[PrimeVideo]
        self.pv = PrimeVideo()

    @patch('backend.prime_api.net.getURLData')
    def test_get_stream_success(self, mock_get_url_data):
        """Tests that GetStream successfully parses a valid JSON response."""
        mock_get_url_data.return_value = (True, MOCK_STREAM_JSON)
        
        success, stream_info = self.pv.GetStream("B012345")
        
        self.assertTrue(success)
        self.assertEqual(stream_info['manifest_url'], "http://mock.playback/manifest.mpd")
        self.assertEqual(stream_info['license_url'], "http://mock.license/server")
        self.assertEqual(len(stream_info['audio_tracks']), 1)
        self.assertEqual(stream_info['audio_tracks'][0]['languageCode'], "en_US")
        self.assertEqual(len(stream_info['subtitle_tracks']), 1)

    @patch('backend.prime_api.net.getURLData')
    def test_get_stream_failure_on_api_error(self, mock_get_url_data):
        """Tests that GetStream returns False when the API call fails."""
        mock_get_url_data.return_value = (False, "API Error")
        success, data = self.pv.GetStream("B012345")
        self.assertFalse(success)
        self.assertEqual(data, "API Error")

    @patch('backend.prime_api.net.getURLData')
    def test_get_stream_failure_on_bad_json(self, mock_get_url_data):
        """Tests that GetStream returns False when the JSON is missing required keys."""
        mock_get_url_data.return_value = (True, {"error": "bad data"})
        success, data = self.pv.GetStream("B012345")
        self.assertFalse(success)
        self.assertIn("Failed to parse stream data", data)

if __name__ == '__main__':
    unittest.main()
