"""
src/logging_utils/logger.py
===========================
Manejo de logs y redirección de stdout/stderr por ciclo de compra.
"""

import os
import sys
import io
import threading
import datetime


class LogManager:
    """Duplica stdout/stderr a consola y almacena búferes aislados por cada ciclo."""

    class _StreamInterceptor:
        def __init__(self, original_stream, buffer_callback):
            self.original = original_stream
            self.buffer_cb = buffer_callback

        def write(self, mensaje: str):
            self.original.write(mensaje)
            self.original.flush()
            self.buffer_cb(mensaje)

        def flush(self):
            self.original.flush()

    def __init__(self, logs_dir: str):
        self.logs_dir = logs_dir
        os.makedirs(self.logs_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._buffer = io.StringIO()

        self._stdout_interceptor = self._StreamInterceptor(sys.stdout, self._append_log)
        self._stderr_interceptor = self._StreamInterceptor(sys.stderr, self._append_log)

        sys.stdout = self._stdout_interceptor
        sys.stderr = self._stderr_interceptor

    def _append_log(self, texto: str):
        with self._lock:
            self._buffer.write(texto)

    def iniciar_nuevo_ciclo(self):
        with self._lock:
            self._buffer = io.StringIO()

    def _purgar_logs_antiguos(self, max_archivos: int = 200):
        """Mantiene acotado el número de archivos de logs en disco para proteger la tarjeta SD."""
        try:
            archivos = [
                os.path.join(self.logs_dir, f)
                for f in os.listdir(self.logs_dir)
                if f.startswith("log_") and f.endswith(".txt")
            ]
            if len(archivos) > max_archivos:
                # Ordenar por fecha de modificación (los más antiguos primero)
                archivos.sort(key=os.path.getmtime)
                cuantos_eliminar = len(archivos) - max_archivos
                for f_antiguo in archivos[:cuantos_eliminar]:
                    try:
                        os.remove(f_antiguo)
                    except OSError:
                        pass
        except Exception:
            pass

    def guardar_log_ciclo(self, motivo: str = "fin_ciclo", alias: str = "sin_alias"):
        with self._lock:
            contenido = self._buffer.getvalue()

        if not contenido.strip():
            return

        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"log_{timestamp}_{alias}.txt"
            ruta_archivo = os.path.join(self.logs_dir, nombre_archivo)
            with open(ruta_archivo, "w", encoding="utf-8") as f:
                f.write("=== LOG DE CICLO DE COMPRA (v2.0 Modular) ===\n")
                f.write(f"Fecha: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Alias: {alias}\n")
                f.write(f"Motivo fin: {motivo}\n")
                f.write("=" * 38 + "\n\n")
                f.write(contenido)
            print(f"[LOGS] Log guardado con éxito: {ruta_archivo}")
            self._purgar_logs_antiguos(max_archivos=200)
        except Exception as e:
            print(f"[LOGS] Error al guardar archivo de log: {e}")
