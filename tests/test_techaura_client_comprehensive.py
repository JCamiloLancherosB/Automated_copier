"""Tests comprehensivos para el cliente de TechAura."""

from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from mediacopier.api.techaura_client import TechAuraClient, USBOrder


class TestConnectionAndAuthentication:
    """Tests para conexión y autenticación del cliente."""

    def test_client_connects_with_valid_credentials(
        self,
        mock_requests_get: MagicMock,
        valid_api_key: str,
        test_base_url: str,
        empty_orders_response: dict[str, Any],
    ) -> None:
        """Test que el cliente conecta correctamente con credenciales válidas."""
        mock_response = MagicMock()
        mock_response.json.return_value = empty_orders_response
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        client = TechAuraClient(base_url=test_base_url, api_key=valid_api_key)
        orders = client.get_pending_orders()

        assert orders == []
        mock_requests_get.assert_called_once()
        call_kwargs = mock_requests_get.call_args[1]
        assert call_kwargs["headers"]["X-API-Key"] == valid_api_key

    def test_client_raises_on_invalid_api_key(
        self,
        mock_requests_get: MagicMock,
        test_base_url: str,
    ) -> None:
        """Test que el cliente lanza excepción con API key inválida."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "401 Unauthorized"
        )
        mock_requests_get.return_value = mock_response

        client = TechAuraClient(base_url=test_base_url, api_key="invalid-key")

        with pytest.raises(requests.HTTPError) as exc_info:
            client.get_pending_orders()
        assert "401" in str(exc_info.value)

    def test_client_raises_on_missing_api_key(
        self,
        mock_requests_get: MagicMock,
        test_base_url: str,
    ) -> None:
        """Test que el cliente lanza excepción cuando el API requiere key y no se provee."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        mock_requests_get.return_value = mock_response

        client = TechAuraClient(base_url=test_base_url, api_key="")

        with pytest.raises(requests.HTTPError) as exc_info:
            client.get_pending_orders()
        assert "403" in str(exc_info.value)

    def test_client_handles_connection_timeout(
        self,
        mock_requests_get: MagicMock,
        test_base_url: str,
    ) -> None:
        """Test que el cliente maneja timeout de conexión."""
        mock_requests_get.side_effect = requests.Timeout("Connection timed out")

        client = TechAuraClient(base_url=test_base_url, api_key="test-key")

        with pytest.raises(requests.Timeout):
            client.get_pending_orders()

    def test_client_handles_server_unreachable(
        self,
        mock_requests_get: MagicMock,
        test_base_url: str,
    ) -> None:
        """Test que el cliente maneja servidor inalcanzable."""
        mock_requests_get.side_effect = requests.ConnectionError(
            "Failed to establish a new connection"
        )

        client = TechAuraClient(base_url=test_base_url, api_key="test-key")

        with pytest.raises(requests.ConnectionError):
            client.get_pending_orders()


class TestGetPendingOrders:
    """Tests para el método get_pending_orders."""

    def test_returns_empty_list_when_no_orders(
        self,
        mock_requests_get: MagicMock,
        empty_orders_response: dict[str, Any],
    ) -> None:
        """Test que retorna lista vacía cuando no hay órdenes."""
        mock_response = MagicMock()
        mock_response.json.return_value = empty_orders_response
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        client = TechAuraClient()
        orders = client.get_pending_orders()

        assert orders == []
        assert isinstance(orders, list)

    def test_returns_list_of_usb_orders(
        self,
        mock_requests_get: MagicMock,
        sample_orders_response: dict[str, Any],
    ) -> None:
        """Test que retorna lista de objetos USBOrder."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_orders_response
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        client = TechAuraClient()
        orders = client.get_pending_orders()

        assert len(orders) == 1
        assert isinstance(orders[0], USBOrder)

    def test_parses_order_fields_correctly(
        self,
        mock_requests_get: MagicMock,
        sample_order_data: dict[str, Any],
    ) -> None:
        """Test que parsea todos los campos de la orden correctamente."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"orders": [sample_order_data]}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        client = TechAuraClient()
        orders = client.get_pending_orders()
        order = orders[0]

        assert order.order_id == sample_order_data["order_id"]
        assert order.order_number == sample_order_data["order_number"]
        assert order.customer_phone == sample_order_data["customer_phone"]
        assert order.customer_name == sample_order_data["customer_name"]
        assert order.product_type == sample_order_data["product_type"]
        assert order.capacity == sample_order_data["capacity"]
        assert order.genres == sample_order_data["genres"]
        assert order.artists == sample_order_data["artists"]
        assert order.videos == sample_order_data["videos"]
        assert order.movies == sample_order_data["movies"]
        assert order.created_at == sample_order_data["created_at"]
        assert order.status == sample_order_data["status"]

    def test_handles_multiple_orders(
        self,
        mock_requests_get: MagicMock,
        sample_order_data: dict[str, Any],
    ) -> None:
        """Test que maneja múltiples órdenes en una respuesta."""
        # Simulando múltiples órdenes que podrían venir de paginación
        order1 = sample_order_data.copy()
        order1["order_id"] = "order-001"
        order2 = sample_order_data.copy()
        order2["order_id"] = "order-002"
        order3 = sample_order_data.copy()
        order3["order_id"] = "order-003"

        mock_response = MagicMock()
        mock_response.json.return_value = {"orders": [order1, order2, order3]}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        client = TechAuraClient()
        orders = client.get_pending_orders()

        assert len(orders) == 3
        assert orders[0].order_id == "order-001"
        assert orders[1].order_id == "order-002"
        assert orders[2].order_id == "order-003"

    def test_handles_malformed_response_gracefully(
        self,
        mock_requests_get: MagicMock,
    ) -> None:
        """Test que maneja respuestas malformadas sin valores esperados."""
        # Respuesta con campos faltantes
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "orders": [
                {
                    "order_id": "partial-order",
                    "order_number": "ORD-PARTIAL",
                    "customer_phone": "",
                    "customer_name": "",
                    "product_type": "",
                    "capacity": "",
                    # Faltan: genres, artists, videos, movies, created_at, status
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        client = TechAuraClient()
        orders = client.get_pending_orders()

        assert len(orders) == 1
        order = orders[0]
        assert order.order_id == "partial-order"
        assert order.genres == []
        assert order.artists == []
        assert order.videos == []
        assert order.movies == []
        assert order.created_at == ""
        assert order.status == ""


class TestStartBurning:
    """Tests para el método start_burning."""

    def test_returns_true_on_success(
        self,
        mock_requests_post: MagicMock,
        success_response_data: dict[str, Any],
    ) -> None:
        """Test que retorna True cuando se inicia la grabación exitosamente."""
        mock_response = MagicMock()
        mock_response.json.return_value = success_response_data
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()
        result = client.start_burning("order-123")

        assert result is True
        mock_requests_post.assert_called_once()
        call_url = mock_requests_post.call_args[0][0]
        assert "order-123" in call_url
        assert "start-burning" in call_url

    def test_returns_false_on_invalid_order(
        self,
        mock_requests_post: MagicMock,
        failure_response_data: dict[str, Any],
    ) -> None:
        """Test que retorna False con orden inválida."""
        mock_response = MagicMock()
        mock_response.json.return_value = failure_response_data
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()
        result = client.start_burning("invalid-order-id")

        assert result is False

    def test_handles_already_burning_order(
        self,
        mock_requests_post: MagicMock,
    ) -> None:
        """Test que maneja orden que ya está en proceso de grabación."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "error": "Order already in burning state",
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()
        result = client.start_burning("already-burning-order")

        assert result is False

    def test_succeeds_after_previous_failure(
        self,
        mock_requests_post: MagicMock,
        success_response_data: dict[str, Any],
    ) -> None:
        """Test que puede tener éxito después de un fallo previo."""
        # Primer intento falla con error temporal
        failure_response = MagicMock()
        failure_response.raise_for_status.side_effect = requests.HTTPError(
            "503 Service Unavailable"
        )

        # Segundo intento exitoso
        success_response = MagicMock()
        success_response.json.return_value = success_response_data
        success_response.raise_for_status = MagicMock()

        mock_requests_post.side_effect = [failure_response, success_response]

        client = TechAuraClient()

        # Primer intento falla
        with pytest.raises(requests.HTTPError):
            client.start_burning("order-123")

        # Segundo intento tiene éxito
        result = client.start_burning("order-123")
        assert result is True


class TestCompleteBurning:
    """Tests para el método complete_burning."""

    def test_returns_true_on_success(
        self,
        mock_requests_post: MagicMock,
        success_response_data: dict[str, Any],
    ) -> None:
        """Test que retorna True cuando se completa la grabación exitosamente."""
        mock_response = MagicMock()
        mock_response.json.return_value = success_response_data
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()
        result = client.complete_burning("order-123")

        assert result is True
        mock_requests_post.assert_called_once()
        call_url = mock_requests_post.call_args[0][0]
        assert "order-123" in call_url
        assert "complete-burning" in call_url

    def test_returns_false_on_not_burning_order(
        self,
        mock_requests_post: MagicMock,
    ) -> None:
        """Test que retorna False cuando la orden no está en estado de grabación."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "error": "Order is not in burning state",
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()
        result = client.complete_burning("not-burning-order")

        assert result is False

    def test_completes_burning_endpoint(
        self,
        mock_requests_post: MagicMock,
        success_response_data: dict[str, Any],
    ) -> None:
        """Test que verifica que se llama al endpoint correcto de complete-burning."""
        # El método actual no soporta notas, pero verificamos la llamada base
        mock_response = MagicMock()
        mock_response.json.return_value = success_response_data
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()
        result = client.complete_burning("order-123")

        assert result is True
        # Verificamos que se llamó al endpoint correcto
        call_url = mock_requests_post.call_args[0][0]
        assert "/api/usb-integration/orders/order-123/complete-burning" in call_url


class TestReportError:
    """Tests para el método report_error."""

    def test_returns_true_on_success(
        self,
        mock_requests_post: MagicMock,
        success_response_data: dict[str, Any],
    ) -> None:
        """Test que retorna True cuando se reporta el error exitosamente."""
        mock_response = MagicMock()
        mock_response.json.return_value = success_response_data
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()
        result = client.report_error("order-123", "USB not detected")

        assert result is True
        mock_requests_post.assert_called_once()
        call_kwargs = mock_requests_post.call_args[1]
        assert call_kwargs["json"] == {"error_message": "USB not detected"}

    def test_sends_error_code_and_retryable_flag(
        self,
        mock_requests_post: MagicMock,
        success_response_data: dict[str, Any],
    ) -> None:
        """Test que envía el mensaje de error correctamente."""
        mock_response = MagicMock()
        mock_response.json.return_value = success_response_data
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()
        error_message = "ERR_USB_WRITE_FAILED: Disk write error - retryable"
        result = client.report_error("order-123", error_message)

        assert result is True
        call_kwargs = mock_requests_post.call_args[1]
        assert call_kwargs["json"]["error_message"] == error_message

    def test_handles_very_long_error_messages(
        self,
        mock_requests_post: MagicMock,
        success_response_data: dict[str, Any],
    ) -> None:
        """Test que maneja mensajes de error muy largos."""
        mock_response = MagicMock()
        mock_response.json.return_value = success_response_data
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()
        # Mensaje de error muy largo (5000 caracteres)
        long_error_message = "Error: " + "x" * 4993
        result = client.report_error("order-123", long_error_message)

        assert result is True
        call_kwargs = mock_requests_post.call_args[1]
        assert call_kwargs["json"]["error_message"] == long_error_message
        assert len(call_kwargs["json"]["error_message"]) == 5000


class TestErrorHandling:
    """Tests para manejo de errores HTTP."""

    def test_handles_500_server_error(
        self,
        mock_requests_get: MagicMock,
    ) -> None:
        """Test que maneja error 500 del servidor."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "500 Internal Server Error"
        )
        mock_requests_get.return_value = mock_response

        client = TechAuraClient()

        with pytest.raises(requests.HTTPError) as exc_info:
            client.get_pending_orders()
        assert "500" in str(exc_info.value)

    def test_handles_503_service_unavailable(
        self,
        mock_requests_post: MagicMock,
    ) -> None:
        """Test que maneja error 503 de servicio no disponible."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "503 Service Unavailable"
        )
        mock_requests_post.return_value = mock_response

        client = TechAuraClient()

        with pytest.raises(requests.HTTPError) as exc_info:
            client.start_burning("order-123")
        assert "503" in str(exc_info.value)

    def test_handles_rate_limiting_429(
        self,
        mock_requests_get: MagicMock,
    ) -> None:
        """Test que maneja error 429 de rate limiting."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "429 Too Many Requests"
        )
        mock_requests_get.return_value = mock_response

        client = TechAuraClient()

        with pytest.raises(requests.HTTPError) as exc_info:
            client.get_pending_orders()
        assert "429" in str(exc_info.value)

    def test_handles_network_errors(
        self,
        mock_requests_post: MagicMock,
    ) -> None:
        """Test que maneja errores de red."""
        mock_requests_post.side_effect = requests.ConnectionError(
            "Network is unreachable"
        )

        client = TechAuraClient()

        with pytest.raises(requests.ConnectionError):
            client.complete_burning("order-123")
