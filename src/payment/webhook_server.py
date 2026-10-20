"""
src/payment/webhook_server.py
=============================
Servidor Flask desacoplado que notifica confirmaciones de pago en segundo plano.
"""

import hmac
import threading
from typing import Callable, Optional

try:
    from flask import Flask, request as flask_request, jsonify
    FLASK_DISPONIBLE = True
except ImportError:
    FLASK_DISPONIBLE = False


class WebhookServer:
    """Servidor Flask desacoplado que notifica confirmaciones de pago en segundo plano."""

    def __init__(
        self,
        port: int,
        on_payment_callback: Callable[[str], bool],
        secret_token: Optional[str] = None
    ):
        self.port = port
        self.on_payment_callback = on_payment_callback
        self.secret_token = secret_token
        if FLASK_DISPONIBLE:
            self.app = Flask("WebhookServer")
            self._setup_routes()
        else:
            self.app = None

    def _validar_autenticacion(self) -> bool:
        """
        Valida la autenticidad de la petición entrante.
        Si hay un secret_token configurado:
          1. Verifica coincidencia segura en query param `?token=...`
          2. O en header `X-Webhook-Token: ...`
          3. O en header `Authorization: Bearer ...` o `Authorization: Basic ...`
        """
        if not self.secret_token:
            return True

        # 1. Query parameter ?token=...
        token_param = flask_request.args.get("token")
        if token_param and hmac.compare_digest(token_param, self.secret_token):
            return True

        # 2. Header X-Webhook-Token
        token_header = flask_request.headers.get("X-Webhook-Token")
        if token_header and hmac.compare_digest(token_header, self.secret_token):
            return True

        # 3. Header Authorization (Bearer o Basic token)
        auth_header = flask_request.headers.get("Authorization", "")
        if auth_header:
            if auth_header.startswith("Bearer "):
                token_val = auth_header[7:].strip()
                if hmac.compare_digest(token_val, self.secret_token):
                    return True
            elif auth_header.startswith("Basic "):
                token_val = auth_header[6:].strip()
                if hmac.compare_digest(token_val, self.secret_token):
                    return True

        return False

    def _setup_routes(self):
        @self.app.route("/api/pagos/callback", methods=["POST"])
        def callback():
            if not self._validar_autenticacion():
                print("[WEBHOOK SEGURIDAD] Rechazado: Petición sin autorización válida o token incorrecto.")
                return jsonify({"codigo": "9999", "mensaje": "No autorizado"}), 401

            datos = flask_request.get_json(silent=True) or {}
            print(f"\n[WEBHOOK RECIBIDO]: {datos}")

            alias = datos.get("alias", "")
            if not alias or not isinstance(alias, str):
                print("[WEBHOOK SEGURIDAD] Rechazado: Payload sin alias válido.")
                return jsonify({"codigo": "9999", "mensaje": "Alias requerido"}), 400

            aceptado = self.on_payment_callback(alias)
            if aceptado:
                return jsonify({"codigo": "0000", "mensaje": "Registro exitoso"}), 200
            else:
                return jsonify({"codigo": "9999", "mensaje": "Transaccion no valida o expirada"}), 400

    def iniciar(self):
        if not FLASK_DISPONIBLE:
            print(f"[WARN] Flask no está instalado. Webhook no iniciado en puerto {self.port}.")
            return
        print(f"[INFO] Servidor Webhook listo en http://127.0.0.1:{self.port} ...")
        threading.Thread(
            target=lambda: self.app.run(host="127.0.0.1", port=self.port, debug=False, use_reloader=False),
            daemon=True
        ).start()
