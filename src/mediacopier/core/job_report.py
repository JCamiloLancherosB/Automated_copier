"""Job report module for MediaCopier.

This module provides:
- JobReport dataclass for storing job execution details
- Export report to JSON
- Summary generation by category (COPIED/SKIPPED/FILTERED/FAILED)
- File operation details with clear reasons for failures
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from mediacopier.core.copier import CopyItemAction, CopyPlan, CopyReport
from mediacopier.core.matcher import MatchResult


class FileOperationStatus(Enum):
    """Status of a file operation in the report.

    - COPIED: File was successfully copied
    - SKIPPED: File was skipped due to collision (exists, same size, same hash)
    - FILTERED: File was filtered out by rules (extension, size, duration, excluded words)
                Note: FILTERED is used when files don't make it into the copy plan.
                This typically happens during matching/indexing, not during copy execution.
    - FAILED: File copy failed due to an error
    """

    COPIED = "COPIED"
    SKIPPED = "SKIPPED"
    FILTERED = "FILTERED"
    FAILED = "FAILED"


@dataclass
class FileOperation:
    """Details of a single file operation.

    Attributes:
        source_path: Source file path.
        source_name: Source file name.
        dest_path: Destination file path (if applicable).
        dest_name: Destination file name (if applicable).
        status: Status of the operation.
        reason: Reason for the status (especially for non-COPIED).
        size_bytes: File size in bytes.
    """

    source_path: str
    source_name: str
    dest_path: str | None
    dest_name: str | None
    status: FileOperationStatus
    reason: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source_path": self.source_path,
            "source_name": self.source_name,
            "dest_path": self.dest_path,
            "dest_name": self.dest_name,
            "status": self.status.value,
            "reason": self.reason,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileOperation:
        """Deserialize from dictionary."""
        return cls(
            source_path=data["source_path"],
            source_name=data["source_name"],
            dest_path=data.get("dest_path"),
            dest_name=data.get("dest_name"),
            status=FileOperationStatus(data["status"]),
            reason=data.get("reason", ""),
            size_bytes=data.get("size_bytes", 0),
        )


@dataclass
class MatchInfo:
    """Information about a match for the report.

    Attributes:
        requested_text: Original requested item text.
        requested_type: Type of the requested item.
        matched_file: Path of the matched file (if found).
        matched_name: Name of the matched file (if found).
        match_score: Match score (0-100).
        match_found: Whether a match was found.
    """

    requested_text: str
    requested_type: str
    matched_file: str | None
    matched_name: str | None
    match_score: float
    match_found: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "requested_text": self.requested_text,
            "requested_type": self.requested_type,
            "matched_file": self.matched_file,
            "matched_name": self.matched_name,
            "match_score": self.match_score,
            "match_found": self.match_found,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchInfo:
        """Deserialize from dictionary."""
        return cls(
            requested_text=data["requested_text"],
            requested_type=data["requested_type"],
            matched_file=data.get("matched_file"),
            matched_name=data.get("matched_name"),
            match_score=data.get("match_score", 0.0),
            match_found=data.get("match_found", False),
        )


@dataclass
class CategorySummary:
    """Summary of operations by category.

    Attributes:
        copied: Number of files copied.
        skipped: Number of files skipped.
        filtered: Number of files filtered out.
        failed: Number of files that failed.
    """

    copied: int = 0
    skipped: int = 0
    filtered: int = 0
    failed: int = 0

    @property
    def total(self) -> int:
        """Get total number of files processed."""
        return self.copied + self.skipped + self.filtered + self.failed

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "COPIED": self.copied,
            "SKIPPED": self.skipped,
            "FILTERED": self.filtered,
            "FAILED": self.failed,
            "TOTAL": self.total,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CategorySummary:
        """Deserialize from dictionary."""
        return cls(
            copied=data.get("COPIED", 0),
            skipped=data.get("SKIPPED", 0),
            filtered=data.get("FILTERED", 0),
            failed=data.get("FAILED", 0),
        )


@dataclass
class JobReport:
    """Complete report for a copy job.

    Attributes:
        job_id: Unique job identifier.
        job_name: Human-readable job name.
        start_time: Job start timestamp (ISO format).
        end_time: Job end timestamp (ISO format).
        sources: List of source directories.
        destination: Destination directory.
        organization_mode: File organization mode used.
        dry_run: Whether this was a dry run.
        matches: List of match information.
        operations: List of file operations.
        summary: Summary by category.
        total_bytes_copied: Total bytes copied.
        errors: List of error details.
    """

    job_id: str
    job_name: str
    start_time: str = ""
    end_time: str = ""
    sources: list[str] = field(default_factory=list)
    destination: str = ""
    organization_mode: str = ""
    dry_run: bool = False
    matches: list[MatchInfo] = field(default_factory=list)
    operations: list[FileOperation] = field(default_factory=list)
    summary: CategorySummary = field(default_factory=CategorySummary)
    total_bytes_copied: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "job_id": self.job_id,
            "job_name": self.job_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "sources": self.sources,
            "destination": self.destination,
            "organization_mode": self.organization_mode,
            "dry_run": self.dry_run,
            "matches": [m.to_dict() for m in self.matches],
            "operations": [op.to_dict() for op in self.operations],
            "summary": self.summary.to_dict(),
            "total_bytes_copied": self.total_bytes_copied,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobReport:
        """Deserialize from dictionary."""
        return cls(
            job_id=data["job_id"],
            job_name=data["job_name"],
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time", ""),
            sources=data.get("sources", []),
            destination=data.get("destination", ""),
            organization_mode=data.get("organization_mode", ""),
            dry_run=data.get("dry_run", False),
            matches=[MatchInfo.from_dict(m) for m in data.get("matches", [])],
            operations=[FileOperation.from_dict(op) for op in data.get("operations", [])],
            summary=CategorySummary.from_dict(data.get("summary", {})),
            total_bytes_copied=data.get("total_bytes_copied", 0),
            errors=data.get("errors", []),
        )

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string.

        Args:
            indent: Indentation level for pretty printing.

        Returns:
            JSON string representation.
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> JobReport:
        """Deserialize from JSON string.

        Args:
            json_str: JSON string representation.

        Returns:
            JobReport instance.
        """
        return cls.from_dict(json.loads(json_str))

    def export_to_json(self, output_path: str | Path) -> Path:
        """Export report to a JSON file.

        Args:
            output_path: Path for the output file.

        Returns:
            Path where the report was saved.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load_from_json(cls, file_path: str | Path) -> JobReport | None:
        """Load report from a JSON file.

        Args:
            file_path: Path to the JSON file.

        Returns:
            JobReport instance or None if file doesn't exist.
        """
        path = Path(file_path)
        if not path.exists():
            return None
        try:
            return cls.from_json(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return None

    def add_match(self, match_result: MatchResult) -> None:
        """Add a match result to the report.

        Args:
            match_result: MatchResult from the matcher.
        """
        best_match = match_result.best_match
        matched_file = best_match.media_file.path if best_match else None
        matched_name = best_match.media_file.nombre_base if best_match else None
        match_score = best_match.score if best_match else 0.0

        match_info = MatchInfo(
            requested_text=match_result.requested_item.texto_original,
            requested_type=match_result.requested_item.tipo.value,
            matched_file=matched_file,
            matched_name=matched_name,
            match_score=match_score,
            match_found=match_result.match_found,
        )
        self.matches.append(match_info)

    def add_operation(
        self,
        source_path: str,
        dest_path: str | None,
        status: FileOperationStatus,
        reason: str = "",
        size_bytes: int = 0,
    ) -> None:
        """Add a file operation to the report.

        Args:
            source_path: Source file path.
            dest_path: Destination file path (optional).
            status: Status of the operation.
            reason: Reason for the status.
            size_bytes: File size in bytes.
        """
        source_name = Path(source_path).name
        dest_name = Path(dest_path).name if dest_path else None

        operation = FileOperation(
            source_path=source_path,
            source_name=source_name,
            dest_path=dest_path,
            dest_name=dest_name,
            status=status,
            reason=reason,
            size_bytes=size_bytes,
        )
        self.operations.append(operation)

        # Update summary
        if status == FileOperationStatus.COPIED:
            self.summary.copied += 1
            self.total_bytes_copied += size_bytes
        elif status == FileOperationStatus.SKIPPED:
            self.summary.skipped += 1
        elif status == FileOperationStatus.FILTERED:
            self.summary.filtered += 1
        elif status == FileOperationStatus.FAILED:
            self.summary.failed += 1

    def add_error(self, source_path: str, error_message: str) -> None:
        """Add an error to the report.

        Args:
            source_path: Path of the file that failed.
            error_message: Error message (no sensitive data).
        """
        self.errors.append({
            "source_path": source_path,
            "source_name": Path(source_path).name,
            "reason": error_message,
        })

    def add_filtered_file(self, source_path: str, reason: str, size_bytes: int = 0) -> None:
        """Add a filtered file to the report.

        This is a convenience method for reporting files that were filtered out
        during matching/indexing (before the copy plan was created).

        Args:
            source_path: Path of the file that was filtered.
            reason: Reason for filtering (e.g., "Extension not allowed", "Size too small").
            size_bytes: File size in bytes.
        """
        self.add_operation(
            source_path=source_path,
            dest_path=None,
            status=FileOperationStatus.FILTERED,
            reason=reason,
            size_bytes=size_bytes,
        )

    def set_start_time(self) -> None:
        """Set the start time to now."""
        self.start_time = datetime.now().isoformat()

    def set_end_time(self) -> None:
        """Set the end time to now."""
        self.end_time = datetime.now().isoformat()

    def get_summary_text(self) -> str:
        """Get a human-readable summary of the job.

        Returns:
            Formatted summary string.
        """
        lines = [
            f"Job Report: {self.job_name} (ID: {self.job_id})",
            f"Start: {self.start_time}",
            f"End: {self.end_time}",
            f"Dry Run: {self.dry_run}",
            "",
            "Summary by Category:",
            f"  COPIED:   {self.summary.copied}",
            f"  SKIPPED:  {self.summary.skipped}",
            f"  FILTERED: {self.summary.filtered}",
            f"  FAILED:   {self.summary.failed}",
            f"  TOTAL:    {self.summary.total}",
            "",
            f"Total bytes copied: {self.total_bytes_copied:,}",
        ]

        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for error in self.errors:
                lines.append(f"  - {error['source_name']}: {error['reason']}")

        return "\n".join(lines)


def create_job_report_from_plan_and_result(
    job_id: str,
    job_name: str,
    plan: CopyPlan,
    copy_report: CopyReport,
    matches: list[MatchResult] | None = None,
    sources: list[str] | None = None,
    destination: str = "",
    organization_mode: str = "",
    dry_run: bool = False,
    start_time: str = "",
    end_time: str = "",
) -> JobReport:
    """Create a JobReport from a CopyPlan and CopyReport.

    This is a convenience function to build a complete JobReport from
    the results of a copy operation.

    Args:
        job_id: Unique job identifier.
        job_name: Human-readable job name.
        plan: The copy plan that was executed.
        copy_report: The result of executing the plan.
        matches: Optional list of match results.
        sources: List of source directories.
        destination: Destination directory.
        organization_mode: Organization mode used.
        dry_run: Whether this was a dry run.
        start_time: Start time in ISO format.
        end_time: End time in ISO format.

    Returns:
        Complete JobReport.
    """
    report = JobReport(
        job_id=job_id,
        job_name=job_name,
        start_time=start_time,
        end_time=end_time or datetime.now().isoformat(),
        sources=sources or [],
        destination=destination,
        organization_mode=organization_mode,
        dry_run=dry_run,
    )

    # Add matches
    if matches:
        for match_result in matches:
            report.add_match(match_result)

    # Add operations from plan items
    # Create a dict of errors for quick lookup
    error_dict = {src: msg for src, msg in copy_report.errors}

    for item in plan.items:
        # Determine status based on action and errors
        if item.source in error_dict:
            status = FileOperationStatus.FAILED
            reason = error_dict[item.source]
        elif item.action == CopyItemAction.COPY:
            status = FileOperationStatus.COPIED
            reason = item.reason or ""
        elif item.action == CopyItemAction.RENAME_COPY:
            status = FileOperationStatus.COPIED
            reason = item.reason or "renamed due to collision"
        elif item.action == CopyItemAction.SKIP_EXISTS:
            status = FileOperationStatus.SKIPPED
            reason = item.reason or "File already exists"
        elif item.action == CopyItemAction.SKIP_SAME_SIZE:
            status = FileOperationStatus.SKIPPED
            reason = item.reason or "Same size as existing file"
        elif item.action == CopyItemAction.SKIP_SAME_HASH:
            status = FileOperationStatus.SKIPPED
            reason = item.reason or "Same hash as existing file"
        else:
            # Unknown action - log as warning but don't fail
            # This could happen if new actions are added
            status = FileOperationStatus.SKIPPED
            reason = item.reason or f"Unknown action: {item.action.value}"

        report.add_operation(
            source_path=item.source,
            dest_path=item.destination,
            status=status,
            reason=reason,
            size_bytes=item.size if status == FileOperationStatus.COPIED else 0,
        )

    # Add errors
    for source, message in copy_report.errors:
        report.add_error(source, message)

    return report
