"""Rail listing and search UI handlers."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - Kodi runtime
    import xbmcgui
    import xbmcplugin
    import xbmcaddon
except ImportError:  # pragma: no cover - local dev fallback

    class _Dialog:
        @staticmethod
        def input(heading: str):
            print(f"SEARCH: {heading}")
            return ""

    class _ListItem:
        def __init__(self, label=""):
            self.label = label

        def setArt(self, art: Dict[str, str]):
            self.art = art

        def setInfo(self, type_: str, info: Dict[str, Any]):
            self.info = (type_, info)

    class _Plugin:
        @staticmethod
        def addDirectoryItems(handle, items):
            print(f"ADD {len(items)} items")

        @staticmethod
        def setContent(handle, content):
            print(f"SET CONTENT {content}")

    xbmcgui = type("xbmcgui", (), {"ListItem": _ListItem, "Dialog": _Dialog})  # type: ignore
    xbmcplugin = _Plugin()  # type: ignore
    xbmcaddon = type(
        "addon",
        (),
        {
            "Addon": lambda *a, **k: type(
                "AddonStub",
                (),
                {
                    "getSettingInt": lambda self, k: 300,
                    "getSettingBool": lambda self, k: True,
                    "getSetting": lambda self, k: 300,
                    "getLocalizedString": lambda self, k: "",
                },
            )(),
        },
    )  # type: ignore

from ..backend import BackendError, BackendUnavailable, get_backend
from ..cache import get_cache
from ..perf import log_duration, timed
from ..preflight import PreflightError, ensure_ready_or_raise

DEFAULT_CACHE_TTL = 300


def show_list(context, rail_id: str, cursor: Optional[str] = None) -> None:
    backend_id = ensure_ready_or_raise()
    addon = xbmcaddon.Addon()
    cache = get_cache()
    cache_ttl = _get_cache_ttl(addon)
    use_cache = _get_use_cache(addon)
    start = time.perf_counter()

    cache_key = f"rail:{rail_id}:{cursor or 'root'}"
    cached: Optional[Dict[str, Any]] = (
        cache.get(cache_key, ttl_seconds=cache_ttl) if use_cache else None
    )
    items: List[Dict[str, Any]]
    next_cursor: Optional[str]
    warm = cached is not None

    if cached:
        items = cached.get("items", [])
        next_cursor = cached.get("next")
    else:
        backend = get_backend(backend_id)
        try:
            items, next_cursor = backend.get_rail_items(rail_id, cursor)
        except (BackendUnavailable, BackendError) as exc:
            raise PreflightError(str(exc))
        if use_cache:
            cache.set(cache_key, {"items": items, "next": next_cursor}, cache_ttl)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    log_duration(
        "list",
        elapsed_ms,
        warm=warm,
        warm_threshold_ms=150.0,
        cold_threshold_ms=500.0,
        details=rail_id,
    )

    _render_items(context, items, next_cursor, rail_id)


@timed("list_items")
def _render_items(
    context, items: List[Dict[str, Any]], next_cursor: Optional[str], rail_id: str
) -> None:
    content_type = _infer_content(items)
    xbmcplugin.setContent(context.handle, content_type)

    list_items = []
    for item in items:
        label = item.get("title", "")
        li = xbmcgui.ListItem(label=label)
        li.setArt({k: v for k, v in item.get("art", {}).items() if v})
        li.setInfo(
            "video",
            {
                "title": label,
                "plot": item.get("plot", ""),
                "year": item.get("year") or 0,
                "duration": item.get("duration") or 0,
                "mediatype": (
                    "movie"
                    if item.get("is_movie")
                    else "tvshow" if item.get("is_show") else "video"
                ),
            },
        )
        play_url = context.build_url(action="play", asin=item.get("asin", ""))
        list_items.append((play_url, li, False))

    if next_cursor:
        more_item = xbmcgui.ListItem(label=_get_more_label())
        more_url = context.build_url(
            action="list", rail=rail_id, cursor=str(next_cursor)
        )
        list_items.append((more_url, more_item, True))

    xbmcplugin.addDirectoryItems(context.handle, list_items)


def show_search(context, query: Optional[str], cursor: Optional[str]) -> None:
    backend_id = ensure_ready_or_raise()
    if not query:
        query = _prompt_search()
    if not query:
        return
    backend = get_backend(backend_id)
    try:
        items, next_cursor = backend.search(query, cursor)
    except (BackendUnavailable, BackendError) as exc:
        raise PreflightError(str(exc))
    _render_items(context, items, next_cursor, "search")


def _prompt_search() -> Optional[str]:
    try:
        addon = xbmcaddon.Addon()
        keyboard = xbmcgui.Dialog()
        # type: ignore[attr-defined]
        return keyboard.input(
            addon.getLocalizedString(30030)
        )  # pragma: no cover - Kodi runtime
    except Exception:
        return None


def _infer_content(items: List[Dict[str, Any]]) -> str:
    for item in items:
        if item.get("is_movie"):
            return "movies"
        if item.get("is_show"):
            return "tvshows"
    return "videos"


def _get_cache_ttl(addon) -> int:
    try:
        return int(addon.getSettingInt("cache_ttl"))
    except Exception:
        return DEFAULT_CACHE_TTL


def _get_more_label() -> str:
    try:
        addon = xbmcaddon.Addon()
        label = addon.getLocalizedString(30010)
        return label or "More…"
    except Exception:
        return "More…"


def _get_use_cache(addon) -> bool:
    try:
        return addon.getSettingBool("use_cache")
    except Exception:
        try:
            return str(addon.getSetting("use_cache")).lower() == "true"
        except Exception:
            return True
