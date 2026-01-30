"""Duplicate file detection module."""

import hashlib
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Set


class DuplicateMethod(Enum):
    """Methods for detecting duplicate files."""

    BY_NAME = "by_name"
    BY_HASH = "by_hash"
    BY_METADATA = "by_metadata"
    BY_SIZE_DURATION = "by_size_duration"
    SMART = "smart"  # Combina múltiples métodos


@dataclass
class DuplicateGroup:
    """Grupo de archivos duplicados."""

    original: str
    duplicates: List[str]
    method: DuplicateMethod
    confidence: float  # 0.0 - 1.0


class DuplicateDetector:
    """Detector de archivos duplicados."""

    def __init__(self):
        self._file_hashes: Dict[str, str] = {}
        self._file_names: Dict[str, List[str]] = {}

    def find_duplicates(
        self, files: List[str], method: DuplicateMethod = DuplicateMethod.SMART
    ) -> List[DuplicateGroup]:
        """Encontrar archivos duplicados."""
        if method == DuplicateMethod.BY_NAME:
            return self._find_by_name(files)
        elif method == DuplicateMethod.BY_HASH:
            return self._find_by_hash(files)
        elif method == DuplicateMethod.BY_METADATA:
            return self._find_by_metadata(files)
        elif method == DuplicateMethod.BY_SIZE_DURATION:
            return self._find_by_size(files)
        else:  # SMART
            return self._find_smart(files)

    def _normalize_filename(self, filename: str) -> str:
        """Normalizar nombre para comparación."""
        name = Path(filename).stem.lower()
        # Quitar números al inicio (001 - , 01. , etc)
        name = re.sub(r"^[\d\s\-_.]+", "", name)
        # Quitar caracteres especiales
        name = re.sub(r"[^a-z0-9]", "", name)
        return name

    def _find_by_name(self, files: List[str]) -> List[DuplicateGroup]:
        """Encontrar duplicados por nombre normalizado."""
        groups: Dict[str, List[str]] = {}

        for filepath in files:
            normalized = self._normalize_filename(os.path.basename(filepath))
            if normalized:
                if normalized not in groups:
                    groups[normalized] = []
                groups[normalized].append(filepath)

        result = []
        for name, paths in groups.items():
            if len(paths) > 1:
                result.append(
                    DuplicateGroup(
                        original=paths[0],
                        duplicates=paths[1:],
                        method=DuplicateMethod.BY_NAME,
                        confidence=0.7,
                    )
                )
        return result

    def _get_file_hash(self, filepath: str, quick: bool = True) -> str:
        """Calcular hash MD5 del archivo."""
        hasher = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                if quick:
                    # Solo primeros y últimos 64KB para velocidad
                    hasher.update(f.read(65536))
                    f.seek(-65536, 2)
                    hasher.update(f.read(65536))
                else:
                    for chunk in iter(lambda: f.read(65536), b""):
                        hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""

    def _find_by_hash(self, files: List[str]) -> List[DuplicateGroup]:
        """Encontrar duplicados por hash MD5."""
        groups: Dict[str, List[str]] = {}

        for filepath in files:
            file_hash = self._get_file_hash(filepath)
            if file_hash:
                if file_hash not in groups:
                    groups[file_hash] = []
                groups[file_hash].append(filepath)

        result = []
        for hash_val, paths in groups.items():
            if len(paths) > 1:
                result.append(
                    DuplicateGroup(
                        original=paths[0],
                        duplicates=paths[1:],
                        method=DuplicateMethod.BY_HASH,
                        confidence=0.99,
                    )
                )
        return result

    def _find_by_metadata(self, files: List[str]) -> List[DuplicateGroup]:
        """Encontrar duplicados por metadata ID3."""
        try:
            from mutagen.easyid3 import EasyID3
        except ImportError:
            return []

        groups: Dict[str, List[str]] = {}

        for filepath in files:
            try:
                audio = EasyID3(filepath)
                artist = audio.get("artist", [""])[0].lower()
                title = audio.get("title", [""])[0].lower()
                key = f"{artist}|{title}"
                if key != "|":
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(filepath)
            except Exception:
                continue

        result = []
        for key, paths in groups.items():
            if len(paths) > 1:
                result.append(
                    DuplicateGroup(
                        original=paths[0],
                        duplicates=paths[1:],
                        method=DuplicateMethod.BY_METADATA,
                        confidence=0.85,
                    )
                )
        return result

    def _find_by_size(self, files: List[str]) -> List[DuplicateGroup]:
        """Encontrar duplicados por tamaño de archivo."""
        groups: Dict[int, List[str]] = {}

        for filepath in files:
            try:
                size = os.path.getsize(filepath)
                if size not in groups:
                    groups[size] = []
                groups[size].append(filepath)
            except Exception:
                continue

        result = []
        for size, paths in groups.items():
            if len(paths) > 1:
                # Verificar con hash rápido
                hash_groups: Dict[str, List[str]] = {}
                for p in paths:
                    h = self._get_file_hash(p, quick=True)
                    if h not in hash_groups:
                        hash_groups[h] = []
                    hash_groups[h].append(p)

                for hash_val, hash_paths in hash_groups.items():
                    if len(hash_paths) > 1:
                        result.append(
                            DuplicateGroup(
                                original=hash_paths[0],
                                duplicates=hash_paths[1:],
                                method=DuplicateMethod.BY_SIZE_DURATION,
                                confidence=0.95,
                            )
                        )
        return result

    def _find_smart(self, files: List[str]) -> List[DuplicateGroup]:
        """Detección inteligente combinando métodos."""
        # Primero por tamaño (rápido)
        by_size = self._find_by_size(files)

        # Complementar con nombres
        by_name = self._find_by_name(files)

        # Combinar resultados únicos
        seen_duplicates: Set[str] = set()
        result = []

        for group in by_size:
            for dup in group.duplicates:
                seen_duplicates.add(dup)
            result.append(group)

        for group in by_name:
            new_dups = [d for d in group.duplicates if d not in seen_duplicates]
            if new_dups:
                result.append(
                    DuplicateGroup(
                        original=group.original,
                        duplicates=new_dups,
                        method=group.method,
                        confidence=group.confidence,
                    )
                )

        return result

    def get_unique_files(
        self, files: List[str], method: DuplicateMethod = DuplicateMethod.SMART
    ) -> List[str]:
        """Obtener lista de archivos sin duplicados."""
        duplicates = self.find_duplicates(files, method)

        # Crear set de duplicados a excluir
        to_exclude: Set[str] = set()
        for group in duplicates:
            to_exclude.update(group.duplicates)

        return [f for f in files if f not in to_exclude]

    def generate_report(self, duplicates: List[DuplicateGroup]) -> str:
        """Generar reporte de duplicados encontrados."""
        if not duplicates:
            return "✅ No se encontraron archivos duplicados."

        lines = [f"⚠️ Se encontraron {len(duplicates)} grupos de duplicados:\n"]

        for i, group in enumerate(duplicates, 1):
            lines.append(f"\n📁 Grupo {i} (Confianza: {group.confidence*100:.0f}%)")
            lines.append(f"   Original: {os.path.basename(group.original)}")
            for dup in group.duplicates:
                lines.append(f"   ❌ Duplicado: {os.path.basename(dup)}")

        total_dups = sum(len(g.duplicates) for g in duplicates)
        lines.append(
            f"\n📊 Total: {total_dups} archivos duplicados que se pueden eliminar"
        )

        return "\n".join(lines)
