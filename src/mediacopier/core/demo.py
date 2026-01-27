"""Demo mode module for MediaCopier.

This module provides sample data for demonstrating and testing the application
without requiring external media files or resources.

The demo mode creates:
- A temporary source directory with dummy media files
- Sample request lists for songs and movies
- Pre-configured CopyJob instances ready to run

Usage:
    from mediacopier.core.demo import DemoManager

    # Create demo manager
    demo = DemoManager()

    # Set up demo environment (creates temp files)
    demo.setup()

    # Get demo catalog
    catalog = demo.get_catalog()

    # Get sample requests
    song_requests = demo.get_song_requests()
    movie_requests = demo.get_movie_requests()

    # Get pre-configured job
    job = demo.get_demo_job("music")

    # Clean up when done
    demo.cleanup()
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mediacopier.core.indexer import MediaCatalog, scan_sources
from mediacopier.core.models import (
    CopyJob,
    CopyRules,
    OrganizationMode,
    RequestedItem,
    RequestedItemType,
)

# ---------------------------------------------------------------------------
# Demo Data Constants
# ---------------------------------------------------------------------------

# Sample songs with artist - title format
DEMO_SONGS = [
    ("Queen", "Bohemian Rhapsody"),
    ("Queen", "We Will Rock You"),
    ("Queen", "We Are The Champions"),
    ("The Beatles", "Hey Jude"),
    ("The Beatles", "Let It Be"),
    ("The Beatles", "Yesterday"),
    ("Led Zeppelin", "Stairway to Heaven"),
    ("Led Zeppelin", "Whole Lotta Love"),
    ("Pink Floyd", "Comfortably Numb"),
    ("Pink Floyd", "Wish You Were Here"),
    ("Pink Floyd", "Another Brick in the Wall"),
    ("AC DC", "Highway to Hell"),
    ("AC DC", "Back in Black"),
    ("AC DC", "Thunderstruck"),
    ("Nirvana", "Smells Like Teen Spirit"),
    ("Nirvana", "Come as You Are"),
    ("Guns N Roses", "Sweet Child O Mine"),
    ("Guns N Roses", "Welcome to the Jungle"),
    ("Michael Jackson", "Thriller"),
    ("Michael Jackson", "Billie Jean"),
]

# Sample movies with year
DEMO_MOVIES = [
    ("The Matrix", 1999),
    ("Inception", 2010),
    ("Interstellar", 2014),
    ("The Dark Knight", 2008),
    ("Pulp Fiction", 1994),
    ("The Shawshank Redemption", 1994),
    ("Fight Club", 1999),
    ("Forrest Gump", 1994),
    ("The Godfather", 1972),
    ("Goodfellas", 1990),
]

# Sample requests for songs (partial matches for fuzzy matching)
DEMO_SONG_REQUESTS = [
    "Bohemian Rhapsody",
    "Hey Jude",
    "Stairway to Heaven",
    "Comfortably Numb",
    "Thriller",
    "Sweet Child",
]

# Sample requests for movies
DEMO_MOVIE_REQUESTS = [
    "Matrix",
    "Inception",
    "Dark Knight",
    "Pulp Fiction",
]


def _create_dummy_file(path: Path, size_kb: int = 100) -> None:
    """Create a dummy file with specified size.

    Args:
        path: Path where the file should be created.
        size_kb: Size of the file in kilobytes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.stem * (size_kb * 1024 // max(len(path.stem), 1))
    content = content[: size_kb * 1024].ljust(size_kb * 1024, "x")
    path.write_text(content)


@dataclass
class DemoManager:
    """Manager for demo mode functionality.

    Creates and manages temporary demo files and provides sample data
    for testing the MediaCopier pipeline without external resources.

    Attributes:
        base_dir: Base directory for demo files (auto-created if None).
        source_dir: Source directory containing demo media files.
        dest_dir: Destination directory for copy operations.
        catalog: Cached media catalog from demo files.
    """

    base_dir: Path | None = None
    source_dir: Path | None = None
    dest_dir: Path | None = None
    catalog: MediaCatalog | None = None
    _temp_dir: tempfile.TemporaryDirectory | None = field(
        default=None, repr=False, compare=False
    )
    _is_setup: bool = field(default=False, repr=False, compare=False)

    def setup(self) -> None:
        """Set up the demo environment.

        Creates temporary directories and populates them with demo files.
        This method is idempotent - calling it multiple times has no effect.
        """
        if self._is_setup:
            return

        # Create temporary directory
        self._temp_dir = tempfile.TemporaryDirectory(prefix="mediacopier_demo_")
        self.base_dir = Path(self._temp_dir.name)
        self.source_dir = self.base_dir / "source"
        self.dest_dir = self.base_dir / "destination"

        # Create directory structure
        music_dir = self.source_dir / "Music"
        movies_dir = self.source_dir / "Movies"
        music_dir.mkdir(parents=True)
        movies_dir.mkdir(parents=True)
        self.dest_dir.mkdir(parents=True)

        # Create demo music files
        for artist, title in DEMO_SONGS:
            filename = f"{artist} - {title}.mp3"
            _create_dummy_file(music_dir / filename, size_kb=100)

        # Create demo movie files
        for title, year in DEMO_MOVIES:
            # Use different extensions for variety
            ext = ".mp4" if year >= 2000 else ".mkv"
            filename = f"{title} ({year}){ext}"
            _create_dummy_file(movies_dir / filename, size_kb=200)

        # Build catalog
        self.catalog = scan_sources([str(self.source_dir)], include_subfolders=True)

        self._is_setup = True

    def cleanup(self) -> None:
        """Clean up demo environment and remove temporary files."""
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

        self.base_dir = None
        self.source_dir = None
        self.dest_dir = None
        self.catalog = None
        self._is_setup = False

    def ensure_setup(self) -> None:
        """Ensure the demo environment is set up."""
        if not self._is_setup:
            self.setup()

    def get_catalog(self) -> MediaCatalog:
        """Get the demo media catalog.

        Returns:
            MediaCatalog containing all demo media files.

        Raises:
            RuntimeError: If setup() has not been called.
        """
        self.ensure_setup()
        if self.catalog is None:
            raise RuntimeError("Demo catalog not available. Call setup() first.")
        return self.catalog

    def get_source_dir(self) -> Path:
        """Get the demo source directory path.

        Returns:
            Path to the demo source directory.

        Raises:
            RuntimeError: If setup() has not been called.
        """
        self.ensure_setup()
        if self.source_dir is None:
            raise RuntimeError("Demo source directory not available. Call setup() first.")
        return self.source_dir

    def get_dest_dir(self) -> Path:
        """Get the demo destination directory path.

        Returns:
            Path to the demo destination directory.

        Raises:
            RuntimeError: If setup() has not been called.
        """
        self.ensure_setup()
        if self.dest_dir is None:
            raise RuntimeError("Demo destination directory not available. Call setup() first.")
        return self.dest_dir

    def get_song_requests(self) -> list[RequestedItem]:
        """Get sample song request items.

        Returns:
            List of RequestedItem instances for demo songs.
        """
        return [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original=title)
            for title in DEMO_SONG_REQUESTS
        ]

    def get_movie_requests(self) -> list[RequestedItem]:
        """Get sample movie request items.

        Returns:
            List of RequestedItem instances for demo movies.
        """
        return [
            RequestedItem(tipo=RequestedItemType.MOVIE, texto_original=title)
            for title in DEMO_MOVIE_REQUESTS
        ]

    def get_all_requests(self) -> list[RequestedItem]:
        """Get all sample request items (songs and movies).

        Returns:
            Combined list of all demo request items.
        """
        return self.get_song_requests() + self.get_movie_requests()

    def get_demo_job(
        self,
        job_type: str = "music",
        organization_mode: OrganizationMode = OrganizationMode.SINGLE_FOLDER,
        dry_run: bool = True,
    ) -> CopyJob:
        """Get a pre-configured demo CopyJob.

        Args:
            job_type: Type of job - "music", "movies", or "all".
            organization_mode: How to organize copied files.
            dry_run: Whether to run in dry-run mode (default True for demos).

        Returns:
            CopyJob configured with demo data.

        Raises:
            ValueError: If job_type is not recognized.
            RuntimeError: If setup() has not been called.
        """
        self.ensure_setup()

        if self.source_dir is None or self.dest_dir is None:
            raise RuntimeError("Demo directories not available. Call setup() first.")

        if job_type == "music":
            items = self.get_song_requests()
            name = "Demo Music Job"
            extensions = [".mp3", ".flac", ".wav"]
        elif job_type == "movies":
            items = self.get_movie_requests()
            name = "Demo Movies Job"
            extensions = [".mp4", ".mkv", ".avi"]
        elif job_type == "all":
            items = self.get_all_requests()
            name = "Demo Full Job"
            extensions = [".mp3", ".flac", ".wav", ".mp4", ".mkv", ".avi"]
        else:
            raise ValueError(f"Unknown job type: {job_type}. Use 'music', 'movies', or 'all'.")

        return CopyJob(
            nombre=name,
            origenes=[str(self.source_dir)],
            destino=str(self.dest_dir),
            modo_organizacion=organization_mode,
            lista_items=items,
            reglas=CopyRules(
                extensiones_permitidas=extensions,
                dry_run=dry_run,
                usar_fuzzy=True,
                umbral_fuzzy=60.0,
            ),
        )

    def get_demo_stats(self) -> dict[str, Any]:
        """Get statistics about the demo environment.

        Returns:
            Dictionary with demo environment statistics.
        """
        self.ensure_setup()

        catalog = self.get_catalog()
        audio_files = [f for f in catalog.archivos if f.tipo.value == "audio"]
        video_files = [f for f in catalog.archivos if f.tipo.value == "video"]

        return {
            "total_files": len(catalog.archivos),
            "audio_files": len(audio_files),
            "video_files": len(video_files),
            "source_dir": str(self.source_dir),
            "dest_dir": str(self.dest_dir),
            "song_requests": len(DEMO_SONG_REQUESTS),
            "movie_requests": len(DEMO_MOVIE_REQUESTS),
        }

    def __enter__(self) -> "DemoManager":
        """Context manager entry - sets up demo environment."""
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleans up demo environment."""
        self.cleanup()


def run_demo_pipeline() -> dict[str, Any]:
    """Run a complete demo of the MediaCopier pipeline.

    This function demonstrates the full pipeline:
    1. Creates demo files
    2. Builds catalog
    3. Matches requests
    4. Builds copy plan
    5. Executes dry-run
    6. Cleans up

    Returns:
        Dictionary with demo results including stats and report.
    """
    from mediacopier.core.copier import build_copy_plan, execute_copy_plan
    from mediacopier.core.matcher import match_items

    with DemoManager() as demo:
        # Get demo data
        catalog = demo.get_catalog()
        requests = demo.get_all_requests()
        dest = demo.get_dest_dir()

        # Match requests
        results = match_items(requests, catalog, threshold=60.0)
        matches_found = sum(1 for r in results if r.match_found)

        # Build plan
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest),
        )

        # Execute dry-run
        report = execute_copy_plan(plan, dry_run=True)

        return {
            "total_requests": len(requests),
            "matches_found": matches_found,
            "files_to_copy": plan.files_to_copy,
            "total_bytes": plan.total_bytes,
            "dry_run_copied": report.copied,
            "dry_run_skipped": report.skipped,
            "dry_run_failed": report.failed,
            "demo_stats": demo.get_demo_stats(),
        }


# Convenience function for CLI/app integration
def is_demo_available() -> bool:
    """Check if demo mode can be used.

    Returns:
        Always returns True as demo mode has no external dependencies.
    """
    return True


def get_demo_info() -> dict[str, Any]:
    """Get information about the demo mode.

    Returns:
        Dictionary with demo mode information.
    """
    return {
        "available": True,
        "description": "Demo mode creates temporary files for testing",
        "songs_available": len(DEMO_SONGS),
        "movies_available": len(DEMO_MOVIES),
        "song_requests": DEMO_SONG_REQUESTS,
        "movie_requests": DEMO_MOVIE_REQUESTS,
    }
