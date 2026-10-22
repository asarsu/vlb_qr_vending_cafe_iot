"""
src/core/coordinator.py
=======================
Orquestador principal y caso de uso del ciclo de compra.
Coordina hardware serial MDB, API de pagos, logs y máquina de estados.
"""

import time
import base64
import threading
from io import BytesIO
from typing import Optional

try:
    from PIL import Image, ImageTk
    PIL_DISPONIBLE = True
except ImportError:
    PIL_DISPONIBLE = False

from src.config.settings import AppConfig
from src.core.state import VendingState
from src.logging_utils.logger import LogManager
from src.hardware.serial_driver import SerialMdbDriver
from src.hardware.mdb_protocol import MdbSecurityController
from src.payment.bisa_client import BisaApiClient


class TouchHitboxManager:
    """Centraliza la calibración y detección táctil."""

    @staticmethod
    def es_boton_volver(tx: int, ty: int) -> bool:
        return (10 <= tx <= 110) and (130 <= ty <= 260)

    @staticmethod
    def es_boton_comprar(tx: int, ty: int) -> bool:
        return (10 <= tx <= 110) and (500 <= ty <= 630)


class VendingCoordinator:
    """Orquesta la máquina de estados, el flujo de pagos y la interacción con la VMC."""

    def __init__(
        self,
        config: AppConfig,
        state: VendingState,
        bisa_client: BisaApiClient,
        serial_driver: SerialMdbDriver,
        log_manager: LogManager,
    ):
        self.config = config
        self.state = state
        self.bisa_client = bisa_client
        self.serial_driver = serial_driver
        self.log_manager = log_manager

    def on_touch(self, tx: int, ty: int):
        estado = self.state.get_estado()
        print(f"[DEBUG TÁCTIL] Touch -> X: {tx}, Y: {ty} | Estado: {estado}")

        if estado == "BIENVENIDA":
            self.state.set_estado("INSTRUCCIONES")
        elif estado == "INSTRUCCIONES":
            if TouchHitboxManager.es_boton_volver(tx, ty):
                self.state.set_estado("BIENVENIDA")
            elif TouchHitboxManager.es_boton_comprar(tx, ty):
                self.state.set_estado("GENERANDO")
                threading.Thread(target=self.ejecutar_flujo_compra, daemon=True).start()

    def on_webhook_pago_recibido(self, alias_recibido: str) -> bool:
        """
        Valida que el callback recibido pertenezca a la compra en curso.
        Retorna True si fue aceptado, False si fue rechazado por no coincidir o estar fuera de sesión.
        """
        with self.state.lock:
            estado = self.state.estado_maquina
            alias_actual = self.state.alias_actual

            # Validar que exista un alias activo y que coincida exactamente
            if not alias_actual or alias_recibido != alias_actual:
                print(
                    f"[WEBHOOK SEGURIDAD] ¡DENEGADO! Alias recibido '{alias_recibido}' "
                    f"no coincide con la sesión activa '{alias_actual}'."
                )
                return False

            # Si ya se aprobó por polling y la máquina está despachando/entregando este mismo alias,
            # responder exitoso (idempotencia) para que el banco registre 200 OK
            if estado in ("DESPACHANDO", "ENTREGANDO"):
                print(f"[WEBHOOK] Alias {alias_recibido} ya en curso/despachando. Confirmación redundante aceptada.")
                return True

            # Validar que la máquina esté esperando el pago activamente
            if estado != "MOSTRANDO":
                print(f"[WEBHOOK SEGURIDAD] Rechazado: Máquina no está en estado MOSTRANDO (actual: {estado}).")
                return False

            print(f"[WEBHOOK] ¡Alias {alias_recibido} validado con éxito para sesión activa!")
            self.state.pago_confirmado_flag = True
            return True

    def ejecutar_flujo_compra(self):
        """Ciclo completo de compra: Generar QR -> Esperar Pago -> Inyectar MDB."""
        self.log_manager.iniciar_nuevo_ciclo()
        print("[FLUJO] Iniciando nuevo ciclo de compra...")

        with self.state.lock:
            monto = self.state.monto_actual
            self.state.pago_confirmado_flag = False
            self.state.codigo_producto_actual = None
            self.state.mensaje_alerta = ""

        b64_qr, alias = self.bisa_client.generar_qr(monto)

        if not b64_qr or not alias:
            print("[FLUJO] Fallo la generación de QR por conexión/servicio bancario. Mostrando pantalla de error.")
            self.log_manager.guardar_log_ciclo(motivo="fallo_generacion_qr", alias=alias or "sin_alias")
            self.state.set_estado("ERROR_CONEXION_BANCO")
            time.sleep(6.0)
            self.state.set_estado("BIENVENIDA")
            return

        # Decodificar imagen para UI
        try:
            if PIL_DISPONIBLE:
                img_bytes = base64.b64decode(b64_qr)
                img = Image.open(BytesIO(img_bytes)).resize((300, 300), Image.Resampling.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                with self.state.lock:
                    self.state.alias_actual = alias
                    self.state.imagen_qr_tk = img_tk
            else:
                with self.state.lock:
                    self.state.alias_actual = alias
                    self.state.imagen_qr_tk = None
        except Exception as e:
            print(f"[FLUJO ERROR] Error cargando imagen QR: {e}")
            self.state.set_estado("ERROR_CONEXION_BANCO")
            time.sleep(4.0)
            self.state.set_estado("BIENVENIDA")
            return

        self.state.set_estado("MOSTRANDO")
        pago_exitoso = self._esperar_pago(alias)

        if pago_exitoso:
            self.state.set_estado("DESPACHANDO")
            self._gestionar_sesion_vmc(monto)
        else:
            print("[FLUJO] Tiempo de espera de pago agotado.")
            self.log_manager.guardar_log_ciclo(motivo="timeout_espera_pago", alias=alias)
            self.state.set_estado("BIENVENIDA")

    def _esperar_pago(self, alias: str) -> bool:
        t_inicio = time.time()
        bandera_pendiente = False

        while (time.time() - t_inicio) < self.config.timeout_pago_segundos:
            if self.state.get_estado() != "MOSTRANDO":
                return False

            # Comprobar webhook
            with self.state.lock:
                if self.state.pago_confirmado_flag:
                    print("[FLUJO] Pago confirmado por Webhook.")
                    return True

            # Polling a la API de Bisa
            aprobado, bandera_pendiente = self.bisa_client.consultar_estado(alias, bandera_pendiente)
            if aprobado:
                print("[FLUJO] Pago confirmado por Polling.")
                return True

            time.sleep(1.0)

        return False

    def _gestionar_sesion_vmc(self, monto_inicial: float):
        """Controlador de máquina de estados MDB con candado de seguridad."""
        self.serial_driver.limpiar_buffer()

        with self.state.lock:
            self.state.credito_disponible = float(monto_inicial)
            self.state.mensaje_alerta = ""
            self.state.codigo_producto_actual = None
            self.state.precio_producto_actual = 0.0
            alias_ciclo = self.state.alias_actual or "sin_alias"

        trama_inicial = MdbSecurityController.calcular_trama_credito(monto_inicial)
        print(f"[MDB] Inyectando crédito Bs {monto_inicial:.2f} -> {trama_inicial}")
        self.serial_driver.enviar_hex(trama_inicial)

        print("[MDB] Esperando selección de producto en botonera VMC...")
        t_inicio = time.time()

        while (time.time() - t_inicio) < self.config.timeout_vmc_segundos:
            texto, hex_crudo, _ = self.serial_driver.leer_trama()

            if texto or hex_crudo:
                print(f"[VMC RAW] HEX: {hex_crudo} | ASCII: {texto}")

                # ── 1300: VEND REQUEST (Petición de venta) ──────────────
                if "1300" in texto or "1300" in hex_crudo:
                    cod, precio_bs, centavos_vmc = MdbSecurityController.parsear_vend_request(texto, hex_crudo)

                    with self.state.lock:
                        if cod:
                            self.state.codigo_producto_actual = cod
                        credito_actual = self.state.credito_disponible

                    # Candado de Seguridad Estricto:
                    # Si no se pudo decodificar el precio real de la trama 1300, denegar por seguridad
                    if centavos_vmc is None:
                        print(f"[MDB CANDADO ERROR] Trama 1300 corrupta o sin precio legible. ¡DENEGADO!")
                        self.serial_driver.enviar_hex("0606")  # Vend Denied
                        time.sleep(0.15)
                        self.serial_driver.enviar_hex("0707")
                        time.sleep(0.2)
                        trama_reset = MdbSecurityController.calcular_trama_credito(credito_actual)
                        self.serial_driver.enviar_hex(trama_reset)
                        with self.state.lock:
                            self.state.mensaje_alerta = "Error de comunicación con máquina.\nPor favor digita nuevamente."
                        continue

                    precio_en_centavos = centavos_vmc
                    precio_final = round(precio_en_centavos / 100.0, 2)
                    centavos_disponibles = int(round(credito_actual * 100))

                    with self.state.lock:
                        self.state.precio_producto_actual = precio_final

                    print(f"[MDB SEGURIDAD] Producto: #{cod} | Precio: Bs {precio_final:.2f} ({precio_en_centavos} cts) | Saldo: Bs {credito_actual:.2f} ({centavos_disponibles} cts)")

                    # El precio debe ser exactamente igual al monto abonado
                    if precio_en_centavos != centavos_disponibles:
                        if precio_en_centavos > centavos_disponibles:
                            print(f"[MDB CANDADO] ¡DENEGADO! Costo {precio_final:.2f} > Saldo {credito_actual:.2f}")
                            mensaje_error = (
                                f"¡Producto #{cod} cuesta Bs. {precio_final:.2f}!\n"
                                f"Tu saldo es: Bs. {credito_actual:.2f}\n"
                                f"Elige un producto de Bs. {credito_actual:.2f}"
                            )
                        else:
                            print(f"[MDB CANDADO] ¡DENEGADO! Costo {precio_final:.2f} < Saldo {credito_actual:.2f}")
                            mensaje_error = (
                                f"¡Producto #{cod} cuesta Bs. {precio_final:.2f}!\n"
                                f"Tu saldo es: Bs. {credito_actual:.2f}\n"
                                f"Debes elegir un producto de exactamente Bs. {credito_actual:.2f}"
                            )

                        self.serial_driver.enviar_hex("0606")  # Vend Denied
                        time.sleep(0.15)
                        self.serial_driver.enviar_hex("0707")  # Finalizar selección bloqueada
                        time.sleep(0.2)

                        # Reinyectar crédito disponible para permitir nueva selección
                        trama_reset = MdbSecurityController.calcular_trama_credito(credito_actual)
                        self.serial_driver.enviar_hex(trama_reset)

                        with self.state.lock:
                            self.state.mensaje_alerta = mensaje_error
                    else:
                        print(f"[MDB CANDADO] ¡APROBADO! Autorizando #{cod} con 0505 (Monto exacto: Bs. {precio_final:.2f})...")
                        with self.state.lock:
                            self.state.mensaje_alerta = ""
                        self.serial_driver.enviar_hex("0505")  # Vend Approve

                # ── 1302: VEND SUCCESS (Caída física exitosa) ───────────
                elif "1302" in texto or "1302" in hex_crudo:
                    with self.state.lock:
                        remanente = round(self.state.credito_disponible - self.state.precio_producto_actual, 2)
                        self.state.credito_disponible = max(0.0, remanente)
                        self.state.estado_maquina = "ENTREGANDO"
                        credito_restante = self.state.credito_disponible

                    print(f"[MDB] 1302 Vend Success. Remanente: Bs {credito_restante:.2f}")

                    # Si el crédito se agotó totalmente en esta entrega, cerrar ciclo inmediatamente con 0707
                    if credito_restante <= 0:
                        print("[MDB] Crédito totalmente utilizado tras 1302. Enviando 0707...")
                        time.sleep(0.3)
                        self.serial_driver.enviar_hex("0707")
                        time.sleep(4)
                        break

                # ── 1304: VEND SESSION COMPLETE ─────────────────────────
                elif "1304" in texto or "1304" in hex_crudo:
                    print("[MDB] VMC reporta ciclo completado (1304). Enviando 0707...")
                    self.serial_driver.enviar_hex("0707")
                    time.sleep(0.3)

                    with self.state.lock:
                        credito_restante = self.state.credito_disponible

                    if credito_restante > 0:
                        print(f"[MDB MULTI-VENTA] Reinyectando saldo remanente: Bs. {credito_restante:.2f}")
                        trama_rem = MdbSecurityController.calcular_trama_credito(credito_restante)
                        self.serial_driver.enviar_hex(trama_rem)

                        time.sleep(3)
                        with self.state.lock:
                            self.state.codigo_producto_actual = None
                            self.state.precio_producto_actual = 0.0
                            self.state.mensaje_alerta = ""
                            self.state.estado_maquina = "DESPACHANDO"
                        t_inicio = time.time()  # Reiniciar timeout para siguiente producto
                    else:
                        print("[MDB] Crédito totalmente utilizado.")
                        time.sleep(4)
                        break

                # ── 1301 / 1303: VEND CANCELLED / FAILED ────────────────
                elif any(c in texto or c in hex_crudo for c in ["1301", "1303"]):
                    print("[MDB] Venta cancelada o fallida en VMC (1301/1303).")
                    self.serial_driver.enviar_hex("0707")
                    break

            time.sleep(0.05)
        else:
            print("[MDB] Timeout esperando selección en VMC.")
            self.serial_driver.enviar_hex("0707")

        print("[MDB] Sesión VMC terminada. Volviendo a BIENVENIDA.")
        self.log_manager.guardar_log_ciclo(motivo="compra_finalizada", alias=alias_ciclo)

        with self.state.lock:
            self.state.pago_confirmado_flag = False
            self.state.codigo_producto_actual = None
            self.state.mensaje_alerta = ""
            self.state.credito_disponible = self.config.monto_inicial_bs
            self.state.set_estado("BIENVENIDA")
