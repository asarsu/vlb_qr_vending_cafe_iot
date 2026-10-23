"""
src/config/settings.py
======================
Configuración centralizada de la aplicación Kiosco QR Vending.
Permite sobreescribir valores mediante variables de entorno para despliegue flexible.
"""

import os
from dataclasses import dataclass


def _cargar_env_local():
    """Carga variables desde .env si existe, sin requerir librerías externas como python-dotenv."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env_path = os.path.join(base_dir, ".env")
    if os.path.isfile(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.split("#", 1)[0].strip()
                    if v.startswith('"') and v.endswith('"'):
                        v = v[1:-1]
                    elif v.startswith("'") and v.endswith("'"):
                        v = v[1:-1]
                    if k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


_cargar_env_local()


def _get_clean_env(key: str, default: str = "") -> str:
    """Obtiene variable de entorno eliminando comentarios inline (#...) y espacios."""
    val = os.getenv(key, default)
    if val is None:
        return default
    # Cortar comentarios inline si existen
    if "#" in val:
        val = val.split("#", 1)[0]
    return val.strip()


@dataclass(frozen=True)
class AppConfig:
    # Entorno operativo (0 = producción / quiosco seguro, 1 = desarrollo local)
    dev_mode: bool = _get_clean_env("DEV_MODE", "0").lower() in ("1", "true", "yes")

    # Dimensiones de pantalla
    screen_w: int = int(_get_clean_env("SCREEN_W", "480"))
    screen_h: int = int(_get_clean_env("SCREEN_H", "800"))

    # API BISA / SIP
    bisa_base_url: str = _get_clean_env("BISA_BASE_URL", "https://dev-sip.mc4.com.bo:8443")
    api_key_auth: str = _get_clean_env("BISA_API_KEY_AUTH", "")
    username: str = _get_clean_env("BISA_USERNAME", "")
    password: str = _get_clean_env("BISA_PASSWORD", "")
    apikey_servicio: str = _get_clean_env("BISA_APIKEY_SERVICIO", "")
    webhook_callback_url: str = _get_clean_env("WEBHOOK_CALLBACK_URL", "https://qr01.vendingbolivia.com/api/pagos/callback")
    webhook_port: int = int(_get_clean_env("WEBHOOK_PORT", "5000"))
    webhook_secret_token: str = _get_clean_env("WEBHOOK_SECRET_TOKEN", "")

    # MDB / Serial
    serial_port: str = _get_clean_env("SERIAL_PORT", "/dev/ttyUSB0")
    serial_baudrate: int = int(_get_clean_env("SERIAL_BAUDRATE", "9600"))
    serial_timeout: float = float(_get_clean_env("SERIAL_TIMEOUT", "0.1"))

    # Parámetros operativos
    monto_inicial_bs: float = float(_get_clean_env("MONTO_INICIAL_BS", "5.00"))
    timeout_pago_segundos: int = int(_get_clean_env("TIMEOUT_PAGO_SEGUNDOS", "180"))
    timeout_vmc_segundos: int = int(_get_clean_env("TIMEOUT_VMC_SEGUNDOS", "120"))
    detalle_glosa: str = _get_clean_env("DETALLE_GLOSA", "Vending Cafe Concerto")

    # Rutas relativas del proyecto
    base_dir: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    logs_dir: str = os.path.join(base_dir, "logs")
    logo_path: str = os.path.join(base_dir, "public", "logo-vlb-square-noBg.png")
    qr_icon_path: str = os.path.join(base_dir, "public", "qr_img2.png")
