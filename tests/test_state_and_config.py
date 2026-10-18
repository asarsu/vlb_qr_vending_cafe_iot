"""
tests/test_state_and_config.py
==============================
Pruebas unitarias para AppConfig, VendingState y TouchHitboxManager.
"""

import unittest
from src.config.settings import AppConfig
from src.core.state import VendingState
from src.core.coordinator import TouchHitboxManager


class TestStateAndConfig(unittest.TestCase):

    def test_app_config_defaults(self):
        config = AppConfig()
        self.assertEqual(config.screen_w, 480)
        self.assertEqual(config.screen_h, 800)
        self.assertEqual(config.monto_inicial_bs, 5.00)
        self.assertEqual(config.webhook_port, 5000)

    def test_vending_state_thread_safety(self):
        state = VendingState()
        self.assertEqual(state.get_estado(), "BIENVENIDA")
        state.set_estado("INSTRUCCIONES")
        self.assertEqual(state.get_estado(), "INSTRUCCIONES")
        state.set_estado("ERROR_CONEXION_BANCO")
        self.assertEqual(state.get_estado(), "ERROR_CONEXION_BANCO")

    def test_touch_hitbox_buttons(self):
        # Botón Volver: (10 <= tx <= 110) and (130 <= ty <= 260)
        self.assertTrue(TouchHitboxManager.es_boton_volver(50, 200))
        self.assertFalse(TouchHitboxManager.es_boton_volver(200, 200))

        # Botón Comprar: (10 <= tx <= 110) and (500 <= ty <= 630)
        self.assertTrue(TouchHitboxManager.es_boton_comprar(50, 550))
        self.assertFalse(TouchHitboxManager.es_boton_comprar(50, 300))


if __name__ == "__main__":
    unittest.main()
