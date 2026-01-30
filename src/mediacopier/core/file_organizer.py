"""Advanced file organization and mixing for multimedia files.

This module provides advanced organization capabilities including:
- Genre interleaving for variety in playlists
- Multiple sorting modes (alphabetical, by artist, by year, etc.)
- File enumeration and name normalization
- Playlist generation (M3U format)
"""

from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class SortMode(Enum):
    """Available sorting modes for organizing files."""

    ORIGINAL = "original"
    INTERLEAVE_GENRE = "interleave_genre"
    SHUFFLE = "shuffle"
    ALPHABETICAL = "alphabetical"
    ALPHABETICAL_DESC = "alphabetical_desc"
    BY_ARTIST = "by_artist"
    BY_GENRE_FOLDERS = "by_genre_folders"
    BY_YEAR = "by_year"


@dataclass
class MusicFile:
    """Represents a music file with metadata."""

    path: str
    filename: str
    genre: str = ""
    artist: str = ""
    year: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "path": self.path,
            "filename": self.filename,
            "genre": self.genre,
            "artist": self.artist,
            "year": self.year,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MusicFile:
        """Deserialize from dictionary."""
        return cls(
            path=data["path"],
            filename=data["filename"],
            genre=data.get("genre", ""),
            artist=data.get("artist", ""),
            year=data.get("year", ""),
        )


class FileOrganizer:
    """Organizer for multimedia files with advanced sorting and mixing capabilities."""

    # Audio file extensions to recognize
    AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma"}

    def __init__(self) -> None:
        """Initialize the file organizer."""
        self.files: list[MusicFile] = []

    def add_files_from_directory(self, directory: str, genre: str = "") -> None:
        """Add audio files from a directory with optional genre tag.

        Args:
            directory: Path to directory containing audio files
            genre: Optional genre tag (defaults to directory name if not provided)
        """
        if not os.path.isdir(directory):
            return

        for filename in os.listdir(directory):
            if self._is_audio_file(filename):
                self.files.append(
                    MusicFile(
                        path=os.path.join(directory, filename),
                        filename=filename,
                        genre=genre or os.path.basename(directory),
                    )
                )

    def add_file(self, file: MusicFile) -> None:
        """Add a single music file to the organizer.

        Args:
            file: MusicFile instance to add
        """
        self.files.append(file)

    def _is_audio_file(self, filename: str) -> bool:
        """Check if a file is an audio file based on extension.

        Args:
            filename: Name of the file to check

        Returns:
            True if file is an audio file
        """
        return Path(filename).suffix.lower() in self.AUDIO_EXTENSIONS

    def organize(self, mode: SortMode) -> list[tuple[int, MusicFile]]:
        """Organize files according to the specified mode.

        Args:
            mode: Sorting mode to apply

        Returns:
            List of tuples (index, MusicFile) with index starting from 1
        """
        if mode == SortMode.INTERLEAVE_GENRE:
            return self._interleave_by_genre()
        elif mode == SortMode.SHUFFLE:
            return self._shuffle()
        elif mode == SortMode.ALPHABETICAL:
            return self._sort_alphabetical()
        elif mode == SortMode.ALPHABETICAL_DESC:
            return self._sort_alphabetical(reverse=True)
        elif mode == SortMode.BY_ARTIST:
            return self._group_by_artist()
        elif mode == SortMode.BY_YEAR:
            return self._sort_by_year()
        else:  # ORIGINAL or BY_GENRE_FOLDERS
            return [(i + 1, f) for i, f in enumerate(self.files)]

    def _interleave_by_genre(self) -> list[tuple[int, MusicFile]]:
        """Interleave songs by genre for maximum variety.

        This creates a playlist where genres alternate, providing
        a diverse listening experience.

        Returns:
            List of tuples (index, MusicFile) with songs interleaved by genre
        """
        # Group files by genre
        by_genre: dict[str, list[MusicFile]] = {}
        for f in self.files:
            genre = f.genre or "Unknown"
            if genre not in by_genre:
                by_genre[genre] = []
            by_genre[genre].append(f)

        # Interleave: take one from each genre in round-robin fashion
        result: list[MusicFile] = []
        genres = list(by_genre.keys())
        indices = {g: 0 for g in genres}

        while any(indices[g] < len(by_genre[g]) for g in genres):
            for genre in genres:
                if indices[genre] < len(by_genre[genre]):
                    result.append(by_genre[genre][indices[genre]])
                    indices[genre] += 1

        return [(i + 1, f) for i, f in enumerate(result)]

    def _shuffle(self) -> list[tuple[int, MusicFile]]:
        """Randomly shuffle all files.

        Returns:
            List of tuples (index, MusicFile) in random order
        """
        shuffled = self.files.copy()
        random.shuffle(shuffled)
        return [(i + 1, f) for i, f in enumerate(shuffled)]

    def _sort_alphabetical(self, reverse: bool = False) -> list[tuple[int, MusicFile]]:
        """Sort files alphabetically by filename.

        Args:
            reverse: If True, sort in descending order (Z-A)

        Returns:
            List of tuples (index, MusicFile) sorted alphabetically
        """
        sorted_files = sorted(self.files, key=lambda f: f.filename.lower(), reverse=reverse)
        return [(i + 1, f) for i, f in enumerate(sorted_files)]

    def _group_by_artist(self) -> list[tuple[int, MusicFile]]:
        """Group files by artist, then sort by filename within each artist.

        Returns:
            List of tuples (index, MusicFile) grouped by artist
        """
        sorted_files = sorted(
            self.files, key=lambda f: (f.artist.lower(), f.filename.lower())
        )
        return [(i + 1, f) for i, f in enumerate(sorted_files)]

    def _sort_by_year(self) -> list[tuple[int, MusicFile]]:
        """Sort files by year, then by filename.

        Files without year information are sorted to the end.

        Returns:
            List of tuples (index, MusicFile) sorted by year
        """
        sorted_files = sorted(
            self.files, key=lambda f: (f.year or "9999", f.filename.lower())
        )
        return [(i + 1, f) for i, f in enumerate(sorted_files)]

    def format_filename(
        self,
        index: int,
        file: MusicFile,
        enumerate_files: bool = True,
        normalize: bool = True,
    ) -> str:
        """Format a filename for copying with optional enumeration and normalization.

        Args:
            index: Sequence number for the file
            file: MusicFile to format
            enumerate_files: If True, prefix with zero-padded index (e.g., "001 - ")
            normalize: If True, remove special characters and normalize spaces

        Returns:
            Formatted filename string
        """
        name = Path(file.filename).stem
        ext = Path(file.filename).suffix

        if normalize:
            # Remove invalid filesystem characters
            name = re.sub(r'[<>:"/\\|?*]', "", name)
            # Normalize whitespace
            name = re.sub(r"\s+", " ", name).strip()

        if enumerate_files:
            return f"{index:03d} - {name}{ext}"
        else:
            return f"{name}{ext}"

    def create_playlist(
        self, organized_files: list[tuple[int, str]], output_path: str
    ) -> bool:
        """Create an M3U playlist file.

        Args:
            organized_files: List of tuples (index, filename)
            output_path: Path where the playlist file should be created

        Returns:
            True if playlist was created successfully, False otherwise
        """
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for _, filename in organized_files:
                    f.write(f"{filename}\n")
            return True
        except (OSError, IOError):
            # Log the error silently and return False
            # The caller should handle this appropriately
            return False
