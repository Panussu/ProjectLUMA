from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from luma_backend import create_app
from luma_backend.maintenance import backup_backend, cleanup_expired_jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LUMA backend backup and retention tools")
    commands = parser.add_subparsers(dest="command", required=True)

    backup = commands.add_parser("backup", help="Back up SQLite and result media")
    backup.add_argument(
        "--destination",
        type=Path,
        default=Path(__file__).resolve().parent / "backups",
    )

    cleanup = commands.add_parser("cleanup", help="Preview or delete expired terminal jobs")
    cleanup.add_argument("--days", type=int)
    cleanup.add_argument(
        "--apply",
        action="store_true",
        help="Delete the reported jobs and files; without this flag the command is read-only",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_app({"RECOVER_JOBS_ON_STARTUP": False})
    if args.command == "backup":
        result = {"backup": str(backup_backend(app, args.destination))}
    else:
        days = args.days or app.config["MEDIA_RETENTION_DAYS"]
        result = cleanup_expired_jobs(app, days, apply=args.apply)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
