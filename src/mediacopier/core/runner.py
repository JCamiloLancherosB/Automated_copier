"""Job runner for executing copy jobs with pause/resume/stop support.

This module provides the JobRunner class that executes copy jobs in a background
thread with support for:
- States: PENDING, RUNNING, PAUSED, STOP_REQUESTED, DONE, FAILED
- Checkpoint-based pause/resume (between files)
- Safe stop functionality
- Progress tracking with ETA calculation
- Thread-safe communication via event queue
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from mediacopier.core.copier import CopyItemAction, CopyPlan, CopyReport


class RunnerState(Enum):
    """State of the job runner."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOP_REQUESTED = "stop_requested"
    DONE = "done"
    FAILED = "failed"


class RunnerEventType(Enum):
    """Types of events emitted by the runner."""

    STATE_CHANGED = "state_changed"
    PROGRESS = "progress"
    FILE_STARTED = "file_started"
    FILE_COMPLETED = "file_completed"
    FILE_SKIPPED = "file_skipped"
    FILE_FAILED = "file_failed"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    ERROR = "error"


@dataclass
class RunnerEvent:
    """Event emitted by the runner for UI updates."""

    event_type: RunnerEventType
    job_id: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunnerProgress:
    """Progress information for a running job."""

    job_id: str
    current_index: int = 0
    total_files: int = 0
    current_file: str = ""
    bytes_copied: int = 0
    total_bytes: int = 0
    files_copied: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    start_time: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    progress_percent: float = 0.0
    state: RunnerState = RunnerState.PENDING

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "job_id": self.job_id,
            "current_index": self.current_index,
            "total_files": self.total_files,
            "current_file": self.current_file,
            "bytes_copied": self.bytes_copied,
            "total_bytes": self.total_bytes,
            "files_copied": self.files_copied,
            "files_skipped": self.files_skipped,
            "files_failed": self.files_failed,
            "start_time": self.start_time,
            "elapsed_seconds": self.elapsed_seconds,
            "eta_seconds": self.eta_seconds,
            "progress_percent": self.progress_percent,
            "state": self.state.value,
        }


class JobRunner:
    """Runner that executes copy jobs with pause/resume/stop support.

    The runner executes in a background thread and communicates with the UI
    via an event queue. It supports:
    - Pausing between files (checkpoint)
    - Safe stopping
    - Progress tracking with ETA
    - Thread-safe state management
    """

    def __init__(self, event_queue: Queue[RunnerEvent] | None = None) -> None:
        """Initialize the job runner.

        Args:
            event_queue: Queue for sending events to the UI. If None, events are discarded.
        """
        self._event_queue = event_queue or Queue()
        self._state = RunnerState.PENDING
        self._state_lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_job_id: str | None = None
        self._progress: RunnerProgress | None = None
        self._report: CopyReport | None = None
        # Checkpoint: index of next file to process
        self._checkpoint_index: int = 0

    @property
    def state(self) -> RunnerState:
        """Get the current runner state."""
        with self._state_lock:
            return self._state

    @property
    def progress(self) -> RunnerProgress | None:
        """Get the current progress information."""
        return self._progress

    @property
    def report(self) -> CopyReport | None:
        """Get the final copy report after job completion."""
        return self._report

    @property
    def is_running(self) -> bool:
        """Check if the runner is currently executing a job."""
        return self.state in (RunnerState.RUNNING, RunnerState.PAUSED)

    @property
    def can_edit(self) -> bool:
        """Check if the job can be edited (not running)."""
        return self.state in (
            RunnerState.PENDING,
            RunnerState.DONE,
            RunnerState.FAILED,
        )

    def _set_state(self, new_state: RunnerState) -> None:
        """Set the runner state and emit an event."""
        with self._state_lock:
            old_state = self._state
            self._state = new_state

        if old_state != new_state:
            self._emit_event(
                RunnerEventType.STATE_CHANGED,
                {"old_state": old_state.value, "new_state": new_state.value},
            )

    def _emit_event(
        self, event_type: RunnerEventType, data: dict[str, Any] | None = None
    ) -> None:
        """Emit an event to the UI queue."""
        if self._event_queue is not None and self._current_job_id:
            event = RunnerEvent(
                event_type=event_type,
                job_id=self._current_job_id,
                data=data or {},
            )
            self._event_queue.put(event)

    def start(
        self,
        job_id: str,
        plan: CopyPlan,
        dry_run: bool = False,
    ) -> bool:
        """Start executing a copy plan.

        Args:
            job_id: ID of the job being executed.
            plan: The copy plan to execute.
            dry_run: If True, simulate copying without actually copying files.

        Returns:
            True if the job was started, False if already running.
        """
        if self.is_running:
            return False

        self._current_job_id = job_id
        self._checkpoint_index = 0
        self._stop_requested.clear()
        self._pause_event.set()
        self._report = None

        self._progress = RunnerProgress(
            job_id=job_id,
            total_files=len(plan.items),
            total_bytes=plan.total_bytes,
            start_time=time.time(),
            state=RunnerState.RUNNING,
        )

        self._set_state(RunnerState.RUNNING)

        self._thread = threading.Thread(
            target=self._run_job,
            args=(plan, dry_run),
            daemon=True,
        )
        self._thread.start()
        return True

    def resume_from_checkpoint(
        self,
        job_id: str,
        plan: CopyPlan,
        checkpoint_index: int,
        dry_run: bool = False,
    ) -> bool:
        """Resume execution from a checkpoint.

        Args:
            job_id: ID of the job being executed.
            plan: The copy plan to execute.
            checkpoint_index: Index of the next file to process.
            dry_run: If True, simulate copying without actually copying files.

        Returns:
            True if the job was resumed, False if already running.
        """
        if self.is_running:
            return False

        self._current_job_id = job_id
        self._checkpoint_index = checkpoint_index
        self._stop_requested.clear()
        self._pause_event.set()
        self._report = None

        # Calculate already processed stats
        bytes_already_copied = sum(
            item.size
            for item in plan.items[:checkpoint_index]
            if item.action in (CopyItemAction.COPY, CopyItemAction.RENAME_COPY)
        )

        self._progress = RunnerProgress(
            job_id=job_id,
            current_index=checkpoint_index,
            total_files=len(plan.items),
            bytes_copied=bytes_already_copied,
            total_bytes=plan.total_bytes,
            start_time=time.time(),
            state=RunnerState.RUNNING,
        )

        self._set_state(RunnerState.RUNNING)

        self._thread = threading.Thread(
            target=self._run_job,
            args=(plan, dry_run),
            daemon=True,
        )
        self._thread.start()
        return True

    def pause(self) -> bool:
        """Request to pause the job at the next checkpoint.

        Returns:
            True if pause was requested, False if not running.
        """
        if self.state != RunnerState.RUNNING:
            return False

        self._pause_event.clear()
        self._set_state(RunnerState.PAUSED)
        return True

    def resume(self) -> bool:
        """Resume a paused job.

        Returns:
            True if resumed, False if not paused.
        """
        if self.state != RunnerState.PAUSED:
            return False

        self._set_state(RunnerState.RUNNING)
        self._pause_event.set()
        return True

    def stop(self) -> bool:
        """Request to stop the job as soon as possible.

        Returns:
            True if stop was requested, False if not running.
        """
        if not self.is_running:
            return False

        self._stop_requested.set()
        self._pause_event.set()  # Unblock if paused
        self._set_state(RunnerState.STOP_REQUESTED)
        return True

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for the job to complete.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if job completed, False if timeout.
        """
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def get_checkpoint(self) -> int:
        """Get the current checkpoint index for resume."""
        return self._checkpoint_index

    def _run_job(self, plan: CopyPlan, dry_run: bool) -> None:
        """Execute the copy plan in a background thread."""
        report = CopyReport()
        total_items = len(plan.items)
        bytes_copied_so_far = self._progress.bytes_copied if self._progress else 0
        files_copied = 0
        files_skipped = 0
        files_failed = 0

        # Count already processed items
        for i in range(self._checkpoint_index):
            item = plan.items[i]
            if item.action in (CopyItemAction.COPY, CopyItemAction.RENAME_COPY):
                files_copied += 1
            else:
                files_skipped += 1

        try:
            for i in range(self._checkpoint_index, total_items):
                # Check for stop request
                if self._stop_requested.is_set():
                    self._checkpoint_index = i
                    break

                # Wait if paused (checkpoint between files)
                if not self._pause_event.is_set():
                    self._checkpoint_index = i
                    self._update_progress(
                        i, total_items, "", bytes_copied_so_far,
                        files_copied, files_skipped, files_failed
                    )
                    self._pause_event.wait()

                    # Check stop after resuming from pause
                    if self._stop_requested.is_set():
                        break

                item = plan.items[i]

                # Emit file started event
                self._emit_event(
                    RunnerEventType.FILE_STARTED,
                    {"index": i, "source": item.source, "destination": item.destination},
                )

                # Update progress
                self._update_progress(
                    i, total_items, item.source, bytes_copied_so_far,
                    files_copied, files_skipped, files_failed
                )

                # Process the item
                if item.action in (
                    CopyItemAction.SKIP_EXISTS,
                    CopyItemAction.SKIP_SAME_SIZE,
                    CopyItemAction.SKIP_SAME_HASH,
                ):
                    report.skipped += 1
                    files_skipped += 1
                    self._emit_event(
                        RunnerEventType.FILE_SKIPPED,
                        {"index": i, "source": item.source, "reason": item.reason},
                    )
                    continue

                if item.action in (CopyItemAction.COPY, CopyItemAction.RENAME_COPY):
                    if dry_run:
                        # Dry-run: simulate copy
                        report.copied += 1
                        report.bytes_copied += item.size
                        bytes_copied_so_far += item.size
                        files_copied += 1
                        self._emit_event(
                            RunnerEventType.FILE_COMPLETED,
                            {
                                "index": i,
                                "source": item.source,
                                "destination": item.destination,
                                "dry_run": True,
                            },
                        )
                    else:
                        # Actually copy the file
                        try:
                            dest_path = Path(item.destination)
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item.source, item.destination)
                            report.copied += 1
                            report.bytes_copied += item.size
                            bytes_copied_so_far += item.size
                            files_copied += 1
                            self._emit_event(
                                RunnerEventType.FILE_COMPLETED,
                                {
                                    "index": i,
                                    "source": item.source,
                                    "destination": item.destination,
                                },
                            )
                        except OSError as e:
                            report.failed += 1
                            report.errors.append((item.source, str(e)))
                            files_failed += 1
                            self._emit_event(
                                RunnerEventType.FILE_FAILED,
                                {"index": i, "source": item.source, "error": str(e)},
                            )

                # Update checkpoint after each file
                self._checkpoint_index = i + 1

            # Final progress update
            self._update_progress(
                total_items, total_items, "", bytes_copied_so_far,
                files_copied, files_skipped, files_failed
            )

            # Determine final state
            if self._stop_requested.is_set():
                # Job was stopped
                self._report = report
                self._emit_event(
                    RunnerEventType.JOB_COMPLETED,
                    {"stopped": True, "report": report.to_dict()},
                )
                self._set_state(RunnerState.DONE)
            else:
                # Job completed normally
                self._report = report
                self._emit_event(
                    RunnerEventType.JOB_COMPLETED,
                    {"stopped": False, "report": report.to_dict()},
                )
                self._set_state(RunnerState.DONE)

        except Exception as e:
            self._report = report
            self._emit_event(
                RunnerEventType.JOB_FAILED,
                {"error": str(e), "report": report.to_dict()},
            )
            self._set_state(RunnerState.FAILED)

    def _update_progress(
        self,
        current_index: int,
        total_files: int,
        current_file: str,
        bytes_copied: int,
        files_copied: int,
        files_skipped: int,
        files_failed: int,
    ) -> None:
        """Update progress and emit progress event."""
        if self._progress is None:
            return

        now = time.time()
        elapsed = now - self._progress.start_time

        # Calculate progress percentage
        if self._progress.total_bytes > 0:
            progress_percent = (bytes_copied / self._progress.total_bytes) * 100
        elif total_files > 0:
            progress_percent = (current_index / total_files) * 100
        else:
            progress_percent = 0.0

        # Calculate ETA based on bytes copied
        eta_seconds = 0.0
        if bytes_copied > 0 and elapsed > 0:
            bytes_per_second = bytes_copied / elapsed
            remaining_bytes = self._progress.total_bytes - bytes_copied
            if bytes_per_second > 0:
                eta_seconds = remaining_bytes / bytes_per_second

        self._progress.current_index = current_index
        self._progress.current_file = current_file
        self._progress.bytes_copied = bytes_copied
        self._progress.files_copied = files_copied
        self._progress.files_skipped = files_skipped
        self._progress.files_failed = files_failed
        self._progress.elapsed_seconds = elapsed
        self._progress.eta_seconds = eta_seconds
        self._progress.progress_percent = progress_percent
        self._progress.state = self.state

        self._emit_event(
            RunnerEventType.PROGRESS,
            self._progress.to_dict(),
        )


class JobRunnerManager:
    """Manager for running multiple jobs with a single runner.

    This class provides a higher-level interface for managing job execution,
    including tracking job states and progress for multiple jobs.
    """

    def __init__(self) -> None:
        """Initialize the job runner manager."""
        self._event_queue: Queue[RunnerEvent] = Queue()
        self._runner = JobRunner(self._event_queue)
        self._job_plans: dict[str, CopyPlan] = {}
        self._job_checkpoints: dict[str, int] = {}
        self._job_dry_run: dict[str, bool] = {}
        self._lock = threading.Lock()

    @property
    def event_queue(self) -> Queue[RunnerEvent]:
        """Get the event queue for UI updates."""
        return self._event_queue

    @property
    def runner(self) -> JobRunner:
        """Get the underlying job runner."""
        return self._runner

    def get_events(self, timeout: float = 0.0) -> list[RunnerEvent]:
        """Get all pending events from the queue.

        Args:
            timeout: Maximum time to wait for first event.

        Returns:
            List of events.
        """
        events = []
        try:
            # Wait for first event
            event = self._event_queue.get(timeout=timeout)
            events.append(event)

            # Get any additional events without waiting
            while True:
                try:
                    event = self._event_queue.get_nowait()
                    events.append(event)
                except Empty:
                    break
        except Empty:
            pass
        return events

    def register_job(
        self, job_id: str, plan: CopyPlan, dry_run: bool = False
    ) -> None:
        """Register a job for execution.

        Args:
            job_id: Unique job ID.
            plan: Copy plan for the job.
            dry_run: Whether to run in dry-run mode.
        """
        with self._lock:
            self._job_plans[job_id] = plan
            self._job_checkpoints[job_id] = 0
            self._job_dry_run[job_id] = dry_run

    def unregister_job(self, job_id: str) -> None:
        """Unregister a job.

        Args:
            job_id: Job ID to unregister.
        """
        with self._lock:
            self._job_plans.pop(job_id, None)
            self._job_checkpoints.pop(job_id, None)
            self._job_dry_run.pop(job_id, None)

    def start_job(self, job_id: str) -> bool:
        """Start executing a registered job.

        Args:
            job_id: Job ID to start.

        Returns:
            True if started, False if not found or already running.
        """
        with self._lock:
            if job_id not in self._job_plans:
                return False
            plan = self._job_plans[job_id]
            dry_run = self._job_dry_run.get(job_id, False)
            checkpoint = self._job_checkpoints.get(job_id, 0)

        if checkpoint > 0:
            return self._runner.resume_from_checkpoint(
                job_id, plan, checkpoint, dry_run
            )
        return self._runner.start(job_id, plan, dry_run)

    def pause_job(self) -> bool:
        """Pause the currently running job.

        Returns:
            True if paused, False if not running.
        """
        return self._runner.pause()

    def resume_job(self) -> bool:
        """Resume the paused job.

        Returns:
            True if resumed, False if not paused.
        """
        return self._runner.resume()

    def stop_job(self) -> bool:
        """Stop the currently running job.

        Returns:
            True if stop requested, False if not running.
        """
        result = self._runner.stop()
        if result:
            # Save checkpoint for potential resume
            job_id = self._runner._current_job_id
            if job_id:
                with self._lock:
                    self._job_checkpoints[job_id] = self._runner.get_checkpoint()
        return result

    def save_checkpoint(self, job_id: str) -> None:
        """Save the current checkpoint for a job.

        Args:
            job_id: Job ID to save checkpoint for.
        """
        if self._runner._current_job_id == job_id:
            with self._lock:
                self._job_checkpoints[job_id] = self._runner.get_checkpoint()

    def get_checkpoint(self, job_id: str) -> int:
        """Get the saved checkpoint for a job.

        Args:
            job_id: Job ID to get checkpoint for.

        Returns:
            Checkpoint index, or 0 if not found.
        """
        with self._lock:
            return self._job_checkpoints.get(job_id, 0)

    def can_edit_job(self, job_id: str) -> bool:
        """Check if a job can be edited.

        Args:
            job_id: Job ID to check.

        Returns:
            True if the job can be edited.
        """
        # Can edit if runner is not running this job
        if self._runner._current_job_id != job_id:
            return True
        return self._runner.can_edit

    def get_progress(self, job_id: str) -> RunnerProgress | None:
        """Get progress for a job.

        Args:
            job_id: Job ID to get progress for.

        Returns:
            Progress information or None.
        """
        if self._runner._current_job_id == job_id:
            return self._runner.progress
        return None
