# AGENTS.md — Kodi “Prime Video, Netflix-Style” Add-on

This document defines the agents, their responsibilities, and hand-offs for implementing the **Prime Video, Netflix-style** Kodi add-on described in the Mission Brief.

All agents must strictly follow:

- The **Order of Precedence** in the Mission Brief.
- The rule: **reuse an existing Prime Video backend** (no DRM/login/stream reimplementation).
- The requirement that **all routed code paths are complete and functional** (no stubs).

---

## 1. Agent: Lead Architect

**Alias:** `architect-agent`  
**Goal:** Turn the Mission Brief into a coherent file layout and integration plan, then keep all agents aligned with it.

### Responsibilities

- Define/confirm the final **add-on structure**:

  - `addon.xml`
  - `default.py`
  - `resources/settings.xml`
  - `resources/lib/router.py`
  - `resources/lib/preflight.py`
  - `resources/lib/cache.py`
  - `resources/lib/perf.py`
  - `resources/lib/backend/prime_api.py`
  - `resources/lib/ui/home.py`
  - `resources/lib/ui/listing.py`
  - `resources/lib/ui/playback.py`
  - `resources/lib/ui/diagnostics.py`
  - `resources/language/resource.language.en_gb/strings.po`

- Ensure architecture respects:

  1. Kodi 21+ constraints.
  2. Reuse of the existing Prime backend (no DRM/login rework).
  3. Separation of concerns:
     - Routing vs. UI vs. backend vs. infra (cache/perf/preflight).

- Define **API contracts** between modules:
  - What `prime_api` returns (data model for rails, items, and playable data).
  - What `home/listing/playback/diagnostics` expect.
  - What `cache` and `perf` functions look like.

- Enforce the **Order of Precedence** when conflicts appear.

### Input

- Full Mission Brief text.
- This AGENTS.md.

### Output

- Final, authoritative **module API design** and function signatures.
- A short integration note at the top of each module (docstring/comment) explaining its role and callers.

## 2. Agent: Backend Integration

**Alias:** `backend-agent`  
**Goal:** Implement `backend/prime_api.py` as a **native backend** for Prime Video, directly communicating with Amazon's APIs, **without depending on an existing Prime Video add-on**. This module demonstrates the use of several design patterns: Singleton, Facade, Strategy, and Adapter.

### Responsibilities

- Implement `prime_api.py` with:

  - **Native API Strategy (`_NativeAPIIntegration`):**
    - Handle **Amazon Authentication**: Implement login/logout, manage user sessions (cookies, tokens), and ensure session persistence (saving/loading data to/from disk).
    - Make **Direct API Calls**: Interact with Amazon's Prime Video APIs to fetch content (home rails, rail items, search results, playable media information). *Note: This requires detailed investigation of Amazon's undocumented API endpoints.*
    - **Parse API Responses**: Process JSON responses from Amazon's APIs.
    - **Normalize Data**: Convert raw API data into internal models:
      - Rails: `{"id": str, "title": str, "type": "movies"/"tv"/"mixed"}`
      - Items: `{"asin": str, "title": str, "plot": str, "year": int|None, "duration": int|None, "art": {...}, "is_movie": bool, "is_show": bool}`
      - Playable: `{"url": str, "manifest_type": str, "license_key": str|None, "headers": {...}, "metadata": {...}}`
    - Expose region/DRM readiness info (`get_region_info()`, `is_drm_ready()`) via direct API calls.
    - **Dependency Note:** This implementation requires the `requests` Python library, which must be bundled with the add-on.

  - **Facade (`PrimeAPI`):** Provide a simplified, unified interface to the underlying native API strategy.
  - **Singleton (`get_backend()`):** Ensure only a single instance of `PrimeAPI` is created and managed.
  - **Adapter (`normalize_rail`, `normalize_item`):** Convert backend data formats to the UI's expected format.

- Provide a small set of **backend-facing exceptions** (e.g. `BackendError`, `AuthenticationError`) that callers can handle.

### Input

- Architect-defined API contracts (now updated for native integration).
- Knowledge of Amazon Prime Video API structure (requires external investigation).

### Output

- `resources/lib/backend/prime_api.py` containing:
  - Complete native backend implementation (authentication, content fetching, session management).
  - Normalized data types for rails/items/playable.
  - Logging of operations and errors.
  - Explicit use of Singleton, Facade, Strategy, and Adapter patterns.

## 3. Agent: Preflight & Capability

**Alias:** `preflight-agent`  
**Goal:** Implement `preflight.py` to verify the environment (backend installed, `inputstream.adaptive` present, DRM readiness) and fail fast with a single clear error.

### Responsibilities

- Implement `ensure_ready_or_raise()` that:

  1. Checks that the backend add-on is available:
     - Via import or Kodi JSON-RPC (`Addons.GetAddons`).
  2. Checks for `inputstream.adaptive` presence/enabled.
  3. Optionally queries backend for DRM readiness / region info.
  4. On failure:
     - Raises a well-defined exception (e.g. `PreflightError`) with a user-friendly message.
     - Message must advise the user to open and configure/log in to the existing Prime add-on and/or enable `inputstream.adaptive`.

- Implement a helper that **displays** this failure in a Kodi-friendly way:
  - Either dialog or notification, then cleanly returns from the current route.

- Ensure `preflight.ensure_ready_or_raise()` is invoked from:
  - Home route (root),
  - Diagnostics route,
  - Any route that eventually leads to playback.

### Input

- Backend agent’s APIs (`prime_api`).
- Kodi JSON-RPC details.
- Mission Brief performance/UX requirements.

### Output

- `resources/lib/preflight.py` with:
  - `ensure_ready_or_raise()` function.
  - Any small helpers to show messages.
  - No placeholders; actual checks.

---

## 4. Agent: Caching & Performance

**Alias:** `perf-cache-agent`  
**Goal:** Provide a **simple, robust TTL JSON cache** and a **timing decorator** used across the add-on to ensure fluency.

### Responsibilities

#### Cache

- Implement `resources/lib/cache.py` with:

  - `get(key: str) -> Optional[Any]`:
    - Look in `special://profile/addon_data/<addon.id>/cache/`.
    - Check TTL; if stale or missing, return `None`.
  - `set(key: str, data: Any, ttl_seconds: int = 300) -> None`:
    - Write JSON to disk with timestamp and TTL.

- Provide helper functions for common keys:
  - e.g. `get_home_data()`, `set_home_data(data)`, or rely on clear key naming policy.

#### Timing

- Implement `resources/lib/perf.py` with:

  - `timed(label: str)` decorator:
    - Measures elapsed time in milliseconds.
    - Logs with `xbmc.log` using consistent prefix (e.g. `[primeflix-perf] label=... elapsed_ms=...`).
    - Respects an “Enable performance logging” setting (no-op if disabled).

- Implement acceptance-check helpers:
  - Functions that:
    - Compare elapsed times vs targets:
      - Cold home ≤ 1500 ms.
      - Warm home ≤ 300 ms.
      - Rail fetch: ≤ 500 ms cold, ≤ 150 ms warm.
    - Emit `WARNING` logs when thresholds are exceeded.

### Input

- File path conventions from Architect Agent.
- Settings from Settings Agent.

### Output

- `resources/lib/cache.py` with full TTL cache implementation.
- `resources/lib/perf.py` with decorator and threshold-check helpers.

---

## 5. Agent: Routing & Glue

**Alias:** `router-agent`  
**Goal:** Implement `default.py` and `router.py` to map Kodi plugin URIs to the correct UI functions.

### Responsibilities

- Implement `default.py`:

  - Imports `dispatch()` from `resources.lib.router`.
  - Passes `sys.argv[0]` and `sys.argv[2]` (when present) into `dispatch`.

- Implement `resources/lib/router.py`:

  - Parse query parameters from `sys.argv[2]`.
  - Routes:
    - No `action` / empty → `ui.home.show_home()`.
    - `action=list&rail=<id>` → `ui.listing.show_list(rail_id)`.
    - `action=play&asin=<id>` → `ui.playback.play(asin)`.
    - `action=diagnostics` → `ui.diagnostics.show_results()`.
    - `action=search` → search UI (or delegate to backend search).
  - Handle preflight errors gracefully:
    - Catch `PreflightError` and show message.
  - Always call `xbmcplugin.endOfDirectory(handle)` after directory-building routes.

### Input

- Architect’s routing design.
- Function signatures from UI agents.

### Output

- `default.py` and `resources/lib/router.py` fully implemented, with no dead routes.

---

## 6. Agent: Home & Listing UI

**Alias:** `ui-home-listing-agent`  
**Goal:** Deliver the Netflix-style rails and listing pages using backend data + cache for fast, fluent navigation.

### Responsibilities

#### Home (`ui/home.py`)

- Implement `show_home()`:

  1. Run `preflight.ensure_ready_or_raise()`.
  2. Set content type using `xbmcplugin.setContent`:
     - For mixed rails: `"videos"`.
  3. Fetch home data:
     - First try cache; if missing/stale, call `prime_api` and update cache.
  4. Build rails:
     - Continue Watching (if available).
     - Prime Originals.
     - Movies.
     - TV.
     - Recommended For You (if available).
     - Search (always last).
  5. Use in-memory list building, then add directory items in one go.
  6. Wrap in `@timed("home_build")` and call performance threshold helpers.

#### Listing (`ui/listing.py`)

- Implement `show_list(rail_id, page=1)`:

  - Determine rail type (movies/tv/mixed).
  - Set `xbmcplugin.setContent` accordingly.
  - Fetch items for the given rail + page (using cache + backend).
  - Build items with:
    - `setArt` and `setInfo` fully populated.
    - Folders for paginated “More…” if applicable.
  - Wrap in `@timed(f"list_{rail_id}_page_{page}")`.

### Input

- Backend models from `prime_api`.
- Cache/perf helpers.
- Architect’s rail definitions.

### Output

- `resources/lib/ui/home.py` and `resources/lib/ui/listing.py` with a smooth, Netflix-style UX.

---

## 7. Agent: Playback UI

**Alias:** `ui-playback-agent`  
**Goal:** Implement `ui/playback.py` to hand off playable items to Kodi using `inputstream.adaptive` and backend-provided data.

### Responsibilities

- Implement `play(asin: str)`:

  1. Optionally run `preflight.ensure_ready_or_raise()` (or rely on upstream).
  2. Call `prime_api.get_playable(asin)`.
  3. From the returned structure, create a `xbmcgui.ListItem`:
     - Set all `inputstream.adaptive` properties (`inputstream`, `manifest_type`, license keys, headers, etc.).
     - Set info/metadata for the item.
     - `setContentLookup(False)`.
  4. Call `xbmcplugin.setResolvedUrl(handle, True, listitem)`.
  5. Wrap in `@timed("playback_handoff")` and log errors with details.

- Handle failures:
  - Show a notification when `get_playable` fails (with a user-readable message).
  - Write detailed error to log.

### Input

- Backend playable structure.
- Perf helpers.

### Output

- `resources/lib/ui/playback.py` with a complete playback path.

---

## 8. Agent: Diagnostics & QA

**Alias:** `diagnostics-agent`  
**Goal:** Implement the diagnostics route to validate performance and backend strategy in a user-visible way.

### Responsibilities

- Implement `resources/lib/ui/diagnostics.py`:

  - `show_results()` route should:
    1. Run `preflight.ensure_ready_or_raise()`.
    2. Execute home builder three times:
       - 1st: treat as cold (clear relevant cache before).
       - 2nd/3rd: warm.
    3. Gather timings (via `perf` infrastructure).
    4. Query backend for currently used strategy (direct import vs indirect).
    5. Present results as directory items:
       - Example titles:
         - `Run 1: 1030 ms (cold, strategy=direct)`
         - `Run 2: 130 ms (warm, strategy=direct)`
         - `[SLOW] Movies rail: 890 ms (threshold 500 ms)`
  - Ensure thresholds are evaluated and flagged.

### Input

- perf/cache helpers.
- Backend’s strategy flag.

### Output

- `resources/lib/ui/diagnostics.py` providing a usable, informative diagnostics route.

---

## 9. Agent: Settings & Localization

**Alias:** `settings-i18n-agent`  
**Goal:** Provide minimal, clean settings and base localization strings.

### Responsibilities

- Implement `resources/settings.xml` with the following options:

  - “Preferred region” (enum: us/uk/de/jp).
  - “Max resolution” (auto/1080p/720p).
  - “Use cache” (bool, default true).
  - “Cache TTL (seconds)” (int, default 300).
  - “Enable performance logging” (bool, default false).

- Provide `resources/language/resource.language.en_gb/strings.po` with IDs used in settings and messages.

- Ensure settings can be easily referenced from other modules via a small helper (module or function) if needed.

### Input

- Mission Brief settings requirements.

### Output

- `resources/settings.xml` and base `strings.po` complete and coherent.

---

## 10. Agent: Manifest & Packaging

**Alias:** `manifest-agent`  
**Goal:** Implement `addon.xml` and basic metadata (icon/fanart placeholders) so the add-on installs and appears correctly in Kodi.

### Responsibilities

- Create `addon.xml`:

  - Unique id (e.g. `plugin.video.primeflix`).
  - Name, version (e.g. `1.0.0`).
  - Type: `xbmc.addon.video`.
  - Depend on correct `xbmc.python` version for Kodi 21.
  - Declare summary/description that clearly states it requires an existing Prime/“Amazon VOD” add-on and is not official.

- Provide references for:

  - `icon.png`
  - `fanart.jpg`

- Ensure all file paths and imports match the folder structure defined by Architect.

### Input

- Kodi 21 add-on requirements.

### Output

- Valid `addon.xml` and consistent metadata.

---

## 11. Collaboration & Handoffs

- **Architect Agent** initializes and defines function signatures and data models.
- **Backend Agent** and **Preflight Agent** implement their modules first, exposing clear APIs.
- **Perf/Cache Agent** provides `cache` and `perf` modules early.
- **Router Agent** wires routes to stubs, then replaces stubs with real functions.
- **UI Agents** (Home/Listing, Playback, Diagnostics) implement views using the APIs and helpers.
- **Settings & Manifest Agents** finalize settings and `addon.xml`.

All agents must ensure:

- No route points to an unimplemented function.
- No TODOs are left in the final code.
- The resulting add-on can be dropped into a Kodi `addons` folder and used directly (once a compatible Prime backend is installed and configured).
