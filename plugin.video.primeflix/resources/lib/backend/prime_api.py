"""Prime backend facade with automatic strategy selection for callers.

This module is invoked by UI layers (home, listing, playback, diagnostics)
through :func:`get_backend`, providing normalized data from the installed
Prime Video backend via direct imports or JSON-RPC fallback.
"""
from __future__ import annotations
import importlib
import inspect
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # pragma: no cover - Kodi runtime
    import xbmc
    import xbmcaddon
except ImportError:  # pragma: no cover - local dev fallback
    class _XBMCStub:
        LOGDEBUG = 0
        LOGINFO = 1
        LOGWARNING = 2
        LOGERROR = 3

        @staticmethod
        def log(message: str, level: int = 0) -> None:
            print(f"[xbmc:{level}] {message}")

        @staticmethod
        def executeJSONRPC(payload: str) -> str:
            return json.dumps({"result": {}})

    class _AddonStub:
        def __init__(self, addon_id: Optional[str] = None):
            self._id = addon_id or "plugin.video.primeflix"

        def getAddonInfo(self, key: str) -> str:
            mapping = {
                "id": self._id,
                "name": "PrimeFlix",
                "path": os.getcwd(),
            }
            return mapping.get(key, "")

        def getSetting(self, key: str) -> str:  # type: ignore[override]
            defaults = {
                "region": "0",
                "cache_ttl": "300",
                "use_cache": "true",
            }
            return defaults.get(key, "")

        def getSettingString(self, key: str) -> str:  # Kodi 21+
            return self.getSetting(key)

        def getSettingBool(self, key: str) -> bool:
            return self.getSetting(key).lower() == "true"

        def getSettingInt(self, key: str) -> int:
            try:
                return int(self.getSetting(key))
            except ValueError:
                return 0

    xbmc = _XBMCStub()  # type: ignore
    xbmcaddon = type("addon", (), {"Addon": _AddonStub})  # type: ignore

from ..cache import get_cache
from ..perf import log_debug, log_info, timed
from ..preflight import ensure_ready_or_raise


class BackendError(RuntimeError):
    """Raised when backend data could not be retrieved."""


@dataclass(frozen=True)
class RailData:
    """Normalized representation for rail responses."""

    items: List[Dict[str, Any]]
    cursor: Optional[str]


class _BaseStrategy:
    name = "base"

    def get_region(self) -> Optional[str]:  # pragma: no cover - interface
        return None

    def is_drm_ready(self) -> Optional[bool]:  # pragma: no cover - interface
        return None

    def get_rail(self, rail_id: str, cursor: Optional[str], limit: int) -> RailData:
        raise NotImplementedError

    def search(self, query: str, cursor: Optional[str], limit: int) -> RailData:
        raise NotImplementedError

    def get_playable(self, asin: str) -> Dict[str, Any]:
        raise NotImplementedError


class _DirectBackendStrategy(_BaseStrategy):
    """Strategy using direct Python imports from the backend add-on."""

    name = "direct"
    MODULE_CANDIDATES = (
        "resources.lib.api",
        "resources.lib.primevideo",
        "resources.lib.prime_video",
        "resources.lib.backend.api",
    )
    CLASS_CANDIDATES = (
        "PrimeVideo",
        "PrimeVideoApi",
        "PrimeVideoAPI",
        "API",
    )
    HOME_CALLS = ("get_home", "get_home_menu", "get_home_sections")
    RAIL_CALLS = ("get_rail", "get_rail_items", "get_menu_items", "get_items", "get_list")
    SEARCH_CALLS = ("search", "search_catalog", "get_search")
    PLAY_CALLS = ("get_playable", "get_playback", "play", "resolve")
    REGION_CALLS = ("get_region", "region", "get_marketplace")
    DRM_CALLS = ("is_drm_ready", "drm_ready", "check_drm", "has_drm")

    def __init__(self, backend_id: str) -> None:
        self._backend_id = backend_id
        self._api: Any = None
        self._module: Optional[ModuleType] = None
        self._home_callable: Optional[Any] = None
        self._rail_callable: Optional[Any] = None
        self._search_callable: Optional[Any] = None
        self._play_callable: Optional[Any] = None
        self._region_callable: Optional[Any] = None
        self._drm_callable: Optional[Any] = None
        self._prepare()

    def _prepare(self) -> None:
        addon = xbmcaddon.Addon(self._backend_id)
        addon_path = addon.getAddonInfo("path")
        if addon_path and addon_path not in sys.path:
            sys.path.append(addon_path)
        for module_name in self.MODULE_CANDIDATES:
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue
            api = self._extract_api(module)
            if api is not None:
                self._module = module
                self._api = api
                break
        if self._api is None:
            raise BackendError("Direct strategy unavailable")

    def _extract_api(self, module: ModuleType) -> Optional[Any]:
        callable_pairs = (
            ("home", self.HOME_CALLS),
            ("rail", self.RAIL_CALLS),
            ("search", self.SEARCH_CALLS),
            ("play", self.PLAY_CALLS),
        )
        # Try module-level functions first
        resolved = {}
        for key, candidates in callable_pairs:
            func = self._find_callable(module, candidates)
            if func is None:
                break
            resolved[key] = func
        else:
            self._home_callable = resolved["home"]
            self._rail_callable = resolved["rail"]
            self._search_callable = resolved["search"]
            self._play_callable = resolved["play"]
            self._region_callable = self._find_callable(module, self.REGION_CALLS)
            self._drm_callable = self._find_callable(module, self.DRM_CALLS)
            return module

        # Fallback to class-based API discovery
        for class_name in self.CLASS_CANDIDATES:
            candidate = getattr(module, class_name, None)
            if candidate is None or not inspect.isclass(candidate):
                continue
            try:
                instance = candidate()  # type: ignore[call-arg]
            except Exception:
                continue
            if self._has_methods(instance):
                self._home_callable = getattr(instance, self._resolve_name(instance, self.HOME_CALLS))
                self._rail_callable = getattr(instance, self._resolve_name(instance, self.RAIL_CALLS))
                self._search_callable = getattr(instance, self._resolve_name(instance, self.SEARCH_CALLS))
                self._play_callable = getattr(instance, self._resolve_name(instance, self.PLAY_CALLS))
                region_method = self._resolve_name(instance, self.REGION_CALLS)
                if region_method:
                    self._region_callable = getattr(instance, region_method)
                drm_method = self._resolve_name(instance, self.DRM_CALLS)
                if drm_method:
                    self._drm_callable = getattr(instance, drm_method)
                return instance
        return None

    @staticmethod
    def _find_callable(module: ModuleType, names: Iterable[str]) -> Optional[Any]:
        for name in names:
            func = getattr(module, name, None)
            if callable(func):
                return func
        return None

    @staticmethod
    def _has_methods(instance: Any) -> bool:
        required_groups = (
            _DirectBackendStrategy.HOME_CALLS,
            _DirectBackendStrategy.RAIL_CALLS,
            _DirectBackendStrategy.SEARCH_CALLS,
            _DirectBackendStrategy.PLAY_CALLS,
        )
        for group in required_groups:
            if _DirectBackendStrategy._resolve_name(instance, group) is None:
                return False
        return True

    @staticmethod
    def _resolve_name(instance: Any, names: Iterable[str]) -> Optional[str]:
        for name in names:
            func = getattr(instance, name, None)
            if callable(func):
                return name
        return None

    @staticmethod
    def _invoke(func: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except TypeError:
            if kwargs:
                return func(*args)
            raise

    def _ensure_prepared(self) -> None:
        if not all((self._home_callable, self._rail_callable, self._search_callable, self._play_callable)):
            raise BackendError("Incomplete direct backend binding")

    def get_region(self) -> Optional[str]:
        if self._region_callable is None:
            return None
        try:
            value = self._invoke(self._region_callable)
        except Exception:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            region = value.get("region") or value.get("marketplace")
            if isinstance(region, str):
                return region
        return None

    def is_drm_ready(self) -> Optional[bool]:
        if self._drm_callable is None:
            return None
        try:
            value = self._invoke(self._drm_callable)
        except Exception:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "yes", "ready"):
                return True
            if lowered in ("false", "no", "not ready", "unavailable"):
                return False
        if isinstance(value, dict):
            ready = value.get("ready") or value.get("drm_ready")
            if isinstance(ready, bool):
                return ready
        return None

    def get_rail(self, rail_id: str, cursor: Optional[str], limit: int) -> RailData:
        self._ensure_prepared()
        try:
            if cursor:
                result = self._invoke(self._rail_callable, rail_id, cursor=cursor, limit=limit)
            else:
                result = self._invoke(self._rail_callable, rail_id, limit=limit)
        except TypeError:
            if cursor:
                result = self._invoke(self._rail_callable, rail_id, cursor)
            else:
                result = self._invoke(self._rail_callable, rail_id)
        return self._normalize(result)

    def search(self, query: str, cursor: Optional[str], limit: int) -> RailData:
        self._ensure_prepared()
        kwargs: Dict[str, Any] = {"query": query, "limit": limit}
        if cursor:
            kwargs["cursor"] = cursor
        try:
            result = self._invoke(self._search_callable, **kwargs)
        except TypeError:
            args = (query,)
            if cursor:
                args += (cursor,)
            result = self._invoke(self._search_callable, *args)
        return self._normalize(result)

    def get_playable(self, asin: str) -> Dict[str, Any]:
        self._ensure_prepared()
        result = self._invoke(self._play_callable, asin)
        if not isinstance(result, dict):
            raise BackendError("Backend returned unexpected playback payload")
        return result

    @staticmethod
    def _normalize(payload: Any) -> RailData:
        if isinstance(payload, RailData):
            return payload
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("videos") or payload.get("data") or []
            cursor = payload.get("cursor") or payload.get("next")
            normalized = [_normalize_video(item) for item in items]
            return RailData([item for item in normalized if item], _safe_str(cursor))
        if isinstance(payload, (list, tuple)):
            normalized = [_normalize_video(item) for item in payload]
            return RailData([item for item in normalized if item], None)
        raise BackendError("Backend returned unsupported rail payload")


class _IndirectBackendStrategy(_BaseStrategy):
    """Strategy invoking the backend add-on via JSON-RPC."""

    name = "indirect"

    def __init__(self, backend_id: str) -> None:
        self._backend_id = backend_id
        xbmcaddon.Addon(backend_id)  # ensure addon exists

    def _execute(self, action: str, **params: Any) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "method": "Addons.ExecuteAddon",
            "params": {
                "addonid": self._backend_id,
                "params": {"action": action, **params},
            },
            "id": int(time.time() * 1000) & 0xFFFF,
        }
        response = xbmc.executeJSONRPC(json.dumps(payload))
        try:
            data = json.loads(response)
        except json.JSONDecodeError as exc:
            raise BackendError("Invalid JSON from backend") from exc
        result = data.get("result") or {}
        if isinstance(result, dict):
            raw = result.get("value") or result.get("data") or result.get("json")
            if isinstance(raw, str):
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    raise BackendError("Backend returned malformed data")
            if isinstance(result, dict):
                return result  # already a dict
        raise BackendError("Backend did not provide usable data")

    def get_region(self) -> Optional[str]:
        try:
            data = self._execute("get_region")
        except BackendError:
            return None
        region = data.get("region") or data.get("marketplace")
        if isinstance(region, str):
            return region
        return None

    def is_drm_ready(self) -> Optional[bool]:
        try:
            data = self._execute("is_drm_ready")
        except BackendError:
            return None
        if isinstance(data, bool):
            return data
        if isinstance(data, dict):
            ready = data.get("ready") or data.get("drm_ready")
            if isinstance(ready, bool):
                return ready
        if isinstance(data, str):
            lowered = data.strip().lower()
            if lowered in ("true", "yes", "ready"):
                return True
            if lowered in ("false", "no", "not ready", "unavailable"):
                return False
        return None

    def get_rail(self, rail_id: str, cursor: Optional[str], limit: int) -> RailData:
        params: Dict[str, Any] = {"rail": rail_id, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        data = self._execute("get_rail", **params)
        items = data.get("items") or data.get("videos") or []
        cursor_value = data.get("cursor") or data.get("next")
        normalized = [_normalize_video(item) for item in items]
        return RailData([item for item in normalized if item], _safe_str(cursor_value))

    def search(self, query: str, cursor: Optional[str], limit: int) -> RailData:
        params: Dict[str, Any] = {"query": query, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        data = self._execute("search", **params)
        items = data.get("items") or data.get("videos") or []
        cursor_value = data.get("cursor") or data.get("next")
        normalized = [_normalize_video(item) for item in items]
        return RailData([item for item in normalized if item], _safe_str(cursor_value))

    def get_playable(self, asin: str) -> Dict[str, Any]:
        data = self._execute("play", asin=asin)
        if not isinstance(data, dict):
            raise BackendError("Backend returned invalid playback data")
        playback = data.get("playback") or data
        if not isinstance(playback, dict):
            raise BackendError("Playback payload missing")
        return playback


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_video(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    asin = item.get("asin") or item.get("id") or item.get("contentId") or item.get("content_id")
    title = item.get("title") or item.get("name")
    if not asin or not title:
        return None
    info = item.get("info") or {}
    if not isinstance(info, dict):
        info = {}
    art = item.get("art") or {}
    if not isinstance(art, dict):
        art = {}
    plot = item.get("plot") or info.get("plot") or item.get("synopsis")
    mediatype = info.get("mediatype") or item.get("mediatype") or item.get("type")
    if isinstance(mediatype, str):
        mediatype = mediatype.lower()
    duration = info.get("duration") or info.get("runtime") or item.get("runtime")
    try:
        duration_int = int(duration) if duration is not None else None
    except (ValueError, TypeError):
        duration_int = None
    year = info.get("year") or item.get("year")
    try:
        year_int = int(year) if year is not None else None
    except (ValueError, TypeError):
        year_int = None
    genres = info.get("genre") or item.get("genre") or []
    if isinstance(genres, str):
        genres = [g.strip() for g in genres.split("/") if g.strip()]
    elif not isinstance(genres, list):
        genres = []
    normalized = {
        "asin": asin,
        "title": title,
        "plot": plot or "",
        "mediatype": mediatype or "video",
        "duration": duration_int,
        "year": year_int,
        "genres": genres,
        "art": {
            "thumb": art.get("thumb") or art.get("poster") or art.get("fanart"),
            "poster": art.get("poster") or art.get("thumb"),
            "fanart": art.get("fanart") or art.get("landscape"),
        },
        "info": {
            "plot": plot or "",
            "title": title,
            "duration": duration_int or 0,
            "year": year_int or 0,
            "genre": genres,
            "mediatype": mediatype or "video",
        },
        "is_playable": bool(item.get("is_playable", item.get("playable", True))),
        "is_folder": bool(item.get("is_folder", False)),
    }
    if "season" in info:
        normalized["season"] = info.get("season")
    if "episode" in info:
        normalized["episode"] = info.get("episode")
    return normalized


RAIL_COLD_THRESHOLD_MS = 500.0


class PrimeAPI:
    """Facade exposing backend data retrieval with caching."""

    REGION_OPTIONS = ("us", "uk", "de", "jp")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._backend_id = ensure_ready_or_raise()
        self._strategy: _BaseStrategy = self._select_strategy()
        self._cache = get_cache()

    def _select_strategy(self) -> _BaseStrategy:
        errors: List[str] = []
        for strategy_cls in (_DirectBackendStrategy, _IndirectBackendStrategy):
            try:
                strategy = strategy_cls(self._backend_id)
                log_info(f"Using {strategy.name} backend strategy with {self._backend_id}")
                return strategy
            except Exception as exc:
                errors.append(f"{strategy_cls.__name__}: {exc}")
                log_debug(f"Strategy {strategy_cls.__name__} failed: {exc}")
        raise BackendError("No backend strategy available: " + "; ".join(errors))

    @property
    def backend_id(self) -> str:
        return self._backend_id

    @property
    def strategy_name(self) -> str:
        return self._strategy.name

    def get_region(self) -> str:
        addon = xbmcaddon.Addon()
        preferred_index = self._get_setting_int(addon, "region", 0)
        preferred_index = max(0, min(preferred_index, len(self.REGION_OPTIONS) - 1))
        preferred = self.REGION_OPTIONS[preferred_index]
        backend_region = self._strategy.get_region()
        if backend_region:
            backend_region = backend_region.lower()
            if backend_region != preferred:
                log_info(f"Preferred region={preferred.upper()}, backend region={backend_region.upper()} — using backend")
            return backend_region
        return preferred

    @staticmethod
    def _get_setting_int(addon: Any, setting_id: str, default: int) -> int:
        try:
            return addon.getSettingInt(setting_id)
        except AttributeError:
            try:
                return int(addon.getSetting(setting_id))
            except Exception:
                return default

    @staticmethod
    def _get_setting_bool(addon: Any, setting_id: str, default: bool) -> bool:
        try:
            return addon.getSettingBool(setting_id)
        except AttributeError:
            value = addon.getSetting(setting_id)
            if isinstance(value, str):
                return value.lower() == "true"
            return default

    @timed("PrimeAPI.get_rail", warn_threshold_ms=RAIL_COLD_THRESHOLD_MS)
    def get_rail(self, rail_id: str, cursor: Optional[str], limit: int, ttl: int, use_cache: bool, force_refresh: bool = False) -> Tuple[RailData, bool]:
        cache_key = f"rail::{rail_id}::{cursor or 'root'}"
        if not force_refresh and use_cache:
            cached = self._cache.get(cache_key, ttl_seconds=ttl)
            if cached:
                if isinstance(cached, dict) and "items" in cached:
                    return RailData(cached["items"], cached.get("cursor")), True
                if isinstance(cached, list):
                    return RailData(cached, None), True
        data = self._strategy.get_rail(rail_id, cursor, limit)
        if use_cache:
            self._cache.set(cache_key, {"items": data.items, "cursor": data.cursor}, ttl)
        return data, False

    @timed("PrimeAPI.search", warn_threshold_ms=RAIL_COLD_THRESHOLD_MS)
    def search(self, query: str, cursor: Optional[str], limit: int, ttl: int, use_cache: bool) -> Tuple[RailData, bool]:
        cache_key = f"search::{query.lower()}::{cursor or 'root'}"
        if use_cache:
            cached = self._cache.get(cache_key, ttl_seconds=ttl)
            if cached:
                if isinstance(cached, dict) and "items" in cached:
                    return RailData(cached["items"], cached.get("cursor")), True
                if isinstance(cached, list):
                    return RailData(cached, None), True
        data = self._strategy.search(query, cursor, limit)
        if use_cache:
            self._cache.set(cache_key, {"items": data.items, "cursor": data.cursor}, ttl)
        return data, False

    def get_playable(self, asin: str) -> Dict[str, Any]:
        return self._strategy.get_playable(asin)

    def is_drm_ready(self) -> Optional[bool]:
        return self._strategy.is_drm_ready()


_backend_instance: Optional[PrimeAPI] = None
_backend_lock = threading.Lock()


def get_backend() -> PrimeAPI:
    global _backend_instance
    if _backend_instance is None:
        with _backend_lock:
            if _backend_instance is None:
                _backend_instance = PrimeAPI()
    return _backend_instance
