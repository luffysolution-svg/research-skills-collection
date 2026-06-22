#!/usr/bin/env python3
"""Create and safely remove per-task temporary workspaces."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


PREFIX = "document-markdown-"
MARKER = ".document-markdown-workspace.json"


def temp_root() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def create_workspace() -> Path:
    task_id = uuid.uuid4().hex
    workspace = Path(tempfile.mkdtemp(prefix=PREFIX)).resolve()
    marker = {
        "schema": 1,
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "temp_root": str(temp_root()),
    }
    (workspace / MARKER).write_text(
        json.dumps(marker, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return workspace


def validate_workspace(value: str) -> Path:
    workspace = Path(value).expanduser().resolve()
    root = temp_root()
    if workspace == root or not is_relative_to(workspace, root):
        raise ValueError("Refusing path outside the system temporary directory")
    if not workspace.name.startswith(PREFIX):
        raise ValueError(f"Workspace name must start with {PREFIX!r}")
    if workspace.is_symlink():
        raise ValueError("Refusing to clean a symbolic-link workspace")

    marker_path = workspace / MARKER
    if not marker_path.is_file() or marker_path.is_symlink():
        raise ValueError("Workspace marker is missing or invalid")
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if marker.get("schema") != 1:
        raise ValueError("Unsupported workspace marker schema")
    if Path(marker.get("workspace", "")).resolve() != workspace:
        raise ValueError("Workspace marker path does not match")
    if Path(marker.get("temp_root", "")).resolve() != root:
        raise ValueError("Workspace marker temporary root does not match")
    if not marker.get("task_id"):
        raise ValueError("Workspace marker task ID is missing")
    return workspace


def cleanup_workspace(value: str) -> None:
    workspace = validate_workspace(value)
    shutil.rmtree(workspace)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("workspace")
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("workspace")
    args = parser.parse_args()

    try:
        if args.command == "create":
            print(create_workspace())
        elif args.command == "validate":
            print(validate_workspace(args.workspace))
        else:
            cleanup_workspace(args.workspace)
            print("Temporary workspace cleaned.")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Workspace operation refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
