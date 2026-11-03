"""`python -m open_cowork` — run the server."""

from __future__ import annotations

import argparse
import logging


def main() -> None:
    import uvicorn

    from .config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(prog="open-cowork")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (development)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        "open_cowork.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
