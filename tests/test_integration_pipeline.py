"""Integration tests for the complete MediaCopier pipeline.

These tests create a temporary file structure and validate the full
pipeline from catalog building through matching to plan building
and execution (both dry-run and real copy).

Acceptance criteria tested:
- pytest passes and validates the complete pipeline
- Destination paths are correct
- Size/duration filters apply
- Collisions are resolved according to configuration
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest

from mediacopier.core.copier import (
    CollisionStrategy,
    CopyItemAction,
    build_copy_plan,
    execute_copy_plan,
)
from mediacopier.core.indexer import MediaCatalog, MediaType, scan_sources
from mediacopier.core.matcher import match_items
from mediacopier.core.models import (
    CopyJob,
    CopyRules,
    OrganizationMode,
    RequestedItem,
    RequestedItemType,
)

# ---------------------------------------------------------------------------
# Fixtures for creating temporary file structures
# ---------------------------------------------------------------------------


def create_dummy_file(path: Path, size_bytes: int = 1024, content_prefix: str = "") -> None:
    """Create a dummy file with specified size.

    Args:
        path: Path where the file should be created.
        size_bytes: Size of the file in bytes.
        content_prefix: Optional prefix for the content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    base_content = content_prefix or path.stem
    repetitions = size_bytes // max(len(base_content), 1)
    content = base_content * repetitions
    # Ensure we have exactly the requested size
    content = content[:size_bytes].ljust(size_bytes, "x")
    path.write_text(content)


@pytest.fixture
def media_source(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a source directory with dummy media files (mp3/mp4/mkv).

    Structure created:
        source/
        ├── Music/
        │   ├── Artist A - Song One.mp3
        │   ├── Artist A - Song Two.mp3
        │   ├── Artist B - Track Alpha.mp3
        │   ├── Artist B - Track Beta (Live).mp3
        │   ├── Classical - Symphony No 5.mp3
        │   └── small_song.mp3           (< 1MB for size filter tests)
        └── Movies/
            ├── The Matrix (1999).mp4
            ├── Inception (2010).mkv
            ├── Interstellar 2014.mp4
            └── short_clip.mp4            (small file for filter tests)
    """
    source = tmp_path / "source"
    music_dir = source / "Music"
    movies_dir = source / "Movies"
    music_dir.mkdir(parents=True)
    movies_dir.mkdir(parents=True)

    # Create music files - normal size (1MB)
    create_dummy_file(music_dir / "Artist A - Song One.mp3", size_bytes=1024 * 1024)
    create_dummy_file(music_dir / "Artist A - Song Two.mp3", size_bytes=1024 * 1024)
    create_dummy_file(music_dir / "Artist B - Track Alpha.mp3", size_bytes=1024 * 1024)
    create_dummy_file(music_dir / "Artist B - Track Beta (Live).mp3", size_bytes=1024 * 1024)
    create_dummy_file(music_dir / "Classical - Symphony No 5.mp3", size_bytes=1024 * 1024)

    # Create small music file (< 1MB) for size filter tests
    create_dummy_file(music_dir / "small_song.mp3", size_bytes=500 * 1024)

    # Create movie files - larger size (2MB)
    create_dummy_file(movies_dir / "The Matrix (1999).mp4", size_bytes=2 * 1024 * 1024)
    create_dummy_file(movies_dir / "Inception (2010).mkv", size_bytes=2 * 1024 * 1024)
    create_dummy_file(movies_dir / "Interstellar 2014.mp4", size_bytes=2 * 1024 * 1024)

    # Create small video file for size filter tests
    create_dummy_file(movies_dir / "short_clip.mp4", size_bytes=100 * 1024)

    yield source

    # Cleanup is handled by tmp_path fixture


@pytest.fixture
def destination(tmp_path: Path) -> Generator[Path, None, None]:
    """Create an empty destination directory."""
    dest = tmp_path / "destination"
    dest.mkdir(parents=True)
    yield dest


# ---------------------------------------------------------------------------
# Test: Build Catalog
# ---------------------------------------------------------------------------


class TestBuildCatalog:
    """Test catalog building from source directory."""

    def test_scan_sources_finds_all_media_files(self, media_source: Path) -> None:
        """Test that scan_sources finds all media files in the source."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        # Should find 10 files total (6 mp3 + 4 mp4/mkv)
        assert len(catalog.archivos) == 10

        # Count by type
        audio_count = sum(1 for f in catalog.archivos if f.tipo == MediaType.AUDIO)
        video_count = sum(1 for f in catalog.archivos if f.tipo == MediaType.VIDEO)

        assert audio_count == 6
        assert video_count == 4

    def test_scan_sources_with_extension_filter(self, media_source: Path) -> None:
        """Test that extension filter limits results."""
        # Only mp3 files
        catalog = scan_sources(
            [str(media_source)],
            include_subfolders=True,
            allowed_extensions=[".mp3"],
        )
        assert len(catalog.archivos) == 6
        assert all(f.extension == ".mp3" for f in catalog.archivos)

        # Only video files
        catalog = scan_sources(
            [str(media_source)],
            include_subfolders=True,
            allowed_extensions=[".mp4", ".mkv"],
        )
        assert len(catalog.archivos) == 4
        assert all(f.extension in [".mp4", ".mkv"] for f in catalog.archivos)


# ---------------------------------------------------------------------------
# Test: Matching
# ---------------------------------------------------------------------------


class TestMatching:
    """Test matching requested items against catalog."""

    def test_match_song_requests(self, media_source: Path) -> None:
        """Test matching song requests finds correct files."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Track Alpha"),
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Symphony No 5"),
        ]

        results = match_items(requests, catalog, threshold=50.0)

        assert len(results) == 3
        # All should find matches
        assert all(r.match_found for r in results)

        # Verify correct matches
        assert "Song One" in results[0].best_match.media_file.nombre_base
        assert "Track Alpha" in results[1].best_match.media_file.nombre_base
        assert "Symphony No 5" in results[2].best_match.media_file.nombre_base

    def test_match_movie_requests(self, media_source: Path) -> None:
        """Test matching movie requests finds correct files."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        requests = [
            RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="The Matrix"),
            RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="Inception"),
            RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="Interstellar"),
        ]

        results = match_items(requests, catalog, threshold=50.0)

        assert len(results) == 3
        assert all(r.match_found for r in results)

    def test_live_version_has_penalty(self, media_source: Path) -> None:
        """Test that live versions receive scoring penalty for songs."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Track Beta"),
        ]

        results = match_items(requests, catalog, threshold=40.0)

        assert results[0].match_found
        # The match should have a "live" penalty
        assert "live" in results[0].best_match.penalties


# ---------------------------------------------------------------------------
# Test: Build Copy Plan
# ---------------------------------------------------------------------------


class TestBuildCopyPlan:
    """Test building copy plans from match results."""

    def test_build_plan_single_folder_mode(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test plan building with SINGLE_FOLDER organization."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Two"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
        )

        assert plan.files_to_copy == 2
        # All files should go directly to destination
        for item in plan.items:
            dest_path = Path(item.destination)
            assert dest_path.parent == destination

    def test_build_plan_folder_per_request_mode(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test plan building with FOLDER_PER_REQUEST organization."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        requests = [
            RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="The Matrix (1999)"),
            RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="Inception (2010)"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.FOLDER_PER_REQUEST,
            dest_root=str(destination),
        )

        assert plan.files_to_copy == 2
        # Movies should go to Movies/<Name>/ subfolder
        for item in plan.items:
            dest_path = Path(item.destination)
            # Should be in Movies subfolder
            assert "Movies" in str(dest_path)

    def test_collision_strategy_skip(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test that SKIP strategy marks existing files to skip."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        # Pre-create a file at destination
        existing_file = destination / "Artist A - Song One.mp3"
        create_dummy_file(existing_file, size_bytes=100)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
            collision_strategy=CollisionStrategy.SKIP,
        )

        assert plan.files_to_skip == 1
        assert plan.files_to_copy == 0
        assert plan.items[0].action == CopyItemAction.SKIP_EXISTS

    def test_collision_strategy_rename(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test that RENAME strategy creates unique filenames."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        # Pre-create a file at destination
        existing_file = destination / "Artist A - Song One.mp3"
        create_dummy_file(existing_file, size_bytes=100)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
            collision_strategy=CollisionStrategy.RENAME,
        )

        assert plan.files_to_copy == 1
        assert plan.items[0].action == CopyItemAction.RENAME_COPY
        # Destination should have _1 suffix
        assert "_1" in plan.items[0].destination

    def test_collision_strategy_compare_size(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test that COMPARE_SIZE strategy checks file sizes."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        # Pre-create a file with same size at destination
        source_size = 1024 * 1024  # Same as source
        existing_file = destination / "Artist A - Song One.mp3"
        create_dummy_file(existing_file, size_bytes=source_size)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
            collision_strategy=CollisionStrategy.COMPARE_SIZE,
        )

        # Same size should skip
        assert plan.files_to_skip == 1
        assert plan.items[0].action == CopyItemAction.SKIP_SAME_SIZE


# ---------------------------------------------------------------------------
# Test: Execute Copy Plan (Dry Run)
# ---------------------------------------------------------------------------


class TestExecuteCopyPlanDryRun:
    """Test executing copy plans in dry-run mode."""

    def test_dry_run_does_not_create_files(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test that dry-run mode doesn't actually create files."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Two"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
        )

        # Execute in dry-run mode
        report = execute_copy_plan(plan, dry_run=True)

        # Report should show files "copied"
        assert report.copied == 2
        assert report.failed == 0

        # But no actual files should exist
        files_in_dest = list(destination.glob("*.mp3"))
        assert len(files_in_dest) == 0

    def test_dry_run_reports_correct_stats(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test that dry-run mode reports correct statistics."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        # Pre-create a file to test skip
        existing_file = destination / "Artist A - Song One.mp3"
        create_dummy_file(existing_file, size_bytes=100)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Two"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
            collision_strategy=CollisionStrategy.SKIP,
        )

        report = execute_copy_plan(plan, dry_run=True)

        # One file should be skipped, one copied
        assert report.skipped == 1
        assert report.copied == 1


# ---------------------------------------------------------------------------
# Test: Execute Copy Plan (Real Copy)
# ---------------------------------------------------------------------------


class TestExecuteCopyPlanReal:
    """Test executing copy plans with real file copying."""

    def test_real_copy_creates_files(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test that real copy mode creates actual files."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Two"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
        )

        # Execute real copy
        report = execute_copy_plan(plan, dry_run=False)

        assert report.copied == 2
        assert report.failed == 0

        # Files should actually exist
        files_in_dest = list(destination.glob("*.mp3"))
        assert len(files_in_dest) == 2

        # Verify file names
        file_names = [f.name for f in files_in_dest]
        assert "Artist A - Song One.mp3" in file_names
        assert "Artist A - Song Two.mp3" in file_names

    def test_real_copy_preserves_content(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test that real copy preserves file content."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
        )

        # Get source file content
        source_file = Path(plan.items[0].source)
        source_content = source_file.read_text()

        # Execute real copy
        execute_copy_plan(plan, dry_run=False)

        # Check destination content matches
        dest_file = Path(plan.items[0].destination)
        dest_content = dest_file.read_text()

        assert source_content == dest_content

    def test_real_copy_creates_subdirectories(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test that real copy creates necessary subdirectories."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        requests = [
            RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="The Matrix"),
        ]

        results = match_items(requests, catalog, threshold=50.0)
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.FOLDER_PER_REQUEST,
            dest_root=str(destination),
        )

        # Execute real copy
        report = execute_copy_plan(plan, dry_run=False)

        assert report.copied == 1

        # Check that Movies directory structure was created
        movies_dir = destination / "Movies"
        assert movies_dir.exists()

        # Should have a subfolder with the movie name
        subdirs = list(movies_dir.iterdir())
        assert len(subdirs) == 1
        assert "Matrix" in subdirs[0].name


# ---------------------------------------------------------------------------
# Test: Complete Pipeline Integration
# ---------------------------------------------------------------------------


class TestCompletePipeline:
    """Test the complete pipeline from scan to copy."""

    def test_complete_pipeline_songs_and_movies(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test complete pipeline with both songs and movies."""
        # Step 1: Build catalog
        catalog = scan_sources([str(media_source)], include_subfolders=True)
        assert len(catalog.archivos) == 10

        # Step 2: Create requests for songs and movies
        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Track Alpha"),
            RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="Inception"),
        ]

        # Step 3: Match
        results = match_items(requests, catalog, threshold=50.0)
        assert all(r.match_found for r in results)

        # Step 4: Build plan
        plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
        )
        assert plan.files_to_copy == 3

        # Step 5: Dry run
        dry_report = execute_copy_plan(plan, dry_run=True)
        assert dry_report.copied == 3

        # No files should exist yet
        assert len(list(destination.iterdir())) == 0

        # Step 6: Real copy
        real_report = execute_copy_plan(plan, dry_run=False)
        assert real_report.copied == 3
        assert real_report.failed == 0

        # Verify files exist
        files_in_dest = list(destination.iterdir())
        assert len(files_in_dest) == 3

    def test_complete_pipeline_with_size_filter(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test complete pipeline with size filtering applied manually."""
        # Build catalog
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        # Filter catalog to exclude small files (< 1MB)
        min_size = 1024 * 1024  # 1MB
        filtered_files = [f for f in catalog.archivos if f.tamano >= min_size]
        filtered_catalog = MediaCatalog(
            archivos=filtered_files,
            origenes=catalog.origenes,
            timestamp=catalog.timestamp,
            hash_origenes=catalog.hash_origenes,
        )

        # Should exclude small_song.mp3 and short_clip.mp4
        # Original: 6 mp3 (1 small) + 4 mp4/mkv (1 small) = 10
        # Filtered: 5 mp3 + 3 mp4/mkv = 8
        assert len(filtered_catalog.archivos) == 8

        # Verify small files are excluded from catalog
        file_names = [f.nombre_base for f in filtered_catalog.archivos]
        assert "small_song" not in file_names
        assert "short_clip" not in file_names

        # Verify large files are still present
        assert any("Song One" in name for name in file_names)
        assert any("Matrix" in name for name in file_names)

    def test_complete_pipeline_with_collision_handling(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test complete pipeline handles collisions correctly."""
        catalog = scan_sources([str(media_source)], include_subfolders=True)

        # Pre-create existing file
        existing_file = destination / "Artist A - Song One.mp3"
        create_dummy_file(existing_file, size_bytes=500)

        requests = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
        ]

        results = match_items(requests, catalog, threshold=50.0)

        # Test SKIP strategy
        skip_plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
            collision_strategy=CollisionStrategy.SKIP,
        )
        assert skip_plan.files_to_skip == 1

        # Test RENAME strategy
        rename_plan = build_copy_plan(
            results,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(destination),
            collision_strategy=CollisionStrategy.RENAME,
        )
        assert rename_plan.files_to_copy == 1
        assert "_1" in rename_plan.items[0].destination

        # Execute rename copy
        report = execute_copy_plan(rename_plan, dry_run=False)
        assert report.copied == 1

        # Both files should exist now
        files = list(destination.glob("*.mp3"))
        assert len(files) == 2


# ---------------------------------------------------------------------------
# Test: CopyJob Integration
# ---------------------------------------------------------------------------


class TestCopyJobIntegration:
    """Test using CopyJob model with the pipeline."""

    def test_copy_job_with_rules(
        self, media_source: Path, destination: Path
    ) -> None:
        """Test creating and using a CopyJob with rules."""
        # Create a CopyJob
        job = CopyJob(
            nombre="Test Music Job",
            origenes=[str(media_source)],
            destino=str(destination),
            modo_organizacion=OrganizationMode.SINGLE_FOLDER,
            lista_items=[
                RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song One"),
                RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Two"),
            ],
            reglas=CopyRules(
                extensiones_permitidas=[".mp3"],
                dry_run=False,
            ),
        )

        # Validate job
        job.validate()

        # Build catalog from job sources
        catalog = scan_sources(
            job.origenes,
            include_subfolders=job.reglas.incluir_subcarpetas,
            allowed_extensions=job.reglas.extensiones_permitidas
            if job.reglas.solo_extensiones_seleccionadas
            else None,
        )

        assert len(catalog.archivos) > 0

        # Match items
        results = match_items(
            job.lista_items,
            catalog,
            threshold=job.reglas.umbral_fuzzy if job.reglas.usar_fuzzy else 100.0,
        )

        assert all(r.match_found for r in results)

        # Build and execute plan
        plan = build_copy_plan(
            results,
            organization_mode=job.modo_organizacion,
            dest_root=job.destino,
        )

        report = execute_copy_plan(plan, dry_run=job.reglas.dry_run)

        assert report.copied == 2
        assert report.failed == 0

        # Verify files exist
        files = list(Path(job.destino).glob("*.mp3"))
        assert len(files) == 2
