"""Tests para el cliente de TechAura."""

from unittest.mock import MagicMock, patch

import pytest

from mediacopier.api.techaura_client import TechAuraClient, USBOrder


class TestUSBOrder:
    """Tests para la dataclass USBOrder."""

    def test_usb_order_creation(self) -> None:
        """Test de creación de USBOrder con todos los campos."""
        order = USBOrder(
            order_id="123",
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
        assert order.order_id == "123"
        assert order.order_number == "ORD-001"
        assert order.customer_name == "Juan Pérez"
        assert order.product_type == "music"
        assert order.genres == ["salsa", "merengue"]
        assert order.artists == ["Marc Anthony", "Juan Luis Guerra"]

    def test_usb_order_default_values(self) -> None:
        """Test de valores por defecto en USBOrder."""
        order = USBOrder(
            order_id="456",
            order_number="ORD-002",
            customer_phone="+573009876543",
            customer_name="María García",
            product_type="videos",
            capacity="32GB",
        )
        assert order.genres == []
        assert order.artists == []
        assert order.videos == []
        assert order.movies == []
        assert order.created_at == ""
        assert order.status == ""


class TestTechAuraClient:
    """Tests para TechAuraClient."""

    def test_client_initialization_defaults(self) -> None:
        """Test de inicialización con valores por defecto."""
        client = TechAuraClient()
        assert client.base_url == "http://localhost:3006"
        assert client.api_key == ""
        assert client.timeout == 30

    def test_client_initialization_custom_values(self) -> None:
        """Test de inicialización con valores personalizados."""
        client = TechAuraClient(
            base_url="https://api.techaura.com", api_key="test-api-key"
        )
        assert client.base_url == "https://api.techaura.com"
        assert client.api_key == "test-api-key"

    def test_client_initialization_from_env(self) -> None:
        """Test de inicialización desde variables de entorno."""
        with patch.dict(
            "os.environ",
            {
                "TECHAURA_API_URL": "https://env.techaura.com",
                "TECHAURA_API_KEY": "env-api-key",
            },
        ):
            client = TechAuraClient()
            assert client.base_url == "https://env.techaura.com"
            assert client.api_key == "env-api-key"

    def test_get_headers_without_api_key(self) -> None:
        """Test de headers sin API key."""
        client = TechAuraClient(api_key="")
        headers = client._get_headers()
        assert headers == {"Content-Type": "application/json"}
        assert "Authorization" not in headers

    def test_get_headers_with_api_key(self) -> None:
        """Test de headers con API key."""
        client = TechAuraClient(api_key="my-secret-key")
        headers = client._get_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer my-secret-key"


class TestGetPendingOrders:
    """Tests para el método get_pending_orders."""

    @patch("mediacopier.api.techaura_client.requests.get")
    def test_get_pending_orders_success(self, mock_get: MagicMock) -> None:
        """Test de obtención exitosa de órdenes pendientes."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "orders": [
                {
                    "order_id": "order-123",
                    "order_number": "ORD-001",
                    "customer_phone": "+573001234567",
                    "customer_name": "Test User",
                    "product_type": "music",
                    "capacity": "16GB",
                    "genres": ["rock", "pop"],
                    "artists": ["Artist 1"],
                    "videos": [],
                    "movies": [],
                    "created_at": "2024-01-15T10:00:00Z",
                    "status": "pending",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = TechAuraClient(base_url="http://test.api")
        orders = client.get_pending_orders()

        assert len(orders) == 1
        assert orders[0].order_id == "order-123"
        assert orders[0].customer_name == "Test User"
        assert orders[0].genres == ["rock", "pop"]
        mock_get.assert_called_once()

    @patch("mediacopier.api.techaura_client.requests.get")
    def test_get_pending_orders_empty(self, mock_get: MagicMock) -> None:
        """Test de obtención de lista vacía de órdenes."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"orders": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = TechAuraClient()
        orders = client.get_pending_orders()

        assert orders == []

    @patch("mediacopier.api.techaura_client.requests.get")
    def test_get_pending_orders_connection_error(self, mock_get: MagicMock) -> None:
        """Test de manejo de error de conexión."""
        import requests

        mock_get.side_effect = requests.ConnectionError("Connection refused")

        client = TechAuraClient()
        with pytest.raises(requests.ConnectionError):
            client.get_pending_orders()

    @patch("mediacopier.api.techaura_client.requests.get")
    def test_get_pending_orders_http_error(self, mock_get: MagicMock) -> None:
        """Test de manejo de error HTTP."""
        import requests

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = mock_response

        client = TechAuraClient()
        with pytest.raises(requests.HTTPError):
            client.get_pending_orders()


class TestStartBurning:
    """Tests para el método start_burning."""

    @patch("mediacopier.api.techaura_client.requests.post")
    def test_start_burning_success(self, mock_post: MagicMock) -> None:
        """Test de marcado exitoso de inicio de grabación."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = TechAuraClient(base_url="http://test.api")
        result = client.start_burning("order-123")

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "order-123" in call_args[0][0]

    @patch("mediacopier.api.techaura_client.requests.post")
    def test_start_burning_failure(self, mock_post: MagicMock) -> None:
        """Test de fallo al marcar inicio de grabación."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = TechAuraClient()
        result = client.start_burning("order-456")

        assert result is False


class TestCompleteBurning:
    """Tests para el método complete_burning."""

    @patch("mediacopier.api.techaura_client.requests.post")
    def test_complete_burning_success(self, mock_post: MagicMock) -> None:
        """Test de marcado exitoso de grabación completada."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = TechAuraClient()
        result = client.complete_burning("order-123")

        assert result is True

    @patch("mediacopier.api.techaura_client.requests.post")
    def test_complete_burning_connection_error(self, mock_post: MagicMock) -> None:
        """Test de error de conexión al completar grabación."""
        import requests

        mock_post.side_effect = requests.ConnectionError()

        client = TechAuraClient()
        with pytest.raises(requests.ConnectionError):
            client.complete_burning("order-123")


class TestReportError:
    """Tests para el método report_error."""

    @patch("mediacopier.api.techaura_client.requests.post")
    def test_report_error_success(self, mock_post: MagicMock) -> None:
        """Test de reporte exitoso de error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = TechAuraClient()
        result = client.report_error("order-123", "USB not detected")

        assert result is True
        call_args = mock_post.call_args
        assert call_args[1]["json"] == {"error_message": "USB not detected"}

    @patch("mediacopier.api.techaura_client.requests.post")
    def test_report_error_http_error(self, mock_post: MagicMock) -> None:
        """Test de error HTTP al reportar error."""
        import requests

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_post.return_value = mock_response

        client = TechAuraClient()
        with pytest.raises(requests.HTTPError):
            client.report_error("invalid-order", "Error message")
