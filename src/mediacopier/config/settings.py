"""Configuración de MediaCopier."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TechAuraSettings:
    """Configuración para la conexión con TechAura API."""

    api_url: str = ""
    api_key: str = ""
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60
    polling_interval_seconds: int = 30

    # Legacy alias for backwards compatibility
    @property
    def polling_interval(self) -> int:
        """Alias for polling_interval_seconds for backward compatibility."""
        return self.polling_interval_seconds

    def __post_init__(self) -> None:
        """Inicializa valores desde variables de entorno si no se proporcionan."""
        if not self.api_url:
            self.api_url = os.getenv("TECHAURA_API_URL", "http://localhost:3006")
        if not self.api_key:
            self.api_key = os.getenv("TECHAURA_API_KEY", "")

        # Load numeric settings from environment
        polling_env = os.getenv("TECHAURA_POLLING_INTERVAL")
        if polling_env:
            try:
                self.polling_interval_seconds = int(polling_env)
            except ValueError:
                pass  # Keep default value if env var is not a valid integer

        timeout_env = os.getenv("TECHAURA_TIMEOUT_SECONDS")
        if timeout_env:
            try:
                self.timeout_seconds = int(timeout_env)
            except ValueError:
                pass

        max_retries_env = os.getenv("TECHAURA_MAX_RETRIES")
        if max_retries_env:
            try:
                self.max_retries = int(max_retries_env)
            except ValueError:
                pass

        retry_delay_env = os.getenv("TECHAURA_RETRY_DELAY_SECONDS")
        if retry_delay_env:
            try:
                self.retry_delay_seconds = float(retry_delay_env)
            except ValueError:
                pass

        cb_threshold_env = os.getenv("TECHAURA_CIRCUIT_BREAKER_THRESHOLD")
        if cb_threshold_env:
            try:
                self.circuit_breaker_threshold = int(cb_threshold_env)
            except ValueError:
                pass

        cb_timeout_env = os.getenv("TECHAURA_CIRCUIT_BREAKER_TIMEOUT")
        if cb_timeout_env:
            try:
                self.circuit_breaker_timeout = int(cb_timeout_env)
            except ValueError:
                pass


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
class ContentSettings:
    """Configuración de rutas de contenido para diferentes tipos de productos."""

    music_path: str = ""
    videos_path: str = ""
    movies_path: str = ""

    def __post_init__(self) -> None:
        """Inicializa valores desde variables de entorno si no se proporcionan."""
        if not self.music_path:
            self.music_path = os.getenv("CONTENT_PATH_MUSIC", "")
        if not self.videos_path:
            self.videos_path = os.getenv("CONTENT_PATH_VIDEOS", "")
        if not self.movies_path:
            self.movies_path = os.getenv("CONTENT_PATH_MOVIES", "")

    def get_path_for_type(self, product_type: str) -> str:
        """Obtener la ruta para un tipo de producto específico.

        Args:
            product_type: Tipo de producto ('music', 'videos', 'movies').

        Returns:
            Ruta configurada para el tipo de producto o cadena vacía si no existe.
        """
        paths = {
            "music": self.music_path,
            "videos": self.videos_path,
            "movies": self.movies_path,
        }
        return paths.get(product_type, "")

    def validate(self) -> list[str]:
        """Validar que las rutas configuradas existen.

        Returns:
            Lista de errores de validación. Lista vacía si todo es válido.
        """
        errors = []
        for name, path in [
            ("music", self.music_path),
            ("videos", self.videos_path),
            ("movies", self.movies_path),
        ]:
            if path and not os.path.isdir(path):
                errors.append(f"Path for {name} does not exist: {path}")
        return errors


@dataclass
class Settings:
    """Configuración principal de MediaCopier."""

    techaura: TechAuraSettings = field(default_factory=TechAuraSettings)
    content_paths: ContentPaths = field(default_factory=ContentPaths)
    content: ContentSettings = field(default_factory=ContentSettings)


def get_settings() -> Settings:
    """Obtiene la configuración de la aplicación.

    Returns:
        Instancia de Settings con la configuración actual.
    """
    return Settings()
