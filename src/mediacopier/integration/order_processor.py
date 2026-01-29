"""Procesador de órdenes de TechAura para grabación USB."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
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


@dataclass
class OrderProcessorConfig:
    """Configuración del procesador de órdenes de TechAura."""

    content_sources: dict[str, str]  # {'music': '/path/to/music', 'videos': '/path/to/videos'}
    polling_interval_seconds: int = 30
    auto_start_burning: bool = False  # Si True, inicia grabación automáticamente
    confirmation_callback: Optional[Callable[[USBOrder], bool]] = None


@dataclass
class PendingOrder:
    """Orden pendiente de confirmación."""

    order: USBOrder
    copy_job: CopyJob
    job: Optional[Job] = None
    usb_destination: str = ""


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
        self._lock = threading.Lock()

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

    def start_polling(self) -> None:
        """Iniciar polling de pedidos pendientes."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._polling_loop, daemon=True)
        self._thread.start()

    def stop_polling(self) -> None:
        """Detener polling."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _polling_loop(self) -> None:
        """Loop principal de polling."""
        while self._running:
            try:
                self._fetch_and_process_orders()
            except Exception:
                # Log error but continue polling
                pass

            # Wait for next interval
            for _ in range(self._config.polling_interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

    def _fetch_and_process_orders(self) -> None:
        """Obtener y procesar órdenes pendientes."""
        try:
            orders = self._client.get_pending_orders()
            for order in orders:
                if order.order_id not in self._processed_orders:
                    self._process_new_order(order)
        except Exception:
            # Silently handle API errors during polling
            pass

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
        except Exception:
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
            except Exception:
                pass  # Log error but don't fail

    def on_job_progress(self, job_id: str, progress: int) -> None:
        """Callback de progreso.

        Args:
            job_id: ID del job.
            progress: Porcentaje de progreso (0-100).
        """
        # Opcional: reportar progreso al API si se implementa en el futuro
        pass

    def on_job_completed(self, job_id: str) -> None:
        """Callback cuando termina la grabación exitosamente.

        Args:
            job_id: ID del job que terminó.
        """
        order_id = self._job_to_order.get(job_id)
        if order_id:
            try:
                self._client.complete_burning(order_id)
            except Exception:
                pass  # Log error but don't fail

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
            except Exception:
                pass  # Log error but don't fail
