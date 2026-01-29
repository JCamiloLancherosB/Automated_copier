"""Cliente para comunicación con TechAura Chatbot API."""

import os
from dataclasses import dataclass, field
from typing import Optional

import requests


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


class TechAuraClient:
    """Cliente para comunicación con TechAura Chatbot API."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        """Inicializa el cliente de TechAura.

        Args:
            base_url: URL base del API de TechAura.
            api_key: Clave de API para autenticación.
        """
        self.base_url = base_url or os.getenv("TECHAURA_API_URL", "http://localhost:3006")
        self.api_key = api_key or os.getenv("TECHAURA_API_KEY", "")
        self.timeout = 30

    def _get_headers(self) -> dict[str, str]:
        """Obtener headers para las peticiones HTTP."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get_pending_orders(self) -> list[USBOrder]:
        """Obtener pedidos pendientes de grabación.

        Returns:
            Lista de órdenes USB pendientes de grabación.

        Raises:
            requests.RequestException: Si hay error en la comunicación con el API.
        """
        url = f"{self.base_url}/api/orders/pending"
        response = requests.get(url, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()

        orders = []
        data = response.json()
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
        return orders

    def start_burning(self, order_id: str) -> bool:
        """Marcar pedido como en proceso de grabación.

        Args:
            order_id: ID del pedido a marcar.

        Returns:
            True si se marcó exitosamente, False en caso contrario.

        Raises:
            requests.RequestException: Si hay error en la comunicación con el API.
        """
        url = f"{self.base_url}/api/orders/{order_id}/start-burning"
        response = requests.post(url, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("success", False)

    def complete_burning(self, order_id: str) -> bool:
        """Marcar pedido como grabación completada.

        Args:
            order_id: ID del pedido a marcar como completado.

        Returns:
            True si se marcó exitosamente, False en caso contrario.

        Raises:
            requests.RequestException: Si hay error en la comunicación con el API.
        """
        url = f"{self.base_url}/api/orders/{order_id}/complete-burning"
        response = requests.post(url, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("success", False)

    def report_error(self, order_id: str, error_message: str) -> bool:
        """Reportar error en grabación.

        Args:
            order_id: ID del pedido con error.
            error_message: Mensaje describiendo el error.

        Returns:
            True si se reportó exitosamente, False en caso contrario.

        Raises:
            requests.RequestException: Si hay error en la comunicación con el API.
        """
        url = f"{self.base_url}/api/orders/{order_id}/report-error"
        payload = {"error_message": error_message}
        response = requests.post(
            url, headers=self._get_headers(), json=payload, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json().get("success", False)
