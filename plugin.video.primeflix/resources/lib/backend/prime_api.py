from __future__ import annotations

import importlib
import json
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import xbmc
    import xbmcaddon
except ImportError:  # pragma: no cover - development fallback
    xbmc = None
    xbmcaddon = None


_LOG_INFO = 1
_LOG_WARNING = 2
_LOG_ERROR = 4

POSSIBLE_ADDONS = [
    "plugin.video.amazon-test",
    "plugin.video.amazonvod",
    "plugin.video.primevideo",
    "plugin.video.amazonprime",
    "plugin.video.amazon"
]

DIRECT_MODULE_CANDIDATES = [
    "resources.lib.api",
    "resources.lib.prime_api",
    "resources.lib.navigation",
    "resources.lib.main"
]


@dataclass
class Rail:
    identifier: str
    title: str
    items: List[Dict[str, Any]]
    content_type: str = "videos"


class PrimeBackend:
    """Encapsulates communication with the Prime Video backend add-on."""

    def __init__(self):
        self.strategy: Optional[str] = None
        self.addon_id: Optional[str] = None
        self._direct_module: Optional[Any] = None
        self._region: Optional[str] = None
        self._detect_backend()

    # region detection --------------------------------------------------
    def _detect_backend(self) -> None:
        for addon_id in POSSIBLE_ADDONS:
            module = self._try_direct_bind(addon_id)
            if module:
                self.strategy = "direct"
                self.addon_id = addon_id
                self._direct_module = module
                self._log(f"[PrimeFlix] Using direct backend strategy with {addon_id}")
                return
        for addon_id in POSSIBLE_ADDONS:
            if self._check_addon_exists(addon_id):
                self.strategy = "indirect"
                self.addon_id = addon_id
                self._log(f"[PrimeFlix] Using indirect backend strategy with {addon_id}")
                return
        self._log("[PrimeFlix] No compatible Prime backend found", _LOG_ERROR)

    def _check_addon_exists(self, addon_id: str) -> bool:
        if not xbmcaddon:
            return False
        try:
            xbmcaddon.Addon(addon_id)
            return True
        except Exception:
            return False

    def _try_direct_bind(self, addon_id: str):
        if not xbmcaddon:
            return None
        try:
            addon = xbmcaddon.Addon(addon_id)
        except Exception:
            return None
        path = addon.getAddonInfo("path")
        if path and path not in sys.path:
            sys.path.append(path)
        for module_name in DIRECT_MODULE_CANDIDATES:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
            if self._module_has_api(module):
                return module
        return None

    @staticmethod
    def _module_has_api(module: Any) -> bool:
        for attr in ("get_home_rails", "get_home", "home", "PrimeVideoAPI"):
            if hasattr(module, attr):
                return True
        return False

    # logging ------------------------------------------------------------
    def _log(self, message: str, level: int = _LOG_INFO) -> None:
        if xbmc:
            xbmc.log(message, level)
        else:  # pragma: no cover - development fallback
            print(f"[xbmc][{level}] {message}")

    # interface ----------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        return bool(self.addon_id and self.strategy)

    def get_backend_info(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy or "unknown",
            "addon_id": self.addon_id,
            "region": self.get_region()
        }

    def get_region(self) -> Optional[str]:
        if self._region:
            return self._region
        if self.strategy == "direct" and self._direct_module:
            self._region = self._call_direct(("get_region", "region"))
        elif self.strategy == "indirect" and self.addon_id:
            self._region = self._call_indirect("region")
        return self._region

    def get_home_rails(self) -> List[Rail]:
        raw = None
        if self.strategy == "direct" and self._direct_module:
            raw = self._call_direct(("get_home_rails", "get_home", "home"))
        elif self.strategy == "indirect" and self.addon_id:
            raw = self._call_indirect("home")
        rails = self._normalize_rails(raw)
        return rails

    def get_rail_items(self, rail_id: str, page: int = 1) -> Tuple[List[Dict[str, Any]], bool]:
        raw = None
        if self.strategy == "direct" and self._direct_module:
            raw = self._call_direct(("get_rail_items", "list_rail", "get_menu_items"), rail_id, page)
        elif self.strategy == "indirect" and self.addon_id:
            raw = self._call_indirect("list", rail=rail_id, page=page)
        items, has_more = self._normalize_items(raw)
        return items, has_more

    def search(self, query: str, page: int = 1) -> Tuple[List[Dict[str, Any]], bool]:
        raw = None
        if self.strategy == "direct" and self._direct_module:
            raw = self._call_direct(("search", "find"), query, page)
        elif self.strategy == "indirect" and self.addon_id:
            raw = self._call_indirect("search", query=query, page=page)
        items, has_more = self._normalize_items(raw)
        return items, has_more

    def get_playable(self, asin: str) -> Dict[str, Any]:
        if self.strategy == "direct" and self._direct_module:
            raw = self._call_direct(("get_playable", "play", "get_playback_info"), asin)
        elif self.strategy == "indirect" and self.addon_id:
            raw = self._call_indirect("play", asin=asin)
        else:
            raise RuntimeError("Prime backend not ready")
        return self._normalize_playback(raw)

    # direct strategy helpers --------------------------------------------
    def _call_direct(self, names: Iterable[str], *args: Any) -> Any:
        if not self._direct_module:
            raise RuntimeError("Direct backend missing")
        module = self._direct_module
        # object based API
        api_obj = None
        for attr in ("PrimeVideoAPI", "API", "PrimeApi"):
            if hasattr(module, attr):
                factory = getattr(module, attr)
                api_obj = factory() if callable(factory) else factory
                break
        for name in names:
            func = None
            if api_obj and hasattr(api_obj, name):
                func = getattr(api_obj, name)
            elif hasattr(module, name):
                func = getattr(module, name)
            if callable(func):
                return func(*args)
        raise RuntimeError(f"Direct backend method not found for {names}")

    # indirect strategy helpers ------------------------------------------
    def _call_indirect(self, action: str, **params: Any) -> Any:
        if not xbmc or not self.addon_id:
            raise RuntimeError("Indirect backend not available")
        plugin_params = {"action": action}
        plugin_params.update({k: v for k, v in params.items() if v is not None})
        plugin_url = f"plugin://{self.addon_id}/?{urllib.parse.urlencode(plugin_params)}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "Files.GetDirectory",
            "params": {"directory": plugin_url, "media": "video", "properties": [
                "title",
                "file",
                "plot",
                "art",
                "streamdetails",
                "resume"
            ]}
        }
        response = xbmc.executeJSONRPC(json.dumps(payload))
        data = json.loads(response)
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        result = data.get("result", {})
        if action == "play":
            # Addons.ExecuteAddon to retrieve playback info
            payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "Addons.ExecuteAddon",
                "params": {"addonid": self.addon_id, "params": plugin_params}
            }
            response = xbmc.executeJSONRPC(json.dumps(payload))
            playback_data = json.loads(response)
            if "error" in playback_data:
                raise RuntimeError(str(playback_data["error"]))
            return playback_data.get("result")
        return result

    # normalization ------------------------------------------------------
    def _normalize_rails(self, raw: Any) -> List[Rail]:
        rails: List[Rail] = []
        if isinstance(raw, dict):
            candidates = raw.get("rails") or raw.get("items") or raw.get("children")
        else:
            candidates = raw
        if isinstance(candidates, list):
            for entry in candidates:
                if not isinstance(entry, dict):
                    continue
                identifier = entry.get("id") or entry.get("slug") or entry.get("title") or entry.get("name")
                if not identifier:
                    continue
                title = entry.get("title") or entry.get("name") or identifier
                items = entry.get("items") or entry.get("contents") or entry.get("children") or []
                content_type = entry.get("content_type") or entry.get("type") or "videos"
                rails.append(Rail(str(identifier), title, items, content_type))
        return rails

    def _normalize_items(self, raw: Any) -> Tuple[List[Dict[str, Any]], bool]:
        items: List[Dict[str, Any]] = []
        has_more = False
        data = None
        if isinstance(raw, dict):
            data = raw.get("items") or raw.get("videos") or raw.get("entries") or raw.get("files")
            has_more = bool(raw.get("has_more") or raw.get("next_page"))
        elif isinstance(raw, list):
            data = raw
        if isinstance(data, list):
            for entry in data:
                normalized = self._normalize_item(entry)
                if normalized:
                    items.append(normalized)
        return items, has_more

    def _normalize_item(self, entry: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(entry, dict):
            return None
        asin = entry.get("asin") or entry.get("id") or entry.get("contentId") or entry.get("url")
        label = entry.get("title") or entry.get("label") or entry.get("name")
        if not asin or not label:
            return None
        art = entry.get("art") or {
            "thumb": entry.get("thumb"),
            "poster": entry.get("poster"),
            "fanart": entry.get("fanart")
        }
        info = entry.get("info") or {
            "title": label,
            "plot": entry.get("plot") or entry.get("description") or "",
            "year": entry.get("year"),
            "genre": entry.get("genre"),
            "duration": entry.get("duration")
        }
        item_type = entry.get("type") or entry.get("media_type") or "video"
        is_folder = bool(entry.get("is_folder"))
        return {
            "asin": str(asin),
            "title": label,
            "art": {k: v for k, v in art.items() if v},
            "info": info,
            "is_folder": is_folder,
            "type": item_type,
            "params": entry.get("params") or {}
        }

    def _normalize_playback(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        raise RuntimeError("Invalid playback payload")


_backend: Optional[PrimeBackend] = None


def get_backend() -> Optional[PrimeBackend]:
    global _backend
    if _backend is None:
        backend = PrimeBackend()
        if backend.is_ready:
            _backend = backend
        else:
            _backend = None
    return _backend
