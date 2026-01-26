"""Job queue models for MediaCopier UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4


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


class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def add_job(self, name: str, items: list[str]) -> Job:
        job = Job(id=uuid4().hex, name=name, items=list(items))
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
