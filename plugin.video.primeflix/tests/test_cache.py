import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os
import json
import time

# Mock Kodi imports for testing outside Kodi
class MockXBMC:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 3
    def log(self, message: str, level: int = 0) -> None: pass

class MockXBMCAddon:
    def Addon(self, addon_id=None):
        mock_addon = MagicMock()
        mock_addon.getAddonInfo.return_value = "/mock/profile/addon_data/plugin.video.primeflix" # for profile path
        return mock_addon

class MockXBMCRuntime:
    def exists(self, path): return False
    def mkdirs(self, path): pass
    def translatePath(self, path): return path
    def delete(self, path): pass
    def File(self, path, mode='r'):
        # This is a bit complex as mock_open doesn't handle read/write on separate calls well
        # We'll use a side_effect or global state for simplicity in actual tests
        pass

# Patch Kodi modules globally before other imports
sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = MockXBMCAddon()
sys.modules['xbmcvfs'] = MockXBMCRuntime()

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import cache as cache_module


class TestCache(unittest.TestCase):

    def setUp(self):
        # Reset mocks before each test
        sys.modules['xbmcvfs'] = MockXBMCRuntime() # Fresh mock for each test
        self.mock_xbmcvfs = sys.modules['xbmcvfs']
        self.cache_instance = cache_module.get_cache() # Get a fresh instance
        self.cache_instance._base_path = "/mock/cache" # Override base path for testing
        self.cache_instance._lock = MagicMock() # Mock lock

        # Ensure directory exists for tests
        self.mock_xbmcvfs.exists.side_effect = lambda path: path == self.cache_instance._base_path
        
    def test_cache_init_creates_dir(self):
        self.mock_xbmcvfs.exists.return_value = False
        cache_module.get_cache()._base_path = "/new/mock/cache" # Set new path
        cache_module.get_cache()._base_path = "/new/mock/cache" # Ensure init path is covered
        self.mock_xbmcvfs.mkdirs.assert_called_once_with("/new/mock/cache")

    @patch('time.time', return_value=1000)
    def test_set_and_get_success(self, mock_time):
        mock_file_content = ""
        mock_file_obj = MagicMock()
        mock_file_obj.__enter__.return_value = mock_file_obj
        mock_file_obj.write.side_effect = lambda data: globals().update(mock_file_content=data)
        mock_file_obj.read.side_effect = lambda: globals().update(mock_file_content=mock_file_content)

        with patch('xbmcvfs.File', return_value=mock_file_obj):
            self.mock_xbmcvfs.exists.side_effect = lambda path: path == self.cache_instance._filepath("test_key")

            self.cache_instance.set("test_key", {"data": "value"}, 60)
            self.assertEqual(json.loads(mock_file_content)['data'], {"data": "value"})

            retrieved_data = self.cache_instance.get("test_key")
            self.assertEqual(retrieved_data, {"data": "value"})

    @patch('time.time', side_effect=[1000, 1070]) # Current time, then 70s later
    def test_get_stale_data_deleted(self, mock_time):
        mock_file_content = json.dumps({"timestamp": 1000, "ttl": 60, "key": "stale_key", "data": "stale"})
        
        mock_file_obj = MagicMock()
        mock_file_obj.__enter__.return_value = mock_file_obj
        mock_file_obj.read.return_value = mock_file_content

        with patch('xbmcvfs.File', return_value=mock_file_obj):
            self.mock_xbmcvfs.exists.side_effect = lambda path: path == self.cache_instance._filepath("stale_key")

            retrieved_data = self.cache_instance.get("stale_key")
            self.assertIsNone(retrieved_data)
            self.mock_xbmcvfs.delete.assert_called_once_with(self.cache_instance._filepath("stale_key"))

    def test_get_corrupted_data_deleted(self):
        corrupted_content = "not valid json"
        mock_file_obj = MagicMock()
        mock_file_obj.__enter__.return_value = mock_file_obj
        mock_file_obj.read.return_value = corrupted_content

        with patch('xbmcvfs.File', return_value=mock_file_obj):
            self.mock_xbmcvfs.exists.side_effect = lambda path: path == self.cache_instance._filepath("corrupted_key")

            retrieved_data = self.cache_instance.get("corrupted_key")
            self.assertIsNone(retrieved_data)
            self.mock_xbmcvfs.delete.assert_called_once_with(self.cache_instance._filepath("corrupted_key"))

    def test_delete_key(self):
        self.mock_xbmcvfs.exists.return_value = True
        self.cache_instance.delete("key_to_delete")
        self.mock_xbmcvfs.delete.assert_called_once_with(self.cache_instance._filepath("key_to_delete"))

    @patch('os.listdir', return_value=['prefix_1.json', 'other_key.json', 'prefix_2.json'])
    @patch('xbmcvfs.File')
    def test_clear_prefix(self, mock_file_class, mock_listdir):
        # Setup mock file contents for listdir
        def mock_read_content(path, mode):
            if 'prefix_1.json' in path: return json.dumps({'key': 'prefix_1'})
            if 'prefix_2.json' in path: return json.dumps({'key': 'prefix_2'})
            if 'other_key.json' in path: return json.dumps({'key': 'other_key'})
            return '{}'

        mock_file_instance = MagicMock()
        mock_file_instance.__enter__.return_value = mock_file_instance
        mock_file_instance.read.side_effect = mock_read_content
        mock_file_class.return_value = mock_file_instance
        
        self.mock_xbmcvfs.exists.return_value = True # Assume files exist
        
        self.cache_instance.clear_prefix("prefix_")
        self.assertEqual(self.mock_xbmcvfs.delete.call_count, 2)
        self.mock_xbmcvfs.delete.assert_has_calls([
            call(self.cache_instance._filepath("prefix_1")),
            call(self.cache_instance._filepath("prefix_2"))
        ], any_order=True)

    @patch('os.listdir', return_value=['file1.json', 'file2.txt', 'file3.json'])
    def test_clear_all(self, mock_listdir):
        self.mock_xbmcvfs.exists.return_value = True # Assume dir exists
        self.cache_instance.clear_all()
        self.assertEqual(self.mock_xbmcvfs.delete.call_count, 2)
        self.mock_xbmcvfs.delete.assert_has_calls([
            call(os.path.join(self.cache_instance._base_path, 'file1.json')),
            call(os.path.join(self.cache_instance._base_path, 'file3.json'))
        ], any_order=True)

if __name__ == '__main__':
    unittest.main()
