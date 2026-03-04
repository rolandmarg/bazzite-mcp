from __future__ import annotations

import atexit
import logging
import os
import signal
import sys

from bazzite_mcp.server import mcp

logger = logging.getLogger(__name__)

_cleanup_done = False


def _cleanup() -> None:
    """Release resources on shutdown."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    logger.debug("bazzite-mcp shutting down, releasing resources")

    # Close any cached singleton connections
    from bazzite_mcp.config import reset_config

    reset_config()


def _signal_handler(signum: int, _frame: object) -> None:
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    logger.info("Received signal %s, shutting down gracefully", signum)
    _cleanup()
    sys.exit(0)


def main() -> None:
    logging.basicConfig(
        level=getattr(
            logging,
            os.environ.get("BAZZITE_MCP_LOG_LEVEL", "INFO").upper(),
            logging.INFO,
        ),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    atexit.register(_cleanup)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
