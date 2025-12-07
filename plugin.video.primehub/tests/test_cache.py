import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import json
import time

# Import and apply global patches for Kodi modules
from .kodi_mocks import patch_kodi_modules_globally

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import cache as cache_module


class TestCache(unittest.TestCase):

    def setUp(self):
        patch_kodi_modules_globally()
        self.mock_xbmcvfs = sys.modules['xbmcvfs']
        
        # Reset get_cache to ensure a fresh instance
        cache_module._cache_instance = None
        self.cache_instance = cache_module.get_cache()
        self.cache_instance._base_path = "/mock/cache" # Override base path
        self.cache_instance._lock = MagicMock() # Mock lock

        # Ensure directory exists for tests
        self.mock_xbmcvfs.exists.side_effect = lambda path: path == self.cache_instance._base_path
        
    def tearDown(self):
        patch.stopall()

    # ... (rest of the tests remain the same, they should work with the new mock setup)
    @patch('time.time', return_value=1000)
    def test_set_and_get_success(self, mock_time):
        mock_file_content = ""
        mock_file_obj = MagicMock()
        mock_file_obj.__enter__.return_value = mock_file_obj
        mock_file_obj.write.side_effect = lambda data: globals().update(mock_file_content=data)
        
        with patch('xbmcvfs.File', return_value=mock_file_obj):
            self.mock_xbmcvfs.exists.side_effect = lambda path: path == self.cache_instance._filepath("test_key")
            
            self.cache_instance.set("test_key", {"data": "value"}, 60)
            
            # Now, simulate the read
            mock_file_obj.read.return_value = mock_file_content
            retrieved_data = self.cache_instance.get("test_key")
            self.assertEqual(retrieved_data, {"data": "value"})

if __name__ == '__main__':
    unittest.main()