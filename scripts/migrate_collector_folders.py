from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Set, Tuple

from src.data_collector_storage import item_blob_name


def collector_docs(storage_root: Path) -> Iterable[Path]:
    yield from storage_root.glob("*/data_collector/*/*/bboxes.json")


def migrated_doc(doc: Dict[str, Any], old_storage_name: str, new_storage_name: str) -> Dict[str, Any]:
    result = dict(doc)
    uid = str(doc.get("user_id") or "")
    old_prefix = f"{uid}/data_collector/{old_storage_name}/"
    new_prefix = f"{uid}/data_collector/{new_storage_name}/"
    result["storage_name"] = new_storage_name
    for key in ("image_blob", "evaluated_image_blob"):
        value = result.get(key)
        if isinstance(value, str) and value.startswith(old_prefix):
            result[key] = new_prefix + value[len(old_prefix) :]
    return result


def migrate_input_images(storage_root: Path, *, dry_run: bool) -> Tuple[int, int]:
    renamed = 0
    skipped = 0
    for doc_path in sorted(collector_docs(storage_root)):
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
        image_blob = str(doc.get("image_blob") or "")
        source_path = storage_root / image_blob
        if source_path.name.startswith("input_image."):
            skipped += 1
            continue
        if not source_path.name.startswith("image."):
            skipped += 1
            continue

        destination_path = source_path.with_name(f"input_image{source_path.suffix}")
        if destination_path.exists():
            raise FileExistsError(f"Refusing to overwrite {destination_path}")
        if not source_path.is_file():
            raise FileNotFoundError(f"Input image not found: {source_path}")

        print(f"{source_path.relative_to(storage_root)} -> {destination_path.relative_to(storage_root)}")
        if not dry_run:
            source_path.rename(destination_path)
            try:
                doc["image_blob"] = destination_path.relative_to(storage_root).as_posix()
                temporary_doc = doc_path.with_name(".bboxes.json.tmp")
                temporary_doc.write_text(
                    json.dumps(doc, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                temporary_doc.replace(doc_path)
            except Exception:
                destination_path.rename(source_path)
                raise
        renamed += 1

    return renamed, skipped


def remove_redundant_evaluated_images(storage_root: Path, *, dry_run: bool) -> Tuple[int, int]:
    evaluated_paths = set(storage_root.glob("*/data_collector/*/*/evaluated.png"))
    cleared_references = 0
    for doc_path in sorted(collector_docs(storage_root)):
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
        evaluated_blob = str(doc.get("evaluated_image_blob") or "")
        if not evaluated_blob:
            continue
        evaluated_paths.add(storage_root / evaluated_blob)
        if not dry_run:
            doc.pop("evaluated_image_blob", None)
            temporary_doc = doc_path.with_name(".bboxes.json.tmp")
            temporary_doc.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_doc.replace(doc_path)
        cleared_references += 1

    existing_paths = sorted(path for path in evaluated_paths if path.is_file())
    for path in existing_paths:
        print(f"Remove redundant {path.relative_to(storage_root)}")
        if not dry_run:
            path.unlink()
    return len(existing_paths), cleared_references


def migrate(storage_root: Path, *, dry_run: bool) -> Tuple[int, int, int, int, int, int]:
    docs = sorted(collector_docs(storage_root))
    occupied: Set[str] = set()
    for path in docs:
        relative = path.parent.relative_to(storage_root)
        occupied.add("/".join(relative.parts[2:]))

    migrated = 0
    skipped = 0
    for doc_path in docs:
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
        old_storage_name = "/".join(doc_path.parent.relative_to(storage_root).parts[2:])
        occupied.discard(old_storage_name)
        new_storage_name = item_blob_name(
            doc.get("template_name") or old_storage_name.split("/", 1)[0],
            doc.get("original_filename") or doc.get("name"),
            str(doc.get("sha256") or doc.get("id") or ""),
            occupied,
        )
        occupied.add(new_storage_name)
        if new_storage_name == old_storage_name:
            skipped += 1
            continue

        source_dir = doc_path.parent
        uid_dir = storage_root / source_dir.relative_to(storage_root).parts[0] / "data_collector"
        destination_dir = uid_dir / new_storage_name
        if destination_dir.exists():
            raise FileExistsError(f"Refusing to overwrite {destination_dir}")

        print(f"{source_dir.relative_to(storage_root)} -> {destination_dir.relative_to(storage_root)}")
        if not dry_run:
            updated = migrated_doc(doc, old_storage_name, new_storage_name)
            destination_dir.parent.mkdir(parents=True, exist_ok=True)
            source_dir.rename(destination_dir)
            try:
                temporary_doc = destination_dir / ".bboxes.json.tmp"
                temporary_doc.write_text(
                    json.dumps(updated, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                temporary_doc.replace(destination_dir / "bboxes.json")
            except Exception:
                destination_dir.rename(source_dir)
                raise
        migrated += 1

    renamed_images, skipped_images = migrate_input_images(storage_root, dry_run=dry_run)
    removed_evaluated, cleared_references = remove_redundant_evaluated_images(
        storage_root,
        dry_run=dry_run,
    )
    return (
        migrated,
        skipped,
        renamed_images,
        skipped_images,
        removed_evaluated,
        cleared_references,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Give data-collector folders and input images readable names."
    )
    parser.add_argument("--storage-root", type=Path, default=Path(__file__).resolve().parents[1] / "local_storage")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    (
        migrated,
        skipped,
        renamed_images,
        skipped_images,
        removed_evaluated,
        cleared_references,
    ) = migrate(
        args.storage_root.resolve(),
        dry_run=args.dry_run,
    )
    action = "Would migrate" if args.dry_run else "Migrated"
    image_action = "would rename" if args.dry_run else "renamed"
    evaluated_action = "would remove" if args.dry_run else "removed"
    print(
        f"{action} {migrated} collector folders; {skipped} already used readable names; "
        f"{image_action} {renamed_images} input images; {skipped_images} already used the new name; "
        f"{evaluated_action} {removed_evaluated} redundant evaluated images and "
        f"cleared {cleared_references} references."
    )


if __name__ == "__main__":
    main()
