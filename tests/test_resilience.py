"""Tests de resiliencia para el sistema de grabación Python."""

import os
import tempfile
import time
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
import requests

from mediacopier.api.techaura_client import (
    CircuitBreaker,
    CircuitBreakerOpen,
    InvalidJSONResponse,
    TechAuraClient,
)
from mediacopier.config.settings import TechAuraSettings
from mediacopier.integration.order_processor import (
    CopyProgress,
    OrderProcessorConfig,
    TechAuraOrderProcessor,
)
from mediacopier.ui.job_queue import JobQueue


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_requests_get() -> Generator[MagicMock, None, None]:
    """Fixture que parchea requests.get."""
    with patch("mediacopier.api.techaura_client.requests.get") as mock_get:
        yield mock_get


@pytest.fixture
def mock_requests_post() -> Generator[MagicMock, None, None]:
    """Fixture que parchea requests.post."""
    with patch("mediacopier.api.techaura_client.requests.post") as mock_post:
        yield mock_post


@pytest.fixture
def settings_fast_retry() -> TechAuraSettings:
    """Settings with fast retry for testing."""
    return TechAuraSettings(
        api_url="http://test.api",
        api_key="test-key",
        timeout_seconds=1,
        max_retries=3,
        retry_delay_seconds=0.1,  # Fast retries for testing
        circuit_breaker_threshold=5,
        circuit_breaker_timeout=2,  # Short timeout for testing
    )


@pytest.fixture
def client_fast_retry(settings_fast_retry: TechAuraSettings) -> TechAuraClient:
    """Client with fast retry settings."""
    return TechAuraClient(settings=settings_fast_retry)


@pytest.fixture
def temp_progress_dir() -> Generator[str, None, None]:
    """Create temporary directory for progress files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# ============================================================================
# Tests: API Timeout Handling
# ============================================================================


class TestHandlesAPITimeout:
    """Tests para manejo de timeout del API."""

    def test_handles_api_timeout(
        self, mock_requests_get: MagicMock, client_fast_retry: TechAuraClient
    ) -> None:
        """Test que el cliente maneja timeout del API correctamente."""
        # Configure mock to always timeout
        mock_requests_get.side_effect = requests.Timeout("Connection timed out")

        # Should raise Timeout after retries
        with pytest.raises(requests.Timeout):
            client_fast_retry.get_pending_orders()

        # Verify retries were attempted (3 retries = 3 calls)
        assert mock_requests_get.call_count == 3

    def test_timeout_triggers_circuit_breaker(
        self, mock_requests_get: MagicMock, settings_fast_retry: TechAuraSettings
    ) -> None:
        """Test que timeouts incrementan el contador del circuit breaker."""
        # Configure with lower threshold
        settings_fast_retry.circuit_breaker_threshold = 3
        client = TechAuraClient(settings=settings_fast_retry)

        mock_requests_get.side_effect = requests.Timeout("Connection timed out")

        # First request fails with retries
        with pytest.raises(requests.Timeout):
            client.get_pending_orders()

        # Circuit breaker should have recorded failures
        assert client.circuit_breaker.failure_count >= 3

    def test_successful_request_after_timeout_resets_circuit_breaker(
        self, mock_requests_get: MagicMock, client_fast_retry: TechAuraClient
    ) -> None:
        """Test que una request exitosa después de timeout resetea el circuit breaker."""
        # First request times out
        mock_requests_get.side_effect = requests.Timeout("Connection timed out")
        with pytest.raises(requests.Timeout):
            client_fast_retry.get_pending_orders()

        failures_after_timeout = client_fast_retry.circuit_breaker.failure_count

        # Second request succeeds
        mock_response = MagicMock()
        mock_response.json.return_value = {"orders": []}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.side_effect = None
        mock_requests_get.return_value = mock_response

        result = client_fast_retry.get_pending_orders()

        assert result == []
        assert client_fast_retry.circuit_breaker.failure_count == 0


# ============================================================================
# Tests: Circuit Breaker
# ============================================================================


class TestCircuitBreakerOpensAfterFailures:
    """Tests para el circuit breaker que se abre después de fallos."""

    def test_circuit_breaker_opens_after_threshold_failures(
        self, mock_requests_get: MagicMock
    ) -> None:
        """Test que el circuit breaker se abre después del umbral de fallos."""
        settings = TechAuraSettings(
            api_url="http://test.api",
            api_key="test-key",
            max_retries=1,  # Single retry to speed up test
            retry_delay_seconds=0.01,
            circuit_breaker_threshold=3,
            circuit_breaker_timeout=60,
        )
        client = TechAuraClient(settings=settings)

        mock_requests_get.side_effect = requests.ConnectionError("Connection refused")

        # Make requests until circuit breaker opens
        for _ in range(3):
            try:
                client.get_pending_orders()
            except (requests.ConnectionError, CircuitBreakerOpen):
                pass

        # Circuit breaker should now be open
        assert client.circuit_breaker.is_open is True

    def test_circuit_breaker_rejects_requests_when_open(
        self, mock_requests_get: MagicMock
    ) -> None:
        """Test que el circuit breaker rechaza requests cuando está abierto."""
        settings = TechAuraSettings(
            api_url="http://test.api",
            api_key="test-key",
            max_retries=1,
            retry_delay_seconds=0.01,
            circuit_breaker_threshold=2,
            circuit_breaker_timeout=60,
        )
        client = TechAuraClient(settings=settings)

        mock_requests_get.side_effect = requests.ConnectionError("Connection refused")

        # Open the circuit breaker
        for _ in range(2):
            try:
                client.get_pending_orders()
            except (requests.ConnectionError, CircuitBreakerOpen):
                pass

        # Reset mock to track new calls
        mock_requests_get.reset_mock()

        # Next request should be rejected without calling the API
        with pytest.raises(CircuitBreakerOpen):
            client.get_pending_orders()

        # API should not have been called
        assert mock_requests_get.call_count == 0


class TestCircuitBreakerResetsAfterSuccess:
    """Tests para el circuit breaker que se resetea después de éxito."""

    def test_circuit_breaker_resets_after_timeout(
        self, mock_requests_get: MagicMock
    ) -> None:
        """Test que el circuit breaker se resetea después del timeout."""
        settings = TechAuraSettings(
            api_url="http://test.api",
            api_key="test-key",
            max_retries=1,
            retry_delay_seconds=0.01,
            circuit_breaker_threshold=2,
            circuit_breaker_timeout=1,  # 1 second timeout for testing
        )
        client = TechAuraClient(settings=settings)

        mock_requests_get.side_effect = requests.ConnectionError("Connection refused")

        # Open the circuit breaker
        for _ in range(2):
            try:
                client.get_pending_orders()
            except (requests.ConnectionError, CircuitBreakerOpen):
                pass

        assert client.circuit_breaker.is_open is True

        # Wait for timeout
        time.sleep(1.1)

        # Circuit breaker should allow requests again
        assert client.circuit_breaker.is_open is False

    def test_circuit_breaker_resets_on_successful_request(
        self, mock_requests_get: MagicMock
    ) -> None:
        """Test que el circuit breaker se resetea con request exitosa."""
        settings = TechAuraSettings(
            api_url="http://test.api",
            api_key="test-key",
            max_retries=1,
            retry_delay_seconds=0.01,
            circuit_breaker_threshold=3,
            circuit_breaker_timeout=1,
        )
        client = TechAuraClient(settings=settings)

        # Make some failing requests
        mock_requests_get.side_effect = requests.ConnectionError("Connection refused")
        for _ in range(2):
            try:
                client.get_pending_orders()
            except (requests.ConnectionError, CircuitBreakerOpen):
                pass

        # Verify failure count
        assert client.circuit_breaker.failure_count == 2

        # Make a successful request
        mock_response = MagicMock()
        mock_response.json.return_value = {"orders": []}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.side_effect = None
        mock_requests_get.return_value = mock_response

        client.get_pending_orders()

        # Circuit breaker should be reset
        assert client.circuit_breaker.failure_count == 0
        assert client.circuit_breaker.is_open is False


class TestCircuitBreakerUnit:
    """Unit tests for CircuitBreaker class."""

    def test_initial_state(self) -> None:
        """Test initial state of circuit breaker."""
        cb = CircuitBreaker(threshold=5, timeout=60)
        assert cb.is_open is False
        assert cb.failure_count == 0

    def test_record_failure_increments_count(self) -> None:
        """Test that record_failure increments the failure count."""
        cb = CircuitBreaker(threshold=5, timeout=60)
        cb.record_failure()
        assert cb.failure_count == 1
        cb.record_failure()
        assert cb.failure_count == 2

    def test_opens_at_threshold(self) -> None:
        """Test that circuit opens at threshold."""
        cb = CircuitBreaker(threshold=3, timeout=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.is_open is True

    def test_record_success_resets(self) -> None:
        """Test that record_success resets the circuit."""
        cb = CircuitBreaker(threshold=3, timeout=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.is_open is False

    def test_manual_reset(self) -> None:
        """Test manual reset of circuit breaker."""
        cb = CircuitBreaker(threshold=2, timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        cb.reset()
        assert cb.is_open is False
        assert cb.failure_count == 0


# ============================================================================
# Tests: Resume After USB Reconnected
# ============================================================================


class TestResumeAfterUSBReconnected:
    """Tests para resumir después de reconectar USB."""

    def test_resume_after_usb_reconnected(
        self, temp_progress_dir: str
    ) -> None:
        """Test que puede resumir copia después de reconectar USB."""
        mock_client = MagicMock()
        job_queue = JobQueue()
        config = OrderProcessorConfig(
            content_sources={"music": "/media/music"},
            polling_interval_seconds=1,
            progress_save_path=temp_progress_dir,
        )

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        # Create and save progress
        progress = CopyProgress(
            order_id="test-order-123",
            total_files=100,
            files_copied=50,
            current_file_index=50,
            is_interrupted=True,
            usb_destination=temp_progress_dir,  # Use temp dir as mock USB
        )
        processor._save_progress("test-order-123", progress)

        # Verify progress was saved
        assert processor.can_resume_order("test-order-123")

        # Resume the order
        resumed_progress = processor.resume_order("test-order-123")

        assert resumed_progress is not None
        assert resumed_progress.files_copied == 50
        assert resumed_progress.current_file_index == 50
        assert resumed_progress.is_interrupted is False

    def test_cannot_resume_without_usb(
        self, temp_progress_dir: str
    ) -> None:
        """Test que no puede resumir si USB no está disponible."""
        mock_client = MagicMock()
        job_queue = JobQueue()
        config = OrderProcessorConfig(
            content_sources={"music": "/media/music"},
            polling_interval_seconds=1,
            progress_save_path=temp_progress_dir,
        )

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        # Create and save progress with non-existent USB path
        progress = CopyProgress(
            order_id="test-order-456",
            total_files=100,
            files_copied=50,
            current_file_index=50,
            is_interrupted=True,
            usb_destination="/nonexistent/usb/path",
        )
        processor._save_progress("test-order-456", progress)

        # Should not be able to resume
        assert processor.can_resume_order("test-order-456") is False

    def test_progress_saved_on_interrupt(
        self, temp_progress_dir: str
    ) -> None:
        """Test que el progreso se guarda al interrumpir."""
        mock_client = MagicMock()
        job_queue = JobQueue()
        config = OrderProcessorConfig(
            content_sources={"music": "/media/music"},
            polling_interval_seconds=1,
            progress_save_path=temp_progress_dir,
        )

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        # Create progress and store in processor
        progress = CopyProgress(
            order_id="test-order-789",
            total_files=100,
            files_copied=75,
            current_file_index=75,
            is_interrupted=False,
            usb_destination=temp_progress_dir,
        )
        processor._order_progress["test-order-789"] = progress

        # Save progress
        result = processor._save_progress("test-order-789", progress)
        assert result is True

        # Verify file exists
        progress_file = os.path.join(temp_progress_dir, "progress_test-order-789.json")
        assert os.path.exists(progress_file)

    def test_progress_deleted_on_completion(
        self, temp_progress_dir: str
    ) -> None:
        """Test que el progreso se elimina al completar."""
        mock_client = MagicMock()
        mock_client.complete_burning.return_value = True
        job_queue = JobQueue()
        config = OrderProcessorConfig(
            content_sources={"music": "/media/music"},
            polling_interval_seconds=1,
            progress_save_path=temp_progress_dir,
        )

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        # Create and save progress
        progress = CopyProgress(
            order_id="test-order-complete",
            total_files=100,
            files_copied=100,
            current_file_index=100,
        )
        processor._order_progress["test-order-complete"] = progress
        processor._save_progress("test-order-complete", progress)

        # Set up job mapping
        processor._job_to_order["job-123"] = "test-order-complete"

        # Call on_job_completed
        processor.on_job_completed("job-123")

        # Verify progress file was deleted
        progress_file = os.path.join(temp_progress_dir, "progress_test-order-complete.json")
        assert not os.path.exists(progress_file)


# ============================================================================
# Tests: Graceful Shutdown on Interrupt
# ============================================================================


class TestGracefulShutdownOnInterrupt:
    """Tests para shutdown graceful en interrupción."""

    def test_graceful_shutdown_on_interrupt(
        self, temp_progress_dir: str
    ) -> None:
        """Test que el shutdown es graceful cuando se interrumpe."""
        mock_client = MagicMock()
        mock_client.get_pending_orders.return_value = []
        job_queue = JobQueue()
        config = OrderProcessorConfig(
            content_sources={"music": "/media/music"},
            polling_interval_seconds=1,
            progress_save_path=temp_progress_dir,
        )

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        # Start polling
        processor.start_polling()
        assert processor.is_running is True

        # Stop polling gracefully
        processor.stop_polling()
        assert processor.is_running is False

    def test_shutdown_event_stops_polling(self) -> None:
        """Test que el evento de shutdown detiene el polling."""
        mock_client = MagicMock()
        mock_client.get_pending_orders.return_value = []
        job_queue = JobQueue()
        config = OrderProcessorConfig(
            content_sources={"music": "/media/music"},
            polling_interval_seconds=10,  # Long interval
        )

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        processor.start_polling()
        time.sleep(0.1)  # Let polling start

        # Set shutdown event
        processor._shutdown_event.set()
        processor._running = False

        # Wait a bit for thread to notice
        time.sleep(1.5)

        # Thread should have stopped
        assert processor.is_running is False

    def test_progress_saved_during_shutdown(
        self, temp_progress_dir: str
    ) -> None:
        """Test que el progreso se guarda durante el shutdown."""
        mock_client = MagicMock()
        job_queue = JobQueue()
        config = OrderProcessorConfig(
            content_sources={"music": "/media/music"},
            polling_interval_seconds=1,
            progress_save_path=temp_progress_dir,
        )

        processor = TechAuraOrderProcessor(mock_client, job_queue, config)

        # Create in-progress order
        progress = CopyProgress(
            order_id="shutdown-test-order",
            total_files=100,
            files_copied=30,
            current_file_index=30,
            is_interrupted=False,
            usb_destination=temp_progress_dir,
        )
        processor._order_progress["shutdown-test-order"] = progress

        # Mark as interrupted and save
        progress.is_interrupted = True
        processor._save_progress("shutdown-test-order", progress)

        # Verify progress was saved
        loaded = processor._load_progress("shutdown-test-order")
        assert loaded is not None
        assert loaded.is_interrupted is True
        assert loaded.files_copied == 30


# ============================================================================
# Tests: Retry with Exponential Backoff
# ============================================================================


class TestRetryWithExponentialBackoff:
    """Tests para retry con backoff exponencial."""

    def test_retry_with_exponential_backoff(
        self, mock_requests_get: MagicMock
    ) -> None:
        """Test que los retries usan backoff exponencial."""
        settings = TechAuraSettings(
            api_url="http://test.api",
            api_key="test-key",
            max_retries=3,
            retry_delay_seconds=0.1,
            circuit_breaker_threshold=10,  # High threshold to not trigger
        )
        client = TechAuraClient(settings=settings)

        # First two calls fail, third succeeds
        mock_response = MagicMock()
        mock_response.json.return_value = {"orders": []}
        mock_response.raise_for_status = MagicMock()

        call_times: list[float] = []

        def track_calls(*args: Any, **kwargs: Any) -> MagicMock:
            call_times.append(time.time())
            if len(call_times) < 3:
                raise requests.ConnectionError("Connection refused")
            return mock_response

        mock_requests_get.side_effect = track_calls

        start_time = time.time()
        result = client.get_pending_orders()

        assert result == []
        assert len(call_times) == 3

        # Verify backoff timing (0.1s, 0.2s delays)
        # First retry after ~0.1s, second after ~0.2s more
        if len(call_times) >= 2:
            first_delay = call_times[1] - call_times[0]
            assert first_delay >= 0.09  # Allow some tolerance

        if len(call_times) >= 3:
            second_delay = call_times[2] - call_times[1]
            assert second_delay >= 0.18  # Should be ~0.2s

    def test_retry_stops_at_max_retries(
        self, mock_requests_get: MagicMock
    ) -> None:
        """Test que los retries se detienen en max_retries."""
        settings = TechAuraSettings(
            api_url="http://test.api",
            api_key="test-key",
            max_retries=3,
            retry_delay_seconds=0.01,
            circuit_breaker_threshold=10,
        )
        client = TechAuraClient(settings=settings)

        mock_requests_get.side_effect = requests.ConnectionError("Connection refused")

        with pytest.raises(requests.ConnectionError):
            client.get_pending_orders()

        assert mock_requests_get.call_count == 3


# ============================================================================
# Tests: JSON Validation
# ============================================================================


class TestJSONValidation:
    """Tests para validación de respuestas JSON."""

    def test_handles_invalid_json_response(
        self, mock_requests_get: MagicMock
    ) -> None:
        """Test que maneja respuestas JSON inválidas."""
        import json

        settings = TechAuraSettings(
            api_url="http://test.api",
            api_key="test-key",
            max_retries=1,
            retry_delay_seconds=0.01,
            circuit_breaker_threshold=10,
        )
        client = TechAuraClient(settings=settings)

        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        with pytest.raises(InvalidJSONResponse):
            client.get_pending_orders()

    def test_validates_expected_keys(
        self, mock_requests_get: MagicMock
    ) -> None:
        """Test que valida claves esperadas en respuesta."""
        settings = TechAuraSettings(
            api_url="http://test.api",
            api_key="test-key",
            max_retries=1,
            retry_delay_seconds=0.01,
        )
        client = TechAuraClient(settings=settings)

        # Response missing expected "orders" key but still valid JSON
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}  # Wrong key
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        # Should not raise, but return empty list since "orders" key is missing
        result = client.get_pending_orders()
        assert result == []


# ============================================================================
# Tests: Copy Progress
# ============================================================================


class TestCopyProgress:
    """Tests for CopyProgress class."""

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization and deserialization."""
        progress = CopyProgress(
            order_id="test-123",
            total_files=100,
            files_copied=50,
            files_skipped=5,
            files_failed=2,
            bytes_copied=1024000,
            current_file_index=57,
            copied_files=["file1.mp3", "file2.mp3"],
            failed_files=[("file3.mp3", "Permission denied")],
            start_time=1000.0,
            is_interrupted=True,
            usb_destination="/usb/drive",
        )

        data = progress.to_dict()
        restored = CopyProgress.from_dict(data)

        assert restored.order_id == progress.order_id
        assert restored.total_files == progress.total_files
        assert restored.files_copied == progress.files_copied
        assert restored.is_interrupted == progress.is_interrupted
        assert restored.usb_destination == progress.usb_destination

    def test_estimate_remaining_time(self) -> None:
        """Test remaining time estimation."""
        progress = CopyProgress(
            order_id="test-123",
            total_files=100,
            files_copied=50,
            current_file_index=50,
            start_time=time.time() - 50,  # 50 seconds ago, 1 file/sec
        )

        remaining = progress.estimate_remaining_time()
        # Should be approximately 50 seconds (50 files left at 1 file/sec)
        assert 40 <= remaining <= 60

    def test_estimate_remaining_time_no_progress(self) -> None:
        """Test remaining time with no progress."""
        progress = CopyProgress(
            order_id="test-123",
            total_files=100,
            files_copied=0,
        )

        remaining = progress.estimate_remaining_time()
        assert remaining == 0.0
