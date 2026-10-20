"""
src/app.py
==========
Factoría y ensamblador principal de la aplicación Kiosco QR Vending.
Implementa Inyección de Dependencias (Dependency Injection) para
componer el hardware, la lógica de negocio, los servicios de pago y la UI.
"""

import sys

try:
    import tkinter as tk
    TKINTER_DISPONIBLE = True
except ImportError:
    TKINTER_DISPONIBLE = False

from src.config.settings import AppConfig
from src.core.state import VendingState
from src.core.coordinator import VendingCoordinator
from src.logging_utils.logger import LogManager
from src.hardware.serial_driver import SerialMdbDriver
from src.payment.bisa_client import BisaApiClient
from src.payment.webhook_server import WebhookServer
from src.ui.vending_ui import VendingUI


class VendingApplication:
    """Clase principal de aplicación que gestiona el ciclo de vida completo."""

    def __init__(self, config: AppConfig = None):
        self.config = config or AppConfig()
        self.log_manager = LogManager(self.config.logs_dir)
        self.state = VendingState(
            monto_actual=self.config.monto_inicial_bs,
            credito_disponible=self.config.monto_inicial_bs,
        )

        # 1. Driver de hardware MDB
        self.serial_driver = SerialMdbDriver(
            port=self.config.serial_port,
            baudrate=self.config.serial_baudrate,
            timeout=self.config.serial_timeout,
        )

        # 2. Cliente de pagos Banco BISA
        self.bisa_client = BisaApiClient(self.config)

        # 3. Coordinador de casos de uso (Lógica de negocio)
        self.coordinator = VendingCoordinator(
            config=self.config,
            state=self.state,
            bisa_client=self.bisa_client,
            serial_driver=self.serial_driver,
            log_manager=self.log_manager,
        )

        # 4. Servidor Webhook Flask para notificaciones push de pagos
        self.webhook_server = WebhookServer(
            port=self.config.webhook_port,
            on_payment_callback=self.coordinator.on_webhook_pago_recibido,
            secret_token=self.config.webhook_secret_token,
        )

        # 5. Interfaz de usuario Tkinter
        self.root = None
        self.ui = None

    def start(self):
        """Inicia todos los subsistemas y arranca el bucle de eventos."""
        print("[APP] Iniciando Kiosco QR Vending (v2.0 Modular)...")

        # Iniciar conexión serial
        self.serial_driver.conectar()

        # Iniciar servidor webhook
        self.webhook_server.iniciar()

        # Si no hay Tkinter disponible (e.g. entorno headless o terminal)
        if not TKINTER_DISPONIBLE:
            print("[WARN] Tkinter no está disponible en este entorno. Corriendo en modo headless...")
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                self.serial_driver.cerrar()
            return

        # Iniciar UI
        self.root = tk.Tk()
        self.ui = VendingUI(
            root=self.root,
            config=self.config,
            state=self.state,
            on_touch_cb=self.coordinator.on_touch,
        )

        try:
            self.ui.renderizar()
            self.root.mainloop()
        finally:
            self.serial_driver.cerrar()
            print("[APP] Aplicación finalizada limpiamente.")


def create_app(config: AppConfig = None) -> VendingApplication:
    """Helper para crear una instancia configurada de la aplicación."""
    return VendingApplication(config=config)
