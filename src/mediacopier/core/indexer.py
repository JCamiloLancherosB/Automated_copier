"""File indexer for scanning and cataloging media files."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from mediacopier.core.metadata_audio import AudioMeta


class MediaType(Enum):
    """Type of media file."""

    AUDIO = "audio"
    VIDEO = "video"
    OTHER = "other"


# Default audio file extensions
AUDIO_EXTENSIONS: set[str] = {
    ".mp3",
    ".flac",
    ".wav",
    ".aac",
    ".ogg",
    ".wma",
    ".m4a",
    ".opus",
    ".aiff",
    ".alac",
}

# Default video file extensions
VIDEO_EXTENSIONS: set[str] = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".mpeg",
    ".mpg",
    ".3gp",
}

# Extensions to ignore by default (temporary/system files)
IGNORED_EXTENSIONS: set[str] = {
    ".tmp",
    ".temp",
    ".bak",
    ".swp",
    ".swo",
    ".part",
    ".crdownload",
    ".partial",
    ".download",
}

# File name patterns to ignore (temporary/system files)
IGNORED_PATTERNS: set[str] = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".gitignore",
    ".gitkeep",
}


def detect_media_type(extension: str) -> MediaType:
    """Detect media type based on file extension.

    Args:
        extension: File extension including the dot (e.g., '.mp3').

    Returns:
        MediaType enum value.
    """
    ext_lower = extension.lower()
    if ext_lower in AUDIO_EXTENSIONS:
        return MediaType.AUDIO
    if ext_lower in VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    return MediaType.OTHER


def should_ignore_file(file_path: Path) -> bool:
    """Check if a file should be ignored.

    Args:
        file_path: Path to the file.

    Returns:
        True if the file should be ignored.
    """
    name = file_path.name

    # Check for ignored patterns
    if name in IGNORED_PATTERNS:
        return True

    # Check for hidden files (Unix-style)
    if name.startswith(".") and name not in IGNORED_PATTERNS:
        return True

    # Check for ignored extensions
    if file_path.suffix.lower() in IGNORED_EXTENSIONS:
        return True

    return False


@dataclass
class MediaFile:
    """Represents a media file in the catalog."""

    path: str
    nombre_base: str
    extension: str
    tamano: int
    tipo: MediaType
    audio_meta: "AudioMeta | None" = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            "path": self.path,
            "nombre_base": self.nombre_base,
            "extension": self.extension,
            "tamano": self.tamano,
            "tipo": self.tipo.value,
        }
        if self.audio_meta is not None:
            result["audio_meta"] = self.audio_meta.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaFile:
        """Deserialize from dictionary."""
        audio_meta = None
        if "audio_meta" in data and data["audio_meta"] is not None:
            from mediacopier.core.metadata_audio import AudioMeta

            audio_meta = AudioMeta.from_dict(data["audio_meta"])
        return cls(
            path=data["path"],
            nombre_base=data["nombre_base"],
            extension=data["extension"],
            tamano=data["tamano"],
            tipo=MediaType(data["tipo"]),
            audio_meta=audio_meta,
        )

    @classmethod
    def from_path(cls, file_path: Path, extract_metadata: bool = False) -> MediaFile:
        """Create a MediaFile from a file path.

        Args:
            file_path: Path to the file.
            extract_metadata: Whether to extract audio metadata for audio files.

        Returns:
            MediaFile instance.
        """
        media_type = detect_media_type(file_path.suffix)
        audio_meta = None

        if extract_metadata and media_type == MediaType.AUDIO:
            from mediacopier.core.metadata_audio import extract_audio_metadata

            audio_meta = extract_audio_metadata(file_path)

        return cls(
            path=str(file_path),
            nombre_base=file_path.stem,
            extension=file_path.suffix,
            tamano=file_path.stat().st_size,
            tipo=media_type,
            audio_meta=audio_meta,
        )


@dataclass
class MediaCatalog:
    """Catalog of media files with caching support."""

    archivos: list[MediaFile] = field(default_factory=list)
    origenes: list[str] = field(default_factory=list)
    timestamp: str = ""
    hash_origenes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "archivos": [f.to_dict() for f in self.archivos],
            "origenes": self.origenes,
            "timestamp": self.timestamp,
            "hash_origenes": self.hash_origenes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaCatalog:
        """Deserialize from dictionary."""
        return cls(
            archivos=[MediaFile.from_dict(f) for f in data.get("archivos", [])],
            origenes=data.get("origenes", []),
            timestamp=data.get("timestamp", ""),
            hash_origenes=data.get("hash_origenes", ""),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> MediaCatalog:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def save_to_file(self, file_path: str | Path) -> None:
        """Save catalog to a JSON file.

        Args:
            file_path: Path to the output file.
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load_from_file(cls, file_path: str | Path) -> MediaCatalog | None:
        """Load catalog from a JSON file.

        Args:
            file_path: Path to the input file.

        Returns:
            MediaCatalog instance or None if file doesn't exist.
        """
        path = Path(file_path)
        if not path.exists():
            return None
        try:
            return cls.from_json(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return None


def _compute_sources_hash(sources: list[str], include_subfolders: bool) -> str:
    """Compute a simple hash of the source folders configuration.

    This is used to detect if the scan configuration has changed.

    Args:
        sources: List of source folder paths.
        include_subfolders: Whether subfolders are included.

    Returns:
        Hash string.
    """
    content = "|".join(sorted(sources)) + f"|subfolders={include_subfolders}"
    return hashlib.md5(content.encode()).hexdigest()


def _is_cache_valid(
    cache: MediaCatalog,
    sources: list[str],
    include_subfolders: bool,
) -> bool:
    """Check if cached catalog is still valid.

    Args:
        cache: Cached catalog.
        sources: Current source folders.
        include_subfolders: Current subfolder setting.

    Returns:
        True if cache can be reused.
    """
    current_hash = _compute_sources_hash(sources, include_subfolders)
    if cache.hash_origenes != current_hash:
        return False

    # Check if any source folder has been modified since cache
    if not cache.timestamp:
        return False

    try:
        cache_time = datetime.fromisoformat(cache.timestamp)
        for source in sources:
            source_path = Path(source)
            if not source_path.exists():
                return False
            # Check modification time of source folder
            mtime = datetime.fromtimestamp(source_path.stat().st_mtime)
            if mtime > cache_time:
                return False
    except (ValueError, OSError):
        return False

    return True


# Type alias for progress callback
ProgressCallback = Callable[[int, int, str], None]


def scan_sources(
    sources: list[str],
    include_subfolders: bool = True,
    allowed_extensions: list[str] | None = None,
    cache_path: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    extract_audio_metadata: bool = False,
) -> MediaCatalog:
    """Scan source folders and build a media catalog.

    This function scans one or more source folders for media files and
    returns a MediaCatalog. It supports incremental caching to avoid
    rescanning unchanged folders.

    The function is designed to run in a worker thread and reports progress
    via a callback to avoid freezing the UI.

    Args:
        sources: List of source folder paths to scan.
        include_subfolders: Whether to include subfolders in the scan.
        allowed_extensions: Optional list of extensions to include (e.g., ['.mp3', '.flac']).
            If None, all non-ignored extensions are included.
        cache_path: Optional path to save/load the catalog cache.
        progress_callback: Optional callback(current, total, current_file) for progress.
        extract_audio_metadata: Whether to extract audio metadata for audio files.

    Returns:
        MediaCatalog with all found media files.
    """
    # Normalize sources
    sources = [str(Path(s).resolve()) for s in sources if s]

    # Try to load from cache
    if cache_path:
        cached = MediaCatalog.load_from_file(cache_path)
        if cached and _is_cache_valid(cached, sources, include_subfolders):
            if progress_callback:
                progress_callback(len(cached.archivos), len(cached.archivos), "Cache loaded")
            return cached

    # First pass: count total files for progress
    all_files: list[Path] = []
    for source in sources:
        source_path = Path(source)
        if not source_path.exists():
            continue

        if include_subfolders:
            all_files.extend(f for f in source_path.rglob("*") if f.is_file())
        else:
            all_files.extend(f for f in source_path.iterdir() if f.is_file())

    total_files = len(all_files)
    media_files: list[MediaFile] = []

    # Normalize allowed extensions
    allowed_set: set[str] | None = None
    if allowed_extensions:
        allowed_set = {
            ext.lower() if ext.startswith(".") else f".{ext}".lower() for ext in allowed_extensions
        }

    # Second pass: process files
    for i, file_path in enumerate(all_files):
        # Report progress
        if progress_callback:
            progress_callback(i + 1, total_files, str(file_path))

        # Skip ignored files
        if should_ignore_file(file_path):
            continue

        # Check allowed extensions
        ext = file_path.suffix.lower()
        if allowed_set and ext not in allowed_set:
            continue

        try:
            media_file = MediaFile.from_path(file_path, extract_metadata=extract_audio_metadata)
            media_files.append(media_file)
        except OSError:
            # Skip files that can't be read
            continue

    # Build catalog
    catalog = MediaCatalog(
        archivos=media_files,
        origenes=sources,
        timestamp=datetime.now().isoformat(),
        hash_origenes=_compute_sources_hash(sources, include_subfolders),
    )

    # Save to cache
    if cache_path:
        catalog.save_to_file(cache_path)

    return catalog
