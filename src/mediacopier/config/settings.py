"""Configuración de MediaCopier."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TechAuraSettings:
    """Configuración para la conexión con TechAura API."""

    api_url: str = ""
    api_key: str = ""
    polling_interval: int = 30  # segundos

    def __post_init__(self) -> None:
        """Inicializa valores desde variables de entorno si no se proporcionan."""
        if not self.api_url:
            self.api_url = os.getenv("TECHAURA_API_URL", "http://localhost:3006")
        if not self.api_key:
            self.api_key = os.getenv("TECHAURA_API_KEY", "")
        polling_env = os.getenv("TECHAURA_POLLING_INTERVAL")
        if polling_env:
            self.polling_interval = int(polling_env)


@dataclass
class ContentPaths:
    """Rutas de contenido para música, videos y películas."""

    music_path: Path = field(default_factory=lambda: Path("/content/music"))
    videos_path: Path = field(default_factory=lambda: Path("/content/videos"))
    movies_path: Path = field(default_factory=lambda: Path("/content/movies"))

    def __post_init__(self) -> None:
        """Inicializa valores desde variables de entorno si están disponibles."""
        music_env = os.getenv("CONTENT_MUSIC_PATH")
        if music_env:
            self.music_path = Path(music_env)

        videos_env = os.getenv("CONTENT_VIDEOS_PATH")
        if videos_env:
            self.videos_path = Path(videos_env)

        movies_env = os.getenv("CONTENT_MOVIES_PATH")
        if movies_env:
            self.movies_path = Path(movies_env)


@dataclass
class Settings:
    """Configuración principal de MediaCopier."""

    techaura: TechAuraSettings = field(default_factory=TechAuraSettings)
    content_paths: ContentPaths = field(default_factory=ContentPaths)


def get_settings() -> Settings:
    """Obtiene la configuración de la aplicación.

    Returns:
        Instancia de Settings con la configuración actual.
    """
    return Settings()
