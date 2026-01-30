"""UI state storage persistence for MediaCopier."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class UIStateStorage:
    """Persistencia del estado de la UI."""

    def __init__(self, storage_dir: str | Path) -> None:
        """Initialize UI state storage.

        Args:
            storage_dir: Directory for storing UI state.
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.storage_dir / "ui_state.json"

    def save_state(self, state: dict[str, Any]) -> bool:
        """Guardar estado de la UI.

        Args:
            state: UI state dictionary to save.

        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            return True
        except (IOError, OSError) as e:
            logger.error(f"Error saving UI state: {e}")
            return False

    def load_state(self) -> dict[str, Any]:
        """Cargar estado de la UI.

        Returns:
            Dictionary containing UI state, or default state if not found.
        """
        if not self.state_file.exists():
            return self._default_state()
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Error loading UI state: {e}")
            return self._default_state()

    def _default_state(self) -> dict[str, Any]:
        """Get default UI state.

        Returns:
            Default UI state dictionary.
        """
        return {
            "window_geometry": "1200x800",
            "window_position": None,
            "last_source_path": "",
            "last_destination_path": "",
            "auto_refresh_enabled": True,
            "selected_usb_index": 0,
        }
