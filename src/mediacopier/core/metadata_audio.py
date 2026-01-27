"""Audio metadata extraction module for MediaCopier."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Try to use mutagen for metadata extraction
try:
    import mutagen
    from mutagen.easyid3 import EasyID3
    from mutagen.flac import FLAC
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4
    from mutagen.wave import WAVE

    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

# Unknown values for fallback
UNKNOWN_GENRE = "Unknown Genre"
UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_TITLE = "Unknown Title"
UNKNOWN_ALBUM = "Unknown Album"

# Pattern to parse "Artist - Title" from filename
ARTIST_TITLE_PATTERN = re.compile(r"^(.+?)\s*[-–—]\s*(.+)$")


@dataclass
class AudioMeta:
    """Audio metadata for a media file."""

    artist: str = ""
    title: str = ""
    album: str = ""
    genre: str = ""
    year: str = ""
    duration_sec: float | None = None
    bitrate_kbps: int | None = None
    codec: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "artist": self.artist,
            "title": self.title,
            "album": self.album,
            "genre": self.genre,
            "year": self.year,
            "duration_sec": self.duration_sec,
            "bitrate_kbps": self.bitrate_kbps,
            "codec": self.codec,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AudioMeta:
        """Deserialize from dictionary."""
        return cls(
            artist=data.get("artist", ""),
            title=data.get("title", ""),
            album=data.get("album", ""),
            genre=data.get("genre", ""),
            year=data.get("year", ""),
            duration_sec=data.get("duration_sec"),
            bitrate_kbps=data.get("bitrate_kbps"),
            codec=data.get("codec", ""),
        )

    @property
    def has_genre(self) -> bool:
        """Check if genre metadata is available."""
        return bool(self.genre and self.genre != UNKNOWN_GENRE)

    @property
    def has_artist(self) -> bool:
        """Check if artist metadata is available."""
        return bool(self.artist and self.artist != UNKNOWN_ARTIST)

    def get_genre_or_unknown(self) -> str:
        """Get the genre or UNKNOWN_GENRE if not available."""
        return self.genre if self.has_genre else UNKNOWN_GENRE

    def get_artist_or_unknown(self) -> str:
        """Get the artist or UNKNOWN_ARTIST if not available."""
        return self.artist if self.has_artist else UNKNOWN_ARTIST


def parse_artist_title_from_filename(filename: str) -> tuple[str, str]:
    """Parse artist and title from a filename in "Artist - Title" format.

    This is a fallback when no embedded tags are available.

    Args:
        filename: The base filename (without extension).

    Returns:
        Tuple of (artist, title). If parsing fails, returns (UNKNOWN_ARTIST, filename).
    """
    # Remove common file extensions if present in the stem
    clean_name = filename.strip()

    match = ARTIST_TITLE_PATTERN.match(clean_name)
    if match:
        artist = match.group(1).strip()
        title = match.group(2).strip()
        return (artist if artist else UNKNOWN_ARTIST, title if title else UNKNOWN_TITLE)

    # If no pattern match, return unknown artist and filename as title
    return (UNKNOWN_ARTIST, clean_name if clean_name else UNKNOWN_TITLE)


def _get_first_tag(tags: dict, keys: list[str]) -> str:
    """Get the first available tag value from a list of possible keys.

    Args:
        tags: Dictionary of tags.
        keys: List of keys to try.

    Returns:
        The first found value, or empty string.
    """
    for key in keys:
        value = tags.get(key)
        if value:
            if isinstance(value, list):
                return str(value[0]) if value else ""
            return str(value)
    return ""


def _extract_mp3_metadata(file_path: Path) -> AudioMeta:
    """Extract metadata from an MP3 file.

    Args:
        file_path: Path to the MP3 file.

    Returns:
        AudioMeta with extracted metadata.
    """
    meta = AudioMeta(codec="mp3")
    try:
        audio = MP3(file_path, ID3=EasyID3)

        # Duration and bitrate from audio info
        if audio.info:
            meta.duration_sec = audio.info.length
            meta.bitrate_kbps = int(audio.info.bitrate / 1000) if audio.info.bitrate else None

        # Tags from EasyID3
        if audio.tags:
            tags = dict(audio.tags)
            meta.artist = _get_first_tag(tags, ["artist", "albumartist"])
            meta.title = _get_first_tag(tags, ["title"])
            meta.album = _get_first_tag(tags, ["album"])
            meta.genre = _get_first_tag(tags, ["genre"])
            meta.year = _get_first_tag(tags, ["date", "year"])

    except Exception:
        # Best effort - return what we have
        pass

    return meta


def _extract_m4a_metadata(file_path: Path) -> AudioMeta:
    """Extract metadata from an M4A/AAC file.

    Args:
        file_path: Path to the M4A file.

    Returns:
        AudioMeta with extracted metadata.
    """
    meta = AudioMeta(codec="aac")
    try:
        audio = MP4(file_path)

        # Duration and bitrate from audio info
        if audio.info:
            meta.duration_sec = audio.info.length
            meta.bitrate_kbps = int(audio.info.bitrate / 1000) if audio.info.bitrate else None
            # Update codec if available
            if hasattr(audio.info, "codec"):
                meta.codec = audio.info.codec or "aac"

        # Tags from MP4
        if audio.tags:
            tags = dict(audio.tags)
            meta.artist = _get_first_tag(tags, ["\xa9ART", "aART"])
            meta.title = _get_first_tag(tags, ["\xa9nam"])
            meta.album = _get_first_tag(tags, ["\xa9alb"])
            meta.genre = _get_first_tag(tags, ["\xa9gen"])
            meta.year = _get_first_tag(tags, ["\xa9day"])

    except Exception:
        # Best effort - return what we have
        pass

    return meta


def _extract_flac_metadata(file_path: Path) -> AudioMeta:
    """Extract metadata from a FLAC file.

    Args:
        file_path: Path to the FLAC file.

    Returns:
        AudioMeta with extracted metadata.
    """
    meta = AudioMeta(codec="flac")
    try:
        audio = FLAC(file_path)

        # Duration from audio info
        if audio.info:
            meta.duration_sec = audio.info.length
            # FLAC uses bits per sample rather than bitrate
            if (
                hasattr(audio.info, "bits_per_sample")
                and hasattr(audio.info, "sample_rate")
                and hasattr(audio.info, "channels")
            ):
                # Approximate bitrate for FLAC
                meta.bitrate_kbps = int(
                    (audio.info.bits_per_sample * audio.info.sample_rate * audio.info.channels)
                    / 1000
                )

        # Tags from Vorbis comments
        if audio.tags:
            tags = {k.lower(): v for k, v in audio.tags}
            meta.artist = _get_first_tag(tags, ["artist", "albumartist"])
            meta.title = _get_first_tag(tags, ["title"])
            meta.album = _get_first_tag(tags, ["album"])
            meta.genre = _get_first_tag(tags, ["genre"])
            meta.year = _get_first_tag(tags, ["date", "year"])

    except Exception:
        # Best effort - return what we have
        pass

    return meta


def _extract_wav_metadata(file_path: Path) -> AudioMeta:
    """Extract metadata from a WAV file.

    Args:
        file_path: Path to the WAV file.

    Returns:
        AudioMeta with extracted metadata.
    """
    meta = AudioMeta(codec="wav")
    try:
        audio = WAVE(file_path)

        # Duration from audio info
        if audio.info:
            meta.duration_sec = audio.info.length
            if hasattr(audio.info, "bits_per_sample") and hasattr(audio.info, "sample_rate"):
                # Calculate bitrate for WAV
                channels = getattr(audio.info, "channels", 2)
                meta.bitrate_kbps = int(
                    (audio.info.bits_per_sample * audio.info.sample_rate * channels) / 1000
                )

        # WAV files can have ID3 tags
        if audio.tags:
            tags = dict(audio.tags)
            meta.artist = _get_first_tag(tags, ["artist", "albumartist"])
            meta.title = _get_first_tag(tags, ["title"])
            meta.album = _get_first_tag(tags, ["album"])
            meta.genre = _get_first_tag(tags, ["genre"])
            meta.year = _get_first_tag(tags, ["date", "year"])

    except Exception:
        # Best effort - return what we have
        pass

    return meta


def extract_audio_metadata(file_path: str | Path) -> AudioMeta | None:
    """Extract audio metadata from a file.

    Uses mutagen to read embedded tags from MP3, M4A, FLAC, and WAV files.
    Falls back to parsing the filename if no tags are available.

    Args:
        file_path: Path to the audio file.

    Returns:
        AudioMeta with extracted metadata, or None if mutagen is not available
        and the file cannot be processed.
    """
    path = Path(file_path)
    extension = path.suffix.lower()

    if not MUTAGEN_AVAILABLE:
        # Fallback to filename parsing only
        artist, title = parse_artist_title_from_filename(path.stem)
        return AudioMeta(artist=artist, title=title)

    # Extract based on file extension
    meta: AudioMeta | None = None

    if extension == ".mp3":
        meta = _extract_mp3_metadata(path)
    elif extension in {".m4a", ".aac", ".mp4"}:
        meta = _extract_m4a_metadata(path)
    elif extension == ".flac":
        meta = _extract_flac_metadata(path)
    elif extension == ".wav":
        meta = _extract_wav_metadata(path)
    else:
        # Unsupported format - try generic mutagen
        try:
            audio = mutagen.File(path, easy=True)
            if audio:
                meta = AudioMeta()
                if audio.info:
                    meta.duration_sec = getattr(audio.info, "length", None)
                    bitrate = getattr(audio.info, "bitrate", None)
                    meta.bitrate_kbps = int(bitrate / 1000) if bitrate else None
                if audio.tags:
                    tags = dict(audio.tags)
                    meta.artist = _get_first_tag(tags, ["artist", "albumartist"])
                    meta.title = _get_first_tag(tags, ["title"])
                    meta.album = _get_first_tag(tags, ["album"])
                    meta.genre = _get_first_tag(tags, ["genre"])
                    meta.year = _get_first_tag(tags, ["date", "year"])
        except Exception:
            pass

    # If no metadata extracted, create empty AudioMeta
    if meta is None:
        meta = AudioMeta()

    # Fallback to filename parsing for missing artist/title
    if not meta.artist or not meta.title:
        artist, title = parse_artist_title_from_filename(path.stem)
        if not meta.artist:
            meta.artist = artist
        if not meta.title:
            meta.title = title

    return meta


def get_organization_path_by_genre(
    audio_meta: AudioMeta | None,
    filename: str,
) -> str:
    """Generate an organization path based on genre and artist.

    This creates a path like: Genre/Artist/filename

    Args:
        audio_meta: Audio metadata, may be None.
        filename: The original filename.

    Returns:
        A relative path for organizing the file.
    """
    if audio_meta and audio_meta.has_genre:
        genre = audio_meta.genre
    else:
        genre = UNKNOWN_GENRE

    if audio_meta and audio_meta.has_artist:
        artist = audio_meta.artist
    else:
        artist = UNKNOWN_ARTIST

    # Sanitize for path usage
    safe_genre = _sanitize_path_component(genre)
    safe_artist = _sanitize_path_component(artist)

    return f"{safe_genre}/{safe_artist}/{filename}"


def _sanitize_path_component(name: str) -> str:
    """Sanitize a string for use as a path component.

    Args:
        name: The string to sanitize.

    Returns:
        A safe string for use in file paths.
    """
    # Replace invalid characters with underscore
    invalid_chars = r'<>:"/\\|?*'
    result = name
    for char in invalid_chars:
        result = result.replace(char, "_")
    # Remove leading/trailing dots and spaces
    result = result.strip(". ")
    # Ensure non-empty
    return result if result else "Unknown"
