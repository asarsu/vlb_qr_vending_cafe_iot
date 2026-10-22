"""
src/hardware/serial_driver.py
=============================
Encapsula la comunicación a bajo nivel con el adaptador Waferstar MDB.
"""

import time
import threading
from typing import Optional, Tuple

try:
    import serial
    SERIAL_DISPONIBLE = True
except ImportError:
    SERIAL_DISPONIBLE = False


class SerialMdbDriver:
    """Encapsula la comunicación a bajo nivel con el adaptador Waferstar MDB."""

    def __init__(self, port: str, baudrate: int, timeout: float = 0.1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional["serial.Serial"] = None
        self._rx_buffer = bytearray()
        self._io_lock = threading.Lock()

    def conectar(self, reintentos: int = 5, delay: float = 1.0) -> bool:
        if not SERIAL_DISPONIBLE:
            print("[SERIAL] pyserial no instalado. Operando en modo mock/simulado.")
            return False

        for intento in range(1, reintentos + 1):
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                print(f"[SERIAL] Puerto {self.port} abierto correctamente (intento {intento}/{reintentos}).")
                return True
            except Exception as e:
                self.ser = None
                if intento < reintentos:
                    print(f"[SERIAL] Intento {intento}/{reintentos} falló para {self.port}: {e}. Reintentando en {delay}s...")
                    time.sleep(delay)
                else:
                    print(f"[SERIAL] Advertencia: No se pudo abrir {self.port} tras {reintentos} intentos: {e}")
        return False

    def _asegurar_conexion(self) -> bool:
        """Intenta reconectar bajo demanda si el puerto no está activo."""
        if self.ser and self.ser.is_open:
            return True
        return self.conectar(reintentos=2, delay=0.5)

    def cerrar(self):
        with self._io_lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                    print("[SERIAL] Puerto cerrado limpiamente.")
                except Exception:
                    pass

    def enviar_hex(self, comando_hex: str):
        with self._io_lock:
            if not (self.ser and self.ser.is_open):
                self._asegurar_conexion()

            if self.ser and self.ser.is_open:
                try:
                    self.ser.write(bytes.fromhex(comando_hex))
                    time.sleep(0.1)
                except Exception as e:
                    print(f"[SERIAL ERROR] Error al escribir {comando_hex}: {e}")
                    # Si hubo error de pipe/desconexión, marcar para reconectar en el próximo ciclo
                    try:
                        self.ser.close()
                    except Exception:
                        pass
                    self.ser = None
            else:
                print(f"[SERIAL MOCK] Habría enviado: {comando_hex}")

    def limpiar_buffer(self):
        with self._io_lock:
            self._rx_buffer.clear()
            if self.ser and self.ser.is_open:
                try:
                    self.ser.reset_input_buffer()
                except Exception:
                    pass

    def leer_trama(self) -> Tuple[str, str, bytes]:
        """
        Lee bytes extrayendo tramas delimitadas por STX (0x02) y ETX (0x03).
        Retorna (texto_ascii, hex_str, raw_bytes).
        """
        with self._io_lock:
            if not (self.ser and self.ser.is_open):
                self._asegurar_conexion()

            if self.ser and self.ser.is_open:
                try:
                    if self.ser.in_waiting > 0:
                        nuevos_bytes = self.ser.read(self.ser.in_waiting)
                        self._rx_buffer.extend(nuevos_bytes)
                except Exception as e:
                    print(f"[SERIAL ERROR] Error en lectura: {e}")
                    try:
                        self.ser.close()
                    except Exception:
                        pass
                    self.ser = None

            # Buscar delimitación STX (\x02) y ETX (\x03)
            if b"\x02" in self._rx_buffer:
                inicio = self._rx_buffer.find(b"\x02")
                fin = self._rx_buffer.find(b"\x03", inicio)
                if fin != -1:
                    trama_bytes = self._rx_buffer[inicio + 1 : fin]
                    self._rx_buffer = self._rx_buffer[fin + 1 :]
                    texto = trama_bytes.decode("ascii", errors="ignore").strip().upper()
                    return texto, trama_bytes.hex().upper(), bytes(trama_bytes)

            # Fallback si solo hay ETX
            if len(self._rx_buffer) > 0 and b"\x03" in self._rx_buffer:
                fin = self._rx_buffer.find(b"\x03")
                trama_bytes = self._rx_buffer[:fin]
                self._rx_buffer = self._rx_buffer[fin + 1 :]
                texto = trama_bytes.decode("ascii", errors="ignore").strip().upper()
                return texto, trama_bytes.hex().upper(), bytes(trama_bytes)

            return "", "", b""
