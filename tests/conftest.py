"""Fixtures compartidas para tests del cliente TechAura."""

from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest


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
def sample_order_data() -> dict[str, Any]:
    """Fixture que proporciona datos de ejemplo para una orden."""
    return {
        "order_id": "order-123",
        "order_number": "ORD-001",
        "customer_phone": "+573001234567",
        "customer_name": "Juan Pérez",
        "product_type": "music",
        "capacity": "16GB",
        "genres": ["salsa", "merengue"],
        "artists": ["Marc Anthony", "Juan Luis Guerra"],
        "videos": [],
        "movies": [],
        "created_at": "2024-01-15T10:30:00Z",
        "status": "pending",
    }


@pytest.fixture
def sample_orders_response(sample_order_data: dict[str, Any]) -> dict[str, Any]:
    """Fixture que proporciona una respuesta de ejemplo con órdenes."""
    return {"orders": [sample_order_data]}


@pytest.fixture
def empty_orders_response() -> dict[str, Any]:
    """Fixture que proporciona una respuesta vacía de órdenes."""
    return {"orders": []}


@pytest.fixture
def success_response_data() -> dict[str, Any]:
    """Fixture que proporciona una respuesta de éxito."""
    return {"success": True}


@pytest.fixture
def failure_response_data() -> dict[str, Any]:
    """Fixture que proporciona una respuesta de fallo."""
    return {"success": False}


@pytest.fixture
def valid_api_key() -> str:
    """Fixture que proporciona una API key válida."""
    return "test-valid-api-key-12345"


@pytest.fixture
def test_base_url() -> str:
    """Fixture que proporciona una URL base de prueba."""
    return "http://test.api.techaura.com"
