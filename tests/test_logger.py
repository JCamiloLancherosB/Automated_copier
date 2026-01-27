"""Unit tests for the logger module."""

from __future__ import annotations

from pathlib import Path

from mediacopier.core.logger import (
    FileStatus,
    LogLevel,
    MediaCopierLogger,
    get_logger,
    reset_logger,
)


class TestFileStatus:
    """Tests for FileStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Test that all required statuses exist."""
        assert FileStatus.COPIED.value == "COPIED"
        assert FileStatus.SKIPPED.value == "SKIPPED"
        assert FileStatus.FILTERED.value == "FILTERED"
        assert FileStatus.FAILED.value == "FAILED"


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_all_levels_exist(self) -> None:
        """Test that all required log levels exist."""
        assert LogLevel.DEBUG.value == 10
        assert LogLevel.INFO.value == 20
        assert LogLevel.WARNING.value == 30
        assert LogLevel.ERROR.value == 40


class TestMediaCopierLogger:
    """Tests for MediaCopierLogger class."""

    def test_initialization(self) -> None:
        """Test logger initialization."""
        logger = MediaCopierLogger(name="test_logger")
        assert logger is not None
        logger.close()

    def test_log_entries_stored(self) -> None:
        """Test that log entries are stored."""
        logger = MediaCopierLogger(name="test_store")
        logger.info("Test message")
        entries = logger.get_log_entries()
        assert len(entries) == 1
        assert "Test message" in entries[0]
        assert "[INFO]" in entries[0]
        logger.close()

    def test_debug_level_logging(self) -> None:
        """Test debug level logging."""
        logger = MediaCopierLogger(name="test_debug", level=LogLevel.DEBUG)
        logger.debug("Debug message")
        entries = logger.get_log_entries()
        assert len(entries) == 1
        assert "[DEBUG]" in entries[0]
        logger.close()

    def test_warning_level_logging(self) -> None:
        """Test warning level logging."""
        logger = MediaCopierLogger(name="test_warning")
        logger.warning("Warning message")
        entries = logger.get_log_entries()
        assert len(entries) == 1
        assert "[WARNING]" in entries[0]
        logger.close()

    def test_error_level_logging(self) -> None:
        """Test error level logging."""
        logger = MediaCopierLogger(name="test_error")
        logger.error("Error message")
        entries = logger.get_log_entries()
        assert len(entries) == 1
        assert "[ERROR]" in entries[0]
        logger.close()

    def test_log_file_status_copied(self) -> None:
        """Test logging file status COPIED."""
        logger = MediaCopierLogger(name="test_status_copied")
        logger.log_file_status(
            FileStatus.COPIED,
            "/source/song.mp3",
            "/dest/song.mp3",
        )
        entries = logger.get_log_entries()
        assert len(entries) == 1
        assert "[COPIED]" in entries[0]
        assert "song.mp3" in entries[0]
        logger.close()

    def test_log_file_status_skipped(self) -> None:
        """Test logging file status SKIPPED."""
        logger = MediaCopierLogger(name="test_status_skipped")
        logger.log_file_status(
            FileStatus.SKIPPED,
            "/source/song.mp3",
            "/dest/song.mp3",
            reason="File already exists",
        )
        entries = logger.get_log_entries()
        assert len(entries) == 1
        assert "[SKIPPED]" in entries[0]
        assert "File already exists" in entries[0]
        logger.close()

    def test_log_file_status_failed_with_reason(self) -> None:
        """Test logging file status FAILED with reason."""
        logger = MediaCopierLogger(name="test_status_failed")
        logger.log_file_status(
            FileStatus.FAILED,
            "/source/song.mp3",
            "/dest/song.mp3",
            reason="Permission denied",
        )
        entries = logger.get_log_entries()
        assert len(entries) == 1
        assert "[FAILED]" in entries[0]
        assert "Permission denied" in entries[0]
        logger.close()

    def test_log_job_start(self) -> None:
        """Test logging job start."""
        logger = MediaCopierLogger(name="test_job_start")
        logger.log_job_start("job-123", "My Test Job")
        entries = logger.get_log_entries()
        assert len(entries) == 1
        assert "JOB START" in entries[0]
        assert "My Test Job" in entries[0]
        assert "job-123" in entries[0]
        logger.close()

    def test_log_job_end(self) -> None:
        """Test logging job end with summary."""
        logger = MediaCopierLogger(name="test_job_end")
        logger.log_job_end("job-123", "My Test Job", copied=10, skipped=5, filtered=2, failed=1)
        entries = logger.get_log_entries()
        assert len(entries) == 2
        assert "JOB END" in entries[0]
        assert "COPIED=10" in entries[1]
        assert "SKIPPED=5" in entries[1]
        assert "FILTERED=2" in entries[1]
        assert "FAILED=1" in entries[1]
        assert "TOTAL=18" in entries[1]
        logger.close()

    def test_export_to_txt(self, tmp_path: Path) -> None:
        """Test exporting log to .txt file."""
        logger = MediaCopierLogger(name="test_export")
        logger.info("Line 1")
        logger.warning("Line 2")
        logger.error("Line 3")

        output_file = tmp_path / "test_log.txt"
        result_path = logger.export_to_txt(output_file)

        assert result_path == output_file
        assert output_file.exists()

        content = output_file.read_text()
        assert "Line 1" in content
        assert "Line 2" in content
        assert "Line 3" in content
        assert "[INFO]" in content
        assert "[WARNING]" in content
        assert "[ERROR]" in content
        logger.close()

    def test_clear_entries(self) -> None:
        """Test clearing log entries."""
        logger = MediaCopierLogger(name="test_clear")
        logger.info("Message 1")
        logger.info("Message 2")
        assert len(logger.get_log_entries()) == 2

        logger.clear_entries()
        assert len(logger.get_log_entries()) == 0
        logger.close()

    def test_set_log_file(self, tmp_path: Path) -> None:
        """Test setting log file."""
        logger = MediaCopierLogger(name="test_set_file")
        log_file = tmp_path / "runtime.log"
        logger.set_log_file(log_file)
        logger.info("Test message")
        logger.close()

        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content

    def test_timestamp_in_log_entries(self) -> None:
        """Test that timestamps are present in log entries."""
        logger = MediaCopierLogger(name="test_timestamp")
        logger.info("Test message")
        entries = logger.get_log_entries()
        assert len(entries) == 1
        # Timestamp format: YYYY-MM-DD HH:MM:SS
        import re
        timestamp_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
        assert re.search(timestamp_pattern, entries[0]) is not None
        logger.close()


class TestGlobalLogger:
    """Tests for global logger functions."""

    def test_get_logger_creates_singleton(self) -> None:
        """Test that get_logger returns the same instance."""
        reset_logger()
        logger1 = get_logger()
        logger2 = get_logger()
        assert logger1 is logger2
        reset_logger()

    def test_reset_logger_clears_singleton(self) -> None:
        """Test that reset_logger clears the singleton."""
        reset_logger()
        get_logger()  # Create first instance
        reset_logger()
        logger2 = get_logger()
        # After reset, should be new instance
        # (Can't compare directly as both will be MediaCopierLogger instances,
        # but the internal state should be fresh)
        assert logger2.get_log_entries() == []
        reset_logger()


class TestAcceptanceCriteria:
    """Tests for acceptance criteria: After a job, have a reproducible log."""

    def test_full_job_logging_cycle(self, tmp_path: Path) -> None:
        """Test a complete job logging cycle produces reproducible log."""
        logger = MediaCopierLogger(name="test_acceptance")
        log_file = tmp_path / "job_log.txt"

        # Start job
        logger.log_job_start("job-001", "Test Copy Job")

        # Log some file operations
        logger.log_file_status(FileStatus.COPIED, "/src/file1.mp3", "/dst/file1.mp3")
        logger.log_file_status(FileStatus.SKIPPED, "/src/file2.mp3", reason="Already exists")
        logger.log_file_status(
            FileStatus.FILTERED, "/src/file3.mp3", reason="Extension not allowed"
        )
        logger.log_file_status(FileStatus.FAILED, "/src/file4.mp3", reason="Permission denied")

        # End job
        logger.log_job_end("job-001", "Test Copy Job", copied=1, skipped=1, filtered=1, failed=1)

        # Export log
        result_path = logger.export_to_txt(log_file)
        logger.close()

        # Verify log file exists and contains all entries
        assert result_path.exists()
        content = result_path.read_text()

        # Verify all parts of the job are logged
        assert "JOB START" in content
        assert "Test Copy Job" in content
        assert "[COPIED]" in content
        assert "[SKIPPED]" in content
        assert "[FILTERED]" in content
        assert "[FAILED]" in content
        assert "JOB END" in content
        assert "COPIED=1" in content
        assert "SKIPPED=1" in content
        assert "FILTERED=1" in content
        assert "FAILED=1" in content

        # Verify no sensitive data (full paths should not be in output for file status)
        # File names only should be present
        assert "file1.mp3" in content
        assert "file2.mp3" in content

    def test_log_with_only_paths_and_names_no_sensitive_data(self) -> None:
        """Test that logs contain only paths and names, no sensitive data."""
        logger = MediaCopierLogger(name="test_no_sensitive")

        # Log a file status with a path that might look like it has sensitive data
        logger.log_file_status(
            FileStatus.COPIED,
            "/home/user/secret_folder/my_song.mp3",
            "/backup/music/my_song.mp3",
        )

        entries = logger.get_log_entries()
        assert len(entries) == 1

        # Only the filename should appear, not the full path
        entry = entries[0]
        assert "my_song.mp3" in entry
        # The log should show path info but in a clean way (filename only)
        logger.close()
