"""Core data models for MediaCopier."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


class OrganizationMode(Enum):
    """Organization modes for file copying."""

    SINGLE_FOLDER = "single_folder"
    SCATTER_BY_ARTIST = "scatter_by_artist"
    SCATTER_BY_GENRE = "scatter_by_genre"
    FOLDER_PER_REQUEST = "folder_per_request"
    KEEP_RELATIVE = "keep_relative"


class RequestedItemType(Enum):
    """Types of items that can be requested for copying."""

    SONG = "song"
    MOVIE = "movie"
    GENRE = "genre"
    ARTIST = "artist"
    FOLDER = "folder"


class CopyJobStatus(Enum):
    """Status of a copy job."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


@dataclass
class RequestedItem:
    """Represents an item requested for copying."""

    tipo: RequestedItemType
    texto_original: str
    texto_normalizado: str = ""

    def __post_init__(self) -> None:
        if not self.texto_normalizado:
            self.texto_normalizado = self._normalize(self.texto_original)

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for comparison."""
        return text.strip().lower()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "tipo": self.tipo.value,
            "texto_original": self.texto_original,
            "texto_normalizado": self.texto_normalizado,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequestedItem:
        """Deserialize from dictionary."""
        return cls(
            tipo=RequestedItemType(data["tipo"]),
            texto_original=data["texto_original"],
            texto_normalizado=data.get("texto_normalizado", ""),
        )


@dataclass
class CopyRules:
    """Rules that govern file copying behavior."""

    extensiones_permitidas: list[str] = field(default_factory=list)
    tamano_min_mb: float = 0.0
    duracion_min_seg: float = 0.0
    incluir_subcarpetas: bool = True
    excluir_palabras: list[str] = field(default_factory=list)
    organizar_por_genero: bool = False
    # New configurable options
    filtrar_por_tamano: bool = False
    filtrar_por_duracion: bool = False
    solo_extensiones_seleccionadas: bool = False
    dry_run: bool = False
    evitar_duplicados: bool = True
    usar_fuzzy: bool = True
    umbral_fuzzy: float = 60.0

    def validate(self) -> None:
        """Validate the rules configuration.

        Raises:
            ValidationError: If any rule is invalid.
        """
        if self.tamano_min_mb < 0:
            raise ValidationError("tamano_min_mb no puede ser negativo")
        if self.duracion_min_seg < 0:
            raise ValidationError("duracion_min_seg no puede ser negativa")
        if self.umbral_fuzzy < 0 or self.umbral_fuzzy > 100:
            raise ValidationError("umbral_fuzzy debe estar entre 0 y 100")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "extensiones_permitidas": self.extensiones_permitidas,
            "tamano_min_mb": self.tamano_min_mb,
            "duracion_min_seg": self.duracion_min_seg,
            "incluir_subcarpetas": self.incluir_subcarpetas,
            "excluir_palabras": self.excluir_palabras,
            "organizar_por_genero": self.organizar_por_genero,
            "filtrar_por_tamano": self.filtrar_por_tamano,
            "filtrar_por_duracion": self.filtrar_por_duracion,
            "solo_extensiones_seleccionadas": self.solo_extensiones_seleccionadas,
            "dry_run": self.dry_run,
            "evitar_duplicados": self.evitar_duplicados,
            "usar_fuzzy": self.usar_fuzzy,
            "umbral_fuzzy": self.umbral_fuzzy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CopyRules:
        """Deserialize from dictionary."""
        return cls(
            extensiones_permitidas=data.get("extensiones_permitidas", []),
            tamano_min_mb=data.get("tamano_min_mb", 0.0),
            duracion_min_seg=data.get("duracion_min_seg", 0.0),
            incluir_subcarpetas=data.get("incluir_subcarpetas", True),
            excluir_palabras=data.get("excluir_palabras", []),
            organizar_por_genero=data.get("organizar_por_genero", False),
            filtrar_por_tamano=data.get("filtrar_por_tamano", False),
            filtrar_por_duracion=data.get("filtrar_por_duracion", False),
            solo_extensiones_seleccionadas=data.get("solo_extensiones_seleccionadas", False),
            dry_run=data.get("dry_run", False),
            evitar_duplicados=data.get("evitar_duplicados", True),
            usar_fuzzy=data.get("usar_fuzzy", True),
            umbral_fuzzy=data.get("umbral_fuzzy", 60.0),
        )


@dataclass
class CopyStats:
    """Statistics for a copy job."""

    archivos_encontrados: int = 0
    archivos_copiados: int = 0
    archivos_omitidos: int = 0
    archivos_error: int = 0
    bytes_copiados: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "archivos_encontrados": self.archivos_encontrados,
            "archivos_copiados": self.archivos_copiados,
            "archivos_omitidos": self.archivos_omitidos,
            "archivos_error": self.archivos_error,
            "bytes_copiados": self.bytes_copiados,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CopyStats:
        """Deserialize from dictionary."""
        return cls(
            archivos_encontrados=data.get("archivos_encontrados", 0),
            archivos_copiados=data.get("archivos_copiados", 0),
            archivos_omitidos=data.get("archivos_omitidos", 0),
            archivos_error=data.get("archivos_error", 0),
            bytes_copiados=data.get("bytes_copiados", 0),
        )


@dataclass
class CopyJob:
    """Represents a copy job in the queue."""

    nombre: str
    origenes: list[str]
    destino: str
    modo_organizacion: OrganizationMode = OrganizationMode.SINGLE_FOLDER
    lista_items: list[RequestedItem] = field(default_factory=list)
    reglas: CopyRules = field(default_factory=CopyRules)
    estado: CopyJobStatus = CopyJobStatus.PENDING
    stats: CopyStats = field(default_factory=CopyStats)
    id: str = field(default_factory=lambda: uuid4().hex)

    def validate(self, check_origen_exists: bool = False) -> None:
        """Validate the job configuration.

        Args:
            check_origen_exists: If True, verifies that origin paths exist on disk.

        Raises:
            ValidationError: If validation fails.
        """
        if not self.destino:
            raise ValidationError("El destino no puede estar vacío")

        if not self.origenes:
            raise ValidationError("Debe especificar al menos un origen")

        if check_origen_exists:
            for origen in self.origenes:
                if not os.path.exists(origen):
                    raise ValidationError(f"El origen no existe: {origen}")

        self.reglas.validate()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "nombre": self.nombre,
            "origenes": self.origenes,
            "destino": self.destino,
            "modo_organizacion": self.modo_organizacion.value,
            "lista_items": [item.to_dict() for item in self.lista_items],
            "reglas": self.reglas.to_dict(),
            "estado": self.estado.value,
            "stats": self.stats.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CopyJob:
        """Deserialize from dictionary."""
        return cls(
            id=data.get("id", uuid4().hex),
            nombre=data["nombre"],
            origenes=data["origenes"],
            destino=data["destino"],
            modo_organizacion=OrganizationMode(data.get("modo_organizacion", "single_folder")),
            lista_items=[RequestedItem.from_dict(item) for item in data.get("lista_items", [])],
            reglas=CopyRules.from_dict(data.get("reglas", {})),
            estado=CopyJobStatus(data.get("estado", "pending")),
            stats=CopyStats.from_dict(data.get("stats", {})),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> CopyJob:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


def export_queue_to_json(jobs: list[CopyJob]) -> str:
    """Export a list of CopyJobs to JSON.

    Args:
        jobs: List of CopyJob instances to export.

    Returns:
        JSON string representation of the queue.
    """
    return json.dumps([job.to_dict() for job in jobs], ensure_ascii=False, indent=2)


def import_queue_from_json(json_str: str) -> list[CopyJob]:
    """Import a list of CopyJobs from JSON.

    Args:
        json_str: JSON string representation of the queue.

    Returns:
        List of CopyJob instances.
    """
    data = json.loads(json_str)
    return [CopyJob.from_dict(job_data) for job_data in data]


@dataclass
class Profile:
    """A saved profile containing rules and organization mode."""

    nombre: str
    reglas: CopyRules = field(default_factory=CopyRules)
    modo_organizacion: OrganizationMode = OrganizationMode.SINGLE_FOLDER

    def validate(self) -> None:
        """Validate the profile configuration.

        Raises:
            ValidationError: If validation fails.
        """
        if not self.nombre or not self.nombre.strip():
            raise ValidationError("El nombre del perfil no puede estar vacío")
        self.reglas.validate()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "nombre": self.nombre,
            "reglas": self.reglas.to_dict(),
            "modo_organizacion": self.modo_organizacion.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        """Deserialize from dictionary."""
        return cls(
            nombre=data["nombre"],
            reglas=CopyRules.from_dict(data.get("reglas", {})),
            modo_organizacion=OrganizationMode(
                data.get("modo_organizacion", "single_folder")
            ),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Profile":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


class ProfileManager:
    """Manager for saving, loading, and listing profiles."""

    def __init__(self, profiles_dir: str | None = None) -> None:
        """Initialize the profile manager.

        Args:
            profiles_dir: Directory to store profiles. Defaults to user data directory.
        """
        if profiles_dir:
            self._profiles_dir = Path(profiles_dir)
        else:
            # Default to a directory in user's home
            self._profiles_dir = Path.home() / ".mediacopier" / "profiles"
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

    def _get_profile_path(self, name: str) -> Path:
        """Get the file path for a profile name."""
        # Sanitize name to use as filename - replace spaces with underscores for cross-platform
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        safe_name = safe_name.strip("_")
        if not safe_name:
            safe_name = "profile"
        return self._profiles_dir / f"{safe_name}.json"

    def save_profile(self, profile: Profile) -> Path:
        """Save a profile to disk.

        Args:
            profile: Profile to save.

        Returns:
            Path where the profile was saved.

        Raises:
            ValidationError: If the profile is invalid.
        """
        profile.validate()
        file_path = self._get_profile_path(profile.nombre)
        file_path.write_text(profile.to_json(), encoding="utf-8")
        return file_path

    def load_profile(self, name: str) -> Profile | None:
        """Load a profile by name.

        Args:
            name: Profile name.

        Returns:
            Profile instance or None if not found.
        """
        file_path = self._get_profile_path(name)
        if not file_path.exists():
            return None
        try:
            content = file_path.read_text(encoding="utf-8")
            return Profile.from_json(content)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def list_profiles(self) -> list[str]:
        """List all available profile names.

        Returns:
            List of profile names.
        """
        profiles = []
        for file_path in self._profiles_dir.glob("*.json"):
            try:
                content = file_path.read_text(encoding="utf-8")
                profile = Profile.from_json(content)
                profiles.append(profile.nombre)
            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip invalid profile files
                continue
        return sorted(profiles)

    def delete_profile(self, name: str) -> bool:
        """Delete a profile by name.

        Args:
            name: Profile name.

        Returns:
            True if deleted, False if not found.
        """
        file_path = self._get_profile_path(name)
        if file_path.exists():
            file_path.unlink()
            return True
        return False
