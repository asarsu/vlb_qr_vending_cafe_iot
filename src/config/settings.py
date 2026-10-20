"""
src/config/settings.py
======================
Configuración centralizada de la aplicación Kiosco QR Vending.
Permite sobreescribir valores mediante variables de entorno para despliegue flexible.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    # Dimensiones de pantalla
    screen_w: int = int(os.getenv("SCREEN_W", "480"))
    screen_h: int = int(os.getenv("SCREEN_H", "800"))

    # API BISA / SIP
    bisa_base_url: str = os.getenv("BISA_BASE_URL", "https://dev-sip.mc4.com.bo:8443")
    api_key_auth: str = os.getenv("BISA_API_KEY_AUTH", "")
    username: str = os.getenv("BISA_USERNAME", "")
    password: str = os.getenv("BISA_PASSWORD", "")
    apikey_servicio: str = os.getenv("BISA_APIKEY_SERVICIO", "")
    webhook_callback_url: str = os.getenv("WEBHOOK_CALLBACK_URL", "https://qr01.vendingbolivia.com/api/pagos/callback")
    webhook_port: int = int(os.getenv("WEBHOOK_PORT", "5000"))
    webhook_secret_token: str = os.getenv("WEBHOOK_SECRET_TOKEN", "")

    # MDB / Serial
    serial_port: str = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
    serial_baudrate: int = int(os.getenv("SERIAL_BAUDRATE", "9600"))
    serial_timeout: float = float(os.getenv("SERIAL_TIMEOUT", "0.1"))

    # Parámetros operativos
    monto_inicial_bs: float = float(os.getenv("MONTO_INICIAL_BS", "5.00"))
    timeout_pago_segundos: int = int(os.getenv("TIMEOUT_PAGO_SEGUNDOS", "180"))
    timeout_vmc_segundos: int = int(os.getenv("TIMEOUT_VMC_SEGUNDOS", "120"))

    # Rutas relativas del proyecto
    base_dir: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    logs_dir: str = os.path.join(base_dir, "logs")
    logo_path: str = os.path.join(base_dir, "public", "logo-vlb-square-noBg.png")
    qr_icon_path: str = os.path.join(base_dir, "public", "qr_img2.png")
