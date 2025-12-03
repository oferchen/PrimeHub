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
    INPUT_PASSWORD = 1
    Dialog = MagicMock()

# Patch Kodi modules globally before other imports
sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = MockXBMCAddon()
sys.modules['xbmcgui'] = MockXBMCGUI()

# Add the lib directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/lib')))

# Import the module under test
import ui.login as login_module
from backend.prime_api import AuthenticationError

class TestUILogin(unittest.TestCase):

    def setUp(self):
        # Reset mocks before each test
        sys.modules['xbmcaddon'].Addon.reset_mock()
        sys.modules['xbmcgui'].Dialog.reset_mock()
        
        # Patch get_backend
        self.patcher_get_backend = patch('ui.login.get_backend')
        self.mock_get_backend = self.patcher_get_backend.start()
        self.mock_backend_instance = MagicMock()
        self.mock_get_backend.return_value = self.mock_backend_instance

        # Mock Dialog instance
        self.mock_dialog_instance = MagicMock()
        sys.modules['xbmcgui'].Dialog.return_value = self.mock_dialog_instance

    def tearDown(self):
        self.patcher_get_backend.stop()

    def test_show_login_screen_success(self):
        self.mock_dialog_instance.input.side_effect = ["testuser", "testpass"]
        self.mock_backend_instance.login.return_value = True

        result = login_module.show_login_screen()
        self.assertTrue(result)
        
        self.assertEqual(self.mock_dialog_instance.input.call_count, 2)
        self.mock_dialog_instance.input.assert_any_call("LocalizedString_32001")
        self.mock_dialog_instance.input.assert_any_call("LocalizedString_32002", option=sys.modules['xbmcgui'].INPUT_PASSWORD)
        self.mock_backend_instance.login.assert_called_once_with("testuser", "testpass")
        self.mock_dialog_instance.ok.assert_called_once_with("LocalizedString_32003", "LocalizedString_32004")

    def test_show_login_screen_cancel_username(self):
        self.mock_dialog_instance.input.side_effect = ["", "testpass"] # Username empty
        
        result = login_module.show_login_screen()
        self.assertFalse(result)
        
        self.mock_dialog_instance.input.assert_called_once_with("LocalizedString_32001")
        self.mock_backend_instance.login.assert_not_called()
        self.mock_dialog_instance.ok.assert_not_called()

    def test_show_login_screen_cancel_password(self):
        self.mock_dialog_instance.input.side_effect = ["testuser", ""] # Password empty
        
        result = login_module.show_login_screen()
        self.assertFalse(result)
        
        self.assertEqual(self.mock_dialog_instance.input.call_count, 2)
        self.mock_dialog_instance.input.assert_any_call("LocalizedString_32001")
        self.mock_dialog_instance.input.assert_any_call("LocalizedString_32002", option=sys.modules['xbmcgui'].INPUT_PASSWORD)
        self.mock_backend_instance.login.assert_not_called()
        self.mock_dialog_instance.ok.assert_not_called()

    def test_show_login_screen_backend_login_returns_false(self):
        self.mock_dialog_instance.input.side_effect = ["testuser", "testpass"]
        self.mock_backend_instance.login.return_value = False

        result = login_module.show_login_screen()
        self.assertFalse(result)
        
        self.mock_backend_instance.login.assert_called_once_with("testuser", "testpass")
        self.mock_dialog_instance.ok.assert_called_once_with("LocalizedString_32005", "LocalizedString_32006")

    def test_show_login_screen_backend_login_raises_authentication_error(self):
        self.mock_dialog_instance.input.side_effect = ["testuser", "testpass"]
        self.mock_backend_instance.login.side_effect = AuthenticationError("Some auth error")

        result = login_module.show_login_screen()
        self.assertFalse(result)
        
        self.mock_backend_instance.login.assert_called_once_with("testuser", "testpass")
        self.mock_dialog_instance.ok.assert_called_once_with("LocalizedString_32005", "Some auth error")

if __name__ == '__main__':
    unittest.main()
