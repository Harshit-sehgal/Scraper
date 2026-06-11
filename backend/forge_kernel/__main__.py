"""forge-kernel — CLI entry point.

Run with::

    python -m forge_kernel            # start the API server (default port 9010)
    python -m forge_kernel --help      # show all options
"""

from __future__ import annotations

import argparse
import logging

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="DataForge Forge Kernel API server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1; pass 0.0.0.0 explicitly for container ingress)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9010,
        help="Port to listen on (default: 9010)",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Logging level (default: info)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from forge_kernel.api.app import create_app

    app = create_app()

    logger = logging.getLogger("forge_kernel")
    logger.info("Starting Forge Kernel on %s:%d", args.host, args.port)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
