"""Tests for persistence modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mediacopier.core.models import CopyRules, OrganizationMode
from mediacopier.persistence import JobStorage, StatsStorage, UIStateStorage
from mediacopier.ui.job_queue import Job, JobStatus


class TestJobStorage:
    """Tests for JobStorage."""

    @pytest.fixture
    def temp_storage_dir(self, tmp_path: Path) -> Path:
        """Create temporary storage directory."""
        return tmp_path / "test_storage"

    @pytest.fixture
    def job_storage(self, temp_storage_dir: Path) -> JobStorage:
        """Create JobStorage instance."""
        return JobStorage(str(temp_storage_dir))

    @pytest.fixture
    def sample_jobs(self) -> list[Job]:
        """Create sample jobs for testing."""
        return [
            Job(
                id="job1",
                name="Test Job 1",
                items=["item1", "item2"],
                status=JobStatus.PENDING,
                progress=0,
                rules_snapshot=CopyRules(),
                organization_mode=OrganizationMode.SINGLE_FOLDER,
            ),
            Job(
                id="job2",
                name="Test Job 2",
                items=["item3", "item4"],
                status=JobStatus.RUNNING,
                progress=50,
                rules_snapshot=CopyRules(),
                organization_mode=OrganizationMode.SCATTER_BY_ARTIST,
            ),
        ]

    def test_storage_directory_creation(self, job_storage: JobStorage) -> None:
        """Test that storage directory is created."""
        assert job_storage.storage_dir.exists()
        assert job_storage.storage_dir.is_dir()

    def test_save_jobs(self, job_storage: JobStorage, sample_jobs: list[Job]) -> None:
        """Test saving jobs to disk."""
        result = job_storage.save_jobs(sample_jobs)
        assert result is True
        assert job_storage.jobs_file.exists()

    def test_load_jobs_empty(self, job_storage: JobStorage) -> None:
        """Test loading jobs when no file exists."""
        jobs = job_storage.load_jobs()
        assert jobs == []

    def test_save_and_load_jobs(
        self, job_storage: JobStorage, sample_jobs: list[Job]
    ) -> None:
        """Test roundtrip save and load of jobs."""
        job_storage.save_jobs(sample_jobs)
        loaded_jobs = job_storage.load_jobs()

        assert len(loaded_jobs) == len(sample_jobs)
        for original, loaded in zip(sample_jobs, loaded_jobs):
            assert loaded.id == original.id
            assert loaded.name == original.name
            assert loaded.items == original.items
            assert loaded.status == original.status
            assert loaded.progress == original.progress
            assert loaded.organization_mode == original.organization_mode

    def test_clear_jobs(self, job_storage: JobStorage, sample_jobs: list[Job]) -> None:
        """Test clearing saved jobs."""
        job_storage.save_jobs(sample_jobs)
        assert job_storage.jobs_file.exists()

        result = job_storage.clear_jobs()
        assert result is True
        assert not job_storage.jobs_file.exists()

    def test_load_jobs_corrupted_file(
        self, job_storage: JobStorage, temp_storage_dir: Path
    ) -> None:
        """Test loading jobs with corrupted file."""
        # Write invalid JSON
        job_storage.jobs_file.write_text("invalid json {")
        jobs = job_storage.load_jobs()
        assert jobs == []

    @pytest.mark.skipif(
        not hasattr(Path(), "_flavour") or "WindowsPath" not in str(type(Path())),
        reason="Windows path tests can only run on Windows"
    )
    def test_default_storage_dir_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default storage directory on Windows."""
        monkeypatch.setattr("os.name", "nt")
        monkeypatch.setenv("APPDATA", "C:\\Users\\Test\\AppData\\Roaming")

        storage = JobStorage()
        expected = Path("C:\\Users\\Test\\AppData\\Roaming\\MediaCopier")
        assert storage.storage_dir == expected

    def test_default_storage_dir_unix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default storage directory on Unix."""
        monkeypatch.setattr("os.name", "posix")
        home = Path.home()

        storage = JobStorage()
        expected = home / ".config" / "MediaCopier"
        assert storage.storage_dir == expected


class TestStatsStorage:
    """Tests for StatsStorage."""

    @pytest.fixture
    def temp_storage_dir(self, tmp_path: Path) -> Path:
        """Create temporary storage directory."""
        return tmp_path / "test_storage"

    @pytest.fixture
    def stats_storage(self, temp_storage_dir: Path) -> StatsStorage:
        """Create StatsStorage instance."""
        return StatsStorage(temp_storage_dir)

    def test_storage_directory_creation(self, stats_storage: StatsStorage) -> None:
        """Test that storage directory is created."""
        assert stats_storage.storage_dir.exists()
        assert stats_storage.storage_dir.is_dir()

    def test_save_stats(self, stats_storage: StatsStorage) -> None:
        """Test saving stats to disk."""
        stats = {"files_copied": 10, "bytes_copied": 1024}
        result = stats_storage.save_stats(stats)
        assert result is True
        assert stats_storage.stats_file.exists()

    def test_load_stats_empty(self, stats_storage: StatsStorage) -> None:
        """Test loading stats when no file exists."""
        stats = stats_storage.load_stats()
        assert stats == {"history": [], "totals": {}}

    def test_save_and_load_stats(self, stats_storage: StatsStorage) -> None:
        """Test roundtrip save and load of stats."""
        stats1 = {"files_copied": 10, "bytes_copied": 1024}
        stats2 = {"files_copied": 5, "bytes_copied": 512}

        stats_storage.save_stats(stats1)
        stats_storage.save_stats(stats2)

        loaded = stats_storage.load_stats()
        assert len(loaded["history"]) == 2
        assert loaded["history"][0]["files_copied"] == 10
        assert loaded["history"][1]["files_copied"] == 5
        # Check that timestamps were added
        assert "timestamp" in loaded["history"][0]
        assert "timestamp" in loaded["history"][1]

    def test_stats_history_limit(self, stats_storage: StatsStorage) -> None:
        """Test that history is limited to 100 entries."""
        # Save 105 stats entries
        for i in range(105):
            stats_storage.save_stats({"files_copied": i, "bytes_copied": i * 100})

        loaded = stats_storage.load_stats()
        assert len(loaded["history"]) == 100
        # Should keep the last 100
        assert loaded["history"][0]["files_copied"] == 5
        assert loaded["history"][-1]["files_copied"] == 104

    def test_get_summary(self, stats_storage: StatsStorage) -> None:
        """Test getting statistics summary."""
        stats_storage.save_stats({"files_copied": 10, "bytes_copied": 1024})
        stats_storage.save_stats({"files_copied": 5, "bytes_copied": 512})

        summary = stats_storage.get_summary()
        assert summary["total_jobs"] == 2
        assert summary["total_files_copied"] == 15
        assert summary["total_bytes_copied"] == 1536

    def test_load_stats_corrupted_file(
        self, stats_storage: StatsStorage, temp_storage_dir: Path
    ) -> None:
        """Test loading stats with corrupted file."""
        # Write invalid JSON
        stats_storage.stats_file.write_text("invalid json {")
        stats = stats_storage.load_stats()
        assert stats == {"history": [], "totals": {}}


class TestUIStateStorage:
    """Tests for UIStateStorage."""

    @pytest.fixture
    def temp_storage_dir(self, tmp_path: Path) -> Path:
        """Create temporary storage directory."""
        return tmp_path / "test_storage"

    @pytest.fixture
    def ui_state_storage(self, temp_storage_dir: Path) -> UIStateStorage:
        """Create UIStateStorage instance."""
        return UIStateStorage(temp_storage_dir)

    def test_storage_directory_creation(
        self, ui_state_storage: UIStateStorage
    ) -> None:
        """Test that storage directory is created."""
        assert ui_state_storage.storage_dir.exists()
        assert ui_state_storage.storage_dir.is_dir()

    def test_save_state(self, ui_state_storage: UIStateStorage) -> None:
        """Test saving UI state to disk."""
        state = {
            "window_geometry": "1200x800",
            "last_source_path": "/path/to/source",
        }
        result = ui_state_storage.save_state(state)
        assert result is True
        assert ui_state_storage.state_file.exists()

    def test_load_state_empty(self, ui_state_storage: UIStateStorage) -> None:
        """Test loading state when no file exists."""
        state = ui_state_storage.load_state()
        default = ui_state_storage._default_state()
        assert state == default

    def test_save_and_load_state(self, ui_state_storage: UIStateStorage) -> None:
        """Test roundtrip save and load of UI state."""
        state = {
            "window_geometry": "1200x800",
            "window_position": "+100+200",
            "last_source_path": "/path/to/source",
            "last_destination_path": "/path/to/dest",
            "auto_refresh_enabled": False,
            "selected_usb_index": 2,
        }

        ui_state_storage.save_state(state)
        loaded = ui_state_storage.load_state()

        assert loaded == state

    def test_load_state_corrupted_file(
        self, ui_state_storage: UIStateStorage, temp_storage_dir: Path
    ) -> None:
        """Test loading state with corrupted file."""
        # Write invalid JSON
        ui_state_storage.state_file.write_text("invalid json {")
        state = ui_state_storage.load_state()
        default = ui_state_storage._default_state()
        assert state == default

    def test_default_state_values(self, ui_state_storage: UIStateStorage) -> None:
        """Test default state has expected values."""
        default = ui_state_storage._default_state()
        assert default["window_geometry"] == "1200x800"
        assert default["window_position"] is None
        assert default["last_source_path"] == ""
        assert default["last_destination_path"] == ""
        assert default["auto_refresh_enabled"] is True
        assert default["selected_usb_index"] == 0
