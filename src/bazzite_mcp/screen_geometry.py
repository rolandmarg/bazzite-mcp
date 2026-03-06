"""Minimal screen geometry helpers used by input tooling."""

from __future__ import annotations

import logging
import re
from functools import lru_cache

from bazzite_mcp.runner import run_command

logger = logging.getLogger(__name__)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@lru_cache(maxsize=1)
def get_monitor_info() -> dict[str, dict]:
    """Parse monitor positions and sizes from kscreen-doctor."""
    result = run_command("kscreen-doctor --outputs")
    if result.returncode != 0:
        logger.warning("kscreen-doctor failed: %s", result.stderr)
        return {}

    text = _ANSI_RE.sub("", result.stdout)
    monitors: dict[str, dict] = {}
    current_name: str | None = None

    for line in text.splitlines():
        header = re.match(r"Output:\s+\d+\s+(\S+)", line)
        if header:
            current_name = header.group(1)
            monitors[current_name] = {"x": 0, "y": 0, "w": 0, "h": 0, "scale": 1.0}
            continue

        if current_name is None:
            continue

        geometry = re.match(r"\s*Geometry:\s*(-?\d+),(-?\d+)\s+(\d+)x(\d+)", line)
        if geometry:
            monitors[current_name]["x"] = int(geometry.group(1))
            monitors[current_name]["y"] = int(geometry.group(2))
            monitors[current_name]["w"] = int(geometry.group(3))
            monitors[current_name]["h"] = int(geometry.group(4))
            continue

        scale = re.match(r"\s*Scale:\s*(\d+(?:\.\d+)?)", line)
        if scale:
            monitors[current_name]["scale"] = float(scale.group(1))

    return monitors
