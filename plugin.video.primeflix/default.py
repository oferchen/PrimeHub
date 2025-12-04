"""Kodi entrypoint delegating to the PrimeFlix router.

Kodi invokes this module directly; it forwards the plugin base URL and
parameters to :func:`resources.lib.router.dispatch`.
"""

import sys
import traceback
import xbmc
import xbmcgui

from resources.lib.router import dispatch


def main():
    try:
        handle = sys.argv[0]
        params = sys.argv[2] if len(sys.argv) > 2 else ""
        dispatch(handle, params)
    except Exception as e:
        # Log the full traceback for debugging
        xbmc.log(f"PrimeHub unhandled exception: {traceback.format_exc()}", xbmc.LOGERROR)
        
        # Show a generic error notification to the user
        xbmcgui.Dialog().notification(
            "PrimeHub Error",
            "An unexpected error occurred. Check the log for more details.",
            xbmcgui.NOTIFICATION_ERROR
        )


if __name__ == "__main__":
    main()
