from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from bazzite_mcp.db import ensure_tables, get_connection, get_db_path

logger = logging.getLogger(__name__)

REPORT_CACHE_TTL = 86400


def _get_cache_conn():
    db_path = get_db_path("docs_cache.db")
    conn = get_connection(db_path)
    ensure_tables(conn, "cache")
    return conn


def _get_cached_reports(app_id: int) -> dict[str, Any] | None:
    conn = _get_cache_conn()
    try:
        row = conn.execute(
            "SELECT protondb_summary, pcgamingwiki_data, fetched_at "
            "FROM game_reports WHERE app_id = ?",
            (app_id,),
        ).fetchone()
        if not row:
            return None

        fetched_raw = str(row["fetched_at"])
        if fetched_raw.endswith("Z"):
            fetched_raw = fetched_raw.replace("Z", "+00:00")

        try:
            fetched = datetime.fromisoformat(fetched_raw)
        except ValueError:
            return None

        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - fetched).total_seconds()
        if age > REPORT_CACHE_TTL:
            return None

        return {
            "protondb_summary": (
                json.loads(row["protondb_summary"]) if row["protondb_summary"] else None
            ),
            "pcgamingwiki_data": (
                json.loads(row["pcgamingwiki_data"])
                if row["pcgamingwiki_data"]
                else None
            ),
        }
    finally:
        conn.close()


def _cache_reports(
    app_id: int,
    summary: dict[str, Any] | None,
    pcgw: dict[str, Any] | None = None,
) -> None:
    conn = _get_cache_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO game_reports "
            "(app_id, protondb_summary, pcgamingwiki_data) VALUES (?, ?, ?)",
            (
                app_id,
                json.dumps(summary) if summary else None,
                json.dumps(pcgw) if pcgw else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def _fetch_protondb_summary(app_id: int) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"https://www.protondb.com/api/v1/reports/summaries/{app_id}.json"
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("ProtonDB summary fetch failed for %s: %s", app_id, exc)
        return None


async def _fetch_pcgamingwiki_data(app_id: int) -> dict[str, Any] | None:
    try:
        params = {
            "action": "cargoquery",
            "format": "json",
            "tables": "Infobox_game,Video,Input,API,Cloud",
            "join_on": (
                "Infobox_game._pageName=Video._pageName,"
                "Infobox_game._pageName=Input._pageName,"
                "Infobox_game._pageName=API._pageName,"
                "Infobox_game._pageName=Cloud._pageName"
            ),
            "fields": (
                "Infobox_game._pageName=Page,"
                "Infobox_game.Steam_AppID,"
                "Infobox_game.Developers,"
                "Infobox_game.Publishers,"
                "Infobox_game.Released,"
                "Infobox_game.Genres,"
                "Video.Upscaling,"
                "Video.Frame_gen,"
                "Video.Vsync,"
                "Input.Controller_support,"
                "Input.Full_controller_support,"
                "API.Vulkan_versions,"
                "Cloud.Steam=Steam_cloud"
            ),
            "where": f'Infobox_game.Steam_AppID HOLDS "{app_id}"',
            "limit": "1",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://www.pcgamingwiki.com/w/api.php", params=params
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return None

            rows = payload.get("cargoquery")
            if not isinstance(rows, list) or not rows:
                return None

            first = rows[0]
            if not isinstance(first, dict):
                return None

            title = first.get("title")
            if not isinstance(title, dict):
                return None

            return {
                "page": title.get("Page"),
                "steam_app_id": title.get("Steam AppID"),
                "developers": title.get("Developers"),
                "publishers": title.get("Publishers"),
                "released": title.get("Released"),
                "genres": title.get("Genres"),
                "upscaling": title.get("Upscaling"),
                "frame_gen": title.get("Frame gen"),
                "vsync": title.get("Vsync"),
                "controller_support": title.get("Controller support"),
                "full_controller_support": title.get("Full controller support"),
                "vulkan_versions": title.get("Vulkan versions"),
                "steam_cloud": title.get("Steam_cloud"),
            }
    except Exception as exc:
        logger.warning("PCGamingWiki fetch failed for %s: %s", app_id, exc)
        return None


def _format_reports(
    app_id: int,
    summary: dict[str, Any] | None,
    pcgw: dict[str, Any] | None,
    from_cache: bool = False,
) -> str:
    parts: list[str] = []
    cache_note = " (cached)" if from_cache else ""

    if summary:
        tier = str(summary.get("tier", "unknown"))
        confidence = str(summary.get("confidence", "unknown"))
        best = str(summary.get("bestReportedTier", "unknown"))
        trending = str(summary.get("trendingTier", "unknown"))
        total = summary.get("total")
        parts.append(
            f"## ProtonDB - App {app_id}{cache_note}\n"
            f"**Rating:** {tier.upper()}\n"
            f"**Confidence:** {confidence}\n"
            f"**Trending tier:** {trending}\n"
            f"**Best reported:** {best}\n"
            f"**Total reports:** {total if total is not None else 'unknown'}"
        )

    if pcgw:
        page = pcgw.get("page") or f"App {app_id}"
        parts.append(
            f"## PCGamingWiki - {page}\n"
            f"**Upscaling:** {pcgw.get('upscaling') or 'unknown'}\n"
            f"**Frame generation:** {pcgw.get('frame_gen') or 'unknown'}\n"
            f"**VSync:** {pcgw.get('vsync') or 'unknown'}\n"
            f"**Controller support:** {pcgw.get('controller_support') or 'unknown'}\n"
            f"**Full controller support:** {pcgw.get('full_controller_support') or 'unknown'}\n"
            f"**Vulkan:** {pcgw.get('vulkan_versions') or 'not listed'}\n"
            f"**Steam Cloud:** {pcgw.get('steam_cloud') or 'unknown'}"
        )

    return "\n\n".join(parts) if parts else f"No data available for app {app_id}."


async def _game_reports(app_id: int) -> str:
    """Fetch compatibility and optimization hints for a Steam game."""
    cached = _get_cached_reports(app_id)
    if cached:
        return _format_reports(
            app_id,
            cached.get("protondb_summary"),
            cached.get("pcgamingwiki_data"),
            from_cache=True,
        )

    summary = await _fetch_protondb_summary(app_id)
    pcgw = await _fetch_pcgamingwiki_data(app_id)
    if not summary and not pcgw:
        return (
            f"No community data found for app ID {app_id}. "
            "Could not retrieve ProtonDB summary or PCGamingWiki entries."
        )

    _cache_reports(app_id, summary, pcgw)
    return _format_reports(app_id, summary, pcgw, from_cache=False)
