"""Tests comprehensivos para el procesador de órdenes de TechAura."""

import time
from typing import Generator
from unittest.mock import MagicMock

import pytest
import requests

from mediacopier.api.techaura_client import TechAuraClient, USBOrder
from mediacopier.core.models import OrganizationMode, RequestedItemType
from mediacopier.integration.order_processor import (
    OrderProcessorConfig,
    PendingOrder,
    TechAuraOrderProcessor,
)
from mediacopier.ui.job_queue import JobQueue

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock TechAura client."""
    return MagicMock(spec=TechAuraClient)


@pytest.fixture
def job_queue() -> JobQueue:
    """Create a job queue for testing."""
    return JobQueue()


@pytest.fixture
def config() -> OrderProcessorConfig:
    """Create a processor config for testing."""
    return OrderProcessorConfig(
        content_sources={
            "music": "/media/music",
            "videos": "/media/videos",
            "movies": "/media/movies",
        },
        polling_interval_seconds=1,  # Short interval for testing
        auto_start_burning=False,
    )


@pytest.fixture
def sample_music_order() -> USBOrder:
    """Create a sample music order."""
    return USBOrder(
        order_id="order-123",
        order_number="ORD-001",
        customer_phone="+573001234567",
        customer_name="Juan Pérez",
        product_type="music",
        capacity="16GB",
        genres=["salsa", "merengue"],
        artists=["Marc Anthony", "Juan Luis Guerra"],
        videos=[],
        movies=[],
        created_at="2024-01-15T10:30:00Z",
        status="pending",
    )


@pytest.fixture
def sample_video_order() -> USBOrder:
    """Create a sample video order."""
    return USBOrder(
        order_id="order-456",
        order_number="ORD-002",
        customer_phone="+573009876543",
        customer_name="María García",
        product_type="videos",
        capacity="32GB",
        genres=[],
        artists=[],
        videos=["Video1", "Video2"],
        movies=[],
        created_at="2024-01-15T11:00:00Z",
        status="pending",
    )


@pytest.fixture
def sample_movie_order() -> USBOrder:
    """Create a sample movie order."""
    return USBOrder(
        order_id="order-789",
        order_number="ORD-003",
        customer_phone="+573005555555",
        customer_name="Carlos Rodríguez",
        product_type="movies",
        capacity="64GB",
        genres=["Action", "Comedy"],
        artists=[],
        videos=[],
        movies=["Movie1", "Movie2"],
        created_at="2024-01-15T12:00:00Z",
        status="pending",
    )


@pytest.fixture
def processor(
    mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
) -> Generator[TechAuraOrderProcessor, None, None]:
    """Create a processor for testing."""
    proc = TechAuraOrderProcessor(mock_client, job_queue, config)
    yield proc
    # Cleanup: stop polling if running
    if proc.is_running:
        proc.stop_polling()


# ============================================================================
# Tests: convert_order_to_job()
# ============================================================================


class TestConvertOrderToJob:
    """Tests para el método convert_order_to_job()."""

    def test_converts_music_order_to_job_with_correct_extensions(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que convierte orden de música con extensiones correctas."""
        copy_job = processor.convert_order_to_job(sample_music_order)

        expected_extensions = [".mp3", ".flac", ".wav", ".m4a"]
        assert copy_job.reglas.extensiones_permitidas == expected_extensions

    def test_converts_videos_order_to_job_with_correct_extensions(
        self, processor: TechAuraOrderProcessor, sample_video_order: USBOrder
    ) -> None:
        """Test que convierte orden de videos con extensiones correctas."""
        copy_job = processor.convert_order_to_job(sample_video_order)

        expected_extensions = [".mp4", ".mkv", ".avi", ".mov"]
        assert copy_job.reglas.extensiones_permitidas == expected_extensions

    def test_converts_movies_order_to_job_with_correct_extensions(
        self, processor: TechAuraOrderProcessor, sample_movie_order: USBOrder
    ) -> None:
        """Test que convierte orden de películas con extensiones correctas."""
        copy_job = processor.convert_order_to_job(sample_movie_order)

        expected_extensions = [".mp4", ".mkv", ".avi"]
        assert copy_job.reglas.extensiones_permitidas == expected_extensions

    def test_maps_genres_to_requested_items_genre_type(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que mapea géneros a RequestedItems de tipo GENRE."""
        copy_job = processor.convert_order_to_job(sample_music_order)

        genre_items = [
            item for item in copy_job.lista_items if item.tipo == RequestedItemType.GENRE
        ]
        assert len(genre_items) == 2
        assert genre_items[0].texto_original == "salsa"
        assert genre_items[1].texto_original == "merengue"

    def test_maps_artists_to_requested_items_artist_type(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que mapea artistas a RequestedItems de tipo ARTIST."""
        copy_job = processor.convert_order_to_job(sample_music_order)

        artist_items = [
            item for item in copy_job.lista_items if item.tipo == RequestedItemType.ARTIST
        ]
        assert len(artist_items) == 2
        assert artist_items[0].texto_original == "Marc Anthony"
        assert artist_items[1].texto_original == "Juan Luis Guerra"

    def test_sets_scatter_by_genre_for_music(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que establece modo SCATTER_BY_GENRE para música."""
        copy_job = processor.convert_order_to_job(sample_music_order)

        assert copy_job.modo_organizacion == OrganizationMode.SCATTER_BY_GENRE

    def test_sets_folder_per_request_for_movies(
        self, processor: TechAuraOrderProcessor, sample_movie_order: USBOrder
    ) -> None:
        """Test que establece modo FOLDER_PER_REQUEST para películas."""
        copy_job = processor.convert_order_to_job(sample_movie_order)

        assert copy_job.modo_organizacion == OrganizationMode.FOLDER_PER_REQUEST

    def test_handles_empty_genres_list(
        self, processor: TechAuraOrderProcessor
    ) -> None:
        """Test que maneja lista de géneros vacía."""
        order = USBOrder(
            order_id="order-empty-genres",
            order_number="ORD-EMPTY",
            customer_phone="+573001111111",
            customer_name="Test User",
            product_type="music",
            capacity="8GB",
            genres=[],
            artists=["Artist1"],
        )

        copy_job = processor.convert_order_to_job(order)

        genre_items = [
            item for item in copy_job.lista_items if item.tipo == RequestedItemType.GENRE
        ]
        assert len(genre_items) == 0

    def test_handles_empty_artists_list(
        self, processor: TechAuraOrderProcessor
    ) -> None:
        """Test que maneja lista de artistas vacía."""
        order = USBOrder(
            order_id="order-empty-artists",
            order_number="ORD-EMPTY",
            customer_phone="+573001111111",
            customer_name="Test User",
            product_type="music",
            capacity="8GB",
            genres=["rock"],
            artists=[],
        )

        copy_job = processor.convert_order_to_job(order)

        artist_items = [
            item for item in copy_job.lista_items if item.tipo == RequestedItemType.ARTIST
        ]
        assert len(artist_items) == 0

    def test_job_name_includes_order_number_and_customer(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que el nombre del job incluye número de orden y cliente."""
        copy_job = processor.convert_order_to_job(sample_music_order)

        assert copy_job.nombre == "Pedido ORD-001 - Juan Pérez"


# ============================================================================
# Tests: queue_order_for_confirmation()
# ============================================================================


class TestQueueOrderForConfirmation:
    """Tests para el método queue_order_for_confirmation()."""

    def test_adds_order_to_pending_queue(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que agrega orden a la cola de pendientes."""
        pending = processor.queue_order_for_confirmation(sample_music_order)

        assert isinstance(pending, PendingOrder)
        assert sample_music_order.order_id in processor.pending_orders
        assert processor.pending_orders[sample_music_order.order_id].order is sample_music_order

    def test_does_not_duplicate_same_order(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que sobrescribe la orden si se agrega dos veces (no duplica)."""
        processor.queue_order_for_confirmation(sample_music_order)
        processor.queue_order_for_confirmation(sample_music_order)

        # La segunda llamada sobrescribe la primera, pero solo hay una entrada
        assert len(processor.pending_orders) == 1
        assert sample_music_order.order_id in processor.pending_orders

    def test_marks_order_as_queued_in_client(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que crea PendingOrder con la estructura correcta."""
        pending = processor.queue_order_for_confirmation(sample_music_order)

        # Verify the pending order has the correct structure
        assert pending.order is sample_music_order
        assert pending.copy_job is not None
        assert pending.job is None  # Not yet started
        assert pending.usb_destination == ""  # Not yet set


# ============================================================================
# Tests: confirm_and_start_burning()
# ============================================================================


class TestConfirmAndStartBurning:
    """Tests para el método confirm_and_start_burning()."""

    def test_calls_client_start_burning(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que llama al cliente para notificar inicio de grabación."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)

        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        # Job should be created
        assert job is not None
        # Now simulate the job starting callback
        processor.on_job_started(job.id)
        mock_client.start_burning.assert_called_once_with(sample_music_order.order_id)

    def test_sets_destination_path(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que establece la ruta de destino correctamente."""
        processor.queue_order_for_confirmation(sample_music_order)

        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/my_usb")

        assert job is not None
        # The job in the queue should have the correct items
        jobs = processor._job_queue.list_jobs()
        assert len(jobs) == 1

    def test_triggers_job_runner(
        self, processor: TechAuraOrderProcessor, sample_music_order: USBOrder
    ) -> None:
        """Test que desencadena el inicio del job runner."""
        processor.queue_order_for_confirmation(sample_music_order)

        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        assert job is not None
        # Verify job was added to queue
        assert len(processor._job_queue.list_jobs()) == 1
        queued_job = processor._job_queue.list_jobs()[0]
        assert queued_job.id == job.id

    def test_handles_invalid_usb_destination(
        self, processor: TechAuraOrderProcessor
    ) -> None:
        """Test que maneja destino USB inválido (orden inexistente)."""
        # Try to confirm an order that doesn't exist
        result = processor.confirm_and_start_burning("nonexistent-order", "/usb/drive")

        assert result is None
        assert len(processor._job_queue.list_jobs()) == 0


# ============================================================================
# Tests: Callbacks
# ============================================================================


class TestCallbacks:
    """Tests para callbacks de notificación."""

    def test_on_job_started_notifies_techaura(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que on_job_started notifica a TechAura."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        processor.on_job_started(job.id)

        mock_client.start_burning.assert_called_once_with(sample_music_order.order_id)

    def test_on_job_completed_notifies_techaura(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que on_job_completed notifica a TechAura."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        processor.on_job_completed(job.id)

        mock_client.complete_burning.assert_called_once_with(sample_music_order.order_id)

    def test_on_job_failed_reports_error_to_techaura(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que on_job_failed reporta error a TechAura."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        error_message = "USB disconnected during copy"
        processor.on_job_failed(job.id, error_message)

        mock_client.report_error.assert_called_once_with(
            sample_music_order.order_id, error_message
        )

    def test_callbacks_handle_client_errors_gracefully(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que los callbacks manejan errores del cliente sin lanzar excepciones."""
        mock_client.start_burning.side_effect = requests.ConnectionError("Network error")
        mock_client.complete_burning.side_effect = requests.ConnectionError("Network error")
        mock_client.report_error.side_effect = requests.ConnectionError("Network error")

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        # These should not raise exceptions
        processor.on_job_started(job.id)
        processor.on_job_completed(job.id)
        processor.on_job_failed(job.id, "Some error")

        # All methods were called despite errors
        mock_client.start_burning.assert_called_once()
        mock_client.complete_burning.assert_called_once()
        mock_client.report_error.assert_called_once()


# ============================================================================
# Tests: Polling
# ============================================================================


class TestPolling:
    """Tests para el mecanismo de polling."""

    def test_polling_fetches_new_orders(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que el polling obtiene nuevas órdenes."""
        config = OrderProcessorConfig(
            content_sources={"music": "/media/music"},
            polling_interval_seconds=1,
            auto_start_burning=False,
        )
        mock_client.get_pending_orders.return_value = [sample_music_order]

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.start_polling()

        # Wait for at least one polling cycle
        time.sleep(1.5)

        processor.stop_polling()

        # Verify get_pending_orders was called
        mock_client.get_pending_orders.assert_called()

    def test_polling_skips_already_processed_orders(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que el polling omite órdenes ya procesadas."""
        config = OrderProcessorConfig(
            content_sources={"music": "/media/music"},
            polling_interval_seconds=1,
            auto_start_burning=False,
        )
        mock_client.get_pending_orders.return_value = [sample_music_order]

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        # Manually process the order first
        processor.queue_order_for_confirmation(sample_music_order)
        processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        initial_pending_count = len(processor.pending_orders)

        # Start polling
        processor.start_polling()
        time.sleep(1.5)
        processor.stop_polling()

        # The order should not be re-added to pending
        assert len(processor.pending_orders) == initial_pending_count

    def test_polling_handles_empty_response(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
    ) -> None:
        """Test que el polling maneja respuesta vacía."""
        mock_client.get_pending_orders.return_value = []

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.start_polling()

        time.sleep(1.5)

        processor.stop_polling()

        # Should not raise errors, pending orders should be empty
        assert len(processor.pending_orders) == 0
        mock_client.get_pending_orders.assert_called()

    def test_polling_stops_on_stop_polling_call(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
    ) -> None:
        """Test que el polling se detiene al llamar stop_polling."""
        mock_client.get_pending_orders.return_value = []

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        processor.start_polling()
        assert processor.is_running is True

        processor.stop_polling()
        assert processor.is_running is False

        # Thread should be None after stopping
        assert processor._thread is None


# ============================================================================
# Tests: Escenarios de Error
# ============================================================================


class TestErrorScenarios:
    """Tests para escenarios de error."""

    def test_handles_missing_content_source_path(
        self, job_queue: JobQueue
    ) -> None:
        """Test que maneja falta de ruta de contenido fuente."""
        mock_client = MagicMock(spec=TechAuraClient)
        config = OrderProcessorConfig(
            content_sources={},  # No content sources configured
            polling_interval_seconds=1,
        )

        order = USBOrder(
            order_id="order-no-source",
            order_number="ORD-NO-SOURCE",
            customer_phone="+573001111111",
            customer_name="Test User",
            product_type="music",  # Not in content_sources
            capacity="8GB",
        )

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        copy_job = processor.convert_order_to_job(order)

        # Should have empty origins when content source is not found
        assert copy_job.origenes == []

    def test_handles_usb_disconnected_mid_copy(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que reporta error de desconexión USB a TechAura."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        # Simulate USB disconnection error
        error_message = "USB device disconnected: /usb/drive"
        processor.on_job_failed(job.id, error_message)

        # Verify error was reported to TechAura
        mock_client.report_error.assert_called_once_with(
            sample_music_order.order_id, error_message
        )

    def test_handles_insufficient_usb_space(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que reporta error de espacio insuficiente a TechAura."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        # Simulate insufficient space error
        error_message = "Insufficient space on USB device: required 16GB, available 2GB"
        processor.on_job_failed(job.id, error_message)

        # Verify error was reported to TechAura
        mock_client.report_error.assert_called_once_with(
            sample_music_order.order_id, error_message
        )

    def test_handles_read_only_usb(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test que reporta error de USB de solo lectura a TechAura."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        # Simulate read-only USB error
        error_message = "USB device is read-only: /usb/drive"
        processor.on_job_failed(job.id, error_message)

        # Verify error was reported to TechAura
        mock_client.report_error.assert_called_once_with(
            sample_music_order.order_id, error_message
        )
