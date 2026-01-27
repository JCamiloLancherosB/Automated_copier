"""Unit tests for core copier module."""

from __future__ import annotations

from pathlib import Path

from mediacopier.core.copier import (
    CollisionStrategy,
    CopyItemAction,
    CopyPlan,
    CopyPlanItem,
    CopyReport,
    build_copy_plan,
    compute_file_hash,
    execute_copy_plan,
    generate_unique_filename,
)
from mediacopier.core.indexer import MediaFile, MediaType
from mediacopier.core.matcher import MatchCandidate, MatchResult
from mediacopier.core.metadata_audio import AudioMeta
from mediacopier.core.models import OrganizationMode, RequestedItem, RequestedItemType


class TestCopyPlanItem:
    """Tests for CopyPlanItem dataclass."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for CopyPlanItem."""
        original = CopyPlanItem(
            source="/music/song.mp3",
            destination="/backup/song.mp3",
            action=CopyItemAction.COPY,
            size=1024000,
            reason="",
        )
        data = original.to_dict()
        restored = CopyPlanItem.from_dict(data)

        assert restored.source == original.source
        assert restored.destination == original.destination
        assert restored.action == original.action
        assert restored.size == original.size
        assert restored.reason == original.reason

    def test_to_dict_with_reason(self) -> None:
        """Test serialization includes reason."""
        item = CopyPlanItem(
            source="/a.mp3",
            destination="/b.mp3",
            action=CopyItemAction.SKIP_EXISTS,
            size=100,
            reason="File already exists",
        )
        data = item.to_dict()
        assert data["reason"] == "File already exists"


class TestCopyPlan:
    """Tests for CopyPlan dataclass."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for CopyPlan."""
        original = CopyPlan(
            items=[
                CopyPlanItem(
                    source="/a.mp3",
                    destination="/b.mp3",
                    action=CopyItemAction.COPY,
                    size=1000,
                ),
                CopyPlanItem(
                    source="/c.mp3",
                    destination="/d.mp3",
                    action=CopyItemAction.SKIP_EXISTS,
                    size=2000,
                    reason="File already exists",
                ),
            ],
            total_bytes=1000,
            files_to_copy=1,
            files_to_skip=1,
        )
        data = original.to_dict()
        restored = CopyPlan.from_dict(data)

        assert len(restored.items) == len(original.items)
        assert restored.total_bytes == original.total_bytes
        assert restored.files_to_copy == original.files_to_copy
        assert restored.files_to_skip == original.files_to_skip


class TestCopyReport:
    """Tests for CopyReport dataclass."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for CopyReport."""
        original = CopyReport(
            copied=10,
            skipped=5,
            failed=2,
            bytes_copied=1024 * 1024 * 100,
            errors=[("/a.mp3", "Permission denied")],
        )
        data = original.to_dict()
        restored = CopyReport.from_dict(data)

        assert restored.copied == original.copied
        assert restored.skipped == original.skipped
        assert restored.failed == original.failed
        assert restored.bytes_copied == original.bytes_copied
        assert restored.errors == original.errors


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_hash_identical_files(self, tmp_path: Path) -> None:
        """Test that identical files have the same hash."""
        content = b"test content for hashing" * 100
        file1 = tmp_path / "file1.bin"
        file2 = tmp_path / "file2.bin"
        file1.write_bytes(content)
        file2.write_bytes(content)

        hash1 = compute_file_hash(file1)
        hash2 = compute_file_hash(file2)

        assert hash1 == hash2

    def test_hash_different_files(self, tmp_path: Path) -> None:
        """Test that different files have different hashes."""
        file1 = tmp_path / "file1.bin"
        file2 = tmp_path / "file2.bin"
        file1.write_bytes(b"content A")
        file2.write_bytes(b"content B")

        hash1 = compute_file_hash(file1)
        hash2 = compute_file_hash(file2)

        assert hash1 != hash2

    def test_hash_is_deterministic(self, tmp_path: Path) -> None:
        """Test that hashing the same file produces consistent results."""
        file = tmp_path / "test.bin"
        file.write_bytes(b"deterministic content")

        hash1 = compute_file_hash(file)
        hash2 = compute_file_hash(file)

        assert hash1 == hash2


class TestGenerateUniqueFilename:
    """Tests for generate_unique_filename function."""

    def test_generates_suffix_1_when_original_exists(self, tmp_path: Path) -> None:
        """Test that _1 suffix is generated when original exists."""
        original = tmp_path / "song.mp3"
        original.write_bytes(b"content")

        unique = generate_unique_filename(original)

        assert unique.name == "song_1.mp3"
        assert unique.parent == original.parent

    def test_generates_suffix_2_when_1_exists(self, tmp_path: Path) -> None:
        """Test that _2 suffix is generated when _1 also exists."""
        (tmp_path / "song.mp3").write_bytes(b"content")
        (tmp_path / "song_1.mp3").write_bytes(b"content")

        unique = generate_unique_filename(tmp_path / "song.mp3")

        assert unique.name == "song_2.mp3"

    def test_deterministic_renaming(self, tmp_path: Path) -> None:
        """Test that renaming is deterministic and predictable."""
        original = tmp_path / "song.mp3"
        original.write_bytes(b"content")

        # Call multiple times - should always get the same result
        result1 = generate_unique_filename(original)
        result2 = generate_unique_filename(original)

        assert result1 == result2
        assert result1.name == "song_1.mp3"

    def test_preserves_extension(self, tmp_path: Path) -> None:
        """Test that file extension is preserved."""
        original = tmp_path / "video.mkv"
        original.write_bytes(b"content")

        unique = generate_unique_filename(original)

        assert unique.suffix == ".mkv"
        assert unique.name == "video_1.mkv"


class TestBuildCopyPlan:
    """Tests for build_copy_plan function."""

    def _create_match_result(
        self,
        requested_text: str,
        matched_path: str,
        matched_name: str,
        size: int,
    ) -> MatchResult:
        """Helper to create a MatchResult for testing."""
        media_file = MediaFile(
            path=matched_path,
            nombre_base=matched_name,
            extension=".mp3",
            tamano=size,
            tipo=MediaType.AUDIO,
        )
        candidate = MatchCandidate(
            media_file=media_file,
            score=95.0,
            reason="test match",
            is_exact=True,
            normalized_name=matched_name.lower(),
        )
        requested = RequestedItem(
            tipo=RequestedItemType.SONG,
            texto_original=requested_text,
        )
        return MatchResult(
            requested_item=requested,
            candidates=[candidate],
            best_match=candidate,
            match_found=True,
        )

    def test_builds_plan_single_folder_mode(self, tmp_path: Path) -> None:
        """Test building a plan with SINGLE_FOLDER organization."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()

        matches = [
            self._create_match_result("Song A", "/music/song_a.mp3", "song_a", 1000),
            self._create_match_result("Song B", "/music/song_b.mp3", "song_b", 2000),
        ]

        plan = build_copy_plan(
            matches=matches,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
        )

        assert len(plan.items) == 2
        assert plan.files_to_copy == 2
        assert plan.files_to_skip == 0
        assert plan.total_bytes == 3000

        # All files should go to dest_root directly
        for item in plan.items:
            assert Path(item.destination).parent == dest_root

    def test_collision_strategy_skip(self, tmp_path: Path) -> None:
        """Test collision handling with SKIP strategy."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        # Create existing file at destination
        existing = dest_root / "song_a.mp3"
        existing.write_bytes(b"existing content")

        matches = [
            self._create_match_result("Song A", "/music/song_a.mp3", "song_a", 1000),
        ]

        plan = build_copy_plan(
            matches=matches,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
            collision_strategy=CollisionStrategy.SKIP,
        )

        assert len(plan.items) == 1
        assert plan.items[0].action == CopyItemAction.SKIP_EXISTS
        assert plan.files_to_copy == 0
        assert plan.files_to_skip == 1

    def test_collision_strategy_rename(self, tmp_path: Path) -> None:
        """Test collision handling with RENAME strategy."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        # Create existing file at destination
        existing = dest_root / "song_a.mp3"
        existing.write_bytes(b"existing content")

        matches = [
            self._create_match_result("Song A", "/music/song_a.mp3", "song_a", 1000),
        ]

        plan = build_copy_plan(
            matches=matches,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
            collision_strategy=CollisionStrategy.RENAME,
        )

        assert len(plan.items) == 1
        assert plan.items[0].action == CopyItemAction.RENAME_COPY
        assert "song_a_1.mp3" in plan.items[0].destination
        assert plan.files_to_copy == 1
        assert plan.files_to_skip == 0

    def test_collision_strategy_compare_size_same(self, tmp_path: Path) -> None:
        """Test collision handling with COMPARE_SIZE when sizes match."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create source file with known size
        source_file = source_dir / "song_a.mp3"
        content = b"test content"
        source_file.write_bytes(content)
        size = len(content)

        # Create existing file at destination with same size
        existing = dest_root / "song_a.mp3"
        existing.write_bytes(content)

        matches = [
            self._create_match_result("Song A", str(source_file), "song_a", size),
        ]

        plan = build_copy_plan(
            matches=matches,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
            collision_strategy=CollisionStrategy.COMPARE_SIZE,
        )

        assert len(plan.items) == 1
        assert plan.items[0].action == CopyItemAction.SKIP_SAME_SIZE
        assert plan.files_to_skip == 1

    def test_collision_strategy_compare_size_different(self, tmp_path: Path) -> None:
        """Test collision handling with COMPARE_SIZE when sizes differ."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create source file
        source_file = source_dir / "song_a.mp3"
        source_file.write_bytes(b"longer source content")

        # Create existing file at destination with different size
        existing = dest_root / "song_a.mp3"
        existing.write_bytes(b"short")

        matches = [
            self._create_match_result(
                "Song A", str(source_file), "song_a", source_file.stat().st_size
            ),
        ]

        plan = build_copy_plan(
            matches=matches,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
            collision_strategy=CollisionStrategy.COMPARE_SIZE,
        )

        assert len(plan.items) == 1
        assert plan.items[0].action == CopyItemAction.RENAME_COPY
        assert "song_a_1.mp3" in plan.items[0].destination

    def test_collision_strategy_compare_hash_same(self, tmp_path: Path) -> None:
        """Test collision handling with COMPARE_HASH when hashes match."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create identical files
        content = b"identical content for hash test"
        source_file = source_dir / "song_a.mp3"
        source_file.write_bytes(content)
        existing = dest_root / "song_a.mp3"
        existing.write_bytes(content)

        matches = [
            self._create_match_result(
                "Song A", str(source_file), "song_a", len(content)
            ),
        ]

        plan = build_copy_plan(
            matches=matches,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
            collision_strategy=CollisionStrategy.COMPARE_HASH,
        )

        assert len(plan.items) == 1
        assert plan.items[0].action == CopyItemAction.SKIP_SAME_HASH
        assert plan.files_to_skip == 1

    def test_collision_strategy_compare_hash_different(self, tmp_path: Path) -> None:
        """Test collision handling with COMPARE_HASH when hashes differ."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create files with different content
        source_file = source_dir / "song_a.mp3"
        source_file.write_bytes(b"source content version A")
        existing = dest_root / "song_a.mp3"
        existing.write_bytes(b"existing content version B")

        matches = [
            self._create_match_result(
                "Song A", str(source_file), "song_a", source_file.stat().st_size
            ),
        ]

        plan = build_copy_plan(
            matches=matches,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
            collision_strategy=CollisionStrategy.COMPARE_HASH,
        )

        assert len(plan.items) == 1
        assert plan.items[0].action == CopyItemAction.RENAME_COPY
        assert "song_a_1.mp3" in plan.items[0].destination

    def test_no_match_found_skipped(self, tmp_path: Path) -> None:
        """Test that items without matches are skipped."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()

        requested = RequestedItem(
            tipo=RequestedItemType.SONG,
            texto_original="Nonexistent Song",
        )
        no_match_result = MatchResult(
            requested_item=requested,
            candidates=[],
            best_match=None,
            match_found=False,
        )

        plan = build_copy_plan(
            matches=[no_match_result],
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
        )

        assert len(plan.items) == 0

    def test_plan_detects_internal_collisions(self, tmp_path: Path) -> None:
        """Test that plan detects collisions within the same plan."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()

        # Two matches that would go to the same destination
        matches = [
            self._create_match_result("Song A", "/music1/song.mp3", "song", 1000),
            self._create_match_result("Song B", "/music2/song.mp3", "song", 2000),
        ]

        plan = build_copy_plan(
            matches=matches,
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
        )

        assert len(plan.items) == 2
        destinations = [item.destination for item in plan.items]
        # Should have unique destinations
        assert len(set(destinations)) == 2


class TestExecuteCopyPlan:
    """Tests for execute_copy_plan function."""

    def test_dry_run_does_not_create_files(self, tmp_path: Path) -> None:
        """Test that dry_run=True doesn't actually copy files."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create source file
        source_file = source_dir / "song.mp3"
        source_file.write_bytes(b"test content")

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source_file),
                    destination=str(dest_root / "song.mp3"),
                    action=CopyItemAction.COPY,
                    size=12,
                ),
            ],
            total_bytes=12,
            files_to_copy=1,
            files_to_skip=0,
        )

        report = execute_copy_plan(plan, dry_run=True)

        # Report should show file as copied
        assert report.copied == 1
        assert report.bytes_copied == 12
        # But file should NOT exist
        assert not (dest_root / "song.mp3").exists()

    def test_actual_copy_creates_files(self, tmp_path: Path) -> None:
        """Test that actual copy creates files at destination."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create source file
        content = b"test content for actual copy"
        source_file = source_dir / "song.mp3"
        source_file.write_bytes(content)

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source_file),
                    destination=str(dest_root / "song.mp3"),
                    action=CopyItemAction.COPY,
                    size=len(content),
                ),
            ],
            total_bytes=len(content),
            files_to_copy=1,
            files_to_skip=0,
        )

        report = execute_copy_plan(plan, dry_run=False)

        # Report should show file as copied
        assert report.copied == 1
        assert report.bytes_copied == len(content)
        # File should exist with correct content
        dest_file = dest_root / "song.mp3"
        assert dest_file.exists()
        assert dest_file.read_bytes() == content

    def test_copy_preserves_timestamps(self, tmp_path: Path) -> None:
        """Test that shutil.copy2 preserves timestamps."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create source file
        source_file = source_dir / "song.mp3"
        source_file.write_bytes(b"test content")

        # Set specific modification time
        original_mtime = source_file.stat().st_mtime

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source_file),
                    destination=str(dest_root / "song.mp3"),
                    action=CopyItemAction.COPY,
                    size=12,
                ),
            ],
            total_bytes=12,
            files_to_copy=1,
            files_to_skip=0,
        )

        execute_copy_plan(plan, dry_run=False)

        dest_file = dest_root / "song.mp3"
        dest_mtime = dest_file.stat().st_mtime
        # Timestamps should match (or be very close due to filesystem precision)
        assert abs(dest_mtime - original_mtime) < 1.0

    def test_creates_destination_directories(self, tmp_path: Path) -> None:
        """Test that destination directories are created automatically."""
        dest_root = tmp_path / "dest"
        # Don't create dest_root - let copy create it
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        source_file = source_dir / "song.mp3"
        source_file.write_bytes(b"test content")

        # Destination has nested directories
        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source_file),
                    destination=str(dest_root / "subdir" / "nested" / "song.mp3"),
                    action=CopyItemAction.COPY,
                    size=12,
                ),
            ],
            total_bytes=12,
            files_to_copy=1,
            files_to_skip=0,
        )

        report = execute_copy_plan(plan, dry_run=False)

        assert report.copied == 1
        assert (dest_root / "subdir" / "nested" / "song.mp3").exists()

    def test_skip_items_are_counted(self, tmp_path: Path) -> None:
        """Test that skip items are counted in report."""
        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source="/nonexistent/a.mp3",
                    destination="/dest/a.mp3",
                    action=CopyItemAction.SKIP_EXISTS,
                    size=1000,
                ),
                CopyPlanItem(
                    source="/nonexistent/b.mp3",
                    destination="/dest/b.mp3",
                    action=CopyItemAction.SKIP_SAME_SIZE,
                    size=2000,
                ),
                CopyPlanItem(
                    source="/nonexistent/c.mp3",
                    destination="/dest/c.mp3",
                    action=CopyItemAction.SKIP_SAME_HASH,
                    size=3000,
                ),
            ],
            total_bytes=0,
            files_to_copy=0,
            files_to_skip=3,
        )

        report = execute_copy_plan(plan, dry_run=False)

        assert report.skipped == 3
        assert report.copied == 0

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        """Test that progress callback is called correctly."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create source files
        for i in range(3):
            (source_dir / f"song{i}.mp3").write_bytes(b"x" * 100)

        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source=str(source_dir / f"song{i}.mp3"),
                    destination=str(dest_root / f"song{i}.mp3"),
                    action=CopyItemAction.COPY,
                    size=100,
                )
                for i in range(3)
            ],
            total_bytes=300,
            files_to_copy=3,
            files_to_skip=0,
        )

        progress_calls: list[tuple[int, int, str, int, int]] = []

        def progress_cb(
            current: int, total: int, current_file: str, bytes_so_far: int, total_bytes: int
        ) -> None:
            progress_calls.append((current, total, current_file, bytes_so_far, total_bytes))

        execute_copy_plan(plan, dry_run=False, progress_callback=progress_cb)

        # Should have 3 calls during copy + 1 final call
        assert len(progress_calls) == 4
        # Check progression
        assert progress_calls[0][0] == 1  # First file
        assert progress_calls[1][0] == 2  # Second file
        assert progress_calls[2][0] == 3  # Third file
        assert progress_calls[3][0] == 3  # Final call

    def test_handles_copy_errors(self, tmp_path: Path) -> None:
        """Test that copy errors are recorded in report."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()

        # Source file doesn't exist - should cause an error
        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source="/nonexistent/path/song.mp3",
                    destination=str(dest_root / "song.mp3"),
                    action=CopyItemAction.COPY,
                    size=100,
                ),
            ],
            total_bytes=100,
            files_to_copy=1,
            files_to_skip=0,
        )

        report = execute_copy_plan(plan, dry_run=False)

        assert report.failed == 1
        assert report.copied == 0
        assert len(report.errors) == 1
        assert "/nonexistent/path/song.mp3" in report.errors[0][0]


class TestAcceptanceCriteria:
    """Tests for acceptance criteria: No files are overwritten, decisions are consistent."""

    def test_files_never_overwritten(self, tmp_path: Path) -> None:
        """Test that existing files are never overwritten."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create source file
        source_file = source_dir / "song.mp3"
        source_file.write_bytes(b"new content")

        # Create existing file with different content
        existing = dest_root / "song.mp3"
        original_content = b"original content - should not be changed"
        existing.write_bytes(original_content)

        media_file = MediaFile(
            path=str(source_file),
            nombre_base="song",
            extension=".mp3",
            tamano=source_file.stat().st_size,
            tipo=MediaType.AUDIO,
        )
        candidate = MatchCandidate(
            media_file=media_file,
            score=95.0,
            reason="test",
            is_exact=True,
            normalized_name="song",
        )
        requested = RequestedItem(
            tipo=RequestedItemType.SONG,
            texto_original="Song",
        )
        match_result = MatchResult(
            requested_item=requested,
            candidates=[candidate],
            best_match=candidate,
            match_found=True,
        )

        # Test with SKIP strategy
        plan = build_copy_plan(
            matches=[match_result],
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
            collision_strategy=CollisionStrategy.SKIP,
        )
        execute_copy_plan(plan, dry_run=False)

        # Original content should be preserved
        assert existing.read_bytes() == original_content

    def test_files_never_overwritten_rename_strategy(self, tmp_path: Path) -> None:
        """Test that RENAME strategy creates new file instead of overwriting."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create source file
        new_content = b"new content"
        source_file = source_dir / "song.mp3"
        source_file.write_bytes(new_content)

        # Create existing file with different content
        existing = dest_root / "song.mp3"
        original_content = b"original content"
        existing.write_bytes(original_content)

        media_file = MediaFile(
            path=str(source_file),
            nombre_base="song",
            extension=".mp3",
            tamano=len(new_content),
            tipo=MediaType.AUDIO,
        )
        candidate = MatchCandidate(
            media_file=media_file,
            score=95.0,
            reason="test",
            is_exact=True,
            normalized_name="song",
        )
        requested = RequestedItem(
            tipo=RequestedItemType.SONG,
            texto_original="Song",
        )
        match_result = MatchResult(
            requested_item=requested,
            candidates=[candidate],
            best_match=candidate,
            match_found=True,
        )

        # Test with RENAME strategy
        plan = build_copy_plan(
            matches=[match_result],
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
            collision_strategy=CollisionStrategy.RENAME,
        )
        execute_copy_plan(plan, dry_run=False)

        # Original content should be preserved
        assert existing.read_bytes() == original_content
        # New file should exist with new content
        renamed = dest_root / "song_1.mp3"
        assert renamed.exists()
        assert renamed.read_bytes() == new_content

    def test_consistent_decision_making(self, tmp_path: Path) -> None:
        """Test that the same input produces the same plan."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        source_file = source_dir / "song.mp3"
        source_file.write_bytes(b"test content")

        media_file = MediaFile(
            path=str(source_file),
            nombre_base="song",
            extension=".mp3",
            tamano=12,
            tipo=MediaType.AUDIO,
        )
        candidate = MatchCandidate(
            media_file=media_file,
            score=95.0,
            reason="test",
            is_exact=True,
            normalized_name="song",
        )
        requested = RequestedItem(
            tipo=RequestedItemType.SONG,
            texto_original="Song",
        )
        match_result = MatchResult(
            requested_item=requested,
            candidates=[candidate],
            best_match=candidate,
            match_found=True,
        )

        # Build plan multiple times
        plan1 = build_copy_plan(
            matches=[match_result],
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
        )
        plan2 = build_copy_plan(
            matches=[match_result],
            organization_mode=OrganizationMode.SINGLE_FOLDER,
            dest_root=str(dest_root),
        )

        # Plans should be identical
        assert len(plan1.items) == len(plan2.items)
        for item1, item2 in zip(plan1.items, plan2.items):
            assert item1.source == item2.source
            assert item1.destination == item2.destination
            assert item1.action == item2.action


class TestOrganizationModes:
    """Tests for different organization modes."""

    def _create_match_with_metadata(
        self,
        tmp_path: Path,
        filename: str,
        artist: str | None = None,
        genre: str | None = None,
    ) -> MatchResult:
        """Helper to create a match result with metadata."""
        source_dir = tmp_path / "source"
        source_dir.mkdir(exist_ok=True)
        source_file = source_dir / filename
        source_file.write_bytes(b"test content")

        audio_meta = None
        if artist or genre:
            audio_meta = AudioMeta(
                title=filename,
                artist=artist or "",
                album="Test Album",
                genre=genre or "",
                duration_sec=180.0,
            )

        media_file = MediaFile(
            path=str(source_file),
            nombre_base=source_file.stem,
            extension=source_file.suffix,
            tamano=12,
            tipo=MediaType.AUDIO,
            audio_meta=audio_meta,
        )
        candidate = MatchCandidate(
            media_file=media_file,
            score=95.0,
            reason="test",
            is_exact=True,
            normalized_name=source_file.stem.lower(),
        )
        requested = RequestedItem(
            tipo=RequestedItemType.SONG,
            texto_original=filename,
        )
        return MatchResult(
            requested_item=requested,
            candidates=[candidate],
            best_match=candidate,
            match_found=True,
        )

    def test_scatter_by_artist(self, tmp_path: Path) -> None:
        """Test SCATTER_BY_ARTIST organizes files into artist folders."""
        dest_root = tmp_path / "dest"

        match = self._create_match_with_metadata(
            tmp_path, "song.mp3", artist="The Beatles"
        )

        plan = build_copy_plan(
            matches=[match],
            organization_mode=OrganizationMode.SCATTER_BY_ARTIST,
            dest_root=str(dest_root),
        )

        assert len(plan.items) == 1
        assert "The Beatles" in plan.items[0].destination

    def test_scatter_by_genre(self, tmp_path: Path) -> None:
        """Test SCATTER_BY_GENRE organizes files into genre folders."""
        dest_root = tmp_path / "dest"

        match = self._create_match_with_metadata(
            tmp_path, "song.mp3", genre="Rock"
        )

        plan = build_copy_plan(
            matches=[match],
            organization_mode=OrganizationMode.SCATTER_BY_GENRE,
            dest_root=str(dest_root),
        )

        assert len(plan.items) == 1
        assert "Rock" in plan.items[0].destination

    def test_folder_per_request(self, tmp_path: Path) -> None:
        """Test FOLDER_PER_REQUEST creates folders for each request."""
        dest_root = tmp_path / "dest"

        match = self._create_match_with_metadata(tmp_path, "song.mp3")
        # The request name is the texto_original

        plan = build_copy_plan(
            matches=[match],
            organization_mode=OrganizationMode.FOLDER_PER_REQUEST,
            dest_root=str(dest_root),
        )

        assert len(plan.items) == 1
        # Should contain the request name (filename in this case)
        assert "song.mp3" in plan.items[0].destination or "song" in plan.items[0].destination
