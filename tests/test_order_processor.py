"""Tests para el procesador de órdenes de TechAura."""

from unittest.mock import MagicMock

import pytest

from mediacopier.api.techaura_client import TechAuraClient, USBOrder
from mediacopier.core.models import OrganizationMode, RequestedItemType
from mediacopier.integration.order_processor import (
    OrderProcessorConfig,
    PendingOrder,
    TechAuraOrderProcessor,
)
from mediacopier.ui.job_queue import JobQueue


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
        polling_interval_seconds=5,
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


class TestOrderProcessorConfig:
    """Tests para OrderProcessorConfig."""

    def test_config_creation_with_defaults(self) -> None:
        """Test de creación de config con valores por defecto."""
        config = OrderProcessorConfig(content_sources={"music": "/music"})
        assert config.polling_interval_seconds == 30
        assert config.auto_start_burning is False
        assert config.confirmation_callback is None

    def test_config_creation_custom_values(self) -> None:
        """Test de creación de config con valores personalizados."""
        callback = MagicMock()
        config = OrderProcessorConfig(
            content_sources={"music": "/music", "videos": "/videos"},
            polling_interval_seconds=60,
            auto_start_burning=True,
            confirmation_callback=callback,
        )
        assert config.content_sources == {"music": "/music", "videos": "/videos"}
        assert config.polling_interval_seconds == 60
        assert config.auto_start_burning is True
        assert config.confirmation_callback is callback


class TestTechAuraOrderProcessor:
    """Tests para TechAuraOrderProcessor."""

    def test_processor_initialization(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de inicialización del procesador."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        assert processor.client is mock_client
        assert processor.is_running is False
        assert processor.pending_orders == {}

    def test_start_stop_polling(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de iniciar y detener polling."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        processor.start_polling()
        assert processor.is_running is True

        processor.stop_polling()
        assert processor.is_running is False

    def test_start_polling_idempotent(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de que start_polling es idempotente."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        processor.start_polling()
        thread1 = processor._thread
        processor.start_polling()  # Second call should not create new thread
        assert processor._thread is thread1

        processor.stop_polling()


class TestConvertOrderToJob:
    """Tests para conversión de órdenes a jobs."""

    def test_convert_music_order(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de conversión de orden de música."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        copy_job = processor.convert_order_to_job(sample_music_order)

        assert copy_job.nombre == "Pedido ORD-001 - Juan Pérez"
        assert copy_job.origenes == ["/media/music"]
        assert copy_job.destino == ""
        assert copy_job.modo_organizacion == OrganizationMode.SCATTER_BY_GENRE

        # Check requested items
        assert len(copy_job.lista_items) == 4
        genres = [i for i in copy_job.lista_items if i.tipo == RequestedItemType.GENRE]
        artists = [i for i in copy_job.lista_items if i.tipo == RequestedItemType.ARTIST]
        assert len(genres) == 2
        assert len(artists) == 2
        assert genres[0].texto_original == "salsa"
        assert artists[0].texto_original == "Marc Anthony"

        # Check rules
        assert ".mp3" in copy_job.reglas.extensiones_permitidas
        assert ".flac" in copy_job.reglas.extensiones_permitidas

    def test_convert_video_order(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_video_order: USBOrder,
    ) -> None:
        """Test de conversión de orden de videos."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        copy_job = processor.convert_order_to_job(sample_video_order)

        assert copy_job.nombre == "Pedido ORD-002 - María García"
        assert copy_job.origenes == ["/media/videos"]
        assert copy_job.modo_organizacion == OrganizationMode.FOLDER_PER_REQUEST

        # Check rules
        assert ".mp4" in copy_job.reglas.extensiones_permitidas
        assert ".mkv" in copy_job.reglas.extensiones_permitidas

    def test_convert_order_unknown_product_type(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de conversión con tipo de producto desconocido."""
        order = USBOrder(
            order_id="order-999",
            order_number="ORD-999",
            customer_phone="+573001111111",
            customer_name="Test User",
            product_type="unknown",
            capacity="8GB",
        )
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        copy_job = processor.convert_order_to_job(order)

        assert copy_job.origenes == []
        assert copy_job.reglas.extensiones_permitidas == []


class TestQueueOrderForConfirmation:
    """Tests para agregar órdenes a cola de confirmación."""

    def test_queue_order_creates_pending_order(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de agregar orden a cola de confirmación."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        pending = processor.queue_order_for_confirmation(sample_music_order)

        assert isinstance(pending, PendingOrder)
        assert pending.order is sample_music_order
        assert pending.copy_job is not None
        assert pending.job is None
        assert pending.usb_destination == ""

        # Check it's in pending orders
        assert sample_music_order.order_id in processor.pending_orders

    def test_queue_multiple_orders(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
        sample_video_order: USBOrder,
    ) -> None:
        """Test de agregar múltiples órdenes."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        processor.queue_order_for_confirmation(sample_music_order)
        processor.queue_order_for_confirmation(sample_video_order)

        assert len(processor.pending_orders) == 2


class TestConfirmAndStartBurning:
    """Tests para confirmar y comenzar grabación."""

    def test_confirm_order_creates_job(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de confirmar orden crea job."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)

        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb/drive")

        assert job is not None
        assert job.name == "Pedido ORD-001 - Juan Pérez"
        assert len(job_queue.list_jobs()) == 1

        # Order should be removed from pending
        assert sample_music_order.order_id not in processor.pending_orders

    def test_confirm_nonexistent_order_returns_none(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de confirmar orden inexistente retorna None."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        result = processor.confirm_and_start_burning("nonexistent", "/usb")

        assert result is None
        assert len(job_queue.list_jobs()) == 0


class TestCancelPendingOrder:
    """Tests para cancelar órdenes pendientes."""

    def test_cancel_pending_order(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de cancelar orden pendiente."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)

        result = processor.cancel_pending_order(sample_music_order.order_id)

        assert result is True
        assert sample_music_order.order_id not in processor.pending_orders

    def test_cancel_nonexistent_order_returns_false(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de cancelar orden inexistente retorna False."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        result = processor.cancel_pending_order("nonexistent")

        assert result is False


class TestJobCallbacks:
    """Tests para callbacks de estado de jobs."""

    def test_on_job_started_calls_api(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de callback on_job_started llama al API."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb")

        processor.on_job_started(job.id)

        mock_client.start_burning.assert_called_once_with(sample_music_order.order_id)

    def test_on_job_completed_calls_api(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de callback on_job_completed llama al API."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb")

        processor.on_job_completed(job.id)

        mock_client.complete_burning.assert_called_once_with(sample_music_order.order_id)

    def test_on_job_failed_calls_api_with_error(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de callback on_job_failed llama al API con error."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb")

        processor.on_job_failed(job.id, "USB disconnected")

        mock_client.report_error.assert_called_once_with(
            sample_music_order.order_id, "USB disconnected"
        )

    def test_on_job_started_unknown_job_no_error(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de callback con job desconocido no causa error."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        # Should not raise exception
        processor.on_job_started("unknown-job-id")
        mock_client.start_burning.assert_not_called()

    def test_callbacks_handle_api_errors(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de que callbacks manejan errores del API."""
        import requests

        mock_client.start_burning.side_effect = requests.ConnectionError()

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb")

        # Should not raise exception
        processor.on_job_started(job.id)


class TestFetchPendingOrders:
    """Tests para obtener órdenes pendientes manualmente."""

    def test_fetch_pending_orders_success(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de obtener órdenes pendientes exitosamente."""
        mock_client.get_pending_orders.return_value = [sample_music_order]

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        orders = processor.fetch_pending_orders()

        assert len(orders) == 1
        assert orders[0].order_id == sample_music_order.order_id

    def test_fetch_pending_orders_handles_errors(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de manejo de errores al obtener órdenes."""
        import requests

        mock_client.get_pending_orders.side_effect = requests.ConnectionError()

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        orders = processor.fetch_pending_orders()

        assert orders == []


class TestGetExtensionsForType:
    """Tests para obtener extensiones por tipo de producto."""

    def test_music_extensions(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de extensiones para música."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        extensions = processor._get_extensions_for_type("music")

        assert ".mp3" in extensions
        assert ".flac" in extensions
        assert ".wav" in extensions
        assert ".m4a" in extensions

    def test_videos_extensions(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de extensiones para videos."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        extensions = processor._get_extensions_for_type("videos")

        assert ".mp4" in extensions
        assert ".mkv" in extensions
        assert ".avi" in extensions
        assert ".mov" in extensions

    def test_movies_extensions(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de extensiones para películas."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        extensions = processor._get_extensions_for_type("movies")

        assert ".mp4" in extensions
        assert ".mkv" in extensions
        assert ".avi" in extensions
        assert ".mov" not in extensions  # Movies don't include .mov

    def test_unknown_type_returns_empty(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de tipo desconocido retorna lista vacía."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        extensions = processor._get_extensions_for_type("unknown")

        assert extensions == []


class TestGetOrderIdForJob:
    """Tests para obtener order_id por job_id."""

    def test_get_order_id_for_confirmed_job(
        self,
        mock_client: MagicMock,
        job_queue: JobQueue,
        config: OrderProcessorConfig,
        sample_music_order: USBOrder,
    ) -> None:
        """Test de obtener order_id para job confirmado."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)
        processor.queue_order_for_confirmation(sample_music_order)
        job = processor.confirm_and_start_burning(sample_music_order.order_id, "/usb")

        order_id = processor.get_order_id_for_job(job.id)

        assert order_id == sample_music_order.order_id

    def test_get_order_id_unknown_job_returns_none(
        self, mock_client: MagicMock, job_queue: JobQueue, config: OrderProcessorConfig
    ) -> None:
        """Test de obtener order_id para job desconocido retorna None."""
        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        order_id = processor.get_order_id_for_job("unknown-job")

        assert order_id is None
