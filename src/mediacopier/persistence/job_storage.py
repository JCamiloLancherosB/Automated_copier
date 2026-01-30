"""Job storage persistence for MediaCopier."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mediacopier.ui.job_queue import Job

logger = logging.getLogger(__name__)


class JobStorage:
    """Persistencia de jobs en disco."""

    def __init__(self, storage_dir: str | None = None) -> None:
        """Initialize job storage.

        Args:
            storage_dir: Optional directory for storage. If None, uses default location.
        """
        self.storage_dir = Path(storage_dir or self._get_default_dir())
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_file = self.storage_dir / "pending_jobs.json"

    def _get_default_dir(self) -> str:
        """Obtener directorio por defecto para almacenamiento."""
        if os.name == "nt":  # Windows
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            base = os.path.expanduser("~/.config")
        return os.path.join(base, "MediaCopier")

    def save_jobs(self, jobs: list[Job]) -> bool:
        """Guardar lista de jobs pendientes.

        Args:
            jobs: List of Job objects to save.

        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            data = [job.to_dict() for job in jobs]
            with open(self.jobs_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except (IOError, OSError) as e:
            logger.error(f"Error saving jobs: {e}")
            return False

    def load_jobs(self) -> list[Job]:
        """Cargar jobs guardados.

        Returns:
            List of Job objects loaded from disk, or empty list if none found.
        """
        if not self.jobs_file.exists():
            return []
        try:
            with open(self.jobs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            from mediacopier.ui.job_queue import Job

            return [Job.from_dict(d) for d in data]
        except (json.JSONDecodeError, IOError, OSError, KeyError) as e:
            logger.error(f"Error loading jobs: {e}")
            return []

    def clear_jobs(self) -> bool:
        """Clear saved jobs.

        Returns:
            True if cleared successfully, False otherwise.
        """
        try:
            if self.jobs_file.exists():
                self.jobs_file.unlink()
            return True
        except (IOError, OSError) as e:
            logger.error(f"Error clearing jobs: {e}")
            return False
