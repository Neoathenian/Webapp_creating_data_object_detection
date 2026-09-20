"""Move the legacy local workspace without changing saved logical blob keys."""
from __future__ import annotations

import argparse
from pathlib import Path


def migrate(source: Path, destination: Path, *, dry_run: bool = False) -> int:
    moves = []
    targets = set()
    for user_dir in sorted(source.iterdir()) if source.exists() else []:
        if not user_dir.is_dir():
            raise ValueError(f"Unexpected file in storage root: {user_dir}")
        for folder in sorted(user_dir.iterdir()):
            target = destination / ("bboxes" if folder.name in ("data_collector", "1data_collector") else "templates")
            if folder.name not in ("data_collector", "1data_collector"):
                target /= folder.name
            if target.exists() or target in targets:
                raise FileExistsError(f"Refusing to merge or overwrite {target}")
            targets.add(target)
            moves.append((folder, target))
    for folder, target in moves:
        print(f"{folder} -> {target}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            folder.rename(target)
    if not dry_run:
        for name in ("templates/CI", "templates/Talon", "bboxes"):
            (destination / name).mkdir(parents=True, exist_ok=True)
        if source.exists():
            for user_dir in source.iterdir():
                user_dir.rmdir()
            source.rmdir()
    return len(moves)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "local_storage")
    parser.add_argument("--destination", type=Path, default=root / "webapp_storage_outputs" / "local")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(f"Folders: {migrate(args.source, args.destination, dry_run=args.dry_run)}")
