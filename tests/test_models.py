"""Unit tests for core data models."""

from __future__ import annotations

import pytest

from mediacopier.core.models import (
    CopyJob,
    CopyJobStatus,
    CopyRules,
    CopyStats,
    OrganizationMode,
    RequestedItem,
    RequestedItemType,
    ValidationError,
    export_queue_to_json,
    import_queue_from_json,
)


class TestRequestedItem:
    """Tests for RequestedItem dataclass."""

    def test_auto_normalization(self) -> None:
        """Test that texto_normalizado is auto-generated from texto_original."""
        item = RequestedItem(
            tipo=RequestedItemType.SONG,
            texto_original="  The Beatles  ",
        )
        assert item.texto_normalizado == "the beatles"

    def test_explicit_normalization(self) -> None:
        """Test that explicit texto_normalizado is preserved."""
        item = RequestedItem(
            tipo=RequestedItemType.ARTIST,
            texto_original="The Beatles",
            texto_normalizado="beatles",
        )
        assert item.texto_normalizado == "beatles"

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for RequestedItem."""
        original = RequestedItem(
            tipo=RequestedItemType.GENRE,
            texto_original="Rock & Roll",
        )
        data = original.to_dict()
        restored = RequestedItem.from_dict(data)

        assert restored.tipo == original.tipo
        assert restored.texto_original == original.texto_original
        assert restored.texto_normalizado == original.texto_normalizado


class TestCopyRules:
    """Tests for CopyRules dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        rules = CopyRules()
        assert rules.extensiones_permitidas == []
        assert rules.tamano_min_mb == 0.0
        assert rules.duracion_min_seg == 0.0
        assert rules.incluir_subcarpetas is True
        assert rules.excluir_palabras == []

    def test_validate_negative_size(self) -> None:
        """Test validation fails for negative size."""
        rules = CopyRules(tamano_min_mb=-1.0)
        with pytest.raises(ValidationError, match="tamano_min_mb no puede ser negativo"):
            rules.validate()

    def test_validate_negative_duration(self) -> None:
        """Test validation fails for negative duration."""
        rules = CopyRules(duracion_min_seg=-5.0)
        with pytest.raises(ValidationError, match="duracion_min_seg no puede ser negativa"):
            rules.validate()

    def test_valid_rules(self) -> None:
        """Test validation passes for valid rules."""
        rules = CopyRules(
            extensiones_permitidas=[".mp3", ".flac"],
            tamano_min_mb=1.0,
            duracion_min_seg=30.0,
            incluir_subcarpetas=False,
            excluir_palabras=["remix", "cover"],
        )
        rules.validate()  # Should not raise

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for CopyRules."""
        original = CopyRules(
            extensiones_permitidas=[".mp3", ".wav"],
            tamano_min_mb=5.0,
            duracion_min_seg=60.0,
            incluir_subcarpetas=False,
            excluir_palabras=["live", "demo"],
        )
        data = original.to_dict()
        restored = CopyRules.from_dict(data)

        assert restored.extensiones_permitidas == original.extensiones_permitidas
        assert restored.tamano_min_mb == original.tamano_min_mb
        assert restored.duracion_min_seg == original.duracion_min_seg
        assert restored.incluir_subcarpetas == original.incluir_subcarpetas
        assert restored.excluir_palabras == original.excluir_palabras


class TestCopyStats:
    """Tests for CopyStats dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        stats = CopyStats()
        assert stats.archivos_encontrados == 0
        assert stats.archivos_copiados == 0
        assert stats.archivos_omitidos == 0
        assert stats.archivos_error == 0
        assert stats.bytes_copiados == 0

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for CopyStats."""
        original = CopyStats(
            archivos_encontrados=100,
            archivos_copiados=95,
            archivos_omitidos=3,
            archivos_error=2,
            bytes_copiados=1024 * 1024 * 500,
        )
        data = original.to_dict()
        restored = CopyStats.from_dict(data)

        assert restored.archivos_encontrados == original.archivos_encontrados
        assert restored.archivos_copiados == original.archivos_copiados
        assert restored.archivos_omitidos == original.archivos_omitidos
        assert restored.archivos_error == original.archivos_error
        assert restored.bytes_copiados == original.bytes_copiados


class TestCopyJob:
    """Tests for CopyJob dataclass."""

    def test_validate_missing_destino(self) -> None:
        """Test validation fails when destino is empty."""
        job = CopyJob(
            nombre="Test Job",
            origenes=["/music"],
            destino="",
        )
        with pytest.raises(ValidationError, match="El destino no puede estar vacío"):
            job.validate()

    def test_validate_missing_origenes(self) -> None:
        """Test validation fails when origenes is empty."""
        job = CopyJob(
            nombre="Test Job",
            origenes=[],
            destino="/dest",
        )
        with pytest.raises(ValidationError, match="Debe especificar al menos un origen"):
            job.validate()

    def test_validate_invalid_rules(self) -> None:
        """Test validation propagates rule validation errors."""
        job = CopyJob(
            nombre="Test Job",
            origenes=["/music"],
            destino="/dest",
            reglas=CopyRules(tamano_min_mb=-10),
        )
        with pytest.raises(ValidationError, match="tamano_min_mb no puede ser negativo"):
            job.validate()

    def test_validate_nonexistent_origen(self, tmp_path) -> None:
        """Test validation fails when origen doesn't exist and check_origen_exists=True."""
        job = CopyJob(
            nombre="Test Job",
            origenes=["/nonexistent/path"],
            destino=str(tmp_path / "dest"),
        )
        with pytest.raises(ValidationError, match="El origen no existe"):
            job.validate(check_origen_exists=True)

    def test_validate_existing_origen(self, tmp_path) -> None:
        """Test validation passes when origen exists."""
        origen = tmp_path / "source"
        origen.mkdir()
        job = CopyJob(
            nombre="Test Job",
            origenes=[str(origen)],
            destino=str(tmp_path / "dest"),
        )
        job.validate(check_origen_exists=True)  # Should not raise

    def test_valid_job(self) -> None:
        """Test validation passes for a valid job."""
        job = CopyJob(
            nombre="Test Job",
            origenes=["/music"],
            destino="/dest",
        )
        job.validate()  # Should not raise

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for CopyJob."""
        original = CopyJob(
            nombre="Music Copy",
            origenes=["/music/rock", "/music/jazz"],
            destino="/backup/music",
            modo_organizacion=OrganizationMode.SCATTER_BY_ARTIST,
            lista_items=[
                RequestedItem(tipo=RequestedItemType.ARTIST, texto_original="Pink Floyd"),
                RequestedItem(tipo=RequestedItemType.GENRE, texto_original="Rock"),
            ],
            reglas=CopyRules(
                extensiones_permitidas=[".mp3", ".flac"],
                tamano_min_mb=1.0,
            ),
            estado=CopyJobStatus.RUNNING,
            stats=CopyStats(archivos_encontrados=50, archivos_copiados=25),
        )

        data = original.to_dict()
        restored = CopyJob.from_dict(data)

        assert restored.id == original.id
        assert restored.nombre == original.nombre
        assert restored.origenes == original.origenes
        assert restored.destino == original.destino
        assert restored.modo_organizacion == original.modo_organizacion
        assert len(restored.lista_items) == len(original.lista_items)
        assert restored.lista_items[0].texto_original == original.lista_items[0].texto_original
        assert restored.reglas.extensiones_permitidas == original.reglas.extensiones_permitidas
        assert restored.estado == original.estado
        assert restored.stats.archivos_encontrados == original.stats.archivos_encontrados

    def test_to_json_from_json_roundtrip(self) -> None:
        """Test full JSON string roundtrip for CopyJob."""
        original = CopyJob(
            nombre="Full Test",
            origenes=["/src"],
            destino="/dst",
            modo_organizacion=OrganizationMode.FOLDER_PER_REQUEST,
            lista_items=[
                RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="Inception")
            ],
            reglas=CopyRules(duracion_min_seg=300.0),
            estado=CopyJobStatus.COMPLETED,
            stats=CopyStats(archivos_copiados=10, bytes_copiados=1024000),
        )

        json_str = original.to_json()
        restored = CopyJob.from_json(json_str)

        assert restored.id == original.id
        assert restored.nombre == original.nombre
        assert restored.destino == original.destino
        assert restored.modo_organizacion == original.modo_organizacion
        assert restored.lista_items[0].texto_original == "Inception"
        assert restored.reglas.duracion_min_seg == 300.0
        assert restored.estado == CopyJobStatus.COMPLETED
        assert restored.stats.bytes_copiados == 1024000


class TestQueueExportImport:
    """Tests for queue export/import functions."""

    def test_export_import_queue_roundtrip(self) -> None:
        """Test that exporting and importing a queue preserves all data."""
        jobs = [
            CopyJob(
                nombre="Job 1",
                origenes=["/music"],
                destino="/backup1",
                modo_organizacion=OrganizationMode.SINGLE_FOLDER,
                lista_items=[
                    RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song A")
                ],
                estado=CopyJobStatus.PENDING,
            ),
            CopyJob(
                nombre="Job 2",
                origenes=["/movies", "/series"],
                destino="/backup2",
                modo_organizacion=OrganizationMode.KEEP_RELATIVE,
                lista_items=[
                    RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="Movie B"),
                    RequestedItem(tipo=RequestedItemType.FOLDER, texto_original="Series C"),
                ],
                reglas=CopyRules(
                    extensiones_permitidas=[".mkv", ".avi"],
                    tamano_min_mb=100.0,
                ),
                estado=CopyJobStatus.COMPLETED,
                stats=CopyStats(
                    archivos_encontrados=500,
                    archivos_copiados=450,
                    archivos_omitidos=40,
                    archivos_error=10,
                    bytes_copiados=1024 * 1024 * 1024 * 50,
                ),
            ),
        ]

        json_str = export_queue_to_json(jobs)
        restored_jobs = import_queue_from_json(json_str)

        assert len(restored_jobs) == len(jobs)

        # Verify first job
        assert restored_jobs[0].id == jobs[0].id
        assert restored_jobs[0].nombre == jobs[0].nombre
        assert restored_jobs[0].origenes == jobs[0].origenes
        assert restored_jobs[0].destino == jobs[0].destino
        assert restored_jobs[0].modo_organizacion == jobs[0].modo_organizacion
        assert len(restored_jobs[0].lista_items) == 1
        assert restored_jobs[0].lista_items[0].texto_original == "Song A"
        assert restored_jobs[0].estado == CopyJobStatus.PENDING

        # Verify second job
        assert restored_jobs[1].id == jobs[1].id
        assert restored_jobs[1].nombre == jobs[1].nombre
        assert restored_jobs[1].origenes == jobs[1].origenes
        assert restored_jobs[1].destino == jobs[1].destino
        assert restored_jobs[1].modo_organizacion == OrganizationMode.KEEP_RELATIVE
        assert len(restored_jobs[1].lista_items) == 2
        assert restored_jobs[1].reglas.extensiones_permitidas == [".mkv", ".avi"]
        assert restored_jobs[1].reglas.tamano_min_mb == 100.0
        assert restored_jobs[1].estado == CopyJobStatus.COMPLETED
        assert restored_jobs[1].stats.archivos_encontrados == 500
        assert restored_jobs[1].stats.archivos_copiados == 450
        assert restored_jobs[1].stats.bytes_copiados == 1024 * 1024 * 1024 * 50

    def test_export_empty_queue(self) -> None:
        """Test exporting an empty queue."""
        json_str = export_queue_to_json([])
        restored = import_queue_from_json(json_str)
        assert restored == []


class TestOrganizationModeEnum:
    """Tests for OrganizationMode enum."""

    def test_all_modes_exist(self) -> None:
        """Test that all required modes exist."""
        assert OrganizationMode.SINGLE_FOLDER.value == "single_folder"
        assert OrganizationMode.SCATTER_BY_ARTIST.value == "scatter_by_artist"
        assert OrganizationMode.SCATTER_BY_GENRE.value == "scatter_by_genre"
        assert OrganizationMode.FOLDER_PER_REQUEST.value == "folder_per_request"
        assert OrganizationMode.KEEP_RELATIVE.value == "keep_relative"


class TestRequestedItemTypeEnum:
    """Tests for RequestedItemType enum."""

    def test_all_types_exist(self) -> None:
        """Test that all required types exist."""
        assert RequestedItemType.SONG.value == "song"
        assert RequestedItemType.MOVIE.value == "movie"
        assert RequestedItemType.GENRE.value == "genre"
        assert RequestedItemType.ARTIST.value == "artist"
        assert RequestedItemType.FOLDER.value == "folder"
