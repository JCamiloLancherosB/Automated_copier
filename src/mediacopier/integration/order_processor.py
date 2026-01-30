"""Procesador de órdenes de TechAura para grabación USB."""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from mediacopier.api.techaura_client import TechAuraClient, USBOrder
from mediacopier.core.models import (
    CopyJob,
    CopyRules,
    OrganizationMode,
    RequestedItem,
    RequestedItemType,
)
from mediacopier.ui.job_queue import Job, JobQueue

# Configure module logger
logger = logging.getLogger(__name__)


class USBDisconnectedError(Exception):
    """Error raised when USB device is disconnected during copy."""

    pass


class InsufficientSpaceError(Exception):
    """Error raised when there's not enough space on USB."""

    pass


class CorruptFileError(Exception):
    """Error raised when source file is corrupt."""

    pass


class InsufficientPermissionsError(Exception):
    """Error raised when there are insufficient permissions."""

    pass


class UserInterruptError(Exception):
    """Error raised when user interrupts the process (Ctrl+C)."""

    pass


@dataclass
class CopyProgress:
    """Progress state for copy operations, used for resume capability."""

    order_id: str
    total_files: int = 0
    files_copied: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    bytes_copied: int = 0
    current_file_index: int = 0
    copied_files: list[str] = field(default_factory=list)
    failed_files: list[tuple[str, str]] = field(default_factory=list)
    start_time: float = 0.0
    last_update_time: float = 0.0
    is_interrupted: bool = False
    usb_destination: str = ""

    def to_dict(self) -> dict:
        """Convert progress to dictionary for serialization."""
        return {
            "order_id": self.order_id,
            "total_files": self.total_files,
            "files_copied": self.files_copied,
            "files_skipped": self.files_skipped,
            "files_failed": self.files_failed,
            "bytes_copied": self.bytes_copied,
            "current_file_index": self.current_file_index,
            "copied_files": self.copied_files,
            "failed_files": self.failed_files,
            "start_time": self.start_time,
            "last_update_time": self.last_update_time,
            "is_interrupted": self.is_interrupted,
            "usb_destination": self.usb_destination,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CopyProgress":
        """Create progress from dictionary."""
        return cls(
            order_id=data.get("order_id", ""),
            total_files=data.get("total_files", 0),
            files_copied=data.get("files_copied", 0),
            files_skipped=data.get("files_skipped", 0),
            files_failed=data.get("files_failed", 0),
            bytes_copied=data.get("bytes_copied", 0),
            current_file_index=data.get("current_file_index", 0),
            copied_files=data.get("copied_files", []),
            failed_files=data.get("failed_files", []),
            start_time=data.get("start_time", 0.0),
            last_update_time=data.get("last_update_time", 0.0),
            is_interrupted=data.get("is_interrupted", False),
            usb_destination=data.get("usb_destination", ""),
        )

    def estimate_remaining_time(self) -> float:
        """Estimate remaining time in seconds based on current progress."""
        if self.files_copied == 0 or self.start_time == 0:
            return 0.0
        elapsed = time.time() - self.start_time
        rate = self.files_copied / elapsed
        remaining_files = self.total_files - self.current_file_index
        return remaining_files / rate if rate > 0 else 0.0


@dataclass
class OrderProcessorConfig:
    """Configuración del procesador de órdenes de TechAura."""

    content_sources: dict[str, str]  # {'music': '/path/to/music', 'videos': '/path/to/videos'}
    polling_interval_seconds: int = 30
    auto_start_burning: bool = False  # Si True, inicia grabación automáticamente
    confirmation_callback: Optional[Callable[[USBOrder], bool]] = None
    progress_save_path: str = ""  # Path to save progress files for resume
    on_new_order_callback: Optional[Callable[[USBOrder], None]] = None


@dataclass
class PendingOrder:
    """Orden pendiente de confirmación."""

    order: USBOrder
    copy_job: CopyJob
    job: Optional[Job] = None
    usb_destination: str = ""
    progress: Optional[CopyProgress] = None


class TechAuraOrderProcessor:
    """Procesador de órdenes de TechAura para integración con cola de trabajos."""

    def __init__(
        self, client: TechAuraClient, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Inicializa el procesador de órdenes.

        Args:
            client: Cliente de TechAura para comunicación con el API.
            job_queue: Cola de trabajos de MediaCopier.
            config: Configuración del procesador.
        """
        self._client = client
        self._job_queue = job_queue
        self._config = config
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processed_orders: set[str] = set()
        self._pending_orders: dict[str, PendingOrder] = {}
        self._job_to_order: dict[str, str] = {}  # job_id -> order_id mapping
        self._order_progress: dict[str, CopyProgress] = {}  # order_id -> progress
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._previous_order_ids: set[str] = set()

        # Set up signal handlers for graceful shutdown
        self._original_sigint_handler = signal.getsignal(signal.SIGINT)
        self._original_sigterm_handler = signal.getsignal(signal.SIGTERM)

        logger.debug("TechAuraOrderProcessor initialized")

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum: int, frame: object) -> None:
            logger.warning(f"Received signal {signum}, initiating graceful shutdown...")
            self._shutdown_event.set()
            self._running = False

            # Save progress for all active orders (copy dict to avoid race conditions)
            with self._lock:
                progress_copy = dict(self._order_progress)

            for order_id, progress in progress_copy.items():
                if progress and not progress.is_interrupted:
                    progress.is_interrupted = True
                    self._save_progress(order_id, progress)
                    logger.info(f"Progress saved for order {order_id}")

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        signal.signal(signal.SIGINT, self._original_sigint_handler)
        signal.signal(signal.SIGTERM, self._original_sigterm_handler)

    @property
    def client(self) -> TechAuraClient:
        """Obtener el cliente de TechAura."""
        return self._client

    @property
    def pending_orders(self) -> dict[str, PendingOrder]:
        """Obtener órdenes pendientes de confirmación."""
        with self._lock:
            return dict(self._pending_orders)

    @property
    def is_running(self) -> bool:
        """Verificar si el polling está activo."""
        return self._running

    def get_progress(self, order_id: str) -> Optional[CopyProgress]:
        """Get copy progress for an order."""
        return self._order_progress.get(order_id)

    def _get_progress_file_path(self, order_id: str) -> str:
        """Get the file path for storing progress."""
        if self._config.progress_save_path:
            return os.path.join(self._config.progress_save_path, f"progress_{order_id}.json")
        return ""

    def _save_progress(self, order_id: str, progress: CopyProgress) -> bool:
        """Save progress to file for resume capability.

        Args:
            order_id: Order ID.
            progress: Progress to save.

        Returns:
            True if saved successfully, False otherwise.
        """
        file_path = self._get_progress_file_path(order_id)
        if not file_path:
            return False

        try:
            progress.last_update_time = time.time()
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(progress.to_dict(), f, indent=2)
            logger.debug(f"Progress saved for order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save progress for order {order_id}: {e}")
            return False

    def _load_progress(self, order_id: str) -> Optional[CopyProgress]:
        """Load progress from file for resume capability.

        Args:
            order_id: Order ID.

        Returns:
            Loaded progress or None if not found.
        """
        file_path = self._get_progress_file_path(order_id)
        if not file_path or not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            progress = CopyProgress.from_dict(data)
            logger.info(
                f"Loaded progress for order {order_id}: {progress.files_copied} files copied"
            )
            return progress
        except Exception as e:
            logger.error(f"Failed to load progress for order {order_id}: {e}")
            return None

    def _delete_progress(self, order_id: str) -> None:
        """Delete progress file after successful completion.

        Args:
            order_id: Order ID.
        """
        file_path = self._get_progress_file_path(order_id)
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Progress file deleted for order {order_id}")
            except Exception as e:
                logger.warning(f"Failed to delete progress file for order {order_id}: {e}")

    def start_polling(self) -> None:
        """Iniciar polling de pedidos pendientes."""
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()
        self._setup_signal_handlers()
        self._thread = threading.Thread(target=self._polling_loop, daemon=True)
        self._thread.start()
        logger.info("Polling started")

    def stop_polling(self) -> None:
        """Detener polling."""
        self._running = False
        self._shutdown_event.set()
        self._restore_signal_handlers()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Polling stopped")

    def _polling_loop(self) -> None:
        """Loop principal de polling."""
        while self._running and not self._shutdown_event.is_set():
            try:
                self._fetch_and_process_orders()
            except Exception as e:
                # Log error but continue polling
                logger.error(f"Error during polling: {e}")

            # Wait for next interval with interruptible sleep
            for _ in range(self._config.polling_interval_seconds):
                if not self._running or self._shutdown_event.is_set():
                    break
                time.sleep(1)

    def _fetch_and_process_orders(self) -> None:
        """Obtener y procesar órdenes pendientes."""
        try:
            orders = self._client.get_pending_orders()
            current_order_ids = {order.order_id for order in orders}

            for order in orders:
                if order.order_id not in self._processed_orders:
                    self._process_new_order(order)

                    # Check if this is a truly new order (not seen before)
                    if order.order_id not in self._previous_order_ids:
                        # Notify about new order
                        if self._config.on_new_order_callback:
                            try:
                                self._config.on_new_order_callback(order)
                            except Exception as e:
                                logger.error(f"Error in new order callback: {e}")
                        logger.info(f"New order detected: {order.order_number}")

            # Update previous order IDs
            self._previous_order_ids = current_order_ids

        except Exception as e:
            # Log API errors during polling
            logger.warning(f"Failed to fetch orders: {e}")

    def _process_new_order(self, order: USBOrder) -> None:
        """Procesar una nueva orden."""
        with self._lock:
            if order.order_id in self._processed_orders:
                return

            if self._config.auto_start_burning and self._config.confirmation_callback:
                # Auto-start with confirmation callback
                if self._config.confirmation_callback(order):
                    self._processed_orders.add(order.order_id)
            else:
                # Add to pending orders for manual confirmation
                self.queue_order_for_confirmation(order)

    def fetch_pending_orders(self) -> list[USBOrder]:
        """Obtener órdenes pendientes manualmente (sin polling).

        Returns:
            Lista de órdenes USB pendientes.
        """
        try:
            return self._client.get_pending_orders()
        except Exception as e:
            logger.error(f"Failed to fetch pending orders: {e}")
            return []

    def convert_order_to_job(self, order: USBOrder) -> CopyJob:
        """Convertir orden de TechAura a CopyJob.

        Args:
            order: Orden USB de TechAura.

        Returns:
            CopyJob configurado según la orden.
        """
        # Mapear géneros/artistas a RequestedItem
        items: list[RequestedItem] = []
        for genre in order.genres:
            items.append(RequestedItem(tipo=RequestedItemType.GENRE, texto_original=genre))
        for artist in order.artists:
            items.append(RequestedItem(tipo=RequestedItemType.ARTIST, texto_original=artist))

        # Determinar origen basado en tipo de producto
        source_path = self._config.content_sources.get(order.product_type, "")

        # Crear CopyJob
        return CopyJob(
            nombre=f"Pedido {order.order_number} - {order.customer_name}",
            origenes=[source_path] if source_path else [],
            destino="",  # Se establecerá cuando se seleccione USB
            modo_organizacion=(
                OrganizationMode.SCATTER_BY_GENRE
                if order.product_type == "music"
                else OrganizationMode.FOLDER_PER_REQUEST
            ),
            lista_items=items,
            reglas=CopyRules(
                extensiones_permitidas=self._get_extensions_for_type(order.product_type)
            ),
        )

    def queue_order_for_confirmation(self, order: USBOrder) -> PendingOrder:
        """Agregar orden a cola pendiente de confirmación.

        Args:
            order: Orden USB a agregar.

        Returns:
            PendingOrder con la información de la orden.
        """
        copy_job = self.convert_order_to_job(order)
        pending = PendingOrder(order=order, copy_job=copy_job)

        with self._lock:
            self._pending_orders[order.order_id] = pending

        return pending

    def confirm_and_start_burning(self, order_id: str, usb_destination: str) -> Optional[Job]:
        """Confirmar detalles y comenzar grabación.

        Args:
            order_id: ID de la orden a confirmar.
            usb_destination: Ruta de destino USB.

        Returns:
            Job creado o None si falla.
        """
        with self._lock:
            pending = self._pending_orders.get(order_id)
            if pending is None:
                return None

            # Update destination
            pending.usb_destination = usb_destination
            pending.copy_job.destino = usb_destination

            # Create job in queue
            job = self._job_queue.add_job(
                name=pending.copy_job.nombre,
                items=[item.texto_original for item in pending.copy_job.lista_items],
                rules=pending.copy_job.reglas,
                organization_mode=pending.copy_job.modo_organizacion,
            )
            pending.job = job
            self._job_to_order[job.id] = order_id
            self._processed_orders.add(order_id)

            # Remove from pending
            del self._pending_orders[order_id]

        return job

    def cancel_pending_order(self, order_id: str) -> bool:
        """Cancelar una orden pendiente.

        Args:
            order_id: ID de la orden a cancelar.

        Returns:
            True si se canceló exitosamente.
        """
        with self._lock:
            if order_id in self._pending_orders:
                del self._pending_orders[order_id]
                return True
        return False

    def get_order_id_for_job(self, job_id: str) -> Optional[str]:
        """Obtener el order_id asociado a un job.

        Args:
            job_id: ID del job.

        Returns:
            ID de la orden o None si no existe.
        """
        return self._job_to_order.get(job_id)

    def _get_extensions_for_type(self, product_type: str) -> list[str]:
        """Obtener extensiones permitidas según tipo de producto.

        Args:
            product_type: Tipo de producto (music, videos, movies).

        Returns:
            Lista de extensiones permitidas.
        """
        if product_type == "music":
            return [".mp3", ".flac", ".wav", ".m4a"]
        elif product_type == "videos":
            return [".mp4", ".mkv", ".avi", ".mov"]
        elif product_type == "movies":
            return [".mp4", ".mkv", ".avi"]
        return []

    # Edge case validation methods
    def validate_usb_connection(self, usb_path: str) -> tuple[bool, str]:
        """Validate that the USB device is connected and accessible.

        Args:
            usb_path: Path to the USB mount point.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not usb_path:
            return False, "USB path is empty"

        if not os.path.exists(usb_path):
            logger.error(f"USB disconnected: path does not exist: {usb_path}")
            return False, f"USB disconnected: {usb_path} does not exist"

        if not os.path.isdir(usb_path):
            logger.error(f"USB path is not a directory: {usb_path}")
            return False, f"USB path is not a directory: {usb_path}"

        # Check if we can write to the USB
        test_file = os.path.join(usb_path, ".write_test")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            try:
                os.remove(test_file)
            except OSError:
                pass  # Ignore removal errors, the write succeeded
        except PermissionError:
            logger.error(f"Insufficient permissions to write to USB: {usb_path}")
            return False, f"Insufficient permissions to write to USB: {usb_path}"
        except OSError as e:
            logger.error(f"Cannot write to USB: {e}")
            return False, f"Cannot write to USB: {e}"

        return True, ""

    def check_usb_space(
        self, usb_path: str, required_bytes: int
    ) -> tuple[bool, int, str]:
        """Check if USB has enough free space.

        Args:
            usb_path: Path to the USB mount point.
            required_bytes: Required space in bytes.

        Returns:
            Tuple of (has_space, available_bytes, error_message).
        """
        try:
            stat = os.statvfs(usb_path)
            available_bytes = stat.f_bavail * stat.f_frsize

            if available_bytes < required_bytes:
                required_mb = required_bytes / (1024 * 1024)
                available_mb = available_bytes / (1024 * 1024)
                error_msg = (
                    f"Insufficient space on USB: required {required_mb:.1f}MB, "
                    f"available {available_mb:.1f}MB"
                )
                logger.error(error_msg)
                return False, available_bytes, error_msg

            return True, available_bytes, ""
        except Exception as e:
            logger.error(f"Failed to check USB space: {e}")
            return False, 0, f"Failed to check USB space: {e}"

    def validate_source_file(self, file_path: str) -> tuple[bool, str]:
        """Validate that a source file is readable and not corrupt.

        Args:
            file_path: Path to the source file.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not os.path.exists(file_path):
            return False, f"Source file does not exist: {file_path}"

        if not os.path.isfile(file_path):
            return False, f"Source path is not a file: {file_path}"

        # Check read permissions
        if not os.access(file_path, os.R_OK):
            logger.error(f"Insufficient permissions to read file: {file_path}")
            return False, f"Insufficient permissions to read file: {file_path}"

        # Try to read the first few bytes to check for corruption
        try:
            with open(file_path, "rb") as f:
                # Read first 1KB to check for basic corruption
                header = f.read(1024)
                if len(header) == 0 and os.path.getsize(file_path) > 0:
                    logger.error(f"File appears to be corrupt: {file_path}")
                    return False, f"File appears to be corrupt: {file_path}"
        except IOError as e:
            logger.error(f"Failed to read file: {file_path}: {e}")
            return False, f"Failed to read file (possibly corrupt): {e}"

        return True, ""

    def can_resume_order(self, order_id: str) -> bool:
        """Check if an order can be resumed from saved progress.

        Args:
            order_id: Order ID.

        Returns:
            True if progress exists and can be resumed.
        """
        progress = self._load_progress(order_id)
        if progress and progress.is_interrupted:
            # Validate the USB destination still exists
            is_valid, _ = self.validate_usb_connection(progress.usb_destination)
            return is_valid
        return False

    def resume_order(self, order_id: str) -> Optional[CopyProgress]:
        """Resume a previously interrupted order.

        Args:
            order_id: Order ID.

        Returns:
            Copy progress if resumed, None otherwise.
        """
        progress = self._load_progress(order_id)
        if not progress:
            logger.warning(f"No progress found for order {order_id}")
            return None

        # Validate USB is still connected
        is_valid, error = self.validate_usb_connection(progress.usb_destination)
        if not is_valid:
            logger.error(f"Cannot resume order {order_id}: {error}")
            return None

        # Store progress for tracking
        self._order_progress[order_id] = progress
        progress.is_interrupted = False
        logger.info(
            f"Resuming order {order_id} from file {progress.current_file_index + 1}"
        )

        return progress

    # Callbacks para reportar estado a TechAura
    def on_job_started(self, job_id: str) -> None:
        """Callback cuando inicia la grabación.

        Args:
            job_id: ID del job que inició.
        """
        order_id = self._job_to_order.get(job_id)
        if order_id:
            try:
                self._client.start_burning(order_id)
                logger.info(f"Notified TechAura: job {job_id} started for order {order_id}")
            except Exception as e:
                logger.error(f"Failed to notify TechAura of job start: {e}")

    def on_job_progress(self, job_id: str, progress: int) -> None:
        """Callback de progreso.

        Args:
            job_id: ID del job.
            progress: Porcentaje de progreso (0-100).
        """
        order_id = self._job_to_order.get(job_id)
        if order_id:
            with self._lock:
                # Update internal progress tracking
                if order_id in self._order_progress:
                    self._order_progress[order_id].files_copied = progress
                    # Periodically save progress
                    if progress % 10 == 0:  # Save every 10%
                        self._save_progress(order_id, self._order_progress[order_id])

    def on_job_completed(self, job_id: str) -> None:
        """Callback cuando termina la grabación exitosamente.

        Args:
            job_id: ID del job que terminó.
        """
        order_id = self._job_to_order.get(job_id)
        if order_id:
            try:
                self._client.complete_burning(order_id)
                logger.info(f"Notified TechAura: job {job_id} completed for order {order_id}")
                # Clean up progress file
                self._delete_progress(order_id)
                with self._lock:
                    if order_id in self._order_progress:
                        del self._order_progress[order_id]
            except Exception as e:
                logger.error(f"Failed to notify TechAura of job completion: {e}")

    def on_job_failed(self, job_id: str, error: str) -> None:
        """Callback cuando falla la grabación.

        Args:
            job_id: ID del job que falló.
            error: Mensaje de error.
        """
        order_id = self._job_to_order.get(job_id)
        if order_id:
            try:
                self._client.report_error(order_id, error)
                logger.info(f"Notified TechAura: job {job_id} failed for order {order_id}")

                # Save progress for potential resume
                with self._lock:
                    if order_id in self._order_progress:
                        progress = self._order_progress[order_id]
                        progress.is_interrupted = True
                        self._save_progress(order_id, progress)
            except Exception as e:
                logger.error(f"Failed to notify TechAura of job failure: {e}")
