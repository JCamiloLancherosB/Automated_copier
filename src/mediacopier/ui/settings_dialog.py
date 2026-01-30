"""Diálogo de configuración para MediaCopier."""

from __future__ import annotations

import os
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk


class SettingsDialog(ctk.CTkToplevel):
    """Diálogo modal para configurar las variables de conexión y rutas de contenido."""

    def __init__(self, parent: ctk.CTk, current_settings: dict) -> None:
        """Inicializa el diálogo de configuración.

        Args:
            parent: Ventana padre.
            current_settings: Configuración actual con claves:
                - api_url: URL del API de TechAura
                - api_key: API Key de TechAura
                - music_path: Ruta de música
                - videos_path: Ruta de videos
                - movies_path: Ruta de películas
        """
        super().__init__(parent)
        self.title("Configuración")
        self.geometry("600x500")
        self.transient(parent)
        self.grab_set()

        self._current_settings = current_settings
        self._result: Optional[dict] = None
        self._key_visible = False

        self._build_ui()
        self._load_current_values()

    def _build_ui(self) -> None:
        """Construye la interfaz del diálogo."""
        # TechAura API Section
        api_frame = ctk.CTkFrame(self)
        api_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(api_frame, text="🔗 TechAura API", font=("Arial", 14, "bold")).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        # URL
        url_frame = ctk.CTkFrame(api_frame, fg_color="transparent")
        url_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(url_frame, text="URL:", width=80).pack(side="left")
        self._url_entry = ctk.CTkEntry(url_frame, width=400)
        self._url_entry.pack(side="left", padx=10, fill="x", expand=True)

        # API Key
        key_frame = ctk.CTkFrame(api_frame, fg_color="transparent")
        key_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(key_frame, text="API Key:", width=80).pack(side="left")
        self._key_entry = ctk.CTkEntry(key_frame, width=350, show="*")
        self._key_entry.pack(side="left", padx=10, fill="x", expand=True)
        self._show_key_btn = ctk.CTkButton(
            key_frame, text="👁", width=40, command=self._toggle_key_visibility
        )
        self._show_key_btn.pack(side="left", padx=5)

        # Test connection button
        ctk.CTkButton(
            api_frame, text="🔌 Probar conexión", command=self._test_connection
        ).pack(pady=10)

        # Content Paths Section
        paths_frame = ctk.CTkFrame(self)
        paths_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            paths_frame, text="📁 Rutas de Contenido", font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))

        self._path_entries = {}
        for content_type, label in [
            ("music", "🎵 Música"),
            ("videos", "🎬 Videos"),
            ("movies", "🎥 Películas"),
        ]:
            self._create_path_entry(paths_frame, content_type, label)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=20)

        ctk.CTkButton(
            btn_frame, text="Cancelar", fg_color="gray", command=self.destroy
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="Restaurar valores por defecto", command=self._restore_defaults
        ).pack(side="left", padx=5, expand=True)
        ctk.CTkButton(
            btn_frame, text="Guardar", fg_color="#34a853", command=self._save
        ).pack(side="right", padx=5)

    def _create_path_entry(self, parent: ctk.CTkFrame, content_type: str, label: str) -> None:
        """Crea un campo de entrada para una ruta de contenido.

        Args:
            parent: Frame padre.
            content_type: Tipo de contenido (music, videos, movies).
            label: Etiqueta a mostrar.
        """
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=3)

        ctk.CTkLabel(frame, text=label, width=100).pack(side="left")
        entry = ctk.CTkEntry(frame, width=320)
        entry.pack(side="left", padx=5, fill="x", expand=True)

        ctk.CTkButton(frame, text="📂", width=40, command=lambda: self._browse_path(entry)).pack(
            side="left", padx=2
        )

        status_label = ctk.CTkLabel(frame, text="", width=30)
        status_label.pack(side="left", padx=5)

        self._path_entries[content_type] = (entry, status_label)
        entry.bind("<KeyRelease>", lambda e, ct=content_type: self._validate_path(ct))

    def _browse_path(self, entry: ctk.CTkEntry) -> None:
        """Abre un diálogo para seleccionar una ruta.

        Args:
            entry: Campo de entrada donde se insertará la ruta seleccionada.
        """
        path = filedialog.askdirectory()
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)
            # Trigger validation after setting the path
            entry.event_generate("<KeyRelease>")

    def _validate_path(self, content_type: str) -> None:
        """Valida si una ruta existe.

        Args:
            content_type: Tipo de contenido a validar.
        """
        entry, status = self._path_entries[content_type]
        path = entry.get()
        if path and os.path.isdir(path):
            status.configure(text="✓", text_color="#34a853")
        elif path:
            status.configure(text="✗", text_color="#ea4335")
        else:
            status.configure(text="")

    def _toggle_key_visibility(self) -> None:
        """Alterna la visibilidad de la API Key."""
        self._key_visible = not self._key_visible
        if self._key_visible:
            self._key_entry.configure(show="")
        else:
            self._key_entry.configure(show="*")

    def _test_connection(self) -> None:
        """Prueba la conexión con la API de TechAura."""
        # Import here to avoid circular dependencies
        from mediacopier.api.techaura_client import TechAuraClient

        api_url = self._url_entry.get()
        api_key = self._key_entry.get()

        if not api_url:
            self._show_message("Error", "Por favor ingrese una URL")
            return

        try:
            # Try to create a client and test the connection
            client = TechAuraClient(base_url=api_url, api_key=api_key)
            # Try to fetch orders as a connection test
            client.get_usb_orders()
            self._show_message("Éxito", "Conexión exitosa con TechAura API")
        except Exception as e:
            self._show_message("Error", f"Error al conectar: {str(e)}")

    def _show_message(self, title: str, message: str) -> None:
        """Muestra un mensaje en un diálogo modal.

        Args:
            title: Título del diálogo.
            message: Mensaje a mostrar.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("300x150")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=message, wraplength=250).pack(pady=20, padx=20)
        ctk.CTkButton(dialog, text="OK", command=dialog.destroy).pack(pady=10)

    def _restore_defaults(self) -> None:
        """Restaura los valores por defecto."""
        self._url_entry.delete(0, "end")
        self._url_entry.insert(0, "http://localhost:3006")

        self._key_entry.delete(0, "end")
        self._key_entry.insert(0, "")

        for content_type in ["music", "videos", "movies"]:
            entry, _ = self._path_entries[content_type]
            entry.delete(0, "end")
            if content_type == "music":
                entry.insert(0, "/content/music")
            elif content_type == "videos":
                entry.insert(0, "/content/videos")
            elif content_type == "movies":
                entry.insert(0, "/content/movies")
            self._validate_path(content_type)

    def _load_current_values(self) -> None:
        """Carga los valores actuales desde la configuración."""
        self._url_entry.insert(0, self._current_settings.get("api_url", ""))
        self._key_entry.insert(0, self._current_settings.get("api_key", ""))

        for content_type in ["music", "videos", "movies"]:
            entry, _ = self._path_entries[content_type]
            path_key = f"{content_type}_path"
            path = self._current_settings.get(path_key, "")
            if path:
                entry.insert(0, path)
            self._validate_path(content_type)

    def _save(self) -> None:
        """Guarda la configuración y cierra el diálogo."""
        self._result = {
            "api_url": self._url_entry.get(),
            "api_key": self._key_entry.get(),
            "music_path": self._path_entries["music"][0].get(),
            "videos_path": self._path_entries["videos"][0].get(),
            "movies_path": self._path_entries["movies"][0].get(),
        }
        self._save_to_env()
        self.destroy()

    def _save_to_env(self) -> None:
        """Guarda la configuración en el archivo .env."""
        # Get the project root directory (assuming .env should be in the repo root)
        project_root = Path(__file__).parent.parent.parent.parent
        env_file = project_root / ".env"

        # Read existing .env file if it exists
        env_vars = {}
        if env_file.exists():
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key] = value

        # Update with new values
        if self._result:
            env_vars["TECHAURA_API_URL"] = self._result["api_url"]
            env_vars["TECHAURA_API_KEY"] = self._result["api_key"]
            env_vars["CONTENT_MUSIC_PATH"] = self._result["music_path"]
            env_vars["CONTENT_VIDEOS_PATH"] = self._result["videos_path"]
            env_vars["CONTENT_MOVIES_PATH"] = self._result["movies_path"]

        # Write back to .env with restrictive permissions
        with open(env_file, "w") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")

        # Set restrictive permissions to protect sensitive data (owner read/write only)
        env_file.chmod(0o600)

    def get_result(self) -> Optional[dict]:
        """Retorna el resultado del diálogo.

        Returns:
            Diccionario con los valores guardados o None si se canceló.
        """
        return self._result
