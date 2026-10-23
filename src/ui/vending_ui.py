"""
src/ui/vending_ui.py
====================
Interfaz gráfica Tkinter para la pantalla táctil del kiosco vending (480x800).

Mejoras respecto a la versión anterior:
  * Paleta cálida unificada (crema / coral / amarillo) con contraste legible.
  * Dibujo estático solo cuando cambia el estado o los datos; las animaciones
    (pulso, spinner, puntos) viven en su propia capa ("anim") y son baratas.
  * Helpers (_t, _tarjeta, _boton) en lugar de ~60 llamadas repetidas.
  * Lectura atómica del estado (un solo lock por frame).
  * El bucle de render sobrevive a excepciones (un kiosco no debe congelarse).
  * Corregido: logo recortado arriba, "Elije" -> "Elige", emoji ⚠️ (no se
    renderiza bien en la Raspberry Pi).

IMPORTANTE: las constantes BTN_* NO se tocaron. Son las coordenadas visuales de
los botones; la calibración táctil vive aparte y no debe derivarse de aquí.
"""

import math
import time
from typing import Callable, Dict, Optional

try:
    import tkinter as tk
    from PIL import Image, ImageTk
    UI_DISPONIBLE = True
except ImportError:
    UI_DISPONIBLE = False

from src.config.settings import AppConfig
from src.core.state import VendingState


def _mezcla(a: str, b: str, k: float) -> str:
    """Interpola dos colores #RRGGBB (k=0 -> a, k=1 -> b)."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * k) for x, y in zip(ca, cb))


class VendingUI:
    """Gestiona la pantalla táctil y el renderizado gráfico de estados."""

    # --- Paleta -----------------------------------------------------------
    BG_COLOR = "#FAF7F0"
    TEXT_COLOR = "#2B2622"
    MUTED = "#7A6F66"
    ACCENT_COLOR = "#2B2622"
    CORAL = "#E8664F"
    CORAL_OSCURO = "#B84848"
    AMARILLO = "#E5B71D"
    AMARILLO_SUAVE = "#FDF3D6"
    AMARILLO_TEXTO = "#7A5A00"
    VERDE = "#1E9E6A"
    ROJO = "#B3261E"
    ROJO_SUAVE = "#FDE8E4"
    AZUL = "#1D4ED8"
    TARJETA = "#FFFFFF"
    BORDE = "#EADFD0"

    FUENTE = "Helvetica"
    FRAME_MS = 80  # ~12 fps: suficiente para pulso/spinner en la Pi

    # --- Botones (coordenadas visuales: NO modificar) -----------------------
    BTN_VOLVER_X0, BTN_VOLVER_Y0 = 20, 680
    BTN_VOLVER_X1, BTN_VOLVER_Y1 = 230, 750

    BTN_COMPRAR_X0, BTN_COMPRAR_Y0 = 250, 680
    BTN_COMPRAR_X1, BTN_COMPRAR_Y1 = 460, 750

    PASOS = (
        "Elige tu bebida en el menú de la máquina.",
        "Abre tu app de pagos preferida, escanea el QR y paga.",
        "Espera la confirmación del crédito en esta pantalla.",
        "Presiona el botón de tu bebida en la máquina Concerto.",
        "Espera la preparación y llenado de tu vaso.",
        "Retira tu café en el compartimiento y ¡disfrútalo!",
    )

    def __init__(self, root: "tk.Tk", config: AppConfig, state: VendingState,
                 on_touch_cb: Callable[[int, int], None]):
        self.root = root
        self.config = config
        self.state = state
        self.on_touch_cb = on_touch_cb

        self.root.attributes("-fullscreen", True)
        self.root.config(cursor="none")
        if self.config.dev_mode:
            self.root.bind("<Escape>", lambda e: self.root.destroy())

        self.canvas = tk.Canvas(
            self.root, width=self.config.screen_w, height=self.config.screen_h, highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.config(bg=self.BG_COLOR)
        self.canvas.bind("<Button-1>", self._handle_touch)

        self._ultima_firma: Optional[tuple] = None
        self._pantallas: Dict[str, Callable] = {
            "BIENVENIDA": self._render_bienvenida,
            "INSTRUCCIONES": self._render_instrucciones,
            "GENERANDO": self._render_generando,
            "MOSTRANDO": self._render_mostrando,
            "DESPACHANDO": self._render_despachando,
            "ENTREGANDO": self._render_entregando,
            "RETIRE_PRODUCTO": self._render_entregando,
            "ERROR_CONEXION_BANCO": self._render_error_banco,
        }
        self._animaciones: Dict[str, Callable] = {
            "BIENVENIDA": self._anim_bienvenida,
            "GENERANDO": self._anim_generando,
            "MOSTRANDO": self._anim_mostrando,
            "DESPACHANDO": self._anim_despachando,
            "ENTREGANDO": self._anim_entregando,
            "RETIRE_PRODUCTO": self._anim_entregando,
            "ERROR_CONEXION_BANCO": self._anim_error_banco,
        }

        self._cargar_recursos()

    # ------------------------------------------------------------------
    # Recursos y eventos
    # ------------------------------------------------------------------
    def _cargar_recursos(self):
        try:
            img = Image.open(self.config.logo_path).convert("RGBA").resize((200, 200), Image.Resampling.LANCZOS)
            self.logo_principal = ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"[UI] No se pudo cargar logo principal: {e}")
            self.logo_principal = None

        try:
            img_qr = Image.open(self.config.qr_icon_path).convert("RGBA").resize((200, 150), Image.Resampling.LANCZOS)
            self.qr_icon = ImageTk.PhotoImage(img_qr)
        except Exception as e:
            print(f"[UI] No se pudo cargar icono decorativo: {e}")
            self.qr_icon = None

    def _handle_touch(self, event):
        self.on_touch_cb(event.x, event.y)

    # ------------------------------------------------------------------
    # Bucle de render
    # ------------------------------------------------------------------
    def _leer_estado(self) -> dict:
        """Snapshot del modelo con un único lock por frame."""
        estado = self.state.get_estado()
        with self.state.lock:
            return {
                "estado": estado,
                "credito": self.state.credito_disponible,
                "alerta": self.state.mensaje_alerta,
                "codigo": self.state.codigo_producto_actual,
                "precio": self.state.precio_producto_actual,
                "qr": self.state.imagen_qr_tk,
            }

    def renderizar(self):
        """Redibuja solo si algo cambió; las animaciones corren aparte."""
        try:
            s = self._leer_estado()
            firma = (s["estado"], s["credito"], s["alerta"], s["codigo"], s["precio"], id(s["qr"]))

            if firma != self._ultima_firma:
                self._ultima_firma = firma
                self.canvas.delete("dinamico")
                pantalla = self._pantallas.get(s["estado"])
                if pantalla:
                    pantalla(self.config.screen_w // 2, s)

            self.canvas.delete("anim")
            anim = self._animaciones.get(s["estado"])
            if anim:
                anim(self.config.screen_w // 2, time.monotonic())
        except Exception as e:  # el kiosco no puede quedarse congelado
            print(f"[UI] Error al renderizar: {e}")
        finally:
            self.root.after(self.FRAME_MS, self.renderizar)

    # ------------------------------------------------------------------
    # Helpers de dibujo
    # ------------------------------------------------------------------
    def _t(self, x, y, texto, size, color=None, bold=False, italic=False, anchor="center", **kw):
        estilo = " ".join(n for n, activo in (("bold", bold), ("italic", italic)) if activo)
        fuente = (self.FUENTE, size, estilo) if estilo else (self.FUENTE, size)
        return self.canvas.create_text(
            x, y, text=texto, font=fuente, fill=color or self.TEXT_COLOR,
            anchor=anchor, tags="dinamico", **kw
        )

    def _poligono_redondeado(self, x0, y0, x1, y1, r, tag, **kw):
        r = min(r, (x1 - x0) // 2, (y1 - y0) // 2)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.canvas.create_polygon(pts, smooth=True, tags=tag, **kw)

    def _tarjeta(self, x0, y0, x1, y1, fill=None, outline=None, width=2, r=20):
        return self._poligono_redondeado(
            x0, y0, x1, y1, r, "dinamico",
            fill=fill or self.TARJETA, outline=outline or self.BORDE, width=width
        )

    def _boton(self, x0, y0, x1, y1, texto, fill, color, outline=None, size=15):
        self._tarjeta(x0, y0, x1, y1, fill=fill, outline=outline or fill, width=2, r=16)
        self._t((x0 + x1) // 2, (y0 + y1) // 2, texto, size, color, bold=True)

    def _pulso(self, x0, y0, x1, y1, t, color, r=24, alcance=22):
        """Dos anillos que se expanden y se desvanecen alrededor de un rectángulo."""
        for i in range(2):
            fase = (t * 0.7 + i * 0.5) % 1.0
            g = int(fase * alcance)
            self._poligono_redondeado(
                x0 - g, y0 - g, x1 + g, y1 + g, r + g, "anim",
                fill="", outline=_mezcla(color, self.BG_COLOR, fase), width=3
            )

    def _puntos(self, cx, y, t, color):
        """Tres puntos de 'esperando' donde se ilumina uno a la vez."""
        activo = int(t * 3) % 3
        for i in range(3):
            x = cx + (i - 1) * 22
            c = color if i == activo else _mezcla(color, self.BG_COLOR, 0.7)
            self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill=c, outline="", tags="anim")

    # ------------------------------------------------------------------
    # Pantallas (capa estática)
    # ------------------------------------------------------------------
    def _render_bienvenida(self, cx: int, s: dict):
        if self.logo_principal:
            self.canvas.create_image(cx, 135, image=self.logo_principal, tags="dinamico")
        else:
            self._t(cx, 135, "[ LOGO CONCERTO ]", 16, bold=True)

        self._t(cx, 275, "PAGA CON QR", 36, self.CORAL_OSCURO, bold=True)
        self._t(cx, 330, "Tu café recién preparado en segundos", 16, self.MUTED, width=400, justify="center")

        self._tarjeta(100, 390, 380, 590, r=24)
        if self.qr_icon:
            self.canvas.create_image(cx, 490, image=self.qr_icon, tags="dinamico")

        self._tarjeta(60, 630, 420, 690, fill=self.CORAL, outline=self.CORAL, r=30)
        self._t(cx, 660, "TOCA LA PANTALLA", 22, "white", bold=True)
        self._t(cx, 718, "para ver las instrucciones", 14, self.MUTED)

        for dx, txt in ((-140, "✓ Seguro"), (0, "✓ Rápido"), (140, "✓ Sin efectivo")):
            self._t(cx + dx, 765, txt, 13, self.VERDE, bold=True)

    def _render_instrucciones(self, cx: int, s: dict):
        self._t(cx, 55, "Cómo comprar", 28, bold=True)
        self.canvas.create_rectangle(cx - 30, 80, cx + 30, 84, fill=self.CORAL, outline="", tags="dinamico")

        for i, texto in enumerate(self.PASOS):
            y = 135 + i * 88
            self.canvas.create_oval(32, y - 20, 72, y + 20, fill=self.CORAL, outline="", tags="dinamico")
            self._t(52, y, str(i + 1), 16, "white", bold=True)
            self._t(92, y, texto, 15, anchor="w", width=360)

        self._boton(self.BTN_VOLVER_X0, self.BTN_VOLVER_Y0, self.BTN_VOLVER_X1, self.BTN_VOLVER_Y1,
                    "Volver atrás", fill=self.TARJETA, color=self.CORAL_OSCURO,
                    outline=self.CORAL_OSCURO, size=14)
        self._boton(self.BTN_COMPRAR_X0, self.BTN_COMPRAR_Y0, self.BTN_COMPRAR_X1, self.BTN_COMPRAR_Y1,
                    "Realizar compra", fill=self.VERDE, color="white", size=15)

    def _render_generando(self, cx: int, s: dict):
        self._t(cx, 450, "Generando tu QR", 26, bold=True)
        self._t(cx, 495, "Conectando con el banco…", 15, self.MUTED)

    def _render_mostrando(self, cx: int, s: dict):
        qr_size = 320
        x0 = (self.config.screen_w - qr_size) // 2
        y0, x1, y1 = 190, x0 + qr_size, 190 + qr_size

        self._t(cx, 100, "Escanea para pagar", 28, bold=True)
        self._t(cx, 148, "con la app de tu banco", 16, self.MUTED)

        self._tarjeta(x0, y0, x1, y1, outline=self.VERDE, width=4)
        if s["qr"]:
            self.canvas.create_image(cx, (y0 + y1) // 2, image=s["qr"], tags="dinamico")
        else:
            self._t(cx, (y0 + y1) // 2, "Cargando imagen…", 16, self.MUTED)

        self._t(cx, 625, "Esperando confirmación de pago", 16, self.CORAL_OSCURO, bold=True)
        self._t(cx, 665, "Paga el monto exacto del producto", 14, self.MUTED)

    def _render_despachando(self, cx: int, s: dict):
        credito, alerta = s["credito"], s["alerta"]

        self.canvas.create_oval(cx - 34, 70, cx + 34, 138, fill=self.VERDE, outline="", tags="dinamico")
        self._t(cx, 104, "✓", 34, "white", bold=True)
        self._t(cx, 175, "¡Pago exitoso!", 28, self.VERDE, bold=True)

        self._tarjeta(40, 215, 440, 345)
        self._t(cx, 245, "CRÉDITO DISPONIBLE", 12, self.MUTED, bold=True)
        self._t(cx, 295, f"Bs. {credito:.2f}", 40, bold=True)

        if alerta:
            self._tarjeta(30, 375, 450, 535, fill=self.ROJO_SUAVE, outline=self.ROJO, width=3)
            self._t(cx, 410, "El monto no coincide", 18, self.ROJO, bold=True)
            self._t(cx, 475, alerta, 14, self.ROJO, justify="center", width=380)
        else:
            self._tarjeta(30, 375, 450, 535, outline=self.VERDE, width=3)
            self._t(cx, 425, "Presiona el botón de tu bebida", 18, bold=True, width=380, justify="center")
            self._t(cx, 475, "en el panel de la máquina Concerto", 15, self.MUTED)

        self._t(cx, 585, f"Elige una opción de hasta Bs. {credito:.2f}", 16, self.VERDE, bold=True)
        self._t(cx, 640, "Esperando selección en la máquina…", 14, self.MUTED, italic=True)

    def _render_entregando(self, cx: int, s: dict):
        codigo, precio, credito = s["codigo"], s["precio"], s["credito"]

        self._t(cx, 105, "¡Venta confirmada!", 28, self.VERDE, bold=True)

        self._tarjeta(50, 160, 430, 330, outline=self.VERDE, width=3)
        self._t(cx, 192, "BEBIDA SELECCIONADA", 12, self.MUTED, bold=True)
        self._t(cx, 250, f"#{codigo}" if codigo else "PREPARANDO", 40, self.CORAL_OSCURO, bold=True)
        if precio > 0:
            self._t(cx, 303, f"Precio cobrado: Bs. {precio:.2f}", 15, self.VERDE, bold=True)

        self._tarjeta(30, 365, 450, 545, fill=self.AMARILLO_SUAVE, outline=self.AMARILLO, width=3)
        self._t(cx, 415, "PREPARANDO BEBIDA", 24, self.AMARILLO_TEXTO, bold=True)
        self._t(cx, 483, "Espera a que finalice la preparación\ny retira tu vaso del compartimiento",
                16, self.AMARILLO_TEXTO, justify="center")

        if credito > 0:
            self._tarjeta(70, 625, 410, 677, fill="#E6EEFD", outline="#E6EEFD", r=26)
            self._t(cx, 651, f"Crédito restante: Bs. {credito:.2f}", 16, self.AZUL, bold=True)

        self._t(cx, 730, "¡Gracias por tu compra!", 20, self.VERDE, bold=True)

    def _render_error_banco(self, cx: int, s: dict):
        # Icono / círculo de advertencia sin emojis para compatibilidad con Raspberry Pi
        self.canvas.create_oval(cx - 45, 120, cx + 45, 210, fill=self.ROJO_SUAVE, outline=self.ROJO, width=3, tags="dinamico")
        self._t(cx, 165, "!", 46, self.ROJO, bold=True)

        self._t(cx, 255, "Medio de pago\nno disponible", 24, self.ROJO, bold=True)
        self._t(cx, 300, "No se pudo conectar con el banco", 16, self.MUTED)

        # Tarjeta informativa central
        self._tarjeta(30, 350, 450, 560, fill=self.TARJETA, outline=self.BORDE, width=2, r=20)
        self._t(cx, 410, "El servicio de QR no responde\nen este momento.", 17, self.TEXT_COLOR, justify="center")
        self._t(cx, 485, "Por favor, utiliza otro\nmétodo de pago.", 18, self.CORAL_OSCURO, bold=True, justify="center")

        # Mensaje inferior orientativo
        self._t(cx, 630, "Regresando al inicio…", 15, self.MUTED, italic=True)

    # ------------------------------------------------------------------
    # Animaciones (capa "anim": se borra y redibuja cada frame)
    # ------------------------------------------------------------------
    def _anim_bienvenida(self, cx: int, t: float):
        self._pulso(100, 390, 380, 590, t, self.CORAL, r=24)

    def _anim_generando(self, cx: int, t: float):
        cy, r = 300, 60
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=self.BORDE, width=10, tags="anim")
        self.canvas.create_arc(cx - r, cy - r, cx + r, cy + r, start=-(t * 300) % 360, extent=110,
                               style="arc", outline=self.CORAL, width=10, tags="anim")

    def _anim_mostrando(self, cx: int, t: float):
        x0 = (self.config.screen_w - 320) // 2
        self._pulso(x0, 190, x0 + 320, 510, t, self.VERDE, r=20, alcance=18)
        self._puntos(cx, 580, t, self.CORAL_OSCURO)

    def _anim_despachando(self, cx: int, t: float):
        self._puntos(cx, 690, t, self.VERDE)

    def _anim_entregando(self, cx: int, t: float):
        y = 585 + 8 * math.sin(t * 6)
        self.canvas.create_text(cx, y, text="▼", font=(self.FUENTE, 26), fill=self.CORAL, tags="anim")

    def _anim_error_banco(self, cx: int, t: float):
        self._puntos(cx, 675, t, self.ROJO)