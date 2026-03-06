"""Clean uninstall utility for bazzite-mcp.

Removes all data created by the server:
- Local cache database
- Audit log database
- Config files (optional)

Usage: python -m bazzite_mcp.cleanup [--include-config]
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from bazzite_mcp.db import get_db_path


def get_data_dir() -> Path:
    return get_db_path("").parent


def get_config_dir() -> Path:
    import os

    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "bazzite-mcp"


def cleanup(include_config: bool = False, dry_run: bool = False) -> list[str]:
    """Remove all bazzite-mcp data files.

    Returns list of paths removed (or that would be removed in dry_run).
    """
    removed: list[str] = []

    data_dir = get_data_dir()
    if data_dir.exists():
        for f in data_dir.iterdir():
            path_str = str(f)
            removed.append(path_str)
            if not dry_run:
                f.unlink(missing_ok=True)
        if not dry_run:
            data_dir.rmdir()
        removed.append(str(data_dir))

    if include_config:
        config_dir = get_config_dir()
        if config_dir.exists():
            for f in config_dir.iterdir():
                path_str = str(f)
                removed.append(path_str)
                if not dry_run:
                    f.unlink(missing_ok=True)
            if not dry_run:
                config_dir.rmdir()
            removed.append(str(config_dir))

    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean uninstall bazzite-mcp data")
    parser.add_argument(
        "--include-config",
        action="store_true",
        help="Also remove config files (~/.config/bazzite-mcp/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting",
    )
    args = parser.parse_args()

    removed = cleanup(include_config=args.include_config, dry_run=args.dry_run)

    if not removed:
        print("Nothing to clean up.")
        return

    label = "Would remove" if args.dry_run else "Removed"
    for path in removed:
        print(f"  {label}: {path}")

    if args.dry_run:
        print(f"\nDry run: {len(removed)} items would be removed.")
    else:
        print(f"\nCleaned up {len(removed)} items.")


if __name__ == "__main__":
    main()
