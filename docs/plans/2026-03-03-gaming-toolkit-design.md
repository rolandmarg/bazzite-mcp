# Gaming Toolkit Design

**Date:** 2026-03-03
**Status:** Approved

## Problem

Bazzite is a gaming OS. bazzite-mcp has zero gaming awareness. This is the biggest identity gap — the MCP server should help users optimize and troubleshoot games using their actual hardware profile and real community data.

## Design Principle

The AI agent is the reasoning engine. The MCP provides:
1. **Structured local data** — what's installed, what's configured
2. **Structured online data** — what the community says works
3. **Mutation tools** — apply the recommended settings

We don't build an optimizer. We build data access + config mutation. The AI composes them.

## Tools — 3 new tools in `tools/gaming.py`

### 1. `steam_library`

**Purpose:** List installed Steam games with metadata.

**Implementation:**
- Parse `libraryfolders.vdf` to find all Steam library paths
- Parse `appmanifest_*.acf` files from each library folder
- Return per-game: app ID, name, install size, state flags, Proton version (from `compatdata/`)
- Optional `filter` parameter for name substring matching

**Data sources:**
- `~/.steam/steam/config/libraryfolders.vdf` — library folder paths
- `<library>/steamapps/appmanifest_*.acf` — per-game manifest
- `<library>/steamapps/compatdata/<appid>/` — Proton prefix existence = Linux/Proton game

**Dependencies:** `vdf` Python library (MIT, parses Valve KeyValues format)

**Guardrails:** Read-only, no commands. Pure file parsing.

### 2. `game_reports`

**Purpose:** Fetch community compatibility and optimization data for a game.

**Implementation:**
- Takes: `app_id` (int) or `game_name` (str, resolved via steam_library)
- Queries ProtonDB API: `GET https://www.protondb.com/api/v1/reports/summaries/{appId}.json`
  - Returns: tier (Platinum/Gold/Silver/Bronze/Borked), confidence, score, trending
- Queries ProtonDB reports: `GET https://www.protondb.com/api/v1/reports?appId={appId}`
  - Returns: individual user reports with Proton version, OS, GPU, notes, rating
  - Filter/rank reports by hardware similarity to user's system (same GPU vendor, similar tier)
- Queries PCGamingWiki via Cargo API for known issues, settings recommendations
  - `api.php?action=cargoquery&tables=Infobox_game&fields=...&where=Steam_AppID='{appId}'`
- Cache results in existing SQLite `docs_cache.db` with 24h TTL (reuse `cache/` patterns)
- Return structured summary: tier, top reports (prioritizing similar hardware), known issues, recommended Proton version, common launch options from reports

**Dependencies:** `httpx` (already a dependency)

**Guardrails:** Read-only network calls. Cached. No mutations.

### 3. `game_settings`

**Purpose:** Read and write per-game gaming configuration (MangoHud + Steam launch options).

**Parameters:**
- `action`: `get` | `set`
- `app_id`: Steam app ID
- For `get`: returns current MangoHud config + Steam launch options for this game
- For `set`:
  - `mangohud` (optional dict): key-value pairs to write to MangoHud per-game config
  - `launch_options` (optional str): Steam launch options string to apply

**MangoHud config:**
- Per-game: `~/.config/MangoHud/<appid>.conf`
- Global: `~/.config/MangoHud/MangoHud.conf`
- Format: `key=value` per line (INI-like, no sections)
- Backup before write → enables rollback via audit system

**Steam launch options:**
- Stored in `~/.steam/steam/userdata/<userid>/config/localconfig.vdf`
- Path: `UserLocalConfigStore/Software/Valve/Steam/apps/<appid>/LaunchOptions`
- Backup VDF before write → rollback via audit system
- Uses `vdf` library for parsing and serialization

**Guardrails:**
- All writes audited via `run_audited` pattern (backup + audit log + rollback command)
- No shell commands — direct Python file I/O
- Validates MangoHud keys against known-good set to prevent typos

## Existing tools that cover the rest

| Need | Already covered by |
|------|--------------------|
| GPU, CPU, RAM, sensors | `hardware_info`, `system_info` |
| GameMode enable/disable | `manage_service` (systemctl --user) |
| Proton version listing | `steam_library` compatdata + `ls compatibilitytools.d/` via agent |
| Gamescope launch flags | AI knowledge — it constructs the string |
| Vulkan info | Extend `hardware_info` to include `vulkaninfo --summary` (minor) |

## Data flow — "Optimize this game"

```
User: "Optimize Cyberpunk for my system"

1. steam_library(filter="cyberpunk")  → app_id=1091500, Proton 9.0
2. hardware_info()                     → RTX 3060 Ti, i7-12700K, 32GB
3. game_reports(app_id=1091500)        → Gold tier, "use GE-Proton, FSR, cap 60fps"
4. AI reasons: GE-Proton10-32 available, FSR via gamescope, GameMode should be on
5. game_settings(action="set", app_id=1091500,
     mangohud={"fps_limit": 60, "gpu_stats": 1, "cpu_stats": 1},
     launch_options="gamescope -w 1920 -h 1080 -F fsr -r 60 -- mangohud %command%")
6. manage_service(service="gamemoded", action="enable", user=true)
```

## Architecture

**New file:** `src/bazzite_mcp/tools/gaming.py`

**New dependency:** `vdf` (add to pyproject.toml)

**Cache extension:** Add `game_reports` table to `docs_cache.db`:
```sql
CREATE TABLE IF NOT EXISTS game_reports (
    app_id INTEGER PRIMARY KEY,
    protondb_summary TEXT,    -- JSON blob
    protondb_reports TEXT,    -- JSON blob (top N reports)
    pcgamingwiki_data TEXT,   -- JSON blob
    fetched_at REAL           -- Unix timestamp for TTL
);
```

**Guardrails additions:**
- Add to `ALLOWED_COMMAND_PREFIXES`: `vulkaninfo` (for hardware_info extension)
- No other command allowlist changes needed (gaming tools use file I/O, not shell)

**Server registration:** Add 3 tools to `server.py` in new `# Gaming` section.

## What this does NOT include (YAGNI)

- Lutris/Heroic/Bottles — different launchers, separate scope
- Controller/gamepad mapping — complex input subsystem
- Live FPS monitoring — MCP is request-response
- Wine prefix management — Proton abstracts this
- Gamescope wrapper tool — AI constructs the flags
- GameMode wrapper — existing `manage_service` covers it
- Gaming hardware tool — existing `hardware_info` covers it
