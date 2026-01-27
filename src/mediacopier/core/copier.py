"""Copy engine for MediaCopier.

This module provides the core copying functionality including:
- Building copy plans from match results
- Executing copy plans with shutil.copy2 (preserving timestamps)
- Dry-run mode for planning without copying
- Collision handling strategies
- Progress callbacks and final reporting
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from mediacopier.core.matcher import MatchResult
from mediacopier.core.models import OrganizationMode


class CollisionStrategy(Enum):
    """Strategy for handling file collisions at destination."""

    SKIP = "skip"
    RENAME = "rename"
    COMPARE_SIZE = "compare_size"
    COMPARE_HASH = "compare_hash"


class CopyItemAction(Enum):
    """Action to perform for a copy item."""

    COPY = "copy"
    SKIP_EXISTS = "skip_exists"
    SKIP_SAME_SIZE = "skip_same_size"
    SKIP_SAME_HASH = "skip_same_hash"
    RENAME_COPY = "rename_copy"


@dataclass
class CopyPlanItem:
    """Represents a single file to be copied in the plan."""

    source: str
    destination: str
    action: CopyItemAction
    size: int
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source": self.source,
            "destination": self.destination,
            "action": self.action.value,
            "size": self.size,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CopyPlanItem:
        """Deserialize from dictionary."""
        return cls(
            source=data["source"],
            destination=data["destination"],
            action=CopyItemAction(data["action"]),
            size=data["size"],
            reason=data.get("reason", ""),
        )


@dataclass
class CopyPlan:
    """A plan describing all files to be copied."""

    items: list[CopyPlanItem] = field(default_factory=list)
    total_bytes: int = 0
    files_to_copy: int = 0
    files_to_skip: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "items": [item.to_dict() for item in self.items],
            "total_bytes": self.total_bytes,
            "files_to_copy": self.files_to_copy,
            "files_to_skip": self.files_to_skip,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CopyPlan:
        """Deserialize from dictionary."""
        return cls(
            items=[CopyPlanItem.from_dict(item) for item in data.get("items", [])],
            total_bytes=data.get("total_bytes", 0),
            files_to_copy=data.get("files_to_copy", 0),
            files_to_skip=data.get("files_to_skip", 0),
        )


@dataclass
class CopyReport:
    """Final report after executing a copy plan."""

    copied: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_copied: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "copied": self.copied,
            "skipped": self.skipped,
            "failed": self.failed,
            "bytes_copied": self.bytes_copied,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CopyReport:
        """Deserialize from dictionary."""
        return cls(
            copied=data.get("copied", 0),
            skipped=data.get("skipped", 0),
            failed=data.get("failed", 0),
            bytes_copied=data.get("bytes_copied", 0),
            errors=data.get("errors", []),
        )


# Type alias for progress callbacks
# (current_file_index, total_files, current_file_path, bytes_copied_so_far, total_bytes)
ProgressCallback = Callable[[int, int, str, int, int], None]


def compute_file_hash(file_path: str | Path, algorithm: str = "md5") -> str:
    """Compute hash of a file.

    Args:
        file_path: Path to the file.
        algorithm: Hash algorithm to use (default: md5).

    Returns:
        Hex digest of the file hash.
    """
    path = Path(file_path)
    h = hashlib.new(algorithm)
    with path.open("rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def generate_unique_filename(dest_path: Path) -> Path:
    """Generate a unique filename by adding a numeric suffix.

    This function produces deterministic renaming by incrementing a counter.

    Args:
        dest_path: Original destination path that has a collision.

    Returns:
        New unique path with numeric suffix.
    """
    stem = dest_path.stem
    suffix = dest_path.suffix
    parent = dest_path.parent

    counter = 1
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1


def _compute_destination_path(
    source_path: str,
    dest_root: str,
    organization_mode: OrganizationMode,
    artist: str | None = None,
    genre: str | None = None,
    request_name: str | None = None,
    source_root: str | None = None,
) -> Path:
    """Compute the destination path based on organization mode.

    Args:
        source_path: Path to the source file.
        dest_root: Root destination directory.
        organization_mode: How to organize files.
        artist: Artist name for SCATTER_BY_ARTIST mode.
        genre: Genre name for SCATTER_BY_GENRE mode.
        request_name: Request name for FOLDER_PER_REQUEST mode.
        source_root: Source root for KEEP_RELATIVE mode.

    Returns:
        Full destination path.
    """
    source = Path(source_path)
    dest = Path(dest_root)
    filename = source.name

    if organization_mode == OrganizationMode.SINGLE_FOLDER:
        return dest / filename

    elif organization_mode == OrganizationMode.SCATTER_BY_ARTIST:
        subfolder = artist if artist else "Unknown Artist"
        # Sanitize folder name
        subfolder = "".join(c for c in subfolder if c.isalnum() or c in " -_").strip()
        if not subfolder:
            subfolder = "Unknown Artist"
        return dest / subfolder / filename

    elif organization_mode == OrganizationMode.SCATTER_BY_GENRE:
        subfolder = genre if genre else "Unknown Genre"
        # Sanitize folder name
        subfolder = "".join(c for c in subfolder if c.isalnum() or c in " -_").strip()
        if not subfolder:
            subfolder = "Unknown Genre"
        return dest / subfolder / filename

    elif organization_mode == OrganizationMode.FOLDER_PER_REQUEST:
        subfolder = request_name if request_name else "Request"
        # Sanitize folder name
        subfolder = "".join(c for c in subfolder if c.isalnum() or c in " -_").strip()
        if not subfolder:
            subfolder = "Request"
        return dest / subfolder / filename

    elif organization_mode == OrganizationMode.KEEP_RELATIVE:
        if source_root:
            try:
                relative = source.relative_to(source_root)
                return dest / relative
            except ValueError:
                # Source is not under source_root, use filename only
                return dest / filename
        return dest / filename

    # Default fallback
    return dest / filename


def _resolve_collision(
    source_path: Path,
    dest_path: Path,
    strategy: CollisionStrategy,
) -> tuple[CopyItemAction, Path, str]:
    """Resolve a file collision based on strategy.

    Args:
        source_path: Path to the source file.
        dest_path: Path to the destination file (that already exists).
        strategy: Strategy to use for resolving the collision.

    Returns:
        Tuple of (action, final_destination_path, reason).
    """
    if strategy == CollisionStrategy.SKIP:
        return CopyItemAction.SKIP_EXISTS, dest_path, "File already exists"

    elif strategy == CollisionStrategy.RENAME:
        new_dest = generate_unique_filename(dest_path)
        return CopyItemAction.RENAME_COPY, new_dest, f"Renamed to {new_dest.name}"

    elif strategy == CollisionStrategy.COMPARE_SIZE:
        source_size = source_path.stat().st_size
        dest_size = dest_path.stat().st_size
        if source_size == dest_size:
            return CopyItemAction.SKIP_SAME_SIZE, dest_path, "Same size, skipping"
        else:
            new_dest = generate_unique_filename(dest_path)
            return (
                CopyItemAction.RENAME_COPY,
                new_dest,
                f"Different size, renamed to {new_dest.name}",
            )

    elif strategy == CollisionStrategy.COMPARE_HASH:
        source_hash = compute_file_hash(source_path)
        dest_hash = compute_file_hash(dest_path)
        if source_hash == dest_hash:
            return CopyItemAction.SKIP_SAME_HASH, dest_path, "Same hash, skipping"
        else:
            new_dest = generate_unique_filename(dest_path)
            return (
                CopyItemAction.RENAME_COPY,
                new_dest,
                f"Different hash, renamed to {new_dest.name}",
            )

    # Default: skip
    return CopyItemAction.SKIP_EXISTS, dest_path, "File already exists"


def build_copy_plan(
    matches: list[MatchResult],
    organization_mode: OrganizationMode,
    dest_root: str,
    collision_strategy: CollisionStrategy = CollisionStrategy.SKIP,
    source_root: str | None = None,
) -> CopyPlan:
    """Build a copy plan from match results.

    This function creates a plan describing what files will be copied and where,
    without actually performing any copy operations. This allows for dry-run
    inspection and user review before executing.

    Args:
        matches: List of match results from the matcher.
        organization_mode: How to organize files at destination.
        dest_root: Root destination directory.
        collision_strategy: How to handle file collisions.
        source_root: Source root for KEEP_RELATIVE mode.

    Returns:
        CopyPlan with all planned items.
    """
    plan = CopyPlan()

    # Track destinations to detect collisions within the same plan
    planned_destinations: dict[str, CopyPlanItem] = {}

    for match_result in matches:
        if not match_result.match_found or not match_result.best_match:
            continue

        source_file = match_result.best_match.media_file
        source_path = Path(source_file.path)

        # Get metadata for organization
        artist = None
        genre = None
        if source_file.audio_meta:
            artist = source_file.audio_meta.artist
            genre = source_file.audio_meta.genre

        request_name = match_result.requested_item.texto_original

        # Compute destination path
        file_dest = _compute_destination_path(
            source_path=source_file.path,
            dest_root=dest_root,
            organization_mode=organization_mode,
            artist=artist,
            genre=genre,
            request_name=request_name,
            source_root=source_root,
        )

        file_size = source_file.tamano

        # Check for collisions in the plan itself (same destination from different sources)
        dest_str = str(file_dest)
        if dest_str in planned_destinations:
            # Collision within plan - rename this file
            file_dest = generate_unique_filename(file_dest)
            dest_str = str(file_dest)

        # Check for collision with existing file at destination
        if file_dest.exists():
            action, final_dest, reason = _resolve_collision(
                source_path, file_dest, collision_strategy
            )
            item = CopyPlanItem(
                source=source_file.path,
                destination=str(final_dest),
                action=action,
                size=file_size,
                reason=reason,
            )
        else:
            # No collision - plan to copy
            item = CopyPlanItem(
                source=source_file.path,
                destination=dest_str,
                action=CopyItemAction.COPY,
                size=file_size,
                reason="",
            )

        planned_destinations[str(item.destination)] = item
        plan.items.append(item)

        # Update plan statistics
        if item.action in (CopyItemAction.COPY, CopyItemAction.RENAME_COPY):
            plan.files_to_copy += 1
            plan.total_bytes += file_size
        else:
            plan.files_to_skip += 1

    return plan


def execute_copy_plan(
    plan: CopyPlan,
    dry_run: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> CopyReport:
    """Execute a copy plan.

    Args:
        plan: The copy plan to execute.
        dry_run: If True, don't actually copy files, just log actions.
        progress_callback: Optional callback for progress updates.
            Called with (current_index, total, current_file, bytes_so_far, total_bytes).

    Returns:
        CopyReport with results of the copy operation.
    """
    report = CopyReport()
    total_items = len(plan.items)
    bytes_copied_so_far = 0

    for i, item in enumerate(plan.items):
        # Report progress
        if progress_callback:
            progress_callback(
                i + 1,
                total_items,
                item.source,
                bytes_copied_so_far,
                plan.total_bytes,
            )

        if item.action in (
            CopyItemAction.SKIP_EXISTS,
            CopyItemAction.SKIP_SAME_SIZE,
            CopyItemAction.SKIP_SAME_HASH,
        ):
            report.skipped += 1
            continue

        if item.action in (CopyItemAction.COPY, CopyItemAction.RENAME_COPY):
            if dry_run:
                # In dry-run mode, just count as if copied
                report.copied += 1
                report.bytes_copied += item.size
                bytes_copied_so_far += item.size
            else:
                try:
                    dest_path = Path(item.destination)
                    # Ensure destination directory exists
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    # Copy file preserving metadata (timestamps, permissions)
                    shutil.copy2(item.source, item.destination)
                    report.copied += 1
                    report.bytes_copied += item.size
                    bytes_copied_so_far += item.size
                except OSError as e:
                    report.failed += 1
                    report.errors.append((item.source, str(e)))

    # Final progress callback
    if progress_callback:
        progress_callback(
            total_items,
            total_items,
            "",
            bytes_copied_so_far,
            plan.total_bytes,
        )

    return report
