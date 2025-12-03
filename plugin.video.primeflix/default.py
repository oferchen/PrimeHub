"""Kodi entrypoint delegating to the PrimeFlix router.

Kodi invokes this module directly; it forwards the plugin base URL and
parameters to :func:`resources.lib.router.dispatch`.
"""

import sys

from resources.lib.router import dispatch


def main():
    handle = sys.argv[0]
    params = sys.argv[2] if len(sys.argv) > 2 else ""
    dispatch(handle, params)


if __name__ == "__main__":
    main()
