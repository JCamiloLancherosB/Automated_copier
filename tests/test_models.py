"""Unit tests for core data models."""

from __future__ import annotations

import pytest

from mediacopier.core.models import (
    CopyJob,
    CopyJobStatus,
    CopyRules,
    CopyStats,
    OrganizationMode,
    Profile,
    ProfileManager,
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
        assert rules.organizar_por_genero is False

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
            lista_items=[RequestedItem(tipo=RequestedItemType.MOVIE, texto_original="Inception")],
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
                lista_items=[RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song A")],
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


class TestCopyRulesNewFields:
    """Tests for new CopyRules fields."""

    def test_new_default_values(self) -> None:
        """Test that new default values are set correctly."""
        rules = CopyRules()
        assert rules.filtrar_por_tamano is False
        assert rules.filtrar_por_duracion is False
        assert rules.solo_extensiones_seleccionadas is False
        assert rules.dry_run is False
        assert rules.evitar_duplicados is True
        assert rules.usar_fuzzy is True
        assert rules.umbral_fuzzy == 60.0

    def test_validate_invalid_fuzzy_threshold_negative(self) -> None:
        """Test validation fails for negative fuzzy threshold."""
        rules = CopyRules(umbral_fuzzy=-10.0)
        with pytest.raises(ValidationError, match="umbral_fuzzy debe estar entre 0 y 100"):
            rules.validate()

    def test_validate_invalid_fuzzy_threshold_over_100(self) -> None:
        """Test validation fails for fuzzy threshold over 100."""
        rules = CopyRules(umbral_fuzzy=150.0)
        with pytest.raises(ValidationError, match="umbral_fuzzy debe estar entre 0 y 100"):
            rules.validate()

    def test_validate_valid_fuzzy_threshold(self) -> None:
        """Test validation passes for valid fuzzy threshold."""
        rules = CopyRules(umbral_fuzzy=85.0)
        rules.validate()  # Should not raise

    def test_new_fields_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for new CopyRules fields."""
        original = CopyRules(
            filtrar_por_tamano=True,
            filtrar_por_duracion=True,
            solo_extensiones_seleccionadas=True,
            dry_run=True,
            evitar_duplicados=False,
            usar_fuzzy=False,
            umbral_fuzzy=75.0,
        )
        data = original.to_dict()
        restored = CopyRules.from_dict(data)

        assert restored.filtrar_por_tamano == original.filtrar_por_tamano
        assert restored.filtrar_por_duracion == original.filtrar_por_duracion
        assert restored.solo_extensiones_seleccionadas == original.solo_extensiones_seleccionadas
        assert restored.dry_run == original.dry_run
        assert restored.evitar_duplicados == original.evitar_duplicados
        assert restored.usar_fuzzy == original.usar_fuzzy
        assert restored.umbral_fuzzy == original.umbral_fuzzy


class TestAdvancedRulesFields:
    """Tests for advanced CopyRules fields (extension filtering, movie preferences)."""

    def test_advanced_default_values(self) -> None:
        """Test that advanced filtering default values are set correctly."""
        rules = CopyRules()
        assert rules.extensiones_audio_permitidas == []
        assert rules.extensiones_audio_bloqueadas == []
        assert rules.extensiones_video_permitidas == []
        assert rules.extensiones_video_bloqueadas == []
        assert rules.solo_mejor_match is False
        assert rules.preferir_resolucion_alta is True
        assert rules.codecs_preferidos == []
        assert rules.tamano_max_mb == 0.0
        assert rules.duracion_max_seg == 0.0

    def test_validate_negative_max_size(self) -> None:
        """Test validation fails for negative max size."""
        rules = CopyRules(tamano_max_mb=-10.0)
        with pytest.raises(ValidationError, match="tamano_max_mb no puede ser negativo"):
            rules.validate()

    def test_validate_negative_max_duration(self) -> None:
        """Test validation fails for negative max duration."""
        rules = CopyRules(duracion_max_seg=-100.0)
        with pytest.raises(ValidationError, match="duracion_max_seg no puede ser negativa"):
            rules.validate()

    def test_advanced_fields_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for advanced CopyRules fields."""
        original = CopyRules(
            extensiones_audio_permitidas=[".mp3", ".flac"],
            extensiones_audio_bloqueadas=[".wma", ".aac"],
            extensiones_video_permitidas=[".mkv", ".mp4"],
            extensiones_video_bloqueadas=[".avi", ".wmv"],
            solo_mejor_match=True,
            preferir_resolucion_alta=True,
            codecs_preferidos=["h264", "hevc", "x265"],
            tamano_max_mb=5000.0,
            duracion_max_seg=10800.0,
        )
        data = original.to_dict()
        restored = CopyRules.from_dict(data)

        assert restored.extensiones_audio_permitidas == original.extensiones_audio_permitidas
        assert restored.extensiones_audio_bloqueadas == original.extensiones_audio_bloqueadas
        assert restored.extensiones_video_permitidas == original.extensiones_video_permitidas
        assert restored.extensiones_video_bloqueadas == original.extensiones_video_bloqueadas
        assert restored.solo_mejor_match == original.solo_mejor_match
        assert restored.preferir_resolucion_alta == original.preferir_resolucion_alta
        assert restored.codecs_preferidos == original.codecs_preferidos
        assert restored.tamano_max_mb == original.tamano_max_mb
        assert restored.duracion_max_seg == original.duracion_max_seg

    def test_exclusion_words_list(self) -> None:
        """Test exclusion words list in rules."""
        rules = CopyRules(
            excluir_palabras=["sample", "trailer", "camrip", "low quality"]
        )
        assert "sample" in rules.excluir_palabras
        assert "trailer" in rules.excluir_palabras
        assert "camrip" in rules.excluir_palabras
        assert "low quality" in rules.excluir_palabras

    def test_full_advanced_rules_roundtrip(self) -> None:
        """Test complete advanced rules configuration roundtrip."""
        original = CopyRules(
            excluir_palabras=["sample", "trailer", "camrip"],
            extensiones_audio_permitidas=[".mp3", ".flac", ".wav"],
            extensiones_video_permitidas=[".mkv", ".mp4"],
            extensiones_video_bloqueadas=[".avi"],
            solo_mejor_match=True,
            preferir_resolucion_alta=True,
            codecs_preferidos=["h264", "hevc"],
            tamano_min_mb=10.0,
            tamano_max_mb=5000.0,
            duracion_min_seg=60.0,
            duracion_max_seg=7200.0,
            filtrar_por_tamano=True,
            filtrar_por_duracion=True,
        )
        original.validate()  # Should not raise

        data = original.to_dict()
        restored = CopyRules.from_dict(data)
        restored.validate()  # Should not raise

        # Verify all fields match
        assert restored.excluir_palabras == original.excluir_palabras
        assert restored.extensiones_audio_permitidas == original.extensiones_audio_permitidas
        assert restored.extensiones_video_permitidas == original.extensiones_video_permitidas
        assert restored.extensiones_video_bloqueadas == original.extensiones_video_bloqueadas
        assert restored.solo_mejor_match == original.solo_mejor_match
        assert restored.preferir_resolucion_alta == original.preferir_resolucion_alta
        assert restored.codecs_preferidos == original.codecs_preferidos
        assert restored.tamano_min_mb == original.tamano_min_mb
        assert restored.tamano_max_mb == original.tamano_max_mb
        assert restored.duracion_min_seg == original.duracion_min_seg
        assert restored.duracion_max_seg == original.duracion_max_seg


class TestProfile:
    """Tests for Profile dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        profile = Profile(nombre="Test Profile")
        assert profile.nombre == "Test Profile"
        assert profile.modo_organizacion == OrganizationMode.SINGLE_FOLDER
        assert isinstance(profile.reglas, CopyRules)

    def test_validate_empty_name(self) -> None:
        """Test validation fails for empty name."""
        profile = Profile(nombre="")
        with pytest.raises(ValidationError, match="El nombre del perfil no puede estar vacío"):
            profile.validate()

    def test_validate_whitespace_name(self) -> None:
        """Test validation fails for whitespace-only name."""
        profile = Profile(nombre="   ")
        with pytest.raises(ValidationError, match="El nombre del perfil no puede estar vacío"):
            profile.validate()

    def test_validate_propagates_rules_error(self) -> None:
        """Test validation propagates rule validation errors."""
        profile = Profile(
            nombre="Test Profile",
            reglas=CopyRules(tamano_min_mb=-10),
        )
        with pytest.raises(ValidationError, match="tamano_min_mb no puede ser negativo"):
            profile.validate()

    def test_valid_profile(self) -> None:
        """Test validation passes for a valid profile."""
        profile = Profile(
            nombre="USB Música",
            reglas=CopyRules(
                extensiones_permitidas=[".mp3", ".flac"],
                tamano_min_mb=1.0,
                usar_fuzzy=True,
                umbral_fuzzy=70.0,
            ),
            modo_organizacion=OrganizationMode.SCATTER_BY_ARTIST,
        )
        profile.validate()  # Should not raise

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test JSON roundtrip for Profile."""
        original = Profile(
            nombre="USB Música",
            reglas=CopyRules(
                extensiones_permitidas=[".mp3", ".flac"],
                tamano_min_mb=1.0,
                filtrar_por_tamano=True,
                usar_fuzzy=True,
                umbral_fuzzy=70.0,
            ),
            modo_organizacion=OrganizationMode.SCATTER_BY_ARTIST,
        )
        data = original.to_dict()
        restored = Profile.from_dict(data)

        assert restored.nombre == original.nombre
        assert restored.modo_organizacion == original.modo_organizacion
        assert restored.reglas.extensiones_permitidas == original.reglas.extensiones_permitidas
        assert restored.reglas.tamano_min_mb == original.reglas.tamano_min_mb
        assert restored.reglas.filtrar_por_tamano == original.reglas.filtrar_por_tamano
        assert restored.reglas.usar_fuzzy == original.reglas.usar_fuzzy
        assert restored.reglas.umbral_fuzzy == original.reglas.umbral_fuzzy

    def test_to_json_from_json_roundtrip(self) -> None:
        """Test full JSON string roundtrip for Profile."""
        original = Profile(
            nombre="Video Backup",
            reglas=CopyRules(
                extensiones_permitidas=[".mp4", ".mkv"],
                duracion_min_seg=600.0,
                filtrar_por_duracion=True,
                dry_run=True,
            ),
            modo_organizacion=OrganizationMode.FOLDER_PER_REQUEST,
        )
        json_str = original.to_json()
        restored = Profile.from_json(json_str)

        assert restored.nombre == original.nombre
        assert restored.modo_organizacion == original.modo_organizacion
        assert restored.reglas.extensiones_permitidas == original.reglas.extensiones_permitidas
        assert restored.reglas.duracion_min_seg == original.reglas.duracion_min_seg
        assert restored.reglas.filtrar_por_duracion == original.reglas.filtrar_por_duracion
        assert restored.reglas.dry_run == original.reglas.dry_run


class TestProfileManager:
    """Tests for ProfileManager."""

    def test_save_and_load_profile(self, tmp_path) -> None:
        """Test saving and loading a profile."""
        manager = ProfileManager(profiles_dir=str(tmp_path))
        profile = Profile(
            nombre="USB Música",
            reglas=CopyRules(
                extensiones_permitidas=[".mp3", ".flac"],
                tamano_min_mb=1.0,
                usar_fuzzy=True,
                umbral_fuzzy=70.0,
            ),
            modo_organizacion=OrganizationMode.SCATTER_BY_ARTIST,
        )
        manager.save_profile(profile)

        loaded = manager.load_profile("USB Música")
        assert loaded is not None
        assert loaded.nombre == "USB Música"
        assert loaded.reglas.extensiones_permitidas == [".mp3", ".flac"]
        assert loaded.reglas.tamano_min_mb == 1.0
        assert loaded.modo_organizacion == OrganizationMode.SCATTER_BY_ARTIST

    def test_load_nonexistent_profile(self, tmp_path) -> None:
        """Test loading a profile that doesn't exist."""
        manager = ProfileManager(profiles_dir=str(tmp_path))
        loaded = manager.load_profile("Nonexistent")
        assert loaded is None

    def test_list_profiles(self, tmp_path) -> None:
        """Test listing all profiles."""
        manager = ProfileManager(profiles_dir=str(tmp_path))

        # Save multiple profiles
        manager.save_profile(Profile(nombre="Profile A"))
        manager.save_profile(Profile(nombre="Profile B"))
        manager.save_profile(Profile(nombre="Profile C"))

        profiles = manager.list_profiles()
        assert len(profiles) == 3
        assert "Profile A" in profiles
        assert "Profile B" in profiles
        assert "Profile C" in profiles

    def test_delete_profile(self, tmp_path) -> None:
        """Test deleting a profile."""
        manager = ProfileManager(profiles_dir=str(tmp_path))
        profile = Profile(nombre="Test Profile")
        manager.save_profile(profile)

        assert manager.delete_profile("Test Profile") is True
        assert manager.load_profile("Test Profile") is None

    def test_delete_nonexistent_profile(self, tmp_path) -> None:
        """Test deleting a profile that doesn't exist."""
        manager = ProfileManager(profiles_dir=str(tmp_path))
        assert manager.delete_profile("Nonexistent") is False

    def test_save_profile_validates(self, tmp_path) -> None:
        """Test that saving a profile validates it first."""
        manager = ProfileManager(profiles_dir=str(tmp_path))
        profile = Profile(nombre="", reglas=CopyRules())

        with pytest.raises(ValidationError):
            manager.save_profile(profile)

    def test_acceptance_criteria_usb_musica_profile(self, tmp_path) -> None:
        """Test acceptance criteria: save and load 'USB Música' profile for a new job."""
        manager = ProfileManager(profiles_dir=str(tmp_path))

        # Create and save the "USB Música" profile
        usb_musica = Profile(
            nombre="USB Música",
            reglas=CopyRules(
                extensiones_permitidas=[".mp3", ".flac", ".wav"],
                tamano_min_mb=0.5,
                filtrar_por_tamano=True,
                evitar_duplicados=True,
                usar_fuzzy=True,
                umbral_fuzzy=65.0,
            ),
            modo_organizacion=OrganizationMode.SCATTER_BY_ARTIST,
        )
        manager.save_profile(usb_musica)

        # List profiles and verify it's there
        profiles = manager.list_profiles()
        assert "USB Música" in profiles

        # Load the profile and apply it to a new job
        loaded_profile = manager.load_profile("USB Música")
        assert loaded_profile is not None

        # Verify all settings were preserved
        assert loaded_profile.nombre == "USB Música"
        assert loaded_profile.reglas.extensiones_permitidas == [".mp3", ".flac", ".wav"]
        assert loaded_profile.reglas.tamano_min_mb == 0.5
        assert loaded_profile.reglas.filtrar_por_tamano is True
        assert loaded_profile.reglas.evitar_duplicados is True
        assert loaded_profile.reglas.usar_fuzzy is True
        assert loaded_profile.reglas.umbral_fuzzy == 65.0
        assert loaded_profile.modo_organizacion == OrganizationMode.SCATTER_BY_ARTIST
