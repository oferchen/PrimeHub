# DEVELOPERS.md — Guide for Native Backend Implementation

This document provides a guide for developers to complete the native backend implementation for the PrimeHub add-on. The current architecture is designed to communicate directly with Amazon's Prime Video APIs, but the core HTTP requests and data parsing are stubbed out. Completing this requires manual investigation of Amazon's APIs.

## 1. Architecture Overview

The native backend (`resources/lib/backend/prime_api.py`) uses several design patterns:

- **Singleton:** The `get_backend()` function ensures only one instance of `PrimeAPI` exists.
- **Facade:** The `PrimeAPI` class provides a simple, clean interface to the backend for the UI.
- **Strategy:** The `_NativeAPIIntegration` class is the concrete strategy for all backend communication. This is where the core implementation work is needed.

## 2. Dependency: `requests` Library

The native backend uses the `requests` library for HTTP communication. Since Kodi's Python environment is isolated, this library must be **bundled (vendored)** with the add-on.

**To bundle `requests`:**
1. Create a `requirements.txt` file in the root of the project with the following content:
   ```
   requests
   ```
2. Install the dependency into a local `lib` or `vendor` directory within the add-on's `resources` folder:
   ```bash
   pip install -r requirements.txt --target=plugin.video.primeflix/resources/lib/vendor
   ```
3. Ensure this vendor directory is added to Python's path at the top of `prime_api.py`:
   ```python
   # In prime_api.py
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'vendor'))
   import requests
   ```

## 3. Investigating Amazon's Private APIs

The most critical task is to discover the API endpoints, request parameters, and response structures that Amazon's website uses.

**Tools:**
- A web browser (e.g., Chrome, Firefox).
- The browser's **Developer Tools** (usually opened with F12 or Ctrl+Shift+I).

**General Process:**
1. Open the Amazon Prime Video website in your browser.
2. Open the Developer Tools and switch to the **Network** tab.
3. Filter the network requests by **Fetch/XHR** to see only API calls.
4. Perform an action on the website (e.g., log in, click on a movie, browse a category).
5. Observe the new network requests that appear in the Developer Tools.
6. **Inspect the request:**
   - **URL:** This is the API endpoint.
   - **Headers:** Look for important headers like `Content-Type`, `Authorization`, `x-amz-access-token`, `Cookie`, etc.
   - **Payload/Body:** For POST requests (like login), inspect the form data or JSON body being sent.
7. **Inspect the response:**
   - **Preview/Response Tabs:** Look at the JSON data returned by the API. This is the data you will need to parse.

## 4. Implementing `_NativeAPIIntegration` Methods

### 4.1. Authentication (`login`)

This is the most complex part. You need to replicate the browser's login flow.
1.  **GET `https://www.amazon.com/ap/signin`:** First, you need to load the sign-in page to get hidden form inputs like `appActionToken`, `workflowStateHandle`, etc., and any CSRF tokens from the HTML.
2.  **POST `https://www.amazon.com/ap/signin`:** Send a POST request with the user's `email`, `password`, and all the hidden form data you extracted.
3.  **Handle Response:**
    - A successful login will usually result in a 302 redirect and set session cookies (e.g., `at-main`, `sess-at-main`). The `requests.Session` object will handle these cookies automatically.
    - A failed login might return a 200 with an error message in the HTML, or redirect back to the sign-in page.
    - Be prepared to handle Multi-Factor Authentication (MFA) and CAPTCHAs, which will require additional user input and API calls.
4.  **Update `login` method:** Replace the stubbed logic in `_NativeAPIIntegration.login` with your `requests` implementation.

### 4.2. Session Persistence (`_load_session`, `_save_session`)

- The current implementation saves/loads the `requests` cookie jar as a dictionary. This is a good starting point, but ensure that all necessary cookies are being persisted.
- The `_verify_session` method should be updated to make a lightweight, authenticated API call (e.g., to a "get user profile" endpoint) to confirm the loaded session is still valid.

### 4.3. Content Fetching (`get_home_rails`, `get_rail_items`, `search`)

- Use the network inspection technique described above to find the API endpoints for:
  - **Home Screen:** The API call that populates the main Prime Video page.
  - **Viewing a Category/Rail:** The API call made when you click "See all" on a rail.
  - **Search:** The API call made when you type in the search bar.
- These endpoints will likely be part of Amazon's `atv-ps.amazon.com` or similar subdomains.
- Update the corresponding methods in `_NativeAPIIntegration` to call these endpoints and parse the JSON responses, adapting them into the normalized data structure that `normalize_rail` and `normalize_item` expect.

### 4.4. Playback (`get_playable`)

- When you click to play a video on the website, inspect the network requests for calls to endpoints that return manifest URLs (ending in `.mpd` or `.m3u8`) and license URLs (for Widevine DRM).
- These are often fetched from an endpoint like `atv-ps.amazon.com/cdp/catalog/GetPlaybackResources`.
- Update `_NativeAPIIntegration.get_playable` to call this endpoint and extract the necessary data to populate the `Playable` object, which is then passed to Kodi's `inputstream.adaptive`.

Good luck with the implementation!
