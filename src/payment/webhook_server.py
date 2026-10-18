"""
src/payment/webhook_server.py
=============================
Servidor Flask desacoplado que notifica confirmaciones de pago en segundo plano.
"""

import threading
from typing import Callable

try:
    from flask import Flask, request as flask_request, jsonify
    FLASK_DISPONIBLE = True
except ImportError:
    FLASK_DISPONIBLE = False


class WebhookServer:
    """Servidor Flask desacoplado que notifica confirmaciones de pago en segundo plano."""

    def __init__(self, port: int, on_payment_callback: Callable[[str], None]):
        self.port = port
        self.on_payment_callback = on_payment_callback
        if FLASK_DISPONIBLE:
            self.app = Flask("WebhookServer")
            self._setup_routes()
        else:
            self.app = None

    def _setup_routes(self):
        @self.app.route("/api/pagos/callback", methods=["POST"])
        def callback():
            datos = flask_request.get_json(silent=True) or {}
            print(f"\n[WEBHOOK RECIBIDO]: {datos}")
            alias = datos.get("alias", "")
            self.on_payment_callback(alias)
            # Respuesta 0000 requerida formalmente por BISA/SIP
            return jsonify({"codigo": "0000", "mensaje": "Registro exitoso"}), 200

    def iniciar(self):
        if not FLASK_DISPONIBLE:
            print(f"[WARN] Flask no está instalado. Webhook no iniciado en puerto {self.port}.")
            return
        print(f"[INFO] Servidor Webhook listo en http://127.0.0.1:{self.port} ...")
        threading.Thread(
            target=lambda: self.app.run(host="127.0.0.1", port=self.port, debug=False, use_reloader=False),
            daemon=True
        ).start()
