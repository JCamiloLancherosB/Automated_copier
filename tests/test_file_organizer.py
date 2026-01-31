"""Tests for the FileOrganizer module."""

import tempfile
from pathlib import Path

import pytest

from mediacopier.core.file_organizer import FileOrganizer, MusicFile, SortMode


class TestMusicFile:
    """Tests for MusicFile dataclass."""

    def test_music_file_creation(self):
        """Test creating a MusicFile."""
        file = MusicFile(
            path="/path/to/song.mp3",
            filename="song.mp3",
            genre="Rock",
            artist="Artist Name",
            year="2020",
        )
        assert file.path == "/path/to/song.mp3"
        assert file.filename == "song.mp3"
        assert file.genre == "Rock"
        assert file.artist == "Artist Name"
        assert file.year == "2020"

    def test_music_file_to_dict(self):
        """Test serializing MusicFile to dict."""
        file = MusicFile(
            path="/path/to/song.mp3", filename="song.mp3", genre="Rock", year="2020"
        )
        data = file.to_dict()
        assert data["path"] == "/path/to/song.mp3"
        assert data["filename"] == "song.mp3"
        assert data["genre"] == "Rock"
        assert data["year"] == "2020"

    def test_music_file_from_dict(self):
        """Test deserializing MusicFile from dict."""
        data = {
            "path": "/path/to/song.mp3",
            "filename": "song.mp3",
            "genre": "Rock",
            "artist": "Artist",
            "year": "2020",
        }
        file = MusicFile.from_dict(data)
        assert file.path == "/path/to/song.mp3"
        assert file.filename == "song.mp3"
        assert file.genre == "Rock"
        assert file.artist == "Artist"
        assert file.year == "2020"


class TestFileOrganizer:
    """Tests for FileOrganizer class."""

    def test_is_audio_file(self):
        """Test audio file detection."""
        organizer = FileOrganizer()
        assert organizer._is_audio_file("song.mp3")
        assert organizer._is_audio_file("song.MP3")
        assert organizer._is_audio_file("song.wav")
        assert organizer._is_audio_file("song.flac")
        assert organizer._is_audio_file("song.m4a")
        assert not organizer._is_audio_file("song.txt")
        assert not organizer._is_audio_file("song.jpg")

    def test_add_file(self):
        """Test adding a single file."""
        organizer = FileOrganizer()
        file = MusicFile(path="/test/song.mp3", filename="song.mp3", genre="Rock")
        organizer.add_file(file)
        assert len(organizer.files) == 1
        assert organizer.files[0].filename == "song.mp3"

    def test_organize_original_mode(self):
        """Test organizing in original order."""
        organizer = FileOrganizer()
        organizer.add_file(MusicFile(path="/test/a.mp3", filename="a.mp3"))
        organizer.add_file(MusicFile(path="/test/b.mp3", filename="b.mp3"))
        organizer.add_file(MusicFile(path="/test/c.mp3", filename="c.mp3"))

        result = organizer.organize(SortMode.ORIGINAL)
        assert len(result) == 3
        assert result[0][0] == 1  # First index
        assert result[0][1].filename == "a.mp3"
        assert result[1][0] == 2
        assert result[1][1].filename == "b.mp3"
        assert result[2][0] == 3
        assert result[2][1].filename == "c.mp3"

    def test_organize_alphabetical(self):
        """Test alphabetical sorting."""
        organizer = FileOrganizer()
        organizer.add_file(MusicFile(path="/test/c.mp3", filename="c.mp3"))
        organizer.add_file(MusicFile(path="/test/a.mp3", filename="a.mp3"))
        organizer.add_file(MusicFile(path="/test/b.mp3", filename="b.mp3"))

        result = organizer.organize(SortMode.ALPHABETICAL)
        assert len(result) == 3
        assert result[0][1].filename == "a.mp3"
        assert result[1][1].filename == "b.mp3"
        assert result[2][1].filename == "c.mp3"

    def test_organize_alphabetical_desc(self):
        """Test reverse alphabetical sorting."""
        organizer = FileOrganizer()
        organizer.add_file(MusicFile(path="/test/c.mp3", filename="c.mp3"))
        organizer.add_file(MusicFile(path="/test/a.mp3", filename="a.mp3"))
        organizer.add_file(MusicFile(path="/test/b.mp3", filename="b.mp3"))

        result = organizer.organize(SortMode.ALPHABETICAL_DESC)
        assert len(result) == 3
        assert result[0][1].filename == "c.mp3"
        assert result[1][1].filename == "b.mp3"
        assert result[2][1].filename == "a.mp3"

    def test_organize_interleave_genre(self):
        """Test genre interleaving."""
        organizer = FileOrganizer()
        # Add songs from different genres
        organizer.add_file(MusicFile(path="/test/a1.mp3", filename="a1.mp3", genre="Rock"))
        organizer.add_file(MusicFile(path="/test/a2.mp3", filename="a2.mp3", genre="Rock"))
        organizer.add_file(MusicFile(path="/test/a3.mp3", filename="a3.mp3", genre="Rock"))
        organizer.add_file(MusicFile(path="/test/b1.mp3", filename="b1.mp3", genre="Pop"))
        organizer.add_file(MusicFile(path="/test/b2.mp3", filename="b2.mp3", genre="Pop"))
        organizer.add_file(MusicFile(path="/test/c1.mp3", filename="c1.mp3", genre="Jazz"))

        result = organizer.organize(SortMode.INTERLEAVE_GENRE)
        assert len(result) == 6

        # Verify interleaving: should alternate between genres
        # First round: one from each genre
        genres_first_round = [result[0][1].genre, result[1][1].genre, result[2][1].genre]
        assert set(genres_first_round) == {"Rock", "Pop", "Jazz"}

        # Second round: Rock and Pop (Jazz exhausted)
        genres_second_round = [result[3][1].genre, result[4][1].genre]
        assert "Rock" in genres_second_round
        assert "Pop" in genres_second_round

        # Third round: only Rock left
        assert result[5][1].genre == "Rock"

    def test_organize_shuffle(self):
        """Test shuffle mode."""
        organizer = FileOrganizer()
        for i in range(10):
            organizer.add_file(MusicFile(path=f"/test/{i}.mp3", filename=f"{i}.mp3"))

        result = organizer.organize(SortMode.SHUFFLE)
        assert len(result) == 10

        # Check that all files are present (order may vary)
        filenames = {item[1].filename for item in result}
        expected_filenames = {f"{i}.mp3" for i in range(10)}
        assert filenames == expected_filenames

    def test_organize_by_artist(self):
        """Test grouping by artist."""
        organizer = FileOrganizer()
        organizer.add_file(
            MusicFile(path="/test/song3.mp3", filename="song3.mp3", artist="Artist B")
        )
        organizer.add_file(
            MusicFile(path="/test/song1.mp3", filename="song1.mp3", artist="Artist A")
        )
        organizer.add_file(
            MusicFile(path="/test/song2.mp3", filename="song2.mp3", artist="Artist A")
        )
        organizer.add_file(
            MusicFile(path="/test/song4.mp3", filename="song4.mp3", artist="Artist B")
        )

        result = organizer.organize(SortMode.BY_ARTIST)
        assert len(result) == 4

        # Verify grouping by artist
        assert result[0][1].artist == "Artist A"
        assert result[1][1].artist == "Artist A"
        assert result[2][1].artist == "Artist B"
        assert result[3][1].artist == "Artist B"

    def test_organize_by_year(self):
        """Test sorting by year."""
        organizer = FileOrganizer()
        organizer.add_file(
            MusicFile(path="/test/song1.mp3", filename="song1.mp3", year="2020")
        )
        organizer.add_file(
            MusicFile(path="/test/song2.mp3", filename="song2.mp3", year="2018")
        )
        organizer.add_file(
            MusicFile(path="/test/song3.mp3", filename="song3.mp3", year="2022")
        )
        organizer.add_file(MusicFile(path="/test/song4.mp3", filename="song4.mp3", year=""))

        result = organizer.organize(SortMode.BY_YEAR)
        assert len(result) == 4

        # Verify sorting by year (empty year goes to end)
        assert result[0][1].year == "2018"
        assert result[1][1].year == "2020"
        assert result[2][1].year == "2022"
        assert result[3][1].year == ""

    def test_format_filename_with_enumeration(self):
        """Test filename formatting with enumeration."""
        organizer = FileOrganizer()
        file = MusicFile(path="/test/song.mp3", filename="song.mp3")

        formatted = organizer.format_filename(1, file, enumerate_files=True, normalize=False)
        assert formatted == "001 - song.mp3"

        formatted = organizer.format_filename(42, file, enumerate_files=True, normalize=False)
        assert formatted == "042 - song.mp3"

        formatted = organizer.format_filename(999, file, enumerate_files=True, normalize=False)
        assert formatted == "999 - song.mp3"

    def test_format_filename_without_enumeration(self):
        """Test filename formatting without enumeration."""
        organizer = FileOrganizer()
        file = MusicFile(path="/test/song.mp3", filename="song.mp3")

        formatted = organizer.format_filename(1, file, enumerate_files=False, normalize=False)
        assert formatted == "song.mp3"

    def test_format_filename_with_normalization(self):
        """Test filename normalization."""
        organizer = FileOrganizer()
        file = MusicFile(
            path="/test/song.mp3", filename='bad:file|name?.mp3'
        )

        formatted = organizer.format_filename(1, file, enumerate_files=False, normalize=True)
        assert formatted == "badfilename.mp3"

        file2 = MusicFile(path="/test/song.mp3", filename="song   with   spaces.mp3")
        formatted2 = organizer.format_filename(1, file2, enumerate_files=False, normalize=True)
        assert formatted2 == "song with spaces.mp3"

    def test_create_playlist(self):
        """Test playlist creation."""
        organizer = FileOrganizer()

        with tempfile.TemporaryDirectory() as tmpdir:
            playlist_path = Path(tmpdir) / "playlist.m3u"

            organized_files = [
                (1, "001 - song1.mp3"),
                (2, "002 - song2.mp3"),
                (3, "003 - song3.mp3"),
            ]

            success = organizer.create_playlist(organized_files, str(playlist_path))
            assert success
            assert playlist_path.exists()

            # Verify content
            content = playlist_path.read_text(encoding="utf-8")
            assert content.startswith("#EXTM3U\n")
            assert "001 - song1.mp3" in content
            assert "002 - song2.mp3" in content
            assert "003 - song3.mp3" in content

    def test_add_files_from_directory(self):
        """Test adding files from a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create some test audio files
            (tmppath / "song1.mp3").touch()
            (tmppath / "song2.wav").touch()
            (tmppath / "not_audio.txt").touch()

            organizer = FileOrganizer()
            organizer.add_files_from_directory(str(tmppath), genre="TestGenre")

            # Should have added 2 audio files, not the txt file
            assert len(organizer.files) == 2
            assert all(f.genre == "TestGenre" for f in organizer.files)

            filenames = {f.filename for f in organizer.files}
            assert "song1.mp3" in filenames
            assert "song2.wav" in filenames
            assert "not_audio.txt" not in filenames

    def test_interleave_genre_example(self):
        """Test the exact example from the requirements."""
        organizer = FileOrganizer()

        # Género A: [A1, A2, A3, A4]
        for i in range(1, 5):
            organizer.add_file(
                MusicFile(path=f"/test/a{i}.mp3", filename=f"A{i}.mp3", genre="A")
            )

        # Género B: [B1, B2, B3]
        for i in range(1, 4):
            organizer.add_file(
                MusicFile(path=f"/test/b{i}.mp3", filename=f"B{i}.mp3", genre="B")
            )

        # Género C: [C1, C2]
        for i in range(1, 3):
            organizer.add_file(
                MusicFile(path=f"/test/c{i}.mp3", filename=f"C{i}.mp3", genre="C")
            )

        result = organizer.organize(SortMode.INTERLEAVE_GENRE)

        # Expected order: A1, B1, C1, A2, B2, C2, A3, B3, A4
        expected_order = ["A1.mp3", "B1.mp3", "C1.mp3", "A2.mp3", "B2.mp3", "C2.mp3", "A3.mp3", "B3.mp3", "A4.mp3"]
        
        actual_order = [item[1].filename for item in result]
        assert actual_order == expected_order

        # Verify indices start from 1
        assert result[0][0] == 1
        assert result[-1][0] == 9
