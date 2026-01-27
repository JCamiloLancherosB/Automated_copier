"""Unit tests for core metadata_video module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mediacopier.core.metadata_video import (
    FFPROBE_AVAILABLE,
    VideoMeta,
    extract_video_metadata,
    meets_minimum_duration,
    parse_ffprobe_json,
)

# Fixture: Sample ffprobe JSON output for a typical video file
FFPROBE_FIXTURE_STANDARD = {
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_type": "video",
            "width": 1920,
            "height": 1080,
            "duration": "120.5",
        },
        {
            "index": 1,
            "codec_name": "aac",
            "codec_type": "audio",
            "duration": "120.5",
        },
    ],
    "format": {
        "filename": "test_video.mp4",
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "120.500000",
        "size": "15000000",
    },
}

# Fixture: ffprobe JSON for a video with multiple streams
FFPROBE_FIXTURE_MULTI_STREAM = {
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_type": "video",
            "width": 1280,
            "height": 720,
        },
        {
            "index": 1,
            "codec_name": "h264",
            "codec_type": "video",
            "width": 640,
            "height": 480,
        },
        {
            "index": 2,
            "codec_name": "aac",
            "codec_type": "audio",
        },
        {
            "index": 3,
            "codec_name": "mp3",
            "codec_type": "audio",
        },
    ],
    "format": {
        "duration": "300.0",
    },
}

# Fixture: ffprobe JSON with duration only in streams
FFPROBE_FIXTURE_DURATION_IN_STREAM = {
    "streams": [
        {
            "index": 0,
            "codec_name": "vp9",
            "codec_type": "video",
            "width": 3840,
            "height": 2160,
            "duration": "600.123",
        },
    ],
    "format": {
        "filename": "4k_video.webm",
    },
}

# Fixture: ffprobe JSON with minimal info
FFPROBE_FIXTURE_MINIMAL = {
    "streams": [],
    "format": {},
}

# Fixture: ffprobe JSON with invalid values
FFPROBE_FIXTURE_INVALID_VALUES = {
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "width": "invalid",
            "height": None,
        },
    ],
    "format": {
        "duration": "not_a_number",
    },
}


class TestVideoMeta:
    """Tests for VideoMeta dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        meta = VideoMeta()
        assert meta.duration_sec is None
        assert meta.width is None
        assert meta.height is None
        assert meta.codec == ""
        assert meta.video_streams == 0
        assert meta.audio_streams == 0

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for VideoMeta."""
        original = VideoMeta(
            duration_sec=120.5,
            width=1920,
            height=1080,
            codec="h264",
            video_streams=1,
            audio_streams=2,
        )
        data = original.to_dict()
        restored = VideoMeta.from_dict(data)

        assert restored.duration_sec == original.duration_sec
        assert restored.width == original.width
        assert restored.height == original.height
        assert restored.codec == original.codec
        assert restored.video_streams == original.video_streams
        assert restored.audio_streams == original.audio_streams

    def test_has_duration(self) -> None:
        """Test has_duration property."""
        meta = VideoMeta(duration_sec=120.5)
        assert meta.has_duration is True

        meta = VideoMeta(duration_sec=0)
        assert meta.has_duration is False

        meta = VideoMeta(duration_sec=None)
        assert meta.has_duration is False

    def test_has_resolution(self) -> None:
        """Test has_resolution property."""
        meta = VideoMeta(width=1920, height=1080)
        assert meta.has_resolution is True

        meta = VideoMeta(width=1920, height=None)
        assert meta.has_resolution is False

        meta = VideoMeta(width=None, height=1080)
        assert meta.has_resolution is False

        meta = VideoMeta()
        assert meta.has_resolution is False

    def test_duration_minutes(self) -> None:
        """Test duration_minutes property."""
        meta = VideoMeta(duration_sec=120.0)
        assert meta.duration_minutes == 2.0

        meta = VideoMeta(duration_sec=90.0)
        assert meta.duration_minutes == 1.5

        meta = VideoMeta(duration_sec=None)
        assert meta.duration_minutes is None


class TestParseFfprobeJson:
    """Tests for parse_ffprobe_json function."""

    def test_standard_video(self) -> None:
        """Test parsing standard video file metadata."""
        meta = parse_ffprobe_json(FFPROBE_FIXTURE_STANDARD)

        assert meta.duration_sec == 120.5
        assert meta.width == 1920
        assert meta.height == 1080
        assert meta.codec == "h264"
        assert meta.video_streams == 1
        assert meta.audio_streams == 1

    def test_multi_stream_video(self) -> None:
        """Test parsing video with multiple streams."""
        meta = parse_ffprobe_json(FFPROBE_FIXTURE_MULTI_STREAM)

        assert meta.duration_sec == 300.0
        # Should get resolution from first video stream
        assert meta.width == 1280
        assert meta.height == 720
        assert meta.codec == "h264"
        assert meta.video_streams == 2
        assert meta.audio_streams == 2

    def test_duration_in_stream(self) -> None:
        """Test parsing when duration is only in stream, not format."""
        meta = parse_ffprobe_json(FFPROBE_FIXTURE_DURATION_IN_STREAM)

        assert meta.duration_sec == 600.123
        assert meta.width == 3840
        assert meta.height == 2160
        assert meta.codec == "vp9"
        assert meta.video_streams == 1
        assert meta.audio_streams == 0

    def test_minimal_info(self) -> None:
        """Test parsing with minimal/empty information."""
        meta = parse_ffprobe_json(FFPROBE_FIXTURE_MINIMAL)

        assert meta.duration_sec is None
        assert meta.width is None
        assert meta.height is None
        assert meta.codec == ""
        assert meta.video_streams == 0
        assert meta.audio_streams == 0

    def test_invalid_values(self) -> None:
        """Test that invalid values are handled gracefully."""
        meta = parse_ffprobe_json(FFPROBE_FIXTURE_INVALID_VALUES)

        # Invalid duration should be None
        assert meta.duration_sec is None
        # Invalid width/height should be None
        assert meta.width is None
        assert meta.height is None
        assert meta.video_streams == 1
        assert meta.audio_streams == 0

    def test_empty_dict(self) -> None:
        """Test parsing an empty dictionary."""
        meta = parse_ffprobe_json({})

        assert meta.duration_sec is None
        assert meta.width is None
        assert meta.height is None
        assert meta.codec == ""
        assert meta.video_streams == 0
        assert meta.audio_streams == 0


class TestMeetsMinimumDuration:
    """Tests for meets_minimum_duration function."""

    def test_meets_duration_when_longer(self) -> None:
        """Test that video meets duration when longer than minimum."""
        meta = VideoMeta(duration_sec=300.0)  # 5 minutes
        assert meets_minimum_duration(meta, 180.0) is True  # 3 minute minimum

    def test_meets_duration_when_equal(self) -> None:
        """Test that video meets duration when equal to minimum."""
        meta = VideoMeta(duration_sec=180.0)
        assert meets_minimum_duration(meta, 180.0) is True

    def test_does_not_meet_duration_when_shorter(self) -> None:
        """Test that video doesn't meet duration when shorter than minimum."""
        meta = VideoMeta(duration_sec=60.0)  # 1 minute
        assert meets_minimum_duration(meta, 180.0) is False  # 3 minute minimum

    def test_meets_duration_when_no_minimum(self) -> None:
        """Test that video meets duration when minimum is 0 or negative."""
        meta = VideoMeta(duration_sec=10.0)
        assert meets_minimum_duration(meta, 0.0) is True
        assert meets_minimum_duration(meta, -1.0) is True

    def test_meets_duration_when_no_metadata(self) -> None:
        """Test that video meets duration when metadata is None."""
        assert meets_minimum_duration(None, 180.0) is True

    def test_meets_duration_when_duration_unknown(self) -> None:
        """Test that video meets duration when duration is unknown."""
        meta = VideoMeta()  # duration_sec is None
        assert meets_minimum_duration(meta, 180.0) is True


class TestExtractVideoMetadata:
    """Tests for extract_video_metadata function."""

    def test_fallback_when_no_ffprobe(self) -> None:
        """Test that empty VideoMeta is returned when ffprobe is unavailable."""
        with patch("mediacopier.core.metadata_video.FFPROBE_AVAILABLE", False):
            meta = extract_video_metadata("/fake/path/video.mp4")
            assert meta is not None
            assert meta.duration_sec is None
            assert meta.width is None
            assert meta.height is None

    def test_returns_empty_on_ffprobe_failure(self, tmp_path: Path) -> None:
        """Test that empty VideoMeta is returned when ffprobe fails."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video content")

        with patch("mediacopier.core.metadata_video.FFPROBE_AVAILABLE", True):
            with patch(
                "mediacopier.core.metadata_video._run_ffprobe",
                return_value=None,
            ):
                meta = extract_video_metadata(test_file)
                assert meta is not None
                assert meta.duration_sec is None
                assert meta.width is None
                assert meta.height is None

    def test_parses_ffprobe_output(self, tmp_path: Path) -> None:
        """Test that ffprobe output is parsed correctly."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video content")

        with patch("mediacopier.core.metadata_video.FFPROBE_AVAILABLE", True):
            with patch(
                "mediacopier.core.metadata_video._run_ffprobe",
                return_value=FFPROBE_FIXTURE_STANDARD,
            ):
                meta = extract_video_metadata(test_file)
                assert meta is not None
                assert meta.duration_sec == 120.5
                assert meta.width == 1920
                assert meta.height == 1080
                assert meta.codec == "h264"


class TestFfprobeAvailabilityFlag:
    """Tests for FFPROBE_AVAILABLE flag."""

    def test_flag_is_boolean(self) -> None:
        """Test that FFPROBE_AVAILABLE flag is a boolean."""
        assert isinstance(FFPROBE_AVAILABLE, bool)


class TestFilterByMinimumDuration:
    """Integration tests for filtering videos by minimum duration."""

    def test_filter_short_videos(self) -> None:
        """Test filtering out videos shorter than minimum duration."""
        videos = [
            VideoMeta(duration_sec=60.0),   # 1 minute - too short
            VideoMeta(duration_sec=180.0),  # 3 minutes - exactly minimum
            VideoMeta(duration_sec=300.0),  # 5 minutes - above minimum
            VideoMeta(),                     # Unknown duration - include
        ]
        min_duration = 180.0  # 3 minutes

        filtered = [
            v for v in videos if meets_minimum_duration(v, min_duration)
        ]

        assert len(filtered) == 3
        assert filtered[0].duration_sec == 180.0
        assert filtered[1].duration_sec == 300.0
        assert filtered[2].duration_sec is None
