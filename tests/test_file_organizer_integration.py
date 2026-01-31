"""Integration tests for FileOrganizer with copy workflow."""

import tempfile
from pathlib import Path

import pytest

from mediacopier.core.file_organizer import FileOrganizer, MusicFile, SortMode


class TestFileOrganizerIntegration:
    """Integration tests for the file organizer workflow."""

    def test_complete_workflow_with_enumeration(self):
        """Test a complete workflow: add files, organize, format, create playlist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create source directories with music files
            rock_dir = tmppath / "Rock"
            rock_dir.mkdir()
            (rock_dir / "song1.mp3").write_text("rock1")
            (rock_dir / "song2.mp3").write_text("rock2")

            pop_dir = tmppath / "Pop"
            pop_dir.mkdir()
            (pop_dir / "track1.mp3").write_text("pop1")
            (pop_dir / "track2.mp3").write_text("pop2")

            # Initialize organizer and add files
            organizer = FileOrganizer()
            organizer.add_files_from_directory(str(rock_dir), "Rock")
            organizer.add_files_from_directory(str(pop_dir), "Pop")

            assert len(organizer.files) == 4

            # Organize with interleave mode
            organized = organizer.organize(SortMode.INTERLEAVE_GENRE)
            assert len(organized) == 4

            # Verify interleaving
            genres = [item[1].genre for item in organized]
            # First two should be different genres
            assert genres[0] != genres[1]

            # Format filenames with enumeration
            formatted_files = []
            for index, music_file in organized:
                formatted_name = organizer.format_filename(
                    index, music_file, enumerate_files=True, normalize=True
                )
                formatted_files.append((index, formatted_name))

            # Verify enumeration
            assert formatted_files[0][1].startswith("001 - ")
            assert formatted_files[1][1].startswith("002 - ")
            assert formatted_files[2][1].startswith("003 - ")
            assert formatted_files[3][1].startswith("004 - ")

            # Create playlist
            playlist_path = tmppath / "test_playlist.m3u"
            success = organizer.create_playlist(formatted_files, str(playlist_path))
            assert success
            assert playlist_path.exists()

            # Verify playlist content
            content = playlist_path.read_text()
            assert content.startswith("#EXTM3U\n")
            for _, filename in formatted_files:
                assert filename in content

    def test_workflow_without_enumeration(self):
        """Test workflow without file enumeration."""
        organizer = FileOrganizer()
        organizer.add_file(MusicFile(path="/test/song.mp3", filename="song.mp3"))
        organizer.add_file(MusicFile(path="/test/track.mp3", filename="track.mp3"))

        organized = organizer.organize(SortMode.ALPHABETICAL)

        formatted = []
        for index, music_file in organized:
            name = organizer.format_filename(
                index, music_file, enumerate_files=False, normalize=False
            )
            formatted.append(name)

        # Without enumeration, should be original names
        assert "song.mp3" in formatted
        assert "track.mp3" in formatted
        # Should not have numeric prefix
        assert not any(name.startswith("001") for name in formatted)

    def test_normalization_removes_special_characters(self):
        """Test that normalization removes special filesystem characters."""
        organizer = FileOrganizer()
        organizer.add_file(
            MusicFile(path="/test/song.mp3", filename='bad:file|name?.mp3')
        )

        organized = organizer.organize(SortMode.ORIGINAL)
        index, music_file = organized[0]

        # With normalization
        normalized = organizer.format_filename(
            index, music_file, enumerate_files=False, normalize=True
        )
        assert ":" not in normalized
        assert "|" not in normalized
        assert "?" not in normalized
        assert normalized == "badfilename.mp3"

        # Without normalization
        not_normalized = organizer.format_filename(
            index, music_file, enumerate_files=False, normalize=False
        )
        # Original bad characters should remain
        assert ":" in not_normalized or "|" in not_normalized or "?" in not_normalized

    def test_genre_interleaving_with_real_scenario(self):
        """Test genre interleaving with a realistic scenario."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create multiple genres with different numbers of songs
            genres_data = {
                "Rock": 4,
                "Pop": 3,
                "Jazz": 2,
                "Electronic": 1,
            }

            organizer = FileOrganizer()

            for genre, count in genres_data.items():
                genre_dir = tmppath / genre
                genre_dir.mkdir()
                for i in range(1, count + 1):
                    song_file = genre_dir / f"{genre}_{i}.mp3"
                    song_file.write_text(f"{genre} song {i}")

                organizer.add_files_from_directory(str(genre_dir), genre)

            # Total: 4 + 3 + 2 + 1 = 10 songs
            assert len(organizer.files) == 10

            # Organize with genre interleaving
            organized = organizer.organize(SortMode.INTERLEAVE_GENRE)
            assert len(organized) == 10

            # First 4 items should include all 4 genres (one from each)
            first_four_genres = {organized[i][1].genre for i in range(4)}
            assert first_four_genres == {"Rock", "Pop", "Jazz", "Electronic"}

            # Verify all songs are present
            all_filenames = {item[1].filename for item in organized}
            expected_filenames = set()
            for genre, count in genres_data.items():
                for i in range(1, count + 1):
                    expected_filenames.add(f"{genre}_{i}.mp3")
            assert all_filenames == expected_filenames

    def test_mixed_files_and_directories(self):
        """Test adding both individual files and directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create a directory with files
            dir1 = tmppath / "dir1"
            dir1.mkdir()
            (dir1 / "song1.mp3").write_text("data")
            (dir1 / "song2.wav").write_text("data")

            # Create standalone files
            file1 = tmppath / "standalone.mp3"
            file1.write_text("data")

            organizer = FileOrganizer()

            # Add directory
            organizer.add_files_from_directory(str(dir1), "TestGenre")

            # Add standalone file
            organizer.add_file(MusicFile(path=str(file1), filename=file1.name))

            assert len(organizer.files) == 3

            # Two from directory should have genre
            dir_files = [f for f in organizer.files if f.genre == "TestGenre"]
            assert len(dir_files) == 2

            # Standalone should have empty or different genre
            standalone_files = [f for f in organizer.files if f.filename == "standalone.mp3"]
            assert len(standalone_files) == 1
