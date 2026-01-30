"""Cliente para comunicación con TechAura Chatbot API."""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from mediacopier.config.settings import TechAuraSettings

# Configure module logger
logger = logging.getLogger(__name__)


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""

    pass


class InvalidJSONResponse(Exception):
    """Exception raised when API returns invalid JSON."""

    pass


@dataclass
class USBOrder:
    """Representa un pedido de USB para grabación."""

    order_id: str
    order_number: str
    customer_phone: str
    customer_name: str
    product_type: str  # 'music', 'videos', 'movies'
    capacity: str
    genres: list[str] = field(default_factory=list)
    artists: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    movies: list[str] = field(default_factory=list)
    created_at: str = ""
    status: str = ""


class CircuitBreaker:
    """Circuit breaker implementation for API resilience."""

    def __init__(self, threshold: int = 5, timeout: int = 60) -> None:
        """Initialize circuit breaker.

        Args:
            threshold: Number of failures before opening the circuit.
            timeout: Seconds to wait before allowing requests after circuit opens.
        """
        self._failure_count = 0
        self._threshold = threshold
        self._timeout = timeout
        self._last_failure_time: Optional[float] = None
        self._is_open = False

    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        if not self._is_open:
            return False

        # Check if timeout has passed (half-open state)
        if self._last_failure_time is not None:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self._timeout:
                logger.info("Circuit breaker timeout elapsed, entering half-open state")
                # Don't fully reset yet - allow one request to test
                # The circuit will be properly reset on next success
                self._is_open = False
                # Reset failure count to give the next request a chance
                self._failure_count = 0
                return False

        return True

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    def record_success(self) -> None:
        """Record a successful request, resetting the circuit."""
        if self._failure_count > 0 or self._is_open:
            logger.info("Request succeeded, resetting circuit breaker")
        self._failure_count = 0
        self._is_open = False
        self._last_failure_time = None

    def record_failure(self) -> None:
        """Record a failed request."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        logger.warning(
            f"Request failed, failure count: {self._failure_count}/{self._threshold}"
        )

        if self._failure_count >= self._threshold:
            self._is_open = True
            logger.error(
                f"Circuit breaker opened after {self._failure_count} failures. "
                f"Will retry after {self._timeout} seconds."
            )

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._failure_count = 0
        self._is_open = False
        self._last_failure_time = None
        logger.info("Circuit breaker manually reset")


class TechAuraClient:
    """Cliente para comunicación con TechAura Chatbot API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        settings: Optional[TechAuraSettings] = None,
    ):
        """Inicializa el cliente de TechAura.

        Args:
            base_url: URL base del API de TechAura.
            api_key: Clave de API para autenticación.
            settings: Configuración de TechAura (opcional).
        """
        # Use settings if provided, otherwise create defaults
        self._settings = settings or TechAuraSettings()

        # Override from explicit parameters
        self.base_url = base_url or self._settings.api_url
        self.api_key = api_key or self._settings.api_key
        self.timeout = self._settings.timeout_seconds
        self.max_retries = self._settings.max_retries
        self.retry_delay = self._settings.retry_delay_seconds

        # Initialize circuit breaker
        self._circuit_breaker = CircuitBreaker(
            threshold=self._settings.circuit_breaker_threshold,
            timeout=self._settings.circuit_breaker_timeout,
        )

        logger.debug(
            f"TechAuraClient initialized with base_url={self.base_url}, "
            f"timeout={self.timeout}s, max_retries={self.max_retries}"
        )

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Get the circuit breaker instance."""
        return self._circuit_breaker

    def _get_headers(self) -> dict[str, str]:
        """Obtener headers para las peticiones HTTP."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _validate_json_response(
        self, response: requests.Response, expected_keys: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """Validate and parse JSON response.

        Args:
            response: HTTP response object.
            expected_keys: Optional list of keys expected in the response.

        Returns:
            Parsed JSON data.

        Raises:
            InvalidJSONResponse: If response is not valid JSON.
        """
        try:
            data = response.json()
            logger.debug(f"Response JSON: {data}")

            if expected_keys:
                for key in expected_keys:
                    if key not in data:
                        logger.warning(f"Expected key '{key}' not found in response")

            return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
            raise InvalidJSONResponse(f"Failed to parse JSON response: {e}") from e

    def _request_with_retry(
        self,
        method: str,
        url: str,
        expected_keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute HTTP request with retry logic and circuit breaker.

        Args:
            method: HTTP method ('get' or 'post').
            url: Full URL for the request.
            expected_keys: Optional list of keys expected in the response.
            **kwargs: Additional arguments for requests.

        Returns:
            Parsed JSON response data.

        Raises:
            CircuitBreakerOpen: If circuit breaker is open.
            requests.RequestException: If all retries fail.
        """
        # Check circuit breaker
        if self._circuit_breaker.is_open:
            logger.error("Circuit breaker is open, request rejected")
            raise CircuitBreakerOpen(
                f"Circuit breaker is open. Wait {self._settings.circuit_breaker_timeout}s "
                "before retrying."
            )

        # Set default timeout
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", self._get_headers())

        last_exception: Optional[Exception] = None
        request_func = requests.get if method == "get" else requests.post

        for attempt in range(self.max_retries):
            delay = self.retry_delay * (2**attempt)  # Exponential backoff

            try:
                logger.debug(f"Attempt {attempt + 1}/{self.max_retries}: {method.upper()} {url}")

                response = request_func(url, **kwargs)
                response.raise_for_status()

                # Validate and parse JSON
                data = self._validate_json_response(response, expected_keys)

                # Success - reset circuit breaker
                self._circuit_breaker.record_success()
                logger.info(f"Request successful: {method.upper()} {url}")

                return data

            except (
                requests.Timeout,
                requests.ConnectionError,
                InvalidJSONResponse,
            ) as e:
                last_exception = e
                self._circuit_breaker.record_failure()
                logger.warning(
                    f"Attempt {attempt + 1} failed: {type(e).__name__}: {e}. "
                    f"Retrying in {delay}s..."
                )

                if attempt < self.max_retries - 1:
                    time.sleep(delay)

            except requests.HTTPError as e:
                # For HTTP errors (4xx, 5xx), only retry on server errors
                last_exception = e
                status_code = e.response.status_code if e.response is not None else 0

                if 500 <= status_code < 600:
                    # Server error - retry
                    self._circuit_breaker.record_failure()
                    logger.warning(
                        f"Server error {status_code}, attempt {attempt + 1}. "
                        f"Retrying in {delay}s..."
                    )
                    if attempt < self.max_retries - 1:
                        time.sleep(delay)
                else:
                    # Client error - don't retry
                    logger.error(f"Client error {status_code}: {e}")
                    raise

        # All retries exhausted
        logger.error(f"All {self.max_retries} attempts failed for {method.upper()} {url}")
        if last_exception:
            raise last_exception
        raise requests.RequestException(f"Request failed after {self.max_retries} attempts")

    def get_pending_orders(self) -> list[USBOrder]:
        """Obtener pedidos pendientes de grabación.

        Returns:
            Lista de órdenes USB pendientes de grabación.

        Raises:
            requests.RequestException: Si hay error en la comunicación con el API.
            CircuitBreakerOpen: Si el circuit breaker está abierto.
        """
        url = f"{self.base_url}/api/orders/pending"
        logger.info("Fetching pending orders")

        data = self._request_with_retry("get", url, expected_keys=["orders"])

        orders = []
        for item in data.get("orders", []):
            order = USBOrder(
                order_id=item.get("order_id", ""),
                order_number=item.get("order_number", ""),
                customer_phone=item.get("customer_phone", ""),
                customer_name=item.get("customer_name", ""),
                product_type=item.get("product_type", ""),
                capacity=item.get("capacity", ""),
                genres=item.get("genres", []),
                artists=item.get("artists", []),
                videos=item.get("videos", []),
                movies=item.get("movies", []),
                created_at=item.get("created_at", ""),
                status=item.get("status", ""),
            )
            orders.append(order)

        logger.info(f"Retrieved {len(orders)} pending orders")
        return orders

    def start_burning(self, order_id: str) -> bool:
        """Marcar pedido como en proceso de grabación.

        Args:
            order_id: ID del pedido a marcar.

        Returns:
            True si se marcó exitosamente, False en caso contrario.

        Raises:
            requests.RequestException: Si hay error en la comunicación con el API.
            CircuitBreakerOpen: Si el circuit breaker está abierto.
        """
        url = f"{self.base_url}/api/orders/{order_id}/start-burning"
        logger.info(f"Starting burning for order {order_id}")

        data = self._request_with_retry("post", url, expected_keys=["success"])
        success = data.get("success", False)

        if success:
            logger.info(f"Order {order_id} marked as burning")
        else:
            logger.warning(f"Failed to mark order {order_id} as burning")

        return success

    def complete_burning(self, order_id: str) -> bool:
        """Marcar pedido como grabación completada.

        Args:
            order_id: ID del pedido a marcar como completado.

        Returns:
            True si se marcó exitosamente, False en caso contrario.

        Raises:
            requests.RequestException: Si hay error en la comunicación con el API.
            CircuitBreakerOpen: Si el circuit breaker está abierto.
        """
        url = f"{self.base_url}/api/orders/{order_id}/complete-burning"
        logger.info(f"Completing burning for order {order_id}")

        data = self._request_with_retry("post", url, expected_keys=["success"])
        success = data.get("success", False)

        if success:
            logger.info(f"Order {order_id} marked as completed")
        else:
            logger.warning(f"Failed to mark order {order_id} as completed")

        return success

    def report_error(self, order_id: str, error_message: str) -> bool:
        """Reportar error en grabación.

        Args:
            order_id: ID del pedido con error.
            error_message: Mensaje describiendo el error.

        Returns:
            True si se reportó exitosamente, False en caso contrario.

        Raises:
            requests.RequestException: Si hay error en la comunicación con el API.
            CircuitBreakerOpen: Si el circuit breaker está abierto.
        """
        url = f"{self.base_url}/api/orders/{order_id}/report-error"
        payload = {"error_message": error_message}
        logger.error(f"Reporting error for order {order_id}: {error_message}")

        data = self._request_with_retry(
            "post", url, expected_keys=["success"], json=payload
        )
        success = data.get("success", False)

        if success:
            logger.info(f"Error reported successfully for order {order_id}")
        else:
            logger.warning(f"Failed to report error for order {order_id}")

        return success

    def check_connection(self) -> bool:
        """Check if the TechAura API is reachable.

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            url = f"{self.base_url}/api/orders/pending"
            response = requests.get(
                url, headers=self._get_headers(), timeout=self.timeout
            )
            return response.status_code < 500
        except Exception as e:
            logger.debug(f"Connection check failed: {e}")
            return False
