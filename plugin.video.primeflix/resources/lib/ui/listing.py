"""Rail listing and search UI handlers."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - Kodi runtime
    import xbmcgui
    import xbmcplugin
    import xbmcaddon
except ImportError:  # pragma: no cover - local dev fallback
    from ...tests.kodi_mocks import MockXBMCAddon as xbmcaddon
    from ...tests.kodi_mocks import MockXBMCGUI as xbmcgui
    from ...tests.kodi_mocks import MockXBMCPlugin as xbmcplugin

from ..backend.prime_api import BackendError, BackendUnavailable, get_backend
from ..cache import get_cache
from ..perf import log_duration, timed
from ..preflight import PreflightError, ensure_ready_or_raise

DEFAULT_CACHE_TTL = 300


def show_list(context, rail_id: str, cursor: Optional[str] = None) -> None:
    ensure_ready_or_raise()
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
        backend = get_backend()
        try:
            items, next_cursor = backend.get_rail_items(rail_id, cursor)
        except (BackendUnavailable, BackendError) as exc:
            # Display a more user-friendly error notification for content fetching failures
            xbmcgui.Dialog().notification(
                addon.getLocalizedString(32005), # "Login Failed" (re-purposed for error)
                addon.getLocalizedString(41000), # New string for "Content Unavailable"
                xbmcgui.NOTIFICATION_ERROR
            )
            raise PreflightError(str(exc)) # Re-raise for router to handle
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

    addon = xbmcaddon.Addon()

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

        # Add Context Menu Items
        context_menu_items = []
        if item.get("asin"): # Only add if item has an ASIN
            add_to_watchlist_url = context.build_url(action="add_to_watchlist", asin=item["asin"])
            context_menu_items.append((addon.getLocalizedString(32008), f"RunPlugin({add_to_watchlist_url})")) # "Add to Watchlist"
            mark_as_watched_url = context.build_url(action="mark_as_watched", asin=item["asin"], status="true")
            context_menu_items.append((addon.getLocalizedString(32009), f"RunPlugin({mark_as_watched_url})")) # "Mark as Watched"

        li.addContextMenuItems(context_menu_items)

        list_items.append((play_url, li, False))

    if next_cursor:
        more_item = xbmcgui.ListItem(label=_get_more_label())
        more_url = context.build_url(
            action="list", rail=rail_id, cursor=str(next_cursor)
        )
        list_items.append((more_url, more_item, True))

    xbmcplugin.addDirectoryItems(context.handle, list_items)


def handle_add_to_watchlist(context, asin: str) -> None:
    """Handles adding an item to the watchlist."""
    addon = xbmcaddon.Addon()
    dialog = xbmcgui.Dialog()
    backend = get_backend()

    try:
        if backend.add_to_watchlist(asin):
            dialog.notification(
                addon.getLocalizedString(32008), # "Add to Watchlist"
                addon.getLocalizedString(32003), # "Login Successful" (re-purposing for success)
                xbmcgui.NOTIFICATION_INFO
            )
        else:
            dialog.notification(
                addon.getLocalizedString(32008),
                addon.getLocalizedString(32005), # "Login Failed" (re-purposing for failure)
                xbmcgui.NOTIFICATION_ERROR
            )
    except AuthenticationError:
        dialog.notification(
            addon.getLocalizedString(32008),
            addon.getLocalizedString(21090), # "Please log in..."
            xbmcgui.NOTIFICATION_WARNING
        )
    except BackendError as e:
        dialog.notification(
            addon.getLocalizedString(32008),
            str(e),
            xbmcgui.NOTIFICATION_ERROR
        )


def handle_mark_as_watched(context, asin: str, status: bool) -> None:
    """Handles marking an item as watched or unwatched."""
    addon = xbmcaddon.Addon()
    dialog = xbmcgui.Dialog()
    backend = get_backend()

    try:
        if backend.mark_as_watched(asin, status):
            dialog.notification(
                addon.getLocalizedString(32009), # "Mark as Watched"
                addon.getLocalizedString(32003), # "Login Successful" (re-purposing for success)
                xbmcgui.NOTIFICATION_INFO
            )
        else:
            dialog.notification(
                addon.getLocalizedString(32009),
                addon.getLocalizedString(32005), # "Login Failed" (re-purposing for failure)
                xbmcgui.NOTIFICATION_ERROR
            )
    except AuthenticationError:
        dialog.notification(
            addon.getLocalizedString(32009),
            addon.getLocalizedString(21090), # "Please log in..."
            xbmcgui.NOTIFICATION_WARNING
        )
    except BackendError as e:
        dialog.notification(
            addon.getLocalizedString(32009),
            str(e),
            xbmcgui.NOTIFICATION_ERROR
        )


def show_search(context, query: Optional[str], cursor: Optional[str]) -> None:
    ensure_ready_or_raise()
    if not query:
        query = _prompt_search()
    if not query:
        return
    backend = get_backend()
    try:
        items, next_cursor = backend.search(query, cursor)
    except (BackendUnavailable, BackendError) as exc:
        # Display a more user-friendly error notification for content fetching failures
        addon = xbmcaddon.Addon() # Need addon for localized strings
        xbmcgui.Dialog().notification(
            addon.getLocalizedString(32005), # "Login Failed" (re-purposed for error)
            addon.getLocalizedString(41000), # New string for "Content Unavailable"
            xbmcgui.NOTIFICATION_ERROR
        )
        raise PreflightError(str(exc)) # Re-raise for router to handle
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
