# PrimeHub Native Backend API Documentation

This document specifies the internal API for the PrimeHub native backend, as inferred from the `Sandmann79/plugin.video.amazon-test` source code. All native implementations must conform to this specification.

## 1. Core Network Functions (`network.py`)

### 1.1 `getURL(url, useCookie, headers, postdata)`

- **Description:** Performs a raw HTTP GET or POST request.
- **Parameters:**
  - `url` (str): The full URL to request.
  - `useCookie` (bool): If `True`, includes the user's session cookies.
  - `headers` (dict): A dictionary of request headers.
  - `postdata` (dict): If provided, the request is a POST with this data.
- **Returns:** The raw response body as a string.

### 1.2 `GrabJSON(url, postData)`

- **Description:** Fetches a URL and extracts a JSON object, even if embedded in an HTML page.
- **Parameters:**
  - `url` (str): The URL to fetch.
  - `postData` (dict): Optional POST data.
- **Returns:** A dictionary representing the parsed JSON.

### 1.3 `getURLData(mode, asin, ...)`

- **Description:** Calls a specific Amazon "cdp" (Customer-facing Display Policies) API endpoint.
- **Parameters:**
  - `mode` (str): The API mode (e.g., `catalog/GetPlaybackResources`).
  - `asin` (str): The Amazon Standard Identification Number of the item.
  - Additional parameters for device type, firmware, etc.
- **Returns:** A tuple of `(success: bool, data: dict | str)`.

### 1.4 `MechanizeLogin(username, password)`

- **Description:** Simulates a browser login to handle multi-step authentication.
- **Parameters:**
  - `username` (str): The user's email.
  - `password` (str): The user's password.
- **Returns:** The `requests.Session` object with authentication cookies.

## 2. High-Level Backend Methods (`prime_api.py`)

The `PrimeVideo` singleton class provides these methods.

### 2.1 `BuildRoot()`

- **Description:** Fetches the main menu structure for the home screen.
- **Internal Logic:** Calls `GrabJSON` on the storefront URL (e.g., `/gp/video/storefront`).
- **Returns:** `True` on success. The parsed data is stored internally in `self._catalog`.

### 2.2 `Browse(path)`

- **Description:** Navigates a "virtual" path in the catalog (e.g., `root`, `root/movies`).
- **Internal Logic:**
  - Traverses the internal `self._catalog`.
  - If a node has a `lazyLoadURL`, it calls `_LazyLoad` to fetch and parse the content.
- **Returns:** A tuple of `(items: list[dict], next_page_cursor: str | None)`.

### 2.3 `Search(query)`

- **Description:** Performs a search.
- **Internal Logic:** Calls `Browse` with a special `search` path, which is then handled by `_LazyLoad`.
- **Returns:** A tuple of `(items: list[dict], next_page_cursor: str | None)`.

### 2.4 `GetStream(asin)`

- **Description:** Fetches the playback manifest and DRM license URL for an item.
- **Internal Logic:** Calls `getURLData` with `mode='catalog/GetPlaybackResources'`.
- **Returns:** A tuple of `(success: bool, stream_data: dict | str)`.

### 2.5 `_LazyLoad(obj, breadcrumb)`

- **Description:** The core parsing engine. Fetches data for a catalog node and parses the complex JSON response.
- **Internal Logic:** Calls `GrabJSON` and then uses detailed parsing logic to extract items, seasons, episodes, and metadata.

## 3. Data Structures (Inferred)

### 3.1 Item Structure

```json
{
  "asin": "B012345",
  "title": "The Grand Tour",
  "metadata": {
    "videometa": {
      "mediatype": "tvshow",
      "year": 2016,
      "plot": "Motoring show.",
      "season": 1,
      "episode": 1
    },
    "artmeta": {
      "thumb": "http://...",
      "poster": "http://...",
      "fanart": "http://..."
    }
  },
  "children": ["<season_asin_1>", "<season_asin_2>"]
}
```

### 3.2 Playback Stream Structure

```json
{
  "manifestUrl": "http://.../manifest.mpd",
  "licenseUrl": "http://.../license_server",
  "audio": [
    {"language": "en", "audioTrackId": "A1"}
  ]
}
```
