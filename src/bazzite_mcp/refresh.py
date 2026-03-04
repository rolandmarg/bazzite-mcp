"""Standalone entry point for refreshing the docs cache.

Used by the systemd timer: python -m bazzite_mcp.refresh
"""

import asyncio

from bazzite_mcp.tools.docs import refresh_docs_cache


def main() -> None:
    print(asyncio.run(refresh_docs_cache()))


if __name__ == "__main__":
    main()
