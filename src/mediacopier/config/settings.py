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
class UIState:
    """Estado persistente de la UI."""

    window_width: int = 1200
    window_height: int = 800
    window_x: int | None = None
    window_y: int | None = None
    auto_refresh_enabled: bool = True
    last_destination: str = ""

    def to_dict(self) -> dict:
        """Convertir a diccionario."""
        return {
            "window_width": self.window_width,
            "window_height": self.window_height,
            "window_x": self.window_x,
            "window_y": self.window_y,
            "auto_refresh_enabled": self.auto_refresh_enabled,
            "last_destination": self.last_destination,
        }

    @staticmethod
    def from_dict(data: dict) -> "UIState":
        """Crear desde diccionario."""
        return UIState(
            window_width=data.get("window_width", 1200),
            window_height=data.get("window_height", 800),
            window_x=data.get("window_x"),
            window_y=data.get("window_y"),
            auto_refresh_enabled=data.get("auto_refresh_enabled", True),
            last_destination=data.get("last_destination", ""),
        )


@dataclass
class Settings:
    """Configuración principal de MediaCopier."""

    techaura: TechAuraSettings = field(default_factory=TechAuraSettings)
    content_paths: ContentPaths = field(default_factory=ContentPaths)
    content: ContentSettings = field(default_factory=ContentSettings)
    ui_state: UIState = field(default_factory=UIState)


def get_settings() -> Settings:
    """Obtiene la configuración de la aplicación.

    Returns:
        Instancia de Settings con la configuración actual.
    """
    return Settings()


def load_ui_state() -> UIState:
    """Carga el estado de la UI desde archivo.

    Returns:
        Estado de la UI guardado o estado por defecto.
    """
    import json
    from pathlib import Path

    config_dir = Path.home() / ".mediacopier"
    config_file = config_dir / "ui_state.json"

    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                data = json.load(f)
                return UIState.from_dict(data)
        except (json.JSONDecodeError, IOError):
            pass

    return UIState()


def save_ui_state(ui_state: UIState) -> None:
    """Guarda el estado de la UI en archivo.

    Args:
        ui_state: Estado de la UI a guardar.
    """
    import json
    from pathlib import Path

    config_dir = Path.home() / ".mediacopier"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "ui_state.json"

    try:
        with open(config_file, "w") as f:
            json.dump(ui_state.to_dict(), f, indent=2)
    except IOError:
        pass  # Silently fail if we can't save state
