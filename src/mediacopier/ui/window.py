"""Windowed UI for MediaCopier."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import customtkinter as ctk

from mediacopier.core.models import CopyRules, OrganizationMode, Profile, ProfileManager
from mediacopier.ui.job_queue import JobQueue, JobStatus


class LogLevel:
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    OK = "OK"


UI_POLL_INTERVAL_MS = 120

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
        self.geometry("1200x800")
        self.minsize(1100, 700)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self._job_queue = JobQueue()
        self._profile_manager = ProfileManager()
        self._selected_job_id: str | None = None
        self._ui_queue: list[Callable[[], None]] = []

        self._build_layout()
        self._start_ui_queue()
        self._refresh_profiles()
        self._log(LogLevel.INFO, "UI lista para crear jobs.")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1, uniform="cols")
        self.grid_columnconfigure(1, weight=1, uniform="cols")
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._left_panel = ctk.CTkScrollableFrame(self)
        self._left_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=12, pady=12)

        self._right_panel = ctk.CTkFrame(self)
        self._right_panel.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=12, pady=12)
        self._right_panel.grid_rowconfigure(1, weight=1)

        self._queue_panel = ctk.CTkFrame(self)
        self._queue_panel.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._queue_panel.grid_rowconfigure(1, weight=1)

        self._log_panel = ctk.CTkFrame(self)
        self._log_panel.grid(row=2, column=1, sticky="nsew", padx=12, pady=(0, 12))
        self._log_panel.grid_rowconfigure(1, weight=1)

        self._build_left_panel()
        self._build_right_panel()
        self._build_queue_panel()
        self._build_log_panel()

    def _build_left_panel(self) -> None:
        row = 0

        # Section: Configuration
        ctk.CTkLabel(self._left_panel, text="Configuración", font=("Arial", 18, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 8)
        )
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
            row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 12)
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
        ctk.CTkLabel(self._log_panel, text="Consola de logs", font=("Arial", 18, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 8)
        )
        self._log_text = ctk.CTkTextbox(self._log_panel, wrap="word", height=160)
        self._log_text.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self._log_text.configure(state="disabled")
        self._log_text.tag_config("INFO", foreground="#9aa0a6")
        self._log_text.tag_config("WARN", foreground="#fbbc05")
        self._log_text.tag_config("ERROR", foreground="#ea4335")
        self._log_text.tag_config("OK", foreground="#34a853")

    def _start_ui_queue(self) -> None:
        def poll() -> None:
            queue = list(self._ui_queue)
            self._ui_queue.clear()
            for callback in queue:
                callback()
            self.after(UI_POLL_INTERVAL_MS, poll)

        self.after(UI_POLL_INTERVAL_MS, poll)

    def enqueue_ui(self, callback: Callable[[], None]) -> None:
        self._ui_queue.append(callback)

    def _log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {level}: {message}\n"

        def append() -> None:
            self._log_text.configure(state="normal")
            self._log_text.insert("end", line, level)
            self._log_text.see("end")
            self._log_text.configure(state="disabled")

        self.enqueue_ui(append)

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

        # Parse extensions
        extensions_text = self._extensions_entry.get().strip()
        extensions = []
        if extensions_text:
            for ext in extensions_text.split(","):
                ext = ext.strip()
                if ext:
                    if not ext.startswith("."):
                        ext = f".{ext}"
                    extensions.append(ext.lower())

        # Validate fuzzy threshold
        fuzzy_threshold = self._fuzzy_threshold_var.get()
        if fuzzy_threshold < 0 or fuzzy_threshold > 100:
            self._show_error("Umbral fuzzy debe estar entre 0 y 100")
            return None

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
        self._duration_entry.insert(0, str(rules.duracion_min_seg / 60))  # Convert seconds to min

        self._fuzzy_threshold_var.set(rules.umbral_fuzzy)
        self._fuzzy_label.configure(text=f"{int(rules.umbral_fuzzy)}%")

        self._extensions_entry.delete(0, "end")
        if rules.extensiones_permitidas:
            self._extensions_entry.insert(0, ", ".join(rules.extensiones_permitidas))

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

    def _update_job_status(self, status: JobStatus) -> None:
        job_id = self._require_selected_job()
        if not job_id:
            return
        job = self._job_queue.update_status(job_id, status)
        self._refresh_jobs()
        self._log(LogLevel.INFO, f"{job.name} -> {status.value}.")

    def _on_run_job(self) -> None:
        self._update_job_status(JobStatus.RUNNING)

    def _on_pause_job(self) -> None:
        self._update_job_status(JobStatus.PAUSED)

    def _on_resume_job(self) -> None:
        self._update_job_status(JobStatus.RUNNING)

    def _on_stop_job(self) -> None:
        self._update_job_status(JobStatus.STOPPED)

    def _on_edit_job(self) -> None:
        job_id = self._require_selected_job()
        if not job_id:
            return
        job = self._job_queue.get_job(job_id)
        new_name = f"{job.name} (editado)"
        job.name = new_name
        self._refresh_jobs()
        self._log(LogLevel.OK, f"Job actualizado: {new_name}.")

    def _on_delete_job(self) -> None:
        job_id = self._require_selected_job()
        if not job_id:
            return
        job = self._job_queue.remove_job(job_id)
        self._selected_job_id = None
        self._refresh_jobs()
        self._log(LogLevel.WARN, f"Job eliminado: {job.name}.")


def run_window() -> None:
    app = MediaCopierUI()
    app.mainloop()
