"""Synchronize the local searchable TSE master from J-Quants.

Only aggregate counts and non-secret provenance are written to stdout.  Use
``--adopt-legacy`` explicitly to reconcile rows created before source
provenance was recorded; without it, unmatched legacy/manual rows are never
treated as J-Quants deletions.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for import_root in (REPO_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from app.db.session import get_session_factory, init_db  # noqa: E402
from app.services.monitoring_runtime import get_monitoring_container  # noqa: E402
from kabuhandan_hojo.connectors.base import ConnectorError, MissingCredentialsError  # noqa: E402
from kabuhandan_hojo.services.ingestion import IngestionService  # noqa: E402


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=_parse_date, help="Historical snapshot date (YYYY-MM-DD).")
    parser.add_argument(
        "--adopt-legacy",
        action="store_true",
        help="Explicitly classify unmatched legacy rows as J-Quants-owned during a current full sync.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and calculate changes, then roll the transaction back.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.as_of is not None and args.adopt_legacy:
        print(json.dumps({"ok": False, "error": "--adopt-legacy requires a current snapshot."}))
        return 2

    init_db()
    service = IngestionService(get_monitoring_container())
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            result = await service.sync_security_master_from_jquants(
                session,
                as_of=args.as_of,
                adopt_legacy=args.adopt_legacy,
            )
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
        except MissingCredentialsError:
            session.rollback()
            print(json.dumps({"ok": False, "error": "JQUANTS_API_KEY is not configured."}))
            return 1
        except ConnectorError:
            session.rollback()
            print(json.dumps({"ok": False, "error": "J-Quants master synchronization failed."}))
            return 1
        except Exception:
            session.rollback()
            print(json.dumps({"ok": False, "error": "Local master persistence failed."}))
            return 1

    payload = asdict(result)
    payload.update({"ok": True, "dry_run": args.dry_run})
    print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_run(_build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
