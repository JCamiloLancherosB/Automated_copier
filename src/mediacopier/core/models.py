"""Core data models for MediaCopier."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
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

    def validate(self) -> None:
        """Validate the rules configuration.

        Raises:
            ValidationError: If any rule is invalid.
        """
        if self.tamano_min_mb < 0:
            raise ValidationError("tamano_min_mb no puede ser negativo")
        if self.duracion_min_seg < 0:
            raise ValidationError("duracion_min_seg no puede ser negativa")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "extensiones_permitidas": self.extensiones_permitidas,
            "tamano_min_mb": self.tamano_min_mb,
            "duracion_min_seg": self.duracion_min_seg,
            "incluir_subcarpetas": self.incluir_subcarpetas,
            "excluir_palabras": self.excluir_palabras,
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
