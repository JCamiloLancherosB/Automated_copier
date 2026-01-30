"""Statistics storage persistence for MediaCopier."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StatsStorage:
    """Persistencia de estadísticas de grabación."""

    def __init__(self, storage_dir: str | Path) -> None:
        """Initialize stats storage.

        Args:
            storage_dir: Directory for storing statistics.
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.stats_file = self.storage_dir / "burning_stats.json"

    def save_stats(self, stats: dict[str, Any]) -> bool:
        """Guardar estadísticas.

        Args:
            stats: Statistics dictionary to save.

        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            # Cargar existentes y agregar
            existing = self.load_stats()
            existing["history"].append(
                {**stats, "timestamp": datetime.now().isoformat()}
            )
            # Mantener solo últimos 100 registros
            existing["history"] = existing["history"][-100:]

            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
            return True
        except (IOError, OSError) as e:
            logger.error(f"Error saving stats: {e}")
            return False

    def load_stats(self) -> dict[str, Any]:
        """Cargar estadísticas.

        Returns:
            Dictionary containing statistics history and totals.
        """
        if not self.stats_file.exists():
            return {"history": [], "totals": {}}
        try:
            with open(self.stats_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Error loading stats: {e}")
            return {"history": [], "totals": {}}

    def get_summary(self) -> dict[str, Any]:
        """Obtener resumen de estadísticas.

        Returns:
            Summary dictionary with aggregated statistics.
        """
        stats = self.load_stats()
        return {
            "total_jobs": len(stats["history"]),
            "total_files_copied": sum(h.get("files_copied", 0) for h in stats["history"]),
            "total_bytes_copied": sum(h.get("bytes_copied", 0) for h in stats["history"]),
        }
