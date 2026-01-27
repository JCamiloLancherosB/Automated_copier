"""USB and removable drive detection for MediaCopier.

This module provides cross-platform detection of removable drives:
- Windows: Detects removable drive letters
- macOS: Detects volumes in /Volumes
- Linux: Detects mounted volumes in common mount points
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class USBWriteError(Exception):
    """Raised when there's an error writing to USB drive."""

    pass


class USBPermissionError(Exception):
    """Raised when there's a permission error accessing USB drive."""

    pass


@dataclass
class RemovableDrive:
    """Represents a detected removable drive."""

    path: str
    label: str
    is_writable: bool
    total_space: int = 0
    free_space: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "path": self.path,
            "label": self.label,
            "is_writable": self.is_writable,
            "total_space": self.total_space,
            "free_space": self.free_space,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RemovableDrive":
        """Deserialize from dictionary."""
        return cls(
            path=data["path"],
            label=data["label"],
            is_writable=data.get("is_writable", False),
            total_space=data.get("total_space", 0),
            free_space=data.get("free_space", 0),
        )


def _is_path_writable(path: str) -> bool:
    """Check if a path is writable by attempting to access it.

    Args:
        path: Path to check.

    Returns:
        True if writable, False otherwise.
    """
    try:
        p = Path(path)
        if not p.exists():
            return False

        # Try to check if we have write permissions
        if os.access(path, os.W_OK):
            return True

        return False
    except (OSError, PermissionError):
        return False


def _get_disk_space(path: str) -> tuple[int, int]:
    """Get total and free space for a path.

    Args:
        path: Path to check.

    Returns:
        Tuple of (total_space, free_space) in bytes.
    """
    try:
        stat_result = os.statvfs(path)
        total = stat_result.f_frsize * stat_result.f_blocks
        free = stat_result.f_frsize * stat_result.f_bavail
        return total, free
    except (OSError, AttributeError):
        # statvfs not available on Windows, use shutil.disk_usage instead
        try:
            import shutil

            usage = shutil.disk_usage(path)
            return usage.total, usage.free
        except (OSError, PermissionError):
            return 0, 0


def _get_volume_label_windows(drive_letter: str) -> str:
    """Get volume label on Windows.

    Args:
        drive_letter: Drive letter like 'E:'

    Returns:
        Volume label or drive letter as fallback.
    """
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        volume_name_buffer = ctypes.create_unicode_buffer(261)
        filesystem_name_buffer = ctypes.create_unicode_buffer(261)

        result = kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive_letter + "\\"),
            volume_name_buffer,
            ctypes.sizeof(volume_name_buffer),
            None,
            None,
            None,
            filesystem_name_buffer,
            ctypes.sizeof(filesystem_name_buffer),
        )

        if result and volume_name_buffer.value:
            return volume_name_buffer.value

        return drive_letter
    except Exception:
        return drive_letter


def _detect_windows_drives() -> list[RemovableDrive]:
    """Detect removable drives on Windows.

    Returns:
        List of detected removable drives.
    """
    drives = []

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        # Get all drive letters
        bitmask = kernel32.GetLogicalDrives()

        for letter_code in range(26):
            if bitmask & (1 << letter_code):
                letter = chr(ord("A") + letter_code)
                drive_path = f"{letter}:\\"

                # Check if it's a removable drive (type 2) or fixed (type 3)
                # We include both for USB support (some USB drives report as fixed)
                drive_type = kernel32.GetDriveTypeW(drive_path)

                # Type 2 = DRIVE_REMOVABLE, Type 3 = DRIVE_FIXED
                # Exclude: 0 = UNKNOWN, 1 = NO_ROOT_DIR, 4 = NETWORK, 5 = CDROM, 6 = RAMDISK
                if drive_type in (2, 3):
                    # Skip C: drive (usually the system drive)
                    if letter == "C":
                        continue

                    if os.path.exists(drive_path):
                        label = _get_volume_label_windows(f"{letter}:")
                        is_writable = _is_path_writable(drive_path)
                        total, free = _get_disk_space(drive_path)

                        drives.append(
                            RemovableDrive(
                                path=drive_path,
                                label=label if label != f"{letter}:" else f"USB ({letter}:)",
                                is_writable=is_writable,
                                total_space=total,
                                free_space=free,
                            )
                        )
    except Exception:
        # If ctypes fails, fall back to checking common drive letters
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                is_writable = _is_path_writable(drive_path)
                total, free = _get_disk_space(drive_path)
                drives.append(
                    RemovableDrive(
                        path=drive_path,
                        label=f"USB ({letter}:)",
                        is_writable=is_writable,
                        total_space=total,
                        free_space=free,
                    )
                )

    return drives


def _detect_macos_volumes() -> list[RemovableDrive]:
    """Detect mounted volumes on macOS.

    Returns:
        List of detected volumes.
    """
    drives = []
    volumes_path = Path("/Volumes")

    if not volumes_path.exists():
        return drives

    try:
        for volume in volumes_path.iterdir():
            # Skip the Macintosh HD (main system volume)
            if volume.name == "Macintosh HD":
                continue

            # Skip hidden volumes
            if volume.name.startswith("."):
                continue

            # Skip symlinks that point to root
            if volume.is_symlink():
                try:
                    if volume.resolve() == Path("/"):
                        continue
                except (OSError, PermissionError):
                    continue

            if volume.is_dir():
                vol_path = str(volume)
                is_writable = _is_path_writable(vol_path)
                total, free = _get_disk_space(vol_path)

                drives.append(
                    RemovableDrive(
                        path=vol_path,
                        label=volume.name,
                        is_writable=is_writable,
                        total_space=total,
                        free_space=free,
                    )
                )
    except PermissionError:
        pass

    return drives


def _detect_linux_volumes() -> list[RemovableDrive]:
    """Detect mounted volumes on Linux.

    Returns:
        List of detected volumes.
    """
    drives = []

    # Common Linux mount points for removable media
    mount_points = [
        Path("/media"),
        Path("/mnt"),
        Path("/run/media"),
    ]

    # Add user-specific media directory
    user = os.environ.get("USER", "")
    if user:
        mount_points.append(Path(f"/media/{user}"))
        mount_points.append(Path(f"/run/media/{user}"))

    seen_paths = set()

    for mount_point in mount_points:
        if not mount_point.exists():
            continue

        try:
            # Check direct mounts at the mount point
            for item in mount_point.iterdir():
                if item.is_dir() and str(item) not in seen_paths:
                    # Skip hidden directories
                    if item.name.startswith("."):
                        continue

                    vol_path = str(item)
                    seen_paths.add(vol_path)

                    is_writable = _is_path_writable(vol_path)
                    total, free = _get_disk_space(vol_path)

                    # Only include if it has some space (indicates it's actually mounted)
                    if total > 0:
                        drives.append(
                            RemovableDrive(
                                path=vol_path,
                                label=item.name,
                                is_writable=is_writable,
                                total_space=total,
                                free_space=free,
                            )
                        )
        except PermissionError:
            continue

    return drives


def detect_removable_drives() -> list[RemovableDrive]:
    """Detect all available removable drives on the current system.

    This function automatically detects the operating system and uses
    the appropriate method to find removable drives.

    Returns:
        List of detected removable drives.
    """
    system = platform.system().lower()

    if system == "windows":
        return _detect_windows_drives()
    elif system == "darwin":
        return _detect_macos_volumes()
    else:  # Linux and other Unix-like systems
        return _detect_linux_volumes()


def validate_usb_destination(path: str) -> tuple[bool, str]:
    """Validate that a USB destination is usable.

    Args:
        path: Path to validate.

    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    if not path:
        return False, "La ruta de destino no puede estar vacía"

    p = Path(path)

    if not p.exists():
        return False, f"La ruta no existe: {path}"

    if not p.is_dir():
        return False, f"La ruta no es un directorio: {path}"

    if not os.access(path, os.R_OK):
        return False, f"Sin permisos de lectura en: {path}"

    if not os.access(path, os.W_OK):
        return False, f"Sin permisos de escritura en: {path}"

    return True, ""


def pre_create_folders(base_path: str, folder_structure: list[str]) -> tuple[bool, str]:
    """Pre-create folder structure at destination.

    Args:
        base_path: Base path where to create folders.
        folder_structure: List of relative folder paths to create.

    Returns:
        Tuple of (success, error_message). error_message is empty if successful.

    Raises:
        USBPermissionError: If there's a permission error.
        USBWriteError: If there's a write error.
    """
    is_valid, error = validate_usb_destination(base_path)
    if not is_valid:
        return False, error

    base = Path(base_path)

    for folder in folder_structure:
        folder_path = base / folder

        try:
            folder_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            error_msg = f"Error de permisos al crear carpeta '{folder}': {e}"
            raise USBPermissionError(error_msg) from e
        except OSError as e:
            error_msg = f"Error de escritura al crear carpeta '{folder}': {e}"
            raise USBWriteError(error_msg) from e

    return True, ""


def get_usb_music_folder_structure(genres: list[str] | None = None) -> list[str]:
    """Get standard folder structure for USB Music.

    Creates Music/Genre/Artist structure.

    Args:
        genres: Optional list of genres to pre-create. If None, creates base Music folder.

    Returns:
        List of folder paths to create.
    """
    folders = ["Music"]

    if genres:
        for genre in genres:
            # Sanitize genre name for folder
            safe_genre = "".join(c if c.isalnum() or c in " -_" else "_" for c in genre)
            folders.append(f"Music/{safe_genre}")

    return folders


def get_usb_movies_folder_structure() -> list[str]:
    """Get standard folder structure for USB Movies.

    Creates Movies/ structure.

    Returns:
        List of folder paths to create.
    """
    return ["Movies"]


def format_drive_size(size_bytes: int) -> str:
    """Format drive size in human-readable format.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted size string.
    """
    if size_bytes >= 1024**4:
        return f"{size_bytes / (1024**4):.1f} TB"
    elif size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.1f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} B"


def get_drive_display_name(drive: RemovableDrive) -> str:
    """Get display name for a drive in UI.

    Args:
        drive: The removable drive.

    Returns:
        Display name including label and free space.
    """
    free_str = format_drive_size(drive.free_space)
    writable_indicator = "" if drive.is_writable else " [Solo lectura]"
    return f"{drive.label} ({free_str} libre){writable_indicator}"
