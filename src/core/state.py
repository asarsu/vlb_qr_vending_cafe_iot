"""
src/core/state.py
=================
Modelo de estado compartido y sincronizado para la máquina de vending.
"""

import threading
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class VendingState:
    """Estado compartido y thread-safe de la máquina de vending."""
    estado_maquina: str = "BIENVENIDA"
    monto_actual: float = 5.00
    credito_disponible: float = 5.00
    alias_actual: Optional[str] = None
    imagen_qr_tk: Optional[Any] = None  # ImageTk.PhotoImage cuando Tkinter está activo
    codigo_producto_actual: Optional[str] = None
    precio_producto_actual: float = 0.0
    mensaje_alerta: str = ""
    pago_confirmado_flag: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)

    def set_estado(self, nuevo_estado: str):
        with self.lock:
            self.estado_maquina = nuevo_estado

    def get_estado(self) -> str:
        with self.lock:
            return self.estado_maquina
