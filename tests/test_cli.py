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


def test_job_queue_with_rules_snapshot() -> None:
    """Test that job stores a snapshot of rules at creation time."""
    from mediacopier.core.models import CopyRules, OrganizationMode
    from mediacopier.ui.job_queue import JobQueue

    queue = JobQueue()

    # Create rules
    rules = CopyRules(
        extensiones_permitidas=[".mp3", ".flac"],
        tamano_min_mb=1.0,
        filtrar_por_tamano=True,
        usar_fuzzy=True,
        umbral_fuzzy=70.0,
    )

    # Add job with rules snapshot
    job = queue.add_job(
        "Music Job",
        ["song1", "song2"],
        rules=rules,
        organization_mode=OrganizationMode.SCATTER_BY_ARTIST,
    )

    # Verify rules snapshot
    assert job.rules_snapshot.extensiones_permitidas == [".mp3", ".flac"]
    assert job.rules_snapshot.tamano_min_mb == 1.0
    assert job.rules_snapshot.filtrar_por_tamano is True
    assert job.rules_snapshot.usar_fuzzy is True
    assert job.rules_snapshot.umbral_fuzzy == 70.0
    assert job.organization_mode == OrganizationMode.SCATTER_BY_ARTIST

    # Modify original rules - snapshot should not change
    rules.umbral_fuzzy = 90.0
    assert job.rules_snapshot.umbral_fuzzy == 70.0  # Still the original value


def test_job_to_dict_from_dict_roundtrip() -> None:
    """Test job serialization roundtrip."""
    from mediacopier.core.models import CopyRules, OrganizationMode
    from mediacopier.ui.job_queue import Job, JobQueue, JobStatus

    queue = JobQueue()

    rules = CopyRules(
        extensiones_permitidas=[".mp3"],
        dry_run=True,
        usar_fuzzy=False,
    )

    job = queue.add_job(
        "Test Job",
        ["item1", "item2"],
        rules=rules,
        organization_mode=OrganizationMode.FOLDER_PER_REQUEST,
    )
    job.status = JobStatus.RUNNING
    job.progress = 50

    # Serialize and deserialize
    data = job.to_dict()
    restored = Job.from_dict(data)

    assert restored.id == job.id
    assert restored.name == job.name
    assert restored.items == job.items
    assert restored.status == job.status
    assert restored.progress == job.progress
    assert restored.rules_snapshot.extensiones_permitidas == [".mp3"]
    assert restored.rules_snapshot.dry_run is True
    assert restored.rules_snapshot.usar_fuzzy is False
    assert restored.organization_mode == OrganizationMode.FOLDER_PER_REQUEST
