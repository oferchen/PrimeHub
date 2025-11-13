import sys
import urllib.parse

try:
    import xbmcplugin
except ImportError:  # pragma: no cover - development fallback
    xbmcplugin = None

from .ui import diagnostics, home, listing, playback


def _get_handle(base_handle):
    try:
        return int(sys.argv[1])
    except (IndexError, ValueError):
        try:
            return int(base_handle)
        except (TypeError, ValueError):
            return 0


def _parse_params(paramstring):
    if not paramstring:
        return {}
    query = paramstring[1:] if paramstring.startswith("?") else paramstring
    if not query:
        return {}
    return dict(urllib.parse.parse_qsl(query))


def dispatch(base_handle, paramstring):
    handle = _get_handle(base_handle)
    params = _parse_params(paramstring)
    action = params.get("action")

    if not action:
        home.show_home(handle)
    elif action == "list":
        listing.show_list(handle, params.get("rail"), int(params.get("page", "1")))
    elif action == "play":
        playback.play(handle, params.get("asin"))
    elif action == "diagnostics":
        diagnostics.show_results(handle)
    elif action == "search":
        listing.start_search(handle, params)
    else:
        home.show_home(handle)

    if xbmcplugin:
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
