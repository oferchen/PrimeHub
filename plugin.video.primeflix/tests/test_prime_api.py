import unittest
from unittest.mock import MagicMock, patch, call


# Mock Kodi imports and environment for testing outside Kodi
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    def log(self, message: str, level: int = 0) -> None:
        pass  # Suppress logging during tests


class MockXBMCAddon:
    def Addon(self, addon_id=None):
        mock_addon = MagicMock()
        mock_addon.getAddonInfo.side_effect = lambda key: {
            "id": addon_id or "plugin.video.primeflix",
            "profile": "/mock/path/to/profile",
            "path": "/mock/path/to/addon",
            "fanart": "/mock/path/to/fanart.jpg",
            "name": "PrimeHub",
        }.get(key, "")
        mock_addon.getSetting.side_effect = lambda key: {
            "region": "0",  # us
            "max_resolution": "0",  # auto
            "use_cache": "true",
            "cache_ttl": "300",
            "perf_logging": "false",
        }.get(key, "0")
        mock_addon.getSettingBool.side_effect = lambda key: {
            "use_cache": True,
            "perf_logging": False,
        }.get(key, False)
        mock_addon.getSettingInt.side_effect = lambda key: {
            "cache_ttl": 300,
        }.get(key, 0)
        mock_addon.getLocalizedString.side_effect = (
            lambda code: f"LocalizedString_{code}"
        )
        return mock_addon


# Patch xbmc and xbmcaddon globally for the test environment
# This needs to be done before importing prime_api
original_sys_path = list(sys.path)  # Store original sys.path
sys.modules["xbmc"] = MockXBMC()
sys.modules["xbmcaddon"] = MockXBMCAddon()
# sys.modules['xbmcgui'] = MagicMock() # Not used directly in prime_api

# Add the lib directory to sys.path so we can import prime_api
import sys
import os

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../resources/lib"))
)

# Import the module under test AFTER setting up mocks and path
import prime_api
from prime_api import (
    PrimeAPI,
    BackendUnavailable,
    BackendError,
    Playable,
    _AmazonVODIntegration,
    _JsonRPCIntegration,
    normalize_rail,
    normalize_item,
)

# Restore sys.path after import
sys.path = original_sys_path


class TestPrimeAPI(unittest.TestCase):

    def setUp(self):
        # Ensure _backend_instance is reset for each test
        prime_api._backend_instance = None

        # Reset getSetting mocks to default for each test
        mock_addon_instance = xbmcaddon.Addon()
        mock_addon_instance.getSetting.side_effect = lambda key: {
            "region": "0",  # us
            "max_resolution": "0",  # auto
        }.get(key, "0")
        mock_addon_instance.getSettingBool.side_effect = lambda key: {
            "use_cache": True,
            "perf_logging": False,
        }.get(key, False)
        mock_addon_instance.getSettingInt.side_effect = lambda key: {
            "cache_ttl": 300,
        }.get(key, 0)
        mock_addon_instance.getLocalizedString.side_effect = (
            lambda code: f"LocalizedString_{code}"
        )

    @patch("prime_api.discover_backend", return_value="plugin.video.amazonvod")
    @patch("prime_api._AmazonVODIntegration")
    @patch("prime_api._JsonRPCIntegration")
    def test_primeapi_init_direct_success(
        self, MockJsonRPCIntegration, MockAmazonVODIntegration, mock_discover_backend
    ):
        # Test case: Direct import succeeds
        mock_amazon_instance = MagicMock()
        MockAmazonVODIntegration.return_value = mock_amazon_instance

        api = PrimeAPI()
        self.assertIsInstance(
            api._strategy, MagicMock
        )  # It's a MagicMock instance returned by patch
        self.assertEqual(api._strategy_name, "direct_import")
        MockAmazonVODIntegration.assert_called_once_with(
            "plugin.video.amazonvod", api._addon
        )
        MockJsonRPCIntegration.assert_not_called()

    @patch("prime_api.discover_backend", return_value="plugin.video.amazonvod")
    @patch(
        "prime_api._AmazonVODIntegration",
        side_effect=BackendUnavailable("Direct failed"),
    )
    @patch("prime_api._JsonRPCIntegration")
    def test_primeapi_init_jsonrpc_fallback_success(
        self, MockJsonRPCIntegration, MockAmazonVODIntegration, mock_discover_backend
    ):
        # Test case: Direct import fails, JSON-RPC succeeds
        mock_jsonrpc_instance = MagicMock()
        MockJsonRPCIntegration.return_value = mock_jsonrpc_instance

        api = PrimeAPI()
        self.assertIsInstance(api._strategy, MagicMock)
        self.assertEqual(api._strategy_name, "json_rpc")
        MockAmazonVODIntegration.assert_called_once_with(
            "plugin.video.amazonvod", api._addon
        )
        MockJsonRPCIntegration.assert_called_once_with(
            "plugin.video.amazonvod", api._addon
        )

    @patch("prime_api.discover_backend", return_value="plugin.video.amazonvod")
    @patch(
        "prime_api._AmazonVODIntegration",
        side_effect=BackendUnavailable("Direct failed"),
    )
    @patch(
        "prime_api._JsonRPCIntegration",
        side_effect=BackendUnavailable("JSON-RPC failed"),
    )
    def test_primeapi_init_all_fail(
        self, MockJsonRPCIntegration, MockAmazonVODIntegration, mock_discover_backend
    ):
        # Test case: Both strategies fail
        with self.assertRaises(BackendUnavailable):
            PrimeAPI()
        # _addon is an instance of MockXBMCAddon.Addon(), which is also a MagicMock
        MockAmazonVODIntegration.assert_called_once_with(
            "plugin.video.amazonvod", unittest.mock.ANY
        )
        MockJsonRPCIntegration.assert_called_once_with(
            "plugin.video.amazonvod", unittest.mock.ANY
        )

    @patch("prime_api.discover_backend", return_value=None)
    def test_primeapi_init_no_backend_found(self, mock_discover_backend):
        # Test case: No backend addon discovered
        with self.assertRaises(BackendUnavailable):
            PrimeAPI()


# --- Tests for _AmazonVODIntegration methods ---
class TestAmazonVODIntegration(unittest.TestCase):
    def setUp(self):
        self.addon_id = "plugin.video.amazonvod"
        self.mock_addon = MagicMock(spec=xbmcaddon.Addon)
        self.mock_pv = MagicMock()

        # Mock _AmazonVODIntegration to bypass _init_amazon_modules and directly set _pv
        with patch("prime_api._AmazonVODIntegration._init_amazon_modules"):
            self.integration = _AmazonVODIntegration(self.addon_id, self.mock_addon)
            self.integration._pv = self.mock_pv  # Manually set the mocked _pv

        # Configure default settings for the mock addon
        self.mock_addon.getSetting.side_effect = lambda key: {
            "region": "0",  # us
            "max_resolution": "0",  # auto
        }.get(key, "0")

    def test_get_home_rails_success(self):
        self.mock_pv._catalog = {"root": {"movies": {"title": "Movies Rail"}}}
        rails = self.integration.get_home_rails()
        self.assertEqual(len(rails), 1)
        self.assertEqual(rails[0]["id"], "movies")

    def test_get_home_rails_default_fallback(self):
        # Test when _catalog is empty or invalid
        self.mock_pv._catalog = {"root": {}}
        rails = self.integration.get_home_rails()
        self.assertGreater(len(rails), 0)
        self.assertIn(
            {
                "id": "watchlist",
                "title": "My Watchlist",
                "type": "mixed",
                "path": "watchlist",
            },
            rails,
        )

    def test_get_home_rails_no_pv(self):
        self.integration._pv = None
        rails = self.integration.get_home_rails()
        self.assertGreater(len(rails), 0)  # Should fall back to defaults

    def test_get_rail_items_success(self):
        self.mock_pv._catalog = {
            "root": {"movies": {"content": [{"asin": "123", "title": "Movie 1"}]}}
        }
        items, next_cursor = self.integration.get_rail_items("movies", None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["asin"], "123")
        self.assertIsNone(next_cursor)

    def test_get_rail_items_launcher_fallback(self):
        self.mock_pv._catalog = {}  # No catalog means no items
        items, next_cursor = self.integration.get_rail_items("unknown_rail", None)
        self.assertEqual(len(items), 1)
        self.assertIn("LAUNCHER_", items[0]["asin"])

    def test_get_playable_success(self):
        mock_stream_data = {
            "url": "http://manifest.url",
            "type": "mpd",
            "drm": {"type": "com.widevine.alpha", "license_url": "http://license.url"},
            "headers": {"User-Agent": "test"},
            "metadata": {"title": "Test Movie"},
        }
        self.mock_pv.GetStream.return_value = mock_stream_data

        playable = self.integration.get_playable("test_asin")
        self.assertEqual(playable.url, "http://manifest.url")
        self.assertEqual(playable.manifest_type, "mpd")
        self.assertEqual(playable.license_key, "http://license.url")
        self.assertEqual(playable.metadata["title"], "Test Movie")
        self.mock_pv.GetStream.assert_called_once_with(asin="test_asin", play=False)

    def test_get_playable_backend_error(self):
        self.mock_pv.GetStream.side_effect = Exception("PV error")
        with self.assertRaises(BackendError):
            self.integration.get_playable("test_asin")

    def test_search_success(self):
        mock_search_results = {
            "content": [{"asin": "s1", "title": "Search Result 1"}],
            "next_page_cursor": "next_page",
        }
        self.mock_pv.Search.return_value = mock_search_results

        items, next_cursor = self.integration.search("query", None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["asin"], "s1")
        self.assertEqual(next_cursor, "next_page")
        self.mock_pv.Search.assert_called_once_with("query", page=None)

    def test_get_region_info_success(self):
        self.mock_pv.getRegion.return_value = {"country": "US"}
        region = self.integration.get_region_info()
        self.assertEqual(region, {"country": "US"})
        self.mock_pv.getRegion.assert_called_once()

    def test_is_drm_ready_success(self):
        self.mock_pv.isDRMReady.return_value = True
        is_ready = self.integration.is_drm_ready()
        self.assertTrue(is_ready)
        self.mock_pv.isDRMReady.assert_called_once()


# --- Tests for _JsonRPCIntegration methods ---
class TestJsonRPCIntegration(unittest.TestCase):
    def setUp(self):
        self.addon_id = "plugin.video.amazonvod"
        self.mock_addon = MagicMock(spec=xbmcaddon.Addon)
        self.integration = _JsonRPCIntegration(self.addon_id, self.mock_addon)

        # Configure default settings for the mock addon
        self.mock_addon.getSetting.side_effect = lambda key: {
            "region": "0",  # us
            "max_resolution": "0",  # auto
        }.get(key, "0")

    @patch("prime_api.xbmc.executeJSONRPC")
    def test_get_home_rails_success(self, mock_executeJSONRPC):
        mock_executeJSONRPC.return_value = (
            '{"result": "[{"id": "r1", "title": "Rail 1"}]"}'
        )
        rails = self.integration.get_home_rails()
        self.assertEqual(len(rails), 1)
        self.assertEqual(rails[0]["id"], "r1")
        mock_executeJSONRPC.assert_called_once()

    @patch("prime_api.xbmc.executeJSONRPC")
    def test_get_home_rails_rpc_error(self, mock_executeJSONRPC):
        mock_executeJSONRPC.return_value = '{"error": {"message": "RPC Error"}}'
        with self.assertRaises(BackendError):
            self.integration.get_home_rails()

    @patch("prime_api.xbmc.executeJSONRPC")
    def test_get_rail_items_success(self, mock_executeJSONRPC):
        mock_executeJSONRPC.return_value = (
            '{"result": "{"items": [{"asin": "i1"}], "next_cursor": "c1"}"}'
        )
        items, next_cursor = self.integration.get_rail_items("rail_id", None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["asin"], "i1")
        self.assertEqual(next_cursor, "c1")
        mock_executeJSONRPC.assert_called_once()

    @patch("prime_api.xbmc.executeJSONRPC")
    def test_get_playable_success(self, mock_executeJSONRPC):
        mock_playable_data = {
            "url": "http://manifest.url",
            "manifest_type": "mpd",
            "license_key": "http://license.url",
            "headers": {"User-Agent": "test"},
            "metadata": {"title": "Test Playable"},
        }
        mock_executeJSONRPC.return_value = (
            f'{{"result": "{json.dumps(mock_playable_data).replace("\"", "\\\"")}"}}'
        )

        playable = self.integration.get_playable("asin1")
        self.assertEqual(playable.url, "http://manifest.url")
        self.assertEqual(playable.metadata["title"], "Test Playable")
        mock_executeJSONRPC.assert_called_once()

    @patch("prime_api.xbmc.executeJSONRPC")
    def test_search_success(self, mock_executeJSONRPC):
        mock_search_results = {
            "items": [{"asin": "s1", "title": "Search Result 1"}],
            "next_cursor": "next_page",
        }
        mock_executeJSONRPC.return_value = (
            f'{{"result": "{json.dumps(mock_search_results).replace("\"", "\\\"")}"}}'
        )

        items, next_cursor = self.integration.search("query", None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["asin"], "s1")
        self.assertEqual(next_cursor, "next_page")
        mock_executeJSONRPC.assert_called_once()

    @patch("prime_api.xbmc.executeJSONRPC")
    def test_get_region_info_success(self, mock_executeJSONRPC):
        mock_executeJSONRPC.return_value = '{"result": "{"country": "US"}"}'
        region = self.integration.get_region_info()
        self.assertEqual(region, {"country": "US"})
        mock_executeJSONRPC.assert_called_once()

    @patch("prime_api.xbmc.executeJSONRPC")
    def test_is_drm_ready_success_bool(self, mock_executeJSONRPC):
        mock_executeJSONRPC.return_value = '{"result": "true"}'
        is_ready = self.integration.is_drm_ready()
        self.assertTrue(is_ready)
        mock_executeJSONRPC.assert_called_once()

    @patch("prime_api.xbmc.executeJSONRPC")
    def test_is_drm_ready_success_dict(self, mock_executeJSONRPC):
        mock_executeJSONRPC.return_value = '{"result": "{"ready": true}"}'
        is_ready = self.integration.is_drm_ready()
        self.assertTrue(is_ready)
        mock_executeJSONRPC.assert_called_once()


# --- Tests for normalize functions ---
class TestNormalizeFunctions(unittest.TestCase):
    def test_normalize_rail(self):
        raw_rail = {
            "id": "test_id",
            "title": "Test Title",
            "type": "movies",
            "path": "/path",
        }
        normalized = normalize_rail(raw_rail)
        self.assertEqual(normalized["id"], "test_id")
        self.assertEqual(normalized["title"], "Test Title")
        self.assertEqual(normalized["type"], "movies")

    def test_normalize_item(self):
        raw_item = {
            "asin": "a1",
            "title": "Item Title",
            "plot": "Plot",
            "year": 2020,
            "duration": 120,
            "art": {"poster": "p.jpg"},
            "is_movie": True,
        }
        normalized = normalize_item(raw_item)
        self.assertEqual(normalized["asin"], "a1")
        self.assertEqual(normalized["title"], "Item Title")
        self.assertTrue(normalized["is_movie"])
        self.assertEqual(normalized["art"]["poster"], "p.jpg")


if __name__ == "__main__":
    unittest.main()
