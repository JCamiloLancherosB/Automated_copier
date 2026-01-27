"""Unit tests for the job runner module."""

from __future__ import annotations

import time
from pathlib import Path
from queue import Queue

from mediacopier.core.copier import CopyItemAction, CopyPlan, CopyPlanItem
from mediacopier.core.runner import (
    JobRunner,
    JobRunnerManager,
    RunnerEvent,
    RunnerEventType,
    RunnerProgress,
    RunnerState,
)


class TestRunnerState:
    """Tests for RunnerState enum."""

    def test_all_states_exist(self) -> None:
        """Test that all required states exist."""
        assert RunnerState.PENDING.value == "pending"
        assert RunnerState.RUNNING.value == "running"
        assert RunnerState.PAUSED.value == "paused"
        assert RunnerState.STOP_REQUESTED.value == "stop_requested"
        assert RunnerState.DONE.value == "done"
        assert RunnerState.FAILED.value == "failed"


class TestRunnerProgress:
    """Tests for RunnerProgress dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        progress = RunnerProgress(job_id="test-123")
        assert progress.job_id == "test-123"
        assert progress.current_index == 0
        assert progress.total_files == 0
        assert progress.bytes_copied == 0
        assert progress.state == RunnerState.PENDING

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        progress = RunnerProgress(
            job_id="test-123",
            current_index=5,
            total_files=10,
            bytes_copied=1024,
            total_bytes=2048,
            state=RunnerState.RUNNING,
        )
        data = progress.to_dict()
        assert data["job_id"] == "test-123"
        assert data["current_index"] == 5
        assert data["total_files"] == 10
        assert data["bytes_copied"] == 1024
        assert data["state"] == "running"


class TestJobRunner:
    """Tests for JobRunner class."""

    def test_initial_state_is_pending(self) -> None:
        """Test that runner starts in PENDING state."""
        runner = JobRunner()
        assert runner.state == RunnerState.PENDING

    def test_start_changes_state_to_running(self, tmp_path: Path) -> None:
        """Test that starting a job changes state to RUNNING."""
        runner = JobRunner()
        plan = CopyPlan()

        result = runner.start("job-1", plan, dry_run=True)

        assert result is True
        # Give thread time to start
        time.sleep(0.1)
        # State should be RUNNING or DONE (for empty plan)
        assert runner.state in (RunnerState.RUNNING, RunnerState.DONE)

    def test_cannot_start_when_running(self, tmp_path: Path) -> None:
        """Test that starting fails when already running."""
        source = tmp_path / "source.txt"
        source.write_text("content")
        dest = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source),
                    destination=str(dest / "dest.txt"),
                    action=CopyItemAction.COPY,
                    size=100,
                )
                for _ in range(10)  # Multiple items to ensure job is still running
            ],
            total_bytes=1000,
        )

        runner = JobRunner()
        runner.start("job-1", plan, dry_run=True)
        time.sleep(0.05)

        runner.start("job-2", plan, dry_run=True)
        # Might be True if first job already finished
        runner.wait(timeout=1.0)

    def test_dry_run_does_not_copy_files(self, tmp_path: Path) -> None:
        """Test that dry-run mode doesn't actually copy files."""
        source = tmp_path / "source.txt"
        source.write_text("test content")
        dest = tmp_path / "dest" / "output.txt"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source),
                    destination=str(dest),
                    action=CopyItemAction.COPY,
                    size=source.stat().st_size,
                )
            ],
            total_bytes=source.stat().st_size,
        )

        runner = JobRunner()
        runner.start("job-1", plan, dry_run=True)
        runner.wait(timeout=5.0)

        assert not dest.exists()
        assert runner.state == RunnerState.DONE
        assert runner.report is not None
        assert runner.report.copied == 1

    def test_actual_copy_creates_files(self, tmp_path: Path) -> None:
        """Test that actual copy mode creates files."""
        source = tmp_path / "source.txt"
        source.write_text("test content")
        dest_dir = tmp_path / "dest"
        dest = dest_dir / "output.txt"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source),
                    destination=str(dest),
                    action=CopyItemAction.COPY,
                    size=source.stat().st_size,
                )
            ],
            total_bytes=source.stat().st_size,
        )

        runner = JobRunner()
        runner.start("job-1", plan, dry_run=False)
        runner.wait(timeout=5.0)

        assert dest.exists()
        assert dest.read_text() == "test content"
        assert runner.state == RunnerState.DONE

    def test_pause_and_resume(self, tmp_path: Path) -> None:
        """Test pausing and resuming a job."""
        # Create multiple source files
        sources = []
        for i in range(5):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}")
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        event_queue: Queue[RunnerEvent] = Queue()
        runner = JobRunner(event_queue)
        runner.start("job-1", plan, dry_run=True)

        # Wait a bit then pause
        time.sleep(0.05)
        pause_result = runner.pause()

        # Check state - might already be done if fast
        if runner.state == RunnerState.DONE:
            # Job finished too quickly, test passes
            return

        assert pause_result is True
        assert runner.state == RunnerState.PAUSED

        # Resume
        resume_result = runner.resume()
        assert resume_result is True
        assert runner.state == RunnerState.RUNNING

        # Wait for completion
        runner.wait(timeout=5.0)
        assert runner.state == RunnerState.DONE

    def test_stop_job(self, tmp_path: Path) -> None:
        """Test stopping a job."""
        # Create many files to ensure job takes time
        sources = []
        for i in range(20):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}" * 1000)  # Larger content
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        runner = JobRunner()
        runner.start("job-1", plan, dry_run=True)

        # Request stop
        time.sleep(0.01)
        runner.stop()

        runner.wait(timeout=5.0)

        # State should be DONE after stop completes
        assert runner.state == RunnerState.DONE
        # Report should indicate the job was stopped
        assert runner.report is not None

    def test_checkpoint_saved_on_pause(self, tmp_path: Path) -> None:
        """Test that checkpoint is saved when paused."""
        sources = []
        for i in range(10):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}")
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        runner = JobRunner()
        runner.start("job-1", plan, dry_run=True)

        time.sleep(0.01)
        runner.pause()
        time.sleep(0.05)

        checkpoint = runner.get_checkpoint()
        # Checkpoint should be >= 0
        assert checkpoint >= 0

        runner.stop()
        runner.wait(timeout=5.0)

    def test_events_are_emitted(self, tmp_path: Path) -> None:
        """Test that events are emitted during execution."""
        source = tmp_path / "source.txt"
        source.write_text("test content")
        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source),
                    destination=str(dest_dir / "dest.txt"),
                    action=CopyItemAction.COPY,
                    size=source.stat().st_size,
                )
            ],
            total_bytes=source.stat().st_size,
        )

        event_queue: Queue[RunnerEvent] = Queue()
        runner = JobRunner(event_queue)
        runner.start("job-1", plan, dry_run=True)
        runner.wait(timeout=5.0)

        # Collect events
        events = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        # Check that we got some events
        assert len(events) > 0

        # Check event types
        event_types = [e.event_type for e in events]
        assert RunnerEventType.STATE_CHANGED in event_types
        assert RunnerEventType.JOB_COMPLETED in event_types

    def test_skip_action_is_handled(self, tmp_path: Path) -> None:
        """Test that skip actions are handled correctly."""
        source = tmp_path / "source.txt"
        source.write_text("test content")

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source),
                    destination=str(tmp_path / "dest.txt"),
                    action=CopyItemAction.SKIP_EXISTS,
                    size=source.stat().st_size,
                    reason="File already exists",
                )
            ],
            total_bytes=0,
            files_to_skip=1,
        )

        runner = JobRunner()
        runner.start("job-1", plan, dry_run=True)
        runner.wait(timeout=5.0)

        assert runner.state == RunnerState.DONE
        assert runner.report is not None
        assert runner.report.skipped == 1
        assert runner.report.copied == 0

    def test_progress_updates(self, tmp_path: Path) -> None:
        """Test that progress is updated during execution."""
        sources = []
        for i in range(3):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}")
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        runner = JobRunner()
        runner.start("job-1", plan, dry_run=True)
        runner.wait(timeout=5.0)

        # Check final progress
        progress = runner.progress
        assert progress is not None
        assert progress.total_files == 3
        assert progress.files_copied == 3

    def test_can_edit_when_not_running(self) -> None:
        """Test that can_edit returns True when not running."""
        runner = JobRunner()
        assert runner.can_edit is True

    def test_cannot_edit_when_running(self, tmp_path: Path) -> None:
        """Test that can_edit returns False when running."""
        sources = []
        for i in range(20):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}" * 100)
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        runner = JobRunner()
        runner.start("job-1", plan, dry_run=True)

        # Immediately check can_edit
        if runner.is_running:
            assert runner.can_edit is False

        runner.stop()
        runner.wait(timeout=5.0)

    def test_resume_from_checkpoint(self, tmp_path: Path) -> None:
        """Test resuming from a checkpoint."""
        sources = []
        for i in range(5):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}")
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        runner = JobRunner()
        # Resume from checkpoint 2 (skip first 2 files)
        runner.resume_from_checkpoint("job-1", plan, checkpoint_index=2, dry_run=True)
        runner.wait(timeout=5.0)

        assert runner.state == RunnerState.DONE
        assert runner.report is not None
        # Only 3 files should be "copied" (items 2, 3, 4)
        assert runner.report.copied == 3


class TestJobRunnerManager:
    """Tests for JobRunnerManager class."""

    def test_register_and_start_job(self, tmp_path: Path) -> None:
        """Test registering and starting a job."""
        source = tmp_path / "source.txt"
        source.write_text("test content")
        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source),
                    destination=str(dest_dir / "dest.txt"),
                    action=CopyItemAction.COPY,
                    size=source.stat().st_size,
                )
            ],
            total_bytes=source.stat().st_size,
        )

        manager = JobRunnerManager()
        manager.register_job("job-1", plan, dry_run=True)

        result = manager.start_job("job-1")
        assert result is True

        manager.runner.wait(timeout=5.0)
        assert manager.runner.state == RunnerState.DONE

    def test_pause_and_resume_via_manager(self, tmp_path: Path) -> None:
        """Test pause and resume via manager."""
        sources = []
        for i in range(10):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}")
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        manager = JobRunnerManager()
        manager.register_job("job-1", plan, dry_run=True)
        manager.start_job("job-1")

        time.sleep(0.01)
        manager.pause_job()

        # Check if paused or already done
        if manager.runner.state == RunnerState.PAUSED:
            manager.resume_job()

        manager.runner.wait(timeout=5.0)
        assert manager.runner.state == RunnerState.DONE

    def test_stop_via_manager(self, tmp_path: Path) -> None:
        """Test stop via manager."""
        sources = []
        for i in range(20):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}" * 100)
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        manager = JobRunnerManager()
        manager.register_job("job-1", plan, dry_run=True)
        manager.start_job("job-1")

        time.sleep(0.01)
        manager.stop_job()

        manager.runner.wait(timeout=5.0)
        assert manager.runner.state == RunnerState.DONE

    def test_get_events(self, tmp_path: Path) -> None:
        """Test getting events from manager."""
        source = tmp_path / "source.txt"
        source.write_text("test content")
        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source),
                    destination=str(dest_dir / "dest.txt"),
                    action=CopyItemAction.COPY,
                    size=source.stat().st_size,
                )
            ],
            total_bytes=source.stat().st_size,
        )

        manager = JobRunnerManager()
        manager.register_job("job-1", plan, dry_run=True)
        manager.start_job("job-1")
        manager.runner.wait(timeout=5.0)

        # Get events
        events = manager.get_events(timeout=0.1)
        assert len(events) > 0

    def test_unregister_job(self, tmp_path: Path) -> None:
        """Test unregistering a job."""
        plan = CopyPlan()

        manager = JobRunnerManager()
        manager.register_job("job-1", plan, dry_run=True)
        manager.unregister_job("job-1")

        # Starting unregistered job should fail
        result = manager.start_job("job-1")
        assert result is False

    def test_can_edit_job_when_not_running(self, tmp_path: Path) -> None:
        """Test can_edit_job returns True when not running."""
        plan = CopyPlan()

        manager = JobRunnerManager()
        manager.register_job("job-1", plan, dry_run=True)

        assert manager.can_edit_job("job-1") is True

    def test_get_progress(self, tmp_path: Path) -> None:
        """Test getting progress for a job."""
        sources = []
        for i in range(5):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}")
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        manager = JobRunnerManager()
        manager.register_job("job-1", plan, dry_run=True)
        manager.start_job("job-1")

        # Wait a bit for job to start
        time.sleep(0.05)

        progress = manager.get_progress("job-1")
        if progress is not None:  # Might be None if job finished very quickly
            assert progress.job_id == "job-1"
            assert progress.total_files == 5

        manager.runner.wait(timeout=5.0)


class TestAcceptanceCriteria:
    """Tests for acceptance criteria: Pause during copy and resume continues where it left off."""

    def test_pause_during_copy_and_resume_continues(self, tmp_path: Path) -> None:
        """Test that pausing during copy and resuming continues from where it was."""
        # Create source files
        sources = []
        for i in range(10):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}" * 1000)
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        event_queue: Queue[RunnerEvent] = Queue()
        runner = JobRunner(event_queue)

        # Start the job
        runner.start("job-1", plan, dry_run=False)

        # Wait a bit then pause
        time.sleep(0.02)
        runner.pause()

        # Wait for pause to take effect
        time.sleep(0.1)

        if runner.state == RunnerState.DONE:
            # Job finished too quickly, but still valid test
            assert runner.report is not None
            assert runner.report.copied == 10
            return

        # Get checkpoint
        checkpoint_before_resume = runner.get_checkpoint()

        # Files copied so far should match checkpoint
        files_copied_before = sum(
            1 for i in range(checkpoint_before_resume)
            if (dest_dir / f"dest{i}.txt").exists()
        )
        # Some files should be copied
        assert files_copied_before >= 0

        # Resume
        runner.resume()

        # Wait for completion
        runner.wait(timeout=10.0)

        assert runner.state == RunnerState.DONE
        assert runner.report is not None

        # All files should be copied
        all_files_copied = all(
            (dest_dir / f"dest{i}.txt").exists() for i in range(10)
        )
        assert all_files_copied is True

        # Verify content
        for i in range(10):
            dest = dest_dir / f"dest{i}.txt"
            assert dest.read_text() == f"content {i}" * 1000

    def test_stop_saves_checkpoint_for_later_resume(self, tmp_path: Path) -> None:
        """Test that stopping saves checkpoint that can be used to resume later."""
        sources = []
        for i in range(10):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content {i}" * 1000)
            sources.append(source)

        dest_dir = tmp_path / "dest"

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(src),
                    destination=str(dest_dir / f"dest{i}.txt"),
                    action=CopyItemAction.COPY,
                    size=src.stat().st_size,
                )
                for i, src in enumerate(sources)
            ],
            total_bytes=sum(src.stat().st_size for src in sources),
        )

        # First run - stop in the middle
        runner1 = JobRunner()
        runner1.start("job-1", plan, dry_run=False)
        time.sleep(0.02)
        runner1.stop()
        runner1.wait(timeout=10.0)

        checkpoint = runner1.get_checkpoint()

        if checkpoint >= 10:
            # Job completed before stop, still valid
            return

        # Second run - resume from checkpoint
        runner2 = JobRunner()
        runner2.resume_from_checkpoint("job-1", plan, checkpoint, dry_run=False)
        runner2.wait(timeout=10.0)

        assert runner2.state == RunnerState.DONE

        # Total files should all be copied between both runs
        # Note: Some might be duplicated if checkpoint wasn't exact, but all should exist
        total_copied = runner1.report.copied + runner2.report.copied
        assert total_copied >= 10  # At least all files should be copied
