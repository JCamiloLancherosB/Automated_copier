from __future__ import annotations

from mediacopier.ui.cli import run_cli


def test_run_cli_outputs_hello_cli(capsys) -> None:
    run_cli()
    captured = capsys.readouterr()
    assert "Hello CLI" in captured.out


def test_job_queue_transitions() -> None:
    from mediacopier.ui.job_queue import JobQueue, JobStatus

    queue = JobQueue()
    job = queue.add_job("Job 1", ["a", "b"])

    assert job.status is JobStatus.PENDING

    queue.update_status(job.id, JobStatus.RUNNING)
    queue.update_progress(job.id, 75)
    updated = queue.get_job(job.id)

    assert updated.status is JobStatus.RUNNING
    assert updated.progress == 75
