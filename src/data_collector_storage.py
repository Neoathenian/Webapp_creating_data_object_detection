from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any, Iterable


_UNSAFE_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_path_part(value: Any, fallback: str, *, max_length: int = 120) -> str:
    """Return one portable path component without changing readable names."""
    text = str(value or "").strip()
    text = _UNSAFE_PATH_CHARS.sub("-", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:max_length].rstrip(" .") or fallback


def uploaded_filename(value: Any, digest: str) -> str:
    """Return a safe basename for an uploaded file, including its extension."""
    basename = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    return safe_path_part(basename, f"image-{digest[:16]}")


def input_image_blob_name(uid: str, collector_root: str, item_name: str, extension: Any) -> str:
    """Return the collector blob path for an input image, preserving its format."""
    safe_extension = re.sub(r"[^a-zA-Z0-9]", "", str(extension or ""))[:15].lower() or "png"
    return f"{uid}/{collector_root}/{item_name}/input_image.{safe_extension}"


def item_blob_name(
    template_name: Any,
    original_filename: Any,
    digest: str,
    occupied: Iterable[str] = (),
) -> str:
    """Build ``<template>/<filename stem>`` and resolve name collisions."""
    template_part = safe_path_part(template_name, "template")
    filename_part = uploaded_filename(original_filename, digest)
    suffix = PurePath(filename_part).suffix
    folder_part = filename_part[: -len(suffix)] if suffix else filename_part
    folder_part = folder_part or filename_part
    occupied_names = set(occupied)
    candidate = f"{template_part}/{folder_part}"
    if candidate not in occupied_names:
        return candidate

    for digest_length in (8, 12, 16, 24, 32, len(digest)):
        discriminator = digest[:digest_length] or "copy"
        candidate = f"{template_part}/{folder_part}-{discriminator}"
        if candidate not in occupied_names:
            return candidate

    # This is reachable only when ``digest`` is empty or every hash spelling was
    # already used. Keep the result readable while guaranteeing progress.
    copy_number = 2
    while True:
        candidate = f"{template_part}/{folder_part}-{copy_number}"
        if candidate not in occupied_names:
            return candidate
        copy_number += 1
