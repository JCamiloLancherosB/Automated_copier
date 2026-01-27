"""Logging module for MediaCopier with timestamps and levels.

This module provides:
- Timestamped logging with configurable levels
- Log export to .txt files
- File status tracking (COPIED, SKIPPED, FILTERED, FAILED)
- Clean logging with paths and names only (no sensitive data)
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from pathlib import Path


class FileStatus(Enum):
    """Status of a file during copy operation."""

    COPIED = "COPIED"
    SKIPPED = "SKIPPED"
    FILTERED = "FILTERED"
    FAILED = "FAILED"


class LogLevel(Enum):
    """Log levels for MediaCopier."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR


class MediaCopierLogger:
    """Logger for MediaCopier with timestamp and level support.

    This logger provides:
    - Timestamped log entries with configurable levels
    - Export logs to .txt files
    - Safe logging (only paths and names, no sensitive data)
    """

    # Format for log timestamps
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

    # Log message format
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

    # Maximum log entries to keep in memory (to avoid memory issues)
    MAX_LOG_ENTRIES = 100000

    def __init__(
        self,
        name: str = "mediacopier",
        level: LogLevel = LogLevel.INFO,
        log_file: str | Path | None = None,
        max_entries: int | None = None,
    ) -> None:
        """Initialize the logger.

        Args:
            name: Logger name identifier.
            level: Minimum log level to capture.
            log_file: Optional path to write logs to a file.
            max_entries: Maximum entries to keep in memory. Defaults to MAX_LOG_ENTRIES.
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level.value)
        self._logger.handlers.clear()  # Clear existing handlers

        # Create formatter
        formatter = logging.Formatter(
            self.LOG_FORMAT,
            datefmt=self.TIMESTAMP_FORMAT,
        )

        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        # Add file handler if log_file specified
        self._log_file_path: Path | None = None
        self._file_handler: logging.FileHandler | None = None
        if log_file:
            self.set_log_file(log_file)

        # Track log entries for export with configurable limit
        self._log_entries: list[str] = []
        self._max_entries = max_entries if max_entries is not None else self.MAX_LOG_ENTRIES

    def set_log_file(self, log_file: str | Path) -> None:
        """Set or change the log file path.

        Args:
            log_file: Path to the log file.
        """
        # Remove existing file handler
        if self._file_handler:
            self._logger.removeHandler(self._file_handler)
            self._file_handler.close()

        self._log_file_path = Path(log_file)
        self._log_file_path.parent.mkdir(parents=True, exist_ok=True)

        self._file_handler = logging.FileHandler(
            self._log_file_path, mode="a", encoding="utf-8"
        )
        formatter = logging.Formatter(
            self.LOG_FORMAT,
            datefmt=self.TIMESTAMP_FORMAT,
        )
        self._file_handler.setFormatter(formatter)
        self._logger.addHandler(self._file_handler)

    def _format_entry(self, level: str, message: str) -> str:
        """Format a log entry with timestamp.

        Args:
            level: Log level string.
            message: Log message.

        Returns:
            Formatted log entry string.
        """
        timestamp = datetime.now().strftime(self.TIMESTAMP_FORMAT)
        return f"{timestamp} [{level}] {message}"

    def _log(self, level: LogLevel, message: str) -> None:
        """Log a message and store it for export.

        Args:
            level: Log level.
            message: Message to log.
        """
        entry = self._format_entry(level.name, message)
        self._log_entries.append(entry)

        # Enforce max entries limit to prevent memory issues
        if len(self._log_entries) > self._max_entries:
            # Remove oldest entries (keep last max_entries)
            self._log_entries = self._log_entries[-self._max_entries:]

        self._logger.log(level.value, message)

    def debug(self, message: str) -> None:
        """Log a debug message.

        Args:
            message: Message to log.
        """
        self._log(LogLevel.DEBUG, message)

    def info(self, message: str) -> None:
        """Log an info message.

        Args:
            message: Message to log.
        """
        self._log(LogLevel.INFO, message)

    def warning(self, message: str) -> None:
        """Log a warning message.

        Args:
            message: Message to log.
        """
        self._log(LogLevel.WARNING, message)

    def error(self, message: str) -> None:
        """Log an error message.

        Args:
            message: Message to log.
        """
        self._log(LogLevel.ERROR, message)

    def log_file_status(
        self,
        status: FileStatus,
        source_path: str,
        dest_path: str | None = None,
        reason: str = "",
    ) -> None:
        """Log file operation status with safe path information.

        Args:
            status: File operation status.
            source_path: Source file path.
            dest_path: Destination file path (optional).
            reason: Reason for the status (especially for failures).
        """
        # Extract only file names for cleaner logs
        source_name = Path(source_path).name
        dest_info = f" -> {Path(dest_path).name}" if dest_path else ""
        reason_info = f" ({reason})" if reason else ""

        message = f"[{status.value}] {source_name}{dest_info}{reason_info}"

        # Use appropriate log level based on status
        if status == FileStatus.FAILED:
            self.error(message)
        elif status == FileStatus.SKIPPED or status == FileStatus.FILTERED:
            self.info(message)
        else:  # COPIED
            self.info(message)

    def log_job_start(self, job_id: str, job_name: str) -> None:
        """Log the start of a copy job.

        Args:
            job_id: Unique job identifier.
            job_name: Human-readable job name.
        """
        self.info(f"=== JOB START: {job_name} (ID: {job_id}) ===")

    def log_job_end(
        self,
        job_id: str,
        job_name: str,
        copied: int,
        skipped: int,
        filtered: int,
        failed: int,
    ) -> None:
        """Log the end of a copy job with summary.

        Args:
            job_id: Unique job identifier.
            job_name: Human-readable job name.
            copied: Number of files copied.
            skipped: Number of files skipped.
            filtered: Number of files filtered out.
            failed: Number of files that failed.
        """
        total = copied + skipped + filtered + failed
        self.info(f"=== JOB END: {job_name} (ID: {job_id}) ===")
        summary = f"COPIED={copied}, SKIPPED={skipped}, FILTERED={filtered}, FAILED={failed}"
        self.info(f"Summary: {summary}, TOTAL={total}")

    def export_to_txt(self, output_path: str | Path) -> Path:
        """Export all log entries to a .txt file.

        Args:
            output_path: Path for the output file.

        Returns:
            Path where the log was saved.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(self._log_entries))
            if self._log_entries:
                f.write("\n")

        return path

    def get_log_entries(self) -> list[str]:
        """Get all stored log entries.

        Returns:
            List of formatted log entries.
        """
        return self._log_entries.copy()

    def clear_entries(self) -> None:
        """Clear stored log entries."""
        self._log_entries.clear()

    def close(self) -> None:
        """Close the logger and release resources."""
        if self._file_handler:
            self._logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None


# Global logger instance for convenience
_global_logger: MediaCopierLogger | None = None


def get_logger(
    name: str = "mediacopier",
    level: LogLevel = LogLevel.INFO,
    log_file: str | Path | None = None,
) -> MediaCopierLogger:
    """Get or create the global logger instance.

    Args:
        name: Logger name identifier.
        level: Minimum log level to capture.
        log_file: Optional path to write logs to a file.

    Returns:
        MediaCopierLogger instance.
    """
    global _global_logger
    if _global_logger is None:
        _global_logger = MediaCopierLogger(name=name, level=level, log_file=log_file)
    return _global_logger


def reset_logger() -> None:
    """Reset the global logger instance."""
    global _global_logger
    if _global_logger:
        _global_logger.close()
    _global_logger = None
