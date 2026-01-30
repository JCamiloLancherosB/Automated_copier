"""Unit tests for duplicate_detector module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mediacopier.core.duplicate_detector import (
    DuplicateDetector,
    DuplicateGroup,
    DuplicateMethod,
)


class TestDuplicateMethod:
    """Tests for DuplicateMethod enum."""

    def test_enum_values(self) -> None:
        """Test that all expected enum values exist."""
        assert DuplicateMethod.BY_NAME.value == "by_name"
        assert DuplicateMethod.BY_HASH.value == "by_hash"
        assert DuplicateMethod.BY_METADATA.value == "by_metadata"
        assert DuplicateMethod.BY_SIZE_DURATION.value == "by_size_duration"
        assert DuplicateMethod.SMART.value == "smart"


class TestDuplicateGroup:
    """Tests for DuplicateGroup dataclass."""

    def test_creation(self) -> None:
        """Test creating a DuplicateGroup."""
        group = DuplicateGroup(
            original="/path/to/file1.mp3",
            duplicates=["/path/to/file2.mp3", "/path/to/file3.mp3"],
            method=DuplicateMethod.BY_HASH,
            confidence=0.99,
        )
        assert group.original == "/path/to/file1.mp3"
        assert len(group.duplicates) == 2
        assert group.method == DuplicateMethod.BY_HASH
        assert group.confidence == 0.99


class TestNormalizeFilename:
    """Tests for _normalize_filename method."""

    def test_basic_normalization(self) -> None:
        """Test basic filename normalization."""
        detector = DuplicateDetector()
        assert detector._normalize_filename("Song Name.mp3") == "songname"

    def test_remove_leading_numbers(self) -> None:
        """Test removal of leading numbers."""
        detector = DuplicateDetector()
        assert detector._normalize_filename("01 - Song Name.mp3") == "songname"
        assert detector._normalize_filename("001. Song Name.mp3") == "songname"
        assert detector._normalize_filename("123_Song Name.mp3") == "songname"

    def test_remove_special_chars(self) -> None:
        """Test removal of special characters."""
        detector = DuplicateDetector()
        assert detector._normalize_filename("Song-Name!@#.mp3") == "songname"
        assert detector._normalize_filename("Song (Live).mp3") == "songlive"

    def test_case_insensitive(self) -> None:
        """Test case insensitivity."""
        detector = DuplicateDetector()
        assert detector._normalize_filename("SONG NAME.mp3") == "songname"
        assert detector._normalize_filename("Song Name.mp3") == "songname"


class TestFindByName:
    """Tests for finding duplicates by name."""

    def test_find_duplicates_by_name(self) -> None:
        """Test finding duplicates with similar names."""
        detector = DuplicateDetector()
        files = [
            "/music/01 - Song Name.mp3",
            "/music/Song Name.mp3",
            "/music/02 - Another Song.mp3",
        ]
        duplicates = detector._find_by_name(files)

        assert len(duplicates) == 1
        assert duplicates[0].method == DuplicateMethod.BY_NAME
        assert duplicates[0].confidence == 0.7
        assert len(duplicates[0].duplicates) == 1

    def test_no_duplicates_by_name(self) -> None:
        """Test when no duplicates exist."""
        detector = DuplicateDetector()
        files = [
            "/music/Song One.mp3",
            "/music/Song Two.mp3",
            "/music/Song Three.mp3",
        ]
        duplicates = detector._find_by_name(files)

        assert len(duplicates) == 0

    def test_multiple_duplicate_groups(self) -> None:
        """Test multiple groups of duplicates."""
        detector = DuplicateDetector()
        files = [
            "/music/01 - Song A.mp3",
            "/music/Song A.mp3",
            "/music/01 - Song B.mp3",
            "/music/Song B.mp3",
        ]
        duplicates = detector._find_by_name(files)

        assert len(duplicates) == 2


class TestGetFileHash:
    """Tests for _get_file_hash method."""

    def test_hash_quick_mode(self) -> None:
        """Test quick hash calculation."""
        detector = DuplicateDetector()
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content" * 10000)
            tmp.flush()
            hash1 = detector._get_file_hash(tmp.name, quick=True)
            assert len(hash1) == 32  # MD5 hash length
            Path(tmp.name).unlink()

    def test_hash_full_mode(self) -> None:
        """Test full hash calculation."""
        detector = DuplicateDetector()
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content" * 10000)
            tmp.flush()
            hash1 = detector._get_file_hash(tmp.name, quick=False)
            assert len(hash1) == 32  # MD5 hash length
            Path(tmp.name).unlink()

    def test_hash_nonexistent_file(self) -> None:
        """Test hash calculation for nonexistent file."""
        detector = DuplicateDetector()
        hash_val = detector._get_file_hash("/nonexistent/file.mp3", quick=True)
        assert hash_val == ""


class TestFindByHash:
    """Tests for finding duplicates by hash."""

    def test_find_duplicates_by_hash(self) -> None:
        """Test finding duplicates with same content."""
        detector = DuplicateDetector()

        # Create two temporary files with same content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp1:
            tmp1.write(b"same content" * 10000)
            tmp1.flush()
            file1 = tmp1.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp2:
            tmp2.write(b"same content" * 10000)
            tmp2.flush()
            file2 = tmp2.name

        try:
            files = [file1, file2]
            duplicates = detector._find_by_hash(files)

            assert len(duplicates) == 1
            assert duplicates[0].method == DuplicateMethod.BY_HASH
            assert duplicates[0].confidence == 0.99
            assert len(duplicates[0].duplicates) == 1
        finally:
            Path(file1).unlink()
            Path(file2).unlink()

    def test_no_duplicates_by_hash(self) -> None:
        """Test when files have different content."""
        detector = DuplicateDetector()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp1:
            tmp1.write(b"content 1" * 10000)
            tmp1.flush()
            file1 = tmp1.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp2:
            tmp2.write(b"content 2" * 10000)
            tmp2.flush()
            file2 = tmp2.name

        try:
            files = [file1, file2]
            duplicates = detector._find_by_hash(files)

            assert len(duplicates) == 0
        finally:
            Path(file1).unlink()
            Path(file2).unlink()


class TestFindByMetadata:
    """Tests for finding duplicates by metadata."""

    def test_find_by_metadata_no_mutagen(self) -> None:
        """Test when mutagen is not available."""
        detector = DuplicateDetector()
        # Patch the import inside the function
        with patch.dict("sys.modules", {"mutagen.easyid3": None}):
            files = ["/music/song1.mp3", "/music/song2.mp3"]
            duplicates = detector._find_by_metadata(files)
            assert len(duplicates) == 0

    def test_find_by_metadata_with_mutagen(self) -> None:
        """Test finding duplicates by ID3 tags."""
        try:
            from mutagen.easyid3 import EasyID3
        except ImportError:
            pytest.skip("mutagen not available")

        detector = DuplicateDetector()

        mock_audio1 = {"artist": ["Test Artist"], "title": ["Test Title"]}
        mock_audio2 = {"artist": ["Test Artist"], "title": ["Test Title"]}

        with patch("mutagen.easyid3.EasyID3") as mock_easyid3:
            mock_easyid3.side_effect = [
                MagicMock(get=lambda k, d: mock_audio1.get(k, d)),
                MagicMock(get=lambda k, d: mock_audio2.get(k, d)),
            ]

            files = ["/music/song1.mp3", "/music/song2.mp3"]
            duplicates = detector._find_by_metadata(files)

            assert len(duplicates) == 1
            assert duplicates[0].method == DuplicateMethod.BY_METADATA
            assert duplicates[0].confidence == 0.85

    def test_find_by_metadata_handles_exceptions(self) -> None:
        """Test that exceptions are handled gracefully."""
        try:
            from mutagen.easyid3 import EasyID3
        except ImportError:
            pytest.skip("mutagen not available")

        detector = DuplicateDetector()

        with patch("mutagen.easyid3.EasyID3", side_effect=Exception("Error")):
            files = ["/music/song1.mp3"]
            duplicates = detector._find_by_metadata(files)
            assert len(duplicates) == 0


class TestFindBySize:
    """Tests for finding duplicates by size."""

    def test_find_duplicates_by_size(self) -> None:
        """Test finding duplicates with same size."""
        detector = DuplicateDetector()

        # Create two files with same size and content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp1:
            tmp1.write(b"x" * 10000)
            tmp1.flush()
            file1 = tmp1.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp2:
            tmp2.write(b"x" * 10000)
            tmp2.flush()
            file2 = tmp2.name

        try:
            files = [file1, file2]
            duplicates = detector._find_by_size(files)

            assert len(duplicates) == 1
            assert duplicates[0].method == DuplicateMethod.BY_SIZE_DURATION
            assert duplicates[0].confidence == 0.95
        finally:
            Path(file1).unlink()
            Path(file2).unlink()

    def test_no_duplicates_by_size(self) -> None:
        """Test when files have different sizes."""
        detector = DuplicateDetector()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp1:
            tmp1.write(b"x" * 10000)
            tmp1.flush()
            file1 = tmp1.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp2:
            tmp2.write(b"y" * 20000)
            tmp2.flush()
            file2 = tmp2.name

        try:
            files = [file1, file2]
            duplicates = detector._find_by_size(files)

            assert len(duplicates) == 0
        finally:
            Path(file1).unlink()
            Path(file2).unlink()


class TestFindSmart:
    """Tests for smart duplicate detection."""

    def test_smart_combines_methods(self) -> None:
        """Test that smart detection combines multiple methods."""
        detector = DuplicateDetector()

        # Create test files
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp1:
            tmp1.write(b"content" * 10000)
            tmp1.flush()
            file1 = tmp1.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp2:
            tmp2.write(b"content" * 10000)
            tmp2.flush()
            file2 = tmp2.name

        try:
            files = [file1, file2]
            duplicates = detector._find_smart(files)

            # Should find at least by size
            assert len(duplicates) >= 1
        finally:
            Path(file1).unlink()
            Path(file2).unlink()


class TestGetUniqueFiles:
    """Tests for get_unique_files method."""

    def test_get_unique_files(self) -> None:
        """Test getting list of unique files."""
        detector = DuplicateDetector()
        files = [
            "/music/01 - Song Name.mp3",
            "/music/Song Name.mp3",
            "/music/Different Song.mp3",
        ]
        unique = detector.get_unique_files(files, method=DuplicateMethod.BY_NAME)

        # Should have 2 unique files (one duplicate removed)
        assert len(unique) == 2

    def test_all_unique_files(self) -> None:
        """Test when all files are unique."""
        detector = DuplicateDetector()
        files = [
            "/music/Song One.mp3",
            "/music/Song Two.mp3",
            "/music/Song Three.mp3",
        ]
        unique = detector.get_unique_files(files, method=DuplicateMethod.BY_NAME)

        assert len(unique) == 3


class TestGenerateReport:
    """Tests for generate_report method."""

    def test_report_no_duplicates(self) -> None:
        """Test report when no duplicates found."""
        detector = DuplicateDetector()
        report = detector.generate_report([])

        assert "✅" in report
        assert "No se encontraron" in report

    def test_report_with_duplicates(self) -> None:
        """Test report generation with duplicates."""
        detector = DuplicateDetector()
        groups = [
            DuplicateGroup(
                original="/music/song1.mp3",
                duplicates=["/music/song2.mp3", "/music/song3.mp3"],
                method=DuplicateMethod.BY_HASH,
                confidence=0.99,
            )
        ]
        report = detector.generate_report(groups)

        assert "⚠️" in report
        assert "grupos de duplicados" in report
        assert "99%" in report
        assert "song1.mp3" in report
        assert "song2.mp3" in report
        assert "2 archivos duplicados" in report


class TestFindDuplicates:
    """Tests for main find_duplicates method."""

    def test_find_duplicates_by_name_method(self) -> None:
        """Test calling find_duplicates with BY_NAME method."""
        detector = DuplicateDetector()
        files = ["/music/01 - Song.mp3", "/music/Song.mp3"]
        duplicates = detector.find_duplicates(files, method=DuplicateMethod.BY_NAME)

        assert len(duplicates) == 1
        assert duplicates[0].method == DuplicateMethod.BY_NAME

    def test_find_duplicates_smart_method(self) -> None:
        """Test calling find_duplicates with SMART method."""
        detector = DuplicateDetector()
        files = ["/music/song1.mp3", "/music/song2.mp3"]
        duplicates = detector.find_duplicates(files, method=DuplicateMethod.SMART)

        # Should return a list (empty or with results)
        assert isinstance(duplicates, list)
