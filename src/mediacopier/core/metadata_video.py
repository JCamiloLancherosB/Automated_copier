"""Video metadata extraction module for MediaCopier."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _check_ffprobe_available() -> bool:
    """Check if ffprobe is available on the system.

    Returns:
        True if ffprobe is available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


# Check for ffprobe availability at import time
FFPROBE_AVAILABLE = _check_ffprobe_available()


@dataclass
class VideoMeta:
    """Video metadata for a media file."""

    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str = ""
    video_streams: int = 0
    audio_streams: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "duration_sec": self.duration_sec,
            "width": self.width,
            "height": self.height,
            "codec": self.codec,
            "video_streams": self.video_streams,
            "audio_streams": self.audio_streams,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VideoMeta:
        """Deserialize from dictionary."""
        return cls(
            duration_sec=data.get("duration_sec"),
            width=data.get("width"),
            height=data.get("height"),
            codec=data.get("codec", ""),
            video_streams=data.get("video_streams", 0),
            audio_streams=data.get("audio_streams", 0),
        )

    @property
    def has_duration(self) -> bool:
        """Check if duration metadata is available."""
        return self.duration_sec is not None and self.duration_sec > 0

    @property
    def has_resolution(self) -> bool:
        """Check if resolution metadata is available."""
        return self.width is not None and self.height is not None

    @property
    def duration_minutes(self) -> float | None:
        """Get duration in minutes."""
        if self.duration_sec is not None:
            return self.duration_sec / 60.0
        return None


def parse_ffprobe_json(ffprobe_output: dict[str, Any]) -> VideoMeta:
    """Parse ffprobe JSON output and extract video metadata.

    Args:
        ffprobe_output: Parsed JSON output from ffprobe -print_format json.

    Returns:
        VideoMeta with extracted metadata.
    """
    meta = VideoMeta()

    # Parse format information for duration
    format_info = ffprobe_output.get("format", {})
    if "duration" in format_info:
        try:
            meta.duration_sec = float(format_info["duration"])
        except (ValueError, TypeError):
            pass

    # Parse streams information
    streams = ffprobe_output.get("streams", [])
    video_stream_count = 0
    audio_stream_count = 0

    for stream in streams:
        codec_type = stream.get("codec_type", "")

        if codec_type == "video":
            video_stream_count += 1
            # Get resolution from the first video stream
            if not meta.has_resolution:
                try:
                    width = stream.get("width")
                    height = stream.get("height")
                    if width is not None and height is not None:
                        meta.width = int(width)
                        meta.height = int(height)
                except (ValueError, TypeError):
                    pass

            # Get codec from the first video stream
            if not meta.codec:
                meta.codec = stream.get("codec_name", "")

            # Try to get duration from video stream if not in format
            if not meta.has_duration and "duration" in stream:
                try:
                    meta.duration_sec = float(stream["duration"])
                except (ValueError, TypeError):
                    pass

        elif codec_type == "audio":
            audio_stream_count += 1

    meta.video_streams = video_stream_count
    meta.audio_streams = audio_stream_count

    return meta


def _run_ffprobe(file_path: Path) -> dict[str, Any] | None:
    """Run ffprobe and return the JSON output.

    Args:
        file_path: Path to the video file.

    Returns:
        Parsed JSON output from ffprobe, or None if the command fails.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return None

        return json.loads(result.stdout)

    except (subprocess.SubprocessError, FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def extract_video_metadata(file_path: str | Path) -> VideoMeta:
    """Extract video metadata from a file.

    Uses ffprobe to read video metadata if available.
    Falls back to returning minimal VideoMeta with no duration/resolution
    if ffprobe is not available.

    Args:
        file_path: Path to the video file.

    Returns:
        VideoMeta with extracted metadata, or empty VideoMeta with minimal data
        if ffprobe is not available or fails.
    """
    path = Path(file_path)

    if not FFPROBE_AVAILABLE:
        # Fallback: return empty VideoMeta (size and extension handled by MediaFile)
        return VideoMeta()

    # Run ffprobe and parse the output
    ffprobe_output = _run_ffprobe(path)
    if ffprobe_output is None:
        # ffprobe failed for this file, return empty metadata
        return VideoMeta()

    return parse_ffprobe_json(ffprobe_output)


def meets_minimum_duration(video_meta: VideoMeta | None, min_duration_sec: float) -> bool:
    """Check if video meets minimum duration requirement.

    Args:
        video_meta: Video metadata, may be None.
        min_duration_sec: Minimum duration in seconds.

    Returns:
        True if video meets minimum duration, or if duration cannot be determined.
        False if video is shorter than minimum duration.
    """
    if min_duration_sec <= 0:
        return True

    if video_meta is None:
        # If we have no metadata, assume it meets the requirement
        return True

    if video_meta.duration_sec is None:
        # If duration is unknown, assume it meets the requirement
        return True

    return video_meta.duration_sec >= min_duration_sec
