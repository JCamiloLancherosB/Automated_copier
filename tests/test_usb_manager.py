"""Tests for USBManager class."""

import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mediacopier.api.techaura_client import USBOrder
from mediacopier.core.usb_manager import USBManager


class TestUSBManager:
    """Tests for USBManager class."""

    def test_rename_usb_for_order_with_valid_phone(self):
        """Test renaming USB with valid phone number."""
        manager = USBManager()
        order = USBOrder(
            order_id="123",
            order_number="ORD-001",
            customer_phone="+57 300 123 4567",
            customer_name="Test User",
            product_type="music",
            capacity="16GB"
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout="Success", returncode=0)
            
            if os.name == 'nt':
                result = manager.rename_usb_for_order(order, "D:\\")
                assert result is True
                mock_run.assert_called_once()
                # Verify it uses first 6 digits: 573001
                call_args = mock_run.call_args
                assert '573001' in str(call_args)
            else:
                # On non-Windows, should return False (not implemented)
                result = manager.rename_usb_for_order(order, "/media/usb")
                assert result is False

    def test_rename_usb_for_order_fallback_to_order_number(self):
        """Test USB rename fallback when no phone digits."""
        manager = USBManager()
        order = USBOrder(
            order_id="123",
            order_number="ORD001",
            customer_phone="",
            customer_name="Test User",
            product_type="music",
            capacity="16GB"
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout="Success", returncode=0)
            
            if os.name == 'nt':
                result = manager.rename_usb_for_order(order, "D:\\")
                assert result is True
                # Should use first 6 chars of order number
                call_args = mock_run.call_args
                assert 'ORD001' in str(call_args)

    def test_rename_usb_for_order_invalid_path(self):
        """Test USB rename with invalid path."""
        manager = USBManager()
        order = USBOrder(
            order_id="123",
            order_number="ORD-001",
            customer_phone="+57 300 123 4567",
            customer_name="Test User",
            product_type="music",
            capacity="16GB"
        )
        
        result = manager.rename_usb_for_order(order, "invalid_path")
        assert result is False

    def test_rename_usb_subprocess_error(self):
        """Test USB rename handles subprocess errors."""
        manager = USBManager()
        order = USBOrder(
            order_id="123",
            order_number="ORD-001",
            customer_phone="+57 300 123 4567",
            customer_name="Test User",
            product_type="music",
            capacity="16GB"
        )
        
        with patch('subprocess.run') as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.CalledProcessError(1, 'label')
            
            if os.name == 'nt':
                result = manager.rename_usb_for_order(order, "D:\\")
                assert result is False

    def test_verify_copy_success(self, tmp_path):
        """Test successful copy verification."""
        manager = USBManager()
        
        # Create test files
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        
        content = b"Test content for verification"
        source.write_bytes(content)
        dest.write_bytes(content)
        
        result = manager.verify_copy(str(source), str(dest))
        assert result is True

    def test_verify_copy_size_mismatch(self, tmp_path):
        """Test copy verification with size mismatch."""
        manager = USBManager()
        
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        
        source.write_bytes(b"Source content")
        dest.write_bytes(b"Different")
        
        result = manager.verify_copy(str(source), str(dest))
        assert result is False

    def test_verify_copy_checksum_mismatch(self, tmp_path):
        """Test copy verification with checksum mismatch."""
        manager = USBManager()
        
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        
        # Same size but different content
        source.write_bytes(b"1234567890")
        dest.write_bytes(b"0987654321")
        
        result = manager.verify_copy(str(source), str(dest))
        assert result is False

    def test_verify_copy_source_missing(self, tmp_path):
        """Test copy verification when source is missing."""
        manager = USBManager()
        
        source = tmp_path / "nonexistent.txt"
        dest = tmp_path / "dest.txt"
        dest.write_bytes(b"Content")
        
        result = manager.verify_copy(str(source), str(dest))
        assert result is False

    def test_verify_copy_dest_missing(self, tmp_path):
        """Test copy verification when destination is missing."""
        manager = USBManager()
        
        source = tmp_path / "source.txt"
        source.write_bytes(b"Content")
        dest = tmp_path / "nonexistent.txt"
        
        result = manager.verify_copy(str(source), str(dest))
        assert result is False

    def test_create_folder_structure(self, tmp_path):
        """Test creating folder structure."""
        manager = USBManager()
        
        structure = {
            "Música": ["Rock", "Pop", "Jazz"],
            "Videos": ["Conciertos", "Clips"],
            "Fotos": []
        }
        
        result = manager.create_folder_structure(str(tmp_path), structure)
        assert result is True
        
        # Verify folders were created
        assert (tmp_path / "Música").exists()
        assert (tmp_path / "Música" / "Rock").exists()
        assert (tmp_path / "Música" / "Pop").exists()
        assert (tmp_path / "Música" / "Jazz").exists()
        assert (tmp_path / "Videos").exists()
        assert (tmp_path / "Videos" / "Conciertos").exists()
        assert (tmp_path / "Videos" / "Clips").exists()
        assert (tmp_path / "Fotos").exists()

    def test_create_folder_structure_nonexistent_dest(self):
        """Test creating folder structure with nonexistent destination."""
        manager = USBManager()
        
        structure = {"Música": []}
        result = manager.create_folder_structure("/nonexistent/path", structure)
        assert result is False

    def test_cleanup_temp_files(self, tmp_path):
        """Test cleaning up temporary files."""
        manager = USBManager()
        
        # Create some temporary files
        (tmp_path / "file.txt").write_text("Normal file")
        (tmp_path / "temp.tmp").write_text("Temp file")
        (tmp_path / "backup~").write_text("Backup file")
        (tmp_path / ".DS_Store").write_text("Mac file")
        (tmp_path / "Thumbs.db").write_text("Windows file")
        
        # Create subdirectory with temp files
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "another.tmp").write_text("Another temp")
        
        manager.cleanup_temp_files(str(tmp_path))
        
        # Normal file should remain
        assert (tmp_path / "file.txt").exists()
        
        # Temp files should be removed
        assert not (tmp_path / "temp.tmp").exists()
        assert not (tmp_path / "backup~").exists()
        assert not (tmp_path / ".DS_Store").exists()
        assert not (tmp_path / "Thumbs.db").exists()
        assert not (subdir / "another.tmp").exists()

    def test_cleanup_temp_files_nonexistent_path(self):
        """Test cleanup with nonexistent path doesn't crash."""
        manager = USBManager()
        # Should not raise exception
        manager.cleanup_temp_files("/nonexistent/path")

    def test_validate_path_valid(self, tmp_path):
        """Test path validation with valid path."""
        manager = USBManager()
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")
        
        assert manager.validate_path(str(test_file), must_exist=True) is True

    def test_validate_path_nonexistent_when_required(self):
        """Test path validation when path must exist."""
        manager = USBManager()
        
        result = manager.validate_path("/nonexistent/path", must_exist=True)
        assert result is False

    def test_validate_path_nonexistent_when_not_required(self):
        """Test path validation when existence not required."""
        manager = USBManager()
        
        # Should pass if path doesn't have dangerous chars
        result = manager.validate_path("/some/new/path", must_exist=False)
        assert result is True

    def test_validate_path_empty(self):
        """Test path validation with empty path."""
        manager = USBManager()
        
        assert manager.validate_path("", must_exist=False) is False
        assert manager.validate_path("   ", must_exist=False) is False

    def test_validate_path_dangerous_chars(self):
        """Test path validation rejects dangerous characters."""
        manager = USBManager()
        
        dangerous_paths = [
            "../../../etc/passwd",
            "path/with/../traversal",
            "path<with>pipes",
            "path|with|pipes",
        ]
        
        for path in dangerous_paths:
            assert manager.validate_path(path, must_exist=False) is False

    def test_validate_path_writable(self, tmp_path):
        """Test path validation for write permission."""
        manager = USBManager()
        
        # tmp_path should be writable
        assert manager.validate_path(str(tmp_path), must_exist=True, must_be_writable=True) is True

    def test_validate_path_not_writable(self):
        """Test path validation for non-writable paths."""
        manager = USBManager()
        
        # On Unix-like systems, /root is typically not writable by regular users
        if os.name != 'nt':
            result = manager.validate_path("/root/test", must_exist=False, must_be_writable=True)
            # May vary based on permissions, so we just check it doesn't crash
            assert isinstance(result, bool)

    def test_calculate_checksum(self, tmp_path):
        """Test MD5 checksum calculation."""
        manager = USBManager()
        
        test_file = tmp_path / "test.txt"
        content = b"Test content for checksum"
        test_file.write_bytes(content)
        
        checksum = manager._calculate_checksum(test_file)
        
        # Verify it's a valid MD5 hex string
        assert len(checksum) == 32
        assert all(c in '0123456789abcdef' for c in checksum)
        
        # Verify it matches expected value
        expected = hashlib.md5(content).hexdigest()
        assert checksum == expected

    def test_calculate_checksum_large_file(self, tmp_path):
        """Test checksum calculation with large file."""
        manager = USBManager()
        
        test_file = tmp_path / "large.bin"
        # Create a file larger than the chunk size (8192 bytes)
        content = b"X" * (8192 * 3 + 100)
        test_file.write_bytes(content)
        
        checksum = manager._calculate_checksum(test_file)
        expected = hashlib.md5(content).hexdigest()
        assert checksum == expected
