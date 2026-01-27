"""Unit tests for USB drive detection module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mediacopier.core.usb_detector import (
    RemovableDrive,
    USBPermissionError,
    USBWriteError,
    _get_disk_space,
    _is_path_writable,
    detect_removable_drives,
    format_drive_size,
    get_drive_display_name,
    get_usb_movies_folder_structure,
    get_usb_music_folder_structure,
    pre_create_folders,
    validate_usb_destination,
)


class TestRemovableDrive:
    """Tests for RemovableDrive dataclass."""

    def test_creation(self) -> None:
        """Test basic creation of RemovableDrive."""
        drive = RemovableDrive(
            path="/media/usb",
            label="My USB",
            is_writable=True,
            total_space=16 * 1024**3,  # 16 GB
            free_space=8 * 1024**3,  # 8 GB
        )
        assert drive.path == "/media/usb"
        assert drive.label == "My USB"
        assert drive.is_writable is True
        assert drive.total_space == 16 * 1024**3
        assert drive.free_space == 8 * 1024**3

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for RemovableDrive."""
        original = RemovableDrive(
            path="/Volumes/USB",
            label="USB Drive",
            is_writable=True,
            total_space=32 * 1024**3,
            free_space=20 * 1024**3,
        )
        data = original.to_dict()
        restored = RemovableDrive.from_dict(data)

        assert restored.path == original.path
        assert restored.label == original.label
        assert restored.is_writable == original.is_writable
        assert restored.total_space == original.total_space
        assert restored.free_space == original.free_space

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        drive = RemovableDrive(
            path="/media/usb",
            label="USB",
            is_writable=False,
        )
        assert drive.total_space == 0
        assert drive.free_space == 0


class TestIsPathWritable:
    """Tests for _is_path_writable function."""

    def test_writable_path(self, tmp_path: Path) -> None:
        """Test that a writable path returns True."""
        assert _is_path_writable(str(tmp_path)) is True

    def test_nonexistent_path(self) -> None:
        """Test that a nonexistent path returns False."""
        assert _is_path_writable("/nonexistent/path/12345") is False

    def test_permission_error(self, tmp_path: Path) -> None:
        """Test handling of permission errors."""
        with patch("os.access", side_effect=PermissionError("Access denied")):
            # Should return False, not raise
            assert _is_path_writable(str(tmp_path)) is False


class TestGetDiskSpace:
    """Tests for _get_disk_space function."""

    def test_valid_path(self, tmp_path: Path) -> None:
        """Test getting disk space for a valid path."""
        total, free = _get_disk_space(str(tmp_path))
        # Should return positive values
        assert total > 0
        assert free >= 0
        assert free <= total

    def test_invalid_path(self) -> None:
        """Test getting disk space for an invalid path."""
        total, free = _get_disk_space("/nonexistent/path/12345")
        # Should return zeros, not raise
        assert total == 0
        assert free == 0


class TestValidateUSBDestination:
    """Tests for validate_usb_destination function."""

    def test_empty_path(self) -> None:
        """Test validation fails for empty path."""
        is_valid, error = validate_usb_destination("")
        assert is_valid is False
        assert "vacía" in error.lower()

    def test_nonexistent_path(self) -> None:
        """Test validation fails for nonexistent path."""
        is_valid, error = validate_usb_destination("/nonexistent/path/12345")
        assert is_valid is False
        assert "no existe" in error.lower()

    def test_valid_path(self, tmp_path: Path) -> None:
        """Test validation passes for a valid writable directory."""
        is_valid, error = validate_usb_destination(str(tmp_path))
        assert is_valid is True
        assert error == ""

    def test_file_instead_of_directory(self, tmp_path: Path) -> None:
        """Test validation fails when path is a file."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        is_valid, error = validate_usb_destination(str(file_path))
        assert is_valid is False
        assert "no es un directorio" in error.lower()


class TestPreCreateFolders:
    """Tests for pre_create_folders function."""

    def test_create_single_folder(self, tmp_path: Path) -> None:
        """Test creating a single folder."""
        success, error = pre_create_folders(str(tmp_path), ["Music"])
        assert success is True
        assert error == ""
        assert (tmp_path / "Music").exists()

    def test_create_nested_folders(self, tmp_path: Path) -> None:
        """Test creating nested folders."""
        folders = ["Music", "Music/Rock", "Music/Rock/Pink Floyd"]
        success, error = pre_create_folders(str(tmp_path), folders)
        assert success is True
        assert error == ""
        assert (tmp_path / "Music" / "Rock" / "Pink Floyd").exists()

    def test_create_multiple_top_level_folders(self, tmp_path: Path) -> None:
        """Test creating multiple top-level folders."""
        folders = ["Music", "Movies", "Documents"]
        success, error = pre_create_folders(str(tmp_path), folders)
        assert success is True
        assert error == ""
        for folder in folders:
            assert (tmp_path / folder).exists()

    def test_invalid_base_path(self) -> None:
        """Test that invalid base path returns error."""
        success, error = pre_create_folders("/nonexistent/path", ["Music"])
        assert success is False
        assert "no existe" in error.lower()

    def test_permission_error(self, tmp_path: Path) -> None:
        """Test handling of permission errors during folder creation."""
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Access denied")):
            with pytest.raises(USBPermissionError):
                pre_create_folders(str(tmp_path), ["Music"])

    def test_write_error(self, tmp_path: Path) -> None:
        """Test handling of OS errors during folder creation."""
        with patch("pathlib.Path.mkdir", side_effect=OSError("Disk full")):
            with pytest.raises(USBWriteError):
                pre_create_folders(str(tmp_path), ["Music"])


class TestGetUSBMusicFolderStructure:
    """Tests for get_usb_music_folder_structure function."""

    def test_basic_structure(self) -> None:
        """Test basic music folder structure."""
        folders = get_usb_music_folder_structure()
        assert "Music" in folders

    def test_with_genres(self) -> None:
        """Test music folder structure with genres."""
        genres = ["Rock", "Jazz", "Classical"]
        folders = get_usb_music_folder_structure(genres)
        assert "Music" in folders
        assert "Music/Rock" in folders
        assert "Music/Jazz" in folders
        assert "Music/Classical" in folders

    def test_genre_sanitization(self) -> None:
        """Test that genre names with special characters are sanitized."""
        genres = ["Rock & Roll", "R&B/Soul", "Hip-Hop"]
        folders = get_usb_music_folder_structure(genres)
        # Check that folders were created but special chars were handled
        assert any("Rock" in f for f in folders)
        assert any("Hip-Hop" in f for f in folders)


class TestGetUSBMoviesFolderStructure:
    """Tests for get_usb_movies_folder_structure function."""

    def test_basic_structure(self) -> None:
        """Test basic movies folder structure."""
        folders = get_usb_movies_folder_structure()
        assert "Movies" in folders


class TestFormatDriveSize:
    """Tests for format_drive_size function."""

    def test_bytes(self) -> None:
        """Test formatting bytes."""
        assert format_drive_size(500) == "500 B"

    def test_kilobytes(self) -> None:
        """Test formatting kilobytes."""
        assert "KB" in format_drive_size(1500)

    def test_megabytes(self) -> None:
        """Test formatting megabytes."""
        assert "MB" in format_drive_size(5 * 1024**2)

    def test_gigabytes(self) -> None:
        """Test formatting gigabytes."""
        assert "GB" in format_drive_size(8 * 1024**3)

    def test_terabytes(self) -> None:
        """Test formatting terabytes."""
        assert "TB" in format_drive_size(2 * 1024**4)


class TestGetDriveDisplayName:
    """Tests for get_drive_display_name function."""

    def test_writable_drive(self) -> None:
        """Test display name for writable drive."""
        drive = RemovableDrive(
            path="/media/usb",
            label="My USB",
            is_writable=True,
            total_space=16 * 1024**3,
            free_space=8 * 1024**3,
        )
        display = get_drive_display_name(drive)
        assert "My USB" in display
        assert "GB" in display
        assert "libre" in display
        assert "Solo lectura" not in display

    def test_readonly_drive(self) -> None:
        """Test display name for read-only drive."""
        drive = RemovableDrive(
            path="/media/usb",
            label="Protected USB",
            is_writable=False,
            total_space=16 * 1024**3,
            free_space=8 * 1024**3,
        )
        display = get_drive_display_name(drive)
        assert "Protected USB" in display
        assert "Solo lectura" in display


class TestDetectRemovableDrives:
    """Tests for detect_removable_drives function."""

    def test_returns_list(self) -> None:
        """Test that function returns a list."""
        drives = detect_removable_drives()
        assert isinstance(drives, list)
        # Each item should be a RemovableDrive
        for drive in drives:
            assert isinstance(drive, RemovableDrive)

    @patch("platform.system")
    def test_windows_detection(self, mock_system: MagicMock) -> None:
        """Test Windows drive detection is called on Windows."""
        mock_system.return_value = "Windows"
        with patch(
            "mediacopier.core.usb_detector._detect_windows_drives"
        ) as mock_detect:
            mock_detect.return_value = []
            detect_removable_drives()
            mock_detect.assert_called_once()

    @patch("platform.system")
    def test_macos_detection(self, mock_system: MagicMock) -> None:
        """Test macOS volume detection is called on macOS."""
        mock_system.return_value = "Darwin"
        with patch(
            "mediacopier.core.usb_detector._detect_macos_volumes"
        ) as mock_detect:
            mock_detect.return_value = []
            detect_removable_drives()
            mock_detect.assert_called_once()

    @patch("platform.system")
    def test_linux_detection(self, mock_system: MagicMock) -> None:
        """Test Linux volume detection is called on Linux."""
        mock_system.return_value = "Linux"
        with patch(
            "mediacopier.core.usb_detector._detect_linux_volumes"
        ) as mock_detect:
            mock_detect.return_value = []
            detect_removable_drives()
            mock_detect.assert_called_once()


class TestUSBTemplateIntegration:
    """Integration tests for USB template functionality."""

    def test_usb_music_template_creates_structure(self, tmp_path: Path) -> None:
        """Test creating USB Music folder structure."""
        genres = ["Rock", "Pop", "Jazz"]
        folders = get_usb_music_folder_structure(genres)
        success, error = pre_create_folders(str(tmp_path), folders)

        assert success is True
        assert (tmp_path / "Music").exists()
        assert (tmp_path / "Music" / "Rock").exists()
        assert (tmp_path / "Music" / "Pop").exists()
        assert (tmp_path / "Music" / "Jazz").exists()

    def test_usb_movies_template_creates_structure(self, tmp_path: Path) -> None:
        """Test creating USB Movies folder structure."""
        folders = get_usb_movies_folder_structure()
        success, error = pre_create_folders(str(tmp_path), folders)

        assert success is True
        assert (tmp_path / "Movies").exists()

    def test_acceptance_criteria_usb_connected_and_copy(self, tmp_path: Path) -> None:
        """Test acceptance criteria: USB connected appears as destination and copies.

        This test simulates the scenario where a USB drive is connected and
        the user can select it as a destination for copying with standard structure.
        """
        # Simulate a detected USB drive
        usb_drive = RemovableDrive(
            path=str(tmp_path),
            label="Test USB",
            is_writable=True,
            total_space=16 * 1024**3,
            free_space=10 * 1024**3,
        )

        # Validate the USB destination
        is_valid, error = validate_usb_destination(usb_drive.path)
        assert is_valid is True

        # Pre-create music folder structure
        folders = get_usb_music_folder_structure(["Rock", "Pop"])
        success, _ = pre_create_folders(usb_drive.path, folders)
        assert success is True

        # Verify standard structure was created
        assert (tmp_path / "Music").exists()
        assert (tmp_path / "Music" / "Rock").exists()
        assert (tmp_path / "Music" / "Pop").exists()

        # Simulate a file copy to the structure
        test_file = tmp_path / "Music" / "Rock" / "test_song.mp3"
        test_file.write_bytes(b"test audio content")
        assert test_file.exists()
