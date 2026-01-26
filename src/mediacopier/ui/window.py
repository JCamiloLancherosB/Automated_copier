"""Windowed UI for MediaCopier."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import customtkinter as ctk

from mediacopier.ui.job_queue import JobQueue, JobStatus


class LogLevel:
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    OK = "OK"


UI_POLL_INTERVAL_MS = 120


class MediaCopierUI(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MediaCopier")
        self.geometry("1200x720")
        self.minsize(1100, 650)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self._job_queue = JobQueue()
        self._selected_job_id: str | None = None
        self._ui_queue: list[Callable[[], None]] = []

        self._build_layout()
        self._start_ui_queue()
        self._log(LogLevel.INFO, "UI lista para crear jobs.")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1, uniform="cols")
        self.grid_columnconfigure(1, weight=1, uniform="cols")
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._left_panel = ctk.CTkFrame(self)
        self._left_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=12, pady=12)
        self._left_panel.grid_rowconfigure(9, weight=1)

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
        ctk.CTkLabel(self._left_panel, text="Configuración", font=("Arial", 18, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 8)
        )

        ctk.CTkLabel(self._left_panel, text="Origen").grid(
            row=1, column=0, sticky="w", padx=16
        )
        self._source_entry = ctk.CTkEntry(self._left_panel, placeholder_text="Ruta de origen")
        self._source_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 12))

        ctk.CTkLabel(self._left_panel, text="Destino").grid(
            row=3, column=0, sticky="w", padx=16
        )
        self._destination_entry = ctk.CTkEntry(self._left_panel, placeholder_text="Ruta de destino")
        self._destination_entry.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 12))

        ctk.CTkLabel(self._left_panel, text="Modo de copiado").grid(
            row=5, column=0, sticky="w", padx=16
        )
        self._mode_option = ctk.CTkOptionMenu(
            self._left_panel, values=["Completo", "Incremental", "Solo nuevos"]
        )
        self._mode_option.grid(row=6, column=0, sticky="ew", padx=16, pady=(4, 12))

        ctk.CTkLabel(self._left_panel, text="Filtros").grid(
            row=7, column=0, sticky="w", padx=16
        )
        self._filters = {
            "Solo imágenes": ctk.BooleanVar(value=True),
            "Solo videos": ctk.BooleanVar(value=False),
            "Excluir duplicados": ctk.BooleanVar(value=True),
        }
        row = 8
        for label, variable in self._filters.items():
            checkbox = ctk.CTkCheckBox(self._left_panel, text=label, variable=variable)
            checkbox.grid(row=row, column=0, sticky="w", padx=16, pady=(0, 6))
            row += 1

        self._build_action_buttons(start_row=row + 1)

    def _build_action_buttons(self, start_row: int) -> None:
        button_frame = ctk.CTkFrame(self._left_panel)
        button_frame.grid(row=start_row, column=0, sticky="ew", padx=16, pady=(12, 16))
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
        ctk.CTkLabel(
            self._queue_panel, text="Cola de trabajos", font=("Arial", 18, "bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

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
        items = self._read_items()
        job_name = f"Job {len(self._job_queue.list_jobs()) + 1}"
        job = self._job_queue.add_job(job_name, items)
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
