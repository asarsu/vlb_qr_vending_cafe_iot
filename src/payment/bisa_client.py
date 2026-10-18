"""
src/payment/bisa_client.py
==========================
Cliente para la API de Pagos QR de Banco BISA / SIP (MC4).
"""

import time
import json
import datetime
import threading
from typing import Optional, Tuple
import requests

from src.config.settings import AppConfig


class BisaApiClient:
    """Gestiona la autenticación, generación de códigos QR y polling de transacciones."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._token: Optional[str] = None
        self._lock = threading.Lock()

    def obtener_token(self) -> bool:
        url = f"{self.config.bisa_base_url}/autenticacion/v1/generarToken"
        headers = {
            "apikey": self.config.api_key_auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "username": str(self.config.username),
            "password": str(self.config.password),
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            print(f"[API TOKEN] Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("codigo") == "OK":
                    with self._lock:
                        self._token = data["objeto"]["token"]
                    print("[API] Token Bearer obtenido exitosamente.")
                    return True
        except Exception as e:
            print(f"[API ERROR] Falla obteniendo token: {e}")
        return False

    def generar_qr(self, monto: float) -> Tuple[Optional[str], Optional[str]]:
        """Genera el código QR. Retorna (base64_imagen, alias_generado)."""
        if not self._token:
            if not self.obtener_token():
                return None, None

        url = f"{self.config.bisa_base_url}/api/v1/generaQr"
        headers = {
            "apikeyServicio": self.config.apikey_servicio,
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        alias_dinamico = f"VEND_{int(time.time())}"
        vencimiento = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%d/%m/%Y")

        payload = {
            "monto": monto,
            "moneda": "BOB",
            "detalleGlosa": "Vending Snakky Univalle",
            "alias": alias_dinamico,
            "unicoUso": True,
            "fechaVencimiento": vencimiento,
            "tipoSolicitud": "API",
            "callback": self.config.webhook_callback_url,
        }

        try:
            print(f"[API QR] Solicitando QR para Bs {monto:.2f} | Alias: {alias_dinamico}")
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("codigo") == "0000":
                    return data["objeto"]["imagenQr"], alias_dinamico
                else:
                    print(f"[API QR] Error de servicio: {data.get('mensaje')}")
            elif resp.status_code == 401:
                print("[API QR] Token expirado, reintentando...")
                if self.obtener_token():
                    return self.generar_qr(monto)
        except Exception as e:
            print(f"[API ERROR] Error en generaQr: {e}")

        return None, None

    def consultar_estado(self, alias: str, bandera_pendiente: bool) -> Tuple[bool, bool]:
        """
        Consulta estadoTransaccion.
        Retorna (pago_confirmado, nuevo_valor_bandera_pendiente).
        """
        if not self._token:
            return False, bandera_pendiente

        url = f"{self.config.bisa_base_url}/api/v1/estadoTransaccion"
        headers = {
            "apikeyServicio": self.config.apikey_servicio,
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload = {"alias": alias}

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[API POLLING] estadoTransaccion: {data}")
                if data.get("codigo") == "0000":
                    obj = data.get("objeto") or {}
                    estado = obj.get("estadoActual")
                    if estado == "PENDIENTE":
                        return False, True
                    elif estado == "PAGADO":
                        return True, False
                elif data.get("codigo") == "9999":
                    if bandera_pendiente:
                        print("[API POLLING] Transición PENDIENTE -> 9999: ¡Pago aprobado!")
                        return True, False
            elif resp.status_code == 401:
                print("[API POLLING] Token vencido en polling.")
                self.obtener_token()
        except Exception as e:
            print(f"[API ERROR] Error en polling: {e}")

        return False, bandera_pendiente
