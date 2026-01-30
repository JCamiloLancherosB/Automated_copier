"""Tests para el módulo de configuración."""

from pathlib import Path
from unittest.mock import patch

from mediacopier.config.settings import (
    ContentPaths,
    Settings,
    TechAuraSettings,
    get_settings,
)


class TestTechAuraSettings:
    """Tests para TechAuraSettings."""

    def test_default_values(self) -> None:
        """Test de valores por defecto."""
        settings = TechAuraSettings()
        assert settings.api_url == "http://localhost:3006"
        assert settings.api_key == ""
        assert settings.polling_interval == 30

    def test_custom_values(self) -> None:
        """Test con valores personalizados."""
        settings = TechAuraSettings(
            api_url="https://custom.api.com",
            api_key="custom-key",
            polling_interval_seconds=60,
        )
        assert settings.api_url == "https://custom.api.com"
        assert settings.api_key == "custom-key"
        assert settings.polling_interval == 60

    def test_env_variables(self) -> None:
        """Test de lectura de variables de entorno."""
        with patch.dict(
            "os.environ",
            {
                "TECHAURA_API_URL": "https://env.api.com",
                "TECHAURA_API_KEY": "env-key",
                "TECHAURA_POLLING_INTERVAL": "120",
            },
        ):
            settings = TechAuraSettings()
            assert settings.api_url == "https://env.api.com"
            assert settings.api_key == "env-key"
            assert settings.polling_interval == 120

    def test_invalid_polling_interval_env(self) -> None:
        """Test de valor inválido para polling_interval en variable de entorno."""
        with patch.dict(
            "os.environ",
            {"TECHAURA_POLLING_INTERVAL": "invalid"},
        ):
            settings = TechAuraSettings()
            # Should keep default value when env var is invalid
            assert settings.polling_interval == 30

    def test_custom_value_overrides_env(self) -> None:
        """Test de que valores personalizados tienen prioridad sobre env."""
        with patch.dict(
            "os.environ",
            {"TECHAURA_API_URL": "https://env.api.com"},
        ):
            settings = TechAuraSettings(api_url="https://custom.api.com")
            assert settings.api_url == "https://custom.api.com"


class TestContentPaths:
    """Tests para ContentPaths."""

    def test_default_values(self) -> None:
        """Test de valores por defecto."""
        paths = ContentPaths()
        assert paths.music_path == Path("/content/music")
        assert paths.videos_path == Path("/content/videos")
        assert paths.movies_path == Path("/content/movies")

    def test_custom_values(self) -> None:
        """Test con valores personalizados."""
        paths = ContentPaths(
            music_path=Path("/custom/music"),
            videos_path=Path("/custom/videos"),
            movies_path=Path("/custom/movies"),
        )
        assert paths.music_path == Path("/custom/music")
        assert paths.videos_path == Path("/custom/videos")
        assert paths.movies_path == Path("/custom/movies")

    def test_env_variables(self) -> None:
        """Test de lectura de variables de entorno."""
        with patch.dict(
            "os.environ",
            {
                "CONTENT_MUSIC_PATH": "/env/music",
                "CONTENT_VIDEOS_PATH": "/env/videos",
                "CONTENT_MOVIES_PATH": "/env/movies",
            },
        ):
            paths = ContentPaths()
            assert paths.music_path == Path("/env/music")
            assert paths.videos_path == Path("/env/videos")
            assert paths.movies_path == Path("/env/movies")

    def test_partial_env_variables(self) -> None:
        """Test de lectura parcial de variables de entorno."""
        with patch.dict(
            "os.environ",
            {"CONTENT_MUSIC_PATH": "/env/music"},
            clear=False,
        ):
            paths = ContentPaths()
            assert paths.music_path == Path("/env/music")
            assert paths.videos_path == Path("/content/videos")  # Default
            assert paths.movies_path == Path("/content/movies")  # Default


class TestSettings:
    """Tests para Settings."""

    def test_default_initialization(self) -> None:
        """Test de inicialización por defecto."""
        settings = Settings()
        assert isinstance(settings.techaura, TechAuraSettings)
        assert isinstance(settings.content_paths, ContentPaths)

    def test_custom_initialization(self) -> None:
        """Test de inicialización con valores personalizados."""
        techaura = TechAuraSettings(api_url="https://custom.api.com")
        content_paths = ContentPaths(music_path=Path("/custom/music"))
        settings = Settings(techaura=techaura, content_paths=content_paths)
        
        assert settings.techaura.api_url == "https://custom.api.com"
        assert settings.content_paths.music_path == Path("/custom/music")


class TestGetSettings:
    """Tests para la función get_settings."""

    def test_returns_settings_instance(self) -> None:
        """Test de que get_settings devuelve una instancia de Settings."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_uses_env_variables(self) -> None:
        """Test de que get_settings usa variables de entorno."""
        with patch.dict(
            "os.environ",
            {
                "TECHAURA_API_URL": "https://env.api.com",
                "CONTENT_MUSIC_PATH": "/env/music",
            },
        ):
            settings = get_settings()
            assert settings.techaura.api_url == "https://env.api.com"
            assert settings.content_paths.music_path == Path("/env/music")
