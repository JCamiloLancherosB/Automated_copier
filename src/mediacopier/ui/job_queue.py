"""Job queue models for MediaCopier UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from mediacopier.core.models import CopyRules, OrganizationMode


class JobStatus(Enum):
    PENDING = "Pendiente"
    RUNNING = "En ejecución"
    PAUSED = "Pausado"
    STOPPED = "Detenido"
    COMPLETED = "Completado"
    ERROR = "Error"


class JobNotFoundError(KeyError):
    pass


@dataclass
class Job:
    id: str
    name: str
    items: list[str]
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    # Snapshot of rules at job creation time
    rules_snapshot: CopyRules = field(default_factory=CopyRules)
    organization_mode: OrganizationMode = OrganizationMode.SINGLE_FOLDER

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "items": self.items,
            "status": self.status.value,
            "progress": self.progress,
            "rules_snapshot": self.rules_snapshot.to_dict(),
            "organization_mode": self.organization_mode.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            items=data["items"],
            status=JobStatus(data.get("status", "Pendiente")),
            progress=data.get("progress", 0),
            rules_snapshot=CopyRules.from_dict(data.get("rules_snapshot", {})),
            organization_mode=OrganizationMode(
                data.get("organization_mode", "single_folder")
            ),
        )


class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def add_job(
        self,
        name: str,
        items: list[str],
        rules: CopyRules | None = None,
        organization_mode: OrganizationMode = OrganizationMode.SINGLE_FOLDER,
    ) -> Job:
        """Add a new job with a snapshot of the current rules.

        Args:
            name: Job name.
            items: List of items for the job.
            rules: Optional rules to snapshot. If None, uses default rules.
            organization_mode: Organization mode for the job.

        Returns:
            The created Job instance.
        """
        # Create a snapshot of the rules at job creation time
        rules_snapshot = CopyRules.from_dict(rules.to_dict()) if rules else CopyRules()
        job = Job(
            id=uuid4().hex,
            name=name,
            items=list(items),
            rules_snapshot=rules_snapshot,
            organization_mode=organization_mode,
        )
        self._jobs[job.id] = job
        return job

    def restore_job(self, job: Job) -> Job:
        """Restore a job (for loading from persistence).

        Args:
            job: Job to restore.

        Returns:
            The restored Job instance.
        """
        self._jobs[job.id] = job
        return job

    def list_jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise JobNotFoundError(f"Job no encontrado: {job_id}") from exc

    def update_status(self, job_id: str, status: JobStatus) -> Job:
        job = self.get_job(job_id)
        job.status = status
        return job

    def update_progress(self, job_id: str, progress: int) -> Job:
        job = self.get_job(job_id)
        job.progress = max(0, min(100, progress))
        return job

    def remove_job(self, job_id: str) -> Job:
        return self._jobs.pop(job_id)
