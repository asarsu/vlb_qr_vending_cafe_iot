"""
tests/test_security_critical.py
===============================
Pruebas de seguridad para las mitigaciones de riesgos críticos:
1. Validación estricta de alias y estado en coordinator.on_webhook_pago_recibido.
2. Autenticación y rechazo de payloads no autorizados en WebhookServer.
"""

import unittest
from unittest.mock import MagicMock
from src.config.settings import AppConfig
from src.core.state import VendingState
from src.core.coordinator import VendingCoordinator
from src.payment.webhook_server import WebhookServer


class TestSecurityCritical(unittest.TestCase):

    def setUp(self):
        self.config = AppConfig(
            webhook_secret_token="token_super_secreto_123"
        )
        self.state = VendingState()
        self.bisa_client = MagicMock()
        self.serial_driver = MagicMock()
        self.log_manager = MagicMock()
        self.coordinator = VendingCoordinator(
            config=self.config,
            state=self.state,
            bisa_client=self.bisa_client,
            serial_driver=self.serial_driver,
            log_manager=self.log_manager,
        )

    def test_webhook_rejected_when_not_in_mostrando_state(self):
        """No debe aprobar pagos si la máquina está en BIENVENIDA u otro estado."""
        self.state.set_estado("BIENVENIDA")
        self.state.alias_actual = "VEND_100"

        aceptado = self.coordinator.on_webhook_pago_recibido("VEND_100")
        self.assertFalse(aceptado)
        self.assertFalse(self.state.pago_confirmado_flag)

    def test_webhook_rejected_when_alias_mismatches(self):
        """No debe aprobar pagos si el alias enviado no coincide exactamente con el activo."""
        self.state.set_estado("MOSTRANDO")
        self.state.alias_actual = "VEND_100"

        aceptado = self.coordinator.on_webhook_pago_recibido("VEND_OTRO_200")
        self.assertFalse(aceptado)
        self.assertFalse(self.state.pago_confirmado_flag)

    def test_webhook_rejected_when_no_active_session_alias(self):
        """No debe aprobar si no hay sesión activa (alias_actual es None)."""
        self.state.set_estado("MOSTRANDO")
        self.state.alias_actual = None

        aceptado = self.coordinator.on_webhook_pago_recibido("VEND_100")
        self.assertFalse(aceptado)
        self.assertFalse(self.state.pago_confirmado_flag)

    def test_webhook_approved_when_matching_active_session(self):
        """Debe aprobar únicamente si está en MOSTRANDO y coincide el alias."""
        self.state.set_estado("MOSTRANDO")
        self.state.alias_actual = "VEND_100"

        aceptado = self.coordinator.on_webhook_pago_recibido("VEND_100")
        self.assertTrue(aceptado)
        self.assertTrue(self.state.pago_confirmado_flag)

    def test_webhook_server_authentication_and_routing(self):
        """Verifica que el servidor Flask rechace peticiones sin autenticación o con alias erróneo."""
        from src.payment.webhook_server import FLASK_DISPONIBLE
        if not FLASK_DISPONIBLE:
            self.skipTest("Flask no está instalado en este entorno local de desarrollo")

        callback_mock = MagicMock(return_value=True)
        server = WebhookServer(
            port=5000,
            on_payment_callback=callback_mock,
            secret_token="token_secreto_xyz"
        )
        client = server.app.test_client()

        # 1. Petición sin token -> 401
        res = client.post("/api/pagos/callback", json={"alias": "VEND_1"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json().get("codigo"), "9999")
        callback_mock.assert_not_called()

        # 2. Petición con token incorrecto -> 401
        res = client.post("/api/pagos/callback?token=invalido", json={"alias": "VEND_1"})
        self.assertEqual(res.status_code, 401)
        callback_mock.assert_not_called()

        # 3. Petición con token correcto en query param pero sin alias -> 400
        res = client.post("/api/pagos/callback?token=token_secreto_xyz", json={})
        self.assertEqual(res.status_code, 400)
        callback_mock.assert_not_called()

        # 4. Petición con token correcto en Header X-Webhook-Token y alias válido -> 200
        res = client.post(
            "/api/pagos/callback",
            headers={"X-Webhook-Token": "token_secreto_xyz"},
            json={"alias": "VEND_1"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json().get("codigo"), "0000")
        callback_mock.assert_called_with("VEND_1")


if __name__ == "__main__":
    unittest.main()
