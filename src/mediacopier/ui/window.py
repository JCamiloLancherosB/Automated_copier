"""Windowed UI for MediaCopier."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from mediacopier.api.techaura_client import CircuitBreakerOpen, TechAuraClient, USBOrder
from mediacopier.config.settings import load_ui_state, save_ui_state
from mediacopier.core.copier import CopyItemAction, CopyPlan, CopyPlanItem
from mediacopier.core.models import CopyRules, OrganizationMode, Profile, ProfileManager
from mediacopier.core.runner import (
    JobRunnerManager,
    RunnerEvent,
    RunnerEventType,
)
from mediacopier.core.usb_detector import (
    RemovableDrive,
    USBPermissionError,
    USBWriteError,
    detect_removable_drives,
    get_drive_display_name,
    get_usb_movies_folder_structure,
    get_usb_music_folder_structure,
    pre_create_folders,
    validate_usb_destination,
)
from mediacopier.integration.order_processor import (
    OrderProcessorConfig,
    TechAuraOrderProcessor,
)
from mediacopier.persistence import JobStorage, StatsStorage
from mediacopier.ui.components import StatusBar, Toast, Tooltip
from mediacopier.ui.dialogs import ConfirmationDialog
from mediacopier.ui.job_queue import JobQueue, JobStatus
from mediacopier.ui.styles import Colors, Emojis


class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    OK = "OK"


UI_POLL_INTERVAL_MS = 120
AUTO_REFRESH_INTERVAL_MS = 30000  # 30 seconds for auto-refresh

# Estimated time multipliers (in minutes) for recording time calculation
# These are rough estimates based on typical content transfer rates
ESTIMATED_TIME_PER_MUSIC_ITEM_MINUTES = 2  # Per genre or artist
ESTIMATED_TIME_PER_VIDEO_MINUTES = 5  # Per video file
ESTIMATED_TIME_PER_MOVIE_MINUTES = 10  # Per movie file

# Organization mode translations
ORGANIZATION_MODES = {
    "Carpeta única": OrganizationMode.SINGLE_FOLDER,
    "Por artista": OrganizationMode.SCATTER_BY_ARTIST,
    "Por género": OrganizationMode.SCATTER_BY_GENRE,
    "Por solicitud": OrganizationMode.FOLDER_PER_REQUEST,
    "Mantener estructura": OrganizationMode.KEEP_RELATIVE,
}

ORGANIZATION_MODES_REVERSE = {v: k for k, v in ORGANIZATION_MODES.items()}


class MediaCopierUI(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MediaCopier")
        
        # Load UI state and apply window geometry
        self._ui_state = load_ui_state()
        if self._ui_state.window_width and self._ui_state.window_height:
            self.geometry(f"{self._ui_state.window_width}x{self._ui_state.window_height}")
            if self._ui_state.window_x is not None and self._ui_state.window_y is not None:
                self.geometry(f"+{self._ui_state.window_x}+{self._ui_state.window_y}")
        else:
            self.geometry("1200x800")
        
        self.minsize(1100, 700)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self._job_queue = JobQueue()
        self._profile_manager = ProfileManager()
        self._runner_manager = JobRunnerManager()
        self._selected_job_id: str | None = None
        self._detected_usb_drives: list[RemovableDrive] = []
        self._ui_queue: list[Callable[[], None]] = []

        # Initialize persistence
        self._job_storage = JobStorage()
        self._stats_storage = StatsStorage(self._job_storage.storage_dir)

        # TechAura integration
        self._techaura_client: Optional[TechAuraClient] = None
        self._order_processor: Optional[TechAuraOrderProcessor] = None
        self._selected_order_id: Optional[str] = None
        self._techaura_orders: list[USBOrder] = []

        # Connection status and auto-refresh
        self._techaura_connected: bool = False
        self._auto_refresh_enabled: bool = self._ui_state.auto_refresh_enabled
        self._auto_refresh_after_id: Optional[str] = None
        self._previous_order_count: int = 0

        # Recording state for cancellation confirmation
        self._recording_in_progress: bool = False
        self._current_recording_job_id: Optional[str] = None
        self._recording_start_time: Optional[datetime] = None
        self._last_refresh_time: Optional[datetime] = None

        # UI components
        self._status_bar: Optional[StatusBar] = None

        # Log management
        self._log_entries: list[tuple[str, str, str]] = []  # (timestamp, level, message)
        self._log_filter_var: Optional[ctk.StringVar] = None
        self._max_log_entries: int = 1000

        self._build_layout()
        self._start_ui_queue()
        self._refresh_profiles()
        self._refresh_usb_drives()
        self._start_auto_refresh()
        self._restore_pending_jobs()
        self._start_autosave()
        self._log(LogLevel.INFO, "UI lista para crear jobs.")
        
        # Verificar conexión con TechAura después de 1 segundo
        self.after(1000, self._initial_connection_check)

    def _initial_connection_check(self) -> None:
        """Verificar conexión con TechAura al iniciar."""
        self._log(LogLevel.INFO, "Verificando conexión con TechAura...")
    
        if self._techaura_client is None:
            self._init_techaura_processor()
    
        if self._techaura_client is not None:
            try:
                connected = self._techaura_client.check_connection()
                self._update_connection_status(connected)
                if connected:
                    self._log(LogLevel.OK, "✅ Conexión con TechAura establecida")
                    self._on_refresh_techaura_orders()
                else:
                    self._log(LogLevel.WARN, "⚠️ No se pudo conectar con TechAura")
            except Exception as e:
                self._update_connection_status(False)
                self._log(LogLevel.ERROR, f"Error al verificar conexión: {str(e)}")
        else:
            self._update_connection_status(False)
            self._log(LogLevel.WARN, "⚠️ Cliente TechAura no configurado")

    def _restore_pending_jobs(self) -> None:
        """Restore pending jobs from disk."""
        try:
            jobs = self._job_storage.load_jobs()
            if jobs:
                restored_count = 0
                for job in jobs:
                    # Skip completed or error jobs
                    if job.status in (JobStatus.COMPLETED, JobStatus.ERROR):
                        continue
                    # Reset running jobs to pending
                    if job.status == JobStatus.RUNNING:
                        job.status = JobStatus.PENDING
                    # Add to queue
                    self._job_queue._jobs[job.id] = job
                    restored_count += 1
                
                if restored_count > 0:
                    self._log(
                        LogLevel.OK, 
                        f"✅ Restaurados {restored_count} job(s) pendiente(s) de sesión anterior"
                    )
                    self._refresh_queue_panel()
                else:
                    self._log(LogLevel.INFO, "No hay jobs pendientes para restaurar")
            else:
                self._log(LogLevel.DEBUG, "No se encontraron jobs guardados")
        except Exception as e:
            self._log(LogLevel.WARN, f"⚠️ Error al restaurar jobs: {e}")

    def _start_autosave(self) -> None:
        """Iniciar auto-guardado cada 60 segundos."""
        self._save_current_state()
        self.after(60000, self._start_autosave)

    def _save_current_state(self) -> None:
        """Guardar estado actual (jobs pendientes)."""
        try:
            # Only save jobs that are not completed or in error state
            pending_jobs = [
                job for job in self._job_queue.list_jobs()
                if job.status not in (JobStatus.COMPLETED, JobStatus.ERROR)
            ]
            if self._job_storage.save_jobs(pending_jobs):
                self._log(LogLevel.DEBUG, f"Auto-guardado: {len(pending_jobs)} job(s) pendiente(s)")
        except Exception as e:
            self._log(LogLevel.WARN, f"Error en auto-guardado: {e}")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1, uniform="cols")
        self.grid_columnconfigure(1, weight=1, uniform="cols")
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._left_panel = ctk.CTkScrollableFrame(self)
        self._left_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=12, pady=12)

        self._right_panel = ctk.CTkFrame(self)
        self._right_panel.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=12, pady=12)
        self._right_panel.grid_rowconfigure(1, weight=1)

        self._queue_panel = ctk.CTkFrame(self)
        self._queue_panel.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 6))
        self._queue_panel.grid_rowconfigure(1, weight=1)

        self._log_panel = ctk.CTkFrame(self)
        self._log_panel.grid(row=2, column=1, sticky="nsew", padx=12, pady=(0, 6))
        self._log_panel.grid_rowconfigure(1, weight=1)

        # TechAura orders panel
        self._techaura_panel = ctk.CTkFrame(self)
        self._techaura_panel.grid(
            row=3, column=0, columnspan=2, sticky="nsew", padx=12, pady=(0, 12)
        )
        self._techaura_panel.grid_rowconfigure(1, weight=1)
        self._techaura_panel.grid_columnconfigure(0, weight=1)
        self._techaura_panel.grid_columnconfigure(1, weight=1)

        self._build_left_panel()
        self._build_right_panel()
        self._build_queue_panel()
        self._build_log_panel()
        self._build_techaura_orders_panel()

        # Status bar at bottom
        self._status_bar = StatusBar(self)
        self._status_bar.grid(row=4, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

    def _build_left_panel(self) -> None:
        row = 0

        # Section: Configuration with Settings button
        config_header_frame = ctk.CTkFrame(self._left_panel, fg_color="transparent")
        config_header_frame.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 8)
        )
        config_header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(config_header_frame, text="Configuración", font=("Arial", 18, "bold")).pack(
            side="left", anchor="w"
        )
        ctk.CTkButton(
            config_header_frame, text="⚙️", width=40, command=self._open_settings_dialog
        ).pack(side="right")
        row += 1

        # Origin
        ctk.CTkLabel(self._left_panel, text="Origen").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=16
        )
        row += 1
        self._source_entry = ctk.CTkEntry(self._left_panel, placeholder_text="Ruta de origen")
        self._source_entry.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 12))
        row += 1

        # Destination
        ctk.CTkLabel(self._left_panel, text="Destino").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=16
        )
        row += 1
        self._destination_entry = ctk.CTkEntry(
            self._left_panel, placeholder_text="Ruta de destino"
        )
        self._destination_entry.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 8)
        )
        # Load last destination from saved state
        if self._ui_state.last_destination:
            self._destination_entry.insert(0, self._ui_state.last_destination)
        row += 1

        # USB Destination Dropdown
        ctk.CTkLabel(self._left_panel, text="Destino (USB detectadas)").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=16
        )
        row += 1

        usb_frame = ctk.CTkFrame(self._left_panel)
        usb_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 8))
        usb_frame.grid_columnconfigure(0, weight=1)
        row += 1

        self._usb_combo = ctk.CTkOptionMenu(
            usb_frame,
            values=["(Ninguna USB detectada)"],
            command=self._on_usb_selected,
        )
        self._usb_combo.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=4)

        ctk.CTkButton(
            usb_frame, text="Refrescar USB", width=100, command=self._on_refresh_usb
        ).grid(row=0, column=1, padx=2, pady=4)

        # Pre-create folders option
        self._pre_create_folders_var = ctk.BooleanVar(value=False)
        self._pre_create_folders_checkbox = ctk.CTkCheckBox(
            self._left_panel,
            text="Pre-crear carpetas antes de copiar",
            variable=self._pre_create_folders_var,
        )
        self._pre_create_folders_checkbox.grid(
            row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12)
        )
        row += 1

        # Organization Mode
        ctk.CTkLabel(self._left_panel, text="Modo de organización").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=16
        )
        row += 1
        self._mode_option = ctk.CTkOptionMenu(
            self._left_panel, values=list(ORGANIZATION_MODES.keys())
        )
        self._mode_option.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 12))
        row += 1

        # Section: Profiles
        ctk.CTkLabel(
            self._left_panel, text="Perfiles", font=("Arial", 16, "bold")
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 8))
        row += 1

        # Profile selector
        profile_frame = ctk.CTkFrame(self._left_panel)
        profile_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))
        profile_frame.grid_columnconfigure(0, weight=1)
        row += 1

        self._profile_combo = ctk.CTkOptionMenu(
            profile_frame, values=["(Ninguno)"], command=self._on_profile_selected
        )
        self._profile_combo.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=4)

        ctk.CTkButton(profile_frame, text="Cargar", width=70, command=self._on_load_profile).grid(
            row=0, column=1, padx=2, pady=4
        )
        ctk.CTkButton(
            profile_frame, text="Eliminar", width=70, command=self._on_delete_profile
        ).grid(row=0, column=2, padx=2, pady=4)

        # Save profile
        save_frame = ctk.CTkFrame(self._left_panel)
        save_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        save_frame.grid_columnconfigure(0, weight=1)
        row += 1

        self._profile_name_entry = ctk.CTkEntry(
            save_frame, placeholder_text="Nombre del perfil"
        )
        self._profile_name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=4)
        ctk.CTkButton(save_frame, text="Guardar perfil", command=self._on_save_profile).grid(
            row=0, column=1, padx=2, pady=4
        )

        # Section: Configurable Rules
        ctk.CTkLabel(
            self._left_panel, text="Reglas configurables", font=("Arial", 16, "bold")
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 8))
        row += 1

        # Checkboxes for rules
        self._rules_vars = {
            "filtrar_por_tamano": ctk.BooleanVar(value=False),
            "filtrar_por_duracion": ctk.BooleanVar(value=False),
            "solo_extensiones_seleccionadas": ctk.BooleanVar(value=False),
            "dry_run": ctk.BooleanVar(value=False),
            "evitar_duplicados": ctk.BooleanVar(value=True),
            "usar_fuzzy": ctk.BooleanVar(value=True),
        }

        checkbox_labels = {
            "filtrar_por_tamano": "Filtrar por tamaño mínimo",
            "filtrar_por_duracion": "Filtrar por duración mínima",
            "solo_extensiones_seleccionadas": "Solo extensiones seleccionadas",
            "dry_run": "Dry-run (simular sin copiar)",
            "evitar_duplicados": "Evitar duplicados",
            "usar_fuzzy": "Usar coincidencia fuzzy",
        }

        for key, label in checkbox_labels.items():
            checkbox = ctk.CTkCheckBox(
                self._left_panel, text=label, variable=self._rules_vars[key]
            )
            checkbox.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))
            row += 1

        # Numeric fields
        numeric_frame = ctk.CTkFrame(self._left_panel)
        numeric_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 8))
        row += 1

        ctk.CTkLabel(numeric_frame, text="Tamaño mín (MB):").grid(
            row=0, column=0, sticky="w", padx=(8, 4), pady=4
        )
        self._size_entry = ctk.CTkEntry(numeric_frame, width=80, placeholder_text="0")
        self._size_entry.grid(row=0, column=1, sticky="w", padx=(0, 16), pady=4)
        self._size_entry.insert(0, "0")

        ctk.CTkLabel(numeric_frame, text="Duración mín (min):").grid(
            row=0, column=2, sticky="w", padx=(8, 4), pady=4
        )
        self._duration_entry = ctk.CTkEntry(numeric_frame, width=80, placeholder_text="0")
        self._duration_entry.grid(row=0, column=3, sticky="w", padx=(0, 8), pady=4)
        self._duration_entry.insert(0, "0")

        # Fuzzy threshold slider
        ctk.CTkLabel(self._left_panel, text="Umbral de coincidencia fuzzy:").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 4)
        )
        row += 1

        slider_frame = ctk.CTkFrame(self._left_panel)
        slider_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))
        slider_frame.grid_columnconfigure(0, weight=1)
        row += 1

        self._fuzzy_threshold_var = ctk.DoubleVar(value=60.0)
        self._fuzzy_slider = ctk.CTkSlider(
            slider_frame,
            from_=0,
            to=100,
            variable=self._fuzzy_threshold_var,
            command=self._on_fuzzy_slider_change,
        )
        self._fuzzy_slider.grid(row=0, column=0, sticky="ew", padx=(8, 8), pady=4)

        self._fuzzy_label = ctk.CTkLabel(slider_frame, text="60%")
        self._fuzzy_label.grid(row=0, column=1, sticky="e", padx=(0, 8), pady=4)

        # Extensions field
        ctk.CTkLabel(self._left_panel, text="Extensiones permitidas (separadas por coma):").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 4)
        )
        row += 1
        self._extensions_entry = ctk.CTkEntry(
            self._left_panel, placeholder_text=".mp3, .flac, .wav, .mp4"
        )
        self._extensions_entry.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12)
        )
        row += 1

        # Section: Advanced Filtering Rules
        ctk.CTkLabel(
            self._left_panel, text="Reglas avanzadas", font=("Arial", 16, "bold")
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 8))
        row += 1

        # Solo mejor match checkbox
        self._rules_vars["solo_mejor_match"] = ctk.BooleanVar(value=False)
        solo_mejor_checkbox = ctk.CTkCheckBox(
            self._left_panel,
            text="Solo copiar el mejor match por solicitud",
            variable=self._rules_vars["solo_mejor_match"],
        )
        solo_mejor_checkbox.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))
        row += 1

        # Prefer high resolution checkbox (for movies)
        self._rules_vars["preferir_resolucion_alta"] = ctk.BooleanVar(value=True)
        res_checkbox = ctk.CTkCheckBox(
            self._left_panel,
            text="Preferir mayor resolución (películas)",
            variable=self._rules_vars["preferir_resolucion_alta"],
        )
        res_checkbox.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))
        row += 1

        # Exclusion words (multiline textbox)
        ctk.CTkLabel(
            self._left_panel,
            text="Palabras a excluir (una por línea):",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 4))
        row += 1

        self._exclusion_words_text = ctk.CTkTextbox(
            self._left_panel, height=80, wrap="word"
        )
        self._exclusion_words_text.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8)
        )
        # Default exclusion words
        default_exclusions = "sample\ntrailer\ncamrip\ncam\nts\ntelesync\nlow quality"
        self._exclusion_words_text.insert("1.0", default_exclusions)
        row += 1

        # Audio extensions whitelist
        ctk.CTkLabel(
            self._left_panel,
            text="Ext. audio permitidas (coma sep., vacío=todas):",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 4))
        row += 1
        self._audio_ext_whitelist_entry = ctk.CTkEntry(
            self._left_panel, placeholder_text=".mp3, .flac, .wav"
        )
        self._audio_ext_whitelist_entry.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 6)
        )
        row += 1

        # Video extensions whitelist
        ctk.CTkLabel(
            self._left_panel,
            text="Ext. video permitidas (coma sep., vacío=todas):",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 4))
        row += 1
        self._video_ext_whitelist_entry = ctk.CTkEntry(
            self._left_panel, placeholder_text=".mkv, .mp4"
        )
        self._video_ext_whitelist_entry.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 6)
        )
        row += 1

        # Preferred codecs (for movies)
        ctk.CTkLabel(
            self._left_panel,
            text="Codecs preferidos (coma sep., ej: h264, hevc):",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 4))
        row += 1
        self._codecs_entry = ctk.CTkEntry(
            self._left_panel, placeholder_text="h264, hevc, x265"
        )
        self._codecs_entry.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12)
        )
        row += 1

        # Error message label
        self._error_label = ctk.CTkLabel(
            self._left_panel, text="", text_color="#ea4335", wraplength=400
        )
        self._error_label.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 8))
        row += 1

        # Action buttons
        self._build_action_buttons(start_row=row)

    def _on_fuzzy_slider_change(self, value: float) -> None:
        self._fuzzy_label.configure(text=f"{int(value)}%")

    def _build_action_buttons(self, start_row: int) -> None:
        button_frame = ctk.CTkFrame(self._left_panel)
        button_frame.grid(
            row=start_row, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 16)
        )
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        buttons = [
            ("Agregar a cola", self._on_add_job),
            ("Ejecutar", self._on_run_job),
            ("Pausar", self._on_pause_job),
            ("Reanudar", self._on_resume_job),
            ("Detener", self._on_stop_job),
            ("Editar job", self._on_edit_job),
            ("Eliminar job", self._on_delete_job),
        ]

        row = 0
        col = 0
        for label, command in buttons:
            ctk.CTkButton(button_frame, text=label, command=command).grid(
                row=row, column=col, sticky="ew", padx=6, pady=6
            )
            col += 1
            if col == 2:
                col = 0
                row += 1

    def _build_right_panel(self) -> None:
        ctk.CTkLabel(
            self._right_panel,
            text="Lista de archivos (uno por línea)",
            font=("Arial", 18, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        self._names_text = ctk.CTkTextbox(self._right_panel, wrap="none")
        self._names_text.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

    def _build_queue_panel(self) -> None:
        ctk.CTkLabel(self._queue_panel, text="Cola de trabajos", font=("Arial", 18, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 8)
        )

        self._queue_table = ctk.CTkScrollableFrame(self._queue_panel)
        self._queue_table.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self._queue_table.grid_columnconfigure(0, weight=2)
        self._queue_table.grid_columnconfigure(1, weight=1)
        self._queue_table.grid_columnconfigure(2, weight=1)

        header_style = {"font": ("Arial", 13, "bold")}
        self._queue_header_widgets = [
            ctk.CTkLabel(self._queue_table, text="Job", **header_style),
            ctk.CTkLabel(self._queue_table, text="Estado", **header_style),
            ctk.CTkLabel(self._queue_table, text="Progreso", **header_style),
        ]
        for column, widget in enumerate(self._queue_header_widgets):
            widget.grid(row=0, column=column, sticky="w")

    def _build_log_panel(self) -> None:
        # Header with buttons
        header_frame = ctk.CTkFrame(self._log_panel, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(header_frame, text="Consola de logs", font=("Arial", 18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        
        ctk.CTkButton(
            header_frame, text="Copiar", width=80, command=self._on_copy_logs
        ).grid(row=0, column=1, padx=4)
        
        ctk.CTkButton(
            header_frame, text="Limpiar", width=80, command=self._on_clear_logs
        ).grid(row=0, column=2, padx=4)
        
        self._log_text = ctk.CTkTextbox(self._log_panel, wrap="word", height=160)
        self._log_text.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self._log_text.configure(state="disabled")
        self._log_text.tag_config("INFO", foreground=Colors.TEXT_SECONDARY)
        self._log_text.tag_config("WARN", foreground=Colors.WARNING)
        self._log_text.tag_config("ERROR", foreground=Colors.ERROR)
        self._log_text.tag_config("OK", foreground=Colors.SUCCESS)

    def _start_ui_queue(self) -> None:
        def poll() -> None:
            queue = list(self._ui_queue)
            self._ui_queue.clear()
            for callback in queue:
                callback()
            # Process runner events
            self._process_runner_events()
            self.after(UI_POLL_INTERVAL_MS, poll)

        self.after(UI_POLL_INTERVAL_MS, poll)

    def _process_runner_events(self) -> None:
        """Process events from the job runner."""
        events = self._runner_manager.get_events(timeout=0.0)
        for event in events:
            self._handle_runner_event(event)

    def _handle_runner_event(self, event: RunnerEvent) -> None:
        """Handle a single runner event."""
        if event.event_type == RunnerEventType.STATE_CHANGED:
            new_state = event.data.get("new_state", "")
            self._update_job_status_from_runner(event.job_id, new_state)

        elif event.event_type == RunnerEventType.PROGRESS:
            self._update_progress_display(event)

        elif event.event_type == RunnerEventType.FILE_STARTED:
            source = event.data.get("source", "")
            self._log(LogLevel.INFO, f"Copiando: {source}")

        elif event.event_type == RunnerEventType.FILE_COMPLETED:
            dest = event.data.get("destination", "")
            dry_run = event.data.get("dry_run", False)
            if dry_run:
                self._log(LogLevel.OK, f"[DRY-RUN] Copiado a: {dest}")
            else:
                self._log(LogLevel.OK, f"Copiado a: {dest}")

        elif event.event_type == RunnerEventType.FILE_SKIPPED:
            source = event.data.get("source", "")
            reason = event.data.get("reason", "")
            self._log(LogLevel.INFO, f"Omitido: {source} ({reason})")

        elif event.event_type == RunnerEventType.FILE_FAILED:
            source = event.data.get("source", "")
            error = event.data.get("error", "")
            self._log(LogLevel.ERROR, f"Error copiando {source}: {error}")

        elif event.event_type == RunnerEventType.JOB_COMPLETED:
            report = event.data.get("report", {})
            stopped = event.data.get("stopped", False)
            self._on_job_completed(event.job_id, report, stopped)

        elif event.event_type == RunnerEventType.JOB_FAILED:
            error = event.data.get("error", "")
            self._log(LogLevel.ERROR, f"Job falló: {error}")

    def _update_job_status_from_runner(self, job_id: str, runner_state: str) -> None:
        """Update job status based on runner state."""
        status_map = {
            "pending": JobStatus.PENDING,
            "running": JobStatus.RUNNING,
            "paused": JobStatus.PAUSED,
            "stop_requested": JobStatus.RUNNING,  # Still running during stop
            "done": JobStatus.COMPLETED,
            "failed": JobStatus.ERROR,
        }
        status = status_map.get(runner_state, JobStatus.PENDING)
        try:
            self._job_queue.update_status(job_id, status)
            self._refresh_jobs()
        except Exception:
            pass

    def _update_progress_display(self, event: RunnerEvent) -> None:
        """Update the progress display from runner event."""
        data = event.data
        job_id = event.job_id

        progress_percent = data.get("progress_percent", 0)
        current_index = data.get("current_index", 0)
        total_files = data.get("total_files", 0)
        eta_seconds = data.get("eta_seconds", 0)
        files_copied = data.get("files_copied", 0)
        files_skipped = data.get("files_skipped", 0)
        files_failed = data.get("files_failed", 0)

        # Update job progress in queue
        try:
            self._job_queue.update_progress(job_id, int(progress_percent))
            self._refresh_jobs()
        except Exception:
            pass

        # Format ETA
        if eta_seconds > 0:
            minutes = int(eta_seconds // 60)
            seconds = int(eta_seconds % 60)
            eta_str = f"{minutes}m {seconds}s"
        else:
            eta_str = "--"

        # Log progress periodically (every 10% or so)
        if current_index > 0 and current_index % max(1, total_files // 10) == 0:
            self._log(
                LogLevel.INFO,
                f"Progreso: {current_index}/{total_files} ({progress_percent:.1f}%) - "
                f"ETA: {eta_str} - Copiados: {files_copied}, "
                f"Omitidos: {files_skipped}, Errores: {files_failed}",
            )

    def _on_job_completed(
        self, job_id: str, report: dict, stopped: bool
    ) -> None:
        """Handle job completion."""
        copied = report.get("copied", 0)
        skipped = report.get("skipped", 0)
        failed = report.get("failed", 0)
        bytes_copied = report.get("bytes_copied", 0)

        # Format bytes
        if bytes_copied >= 1024 * 1024 * 1024:
            size_str = f"{bytes_copied / (1024 * 1024 * 1024):.2f} GB"
        elif bytes_copied >= 1024 * 1024:
            size_str = f"{bytes_copied / (1024 * 1024):.2f} MB"
        elif bytes_copied >= 1024:
            size_str = f"{bytes_copied / 1024:.2f} KB"
        else:
            size_str = f"{bytes_copied} bytes"

        if stopped:
            self._log(
                LogLevel.WARN,
                f"Job detenido - Copiados: {copied}, Omitidos: {skipped}, "
                f"Errores: {failed}, Tamaño: {size_str}",
            )
            Toast.show(self, f"{Emojis.WARNING} Grabación detenida", Toast.WARNING)
        else:
            self._log(
                LogLevel.OK,
                f"Job completado - Copiados: {copied}, Omitidos: {skipped}, "
                f"Errores: {failed}, Tamaño: {size_str}",
            )
            if failed > 0:
                Toast.show(
                    self, f"{Emojis.WARNING} Grabación completada con errores", Toast.WARNING
                )
            else:
                Toast.show(
                    self,
                    f"{Emojis.SUCCESS} Grabación completada exitosamente",
                    Toast.SUCCESS,
                )

    def enqueue_ui(self, callback: Callable[[], None]) -> None:
        self._ui_queue.append(callback)

    def _log(self, level: str, message: str) -> None:
        """Agregar mensaje al log con formato y color."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_entries.append((timestamp, level, message))
        
        # Enforce max entries limit to prevent memory leak
        if len(self._log_entries) > self._max_log_entries:
            self._log_entries = self._log_entries[-self._max_log_entries:]
        
        # Aplicar filtro actual
        if self._should_show_log(level):
            def append() -> None:
                self._append_log_entry(timestamp, level, message)
            self.enqueue_ui(append)

    def _append_log_entry(self, timestamp: str, level: str, message: str) -> None:
        """Agregar entrada formateada al widget de logs."""
        self._log_text.configure(state="normal")
        
        # Insertar timestamp
        self._log_text.insert("end", f"[{timestamp}] ", "TIMESTAMP")
        
        # Insertar nivel y mensaje con color
        self._log_text.insert("end", f"{level}: ", level)
        self._log_text.insert("end", f"{message}\n")
        
        self._log_text.configure(state="disabled")
        self._log_text.see("end")

    def _clear_logs(self) -> None:
        """Limpiar todos los logs."""
        self._log_entries.clear()
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def _copy_logs(self) -> None:
        """Copiar logs al portapapeles."""
        log_text = "\n".join([f"[{ts}] {lvl}: {msg}" for ts, lvl, msg in self._log_entries])
        self.clipboard_clear()
        self.clipboard_append(log_text)
        self._log(LogLevel.INFO, "Logs copiados al portapapeles")

    def _export_logs(self) -> None:
        """Exportar logs a archivo."""
        from tkinter import filedialog
        filepath = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt")],
            initialname=f"mediacopier_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                for ts, lvl, msg in self._log_entries:
                    f.write(f"[{ts}] {lvl}: {msg}\n")
            self._log(LogLevel.OK, f"Logs exportados a: {filepath}")

    def _on_filter_change(self, value: str) -> None:
        """Cambiar filtro de logs."""
        self._refresh_log_display()

    def _should_show_log(self, level: str) -> bool:
        """Verificar si el log debe mostrarse según el filtro."""
        if self._log_filter_var is None:
            return True
        filter_value = self._log_filter_var.get()
        if filter_value == "ALL":
            return True
        return level == filter_value

    def _refresh_log_display(self) -> None:
        """Refrescar display de logs según filtro."""
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        
        for ts, lvl, msg in self._log_entries:
            if self._should_show_log(lvl):
                self._append_log_entry(ts, lvl, msg)
        
        self._log_text.configure(state="disabled")

    def _on_clear_logs(self) -> None:
        """Clear the log panel."""
        def clear() -> None:
            self._log_text.configure(state="normal")
            self._log_text.delete("1.0", "end")
            self._log_text.configure(state="disabled")
        self.enqueue_ui(clear)

    def _on_copy_logs(self) -> None:
        """Copy logs to clipboard."""
        try:
            logs = self._log_text.get("1.0", "end")
            self.clipboard_clear()
            self.clipboard_append(logs)
            Toast.show(self, "Logs copiados al portapapeles", Toast.SUCCESS)
        except Exception as e:
            Toast.show(self, f"Error al copiar logs: {e}", Toast.ERROR)

    def _show_error(self, message: str) -> None:
        """Show an error message in the UI."""
        self._error_label.configure(text=message)
        self._log(LogLevel.ERROR, message)

    def _clear_error(self) -> None:
        """Clear the error message."""
        self._error_label.configure(text="")

    def _validate_numeric_input(self, value: str, field_name: str) -> float | None:
        """Validate numeric input and return float value or None if invalid."""
        if not value.strip():
            return 0.0
        try:
            num = float(value.strip())
            if num < 0:
                self._show_error(f"{field_name} no puede ser negativo")
                return None
            return num
        except ValueError:
            self._show_error(f"{field_name} debe ser un número válido")
            return None

    def _get_current_rules(self) -> CopyRules | None:
        """Get rules from current UI state with validation."""
        self._clear_error()

        # Validate size
        size = self._validate_numeric_input(self._size_entry.get(), "Tamaño mínimo")
        if size is None:
            return None

        # Validate duration
        duration = self._validate_numeric_input(self._duration_entry.get(), "Duración mínima")
        if duration is None:
            return None

        # Parse extensions - normalize to lowercase with leading dot
        extensions_text = self._extensions_entry.get().strip()
        extensions = []
        if extensions_text:
            for raw_ext in extensions_text.split(","):
                raw_ext = raw_ext.strip()
                if raw_ext:
                    ext = raw_ext if raw_ext.startswith(".") else f".{raw_ext}"
                    extensions.append(ext.lower())

        # Validate fuzzy threshold
        fuzzy_threshold = self._fuzzy_threshold_var.get()
        if fuzzy_threshold < 0 or fuzzy_threshold > 100:
            self._show_error("Umbral fuzzy debe estar entre 0 y 100")
            return None

        # Parse exclusion words from multiline textbox
        exclusion_text = self._exclusion_words_text.get("1.0", "end-1c").strip()
        excluir_palabras = []
        if exclusion_text:
            for line in exclusion_text.split("\n"):
                word = line.strip()
                if word:
                    excluir_palabras.append(word)

        # Parse audio extensions whitelist
        audio_ext_text = self._audio_ext_whitelist_entry.get().strip()
        audio_ext_whitelist = []
        if audio_ext_text:
            for raw_ext in audio_ext_text.split(","):
                raw_ext = raw_ext.strip()
                if raw_ext:
                    ext = raw_ext if raw_ext.startswith(".") else f".{raw_ext}"
                    audio_ext_whitelist.append(ext.lower())

        # Parse video extensions whitelist
        video_ext_text = self._video_ext_whitelist_entry.get().strip()
        video_ext_whitelist = []
        if video_ext_text:
            for raw_ext in video_ext_text.split(","):
                raw_ext = raw_ext.strip()
                if raw_ext:
                    ext = raw_ext if raw_ext.startswith(".") else f".{raw_ext}"
                    video_ext_whitelist.append(ext.lower())

        # Parse preferred codecs
        codecs_text = self._codecs_entry.get().strip()
        codecs_preferidos = []
        if codecs_text:
            for codec in codecs_text.split(","):
                codec = codec.strip()
                if codec:
                    codecs_preferidos.append(codec.lower())

        return CopyRules(
            extensiones_permitidas=extensions,
            tamano_min_mb=size,
            duracion_min_seg=duration * 60,  # Convert minutes to seconds
            filtrar_por_tamano=self._rules_vars["filtrar_por_tamano"].get(),
            filtrar_por_duracion=self._rules_vars["filtrar_por_duracion"].get(),
            solo_extensiones_seleccionadas=self._rules_vars["solo_extensiones_seleccionadas"].get(),
            dry_run=self._rules_vars["dry_run"].get(),
            evitar_duplicados=self._rules_vars["evitar_duplicados"].get(),
            usar_fuzzy=self._rules_vars["usar_fuzzy"].get(),
            umbral_fuzzy=fuzzy_threshold,
            excluir_palabras=excluir_palabras,
            extensiones_audio_permitidas=audio_ext_whitelist,
            extensiones_video_permitidas=video_ext_whitelist,
            solo_mejor_match=self._rules_vars["solo_mejor_match"].get(),
            preferir_resolucion_alta=self._rules_vars["preferir_resolucion_alta"].get(),
            codecs_preferidos=codecs_preferidos,
        )

    def _get_current_organization_mode(self) -> OrganizationMode:
        """Get organization mode from current UI state."""
        mode_text = self._mode_option.get()
        return ORGANIZATION_MODES.get(mode_text, OrganizationMode.SINGLE_FOLDER)

    def _apply_rules_to_ui(self, rules: CopyRules) -> None:
        """Apply rules to UI controls."""
        self._rules_vars["filtrar_por_tamano"].set(rules.filtrar_por_tamano)
        self._rules_vars["filtrar_por_duracion"].set(rules.filtrar_por_duracion)
        self._rules_vars["solo_extensiones_seleccionadas"].set(rules.solo_extensiones_seleccionadas)
        self._rules_vars["dry_run"].set(rules.dry_run)
        self._rules_vars["evitar_duplicados"].set(rules.evitar_duplicados)
        self._rules_vars["usar_fuzzy"].set(rules.usar_fuzzy)

        self._size_entry.delete(0, "end")
        self._size_entry.insert(0, str(rules.tamano_min_mb))

        self._duration_entry.delete(0, "end")
        # Convert seconds to minutes with rounding for clean display
        duration_minutes = round(rules.duracion_min_seg / 60, 2)
        self._duration_entry.insert(0, str(duration_minutes))

        self._fuzzy_threshold_var.set(rules.umbral_fuzzy)
        self._fuzzy_label.configure(text=f"{int(rules.umbral_fuzzy)}%")

        self._extensions_entry.delete(0, "end")
        if rules.extensiones_permitidas:
            self._extensions_entry.insert(0, ", ".join(rules.extensiones_permitidas))

        # Apply advanced rules to UI
        self._rules_vars["solo_mejor_match"].set(rules.solo_mejor_match)
        self._rules_vars["preferir_resolucion_alta"].set(rules.preferir_resolucion_alta)

        # Exclusion words
        self._exclusion_words_text.delete("1.0", "end")
        if rules.excluir_palabras:
            self._exclusion_words_text.insert("1.0", "\n".join(rules.excluir_palabras))

        # Audio extensions whitelist
        self._audio_ext_whitelist_entry.delete(0, "end")
        if rules.extensiones_audio_permitidas:
            self._audio_ext_whitelist_entry.insert(
                0, ", ".join(rules.extensiones_audio_permitidas)
            )

        # Video extensions whitelist
        self._video_ext_whitelist_entry.delete(0, "end")
        if rules.extensiones_video_permitidas:
            self._video_ext_whitelist_entry.insert(
                0, ", ".join(rules.extensiones_video_permitidas)
            )

        # Preferred codecs
        self._codecs_entry.delete(0, "end")
        if rules.codecs_preferidos:
            self._codecs_entry.insert(0, ", ".join(rules.codecs_preferidos))

    def _apply_organization_mode_to_ui(self, mode: OrganizationMode) -> None:
        """Apply organization mode to UI."""
        mode_text = ORGANIZATION_MODES_REVERSE.get(mode, "Carpeta única")
        self._mode_option.set(mode_text)

    # Profile management
    def _refresh_profiles(self) -> None:
        """Refresh the profiles dropdown."""
        profiles = self._profile_manager.list_profiles()
        values = ["(Ninguno)"] + profiles
        self._profile_combo.configure(values=values)

    def _on_profile_selected(self, selection: str) -> None:
        """Handle profile selection from dropdown."""
        if selection == "(Ninguno)":
            return
        self._on_load_profile()

    def _on_load_profile(self) -> None:
        """Load selected profile."""
        profile_name = self._profile_combo.get()
        if profile_name == "(Ninguno)":
            self._log(LogLevel.WARN, "Selecciona un perfil primero.")
            return

        profile = self._profile_manager.load_profile(profile_name)
        if profile:
            self._apply_rules_to_ui(profile.reglas)
            self._apply_organization_mode_to_ui(profile.modo_organizacion)
            self._profile_name_entry.delete(0, "end")
            self._profile_name_entry.insert(0, profile.nombre)
            self._log(LogLevel.OK, f"Perfil cargado: {profile.nombre}")
        else:
            self._log(LogLevel.ERROR, f"No se pudo cargar el perfil: {profile_name}")

    def _on_save_profile(self) -> None:
        """Save current settings as a profile."""
        self._clear_error()

        profile_name = self._profile_name_entry.get().strip()
        if not profile_name:
            self._show_error("Ingresa un nombre para el perfil")
            return

        rules = self._get_current_rules()
        if rules is None:
            return

        mode = self._get_current_organization_mode()

        profile = Profile(nombre=profile_name, reglas=rules, modo_organizacion=mode)

        try:
            self._profile_manager.save_profile(profile)
            self._refresh_profiles()
            self._profile_combo.set(profile_name)
            self._log(LogLevel.OK, f"Perfil guardado: {profile_name}")
        except Exception as e:
            self._show_error(f"Error al guardar perfil: {e}")

    def _on_delete_profile(self) -> None:
        """Delete selected profile."""
        profile_name = self._profile_combo.get()
        if profile_name == "(Ninguno)":
            self._log(LogLevel.WARN, "Selecciona un perfil primero.")
            return

        if self._profile_manager.delete_profile(profile_name):
            self._refresh_profiles()
            self._profile_combo.set("(Ninguno)")
            self._log(LogLevel.OK, f"Perfil eliminado: {profile_name}")
        else:
            self._log(LogLevel.ERROR, f"No se pudo eliminar el perfil: {profile_name}")

    # USB drive management
    def _refresh_usb_drives(self) -> None:
        """Refresh the list of detected USB drives."""
        self._detected_usb_drives = detect_removable_drives()

        if self._detected_usb_drives:
            values = [get_drive_display_name(drive) for drive in self._detected_usb_drives]
            self._usb_combo.configure(values=values)
            # Select first available drive
            self._usb_combo.set(values[0])
            self._log(
                LogLevel.INFO,
                f"Detectadas {len(self._detected_usb_drives)} unidades USB",
            )
        else:
            self._usb_combo.configure(values=["(Ninguna USB detectada)"])
            self._usb_combo.set("(Ninguna USB detectada)")
        
        # Update status bar
        if self._status_bar:
            self._status_bar.update_usb_count(len(self._detected_usb_drives))

    def _on_refresh_usb(self) -> None:
        """Handle USB refresh button click."""
        self._refresh_usb_drives()
        if not self._detected_usb_drives:
            self._log(LogLevel.WARN, "No se detectaron unidades USB conectadas.")
        else:
            Toast.show(
                self,
                f"{Emojis.USB} {len(self._detected_usb_drives)} USB detectadas",
                Toast.INFO,
            )

    def _on_usb_selected(self, selection: str) -> None:
        """Handle USB drive selection from dropdown."""
        if selection == "(Ninguna USB detectada)":
            return

        # Find the selected drive
        for drive in self._detected_usb_drives:
            if get_drive_display_name(drive) == selection:
                # Update destination entry with drive path
                self._destination_entry.delete(0, "end")
                self._destination_entry.insert(0, drive.path)

                if not drive.is_writable:
                    self._show_error(f"La unidad {drive.label} es de solo lectura")
                else:
                    self._clear_error()
                    self._log(LogLevel.OK, f"USB seleccionada: {drive.label}")
                break

    def _open_settings_dialog(self) -> None:
        """Open the settings configuration dialog."""
        from mediacopier.config.settings import get_settings

        # Get current settings
        settings = get_settings()
        current_settings = {
            "api_url": settings.techaura.api_url,
            "api_key": settings.techaura.api_key,
            "music_path": str(settings.content_paths.music_path),
            "videos_path": str(settings.content_paths.videos_path),
            "movies_path": str(settings.content_paths.movies_path),
        }

        # Open dialog
        dialog = SettingsDialog(self, current_settings)
        self.wait_window(dialog)

        # Apply changes if saved
        result = dialog.get_result()
        if result:
            self._apply_settings(result)

    def _apply_settings(self, settings: dict) -> None:
        """Apply settings changes to the application.

        Args:
            settings: Dictionary with new settings values.
        """
        # Update environment variables for immediate effect
        import os

        os.environ["TECHAURA_API_URL"] = settings["api_url"]
        os.environ["TECHAURA_API_KEY"] = settings["api_key"]
        os.environ["CONTENT_MUSIC_PATH"] = settings["music_path"]
        os.environ["CONTENT_VIDEOS_PATH"] = settings["videos_path"]
        os.environ["CONTENT_MOVIES_PATH"] = settings["movies_path"]

        # Reinitialize TechAura client if connected
        if self._techaura_client or self._order_processor:
            try:
                content_sources = {
                    "music": settings["music_path"],
                    "videos": settings["videos_path"],
                    "movies": settings["movies_path"],
                }
                self.setup_techaura_integration(
                    content_sources, settings["api_url"], settings["api_key"]
                )
                self._log(LogLevel.OK, "Configuración aplicada exitosamente")
            except Exception as e:
                self._log(LogLevel.ERROR, f"Error al aplicar configuración: {str(e)}")
        else:
            self._log(LogLevel.OK, "Configuración guardada exitosamente")

    def _get_selected_usb_drive(self) -> RemovableDrive | None:
        """Get the currently selected USB drive."""
        selection = self._usb_combo.get()
        if selection == "(Ninguna USB detectada)":
            return None

        for drive in self._detected_usb_drives:
            if get_drive_display_name(drive) == selection:
                return drive
        return None

    def _pre_create_usb_folders(self, dest_path: str) -> bool:
        """Pre-create folder structure based on organization mode.

        Args:
            dest_path: Destination path.

        Returns:
            True if successful, False otherwise.
        """
        if not self._pre_create_folders_var.get():
            return True

        is_valid, error = validate_usb_destination(dest_path)
        if not is_valid:
            self._show_error(error)
            return False

        mode = self._get_current_organization_mode()
        folders: list[str] = []

        if mode == OrganizationMode.SCATTER_BY_GENRE:
            # USB Music template: Music/Genre/Artist
            folders = get_usb_music_folder_structure()
        elif mode == OrganizationMode.FOLDER_PER_REQUEST:
            # USB Movies template: Movies/
            folders = get_usb_movies_folder_structure()
        elif mode == OrganizationMode.SCATTER_BY_ARTIST:
            # Simple Music folder
            folders = ["Music"]
        else:
            # Other modes: no pre-creation needed
            return True

        try:
            success, error = pre_create_folders(dest_path, folders)
            if not success:
                self._show_error(error)
                return False
            self._log(LogLevel.OK, f"Carpetas pre-creadas en: {dest_path}")
            return True
        except USBPermissionError as e:
            self._show_error(f"Error de permisos: {e}")
            return False
        except USBWriteError as e:
            self._show_error(f"Error de escritura: {e}")
            return False

    def _read_items(self) -> list[str]:
        content = self._names_text.get("1.0", "end").strip()
        if not content:
            return []
        return [line.strip() for line in content.splitlines() if line.strip()]

    def _refresh_jobs(self) -> None:
        header_count = len(self._queue_header_widgets)
        for widget in self._queue_table.winfo_children()[header_count:]:
            widget.destroy()

        for row_index, job in enumerate(self._job_queue.list_jobs(), start=1):
            row_widgets = []
            name_label = ctk.CTkLabel(
                self._queue_table,
                text=job.name,
                anchor="w",
            )
            name_label.grid(row=row_index, column=0, sticky="ew", padx=(0, 8), pady=4)
            row_widgets.append(name_label)

            status_label = ctk.CTkLabel(self._queue_table, text=job.status.value)
            status_label.grid(row=row_index, column=1, sticky="w", padx=(0, 8), pady=4)
            row_widgets.append(status_label)

            progress_label = ctk.CTkLabel(self._queue_table, text=f"{job.progress}%")
            progress_label.grid(row=row_index, column=2, sticky="w", pady=4)
            row_widgets.append(progress_label)

            for widget in row_widgets:
                widget.bind("<Button-1>", lambda _event, job_id=job.id: self._select_job(job_id))

        self._queue_table.update_idletasks()

    def _select_job(self, job_id: str) -> None:
        self._selected_job_id = job_id
        job = self._job_queue.get_job(job_id)
        self._log(LogLevel.INFO, f"Job seleccionado: {job.name}")

    def _on_add_job(self) -> None:
        """Add a new job with current rules snapshot."""
        rules = self._get_current_rules()
        if rules is None:
            return

        items = self._read_items()
        mode = self._get_current_organization_mode()

        job_name = f"Job {len(self._job_queue.list_jobs()) + 1}"
        job = self._job_queue.add_job(job_name, items, rules=rules, organization_mode=mode)
        self._selected_job_id = job.id
        self._refresh_jobs()
        self._log(LogLevel.OK, f"Agregado {job.name} con {len(items)} elementos.")

    def _require_selected_job(self) -> str | None:
        if not self._selected_job_id:
            self._log(LogLevel.WARN, "Selecciona un job primero.")
            return None
        return self._selected_job_id

    def _create_copy_plan_for_job(self, job_id: str) -> CopyPlan | None:
        """Create a copy plan for a job based on its items.

        This is a simplified version that creates plan items from the job's item list.
        In a full implementation, this would use the indexer and matcher.
        """
        try:
            job = self._job_queue.get_job(job_id)
        except Exception:
            return None

        # Get source and destination from UI
        source = self._source_entry.get().strip()
        dest = self._destination_entry.get().strip()

        if not source or not dest:
            self._show_error("Especifica origen y destino")
            return None

        # For now, create a simple plan with the items as file paths
        # In a real implementation, this would use the matcher to find files
        items = []
        total_bytes = 0

        for item_text in job.items:
            # Check if item_text is a file path
            item_path = Path(item_text)
            if item_path.exists() and item_path.is_file():
                size = item_path.stat().st_size
                dest_path = Path(dest) / item_path.name
                items.append(
                    CopyPlanItem(
                        source=str(item_path),
                        destination=str(dest_path),
                        action=CopyItemAction.COPY,
                        size=size,
                    )
                )
                total_bytes += size

        plan = CopyPlan(
            items=items,
            total_bytes=total_bytes,
            files_to_copy=len(items),
            files_to_skip=0,
        )

        return plan

    def _on_run_job(self) -> None:
        """Start executing the selected job."""
        job_id = self._require_selected_job()
        if not job_id:
            return

        try:
            job = self._job_queue.get_job(job_id)
        except Exception:
            self._log(LogLevel.ERROR, "Job no encontrado.")
            return

        # Check if can run
        if not self._runner_manager.can_edit_job(job_id):
            self._log(LogLevel.WARN, "No se puede ejecutar este job ahora.")
            return

        # Pre-create folders if option is enabled
        dest = self._destination_entry.get().strip()
        if dest and not self._pre_create_usb_folders(dest):
            return

        # Create copy plan
        plan = self._create_copy_plan_for_job(job_id)
        if plan is None:
            return

        if len(plan.items) == 0:
            self._log(
                LogLevel.WARN,
                "No hay archivos para copiar. Agrega rutas de archivo válidas.",
            )
            return

        # Register and start the job
        dry_run = job.rules_snapshot.dry_run
        self._runner_manager.register_job(job_id, plan, dry_run=dry_run)

        if self._runner_manager.start_job(job_id):
            self._job_queue.update_status(job_id, JobStatus.RUNNING)
            self._refresh_jobs()
            size_mb = plan.total_bytes / (1024 * 1024) if plan.total_bytes > 0 else 0.0
            self._log(
                LogLevel.OK,
                f"Ejecutando {job.name} ({len(plan.items)} archivos, "
                f"{size_mb:.2f} MB)"
                + (" [DRY-RUN]" if dry_run else ""),
            )
            Toast.show(self, f"{Emojis.PLAY} Grabación iniciada", Toast.INFO)
        else:
            self._log(LogLevel.ERROR, "No se pudo iniciar el job.")
            Toast.show(self, f"{Emojis.ERROR} Error al iniciar grabación", Toast.ERROR)

    def _on_pause_job(self) -> None:
        """Pause the currently running job."""
        if self._runner_manager.pause_job():
            self._log(LogLevel.WARN, "Job pausado.")
        else:
            self._log(LogLevel.WARN, "No hay job en ejecución para pausar.")

    def _on_resume_job(self) -> None:
        """Resume the paused job."""
        if self._runner_manager.resume_job():
            self._log(LogLevel.OK, "Job reanudado.")
        else:
            self._log(LogLevel.WARN, "No hay job pausado para reanudar.")

    def _on_stop_job(self) -> None:
        """Stop the currently running job."""
        if self._runner_manager.stop_job():
            self._log(LogLevel.WARN, "Deteniendo job...")
        else:
            self._log(LogLevel.WARN, "No hay job en ejecución para detener.")

    def _on_edit_job(self) -> None:
        """Edit the selected job."""
        job_id = self._require_selected_job()
        if not job_id:
            return

        # Check if can edit
        if not self._runner_manager.can_edit_job(job_id):
            self._log(
                LogLevel.WARN,
                "No se puede editar un job en ejecución. Detén el job primero.",
            )
            return

        try:
            job = self._job_queue.get_job(job_id)
        except Exception:
            self._log(LogLevel.ERROR, "Job no encontrado.")
            return

        # Load job items into the text area for editing
        self._names_text.delete("1.0", "end")
        self._names_text.insert("1.0", "\n".join(job.items))

        # Apply job rules to UI
        self._apply_rules_to_ui(job.rules_snapshot)
        self._apply_organization_mode_to_ui(job.organization_mode)

        # Mark job as being edited
        new_name = f"{job.name} (editando)"
        job.name = new_name
        self._refresh_jobs()
        self._log(LogLevel.OK, f"Editando {job.name}.")

    def _on_delete_job(self) -> None:
        """Delete the selected job."""
        job_id = self._require_selected_job()
        if not job_id:
            return

        # Check if can delete
        if not self._runner_manager.can_edit_job(job_id):
            self._log(
                LogLevel.WARN,
                "No se puede eliminar un job en ejecución. Detén el job primero.",
            )
            return

        try:
            job = self._job_queue.remove_job(job_id)
            self._runner_manager.unregister_job(job_id)
            self._selected_job_id = None
            self._refresh_jobs()
            self._log(LogLevel.WARN, f"Job eliminado: {job.name}.")
        except Exception:
            self._log(LogLevel.ERROR, "No se pudo eliminar el job.")

    # ========== TechAura Integration Methods ==========

    def _build_techaura_orders_panel(self) -> None:
        """Panel para mostrar y gestionar pedidos de TechAura."""
        # Header
        header_frame = ctk.CTkFrame(self._techaura_panel)
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 8))
        header_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            header_frame, text="Pedidos TechAura", font=("Arial", 18, "bold")
        ).grid(row=0, column=0, sticky="w", padx=(0, 16))

        # Connection status indicator with tooltip
        self._connection_status_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self._connection_status_frame.grid(row=0, column=1, sticky="w", padx=8)

        self._connection_indicator = ctk.CTkLabel(
            self._connection_status_frame,
            text="●",
            font=("Arial", 16),
            text_color=Colors.DISCONNECTED,
        )
        self._connection_indicator.grid(row=0, column=0, padx=(0, 4))

        self._connection_status_label = ctk.CTkLabel(
            self._connection_status_frame,
            text="Desconectado",
            font=("Arial", 12),
            text_color=Colors.DISCONNECTED,
        )
        self._connection_status_label.grid(row=0, column=1)
        
        # Add tooltip to connection status
        Tooltip(self._connection_status_frame, "Estado de conexión a TechAura API")

        # Auto-refresh checkbox
        self._auto_refresh_var = ctk.BooleanVar(value=self._auto_refresh_enabled)
        self._auto_refresh_checkbox = ctk.CTkCheckBox(
            header_frame,
            text="Auto-refresh (30s)",
            variable=self._auto_refresh_var,
            command=self._on_toggle_auto_refresh,
        )
        self._auto_refresh_checkbox.grid(row=0, column=2, sticky="e", padx=(8, 4))

        # Refresh button
        ctk.CTkButton(
            header_frame,
            text="Actualizar pedidos",
            width=150,
            command=self._on_refresh_techaura_orders,
        ).grid(row=0, column=3, sticky="e", padx=4)

        # Reconnect button
        self._reconnect_btn = ctk.CTkButton(
            header_frame,
            text="🔄 Reconectar",
            width=100,
            fg_color="#666666",
            command=self._on_reconnect,
        )
        self._reconnect_btn.grid(row=0, column=4, sticky="e", padx=4)

        # Orders list frame (left side)
        orders_list_frame = ctk.CTkFrame(self._techaura_panel)
        orders_list_frame.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 12))
        orders_list_frame.grid_rowconfigure(1, weight=1)
        orders_list_frame.grid_columnconfigure(0, weight=1)

        # Pending orders label (will update with count)
        self._pending_orders_label = ctk.CTkLabel(
            orders_list_frame, text="Pedidos pendientes:", font=("Arial", 14)
        )
        self._pending_orders_label.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        self._techaura_orders_table = ctk.CTkScrollableFrame(orders_list_frame, height=120)
        self._techaura_orders_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._techaura_orders_table.grid_columnconfigure(0, weight=2)
        self._techaura_orders_table.grid_columnconfigure(1, weight=1)
        self._techaura_orders_table.grid_columnconfigure(2, weight=1)
        self._techaura_orders_table.grid_columnconfigure(3, weight=1)

        # Table headers
        table_header_style = {"font": ("Arial", 12, "bold")}
        ctk.CTkLabel(self._techaura_orders_table, text="Pedido", **table_header_style).grid(
            row=0, column=0, sticky="w", padx=4
        )
        ctk.CTkLabel(self._techaura_orders_table, text="Cliente", **table_header_style).grid(
            row=0, column=1, sticky="w", padx=4
        )
        ctk.CTkLabel(self._techaura_orders_table, text="Tipo", **table_header_style).grid(
            row=0, column=2, sticky="w", padx=4
        )
        ctk.CTkLabel(self._techaura_orders_table, text="USB (GB)", **table_header_style).grid(
            row=0, column=3, sticky="w", padx=4
        )

        # Order details frame (right side)
        details_frame = ctk.CTkFrame(self._techaura_panel)
        details_frame.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 12))
        details_frame.grid_rowconfigure(1, weight=1)
        details_frame.grid_columnconfigure(0, weight=1)

        # Details header with estimated time
        details_header_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
        details_header_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        details_header_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(details_header_frame, text="Detalles del pedido:", font=("Arial", 14)).grid(
            row=0, column=0, sticky="w"
        )

        self._estimated_time_label = ctk.CTkLabel(
            details_header_frame,
            text="",
            font=("Arial", 11),
            text_color="#9aa0a6",
        )
        self._estimated_time_label.grid(row=0, column=1, sticky="e")

        self._techaura_details_text = ctk.CTkTextbox(details_frame, wrap="word", height=100)
        self._techaura_details_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
        self._techaura_details_text.configure(state="disabled")

        # Action buttons for orders
        buttons_frame = ctk.CTkFrame(details_frame)
        buttons_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        buttons_frame.grid_columnconfigure(0, weight=1)
        buttons_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            buttons_frame,
            text="Ver detalles",
            command=self._on_view_order_details,
        ).grid(row=0, column=0, sticky="ew", padx=4, pady=4)

        ctk.CTkButton(
            buttons_frame,
            text="Confirmar y grabar",
            fg_color="#34a853",
            hover_color="#2d9148",
            command=self._on_confirm_and_burn_order,
        ).grid(row=0, column=1, sticky="ew", padx=4, pady=4)

    def _start_auto_refresh(self) -> None:
        """Start auto-refresh timer for TechAura orders."""
        if self._auto_refresh_enabled and self._auto_refresh_after_id is None:
            self._auto_refresh_after_id = self.after(
                AUTO_REFRESH_INTERVAL_MS, self._auto_refresh_tick
            )

    def _stop_auto_refresh(self) -> None:
        """Stop auto-refresh timer."""
        if self._auto_refresh_after_id is not None:
            self.after_cancel(self._auto_refresh_after_id)
            self._auto_refresh_after_id = None

    def _auto_refresh_tick(self) -> None:
        """Auto-refresh timer tick."""
        self._auto_refresh_after_id = None

        if self._auto_refresh_enabled:
            self._on_refresh_techaura_orders()
            # Schedule next refresh
            self._auto_refresh_after_id = self.after(
                AUTO_REFRESH_INTERVAL_MS, self._auto_refresh_tick
            )

    def _on_toggle_auto_refresh(self) -> None:
        """Toggle auto-refresh setting."""
        self._auto_refresh_enabled = self._auto_refresh_var.get()
        if self._auto_refresh_enabled:
            self._start_auto_refresh()
            self._log(LogLevel.INFO, "Auto-refresh activado (cada 30 segundos)")
        else:
            self._stop_auto_refresh()
            self._log(LogLevel.INFO, "Auto-refresh desactivado")

    def _update_connection_status(self, connected: bool, reconnecting: bool = False) -> None:
        """Update the TechAura connection status indicator."""
        self._techaura_connected = connected
        if connected:
            self._connection_indicator.configure(text_color=Colors.CONNECTED)
            self._connection_status_label.configure(
                text="Conectado", text_color=Colors.CONNECTED
            )
            if self._status_bar and hasattr(self._status_bar, 'update_connection'):
                self._status_bar.update_connection(True)
        elif reconnecting:
            self._connection_indicator.configure(text_color=Colors.WARNING)
            self._connection_status_label.configure(
                text="Reconectando...", text_color=Colors.WARNING
            )
            if self._status_bar and hasattr(self._status_bar, 'update_connection'):
                self._status_bar.update_connection(False)
        else:
            self._connection_indicator.configure(text_color=Colors.DISCONNECTED)
            self._connection_status_label.configure(
                text="Desconectado", text_color=Colors.DISCONNECTED
            )
            if self._status_bar and hasattr(self._status_bar, 'update_connection'):
                self._status_bar.update_connection(False)

    def _check_and_notify_new_orders(self, new_order_count: int) -> None:
        """Check if there are new orders and show notification."""
        if new_order_count > self._previous_order_count and self._previous_order_count > 0:
            new_count = new_order_count - self._previous_order_count
            self._show_new_order_notification(new_count)
        self._previous_order_count = new_order_count

    def _show_new_order_notification(self, count: int) -> None:
        """Show notification for new orders."""
        message = f"¡{count} nuevo{'s' if count > 1 else ''} pedido{'s' if count > 1 else ''}!"
        self._log(LogLevel.OK, message)
        Toast.show(self, f"{Emojis.ORDER} {message}", Toast.SUCCESS)

    def _calculate_estimated_time(self, order: USBOrder) -> int:
        """Calculate estimated recording time in minutes.
        
        Args:
            order: The USB order to calculate time for.
            
        Returns:
            Estimated time in minutes.
        """
        estimated_minutes = 0
        if order.product_type == "music":
            estimated_minutes = (
                (len(order.genres) + len(order.artists))
                * ESTIMATED_TIME_PER_MUSIC_ITEM_MINUTES
            )
        elif order.product_type == "videos":
            estimated_minutes = len(order.videos) * ESTIMATED_TIME_PER_VIDEO_MINUTES
        elif order.product_type == "movies":
            estimated_minutes = len(order.movies) * ESTIMATED_TIME_PER_MOVIE_MINUTES
        return estimated_minutes

    def _update_estimated_time(self, order: Optional[USBOrder] = None) -> None:
        """Update the estimated recording time display."""
        if order is None or not hasattr(self, "_estimated_time_label"):
            return

        estimated_minutes = self._calculate_estimated_time(order)

        if estimated_minutes > 0:
            if estimated_minutes >= 60:
                hours = estimated_minutes // 60
                mins = estimated_minutes % 60
                time_str = f"~{hours}h {mins}m"
            else:
                time_str = f"~{estimated_minutes}m"
            self._estimated_time_label.configure(text=f"Tiempo estimado: {time_str}")
        else:
            self._estimated_time_label.configure(text="")

    def _show_cancel_confirmation(self) -> bool:
        """Show confirmation dialog before canceling in-progress recording.

        Returns:
            True if user confirms cancellation, False otherwise.
        """
        if not self._recording_in_progress:
            return True

        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirmar Cancelación")
        dialog.geometry("400x200")
        dialog.transient(self)
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"confirmed": False}

        ctk.CTkLabel(
            dialog,
            text="⚠️ Grabación en progreso",
            font=("Arial", 16, "bold"),
            text_color="#fbbc05",
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            dialog,
            text="¿Estás seguro de que deseas cancelar la grabación actual?\n"
            "El progreso actual se perderá.",
            font=("Arial", 12),
            wraplength=350,
        ).pack(pady=10)

        buttons_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons_frame.pack(pady=20)

        def on_cancel() -> None:
            result["confirmed"] = False
            dialog.destroy()

        def on_confirm() -> None:
            result["confirmed"] = True
            dialog.destroy()

        ctk.CTkButton(
            buttons_frame,
            text="No, continuar",
            fg_color="#34a853",
            hover_color="#2d9148",
            command=on_cancel,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            buttons_frame,
            text="Sí, cancelar",
            fg_color="#ea4335",
            hover_color="#c5221f",
            command=on_confirm,
        ).pack(side="left", padx=10)

        dialog.wait_window()
        return result["confirmed"]

    def _on_reconnect(self) -> None:
        """Intentar reconectar con TechAura."""
        self._log(LogLevel.INFO, "Intentando reconectar...")
        
        # Reiniciar el cliente
        self._techaura_client = None
        self._order_processor = None
        
        # Reintentar conexión
        self._initial_connection_check()

    def _on_refresh_techaura_orders(self) -> None:
        """Actualizar lista de pedidos de TechAura."""
        if self._order_processor is None:
            # Initialize order processor if not already done
            self._init_techaura_processor()

        if self._order_processor is None:
            self._log(LogLevel.WARN, "No se pudo inicializar el procesador TechAura.")
            self._update_connection_status(False)
            return

        # Verificar conexión antes de intentar obtener pedidos
        if self._techaura_client and not self._techaura_client.check_connection():
            self._update_connection_status(False)
            self._log(LogLevel.WARN, "No se puede conectar con el servidor TechAura.")
            return

        try:
            self._techaura_orders = self._order_processor.fetch_pending_orders()

            # Also add any locally pending orders
            for order_id, pending in self._order_processor.pending_orders.items():
                if pending.order not in self._techaura_orders:
                    self._techaura_orders.append(pending.order)

            self._refresh_techaura_orders_list()
            self._update_connection_status(True)
            self._check_and_notify_new_orders(len(self._techaura_orders))
            self._log(
                LogLevel.INFO, f"Se encontraron {len(self._techaura_orders)} pedidos pendientes."
            )
        except CircuitBreakerOpen:
            self._update_connection_status(False)
            self._log(LogLevel.WARN, "Circuit breaker abierto. Esperando para reconectar...")
        except Exception as e:
            self._update_connection_status(False)
            self._log(LogLevel.ERROR, f"Error al obtener pedidos: {str(e)}")

    def _init_techaura_processor(self) -> None:
        """Inicializar el procesador de TechAura."""
        try:
            self._techaura_client = TechAuraClient()
            config = OrderProcessorConfig(
                content_sources={
                    "music": "",  # Se configurará desde variables de entorno
                    "videos": "",
                    "movies": "",
                },
                polling_interval_seconds=60,
                auto_start_burning=False,
            )
            self._order_processor = TechAuraOrderProcessor(
                self._techaura_client, self._job_queue, config
            )
            self._log(LogLevel.OK, "Procesador TechAura inicializado.")
            
            # Verificar conexión inmediatamente después de inicializar
            if self._techaura_client.check_connection():
                self._update_connection_status(True)
                self._log(LogLevel.OK, "Conectado con el servidor TechAura.")
            else:
                self._update_connection_status(False)
                self._log(LogLevel.WARN, "No se puede conectar con el servidor TechAura.")
        except Exception as e:
            self._log(LogLevel.ERROR, f"Error al inicializar TechAura: {str(e)}")

    def _refresh_techaura_orders_list(self) -> None:
        """Refrescar la lista visual de pedidos TechAura."""
        # Update pending count
        count = len(self._techaura_orders)
        self._pending_orders_label.configure(
            text=f"Pedidos pendientes: {count}"
        )
        
        # Clear existing rows (except headers)
        for widget in self._techaura_orders_table.winfo_children():
            info = widget.grid_info()
            if info and int(info.get("row", 0)) > 0:
                widget.destroy()

        # Add order rows
        for idx, order in enumerate(self._techaura_orders):
            row = idx + 1

            # Get emoji for order type
            emoji = ""
            if "MUSIC" in order.product_type.upper():
                emoji = Emojis.MUSIC + " "
            elif "VIDEO" in order.product_type.upper():
                emoji = Emojis.VIDEO + " "
            elif "MOVIE" in order.product_type.upper():
                emoji = Emojis.MOVIE + " "

            # Order number label (clickable) with emoji
            order_label = ctk.CTkLabel(
                self._techaura_orders_table,
                text=f"{emoji}{order.order_number}",
                cursor="hand2",
            )
            order_label.grid(row=row, column=0, sticky="w", padx=4, pady=2)
            order_label.bind("<Button-1>", lambda e, oid=order.order_id: self._on_select_order(oid))

            # Customer name
            customer_label = ctk.CTkLabel(
                self._techaura_orders_table,
                text=order.customer_name[:20] + ("..." if len(order.customer_name) > 20 else ""),
            )
            customer_label.grid(row=row, column=1, sticky="w", padx=4, pady=2)
            customer_label.bind(
                "<Button-1>", lambda e, oid=order.order_id: self._on_select_order(oid)
            )

            # Product type
            type_label = ctk.CTkLabel(self._techaura_orders_table, text=order.product_type)
            type_label.grid(row=row, column=2, sticky="w", padx=4, pady=2)
            type_label.bind(
                "<Button-1>", lambda e, oid=order.order_id: self._on_select_order(oid)
            )
            
            # USB capacity
            capacity_label = ctk.CTkLabel(self._techaura_orders_table, text=order.capacity)
            capacity_label.grid(row=row, column=3, sticky="w", padx=4, pady=2)
            capacity_label.bind(
                "<Button-1>", lambda e, oid=order.order_id: self._on_select_order(oid)
            )

    def _on_select_order(self, order_id: str) -> None:
        """Seleccionar un pedido de la lista."""
        self._selected_order_id = order_id
        self._update_order_details_display()

    def _update_order_details_display(self) -> None:
        """Actualizar el display de detalles del pedido seleccionado."""
        self._techaura_details_text.configure(state="normal")
        self._techaura_details_text.delete("1.0", "end")

        if self._selected_order_id is None:
            self._techaura_details_text.insert("1.0", "Selecciona un pedido para ver detalles.")
            self._techaura_details_text.configure(state="disabled")
            self._update_estimated_time(None)
            return

        # Find the selected order
        order = None
        for o in self._techaura_orders:
            if o.order_id == self._selected_order_id:
                order = o
                break

        if order is None:
            self._techaura_details_text.insert("1.0", "Pedido no encontrado.")
            self._techaura_details_text.configure(state="disabled")
            self._update_estimated_time(None)
            return

        # Build details text with emojis and colors
        details = f"{Emojis.ORDER} Pedido: {order.order_number}\n"
        details += f"{Emojis.CLIENT} Cliente: {order.customer_name}\n"
        details += f"{Emojis.PHONE} Teléfono: {order.customer_phone}\n"
        details += f"{Emojis.USB} Capacidad USB: {order.capacity}\n"
        details += f"Estado: {order.status}\n"

        if order.genres:
            details += f"\n{Emojis.MUSIC} Géneros:\n"
            for genre in order.genres:
                details += f"  • {genre}\n"
        if order.artists:
            details += f"\n{Emojis.MUSIC} Artistas:\n"
            for artist in order.artists:
                details += f"  • {artist}\n"
        if order.videos:
            details += f"\n{Emojis.VIDEO} Videos:\n"
            for video in order.videos:
                details += f"  • {video}\n"
        if order.movies:
            details += f"\n{Emojis.MOVIE} Películas:\n"
            for movie in order.movies:
                details += f"  • {movie}\n"

        if order.created_at:
            details += f"\n{Emojis.CLOCK} Creado: {order.created_at}\n"

        self._techaura_details_text.insert("1.0", details)
        self._techaura_details_text.configure(state="disabled")

        # Update estimated time
        self._update_estimated_time(order)

    def _on_view_order_details(self) -> None:
        """Ver detalles completos del pedido seleccionado."""
        if self._selected_order_id is None:
            self._log(LogLevel.WARN, "Selecciona un pedido primero.")
            return
        self._update_order_details_display()
        self._log(LogLevel.INFO, f"Mostrando detalles del pedido {self._selected_order_id}")

    def _on_confirm_and_burn_order(self) -> None:
        """Confirmar y comenzar grabación del pedido seleccionado."""
        # Check for recording in progress
        if self._recording_in_progress:
            if not self._show_cancel_confirmation():
                return

        if self._selected_order_id is None:
            self._log(LogLevel.WARN, "Selecciona un pedido primero.")
            return

        if self._order_processor is None:
            self._log(LogLevel.ERROR, "Procesador TechAura no inicializado.")
            return

        # Find the selected order
        order = None
        for o in self._techaura_orders:
            if o.order_id == self._selected_order_id:
                order = o
                break

        if order is None:
            self._log(LogLevel.ERROR, "Pedido no encontrado.")
            return

        # Show confirmation dialog
        if self._show_order_confirmation_dialog(order):
            # Get USB destination
            usb_dest = self._destination_entry.get().strip()
            if not usb_dest:
                self._log(LogLevel.ERROR, "Selecciona un destino USB primero.")
                return

            # Queue the order if not already queued
            if order.order_id not in self._order_processor.pending_orders:
                self._order_processor.queue_order_for_confirmation(order)

            # Confirm and start burning
            job = self._order_processor.confirm_and_start_burning(order.order_id, usb_dest)

            if job:
                self._log(LogLevel.OK, f"Job creado para pedido {order.order_number}: {job.name}")
                self._refresh_jobs()
                self._refresh_techaura_orders_list()

                # Remove order from local list
                self._techaura_orders = [
                    o for o in self._techaura_orders if o.order_id != order.order_id
                ]
                self._selected_order_id = None
                self._update_order_details_display()
            else:
                self._log(LogLevel.ERROR, "No se pudo crear el job.")

    def _show_order_confirmation_dialog(self, order: USBOrder) -> bool:
        """Mostrar diálogo con detalles del pedido para confirmar grabación.

        Args:
            order: Orden USB a confirmar.

        Returns:
            True si el usuario confirmó, False si canceló.
        """
        # Get USB destination
        usb_dest = self._destination_entry.get().strip()
        
        # Get selected USB drive for capacity info
        selected_drive = self._get_selected_usb_drive()
        usb_info = ""
        if selected_drive:
            usb_info = f"{selected_drive.label} ({selected_drive.size_gb:.1f} GB)"
        else:
            usb_info = usb_dest or "(No seleccionado)"
        
        # Calculate estimated time
        estimated_minutes = self._calculate_estimated_time(order)
        estimated_time = f"{estimated_minutes} minutos"
        
        # Show confirmation dialog
        dialog = ConfirmationDialog(
            parent=self,
            order=order,
            usb_info=usb_info,
            estimated_time=estimated_time
        )
        
        return dialog.show()

    def destroy(self) -> None:
        """Save UI state and pending jobs before closing."""
        try:
            # Save pending jobs
            pending_jobs = [
                job for job in self._job_queue.list_jobs()
                if job.status not in (JobStatus.COMPLETED, JobStatus.ERROR)
            ]
            self._job_storage.save_jobs(pending_jobs)
            
            # Save window geometry
            self._ui_state.window_width = self.winfo_width()
            self._ui_state.window_height = self.winfo_height()
            self._ui_state.window_x = self.winfo_x()
            self._ui_state.window_y = self.winfo_y()
            self._ui_state.auto_refresh_enabled = self._auto_refresh_enabled
            
            # Save last destination if set
            dest = self._destination_entry.get()
            if dest:
                self._ui_state.last_destination = dest
            
            save_ui_state(self._ui_state)
        except Exception:
            pass  # Don't fail on save errors
        
        super().destroy()

    def setup_techaura_integration(
        self,
        content_sources: dict[str, str],
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """Configurar la integración con TechAura.

        Args:
            content_sources: Diccionario de rutas de contenido {'music': '/path', ...}
            api_url: URL del API de TechAura (opcional, usa env var si no se provee)
            api_key: Clave API de TechAura (opcional, usa env var si no se provee)
        """
        try:
            self._techaura_client = TechAuraClient(base_url=api_url, api_key=api_key)
            config = OrderProcessorConfig(
                content_sources=content_sources,
                polling_interval_seconds=60,
                auto_start_burning=False,
            )
            self._order_processor = TechAuraOrderProcessor(
                self._techaura_client, self._job_queue, config
            )
            self._log(LogLevel.OK, "Integración TechAura configurada correctamente.")
        except Exception as e:
            self._log(LogLevel.ERROR, f"Error al configurar TechAura: {str(e)}")


def run_window() -> None:
    app = MediaCopierUI()
    app.mainloop()
