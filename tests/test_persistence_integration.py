"""Integration tests for persistence in window.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediacopier.core.models import CopyRules, OrganizationMode
from mediacopier.persistence import JobStorage
from mediacopier.ui.job_queue import Job, JobStatus


class TestWindowPersistenceIntegration:
    """Test persistence integration with window.py."""

    @pytest.fixture
    def temp_storage_dir(self, tmp_path: Path) -> Path:
        """Create temporary storage directory."""
        return tmp_path / "test_storage"

    @pytest.fixture
    def job_storage(self, temp_storage_dir: Path) -> JobStorage:
        """Create JobStorage instance."""
        return JobStorage(str(temp_storage_dir))

    @pytest.fixture
    def sample_pending_jobs(self) -> list[Job]:
        """Create sample pending jobs."""
        return [
            Job(
                id="job1",
                name="Test Pending Job",
                items=["item1", "item2"],
                status=JobStatus.PENDING,
                progress=0,
                rules_snapshot=CopyRules(),
                organization_mode=OrganizationMode.SINGLE_FOLDER,
            ),
            Job(
                id="job2",
                name="Test Running Job",
                items=["item3"],
                status=JobStatus.RUNNING,
                progress=50,
                rules_snapshot=CopyRules(),
                organization_mode=OrganizationMode.SCATTER_BY_ARTIST,
            ),
            Job(
                id="job3",
                name="Test Completed Job",
                items=["item4"],
                status=JobStatus.COMPLETED,
                progress=100,
                rules_snapshot=CopyRules(),
                organization_mode=OrganizationMode.SINGLE_FOLDER,
            ),
        ]

    def test_save_only_pending_jobs(
        self, job_storage: JobStorage, sample_pending_jobs: list[Job]
    ) -> None:
        """Test that only pending/running jobs are saved, not completed ones."""
        # Filter like window.py does
        jobs_to_save = [
            job
            for job in sample_pending_jobs
            if job.status not in (JobStatus.COMPLETED, JobStatus.ERROR)
        ]

        # Save
        result = job_storage.save_jobs(jobs_to_save)
        assert result is True

        # Load and verify
        loaded_jobs = job_storage.load_jobs()
        assert len(loaded_jobs) == 2  # Only pending and running, not completed
        assert loaded_jobs[0].status == JobStatus.PENDING
        assert loaded_jobs[1].status == JobStatus.RUNNING

    def test_restore_converts_running_to_pending(
        self, job_storage: JobStorage
    ) -> None:
        """Test that running jobs are converted to pending on restore."""
        # Save a running job
        running_job = Job(
            id="running1",
            name="Running Job",
            items=["item1"],
            status=JobStatus.RUNNING,
            progress=50,
            rules_snapshot=CopyRules(),
            organization_mode=OrganizationMode.SINGLE_FOLDER,
        )
        job_storage.save_jobs([running_job])

        # Load and convert like window.py does
        jobs = job_storage.load_jobs()
        for job in jobs:
            if job.status == JobStatus.RUNNING:
                job.status = JobStatus.PENDING

        # Verify
        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.PENDING
        assert jobs[0].progress == 50  # Progress is preserved

    def test_periodic_autosave_scenario(
        self, job_storage: JobStorage, sample_pending_jobs: list[Job]
    ) -> None:
        """Test the auto-save scenario every 60 seconds."""
        # Simulate multiple auto-saves
        for _ in range(3):
            # Update progress as jobs run
            for job in sample_pending_jobs:
                if job.status == JobStatus.RUNNING:
                    job.progress = min(100, job.progress + 20)

            # Save like window.py does
            jobs_to_save = [
                job
                for job in sample_pending_jobs
                if job.status not in (JobStatus.COMPLETED, JobStatus.ERROR)
            ]
            job_storage.save_jobs(jobs_to_save)

        # Verify last save
        loaded_jobs = job_storage.load_jobs()
        assert len(loaded_jobs) == 2
        # Running job should have progressed
        running_job = next(j for j in loaded_jobs if j.id == "job2")
        assert running_job.progress > 50

    def test_window_destroy_saves_jobs(
        self, job_storage: JobStorage, sample_pending_jobs: list[Job]
    ) -> None:
        """Test that window destroy saves pending jobs."""
        # Simulate window.destroy() logic
        jobs_to_save = [
            job
            for job in sample_pending_jobs
            if job.status not in (JobStatus.COMPLETED, JobStatus.ERROR)
        ]

        # Save
        success = job_storage.save_jobs(jobs_to_save)
        assert success is True

        # Verify file exists
        assert job_storage.jobs_file.exists()

        # Verify can be loaded
        loaded = job_storage.load_jobs()
        assert len(loaded) == 2

    def test_empty_queue_saves_empty_list(self, job_storage: JobStorage) -> None:
        """Test that empty job queue saves empty list."""
        # Save empty list
        result = job_storage.save_jobs([])
        assert result is True

        # Load should return empty list
        loaded = job_storage.load_jobs()
        assert loaded == []

    def test_restore_with_no_saved_jobs(self, job_storage: JobStorage) -> None:
        """Test restore when no jobs were saved."""
        # Ensure no file exists
        if job_storage.jobs_file.exists():
            job_storage.jobs_file.unlink()

        # Load should return empty list
        jobs = job_storage.load_jobs()
        assert jobs == []

    def test_job_queue_integration(self, job_storage: JobStorage) -> None:
        """Test integration with JobQueue class."""
        from mediacopier.ui.job_queue import JobQueue

        # Create queue and add jobs
        queue = JobQueue()
        queue.add_job("Job 1", ["item1"], CopyRules(), OrganizationMode.SINGLE_FOLDER)
        queue.add_job("Job 2", ["item2"], CopyRules(), OrganizationMode.SCATTER_BY_ARTIST)

        # Save all jobs
        jobs_to_save = [
            job
            for job in queue.list_jobs()
            if job.status not in (JobStatus.COMPLETED, JobStatus.ERROR)
        ]
        job_storage.save_jobs(jobs_to_save)

        # Load into new queue
        new_queue = JobQueue()
        loaded_jobs = job_storage.load_jobs()
        for job in loaded_jobs:
            new_queue.restore_job(job)

        # Verify
        assert len(new_queue.list_jobs()) == 2
        loaded_job_names = [j.name for j in new_queue.list_jobs()]
        assert "Job 1" in loaded_job_names
        assert "Job 2" in loaded_job_names
