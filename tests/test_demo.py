"""Tests for the demo mode module."""

from __future__ import annotations

import pytest

from mediacopier.core.demo import (
    DEMO_MOVIE_REQUESTS,
    DEMO_MOVIES,
    DEMO_SONG_REQUESTS,
    DEMO_SONGS,
    DemoManager,
    get_demo_info,
    is_demo_available,
    run_demo_pipeline,
)
from mediacopier.core.indexer import MediaType
from mediacopier.core.models import OrganizationMode, RequestedItemType


class TestDemoManager:
    """Tests for DemoManager class."""

    def test_setup_creates_directories(self) -> None:
        """Test that setup creates the required directories."""
        demo = DemoManager()
        try:
            demo.setup()

            assert demo.source_dir is not None
            assert demo.dest_dir is not None
            assert demo.source_dir.exists()
            assert demo.dest_dir.exists()
            assert (demo.source_dir / "Music").exists()
            assert (demo.source_dir / "Movies").exists()
        finally:
            demo.cleanup()

    def test_setup_creates_demo_files(self) -> None:
        """Test that setup creates demo media files."""
        demo = DemoManager()
        try:
            demo.setup()

            music_dir = demo.source_dir / "Music"
            movies_dir = demo.source_dir / "Movies"

            # Check music files
            mp3_files = list(music_dir.glob("*.mp3"))
            assert len(mp3_files) == len(DEMO_SONGS)

            # Check movie files
            video_files = list(movies_dir.glob("*.mp4")) + list(movies_dir.glob("*.mkv"))
            assert len(video_files) == len(DEMO_MOVIES)
        finally:
            demo.cleanup()

    def test_setup_is_idempotent(self) -> None:
        """Test that calling setup multiple times has no effect."""
        demo = DemoManager()
        try:
            demo.setup()
            first_source = demo.source_dir

            demo.setup()  # Call again
            assert demo.source_dir == first_source
        finally:
            demo.cleanup()

    def test_cleanup_removes_files(self) -> None:
        """Test that cleanup removes all demo files."""
        demo = DemoManager()
        demo.setup()

        base_dir = demo.base_dir
        assert base_dir.exists()

        demo.cleanup()

        # Base dir should be removed
        assert not base_dir.exists()
        assert demo.source_dir is None
        assert demo.dest_dir is None
        assert demo.catalog is None

    def test_context_manager(self) -> None:
        """Test using DemoManager as context manager."""
        with DemoManager() as demo:
            assert demo.source_dir is not None
            assert demo.source_dir.exists()
            base_dir = demo.base_dir

        # After context, files should be cleaned up
        assert not base_dir.exists()

    def test_get_catalog(self) -> None:
        """Test getting the demo catalog."""
        with DemoManager() as demo:
            catalog = demo.get_catalog()

            assert catalog is not None
            assert len(catalog.archivos) == len(DEMO_SONGS) + len(DEMO_MOVIES)

            # Check media types
            audio_count = sum(1 for f in catalog.archivos if f.tipo == MediaType.AUDIO)
            video_count = sum(1 for f in catalog.archivos if f.tipo == MediaType.VIDEO)

            assert audio_count == len(DEMO_SONGS)
            assert video_count == len(DEMO_MOVIES)

    def test_get_song_requests(self) -> None:
        """Test getting song request items."""
        demo = DemoManager()
        requests = demo.get_song_requests()

        assert len(requests) == len(DEMO_SONG_REQUESTS)
        assert all(r.tipo == RequestedItemType.SONG for r in requests)

    def test_get_movie_requests(self) -> None:
        """Test getting movie request items."""
        demo = DemoManager()
        requests = demo.get_movie_requests()

        assert len(requests) == len(DEMO_MOVIE_REQUESTS)
        assert all(r.tipo == RequestedItemType.MOVIE for r in requests)

    def test_get_all_requests(self) -> None:
        """Test getting all request items."""
        demo = DemoManager()
        requests = demo.get_all_requests()

        expected_count = len(DEMO_SONG_REQUESTS) + len(DEMO_MOVIE_REQUESTS)
        assert len(requests) == expected_count

    def test_get_demo_job_music(self) -> None:
        """Test getting a music demo job."""
        with DemoManager() as demo:
            job = demo.get_demo_job("music")

            assert job.nombre == "Demo Music Job"
            assert len(job.lista_items) == len(DEMO_SONG_REQUESTS)
            assert all(
                item.tipo == RequestedItemType.SONG for item in job.lista_items
            )
            assert ".mp3" in job.reglas.extensiones_permitidas

    def test_get_demo_job_movies(self) -> None:
        """Test getting a movies demo job."""
        with DemoManager() as demo:
            job = demo.get_demo_job("movies")

            assert job.nombre == "Demo Movies Job"
            assert len(job.lista_items) == len(DEMO_MOVIE_REQUESTS)
            assert all(
                item.tipo == RequestedItemType.MOVIE for item in job.lista_items
            )
            assert ".mp4" in job.reglas.extensiones_permitidas

    def test_get_demo_job_all(self) -> None:
        """Test getting a full demo job."""
        with DemoManager() as demo:
            job = demo.get_demo_job("all")

            expected_items = len(DEMO_SONG_REQUESTS) + len(DEMO_MOVIE_REQUESTS)
            assert len(job.lista_items) == expected_items

    def test_get_demo_job_custom_mode(self) -> None:
        """Test getting a demo job with custom organization mode."""
        with DemoManager() as demo:
            job = demo.get_demo_job(
                "music",
                organization_mode=OrganizationMode.FOLDER_PER_REQUEST,
            )

            assert job.modo_organizacion == OrganizationMode.FOLDER_PER_REQUEST

    def test_get_demo_job_invalid_type(self) -> None:
        """Test that invalid job type raises ValueError."""
        with DemoManager() as demo:
            with pytest.raises(ValueError, match="Unknown job type"):
                demo.get_demo_job("invalid")

    def test_get_demo_stats(self) -> None:
        """Test getting demo environment statistics."""
        with DemoManager() as demo:
            stats = demo.get_demo_stats()

            assert "total_files" in stats
            assert "audio_files" in stats
            assert "video_files" in stats
            assert stats["total_files"] == len(DEMO_SONGS) + len(DEMO_MOVIES)
            assert stats["audio_files"] == len(DEMO_SONGS)
            assert stats["video_files"] == len(DEMO_MOVIES)


class TestDemoHelperFunctions:
    """Tests for demo helper functions."""

    def test_is_demo_available(self) -> None:
        """Test that demo is always available."""
        assert is_demo_available() is True

    def test_get_demo_info(self) -> None:
        """Test getting demo information."""
        info = get_demo_info()

        assert info["available"] is True
        assert info["songs_available"] == len(DEMO_SONGS)
        assert info["movies_available"] == len(DEMO_MOVIES)
        assert len(info["song_requests"]) > 0
        assert len(info["movie_requests"]) > 0


class TestRunDemoPipeline:
    """Tests for the run_demo_pipeline function."""

    def test_run_demo_pipeline(self) -> None:
        """Test running the complete demo pipeline."""
        result = run_demo_pipeline()

        assert "total_requests" in result
        assert "matches_found" in result
        assert "files_to_copy" in result
        assert "dry_run_copied" in result
        assert "demo_stats" in result

        # Verify some matches were found
        assert result["matches_found"] > 0

        # Verify dry-run completed
        assert result["dry_run_failed"] == 0

    def test_run_demo_pipeline_matches_requests(self) -> None:
        """Test that demo pipeline finds matches for most requests."""
        result = run_demo_pipeline()

        total = result["total_requests"]
        matches = result["matches_found"]

        # Should match at least 50% of requests
        assert matches >= total // 2


class TestDemoIntegrationWithPipeline:
    """Integration tests using demo mode with the full pipeline."""

    def test_demo_with_matcher(self) -> None:
        """Test demo files work with the matcher."""
        from mediacopier.core.matcher import match_items

        with DemoManager() as demo:
            catalog = demo.get_catalog()
            requests = demo.get_song_requests()

            results = match_items(requests, catalog, threshold=50.0)

            # Should find matches for most songs
            matches_found = sum(1 for r in results if r.match_found)
            assert matches_found >= len(requests) // 2

    def test_demo_with_copy_plan(self) -> None:
        """Test demo files work with copy plan building."""
        from mediacopier.core.copier import build_copy_plan
        from mediacopier.core.matcher import match_items

        with DemoManager() as demo:
            catalog = demo.get_catalog()
            requests = demo.get_song_requests()
            dest = demo.get_dest_dir()

            results = match_items(requests, catalog, threshold=50.0)
            plan = build_copy_plan(
                results,
                organization_mode=OrganizationMode.SINGLE_FOLDER,
                dest_root=str(dest),
            )

            # Should have files to copy
            assert plan.files_to_copy > 0

    def test_demo_with_execute_dry_run(self) -> None:
        """Test demo files work with plan execution in dry-run mode."""
        from mediacopier.core.copier import build_copy_plan, execute_copy_plan
        from mediacopier.core.matcher import match_items

        with DemoManager() as demo:
            catalog = demo.get_catalog()
            requests = demo.get_all_requests()
            dest = demo.get_dest_dir()

            results = match_items(requests, catalog, threshold=50.0)
            plan = build_copy_plan(
                results,
                organization_mode=OrganizationMode.SINGLE_FOLDER,
                dest_root=str(dest),
            )

            report = execute_copy_plan(plan, dry_run=True)

            # Dry-run should report copies but not create files
            assert report.copied > 0
            assert report.failed == 0
            assert len(list(dest.iterdir())) == 0

    def test_demo_with_execute_real_copy(self) -> None:
        """Test demo files work with real copy execution."""
        from mediacopier.core.copier import build_copy_plan, execute_copy_plan
        from mediacopier.core.matcher import match_items

        with DemoManager() as demo:
            catalog = demo.get_catalog()
            requests = demo.get_song_requests()[:3]  # Just a few for speed
            dest = demo.get_dest_dir()

            results = match_items(requests, catalog, threshold=50.0)
            matched_count = sum(1 for r in results if r.match_found)

            plan = build_copy_plan(
                results,
                organization_mode=OrganizationMode.SINGLE_FOLDER,
                dest_root=str(dest),
            )

            report = execute_copy_plan(plan, dry_run=False)

            # Real copy should create files
            assert report.copied == matched_count
            assert report.failed == 0

            files_in_dest = list(dest.glob("*.mp3"))
            assert len(files_in_dest) == matched_count
