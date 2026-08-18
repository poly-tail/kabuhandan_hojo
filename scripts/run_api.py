"""Run the Phase 0 API with optional mock responses."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

import uvicorn


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args(
    argv: Sequence[str] | None = None,
    *,
    default_host: str | None = None,
    default_port: int | None = None,
) -> argparse.Namespace:
    """Parse command-line arguments for the API runner."""

    resolved_host = default_host if default_host is not None else os.getenv("API_HOST", "127.0.0.1")
    resolved_port = default_port if default_port is not None else int(os.getenv("API_PORT", "8000"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=resolved_host)
    parser.add_argument("--port", type=int, default=resolved_port)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--mock", action="store_true", help="serve in-memory mock responses instead of live DB-backed data")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the API server."""

    os.chdir(REPO_ROOT)
    from app.core.config import get_settings

    settings = get_settings()
    args = parse_args(argv, default_host=settings.api_host, default_port=settings.api_port)
    if args.mock:
        os.environ["APP_USE_MOCK"] = "true"

    from app.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    uvicorn.run("app.main:create_app", host=args.host, port=args.port, reload=args.reload, factory=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
