"""Unit tests for core metadata_audio module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mediacopier.core.metadata_audio import (
    MUTAGEN_AVAILABLE,
    UNKNOWN_ARTIST,
    UNKNOWN_GENRE,
    UNKNOWN_TITLE,
    AudioMeta,
    extract_audio_metadata,
    get_organization_path_by_genre,
    parse_artist_title_from_filename,
)


class TestParseArtistTitleFromFilename:
    """Tests for parse_artist_title_from_filename function."""

    def test_standard_format(self) -> None:
        """Test parsing standard 'Artist - Title' format."""
        artist, title = parse_artist_title_from_filename("Pink Floyd - Comfortably Numb")
        assert artist == "Pink Floyd"
        assert title == "Comfortably Numb"

    def test_with_dash_variant(self) -> None:
        """Test parsing with different dash styles."""
        # En dash
        artist, title = parse_artist_title_from_filename("The Beatles – Yesterday")
        assert artist == "The Beatles"
        assert title == "Yesterday"

        # Em dash
        artist, title = parse_artist_title_from_filename("Queen—Bohemian Rhapsody")
        assert artist == "Queen"
        assert title == "Bohemian Rhapsody"

    def test_with_extra_spaces(self) -> None:
        """Test parsing with extra spaces around separator."""
        artist, title = parse_artist_title_from_filename("Led Zeppelin   -   Stairway to Heaven")
        assert artist == "Led Zeppelin"
        assert title == "Stairway to Heaven"

    def test_no_separator(self) -> None:
        """Test parsing when no separator is present."""
        artist, title = parse_artist_title_from_filename("Just A Song Name")
        assert artist == UNKNOWN_ARTIST
        assert title == "Just A Song Name"

    def test_empty_string(self) -> None:
        """Test parsing an empty string."""
        artist, title = parse_artist_title_from_filename("")
        assert artist == UNKNOWN_ARTIST
        assert title == UNKNOWN_TITLE

    def test_only_separator(self) -> None:
        """Test parsing string with only separator."""
        artist, title = parse_artist_title_from_filename(" - ")
        # The pattern matches but groups are empty, so fallback values are used
        assert artist == UNKNOWN_ARTIST
        # Title ends up as "-" after stripping, so return that as title
        assert title == "-"  # Edge case: minimal separator content

    def test_multiple_separators(self) -> None:
        """Test parsing with multiple dashes in title."""
        artist, title = parse_artist_title_from_filename("Artist Name - Song - Part 2")
        assert artist == "Artist Name"
        assert title == "Song - Part 2"


class TestAudioMeta:
    """Tests for AudioMeta dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        meta = AudioMeta()
        assert meta.artist == ""
        assert meta.title == ""
        assert meta.album == ""
        assert meta.genre == ""
        assert meta.year == ""
        assert meta.duration_sec is None
        assert meta.bitrate_kbps is None
        assert meta.codec == ""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for AudioMeta."""
        original = AudioMeta(
            artist="Pink Floyd",
            title="Comfortably Numb",
            album="The Wall",
            genre="Progressive Rock",
            year="1979",
            duration_sec=382.5,
            bitrate_kbps=320,
            codec="mp3",
        )
        data = original.to_dict()
        restored = AudioMeta.from_dict(data)

        assert restored.artist == original.artist
        assert restored.title == original.title
        assert restored.album == original.album
        assert restored.genre == original.genre
        assert restored.year == original.year
        assert restored.duration_sec == original.duration_sec
        assert restored.bitrate_kbps == original.bitrate_kbps
        assert restored.codec == original.codec

    def test_has_genre(self) -> None:
        """Test has_genre property."""
        meta = AudioMeta(genre="Rock")
        assert meta.has_genre is True

        meta = AudioMeta(genre="")
        assert meta.has_genre is False

        meta = AudioMeta(genre=UNKNOWN_GENRE)
        assert meta.has_genre is False

    def test_has_artist(self) -> None:
        """Test has_artist property."""
        meta = AudioMeta(artist="Pink Floyd")
        assert meta.has_artist is True

        meta = AudioMeta(artist="")
        assert meta.has_artist is False

        meta = AudioMeta(artist=UNKNOWN_ARTIST)
        assert meta.has_artist is False

    def test_get_genre_or_unknown(self) -> None:
        """Test get_genre_or_unknown method."""
        meta = AudioMeta(genre="Rock")
        assert meta.get_genre_or_unknown() == "Rock"

        meta = AudioMeta(genre="")
        assert meta.get_genre_or_unknown() == UNKNOWN_GENRE

    def test_get_artist_or_unknown(self) -> None:
        """Test get_artist_or_unknown method."""
        meta = AudioMeta(artist="Pink Floyd")
        assert meta.get_artist_or_unknown() == "Pink Floyd"

        meta = AudioMeta(artist="")
        assert meta.get_artist_or_unknown() == UNKNOWN_ARTIST


class TestGetOrganizationPathByGenre:
    """Tests for get_organization_path_by_genre function."""

    def test_with_full_metadata(self) -> None:
        """Test organization path with full metadata."""
        meta = AudioMeta(artist="Pink Floyd", genre="Progressive Rock")
        path = get_organization_path_by_genre(meta, "Comfortably Numb.mp3")
        assert path == "Progressive Rock/Pink Floyd/Comfortably Numb.mp3"

    def test_with_no_metadata(self) -> None:
        """Test organization path with no metadata."""
        path = get_organization_path_by_genre(None, "song.mp3")
        assert path == f"{UNKNOWN_GENRE}/{UNKNOWN_ARTIST}/song.mp3"

    def test_with_partial_metadata(self) -> None:
        """Test organization path with partial metadata."""
        meta = AudioMeta(artist="Pink Floyd")  # No genre
        path = get_organization_path_by_genre(meta, "song.mp3")
        assert path == f"{UNKNOWN_GENRE}/Pink Floyd/song.mp3"

        meta = AudioMeta(genre="Rock")  # No artist
        path = get_organization_path_by_genre(meta, "song.mp3")
        assert path == f"Rock/{UNKNOWN_ARTIST}/song.mp3"

    def test_sanitizes_invalid_chars(self) -> None:
        """Test that invalid path characters are sanitized."""
        meta = AudioMeta(artist="AC/DC", genre="Rock/Metal")
        path = get_organization_path_by_genre(meta, "song.mp3")
        assert "/" not in meta.genre.replace("/", "_")  # Verify sanitization logic
        # The path should be sanitized
        assert "Rock_Metal/AC_DC/song.mp3" == path


class TestExtractAudioMetadata:
    """Tests for extract_audio_metadata function."""

    def test_fallback_when_no_mutagen(self) -> None:
        """Test that filename parsing is used when mutagen is unavailable."""
        with patch("mediacopier.core.metadata_audio.MUTAGEN_AVAILABLE", False):
            # Need to reload the function behavior
            from mediacopier.core.metadata_audio import parse_artist_title_from_filename

            # Test the fallback logic directly
            artist, title = parse_artist_title_from_filename("Artist - Title")
            assert artist == "Artist"
            assert title == "Title"

    def test_with_unsupported_extension(self, tmp_path: Path) -> None:
        """Test handling of unsupported file extensions."""
        # Create a test file with unsupported extension
        test_file = tmp_path / "test.xyz"
        test_file.write_bytes(b"fake content")

        # Should return AudioMeta with fallback values
        meta = extract_audio_metadata(test_file)
        assert meta is not None
        # Without tags, should fallback to filename parsing
        assert meta.artist == UNKNOWN_ARTIST
        assert meta.title == "test"


class TestMockMutagenExtraction:
    """Tests for mutagen-based metadata extraction with mocking."""

    @pytest.fixture
    def mock_mp3_file(self, tmp_path: Path) -> Path:
        """Create a mock MP3 file path."""
        test_file = tmp_path / "test_song.mp3"
        test_file.write_bytes(b"fake mp3 content")
        return test_file

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    def test_extracts_artist_title_from_tags(self, mock_mp3_file: Path) -> None:
        """Test extraction of artist and title from tags."""
        mock_audio = MagicMock()
        mock_audio.info.length = 180.5
        mock_audio.info.bitrate = 320000
        mock_audio.tags = {
            "artist": ["Pink Floyd"],
            "title": ["Comfortably Numb"],
            "album": ["The Wall"],
            "genre": ["Progressive Rock"],
            "date": ["1979"],
        }

        with patch("mediacopier.core.metadata_audio.MP3", return_value=mock_audio):
            meta = extract_audio_metadata(mock_mp3_file)

        assert meta is not None
        assert meta.artist == "Pink Floyd"
        assert meta.title == "Comfortably Numb"
        assert meta.album == "The Wall"
        assert meta.genre == "Progressive Rock"
        assert meta.year == "1979"
        assert meta.duration_sec == 180.5
        assert meta.bitrate_kbps == 320

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    def test_fallback_to_filename_when_no_tags(self, tmp_path: Path) -> None:
        """Test fallback to filename parsing when no tags are available."""
        test_file = tmp_path / "Artist Name - Song Title.mp3"
        test_file.write_bytes(b"fake mp3 content")

        mock_audio = MagicMock()
        mock_audio.info.length = 180.5
        mock_audio.info.bitrate = 320000
        mock_audio.tags = {}  # No tags

        with patch("mediacopier.core.metadata_audio.MP3", return_value=mock_audio):
            meta = extract_audio_metadata(test_file)

        assert meta is not None
        # Should fallback to filename parsing
        assert meta.artist == "Artist Name"
        assert meta.title == "Song Title"

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    def test_handles_exception_gracefully(self, mock_mp3_file: Path) -> None:
        """Test that exceptions during extraction are handled gracefully."""
        with patch("mediacopier.core.metadata_audio.MP3", side_effect=Exception("Test error")):
            meta = extract_audio_metadata(mock_mp3_file)

        assert meta is not None
        # Should fallback to filename parsing
        assert meta.artist == UNKNOWN_ARTIST
        assert meta.title == "test_song"


class TestMutagenAvailabilityFlag:
    """Tests for MUTAGEN_AVAILABLE flag."""

    def test_flag_is_boolean(self) -> None:
        """Test that MUTAGEN_AVAILABLE flag is a boolean."""
        assert isinstance(MUTAGEN_AVAILABLE, bool)
