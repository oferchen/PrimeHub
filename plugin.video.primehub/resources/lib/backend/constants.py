"""
Constants for the native Prime Video backend.
NOTE: These are placeholders and must be replaced with real, discovered
API endpoints and parameters.
"""

BASE_URL = "https://atv-ps.amazon.com"

# Example endpoints (these are speculative)
URLS = {
    "home": f"{BASE_URL}/cdp/catalog/GetPage?pageId=Home",
    "rail_items": f"{BASE_URL}/cdp/catalog/GetPage?pageId={{rail_id}}",
    "search": f"{BASE_URL}/cdp/catalog/Search?query={{query}}",
    "get_playback": f"{BASE_URL}/cdp/catalog/GetPlaybackResources",
}

# Example device and application metadata required for API calls
# These values often need to be specific to a real browser or app
# to get valid responses.
DEVICE_INFO = {
    "deviceType": "A1F83G8C2ARO7P", # Example: Chrome on macOS
    "firmware": "1",
    "deviceDrmOverride": "CENC",
    # ... and many other parameters
}
