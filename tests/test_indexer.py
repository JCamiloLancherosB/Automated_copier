"""Unit tests for core indexer module."""

from __future__ import annotations

import json
from pathlib import Path

from mediacopier.core.indexer import (
    AUDIO_EXTENSIONS,
    IGNORED_EXTENSIONS,
    VIDEO_EXTENSIONS,
    MediaCatalog,
    MediaFile,
    MediaType,
    detect_media_type,
    scan_sources,
    should_ignore_file,
)


class TestDetectMediaType:
    """Tests for detect_media_type function."""

    def test_audio_extensions(self) -> None:
        """Test that audio extensions are detected correctly."""
        for ext in AUDIO_EXTENSIONS:
            assert detect_media_type(ext) == MediaType.AUDIO
            # Test case insensitivity
            assert detect_media_type(ext.upper()) == MediaType.AUDIO

    def test_video_extensions(self) -> None:
        """Test that video extensions are detected correctly."""
        for ext in VIDEO_EXTENSIONS:
            assert detect_media_type(ext) == MediaType.VIDEO
            # Test case insensitivity
            assert detect_media_type(ext.upper()) == MediaType.VIDEO

    def test_other_extensions(self) -> None:
        """Test that unknown extensions are detected as OTHER."""
        other_extensions = [".txt", ".pdf", ".doc", ".xlsx", ".py", ".json"]
        for ext in other_extensions:
            assert detect_media_type(ext) == MediaType.OTHER

    def test_common_audio_formats(self) -> None:
        """Test specific common audio formats."""
        assert detect_media_type(".mp3") == MediaType.AUDIO
        assert detect_media_type(".flac") == MediaType.AUDIO
        assert detect_media_type(".wav") == MediaType.AUDIO
        assert detect_media_type(".aac") == MediaType.AUDIO

    def test_common_video_formats(self) -> None:
        """Test specific common video formats."""
        assert detect_media_type(".mp4") == MediaType.VIDEO
        assert detect_media_type(".mkv") == MediaType.VIDEO
        assert detect_media_type(".avi") == MediaType.VIDEO
        assert detect_media_type(".mov") == MediaType.VIDEO


class TestShouldIgnoreFile:
    """Tests for should_ignore_file function."""

    def test_ignored_extensions(self) -> None:
        """Test that ignored extensions are filtered out."""
        for ext in IGNORED_EXTENSIONS:
            assert should_ignore_file(Path(f"/tmp/test{ext}")) is True

    def test_ignored_patterns(self) -> None:
        """Test that specific ignored patterns are filtered out."""
        ignored_files = [".DS_Store", "Thumbs.db", "desktop.ini"]
        for name in ignored_files:
            assert should_ignore_file(Path(f"/tmp/{name}")) is True

    def test_hidden_files_ignored(self) -> None:
        """Test that hidden files (starting with .) are ignored."""
        assert should_ignore_file(Path("/tmp/.hidden_file.mp3")) is True
        assert should_ignore_file(Path("/tmp/.config")) is True

    def test_normal_files_not_ignored(self) -> None:
        """Test that normal files are not ignored."""
        assert should_ignore_file(Path("/tmp/song.mp3")) is False
        assert should_ignore_file(Path("/tmp/video.mp4")) is False
        assert should_ignore_file(Path("/tmp/document.txt")) is False


class TestMediaFile:
    """Tests for MediaFile dataclass."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for MediaFile."""
        original = MediaFile(
            path="/music/song.mp3",
            nombre_base="song",
            extension=".mp3",
            tamano=1024000,
            tipo=MediaType.AUDIO,
        )
        data = original.to_dict()
        restored = MediaFile.from_dict(data)

        assert restored.path == original.path
        assert restored.nombre_base == original.nombre_base
        assert restored.extension == original.extension
        assert restored.tamano == original.tamano
        assert restored.tipo == original.tipo

    def test_from_path(self, tmp_path: Path) -> None:
        """Test creating MediaFile from a real file path."""
        test_file = tmp_path / "test_song.mp3"
        test_file.write_bytes(b"fake mp3 content" * 100)

        media_file = MediaFile.from_path(test_file)

        assert media_file.path == str(test_file)
        assert media_file.nombre_base == "test_song"
        assert media_file.extension == ".mp3"
        assert media_file.tamano == 1600
        assert media_file.tipo == MediaType.AUDIO


class TestMediaCatalog:
    """Tests for MediaCatalog dataclass."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for MediaCatalog."""
        original = MediaCatalog(
            archivos=[
                MediaFile(
                    path="/music/song.mp3",
                    nombre_base="song",
                    extension=".mp3",
                    tamano=1024000,
                    tipo=MediaType.AUDIO,
                ),
                MediaFile(
                    path="/videos/clip.mp4",
                    nombre_base="clip",
                    extension=".mp4",
                    tamano=5000000,
                    tipo=MediaType.VIDEO,
                ),
            ],
            origenes=["/music", "/videos"],
            timestamp="2024-01-01T12:00:00",
            hash_origenes="abc123",
        )
        data = original.to_dict()
        restored = MediaCatalog.from_dict(data)

        assert len(restored.archivos) == len(original.archivos)
        assert restored.origenes == original.origenes
        assert restored.timestamp == original.timestamp
        assert restored.hash_origenes == original.hash_origenes

    def test_to_json_from_json_roundtrip(self) -> None:
        """Test full JSON string roundtrip for MediaCatalog."""
        original = MediaCatalog(
            archivos=[
                MediaFile(
                    path="/music/song.flac",
                    nombre_base="song",
                    extension=".flac",
                    tamano=30000000,
                    tipo=MediaType.AUDIO,
                ),
            ],
            origenes=["/music"],
            timestamp="2024-01-15T10:30:00",
            hash_origenes="def456",
        )
        json_str = original.to_json()
        restored = MediaCatalog.from_json(json_str)

        assert len(restored.archivos) == 1
        assert restored.archivos[0].nombre_base == "song"
        assert restored.origenes == ["/music"]

    def test_save_and_load_from_file(self, tmp_path: Path) -> None:
        """Test saving and loading catalog to/from file."""
        cache_file = tmp_path / "cache" / "catalog.json"

        original = MediaCatalog(
            archivos=[
                MediaFile(
                    path="/music/track.wav",
                    nombre_base="track",
                    extension=".wav",
                    tamano=44000000,
                    tipo=MediaType.AUDIO,
                ),
            ],
            origenes=["/music"],
            timestamp="2024-02-01T08:00:00",
            hash_origenes="ghi789",
        )

        # Save to file
        original.save_to_file(cache_file)
        assert cache_file.exists()

        # Load from file
        loaded = MediaCatalog.load_from_file(cache_file)
        assert loaded is not None
        assert len(loaded.archivos) == 1
        assert loaded.archivos[0].nombre_base == "track"
        assert loaded.timestamp == "2024-02-01T08:00:00"

    def test_load_from_nonexistent_file(self, tmp_path: Path) -> None:
        """Test that loading from nonexistent file returns None."""
        result = MediaCatalog.load_from_file(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_from_invalid_json_file(self, tmp_path: Path) -> None:
        """Test that loading from invalid JSON file returns None."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json {{{", encoding="utf-8")

        result = MediaCatalog.load_from_file(invalid_file)
        assert result is None


class TestScanSources:
    """Tests for scan_sources function."""

    def test_scan_empty_folder(self, tmp_path: Path) -> None:
        """Test scanning an empty folder."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        catalog = scan_sources([str(empty_dir)])

        assert len(catalog.archivos) == 0
        assert catalog.origenes == [str(empty_dir)]

    def test_scan_folder_with_files(self, tmp_path: Path) -> None:
        """Test scanning a folder with media files."""
        music_dir = tmp_path / "music"
        music_dir.mkdir()

        # Create some test files
        (music_dir / "song1.mp3").write_bytes(b"fake mp3" * 10)
        (music_dir / "song2.flac").write_bytes(b"fake flac" * 10)
        (music_dir / "video.mp4").write_bytes(b"fake mp4" * 10)

        catalog = scan_sources([str(music_dir)])

        assert len(catalog.archivos) == 3
        types = {f.tipo for f in catalog.archivos}
        assert MediaType.AUDIO in types
        assert MediaType.VIDEO in types

    def test_scan_with_subfolders(self, tmp_path: Path) -> None:
        """Test scanning with subfolders included."""
        root_dir = tmp_path / "media"
        root_dir.mkdir()
        sub_dir = root_dir / "subfolder"
        sub_dir.mkdir()

        (root_dir / "root_song.mp3").write_bytes(b"x" * 100)
        (sub_dir / "sub_song.mp3").write_bytes(b"y" * 100)

        # With subfolders
        catalog = scan_sources([str(root_dir)], include_subfolders=True)
        assert len(catalog.archivos) == 2

        # Without subfolders
        catalog = scan_sources([str(root_dir)], include_subfolders=False)
        assert len(catalog.archivos) == 1
        assert "root_song" in catalog.archivos[0].nombre_base

    def test_filter_by_extension(self, tmp_path: Path) -> None:
        """Test filtering by allowed extensions."""
        media_dir = tmp_path / "media"
        media_dir.mkdir()

        (media_dir / "song.mp3").write_bytes(b"mp3" * 10)
        (media_dir / "track.flac").write_bytes(b"flac" * 10)
        (media_dir / "video.mp4").write_bytes(b"mp4" * 10)
        (media_dir / "document.txt").write_bytes(b"txt" * 10)

        # Filter only mp3
        catalog = scan_sources([str(media_dir)], allowed_extensions=[".mp3"])
        assert len(catalog.archivos) == 1
        assert catalog.archivos[0].extension == ".mp3"

        # Filter mp3 and flac
        catalog = scan_sources([str(media_dir)], allowed_extensions=[".mp3", ".flac"])
        assert len(catalog.archivos) == 2
        extensions = {f.extension for f in catalog.archivos}
        assert extensions == {".mp3", ".flac"}

    def test_filter_extension_without_dot(self, tmp_path: Path) -> None:
        """Test that extensions without leading dot also work."""
        media_dir = tmp_path / "media"
        media_dir.mkdir()

        (media_dir / "song.mp3").write_bytes(b"mp3" * 10)
        (media_dir / "track.flac").write_bytes(b"flac" * 10)

        # Filter with extension without leading dot
        catalog = scan_sources([str(media_dir)], allowed_extensions=["mp3"])
        assert len(catalog.archivos) == 1
        assert catalog.archivos[0].extension == ".mp3"

    def test_ignore_temp_files(self, tmp_path: Path) -> None:
        """Test that temporary files are ignored."""
        media_dir = tmp_path / "media"
        media_dir.mkdir()

        (media_dir / "song.mp3").write_bytes(b"mp3" * 10)
        (media_dir / "temp.tmp").write_bytes(b"tmp" * 10)
        (media_dir / "partial.part").write_bytes(b"part" * 10)
        (media_dir / ".hidden.mp3").write_bytes(b"hidden" * 10)

        catalog = scan_sources([str(media_dir)])

        assert len(catalog.archivos) == 1
        assert catalog.archivos[0].nombre_base == "song"

    def test_progress_callback(self, tmp_path: Path) -> None:
        """Test that progress callback is called correctly."""
        media_dir = tmp_path / "media"
        media_dir.mkdir()

        for i in range(5):
            (media_dir / f"song{i}.mp3").write_bytes(b"x" * 100)

        progress_calls: list[tuple[int, int, str]] = []

        def progress_callback(current: int, total: int, current_file: str) -> None:
            progress_calls.append((current, total, current_file))

        catalog = scan_sources([str(media_dir)], progress_callback=progress_callback)

        assert len(catalog.archivos) == 5
        assert len(progress_calls) == 5
        # Check that progress increases
        for i, (current, total, _) in enumerate(progress_calls):
            assert current == i + 1
            assert total == 5

    def test_cache_save_and_load(self, tmp_path: Path) -> None:
        """Test that cache is saved and loaded correctly."""
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        cache_file = tmp_path / "cache.json"

        (media_dir / "song.mp3").write_bytes(b"mp3" * 10)

        # First scan - should create cache
        catalog1 = scan_sources([str(media_dir)], cache_path=cache_file)
        assert cache_file.exists()
        assert len(catalog1.archivos) == 1

        # Verify cache content
        with cache_file.open() as f:
            cache_data = json.load(f)
        assert "archivos" in cache_data
        assert "timestamp" in cache_data
        assert "hash_origenes" in cache_data

    def test_multiple_sources(self, tmp_path: Path) -> None:
        """Test scanning multiple source folders."""
        music_dir = tmp_path / "music"
        video_dir = tmp_path / "videos"
        music_dir.mkdir()
        video_dir.mkdir()

        (music_dir / "song.mp3").write_bytes(b"mp3" * 10)
        (video_dir / "clip.mp4").write_bytes(b"mp4" * 10)

        catalog = scan_sources([str(music_dir), str(video_dir)])

        assert len(catalog.archivos) == 2
        assert len(catalog.origenes) == 2

    def test_nonexistent_source_skipped(self, tmp_path: Path) -> None:
        """Test that nonexistent source folders are skipped gracefully."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        (existing_dir / "song.mp3").write_bytes(b"mp3" * 10)

        nonexistent = tmp_path / "nonexistent"

        catalog = scan_sources([str(existing_dir), str(nonexistent)])

        assert len(catalog.archivos) == 1
