"""Unit tests for the job_report module."""

from __future__ import annotations

import json
from pathlib import Path

from mediacopier.core.copier import CopyItemAction, CopyPlan, CopyPlanItem, CopyReport
from mediacopier.core.indexer import MediaFile, MediaType
from mediacopier.core.job_report import (
    CategorySummary,
    FileOperation,
    FileOperationStatus,
    JobReport,
    MatchInfo,
    create_job_report_from_plan_and_result,
)
from mediacopier.core.matcher import MatchCandidate, MatchResult
from mediacopier.core.models import RequestedItem, RequestedItemType


class TestFileOperationStatus:
    """Tests for FileOperationStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Test that all required statuses exist."""
        assert FileOperationStatus.COPIED.value == "COPIED"
        assert FileOperationStatus.SKIPPED.value == "SKIPPED"
        assert FileOperationStatus.FILTERED.value == "FILTERED"
        assert FileOperationStatus.FAILED.value == "FAILED"


class TestFileOperation:
    """Tests for FileOperation dataclass."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for FileOperation."""
        original = FileOperation(
            source_path="/src/song.mp3",
            source_name="song.mp3",
            dest_path="/dst/song.mp3",
            dest_name="song.mp3",
            status=FileOperationStatus.COPIED,
            reason="",
            size_bytes=1024,
        )
        data = original.to_dict()
        restored = FileOperation.from_dict(data)

        assert restored.source_path == original.source_path
        assert restored.source_name == original.source_name
        assert restored.dest_path == original.dest_path
        assert restored.dest_name == original.dest_name
        assert restored.status == original.status
        assert restored.reason == original.reason
        assert restored.size_bytes == original.size_bytes

    def test_to_dict_with_reason(self) -> None:
        """Test serialization includes reason."""
        op = FileOperation(
            source_path="/src/song.mp3",
            source_name="song.mp3",
            dest_path=None,
            dest_name=None,
            status=FileOperationStatus.FAILED,
            reason="Permission denied",
            size_bytes=0,
        )
        data = op.to_dict()
        assert data["reason"] == "Permission denied"
        assert data["status"] == "FAILED"


class TestMatchInfo:
    """Tests for MatchInfo dataclass."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for MatchInfo."""
        original = MatchInfo(
            requested_text="Bohemian Rhapsody",
            requested_type="song",
            matched_file="/music/queen_bohemian.mp3",
            matched_name="queen_bohemian",
            match_score=95.5,
            match_found=True,
        )
        data = original.to_dict()
        restored = MatchInfo.from_dict(data)

        assert restored.requested_text == original.requested_text
        assert restored.requested_type == original.requested_type
        assert restored.matched_file == original.matched_file
        assert restored.matched_name == original.matched_name
        assert restored.match_score == original.match_score
        assert restored.match_found == original.match_found


class TestCategorySummary:
    """Tests for CategorySummary dataclass."""

    def test_total_calculation(self) -> None:
        """Test that total is calculated correctly."""
        summary = CategorySummary(copied=10, skipped=5, filtered=3, failed=2)
        assert summary.total == 20

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        summary = CategorySummary(copied=10, skipped=5, filtered=3, failed=2)
        data = summary.to_dict()
        assert data["COPIED"] == 10
        assert data["SKIPPED"] == 5
        assert data["FILTERED"] == 3
        assert data["FAILED"] == 2
        assert data["TOTAL"] == 20

    def test_from_dict(self) -> None:
        """Test deserialization from dictionary."""
        data = {"COPIED": 8, "SKIPPED": 4, "FILTERED": 2, "FAILED": 1}
        summary = CategorySummary.from_dict(data)
        assert summary.copied == 8
        assert summary.skipped == 4
        assert summary.filtered == 2
        assert summary.failed == 1


class TestJobReport:
    """Tests for JobReport dataclass."""

    def test_initialization(self) -> None:
        """Test JobReport initialization."""
        report = JobReport(job_id="job-001", job_name="Test Job")
        assert report.job_id == "job-001"
        assert report.job_name == "Test Job"
        assert report.matches == []
        assert report.operations == []
        assert report.summary.total == 0

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for JobReport."""
        original = JobReport(
            job_id="job-001",
            job_name="Test Job",
            start_time="2024-01-15T10:30:00",
            end_time="2024-01-15T10:35:00",
            sources=["/music", "/videos"],
            destination="/backup",
            organization_mode="single_folder",
            dry_run=False,
        )
        original.summary = CategorySummary(copied=5, skipped=2, filtered=1, failed=0)

        data = original.to_dict()
        restored = JobReport.from_dict(data)

        assert restored.job_id == original.job_id
        assert restored.job_name == original.job_name
        assert restored.start_time == original.start_time
        assert restored.end_time == original.end_time
        assert restored.sources == original.sources
        assert restored.destination == original.destination
        assert restored.organization_mode == original.organization_mode
        assert restored.dry_run == original.dry_run
        assert restored.summary.copied == original.summary.copied

    def test_to_json_from_json_roundtrip(self) -> None:
        """Test JSON string roundtrip."""
        original = JobReport(
            job_id="job-002",
            job_name="JSON Test",
        )
        json_str = original.to_json()
        restored = JobReport.from_json(json_str)

        assert restored.job_id == original.job_id
        assert restored.job_name == original.job_name

    def test_add_operation_updates_summary(self) -> None:
        """Test that add_operation updates the summary."""
        report = JobReport(job_id="job-003", job_name="Summary Test")

        report.add_operation(
            source_path="/src/file1.mp3",
            dest_path="/dst/file1.mp3",
            status=FileOperationStatus.COPIED,
            size_bytes=1024,
        )
        assert report.summary.copied == 1
        assert report.total_bytes_copied == 1024

        report.add_operation(
            source_path="/src/file2.mp3",
            dest_path="/dst/file2.mp3",
            status=FileOperationStatus.SKIPPED,
            reason="File exists",
        )
        assert report.summary.skipped == 1

        report.add_operation(
            source_path="/src/file3.mp3",
            dest_path=None,
            status=FileOperationStatus.FILTERED,
            reason="Wrong extension",
        )
        assert report.summary.filtered == 1

        report.add_operation(
            source_path="/src/file4.mp3",
            dest_path="/dst/file4.mp3",
            status=FileOperationStatus.FAILED,
            reason="Permission denied",
        )
        assert report.summary.failed == 1

        assert report.summary.total == 4

    def test_add_error(self) -> None:
        """Test adding errors to the report."""
        report = JobReport(job_id="job-004", job_name="Error Test")
        report.add_error("/src/bad_file.mp3", "Permission denied")

        assert len(report.errors) == 1
        assert report.errors[0]["source_path"] == "/src/bad_file.mp3"
        assert report.errors[0]["source_name"] == "bad_file.mp3"
        assert report.errors[0]["reason"] == "Permission denied"

    def test_add_filtered_file(self) -> None:
        """Test adding filtered files to the report."""
        report = JobReport(job_id="job-filter", job_name="Filter Test")
        report.add_filtered_file("/src/file.txt", "Extension not allowed", size_bytes=512)

        assert len(report.operations) == 1
        assert report.operations[0].status == FileOperationStatus.FILTERED
        assert report.operations[0].reason == "Extension not allowed"
        assert report.summary.filtered == 1

    def test_set_start_and_end_time(self) -> None:
        """Test setting start and end times."""
        report = JobReport(job_id="job-005", job_name="Time Test")
        assert report.start_time == ""
        assert report.end_time == ""

        report.set_start_time()
        assert report.start_time != ""
        assert "T" in report.start_time  # ISO format

        report.set_end_time()
        assert report.end_time != ""
        assert "T" in report.end_time

    def test_get_summary_text(self) -> None:
        """Test generating human-readable summary."""
        report = JobReport(
            job_id="job-006",
            job_name="Summary Text Test",
            start_time="2024-01-15T10:30:00",
            end_time="2024-01-15T10:35:00",
            dry_run=False,
        )
        report.summary = CategorySummary(copied=10, skipped=5, filtered=2, failed=1)
        report.total_bytes_copied = 10240

        summary_text = report.get_summary_text()

        assert "Summary Text Test" in summary_text
        assert "job-006" in summary_text
        assert "COPIED:   10" in summary_text
        assert "SKIPPED:  5" in summary_text
        assert "FILTERED: 2" in summary_text
        assert "FAILED:   1" in summary_text
        assert "TOTAL:    18" in summary_text
        assert "10,240" in summary_text  # bytes with comma formatting

    def test_get_summary_text_with_errors(self) -> None:
        """Test summary text includes errors."""
        report = JobReport(job_id="job-007", job_name="Error Summary")
        report.add_error("/src/file1.mp3", "Permission denied")
        report.add_error("/src/file2.mp3", "Disk full")

        summary_text = report.get_summary_text()

        assert "Errors:" in summary_text
        assert "file1.mp3" in summary_text
        assert "Permission denied" in summary_text
        assert "file2.mp3" in summary_text
        assert "Disk full" in summary_text

    def test_export_to_json_file(self, tmp_path: Path) -> None:
        """Test exporting report to JSON file."""
        report = JobReport(
            job_id="job-008",
            job_name="Export Test",
            sources=["/music"],
            destination="/backup",
        )
        report.add_operation(
            source_path="/src/song.mp3",
            dest_path="/dst/song.mp3",
            status=FileOperationStatus.COPIED,
            size_bytes=2048,
        )

        output_file = tmp_path / "report.json"
        result_path = report.export_to_json(output_file)

        assert result_path == output_file
        assert output_file.exists()

        content = output_file.read_text()
        data = json.loads(content)
        assert data["job_id"] == "job-008"
        assert data["job_name"] == "Export Test"
        assert len(data["operations"]) == 1

    def test_load_from_json_file(self, tmp_path: Path) -> None:
        """Test loading report from JSON file."""
        # Create and save a report
        original = JobReport(job_id="job-009", job_name="Load Test")
        original.summary = CategorySummary(copied=3, skipped=1, filtered=0, failed=0)

        output_file = tmp_path / "load_test.json"
        original.export_to_json(output_file)

        # Load and verify
        loaded = JobReport.load_from_json(output_file)
        assert loaded is not None
        assert loaded.job_id == "job-009"
        assert loaded.job_name == "Load Test"
        assert loaded.summary.copied == 3

    def test_load_from_nonexistent_file(self, tmp_path: Path) -> None:
        """Test loading from non-existent file returns None."""
        result = JobReport.load_from_json(tmp_path / "nonexistent.json")
        assert result is None


class TestAddMatch:
    """Tests for adding match results to job report."""

    def test_add_match_with_best_match(self) -> None:
        """Test adding a match result with a best match."""
        report = JobReport(job_id="job-010", job_name="Match Test")

        # Create a match result with a best match
        requested = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Test Song")
        media_file = MediaFile(
            path="/music/test_song.mp3",
            nombre_base="test_song",
            extension=".mp3",
            tamano=1024,
            tipo=MediaType.AUDIO,
        )
        candidate = MatchCandidate(
            media_file=media_file,
            score=95.0,
            reason="Exact match",
            is_exact=True,
        )
        match_result = MatchResult(
            requested_item=requested,
            candidates=[candidate],
            best_match=candidate,
            match_found=True,
        )

        report.add_match(match_result)

        assert len(report.matches) == 1
        match_info = report.matches[0]
        assert match_info.requested_text == "Test Song"
        assert match_info.requested_type == "song"
        assert match_info.matched_file == "/music/test_song.mp3"
        assert match_info.matched_name == "test_song"
        assert match_info.match_score == 95.0
        assert match_info.match_found is True

    def test_add_match_without_best_match(self) -> None:
        """Test adding a match result without a best match."""
        report = JobReport(job_id="job-011", job_name="No Match Test")

        requested = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Unknown Song")
        match_result = MatchResult(
            requested_item=requested,
            candidates=[],
            best_match=None,
            match_found=False,
        )

        report.add_match(match_result)

        assert len(report.matches) == 1
        match_info = report.matches[0]
        assert match_info.requested_text == "Unknown Song"
        assert match_info.matched_file is None
        assert match_info.matched_name is None
        assert match_info.match_score == 0.0
        assert match_info.match_found is False


class TestCreateJobReportFromPlanAndResult:
    """Tests for creating job report from plan and result."""

    def test_create_report_from_plan_and_result(self) -> None:
        """Test creating a complete report from copy plan and result."""
        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source="/src/file1.mp3",
                    destination="/dst/file1.mp3",
                    action=CopyItemAction.COPY,
                    size=1024,
                ),
                CopyPlanItem(
                    source="/src/file2.mp3",
                    destination="/dst/file2.mp3",
                    action=CopyItemAction.SKIP_EXISTS,
                    size=2048,
                    reason="File already exists",
                ),
            ],
            total_bytes=1024,
            files_to_copy=1,
            files_to_skip=1,
        )

        copy_report = CopyReport(
            copied=1,
            skipped=1,
            failed=0,
            bytes_copied=1024,
            errors=[],
        )

        job_report = create_job_report_from_plan_and_result(
            job_id="job-012",
            job_name="Create Test",
            plan=plan,
            copy_report=copy_report,
            sources=["/src"],
            destination="/dst",
            organization_mode="single_folder",
            dry_run=False,
            start_time="2024-01-15T10:00:00",
            end_time="2024-01-15T10:05:00",
        )

        assert job_report.job_id == "job-012"
        assert job_report.job_name == "Create Test"
        assert len(job_report.operations) == 2
        assert job_report.summary.copied == 1
        assert job_report.summary.skipped == 1

    def test_create_report_with_errors(self) -> None:
        """Test creating report that includes errors."""
        plan = CopyPlan(
            items=[
                CopyPlanItem(
                    source="/src/bad_file.mp3",
                    destination="/dst/bad_file.mp3",
                    action=CopyItemAction.COPY,
                    size=1024,
                ),
            ],
            total_bytes=1024,
            files_to_copy=1,
        )

        copy_report = CopyReport(
            copied=0,
            skipped=0,
            failed=1,
            bytes_copied=0,
            errors=[("/src/bad_file.mp3", "Permission denied")],
        )

        job_report = create_job_report_from_plan_and_result(
            job_id="job-013",
            job_name="Error Test",
            plan=plan,
            copy_report=copy_report,
        )

        assert job_report.summary.failed == 1
        assert len(job_report.errors) == 1
        assert job_report.errors[0]["reason"] == "Permission denied"


class TestAcceptanceCriteria:
    """Tests for acceptance criteria: After a job, have a reproducible report."""

    def test_reproducible_report_after_job(self, tmp_path: Path) -> None:
        """Test that after a job, a reproducible JSON report is generated."""
        # Create a job report as would happen after a job
        report = JobReport(
            job_id="job-acceptance",
            job_name="Acceptance Test Job",
            sources=["/music/collection"],
            destination="/backup/music",
            organization_mode="scatter_by_artist",
            dry_run=False,
        )
        report.set_start_time()

        # Add some matches
        requested = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Test Song")
        media_file = MediaFile(
            path="/music/test.mp3",
            nombre_base="test",
            extension=".mp3",
            tamano=2048,
            tipo=MediaType.AUDIO,
        )
        match_result = MatchResult(
            requested_item=requested,
            candidates=[MatchCandidate(media_file=media_file, score=90.0, reason="Good match")],
            best_match=MatchCandidate(media_file=media_file, score=90.0, reason="Good match"),
            match_found=True,
        )
        report.add_match(match_result)

        # Add operations
        report.add_operation(
            source_path="/music/song1.mp3",
            dest_path="/backup/Artist1/song1.mp3",
            status=FileOperationStatus.COPIED,
            size_bytes=3072,
        )
        report.add_operation(
            source_path="/music/song2.mp3",
            dest_path="/backup/Artist1/song2.mp3",
            status=FileOperationStatus.SKIPPED,
            reason="File already exists",
        )
        report.add_operation(
            source_path="/music/song3.txt",
            dest_path=None,
            status=FileOperationStatus.FILTERED,
            reason="Extension not allowed",
        )
        report.add_operation(
            source_path="/music/song4.mp3",
            dest_path="/backup/Artist2/song4.mp3",
            status=FileOperationStatus.FAILED,
            reason="Permission denied",
        )
        report.add_error("/music/song4.mp3", "Permission denied")

        report.set_end_time()

        # Export to JSON
        output_file = tmp_path / "job_report.json"
        report.export_to_json(output_file)

        # Verify the report is reproducible by loading it
        loaded = JobReport.load_from_json(output_file)
        assert loaded is not None

        # Verify all key information is preserved
        assert loaded.job_id == "job-acceptance"
        assert loaded.job_name == "Acceptance Test Job"
        assert loaded.sources == ["/music/collection"]
        assert loaded.destination == "/backup/music"
        assert loaded.organization_mode == "scatter_by_artist"

        # Verify summary
        assert loaded.summary.copied == 1
        assert loaded.summary.skipped == 1
        assert loaded.summary.filtered == 1
        assert loaded.summary.failed == 1
        assert loaded.summary.total == 4

        # Verify matches
        assert len(loaded.matches) == 1
        assert loaded.matches[0].requested_text == "Test Song"
        assert loaded.matches[0].match_found is True

        # Verify operations
        assert len(loaded.operations) == 4

        # Verify errors
        assert len(loaded.errors) == 1
        assert loaded.errors[0]["reason"] == "Permission denied"

        # Verify timestamps
        assert loaded.start_time != ""
        assert loaded.end_time != ""

        # Verify human readable summary
        summary_text = loaded.get_summary_text()
        assert "COPIED:   1" in summary_text
        assert "SKIPPED:  1" in summary_text
        assert "FILTERED: 1" in summary_text
        assert "FAILED:   1" in summary_text
